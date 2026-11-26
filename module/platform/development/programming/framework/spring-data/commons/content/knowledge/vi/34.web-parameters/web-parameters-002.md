# PageableHandlerMethodArgumentResolver và SortHandlerMethodArgumentResolver

## Mục tiêu và phạm vi

Một endpoint danh sách thường nhận số trang, kích thước trang và thứ tự sắp xếp từ URL. Trong Spring Data Commons, hai lớp kết nối những tham số web đó với abstraction truy cập dữ liệu là:

- `PageableHandlerMethodArgumentResolver`: tạo đối số `Pageable` cho phương thức controller.
- `SortHandlerMethodArgumentResolver`: tạo đối số `Sort`, đồng thời cung cấp phần sắp xếp cho pageable resolver.

Bài học thuộc chương **Tham số web** của module **SPRING_DATA_COMMONS**. Trọng tâm là Spring MVC: cách binding hoạt động, cú pháp request, giá trị mặc định, cấu hình và ranh giới trách nhiệm. Các ví dụ dùng Java 17 trở lên và giả định Spring MVC cùng Spring Data Web Support đã được thiết lập.

Sau bài học, bạn có thể thiết kế một endpoint nhận phân trang và sắp xếp, giải thích kết quả resolver tạo ra và chuyển metadata đó đến repository phù hợp. Bạn cũng cần phân biệt abstraction dùng chung của Commons với năng lực thực thi của từng module như JPA, JDBC hoặc MongoDB.

## 1. Resolver nằm ở đâu trong một request?

Xét request:

~~~http
GET /products?page=2&size=15&sort=price,desc&sort=id,asc
~~~

Luồng xử lý có thể hình dung như sau:

~~~mermaid
flowchart LR
    A["Request HTTP"] --> B["Spring MVC chọn handler"]
    B --> C["Resolver tạo Pageable và Sort"]
    C --> D["Controller nhận đối số"]
    D --> E["Áp dụng chính sách truy vấn"]
    E --> F["Repository của module store"]
    F --> G["Kết quả và response DTO"]
~~~

Có ba đối tượng khác nhau:

| Đối tượng | Mang thông tin gì? | Có dữ liệu truy vấn chưa? |
|---|---|---|
| `Sort` | Các thuộc tính, hướng và tùy chọn sắp xếp | Chưa |
| `Pageable` | Yêu cầu phân trang và `Sort` đi kèm | Chưa |
| `Page<T>` | Nội dung của một trang và metadata kết quả, gồm tổng số phần tử/trang | Có |

Resolver không gọi repository để tìm sản phẩm. Nó cũng không biết trước có bao nhiêu sản phẩm phù hợp. Tác vụ của resolver là tạo giá trị đầu vào cho handler; tầng truy cập dữ liệu mới diễn giải chúng thành thao tác được store hỗ trợ.

Controller có `Pageable` không đồng nghĩa dữ liệu đã được phân trang. Nếu code bỏ qua đối số đó và gọi một thao tác lấy toàn bộ dữ liệu, việc binding thành công không giúp hạn chế kết quả.

Tham khảo hợp đồng của [Pageable](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Pageable.html) và [Page](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html).

## 2. Bật Spring Data Web Support

Trong một ứng dụng Spring MVC được cấu hình bằng Java, có thể bật hỗ trợ web của Spring Data:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@Configuration
@EnableSpringDataWebSupport
public class DataWebConfiguration {
}
~~~

Đoạn này giả định hạ tầng Spring MVC đã tồn tại. Annotation đăng ký các thành phần hỗ trợ web, trong đó có hai resolver đang xét. Nó không cấu hình database hoặc tự tạo implementation cho mọi repository.

Trong ứng dụng Spring Boot, auto-configuration có thể đã cung cấp hỗ trợ tương ứng khi điều kiện về classpath và cấu hình được đáp ứng. Cần xác định cấu hình thực tế trước khi bổ sung một bộ resolver khác. Việc có dependency Spring Data Commons trên classpath, đứng riêng, chưa chứng minh một cấu hình MVC bất kỳ đã đăng ký resolver.

Tham số controller thường khai báo trực tiếp bằng interface:

~~~java
public Object list(Pageable pageable) {
    // Xử lý yêu cầu danh sách.
}
~~~

Đây chỉ là minh họa chữ ký, chưa phải một implementation hoàn chỉnh. Không cần thêm `@RequestParam` vào `Pageable` để yêu cầu cơ chế này hoạt động. `@RequestParam` phục vụ một cơ chế phân giải tham số khác; cũng không dùng `@RequestBody` nếu hợp đồng là đọc `page`, `size` và `sort` từ query string.

Thông tin đăng ký nằm trong [EnableSpringDataWebSupport](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/config/EnableSpringDataWebSupport.html). Phần còn lại của bài giả định resolver đã được đăng ký đúng trong ứng dụng.

