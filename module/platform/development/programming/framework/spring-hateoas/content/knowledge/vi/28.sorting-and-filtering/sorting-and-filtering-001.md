# Link cho sorting

Khi một REST API trả về collection, client thường cần xem dữ liệu theo nhiều thứ tự khác nhau: đơn hàng mới nhất trước, tổng tiền tăng dần hoặc khách hàng theo tên. Query parameter như `sort=createdAt,desc` cho server biết thứ tự mong muốn. Với hypermedia, server có thể công bố các link để client khám phá những cách sắp xếp được hỗ trợ và theo link tương ứng.

Spring Data cung cấp `Sort` và `Pageable` để nhận tiêu chí sắp xếp từ request. Khi tích hợp Spring HATEOAS, các resolver HATEOAS-aware đưa tiêu chí sort vào URI được tạo từ controller method. Với collection phân trang, `PagedResourcesAssembler` tạo link điều hướng và giữ trạng thái sort hiện tại. Bài học này trình bày cách tạo link cho sorting, kết hợp với phân trang và kiểm soát các tiêu chí được phép.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích cú pháp sort trong query parameter.
- Nhận `Sort` hoặc `Pageable` trong controller Spring MVC.
- Tạo link có query parameter sort bằng `WebMvcLinkBuilder`.
- Công bố các link cho lựa chọn sắp xếp phổ biến.
- Dùng `PagedResourcesAssembler` để tạo link phân trang giữ sort.
- Cấu hình sort mặc định bằng `@SortDefault` và `@PageableDefault`.
- Kiểm soát thuộc tính được phép sort và kiểm thử link trong HAL.

## Vì sao cần link cho sorting?

Một collection có thể có nhiều cách xem. Nếu client tự ghép query string, client phải biết trước tên tham số, cú pháp sort và các thuộc tính server chấp nhận. Khi server thay đổi mapping hoặc giới hạn lựa chọn, client tự xây URI có thể bị ảnh hưởng.

Hypermedia cho phép server công bố các link đại diện cho những cách xem collection. Client theo link để lấy representation tương ứng mà không phải tự đoán cấu trúc URI.

