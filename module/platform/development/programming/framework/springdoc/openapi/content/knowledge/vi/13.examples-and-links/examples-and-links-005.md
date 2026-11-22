# Tệp ví dụ bên ngoài và khả năng truy cập từ công cụ hiển thị

Ví dụ request và response giúp người tích hợp hiểu dữ liệu API mong đợi mà không phải tự đoán từ schema. Với payload nhỏ, có thể nhúng ví dụ trực tiếp vào tài liệu OpenAPI. Với payload lớn, nhiều định dạng hoặc cần chia sẻ cùng một mẫu cho nhiều endpoint, có thể lưu nội dung trong tệp riêng và tham chiếu bằng thuộc tính **externalValue** của Example Object.

Khi dùng springdoc-openapi, annotation **@ExampleObject** cho phép khai báo externalValue cùng tên, mô tả và phần tóm tắt. springdoc ghi tham chiếu này vào đặc tả được sinh; trình duyệt và công cụ hiển thị như Swagger UI chịu trách nhiệm truy cập URL của tệp. Vì vậy, một URL tồn tại trên máy chủ ứng dụng chưa đủ: URL phải truy cập được từ nơi công cụ hiển thị đang chạy và phiên bản renderer phải hỗ trợ cách tham chiếu đó.

## 1. Phân biệt ví dụ nhúng, externalValue và $ref

OpenAPI có nhiều cách cung cấp ví dụ. Ba cách dưới đây phục vụ các mục đích khác nhau:

| Cách khai báo | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| **example** | Một giá trị minh họa trực tiếp, gọn cho trường hợp đơn giản | Một giá trị mẫu duy nhất |
| **examples** với **value** | Một hoặc nhiều Example Object chứa dữ liệu ngay trong đặc tả | Cần nhiều mẫu có tên, mô tả hoặc ngữ cảnh |
| **examples** với **externalValue** | Example Object trỏ đến URL chứa nội dung mẫu thực tế | Payload lớn, XML, CSV, PDF, ảnh hoặc tệp được quản lý riêng |
| **examples** với **$ref** | Tham chiếu đến Example Object dùng lại trong **components.examples** hoặc tài liệu OpenAPI khác | Cần dùng lại cùng một ví dụ ở nhiều operation |

**externalValue** là URI trỏ đến nội dung ví dụ. Nó không phải đường dẫn đến một file trên ổ đĩa của máy chạy Spring Boot. Ví dụ **src/main/resources/static/examples/order.json** là đường dẫn nguồn trong dự án; URL mà công cụ cần truy cập có thể là **https://api.example.com/examples/order.json**.

Không nhầm **externalValue** với **$ref**. **$ref** dùng để tham chiếu một thành phần hoặc một phần của tài liệu OpenAPI; **externalValue** trỏ đến dữ liệu mẫu nguyên bản. Cách viết **value: { $ref: "./examples/order.json" }** không tải file JSON làm giá trị ví dụ. Muốn trỏ đến nội dung file, hãy dùng externalValue.

Trong Example Object, **value** và **externalValue** loại trừ lẫn nhau. Nếu khai báo cả hai, tài liệu không còn rõ nguồn dữ liệu và công cụ có thể bỏ qua một trường. Với ví dụ ngoài, chỉ khai báo externalValue cùng summary và description nếu cần.

Example Object có thể được đặt trong thuộc tính **examples** của Parameter Object, Header Object hoặc Media Type Object. Với tham số và header, ví dụ cần phản ánh giá trị đã được tuần tự hóa theo quy tắc truyền tương ứng. Ở các object này, trường **example** dạng đơn và **examples** dạng map cũng loại trừ lẫn nhau; hãy chọn một cách khai báo cho mỗi vị trí.

## 2. Đặt tệp mẫu ở đâu trong dự án Spring Boot?

Một cách đơn giản là lưu ví dụ trong thư mục static của ứng dụng:

~~~text
src/
  main/
    resources/
      static/
        examples/
          orders/
            create-order.json
            order-created.json
            validation-error.json
~~~

Với cấu hình tài nguyên tĩnh mặc định của Spring Boot, file **src/main/resources/static/examples/orders/create-order.json** có thể được phục vụ tại URL:

~~~text
https://api.example.com/examples/orders/create-order.json
~~~

