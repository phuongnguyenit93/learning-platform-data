# Đánh dấu deprecated và mô tả lộ trình thay thế

Khi một endpoint, tham số hoặc field không còn được khuyến nghị sử dụng, hãy đánh dấu deprecated và cung cấp thông tin thay thế đủ rõ để consumer có thể chuyển đổi. Springdoc-openapi có thể đưa trạng thái này vào OpenAPI từ annotation của Java hoặc Swagger annotations. OpenAPI biểu diễn trạng thái bằng thuộc tính boolean deprecated; tài liệu cần bổ sung lý do, phương án thay thế, mốc thời gian và hướng dẫn migration.

Deprecation là thông báo về vòng đời của API. Nó không tự tắt endpoint, không thay đổi response và không xóa code. Consumer vẫn có thể gọi API cũ trong giai đoạn chuyển tiếp. Việc ngừng phục vụ hoặc xóa endpoint là một thay đổi riêng, thường có ảnh hưởng tương thích và cần được quản lý theo chính sách versioning.

Một lộ trình thay thế tốt có bốn phần: xác định chính xác thành phần deprecated, công bố API thay thế, thông báo trong tài liệu và response runtime, rồi theo dõi quá trình chuyển đổi trước khi ngừng hỗ trợ.

## 1. Deprecation khác gì với ẩn hoặc xóa API?

Các trạng thái sau có ý nghĩa khác nhau:

| Trạng thái | Ý nghĩa | Consumer hiện tại |
|---|---|---|
| Active | API đang được hỗ trợ và khuyến nghị sử dụng | Tiếp tục sử dụng |
| Deprecated | API vẫn hoạt động nhưng không nên dùng cho tích hợp mới; cần chuyển sang phương án thay thế | Có thể tiếp tục gọi trong thời gian chuyển tiếp |
| Hidden from docs | Endpoint bị loại khỏi OpenAPI document | Runtime có thể vẫn hoạt động; consumer không còn thấy trong tài liệu |
| Disabled | Runtime từ chối hoặc không còn cung cấp endpoint | Request có thể nhận 404, 410 hoặc lỗi theo thiết kế |
| Removed | Route, parameter hoặc field đã bị xóa khỏi contract/runtime | Consumer phụ thuộc vào phần đã xóa có thể hỏng |

Không dùng @Hidden hoặc @Operation(hidden = true) để thay cho deprecation. Hidden chỉ điều khiển việc hiển thị trong tài liệu; nó không nói cho consumer biết API vẫn tồn tại nhưng sắp được thay thế. Tương tự, không xóa endpoint ngay khi vừa đánh dấu deprecated.

Deprecation cũng không đồng nghĩa một thay đổi đã trở nên tương thích ngược. Nếu API cũ vẫn giữ nguyên hành vi và chỉ được đánh dấu deprecated, consumer có thời gian migration. Nếu cùng lúc đổi kiểu dữ liệu, xóa field hoặc thay đổi ý nghĩa response, đó vẫn là một thay đổi contract cần đánh giá riêng.

## 2. Thuộc tính deprecated trong OpenAPI

OpenAPI có thuộc tính boolean deprecated ở các đối tượng quan trọng:

| Đối tượng OpenAPI | Phạm vi đánh dấu | Ví dụ |
|---|---|---|
| Operation Object | Toàn bộ operation HTTP | GET /api/v1/products |
| Parameter Object | Một path, query, header hoặc cookie parameter | Query parameter archived |
| Header Object | Một response/request header được mô tả | Header X-Legacy-Mode |
| Schema Object | Một model hoặc property trong schema | Property legacyCode |

Khi deprecated là true, tài liệu thông báo consumer nên tránh sử dụng thành phần đó. Đây là metadata hướng dẫn consumer; nó không tự cung cấp ngày ngừng hỗ trợ hoặc URL thay thế.

Ví dụ OpenAPI rút gọn:

~~~yaml
paths:
  /api/v1/products:
    get:
      deprecated: true
      summary: Liệt kê sản phẩm (deprecated)
      description: Dùng GET /api/v2/products. Endpoint v1 dự kiến ngừng phục vụ sau ngày 31-12-2027.
      parameters:
        - name: archived
          in: query
          deprecated: true
          description: Dùng query parameter status của API v2.
          schema:
            type: boolean
      responses:
        '200':
          description: Danh sách sản phẩm
components:
  schemas:
    Product:
      type: object
      properties:
        legacyCode:
          type: string
          deprecated: true
          description: Dùng productCode.
        productCode:
          type: string
~~~

Tài liệu OpenAPI chỉ có cờ boolean. Nếu cần thông tin chi tiết như phiên bản bắt đầu deprecated, ngày sunset, replacement URL hoặc bước chuyển đổi, hãy ghi trong description, externalDocs, extension có quy ước rõ ràng hoặc HTTP response headers.

## 3. Đánh dấu operation bằng @Operation(deprecated = true)

Swagger annotations cung cấp thuộc tính deprecated cho @Operation. Đây là cách tường minh để đánh dấu một method HTTP trong tài liệu:

~~~java
@RestController
@RequestMapping("/api")
class ProductController {

