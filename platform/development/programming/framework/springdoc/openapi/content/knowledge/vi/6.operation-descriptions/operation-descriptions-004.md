# operationId duy nhất, ổn định và ảnh hưởng đến bộ sinh mã phía gọi

Trong một tài liệu OpenAPI, mỗi operation có thể có trường <code>operationId</code> để định danh operation đó bằng một chuỗi. Trường này thường được các công cụ sinh client SDK dùng làm cơ sở đặt tên method, đồng thời có thể được tham chiếu từ những thành phần khác của đặc tả. Vì vậy, một <code>operationId</code> tốt cần duy nhất trong tài liệu, dễ hiểu và ổn định qua các lần thay đổi mã nguồn.

Khi dùng springdoc-openapi, có thể khai báo giá trị này trực tiếp bằng thuộc tính <code>operationId</code> của annotation <code>@Operation</code>. Cần xem nó như một phần của hợp đồng API công bố cho người tiêu thụ, thay vì chỉ là tên method Java nội bộ.

## 1. operationId là gì?

<code>operationId</code> là trường tùy chọn trong Operation Object của OpenAPI. Giá trị của nó là một chuỗi duy nhất dùng để định danh operation trong tài liệu.

~~~yaml
paths:
  /customers/{customerId}:
    get:
      operationId: getCustomerById
      summary: Lấy thông tin khách hàng
      responses:
        "200":
          description: Tìm thấy khách hàng
~~~

Trong ví dụ, operation được xác định bởi tổ hợp phương thức HTTP <code>GET</code> và đường dẫn <code>/customers/{customerId}</code>. Giá trị <code>getCustomerById</code> là tên định danh được công bố cho operation đó.

Phân biệt các thành phần:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| HTTP method | <code>GET</code> | Hành động HTTP của operation |
| Path | <code>/customers/{customerId}</code> | Địa chỉ tài nguyên |
| <code>operationId</code> | <code>getCustomerById</code> | Định danh duy nhất của operation trong tài liệu |
| <code>summary</code> | <code>Lấy thông tin khách hàng</code> | Tiêu đề ngắn cho người đọc |
| Tên method Java | <code>findCustomer</code> | Tên phương thức triển khai trong ứng dụng |

Các giá trị này phục vụ mục đích khác nhau. Đổi tên method Java không nhất thiết phải đổi <code>operationId</code>; đổi path cũng không bắt buộc phải đổi nó nếu operation vẫn đại diện cho cùng một hành động nghiệp vụ và hợp đồng được quản lý tương thích.

## 2. Quy tắc duy nhất trong tài liệu

Theo OpenAPI Specification, nếu khai báo <code>operationId</code>, giá trị đó phải là duy nhất trong tất cả operation của tài liệu API. Phạm vi duy nhất là toàn bộ tài liệu, không chỉ trong một path, controller hoặc tag.

Ví dụ sau bị trùng:

~~~yaml
paths:
  /customers:
    get:
      operationId: getResource
      responses:
        "200":
          description: OK
  /orders:
    get:
      operationId: getResource
      responses:
        "200":
          description: OK
~~~

Hai operation có path khác nhau nhưng cùng <code>operationId</code>. Tài liệu không đáp ứng yêu cầu duy nhất; công cụ sinh mã có thể báo lỗi, tạo tên method xung đột hoặc xử lý không nhất quán.

Ví dụ sửa:

~~~yaml
paths:
  /customers:
    get:
      operationId: listCustomers
      responses:
        "200":
          description: OK
  /orders:
    get:
      operationId: listOrders
      responses:
        "200":
          description: OK
~~~

Ngay cả khi tài liệu được chia thành nhiều nhóm bằng GroupedOpenApi, nên đặt tên nhất quán và tránh trùng giữa các nhóm nếu các đặc tả có thể được hợp nhất hoặc dùng chung một quy trình sinh SDK. Quy tắc bắt buộc của OpenAPI được áp dụng trên từng tài liệu được xuất.

## 3. Đặt operationId có ý nghĩa và dễ dùng