## 3. Một controller quan sát trực tiếp kết quả binding

Controller dưới đây trả metadata để học và kiểm thử, chưa truy vấn database. Lưu các kiểu trong ví dụ thành đơn vị mã nguồn Java phù hợp khi thực hành.

~~~java
import java.util.List;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/probe")
public class PagingProbeController {

    @GetMapping("/page")
    public PageView page(Pageable pageable) {
        return new PageView(
            pageable.getPageNumber(),
            pageable.getPageSize(),
            pageable.getOffset(),
            describe(pageable.getSort())
        );
    }

    @GetMapping("/sort")
    public List<OrderView> sort(Sort sort) {
        return describe(sort);
    }

    private static List<OrderView> describe(Sort sort) {
        return sort.stream()
            .map(order -> new OrderView(
                order.getProperty(),
                order.getDirection().name(),
                order.isIgnoreCase()
            ))
            .toList();
    }

    public record OrderView(
        String property,
        String direction,
        boolean ignoreCase
    ) {
    }

    public record PageView(
        int page,
        int size,
        long offset,
        List<OrderView> orders
    ) {
    }
}
~~~

Với request:

~~~http
GET /probe/page?page=2&size=15&sort=price,desc&sort=id,asc
~~~

metadata mong đợi là:

~~~json
{
  "page": 2,
  "size": 15,
  "offset": 30,
  "orders": [
    {
      "property": "price",
      "direction": "DESC",
      "ignoreCase": false
    },
    {
      "property": "id",
      "direction": "ASC",
      "ignoreCase": false
    }
  ]
}
~~~

Với pageable phân trang thông thường:

~~~text
offset = pageNumber × pageSize
~~~

Trang 2 theo chỉ số bắt đầu từ 0 là trang thứ ba. `offset = 30` chỉ biểu diễn vị trí bắt đầu được yêu cầu. Đó không phải bằng chứng resolver đã đọc hoặc bỏ qua 30 bản ghi tại database.

Ví dụ controller này giả định fallback là pageable có phân trang. Nếu chủ động cấu hình fallback `Pageable.unpaged()`, phải xử lý `isUnpaged()` trước khi gọi các accessor chỉ có ý nghĩa với yêu cầu phân trang.

## 4. Cú pháp của page và size

Khi chưa tùy biến resolver và không có annotation mặc định riêng trên tham số:

| Query string | Yêu cầu được biểu diễn |
|---|---|
| Không truyền tham số | Trang 0, kích thước 20 |
| `?page=0&size=10` | Trang đầu, tối đa 10 phần tử theo yêu cầu |
| `?page=1&size=10` | Trang thứ hai, offset 10 |
| `?page=3` | Trang 3, dùng kích thước mặc định |
| `?size=50` | Trang đầu, kích thước 50 nếu nằm trong giới hạn cấu hình |

Đây là mặc định của Spring Data Web Support; cấu hình ứng dụng có thể thay đổi chúng. Không mặc định mọi dự án Spring Boot đều đang dùng đúng các giá trị đó.

`size` là kích thước yêu cầu, không bảo đảm kết quả luôn có đủ phần tử. Trang cuối có thể ngắn hơn. Một trang nằm ngoài phạm vi dữ liệu có thể rỗng; resolver không biết dữ liệu thực tế để tự phát sinh lỗi “không có trang”.

Hợp đồng mặc định về query string được mô tả trong [Spring Data Commons Web Support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions-web.html).

### Pageable đã chứa phần sắp xếp

Nếu controller nhận `Pageable pageable`, đọc các thứ tự bằng:

~~~java
Sort sort = pageable.getSort();
~~~

Thông thường không cần thêm một đối số `Sort` riêng chỉ để đọc lại chính tham số `sort` đó. Nếu khai báo cả hai mà không phân biệt namespace, chúng có thể cùng đọc một nguồn query string. Hãy xác định rõ mục đích của mỗi đối số.

Mặc định không có sort không có nghĩa database bảo đảm trả dữ liệu theo ID. Thứ tự tự nhiên hoặc thứ tự quan sát được trong vài lần chạy không phải một hợp đồng ổn định.

## 5. Cú pháp sort và thứ tự ưu tiên

Một biểu thức thông dụng là `sort=property,direction`:

~~~http
GET /probe/sort?sort=name,asc
GET /probe/sort?sort=price,desc
~~~

Có thể dùng nhiều tham số `sort`:

~~~http
GET /probe/sort?sort=price,desc&sort=id,asc
~~~

Ý nghĩa mong muốn:

1. Sắp xếp chính theo giá giảm dần.
2. Khi giá bằng nhau, sắp xếp tiếp theo ID tăng dần.

Thứ tự các `Sort.Order` quan trọng. Hai danh sách `price DESC, id ASC` và `id ASC, price DESC` không tương đương.

