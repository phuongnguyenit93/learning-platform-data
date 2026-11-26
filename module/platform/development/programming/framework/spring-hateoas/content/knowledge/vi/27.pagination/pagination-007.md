# Tham số sort trong Spring Data và Spring HATEOAS

Phân trang xác định một lát dữ liệu được trả về; tham số **sort** xác định thứ tự các phần tử trong lát dữ liệu đó. Với Spring Data, máy khách gửi sort criteria trong query string, Spring MVC chuyển chúng thành đối tượng `Sort` bên trong `Pageable`, rồi repository áp dụng các tiêu chí này khi truy vấn. Khi kết hợp Spring HATEOAS, `PagedResourcesAssembler` tạo các link điều hướng trang và giữ ngữ cảnh sắp xếp để máy khách tiếp tục duyệt cùng một thứ tự.

Ví dụ:

~~~http
GET /orders?page=0&size=20&sort=createdAt,desc&sort=id,asc
~~~

Request này lấy trang đầu gồm tối đa 20 đơn hàng, sắp xếp theo `createdAt` giảm dần; nếu nhiều đơn có cùng thời điểm tạo, `id` tăng dần được dùng làm tiêu chí phụ.

## 1. Sort giải quyết vấn đề gì khi phân trang?

Giả sử collection có các đơn hàng:

| ID | Thời điểm tạo |
|---:|---|
| 101 | 10:15 |
| 102 | 09:20 |
| 103 | 11:05 |
| 104 | 10:15 |

Nếu API chỉ dùng `page=0&size=2` mà không xác định thứ tự, database không bảo đảm các phần tử luôn xuất hiện theo cùng một thứ tự. Trang đầu có thể thay đổi giữa các lần truy vấn, đặc biệt khi dữ liệu được thêm hoặc cập nhật.

Sort làm cho thứ tự trở nên rõ ràng:

~~~http
GET /orders?page=0&size=2&sort=createdAt,desc
~~~

Kết quả được sắp xếp theo thời điểm tạo giảm dần trước khi chia trang. Tuy nhiên, hai đơn hàng có cùng `createdAt` vẫn có thể đổi chỗ nếu không có tiêu chí phụ.

Vì vậy, với dữ liệu được phân trang, nên xác định thứ tự có tính phân biệt đủ mạnh, thường bằng cách thêm khóa duy nhất như `id`:

~~~http
GET /orders?page=0&size=2&sort=createdAt,desc&sort=id,asc
~~~

Thứ tự ổn định giúp hạn chế bản ghi bị lặp hoặc bỏ sót do các hàng có cùng giá trị sort. Nó không tạo snapshot nhất quán khi dữ liệu liên tục thay đổi giữa các request; với use case cần duyệt tập dữ liệu biến động lớn, có thể cần keyset/cursor pagination.

## 2. Cú pháp query parameter sort

Spring Data Web mặc định dùng query parameter `sort`. Mỗi giá trị có thể chứa tên thuộc tính và hướng sắp xếp:

~~~text
sort=property,direction
~~~

Trong đó:

- `property` là thuộc tính mà repository có thể sắp xếp.
- `direction` là `asc` hoặc `desc`.
- Nếu bỏ direction, hướng mặc định là tăng dần (`ASC`).

Ví dụ:

| Query parameter | Ý nghĩa |
|---|---|
| `sort=createdAt` | `createdAt` tăng dần |
| `sort=createdAt,asc` | `createdAt` tăng dần |
| `sort=createdAt,desc` | `createdAt` giảm dần |
| `sort=total,desc` | `total` giảm dần |
| `sort=status,asc` | `status` tăng dần |

Tên thuộc tính thường là property của domain model hoặc property path mà repository hiểu, không nhất thiết là tên trường JSON mà DTO công bố.

Ví dụ DTO có trường `created` nhưng entity dùng `createdAt`. Nếu repository nhận `Pageable` trực tiếp, sort key có thể cần là `createdAt`; muốn public API dùng `created`, ứng dụng nên ánh xạ alias đó sang property nội bộ.

## 3. Sắp xếp theo nhiều tiêu chí

Có thể lặp lại query parameter `sort`. Mỗi giá trị tạo một tiêu chí sort riêng, theo đúng thứ tự xuất hiện:

~~~http
GET /orders?page=0&size=20&sort=status,asc&sort=createdAt,desc
~~~

Thứ tự được áp dụng như sau:

1. Sắp xếp theo `status` tăng dần.
2. Nếu nhiều đơn có cùng `status`, sắp xếp tiếp theo `createdAt` giảm dần.

Có thể thêm khóa duy nhất làm tiêu chí cuối:

~~~http
GET /orders?page=0&size=20&sort=status,asc&sort=createdAt,desc&sort=id,asc
~~~

Một số client gửi cùng tên query parameter nhiều lần. Vì vậy, khi tự xây request URL, hãy bảo đảm thư viện HTTP giữ được các giá trị `sort` lặp lại, không ghi đè giá trị trước bằng giá trị sau.

Không nên gộp nhiều tiêu chí thành một chuỗi tùy ý nếu cú pháp resolver của ứng dụng không hỗ trợ. Cách phổ biến và dễ đọc là một `sort` parameter cho mỗi tiêu chí.

## 4. Từ sort parameter đến Sort và Pageable

Spring Data Web phân tích query parameters rồi cung cấp đối tượng `Pageable` cho controller. `Pageable` chứa:

- Số trang hiện tại, bắt đầu từ 0 theo mặc định.
- Kích thước trang.
- Đối tượng `Sort` chứa danh sách tiêu chí.

Ví dụ controller:

~~~java
@GetMapping
public Page<Order> findAll(Pageable pageable) {
    return orderRepository.findAll(pageable);
}
~~~

Request:

~~~http
GET /orders?page=1&size=10&sort=createdAt,desc&sort=id,asc
~~~

Spring chuyển thành một Pageable tương đương về ý nghĩa với:

~~~java
PageRequest.of(
    1,
    10,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
    )
);
~~~

Controller không cần tự đọc từng tham số `page`, `size` và `sort`. Resolver của Spring Data thực hiện việc phân tích và binding.

`Pageable` có thể được truyền xuống service và repository. Repository Spring Data hỗ trợ các phương thức nhận `Pageable`, ví dụ `findAll(Pageable pageable)` hoặc query method có thêm tham số `Pageable`.

## 5. Tạo Sort bằng Java

Khi cần tạo thứ tự mặc định hoặc xây dựng truy vấn trong service, có thể dùng `Sort` và `Sort.Order`.

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("id")
);

Pageable pageable = PageRequest.of(0, 20, sort);

Page<Order> page = orderRepository.findAll(pageable);
~~~

`Sort.Order` biểu diễn một tiêu chí sắp xếp. Các factory method thường dùng:

~~~java
Sort.Order.asc("name");
Sort.Order.desc("createdAt");
~~~

Có thể tạo `Sort` từ một property và direction:

~~~java
Sort sort = Sort.by(Sort.Direction.DESC, "createdAt");
~~~

Hoặc kết hợp các tiêu chí:

~~~java
Sort sort = Sort.by("status")
    .ascending()
    .and(Sort.by("createdAt").descending());
~~~

Dùng `Sort.unsorted()` khi truy vấn không yêu cầu thứ tự cụ thể. Với API phân trang công khai, thường nên có thứ tự mặc định rõ ràng để response không phụ thuộc vào thứ tự tự nhiên của database.

## 6. Default sort bằng @PageableDefault

Nếu client không gửi `sort`, controller có thể áp dụng thứ tự mặc định bằng `@PageableDefault`.

~~~java
@GetMapping
public Page<Order> findAll(
        @PageableDefault(
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        ) Pageable pageable) {

    return orderRepository.findAll(pageable);
}
~~~

Request không có sort:

~~~http
GET /orders
~~~

sẽ dùng page size 20 và sort theo `createdAt` giảm dần.

Nếu client gửi sort tường minh, các tiêu chí trong request sẽ được dùng thay cho sort mặc định của annotation. Ví dụ:

~~~http
GET /orders?sort=total,asc
~~~

sẽ sắp xếp theo `total` tăng dần, trong khi page size mặc định vẫn là 20.

Có thể khai báo nhiều tiêu chí mặc định bằng `@PageableDefault`:

~~~java
@PageableDefault(
    size = 20,
    sort = {"createdAt", "id"},
    direction = Sort.Direction.DESC
)
Pageable pageable
~~~

