# Cập nhật từng phần bằng JSON theo media type được hỗ trợ

Spring Data REST cung cấp HTTP **PATCH** trên item resource để cập nhật một phần trạng thái entity. Client gửi phần dữ liệu hoặc các thao tác cần thay đổi trong request body; server nạp entity hiện tại, áp dụng phần cập nhật rồi gọi phương thức **save(…)** của repository.

Điểm quyết định cách server hiểu JSON là header **Content-Type**. Một object JSON đơn giản, JSON Merge Patch và JSON Patch có cấu trúc cùng quy tắc khác nhau. Chọn đúng media type giúp client và server thống nhất ý nghĩa của trường bị bỏ qua, trường có giá trị null, thao tác trên mảng và các thao tác thay thế/xóa.

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt PUT và PATCH trên item resource.
- Gửi partial update bằng application/json hoặc application/hal+json.
- Phân biệt JSON Merge Patch (application/merge-patch+json) với JSON Patch (application/json-patch+json).
- Chọn đúng Content-Type, đồng thời dùng Accept để điều khiển representation trả về.
- Kiểm tra các điều kiện để PATCH được công bố, các lỗi thường gặp và rủi ro bảo mật liên quan đến JSON Patch.

## 1. PATCH cập nhật một phần item resource

Giả sử repository people quản lý entity:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private String phoneNumber;
}
~~~

Repository:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Spring Data REST công bố item resource theo dạng:

~~~text
/people/{id}
~~~

Với một item đã tồn tại, các phương thức có ý nghĩa khác nhau:

| HTTP method | Ý nghĩa | Dữ liệu client gửi |
| --- | --- | --- |
| PUT | Thay thế trạng thái resource bằng representation được gửi | Representation đầy đủ theo hợp đồng cập nhật |
| PATCH | Cập nhật một phần trạng thái resource | Các trường hoặc thao tác cần thay đổi |
| GET | Đọc trạng thái hiện tại | Không có request body cho thao tác thông thường |

Ví dụ, trạng thái hiện tại:

~~~json
{
  "firstName": "An",
  "lastName": "Tran",
  "email": "an@example.com",
  "phoneNumber": "0900000000"
}
~~~

Nếu chỉ muốn đổi lastName, PATCH cho phép gửi phần thay đổi mà không cần gửi lại firstName, email và phoneNumber.

Spring Data REST xử lý PATCH của item resource thông qua phương thức save(…) nếu repository có công bố phương thức đó. Vì vậy, repository phải có khả năng lưu entity và không được tắt export của save(…).

## 2. Content-Type và Accept có vai trò khác nhau

Hai header thường xuất hiện trong request:

- **Content-Type** cho server biết định dạng và ngữ nghĩa của request body.
- **Accept** cho server biết client muốn nhận response theo media type nào.

Ví dụ:

~~~http
PATCH /people/1 HTTP/1.1
Content-Type: application/merge-patch+json
Accept: application/hal+json

{
  "lastName": "Nguyen"
}
~~~

Ở đây, server hiểu body theo JSON Merge Patch; client yêu cầu response ở dạng HAL JSON.

Không nên đổi Accept để sửa lỗi server không đọc được request body. Khi gặp lỗi 415 Unsupported Media Type, hãy kiểm tra trước Content-Type, media type thực sự được endpoint hỗ trợ và phiên bản Spring Data REST đang chạy.

## 3. Các media type PATCH được Spring Data REST công bố hỗ trợ

Tài liệu Repository resources của Spring Data REST 5.1.0 liệt kê các media type cho PATCH item resource:

| Media type | Cách dùng |
| --- | --- |
| application/json | Gửi object JSON chứa các trường muốn cập nhật theo cơ chế partial binding của Spring Data REST. |
| application/hal+json | Gửi JSON theo representation HAL. |
| application/merge-patch+json | Gửi tài liệu JSON Merge Patch theo RFC 7396. |
| application/patch+json | Được liệt kê trong bảng Supported Media Types của tài liệu Spring Data REST; kiểm tra runtime của phiên bản đang dùng trước khi chọn. |
| application/json-patch+json | Media type chuẩn của JSON Patch theo RFC 6902; Spring Security Advisory của Spring Data REST cũng xác định request JSON Patch bằng media type này. |

