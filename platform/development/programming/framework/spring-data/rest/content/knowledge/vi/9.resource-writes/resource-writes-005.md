# PATCH cập nhật một phần và phân biệt với PUT trong Spring Data REST

Trong Spring Data REST, client có thể thay đổi tài nguyên bằng các phương thức HTTP như PUT và PATCH. Hai phương thức đều có thể cập nhật một item resource, nhưng thể hiện ý định khác nhau:

- **PUT** gửi representation dùng để thay thế trạng thái của tài nguyên tại URI đích.
- **PATCH** gửi những thay đổi cần áp dụng lên tài nguyên hiện tại, thường chỉ gồm các thuộc tính cần cập nhật.

Chọn đúng phương thức giúp client tránh vô tình ghi đè dữ liệu mà nó không định thay đổi. Đây cũng là một phần quan trọng của hợp đồng API khi nhiều client cùng cập nhật một loại tài nguyên.

## 1. Endpoint cập nhật tài nguyên trong Spring Data REST

Giả sử ứng dụng có repository:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Spring Data REST có thể công bố collection resource tại `/people` và item resource theo ID, ví dụ:

~~~http
GET /people/42
~~~

Để cập nhật item resource, client gửi request đến URI của chính tài nguyên đó:

~~~http
PUT /people/42
PATCH /people/42
~~~

Các thao tác này được Spring Data REST ánh xạ vào repository và cơ chế binding của domain object. URI thực tế phụ thuộc path, base path, cấu hình export và repository của ứng dụng.

Ví dụ dưới đây giả sử item resource là một người có các thuộc tính `firstName`, `lastName`, `email` và `active`.

## 2. PUT: gửi representation để thay thế tài nguyên

PUT thể hiện ý định đặt trạng thái của tài nguyên tại URI đích theo representation mà client gửi. Với Spring Data REST, client nên gửi đầy đủ các thuộc tính cần có trong representation cập nhật.

Ví dụ:

~~~http
PUT /people/42
Content-Type: application/json
Accept: application/hal+json

{
  "firstName": "An",
  "lastName": "Nguyen",
  "email": "an.nguyen@example.com",
  "active": true
}
~~~

Client đang gửi representation của người có ID 42. Đây là cách phù hợp khi client có dữ liệu đầy đủ và muốn thay thế trạng thái tài nguyên theo nội dung request.

Nếu client chỉ gửi:

~~~http
PUT /people/42
Content-Type: application/json

{
  "email": "an.new@example.com"
}
~~~

thì request vẫn mang ý nghĩa PUT. Client không nên giả định rằng các thuộc tính bị bỏ qua chắc chắn được giữ nguyên. Vì PUT là thao tác thay thế representation, các trường không được gửi có thể trở về giá trị mặc định hoặc null tùy cách Spring Data REST bind dữ liệu vào domain object, constructor, setter và logic của ứng dụng.

Vì vậy, nếu muốn giữ các trường khác, client nên gửi representation đầy đủ hoặc chọn PATCH để thể hiện rõ ý định cập nhật một phần.

PUT có tính idempotent theo ngữ nghĩa HTTP: gửi lại cùng một request nhiều lần phải đưa tài nguyên về cùng trạng thái đích như gửi một lần, miễn là request và trạng thái liên quan không đổi. Điều này không có nghĩa mọi side effect nghiệp vụ tùy chỉnh đều tự động chạy đúng một lần; ứng dụng cần thiết kế event và logic nghiệp vụ phù hợp.

## 3. PATCH: chỉ gửi những thuộc tính cần thay đổi

PATCH thể hiện ý định áp dụng một phần thay đổi lên tài nguyên hiện tại. Với Spring Data REST, cách sử dụng phổ biến là gửi một JSON object chỉ chứa các thuộc tính muốn cập nhật.

Ví dụ, client chỉ muốn đổi email:

~~~http
PATCH /people/42
Content-Type: application/json
Accept: application/hal+json

{
  "email": "an.new@example.com"
}
~~~

