# Lựa chọn điểm mở rộng: cấu hình, processor, listener hoặc Controller

## Mục tiêu

Spring Data REST tự động xuất bản các Spring Data repository thành REST API. Khi API cần thay đổi hành vi mặc định, bạn có thể mở rộng ở nhiều tầng khác nhau: cấu hình toàn cục, representation trả về, vòng đời thao tác repository hoặc endpoint HTTP.

Chọn đúng điểm mở rộng giúp phần tùy biến nằm ở đúng nơi chịu trách nhiệm. Ví dụ, thêm một liên kết vào JSON không cần viết lại controller; kiểm tra dữ liệu trước khi REST exporter lưu entity không cần tạo endpoint mới; còn một quy trình nghiệp vụ nhiều bước có thể cần controller riêng.

Bài này tập trung vào bốn lựa chọn chính:

1. `RepositoryRestConfigurer`: cấu hình cách Spring Data REST hoạt động.
2. `RepresentationModelProcessor`: bổ sung liên kết hoặc nội dung hypermedia cho representation.
3. Repository REST events/listeners: xử lý các sự kiện trong vòng đời tạo, lưu, xóa và thay đổi liên kết.
4. `@RepositoryRestController`: xây dựng hoặc thay thế handler cho một endpoint thuộc không gian URI của Spring Data REST.

## 1. Bắt đầu bằng việc xác định loại thay đổi

Trước khi viết code, hãy xác định điều gì cần thay đổi:

| Nhu cầu | Điểm mở rộng nên xem xét |
|---|---|
| Đổi base path, quy tắc export repository, giới hạn trang, CORS hoặc cách chuyển đổi kiểu | `RepositoryRestConfigurer` và `RepositoryRestConfiguration` |
| Thêm link, link điều hướng hoặc thông tin hypermedia vào response hiện có | `RepresentationModelProcessor` |
| Kiểm tra, chuẩn hóa, ghi audit hoặc phản ứng với thao tác tạo/lưu/xóa qua REST | Repository REST event handler hoặc listener |
| Thêm endpoint, xử lý request riêng, tổng hợp dữ liệu hoặc thay thế response handler | `@RepositoryRestController` |
| Thay đổi cách truy vấn hoặc truy cập dữ liệu | Repository query method hoặc custom repository fragment |

Các annotation `@RepositoryRestResource` và `@RestResource` cũng là công cụ cấu hình khai báo hữu ích. Chúng phù hợp để đổi path, relation name, projection hoặc tắt export của repository/method. Khi cần logic động hoặc một luồng HTTP tùy chỉnh, hãy chọn extension point tương ứng ở trên.

## 2. Cấu hình toàn cục với RepositoryRestConfigurer

Dùng `RepositoryRestConfigurer` khi muốn thay đổi cấu hình chung của REST exporter. Interface này cung cấp callback để điều chỉnh `RepositoryRestConfiguration` và các thành phần tích hợp khác.

Với Spring Boot, cấu hình tự động của Spring Data REST được bật khi ứng dụng có starter phù hợp. Chỉ cần đăng ký một bean `RepositoryRestConfigurer`; không cần tự import cấu hình MVC của Spring Data REST trong ứng dụng Spring Boot thông thường.

Ví dụ đổi base path, giới hạn kích thước trang và cấu hình CORS:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestApiConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setBasePath("/api");
        config.setDefaultPageSize(25);
        config.setMaxPageSize(100);

        cors.addMapping("/**")
                .allowedOrigins("https://client.example")
                .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE");
    }
}
~~~

Sau cấu hình, các repository resource được phục vụ dưới base path `/api`. Client có thể yêu cầu tối đa 100 phần tử mỗi trang; trang mặc định có 25 phần tử. Origin và HTTP method được cho phép trong ví dụ chỉ là giá trị minh họa, cần thay bằng chính sách của ứng dụng.

Một số nhóm cấu hình khác mà `RepositoryRestConfigurer` hỗ trợ:

- **Repository exposure:** đặt `RepositoryDetectionStrategy`, kiểm soát HTTP method được export và cấu hình quy tắc export theo domain type.
- **Conversion:** đăng ký converter để chuyển đổi giá trị request parameter hoặc kiểu dữ liệu.
- **HTTP message conversion:** thêm hoặc điều chỉnh `HttpMessageConverter`.
- **Jackson:** cấu hình mapper/module, serializer và deserializer dành cho representation.
- **Validation:** đăng ký validator với `ValidatingRepositoryEventListener`.
- **Exception handling:** tùy chỉnh `ExceptionHandlerExceptionResolver` được REST exporter sử dụng.

Ví dụ, nếu cần thêm validator chạy trước khi tạo hoặc lưu entity, có thể cấu hình listener trong cùng configurer:

~~~java
@Override
public void configureValidatingRepositoryEventListener(
        ValidatingRepositoryEventListener listener) {

    listener.addValidator("beforeCreate", personValidator);
    listener.addValidator("beforeSave", personValidator);
}
~~~

Tên event `beforeCreate` và `beforeSave` gắn validator với hai thời điểm tương ứng của REST exporter.

Với các tùy chọn cơ bản đã có trong Spring Boot properties, hãy ưu tiên cấu hình bằng `spring.data.rest.*`. Dùng `RepositoryRestConfigurer` khi cần callback, cấu hình có điều kiện hoặc tích hợp bean Java. Tránh đăng ký nhiều configurer cùng chỉnh một thuộc tính mà không kiểm soát thứ tự và kết quả cuối.

## 3. Bổ sung hypermedia bằng RepresentationModelProcessor

Dùng `RepresentationModelProcessor` khi response mặc định đã đúng về dữ liệu nhưng cần thêm liên kết để client tiếp tục điều hướng hoặc thực hiện một thao tác liên quan.

Spring Data REST tích hợp với Spring HATEOAS. Các bean `RepresentationModelProcessor<EntityModel<T>>` được exporter nhận diện khi tạo representation cho entity kiểu `T`.

Ví dụ thêm liên kết tới trang hướng dẫn dành cho một Person:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelProcessor;

@Configuration
public class PersonRepresentationConfiguration {

    @Bean
    RepresentationModelProcessor<EntityModel<Person>> personProcessor() {
        return model -> {
            model.add(Link.of("/docs/people").withRel("documentation"));
            return model;
        };
    }
}
~~~

Khi Spring Data REST serialize một entity `Person`, processor được gọi với `EntityModel<Person>`. Link có relation `documentation` sẽ được thêm vào representation HAL trong `_links`.

Ví dụ phần link trong response:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/people/42"
    },
    "documentation": {
      "href": "/docs/people"
    }
  },
  "firstName": "An",
  "lastName": "Nguyen"
}
~~~

Trong ứng dụng thực tế, nên tạo link bằng Spring HATEOAS `linkTo(...)`, `methodOn(...)` hoặc các API link tương ứng thay vì hard-code host, port hay base path. Cách tạo link theo mapping giúp ứng dụng hoạt động đúng khi chạy sau reverse proxy hoặc khi base path thay đổi.

Processor phù hợp với các việc như:

- Bổ sung link tới tài nguyên liên quan hoặc tài liệu.
- Thêm action link khi entity đáp ứng một điều kiện.
- Bổ sung metadata trình bày mà client cần để tiếp tục điều hướng.
- Chuẩn hóa các link của một loại representation.

Processor chạy trong quá trình xây dựng representation. Không dùng nó để lưu entity, thực hiện side effect, kiểm tra quyền truy cập hoặc thay thế quy tắc nghiệp vụ. Nếu cần thay đổi dữ liệu được lưu, hãy dùng service, repository hoặc lifecycle hook phù hợp.

Nếu cần thay đổi toàn bộ cấu trúc JSON thay vì chỉ bổ sung hypermedia, hãy xem xét custom Jackson serializer/deserializer hoặc converter. Đây là thay đổi sâu hơn: converter tùy chỉnh phải giữ đúng cách Spring Data REST xử lý liên kết tới repository resource.

## 4. Xử lý vòng đời bằng repository REST events và listener

Spring Data REST phát ra các event khi REST exporter thao tác với entity. Có hai cách thường dùng để lắng nghe.

### 4.1. Annotated event handler