Có một khác biệt về cách ghi tên media type giữa bảng Supported Media Types trong tài liệu Repository resources (application/patch+json) và tài liệu chuẩn RFC 6902/Spring Security Advisory (application/json-patch+json). Khi dùng JSON Patch, ưu tiên media type chuẩn application/json-patch+json và kiểm thử trên đúng phiên bản thư viện đang chạy. Có thể kiểm tra hằng RestMediaTypes.JSON_PATCH_JSON trong dependency để xác nhận giá trị mà runtime nhận diện.

Các media type trên không thể thay thế cho nhau tùy ý. Ví dụ, body là một mảng thao tác op/path/value thì phải được gửi theo JSON Patch; body là object mô tả phần trạng thái mới thì dùng JSON hoặc Merge Patch phù hợp.

## 4. Partial update với application/json

Đây là cách đơn giản khi chỉ cần gửi các trường muốn thay đổi:

~~~http
PATCH /people/1 HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "lastName": "Nguyen",
  "phoneNumber": "0911111111"
}
~~~

Các thuộc tính không xuất hiện trong request body được giữ nguyên theo cơ chế partial update của Spring Data REST. Cơ chế này sử dụng DomainObjectReader để áp dụng một ObjectNode lên domain object hiện tại và có thể merge các object lồng nhau.

Ví dụ, nếu chỉ gửi:

~~~json
{
  "lastName": "Nguyen"
}
~~~

thì mục tiêu là đổi lastName; các trường khác không được gửi lại.

Cần phân biệt cách partial binding này với JSON Merge Patch theo RFC 7396:

- application/json là cách gửi object partial theo cơ chế Spring Data REST.
- Không tự suy ra rằng null, mảng hoặc object lồng nhau sẽ có đầy đủ ngữ nghĩa RFC 7396.
- Nếu cần hợp đồng rõ ràng về ý nghĩa của null và cách merge object, hãy chọn application/merge-patch+json.

DomainObjectReader là thành phần Spring Data REST áp dụng một JSON object lên entity hiện tại. Tài liệu API mô tả nó thực hiện merge đệ quy đối với object lồng nhau trong giới hạn của quá trình binding.

## 5. JSON Merge Patch — application/merge-patch+json

JSON Merge Patch được định nghĩa trong RFC 7396. Body có hình dạng gần giống JSON representation của resource và chỉ chứa các thành viên cần thay đổi.

Ví dụ trạng thái hiện tại:

~~~json
{
  "firstName": "An",
  "lastName": "Tran",
  "email": "an@example.com",
  "address": {
    "city": "Ho Chi Minh City",
    "district": "District 1"
  }
}
~~~

Client chỉ muốn đổi họ và thành phố:

~~~http
PATCH /people/1 HTTP/1.1
Content-Type: application/merge-patch+json
Accept: application/hal+json

{
  "lastName": "Nguyen",
  "address": {
    "city": "Da Nang"
  }
}
~~~

Ý nghĩa theo RFC 7396:

- Thành viên không xuất hiện trong patch được giữ nguyên.
- Thành viên mới được thêm vào.
- Thành viên đã tồn tại được thay bằng giá trị trong patch.
- Object lồng nhau được merge đệ quy.
- Thành viên có giá trị null biểu thị yêu cầu xóa thành viên đó khỏi target.
- Nếu giá trị patch là một mảng, mảng đích được thay bằng toàn bộ mảng mới; Merge Patch không có thao tác sửa riêng một phần tử mảng.

Ví dụ xóa giá trị email theo ngữ nghĩa Merge Patch:

~~~http
PATCH /people/1 HTTP/1.1
Content-Type: application/merge-patch+json
Accept: application/hal+json

