# Thực hiện chuỗi thao tác Spring Data REST bằng curl hoặc Postman

## Mục tiêu

Bài thực hành này hướng dẫn một máy khách REST khám phá API Spring Data REST và thực hiện chuỗi thao tác phổ biến trên một repository đã được xuất bản: đọc tài nguyên gốc, đọc collection, tạo item, đọc item, cập nhật một phần hoặc toàn bộ, tìm kiếm, phân trang, sắp xếp và xóa. Các ví dụ dùng collection people và entity Person theo Spring Getting Started Guide; thay tên relation, trường JSON và URI bằng những giá trị mà API thực tế trả về.

Sau bài này, người học có thể:

- Khám phá endpoint qua các liên kết HAL thay vì đoán đường dẫn.
- Gửi đúng HTTP method, Content-Type, Accept và JSON body.
- Dùng Location hoặc _links.self để tiếp tục chuỗi request.
- Phân biệt PUT thay thế toàn bộ tài nguyên với PATCH cập nhật một phần.
- Dùng curl trên terminal hoặc tạo collection Postman có biến và kiểm tra response.
- Nhận biết các lỗi HTTP phổ biến khi tích hợp client.

## 1. Chuẩn bị

Giả sử ứng dụng đang chạy tại http://localhost:8080 và repository được xuất bản dưới relation people, tương ứng collection URI /people. Nếu ứng dụng cấu hình base path, chẳng hạn /api, hãy đặt base URL thành http://localhost:8080/api. Không mặc định mọi repository đều có đường dẫn /people: Spring Data REST tạo collection path từ tên domain type và cho phép đổi path bằng @RepositoryRestResource.

Spring Data REST dùng HAL làm định dạng hypermedia mặc định. Response thường chứa:

- _links: các liên kết đến collection, item, search, profile và tài nguyên liên quan.
- _embedded: các tài nguyên được nhúng, ví dụ danh sách people trong response collection.
- page: metadata phân trang khi endpoint trả về Page.

Các header thường dùng:

| Header | Mục đích |
|---|---|
| Accept: application/hal+json | Yêu cầu response ở dạng HAL JSON |
| Content-Type: application/json | Khai báo body request là JSON |
| Content-Type: text/uri-list | Gửi URI khi liên kết một association |
| Authorization | Gửi thông tin xác thực nếu API bật Spring Security |

Trong Windows PowerShell, gọi rõ curl.exe vì curl có thể là alias của Invoke-WebRequest. Các lệnh bên dưới dùng cú pháp PowerShell và biến $baseUrl. Trên Linux/macOS, có thể thay curl.exe bằng curl và dùng cú pháp quote phù hợp với shell.

~~~powershell
$baseUrl = "http://localhost:8080"
~~~

Nếu ứng dụng có base path, cập nhật biến trên trước khi chạy các lệnh.

## 2. Khám phá API từ resource root

Bắt đầu bằng GET tới root URI:

~~~powershell
curl.exe -i -H "Accept: application/hal+json" "$baseUrl/"
~~~

Một response mẫu có thể chứa relation people:

~~~json
{
  "_links": {
    "people": {
      "href": "http://localhost:8080/people{?page,size,sort*}",
      "templated": true
    },
    "profile": {
      "href": "http://localhost:8080/profile"
    }
  }
}
~~~

Đọc href của relation people để biết collection URI. Trong ví dụ này, URI là /people. Nếu relation hoặc path khác, dùng đúng href do server trả về. Khi tích hợp client lâu dài, nên đi theo các liên kết HAL thay vì hardcode path hoặc tự suy ra tên collection.

## 3. Chuỗi thao tác bằng curl

### 3.1. Đọc collection

~~~powershell
curl.exe -i -H "Accept: application/hal+json" "$baseUrl/people"
~~~

Response collection thường có _embedded.people, các liên kết self, profile, search và object page. Nếu collection rỗng, mảng people có thể rỗng nhưng các liên kết điều hướng vẫn có thể xuất hiện.

