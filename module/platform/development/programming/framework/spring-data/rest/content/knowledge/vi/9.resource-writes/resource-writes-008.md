# JSON Merge Patch với application/merge-patch+json

## 1. JSON Merge Patch là gì?

JSON Merge Patch là định dạng mô tả thay đổi một phần của tài liệu JSON. Client gửi một JSON document chứa những thuộc tính cần thêm, thay thế hoặc xóa; server áp dụng document đó lên trạng thái hiện tại của resource.

Định dạng này được chuẩn hóa trong **RFC 7396** và thường dùng cùng HTTP method **PATCH**. Media type chuẩn là:

~~~~http
application/merge-patch+json
~~~~

Spring Data REST hỗ trợ media type này cho item resource. Client gửi patch document đến URI của một item, ví dụ:

~~~~http
PATCH /people/42
Content-Type: application/merge-patch+json
Accept: application/hal+json
~~~~

Body của Merge Patch không phải bản sao đầy đủ của entity. Nó là mô tả thay đổi theo cấu trúc JSON. Những thuộc tính không xuất hiện trong patch được giữ nguyên; thuộc tính có mặt được xử lý theo quy tắc của RFC 7396.

## 2. Phân biệt PUT, PATCH, JSON Merge Patch và JSON Patch

| Cơ chế | Ý nghĩa |
|---|---|
| PUT | Gửi representation mới để thay thế trạng thái của resource tại URI đích |
| PATCH | Gửi một patch document để server áp dụng các thay đổi lên resource |
| JSON Merge Patch | Định dạng patch dựa trên JSON object; null trong object biểu thị xóa member |
| JSON Patch | Định dạng patch dạng danh sách thao tác như add, remove, replace, move, copy và test theo đường dẫn |

Trong Spring Data REST, PUT thay thế trạng thái của item bằng request body, còn PATCH cập nhật một phần trạng thái. PATCH không tự xác định một định dạng body duy nhất; media type của request cho server biết client đang dùng định dạng patch nào.

JSON Merge Patch phù hợp khi resource chủ yếu là object JSON và nhu cầu cập nhật thường là thay giá trị field, thêm field hoặc xóa field. Nếu cần thao tác chính xác trên phần tử mảng, di chuyển giá trị, kiểm tra điều kiện ở một path hoặc biểu diễn rõ thao tác add/remove/replace, JSON Patch theo RFC 6902 có thể phù hợp hơn.

Không được gửi một JSON object bất kỳ rồi mặc định server hiểu nó theo Merge Patch. Hãy khai báo đúng Content-Type: application/merge-patch+json.

## 3. Quy tắc xử lý của RFC 7396

Có bốn quy tắc cần nhớ.

### Thuộc tính không xuất hiện trong patch được giữ nguyên

Giả sử resource hiện tại là:

~~~~json
{
  "firstName": "Frodo",
  "lastName": "Baggins",
  "email": "frodo@example.com",
  "active": true
}
~~~~

Client gửi:

~~~~json
{
  "firstName": "Sam"
}
~~~~

Kết quả:

~~~~json
{
  "firstName": "Sam",
  "lastName": "Baggins",
  "email": "frodo@example.com",
  "active": true
}
~~~~

Chỉ firstName thay đổi. Những field không được đề cập trong patch không bị xóa hoặc gán lại chỉ vì client không gửi chúng.

### Giá trị khác null thay thế hoặc thêm thuộc tính

Nếu field đã tồn tại, giá trị mới thay thế giá trị cũ. Nếu field chưa tồn tại, field đó được thêm vào:

~~~~json
{
  "nickname": "Ring-bearer",
  "active": false
}
~~~~

Patch trên thêm nickname và thay active thành false. Các giá trị false, 0 và chuỗi rỗng vẫn là giá trị bình thường; chúng không có nghĩa là bỏ qua field.

### Giá trị null trong object có nghĩa là xóa member

Giả sử resource có:

~~~~json
{
  "firstName": "Frodo",
  "email": "frodo@example.com",
  "phone": "+84-123-456"
}
~~~~

Client gửi:

~~~~json
{
  "phone": null
}
~~~~

Kết quả theo RFC 7396:

~~~~json
{
  "firstName": "Frodo",
  "email": "frodo@example.com"
}
~~~~

