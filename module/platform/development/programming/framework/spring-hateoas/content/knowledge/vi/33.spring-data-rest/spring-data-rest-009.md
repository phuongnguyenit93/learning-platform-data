# Override representation trong Spring Data REST

Spring Data REST tự chuyển domain entity thành REST representation. Với một entity, exporter thường sao chép các thuộc tính đơn giản hoặc embedded vào payload và tạo link cho những association được quản lý bởi repository. Cách mặc định này phù hợp với CRUD API thông thường, nhưng đôi khi response cần thêm link nghiệp vụ, một tập trường khác, một cấu trúc dữ liệu riêng hoặc một handler có thể xử lý kết quả trước khi trả về client.

Spring Data REST và Spring HATEOAS cung cấp nhiều mức tùy chỉnh. Bạn có thể giữ nguyên payload và bổ sung link bằng `RepresentationModelProcessor`, chọn tập trường bằng projection, thay đổi cách chuyển entity thành representation bằng `ConversionService` và `Converter`, hoặc viết handler riêng bằng `@RepositoryRestController`. Nếu chỉ cần định dạng một kiểu dữ liệu, custom Jackson serializer có thể là lựa chọn phù hợp hơn. Hãy chọn extension point theo phần thực sự cần thay đổi để giữ các link và semantics hypermedia ổn định.

## 1. Representation mặc định của Spring Data REST

Spring Data REST xuất bản repository thành collection resource, item resource và association resource. Khi serialize một entity, exporter tạo một `EntityModel` chứa dữ liệu cùng các link.

Ví dụ một response người dùng:

```json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "/people/1"
    },
    "address": {
      "href": "/people/1/address"
    }
  }
}
```

Các thuộc tính `firstName` và `lastName` là dữ liệu của entity. `self` trỏ tới item resource; `address` là link tới association resource do Spring Data REST quản lý. Với collection resource, item có thể được đặt dưới `_embedded`, còn page metadata và pagination links được thêm nếu repository hỗ trợ phân trang.

Khi override representation, hãy xác định phần nào của response cần thay đổi và phần nào cần giữ lại. Nếu thay toàn bộ conversion mặc định, bạn có thể phải tự tạo lại self link, association link, relation collection hoặc metadata phân trang.

## 2. Chọn đúng extension point

Không phải mọi yêu cầu thay đổi JSON đều cần thay converter. Bảng sau giúp chọn cách tùy chỉnh phù hợp:

| Nhu cầu | Cơ chế phù hợp | Phạm vi thay đổi |
| --- | --- | --- |
| Thêm link trợ giúp hoặc link nghiệp vụ | `RepresentationModelProcessor` | Bổ sung link vào model hiện có. |
| Chọn trường nào được hiển thị | Projection hoặc excerpt projection | Thay đổi tập thuộc tính được biểu diễn. |
| Chuyển entity thành cấu trúc representation khác | `ConversionService` và `Converter<Entity, EntityModel>` | Thay conversion mặc định. |
| Tạo handler tùy chỉnh trong URI space của repository | `@RepositoryRestController` | Kiểm soát request, xử lý dữ liệu và response cho route đó. |
| Tạo route riêng dưới base path, không gắn với một repository cụ thể | `@BasePathAwareController` | Bổ sung custom operation trong namespace Spring Data REST. |
| Định dạng một value object hoặc kiểu dữ liệu cụ thể | Jackson serializer/deserializer | Thay cách serialize hoặc deserialize kiểu đó. |

Ưu tiên cơ chế hẹp nhất đáp ứng yêu cầu. Ví dụ, nếu chỉ cần thêm relation `help`, processor ít ảnh hưởng hơn việc thay converter cho toàn bộ entity. Nếu chỉ cần ẩn một số trường, projection thường rõ ràng hơn một custom serializer cho cả entity.

## 3. Thêm link vào representation bằng RepresentationModelProcessor

