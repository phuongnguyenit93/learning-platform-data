# Tham số phân trang, sắp xếp và lọc trong Spring REST Docs

## 1. Bài toán thực tế và mục tiêu

Một endpoint liệt kê sản phẩm thường nhận các query parameters để giới hạn số kết quả, xác định thứ tự và lọc dữ liệu:

```http
GET /api/products?page=1&size=10&sort=price,asc&sort=id,asc&status=ACTIVE&status=PREORDER&q=gaming%20phone&minPrice=100&maxPrice=500 HTTP/1.1
Host: api.example.test
Accept: application/json
```

Trong request này:

- `page=1` chọn trang thứ hai nếu hệ thống dùng chỉ số trang **bắt đầu từ 0**.
- `size=10` yêu cầu tối đa 10 kết quả mỗi trang.
- Hai lần xuất hiện của `sort` mô tả hai tiêu chí sắp xếp, theo thứ tự ưu tiên.
- Hai lần xuất hiện của `status` chọn hai trạng thái; cần xác định cách kết hợp chúng.
- `q` là từ khóa; `minPrice` và `maxPrice` giới hạn khoảng giá.

Module **SPRING_REST_DOCS** dùng **Spring REST Docs** để sinh tài liệu API có thể kiểm chứng ngay từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Trong chương **Query parameters**, chúng ta dùng `queryParameters(...)` và `parameterWithName(...)` để mô tả hợp đồng phân trang, sắp xếp, lọc; sinh snippet vào Asciidoctor/Markdown; sau đó đưa bước kiểm thử và xuất tài liệu vào build/CI.

Mục tiêu sau khi học:

1. Thiết kế và mô tả rõ `page`, `size`, `sort` cùng các bộ lọc.
2. Phân biệt tham số bắt buộc, tùy chọn, giá trị mặc định và quy tắc nghiệp vụ.
3. Kiểm thử cả việc **document đúng tên** lẫn **xử lý đúng giá trị**.
4. Tạo `query-parameters.adoc` và tích hợp snippet vào trang tài liệu endpoint.

## 2. Thiết kế hợp đồng query cho một endpoint danh sách

Trước khi viết kiểm thử tài liệu, nhóm cần thống nhất quy ước trên HTTP. Bảng sau là **hợp đồng minh họa** cho `GET /api/products`; không phải hành vi tự động của mọi Spring MVC controller:

| Tham số | Cú pháp | Mặc định | Điều kiện và ý nghĩa |
| --- | --- | --- | --- |
| `page` | Số nguyên từ 0 | `0` | Trang bắt đầu từ 0; chỉ một giá trị |
| `size` | Số nguyên từ 1 đến 100 | `20` | Số phần tử tối đa trên trang |
| `sort` | `field,direction`; có thể lặp | `createdAt,desc` và thêm `id,asc` để ổn định thứ tự | `field` chỉ thuộc `price`, `createdAt`, `id`; `direction` là `asc` hoặc `desc` |
| `status` | Có thể lặp: `status=ACTIVE&status=PREORDER` | Không lọc trạng thái | Mỗi trạng thái thuộc `ACTIVE`, `PREORDER`, `ARCHIVED` |
| `q` | Chuỗi văn bản đã URL-encode | Không lọc theo từ khóa | Tìm kiếm theo quy tắc do ứng dụng quy định |
| `minPrice` | Số thập phân không âm | Không có giới hạn dưới | Có thể gửi riêng |
| `maxPrice` | Số thập phân không âm | Không có giới hạn trên | Nếu gửi cùng `minPrice` thì `maxPrice >= minPrice` |

Giả sử endpoint lọc kết quả bằng phép **AND giữa các nhóm điều kiện** (`status`, `q` và khoảng giá), đồng thời dùng **OR giữa nhiều giá trị `status`**. Khi lấy dữ liệu thực tế, tầng service/repository phải hiện thực đúng quy tắc này và có test kiểm chứng.

