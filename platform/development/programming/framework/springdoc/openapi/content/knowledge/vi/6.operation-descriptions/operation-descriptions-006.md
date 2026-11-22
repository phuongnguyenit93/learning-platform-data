# Nội dung Markdown, khối mã và giới hạn hiển thị

## 1. Vì sao nội dung mô tả operation cần được trình bày tốt?

OpenAPI không chỉ liệt kê path và kiểu dữ liệu. Một operation tốt còn giải thích mục đích, điều kiện sử dụng, thứ tự thao tác, quy tắc nghiệp vụ, lỗi có thể gặp và ví dụ để client tích hợp đúng.

Springdoc OpenAPI tạo document từ controller, DTO, annotation, Jackson metadata và validation. Các trường description trong document có thể chứa Markdown theo quy tắc CommonMark của OpenAPI. Swagger UI đọc các trường đó và hiển thị nội dung có định dạng trong trang API reference.

Trong module SPRINGDOC_OPENAPI, việc mô tả request, response, schema, bảo mật, document groups, JSON/YAML, kiểm thử contract và phân phối tài liệu đều cần nội dung dễ đọc. Một đoạn mô tả ngắn nhưng rõ thường hữu ích hơn một khối văn bản dài, lặp lại cấu trúc đã có trong schema.

Bài này tập trung vào cách viết Markdown trong description, cách đặt khối mã, cách cung cấp example có cấu trúc, cách xử lý chuỗi nhiều dòng trong Java annotation và cách giữ nội dung hiển thị tốt trong Swagger UI.

## 2. Markdown nằm ở đâu trong OpenAPI document?

OpenAPI có nhiều trường văn bản có thể chứa mô tả. Một số vị trí thường dùng:

| Vị trí | Mục đích |
|---|---|
| info.description | Giới thiệu API ở cấp document |
| tags[].description | Giải thích một nhóm operation |
| operation.description | Hướng dẫn sử dụng một operation |
| parameter.description | Giải thích path, query, header hoặc cookie parameter |
| requestBody.description | Giải thích payload gửi lên |
| responses[status].description | Giải thích kết quả hoặc tình huống lỗi |
| schema.description | Giải thích model hoặc property |
| header.description | Giải thích response/request header |

Trường summary thường dùng cho nhãn ngắn trong danh sách operation. Nên giữ summary súc tích, dễ quét bằng mắt; đặt quy trình, điều kiện và ví dụ vào description.

Không phải mọi trường text trong OpenAPI đều có cùng ý nghĩa. Ví dụ, example là dữ liệu mẫu có cấu trúc; description là phần giải thích cho người đọc. Không dùng description thay thế schema hoặc example.

## 3. Markdown trong OpenAPI tuân theo CommonMark

OpenAPI Specification quy định các trường description hỗ trợ CommonMark. Các cấu trúc thường dùng gồm:

- Heading bằng dấu thăng.
- Đoạn văn.
- Danh sách có thứ tự và không thứ tự.
- In đậm và in nghiêng.
- Link.
- Inline code.
- Fenced code block.
- Blockquote.

Ví dụ một operation description:

~~~~markdown
### Điều kiện sử dụng

- Người gọi phải có quyền đọc đơn hàng.
- Mã đơn hàng phải tồn tại.
- Đơn hàng thuộc tenant hiện tại.

**Lưu ý:** Endpoint chỉ trả dữ liệu tóm tắt.

