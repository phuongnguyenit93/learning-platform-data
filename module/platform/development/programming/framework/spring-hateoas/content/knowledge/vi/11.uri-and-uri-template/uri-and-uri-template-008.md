# Template và path variable

URI template là một mẫu URI có chứa biến để một phần của địa chỉ có thể được xác định khi cần. Trong REST API, template thường được dùng để công bố một đường dẫn có tham số tìm kiếm, lọc hoặc phân trang. Path variable là biến nằm trong đường dẫn của một endpoint, thường đại diện cho định danh của tài nguyên.

Spring HATEOAS hỗ trợ biểu diễn liên kết có URI template. Khi client nhận một liên kết như `/orders{?status,page,size}`, client có thể điền các giá trị phù hợp để tạo URI truy vấn. Với tài nguyên cụ thể, server thường tạo liên kết đã có giá trị bằng `linkTo(methodOn(...))`, nhờ đó client không phải tự ghép ID vào đường dẫn.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt URI đầy đủ, URI template và path variable.
- Nhận diện biến đường dẫn trong mapping Spring MVC bằng `@PathVariable`.
- Mô tả biến query bằng cú pháp URI template.
- Tạo `Link` chứa template và nhận biết thuộc tính `templated` trong HAL.
- Dùng `UriTemplate` để mở rộng biến thành URI cụ thể.
- Chọn giữa liên kết đã mở rộng và liên kết template khi thiết kế API.

## URI và URI template

Một URI cụ thể xác định một đích đến. Ví dụ:

```text
https://api.example.test/orders/42
```

URI template mô tả một nhóm URI có cùng cấu trúc:

```text
https://api.example.test/orders/{id}
```

`{id}` là biến. Khi thay `id` bằng `42`, template tạo ra URI cụ thể `/orders/42`. Một template có thể chứa nhiều biến:

```text
https://api.example.test/orders/{id}{?projection}
https://api.example.test/orders{?status,page,size,sort}
```

Template đầu tiên có biến đường dẫn `id` và biến query tùy chọn `projection`. Template thứ hai mô tả endpoint danh sách với các tham số query có thể được cung cấp khi tìm kiếm.

URI template giúp server công bố cấu trúc tham số cần thiết để client hoàn thành một URI. Client không phải tự suy ra tên tham số hoặc quy tắc ghép chuỗi từ tài liệu endpoint.

Các ví dụ đơn hàng trong bài dùng DTO và service contract tối giản sau:

```java
import java.util.List;

public record OrderView(long id, String status) {
}

interface OrderService {
    OrderView findById(long id);
    OrderView findForCustomer(long customerId, long orderId);
    List<OrderView> search(String status, int page, int size);
    OrderView findById(long id, String projection, String locale);
}
```

## Path variable trong Spring MVC

Path variable là phần biến nằm trong path của mapping. Trong Spring MVC, dùng `{name}` trong mapping và `@PathVariable` trong tham số phương thức:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    OrderView one(@PathVariable("id") long id) {
        return orders.findById(id);
    }
}
```

Request `GET /orders/42` gán giá trị `42` cho tham số `id`. Mapping xác định một tài nguyên đơn lẻ dựa trên định danh đó.

Một mapping có thể có nhiều path variable:

```java
@GetMapping("/customers/{customerId}/orders/{orderId}")
OrderView oneForCustomer(
        @PathVariable long customerId,
        @PathVariable long orderId) {
    return orders.findForCustomer(customerId, orderId);
}
```

Trong trường hợp này, URI `/customers/7/orders/42` cung cấp hai giá trị độc lập: `customerId=7` và `orderId=42`. Path variable thường dùng cho phần định danh tài nguyên trong cấu trúc đường dẫn.

Tên biến trong mapping và tham số có thể được liên kết tường minh bằng `@PathVariable("orderId")`. Khi bỏ tên trong annotation, Spring cần xác định được tên tham số từ metadata biên dịch. Khai báo rõ tên hữu ích khi tên tham số Java khác tên biến URI hoặc khi muốn code dễ đọc.

## Path variable và query parameter khác nhau thế nào?

Path variable là một phần của path, thường định danh tài nguyên. Query parameter nằm sau dấu `?`, thường dùng để lọc, phân trang, sắp xếp hoặc chọn projection.

| Đặc điểm | Path variable | Query parameter |
|---|---|---|
| Vị trí | Trong đường dẫn | Sau dấu `?` |
| Ví dụ | `/orders/42` | `/orders?status=NEW&page=0` |
| Spring MVC | `@PathVariable` | `@RequestParam` |
| Vai trò phổ biến | Định danh tài nguyên hoặc tài nguyên con | Lọc, tìm kiếm, phân trang, tùy chọn biểu diễn |
| Tính bắt buộc | Thường bắt buộc để khớp mapping | Có thể tùy chọn hoặc bắt buộc tùy endpoint |

Ví dụ endpoint tìm đơn hàng:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import java.util.List;

@GetMapping
List<OrderView> search(
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {
    return orders.search(status, page, size);
}
```

