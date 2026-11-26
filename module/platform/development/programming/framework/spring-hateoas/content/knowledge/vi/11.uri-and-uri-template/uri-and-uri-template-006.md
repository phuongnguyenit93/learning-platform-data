# Tham số tùy chọn

## Mục tiêu

Sau bài này, bạn có thể mô tả tham số truy vấn tùy chọn trong URI template, phân biệt tham số vắng mặt với tham số có giá trị rỗng hoặc giá trị mặc định, công bố link tìm kiếm có biến tùy chọn bằng Spring HATEOAS, mở rộng template thành URI cụ thể và kiểm thử hành vi của các biến đó.

## 1. Vì sao cần tham số tùy chọn?

Một endpoint tìm kiếm thường cho phép client kết hợp nhiều tiêu chí. Ví dụ, API đơn hàng có thể lọc theo trạng thái, khách hàng và khoảng ngày, đồng thời hỗ trợ phân trang:

```text
/orders?status=PENDING&customer=acme&page=0&size=20
```

Không phải request nào cũng cần mọi tiêu chí. Người dùng có thể chỉ lọc theo trạng thái, hoặc không đặt bộ lọc nào và chỉ xem danh sách mặc định. Nếu API bắt buộc mọi tham số, client phải gửi những giá trị giả chỉ để thỏa mãn cú pháp.

URI template cho phép mô tả các biến truy vấn mà client có thể cung cấp khi cần. Các biến không được cung cấp sẽ bị bỏ khỏi URI mở rộng. Nhờ vậy, một link tìm kiếm có thể mô tả nhiều cách gọi endpoint mà không cần công bố một URL riêng cho từng tổ hợp bộ lọc.

## 2. Cú pháp biến truy vấn tùy chọn

Với URI template, toán tử `{?...}` mở đầu phần query và liệt kê các biến có thể xuất hiện:

```text
/orders{?status,customer,from,to,page,size}
```

Trong đó:

- `status` là bộ lọc trạng thái.
- `customer` là mã hoặc tên khách hàng.
- `from` và `to` là giới hạn ngày.
- `page` và `size` điều khiển phân trang.

Khi mở rộng template, chỉ những biến có giá trị được cung cấp mới xuất hiện trong query string.

| Biến được cung cấp | URI sau khi mở rộng |
|---|---|
| `status=PENDING`, `page=0`, `size=20` | `/orders?status=PENDING&page=0&size=20` |
| `customer=acme`, `page=0`, `size=20` | `/orders?customer=acme&page=0&size=20` |
| Chỉ `page=0`, `size=20` | `/orders?page=0&size=20` |
| Không cung cấp biến nào | `/orders` |

Thứ tự các biến trong template xác định thứ tự chúng được mở rộng trong query string. Client không cần gửi một tham số không dùng đến; server nhận được request chỉ với các tiêu chí thực sự được cung cấp.

## 3. Phân biệt vắng mặt, rỗng và mặc định

Ba tình huống này có ý nghĩa khác nhau trong hợp đồng API:

| Tình huống | Ví dụ request | Ý nghĩa thường gặp |
|---|---|---|
| Tham số vắng mặt | `/orders` | Client không đặt tiêu chí đó |
| Tham số có giá trị rỗng | `/orders?status=` | Tham số có mặt nhưng giá trị là chuỗi rỗng |
| Tham số có giá trị mặc định | `/orders?page=0&size=20` | Client hoặc server sử dụng giá trị mặc định đã thống nhất |

Theo quy tắc URI template, biến không được cung cấp sẽ bị bỏ qua khi mở rộng. Nếu biến được cung cấp với chuỗi rỗng, nó vẫn có thể tạo ra một tham số có giá trị rỗng, chẳng hạn `status=`. Vì vậy, không nên đưa mọi biến vào map với giá trị rỗng nếu mục tiêu là bỏ qua bộ lọc.

Giá trị mặc định là quy tắc nghiệp vụ hoặc quy tắc API. URI template không tự quyết định rằng `page` mặc định là 0 hay `size` mặc định là 20. Server và client cần thống nhất mặc định đó. Có thể để server áp dụng mặc định khi tham số vắng mặt, hoặc client chủ động đưa giá trị mặc định vào URI.

Một quy tắc dễ kiểm soát là:

- Không đưa biến vào map nếu client không chọn tiêu chí.
- Đưa chuỗi rỗng vào map chỉ khi API định nghĩa chuỗi rỗng là một giá trị có ý nghĩa.
- Đưa giá trị mặc định vào map khi muốn URI thể hiện tường minh lựa chọn của client.
- Kiểm tra dữ liệu đầu vào ở server ngay cả khi URI được tạo từ template do server công bố.

## 4. Công bố link tìm kiếm bằng Spring HATEOAS

Spring HATEOAS có thể công bố URI template dưới dạng một link. Ví dụ:

```java
Link search = Link.of("/orders{?status,customer,from,to,page,size}")
        .withRel("search");
```

