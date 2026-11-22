# Mô tả liên kết hoặc con trỏ cho phân trang cursor

Phân trang cursor chia một tập dữ liệu thành các phần liên tiếp bằng một giá trị con trỏ (cursor). Client gửi cursor nhận được từ response trước để lấy phần tiếp theo. Khác với phân trang offset dùng số trang hoặc vị trí bắt đầu, cursor thường đại diện cho vị trí cuối cùng đã đọc theo một thứ tự sắp xếp ổn định. Cách này phù hợp với danh sách lớn, dữ liệu thay đổi thường xuyên hoặc API cần tiếp tục đọc mà không phải quét lại các bản ghi từ đầu.

Trong hợp đồng OpenAPI, cursor có thể được mô tả như query parameter; response có thể trả `nextCursor`, `previousCursor` hoặc URL điều hướng `next`/`previous`. Springdoc-openapi giúp công bố các trường và parameter này bằng schema, annotation và response header. Cần phân biệt cursor token, URL điều hướng trong payload, HTTP `Link` header và OpenAPI Link Object vì chúng có vai trò khác nhau.

## 1. Cursor pagination hoạt động như thế nào?

Với offset pagination, client thường gửi `page` và `size`, hoặc `offset` và `limit`. Server bỏ qua một số bản ghi rồi lấy phần tiếp theo. Với cursor pagination, server trả một cursor mô tả vị trí tiếp tục. Client gửi cursor đó trong request kế tiếp.

Ví dụ luồng đơn giản:

```text
Request đầu:
GET /api/orders?limit=20

Response đầu:
{
  "items": [ ... 20 đơn hàng ... ],
  "nextCursor": "eyJjcmVhdGVkQXQiOi..."
}

Request tiếp:
GET /api/orders?limit=20&cursor=eyJjcmVhdGVkQXQiOi...

Response tiếp:
{
  "items": [ ... 20 đơn hàng tiếp theo ... ],
  "nextCursor": "eyJjcmVhdGVkQXQiOi..."
}
```

Client không cần tự tính vị trí tiếp theo. Server phát hành cursor sau khi xác định trang hiện tại và dùng cursor đó để tiếp tục truy vấn.

Một response có thể chứa:

- `items`: các phần tử của trang hiện tại.
- `nextCursor`: cursor để lấy trang kế tiếp; có thể null hoặc không xuất hiện khi hết dữ liệu.
- `previousCursor`: cursor để quay lại trang trước nếu API hỗ trợ điều hướng ngược.
- `hasNext` hoặc `hasPrevious`: cờ trạng thái nếu API cần cung cấp tường minh, dù có thể suy ra từ cursor.
- `next` và `previous`: URL đầy đủ hoặc tương đối để client gọi tiếp.

Không cần trả tất cả trường trên nếu chúng trùng lặp thông tin. Hãy chọn một cấu trúc rõ ràng và giữ ổn định trong toàn API.

## 2. Cursor khác offset và page number

| Tiêu chí | Offset/page | Cursor |
|---|---|---|
| Tham số tiếp tục | `page`, `size`, `offset`, `limit` | `cursor`, thường kèm `limit` |
| Cách xác định vị trí | Bỏ qua số lượng bản ghi trước đó | Tiếp tục sau một khóa sắp xếp hoặc vị trí đã mã hóa |
| Khi dữ liệu mới được chèn | Bản ghi có thể dịch chuyển giữa các trang | Ít bị dịch chuyển nếu thứ tự và cursor được thiết kế ổn định |
| Truy cập trang tùy ý | Dễ hơn với page number/offset | Thường cần đi tuần tự từ cursor đã có |
| Hiệu năng trên tập dữ liệu lớn | Offset lớn có thể tốn chi phí quét/bỏ qua | Keyset query có thể tận dụng index phù hợp |
| Điều hướng ngược | Dễ tính bằng số trang | Cần cursor trước hoặc cơ chế truy vấn ngược |
| Hiển thị tổng số trang | Thường dễ tính nếu có total count | Không nhất thiết có total count |

Cursor không tự động làm truy vấn nhanh. Hiệu năng phụ thuộc cách tạo cursor, thứ tự sắp xếp, index và câu truy vấn. Nếu server vẫn giải mã cursor rồi thực hiện `OFFSET` rất lớn, nhiều lợi ích của keyset pagination sẽ không xuất hiện.

