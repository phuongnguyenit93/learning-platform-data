# PUT tạo mới, cập nhật và xử lý trường bị thiếu

## Mục tiêu bài học

Trong chương **HTTP Methods** của module **INTEGRATION_API_REST**, bài học này tập trung vào cách thiết kế một thao tác PUT dựa trên resource, URI và hợp đồng dữ liệu. Sau khi học, bạn có thể:

- Quyết định một endpoint PUT được phép tạo resource mới hay chỉ thay thế resource đã tồn tại.
- Phân biệt trường bị thiếu, trường mang giá trị `null`, chuỗi rỗng và danh sách rỗng.
- Thiết kế DTO và logic Java/Spring không vô tình biến PUT thành cập nhật từng phần.
- Chọn mã trạng thái, áp dụng điều kiện chống ghi đè và mô tả hành vi bằng OpenAPI.
- Xác định các tình huống cần kiểm thử khi một request được gửi lại hoặc nhiều client cùng cập nhật.

Ví dụ xuyên suốt là resource sản phẩm tại `/products/{productId}`. Các chính sách cụ thể về trường dữ liệu trong bài là **hợp đồng của API ví dụ**, cần được triển khai và công bố; chúng không tự xuất hiện chỉ vì controller có annotation `@PutMapping`.

## 1. Hiểu đúng ý định của PUT

PUT yêu cầu tạo hoặc thay thế trạng thái tại URI đích bằng trạng thái mà biểu diễn gửi lên mô tả. Tạo thành công trả `201`; thay thế thành công trả `200` hoặc `204`. Đây là ngữ nghĩa nền tảng của phương thức. [RFC 9110, mục 9.3.4](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.4).

~~~http
PUT /products/P100 HTTP/1.1
Host: api.example.test
Content-Type: application/json

{
  "name": "Bàn phím cơ",
  "price": 1290000,
  "description": "Kết nối USB-C",
  "tags": ["keyboard", "wired"],
  "active": true
}
~~~

Client đang yêu cầu: “Hãy đặt phần trạng thái sản phẩm mà tôi được phép ghi tại `/products/P100` thành trạng thái này”.

Điều đó khác với yêu cầu “tăng giá thêm 100000” hoặc “chỉ sửa trường name”. Trong ví dụ này, `price` là mức giá cuối cùng cần có, không phải số tiền cộng thêm.

### 1.1. Resource không đồng nhất với một hàng database

Biểu diễn ghi của sản phẩm gồm `name`, `price`, `description`, `tags`, `active`. Biểu diễn đọc có thể chứa thêm:

~~~json
{
  "id": "P100",
  "name": "Bàn phím cơ",
  "price": 1290000,
  "description": "Kết nối USB-C",
  "tags": ["keyboard", "wired"],
  "active": true,
  "createdAt": "2026-11-01T08:00:00Z",
  "updatedAt": "2026-11-17T03:00:00Z"
}
~~~

Việc thay thế phần trạng thái cho phép ghi không có nghĩa là xóa hàng cũ, chèn hàng mới, đổi khóa chính hoặc xóa `createdAt`. Server vẫn quản lý metadata và các ràng buộc lưu trữ.

Nếu giá và tồn kho thuộc những quy trình nghiệp vụ khác nhau, có thể tách resource, chẳng hạn `/products/P100/pricing`. Khi đó PUT tác động đến toàn bộ trạng thái ghi của resource định giá được công bố tại URI này, không mặc nhiên thay thế mọi thuộc tính sản phẩm.

### 1.2. URI xác định đối tượng đích

Ở `PUT /products/P100`, định danh đích đã có trước khi request được xử lý. Client có thể dùng mã nghiệp vụ hoặc UUID đã chọn, nếu server cho phép.

Trong API ví dụ, body không có `id`; URI là nguồn xác định sản phẩm. Nếu API khác cho phép body chứa `id`, phải kiểm tra nó khớp URI và công bố cách báo lỗi khi không khớp.

Khi server chịu trách nhiệm cấp định danh và chọn URI mới, `POST /products` thường phù hợp hơn. Một thao tác SQL tên “upsert” không đủ để quyết định HTTP method; cần bắt đầu từ ý định của client và hợp đồng resource.