Tham khảo [quy tắc phân trang](https://developer.example.com/pagination).
~~~~

Các renderer có thể khác nhau ở một số extension ngoài CommonMark. Vì vậy, nội dung dùng cho nhiều công cụ nên ưu tiên cú pháp CommonMark phổ biến thay vì dựa vào tính năng riêng của một renderer.

## 4. Summary và description có vai trò khác nhau

Summary là nhãn ngắn cho operation. Description cung cấp ngữ cảnh và hướng dẫn.

~~~java
@Operation(
    operationId = "getOrderById",
    summary = "Lấy đơn hàng theo mã",
    description = """
        Trả về thông tin đơn hàng theo mã định danh.

        Người gọi cần có quyền đọc đơn hàng thuộc tenant hiện tại.
        Nếu không tìm thấy đơn hàng, API trả về 404.
        """
)
@GetMapping("/{orderId}")
public OrderResponse getOrder(
        @PathVariable String orderId) {
    return orderService.getOrder(orderId);
}
~~~

Summary nên giúp người đọc nhận ra operation ngay trong danh sách. Description có thể giải thích:

- Khi nào nên gọi operation.
- Điều kiện trước khi gọi.
- Quy tắc phân quyền hoặc tenant.
- Dữ liệu đầu vào đặc biệt.
- Các response quan trọng.
- Liên kết tới quy trình liên quan.

Không lặp nguyên văn summary ở đầu description nếu câu đó không bổ sung ngữ cảnh. Nội dung lặp khiến trang tài liệu dài hơn mà không tăng thông tin.

## 5. Dùng Markdown trong @Operation

Annotation @Operation có thuộc tính description dạng String. Có thể truyền một chuỗi nhiều dòng bằng Java text block khi dự án dùng Java 15 trở lên:

~~~java
@Operation(
    summary = "Tạo đơn hàng",
    description = """
        Tạo một đơn hàng mới cho khách hàng hiện tại.

        ### Quy tắc

        - Khách hàng phải đang hoạt động.
        - Danh sách sản phẩm không được rỗng.
        - Số lượng mỗi dòng phải lớn hơn 0.

        ### Kết quả

        API trả về mã đơn hàng mới và trạng thái ban đầu.
        """
)
@PostMapping
public OrderResponse createOrder(
        @Valid @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Text block giúp giữ xuống dòng tự nhiên, tránh nối nhiều chuỗi bằng toán tử cộng. Nội dung vẫn là giá trị String tĩnh nên có thể dùng trong annotation.

Với Java cũ hơn, dùng chuỗi nối hoặc ký tự xuống dòng:

~~~java
@Operation(
    summary = "Tạo đơn hàng",
    description = "Tạo đơn hàng mới.\n\n"
        + "### Quy tắc\n\n"
        + "- Khách hàng phải đang hoạt động.\n"
        + "- Danh sách sản phẩm không được rỗng."
)
~~~

Khi dùng chuỗi thông thường, phải escape dấu nháy kép, dấu gạch chéo ngược và ký tự xuống dòng theo cú pháp Java. Text block giảm lỗi escape nhưng vẫn cần kiểm tra nội dung Markdown sau khi Springdoc sinh document.

## 6. Mô tả parameter bằng Markdown ngắn gọn

Parameter description nên giải thích đúng một tham số. Không nên đưa toàn bộ hướng dẫn operation vào từng parameter.

~~~java
@GetMapping
public Page<OrderResponse> searchOrders(
    @Parameter(
        description = """
            Từ khóa tìm kiếm theo mã đơn hàng hoặc tên khách hàng.

            Để tìm chính xác theo mã, gửi toàn bộ mã đơn hàng.
            """
    )
    @RequestParam(required = false) String keyword,

    @Parameter(
        description = "Số trang, bắt đầu từ 0.",
        example = "0"
    )
    @RequestParam(defaultValue = "0") int page
) {
    return orderService.search(keyword, page);
}
~~~

Một mô tả parameter tốt trả lời:

- Tham số đại diện cho dữ liệu nào?
- Có bắt buộc hay không?
- Giá trị mặc định là gì?
- Đơn vị đo hoặc format ra sao?
- Có giới hạn hoặc quy tắc validation nào?
- Có ví dụ hợp lệ nào?

Thông tin required và schema constraint nên được khai báo bằng cấu trúc OpenAPI tương ứng. Description chỉ giải thích thêm, không thay thế required flag, type, format, minimum hoặc maximum.

## 7. Mô tả request body và response

Request body description giải thích payload mà client gửi. Response description giải thích kết quả theo từng HTTP status.

~~~java
@PostMapping
@Operation(
    summary = "Tạo đơn hàng",
    description = """
        Tạo đơn hàng từ danh sách sản phẩm.

        Kiểm tra tồn kho được thực hiện trước khi xác nhận đơn.
        """
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Đơn hàng được tạo thành công"
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Payload không hợp lệ"
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Không đủ tồn kho để tạo đơn"
    )
})
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {
    OrderResponse result = orderService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(result);
}
~~~

Mỗi response description nên giải thích ý nghĩa của status, điều kiện xảy ra và cấu trúc body nếu cần. Không chỉ ghi “Success” hoặc “Error” cho mọi response.