Ví dụ nội dung create-order.json:

~~~json
{
  "customerId": "CUS-100",
  "items": [
    {
      "productId": "PRD-001",
      "quantity": 2
    },
    {
      "productId": "PRD-008",
      "quantity": 1
    }
  ],
  "note": "Giao hàng trong giờ hành chính"
}
~~~

File ví dụ được đóng gói cùng ứng dụng và có thể được phân phối qua static resource handler. Cần kiểm tra cấu hình **spring.web.resources** của dự án, vì ứng dụng có thể đã tắt static mapping hoặc đổi vị trí tài nguyên. Nếu Swagger UI được phục vụ từ một host khác, có thể lưu ví dụ trên web server hoặc object storage chuyên phục vụ tài liệu.

Không dùng đường dẫn filesystem như **C:\\project\\src\\main\\resources\\static\\examples\\orders\\create-order.json**, đường dẫn classpath như **classpath:/static/examples/...** hoặc URL **file://** trong externalValue. Trình duyệt của người dùng không thể đọc filesystem hay classpath bên trong máy chủ Spring Boot.

## 3. Khai báo externalValue trong OpenAPI YAML

Ví dụ sau mô tả request tạo đơn hàng bằng tệp JSON bên ngoài:

~~~yaml
paths:
  /api/orders:
    post:
      summary: Tạo đơn hàng
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
            examples:
              standardOrder:
                summary: Đơn hàng tiêu chuẩn
                description: Có hai sản phẩm và ghi chú giao hàng.
                externalValue: https://api.example.com/examples/orders/create-order.json
      responses:
        '201':
          description: Đã tạo đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
              examples:
                createdOrder:
                  summary: Đơn hàng đã được tạo
                  externalValue: https://api.example.com/examples/orders/order-created.json
~~~

Trong Media Type Object, **examples** là một map có tên. Mỗi tên như standardOrder hoặc createdOrder giúp người đọc nhận diện lựa chọn. Example Object có thể chứa summary, description, value hoặc externalValue. Nội dung ngoài nên tương thích với schema của media type tương ứng.

Một operation có thể có nhiều ví dụ:

~~~yaml
examples:
  standardOrder:
    summary: Đơn hàng tiêu chuẩn
    externalValue: https://api.example.com/examples/orders/create-order-standard.json
  giftOrder:
    summary: Đơn hàng có yêu cầu gói quà
    externalValue: https://api.example.com/examples/orders/create-order-gift.json
~~~

Các mẫu trên phải cùng tuân theo hợp đồng CreateOrderRequest. Nếu muốn minh họa request sai định dạng hoặc response lỗi, hãy đặt mẫu đó ở response lỗi với schema lỗi tương ứng; đừng gắn payload không hợp lệ vào schema request thành công nếu điều đó làm ví dụ mâu thuẫn với hợp đồng.

## 4. Dùng components.examples để tái sử dụng

Nếu một ví dụ được dùng ở nhiều operation, có thể khai báo một lần trong **components.examples** rồi tham chiếu bằng **$ref**:

~~~yaml
components:
  examples:
    CreatedOrder:
      summary: Đơn hàng đã được tạo
      description: Response thành công sau khi tạo đơn hàng.
      externalValue: https://api.example.com/examples/orders/order-created.json

    ValidationError:
      summary: Lỗi kiểm tra dữ liệu
      externalValue: https://api.example.com/examples/errors/validation-error.json

paths:
  /api/orders:
    post:
      responses:
        '201':
          description: Đã tạo đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
              examples:
                created:
                  $ref: '#/components/examples/CreatedOrder'
        '400':
          description: Dữ liệu không hợp lệ
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiError'
              examples:
                invalidRequest:
                  $ref: '#/components/examples/ValidationError'
~~~

**components.examples** chỉ chứa định nghĩa Example Object; operation sử dụng nó bằng **$ref**. Đây là tham chiếu tới Example Object trong tài liệu OpenAPI, khác với việc dùng externalValue để lấy nội dung file. Hai cơ chế có thể kết hợp: operation tham chiếu component, component lại chứa externalValue.

