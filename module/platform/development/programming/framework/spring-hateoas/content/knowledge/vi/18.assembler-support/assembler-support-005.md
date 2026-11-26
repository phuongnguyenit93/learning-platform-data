# Tạo collection model

Trong Spring HATEOAS, `CollectionModel<T>` biểu diễn một collection resource gồm nhiều representation cùng các liên kết ở cấp tập hợp. Khi mỗi phần tử cũng cần có link riêng, ứng dụng thường kết hợp `CollectionModel<EntityModel<D>>` với `RepresentationModelAssembler<T, EntityModel<D>>`.

`RepresentationModelAssembler` tập trung việc chuyển một đối tượng domain thành representation hypermedia. Phương thức `toModel(...)` tạo model cho từng phần tử; phương thức `toCollectionModel(...)` áp dụng assembler cho toàn bộ iterable và gom các kết quả vào một `CollectionModel`. Controller nhận kết quả này rồi bổ sung link ở cấp collection như `self`, `search` hoặc một affordance phù hợp.

Ví dụ, API quản lý người dùng có thể trả về collection người dùng. Mỗi người dùng có link self đến chi tiết cá nhân; collection có link self đến chính tập hợp. Client có thể đi từ collection đến từng item theo link được công bố mà không phải tự dựng URI từ ID.

Sau bài học, bạn có thể:

- Phân biệt collection model với model của từng phần tử.
- Cài đặt `RepresentationModelAssembler` để chuyển domain object thành `EntityModel`.
- Dùng `toCollectionModel(...)` để tạo `CollectionModel` từ một iterable.
- Bổ sung link ở cấp collection và phân biệt chúng với link của từng item.
- Định nghĩa relation cho các phần tử nhúng trong HAL.
- Xử lý collection rỗng, collection đã lọc và các trường hợp không có dữ liệu.
- Kiểm thử content, embedded relation, item links và collection links bằng MockMvc.

## 1. CollectionModel và representation của từng item

Một collection resource và một item resource có phạm vi khác nhau:

- Collection resource đại diện cho tập hợp, ví dụ `/people`.
- Item resource đại diện cho một phần tử, ví dụ `/people/42`.

Một phản hồi collection có thể chứa nhiều item representation và các link ở cấp collection. Trong HAL, item thường nằm trong `_embedded`, còn link được nhóm trong `_links`.

Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/people"
    }
  },
  "_embedded": {
    "people": [
      {
        "id": "42",
        "name": "Lan",
        "_links": {
          "self": {
            "href": "https://api.example.com/people/42"
          }
        }
      },
      {
        "id": "43",
        "name": "Minh",
        "_links": {
          "self": {
            "href": "https://api.example.com/people/43"
          }
        }
      }
    ]
  }
}
~~~

Có hai cấp link cần phân biệt:

| Cấp | Ví dụ relation | Mục đích |
|---|---|---|
| Collection | `self`, `search`, `create` | Điều hướng hoặc thao tác với tập hợp |
| Item | `self`, `manager`, `profile` | Điều hướng từ một phần tử cụ thể |

Link self của collection trỏ đến `/people`. Link self của từng item trỏ đến URI riêng của người đó. Hai link cùng relation `self` nhưng thuộc hai representation khác nhau.

### 1.1. CollectionModel không tự chuyển đổi domain object

`CollectionModel<T>` là container cho các representation đã được tạo. Nó không biết cách chuyển một JPA entity hoặc domain object thành DTO, cũng không tự suy ra link self cho từng phần tử.

Có thể tạo thủ công:

~~~java
CollectionModel<EntityModel<PersonRepresentation>> model =
    CollectionModel.of(List.of(firstPersonModel, secondPersonModel));
~~~

Các import cho ví dụ này:

~~~java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
~~~

Trong ứng dụng thực tế, khi cách chuyển đổi cần được tái sử dụng, `RepresentationModelAssembler` đảm nhiệm việc tạo model cho từng item và gom chúng thành collection.

### 1.2. Chọn kiểu phần tử của CollectionModel

Kiểu generic của `CollectionModel` quyết định dữ liệu trong collection:

| Kiểu | Ý nghĩa |
|---|---|
| `CollectionModel<PersonRepresentation>` | Các item là DTO thuần |
| `CollectionModel<EntityModel<PersonRepresentation>>` | Mỗi item có nội dung và link riêng |
| `CollectionModel<PersonModel>` | Mỗi item là lớp riêng kế thừa `RepresentationModel` |

