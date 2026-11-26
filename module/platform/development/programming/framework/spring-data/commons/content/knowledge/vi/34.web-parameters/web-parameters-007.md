# Tùy chỉnh argument resolver và chính sách của ứng dụng

## 1. Mục tiêu và phạm vi

Trong chương **Tham số web** của module **Spring Data Commons**, argument resolver là điểm nối giữa dữ liệu HTTP và các abstraction như `Pageable`, `Sort`. Việc tùy chỉnh điểm nối này giúp ứng dụng thực thi một hợp đồng web nhất quán trước khi truy vấn dữ liệu.

Sau bài học, bạn cần làm được:

- Giải thích cách Spring MVC chọn resolver cho một tham số controller.
- Phân biệt đổi cấu hình resolver có sẵn với viết resolver mới.
- Áp dụng mặc định, giới hạn và quy tắc sort phù hợp với ứng dụng.
- Giới hạn phạm vi của resolver tùy chỉnh để tránh ảnh hưởng các endpoint khác.
- Chuyển đầu vào không hợp lệ thành lỗi HTTP rõ ràng.
- Kiểm tra rằng request thực sự đi qua resolver được cấu hình.

Ví dụ dùng **Spring MVC** và Java 17 trở lên. Các lớp `HandlerMethodArgumentResolver`, `NativeWebRequest` và `WebMvcConfigurer` thuộc hạ tầng MVC; các kiểu `Pageable`, `PageRequest`, `Sort` thuộc Spring Data Commons.

Bài không giả định một loại database cụ thể. Việc repository hoặc template thực thi `Pageable`, truy vấn đếm hay scrolling phải được xác nhận theo mô-đun lưu trữ đang dùng.

## 2. Argument resolver nằm ở đâu trong luồng xử lý?

Một controller có thể nhận trực tiếp:

~~~java
@GetMapping("/books")
Object list(Pageable pageable) {
    // Dùng pageable để gọi dịch vụ.
    return null;
}
~~~

Đây chỉ là hình dạng minh họa chữ ký, chưa phải endpoint hoàn chỉnh. Spring MVC cần hạ tầng phù hợp để tạo giá trị cho tham số `pageable`.

Luồng khái niệm:

~~~text
HTTP query parameters
        |
        v
Spring MVC xác định phương thức controller
        |
        v
Chọn resolver hỗ trợ từng tham số
        |
        v
Chuyển đổi + mặc định + kiểm tra theo chính sách
        |
        v
Giá trị tham số Java
        |
        v
Controller -> service -> repository/template -> store
~~~

Hai phương thức quan trọng của một resolver:

~~~java
boolean supportsParameter(MethodParameter parameter);

Object resolveArgument(
        MethodParameter parameter,
        ModelAndViewContainer container,
        NativeWebRequest request,
        WebDataBinderFactory binderFactory) throws Exception;
~~~

`supportsParameter` quyết định tham số nào thuộc trách nhiệm resolver. `resolveArgument` tạo giá trị tương ứng cho request hiện tại.

MVC chọn resolver hỗ trợ tham số trong chuỗi resolver đã đăng ký; việc một bean resolver tồn tại chưa chứng minh nó được dùng. Khi nhiều resolver đều hỗ trợ cùng một tham số, thứ tự trong chuỗi là điều cần kiểm soát.

Không nên đưa logic truy vấn database vào resolver chỉ để tạo một `Pageable`. Parsing tham số có thể hoàn tất trước khi gọi tầng dữ liệu.

## 3. Chọn mức tùy biến nhỏ nhất đáp ứng chính sách

| Nhu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| Đổi tên page/size, size mặc định hoặc trần size | Properties của Boot hoặc customizer cho resolver chuẩn |
| Mặc định khác nhau theo endpoint | `@PageableDefault`, `@SortDefault` khi phù hợp |
| Hai bộ phân trang trong cùng phương thức | Qualifier cùng cấu hình đặt tên tham số |
| Quy tắc sort công khai khác property của domain | Ánh xạ có kiểm soát trước khi tạo Sort |
| Phải từ chối đầu vào sai thay vì fallback | Kiểm tra đầu vào gốc hoặc resolver riêng |
| Một nhóm endpoint có hợp đồng đặc thù | Annotation và kiểu tham số chuyên biệt |
| Thay đổi toàn bộ cơ chế phân giải Pageable | Cấu hình hạ tầng có chủ đích, xác minh chuỗi resolver thực tế |