phone bị loại khỏi JSON document. Đây là điểm rất dễ nhầm: trong JSON Merge Patch, null không có nghĩa là “giữ field và đặt giá trị của nó thành null”; nó là chỉ thị xóa member đó.

Do đó, Merge Patch không thể biểu diễn trực tiếp ý định “đặt một property trong object thành JSON null” theo cùng cách với một giá trị thông thường. Nếu domain cần phân biệt rõ field bị bỏ qua, field được xóa và field được đặt thành null, hãy cân nhắc JSON Patch hoặc một request DTO có quy ước presence/null riêng.

### Object lồng nhau được merge đệ quy

Patch một object con không thay thế toàn bộ object con. Các member được merge tiếp theo cùng quy tắc:

~~~~json
{
  "firstName": "Frodo",
  "address": {
    "city": "Hobbiton",
    "country": "Shire",
    "postalCode": "12345"
  }
}
~~~~

Patch:

~~~~json
{
  "address": {
    "city": "Bree"
  }
}
~~~~

Kết quả:

~~~~json
{
  "firstName": "Frodo",
  "address": {
    "city": "Bree",
    "country": "Shire",
    "postalCode": "12345"
  }
}
~~~~

Chỉ address.city thay đổi. country và postalCode được giữ nguyên.

## 4. Mảng là trường hợp đặc biệt

Theo RFC 7396, array được xem là một giá trị hoàn chỉnh. Khi patch chứa một array, array đích được thay bằng array mới; các phần tử không được merge theo index.

Resource hiện tại:

~~~~json
{
  "name": "Travel kit",
  "tags": ["map", "compass", "rope"]
}
~~~~

Patch:

~~~~json
{
  "tags": ["map", "compass"]
}
~~~~

Kết quả:

~~~~json
{
  "name": "Travel kit",
  "tags": ["map", "compass"]
}
~~~~

Phần tử rope bị loại vì cả array đã được thay thế. Nếu muốn chỉ xóa phần tử ở index 2 mà giữ nguyên các phần tử khác, Merge Patch không cung cấp cú pháp đó.

Các giới hạn khác:

- null nằm bên trong array là một phần tử null bình thường, không phải chỉ thị xóa phần tử.
- Patch root là một scalar, array hoặc null sẽ thay thế toàn bộ target bằng giá trị đó.
- Nếu patch root là object nhưng target hiện tại không phải object, thuật toán bắt đầu từ một object rỗng rồi áp dụng các member của patch.
- Object rỗng {} không tạo thay đổi.

Vì vậy, Merge Patch đặc biệt phù hợp với resource có cấu trúc object. Với collection lớn hoặc thao tác theo từng phần tử, nên thiết kế endpoint nghiệp vụ hoặc chọn JSON Patch.

## 5. Ví dụ đầy đủ: cập nhật nhiều field của một person

Giả sử GET /people/42 trả về:

~~~~json
{
  "firstName": "Frodo",
  "lastName": "Baggins",
  "email": "frodo@example.com",
  "phone": "+84-123-456",
  "address": {
    "city": "Hobbiton",
    "country": "Shire"
  },
  "tags": ["traveler", "ring-bearer"]
}
~~~~

Client chỉ muốn đổi tên, đổi thành phố, xóa số điện thoại và thay danh sách tag. Patch document:

~~~~json
{
  "firstName": "Sam",
  "address": {
    "city": "Bree"
  },
  "phone": null,
  "tags": ["traveler"]
}
~~~~

Kết quả mong muốn:

~~~~json
{
  "firstName": "Sam",
  "lastName": "Baggins",
  "email": "frodo@example.com",
  "address": {
    "city": "Bree",
    "country": "Shire"
  },
  "tags": ["traveler"]
}
~~~~

Có thể đọc thay đổi như sau:

| Field | Kết quả | Lý do |
|---|---|---|
| firstName | Sam | Giá trị được thay thế |
| lastName | Baggins | Không có trong patch nên giữ nguyên |
| email | frodo@example.com | Không có trong patch nên giữ nguyên |
| address.city | Bree | Object lồng nhau được merge |
| address.country | Shire | Không có trong object patch nên giữ nguyên |
| phone | Bị xóa | Giá trị null trong object có nghĩa là xóa member |
| tags | ["traveler"] | Array được thay thế toàn bộ |

