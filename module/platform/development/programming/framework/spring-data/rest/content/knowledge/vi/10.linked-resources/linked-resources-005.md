# `text/uri-list` và cách biểu diễn một hoặc nhiều URI

Trong REST API, client thường gửi dữ liệu của một resource dưới dạng JSON. Tuy nhiên, khi cần tham chiếu đến resource đã tồn tại, gửi toàn bộ object có thể dư thừa và dễ tạo ra nhiều nguồn dữ liệu không nhất quán. `text/uri-list` giải quyết trường hợp đó bằng một body văn bản đơn giản: mỗi dòng chứa một URI trỏ đến một resource.

Trong Spring Data REST, media type này đặc biệt hữu ích khi làm việc với **association resource**. Thay vì gửi một object Customer hoặc một mảng Product đầy đủ, client gửi URI của các resource cần liên kết với entity hiện tại.

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích `text/uri-list` là gì và phân biệt nó với JSON.
- Biểu diễn một URI hoặc nhiều URI trong cùng một request body.
- Đặt đúng HTTP header `Content-Type`.
- Tìm association link trong HAL response của Spring Data REST.
- Dùng `PUT`, `POST` và `DELETE` đúng mục đích khi cập nhật quan hệ.
- Nhận biết các lỗi thường gặp khi gửi URI list.

## 2. URI, URL và vai trò của media type

**URI (Uniform Resource Identifier)** là chuỗi định danh một tài nguyên. URL là một dạng URI cho biết cách định vị tài nguyên, chẳng hạn:

~~~text
https://api.example.com/customers/42
~~~

Trong ví dụ REST thông thường, URI này xác định customer có id là `42`. Client có thể dùng URI đó để yêu cầu server đọc resource, hoặc gửi URI cho một endpoint khác để thiết lập quan hệ với resource ấy.

Media type mô tả cấu trúc của phần body HTTP. `text/uri-list` cho server biết rằng body là danh sách URI ở dạng văn bản thuần. Nó không có nghĩa là server sẽ tự động tải mọi URI từ Internet; ứng dụng nhận request quyết định cách phân giải và kiểm tra từng URI.

Hai header cần phân biệt:

- `Content-Type`: định dạng của body mà client đang gửi.
- `Accept`: định dạng response mà client muốn nhận.

Khi gửi danh sách URI cho association resource, header quan trọng là:

~~~http
Content-Type: text/uri-list
~~~

Nếu muốn nhận response theo HAL, client có thể đồng thời gửi:

~~~http
Accept: application/hal+json
~~~

Không dùng `Accept` thay cho `Content-Type`: hai header mô tả hai chiều khác nhau của trao đổi HTTP.

## 3. Cú pháp của `text/uri-list`

Đây là định dạng theo từng dòng. Mỗi URI nằm trọn trên một dòng riêng.

### 3.1. Một URI

Body chỉ có một dòng:

~~~text
https://api.example.com/customers/42
~~~

Server nhận được một tham chiếu đến customer 42. Không cần bọc URI trong dấu nháy kép và không cần tạo object JSON.

### 3.2. Nhiều URI

Khi cần gửi nhiều resource, đặt mỗi URI trên một dòng:

~~~text
https://api.example.com/products/10
https://api.example.com/products/11
https://api.example.com/products/12
~~~

Ba dòng tương ứng với ba URI. Đây là cách biểu diễn danh sách; không dùng dấu phẩy, dấu chấm phẩy hoặc dấu ngoặc vuông để phân tách.

### 3.3. Dòng chú thích

Theo định dạng được mô tả trong RFC 2483, một dòng bắt đầu bằng ký tự `#` là dòng chú thích và được bỏ qua khi xử lý:

~~~text
# Các URI thay thế cho tài nguyên gốc
https://cdn.example.com/files/manual.pdf
https://backup.example.com/files/manual.pdf
~~~

Ký tự `#` chỉ mở đầu comment khi nó là ký tự đầu tiên của dòng. Nếu `#` xuất hiện bên trong URI, ví dụ ở phần fragment, nó vẫn là một phần của URI:

~~~text
https://docs.example.com/guide#installation
~~~

Với request cập nhật association trong Spring Data REST, nên gửi trực tiếp các URI cần liên kết và tránh thêm dòng chú thích vào body. Cách này giữ payload rõ ràng và không phụ thuộc vào cách một parser cụ thể xử lý comment.

### 3.4. Quy tắc cần nhớ

