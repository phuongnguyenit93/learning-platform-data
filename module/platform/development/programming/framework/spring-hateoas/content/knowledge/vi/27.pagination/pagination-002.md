# Pageable parameter

`Pageable` là abstraction của Spring Data mô tả yêu cầu phân trang và sắp xếp: trang cần lấy, số phần tử trên mỗi trang và thứ tự sắp xếp. Trong Spring HATEOAS, controller có thể nhận `Pageable` từ query parameter, dùng nó để truy vấn dữ liệu, rồi chuyển `Page<T>` thành `PagedModel` có metadata và các link điều hướng.

Client thường gửi các tham số `page`, `size` và `sort`. Ví dụ `GET /orders?page=0&size=20&sort=createdAt,desc` yêu cầu trang đầu tiên, tối đa 20 đơn hàng, sắp xếp theo thời gian tạo giảm dần. Spring Data Web tự chuyển các query parameter này thành đối tượng `Pageable` khi hỗ trợ web được cấu hình. Spring HATEOAS dùng kết quả phân trang để tạo các link như `first`, `prev`, `self`, `next` và `last`.

## 1. Pageable là gì?

`Pageable` thuộc Spring Data và biểu diễn yêu cầu lấy một phần dữ liệu. Nó cung cấp thông tin như:

- `getPageNumber()`: số thứ tự trang, mặc định đánh số từ 0.
- `getPageSize()`: số phần tử tối đa trên một trang.
- `getOffset()`: vị trí bắt đầu trong tập kết quả.
- `getSort()`: điều kiện sắp xếp.
- `next()`, `previousOrFirst()` và các phương thức liên quan: tạo yêu cầu trang kế tiếp hoặc trang trước.

Ví dụ:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.DESC, "createdAt"));
```

Đối tượng này yêu cầu trang đầu tiên, kích thước 20 và sắp xếp theo thuộc tính `createdAt` giảm dần. `PageRequest` là một implementation phổ biến của `Pageable`; trong controller, thông thường không cần tự tạo nó vì Spring Data Web có thể phân tích request để cung cấp tham số `Pageable`.

## 2. Các query parameter cơ bản

Spring Data Web mặc định sử dụng các tham số phổ biến sau:

| Tham số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `page` | Chỉ số trang, bắt đầu từ 0 theo mặc định | `page=0` |
| `size` | Số phần tử tối đa trên một trang | `size=20` |
| `sort` | Thuộc tính và hướng sắp xếp | `sort=createdAt,desc` |

Request đầy đủ:

```http
GET /orders?page=0&size=20&sort=createdAt,desc HTTP/1.1
Host: api.example.test
Accept: application/hal+json
```

`page=0` là trang đầu tiên, không phải trang số 1. Với kích thước 20, trang đầu tiên lấy các phần tử ở vị trí 0 đến 19; trang thứ hai bắt đầu từ vị trí 20. Về mặt khái niệm, offset được tính bằng `page × size`.

Nếu client bỏ qua các tham số, Spring Data dùng giá trị fallback được cấu hình trong ứng dụng hoặc giá trị mặc định của resolver. Không nên để client phụ thuộc vào một giá trị mặc định ngầm; API nên công bố rõ kích thước trang mặc định và giới hạn tối đa.

## 3. Tham số sort

`sort` mô tả thuộc tính dùng để sắp xếp và hướng sắp xếp. Cú pháp thường dùng là:

```text
sort=property,direction
```

Trong đó `direction` thường là `asc` hoặc `desc`. Ví dụ:

```http
GET /orders?sort=createdAt,desc HTTP/1.1
```

Có thể gửi nhiều tham số `sort` để tạo thứ tự sắp xếp nhiều cấp:

```http
GET /orders?page=0&size=20&sort=status,asc&sort=createdAt,desc HTTP/1.1
```

Kết quả được sắp xếp theo `status` tăng dần; nếu nhiều đơn hàng có cùng trạng thái, chúng được sắp xếp tiếp theo `createdAt` giảm dần. Nên thêm một thuộc tính ổn định, duy nhất làm tiêu chí cuối khi cần thứ tự nhất quán giữa các trang, ví dụ `id`.

Tên thuộc tính trong `sort` phải tương ứng với thuộc tính mà tầng truy vấn hiểu, thường là property của domain model hoặc projection. Không nên mặc định tên cột vật lý trong database là tên mà API phải công bố.

## 4. Nhận Pageable trong controller

Khi Spring Data Web được bật, `PageableHandlerMethodArgumentResolver` phân tích request parameter và cung cấp `Pageable` cho controller. Với Spring Boot và Spring Data, phần hỗ trợ này thường được cấu hình tự động khi các dependency phù hợp có mặt.

Ví dụ controller nhận `Pageable`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.domain.Sort;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderRepository orderRepository;

    OrderController(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @GetMapping
    Page<Order> all(
            @PageableDefault(
                    size = 20,
                    sort = "createdAt",
                    direction = Sort.Direction.DESC) Pageable pageable) {
        return orderRepository.findAll(pageable);
    }
}
```

