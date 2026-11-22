# Phân biệt 200, 201, 204 và lỗi phương thức không được hỗ trợ trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể:
- Đọc status code để biết request đã đọc dữ liệu, cập nhật hay tạo tài nguyên.
- Phân biệt phản hồi thành công có representation với phản hồi thành công không có body.
- Nhận diện HTTP 405 khi gọi một method mà endpoint hoặc repository không hỗ trợ.
- Kiểm tra đúng URL, HTTP method, header và cấu hình Spring Data REST khi gặp lỗi.

## 1. Bắt đầu từ loại resource

Spring Data REST xuất bản repository thành các HTTP resource. Với repository quản lý Person, ví dụ:

- Collection resource: **/people**, đại diện cho tập hợp Person.
- Item resource: **/people/42**, đại diện cho một Person cụ thể.
- Search resource: **/people/search**, cung cấp các query method được export.
- Association resource: **/people/42/address**, đại diện cho quan hệ của một item.

Các method được hỗ trợ phụ thuộc vào loại resource và những method mà repository thực sự export. Vì vậy, không thể suy ra rằng mọi URL đều nhận được mọi HTTP method.

| Resource | HTTP method thường được hỗ trợ | Mục đích |
|---|---|---|
| Collection /people | GET, POST | Đọc danh sách; tạo item mới |
| Item /people/{id} | GET, PUT, PATCH, DELETE | Đọc, thay thế, cập nhật một phần hoặc xóa item |
| Search /people/search | GET | Khám phá và gọi query method |
| Association | GET, PUT, POST, DELETE tùy loại quan hệ | Đọc hoặc thay đổi liên kết |

Đây là cấu hình mặc định thường gặp. Repository method bị thiếu, bị ẩn bằng @RestResource(exported = false) hoặc bị giới hạn bằng cấu hình exposure có thể làm một method không còn được hỗ trợ.

## 2. Ý nghĩa của ba status code thành công

### 200 OK — request thành công và có representation

200 OK cho biết server xử lý request thành công và trả về representation trong response body.

Các tình huống thường gặp:
- GET đọc collection hoặc item thành công.
- PUT cập nhật item hiện có và server trả representation của item.
- PATCH cập nhật một phần item và server trả representation.
- DELETE có thể trả 200 OK kèm representation đã xóa nếu cấu hình và header yêu cầu response body.

Ví dụ khi đọc một item:

    GET /people/42
    Accept: application/hal+json

Phản hồi minh họa:

    HTTP/1.1 200 OK
    Content-Type: application/hal+json

    {
      "firstName": "An",
      "lastName": "Nguyen",
      "_links": {
        "self": { "href": "http://localhost:8080/people/42" }
      }
    }

Đừng hiểu 200 là “đã tạo mới”. Với request cập nhật, nó thường có nghĩa là thao tác đã thành công và server trả lại representation.

### 201 Created — một resource mới đã được tạo

201 Created xác nhận server đã tạo resource mới. Trong Spring Data REST, trường hợp phổ biến là:
- POST vào collection resource, ví dụ POST /people.
- PUT tạo resource mới tại item URI, nếu tính năng PUT-for-creation đang được bật.

Response thường có header Location trỏ đến URI của resource mới. Đây là thông tin quan trọng để client lưu lại đường dẫn của item vừa tạo.

Ví dụ:

    POST /people
    Content-Type: application/json
    Accept: application/hal+json

    {
      "firstName": "An",
      "lastName": "Nguyen"
    }

Phản hồi minh họa:

    HTTP/1.1 201 Created
    Location: http://localhost:8080/people/42
    Content-Type: application/hal+json

    {
      "firstName": "An",
      "lastName": "Nguyen",
      "_links": {
        "self": { "href": "http://localhost:8080/people/42" }
      }
    }

Body có thể được trả về hoặc để trống tùy Accept và cấu hình RepositoryRestConfiguration.setReturnBodyOnCreate(...). Ngay cả khi body trống, client vẫn có thể dùng URI trong Location để truy cập resource vừa tạo.

