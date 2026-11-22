# Liên kết profile và khả năng tự mô tả của tài nguyên trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao Spring Data REST trả về các liên kết hypermedia cùng representation của resource; khám phá API từ API root; phân biệt link self, collection, item, association, search và profile; dùng profile để lấy metadata ALPS hoặc JSON Schema; và xây dựng client điều hướng theo link do server cung cấp thay vì tự ghép URL.

## 1. Tài nguyên tự mô tả là gì?

Một REST resource tự mô tả (self-descriptive resource) cung cấp đủ thông tin để client hiểu response đang nói về resource nào, dữ liệu có ý nghĩa gì ở mức representation, và có thể thực hiện bước tiếp theo bằng cách nào. Khả năng này thường đến từ sự kết hợp của:

- HTTP method, status code và header.
- Media type trong request và response.
- Các link hypermedia cùng relation mô tả mục đích của link.
- Metadata/profile giải thích semantics và cấu trúc dữ liệu.
- Representation hiện tại và các resource được nhúng (embedded resources), nếu có.

Ví dụ, một response JSON có field id, name và address nhưng không có media type rõ ràng hoặc link relation có thể buộc client phải biết trước URL và ý nghĩa từng field. Với hypermedia, server trả representation kèm các link như self, people, search, profile hoặc next. Client đọc relation để biết link dùng làm gì rồi theo URI thực tế server trả về.

Khái niệm này thường gắn với HATEOAS (Hypermedia as the Engine of Application State): client khám phá các hành động có thể thực hiện tiếp theo từ hypermedia controls trong response. Client vẫn cần hiểu media type và semantics của relation; hypermedia không tự làm cho một client hoàn toàn không cần kiến thức về nghiệp vụ.

## 2. Spring Data REST sử dụng HAL để biểu diễn resource

Spring Data REST thường dùng HAL (Hypertext Application Language) để biểu diễn tài nguyên. HAL JSON đặt các liên kết trong object _links và các resource được nhúng trong _embedded.

Ví dụ response collection:

```json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people"
    },
    "profile": {
      "href": "http://localhost:8080/profile/people"
    },
    "search": {
      "href": "http://localhost:8080/people/search"
    }
  },
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
  "page": {
    "size": 20,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
```

Đây là response minh họa đã rút gọn. Tên relation, URL, các trường page và nội dung embedded thực tế phụ thuộc repository path, cấu hình, projection và dữ liệu.

Các thành phần quan trọng:

- _links: các hypermedia link mà client có thể theo.
- _embedded: các resource được nhúng trong representation hiện tại.
- page: thông tin phân trang của collection.
- self: URI của chính resource hoặc collection đang được biểu diễn.

Một item resource cũng có self link và có thể có link tới các association như address, orders hoặc các resource liên quan. Client nên đọc URI trong link thay vì suy ra URI từ ID.

## 3. Bắt đầu khám phá từ API root

API root là entry point để client bắt đầu tương tác với Spring Data REST. Khi ứng dụng export repository, root thường cung cấp link tới collection resource của từng repository cùng link profile.

Ví dụ:

```http
GET /
Accept: application/hal+json
```

Response rút gọn:

```json
{
  "_links": {
    "people": {
      "href": "http://localhost:8080/people"
    },
    "orders": {
      "href": "http://localhost:8080/orders"
    },
    "profile": {
      "href": "http://localhost:8080/profile"
    }
  }
}
```

Client bắt đầu bằng URL entry point đã được cấu hình hoặc được cung cấp. Từ đó, client tìm relation people để mở collection, orders để mở collection khác, hoặc profile để khám phá metadata.

Không nên hard-code các path /people, /orders hay /profile vào mọi client chỉ vì các ví dụ dùng những path này. Ứng dụng có thể đổi base path, repository path hoặc collection relation bằng cấu hình. API root là nơi công bố các link hiện hành.

Ví dụ repository:

```java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
}
```