Những thuộc tính dùng chung hướng có thể nằm trong một biểu thức:

~~~http
GET /probe/sort?sort=name,id,asc
~~~

Khi muốn các hướng khác nhau, dùng các tham số riêng như ví dụ `price` và `id`. Không ghép nhiều cặp thuộc tính–hướng một cách tùy ý vào một giá trị và kỳ vọng parser hiểu theo từng cặp.

### Không phân biệt hoa thường là một yêu cầu có điều kiện

Cú pháp có thể biểu diễn yêu cầu bỏ qua hoa thường:

~~~http
GET /probe/sort?sort=name,asc,ignorecase
~~~

Resolver tạo metadata tương ứng. Việc store áp dụng được yêu cầu đó trên kiểu dữ liệu, collation hoặc biểu thức truy vấn đang dùng phải được kiểm tra ở tầng tích hợp. Không suy rằng tùy chọn này có ý nghĩa cho mọi thuộc tính, chẳng hạn một trường số.

`Sort.Order` còn có các tùy chọn ở API Java. Sự tồn tại của một phương thức Java không tự biến tên của nó thành token query string hợp lệ. Khi thiết kế cú pháp URL, cần dùng cú pháp mà resolver đang cấu hình thực sự hỗ trợ.

Xem abstraction [Sort](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Sort.html) và khả năng cấu hình parser trong [SortHandlerMethodArgumentResolverSupport](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/SortHandlerMethodArgumentResolverSupport.html).

## 6. Nhận Sort độc lập

Endpoint chỉ có nhu cầu sắp xếp có thể nhận `Sort` trực tiếp, như `/probe/sort` ở ví dụ đầu:

~~~http
GET /probe/sort?sort=name,asc&sort=id,desc
~~~

Trong endpoint đó, việc client gửi thêm `page` và `size` không tạo ra phân trang, vì handler không nhận hoặc sử dụng `Pageable`.

Một phương thức repository nhận `Sort` thường thể hiện yêu cầu lấy kết quả theo thứ tự đó, còn giới hạn số lượng phải được thiết kế riêng. Vì vậy, không thay thế endpoint phân trang bằng endpoint chỉ nhận sort khi tập dữ liệu có thể lớn.

Một sai sót khác là controller nhận `Sort` nhưng service tạo một `Sort.by("id")` mới và bỏ qua đầu vào. Resolver vẫn hoạt động; lỗi nằm ở việc metadata không được truyền qua các tầng.

Nếu ứng dụng cố ý áp dụng một thứ tự cố định, nên tài liệu hóa hợp đồng đó thay vì quảng bá rằng endpoint cho phép client tùy chọn mọi cách sắp xếp.

## 7. Đặt mặc định theo endpoint

### 7.1. PageableDefault

`@PageableDefault` thiết lập giá trị mặc định cho một đối số:

~~~java
import java.util.Map;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;

// Phương thức đặt trong một @RestController.
@GetMapping("/products/defaults")
public Map<String, Object> defaults(
    @PageableDefault(
        page = 0,
        size = 25,
        sort = "name",
        direction = Sort.Direction.ASC
    ) Pageable pageable
) {
    return Map.of(
        "page", pageable.getPageNumber(),
        "size", pageable.getPageSize(),
        "sort", pageable.getSort().toString()
    );
}
~~~

Khi không truyền tham số, endpoint này nhận trang đầu, kích thước 25 và mặc định sắp xếp theo tên. Khi truyền giá trị hợp lệ cho từng phần, resolver sử dụng đầu vào tương ứng.

Cần phân biệt hai mặc định khác nhau:

- Fallback của resolver khi không có cấu hình riêng: thường là trang 0, kích thước 20.
- Giá trị mặc định của thuộc tính `size` trong chính annotation `@PageableDefault`: 10.

Vì vậy, thêm `@PageableDefault` không khai báo `size` có thể thay đổi kích thước mặc định của endpoint. Khai báo `size` tường minh thường giúp người đọc hiểu hợp đồng dễ hơn.

Annotation này cung cấp mặc định, không khóa kích thước trang ở 25 và không phải giới hạn tối đa. Xem [PageableDefault](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableDefault.html).

### 7.2. SortDefault và nhiều hướng mặc định

Khi mặc định gồm nhiều thuộc tính với các hướng khác nhau, dùng `@SortDefault.SortDefaults`:

~~~java
import java.util.Map;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.SortDefault;
import org.springframework.web.bind.annotation.GetMapping;

// Phương thức đặt trong một @RestController.
@GetMapping("/products/recent")
public Map<String, Object> recent(
    @PageableDefault(size = 25)
    @SortDefault.SortDefaults({
        @SortDefault(
            sort = "createdAt",
            direction = Sort.Direction.DESC
        ),
        @SortDefault(
            sort = "id",
            direction = Sort.Direction.ASC
        )
    }) Pageable pageable
) {
    return Map.of(
        "page", pageable.getPageNumber(),
        "size", pageable.getPageSize(),
        "sort", pageable.getSort().toString()
    );
}
~~~

