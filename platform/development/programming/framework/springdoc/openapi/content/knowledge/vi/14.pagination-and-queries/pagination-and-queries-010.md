# Kiểm tra dữ liệu phân trang được tuần tự hóa thay vì dựa vào tên kiểu

## 1. Vì sao phải kiểm tra JSON thực tế của response phân trang?

Trong Spring Boot, controller thường trả về Page, Slice hoặc List để biểu diễn kết quả truy vấn. Những kiểu Java này giúp ứng dụng làm việc với dữ liệu phân trang, nhưng tên kiểu trả về không phải là hợp đồng JSON mà client trực tiếp nhận được.

Khi Spring MVC ghi response, Jackson và các cấu hình serialization quyết định cấu trúc JSON cuối cùng. Cùng một kiểu Page có thể được serialize theo các cách khác nhau tùy phiên bản Spring Data, cách cấu hình và kiểu wrapper được dùng. Springdoc OpenAPI lại tạo schema dựa trên chữ ký controller, generic type, annotation và model resolver. Vì vậy, schema suy luận từ tên kiểu Java có thể không phản ánh chính xác JSON trên đường truyền.

Ví dụ, một controller khai báo trả về Page<ProductResponse>. Client cần biết response thực tế có các trường content, page, totalElements, totalPages hay một cấu trúc khác. Client không cần biết implementation nội bộ đang dùng PageImpl hay một implementation Page khác.

Khi thiết kế hợp đồng API phân trang, cần xác minh hai đầu:

- **JSON runtime**: body thực sự được Jackson serialize và gửi cho client.
- **OpenAPI schema**: tài liệu Springdoc công bố cho operation đó.

Hai đầu cần khớp về tên property, kiểu dữ liệu, cấu trúc lồng nhau, giá trị mặc định và metadata phân trang. Bài này tập trung vào cách kiểm tra response đã tuần tự hóa, các lựa chọn biểu diễn Page ổn định và cách đồng bộ schema Springdoc với payload thực tế.

## 2. Phân biệt kiểu trả về Java với JSON trên đường truyền

Một phương thức có thể khai báo:

~~~java
@GetMapping("/api/products")
public Page<ProductResponse> findAll(Pageable pageable) {
    return productService.findAll(pageable);
}
~~~

Chữ ký trên cho biết controller trả về một đối tượng Page có phần tử ProductResponse. Nó chưa mô tả đầy đủ JSON mà client nhận được.

Trong quá trình tạo response:

1. Spring gọi controller và nhận đối tượng Page.
2. HttpMessageConverter chọn Jackson để ghi body theo media type.
3. Jackson duyệt đối tượng runtime cùng các module, annotation và cấu hình.
4. JSON được ghi vào HTTP response.
5. Client chỉ nhìn thấy JSON, status, headers và media type.

Do đó, không nên suy luận payload chỉ từ tên Page, PageImpl hoặc Slice. Hãy gọi endpoint hoặc serialize một đối tượng mẫu bằng ObjectMapper để xem cấu trúc thật.

Ví dụ một JSON response có thể có dạng:

~~~json
{
  "content": [
    {
      "id": 101,
      "name": "Bàn phím cơ"
    }
  ],
  "page": {
    "size": 20,
    "number": 0,
    "totalElements": 41,
    "totalPages": 3
  }
}
~~~

Đây là một cấu trúc response có metadata được đặt trong object page. Một cấu hình khác có thể trả các trường phân trang ở cấp gốc. Client cần một cấu trúc ổn định được API công bố, không cần đoán dựa vào implementation.

## 3. Page, Slice và List mang ngữ nghĩa khác nhau

Spring Data cung cấp nhiều kiểu kết quả truy vấn:

| Kiểu Java | Ngữ nghĩa | Metadata thường cần cho client |
|---|---|---|
| Page<T> | Một trang dữ liệu và thông tin tổng số phần tử/trang | content, page number, size, totalElements, totalPages |
| Slice<T> | Một phần dữ liệu và thông tin còn trang tiếp theo hay không | content, number, size, hasNext, hasPrevious |
| List<T> | Danh sách dữ liệu không mang metadata phân trang | Mảng phần tử |
| Window<T> với scrolling API | Một cửa sổ dữ liệu theo cơ chế cuộn | Nội dung và vị trí tiếp tục theo API cụ thể |

Page thường cần truy vấn tổng số bản ghi để tính totalElements và totalPages. Slice có thể tránh truy vấn count và chỉ cho biết có dữ liệu tiếp theo. List không tự biểu diễn metadata phân trang.

Đừng khai báo schema Page nếu response runtime chỉ là List. Tương tự, nếu API trả Slice nhưng tài liệu hiển thị totalPages, đó là dấu hiệu schema đang mô tả sai hoặc ứng dụng đã tự bổ sung metadata ở một lớp khác.

Việc chọn Page, Slice hay List phải dựa trên yêu cầu client. Giao diện cần hiển thị tổng số trang thường cần Page; luồng cuộn vô hạn có thể chỉ cần Slice hoặc cursor; danh sách nhỏ có thể chỉ cần List.

## 4. Vấn đề khi serialize trực tiếp PageImpl

PageImpl là implementation phổ biến của Page. Nếu trả trực tiếp PageImpl, Jackson có thể serialize các property được expose bởi implementation và các interface liên quan. Hình dạng JSON đó có thể bao gồm content, pageable, sort, number, size, totalElements, totalPages, first, last, numberOfElements hoặc empty, tùy phiên bản và cấu hình.

Cấu trúc được serialize trực tiếp từ PageImpl không nên được xem là hợp đồng JSON ổn định. Thay đổi phiên bản Spring Data hoặc cách cấu hình serialization có thể làm thay đổi chi tiết JSON mà client đang phụ thuộc.

Vấn đề không nằm ở việc Page không hữu ích trong tầng repository/service. Page vẫn là abstraction phù hợp để truy vấn. Vấn đề là đưa trực tiếp implementation hoặc cấu trúc serialization của nó thành payload công khai mà không có lớp hợp đồng ổn định.

Một nguyên tắc dễ áp dụng:

- Dùng Page<T> bên trong ứng dụng để truy vấn và tính metadata.
- Chuyển kết quả sang một response representation có cấu trúc được kiểm soát.
- Mô tả chính representation đó trong OpenAPI.
- Kiểm thử JSON thực tế để bảo đảm cấu trúc không thay đổi ngoài ý muốn.

## 5. Dùng PagedModel để có representation ổn định hơn

Spring Data cung cấp **PagedModel** trong package spring-data-web để bọc Page và cung cấp một representation dành cho serialization.

Ví dụ:

~~~java
@GetMapping("/api/products")
public PagedModel<ProductResponse> findAll(Pageable pageable) {
    Page<ProductResponse> result = productService.findAll(pageable);
    return new PagedModel<>(result);
}
~~~

PagedModel biểu diễn nội dung và metadata trang theo cấu trúc ổn định hơn so với serialize trực tiếp PageImpl. Một JSON response thường có dạng:

~~~json
{
  "content": [
    {
      "id": 101,
      "name": "Bàn phím cơ"
    }
  ],
  "page": {
    "size": 20,
    "number": 0,
    "totalElements": 41,
    "totalPages": 3
  }
}
~~~

Client đọc danh sách từ content và metadata từ page. Các trường cụ thể cần được kiểm tra trên phiên bản Spring Data đang sử dụng và cấu hình ObjectMapper thực tế.

PagedModel là lớp biểu diễn response. Service vẫn có thể trả Page<ProductResponse>; controller hoặc mapper chuyển Page sang PagedModel trước khi gửi ra ngoài.