```java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

Với cấu hình trên, Spring Data REST export repository thành collection resource và công bố link relation tương ứng ở API root.

## 4. Hiểu các loại link thường gặp

Các link có relation khác nhau mô tả những hướng điều hướng khác nhau. Một số relation phổ biến trong Spring Data REST/HAL:

| Relation | Mục đích | Ví dụ |
| --- | --- | --- |
| self | URI của resource hiện tại | Item /people/1 |
| Tên collection, ví dụ people | Mở collection resource | /people |
| profile | Tìm metadata/profile mô tả semantics của resource hoặc API | /profile hoặc profile cụ thể |
| search | Khám phá các query resource được công bố | /people/search |
| Tên association, ví dụ address | Truy cập resource liên kết | /people/1/address |
| first, prev, next, last | Điều hướng các trang collection | Link phân trang |
| related hoặc relation tùy chỉnh | Truy cập resource liên quan theo semantics của API | URI do server cung cấp |

Tên relation cụ thể phụ thuộc media type, cấu hình và loại resource. Không phải response nào cũng có tất cả các relation trong bảng. Client cần kiểm tra link thực tế có trong response.

### Link có thể là URI template

Một số link có thể chứa URI template và thuộc tính templated: true, ví dụ:

```json
{
  "_links": {
    "findByLastName": {
      "href": "http://localhost:8080/people/search/findByLastName{?name}",
      "templated": true
    }
  }
}
```

Client cần điền biến template theo quy tắc URI template, ví dụ name=Nguyen, thay vì nối chuỗi thủ công. Không được giả định mọi link là URL hoàn chỉnh không có biến.

### Link và embedded resource khác nhau

Link cho phép client điều hướng đến resource khác khi cần. Embedded resource đưa representation của resource liên quan ngay trong response hiện tại. Embedded data có thể giảm số request, nhưng không thay thế link self hoặc các link cần thiết để tiếp tục tương tác.

Client nên dùng link khi cần lấy representation mới nhất hoặc thực hiện thao tác trên resource đích. Dữ liệu embedded có thể là projection hoặc representation rút gọn, nên không được mặc định nó chứa toàn bộ thuộc tính của resource gốc.

## 5. Profile link dùng để làm gì?

Relation profile giúp client tìm metadata mô tả thêm semantics của resource hoặc API. Trong Spring Data REST, API root cung cấp link profile. Client theo link đó để xem danh sách profile của các repository được export.

Ví dụ:

```http
GET /profile
Accept: application/hal+json
```

Response có thể liệt kê các link profile:

```json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/profile"
    },
    "people": {
      "href": "http://localhost:8080/profile/people"
    },
    "orders": {
      "href": "http://localhost:8080/profile/orders"
    }
  }
}
```

Client theo link profile của repository cần tìm, ví dụ /profile/people. URI profile cụ thể có thể cung cấp các định dạng metadata khác nhau tùy theo header Accept.

Profile không phải endpoint CRUD của resource. Nó cung cấp mô tả về resource và semantics của API để client, tài liệu hoặc tooling hiểu representation tốt hơn.

## 6. Lấy ALPS profile từ Spring Data REST

Spring Data REST cung cấp metadata ALPS (Application-Level Profile Semantics) cho repository. ALPS mô tả các descriptor về semantics và affordance của resource, ví dụ:

- Các property hoặc semantic descriptor của representation.
- Các thao tác an toàn, idempotent hoặc không an toàn.
- Resource type mà một thao tác tạo hoặc trả về liên quan đến.
- Các projection được công bố, tùy cấu hình.

Client theo profile link rồi yêu cầu ALPS:

```http
GET /profile/people
Accept: application/alps+json
```

Ví dụ ALPS document rút gọn:

```json
{
  "version": "1.0",
  "descriptors": [
    {
      "id": "person",
      "descriptors": [
        { "name": "firstName", "type": "SEMANTIC" },
        { "name": "lastName", "type": "SEMANTIC" }
      ]
    },
    {
      "id": "get-people",
      "name": "people",
      "type": "SAFE",
      "rt": "#person"
    },
    {
      "id": "create-people",
      "name": "people",
      "type": "UNSAFE",
      "rt": "#person"
    }
  ]
}
```

Đây là ví dụ minh họa. Descriptor thực tế do Spring Data REST tạo ra phụ thuộc domain type, repository, projection và phiên bản framework.

ALPS tập trung vào ngữ nghĩa và các transition có thể khám phá. Nó không thay thế schema dữ liệu chi tiết hoặc tài liệu HTTP contract đầy đủ.

## 7. Lấy JSON Schema từ cùng profile URI

Spring Data REST có thể cung cấp JSON Schema cho repository profile. Dùng cùng URI profile và thay đổi content negotiation:

```http
GET /profile/people
Accept: application/schema+json
```

Ví dụ JSON Schema rút gọn:

```json
{
  "$schema": "https://json-schema.org/draft-04/schema#",
  "title": "Person",
  "type": "object",
  "properties": {
    "firstName": {
      "type": "string"
    },
    "lastName": {
      "type": "string"
    }
  }
}
```

JSON Schema mô tả hình dạng dữ liệu như object, property, kiểu dữ liệu và một số constraint. Client có thể dùng nó để sinh form, kiểm tra JSON hoặc tạo model.

Cần phân biệt:

- ALPS trả lời câu hỏi về semantics và affordances của resource.
- JSON Schema trả lời câu hỏi về cấu trúc và constraint của JSON.
- Profile URI là điểm lấy metadata; collection/item URI mới là resource endpoint để thao tác dữ liệu.

Cả hai dạng metadata đều được chọn bằng media type. Hãy đọc Content-Type của response và không giả định server luôn trả đúng định dạng chỉ vì client đã gửi một header Accept.

## 8. Search link và query resources

Spring Data REST có thể công bố các query method của repository dưới resource search. Client khám phá link search từ collection thay vì tự đoán URL query.

Ví dụ repository:

```java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    List<Person> findByLastName(@Param("name") String lastName);
}
```

Spring Data REST có thể cung cấp link dạng:

```json
{
  "_links": {
    "search": {
      "href": "http://localhost:8080/people/search"
    }
  }
}
```

Theo link search:

```http
GET /people/search
Accept: application/hal+json
```

Search resource trả các link tới query method. Một query link có thể là URI template:

```json
{
  "_links": {
    "findByLastName": {
      "href": "http://localhost:8080/people/search/findByLastName{?name}",
      "templated": true
    }
  }
}
```

Client điền query parameter theo template:

```http
GET /people/search/findByLastName?name=Nguyen
Accept: application/hal+json
```

Tên query method, tham số và URI thực tế phụ thuộc repository method và annotation. Nếu method chưa được export hoặc bị ẩn bằng @RestResource(exported = false), client sẽ không có link tương ứng.

## 9. Association links và điều hướng giữa các resource

Spring Data REST có thể biểu diễn association giữa entity bằng link riêng. Ví dụ Person có Address:

```java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToOne
    private Address address;
}
```

Một item response có thể chứa:

```json
{
  "name": "An",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/1"
    },
    "address": {
      "href": "http://localhost:8080/people/1/address"
    }
  }
}
```

Client theo relation address để đọc association resource. Nếu cần thay đổi association, dùng URI và HTTP method/payload mà Spring Data REST công bố cho association endpoint. Với association to-one, API thường hỗ trợ PUT để liên kết một resource và DELETE để gỡ liên kết; association to-many có semantics và payload riêng. Hãy kiểm tra mapping và trạng thái response thực tế trước khi triển khai client.

Ví dụ cập nhật association không nên được xây dựng bằng cách tự đoán path từ ID của Person và Address. Hãy theo link relation được trả về và gửi URI của resource đích theo định dạng mà endpoint association yêu cầu.

Việc một association link xuất hiện cũng không có nghĩa client được phép truy cập hoặc sửa nó. Authorization và repository exposure vẫn quyết định thao tác nào được phép.

## 10. Pagination links và điều hướng collection

Collection lớn thường được chia thành nhiều trang. Spring Data REST dùng các link điều hướng như first, prev, self, next và last, cùng thông tin trong object page.

Ví dụ:

```json
{
  "_links": {
    "first": { "href": "http://localhost:8080/people?page=0&size=20" },
    "prev": { "href": "http://localhost:8080/people?page=1&size=20" },
    "self": { "href": "http://localhost:8080/people?page=2&size=20" },
    "next": { "href": "http://localhost:8080/people?page=3&size=20" },
    "last": { "href": "http://localhost:8080/people?page=8&size=20" }
  },
  "page": {
    "size": 20,
    "totalElements": 175,
    "totalPages": 9,
    "number": 2
  }
}
```

Các URL trong ví dụ chỉ để minh họa. Ở trang đầu, link prev có thể không xuất hiện; ở trang cuối, link next có thể không xuất hiện. Client không nên tự tăng page bằng cách ghép query string. Hãy theo next nếu link đó tồn tại, dừng khi không còn link next.

Cách này giúp client không phụ thuộc vào page size mặc định hoặc quy tắc phân trang của server. Server có thể thay đổi kích thước trang tối đa mà client vẫn điều hướng theo link được công bố.

## 11. Client điều hướng theo links thay vì hard-code URL

Một client hypermedia thường thực hiện chuỗi thao tác:

1. Gửi GET đến API root.
2. Đọc link relation cần dùng, ví dụ people.
3. Theo link đó để lấy collection.
4. Chọn một item và theo self để lấy chi tiết.
5. Theo profile nếu cần hiểu semantics hoặc schema.
6. Theo search để khám phá query methods.
7. Theo association link hoặc pagination link khi nghiệp vụ yêu cầu.

Ví dụ JavaScript tối giản:

```javascript
async function getHal(url) {
    const response = await fetch(url, {
        headers: { Accept: "application/hal+json" }
    });

    if (!response.ok) {
        throw new Error("HTTP " + response.status);
    }

    return response.json();
}