Những thông tin cần công bố gồm: trang có bắt đầu từ 0 hay 1, giới hạn `size`, tên trường cho phép sắp xếp, thứ tự ưu tiên của nhiều `sort`, cách kết hợp bộ lọc, định dạng số/ngày, hành vi khi tham số vắng hoặc sai, và quy tắc xác định thứ tự ổn định khi dữ liệu có giá trị trùng.

## 3. Phân trang: `page`, `size` và giới hạn

### 3.1. Phân trang theo số trang và độ lệch

Nếu trang bắt đầu từ 0, số phần tử cần bỏ qua thường là:

```text
offset = page * size
```

Ví dụ, với `page=2&size=10`, bộ dữ liệu đã sắp xếp ổn định sẽ bỏ qua 20 kết quả đầu rồi lấy tối đa 10 kết quả tiếp theo. Trong API công khai cần nói rõ **`page=0` là trang đầu tiên**. Đừng mặc định người dùng hiểu `page=1` là trang đầu.

| Query | Kết quả theo hợp đồng minh họa |
| --- | --- |
| Không có `page` và `size` | Trang 0, tối đa 20 kết quả |
| `?page=0&size=10` | Tối đa 10 kết quả đầu tiên |
| `?page=2&size=10` | Tối đa 10 kết quả sau 20 kết quả đầu |
| `?page=-1` | HTTP 400 vì trang âm |
| `?size=0` hoặc `?size=101` | HTTP 400 vì nằm ngoài khoảng 1–100 |
| `?page=abc` | Thông thường HTTP 400 do lỗi chuyển kiểu sang `int` |

Giới hạn kích thước trang bảo vệ bộ nhớ, thời gian truy vấn và băng thông. API còn cần xem xét tình huống `page * size` vượt giới hạn số nguyên/giới hạn truy vấn của cơ sở dữ liệu khi chuyển thành offset. Những quy tắc này nằm ở ứng dụng và database, **không được Spring REST Docs tự kiểm tra**.

### 3.2. Phân trang ổn định khi dữ liệu thay đổi

Nếu `sort=price,asc` và nhiều sản phẩm có cùng giá, thứ tự của chúng có thể không xác định. Trong hợp đồng minh họa, API tự thêm `id,asc` làm tiêu chí cuối cùng nếu client chưa cung cấp `id`. Nhờ đó, trong một snapshot dữ liệu, các dòng cùng `price` vẫn có thứ tự xác định.

Ngay cả với thứ tự ổn định, khi dữ liệu được thêm hoặc xóa giữa các request, offset pagination vẫn có thể khiến client thấy bản ghi bị lặp hoặc bỏ sót. Nếu yêu cầu duyệt bộ dữ liệu biến động liên tục, có thể thiết kế **cursor pagination** với `cursor` và `limit`; đây là một hợp đồng khác, cần tài liệu riêng về token, thời hạn, thứ tự và tính nhất quán.

### 3.3. Metadata của response

Tài liệu request `page`/`size` chưa đủ cho API danh sách: client cũng cần biết response biểu diễn trang hiện tại và cách chuyển trang. Một body minh họa:

```json
{
  "content": [
    {"id": 24, "name": "Gaming phone", "price": 250}
  ],
  "page": 1,
  "size": 10,
  "totalElements": 57,
  "totalPages": 6,
  "hasNext": true
}
```

Đây là cấu trúc ví dụ do ứng dụng định nghĩa; Spring REST Docs không bắt buộc response phải có các trường trên. Trong dự án thực, dùng `responseFields(...)`/`responseBody(...)` để document payload và viết assertion cho metadata nếu API công bố chúng.

## 4. Sắp xếp: `sort` lặp, thứ tự ưu tiên và danh sách cho phép

Query thường gặp:

```http
GET /api/products?sort=price,asc&sort=id,asc HTTP/1.1
```

Hợp đồng minh họa định nghĩa mỗi giá trị có dạng `field,direction`. Vì `sort` xuất hiện hai lần nên client yêu cầu sắp xếp theo `price` tăng dần trước, sau đó theo `id` tăng dần nếu giá trùng.

