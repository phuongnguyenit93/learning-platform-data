# Serialize PagedModel

`PagedModel<T>` là kiểu representation của Spring HATEOAS dành cho collection có metadata phân trang và các liên kết hypermedia. Khi serialize thành HAL JSON, một response phân trang thường có ba phần chính: các phần tử được nhúng trong `_embedded`, các link điều hướng trong `_links` và thông tin trang trong `page`.

Điểm cần phân biệt là `Page<T>` của Spring Data mô tả kết quả truy vấn ở phía server, còn `PagedModel<T>` mô tả representation HTTP mà client nhận được. `PagedResourcesAssembler` giúp chuyển từ `Page<T>` sang `PagedModel` và tạo các link phân trang; Spring HATEOAS cùng message converter chịu trách nhiệm serialize model theo media type đã chọn.

## Từ Page đến PagedModel

`Page<T>` thường được repository trả về khi truy vấn có `Pageable`. Nó chứa nội dung của trang hiện tại và metadata như số phần tử, tổng số phần tử, tổng số trang và số trang hiện tại. Đây là đối tượng phục vụ xử lý dữ liệu ở server.

`PagedModel<T>` là representation model có thể chứa các model phần tử, `PageMetadata` và link. Nó đưa thông tin cần thiết để client hiểu collection đang ở trang nào và điều hướng tới trang khác. Client không cần biết repository, câu SQL hoặc cách server tính offset.

| Kiểu | Mục đích | Nơi thường sử dụng |
| --- | --- | --- |
| `Page<T>` | Kết quả truy vấn có phân trang, gồm nội dung và metadata trang | Repository và service |
| `Pageable` | Mô tả yêu cầu trang, kích thước và sắp xếp | Tham số đầu vào của controller/service |
| `PagedModel<T>` | Representation hypermedia cho collection phân trang | Controller và HTTP response |
| `PagedModel.PageMetadata` | Metadata của trang được công bố cho client | Bên trong `PagedModel` |
| `PagedResourcesAssembler<T>` | Chuyển `Page<T>` thành `PagedModel` và tạo link phân trang | Controller hoặc lớp trình bày |

Với Spring Data, `Page<T>` thường cần biết tổng số phần tử để tính `totalPages`; tùy repository và cách truy vấn, việc này có thể phát sinh thêm count query. Nếu ứng dụng không cần tổng số trang, có thể cân nhắc mô hình dạng `Slice` hoặc cursor pagination và tự thiết kế representation/link phù hợp thay vì công bố metadata tổng mà server không có.

## Cấu trúc HAL JSON khi serialize

Với media type `application/hal+json`, representation phân trang thường có cấu trúc như sau:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PENDING",
        "total": 125000,
        "_links": {
          "self": {
            "href": "https://api.example.com/orders/42"
          }
        }
      },
      {
        "id": 43,
        "status": "PAID",
        "total": 89000,
        "_links": {
          "self": {
            "href": "https://api.example.com/orders/43"
          }
        }
      }
    ]
  },
  "_links": {
    "first": {
      "href": "https://api.example.com/orders?page=0&size=20"
    },
    "self": {
      "href": "https://api.example.com/orders?page=0&size=20"
    },
    "next": {
      "href": "https://api.example.com/orders?page=1&size=20"
    },
    "last": {
      "href": "https://api.example.com/orders?page=2&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 45,
    "totalPages": 3,
    "number": 0
  }
}
```

Ý nghĩa từng phần:

- `_embedded.orders` chứa các phần tử của trang hiện tại. Mỗi phần tử có thể là một `EntityModel` với dữ liệu và link riêng.
- `_links` ở cấp ngoài mô tả collection/trang hiện tại và các trang có thể điều hướng tới.
- `page` chứa metadata phân trang. `size` là kích thước trang, `totalElements` là tổng số phần tử, `totalPages` là tổng số trang và `number` là chỉ số trang hiện tại, thường bắt đầu từ `0`.

Các link `prev` hoặc `next` chỉ xuất hiện khi có trang tương ứng để điều hướng. Ví dụ ở trang đầu không có `prev`; ở trang cuối không có `next`. Link `first`, `last` cũng phụ thuộc khả năng xác định trang đầu và cuối. Client nên kiểm tra sự tồn tại của relation thay vì giả định mọi response đều có đủ tất cả link.

Tên `orders` trong `_embedded` phụ thuộc relation provider và cấu hình relation của ứng dụng. Có thể công bố tên item và collection một cách rõ ràng bằng `@Relation` trên kiểu representation:

```java
import java.math.BigDecimal;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderRepresentation(
    Long id,
    String status,
    BigDecimal total
) {}
```

Khi dùng `EntityModel<OrderRepresentation>` trong `PagedModel`, relation collection được dùng làm tên phần nhúng. Hãy giữ relation ổn định vì client có thể dựa vào nó để tìm danh sách phần tử trong `_embedded`.

## Tạo representation phần tử

Mỗi phần tử nên được ánh xạ thành model riêng, thường bằng `RepresentationModelAssembler`. Assembler tạo nội dung và link `self` cho từng đơn hàng, dùng lại `OrderRepresentation` đã định nghĩa ở trên:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        OrderRepresentation body = new OrderRepresentation(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );

        return EntityModel.of(body,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel());
    }
}
```

