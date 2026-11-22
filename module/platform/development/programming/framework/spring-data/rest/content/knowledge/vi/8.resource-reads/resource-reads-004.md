# HEAD để kiểm tra tài nguyên và đọc header

## Mục tiêu

Trong Spring Data REST, `HEAD` cho phép client kiểm tra một resource và đọc metadata của response mà không nhận representation body. Đây là cách hữu ích để kiểm tra một endpoint hoặc item có tồn tại hay không, đọc thông tin cache và content negotiation, hoặc quyết định có cần tải nội dung bằng `GET` hay không.

Điểm cốt lõi: **HEAD có ngữ nghĩa tương ứng với GET trên cùng URI, nhưng response không có body**. Vì vậy, client có thể đọc status và header, nhưng không thể dựa vào HEAD để xem JSON/HAL, dữ liệu nghiệp vụ, `_links` hoặc `_embedded`.

## 1. HEAD hoạt động như thế nào?

Theo HTTP, HEAD yêu cầu server trả về metadata tương tự response của GET cho cùng resource, nhưng bỏ phần message body.

Ví dụ:

~~~http
GET /api/people/42
Accept: application/hal+json
~~~

GET có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "person-42-v3"
Cache-Control: private, max-age=60

{
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/people/42"
    }
  }
}
~~~

Request HEAD tới cùng URI có thể trả:

~~~http
HEAD /api/people/42
Accept: application/hal+json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "person-42-v3"
Cache-Control: private, max-age=60
~~~

Response HEAD không chứa JSON body. Các header cụ thể phụ thuộc server, cấu hình và resource; ví dụ trên chỉ minh họa một response có ETag và cache policy.

HEAD là method **safe** và **idempotent** theo HTTP:

- Safe: request được dùng để đọc trạng thái, không yêu cầu server thay đổi dữ liệu nghiệp vụ.
- Idempotent: gửi lặp lại cùng request không làm thay đổi kết quả nghiệp vụ do request gây ra.

HEAD không phải lệnh xóa, tạo hoặc cập nhật resource. Nếu mục tiêu là thay đổi dữ liệu, dùng method phù hợp như POST, PUT, PATCH hoặc DELETE.

## 2. HEAD trong Spring Data REST

Spring Data REST công bố các repository resource theo loại resource. Các endpoint collection và item thường hỗ trợ HEAD cùng với các thao tác đọc tương ứng.

Giả sử repository Person được export tại `/api/people`.

| Loại resource | Request | Mục đích |
|---|---|---|
| Collection | `HEAD /api/people` | Kiểm tra collection endpoint và đọc header |
| Item | `HEAD /api/people/42` | Kiểm tra item 42 và đọc header |
| Collection | `GET /api/people` | Đọc representation collection |
| Item | `GET /api/people/42` | Đọc representation của item |

Ví dụ HEAD cho collection:

~~~http
HEAD /api/people?page=0&size=20
Accept: application/hal+json
~~~

Ví dụ HEAD cho item:

~~~http
HEAD /api/people/42
Accept: application/hal+json
~~~

Với repository resource chuẩn, Spring Data REST xử lý HEAD theo khả năng đọc của collection hoặc item. Trong Spring MVC, HEAD có thể được xử lý thông qua cùng luồng xử lý GET và phần body được loại bỏ khi tạo response. Vì thế, **không nên mặc định HEAD luôn rẻ hơn GET hoặc chắc chắn không truy vấn repository**. Server vẫn có thể cần tra cứu dữ liệu để xác định item có tồn tại, tạo status, tính validator hoặc tạo các header tương ứng.

Đường dẫn và base path trong ví dụ phụ thuộc cấu hình. Nếu ứng dụng không dùng `/api`, hãy dùng URI thực tế mà API công bố.

## 3. HEAD cho biết được điều gì?

HEAD giúp client đọc các thông tin nằm trong status line và response headers.

| Thông tin | Cách sử dụng |
|---|---|
| Status code | Biết request thành công, resource không tồn tại, bị từ chối hay không hỗ trợ method |
| `Content-Type` | Biết kiểu representation mà GET tương ứng sẽ trả về, nếu server cung cấp |
| `Content-Length` | Nếu có, thường mô tả độ dài body của response GET tương ứng; server có thể bỏ header này nếu không biết hoặc không tính |
| `ETag` | Validator để so sánh phiên bản representation |
| `Last-Modified` | Thời điểm resource/representation được sửa đổi lần cuối, nếu server cung cấp |
| `Cache-Control` | Chính sách cache như `private`, `no-store`, `max-age` |
| `Vary` | Cho cache biết những request header nào có thể làm thay đổi representation |
| `Content-Language` | Ngôn ngữ của representation, nếu được cung cấp |