const root = await getHal("https://api.example.com/");
const peopleUrl = root._links.people.href;

const people = await getHal(peopleUrl);
const firstPerson = people._embedded.people[0];
const personUrl = firstPerson._links.self.href;

const person = await getHal(personUrl);
console.log(person);
```

Ví dụ dùng link do server trả về ở từng bước. Trong ứng dụng thực tế, cần xử lý URI template, link vắng mặt, authentication, lỗi mạng, media type và response status phù hợp.

Không được giả định link relation luôn có mặt. Một repository có thể không export search; item có thể không có association; collection trang cuối không có next. Client phải kiểm tra link trước khi sử dụng.

### Dùng Spring HATEOAS Traverson

Nếu client viết bằng Java, Spring HATEOAS cung cấp Traverson để điều hướng REST API theo relation:

```java
Traverson traverson = new Traverson(
    URI.create("https://api.example.com/"),
    MediaTypes.HAL_JSON);

ParameterizedTypeReference<CollectionModel<EntityModel<Person>>> type =
    new ParameterizedTypeReference<>() {};

CollectionModel<EntityModel<Person>> people =
    traverson
        .follow("people")
        .toObject(type);
```

Ví dụ minh họa cách đi theo relation people; kiểu trả về và cách cấu hình authentication cần điều chỉnh theo client và response thực tế.

## 12. Tạo link tùy chỉnh cho representation

Khi cần thêm link theo nghiệp vụ, có thể dùng Spring HATEOAS và các extension point của Spring Data REST. Một cách phổ biến là triển khai RepresentationModelProcessor để bổ sung link cho representation.

Ví dụ minh họa:

```java
@Component
public class PersonModelProcessor
        implements RepresentationModelProcessor<EntityModel<Person>> {

    @Override
    public EntityModel<Person> process(EntityModel<Person> model) {
        model.getContent().ifPresent(person -> {
            Link summary = Link.of(
                "/people/" + person.getId() + "/summary",
                "summary");
            model.add(summary);
        });

        return model;
    }
}
```

Đây là ví dụ khái niệm; trong ứng dụng thực tế nên dùng link builder của Spring HATEOAS để tạo URI có context path, base path và encoding chính xác, thay vì nối chuỗi. Cần bảo đảm endpoint đích thực sự tồn tại và có authorization phù hợp.

Một link tùy chỉnh nên có relation mang ý nghĩa rõ ràng. Nếu relation là loại riêng của ứng dụng, hãy mô tả nó trong profile hoặc tài liệu API để client hiểu mục đích. Không thêm link chỉ để hiển thị URL nếu client không có semantics để sử dụng.

## 13. Content negotiation giúp representation tự mô tả

Client có thể dùng header Accept để yêu cầu media type mong muốn. Server trả Content-Type cho biết representation thực tế.

Ví dụ:

```http
GET /people
Accept: application/hal+json
```

Để lấy ALPS profile:

```http
GET /profile/people
Accept: application/alps+json
```

Để lấy JSON Schema:

```http
GET /profile/people
Accept: application/schema+json
```

Các media type này không hoán đổi cho nhau. HAL JSON là representation tài nguyên; ALPS là profile ngữ nghĩa; JSON Schema mô tả cấu trúc dữ liệu. Nếu client gửi Accept không được server hỗ trợ, server có thể trả 406 Not Acceptable.

Response header cũng có thể mang thông tin quan trọng khác:

- Content-Type: định dạng representation.
- Location: URI resource vừa được tạo sau POST.
- ETag hoặc Last-Modified: validator hỗ trợ cache hoặc conditional request khi được cấu hình.
- Cache-Control: chính sách cache.

Client nên giữ lại validator và URI theo đúng resource/representation. Không suy ra version hoặc thời điểm cập nhật chỉ từ nội dung body nếu server đã cung cấp header chuyên dụng.

## 14. Self-descriptive không có nghĩa là tự động đầy đủ hoặc luôn truy cập được

Hypermedia giúp client khám phá các khả năng mà server công bố, nhưng có một số giới hạn:

**Không phải mọi relation đều có ý nghĩa chuẩn toàn cầu.** Relation chuẩn như self, next có semantics được định nghĩa rộng; relation tùy chỉnh như summary cần profile hoặc tài liệu giải thích.

**Link không đảm bảo quyền truy cập.** Server có thể trả link nhưng request vẫn cần authentication/authorization. Ngược lại, link có thể bị ẩn khỏi representation tùy cách thiết kế. Client vẫn phải xử lý 401, 403 và 404.

**Profile không phải schema validation đầy đủ.** ALPS mô tả semantics; JSON Schema mô tả shape; business rule phụ thuộc trạng thái hoặc nhiều resource vẫn cần được server thực thi.

**Embedded representation có thể rút gọn.** Client không nên giả định embedded resource tương đương với GET item resource đầy đủ.

**URL có thể thay đổi.** Đây chính là lý do client nên theo link. Tuy nhiên, client vẫn cần một entry point ổn định hoặc cấu hình ban đầu để tìm API root.

**Hypermedia không loại bỏ versioning và compatibility.** Khi semantics hoặc relation thay đổi, cần duy trì tương thích hoặc công bố thay đổi có kiểm soát. Client nên xử lý link không có mặt và relation mới mà nó chưa biết.

## 15. Lỗi thường gặp khi làm việc với profile và hypermedia links

**Client tự ghép URL từ ID**

Điều này làm client phụ thuộc vào path convention. Hãy dùng self và association links do server trả về.

**Không thấy link profile**

Kiểm tra API root và đi theo relation profile. Spring Data REST thường cung cấp một profile index tại /profile, rồi từ đó link tới profile của từng repository.

**Gửi sai Accept header**

Dùng application/hal+json cho resource HAL, application/alps+json cho ALPS và application/schema+json cho JSON Schema. Kiểm tra response Content-Type.

**Giả định mọi collection đều có search**

Chỉ query methods được export mới xuất hiện. Theo link search trước, rồi theo link query cụ thể.

**Giả định mọi item đều có association**

Association link phụ thuộc mapping, export và quyền truy cập. Kiểm tra _links của item trước khi điều hướng.

**Tự tạo link pagination bằng cách sửa page number**

Dùng link next hoặc prev do server cung cấp để không phụ thuộc page size và quy tắc phân trang.

**Không xử lý URI template**

Kiểm tra thuộc tính templated; điền biến theo chuẩn URI template và encode query value đúng cách.

**Coi profile link là endpoint dữ liệu**

Profile mô tả semantics/schema; collection và item resources mới là endpoint để đọc hoặc thay đổi dữ liệu.

## Tóm tắt

- Spring Data REST dùng HAL JSON để trả resource với _links, _embedded và thông tin page.
- API root là entry point; client đọc các relation như collection name và profile để khám phá API.
- self, search, association và pagination links cung cấp đường điều hướng theo trạng thái thực tế của server.
- Profile link dẫn tới metadata repository; dùng application/alps+json để lấy ALPS và application/schema+json để lấy JSON Schema.
- ALPS mô tả semantics/affordances; JSON Schema mô tả cấu trúc JSON; HAL biểu diễn resource và link.
- Client nên theo link do server trả về, xử lý URI template và kiểm tra relation có tồn tại trước khi sử dụng.
- Link không tự cấp quyền truy cập; authentication, authorization và validation vẫn được server thực thi.
- Representation tự mô tả cải thiện khả năng khám phá và giảm coupling URL, nhưng client vẫn cần hiểu media type và semantics của relation.

## Tài liệu tham khảo

- [Spring Data REST — Metadata](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Excerpt projections and projections](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring HATEOAS — Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [HAL — Hypertext Application Language](https://stateless.group/hal_specification.html)
- [RFC 6906 — The 'profile' Link Relation Type](https://www.rfc-editor.org/rfc/rfc6906)
- [RFC 8288 — Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
