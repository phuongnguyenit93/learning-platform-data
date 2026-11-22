# OPTIONS và Allow để kiểm tra HTTP method khả dụng

Khi tích hợp với Spring Data REST, client thường biết URL của một tài nguyên nhưng chưa chắc endpoint đó hỗ trợ những HTTP method nào. Một collection, một item, search resource và association resource có thể có các thao tác khác nhau. HTTP `OPTIONS` cho phép client hỏi khả năng của một target resource; response thường dùng header `Allow` để công bố các method được hỗ trợ.

## 1. OPTIONS dùng để làm gì?

`OPTIONS` là HTTP method dùng để hỏi server về các tùy chọn giao tiếp có sẵn cho một resource hoặc server. Request nhắm đến một URI cụ thể giúp client tìm hiểu endpoint đó hỗ trợ những thao tác nào mà không cần thực hiện thao tác đọc hoặc ghi dữ liệu như GET, POST hay DELETE.

Ví dụ:

```http
OPTIONS /people/42 HTTP/1.1
Host: api.example.test
Accept: application/hal+json
```

Server có thể trả response thành công cùng header:

```http
HTTP/1.1 200 OK
Allow: GET, HEAD, PUT, PATCH, DELETE, OPTIONS
```

Danh sách trên chỉ là ví dụ minh họa. Các method thực tế phụ thuộc endpoint, repository được export, cấu hình Spring Data REST, Spring MVC, security và phiên bản framework đang chạy.

Một response OPTIONS thường không cần trả representation của entity. Mục tiêu chính là công bố khả năng giao tiếp qua status và response headers. Client nên đọc header thay vì mong đợi JSON chứa dữ liệu của resource.

## 2. Allow cho biết điều gì?

`Allow` là response header liệt kê các HTTP method mà target resource hiện hỗ trợ. Các method được phân tách bằng dấu phẩy.

Ví dụ:

```http
Allow: GET, HEAD, PUT, PATCH, DELETE, OPTIONS
```

Trong ví dụ này, endpoint công bố các method GET, HEAD, PUT, PATCH, DELETE và OPTIONS. Client có thể dùng thông tin này để quyết định thao tác tiếp theo hoặc hiển thị những hành động phù hợp trong giao diện.

Cần hiểu đúng phạm vi của header:

- `Allow` mô tả method được hỗ trợ tại resource được hỏi, không phải danh sách method của toàn bộ API.
- Collection và item có thể trả các danh sách khác nhau.
- Association resource và search resource cũng có thể có method riêng.
- Header phản ánh khả năng hiện tại của server; cấu hình hoặc phiên bản triển khai thay đổi có thể làm danh sách thay đổi.
- Có method trong `Allow` không bảo đảm mọi request cụ thể đều thành công. Body vẫn có thể sai, dữ liệu có thể không hợp lệ, resource có thể không ở trạng thái cho phép thao tác hoặc caller có thể thiếu quyền.

Theo HTTP semantics, response `405 Method Not Allowed` phải có header `Allow` để chỉ ra các method hiện được hỗ trợ cho target resource. Điều này hữu ích khi client gửi một method không được endpoint chấp nhận.

## 3. Gửi OPTIONS bằng curl

Có thể dùng curl để kiểm tra một endpoint:

```bash
curl -i -X OPTIONS https://api.example.test/people
```

Tùy cách server triển khai, có thể nhận response như sau:

```http
HTTP/1.1 200 OK
Allow: GET, HEAD, POST, OPTIONS
```

Sau đó kiểm tra một item cụ thể:

```bash
curl -i -X OPTIONS https://api.example.test/people/42
```

Một item có thể công bố các method khác collection, ví dụ:

```http
HTTP/1.1 200 OK
Allow: GET, HEAD, PUT, PATCH, DELETE, OPTIONS
```

Đây là hai response giả định để minh họa cách đọc kết quả, không phải cam kết rằng mọi repository Spring Data REST đều trả đúng các method trên. Hãy gọi chính endpoint đang tích hợp và đọc response thực tế.

Nếu endpoint yêu cầu authentication, gửi credentials theo cơ chế mà ứng dụng đang dùng. Khi nhận `401 Unauthorized` hoặc `403 Forbidden`, cần phân biệt lỗi xác thực/phân quyền với việc method không được hỗ trợ.

## 4. Kiểm tra các loại resource trong Spring Data REST

Không nên kiểm tra một URL rồi áp dụng danh sách `Allow` đó cho mọi endpoint khác. Trong Spring Data REST, mỗi loại resource đại diện cho một nhóm thao tác riêng.

| Resource | Ví dụ URL | Điều cần kiểm tra |
|---|---|---|
| Collection | `/people` | Đọc danh sách, tạo item và các method collection được export |
| Item | `/people/42` | Đọc, cập nhật hoặc xóa một entity |
| Search resource | `/people/search` | Khám phá và gọi query methods được export |
| Association | `/people/42/orders` | Đọc hoặc thay đổi quan hệ giữa các entity |

Ví dụ có thể lần lượt gửi:

```bash
curl -i -X OPTIONS https://api.example.test/people
curl -i -X OPTIONS https://api.example.test/people/42
curl -i -X OPTIONS https://api.example.test/people/search
curl -i -X OPTIONS https://api.example.test/people/42/orders
```

Các URL trên là ví dụ. Base path, collection resource rel, item resource rel và association path của ứng dụng có thể khác. Hãy dùng URL thực tế mà API công bố trong HAL links hoặc tài liệu endpoint.