Nếu response có schema lỗi dùng chung, khai báo schema qua @Content và @Schema. Description không thể thay thế model ApiError mà client cần deserialize.

## 8. Dùng heading để chia nội dung dài

Một description có nhiều chủ đề nên dùng heading để người đọc tìm nhanh:

~~~~markdown
### Mục đích

Tạo yêu cầu thanh toán cho đơn hàng.

### Điều kiện

- Đơn hàng đã được xác nhận.
- Tổng tiền lớn hơn 0.
- Người gọi có quyền thanh toán.

### Quy trình

1. Client gửi mã đơn hàng.
2. Server kiểm tra trạng thái đơn.
3. Server tạo payment request.
4. API trả về mã giao dịch.

### Lỗi có thể gặp

- 404: Không tìm thấy đơn hàng.
- 409: Đơn hàng đã được thanh toán.
- 422: Dữ liệu thanh toán không hợp lệ.
~~~~

Dùng heading có cấp bậc hợp lý. Nếu toàn bộ nội dung nằm trong description của một operation, heading cấp ba thường đủ để phân nhóm. Tránh nhảy cấp heading chỉ để tạo chữ lớn.

Không lạm dụng heading cho từng câu. Mỗi heading nên đại diện cho một phần nội dung có ý nghĩa.

## 9. Khối mã fenced code block

Fenced code block giúp hiển thị ví dụ có định dạng và giữ nguyên khoảng trắng. Dùng ba dấu backtick hoặc ba dấu ngã để mở và đóng khối.

Ví dụ request HTTP:

~~~~markdown
~~~http
POST /api/orders
Content-Type: application/json
Authorization: Bearer <token>

{
  "customerId": "CUS-1001",
  "items": [
    {
      "productId": "P-100",
      "quantity": 2
    }
  ]
}
~~~
~~~~

Tên ngôn ngữ sau dấu mở giúp renderer chọn syntax highlighting. Một số nhãn phổ biến:

| Nhãn | Nội dung |
|---|---|
| json | JSON payload |
| yaml | OpenAPI hoặc cấu hình YAML |
| http | HTTP request/response |
| bash | Lệnh shell |
| java | Mã Java |
| xml | Maven POM hoặc XML |
| text | Nội dung thuần |
| sql | SQL query |

Nếu renderer không nhận diện nhãn, khối mã vẫn cần đọc được dưới dạng văn bản đơn sắc. Không phụ thuộc màu syntax để truyền tải ý nghĩa.

## 10. Ví dụ khối mã trong annotation Java

Khi đưa Markdown vào annotation, cần bảo đảm các dấu phân cách Markdown không bị Java string parser xử lý sai.

Với text block:

~~~~java
@Operation(
    summary = "Tìm kiếm đơn hàng",
    description = """
        Gửi truy vấn tìm kiếm qua query parameter.

        Ví dụ:

        ~~~http
        GET /api/orders?status=NEW&page=0
        Accept: application/json
        ~~~

        Kết quả được phân trang.
        """
)
~~~~

Dấu backtick hoặc dấu ngã trong text block là ký tự bình thường. Không cần escape chúng theo cú pháp Java.

Nếu dùng chuỗi thông thường, dấu nháy kép trong code example cần escape, và xuống dòng phải dùng \n hoặc nối chuỗi. Với đoạn mã dài, text block thường dễ bảo trì hơn.

Hãy kiểm tra document JSON sau khi Springdoc sinh ra để chắc chắn các dấu phân cách và xuống dòng vẫn còn nguyên.

## 11. Dùng dấu phân cách phù hợp khi có code fence lồng nhau

Nếu chính tài liệu đang hướng dẫn cách viết một fenced code block, khối ngoài phải dùng số lượng dấu phân cách dài hơn hoặc dùng loại dấu khác.

Ví dụ khối ngoài dùng bốn dấu ngã, khối bên trong dùng ba dấu ngã:

~~~~markdown
~~~json
{
  "status": "NEW"
}
~~~
~~~~

Khi description chứa nhiều tầng code fence, hãy chọn delimiter ngoài dài hơn để tránh kết thúc nhầm khối. Lỗi thiếu dấu đóng có thể làm toàn bộ phần còn lại của description bị hiển thị như code hoặc khiến cấu trúc Markdown sai.

