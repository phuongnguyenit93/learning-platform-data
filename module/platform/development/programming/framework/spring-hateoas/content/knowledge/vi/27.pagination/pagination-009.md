# Giới hạn kích thước trang trong Spring HATEOAS

Phân trang giúp API trả về một phần dữ liệu trong mỗi response thay vì tải toàn bộ collection. Tuy nhiên, nếu client được tự do yêu cầu kích thước trang quá lớn, một request có thể khiến database đọc nhiều bản ghi, ứng dụng tạo representation lớn và Jackson phải serialize một lượng JSON đáng kể. Vì vậy, API cần xác định kích thước trang mặc định và giới hạn tối đa mà server chấp nhận.

Trong Spring Data Web, tham số `Pageable` được phân giải từ query parameter như `page` và `size`. Spring Data cung cấp cấu hình `defaultPageSize` và `maxPageSize` để đặt giá trị mặc định và giới hạn kích thước được chấp nhận. Spring HATEOAS dùng kết quả `Page` đó để tạo `PagedModel`, page metadata và các link điều hướng. Khi giới hạn được áp dụng đúng từ đầu, metadata và link phản ánh kích thước trang thực tế mà server đã xử lý.

## 1. Kích thước trang là gì?

Kích thước trang (`size`) là số phần tử tối đa mà client yêu cầu trong một trang. Ví dụ:

```http
GET /orders?page=0&size=20
```

Request yêu cầu trang đầu tiên với tối đa 20 đơn hàng. `page` thường được đánh số từ `0`; `size` xác định số phần tử tối đa trong một trang.

Kích thước trang không phải tổng số bản ghi của collection và cũng không phải số item luôn xuất hiện trong response. Nếu trang cuối chỉ còn 3 đơn hàng, response có 3 item nhưng kích thước trang vẫn có thể là 20.

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | ---: | --- |
| `page` | `2` | Chỉ số trang thứ ba theo cách đánh số từ 0. |
| `size` | `20` | Tối đa 20 item trong một trang. |
| Số item thực tế | `7` | Số phần tử thực sự có trong trang hiện tại. |
| `totalElements` | `47` | Tổng số phần tử phù hợp với truy vấn. |
| `totalPages` | `3` | Tổng số trang theo kích thước trang và kết quả. |

## 2. Vì sao cần giới hạn kích thước trang?

Nếu API cho phép `size=1000000`, một request có thể yêu cầu quá nhiều dữ liệu. Điều này làm tăng chi phí ở nhiều tầng:

- Database phải đọc, sắp xếp và trả về nhiều bản ghi hơn.
- Ứng dụng phải giữ nhiều object trong bộ nhớ khi ánh xạ sang DTO và representation model.
- Assembler tạo link cho từng item.
- Jackson phải serialize payload lớn hơn.
- Network truyền response lớn, làm tăng độ trễ và băng thông.
- Một client lỗi hoặc cố ý gửi request lớn có thể gây quá tải tài nguyên.

Giới hạn page size là một biện pháp kiểm soát tài nguyên. Nó không thay thế index database, giới hạn thời gian truy vấn, kiểm soát sort/filter hoặc rate limiting, nhưng giúp chặn một nguồn tải lớn ngay tại ranh giới HTTP.

## 3. Phân biệt default page size và maximum page size

Hai cấu hình có mục đích khác nhau:

| Cấu hình | Vai trò | Ví dụ |
| --- | --- | --- |
| Default page size | Kích thước dùng khi client không gửi tham số `size`. | `20` |
| Maximum page size | Mức trần server cho phép khi client yêu cầu kích thước lớn hơn. | `100` |

Giả sử server cấu hình mặc định là 20 và tối đa là 100:

| Request | Kích thước được xử lý |
| --- | ---: |
| Không có `size` | 20 |
| `size=10` | 10 |
| `size=100` | 100 |
| `size=5000` | Bị giới hạn ở 100 |

Spring Data Web có thể chuẩn hóa hoặc giới hạn giá trị đầu vào khi tạo `Pageable`. Hãy kiểm thử hành vi thực tế của phiên bản và cấu hình ứng dụng, đặc biệt với `size=0`, số âm hoặc giá trị không hợp lệ.

## 4. Cấu hình trong Spring Boot bằng application.yml

