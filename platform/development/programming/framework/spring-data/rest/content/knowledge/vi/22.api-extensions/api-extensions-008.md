# Tạo liên kết repository bằng RepositoryEntityLinks trong Spring Data REST

## Mục tiêu

Khi viết custom controller hoặc bổ sung hypermedia link vào response, ứng dụng thường cần tạo URL trỏ tới collection, item, trang phân trang hoặc search resource do Spring Data REST export.

Có thể tự ghép chuỗi như `/api/people/42`, nhưng cách đó dễ sai khi repository đổi path, collection relation, base path, tên tham số paging hoặc cách chuyển đổi identifier. Spring Data REST cung cấp `RepositoryEntityLinks` để tạo link dựa trên metadata repository đã được export.

Các trường hợp thường dùng:

- Tạo link tới collection resource của một domain type.
- Tạo link tới item resource bằng identifier.
- Tạo link tới collection có Pageable.
- Lấy tất cả search links của repository.
- Tạo link tới một query method cụ thể bằng relation.
- Bổ sung các link này vào `EntityModel` hoặc `CollectionModel` của Spring HATEOAS.

Bài này trình bày API của `RepositoryEntityLinks`, cách inject bean, cách dùng các overload cho paging/sorting, cách kết hợp với HAL và custom controller, cùng những giới hạn cần lưu ý.

## 1. Vì sao không nên tự ghép URL?

Giả sử repository được khai báo:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Với base path `/api`, collection resource có thể là:

~~~text
/api/people
~~~

Item có ID 42 có thể là:

~~~text
/api/people/42
~~~

Nếu sau này nhóm phát triển thay đổi:

- Base path từ `/api` thành `/v1`.
- Collection path từ `people` thành `persons`.
- Collection relation bằng `collectionResourceRel`.
- Tên tham số phân trang hoặc sort.
- Cách biểu diễn backend identifier bằng converter.

Các chuỗi URL hardcode trong custom controller có thể không còn khớp với tài nguyên mà exporter tạo ra.

Ví dụ cách ghép URL dễ lỗi:

~~~java
String href = "/api/people/" + person.getId();
~~~

Đoạn code này đang giả định base path, collection path và định dạng identifier. Nó không đọc metadata repository từ Spring Data REST.

`RepositoryEntityLinks` được thiết kế để tạo link tới các resource đã export. Nó dùng cấu hình và resource mappings của Spring Data REST để xây dựng link, nhờ đó custom code không phải tự lặp lại quy tắc URL của exporter.

## 2. RepositoryEntityLinks là gì?

`RepositoryEntityLinks` nằm trong package:

~~~java
import org.springframework.data.rest.webmvc.support.RepositoryEntityLinks;
~~~

Đây là implementation của Spring Data HATEOAS `EntityLinks`, chuyên tạo link cho domain type được quản lý bởi Spring Data REST.

Javadoc mô tả nó có khả năng tạo `Link` cho domain classes do Spring Data REST quản lý. API hiện tại có các nhóm phương thức chính:

| Phương thức | Kết quả | Mục đích |
| --- | --- | --- |
| `linkToCollectionResource(type)` | `Link` | Link tới collection resource |
| `linkToItemResource(type, id)` | `Link` | Link tới một item resource |
| `linkToPagedResource(type, pageable)` | `Link` | Link tới collection có thông tin phân trang |
| `linksToSearchResources(type)` | `Links` | Tất cả link tới search resources được export |
| `linksToSearchResources(type, pageable)` | `Links` | Search links có thể được mở rộng theo Pageable |
| `linksToSearchResources(type, sort)` | `Links` | Search links có thể được mở rộng theo Sort |
| `linkToSearchResource(type, relation)` | `Link` hoặc null | Link tới query method theo relation |
| `linkToSearchResource(type, relation, pageable)` | `Link` hoặc null | Search link có Pageable |
| `linkToSearchResource(type, relation, sort)` | `Link` | Search link có Sort |
| `linkFor(type)` | `LinkBuilder` | API cấp thấp để tùy chỉnh thêm đường dẫn |