## 12. Markdown code block không phải OpenAPI example

Một khối mã trong description chỉ là văn bản được trình bày. Nó không tự trở thành request body example mà Swagger UI dùng khi người dùng bấm Try it out.

Muốn cung cấp dữ liệu mẫu có cấu trúc, hãy khai báo example hoặc examples trong OpenAPI content.

Ví dụ response:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Đơn hàng được tìm thấy",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = OrderResponse.class),
        examples = @ExampleObject(
            name = "confirmedOrder",
            summary = "Đơn hàng đã xác nhận",
            value = """
                {
                  "id": "ORD-1001",
                  "status": "CONFIRMED"
                }
                """
        )
    )
)
~~~

ExampleObject được gắn với media type và schema. Swagger UI có thể dùng nó để minh họa payload tùy cấu hình và phiên bản.

Description giải thích ý nghĩa và quy trình. Example cung cấp dữ liệu mẫu có thể được tooling đọc. Nên dùng cả hai đúng mục đích.

## 13. Dùng @Schema(example) cho property

Với một giá trị mẫu đơn giản, có thể đặt example trên schema:

~~~java
public record CreateOrderRequest(
    @Schema(
        description = "Mã khách hàng",
        example = "CUS-1001"
    )
    @NotBlank
    String customerId,

    @Schema(
        description = "Số lượng sản phẩm",
        example = "2",
        minimum = "1"
    )
    @Min(1)
    int quantity
) {
}
~~~

Example trên property giúp hiển thị một giá trị mẫu cho field. Nó không mô tả toàn bộ request object.

Với payload phức tạp, dùng @ExampleObject ở cấp Media Type hoặc content. Không nhồi JSON nhiều dòng vào một field description nếu mục đích thực tế là cung cấp request example.

Example phải khớp schema và serialization thực tế. Một ví dụ có field sai kiểu có thể làm người tích hợp gửi request lỗi dù document nhìn có vẻ đầy đủ.

## 14. Phân biệt example và examples

OpenAPI hỗ trợ cả example đơn và examples có tên.

- example phù hợp khi chỉ cần một giá trị mẫu.
- examples phù hợp khi cần nhiều tình huống hoặc đặt tên cho từng mẫu.
- ExampleObject có thể có summary, description, value hoặc externalValue theo cấu trúc được hỗ trợ.
- Không khai báo đồng thời các dạng example và examples ở cùng một Media Type Object nếu OpenAPI Specification cấm tổ hợp đó.

Ví dụ hai tình huống:

~~~java
@Content(
    mediaType = "application/json",
    examples = {
        @ExampleObject(
            name = "newOrder",
            summary = "Đơn hàng mới",
            value = """
                {"status":"NEW"}
                """
        ),
        @ExampleObject(
            name = "cancelledOrder",
            summary = "Đơn hàng đã hủy",
            value = """
                {"status":"CANCELLED"}
                """
        )
    }
)
~~~

Các ví dụ cần đại diện cho những trường hợp client thực sự gặp. Tránh tạo nhiều ví dụ chỉ khác một giá trị vô nghĩa.

## 15. Khi nào dùng link thay vì chèn toàn bộ nội dung?

Nếu quy trình quá dài hoặc cần giải thích nhiều bước nghiệp vụ, description chỉ nên tóm tắt và liên kết tới tài liệu chuyên sâu.

~~~~markdown
### Quy trình thanh toán

1. Tạo payment intent.
2. Chuyển người dùng tới cổng thanh toán.
3. Nhận kết quả qua webhook.
4. Xác minh trạng thái trước khi hoàn tất đơn.

