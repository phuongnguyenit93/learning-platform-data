# @PageableDefault, @SortDefault và giá trị dự phòng

## 1. Mặc định của tham số web nằm ở đâu?

Trong chương **Tham số web** của module **SPRING_DATA_COMMONS**, hai annotation `@PageableDefault` và `@SortDefault` giúp một endpoint có hành vi xác định khi client không gửi đủ thông tin phân trang hoặc sắp xếp.

Ví dụ, API danh sách đơn hàng cần trả trang đầu, mỗi trang 25 phần tử, ưu tiên đơn mới nhất. Client vẫn có thể yêu cầu trang khác hoặc cách sắp xếp khác theo hợp đồng API.

Luồng xử lý cần phân biệt:

~~~text
Query string của HTTP request
    → argument resolver của Spring Data Web
    → Pageable hoặc Sort
    → controller/service
    → repository và khả năng truy vấn của store
~~~

Các annotation này cấu hình **đầu vào của controller**. Chúng không tự giới hạn mọi lời gọi repository, không quyết định cơ chế auditing và không bảo đảm mọi kho dữ liệu đều thực thi được mọi cách sort.

Bài viết dùng Spring MVC với Spring Data Web đã được đăng ký. Trong ứng dụng cấu hình thủ công, có thể bật hỗ trợ bằng `@EnableSpringDataWebSupport`; với Spring Boot, cần xác nhận cấu hình tự động tương ứng đang hoạt động. Các trường hợp biên về parsing bên dưới được minh họa theo resolver chuẩn của Spring Data Commons **3.5.1**, không giả định phiên bản của dự án đang dùng. [Spring Data Web support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)

## 2. Phân biệt ba loại giá trị mặc định

| Cơ chế | Phạm vi | Ý nghĩa |
| --- | --- | --- |
| `@PageableDefault` | Một tham số `Pageable` | Khai báo page, size và có thể khai báo sort mặc định |
| `@SortDefault` | Một tham số `Sort`, hoặc phần sort của `Pageable` | Khai báo property, direction và tùy chọn sort mặc định |
| Fallback trên resolver | Các tham số do resolver đó xử lý | Cung cấp giá trị khi không có khai báo cục bộ tương ứng |

Mặc định của annotation không đồng nhất với mặc định của resolver:

- `@PageableDefault` không ghi thuộc tính nào có `page = 0`, `size = 10`, không khai báo property sort.
- Resolver chuẩn không có annotation hoặc tùy biến dùng fallback tương đương `PageRequest.of(0, 20)`.