### 3.2. Tạo một item bằng POST

Body mẫu theo Person của Spring guide:

~~~powershell
$createBody = '{"firstName":"Frodo","lastName":"Baggins"}'
curl.exe -i -X POST "$baseUrl/people" -H "Content-Type: application/json" -H "Accept: application/hal+json" --data-raw $createBody
~~~

Kết quả mong đợi:

- HTTP 201 Created.
- Response có header Location chứa URI của item vừa tạo.
- Nếu server trả representation, body thường có _links.self.href và dữ liệu Person.

Ví dụ Location có thể là http://localhost:8080/people/1. ID thực tế do datastore cấp; luôn lấy Location hoặc _links.self.href từ response. Gán URI đó vào biến để dùng ở các bước tiếp theo:

~~~powershell
$itemUrl = "http://localhost:8080/people/1"
~~~

Thay giá trị ví dụ bằng Location thực tế.

### 3.3. Đọc item vừa tạo

~~~powershell
curl.exe -i -H "Accept: application/hal+json" "$itemUrl"
~~~

Kiểm tra status 200 OK, dữ liệu firstName và lastName, cùng liên kết self. Dùng URI của item để thực hiện các thao tác tiếp theo.

### 3.4. Cập nhật một phần bằng PATCH

PATCH chỉ áp dụng các trường có trong body. Ví dụ đổi firstName và giữ nguyên lastName:

~~~powershell
$patchBody = '{"firstName":"Bilbo Jr."}'
curl.exe -i -X PATCH "$itemUrl" -H "Content-Type: application/json" -H "Accept: application/hal+json" --data-raw $patchBody
~~~

Sau đó GET lại item để xác nhận firstName đã đổi và lastName vẫn là Baggins. Spring Data REST hỗ trợ application/json cho PATCH; các media type application/hal+json, application/patch+json và application/merge-patch+json cũng được hỗ trợ.

### 3.5. Thay thế toàn bộ bằng PUT

PUT thay thế trạng thái của tài nguyên bằng representation gửi lên. Hãy gửi đầy đủ các trường cần giữ:

~~~powershell
$putBody = '{"firstName":"Bilbo","lastName":"Baggins"}'
curl.exe -i -X PUT "$itemUrl" -H "Content-Type: application/json" -H "Accept: application/hal+json" --data-raw $putBody
~~~

Nếu bỏ một trường khỏi body PUT, trường đó có thể được đặt thành null theo semantics thay thế. Dùng PATCH khi chỉ muốn thay đổi một phần. GET lại item để xác nhận dữ liệu sau cập nhật.

### 3.6. Khám phá và gọi search resource

Đọc link search trong response collection hoặc gọi search URI mà HAL trả về:

~~~powershell
curl.exe -i -H "Accept: application/hal+json" "$baseUrl/people/search"
~~~

Nếu repository có finder findByLastName với @Param("name"), response search có thể cung cấp URI template tương tự /people/search/findByLastName{?name}. Gọi finder với query parameter:

~~~powershell
curl.exe -i -H "Accept: application/hal+json" "$baseUrl/people/search/findByLastName?name=Baggins"
~~~

Tên finder, path và parameter phụ thuộc repository interface và annotation @RestResource. Nếu link không xuất hiện, kiểm tra repository có khai báo finder và phương thức có được export hay không.

### 3.7. Phân trang và sắp xếp

Collection hỗ trợ các query parameter page, size và sort nếu repository hỗ trợ paging/sorting:

~~~powershell
curl.exe -i -H "Accept: application/hal+json" "$baseUrl/people?page=0&size=5&sort=lastName,asc"
~~~

- page bắt đầu từ 0.
- size là số phần tử tối đa trong một trang.
- sort dùng dạng tên-trường,asc hoặc tên-trường,desc.