`Order` và `OrderController` là các kiểu thuộc ứng dụng minh họa. Assembler kiểm soát dữ liệu được công bố và link của từng phần tử. `PagedResourcesAssembler` sẽ gọi assembler này cho nội dung của trang khi tạo representation phân trang.

## Serialize bằng PagedResourcesAssembler trong controller

Controller nhận `Pageable`, truy vấn `Page<Order>` và chuyển page thành `PagedModel`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderRepository repository;
    private final OrderModelAssembler assembler;

    OrderController(OrderRepository repository, OrderModelAssembler assembler) {
        this.repository = repository;
        this.assembler = assembler;
    }

    @GetMapping(produces = "application/hal+json")
    PagedModel<EntityModel<OrderRepresentation>> all(
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> page = repository.findAll(pageable);
        return pagedAssembler.toModel(page, assembler);
    }

    @GetMapping("/{id}")
    EntityModel<OrderRepresentation> one(@PathVariable Long id) {
        Order order = repository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
        return assembler.toModel(order);
    }
}
```

Ví dụ giả định `OrderRepository` hỗ trợ `findAll(Pageable)` và `OrderModelAssembler` triển khai `RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>>`. `PagedResourcesAssembler.toModel(page, assembler)` thực hiện hai việc quan trọng: ánh xạ từng phần tử bằng assembler và tạo metadata cùng link phân trang cho `PagedModel`.

Client có thể gọi `/orders?page=0&size=20&sort=createdAt,desc`. `Pageable` nhận tham số trang, kích thước và sắp xếp; response được trả theo HAL JSON do `produces` chỉ định. Trong cấu hình Spring Boot có Spring Data web support, resolver có thể chuyển query parameter thành `Pageable`. Với cấu hình không dùng Boot, cần bật cấu hình Spring Data web phù hợp để có resolver cho `Pageable` và `PagedResourcesAssembler`.

Không cần tự tạo chuỗi JSON, tự thêm `page` hoặc tự tính link `next`. Hãy trả về `PagedModel` từ controller và để bộ chuyển đổi hypermedia của Spring HATEOAS serialize model.

## Cấu hình media type và serializer

Serialization của hypermedia phụ thuộc media type và các module Jackson mà Spring HATEOAS cung cấp. Trong ứng dụng Spring Boot, `spring-boot-starter-hateoas` là cách thông dụng để tích hợp Spring HATEOAS với Spring MVC và cấu hình hỗ trợ HAL. Request có thể yêu cầu HAL bằng header:

```http
GET /orders?page=0&size=20 HTTP/1.1
Accept: application/hal+json
```

Response tương ứng nên có `Content-Type: application/hal+json`. Header `Accept` thể hiện định dạng client muốn nhận; `Content-Type` cho biết định dạng response thực tế. Nếu endpoint khai báo `produces = "application/hal+json"`, Spring MVC có thể dùng thông tin này trong content negotiation.

Trong ứng dụng không dùng Spring Boot, có thể bật hỗ trợ hypermedia HAL bằng cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;

@Configuration
@EnableHypermediaSupport(type = EnableHypermediaSupport.HypermediaType.HAL)
class HypermediaConfiguration {
}
```

Nếu serialize thủ công ngoài luồng Spring MVC, không nên tạo một `new ObjectMapper()` trống rồi kỳ vọng nó tự hiểu `PagedModel`, `_links` và `_embedded`. Hãy dùng `ObjectMapper` đã được cấu hình với các module hypermedia phù hợp của ứng dụng. Trong controller thông thường, trả về model để message converter thực hiện serialization giúp cấu hình nhất quán hơn.