## 2. PUT có được tạo mới không?

Khả năng tạo mới cần được xác định rõ cho từng endpoint.

| Chính sách endpoint | URI chưa có resource | URI đã có resource |
| --- | --- | --- |
| Cho phép tạo hoặc thay thế | Tạo tại URI đích nếu hợp lệ và có quyền; trả `201 Created` | Thay thế phần trạng thái ghi; trả `200 OK` hoặc `204 No Content` |
| Chỉ cho phép thay thế | Không tạo; API ví dụ chọn `404 Not Found` | Thay thế nếu hợp lệ và có quyền |
| Tạo khi chưa tồn tại bằng điều kiện HTTP | Gửi `If-None-Match: *`; tạo thành công trả `201` | Điều kiện không thỏa; trả `412 Precondition Failed` |

`404` ở dòng thứ hai là chính sách cho một resource chưa tồn tại, không phải bằng chứng PUT không thể tạo mới. Nếu URI tồn tại nhưng không hỗ trợ PUT, `405 Method Not Allowed` cùng header `Allow` phù hợp với tình huống khác đó.

### 2.1. Ví dụ tạo mới

Giả sử endpoint cho phép tạo hoặc thay thế và `P100` chưa tồn tại. Sau request đầy đủ ở trên, server có thể trả:

~~~http
HTTP/1.1 201 Created
Location: /products/P100
Content-Type: application/json

{
  "id": "P100",
  "name": "Bàn phím cơ",
  "price": 1290000,
  "description": "Kết nối USB-C",
  "tags": ["keyboard", "wired"],
  "active": true,
  "createdAt": "2026-11-17T03:00:00Z",
  "updatedAt": "2026-11-17T03:00:00Z"
}
~~~

Header `Location` trong ví dụ chỉ rõ URI sản phẩm vừa tạo. Server không tự chuyển sang tạo `P101` để né xung đột với `P100`.

### 2.2. Ví dụ thay thế

Khi `P100` đã tồn tại, cùng endpoint có thể trả `200 OK` với biểu diễn kết quả. Nếu hợp đồng chọn không trả nội dung, dùng:

~~~http
HTTP/1.1 204 No Content
~~~

Response `204` không có body JSON. Quyết định dùng `200` hay `204` nên ổn định để client biết có cần đọc body.

## 3. Trường bị thiếu: phần cần thiết kế kỹ nhất

HTTP không đưa ra một quy tắc chung rằng mọi thuộc tính JSON vắng mặt đều phải thành `null`, cũng không định nghĩa cách ánh xạ JSON sang database. Với PUT thay thế, API cần mô tả được trạng thái cuối cùng từ body và các mặc định của hợp đồng.

Trong bài này, hợp đồng ghi sản phẩm được chọn như sau:

| Trường | Quyền ghi | Khi bị thiếu | Khi là `null` | Khi có giá trị |
| --- | --- | --- | --- | --- |
| `name` | Client | Từ chối `400` | Từ chối `400` | Chuỗi không trắng, tối đa 120 ký tự |
| `price` | Client | Từ chối `400` | Từ chối `400` | Số thập phân lớn hơn 0 |
| `active` | Client | Từ chối `400` | Từ chối `400` | Boolean; `false` là hợp lệ |
| `description` | Client | Đặt thành `null` | Đặt thành `null` | Chuỗi tối đa 2000 ký tự; chuỗi rỗng được chấp nhận |
| `tags` | Client | Đặt thành `[]` | Đặt thành `[]` | Thay thế toàn bộ danh sách, tối đa 20 phần tử không trắng |
| `id`, `createdAt`, `updatedAt` | Server | Server quản lý | Từ chối nếu xuất hiện trong body | Từ chối nếu xuất hiện trong body |

API cũng từ chối thuộc tính body không được khai báo. Đây là lựa chọn giúp phát hiện lỗi tên trường và tránh client tưởng rằng trường đã được ghi dù server bỏ qua.

Điểm quyết định: **trường tùy chọn bị thiếu không được âm thầm giữ giá trị cũ trong hợp đồng này**. Nếu nhận `description` bị thiếu rồi giữ mô tả cũ, kết quả phụ thuộc dữ liệu trước đó, trái với quy tắc thay thế mà API đang hứa.

