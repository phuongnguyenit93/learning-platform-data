# `201 Created`, `Location` và cách lấy biểu diễn sau khi tạo

## Mục tiêu

Khi client tạo một entity qua Spring Data REST, request thường là `POST` đến collection endpoint của repository. Nếu tạo thành công, server trả về `201 Created` và header `Location` chứa URI của resource vừa được tạo. Client dùng URI này để truy cập chính xác resource mới, kể cả khi server tự sinh ID hoặc đường dẫn đã được cấu hình riêng.

## Gửi request tạo resource

Ví dụ repository `PersonRepository` được công bố tại `/people`, ứng dụng có base path `/api`, và entity có các trường `firstName`, `lastName`:

    POST /api/people HTTP/1.1
    Host: localhost:8080
    Content-Type: application/json
    Accept: application/hal+json

    {
      "firstName": "An",
      "lastName": "Nguyen"
    }

Spring Data REST nhận JSON, tạo entity và lưu qua repository. Khi thao tác thành công, response có dạng:

    HTTP/1.1 201 Created
    Location: http://localhost:8080/api/people/42

Trong ví dụ, `42` là ID do hệ thống cấp. Giá trị thực tế phụ thuộc cơ chế sinh khóa và dữ liệu hiện có; client không nên tự đoán ID hoặc tự ghép URI từ một quy tắc cố định.

## Ý nghĩa của `201 Created`

`201 Created` cho biết request đã tạo thành công một resource mới. Với Spring Data REST, resource được tạo là item thuộc collection repository nhận request.

Header `Location` cho biết URI của item vừa tạo. Đây là thông tin quan trọng để client tiếp tục thao tác với resource: đọc dữ liệu, cập nhật hoặc xóa theo URI đó. Hãy lấy nguyên giá trị header từ response, xử lý nó như một URI và không giả định rằng ID luôn là số hoặc đường dẫn luôn có dạng `/{id}`.

Đường dẫn trong `Location` chịu ảnh hưởng bởi đường dẫn collection của repository và base path ứng dụng. Ví dụ `spring.data.rest.base-path=/api` khiến URL được thêm tiền tố `/api`; `@RepositoryRestResource(path = "...")` có thể thay đổi phần collection path.

## Lấy biểu diễn của resource vừa tạo

Header `Location` là URI định danh resource; nó không đồng nghĩa response luôn chứa đầy đủ JSON của entity. Cấu hình mặc định của Spring Data REST không trả representation trong body của response tạo mới. Vì vậy client có thể gửi request `GET` đến URI nhận được trong `Location` để lấy biểu diễn:

    GET /api/people/42 HTTP/1.1
    Host: localhost:8080
    Accept: application/hal+json

Response đọc resource thường có dạng:

    HTTP/1.1 200 OK
    Content-Type: application/hal+json

    {
      "firstName": "An",
      "lastName": "Nguyen",
      "_links": {
        "self": {
          "href": "http://localhost:8080/api/people/42"
        },
        "person": {
          "href": "http://localhost:8080/api/people/42"
        }
      }
    }

Body thực tế phụ thuộc các thuộc tính entity, projection, cấu hình serialization và các liên kết mà ứng dụng công bố. Dùng URI `Location` để xác định resource rồi đọc representation từ response `GET`; không dựa vào ví dụ JSON cố định.

## Yêu cầu Spring Data REST trả body ngay trong response tạo mới

Nếu client cần representation ngay sau `POST`, có thể bật tùy chọn `return-body-on-create`:

    spring.data.rest.return-body-on-create=true

Trong Spring Boot, đặt thuộc tính này trong `application.properties` hoặc cấu hình tương đương của môi trường chạy ứng dụng. Khi bật, Spring Data REST có thể đưa representation của resource mới vào response `201 Created`. Header `Location` vẫn cung cấp URI của resource và vẫn nên được client sử dụng làm định danh chuẩn.

Nếu không bật tùy chọn này, client nên thực hiện `GET` đến `Location` khi cần dữ liệu vừa được lưu. Việc lấy body trực tiếp hay gọi `GET` là lựa chọn về cách client nhận representation; cả hai trường hợp đều dựa trên cùng resource đã tạo.

## Ví dụ với cURL

Có thể lưu header response của request tạo mới để lấy URI mà server trả về:

    curl -i -X POST http://localhost:8080/api/people \
      -H "Content-Type: application/json" \
      -H "Accept: application/hal+json" \
      -d '{"firstName":"An","lastName":"Nguyen"}'

Đọc giá trị `Location` trong response, sau đó gọi URI đó:

    curl -i http://localhost:8080/api/people/42 \
      -H "Accept: application/hal+json"

Trong ứng dụng thực tế, thay URL minh họa bằng đúng giá trị `Location` nhận được từ response đầu tiên. Ví dụ này tách hai bước để thể hiện rõ rằng ID và URI do server quyết định.

## Xử lý lỗi và các trường hợp cần chú ý

- `400 Bad Request`: JSON không hợp lệ hoặc dữ liệu không vượt qua validation; kiểm tra response để biết trường và nguyên nhân lỗi.
- `415 Unsupported Media Type`: request gửi media type không được endpoint hỗ trợ; khi gửi JSON, đặt `Content-Type: application/json`.
- `409 Conflict`: thao tác tạo xung đột với trạng thái hoặc ràng buộc dữ liệu của ứng dụng; xử lý theo chi tiết lỗi mà server trả về.
- Không có `Location` như mong đợi: kiểm tra response thực tế, endpoint nhận request và cấu hình Spring Data REST; client không nên tự dựng URI thay cho server.
- `GET` đến `Location` thất bại: kiểm tra URI có được giữ nguyên khi parse hay không, quyền truy cập của client, và resource có còn tồn tại hay không.

Validation, ràng buộc duy nhất và logic nghiệp vụ vẫn được áp dụng khi entity được tạo qua repository REST. `201 Created` chỉ được trả khi thao tác tạo hoàn tất thành công.

## Quy trình client nên thực hiện

1. Gửi `POST` đến collection endpoint với `Content-Type: application/json` và payload hợp lệ.
2. Kiểm tra status `201 Created`.
3. Đọc header `Location` và lưu URI được server trả về.
4. Nếu response đã có representation và client cần dùng ngay, đọc body đó; nếu không, gửi `GET` đến URI trong `Location` với `Accept: application/hal+json`.
5. Dùng các liên kết HAL trong representation để tiếp tục điều hướng hoặc thao tác với resource.

Không ghép URI từ ID giả định, không mặc định response `POST` luôn có body, và không nhầm `Location` với nội dung representation. Hai thông tin này phục vụ hai việc khác nhau: `Location` xác định resource mới, còn representation mô tả trạng thái và các liên kết của resource đó.