Ví dụ response HAL có thể công bố:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.test/orders?sort=createdAt,desc"
    },
    "newest": {
      "href": "https://api.example.test/orders?sort=createdAt,desc"
    },
    "lowestTotal": {
      "href": "https://api.example.test/orders?sort=total,asc"
    }
  }
}
```

`newest` và `lowestTotal` là relation do API định nghĩa để công bố các lựa chọn sắp xếp. Tên relation cần ổn định và được mô tả trong hợp đồng API. Client chỉ cần theo link tương ứng để nhận collection đã được sắp xếp.

## Cú pháp sort của Spring Data

Spring Data Web mặc định nhận tham số `sort` theo dạng:

```http
GET /orders?sort=createdAt,desc
```

Trong đó `createdAt` là thuộc tính dùng để sắp xếp và `desc` là chiều giảm dần. Nếu không chỉ định chiều, mặc định là tăng dần.

Có thể gửi nhiều tham số `sort` để sắp xếp theo nhiều thuộc tính:

```http
GET /orders?sort=status,asc&sort=createdAt,desc
```

Ví dụ trên sắp xếp theo `status` tăng dần trước, sau đó theo `createdAt` giảm dần cho các đơn hàng có cùng trạng thái.

Khi kết hợp phân trang, các tham số mặc định là:

| Tham số | Ý nghĩa | Mặc định |
|---|---|---|
| `page` | Số trang, bắt đầu từ 0 | `0` |
| `size` | Số phần tử mỗi trang | `20` |
| `sort` | Một hoặc nhiều tiêu chí sắp xếp | Không sort nếu không cấu hình mặc định |

Ví dụ:

```http
GET /orders?page=0&size=20&sort=createdAt,desc&sort=total,asc
```

Ứng dụng có thể đổi tên tham số, prefix, delimiter hoặc giới hạn kích thước trang thông qua cấu hình resolver. Vì vậy, client nên dùng link server công bố thay vì giả định các tên mặc định luôn tồn tại.

## Nhận Sort trong controller

Spring Data Web đăng ký `SortHandlerMethodArgumentResolver` để chuyển query parameter thành đối tượng `Sort`. Controller có thể nhận `Sort` trực tiếp:

```java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderRepository orders;

    OrderController(OrderRepository orders) {
        this.orders = orders;
    }

    @GetMapping
    List<Order> all(Sort sort) {
        return orders.findAll(sort);
    }
}
```

Giả sử `OrderRepository` là repository Spring Data hỗ trợ `findAll(Sort)`. Khi client gửi `GET /orders?sort=createdAt,desc`, Spring MVC chuyển query thành `Sort` và truyền vào controller.

Với Spring Data JPA, có thể kế thừa `JpaRepository` để nhận sẵn các phương thức tìm kiếm theo `Sort` và `Pageable`:

```java
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<Order, Long> {
}
```

Nếu endpoint chỉ cần sắp xếp mà không cần phân trang, nhận `Sort` trực tiếp là đủ. Nếu cần giới hạn số phần tử và điều hướng qua các trang, dùng `Pageable`.

## Tạo link sort bằng WebMvcLinkBuilder

Khi Spring Data Web được tích hợp với Spring HATEOAS, các resolver HATEOAS-aware có thể tham gia vào quá trình xây URI:

- `HateoasSortHandlerMethodArgumentResolver` mở rộng resolver sort và triển khai `UriComponentsContributor`.
- `HateoasPageableHandlerMethodArgumentResolver` mở rộng resolver phân trang và cũng triển khai `UriComponentsContributor`.

Khi `WebMvcLinkBuilder` tạo link tới controller method có tham số `Sort` hoặc `Pageable`, resolver có thể bổ sung query parameter tương ứng. Bạn không cần tự nối chuỗi query string.

Ví dụ controller công bố hai link sắp xếp phổ biến:

```java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderRepository orders;

    OrderController(OrderRepository orders) {
        this.orders = orders;
    }

    @GetMapping
    CollectionModel<Order> all(Sort sort) {
        List<Order> content = orders.findAll(sort);

        Link self = linkTo(methodOn(OrderController.class).all(sort))
            .withSelfRel();

        Link newest = linkTo(methodOn(OrderController.class).all(
                Sort.by(Sort.Order.desc("createdAt"))))
            .withRel("newest");

        Link lowestTotal = linkTo(methodOn(OrderController.class).all(
                Sort.by(Sort.Order.asc("total"))))
            .withRel("lowestTotal");

        return CollectionModel.of(content, self, newest, lowestTotal);
    }
}
```

Trong ví dụ:

1. `all(Sort sort)` cho phép Spring Data phân tích tham số sort từ request.
2. `methodOn(OrderController.class).all(sort)` tạo proxy invocation để Spring HATEOAS đọc mapping và tham số của handler method.
3. Resolver HATEOAS-aware tham gia tạo URI có query parameter sort.
4. Link `newest` và `lowestTotal` được tạo từ các đối tượng `Sort` cụ thể, nên trỏ tới hai cách xem collection khác nhau.

`methodOn()` không thực thi phương thức controller và không gọi repository. Nó ghi nhận lời gọi trên proxy để link builder phân tích mapping. Các tham số được resolver hỗ trợ như `Sort` hoặc `Pageable` có thể được dùng để bổ sung URI; không nên giả định mọi tham số method đều tự động trở thành query parameter.

Response HAL có thể chứa các link tương tự:

```json
{
  "_embedded": {
    "orders": [
      { "id": 42, "status": "NEW", "total": 1250000 }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test/orders?sort=createdAt,desc"
    },
    "newest": {
      "href": "https://api.example.test/orders?sort=createdAt,desc"
    },
    "lowestTotal": {
      "href": "https://api.example.test/orders?sort=total,asc"
    }
  }
}
```

Tên relation collection `orders` trong ví dụ phụ thuộc relation provider hoặc `@Relation` trên kiểu representation. URI minh họa được rút gọn để tập trung vào tham số sort.

## Link template cho sort

Khi muốn client tự chọn tiêu chí sort trong một tập giá trị được server hỗ trợ, API có thể công bố link dạng URI template:

```json
{
  "_links": {
    "sort": {
      "href": "https://api.example.test/orders{?sort}",
      "templated": true,
      "title": "Sort orders"
    }
  }
}
```

Client mở rộng biến `sort` với giá trị theo cú pháp API, ví dụ `createdAt,desc`. URI template cho biết tham số cần truyền và vị trí của nó.

`HateoasSortHandlerMethodArgumentResolver` có phương thức tạo template variables cho tham số sort. Khi dùng tích hợp HATEOAS-aware, link builder có thể tạo URI template dựa trên chữ ký controller method có tham số `Sort`. Đây là lựa chọn phù hợp khi muốn cho client chọn sort động.

Với một handler method nhận `Sort`, có thể tạo link template bằng cách truyền placeholder `null` cho tham số đó:

~~~java
Link sortTemplate = linkTo(methodOn(OrderController.class).all(null))
    .withRel("sort");
~~~

Ở đây `null` chỉ được dùng để chọn phương thức và yêu cầu resolver mô tả biến sort. Nó không phải giá trị sort mặc định và không thực thi handler method.

URI template chỉ mô tả biến và cấu trúc URI. Nó không tự công bố danh sách thuộc tính hợp lệ, chiều sort được hỗ trợ hay cách sắp xếp mặc định. Nếu API chỉ cho phép một số lựa chọn, hãy công bố các link cụ thể như `newest` và `lowestTotal`, hoặc mô tả tập lựa chọn trong profile/tài liệu API.

## Link sort kết hợp với phân trang

Trong nhiều API, sorting và pagination đi cùng nhau. Client chọn thứ tự sắp xếp rồi duyệt các trang của cùng một collection. Nếu link `next` làm mất tham số sort, trang tiếp theo có thể trả kết quả theo thứ tự mặc định và làm trải nghiệm client không nhất quán.

Spring Data cung cấp `Pageable` để mang đồng thời page, size và sort:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Order.desc("createdAt"))
);
```

