# Tham số page

## Mục tiêu

Sau bài này, bạn có thể đọc và thiết kế tham số phân trang trong REST API dùng Spring Data và Spring HATEOAS, hiểu ý nghĩa của `page`, `size` và `sort`, ánh xạ chúng thành `Pageable`, tạo response phân trang bằng `PagedResourcesAssembler` và kiểm thử metadata cùng các link điều hướng trong HAL.

## 1. Tham số page dùng để làm gì?

Một collection có thể chứa hàng nghìn hoặc hàng triệu tài nguyên. Trả toàn bộ dữ liệu trong một response làm tăng thời gian truy vấn, kích thước payload và bộ nhớ mà server/client cần sử dụng. Phân trang chia collection thành các phần nhỏ, mỗi request chỉ lấy một trang.

Trong Spring Data Web, tham số truy vấn thường dùng là:

- `page`: số thứ tự trang mà client muốn lấy.
- `size`: số phần tử tối đa trong một trang.
- `sort`: thuộc tính và hướng sắp xếp trước khi cắt trang.

Ví dụ:

```http
GET /orders?page=0&size=20&sort=createdAt,desc
Accept: application/hal+json
```

Request yêu cầu trang đầu tiên, tối đa 20 đơn hàng, sắp xếp theo `createdAt` giảm dần.

Mặc định Spring Data sử dụng chỉ số trang bắt đầu từ 0:

| Giá trị | Ý nghĩa |
|---|---|
| `page=0` | Trang đầu tiên |
| `page=1` | Trang thứ hai |
| `page=2` | Trang thứ ba |
| `size=20` | Tối đa 20 phần tử trong mỗi trang |
| `sort=createdAt,desc` | Sắp xếp theo thời điểm tạo, mới nhất trước |

Chỉ số `page` là vị trí của trang, không phải số thứ tự của bản ghi. Với `page=2` và `size=20`, offset logic là 40: truy vấn bắt đầu từ phần tử thứ 41 trong thứ tự đã sắp xếp.

## 2. Spring chuyển page thành Pageable như thế nào?

Spring Data Web có cơ chế phân giải tham số request thành đối tượng `Pageable`. Khi controller khai báo tham số kiểu này, Spring tự đọc các query parameter và tạo thông tin phân trang:

```java
@GetMapping("/orders")
public Page<Order> getOrders(Pageable pageable) {
    return orderRepository.findAll(pageable);
}
```

Với request:

```http
GET /orders?page=2&size=20&sort=createdAt,desc
```

Spring tạo một `Pageable` tương đương với:

```java
PageRequest.of(
        2,
        20,
        Sort.by(Sort.Direction.DESC, "createdAt")
);
```

Đối tượng `Pageable` chứa:

- `getPageNumber()`: chỉ số trang nội bộ, mặc định bắt đầu từ 0.
- `getPageSize()`: số phần tử yêu cầu trong một trang.
- `getOffset()`: vị trí bắt đầu trong collection đã sắp xếp.
- `getSort()`: thông tin sắp xếp.

Nên nhận `Pageable` ở controller thay vì tự đọc `page` và `size` bằng nhiều `@RequestParam`. Cơ chế của Spring Data xử lý việc phân tích tham số, giá trị mặc định và giới hạn cấu hình một cách nhất quán.

## 3. Đặt giá trị mặc định bằng @PageableDefault

Nếu client không truyền `page` hoặc `size`, ứng dụng cần một giá trị mặc định. Có thể dùng `@PageableDefault` để định nghĩa chính sách cho từng endpoint:

```java
@GetMapping("/orders")
public Page<Order> getOrders(
        @PageableDefault(
            page = 0,
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        ) Pageable pageable) {

    return orderRepository.findAll(pageable);
}
```

Với cấu hình này:

- Không truyền `page` thì lấy trang 0.
- Không truyền `size` thì lấy tối đa 20 phần tử.
- Không truyền `sort` thì sắp xếp theo `createdAt` giảm dần.
- Client vẫn có thể truyền các tham số hợp lệ để yêu cầu trang hoặc cách sắp xếp khác.