Spring Data REST tạo các handler dựa trên repository và cấu hình export. Việc repository có method Java không đồng nghĩa method đó luôn được công bố qua REST. Chẳng hạn, method hoặc repository bị đánh dấu `@RestResource(exported = false)` sẽ không được export theo cấu hình tương ứng. Các custom repository methods cũng cần được export và mapping đúng thì client mới gọi được qua HTTP.

Do đó, OPTIONS là cách quan sát endpoint đang chạy. Nó bổ sung cho việc đọc repository configuration và HAL links, chứ không thay thế hiểu biết về API contract.

## 5. OPTIONS và lỗi 405 Method Not Allowed

Giả sử client gửi DELETE đến một collection chỉ hỗ trợ GET và POST. Server có thể trả:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD, POST, OPTIONS
Content-Type: application/problem+json
```

Ý nghĩa:

- `405` cho biết method được gửi không được phép tại target resource.
- `Allow` cho biết các method hiện được hỗ trợ.
- Body lỗi, nếu có, cung cấp thêm thông tin theo định dạng mà server sử dụng.

Client có thể dùng `Allow` để cập nhật cách gọi hoặc hiển thị hành động phù hợp. Tuy nhiên, không nên tự động thử một method khác chỉ vì nó xuất hiện trong header; client vẫn cần biết ý nghĩa nghiệp vụ và payload cần thiết của thao tác đó.

Phân biệt một số status thường gặp:

| Status | Ý nghĩa trong tình huống này |
|---|---|
| `200 OK` / `204 No Content` | OPTIONS được xử lý thành công; đọc các response headers |
| `404 Not Found` | Target URI không được tìm thấy hoặc không được công bố theo cách server xử lý |
| `405 Method Not Allowed` | Resource tồn tại nhưng method được gửi không được hỗ trợ; kiểm tra `Allow` |
| `401 Unauthorized` | Thiếu hoặc không hợp lệ thông tin xác thực |
| `403 Forbidden` | Caller đã được nhận diện nhưng không được phép thực hiện request theo policy |

Không phải mọi server đều dùng cùng body hoặc status cho mọi trường hợp. Hãy dựa vào status và headers thực tế, đồng thời kiểm tra cấu hình security nếu request bị từ chối.

## 6. OPTIONS thông thường và CORS preflight

Một điểm dễ nhầm là OPTIONS được browser dùng cho **CORS preflight**. Đây vẫn là HTTP OPTIONS, nhưng mục đích của request là hỏi liệu một request cross-origin dự kiến có được phép gửi từ origin hiện tại hay không.

Browser có thể gửi:

```http
OPTIONS /people/42 HTTP/1.1
Host: api.example.test
Origin: https://frontend.example.test
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type, authorization
```

Server có thể trả các CORS response headers:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://frontend.example.test
Access-Control-Allow-Methods: GET, POST, PATCH, DELETE
Access-Control-Allow-Headers: Content-Type, Authorization
```

Hai loại thông tin cần phân biệt:

| Header | Ý nghĩa |
|---|---|
| `Allow` | HTTP method mà target resource hỗ trợ |
| `Access-Control-Allow-Methods` | Method mà server cho phép browser dùng trong CORS context cho origin/request đang xét |

CORS preflight còn có thể kiểm tra origin và request headers. Vì vậy, một method có trong `Allow` chưa chắc đã được browser cho phép gọi cross-origin; policy CORS có thể hạn chế nó. Ngược lại, `Access-Control-Allow-Methods` không thay thế việc endpoint thực sự triển khai method đó.

Khi debug browser, hãy xem cả request OPTIONS và response CORS headers trong Network panel. Nếu gọi API bằng curl thành công nhưng browser bị chặn, nguyên nhân có thể là CORS policy chứ không phải repository endpoint.

## 7. OPTIONS không thay thế security hoặc validation

OPTIONS giúp khám phá khả năng HTTP của resource. Nó không phải cơ chế cấp quyền và cũng không kiểm tra trước toàn bộ điều kiện của một thao tác.

Ví dụ:

- `Allow` có thể công bố PATCH, nhưng PATCH vẫn có thể trả 401 hoặc 403 nếu caller không đủ quyền.
- Caller có quyền PATCH nhưng payload không hợp lệ, server vẫn có thể trả 400.
- DELETE được hỗ trợ nhưng resource đang bị ràng buộc bởi quy tắc nghiệp vụ hoặc constraint dữ liệu; thao tác vẫn có thể thất bại.
- Link hoặc method không được công bố trong response không phải bằng chứng rằng URI đó an toàn nếu truy cập trực tiếp.

Server phải kiểm tra authentication, authorization, validation và trạng thái nghiệp vụ trên request thực tế. Client dùng OPTIONS như một tín hiệu khám phá API, không coi nó là bảo đảm rằng hành động chắc chắn thành công.

## 8. Quy trình kiểm tra method cho client

1. Lấy URI của resource từ HAL link hoặc API contract.
2. Gửi OPTIONS đến đúng URI, giữ nguyên authentication context cần thiết.
3. Đọc status code và header `Allow` nếu server cung cấp.
4. Nếu browser gọi cross-origin, kiểm tra thêm `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers`.
5. Chọn method theo API contract và gửi request thật với payload, `Content-Type` và `Accept` phù hợp.
6. Xử lý response thực tế: method được hỗ trợ vẫn có thể thất bại do quyền, validation, trạng thái resource hoặc lỗi persistence.

Khi kiểm tra từng URI thay vì suy luận từ một endpoint chung, client có thể hiểu rõ hơn khả năng của collection, item, search và association resource. `OPTIONS` cùng `Allow` cung cấp một cách tiêu chuẩn để khám phá HTTP methods, còn Spring Data REST và Spring Security vẫn chịu trách nhiệm quyết định endpoint nào thực sự được export và request nào được chấp nhận.