## 3. Thiết kế cursor ổn định bằng keyset pagination

Một cursor thường lưu các giá trị sắp xếp của bản ghi cuối cùng trong trang hiện tại. Ví dụ danh sách đơn hàng được sắp xếp theo `createdAt DESC`; nếu nhiều bản ghi có cùng thời điểm, cần thêm khóa duy nhất như `id DESC` để thứ tự không bị nhập nhằng.

```sql
SELECT id, created_at, status, total
FROM orders
WHERE (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :limitPlusOne;
```

Đây là dạng minh họa cho cơ sở dữ liệu hỗ trợ so sánh tuple. Với hệ quản trị khác, có thể viết điều kiện tương đương:

```sql
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id < :lastId)
```

Server thường truy vấn `limit + 1` bản ghi để biết còn dữ liệu tiếp theo hay không. Nếu có bản ghi dư, server trả `limit` phần tử và tạo `nextCursor` từ khóa sắp xếp của phần tử cuối cùng được trả.

Một cursor ổn định cần:

- Có thứ tự sắp xếp xác định, tốt nhất gồm một khóa duy nhất làm tie-breaker.
- Lưu đủ các giá trị cần để tiếp tục truy vấn, không chỉ một timestamp có thể trùng.
- Dùng cùng thứ tự và điều kiện lọc ở các request tiếp theo.
- Xác định rõ cách xử lý giá trị null, collation và độ chính xác timestamp.
- Được tạo từ dữ liệu sau cùng trong trang đã trả, không phải bản ghi dư dùng để phát hiện trang kế tiếp.

Nếu thứ tự sắp xếp thay đổi giữa các request, cursor cũ có thể không còn ý nghĩa. Hãy cố định sort trong hợp đồng hoặc ràng buộc sort vào cursor.

## 4. Thiết kế request parameter `cursor` và `limit`

Một endpoint cursor pagination thường nhận cursor tùy chọn và giới hạn số phần tử. Request đầu tiên không gửi cursor; các request tiếp theo gửi cursor từ response trước.

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping
    CursorPage<OrderResponse> list(
            @RequestParam(required = false) String cursor,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit) {
        return orderService.list(cursor, limit);
    }
}
```

Trong ví dụ:

- `cursor` là query parameter tùy chọn; không có cursor nghĩa là bắt đầu từ vị trí đầu tiên.
- `limit` là số phần tử tối đa yêu cầu trong một response.
- `@Min` và `@Max` giới hạn kích thước trang ở runtime nếu validation được kích hoạt.
- `defaultValue` cho phép Spring áp dụng giá trị mặc định khi query parameter không được gửi.

Không nên cho phép `limit` không giới hạn. Giá trị tối đa giúp kiểm soát tải cơ sở dữ liệu, bộ nhớ và kích thước response. Nếu cursor sai định dạng, hết hạn hoặc không phù hợp với bộ lọc hiện tại, API cần có response lỗi rõ ràng, chẳng hạn `400 Bad Request`.

## 5. Mô tả cursor parameter bằng springdoc-openapi

Springdoc có thể suy ra query parameter từ `@RequestParam`. Dùng `@Parameter` để mô tả rõ cursor là token opaque, không phải số trang hay giá trị client tự tạo.

```java
@GetMapping
CursorPage<OrderResponse> list(
        @Parameter(
            description = "Con trỏ do server trả về ở trang trước. Bỏ qua khi lấy trang đầu tiên.",
            example = "eyJjcmVhdGVkQXQiOiIyMDI2LTExLTIwVDEwOjAwOjAwWiIsImlkIjoiLi4uIn0"
        )
        @RequestParam(required = false) String cursor,
        @Parameter(
            description = "Số phần tử tối đa trong một trang",
            example = "20"
        )
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit) {
    return orderService.list(cursor, limit);
}
```

Trong OpenAPI, `cursor` thường có schema `type: string`, `required: false`; `limit` là integer, có giá trị mặc định và giới hạn tương ứng. Không mô tả cursor là `format: uuid` nếu token thực tế là chuỗi opaque chứa dữ liệu mã hóa hoặc chữ ký.

Ví dụ YAML rút gọn:

```yaml
paths:
  /api/orders:
    get:
      parameters:
        - name: cursor
          in: query
          required: false
          description: Cursor do server cấp từ response trước
          schema:
            type: string
        - name: limit
          in: query
          required: false
          description: Số phần tử tối đa trong trang
          schema:
            type: integer
            format: int32
            minimum: 1
            maximum: 100
            default: 20
      responses:
        '200':
          description: Trang đơn hàng
