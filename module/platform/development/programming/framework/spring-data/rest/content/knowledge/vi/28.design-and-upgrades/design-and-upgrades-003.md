# Quản lý thay đổi tên trường, path, rel và projection trong Spring Data REST

## Mục tiêu

Một API Spring Data REST có nhiều tên cùng xuất hiện trong hợp đồng HTTP nhưng phục vụ những vai trò khác nhau:

- **Tên thuộc tính Java:** tên field/getter trong entity hoặc projection.
- **Tên cột database:** tên vật lý trong schema, có thể khác tên Java.
- **Tên field JSON:** key client đọc hoặc gửi trong request body.
- **Path:** đoạn URL dùng để truy cập collection, item, association hoặc query method.
- **HAL relation (rel):** tên quan hệ trong `_links`, giúp client hiểu link dẫn tới loại tài nguyên nào.
- **Projection name:** tên client truyền trong query parameter `projection`.

Đổi một tên không nhất thiết phải đổi tất cả các tên còn lại. Nhưng nếu client đang phụ thuộc vào tên cũ, thay đổi có thể làm hỏng request hoặc khiến client không còn tìm thấy link/field mong đợi.

Bài này trình bày cách phân loại thay đổi, cách giữ tương thích trong giai đoạn chuyển tiếp, cách cấu hình path/rel/projection, chiến lược versioning và cách kiểm thử hợp đồng API trước khi loại bỏ tên cũ.

## 1. Phân biệt các loại tên trong hợp đồng API

Ví dụ entity:

~~~java
@Entity
@Table(name = "person")
public class Person {

    @Id
    private Long id;

    @Column(name = "display_name")
    private String displayName;

    private String familyName;
}
~~~

Representation JSON có thể là:

~~~json
{
  "displayName": "Lan",
  "familyName": "Nguyen"
}
~~~

Các tên ở đây có ý nghĩa khác nhau:

| Lớp | Tên ví dụ | Nơi được dùng |
| --- | --- | --- |
| Java property | `displayName` | Entity, getter, repository query derivation |
| Database column | `display_name` | Schema và SQL |
| JSON property | `displayName` | Request/response body |
| Collection path | `/people` | URL collection |
| Item path | `/people/42` | URL một entity |
| Collection rel | `people` | Key trong `_links` |
| Query method path | `by-family-name` | URL search endpoint |
| Query method rel | `byFamilyName` | Key trong search links |
| Projection name | `personSummary` | `?projection=personSummary` |

Không dùng tên Java class hoặc database column làm hợp đồng HTTP một cách vô tình. Hãy xác định tên công khai có chủ đích để thay đổi implementation bên trong ít ảnh hưởng client hơn.

## 2. Đánh giá thay đổi là additive hay breaking

Trước khi đổi tên, xác định client nào đang dùng hợp đồng hiện tại và thay đổi thuộc nhóm nào.

| Thay đổi | Rủi ro tương thích |
| --- | --- |
| Thêm field JSON tùy chọn | Thường additive, nhưng client strict schema có thể từ chối |
| Xóa hoặc đổi tên field JSON | Breaking với client đang đọc/gửi tên cũ |
| Thêm collection path mới | Additive nếu path cũ vẫn hoạt động |
| Đổi collection path | Breaking với client hardcode URL cũ |
| Đổi HAL rel | Breaking với client tìm link theo rel cũ |
| Đổi search path hoặc rel | Breaking với client gọi query resource cũ hoặc tìm rel cũ |
| Đổi projection name | Breaking với client gửi `?projection=oldName` |
| Đổi excerpt mặc định | Có thể breaking vì embedded representation thay đổi |
| Đổi kiểu dữ liệu hoặc nullability | Có thể breaking dù tên field không đổi |
| Đổi thứ tự/ý nghĩa nghiệp vụ của field | Có thể breaking về ngữ nghĩa dù JSON vẫn parse được |

Không đánh giá compatibility chỉ bằng việc endpoint vẫn trả HTTP 200. Client có thể nhận 200 nhưng không còn thấy field hoặc relation mà nó cần.