Không cần viết lại toàn bộ parser chỉ để đổi tên `page` thành `p`.

Ngược lại, đổi tên tham số hoặc đặt `maxPageSize` chưa đủ để tạo một API nghiêm ngặt. Resolver chuẩn có thể chuẩn hóa hoặc fallback một số đầu vào sai; hợp đồng yêu cầu HTTP 400 phải được thực hiện rõ ràng.

## 4. Tùy chỉnh resolver chuẩn

### 4.1. Properties khi Spring Boot tự cấu hình Spring Data Web

~~~yaml
spring:
  data:
    web:
      pageable:
        page-parameter: page
        size-parameter: size
        default-page-size: 25
        max-page-size: 100
        one-indexed-parameters: false
~~~

Đây là lựa chọn đơn giản khi chính sách chỉ cần các thiết lập tương ứng và auto-configuration đang có hiệu lực.

Các thuộc tính này không thay đổi mọi `PageRequest.of` được tạo thủ công trong tác vụ nền hoặc service khác.

Nếu dự án tự thay thế cấu hình Spring Data Web, cần xác nhận properties vẫn được hạ tầng đang dùng áp dụng. Không chỉ nhìn vào một khối YAML để kết luận request đã được giới hạn.

### 4.2. Customizer cho pageable và sort

Trong ứng dụng có tích hợp Spring Data Web áp dụng các bean customizer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.config.PageableHandlerMethodArgumentResolverCustomizer;
import org.springframework.data.web.config.SortHandlerMethodArgumentResolverCustomizer;

@Configuration(proxyBeanMethods = false)
class StandardPagingConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pageablePolicy() {
        return resolver -> {
            resolver.setPageParameterName("page");
            resolver.setSizeParameterName("size");
            resolver.setOneIndexedParameters(false);
            resolver.setFallbackPageable(
                    PageRequest.of(0, 25));
            resolver.setMaxPageSize(100);
        };
    }

    @Bean
    SortHandlerMethodArgumentResolverCustomizer sortPolicy() {
        return resolver -> {
            resolver.setSortParameter("sort");
            resolver.setFallbackSort(
                    Sort.by(Sort.Order.asc("id")));
        };
    }
}
~~~

Đây là một cách cấu hình bằng code; không cần lặp lại cùng chính sách ở cả properties lẫn nhiều customizer độc lập.

Một số điểm mở rộng cần phân biệt:

| Thiết lập | Tác động |
| --- | --- |
| Tên page/size | Query parameter được resolver đọc |
| Fallback Pageable | Giá trị dự phòng khi không có mặc định phù hợp khác |
| Max page size | Trần kích thước được resolver chuẩn tạo |
| One-indexed parameters | Quy đổi chỉ số đầu vào ở biên HTTP |
| Prefix | Thêm tiền tố cho tên tham số phân trang |
| Qualifier delimiter | Quy tắc ghép qualifier với tên tham số |
| Sort parameter | Tên tham số chứa chỉ dẫn sắp xếp |
| Fallback Sort | Thứ tự dự phòng của sort resolver |

Prefix của pageable và tên tham số sort không phải cùng một thiết lập. Khi tạo nhiều bộ phân trang có qualifier, hãy kiểm tra cả page, size và sort thay vì chỉ đổi một tên.

Ví dụ endpoint có `@Qualifier("books") Pageable` và `@Qualifier("authors") Pageable` thường dùng nhóm tham số có tên tương ứng như `books_page`, `books_size`, `books_sort`; quy tắc cuối cùng phụ thuộc tên và delimiter đã cấu hình.

Qualifier phân biệt các bộ tham số; nó không xác định quyền truy cập một tập dữ liệu.

### 4.3. Annotation mặc định không phải ràng buộc bắt buộc

~~~java
@GetMapping("/books")
Object list(
        @PageableDefault(size = 25, sort = "id") Pageable pageable) {
    return null;
}
~~~

Snippet chỉ minh họa annotation. Mặc định tại tham số có thể được dùng thay cho fallback toàn cục. Client vẫn có thể gửi size khác theo chính sách resolver.

