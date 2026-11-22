# Content negotiation theo Accept và Content-Type

## 1. Mục tiêu và bối cảnh

Trong chương **Biểu diễn dữ liệu** của module `INTEGRATION_API_REST`, bài này giải thích cách client và server thống nhất định dạng dữ liệu trên đường truyền. Sau bài học, bạn có thể đọc chính xác một cặp request/response, thiết kế hợp đồng media type, phân biệt lỗi `406` và `415`, và triển khai quy tắc tương ứng trong Java/Spring MVC.

Giả sử API quản lý sản phẩm cung cấp resource `/products/42`. Ứng dụng bán hàng cần JSON để xử lý, còn một công cụ vận hành muốn văn bản để hiển thị nhanh. Hai client cùng hỏi về một sản phẩm nhưng cần hai cách biểu diễn. Việc lựa chọn này không làm thay đổi danh tính resource, quyền truy cập hay ý nghĩa nghiệp vụ của thao tác `GET`.

Bài học tập trung vào thương lượng định dạng bằng header. Các ví dụ về cache, OpenAPI và kiểm thử được dùng để biến lựa chọn định dạng thành một hợp đồng có thể quan sát và kiểm chứng.

## 2. Resource, representation và media type

**Resource** là đối tượng được API định danh, chẳng hạn sản phẩm số `42`. **Representation** là dữ liệu thể hiện trạng thái của resource theo một định dạng và hợp đồng cụ thể.

Ví dụ biểu diễn JSON:

```json
{
  "id": "42",
  "name": "Bàn phím",
  "price": 990000,
  "currency": "VND"
}
```

Ví dụ biểu diễn văn bản:

```text
42 | Bàn phím | 990000 VND
```

**Media type** mô tả loại dữ liệu để bên nhận chọn cách xử lý, thường có cấu trúc:

```text
type/subtype; parameter=value
```

| Media type | Cách sử dụng điển hình |
| --- | --- |
| `application/json` | Tài liệu JSON |
| `application/xml` | Tài liệu XML |
| `text/plain; charset=UTF-8` | Văn bản với bộ mã được khai báo |
| `text/csv` | Dữ liệu bảng theo hợp đồng CSV |
| `multipart/form-data; boundary=...` | Body gồm nhiều phần, thường dùng khi gửi biểu mẫu hoặc tệp |

Media type chưa mô tả đầy đủ schema nghiệp vụ. Hai tài liệu cùng là `application/json` có thể khác hoàn toàn về tên trường, đơn vị tiền tệ hoặc ý nghĩa dữ liệu. Vì vậy, thương lượng định dạng phải đi cùng hợp đồng dữ liệu rõ ràng.

Việc thêm `.json` vào một URI cũng không tự biến body thành JSON. Định dạng thực tế phải phù hợp với metadata và hợp đồng của API.

## 3. Hai header trả lời hai câu hỏi khác nhau

Trong request thông thường:

- `Content-Type` trả lời: **Body tôi đang gửi có định dạng gì?**
- `Accept` trả lời: **Tôi chấp nhận những định dạng response nào?**

Trong response, `Content-Type` cho biết định dạng mà server thực sự đã gửi. Phân biệt này dựa trên ngữ nghĩa của [Content-Type](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.3) và [Accept](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.5.1) trong HTTP.

| Header và vị trí | Ví dụ | Ý nghĩa trong trao đổi API |
| --- | --- | --- |
| Request `Content-Type` | `application/json` | Server cần đọc body request theo hợp đồng JSON |
| Request `Accept` | `application/xml` | Client yêu cầu một response XML nếu server hỗ trợ |
| Response `Content-Type` | `application/xml` | Body response thực sự là XML |

### 3.1. Đầu vào và đầu ra có thể khác nhau

```http
POST /products HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/xml

{"name":"Bàn phím","price":990000,"currency":"VND"}
```

Nếu endpoint nhận JSON và có thể tạo XML, một response hợp lệ theo hợp đồng đó là:

```http
HTTP/1.1 201 Created
Location: /products/42
Content-Type: application/xml
Vary: Accept

<product>
  <id>42</id>
  <name>Bàn phím</name>
  <price>990000</price>
  <currency>VND</currency>
</product>
```