## 6. Gửi Merge Patch đến Spring Data REST

Giả sử repository được export tại /people và item có ID 42. Request mẫu:

~~~~bash
curl -i -X PATCH \
  "http://localhost:8080/people/42" \
  -H "Content-Type: application/merge-patch+json" \
  -H "Accept: application/hal+json" \
  -d '{
    "firstName": "Sam",
    "address": {
      "city": "Bree"
    },
    "phone": null,
    "tags": ["traveler"]
  }'
~~~~

Hai header có vai trò khác nhau:

- Content-Type: application/merge-patch+json nói với server rằng body tuân theo quy tắc JSON Merge Patch.
- Accept: application/hal+json yêu cầu representation HAL cho response nếu server trả body.

Accept không thay thế Content-Type. Nếu client gửi application/json trong khi muốn áp dụng Merge Patch, hành vi sẽ phụ thuộc cách server diễn giải media type đó; để request rõ ràng và portable, hãy dùng đúng media type chuẩn.

Có thể dùng response không có body nếu client không cần nhận representation sau cập nhật. Với Spring Data REST, response body và status code của thao tác cập nhật phụ thuộc Accept và cấu hình RepositoryRestConfiguration.setReturnBodyOnUpdate(…).

## 7. Spring Data REST xử lý PATCH như thế nào?

Spring Data REST công bố item resource dưới URI dạng:

~~~~text
/{repository}/{id}
~~~~

Theo tài liệu Repository resources hiện hành, item resource hỗ trợ GET, PUT, PATCH và DELETE, trừ khi ứng dụng chủ động thay đổi việc export method. Đối với PATCH:

- PATCH thực hiện cập nhật một phần trạng thái của item.
- Repository method được dùng để lưu thay đổi là save(…).
- Media type được tài liệu hiện hành liệt kê gồm application/hal+json, application/json, application/patch+json và application/merge-patch+json.
- Nếu các method save(…) không tồn tại hoặc bị ẩn bằng @RestResource(exported = false), PATCH trả 405 Method Not Allowed.

Điều này có nghĩa là endpoint PATCH của item phụ thuộc vào khả năng save của repository. Không cần tạo một query method tên mergePatch trong CrudRepository chỉ để Spring Data REST nhận diện media type.

Ví dụ repository:

~~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends CrudRepository<Person, Long> {
}
~~~~

Spring Data REST có thể cung cấp PATCH cho item resource /people/{id}. Việc xử lý body, binding và lưu entity được thực hiện bởi hạ tầng Spring Data REST/Jackson của phiên bản đang chạy. Các quy tắc Merge Patch ở cấp JSON vẫn là cơ sở để hiểu ý nghĩa của document; kết quả binding cuối cùng cần được kiểm chứng bằng integration test với domain model thực tế.

Nếu muốn tắt PATCH, có thể ẩn method save phù hợp hoặc cấu hình supported HTTP methods. Cần nhớ rằng save(…) cũng ảnh hưởng đến khả năng POST và PUT, vì các thao tác này cũng dùng save. Hãy kiểm tra riêng các method mà API muốn giữ lại.

## 8. Khác biệt giữa Merge Patch và cập nhật association

Spring Data REST có resource riêng cho association của entity. Ví dụ person có link address, roles hoặc orders. Những association resource có HTTP method và media type riêng; với association, Spring Data REST thường dùng text/uri-list để bind hoặc thêm resource liên quan.

Vì vậy, không nên mặc định rằng gửi một object JSON lồng nhau trong Merge Patch sẽ có cùng ý nghĩa với thao tác bind association qua URI. Cần phân biệt:

- Cập nhật field giá trị đơn giản hoặc object embedded thuộc representation.
- Thay đổi quan hệ giữa hai aggregate/repository resource.
- Thêm hoặc bỏ phần tử của collection association.

Với association, hãy đi theo link mà Spring Data REST cung cấp và dùng đúng contract của association resource. Ví dụ, một request PUT hoặc POST với text/uri-list có thể gắn URI của resource liên quan vào association. Kiểm tra response và trạng thái quan hệ sau khi thao tác để bảo đảm client đang thay đổi đúng loại dữ liệu.

## 9. Validation, binding và các field được phép cập nhật

