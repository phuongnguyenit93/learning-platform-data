# Bộ lọc bắt buộc

## Mục tiêu

Sau bài này, bạn có thể thiết kế endpoint collection yêu cầu client cung cấp các tiêu chí lọc bắt buộc, phân biệt tham số bị thiếu với giá trị rỗng hoặc không hợp lệ, ánh xạ query parameters thành filter object, kết hợp bộ lọc với `Pageable`, tạo response HAL có link điều hướng và kiểm thử hợp đồng bằng MockMvc.

## 1. Bộ lọc bắt buộc là gì?

Một endpoint collection có thể yêu cầu một hoặc nhiều tiêu chí trước khi truy vấn dữ liệu. Ví dụ, API tìm đơn hàng có thể bắt buộc client chỉ định trạng thái và khoảng thời gian:

```http
GET /orders?status=PENDING&from=2026-10-01&to=2026-10-31&page=0&size=20
Accept: application/hal+json
```

Trong ví dụ này:

- `status` giới hạn kết quả theo trạng thái đơn hàng.
- `from` và `to` xác định khoảng ngày cần tìm.
- `page` và `size` xác định phần dữ liệu cần lấy.
- `sort` có thể bổ sung thứ tự sắp xếp.

Bộ lọc được gọi là bắt buộc khi server không chấp nhận truy vấn nếu thiếu tiêu chí đó. Chẳng hạn, API báo cáo chỉ cho phép tìm theo khoảng thời gian, hoặc API tra cứu đơn hàng yêu cầu trạng thái để giới hạn tập kết quả.

Ví dụ hợp đồng:

| Tham số | Bắt buộc | Ý nghĩa |
|---|---|---|
| `status` | Có | Trạng thái đơn hàng |
| `from` | Có | Ngày bắt đầu, tính cả ngày này |
| `to` | Có | Ngày kết thúc, tính cả ngày này |
| `page` | Không | Mặc định là trang đầu |
| `size` | Không | Dùng kích thước mặc định của endpoint |
| `sort` | Không | Dùng thứ tự mặc định nếu client không truyền |

Bắt buộc hay tùy chọn là một phần của hợp đồng API. Client cần biết tham số nào phải gửi để request hợp lệ và server cần trả lỗi nhất quán khi điều kiện đó không được đáp ứng.

## 2. Phân biệt thiếu, rỗng và không hợp lệ

Ba trường hợp này không giống nhau:

1. **Thiếu tham số:** request không có `status`.
2. **Giá trị rỗng:** request có `status=` nhưng không cung cấp nội dung.
3. **Giá trị không hợp lệ:** request có `status=UNKNOWN`, trong khi API chỉ chấp nhận các trạng thái đã định nghĩa.

Với Spring MVC, `@RequestParam` mặc định có `required = true`. Nếu tham số không xuất hiện, framework thường trả lỗi 400 trước khi gọi phương thức controller:

```java
@GetMapping("/orders")
public List<OrderView> search(
        @RequestParam("status") OrderStatus status) {
    // ...
}
```

Request thiếu `status` sẽ không được bind thành công. Tuy nhiên, giá trị rỗng và giá trị không thể chuyển đổi cần được kiểm tra rõ ràng theo kiểu tham số và converter đang dùng. Đừng giả định rằng `required = true` đồng nghĩa mọi giá trị đều hợp lệ.

Với tham số kiểu enum, chuỗi không khớp hằng enum sẽ gây lỗi chuyển đổi và thường được ánh xạ thành 400. Với chuỗi tự do, cần kiểm tra chuỗi rỗng hoặc chỉ chứa khoảng trắng. Với ngày tháng, cần kiểm tra định dạng và quan hệ giữa hai mốc ngày.

Một endpoint có hợp đồng tốt cần trả lỗi dễ hiểu cho cả ba trường hợp, ví dụ:

- Thiếu `status`: báo tham số bắt buộc chưa được cung cấp.
- `status=`: báo giá trị không được để trống.
- `status=UNKNOWN`: báo trạng thái không được hỗ trợ.
- `from` lớn hơn `to`: báo khoảng thời gian không hợp lệ.

## 3. Gom các filter vào một request model

Khi endpoint có nhiều bộ lọc, dùng `@ModelAttribute` để bind query parameters vào một đối tượng criteria giúp chữ ký controller gọn và dễ mở rộng.

Ví dụ record chứa tiêu chí tìm kiếm:

```java
import java.time.LocalDate;

import jakarta.validation.constraints.NotNull;

import org.springframework.format.annotation.DateTimeFormat;

public record OrderSearchCriteria(
        @NotNull OrderStatus status,

        @NotNull
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate from,

        @NotNull
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate to
) {
}
```

Các annotation có ý nghĩa:

- `@NotNull` yêu cầu trường phải có giá trị sau khi bind.
- `@DateTimeFormat` quy định ngày được truyền theo định dạng ISO `yyyy-MM-dd`.
- `OrderStatus` giới hạn trạng thái vào các giá trị enum mà ứng dụng hỗ trợ.

Controller nhận model và bật validation:

```java
@GetMapping("/orders")
public PagedModel<EntityModel<OrderView>> searchOrders(
        @Valid @ModelAttribute OrderSearchCriteria criteria,
        @PageableDefault(size = 20, sort = "createdAt",
                direction = Sort.Direction.DESC) Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    validateDateRange(criteria);

    Page<Order> result = orderService.search(criteria, pageable);

    return pagedAssembler.toModel(result, orderModelAssembler);
}
```

Trong ứng dụng Spring MVC có Jakarta Bean Validation, `@Valid` yêu cầu kiểm tra các constraint trên model attribute. Khi validation thất bại, request thường kết thúc bằng 400. Quy tắc liên trường như `from` phải trước hoặc bằng `to` cần được kiểm tra bổ sung trong service, controller hoặc một class-level validator.

Ví dụ kiểm tra khoảng ngày:

```java
private void validateDateRange(OrderSearchCriteria criteria) {
    if (criteria.from().isAfter(criteria.to())) {
        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "'from' must be on or before 'to'"
        );
    }
}
```

Nếu dự án dùng Spring Framework hoặc cấu hình validation khác, hãy kiểm tra cơ chế kích hoạt method/model validation tương ứng. Đừng dựa vào annotation nếu Bean Validation provider chưa có trong ứng dụng.

## 4. Khai báo tham số bắt buộc trực tiếp bằng @RequestParam

Với endpoint nhỏ chỉ có một hoặc hai bộ lọc, khai báo trực tiếp có thể dễ đọc hơn request model:

```java
@GetMapping("/orders")
public PagedModel<EntityModel<OrderView>> searchOrders(
        @RequestParam("status") OrderStatus status,
        @RequestParam("from")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate from,
        @RequestParam("to")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate to,
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    if (from.isAfter(to)) {
        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "'from' must be on or before 'to'"
        );
    }

    Page<Order> result =
            orderService.search(status, from, to, pageable);

    return pagedAssembler.toModel(result, orderModelAssembler);
}
```

Vì `required` mặc định là `true`, cả ba tham số đều bắt buộc. Có thể ghi rõ `required = true` để hợp đồng dễ nhận biết khi đọc code:

```java
@RequestParam(name = "status", required = true) OrderStatus status
```

Dùng request model khi filter tăng lên hoặc cần validation tổng thể. Dùng `@RequestParam` trực tiếp khi số tham số nhỏ và từng tham số độc lập. Cả hai cách đều cần quy tắc xử lý rõ cho giá trị rỗng, không chuyển đổi được và điều kiện liên trường.

## 5. Áp dụng filter ở tầng truy vấn

Không nên nhận filter rồi bỏ qua khi gọi repository. Bộ lọc bắt buộc phải tham gia vào câu truy vấn thực tế để server chỉ trả những bản ghi thỏa tiêu chí.

Với Spring Data JPA, repository có thể mở rộng `JpaSpecificationExecutor`:

```java
public interface OrderRepository
        extends JpaRepository<Order, UUID>,
                JpaSpecificationExecutor<Order> {
}
```

Service xây dựng một specification từ các tiêu chí bắt buộc:

```java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Page<Order> search(
            OrderSearchCriteria criteria,
            Pageable pageable) {

        LocalDateTime start = criteria.from().atStartOfDay();
        LocalDateTime endExclusive =
                criteria.to().plusDays(1).atStartOfDay();

        Specification<Order> filter = (root, query, cb) -> cb.and(
                cb.equal(root.get("status"), criteria.status()),
                cb.greaterThanOrEqualTo(
                        root.<LocalDateTime>get("createdAt"), start),
                cb.lessThan(
                        root.<LocalDateTime>get("createdAt"), endExclusive)
        );

        return repository.findAll(filter, pageable);
    }
}
```

