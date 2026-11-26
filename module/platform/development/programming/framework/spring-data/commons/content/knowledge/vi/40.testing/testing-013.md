# Kiểm thử tham số web, JSON phân trang và giới hạn đầu vào

## Mục tiêu và phạm vi

Một repository trả đúng `Page` chưa chứng minh endpoint phân trang hoạt động đúng. Tham số HTTP còn phải được chuyển thành yêu cầu truy vấn, dữ liệu cần được chuyển thành JSON ổn định và các giới hạn đầu vào phải được thực thi trước khi ứng dụng truy cập store.

Trong Spring Data Commons, `Pageable`, `Page`, `Slice` và `Sort` giúp mô tả hợp đồng truy xuất. Chúng không tự quyết định toàn bộ chính sách của API công khai.

Sau bài học này, bạn có thể:

- Kiểm tra cách endpoint nhận page, size và nhiều tiêu chí sort.
- Phân biệt giá trị mặc định, chuẩn hóa đầu vào và từ chối đầu vào.
- Kiểm tra JSON của trang đầu, trang cuối và trang rỗng.
- Bảo vệ các giới hạn về kích thước trang, độ sâu phân trang và trường sắp xếp.
- Tách kiểm thử controller, cấu hình web thực tế và repository của từng store.

Ví dụ dùng Spring MVC, MockMvc, JUnit Jupiter, Mockito và Jackson. Với WebFlux, cần dùng cơ chế kiểm thử web tương ứng và không áp đặt giả định thực thi đồng bộ của ví dụ.

## 1. Ba hợp đồng cần kiểm tra riêng

```text
HTTP query
    |
    v
Chuyển đổi và kiểm tra đầu vào
    |
    v
Pageable / Sort
    |
    v
Service và repository của store
    |
    v
Page / Slice
    |
    v
DTO JSON công khai
```

Ba hợp đồng chính là:

| Hợp đồng | Câu hỏi cần trả lời |
|---|---|
| Đầu vào web | Thiếu tham số thì dùng gì? Giá trị sai bị từ chối hay chuẩn hóa? |
| Gọi tầng dữ liệu | Service nhận đúng page index, size và thứ tự sort không? |
| Đầu ra JSON | Nội dung, metadata, tên trường và trạng thái lỗi có đúng hợp đồng công khai không? |

Mock repository hoặc service có thể giúp kiểm tra controller, nhưng không xác minh database thực hiện đúng truy vấn. Ngược lại, integration test repository không kiểm tra tên query parameter hoặc JSON HTTP.

## 2. Viết rõ chính sách trước khi viết assertion

Ví dụ dưới đây chọn hợp đồng ứng dụng như sau:

| Đầu vào | Chính sách |
|---|---|
| `page` | Bắt đầu từ 0; mặc định 0; hợp lệ từ 0 đến 1000 |
| `size` | Mặc định 20; hợp lệ từ 1 đến 100 |
| `sort` | Có thể lặp tối đa 3 lần; mỗi giá trị có dạng `property,direction` |
| Property được phép | `id`, `name`, `price` |
| Direction | Chỉ nhận chính xác `asc` hoặc `desc` |
| Không có sort | Dùng `id ASC` |
| Sort chưa có id | Thêm `id ASC` làm khóa phụ |
| Lặp page hoặc size | HTTP 400 |
| Lặp một property sort | HTTP 400 |
| Tham số không được hỗ trợ | HTTP 400 |
| Giá trị số rỗng, âm, thập phân hoặc tràn miền số | HTTP 400 |

Đây là quyết định của API minh họa, không phải toàn bộ hành vi mặc định của Spring Data.

Ví dụ request hợp lệ:

```text
GET /products?page=0&size=2&sort=price,desc&sort=id,asc
```

Sort công khai cũng được giới hạn để tránh cho client chọn tùy ý đường dẫn property nội bộ, liên kết phức tạp hoặc trường không được hỗ trợ.

Nếu API chọn page bắt đầu từ 1, hãy ghi rõ việc chuyển đổi sang page index nội bộ bắt đầu từ 0. Không để client phải suy đoán từ kết quả.

## 3. Resolver Pageable không thay thế chính sách validation