Không nên mặc định mọi PUT đều trả 201: PUT cập nhật item đã tồn tại thường trả 200 hoặc 204; PUT chỉ trả 201 khi nó thực sự tạo resource mới và thao tác tạo bằng PUT được cho phép.

### 204 No Content — request thành công nhưng không có body

204 No Content vẫn là một kết quả thành công. Nó có nghĩa là server đã thực hiện thao tác nhưng không gửi representation trong response body.

Trong Spring Data REST, 204 thường xuất hiện với:
- PUT cập nhật item khi server không trả body.
- PATCH cập nhật một phần item khi server không trả body.
- DELETE xóa item khi server không trả body.

Với cấu hình mặc định, sự hiện diện của header Accept có thể quyết định server có trả body hay không. Nếu có Accept, server có thể trả representation và status 200 OK cho thao tác cập nhật/xóa; nếu không có, response thành công thường là 204 No Content. Các thiết lập như setReturnBodyOnUpdate(...) và setReturnBodyOnDelete(...) có thể thay đổi hành vi này.

Ví dụ:

    PUT /people/42
    Content-Type: application/json

    {
      "firstName": "An",
      "lastName": "Tran"
    }

Phản hồi có thể là:

    HTTP/1.1 204 No Content

Không có JSON body để đọc. Client không nên gọi response.json() một cách vô điều kiện sau response 204, vì việc parse body rỗng có thể tạo lỗi ở phía client dù thao tác trên server đã thành công.

## 3. So sánh 200, 201 và 204 theo thao tác

| Request | Kết quả | Status thường gặp | Điều cần kiểm tra |
|---|---|---|---|
| GET collection hoặc item | Đọc thành công | 200 | Response body chứa representation |
| POST collection | Tạo item mới | 201 | Lấy URI mới từ header Location |
| PUT item đã tồn tại | Thay thế trạng thái item | 200 hoặc 204 | Có trả body hay không; kiểm tra Accept và cấu hình |
| PUT item để tạo mới | Tạo item tại URI chỉ định | 201 nếu PUT-for-creation được bật | Kiểm tra cấu hình cho phép tạo bằng PUT |
| PATCH item | Cập nhật một phần item | 200 hoặc 204 | Kiểm tra chính sách trả body |
| DELETE item | Xóa item | 200 hoặc 204 | Kiểm tra chính sách trả body |

Điểm quan trọng: status code của PUT, PATCH và DELETE không chỉ phụ thuộc vào HTTP method. Nó còn phụ thuộc vào việc thao tác tạo mới hay cập nhật/xóa, server có trả representation hay không, header Accept và cấu hình Spring Data REST.

## 4. 405 Method Not Allowed — URL có resource nhưng method không được hỗ trợ

405 Method Not Allowed xuất hiện khi request dùng một HTTP method mà resource đó không cho phép.

Ví dụ:
- Gửi PUT /people: collection resource mặc định chỉ hỗ trợ GET và POST.
- Gửi DELETE /people/search: search resource là resource chỉ đọc.
- Gửi PATCH /people/42 trong khi PATCH đã bị tắt bằng cấu hình exposure.
- Gửi POST, PUT hoặc PATCH khi repository không export method save(...).
- Gửi DELETE khi repository không export method xóa tương ứng.

Phản hồi minh họa:

    HTTP/1.1 405 Method Not Allowed
    Allow: GET, HEAD, POST

Nếu response có header Allow, hãy dùng danh sách trong header để biết các method mà endpoint chấp nhận. Đừng tự đổi URL hoặc thử liên tục nhiều method mà chưa xác định resource đang gọi.

### Phân biệt 405 với 404

| Status | Ý nghĩa | Hướng kiểm tra |
|---|---|---|
| 404 Not Found | Không tìm thấy đường dẫn hoặc resource tương ứng; item có thể không tồn tại | Kiểm tra base path, tên collection, ID, repository có được export không |
| 405 Method Not Allowed | Đường dẫn nhận diện được nhưng HTTP method không được hỗ trợ | Kiểm tra loại resource, method được export và header Allow |