Trong ví dụ này, phần mặc định về kích thước và phần mặc định về thứ tự được khai báo riêng. `@SortDefault` cũng có thể dùng trên đối số `Sort` độc lập.

Mặc định sort không phải một thứ tự bổ sung bắt buộc sau sort của client. Nếu client gửi `sort=price,desc`, đừng kỳ vọng `id ASC` ở annotation luôn được tự nối thêm. Nếu nghiệp vụ cần một khóa phân xử cuối cùng, bổ sung bằng chính sách ứng dụng.

Tránh khai báo cùng một chính sách sort ở nhiều annotation theo những cách chồng chéo khó hiểu. Hợp đồng annotation nằm trong [SortDefault](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/SortDefault.html).

## 8. Nhiều Pageable hoặc Sort trong một handler

Một màn hình có thể hiển thị hai bảng cần phân trang độc lập. Dùng `@Qualifier` để phân biệt:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;

// Phương thức đặt trong một @RestController.
@GetMapping("/dashboard")
public Map<String, Object> dashboard(
    @Qualifier("products") Pageable products,
    @Qualifier("suppliers") Pageable suppliers
) {
    return Map.of(
        "productPage", products.getPageNumber(),
        "productSize", products.getPageSize(),
        "productSort", products.getSort().toString(),
        "supplierPage", suppliers.getPageNumber(),
        "supplierSize", suppliers.getPageSize(),
        "supplierSort", suppliers.getSort().toString()
    );
}
~~~

Request tương ứng với delimiter mặc định là dấu gạch dưới:

~~~http
GET /dashboard?products_page=1&products_size=10&products_sort=name,asc&suppliers_page=0&suppliers_size=5&suppliers_sort=id,desc
~~~

`products_sort` đi vào `products.getSort()`; `suppliers_sort` đi vào pageable của nhà cung cấp. Nguyên tắc namespace cũng áp dụng cho nhiều đối số `Sort` độc lập.

Tên query không lấy từ tên biến Java `products` một cách ngầm định; trong ví dụ, namespace được chỉ định bởi `@Qualifier("products")`. Đổi tên biến mà giữ qualifier không có nghĩa đổi API.

Không nên khai báo hai `Pageable` không phân biệt rồi trông chờ Spring tự biết tham số nào điều khiển bảng nào. Việc controller nhận được hai đối tượng không thay thế cho một hợp đồng URL rõ ràng.

Cơ chế qualifier và việc kết hợp resolver được thể hiện trong mã nguồn [PageableHandlerMethodArgumentResolver](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/web/PageableHandlerMethodArgumentResolver.java).

## 9. Tùy biến resolver bằng customizer

Có thể đăng ký các bean customizer khi dùng cấu hình Spring Data Web Support hỗ trợ chúng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.web.config.PageableHandlerMethodArgumentResolverCustomizer;
import org.springframework.data.web.config.SortHandlerMethodArgumentResolverCustomizer;

@Configuration
public class PagingPolicyConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pageableCustomizer() {
        return resolver -> {
            resolver.setFallbackPageable(PageRequest.of(0, 20));
            resolver.setMaxPageSize(100);
        };
    }

    @Bean
    SortHandlerMethodArgumentResolverCustomizer sortCustomizer() {
        return resolver -> resolver.setSortParameter("order");
    }
}
~~~

Trong cấu hình minh họa này:

- Request không cung cấp thông tin phân trang dùng fallback tương ứng nếu không có annotation mặc định riêng.
- Kích thước trang được giới hạn ở 100.
- Tham số sắp xếp đổi từ `sort` thành `order`.

Request sau dùng tên đã tùy biến:

~~~http
GET /probe/page?page=1&size=30&order=price,desc
~~~

Đây là một cấu hình thay thế cho những ví dụ dùng mặc định, không phải yêu cầu đổi hợp đồng giữa chừng trong cùng một API.

Customizer phải được áp dụng lên đúng instance resolver đang phục vụ request. Nếu ứng dụng tự tạo resolver riêng bên ngoài cấu hình Spring Data, việc tồn tại bean customizer không bảo đảm instance đó đã được tùy biến.

Nên gom các thiết lập liên quan vào một chính sách rõ ràng, thay vì phụ thuộc vào thứ tự không được chủ động quản lý giữa nhiều bean customizer cùng loại. Hai callback tương ứng là [PageableHandlerMethodArgumentResolverCustomizer](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/config/PageableHandlerMethodArgumentResolverCustomizer.html) và [SortHandlerMethodArgumentResolverCustomizer](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/config/SortHandlerMethodArgumentResolverCustomizer.html).

