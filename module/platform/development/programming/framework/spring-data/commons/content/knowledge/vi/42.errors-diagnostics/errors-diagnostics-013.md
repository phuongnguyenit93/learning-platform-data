# Khác biệt JSON phân trang hoặc binding HTTP sau nâng phiên bản

## 1. Cùng repository nhưng hợp đồng HTTP vẫn có thể thay đổi

Trong chương **Lỗi và chẩn đoán** của **SPRING_DATA_COMMONS**, một sự cố sau nâng phiên bản có thể xuất hiện ở lớp web dù truy vấn repository vẫn chạy đúng.

Ví dụ:

- Client không còn tìm thấy totalElements ở vị trí cũ.
- Cùng page=1 nhưng server trả một nhóm dữ liệu khác.
- size không còn có giá trị mặc định như trước.
- Sort được hiểu khác do cách truyền tham số.
- Một PathVariable không còn chuyển được thành domain object.
- Response có thêm metadata nội bộ hoặc chuyển sang dạng có liên kết.

Cần tách hai hướng biến đổi:

~~~text
Request HTTP
  → Argument resolver / conversion
    → Pageable, Sort, ID hoặc domain object
      → Service và repository
        → Page, Slice hoặc kết quả domain
          → Message converter / JSON serialization
            → Response HTTP
~~~

Một thay đổi ở đầu vào không được sửa bằng serializer. Một thay đổi JSON không được sửa bằng cách đổi query nếu query đã trả đúng dữ liệu.

Mục tiêu của bài là xác định ranh giới thay đổi, khôi phục hợp đồng cần giữ và kiểm chứng bằng request/response cụ thể.

## 2. Phân loại triệu chứng trước khi sửa

| Triệu chứng | Tầng cần kiểm tra trước |
| --- | --- |
| Bản ghi đúng nhưng metadata JSON đổi | Serialization của kết quả phân trang |
| Cùng URI nhưng khác trang dữ liệu | Binding page, size, sort và quy ước đánh số |
| Request từng được chấp nhận nay trả lỗi | Conversion, argument resolver, validation |
| Không tìm thấy field theo đường dẫn JSON cũ | DTO, naming strategy, module hoặc representation |
| Xuất hiện _links hoặc dạng nhúng khác | HATEOAS và content negotiation |
| ID URL không chuyển được thành entity | DomainClassConverter, repository discovery, conversion ID |
| Chỉ một controller khác hành vi | Annotation/default cục bộ hoặc cấu hình resolver |
| Test slice khác ứng dụng chạy thật | Context, auto-configuration hoặc bean được nạp khác nhau |

Không bắt đầu bằng giả định “Spring Data đổi query”. Trước hết so sánh tham số đã bind và đối tượng trả về từ service.

Một phép chẩn đoán có ích phải trả lời:

~~~text
Request có giống không?
Giá trị sau binding có giống không?
Kết quả nghiệp vụ có giống không?
JSON và media type có giống không?
~~~

## 3. Page là abstraction Java, không tự là schema JSON cố định

Page mô tả nội dung phân trang và metadata như số trang, kích thước trang, tổng phần tử và tổng trang. Một implementation như PageImpl còn có cấu trúc cùng các accessor phục vụ API Java.

Nếu controller trả trực tiếp Page hoặc PageImpl, JSON có thể phụ thuộc:

- Implementation thực tế.
- Phiên bản thư viện.
- JSON module được đăng ký.
- Naming strategy, mixin hoặc custom serializer.
- Cấu hình web và message converter.
- Cơ chế HATEOAS nếu có.

Các chi tiết như pageable, sort, first, last hoặc empty không nên mặc định được xem là hợp đồng công khai ổn định chỉ vì chúng từng xuất hiện trong response.

### Ví dụ khác vị trí metadata

Hai response minh họa có thể diễn đạt cùng một kết quả nhưng khác schema:

~~~json
{
  "content": [],
  "number": 0,
  "size": 20,
  "totalElements": 0,
  "totalPages": 0
}
~~~

~~~json
{
  "content": [],
  "page": {
    "number": 0,
    "size": 20,
    "totalElements": 0,
    "totalPages": 0
  }
}
~~~

Đây là ví dụ về khác biệt cấu trúc, không phải khẳng định mọi nâng phiên bản đều tự chuyển từ dạng thứ nhất sang dạng thứ hai.

Nếu client đọc response.totalElements trong khi server trả response.page.totalElements, repository đúng vẫn không ngăn được lỗi phía client.