Nếu Springdoc suy luận schema từ PagedModel chưa thể hiện đúng generic item type hoặc metadata mong muốn, hãy bổ sung response schema cụ thể và kiểm tra JSON/YAML được sinh ra. Đừng cho rằng tên PagedModel tự bảo đảm mọi công cụ OpenAPI sẽ tạo ra schema đúng trong mọi phiên bản.

## 6. Cấu hình PageSerializationMode.VIA_DTO

Trong các phiên bản Spring Data hỗ trợ cơ chế page serialization mode, có thể cấu hình Spring Data Web để chuyển Page thành representation DTO khi ghi JSON thay vì serialize trực tiếp PageImpl.

Ví dụ:

~~~java
@Configuration
@EnableSpringDataWebSupport(
    pageSerializationMode =
        EnableSpringDataWebSupport.PageSerializationMode.VIA_DTO
)
public class WebConfiguration {
}
~~~

Chế độ VIA_DTO sử dụng representation ổn định của Spring Data cho Page khi serialize. Chế độ DIRECT giữ cách serialize trực tiếp đối tượng Page. Với API công khai, VIA_DTO giúp giảm phụ thuộc vào chi tiết nội bộ của PageImpl.

Một số điểm cần lưu ý:

- Tùy chọn này phụ thuộc phiên bản Spring Data Commons đang dùng.
- Hãy kiểm tra enum và cách cấu hình của đúng phiên bản dependency.
- Cấu hình ảnh hưởng đến serialization response của Page trong phạm vi Spring Data Web.
- Nó không tự chứng minh OpenAPI schema của mọi endpoint đã đúng.
- Nếu API có custom serializer, ResponseBodyAdvice hoặc wrapper khác, JSON cuối cùng vẫn cần được kiểm tra.

Khi bật VIA_DTO, hãy chụp lại JSON thực tế và cập nhật schema OpenAPI theo cấu trúc mới. Không nên chỉ đổi cấu hình mà bỏ qua contract test.

## 7. Tạo response DTO riêng để kiểm soát hợp đồng

Với API cần kiểm soát chính xác tên property, metadata và khả năng tương thích, một DTO riêng thường là lựa chọn rõ ràng.

Ví dụ:

~~~java
public record PageInfoResponse(
    int number,
    int size,
    long totalElements,
    int totalPages
) {}

public record ProductPageResponse(
    List<ProductResponse> content,
    PageInfoResponse page
) {}
~~~

Mapper chuyển Page sang response DTO:

~~~java
public final class ProductPageMapper {

    private ProductPageMapper() {}

    public static ProductPageResponse from(Page<ProductResponse> source) {
        PageInfoResponse pageInfo = new PageInfoResponse(
            source.getNumber(),
            source.getSize(),
            source.getTotalElements(),
            source.getTotalPages()
        );

        return new ProductPageResponse(
            source.getContent(),
            pageInfo
        );
    }
}
~~~

Controller:

~~~java
@GetMapping("/api/products")
public ProductPageResponse findAll(Pageable pageable) {
    Page<ProductResponse> result = productService.findAll(pageable);
    return ProductPageMapper.from(result);
}
~~~

JSON được xác định bởi record DTO:

~~~json
{
  "content": [
    {
      "id": 101,
      "name": "Bàn phím cơ"
    }
  ],
  "page": {
    "number": 0,
    "size": 20,
    "totalElements": 41,
    "totalPages": 3
  }
}
~~~

Lợi ích của DTO riêng:

- Tên property là một phần rõ ràng của hợp đồng.
- Có thể thêm hoặc bỏ metadata mà không phụ thuộc PageImpl.
- Springdoc có thể suy luận schema từ kiểu response cụ thể.
- Dễ viết test JSON và contract test.
- Có thể duy trì cùng representation ngay cả khi đổi cách truy vấn ở tầng repository.