Client có thể gọi `/orders?status=NEW&page=0&size=20`. Trong API thực tế, cần kiểm tra giới hạn `size`, giá trị `page` và các trường được phép sắp xếp. URI template có thể công bố những tham số mà client được phép cung cấp.

## Cú pháp URI template

Spring HATEOAS sử dụng URI template theo quy ước RFC 6570. Biểu thức trong dấu ngoặc nhọn cho biết cách mở rộng biến vào URI. Một số dạng thường gặp:

| Cú pháp | Ý nghĩa | Ví dụ template |
|---|---|---|
| `{id}` | Mở rộng biến theo dạng chuỗi đơn giản | `/orders/{id}` |
| `{/id}` | Mở rộng biến thành một path segment có dấu `/` | `/orders{/id}` |
| `{?page,size}` | Thêm query string với các biến đã có giá trị | `/orders{?page,size}` |
| `{&sort}` | Thêm tham số query tiếp nối vào query string | `/orders{?page}{&sort}` |

Ví dụ `/orders{?status,page,size}` có thể mở rộng thành:

```text
/orders?status=NEW&page=0&size=20
```

Nếu `status` không được cung cấp, biến tùy chọn đó được bỏ khỏi query khi mở rộng. Ngược lại, biến đường dẫn như `{id}` cần có giá trị hợp lệ để tạo URI trỏ tới tài nguyên cụ thể.

Các giá trị được mở rộng theo quy tắc URI template và mã hóa URI phù hợp. Không nên tự nối chuỗi với dữ liệu do client nhập, vì ký tự như dấu cách, `&`, `?` hoặc `/` có thể làm thay đổi cấu trúc URI nếu không được mã hóa đúng.

## Tạo liên kết có template bằng Spring HATEOAS

`Link` có thể chứa một URI template. Khi template có biến chưa mở rộng, Spring HATEOAS nhận diện liên kết là templated. Ví dụ:

```java
import org.springframework.hateoas.Link;

Link search = Link.of(
    "/orders{?status,page,size,sort}",
    "search"
);

Link orderTemplate = Link.of(
    "/orders/{id}",
    "order"
);
```

`search` mô tả endpoint danh sách có các tham số query tùy chọn. `orderTemplate` mô tả cấu trúc đường dẫn chi tiết có biến `id`. Liên kết template có thể được dùng khi client được phép chọn giá trị biến. Trong nhiều API, liên kết template tới tài nguyên chi tiết chỉ hữu ích khi client thực sự cần chọn ID; khi server đang trả representation của một đơn hàng cụ thể, nên cung cấp `self` đã mở rộng tới đúng ID.

HAL thể hiện một liên kết template bằng thuộc tính `templated: true`:

```json
{
  "_links": {
    "search": {
      "href": "/orders{?status,page,size,sort}",
      "templated": true
    }
  }
}
```

Client đọc `href`, nhận biết `templated`, rồi mở rộng các biến theo cú pháp template trước khi gửi request. Với liên kết không có `templated: true`, client có thể dùng trực tiếp `href` như URI đích.

## Dùng `UriTemplate` để mở rộng biến

Spring HATEOAS cung cấp `UriTemplate` để làm việc với template thay vì xử lý chuỗi thủ công. Ví dụ:

```java
import java.net.URI;
import java.util.Map;

import org.springframework.hateoas.UriTemplate;

UriTemplate template = UriTemplate.of(
    "/orders/{id}{?projection}"
);

URI detailUri = template.expand(Map.of(
    "id", 42,
    "projection", "summary"
));

// detailUri tương ứng với /orders/42?projection=summary
```

Với template tìm kiếm, có thể chỉ cung cấp những biến cần dùng:

```java
UriTemplate searchTemplate = UriTemplate.of(
    "/orders{?status,page,size}"
);

URI searchUri = searchTemplate.expand(Map.of(
    "status", "NEW",
    "page", 0,
    "size", 20
));
```

Kết quả là URI `/orders?status=NEW&page=0&size=20`. Việc mở rộng template giữ logic mã hóa giá trị theo quy tắc URI. Nếu biến bắt buộc không được cung cấp hoặc template không hợp lệ, cần xử lý lỗi trước khi gửi request.

Có thể đặt `UriTemplate` trực tiếp vào `Link` để giữ template trong representation:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.UriTemplate;

UriTemplate searchTemplate = UriTemplate.of("/orders{?status,page,size}");