Không phải ứng dụng Spring Data REST nào cũng trả tất cả các header này. Chẳng hạn, ETag và Last-Modified chỉ có ý nghĩa khi server hoặc tầng hạ tầng có cấu hình validator phù hợp. Đừng viết client giả định một header luôn tồn tại; hãy kiểm tra sự hiện diện của nó trước khi sử dụng.

### 3.1. Content-Type vẫn có ý nghĩa dù không có body

Client có thể gửi:

~~~http
Accept: application/hal+json
~~~

Nếu server hỗ trợ HAL JSON, response HEAD có thể có:

~~~http
Content-Type: application/hal+json
~~~

Header này cho biết định dạng representation của GET tương ứng. Tuy nhiên, client vẫn không nhận được JSON để phân tích. Muốn đọc các field nghiệp vụ hoặc link hypermedia, client phải gọi GET.

Nếu giá trị Accept không được server hỗ trợ, request có thể nhận `406 Not Acceptable`. Vì vậy, HEAD vẫn tham gia vào quá trình content negotiation.

### 3.2. Content-Length không phải lúc nào cũng xuất hiện

Về ngữ nghĩa HTTP, nếu server gửi Content-Length cho HEAD thì giá trị đó mô tả độ dài body mà GET tương ứng sẽ trả về, không phải độ dài body HEAD (vì body HEAD bằng 0). Tuy nhiên, server có thể bỏ Content-Length khi không thể xác định giá trị mà không tạo body.

Do đó:

- Không dùng việc thiếu Content-Length để kết luận resource không tồn tại.
- Không hiểu Content-Length của HEAD là số byte thực sự được truyền trong response HEAD.
- Nếu cần biết kích thước tải thực tế, hãy xem header và hành vi của endpoint cụ thể; HEAD không bảo đảm server luôn cung cấp kích thước.

## 4. Phân biệt collection tồn tại và item tồn tại

Một khác biệt quan trọng là collection endpoint có thể tồn tại ngay cả khi collection không có phần tử nào.

Ví dụ:

~~~http
HEAD /api/people
~~~

Nếu endpoint collection được export và truy cập được, server có thể trả `200 OK` dù repository hiện chưa có Person nào.

Trong khi đó:

~~~http
HEAD /api/people/999999
~~~

Nếu không có item với ID đó, server thường trả `404 Not Found`.

Có thể đọc kết quả như sau:

| Response | Diễn giải |
|---|---|
| `200 OK` cho collection | Collection endpoint có thể truy cập; không chứng minh collection có phần tử |
| `200 OK` cho item | Item resource được tìm thấy và có thể truy cập |
| `404 Not Found` cho item | Không tìm thấy item tại URI đó, hoặc server không tiết lộ sự tồn tại của nó |
| `401 Unauthorized` | Thiếu hoặc không hợp lệ thông tin xác thực |
| `403 Forbidden` | Người gọi không có quyền thực hiện request |
| `405 Method Not Allowed` | Resource không hỗ trợ HEAD trong cấu hình hiện tại |
| `406 Not Acceptable` | Không có representation phù hợp với Accept |
| `5xx` | Server hoặc hạ tầng gặp lỗi |

HEAD không cho biết collection có bao nhiêu phần tử, vì response body chứa danh sách và metadata phân trang đã bị loại bỏ. Nếu cần biết số lượng hoặc xem các item, hãy gọi GET collection.

## 5. HEAD và các header cache validator

HEAD thường hữu ích khi client làm việc với cache. Hai validator thường gặp là ETag và Last-Modified.

### 5.1. ETag và If-None-Match

Server có thể trả:

~~~http
HTTP/1.1 200 OK
ETag: "people-42-v5"
~~~

Client lưu ETag đó. Lần kiểm tra sau, client gửi:

~~~http
HEAD /api/people/42
If-None-Match: "people-42-v5"
Accept: application/hal+json
~~~

Nếu representation vẫn tương ứng với validator đã gửi, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "people-42-v5"
~~~