    @Operation(
        operationId = "listProductsV1",
        summary = "Liệt kê sản phẩm phiên bản 1",
        description = """
            API cũ, không khuyến nghị cho tích hợp mới.
            Dùng GET /api/v2/products.
            Hướng dẫn chuyển đổi: https://docs.example.com/migrations/products-v1
            """,
        deprecated = true,
        externalDocs = @ExternalDocumentation(
            description = "Hướng dẫn chuyển từ Products API v1 sang v2",
            url = "https://docs.example.com/migrations/products-v1"
        )
    )
    @GetMapping("/v1/products")
    List<ProductResponse> listProductsV1() {
        return productService.listV1();
    }
}
~~~

Khi springdoc đọc annotation, operation tương ứng được sinh với deprecated: true. Swagger UI và các công cụ đọc OpenAPI có thể hiển thị operation này là deprecated.

Giữ operationId ổn định trong suốt vòng đời của operation cũ. Không đổi operationId theo locale hoặc đổi nó chỉ để thêm chữ deprecated; các công cụ sinh SDK có thể dùng operationId làm tên method. Phần trạng thái và hướng dẫn migration nên nằm trong deprecated, summary/description và externalDocs.

## 4. Dùng @Deprecated trong Java

Java có annotation @Deprecated để đánh dấu class, method, constructor, field hoặc API member không còn được khuyến nghị. Từ Java 9, annotation hỗ trợ hai thuộc tính:

- since: phiên bản bắt đầu deprecated.
- forRemoval: cho biết API dự kiến bị xóa trong một bản phát hành tương lai hay chỉ không còn được khuyến nghị.

Ví dụ:

~~~java
/**
 * Liệt kê sản phẩm theo hợp đồng API v1.
 *
 * @deprecated Dùng {@link #listProductsV2(ProductStatus)}.
 *             Xem hướng dẫn tại https://docs.example.com/migrations/products-v1.
 */
@Deprecated(since = "2.4", forRemoval = true)
@GetMapping("/api/v1/products")
List<ProductResponse> listProductsV1() {
    return productService.listV1();
}
~~~

Springdoc có thể nhận diện @Deprecated trên model và operation để đánh dấu phần tương ứng trong OpenAPI. Dùng @Operation(deprecated = true) khi muốn khai báo trạng thái trực tiếp trong Swagger annotation; dùng @Deprecated để đồng bộ trạng thái ở mã nguồn, compiler và tài liệu Java.

Ví dụ khai báo cả hai:

~~~java
@Deprecated(since = "2.4", forRemoval = true)
@Operation(
    operationId = "listProductsV1",
    summary = "Liệt kê sản phẩm phiên bản 1",
    deprecated = true,
    description = "Dùng GET /api/v2/products. Xem migration guide tại https://docs.example.com/migrations/products-v1."
)
@GetMapping("/api/v1/products")
List<ProductResponse> listProductsV1() {
    return productService.listV1();
}
~~~

Không coi since và forRemoval là ngày sunset. since là nhãn phiên bản trong code; forRemoval chỉ thể hiện ý định loại bỏ trong tương lai. OpenAPI deprecated vẫn là boolean và không tự chuyển hai giá trị này thành lịch ngừng hỗ trợ.

### Viết Javadoc cho API deprecated

Javadoc nên giải thích vì sao API cũ không còn được khuyến nghị, thay thế bằng gì và liên kết đến hướng dẫn migration:

~~~java
/**
 * Tìm sản phẩm bằng mã legacy.
 *
 * @deprecated Từ phiên bản 2.4, hãy dùng {@link #findByProductCode(String)}.
 *             Tham số legacyCode không còn được hỗ trợ trong API mới.
 *             Xem https://docs.example.com/migrations/product-lookup.
 */
@Deprecated(since = "2.4", forRemoval = true)
public ProductResponse findByLegacyCode(String legacyCode) {
    return repository.findByLegacyCode(legacyCode);
}
~~~

Thông điệp thay thế phải trỏ tới API thực sự tồn tại. Trước khi publish tài liệu, xác minh method hoặc endpoint thay thế đã được triển khai và được mô tả trong OpenAPI.

## 5. Cấu hình springdoc tự nhận diện @Deprecated

Springdoc có deprecating model converter để đánh dấu schema tương ứng khi model Java chứa @Deprecated. Trong cấu hình hiện hành, converter này được bật mặc định:

~~~yaml
springdoc:
  model-converters:
    deprecating-converter:
      enabled: true
~~~

Khi cần tắt cơ chế tự đánh dấu từ Java @Deprecated, property là:

~~~yaml
springdoc:
  model-converters:
    deprecating-converter:
      enabled: false
~~~

Thông thường nên giữ converter bật để code và tài liệu không lệch nhau. Chỉ tắt khi có lý do rõ ràng và đã thay thế bằng metadata khác được kiểm thử. Property này điều khiển deprecating model converter; nó không phải công tắc chung để xóa toàn bộ trạng thái deprecated mà annotation @Operation hoặc @Schema khai báo trực tiếp.

Sau khi thay đổi cấu hình, kiểm tra /v3/api-docs để xác nhận operation và schema có cờ deprecated đúng như mong đợi. Không chỉ dựa vào việc Swagger UI đổi màu hoặc gạch ngang một operation.

## 6. Đánh dấu một parameter deprecated

Một endpoint có thể vẫn được giữ nguyên nhưng một query parameter hoặc header đã có phương án thay thế. Dùng @Parameter(deprecated = true) để đánh dấu riêng parameter:

~~~java
@GetMapping("/api/v2/products")
@Operation(summary = "Tìm kiếm sản phẩm")
List<ProductResponse> searchProducts(
    @Parameter(
        name = "archived",
        description = "Đã deprecated. Dùng status=ARCHIVED hoặc status=ACTIVE.",
        deprecated = true
    )
    @RequestParam(required = false) Boolean archived,

    @Parameter(
        name = "status",
        description = "Trạng thái sản phẩm cần lọc."
    )
    @RequestParam(required = false) ProductStatus status
) {
    ProductStatus effectiveStatus = status;
    if (effectiveStatus == null && archived != null) {
        effectiveStatus = archived ? ProductStatus.ARCHIVED : ProductStatus.ACTIVE;
    }
    return productService.search(effectiveStatus);
}
~~~

Trong giai đoạn chuyển tiếp, server có thể tiếp tục nhận archived và ánh xạ sang status. Nếu cả hai parameter cùng xuất hiện, hãy định nghĩa quy tắc ưu tiên hoặc trả 400 để tránh request mơ hồ. Quy tắc này phải được mô tả trong operation description và kiểm thử.

Không đổi tên parameter trên runtime nhưng chỉ đổi tên trong OpenAPI. Ví dụ nếu server vẫn nhận archived thì tài liệu phải phản ánh archived là deprecated và status là parameter mới. Khi xóa archived, đó là thay đổi contract và cần thông báo theo lộ trình.

## 7. Đánh dấu field hoặc schema deprecated

Một property trong JSON có thể được giữ lại để tương thích nhưng không nên dùng cho client mới. Dùng @Schema(deprecated = true) trên field hoặc record component:

~~~java
@Schema(description = "Thông tin sản phẩm trong catalog")
public record ProductResponse(
    UUID id,

    @Schema(
        deprecated = true,
        description = "Mã cũ. Dùng productCode; field này sẽ được loại bỏ trong API major tiếp theo."
    )
    String legacyCode,

    @Schema(
        description = "Mã sản phẩm chính thức."
    )
    String productCode,

    String name
) {}
~~~

OpenAPI schema của legacyCode sẽ có deprecated: true. Consumer vẫn có thể đọc field này trong thời gian chuyển tiếp; server cần tiếp tục cung cấp giá trị nếu contract hiện tại còn cam kết field đó.

Nếu toàn bộ model đã deprecated, có thể dùng @Schema(deprecated = true) ở cấp class. Nếu model chỉ có một field cũ, chỉ đánh dấu field đó để không khiến consumer hiểu nhầm mọi field của model đều sắp bị loại bỏ.

Không bỏ field khỏi JSON response ngay khi thêm deprecated: true. Code generator và SDK có thể hiển thị cảnh báo cho developer, nhưng runtime contract vẫn cần giữ field trong giai đoạn hỗ trợ.

## 8. Mô tả replacement bằng description và externalDocs

OpenAPI không có thuộc tính chuẩn riêng tên replacementOperationId hoặc sunsetDate. Vì vậy, mô tả phương án thay thế bằng các trường văn bản và liên kết:

~~~java
@Operation(
    operationId = "getProductV1",
    summary = "Lấy sản phẩm (deprecated)",
    deprecated = true,
    description = """
        API này được giữ để tương thích với consumer hiện tại.

        Thay thế bằng GET /api/v2/products/{productCode}.
        Path parameter id được thay bằng productCode.
        Response field legacyCode được thay bằng productCode.

        Ngày bắt đầu deprecation: 2027-01-01.
        Ngày dự kiến ngừng phục vụ: 2027-12-31.
        """,
    externalDocs = @ExternalDocumentation(
        description = "Migration guide và bảng ánh xạ v1 sang v2",
        url = "https://docs.example.com/migrations/products-v1"
    )
)
@GetMapping("/api/v1/products/{id}")
ProductResponse getProductV1(@PathVariable UUID id) {
    return productService.getV1(id);
}
~~~

Description nên trả lời các câu hỏi thực tế:

- Vì sao operation hoặc field cũ bị deprecated?
- Endpoint, parameter hoặc schema nào thay thế?
- Request cũ được chuyển sang request mới như thế nào?
- Response mới có field hoặc semantics nào khác?
- API cũ tiếp tục hoạt động tới mốc nào?
- Consumer cần hoàn thành migration trước khi điều gì xảy ra?

Tránh ghi một câu chung chung như “Use v2 instead”. Consumer cần biết path, method, parameter, schema và cách xử lý khác biệt.

## 9. Công bố response headers cho endpoint deprecated

OpenAPI mô tả contract, còn HTTP response headers có thể thông báo trạng thái deprecation tại thời điểm consumer thực sự gọi endpoint. RFC 9745 định nghĩa header Deprecation; RFC 8594 định nghĩa header Sunset.

Ví dụ response của endpoint cũ:

~~~http
HTTP/1.1 200 OK
Deprecation: @1798761600
Sunset: Fri, 31 Dec 2027 23:59:59 GMT
Link: <https://docs.example.com/migrations/products-v1>; rel="deprecation"
Link: </api/v2/products>; rel="successor-version"
Content-Type: application/json
~~~

Ý nghĩa:

- Deprecation là Structured Field Date theo RFC 9651, có dạng @ cộng Unix timestamp tính bằng giây. Ví dụ @1798761600 tương ứng 2027-01-01T00:00:00Z.
- Sunset dùng HTTP-date theo RFC 8594. Mốc Sunset không được sớm hơn mốc Deprecation.
- Link với rel=deprecation trỏ tới tài liệu giải thích việc deprecated và hướng dẫn migration.
- Link với rel=successor-version có thể trỏ tới tài nguyên phiên bản kế tiếp trong hệ thống versioned resources.