Một thay đổi được xem là an toàn hơn khi client cũ tiếp tục hoạt động trong giai đoạn chuyển tiếp và có thời gian nâng cấp rõ ràng.

## 3. Đổi tên Java property nhưng giữ nguyên database column

Giả sử code cũ dùng:

~~~java
private String name;
~~~

Code mới muốn dùng `displayName`, nhưng database vẫn giữ cột `display_name` hoặc một cột cũ đã tồn tại.

Dùng `@Column(name = ...)` để tách tên Java khỏi tên vật lý:

~~~java
@Entity
@Table(name = "person")
public class Person {

    @Id
    private Long id;

    @Column(name = "name")
    private String displayName;
}
~~~

Entity có thể đổi tên property Java thành `displayName` mà không cần đổi tên cột database. Repository query derivation, getter, projection và JSON mapping có thể cần cập nhật theo Java property mới.

Điều này không tự giữ nguyên JSON field cũ. Nếu client đang gửi `name` và response đang trả `name`, cần cấu hình JSON compatibility riêng.

Tách schema migration khỏi API migration giúp tránh phải thay đổi database column và client contract trong cùng một lần phát hành.

## 4. Giữ tên JSON ổn định bằng @JsonProperty

Nếu muốn đổi tên Java property nhưng giữ tên JSON công khai, có thể dùng Jackson `@JsonProperty`:

~~~java
@Entity
public class Person {

    @Id
    private Long id;

    @JsonProperty("name")
    private String displayName;
}
~~~

Khi serialize, property có thể tiếp tục xuất hiện dưới key `name`, dù tên Java là `displayName`.

Đây là cách hữu ích khi muốn refactor code nội bộ mà không đổi API contract. Cần kiểm tra annotation được đặt trên field/getter nào và Jackson visibility của entity trong cấu hình Spring Data REST.

Nếu muốn đổi JSON name từ `name` sang `displayName`, chỉ thay `@JsonProperty` thành tên mới sẽ làm client cũ mất field. Khi đó cần chiến lược chuyển tiếp.

## 5. Nhận tên JSON cũ bằng @JsonAlias

Jackson `@JsonAlias` cho phép deserializer chấp nhận thêm tên cũ khi đọc request:

~~~java
@Entity
public class Person {

    @Id
    private Long id;

    @JsonProperty("displayName")
    @JsonAlias("name")
    private String displayName;
}
~~~

Ý nghĩa:

- Response serialization dùng tên chính `displayName`.
- Request deserialization có thể chấp nhận cả `displayName` và alias `name`.
- `@JsonAlias` không làm response xuất đồng thời cả hai key.

Ví dụ client cũ gửi:

~~~json
{
  "name": "Lan"
}
~~~

và client mới gửi:

~~~json
{
  "displayName": "Lan"
}
~~~

Cả hai có thể được bind vào cùng property nếu cấu hình Jackson và Spring Data REST đang dùng annotation đó.

**Giới hạn quan trọng:** alias chỉ hỗ trợ đọc input. Nếu client cũ cần response vẫn có key `name`, `@JsonAlias` không đáp ứng yêu cầu đó. Muốn trả cả tên cũ và mới trong giai đoạn chuyển tiếp, cần representation/DTO hoặc custom serializer được thiết kế rõ ràng; tránh tạo hai property Java cùng ghi vào một field gây xung đột.

Với thao tác PUT, PATCH và JSON Merge Patch, cần kiểm thử cả hai key và hành vi khi payload gửi đồng thời tên cũ lẫn tên mới. Không để hai giá trị khác nhau ghi vào cùng một property mà không có quy tắc ưu tiên rõ ràng.

## 6. Đổi collection path bằng @RepositoryRestResource

Spring Data REST cho phép tùy chỉnh path của repository:

~~~java
@RepositoryRestResource(path = "persons")
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Collection resource có path `/persons`; item resource có dạng `/persons/{id}`.