{
  "email": null
}
~~~

Trong quá trình binding vào entity, việc xóa một thuộc tính có thể tương ứng với việc đặt thuộc tính đó về null. Kết quả cuối cùng còn phụ thuộc kiểu Java, validation, ràng buộc database và quy tắc nghiệp vụ. Nếu trường không cho phép null, thao tác có thể thất bại khi validate hoặc persist.

**Lưu ý quan trọng:** Merge Patch dùng null làm dấu hiệu xóa. Vì vậy, định dạng này không phù hợp nếu API cần phân biệt rõ “đặt giá trị thật thành null” với “xóa thành viên khỏi document”.

### Cập nhật object lồng nhau

Với body:

~~~json
{
  "address": {
    "city": "Da Nang"
  }
}
~~~

Merge Patch có ý nghĩa giữ lại các thành viên khác của address theo quy tắc merge đệ quy; district không bị xóa chỉ vì không xuất hiện trong patch.

Nếu muốn thay toàn bộ object hoặc collection, hãy thể hiện rõ cấu trúc đầy đủ cần thay và kiểm thử trên entity thực tế.

## 6. JSON Patch — application/json-patch+json

JSON Patch được định nghĩa trong RFC 6902. Thay vì gửi một object trạng thái partial, client gửi một **mảng các thao tác**. Mỗi thao tác chỉ rõ hành động và vị trí cần tác động.

Các thao tác chuẩn:

| op | Ý nghĩa |
| --- | --- |
| add | Thêm thành viên hoặc phần tử |
| remove | Xóa thành viên hoặc phần tử |
| replace | Thay giá trị tại vị trí đã tồn tại |
| move | Di chuyển giá trị từ vị trí nguồn sang vị trí đích |
| copy | Sao chép giá trị từ vị trí nguồn sang vị trí đích |
| test | Kiểm tra giá trị hiện tại có khớp điều kiện hay không |

Mỗi thao tác thường dùng các trường:

- op: tên thao tác.
- path: JSON Pointer trỏ tới vị trí cần thao tác.
- value: giá trị mới đối với add, replace hoặc test.
- from: vị trí nguồn đối với move và copy.

Ví dụ đổi lastName:

~~~http
PATCH /people/1 HTTP/1.1
Content-Type: application/json-patch+json
Accept: application/hal+json

[
  {
    "op": "replace",
    "path": "/lastName",
    "value": "Nguyen"
  }
]
~~~

Ví dụ thêm một phần tử vào cuối mảng tags:

~~~json
[
  {
    "op": "add",
    "path": "/tags/-",
    "value": "priority"
  }
]
~~~

Trong JSON Pointer:

- /lastName trỏ tới thuộc tính lastName ở cấp hiện tại.
- /address/city trỏ tới thuộc tính city bên trong address.
- Với mảng, dùng chỉ số như /tags/0; dấu - biểu thị vị trí cuối mảng khi thêm phần tử.
- Ký tự ~ và / trong tên thành viên cần được escape theo JSON Pointer: ~0 biểu diễn ~, ~1 biểu diễn /.

Các thao tác được áp dụng theo thứ tự xuất hiện trong mảng. Nếu thao tác trước thay đổi cấu trúc, thao tác sau được đánh giá trên trạng thái đã cập nhật.

Ví dụ kết hợp test và replace:

~~~json
[
  {
    "op": "test",
    "path": "/status",
    "value": "DRAFT"
  },
  {
    "op": "replace",
    "path": "/status",
    "value": "PUBLISHED"
  }
]
~~~

Nếu điều kiện test không đúng, patch không được xem là thành công. Đây là cách đặt điều kiện trên trạng thái hiện tại trước khi áp dụng thao tác tiếp theo.

## 7. Phân biệt JSON Patch và JSON Merge Patch