Nếu client cần điều hướng từ collection đến chi tiết từng item, lựa chọn `EntityModel` hoặc một lớp `RepresentationModel` thường phù hợp hơn.

## 2. Định nghĩa representation cho một phần tử

Giả sử ứng dụng quản lý danh bạ. Domain object:

~~~java
public class Person {

    private UUID id;
    private String name;
    private String email;

    public UUID getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
~~~

API không nhất thiết phải công bố toàn bộ domain object. Tạo DTO riêng để xác định dữ liệu được trả về:

~~~java
@Relation(value = "person", collectionRelation = "people")
public record PersonRepresentation(
    UUID id,
    String name,
    String email
) {}
~~~

`@Relation` thuộc package `org.springframework.hateoas.server.core`. Trong ví dụ này:

- `value = "person"` định nghĩa relation cho một item.
- `collectionRelation = "people"` định nghĩa tên relation cho tập hợp item nhúng.

Khi serialize theo HAL, collection có thể xuất hiện dưới khóa `_embedded.people`. Việc khai báo relation rõ ràng giúp tránh để client phụ thuộc vào tên class Java hoặc quy tắc suy luận mặc định.

Các import:

~~~java
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;
~~~

### 2.1. Vì sao tách DTO khỏi domain object?

DTO giúp kiểm soát hợp đồng API:

- Chỉ công bố các trường cần thiết.
- Không vô tình để lộ trường nội bộ hoặc quan hệ persistence.
- Giữ cấu trúc API ổn định khi domain model thay đổi.
- Cho phép một domain object có nhiều representation tùy use case.

Assembler sẽ chuyển `Person` thành `PersonRepresentation` rồi gắn link. Nhờ đó, việc tạo dữ liệu và việc tạo liên kết được tổ chức trong cùng một bước xây representation.

## 3. Cài đặt RepresentationModelAssembler

`RepresentationModelAssembler<T, D>` là interface tổng quát của Spring HATEOAS:

- `T` là kiểu đầu vào, thường là domain object.
- `D` là kiểu representation đầu ra, phải kế thừa `RepresentationModel`.

Phương thức chính là:

~~~java
D toModel(T entity);
~~~

Assembler cho Person:

~~~java
@Component
public class PersonModelAssembler
        implements RepresentationModelAssembler<Person, EntityModel<PersonRepresentation>> {

    @Override
    public EntityModel<PersonRepresentation> toModel(Person person) {
        UUID id = person.getId();

        PersonRepresentation content = new PersonRepresentation(
            id,
            person.getName(),
            person.getEmail()
        );

        return EntityModel.of(
            content,
            linkTo(methodOn(PersonController.class).one(id))
                .withSelfRel()
        );
    }
}
~~~

Assembler thực hiện ba việc:

1. Lấy các trường cần công bố từ domain object.
2. Tạo DTO `PersonRepresentation`.
3. Bọc DTO trong `EntityModel` và thêm link self đến endpoint chi tiết.

Import chính:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

`methodOn(...)` mô tả phương thức controller và tham số để Spring HATEOAS dựng URI theo mapping. Nó không thực thi logic nghiệp vụ của controller.

### 3.1. Mỗi item có link riêng

Với hai đối tượng Person có ID khác nhau, assembler tạo hai model:

~~~java
EntityModel<PersonRepresentation> first = assembler.toModel(person42);
EntityModel<PersonRepresentation> second = assembler.toModel(person43);
~~~

Mỗi model có nội dung riêng và link self trỏ đến đúng ID. Assembler không cần biết collection có bao nhiêu phần tử; nó chỉ chuyển đổi một đối tượng tại một thời điểm.

### 3.2. Thêm link liên quan vào item

Nếu mỗi người có thể liên kết đến hồ sơ hoặc người quản lý, assembler có thể thêm các relation khác:

~~~java
return EntityModel.of(
    content,
    linkTo(methodOn(PersonController.class).one(id)).withSelfRel(),
    linkTo(methodOn(PersonController.class).manager(id)).withRel("manager")
);
~~~

Chỉ thêm link khi endpoint và quan hệ nghiệp vụ tồn tại. Nếu link phụ thuộc trạng thái hoặc quyền, hãy tạo có điều kiện và vẫn kiểm tra quyền ở endpoint đích.

## 4. Tạo collection model bằng toCollectionModel

Interface `RepresentationModelAssembler` cung cấp phương thức mặc định:

~~~java
CollectionModel<D> toCollectionModel(Iterable<? extends T> entities);
~~~

Phương thức này duyệt các phần tử đầu vào, gọi `toModel(...)` cho từng phần tử, sau đó gom các kết quả thành `CollectionModel`.

Với `PersonModelAssembler` ở trên:

~~~java
CollectionModel<EntityModel<PersonRepresentation>> people =
    assembler.toCollectionModel(personService.findAll());
~~~

Nếu service trả về `List<Person>`, danh sách được chuyển thành collection của các `EntityModel<PersonRepresentation>`. Mỗi item giữ link self do assembler tạo.

Điểm cần nhớ: `toCollectionModel(...)` tạo collection từ các item model. Nó không tự biết endpoint collection cụ thể để tạo link self ở cấp tập hợp. Hãy bổ sung link collection tại controller hoặc override phương thức nếu muốn đóng gói quy tắc đó trong assembler.

### 4.1. Controller bổ sung link ở cấp collection

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/people")
public class PersonController {