### Các tùy biến cần hiểu đúng

| Thiết lập | Tác động |
|---|---|
| `setPageParameterName("p")` | Đọc số trang từ `p` |
| `setSizeParameterName("limit")` | Đọc kích thước từ `limit` |
| `setOneIndexedParameters(true)` | Diễn giải trang HTTP đầu tiên là 1 |
| `setMaxPageSize(100)` | Đặt trần kích thước trang được chấp nhận |
| `setPrefix("search_")` trên pageable resolver | Thêm prefix vào tham số trang và kích thước |
| `setQualifierDelimiter("_")` | Điều khiển dấu nối namespace của qualifier |
| `setSortParameter("order")` trên sort resolver | Đổi tên tham số sort |
| `setPropertyDelimiter(";")` trên sort resolver | Đổi delimiter trong biểu thức sort |

Prefix của pageable resolver không tự đổi prefix của tham số sort. Nếu đổi qualifier delimiter, cần giữ hai resolver nhất quán để cùng một pageable đọc đúng các tham số dự kiến.

Các setter phía pageable được mô tả trong [PageableHandlerMethodArgumentResolverSupport](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableHandlerMethodArgumentResolverSupport.html).

## 10. Trang bắt đầu từ 1 ở HTTP, từ 0 trong Pageable

Giả sử thêm vào pageable customizer:

~~~java
resolver.setOneIndexedParameters(true);
~~~

Khi đó:

| Request HTTP | `pageable.getPageNumber()` | Với `size=10`, offset |
|---|---:|---:|
| `page=1` | 0 | 0 |
| `page=2` | 1 | 10 |
| `page=3` | 2 | 20 |

Thiết lập này thay đổi cách đọc chỉ số từ request. Nó không đổi quy ước nội bộ của `PageRequest` sang bắt đầu từ 1.

Một lỗi thường gặp là bật chế độ này rồi lại trừ 1 trong controller. Khi đối số đã được resolver tạo đúng, phép trừ bổ sung làm sai trang.

Nếu response của API cũng cần dùng số trang bắt đầu từ 1, hãy định nghĩa rõ trong DTO response và chuyển đổi có chủ đích. Không suy rằng việc đổi đầu vào HTTP tự đổi mọi metadata đầu ra.

Cũng phải ghi rõ frontend gửi số trang theo quy ước nào. Một API mà request bắt đầu từ 1 nhưng response âm thầm bắt đầu từ 0 dễ tạo lỗi khi người dùng chuyển trang hoặc sao chép URL.

## 11. Binding không đồng nghĩa validation nghiêm ngặt

Các resolver chuẩn có thể chuẩn hóa một số giá trị thay vì luôn trả `400 Bad Request`:

- Giá trị trang không chuyển được sang số có thể được xử lý về mốc 0.
- Kích thước trang không hợp lệ có thể dùng kích thước mặc định.
- Kích thước vượt trần có thể bị giảm xuống trần đã cấu hình.

Không xây dựng hợp đồng “mọi đầu vào sai đều báo 400” chỉ dựa vào việc dùng `Pageable`. Nếu hợp đồng yêu cầu từ chối đầu vào thô không hợp lệ, cần xử lý ở lớp còn thấy được giá trị request trước khi thông tin bị chuẩn hóa, hoặc bằng resolver tùy biến thích hợp.

Một validation trên đối tượng `Pageable` sau binding chỉ nhìn thấy kết quả đã chuẩn hóa. Chẳng hạn client gửi kích thước 100000 nhưng resolver đã giới hạn về 100; tầng sau không thể từ giá trị 100 kết luận chính xác request ban đầu đã gửi bao nhiêu.

Hành vi cụ thể cần được kiểm thử với phiên bản và cấu hình ứng dụng. Mã nguồn [PageableHandlerMethodArgumentResolverSupport](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/web/PageableHandlerMethodArgumentResolverSupport.java) giúp đối chiếu cơ chế fallback và giới hạn.

### Tên thuộc tính sort cũng cần chính sách riêng

Parser tạo `Sort.Order` không có trách nhiệm bảo đảm tên property được phép dùng trong một endpoint cụ thể. Một token hướng gõ sai cũng không nên được giả định chắc chắn sẽ tạo lỗi binding ngay.

Đầu vào lạ có thể trở thành tên thuộc tính và chỉ bị phát hiện khi tầng truy vấn xử lý. Vì vậy, hãy quy định tập tên sort được phép và kiểm thử các trường hợp sai, thay vì dùng lỗi database như hợp đồng validation.

Có thể đối chiếu cơ chế đọc tham số trong [SortHandlerMethodArgumentResolver](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/web/SortHandlerMethodArgumentResolver.java) và cơ chế phân tích biểu thức trong [SortHandlerMethodArgumentResolverSupport](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/web/SortHandlerMethodArgumentResolverSupport.java).