Khoảng ngày được chuyển thành khoảng thời gian nửa mở: từ đầu ngày `from` (bao gồm) đến đầu ngày sau `to` (không bao gồm). Cách này bao gồm toàn bộ ngày kết thúc mà không cần đoán độ chính xác phần mili giây hoặc nano giây của cột thời gian.

Nếu trường database là `LocalDate` thay vì `LocalDateTime`, hãy dùng phép so sánh ngày trực tiếp. Nếu dữ liệu lưu UTC hoặc có múi giờ, cần xác định múi giờ nghiệp vụ trước khi chuyển ngày thành thời điểm.

Bộ lọc bắt buộc nên được kết hợp bằng điều kiện AND nếu hợp đồng yêu cầu tất cả tiêu chí cùng thỏa mãn. Nếu API có bộ lọc tùy chọn, chỉ thêm predicate khi tham số tương ứng được cung cấp.

## 6. Kết hợp filter với Pageable và HAL

Bộ lọc xác định tập kết quả; `Pageable` xác định phần nào của tập kết quả đó được trả về. Hai khái niệm cần phối hợp trong cùng truy vấn:

```java
@GetMapping(value = "/orders", produces = MediaTypes.HAL_JSON_VALUE)
public PagedModel<EntityModel<OrderView>> searchOrders(
        @Valid @ModelAttribute OrderSearchCriteria criteria,
        @PageableDefault(size = 20, sort = "createdAt",
                direction = Sort.Direction.DESC) Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    validateDateRange(criteria);

    Page<Order> page = orderService.search(criteria, pageable);

    return pagedAssembler.toModel(page, orderModelAssembler);
}
```

Response HAL có thể có dạng:

```json
{
  "_embedded": {
    "orders": [
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
    "self": {
      "href": "/orders?status=PENDING&from=2026-10-01&to=2026-10-31&page=0&size=20"
    },
    "next": {
      "href": "/orders?status=PENDING&from=2026-10-01&to=2026-10-31&page=1&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 37,
    "totalPages": 2,
    "number": 0
  }
}
```

Các link phân trang phải tiếp tục đại diện cho cùng tập kết quả. Khi client theo `next`, các filter bắt buộc như `status`, `from` và `to` cần được giữ lại. Nếu link mất một filter, request tiếp theo có thể trả một tập dữ liệu khác hoặc bị từ chối vì thiếu tham số.

`PagedResourcesAssembler` tạo `PagedModel` và link điều hướng dựa trên request cùng pageable resolver. Hãy xác nhận response thực tế giữ các query parameters của filter, đặc biệt khi ứng dụng dùng custom resolver, filter object hoặc cơ chế tạo link riêng.

## 7. Công bố cách tìm kiếm cho client

Nếu endpoint yêu cầu nhiều filter, client cần biết những trường nào phải gửi trước khi gọi. Có thể tài liệu hóa query parameters trong OpenAPI, hoặc công bố một link tìm kiếm có URI template.

Ví dụ link HAL templated:

```json
{
  "_links": {
    "search": {
      "href": "/orders{?status,from,to,page,size,sort}",
      "templated": true
    }
  }
}
```

URI template cho biết các biến truy vấn mà client có thể mở rộng. Tuy nhiên, cú pháp template tự nó không thể hiện đầy đủ trường nào bắt buộc và quy tắc validation nào áp dụng. Cần tài liệu hóa required fields hoặc công bố template có metadata đầu vào.

Nếu client cần một biểu mẫu có thể khám phá, HAL-FORMS có thể mô tả template tìm kiếm với các property bắt buộc:

```java
Link search = linkTo(methodOn(OrderController.class)
        .searchOrders(null, Pageable.unpaged(), null))
        .withRel("search");

Link searchForm = Affordances.of(search)
        .afford(methodOn(OrderController.class)
                .searchOrders(null, Pageable.unpaged(), null))
        .withInput(OrderSearchCriteria.class)
        .withName("search")
        .toLink();
```

Ví dụ minh họa cách gắn input type vào affordance tìm kiếm; chữ ký phương thức và đối số placeholder cần điều chỉnh theo controller thực tế. Để template mô tả chính xác các trường bắt buộc, DTO input cần có metadata validation như `@NotNull` hoặc `@NotBlank`, và endpoint phải hỗ trợ HAL-FORMS trong content negotiation.

HAL-FORMS giúp client khám phá các property của template, nhưng server vẫn phải validate request khi nhận. Metadata chỉ hướng dẫn client tạo request đúng; nó không thay thế ràng buộc ở controller và service.