Deprecation và Sunset không thay đổi semantics của response hiện tại. Deprecation thông báo resource đã hoặc sẽ bị deprecated; Sunset thông báo thời điểm resource dự kiến không còn phản hồi. Nếu chỉ muốn thông báo deprecated mà chưa xác định ngày ngừng, không cần tự đặt một Sunset date giả.

### Khai báo response headers trong OpenAPI

Có thể mô tả các header này bằng @ApiResponse:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Response của endpoint cũ; xem migration guide.",
    headers = {
        @Header(
            name = "Deprecation",
            description = "Structured Field Date cho biết thời điểm deprecation.",
            schema = @Schema(type = "string", example = "@1798761600")
        ),
        @Header(
            name = "Sunset",
            description = "HTTP-date dự kiến endpoint ngừng phục vụ.",
            schema = @Schema(type = "string", example = "Fri, 31 Dec 2027 23:59:59 GMT")
        ),
        @Header(
            name = "Link",
            description = "Liên kết tới migration guide và successor resource.",
            schema = @Schema(type = "string")
        )
    }
)
~~~

Nếu response thực tế không gửi một header nào đó, đừng khai báo nó như header luôn tồn tại. OpenAPI phải mô tả hành vi runtime, kể cả điều kiện header chỉ xuất hiện trên endpoint hoặc phiên bản deprecated.

## 10. Thêm deprecation headers trong Spring Boot

Với Spring MVC, có thể dùng HandlerInterceptor hoặc OncePerRequestFilter để thêm header cho các route cũ. Ví dụ filter chỉ áp dụng cho prefix /api/v1:

~~~java
@Component
class DeprecatedApiHeadersFilter extends OncePerRequestFilter {

    private static final String DEPRECATION_DATE = "@1798761600";
    private static final String SUNSET_DATE = "Fri, 31 Dec 2027 23:59:59 GMT";

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith(
            request.getContextPath() + "/api/v1/"
        );
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        response.setHeader("Deprecation", DEPRECATION_DATE);
        response.setHeader("Sunset", SUNSET_DATE);
        response.addHeader(
            "Link",
            "<https://docs.example.com/migrations/products-v1>; rel=\"deprecation\""
        );
        response.addHeader(
            "Link",
            "</api/v2/products>; rel=\"successor-version\""
        );
        filterChain.doFilter(request, response);
    }
}
~~~

Filter cần được giới hạn đúng path và đúng thời gian. Nếu chỉ một vài operation deprecated trong /api/v1, hãy dùng danh sách route cụ thể hoặc metadata riêng thay vì gắn header cho toàn bộ prefix.

Với Spring WebFlux, dùng WebFilter hoặc filter function tương ứng; không dùng OncePerRequestFilter vì đây là Servlet API. Với gateway, có thể thêm headers tại gateway nếu gateway nắm chính xác route và lifecycle policy.

Nếu API được gọi từ browser khác origin, kiểm tra CORS expose headers. Browser JavaScript không đọc được custom response headers nếu Access-Control-Expose-Headers không công bố chúng.

## 11. Link tới migration guide và API thay thế

Một migration guide nên là tài liệu ổn định, có URL công khai và được version hóa. Có thể liên kết từ:

- OpenAPI Operation bằng externalDocs.
- Deprecation response header bằng Link rel=deprecation.
- Successor resource bằng Link rel=successor-version khi phù hợp với mô hình version history.
- Trang API portal hoặc changelog.

Ví dụ Link headers:

~~~http
Link: <https://docs.example.com/migrations/products-v1>; rel="deprecation"
Link: </api/v2/products>; rel="successor-version"
Link: </api/version-history/products>; rel="version-history"
~~~

Link relation deprecation được RFC 9745 đăng ký để trỏ tới tài liệu dành cho con người về việc deprecated. Relation successor-version và version-history được định nghĩa trong RFC 5829 cho điều hướng tài nguyên có version. Nếu đường dẫn thay thế không phải tài nguyên versioned theo nghĩa đó, hãy ghi replacement URL trong migration guide hoặc một extension được tổ chức quy ước thay vì gán sai semantics cho link relation.

Không trỏ replacement link tới endpoint chưa được phát hành, yêu cầu quyền truy cập khác mà consumer không thể dùng, hoặc một tài liệu chỉ tồn tại trong môi trường nội bộ.

## 12. Xây dựng lộ trình thay thế theo từng giai đoạn

Không nên đánh dấu deprecated và xóa endpoint trong cùng một release nếu consumer cần thời gian thay đổi. Một lộ trình có thể chia thành các giai đoạn:

| Giai đoạn | Hành động của provider | Kỳ vọng với consumer |
|---|---|---|
| 1. Chuẩn bị replacement | Xây API mới, schema mới, migration guide và contract tests | Chưa cần thay đổi ngay |
| 2. Công bố API mới | Phát hành endpoint mới và tài liệu OpenAPI | Có thể tích hợp mới bằng API mới |
| 3. Đánh dấu API cũ deprecated | Cập nhật OpenAPI, Java annotations, response headers và changelog | Lập kế hoạch migration |
| 4. Chuyển tiếp | Duy trì API cũ, theo dõi mức sử dụng, hỗ trợ consumer | Chuyển dần sang API mới |
| 5. Sunset | Gửi thông báo cuối, công bố ngày ngừng và xử lý hỗ trợ còn lại | Hoàn tất migration |
| 6. Ngừng phục vụ | Trả trạng thái đã thống nhất, ví dụ 410 Gone, hoặc gỡ route theo policy | Không còn gọi API cũ |

