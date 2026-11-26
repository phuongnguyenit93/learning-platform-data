# Biến URI trong Spring HATEOAS

Biến URI cho phép một mẫu địa chỉ đại diện cho nhiều URI cụ thể. Thay vì tạo riêng từng đường dẫn cho mọi mã đơn hàng, trạng thái lọc hoặc số trang, API có thể công bố một URI template chứa các biến. Máy khách điền giá trị cần thiết để mở tài nguyên hoặc thực hiện truy vấn.

Trong Spring HATEOAS, **UriTemplate** hỗ trợ khai báo và mở rộng mẫu URI, còn **Link** có thể mang URI template để công bố cho máy khách. Khi kết hợp với **WebMvcLinkBuilder**, ứng dụng cũng có thể tạo URI từ mapping controller mà không phải tự ghép chuỗi đường dẫn.

## 1. URI cụ thể và URI template

Một URI cụ thể xác định một đích đến:

~~~
/orders/42
~~~

URI template mô tả một nhóm URI bằng các biến:

~~~
/orders/{orderId}
~~~

Khi thay **orderId** bằng **42**, mẫu được mở rộng thành **/orders/42**.

| Loại | Ví dụ | Ý nghĩa |
|---|---|---|
| URI cụ thể | /orders/42 | Trỏ đến một đơn hàng |
| URI template | /orders/{orderId} | Mẫu có thể tạo URI cho nhiều đơn hàng |
| URI cụ thể có query | /orders?status=PAID&page=2 | Truy vấn một trang với bộ lọc cụ thể |
| URI template có query | /orders{?status,page,size} | Mẫu tìm kiếm có các tham số tùy chọn |

Biến URI thường xuất hiện ở hai vị trí:

- **Path variable:** nằm trong đường dẫn, dùng để định danh tài nguyên hoặc một phần của cấu trúc tài nguyên.
- **Query variable:** nằm trong query string, thường dùng cho lọc, tìm kiếm, phân trang hoặc sắp xếp.

Ví dụ:

~~~
/orders/{orderId}/items/{itemId}
/orders{?status,page,size,sort}
~~~

Mẫu thứ nhất chứa hai biến đường dẫn. Mẫu thứ hai chứa các biến truy vấn.

## 2. Cú pháp biến theo URI Template

Spring HATEOAS hỗ trợ cú pháp URI template theo RFC 6570. Một số biểu thức thường gặp:

| Biểu thức | Cách mở rộng | Ví dụ |
|---|---|---|
| {id} | Biến đơn giản | /orders/{id} |
| {/id} | Biến được thêm như một segment đường dẫn | /orders{/id} |
| {?page,size} | Bắt đầu query string | /orders{?page,size} |
| {&sort,status} | Bổ sung tham số vào query đã có | /orders{?page}{&sort,status} |
| {+path} | Mở rộng biến cho phép giữ ký tự reserved | /files/{+path} |

Trong API thông thường, hai dạng dễ gặp nhất là **{id}** cho path variable và **{?page,size}** cho query variables.

Ví dụ một mẫu tìm kiếm:

~~~
/orders{?status,page,size,sort}
~~~

Khi máy khách cung cấp status=PAID, page=1, size=20, sort=createdAt,desc, URI được mở rộng thành:

~~~
/orders?status=PAID&page=1&size=20&sort=createdAt%2Cdesc
~~~

Cách mã hóa chính xác phụ thuộc quy tắc mở rộng URI template. Dấu phẩy hoặc ký tự đặc biệt có thể được percent-encode trong giá trị query.

Không nên tự thay biến bằng phép nối chuỗi. URI template xử lý cấu trúc biểu thức và mã hóa giá trị theo quy tắc tương ứng, giảm nguy cơ tạo URL sai khi dữ liệu có dấu cách, dấu &, dấu ? hoặc ký tự Unicode.

## 3. Khai báo và mở rộng UriTemplate

Spring HATEOAS cung cấp lớp org.springframework.hateoas.UriTemplate để tạo và mở rộng mẫu URI.

Ví dụ với path variable:

~~~java
import org.springframework.hateoas.UriTemplate;

import java.util.Map;

UriTemplate template = UriTemplate.of("/orders/{orderId}");

String uri = template.expand(
    Map.of("orderId", 42)
);

// /orders/42
~~~

**UriTemplate.of(...)** tạo một mẫu. **expand(...)** nhận giá trị cho các biến và trả về URI đã mở rộng.

Có thể truyền nhiều biến bằng Map:

~~~java
UriTemplate template =
    UriTemplate.of("/orders/{orderId}/items/{itemId}");

String uri = template.expand(
    Map.of(
        "orderId", 42,
        "itemId", 3
    )
);