Có thể thêm link này vào representation của collection:

```java
@GetMapping
public CollectionModel<EntityModel<Order>> getOrders() {
    CollectionModel<EntityModel<Order>> model =
            orderAssembler.toCollectionModel(orderService.findAll());

    model.add(Link.of("/orders{?status,customer,from,to,page,size}")
            .withRel("search"));

    model.add(linkTo(methodOn(OrderController.class)
            .getOrders()).withSelfRel());

    return model;
}
```

Khi được tuần tự hóa theo HAL, link template được đánh dấu bằng `templated: true`:

```json
{
  "_links": {
    "self": {
      "href": "/orders"
    },
    "search": {
      "href": "/orders{?status,customer,from,to,page,size}",
      "templated": true
    }
  }
}
```

Client có thể đọc relation `search`, nhận ra đây là template và cung cấp những biến mà người dùng đã chọn. Link template mô tả các tiêu chí có thể truyền; nó không có nghĩa tất cả tham số đều bắt buộc.

Trong ứng dụng có context path hoặc base path thay đổi theo môi trường, hãy bảo đảm template được xây dựng từ URI gốc phù hợp với cách triển khai. Ví dụ dùng đường dẫn `/orders` ở trên giả định endpoint được công bố tại root của host.

## 5. Khai báo tham số tùy chọn ở controller

Link template cần khớp với mapping thật của server. Spring MVC cho phép khai báo query parameter không bắt buộc bằng `@RequestParam(required = false)`.

```java
@GetMapping
public PagedModel<EntityModel<Order>> searchOrders(
        @RequestParam(required = false) String status,
        @RequestParam(required = false) String customer,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> result = orderService.search(
            status,
            customer,
            PageRequest.of(page, size)
    );

    return pagedAssembler.toModel(result, orderAssembler);
}
```

Trong ví dụ:

- `status` và `customer` có thể vắng mặt. Khi không có giá trị, Spring MVC gán `null` cho tham số kiểu `String`.
- `page` và `size` có giá trị mặc định khi client không gửi chúng.
- Service nhận tiêu chí tìm kiếm và thông tin trang để tạo kết quả.
- `PagedResourcesAssembler` chuyển `Page<Order>` thành `PagedModel` cùng metadata và link điều hướng.

Các import liên quan:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
```

Nếu dùng `defaultValue` cho một tham số, Spring MVC áp dụng giá trị mặc định khi tham số bị thiếu hoặc có giá trị rỗng. Nếu cần phân biệt rõ chuỗi rỗng với tham số vắng mặt, không nên đặt `defaultValue` cho tham số đó; hãy xử lý quy tắc này trong tầng ứng dụng.

Kiểu dữ liệu cũng quan trọng. Với `int page`, request `page=abc` không thể chuyển đổi thành số và thường dẫn đến lỗi binding. Cần kiểm tra giới hạn như page không âm và size không vượt quá ngưỡng cho phép để tránh truy vấn quá lớn.

## 6. Mở rộng template thành URI cụ thể

Ở phía client hoặc trong một thành phần cần tạo URI cụ thể, có thể mở rộng template bằng `UriTemplate` của Spring HATEOAS.

```java
import java.net.URI;
import java.util.HashMap;
import java.util.Map;

import org.springframework.hateoas.UriTemplate;

Map<String, Object> variables = new HashMap<>();
variables.put("page", 0);
variables.put("size", 20);
variables.put("status", "PENDING");

URI target = UriTemplate
        .of("/orders{?status,customer,from,to,page,size}")
        .expand(variables);
```

URI kết quả có dạng:

```text
/orders?status=PENDING&page=0&size=20
```

Biến `customer`, `from` và `to` không được thêm vào map, nên chúng bị bỏ khỏi URI. Nếu không có tiêu chí trạng thái, chỉ cần không thêm `status`:

```java
Map<String, Object> variables = new HashMap<>();
variables.put("page", 0);
variables.put("size", 20);

URI target = UriTemplate
        .of("/orders{?status,customer,from,to,page,size}")
        .expand(variables);
```

Kết quả:

```text
/orders?page=0&size=20
```

Đừng thêm các key có giá trị `null` để biểu thị biến không dùng đến. Hãy bỏ key khỏi map. Nếu chuỗi rỗng là một giá trị hợp lệ theo hợp đồng, hãy thêm key với chuỗi rỗng một cách tường minh và kiểm thử URI kết quả.

## 7. Encoding giá trị tùy chọn

Giá trị truy vấn có thể chứa dấu cách, dấu tiếng Việt, dấu `&`, `?` hoặc ký tự đặc biệt. Khi mở rộng URI template, dữ liệu cần được encoding theo quy tắc URI để không bị hiểu nhầm thành dấu phân cách cấu trúc.

Ví dụ, nếu `customer` là `An & Bình`, giá trị dấu `&` phải được mã hóa để không tạo thêm một query parameter ngoài ý muốn. Dùng API mở rộng URI template thay vì tự nối chuỗi:

```java
Map<String, Object> variables = new HashMap<>();
variables.put("customer", "An & Bình");
variables.put("page", 0);
variables.put("size", 20);