Cách khai báo này áp dụng cùng direction cho các property trong mảng. Nếu cần direction khác nhau cho từng property, hãy tạo `Sort` rõ ràng trong cấu hình mặc định hoặc dùng `@SortDefault` với các order riêng.

## 7. Dùng @SortDefault cho nhiều hướng khác nhau

`@SortDefault` cho phép mô tả default sort riêng cho từng property. Khi cần nhiều order với direction khác nhau, có thể kết hợp `@SortDefault.SortDefaults`.

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.web.SortDefault;

@GetMapping
public Page<Order> findAll(
    @SortDefault.SortDefaults({
        @SortDefault(
            sort = "createdAt",
            direction = Sort.Direction.DESC
        ),
        @SortDefault(
            sort = "id",
            direction = Sort.Direction.ASC
        )
    })
    Pageable pageable
) {
    return orderRepository.findAll(pageable);
}
~~~

Khi client không truyền `sort`, thứ tự mặc định là `createdAt DESC`, sau đó `id ASC`. Nếu client gửi sort parameter, resolver dùng tiêu chí do client yêu cầu theo quy tắc của Pageable argument resolver.

Chọn `@PageableDefault` cho trường hợp đơn giản. Dùng `@SortDefault` khi cần nhiều tiêu chí mặc định với hướng khác nhau hoặc muốn tách cấu hình sort khỏi page size.

## 8. Thuộc tính nào có thể sort?

Sort property phải tương ứng với thuộc tính mà tầng truy vấn có thể xử lý. Với Spring Data JPA, các property path hợp lệ có thể bao gồm thuộc tính của entity và một số đường dẫn qua quan hệ, tùy query được tạo.

Ví dụ:

~~~http
GET /orders?sort=createdAt,desc
GET /orders?sort=customer.name,asc
GET /orders?sort=totalAmount,desc
~~~

Sort theo `customer.name` có thể khiến truy vấn cần join tới customer. Điều đó ảnh hưởng hiệu năng và có thể không phù hợp với mọi query hoặc projection.

Cần phân biệt ba tên:

| Tầng | Ví dụ |
|---|---|
| JSON field | `created` |
| Domain/entity property | `createdAt` |
| Database column | `created_at` |

Spring Data thường nhận property của domain/entity, không phải tên cột database. Không nên đưa tên cột SQL trực tiếp vào sort parameter trừ khi repository được thiết kế rõ ràng để nhận alias đó.

Với projection hoặc custom query, khả năng sort còn phụ thuộc query definition. Hãy kiểm thử truy vấn thực tế thay vì giả định mọi property đều có thể sort.

## 9. Giới hạn sort key được phép từ client

Không nên cho client tùy ý yêu cầu sắp xếp theo mọi thuộc tính nội bộ. Một sort key có thể gây join tốn kém, làm lộ cấu trúc domain hoặc tạo thứ tự không phù hợp với contract công khai.

Hãy định nghĩa allow-list cho các sort key mà API hỗ trợ:

~~~java
private static final Set<String> ALLOWED_SORTS = Set.of(
    "id",
    "status",
    "createdAt",
    "totalAmount"
);

private void validateSort(Pageable pageable) {
    for (Sort.Order order : pageable.getSort()) {
        if (!ALLOWED_SORTS.contains(order.getProperty())) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Unsupported sort property: " + order.getProperty()
            );
        }
    }
}
~~~

Sau đó kiểm tra trước khi gọi repository:

~~~java
@GetMapping
public Page<Order> findAll(Pageable pageable) {
    validateSort(pageable);
    return orderRepository.findAll(pageable);
}
~~~

Allow-list tạo ra contract rõ ràng: máy khách chỉ sort theo những field API công bố. Khi cần tên công khai khác với tên entity, có thể ánh xạ alias sang property nội bộ trong service trước khi truy vấn.

Không nên dùng `JpaSort.unsafe(...)` với giá trị lấy trực tiếp từ query parameter. API unsafe dành cho biểu thức sort được kiểm soát trong code, không phải để chuyển chuỗi tùy ý từ client thành SQL fragment.

## 10. Sort theo chữ hoa/chữ thường và giá trị null

`Sort.Order` cung cấp một số tùy chọn bổ sung:

~~~java
Sort.Order nameOrder = Sort.Order.asc("name")
    .ignoreCase();