Nếu trước đây path là `/people`, đổi thành `/persons` sẽ làm các URL cũ không còn hoạt động nếu không có route tương thích.

Phân biệt path với relation:

~~~java
@RepositoryRestResource(
    path = "persons",
    collectionResourceRel = "people"
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Ở đây:

- `path = "persons"`: URL path dùng để gọi collection.
- `collectionResourceRel = "people"`: relation name dùng trong HAL link tới collection.

Hai giá trị có thể khác nhau. Client HATEOAS nên tìm relation phù hợp rồi theo `href`, thay vì ghép path từ relation name.

Đổi path không tự đổi tên entity, database table hoặc Java repository. Nó chỉ thay đổi URI mapping do exporter công bố.

## 7. Giữ path cũ trong giai đoạn chuyển tiếp

Nếu nhiều client đang gọi path cũ, không nên xóa path ngay khi phát hành path mới.

Một lộ trình có thể là:

1. Công bố path mới.
2. Duy trì path cũ bằng route tương thích hoặc gateway rewrite.
3. Ghi nhận request tới path cũ để biết còn client nào sử dụng.
4. Thông báo thời điểm ngừng hỗ trợ.
5. Chuyển client sang link mới do HAL cung cấp.
6. Chỉ loại bỏ path cũ sau khi hết thời gian hỗ trợ và đã xác nhận traffic cũ giảm về mức chấp nhận được.

Với GET, redirect có thể là một cách chuyển hướng nếu client xử lý redirect và response hypermedia phù hợp. Với PUT/PATCH/DELETE hoặc request có body, phải chọn redirect status bảo toàn method/body (ví dụ 307 hoặc 308) và kiểm tra hành vi của client, proxy và authentication. Không dùng 301/302 một cách máy móc cho request ghi vì một số client có thể đổi method thành GET.

Một lựa chọn khác là API gateway rewrite path cũ sang path mới. Khi dùng gateway, kiểm tra cả:

- Request path được rewrite.
- `Location` header khi POST tạo resource.
- HAL `self`, `next`, `prev` và association href.
- ETag/Last-Modified và cache key.
- Authentication, CORS và logging.

Nếu gateway chỉ rewrite request nhưng response vẫn phát link path mới, client cũ có thể vẫn hoạt động nếu theo link; client hardcode path cũ cần được cập nhật.

## 8. Đổi collection rel mà không đổi path

HAL relation mô tả ý nghĩa của link, còn path là địa chỉ truy cập.

Ví dụ:

~~~java
@RepositoryRestResource(
    path = "persons",
    collectionResourceRel = "people"
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

HAL root có thể chứa:

~~~json
{
  "_links": {
    "people": {
      "href": "https://api.example.com/api/persons"
    }
  }
}
~~~

Nếu đổi `collectionResourceRel` từ `people` thành `persons`, URL có thể vẫn giữ nguyên nhưng client tìm key `people` sẽ không còn thấy link theo tên cũ.

Hypermedia giúp giảm phụ thuộc vào URL, nhưng client vẫn phải biết relation name mà nó cần. Vì vậy, đổi rel cũng là một thay đổi contract nếu client đang dùng rel cũ.

Spring Data REST chỉ có một giá trị `collectionResourceRel` trên annotation repository. Không thể giả định rằng khai báo hai tên trong cùng thuộc tính sẽ tạo hai alias relation. Nếu cần duy trì rel cũ, có thể bổ sung compatibility link qua custom representation/processor hoặc custom controller, rồi kiểm thử link thực tế trong HAL response.

Giữ relation ổn định thường là lựa chọn tốt khi chỉ cần đổi URL path. Nếu không có lý do nghiệp vụ để đổi rel, giữ rel cũ sẽ giảm số client cần thay đổi.

## 9. Đổi path và rel của query method

Query methods được công bố bằng `@RestResource`. Ví dụ:

~~~java
@RestResource(
    path = "by-family-name",
    rel = "byFamilyName"
)
List<Person> findByFamilyNameIgnoreCase(
        @Param("familyName") String familyName);
~~~

Ba tên cần phân biệt:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Java method | `findByFamilyNameIgnoreCase` | Tên method repository |
| Search path | `by-family-name` | URL của query endpoint |
| Search rel | `byFamilyName` | Key trong search resource `_links` |

Nếu muốn đổi URL nhưng giữ rel, chỉ thay `path`. Nếu muốn đổi rel nhưng giữ URL, chỉ thay `rel`. Đừng đổi cả hai cùng lúc nếu chưa có lý do và kế hoạch chuyển client.

Ví dụ giữ path cũ nhưng đổi tên method Java:

~~~java
@RestResource(
    path = "by-last-name",
    rel = "byFamilyName"
)
List<Person> findByFamilyNameIgnoreCase(
        @Param("familyName") String familyName);
~~~

Client tiếp tục gọi path cũ; search resource công bố relation mới. Nếu client tìm link bằng rel cũ, cần giai đoạn alias relation.

Cũng cần kiểm tra tên query parameter nghiệp vụ như `familyName`. Đổi tên tham số Java hoặc `@Param` có thể làm URL query thay đổi; đây là một phần khác của contract so với path/rel.

## 10. Đổi projection name

Projection được công bố bằng `@Projection(name = ...)`:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getDisplayName();

    String getFamilyName();
}
~~~

Client lựa chọn projection bằng:

~~~http
GET /api/persons/42?projection=personSummary
Accept: application/hal+json
~~~

Nếu đổi tên thành `personCard`, client gửi `projection=personSummary` có thể không còn hoạt động nếu projection cũ bị xóa hoặc không được phát hiện.

Có thể giữ tên cũ như một alias bằng cách duy trì projection interface cũ và thêm interface mới:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getDisplayName();

    String getFamilyName();
}
~~~