| Thành phần | Quy tắc |
|---|---|
| Phân tách | Một URI trên một dòng |
| Dòng chú thích | Dòng bắt đầu bằng `#` theo định dạng RFC |
| Ngắt dòng | RFC mô tả CRLF cho các dòng của định dạng `text/*` |
| URI dài | Không tự chèn ngắt dòng vào giữa URI |
| Dấu phân cách | Không dùng dấu phẩy hoặc dấu chấm phẩy |
| Cấu trúc | Không bọc danh sách bằng JSON array |
| Header request | Dùng `Content-Type: text/uri-list` |

Một URI rất dài vẫn là một dòng duy nhất. Nếu tự xuống dòng giữa URI, server có thể hiểu phần trước và phần sau là hai URI khác nhau hoặc từ chối payload.

Trong file chứa nhiều URI, hãy bảo đảm mỗi dòng được kết thúc đúng cách. RFC mô tả CRLF (`\r\n`) cho định dạng văn bản này. Khi tạo payload bằng code, nên chủ động dùng CRLF để tránh phụ thuộc vào kiểu xuống dòng của hệ điều hành.

## 4. `text/uri-list` trong Spring Data REST

Spring Data REST xuất các repository thành REST resource. Với một repository quản lý entity `Order`, API thường có:

- Collection resource: danh sách order, ví dụ `/orders`.
- Item resource: một order cụ thể, ví dụ `/orders/1`.
- Association resource: resource đại diện cho quan hệ của order với entity khác, ví dụ `/orders/1/customer` hoặc `/orders/1/products`.

Association resource được tạo từ các association của domain object. Tên và đường dẫn mặc định dựa trên tên property; có thể tùy chỉnh bằng `@RestResource` trên property. Vì vậy, client nên đọc link mà server trả về thay vì tự đoán URL.

### 4.1. Khám phá association link qua HAL

Gửi GET đến item resource:

~~~http
GET /orders/1 HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
~~~

Response có thể chứa các link tương tự ví dụ sau:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/1"
    },
    "customer": {
      "href": "http://localhost:8080/orders/1/customer"
    },
    "products": {
      "href": "http://localhost:8080/orders/1/products"
    }
  }
}
~~~

Đây là ví dụ minh họa. Tên relation và URL thực tế phụ thuộc vào domain model, cấu hình repository và các tùy chỉnh của ứng dụng. Client lấy `href` của relation cần thao tác rồi gửi request đến đúng association resource đó.

### 4.2. Các HTTP method của association resource

| Method | Ý nghĩa | Body |
|---|---|---|
| `GET` | Đọc trạng thái association | Không cần `text/uri-list`; tài liệu Spring Data REST liệt kê HAL/JSON |
| `PUT` | Gắn resource được chỉ định bởi URI vào association | `text/uri-list` |
| `POST` | Chỉ dành cho collection association; thêm phần tử mới vào collection | `text/uri-list` |
| `DELETE` | Hủy liên kết association | Thông thường không cần body |

Một điểm cần phân biệt: `POST /orders` là thao tác tạo Order mới trên collection resource; `POST /orders/1/products` là thao tác thêm Product vào collection association của Order 1. Hai endpoint có ý nghĩa khác nhau dù cùng dùng HTTP method POST.

### 4.3. Quan hệ to-one: gửi đúng một URI bằng PUT

Giả sử Order có một Customer. Để liên kết Order 1 với Customer 42, gửi URI của Customer đến association link:

~~~http
PUT /orders/1/customer HTTP/1.1
Host: localhost:8080
Content-Type: text/uri-list

http://localhost:8080/customers/42
~~~

Có thể thực hiện bằng curl:

~~~bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data-binary "http://localhost:8080/customers/42" \
  "http://localhost:8080/orders/1/customer"
~~~

Body là URI của Customer, không phải JSON của Customer. Spring Data REST dùng URI đó để phân giải resource rồi gắn vào association.

Với association to-one, chỉ gửi một URI. Nếu body chứa nhiều URI, Spring Data REST trả về `400 Bad Request` vì một quan hệ chỉ nhận một đích.

### 4.4. Quan hệ collection: gửi nhiều URI

Giả sử Order có nhiều Product. Tạo file `products.uris` với nội dung:

~~~text
http://localhost:8080/products/10
http://localhost:8080/products/11
http://localhost:8080/products/12
~~~

Để thêm các Product này vào collection association, gửi POST đến link `products`:

~~~bash
curl -i -X POST \
  -H "Content-Type: text/uri-list" \
  --data-binary @products.uris \
  "http://localhost:8080/orders/1/products"
~~~

Mỗi dòng trong file là một resource cần thêm. POST trên association resource chỉ áp dụng cho collection association và có ý nghĩa thêm phần tử vào collection.

