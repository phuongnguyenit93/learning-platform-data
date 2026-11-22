# Ảnh hưởng của thay đổi rel và cấu trúc biểu diễn đến máy khách Spring Data REST

Spring Data REST công bố repository dưới dạng tài nguyên REST và dùng các liên kết hypermedia để hướng dẫn client khám phá chức năng. Với biểu diễn HAL, tên relation (rel) cho biết một liên kết có ý nghĩa gì; cấu trúc JSON cho biết dữ liệu và các tài nguyên liên quan được trình bày ra sao.

Khi thay đổi rel hoặc cấu trúc biểu diễn, API có thể vẫn trả về HTTP 200 nhưng client cũ vẫn hỏng vì không còn tìm thấy liên kết, không đọc được collection hoặc không ánh xạ được thuộc tính. Do đó, rel và representation là một phần của hợp đồng API mà máy khách phụ thuộc vào.

## 1. Rel trong HAL có vai trò gì?

HAL biểu diễn các liên kết trong thuộc tính _links. Mỗi key trong _links là một relation, còn giá trị thường chứa href và có thể có thêm metadata như templated.

Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people"
    },
    "search": {
      "href": "http://localhost:8080/people/search"
    },
    "profile": {
      "href": "http://localhost:8080/profile/people"
    }
  }
}
~~~

Trong ví dụ:

- self trỏ tới chính tài nguyên hiện tại.
- search cho biết nơi khám phá các phương thức tìm kiếm.
- profile trỏ tới mô tả profile của tài nguyên.

Client có thể tìm liên kết theo relation thay vì tự ghép URL. Điều này giúp server thay đổi host, context path hoặc đường dẫn cụ thể mà client vẫn có thể khám phá endpoint từ tài nguyên gốc.

HAL có các relation chuẩn như self, next, prev, first, last và các relation do ứng dụng định nghĩa. Relation tùy chỉnh nên có tên ổn định và ý nghĩa rõ ràng để client hiểu chức năng mà liên kết cung cấp.

## 2. Spring Data REST công bố rel ở những vị trí nào?

Spring Data REST dùng relation trong cả phần liên kết và phần tài nguyên được nhúng.

### Relation trong _links

Các liên kết điều hướng nằm trong _links. Ví dụ, một query method có thể được công bố trong search resource:

~~~java
public interface PersonRepository extends CrudRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    List<Person> findByLastName(@Param("lastName") String lastName);
}
~~~

Với collection resource /people, search resource có thể trả về:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/search"
    },
    "byLastName": {
      "href": "http://localhost:8080/people/search/by-last-name{?lastName}",
      "templated": true
    }
  }
}
~~~

Client tìm relation byLastName, điền biến lastName trong URI template rồi gọi endpoint. rel là tên liên kết trong HAL; path là đoạn URL của endpoint. Thay rel có thể làm thay đổi key trong _links dù href vẫn giữ nguyên.

### Relation trong _embedded

Khi HAL nhúng các tài nguyên con, key trong _embedded cũng là relation. Ví dụ:

~~~java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people"
)
public interface PersonRepository extends CrudRepository<Person, Long> {
}
~~~

Một collection response có thể có dạng:

~~~json
{
  "_embedded": {
    "people": [
      {
        "firstName": "An",
        "lastName": "Nguyen",
        "_links": {
          "self": {
            "href": "http://localhost:8080/people/1"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/people"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
~~~

Ở đây, collectionResourceRel = "people" quyết định relation dùng để biểu diễn collection trong HAL. Client thường đọc danh sách từ _embedded.people. Nếu relation này đổi thành persons, collection có thể được trình bày dưới _embedded.persons; client vẫn đọc _embedded.people sẽ không tìm thấy danh sách.

_links và _embedded phục vụ hai mục đích khác nhau: _links cung cấp đường dẫn để điều hướng, còn _embedded chứa representation của tài nguyên liên quan ngay trong response.

## 3. Đổi rel ảnh hưởng đến client như thế nào?

Giả sử phiên bản đầu của API công bố finder như sau:

~~~java
@RestResource(path = "by-last-name", rel = "byLastName")
List<Person> findByLastName(@Param("lastName") String lastName);
~~~

Client cũ có thể tìm _links.byLastName để gọi chức năng tìm kiếm. Sau đó server đổi relation:

~~~java
@RestResource(path = "by-last-name", rel = "peopleByLastName")
List<Person> findByLastName(@Param("lastName") String lastName);
~~~

Đường dẫn endpoint vẫn là /people/search/by-last-name, nhưng key liên kết đổi từ byLastName thành peopleByLastName.

Client phụ thuộc vào relation cũ có thể gặp các tình huống:

- Không tìm thấy _links.byLastName và bỏ qua chức năng tìm kiếm.
- Báo lỗi khi ứng dụng yêu cầu một relation bắt buộc.
- Tự ghép URL dựa trên convention cũ rồi gọi nhầm endpoint.
- Không thể khám phá chức năng dù server vẫn hoạt động bình thường.

Tương tự, đổi collectionResourceRel có thể làm client không tìm thấy collection trong _embedded. Đây là thay đổi có ảnh hưởng trực tiếp đến cách client đọc dữ liệu.

### Đổi rel khác với đổi path

| Thay đổi | Ảnh hưởng thường gặp |
|---|---|
| Đổi rel của finder | Key liên kết trong _links thay đổi |
| Đổi collectionResourceRel | Relation của collection trong HAL, thường là key trong _embedded, thay đổi |
| Đổi path | URL trong href thay đổi |
| Đổi @Param | Tên biến/query parameter trong URI template thay đổi |
| Đổi kiểu representation | Cấu trúc dữ liệu mà client phân tích có thể thay đổi |

Một thay đổi có thể tác động đến nhiều phần cùng lúc. Ví dụ, đổi cả path lẫn rel khiến client vừa phải tìm relation mới, vừa phải sử dụng URI mới nếu đang hard-code URL.

## 4. Thay đổi cấu trúc representation ảnh hưởng đến client ra sao?

Representation là nội dung tài nguyên được server trả về. Với Spring Data REST và HAL, response thường kết hợp dữ liệu miền, liên kết và metadata.

Một item resource có thể có dạng:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "active": true,
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/1"
    },
    "orders": {
      "href": "http://localhost:8080/people/1/orders"
    }
  }
}
~~~

Client có thể phụ thuộc vào tên trường, kiểu dữ liệu, cấu trúc lồng nhau và cách biểu diễn association. Các thay đổi sau đây có thể làm hỏng client:

- Đổi tên thuộc tính: lastName thành familyName khiến client đọc lastName nhận giá trị thiếu.
- Đổi kiểu dữ liệu: một trường từ số thành chuỗi có thể làm quá trình deserialize hoặc tính toán thất bại.
- Đổi cấu trúc lồng nhau: một giá trị đơn chuyển thành object hoặc object chuyển thành mảng làm thay đổi đường dẫn truy cập dữ liệu.
- Đổi cách nhúng association: dữ liệu trước đây được đọc trực tiếp từ _embedded có thể chỉ còn một liên kết trong _links, hoặc ngược lại.
- Đổi projection: response có thể thêm, bỏ hoặc thay đổi các thuộc tính được chọn để trình bày.
- Đổi cấu trúc collection: relation của danh sách, nội dung phần tử hoặc metadata phân trang thay đổi có thể ảnh hưởng đến màn hình danh sách và logic điều hướng.

Ví dụ, client đang đọc:

~~~javascript
const people = response._embedded.people;
const lastName = people[0].lastName;
~~~

Nếu collection relation chuyển thành persons, hoặc thuộc tính lastName đổi tên, đoạn code trên không còn hoạt động như trước.

## 5. Projection và association có thể làm thay đổi representation

Spring Data REST hỗ trợ projection để giới hạn các thuộc tính xuất hiện trong representation. Ví dụ:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

Client có thể yêu cầu projection nếu endpoint và cấu hình cho phép:

~~~http
GET /people/1?projection=personSummary
Accept: application/hal+json
~~~

Representation theo projection có thể chỉ chứa những thuộc tính được định nghĩa trong interface. Nếu server đổi projection mặc định hoặc thay đổi các getter của projection, client phụ thuộc vào trường cũ có thể không còn đọc được dữ liệu.

Association cũng cần được chú ý. Spring Data REST thường biểu diễn quan hệ giữa entity bằng các liên kết để client có thể điều hướng tới tài nguyên liên quan. Khi dùng projection hoặc cấu hình nhúng phù hợp, dữ liệu association có thể xuất hiện trực tiếp trong representation. Client cần biết mình đang nhận một link hay một object nhúng và xử lý đúng dạng đó.

Ví dụ, một liên kết association:

~~~json
{
  "_links": {
    "address": {
      "href": "http://localhost:8080/people/1/address"
    }
  }
}
~~~

Khác với dữ liệu association được nhúng:

~~~json
{
  "_embedded": {
    "address": {
      "city": "Hanoi",
      "country": "Vietnam"
    }
  }
}
~~~

Client đang truy cập address.city trực tiếp sẽ không thể dùng cùng cách truy cập khi server chỉ trả về liên kết address. Khi nhận link, client cần theo liên kết để lấy representation của tài nguyên liên quan.

## 6. Tác động đến client dùng HAL và HATEOAS

Client HATEOAS được thiết kế để khám phá chức năng qua liên kết và relation. Cách tiếp cận này giảm sự phụ thuộc vào URL cụ thể, nhưng không loại bỏ hoàn toàn hợp đồng giữa client và server.

Client vẫn cần biết:

- Relation nào đại diện cho chức năng cần sử dụng.
- Media type và định dạng representation mà server cung cấp.
- Các trường dữ liệu cần thiết cho nghiệp vụ.
- Kiểu dữ liệu và quy tắc xử lý collection, phân trang, association.
- Cách xử lý khi một liên kết tùy chọn hoặc thuộc tính không xuất hiện.

Ví dụ, client nên khám phá relation next để chuyển trang thay vì tự tạo URL bằng cách tăng tham số page:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people?page=0&size=20"
    },
    "next": {
      "href": "http://localhost:8080/people?page=1&size=20"
    }
  }
}
~~~

