# `If-Match` cho PUT, PATCH, DELETE và phản hồi 412

## Mục tiêu

`If-Match` giúp client chỉ cập nhật hoặc xóa một resource khi resource đó vẫn ở phiên bản mà client đã đọc. Cơ chế này ngăn tình huống hai client cùng sửa một entity rồi request đến sau âm thầm ghi đè thay đổi của request trước (lost update).

Spring Data REST hỗ trợ conditional request dựa trên ETag. Server trả ETag khi đọc resource; client gửi lại giá trị đó trong header `If-Match` khi thực hiện `PUT`, `PATCH` hoặc `DELETE`. Nếu ETag không còn khớp với phiên bản hiện tại, server từ chối thao tác bằng `412 Precondition Failed`.

## ETag và thuộc tính `@Version`

ETag là mã định danh phiên bản của representation/resource do server phát ra. Với entity JPA, cách thông dụng để Spring Data REST hỗ trợ kiểm tra phiên bản là khai báo thuộc tính có `@Version`:

    @Entity
    public class Product {
        @Id
        @GeneratedValue
        private Long id;

        private String name;

        private BigDecimal price;

        @Version
        private Long version;

        // getters and setters
    }

`@Version` cho phép persistence provider phát hiện cập nhật đồng thời. Khi một transaction ghi entity, version được kiểm tra và tăng theo cơ chế optimistic locking của JPA. Spring Data REST có thể dùng thông tin phiên bản này để tạo ETag và kiểm tra precondition cho request có điều kiện.

ETag là giá trị opaque đối với client. Không tự tính ETag từ ID, timestamp hoặc trường `version`; hãy dùng nguyên giá trị server trả về, bao gồm cả dấu ngoặc kép nếu có. Không giả định ETag luôn là một số hoặc luôn bằng trực tiếp giá trị của thuộc tính `@Version`.

## Lấy ETag trước khi cập nhật

Đầu tiên, client đọc item resource và lưu header `ETag` trong response:

    GET /api/products/42 HTTP/1.1
    Host: localhost:8080
    Accept: application/hal+json

Response ví dụ:

    HTTP/1.1 200 OK
    Content-Type: application/hal+json
    ETag: "0"

    {
      "name": "Keyboard",
      "price": 75.00,
      "_links": {
        "self": {
          "href": "http://localhost:8080/api/products/42"
        }
      }
    }

Trong ví dụ, client lưu chính xác giá trị header `ETag: "0"`. Giá trị này chỉ minh họa; ETag thực tế do server quyết định.

## Dùng `If-Match` với PUT

`PUT` thay thế representation của resource theo hợp đồng endpoint. Client gửi ETag đã đọc trong `If-Match`:

    PUT /api/products/42 HTTP/1.1
    Host: localhost:8080
    Content-Type: application/json
    If-Match: "0"

    {
      "name": "Mechanical Keyboard",
      "price": 89.00
    }

Nếu resource vẫn có ETag khớp với `"0"`, server xử lý cập nhật. Sau khi cập nhật thành công, response có thể trả ETag mới; client cần lưu giá trị mới để dùng cho lần cập nhật tiếp theo.

Nếu một client khác đã cập nhật resource và ETag hiện tại đổi thành `"1"`, request vẫn gửi `If-Match: "0"` sẽ không được áp dụng. Server trả `412 Precondition Failed` để báo precondition không còn đúng.

## Dùng `If-Match` với PATCH

`PATCH` thay đổi một phần representation. Cơ chế kiểm tra phiên bản giống PUT: client gửi ETag gần nhất trong `If-Match` cùng patch document:

    PATCH /api/products/42 HTTP/1.1
    Host: localhost:8080
    Content-Type: application/merge-patch+json
    If-Match: "1"

    {
      "price": 92.00
    }

Ví dụ trên minh họa JSON Merge Patch; media type và định dạng patch phải khớp với loại patch endpoint hỗ trợ trong ứng dụng. `If-Match` bảo đảm patch chỉ được áp dụng nếu resource vẫn ở phiên bản mà client dựa vào khi tạo patch.

Không bỏ `If-Match` chỉ vì patch chỉ thay một trường. Một thay đổi ở trường khác giữa lúc đọc và lúc gửi patch vẫn có thể làm quyết định nghiệp vụ của client trở nên lỗi thời.

## Dùng `If-Match` với DELETE

Client cũng có thể yêu cầu chỉ xóa resource nếu nó chưa thay đổi kể từ lần đọc gần nhất:

    DELETE /api/products/42 HTTP/1.1
    Host: localhost:8080
    If-Match: "2"

Nếu ETag khớp, server tiếp tục xóa theo quyền truy cập và các ràng buộc của ứng dụng. Nếu resource đã thay đổi, server trả `412 Precondition Failed` và không thực hiện thao tác xóa theo precondition cũ.

Điều này hữu ích khi giao diện hiển thị thông tin resource để người dùng xác nhận xóa. Nếu resource đã được người khác chỉnh sửa trong lúc người dùng đang xem, client có thể yêu cầu người dùng tải lại trước khi xác nhận hành động.

## Ý nghĩa của phản hồi 412

`412 Precondition Failed` có nghĩa là điều kiện trong request không còn đúng tại thời điểm server xử lý. Với `If-Match`, nguyên nhân thường là ETag client gửi không khớp với ETag hiện tại của resource.

Ví dụ:

1. Client A đọc resource và nhận ETag `"4"`.
2. Client B đọc cùng resource, cập nhật thành công và server phát ETag mới `"5"`.
3. Client A gửi PUT với `If-Match: "4"`.
4. Server so sánh với phiên bản hiện tại, phát hiện ETag đã thay đổi và trả `412 Precondition Failed`.