`RepresentationModelProcessor` cho phép xử lý hypermedia model trong luồng exporter tạo representation. Spring Data REST tự phát hiện các bean có kiểu `RepresentationModelProcessor<EntityModel<T>>` và áp dụng chúng khi serialize entity có kiểu `T`, trước khi response được ghi ra.

Ví dụ thêm link tài liệu trợ giúp cho mọi representation `Person`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class PersonRepresentationProcessor
        implements RepresentationModelProcessor<EntityModel<Person>> {

    @Override
    public EntityModel<Person> process(EntityModel<Person> model) {
        model.add(linkTo(methodOn(PersonDocsController.class).people())
                .withRel("help"));
        return model;
    }
}
```

Controller tài liệu có thể khai báo như sau:

```java
import org.springframework.data.rest.webmvc.BasePathAwareController;

@BasePathAwareController
class PersonDocsController {

    @GetMapping("/docs/people")
    ResponseEntity<String> people() {
        return ResponseEntity.ok("Documentation for people resources");
    }

    @GetMapping("/docs/people/active")
    ResponseEntity<String> activePeople() {
        return ResponseEntity.ok("Documentation for active people");
    }
}
```

`linkTo(methodOn(...))` tạo URI từ mapping controller thay vì hard-code hostname. Processor thêm relation `help` vào model; nó không thay đổi các thuộc tính `firstName`, `lastName` hoặc association link mặc định.

Processor này được áp dụng cho representation có kiểu `EntityModel<Person>`. Nếu cần xử lý collection model hoặc một kiểu representation khác, hãy khai báo processor đúng generic type và xác nhận nó được exporter áp dụng trong response thực tế.

## 4. Dùng processor có điều kiện

Có thể thêm link tùy theo dữ liệu của entity hoặc trạng thái nghiệp vụ. Đây là biến thể thay cho processor ở ví dụ trước; giả sử `Person` có thuộc tính boolean `active`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class PersonRepresentationProcessor
        implements RepresentationModelProcessor<EntityModel<Person>> {

    @Override
    public EntityModel<Person> process(EntityModel<Person> model) {
        Person person = model.getContent();

        if (person != null && person.isActive()) {
            model.add(linkTo(methodOn(PersonDocsController.class)
                    .activePeople()).withRel("active-help"));
        }

        return model;
    }
}
```

Điều kiện trong ví dụ chỉ minh họa việc công bố link theo trạng thái. Trong ứng dụng thực tế, nếu việc công bố link phụ thuộc quyền người dùng hiện tại, hãy dùng policy/service chuyên trách để quyết định. Không lưu request-specific state trong field của processor singleton.

Link chỉ giúp client khám phá khả năng. Endpoint đích vẫn phải kiểm tra xác thực, quyền và trạng thái nghiệp vụ khi nhận request. Không công bố link không phải là cơ chế bảo vệ endpoint.

## 5. Phân biệt processor với thay đổi payload

`RepresentationModelProcessor` phù hợp nhất để bổ sung hoặc điều chỉnh hypermedia controls như link. Ví dụ, nó có thể thêm `help`, `orders`, `cart` hoặc affordance phù hợp vào model.

Nếu mục tiêu là thay đổi dữ liệu trong payload, processor không phải lựa chọn đầu tiên. Với việc chọn hoặc ẩn trường, hãy xem projection. Với việc biến một entity thành DTO có cấu trúc khác, hãy xem custom converter hoặc custom controller.

Không nên ép processor trở thành tầng mapping DTO. Việc chuyển đổi dữ liệu cần có ranh giới rõ ràng, đặc biệt khi entity có quan hệ JPA hai chiều, trường nhạy cảm hoặc lazy association.

## 6. Chọn tập trường bằng projection

Projection cho phép Spring Data REST trình bày một tập thuộc tính khác của domain type. Ví dụ:

```java
@Projection(name = "summary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
```

Client có thể yêu cầu:

```http
GET /people/1?projection=summary
Accept: application/hal+json
```