| Tiêu chí | JSON Merge Patch | JSON Patch |
| --- | --- | --- |
| Media type chuẩn | application/merge-patch+json | application/json-patch+json |
| Cấu trúc body | Object JSON có hình dạng gần giống resource | Mảng các operation object |
| Thay đổi field | Gửi tên field và giá trị mới | Dùng add, remove, replace cùng JSON Pointer |
| Xóa field | Gửi giá trị null | Dùng remove |
| Thay đổi mảng | Thường thay toàn bộ mảng | Có thể thao tác theo index hoặc vị trí cuối |
| Điều kiện trước khi sửa | Không có operation test riêng | Có test |
| Thứ tự thao tác | Ngữ nghĩa merge theo cấu trúc | Thứ tự operation trong mảng có ý nghĩa |
| Trường hợp phù hợp | Cập nhật một số trường/object đơn giản | Cần thao tác chính xác trên path, mảng hoặc cần kiểm tra điều kiện |

Ví dụ cùng mục tiêu đổi lastName:

**Merge Patch**

~~~json
{
  "lastName": "Nguyen"
}
~~~

**JSON Patch**

~~~json
[
  {
    "op": "replace",
    "path": "/lastName",
    "value": "Nguyen"
  }
]
~~~

Nếu chỉ đổi một vài field đơn giản, Merge Patch thường dễ đọc. Nếu cần chỉ định rõ từng thao tác, xử lý phần tử mảng hoặc kiểm tra trạng thái trước khi cập nhật, JSON Patch biểu đạt được nhiều hơn.

## 8. PUT và PATCH: tránh gửi thiếu dữ liệu với PUT

PUT thay thế trạng thái resource bằng request body. PATCH chỉ áp dụng phần thay đổi.

Giả sử entity hiện tại có firstName, lastName, email:

- Gửi PUT với chỉ {"lastName":"Nguyen"} có thể khiến các trường không gửi bị đặt về giá trị mặc định hoặc null tùy cơ chế binding.
- Gửi PATCH với cùng nội dung được hiểu là chỉ muốn đổi lastName.

Vì vậy, chọn PUT khi client sở hữu representation đầy đủ và muốn thay thế nó. Chọn PATCH khi client chỉ có một tập thay đổi.

Đừng dùng PATCH như một cách bỏ qua validation hoặc business rule. Dữ liệu sau khi áp dụng patch vẫn phải thỏa mãn validation, ràng buộc domain và persistence của ứng dụng.

## 9. Gửi request bằng curl

### 9.1. JSON partial object

~~~bash
curl -i -X PATCH -H "Content-Type: application/json" -H "Accept: application/hal+json" -d '{"lastName":"Nguyen"}' http://localhost:8080/people/1
~~~

### 9.2. JSON Merge Patch

~~~bash
curl -i -X PATCH -H "Content-Type: application/merge-patch+json" -H "Accept: application/hal+json" -d '{"lastName":"Nguyen","address":{"city":"Da Nang"}}' http://localhost:8080/people/1
~~~

### 9.3. JSON Patch

~~~bash
curl -i -X PATCH -H "Content-Type: application/json-patch+json" -H "Accept: application/hal+json" -d '[{"op":"replace","path":"/lastName","value":"Nguyen"}]' http://localhost:8080/people/1
~~~

Các ví dụ dùng host và path mặc định để minh họa. Nếu ứng dụng cấu hình base path, reverse proxy hoặc repository path khác, hãy dùng URI thực tế mà API công bố.

## 10. Điều kiện công bố PATCH và response

Theo Repository resources reference:

- Item resource hỗ trợ PATCH nếu cấu hình và repository cho phép.
- Spring Data REST gọi save(…) để lưu entity sau khi áp dụng patch.
- Nếu repository không có phương thức save(…) phù hợp hoặc phương thức này bị ẩn bằng @RestResource(exported = false), endpoint PATCH có thể trả 405 Method Not Allowed.
- Body response phụ thuộc Accept và cấu hình RepositoryRestConfiguration.setReturnBodyOnUpdate(…).