Nếu endpoint cần size tối đa khác hoặc sort chỉ thuộc một danh sách cho phép, không coi annotation mặc định là cơ chế đã thực hiện đầy đủ các kiểm tra đó.

## 5. Chính sách ứng dụng cần được viết rõ

Giả sử nhóm endpoint catalog chọn một hợp đồng đặc thù:

| Thành phần | Chính sách |
| --- | --- |
| Số trang công khai | `p`, bắt đầu từ 1 |
| Kích thước trang | `limit`, mặc định 25, tối đa 100 |
| Chỉ dẫn sort | `order`, được phép lặp |
| Cú pháp order | `tênCôngKhai,asc` hoặc `tênCôngKhai,desc` |
| Tên sort công khai | `name`, `created`, `id` |
| Mặc định sort | `created` giảm dần, sau đó `id` tăng dần |
| Trang ngoài miền, số sai, tham số lặp không hợp lệ | HTTP 400 |
| Tham số ngoài hợp đồng | HTTP 400 |
| Offset tối đa | 100.000 |

Ví dụ hợp lệ:

~~~http
GET /catalog/books
GET /catalog/books?p=2&limit=25
GET /catalog/books?order=name,asc&order=created,desc
~~~

Các tên công khai được ánh xạ sang property của domain:

| Tên trong HTTP | Property chuyển vào Sort |
| --- | --- |
| `name` | `title` |
| `created` | `createdAt` |
| `id` | `id` |

Đây là ánh xạ property của mô hình truy vấn, không phải chỗ ghép tên cột hoặc biểu thức SQL từ chuỗi client.

Hợp đồng trong bài cố ý chỉ có ba tham số `p`, `limit`, `order`. Nếu endpoint cần bộ lọc, phải bổ sung tên tham số và chính sách tương ứng.

## 6. Dùng kiểu tham số chuyên biệt để giới hạn phạm vi resolver

Có thể để resolver mới xử lý trực tiếp `Pageable`, nhưng như vậy nó có thể cạnh tranh với resolver chuẩn. Một lựa chọn rõ ràng cho nhóm endpoint đặc thù là dùng một kiểu bọc:

~~~java
import java.util.Objects;

import org.springframework.data.domain.Pageable;

public record CatalogPage(Pageable pageable) {

    public CatalogPage {
        Objects.requireNonNull(pageable, "pageable");
    }
}
~~~

Và một annotation đánh dấu:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface CatalogPaging {
}
~~~

Mỗi kiểu `public` đặt trong file Java tương ứng khi triển khai thật. Các đoạn code của bài là ví dụ học tập trong tài liệu, không yêu cầu tạo các file đó tại bước viết nội dung này.

Controller sẽ nhận:

~~~java
@CatalogPaging CatalogPage paging
~~~

Resolver chỉ hỗ trợ đúng tổ hợp annotation và kiểu này. `Pageable` thông thường ở các endpoint khác tiếp tục thuộc hạ tầng chuẩn.

Annotation tự tạo không có hiệu lực nếu resolver chưa được đăng ký. Ngược lại, không nên viết `supportsParameter` chỉ kiểm tra annotation rồi trả về một object không tương thích với kiểu tham số.

## 7. Implementation resolver theo chính sách catalog

Resolver dưới đây không giữ trạng thái riêng của từng request trong field. Toàn bộ dữ liệu request nằm trong biến cục bộ; các hằng số và tập ánh xạ là bất biến.

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.core.MethodParameter;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;
import org.springframework.web.server.ResponseStatusException;