Response phân trang có metadata page và các link next, prev khi có trang tương ứng. Hãy theo href của next/prev để chuyển trang. Trong shell, đặt toàn bộ URI trong dấu ngoặc kép nếu URL có ký tự &.

### 3.8. Xóa item

~~~powershell
curl.exe -i -X DELETE "$itemUrl"
~~~

Với cấu hình mặc định không trả body cho DELETE, response thành công thường là 204 No Content. Tùy cấu hình và Accept, server có thể trả 200 OK kèm representation. Gọi GET lại URI item để xác nhận tài nguyên đã bị xóa; kết quả thường là 404 Not Found.

### 3.9. Liên kết association (nếu domain có quan hệ)

Response item có thể chứa link tới association, ví dụ _links.customer.href. Lấy đúng href từ response để biết URI association. Với association to-one, gửi URI của tài nguyên cần liên kết bằng PUT và Content-Type text/uri-list:

~~~powershell
$customerUri = "http://localhost:8080/customers/42"
curl.exe -i -X PUT "$baseUrl/orders/1/customer" -H "Content-Type: text/uri-list" --data-raw $customerUri
~~~

Với collection association, POST thêm một phần tử vào association; DELETE gỡ liên kết. Đường dẫn /orders/1/customer chỉ là ví dụ, hãy thay bằng URI association thực tế. Với association to-one, gửi nhiều URI có thể dẫn đến 400 Bad Request.

## 4. Thực hiện cùng chuỗi thao tác trong Postman

Tạo một Collection, ví dụ Spring Data REST - Client Flow, và đặt Collection Variables:

| Variable | Giá trị ban đầu |
|---|---|
| baseUrl | http://localhost:8080 |
| peopleUrl | để trống |
| itemUrl | để trống |

Nếu API có base path, thêm vào baseUrl. Mỗi request nên đặt Accept: application/hal+json. Các request có JSON body cần thêm Content-Type: application/json.

### Request 1 — Khám phá root

- Method: GET
- URL: {{baseUrl}}/
- Header: Accept = application/hal+json

Trong tab Post-response, lưu href của relation people:

~~~javascript
const body = pm.response.json();

pm.test("Root trả về relation people", function () {
    pm.response.to.have.status(200);
    pm.expect(body._links.people.href).to.be.a("string");
});

pm.collectionVariables.set("peopleUrl", body._links.people.href);
~~~

Nếu relation được đổi tên bằng @RepositoryRestResource, thay people bằng đúng key trong _links.

### Request 2 — Đọc collection

- Method: GET
- URL: {{peopleUrl}}
- Header: Accept = application/hal+json

Kiểm tra status 200 và cấu trúc _embedded, _links, page. Nếu cần lấy một item có sẵn từ collection, có thể lưu _links.self.href của phần tử đầu tiên:

~~~javascript
const body = pm.response.json();
const items = body._embedded?.people ?? [];

if (items.length > 0) {
    pm.collectionVariables.set("itemUrl", items[0]._links.self.href);
}
~~~

### Request 3 — Tạo item

- Method: POST
- URL: {{peopleUrl}}
- Headers: Content-Type = application/json; Accept = application/hal+json
- Body: chọn raw, JSON

~~~json
{
  "firstName": "Frodo",
  "lastName": "Baggins"
}
~~~

Post-response script:

~~~javascript
pm.test("POST tạo item thành công", function () {
    pm.response.to.have.status(201);
});

const location = pm.response.headers.get("Location");
pm.expect(location).to.be.ok;
pm.collectionVariables.set("itemUrl", location);
~~~

Script lưu Location vào itemUrl để các request tiếp theo dùng cùng tài nguyên. Nếu server không trả Location do cấu hình riêng, lấy href từ _links.self trong response body.

### Request 4 — Đọc item

- Method: GET
- URL: {{itemUrl}}
- Header: Accept = application/hal+json