Dùng `@RepositoryEventHandler` để khai báo handler theo domain type. Các annotation trên method xác định thời điểm handler được gọi.

Ví dụ kiểm tra dữ liệu trước khi tạo/lưu và ghi nhận sau khi lưu:

~~~java
import org.springframework.data.rest.core.annotation.HandleAfterSave;
import org.springframework.data.rest.core.annotation.HandleBeforeCreate;
import org.springframework.data.rest.core.annotation.HandleBeforeSave;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.stereotype.Component;

@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        validatePerson(person);
    }

    @HandleBeforeSave
    public void beforeSave(Person person) {
        validatePerson(person);
    }

    @HandleAfterSave
    public void afterSave(Person person) {
        // Ghi nhận thao tác lưu hoặc cập nhật trạng thái phụ trợ.
    }

    private void validatePerson(Person person) {
        if (person.getFirstName() == null
                || person.getFirstName().isBlank()) {
            throw new IllegalArgumentException("firstName is required");
        }
    }
}
~~~

`@RepositoryEventHandler(Person.class)` giới hạn handler cho loại entity Person. Nếu không truyền class, loại entity được xác định từ tham số đầu tiên của các method được đánh dấu.

Các event mà REST exporter công bố gồm:

| Event | Thời điểm |
|---|---|
| `BeforeCreateEvent` | Trước khi tạo entity mới |
| `AfterCreateEvent` | Sau khi tạo entity |
| `BeforeSaveEvent` | Trước khi lưu/cập nhật entity |
| `AfterSaveEvent` | Sau khi lưu/cập nhật entity |
| `BeforeLinkSaveEvent` | Trước khi lưu thay đổi liên kết |
| `AfterLinkSaveEvent` | Sau khi lưu thay đổi liên kết |
| `BeforeDeleteEvent` | Trước khi xóa entity |
| `AfterDeleteEvent` | Sau khi xóa entity |

Các annotation tương ứng thường dùng là `@HandleBeforeCreate`, `@HandleAfterCreate`, `@HandleBeforeSave`, `@HandleAfterSave`, `@HandleBeforeLinkSave`, `@HandleAfterLinkSave`, `@HandleBeforeDelete` và `@HandleAfterDelete`.

### 4.2. AbstractRepositoryEventListener

Nếu muốn xử lý tập trung nhiều loại entity hoặc muốn ghi đè callback theo event, có thể kế thừa `AbstractRepositoryEventListener`:

~~~java
import org.springframework.data.rest.core.event.AbstractRepositoryEventListener;
import org.springframework.stereotype.Component;

@Component
public class AuditRepositoryEventListener
        extends AbstractRepositoryEventListener<Object> {

    @Override
    protected void onBeforeSave(Object entity) {
        // Kiểm tra hoặc chuẩn bị dữ liệu trước khi lưu.
    }

    @Override
    protected void onAfterDelete(Object entity) {
        // Ghi nhận entity vừa bị xóa.
    }
}
~~~

Cách này có thể nhận nhiều loại entity; listener cần tự kiểm tra kiểu nếu logic chỉ áp dụng cho một số domain type. Với handler theo entity cụ thể, annotated event handler thường rõ ràng và an toàn kiểu hơn.

### 4.3. Giới hạn của REST events

Các event trên thuộc quy trình của Spring Data REST exporter. Không nên mặc định rằng mọi lời gọi `repository.save(...)` từ service, batch job hoặc code nội bộ đều phát ra cùng các REST events.

Spring application events mặc định được xử lý đồng bộ. Vì vậy, một handler chạy lâu có thể kéo dài request; exception phát sinh trong handler cũng có thể ảnh hưởng tới kết quả thao tác đang xử lý.

Dùng before-event cho kiểm tra hoặc chuẩn hóa phù hợp với luồng REST. Với quy tắc bất biến phải đúng cho mọi đường ghi dữ liệu, hãy đặt quy tắc trong domain/service layer hoặc validation dùng chung. Với việc gửi message tới hệ thống bên ngoài cần bảo đảm sau commit, hãy dùng cơ chế transaction-bound event hoặc transactional outbox phù hợp; không coi `@HandleAfterSave` là cam kết rằng transaction đã commit thành công.