Xem [hướng dẫn tích hợp thanh toán](https://developer.example.com/payments)
để biết luồng đầy đủ và các tình huống retry.
~~~~

Liên kết cần ổn định, có quyền truy cập phù hợp và không trỏ tới tài liệu nội bộ mà client public không thể xem.

Không dùng link để thay thế thông tin thiết yếu cần có ngay tại operation. Client vẫn phải biết request tối thiểu, response chính và các lỗi quan trọng mà không cần mở nhiều trang khác.

## 16. Không lạm dụng HTML trong description

OpenAPI description hỗ trợ CommonMark. Một số renderer có thể xử lý một phần HTML, nhưng khả năng và chính sách sanitization khác nhau.

Không dựa vào raw HTML phức tạp để tạo layout. Tránh script, iframe, event handler hoặc nội dung có thể thực thi. Một số renderer sẽ loại bỏ hoặc escape nội dung đó; các renderer khác có thể xử lý khác nhau.

Ưu tiên Markdown heading, danh sách, link, fenced code và blockquote. Nếu cần một trang tài liệu có layout phong phú, hãy dùng developer portal hoặc website riêng thay vì biến operation description thành trang HTML nhúng.

Không đặt secret, token, thông tin cá nhân hoặc dữ liệu production trong description, code block hay example.

## 17. Bảng Markdown và khả năng tương thích renderer

Bảng rất hữu ích khi so sánh status code, parameter hoặc các trường hợp lỗi. Tuy nhiên, bảng Markdown kiểu GitHub Flavored Markdown không phải cú pháp cốt lõi của CommonMark.

Một số phiên bản Swagger UI hoặc renderer hỗ trợ bảng; một số công cụ khác có thể hiển thị không giống nhau. Nếu document cần tương thích với nhiều client, có thể thay bảng bằng danh sách có nhãn.

Ví dụ dạng danh sách dễ tương thích:

~~~~markdown
**200 — Thành công:** Trả về thông tin đơn hàng.

**404 — Không tìm thấy:** Mã đơn hàng không tồn tại.

**409 — Xung đột:** Đơn hàng không ở trạng thái cho phép cập nhật.
~~~~

Nếu dùng bảng, kiểm tra trên đúng Swagger UI version và các portal mà tổ chức hỗ trợ. Không dùng bảng lồng nhau hoặc bảng quá rộng khiến trang khó đọc trên màn hình nhỏ.

## 18. Giới hạn ký tự của description

OpenAPI Specification không đặt một giới hạn ký tự chung áp dụng cho mọi trường description. Tuy nhiên, điều đó không có nghĩa description nên dài tùy ý.

Giới hạn thực tế có thể đến từ:

- Kích thước OpenAPI JSON/YAML response.
- Reverse proxy hoặc API gateway response-size limit.
- Bộ nhớ và thời gian parse của trình duyệt.
- Hiệu năng render của Swagger UI.
- Khả năng tìm kiếm và cuộn trong operation dài.
- Hệ thống lưu trữ hoặc import document.
- Quy tắc nội bộ của API catalog.
- Trải nghiệm đọc trên màn hình nhỏ và hỗ trợ tiếp cận.

Không nên tự đặt một con số như 500 hoặc 1.000 ký tự rồi coi đó là giới hạn chuẩn OpenAPI. Nếu tổ chức có giới hạn nội bộ, hãy ghi rõ đó là governance rule và kiểm tra bằng lint rule riêng.

Giữ summary ngắn. Với description, chia nội dung theo heading, đưa payload sang example và chuyển quy trình chuyên sâu sang tài liệu liên kết.

## 19. Giới hạn hiển thị của Swagger UI

Swagger UI có thể thu gọn hoặc mở rộng operation và tag. Cấu hình mở rộng ảnh hưởng đến lượng nội dung hiển thị ngay khi tải trang.

Ví dụ:

~~~yaml
springdoc:
  swagger-ui:
    doc-expansion: none
~~~

Giá trị none giúp các operation ban đầu được thu gọn. Các lựa chọn mở rộng khác phụ thuộc property và version Swagger UI/Springdoc đang dùng.

Một số cấu hình giao diện khác có thể giúp người đọc tìm operation:

~~~yaml
springdoc:
  swagger-ui:
    filter: true
    display-operation-id: true
    operations-sorter: alpha
    tags-sorter: alpha
~~~

Hãy kiểm tra property reference của phiên bản Springdoc đang dùng trước khi áp dụng. Tên property trong YAML được ánh xạ tới cấu hình Swagger UI tương ứng.

Cấu hình doc expansion chỉ thay đổi cách giao diện mở operation. Nó không cắt bớt description trong OpenAPI document và không làm document nhỏ hơn.

## 20. Tổ chức description theo độ ưu tiên

Một operation description dễ đọc có thể theo cấu trúc:

1. Một hoặc hai câu nêu mục đích.
2. Điều kiện hoặc quyền cần có.
3. Quy tắc nghiệp vụ đặc biệt.
4. Quy trình gọi nếu có nhiều bước.
5. Các tình huống lỗi quan trọng.
6. Link tới tài liệu chuyên sâu nếu cần.

Không nhất thiết operation nào cũng cần đủ sáu phần. Một GET đơn giản có thể chỉ cần mục đích và một lưu ý về quyền truy cập.

Ví dụ:

~~~~markdown
Lấy trạng thái xử lý của một đơn hàng.

### Điều kiện

Người gọi phải có quyền xem đơn hàng thuộc tenant hiện tại.

### Kết quả

Trả về trạng thái hiện tại, thời điểm cập nhật gần nhất và mã đơn hàng.

### Lỗi

- 404: Không tìm thấy đơn hàng.
- 403: Không có quyền xem đơn hàng.
~~~~

Cấu trúc nhất quán giúp người dùng chuyển giữa nhiều operation mà không phải học lại cách đọc từng trang.

## 21. Giữ description đồng bộ với schema và runtime

Markdown có thể nói một điều nhưng schema hoặc runtime lại thể hiện điều khác. Ví dụ:

- Description nói parameter tùy chọn nhưng OpenAPI đánh dấu required.
- Description nói ngày giờ theo UTC nhưng JSON thực tế không có timezone.
- Description ghi status 201 nhưng controller trả 200.
- Code block dùng field cũ đã bị xóa khỏi DTO.
- Example dùng enum value không còn hợp lệ.
- Description hứa response có field mà Jackson đang loại bỏ.

Vì vậy, khi sửa description, hãy kiểm tra lại required, nullable, type, format, enum, validation constraints, media type, HTTP status, Jackson serialization và security requirement.

Nội dung giải thích cần mô tả đúng hành vi thực tế, không được trở thành một hợp đồng song song khác với OpenAPI schema.

## 22. Kiểm tra Markdown đã được Springdoc xuất ra

Sau khi chạy ứng dụng, tải OpenAPI JSON:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output target/openapi.json
~~~

Tìm operation và kiểm tra description trong document. Có thể dùng jq:

~~~bash
jq -r '.paths["/api/orders"].post.description' \
  target/openapi.json
~~~

Nếu description chứa newline, code fence hoặc Markdown, kiểm tra JSON đã escape đúng và nội dung sau khi parse vẫn giữ đúng dấu xuống dòng.

Không chỉ nhìn source annotation. Springdoc có thể kết hợp nhiều annotation/customizer, và kết quả cuối cùng trong document mới là thứ Swagger UI nhận.

Với nhiều document group, kiểm tra description trong từng endpoint group. Một customizer có thể áp dụng cho default document nhưng không áp dụng như mong muốn cho group.

## 23. Kiểm thử description bằng MockMvc

Có thể xác minh description được xuất ra trong OpenAPI JSON:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OperationDescriptionTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void shouldPublishOperationDescription() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/orders'].post.summary"
            ).value("Tạo đơn hàng"))
            .andExpect(jsonPath(
                "$.paths['/api/orders'].post.description"
            ).value(org.hamcrest.Matchers.containsString(
                "Điều kiện"
            )));
    }
}
~~~