```

Nếu endpoint cho phép lọc hoặc sắp xếp, các parameter như `status`, `fromDate`, `sort` cũng cần được mô tả. Server phải xác định chúng có được thay đổi khi client gửi cursor cũ hay không.

## 6. Mô tả `nextCursor` và `previousCursor` trong response schema

Response nên mô tả rõ cursor nào có thể được sử dụng để đi tiếp hoặc quay lại. Ví dụ DTO:

```java
public class CursorPage<T> {
    private List<T> items;
    private String nextCursor;
    private String previousCursor;

    // getters và setters
}
```

Schema OpenAPI minh họa:

```yaml
CursorPageOrderResponse:
  type: object
  required:
    - items
  properties:
    items:
      type: array
      items:
        $ref: '#/components/schemas/OrderResponse'
    nextCursor:
      type: string
      nullable: true
      description: Cursor lấy trang tiếp theo; null khi không còn trang sau
    previousCursor:
      type: string
      nullable: true
      description: Cursor quay lại trang trước nếu API hỗ trợ
```

`nullable: true` là cách biểu diễn thường dùng trong OpenAPI 3.0. Nếu tài liệu dùng OpenAPI 3.1, cần biểu diễn null theo cú pháp JSON Schema mà phiên bản springdoc đang xuất hỗ trợ.

Không nhất thiết phải trả `hasNext` nếu `nextCursor` null đã thể hiện rõ rằng không còn trang sau. Nếu vẫn trả cả hai, cần bảo đảm chúng luôn nhất quán: `hasNext: true` phải đi cùng một cursor có thể sử dụng.

Có thể dùng `@Schema` để mô tả các trường:

```java
public class CursorPage<T> {
    @Schema(description = "Các phần tử trong trang hiện tại")
    private List<T> items;

    @Schema(
        description = "Cursor opaque dùng để lấy trang tiếp theo; null khi hết dữ liệu",
        nullable = true,
        example = "eyJjcmVhdGVkQXQiOi..."
    )
    private String nextCursor;

    @Schema(
        description = "Cursor opaque dùng để quay lại trang trước; null nếu không có",
        nullable = true
    )
    private String previousCursor;

    // getters và setters
}
```

Schema generic `CursorPage<T>` có thể được springdoc tạo với tên phụ thuộc kiểu cụ thể. Nếu tên schema cần ổn định trong hợp đồng công khai, có thể tạo DTO cụ thể như `OrderCursorPageResponse` hoặc cấu hình tên schema theo phiên bản thư viện.

## 7. Trả URL `next` và `previous` thay cho cursor token

Một API có thể trả trực tiếp URL hoàn chỉnh hoặc tương đối để client chỉ cần gọi lại:

```json
{
  "items": [
    { "id": "ord-101", "status": "PAID" }
  ],
  "links": {
    "next": "/api/orders?limit=20&cursor=eyJpZCI6...",
    "previous": null
  }
}
```

Trong cách này, server chịu trách nhiệm tạo URL và giữ lại các filter, sort, limit cần thiết. Client không phải ghép query string thủ công. DTO tương ứng:

```java
public class PageLinks {
    private URI next;
    private URI previous;

    // getters và setters
}

public class LinkedCursorPage<T> {
    private List<T> items;
    private PageLinks links;

    // getters và setters
}
```

Schema:

```yaml
PageLinks:
  type: object
  properties:
    next:
      type: string
      format: uri-reference
      nullable: true
    previous:
      type: string
      format: uri-reference
      nullable: true