Với ứng dụng Spring Boot có Spring Data Web, có thể cấu hình kích thước mặc định và tối đa trong `application.yml`:

```yaml
spring:
  data:
    web:
      pageable:
        default-page-size: 20
        max-page-size: 100
```

Trong ví dụ:

- Request không truyền `size` sẽ dùng kích thước mặc định 20.
- Request truyền `size` lớn hơn 100 sẽ bị giới hạn ở 100 bởi resolver.
- Request truyền `size` nhỏ hơn giới hạn vẫn được xử lý theo giá trị client yêu cầu, nếu hợp lệ.

Đặt giới hạn ở resolver giúp mọi controller dùng `Pageable` tuân theo chính sách chung. Điều này hữu ích khi API có nhiều endpoint phân trang và cần một mức trần thống nhất.

Tên property và hành vi có thể phụ thuộc phiên bản Spring Boot/Spring Data. Nếu ứng dụng không dùng auto-configuration của Boot, cần cấu hình resolver bằng Java theo cách phù hợp với Spring Data Web.

## 5. Cấu hình bằng PageableHandlerMethodArgumentResolverCustomizer

Khi cần cấu hình bằng Java, Spring Data Web cung cấp `PageableHandlerMethodArgumentResolverCustomizer` để tùy chỉnh resolver:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.web.config.PageableHandlerMethodArgumentResolverCustomizer;