Trong trường hợp này, `firstName`, `lastName` và `active` không xuất hiện trong request nên không nằm trong phần thay đổi mà client yêu cầu. Đây là lựa chọn phù hợp khi client chỉ biết hoặc chỉ muốn sửa một vài trường.

Một ví dụ khác, cập nhật tên và trạng thái:

~~~http
PATCH /people/42
Content-Type: application/json

{
  "firstName": "Anh",
  "active": false
}
~~~

Client không cần gửi lại email và họ tên cũ nếu không định thay đổi chúng.

PATCH không được HTTP bảo đảm idempotent trong mọi trường hợp. Tuy nhiên, một request dạng gán giá trị như `{"active": false}` thường có thể được gửi lại mà vẫn đưa tài nguyên về cùng trạng thái. Các thao tác kiểu tăng số đếm hoặc thêm phần tử có thể có hành vi khác tùy cách server triển khai.

## 4. So sánh PUT và PATCH

| Tiêu chí | PUT | PATCH |
|---|---|---|
| Ý định | Thay thế trạng thái tài nguyên tại URI đích | Áp dụng thay đổi lên tài nguyên hiện tại |
| Nội dung request | Thường gửi representation đầy đủ | Thường chỉ gửi các trường cần thay đổi |
| Trường bị bỏ qua | Không nên giả định được giữ nguyên | Thường không thuộc phần cập nhật |
| Tính idempotent theo HTTP | Có | Không được bảo đảm chung |
| Trường hợp phù hợp | Client có toàn bộ trạng thái cần ghi | Client chỉ cần sửa một phần |
| Rủi ro phổ biến | Ghi đè dữ liệu không gửi kèm | Hiểu sai cách xử lý null, object lồng nhau hoặc association |

Cả hai request đều có thể trả về thành công, nhưng không thể xem chúng là hai cách viết tương đương. Ý nghĩa của request phụ thuộc vào phương thức HTTP và cách server triển khai việc cập nhật.

## 5. Phân biệt thuộc tính bị bỏ qua và thuộc tính null

Đây là điểm cần đặc biệt chú ý khi gửi PATCH.

Giả sử tài nguyên hiện tại có:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "email": "an.nguyen@example.com",
  "phone": "0900000000"
}
~~~

Nếu client gửi:

~~~json
{
  "email": "an.new@example.com"
}
~~~

thì client chỉ yêu cầu đổi email. Các trường không xuất hiện như `firstName`, `lastName` và `phone` không được client yêu cầu thay đổi.

Nếu client gửi:

~~~json
{
  "phone": null
}
~~~

thì đây là một giá trị được gửi tường minh. Với thuộc tính nullable và cơ chế binding tương ứng, nó có thể yêu cầu xóa giá trị phone hiện tại.

Cần phân biệt:

- **Không có key:** client không gửi thuộc tính đó.
- **Có key với giá trị null:** client gửi thuộc tính đó và đặt giá trị null.
- **Có key với giá trị cụ thể:** client yêu cầu đặt giá trị mới.

Khả năng xóa một thuộc tính còn phụ thuộc vào kiểu Java, validation, constructor/setter, quy tắc nghiệp vụ và cách Spring Data REST bind request. Nếu trường không cho phép null hoặc có validation bắt buộc, request có thể bị từ chối.

Không nên giả định mọi cấu trúc object lồng nhau hoặc collection đều được merge sâu theo cùng một quy tắc. Với nested object, danh sách và association, hãy kiểm tra hành vi của phiên bản Spring Data REST cùng model thực tế và viết integration test cho trường hợp cần hỗ trợ.

## 6. PATCH không đồng nghĩa với mọi định dạng JSON Patch

PATCH là HTTP method; bản thân tên phương thức không quy định duy nhất định dạng body. Có nhiều cách biểu diễn một phần thay đổi, chẳng hạn JSON Patch theo RFC 6902 hoặc JSON Merge Patch theo RFC 7396.

Ví dụ JSON Patch dùng danh sách thao tác:

~~~json
[
  {
    "op": "replace",
    "path": "/email",
    "value": "an.new@example.com"
  }
]
~~~

JSON Merge Patch có thể dùng object JSON để biểu diễn các giá trị cần hợp nhất:

~~~json
{
  "email": "an.new@example.com",
  "phone": null
}
~~~

Cách PATCH thông dụng của Spring Data REST dùng representation JSON một phần với `Content-Type: application/json`. Không nên tự động giả định endpoint repository chấp nhận mọi media type hoặc mọi cú pháp JSON Patch/Merge Patch chỉ vì HTTP method là PATCH.

Nếu ứng dụng muốn hỗ trợ RFC 6902 hoặc RFC 7396, cần xác nhận endpoint và cấu hình thực tế có hỗ trợ media type đó hay không; nếu dùng custom controller, phần triển khai phải xử lý đúng định dạng tương ứng.

## 7. Cập nhật association và collection

Domain object có thể chứa association như địa chỉ, đơn hàng hoặc nhóm thành viên. Spring Data REST thường công bố association dưới dạng các liên kết có thể khám phá.

Ví dụ item resource:

~~~json
{
  "firstName": "An",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "address": {
      "href": "http://localhost:8080/people/42/address"
    }
  }
}
~~~

Khi muốn thay đổi association, hãy xem relation và endpoint association mà server công bố. Một endpoint association có thể nhận URI của tài nguyên liên quan theo hợp đồng của Spring Data REST.

Ví dụ minh họa cập nhật liên kết địa chỉ:

~~~http
PUT /people/42/address
Content-Type: text/uri-list

http://localhost:8080/addresses/7
~~~

Request này minh họa cách gán association qua URI của tài nguyên liên quan. Nó khác với PATCH các thuộc tính scalar trên `/people/42`.

Với collection association, cần phân biệt thao tác thay thế danh sách liên kết với thao tác cập nhật một phần. Không nên gửi một mảng rút gọn bằng PUT nếu mục tiêu chỉ là thêm một phần tử mà không thay thế quan hệ hiện tại. Hãy dựa vào endpoint association, media type và semantics mà API công bố; kiểm thử riêng trường hợp thêm, thay thế và gỡ liên kết.

## 8. Validation, authorization và logic nghiệp vụ

Dùng PATCH không có nghĩa request được bỏ qua validation. Các ràng buộc domain và validation của ứng dụng vẫn có thể được áp dụng khi Spring Data REST bind và lưu entity.

Một số điểm cần kiểm tra:

- Thuộc tính có được phép cập nhật qua REST hay không.
- Giá trị mới có hợp lệ và thỏa mãn ràng buộc domain hay không.
- Client có quyền thực hiện thao tác cập nhật hay không.
- Việc cập nhật một trường có làm thay đổi bất biến nghiệp vụ hoặc trạng thái liên quan hay không.
- Association được phép gán có thuộc phạm vi người dùng được truy cập hay không.

Ví dụ, client có thể gửi PATCH chỉ đổi `email`, nhưng ứng dụng vẫn cần xác thực định dạng email, kiểm tra quyền và bảo đảm email không trùng nếu domain yêu cầu.

Nếu có logic nghiệp vụ cần phối hợp nhiều trường, hãy đặt logic đó trong service/domain layer hoặc cơ chế phù hợp của ứng dụng. Không nên dựa vào việc client gửi đầy đủ trường hay chỉ gửi một trường để bảo vệ bất biến dữ liệu.

## 9. Đồng thời cập nhật và tránh ghi đè dữ liệu

Khi nhiều client cùng đọc rồi cập nhật một tài nguyên, request đến sau có thể ghi đè thay đổi của request đến trước. PATCH giảm lượng dữ liệu phải gửi nhưng tự nó không giải quyết mọi xung đột đồng thời.

Nếu ứng dụng sử dụng optimistic locking, entity có thể có trường phiên bản, ví dụ:

~~~java
@Version
private Long version;
~~~