Khi cập nhật tệp ngoài, mọi operation dùng component đó sẽ hiển thị mẫu mới nếu URL vẫn giữ nguyên. Vì vậy, cần quản lý phiên bản của tệp ví dụ và tránh thay đổi nội dung theo cách phá vỡ hợp đồng mà không kiểm tra các nơi đang dùng.

## 5. Khai báo externalValue bằng annotation trong Spring Boot

**@ExampleObject** của swagger-annotations có các thuộc tính name, summary, description, value, externalValue và ref. Có thể gắn ví dụ vào request body hoặc response content.

Ví dụ khai báo request và response:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @PostMapping(
        value = "/api/orders",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    @Operation(
        summary = "Tạo đơn hàng",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            required = true,
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = CreateOrderRequest.class),
                examples = {
                    @ExampleObject(
                        name = "standardOrder",
                        summary = "Đơn hàng tiêu chuẩn",
                        description = "Mẫu JSON tạo đơn hàng có nhiều sản phẩm.",
                        externalValue = "https://api.example.com/examples/orders/create-order.json"
                    )
                }
            )
        )
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Đã tạo đơn hàng",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = OrderResponse.class),
                examples = {
                    @ExampleObject(
                        name = "createdOrder",
                        summary = "Đơn hàng đã được tạo",
                        externalValue = "https://api.example.com/examples/orders/order-created.json"
                    )
                }
            )
        )
    })
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        return ResponseEntity.status(201).body(orderService.create(request));
    }
}
~~~

Ví dụ dùng annotation RequestBody của Spring ở tham số method. Trong **@Operation**, phần request body dùng annotation của OpenAPI với tên đầy đủ **io.swagger.v3.oas.annotations.parameters.RequestBody** để tránh nhầm hai loại annotation cùng tên.

Nếu cần nhúng ví dụ nhỏ trực tiếp, có thể dùng value:

~~~java
@ExampleObject(
    name = "minimalOrder",
    summary = "Đơn hàng tối giản",
    value = "{\"customerId\":\"CUS-100\",\"items\":[{\"productId\":\"PRD-001\",\"quantity\":1}]}"
)
~~~

Không khai báo value cùng externalValue cho cùng một Example Object. Với externalValue, annotation chỉ ghi URL vào tài liệu; nó không tự chép file từ src/main/resources vào đặc tả và cũng không làm cho file tự động được phục vụ qua HTTP.

## 6. Định dạng tệp ví dụ và media type

Tệp ví dụ phải phù hợp với media type của request hoặc response. Một số trường hợp:

| Media type | Tệp ví dụ thường dùng | Lưu ý |
| --- | --- | --- |
| **application/json** | .json | Nội dung phải là JSON hợp lệ và khớp schema |
| **application/xml** | .xml | XML phải tuân theo cấu trúc và encoding đã công bố |
| **text/plain** | .txt | Chứa văn bản thuần, không bọc thêm JSON |
| **text/csv** | .csv | Header, delimiter và encoding cần nhất quán |
| **application/pdf** | .pdf | Dùng schema và media type mô tả nội dung nhị phân |
| **image/png**, **image/jpeg** | .png, .jpg | Renderer cần hỗ trợ cách hiển thị ảnh hoặc cung cấp liên kết tải |

Với JSON, ví dụ nên là payload thực tế mà client gửi hoặc nhận. Với XML hoặc CSV, cần giữ nguyên định dạng thay vì chuyển nội dung thành object JSON. Với PDF hoặc ảnh, externalValue trỏ đến tệp nhị phân; việc Swagger UI có hiển thị trực tiếp hay chỉ cho tải xuống phụ thuộc khả năng của renderer và media type.

Nếu API dùng multipart/form-data, ví dụ của từng phần có thể cần cấu hình encoding và content type riêng. Không giả định một file JSON bên ngoài có thể đại diện toàn bộ request multipart mà không mô tả cấu trúc các part.

## 7. Điều kiện để Swagger UI truy cập được tệp ngoài

externalValue được ghi vào tài liệu OpenAPI, nhưng Swagger UI phải truy cập URL của tệp từ trình duyệt. Hãy kiểm tra các điều kiện sau:

1. URL dùng giao thức mà môi trường cho phép, ưu tiên HTTPS khi trang tài liệu cũng chạy qua HTTPS.
2. URL công khai hoặc có quyền truy cập phù hợp từ trình duyệt của người dùng.
3. Request GET đến URL trả về 200 OK và nội dung file thực tế, không phải trang đăng nhập hoặc trang lỗi HTML.
4. Nếu file nằm khác origin với Swagger UI, máy chủ file phải cho phép CORS từ origin của Swagger UI.
5. Proxy, gateway, CDN hoặc WAF không chặn đường dẫn hay request lấy tệp.
6. Content-Type và nội dung phản hồi phù hợp với media type của ví dụ.
7. URL không yêu cầu token bí mật được nhúng trong OpenAPI hoặc một cookie mà trình duyệt không thể gửi.

Nếu Swagger UI và file mẫu cùng origin, ví dụ đều được phục vụ từ **https://api.example.com**, cấu hình CORS thường không cần thiết cho request tải file. Nếu Swagger UI ở **https://docs.example.com** còn file ở **https://api.example.com**, máy chủ file cần trả header CORS phù hợp, chẳng hạn:

~~~http
Access-Control-Allow-Origin: https://docs.example.com
~~~

Trong môi trường kiểm soát truy cập, chỉ cho phép origin tài liệu đã biết và phương thức GET cần thiết. Không mở CORS rộng hơn chính sách của tổ chức. Cũng cần kiểm tra Content Security Policy của trang tài liệu nếu chính sách connect-src giới hạn host mà trình duyệt được phép gọi.

Đừng dùng dữ liệu khách hàng thật, access token, thông tin thanh toán hoặc dữ liệu nội bộ nhạy cảm trong tệp ví dụ công khai. Tệp ở static resource hoặc CDN có thể được tải trực tiếp mà không qua quyền truy cập của endpoint nghiệp vụ.

## 8. URL tuyệt đối, URL tương đối và context path

OpenAPI cho phép URI tham chiếu, nhưng cách mỗi công cụ giải quyết URL tương đối có thể khác nhau. Swagger UI hiện liệt kê hỗ trợ đường dẫn tương đối của external files là giới hạn chưa được triển khai. Vì vậy, URL tuyệt đối thường dễ vận hành và dễ kiểm tra hơn:

~~~yaml
externalValue: https://api.example.com/examples/orders/create-order.json
~~~

Không nên mặc định URL sau sẽ được mọi renderer phân giải giống nhau:

~~~yaml
externalValue: ./examples/orders/create-order.json
~~~

URL tương đối có thể bị ảnh hưởng bởi base URL, servers, địa chỉ tài liệu OpenAPI, reverse proxy và phiên bản Swagger UI. Khi ứng dụng triển khai dưới context path như /store, URL tuyệt đối cần chứa đúng prefix công khai:

~~~text
https://api.example.com/store/examples/orders/create-order.json
~~~

Nếu nhiều môi trường có host khác nhau, có thể sinh đặc tả riêng cho từng môi trường hoặc dùng một host tài liệu ổn định để phân phối ví dụ. Tránh để URL trỏ về localhost, IP mạng riêng hoặc hostname chỉ tồn tại trong môi trường phát triển.

## 9. Khả năng hỗ trợ theo phiên bản công cụ

Đặc tả OpenAPI định nghĩa externalValue, nhưng khả năng tải và hiển thị nội dung phụ thuộc renderer:

| Công cụ / định dạng | Lưu ý |
| --- | --- |
| OpenAPI 3.1 và Swagger UI 5 | Swagger UI 5 hỗ trợ external examples trong định nghĩa OpenAPI 3.1; các bản mới hỗ trợ các phiên bản 3.1 hiện hành |
| OpenAPI 3.0.x và Swagger UI | Hỗ trợ externalValue đã có khác biệt giữa các phiên bản; cần kiểm tra đúng bản Swagger UI và cách phân giải của swagger-client |
| Swagger UI cũ | Có thể hiển thị URL hoặc trường trống thay vì nội dung file |
| Công cụ khác | Có thể đọc externalValue, chỉ hiển thị URL hoặc bỏ qua việc tải file |

Đặc biệt, tài liệu OpenAPI 3.1 không đồng nghĩa mọi renderer tự động hỗ trợ mọi khả năng của 3.1. Hãy kiểm tra trường openapi trong /v3/api-docs và phiên bản Swagger UI thực tế được đóng gói cùng starter hoặc được phục vụ từ CDN.