    private final PersonService service;
    private final PersonModelAssembler assembler;

    public PersonController(
            PersonService service,
            PersonModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping
    public CollectionModel<EntityModel<PersonRepresentation>> all() {
        return assembler.toCollectionModel(service.findAll())
            .add(linkTo(methodOn(PersonController.class).all())
                .withSelfRel());
    }

    @GetMapping("/{id}")
    public EntityModel<PersonRepresentation> one(
            @PathVariable("id") UUID id) {
        return assembler.toModel(service.getRequired(id));
    }
}
~~~

Link self của collection được tạo từ mapping `all()`. Link self của từng item được tạo trong `PersonModelAssembler.toModel(...)`.

Các import chính:

~~~java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

### 4.2. Thêm nhiều link ở cấp collection

Collection có thể cung cấp các liên kết khác ngoài self:

~~~java
return assembler.toCollectionModel(service.findAll())
    .add(
        linkTo(methodOn(PersonController.class).all()).withSelfRel(),
        linkTo(methodOn(PersonController.class).search(null, null))
            .withRel("search")
    );
~~~

Trong ví dụ, giả sử controller có phương thức `search(String city, String name)` với hai query parameter tùy chọn như phần 8.1. `search` là relation tùy chỉnh trỏ đến endpoint tìm kiếm. Không nên thêm link đến một hành động mà endpoint chưa hỗ trợ.

Link create cũng có thể được công bố nếu collection cho phép tạo thành viên:

~~~java
.add(
    linkTo(methodOn(PersonController.class).create(null))
        .withRel("create")
)
~~~

Đoạn mã giả định controller có phương thức `create(CreatePersonRequest request)` được ánh xạ bằng `@PostMapping`; `null` chỉ là placeholder cho tham số body khi dựng URI. Link cơ bản cung cấp relation và href. Nếu client cần biết POST method, content type hoặc cấu trúc body, hãy dùng affordance và media type có khả năng mô tả thao tác đó; không suy luận rằng relation tự nó mô tả đầy đủ HTTP request.

## 5. Tùy chỉnh toCollectionModel

Trong một số ứng dụng, nhiều controller cùng sử dụng assembler và muốn collection luôn có link self. Có thể override `toCollectionModel(...)` để tập trung quy tắc này.

~~~java
@Component
public class PersonModelAssembler
        implements RepresentationModelAssembler<Person, EntityModel<PersonRepresentation>> {

    @Override
    public EntityModel<PersonRepresentation> toModel(Person person) {
        UUID id = person.getId();

        return EntityModel.of(
            new PersonRepresentation(
                id,
                person.getName(),
                person.getEmail()
            ),
            linkTo(methodOn(PersonController.class).one(id)).withSelfRel()
        );
    }

    @Override
    public CollectionModel<EntityModel<PersonRepresentation>> toCollectionModel(
            Iterable<? extends Person> people) {

        return RepresentationModelAssembler.super
            .toCollectionModel(people)
            .add(linkTo(methodOn(PersonController.class).all()).withSelfRel());
    }
}
~~~

Ở đây, `RepresentationModelAssembler.super.toCollectionModel(people)` gọi implementation mặc định của interface để chuyển từng phần tử. Sau đó assembler thêm link self của collection.

Cách này phù hợp khi assembler luôn đại diện cho cùng một collection endpoint. Nếu collection có nhiều biến thể như filter, sort hoặc tenant, việc tự thêm link self cố định trong assembler có thể làm mất tham số của request. Khi đó, controller có thể truyền thông tin ngữ cảnh hoặc tự thêm link sau khi gọi `toCollectionModel(...)`.

### 5.1. Khi nào nên thêm link ở controller?

Thêm link trong controller khi:

- Link phụ thuộc query parameter hiện tại.
- Cùng assembler được dùng cho nhiều collection endpoint.
- Link phản ánh quyền hoặc ngữ cảnh của request.
- Controller chịu trách nhiệm quyết định những khả năng ở cấp collection.

Thêm link trong assembler khi:

- Quy tắc link luôn giống nhau cho mọi lần tạo collection model.
- Assembler được dành riêng cho một collection endpoint.
- Link không phụ thuộc tham số request mà assembler không nhận được.

Điều quan trọng là giữ rõ ranh giới giữa link của từng item và link của collection.

## 6. Tạo CollectionModel thủ công

Không phải lúc nào cũng cần dùng `RepresentationModelAssembler`. Với một danh sách nhỏ hoặc trường hợp chuyển đổi đơn giản, có thể tạo model thủ công.

~~~java
List<EntityModel<PersonRepresentation>> items = people.stream()
    .map(person -> {
        PersonRepresentation content = new PersonRepresentation(
            person.getId(),
            person.getName(),
            person.getEmail()
        );

        return EntityModel.of(
            content,
            linkTo(methodOn(PersonController.class).one(person.getId()))
                .withSelfRel()
        );
    })
    .toList();

CollectionModel<EntityModel<PersonRepresentation>> model =
    CollectionModel.of(
        items,
        linkTo(methodOn(PersonController.class).all()).withSelfRel()
    );
~~~

Các import liên quan:

~~~java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Cách này cho phép kiểm soát toàn bộ việc chuyển đổi ngay tại nơi tạo collection. Tuy nhiên, nếu logic chuyển đổi được dùng ở nhiều nơi, assembler sẽ giúp giảm lặp code và dễ kiểm thử hơn.

### 6.1. CollectionModel.of và add

Hai cách tạo collection phổ biến:

~~~java
CollectionModel<EntityModel<PersonRepresentation>> model =
    CollectionModel.of(items, selfLink);
~~~

hoặc:

~~~java
CollectionModel<EntityModel<PersonRepresentation>> model =
    CollectionModel.of(items)
        .add(selfLink);
~~~

`of(...)` tạo collection từ content và các link ban đầu. `add(...)` bổ sung link sau khi model đã được tạo.

Có thể đọc content và link của model:

~~~java
Iterable<EntityModel<PersonRepresentation>> content = model.getContent();
boolean hasSelf = model.hasLink(IanaLinkRelations.SELF);
~~~

Import relation chuẩn:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
~~~

Không nên chỉnh sửa hoặc tái sử dụng một collection model như một danh sách dữ liệu nghiệp vụ. Nó là representation phục vụ trao đổi hypermedia.

## 7. Collection rỗng

Một collection tồn tại ngay cả khi chưa có phần tử. Ví dụ `GET /people` có thể trả về collection rỗng nhưng vẫn có link self.

Controller không cần nhánh riêng:

~~~java
@GetMapping
public CollectionModel<EntityModel<PersonRepresentation>> all() {
    return assembler.toCollectionModel(service.findAll())
        .add(linkTo(methodOn(PersonController.class).all()).withSelfRel());
}
~~~

Nếu `service.findAll()` trả về danh sách rỗng, `toCollectionModel(...)` tạo collection không có item. Link self vẫn được thêm ở cấp collection.

Trong HAL, `_embedded.people` có thể không xuất hiện khi không có item, tùy cách serializer biểu diễn collection rỗng. Client nên xử lý trường hợp thiếu embedded relation như một collection không có phần tử, theo hợp đồng API; không nên kết luận endpoint không tồn tại chỉ vì không có `_embedded`.

Phân biệt:

- Collection tồn tại nhưng rỗng: thường trả 200 cùng biểu diễn collection và link self.
- Item không tồn tại: endpoint item thường trả 404.
- Endpoint collection không tồn tại: có thể trả 404 theo routing và hợp đồng API.

## 8. Collection đã lọc và sắp xếp

Nếu collection hỗ trợ filter hoặc sort, link self phải mô tả đúng tập kết quả hiện tại.

Ví dụ endpoint:

Đây là biến thể của phương thức `all()` ở mục 4.1: thay chữ ký không tham số bằng chữ ký nhận filter và sort. Không khai báo đồng thời hai handler cùng ánh xạ GET `/people` nếu không có điều kiện mapping để phân biệt.

~~~java
@GetMapping
public CollectionModel<EntityModel<PersonRepresentation>> all(
        @RequestParam(required = false) String city,
        @RequestParam(defaultValue = "name") String sort) {

    List<Person> people = service.findPeople(city, sort);

    return assembler.toCollectionModel(people)
        .add(linkTo(methodOn(PersonController.class).all(city, sort))
            .withSelfRel());
}
~~~

Link self được tạo từ các giá trị filter và sort hiện tại. Nếu client theo link self, nó sẽ quay lại cùng biến thể collection.

Không nên thêm link self không tham số khi response chứa kết quả đã lọc, vì client có thể quay lại tập hợp khác. Với query parameter do người dùng cung cấp, dùng mapping và builder của Spring để tạo URI thay vì nối chuỗi thủ công.

### 8.1. Link search

Nếu API cung cấp endpoint tìm kiếm riêng, có thể thêm link relation `search` ở cấp collection:

~~~java
@GetMapping("/search")
public CollectionModel<EntityModel<PersonRepresentation>> search(
        @RequestParam(required = false) String city,
        @RequestParam(required = false) String name) {

    List<Person> people = service.search(city, name);

    return assembler.toCollectionModel(people)
        .add(linkTo(methodOn(PersonController.class).search(city, name))
            .withSelfRel());
}
~~~

Các import bổ sung:

~~~java
import java.util.List;

import org.springframework.web.bind.annotation.RequestParam;
~~~

Ở một collection response khác, có thể công bố link đến endpoint này bằng `linkTo(methodOn(PersonController.class).search(null, null)).withRel("search")`. Trong một API có search template hoặc affordance, có thể công bố thêm cấu trúc tham số để client khám phá cách tìm kiếm. Link đơn thuần không mô tả đầy đủ tên và kiểu của mọi input.

## 9. CollectionModel và PagedModel

`CollectionModel` phù hợp với collection được trả về như một tập hợp. Khi cần phân trang và metadata như số trang, kích thước trang, tổng số phần tử và link first/prev/next/last, nên dùng `PagedModel`.

| Kiểu | Nội dung | Metadata phân trang |
|---|---|---|
| `CollectionModel<T>` | Một tập hợp representation | Không có metadata page chuẩn |
| `PagedModel<T>` | Nội dung trang hiện tại | Có `PageMetadata` và link điều hướng |
| `Page<T>` | Kết quả truy vấn của Spring Data | Có thông tin trang ở tầng dữ liệu |

Nếu service trả `Page<Person>`, có thể dùng `PagedResourcesAssembler<Person>` để chuyển thành `PagedModel<EntityModel<PersonRepresentation>>`. Không nên chuyển `Page` thành `List` rồi dùng `CollectionModel` nếu API cần công bố metadata phân trang, vì khi đó thông tin totalElements và totalPages bị mất.

Với collection nhỏ, không cần phân trang, `CollectionModel` và `toCollectionModel(...)` là lựa chọn đơn giản.

## 10. Kiểm thử collection model bằng MockMvc

Kiểm thử nên xác nhận cả hai cấp:

- Link self của collection.
- Link self của từng item.
- Nội dung và relation trong `_embedded`.
- Media type HAL.

Ví dụ:

~~~java
@WebMvcTest(PersonController.class)
@Import(PersonModelAssembler.class)
class PersonControllerTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    PersonService service;