Sort.Order newestFirst = Sort.Order.desc("createdAt")
    .nullsLast();
~~~

- `ignoreCase()` yêu cầu sắp xếp chuỗi không phân biệt chữ hoa/chữ thường nếu datastore/query hỗ trợ.
- `nullsFirst()` hoặc `nullsLast()` yêu cầu vị trí của giá trị null.
- `nullsNative()` để datastore quyết định cách xử lý null theo mặc định.

Ví dụ kết hợp:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("customerName").ignoreCase(),
    Sort.Order.desc("createdAt").nullsLast(),
    Sort.Order.asc("id")
);
~~~

Không phải database hoặc query engine nào cũng xử lý mọi tùy chọn giống nhau. Với JPA, khả năng thực tế còn phụ thuộc provider và dialect. Nếu thứ tự null là một phần quan trọng của API, hãy kiểm thử trên database mà ứng dụng sử dụng trong production.

## 11. Kết hợp sort với filter và pagination

Một endpoint thường nhận filter, sort và pagination cùng lúc:

~~~http
GET /orders?status=PAID&from=2026-01-01&page=0&size=20&sort=createdAt,desc&sort=id,asc
~~~

Controller:

~~~java
@GetMapping
public Page<Order> search(
        @RequestParam(required = false) OrderStatus status,
        @RequestParam(required = false) LocalDate from,
        Pageable pageable) {

    validateSort(pageable);

    return orderRepository.search(status, from, pageable);
}
~~~

Repository hoặc service chịu trách nhiệm áp dụng filter và Pageable trong cùng truy vấn. Sort chỉ quyết định thứ tự của tập kết quả sau khi điều kiện filter được áp dụng.

Không nên tải toàn bộ dữ liệu về Java rồi mới lọc và sort nếu repository có thể thực hiện các thao tác đó ở database. Cách làm ở database thường tiết kiệm bộ nhớ và chỉ lấy các hàng cần cho trang hiện tại.

## 12. Sort và link phân trang trong Spring HATEOAS

Khi controller trả `PagedModel`, `PagedResourcesAssembler` có thể tạo link `self`, `first`, `prev`, `next` và `last` dựa trên request hiện tại và metadata của `Page`.

Ví dụ:

~~~java
@GetMapping
public PagedModel<EntityModel<OrderDto>> search(
        @RequestParam(required = false) OrderStatus status,
        @PageableDefault(
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        ) Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    validateSort(pageable);

    Page<Order> page = orderService.search(status, pageable);

    return pagedAssembler.toModel(page, orderModelAssembler);
}
~~~

Request:

~~~http
GET /orders?status=PAID&page=0&size=20&sort=createdAt,desc&sort=id,asc
~~~

Link `next` được tạo có thể giữ các tham số truy vấn cần thiết:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders?status=PAID&page=0&size=20&sort=createdAt,desc&sort=id,asc"
    },
    "next": {
      "href": "/orders?status=PAID&page=1&size=20&sort=createdAt,desc&sort=id,asc"
    }
  }
}
~~~

Ví dụ chỉ minh họa các link chính. URI thực tế phụ thuộc request mapping, cấu hình resolver, context path và cách link cơ sở được tạo.

Máy khách nên theo link `next` mà server trả về thay vì tự tăng page và ghép lại query string. Như vậy, client giữ nguyên sort và filter mà server đã công bố.

## 13. Khi tạo custom base link cho PagedResourcesAssembler

Trong trường hợp cần truyền base link tùy chỉnh vào `toModel`, phải bảo đảm link đó giữ các tham số có ảnh hưởng tới tập kết quả, gồm filter và sort.

~~~java
Link baseLink = linkTo(
    methodOn(OrderController.class).search(
        status,
        from,
        pageable
    )
).withSelfRel();

return pagedAssembler.toModel(page, orderModelAssembler, baseLink);
~~~

Đây là ví dụ khái quát; chữ ký `search` và thứ tự tham số trong `methodOn` phải khớp controller thực tế. Nếu custom base link bỏ `sort` hoặc filter, các link điều hướng có thể không còn đại diện cho cùng tập kết quả.

Khi không có yêu cầu đặc biệt, để `PagedResourcesAssembler` sử dụng request hiện tại thường đơn giản và ít lỗi hơn.

## 14. Sort ổn định và vấn đề dữ liệu thay đổi