Khi response body được bật và client yêu cầu representation, cập nhật thường trả 200 OK cùng representation. Khi không trả body, response cập nhật thành công thường là 204 No Content. Cấu hình ứng dụng có thể thay đổi hành vi này.

Một số lỗi cần phân biệt:

| HTTP status | Tình huống thường gặp |
| --- | --- |
| 400 Bad Request | JSON sai cú pháp, JSON Patch operation không hợp lệ, path không áp dụng được hoặc dữ liệu không qua binding/validation |
| 404 Not Found | Item resource không tồn tại |
| 405 Method Not Allowed | PATCH/save không được công bố hoặc endpoint không hỗ trợ phương thức |
| 406 Not Acceptable | Server không tạo được response theo media type trong Accept |
| 415 Unsupported Media Type | Content-Type không được endpoint hỗ trợ |

Mã lỗi thực tế có thể phụ thuộc converter, exception handler và cấu hình ứng dụng. Khi chẩn đoán, hãy ghi lại method, URL, Content-Type, Accept, request body và response body/status.

## 11. Association resource có hợp đồng riêng

PATCH item resource và cập nhật association resource là hai luồng khác nhau.

Ví dụ item resource:

~~~text
/people/1
~~~

có thể nhận PATCH với JSON partial body theo media type được hỗ trợ.

Association resource, ví dụ:

~~~text
/people/1/address
~~~

có hợp đồng HTTP riêng. Theo Repository resources reference, PUT và POST trên association resource dùng text/uri-list để liên kết URI của tài nguyên; POST áp dụng cho association dạng collection. Không gửi một JSON Merge Patch object vào association endpoint rồi giả định nó có cùng ngữ nghĩa với PATCH item resource.

Hãy theo link association mà HAL representation trả về và dùng đúng phương thức/media type được tài liệu cho resource đó công bố.

## 12. Kiểm thử partial update

Một bài kiểm thử PATCH nên xác nhận cả trạng thái trước, request và trạng thái sau.

1. Tạo hoặc chuẩn bị một entity có nhiều field đã có giá trị.
2. Gửi PATCH chỉ chứa một field cần đổi.
3. Đọc lại item resource và xác nhận field được gửi đã thay đổi.
4. Xác nhận các field không gửi vẫn giữ nguyên.
5. Với Merge Patch, kiểm tra riêng trường null, object lồng nhau và mảng.
6. Với JSON Patch, kiểm tra từng operation, JSON Pointer path và thứ tự thao tác.
7. Gửi request có Content-Type không được hỗ trợ để xác nhận endpoint từ chối đúng cách.
8. Kiểm tra trường hợp repository tắt export save(…).
9. Kiểm tra validation và ràng buộc database khi patch đặt field về null hoặc thay đổi quan hệ.
10. Đọc lại dữ liệu qua repository hoặc API sau khi request kết thúc để xác nhận trạng thái đã persist.

Ví dụ kiểm tra giữ nguyên field không liên quan:

~~~text
Before:
firstName = An
lastName  = Tran
email     = an@example.com

PATCH:
{"lastName":"Nguyen"}

Expected:
firstName = An
lastName  = Nguyen
email     = an@example.com
~~~

Đừng chỉ kiểm tra HTTP status. Một request trả 2xx vẫn cần được xác nhận rằng đúng field đã thay đổi và các field khác giữ nguyên theo hợp đồng.

## 13. Bảo mật và phiên bản Spring Data REST

Spring đã công bố **CVE-2026-41729**, lỗi SpEL expression injection trong xử lý JSON Patch khi entity hoặc embedded type có thuộc tính persistent kiểu Map. Request JSON Patch có thể đưa map key vào JSON Pointer path; ở các phiên bản bị ảnh hưởng, path này có thể đi vào biểu thức SpEL mà chưa được kiểm tra an toàn.

Spring Security Advisory liệt kê các phiên bản bị ảnh hưởng:

- Spring Data REST 5.0.0 đến 5.0.5.
- Spring Data REST 4.5.0 đến 4.5.11.
- Spring Data REST 4.4.0 đến 4.4.14.
- Spring Data REST 4.3.0 đến 4.3.16.
- Spring Data REST 3.7.19 và các bản cũ hơn trong nhánh đó.

Các bản sửa lỗi được advisory nêu:

| Nhánh | Bản sửa |
| --- | --- |
| 5.0.x | 5.0.6 (OSS); 5.0.5.1 (Enterprise Support) |
| 4.5.x | 4.5.12 (OSS); 4.5.11.1 (Enterprise Support) |
| 4.4.x | 4.4.15 (Enterprise Support) |
| 4.3.x | 4.3.17 (Enterprise Support) |
| 3.7.x | 3.7.20 (Enterprise Support) |

Khi dùng JSON Patch, hãy kiểm tra dependency tree để biết phiên bản spring-data-rest-webmvc và các module Spring Data REST thực sự được resolve. Ưu tiên bản đã vá mới nhất còn được hỗ trợ cho nhánh ứng dụng. Không dựa riêng vào phiên bản Spring Boot được khai báo nếu dependency management hoặc override làm thay đổi phiên bản Spring Data REST cuối cùng.

Ngoài việc nâng cấp:

- Chỉ công bố PATCH cho người dùng có quyền sửa resource.
- Kiểm soát field có thể sửa bằng validation và logic nghiệp vụ.
- Không tin tưởng path, value hoặc URI do client gửi.
- Kiểm thử patch trên thuộc tính Map, object lồng nhau và association nếu domain model có các cấu trúc này.
- Không dùng PATCH để cho phép cập nhật tùy ý những field nội bộ như trạng thái kiểm duyệt, owner hoặc quyền truy cập.

## 14. Checklist nhanh

- [ ] Đã xác định request đang cập nhật item resource hay association resource.
- [ ] Đã chọn PUT hay PATCH đúng với ý nghĩa thay thế/cập nhật một phần.
- [ ] Content-Type khớp định dạng body.
- [ ] Accept khớp representation response mong muốn.
- [ ] Với Merge Patch, đã hiểu null là xóa và mảng được thay toàn bộ.
- [ ] Với JSON Patch, body là mảng operation và path dùng JSON Pointer hợp lệ.
- [ ] Đã kiểm tra save(…) được công bố.
- [ ] Đã kiểm tra response status/body theo cấu hình return body.
- [ ] Đã kiểm thử field không gửi vẫn giữ nguyên.
- [ ] Đã kiểm tra validation, authorization và phiên bản Spring Data REST đã vá.

## 15. Ghi nhớ

PATCH là thao tác cập nhật một phần item resource. Server hiểu request body theo Content-Type:

- application/json: object partial theo cơ chế binding của Spring Data REST.
- application/merge-patch+json: object patch theo RFC 7396, trong đó null biểu thị xóa thành viên.
- application/json-patch+json: mảng operation theo RFC 6902, dùng op, path, value và có thể có from.
- application/hal+json: representation HAL được Spring Data REST liệt kê trong nhóm media type hỗ trợ cho PATCH.

Dùng Accept để chọn định dạng response. Kiểm tra phiên bản thực tế và media type JSON Patch mà runtime nhận diện, vì tài liệu hiện hành có khác biệt về cách ghi application/patch+json và application/json-patch+json.

## Tài liệu tham khảo

- Spring Data REST Reference — Repository resources, Item Resource / PATCH: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST API — DomainObjectReader: https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/json/DomainObjectReader.html
- Spring Data REST API — RestMediaTypes: https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/RestMediaTypes.html
- RFC 7396 — JSON Merge Patch: https://www.rfc-editor.org/rfc/rfc7396.html
- RFC 6902 — JavaScript Object Notation (JSON) Patch: https://www.rfc-editor.org/rfc/rfc6902.html
- Spring Security Advisory — CVE-2026-41729: https://spring.io/security/cve-2026-41729/