## Metadata và link phân trang

`PagedModel.PageMetadata` cung cấp thông tin trang đã được chọn để công bố. Các trường có ý nghĩa như sau:

| Trường JSON | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `size` | Kích thước trang được yêu cầu/áp dụng | `20` |
| `totalElements` | Tổng số phần tử thỏa điều kiện truy vấn | `45` |
| `totalPages` | Tổng số trang theo kích thước trang | `3` |
| `number` | Chỉ số trang hiện tại, bắt đầu từ `0` | `0` |

Các link điều hướng thường gồm:

- `first`: quay về trang đầu.
- `prev`: đến trang trước nếu trang hiện tại lớn hơn trang đầu.
- `self`: truy cập lại trang hiện tại với bộ lọc, sắp xếp và tham số trang tương ứng.
- `next`: đến trang sau nếu còn dữ liệu.
- `last`: đến trang cuối khi tổng số trang được xác định.

Link là nguồn điều hướng đáng tin cậy hơn việc client tự dựng URL. Server có thể thay đổi tên query parameter, cơ chế phân trang hoặc cấu trúc route mà vẫn giữ relation và cập nhật `href` tương ứng. Nếu dùng cursor pagination, URI link có thể mang cursor thay vì `page`; client vẫn theo relation `next` hoặc `prev`.

## Kiểm thử response PagedModel

Nên kiểm thử qua HTTP để xác nhận cả quá trình tạo model lẫn serialization. Ví dụ với MockMvc:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$.page.size").value(20))
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$._links.self.href").exists());
```

Tùy dữ liệu fixture, có thể kiểm tra thêm `totalElements`, `totalPages`, link `next` ở trang đầu và link `prev` ở trang kế tiếp. Với trang cuối, xác nhận `next` không còn xuất hiện. Kiểm tra cả link `self` và `next` có giữ tham số lọc/sắp xếp cần thiết hay không.

Không nên phụ thuộc vào thứ tự các thuộc tính JSON. Hãy kiểm tra theo đường dẫn JSON và ý nghĩa của relation. Nếu relation nhúng là `orders`, test cần khớp với cấu hình relation mà ứng dụng công bố; khi đổi tên relation, cần xem đó là thay đổi hợp đồng và cập nhật client/test có chủ đích.

## Những lỗi thường gặp khi serialize PagedModel

- **Trả `Page<T>` trực tiếp:** response có thể phơi bày cấu trúc nội bộ của Spring Data và thiếu hypermedia link như mong muốn. Chuyển thành `PagedModel` khi hợp đồng API cần representation hypermedia.
- **Tự serialize bằng ObjectMapper trống:** thiếu module hypermedia có thể khiến `_links`, `_embedded` hoặc metadata không được biểu diễn đúng. Dùng cấu hình Jackson do Spring HATEOAS tích hợp.
- **Chọn sai media type:** client yêu cầu HAL nhưng server trả JSON thường hoặc không thương lượng được. Kiểm tra `Accept`, `produces` và `Content-Type`.
- **Thiếu relation cho phần nhúng:** `_embedded` có tên mặc định không phù hợp hoặc không ổn định. Định nghĩa relation rõ ràng và kiểm tra response.
- **Tự ghép link phân trang:** dễ làm mất filter, sort hoặc context path. Dùng `PagedResourcesAssembler` hoặc cơ chế URI builder phù hợp.
- **Nhầm chỉ số trang:** `number` thường bắt đầu từ `0`; giao diện người dùng có thể hiển thị số thứ tự bắt đầu từ `1`, nhưng không nên thay đổi ý nghĩa metadata của API.
- **Công bố tổng số không cần thiết:** count query có thể tốn kém với tập dữ liệu lớn. Chọn `Page`, `Slice` hoặc cursor pagination theo nhu cầu thực tế.

Serialize `PagedModel` đúng cách giúp client nhận dữ liệu của trang hiện tại, hiểu metadata và khám phá các trang kế tiếp bằng hypermedia. Khi dùng `PagedResourcesAssembler`, relation ổn định, media type phù hợp và kiểm thử response HTTP, Spring HATEOAS có thể giữ cho hợp đồng phân trang rõ ràng dù cách truy vấn hoặc cấu trúc nội bộ của server thay đổi.