public final class CatalogPageResolver
        implements HandlerMethodArgumentResolver {

    private static final int DEFAULT_LIMIT = 25;
    private static final int MAX_LIMIT = 100;
    private static final int MAX_EXTERNAL_PAGE = 10_001;
    private static final long MAX_OFFSET = 100_000L;
    private static final int MAX_SORT_RULES = 3;

    private static final Set<String> QUERY_PARAMETERS =
            Set.of("p", "limit", "order");

    private static final Map<String, String> SORT_PROPERTIES =
            Map.of(
                    "name", "title",
                    "created", "createdAt",
                    "id", "id");

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.getParameterType() == CatalogPage.class
                && parameter.hasParameterAnnotation(CatalogPaging.class);
    }

    @Override
    public CatalogPage resolveArgument(
            MethodParameter parameter,
            ModelAndViewContainer container,
            NativeWebRequest request,
            WebDataBinderFactory binderFactory) {

        rejectUnknownParameters(request);

        int externalPage = positiveInt(
                "p", single(request, "p"), 1);
        int limit = positiveInt(
                "limit", single(request, "limit"), DEFAULT_LIMIT);

        if (externalPage > MAX_EXTERNAL_PAGE) {
            throw badRequest("p vượt giới hạn trang cho phép");
        }

        if (limit > MAX_LIMIT) {
            throw badRequest("limit phải nằm trong khoảng 1..100");
        }

        int internalPage = externalPage - 1;
        long offset = (long) internalPage * limit;
        if (offset > MAX_OFFSET) {
            throw badRequest("Offset yêu cầu vượt giới hạn");
        }

        Sort sort = parseSort(request.getParameterValues("order"));

        return new CatalogPage(
                PageRequest.of(internalPage, limit, sort));
    }

    private static void rejectUnknownParameters(
            NativeWebRequest request) {

        for (String name : request.getParameterMap().keySet()) {
            if (!QUERY_PARAMETERS.contains(name)) {
                throw badRequest("Tham số không được hỗ trợ: " + name);
            }
        }
    }

    private static String single(
            NativeWebRequest request, String name) {

        String[] values = request.getParameterValues(name);
        if (values == null) {
            return null;
        }

        if (values.length != 1 || values[0] == null) {
            throw badRequest(
                    "Tham số " + name + " phải có đúng một giá trị");
        }

        return values[0];
    }

    private static int positiveInt(
            String name, String raw, int fallback) {

        if (raw == null) {
            return fallback;
        }

        if (!raw.matches("[0-9]+")) {
            throw badRequest(
                    "Tham số " + name + " phải là số nguyên dương");
        }

        final int value;
        try {
            value = Integer.parseInt(raw);
        } catch (NumberFormatException exception) {
            throw badRequest(
                    "Tham số " + name + " vượt miền số nguyên hỗ trợ");
        }

        if (value < 1) {
            throw badRequest(
                    "Tham số " + name + " phải lớn hơn hoặc bằng 1");
        }

        return value;
    }

    private static Sort parseSort(String[] rawRules) {
        if (rawRules == null) {
            return Sort.by(
                    Sort.Order.desc("createdAt"),
                    Sort.Order.asc("id"));
        }

        if (rawRules.length < 1 || rawRules.length > MAX_SORT_RULES) {
            throw badRequest("order chỉ được có tối đa 3 quy tắc");
        }

        List<Sort.Order> orders = new ArrayList<>();
        Set<String> seenProperties = new HashSet<>();

        for (String rawRule : rawRules) {
            if (rawRule == null) {
                throw badRequest("order không được rỗng");
            }

            String[] parts = rawRule.split(",", -1);
            if (parts.length != 2) {
                throw badRequest(
                        "order phải có dạng tênThuộcTính,asc|desc");
            }

            String property = SORT_PROPERTIES.get(parts[0]);
            if (property == null) {
                throw badRequest(
                        "Tên sắp xếp không được hỗ trợ: " + parts[0]);
            }

            Sort.Direction direction;
            if ("asc".equals(parts[1])) {
                direction = Sort.Direction.ASC;
            } else if ("desc".equals(parts[1])) {
                direction = Sort.Direction.DESC;
            } else {
                throw badRequest("Hướng sắp xếp phải là asc hoặc desc");
            }

            if (!seenProperties.add(property)) {
                throw badRequest(
                        "Không được lặp thuộc tính sắp xếp");
            }

            orders.add(new Sort.Order(direction, property));
        }

        if (!seenProperties.contains("id")) {
            orders.add(Sort.Order.asc("id"));
        }

        return Sort.by(orders);
    }

    private static ResponseStatusException badRequest(String message) {
        return new ResponseStatusException(
                HttpStatus.BAD_REQUEST, message);
    }
}
~~~

### 7.1. Vì sao kiểm tra trước khi tạo PageRequest?

`PageRequest` bảo vệ những điều kiện cơ bản như page không âm, size lớn hơn 0. Nó không biết trần 100, quy ước `p` bắt đầu từ 1 hay alias `name` của ứng dụng.