@Configuration
class PaginationConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pageableCustomizer() {
        return resolver -> {
            resolver.setFallbackPageable(PageRequest.of(0, 20));
            resolver.setMaxPageSize(100);
        };
    }
}
```

`setFallbackPageable(...)` xác định `Pageable` được dùng khi request không cung cấp thông tin phân trang phù hợp. `setMaxPageSize(100)` đặt mức trần cho kích thước trang được resolver chấp nhận.

Chọn cấu hình property hoặc customizer theo nhu cầu. Không cần cấu hình cùng một chính sách ở nhiều nơi nếu không có lý do; nếu có nhiều nguồn cấu hình, hãy xác nhận thứ tự ưu tiên và kết quả cuối cùng trong integration test.

## 6. @PageableDefault chỉ đặt giá trị mặc định

Có thể dùng `@PageableDefault` trên tham số controller để đặt page size mặc định cho endpoint:

```java
@GetMapping
PagedModel<EntityModel<OrderView>> all(
        @PageableDefault(size = 20, sort = "createdAt",
                direction = Sort.Direction.DESC) Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.findAll(pageable);
    return pagedAssembler.toModel(page, assembler);
}
```

Annotation này được dùng khi request không chỉ định giá trị tương ứng. Nó không phải giới hạn tối đa. Nếu client gửi `?size=5000`, giới hạn vẫn cần được đặt ở `PageableHandlerMethodArgumentResolver` hoặc được kiểm tra bổ sung trong tầng ứng dụng.

Đây là khác biệt quan trọng: `@PageableDefault(size = 20)` không bảo vệ endpoint khỏi request có page size rất lớn. Dùng `max-page-size` hoặc `setMaxPageSize(...)` để đặt mức trần.

## 7. Dùng Pageable với repository và PagedResourcesAssembler

Controller nên nhận `Pageable`, truyền nó xuống service/repository và chuyển kết quả `Page<T>` thành `PagedModel<T>` bằng `PagedResourcesAssembler`.

Repository:

```java
interface OrderRepository extends JpaRepository<Order, UUID> {
    Page<Order> findByStatus(OrderStatus status, Pageable pageable);
}
```

Service:

```java
@Service
class OrderService {

    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    Page<Order> findByStatus(OrderStatus status, Pageable pageable) {
        return repository.findByStatus(status, pageable);
    }
}
```

Controller:

```java
@GetMapping
PagedModel<EntityModel<OrderView>> all(
        @RequestParam(required = false) OrderStatus status,
        @PageableDefault(size = 20) Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = status == null
            ? orderService.findAll(pageable)
            : orderService.findByStatus(status, pageable);

    return pagedAssembler.toModel(page, assembler);
}
```

Resolver đã áp dụng default và maximum page size trước khi `Pageable` được truyền tới controller. Repository nhận page request đã chuẩn hóa, do đó database không bị yêu cầu trả về số item vượt quá giới hạn đã cấu hình.

Ví dụ trên giả định service có cả `findAll(Pageable)` và `findByStatus(...)`. Khi API hỗ trợ filter, các link phân trang cần giữ lại điều kiện lọc để client không vô tình chuyển sang một tập kết quả khác.

## 8. Page size được phản ánh trong PagedModel như thế nào?

Khi `PagedResourcesAssembler` chuyển `Page<T>` thành `PagedModel<T>`, page metadata được tạo từ kết quả trang. Trường `page.size` phản ánh kích thước của trang đã được thực hiện; các link `self`, `next`, `prev`, `first` và `last` được tạo theo thông tin phân trang và request.

Ví dụ HAL JSON minh họa:

```json
{
  "_embedded": {
    "orders": []
  },
  "_links": {
    "self": { "href": "/orders?page=0&size=100" },
    "next": { "href": "/orders?page=1&size=100" }
  },
  "page": {
    "size": 100,
    "number": 0,
    "totalElements": 240,
    "totalPages": 3
  }
}
```

Đây là ví dụ cấu trúc; collection thực tế có thể chứa item và các link phụ thuộc vào trang hiện tại. Nếu client gửi `size=5000` nhưng server giới hạn ở 100, response và link phân trang cần phản ánh page size hiệu lực. Client nên theo link `next` thay vì tự ghép URI.

## 9. Giới hạn page size ở tầng service khi cần bảo vệ nhiều caller

Resolver bảo vệ các request đi qua Spring MVC argument resolution. Tuy nhiên, service có thể được gọi từ scheduler, message listener, batch job hoặc một thành phần khác không đi qua controller. Nếu mọi caller cần tuân thủ cùng giới hạn, có thể áp dụng chính sách ở tầng service hoặc một thành phần tạo `Pageable` dùng chung.

Ví dụ helper cho một `Pageable` đã được phân trang:

```java
Pageable limitPageSize(Pageable requested, int maximum) {
    if (requested.isUnpaged()) {
        return PageRequest.of(0, maximum, requested.getSort());
    }

    int effectiveSize = Math.min(requested.getPageSize(), maximum);
    return PageRequest.of(
            requested.getPageNumber(),
            effectiveSize,
            requested.getSort()
    );
}
```

Helper này là ví dụ chính sách ở tầng ứng dụng; cần quyết định rõ cách xử lý `Pageable.unpaged()` trong nghiệp vụ. Có hệ thống nên từ chối unpaged request thay vì tự đổi thành trang đầu. Không nên âm thầm thay đổi semantics nếu caller đang mong đợi toàn bộ kết quả.

Nếu resolver đã giới hạn size cho request HTTP, service guard có thể là lớp bảo vệ bổ sung cho caller khác. Hãy tránh sao chép cùng một hằng số ở nhiều nơi; đặt giới hạn trong cấu hình hoặc policy dùng chung để không bị lệch.

## 10. Giới hạn toàn cục và giới hạn theo endpoint

`max-page-size` ở resolver thường là giới hạn chung cho các tham số `Pageable` được xử lý bởi resolver đó. Một số endpoint có thể cần giới hạn thấp hơn do payload nặng hoặc truy vấn tốn kém.

Ví dụ:

| Endpoint | Default | Maximum phù hợp trong ví dụ |
| --- | ---: | ---: |
| `GET /orders` | 20 | 100 |
| `GET /orders/{id}/events` | 10 | 50 |
| `GET /audit-logs` | 25 | 100 |
| `GET /reports/rows` | 10 | 25 |

`@PageableDefault` có thể đặt default khác nhau cho từng endpoint, nhưng không đặt được max riêng. Nếu cần max khác nhau, có thể:

- Nhận `page` và `size` tường minh bằng `@RequestParam`, validate giới hạn theo endpoint rồi tạo `PageRequest`.
- Tạo argument resolver hoặc policy riêng cho nhóm endpoint cần giới hạn đặc biệt.
- Chuẩn hóa `Pageable` trong tầng service bằng một policy nhận max phù hợp.

Với tham số tường minh, cần kiểm tra `page >= 0`, `1 <= size <= endpointMax` và xử lý lỗi theo hợp đồng API. Nếu dùng Bean Validation trên method parameter, phải bật method validation tương ứng trong ứng dụng.

## 11. Page size limit không giới hạn page number hoặc offset

Giới hạn `size` chỉ kiểm soát số item trong một trang. Nó không tự giới hạn chỉ số trang hoặc offset. Một request như `?page=10000000&size=20` vẫn có thể khiến database phải xử lý offset lớn, tùy loại database, query và index.

Với collection rất lớn, offset pagination có thể chậm khi page number tăng cao. Có thể cân nhắc:

- Giới hạn page depth nếu nghiệp vụ cho phép.
- Dùng keyset/seek pagination dựa trên khóa sắp xếp ổn định.
- Dùng cursor hoặc token tiếp tục thay vì số trang.
- Bảo đảm sort có index và có tiêu chí phụ ổn định để tránh item nhảy trang.

Đừng xem max page size là biện pháp đầy đủ để bảo vệ mọi truy vấn phân trang. Cần đánh giá cả query plan, sort, filter, offset và kích thước representation.

## 12. Giới hạn sort và filter đi cùng page size

Một request nhỏ vẫn có thể tốn kém nếu client yêu cầu sort trên cột không có index hoặc filter phức tạp. Vì vậy, API nên kiểm soát các tiêu chí sort được phép và validate filter.

Ví dụ request:

```http
GET /orders?page=0&size=20&sort=createdAt,desc
```

Hãy xác định danh sách thuộc tính sort được phép như `createdAt`, `status` hoặc `id`. Không nên cho client tùy ý sort theo mọi field entity, đặc biệt khi một số field liên quan tới quan hệ hoặc biểu thức truy vấn đắt đỏ.

Khi xây dựng pagination links, phải giữ sort và filter hiện tại. `PagedResourcesAssembler` có thể dùng request context để tạo link, nhưng vẫn cần kiểm tra response khi controller có query parameter tùy chỉnh hoặc URI mapping phức tạp.

## 13. Xử lý page size không hợp lệ

API cần có hành vi rõ ràng với các giá trị như:

- Không truyền `size`: dùng default.
- `size` nhỏ hơn hoặc bằng 0: chuẩn hóa hoặc từ chối theo chính sách.
- `size` lớn hơn max: giới hạn về max hoặc trả lỗi nếu hợp đồng chọn cách từ chối.
- `size` không phải số: trả lỗi binding theo cơ chế của Spring MVC hoặc ánh xạ thành lỗi API có cấu trúc.
- `page` âm hoặc quá lớn: xử lý theo chính sách page resolver và ứng dụng.

Spring Data resolver thường chuẩn hóa một số đầu vào và giới hạn giá trị vượt max. Nếu muốn API trả `400 Bad Request` thay vì âm thầm clamp, hãy tự validate tham số hoặc xây resolver phù hợp. Điều quan trọng là hành vi phải nhất quán và được tài liệu hóa; client cần biết server đang giới hạn hay từ chối yêu cầu.

## 14. Kiểm thử default và maximum page size bằng MockMvc

Kiểm thử HTTP giúp xác nhận resolver đã áp dụng cấu hình trước khi truy vấn và response có metadata đúng. Ví dụ giả sử default là 20, max là 100:

```java
@Test
void usesDefaultPageSizeWhenSizeIsMissing() throws Exception {
    mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page.size").value(20));
}