| Trường hợp | Ý nghĩa hoặc cách xử lý được đề xuất |
| --- | --- |
| Không gửi `sort` | Mặc định `createdAt,desc`; thêm `id,asc` làm khóa cuối |
| `sort=price,asc` | Sắp xếp theo giá tăng dần, rồi `id` tăng dần |
| `sort=price,desc&sort=id,asc` | Giá giảm dần, sau đó ID tăng dần |
| `sort=unknown,asc` | HTTP 400 vì trường không nằm trong danh sách cho phép |
| `sort=price,up` | HTTP 400 vì hướng sắp xếp không hợp lệ |
| `sort=price` | HTTP 400 theo hợp đồng bắt buộc đủ `field,direction` |

**Lưu ý bảo mật và hiệu năng:** Đừng ghép trực tiếp tên cột do client gửi vào câu SQL. Kiểm tra danh sách trường cho phép và dùng API truy vấn có parameter binding/cơ chế tạo câu lệnh phù hợp. Trường sort public không nhất thiết trùng tên cột vật lý trong database.

Trong Spring Data, `Pageable` và `Sort` có thể giúp binding phân trang/sắp xếp, nhưng mặc định và cú pháp chính xác phụ thuộc cấu hình resolver của ứng dụng. Việc `@RequestParam` tự parse nhiều giá trị hoặc một chuỗi chứa dấu phẩy cũng cần kiểm chứng theo kiểu tham số và converter thực tế; test HTTP là bằng chứng của hợp đồng.

## 5. Lọc dữ liệu: tên bộ lọc, giá trị lặp và khoảng giá

### 5.1. Nhiều giá trị cho một bộ lọc

```http
GET /api/products?status=ACTIVE&status=PREORDER HTTP/1.1
```

Ở mức query string, `status` xuất hiện hai lần. Với hợp đồng đang thiết kế, danh sách có ý nghĩa **ACTIVE hoặc PREORDER**. Trong tài liệu, chỉ cần **một** descriptor `parameterWithName("status")` và ghi rõ việc được lặp, tên enum hợp lệ, cùng quy tắc OR.

Nếu kết hợp thêm `q=phone` thì kết quả phải thỏa điều kiện trạng thái **và** từ khóa. Không được suy ra việc kết hợp AND/OR chỉ từ `@RequestParam List<String>`.

### 5.2. Bộ lọc phạm vi

```http
GET /api/products?minPrice=100&maxPrice=500 HTTP/1.1
```

Theo hợp đồng ví dụ, `minPrice` và `maxPrice` có thể được gửi riêng lẻ để giới hạn một phía. Nếu gửi cả hai, giá trị trên phải lớn hơn hoặc bằng giá trị dưới. Khi dùng số tiền, nên quy định rõ đơn vị tiền tệ, quy tắc làm tròn và precision; `BigDecimal` giúp tránh sai số nhị phân của `double` khi so sánh số thập phân.

### 5.3. Từ khóa và URL encoding

```http
GET /api/products?q=gaming%20phone HTTP/1.1
```

Sau URL decoding, `q` có giá trị `gaming phone`. Nếu chứa `+` hoặc `&`, client cần encode phù hợp thay vì nối chuỗi query thủ công. Hợp đồng cũng nên nói rõ việc trim whitespace, phân biệt hoa thường, hỗ trợ tìm theo trường nào và cách thoát ký tự đặc biệt; các quy tắc này phải do tầng search thực hiện.

## 6. Mô tả các tham số bằng Spring REST Docs