## 12. Áp dụng chính sách sort và phân trang của endpoint

Ví dụ sau là một chính sách ứng dụng tự thiết kế, không phải mặc định của Spring Data:

- Chỉ cho phép các khóa public `id`, `name`, `price` và `created`.
- Khóa public `created` được ánh xạ thành property `createdAt`.
- Từ chối sort lặp cùng một property và yêu cầu bỏ qua hoa thường.
- Nối `id ASC` nếu client chưa chọn ID để phân xử các giá trị bằng nhau.
- Giới hạn kích thước và offset theo ngân sách truy vấn của ví dụ.

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

public final class ProductPagePolicy {

    private static final int MAX_SIZE = 100;
    private static final long MAX_OFFSET = 100_000L;

    private static final Map<String, String> PROPERTIES = Map.of(
        "id", "id",
        "name", "name",
        "price", "price",
        "created", "createdAt"
    );

    private ProductPagePolicy() {
    }

    public static Pageable normalize(Pageable requested) {
        if (requested.isUnpaged()) {
            throw badRequest("Pagination is required");
        }

        if (requested.getPageSize() > MAX_SIZE) {
            throw badRequest("Page size exceeds the endpoint limit");
        }

        if (requested.getOffset() > MAX_OFFSET) {
            throw badRequest("Requested offset is too large");
        }

        List<Sort.Order> orders = new ArrayList<>();
        Set<String> seen = new HashSet<>();

        for (Sort.Order order : requested.getSort()) {
            String property = PROPERTIES.get(order.getProperty());

            if (property == null) {
                throw badRequest("Unsupported sort property");
            }

            if (!seen.add(property)) {
                throw badRequest("Duplicate sort property");
            }

            if (order.isIgnoreCase()) {
                throw badRequest("Ignore-case sorting is not supported");
            }

            orders.add(new Sort.Order(
                order.getDirection(),
                property
            ));
        }

        if (!seen.contains("id")) {
            orders.add(Sort.Order.asc("id"));
        }

        return PageRequest.of(
            requested.getPageNumber(),
            requested.getPageSize(),
            Sort.by(orders)
        );
    }

    private static ResponseStatusException badRequest(String message) {
        return new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            message
        );
    }
}
~~~

Với `sort=price,desc`, policy tạo `price DESC, id ASC`. Với `sort=created,desc`, property chuyển xuống repository là `createdAt`. Với `sort=internalCost,asc`, endpoint từ chối theo hợp đồng của ví dụ.

Khi dùng policy này, annotation mặc định của endpoint cũng phải dùng khóa public, chẳng hạn `sort = "created"`. Nếu annotation đã dùng `createdAt` nhưng bảng ánh xạ chỉ nhận `created`, chính đầu vào mặc định sẽ bị từ chối.

Các ngưỡng 100 và 100000 cần được lựa chọn theo yêu cầu thực tế, không sao chép như một bảo đảm hiệu năng chung. Chính sách không thay thế lọc tenant hoặc kiểm tra quyền truy cập dữ liệu; chúng cần nằm trong truy vấn hoặc tầng nghiệp vụ thích hợp.

Khóa ID tạo thứ tự xác định khi các giá trị chính bằng nhau, nhưng offset pagination vẫn có thể dịch chuyển khi dữ liệu bị thêm/xóa giữa hai request. Nếu nghiệp vụ cần duyệt một tập thay đổi liên tục với yêu cầu chặt chẽ hơn, phải cân nhắc cơ chế snapshot, cursor hoặc keyset theo khả năng của store.

## 13. Truyền metadata xuống repository đúng cách

Ở abstraction Commons, một repository có khả năng phân trang có thể cung cấp hợp đồng:

~~~java
import org.springframework.data.repository.PagingAndSortingRepository;

// Product là kiểu domain đã được mapping theo module store đang dùng.
public interface ProductRepository
    extends PagingAndSortingRepository<Product, Long> {
}
~~~

Đây là chữ ký minh họa cho tầng repository; nó giả định kiểu `Product` và cấu hình module store đã tồn tại. Một service có thể áp dụng policy rồi gọi:

~~~java
Pageable effective = ProductPagePolicy.normalize(requested);
Page<Product> page = repository.findAll(effective);
~~~

Các biến `requested` và `repository` ở đoạn trên là đầu vào và dependency của service. Không tự lấy toàn bộ dữ liệu rồi mới dùng `subList` để giả lập phân trang cho một truy vấn lớn.

`PagingAndSortingRepository` cung cấp hợp đồng, còn việc tạo implementation và triển khai truy vấn phụ thuộc module store. Không suy rằng thêm interface này sẽ tạo hỗ trợ paging cho một hạ tầng vốn chưa hỗ trợ.