`304 Not Modified` cho biết representation chưa thay đổi theo validator mà client cung cấp; client có thể tiếp tục dùng bản cache còn hợp lệ theo chính sách cache. Response 304 cũng không có body.

Nếu representation đã thay đổi, server thường trả status của response HEAD hiện tại (chẳng hạn 200) cùng validator mới nếu có.

### 5.2. Last-Modified và If-Modified-Since

Nếu server công bố Last-Modified:

~~~http
Last-Modified: Tue, 10 Nov 2026 08:30:00 GMT
~~~

Client có thể gửi:

~~~http
HEAD /api/people/42
If-Modified-Since: Tue, 10 Nov 2026 08:30:00 GMT
~~~

Nếu resource không thay đổi kể từ thời điểm đó, server có thể trả 304. Nếu thay đổi, server trả response HEAD mới với các header tương ứng.

ETag thường là validator chính xác hơn khi server tạo được version token đáng tin cậy. Last-Modified có độ phân giải thời gian và độ chính xác phụ thuộc nguồn dữ liệu. Không nên tự tạo hoặc so sánh validator bằng suy đoán; hãy dùng giá trị server trả về.

Lưu ý: conditional request chỉ có hiệu lực khi server hoặc tầng web/cache của ứng dụng hỗ trợ validator. Không phải mọi endpoint Spring Data REST tự động có ETag hoặc Last-Modified.

## 6. Ví dụ kiểm tra bằng curl

Lệnh `curl -I` gửi request HEAD và hiển thị response headers.

Kiểm tra collection:

~~~bash
curl -I \
  -H "Accept: application/hal+json" \
  https://localhost:8080/api/people
~~~

Kiểm tra item:

~~~bash
curl -I \
  -H "Accept: application/hal+json" \
  https://localhost:8080/api/people/42
~~~

Xem chi tiết trao đổi request/response:

~~~bash
curl -v -I \
  -H "Accept: application/hal+json" \
  https://localhost:8080/api/people/42
~~~

So sánh HEAD và GET:

~~~bash
# HEAD: chỉ nhận status và headers
curl -I -H "Accept: application/hal+json" \
  https://localhost:8080/api/people/42

# GET: nhận status, headers và HAL body
curl -i -H "Accept: application/hal+json" \
  https://localhost:8080/api/people/42
~~~

Nếu API yêu cầu xác thực, thêm header Authorization phù hợp:

~~~bash
curl -I \
  -H "Accept: application/hal+json" \
  -H "Authorization: Bearer <access-token>" \
  https://localhost:8080/api/people/42
~~~

Không ghi token thật vào tài liệu, log chia sẻ hoặc shell history dùng chung. Ví dụ trên dùng placeholder.

Khi đọc kết quả, xem status code trước, sau đó mới kiểm tra Content-Type, ETag, Last-Modified, Cache-Control và các header khác. Không tìm JSON body trong response HEAD.

## 7. Kiểm tra HEAD trong integration test

Với ứng dụng Spring MVC, có thể kiểm tra endpoint bằng MockMvc:

~~~java
mockMvc.perform(
        head("/api/people/42")
            .accept("application/hal+json")
    )
    .andExpect(status().isOk())
    .andExpect(content().string(""));
~~~

Test trên xác nhận item có thể được truy cập và response không chứa body. Có thể kiểm tra trường hợp item không tồn tại:

~~~java
mockMvc.perform(
        head("/api/people/999999")
            .accept("application/hal+json")
    )
    .andExpect(status().isNotFound())
    .andExpect(content().string(""));
~~~

Status cụ thể còn phụ thuộc cách ứng dụng xử lý lỗi và bảo mật. Nếu API cố ý che giấu sự tồn tại của resource, request không có quyền có thể nhận 404 thay vì 403.

Không nên assert ETag hoặc Last-Modified trong mọi test nếu ứng dụng chưa cấu hình chúng. Khi muốn kiểm tra validator, hãy cấu hình rõ tầng phát sinh validator rồi mới assert header tương ứng.

## 8. HEAD không thay thế GET hoặc OPTIONS

Ba method có mục đích khác nhau:

| Method | Mục đích | Có response body theo ngữ nghĩa thông thường? |
|---|---|---|
| HEAD | Đọc metadata tương ứng GET, kiểm tra resource | Không |
| GET | Đọc representation của resource | Có thể có |
| OPTIONS | Khám phá các communication options/method được hỗ trợ tại target resource | Có thể không có hoặc có body tùy server |