Client A không nên tự động gửi lại cùng payload với ETag mới mà chưa đọc trạng thái mới. Cách xử lý an toàn là:

- Đọc lại resource để lấy representation và ETag mới.
- So sánh thay đổi hiện tại với ý định của người dùng hoặc nghiệp vụ.
- Kết hợp thay đổi của người khác nếu phù hợp.
- Tạo request mới dựa trên representation mới và gửi với ETag mới.
- Nếu xung đột không thể tự giải quyết, yêu cầu người dùng chọn cách xử lý.

`412` là xung đột precondition, khác với `409 Conflict` vốn thường biểu thị xung đột trạng thái hoặc quy tắc nghiệp vụ ở tầng ứng dụng. Client nên xử lý theo status và error body thực tế mà API cam kết.

## Nếu không gửi If-Match

Nếu client gửi PUT, PATCH hoặc DELETE mà không có `If-Match`, request không mang điều kiện phiên bản do client đọc trước đó. Vì vậy client không nhận được sự bảo vệ lost-update từ precondition này.

Với thao tác cần bảo vệ cập nhật đồng thời, hãy yêu cầu client gửi ETag. Có thể kiểm tra chính sách bắt buộc conditional request ở tầng API hoặc service nếu ứng dụng cần từ chối thao tác không có precondition. Không giả định mọi cấu hình Spring Data REST đều bắt buộc `If-Match` khi header bị bỏ qua.

Header `If-Match: *` có ý nghĩa HTTP là chỉ tiếp tục nếu resource hiện tại tồn tại; nó không xác nhận rằng resource vẫn ở đúng phiên bản client đã đọc. Nếu mục tiêu là chống lost update, dùng ETag cụ thể nhận từ response thay vì wildcard.

## Ví dụ với cURL

Đọc resource và xem ETag:

    curl -i http://localhost:8080/api/products/42 \
      -H "Accept: application/hal+json"

Sao chép chính xác ETag từ response rồi dùng trong PUT:

    curl -i -X PUT http://localhost:8080/api/products/42 \
      -H "Content-Type: application/json" \
      -H 'If-Match: "0"' \
      -d '{"name":"Mechanical Keyboard","price":89.00}'

Ví dụ PATCH:

    curl -i -X PATCH http://localhost:8080/api/products/42 \
      -H "Content-Type: application/merge-patch+json" \
      -H 'If-Match: "1"' \
      -d '{"price":92.00}'

Ví dụ DELETE:

    curl -i -X DELETE http://localhost:8080/api/products/42 \
      -H 'If-Match: "2"'

Các ETag `"0"`, `"1"` và `"2"` chỉ là ví dụ nối tiếp. Trong ứng dụng thật, luôn lấy ETag từ response gần nhất của chính resource đó.

## Kiểm tra cấu hình và hành vi

1. Khai báo `@Version` trên entity được expose qua Spring Data REST và bảo đảm persistence provider hỗ trợ optimistic locking.
2. Gửi GET đến item endpoint; xác nhận response có header `ETag`.
3. Gửi PUT với ETag vừa đọc; xác nhận cập nhật thành công và nhận ETag mới nếu response cung cấp.
4. Gửi PATCH với ETag hiện tại; xác nhận patch chỉ áp dụng khi precondition còn đúng.
5. Gửi DELETE với ETag hiện tại; xác nhận thao tác tuân theo điều kiện phiên bản.
6. Đọc resource ở hai client; cập nhật từ client thứ nhất rồi gửi request từ client thứ hai với ETag cũ; xác nhận server trả `412`.
7. Sau `412`, xác nhận dữ liệu không bị ghi đè bởi request cũ và client phải đọc lại trước khi quyết định gửi thay đổi mới.
8. Thử request không có `If-Match` để xác nhận chính sách của ứng dụng là cho phép hay bắt buộc conditional request.

Integration test nên kiểm tra cả status code, ETag trả về, trạng thái database sau request thành công và trạng thái database sau request có ETag cũ. Chỉ kiểm tra response `412` là chưa đủ nếu chưa xác nhận dữ liệu không bị thay đổi.

## Lưu ý triển khai

- Dùng `@Version` để bật optimistic locking ở persistence layer; ETag và `If-Match` cung cấp cơ chế truyền precondition qua HTTP.
- ETag phải được xem là opaque token. Giữ nguyên dấu ngoặc kép và không tự tăng hoặc tự tạo giá trị.
- Lưu ETag mới sau mỗi lần đọc hoặc cập nhật thành công; không tái sử dụng ETag cũ sau khi resource đã thay đổi.
- Áp dụng kiểm tra phiên bản cho PUT, PATCH và DELETE trên item URI; association endpoint hoặc custom endpoint cần được kiểm tra theo hỗ trợ thực tế của ứng dụng.
- Nếu response không có ETag, kiểm tra `@Version`, loại repository, cấu hình Spring Data REST và header của response trước khi cho phép client dựa vào conditional update.
- Optimistic locking không thay thế authorization, validation hoặc database constraint. Nó chỉ phát hiện request dựa trên phiên bản đã lỗi thời.

`If-Match` gắn thao tác ghi hoặc xóa với đúng phiên bản resource mà client đã đọc. Khi phiên bản thay đổi, `412 Precondition Failed` giúp ngăn ghi đè âm thầm; client cần đọc lại, giải quyết xung đột rồi mới gửi request mới.