Link searchLink = Link.of(
    searchTemplate,
    LinkRelation.of("search")
);
```

Ở đây, `searchLink` giữ nguyên template để serialize cho client khám phá. Nếu ứng dụng cần tạo URI cụ thể ở phía server, gọi `expand(...)` trên template rồi sử dụng URI kết quả.

## Tạo URI cụ thể từ controller với `linkTo` và `methodOn`

Trong Spring HATEOAS, `WebMvcLinkBuilder` tạo liên kết dựa trên mapping Spring MVC. Khi truyền giá trị path variable vào lời gọi `methodOn`, liên kết được tạo sẽ chứa URI cụ thể của tài nguyên:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable long id) {
        OrderView order = orders.findById(id);

        return EntityModel.of(
            order,
            linkTo(methodOn(OrderController.class).one(id)).withSelfRel()
        );
    }
}
```

Nếu `id=42`, liên kết `self` sẽ trỏ tới `/orders/42`. `methodOn` tạo lời gọi proxy để Spring HATEOAS đọc mapping và tham số; `linkTo` xây URI từ metadata đó. Khi đổi mapping của controller, liên kết được tạo theo mapping mới mà code không cần tự nối chuỗi `"/orders/" + id`.

Đây là cách nên dùng cho liên kết tới tài nguyên hiện tại vì server đã biết ID. URI template phù hợp hơn cho những liên kết mà client cần cung cấp giá trị, chẳng hạn tìm kiếm, lọc hoặc chọn trang.

## Kết hợp path variable và query template

Một template có thể chứa path variable và query variable cùng lúc. Ví dụ API cho phép đọc một đơn hàng theo ID và chọn projection:

```text
/orders/{id}{?projection,locale}
```

Client cung cấp `id=42`, `projection=summary`, `locale=vi` để tạo URI:

```text
/orders/42?projection=summary&locale=vi
```

Trong Spring MVC, endpoint có thể khai báo:

```java
@GetMapping("/{id}")
OrderView one(
        @PathVariable long id,
        @RequestParam(required = false) String projection,
        @RequestParam(required = false) String locale) {
    return orders.findById(id, projection, locale);
}
```

Path variable xác định đơn hàng. Query parameters thay đổi cách chọn hoặc biểu diễn dữ liệu. Khi công bố template, tên biến phải khớp với hợp đồng endpoint để client không gửi tham số vô nghĩa.

## Kiểm thử URI template và liên kết

Có thể kiểm thử template trực tiếp bằng cách mở rộng các giá trị và xác nhận URI tạo ra:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.UriTemplate;

class OrderUriTemplateTest {

    @Test
    void expandsPathAndQueryVariables() {
        UriTemplate template = UriTemplate.of(
            "/orders/{id}{?projection}"
        );

        var uri = template.expand(Map.of(
            "id", 42,
            "projection", "summary"
        ));

        assertThat(uri.toString())
            .isEqualTo("/orders/42?projection=summary");
    }

    @Test
    void marksSearchLinkAsTemplated() {
        Link link = Link.of("/orders{?status,page,size}", "search");

        assertThat(link.isTemplated()).isTrue();
    }
}
```

Trong kiểm thử controller, nên kiểm tra cả URI cụ thể của `self` và `templated: true` của liên kết tìm kiếm. Nếu API công bố template cho client, một kiểm thử tích hợp có thể lấy `href` từ response, mở rộng các biến theo dữ liệu test rồi gọi URI vừa tạo.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm path variable với query parameter | Gửi request sai cấu trúc URI | Dùng `@PathVariable` cho biến path và `@RequestParam` cho query |
| Tự nối chuỗi ID vào URI | Dễ sai encoding và phụ thuộc mapping | Dùng `linkTo(methodOn(...))` để tạo link cụ thể |
| Trả template nhưng không đánh dấu `templated` | Client không biết cần mở rộng biến | Dùng `Link` chứa URI template để Spring HATEOAS serialize đúng thuộc tính |
| Công bố tên biến không khớp endpoint | Client mở rộng template nhưng request không khớp mapping | Giữ tên biến nhất quán với hợp đồng API |
| Không mã hóa giá trị query/path | Ký tự đặc biệt có thể làm sai URI | Dùng cơ chế mở rộng template thay vì nối chuỗi |
| Dùng template cho tài nguyên đã biết ID | Client phải làm thêm bước mở rộng không cần thiết | Trả URI cụ thể cho `self` và tài nguyên hiện tại |
| Cho rằng template mô tả HTTP method và body | Client vẫn chưa biết cách gửi thao tác | Kết hợp affordance hoặc media type mô tả thao tác khi cần |

## Ghi nhớ

URI template là mẫu URI có biến; path variable là biến nằm trong đường dẫn và thường định danh tài nguyên. Trong Spring MVC, `@PathVariable` gắn biến path với tham số phương thức, còn `@RequestParam` xử lý query parameter. Spring HATEOAS có thể công bố liên kết template qua `Link`, serialize thành HAL với `templated: true`, và dùng `UriTemplate` để mở rộng biến thành URI cụ thể. Dùng `linkTo(methodOn(...))` khi server đã biết tài nguyên cần liên kết; dùng template khi client cần cung cấp giá trị lọc, tìm kiếm hoặc phân trang.