~~~java
@Projection(name = "personCard", types = Person.class)
public interface PersonCard {

    String getDisplayName();

    String getFamilyName();
}
~~~

Hai projection có thể cung cấp cùng tập field nhưng dùng hai public names khác nhau. Cả hai phải được Spring Data REST phát hiện hoặc đăng ký.

Không chỉ đổi tên interface Java rồi giả định client vẫn dùng được. Public identifier là giá trị trong `@Projection(name = "...")`, không nhất thiết là tên class.

## 11. Thay đổi excerptProjection là thay đổi representation mặc định

Repository có thể cấu hình excerpt:

~~~java
@RepositoryRestResource(
    path = "persons",
    excerptProjection = PersonSummary.class
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Excerpt được áp dụng khi item được nhúng trong collection hoặc related resources. Nếu thay excerpt từ PersonSummary sang PersonDetails, embedded item có thể có thêm field, nested association hoặc payload lớn hơn.

Nếu client dựa vào một field cũ trong collection response, việc thay excerpt có thể phá vỡ client dù item endpoint vẫn trả representation đầy đủ.

Trước khi đổi excerpt:

- So sánh JSON/HAL của collection trước và sau.
- Xác nhận field cũ vẫn tồn tại nếu client cần.
- Kiểm tra nested projection có mở thêm association hay dữ liệu nhạy cảm không.
- Đo payload và query count vì excerpt mới có thể làm tăng lazy loading.
- Cân nhắc giữ projection cũ cho client lựa chọn tường minh.
- Thông báo rõ thay đổi nếu embedded contract không còn tương thích.

Excerpt là cấu hình mặc định cho embedded representation; nó không phải alias của projection name và không tự động áp dụng cho item resource đơn.

## 12. Đổi tên field có ảnh hưởng tới query method và projection

Khi đổi Java property từ `lastName` sang `familyName`, các nơi sau có thể cần thay đổi:

- Derived query: `findByLastName` thành `findByFamilyName`.
- Sort: `sort=lastName,asc` thành `sort=familyName,asc`.
- Projection getter: `getLastName()` thành `getFamilyName()`.
- JSON property nếu không có mapping ổn định bằng `@JsonProperty`.
- Validation, specification, Querydsl binding và custom mapper.
- Test, documentation và client-generated code.

Tên JSON và tên query property không nhất thiết giống nhau. Ví dụ JSON có thể giữ `family_name`, trong khi repository property vẫn là `familyName`. Nhưng Spring Data REST sort/search thường dựa trên domain property path theo quy tắc của framework; không mặc định rằng tên JSON đã đổi sẽ tự đổi tên query parameter.

Nếu cần giữ URL query cũ trong thời gian chuyển tiếp, có thể giữ query method cũ hoặc tạo method alias với `@RestResource(path = "...", rel = "...")` khác nhau, cùng gọi một service/query implementation. Tránh duy trì hai logic truy vấn độc lập có kết quả khác nhau.

## 13. Versioning khi thay đổi không thể giữ tương thích

Nếu thay đổi thực sự breaking, hãy cân nhắc versioning thay vì âm thầm đổi contract đang được sử dụng.

Ví dụ:

~~~text
/api/v1/persons
/api/v2/persons
~~~

Một cách phổ biến là đặt Spring Data REST base path theo version:

~~~properties
spring.data.rest.base-path=/api/v1
~~~

Tuy nhiên, `spring.data.rest.base-path` là cấu hình của exporter trong một ApplicationContext. Không nên giả định rằng chỉ cần khai báo hai giá trị base path trong cùng một `RepositoryRestConfiguration` là một ứng dụng sẽ tự export đồng thời hai phiên bản repository resources độc lập.

Nếu cần chạy v1 và v2 song song, các lựa chọn kiến trúc có thể gồm:

- Hai deployment/application context với cấu hình base path khác nhau.
- API gateway định tuyến version tới deployment tương ứng.
- Custom controllers/DTO cho phiên bản mới trong khi repository exporter cũ tiếp tục phục vụ v1.
- Một API façade riêng kiểm soát representation và mapping cho từng version.

Chọn cách triển khai phù hợp với mức độ khác nhau giữa hai contract và khả năng vận hành. Không tạo hai repository exporter cùng thao tác một entity trong cùng context nếu chưa xác định rõ mapping, handler order và transaction behavior.

Versioning theo media type hoặc header cũng có thể được thiết kế ở tầng API, nhưng Spring Data REST không tự biến một repository thành nhiều representation version độc lập chỉ bằng cách thêm header tùy ý. Cần cấu hình content negotiation/controller rõ ràng và test thực tế.

## 14. Quy trình expand-and-contract

Một chiến lược an toàn là mở rộng contract trước, chuyển client, rồi mới loại bỏ tên cũ.

### Giai đoạn 1: Expand

- Thêm field hoặc projection mới.
- Thêm route/query method mới nếu cần.
- Giữ path, rel, projection và field cũ.
- Nếu đổi input name, chấp nhận cả tên cũ và mới bằng alias hoặc endpoint tương thích.
- Cập nhật tài liệu và link discovery.

### Giai đoạn 2: Migrate clients

- Chuyển client sang field, path, rel và projection mới.
- Ưu tiên theo HAL `href` thay vì hardcode URL.
- Theo dõi traffic trên endpoint/parameter cũ.
- Thêm cảnh báo deprecation khi phù hợp.
- Kiểm thử các phiên bản client đang được hỗ trợ.

### Giai đoạn 3: Contract

- Xác nhận client cũ đã chuyển hoặc hết thời hạn hỗ trợ.
- Gỡ alias field, projection, path hoặc rel cũ.
- Cập nhật contract tests và tài liệu.
- Theo dõi lỗi 404, 400 và request có tên cũ sau khi phát hành.

Không xóa tên cũ chỉ vì client mới đã chạy được trong môi trường test. Hãy dựa vào telemetry và chính sách hỗ trợ client thực tế.

## 15. Thông báo deprecation và thời điểm ngừng hỗ trợ

Khi một path hoặc representation cũ sẽ bị loại bỏ, cần thông báo cho client đủ sớm.

Có thể sử dụng các HTTP response headers theo chính sách API:

~~~http
Deprecation: @1798761600
Sunset: Wed, 01 Dec 2027 00:00:00 GMT
Link: <https://docs.example.com/migrations/persons-v2>; rel="deprecation"
~~~

Ví dụ trên chỉ minh họa định dạng; thời điểm phải được thay bằng lịch phát hành thực tế. Header `Deprecation` được định nghĩa trong RFC 9745; `Sunset` trong RFC 8594. Client không phải lúc nào cũng tự hành động theo các header này, nên vẫn cần tài liệu migration và thông báo trực tiếp cho các nhóm tích hợp.

Có thể ghi metric/log số request tới route cũ, nhưng không gắn raw user data hoặc token vào log. Dùng route name hoặc low-cardinality tag để theo dõi.

## 16. Kiểm thử contract cho field, path, rel và projection

Contract test cần kiểm tra các khía cạnh khác nhau.

### Kiểm tra collection path và rel

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rootPublishesPeopleCollectionRelation() throws Exception {
        mockMvc.perform(get("/api")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.people.href")
                    .value(containsString("/api/persons")));
    }
}
~~~