Đặt các descriptor vào `queryParameters(...)`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("page")
        .description("Chỉ số trang từ 0; mặc định 0")
        .optional(),
    parameterWithName("size")
        .description("Số phần tử/trang, 1-100; mặc định 20")
        .optional(),
    parameterWithName("sort")
        .description("Có thể lặp: sort=field,direction; field là price, createdAt, id; "
            + "direction là asc hoặc desc; mặc định createdAt,desc rồi id,asc")
        .optional(),
    parameterWithName("status")
        .description("Có thể lặp: ACTIVE, PREORDER hoặc ARCHIVED; "
            + "các giá trị kết hợp OR; vắng mặt nghĩa là không lọc")
        .optional(),
    parameterWithName("q")
        .description("Từ khóa tìm kiếm, đã URL-encode; vắng mặt nghĩa là không lọc")
        .optional(),
    parameterWithName("minPrice")
        .description("Giá tối thiểu không âm; có thể bỏ qua")
        .optional(),
    parameterWithName("maxPrice")
        .description("Giá tối đa không âm, không nhỏ hơn minPrice khi có cả hai")
        .optional()
)
```

**`parameterWithName(...)` mô tả tên chứ không mô tả từng giá trị.** Vì thế, `status=ACTIVE&status=PREORDER` có một descriptor cho `status`, và `sort=price,asc&sort=id,asc` có một descriptor cho `sort`. Nội dung `description(...)` sẽ xuất hiện trong bảng snippet.

Mọi descriptor trong ví dụ đều dùng `.optional()` vì endpoint cho phép request không có query string. Điều đó chỉ nói rằng tên tham số có thể **không xuất hiện** trong request test; nó không có nghĩa giá trị nào cũng hợp lệ. `.optional()` cũng không tự thiết lập mặc định trong controller.

### 6.1. Strict, relaxed và ignored

| Cách khai báo | Ý nghĩa khi sinh tài liệu |
| --- | --- |
| `queryParameters(...)` | Chế độ mặc định: báo lỗi khi request chứa tên query parameter chưa được mô tả, hoặc thiếu descriptor bắt buộc |
| `parameterWithName("page").optional()` | `page` được mô tả nhưng có thể vắng mặt trong request |
| `parameterWithName("trace").ignored()` | Biết tên `trace` nhưng không đưa nó vào bảng snippet |
| `relaxedQueryParameters(...)` | Cho phép request chứa tên query parameter chưa được mô tả; vẫn kiểm tra descriptor bắt buộc |

Khi tài liệu hóa API chính thức, nên dùng `queryParameters(...)` nghiêm ngặt để phát hiện tên tham số mới bị thêm vào request mà chưa được mô tả. Dùng `ignored()` cho tham số kỹ thuật có chủ đích và `relaxedQueryParameters(...)` khi thật sự chỉ muốn document một phần request.

### 6.2. Kiểm tra tên khác kiểm tra nội dung

REST Docs có thể xác nhận query string chứa tham số `size` được mô tả, nhưng không tự suy ra từ `description("1-100")` rằng `size=500` cần trả lỗi. Tương tự, `sort=unknown,asc` vẫn có tên `sort` hợp lệ đối với descriptor. Validation giá trị, thứ tự và quan hệ giữa tham số phải nằm trong code ứng dụng và được kiểm thử riêng.

## 7. Ví dụ hoàn chỉnh với MockMvc + JUnit 5

Để thấy rõ các quy tắc truyền query, controller sau chỉ **chuẩn hóa và phản hồi lại tham số**. Nó không truy vấn database; trong API thật, service/repository cần dùng các giá trị đã kiểm tra để thực hiện phân trang, sắp xếp và lọc dữ liệu.

### 7.1. Controller minh họa

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class ProductSearchController {

    private static final Set<String> SORT_FIELDS =
            Set.of("price", "createdAt", "id");
    private static final Set<String> STATUSES =
            Set.of("ACTIVE", "PREORDER", "ARCHIVED");

    @GetMapping("/api/products")
    public String search(
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "20") int size,
            @RequestParam(name = "sort", required = false) List<String> requestedSort,
            @RequestParam(name = "status", required = false) List<String> statuses,
            @RequestParam(name = "q", required = false) String q,
            @RequestParam(name = "minPrice", required = false) BigDecimal minPrice,
            @RequestParam(name = "maxPrice", required = false) BigDecimal maxPrice) {

        if (page < 0 || size < 1 || size > 100) {
            throw badRequest("page/size is out of range");
        }

        if ((minPrice != null && minPrice.signum() < 0)
                || (maxPrice != null && maxPrice.signum() < 0)
                || (minPrice != null && maxPrice != null
                    && minPrice.compareTo(maxPrice) > 0)) {
            throw badRequest("invalid price range");
        }

        List<String> selectedStatuses =
                statuses == null ? List.of() : statuses;
        for (String status : selectedStatuses) {
            if (!STATUSES.contains(status)) {
                throw badRequest("unsupported status");
            }
        }

        List<String> sortInput =
                requestedSort == null || requestedSort.isEmpty()
                    ? List.of("createdAt,desc")
                    : requestedSort;
        List<String> normalizedSort = new ArrayList<>();

        for (String spec : sortInput) {
            String[] parts = spec.split(",", -1);
            if (parts.length != 2
                    || !SORT_FIELDS.contains(parts[0])
                    || (!parts[1].equals("asc") && !parts[1].equals("desc"))) {
                throw badRequest("invalid sort: " + spec);
            }
            normalizedSort.add(parts[0] + ":" + parts[1]);
        }

        // Thêm khóa duy nhất làm tiêu chí cuối nếu client chưa gửi.
        if (normalizedSort.stream().noneMatch(s -> s.startsWith("id:"))) {
            normalizedSort.add("id:asc");
        }

        String keyword = q == null ? "" : q.trim();
        String statusesText = selectedStatuses.isEmpty()
                ? "ALL"
                : String.join("|", selectedStatuses);
        String priceRange = (minPrice == null ? "*" : minPrice.toPlainString())
                + ".."
                + (maxPrice == null ? "*" : maxPrice.toPlainString());

        return "page=" + page
                + ";size=" + size
                + ";sort=" + String.join("|", normalizedSort)
                + ";status=" + statusesText
                + ";q=" + keyword
                + ";price=" + priceRange;
    }

    private static ResponseStatusException badRequest(String reason) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);
    }
}
```