Projection phù hợp khi bạn muốn có nhiều view được xác định trước như summary, detail hoặc view dành cho một use case. Excerpt projection có thể dùng làm representation mặc định của item khi item xuất hiện trong collection hoặc quan hệ liên quan.

Projection không nhất thiết thay đổi domain entity hoặc repository. Nó thay đổi cách các thuộc tính được đưa vào response. Hãy cân nhắc kỹ những thuộc tính association được inline, vì việc mở rộng projection có thể làm tăng payload hoặc kích hoạt truy cập lazy.

## 7. Thay conversion mặc định bằng Converter<Entity, EntityModel>

Khi cần cấu trúc representation khác hẳn cách exporter mặc định tạo model, Spring Data REST cho phép đăng ký `ConversionService` riêng cùng converter từ entity sang `EntityModel`.

Converter chịu trách nhiệm chuyển entity thành representation mà client nhận được. Ví dụ, thay vì công bố toàn bộ `Person`, API có thể công bố một view với tên hiển thị và trạng thái:

```java
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "person", collectionRelation = "people")
public record PersonView(
        Long id,
        String displayName,
        boolean active
) {}
```

Converter:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

class PersonToEntityModelConverter
        implements Converter<Person, EntityModel<PersonView>> {

    @Override
    public EntityModel<PersonView> convert(Person source) {
        PersonView view = new PersonView(
                source.getId(),
                source.getFirstName() + " " + source.getLastName(),
                source.isActive()
        );

        return EntityModel.of(
                view,
                Link.of("/people/" + source.getId(), IanaLinkRelations.SELF)
        );
    }
}
```

Đăng ký converter trong `ConversionService` của ứng dụng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

@Configuration
class PersonRepresentationConfiguration {

    @Bean
    ConversionService conversionService() {
        DefaultConversionService service = new DefaultConversionService();
        service.addConverter(new PersonToEntityModelConverter());
        return service;
    }
}
```

Nếu ứng dụng đã có một bean `ConversionService` dùng cho Spring MVC hoặc các thành phần khác, hãy kiểm tra cách Spring Data REST lấy conversion service và bổ sung converter vào cấu hình tương ứng thay vì tạo một bean cạnh tranh ngoài ý muốn.

Ví dụ dùng relative URI `/people/{id}` để minh họa. Nếu ứng dụng có base path như `/api`, cần bảo đảm link chứa base path chính xác hoặc tạo link từ controller mapping. Không hard-code host/port của môi trường triển khai.

Spring Data REST dùng converter này trong quá trình chuyển entity thành model. Đây là extension point nâng cao: cần xác nhận exporter thực sự sử dụng `ConversionService` đã đăng ký và các converter cần thiết khác vẫn hoạt động. Nếu thay conversion mặc định, bạn chịu trách nhiệm giữ các link mà client cần, bao gồm self link và association link.

## 8. Những gì cần bảo toàn khi thay converter

Default converter của Spring Data REST không chỉ sao chép thuộc tính. Nó còn duyệt entity metadata để tạo link tới những association được quản lý bởi repository. Khi thay conversion mặc định, hãy kiểm tra các phần sau:

- Self link của item trỏ tới đúng item resource.
- Association link trỏ tới đúng association resource.
- Relation name giữ ổn định theo hợp đồng API.
- Embedded data chỉ chứa những trường client cần.
- Collection representation có relation đúng và mỗi item có link riêng khi cần.
- Pagination response vẫn có page metadata và các link điều hướng.
- Base path và URI được tạo đúng trong môi trường có context path hoặc reverse proxy.
- Không đưa dữ liệu nhạy cảm vào DTO hoặc link.

Nếu chỉ muốn thay đổi vài trường, hãy cân nhắc projection thay vì thay toàn bộ converter. Việc thay converter có thể ảnh hưởng nhiều endpoint dùng cùng domain type.

## 9. Dùng @RepositoryRestController cho custom response handler