Các phương thức tạo link typed như collection, item, page và search nên được ưu tiên. Chỉ dùng `linkFor(...)` khi cần xây dựng một đường dẫn tùy biến mà API chuyên biệt chưa đáp ứng.

## 3. Inject RepositoryEntityLinks bằng constructor

Spring Data REST đăng ký `RepositoryEntityLinks` trong ApplicationContext. Có thể inject bean này vào custom controller hoặc service:

~~~java
@RepositoryRestController
public class PersonNavigationController {

    private final RepositoryEntityLinks entityLinks;

    public PersonNavigationController(RepositoryEntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }
}
~~~

Hoặc inject vào một component xử lý representation:

~~~java
@Component
public class PersonLinkFactory {

    private final RepositoryEntityLinks entityLinks;

    public PersonLinkFactory(RepositoryEntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }
}
~~~

Constructor injection giúp thể hiện dependency rõ ràng và dễ thay thế bằng mock trong unit test.

Không cần tự khởi tạo `new RepositoryEntityLinks(...)`. Constructor của implementation cần nhiều thành phần nội bộ như repository metadata, resource mappings, REST configuration, paging template variables và backend ID converters. Hãy dùng bean do Spring Data REST cung cấp.

Nếu Spring không tìm thấy bean, kiểm tra dependency và auto-configuration Spring Data REST đang được nạp. Không tạo một instance thủ công với cấu hình thiếu vì link có thể không phản ánh đúng resource mappings của ứng dụng.

## 4. Tạo link tới collection resource

Dùng `linkToCollectionResource` khi cần URL của collection cho một domain type:

~~~java
Link peopleLink =
        entityLinks.linkToCollectionResource(Person.class);
~~~

Ví dụ trả link trong một response:

~~~java
@GetMapping("/navigation/people")
ResponseEntity<EntityModel<Map<String, String>>> peopleNavigation() {

    Link people = entityLinks
            .linkToCollectionResource(Person.class)
            .withRel("people");

    EntityModel<Map<String, String>> model =
            EntityModel.of(Map.of("description", "Danh sách người dùng"), people);

    return ResponseEntity.ok(model);
}
~~~

Trong ví dụ này:

- `Person.class` xác định domain type.
- Spring Data REST tìm repository/resource mapping tương ứng.
- Link được tạo theo collection path đã export.
- `withRel("people")` gắn relation phù hợp với response custom đang xây dựng.

Nếu repository đổi path bằng `@RepositoryRestResource(path = "persons")`, code vẫn yêu cầu link cho `Person.class`; không phải sửa chuỗi URL trong controller.

Lưu ý: `RepositoryEntityLinks` chỉ hỗ trợ domain type có repository resource tương ứng được Spring Data REST quản lý. Một class DTO bất kỳ không tự trở thành repository resource chỉ vì truyền class đó vào method.

## 5. Tạo link tới item resource

Dùng `linkToItemResource` để tạo link tới một item:

~~~java
Link personLink =
        entityLinks.linkToItemResource(Person.class, 42L);
~~~

Trong custom controller, có thể dùng ID lấy từ entity:

~~~java
@GetMapping("/people/{id}/navigation")
ResponseEntity<EntityModel<PersonNavigation>> navigation(
        @PathVariable Long id) {

    Person person = personRepository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND));

    Link itemLink = entityLinks
            .linkToItemResource(Person.class, person.getId());

    Link collectionLink = entityLinks
            .linkToCollectionResource(Person.class)
            .withRel("people");

    EntityModel<PersonNavigation> model =
            EntityModel.of(
                    new PersonNavigation(person.getId(), person.getDisplayName()),
                    itemLink,
                    collectionLink);

    return ResponseEntity.ok(model);
}
~~~

Record response:

~~~java
public record PersonNavigation(Long id, String displayName) {
}
~~~

