# Media type, structured syntax suffix và media type tùy chỉnh

Trong chương **Biểu diễn dữ liệu** của module **INTEGRATION_API_REST**, một vấn đề quan trọng là làm cho bên gửi và bên nhận hiểu cùng một tài liệu. URI xác định resource, phương thức HTTP mô tả thao tác, còn media type giúp xác định cách diễn giải nội dung được truyền. Chọn media type phù hợp làm rõ hợp đồng REST API, từ phản hồi thành công đến tài liệu lỗi và yêu cầu cập nhật dữ liệu.

Bài này tập trung vào cấu trúc media type, ý nghĩa của hậu tố như `+json`, và cách thiết kế media type tùy chỉnh. Ví dụ dùng HTTP, OpenAPI và Java/Spring; các nguyên tắc thiết kế cũng áp dụng cho công nghệ tương đương.

Sau bài học, người học có thể:

- Phân tích type, subtype, parameter và structured syntax suffix.
- Phân biệt khả năng phân tích cú pháp với khả năng hiểu ngữ nghĩa nghiệp vụ.
- Chọn giữa media type có sẵn và media type tùy chỉnh.
- Khai báo hợp đồng và cấu hình Spring để tránh nhầm `Content-Type`, `Accept`, `consumes` và `produces`.

## 1. Resource có thể có nhiều biểu diễn

Giả sử `/orders/42` xác định một đơn hàng. Một biểu diễn của đơn hàng có thể là:

```json
{
  "id": "42",
  "status": "PAID",
  "total": {
    "amount": "125000",
    "currency": "VND"
  }
}
```

Các byte JSON chưa tự giải thích hết ý nghĩa của dữ liệu. Bên nhận còn cần biết `amount` dùng đơn vị nào, `status` có những giá trị nào, và liệu tài liệu này là toàn bộ biểu diễn đơn hàng hay chỉ là phần thay đổi.

Cùng một resource có thể được biểu diễn bằng JSON cho ứng dụng, HTML cho người dùng hoặc PDF cho việc in. Việc thay đổi biểu diễn không nhất thiết làm thay đổi resource hay URI của nó.

Cần phân biệt ba lớp:

| Lớp | Ví dụ | Câu hỏi được giải đáp |
| --- | --- | --- |
| Resource | `/orders/42` | Đang nói đến đối tượng nào? |
| Cú pháp dữ liệu | JSON | Các byte được phân tích thành cấu trúc gì? |
| Ngữ nghĩa biểu diễn | Tài liệu đơn hàng phiên bản 1 | Các trường có ý nghĩa và quy tắc xử lý nào? |

Media type giúp bên nhận chọn cách xử lý. Schema và đặc tả đi kèm tiếp tục mô tả những chi tiết mà tên media type không thể chứa hết.

## 2. Đọc cấu trúc một media type

Dạng tổng quát là:

```text
type/subtype; parameter=value
```

Ví dụ minh họa xuyên suốt bài:

```http
Content-Type: application/vnd.acme.order.v1+json
```

Tên `application/vnd.acme.order.v1+json` được đặt giả định cho bài học; ví dụ này không khẳng định rằng tên đó đã được đăng ký với IANA.

| Thành phần | Giá trị trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| Top-level type | `application` | Nhóm nội dung được phần mềm xử lý |
| Subtype đầy đủ | `vnd.acme.order.v1+json` | Định danh cụ thể của media type |
| Registration tree | `vnd.` | Cách đặt tên thuộc vendor tree |
| Phần tên do người thiết kế chọn | `acme.order.v1` | Nhận diện định dạng theo quy ước của ví dụ |
| Structured syntax suffix | `+json` | Cú pháp nền là JSON |

`vnd.` và `+json` đều nằm trong subtype. Chúng không phải các header độc lập. Riêng chuỗi `v1` là quy ước của hợp đồng, không phải cơ chế phiên bản do HTTP tự hiểu.