Một thứ tự sort không có khóa phân biệt có thể gây kết quả không ổn định. Ví dụ nhiều đơn hàng cùng `createdAt`:

~~~http
GET /orders?page=0&size=2&sort=createdAt,desc
~~~

Nếu bản ghi ở ranh giới trang có cùng giá trị sort, database không bắt buộc phải giữ thứ tự giữa chúng. Thêm `id` làm tie-breaker:

~~~http
GET /orders?page=0&size=2&sort=createdAt,desc&sort=id,asc
~~~

giúp xác định thứ tự duy nhất hơn.

Tuy nhiên, offset pagination vẫn có thể dịch chuyển khi có dữ liệu mới được chèn hoặc bản ghi hiện tại bị cập nhật giữa hai request. Ví dụ client tải trang 0, sau đó có đơn hàng mới được chèn ở đầu danh sách; khi client tải trang 1, một đơn hàng có thể xuất hiện lặp lại hoặc bị bỏ qua.

Với tập dữ liệu lớn hoặc cập nhật liên tục, cân nhắc keyset pagination/cursor pagination. Cursor thường dựa trên giá trị sort cuối cùng đã đọc, ví dụ `(createdAt, id)`, để truy vấn phần tiếp theo sau vị trí đó. Cách này cần contract riêng và không đồng nghĩa với việc chỉ thêm `sort` vào Pageable.

## 15. Giới hạn với native query và custom repository

Spring Data có thể áp dụng sort động thuận tiện cho query method và JPQL trong nhiều trường hợp. Với native SQL hoặc custom repository, việc thêm `ORDER BY` không phải lúc nào cũng tự động được hỗ trợ theo cùng cách.

Ví dụ native query đã chứa thứ tự cố định:

~~~sql
SELECT *
FROM orders
WHERE status = :status
ORDER BY created_at DESC
~~~

Nếu API nhận thêm `sort=totalAmount,asc`, query có thể không áp dụng sort đó như mong muốn. Cách xử lý phụ thuộc repository implementation và phiên bản Spring Data.

Hãy chọn một trong các hướng:

- Dùng query method hoặc JPQL hỗ trợ Pageable/Sort.
- Xây query động bằng các sort key đã allow-list.
- Dùng custom repository để ánh xạ sort key sang biểu thức query đã kiểm soát.
- Từ chối sort parameter không được hỗ trợ thay vì âm thầm bỏ qua.

Không nối trực tiếp giá trị query parameter vào chuỗi SQL `ORDER BY`.

## 16. Đổi tên tham số sort và resolver

Mặc định Spring Data Web dùng `sort` làm tên query parameter. Ứng dụng có thể cấu hình resolver nếu contract yêu cầu tên khác, chẳng hạn `orderBy`.

Khi tùy chỉnh resolver, cần bảo đảm mọi endpoint phân trang dùng cùng quy ước và các link do Spring HATEOAS tạo ra phản ánh đúng tên parameter. Nếu client gửi `orderBy` nhưng page links lại phát ra `sort`, contract sẽ khó sử dụng.

Việc đổi tên tham số cần được kiểm thử ở hai chiều:

1. Resolver đọc đúng query parameter do client gửi.
2. Link `self`, `next`, `prev` được tạo ra chứa đúng query parameter đã cấu hình.

Nếu không có yêu cầu tương thích cụ thể, giữ tên mặc định `sort` giúp API phù hợp với quy ước Spring Data Web.

## 17. Kiểm thử sort và page links bằng MockMvc

Kiểm thử nên xác nhận dữ liệu được trả theo thứ tự, query được truyền xuống repository và các link điều hướng giữ sort parameter.

Ví dụ kiểm tra response HAL:

~~~java
mockMvc.perform(
        get("/orders")
            .param("page", "0")
            .param("size", "2")
            .param("sort", "createdAt,desc")
            .param("sort", "id,asc")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$.page.size").value(2))
    .andExpect(jsonPath("$._links.self.href").value(
        org.hamcrest.Matchers.containsString("sort=createdAt")
    ))
    .andExpect(jsonPath("$._links.self.href").value(
        org.hamcrest.Matchers.containsString("sort=id")
    ))
    .andExpect(jsonPath("$._links.next.href").value(
        org.hamcrest.Matchers.containsString("page=1")
    ));
~~~

Ngoài kiểm tra JSON, có thể verify service/repository nhận `Pageable` với đúng `Sort.Order`:

~~~java
ArgumentCaptor<Pageable> pageableCaptor =
    ArgumentCaptor.forClass(Pageable.class);

verify(orderService).search(
    eq(OrderStatus.PAID),
    pageableCaptor.capture()
);

Pageable pageable = pageableCaptor.getValue();

assertThat(pageable.getSort().getOrderFor("createdAt").getDirection())
    .isEqualTo(Sort.Direction.DESC);

assertThat(pageable.getSort().getOrderFor("id").getDirection())
    .isEqualTo(Sort.Direction.ASC);
~~~

Nên có thêm các trường hợp:

- Không truyền sort thì dùng default sort.
- Truyền một sort key và direction.
- Truyền nhiều sort parameter để xác nhận thứ tự ưu tiên.
- Truyền direction không hợp lệ.
- Truyền property không nằm trong allow-list.
- Sort theo nested property nếu API công bố hỗ trợ.
- Link next/prev giữ sort và filter.
- Trang đầu không có `prev`; trang cuối không có `next`.
- Custom base link không làm mất sort criteria.

## 18. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Không khai báo sort khi phân trang | Thứ tự có thể không ổn định | Dùng default sort rõ ràng |
| Gửi tên JSON field thay cho entity property | Repository không tìm thấy property | Ánh xạ public sort key sang domain property |
| Gộp nhiều sort criteria sai cú pháp | Resolver không phân tích đúng thứ tự | Lặp query parameter `sort` |
| Không có tie-breaker | Các bản ghi bằng giá trị sort có thể đổi chỗ | Thêm khóa duy nhất như `id` |
| Cho phép mọi property nội bộ | Query nặng hoặc contract bị lộ cấu trúc | Dùng allow-list |
| Dùng `JpaSort.unsafe` với input client | Rủi ro query injection | Chỉ dùng biểu thức được kiểm soát trong code |
| Tự ghép link next | Có thể mất filter hoặc sort | Theo link từ PagedResourcesAssembler |
| Custom base link thiếu sort | Trang kế tiếp đổi thứ tự | Giữ toàn bộ query context |
| Native query bỏ qua sort động | Kết quả không theo yêu cầu client | Ánh xạ sort vào query có kiểm soát hoặc từ chối |
| Nghĩ sort ổn định bảo đảm snapshot | Dữ liệu mới vẫn làm offset page dịch chuyển | Cân nhắc cursor/keyset pagination |

## 19. Quy trình thiết kế sort cho API phân trang

Khi công bố tham số sort trong Spring Data và Spring HATEOAS, hãy thực hiện theo trình tự:

1. Chọn các sort key công khai mà API muốn hỗ trợ.
2. Xác định ánh xạ từ sort key sang property của domain/query.
3. Chọn default sort và thêm tie-breaker duy nhất khi phù hợp.
4. Nhận `Pageable` trong controller thay vì tự parse query string.
5. Validate sort property và direction trước khi truy vấn.
6. Truyền `Pageable` xuống service/repository để database thực hiện sort và pagination.
7. Dùng `PagedResourcesAssembler` tạo `PagedModel` và page links.
8. Bảo đảm link điều hướng giữ sort, filter và page size.
9. Kiểm thử thứ tự dữ liệu, sort mặc định, sort nhiều tiêu chí và page links.
10. Cân nhắc keyset/cursor pagination nếu dữ liệu thay đổi liên tục hoặc offset pagination không còn phù hợp.

Tham số `sort` cho phép máy khách kiểm soát thứ tự dữ liệu mà API trả về. Spring Data chuyển query parameter thành `Sort` bên trong `Pageable`, còn Spring HATEOAS có thể duy trì ngữ cảnh sort trong các link phân trang. Khi giới hạn sort key, dùng thứ tự mặc định ổn định và kiểm thử các page links, API sẽ dễ dự đoán và an toàn hơn khi dữ liệu tăng lên.

## Tài liệu tham khảo

- [Spring Data Commons — Web support và Pageable](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)
- [Spring Data Commons — Sort và Pageable API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Sort.html)
- [Spring Data Web — PageableDefault API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableDefault.html)
- [Spring HATEOAS Reference — Paging](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.paging)