Đổi thứ tự các field trong JSON object cũng khác với đổi tên hoặc đổi vị trí field. Không dùng so sánh chuỗi JSON thuần để kết luận một thay đổi có ý nghĩa hợp đồng.

## 4. Chọn representation phân trang có chủ đích

Có ba hướng thường gặp:

| Hướng | Ý nghĩa | Điều cần kiểm soát |
| --- | --- | --- |
| Trả Page trực tiếp | Phụ thuộc cơ chế serialization đang có | Cấu trúc thực tế và độ ổn định của hợp đồng |
| Dùng representation do Spring Data hỗ trợ | Tách phần response khỏi nhiều chi tiết PageImpl | API có trong phiên bản và cấu hình đang dùng |
| DTO do ứng dụng sở hữu | Ứng dụng quy định field và quy ước rõ | Mapping, tài liệu và contract test |

### Representation DTO của Spring Data

Trong những phiên bản có hỗ trợ, Spring Data cung cấp PagedModel ở package org.springframework.data.web và chế độ serialization VIA_DTO.

Một lựa chọn cấu hình có dạng:

~~~java
import org.springframework.data.web.config.EnableSpringDataWebSupport;
import org.springframework.data.web.config.EnableSpringDataWebSupport.PageSerializationMode;

@EnableSpringDataWebSupport(
        pageSerializationMode = PageSerializationMode.VIA_DTO)
class DataWebConfiguration {
}
~~~

Cần dùng API có trong phiên bản thực tế của dự án. Không sao chép annotation này vào mọi ứng dụng mà chưa xác định hạ tầng web đang được cấu hình qua cơ chế nào.

Khi môi trường đã có auto-configuration, việc thêm cấu hình web tường minh có thể ảnh hưởng những bean hoặc customizer đang được sử dụng. Cần kiểm tra context sau thay đổi.

Một lựa chọn khác trong phiên bản hỗ trợ là trả PagedModel tường minh:

~~~java
return new org.springframework.data.web.PagedModel<>(page);
~~~

Representation này giúp tránh gắn client trực tiếp với nhiều chi tiết nội bộ của PageImpl. Tuy vậy, vẫn cần contract test cho schema mà ứng dụng chọn sử dụng.

### Phân biệt hai PagedModel

org.springframework.data.web.PagedModel và org.springframework.hateoas.PagedModel không phải cùng một kiểu.

Representation HATEOAS có thể kèm link và cấu trúc khác tùy media type cùng assembler. Không thay import chỉ để code biên dịch mà không kiểm tra response.

Cần xem cả Content-Type và Accept. JSON thông thường và HAL không tự là hai response có thể hoán đổi mà client không thay đổi.

## 5. DTO ứng dụng giúp xác định rõ hợp đồng

Ví dụ ứng dụng chọn một schema gồm content và page:

~~~java
import java.util.List;
import org.springframework.data.domain.Page;

public record PageResponse<T>(
        List<T> content,
        PageMetadata page) {

    public static <T> PageResponse<T> from(Page<T> source) {
        return new PageResponse<>(
                List.copyOf(source.getContent()),
                new PageMetadata(
                        source.getNumber(),
                        source.getSize(),
                        source.getTotalElements(),
                        source.getTotalPages()));
    }

    public record PageMetadata(
            int number,
            int size,
            long totalElements,
            int totalPages) {
    }
}
~~~

Ví dụ dùng Java 17 và JSON serializer được cấu hình để xử lý record. Contract của ứng dụng cần xác định rõ:

- number là chỉ số trang nội bộ gốc 0 trong ví dụ.
- size là kích thước trang, không phải số phần tử thực có trong trang cuối.
- totalElements là tổng theo điều kiện truy vấn.
- totalPages là metadata lấy từ Page.
- content gồm các DTO nghiệp vụ.

Nếu API cũ còn cam kết sort, first, last hoặc link, DTO mới phải giữ hoặc thay thế chúng theo kế hoạch tương thích. Đoạn DTO trên không tự giữ mọi field từng có trong PageImpl.

Cũng không lấy PageResponse có totalElements rồi điền một giá trị giả khi service chỉ trả Slice. Nếu không có tổng số theo hợp đồng, nên có response tương ứng thay vì làm metadata trông đầy đủ nhưng sai.

## 6. Ví dụ controller với ranh giới rõ

DTO nghiệp vụ:

~~~java
import java.math.BigDecimal;