Đổi lại, cần viết mapper và duy trì DTO. Với API công khai hoặc API có nhiều client, chi phí này thường đáng giá vì cấu trúc JSON được kiểm soát rõ.

## 8. Chọn metadata phù hợp với trải nghiệm client

Không phải client nào cũng cần toàn bộ metadata của Page. Hãy chọn các trường theo khả năng mà giao diện cần.

Ví dụ một PageInfo có thể chứa:

| Trường | Ý nghĩa |
|---|---|
| number | Chỉ số trang hiện tại, thường bắt đầu từ 0 |
| size | Kích thước trang được áp dụng |
| totalElements | Tổng số bản ghi sau khi lọc |
| totalPages | Tổng số trang |
| first | Có phải trang đầu không |
| last | Có phải trang cuối không |
| numberOfElements | Số phần tử thực tế trong trang |

Nếu API dùng Slice, metadata có thể là:

| Trường | Ý nghĩa |
|---|---|
| number | Chỉ số phần đang đọc |
| size | Kích thước tối đa |
| numberOfElements | Số phần tử thực tế |
| hasNext | Có phần tiếp theo không |
| hasPrevious | Có phần trước không |

Nếu API dùng cursor, có thể công bố nextCursor và hasNext. Đừng thêm totalPages cho cursor response nếu backend không tính hoặc không bảo đảm tổng số trang.

Tổng số phần tử cần được tính sau khi áp dụng bộ lọc. Nếu client lọc status=ACTIVE, totalElements phải phản ánh số bản ghi ACTIVE, không phải tổng số sản phẩm trong database.

## 9. Springdoc suy luận schema từ kiểu trả về như thế nào?

Springdoc đọc kiểu trả về của controller, generic type và các annotation OpenAPI để xây dựng Response Object. Ví dụ:

~~~java
@GetMapping("/api/products")
public Page<ProductResponse> findAll(Pageable pageable) {
    return productService.findAll(pageable);
}
~~~

Từ chữ ký này, Springdoc có thể nhận ra kiểu Page và kiểu phần tử ProductResponse. Tuy nhiên, schema được suy luận không nhất thiết phản ánh chính xác kết quả Jackson sau khi áp dụng page serialization mode, mixin, custom serializer hoặc response advice.

Đặc biệt, có thể xảy ra hai tình huống:

- **Runtime serialization đã thay đổi**: Page được chuyển thành PagedModel hoặc DTO nhưng Springdoc vẫn suy luận từ kiểu khai báo khác.
- **Generic type bị mất**: phương thức trả về kiểu raw, wildcard hoặc wrapper trung gian khiến schema item không còn cụ thể.

Với response DTO riêng, chữ ký controller trực tiếp thể hiện representation công khai, nên Springdoc có cơ sở rõ hơn để tạo schema. Nếu cần, có thể dùng @ApiResponse và @Content để khai báo schema implementation cụ thể.

Ví dụ:

~~~java
@GetMapping("/api/products")
@ApiResponse(
    responseCode = "200",
    description = "Trang sản phẩm",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ProductPageResponse.class)
    )
)
public ProductPageResponse findAll(Pageable pageable) {
    return ProductPageMapper.from(productService.findAll(pageable));
}
~~~

Ở đây schema implementation là ProductPageResponse, trùng với kiểu body thực tế. Annotation chỉ mô tả tài liệu; nó không chuyển đổi response runtime.

## 10. Kiểm tra JSON được serialize bằng ObjectMapper

Có thể dùng ObjectMapper trong test để kiểm tra representation mà Jackson tạo ra từ một đối tượng mẫu.

Ví dụ với PagedModel:

~~~java
@Test
void serializesPageUsingStableRepresentation() throws Exception {
    Page<ProductResponse> page = new PageImpl<>(
        List.of(new ProductResponse(101L, "Bàn phím cơ")),
        PageRequest.of(0, 20),
        41
    );

    PagedModel<ProductResponse> model = new PagedModel<>(page);
    String json = objectMapper.writeValueAsString(model);

    JsonNode root = objectMapper.readTree(json);

    assertThat(root.has("content")).isTrue();
    assertThat(root.path("content").isArray()).isTrue();
    assertThat(root.path("page").path("number").asInt()).isZero();
    assertThat(root.path("page").path("size").asInt()).isEqualTo(20);
    assertThat(root.path("page").path("totalElements").asLong()).isEqualTo(41);
}
~~~

Test này kiểm tra serialization của đối tượng bằng ObjectMapper. Nó hữu ích để phát hiện thay đổi khi nâng cấp Jackson hoặc Spring Data.

Tuy nhiên, ObjectMapper test không thay thế kiểm thử HTTP. Spring MVC có thể dùng converter, configuration, advice hoặc filter khác với ObjectMapper mà test tự tạo. Vì vậy, cần kiểm tra thêm response qua MockMvc hoặc WebTestClient để xác minh đúng cấu hình của ứng dụng.

## 11. Kiểm tra JSON HTTP bằng MockMvc

Một integration test có thể gọi endpoint và kiểm tra cấu trúc body thật:

~~~java
mockMvc.perform(get("/api/products")
        .param("page", "0")
        .param("size", "20"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.content").isArray())
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$.page.size").value(20))
    .andExpect(jsonPath("$.page.totalElements").value(41));
~~~

Nếu API dùng cấu trúc PageImpl trực tiếp, các assertion phải phản ánh đúng JSON thực tế hiện tại. Nếu chuyển sang PagedModel hoặc DTO, cập nhật assertion để kiểm tra contract mới.

Nên kiểm tra thêm:

- Trang đầu, trang giữa và trang cuối.
- Trang không có kết quả.
- Trang vượt phạm vi.
- Bộ lọc làm thay đổi totalElements.
- Sort làm thay đổi thứ tự content.
- Size mặc định và size bị giới hạn.
- Trường metadata không được công bố không xuất hiện ngoài ý muốn.

Test nên tập trung vào contract mà client được phép phụ thuộc. Tránh assert những thuộc tính nội bộ không thuộc hợp đồng công khai, trừ khi API chủ động công bố chúng.

## 12. Kiểm tra OpenAPI schema được Springdoc sinh ra

Sau khi kiểm tra JSON runtime, tải OpenAPI document:

~~~http
GET /v3/api-docs
~~~

Tìm operation tương ứng và xác minh schema:

- Response code đúng, ví dụ 200.
- Media type đúng, thường là application/json.
- Schema body có đúng cấu trúc object hay array.
- content có kiểu item ProductResponse.
- Metadata page có các trường number, size, totalElements và totalPages theo hợp đồng.
- Không xuất hiện các thuộc tính nội bộ không được công bố.
- Required, nullable và format phù hợp với JSON thực tế.
- Example phản ánh đúng cấu trúc response.

Nếu dùng DTO riêng, OpenAPI có thể tham chiếu component ProductPageResponse. Nếu dùng PagedModel, kiểm tra schema sinh ra có thể hiện content và page đúng không. Nếu Springdoc chỉ tạo schema quá chung hoặc không giữ generic item, hãy bổ sung mô tả tường minh hoặc dùng DTO cụ thể.

Một contract test tốt có thể đọc OpenAPI JSON và so sánh các thuộc tính quan trọng với response fixture. Điều này giúp phát hiện trường hợp Jackson serialization đổi nhưng tài liệu chưa được cập nhật, hoặc tài liệu đổi nhưng runtime vẫn trả cấu trúc cũ.

## 13. Phân biệt JSON serialization với Pageable query parameters

Pageable thường xuất hiện ở đầu vào controller:

~~~java
@GetMapping("/api/products")
public ProductPageResponse findAll(
    @ParameterObject Pageable pageable
) {
    return ProductPageMapper.from(productService.findAll(pageable));
}
~~~

`@ParameterObject` giúp Springdoc mô tả Pageable thành query parameter như page, size và sort. Nó chỉ ảnh hưởng cách tài liệu mô tả đầu vào.

Cần phân biệt hai phía:

- **Request parameters**: page, size, sort cho client biết cách yêu cầu trang dữ liệu.
- **Response JSON**: content và metadata cho client biết server đã trả trang nào và có bao nhiêu dữ liệu.

Việc tài liệu hiển thị đúng page/size/sort không chứng minh response schema đúng. Tương tự, response có content/page không có nghĩa các query parameter đầu vào đã được mô tả đúng.

Hãy kiểm tra request và response như hai phần độc lập của cùng một operation.

## 14. Khi dùng Slice hoặc cursor, không công bố metadata của Page

Nếu service trả Slice:

~~~java
@GetMapping("/api/products/recent")
public Slice<ProductResponse> findRecent(Pageable pageable) {
    return productService.findRecent(pageable);
}
~~~

Slice không cung cấp totalElements và totalPages như Page. Nếu client cần biết còn dữ liệu tiếp theo, hãy công bố hasNext và cách tiếp tục truy vấn.

Với cursor pagination, response có thể là:

~~~java
public record ProductCursorResponse(
    List<ProductResponse> content,
    String nextCursor,
    boolean hasNext
) {}
~~~

Schema cần thể hiện nextCursor và hasNext. Cursor nên được coi là giá trị opaque; client gửi lại giá trị nhận được mà không tự diễn giải.

Không nên dùng schema Page chỉ vì tên endpoint có chữ page hoặc method nhận Pageable. Hãy dựa trên payload thực tế. Một endpoint có thể nhận page/size nhưng trả DTO tùy biến, Slice hoặc một representation khác.

## 15. Versioning khi thay đổi cấu trúc response phân trang

Thay đổi từ JSON PageImpl trực tiếp sang PagedModel hoặc DTO có thể làm thay đổi tên property, cấu trúc lồng nhau và metadata. Dù dữ liệu content không đổi, client vẫn có thể bị ảnh hưởng nếu đang đọc các trường cũ.

Ví dụ, client hiện tại đang đọc `totalElements` ở cấp gốc:

~~~json
{
  "content": [],
  "totalElements": 41,
  "totalPages": 3
}
~~~

Sau thay đổi, metadata được đặt dưới `page`:

~~~json
{
  "content": [],
  "page": {
    "totalElements": 41,
    "totalPages": 3
  }
}
~~~

Đây là thay đổi cấu trúc JSON và có thể phá vỡ client. Cần đánh giá như một thay đổi hợp đồng API, cập nhật version hoặc cung cấp giai đoạn chuyển tiếp theo chính sách dự án.

Khi thay đổi:

1. Ghi lại schema và JSON hiện tại.
2. Xác định client đang phụ thuộc vào trường nào.
3. Thiết kế representation mới và cập nhật OpenAPI.
4. Viết test cho cấu trúc cũ/mới theo kế hoạch migration.
5. Công bố thời điểm ngừng hỗ trợ representation cũ.
6. Theo dõi client đã chuyển đổi trước khi loại bỏ tương thích.

Không nên nâng cấp Spring Data hoặc thay page serialization mode mà không kiểm tra tác động tới JSON công khai.

## 16. Các lỗi thường gặp khi kiểm tra dữ liệu phân trang

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Schema OpenAPI khác JSON runtime | Springdoc suy luận từ kiểu Java nhưng Jackson serialize theo wrapper hoặc cấu hình khác |
| JSON có nhiều trường nội bộ của PageImpl | Đang serialize trực tiếp implementation Page |
| Client không tìm thấy totalElements | Metadata được đặt ở vị trí khác hoặc API dùng Slice/cursor |
| Item schema là object rỗng | Generic ProductResponse bị mất khi khai báo raw type hoặc wrapper |
| Springdoc mô tả Page nhưng runtime trả DTO | Chữ ký controller, @ApiResponse hoặc customizer chưa đồng nhất |
| PagedModel JSON đúng nhưng schema sai | Model resolver hoặc phiên bản Springdoc chưa suy luận representation mong muốn |
| Test ObjectMapper pass nhưng HTTP response sai | MVC converter hoặc response advice dùng cấu hình khác |
| totalElements không khớp bộ lọc | Truy vấn count không áp dụng cùng điều kiện lọc |
| Nâng cấp dependency làm JSON thay đổi | Page serialization phụ thuộc phiên bản Spring Data/Jackson |
| Client bị lỗi sau khi đổi cấu trúc metadata | Thay đổi JSON là breaking change nhưng chưa quản lý version |

Khi điều tra, so sánh ba bằng chứng: kiểu trả về controller, JSON runtime và OpenAPI schema. Chỉ khi cả ba được hiểu rõ mới quyết định sửa annotation, DTO, serializer hay cấu hình.

## 17. Quy trình xác minh contract phân trang

Một quy trình có thể áp dụng cho mỗi endpoint phân trang:

1. Xác định client cần Page, Slice, cursor hay danh sách đơn giản.
2. Chọn representation JSON ổn định: DTO riêng, PagedModel hoặc cấu hình page serialization phù hợp.
3. Chạy endpoint và lưu JSON mẫu cho trường hợp có dữ liệu, rỗng và có filter.
4. Kiểm tra tên, kiểu và vị trí của từng property.
5. Tải OpenAPI JSON từ Springdoc và so sánh response schema với JSON runtime.
6. Viết MockMvc/WebTestClient test cho các trường hợp biên.
7. Kiểm tra schema có giữ generic item type và metadata chính xác.
8. Khi nâng cấp Spring Data, Jackson hoặc Springdoc, chạy lại contract test.
9. Đánh giá thay đổi cấu trúc như thay đổi API version nếu client bị ảnh hưởng.

Có thể đưa kiểm tra OpenAPI và contract test vào CI để phát hiện khác biệt trước khi phát hành. Điều này đặc biệt hữu ích với API được nhiều ứng dụng frontend, mobile hoặc dịch vụ khác sử dụng.

## 18. Nguyên tắc thiết kế response phân trang ổn định

Khi dùng Spring Data và Springdoc, hãy ghi nhớ:

1. Page, Slice và List là kiểu Java; JSON được quyết định bởi serialization thực tế.
2. Tránh phụ thuộc vào cấu trúc serialize trực tiếp PageImpl như hợp đồng công khai.
3. Dùng PagedModel hoặc DTO riêng nếu cần representation ổn định.
4. Kiểm tra PageSerializationMode.VIA_DTO theo phiên bản Spring Data đang dùng.
5. Mô tả metadata đúng vị trí và không công bố totalPages nếu runtime không cung cấp.
6. Dùng DTO response cụ thể để Springdoc suy luận schema rõ ràng.
7. Kiểm tra JSON bằng ObjectMapper và kiểm tra HTTP bằng MockMvc/WebTestClient.
8. So sánh OpenAPI document với JSON runtime.
9. Quản lý thay đổi cấu trúc response như thay đổi hợp đồng API.
10. Không dựa vào tên kiểu hoặc giao diện Swagger UI để kết luận payload đúng.

Một hợp đồng phân trang đáng tin cậy bắt đầu từ JSON mà client thật sự nhận được. Kiểu Page giúp tầng dữ liệu làm việc thuận tiện, còn response DTO hoặc PagedModel giúp kiểm soát representation công khai. Khi Springdoc mô tả đúng representation đó và test xác minh cả runtime lẫn OpenAPI, client có thể tích hợp ổn định qua các lần nâng cấp framework.