Controller nhận `Pageable` và truyền cho repository:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping
Page<Order> all(
        @PageableDefault(
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        ) Pageable pageable) {
    return orders.findAll(pageable);
}
```

Client có thể thay đổi sort bằng query parameter:

```http
GET /orders?page=0&size=20&sort=total,asc
```

`Pageable` được tạo từ request sẽ chứa cả vị trí trang, kích thước và thứ tự sắp xếp. Khi chuyển sang trang tiếp theo, các giá trị này cần được giữ nhất quán.

## Tạo link phân trang giữ sort bằng PagedResourcesAssembler

Spring HATEOAS tích hợp với Spring Data qua `PagedResourcesAssembler`. Assembler chuyển `Page<T>` thành `PagedModel<EntityModel<T>>`, thêm metadata trang và link điều hướng như `prev` hoặc `next` tùy trạng thái trang.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderRepository orders;

    OrderController(OrderRepository orders) {
        this.orders = orders;
    }

    @GetMapping
    PagedModel<EntityModel<Order>> all(
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> page = orders.findAll(pageable);
        return pagedAssembler.toModel(page);
    }
}
```

`PagedResourcesAssembler.toModel(page)` thực hiện:

- Bọc từng phần tử trong `EntityModel`.
- Gắn metadata như kích thước trang, tổng số phần tử, tổng số trang và số trang hiện tại.
- Tạo link `prev` và `next` khi trang có trang trước hoặc trang sau.
- Dùng cấu hình của `PageableHandlerMethodArgumentResolver` để tạo tham số điều hướng tương thích với controller.

Vì `Pageable` chứa `Sort`, các link điều hướng được tạo theo cấu hình resolver và giữ tham số sort của request hiện tại. Ví dụ, nếu client gọi:

```http
GET /orders?page=0&size=20&sort=createdAt,desc&sort=total,asc
```

link `next` có thể trỏ tới:

```text
/orders?page=1&size=20&sort=createdAt,desc&sort=total,asc
```

Các giá trị thực tế tuân theo cấu hình resolver của ứng dụng, bao gồm tên tham số, prefix, delimiter và cách đánh số trang. Không nên tự tạo link `next` bằng cách chỉ tăng `page` rồi bỏ các tham số còn lại.

`PagedResourcesAssembler` tự tạo link phân trang, nhưng không tự quyết định mọi lựa chọn sort mà API nên công bố. Nếu muốn có các link preset như `newest` hoặc `lowestTotal`, hãy bổ sung chúng vào model theo hợp đồng của endpoint.

Khi response được serialize bằng HAL, các link và metadata của `PagedModel` được biểu diễn theo media type mà client yêu cầu, ví dụ `application/hal+json`.