Spring Data có tích hợp web để chuyển tham số request thành `Pageable` và `Sort`. Dự án có thể cấu hình tên tham số, giá trị mặc định, cách đánh số và kích thước tối đa.

Tuy nhiên, cần phân biệt:

- Một giá trị không có mặt.
- Một giá trị sai định dạng.
- Một giá trị vượt giới hạn.
- Một giá trị bị thay bằng fallback.
- Một giá trị bị giảm xuống mức tối đa.
- Một giá trị khiến request bị từ chối.

Tùy resolver và cấu hình, một số đầu vào có thể được chuẩn hóa thay vì trả lỗi. Vì vậy, test không nên mặc định rằng mọi `size` vượt mức đều tự tạo HTTP 400.

`@PageableDefault` cung cấp thông tin mặc định; nó không tự biểu diễn đầy đủ mọi quy tắc validation của API. Tương tự, không mặc định đặt constraint lên `Pageable` sẽ khiến framework kiểm tra mọi thuộc tính bên trong theo chính sách mong muốn.

Ví dụ trong bài dùng một parser tường minh để minh họa chính sách từ chối đầu vào. Nếu dự án dùng resolver tùy biến hoặc cơ chế validation khác, hãy kiểm tra đúng đường xử lý đó trong context thật.

Không thêm parser thứ hai chỉ để mô phỏng một hợp đồng khác với endpoint đang chạy.

## 4. Parser chuyển query thành Pageable

Parser sau chỉ phụ trách các query parameter của endpoint minh họa. Nếu endpoint còn có bộ lọc, cần mở rộng hợp đồng cho các bộ lọc đó một cách rõ ràng.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Component;
import org.springframework.util.MultiValueMap;

@Component
public class PagingQueryParser {

    private static final Set<String> PARAMETERS =
            Set.of("page", "size", "sort");

    private static final Set<String> SORT_PROPERTIES =
            Set.of("id", "name", "price");

    public Pageable parse(MultiValueMap<String, String> query) {
        for (String key : query.keySet()) {
            if (!PARAMETERS.contains(key)) {
                throw invalid(
                        "query",
                        "Unsupported query parameter");
            }
        }

        int page = integer(query, "page", 0, 0, 1000);
        int size = integer(query, "size", 20, 1, 100);

        return PageRequest.of(page, size, sort(query));
    }

    private int integer(
            MultiValueMap<String, String> query,
            String field,
            int defaultValue,
            int min,
            int max) {

        List<String> values = query.get(field);

        if (values == null) {
            return defaultValue;
        }

        if (values.size() != 1) {
            throw invalid(
                    field,
                    "Parameter must occur exactly once");
        }

        String raw = values.get(0);

        if (raw == null || !raw.matches("[0-9]+")) {
            throw invalid(
                    field,
                    "Expected an unsigned decimal integer");
        }

        final int value;

        try {
            value = Integer.parseInt(raw);
        } catch (NumberFormatException ex) {
            throw invalid(field, "Integer is out of range");
        }

        if (value < min || value > max) {
            throw invalid(
                    field,
                    "Value is outside the allowed range");
        }

        return value;
    }

    private Sort sort(MultiValueMap<String, String> query) {
        List<String> specifications =
                query.getOrDefault("sort", List.of());

        if (specifications.size() > 3) {
            throw invalid("sort", "Too many sort criteria");
        }

        List<Sort.Order> orders = new ArrayList<>();
        Set<String> seen = new HashSet<>();

        for (String specification : specifications) {
            if (specification == null) {
                throw invalid("sort", "Invalid sort criterion");
            }

            String[] parts = specification.split(",", -1);

            if (parts.length != 2
                    || !SORT_PROPERTIES.contains(parts[0])) {
                throw invalid("sort", "Invalid sort criterion");
            }

            if (!seen.add(parts[0])) {
                throw invalid("sort", "Duplicate sort property");
            }

            Sort.Direction direction = switch (parts[1]) {
                case "asc" -> Sort.Direction.ASC;
                case "desc" -> Sort.Direction.DESC;
                default -> throw invalid(
                        "sort",
                        "Direction must be asc or desc");
            };

            orders.add(new Sort.Order(direction, parts[0]));
        }

        if (!seen.contains("id")) {
            orders.add(Sort.Order.asc("id"));
        }

        return Sort.by(orders);
    }