### 3.1. Ví dụ trạng thái trước và sau

Trước khi cập nhật, sản phẩm có:

~~~json
{
  "name": "Bàn phím cũ",
  "price": 990000,
  "description": "Bảo hành 12 tháng",
  "tags": ["sale", "wired"],
  "active": true
}
~~~

Client gửi:

~~~http
PUT /products/P100 HTTP/1.1
Host: api.example.test
Content-Type: application/json

{
  "name": "Bàn phím mới",
  "price": 1190000,
  "active": false
}
~~~

Sau khi thay thế theo hợp đồng:

~~~json
{
  "name": "Bàn phím mới",
  "price": 1190000,
  "description": null,
  "tags": [],
  "active": false
}
~~~

Client đã không gửi mô tả và danh sách nhãn. Server xóa mô tả, làm rỗng danh sách nhãn, đồng thời gán `active` thành `false`. Metadata do server quản lý được xử lý riêng.

Một UI chỉ hiển thị tên và giá không nên lấy hai trường đó gửi PUT vào hợp đồng này nếu người dùng vẫn muốn giữ mô tả và nhãn. UI cần lấy đầy đủ trạng thái ghi, dùng cơ chế cập nhật từng phần phù hợp, hoặc thao tác với một resource hẹp hơn được thiết kế rõ ràng.

### 3.2. Thiếu, null và rỗng là ba tình huống khác nhau

~~~json
{}
~~~

Không có thuộc tính `description`.

~~~json
{
  "description": null
}
~~~

Có thuộc tính `description` và giá trị là JSON null.

~~~json
{
  "description": ""
}
~~~

Có thuộc tính `description` và giá trị là chuỗi rỗng.

Ba body trên chỉ minh họa một trường; chúng chưa phải request sản phẩm hợp lệ vì thiếu các trường bắt buộc.

Trong hợp đồng ví dụ, hai tình huống đầu được chủ động quy về cùng kết quả `description = null`; tình huống thứ ba lưu chuỗi rỗng. API khác có thể cấm chuỗi rỗng hoặc chuẩn hóa nó về `null`, nhưng phải công bố và kiểm thử lựa chọn đó.

Đối với trường bắt buộc, “có mặt” và “được phép null” cũng là hai quy tắc độc lập. Một schema yêu cầu thuộc tính tồn tại chưa chắc đã cấm nó mang giá trị null.

### 3.3. Khi cần phân biệt thiếu và null trong Java

Một DTO thông thường với `String description` thường nhận `null` cho cả thuộc tính bị thiếu lẫn thuộc tính được gửi là null. Cách này đủ cho hợp đồng ví dụ vì cả hai có cùng hành vi.

Nếu hợp đồng yêu cầu `description` phải có mặt nhưng cho phép gửi null để xóa, chỉ một trường Java nullable không đủ. Cần biểu diễn trạng thái “đã xuất hiện” bằng cấu trúc riêng, custom deserializer hoặc đọc cây JSON trước khi ánh xạ. Với Jackson `JsonNode`, có thể phân biệt:

~~~java
boolean present = body.has("description");
boolean explicitNull = present && body.get("description").isNull();
~~~

Chỉ dùng `hasNonNull` sẽ không tách được trường hợp thiếu và null. Cơ chế kiểm tra presence phải đi cùng validation hợp đồng, không thay thế validation kiểu dữ liệu.

## 4. Object lồng nhau và collection cũng cần quy tắc

Giả sử mở rộng hợp đồng bằng object `shipping`, trong đó `weightGrams` và `fragile` là hai thuộc tính bắt buộc. Nếu client gửi:

~~~json
{
  "shipping": {
    "weightGrams": 800
  }
}
~~~

Một hợp đồng thay thế yêu cầu đầy đủ object phải từ chối vì thiếu `fragile`; không tự lấy giá trị `fragile` từ object cũ. Nếu cho phép thiếu `fragile` với mặc định `false`, phải công bố mặc định và áp dụng nó nhất quán.

Đây là ví dụ mở rộng riêng; schema sản phẩm cơ bản trong bài chưa chấp nhận `shipping`.