Tên type, subtype và tên parameter không phân biệt chữ hoa, chữ thường; giá trị parameter tuân theo định nghĩa riêng. Nên dùng chữ thường để tài liệu và log nhất quán. Quy tắc đặt tên, registration tree và parameter được mô tả trong [RFC 6838](https://www.rfc-editor.org/rfc/rfc6838.html#section-4.2).

### 2.1. Parameter bổ sung thông tin cho media type

Ví dụ:

```http
Content-Type: text/plain; charset=utf-8
```

Ở đây `charset` là parameter, còn `text/plain` là type/subtype. Parameter phải có ý nghĩa được đặc tả; không nên tự thêm một parameter rồi kỳ vọng mọi client hay framework đều hiểu nó.

Với `application/json`, đăng ký media type không định nghĩa parameter `charset`. JSON trao đổi giữa các hệ thống ngoài một hệ sinh thái đóng phải dùng UTF-8. Khi thiết kế API JSON thông thường, có thể gửi `Content-Type: application/json` và mã hóa nội dung bằng UTF-8; việc gắn `charset` không thay thế nghĩa vụ mã hóa đúng. Xem [RFC 8259, mục 8.1 và 11](https://www.rfc-editor.org/rfc/rfc8259.html#section-8.1).

### 2.2. Media type khác tên file và cơ chế nén

Ba khái niệm này có mục đích khác nhau:

```http
Content-Type: application/vnd.acme.order.v1+json
Content-Encoding: gzip
```

Nội dung trên là một biểu diễn đơn hàng có cú pháp JSON và được nén bằng gzip. Sau khi giải nén, bên nhận mới phân tích tài liệu theo media type đã khai báo.

Phần mở rộng `.json` trong tên file hoặc đường dẫn là một quy ước khác. Không nên chỉ nhìn vào đường dẫn để bỏ qua `Content-Type` của thông điệp thực tế. Trong thiết kế này, resource vẫn có URI `/orders/42`, còn header mô tả biểu diễn.

## 3. Structured syntax suffix cho biết điều gì?

Structured syntax suffix là phần hậu tố có ý nghĩa đã được định nghĩa, chẳng hạn `+json` hoặc `+xml`. Nó cho phép bộ xử lý tổng quát nhận biết cú pháp nền mà không cần biết toàn bộ ngữ nghĩa của media type cụ thể. Đây là mục đích được nêu trong [RFC 6839](https://www.rfc-editor.org/rfc/rfc6839.html#section-2).

Ví dụ, công cụ xem dữ liệu có thể đọc `application/vnd.acme.order.v1+json` thành cây JSON và hiển thị các trường. Tuy nhiên, chỉ nhờ `+json`, công cụ đó chưa biết:

- `status: "PAID"` có cho phép hủy đơn hàng hay không.
- `total.amount` là chuỗi thập phân theo đơn vị tiền tệ hay số đơn vị nhỏ nhất.
- Trường nào bắt buộc, trường nào chỉ xuất hiện với một nhóm quyền.
- Cách áp dụng tài liệu khi nó được gửi trong một yêu cầu cập nhật.

Một parser JSON hoạt động thành công mới chứng minh rằng cú pháp đọc được. Để xử lý đúng, ứng dụng vẫn phải nhận diện hợp đồng cụ thể và kiểm tra schema, quy tắc nghiệp vụ.

### 3.1. Cùng hậu tố, khác cách xử lý

| Media type | Cú pháp nền | Mục đích xử lý |
| --- | --- | --- |
| `application/json` | JSON | JSON tổng quát; hợp đồng endpoint cung cấp ngữ nghĩa cụ thể |
| `application/problem+json` | JSON | Mô tả lỗi theo Problem Details |
| `application/json-patch+json` | JSON | Danh sách thao tác để thay đổi tài liệu |
| `application/merge-patch+json` | JSON | Tài liệu thay đổi theo quy tắc JSON Merge Patch |
| `application/vnd.acme.order.v1+json` | JSON | Biểu diễn đơn hàng giả định của bài học |

`application/json` là tên media type hoàn chỉnh; nó không có hậu tố `+json`. Một tài liệu JSON cũng không nhất thiết có giá trị gốc là object.

Chẳng hạn, JSON Patch dùng một array các thao tác:

```http
PATCH /orders/42 HTTP/1.1
Host: api.example.test
Content-Type: application/json-patch+json
Accept: application/vnd.acme.order.v1+json

[
  { "op": "replace", "path": "/deliveryNote", "value": "Giao buổi chiều" }
]
```

Ví dụ này giả định endpoint hỗ trợ JSON Patch và đơn hàng có trường `deliveryNote` được phép sửa. Máy chủ phải thực hiện ngữ nghĩa thao tác `replace`; chỉ deserialize array rồi lưu nguyên array làm đơn hàng sẽ sai. Định dạng này được mô tả trong [RFC 6902](https://www.rfc-editor.org/rfc/rfc6902.html#section-3).

Với JSON Merge Patch:

```http
PATCH /orders/42 HTTP/1.1
Host: api.example.test
Content-Type: application/merge-patch+json

{
  "deliveryNote": null
}
```

Theo định dạng này, giá trị `null` trong một object patch biểu thị việc loại bỏ thành viên tương ứng. Vì vậy, cần cân nhắc khi mô hình dữ liệu có nhu cầu lưu `null` như một giá trị có ý nghĩa riêng. Xem [RFC 7396](https://www.rfc-editor.org/rfc/rfc7396.html#section-2).

Hai ví dụ PATCH là minh họa riêng về ngữ nghĩa media type; chúng không có nghĩa controller GET ở phần sau đã triển khai PATCH.

### 3.2. Không tự bịa hoặc ghép hậu tố theo cảm tính

Các hậu tố có registry riêng tại [IANA Structured Syntax Suffixes](https://www.iana.org/assignments/media-type-structured-suffix/media-type-structured-suffix.xhtml). Khi cần một cú pháp nền, hãy kiểm tra định nghĩa được đăng ký.

Không tự suy ra rằng một tên như `application/vnd.acme.order+json+gzip` có nghĩa là “JSON được gzip”. Đối với HTTP, nén thông thường được diễn đạt bằng `Content-Encoding`. Hậu tố phải phản ánh đúng cú pháp mà bộ xử lý tổng quát có thể đọc theo định nghĩa của nó.

## 4. Đặt media type đúng chiều trong HTTP

Đối với request có nội dung và response có nội dung, hãy tách hai câu hỏi:

| Header | Khi xuất hiện ở đâu | Ý nghĩa trong trao đổi client–server đang xét |
| --- | --- | --- |
| `Content-Type` | Request | Nội dung client đang gửi có media type nào? |
| `Accept` | Request | Client chấp nhận những media type nào cho response? |
| `Content-Type` | Response | Nội dung server thực sự gửi có media type nào? |

`Accept` không mô tả request body. `Content-Type` của request cũng không bắt buộc response phải có cùng media type.

Ví dụ một hợp đồng tạo đơn hàng có thể nhận JSON thông thường và trả biểu diễn tùy chỉnh:

```http
POST /orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/vnd.acme.order.v1+json, application/problem+json

{
  "productId": "SKU-100",
  "quantity": 2
}
```

```http
HTTP/1.1 201 Created
Location: /orders/42
Content-Type: application/vnd.acme.order.v1+json

{
  "id": "42",
  "status": "CREATED",
  "total": {
    "amount": "125000",
    "currency": "VND"
  }
}
```

Schema đầu vào tạo đơn và schema đầu ra biểu diễn đơn là hai hợp đồng khác nhau dù cả hai đều dùng JSON. Hợp đồng còn phải nêu rõ client không được tự quyết định các giá trị do server tính như tổng tiền.

Một GET không gửi body thường chỉ cần `Accept` cho mục đích chọn biểu diễn. Thêm `Content-Type` vào GET không khiến response chuyển thành định dạng đó.

### 4.1. Hậu tố không tạo ra wildcard HTTP tự động

Giả sử server chỉ cung cấp `application/vnd.acme.order.v1+json`. Không thể kết luận rằng request sau đã chấp nhận media type đó:

```http
Accept: application/json
```

Theo quy tắc media range của HTTP, `application/json` chỉ rõ một subtype. Quan hệ “cùng dùng cú pháp JSON” không biến hai media type thành cùng một lựa chọn thương lượng.

Các wildcard HTTP thông dụng là `application/*` và `*/*`. Không nên dựa vào `Accept: application/*+json` như một wildcard hậu tố có tính tương thích phổ quát. Một số thư viện hỗ trợ mẫu đó trong bộ so khớp riêng; đó không phải bảo đảm rằng mọi HTTP client, proxy và server đều xử lý như nhau. Xem [RFC 9110, mục 12.5.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.5.1).

Client nên liệt kê tên cụ thể mà nó thực sự xử lý được:

```http
Accept: application/vnd.acme.order.v1+json, application/json;q=0.5, application/problem+json
```

Trong ví dụ này, `q=0.5` thể hiện mức ưu tiên thấp hơn cho JSON thông thường; mục không có `q` có trọng số mặc định là 1. Trọng số không có nghĩa client hiểu mọi schema có cùng cú pháp.

### 4.2. Phân biệt lỗi lựa chọn định dạng và lỗi nội dung

Trong một API chọn chính sách tôn trọng `Accept` và từ chối định dạng không hỗ trợ, có thể thiết kế:

| Tình huống | Kết quả dự kiến theo hợp đồng |
| --- | --- |
| POST gửi `text/plain`, endpoint chỉ nhận `application/json` | `415 Unsupported Media Type` |
| GET chỉ chấp nhận XML, endpoint chỉ xuất JSON | `406 Not Acceptable` |
| Media type đầu vào được hỗ trợ nhưng JSON bị thiếu dấu ngoặc | `400 Bad Request` |
| JSON hợp lệ nhưng vi phạm quy tắc dữ liệu | Mã lỗi validation được API quy định, chẳng hạn `400` hoặc `422` |

Không biến mọi lỗi JSON thành `415`. Đồng thời, HTTP có cho phép server bỏ qua ưu tiên `Accept` trong một số trường hợp; vì vậy chính sách trả `406` cần được xác định rõ trong API thay vì mô tả như một kết quả bắt buộc cho mọi server.

## 5. Khi nào nên dùng media type tùy chỉnh?

Một REST API có thể dùng `application/json` cùng schema và tài liệu endpoint rõ ràng. Không có yêu cầu phải tạo media type riêng cho từng bảng, từng DTO hoặc từng resource.

Media type tùy chỉnh đáng cân nhắc khi có một định dạng cần được nhận diện độc lập: nhiều ứng dụng trao đổi cùng hợp đồng, cần phân biệt những ngữ nghĩa dễ nhầm lẫn, hoặc cần duy trì nhiều biểu diễn không tương thích tại cùng resource.

| Nhu cầu | Hướng lựa chọn |
| --- | --- |
| CRUD đơn giản trong một hệ thống, schema đã được quản lý | `application/json` thường đủ |
| Phản hồi lỗi theo Problem Details | Dùng `application/problem+json` |
| Danh sách thao tác JSON Patch | Dùng `application/json-patch+json` |
| Định dạng đơn hàng riêng được nhiều bên tiêu thụ độc lập | Cân nhắc media type tùy chỉnh và đặc tả đi kèm |
| Đổi tên một field nội bộ chưa được công bố | Xử lý trong mô hình nội bộ; không cần tạo media type mới |

Bắt đầu bằng cách xem định dạng có sẵn có giải quyết đúng nhu cầu hay không. Việc đặt tên mới kéo theo chi phí tài liệu, kiểm thử tương thích, cấu hình gateway, công cụ tạo SDK và vận hành.

### 5.1. Hiểu registration tree trước khi đặt tên

Các tiền tố như `vnd.` và `prs.` biểu thị registration tree. `vnd.` không có nghĩa là dữ liệu bí mật, độc quyền bắt buộc hay đã được một cơ quan chứng nhận an toàn.

Tự viết một tên bắt đầu bằng `vnd.` không đồng nghĩa đã đăng ký nó. Nếu cần sử dụng rộng rãi, người sở hữu định dạng phải xem quy trình đăng ký phù hợp và tránh xung đột tên. Không nên chọn tên mới với `x-` như một quy ước mặc định cho API công khai; `x-` cũng không đồng nhất với `x.` tree. Các cây đăng ký và hạn chế được trình bày tại [RFC 6838, mục 3](https://www.rfc-editor.org/rfc/rfc6838.html#section-3).

Trong bài, `acme` chỉ là tổ chức giả định. Khi áp dụng thực tế, chọn tên có chủ sở hữu rõ ràng, dễ đối chiếu với đặc tả và không giả mạo một media type đã tồn tại.

## 6. Tên tùy chỉnh phải đi cùng hợp đồng cụ thể

Với `application/vnd.acme.order.v1+json`, một bản đặc tả tối thiểu của ví dụ có thể quy định:

| Nội dung hợp đồng | Quy định của ví dụ |
| --- | --- |
| Cú pháp | JSON, mã hóa UTF-8 |
| Giá trị gốc | Object |
| `id` | Chuỗi định danh; không suy diễn thành số để tính toán |
| `status` | Một trong `CREATED`, `PAID`, `CANCELLED` |
| `total.amount` | Chuỗi gồm các chữ số, biểu diễn số tiền nguyên không âm theo đơn vị tiền tệ |
| `total.currency` | `VND` trong phạm vi hợp đồng minh họa này |
| Trường bắt buộc | `id`, `status`, `total`; trong `total` có `amount`, `currency` |
| Trường bổ sung | Client đọc response phải bỏ qua trường chưa biết; server vẫn kiểm soát dữ liệu được công bố |
| Dữ liệu nhạy cảm | Không có thông tin thanh toán bí mật trong biểu diễn này |

Đây là quyết định của ví dụ, không phải quy tắc chung của mọi media type `+json`. Nếu cần nhiều loại tiền hoặc phần thập phân, phải thiết kế lại biểu diễn số tiền và mô tả rõ độ chính xác, cách làm tròn.

Với tài liệu đầu vào, quy tắc chấp nhận trường chưa biết có thể khác đầu ra. Ví dụ, server có thể từ chối trường đầu vào không được phép để tránh việc client tưởng rằng một giá trị đã được cập nhật. Không nên áp dụng cùng một chính sách một cách máy móc cho cả hai chiều.

Đặc tả đầy đủ còn cần ví dụ hợp lệ, ví dụ bị từ chối, các giới hạn kích thước, quy tắc validation, chủ sở hữu và chính sách tương thích. OpenAPI mô tả schema và media type; ý nghĩa nghiệp vụ như “khi nào đơn được hủy” cần thêm mô tả và quy tắc xử lý.

## 7. Phiên bản trong media type là lựa chọn của hợp đồng

Ví dụ có thể công bố hai biểu diễn:

```text
application/vnd.acme.order.v1+json
application/vnd.acme.order.v2+json
```

HTTP không tự chuyển đổi giữa v1 và v2, cũng không suy ra v2 tốt hơn cho mọi client. Server phải có bộ ánh xạ dữ liệu cho từng biểu diễn, còn client phải yêu cầu loại mà nó hiểu.

Một thay đổi từ `amount` dạng chuỗi theo đơn vị tiền tệ sang `amount` dạng số theo đơn vị nhỏ nhất có thể làm số tiền bị hiểu sai dù tài liệu vẫn là JSON hợp lệ. Giữ nguyên tên media type cho thay đổi đó sẽ phá vỡ giả định của client cũ.

Ngược lại, thêm một trường tùy chọn có thể tương thích nếu hợp đồng đã yêu cầu client bỏ qua trường chưa biết. Thêm giá trị enum mới chưa chắc tương thích: ứng dụng có thể dùng nhánh xử lý chỉ chấp nhận các giá trị đã biết.

Một cách khác là định nghĩa parameter như `version=2` cho media type riêng. Đây cũng là quy ước cần được đặc tả, hỗ trợ và kiểm thử rõ ràng. Không tự thêm `version=2` vào `application/json` rồi coi đó là cơ chế phiên bản chuẩn sẵn có.

Nếu hỗ trợ cả `application/json` lẫn media type tùy chỉnh, cần xác định:

1. Chúng có cùng schema và ngữ nghĩa hay không.
2. `application/json` gắn với hợp đồng ổn định nào.
3. Server chọn loại nào khi client không gửi `Accept` hoặc gửi `*/*`.
4. Khi hết hỗ trợ một loại, client nhận phản hồi gì và có lộ trình chuyển đổi nào.

Không âm thầm đổi ý nghĩa của `application/json` theo “phiên bản mới nhất” nếu các client đang dựa vào hợp đồng cũ.

## 8. Ánh xạ đúng trong Java/Spring MVC

Trong Spring MVC, hai thuộc tính mapping phục vụ hai chiều khác nhau:

| Thuộc tính | Header liên quan | Vai trò |
| --- | --- | --- |
| `consumes` | `Content-Type` của request | Giới hạn loại nội dung đầu vào mà endpoint nhận |
| `produces` | `Accept` của request và loại response | Khai báo các media type endpoint có thể tạo |

Đây là các điều kiện lựa chọn handler, không phải lệnh tự chuyển mọi dữ liệu thành định dạng tương ứng. Cách khai báo được mô tả tại [Spring MVC: Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html#mapping-consumes).

Ví dụ dưới đây là controller minh họa cho một ứng dụng đã có Spring MVC và bộ chuyển đổi JSON. Nó cung cấp duy nhất đơn hàng mẫu `42`, dùng Java 17 trở lên để khai báo `record`, không triển khai lưu trữ hoặc nghiệp vụ đơn hàng:

```java
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderRepresentationController {

    public static final String ORDER_V1 =
            "application/vnd.acme.order.v1+json";

    @GetMapping(path = "/orders/{id}", produces = ORDER_V1)
    public ResponseEntity<OrderDocument> getOrder(
            @PathVariable("id") String id) {

        if (!"42".equals(id)) {
            return ResponseEntity.notFound().build();
        }

        OrderDocument order = new OrderDocument(
                "42",
                "PAID",
                new Money("125000", "VND")
        );

        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(ORDER_V1))
                .varyBy("Accept")
                .cacheControl(CacheControl.noStore())
                .body(order);
    }

    public record OrderDocument(String id, String status, Money total) {
    }

    public record Money(String amount, String currency) {
    }
}
```

Các quyết định đáng chú ý:

- `produces` và `contentType(...)` cùng khai báo một media type, tránh nói một kiểu ở mapping nhưng gửi kiểu khác.
- Chỉ `id=42` có dữ liệu mẫu; các định danh khác trả `404` không có body trong controller này.
- `noStore()` giữ ví dụ ngoài phạm vi lưu cache; chính sách cache thực tế cần được thiết kế theo độ nhạy và vòng đời dữ liệu.
- `Vary: Accept` ghi nhận chiều thương lượng của biểu diễn. Nếu sau này cho phép cache và nhiều loại biểu diễn, cấu hình cache phải tiếp tục xét chiều này.

Khi tạo một endpoint nhận JSON thông thường nhưng xuất biểu diễn đơn hàng riêng, phần annotation có thể là:

```java
@PostMapping(
        path = "/orders",
        consumes = "application/json",
        produces = OrderRepresentationController.ORDER_V1
)
```

Đây chỉ là phần khai báo mapping cho một method tạo đơn hàng, không phải phần triển khai bổ sung vào controller mẫu. Method thực tế cần DTO đầu vào, validation, nghiệp vụ tạo đơn, `201 Created` và `Location` phù hợp.

### 8.1. Converter đọc được chưa có nghĩa endpoint chấp nhận

Đường đi khái quát của một request có body là:

```text
Content-Type của request
    -> điều kiện consumes của handler
    -> message converter đọc nội dung
    -> DTO và validation
    -> xử lý nghiệp vụ
```

Đầu ra cũng cần cả điều kiện `produces` phù hợp với `Accept` và converter có thể ghi đối tượng dưới media type được chọn.

Ví dụ cụ thể, `MappingJackson2HttpMessageConverter` của Spring Framework 6.2 mặc định hỗ trợ `application/json` và mẫu `application/*+json` trong danh sách media type của converter. Đây là khả năng của converter được nêu trong [Javadoc chính thức](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/converter/json/MappingJackson2HttpMessageConverter.html).

Tuy nhiên, handler chỉ khai báo `consumes = "application/json"` không tự trở thành handler cho mọi subtype kết thúc bằng `+json`. Điều kiện mapping và khả năng converter là hai bước riêng.

Khi đổi phiên bản Spring, thư viện JSON hoặc cấu hình converter, cần kiểm tra cấu hình thực tế. Không suy ra từ một converter rằng tất cả môi trường Java/Spring đều có cùng hành vi.

### 8.2. Tránh mở quá rộng đầu vào

Một endpoint có thể được cấu hình nhận nhiều media type cụ thể nếu hợp đồng của chúng đã được hỗ trợ. Không nên cho phép tất cả `application/*+json` rồi mặc định mọi tài liệu đều là DTO đơn hàng.

Ví dụ, tài liệu `application/problem+json` và `application/json-patch+json` đều đọc được bằng parser JSON, nhưng chúng không phải biểu diễn đơn hàng. Bộ xử lý cần chọn đúng ngữ nghĩa trước khi chấp nhận dữ liệu cho nghiệp vụ.

Tương tự, việc đổi annotation thành `produces = "*/*"` không làm ứng dụng có khả năng tạo mọi định dạng. Khả năng đó còn phụ thuộc vào bộ chuyển đổi và mã tạo biểu diễn.

## 9. Ghi rõ media type trong OpenAPI

Trong OpenAPI, từng khóa trong `content` mô tả một media type và gắn với schema, ví dụ tương ứng. Không chỉ ghi “trả JSON” nếu client cần một media type cụ thể. Xem [OpenAPI 3.1.1, Media Type Object](https://spec.openapis.org/oas/v3.1.1.html#media-type-object).

Đặc tả rút gọn sau mô tả GET mẫu ở trên:

```yaml
openapi: 3.1.1
info:
  title: Order Representation Demo
  version: 1.0.0

paths:
  /orders/{id}:
    get:
      summary: Đọc đơn hàng mẫu
      description: Chỉ định danh 42 có dữ liệu trong ví dụ.
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Biểu diễn đơn hàng phiên bản 1
          content:
            application/vnd.acme.order.v1+json:
              schema:
                $ref: '#/components/schemas/OrderV1'
              example:
                id: '42'
                status: PAID
                total:
                  amount: '125000'
                  currency: VND
        '404':
          description: Không có đơn hàng mẫu mang định danh này
        '406':
          description: Không có biểu diễn phù hợp với Accept

components:
  schemas:
    OrderV1:
      type: object
      required: [id, status, total]
      properties:
        id:
          type: string
        status:
          type: string
          enum: [CREATED, PAID, CANCELLED]
        total:
          $ref: '#/components/schemas/MoneyV1'
      additionalProperties: true

    MoneyV1:
      type: object
      required: [amount, currency]
      properties:
        amount:
          type: string
          pattern: '^[0-9]+$'
          description: Số tiền nguyên không âm theo đơn vị VND
        currency:
          type: string
          enum: [VND]
      additionalProperties: true
```

Trong ví dụ, `additionalProperties: true` biểu đạt việc schema cho phép trường bổ sung. Điều đó không tự buộc một SDK sinh ra phải bỏ qua trường chưa biết; cấu hình và kiểm thử client vẫn phải thống nhất với hợp đồng.

Nếu endpoint nhận body, khai báo media type đầu vào dưới `requestBody.content`. Nếu vừa hỗ trợ JSON thông thường vừa hỗ trợ media type tùy chỉnh ở đầu ra, liệt kê từng loại dưới `responses.<status>.content` và bảo đảm server thực sự tạo được chúng.

Không cần tạo header parameter tên `Accept` hoặc `Content-Type` để thay thế các khai báo `content`. Điều cần mô tả là những loại nội dung mà operation thực sự nhận và trả.

## 10. Phản hồi lỗi cũng có media type riêng

Một API có thể trả biểu diễn đơn hàng khi thành công và Problem Details khi lỗi. Định dạng JSON của Problem Details được nhận diện bằng `application/problem+json`, theo [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html#section-3).

Ví dụ hợp đồng của một API đầy đủ, độc lập với phần xử lý lỗi tối giản trong controller mẫu:

```http
GET /orders/999 HTTP/1.1
Host: api.example.test
Accept: application/vnd.acme.order.v1+json, application/problem+json
```

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/order-not-found",
  "title": "Không tìm thấy đơn hàng",
  "status": 404,
  "detail": "Không có đơn hàng phù hợp với yêu cầu.",
  "instance": "/orders/999"
}
```

Các URI trong ví dụ là giả định. API thực tế phải quyết định nội dung nào có thể công bố cho người gọi, đặc biệt khi định danh có thể được dùng để dò dữ liệu.

Client cần xét mã trạng thái và `Content-Type` của response trước khi ánh xạ body. Không deserialize mọi response thành `OrderDocument` chỉ vì endpoint nằm dưới `/orders`.

Đưa `application/problem+json` vào `Accept` cũng chưa đủ để server tự có bộ xử lý lỗi đó. Ứng dụng cần cấu hình xử lý exception và khai báo schema lỗi trong hợp đồng tương ứng. Controller GET của phần 8 chỉ minh họa phản hồi thành công và `404` không body.

## 11. Cache, quyền truy cập và xác thực không được suy ra từ tên

Khi cùng URI có nhiều biểu diễn được chọn theo `Accept` và response có thể được cache, cần xem xét `Vary: Accept` cùng cấu hình cache hoặc CDN. Nếu bỏ qua chiều chọn biểu diễn, client có thể nhận lại tài liệu được lưu cho một yêu cầu khác.

Chỉ thêm `Vary` không tự giải quyết việc cache dữ liệu riêng tư. Chọn `Cache-Control` phù hợp, kiểm soát cache dùng chung và bảo đảm kết quả phân quyền không bị trộn giữa những người gọi. Với ví dụ có dữ liệu riêng và chưa thiết kế cache, `no-store` là một lựa chọn minh họa đơn giản.

Media type cũng không cấp quyền. Người gọi gửi `Content-Type: application/vnd.acme.order.v1+json` không chứng minh rằng họ được sửa đơn, đã xác thực, hoặc dữ liệu an toàn để tin cậy.

Ở đầu vào, vẫn phải giới hạn kích thước, độ sâu cấu trúc và trường được cập nhật. Ở đầu ra, dùng DTO có các trường được phép công bố; không trả nguyên entity chứa trường nội bộ chỉ vì serializer có thể ghi JSON.

Nếu xử lý endpoint cần idempotency, media type không thay thế hợp đồng idempotency. Máy chủ cần xác định cách so sánh các yêu cầu gửi lại; cùng dữ liệu nghiệp vụ có thể được serialize thành những chuỗi byte JSON khác nhau do thứ tự thuộc tính hoặc khoảng trắng.

## 12. Thực hành quan sát hành vi của hợp đồng

Các lệnh sau dành cho môi trường người học tự chạy controller mẫu, giả định ứng dụng ở cổng `8080`. Trong PowerShell, dùng `curl.exe` để gọi chương trình curl.

### 12.1. Yêu cầu đúng media type

```powershell
curl.exe -i -H "Accept: application/vnd.acme.order.v1+json" "http://localhost:8080/orders/42"
```

Kỳ vọng từ controller mẫu: `200`, `Content-Type: application/vnd.acme.order.v1+json`, `Cache-Control` có `no-store`, `Vary` có `Accept`, và body đúng schema đã mô tả.

Không dựa vào thứ tự xuất hiện của header hay thứ tự các thuộc tính JSON để xác định thành công.

### 12.2. Thử yêu cầu JSON thông thường

```powershell
curl.exe -i -H "Accept: application/json" "http://localhost:8080/orders/42"
```

Với mapping chỉ `produces = ORDER_V1`, Spring MVC thông thường trả `406` khi không có biểu diễn phù hợp. Đây là cách quan sát rằng hậu tố `+json` không tự mở rộng lựa chọn của handler thành `application/json`.

Nếu ứng dụng có cấu hình content negotiation hoặc bộ xử lý lỗi riêng, đối chiếu kết quả với cấu hình đó. Không coi sự khác biệt của một môi trường là lý do để bỏ qua hợp đồng.

### 12.3. Yêu cầu một kiểu không được hỗ trợ

```powershell
curl.exe -i -H "Accept: application/xml" "http://localhost:8080/orders/42"
```

Theo chính sách của ví dụ, kết quả mong đợi là `406`. Việc chỉ thay header `Content-Type` của response sang XML sẽ không sửa được lỗi: server cần thực sự tạo nội dung XML nếu muốn công bố hỗ trợ XML.

### 12.4. Kiểm tra các trường hợp đầu vào khi mở rộng POST

Sau khi tự triển khai POST theo hợp đồng ở phần 4, người học nên kiểm tra các tình huống sau:

| Đầu vào | Điều cần quan sát |
| --- | --- |
| `application/json`, JSON hợp lệ | Tạo đơn theo nghiệp vụ và trả đúng media type đầu ra |
| `text/plain`, nội dung trông giống JSON | Bị từ chối theo chính sách `consumes`, không tự đoán định dạng |
| `application/json`, JSON sai cú pháp | Báo lỗi đọc nội dung, không nhầm thành loại nội dung không hỗ trợ |
| `application/problem+json`, object có vài trường trùng DTO | Không nhận như yêu cầu tạo đơn chỉ vì parser đọc được |
| `Accept` chỉ chấp nhận loại server không tạo được | Xử lý đúng chính sách thương lượng đã công bố |

Đây là bài thực hành dành cho người học; các endpoint POST và PATCH cần được triển khai riêng trước khi chạy các tình huống tương ứng.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `Accept` để mô tả request body | Endpoint hoặc client chọn nhầm định dạng | Đặt loại body gửi đi trong `Content-Type` |
| Cho rằng mọi `+json` có cùng schema | Đọc được JSON nhưng xử lý sai ý nghĩa | Nhận diện media type cụ thể và áp dụng hợp đồng tương ứng |
| Tạo subtype mới nhưng không viết đặc tả | Client không biết trường và quy tắc tương thích | Viết schema, ngữ nghĩa, ví dụ và chính sách thay đổi |
| Chỉ đổi header để “hỗ trợ” XML hoặc PDF | Nội dung thực tế không khớp khai báo | Tạo biểu diễn đúng bằng converter hoặc bộ sinh phù hợp |
| Cho rằng `vnd.` đồng nghĩa đã đăng ký | Công bố sai trạng thái của định dạng | Tách việc đặt tên với thủ tục đăng ký |
| Dùng `application/*+json` như bảo đảm wildcard HTTP | Hành vi khác nhau giữa các thành phần | Liệt kê loại cụ thể hoặc kiểm soát và kiểm thử cơ chế mở rộng |
| Dùng tên v1 cho nội dung đã đổi đơn vị tiền | Client cũ hiểu sai dữ liệu | Duy trì hợp đồng cũ hoặc công bố biểu diễn mới |
| Chỉ kiểm tra body khi kiểm thử | Bỏ sót `Content-Type`, thương lượng và cache | Kiểm tra status, header và schema cùng nhau |

## 14. Ghi nhớ khi thiết kế biểu diễn

Media type xác định cách diễn giải một nội dung. Structured syntax suffix giúp nhận biết cú pháp nền để xử lý tổng quát; hợp đồng của media type cụ thể mới giải thích các quy tắc đặc thù.

Với một REST API Java/Spring, hãy bắt đầu từ biểu diễn cần trao đổi, tìm media type có sẵn phù hợp, rồi mô tả schema và ngữ nghĩa. Chỉ thêm media type tùy chỉnh khi nó tạo ra giá trị nhận diện rõ ràng và có thể được duy trì xuyên suốt tài liệu, code, client, xử lý lỗi và kiểm thử.
