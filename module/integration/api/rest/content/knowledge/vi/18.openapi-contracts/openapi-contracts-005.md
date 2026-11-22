# responses, response headers và nhiều media type

## 1. Vì sao response là một phần quan trọng của hợp đồng?

Client không chỉ cần biết **URI, HTTP method, query parameter và request body**. Client còn cần biết **mã HTTP**, **response headers**, **body schema** và **media type** sẽ nhận. Nếu API chỉ nói “trả JSON”, client khó xử lý trường hợp tài nguyên chưa đổi, lỗi xác thực, tải CSV hoặc thao tác không trả body.

Ví dụ cùng collection sản phẩm:

~~~http
GET /api/v1/products?page=0&size=2 HTTP/1.1
Accept: application/json
~~~

~~~http
GET /api/v1/products?page=0&size=2 HTTP/1.1
Accept: text/csv
~~~

Cả hai có thể nhận **200 OK** với representation khác nhau. Một GET có **If-None-Match** hợp lệ có thể nhận **304 Not Modified** không body. Nếu client chỉ chấp nhận định dạng không hỗ trợ, server có thể trả **406 Not Acceptable**.

Bài thuộc chương **Hợp đồng OpenAPI** trong module **INTEGRATION_API_REST**: thiết kế resource/URI, phương thức và mã HTTP, hợp đồng dữ liệu, cache, phân quyền, lỗi và kiểm thử với Java/Spring. Trọng tâm là **OpenAPI 3.1**, nơi một response được diễn đạt bằng **responses → status → description/headers/content**.

Sau bài, bạn có thể: khai báo đúng nhiều nhánh response; mô tả response header; đặt nhiều media type trong **content** của một status; phân biệt **Accept** với **Content-Type**; xử lý **201, 204, 304, 400, 406, 415**; triển khai Spring và viết contract tests. Dữ liệu sản phẩm và giá VND trong bài là giả định.

## 2. Responses Object và Response Object

Một operation có ánh xạ **responses**, từ mã trạng thái tới **Response Object**:

~~~yaml
paths:
  /api/v1/products:
    get:
      responses:
        '200':
          description: Trang sản phẩm được trả thành công
          headers:
            X-Total-Count:
              description: Tổng số phần tử khớp điều kiện
              schema: { type: integer, minimum: 0 }
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductPage'
        '400':
          description: Tham số truy vấn không hợp lệ
        '406':
          description: Không có representation được hỗ trợ
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| **responses** | Các trạng thái mà operation công bố. |
| **'200'**, **'400'** | Mã HTTP cụ thể, viết dưới dạng key chuỗi YAML. |
| **description** | Thuộc tính **bắt buộc** của Response Object. |
| **headers** | Ánh xạ tên response header tới Header Object hoặc Reference Object. |
| **content** | Ánh xạ media type sang Media Type Object với schema, example(s), encoding khi phù hợp. |
| **links** | OpenAPI Link Object định nghĩa quan hệ giữa operations; **khác** HTTP header **Link**. |

Có thể dùng **default** cho status chưa liệt kê hoặc patterned response key như **'4XX'**. Khi một mã status cụ thể và pattern cùng khớp, response cụ thể có ưu tiên. Với API công khai, nên ghi rõ những mã buộc client có hành vi khác, thay vì thay toàn bộ 4xx/5xx bằng một lỗi chung.

**Response Object không tự sinh HTTP header hoặc body.** OpenAPI là hợp đồng; implementation và kiểm thử phải làm cho runtime khớp mô tả.

## 3. Chọn HTTP status trước body và header

| Tình huống | Mã HTTP | Có body? | Header đáng chú ý |
| --- | --- | --- | --- |
| GET collection thành công | **200 OK** | JSON hoặc CSV | Content-Type, ETag, Vary, X-Total-Count |
| GET validator khớp | **304 Not Modified** | **Không** | ETag, Cache-Control, Vary |
| GET chỉ Accept media type không hỗ trợ | **406 Not Acceptable** | Theo contract | Có thể không body |
| Page/size không hợp lệ | **400 Bad Request** | Problem Details | Content-Type |
| POST tạo resource xong | **201 Created** | Có thể JSON | Location |
| POST nhận tác vụ chưa hoàn tất | **202 Accepted** | Có thể operation status | Location của operation |
| DELETE thành công | **204 No Content** | **Không** | Không có body |
| POST Content-Type không hỗ trợ | **415 Unsupported Media Type** | Lỗi tùy contract | Content-Type |
| Xung đột nghiệp vụ | **409 Conflict** | Problem Details | Content-Type |
| Chưa xác thực | **401 Unauthorized** | Lỗi tùy scheme | WWW-Authenticate |
| Quá giới hạn gọi | **429 Too Many Requests** | Theo contract | Retry-After nếu có |