Có thể dùng `@PageableDefault(size = 20)` nếu chỉ cần thay kích thước mặc định. Với chính sách sắp xếp mặc định phức tạp hơn, có thể dùng thêm `@SortDefault` hoặc `@SortDefaults`.

Không nên xem giá trị mặc định là giới hạn tối đa. `@PageableDefault(size = 20)` chỉ xác định kích thước khi client không gửi `size`; client vẫn có thể yêu cầu một kích thước lớn hơn nếu server không cấu hình giới hạn.

## 4. Cấu hình page và size ở cấp ứng dụng

Spring Boot cho phép cấu hình tham số phân trang dùng chung trong `application.yml`:

```yaml
spring:
  data:
    web:
      pageable:
        default-page-size: 20
        max-page-size: 100
        page-parameter: page
        size-parameter: size
        one-indexed-parameters: false
```

Ý nghĩa:

| Thuộc tính | Tác dụng |
|---|---|
| `default-page-size` | Kích thước mặc định khi request không có `size` |
| `max-page-size` | Giới hạn kích thước trang tối đa server chấp nhận |
| `page-parameter` | Tên query parameter mang số trang |
| `size-parameter` | Tên query parameter mang kích thước trang |
| `one-indexed-parameters` | Có xem số trang bên ngoài bắt đầu từ 1 hay không |

Với cấu hình trên, client yêu cầu `size=500` vẫn bị giới hạn ở tối đa 100 phần tử. Giới hạn này giúp tránh một request duy nhất yêu cầu quá nhiều dữ liệu.

Nếu muốn đổi tên tham số, ví dụ `pageNumber` và `pageSize`, có thể cấu hình:

```yaml
spring:
  data:
    web:
      pageable:
        page-parameter: pageNumber
        size-parameter: pageSize
```

Khi đổi tên, phải cập nhật tài liệu API và bảo đảm link phân trang được tạo bởi Spring HATEOAS sử dụng cùng cấu hình resolver. Không nên tự ghép URL theo tên tham số cũ trong assembler.

## 5. Chỉ số trang bắt đầu từ 0 hay 1?

Mặc định Spring Data dùng zero-based indexing. Điều này có nghĩa trang đầu tiên là `page=0`. Quy ước này khớp với `PageRequest.of(0, size)` và cách đánh số nội bộ của `Pageable`.

Một số API hoặc giao diện người dùng muốn trang đầu tiên là `page=1`. Có thể bật:

```yaml
spring:
  data:
    web:
      pageable:
        one-indexed-parameters: true
```

Khi bật cấu hình này, resolver chuyển số trang request bắt đầu từ 1 sang chỉ số nội bộ bắt đầu từ 0. Ví dụ:

| Query parameter | Chỉ số nội bộ |
|---|---:|
| `page=1` | 0 |
| `page=2` | 1 |
| `page=3` | 2 |

Đây là thay đổi ở ranh giới HTTP. Trong code, `Pageable.getPageNumber()` và `PageRequest` vẫn sử dụng chỉ số bắt đầu từ 0.

Không nên trộn hai quy ước trong cùng một API. Nếu chuyển từ zero-based sang one-based, hãy kiểm thử các link `first`, `prev`, `self`, `next` và `last` được tạo ra để client không bị điều hướng sai trang.

## 6. Dùng Pageable với Spring Data repository

Các repository của Spring Data hỗ trợ truy vấn theo `Pageable`. Ví dụ với `JpaRepository`:

```java
public interface OrderRepository
        extends JpaRepository<Order, UUID> {
}
```

Service nhận `Pageable` và trả về `Page<Order>`:

```java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Page<Order> findOrders(Pageable pageable) {
        return repository.findAll(pageable);
    }
}
```

Controller nhận request và chuyển kết quả cho Spring HATEOAS:

```java
@GetMapping(value = "/orders", produces = MediaTypes.HAL_JSON_VALUE)
public PagedModel<EntityModel<Order>> getOrders(
        @PageableDefault(size = 20, sort = "createdAt",
                direction = Sort.Direction.DESC) Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.findOrders(pageable);

    return pagedAssembler.toModel(page, orderModelAssembler);
}
```

Trong ví dụ, `orderModelAssembler` triển khai `RepresentationModelAssembler<Order, EntityModel<Order>>`. `PagedResourcesAssembler` gọi assembler cho từng phần tử, sau đó tạo `PagedModel` gồm nội dung, metadata trang và các link điều hướng.

Các import thường dùng:

```java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
```

Spring Boot với Spring Data Web và Spring HATEOAS starter thường tự cấu hình resolver cùng các thành phần cần thiết. Nếu cấu hình Spring thủ công, cần đăng ký hạ tầng Spring Data Web và Spring HATEOAS phù hợp để tham số `Pageable` và `PagedResourcesAssembler` hoạt động.

## 7. PagedModel chứa metadata gì?

Khi `PagedResourcesAssembler` chuyển một `Page<T>` thành `PagedModel<D>`, response HAL chứa danh sách item, metadata phân trang và các link điều hướng.

Ví dụ response:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "order-41",
        "status": "PAID",
        "_links": {
          "self": {
            "href": "/orders/order-41"
          }
        }
      },
      {
        "id": "order-42",
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "/orders/order-42"
          }
        }
      }
    ]
  },
  "_links": {
    "first": {
      "href": "/orders?page=0&size=20"
    },
    "prev": {
      "href": "/orders?page=0&size=20"
    },
    "self": {
      "href": "/orders?page=1&size=20"
    },
    "next": {
      "href": "/orders?page=2&size=20"
    },
    "last": {
      "href": "/orders?page=4&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 95,
    "totalPages": 5,
    "number": 1
  }
}
```

Ý nghĩa của metadata:

- `size`: kích thước trang hiện tại.
- `totalElements`: tổng số phần tử phù hợp với truy vấn.
- `totalPages`: tổng số trang.
- `number`: chỉ số trang hiện tại, theo quy ước nội bộ bắt đầu từ 0.

Các link có vai trò:

| Relation | Ý nghĩa |
|---|---|
| `first` | Trang đầu tiên |
| `prev` | Trang trước, nếu có |
| `self` | Trang hiện tại |
| `next` | Trang tiếp theo, nếu có |
| `last` | Trang cuối cùng |

Các link điều hướng được tạo từ request hiện tại và resolver phân trang. Những tham số như `size` và `sort` có thể được giữ lại khi chuyển trang để client tiếp tục xem cùng tập kết quả theo cùng thứ tự.

Ví dụ JSON trên minh họa một trang giữa. Ở trang đầu, link `prev` không cần xuất hiện; ở trang cuối, link `next` không cần xuất hiện. Client nên kiểm tra relation hiện có thay vì tự tính URL hoặc giả định mọi link luôn được trả về.

## 8. Giữ bộ lọc và sort khi chuyển trang

Một collection thực tế thường có bộ lọc tìm kiếm. Ví dụ:

```http
GET /orders?status=PENDING&page=0&size=10&sort=createdAt,desc
```

Khi client theo link `next`, request cần giữ `status=PENDING`, `size=10` và `sort=createdAt,desc`. Nếu mất bộ lọc, trang tiếp theo có thể chứa dữ liệu thuộc tập kết quả khác.

`PagedResourcesAssembler` sử dụng request hiện tại và cấu hình pageable resolver để tạo các link phân trang phù hợp. Nếu endpoint nhận thêm query parameter tìm kiếm, cần bảo đảm cách tạo link giữ được các tham số đó. Kiểm thử href trong response thay vì chỉ kiểm tra rằng relation `next` tồn tại.

Sort cũng cần ổn định. Nếu client chỉ sắp xếp theo một thuộc tính có giá trị trùng nhau, thứ tự giữa các bản ghi bằng nhau có thể thay đổi giữa các request. Có thể thêm khóa duy nhất làm tiêu chí phụ, ví dụ:

```text
sort=createdAt,desc&sort=id,asc
```

Thứ tự ổn định giúp giảm khả năng một item bị lặp hoặc bị bỏ qua khi dữ liệu thay đổi trong lúc client đang duyệt nhiều trang. Với dữ liệu biến động liên tục, offset pagination vẫn có thể dịch chuyển giữa các request; khi cần bảo đảm duyệt ổn định hơn ở tập dữ liệu lớn, hãy cân nhắc cursor/keyset pagination.

## 9. Page khác Slice như thế nào?

Spring Data có hai kiểu kết quả thường dùng:

| Kiểu | Thông tin có sẵn | Chi phí thường gặp |
|---|---|---|
| `Page<T>` | Nội dung, số trang, tổng phần tử và tổng số trang | Có thể cần truy vấn đếm tổng số phần tử |
| `Slice<T>` | Nội dung và thông tin còn trang tiếp theo hay không | Thường không cần biết tổng số phần tử |

`PagedResourcesAssembler` nhận `Page<T>` để tạo `PagedModel` có đầy đủ metadata tổng số trang. Nếu endpoint chỉ cần biết còn dữ liệu tiếp theo hay không, `Slice<T>` có thể phù hợp hơn, nhưng ứng dụng cần tự thiết kế representation và link điều hướng theo semantics đó.

Không nên dùng `Page<T>` chỉ để hiển thị một nút “xem thêm” nếu việc đếm tổng số bản ghi quá tốn kém và client không cần biết tổng số trang. Ngược lại, nếu giao diện cần số trang cuối hoặc tổng số kết quả, `Page<T>` cung cấp metadata cần thiết.

## 10. Giới hạn và xác thực tham số

Tham số phân trang đến từ client nên cần được giới hạn:

- Đặt `max-page-size` để ngăn request yêu cầu kích thước quá lớn.
- Chọn default size hợp lý cho endpoint.
- Chỉ cho phép sort theo các thuộc tính mà API công bố.
- Kiểm tra các query filter riêng để tránh truy vấn tốn kém.
- Xác định rõ cách xử lý page âm, size bằng 0 hoặc tham số không hợp lệ theo cấu hình và phiên bản Spring Data đang dùng.

Không nên nối trực tiếp giá trị `sort` vào SQL hoặc JPQL. Dùng `Sort` và repository abstraction của Spring Data, đồng thời whitelist các trường sort được phép nếu API không muốn công bố mọi thuộc tính persistence.

Ví dụ cấu hình giới hạn:

```yaml
spring:
  data:
    web:
      pageable:
        default-page-size: 20
        max-page-size: 100