    private PagingInputException invalid(
            String field,
            String message) {
        return new PagingInputException(field, message);
    }
}
```

Lớp exception dùng trong các đoạn mã:

```java
public class PagingInputException extends RuntimeException {

    private final String field;

    public PagingInputException(
            String field,
            String message) {
        super(message);
        this.field = field;
    }

    public String getField() {
        return field;
    }
}
```

Parser không dùng `getFirst` để âm thầm bỏ qua các giá trị page hoặc size bị lặp. Nó cũng bắt lỗi tràn số trước khi tạo `PageRequest`.

Với page tối đa 1000 và size tối đa 100, offset được giới hạn ở 100000. Đây là giới hạn minh họa; ngưỡng thực tế cần dựa trên hợp đồng và khả năng vận hành của endpoint.

Nếu tên trường công khai khác property của entity, hãy ánh xạ qua danh sách cho phép. Không chuyển trực tiếp mọi chuỗi client gửi vào property path của repository.

## 5. Dùng DTO để kiểm soát JSON phân trang

Không nên coi mọi chi tiết serialization của một implementation `Page` là hợp đồng JSON ổn định của ứng dụng.

Một lựa chọn là dùng DTO riêng. Các dự án dùng mô hình phân trang do framework hỗ trợ cũng cần cấu hình và kiểm thử đúng mô hình đã chọn.

Ví dụ các kiểu DTO:

```java
import java.math.BigDecimal;

public record ProductRow(
        Long id,
        String name,
        BigDecimal price) {
}
```

```java
public record SortRule(
        String property,
        String direction) {
}
```

```java
import java.util.List;
import java.util.Locale;

import org.springframework.data.domain.Page;

public record PageResponse<T>(
        List<T> content,
        int number,
        int size,
        long totalElements,
        int totalPages,
        boolean first,
        boolean last,
        boolean hasNext,
        List<SortRule> sort) {

    public static <T> PageResponse<T> from(Page<T> page) {
        List<SortRule> sortRules = page.getSort().stream()
                .map(order -> new SortRule(
                        order.getProperty(),
                        order.getDirection().name()
                                .toLowerCase(Locale.ROOT)))
                .toList();

        return new PageResponse<>(
                List.copyOf(page.getContent()),
                page.getNumber(),
                page.getSize(),
                page.getTotalElements(),
                page.getTotalPages(),
                page.isFirst(),
                page.isLast(),
                page.hasNext(),
                sortRules);
    }
}
```

DTO giữ riêng:

- `size`: kích thước trang theo hợp đồng phân trang.
- `content.size()`: số phần tử thực có trên trang.
- `totalElements`: tổng số phần tử khớp điều kiện.
- `totalPages`: tổng số trang tương ứng.

Trang cuối có thể có một phần tử trong khi size vẫn bằng 2. Trang vượt phạm vi có content rỗng nhưng totalElements vẫn lớn hơn 0.

Nếu tầng dữ liệu trả `Slice`, không tự thêm tổng số phần tử giả vào DTO. Hãy dùng hợp đồng đầu ra phù hợp với thông tin mà Slice cung cấp.

## 6. Controller và JSON lỗi

Service contract cho ví dụ:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface ProductCatalog {
    Page<ProductRow> findPage(Pageable pageable);
}
```

Controller:

```java
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    private final PagingQueryParser parser;
    private final ProductCatalog catalog;

    public ProductController(
            PagingQueryParser parser,
            ProductCatalog catalog) {
        this.parser = parser;
        this.catalog = catalog;
    }

    @GetMapping("/products")
    public PageResponse<ProductRow> list(
            @RequestParam
            MultiValueMap<String, String> query) {

        return PageResponse.from(
                catalog.findPage(parser.parse(query)));
    }
}
```

Error DTO và handler:

```java
public record PagingError(
        String code,
        String field,
        String message) {
}
```

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class PagingErrorHandler {

    @ExceptionHandler(PagingInputException.class)
    public ResponseEntity<PagingError> invalidPaging(
            PagingInputException exception) {

        return ResponseEntity.badRequest().body(
                new PagingError(
                        "INVALID_PAGING",
                        exception.getField(),
                        exception.getMessage()));
    }
}
```

Handler chỉ chuyển lỗi đầu vào được định nghĩa thành HTTP 400. Không bắt mọi exception rồi trả 400, vì lỗi truy cập store hoặc lỗi lập trình không phải lỗi cú pháp tham số của client.

Các thông báo trong ví dụ không chứa query database, stack trace hoặc tên lớp persistence nội bộ.

## 7. Khung kiểm thử HTTP bằng MockMvc

Khung sau dựng controller theo kiểu standalone để kiểm tra request mapping, parser, handler và JSON. Nó không tự tải toàn bộ cấu hình Spring Boot, security filter hoặc resolver tùy biến của ứng dụng.

```java
import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ProductControllerPagingTest {

    private ProductCatalog catalog;
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        catalog = mock(ProductCatalog.class);

        mvc = MockMvcBuilders.standaloneSetup(
                new ProductController(
                        new PagingQueryParser(),
                        catalog))
                .setControllerAdvice(new PagingErrorHandler())
                .build();
    }

    private ProductRow row(long id, String name, String price) {
        return new ProductRow(
                id,
                name,
                new BigDecimal(price));
    }

    private void givenPage(
            List<ProductRow> rows,
            long total) {

        when(catalog.findPage(any(Pageable.class)))
                .thenAnswer(invocation -> {
                    Pageable request = invocation.getArgument(0);

                    return new PageImpl<>(
                            rows,
                            request,
                            total);
                });
    }

    @Test
    void validRequestHasExpectedJsonAndPageable()
            throws Exception {

        givenPage(
                List.of(
                        row(105L, "Charger", "40.00"),
                        row(104L, "Hub", "30.00")),
                5);

        mvc.perform(get("/products")
                        .param("page", "0")
                        .param("size", "2")
                        .param("sort", "price,desc", "id,asc"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.content.length()").value(2))
                .andExpect(jsonPath("$.content[0].id").value(105))
                .andExpect(jsonPath("$.content[1].id").value(104))
                .andExpect(jsonPath("$.number").value(0))
                .andExpect(jsonPath("$.size").value(2))
                .andExpect(jsonPath("$.totalElements").value(5))
                .andExpect(jsonPath("$.totalPages").value(3))
                .andExpect(jsonPath("$.first").value(true))
                .andExpect(jsonPath("$.last").value(false))
                .andExpect(jsonPath("$.hasNext").value(true))
                .andExpect(jsonPath("$.sort[0].property")
                        .value("price"))
                .andExpect(jsonPath("$.sort[0].direction")
                        .value("desc"))
                .andExpect(jsonPath("$.sort[1].property")
                        .value("id"));

        ArgumentCaptor<Pageable> captured =
                ArgumentCaptor.forClass(Pageable.class);

        verify(catalog).findPage(captured.capture());

        Pageable request = captured.getValue();

        assertThat(request.getPageNumber()).isZero();
        assertThat(request.getPageSize()).isEqualTo(2);
        assertThat(request.getOffset()).isZero();
        assertThat(request.getSort().toList())
                .containsExactly(
                        Sort.Order.desc("price"),
                        Sort.Order.asc("id"));
    }
}
```

Kiểm thử này xác nhận controller truyền đúng Sort xuống service. Nó không chứng minh database đã thực hiện sort đúng, vì dữ liệu của service là mock.

Các test ở phần sau được thêm vào cùng lớp này.

## 8. Kiểm thử giá trị mặc định và khóa sắp xếp phụ

Khi không có query parameter:

```java
@Test
void missingParametersUseThePublishedDefaults()
        throws Exception {

    givenPage(
            List.of(row(101L, "Cable", "10.00")),
            1);

    mvc.perform(get("/products"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.number").value(0))
            .andExpect(jsonPath("$.size").value(20))
            .andExpect(jsonPath("$.sort[0].property").value("id"))
            .andExpect(jsonPath("$.sort[0].direction").value("asc"));

    ArgumentCaptor<Pageable> captured =
            ArgumentCaptor.forClass(Pageable.class);

    verify(catalog).findPage(captured.capture());

    assertThat(captured.getValue().getPageNumber()).isZero();
    assertThat(captured.getValue().getPageSize()).isEqualTo(20);
    assertThat(captured.getValue().getSort())
            .isEqualTo(Sort.by(Sort.Order.asc("id")));
}
```

Khi client chỉ gửi `sort=price,desc`, cần thêm một test xác nhận Sort cuối cùng là:

```text
price DESC, id ASC
```

Khi client đã gửi `sort=id,desc`, parser phải giữ `id DESC`, không thêm `id ASC` lần nữa.

Khóa phụ giúp thứ tự được xác định khi giá bằng nhau. Nó không tự tạo snapshot ổn định nếu dữ liệu được thêm hoặc xóa giữa những request phân trang.

## 9. Kiểm thử JSON của trang cuối và hai dạng rỗng

### 9.1. Trang cuối không đủ kích thước

```java
@Test
void finalPageKeepsRequestedSize()
        throws Exception {

    givenPage(
            List.of(row(105L, "Charger", "40.00")),
            5);

    mvc.perform(get("/products")
                    .param("page", "2")
                    .param("size", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.content.length()").value(1))
            .andExpect(jsonPath("$.number").value(2))
            .andExpect(jsonPath("$.size").value(2))
            .andExpect(jsonPath("$.totalElements").value(5))
            .andExpect(jsonPath("$.totalPages").value(3))
            .andExpect(jsonPath("$.last").value(true))
            .andExpect(jsonPath("$.hasNext").value(false));
}
```

### 9.2. Không có dữ liệu khớp

```java
@Test
void noMatchesProduceAnEmptyArrayAndZeroTotal()
        throws Exception {

    givenPage(List.of(), 0);

    mvc.perform(get("/products")
                    .param("page", "0")
                    .param("size", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.content").isArray())
            .andExpect(jsonPath("$.content.length()").value(0))
            .andExpect(jsonPath("$.totalElements").value(0))
            .andExpect(jsonPath("$.totalPages").value(0))
            .andExpect(jsonPath("$.hasNext").value(false));
}
```

### 9.3. Trang vượt phạm vi

```java
@Test
void pageBeyondTheEndPreservesTheNonzeroTotal()
        throws Exception {

    givenPage(List.of(), 5);

    mvc.perform(get("/products")
                    .param("page", "3")
                    .param("size", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.content.length()").value(0))
            .andExpect(jsonPath("$.number").value(3))
            .andExpect(jsonPath("$.size").value(2))
            .andExpect(jsonPath("$.totalElements").value(5))
            .andExpect(jsonPath("$.totalPages").value(3))
            .andExpect(jsonPath("$.hasNext").value(false));
}
```

Ví dụ chọn trả HTTP 200 với một trang rỗng hợp lệ. Nếu API có chính sách khác, hãy kiểm thử chính sách được công bố.

Không chuyển mọi content rỗng thành HTTP 404. Truy vấn danh sách không có phần tử khác với truy xuất một tài nguyên đơn lẻ không tồn tại.

JSON cũng nên giữ `content: []`, thay vì lúc trả array rỗng, lúc trả null hoặc bỏ hẳn trường.

## 10. Kiểm thử biên số và lỗi định dạng

Các trường hợp cần có:

| Tham số | Hợp lệ ở biên | Không hợp lệ |
|---|---|---|
| page | 0, 1000 | -1, 1001, 1.5, rỗng, chuỗi không phải số |
| size | 1, 100 | 0, -1, 101, 2.5, rỗng |
| Cả hai | Chuỗi số nguyên nằm trong miền cho phép | Chuỗi số vượt miền integer |

Có thể dùng parameterized test cho các giá trị có cùng expected behavior.

Bổ sung import:

```java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
```

Ví dụ:

```java
@ParameterizedTest
@ValueSource(strings = {
        "-1", "1001", "1.5", "", "abc",
        "999999999999999999999999"
})
void invalidPageIsRejectedBeforeCallingTheCatalog(
        String value) throws Exception {

    mvc.perform(get("/products")
                    .param("page", value))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code")
                    .value("INVALID_PAGING"))
            .andExpect(jsonPath("$.field").value("page"));

    verifyNoInteractions(catalog);
}

@ParameterizedTest
@ValueSource(strings = {"0", "-1", "101", "2.5", "", "abc"})
void invalidSizeIsRejectedBeforeCallingTheCatalog(
        String value) throws Exception {

    mvc.perform(get("/products")
                    .param("size", value))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_PAGING"))
            .andExpect(jsonPath("$.field").value("size"));

    verifyNoInteractions(catalog);
}
```

Cần có các test chấp nhận đúng giá trị lớn nhất và nhỏ nhất, không chỉ các test từ chối. Nếu implementation vô tình từ chối cả size bằng 100, nhóm test invalid vẫn có thể pass.

`verifyNoInteractions(catalog)` xác nhận đầu vào sai bị chặn trước tầng truy vấn. Chỉ kiểm tra HTTP 400 không phát hiện trường hợp ứng dụng đã query store rồi mới trả lỗi.

## 11. Kiểm thử tham số lặp và nhiều tiêu chí sort

Scalar và collection có quy tắc khác nhau:

```text
page=0&page=1
    -> lỗi theo hợp đồng minh họa

sort=price,desc&sort=id,asc
    -> hai tiêu chí sort hợp lệ
```

Ví dụ scalar bị lặp:

```java
@Test
void repeatedPageIsRejected()
        throws Exception {

    mvc.perform(get("/products")
                    .param("page", "0", "1"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.field").value("page"));

    verifyNoInteractions(catalog);
}
```

Các test sort cần bao gồm:

| Input | Kết quả mong đợi |
|---|---|
| `price,desc` | price DESC rồi id ASC |
| `name,asc` và `price,desc` | Giữ thứ tự hai tiêu chí rồi thêm id ASC |
| `id,desc` | Chỉ có id DESC |
| `price,asc` và `price,desc` | HTTP 400 vì lặp property |
| Bốn giá trị sort | HTTP 400 vì vượt số tiêu chí |
| `price` | HTTP 400 vì thiếu direction |
| `price,` | HTTP 400 vì direction rỗng |
| `price,asc,extra` | HTTP 400 vì sai cấu trúc |
| `price,sideways` | HTTP 400 |
| `customer.password,asc` | HTTP 400 vì property không được cho phép |

Với chính sách cú pháp chặt của ví dụ, `price, ASC` cũng không hợp lệ. Nếu ứng dụng muốn trim hoặc chấp nhận không phân biệt hoa thường, cần đổi hợp đồng và test tương ứng.

Trong các test dùng `.param(...)`, bạn đang đưa giá trị đã được biểu diễn như request parameter vào MockMvc. Cần có kiểm thử ở đường HTTP phù hợp nếu muốn xác nhận riêng URL encoding, ký tự đặc biệt hoặc proxy có làm thay đổi query hay không.

## 12. Giới hạn đầu vào không chỉ là page size

Một size nhỏ vẫn có thể tạo truy vấn đắt nếu page quá sâu hoặc sort yêu cầu thao tác phức tạp.

Các giới hạn cần xem xét theo endpoint:

- Size tối đa.
- Page hoặc offset tối đa.
- Số tiêu chí sort.
- Danh sách property và hướng sort được hỗ trợ.
- Độ dài chuỗi lọc.
- Số ID trong một bộ lọc tập hợp.
- Khoảng thời gian được phép truy vấn.
- Quyền sử dụng chức năng xuất toàn bộ dữ liệu.

Ví dụ không hỗ trợ `limit`, `unpaged` hoặc `all` như query parameter. Những tham số đó bị từ chối theo quy tắc tham số không được hỗ trợ; client không thể tự bật truy vấn không giới hạn.

Nếu sản phẩm có endpoint export, hãy định nghĩa và kiểm thử hợp đồng tài nguyên riêng của export. Không mặc định dùng `size` cực lớn là cách thay thế an toàn.

Giới hạn size cũng không thay thế authorization hoặc giới hạn tần suất request. Đây là những trách nhiệm khác nhau và cần kiểm tra ở vị trí thực thi thật.

## 13. Kiểm thử hợp đồng JSON thay vì chụp lại mọi chi tiết

Một test JSON nên ưu tiên:

- Tên và kiểu các trường đã công bố.
- Array content và thứ tự phần tử.
- Metadata cần thiết cho điều hướng.
- Cách biểu diễn trường optional hoặc null nếu hợp đồng có.
- Không xuất hiện các trường nội bộ hoặc dữ liệu không được phép.
- Content type và HTTP status phù hợp.

Không cần assertion về thứ tự các key trong một JSON object nếu API không cam kết điều đó. Ngược lại, thứ tự phần tử trong content và thứ tự các tiêu chí sort có ý nghĩa nên phải kiểm tra.

Nếu dùng snapshot test, cần chọn phạm vi snapshot theo hợp đồng công khai. Một snapshot toàn bộ entity có thể vô tình biến trường persistence hoặc quan hệ lazy thành một phần của API.

Với dữ liệu số, cần kiểm tra theo ý nghĩa của trường. Ví dụ một ID được định nghĩa là chuỗi nên giữ kiểu chuỗi; totalElements không nên bị chuyển thành một chuỗi chỉ vì dễ format.

Có thể thêm dữ liệu sentinel để phát hiện rò rỉ trường nội bộ. Chỉ tạo và trả `ProductRow` giúp giới hạn đầu ra, nhưng kiểm thử vẫn cần xác nhận đường mapping thực tế của ứng dụng.

## 14. JSON lỗi cũng là một hợp đồng

Ví dụ lỗi đầu vào:

```json
{
  "code": "INVALID_PAGING",
  "field": "size",
  "message": "Value is outside the allowed range"
}
```

Trong test, thường ưu tiên code, field và status. Nếu message được dịch hoặc điều chỉnh câu chữ, chỉ cố định nguyên văn khi sản phẩm xem nó là một phần hợp đồng bắt buộc.

Cần kiểm tra rằng response lỗi không chứa:

- Stack trace.
- Câu query.
- Tên bảng hoặc thông tin kết nối.
- Giá trị bí mật từ request.
- Toàn bộ object exception.

Không chuyển lỗi database thành lỗi đầu vào chỉ để giữ mọi response ở HTTP 400. Điều đó làm client hiểu sai khả năng retry và che mất lỗi hệ thống.

Nếu API dùng một chuẩn error body khác, hãy thống nhất handler và test theo chuẩn đó thay vì duy trì nhiều kiểu lỗi ngẫu nhiên cho cùng nhóm endpoint.

## 15. Standalone test chưa xác minh cấu hình web của ứng dụng

Các ví dụ MockMvc standalone trong bài kiểm tra controller cùng những thành phần được đăng ký trực tiếp.

Một nhóm kiểm thử với context thực tế cần xác nhận thêm:

- Parser hoặc argument resolver đúng đã được đăng ký.
- Cấu hình mặc định và maximum size đúng được tải từ profile.
- ObjectMapper và naming strategy đúng được sử dụng.
- Global exception handler thực sự có hiệu lực.
- Security filter, tenant context và các interceptor được áp dụng.
- Cấu hình page bắt đầu từ 0 hay 1 đúng với hợp đồng.
- Nếu có nhiều tham số Pageable, qualifier và tên tham số không bị nhầm.

Nếu dùng trực tiếp `Pageable` trong controller, test context phải đi qua resolver đang phục vụ endpoint. Tự tạo PageRequest rồi gọi method Java không kiểm tra được bước phân giải tham số HTTP.

Cũng không tự đăng ký một resolver khác trong test chỉ để làm test pass, trong khi cấu hình production chưa có thay đổi tương ứng.

Với endpoint yêu cầu đăng nhập, cần thiết lập danh tính kiểm thử phù hợp. HTTP 401 hoặc 403 do security chặn trước controller không chứng minh parser xử lý page hoặc size đúng.

## 16. Kết nối kiểm thử web với kiểm thử repository

Bộ kiểm thử có thể chia thành các nhóm bổ sung cho nhau:

| Nhóm | Xác minh |
|---|---|
| Parser unit test | Chuyển đổi, biên số, tham số lặp, danh sách sort cho phép |
| Controller test | HTTP status, gọi service đúng và JSON |
| Test context web | Cấu hình resolver, mapper, handler và filter thực |
| Repository integration test | Store thực thi điều kiện lọc, sort, offset và limit |
| Luồng tích hợp chọn lọc | Một request thật đi qua các lớp quan trọng tới backend kiểm thử |

Một controller test có mock không nên được mô tả là đã kiểm tra query của store.

Ví dụ test HTTP xác nhận Sort là `price DESC, id ASC`. Repository integration test cần fixture có hai sản phẩm trùng giá để xác nhận store áp dụng khóa phụ đúng.

Tương tự, controller test giữ totalElements bằng 5 từ Page mock. Repository test xác nhận total đó được tính đúng trên dữ liệu thật, đặc biệt khi query có join hoặc count query tùy biến.

Không cần lặp mọi tổ hợp đầu vào trên mọi tầng. Đặt từng assertion ở tầng có thể phát hiện đúng loại lỗi, rồi có một số luồng tích hợp để kiểm tra các lớp nối với nhau.

## 17. Các lỗi dễ làm test pass nhưng endpoint vẫn sai

| Cách kiểm tra | Khoảng trống còn lại |
|---|---|
| Gọi trực tiếp controller bằng Java | Không kiểm tra binding HTTP |
| Chỉ kiểm tra HTTP 200 | JSON hoặc Pageable có thể sai |
| Chỉ kiểm tra content length | Có thể sai thứ tự, sai page hoặc sai total |
| Chỉ có test từ chối giá trị lớn | Có thể đang từ chối cả giá trị hợp lệ ở biên |
| Dùng mock trả đúng list đã sort | Chưa xác minh backend thực thi sort |
| Tạo JSON expected từ chính object response | Có thể lặp lại cùng một lỗi mapping |
| Luôn đặt default Pageable thủ công trong test | Bỏ qua cấu hình resolver |
| Chỉ kiểm tra 400, không kiểm tra service | Truy vấn có thể đã chạy với đầu vào nguy hiểm |
| Dùng cùng expected total cho mọi trang rỗng | Không phân biệt không có dữ liệu và vượt phạm vi |
| Chấp nhận mọi tên property từ client | Có thể lộ cấu trúc nội bộ hoặc tạo truy vấn không được hỗ trợ |

Expected value nên đến từ hợp đồng đã xác định, không được tự suy ra bằng đúng đoạn logic mà test đang muốn kiểm tra.

## 18. Bài thực hành

Với một endpoint phân trang của ứng dụng:

1. Viết bảng hợp đồng cho page, size, sort và giá trị mặc định.
2. Chọn rõ từ chối hay chuẩn hóa khi size vượt giới hạn.
3. Kiểm tra page đầu, page giữa và page cuối ở tầng HTTP.
4. Kiểm tra JSON array rỗng khi không có kết quả.
5. Kiểm tra trang vượt phạm vi vẫn giữ total lớn hơn 0 nếu đó là hợp đồng đã chọn.
6. Kiểm tra số âm, số thập phân, giá trị rỗng và tràn số.
7. Kiểm tra scalar parameter lặp và sort nhiều tiêu chí.
8. Kiểm tra property không được cho phép.
9. Xác nhận đầu vào sai không gọi tầng dữ liệu.
10. Chạy một nhóm kiểm thử với cấu hình web thật của dự án.
11. Ghép với repository integration test trên store tương ứng để xác nhận sort và phân trang được thực thi đúng.

Sau mỗi test, hãy chỉ ra nó bảo vệ phần nào của hợp đồng và phần nào vẫn cần một tầng kiểm thử khác.

## 19. Những điều cần nắm vững

Một endpoint phân trang cần kiểm thử từ query parameter tới JSON công khai. Commons cung cấp abstraction dữ liệu, còn ứng dụng chịu trách nhiệm định nghĩa giới hạn đầu vào và cách biểu diễn kết quả.

Kiểm thử đáng tin cậy cần phân biệt default, normalization và rejection; giữ đúng metadata của Page; từ chối sort ngoài hợp đồng; đồng thời xác minh cấu hình web thực sự được sử dụng.

Kết quả rỗng, trang cuối thiếu phần tử và request sai là các tình huống bình thường cần được thiết kế rõ ràng, không phải các ngoại lệ được xử lý tùy hứng.