## 8. Phân biệt filter nghiệp vụ với phân quyền

Một filter bắt buộc không tự tạo ra ranh giới bảo mật. Ví dụ, yêu cầu `customerId` hoặc `tenantId` trong query string không có nghĩa client được phép xem dữ liệu thuộc khách hàng hoặc tenant đó.

Không nên dựa vào filter do client gửi để quyết định quyền truy cập:

```java
// Không dùng query parameter như một bằng chứng phân quyền.
@GetMapping("/orders")
public Page<Order> getOrders(
        @RequestParam UUID tenantId,
        Pageable pageable) {
    return repository.findByTenantId(tenantId, pageable);
}
```

Nếu dữ liệu được phân vùng theo người dùng hoặc tenant, hãy lấy phạm vi được phép từ principal hoặc security context, rồi kết hợp nó vào truy vấn:

```java
UUID tenantId = currentUser.requireTenantId();

return repository.findByTenantIdAndStatus(
        tenantId,
        criteria.status(),
        pageable
);
```

Trong ví dụ, `currentUser` là thành phần ứng dụng lấy tenant đã xác thực. Client có thể gửi filter nghiệp vụ như trạng thái hoặc khoảng ngày, nhưng server tự xác định tenant mà người dùng được phép truy cập.

Nguyên tắc:

- Filter xác định dữ liệu client muốn tìm trong phạm vi được phép.
- Authorization xác định client được phép truy cập phạm vi dữ liệu nào.
- Server phải kiểm tra quyền ở mọi request, kể cả khi client theo một link đã nhận trước đó.
- Không công bố dữ liệu hoặc embedded resource vượt quá quyền của principal hiện tại.

## 9. Kiểm soát sort và kích thước trang

Khi kết hợp filter bắt buộc với phân trang, vẫn cần giới hạn các tham số điều khiển truy vấn:

```yaml
spring:
  data:
    web:
      pageable:
        default-page-size: 20
        max-page-size: 100
```

Giới hạn kích thước trang giúp tránh client yêu cầu hàng chục nghìn bản ghi trong một response. Với sort, chỉ cho phép các thuộc tính được API công bố. Ví dụ:

```java
private static final Set<String> ALLOWED_SORTS =
        Set.of("createdAt", "total", "status");

private void validateSort(Pageable pageable) {
    boolean unsupported = pageable.getSort().stream()
            .anyMatch(order -> !ALLOWED_SORTS.contains(order.getProperty()));

    if (unsupported) {
        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Unsupported sort property"
        );
    }
}
```

Gọi `validateSort(pageable)` trước khi truy vấn. Không nối trực tiếp chuỗi `sort` từ request vào SQL. Spring Data nhận `Sort` có cấu trúc, nhưng API vẫn nên giới hạn thuộc tính mà client được phép sắp xếp.

Với filter có chi phí cao, cân nhắc giới hạn khoảng thời gian tối đa hoặc yêu cầu thêm tiêu chí phân vùng nghiệp vụ. Các giới hạn đó cần được mô tả rõ trong hợp đồng để client biết cách tạo request hợp lệ.

## 10. Kiểm thử bộ lọc bắt buộc bằng MockMvc

Kiểm thử cần xác nhận request hợp lệ trả dữ liệu đúng, còn request thiếu hoặc sai filter bị từ chối.

Ví dụ request hợp lệ:

```java
mockMvc.perform(get("/orders")
        .param("status", "PENDING")
        .param("from", "2026-10-01")
        .param("to", "2026-10-31")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href")
            .value(containsString("status=PENDING")))
    .andExpect(jsonPath("$._links.self.href")
            .value(containsString("from=2026-10-01")))
    .andExpect(jsonPath("$._links.next.href").exists());
```

Test này giả định có đủ dữ liệu để tồn tại trang tiếp theo. Nếu chỉ có một trang, không nên yêu cầu relation `next`.

Kiểm tra thiếu filter bắt buộc:

```java
mockMvc.perform(get("/orders")
        .param("from", "2026-10-01")
        .param("to", "2026-10-31")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isBadRequest());
```

Kiểm tra khoảng ngày không hợp lệ:

```java
mockMvc.perform(get("/orders")
        .param("status", "PENDING")
        .param("from", "2026-10-31")
        .param("to", "2026-10-01")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isBadRequest());
```

Kiểm tra giá trị enum không hợp lệ:

```java
mockMvc.perform(get("/orders")
        .param("status", "UNKNOWN")
        .param("from", "2026-10-01")
        .param("to", "2026-10-31")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isBadRequest());
```

Nên bổ sung kiểm thử:

1. Giá trị rỗng hoặc chỉ chứa khoảng trắng bị từ chối.
2. Ngày sai định dạng bị trả lỗi 400.
3. Filter thực sự được áp dụng trong kết quả repository, không chỉ xuất hiện trong link.
4. Link `self` và `next` giữ nguyên toàn bộ filter bắt buộc.
5. Sort không nằm trong allowlist bị từ chối.
6. Kích thước trang vượt giới hạn được xử lý theo cấu hình.
7. Người dùng không có quyền không thể đọc dữ liệu ngoài phạm vi được cấp, kể cả khi tự sửa filter.

## 11. Những lỗi thường gặp

**Dùng `required = false` cho filter mà nghiệp vụ yêu cầu.** Endpoint có thể chạy truy vấn rộng khi client bỏ qua tiêu chí. Đặt tham số bắt buộc hoặc validate request model.

**Cho rằng required đồng nghĩa non-empty.** Tham số có thể hiện diện nhưng rỗng. Dùng enum, constraint hoặc validation tường minh cho giá trị.

**Chỉ kiểm tra filter ở controller nhưng không đưa vào truy vấn.** Response có thể chứa dữ liệu không phù hợp. Đảm bảo mọi filter bắt buộc tham gia specification hoặc repository query.

**Tự ghép link phân trang.** Link tiếp theo có thể mất filter, sort hoặc context path. Dùng `PagedResourcesAssembler` và kiểm thử href thực tế.

**Nhầm filter với authorization.** Client có thể sửa `tenantId` hoặc `customerId`. Lấy phạm vi quyền từ principal và áp dụng ở server.

**Không kiểm tra quan hệ giữa các filter.** Từng giá trị có thể hợp lệ riêng nhưng kết hợp lại không hợp lệ, ví dụ `from` sau `to`. Thêm validation liên trường.

**Không giới hạn sort và size.** Client có thể yêu cầu truy vấn tốn kém hoặc sắp xếp theo thuộc tính nội bộ. Whitelist sort và cấu hình max page size.

**Công bố URI template nhưng không nói trường nào bắt buộc.** Template liệt kê biến URI, không tự định nghĩa đầy đủ validation. Dùng tài liệu API hoặc HAL-FORMS metadata để công bố yêu cầu.

## 12. Nguyên tắc thiết kế

- Xác định rõ filter nào bắt buộc và filter nào tùy chọn.
- Phân biệt tham số thiếu, rỗng, sai định dạng và không thỏa điều kiện nghiệp vụ.
- Dùng `@RequestParam` cho endpoint nhỏ hoặc `@ModelAttribute` với DTO khi có nhiều tiêu chí.
- Dùng Bean Validation cho giá trị bắt buộc và kiểm tra liên trường trong service hoặc validator.
- Áp dụng filter thật sự trong truy vấn repository.
- Kết hợp filter với `Pageable` và `PagedResourcesAssembler` để tạo HAL có link điều hướng.
- Bảo đảm link phân trang giữ nguyên filter, sort và các tiêu chí tìm kiếm.
- Tách filter nghiệp vụ khỏi authorization; lấy tenant/phạm vi truy cập từ security context.
- Giới hạn kích thước trang và whitelist thuộc tính sort.
- Kiểm thử request hợp lệ, thiếu filter, giá trị sai và link HAL qua MockMvc.

## Kết luận

Bộ lọc bắt buộc xác định những điều kiện client phải cung cấp trước khi server thực hiện truy vấn collection. Spring MVC hỗ trợ kiểm tra sự hiện diện bằng `@RequestParam` và bind nhiều tiêu chí qua `@ModelAttribute`; Bean Validation cùng service xử lý giá trị rỗng, sai định dạng và quy tắc liên trường. Khi kết hợp với `Pageable` và `PagedResourcesAssembler`, response HAL cần giữ filter trong các link điều hướng để client tiếp tục duyệt cùng tập kết quả. Hãy luôn áp dụng filter trong truy vấn, tách nó khỏi authorization và kiểm thử các trường hợp lỗi như một phần hợp đồng API.

## Tài liệu tham khảo

- [Spring Framework Reference – Request Parameters and Model Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring Data Commons Reference – Web Support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)
- [Spring HATEOAS Reference – Pagination](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.paged-resources)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)