**204 và 304 không mang message body** nên thường không khai báo **content**. GET collection lọc hợp lệ nhưng rỗng thường vẫn là **200 với items=[]**, không phải 404. **206 Partial Content** gắn với HTTP Range, không phải mặc định của page/size.

## 4. Một 200 có thể có JSON và CSV

### JSON cho ứng dụng

~~~http
GET /api/v1/products?page=0&size=2 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=30
Vary: Accept
ETag: "products-json-3fda"
X-Total-Count: 34
Link: </api/v1/products?page=1&size=2>; rel="next"

{
  "items": [
    {"id":"prod-101","sku":"BOOK-42","priceVnd":120000,"status":"ACTIVE"},
    {"id":"prod-102","sku":"BOOK-43","priceVnd":150000,"status":"ACTIVE"}
  ],
  "page": 0,
  "size": 2,
  "totalItems": 34
}
~~~

### CSV cho công cụ phân tích

~~~http
GET /api/v1/products?page=0&size=2 HTTP/1.1
Accept: text/csv
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: text/csv; charset=UTF-8
Content-Disposition: attachment; filename="products.csv"
Cache-Control: public, max-age=30
Vary: Accept
ETag: "products-csv-7ab2"
X-Total-Count: 34

id,sku,priceVnd,status
prod-101,BOOK-42,120000,ACTIVE
prod-102,BOOK-43,150000,ACTIVE
~~~

Hai response biểu diễn cùng dữ liệu trang đầu nhưng CSV không mang object metadata trong body. **X-Total-Count** bù thông tin tổng số, còn URI và Link có thể mô tả trang kế. **Vary: Accept** cho cache biết định dạng phụ thuộc Accept; strong ETag phải dựa trên đúng bytes của từng representation, không dùng chung cho JSON và CSV có bytes khác nhau.

## 5. Header Object: mô tả header đúng vị trí

Trong OpenAPI, **headers** là map tên header → Header Object:

~~~yaml
'200':
  description: Trang sản phẩm
  headers:
    ETag:
      description: Validator của representation
      schema: { type: string }
      example: '"products-json-3fda"'
    Cache-Control:
      schema: { type: string }
      example: public, max-age=30
    Vary:
      schema: { type: string }
      example: Accept
    X-Total-Count:
      description: Tổng phần tử sau lọc
      schema: { type: integer, minimum: 0 }
      example: 34
    Link:
      schema: { type: string }
      example: '</api/v1/products?page=1&size=2>; rel="next"'
~~~

Header Object hỗ trợ **description, required, deprecated, schema, example/examples** và một số thuộc tính serialization. **Không khai báo name hoặc in: header** trong Header Object vì tên đã nằm ở key của map. Tên HTTP header không phân biệt hoa thường. Với **schema: integer** cho X-Total-Count, client vẫn nhận một giá trị header dạng chữ số và phải parse.

| Header | Ý nghĩa |
| --- | --- |
| **Location** | URI tài nguyên mới khi 201 hoặc operation URI khi 202 theo contract. |
| **ETag** | Validator của đúng representation, dùng trong conditional GET. |
| **Cache-Control** | Điều khiển lưu và freshness, tùy chính sách dữ liệu. |
| **Vary** | Header request ảnh hưởng lựa chọn representation. |
| **Link** | Next/previous; khác thuộc tính **links** của OpenAPI. |
| **Content-Disposition** | Gợi ý tải và filename; phải kiểm soát dữ liệu đầu vào. |
| **Retry-After** | Thời gian chờ khi 429/503 và tình huống phù hợp. |
| **WWW-Authenticate** | Challenge theo scheme khi 401. |
| **Allow** | Phương thức được phép ở 405. |