Trong các thế hệ Spring Data hiện đại, repository phân trang và repository CRUD là các hợp đồng cần kết hợp theo nhu cầu. Không dựa vào giả định mọi interface phân trang tự cung cấp toàn bộ phương thức CRUD. Xem [PagingAndSortingRepository](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/PagingAndSortingRepository.html).

### Metadata yêu cầu và metadata kết quả

Pageable đầu vào chưa có `totalElements`. Khi service cần một `Page<T>` với tổng số phần tử, module store có thể cần thêm công việc để xác định tổng; không phải lúc nào cũng chỉ có một thao tác đọc đơn giản.

Nếu chỉ cần biết còn phần tiếp theo hay không, có thể cân nhắc `Slice` trong hợp đồng repository được hỗ trợ. Đây là quyết định thiết kế truy vấn, không phải một tùy chọn làm resolver tự tính tổng.

Với response public, nên chủ động định nghĩa cấu trúc JSON. Ví dụ:

~~~java
import java.util.List;

import org.springframework.data.domain.Page;

public record PageResponse<T>(
    List<T> content,
    int page,
    int size,
    long totalElements,
    int totalPages
) {
    public static <T> PageResponse<T> from(Page<T> source) {
        return new PageResponse<>(
            source.getContent(),
            source.getNumber(),
            source.getSize(),
            source.getTotalElements(),
            source.getTotalPages()
        );
    }
}
~~~

`T` nên là DTO/projection mà API chủ định công khai. Ví dụ response này dùng chỉ số trang bắt đầu từ 0. Nếu hợp đồng chọn cách đánh số khác, thực hiện chuyển đổi ở một chỗ rõ ràng.

## 14. Kiểm thử resolver bằng MockMvc

Chỉ gọi trực tiếp `controller.page(PageRequest.of(...))` không kiểm tra việc đọc query string. Để kiểm tra ranh giới HTTP, có thể dùng MockMvc.

Trong standalone setup, phải đăng ký resolver cần dùng. Ví dụ dưới đây sử dụng `PagingProbeController` ở phần 3:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.data.web.PageableHandlerMethodArgumentResolver;
import org.springframework.data.web.SortHandlerMethodArgumentResolver;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

class PagingResolverTest {

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        SortHandlerMethodArgumentResolver sortResolver =
            new SortHandlerMethodArgumentResolver();

        PageableHandlerMethodArgumentResolver pageableResolver =
            new PageableHandlerMethodArgumentResolver(sortResolver);

        pageableResolver.setMaxPageSize(100);