```

URL tương đối có thể dùng khi API được triển khai sau reverse proxy hoặc có nhiều môi trường. URL tuyệt đối thuận tiện cho client nhưng cần tạo đúng scheme, host và base path theo cấu hình triển khai. Không xây URL từ header `Host` hoặc forwarded header chưa được tin cậy nếu ứng dụng chưa cấu hình proxy trust đúng cách.

`next` và `previous` trong JSON là dữ liệu response do ứng dụng tạo. Chúng khác OpenAPI Link Object: một bên là URL runtime thực tế, bên kia là metadata trong tài liệu OpenAPI mô tả cách gọi operation.

## 8. Mô tả HTTP `Link` header

Một lựa chọn khác là đặt URL phân trang trong HTTP response header `Link`, thường theo cú pháp Web Linking:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Link: </api/orders?limit=20&cursor=abc123>; rel="next"
```

Nếu có trang trước:

```http
Link: </api/orders?limit=20&cursor=prev456>; rel="prev",
      </api/orders?limit=20&cursor=next789>; rel="next"
```

`rel="next"` và `rel="prev"` xác định quan hệ của URL. Cần encode query parameter đúng quy tắc URI; không nối cursor thô vào header nếu nó chứa ký tự cần percent-encode.

Trong Spring, có thể thêm header vào `ResponseEntity`:

```java
return ResponseEntity.ok()
        .header(HttpHeaders.LINK,
                "</api/orders?limit=20&cursor=" + encodedCursor + ">; rel=\"next\"")
        .body(page);
```

Đoạn code trên minh họa cấu trúc header; trong triển khai thực tế, hãy tạo URI bằng `UriComponentsBuilder` hoặc một URI builder tương ứng, encode query parameter và tạo từng link theo cách an toàn. Tránh nối chuỗi thủ công khi cursor có thể chứa ký tự đặc biệt.

Với springdoc, khai báo response header bằng `@ApiResponse(headers = @Header(...))`:

```java
@ApiResponse(
    responseCode = "200",
    description = "Trang đơn hàng",
    headers = @Header(
        name = "Link",
        description = "Liên kết đến trang trước hoặc trang tiếp theo",
        schema = @Schema(type = "string")
    )
)
```

Nếu frontend gọi API từ origin khác và cần đọc `Link` bằng JavaScript, cấu hình CORS `Access-Control-Expose-Headers: Link`. Header tồn tại trên response không đồng nghĩa JavaScript luôn được phép đọc nó.

## 9. Mô tả liên kết trang kế tiếp bằng OpenAPI Link Object

OpenAPI Link Object có thể mô tả operation phân trang tiếp theo bằng cách lấy `nextCursor` từ response hiện tại và truyền vào query parameter `cursor` của cùng operation.

```yaml
paths:
  /api/orders:
    get:
      operationId: listOrders
      parameters:
        - name: cursor
          in: query
          required: false
          schema:
            type: string
        - name: limit
          in: query
          required: false
          schema:
            type: integer
            default: 20
      responses:
        '200':
          description: Trang đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderCursorPage'
          links:
            nextPage:
              operationId: listOrders
              parameters:
                cursor: '$response.body#/nextCursor'
                limit: '$request.query.limit'
```

Link `nextPage` cho biết operation đích vẫn là `listOrders`; cursor được lấy từ `nextCursor` của response hiện tại và `limit` được giữ từ request nguồn.

Có một điểm cần chú ý: Link Object nằm tĩnh trong tài liệu cho response `200`, trong khi trang cuối có thể trả `nextCursor: null`. Client hoặc công cụ tiêu thụ phải kiểm tra giá trị cursor trước khi theo link. Link mô tả cách tạo request tiếp theo; nó không bảo đảm response hiện tại luôn có trang kế tiếp.

Nếu cần giữ các filter khác như `status` hoặc `fromDate`, ánh xạ chúng từ request nguồn:

```yaml
links:
  nextPage:
    operationId: listOrders
    parameters:
      cursor: '$response.body#/nextCursor'
      limit: '$request.query.limit'
      status: '$request.query.status'
      fromDate: '$request.query.fromDate'
```

Operation đích phải có các parameter tương ứng. Nếu filter thay đổi trong khi cursor được tái sử dụng, kết quả có thể sai hoặc cursor không còn hợp lệ.

## 10. Khai báo OpenAPI Link bằng annotation springdoc

Có thể dùng `@Link` và `@LinkParameter` trên response để mô tả trang tiếp theo:

```java
@Operation(operationId = "listOrders", summary = "Liệt kê đơn hàng theo cursor")
@ApiResponse(
    responseCode = "200",
    description = "Trang đơn hàng",
    links = @Link(
        name = "nextPage",
        operationId = "listOrders",
        description = "Dùng cursor trong response để lấy trang kế tiếp",
        parameters = {
            @LinkParameter(
                name = "cursor",
                expression = "$response.body#/nextCursor"
            ),
            @LinkParameter(
                name = "limit",
                expression = "$request.query.limit"
            )
        }
    )
)
@GetMapping("/api/orders")
CursorPage<OrderResponse> list(
        @RequestParam(required = false) String cursor,
        @RequestParam(defaultValue = "20") int limit) {
    return orderService.list(cursor, limit);
}
```

Các kiểu `CursorPage`, `OrderResponse` và `orderService` là thành phần minh họa. Sau khi khởi động ứng dụng, kiểm tra `/v3/api-docs` hoặc `/v3/api-docs.yaml` để xác nhận link nằm dưới response `200` và biểu thức được giữ nguyên.

Nếu `nextCursor` null ở trang cuối, công cụ không nên tạo request tiếp theo với cursor null. Đây là điều kiện nghiệp vụ mà client cần xử lý; annotation không làm link biến mất theo từng response runtime.

## 11. Thiết kế cursor token an toàn và bền vững

Cursor thường là token opaque: client chỉ lưu và gửi lại, không tự giải mã hoặc thay đổi. Token có thể chứa các giá trị keyset như timestamp và ID, hoặc là mã tham chiếu đến trạng thái được lưu phía server.

Một cursor dạng token có thể được tạo từ payload JSON rồi mã hóa Base64 URL-safe và ký số:

```json
{
  "v": 1,
  "createdAt": "2026-11-20T10:00:00Z",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "sort": "createdAt:desc,id:desc",
  "filterHash": "...",
  "expiresAt": "2026-11-20T12:00:00Z"
}
```

Đây là payload minh họa; token thực tế có thể được ký bằng HMAC hoặc dùng định danh ngẫu nhiên trỏ đến trạng thái server. Base64 chỉ là encoding, không phải mã hóa bảo mật. Nếu token chứa thông tin nhạy cảm, cần mã hóa hoặc không đưa dữ liệu đó vào token.

Các nguyên tắc quan trọng:

- Xác thực chữ ký hoặc tính toàn vẹn để client không thể sửa ID, sort key hay phạm vi truy vấn.
- Ràng buộc cursor với filter, sort, tenant hoặc ngữ cảnh truy cập phù hợp để tránh tái sử dụng sai phạm vi.
- Kiểm tra quyền truy cập ở mọi request; cursor không phải access token và không cấp quyền.
- Có thể đặt phiên bản token (`v`) để thay đổi cấu trúc cursor có kiểm soát.
- Cân nhắc thời hạn hết hiệu lực và cách phản hồi khi cursor hết hạn.
- Tránh chứa PII hoặc bí mật trong token dễ quan sát trên URL, log và browser history.
- Giới hạn độ dài token và xử lý token lỗi định dạng một cách nhất quán.

Cursor trong query string có thể xuất hiện trong access log, analytics, lịch sử trình duyệt hoặc header Referer tùy môi trường. Không dùng cursor làm nơi chứa thông tin xác thực.

## 12. Giữ nguyên filter và sort giữa các trang

Cursor chỉ có ý nghĩa trong ngữ cảnh truy vấn đã tạo ra nó. Ví dụ, cursor được phát hành cho `status=PAID` và `sort=createdAt,desc` không nên được dùng với `status=CANCELLED` hoặc một sort khác nếu token không được thiết kế cho điều đó.

Có hai cách phổ biến:

1. Đưa hash của filter/sort vào cursor và kiểm tra lại ở request tiếp theo.
2. Lưu filter/sort trong trạng thái cursor phía server và chỉ trả token tham chiếu.

Khi tạo URL `next`, hãy giữ nguyên các parameter liên quan:

```text
/api/orders?status=PAID&sort=createdAt%2Cdesc&limit=20&cursor=...
```

Nếu client thay đổi filter, nên bắt đầu một luồng phân trang mới bằng cách bỏ cursor cũ. API có thể trả `400 Bad Request` khi phát hiện cursor không tương thích với query hiện tại.