Khi cần xử lý một request trong URI space của repository, có thể dùng `@RepositoryRestController`. Annotation này giúp controller sử dụng base path, message converters, exception handling và các cấu hình Spring Data REST liên quan.

Ví dụ tạo một collection resource tùy chỉnh cho những người đang hoạt động:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RepositoryRestController
class PersonSearchController {

    private final PersonRepository repository;

    PersonSearchController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/people/reports/active")
    ResponseEntity<CollectionModel<PersonView>> activePeople() {
        List<PersonView> people = repository.findByActiveTrue().stream()
                .map(person -> new PersonView(
                        person.getId(),
                        person.getFirstName() + " " + person.getLastName(),
                        person.isActive()))
                .toList();

        CollectionModel<PersonView> model = CollectionModel.of(
                people,
                linkTo(methodOn(PersonSearchController.class)
                        .activePeople()).withSelfRel()
        );

        return ResponseEntity.ok(model);
    }
}
```

Mapping `@GetMapping("/people/reports/active")` nằm trong URI space của repository `people`; base path Spring Data REST được áp dụng tự động. Handler có thể lấy dữ liệu từ repository, chuyển sang view và thêm link self cho collection resource tùy chỉnh.

`@RepositoryRestController` phù hợp với thao tác gắn với một resource/repository. Nếu cần route tùy chỉnh dưới base path nhưng không gắn với một repository cụ thể, hãy xem `@BasePathAwareController`.

Khi muốn thay handler ở đúng URI đã được exporter sử dụng, cần kiểm tra mapping thực tế và tránh đăng ký hai handler cạnh tranh cho cùng method/path. Đừng giả định mọi custom mapping sẽ tự động ghi đè handler mặc định chỉ vì cùng tên resource.

## 10. Dùng PersistentEntityResourceAssembler khi cần giữ metadata của Spring Data REST

Một custom controller đôi khi vẫn muốn trả entity theo representation chuẩn của Spring Data REST. `PersistentEntityResourceAssembler` là `RepresentationModelAssembler` có thể tạo `PersistentEntityResource` từ domain object, giữ metadata persistent entity và các link mà exporter cần.

Ví dụ custom handler đọc một người và dùng assembler:

```java
@RepositoryRestController
class PersonDetailController {

    private final PersonRepository repository;