Một repository hoặc resource bị ẩn hoàn toàn có thể khiến đường dẫn không được đăng ký và trả về 404. Vì vậy, cần xác định URL có thực sự trỏ đến resource đã được export hay không trước khi kết luận đây là lỗi method.

### Cách kiểm tra nguyên nhân 405

1. Xác định loại resource: collection, item, search hay association.
2. So sánh method đang gửi với danh sách method mặc định của loại resource đó.
3. Kiểm tra repository có method tương ứng hay không. Ví dụ, save(...) thường được dùng cho POST trên collection và PUT/PATCH trên item; các method delete(...) được dùng cho DELETE.
4. Kiểm tra method hoặc repository có bị ẩn bằng @RestResource(exported = false) hoặc @RepositoryRestResource(exported = false) hay không.
5. Kiểm tra các rule trong RepositoryRestConfiguration.getExposureConfiguration() có tắt method theo loại resource hoặc domain type hay không.
6. Nếu method được chủ động tắt, hãy dùng method được hỗ trợ hoặc thay đổi cấu hình theo yêu cầu nghiệp vụ. Không mở lại một method chỉ để làm mất lỗi 405 nếu thao tác đó không nên được phép.

Ví dụ, Spring Data REST cho phép tắt PATCH trên item resource bằng exposure configuration:

    config.getExposureConfiguration()
        .withItemExposure((metadata, methods) ->
            methods.disable(HttpMethod.PATCH));

Cũng có thể tắt riêng khả năng tạo item bằng PUT cho một domain type bằng disablePutForCreation(). Việc tắt một method là quyết định về API exposure; client phải tuân theo contract đã công bố.

## 5. Đừng nhầm 405 với lỗi header hoặc dữ liệu

Một số lỗi khác thường gặp khi ghi resource:

| Status | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| 400 Bad Request | JSON sai cấu trúc, dữ liệu không hợp lệ hoặc URI association không hợp lệ | Kiểm tra body, kiểu dữ liệu, trường bắt buộc và URI được gửi |
| 406 Not Acceptable | Giá trị Accept yêu cầu representation mà server không thể cung cấp | Dùng media type được endpoint hỗ trợ, thường là application/hal+json hoặc application/json |
| 415 Unsupported Media Type | Content-Type của request body không được endpoint hỗ trợ | Gửi đúng Content-Type; PATCH có thể dùng application/patch+json hoặc application/merge-patch+json |
| 404 Not Found | URL hoặc item không tồn tại, hoặc resource không được export | Kiểm tra link, ID và repository exposure |
| 405 Method Not Allowed | HTTP method không được hỗ trợ trên resource | Kiểm tra method, repository method và exposure configuration |

Hai header cần phân biệt:
- Content-Type: định dạng của dữ liệu client gửi lên. Ví dụ: application/json.
- Accept: định dạng representation client muốn nhận về. Ví dụ: application/hal+json.

Một request có body JSON hợp lệ vẫn có thể thất bại nếu Content-Type không đúng. Tương tự, request có thể thực hiện thành công nhưng trả 204 nếu client không yêu cầu representation hoặc cấu hình server không trả body.

## 6. Thực hành với curl

Giả sử ứng dụng chạy tại http://localhost:8080 và repository export collection /people.

### Tạo resource bằng POST

    curl -i -X POST http://localhost:8080/people -H "Content-Type: application/json" -H "Accept: application/hal+json" -d '{"firstName":"An","lastName":"Nguyen"}'

Đọc status 201 Created và header Location. Dùng URI trong Location để đọc hoặc cập nhật item mới.

### Cập nhật resource bằng PUT

    curl -i -X PUT http://localhost:8080/people/42 -H "Content-Type: application/json" -H "Accept: application/hal+json" -d '{"firstName":"An","lastName":"Tran"}'

Nếu item đã tồn tại và server trả representation, kết quả thường là 200 OK. Nếu bỏ header Accept và server không được cấu hình trả body khi update, kết quả thành công thường là 204 No Content.