// /orders/42/items/3
~~~

Tên khóa trong Map phải khớp với tên biến trong mẫu. Theo quy tắc URI Template, biến không được cung cấp có thể bị bỏ qua khi mở rộng. Nếu hợp đồng nghiệp vụ yêu cầu một giá trị, ứng dụng cần xác thực sự hiện diện của giá trị đó trước khi gọi expand thay vì dựa vào template để kiểm tra.

## 4. Mở rộng query variables

URI template cũng có thể chứa các biến query. Dạng **{?name1,name2}** tạo query string từ những giá trị được cung cấp:

~~~java
import org.springframework.hateoas.UriTemplate;

import java.util.Map;

UriTemplate template =
    UriTemplate.of("/orders{?status,page,size}");

String uri = template.expand(
    Map.of(
        "status", "PAID",
        "page", 1,
        "size", 20
    )
);

// /orders?status=PAID&page=1&size=20
~~~

Các biến query có thể được dùng để công bố khả năng tìm kiếm linh hoạt. Máy khách chỉ cần cung cấp các giá trị cần thiết; các tham số không có giá trị có thể được bỏ qua trong quá trình mở rộng tùy theo quy tắc template.

Với query đã có sẵn, toán tử **{&...}** bổ sung các tham số tiếp theo:

~~~java
UriTemplate template = UriTemplate.of(
    "/orders{?status}{&page,size}"
);

String uri = template.expand(
    Map.of(
        "status", "PAID",
        "page", 1,
        "size", 20
    )
);

// /orders?status=PAID&page=1&size=20
~~~

Dạng này hữu ích khi template được chia thành phần query đầu tiên và phần query bổ sung. Khi thiết kế API, hãy giữ mẫu ngắn, đặt tên biến dễ hiểu và chỉ công bố các tham số mà endpoint thực sự hỗ trợ.

## 5. Xem các biến có trong template

Có thể cần biết một template chứa những biến nào trước khi mở rộng hoặc kiểm tra hợp đồng.

~~~java
import org.springframework.hateoas.UriTemplate;
import java.util.Set;

UriTemplate template =
    UriTemplate.of("/orders{?status,page,size}");

Set<String> variableNames = template.getVariableNames();

// status, page, size
~~~

Danh sách biến giúp kiểm tra mẫu được công bố có đúng những tham số mà máy khách cần hay không. Nó cũng hữu ích khi viết kiểm thử hoặc xây dựng thành phần máy khách tổng quát.

Không nên suy luận rằng mọi biến trong template đều bắt buộc. Cú pháp và toán tử template quyết định cách biến tham gia vào URI; API cần tài liệu hóa biến nào là cần thiết, biến nào tùy chọn và giá trị hợp lệ của chúng.

## 6. Phân biệt URI template variable với Spring MVC path variable

Hai khái niệm có liên quan nhưng phục vụ hai phía khác nhau:

- **URI template variable** là chỗ giữ giá trị trong một mẫu URI, ví dụ {orderId} trong /orders/{orderId}.
- **Spring MVC path variable** là tham số của controller được gắn bằng @PathVariable để nhận giá trị từ request đến.

Ví dụ mapping controller:

~~~java
@GetMapping("/orders/{orderId}")
public OrderDto one(@PathVariable Long orderId) {
    // orderId nhận giá trị từ segment trong request URI.
    throw new UnsupportedOperationException("Ví dụ minh họa");
}
~~~

Biểu thức {orderId} trong mapping và URI template có cùng tên để thể hiện cùng một vị trí dữ liệu, nhưng chúng không tự tạo ra nhau. Khai báo một URI template trong Link không tự đăng ký endpoint; controller vẫn cần mapping và xử lý request tương ứng. Ngược lại, khai báo @PathVariable không tự công bố một link hypermedia cho máy khách.

## 7. Công bố URI template bằng Link

Trong Spring HATEOAS, **Link** có thể mang URI template. Khi href chứa biểu thức biến, link được đánh dấu là templated để máy khách biết cần cung cấp giá trị trước khi gọi URI.

Ví dụ:

~~~java
import org.springframework.hateoas.Link;

Link searchLink = Link.of(
    "/orders{?status,page,size,sort}",
    "search"
);
~~~

Trong HAL JSON, link template được biểu diễn với thuộc tính templated=true:

~~~json
{
  "_links": {
    "search": {
      "href": "/orders{?status,page,size,sort}",
      "templated": true
    }
  }
}
~~~

Máy khách đọc relation search, nhận ra link là template và mở rộng các biến phù hợp trước khi gửi request. Máy khách không cần tự đoán tên endpoint hoặc quy ước query string.