public record InvoiceDto(
        Long id,
        String invoiceNumber,
        BigDecimal total) {
}
~~~

Service ứng dụng:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface InvoiceQueryService {
    Page<InvoiceDto> find(String tenantId, Pageable pageable);
}
~~~

Controller:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/invoices")
public class InvoiceController {

    private final InvoiceQueryService invoices;

    public InvoiceController(InvoiceQueryService invoices) {
        this.invoices = invoices;
    }

    @GetMapping
    public PageResponse<InvoiceDto> list(
            @RequestParam("tenantId") String tenantId,
            @PageableDefault(
                    size = 20,
                    sort = {"createdAt", "id"},
                    direction = Sort.Direction.DESC)
            Pageable pageable) {

        return PageResponse.from(invoices.find(tenantId, pageable));
    }
}
~~~

Controller này tách hai hợp đồng:

~~~text
Argument resolver chịu trách nhiệm HTTP → Pageable.
PageResponse chịu trách nhiệm Page → response công khai.
~~~

Tuy vậy, annotation mặc định không thay thế toàn bộ cấu hình resolver, giới hạn kích thước trang hoặc quy tắc validation của sản phẩm. Các phần đó vẫn phải được xác định và kiểm thử.

## 7. Binding Pageable: cùng chuỗi page có thể mang nghĩa khác

Hạ tầng Spring Data Web thường sử dụng các tham số như page, size và sort theo cấu hình tương ứng. Tên tham số, prefix, delimiter, fallback và giới hạn có thể được tùy chỉnh.

Một khác biệt dễ gây lỗi là quy ước đánh số từ 0 hay từ 1.

### Đầu vào gốc 0

~~~text
HTTP page=0 → Pageable.getPageNumber() = 0.
HTTP page=1 → Pageable.getPageNumber() = 1.
~~~

### Đầu vào gốc 1 khi được cấu hình như vậy

~~~text
HTTP page=1 → Pageable.getPageNumber() = 0.
HTTP page=2 → Pageable.getPageNumber() = 1.
~~~

Quy ước đầu vào không tự làm Page đổi cách đánh số nội bộ. Nếu response muốn dùng số trang gốc 1, adapter response phải thực hiện chuyển đổi theo hợp đồng và kiểm tra tránh cộng hai lần.

### Dấu hiệu sau nâng phiên bản

Trước đây ứng dụng có customizer bật one-indexed input. Sau nâng phiên bản, customizer không còn được nạp do thay đổi context hoặc cách cấu hình.

Cùng page=1 có thể chuyển từ trang đầu sang trang thứ hai. JSON serialization có thể không hề thay đổi.

Cách kiểm tra là quan sát Pageable sau binding, không chỉ nhìn URI và response cuối.

Không mặc định mọi thay đổi số trang là do một default mới của framework. Có thể cấu hình cũ đã không còn có hiệu lực.

## 8. Default, fallback, max size và input không hợp lệ

Có nhiều nguồn cấu hình cùng ảnh hưởng Pageable:

- Annotation như PageableDefault tại method.
- Fallback của resolver.
- Tên và prefix tham số.
- Cấu hình one-indexed.
- Giới hạn page size.
- Bean customizer.
- Cơ chế auto-configuration.
- Resolver tùy biến.

Cần biết nguồn nào đang có hiệu lực cho đúng controller.

| Request | Câu hỏi cần xác định |
| --- | --- |
| Không truyền page và size | Giá trị mặc định thực tế là gì? |
| Chỉ truyền size | Page và sort lấy từ đâu? |
| size vượt giới hạn | Bị giới hạn, dùng fallback hay trả lỗi theo chính sách nào? |
| page âm hoặc không phải số | Resolver xử lý và ứng dụng trả status gì? |
| size bằng 0 | Có hợp lệ không, ai kiểm tra? |
| Có nhiều Pageable | Tên tham số được phân biệt ra sao? |

Không giả định mọi input không hợp lệ đều tự trả HTTP 400. Resolver và validation có thể chuẩn hóa, fallback hoặc từ chối theo cấu hình.

Nếu API yêu cầu từ chối rõ một miền giá trị, cần thiết kế kiểm tra ở ranh giới HTTP phù hợp. Một giới hạn nội bộ của resolver không tự đồng nghĩa với schema lỗi mà client mong đợi.

### Tránh kiểm thử nhầm đường binding

Một method nhận RequestParam int page dùng đường conversion khác một method nhận Pageable. Kết quả của một test không tự đại diện cho method còn lại.