Với collection:

- `tags: ["new"]` thay danh sách cũ bằng danh sách chỉ có `"new"`.
- `tags: []` làm danh sách rỗng.
- Thiếu `tags` và `tags: null` đều làm danh sách rỗng theo bảng hợp đồng.
- Không tự thêm phần tử mới vào danh sách cũ; nếu cần thao tác thêm/xóa một phần tử, thiết kế request khác phù hợp.

Việc thay thế một collection trong resource không tự cho phép xóa mọi bản ghi liên quan trong database. Cần xác định quan hệ sở hữu: xóa liên kết sản phẩm–nhãn khác với xóa nhãn dùng chung cho tất cả sản phẩm.

## 5. Lũy đẳng giúp gửi lại request, không giải quyết mọi vấn đề

Với cùng URI và cùng trạng thái mong muốn, gửi lại PUT không được tạo thêm sản phẩm hoặc tiếp tục cộng giá. Chẳng hạn hai lần gửi `price: 1190000` cùng đặt giá về 1190000. Đó là cách áp dụng tính lũy đẳng vào hợp đồng này.

~~~text
Gửi lần 1: /products/P100 chưa tồn tại -> tạo P100 -> 201
Gửi lần 2: /products/P100 đã tồn tại  -> thay thế P100 -> 200
Trạng thái nghiệp vụ mong muốn: vẫn chỉ một P100 với dữ liệu đã gửi
~~~

Response không cần giống nhau từng byte. Access log, audit record hoặc metadata xử lý có thể khác; chúng không biến PUT thành lời hứa chỉ thực thi đúng một lần. Tuy nhiên, không nên gửi thêm một email xác nhận đơn hàng hay trừ tiền thêm mỗi lần lặp lại thao tác đặt cùng trạng thái. Các hiệu ứng nghiệp vụ đó cần được thiết kế và chống lặp riêng.

Ví dụ triển khai sai:

~~~java
product.setPrice(product.getPrice().add(request.price()));
~~~

Đoạn code này hiểu `price` là số tiền tăng thêm. Gửi lại cùng body sẽ tăng giá thêm lần nữa.

Cách gán phù hợp với hợp đồng:

~~~java
product.setPrice(request.price());
~~~

Client gặp timeout không biết request trước đã commit hay chưa. Có thể gửi lại PUT với cùng URI và nội dung khi điều kiện và nghiệp vụ cho phép, nhưng cần backoff, giới hạn retry và xử lý lỗi. Không tự retry mãi một request sai validation.

Tính lũy đẳng cũng không hứa giữ nguyên kết quả nếu một client khác đã ghi xen giữa. Muốn tránh ghi đè trạng thái mới của người khác, cần điều kiện cập nhật.

## 6. Tránh lost update bằng điều kiện HTTP

### 6.1. Ghi khi phiên bản đang đọc vẫn còn hiện hành

Giả sử GET trả một strong ETag:

~~~http
HTTP/1.1 200 OK
ETag: "product-P100-v7"
Content-Type: application/json

{
  "id": "P100",
  "name": "Bàn phím cơ",
  "price": 1290000,
  "description": null,
  "tags": [],
  "active": true
}
~~~

Client gửi trạng thái mới kèm điều kiện:

~~~http
PUT /products/P100 HTTP/1.1
Host: api.example.test
Content-Type: application/json
If-Match: "product-P100-v7"

{
  "name": "Bàn phím cơ",
  "price": 1190000,
  "description": null,
  "tags": [],
  "active": true
}
~~~

`If-Match` dùng so sánh mạnh. Trong chính sách ví dụ, phiên bản không khớp dẫn đến `412` và không ghi dữ liệu. `If-Match: *` chỉ kiểm tra đang có biểu diễn, không phát hiện thay đổi phiên bản. [RFC 9110, mục 13.1.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1).

Kiểm tra ETag và ghi cần nằm trong một cơ chế nguyên tử: transaction với khóa phù hợp hoặc cập nhật có điều kiện theo version. Kiểm tra trong controller rồi ghi độc lập vẫn để lại khoảng trống cho request khác chen vào. Optimistic locking bằng `@Version` có thể hỗ trợ phát hiện xung đột, nhưng không tự đọc header HTTP hay tự ánh xạ mọi xung đột thành `412`.