Dùng HEAD khi chỉ cần status và header. Dùng GET khi cần dữ liệu nghiệp vụ, link HAL, embedded resource hoặc metadata phân trang trong body. Dùng OPTIONS khi muốn khám phá các method được hỗ trợ; header Allow thường gắn với việc công bố các method hợp lệ, nhưng không nên suy luận danh sách method chỉ từ một response HEAD.

Một HEAD thành công cũng không chứng minh rằng mọi thao tác khác như POST, PUT, PATCH hoặc DELETE đều được bật. Mỗi thao tác còn phụ thuộc repository method được export, cấu hình Spring Data REST và quyền truy cập.

## 9. Những nhầm lẫn thường gặp

- **HEAD không trả JSON rút gọn.** Nó không trả body; muốn xem một phần dữ liệu, hãy dùng GET hoặc projection phù hợp.
- **HEAD không bảo đảm không truy vấn database.** Server có thể chạy logic đọc tương tự GET để xác định resource và tạo header.
- **HEAD 200 trên collection không chứng minh collection có dữ liệu.** Nó chỉ cho biết endpoint collection có thể truy cập.
- **HEAD không cung cấp tổng số phần tử nếu thông tin đó chỉ nằm trong body.** Hãy GET collection nếu cần metadata phân trang.
- **Thiếu Content-Length không đồng nghĩa resource không tồn tại.** Header có thể bị lược bỏ.
- **Không phải endpoint nào cũng có ETag hoặc Last-Modified.** Chỉ dùng validator khi server thật sự cung cấp và hỗ trợ conditional request.
- **HEAD không thay thế OPTIONS.** HEAD kiểm tra metadata của representation; OPTIONS phục vụ khám phá khả năng giao tiếp.
- **HEAD vẫn cần được bảo vệ.** Nếu người dùng không được phép biết một resource tồn tại, chính status HEAD cũng có thể làm lộ thông tin.

## 10. Quy trình debug một request HEAD

Khi HEAD trả kết quả khác mong đợi, kiểm tra lần lượt:

1. **URI:** Đường dẫn có đúng collection path hoặc item URI được API công bố không?
2. **Method:** Endpoint có hỗ trợ HEAD không? Nếu nhận 405, kiểm tra mapping và cấu hình exposure.
3. **Authentication:** Header xác thực có hợp lệ không? Security rule có áp dụng cho HEAD không?
4. **Authorization:** Người gọi có quyền đọc resource không? Một số API cố ý dùng 404 để che giấu resource.
5. **Accept:** Client có yêu cầu media type được hỗ trợ, chẳng hạn `application/hal+json`, không?
6. **Status:** Phân biệt 200, 304, 404, 405, 406 và các lỗi 4xx/5xx.
7. **Headers:** Kiểm tra Content-Type, ETag, Last-Modified, Cache-Control và Vary nếu có.
8. **GET đối chiếu:** Nếu cần xác nhận business fields hoặc link, gửi GET tới cùng URI với cùng Accept và thông tin xác thực.

HEAD giúp kiểm tra resource nhanh từ góc nhìn HTTP. Khi cần hiểu nội dung hoặc cấu trúc hypermedia, GET vẫn là thao tác cần dùng.

## 11. Ghi nhớ

- HEAD tương ứng với GET trên cùng URI nhưng không có response body.
- Spring Data REST hỗ trợ HEAD cho các repository resource chuẩn như collection và item.
- Status code giúp xác định request thành công, item không tồn tại, method không hỗ trợ hoặc bị từ chối.
- Response headers có thể cung cấp Content-Type, Content-Length, ETag, Last-Modified và cache policy; từng header phụ thuộc server.
- Conditional HEAD có thể dùng If-None-Match hoặc If-Modified-Since để nhận 304 khi representation chưa thay đổi.
- HEAD không chứng minh collection có phần tử, không trả HAL body và không bảo đảm tránh truy vấn repository.
- Dùng GET để đọc dữ liệu, HEAD để kiểm tra metadata, và OPTIONS để khám phá communication options.

## Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics, HEAD](https://www.rfc-editor.org/rfc/rfc9110.html#name-head)
- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Framework — HTTP HEAD support](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