Thời lượng từng giai đoạn phụ thuộc số lượng consumer, mức độ thay đổi và hợp đồng hỗ trợ. Không có một thời gian chờ chung phù hợp cho mọi API. API public có nhiều đối tác cần thời gian dài hơn một API nội bộ do một nhóm kiểm soát.

### Giai đoạn 1: chuẩn bị replacement

Trước khi thông báo deprecation, cần có API thay thế hoạt động trong môi trường có thể kiểm thử. Kiểm tra rằng replacement:

- Bao phủ use case chính của API cũ.
- Có schema, security scheme, scope và error response rõ ràng.
- Có tài liệu request/response và ví dụ.
- Có khả năng chạy song song với API cũ trong giai đoạn chuyển tiếp.
- Có migration guide mô tả phần tương đương và phần thay đổi.

Không công bố ngày sunset khi replacement chưa sẵn sàng hoặc chưa có kế hoạch khả thi để consumer chuyển đổi.

### Giai đoạn 2: phát hành replacement trước

Cho consumer dùng thử API mới trước khi đánh dấu API cũ deprecated. Điều này giúp phát hiện khác biệt contract, lỗi phân quyền, giới hạn tốc độ hoặc thiếu tính năng khi vẫn còn thời gian điều chỉnh.

### Giai đoạn 3: đánh dấu và thông báo

Trong cùng một release, đồng bộ:

- OpenAPI document: deprecated: true và mô tả replacement.
- Java source: @Deprecated(since = ..., forRemoval = ...).
- Runtime: Deprecation và Link headers; thêm Sunset khi đã công bố ngày ngừng.
- Release notes/changelog: nêu endpoint và consumer bị ảnh hưởng.
- Migration guide: ví dụ request cũ và request mới.

### Giai đoạn 4: theo dõi mức sử dụng

Theo dõi số request tới endpoint cũ theo client/application identifier đã được kiểm soát. Dùng số liệu tổng hợp để biết consumer nào còn phụ thuộc, nhưng không ghi token, request body nhạy cảm hoặc dữ liệu cá nhân không cần thiết vào log chỉ để phục vụ deprecation.

Thông báo trực tiếp tới owner của consumer đã đăng ký nếu chính sách tích hợp cho phép. Tài liệu và header là tín hiệu cho client; chúng không thay thế việc phối hợp với các đối tác có SLA.

### Giai đoạn 5 và 6: sunset rồi ngừng phục vụ

Trước ngày sunset, gửi thông báo cuối và xác minh consumer quan trọng đã chuyển đổi. Khi tới thời điểm ngừng:

- Thực hiện đúng policy đã công bố.
- Nếu muốn giữ một endpoint tombstone để trả lời rõ ràng, có thể trả 410 Gone cùng liên kết migration guide.
- Không trả dữ liệu nghiệp vụ cũ với semantics khác mà không thông báo.
- Gỡ code, test, route và metadata deprecated khi đã hoàn tất removal.

Trạng thái 410 Gone chỉ là một lựa chọn khi resource đã bị loại bỏ vĩnh viễn. Nếu endpoint được chuyển hướng sang API mới, hãy cân nhắc method, body, authentication và semantics trước khi dùng 301/308; redirect không phải lúc nào cũng an toàn hoặc tương đương cho mọi HTTP method.

## 13. Migration guide cần có bảng ánh xạ cụ thể

Một hướng dẫn thay thế nên giúp consumer chuyển request và response mà không phải suy đoán. Ví dụ API v1 dùng cờ archived dạng boolean, còn API v2 dùng status enum:

| Thành phần | API v1 (deprecated) | API v2 (replacement) |
|---|---|---|
| Endpoint | GET /api/v1/products | GET /api/v2/products |
| Filter sản phẩm lưu trữ | archived=true | status=ARCHIVED |
| Filter sản phẩm đang hoạt động | archived=false | status=ACTIVE |
| Không lọc trạng thái | Bỏ archived | Bỏ status hoặc status=ALL theo contract |
| Mã sản phẩm trong response | legacyCode | productCode |
| Pagination | page, size | page, size |
| Authentication | Bearer token | Cùng scheme nếu policy không đổi |

Ví dụ request cũ:

~~~http
GET /api/v1/products?archived=true&page=0&size=20
Accept: application/json
~~~

Request mới:

~~~http
GET /api/v2/products?status=ARCHIVED&page=0&size=20
Accept: application/json
~~~

Ví dụ response cũ:

~~~json
{
  "items": [
    {
      "id": "p-101",
      "legacyCode": "OLD-101",
      "name": "Bút bi"
    }
  ]
}
~~~

Response mới:

~~~json
{
  "items": [
    {
      "id": "p-101",
      "productCode": "OLD-101",
      "name": "Bút bi"
    }
  ]
}
~~~

Migration guide cần giải thích thêm:

- Có thay đổi thứ tự sắp xếp, pagination hoặc default filter không?
- Có thay đổi nullability, format ngày giờ hoặc enum value không?
- API mới có yêu cầu OAuth scope hoặc role khác không?
- Error code nào thay đổi?
- Có giới hạn rate limit, timeout hoặc payload khác không?
- Consumer có cần thay đổi generated SDK hay cấu hình retry không?

Không chỉ đổi URL trong hướng dẫn. Một endpoint mới có thể có semantics khác dù schema nhìn gần giống; cần nêu rõ mọi khác biệt ảnh hưởng tới logic client.

## 14. Mô tả cả operation cũ và operation thay thế trong OpenAPI

Trong thời gian chuyển tiếp, OpenAPI document có thể chứa cả operation cũ và mới. Operation cũ có deprecated: true cùng description trỏ tới replacement; operation mới có mô tả chính thức và không có cờ deprecated.

Ví dụ:

~~~java
@RestController
class ProductApiController {

    @Deprecated(since = "2.4", forRemoval = true)
    @Operation(
        operationId = "searchProductsV1",
        summary = "Tìm sản phẩm bằng API v1",
        description = "Deprecated từ phiên bản 2.4. Dùng GET /api/v2/products với query parameter status. Migration guide: https://docs.example.com/migrations/products-v1.",
        deprecated = true,
        externalDocs = @ExternalDocumentation(
            description = "Migration guide Products API v1",
            url = "https://docs.example.com/migrations/products-v1"
        )
    )
    @GetMapping("/api/v1/products")
    ProductPage searchV1(
        @RequestParam(required = false) Boolean archived
    ) {
        return productService.searchV1(archived);
    }

    @Operation(
        operationId = "searchProductsV2",
        summary = "Tìm sản phẩm bằng API v2",
        description = "Lọc sản phẩm bằng status: ACTIVE, ARCHIVED hoặc ALL."
    )
    @GetMapping("/api/v2/products")
    ProductPage searchV2(
        @RequestParam(required = false) ProductStatus status
    ) {
        return productService.searchV2(status);
    }
}
~~~

Trong OpenAPI, consumer có thể nhìn thấy hai operation cạnh nhau và chọn operation mới. Không ẩn operation cũ khi nó vẫn còn được hỗ trợ; ẩn sẽ làm mất tín hiệu rằng endpoint đó vẫn tồn tại nhưng đang trong giai đoạn chuyển tiếp.

Nếu API v1 và v2 được chia thành hai OpenAPI group riêng, hãy đảm bảo group v1 vẫn công bố cờ deprecated và group v2 có replacement operation. Có thể thêm externalDocs ở cấp operation hoặc tag để trỏ tới hướng dẫn chung.

## 15. Kiểm thử hành vi tương thích trong thời gian chuyển tiếp

Khi endpoint cũ vẫn được hỗ trợ, cần test rằng nó tiếp tục đáp ứng contract đã công bố:

- Path, method và authentication vẫn hoạt động.
- Request cũ vẫn được parse theo schema cũ.
- Response cũ vẫn chứa các field đã cam kết.
- Parameter deprecated vẫn hoạt động nếu policy nói nó còn được hỗ trợ.
- Header deprecation được gửi đúng.
- API mới hoạt động độc lập và có schema mới.
- Mapping từ request cũ sang nghiệp vụ mới không làm thay đổi semantics ngoài những khác biệt đã công bố.

Nếu hai endpoint dùng chung service, hãy test cả hai adapter để tránh việc sửa logic v2 vô tình làm thay đổi v1. Contract test nên lưu các ví dụ request/response đại diện cho consumer thực tế.

## 16. Kiểm thử cờ deprecated trong OpenAPI document

Không chỉ test endpoint trả response đúng. Cần kiểm tra OpenAPI JSON có cờ deprecated và thông tin replacement:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductOpenApiDeprecationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void marksLegacyOperationAsDeprecated() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/v1/products'].get.deprecated"
            ).value(true))
            .andExpect(jsonPath(
                "$.paths['/api/v1/products'].get.externalDocs.url"
            ).value("https://docs.example.com/migrations/products-v1"))
            .andExpect(jsonPath(
                "$.paths['/api/v2/products'].get.deprecated"
            ).doesNotExist());
    }
}
~~~

Kiểm tra parameter:

~~~java
@Test
void marksLegacyParameterAsDeprecated() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.paths['/api/v2/products'].get.parameters[?(@.name=='archived')].deprecated[0]"
        ).value(true));
}
~~~

Kiểm tra schema property:

~~~java
@Test
void marksLegacySchemaPropertyAsDeprecated() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.components.schemas.ProductResponse.properties.legacyCode.deprecated"
        ).value(true));
}
~~~

JSONPath expression có hỗ trợ filter phụ thuộc implementation đang dùng. Nếu matcher không hỗ trợ cú pháp filter, parse JSON document thành object và tìm parameter theo name. Mục tiêu là xác nhận cờ deprecated đúng vị trí, không phụ thuộc thứ tự parameter.

## 17. Kiểm thử deprecation headers ở runtime

Khi API cũ gửi Deprecation, Sunset và Link headers, nên có test để đảm bảo header thực sự được phát ra trên response. Ví dụ MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class DeprecatedProductApiTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void legacyEndpointPublishesDeprecationInformation() throws Exception {
        mockMvc.perform(get("/api/v1/products")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(header().string("Deprecation", "@1798761600"))
            .andExpect(header().string(
                "Sunset",
                "Fri, 31 Dec 2027 23:59:59 GMT"
            ))
            .andExpect(header().string(
                "Link",
                org.hamcrest.Matchers.containsString("rel=\"deprecation\"")
            ));
    }
}
~~~