`linkToItemResource` nhận domain type và identifier. Identifier phải là giá trị phù hợp với repository/backend ID mapping của domain type đó. Để Spring Data REST và backend converter xử lý URL encoding/identifier mapping; không tự encode ID thành chuỗi URL trước khi truyền vào.

Đừng nhầm việc tạo link với việc tải entity. `linkToItemResource` tạo URI từ metadata và ID; nó không thay thế `findById`, không xác nhận entity đang tồn tại và không kiểm tra quyền truy cập của người dùng.

Nếu cần bảo đảm resource tồn tại, hãy thực hiện repository lookup và authorization trước khi đưa link vào response.

## 6. Tạo link tới collection có phân trang

Khi muốn tạo link cho collection với một `Pageable` cụ thể, dùng `linkToPagedResource`:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "lastName"));

Link firstPage = entityLinks
        .linkToPagedResource(Person.class, pageable);
~~~

Import:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
~~~

Phương thức nhận `Pageable` có thể mở rộng các template variables paging/sorting theo giá trị được truyền vào. Nếu không có Pageable, có thể truyền `null` để tạo link collection dạng phân trang chưa được mở rộng.

Ví dụ tạo link tới trang thứ hai:

~~~java
Pageable secondPage = PageRequest.of(
        1,
        20,
        Sort.by("lastName").ascending());

Link pageLink = entityLinks
        .linkToPagedResource(Person.class, secondPage);
~~~

Số trang bắt đầu từ 0, vì vậy `PageRequest.of(1, 20)` là trang thứ hai.

Tên query parameter được dùng trong link tuân theo cấu hình paging của Spring Data REST. Nếu ứng dụng đổi `page`, `size`, `sort` thành tên khác trong `RepositoryRestConfiguration`, hãy để `RepositoryEntityLinks` tạo link thay vì tự ghép query string.

Một link trang chỉ mô tả URL; nó không thực thi truy vấn. Muốn lấy dữ liệu, vẫn cần gọi repository hoặc theo link đó qua HTTP.

## 7. Lấy tất cả search links của repository

Nếu repository export nhiều query methods, có thể lấy toàn bộ search links:

~~~java
Links searchLinks =
        entityLinks.linksToSearchResources(Person.class);
~~~

Ví dụ repository:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    List<Person> findByLastNameIgnoreCase(
            @Param("lastName") String lastName);

    @RestResource(path = "active", rel = "activePeople")
    Page<Person> findByActiveTrue(Pageable pageable);
}
~~~

Search resource của repository sẽ công bố các finder links theo mapping đã cấu hình. `linksToSearchResources` trả về tập hợp `Links`, có thể thêm trực tiếp vào một representation:

~~~java
CollectionModel<EntityModel<Person>> model =
        CollectionModel.of(personModels);

for (Link searchLink :
        entityLinks.linksToSearchResources(Person.class)) {
    model.add(searchLink);
}
~~~

Không phải mọi repository đều có search resource. Nếu không có query method được export, tập hợp link có thể rỗng. Việc method có trong Java interface cũng chưa đủ; method phải được Spring Data REST phát hiện và export, không bị ẩn bằng `@RestResource(exported = false)`.

## 8. Tạo link tới một query method cụ thể

Nếu chỉ cần một finder link, dùng `linkToSearchResource` với domain type và relation:

~~~java
Link byLastName = entityLinks.linkToSearchResource(
        Person.class,
        LinkRelation.of("byLastName"));
~~~

Import:

~~~java
import org.springframework.hateoas.LinkRelation;
~~~

Relation phải khớp với relation được export cho query method:

~~~java
@RestResource(
    path = "by-last-name",
    rel = "byLastName"
)
List<Person> findByLastNameIgnoreCase(
        @Param("lastName") String lastName);
~~~

Có ba tên khác nhau cần phân biệt:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Java method | `findByLastNameIgnoreCase` | Tên method trong repository |
| Search path | `by-last-name` | Đoạn path của query endpoint |
| Relation | `byLastName` | Tên relation xuất hiện trong HAL |