`@PageableDefault` khai báo giá trị mặc định cho tham số này khi client không cung cấp tương ứng. Ví dụ chọn kích thước 20 và sắp xếp mới nhất trước. Nếu client gửi `size=5`, resolver dùng kích thước được yêu cầu trong giới hạn cấu hình.

Trong ví dụ này repository cần hỗ trợ phương thức `findAll(Pageable)`, thường có sẵn khi dùng Spring Data repository thích hợp. Controller có thể trả `Page<Order>` để minh họa việc truy vấn; phần tiếp theo sẽ chuyển kết quả sang `PagedModel` để công bố theo Spring HATEOAS.

## 5. Cấu hình mặc định bằng annotation

`@PageableDefault` cho phép đặt các giá trị như `page`, `size`, `sort` và `direction`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping
Page<Order> all(
        @PageableDefault(
                page = 0,
                size = 25,
                sort = "createdAt",
                direction = Sort.Direction.DESC) Pageable pageable) {
    return orderRepository.findAll(pageable);
}
```

Các thuộc tính trên chỉ định fallback của tham số controller. Chúng không buộc client luôn dùng trang hoặc kích thước đó; query parameter hợp lệ do client gửi có thể ghi đè mặc định, trong giới hạn resolver.

Nếu cần mặc định nhiều tiêu chí sắp xếp, có thể dùng `@SortDefault`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.SortDefault;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping
Page<Order> all(
        @SortDefault.SortDefaults({
                @SortDefault(sort = "createdAt", direction = Sort.Direction.DESC),
                @SortDefault(sort = "id", direction = Sort.Direction.ASC)
        }) Pageable pageable) {
    return orderRepository.findAll(pageable);
}
```

Các mặc định được dùng khi request không chỉ định thứ tự sắp xếp. Nếu client cung cấp `sort`, resolver sẽ dùng yêu cầu đó theo quy tắc của Spring Data Web.

## 6. Giới hạn page size và bảo vệ tài nguyên

Không nên cho phép client yêu cầu kích thước trang tùy ý. Một request như `size=1000000` có thể khiến truy vấn, bộ nhớ và serialize response tiêu tốn tài nguyên lớn. Hãy cấu hình page size mặc định và giới hạn tối đa.

Với Spring Boot, có thể cấu hình trong `application.yml`:

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
      sort:
        sort-parameter: sort
```

Các thuộc tính này điều chỉnh resolver web của Spring Data trong ứng dụng Spring Boot. `max-page-size` giới hạn kích thước client có thể yêu cầu; `default-page-size` được dùng khi không có `size`; `one-indexed-parameters` quyết định cách diễn giải tham số `page` bên ngoài. Kiểm tra tên property theo phiên bản Spring Boot đang dùng khi nâng cấp.

Ngoài giới hạn kích thước, nên giới hạn các thuộc tính được phép sort. Không nên cho client sắp xếp theo mọi property nội bộ, đặc biệt các trường không công bố hoặc thuộc tính gây truy vấn tốn kém. Có thể ánh xạ tên sort công khai sang property được phép trong service hoặc kiểm tra `Sort` trước khi gọi repository.

## 7. Chỉ số trang: zero-based và one-based

`Pageable` bên trong Spring Data sử dụng chỉ số trang zero-based: trang đầu là `0`, trang tiếp theo là `1`. Một số API muốn giao diện query thân thiện hơn và dùng trang đầu là `1`.

Có thể cấu hình resolver để nhận tham số một-based:

```yaml
spring:
  data:
    web:
      pageable:
        one-indexed-parameters: true