JSON Merge Patch chỉ định cách hợp nhất document JSON. Nó không tự quyết định field nào được phép thay đổi theo nghiệp vụ.

Khi ánh xạ patch vào entity Java, cần lưu ý:

- Field không xuất hiện trong patch phải được giữ nguyên.
- Field có giá trị không hợp lệ phải bị validation từ chối.
- Field chỉ đọc, computed, audit hoặc thuộc quyền quản trị không nên được mở cho client sửa.
- ID, version và các thuộc tính do server quản lý cần được bảo vệ khỏi việc client ghi đè.
- Unknown property có thể bị bỏ qua hoặc gây lỗi tùy cấu hình Jackson và binding; hãy kiểm tra hành vi của ứng dụng.
- Việc xóa một JSON member có thể ánh xạ thành trạng thái null/absent trong object Java tùy kiểu domain, constructor, setter và cấu hình deserialization.

Nếu entity có nhiều field nhạy cảm, nên dùng DTO/command model cho thao tác cập nhật hoặc custom controller để kiểm soát allowlist field. Tránh bind request tùy ý vào entity có nhiều thuộc tính nội bộ rồi dựa vào giao diện client để ẩn field.

Ví dụ DTO cho phép sửa một số thuộc tính:

~~~~java
public record PersonPatchInput(
        @Size(max = 80) String firstName,
        @Email String email,
        AddressPatchInput address
) {
}

public record AddressPatchInput(
        @Size(max = 100) String city
) {
}
~~~~

DTO minh họa cấu trúc dữ liệu cho một custom endpoint. Nếu cần phân biệt field bị bỏ qua với field được gửi null, DTO thông thường có thể chưa đủ vì cả hai có thể được ánh xạ thành Java null. Khi đó cần dùng wrapper biểu diễn presence, JSON tree hoặc một cơ chế patch chuyên dụng.

## 10. Kiểm soát cập nhật đồng thời bằng ETag và If-Match

Một patch thường được tạo dựa trên representation mà client đã đọc trước đó. Nếu một client khác cập nhật resource trước khi patch được gửi, request cũ có thể ghi đè thay đổi mới hoặc tạo ra trạng thái không mong muốn.

HTTP PATCH không mặc định là idempotent. RFC 5789 yêu cầu server áp dụng toàn bộ patch một cách atomic: nếu không thể áp dụng đầy đủ thì không được để lại một phần thay đổi. RFC cũng khuyến nghị dùng conditional request khi patch phụ thuộc vào một trạng thái cơ sở đã biết.

Spring Data REST hỗ trợ ETag và header If-Match cho PUT, PATCH và DELETE khi resource có version metadata phù hợp. Ví dụ:

1. Client GET /people/42.
2. Server trả header ETag: "7".
3. Client gửi PATCH kèm If-Match: "7".
4. Server chỉ thực hiện cập nhật nếu ETag hiện tại vẫn khớp.
5. Nếu resource đã thay đổi, server trả 412 Precondition Failed.

Ví dụ:

~~~~http
PATCH /people/42 HTTP/1.1
Content-Type: application/merge-patch+json
Accept: application/hal+json
If-Match: "7"

{
  "firstName": "Sam"
}
~~~~

Với Spring Data JPA, có thể dùng thuộc tính @Version để đánh dấu version field:

~~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @Version
    private Long version;

    private String firstName;
}
~~~~

Spring Data REST sử dụng metadata version của store để tạo ETag và kiểm tra điều kiện cập nhật. Cần kiểm tra ETag thực tế trong response và bật/duy trì versioning đúng cách cho store đang dùng.

## 11. Các status code thường gặp

| Status | Ý nghĩa trong tình huống PATCH |
|---|---|
| 200 OK | Cập nhật thành công và server trả representation |
| 204 No Content | Cập nhật thành công nhưng response không có body |
| 400 Bad Request | Patch document không hợp lệ hoặc request body không thể parse/bind |
| 404 Not Found | Item resource không tồn tại |
| 405 Method Not Allowed | Repository không có hoặc không export method save cần thiết |
| 409 Conflict | Thay đổi xung đột với trạng thái hiện tại theo logic ứng dụng |
| 412 Precondition Failed | Header If-Match không khớp ETag hiện tại |
| 415 Unsupported Media Type | Content-Type patch không được endpoint hỗ trợ |
| 422 Unprocessable Content | Document hợp lệ về cú pháp nhưng không thể áp dụng theo quy tắc nghiệp vụ (nếu ứng dụng dùng status này) |