## 9. Binding Sort cần giữ đúng cấu trúc tham số

Một request minh họa:

~~~text
/invoices?tenantId=t-1&page=0&size=20
&sort=createdAt,desc
&sort=id,asc
~~~

Trong cấu hình hỗ trợ cú pháp đó, mỗi sort parameter biểu đạt một tiêu chí. Không coi mọi cách gộp nhiều property và direction thành một chuỗi đều tương đương.

Cần kiểm tra:

- Property nhận được.
- Direction của từng property.
- Thứ tự các Sort.Order.
- Delimiter và tên tham số.
- Default sort khi không có sort request.
- Hành vi khi có sort request tường minh.

Ví dụ ứng dụng đổi tên field JSON từ createdAt sang created_at không tự làm repository hiểu created_at là domain property hợp lệ.

Tên sort công khai và property domain cần có hợp đồng rõ. Nếu API dùng alias, lớp chuyển đổi phải thực hiện mapping đó thay vì trông chờ serializer đổi tên ngược cho resolver.

Query tường minh hoặc native query còn có quy tắc sort riêng theo module. Phải kiểm tra đường query thật sau khi HTTP binding đã đúng.

## 10. Nhiều Pageable và qualifier

Nếu controller nhận nhiều bộ tham số phân trang, qualifier có thể được dùng để phân biệt:

~~~java
public Response list(
        @Qualifier("invoices") Pageable invoicePage,
        @Qualifier("customers") Pageable customerPage) {
    // ...
}
~~~

Qualifier ở đây là annotation của Spring beans. Với cấu hình delimiter tương ứng, tên tham số có thể có dạng:

~~~text
invoices_page
invoices_size
customers_page
customers_size
~~~

Tên thực tế phụ thuộc cấu hình. Không suy ra prefix hoặc delimiter chỉ từ một ví dụ.

Sau nâng phiên bản, nếu một custom resolver không còn được đăng ký, các tham số prefixed có thể không còn được xử lý như trước hoặc fallback xuất hiện. Test cần gửi đúng request nhiều bộ tham số và kiểm tra riêng từng Pageable.

Cũng cần dùng cơ chế resolver/customizer đúng với stack MVC hoặc WebFlux của ứng dụng. Một cấu hình cho MVC không tự tác động đến resolver reactive.

## 11. DomainClassConverter là một đường binding khác

Spring Data Web có thể hỗ trợ chuyển một giá trị URL thành domain object khi được bật và có repository phù hợp.

Ví dụ:

~~~java
@GetMapping("/{id}")
public InvoiceDto detail(
        @PathVariable("id") Invoice invoice) {
    return toDto(invoice);
}
~~~

Đường xử lý có thể gồm:

~~~text
Chuỗi ID trong URL
  → Conversion sang kiểu ID
    → Repository tìm đối tượng
      → Bind vào tham số controller
~~~

Nếu đường này thay đổi sau nâng phiên bản, cần kiểm tra:

- Hạ tầng web support có được nạp không.
- Repository có được phát hiện và đủ điều kiện cho cơ chế conversion không.
- Conversion String sang kiểu ID.
- Domain và kiểu ID của repository.
- Resolver cùng exception handler đang được dùng.
- Bản ghi có tồn tại hay không.

Trong cơ chế discovery này, repository CRUD phù hợp là một yếu tố cần kiểm tra; một interface chỉ mang tên Repository không tự bảo đảm mọi tích hợp conversion đều có hiệu lực.

### Phân biệt ID sai định dạng với không có bản ghi

Hai tình huống này khác nhau:

~~~text
ID không chuyển được sang kiểu cần thiết.
ID hợp lệ nhưng không tìm thấy entity.
~~~

Status và body lỗi thực tế còn phụ thuộc resolver cùng cách ứng dụng xử lý. Không mặc định mọi trường hợp đều tự trở thành cùng một 404.

Nếu cần kiểm soát rõ hợp đồng, có thể nhận ID tường minh rồi để service xử lý tìm kiếm và lỗi theo quy tắc ứng dụng.

Việc đổi sang cách này là thay đổi thiết kế binding, không phải một cách sửa JSON phân trang.

## 12. Quy trình chẩn đoán trước và sau nâng phiên bản

### Bước 1: Cố định request và dữ liệu

Giữ cùng URI, query parameters, header Accept và dữ liệu có thứ tự xác định. Nếu dữ liệu thay đổi, không thể quy mọi khác biệt nội dung cho binding.