Các điểm cần chú ý:

- `defaultValue` của `page`/`size` là cấu hình **Spring MVC**, không phải cấu hình Spring REST Docs.
- `List<String> requestedSort` và `List<String> statuses` nhận danh sách giá trị của cùng một tên trong query. Hãy kiểm thử đúng cách client thực sự gửi các giá trị lặp.
- Phần chuẩn hóa sort kiểm tra cả tên trường lẫn hướng để tránh chấp nhận đầu vào tùy ý. `id:asc` được thêm vào cuối nếu chưa có `id`.
- Giá trị giá không âm và quan hệ `minPrice <= maxPrice` được kiểm tra độc lập với `queryParameters(...)`.
- Chuỗi trả về phục vụ bài học về HTTP binding và tài liệu hóa. Nó **chưa phải** kết quả tìm kiếm/phân trang từ repository.

### 7.2. Test tạo tài liệu cho query có đủ nhóm tham số

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ProductQueryDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ProductSearchController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsPaginationSortingAndFiltering() throws Exception {
        mockMvc.perform(get("/api/products")
                        .queryParam("page", "1")
                        .queryParam("size", "10")
                        .queryParam("sort", "price,asc", "id,asc")
                        .queryParam("status", "ACTIVE", "PREORDER")
                        .queryParam("q", "gaming phone")
                        .queryParam("minPrice", "100")
                        .queryParam("maxPrice", "500"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "page=1;size=10;sort=price:asc|id:asc;"
                        + "status=ACTIVE|PREORDER;q=gaming phone;price=100..500"))
                .andDo(document("products-search",
                        queryParameters(
                                parameterWithName("page")
                                        .description("Trang bắt đầu từ 0; mặc định 0")
                                        .optional(),
                                parameterWithName("size")
                                        .description("Kích thước trang, 1-100; mặc định 20")
                                        .optional(),
                                parameterWithName("sort")
                                        .description("Có thể lặp: field,direction; "
                                                + "field=price|createdAt|id, direction=asc|desc; "
                                                + "mặc định createdAt,desc rồi id,asc")
                                        .optional(),
                                parameterWithName("status")
                                        .description("Có thể lặp: ACTIVE, PREORDER, ARCHIVED; "
                                                + "lọc theo OR; bỏ qua để không lọc")
                                        .optional(),
                                parameterWithName("q")
                                        .description("Từ khóa tìm kiếm; bỏ qua để không lọc")
                                        .optional(),
                                parameterWithName("minPrice")
                                        .description("Giá tối thiểu, không âm")
                                        .optional(),
                                parameterWithName("maxPrice")
                                        .description("Giá tối đa, không âm; không nhỏ hơn minPrice")
                                        .optional()
                        )));
    }
}
```

Test gồm hai loại kiểm chứng:

1. `status().isOk()` và `content().string(...)` kiểm chứng cách server nhận, xác thực và chuẩn hóa giá trị.
2. `document("products-search", queryParameters(...))` kiểm tra tên query parameters, sinh snippet và ghi mô tả đúng hợp đồng dự kiến.

**Lưu ý quan trọng với MockMvc:** Dùng `.queryParam(...)` hoặc đưa tham số trực tiếp vào URI khi document bằng `queryParameters(...)`. `.param(...)` chỉ bổ sung Servlet request parameters tổng quát nên có thể khiến controller nhận được dữ liệu nhưng REST Docs không nhận diện đó là query string.

### 7.3. Test cho mặc định và dữ liệu sai

Khi toàn bộ tham số được khai báo `.optional()`, một request không có query string vẫn có thể hợp lệ. Test sau xác minh **default thực tế** của controller:

```java
@Test
void usesDefaultsWhenQueryIsAbsent() throws Exception {
    mockMvc.perform(get("/api/products"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                    "page=0;size=20;sort=createdAt:desc|id:asc;"
                    + "status=ALL;q=;price=*..*"));
}