## 5. Thêm endpoint hoặc thay response bằng Controller

Dùng `@RepositoryRestController` khi cần endpoint tùy chỉnh gắn với không gian URI của một repository hoặc cần thay handler cho một resource cụ thể.

Ví dụ thêm endpoint tổng hợp những Person đang hoạt động:

~~~java
import java.util.List;

import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;

@RepositoryRestController
public class PersonSearchController {

    private final PersonRepository repository;

    public PersonSearchController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/people/search/active-summary")
    public ResponseEntity<CollectionModel<EntityModel<Person>>> activeSummary() {
        List<EntityModel<Person>> people = repository.findByActiveTrue()
                .stream()
                .map(EntityModel::of)
                .toList();

        return ResponseEntity.ok(CollectionModel.of(people));
    }
}
~~~

Trong ví dụ, `/people/search/active-summary` là endpoint tùy chỉnh nằm dưới base path của Spring Data REST. Repository cung cấp dữ liệu; controller thực hiện việc tổng hợp và trả về `CollectionModel` chứa các `EntityModel`.

Khi trả về collection, dùng `CollectionModel<T>`; khi trả về một tài nguyên, dùng `EntityModel<T>` hoặc `RepresentationModel<T>`. Nếu client cần điều hướng theo hypermedia, hãy thêm self link và link cho từng item bằng Spring HATEOAS hoặc `RepositoryEntityLinks`.

### 5.1. RepositoryRestController hay BasePathAwareController?

Hai annotation phục vụ hai phạm vi khác nhau:

- **`@RepositoryRestController`:** dùng cho handler gắn với URI space của repository. Controller được tích hợp với cấu hình, message converter, exception handling và một số xử lý của Spring Data REST. Request mapping chỉ được xử lý khi phù hợp với URI space mà repository export sử dụng.
- **`@BasePathAwareController`:** dùng cho endpoint tùy chỉnh nằm dưới base path nhưng không gắn với một repository cụ thể, chẳng hạn một resource hoặc MVC view dùng chung.

Nếu dùng `@Controller` hoặc `@RestController` thông thường, handler nằm ngoài phạm vi tích hợp của Spring Data REST. Khi đó, không nên giả định nó tự nhận cùng message converter, exception handling, CORS hay cách ánh xạ base path như repository endpoints.

Đặt route tùy chỉnh sao cho không xung đột với collection, item hoặc search resource đã được exporter tạo ra. Hãy kiểm tra URL thực tế sau khi áp dụng base path và các mapping repository.

## 6. Phân biệt Controller với processor và event handler

Ba điểm mở rộng này có thể cùng làm việc với một domain type, nhưng thời điểm và trách nhiệm khác nhau:

| Tiêu chí | RepresentationModelProcessor | REST event handler/listener | RepositoryRestController |
|---|---|---|---|
| Thời điểm | Khi tạo representation trả về | Trong vòng đời thao tác REST | Khi xử lý HTTP request khớp mapping |
| Đầu vào chính | Representation model | Entity và event | Request, tham số, repository/service |
| Kết quả | Representation được bổ sung link/metadata | Validation, audit hoặc side effect theo event | HTTP response tùy chỉnh |
| Có tự tạo endpoint? | Không | Không | Có |
| Nên dùng cho | Enrich hypermedia | Xử lý trước/sau thao tác | Luồng REST riêng hoặc response riêng |

Ví dụ, khi client gọi `GET /people/42`:

1. Repository lấy Person.
2. Spring Data REST tạo representation.
3. Processor có thể thêm link `documentation` vào response.
4. Response được serialize và gửi về client.

Khi client gọi `POST /people`:

1. REST exporter chuyển request body thành entity.
2. Event `BeforeCreateEvent` được phát ra và handler có thể kiểm tra dữ liệu.
3. Repository lưu entity.
4. Event `AfterCreateEvent` được phát ra.
5. REST exporter tạo response; processor tương ứng có thể bổ sung link.

Khi nghiệp vụ cần một endpoint `POST /people/{id}/activate` có quy trình riêng, controller có thể nhận request, gọi service xử lý và trả về representation phù hợp.