Một template path cũng có thể được công bố:

~~~java
Link orderById = Link.of(
    "/orders/{orderId}",
    "item"
);
~~~

Link template hữu ích khi một biểu diễn công bố khả năng tìm kiếm hoặc điều hướng tới một tài nguyên mà mã định danh chưa được biết tại thời điểm tạo phản hồi.

## 8. Tạo URI từ mapping của controller

Với một tài nguyên cụ thể, nên dùng **WebMvcLinkBuilder** để tạo link từ mapping Spring MVC.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{orderId}")
    public OrderDto one(@PathVariable Long orderId) {
        // Tìm và trả về đơn hàng.
        throw new UnsupportedOperationException("Ví dụ minh họa");
    }
}
~~~

Tạo liên kết đến một đơn hàng cụ thể:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(
    methodOn(OrderController.class).one(42L)
).withSelfRel();
~~~

Spring HATEOAS đọc mapping và giá trị tham số để tạo URI cụ thể /orders/42. Khi mapping controller thay đổi, liên kết được tạo từ phương thức sẽ theo mapping mới.

Đây là trường hợp khác với việc công bố URI template. Khi đã biết orderId, link self thường là URI cụ thể. Khi muốn cho máy khách khám phá một endpoint tìm kiếm với nhiều biến, có thể công bố một link templated riêng.

## 9. Kết hợp URI template với RepresentationModel

Một representation model có thể chứa cả link cụ thể lẫn link template. Ví dụ tài nguyên đơn hàng có self cụ thể và link tìm kiếm các đơn hàng khác:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

OrderDto dto = new OrderDto(42L, "PAID", total);

EntityModel<OrderDto> model = EntityModel.of(dto);

model.add(
    Link.of("/orders/42", "self")
);

model.add(
    Link.of(
        "/orders{?status,page,size,sort}",
        "search"
    )
);
~~~

Trong ví dụ:

- self trỏ đến đơn hàng đang được biểu diễn.
- search công bố một mẫu URI để máy khách tìm kiếm tập hợp đơn hàng.

Không phải mọi link đều cần template. Dùng URI cụ thể khi đích đến đã biết; dùng URI template khi máy khách cần cung cấp giá trị biến để xác định đích đến.

## 10. Encoding và kiểm soát giá trị biến

URI template giúp xử lý cấu trúc và encoding, nhưng không thay thế việc xác thực dữ liệu đầu vào.

Ví dụ, giá trị tìm kiếm có thể chứa dấu cách hoặc ký tự dành riêng:

~~~java
UriTemplate template =
    UriTemplate.of("/orders{?keyword}");

String uri = template.expand(
    Map.of("keyword", "keyboard & mouse")
);
~~~

Giá trị query cần được mã hóa để dấu & bên trong từ khóa không bị hiểu nhầm là dấu phân cách tham số. Khi máy chủ nhận request, framework giải mã query parameter thành giá trị tương ứng.

Các nguyên tắc cần giữ:

- Không nối trực tiếp giá trị người dùng vào path hoặc query string.
- Dùng URI template hoặc URI builder để xử lý encoding.
- Xác thực kiểu dữ liệu và miền giá trị sau khi nhận request.
- Giới hạn độ dài từ khóa, số lượng phần tử và page size.
- Chỉ cho phép các tham số sort đã được API hỗ trợ.
- Không dùng giá trị biến URI để bỏ qua kiểm tra quyền hoặc quyền sở hữu tài nguyên.

Với path variable, cần chú ý các ký tự phân cách như dấu gạch chéo. Nếu giá trị có thể chứa ký tự reserved, phải xác định rõ cách mã hóa và cách server xử lý. Không nên coi một giá trị path tùy ý là an toàn chỉ vì nó đã được đặt trong template.

## 11. Template, tham số tùy chọn và hợp đồng API

Một URI template chỉ mô tả cách tạo URI. Nó không tự định nghĩa quy tắc nghiệp vụ của endpoint.

Ví dụ:

~~~
/orders{?status,page,size,sort}
~~~

Mẫu cho biết endpoint có các biến truy vấn đó, nhưng hợp đồng API vẫn phải mô tả:

| Biến | Quy tắc cần công bố |
|---|---|
| status | Các trạng thái hợp lệ và cách kết hợp |
| page | Chỉ số trang, giá trị mặc định và giới hạn |
| size | Kích thước trang tối đa |
| sort | Tên trường và hướng sắp xếp được hỗ trợ |

Nếu một biến bị bỏ qua, máy chủ cần có hành vi mặc định được tài liệu hóa. Ví dụ không truyền page có thể chọn trang đầu; không truyền size có thể dùng kích thước mặc định. Không nên để máy khách phải đoán các giá trị mặc định này.