Kiểm tra status 200 và dữ liệu item. Nếu request POST chưa chạy hoặc chưa lưu itemUrl, biến sẽ rỗng và request không thể định tuyến đúng.

### Request 5 — PATCH item

- Method: PATCH
- URL: {{itemUrl}}
- Headers: Content-Type = application/json; Accept = application/hal+json
- Body:

~~~json
{
  "firstName": "Bilbo Jr."
}
~~~

Post-response script:

~~~javascript
pm.test("PATCH trả về thành công", function () {
    pm.expect(pm.response.code).to.be.oneOf([200, 204]);
});
~~~

Gọi GET item sau PATCH để kiểm tra trường đã đổi và các trường khác vẫn được giữ.

### Request 6 — PUT item

- Method: PUT
- URL: {{itemUrl}}
- Headers: Content-Type = application/json; Accept = application/hal+json
- Body: gửi toàn bộ các trường cần giữ.

~~~json
{
  "firstName": "Bilbo",
  "lastName": "Baggins"
}
~~~

Đọc lại item để xác nhận representation mới. Không dùng body chỉ có một trường nếu mục đích là giữ các trường còn lại.

### Request 7 — DELETE item

- Method: DELETE
- URL: {{itemUrl}}

Post-response script:

~~~javascript
pm.test("DELETE trả về thành công", function () {
    pm.expect(pm.response.code).to.be.oneOf([200, 204]);
});
~~~

Sau đó gửi GET {{itemUrl}}. Kết quả mong đợi là 404 Not Found. Có thể giữ itemUrl trong collection variables để kiểm tra sau xóa; nếu muốn chạy lại collection từ đầu, chạy lại request POST để tạo item mới.

### Chạy theo thứ tự

Trong Collection Runner, sắp xếp request theo thứ tự: root, collection, POST, GET item, PATCH, GET item, PUT, GET item, DELETE, GET sau xóa. Các biến collection được cập nhật từ Post-response scripts sẽ được dùng ở các request sau. Nếu chạy từng request thủ công, cũng cần chạy root trước POST để thiết lập peopleUrl, rồi POST để thiết lập itemUrl.

Nếu API yêu cầu đăng nhập, cấu hình Authorization ở tab Authorization của collection hoặc environment. Tránh ghi token thật vào ví dụ, file collection được chia sẻ hoặc script kiểm thử.

## 5. Kiểm tra kết quả và status code

| Thao tác | Kết quả thường gặp | Điều cần xác nhận |
|---|---|---|
| GET root | 200 OK | Có _links tới các collection |
| GET collection | 200 OK | Có _embedded, _links và page nếu phân trang |
| POST collection | 201 Created | Có Location của item mới |
| GET item | 200 OK | URI item hợp lệ và body đúng |
| PATCH item | 200 OK hoặc 204 No Content | Chỉ các trường gửi lên được cập nhật |
| PUT item | 200 OK hoặc 204 No Content | Toàn bộ representation được thay thế |
| DELETE item | 200 OK hoặc 204 No Content | Item bị xóa |
| GET item sau DELETE | 404 Not Found | Tài nguyên không còn tồn tại |

Mã thành công của PUT, PATCH và DELETE phụ thuộc cấu hình returnBodyOnUpdate/returnBodyOnDelete và header Accept. Không coi response 204 là lỗi chỉ vì body rỗng. Với POST, dùng Location để tìm tài nguyên mới nếu body không được trả về.

