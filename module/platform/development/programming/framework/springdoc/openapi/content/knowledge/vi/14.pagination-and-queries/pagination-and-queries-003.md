# Tên `page`, `size`, `sort` và giá trị mặc định của ứng dụng

API phân trang cần một quy ước ổn định để client yêu cầu đúng phần dữ liệu. Với Spring Data, `Pageable` gom ba thông tin thường gặp: số trang, kích thước trang và thứ tự sắp xếp. Spring MVC tự bind các query parameter thành `Pageable`; springdoc-openapi có thể mô tả chúng thành các parameter riêng trong OpenAPI để Swagger UI hiển thị đúng cách gọi.

Tên query parameter và giá trị mặc định có thể đến từ cấu hình toàn ứng dụng hoặc annotation tại từng controller method. Cần phân biệt cấu hình resolver của Spring Data, mặc định riêng của `@PageableDefault` và schema mà springdoc công bố. Nếu ba phần này không đồng nhất, client có thể gửi đúng theo Swagger UI nhưng server lại áp dụng cách phân trang khác.

## 1. `Pageable` gom page, size và sort

Spring Data cung cấp `Pageable` để biểu diễn yêu cầu phân trang. Thay vì khai báo ba tham số rời rạc, controller nhận một đối tượng:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping
    Page<OrderResponse> list(Pageable pageable) {
        return orderService.findAll(pageable);
    }
}
```

Spring Data Web tự chuyển query parameter thành `Pageable`. Với tên mặc định, client có thể gọi:

```http
GET /api/orders?page=0&size=20&sort=createdAt,desc
```

Ý nghĩa:

- `page`: chỉ số trang. Mặc định bắt đầu từ `0`, tức trang đầu tiên là `page=0`.
- `size`: số phần tử tối đa trong một trang.
- `sort`: thuộc tính dùng để sắp xếp và hướng sắp xếp, thường là `asc` hoặc `desc`.

`Pageable` là yêu cầu gửi vào repository/service; nó không tự truy vấn dữ liệu. Service có thể truyền nó cho repository Spring Data để nhận `Page<T>`, hoặc dùng thông tin của nó để gọi một nguồn dữ liệu khác.

## 2. Tên parameter mặc định và cấu hình toàn ứng dụng

Với cấu hình Spring Data Web thông dụng trong Spring Boot, tên parameter mặc định là `page`, `size` và `sort`. Có thể thay đổi tên và giới hạn ở cấp ứng dụng trong `application.yml`:

```yaml
spring:
  data:
    web:
      pageable:
        page-parameter: page
        size-parameter: size
        default-page-size: 20
        max-page-size: 100
        one-indexed-parameters: false
        prefix: ""
        qualifier-delimiter: _
      sort:
        sort-parameter: sort
```

Các thuộc tính quan trọng:

| Property | Ý nghĩa | Giá trị thường dùng mặc định |
| --- | --- | --- |
| `spring.data.web.pageable.page-parameter` | Tên query parameter cho chỉ số trang | `page` |
| `spring.data.web.pageable.size-parameter` | Tên query parameter cho kích thước trang | `size` |
| `spring.data.web.pageable.default-page-size` | Kích thước trang khi client không gửi `size` | `20` |
| `spring.data.web.pageable.max-page-size` | Giới hạn kích thước trang resolver chấp nhận | `2000` |
| `spring.data.web.pageable.one-indexed-parameters` | Có nhận chỉ số trang bắt đầu từ `1` ở URL hay không | `false` |
| `spring.data.web.pageable.prefix` | Tiền tố thêm vào tên parameter phân trang | Chuỗi rỗng |
| `spring.data.web.pageable.qualifier-delimiter` | Ký tự ngăn giữa qualifier và tên parameter | `_` |
| `spring.data.web.sort.sort-parameter` | Tên query parameter cho sắp xếp | `sort` |

Các giá trị mặc định trong bảng là mặc định phổ biến của Spring Boot/Spring Data Web; hãy kiểm tra cấu hình và phiên bản đang chạy nếu ứng dụng có custom `PageableHandlerMethodArgumentResolver` hoặc `SortHandlerMethodArgumentResolver`. `max-page-size` là giới hạn bảo vệ tài nguyên: dù client yêu cầu `size=100000`, resolver vẫn giới hạn theo cấu hình tối đa.

Nếu đổi tên parameter, ví dụ dùng `p`, `limit` và `orderBy`, client phải gọi theo tên mới. Cần bảo đảm đặc tả OpenAPI cũng công bố đúng các tên đó. Sau khi thay đổi property, kiểm tra `/v3/api-docs` và request HTTP thực tế; nếu phiên bản springdoc không phản ánh custom name như mong muốn, hãy tùy chỉnh parameter trong OpenAPI bằng annotation hoặc `OpenApiCustomizer`.

## 3. Thay đổi tên parameter

Ví dụ ứng dụng muốn dùng tên ngắn `p` cho trang, `limit` cho số phần tử và `orderBy` cho sắp xếp:

```yaml
spring:
  data:
    web:
      pageable:
        page-parameter: p
        size-parameter: limit
        default-page-size: 25
        max-page-size: 100
      sort:
        sort-parameter: orderBy