Resolver thực hiện chính sách trước, sau đó tạo một giá trị Commons hợp lệ.

Công thức offset nhân theo `long` ngay từ đầu. Giới hạn external page được kiểm tra trước khi chuyển đổi, nên không dựa vào phép trừ trên một số ngoài miền để phát hiện lỗi.

### 7.2. Vì sao không gọi database trong supportsParameter?

`supportsParameter` chỉ cần kiểm tra metadata của tham số. Truy vấn dữ liệu tại đây làm quá trình chọn resolver phát sinh chi phí và side effect không liên quan.

Ngay cả trong `resolveArgument`, ví dụ cũng chỉ chuyển đổi đầu vào. Việc xác định người dùng có được xem sách nào thuộc trách nhiệm authorization và tầng ứng dụng.

### 7.3. Vì sao thêm id vào cuối Sort?

Nhiều sách có thể cùng title hoặc createdAt. Tiêu chí id phụ giúp tạo thứ tự xác định hơn nếu id là duy nhất trong tập dữ liệu.

Nếu client đã gửi `order=id,desc`, resolver giữ lựa chọn đó và không thêm một order id mâu thuẫn.

Đây không phải cơ chế snapshot. Khi dữ liệu thay đổi giữa các request, phân trang offset vẫn có thể quan sát phần tử dịch chuyển.

### 7.4. Cú pháp nghiêm ngặt là lựa chọn có chủ đích

Ví dụ không trim chuỗi, không nhận dấu cộng và chỉ nhận direction viết thường. Các giá trị như `limit= 25` hoặc `order=name,ASC` bị từ chối.

Ứng dụng có thể chọn cú pháp dễ dãi hơn, nhưng phải thay đổi parser cùng tài liệu và kiểm tra tương ứng.

Giới hạn ba quy tắc áp dụng cho đầu vào `order`. Khi client không chỉ định id, resolver có thể thêm một tiêu chí id phụ vào kết quả hiệu lực.

## 8. Đăng ký đúng vào chuỗi MVC

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
class CatalogWebConfiguration implements WebMvcConfigurer {

    @Override
    public void addArgumentResolvers(
            List<HandlerMethodArgumentResolver> resolvers) {

        resolvers.add(new CatalogPageResolver());
    }
}
~~~

Resolver ví dụ không có dependency nên có thể tạo trực tiếp tại cấu hình. Nếu cần một policy object hoặc một dịch vụ ánh xạ thuần, hãy inject dependency đó và đăng ký đúng instance.

Chỉ đánh dấu resolver bằng `@Component` không có nghĩa mọi cấu hình MVC sẽ tự thêm nó vào danh sách argument resolver.

Trong ứng dụng Boot, không thêm `@EnableWebMvc` chỉ vì muốn đăng ký resolver này. Annotation đó liên quan đến quyền điều khiển cấu hình MVC và có thể làm thay đổi auto-configuration ngoài mục tiêu đang thực hiện. `WebMvcConfigurer` là điểm mở rộng cần dùng trong ví dụ.

Resolver chuyên biệt không cần giành ưu tiên với pageable resolver chuẩn, vì kiểu đầu vào là `CatalogPage`. Nếu một dự án khác cũng có resolver hỗ trợ kiểu này, vẫn phải kiểm tra chuỗi thực tế.

## 9. Controller giữ vai trò điều phối

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record BookRow(Long id, String title, Instant createdAt) {
}

interface CatalogSearchService {
    Slice<BookRow> find(Pageable pageable);
}

record CatalogSlice<T>(
        List<T> content,
        long page,
        int size,
        int numberOfElements,
        boolean hasNext) {

    static <T> CatalogSlice<T> from(Slice<T> result) {
        return new CatalogSlice<>(
                result.getContent(),
                (long) result.getNumber() + 1L,
                result.getSize(),
                result.getNumberOfElements(),
                result.hasNext());
    }
}

@RestController
@RequestMapping("/catalog/books")
class CatalogBookController {

    private final CatalogSearchService service;

    CatalogBookController(CatalogSearchService service) {
        this.service = service;
    }

    @GetMapping
    CatalogSlice<BookRow> list(
            @CatalogPaging CatalogPage paging) {

        return CatalogSlice.from(
                service.find(paging.pageable()));
    }
}
~~~