Vì vậy, thêm `@PageableDefault` trống có thể đổi kích thước trang từ 20 thành 10. Khi muốn hợp đồng API rõ ràng, nên viết `size` tường minh. [API PageableDefault](https://docs.spring.io/spring-data/commons/docs/3.5.1/api/org/springframework/data/web/PageableDefault.html), [mặc định của web resolver](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)

## 3. Dùng @PageableDefault cho một endpoint

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;

// Phần chữ ký của một controller method.
public void list(
        @PageableDefault(
                page = 0,
                size = 25,
                sort = {"createdAt", "id"},
                direction = Sort.Direction.DESC)
        Pageable pageable) {

    // Chuyển pageable vào service truy vấn phù hợp.
}
~~~

Các giá trị được ghi trên annotation trở thành mặc định tại tham số đó:

| Thuộc tính | Cách đọc |
| --- | --- |
| `page = 0` | Trang đầu trong mô hình đánh số nội bộ từ 0 |
| `size = 25` | Dùng 25 phần tử khi request thiếu size |
| `sort = {"createdAt", "id"}` | Ưu tiên createdAt, sau đó id |
| `direction = DESC` | Cùng áp dụng DESC cho cả hai property |

`value` là alias của `size`, nên `@PageableDefault(25)` có thể dùng được; cách viết `size = 25` dễ đọc hơn khi có nhiều thuộc tính. Không đặt hai alias với giá trị mâu thuẫn. [Khai báo PageableDefault](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableDefault.html)

Cần chú ý `size = 25` là mặc định, không phải kích thước tối đa. Nếu hợp đồng cho phép, request `?size=60` vẫn có thể nhận page size bằng 60.

Về nghiệp vụ, một mặc định hữu ích nên trả được dữ liệu có ý nghĩa khi người dùng mở màn hình lần đầu. Đối với danh sách đơn hàng, trang đầu theo thời gian giảm dần thường dễ hiểu hơn một trang mặc định ở giữa tập kết quả.

## 4. Dùng @SortDefault khi mỗi property có direction riêng

Một `direction` trong `@PageableDefault` áp dụng chung cho danh sách property. Nếu cần `createdAt DESC` nhưng `id ASC`, tách khai báo sort:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.SortDefault;

public void list(
        @PageableDefault(page = 0, size = 25)
        @SortDefault.SortDefaults({
                @SortDefault(
                        sort = "createdAt",
                        direction = Sort.Direction.DESC),
                @SortDefault(
                        sort = "id",
                        direction = Sort.Direction.ASC)
        })
        Pageable pageable) {

    // Mặc định: createdAt DESC, rồi id ASC.
}
~~~

Ở phiên bản hỗ trợ annotation lặp, có thể viết liên tiếp hai `@SortDefault` thay cho container `SortDefaults`. Chọn một cách trình bày nhất quán. `value` của `@SortDefault` là alias cho `sort`; direction mặc định là ASC. `caseSensitive = false` tạo yêu cầu sort không phân biệt hoa thường, nhưng hiệu lực thực tế còn cần được kiểm chứng ở store. [API SortDefault](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/SortDefault.html)

Một tham số chỉ nhận `Sort` cũng dùng được annotation:

~~~java
public void listForExport(
        @SortDefault(sort = "id", direction = Sort.Direction.ASC)
        Sort sort) {

    // Sort chỉ mô tả thứ tự; không cung cấp giới hạn số phần tử.
}
~~~

Đối với export, phải thiết kế riêng giới hạn dữ liệu, streaming hoặc chia lô. Khai báo một sort mặc định không làm thao tác đọc toàn bộ dữ liệu trở nên có giới hạn.

## 5. Thứ tự ưu tiên: page/size và sort có hai nhánh xử lý

### 5.1. Page và size

Với request có giá trị hợp lệ:

1. Giá trị page hoặc size được gửi sẽ được dùng cho thành phần tương ứng.
2. Thành phần bị thiếu lấy từ `@PageableDefault`, nếu tham số có annotation.
3. Nếu không có annotation, thành phần thiếu lấy từ fallback của pageable resolver.

Không nên hiểu `@PageableDefault` là một tập thuộc tính thưa để trộn từng thuộc tính với cấu hình chung. Chỉ cần annotation xuất hiện, các giá trị mặc định của chính annotation cũng tham gia.

Ví dụ ứng dụng đặt fallback chung `PageRequest.of(0, 50)):

~~~java
// Request thiếu size vẫn dùng size = 10 của annotation.
public void list(
        @PageableDefault(sort = "id")
        Pageable pageable) {
}
~~~

Nếu endpoint cần size 50, hãy ghi `@PageableDefault(size = 50, sort = "id")`. Các request không hợp lệ còn đi qua bước chuẩn hóa riêng, được minh họa ở mục 8. [Nhánh chọn annotation hoặc fallback, bản 3.5.1](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/web/PageableHandlerMethodArgumentResolverSupport.java)

### 5.2. Sort

Trong resolver MVC chuẩn, sort được xử lý riêng rồi ghép vào pageable:

- Khi request gửi được các order hợp lệ về mặt cú pháp, chúng thay thế danh sách sort mặc định.
- Khi không gửi sort, sort resolver xét `@SortDefault` hoặc fallback sort của nó.
- Nếu sort resolver trả kết quả có order, pageable nhận kết quả đó.
- Nếu sort resolver trả `Sort.unsorted()`, pageable giữ sort đã có từ `@PageableDefault` hoặc fallback pageable.

Do đó, khi `@SortDefault` có property và `@PageableDefault.sort` cùng xuất hiện, sort có order từ nhánh `@SortDefault` được dùng. Hai danh sách không tự nối với nhau.

Tương tự, một fallback sort chung có order cũng có thể thay sort trong `@PageableDefault`. Để khai báo dễ theo dõi, nên dùng `@PageableDefault` cho page/size và `@SortDefault` cho các order khi endpoint cần nhiều direction. Không dùng annotation sort rỗng như một cơ chế chắc chắn để xóa mọi sort khác. [Cách ghép sort vào pageable](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/web/PageableHandlerMethodArgumentResolver.java), [cách xây dựng sort mặc định](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/web/SortHandlerMethodArgumentResolverSupport.java)

## 6. Đọc kết quả qua các request cụ thể

Giả sử endpoint dùng:

~~~java
@PageableDefault(page = 0, size = 25)
@SortDefault.SortDefaults({
        @SortDefault(sort = "createdAt", direction = Sort.Direction.DESC),
        @SortDefault(sort = "id", direction = Sort.Direction.ASC)
})
Pageable pageable
~~~

Resolver dùng tên tham số chuẩn, đánh số từ 0 và chưa chạm giới hạn size:

| Query string | Page nội bộ | Size | Sort nhận được |
| --- | ---: | ---: | --- |
| Không có query | 0 | 25 | createdAt DESC, id ASC |
| `?page=2` | 2 | 25 | createdAt DESC, id ASC |
| `?size=8` | 0 | 8 | createdAt DESC, id ASC |
| `?page=1&size=8` | 1 | 8 | createdAt DESC, id ASC |
| `?sort=total,asc` | 0 | 25 | total ASC |
| `?sort=total,desc&sort=id,asc` | 0 | 25 | total DESC, id ASC |

Dòng `?sort=total,asc` là tình huống dễ hiểu sai: `id ASC` trong mặc định **không tự được giữ lại**.

Nếu API yêu cầu một khóa phụ để phân biệt các giá trị total bằng nhau, ứng dụng phải bổ sung khóa đó theo chính sách riêng. Annotation chỉ cung cấp lựa chọn ban đầu khi client không chọn sort.

Tên `createdAt`, `total`, `id` trong ví dụ là property mà đường truy vấn dự định hỗ trợ. Không suy rằng chúng phải được thay bằng tên column như `created_at` ở mọi repository.

## 7. Cấu hình fallback chung và giới hạn size

Trong cấu hình Spring Data Web có hỗ trợ customizer, có thể khai báo:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.web.config
        .PageableHandlerMethodArgumentResolverCustomizer;

@Configuration
class PagingWebConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pagingDefaults() {
        return resolver -> {
            resolver.setFallbackPageable(PageRequest.of(0, 50));
            resolver.setMaxPageSize(100);
            resolver.setOneIndexedParameters(false);
        };
    }
}
~~~

Ở cấu hình này, endpoint không có annotation nhận fallback size 50; endpoint khai báo `@PageableDefault(size = 25)` vẫn có mặc định size 25. Giới hạn size 100 là một thiết lập riêng.

Hãy chọn một nơi quản lý chính sách chung để tránh các cấu hình trùng lặp khó truy vết. Khi dùng cơ chế cấu hình của Spring Boot, cần xem xét tương tác với cấu hình web thủ công, thay vì mặc định mọi thiết lập đều được áp dụng đồng thời. [Điểm mở rộng cho web resolver](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)

Một giới hạn page size phù hợp giúp kiểm soát lượng dữ liệu mỗi lần đọc. Nó không tự khống chế chi phí của:

- Truy vấn count để tạo tổng số phần tử của Page.
- Một sort thiếu index phù hợp.
- Offset rất lớn ở các trang sâu.
- Chuyển đổi entity sang DTO có truy vấn bổ sung.
- Một query truy cập nhiều dữ liệu trước khi áp dụng giới hạn.

Đối với API cần hiệu năng ổn định, phải đánh giá cả query thực tế và khả năng của module dữ liệu. Chọn Page, Slice hoặc chiến lược khác theo nhu cầu metadata của API.

## 8. Thiếu, rỗng và sai định dạng không hoàn toàn giống nhau

Không nên công bố quy tắc “tham số sai sẽ luôn trả 400” nếu chỉ đang dùng resolver chuẩn.

Ví dụ riêng cho mục này dùng `@PageableDefault(page = 3, size = 25)`, đánh số từ 0 và max size 100. Những kết quả sau thuộc hành vi parsing của bản 3.5.1:

| Request | Page | Size |
| --- | ---: | ---: |
| Không có query | 3 | 25 |
| `?page=` | 3 | 25 |
| `?page=abc` | 0 | 25 |
| `?page=-2` | 0 | 25 |
| `?size=abc` | 3 | 25 |
| `?size=0` | 3 | 25 |
| `?size=500` | 3 | 100 |

Một chuỗi page không parse được thành số có thể được chuẩn hóa thành 0, thay vì quay lại page mặc định 3. Với size không hợp lệ hoặc không dương, resolver sử dụng size dự phòng thích hợp. Đây là lý do cần kiểm tra đầu vào theo hợp đồng của ứng dụng, thay vì coi mọi trường hợp không dùng được là cùng một nhánh fallback. [Parsing và áp dụng giới hạn, bản 3.5.1](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/web/PageableHandlerMethodArgumentResolverSupport.java)

Đối với sort, request không có tham số hoặc chỉ có một `sort=` rỗng đi vào nhánh mặc định của sort resolver chuẩn trong phiên bản minh họa. Không dùng `sort=` như một quy ước ngầm để yêu cầu bỏ sort. Nếu API cần chế độ đó, hãy thiết kế một lựa chọn rõ ràng. [Xử lý sort thiếu và rỗng](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/web/SortHandlerMethodArgumentResolver.java)

Nếu hợp đồng yêu cầu từ chối `page=abc`, phải kiểm tra giá trị thô hoặc dùng resolver tùy biến trước khi thông tin bị chuẩn hóa. Đến lúc controller chỉ nhận `Pageable`, nó có thể không còn phân biệt được page 0 do client gửi với page 0 do parsing lỗi.

Các giá trị đặt sai trong annotation lại là lỗi cấu hình của lập trình viên. Ví dụ `@PageableDefault(size = 0)` không phải cách yêu cầu “không phân trang”.

## 9. Giá trị mặc định không thay thế kiểm tra property sort

Xét request:

~~~http
GET /orders?sort=internalRiskScore,desc
~~~

Ngay cả khi endpoint mặc định sort theo createdAt, client đã yêu cầu property khác. Việc resolver dựng được một `Sort` không chứng minh property đó tồn tại, được phép công khai hoặc truy vấn hiệu quả.

Một chính sách ví dụ:

- Chỉ chấp nhận `createdAt`, `total` và `id`.
- Luôn có `id` làm khóa phân biệt khi các khóa trước bằng nhau.
- Từ chối các property ngoài hợp đồng bằng phản hồi lỗi rõ ràng.
- Đặt chính sách riêng cho những tùy chọn sort mà backend chưa hỗ trợ.

Có thể chuẩn hóa sau khi resolve:

~~~java
import java.util.Set;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

final class OrderPagingPolicy {

    private static final Set<String> ALLOWED =
            Set.of("createdAt", "total", "id");

    private OrderPagingPolicy() {
    }

    static Pageable normalize(Pageable incoming) {
        if (incoming.isUnpaged()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Endpoint yêu cầu phân trang");
        }

        Sort sort = incoming.getSort();

        for (Sort.Order order : sort) {
            if (!ALLOWED.contains(order.getProperty())) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "Thuộc tính sắp xếp không được hỗ trợ");
            }
        }

        if (sort.getOrderFor("id") == null) {
            sort = sort.and(Sort.by(Sort.Order.asc("id")));
        }

        return PageRequest.of(
                incoming.getPageNumber(),
                incoming.getPageSize(),
                sort);
    }
}
~~~

Đây là chính sách minh họa do ứng dụng chọn, không phải hành vi do `@SortDefault` tự tạo. Nó cần được gọi trước khi chuyển pageable vào service hoặc repository.

Hàm giữ các order đã được chấp nhận rồi bổ sung id nếu thiếu. Với request `sort=total,desc`, kết quả có `total DESC, id ASC`. Với request đã có id, hàm không tự đổi direction của id.

Khóa phụ duy nhất giúp xác định thứ tự giữa các giá trị bằng nhau tại thời điểm query. Nó không bảo đảm dữ liệu không dịch chuyển giữa hai lần đọc khi có insert, update hoặc delete đồng thời. Cách phân trang và mức nhất quán cần được chọn theo yêu cầu thực tế.

## 10. Ví dụ controller để quan sát kết quả binding

Controller dưới đây chỉ trả metadata đã resolve, thuận tiện để thử annotation mà chưa cần truy cập database. Ví dụ dùng Java 17 trở lên:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.SortDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PagingProbeController {

    @GetMapping("/paging-probe")
    PagingView inspect(
            @PageableDefault(page = 0, size = 25)
            @SortDefault.SortDefaults({
                    @SortDefault(
                            sort = "createdAt",
                            direction = Sort.Direction.DESC),
                    @SortDefault(
                            sort = "id",
                            direction = Sort.Direction.ASC)
            })
            Pageable pageable) {

        List<OrderView> orders = new ArrayList<>();
        pageable.getSort().forEach(order ->
                orders.add(new OrderView(
                        order.getProperty(),
                        order.getDirection().name())));

        return new PagingView(
                pageable.getPageNumber(),
                pageable.getPageSize(),
                orders);
    }

    public record PagingView(
            int page, int size, List<OrderView> sort) {
    }

    public record OrderView(String property, String direction) {
    }
}
~~~

Ví dụ kết quả khi không có query string:

~~~json
{
  "page": 0,
  "size": 25,
  "sort": [
    {"property": "createdAt", "direction": "DESC"},
    {"property": "id", "direction": "ASC"}
  ]
}
~~~

Khi nối vào nghiệp vụ, controller nên chuyển pageable qua chính sách của endpoint rồi gọi service. Repository cần cung cấp đường truy vấn hỗ trợ phân trang/sort tương ứng. Projection thay đổi kiểu dữ liệu trả về cũng không tự làm mọi property có thể sort được; cần đánh giá query cụ thể.

Ví dụ probe chứng minh cách đọc kết quả binding, chưa chứng minh khả năng thực thi một query của JPA, MongoDB, JDBC hay một module khác.

## 11. Kiểm thử hợp đồng của annotation

Có thể kiểm thử resolver bằng MockMvc standalone, không cần khởi động database:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.data.web.PageableHandlerMethodArgumentResolver;
import org.springframework.data.web.SortHandlerMethodArgumentResolver;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

class PagingProbeControllerTest {

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        var sortResolver = new SortHandlerMethodArgumentResolver();
        var pageableResolver =
                new PageableHandlerMethodArgumentResolver(sortResolver);
        pageableResolver.setMaxPageSize(100);

        mvc = MockMvcBuilders
                .standaloneSetup(new PagingProbeController())
                .setCustomArgumentResolvers(pageableResolver)
                .build();
    }

    @Test
    void missingParametersUseEndpointDefaults() throws Exception {
        mvc.perform(get("/paging-probe"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(0))
                .andExpect(jsonPath("$.size").value(25))
                .andExpect(jsonPath("$.sort.length()").value(2))
                .andExpect(jsonPath("$.sort[0].property")
                        .value("createdAt"))
                .andExpect(jsonPath("$.sort[0].direction").value("DESC"))
                .andExpect(jsonPath("$.sort[1].property").value("id"))
                .andExpect(jsonPath("$.sort[1].direction").value("ASC"));
    }

    @Test
    void explicitSortReplacesDefaultOrders() throws Exception {
        mvc.perform(get("/paging-probe")
                        .param("page", "2")
                        .param("size", "8")
                        .param("sort", "total,asc"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(2))
                .andExpect(jsonPath("$.size").value(8))
                .andExpect(jsonPath("$.sort.length()").value(1))
                .andExpect(jsonPath("$.sort[0].property").value("total"))
                .andExpect(jsonPath("$.sort[0].direction").value("ASC"));
    }

    @Test
    void sizeCannotExceedResolverMaximum() throws Exception {
        mvc.perform(get("/paging-probe").param("size", "500"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.size").value(100));
    }
}
~~~

Các đoạn code là ví dụ thiết kế kiểm thử, không phải xác nhận đã chạy thành công trong một môi trường cụ thể. Test cần các thư viện JUnit 5, Spring Test và JSON tương ứng trong dự án sử dụng.

Ngoài ba tình huống trên, ma trận của ứng dụng nên xét:

| Nhóm | Bằng chứng cần có |
| --- | --- |
| Tham số thiếu | Mặc định của endpoint được sử dụng |
| Chỉ gửi page hoặc size | Thành phần còn lại có giá trị đúng |
| Sort nhiều direction | Thứ tự các order được giữ đúng |
| Sort rỗng | Hành vi đúng với hợp đồng đã chọn |
| Page/size sai định dạng | Chuẩn hóa hoặc từ chối theo chính sách thực tế |
| Property không cho phép | Không đi đến query ngoài phạm vi API |
| Cấu hình chung | Customizer được đăng ký và áp dụng thật |
| Query tích hợp | Store thực thi được sort, phân trang và kiểu kết quả dự định |

MockMvc standalone trong ví dụ chủ động đăng ký resolver. Nó không chứng minh Spring Boot đã nạp customizer trong application context. Muốn kiểm tra phần cấu hình đó, cần một test dùng context phù hợp của ứng dụng.

## 12. Những lỗi thiết kế thường gặp

| Cách làm | Hệ quả | Điều chỉnh |
| --- | --- | --- |
| Dùng `@PageableDefault(size = 25)` như giới hạn cứng | Client vẫn có thể yêu cầu size lớn hơn | Cấu hình max size hoặc chính sách endpoint |
| Chỉ thêm `@PageableDefault(sort = "id")` và mong giữ size chung | Size có thể trở thành 10 | Ghi rõ size theo hợp đồng |
| Mong sort từ request tự nối với mặc định | Khóa phụ có thể biến mất | Chuẩn hóa các order được phép và thêm khóa phụ cần thiết |
| Xem parsing thành công là property hợp lệ | Lỗi có thể xuất hiện ở query hoặc lộ lựa chọn ngoài hợp đồng | Kiểm tra danh sách property được hỗ trợ |
| Bắt lỗi query rồi trả danh sách rỗng | Client hiểu nhầm không có dữ liệu | Giữ phản hồi lỗi đúng nghĩa |
| Đặt annotation trên service rồi mong tự bind request | Không có bước argument resolution tại service | Đặt tại tham số handler hoặc tự tạo Pageable |
| Dùng sort mặc định để bảo đảm mọi trang bất biến | Dữ liệu đồng thời vẫn có thể dịch chuyển | Thiết kế chiến lược đọc và nhất quán phù hợp |
| Thử bằng gọi Java method trực tiếp | Không đi qua web resolver | Dùng kiểm thử có bước binding HTTP |

## 13. Tự kiểm tra

1. Vì sao `Pageable pageable` không có annotation có thể dùng size 20, còn thêm `@PageableDefault` trống lại dùng size 10?
2. Endpoint cần `createdAt DESC, id ASC` nên khai báo annotation thế nào?
3. Với mặc định trên, request `?sort=total,asc` còn order id hay không?
4. Cần làm gì nếu id phải xuất hiện ngay cả khi client gửi sort riêng?
5. Vì sao `size = 25` không thay thế `setMaxPageSize(100)`?
6. Sau khi nhận Pageable đã được chuẩn hóa, controller có luôn biết client từng gửi `page=abc` không?
7. Vì sao kiểm thử binding không đủ để kết luận store thực thi được query?
8. Một test standalone đăng ký resolver khác gì test cấu hình web thật của ứng dụng?

Một endpoint rõ ràng cần xác định riêng mặc định khi client bỏ trống, quyền ghi đè của client và những giới hạn bắt buộc. `@PageableDefault` cùng `@SortDefault` diễn đạt phần mặc định; resolver, chính sách của ứng dụng và module dữ liệu cùng quyết định hành vi cuối cùng.