## 7. Ví dụ chọn điểm mở rộng theo tình huống

**Tình huống A — Mọi repository cần dùng base path `/api` và giới hạn trang tối đa 100.**

Dùng `RepositoryRestConfigurer` hoặc Spring Boot properties. Đây là cấu hình của REST exporter, không phải logic riêng của Person.

**Tình huống B — Mọi response Person cần có link tới tài liệu.**

Dùng `RepresentationModelProcessor<EntityModel<Person>>`. Processor chỉ bổ sung link vào representation hiện có.

**Tình huống C — Không cho phép tạo Person thiếu tên qua REST và cần ghi nhận sau khi lưu.**

Dùng `@RepositoryEventHandler(Person.class)` với `@HandleBeforeCreate` và `@HandleAfterSave`. Nếu cùng quy tắc phải áp dụng cho batch hoặc service, chuyển validation cốt lõi xuống tầng domain/service.

**Tình huống D — Cần endpoint tổng hợp nhiều repository hoặc quy trình kích hoạt phức tạp.**

Dùng `@RepositoryRestController` nếu endpoint thuộc URI space của repository; dùng `@BasePathAwareController` nếu endpoint chỉ cần nằm dưới base path. Đưa nghiệp vụ vào service để controller chỉ điều phối HTTP.

**Tình huống E — Cần đổi cách ánh xạ một thuộc tính domain sang JSON.**

Xem xét Jackson serializer/deserializer hoặc converter thông qua configurer. Processor chỉ nên dùng để thay đổi representation model/hypermedia; không phải công cụ chính để kiểm soát serialization của mọi trường.

## 8. Các lỗi thường gặp khi mở rộng Spring Data REST

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Configurer không có tác dụng | Bean không được component scan hoặc không được đăng ký trong ApplicationContext; kiểm tra cấu hình auto-configuration và thứ tự configurer. |
| Thay đổi cấu hình chỉ áp dụng một số repository | Quy tắc đang được giới hạn theo domain type hoặc repository exposure; kiểm tra scope của cấu hình. |
| Processor không được gọi | Kiểm tra generic type `EntityModel<T>`, loại entity và bean registration. |
| Link xuất hiện với URI sai host hoặc sai base path | Link được hard-code; dùng Spring HATEOAS link builder hoặc `RepositoryEntityLinks`. |
| Event handler không chạy | Bean chưa được đăng ký, thiếu `@RepositoryEventHandler`, method annotation không đúng event hoặc thao tác không đi qua REST exporter. |
| Handler nhận entity không đúng loại | Kiểm tra tham số đầu tiên của handler method và `@RepositoryEventHandler(DomainType.class)`. |
| Event handler làm request chậm | Logic đồng bộ tốn thời gian; chuyển công việc dài sang cơ chế xử lý nền phù hợp và kiểm soát transaction. |
| Custom controller trả về JSON thiếu HAL links | Response chưa được bọc bằng `EntityModel`/`CollectionModel` hoặc chưa thêm các link cần thiết. |
| Controller không được gọi | Kiểm tra annotation controller, base path, request mapping và xung đột với URI của repository đã export. |
| Endpoint chạy nhưng không có tích hợp Spring Data REST mong đợi | Kiểm tra đang dùng `@RepositoryRestController`, `@BasePathAwareController` hay controller MVC thông thường. |

## Ghi nhớ

Hãy chọn extension point theo trách nhiệm: **Configurer** thay đổi cấu hình exporter; **RepresentationModelProcessor** làm giàu hypermedia representation; **event handler/listener** phản ứng với vòng đời thao tác REST; **Controller** tạo endpoint hoặc response riêng. Đặt validation nghiệp vụ cốt lõi ở domain/service để mọi đường gọi đều tuân thủ. Khi tùy chỉnh sâu serialization, hãy giữ nguyên cơ chế chuyển đổi liên kết của Spring Data REST hoặc chủ động thay thế đầy đủ với hiểu biết về tác động.

## Tài liệu tham khảo

- [Spring Data REST — Getting Started and Configuration](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Data REST — Customizing the JSON Output](https://docs.spring.io/spring-data/rest/reference/customizing/customizing-json-output.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST — Overriding Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