Nếu response có nhiều Link headers, framework hoặc test matcher có thể gộp hoặc trả nhiều giá trị. Khi đó, đọc danh sách header và xác nhận từng relation thay vì so sánh cả chuỗi theo thứ tự cố định.

Test này kiểm tra ví dụ ngày cụ thể. Trong ứng dụng thật, nên đặt deprecation date và sunset date trong cấu hình tập trung hoặc policy object để tránh filter, OpenAPI description và release note dùng các mốc khác nhau. Không lấy thời gian hiện tại trong mỗi request để tạo giá trị header thay đổi liên tục.

Nếu API được gọi từ browser khác origin, kiểm tra CORS expose headers. Browser JavaScript không đọc được custom response headers nếu Access-Control-Expose-Headers không công bố chúng.

## 18. Quy tắc versioning và thời điểm loại bỏ

Deprecation policy nên nêu rõ:

1. Cách xác định API version: path, media type, header hay version trong schema.
2. Cách thông báo deprecation: OpenAPI, HTTP headers, release notes và kênh hỗ trợ.
3. Thời gian hỗ trợ tối thiểu theo loại API.
4. Cách thông báo thay đổi ngày sunset.
5. Trạng thái HTTP sau khi endpoint ngừng phục vụ.
6. Cách xử lý consumer có SLA hoặc hợp đồng hỗ trợ riêng.

Một số nguyên tắc:

- Thêm deprecated: true thường không đổi wire contract, nhưng là tín hiệu lifecycle mà consumer và tooling có thể xử lý.
- Xóa operation, parameter bắt buộc hoặc response field mà consumer phụ thuộc có thể là breaking change.
- Đổi semantics của field mà không đổi schema cũng có thể là breaking change.
- Thêm endpoint thay thế không tự làm API cũ tương thích ngược với API mới.
- Xóa API cũ nên tuân theo versioning policy và mốc đã công bố.

Nếu dùng semantic versioning cho API contract, việc loại bỏ một operation đã công bố thường cần một major version hoặc một phiên bản API mới theo chính sách. Với path versioning, có thể giữ /api/v1 trong thời gian chuyển tiếp và công bố /api/v2. Không giả định mọi tổ chức đều phải dùng cùng một cách đánh version; điều quan trọng là consumer biết contract nào được hỗ trợ và tới khi nào.

## 19. Dùng HTTP 410 Gone sau khi ngừng phục vụ

Khi endpoint đã bị ngừng vĩnh viễn, có thể trả 410 Gone để nói rõ resource đã bị loại bỏ. Ví dụ:

~~~java
@RestControllerAdvice
class RemovedApiExceptionHandler {

    @ExceptionHandler(RemovedApiException.class)
    ResponseEntity<ProblemDetail> handleRemovedApi(RemovedApiException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.GONE);
        problem.setTitle("API đã ngừng phục vụ");
        problem.setDetail(
            "Dùng GET /api/v2/products. Hướng dẫn: https://docs.example.com/migrations/products-v1"
        );
        problem.setType(URI.create(
            "https://docs.example.com/problems/deprecated-api-removed"
        ));

        return ResponseEntity.status(HttpStatus.GONE)
            .header(
                HttpHeaders.LINK,
                "<https://docs.example.com/migrations/products-v1>; rel=\"deprecation\""
            )
            .body(problem);
    }
}
~~~

Đây là ví dụ về response sau khi route cũ đã được chuyển sang cơ chế tombstone hoặc exception handler. Nó không tự thay thế việc xóa mapping và cần được tích hợp với routing thực tế của ứng dụng.

410 Gone phù hợp khi provider biết resource đã bị loại bỏ và không có ý định khôi phục. Nếu endpoint chỉ tạm thời không sẵn sàng, dùng status khác theo đúng semantics thay vì trả 410. Nếu route không còn tồn tại và server trả 404, consumer sẽ khó phân biệt resource chưa từng có với resource đã bị ngừng.

## 20. Lỗi thường gặp khi đánh dấu deprecated

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Swagger UI không hiển thị operation là deprecated | Annotation không được springdoc đọc hoặc cờ chưa bật | Dùng @Operation(deprecated = true), kiểm tra /v3/api-docs |
| Java method deprecated nhưng schema không đổi | Model converter bị tắt hoặc annotation đặt sai member | Kiểm tra @Deprecated và springdoc.model-converters.deprecating-converter.enabled |
| Chỉ description nói deprecated nhưng OpenAPI không có cờ | Quên deprecated = true | Đánh dấu cờ tường minh trên Operation, Parameter hoặc Schema |
| API cũ biến mất ngay sau khi đánh dấu | Dùng @Hidden hoặc xóa route cùng lúc | Giữ endpoint hoạt động trong giai đoạn chuyển tiếp |
| Consumer không biết dùng endpoint nào | Description chỉ nói “use v2” | Ghi path, method, parameter, schema và migration guide |
| Replacement chưa hoạt động | Công bố deprecation trước khi phát hành API mới | Chuẩn bị và kiểm thử replacement trước |
| Deprecation header có format sai | Dùng HTTP-date cho Deprecation | Dùng Structured Field Date dạng @UnixTimestamp theo RFC 9745 |
| Sunset sớm hơn Deprecation | Cấu hình mốc thời gian không nhất quán | Đảm bảo Sunset không sớm hơn ngày Deprecation |
| Response có header nhưng OpenAPI không mô tả | Thiếu @ApiResponse(headers = ...) | Bổ sung header metadata và kiểm thử document |
| Swagger UI hiển thị replacement nhưng runtime trả 404 | OpenAPI annotation không khớp route thực tế | Kiểm thử HTTP mapping và document cùng nhau |
| Xóa field cũ làm SDK consumer lỗi | Không có thời gian chuyển tiếp hoặc đánh giá breaking change | Giữ field cũ, thêm field mới, theo dõi usage rồi mới loại bỏ |
| Browser không đọc được Deprecation header | CORS không expose response header | Thêm Deprecation, Sunset và Link vào Access-Control-Expose-Headers |
| Link replacement trỏ sai môi trường | Hard-code host nội bộ hoặc URL staging | Dùng URL công khai theo môi trường và kiểm tra trước khi phát hành |