## 6. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| GET root hoặc collection trả 404 | Sai host, port, base path hoặc relation path | Gọi root URI đúng, đọc _links và dùng href do server trả về |
| POST trả 405 Method Not Allowed | Repository không export phương thức save hoặc collection không hỗ trợ POST | Kiểm tra repository có CrudRepository/JpaRepository và save không bị @RestResource(exported = false) |
| PUT/PATCH trả 405 | Phương thức save của repository không được export hoặc endpoint không phải item resource | Gọi URI item từ _links.self; kiểm tra cấu hình export method |
| DELETE trả 405 | Phương thức delete không được export | Kiểm tra repository interface và cấu hình supported methods |
| 400 Bad Request | JSON sai cú pháp, sai tên trường hoặc body không hợp lệ | Kiểm tra raw body, kiểu dữ liệu và validation response |
| 415 Unsupported Media Type | Content-Type không khớp với body hoặc association | Dùng application/json cho JSON body; dùng text/uri-list cho association URI |
| POST thành công nhưng không có body | Server không bật return body hoặc request thiếu Accept | Đọc Location response header và GET URI đó; thêm Accept nếu cần representation |
| PUT làm mất dữ liệu trường khác | Body PUT không gửi đủ các trường | Gửi representation đầy đủ hoặc dùng PATCH cho cập nhật một phần |
| Postman báo URL có biến rỗng | Request root/POST chưa chạy hoặc script không tìm đúng relation/Location | Kiểm tra Post-response script, tên relation và response headers/body |
| Query không chạy khi dùng curl | URL có ký tự & chưa được quote hoặc sai tên parameter | Đặt toàn bộ URI trong dấu ngoặc kép và đối chiếu URI template trong link search |
| 401 Unauthorized hoặc 403 Forbidden | Thiếu thông tin xác thực hoặc user không có quyền | Kiểm tra cơ chế đăng nhập, token, role và cấu hình Spring Security |

Một số quy tắc khi debug:

- Xem cả status line, response headers và body bằng curl.exe -i.
- Dùng Content-Type để mô tả body đang gửi; dùng Accept để mô tả response muốn nhận.
- Theo _links.self.href và Location thay vì tự đoán ID.
- Tên collection trong _embedded có thể khác tên Java class vì relation được cấu hình riêng.
- Nếu link có templated: true, điền query parameter theo URI template trước khi gọi.
- Kiểm tra request body thực tế trong Postman Console khi gặp lỗi serialize hoặc biến môi trường.
- Không gửi JSON object vào association endpoint yêu cầu text/uri-list.

## 7. Checklist hoàn thành bài thực hành

- [ ] Ứng dụng đang chạy và base URL trỏ đúng service.
- [ ] GET root trả về HAL với các relation cần thiết.
- [ ] Client lấy collection URI từ _links.
- [ ] GET collection trả về representation và metadata phân trang.
- [ ] POST tạo item và client lưu Location hoặc _links.self.href.
- [ ] GET item đọc được dữ liệu vừa tạo.
- [ ] PATCH chỉ cập nhật trường được gửi.
- [ ] PUT thay thế toàn bộ representation theo đúng body.
- [ ] Search và paging/sorting dùng đúng URI template hoặc query parameter.
- [ ] DELETE xóa item và GET sau xóa xác nhận 404.
- [ ] Nếu có association, client gửi URI bằng text/uri-list.
- [ ] Postman collection variables được thiết lập và chuỗi request chạy đúng thứ tự.

## Tài liệu tham khảo chính thức

1. [Spring Getting Started — Accessing JPA Data with REST](https://spring.io/guides/gs/accessing-data-rest/): ví dụ đầy đủ với curl cho GET root, GET collection, POST, GET item, search, PUT, PATCH và DELETE.
2. [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): discoverability qua HAL, collection/item resources, HTTP methods, status code và media type.
3. [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): page, size, sort và các liên kết next/prev.
4. [Spring Data REST — Tools / HAL Explorer](https://docs.spring.io/spring-data/rest/reference/tools.html): khám phá HAL response, điều hướng URI template và thực hiện GET/POST/PUT/PATCH/DELETE bằng giao diện.
5. [Spring Data REST — Using cURL to talk to Spring Data REST](https://docs.spring.io/spring-data/rest/reference/introduction/example-api-usage-with-curl.html): danh sách hướng dẫn tương tác với Spring Data REST qua curl.
