# Document tìm kiếm với query parameters và phân trang

## 1. Mục tiêu bài thực hành

Trong bài capstone này, bạn sẽ tài liệu hóa API tìm kiếm sản phẩm có bộ lọc, sắp xếp và phân trang bằng Spring REST Docs và MockMvc. Documentation test gửi request với query parameters thực tế, xác nhận status và response payload, sau đó sinh snippet mô tả tham số và các field của kết quả.

Kết quả cuối là tài liệu Asciidoctor/Markdown có thể tái tạo trong build và CI. Khi API thay đổi tên parameter, giới hạn phân trang hoặc cấu trúc response, test và descriptor giúp phát hiện tài liệu không còn khớp.

API minh họa:

| Method | Endpoint | Chức năng |
| --- | --- | --- |
| GET | /api/products | Tìm kiếm sản phẩm |

Query parameters:

| Parameter | Ý nghĩa | Ví dụ | Mặc định |
| --- | --- | --- | --- |
| q | Từ khóa tìm theo tên/mô tả | keyboard | Không có |
| category | Lọc theo danh mục | accessories | Không có |
| minPrice | Giá tối thiểu | 100000 | Không có |
| maxPrice | Giá tối đa | 2000000 | Không có |
| page | Số trang, bắt đầu từ 0 | 0 | 0 |
| size | Số phần tử mỗi trang | 20 | 20 |
| sort | Trường và hướng sắp xếp | price,asc | createdAt,desc |

Các giá trị trên là hợp đồng mẫu. Khi áp dụng vào ứng dụng, phải dùng tên parameter, default và giới hạn thật của endpoint.

## 2. Thiết kế request và response

Một request tìm kiếm có thể là:

~~~http
GET /api/products?q=keyboard&category=accessories&minPrice=100000&maxPrice=2000000&page=0&size=20&sort=price,asc
Accept: application/json
~~~

Response dùng envelope phân trang:

~~~json
{
  "content": [
    {
      "id": "p-42",
      "name": "Mechanical Keyboard",
      "category": "accessories",
      "price": 1299000,
      "currency": "VND",
      "active": true
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1,
  "first": true,
  "last": true
}
~~~

Tách query parameters khỏi response fields khi viết descriptor. Query parameters mô tả dữ liệu client gửi trong URL; response fields mô tả dữ liệu server trả về.

## 3. DTO và response model

Có thể biểu diễn kết quả tìm kiếm bằng DTO:

~~~java
import java.math.BigDecimal;
import java.util.List;

record ProductSummary(
        String id,
        String name,
        String category,
        BigDecimal price,
        String currency,
        boolean active) {}

record ProductSearchResponse(
        List<ProductSummary> content,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean first,
        boolean last) {}
~~~

Các kiểu dữ liệu và field path trong descriptor phải dựa trên JSON sau khi Jackson serialize. Nếu ứng dụng dùng Spring Data Page trực tiếp, envelope JSON có thể khác; nên dùng DTO response ổn định để công bố API thay vì phụ thuộc cấu trúc nội bộ không chủ ý public.

## 4. Controller và query contract

Controller minh họa:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductSearchController {

    @GetMapping
    ProductSearchResponse search(
            @RequestParam(required = false) String q,
            @RequestParam(required = false) String category,
            @RequestParam(required = false) BigDecimal minPrice,
            @RequestParam(required = false) BigDecimal maxPrice,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(defaultValue = "createdAt,desc") String sort) {
        // Validate filter range, normalize sort and delegate to service.
        return productSearchService.search(
                q, category, minPrice, maxPrice, page, size, sort);
    }
}
~~~

Đây là khung minh họa. Trong ứng dụng thật, bổ sung constructor injection cho service và kiểm tra giới hạn page/size, sort fields cùng minPrice/maxPrice. Tài liệu phải công bố các giới hạn mà endpoint thực sự enforce.

## 5. Cấu hình MockMvc và REST Docs

Với Spring Boot test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductSearchDocumentationTest {

    @Autowired
    MockMvc mockMvc;
}
~~~

MockMvc gửi request trực tiếp qua Spring MVC test infrastructure. REST Docs ghi snippet khi operation gọi document(...). Dùng output directory ổn định để Asciidoctor có thể include snippet sau khi test hoàn tất.

## 6. Mô tả query parameters bằng descriptor

Khai báo từng parameter bằng parameterWithName(...). Với parameter có thể vắng mặt, dùng optional(); nếu API có default, ghi rõ trong description hoặc metadata:

~~~java
queryParameters(
        parameterWithName("q")
                .optional()
                .description("Từ khóa tìm trong tên và mô tả sản phẩm"),
        parameterWithName("category")
                .optional()
                .description("Mã danh mục cần lọc"),
        parameterWithName("minPrice")
                .optional()
                .description("Giá thấp nhất, tính theo đơn vị tiền tệ của sản phẩm"),
        parameterWithName("maxPrice")
                .optional()
                .description("Giá cao nhất"),
        parameterWithName("page")
                .description("Số trang, bắt đầu từ 0; mặc định là 0"),
        parameterWithName("size")
                .description("Số phần tử mỗi trang; mặc định là 20"),
        parameterWithName("sort")
                .description("Trường và hướng sắp xếp; mặc định là createdAt,desc"))
~~~

Các parameter page, size và sort vẫn có thể được gửi tường minh trong request để test xác nhận hành vi. Nếu API cho phép bỏ qua chúng, đánh dấu optional() và giải thích default. Descriptor chỉ mô tả hợp đồng; test riêng cần xác minh server thật sự áp dụng default đó.

## 7. Mô tả response fields của envelope phân trang

Response fields cần bao phủ cả metadata phân trang và phần tử trong content:

~~~java
responseFields(
        fieldWithPath("content")
                .description("Danh sách sản phẩm của trang hiện tại"),
        fieldWithPath("content[].id")
                .description("Mã sản phẩm"),
        fieldWithPath("content[].name")
                .description("Tên sản phẩm"),
        fieldWithPath("content[].category")
                .description("Mã danh mục"),
        fieldWithPath("content[].price")
                .description("Giá sản phẩm"),
        fieldWithPath("content[].currency")
                .description("Đơn vị tiền tệ"),
        fieldWithPath("content[].active")
                .description("Sản phẩm đang hoạt động"),
        fieldWithPath("page").description("Số trang hiện tại"),
        fieldWithPath("size").description("Kích thước trang"),
        fieldWithPath("totalElements").description("Tổng số kết quả"),
        fieldWithPath("totalPages").description("Tổng số trang"),
        fieldWithPath("first").description("Có phải trang đầu tiên không"),
        fieldWithPath("last").description("Có phải trang cuối cùng không"))
~~~

Nếu response thực tế không có một field, không thêm descriptor giả. Nếu có metadata bổ sung như numberOfElements hoặc empty, mô tả chúng theo JSON thực tế.

## 8. Documentation test cho tìm kiếm có filter và pagination

Ví dụ test kết hợp queryParameters và responseFields:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductSearchDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void searchProductsWithFiltersAndPagination() throws Exception {
        mockMvc.perform(get("/api/products")
                        .queryParam("q", "keyboard")
                        .queryParam("category", "accessories")
                        .queryParam("minPrice", "100000")
                        .queryParam("maxPrice", "2000000")
                        .queryParam("page", "0")
                        .queryParam("size", "20")
                        .queryParam("sort", "price,asc")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(0))
                .andExpect(jsonPath("$.size").value(20))
                .andExpect(jsonPath("$.content").isArray())
                .andDo(document("products-search",
                        queryParameters(
                                parameterWithName("q").description(
                                        "Từ khóa tìm trong tên và mô tả").optional(),
                                parameterWithName("category").description(
                                        "Mã danh mục cần lọc").optional(),
                                parameterWithName("minPrice").description(
                                        "Giá thấp nhất").optional(),
                                parameterWithName("maxPrice").description(
                                        "Giá cao nhất").optional(),
                                parameterWithName("page").description(
                                        "Số trang, bắt đầu từ 0; mặc định là 0"),
                                parameterWithName("size").description(
                                        "Số phần tử mỗi trang; mặc định là 20"),
                                parameterWithName("sort").description(
                                        "Trường và hướng sắp xếp; mặc định createdAt,desc")),
                        responseFields(
                                fieldWithPath("content").description("Danh sách sản phẩm"),
                                fieldWithPath("content[].id").description("Mã sản phẩm"),
                                fieldWithPath("content[].name").description("Tên sản phẩm"),
                                fieldWithPath("content[].category").description("Mã danh mục"),
                                fieldWithPath("content[].price").description("Giá sản phẩm"),
                                fieldWithPath("content[].currency").description("Đơn vị tiền tệ"),
                                fieldWithPath("content[].active").description("Trạng thái hoạt động"),
                                fieldWithPath("page").description("Số trang hiện tại"),
                                fieldWithPath("size").description("Kích thước trang"),
                                fieldWithPath("totalElements").description("Tổng số kết quả"),
                                fieldWithPath("totalPages").description("Tổng số trang"),
                                fieldWithPath("first").description("Có phải trang đầu không"),
                                fieldWithPath("last").description("Có phải trang cuối không"))));
    }
}
~~~

Test này cần fixture/service test data bảo đảm response ổn định. Các assertion status và JSONPath xác nhận hành vi; descriptors xác nhận query contract và cấu trúc response được mô tả.

## 9. Kiểm tra default pagination

Một test riêng nên bỏ page và size để xác nhận default:

~~~java
@Test
void searchUsesDefaultPageAndSize() throws Exception {
    mockMvc.perform(get("/api/products")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page").value(0))
            .andExpect(jsonPath("$.size").value(20));
}
~~~

Test này không nhất thiết phải sinh snippet mới nếu mục tiêu chỉ là kiểm tra default. Nếu muốn đưa ví dụ request không truyền page/size vào tài liệu, tạo operation identifier riêng và document các query parameters theo đúng trạng thái optional.

## 10. Kiểm tra giới hạn và trường hợp biên

Pagination API cần quy định rõ:

- page bắt đầu từ 0 hay 1.
- size tối thiểu và tối đa.
- page vượt tổng số trang trả về trang rỗng hay lỗi.
- sort chỉ chấp nhận field nào.
- Hướng sort hợp lệ là asc, desc hay cả hai.
- minPrice có được lớn hơn maxPrice không.
- Không có kết quả thì content rỗng và totalElements bằng 0 ra sao.

Bảng test gợi ý:

| Trường hợp | Request | Kỳ vọng cần xác minh |
| --- | --- | --- |
| Mặc định | Không truyền page/size | page=0, size=20 |
| Trang tiếp theo | page=1, size=10 | Trả phần tử của trang 1 |
| Size tối đa | size=100 | Chấp nhận nếu giới hạn là 100 |
| Size vượt giới hạn | size=5000 | Clamp hoặc trả lỗi theo contract |
| Page âm | page=-1 | Trả validation error theo contract |
| Không có kết quả | q=unknown-value | content rỗng, metadata nhất quán |
| Giá không hợp lệ | minPrice lớn hơn maxPrice | Trả lỗi validation nếu API quy định |
| Sort không hỗ trợ | sort=secretField,asc | Từ chối hoặc dùng fallback đã công bố |

Không ghi một hành vi giả định vào tài liệu. Mỗi quy tắc cần được xác nhận bằng test và response thực tế trước khi mô tả.

## 11. Tài liệu hóa response lỗi

Nếu query không hợp lệ, API có thể trả 400 Bad Request với payload lỗi. Ví dụ:

~~~json
{
  "code": "INVALID_PAGE_SIZE",
  "message": "size must be between 1 and 100",
  "field": "size"
}
~~~

Documentation test lỗi có thể dùng identifier riêng:

~~~java
@Test
void searchRejectsInvalidPageSize() throws Exception {
    mockMvc.perform(get("/api/products")
                    .queryParam("size", "5000")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isBadRequest())
            .andDo(document("products-search-invalid-size",
                    queryParameters(
                            parameterWithName("size")
                                    .description("Số phần tử mỗi trang")),
                    responseFields(
                            fieldWithPath("code").description("Mã lỗi"),
                            fieldWithPath("message").description("Thông báo lỗi"),
                            fieldWithPath("field").description("Parameter không hợp lệ"))));
}
~~~

Payload lỗi và status phải khớp exception handler của ứng dụng. Nếu lỗi trả về Problem Details theo RFC 9457 hoặc một cấu trúc khác, mô tả đúng cấu trúc đó thay vì dùng JSON ví dụ ở trên.

## 12. Biên soạn snippet thành AsciiDoc

Tạo phần tìm kiếm trong api-guide.adoc:

~~~adoc
== Tìm kiếm sản phẩm

=== Request

include::{snippets}/products-search/http-request.adoc[]
include::{snippets}/products-search/query-parameters.adoc[]

=== Response

include::{snippets}/products-search/http-response.adoc[]
include::{snippets}/products-search/response-fields.adoc[]

=== Lỗi: kích thước trang không hợp lệ

include::{snippets}/products-search-invalid-size/http-request.adoc[]
include::{snippets}/products-search-invalid-size/query-parameters.adoc[]
include::{snippets}/products-search-invalid-size/http-response.adoc[]
include::{snippets}/products-search-invalid-size/response-fields.adoc[]
~~~

Identifier trong include phải khớp chính xác với document(...). Chỉ include file được sinh; nếu một operation không tạo request-fields hoặc response-fields thì không thêm include cho snippet đó.

## 13. Chạy build và kiểm tra snippet

Quy trình:

~~~text
Clean generated snippets
          |
          v
Run MockMvc documentation tests
          |
          v
Verify query parameter assertions
          |
          v
Generate query and response snippets
          |
          v
Run Asciidoctor
          |
          v
Inspect HTML and includes
~~~

Với Gradle:

~~~bash
./gradlew clean test
./gradlew asciidoctor
~~~

Hoặc chạy clean asciidoctor nếu task đã dependsOn test:

~~~bash
./gradlew clean asciidoctor
~~~

Kiểm tra thư mục build/generated-snippets/products-search có query-parameters.adoc và response-fields.adoc. Đọc nội dung để xác nhận tên parameter, mô tả, thứ tự cột và field path khớp response hiện tại. Kiểm tra HTML cuối không còn include bị thiếu.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Query parameter không xuất hiện | Test không gửi parameter hoặc descriptor sai tên | So sánh URL thực tế và parameterWithName |
| Parameter tùy chọn bị báo thiếu | Chưa đánh dấu optional theo contract | Dùng optional() khi API cho phép vắng mặt |
| Response field path không khớp | API trả array hoặc envelope khác giả định | Xem JSON thực tế sau serialize |
| Default ghi trong tài liệu không đúng | Chỉ ghi mô tả nhưng chưa test default behavior | Thêm test không truyền parameter |
| Pagination metadata mâu thuẫn | Test data hoặc service trả tổng số không ổn định | Dùng fixture cố định và assert metadata |
| Sort field tùy ý gây rủi ro | API không whitelist sort properties | Kiểm tra và công bố danh sách field được hỗ trợ |
| Không có kết quả nhưng descriptor lỗi | Chưa test empty content | Thêm operation hoặc assertion cho empty result |
| Asciidoctor thiếu snippet | Task chạy trước documentation tests hoặc identifier sai | Khai báo dependency và đồng bộ include |

## 15. Bài tập capstone

Hoàn thiện tài liệu tìm kiếm Product:

1. Mô tả query parameters q, category, minPrice và maxPrice.
2. Mô tả page, size và sort, bao gồm default và giới hạn.
3. Mô tả response envelope với content, page, size, totalElements và totalPages.
4. Viết test xác nhận default pagination khi không truyền page/size.
5. Viết test cho trang tiếp theo và trường hợp không có kết quả.
6. Viết test lỗi cho size vượt giới hạn và sort không hợp lệ.
7. Include request, query parameters, response và error snippets vào AsciiDoc.
8. Chạy build sạch và kiểm tra HTML.

**Tiêu chí hoàn thành:** query descriptors phản ánh đúng URL; optional/default được mô tả chính xác; response fields bao phủ envelope và phần tử; giới hạn pagination/sort có test; snippet và HTML được tạo từ lần chạy hiện tại.

## 16. Checklist trước khi đưa vào CI

- [ ] Tên query parameters khớp controller và request thực tế.
- [ ] Parameter optional chỉ khi API cho phép vắng mặt.
- [ ] Default page/size/sort được xác minh bằng test.
- [ ] Giới hạn page/size và quy tắc sort được công bố.
- [ ] Response fields mô tả đầy đủ envelope và phần tử.
- [ ] Empty result và invalid query có test phù hợp.
- [ ] Test data ổn định, không phụ thuộc dịch vụ bên ngoài.
- [ ] Documentation tests chạy trước Asciidoctor.
- [ ] Include trỏ đúng operation identifier và snippet hiện có.
- [ ] CI lưu HTML artifact được tạo từ snippet mới.

**Ghi nhớ:** Tài liệu API tìm kiếm cần mô tả cả query contract lẫn pagination response. Kết hợp MockMvc assertions, query parameter descriptors và response field descriptors giúp người dùng hiểu cách lọc/sắp xếp/phân trang, đồng thời giúp CI phát hiện khi default hoặc cấu trúc kết quả thay đổi.