Sau `412`, client đọc lại resource, cho người dùng xử lý khác biệt rồi gửi ý định cập nhật mới. Không xóa `If-Match` và gửi lại một cách máy móc.

### 6.2. Chỉ tạo khi chưa tồn tại

~~~http
PUT /products/P100 HTTP/1.1
Host: api.example.test
Content-Type: application/json
If-None-Match: *

{
  "name": "Bàn phím cơ",
  "price": 1290000,
  "active": true
}
~~~

`If-None-Match: *` ngăn PUT thay thế resource đã có; điều kiện không thỏa trả `412`. [RFC 9110, mục 13.1.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.2).

Hai client cùng tạo `P100` cần được phân xử nguyên tử ở tầng lưu trữ. Thao tác “SELECT thấy chưa có, sau đó INSERT” thiếu bảo vệ có thể chạy đua; khóa duy nhất của định danh vẫn cần thiết.

Nếu lần tạo đã thành công nhưng response bị mất, gửi lại request có điều kiện này có thể nhận `412`. Client cần đọc và đối chiếu resource; không được suy ra lần đầu chắc chắn thất bại. Mã trạng thái lần gửi lại khác đi không làm mất tính lũy đẳng của ý định tạo.

### 6.3. Không tùy tiện trả ETag trong response PUT

Nếu server biến đổi representation nhận được, không phát validator như `ETag` trong response PUT thành công. Client có thể GET lại để lấy representation và validator hiện tại. [RFC 9110, mục 9.3.4](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.4).

Ví dụ sản phẩm bổ sung metadata và chuẩn hóa trường thiếu, nên các response PUT minh họa không gắn ETag. Header `If-Match` cho lần ghi tiếp theo có thể lấy từ GET.

## 7. Minh họa Java/Spring: DTO thay thế và ánh xạ rõ ràng

Các đoạn code dưới đây mô tả lớp HTTP và cách tạo trạng thái thay thế, dùng Java hỗ trợ record, Spring MVC và Jakarta Bean Validation. Đây không phải ứng dụng hoàn chỉnh; repository, transaction, phân quyền và cơ chế điều kiện HTTP cần được triển khai thêm.

### 7.1. DTO đầu vào tách khỏi entity

~~~java
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.util.List;

public record ReplaceProductRequest(
        @NotBlank
        @Size(max = 120)
        String name,

        @NotNull
        @DecimalMin(value = "0", inclusive = false)
        BigDecimal price,

        @Size(max = 2000)
        String description,

        @Size(max = 20)
        List<@NotBlank String> tags,

        @NotNull
        Boolean active
) {}
~~~

`Boolean` đi cùng `@NotNull` giúp thiếu hoặc null bị từ chối, còn `false` vẫn hợp lệ. Nếu dùng primitive `boolean` với cấu hình binding có giá trị mặc định, rất dễ đánh đồng thuộc tính bị thiếu với yêu cầu đặt `false`.

`@Size` trên các trường tùy chọn không cấm null. Các phần tử null hoặc trắng trong `tags` bị ràng buộc `@NotBlank` từ chối khi validation chạy.

Để hợp đồng “thuộc tính lạ bị từ chối” có hiệu lực, cần bật kiểm tra tại JSON binding. Với cấu hình Spring Boot dùng Jackson, một cách cấu hình là:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

Đây là cấu hình có phạm vi toàn ứng dụng; cần kiểm tra ảnh hưởng đến các endpoint khác. Nếu chỉ muốn chính sách này cho một nhóm request, cấu hình deserializer tương ứng thay vì thay đổi ngầm hành vi của toàn bộ API.

### 7.2. Tạo trạng thái thay thế trước khi đụng entity

~~~java
import java.math.BigDecimal;
import java.util.List;

public record ProductState(
        String name,
        BigDecimal price,
        String description,
        List<String> tags,
        boolean active
) {
    // Chỉ gọi sau khi ReplaceProductRequest đã được validation.
    public static ProductState from(ReplaceProductRequest request) {
        List<String> replacementTags = request.tags() == null
                ? List.of()
                : List.copyOf(request.tags());

        return new ProductState(
                request.name(),
                request.price(),
                request.description(),
                replacementTags,
                request.active()
        );
    }
}
~~~