Nên dùng tên ngắn, mô tả hành động và đối tượng nghiệp vụ. Với hệ sinh thái Java, quy ước lower camel case thường dễ đọc:

| Hành động | operationId gợi ý |
|---|---|
| Liệt kê khách hàng | <code>listCustomers</code> |
| Lấy một khách hàng theo ID | <code>getCustomerById</code> |
| Tạo khách hàng | <code>createCustomer</code> |
| Cập nhật khách hàng | <code>updateCustomer</code> |
| Xóa khách hàng | <code>deleteCustomer</code> |
| Tìm đơn hàng | <code>searchOrders</code> |

Một quy ước đặt tên tốt thường có các đặc điểm:

- Bắt đầu bằng động từ thể hiện hành động như <code>get</code>, <code>list</code>, <code>create</code>, <code>update</code>, <code>delete</code> hoặc <code>search</code>.
- Nêu rõ đối tượng nghiệp vụ, chẳng hạn <code>Customer</code> hoặc <code>Order</code>.
- Dùng hậu tố có ý nghĩa khi cần phân biệt, ví dụ <code>getCustomerById</code> và <code>getCustomerByEmail</code>.
- Tránh tên chung chung như <code>getData</code>, <code>process</code>, <code>execute</code> hoặc tên phụ thuộc vào thứ tự endpoint.
- Tránh khoảng trắng, dấu câu và ký tự khó ánh xạ sang identifier của các ngôn ngữ lập trình.

OpenAPI yêu cầu giá trị là chuỗi duy nhất; quy ước lower camel case là lựa chọn thiết kế để cải thiện khả năng đọc và tương thích với code generator, không phải cú pháp bắt buộc của đặc tả.

## 4. Khai báo operationId bằng springdoc-openapi

Với Spring MVC hoặc Spring WebFlux dùng annotation controller, khai báo <code>operationId</code> trong <code>@Operation</code>:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/customers")
class CustomerController {

    @Operation(
        operationId = "getCustomerById",
        summary = "Lấy thông tin khách hàng theo ID"
    )
    @GetMapping("/{customerId}")
    CustomerResponse getCustomer(
            @PathVariable String customerId) {
        // Tìm và trả về khách hàng
        return new CustomerResponse(customerId, "Lan");
    }
}

record CustomerResponse(String id, String name) {}
~~~

Khi springdoc tạo tài liệu, operation tương ứng sẽ có metadata gần như sau:

~~~yaml
paths:
  /customers/{customerId}:
    get:
      operationId: getCustomerById
      summary: Lấy thông tin khách hàng theo ID
      parameters:
        - name: customerId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: OK
~~~

Ví dụ tập trung vào vị trí khai báo; nội dung response thực tế phụ thuộc DTO và annotation của ứng dụng. Nếu bỏ <code>operationId</code>, springdoc có thể tạo giá trị từ metadata của handler. Cách tạo mặc định có thể phụ thuộc phiên bản và cấu trúc controller, do đó nên khai báo tường minh cho những operation là một phần của SDK hoặc hợp đồng công khai.

## 5. Tên operationId tác động đến code generator như thế nào?

Nhiều công cụ sinh mã client dùng <code>operationId</code> làm cơ sở đặt tên hàm trong SDK. Cách chuyển đổi cụ thể tùy generator, ngôn ngữ và cấu hình, nhưng có thể hình dung:

| operationId trong OpenAPI | Tên method có thể được sinh |
|---|---|
| <code>listCustomers</code> | <code>listCustomers()</code> |
| <code>getCustomerById</code> | <code>getCustomerById(id)</code> |
| <code>createCustomer</code> | <code>createCustomer(request)</code> |
| <code>deleteCustomer</code> | <code>deleteCustomer(id)</code> |

Ví dụ, client SDK Java có thể cung cấp lời gọi:

~~~java
Customer customer = customerApi.getCustomerById("C-100");
~~~

Nếu đội backend đổi <code>operationId</code> từ <code>getCustomerById</code> thành <code>fetchCustomer</code> nhưng giữ nguyên HTTP method và path, client SDK được sinh lại có thể đổi tên method tương ứng. Ứng dụng tiêu thụ SDK có thể không biên dịch cho đến khi mã gọi được cập nhật.