Nếu renderer không tải được external example, có thể giữ ví dụ trực tiếp trong tài liệu bằng components.examples:

~~~yaml
components:
  examples:
    CreatedOrder:
      summary: Đơn hàng đã được tạo
      value:
        id: 4201
        orderNumber: ORD-2026-0042
        status: CONFIRMED
~~~

Sau đó tham chiếu:

~~~yaml
examples:
  created:
    $ref: '#/components/examples/CreatedOrder'
~~~

Đây là phương án dự phòng tương thích rộng hơn vì dữ liệu mẫu nằm trong chính đặc tả. Nếu cần giữ tệp ngoài làm nguồn dữ liệu gốc, có thể tạo bước build để đồng bộ nội dung vào components.examples trước khi phân phối tài liệu.

## 10. Kiểm tra tệp mẫu và request từ trình duyệt

Kiểm tra riêng URL của tệp trước khi mở Swagger UI:

~~~bash
curl -i https://api.example.com/examples/orders/create-order.json
~~~

Xác nhận:

- Status là 200.
- Content-Type là application/json hoặc media type đúng với tệp.
- Body là nội dung JSON mong đợi, không phải HTML do login, proxy hoặc lỗi routing trả về.
- Tệp có thể tải từ mạng và origin mà người dùng Swagger UI đang sử dụng.

Sau đó mở /v3/api-docs và xác nhận externalValue đã được springdoc sinh đúng. Trong Swagger UI, mở Developer Tools, chọn tab Network và tải lại tài liệu. Lọc request theo tên file ví dụ để xem:

- Request URL có đúng host, context path và file name không.
- Request có bị chặn bởi CORS, CSP, TLS hoặc proxy không.
- Status và response body có đúng không.
- Trình duyệt có báo lỗi parse hoặc lỗi hiển thị không.

Cuối cùng, kiểm tra cả phần trình bày ví dụ lẫn thao tác Try it out. Một renderer có thể hiển thị liên kết nhưng không dùng được nội dung file để điền vào request body; hành vi này phụ thuộc phiên bản và plugin. Hãy gửi thử request trong môi trường kiểm thử và xác nhận payload được gửi đúng.

## 11. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Swagger UI hiển thị URL thay vì nội dung mẫu | Renderer không hỗ trợ hoặc chưa xử lý externalValue theo phiên bản OpenAPI đang dùng | Kiểm tra phiên bản Swagger UI và OpenAPI; dùng ví dụ inline nếu cần tương thích |
| Request tải file trả 404 | URL được tạo sai hoặc static resource không được phục vụ | Mở URL trực tiếp, kiểm tra static mapping và context path |
| Request tải file bị CORS | File và Swagger UI nằm khác origin | Cấu hình CORS trên máy chủ file cho origin tài liệu |
| Request trả 200 nhưng ví dụ là HTML | Proxy hoặc hệ thống xác thực chuyển hướng đến trang login/lỗi | Kiểm tra body và Content-Type; cấu hình đường dẫn file có thể truy cập phù hợp |
| URL hoạt động ở máy phát triển nhưng lỗi khi triển khai | Dùng localhost, hostname nội bộ hoặc prefix sai | Dùng URL công khai của môi trường triển khai |
| Tệp được tải nhưng ví dụ không phù hợp schema | File mẫu cũ hoặc payload không cùng hợp đồng | Validate tệp với schema và cập nhật mẫu cùng lúc với API |
| externalValue không có tác dụng khi dùng value: {$ref: ...} | Nhầm tham chiếu file với Reference Object | Dùng externalValue cho tệp dữ liệu hoặc $ref tới components.examples |
| Ví dụ biến mất khi nâng cấp Swagger UI | Khác biệt hỗ trợ OpenAPI 3.0/3.1 hoặc thay đổi renderer | Kiểm tra phiên bản UI, field openapi và Network request |
| Tệp mẫu lộ dữ liệu không nên công khai | Static resource hoặc CDN cho phép truy cập rộng | Dùng dữ liệu tổng hợp và rà soát quyền truy cập trước khi xuất bản |

## 12. Quy trình quản lý ví dụ bên ngoài

Để ví dụ luôn khớp với hợp đồng API, có thể áp dụng quy trình sau:

1. Xác định các request/response quan trọng cần minh họa và schema tương ứng.
2. Tạo tệp mẫu bằng dữ liệu tổng hợp, đặt tên rõ mục đích và định dạng.
3. Lưu tệp trong src/main/resources/static/examples hoặc kho phân phối tài liệu phù hợp.
4. Ghi URL truy cập được vào @ExampleObject(externalValue = "...") hoặc Example Object trong YAML.
5. Kiểm tra file URL, Content-Type, quyền truy cập và CORS từ origin Swagger UI.
6. Tải /v3/api-docs, xác nhận externalValue, rồi kiểm tra trên đúng phiên bản Swagger UI.
7. Validate payload mẫu với schema và kiểm thử Try it out trong môi trường phù hợp.
8. Khi thay đổi schema, cập nhật tệp ví dụ và kiểm tra các operation đang tái sử dụng component.

Nên dùng URL có phiên bản hoặc tên file bất biến khi ví dụ được lưu trên CDN. Ví dụ **examples/v1/orders/create-order.json** giúp người dùng tài liệu cũ tiếp tục nhận đúng nội dung. Nếu URL không đổi nhưng nội dung bị thay thế, cache của CDN hoặc trình duyệt có thể khiến một số người dùng thấy ví dụ cũ trong một khoảng thời gian.

## 13. Checklist trước khi công bố

- [ ] externalValue là URI trỏ đến nội dung mẫu thực tế.
- [ ] Example Object không khai báo đồng thời value và externalValue.
- [ ] Tệp mẫu có định dạng đúng với media type và khớp schema.
- [ ] URL dùng host và context path công khai, không dùng localhost hoặc filesystem path.
- [ ] Trình duyệt của người dùng Swagger UI có thể truy cập URL.
- [ ] CORS và CSP cho phép tải file khi cần.
- [ ] Phiên bản Swagger UI hỗ trợ cách dùng externalValue và phiên bản OpenAPI được xuất.
- [ ] Không chứa dữ liệu nhạy cảm trong ví dụ.
- [ ] Tệp có quy trình phiên bản hóa và cập nhật cùng hợp đồng API.
- [ ] Có phương án inline components.examples nếu renderer không tải được file ngoài.

## 14. Tài liệu tham khảo chính thức

- [OpenAPI Specification 3.1.2 — Example Object](https://spec.openapis.org/oas/v3.1.2.html#example-object) — value, externalValue, tính loại trừ lẫn nhau và cách sử dụng trong parameter/header/media type.
- [OpenAPI Specification 3.1.2 — Components Object](https://spec.openapis.org/oas/v3.1.2.html#components-object) — lưu trữ Example Object dùng lại trong components.examples.
- [Swagger Docs — Adding Examples](https://swagger.io/docs/specification/v3_0/adding-examples/) — ví dụ nhúng và external examples cho JSON, PDF và các media type khác.
- [Swagger UI — External Example Support](https://github.com/swagger-api/swagger-ui/issues/5433) — lịch sử hỗ trợ externalValue, khác biệt OpenAPI 3.0/3.1 và hành vi theo phiên bản Swagger UI.
- [Swagger UI — CORS](https://swagger.io/docs/open-source-tools/swagger-ui/usage/cors/) — các trường hợp cần bật CORS cho tài liệu và tài nguyên được tải từ origin khác.
- [Swagger Annotations — ExampleObject](https://docs.swagger.io/swagger-core/v2.2.25/apidocs/io/swagger/v3/oas/annotations/media/ExampleObject.html) — thuộc tính name, summary, description, value, externalValue và ref.
- [Springdoc-openapi — Introduction](https://springdoc.org/intro.html) — cách thư viện sinh OpenAPI từ cấu trúc và annotation của Spring Boot.

Tệp ví dụ bên ngoài giúp tài liệu gọn, dễ tái sử dụng và hỗ trợ những nội dung khó nhúng trực tiếp vào YAML/JSON. Giá trị của cách làm này phụ thuộc vào URL ổn định, quyền truy cập từ trình duyệt, CORS phù hợp và khả năng hỗ trợ của renderer. Hãy kiểm tra cả đặc tả OpenAPI lẫn hành vi Swagger UI trước khi xem ví dụ ngoài là một phần hoàn chỉnh của trải nghiệm tích hợp.