## 13. Điều hướng ngược và `previousCursor`

Không phải hệ thống nào cũng hỗ trợ quay lại trang trước. Với keyset pagination, cursor tiến và cursor lùi có thể cần logic truy vấn khác nhau.

Để hỗ trợ `previousCursor`, server cần lưu hoặc tính được vị trí bắt đầu của trang trước. Một số thiết kế:

- Trả cursor trước được tạo từ khóa đầu tiên của trang hiện tại và đảo chiều điều kiện/order khi truy vấn ngược.
- Lưu cursor của các trang đã đi qua ở client hoặc server.
- Chỉ hỗ trợ next-only để giữ hợp đồng đơn giản nếu sản phẩm không cần điều hướng ngược.

Ví dụ khi sắp xếp `createdAt DESC, id DESC`, truy vấn tiếp theo dùng điều kiện nhỏ hơn khóa cuối trang; truy vấn ngược cần dùng điều kiện lớn hơn khóa đầu trang, lấy theo thứ tự ngược rồi đảo kết quả trước khi trả. Chi tiết phụ thuộc hệ quản trị dữ liệu và thứ tự sort.

Không tạo `previousCursor` giả bằng cách lùi một số lượng bản ghi cố định nếu dữ liệu có thể thay đổi. Hãy kiểm tra tính ổn định của cursor và thứ tự trả về.

## 14. Response lỗi liên quan đến cursor

Cursor pagination có thể phát sinh lỗi riêng:

| Status | Tình huống |
|---|---|
| `400 Bad Request` | Cursor sai định dạng, chữ ký không hợp lệ hoặc không khớp filter/sort |
| `401 Unauthorized` | Request chưa xác thực |
| `403 Forbidden` | Người dùng không có quyền truy cập phạm vi dữ liệu |
| `410 Gone` | Cursor hoặc snapshot đã hết hạn và API chọn semantics này |
| `422 Unprocessable Content` | Token hợp lệ về cú pháp nhưng không thể xử lý theo quy tắc nghiệp vụ, nếu API dùng status này |
| `429 Too Many Requests` | Client gọi phân trang quá nhanh hoặc vượt quota |

Không phải mọi API cần dùng `410` hay `422`; hãy chọn status code nhất quán với quy ước lỗi của hệ thống. Response lỗi nên có schema ổn định, mã lỗi có thể xử lý và thông báo không tiết lộ chi tiết token nội bộ.

Ví dụ response lỗi:

```yaml
responses:
  '400':
    description: Cursor không hợp lệ hoặc không tương thích với bộ lọc
    content:
      application/problem+json:
        schema:
          $ref: '#/components/schemas/ApiProblem'
  '410':
    description: Cursor đã hết hạn
    content:
      application/problem+json:
        schema:
          $ref: '#/components/schemas/ApiProblem'
```

## 15. Kiểm tra hợp đồng và hành vi phân trang

Sau khi khai báo cursor parameter, response schema và link, cần xác minh cả tài liệu lẫn luồng request:

1. Tải `/v3/api-docs` hoặc `/v3/api-docs.yaml`.
2. Kiểm tra `cursor` là query parameter tùy chọn, `limit` có giới hạn và mặc định đúng.
3. Kiểm tra `nextCursor`/`previousCursor` hoặc URL link được mô tả đúng kiểu, nullability và ý nghĩa.
4. Kiểm tra OpenAPI Link Object nếu dùng; parameter đích phải có tên trùng với operation phân trang.
5. Gọi request đầu tiên không có cursor và xác nhận server trả trang đầu.
6. Gửi `nextCursor` nhận được để lấy trang tiếp theo.
7. Xác nhận không lặp hoặc bỏ sót phần tử trong tập dữ liệu tĩnh.
8. Chèn hoặc cập nhật bản ghi giữa các request để kiểm tra hành vi khi dữ liệu thay đổi.
9. Thử cursor sai, hết hạn, bị sửa và cursor thuộc filter/sort khác.
10. Kiểm tra giới hạn `limit`, quyền truy cập, tenant và response lỗi.
11. Nếu dùng URL hoặc `Link` header, xác nhận URL giữ filter/sort và được encode đúng.
12. Chạy OpenAPI validator và kiểm tra Swagger UI/client generator.