```

Nếu endpoint có yêu cầu đặc biệt, có thể kiểm tra `Pageable` trong service hoặc controller và trả lỗi validation theo hợp đồng API. Hãy thống nhất lỗi cho page/size vượt ngưỡng để client có thể xử lý dự đoán được.

## 11. Kiểm thử tham số page bằng MockMvc

Kiểm thử HTTP xác nhận query parameter được ánh xạ thành đúng trang và response có metadata tương ứng. Ví dụ, với endpoint `GET /orders`:

```java
mockMvc.perform(get("/orders")
        .param("page", "1")
        .param("size", "10")
        .param("sort", "createdAt,desc")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.page.number").value(1))
    .andExpect(jsonPath("$.page.size").value(10))
    .andExpect(jsonPath("$._links.self.href")
            .value(containsString("page=1")))
    .andExpect(jsonPath("$._links.self.href")
            .value(containsString("size=10")))
    .andExpect(jsonPath("$._links.next.href").exists());
```

Test này giả định dữ liệu có ít nhất một trang tiếp theo và ứng dụng đang dùng zero-based parameters. Có thể kiểm tra thêm request không truyền tham số:

```java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$.page.size").value(20));
```

Nếu cấu hình `@PageableDefault` hoặc `default-page-size` khác, hãy cập nhật giá trị kỳ vọng theo chính sách endpoint.

Kiểm thử giới hạn kích thước:

```java
mockMvc.perform(get("/orders")
        .param("size", "500")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.size").value(100));
```

Test này giả định `max-page-size: 100`. Ngoài ra, nên kiểm tra:

1. Trang đầu không công bố `prev` nếu không có trang trước.
2. Trang cuối không công bố `next`.
3. Link `next` tăng page đúng một đơn vị.
4. Các link giữ nguyên size, sort và bộ lọc.
5. Sort nhiều thuộc tính được phản ánh trong request kế tiếp.
6. Khi bật one-indexed parameters, query link bắt đầu từ 1 nhưng metadata nội bộ vẫn phản ánh chỉ số trang của Spring Data.

## 12. Những lỗi thường gặp

**Hiểu page bắt đầu từ 1 theo mặc định.** Spring Data mặc định dùng chỉ số 0. Nếu API muốn bắt đầu từ 1, cấu hình rõ và kiểm thử resolver cùng các link.

**Tự ghép URL next/prev.** Việc tự cộng page có thể làm mất size, sort hoặc filter. Dùng link do `PagedResourcesAssembler` tạo.

**Nhầm default size với max size.** `@PageableDefault(size = 20)` không giới hạn client ở 20 phần tử. Dùng `max-page-size` để giới hạn request.

**Dùng Page khi không cần tổng số phần tử.** `Page<T>` có thể yêu cầu truy vấn count. Cân nhắc `Slice<T>` hoặc cursor pagination nếu chỉ cần biết còn dữ liệu.

**Sort không ổn định.** Sắp xếp theo trường trùng giá trị có thể khiến kết quả giữa các trang thay đổi. Thêm khóa duy nhất làm tiêu chí phụ.

**Không giữ query filter trong link.** Client theo next có thể rời khỏi tập kết quả ban đầu. Kiểm tra link điều hướng với filter và sort thực tế.

**Chỉ kiểm thử service.** Service có thể nhận đúng `Pageable`, nhưng controller hoặc assembler vẫn có thể tạo link sai. Kiểm tra response HAL qua MockMvc.

## 13. Nguyên tắc thiết kế

- Dùng `Pageable` để Spring Data phân giải `page`, `size` và `sort`.
- Dùng `@PageableDefault` cho giá trị mặc định theo endpoint.
- Cấu hình `max-page-size` ở server để giới hạn tài nguyên.
- Thống nhất quy ước zero-based hoặc one-based trên toàn API.
- Dùng `PagedResourcesAssembler` để tạo `PagedModel` và link điều hướng.
- Giữ filter và sort khi client chuyển trang.
- Chọn `Page<T>` khi cần tổng số trang; cân nhắc `Slice<T>` khi chỉ cần biết còn dữ liệu.
- Kiểm thử metadata, href và các biên trang đầu/cuối như một phần hợp đồng hypermedia.

## Kết luận

Tham số `page` xác định trang client muốn lấy; `size` giới hạn số phần tử trong trang và `sort` xác định thứ tự trước khi phân trang. Spring Data ánh xạ các tham số này thành `Pageable`, còn `PagedResourcesAssembler` chuyển `Page<T>` thành `PagedModel` với metadata và các link `first`, `prev`, `self`, `next`, `last`. Hãy thống nhất chỉ số trang, đặt giới hạn kích thước, giữ bộ lọc khi điều hướng và kiểm thử response HAL để client duyệt collection đúng cách.

## Tài liệu tham khảo

- [Spring Data Commons Reference – Web support and Pageable](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)
- [Spring HATEOAS Reference – Pagination](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.paged-resources)
- [Spring Boot Reference – Spring Data Web properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html#appendix.application-properties.data)