`CatalogSearchService` là hợp đồng do ứng dụng định nghĩa; cần implementation dùng repository hoặc template phù hợp với store.

Ví dụ chọn `Slice` vì chỉ cần biết còn dữ liệu tiếp theo, không công bố tổng số phần tử. Không thêm `totalElements` bằng cách đoán từ page size.

Chỉ số trong `Pageable` và `Slice` bắt đầu từ 0. DTO chuyển sang chỉ số công khai bắt đầu từ 1 đúng một lần khi tạo phản hồi.

Controller không lặp lại parser. Các request không hợp lệ bị từ chối trước khi gọi service; các quy tắc nghiệp vụ như phạm vi catalog hay quyền xem dữ liệu vẫn do tầng ứng dụng xử lý.

## 10. Nếu cần giữ nguyên chữ ký Pageable

Một số dự án muốn controller tiếp tục nhận:

~~~java
@GetMapping("/books")
Object list(@ApplicationPaging Pageable pageable) {
    return null;
}
~~~

Đây là một thiết kế khác, không phải annotation đã được implementation ở trên cung cấp.

Nếu viết resolver cho tổ hợp annotation và `Pageable`, resolver chuẩn cũng có thể hỗ trợ cùng tham số theo kiểu `Pageable`. Khi đó phải giải quyết:

1. Resolver nào xuất hiện trước trong chuỗi thực tế.
2. Annotation nào xác định phạm vi chính sách.
3. Endpoint không có annotation sẽ đi qua resolver nào.
4. Mặc định và qualifier có còn được bảo toàn không.
5. Test chứng minh resolver ứng dụng được chọn.

Không coi `@Order` trên chính class resolver là cam kết đủ để nó tự có thứ tự mong muốn trong mọi cơ chế đăng ký. Cách các configurer thêm resolver và thứ tự cuối cùng trong handler adapter mới quyết định hành vi.

Nếu muốn thay toàn bộ resolver chuẩn, dùng điểm mở rộng cấu hình Spring Data Web phù hợp với phiên bản và các tích hợp đang có. Đặc biệt, ứng dụng dùng liên kết phân trang hoặc Spring HATEOAS cần giữ nhất quán cơ chế parse tham số và cơ chế tạo liên kết.

Trong phần lớn trường hợp có hợp đồng riêng cho một nhóm endpoint, kiểu bọc chuyên biệt giúp tránh sự cạnh tranh đó và làm chính sách hiện rõ ngay tại chữ ký.

## 11. Tách chính sách HTTP khỏi nghiệp vụ và bảo mật

Resolver có thể kiểm tra cú pháp và miền đầu vào, nhưng không nên trở thành nơi tập trung mọi logic.

| Quy tắc | Vị trí thích hợp |
| --- | --- |
| Query parameter có đúng tên không | Biên HTTP/resolver |
| p, limit có đúng cú pháp và miền không | Resolver hoặc parser của hợp đồng |
| Alias sort được phép là gì | Policy của endpoint hoặc nhóm endpoint |
| Người dùng được truy cập tenant nào | Authorization và tầng ứng dụng |
| Query có hỗ trợ Sort đó không | Implementation truy vấn của mô-đun lưu trữ |
| Chỉ mục, timeout, execution plan | Thiết kế và cấu hình store |
| Giới hạn batch cho tác vụ nền | Tầng ứng dụng của đường gọi đó |

Không lấy `tenantId` từ query rồi coi nó là bằng chứng người dùng được phép truy cập tenant đó.

Danh sách sort cho phép giúp giới hạn hợp đồng và các truy vấn hỗ trợ. Nó không thay thế parameter binding hoặc cơ chế chống injection của đường truy vấn.

Tương tự, limit nhỏ không bảo đảm mọi truy vấn rẻ. Offset lớn, join, bộ lọc và cách store tạo kết quả có thể chi phối chi phí.

Nếu service được gọi từ cả HTTP lẫn tác vụ nền, các ràng buộc nghiệp vụ cần thiết phải tồn tại tại tầng dùng chung. Resolver chỉ bảo vệ đường HTTP được cấu hình qua nó.

## 12. Thiết kế lỗi và tính nhất quán