@Test
void capsRequestedPageSizeAtConfiguredMaximum() throws Exception {
    mockMvc.perform(get("/orders")
                    .param("page", "0")
                    .param("size", "5000")
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page.size").value(100));
}
```

Test giả định controller trả `PagedModel` và HAL được cấu hình. Nếu API chọn trả lỗi cho size vượt mức thay vì clamp, assertion thứ hai cần kiểm tra status lỗi theo hợp đồng.

Nên kiểm tra thêm repository nhận `Pageable` với page size hiệu lực. Có thể dùng mock/argument captor để xác nhận service không truyền giá trị lớn hơn max xuống repository. Với integration test database, xác nhận số item trong content không vượt page size và link phân trang giữ `size=100`.

## 15. Kiểm thử biên và link điều hướng

Ngoài hai trường hợp default và max, hãy kiểm tra các trường hợp biên:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| `size=1` | Trang chỉ chứa tối đa một item. |
| `size=max` | Server chấp nhận đúng mức trần. |
| `size=max+1` | Server clamp hoặc từ chối theo hợp đồng. |
| `size=0` | Hành vi chuẩn hóa hoặc lỗi được xác định rõ. |
| `size=-1` | Không tạo truy vấn unbounded ngoài ý muốn. |
| Không có kết quả | Page metadata và link tuân theo hợp đồng collection rỗng. |
| Trang cuối | Content có thể ít hơn `size`, metadata vẫn đúng. |
| Có filter/sort | Các link `next` và `prev` giữ ngữ cảnh truy vấn. |

Ví dụ kiểm tra link next có giữ kích thước trang:

```java
mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "100")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.next.href", containsString("size=100")));
```

Nếu link URI được mã hóa hoặc thứ tự query parameter thay đổi, kiểm tra bằng cách parse URI thay vì so sánh toàn bộ chuỗi. Mục tiêu là xác nhận `size` và filter/sort cần thiết vẫn được giữ.

## 16. Các lỗi thường gặp

**Chỉ dùng `@PageableDefault` rồi nghĩ đã có max.** Annotation đặt default, không giới hạn giá trị client yêu cầu. Cấu hình `max-page-size` ở resolver.

**Chỉ giới hạn ở giao diện client.** Client có thể gửi request trực tiếp. Server phải áp dụng giới hạn ở resolver hoặc tầng ứng dụng.

**Trả `Page<T>` trực tiếp và bỏ qua representation hypermedia.** Dùng `PagedResourcesAssembler` để tạo `PagedModel`, metadata và link điều hướng.

**Quên giữ page size trong link.** Client có thể chuyển sang trang tiếp theo với kích thước mặc định hoặc khác mong muốn. Kiểm thử link `next` và `prev`.

**Cho rằng max page size giới hạn page number.** Nó chỉ giới hạn số item mỗi trang; offset lớn vẫn có thể tốn kém.

**Cho phép sort/filter không kiểm soát.** Page size nhỏ không đảm bảo query rẻ. Hãy giới hạn thuộc tính sort và validate filter.

**Chỉ bảo vệ controller nhưng bỏ qua service caller khác.** Nếu service có thể được gọi từ batch hoặc message listener, cân nhắc policy ở tầng service.

**Không xác định hành vi size sai.** Hãy quyết định clamp hay trả lỗi và kiểm thử các giá trị 0, âm, quá lớn và không phải số.

## 17. Bài tập thực hành và tiêu chí hoàn thành

Hãy cấu hình API đơn hàng với page size mặc định 20 và tối đa 100:

1. Cấu hình `spring.data.web.pageable.default-page-size` thành `20`.
2. Cấu hình `spring.data.web.pageable.max-page-size` thành `100`.
3. Tạo endpoint nhận `Pageable` và trả `PagedModel` bằng `PagedResourcesAssembler`.
4. Dùng `@PageableDefault(size = 20)` nếu endpoint cần default riêng.
5. Gửi request không có `size`, `size=10`, `size=100` và `size=5000`.
6. Xác nhận page size hiệu lực và `page.size` trong HAL response.
7. Kiểm tra link `next`/`prev` giữ `size`, filter và sort.
8. Kiểm thử size bằng 0, số âm và giá trị không phải số theo chính sách API.
9. Đánh giá query với page number lớn và giới hạn sort/filter được phép.
10. Nếu service được gọi từ ngoài HTTP, áp dụng policy giới hạn tương ứng hoặc từ chối unpaged request.

Bạn đã nắm được cách giới hạn kích thước trang khi có thể phân biệt default với maximum, cấu hình resolver, hiểu vai trò của `@PageableDefault`, truyền `Pageable` đã chuẩn hóa xuống repository, tạo `PagedModel` bằng `PagedResourcesAssembler` và kiểm thử page metadata cùng pagination links. Giới hạn rõ ràng giúp API giữ response ở kích thước dự đoán được và giảm nguy cơ một request làm tiêu tốn quá nhiều tài nguyên.

## Tài liệu tham khảo chính thức

- [Spring Data Web – PageableHandlerMethodArgumentResolver API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableHandlerMethodArgumentResolver.html)
- [Spring Data Web – PageableHandlerMethodArgumentResolverCustomizer API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/config/PageableHandlerMethodArgumentResolverCustomizer.html)
- [Spring Data Commons Reference Documentation – Web support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)
- [Spring HATEOAS Reference Documentation – Paged resources](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.paged-resources)