### Cập nhật một phần bằng PATCH

    curl -i -X PATCH http://localhost:8080/people/42 -H "Content-Type: application/merge-patch+json" -H "Accept: application/hal+json" -d '{"lastName":"Tran"}'

PATCH chỉ thay đổi những trường được gửi theo định dạng patch mà endpoint hỗ trợ. Kiểm tra response body và status 200 hoặc 204 theo chính sách trả body.

### Xóa resource bằng DELETE

    curl -i -X DELETE http://localhost:8080/people/42 -H "Accept: application/hal+json"

Tùy cấu hình, server có thể trả 200 OK kèm body hoặc 204 No Content không có body.

### Tái hiện lỗi method không được hỗ trợ

    curl -i -X PUT http://localhost:8080/people

Collection resource mặc định không hỗ trợ PUT, nên request có thể nhận 405 Method Not Allowed. Hãy xem header Allow và đổi sang endpoint/method đúng với mục tiêu. Muốn tạo item mới, thông thường gửi POST đến collection resource.

## 7. Checklist khi đọc response

Khi kiểm tra một thao tác ghi, hãy lần lượt hỏi:

- Tôi đang gọi collection URI hay item URI?
- Method này có được resource hỗ trợ không?
- Repository có method tương ứng và method đó có được export không?
- Request body có đúng JSON và Content-Type không?
- Accept có yêu cầu representation mà endpoint hỗ trợ không?
- Status là 200, 201 hay 204? Nếu 201, Location trỏ đến đâu?
- Nếu là 204, client đã xử lý response rỗng đúng cách chưa?
- Nếu là 405, header Allow và exposure configuration cho biết điều gì?

Không đánh giá một thao tác chỉ bằng việc có JSON body hay không. 204 là thành công; ngược lại, 200 không có nghĩa là một resource mới đã được tạo.

## 8. Bài tập tự kiểm tra

**Tình huống 1:** Client POST JSON đến /people, nhận 201 Created và Location: /people/43. Điều gì đã xảy ra?

Đáp án: Server đã tạo resource mới. Client nên lưu hoặc theo link trong Location để truy cập item /people/43.

**Tình huống 2:** Client PUT đến /people/42, nhận 204 No Content. Có phải cập nhật thất bại không?

Đáp án: Không. Đây có thể là cập nhật thành công nhưng server không trả body. Client không nên cố parse JSON từ response này.

**Tình huống 3:** Client gửi DELETE đến /people và nhận 405. Vì sao?

Đáp án: /people là collection resource; method DELETE mặc định áp dụng cho item resource như /people/42, không áp dụng cho collection.

**Tình huống 4:** Client gửi PATCH đến item URI và nhận 405, dù repository có save(...). Cần kiểm tra gì?

Đáp án: Kiểm tra @RestResource(exported = false), exposure configuration và các rule theo item/domain type. Việc có save(...) chưa đảm bảo PATCH luôn được export nếu cấu hình đã tắt method.

**Tình huống 5:** Client nhận 415 Unsupported Media Type khi gửi PATCH. Có nên đổi PATCH thành PUT ngay không?

Đáp án: Chưa. Hãy kiểm tra Content-Type. Spring Data REST hỗ trợ các media type patch như application/patch+json và application/merge-patch+json; dùng đúng định dạng mà endpoint chấp nhận.

## Kết luận

- 200 OK: thao tác thành công và thường có representation trong response body.
- 201 Created: resource mới được tạo; kiểm tra header Location.
- 204 No Content: thao tác thành công nhưng response body rỗng.
- 405 Method Not Allowed: resource không hỗ trợ HTTP method được gửi; kiểm tra loại resource, repository method và exposure configuration.

Với Spring Data REST, hãy xác định đúng resource trước, sau đó mới chọn HTTP method và diễn giải status code. Đặc biệt, PUT/PATCH/DELETE có thể trả 200 hoặc 204 tùy chính sách trả body; 204 không phải lỗi.

## Tài liệu tham khảo

- Spring Data REST — Repository resources: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST — Customizing supported HTTP methods: https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html