API hiện tại nhận `LinkRelation`, vì vậy có thể tạo bằng `LinkRelation.of("byLastName")`. Không truyền nhầm path `by-last-name` hoặc tên Java method nếu relation đã được tùy chỉnh thành giá trị khác.

Phương thức `linkToSearchResource` có thể trả `null` nếu không có search link tương ứng. Hãy xử lý trường hợp này:

~~~java
Link searchLink = entityLinks.linkToSearchResource(
        Person.class,
        LinkRelation.of("byLastName"));

if (searchLink != null) {
    model.add(searchLink);
}
~~~

Không dereference ngay kết quả mà không kiểm tra null, đặc biệt khi repository có thể thay đổi cấu hình export theo profile hoặc module.

## 9. Tạo search link có Pageable hoặc Sort

Các overload của search link hỗ trợ paging và sorting:

~~~java
Pageable pageable = PageRequest.of(
        0,
        25,
        Sort.by("lastName").ascending());

Link searchPage = entityLinks.linkToSearchResource(
        Person.class,
        LinkRelation.of("activePeople"),
        pageable);
~~~

Hoặc chỉ truyền Sort:

~~~java
Link sortedSearch = entityLinks.linkToSearchResource(
        Person.class,
        LinkRelation.of("byLastName"),
        Sort.by(Sort.Direction.DESC, "createdAt"));
~~~

Nếu muốn lấy tất cả search links đã mở rộng theo Pageable:

~~~java
Links expandedSearchLinks =
        entityLinks.linksToSearchResources(Person.class, pageable);
~~~

Hoặc theo Sort:

~~~java
Links sortedSearchLinks =
        entityLinks.linksToSearchResources(
                Person.class,
                Sort.by("lastName").ascending());
~~~

Việc mở rộng template giúp link mang các giá trị paging/sorting đã cung cấp. Các tham số nghiệp vụ của query method, ví dụ `lastName`, vẫn có thể cần được truyền khi client gọi endpoint. Không giả định rằng truyền Pageable sẽ tự điền mọi tham số nghiệp vụ của finder.

Khi query method có tham số Pageable, server sẽ dùng tên page/size/sort theo cấu hình Spring Data REST hiện tại. Hãy đọc link được trả về để biết URI template và các biến còn cần cung cấp.

## 10. Kết hợp RepositoryEntityLinks với Spring HATEOAS models

Spring HATEOAS cung cấp các model để biểu diễn resource và collection có link:

- `EntityModel<T>`: một nội dung/resource cùng các link.
- `CollectionModel<T>`: một tập hợp resource cùng các link.
- `RepresentationModel<T>`: base type cho representation có hypermedia.

Ví dụ tạo item representation:

~~~java
Person person = personRepository.findById(id).orElseThrow();

EntityModel<Person> model = EntityModel.of(
        person,
        entityLinks.linkToItemResource(Person.class, person.getId()),
        entityLinks.linkToCollectionResource(Person.class)
                .withRel("people"));
~~~

Ví dụ tạo collection representation:

~~~java
List<EntityModel<Person>> people = personRepository.findAll()
        .stream()
        .map(person -> EntityModel.of(
                person,
                entityLinks.linkToItemResource(Person.class, person.getId())))
        .toList();

CollectionModel<EntityModel<Person>> model =
        CollectionModel.of(
                people,
                entityLinks.linkToCollectionResource(Person.class));

for (Link link : entityLinks.linksToSearchResources(Person.class)) {
    model.add(link);
}
~~~

Trong ví dụ:

- Mỗi Person có link tới item resource của chính nó.
- CollectionModel có link collection.
- Các search links được bổ sung để client khám phá query endpoints.

Nếu collection có dữ liệu lớn, không nên gọi `findAll()` để tạo danh sách thủ công. Hãy dùng repository paging hoặc một phương thức query có Pageable, rồi xây representation phù hợp với Page/Slice. `RepositoryEntityLinks` tạo link; nó không tự tối ưu truy vấn hoặc chuyển collection thành trang.