URI target = UriTemplate
        .of("/orders{?status,customer,page,size}")
        .expand(variables);
```

Client nên sử dụng URI đã mở rộng theo đúng thư viện URI của mình. Tránh mã hóa thủ công toàn bộ template trước khi mở rộng, vì có thể làm thay đổi dấu ngoặc nhọn hoặc gây double encoding. Đồng thời, server vẫn cần xác thực và chuẩn hóa dữ liệu sau khi nhận request.

## 8. Tổ chức nhiều nhóm tham số tùy chọn

Một template có thể công bố nhiều nhóm biến, nhưng nên giữ nó dễ hiểu. Ví dụ:

```text
/orders{?status,customer,from,to,page,size,sort}
```

Có thể phân nhóm theo mục đích:

| Nhóm | Biến | Vai trò |
|---|---|---|
| Bộ lọc nghiệp vụ | `status`, `customer` | Chọn đơn hàng theo thuộc tính |
| Khoảng thời gian | `from`, `to` | Giới hạn thời điểm tạo |
| Phân trang | `page`, `size` | Chọn lát cắt kết quả |
| Sắp xếp | `sort` | Chọn thứ tự kết quả |

Không nên đưa biến vào template nếu endpoint không hỗ trợ nó. Mỗi biến công bố cần có quy tắc về kiểu dữ liệu, định dạng, giá trị hợp lệ và cách xử lý khi vắng mặt. Với ngày tháng, hãy ghi rõ định dạng, ví dụ ISO-8601 `yyyy-MM-dd`; với sắp xếp, hãy quy định tên trường và chiều sắp xếp được chấp nhận.

Khi API phát triển, có thể bổ sung biến tùy chọn mới mà vẫn giữ các client cũ hoạt động nếu server tiếp tục chấp nhận request không có biến mới. Tuy nhiên, đổi tên hoặc đổi ý nghĩa của biến đã công bố có thể phá vỡ client. Hãy xem tên và semantics của biến template là một phần hợp đồng API.

## 9. Kiểm thử template và tham số tùy chọn

Kiểm thử response cần xác nhận link tìm kiếm có đúng template và được đánh dấu là templated:

```java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href")
            .value(containsString("{?status,customer,from,to,page,size}")));
```

Cần kiểm tra endpoint với nhiều tổ hợp tham số:

```java
mockMvc.perform(get("/orders")
        .param("status", "PENDING")
        .param("page", "0")
        .param("size", "20"))
    .andExpect(status().isOk());
```

Và trường hợp không có bộ lọc:

```java
mockMvc.perform(get("/orders"))
    .andExpect(status().isOk());
```

Nên bổ sung các trường hợp:

1. Tham số tùy chọn bị bỏ qua không làm request thất bại.
2. Tham số có giá trị rỗng được xử lý đúng quy tắc đã công bố.
3. Tham số phân trang vắng mặt nhận đúng giá trị mặc định.
4. Giá trị không hợp lệ bị từ chối hoặc chuẩn hóa theo chính sách API.
5. Giá trị có ký tự đặc biệt được encoding và giải mã đúng.
6. Link template và mapping controller sử dụng cùng tên biến và semantics.

Có thể kiểm thử riêng việc mở rộng `UriTemplate` để xác nhận biến vắng mặt không xuất hiện trong query string. Những kiểm thử này giúp tránh lỗi phổ biến như URL có dấu `&` thừa, query parameter rỗng ngoài ý muốn hoặc template công bố một biến mà controller không nhận.

## 10. Nguyên tắc thiết kế

- **Chỉ công bố biến endpoint thực sự hỗ trợ:** template và controller phải có cùng vocabulary.
- **Bỏ biến không dùng:** không thêm key vào map khi client không chọn bộ lọc.
- **Phân biệt vắng mặt và rỗng:** quy định rõ hai trường hợp có ý nghĩa gì.
- **Công bố giá trị mặc định:** cho biết server áp dụng mặc định nào khi client không gửi tham số.
- **Encoding đúng vị trí:** dùng URI template expansion hoặc builder, tránh ghép query string bằng tay.
- **Giữ semantics ổn định:** tên biến, kiểu dữ liệu và quy tắc mặc định thuộc hợp đồng với client.

## Kết luận

URI template với toán tử `{?...}` giúp công bố các tham số truy vấn tùy chọn trong một link tìm kiếm. Spring HATEOAS có thể phát hành link template với relation `search`, còn `UriTemplate.expand(...)` tạo URI cụ thể từ các biến mà client cung cấp. Bỏ key khi không dùng, phân biệt chuỗi rỗng với tham số vắng mặt, thống nhất giá trị mặc định với controller và kiểm thử encoding sẽ giúp API tìm kiếm linh hoạt mà vẫn giữ hợp đồng hypermedia rõ ràng.