Mapper không đọc giá trị cũ để điền vào trường bị thiếu:

- `description` thiếu hoặc null trở thành null.
- `tags` thiếu hoặc null trở thành danh sách rỗng.
- `active` chỉ được unbox sau khi validation bảo đảm không null.

Khi áp dụng `ProductState` lên entity đã tồn tại, gán đầy đủ năm trường này. Không dùng tiện ích “copy chỉ những property khác null” cho hợp đồng đang học: tiện ích đó sẽ giữ mô tả cũ khi client đang yêu cầu xóa mô tả.

Không bind body trực tiếp vào entity có các trường nhạy cảm như `ownerId`, `tenantId`, `approvedBy`. DTO là danh sách các trường được phép ghi; metadata và quyền sở hữu được xác định ở server.

### 7.3. Controller phân biệt tạo và thay thế

~~~java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.net.URI;
import java.util.UUID;

@RestController
@RequestMapping("/products")
public class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @PutMapping(value = "/{productId}", consumes = "application/json")
    public ResponseEntity<ProductView> put(
            @PathVariable UUID productId,
            @Valid @RequestBody ReplaceProductRequest request
    ) {
        PutProductResult result = service.replaceOrCreate(
                productId,
                ProductState.from(request)
        );

        if (result.created()) {
            return ResponseEntity
                    .created(URI.create("/products/" + productId))
                    .body(result.product());
        }

        return ResponseEntity.ok(result.product());
    }
}
~~~

Trong code này định danh là UUID; khi gọi thử cần dùng URI như `/products/81a124cf-dfe5-4f42-a8b3-4071b586359c` thay cho mã `P100` dùng trong ví dụ HTTP. API dùng mã nghiệp vụ có thể đổi kiểu tham số và kiểm tra định dạng tương ứng.

`ProductService`, `ProductView` và `PutProductResult` là các kiểu ứng dụng cần cung cấp; `PutProductResult` chứa cờ `created` và biểu diễn sản phẩm. Service phải xác định tạo hay thay thế trong cùng quy trình lưu nguyên tử. Không suy ra `created` từ một lần kiểm tra tồn tại trước transaction.

Luồng service cần thực hiện:

1. Xác định người dùng, tenant và quyền truy cập URI đích.
2. Kiểm tra chính sách cho phép tạo nếu resource chưa tồn tại.
3. Khi resource tồn tại, kiểm tra quyền thay thế; không mặc định quyền tạo đồng nghĩa quyền ghi đè.
4. Áp dụng các ràng buộc nghiệp vụ và điều kiện cập nhật nếu endpoint hỗ trợ.
5. Tạo resource hoặc gán toàn bộ trạng thái ghi; giữ metadata thuộc server theo quy tắc của nó.
6. Commit và trả kết quả tạo/thay thế chính xác.

Controller tối giản trên **chưa triển khai `If-Match` hay `If-None-Match`**. Muốn công bố hỗ trợ hai header này, cần chuyển chúng xuống một bộ xử lý điều kiện và service có kiểm tra nguyên tử; không chỉ thêm tham số rồi bỏ qua giá trị.

### 7.4. Chọn và trả lỗi nhất quán

API ví dụ chọn `400` cho JSON lỗi, thuộc tính không được phép hoặc vi phạm validation DTO. Có thể có API chọn `422 Unprocessable Content` cho nội dung đúng cú pháp nhưng sai quy tắc dữ liệu; cần mô tả rõ cách phân loại.

| Tình huống | Mã trong thiết kế ví dụ | Hành vi cần bảo đảm |
| --- | --- | --- |
| Body thiếu `price`, `name` trắng, `active` null | `400 Bad Request` | Không ghi một phần dữ liệu |
| Không có thông tin xác thực hợp lệ | `401 Unauthorized` | Trả challenge phù hợp cơ chế xác thực |
| Đã xác thực nhưng thiếu quyền tạo/thay thế | `403 Forbidden` | Không ghi; chính sách che giấu resource có thể chọn `404` |
| Không có sản phẩm và endpoint chỉ cho thay thế | `404 Not Found` | Không tự tạo sản phẩm |
| Trạng thái hiện tại không cho thay thế, ví dụ sản phẩm đã khóa | `409 Conflict` | Mô tả xung đột nghiệp vụ có thể xử lý |
| Điều kiện phiên bản không thỏa | `412 Precondition Failed` | Không ghi đè |
| Media type không được hỗ trợ | `415 Unsupported Media Type` | Không cố coi mọi body là JSON |

