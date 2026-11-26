# Nhiều tiêu chí sort

Trong một REST API, một tiêu chí sắp xếp thường chưa đủ để xác định thứ tự ổn định cho tập dữ liệu. Ví dụ, khi liệt kê đơn hàng theo trạng thái, nhiều đơn hàng có thể cùng trạng thái. API cần tiêu chí thứ hai như thời điểm tạo; nếu thời điểm cũng trùng nhau, có thể dùng ID làm tiêu chí cuối. Spring Data biểu diễn chuỗi ưu tiên đó bằng nhiều `Sort.Order` trong một `Sort` hoặc nhiều query parameter `sort`.

Thứ tự các tiêu chí rất quan trọng: tiêu chí đầu tiên được áp dụng trước, tiêu chí tiếp theo chỉ phân định thứ tự giữa các phần tử bằng nhau ở tiêu chí trước. Khi kết hợp với `Pageable` và Spring HATEOAS, các tiêu chí sort cần được giữ nguyên trong link `self`, `next`, `prev` để client tiếp tục duyệt đúng tập kết quả.

## 1. Vì sao cần nhiều tiêu chí sort?

Giả sử API trả danh sách đơn hàng. Nếu chỉ sắp xếp theo trạng thái:

```sql
ORDER BY status ASC
```

thì các đơn hàng có cùng `status` không có thứ tự phụ được bảo đảm. Database có thể trả chúng theo thứ tự khác nhau giữa các lần truy vấn. Điều này đặc biệt dễ gây nhầm lẫn khi dữ liệu được chia thành nhiều trang.

Một thứ tự đầy đủ hơn có thể là:

```sql
ORDER BY status ASC, created_at DESC, id ASC
```

Ý nghĩa:

1. Xếp trạng thái theo thứ tự tăng dần.
2. Trong cùng một trạng thái, đơn hàng mới hơn đứng trước.
3. Nếu trạng thái và thời điểm tạo đều bằng nhau, dùng ID tăng dần để phân định.

| Ưu tiên | Thuộc tính | Hướng | Vai trò |
| --- | --- | --- | --- |
| 1 | `status` | ASC | Nhóm đơn hàng theo trạng thái |
| 2 | `createdAt` | DESC | Đơn mới hơn đứng trước trong cùng nhóm |
| 3 | `id` | ASC | Phá hòa để tạo thứ tự xác định |

Tiêu chí cuối nên có tính phân biệt cao, thường là khóa chính hoặc một thuộc tính duy nhất. Đây là cách tạo thứ tự ổn định hơn cho pagination.

## 2. Biểu diễn nhiều tiêu chí bằng Sort

Spring Data cung cấp `Sort` để chứa danh sách `Sort.Order`. Mỗi `Order` mô tả một property, hướng sắp xếp và một số tùy chọn như ignore case hoặc null handling.

```java
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
        Sort.Order.asc("status"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id"));
```

Thứ tự khai báo trong `Sort.by(...)` chính là thứ tự ưu tiên. Đoạn code tương đương với `ORDER BY status ASC, created_at DESC, id ASC` ở mức ý nghĩa truy vấn; tên cột SQL thực tế phụ thuộc mapping của persistence layer.

Có thể viết theo cách nối các `Sort` đơn:

```java
Sort sort = Sort.by("status").ascending()
        .and(Sort.by("createdAt").descending())
        .and(Sort.by("id").ascending());
```

`and(...)` nối các tiêu chí vào cuối chuỗi hiện có. Vì vậy, đổi thứ tự gọi `and(...)` có thể làm thay đổi kết quả. Không xem các tiêu chí sort như một tập hợp không có thứ tự.

## 3. Kết hợp Sort với Pageable