@Test
void rejectsInvalidPageSizeSortAndFilters() throws Exception {
    mockMvc.perform(get("/api/products").queryParam("page", "-1"))
            .andExpect(status().isBadRequest());

    mockMvc.perform(get("/api/products").queryParam("size", "101"))
            .andExpect(status().isBadRequest());

    mockMvc.perform(get("/api/products").queryParam("sort", "password,asc"))
            .andExpect(status().isBadRequest());

    mockMvc.perform(get("/api/products").queryParam("status", "UNKNOWN"))
            .andExpect(status().isBadRequest());

    mockMvc.perform(get("/api/products")
            .queryParam("minPrice", "500")
            .queryParam("maxPrice", "100"))
            .andExpect(status().isBadRequest());
}
```

Hai phương thức trên được thêm vào **cùng lớp kiểm thử** ở mục 7.2. Chúng giúp phát hiện việc ai đó đổi `defaultValue`, bỏ kiểm tra miền giá trị hoặc cho phép sắp xếp theo trường ngoài danh sách. Muốn bảo đảm việc lọc dữ liệu và chia trang thực tế, cần bổ sung integration test có tập dữ liệu mẫu, kiểm tra danh sách item, `totalElements` và thứ tự.

## 8. Snippet và Asciidoctor/Markdown

Với cấu hình Gradle ghi snippet tại `build/generated-snippets`, bài test ở mục 7.2 tạo thư mục minh họa:

```text
build/
  generated-snippets/
    products-search/
      query-parameters.adoc
      http-request.adoc
      http-response.adoc
      curl-request.adoc
      ...
```

Đường dẫn thực tế phụ thuộc cấu hình build; Maven thường dùng `target/generated-snippets`. Với template Asciidoctor, `query-parameters.adoc` chứa bảng tên tham số và phần `description` tương ứng.

Trong `src/docs/asciidoc/products.adoc`:

```asciidoc
= Products API

== Tìm kiếm sản phẩm

GET /api/products

=== Query parameters

include::{snippets}/products-search/query-parameters.adoc[]

=== Ví dụ truy vấn

include::{snippets}/products-search/http-request.adoc[]

=== Response