Nếu client tự ghép URL, nó phụ thuộc vào cấu trúc query parameter và convention của server. Nếu client theo liên kết next, server có thể thay đổi cách tạo URL phân trang mà client không cần biết chi tiết.

Tuy nhiên, nếu relation next bị đổi hoặc biến mất, client cũng cần có quy tắc xử lý phù hợp. Với relation chuẩn, nên giữ đúng ý nghĩa của relation và tránh tái sử dụng tên chuẩn cho chức năng khác.

## 7. Chiến lược giữ tương thích ngược khi thay đổi API

Trước khi đổi rel hoặc representation, hãy xác định client nào đang sử dụng hợp đồng hiện tại. Một thay đổi có thể ảnh hưởng đến ứng dụng web, ứng dụng di động, dịch vụ tích hợp hoặc các consumer bên ngoài.

Một số cách giảm rủi ro:

1. Giữ rel cũ khi còn client phụ thuộc. Nếu cần tên relation mới, cân nhắc công bố liên kết tương thích trong giai đoạn chuyển đổi nếu thiết kế và khả năng của framework cho phép.
2. Giữ path cũ hoặc có cơ chế chuyển hướng. Khi URL thay đổi, xem xét cách duy trì endpoint cũ trong thời gian migration.
3. Thêm trường theo hướng mở rộng. Thêm thuộc tính tùy chọn thường ít ảnh hưởng hơn việc đổi tên hoặc xóa trường đang được client sử dụng.
4. Tránh đổi kiểu và cấu trúc dữ liệu đột ngột. Nếu cần thay đổi lớn, cân nhắc versioning hoặc một representation mới.
5. Công bố rõ relation và ý nghĩa của nó. Tài liệu API nên mô tả relation, tham số và representation tương ứng.
6. Kiểm tra media type. Client và server cần thống nhất cách trao đổi HAL, thường dùng application/hal+json.
7. Kiểm tra projection. Nếu client dựa vào projection cụ thể, hãy giữ ổn định tên projection và các trường cần thiết trong thời gian tương thích.

Không phải mọi thay đổi đều có thể duy trì đồng thời hai representation hoặc hai relation trong mọi cấu hình. Hãy xác nhận khả năng thực tế của Spring Data REST và thiết kế versioning nếu cần một giai đoạn chuyển đổi rõ ràng.

## 8. Thiết kế client bền vững hơn

Client nên xử lý hypermedia một cách linh hoạt:

- Tìm liên kết trong _links theo relation thay vì hard-code URL.
- Với URI template, điền tham số theo template hoặc dùng thư viện hỗ trợ URI template.
- Đọc collection qua relation trong _embedded; không giả định mọi collection luôn có cùng tên key.
- Xử lý trường tùy chọn có thể vắng mặt hoặc có giá trị null.
- Bỏ qua các trường không biết khi deserialize nếu thư viện và hợp đồng cho phép.
- Không phụ thuộc vào thứ tự thuộc tính trong JSON.
- Theo liên kết association thay vì giả định dữ liệu luôn được nhúng.
- Phân biệt response collection, item resource và response phân trang.
- Kiểm tra media type trước khi áp dụng parser tương ứng.

Ví dụ đọc một finder link từ HAL:

~~~javascript
const finderLink = response._links?.byLastName;

if (finderLink) {
  const url = finderLink.href;
  // Điền biến lastName nếu href là URI template,
  // sau đó gửi request tới URL đã hoàn chỉnh.
}
~~~

Cách xử lý này cho phép client nhận biết khi chức năng không được công bố. Trong ứng dụng thực tế, nên có thông báo hoặc fallback phù hợp thay vì để lỗi truy cập thuộc tính lan ra toàn bộ luồng xử lý.

Bỏ qua trường không biết giúp client chịu được việc server bổ sung thuộc tính, nhưng không tự giải quyết được việc server xóa hoặc đổi tên trường mà client bắt buộc phải dùng. Tương tự, khám phá link theo rel giảm phụ thuộc vào URL nhưng client vẫn phụ thuộc vào ý nghĩa và sự ổn định của relation.

## 9. Kiểm thử hợp đồng giữa server và client

Khi thay đổi annotation hoặc projection, hãy kiểm tra response thực tế bằng integration test hoặc contract test.

Các tình huống nên được kiểm tra:

1. Gọi collection endpoint và xác nhận relation của collection trong _embedded.
2. Gọi search resource và xác nhận relation của từng query method trong _links.
3. Kiểm tra href, URI template và query parameter của finder.
4. Gọi item endpoint và xác nhận các thuộc tính cần thiết vẫn có tên, kiểu và cấu trúc như hợp đồng.
5. Kiểm tra association được biểu diễn dưới dạng link hay embedded resource theo thiết kế.
6. Kiểm tra projection mà client đang sử dụng.
7. Kiểm tra liên kết next, prev, first, last và metadata phân trang nếu API hỗ trợ phân trang.
8. Chạy lại contract test của các client đang được hỗ trợ sau khi thay đổi rel hoặc representation.

Một test chỉ kiểm tra HTTP status 200 là chưa đủ. Response có thể thành công nhưng relation hoặc thuộc tính đã đổi, khiến client không thể thực hiện nghiệp vụ.

## 10. Ví dụ thay đổi và tác động

| Thay đổi phía server | Client có thể gặp vấn đề |
|---|---|
| rel = "byLastName" đổi thành rel = "peopleByLastName" | Không tìm thấy finder link cũ |
| collectionResourceRel = "people" đổi thành "persons" | Không đọc được _embedded.people |
| path = "by-last-name" đổi thành "last-name" | URL cũ không còn trỏ đúng endpoint |
| @Param("lastName") đổi thành "familyName" | Client gửi query parameter cũ không còn khớp |
| lastName đổi thành familyName trong JSON | Client deserialize hoặc hiển thị thiếu họ |
| Association chuyển từ embedded object thành link | Client phải thực hiện thêm request để lấy dữ liệu liên quan |
| Projection bỏ firstName | Client phụ thuộc trường này không còn đủ dữ liệu |

## 11. Những điểm cần ghi nhớ

- rel đặt tên và ý nghĩa của liên kết trong HAL; client thường dùng relation để khám phá chức năng.
- _links chứa liên kết điều hướng, còn _embedded chứa representation của tài nguyên được nhúng.
- Đổi relation có thể làm client không tìm thấy finder hoặc collection dù endpoint vẫn phản hồi bình thường.
- Đổi path ảnh hưởng tới URL; đổi rel ảnh hưởng tới tên liên kết; đổi @Param ảnh hưởng tới tên query parameter.
- Đổi projection, thuộc tính entity hoặc cách biểu diễn association có thể làm thay đổi cấu trúc JSON mà client phân tích.
- HATEOAS giảm sự phụ thuộc vào URL cố định, nhưng client vẫn cần relation ổn định và representation có hợp đồng rõ ràng.
- Trước khi phát hành thay đổi, hãy kiểm tra response HAL và chạy contract test với các client đang sử dụng API.