```

Khi bật cấu hình này, client gửi `page=1` để yêu cầu trang đầu. Spring Data chuyển đổi giá trị request sang chỉ số nội bộ phù hợp. Cần kiểm thử cả request và link phân trang được sinh ra để bảo đảm API công bố nhất quán một quy ước.

Không nên tự trừ hoặc cộng 1 trong controller nếu resolver đã được cấu hình xử lý việc này. Việc chuyển đổi hai lần sẽ khiến client nhận sai trang.

## 8. Pageable, Page, Slice và List

`Pageable` là yêu cầu đầu vào; kiểu kết quả truy vấn quyết định metadata mà ứng dụng có thể công bố:

| Kiểu kết quả | Nội dung | Khi nào dùng |
| --- | --- | --- |
| `Page<T>` | Nội dung trang, số phần tử, tổng số phần tử và tổng số trang | Khi client cần biết tổng số kết quả hoặc số trang |
| `Slice<T>` | Nội dung trang và thông tin còn trang tiếp theo hay không | Khi chỉ cần điều hướng tiếp, không cần tổng số trang |
| `List<T>` | Danh sách phần tử của trang, không có metadata phân trang đầy đủ | Khi tầng ứng dụng chỉ cần nội dung và tự quản lý metadata |

`Page<T>` thường cần truy vấn đếm tổng số phần tử để tính metadata. Với tập dữ liệu lớn hoặc truy vấn phức tạp, chi phí count có thể đáng kể. Nếu giao diện chỉ cần nút “Xem thêm”, `Slice<T>` có thể phù hợp hơn.

Spring HATEOAS `PagedModel` thường được tạo từ `Page<T>` thông qua `PagedResourcesAssembler`. Nếu dùng `Slice<T>` hoặc pagination kiểu cursor, cần thiết kế metadata và link điều hướng phù hợp với cơ chế đó; không nên giả định luôn có `last` hoặc tổng số trang.

## 9. Chuyển Page thành PagedModel

Trong API hypermedia, nên công bố trang dữ liệu bằng `PagedModel` để response có metadata phân trang và link điều hướng. `PagedResourcesAssembler<T>` của Spring Data Web tích hợp với Spring HATEOAS và chuyển `Page<T>` thành `PagedModel`.

Assembler cho một đơn hàng:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        return EntityModel.of(
                OrderRepresentation.from(order),
                linkTo(methodOn(OrderController.class)
                        .one(order.getId())).withSelfRel());
    }
}
```

Controller sử dụng `PagedResourcesAssembler`:

```java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping
PagedModel<EntityModel<OrderRepresentation>> all(Pageable pageable) {
    Page<Order> page = orderRepository.findAll(pageable);
    return pagedResourcesAssembler.toModel(page, orderModelAssembler);
}
```

Trong ví dụ, controller cần inject `PagedResourcesAssembler<Order>`, `OrderRepository` và `OrderModelAssembler` qua constructor. `toModel(...)` chuyển từng phần tử trong `Page<Order>` thành `EntityModel<OrderRepresentation>`, thêm metadata trang và tạo link điều hướng tương ứng.

Khi dùng `PagedResourcesAssembler`, Spring Data Web và Spring HATEOAS cần được cấu hình tích hợp. Trong Spring Boot, starter Spring Data và Spring HATEOAS thường cung cấp cấu hình tự động; với cấu hình thủ công, cần bật hỗ trợ Spring Data Web và hypermedia phù hợp.

## 10. Pageable parameter trong request có filter

Một endpoint thường kết hợp phân trang với các bộ lọc nghiệp vụ:

```http
GET /orders?status=PAID&customerId=C-105&page=0&size=20&sort=createdAt,desc HTTP/1.1
Accept: application/hal+json
```

Controller nhận filter và `Pageable` riêng:

Đây là phần method của controller; controller cần inject `OrderService`, `PagedResourcesAssembler<Order>` và `OrderModelAssembler` như ví dụ trước.

```java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping
PagedModel<EntityModel<OrderRepresentation>> search(
        @RequestParam(required = false) OrderStatus status,
        @RequestParam(required = false) UUID customerId,
        Pageable pageable) {

    Page<Order> page = orderService.search(status, customerId, pageable);
    return pagedResourcesAssembler.toModel(page, orderModelAssembler);
}
```