Do đó, thay đổi <code>operationId</code> có thể là thay đổi tương thích ở cấp source code của SDK, dù endpoint HTTP vẫn hoạt động như trước. Với SDK được phát hành cho khách hàng hoặc nhiều nhóm nội bộ, cần quản lý thay đổi này như một phần của phiên bản hợp đồng.

Ngoài tên method, một số công cụ dùng <code>operationId</code> để tạo tên biến, tên hàm trong tài liệu, tên operation trong telemetry hoặc ánh xạ liên kết. Cần kiểm tra đầu ra của generator cụ thể thay vì giả định mọi công cụ đều ánh xạ giống nhau.

## 6. Giữ operationId ổn định qua các lần refactor

Khi operation vẫn đại diện cho cùng hành động nghiệp vụ, nên giữ nguyên <code>operationId</code> dù tên method Java hoặc cách tổ chức controller thay đổi.

Ví dụ trước refactor:

~~~java
@Operation(operationId = "getCustomerById")
@GetMapping("/{id}")
CustomerResponse findCustomer(@PathVariable String id) {
    // ...
}
~~~

Sau khi đổi tên method nội bộ:

~~~java
@Operation(operationId = "getCustomerById")
@GetMapping("/{customerId}")
CustomerResponse loadCustomer(@PathVariable String customerId) {
    // ...
}
~~~

Trong ví dụ, method Java và tên biến path đã thay đổi, nhưng định danh công khai vẫn ổn định. Điều này giúp generator tiếp tục tạo method client cùng tên nếu các phần khác của hợp đồng không làm thay đổi chữ ký.

Giữ ổn định không có nghĩa giữ một tên cũ cho một hành động đã đổi ý nghĩa. Nếu operation được thay thế bằng hành vi nghiệp vụ khác, hãy xác định đó là operation mới và chọn định danh mới. Nếu cần ngừng operation cũ, có thể đánh dấu deprecated trong đặc tả, duy trì trong giai đoạn chuyển tiếp rồi loại bỏ theo chính sách tương thích.

### 6.1. Thay đổi nào nên giữ operationId?

| Thay đổi nội bộ hoặc hợp đồng | Hướng xử lý thường phù hợp |
|---|---|
| Đổi tên method Java nhưng hành động không đổi | Giữ nguyên |
| Chuyển method sang controller khác | Giữ nguyên nếu vẫn là cùng operation |
| Đổi tên biến <code>@PathVariable</code> | Giữ nguyên nếu hành động không đổi |
| Thay đổi implementation hoặc service được gọi | Giữ nguyên nếu hành vi hợp đồng không đổi |
| Đổi path nhưng giữ cùng hành động và có kế hoạch tương thích | Có thể giữ nguyên; đánh giá riêng breaking change của URL |
| Operation mới có mục đích khác | Tạo operationId mới |
| Xóa operation cũ và thay bằng operation khác | Quản lý deprecation/removal và định danh mới theo chính sách phiên bản |

### 6.2. operationId cũng có thể được tham chiếu trong OpenAPI Link

OpenAPI Link Object có thể dùng trường <code>operationId</code> để tham chiếu một operation khác. Ví dụ, response tạo đơn hàng có thể liên kết đến operation lấy đơn hàng vừa tạo:

~~~yaml
responses:
  "201":
    description: Đã tạo đơn hàng
    links:
      GetCreatedOrder:
        operationId: getOrderById
        parameters:
          orderId: "$response.body#/id"
~~~

Trong trường hợp này, <code>getOrderById</code> phải khớp với <code>operationId</code> của operation đích trong tài liệu. Đổi tên operationId mà không cập nhật các Link tham chiếu có thể làm hỏng liên kết trong hợp đồng.

## 7. Tránh xung đột khi có nhiều controller