## Cấu hình Spring Data Web và HATEOAS

Trong ứng dụng Spring Boot có Spring Data và Spring HATEOAS, auto-configuration thường đăng ký các thành phần tích hợp cần thiết. Với cấu hình Spring MVC tự quản lý, có thể bật Spring Data Web support:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@Configuration
@EnableSpringDataWebSupport
class DataWebConfiguration {
}
```

Khi Spring HATEOAS có trên classpath, `@EnableSpringDataWebSupport` đăng ký các thành phần HATEOAS-aware thay cho resolver cơ bản, bao gồm:

- `HateoasSortHandlerMethodArgumentResolver` để nhận và tạo URI có tham số sort.
- `HateoasPageableHandlerMethodArgumentResolver` để nhận và tạo URI có tham số phân trang.
- `PagedResourcesAssembler` để chuyển `Page` thành `PagedModel`.

Không cần tự tạo các resolver này nếu cấu hình Spring Data Web đã đăng ký chúng. Khi thay đổi tên tham số hoặc delimiter, hãy tùy chỉnh resolver bằng các extension point Spring Data cung cấp và kiểm thử lại các link được tạo.

## Giá trị sort mặc định

Không phải request nào cũng cần chỉ định sort. Có thể đặt thứ tự mặc định bằng `@SortDefault` cho tham số `Sort`:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.web.SortDefault;

@GetMapping
CollectionModel<Order> all(
        @SortDefault(
            sort = "createdAt",
            direction = Sort.Direction.DESC
        ) Sort sort) {
    // Truy vấn và tạo representation.
}
```

Nếu controller nhận `Pageable`, dùng `@PageableDefault`:

```java
@GetMapping
PagedModel<EntityModel<Order>> all(
        @PageableDefault(
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        ) Pageable pageable,
        PagedResourcesAssembler<Order> assembler) {
    return assembler.toModel(orders.findAll(pageable));
}
```

Giá trị mặc định được dùng khi client không gửi tham số tương ứng. Khi client gửi `sort` rõ ràng, resolver tạo `Sort` theo lựa chọn của client. Hãy công bố sort mặc định trong tài liệu API nếu nó ảnh hưởng đến cách client diễn giải kết quả.

## Cho phép sort an toàn

Không nên chuyển mọi chuỗi `sort` từ client thẳng vào truy vấn mà không kiểm tra. Spring Data mô tả `Sort.Order` bằng tên property; resolver không tự xác minh tên đó có nằm trong danh sách thuộc tính API cho phép hay không. Ứng dụng cần kiểm tra để tránh lộ trường nội bộ hoặc cho phép truy vấn sort quá tốn kém.

Ví dụ allow-list:

```java
import java.util.Set;
import org.springframework.data.domain.Sort;

class OrderSortPolicy {

    private static final Set<String> ALLOWED_PROPERTIES =
        Set.of("createdAt", "total", "status");

    Sort validate(Sort requested) {
        for (Sort.Order order : requested) {
            if (!ALLOWED_PROPERTIES.contains(order.getProperty())) {
                throw new IllegalArgumentException(
                    "Unsupported sort property: " + order.getProperty()
                );
            }
        }
        return requested;
    }
}
```

Trong ứng dụng thực tế, chuyển lỗi này thành response HTTP phù hợp, chẳng hạn `400 Bad Request`, bằng exception handler. Có thể dùng enum hoặc mapping từ tên public của API sang property truy vấn nội bộ nếu không muốn công bố tên entity.

Khi dùng pagination theo offset, nên có tiêu chí sort ổn định. Nếu nhiều bản ghi có cùng `createdAt`, hãy thêm một khóa phụ duy nhất như `id`:

```java
Sort stableSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("id")
);
```

Sort ổn định giúp giảm việc bản ghi đổi vị trí giữa các trang khi có giá trị sort trùng nhau. Với dữ liệu thay đổi liên tục, offset pagination vẫn có thể dịch chuyển kết quả giữa các request; cân nhắc cursor/keyset pagination nếu yêu cầu nhất quán cao.

## Kiểm thử link sort bằng MockMvc

Kiểm thử cần xác nhận link được tạo có relation đúng và URI chứa tham số sort mong muốn. Ví dụ dưới đây kiểm tra hai link preset:

```java
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.domain.Sort;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderSortingLinksTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderRepository orders;

    @Test
    void exposesLinksForSupportedSortOrders() throws Exception {
        given(orders.findAll(org.mockito.ArgumentMatchers.any(Sort.class)))
            .willReturn(List.of());

        mockMvc.perform(get("/orders"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.newest.href").exists())
            .andExpect(jsonPath("$._links.lowestTotal.href").exists())
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
```

Đây là khung test cho controller dùng `Sort` và trả `CollectionModel` như ví dụ trước. Trong test thực tế, khai báo mock và kiểu model theo repository/controller của dự án. Có thể kiểm tra thêm giá trị href sau khi parse URI để xác nhận tham số `sort` và chiều sort, tránh phụ thuộc cách dấu phẩy được percent-encode.

Với endpoint phân trang, kiểm thử request có nhiều tiêu chí sort và xác nhận link `next` vẫn chứa tất cả tiêu chí đó:

```java
mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "20")
        .param("sort", "createdAt,desc")
        .param("sort", "total,asc"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.next.href").exists());
```

Sau khi lấy href của `next`, phân tích query string để xác nhận `page` tăng lên, `size` được giữ và các giá trị `sort` không bị mất. Cũng nên kiểm thử trang đầu không có `prev`, trang cuối không có `next`, và request sort không hợp lệ bị từ chối.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tự nối chuỗi `?sort=...` vào URI controller | Link dễ sai khi mapping hoặc tên tham số thay đổi | Dùng `WebMvcLinkBuilder` và resolver HATEOAS-aware |
| Dùng resolver sort cơ bản khi tạo link hypermedia | Link builder có thể thiếu template variable hoặc không xử lý sort như mong muốn | Bật Spring Data Web support với Spring HATEOAS |
| Tạo link `next` chỉ giữ `page` | Trang tiếp theo mất sort và filter hiện tại | Dùng `PagedResourcesAssembler` hoặc giữ đầy đủ query state |
| Nghĩ `PagedResourcesAssembler` tự công bố mọi lựa chọn sort | Client không biết các preset sort của API | Thêm link riêng cho các lựa chọn sort được hỗ trợ |
| Cho phép mọi property client gửi vào `sort` | Có thể lộ thuộc tính nội bộ hoặc tạo truy vấn tốn kém | Kiểm tra property theo allow-list |
| Chỉ sort theo thuộc tính có giá trị trùng | Kết quả giữa các trang có thể không ổn định | Thêm khóa phụ duy nhất làm tie-breaker |
| Đổi tên query parameter nhưng không cập nhật link | Client theo link gửi sai tham số | Tùy chỉnh resolver tập trung và kiểm thử href |
| Không tài liệu hóa relation sort tùy chỉnh | Client không hiểu link biểu diễn thứ tự nào | Dùng relation ổn định, có mô tả rõ ràng |

## Ghi nhớ

Link cho sorting cho phép client khám phá các cách xem collection mà server hỗ trợ. Spring Data nhận tiêu chí qua `Sort` hoặc `Pageable`, với tham số mặc định như `sort=createdAt,desc` và có thể nhận nhiều tham số `sort` để sắp xếp theo nhiều thuộc tính. Khi tích hợp Spring HATEOAS, `HateoasSortHandlerMethodArgumentResolver` và `HateoasPageableHandlerMethodArgumentResolver` giúp link builder đưa các tham số đó vào URI. `PagedResourcesAssembler` tạo link phân trang và giữ sort hiện tại; các link preset như `newest` hoặc `lowestTotal` vẫn cần được API công bố riêng. Luôn giới hạn thuộc tính sort được phép và dùng thứ tự ổn định khi phân trang.

## Tài liệu tham khảo

- [Spring Data Commons – Web support for Pageable and Sort](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions-web.html)
- [HateoasSortHandlerMethodArgumentResolver API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/web/HateoasSortHandlerMethodArgumentResolver.html)
- [HateoasPageableHandlerMethodArgumentResolver API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/web/HateoasPageableHandlerMethodArgumentResolver.html)
- [PagedResourcesAssembler API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html)
- [Spring Data JPA – Hypermedia support for Page and Slice](https://docs.spring.io/spring-data/jpa/reference/repositories/core-extensions.html)
- [Spring HATEOAS – Building links in Spring MVC](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.mvc.links)