`Pageable` chỉ chứa page, size và sort. Các query parameter như `status` và `customerId` là filter riêng của endpoint, không tự trở thành thuộc tính của `Pageable`.

Khi tạo link `next` hoặc `prev`, cần giữ lại filter để client điều hướng trong cùng tập kết quả. Hãy kiểm tra link được tạo trong response thực tế, đặc biệt nếu ứng dụng dùng custom link base, proxy hoặc tự xây dựng pagination link. Nếu tự tạo link, cần giữ các filter và sort hiện tại, chỉ thay đổi page tương ứng.

## 11. Nhiều Pageable trong một controller

Trong một số màn hình, endpoint có thể cần phân trang hai tập dữ liệu độc lập. Spring Data Web hỗ trợ phân biệt các tham số bằng `@Qualifier`:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;

// Method fragment bên trong controller.
@GetMapping("/dashboard")
DashboardRepresentation dashboard(
        @Qualifier("orders") Pageable ordersPageable,
        @Qualifier("alerts") Pageable alertsPageable) {
    // Hai Pageable có page/size/sort độc lập.
}
```

Với delimiter mặc định `_`, request có thể dùng các nhóm tham số như `orders_page`, `orders_size`, `orders_sort` và `alerts_page`, `alerts_size`, `alerts_sort`. Cần xác nhận delimiter và prefix theo cấu hình resolver của ứng dụng.

Chỉ dùng nhiều `Pageable` khi endpoint thực sự trả nhiều collection độc lập. Nếu không, nên tách endpoint để hợp đồng dễ hiểu và link phân trang rõ ràng hơn.

## 12. Link phân trang trong HAL

`PagedResourcesAssembler` tạo `PagedModel` có metadata và link điều hướng. Một response HAL có thể có dạng:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "ORD-101",
        "status": "PAID",
        "_links": {
          "self": {
            "href": "https://api.example.test/orders/ORD-101"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test/orders?page=1&size=20&sort=createdAt,desc"
    },
    "first": {
      "href": "https://api.example.test/orders?page=0&size=20&sort=createdAt,desc"
    },
    "prev": {
      "href": "https://api.example.test/orders?page=0&size=20&sort=createdAt,desc"
    },
    "next": {
      "href": "https://api.example.test/orders?page=2&size=20&sort=createdAt,desc"
    },
    "last": {
      "href": "https://api.example.test/orders?page=4&size=20&sort=createdAt,desc"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 85,
    "totalPages": 5,
    "number": 1
  }
}
```

Đây là ví dụ minh họa cho một trang giữa của tập kết quả. Link `next` dẫn đến trang kế tiếp, `prev` dẫn về trang trước; `first` và `last` có thể xuất hiện khi có đủ metadata. Trang đầu không có `prev`, trang cuối không có `next`. `page.number` trong metadata của Spring Data thường là zero-based; nếu resolver nhận tham số một-based, cần xác nhận cách hiển thị và link theo hợp đồng API.

Client nên theo link được server cung cấp thay vì tự tính `page + 1` và ghép URL. Nhờ vậy, server có thể thay đổi tên query parameter, cấu trúc route hoặc cách phân trang mà client vẫn điều hướng theo hypermedia.

## 13. Sắp xếp ổn định giữa các trang

Nếu sort không tạo ra thứ tự duy nhất, các phần tử có cùng giá trị sort có thể thay đổi vị trí giữa những request. Ví dụ chỉ sắp xếp theo `status` có thể khiến các đơn hàng cùng trạng thái xuất hiện không ổn định ở ranh giới trang.

Hãy thêm một thuộc tính phân biệt, thường là ID:

```http
GET /orders?page=0&size=20&sort=status,asc&sort=id,asc
```

Thứ tự sắp xếp ổn định giúp giảm hiện tượng trùng hoặc bỏ sót phần tử khi client đi qua các trang trong khi dữ liệu ít thay đổi. Tuy nhiên, offset pagination vẫn có thể dịch chuyển kết quả khi bản ghi mới được thêm hoặc xóa giữa các request. Với tập dữ liệu cập nhật liên tục và yêu cầu điều hướng ổn định hơn, cân nhắc keyset/cursor pagination.