## 11. Kết hợp với custom controller

Một custom controller có thể dùng `RepositoryEntityLinks` để cung cấp navigation response hoặc thêm link tới repository resource vào response nghiệp vụ.

~~~java
@RepositoryRestController
public class PersonNavigationController {

    private final RepositoryEntityLinks entityLinks;
    private final PersonRepository repository;

    public PersonNavigationController(
            RepositoryEntityLinks entityLinks,
            PersonRepository repository) {
        this.entityLinks = entityLinks;
        this.repository = repository;
    }

    @GetMapping("/people/{id}/navigation")
    ResponseEntity<EntityModel<PersonNavigation>> navigation(
            @PathVariable Long id) {

        Person person = repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND));

        EntityModel<PersonNavigation> model = EntityModel.of(
                new PersonNavigation(person.getId(), person.getDisplayName()),
                entityLinks.linkToItemResource(Person.class, person.getId()),
                entityLinks.linkToCollectionResource(Person.class)
                        .withRel("people"));

        Link byLastName = entityLinks.linkToSearchResource(
                Person.class,
                LinkRelation.of("byLastName"));

        if (byLastName != null) {
            model.add(byLastName);
        }

        return ResponseEntity.ok(model);
    }
}
~~~

Với `@RepositoryRestController`, route nằm trong URI space và base path của Spring Data REST. Nếu dùng một `@RestController` MVC thông thường, có thể inject `RepositoryEntityLinks` để tạo link tới repository resources, nhưng mapping của chính controller vẫn thuộc Spring MVC và cần cấu hình route riêng.

Khi tạo link tới một custom MVC controller, dùng Spring HATEOAS `linkTo(methodOn(...))` là lựa chọn phù hợp hơn. `RepositoryEntityLinks` dành cho các resource do Spring Data REST export.

## 12. RepositoryEntityLinks và resource mappings tùy chỉnh

Spring Data REST cho phép đổi collection path và relation:

~~~java
@RepositoryRestResource(
    path = "persons",
    collectionResourceRel = "people"
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Khi dùng `RepositoryEntityLinks`:

~~~java
Link collection =
        entityLinks.linkToCollectionResource(Person.class);
~~~

Link được tạo theo mapping của repository thay vì bắt buộc phải dùng tên class đã pluralize mặc định.

Điều này đặc biệt hữu ích khi ứng dụng có:

- Collection path khác tên domain type.
- Relation tùy chỉnh.
- Base path khác nhau giữa môi trường.
- Paging parameter được đổi tên.
- Backend ID converter tùy chỉnh.

Không tự suy ra URL từ tên Java class hoặc tên relation. Hãy để Spring Data REST metadata quyết định path và dùng link được trả về.

Nếu repository bị ẩn bằng `@RepositoryRestResource(exported = false)`, không có collection resource công khai để tạo link như một repository endpoint. Hãy kiểm tra repository có thực sự được export trước khi xây navigation cho nó.

## 13. Identifier và custom ID mapping

`linkToItemResource` nhận domain type và một đối tượng ID:

~~~java
Link item = entityLinks.linkToItemResource(Person.class, personId);
~~~

Với repository có ID kiểu `Long`, truyền giá trị Long. Với ID kiểu UUID, truyền UUID tương ứng. Không tự thêm dấu gạch chéo, URL encode hoặc biến đổi giá trị thành path string trước khi truyền.

Spring Data REST có backend ID conversion và resource mapping để tạo URI cho item. Khi ứng dụng dùng custom ID mapping, ví dụ `BackendIdConverter` hoặc `EntityLookup`, hãy bảo đảm identifier truyền vào đúng với quy tắc mà repository/exporter sử dụng.

Cần phân biệt:

- Database primary key: ID lưu trong datastore.
- Backend ID: giá trị mà repository/store dùng để nhận diện entity.
- Public item URI identifier: phần định danh xuất hiện trong URI do REST exporter công bố.

Trong trường hợp mặc định, các giá trị này thường tương ứng. Nếu đã tùy chỉnh URI identifier, không nên giả định chúng luôn giống nhau. Hãy kiểm tra link được sinh ra và GET item URL tương ứng trong integration test.

## 14. Khi nào dùng linkTo thay cho các phương thức typed?

`RepositoryEntityLinks` còn cung cấp:

~~~java
LinkBuilder builder = entityLinks.linkFor(Person.class);
~~~

`linkFor` trả về API cấp thấp `LinkBuilder`. Có thể nối thêm path segment hoặc tham số khi cần:

~~~java
Link searchRoot = entityLinks.linkFor(Person.class)
        .slash("search")
        .withRel("search");
~~~

Tuy nhiên, nếu mục đích là tạo collection/item/page/search resource chuẩn, ưu tiên các phương thức typed:

~~~java
entityLinks.linkToCollectionResource(Person.class);
entityLinks.linkToItemResource(Person.class, id);
entityLinks.linkToPagedResource(Person.class, pageable);
entityLinks.linkToSearchResource(
        Person.class, LinkRelation.of("byLastName"));
~~~

Các phương thức chuyên biệt mô tả rõ ý định và tận dụng resource mapping. Dùng `linkFor` khi cần một path tùy chỉnh chưa có method tương ứng; không tự tái tạo collection hoặc item URL bằng cách nối path nếu API typed đã có sẵn.

Đối với custom MVC route, dùng:

~~~java
linkTo(methodOn(PersonNavigationController.class)
        .navigation(id))
        .withRel("navigation");
~~~

Spring HATEOAS `linkTo(methodOn(...))` phù hợp để tạo link tới controller method. `RepositoryEntityLinks` phù hợp để tạo link tới repository resource.

## 15. Kiểm tra domain type có được hỗ trợ hay không

`RepositoryEntityLinks` triển khai interface `Plugin<Class<?>>` và cung cấp:

~~~java
boolean supported = entityLinks.supports(Person.class);
~~~

Có thể dùng kiểm tra này trong code cần xử lý nhiều domain type:

~~~java
if (!entityLinks.supports(Person.class)) {
    throw new IllegalStateException(
            "Person không có repository resource được hỗ trợ");
}
~~~

Đây là kiểm tra hỗ trợ theo repository metadata; nó không xác nhận một item cụ thể tồn tại. Muốn kiểm tra item, vẫn cần repository lookup.

Không nên dùng `supports` thay cho authorization hoặc kiểm tra export ở runtime của từng endpoint. Nó chỉ giúp xác định `RepositoryEntityLinks` có thể tạo link cho domain type hay không.

## 16. Kiểm thử link bằng MockMvc

Nên kiểm tra link được tạo khớp với base path và repository mapping thực tế. Ví dụ:

~~~java
@SpringBootTest(properties = "spring.data.rest.base-path=/api")
@AutoConfigureMockMvc
class RepositoryEntityLinksTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void customNavigationContainsRepositoryLinks() throws Exception {

        mockMvc.perform(get("/api/people/42/navigation")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.people.href")
                    .value(containsString("/api/people")));
    }
}
~~~

Test trên giả định custom controller trả self link và collection link với relation `people`, đồng thời fixture Person ID 42 tồn tại.

Có thể kiểm tra item link:

~~~java
Link itemLink =
        entityLinks.linkToItemResource(Person.class, 42L);

assertThat(itemLink.getHref())
        .contains("/api/people/42");
~~~

Nếu repository dùng path tùy chỉnh:

~~~java
@RepositoryRestResource(
    path = "persons",
    collectionResourceRel = "people"
)
interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

thì assertion phải phản ánh path `persons`, không phải mặc định `people`.

Kiểm tra search relation:

~~~java
Link searchLink = entityLinks.linkToSearchResource(
        Person.class,
        LinkRelation.of("byLastName"));

assertThat(searchLink).isNotNull();
~~~