JSONPath cần khớp path, method và nội dung thực tế. Nếu description có Markdown heading, test có thể xác minh một chuỗi đặc trưng thay vì so toàn bộ văn bản.

Có thể kiểm tra thêm example:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/orders'].post.responses['201']"
        + ".content['application/json'].examples.confirmedOrder.value.id"
    ).value("ORD-1001"));
~~~

Test này xác minh example có mặt trong document. Nó không chứng minh Swagger UI hiển thị đúng trên mọi trình duyệt; cần smoke test UI riêng nếu giao diện là sản phẩm được hỗ trợ.

## 24. Lỗi thường gặp khi hiển thị Markdown và code block

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Description hiển thị thành một đoạn dài | Thiếu dòng trống hoặc newline bị mất trong Java string | Dùng text block hoặc newline rõ ràng |
| Code fence không đóng | Thiếu delimiter hoặc delimiter lồng nhau bị trùng | Kiểm tra cặp mở/đóng và dùng delimiter ngoài dài hơn |
| JSON example không hiện trong Try it out | JSON nằm trong description thay vì OpenAPI examples | Dùng @ExampleObject hoặc schema example |
| Dấu nháy bị mất | Escape chuỗi Java sai | Kiểm tra giá trị sau khi Springdoc xuất document |
| Markdown table không render | Renderer không hỗ trợ extension bảng | Dùng danh sách CommonMark hoặc kiểm tra UI version |
| Link không hoạt động | URL tương đối hoặc sai origin | Dùng URL ổn định và kiểm tra browser |
| HTML bị loại bỏ | Renderer sanitization hoặc CSP | Dùng Markdown chuẩn thay raw HTML |
| Operation quá dài, khó đọc | Description chứa cả hướng dẫn tổng thể | Tách heading, examples và link |
| UI mở ra quá nhiều operation | Cấu hình doc expansion | Điều chỉnh doc-expansion |
| Summary bị cắt trong danh sách | Summary quá dài hoặc layout hẹp | Rút gọn summary, chuyển chi tiết vào description |
| Swagger UI không thấy nội dung mới | Đang đọc document group khác hoặc cache cũ | Kiểm tra endpoint và cache |
| Description không khớp DTO | Nội dung thủ công chưa cập nhật sau refactor | So sánh schema, example và runtime |