`ResponseStatusException` trong ví dụ biểu diễn HTTP 400. Body lỗi phụ thuộc cơ chế xử lý exception của ứng dụng; không mặc định reason sẽ luôn được serialize thành một trường cụ thể.

Với API cần định dạng ổn định, có thể dùng exception chính sách riêng và `@RestControllerAdvice` để ánh xạ sang cấu trúc lỗi thống nhất.

Một hợp đồng lỗi nên giúp client phân biệt:

- Sai cú pháp số.
- Ngoài miền cho phép.
- Tham số lặp.
- Tên sort không được hỗ trợ.
- Trùng thuộc tính sort.
- Vượt giới hạn độ sâu trang.

Không trả stack trace hoặc thông tin hạ tầng query cho client chỉ để giải thích một lỗi input.

Metadata thành công cũng phải phản ánh chính sách đã áp dụng. Nếu code bổ sung id vào Sort hoặc chuyển p sang chỉ số nội bộ, tầng tiếp theo cần nhận giá trị đã được chuẩn hóa; response không nên mâu thuẫn với cách phân trang thực sự.

Khi đổi tên tham số hoặc chuyển quy ước chỉ số trong API đã có client, cần xem đây là một thay đổi hợp đồng HTTP. Thực hiện phiên bản hóa hoặc lộ trình chuyển đổi phù hợp thay vì đổi âm thầm.

## 13. Kiểm tra resolver và đường HTTP

### 13.1. Kiểm tra phạm vi hỗ trợ

| Tham số controller | supportsParameter của resolver ví dụ |
| --- | --- |
| `@CatalogPaging CatalogPage` | true |
| `CatalogPage` không annotation | false |
| `@CatalogPaging Pageable` | false |
| `Pageable` thông thường | false |
| `String` thông thường | false |

Việc trả false cho một tổ hợp không hợp lệ không có nghĩa ứng dụng sẽ luôn tạo một lỗi cấu hình dễ hiểu. Cần kiểm tra chữ ký endpoint để tránh annotation đặt sai.

### 13.2. Kiểm tra giá trị được tạo

| Query | Kết quả cần xác minh |
| --- | --- |
| Không có tham số | Page nội bộ 0, size 25, sort createdAt DESC và id ASC |
| `p=2&limit=25` | Page nội bộ 1, offset 25 |
| `order=name,asc` | title ASC, sau đó id ASC |
| `order=id,desc` | id DESC, không có id ASC bổ sung |
| `order=name,asc&order=created,desc` | Giữ thứ tự hai quy tắc và thêm id ASC |

Một kiểm tra resolver trực tiếp có thể dựng request như sau:

~~~java
MockHttpServletRequest servletRequest =
        new MockHttpServletRequest();
servletRequest.addParameter("p", "2");
servletRequest.addParameter("limit", "25");

CatalogPage resolved = new CatalogPageResolver().resolveArgument(
        methodParameter,
        null,
        new ServletWebRequest(servletRequest),
        null);

assertEquals(1, resolved.pageable().getPageNumber());
assertEquals(25, resolved.pageable().getPageSize());
assertEquals(25L, resolved.pageable().getOffset());
~~~

Snippet giả định `methodParameter` đại diện cho tham số `@CatalogPaging CatalogPage`, cùng các import từ Spring Test, Spring Web và thư viện assertion. Nó minh họa kiểm tra parser và giá trị kết quả, chưa chứng minh cấu hình MVC đã đăng ký resolver.

### 13.3. Kiểm tra các nhánh HTTP 400

| Query | Nguyên nhân từ chối |
| --- | --- |
| `p=0` hoặc `p=-1` | Không thuộc miền p dương |
| `p=abc` hoặc `p=` | Sai cú pháp |
| `p=2147483648` | Vượt miền int |
| `p=10002` | Vượt trần external page |
| `p=2001&limit=100` | Offset 200.000 vượt giới hạn |
| `limit=0` hoặc `limit=101` | Size ngoài miền |
| `p=1&p=2` | p xuất hiện nhiều lần |
| `order=price,asc` | Sort ngoài danh sách cho phép |
| `order=name,ASC` | Direction không đúng cú pháp đã chọn |
| `order=name` | Thiếu direction |
| `order=name,asc&order=name,desc` | Trùng property |
| Bốn giá trị order | Vượt số quy tắc đầu vào |
| `page=1` | Tên tham số ngoài hợp đồng catalog |