## 14. Kiểm thử Pageable parameter và link

Kiểm thử controller bằng `MockMvc` có thể xác nhận request parameter được phân tích đúng và response chứa metadata/link:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderPaginationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsRequestedPageAndNavigationLinks() throws Exception {
        mockMvc.perform(get("/orders")
                        .param("page", "0")
                        .param("size", "5")
                        .param("sort", "createdAt,desc")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page.size").value(5))
                .andExpect(jsonPath("$.page.number").value(0))
                .andExpect(jsonPath("$._links.self.href").exists());
    }
}
```

Test cần có dữ liệu đủ để tạo trang và repository/service được cấu hình phù hợp. Nếu chỉ có một trang, link `next` có thể không xuất hiện; hãy chuẩn bị nhiều hơn `size` phần tử khi muốn kiểm tra `next`.

Nên kiểm tra thêm:

- Bỏ `page`, `size` và `sort` thì dùng đúng giá trị mặc định.
- Nhiều tham số `sort` được áp dụng theo đúng thứ tự.
- `size` vượt giới hạn bị giới hạn theo cấu hình resolver.
- `page` được diễn giải đúng theo zero-based hoặc one-based.
- Link `next`, `prev`, `first` và `last` giữ nguyên filter và sort.
- Link item trong `_embedded` có relation `self` đúng.
- Trang đầu/cuối không phát link điều hướng không hợp lệ.
- Sort property không nằm trong allow-list bị từ chối hoặc xử lý theo chính sách API.

## 15. Lỗi thường gặp

**Nhầm page bắt đầu từ 1:** Spring Data mặc định dùng zero-based. Chỉ dùng one-based khi resolver được cấu hình rõ ràng.

**Không giới hạn size:** client có thể yêu cầu lượng dữ liệu quá lớn. Đặt default và max page size.

**Nhầm Pageable với Page:** `Pageable` là yêu cầu đầu vào; `Page<T>` là kết quả truy vấn có metadata.

**Trả Page thô như hợp đồng hypermedia:** cấu trúc serialize trực tiếp của `Page` không phải hợp đồng hypermedia ổn định. Dùng `PagedModel` và assembler để công bố metadata/link.

**Sort theo property tùy ý:** không phải mọi property đều nên công khai để sắp xếp. Kiểm tra allow-list và chi phí truy vấn.

**Không có tiêu chí sort cuối ổn định:** các phần tử có cùng giá trị sort có thể đổi vị trí giữa các trang. Thêm ID hoặc thuộc tính duy nhất làm tie-break.

**Làm mất filter trong link điều hướng:** client có thể rời khỏi tập kết quả đang xem. Giữ filter và sort trong link `next`/`prev`.

**Tự ghép URL trang ở client:** cách này gắn client với tên query parameter và route. Hãy theo link do server công bố.

## 16. Checklist triển khai

- Nhận `Pageable` trực tiếp trong controller thay vì tự parse page/size/sort.
- Công bố rõ page zero-based hay one-based.
- Đặt `@PageableDefault` cho kích thước và sort mặc định phù hợp.
- Cấu hình `default-page-size` và `max-page-size`.
- Chỉ cho phép sort theo các property được công bố và có chi phí hợp lý.
- Thêm tie-breaker duy nhất để thứ tự ổn định.
- Chọn `Page` khi cần tổng số kết quả, `Slice` khi chỉ cần biết còn dữ liệu hay không.
- Chuyển `Page<T>` thành `PagedModel` bằng `PagedResourcesAssembler`.
- Kiểm tra metadata và link phân trang trong HAL response.
- Giữ filter, sort và context path trong link điều hướng.
- Kiểm thử mặc định, giới hạn, sort nhiều trường và các trang đầu/cuối.
- Hướng dẫn client theo link do server cung cấp thay vì tự tính URL.

`Pageable` chuẩn hóa cách client yêu cầu một phần dữ liệu, còn Spring HATEOAS giúp công bố kết quả đó thành một resource collection có metadata và link điều hướng. Khi cấu hình tham số, giới hạn kích thước và thứ tự sắp xếp rõ ràng, API có thể hỗ trợ phân trang nhất quán và cho phép client điều hướng mà không phụ thuộc vào cách server tổ chức truy vấn.