Test xác nhận relation `people` trỏ tới path `/api/persons`. Nếu đổi một trong hai, cập nhật assertion theo contract dự kiến.

### Kiểm tra JSON property

~~~java
@Test
void personRepresentationUsesStableJsonPropertyName()
        throws Exception {

    mockMvc.perform(get("/api/persons/{id}", 42)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.displayName").exists())
        .andExpect(jsonPath("$.name").doesNotExist());
}
~~~

### Kiểm tra projection name

~~~java
@Test
void newProjectionNameIsAvailable() throws Exception {
    mockMvc.perform(get("/api/persons/{id}", 42)
            .param("projection", "personCard")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.displayName").exists());
}
~~~

### Kiểm tra search rel/path

~~~java
@Test
void searchResourcePublishesNewFinderRelation() throws Exception {
    mockMvc.perform(get("/api/persons/search")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.byFamilyName.href").exists());
}
~~~

Ngoài các test mới, giữ test tương thích cho tên cũ trong giai đoạn migration:

- Path cũ còn được phục vụ hoặc redirect đúng.
- Rel cũ còn được công bố nếu contract yêu cầu alias.
- Projection cũ vẫn được chọn.
- Request body dùng JSON alias cũ vẫn bind đúng.
- Response không vô tình trả field nhạy cảm.
- ETag, Location, association links và paging links dùng path mới đúng cách.

## 17. Kiểm tra ALPS và link discovery sau khi đổi contract

Spring Data REST cung cấp profile/ALPS metadata qua link `profile`. Metadata có thể mô tả domain properties, search descriptors và projection descriptors.

Sau khi đổi field, search path/rel hoặc projection name:

1. Gọi API root và kiểm tra link `profile`.
2. Theo profile link của domain resource.
3. Kiểm tra descriptor field và projection name.
4. Gọi search resource và kiểm tra relation của query method.
5. Gọi collection/item và kiểm tra `self`, association và paging links.
6. So sánh metadata với tài liệu client đang sử dụng.

ALPS giúp khám phá metadata nhưng không thay thế OpenAPI/contract documentation nếu ứng dụng cần mô tả đầy đủ request schema, response schema, authorization và error semantics.

## 18. Cache, ETag và URL sau khi đổi path

Đổi path hoặc query parameter có thể tạo một request URI mới. HTTP cache key tối thiểu dựa trên method và target URI; vì vậy response của path cũ và path mới không tự động là cùng cache entry.

Sau khi migration:

- Không chuyển ETag từ path cũ sang path mới nếu server không xác nhận chúng là cùng validator.
- Invalidate cache entries của path/rel/query cũ khi dữ liệu hoặc representation thay đổi.
- Kiểm tra `Location`, `self`, `next`, `prev` và association href.
- Kiểm tra gateway rewrite có làm thay đổi URI được dùng trong cache hay không.
- Kiểm tra canonical URL và redirect để tránh cache trùng hoặc vòng lặp.

Một path mới có thể trả cùng entity nhưng không có nghĩa ETag cũ có thể dùng cho URI mới. Hãy để server phát validator cho đúng resource URI.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Java property đổi nhưng database query lỗi | Derived query hoặc mapping vẫn dùng tên cũ | Cập nhật method/property path và giữ column bằng @Column nếu cần |
| JSON response mất field cũ | @JsonProperty đã đổi tên mà không có compatibility plan | Dùng alias input hoặc DTO/custom representation để duy trì output cũ |
| @JsonAlias không giữ field cũ trong response | Alias chỉ tác động deserialization | Dùng DTO/serializer nếu cần trả cả hai key |
| Collection URL đổi nhưng client không tìm thấy link | Path và rel bị nhầm là một | Kiểm tra riêng path và collectionResourceRel |
| Client HATEOAS lỗi sau khi đổi rel | Client tìm relation theo tên cũ | Giữ rel hoặc phát compatibility link trong thời gian chuyển tiếp |
| Search endpoint không còn hoạt động | @RestResource path hoặc rel đã đổi | Duy trì finder alias và kiểm tra search resource |
| Projection cũ không được chọn | @Projection(name) đã đổi hoặc interface cũ bị xóa | Giữ projection alias cho client cũ |
| Collection embedded thay đổi field | excerptProjection đã đổi | Kiểm tra excerpt contract và version/migration |
| Gateway rewrite nhưng Location vẫn sai | Response link được tạo từ URI/mapping khác | Kiểm tra forwarded headers, base path và response links |
| Version v1/v2 không cùng tồn tại như dự kiến | Một RepositoryRestConfiguration chỉ có một base path | Tách deployment/context hoặc dùng custom API façade |
| ETag cũ bị gửi sang URL mới | Cache/validator chỉ lưu theo entity ID | Lưu validator theo URI/representation key |
| Client cũ lỗi dù endpoint vẫn 200 | Field hoặc relation quan trọng đã biến mất | Contract test theo field/rel/projection, không chỉ status |

## 20. Quy trình quản lý thay đổi

1. Liệt kê field JSON, path, rel, search path và projection name hiện tại.
2. Xác định client nào sử dụng từng tên và cách client tìm resource.
3. Phân loại thay đổi additive hay breaking.
4. Tách đổi tên Java/database khỏi đổi tên JSON.
5. Nếu đổi field JSON, xác định chính sách response và request alias riêng.
6. Nếu đổi path, giữ route cũ hoặc cung cấp redirect/gateway mapping phù hợp.
7. Nếu đổi rel, duy trì compatibility link hoặc giữ relation cũ trong thời gian chuyển tiếp.
8. Nếu đổi projection, giữ projection name cũ cho client đang dùng.
9. Nếu đổi excerpt, so sánh embedded representation và payload.
10. Cân nhắc API version mới khi không thể giữ tương thích.
11. Cập nhật HAL/ALPS, documentation và contract tests.
12. Theo dõi traffic cũ trước khi loại bỏ alias.
13. Sau migration, kiểm tra cache, ETag, Location và association links.

## Tài liệu tham khảo

- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): tùy chỉnh repository path, collection relation và resource mapping.
- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): projection name, excerpt projection và representation của embedded resources.
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection, item, search resources và HAL links.
- [Spring Data REST — ALPS metadata](https://docs.spring.io/spring-data/rest/reference/alps.html): profile descriptors, properties, search resources và projection metadata.
- [Jackson — JsonProperty](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.html) và [JsonAlias](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonAlias.html): tên JSON công khai và alias khi deserialize.
- [RFC 9745 — The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745.html): thông báo deprecation cho API clients.
- [RFC 8594 — The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594.html): thông báo thời điểm resource dự kiến ngừng hỗ trợ.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): redirect semantics, Location và method-preserving redirects.