Một body lỗi có cấu trúc giúp client chỉ ra trường cần sửa:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/invalid-product",
  "title": "Dữ liệu sản phẩm không hợp lệ",
  "status": 400,
  "detail": "Request thay thế thiếu trường bắt buộc.",
  "errors": [
    {
      "field": "price",
      "code": "required",
      "message": "price phải được cung cấp và lớn hơn 0."
    }
  ]
}
~~~

`errors` là phần mở rộng của hợp đồng lỗi ví dụ. Để trả đúng cấu trúc này trong Spring, cần exception handler; `@Valid` không tự tạo mọi trường trong body minh họa.

## 8. Ghi chính sách trường thiếu vào OpenAPI

Một đoạn schema OpenAPI 3.1 cho request của ví dụ:

~~~yaml
components:
  schemas:
    ReplaceProductRequest:
      type: object
      additionalProperties: false
      required:
        - name
        - price
        - active
      properties:
        name:
          type: string
          minLength: 1
          maxLength: 120
          pattern: '\S'
          description: Tên không được chỉ gồm ký tự trắng.
        price:
          type: number
          exclusiveMinimum: 0
        active:
          type: boolean
        description:
          type: [string, "null"]
          maxLength: 2000
          description: Bỏ qua hoặc gửi null sẽ xóa mô tả; chuỗi rỗng được giữ.
        tags:
          type: [array, "null"]
          maxItems: 20
          items:
            type: string
            minLength: 1
            pattern: '\S'
          description: Thay thế toàn bộ danh sách; bỏ qua hoặc null thành danh sách rỗng.
~~~

Cần giữ dấu gạch chéo ngược trong pattern `\S` của YAML. Đây là kiểm tra chuỗi có ký tự không trắng; với yêu cầu Unicode hoặc bộ công cụ validation khác nhau, cần thống nhất quy tắc whitespace giữa schema và Java.

Trong schema này:

- `required` buộc ba thuộc tính xuất hiện.
- Kiểu `string`, `number`, `boolean` không bao gồm null nên ba trường bắt buộc không nhận null.
- `description` và `tags` cho phép null một cách tường minh.
- `additionalProperties: false` khớp chính sách từ chối thuộc tính lạ.
- Mô tả ghi rõ hậu quả khi bỏ trường; chỉ nhìn danh sách `required` không biết trường thiếu có bị xóa hay không.

Nếu thêm `default: []` vào schema, đó là mô tả mặc định, không tự khiến controller hoặc database điền giá trị. Server vẫn cần logic chuẩn hóa như `ProductState.from`.

Ở phần operation PUT, cần mô tả chính sách tạo/thay thế, các response `201`, `200` hoặc `204`, các lỗi đã chọn và các header điều kiện thực sự được hỗ trợ. Schema request và schema response nên tách riêng để client không phải gửi lại các trường chỉ đọc.

## 9. Cache và việc đọc lại sau thay thế

Response PUT không cache được. Cache HTTP đi qua request PUT thành công phải vô hiệu hóa bản đã lưu cho URI đích. [RFC 9110, mục 9.3.4](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.4).

Trong ứng dụng, còn có thể có cache danh sách `GET /products`, cache tìm kiếm và cache nội bộ không trực tiếp quan sát request HTTP. Thiết kế cần cập nhật hoặc vô hiệu hóa các cache liên quan sau commit; việc thay đổi phương thức thành PUT không tự đồng bộ mọi tầng cache.

Khi client cần biểu diễn cuối cùng sau chuẩn hóa, có thể dùng body của response `200` hoặc thực hiện GET. Nếu chọn `204`, client không được cố parse body JSON.

## 10. Những tình huống cần kiểm thử