Nếu cần gửi tập URI để gắn với association bằng PUT, dùng cùng cấu trúc body nhưng thay HTTP method:

~~~bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data-binary @products.uris \
  "http://localhost:8080/orders/1/products"
~~~

PUT và POST không đồng nghĩa: PUT gắn các resource được chỉ định vào association; POST thêm phần tử mới vào collection association. Hãy chọn method theo mục tiêu cập nhật và semantics mà API công bố.

### 4.5. Hủy liên kết

DELETE trên association resource dùng để unbind association:

~~~bash
curl -i -X DELETE \
  "http://localhost:8080/orders/1/customer"
~~~

Hủy liên kết không đồng nghĩa xóa entity đích khỏi repository. Ví dụ, bỏ liên kết Customer khỏi Order không có nghĩa là xóa Customer 42. Việc xóa entity là một thao tác khác trên item resource của entity đó.

Khả năng thực hiện method còn phụ thuộc vào association và cấu hình export của ứng dụng. Nếu method không được hỗ trợ hoặc association không cho phép thao tác đó, server có thể trả về `405 Method Not Allowed`.

## 5. Tạo payload từ Java client

Khi client đã có danh sách `URI`, có thể chuyển chúng thành chuỗi nhiều dòng. Ví dụ với Spring WebClient:

~~~java
import java.net.URI;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

List<URI> productUris = List.of(
    URI.create("http://localhost:8080/products/10"),
    URI.create("http://localhost:8080/products/11"),
    URI.create("http://localhost:8080/products/12")
);

String uriListBody = productUris.stream()
    .map(URI::toASCIIString)
    .collect(Collectors.joining("\r\n", "", "\r\n"));

WebClient client = WebClient.create();

client.post()
    .uri("http://localhost:8080/orders/1/products")
    .contentType(MediaType.parseMediaType("text/uri-list"))
    .bodyValue(uriListBody)
    .retrieve()
    .toBodilessEntity()
    .block();
~~~

Điểm quan trọng trong đoạn code:

1. Mỗi phần tử của danh sách trở thành một dòng.
2. Dùng `URI` để biểu diễn và kiểm tra cú pháp URI ở phía client.
3. `toASCIIString()` tạo biểu diễn URI phù hợp để truyền qua HTTP.
4. `contentType(...)` đặt đúng media type cho request body.
5. Không serialize danh sách thành JSON trước khi gửi.

Nếu dùng `RestClient` hoặc một HTTP client khác, nguyên tắc vẫn giống nhau: body là chuỗi URI theo dòng và header `Content-Type` là `text/uri-list`.

Đối với endpoint tự xây dựng bằng `@RestController`, không nên mặc định rằng tham số `@RequestBody List<URI>` sẽ được Spring Data REST tự xử lý. `UriListHttpMessageConverter` của Spring Data REST phục vụ việc đọc/ghi representation model của Spring Data REST. Endpoint riêng cần định nghĩa rõ cách nhận body, parse từng dòng và xử lý lỗi, hoặc đăng ký converter phù hợp với kiểu dữ liệu của endpoint.

## 6. Kiểm tra request và xử lý lỗi

Khi request không hoạt động như mong đợi, kiểm tra lần lượt:

1. **Đúng association link chưa?** Đọc item resource và lấy đúng `href` từ HAL response. Không đoán đường dẫn theo tên property nếu API đã cung cấp link.
2. **Đúng Content-Type chưa?** Body dạng danh sách URI phải đi cùng `Content-Type: text/uri-list`.
3. **Body có đúng cấu trúc không?** Mỗi dòng là một URI; không có JSON brackets, dấu phẩy, dấu nháy hoặc ký tự xuống dòng chèn vào giữa URI.
4. **URI có trỏ đến resource mà API phân giải được không?** Dùng URI của resource đã được export và kiểm tra quyền truy cập.
5. **Method có phù hợp cardinality không?** PUT trên to-one chỉ nhận một URI; POST chỉ được hỗ trợ cho collection association.
6. **Method có được export không?** Cấu hình repository và association có thể giới hạn các HTTP method được phép.

Một số dấu hiệu thường gặp:

| HTTP status / hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| `400 Bad Request` | Body không hợp lệ hoặc gửi nhiều URI cho association to-one |
| `405 Method Not Allowed` | Method không được export hoặc association không cho phép thao tác |
| `415 Unsupported Media Type` | Header `Content-Type` không khớp định dạng body mà endpoint hỗ trợ |
| Không tìm thấy resource đích | URI sai, resource không tồn tại hoặc API không thể phân giải URI đó |