Khi Spring Data REST và cấu hình ứng dụng cung cấp ETag/conditional request, client có thể đọc ETag rồi gửi điều kiện `If-Match` khi cập nhật. Server có thể từ chối request nếu representation đã thay đổi kể từ lần đọc trước, thường bằng phản hồi precondition failed.

Ví dụ dạng request có điều kiện:

~~~http
PATCH /people/42
If-Match: "version-etag"
Content-Type: application/json

{
  "email": "an.new@example.com"
}
~~~

Tên ETag ở trên chỉ là minh họa. Client phải sử dụng đúng giá trị ETag nhận từ response của server và chỉ dựa vào cơ chế này khi ứng dụng thực sự bật, cấu hình và kiểm thử optimistic locking.

## 10. Kiểm thử PUT và PATCH

Nên kiểm thử cả trạng thái trước và sau request thay vì chỉ xác nhận status code.

Ví dụ với PATCH:

1. Tạo hoặc chuẩn bị người có firstName, lastName, email và phone.
2. Gửi PATCH chỉ chứa email mới.
3. Đọc lại item resource.
4. Xác nhận email đã đổi và các thuộc tính không gửi vẫn giữ giá trị cũ.
5. Gửi PATCH với một trường nullable đặt null và xác nhận hành vi xóa giá trị đúng như hợp đồng.
6. Kiểm tra validation khi gửi giá trị không hợp lệ.

Ví dụ với PUT:

1. Chuẩn bị representation đầy đủ của tài nguyên.
2. Gửi PUT với toàn bộ trường mà client có ý định duy trì.
3. Đọc lại tài nguyên và xác nhận trạng thái khớp representation mong muốn.
4. Thử trường hợp bỏ một thuộc tính để hiểu rõ cách binder và domain model xử lý trường bị thiếu.
5. Kiểm tra association, validation và quyền cập nhật.

Ngoài ra, nên kiểm tra request sai media type, tài nguyên không tồn tại, ID không hợp lệ, cập nhật không được phép và xung đột phiên bản nếu optimistic locking được bật.

## 11. Cách chọn phương thức trong ứng dụng

Dùng PUT khi client có representation đầy đủ và muốn thay thế trạng thái tài nguyên theo nội dung đó. Dùng PATCH khi client chỉ muốn thay đổi một tập con thuộc tính và server hỗ trợ cách cập nhật một phần tương ứng.

Ví dụ:

- Một màn hình quản trị tải đầy đủ thông tin người dùng, cho phép chỉnh sửa toàn bộ form và gửi lại toàn bộ representation: PUT có thể phù hợp.
- Một màn hình chỉ cho đổi email hoặc bật/tắt trạng thái: PATCH thường phù hợp hơn.
- Một thao tác thay đổi association: dùng endpoint association và semantics mà API công bố, thay vì đoán cách PATCH một field lồng nhau.
- Một cập nhật cần tránh ghi đè dữ liệu của client khác: kết hợp optimistic locking/conditional request nếu ứng dụng hỗ trợ.

## 12. Những điểm cần ghi nhớ

- PUT thể hiện ý định thay thế trạng thái tài nguyên tại URI đích; client thường gửi representation đầy đủ.
- PATCH thể hiện ý định áp dụng thay đổi một phần; client chỉ gửi các thuộc tính cần cập nhật.
- Với PATCH, key bị bỏ qua khác với key có giá trị null.
- PUT và PATCH có semantics HTTP khác nhau; không chọn phương thức chỉ dựa trên việc body JSON ngắn hay dài.
- PATCH trong Spring Data REST thường dùng JSON object một phần với `Content-Type: application/json`; không mặc định coi nó là JSON Patch RFC 6902 hoặc JSON Merge Patch RFC 7396.
- Association và collection có endpoint, media type và quy tắc riêng; hãy kiểm tra liên kết được công bố và test hành vi thay thế/thêm/gỡ.
- Validation, authorization, logic domain và xử lý xung đột đồng thời vẫn cần được áp dụng khi cập nhật.