### Bước 2: Ghi nhận response cũ và mới

So sánh:

~~~text
HTTP status.
Content-Type.
Cấu trúc JSON và kiểu dữ liệu.
Đường dẫn metadata.
Số phần tử và ID trong content.
Link hoặc cấu trúc nhúng nếu có.
~~~

Không chỉ so sánh nội dung content rồi bỏ qua metadata mà client đang dùng.

### Bước 3: Quan sát giá trị đã bind

Kiểm tra pageNumber, pageSize và từng Sort.Order ngay tại ranh giới service.

Nếu chúng đã khác, tập trung vào resolver/configuration trước khi sửa query.

### Bước 4: So sánh kết quả service trước serialization

Nếu Page đã có đúng nội dung, tổng số và số trang, nhưng HTTP JSON khác, tập trung vào DTO/serializer/module/media type.

Nếu service đã nhận sai Pageable hoặc trả sai dữ liệu, serializer không phải nguồn gốc.

### Bước 5: Kiểm tra cấu hình hiệu lực

Đối chiếu phiên bản và cách nạp Spring Data Web, JSON module, ObjectMapper, HATEOAS cùng customizer.

Một ObjectMapper tự tạo có thể khác bean được auto-configure. Một cấu hình thủ công có thể khiến cấu hình tự động không còn áp dụng như trước.

### Bước 6: Chọn hợp đồng cần giữ

Quyết định giữ schema cũ, dùng representation mới hay cung cấp một version API khác. Không để client tự đoán từ implementation nội bộ.

### Bước 7: Thêm test cho đúng ranh giới thay đổi

Giữ test HTTP với context phản ánh cấu hình thật, đồng thời dùng integration test repository khi cần xác minh phần truy vấn.

## 13. Kiểm thử binding và JSON trong cùng request

Ví dụ sau giả định một môi trường MVC test đã có MockMvc, controller thật, cấu hình web/JSON cần kiểm tra và một InvoiceQueryService mock được đăng ký bằng cơ chế phù hợp với phiên bản dự án.

Service được mock để cô lập hợp đồng HTTP; test này không chứng minh query database.