Status cụ thể ngoài các trường hợp được tài liệu Spring Data REST nêu rõ còn phụ thuộc vào endpoint, converter, cấu hình và exception handler của ứng dụng. Hãy đọc response body và log phía server thay vì chỉ dựa vào status code.

Sau khi cập nhật thành công, có thể GET lại item resource hoặc association resource để xác nhận quan hệ đã thay đổi như mong muốn.

## 7. Các lỗi thiết kế và sử dụng thường gặp

### Gửi JSON array nhưng khai báo `text/uri-list`

Payload sau không phải `text/uri-list`:

~~~json
[
  "http://localhost:8080/products/10",
  "http://localhost:8080/products/11"
]
~~~

Đây là JSON array. Nếu endpoint yêu cầu `text/uri-list`, hãy chuyển thành các dòng URI thuần.

### Gửi nhiều URI trên cùng một dòng

Payload sau không phải danh sách URI theo định dạng này:

~~~text
http://localhost:8080/products/10, http://localhost:8080/products/11
~~~

Server có thể xem toàn bộ dòng là một URI không hợp lệ. Hãy đặt mỗi URI trên một dòng.

### Dùng sai endpoint

Gửi URI đến `/orders` không tương đương gửi URI đến `/orders/1/products`. Endpoint đầu tiên là collection resource dùng để tạo Order; endpoint thứ hai là association resource của Order 1.

### Gửi nhiều URI cho quan hệ to-one

Một association to-one chỉ có một đích. Gửi hai dòng URI cho association như `customer` dẫn đến lỗi `400 Bad Request`. Nếu domain model thực sự cần nhiều đối tượng, hãy kiểm tra lại cardinality của association và dùng endpoint collection tương ứng.

### Xem URI là quyền truy cập

URI hợp lệ về cú pháp không chứng minh rằng caller được phép liên kết resource đó. Server vẫn phải kiểm tra resource tồn tại, thuộc phạm vi API được hỗ trợ và caller có quyền thực hiện thao tác. Không tin cậy URI tùy ý do client cung cấp.

## 8. Lưu ý bảo mật

Một URI list có thể dẫn client hoặc server tới các tài nguyên nhạy cảm. RFC 2483 cảnh báo nguy cơ URI bị giả mạo, chuyển hướng độc hại và làm lộ thông tin qua danh sách URI. Khi triển khai API:

- Xác thực và phân quyền trên từng resource được tham chiếu.
- Nếu API chỉ cho phép URI nội bộ, kiểm tra scheme, host và đường dẫn theo chính sách của ứng dụng.
- Không tự động gọi HTTP đến URI do người dùng gửi nếu không có kiểm soát chống SSRF.
- Tránh ghi log đầy đủ URI có chứa token hoặc dữ liệu nhạy cảm trong query string.
- Không coi việc parse URI thành công là bằng chứng resource hợp lệ hoặc caller có quyền sử dụng resource.

## 9. Checklist trước khi gửi request

- [ ] Đã đọc item resource và lấy association `href` từ HAL.
- [ ] Đã chọn đúng HTTP method cho to-one hoặc collection association.
- [ ] Đã đặt `Content-Type: text/uri-list`.
- [ ] Mỗi URI nằm trên một dòng riêng.
- [ ] Không gửi JSON array, dấu phẩy hoặc dấu nháy quanh URI.
- [ ] To-one chỉ có đúng một URI.
- [ ] Các URI đích thuộc API và caller có quyền liên kết chúng.
- [ ] Đã kiểm tra response và GET lại association sau khi cập nhật.

## 10. Kết luận

`text/uri-list` là một định dạng văn bản nhỏ gọn để truyền một hoặc nhiều tham chiếu resource. Quy tắc cốt lõi là **một URI trên mỗi dòng** và khai báo đúng `Content-Type`. Trong Spring Data REST, hãy lấy association link từ HAL, gửi URI đến association resource và chọn PUT, POST hoặc DELETE theo semantics của quan hệ. Khi hiểu rõ ranh giới giữa collection resource, item resource và association resource, việc liên kết entity qua REST trở nên rõ ràng và ít lỗi hơn.

## Tài liệu tham khảo

- [RFC 2483 — URI Resolution Services Necessary for URN Resolution, Section 5](https://www.rfc-editor.org/rfc/rfc2483.html#section-5): định nghĩa định dạng `text/uri-list`, comment và quy tắc mỗi URI trên một dòng.
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): mô tả collection, item và association resource; các HTTP method và media type được hỗ trợ.
- [Spring Data REST — UriListHttpMessageConverter API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/convert/UriListHttpMessageConverter.html): converter dùng để render các link trong representation model thành `text/uri-list` và parse request có media type này.