    @Test
    void returnsCollectionWithItemAndCollectionLinks() throws Exception {
        UUID id = UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        given(service.findAll()).willReturn(List.of(person(id)));

        mvc.perform(get("/people").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/people")))
            .andExpect(jsonPath("$._embedded.people[0].id")
                .value(id.toString()))
            .andExpect(jsonPath("$._embedded.people[0].name")
                .value("Lan"))
            .andExpect(jsonPath("$._embedded.people[0]._links.self.href")
                .value(endsWith("/people/" + id)));
    }
}
~~~

Fixture `person(id)` tạo một đối tượng Person với tên Lan. Relation `people` được khai báo bằng `@Relation(collectionRelation = "people")`.

Các import thường dùng:

~~~java
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Tùy cấu hình Spring Boot và phiên bản Spring, test slice có thể cần import thêm cấu hình hypermedia hoặc cấu hình service. Hãy giữ test setup phù hợp với ApplicationContext của ứng dụng.

### 10.1. Kiểm thử collection rỗng

Khi service trả về danh sách rỗng:

~~~java
given(service.findAll()).willReturn(List.of());

mvc.perform(get("/people").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists());
~~~

Không nên bắt buộc `$._embedded.people` phải tồn tại nếu serializer bỏ qua embedded relation khi content rỗng. Hãy xác nhận response vẫn đại diện cho collection và có link self.

### 10.2. Kiểm thử từng item có link riêng

Nếu collection có nhiều phần tử, xác nhận href của từng item được tạo từ ID tương ứng. Điều này phát hiện lỗi assembler dùng nhầm ID hoặc mọi item trỏ đến cùng một URI.

### 10.3. Kiểm thử relation của embedded collection

Nếu đổi `@Relation(collectionRelation = "people")` thành tên khác, cấu trúc HAL cũng thay đổi. Kiểm thử relation giúp bảo vệ hợp đồng mà client sử dụng. Không nên để client phụ thuộc vào tên class hoặc cách Spring tự suy ra relation nếu tên đó chưa được công bố rõ.

## 11. Lỗi thường gặp khi tạo collection model

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ trả danh sách DTO thuần | Không có link điều hướng ở item | Dùng EntityModel hoặc RepresentationModel cho item |
| Chỉ thêm link self cho từng item | Collection không có link self | Bổ sung link ở cấp CollectionModel |
| Nghĩ toCollectionModel tự tạo link collection | Response thiếu link self của tập hợp | Thêm link tại controller hoặc override phương thức |
| Dùng sai generic type | Không thể thêm link cho item hoặc sai cấu trúc serialize | Chọn CollectionModel<EntityModel<DTO>> khi item cần link |
| Không khai báo relation cho embedded collection | Tên relation có thể phụ thuộc suy luận mặc định | Dùng @Relation và kiểm thử tên |
| Coi collection rỗng là endpoint không tồn tại | Client xử lý sai trạng thái | Trả collection rỗng với link self |
| Mất filter trong link self | Client quay lại tập kết quả khác | Truyền filter và sort hiện tại |
| Dùng CollectionModel cho dữ liệu cần metadata page | Mất thông tin tổng số trang và điều hướng trang | Dùng PagedModel |
| Lặp logic tạo link ở nhiều nơi | Href và relation không nhất quán | Tập trung trong assembler |
| Cho rằng link cấp quyền truy cập | Endpoint có thể bị gọi trực tiếp | Kiểm tra quyền và nghiệp vụ ở server |

## 12. Quy trình tạo collection model

Khi xây dựng endpoint trả về một collection hypermedia, có thể thực hiện theo trình tự:

1. Xác định domain type và các trường được phép công bố.
2. Tạo DTO cho item và khai báo relation cho embedded collection.
3. Cài đặt `RepresentationModelAssembler<T, EntityModel<D>>`.
4. Trong `toModel(...)`, chuyển domain object thành DTO và tạo link self cho item.
5. Trong controller, gọi `assembler.toCollectionModel(iterable)`.
6. Bổ sung link self và các link ở cấp collection.
7. Giữ filter/sort hiện tại trong link nếu response là collection đã lọc.
8. Dùng `PagedModel` nếu API cần metadata và điều hướng phân trang.
9. Kiểm thử collection có dữ liệu, collection rỗng, relation embedded và link ở cả hai cấp.

## 13. Kết luận

`RepresentationModelAssembler` giúp chuyển từng domain object thành representation hypermedia thông qua `toModel(...)`. Phương thức `toCollectionModel(...)` áp dụng việc chuyển đổi đó cho một iterable và trả về `CollectionModel`. Nhờ vậy, logic tạo DTO và link của từng item được tái sử dụng, còn controller có thể bổ sung các link ở cấp collection.

Khi kết hợp `CollectionModel<EntityModel<DTO>>`, link self của từng item và link self của collection được phân biệt rõ. `@Relation` giúp kiểm soát tên embedded relation trong HAL; kiểm thử MockMvc bảo vệ nội dung, relation và href. Với dữ liệu cần phân trang, dùng `PagedModel` để giữ metadata và các link điều hướng thay vì làm mất thông tin khi chuyển thành một collection thông thường.