**Content-Type là ngoại lệ quan trọng:** định nghĩa Header Object tên **Content-Type** dưới **responses.*.headers** sẽ **bị bỏ qua** theo OpenAPI. Định nghĩa media type trong **content**, còn runtime vẫn cần gửi Content-Type chính xác.

**required: true** chỉ nên dùng khi header luôn được gửi theo contract nhánh đó. Ví dụ Location có thể được cam kết ở 201, nhưng Link trang kế có thể không tồn tại ở trang cuối.

## 6. Một status có nhiều media type

Đúng:

~~~yaml
responses:
  '200':
    description: Trang sản phẩm theo representation
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ProductPage'
      text/csv:
        schema: { type: string }
        example: |
          id,sku,priceVnd,status
          prod-101,BOOK-42,120000,ACTIVE
~~~

**Sai** là khai báo hai key **'200'** ở cùng cấp rồi mong YAML giữ cả hai. Một map có key trùng có thể bị công cụ ghi đè và làm mất một nhánh. Media Type Object hỗ trợ **schema, example/examples, encoding** khi phù hợp.

- **application/json** dùng Schema Object cho JSON object/array.
- **text/csv** thường mô tả là string; prose xác định delimiter, UTF-8, header row, quote và newline.
- **application/pdf** là representation nhị phân; với OAS 3.1 có thể mô tả bằng schema và contentMediaType thích hợp, phụ thuộc tooling.
- **application/problem+json** dùng cho lỗi có cấu trúc theo Problem Details.

Dùng media type cụ thể giúp sinh client và test ít nhập nhằng. **OpenAPI không tự tạo CSV/PDF** từ JSON: backend phải serialize thật và trả đúng bytes.

## 7. Accept khác request Content-Type: 406 khác 415

**Accept** của request nói client muốn nhận representation nào:

~~~http
Accept: text/csv;q=0.9, application/json;q=0.7
~~~