include::{snippets}/products-search/http-response.adoc[]
```

Biến `{snippets}` cần được cấu hình trỏ đến output của Spring REST Docs. Nếu cần mô tả response dạng JSON và metadata phân trang, bổ sung `responseFields(...)` vào bài test của endpoint thật để sinh bảng trường response tương ứng.

Spring REST Docs cũng hỗ trợ chọn `TemplateFormats.markdown()` để sinh snippet định dạng Markdown. Markdown không có cú pháp `include` tiêu chuẩn tương tự Asciidoctor; dùng quy trình ghép snippet thích hợp với công cụ xuất bản của dự án.

### 8.1. Đưa tài liệu vào build và CI

Luồng tổng quát:

1. Khai báo dependency kiểm thử của Spring REST Docs phù hợp môi trường: `spring-restdocs-mockmvc`, `spring-restdocs-webtestclient` hoặc `spring-restdocs-restassured`, kèm JUnit/Spring Test.
2. Khai báo thư mục `generated-snippets` là output của task `test`.
3. Cấu hình task Asciidoctor/đóng gói tài liệu đọc snippets và **phụ thuộc task `test`**.
4. Chạy kiểm thử, render HTML và kiểm tra artifact trong CI; pipeline phải thất bại khi test hoặc bước biên soạn tài liệu thất bại.

Ví dụ minh họa lệnh Gradle sau khi dự án đã khai báo plugin và task tương ứng:

```bash
./gradlew test asciidoctor
```

Thay đổi hợp đồng như `size` tối đa từ 100 xuống 50, đổi tên `status` hoặc thêm `sort` mới cần cập nhật **cả** validation và `description(...)`/test tài liệu. REST Docs không tự suy ra điều kiện nghiệp vụ chỉ từ các dòng mô tả.

## 9. Áp dụng với WebTestClient và REST Assured

Các descriptor `parameterWithName(...)` và `queryParameters(...)` dùng chung giữa các tích hợp. Vị trí gửi query string và gắn `document(...)` thay đổi theo công cụ.

### WebTestClient

Ví dụ với `webTestClient` đã được cấu hình REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri(builder -> builder.path("/api/products")
                .queryParam("page", 1)
                .queryParam("sort", "price,asc", "id,asc")
                .queryParam("status", "ACTIVE", "PREORDER")
                .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("products-search-webclient",
                queryParameters(
                        parameterWithName("page")
                                .description("Trang bắt đầu từ 0").optional(),
                        parameterWithName("sort")
                                .description("Có thể lặp field,direction").optional(),
                        parameterWithName("status")
                                .description("Có thể lặp; chọn nhiều trạng thái").optional()
                )));
```

Ví dụ chỉ document những tên thực sự có trong request này. Với endpoint có nhiều tham số hơn, tài liệu chính thức nên mô tả đủ hợp đồng bằng các descriptor phù hợp; Spring REST Docs không tự lấy mô tả từ annotation controller.

### REST Assured

REST Assured cho phép gửi các giá trị query bằng `queryParam(...)`:

```java
given()
    .filter(documentationFilter)
    .queryParam("page", 1)
    .queryParam("sort", "price,asc", "id,asc")
    .queryParam("status", "ACTIVE", "PREORDER")
    .when()
    .get("/api/products")
    .then()
    .statusCode(200);
```

`documentationFilter` đại diện cho filter đã cấu hình qua module `spring-restdocs-restassured`, chứa `document(..., queryParameters(...))`. Đoạn HTTP call riêng lẻ chưa tự sinh snippet nếu filter không được cấu hình.