## 21. Checklist trước khi công bố deprecation

Trước khi merge thay đổi, xác nhận:

1. API thay thế đã tồn tại và được kiểm thử.
2. Lý do deprecation được giải thích rõ.
3. Operation, parameter hoặc schema đúng phạm vi được đánh dấu deprecated.
4. operationId, path và tên JSON property vẫn ổn định trong giai đoạn chuyển tiếp.
5. Description chỉ rõ replacement path, method và parameter.
6. External documentation hoặc migration guide có thể truy cập.
7. Deprecation date và sunset date nhất quán với policy.
8. Runtime response headers đúng định dạng RFC.
9. OpenAPI document có deprecated: true tại đúng operation/parameter/schema.
10. API cũ vẫn hoạt động trong khoảng hỗ trợ đã công bố.
11. Contract tests kiểm tra cả API cũ và API mới.
12. Consumer owners được thông báo qua kênh đã thống nhất.
13. Usage telemetry đủ để đánh giá migration progress.
14. CI kiểm tra thay đổi contract và ngăn việc xóa API cũ trước mốc cho phép.

## 22. Quy trình thực hiện trong một Spring Boot project

1. Kiểm kê endpoint, parameter, schema property và consumer đang sử dụng phần dự kiến thay thế.
2. Thiết kế endpoint hoặc field mới; kiểm tra schema, security, error response và semantics.
3. Viết migration guide với bảng ánh xạ và request/response trước-sau.
4. Phát hành replacement và xác minh qua integration/contract tests.
5. Đánh dấu Java member bằng @Deprecated(since, forRemoval) khi phù hợp.
6. Đánh dấu OpenAPI bằng @Operation(deprecated = true), @Parameter(deprecated = true) hoặc @Schema(deprecated = true).
7. Bổ sung description, externalDocs và response headers theo chính sách.
8. Gửi Deprecation và Link headers; chỉ gửi Sunset khi đã công bố ngày ngừng.
9. Theo dõi usage và hỗ trợ consumer chuyển đổi.
10. Kiểm tra mốc sunset và thông báo cuối.
11. Ngừng route hoặc field theo versioning policy; cân nhắc 410 Gone cho resource đã bị loại bỏ.
12. Xóa metadata deprecated khi API cũ đã thực sự được loại bỏ và cập nhật tài liệu lịch sử.

Đánh dấu deprecated giúp provider và consumer nhận biết một thành phần đang đi tới cuối vòng đời. Giá trị lớn nhất đến từ thông tin thay thế có thể hành động: endpoint mới, mapping dữ liệu, mốc thời gian, tài liệu và tín hiệu runtime. Khi những phần này đồng bộ giữa Java, OpenAPI, HTTP response và CI, consumer có thể chuyển đổi có kế hoạch và provider giảm rủi ro khi ngừng hỗ trợ API cũ.

## 23. Tài liệu tham khảo

- [Springdoc OpenAPI FAQ](https://springdoc.org/faq.html): cách springdoc xử lý @Deprecated và cấu hình deprecating model converter.
- [Springdoc OpenAPI Core Properties](https://springdoc.org/core-properties.html): springdoc.model-converters.deprecating-converter.enabled.
- [Swagger Core – Operation annotation](https://docs.swagger.io/swagger-core/v2.2.34/apidocs/io/swagger/v3/oas/annotations/Operation.html): thuộc tính deprecated của @Operation.
- [Swagger Core – Schema annotation](https://github.com/swagger-api/swagger-core/blob/master/modules/swagger-annotations/src/main/java/io/swagger/v3/oas/annotations/media/Schema.java): metadata schema, bao gồm trạng thái deprecated.
- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object): thuộc tính deprecated của operation.
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object): thuộc tính deprecated của parameter.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): từ khóa deprecated trong schema.
- [Oracle Java – How to Deprecate APIs](https://docs.oracle.com/en/java/javase/21/core/how-deprecate-apis.html): @Deprecated, since, forRemoval và Javadoc @deprecated.
- [RFC 9745 – The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745.html): Deprecation header và Link relation deprecation.
- [RFC 8594 – The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594.html): thông báo thời điểm resource dự kiến không còn hoạt động.
- [RFC 5829 – Link Relation Types for Version Navigation](https://www.rfc-editor.org/rfc/rfc5829.html): successor-version và version-history.
- [IANA Link Relation Types](https://www.iana.org/assignments/link-relations): registry chính thức của các Link relation.