`Pageable` chứa đồng thời số trang, kích thước trang và `Sort`. Có thể tạo nó bằng `PageRequest.of(...)`:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
        Sort.Order.asc("status"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id"));

Pageable pageable = PageRequest.of(0, 20, sort);
```

Request này lấy trang đầu tiên với tối đa 20 phần tử và áp dụng cả ba tiêu chí. Khi repository nhận `Pageable`, Spring Data chuyển page, size và sort thành yêu cầu truy vấn phù hợp với implementation repository.

Ví dụ repository:

```java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<Order, UUID> {

    Page<Order> findByStatus(OrderStatus status, Pageable pageable);
}
```

Phương thức `findByStatus(...)` lọc theo trạng thái và áp dụng sort trong `Pageable`. Điều kiện lọc và thứ tự sắp xếp là hai phần độc lập của truy vấn.

## 4. Truyền nhiều sort parameter từ client

Spring Data Web cho phép client gửi nhiều tham số `sort`. Mỗi tham số có thể mô tả một tiêu chí:

```http
GET /orders?page=0&size=20&sort=status,asc&sort=createdAt,desc&sort=id,asc HTTP/1.1
Accept: application/hal+json
```

Spring Data Web phân tích các tham số này thành một `Sort` theo đúng thứ tự xuất hiện. Kết quả tương đương với:

```java
Sort.by(
        Sort.Order.asc("status"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id"));
```

Cú pháp `sort=property,direction` thường được dùng cho từng tiêu chí. Có thể lặp query parameter `sort` để diễn tả nhiều property với hướng khác nhau. Hãy kiểm tra cấu hình delimiter của `SortHandlerMethodArgumentResolver` nếu ứng dụng đã tùy chỉnh cách phân tích tham số.

Không nên gửi các tiêu chí trong một chuỗi tùy ý mà server không hiểu. Hợp đồng API cần công bố tên sort field, cú pháp direction và cách xử lý khi một field không được hỗ trợ.

## 5. Nhận nhiều tiêu chí trong controller

Spring Data Web tự chuyển query parameter thành `Pageable` khi web support được cấu hình:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
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
    Page<Order> all(Pageable pageable) {
        return orderRepository.findAll(pageable);
    }
}
```

Với request:

```text
/orders?page=0&size=20&sort=status,asc&sort=createdAt,desc&sort=id,asc
```

`pageable.getSort()` chứa ba `Sort.Order` theo thứ tự client gửi. Controller không cần tự phân tích từng chuỗi `sort` nếu cách mặc định của Spring Data Web phù hợp với hợp đồng API.

Trong API hypermedia, có thể chuyển `Page<Order>` thành `PagedModel` bằng `PagedResourcesAssembler`, như phần dưới đây.

## 6. Thiết lập thứ tự mặc định với @SortDefault

Nếu API cần một thứ tự mặc định nhiều tiêu chí khi client không gửi `sort`, có thể dùng `@SortDefault.SortDefaults`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.SortDefault;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping
Page<Order> all(
        @PageableDefault(size = 20)
        @SortDefault.SortDefaults({
                @SortDefault(sort = "status", direction = Sort.Direction.ASC),
                @SortDefault(sort = "createdAt", direction = Sort.Direction.DESC),
                @SortDefault(sort = "id", direction = Sort.Direction.ASC)
        }) Pageable pageable) {
    return orderRepository.findAll(pageable);
}
```

Trong trường hợp client không truyền `sort`, resolver sử dụng các mặc định được khai báo. Nếu client truyền sort, yêu cầu từ client được phân tích theo quy tắc của Spring Data Web. Nếu API luôn cần tie-breaker duy nhất, đừng chỉ dựa vào sort tùy chọn do client gửi; hãy bảo đảm server thêm tiêu chí cuối nếu thiếu.

## 7. Thêm tie-breaker ổn định

Khi client được phép chọn tiêu chí chính, server vẫn có thể thêm ID làm tiêu chí cuối để thứ tự ổn định. Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.domain.Sort;

Sort ensureStableSort(Sort requested) {
    if (requested.isUnsorted()) {
        return Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id"));
    }

    List<Sort.Order> orders = new ArrayList<>();
    Sort.Order requestedIdOrder = requested.getOrderFor("id");

    requested.forEach(order -> {
        if (!order.getProperty().equals("id")) {
            orders.add(order);
        }
    });

    orders.add(requestedIdOrder == null
            ? Sort.Order.asc("id")
            : requestedIdOrder);

    return Sort.by(orders);
}
```

`getOrderFor("id")` lấy direction mà client đã chọn cho ID nếu có. Hàm loại ID khỏi vị trí cũ rồi thêm nó vào cuối; nếu client chưa yêu cầu ID, hàm dùng `id ASC`. Nhờ vậy, ID luôn là tie-breaker cuối cùng và không vô tình trở thành tiêu chí ưu tiên cao hơn các field khác.

Có thể áp dụng sort ổn định cho `Pageable` bằng cách tạo lại `PageRequest` với cùng page và size:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable stablePageable = PageRequest.of(
        pageable.getPageNumber(),
        pageable.getPageSize(),
        ensureStableSort(pageable.getSort()));
```

Hãy đặt quy tắc tie-breaker ở một nơi dùng chung để mọi endpoint phân trang có cùng hành vi. Nếu ID là UUID ngẫu nhiên, thứ tự theo UUID vẫn có thể phân biệt bản ghi nhưng không nhất thiết mang ý nghĩa nghiệp vụ; đó vẫn có thể là lựa chọn hợp lệ nếu mục tiêu chỉ là tạo thứ tự xác định.

## 8. Ignore case cho tiêu chí chuỗi

Với dữ liệu chuỗi, có thể yêu cầu sort không phân biệt chữ hoa/chữ thường:

```java
Sort sort = Sort.by(
        Sort.Order.asc("customerName").ignoreCase(),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id"));
```

`ignoreCase()` áp dụng cho property chuỗi nếu datastore và query implementation hỗ trợ. Nó có thể làm thay đổi biểu thức truy vấn và ảnh hưởng index/performance. Không áp dụng tùy tiện cho mọi kiểu dữ liệu; chỉ dùng với field chuỗi và xác minh truy vấn sinh ra trong persistence technology của ứng dụng.

## 9. Xử lý giá trị null trong sort

`Sort.Order` có thể biểu diễn gợi ý về cách xử lý giá trị null:

```java
Sort sort = Sort.by(
        Sort.Order.asc("priority").nullsLast(),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id"));
```

`nullsFirst()` hoặc `nullsLast()` biểu thị mong muốn về vị trí của giá trị null. Đây là hint cho datastore/query layer; không phải mọi database hoặc repository implementation đều xử lý giống nhau. Nếu vị trí null là một phần quan trọng của hợp đồng API, hãy kiểm thử trên database thật hoặc kiểm thử tích hợp gần với môi trường triển khai.

Không nên giả định `nullsLast()` luôn được chuyển thành cùng cú pháp SQL trên mọi database. Có thể cần biểu thức sort riêng trong query nếu datastore không hỗ trợ hint như mong muốn.

## 10. Sort theo property lồng nhau

Spring Data có thể hỗ trợ sort theo property lồng nhau tùy repository và query implementation, ví dụ `customer.name`:

```http
GET /orders?sort=customer.name,asc&sort=createdAt,desc
```

Property path có thể khiến ORM tạo join hoặc truy vấn bổ sung. Vì vậy, không nên công bố mọi đường dẫn property nội bộ. Chỉ cho phép các field có ý nghĩa với client và có hiệu năng chấp nhận được.

Đối với native query, query tùy chỉnh hoặc projection, khả năng áp dụng sort động phụ thuộc cách query được khai báo và khả năng framework xử lý. Hãy xác minh repository thực tế; không phải mọi tên property trong `Sort` đều tự động được chuyển thành biểu thức hợp lệ.

## 11. Allow-list sort field công khai

Cho client gửi tên property trực tiếp có thể làm lộ cấu trúc nội bộ hoặc tạo truy vấn tốn kém. API nên công bố một tập sort field được hỗ trợ và ánh xạ tên công khai sang property truy vấn.

Ví dụ client dùng `created` nhưng domain property là `createdAt`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

class OrderSortPolicy {

    private static final Map<String, String> SORT_FIELDS = Map.of(
            "status", "status",
            "created", "createdAt",
            "customer", "customer.name",
            "id", "id");

    Sort toDomainSort(Sort requested) {
        List<Sort.Order> orders = new ArrayList<>();

        requested.forEach(order -> {
            String property = SORT_FIELDS.get(order.getProperty());
            if (property == null) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "Unsupported sort field: " + order.getProperty());
            }

            Sort.Order mapped = new Sort.Order(order.getDirection(), property);
            if (order.isIgnoreCase()) {
                mapped = mapped.ignoreCase();
            }
            mapped = switch (order.getNullHandling()) {
                case NULLS_FIRST -> mapped.nullsFirst();
                case NULLS_LAST -> mapped.nullsLast();
                default -> mapped.nullsNative();
            };
            orders.add(mapped);
        });

        return orders.isEmpty()
                ? Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("id"))
                : Sort.by(orders);
    }
}
```

Trong ví dụ, client chỉ được sort theo bốn tên công khai. `created` được ánh xạ sang `createdAt`, còn `customer` sang `customer.name`. Field không nằm trong allow-list bị từ chối bằng `400 Bad Request`. Nếu cần hỗ trợ `nullsFirst`/`nullsLast`, hãy quyết định rõ policy và kiểm tra datastore có đáp ứng hay không trước khi truyền hint.

Controller có thể áp dụng policy trước khi gọi repository:

Đây là method fragment bên trong controller; controller cần inject `OrderSortPolicy` và `OrderRepository`.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Page<Order> all(Pageable pageable) {
    Sort safeSort = ensureStableSort(
            orderSortPolicy.toDomainSort(pageable.getSort()));
    Pageable safePageable = PageRequest.of(
            pageable.getPageNumber(), pageable.getPageSize(), safeSort);
    return orderRepository.findAll(safePageable);
}
```

Trong ứng dụng thực tế, nên kiểm tra giới hạn page size và sort field ở tầng web/service dùng chung để tránh lặp logic giữa các endpoint.

## 12. Nhiều tiêu chí sort kết hợp filter

Filter xác định tập kết quả; sort xác định thứ tự trong tập đó. Ví dụ:

```http
GET /orders?status=PAID&customerId=C-105&sort=createdAt,desc&sort=id,asc
```

Request chỉ lấy đơn hàng đã thanh toán của khách hàng `C-105`, sau đó sắp xếp theo thời điểm tạo giảm dần và ID tăng dần.

Controller nhận filter và `Pageable` riêng:

```java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping
Page<Order> search(
        @RequestParam(required = false) OrderStatus status,
        @RequestParam(required = false) UUID customerId,
        Pageable pageable) {
    return orderService.search(status, customerId, pageable);
}
```

Các query parameter `status` và `customerId` không tự trở thành sort criteria. `Pageable` chứa page, size và sort; service nhận filter riêng để xây dựng truy vấn phù hợp.

## 13. Giữ sort trong link phân trang Spring HATEOAS

Khi endpoint trả `Page<T>`, `PagedResourcesAssembler` có thể chuyển kết quả thành `PagedModel` cùng các link điều hướng:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;

// Method fragment bên trong controller.
PagedModel<EntityModel<OrderRepresentation>> all(
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderRepository.findAll(pageable);
    return pagedAssembler.toModel(page, orderModelAssembler);
}
```

`PagedResourcesAssembler` dùng thông tin phân trang của `Page` để tạo link `self`, `first`, `prev`, `next` và `last` khi phù hợp. Các tiêu chí sort là một phần của `Pageable`, do đó link điều hướng cần giữ lại các tiêu chí đó.

Ví dụ link HAL cho trang kế tiếp:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.test/orders?page=0&size=20&sort=status,asc&sort=createdAt,desc&sort=id,asc"
    },
    "next": {
      "href": "https://api.example.test/orders?page=1&size=20&sort=status,asc&sort=createdAt,desc&sort=id,asc"
    }
  }
}
```

Client nên theo link `next` do server cung cấp. Không tự ghép `page=page+1` và không làm mất các query parameter sort hoặc filter. Điều này giúp server thay đổi route hoặc tên tham số mà client vẫn điều hướng đúng theo hypermedia.

## 14. Kiểm thử nhiều tiêu chí sort

Kiểm thử cần xác nhận thứ tự ưu tiên thực sự, không chỉ xác nhận response có dữ liệu. Có thể tạo dữ liệu test với các trường hợp trùng tiêu chí đầu và tiêu chí thứ hai:

| ID | Status | Created at |
| --- | --- | --- |
| `O-3` | PAID | 2026-01-10T10:00:00Z |
| `O-1` | PAID | 2026-01-10T10:00:00Z |
| `O-2` | PAID | 2026-01-09T10:00:00Z |
| `O-4` | PENDING | 2026-01-11T10:00:00Z |

Với sort `status ASC`, `createdAt DESC`, `id ASC`, thứ tự kỳ vọng là `O-1`, `O-3`, `O-2`, `O-4` nếu thứ tự enum/status tăng dần đặt `PAID` trước `PENDING`.

Một unit test có thể kiểm tra `Sort` được xây dựng đúng:

```java
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Sort;

import static org.assertj.core.api.Assertions.assertThat;

class OrderSortPolicyTest {

    @Test
    void buildsSortWithPrimarySecondaryAndTieBreaker() {
        Sort requested = Sort.by(
                Sort.Order.asc("status"),
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id"));
        Sort sort = new OrderSortPolicy().toDomainSort(requested);

        assertThat(sort.stream().map(Sort.Order::getProperty).toList())
                .containsExactly("status", "createdAt", "id");
        assertThat(sort.getOrderFor("status").getDirection())
                .isEqualTo(Sort.Direction.ASC);
        assertThat(sort.getOrderFor("createdAt").getDirection())
                .isEqualTo(Sort.Direction.DESC);
        assertThat(sort.getOrderFor("id").getDirection())
                .isEqualTo(Sort.Direction.ASC);
    }
}
```

Unit test này kiểm tra thứ tự khai báo và direction. Cần thêm integration test với repository để xác nhận datastore thực sự trả dữ liệu đúng thứ tự.

Với Spring MVC và `MockMvc`, có thể kiểm tra link phân trang giữ sort:

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
class OrderSortingHypermediaTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void preservesSortCriteriaInNextLink() throws Exception {
        mockMvc.perform(get("/orders")
                        .param("page", "0")
                        .param("size", "2")
                        .param("sort", "status,asc")
                        .param("sort", "createdAt,desc")
                        .param("sort", "id,asc")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.next.href")
                        .value(containsString("sort=status")))
                .andExpect(jsonPath("$._links.next.href")
                        .value(containsString("createdAt")))
                .andExpect(jsonPath("$._links.next.href")
                        .value(containsString("id")));
    }
}
```

Test cần có ít nhất ba phần tử phù hợp để trang đầu kích thước hai có link `next`. Dữ liệu phải được chuẩn bị trong test fixture hoặc database test. Nếu framework URL-encode dấu phẩy trong `href`, hãy kiểm tra giá trị đã decode hoặc dùng assertion phù hợp với encoding thay vì phụ thuộc chuỗi thô.

## 15. Lỗi thường gặp

**Đảo thứ tự ưu tiên:** `status` và `createdAt` không thể đổi chỗ nếu muốn giữ cùng kết quả. Tiêu chí đầu là ưu tiên cao nhất.

**Chỉ sort theo field không duy nhất khi phân trang:** các phần tử bằng nhau có thể đổi vị trí giữa request. Thêm tie-breaker như ID.

**Gửi một sort parameter nhưng nghĩ rằng mọi tiêu chí được áp dụng:** kiểm tra cú pháp resolver. Cách dễ đọc là lặp `sort` cho từng tiêu chí.

**Không kiểm soát field client được sort:** tên property nội bộ có thể bị lộ hoặc tạo truy vấn đắt. Dùng allow-list và ánh xạ tên công khai.

**Giả định ignoreCase/nullsLast hoạt động giống nhau ở mọi database:** đây là khả năng phụ thuộc datastore. Kiểm thử trên môi trường gần production.

**Làm mất sort trong link next/prev:** client sẽ duyệt tập dữ liệu với thứ tự khác. Giữ các query parameter sort trong link.

**Nhầm filter với sort:** filter thu hẹp tập kết quả; sort chỉ sắp xếp tập kết quả đó. Giữ hai phần riêng trong controller/service.

**Tin rằng tie-breaker ngăn mọi dịch chuyển trang:** offset pagination vẫn có thể thay đổi khi bản ghi được thêm hoặc xóa giữa các request. Cân nhắc cursor pagination cho dữ liệu biến động cao.

## 16. Checklist triển khai

- Xác định tiêu chí chính, phụ và tiêu chí phá hòa theo yêu cầu nghiệp vụ.
- Dùng nhiều `Sort.Order` theo đúng thứ tự ưu tiên.
- Dùng nhiều query parameter `sort` để client gửi nhiều tiêu chí.
- Kết hợp `Sort` với `Pageable` để truy vấn phân trang.
- Đặt mặc định bằng `@SortDefault.SortDefaults` khi cần.
- Thêm tie-breaker duy nhất nếu client không cung cấp.
- Chỉ cho phép sort field nằm trong allow-list công khai.
- Chỉ dùng `ignoreCase()` và null handling khi datastore hỗ trợ và đã kiểm thử.
- Kiểm tra sort trên property lồng nhau và query tùy chỉnh.
- Dùng `PagedResourcesAssembler` để tạo `PagedModel` và link điều hướng.
- Giữ nguyên sort và filter trong link `next`, `prev`, `self`.
- Kiểm thử thứ tự dữ liệu trên repository và link hypermedia trên response.

Nhiều tiêu chí sort tạo ra thứ tự có ý nghĩa và ổn định hơn cho collection REST. Khi Spring Data nhận các `Sort.Order` theo đúng thứ tự ưu tiên, API kiểm soát field được phép sort và Spring HATEOAS giữ các tiêu chí đó trong link phân trang, client có thể duyệt dữ liệu nhất quán mà không phải tự xây dựng quy tắc sắp xếp hoặc URL.