## 10. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Test REST Docs báo thiếu `sort` dù controller đã nhận `sort` | Dùng `.param(...)` thay cho query string thực | Gửi bằng `.queryParam(...)` hoặc URL có `?sort=...` |
| `page=1` được hiểu thành trang đầu | Client và server khác quy ước 0-based/1-based | Chốt quy ước và ghi rõ trong `description(...)` |
| `size=500` vẫn tạo snippet | REST Docs kiểm tra tên, không kiểm tra giới hạn giá trị | Validation và test HTTP 400 cho `size` |
| Gửi hai `sort` nhưng tài liệu có hai descriptor cùng tên | Nhầm nhiều giá trị với nhiều tên tham số | Chỉ dùng một `parameterWithName("sort")` và mô tả lặp |
| Trật tự trang thay đổi giữa hai lần gọi cùng dữ liệu | Sort không có khóa phân biệt khi giá trị trùng | Áp dụng tiêu chí ổn định như `id` và kiểm thử |
| Bộ lọc `status` nhận giá trị không công bố | Chưa kiểm tra enum/danh mục được phép | Validate allowlist và viết test lỗi |
| `minPrice > maxPrice` vẫn qua bước document | Điều kiện giá không thuộc kiểm tra của descriptor | Validate khoảng và kiểm tra response 400 |
| Response có tổng số phần tử sai sau khi lọc | Metadata đếm trên tập dữ liệu khác với tập trả về | Test integration với dữ liệu mẫu và total sau filter |
| HTML thiếu bảng query parameters | Sai identifier, thiếu snippet hoặc task docs chạy trước test | Kiểm tra `document(...)`, thư mục snippets và thứ tự task |

## 11. Bài tập thực hành

Hãy xây dựng tài liệu cho endpoint:

```http
GET /api/orders?page=0&size=25&sort=createdAt,desc&sort=id,asc&status=PAID&status=SHIPPED&fromDate=2026-11-01&toDate=2026-11-30 HTTP/1.1
```

Hợp đồng dự kiến:

- `page` mặc định 0, không âm; `size` mặc định 25, từ 1 đến 200.
- `sort` có thể lặp, chỉ cho phép `createdAt`, `totalAmount`, `id` với hướng `asc`/`desc`; bổ sung `id` để ổn định.
- `status` có thể lặp; nhiều giá trị kết hợp OR, chỉ nhận `PENDING`, `PAID`, `SHIPPED`, `CANCELLED`.
- `fromDate` và `toDate` cùng vắng mặt hoặc cùng xuất hiện, dùng định dạng `yyyy-MM-dd`; khoảng ngày phải hợp lệ.
- Các nhóm điều kiện trạng thái và khoảng ngày kết hợp AND.

Thực hiện:

1. Viết controller/service nhận và kiểm tra các tham số; xác định phản hồi khi giá trị sai hoặc mâu thuẫn.
2. Viết test MockMvc gửi nhiều giá trị `sort`/`status` qua `queryParam(...)` và sinh `query-parameters.adoc`; mỗi tên chỉ có một descriptor.
3. Viết test xác minh mặc định khi request không có query string và lỗi khi `size=201`, `sort=secret,asc` hoặc thiếu `toDate`.
4. Dùng tập dữ liệu giả lập để kiểm tra thứ tự item, phân trang và tổng số bản ghi **sau lọc**, thay vì chỉ kiểm tra mô tả trong snippet.
5. Nhúng snippet vào Asciidoctor hoặc quy trình Markdown và đưa cả test lẫn render tài liệu vào CI.

**Tiêu chí hoàn thành:** Tài liệu nêu rõ mặc định, miền giá trị, thứ tự và quy tắc lọc; test HTTP xác nhận dữ liệu đầu vào và kết quả; snippet được sinh từ bài test; build/CI phát hiện khi hợp đồng không còn khớp.

## 12. Tổng kết kiến thức

`page` và `size` quyết định cách chia trang; `sort` quyết định thứ tự; các bộ lọc như `status`, `q` và khoảng giá thu hẹp tập kết quả. Spring REST Docs giúp giữ tài liệu tên query parameters gắn với request HTTP đang được kiểm thử, còn hành vi phân trang, lọc, validation và metadata vẫn phải được kiểm chứng bằng assertion phù hợp. Khi kết hợp `queryParameters(...)`, kiểm thử nghiệp vụ và quy trình build, tài liệu có thể cập nhật có kiểm soát theo thay đổi của REST API.

### Tài liệu tham khảo

- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html)
- [Spring Framework — `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.special-parameters)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