Với ứng dụng lớn, nhiều controller có thể cùng khai báo method Java tên <code>getById</code>. Nếu để springdoc tự suy ra định danh, cấu trúc handler có thể dẫn đến giá trị không mong muốn hoặc khó duy trì. Nên chọn quy ước có tên tài nguyên để tránh trùng:

~~~java
@Operation(operationId = "getCustomerById")
@GetMapping("/customers/{id}")
CustomerResponse getCustomerById(@PathVariable String id) {
    // ...
}

@Operation(operationId = "getOrderById")
@GetMapping("/orders/{id}")
OrderResponse getOrderById(@PathVariable String id) {
    // ...
}
~~~

Nếu API có nhiều nhóm hoặc nhiều phiên bản, hãy cân nhắc cách các tài liệu được tiêu thụ:

- Mỗi tài liệu OpenAPI xuất riêng phải không có operationId trùng trong phạm vi tài liệu đó.
- Nếu nhiều nhóm được hợp nhất thành một tài liệu hoặc dùng chung một SDK, hãy đảm bảo operationId không va chạm sau khi hợp nhất.
- Không dùng tên tag làm cơ chế duy nhất để phân biệt operationId; tag không mở rộng phạm vi duy nhất của trường này.

## 8. Kiểm tra operationId trong tài liệu sinh ra

Sau khi khai báo annotation, kiểm tra đặc tả tại endpoint mặc định:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Trong JSON, tìm các trường <code>operationId</code> bên dưới từng HTTP operation. Với tài liệu lớn, có thể dùng <code>jq</code> để liệt kê:

~~~bash
curl -s http://localhost:8080/v3/api-docs |
  jq -r '.paths | to_entries[] | .key as $path |
    .value | to_entries[] |
    select(.value.operationId != null) |
    [$path, .key, .value.operationId] | @tsv'
~~~

Kết quả giúp đối chiếu path, HTTP method và operationId. Sau đó, xác minh các điều sau:

1. Mọi operation cần định danh đều có <code>operationId</code>.
2. Không có hai operation nào dùng cùng một giá trị trong cùng tài liệu.
3. Tên phản ánh hành động và tài nguyên.
4. Các giá trị không thay đổi ngoài dự kiến sau khi đổi tên method hoặc chuyển controller.
5. Link Object có tham chiếu đến operationId thì vẫn trỏ đúng operation.
6. Client SDK được sinh ra có tên method và chữ ký mong đợi.

Khi API là đầu vào của code generation, nên lưu đặc tả OpenAPI đã phát hành và so sánh với bản mới trong CI. Có thể đặt kiểm tra uniqueness và thay đổi operationId thành một bước kiểm tra hợp đồng trước khi phát hành.

## 9. Danh sách rà soát trước khi phát hành

- [ ] Mỗi operation công khai có <code>operationId</code> tường minh.
- [ ] Các giá trị duy nhất trên toàn bộ operation của từng tài liệu.
- [ ] Tên dùng động từ và tên tài nguyên có ý nghĩa.
- [ ] Không phụ thuộc vào tên method Java hoặc thứ tự khai báo controller.
- [ ] Refactor nội bộ không làm thay đổi định danh công khai ngoài dự kiến.
- [ ] Đã rà soát Link Object và các tham chiếu dùng operationId.
- [ ] Đã sinh thử client SDK để xác nhận tên method.
- [ ] Thay đổi operationId được xem xét trong đánh giá tương thích và phiên bản hợp đồng.

## Tài liệu tham khảo

- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object): quy tắc và ý nghĩa của <code>operationId</code>.
- [OpenAPI Specification – Link Object](https://spec.openapis.org/oas/latest.html#link-object): tham chiếu operation bằng <code>operationId</code>.
- [springdoc-openapi – Getting Started](https://springdoc.org/getting-started.html): tích hợp springdoc-openapi với Spring Boot.
- [Swagger Core – Operation annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/Operation.html): thuộc tính <code>operationId</code> của annotation <code>@Operation</code>.
- [OpenAPI Generator](https://openapi-generator.tech/docs/): cách công cụ sinh client/server từ tài liệu OpenAPI và các tùy chọn generator.