        mvc = standaloneSetup(new PagingProbeController())
            .setCustomArgumentResolvers(
                pageableResolver,
                sortResolver
            )
            .build();
    }

    @Test
    void bindsPageAndSeveralSortOrders() throws Exception {
        mvc.perform(get("/probe/page")
                .param("page", "2")
                .param("size", "15")
                .param("sort", "price,desc", "id,asc"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page").value(2))
            .andExpect(jsonPath("$.size").value(15))
            .andExpect(jsonPath("$.offset").value(30))
            .andExpect(jsonPath("$.orders[0].property")
                .value("price"))
            .andExpect(jsonPath("$.orders[0].direction")
                .value("DESC"))
            .andExpect(jsonPath("$.orders[1].property")
                .value("id"))
            .andExpect(jsonPath("$.orders[1].direction")
                .value("ASC"));
    }

    @Test
    void usesResolverFallback() throws Exception {
        mvc.perform(get("/probe/page"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page").value(0))
            .andExpect(jsonPath("$.size").value(20));
    }

    @Test
    void capsPageSize() throws Exception {
        mvc.perform(get("/probe/page")
                .param("page", "1")
                .param("size", "1000"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.size").value(100))
            .andExpect(jsonPath("$.offset").value(100));
    }
}
~~~

Ví dụ cần JUnit, spring-test và khả năng chuyển response thành JSON phù hợp. Đây là mã thực hành cho người học, không phải bằng chứng đã kiểm thử một ứng dụng store cụ thể.

Điểm quan trọng là truyền cùng `sortResolver` vào pageable resolver và đăng ký nó cho đối số `Sort` độc lập. Nếu hai nơi dùng hai instance có cấu hình khác nhau, endpoint nhận `Sort` và endpoint nhận `Pageable` có thể diễn giải cùng URL khác nhau.

Standalone setup kiểm tra những resolver được đưa trực tiếp vào test. Nó chưa chứng minh bean customizer hoặc auto-configuration của ứng dụng thật đã được áp dụng. Khi cần kiểm tra việc đăng ký bean, sử dụng một test có application context tương ứng.

Hai cách thiết lập được trình bày trong [Spring Framework — Configuring MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/setup.html).

## 15. Những trường hợp nên bổ sung khi thực hành

| Kịch bản | Điều cần xác nhận |
|---|---|
| Không truyền tham số | Fallback đúng hợp đồng endpoint |
| Có `@PageableDefault` | Giá trị mặc định riêng được áp dụng |
| Chỉ truyền `page` hoặc chỉ `size` | Phần còn lại dùng đúng mặc định |
| Nhiều tham số `sort` | Giữ thứ tự ưu tiên và hướng của từng order |
| Bật chỉ số HTTP từ 1 | Trang HTTP 1 tạo page nội bộ 0 |
| Đổi tên `sort` thành `order` | Cả đối số Sort và sort bên trong Pageable đọc cùng hợp đồng |
| Hai qualifier | Mỗi namespace điều khiển đúng đối số |
| Size rất lớn hoặc sai kiểu | Cơ chế chuẩn hóa phù hợp chính sách đã công bố |
| Thuộc tính sort không cho phép | Policy từ chối trước khi gọi truy vấn |
| Sort qua khóa public | Ánh xạ về đúng property của domain |
| Trang không có dữ liệu | Response rỗng vẫn giữ metadata theo hợp đồng |
| Query trên store thật | Sort, giới hạn, tổng và mapping hoạt động đúng |

Các kiểm tra cuối cần tầng tích hợp repository thật. MockMvc không chứng minh chỉ mục database phù hợp, query plan tốt hoặc một store hỗ trợ mọi tùy chọn sort.

Một giới hạn size hợp lý cũng không tự làm mọi query rẻ. Offset sâu, sắp xếp thiếu chỉ mục hoặc điều kiện lọc phức tạp có thể vẫn tốn tài nguyên.

## 16. Phân biệt Spring MVC với WebFlux

Hai lớp trong tiêu đề là resolver thuộc nhánh Spring MVC. Spring Data có những lớp tương ứng cho WebFlux, như `ReactivePageableHandlerMethodArgumentResolver` và `ReactiveSortHandlerMethodArgumentResolver`.

Không lấy cấu hình MVC rồi mặc định nó đã được áp dụng cho WebFlux. Cần kiểm tra hạ tầng web đang dùng và resolver thực sự được đăng ký.

Dù request được xử lý bằng MVC hay WebFlux, `Pageable` và `Sort` vẫn là metadata. Việc tạo ra chúng không đổi một repository đồng bộ thành reactive và không cung cấp thêm khả năng phân trang cho store.

Tham khảo [ReactivePageableHandlerMethodArgumentResolver](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/ReactivePageableHandlerMethodArgumentResolver.html) để nhận diện ranh giới này.

## 17. Chẩn đoán nhanh và bài thực hành

| Hiện tượng | Hướng kiểm tra |
|---|---|
| Spring không tạo được đối số Pageable | Resolver đã được đăng ký đúng MVC context chưa? |
| Thêm annotation làm size mặc định đổi | Có dùng mặc định 10 của PageableDefault không? |
| Frontend luôn lệch một trang | Quy ước số trang HTTP và nội bộ có thống nhất không? |
| Sort trong Pageable khác Sort độc lập | Hai resolver có dùng cùng cấu hình không? |
| Client gửi size lớn nhưng không nhận 400 | Resolver đang chuẩn hóa về trần thay vì validation nghiêm ngặt? |
| Sắp xếp theo property lạ gây lỗi truy vấn | Đã áp dụng tập khóa sort cho phép trước repository chưa? |
| Nhiều bảng cùng chuyển trang | Qualifier và tên query từng bảng đã tách đúng chưa? |
| Thứ tự thay đổi giữa các trang | Có khóa phân xử và có thay đổi dữ liệu đồng thời không? |
| Endpoint có Pageable nhưng vẫn tải toàn bộ | Service có thực sự truyền pageable vào truy vấn không? |
| Test standalone chạy, ứng dụng thật lỗi | Test có bỏ qua cấu hình đăng ký bean của ứng dụng không? |

Bài thực hành:

1. Dựng controller quan sát metadata và gọi URL có hai tham số sort.
2. Đặt mặc định theo endpoint, rồi so sánh với fallback của resolver.
3. Giới hạn size ở 100 và xác minh hành vi khi client gửi 1000.
4. Tạo một handler có hai pageable phân biệt bằng qualifier.
5. Bật chỉ số trang HTTP từ 1, kiểm tra trang nội bộ và response.
6. Thêm policy khóa sort public, ánh xạ khóa và nối ID khi cần.
7. Kết nối một repository của store được hỗ trợ, xác minh metadata được dùng trong truy vấn.
8. Viết rõ hợp đồng khi request sai, trang rỗng và dữ liệu thay đổi giữa các lần đọc.

Điều cần giải thích được sau thực hành là: **resolver chuyển tham số web thành yêu cầu phân trang/sắp xếp; ứng dụng quyết định chính sách được phép; repository của module store thực thi truy vấn; response thể hiện kết quả theo hợp đồng API**.