Với MockMvc đã cấu hình đúng controller và resolver:

~~~java
mockMvc.perform(get("/catalog/books")
        .param("limit", "101"))
    .andExpect(status().isBadRequest());

verifyNoInteractions(service);
~~~

Snippet giả định mock service sạch tại đầu test và các static import tương ứng. Điều quan trọng là chứng minh service chưa được gọi khi input sai.

### 13.4. Kiểm tra wiring thật

Có thể dùng test standalone với:

~~~java
MockMvcBuilders.standaloneSetup(controller)
    .setCustomArgumentResolvers(new CatalogPageResolver())
    .build();
~~~

Cách này kiểm tra controller và resolver được cung cấp trong test, nhưng chưa chứng minh class cấu hình của ứng dụng đã được scan.

Cần thêm kiểm tra MVC với context ứng dụng phù hợp để xác nhận:

- Resolver được đăng ký qua cấu hình thật.
- Endpoint catalog nhận đúng policy.
- Endpoint `Pageable` thông thường vẫn hoạt động theo cấu hình chuẩn.
- Exception được chuyển thành định dạng lỗi đã công bố.
- Chỉ số phản hồi và liên kết điều hướng khớp quy ước công khai.

Không dùng một test gọi trực tiếp `resolveArgument` để kết luận thứ tự resolver hoặc auto-configuration đã đúng.

## 14. Các lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ tạo bean resolver | MVC có thể không dùng nó | Đăng ký qua cấu hình MVC phù hợp |
| supportsParameter nhận mọi Pageable | Chính sách lan sang endpoint ngoài ý muốn | Giới hạn annotation/kiểu hoặc cấu hình thay thế có chủ đích |
| Cho rằng maxPageSize luôn trả 400 | Hợp đồng khác với hành vi fallback/cắt giảm | Viết kiểm tra raw input khi cần nghiêm ngặt |
| Tùy chỉnh pageable nhưng bỏ quên sort | Tên tham số và chính sách không đồng bộ | Cấu hình và kiểm tra cả hai |
| Bật @EnableWebMvc chỉ để thêm resolver | Có thể thay đổi cấu hình Boot rộng hơn dự kiến | Dùng điểm mở rộng WebMvcConfigurer |
| Lưu dữ liệu request vào field mutable | Request đồng thời có thể ảnh hưởng nhau | Dùng biến cục bộ và policy bất biến |
| Truy vấn database trong supportsParameter | Chọn resolver gây I/O không cần thiết | Chỉ kiểm tra metadata tham số |
| Nhận trực tiếp tên sort bất kỳ | Query không được hỗ trợ hoặc lộ cấu trúc nội bộ | Dùng danh sách cho phép và ánh xạ |
| Chuyển chỉ số bắt đầu từ 1 hai lần | Lấy sai cửa sổ dữ liệu | Chuyển ở một điểm duy nhất |
| Chỉ test parser | Không phát hiện lỗi wiring MVC | Kiểm tra thêm đường HTTP có context |

## 15. Bài thực hành

1. Xác định một hợp đồng phân trang hiện có và liệt kê phần nào giải quyết được bằng resolver chuẩn.
2. Cấu hình mặc định và trần size bằng properties hoặc customizer, tránh khai báo chồng chéo.
3. Thiết kế một nhóm endpoint có chính sách riêng bằng annotation và kiểu tham số chuyên biệt.
4. Ánh xạ tối thiểu hai tên sort công khai sang property domain.
5. Từ chối số sai, tham số lặp, sort không hỗ trợ và offset vượt giới hạn trước khi gọi service.
6. Giữ controller chỉ điều phối và phản hồi metadata nhất quán với quy ước chỉ số.
7. Kiểm tra phạm vi supportsParameter, giá trị phân giải và wiring MVC.
8. Giải thích những quy tắc nào vẫn phải được bảo vệ tại tầng ứng dụng và mô-đun lưu trữ.

Bài thực hành hoàn thành khi resolver trở thành một biên chuyển đổi rõ ràng: **hợp đồng HTTP được áp dụng có phạm vi**, **đầu vào sai có kết quả xác định**, và **các abstraction Spring Data Commons được truyền xuống tầng truy vấn với đúng ý nghĩa**.