Status thực tế còn phụ thuộc cấu hình, validation, security filter, exception handler và phiên bản Spring Data REST. Hãy kiểm tra response của ứng dụng thay vì giả định mọi lỗi binding đều trả cùng một status.

## 12. Kiểm thử JSON Merge Patch

Một integration test nên kiểm tra cả quy tắc RFC lẫn việc Spring Data REST lưu entity.

Ví dụ với MockMvc:

~~~~java
mockMvc.perform(patch("/people/{id}", 42L)
        .contentType("application/merge-patch+json")
        .accept(MediaType.APPLICATION_HAL_JSON)
        .content("""
            {
              "firstName": "Sam",
              "address": {
                "city": "Bree"
              },
              "phone": null,
              "tags": ["traveler"]
            }
            """))
    .andExpect(status().isOk());
~~~~

Status trong test phụ thuộc cấu hình trả response body của Spring Data REST. Nếu cấu hình trả 204 khi không có body, hãy dùng isNoContent().

Sau request, kiểm tra trạng thái đã lưu bằng repository hoặc GET resource:

- firstName đã đổi thành Sam.
- address.city đã đổi thành Bree.
- address.country vẫn giữ giá trị cũ.
- phone đã được xóa theo quy tắc Merge Patch.
- tags đã được thay bằng array mới.

Nên có các test riêng cho:

1. Field không xuất hiện trong patch được giữ nguyên.
2. Field nhận giá trị null bị loại khỏi object JSON.
3. Object lồng nhau được merge đệ quy.
4. Array bị thay thế toàn bộ.
5. false, 0 và chuỗi rỗng được giữ như giá trị bình thường.
6. Patch rỗng {} không thay đổi dữ liệu.
7. Patch malformed hoặc Content-Type không hỗ trợ bị từ chối.
8. Field không được phép cập nhật không thể bị client ghi đè.
9. ETag cũ bị từ chối khi resource đã thay đổi.
10. Request thất bại không để lại trạng thái cập nhật dở dang.

## 13. Cách chọn Merge Patch hay JSON Patch

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Đổi vài field trong object | JSON Merge Patch |
| Thêm hoặc xóa member của object | JSON Merge Patch |
| Merge object lồng nhau | JSON Merge Patch |
| Thay cả một array | JSON Merge Patch |
| Sửa một phần tử array theo index | JSON Patch |
| Di chuyển hoặc sao chép giá trị giữa các path | JSON Patch |
| Kiểm tra một giá trị trước khi thay đổi bằng thao tác test | JSON Patch |
| Cần phân biệt rõ bỏ qua field, xóa field và gán JSON null | JSON Patch hoặc custom patch contract |

JSON Merge Patch dễ đọc vì document patch gần giống resource đích. JSON Patch biểu diễn thay đổi rõ ràng hơn dưới dạng operation list, nhưng client phải biết path và cấu trúc thao tác.

Không có định dạng nào phù hợp cho mọi resource. Hãy chọn dựa trên cấu trúc dữ liệu và các thao tác mà client cần thực hiện.

## 14. Kết luận

application/merge-patch+json là media type của JSON Merge Patch theo RFC 7396, thường được gửi trong body của HTTP PATCH. Field bị bỏ qua sẽ giữ nguyên, giá trị mới sẽ thay thế hoặc thêm field, null trong object sẽ xóa member, object lồng nhau được merge đệ quy và array được thay thế toàn bộ.

Spring Data REST hiện hỗ trợ media type này cho item PATCH và dùng save(…) để lưu thay đổi. Khi triển khai, cần chú ý binding vào domain model, association resource, field-level authorization, validation và cập nhật đồng thời bằng ETag/If-Match. Với những trường hợp cần thao tác chi tiết trên array hoặc cần phân biệt rõ null với absent, hãy chọn JSON Patch hoặc một contract cập nhật riêng.

## Tài liệu tham khảo

- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396.html)
- [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789.html)
- [Spring Data REST — Repository resources, item PATCH and supported media types](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Conditional operations with ETag and If-Match](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html)