Khi debug, kiểm tra theo thứ tự: annotation Java, OpenAPI JSON, rồi giao diện Swagger UI. Như vậy có thể xác định lỗi nằm ở source string, document generation hay renderer.

## 25. Checklist trước khi hoàn thiện operation description

Trước khi commit mô tả operation:

- Summary ngắn và thể hiện hành động chính.
- Description giải thích mục đích và điều kiện sử dụng.
- Markdown dùng cú pháp CommonMark phổ biến.
- Heading có cấp bậc và không bị lạm dụng.
- Danh sách thể hiện điều kiện hoặc quy trình rõ ràng.
- Fenced code block có delimiter đóng đúng.
- Code block có nhãn ngôn ngữ khi phù hợp.
- Request/response sample dùng OpenAPI example khi cần tooling đọc.
- Example khớp schema và JSON runtime.
- Link ổn định và không dẫn tới nội dung ngoài audience.
- Không có secret, token hoặc dữ liệu cá nhân thật.
- Nội dung không lặp lại thông tin đã có trong schema.
- Description không quá dài và có heading nếu nhiều chủ đề.
- Swagger UI hiển thị đúng với document thực tế.
- CI kiểm tra document nếu operation là contract quan trọng.

## 26. Nguyên tắc viết Markdown và khối mã trong operation

Khi viết nội dung cho Springdoc OpenAPI:

1. Dùng summary cho nhãn ngắn và description cho hướng dẫn.
2. Dùng Markdown CommonMark để giữ nội dung tương thích giữa renderer.
3. Dùng heading, đoạn văn và danh sách để chia thông tin.
4. Dùng fenced code block cho request, response và lệnh minh họa.
5. Dùng @ExampleObject hoặc schema example cho dữ liệu mẫu có cấu trúc.
6. Không nhầm code block trong description với OpenAPI example.
7. Dùng Java text block cho description nhiều dòng nếu source level hỗ trợ.
8. Giữ description đồng bộ với schema, validation và runtime.
9. Không giả định OpenAPI có một giới hạn ký tự description cố định.
10. Kiểm soát độ dài theo khả năng đọc, kích thước document và renderer.
11. Dùng doc-expansion để điều chỉnh cách Swagger UI mở operation, không coi đó là giới hạn nội dung.
12. Kiểm tra OpenAPI JSON/YAML sau khi Springdoc sinh và test các operation quan trọng.

Một operation description tốt giúp người tích hợp hiểu cách dùng API mà không phải suy đoán từ tên method hoặc DTO. Markdown giải thích quy trình; schema và examples mô tả dữ liệu máy có thể xử lý. Khi hai phần được giữ đồng bộ và nội dung được kiểm tra trong document thực tế, Swagger UI sẽ trở thành một giao diện tài liệu rõ ràng, dễ tìm và đáng tin cậy.

## 27. Tài liệu tham khảo

- OpenAPI Specification — Description fields and CommonMark: https://spec.openapis.org/oas/latest.html
- Springdoc OpenAPI documentation: https://springdoc.org/
- Springdoc configuration properties: https://springdoc.org/properties.html
- Swagger UI configuration: https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/
- Swagger Core annotations: https://github.com/swagger-api/swagger-core