Nếu query method không export hoặc relation không khớp, link có thể null. Test nên xác nhận cả trường hợp có và không có search link nếu cấu hình repository có thể thay đổi theo profile.

Ngoài ra, nên kiểm thử:

- Collection path tùy chỉnh.
- Item identifier và custom ID mapping.
- Base path ở từng profile.
- Paging và sort parameter names đã cấu hình.
- Search link có relation tùy chỉnh.
- Repository bị `exported = false`.
- Link tạo ra có thể được client GET thành công.
- Custom controller không hardcode host, port hoặc base path.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không inject được RepositoryEntityLinks | Spring Data REST auto-configuration chưa được nạp hoặc thiếu dependency | Kiểm tra dependency và ApplicationContext |
| Không tạo được link cho domain type | Type không có repository resource được export | Kiểm tra repository scan và exported flag |
| Link có path mặc định thay vì path tùy chỉnh | Đang tự ghép URL hoặc dùng sai domain type | Dùng RepositoryEntityLinks với đúng domain class |
| Search link trả null | Relation không tồn tại, query method không export hoặc rel bị viết sai | Kiểm tra @RestResource(rel = ...) và metadata search |
| Dùng tên Java method nhưng không tìm được link | API tìm theo LinkRelation/rel, không nhất thiết theo method name | Dùng relation thực tế được công bố |
| Link item sai ID | Truyền nhầm kiểu hoặc giá trị identifier | Truyền ID đúng kiểu repository/backend mapping |
| URL bị lặp base path | Custom code tự thêm /api trong khi exporter đã quản lý base path | Dùng link được tạo từ RepositoryEntityLinks |
| Search link thiếu tham số paging | Chưa truyền Pageable/Sort hoặc link vẫn là template | Dùng overload phù hợp và đọc URI template |
| Link collection đúng nhưng GET trả 404 | Resource path đúng nhưng repository/item không được export hoặc route bị security chặn | Kiểm tra exporter mapping và authorization |
| Dùng RepositoryEntityLinks cho custom MVC method | Đây là link tới repository resources, không phải controller mapping tùy ý | Dùng Spring HATEOAS linkTo(methodOn(...)) |
| Link có nhưng item không tồn tại | Link generation không thực hiện repository lookup | Tìm entity và kiểm tra quyền trước khi trả link |
| Collection response quá lớn | Dùng findAll để tự tạo toàn bộ EntityModel | Dùng Pageable/Page/Slice và tạo page representation |

## 18. Quy trình áp dụng

1. Xác định domain type đã có repository được Spring Data REST export.
2. Inject `RepositoryEntityLinks` qua constructor.
3. Dùng `linkToCollectionResource` cho collection và `linkToItemResource` cho item.
4. Dùng `linkToPagedResource` khi cần link trang với Pageable.
5. Dùng `linksToSearchResources` để khám phá mọi finder link.
6. Dùng `linkToSearchResource` với đúng LinkRelation để lấy một finder link.
7. Xử lý kết quả null của search link.
8. Bổ sung link vào EntityModel/CollectionModel.
9. Dùng `linkTo(methodOn(...))` cho custom MVC controller route.
10. Kiểm thử path, relation, base path, ID mapping và khả năng GET link thực tế.

## Tài liệu tham khảo

- [Spring Data REST — Integration: Programmatic Links](https://docs.spring.io/spring-data/rest/reference/integration.html): ví dụ inject RepositoryEntityLinks và tạo link collection, item, page và search resource.
- [Spring Data REST 5.1.2 API — RepositoryEntityLinks](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/support/RepositoryEntityLinks.html): method signatures hiện tại, các overload Pageable/Sort, LinkRelation và kiểu trả về Link/Links.
- [Spring HATEOAS — EntityModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html): biểu diễn một resource cùng hypermedia links.
- [Spring HATEOAS — CollectionModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html): biểu diễn collection resource cùng links.
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection, item, search resources và resource path/rel customization.
- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): cấu hình repository mappings, base path và item resource URI.
