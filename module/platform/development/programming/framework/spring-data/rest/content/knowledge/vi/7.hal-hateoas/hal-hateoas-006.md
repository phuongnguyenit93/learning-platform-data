# Thương lượng nội dung bằng Accept và Content-Type

Trong HTTP, client và server cần thống nhất cách biểu diễn dữ liệu được gửi đi và cách biểu diễn dữ liệu được trả về. Hai header quan trọng cho việc này là `Content-Type` và `Accept`. Với Spring Data REST, hiểu đúng hai header giúp client gửi đúng payload, nhận đúng representation HAL và xử lý chính xác các endpoint tài nguyên cũng như association.

## 1. Hai header giải quyết hai chiều khác nhau

**`Content-Type` mô tả nội dung của request body.** Client gửi header này để cho server biết payload đang được mã hóa theo media type nào. Ví dụ, body JSON thường dùng `application/json`; danh sách URI dùng để thao tác association thường dùng `text/uri-list`.

**`Accept` mô tả representation mà client muốn nhận trong response.** Client có thể yêu cầu HAL JSON bằng `application/hal+json`, hoặc một media type khác mà server hỗ trợ.

Có thể nhớ theo hai câu hỏi:

| Header | Câu hỏi | Hướng áp dụng |
|---|---|---|
| `Content-Type` | Tôi đang gửi dữ liệu theo định dạng nào? | Request body → server |
| `Accept` | Tôi muốn nhận response theo định dạng nào? | Client ← response |

Ví dụ một request tạo người dùng có thể gửi JSON nhưng yêu cầu response HAL:

```http
POST /people HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/hal+json

{
  "name": "An",
  "email": "an@example.test"
}
```

Ở đây, `Content-Type` cho Spring biết cách đọc body JSON. `Accept` cho Spring biết client muốn representation trả về là HAL JSON. Hai header không cần giống nhau vì chúng mô tả hai chiều độc lập.

## 2. Media type và content negotiation

Media type có dạng tổng quát:

```text
type/subtype
```

Một số media type thường gặp trong Spring Data REST và HAL:

| Media type | Ý nghĩa thường gặp |
|---|---|
| `application/json` | JSON thông thường |
| `application/hal+json` | JSON theo cấu trúc HAL, có thể chứa `_links` và `_embedded` |
| `application/alps+json` | Metadata profile theo định dạng ALPS |
| `text/uri-list` | Một hoặc nhiều URI, thường dùng khi thao tác association |

**Content negotiation** là quá trình chọn representation phù hợp giữa yêu cầu của client và khả năng của server. Client gửi `Accept`; Spring MVC và các `HttpMessageConverter` kiểm tra media type được yêu cầu, loại representation mà endpoint có thể tạo và converter có thể ghi dữ liệu đó.

Spring Data REST sử dụng HAL làm representation hypermedia mặc định trong cấu hình thông dụng. Vì vậy, response collection hoặc item thường có `_links`, và collection có thể có `_embedded`. Khi client muốn dựa vào các hypermedia relation, nên yêu cầu rõ `application/hal+json` để thể hiện kỳ vọng.

Ví dụ:

```http
GET /people/42 HTTP/1.1
Host: api.example.test
Accept: application/hal+json
```

Response minh họa:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
```

```json
{
  "name": "An",
  "email": "an@example.test",
  "_links": {
    "self": {
      "href": "https://api.example.test/people/42"
    }
  }
}
```

Media type thực tế phụ thuộc endpoint, converter và cấu hình `RepositoryRestConfiguration`. Nếu ứng dụng thay đổi default media type hoặc cấu hình HAL, client cần tuân theo hợp đồng mà server công bố.

## 3. Dùng Accept để yêu cầu HAL response

Khi client cần điều hướng API bằng relation, `Accept: application/hal+json` là lựa chọn rõ ràng:

```bash
curl -i \
  -H "Accept: application/hal+json" \
  https://api.example.test/people/42