Khi client không gửi Accept hoặc gửi **Accept: */***, server có thể chọn định dạng mặc định (ví dụ JSON), nhưng phải công bố và kiểm thử. Thứ tự trong OpenAPI **content** không phải thuật toán chọn định dạng.

**Content-Type của request** nói body client gửi là gì:

~~~http
POST /api/v1/products HTTP/1.1
Content-Type: application/json
Accept: application/json

{"sku":"BOOK-44","priceVnd":180000,"status":"ACTIVE"}
~~~

| Trường hợp | Kết quả |
| --- | --- |
| GET Accept: text/csv | 200 với text/csv nếu hỗ trợ |
| GET chỉ Accept: application/xml, API chỉ có JSON/CSV | **406** nếu strict negotiation |
| POST chỉ nhận JSON nhưng Content-Type: text/plain | **415 Unsupported Media Type** |
| POST JSON đúng media type nhưng nội dung sai | 400/validation error theo contract |
| Accept nhiều loại và q-value | Chọn loại hỗ trợ theo ưu tiên và chính sách |

Không mô tả **Accept, Content-Type, Authorization** như header parameter thường trong OpenAPI. Dùng **responses.content**, **requestBody.content** và **securitySchemes**. Lỗi khi client chỉ Accept CSV nhưng request sai cũng cần chính sách response media type rõ, vì không phải client nào cũng parse được Problem Details JSON.

## 8. Phản hồi không có body: 204 và 304

**204 No Content** và **304 Not Modified** không mang body. OpenAPI chỉ cần description và headers:

~~~yaml
'204':
  description: Xóa thành công, không có body

'304':
  description: Representation chưa thay đổi
  headers:
    ETag:
      schema: { type: string }
    Cache-Control:
      schema: { type: string }
    Vary:
      schema: { type: string }
~~~

Không đưa **content: application/json** hoặc object rỗng vào 204/304. Ví dụ conditional GET:

~~~http
GET /api/v1/products?page=0&size=2 HTTP/1.1
Accept: application/json
If-None-Match: "products-json-3fda"
~~~

~~~http
HTTP/1.1 304 Not Modified
ETag: "products-json-3fda"
Cache-Control: public, max-age=30
Vary: Accept
~~~

Cache/client dùng representation đã lưu theo cơ chế HTTP caching. **ETag không quyết định TTL**, mà hỗ trợ revalidation. ETag phải phản ánh đúng variant, page/filter và quyền khi chúng thay đổi bytes.

**201 Created** có thể có body và Location:

~~~yaml
'201':
  description: Đã tạo sản phẩm
  headers:
    Location:
      required: true
      schema: { type: string, format: uri-reference }
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/Product'
~~~

HTTP không bắt buộc mọi 201 có JSON body, nhưng contract này cam kết. **202 Accepted** chỉ là đã nhận xử lý, chưa có kết quả cuối; Location có thể trỏ đến operation/status resource.

## 9. Body lỗi cần schema riêng

Một response lỗi nên có media type **application/problem+json** theo RFC 9457, thay vì mượn schema sản phẩm thành công:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/invalid-query",
  "title": "Invalid query",
  "status": 400,
  "detail": "size phải nằm trong khoảng 1..100",
  "invalidParams": [
    {"name":"size","reason":"Giá trị 200 vượt giới hạn"}
  ]
}
~~~

**invalidParams** là extension do API định nghĩa, không phải trường bắt buộc của RFC. Một schema đơn giản:

~~~yaml
Problem:
  type: object
  properties:
    type: { type: string, format: uri-reference }
    title: { type: string }
    status: { type: integer }
    detail: { type: string }
    invalidParams:
      type: array
      items:
        type: object
        properties:
          name: { type: string }
          reason: { type: string }
~~~

Có thể đặt response lỗi dùng chung trong **components.responses** rồi tham chiếu với **$ref**, nhưng **401/403/409/429** vẫn cần mô tả ngữ nghĩa riêng. 401 cần challenge thích hợp qua **WWW-Authenticate**, 429 có thể kèm **Retry-After**. Không đưa SQL, stack trace, token hoặc thông tin nội bộ vào error body.

## 10. OpenAPI 3.1: hợp đồng kết hợp JSON, CSV và headers

Ví dụ mô tả GET collection với hai media type, POST tạo và DELETE không body. Phần security minh họa Bearer cho thao tác ghi; GET catalog là dữ liệu công khai.

~~~yaml
openapi: 3.1.0
info:
  title: Products API
  version: 1.0.0
paths:
  /api/v1/products:
    get:
      operationId: listProducts
      summary: Liệt kê sản phẩm
      description: >
        page bắt đầu từ 0, size tối đa 100.
        JSON là representation mặc định.
        CSV xuất các dòng sản phẩm, không gồm metadata page trong body.
      parameters:
        - in: query
          name: page
          schema: { type: integer, minimum: 0, default: 0 }
        - in: query
          name: size
          schema: { type: integer, minimum: 1, maximum: 100, default: 20 }
        - in: header
          name: If-None-Match
          schema: { type: string }
      responses:
        '200':
          description: Trang sản phẩm theo representation yêu cầu
          headers:
            ETag:
              description: Validator cho representation này
              schema: { type: string }
            Cache-Control:
              schema: { type: string }
              example: public, max-age=30
            Vary:
              schema: { type: string }
              example: Accept
            X-Total-Count:
              schema: { type: integer, minimum: 0 }
            Link:
              description: URI trang tiếp nếu còn
              schema: { type: string }
            Content-Disposition:
              description: Filename gợi ý với CSV khi có
              schema: { type: string }
          content:
            application/json:
              schema: { $ref: '#/components/schemas/ProductPage' }
              example:
                items:
                  - id: prod-101
                    sku: BOOK-42
                    priceVnd: 120000
                    status: ACTIVE
                page: 0
                size: 2
                totalItems: 34
            text/csv:
              schema: { type: string }
              example: |
                id,sku,priceVnd,status
                prod-101,BOOK-42,120000,ACTIVE
        '304':
          description: Không thay đổi, không có body
          headers:
            ETag:
              schema: { type: string }
            Cache-Control:
              schema: { type: string }
            Vary:
              schema: { type: string }
        '400':
          description: Query không hợp lệ
          content:
            application/problem+json:
              schema: { $ref: '#/components/schemas/Problem' }
        '406':
          description: Không có media type đáp ứng Accept
    post:
      operationId: createProduct
      summary: Tạo một sản phẩm
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: '#/components/schemas/CreateProduct' }
      responses:
        '201':
          description: Đã tạo sản phẩm
          headers:
            Location:
              required: true
              schema: { type: string, format: uri-reference }
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Product' }
        '400':
          description: JSON hoặc dữ liệu không hợp lệ
          content:
            application/problem+json:
              schema: { $ref: '#/components/schemas/Problem' }
        '401':
          description: Chưa xác thực
          headers:
            WWW-Authenticate:
              schema: { type: string }
        '403': { description: Không có quyền }
        '409': { description: SKU xung đột }
        '415': { description: Request Content-Type không hỗ trợ }
  /api/v1/products/{id}:
    delete:
      operationId: deleteProduct
      summary: Xóa sản phẩm
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
      responses:
        '204':
          description: Xóa thành công, không có body
        '401': { description: Chưa xác thực }
        '403': { description: Không có quyền }
        '404': { description: Không tìm thấy sản phẩm }
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    Product:
      type: object
      required: [id, sku, priceVnd, status]
      properties:
        id: { type: string }
        sku: { type: string }
        priceVnd: { type: integer, format: int64, minimum: 0 }
        status:
          type: string
          enum: [ACTIVE, INACTIVE]
    CreateProduct:
      type: object
      additionalProperties: false
      required: [sku, priceVnd, status]
      properties:
        sku: { type: string, minLength: 1 }
        priceVnd: { type: integer, format: int64, minimum: 0 }
        status:
          type: string
          enum: [ACTIVE, INACTIVE]
    ProductPage:
      type: object
      required: [items, page, size, totalItems]
      properties:
        items:
          type: array
          items: { $ref: '#/components/schemas/Product' }
        page: { type: integer, minimum: 0 }
        size: { type: integer, minimum: 1 }
        totalItems: { type: integer, format: int64, minimum: 0 }
    Problem:
      type: object
      properties:
        type: { type: string, format: uri-reference }
        title: { type: string }
        status: { type: integer }
        detail: { type: string }
~~~

**Điểm cần kiểm chứng:** 200 chỉ có **một Response Object** nhưng **hai entry content**; 204/304 không có body; 201 có Location theo contract; 400 trả Problem Details. OpenAPI có thể tái sử dụng **components.headers** và **components.responses** qua $ref khi cùng ngữ nghĩa. Không coi việc khai báo schema và security scheme là bằng chứng code đã triển khai đúng.

## 11. Java/Spring: hai GET theo Accept, một hợp đồng

Ví dụ dùng Java 17+, Spring Boot 3.x, Jackson. **ProductService** và **CsvEncoder** là thành phần ứng dụng tự xây dựng.

~~~java
public record ProductView(
        String id, String sku, long priceVnd, String status) {}

public record ProductPage(
        List<ProductView> items, int page, int size, long totalItems) {}

@RestController
@RequestMapping("/api/v1/products")
public class ProductController {
    private final ProductService service;
    private final ObjectMapper mapper;
    private final CsvEncoder csv;

    // Constructor injection được lược bỏ.

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<byte[]> json(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            WebRequest request) throws JsonProcessingException {

        ProductPage data = readPage(page, size);
        return respond(data, MediaType.APPLICATION_JSON,
                mapper.writeValueAsBytes(data), request, false);
    }

    @GetMapping(produces = "text/csv")
    public ResponseEntity<byte[]> csv(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            WebRequest request) {

        ProductPage data = readPage(page, size);
        return respond(data,
            MediaType.parseMediaType("text/csv;charset=UTF-8"),
            csv.renderUtf8(data.items()), request, true);
    }

    private ProductPage readPage(int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid page or size");
        }
        return service.listPublic(page, size);
    }

    private ResponseEntity<byte[]> respond(
            ProductPage data, MediaType media,
            byte[] bytes, WebRequest request, boolean download) {

        String etag = "\"" + sha256Hex(bytes) + "\"";
        CacheControl policy =
            CacheControl.maxAge(Duration.ofSeconds(30)).cachePublic();

        if (request.checkNotModified(etag)) {
            return ResponseEntity.status(HttpStatus.NOT_MODIFIED)
                .eTag(etag).cacheControl(policy)
                .varyBy(HttpHeaders.ACCEPT).build();
        }

        ResponseEntity.BodyBuilder builder = ResponseEntity.ok()
            .contentType(media)
            .cacheControl(policy)
            .varyBy(HttpHeaders.ACCEPT)
            .eTag(etag)
            .header("X-Total-Count",
                    Long.toString(data.totalItems()));

        if (download) {
            builder.header(HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename=\"products.csv\"");
        }
        return builder.body(bytes);
    }

    private static String sha256Hex(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
~~~

Cần các import Spring MVC/HTTP, Java Duration, HexFormat, MessageDigest, Jackson và collection; đoạn mã minh họa không phải project hoàn chỉnh. Hai handler khác nhau ở **produces**, cùng URI. HTTP response được serialize trước rồi băm **đúng bytes** để tính strong ETag từng biến thể, tránh dùng validator của JSON cho CSV.

Cần kiểm thử mặc định JSON khi Accept không chỉ rõ và 406 khi không có định dạng hỗ trợ. Nếu collection lớn, serialize/băm mỗi lần vẫn có chi phí; có thể dùng một representation version đáng tin khi đảm bảo nó đổi với bất kỳ thay đổi body nào. Không áp **public, max-age=30** cho dữ liệu riêng tư theo user/tenant.

### Tạo và xóa resource

~~~java
@PostMapping(
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<ProductView> create(
        @Valid @RequestBody CreateProductRequest body,
        Authentication caller) {

    ProductView created = service.createAuthorized(caller, body);
    URI location = URI.create("/api/v1/products/" + created.id());
    return ResponseEntity.created(location).body(created);
}

@DeleteMapping("/{id}")
public ResponseEntity<Void> delete(
        @PathVariable String id, Authentication caller) {
    service.deleteAuthorized(caller, id);
    return ResponseEntity.noContent().build();
}
~~~

**CreateProductRequest** và các service dùng authorization phải cài đặt trong ứng dụng thực tế. Trả 201 chỉ sau khi transaction tạo resource đã thành công; Location phải hợp lệ, không ghép host không đáng tin. **204 không có JSON body**.

## 12. CSV, phân quyền và caching cần đi cùng response

CSV không chỉ là nối chuỗi bằng dấu phẩy. Text có dấu phẩy/nháy kép/newline phải được quote và escape; nội dung đầu vào không đáng tin bắt đầu bằng **=, +, -, @** có thể bị spreadsheet hiểu là công thức. Helper đơn giản:

~~~java
static String csvCell(String text) {
    String value = text == null ? "" : text;
    if (!value.isEmpty()
            && "=+-@\t\r".indexOf(value.charAt(0)) >= 0) {
        value = "'" + value;
    }
    return "\"" + value.replace("\"", "\"\"") + "\"";
}
~~~

Đây chỉ là lớp phòng vệ ban đầu, cần kiểm thử với spreadsheet/consumer đích, Unicode, whitespace, control chars và policy xuất dữ liệu. Không coi một hàm quote là bảo đảm chống CSV injection tuyệt đối.

**Header cũng có thể rò dữ liệu:** X-Total-Count đếm sai phạm vi; Location/Link để lộ ID tenant khác; ETag/cache key trộn response của người dùng; Content-Disposition chứa filename không an toàn. Bảo đảm authz trước count/pagination và trước replay response. Dữ liệu riêng tư nên có **Cache-Control: private/no-store** phù hợp, không dùng cache public chung chỉ vì URI giống nhau.

Với frontend cross-origin, JS không tự đọc mọi response header. Nếu client cần **Location, ETag, X-Total-Count**, cấu hình **Access-Control-Expose-Headers** và CORS theo origin đáng tin. **securitySchemes** trong OpenAPI chỉ mô tả phương thức xác thực, không tự thực thi phân quyền.

## 13. Kiểm thử HTTP response với MockMvc

Contract test phải kiểm tra **status, Content-Type, header, schema và body/no-body** trên server thật, không chỉ gọi serializer.

~~~java
@Test
void jsonReturnsHeadersAndItems() throws Exception {
    mockMvc.perform(get("/api/v1/products")
            .param("page", "0").param("size", "2")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(header().exists("ETag"))
        .andExpect(header().exists("X-Total-Count"))
        .andExpect(jsonPath("$.items").isArray());
}

@Test
void csvIsSelectedByAccept() throws Exception {
    mockMvc.perform(get("/api/v1/products").accept("text/csv"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith("text/csv"))
        .andExpect(header().exists("Content-Disposition"))
        .andExpect(content().string(startsWith(
                "id,sku,priceVnd,status")));
}

@Test
void unsupportedAcceptGets406() throws Exception {
    mockMvc.perform(get("/api/v1/products")
            .accept(MediaType.APPLICATION_XML))
        .andExpect(status().isNotAcceptable());
}

@Test
void matchingEtagGets304WithoutBody() throws Exception {
    MvcResult first = mockMvc.perform(get("/api/v1/products")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk()).andReturn();
    String etag = first.getResponse().getHeader("ETag");

    mockMvc.perform(get("/api/v1/products")
            .accept(MediaType.APPLICATION_JSON)
            .header("If-None-Match", etag))
        .andExpect(status().isNotModified())
        .andExpect(content().string(""));
}
~~~

Các ví dụ cần fixtures, imports và Spring configuration thật. Một phần test khác phải xác nhận **201 có Location**, **204 không body**, **415 khi POST sai Content-Type**, **409 khi SKU trùng** và **400 trả Problem Details** nếu hợp đồng công bố. Với Spring Security, tạo principal có role hợp lệ; không tắt phân quyền để làm test pass.

| Test bổ sung | Bất biến cần chứng minh |
| --- | --- |
| ETag JSON gửi khi request CSV | Không trả 304 sai do trộn biến thể |
| Page rỗng | 200 với items rỗng/CSV header row theo contract |
| Dữ liệu CSV chứa dấu phẩy/quote hoặc công thức | Encoder và spreadsheet handling an toàn |
| Hai tenant | Không lộ count, Location, Link, cache hoặc body trái quyền |
| Browser cross-origin | Chỉ expose header đúng chính sách CORS |
| Tích hợp CDN/proxy | Cache tôn trọng Vary, ETag và quyền |
| OpenAPI so với runtime | Mọi mã, header, media type và schema khớp |

Chạy **OpenAPI linter/schema validator** trong CI, kết hợp integration test qua HTTP server. Nếu code bổ sung media type hoặc đổi status, spec và tests phải được cập nhật cùng lúc.

## 14. Bài tập: trả đơn hàng bằng JSON và CSV

Thiết kế hợp đồng đa tenant:

~~~text
GET /api/v1/orders?status=PAID&page=0&size=25
POST /api/v1/orders
DELETE /api/v1/orders/{id}
~~~

GET hỗ trợ **application/json** và **text/csv**; POST nhận JSON, trả **201 + Location**; DELETE trả **204**. Đơn hàng thuộc tenant, CSV có tên người nhận do client nhập.

Hãy thực hiện:

1. Viết **responses** cho 200, 201, 204, 304 và lỗi 400/401/403/404/406/409/415 phù hợp.
2. Mô tả **hai media type dưới một response 200**, schema JSON, CSV UTF-8/quote/header row.
3. Khai báo **Location, ETag, Cache-Control, Vary, X-Total-Count, Content-Disposition**, không đặt Content-Type trong headers map.
4. Thiết kế ETag theo **tenant, filter, page, media type** và policy **private/no-store** cho dữ liệu riêng tư; 304 không có body.
5. Viết Spring controller **produces JSON/CSV**, POST **consumes JSON**, DELETE trả 204 và phân quyền đúng.
6. Viết ít nhất 8 test: 200 JSON/CSV, 406, 415, 201 Location, 204, 304, và chống rò thông tin T1/T2; bổ sung CSV injection test.
7. Validate tài liệu OpenAPI bằng công cụ kiểm tra schema và so với response runtime.

**Sản phẩm:** OpenAPI 3.1, ví dụ HTTP, mã Java/Spring, ma trận kiểm thử và nhận xét bảo mật/cache.

## 15. Checklist và kết luận

Trước khi công bố API, xác nhận: **description đúng cho từng status**, các **header** có schema/điều kiện xuất hiện rõ, các **media type nằm dưới cùng response code**, **204/304 không khai báo content**, **Accept/Content-Type phân biệt rõ**, có test **406/415**, Problem Details không lộ dữ liệu, **Vary/ETag/cache** giữ đúng biến thể và scope quyền.

**Cốt lõi:** OpenAPI mô tả phản hồi qua **responses → status → headers + content[media type]**. Khi implementation Spring và kiểm thử HTTP tuân cùng cấu trúc, client biết chính xác **khi nào đọc body, khi nào chỉ đọc header, định dạng nào đang được trả và mã lỗi nào cần xử lý**.