Ví dụ minh họa các header liên quan; các header về độ dài và truyền tải được lược bỏ.

Không có yêu cầu rằng request và response phải cùng media type. Khả năng đọc JSON và khả năng ghi XML là hai năng lực độc lập của server. Phần triển khai Spring ở dưới chỉ cung cấp JSON và văn bản cho `GET`; ví dụ XML này minh họa một hợp đồng khác.

### 3.2. GET không có body vẫn có thể dùng Accept

```http
GET /products/42 HTTP/1.1
Host: api.example.test
Accept: application/json
```

Request này không gửi body, nên không cần đặt `Content-Type` chỉ để yêu cầu JSON. Response có thể là:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Vary: Accept

{"id":"42","name":"Bàn phím","price":990000,"currency":"VND"}
```

Nếu đổi request thành `Content-Type: application/json` nhưng bỏ `Accept`, client chưa diễn đạt yêu cầu về định dạng response. Một số API vẫn trả JSON do chính sách mặc định, nhưng điều đó không phải tác dụng của request `Content-Type`.

## 4. Đọc Accept: danh sách, wildcard và trọng số q

### 4.1. Danh sách định dạng được chấp nhận

```http
Accept: application/json, application/xml
```

Client chấp nhận cả hai. Khi cần lựa chọn giữa những phương án ngang nhau, API nên có ưu tiên phía server được công bố, ví dụ chọn JSON làm mặc định. Client muốn một định dạng cụ thể nên yêu cầu rõ định dạng đó.

### 4.2. Wildcard mở rộng phạm vi chấp nhận

| Giá trị | Phạm vi |
| --- | --- |
| `application/json` | Media type JSON cụ thể |
| `application/*` | Các subtype thuộc nhóm `application` |
| `*/*` | Mọi media type |

Nếu không có `Accept`, server không nhận được một giới hạn media type từ header này. API có thể chọn định dạng mặc định đã tài liệu hóa. Cần phân biệt **không gửi header** với việc tự tạo một header rỗng; khi cần diễn đạt chấp nhận mọi định dạng, dùng `*/*` hoặc bỏ header theo hợp đồng.

`Accept: application/*` không có nghĩa là server phải hỗ trợ mọi định dạng thuộc nhóm `application`. Server chỉ lựa chọn trong các biểu diễn mà endpoint thực sự cung cấp.

### 4.3. q là trọng số ưu tiên tương đối

```http
Accept: application/json;q=1, application/xml;q=0.7, text/plain;q=0.2
```

Các quy tắc cần nhớ:

- `q` nằm từ `0` đến `1`, với tối đa ba chữ số thập phân.
- Không ghi `q` thì giá trị mặc định là `1`.
- `q=0` biểu thị không chấp nhận media range đó.
- `q` không mô tả chất lượng dữ liệu, mức nén hoặc độ chính xác nghiệp vụ.

Quy tắc trọng số và độ cụ thể của media range được mô tả tại [RFC 9110, phần Accept](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.5.1).

Với ví dụ trên, nếu API chỉ cung cấp XML và văn bản, XML là phương án được client ưu tiên hơn. Việc JSON có trọng số cao nhất không khiến một server chưa hỗ trợ JSON có thể tạo được JSON.

### 4.4. Xác định range khớp cụ thể trước khi so sánh trọng số

Một lỗi phổ biến là tìm mọi range khớp rồi lấy `q` lớn nhất cho từng biểu diễn. Hãy xét:

```http
Accept: application/json;q=0.4, application/*;q=0.9
```

Nếu server cung cấp cả JSON và XML:

| Biểu diễn ứng viên | Range cụ thể nhất khớp | Trọng số áp dụng |
| --- | --- | --- |
| `application/json` | `application/json;q=0.4` | `0.4` |
| `application/xml` | `application/*;q=0.9` | `0.9` |

Trong chính sách chọn ứng viên theo ưu tiên client của ví dụ, XML được ưu tiên. JSON không nhận `0.9` từ wildcard vì đã có range cụ thể hơn.

Một ví dụ khác:

```http
Accept: application/json;q=0, */*;q=1
```

JSON vẫn bị loại bởi khai báo cụ thể `q=0`. Nếu server chỉ có JSON, hợp đồng tôn trọng `Accept` của bài này trả `406`, thay vì dùng wildcard để đưa JSON trở lại danh sách.

Nếu có tham số media type, một range khớp cả tham số có thể cụ thể hơn range chỉ khớp type/subtype. Không nên tự viết bộ phân tích bằng cách `split` chuỗi đơn giản rồi giả định đã xử lý đầy đủ mọi trường hợp. Khi framework tham gia lựa chọn, cần kiểm chứng những ca biên mà hợp đồng API yêu cầu.

## 5. Chính sách thương lượng phải được công bố

Để các ví dụ có kết quả rõ ràng, xét hợp đồng của `GET /products/{id}` như sau:

| Tình huống | Quyết định của API ví dụ |
| --- | --- |
| Client yêu cầu JSON | Trả JSON |
| Client yêu cầu văn bản | Trả văn bản |
| Không gửi `Accept`, hoặc gửi `*/*` | Chọn JSON làm mặc định |
| Nhiều định dạng có ưu tiên ngang nhau | Ưu tiên JSON |
| Không có biểu diễn nào được chấp nhận | Trả `406 Not Acceptable` |

Đây là chính sách thiết kế của API ví dụ. HTTP cho phép server bỏ qua tùy chọn thương lượng trong một số tình huống; không nên biến lựa chọn trả `406` của bài này thành khẳng định rằng mọi server đều bắt buộc làm như vậy. [RFC 9110, phần Absence](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.4.1) mô tả sự linh hoạt đó.

Với API được nhiều ứng dụng tích hợp, một chính sách rõ ràng giúp client nhận biết sớm khi hợp đồng không tương thích. Việc luôn trả JSON dù client chỉ chấp nhận XML có thể làm lỗi xuất hiện muộn ở bước giải mã response.

Một quy trình thiết kế có thể dùng là:

1. Xác định các biểu diễn endpoint thực sự cung cấp.
2. Đọc `Accept`, hoặc áp dụng quy tắc khi header vắng mặt.
3. Xác định khả năng chấp nhận và trọng số cho từng biểu diễn.
4. Chọn một biểu diễn theo quy tắc đã công bố.
5. Nếu không có lựa chọn, trả lỗi hoặc dùng fallback đã được hợp đồng cho phép.
6. Ghi `Content-Type` đúng với body cuối cùng.

Quy trình trên mô tả quyết định về biểu diễn; nó không áp đặt thứ tự thực thi middleware, xác thực hay phân quyền trong mọi framework.

## 6. Content-Type và việc đọc body request

Xét endpoint tạo sản phẩm chỉ nhận JSON:

```http
POST /products HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/json

{"name":"Bàn phím","price":990000,"currency":"VND"}
```

Phía server cần xử lý các lớp khác nhau:

1. Kiểm tra kiểu nội dung đầu vào có được endpoint hỗ trợ hay không.
2. Giải mã body theo kiểu đã khai báo.
3. Ánh xạ dữ liệu vào cấu trúc yêu cầu.
4. Kiểm tra ràng buộc dữ liệu và nghiệp vụ.

### 6.1. Nhãn đúng không bảo đảm nội dung đúng

```http
Content-Type: application/json

<product><name>Bàn phím</name></product>
```

Endpoint có hỗ trợ JSON, nhưng body trên không phải JSON hợp lệ. Khi lỗi nằm ở cú pháp giải mã, API thường trả `400 Bad Request`; đây không phải trường hợp điển hình để trả `415` chỉ vì nội dung bị khai báo sai.

Ngược lại:

```http
Content-Type: application/xml

<product><name>Bàn phím</name></product>
```

Nếu endpoint chỉ nhận JSON, XML hợp lệ vẫn nằm ngoài kiểu đầu vào được hỗ trợ và có thể dẫn đến `415 Unsupported Media Type`.

### 6.2. Thiếu Content-Type không tương đương JSON mặc định

Nếu một request có body nhưng thiếu `Content-Type`, hành vi phụ thuộc hợp đồng và cấu hình bộ đọc dữ liệu. Với endpoint yêu cầu kiểu nội dung rõ ràng, API ví dụ từ chối bằng `415`.

Không dựa vào việc “body trông giống JSON” để suy luận rằng mọi server phải tiếp nhận. Client nên khai báo đúng media type khi gửi nội dung.

### 6.3. Tham số thuộc media type cần có ý nghĩa cụ thể

Với `multipart/form-data`, `boundary` giúp phân tách các phần của body. Khi dùng công cụ dựng multipart, hãy để công cụ tạo cả boundary lẫn body tương ứng. Tự đặt một header thiếu boundary có thể khiến server không đọc được nội dung dù danh nghĩa vẫn là multipart.

Với văn bản, `charset` có thể chỉ ra bộ mã ký tự. Không tự thêm cùng một tham số cho mọi media type mà không kiểm tra hợp đồng của kiểu dữ liệu đó. Quan trọng nhất là byte thực tế, metadata và bộ giải mã phải thống nhất.

## 7. Phân biệt 406, 415 và các lỗi gần nhau

| Mã trạng thái | Câu hỏi chẩn đoán | Ví dụ trong API sản phẩm |
| --- | --- | --- |
| `406 Not Acceptable` | Server có tạo được biểu diễn response mà client chấp nhận không? | Client chỉ nhận XML, endpoint chỉ xuất JSON và văn bản |
| `415 Unsupported Media Type` | Kiểu hoặc cách mã hóa nội dung request có được hỗ trợ không? | Gửi XML đến endpoint chỉ nhận JSON |
| `400 Bad Request` | Request có lỗi cú pháp hoặc không giải mã được theo hợp đồng không? | Body khai báo JSON nhưng thiếu dấu ngoặc đóng |
| `422 Unprocessable Content` | Nội dung đã được hiểu nhưng chỉ dẫn trong đó không xử lý được theo quy tắc API không? | Giá âm trong một API quy định lỗi dữ liệu này dùng `422` |

Việc chọn `400` hay `422` cho lỗi kiểm tra dữ liệu cần nhất quán với hợp đồng API; không phải mọi lỗi validation đều tự động mang mã `422`.

### 7.1. Ví dụ 406

```http
GET /products/42 HTTP/1.1
Host: api.example.test
Accept: application/pdf
```

Nếu endpoint chỉ cung cấp JSON và văn bản, response tối giản có thể là:

```http
HTTP/1.1 406 Not Acceptable
Vary: Accept
Content-Length: 0
```

Response không có body là một lựa chọn hữu ích khi chưa có định dạng lỗi được hai bên thống nhất. API cũng có thể cung cấp thông tin chẩn đoán theo chính sách lỗi đã tài liệu hóa.

### 7.2. Ví dụ 415

```http
POST /products HTTP/1.1
Host: api.example.test
Content-Type: application/xml
Accept: application/json

<product><name>Bàn phím</name></product>
```

Với endpoint chỉ nhận JSON, một response theo hợp đồng lỗi JSON có thể là:

```http
HTTP/1.1 415 Unsupported Media Type
Content-Type: application/json

{
  "code": "UNSUPPORTED_REQUEST_MEDIA_TYPE",
  "message": "Endpoint chỉ nhận application/json",
  "supportedMediaTypes": ["application/json"]
}
```

`Accept: application/json` chỉ giúp chọn định dạng response trong ví dụ này; nó không làm XML đầu vào trở thành hợp lệ.

Nếu request đồng thời có kiểu đầu vào không được hỗ trợ và yêu cầu đầu ra không được hỗ trợ, không suy đoán một thứ tự lỗi áp dụng cho mọi framework. Khi kiểm thử, trước hết tách hai lỗi thành hai request để xác định từng hành vi.

### 7.3. Response lỗi cũng là nội dung cần có hợp đồng

Nếu chọn `application/problem+json` cho lỗi, hãy công bố media type đó và hướng dẫn client chấp nhận nó. Không mặc định rằng `Accept: application/json` bao gồm mọi kiểu có hậu tố `+json`.

Các kiểu như `application/vnd.example.product+json` và `application/problem+json` cho biết cấu trúc dùng JSON nhưng vẫn là những media type riêng. Việc framework hỗ trợ pattern mở rộng như `application/*+json` là khả năng triển khai cần xác minh; không nên coi đó là một media range wildcard chuẩn được mọi HTTP server xử lý giống nhau.

Một lỗi thương lượng không nên tạo vòng lặp: bộ xử lý `406` lại cố ghi chính định dạng đã bị từ chối, rồi tiếp tục sinh một lỗi thương lượng mới.

## 8. Cache phải phân biệt các biểu diễn

Giả sử hai request cùng truy cập `/products/42`:

```http
Accept: application/json
```

và:

```http
Accept: text/plain
```

Nếu một cache tái sử dụng response chỉ dựa vào URI mà bỏ qua yếu tố chọn biểu diễn, client có thể nhận dữ liệu ở định dạng khác với yêu cầu. Khi lựa chọn phụ thuộc vào `Accept`, response cần thể hiện yếu tố này qua `Vary: Accept` theo [ngữ nghĩa Vary của HTTP](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.5.5).

```http
HTTP/1.1 200 OK
Content-Type: application/json
Vary: Accept
Cache-Control: public, max-age=60
ETag: "product-42-json-r7"

{"id":"42","name":"Bàn phím","price":990000,"currency":"VND"}
```

Header `public` trong ví dụ chỉ dành cho một danh mục sản phẩm công khai. Chính sách cache cho dữ liệu theo người dùng phải được thiết kế theo quyền truy cập và tính riêng tư của dữ liệu.

Các điểm triển khai cần giữ nhất quán:

- Ghi `Vary: Accept` cho những biến thể được chọn bằng header này.
- Khi đã có `Vary` cho một header khác, hợp nhất giá trị thay vì xóa giá trị cũ.
- Nếu thêm thương lượng ngôn ngữ hoặc cách nén, xem xét các chiều lựa chọn đó trong cấu hình cache.
- Thiết kế validator cho đúng biểu diễn. Trong ví dụ, JSON và văn bản dùng ETag khác nhau khi byte nội dung khác nhau.

`Vary` không làm response tự động được cache, không cấp thời gian sống và không thay thế `Cache-Control`. Nó cung cấp thông tin để cache biết request nào có thể dùng lại một response đã lưu.

## 9. Ánh xạ sang Spring MVC

Trong Spring MVC:

- `consumes` ràng buộc mapping theo `Content-Type` của request.
- `produces` ràng buộc mapping theo `Accept` và các kiểu đầu ra được khai báo.

Đó là vai trò được mô tả trong tài liệu [Mapping Requests của Spring](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html#mapping-consumes).

Bộ chuyển đổi thông điệp HTTP thực hiện đọc và ghi body. Khai báo một kiểu đầu ra không tự cung cấp serializer cho kiểu đó. Ví dụ, thêm `application/xml` vào annotation mà chưa có bộ chuyển đổi XML phù hợp chưa tạo thành một triển khai XML hoàn chỉnh.

### 9.1. Cùng URI, hai biểu diễn

Ví dụ sau là một controller minh họa cho ứng dụng Spring MVC đã có bộ chuyển đổi JSON và văn bản. Dữ liệu được cố định để tập trung vào thương lượng; lớp này không phải một ứng dụng Spring hoàn chỉnh.

```java
package example.api;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/products")
public class ProductController {

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ProductView> getJson(@PathVariable("id") String id) {
        ProductView product = findProduct(id);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .varyBy("Accept")
                .body(product);
    }

    @GetMapping(path = "/{id}", produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> getText(@PathVariable("id") String id) {
        ProductView product = findProduct(id);
        String body = product.id() + " | " + product.name() + " | "
                + product.price().toPlainString() + " " + product.currency();

        return ResponseEntity.ok()
                .contentType(new MediaType("text", "plain", StandardCharsets.UTF_8))
                .varyBy("Accept")
                .body(body);
    }

    private ProductView findProduct(String id) {
        if (!"42".equals(id)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return new ProductView(
                "42", "Bàn phím", new BigDecimal("990000"), "VND");
    }

    public record ProductView(
            String id, String name, BigDecimal price, String currency) {
    }
}
```

Hai method cùng đọc một resource qua cùng logic lấy dữ liệu. Chúng khác ở định dạng được khai báo và cách tạo body. `produces` để framework tham gia lựa chọn handler; `contentType(...)` ghi metadata đúng với body handler đó tạo ra.

Không dùng `Content-Type` request để chọn giữa hai method `GET` này. Một request `GET` không có body không cần `consumes` chỉ để yêu cầu JSON.

Controller trên thể hiện các yêu cầu `Accept` cụ thể. Chính sách mặc định JSON khi thiếu `Accept`, cách phá hòa, xử lý `q=0`, header `Vary` trên response lỗi và body lỗi cần được cấu hình, kiểm chứng trong ứng dụng thực tế. Không dựa vào thứ tự khai báo hai method Java để cam kết mặc định đó.

### 9.2. Endpoint nhận JSON và trả JSON

Đối với một method tạo sản phẩm trong controller có sẵn, phần khai báo mapping có thể viết:

```java
@PostMapping(
        path = "/products",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
)
```

Đây là đoạn annotation để đặt trên method xử lý, không phải toàn bộ chương trình. Method dùng `@RequestBody` để nhận DTO; phần service tạo dữ liệu và phần trả `201 Created` cùng `Location` thuộc logic của endpoint.

Hai ràng buộc phải được thỏa mãn độc lập:

| Content-Type request | Accept request | Kỳ vọng theo hợp đồng chỉ dùng JSON |
| --- | --- | --- |
| `application/json` | `application/json` | Có thể đi tiếp đến xử lý body và nghiệp vụ |
| `application/xml` | `application/json` | Từ chối đầu vào bằng `415` |
| `application/json` | `application/xml` | Từ chối yêu cầu đầu ra bằng `406` |

Mapping media type không thay thế việc parse dữ liệu, kiểm tra DTO, xác thực hay phân quyền.

### 9.3. Một số cách triển khai dễ tạo lỗi

- **Dùng `contains("json")` để phân tích Accept:** bỏ qua trọng số, wildcard và những media type có hợp đồng khác nhau.
- **Trả chuỗi JSON nhưng gắn nhãn `text/plain`:** client xử lý theo nhãn đã công bố và có thể không chạy bộ đọc JSON.
- **Tự đổi mọi lỗi thành `500`:** làm mất khả năng phân biệt lỗi thương lượng với lỗi phía server.
- **Bắt buộc header phải bằng đúng chuỗi `application/json`:** có thể từ chối những biến thể tham số hợp lệ mà bộ phân tích media type có thể xử lý.
- **Khai báo XML chỉ để làm tài liệu đẹp:** hợp đồng không được hỗ trợ bởi serializer và kiểm thử sẽ gây lỗi khi có client sử dụng.

## 10. Thực hành bằng curl

Các lệnh dưới đây chạy riêng lẻ trên terminal. Chúng giả định ứng dụng ở `localhost:8080` và sản phẩm `42` tồn tại. Các lệnh `GET` có thể dùng với controller minh họa sau khi đưa controller vào một ứng dụng Spring MVC phù hợp.

Yêu cầu JSON:

```text
curl.exe -i "http://localhost:8080/products/42" -H "Accept: application/json"
```

Yêu cầu văn bản:

```text
curl.exe -i "http://localhost:8080/products/42" -H "Accept: text/plain"
```

Yêu cầu định dạng không được endpoint cung cấp:

```text
curl.exe -i "http://localhost:8080/products/42" -H "Accept: application/pdf"
```

Thử ưu tiên văn bản hơn JSON:

```text
curl.exe -i "http://localhost:8080/products/42" -H "Accept: text/plain;q=1, application/json;q=0.5"
```

Thử loại JSON bằng một range cụ thể:

```text
curl.exe -i "http://localhost:8080/products/42" -H "Accept: application/json;q=0, */*;q=1"
```

Khi kiểm chứng chính sách mặc định, cần biết curl thường gửi `Accept: */*`. Để bỏ header này hoàn toàn trong request thử nghiệm:

```text
curl.exe -i "http://localhost:8080/products/42" -H "Accept:"
```

Trong cú pháp curl, tùy chọn trên loại header `Accept` khỏi request; mục đích ở đây là kiểm tra trường hợp không gửi header.

Để kiểm tra `415` trên endpoint `POST /products` chỉ nhận JSON đã được triển khai thêm trong ứng dụng:

```text
curl.exe -i "http://localhost:8080/products" -H "Content-Type: application/xml" -H "Accept: application/json" --data-raw "<product/>"
```

Đọc cả status, `Content-Type`, `Vary` và body. Chỉ thấy `200` chưa chứng minh định dạng trả về đúng hợp đồng. Những lệnh này là bài thực hành cho người học, không phải kết quả khẳng định rằng các ví dụ đã được chạy trên repo hiện tại.

## 11. Mô tả hợp đồng trong OpenAPI

Trong OpenAPI, khai báo media type của request body trong `requestBody.content`; khai báo media type của response trong `responses[status].content`. Không mô hình hóa `Accept` và `Content-Type` như hai tham số header thông thường để thay thế các cấu trúc này. Cách mô tả body được quy định tại [OpenAPI Specification, Media Type Object](https://spec.openapis.org/oas/v3.1.0#media-type-object).

Đoạn dưới là một phần của tài liệu OpenAPI, cần ghép vào tài liệu có phần thông tin và phiên bản tương ứng:

```yaml
paths:
  /products/{id}:
    get:
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Biểu diễn sản phẩm theo Accept
          headers:
            Vary:
              description: Response được chọn dựa trên Accept
              schema:
                type: string
              example: Accept
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
            text/plain:
              schema:
                type: string
              example: '42 | Bàn phím | 990000 VND'
        '406':
          description: Không có biểu diễn phù hợp với Accept
  /products:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProduct'
      responses:
        '201':
          description: Đã tạo sản phẩm
          headers:
            Location:
              description: URI của sản phẩm vừa tạo
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
        '406':
          description: Endpoint không cung cấp media type đầu ra được yêu cầu
        '415':
          description: Endpoint không hỗ trợ media type đầu vào
components:
  schemas:
    CreateProduct:
      type: object
      required: [name, price, currency]
      properties:
        name:
          type: string
        price:
          type: number
          minimum: 0
        currency:
          type: string
          enum: [VND]
    Product:
      allOf:
        - $ref: '#/components/schemas/CreateProduct'
        - type: object
          required: [id]
          properties:
            id:
              type: string
```

Trong tài liệu API, bổ sung bằng lời chính sách mặc định, quy tắc ưu tiên và định dạng lỗi nếu có. Việc liệt kê nhiều media type trong OpenAPI không tự cấu hình server và cũng không bảo đảm các biến thể có dữ liệu tương đương.

Nếu văn bản chỉ phục vụ con người, cần nói rõ mức độ ổn định của format. Nếu client sẽ parse văn bản, thứ tự trường, ký tự phân tách và cách escape phải trở thành một phần của hợp đồng.

## 12. Ma trận kiểm thử hợp đồng

Ma trận sau là các tình huống cần kiểm chứng khi triển khai đầy đủ chính sách của API ví dụ. Nó không phải báo cáo kiểm thử đã chạy.

| Ca | Request hoặc điều kiện | Kỳ vọng |
| --- | --- | --- |
| 1 | `GET`, `Accept: application/json` | `200`, body JSON, `Content-Type: application/json` |
| 2 | `GET`, `Accept: text/plain` | `200`, body văn bản, `Content-Type` thuộc `text/plain` |
| 3 | `GET`, `Accept: application/pdf` | `406` |
| 4 | `GET`, không có `Accept` | JSON mặc định theo hợp đồng đã cấu hình |
| 5 | `GET`, `Accept: */*` | JSON mặc định theo hợp đồng đã cấu hình |
| 6 | `GET`, văn bản có `q` cao hơn JSON | Trả văn bản |
| 7 | `GET`, JSON có `q=0`, wildcard có `q=1` | Không trả JSON; chọn văn bản nếu khả dụng |
| 8 | `POST`, XML đầu vào, chấp nhận JSON | `415` trên endpoint chỉ nhận JSON |
| 9 | `POST`, JSON đầu vào bị lỗi cú pháp | `400` khi bộ đọc xử lý body |
| 10 | JSON và văn bản cùng một sản phẩm | Cùng dữ liệu nghiệp vụ và cùng quy tắc phân quyền |
| 11 | Cache nhận lần lượt hai giá trị `Accept` | Không tái sử dụng nhầm biểu diễn |

Ngoài status, hãy xác minh:

- Header `Content-Type` phù hợp với body giải mã được.
- `Vary` có chiều `Accept` khi lựa chọn biểu diễn phụ thuộc header đó.
- Các trường dữ liệu và đơn vị trong JSON khớp với hợp đồng.
- Body văn bản thể hiện đúng dữ liệu đã được phép truy cập.
- Response lỗi không làm lộ dữ liệu nội bộ hoặc biến lỗi client thành lỗi server ngoài dự kiến.

Với `text/plain; charset=UTF-8`, một phép so sánh chuỗi tuyệt đối với `text/plain` có thể làm test thất bại dù media type tương thích. Chọn cách kiểm tra tương thích media type khi mục tiêu là kiểm chứng type/subtype; kiểm tra tham số riêng khi charset cũng là yêu cầu của hợp đồng.

Khi dùng Spring MVC Test hoặc công cụ tương đương, đưa `Accept` và `Content-Type` vào request kiểm thử một cách độc lập. Một test chỉ gọi endpoint rồi kiểm tra DTO thành công sẽ bỏ qua phần thương lượng nằm ở lớp HTTP.

## 13. Giới hạn cần phân biệt

| Cơ chế | Điều nó quyết định |
| --- | --- |
| `Accept` / `Content-Type` | Kiểu biểu diễn và cách diễn giải nội dung |
| `Accept-Encoding` / `Content-Encoding` | Cách mã hóa nội dung như nén gzip |
| `Accept-Language` / `Content-Language` | Ngôn ngữ tự nhiên của nội dung |
| Xác thực và phân quyền | Người gọi là ai, được đọc hoặc sửa dữ liệu nào |
| Schema và validation | Cấu trúc, kiểu trường, ràng buộc và tính hợp lệ của dữ liệu |

JSON có thể được nén gzip; lúc đó `Content-Type` vẫn mô tả JSON, còn header về encoding mô tả lớp nén. Đổi `Accept` cũng không cấp thêm quyền đọc trường dữ liệu và không thay đổi một thao tác ghi thành thao tác an toàn để tự động retry.

Nếu dùng media type riêng để phân biệt phiên bản hợp đồng, ví dụ `application/vnd.example.product.v2+json`, phải mô tả rõ ý nghĩa phiên bản, hỗ trợ chuyển đổi và khả năng đọc của client. Hậu tố `+json` chỉ hỗ trợ nhận biết cấu trúc JSON; nó không bảo đảm mọi schema hoặc phiên bản tương thích với nhau.

## 14. Tự kiểm tra mức độ hiểu bài

Hãy giải thích bằng một request/response cụ thể cho từng tình huống:

1. Client gửi JSON nhưng muốn nhận XML. Header nào mô tả từng chiều?
2. Endpoint nhận JSON nhưng trả về `415` khi client gửi XML hợp lệ. Vì sao JSON trong `Accept` không giải quyết được lỗi?
3. Với `Accept: application/json;q=0, */*;q=1`, vì sao không được chọn lại JSON trong hợp đồng tôn trọng `Accept`?
4. Hai request cùng URI nhận JSON và văn bản. Header nào giúp cache phân biệt các response?
5. Vì sao thêm `produces = "application/xml"` chưa đủ để cam kết endpoint đã hỗ trợ XML?
6. Khi request không có `Accept`, cần công bố và kiểm chứng quyết định nào để client nhận kết quả ổn định?

Khi thiết kế một endpoint, bắt đầu bằng bốn quyết định cụ thể: những media type được nhận, những media type được trả, cách chọn khi client không nêu ưu tiên và cách phản hồi khi không có lựa chọn tương thích. Sau đó giữ thống nhất các quyết định ấy trong code, OpenAPI và kiểm thử HTTP.