    PersonDetailController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/people/{id}/review")
    ResponseEntity<?> review(
            @PathVariable Long id,
            PersistentEntityResourceAssembler assembler) {

        return repository.findById(id)
                .map(assembler::toModel)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
```

Ví dụ trả representation chuẩn của entity tại route review tùy chỉnh. Nếu cần view hoàn toàn khác, hãy chuyển sang DTO/`EntityModel` riêng và chủ động tạo link. Assembler này hữu ích khi muốn tận dụng metadata và quy tắc link của Spring Data REST trong custom handler.

## 11. Phân biệt @RepositoryRestController và @BasePathAwareController

Hai annotation đều tạo controller trong namespace base path, nhưng phạm vi tích hợp khác nhau:

| Annotation | Khi dùng | Tích hợp bổ sung |
| --- | --- | --- |
| `@RepositoryRestController` | Custom handler gắn với repository hoặc URI space của repository. | Có cấu hình CORS theo repository tương ứng và `OpenEntityManagerInViewInterceptor` khi dùng JPA. |
| `@BasePathAwareController` | Custom operation, resource hoặc view dưới base path nhưng không gắn với một entity/repository cụ thể. | Áp dụng base path cho mapping. |
| `@RestController` | Endpoint MVC độc lập ngoài phạm vi Spring Data REST. | Dùng request handling, message converter và exception handling của MVC thông thường. |

Nếu muốn tận dụng cấu hình, message converter và exception handling của Spring Data REST, hãy chọn `@RepositoryRestController` cho handler liên quan tới repository. Một `@RestController` thông thường nằm ngoài phạm vi tích hợp đó.

## 12. Dùng Jackson serializer khi chỉ cần thay đổi một kiểu dữ liệu

Nếu representation chỉ cần một kiểu con được serialize theo định dạng riêng, hãy dùng Jackson `Module`, `JsonSerializer` hoặc `JsonDeserializer` thay vì thay converter cho toàn entity.

Ví dụ `Money` cần được biểu diễn thành amount và currency:

```java
public record Money(BigDecimal amount, String currency) {}
```

Serializer có thể ghi object JSON tương ứng, trong khi Spring Data REST tiếp tục tạo `_links` và association link cho entity. Các `Module` bean trong application context được exporter đăng ký với `ObjectMapper` của nó.

Đây là lựa chọn phù hợp cho kiểu value object, abstract type hoặc cấu trúc domain khó serialize theo mặc định. Nếu request body cũng cần được đọc theo cấu trúc đặc biệt, cần thêm deserializer hoặc dùng input DTO riêng. Serializer không tự động thay đổi cách deserialize.

## 13. Giữ ổn định content negotiation và hypermedia

Representation là một phần của HTTP contract. Khi override, hãy kiểm tra response với media type mà API hỗ trợ, thường là `application/hal+json` và `application/json` nếu được cấu hình.

Các điểm cần giữ:

- `Accept` header phải được xử lý bởi converter tương ứng.
- `Content-Type` của response phải phản ánh representation thực tế.
- HAL response cần giữ `_links`, `_embedded` và `page` nếu endpoint có phân trang.
- Relation và URI phải nhất quán giữa collection, item và association.
- Nếu cùng URI trả nhiều representation theo `Accept`, cache cần phân biệt các biến thể phù hợp, thường qua `Vary: Accept`.
- Custom DTO không được vô tình biến response hypermedia thành JSON thuần khi client yêu cầu HAL.

Một custom controller trả `CollectionModel` hoặc `EntityModel` giúp Spring HATEOAS serialize theo media type được chọn. Nếu trả DTO thuần, response không tự có link chỉ vì ứng dụng đã cài Spring HATEOAS.

## 14. Không nhầm override representation với validation hoặc bảo mật

Thay representation chỉ thay đổi dữ liệu và hypermedia controls được gửi cho client. Nó không thay thế:

- Bean Validation cho request body.
- Kiểm tra quy tắc nghiệp vụ trong service.
- Authorization theo người dùng, tenant hoặc từng entity.
- Kiểm soát HTTP method được export.
- Bảo vệ dữ liệu nhạy cảm trong domain object.

Ví dụ, ẩn link `delete` khỏi response không ngăn client gọi DELETE trực tiếp. Nếu một field không được phép chỉnh sửa, đừng chỉ loại field khỏi representation; hãy kiểm soát binding và cập nhật ở server.

Custom converter cũng có thể vô tình làm lộ field mới. Hãy xem DTO/representation như một allowlist: chỉ đưa vào các thuộc tính cần công bố.

## 15. Kiểm thử processor và representation bằng MockMvc

Kiểm thử HTTP giúp xác nhận exporter thực sự áp dụng processor hoặc converter. Ví dụ kiểm tra link `help` được thêm vào representation người:

```java
mockMvc.perform(get("/people/{id}", personId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.help.href").exists());
```

Nếu dùng projection, kiểm tra đúng trường được công bố:

```java
mockMvc.perform(get("/people/{id}", personId)
        .param("projection", "summary")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.firstName").exists())
    .andExpect(jsonPath("$.lastName").exists())
    .andExpect(jsonPath("$.email").doesNotExist());
```

Test giả định entity `Person` có thuộc tính `email`, còn `PersonSummary` không khai báo getter cho trường đó.

Nếu dùng custom controller, kiểm tra content type, payload và self link:

```java
mockMvc.perform(get("/people/reports/active")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.people").isArray());
```

`@Relation` đặt tên relation cho item và collection trong HAL. Test cần có fixture ít nhất một người đang hoạt động để xác nhận `_embedded.people` được tạo.

Với custom converter, hãy kiểm tra cả payload mới và các link cần bảo toàn:

- Các trường DTO có giá trị đúng.
- Self link vẫn trỏ tới item resource.
- Association link còn tồn tại nếu hợp đồng yêu cầu.
- Collection và pagination metadata không bị mất.
- Các trường nhạy cảm không xuất hiện.
- Cả request `Accept: application/hal+json` và media type khác đều có kết quả đúng.

## 16. Các lỗi thường gặp

**Dùng processor để thay toàn bộ payload.** Processor phù hợp với việc hậu xử lý model và thêm link; dùng projection hoặc converter nếu cần đổi cấu trúc dữ liệu.

**Thay converter chỉ để thêm một link.** Dùng `RepresentationModelProcessor` để tránh phải tự tạo lại toàn bộ relation và association links.

**Quên self link khi tự tạo EntityModel.** Representation tự xây dựng cần công bố link self nếu client cần truy cập lại tài nguyên.

**Thay ConversionService nhưng mất converter khác.** Kiểm tra exporter đang dùng service nào và bảo đảm các conversion cần thiết vẫn hoạt động.

**Cho rằng @RepositoryRestController luôn ghi đè handler mặc định.** Mapping phải nằm trong URI space của repository và không được xung đột với handler khác. Kiểm thử mapping thực tế.

**Dùng @RestController cho endpoint cần tích hợp Spring Data REST.** Controller thông thường nằm ngoài phạm vi message converter, exception handling và các tích hợp của exporter.

**Trả DTO thuần nhưng kỳ vọng có HAL link.** Dùng `EntityModel`, `CollectionModel` hoặc `RepresentationModel` và thêm link cần thiết.

**Làm mất association link hoặc pagination metadata.** Khi thay representation, kiểm thử cả item, collection và page response.

**Xem việc ẩn field hoặc link là bảo mật.** Server vẫn phải kiểm soát dữ liệu ghi, quyền truy cập và HTTP method.

## 17. Bài tập thực hành và tiêu chí hoàn thành

Hãy tùy chỉnh API Spring Data REST cho `Person`:

1. Tạo repository `PersonRepository` được export tại `/people`.
2. Viết `RepresentationModelProcessor<EntityModel<Person>>` để thêm link `help`.
3. Kiểm tra link mới xuất hiện mà self và association links vẫn được giữ.
4. Tạo projection `PersonSummary` để chỉ công bố tên và họ.
5. Tạo `PersonView` và converter riêng nếu cần thay đổi hoàn toàn cấu trúc output.
6. Khi thay converter, tạo lại self link và association link cần thiết.
7. Viết một `@RepositoryRestController` cho collection resource tùy chỉnh.
8. Dùng `PersistentEntityResourceAssembler` nếu custom handler cần giữ metadata representation chuẩn của Spring Data REST.
9. So sánh `@RepositoryRestController`, `@BasePathAwareController` và `@RestController` theo phạm vi tích hợp.
10. Dùng MockMvc kiểm tra HAL response, content negotiation, trường dữ liệu, link và quyền truy cập.

Bạn đã hiểu cách override representation khi có thể phân biệt việc bổ sung link với việc thay đổi payload, chọn đúng giữa processor, projection, custom converter, controller và Jackson serializer, đồng thời giữ các hypermedia controls cần thiết. Một representation tùy chỉnh tốt phải thể hiện đúng dữ liệu client cần, giữ URI và relation ổn định, tương thích với media type và vẫn tuân thủ validation cùng security ở phía server.

## Tài liệu tham khảo chính thức

- [Spring Data REST – Customizing the JSON Output](https://docs.spring.io/spring-data/rest/reference/customizing/customizing-json-output.html)
- [Spring Data REST – Overriding Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Spring Data REST API – PersistentEntityResourceAssembler](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/PersistentEntityResourceAssembler.html)
- [Spring HATEOAS Reference Documentation – RepresentationModelProcessor](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.representation-model-processors)