Một phép kiểm tra quan trọng là không lặp bản ghi khi nhiều bản ghi có cùng sort key. Nếu chỉ sắp xếp theo `createdAt` và nhiều đơn hàng có timestamp giống nhau, cursor có thể bỏ sót hoặc trả trùng. Thêm khóa duy nhất như `id` làm tie-breaker giúp thứ tự xác định.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Trang tiếp theo lặp bản ghi | Sort không có tie-breaker duy nhất hoặc cursor lấy sai phần tử | Dùng thứ tự ổn định và tạo cursor từ bản ghi cuối được trả |
| Bỏ sót bản ghi | Điều kiện keyset không khớp thứ tự sort hoặc xử lý null sai | Kiểm tra predicate và thứ tự sắp xếp |
| Cursor cũ trả dữ liệu không đúng filter | Không ràng buộc cursor với query context | Lưu hoặc ký filter/sort cùng cursor và kiểm tra lại |
| Client tự giải mã hoặc sửa cursor | Hợp đồng không nói rõ cursor là opaque | Mô tả cursor là token do server cấp, không chỉnh sửa |
| `nextCursor` null nhưng link vẫn được theo | Link Object tĩnh trong tài liệu | Client kiểm tra cursor trước khi gọi trang tiếp |
| URL next mất filter | Server chỉ tạo URL với cursor và limit | Giữ nguyên filter/sort đã áp dụng |
| Cursor quá dài | Đưa quá nhiều trạng thái vào token | Giảm payload hoặc dùng token tham chiếu server-side |
| Cursor lộ thông tin nội bộ | Token Base64 chứa dữ liệu rõ | Ký để chống sửa; mã hóa hoặc dùng opaque ID nếu cần bí mật |
| Swagger UI không tự điều hướng | UI không thực thi OpenAPI Link hoặc chỉ hiển thị metadata | Thử gọi thủ công hoặc dùng client hỗ trợ link |
| `Link` header không đọc được từ frontend | CORS chưa expose header | Thêm `Link` vào `Access-Control-Expose-Headers` |

## 17. Nguyên tắc thiết kế

- Dùng cursor cho luồng đọc tuần tự hoặc tập dữ liệu lớn; dùng offset/page khi cần truy cập trang tùy ý và chi phí phù hợp.
- Dùng sort ổn định, có khóa duy nhất làm tie-breaker.
- Mô tả cursor là chuỗi opaque do server phát hành; client chỉ lưu và gửi lại.
- Giới hạn `limit` và mô tả rõ giá trị mặc định, tối đa.
- Trả `nextCursor` khi có trang sau; không bắt buộc thêm `hasNext` nếu thông tin đã rõ.
- Giữ filter và sort nhất quán giữa các request; ràng buộc cursor với query context nếu cần.
- Chọn response body links, HTTP `Link` header hoặc OpenAPI Link Object theo nhu cầu; không nhầm lẫn vai trò của chúng.
- Nếu dùng OpenAPI Link, ánh xạ cursor bằng runtime expression và yêu cầu client kiểm tra null ở trang cuối.
- Ký hoặc bảo vệ cursor khỏi sửa đổi; mã hóa nếu token có dữ liệu cần giữ bí mật.
- Kiểm tra authorization độc lập; cursor không phải token xác thực.
- Kiểm thử dữ liệu thay đổi, sort key trùng, cursor hết hạn và các trường hợp lỗi.
- Xác minh schema và link trong JSON/YAML được springdoc sinh ra.

## Kết luận

Cursor pagination dùng một token do server cấp để tiếp tục truy vấn từ vị trí đã đọc. Hợp đồng OpenAPI cần mô tả query parameter `cursor`, giới hạn `limit`, các trường `nextCursor`/`previousCursor` hoặc URL điều hướng, và có thể thêm OpenAPI Link Object để ánh xạ cursor của response vào request tiếp theo. Springdoc-openapi hỗ trợ công bố những thành phần này qua `@Parameter`, `@Schema`, response header và `@Link`/`@LinkParameter`. Hãy giữ thứ tự truy vấn ổn định, ràng buộc cursor với filter/sort phù hợp, bảo vệ token và kiểm tra luồng phân trang thực tế để client không bị lặp, thiếu hoặc truy cập sai dữ liệu.