URI template cũng không tự công bố HTTP method, request body hay schema của dữ liệu đầu vào. Nếu cần mô tả một thao tác phức tạp, API có thể kết hợp affordance hoặc một định dạng hypermedia hỗ trợ biểu mẫu, chẳng hạn HAL-FORMS.

## 12. Kiểm thử URI template

Kiểm thử đơn vị có thể xác nhận mẫu được mở rộng thành URI mong muốn:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.UriTemplate;

import java.util.Map;

class UriTemplateTest {

    @Test
    void expandsPathVariables() {
        UriTemplate template =
            UriTemplate.of("/orders/{orderId}/items/{itemId}");

        String uri = template.expand(
            Map.of("orderId", 42, "itemId", 3)
        );

        assertThat(uri).isEqualTo("/orders/42/items/3");
    }

    @Test
    void expandsQueryVariables() {
        UriTemplate template =
            UriTemplate.of("/orders{?status,page,size}");

        String uri = template.expand(
            Map.of(
                "status", "PAID",
                "page", 1,
                "size", 20
            )
        );

        assertThat(uri)
            .isEqualTo("/orders?status=PAID&page=1&size=20");
    }
}
~~~

Ngoài kiểm thử mở rộng, nên kiểm tra link được tuần tự hóa:

~~~java
mockMvc.perform(
        get("/orders/42").accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.search.href")
        .value("/orders{?status,page,size,sort}"))
    .andExpect(jsonPath("$._links.search.templated").value(true));
~~~

Cần kiểm thử các tình huống:

- Template có đúng tên biến và toán tử.
- Giá trị path variable được mở rộng đúng.
- Query variables được mã hóa khi có ký tự đặc biệt.
- Tham số tùy chọn bị bỏ qua theo đúng quy tắc.
- Link HAL có templated=true khi cần.
- Các tham số không hợp lệ bị từ chối hoặc chuẩn hóa theo hợp đồng.
- Máy khách không thể dùng biến URI để truy cập tài nguyên ngoài phạm vi quyền.

## 13. Lỗi thường gặp khi dùng biến URI

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm URI template với URI cụ thể | Gửi request khi biến vẫn chưa được mở rộng | Mở rộng template hoặc để máy khách hypermedia xử lý |
| Tự thay biến bằng nối chuỗi | Sai encoding và dấu phân cách | Dùng UriTemplate hoặc URI builder |
| Sai tên biến khi expand | Không tạo được URI đúng | Đối chiếu tên trong mẫu và Map |
| Dùng {?a,b} sau khi đã có query mà không hiểu toán tử | Query string có thể sai cấu trúc | Dùng {&a,b} cho tham số nối tiếp |
| Công bố biến nhưng không tài liệu hóa | Máy khách không biết giá trị hợp lệ | Mô tả kiểu, miền giá trị và mặc định |
| Cho rằng template tự xác thực đầu vào | Giá trị không hợp lệ vẫn có thể đến server | Xác thực ở controller/service |
| Công bố template thay cho link cụ thể khi đã biết đích | Máy khách phải làm thêm bước không cần thiết | Dùng URI cụ thể cho tài nguyên đã định danh |

## 14. Quy trình thiết kế biến URI

Khi công bố URI template trong Spring HATEOAS, hãy thực hiện theo trình tự:

1. Xác định đích đến là một tài nguyên cụ thể hay một endpoint cần tham số.
2. Chọn path variables cho phần định danh và query variables cho lọc, tìm kiếm, phân trang hoặc sắp xếp.
3. Viết template theo cú pháp RFC 6570 phù hợp.
4. Dùng UriTemplate để mở rộng và kiểm thử mẫu ở phía server khi cần.
5. Dùng Link templated để công bố khả năng điều hướng cho máy khách hypermedia.
6. Dùng WebMvcLinkBuilder để tạo URI cụ thể từ mapping controller khi đã biết các tham số.
7. Tài liệu hóa biến bắt buộc, tùy chọn, kiểu dữ liệu, mặc định và giới hạn.
8. Kiểm thử encoding, link HAL và quyền truy cập của endpoint đích.

Biến URI giúp một API công bố khả năng điều hướng linh hoạt mà không cần tạo sẵn một URL cho mọi tổ hợp tham số. Spring HATEOAS hỗ trợ việc này bằng UriTemplate, Link templated và công cụ tạo link từ controller. Khi tên biến, semantics và quy tắc mở rộng được thiết kế rõ ràng, máy khách có thể khám phá và sử dụng API theo hợp đồng hypermedia thay vì tự xây dựng đường dẫn.