```

Client gọi:

```http
GET /api/orders?p=0&limit=25&orderBy=createdAt,desc
```

Tên parameter là một phần của hợp đồng API. Khi đổi từ `page` sang `p`, các client cũ vẫn gửi `page` có thể không còn phân trang như dự kiến. Nếu cần chuyển đổi không gián đoạn, có thể duy trì alias trong một giai đoạn bằng resolver tùy chỉnh hoặc thiết kế endpoint phiên bản mới; không nên đổi tên công khai mà không thông báo cho client.

## 4. Chỉ số trang bắt đầu từ 0 hay 1

Spring Data `Pageable` sử dụng chỉ số nội bộ bắt đầu từ `0`. Cấu hình `one-indexed-parameters` thay đổi cách client đánh số trên URL:

```yaml
spring:
  data:
    web:
      pageable:
        one-indexed-parameters: true
```

Khi bật cấu hình này, client gửi `page=1` để yêu cầu trang đầu tiên, `page=2` cho trang thứ hai. Resolver chuyển chỉ số bên ngoài về chỉ số nội bộ phù hợp trước khi tạo `Pageable`.

Điều này không có nghĩa `Page.getNumber()` đổi sang một-based. Metadata của `Page` vẫn dựa trên chỉ số nội bộ zero-based. Nếu response body trả `number`, hãy mô tả rõ quy ước này để client không cộng hoặc trừ sai một đơn vị.

Không bật `one-indexed-parameters` chỉ để làm Swagger UI trông thân thiện hơn nếu các client hiện tại đã dùng zero-based. Đây là thay đổi cách gọi API và cần được phản ánh nhất quán trong tài liệu, kiểm thử và ví dụ request.

## 5. Giá trị mặc định toàn ứng dụng và `@PageableDefault`

`default-page-size` trong cấu hình Spring Data Web là mặc định toàn ứng dụng khi controller không khai báo mặc định riêng. Một method có thể ghi đè bằng `@PageableDefault`:

```java
@GetMapping("/recent")
Page<OrderResponse> recent(
    @ParameterObject
    @PageableDefault(
        page = 0,
        size = 25,
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return orderService.findRecent(pageable);
}
```

`@PageableDefault` có các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `page` | Chỉ số trang mặc định. |
| `size` | Kích thước trang mặc định. |
| `sort` | Một hoặc nhiều thuộc tính sắp xếp mặc định. |
| `direction` | Hướng sắp xếp mặc định cho các thuộc tính trong annotation. |

Lưu ý: `@PageableDefault` có giá trị mặc định riêng, thường là `page=0` và `size=10`. Khi annotation xuất hiện trên tham số, các giá trị của nó có thể thay cho `default-page-size` toàn ứng dụng. Vì vậy, nếu muốn dùng mặc định cấu hình của ứng dụng, đừng thêm `@PageableDefault` chỉ để đánh dấu tham số.

Query parameter client gửi vẫn có thể ghi đè mặc định method. Ví dụ method mặc định `size=25`, nhưng request có `size=10` thì resolver dùng kích thước 10, miễn là giá trị nằm trong giới hạn cho phép.

## 6. Thiết lập sort mặc định bằng `@SortDefault`

Khi muốn tách riêng quy tắc sắp xếp khỏi page/size, có thể dùng `@SortDefault`:

```java
@GetMapping
Page<OrderResponse> list(
    @ParameterObject
    @PageableDefault(size = 25)
    @SortDefault(
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return orderService.findAll(pageable);
}
```

Nếu cần sắp xếp theo nhiều thuộc tính mặc định, có thể khai báo container `@SortDefault.SortDefaults`:

```java
@GetMapping
Page<OrderResponse> list(
    @ParameterObject
    @PageableDefault(size = 25)
    @SortDefault.SortDefaults({
        @SortDefault(sort = "createdAt", direction = Sort.Direction.DESC),
        @SortDefault(sort = "id", direction = Sort.Direction.ASC)
    })
    Pageable pageable
) {
    return orderService.findAll(pageable);
}
```

Kết quả mặc định tương đương sắp xếp theo `createdAt DESC`, sau đó `id ASC`. Thứ tự phụ giúp kết quả ổn định khi nhiều bản ghi có cùng thời điểm tạo. Đây là cách tốt để tránh thứ tự thay đổi ngẫu nhiên giữa các lần phân trang.

`@PageableDefault(sort = ...)` cũng có thể khai báo sort trực tiếp. Chọn một cách dễ đọc và nhất quán; tránh khai báo nhiều nguồn mặc định chồng lấn mà không kiểm tra thứ tự ưu tiên trong phiên bản Spring Data đang dùng.

## 7. Cú pháp query parameter `sort`

Spring Data thường nhận mỗi tiêu chí sort theo dạng:

```text
sort=property,direction
```

Ví dụ:

```http
GET /api/orders?sort=createdAt,desc
```

Muốn sắp xếp theo nhiều tiêu chí, có thể lặp lại parameter:

```http
GET /api/orders?sort=createdAt,desc&sort=id,asc
```

Kết quả là `createdAt DESC`, sau đó `id ASC`. Có thể sắp xếp theo thuộc tính lồng nhau nếu property path đó hợp lệ với mô hình dữ liệu, ví dụ `customer.name,asc`. Tên thuộc tính và cú pháp cần phù hợp với entity hoặc mapping mà repository hỗ trợ.

Không nên nhầm `sort` với tên cột SQL. Client gửi tên thuộc tính của mô hình được Spring Data nhận diện; repository chịu trách nhiệm ánh xạ nó vào truy vấn. Nếu API muốn dùng tên thân thiện như `created`, nhưng entity có field `createdAt`, hãy ánh xạ giá trị công khai sang property nội bộ ở service hoặc resolver.

## 8. Giới hạn và kiểm soát thuộc tính sắp xếp

Không nên cho client sắp xếp tùy ý theo mọi field của entity. Một số field có thể không phù hợp để truy vấn, làm lộ cấu trúc nội bộ hoặc gây truy vấn tốn kém. Hãy công bố danh sách sort key được hỗ trợ và xác thực trước khi tạo `Pageable` hoặc `Sort`.

Ví dụ ánh xạ tên sort công khai:

```java
private static final Map<String, String> ALLOWED_SORTS = Map.of(
    "created", "createdAt",
    "status", "status",
    "customer", "customer.name"
);

Sort toAllowedSort(List<String> requestedSorts) {
    List<Sort.Order> orders = requestedSorts.stream()
        .map(value -> {
            String[] parts = value.split(",", 2);
            String property = ALLOWED_SORTS.get(parts[0]);
            if (property == null) {
                throw new IllegalArgumentException("Unsupported sort field: " + parts[0]);
            }
            Sort.Direction direction = parts.length == 2
                ? Sort.Direction.fromString(parts[1])
                : Sort.Direction.ASC;
            return new Sort.Order(direction, property);
        })
        .toList();

    return Sort.by(orders);
}
```

Đây là ví dụ minh họa cho việc ánh xạ allowlist; trong controller thực tế, có thể dùng một request model riêng hoặc custom argument resolver để nhận danh sách sort. Nếu dùng trực tiếp `Pageable`, cần kiểm tra các `Sort.Order` trước khi truyền xuống repository. Không dựa vào việc tên field không tồn tại sẽ tự động bị từ chối trong mọi kiểu query.

Giới hạn `max-page-size` cũng quan trọng tương tự. Kích thước trang quá lớn có thể làm tăng tải database, bộ nhớ và thời gian serialize. Chọn giới hạn theo độ nặng của response, chỉ mục database và năng lực hệ thống; không để client tự quyết định không giới hạn.

## 9. Dùng nhiều `Pageable` trong một operation

Một số endpoint tổng hợp có thể cần phân trang độc lập cho nhiều nhóm dữ liệu. Spring Data hỗ trợ qualifier để phân biệt tên parameter:

```java
@GetMapping("/dashboard")
DashboardResponse dashboard(
    @Qualifier("orders") @ParameterObject Pageable orders,
    @Qualifier("customers") @ParameterObject Pageable customers
) {
    return dashboardService.load(orders, customers);
}
```

Với delimiter mặc định `_`, các query parameter có thể là:

```http
GET /api/dashboard?orders_page=0&orders_size=10&orders_sort=createdAt,desc&customers_page=0&customers_size=5
```

`@Qualifier("orders")` và `@Qualifier("customers")` tạo namespace riêng cho từng nhóm. `qualifier-delimiter` cho phép đổi ký tự ngăn cách. Cấu trúc này tránh hai `Pageable` cùng đọc một bộ `page`, `size` và `sort`.

Nếu springdoc không tự thể hiện đúng tên parameter có qualifier trong phiên bản đang dùng, kiểm tra `/v3/api-docs` và khai báo/tùy chỉnh OpenAPI parameter tường minh. Không để tài liệu chỉ hiển thị một bộ `page`, `size`, `sort` trong khi runtime đòi hai bộ có prefix.

## 10. Mô tả `Pageable` bằng springdoc-openapi

Để springdoc phân rã `Pageable` thành query parameter riêng, dùng `@ParameterObject` trên tham số:

```java
@GetMapping
@Operation(summary = "Tìm kiếm đơn hàng có phân trang")
Page<OrderResponse> search(
    @ParameterObject
    @PageableDefault(size = 25, sort = "createdAt", direction = Sort.Direction.DESC)
    Pageable pageable
) {
    return orderService.search(pageable);
}
```

Springdoc nhận diện `Pageable` và mô tả các trường phân trang như parameter của operation. Swagger UI có thể hiển thị các ô `page`, `size`, `sort` thay vì một object Java không có dạng query rõ ràng.

Hãy kiểm tra `/v3/api-docs` để xác nhận:

- `page`, `size` và `sort` nằm trong `parameters` của operation với `in: query`.
- Schema của `page` và `size` là số nguyên.
- Mô tả nêu đúng chỉ số bắt đầu, kích thước tối đa và cú pháp sort.
- Giá trị mặc định phản ánh `@PageableDefault` hoặc cấu hình runtime.
- Nếu parameter đã đổi tên, đặc tả cũng dùng đúng tên mà resolver chấp nhận.

`@ParameterObject` là annotation của springdoc để phân rã object thành parameter; nó không thay đổi cách Spring Data bind query. Ngược lại, `@PageableDefault` điều chỉnh hành vi resolver; nó không tự bảo đảm mọi mô tả OpenAPI tùy chỉnh đã được cập nhật.

## 11. Kiểm tra mặc định và tên parameter trong ứng dụng

Khi thay đổi cấu hình phân trang, hãy kiểm tra cả ba lớp:

1. **Cấu hình:** xem `spring.data.web.pageable.*` và `spring.data.web.sort.sort-parameter` trong file cấu hình theo profile đang chạy.
2. **Runtime binding:** gọi endpoint không có query parameter để xác nhận page, size và sort mặc định; gọi lại với tên parameter tùy chỉnh để xác nhận resolver nhận đúng.
3. **OpenAPI:** mở `/v3/api-docs`, tìm operation và so sánh tên, kiểu, default, description của parameter với runtime.
4. **Giới hạn:** thử `size` lớn hơn `max-page-size` và xác nhận resolver áp dụng giới hạn.
5. **Sort:** thử nhiều tiêu chí, thứ tự tăng/giảm và field không được hỗ trợ; xác nhận allowlist hoặc validation từ chối đúng.
6. **One-based:** nếu bật `one-indexed-parameters`, kiểm tra `page=1` trả trang đầu và giải thích rõ metadata `Page.number` vẫn zero-based.

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Swagger UI gửi `page` nhưng server chờ `p` | Tên parameter trong OpenAPI không đồng bộ với resolver | Kiểm tra property và tùy chỉnh schema/parameter của springdoc. |
| Không gửi `size` nhưng kích thước khác mong đợi | `@PageableDefault` ghi đè mặc định toàn ứng dụng | Kiểm tra annotation tại method và `default-page-size`. |
| `size=10000` không trả 10.000 bản ghi | Resolver giới hạn theo `max-page-size` | Kiểm tra giới hạn và mô tả rõ trong tài liệu. |
| Trang đầu là `page=1` nhưng metadata trả `number=0` | Đang bật one-indexed request parameters | Mô tả rõ quy ước URL và chỉ số nội bộ. |
| Nhiều `sort` bị mất thứ tự | Client chỉ gửi một giá trị hoặc code tự chuyển đổi không giữ thứ tự | Dùng parameter lặp và giữ thứ tự các `Sort.Order`. |
| Sort theo field lạ gây lỗi truy vấn | Client gửi property không được hỗ trợ | Dùng allowlist và ánh xạ sort key công khai. |
| Hai `Pageable` dùng chung page/size | Thiếu `@Qualifier` hoặc delimiter không đồng bộ | Gắn qualifier cho từng tham số và kiểm tra tên query. |

## 12. Nguyên tắc áp dụng

- Dùng `Pageable` thay vì tự khai báo page, size, sort rời rạc nếu service dùng Spring Data.
- Giữ tên parameter ổn định và công bố đúng trong OpenAPI.
- Dùng cấu hình `spring.data.web.pageable.*` cho mặc định và giới hạn toàn ứng dụng.
- Dùng `@PageableDefault` hoặc `@SortDefault` khi một operation cần mặc định riêng.
- Quyết định rõ URL dùng zero-based hay one-based và đồng bộ với metadata response.
- Dùng cú pháp sort lặp cho nhiều tiêu chí; xác thực field theo allowlist.
- Dùng `@ParameterObject` để springdoc mô tả `Pageable` thành query parameter.
- Kiểm tra runtime binding, giới hạn resolver và `/v3/api-docs` sau mỗi thay đổi.

Tên `page`, `size`, `sort` và các giá trị mặc định là một phần của hợp đồng mà client sử dụng hằng ngày. Spring Data cung cấp cơ chế bind và giới hạn; `@PageableDefault` điều chỉnh từng operation; springdoc mô tả các parameter cho người dùng API. Khi ba lớp này nhất quán, client có thể phân trang và sắp xếp dự đoán được, còn server kiểm soát tốt tải truy vấn.

## Tài liệu tham khảo

- [Spring Data – Web Support và Pageable Handler](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)
- [Spring Boot – Application Properties: Spring Data Web](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Springdoc OpenAPI – tài liệu chính thức](https://springdoc.org/)
- [Spring Data Commons – `PageableDefault`](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableDefault.html)
- [Spring Data Commons – `SortDefault`](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/SortDefault.html)