Các tình huống dưới đây là nội dung thực hành của bài, không phải khẳng định đã có bộ test chạy trong một ứng dụng cụ thể.

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| URI chưa tồn tại, endpoint cho phép tạo | `201`, đúng URI, chỉ một sản phẩm được tạo |
| URI đã tồn tại, body đầy đủ hợp lệ | `200` hoặc `204` theo hợp đồng; trạng thái ghi được thay thế |
| Thiếu `name`, `price` hoặc `active` | `400`; dữ liệu trước request không thay đổi |
| Có `active: false` | Được chấp nhận và lưu false |
| Thiếu `description` | Mô tả cũ trở thành null |
| Có `description: ""` | Lưu chuỗi rỗng đúng hợp đồng |
| Thiếu `tags`, có `tags: null` hoặc có `tags: []` | Đều thành danh sách rỗng |
| Có `tags: ["new"]` | Chỉ còn nhãn mới trong danh sách của sản phẩm |
| Gửi `ownerId`, `id` hoặc tên trường sai | `400`; không thay đổi quyền sở hữu hay metadata |
| Gửi cùng PUT hai lần, không có ghi xen giữa | Không nhân đôi sản phẩm; trạng thái nghiệp vụ không bị cộng dồn |
| Hai client cập nhật cùng một phiên bản | Với điều kiện đã triển khai, một request ghi được; request dùng phiên bản cũ bị từ chối |
| Hai client cùng tạo với `If-None-Match: *` | Chỉ một lần tạo thành công; lần còn lại không ghi đè |
| Validation thất bại sau khi đã có dữ liệu cũ | Toàn bộ resource giữ nguyên, không cập nhật nửa chừng |
| Client thuộc tenant khác gọi cùng mã sản phẩm | Không được đọc/ghi trái phạm vi tenant |
| Endpoint chỉ cho thay thế nhưng URI chưa tồn tại | Không phát sinh hàng mới trong database |

Trong Java/Spring, có thể kiểm tra binding và mã trạng thái bằng MockMvc, kiểm tra thay thế và rollback ở tầng service/repository, rồi dùng kiểm thử tích hợp cho cạnh tranh transaction. Một mock luôn trả `created = true` không chứng minh được tính đúng đắn của upsert khi chạy đồng thời.

## 11. Các lỗi thiết kế thường gặp

**Đặt tên PUT nhưng giữ mọi trường null của entity cũ.** Mapper bỏ qua null khiến client không xóa được mô tả và không biết trường bị thiếu thực sự có ý nghĩa gì. Hãy chọn rõ hợp đồng thay thế hoặc cung cấp thao tác cập nhật từng phần.

**Cho phép body trống vì mọi trường Java đều có mặc định.** Request `{}` có thể vô tình làm sản phẩm mất dữ liệu. Các trường bắt buộc cần được kiểm tra trước khi sửa entity.

**Trả `201` cho mọi lần PUT.** Tạo mới và thay thế là hai kết quả khác nhau; cờ kết quả phải phản ánh việc lưu thực tế.

**Đọc GET rồi gửi nguyên biểu diễn đọc vào PUT.** Response có thể chứa trường chỉ đọc, liên kết hoặc metadata không được phép ghi. Client cần tạo request từ schema ghi đã công bố.

**Coi lũy đẳng là bảo vệ cạnh tranh.** Hai ý định thay thế khác nhau vẫn có thể ghi đè nhau. Dùng điều kiện phiên bản khi nghiệp vụ yêu cầu phát hiện dữ liệu cũ.

**Thêm trường tùy chọn mà không xét client cũ.** Client cũ không biết trường mới, nên có thể bỏ trường đó trong PUT và vô tình xóa giá trị mà client mới đã ghi. Trước khi mở rộng schema, cần đánh giá chính sách mặc định, phiên bản representation, thời gian chuyển đổi và khả năng tách resource.

Một hợp đồng PUT tốt giúp client biết đầy đủ trạng thái cần gửi, giá trị nào sẽ biến mất khi bị bỏ qua, khi nào request có thể tạo mới và cách phát hiện xung đột. Những quyết định này phải thống nhất giữa tài liệu, schema, validation, mapper và tầng lưu trữ.