```

Client đọc `Content-Type` của response để xác nhận server đã trả representation nào. Sau đó, nếu response là HAL, client đọc các relation trong `_links` thay vì giả định URL từ cấu trúc route.

Nếu client gửi nhiều media type trong `Accept`, nó có thể đưa ra thứ tự ưu tiên bằng quality value `q`:

```http
Accept: application/hal+json, application/json;q=0.8
```

Giá trị `q` nằm trong khoảng 0 đến 1; giá trị cao hơn biểu thị mức ưu tiên cao hơn. Server vẫn chỉ có thể chọn một representation mà endpoint và converter thực sự hỗ trợ. Wildcard như `*/*` thể hiện client chấp nhận nhiều loại nội dung, vì vậy server có thể dùng default media type.

Không nên giả định rằng gửi `Accept: application/json` luôn tạo ra cùng cấu trúc với HAL. JSON thuần và HAL JSON là hai media type có mục đích khác nhau. Nếu ứng dụng dựa vào `_links`, hãy yêu cầu HAL rõ ràng và kiểm tra `Content-Type` response.

## 4. Dùng Content-Type khi gửi entity JSON

Với thao tác tạo hoặc cập nhật entity qua repository resource, body JSON cần có media type mà endpoint hỗ trợ, thường là `application/json`. Ví dụ:

```bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"name":"An","email":"an@example.test"}' \
  https://api.example.test/people
```

Spring MVC chọn `HttpMessageConverter` phù hợp để đọc body. Jackson chuyển JSON thành object Java trước khi Spring Data REST tiếp tục xử lý repository operation.

Một request có thể thất bại trước khi repository được gọi nếu:

- JSON sai cú pháp.
- Kiểu dữ liệu trong JSON không thể chuyển thành kiểu Java tương ứng.
- Request khai báo `Content-Type` mà endpoint không hỗ trợ.
- Body không đáp ứng ràng buộc hoặc validation của ứng dụng.

Cần phân biệt lỗi parse/conversion với lỗi validation. Ví dụ `"age": "abc"` khi field Java là số có thể thất bại ở bước chuyển đổi; còn `"name": ""` có thể được chuyển đổi thành công nhưng bị validator từ chối.

## 5. Content-Type đặc biệt khi thao tác association

Spring Data REST không phải lúc nào cũng nhận một entity JSON đầy đủ khi client thay đổi quan hệ. Với association resource, một cách phổ biến là gửi URI của tài nguyên liên quan bằng media type `text/uri-list`.

Ví dụ gán địa chỉ có URI `/addresses/7` cho association `address` của person:

```http
PUT /people/42/address HTTP/1.1
Host: api.example.test
Content-Type: text/uri-list
Accept: application/hal+json

https://api.example.test/addresses/7
```

Lúc này body không phải JSON object. Nó là URI được gửi theo định dạng `text/uri-list`. Nếu client gửi body URI nhưng khai báo `Content-Type: application/json`, converter có thể cố đọc nội dung theo JSON và request sẽ không được xử lý như mong muốn.

Với association nhiều phần tử, `text/uri-list` có thể chứa nhiều URI, mỗi URI trên một dòng. Cách dùng PUT, POST, PATCH hoặc DELETE còn phụ thuộc loại association và semantics mà endpoint association hỗ trợ. Hãy đọc API contract và các link do server trả về để xác định thao tác hợp lệ.

## 6. Profile và media type của metadata

HAL response có thể công bố relation `profile` để client khám phá mô tả ngữ nghĩa của tài nguyên. Trong Spring Data REST, profile thường dẫn đến metadata ALPS. Khi truy cập profile resource, client có thể yêu cầu media type `application/alps+json`.

Ví dụ:

```http
GET /profile/people HTTP/1.1
Host: api.example.test
Accept: application/alps+json
```

Điều này khác với yêu cầu một entity representation bằng HAL. `application/alps+json` mô tả metadata/profile; `application/hal+json` biểu diễn tài nguyên cùng hypermedia links. Client cần chọn `Accept` phù hợp với loại resource mà nó đang truy cập.

## 7. Các lỗi negotiation thường gặp

| HTTP status | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `406 Not Acceptable` | Server không tạo được representation phù hợp với các media type trong `Accept` | Kiểm tra `Accept`, media type endpoint hỗ trợ và cấu hình converter |
| `415 Unsupported Media Type` | Server không đọc được request body theo `Content-Type` đã gửi | Kiểm tra media type của payload; dùng JSON hoặc `text/uri-list` đúng trường hợp |
| `400 Bad Request` | Body sai cú pháp, sai kiểu hoặc không hợp lệ theo validation | Kiểm tra JSON, kiểu dữ liệu và lỗi validation trong response |
| `401 Unauthorized` / `403 Forbidden` | Request thiếu xác thực hoặc không đủ quyền | Kiểm tra credentials và authorization; đổi media type không giải quyết lỗi quyền |

Không nên xử lý mọi lỗi thành một lỗi “JSON không hợp lệ”. 406 thường liên quan đến representation đầu ra; 415 liên quan đến định dạng request body; 400 có thể là lỗi đọc hoặc validation. Phân biệt đúng giúp client sửa đúng header hoặc payload.

## 8. Quy trình chọn header cho client

Trước khi gửi request, client có thể áp dụng các bước sau:

1. Xác định endpoint đang thao tác là item, collection, search, profile hay association resource.
2. Xác định body có tồn tại không và body là JSON entity, HAL payload hay URI list.
3. Đặt `Content-Type` theo đúng định dạng của body; nếu không có body thì không cần tự thêm header này.
4. Đặt `Accept` theo representation mong muốn, ví dụ `application/hal+json` cho tài nguyên hypermedia hoặc `application/alps+json` cho profile ALPS.
5. Đọc `Content-Type` response và xử lý status code trước khi parse body.
6. Nếu nhận HAL, dùng relation trong `_links` để tiếp tục điều hướng; không tự suy ra URI từ tên entity hoặc id.

| Tình huống | Content-Type request | Accept request |
|---|---|---|
| GET một item HAL | Không có request body | `application/hal+json` |
| GET profile ALPS | Không có request body | `application/alps+json` |
| POST entity JSON | `application/json` | `application/hal+json` |
| PUT association bằng URI | `text/uri-list` | `application/hal+json` |

Các giá trị trên là mẫu thông dụng cho Spring Data REST; cấu hình ứng dụng và endpoint cụ thể vẫn quyết định media type được hỗ trợ. Kiểm tra response header và tài liệu API của server khi tích hợp với một hệ thống thực tế.

Khi phân biệt đúng `Accept` và `Content-Type`, client có thể yêu cầu representation hypermedia phù hợp, gửi đúng định dạng cho từng loại endpoint và nhận diện nguyên nhân lỗi negotiation. Đây là nền tảng để tích hợp Spring Data REST ổn định mà vẫn tận dụng được HAL và HATEOAS.