~~~java
@Test
void bindsPageAndSortAndReturnsTheChosenSchema() throws Exception {
    InvoiceDto first =
            new InvoiceDto(101L, "INV-101", new BigDecimal("100.00"));
    InvoiceDto second =
            new InvoiceDto(102L, "INV-102", new BigDecimal("200.00"));

    when(invoices.find(eq("tenant-1"), any(Pageable.class)))
            .thenAnswer(invocation -> {
                Pageable bound = invocation.getArgument(1);
                return new PageImpl<>(
                        List.of(first, second), bound, 3);
            });

    mockMvc.perform(get("/invoices")
                    .param("tenantId", "tenant-1")
                    .param("page", "0")
                    .param("size", "2")
                    .param("sort", "createdAt,desc", "id,asc")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.content.length()").value(2))
            .andExpect(jsonPath("$.content[0].id").value(101))
            .andExpect(jsonPath("$.page.number").value(0))
            .andExpect(jsonPath("$.page.size").value(2))
            .andExpect(jsonPath("$.page.totalElements").value(3))
            .andExpect(jsonPath("$.page.totalPages").value(2));

    ArgumentCaptor<Pageable> captor =
            ArgumentCaptor.forClass(Pageable.class);

    verify(invoices).find(eq("tenant-1"), captor.capture());

    Pageable bound = captor.getValue();
    assertThat(bound.getPageNumber()).isZero();
    assertThat(bound.getPageSize()).isEqualTo(2);

    assertThat(bound.getSort().stream().toList()).containsExactly(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("id"));
}
~~~

Đoạn test dùng JUnit Jupiter, Mockito, AssertJ và các API MockMvc tương ứng. Cấu hình minh họa mong đợi input gốc 0; nếu sản phẩm dùng input gốc 1 thì request và assertion phải đổi theo hợp đồng đó.

Assertion service argument giúp phát hiện binding sai ngay cả khi response tình cờ trông hợp lệ.

Không dựng test controller bằng một bộ resolver mặc định khác ứng dụng rồi coi đó là bằng chứng cấu hình production đúng.

## 14. Ma trận contract test nên giữ khi nâng phiên bản

| Trường hợp | Điều cần kiểm tra |
| --- | --- |
| Không có page/size/sort | Default và fallback |
| Trang đầu tường minh | Quy ước gốc 0 hoặc gốc 1 |
| Trang tiếp theo | Chuyển đổi không lệch một trang |
| Trang cuối chưa đầy | size khác số phần tử content theo định nghĩa |
| Không có kết quả | Schema metadata đúng hợp đồng |
| Trang ngoài dữ liệu | Status, content và metadata theo chính sách |
| Nhiều sort parameter | Property, direction và thứ tự |
| Size vượt giới hạn | Chuẩn hóa hoặc lỗi đúng quy tắc |
| Input sai kiểu | Status và schema lỗi |
| Nhiều Pageable | Prefix/qualifier đúng |
| Accept khác nhau | Representation và Content-Type |
| DomainClassConverter | ID sai định dạng và entity không tồn tại |
| JSON naming/module tùy chỉnh | Field không đổi ngoài chủ đích |

JSONPath hoặc so sánh cấu trúc thường phù hợp hơn việc khóa thứ tự field trong chuỗi JSON object.

Nếu dùng snapshot response, fixture phải ổn định và snapshot cần được đánh giá theo thay đổi hợp đồng. Không tự cập nhật toàn bộ snapshot chỉ để test xanh.

## 15. Chọn cách khắc phục theo tầng

| Nguyên nhân | Hướng xử lý |
| --- | --- |
| JSON phụ thuộc PageImpl thay đổi | Chọn representation/DTO rõ và kiểm thử |
| Client cần đường dẫn metadata cũ | Giữ adapter tương thích hoặc thay client theo kế hoạch |
| One-indexed configuration mất hiệu lực | Khôi phục đúng resolver/customizer và test |
| Fallback/default khác | Cấu hình tường minh ở phạm vi phù hợp |
| Sort request không đúng cú pháp | Sửa contract tham số và test nhiều tiêu chí |
| Naming JSON bị dùng nhầm làm property sort | Mapping alias HTTP sang domain rõ ràng |
| HATEOAS hoặc media type khác | Chọn representation và content negotiation có chủ đích |
| ObjectMapper khác cấu hình dự kiến | Đồng bộ module/serializer với bean thật được sử dụng |
| DomainClassConverter không hoạt động | Sửa web support, discovery hoặc nhận ID tường minh |
| Test context khác ứng dụng | Nạp cấu hình đúng ranh giới cần chứng minh |

Không đổi query lookup strategy, entity mapping hoặc index nếu bằng chứng cho thấy thay đổi nằm hoàn toàn ở HTTP serialization.

Không bật một serializer hoặc annotation toàn cục chỉ để sửa một endpoint mà chưa xem tác động đến các endpoint còn lại cùng dùng Page.

## 16. Những kết luận cần tránh

- “Nâng Spring Data thì mọi response Page đều tự đổi sang cùng một dạng.”
- “Bật input gốc 1 thì JSON number cũng tự thành gốc 1.”
- “PageableDefault bảo đảm mọi input sai đều bị từ chối.”
- “Tên field JSON luôn dùng được làm property Sort.”
- “Hai PagedModel cùng tên là cùng một representation.”
- “Repository test xanh thì binding HTTP cũng đúng.”
- “MockMvc test với service mock chứng minh database đã phân trang đúng.”
- “Domain object không bind được thì chắc chắn bản ghi không tồn tại.”
- “Chỉ khác thứ tự field JSON là schema đã thay đổi.”

Cần kết luận từ request, giá trị sau binding, kết quả nghiệp vụ và response thực tế của cấu hình đang chạy.

## 17. Bài tập áp dụng

1. Ghi lại một request phân trang gồm page, size và hai tiêu chí sort.
2. Kiểm tra Pageable mà service nhận được trước và sau một thay đổi cấu hình.
3. Chọn một schema response rõ, xác định quy ước số trang đầu vào và đầu ra.
4. Viết test metadata JSON thay vì dựa vào chi tiết PageImpl.
5. Kiểm tra trường hợp không truyền tham số, input sai và size vượt giới hạn.
6. Nếu dùng HATEOAS, kiểm tra Accept và Content-Type tương ứng.
7. Nếu dùng domain binding, phân biệt ID sai định dạng với entity không tồn tại.
8. Mô tả cách giữ tương thích cho client đang dùng hợp đồng cũ.

Chẩn đoán thay đổi sau nâng phiên bản cần theo dõi riêng hai chiều HTTP vào và JSON ra. Khi binding, representation và hợp đồng công khai được xác định rõ, có thể sửa đúng tầng và ngăn lỗi lặp lại bằng contract test.
