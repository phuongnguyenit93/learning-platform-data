# Nhận diện và khắc phục công bố quá mức, logic nghiệp vụ trong listener và URL ghép cứng

## Mục tiêu

Khi ứng dụng Spring Data REST phát triển, một số quyết định ban đầu có thể tạo ra rủi ro bảo trì và bảo mật:

- **Công bố quá mức:** repository, association hoặc thuộc tính được export rộng hơn nhu cầu của API.
- **Logic nghiệp vụ trong listener:** quy tắc quan trọng chỉ chạy khi request đi qua Spring Data REST repository event pipeline.
- **URL ghép cứng:** controller hoặc client tự nối chuỗi path/host, khiến API dễ hỏng khi đổi base path, resource mapping, proxy hoặc version.

Cách khắc phục là xác định rõ bề mặt API được phép công bố, đặt invariant ở application/domain layer và dùng hypermedia links hoặc link builder thay cho URL string tự ghép.

## 1. Nhận diện công bố quá mức

Spring Data REST có thể tự tạo collection resource, item resource, search resource và association links từ repository/domain model được export. Đây là cách nhanh để có CRUD API, nhưng cũng có thể công bố nhiều thao tác hơn mức sản phẩm thực sự cần.

Các dấu hiệu cần xem xét:

- Repository nội bộ xuất hiện trong root resource dù client không cần truy cập.
- API cho phép POST/PUT/PATCH/DELETE trên resource chỉ nên đọc.
- Search method nội bộ được công bố dưới `/search`.
- Association link cho phép client thay đổi quan hệ mà nghiệp vụ không cho phép.
- Entity response chứa field nội bộ, dữ liệu nhạy cảm hoặc thông tin quản trị.
- Client có thể gọi URI trực tiếp dù giao diện không hiển thị link.

Đừng đánh giá exposure chỉ bằng danh sách link mà frontend đang hiển thị. Hãy kiểm tra root resource, profile, search resource, association resource và khả năng gọi trực tiếp từng HTTP method.

## 2. Chỉ export repository cần thiết

Có thể tắt export ở cấp repository bằng `@RepositoryRestResource(exported = false)`:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
~~~

Repository vẫn có thể được inject và sử dụng nội bộ trong service. Annotation này ngăn Spring Data REST công bố repository như REST resource.

Nếu ứng dụng có nhiều repository, có thể chuyển sang chiến lược chỉ phát hiện repository được đánh dấu rõ ràng:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setRepositoryDetectionStrategy(
            RepositoryDetectionStrategies.ANNOTATED
        );
    }
}
~~~

Khi dùng chiến lược `ANNOTATED`, chỉ repository được annotate theo quy ước mới được export. Cần rà soát các repository hiện có và đánh dấu tường minh những resource thực sự là public API; nếu không, endpoint hợp lệ có thể biến mất sau khi đổi strategy.

Một phương án khác là giữ strategy hiện tại nhưng đánh dấu `exported = false` cho repository nội bộ. Chọn cách phù hợp với quy mô và cách quản lý API của ứng dụng.

## 3. Giới hạn query method và association

Không phải mọi finder method đều cần trở thành HTTP endpoint. Có thể tắt export cho một query method:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(exported = false)
    List<Person> findByInternalReviewStatus(String status);
}
~~~

Method vẫn có thể được gọi từ Java code nội bộ thông qua repository, nhưng Spring Data REST không công bố link search cho method đó.

Association cũng là một phần bề mặt API. Nếu client không được phép thay đổi quan hệ, có thể tắt export của association bằng cấu hình/annotation phù hợp với domain mapping:

~~~java
@ManyToOne
@RestResource(exported = false)
private Department department;
~~~

Cú pháp và vị trí annotation cần phù hợp với loại association và phiên bản Spring Data REST đang dùng. Sau khi cấu hình, kiểm tra cả representation item lẫn association resource; đừng giả định chỉ ẩn field trong JSON là đã khóa endpoint liên kết.

## 4. Projection không thay thế giới hạn truy cập

Projection và excerpt giúp kiểm soát hình dạng response:

~~~java
@Projection(name = "publicSummary", types = Person.class)
public interface PersonPublicSummary {

    String getFirstName();

    String getLastName();
}
~~~

Có thể cấu hình excerpt projection trên repository:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonPublicSummary.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Projection có thể giảm số field được serialize cho một representation, nhưng không tự quyết định ai được đọc resource hoặc ai được ghi field. Client có thể gọi endpoint khác hoặc gửi payload trực tiếp.

Với dữ liệu nhạy cảm, hãy kết hợp:

- DTO/response model chỉ chứa field được phép công khai.
- Security policy kiểm tra quyền đọc theo principal và resource.
- Write DTO/command chỉ nhận field mà use case cho phép.
- Kiểm thử request trực tiếp, không chỉ kiểm tra giao diện hoặc projection.

Không dùng projection làm hàng rào bảo mật duy nhất.

## 5. Tách ba lớp: representation, authorization và business rules

Khi xem xét một field hoặc thao tác, hãy hỏi ba câu riêng:

| Trách nhiệm | Câu hỏi | Cơ chế phù hợp |
|---|---|---|
| Representation | Client được nhìn thấy field/link nào? | Projection, DTO, assembler, resource mapping |
| Authorization | Principal này được phép làm gì trên resource này? | Spring Security, method security, ownership/tenant policy |
| Business rules | Thay đổi có hợp lệ theo trạng thái và invariant domain không? | Application service, domain method, transaction |

Ví dụ, field `salary` không xuất hiện trong projection public chỉ giải quyết representation. Quyền xem salary cần authorization. Việc cập nhật salary phải được kiểm tra theo quy tắc nghiệp vụ và quyền của người sửa.

Tương tự, ẩn link DELETE không đủ bảo vệ thao tác xóa. Server phải từ chối request trực tiếp nếu principal không có quyền hoặc entity đang ở trạng thái không thể xóa.

## 6. Bảo vệ endpoint bằng Spring Security

URL-level rule là lớp bảo vệ đầu tiên cho HTTP method và path:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/people/**")
                .hasAuthority("people:read")
            .requestMatchers(HttpMethod.POST, "/api/people")
                .hasAuthority("people:create")
            .requestMatchers(HttpMethod.PUT, "/api/people/**")
                .hasAuthority("people:update")
            .requestMatchers(HttpMethod.PATCH, "/api/people/**")
                .hasAuthority("people:update")
            .requestMatchers(HttpMethod.DELETE, "/api/people/**")
                .hasAuthority("people:delete")
            .anyRequest().authenticated()
        )
        .build();
}
~~~

Các matcher phải khớp base path, method và cấu trúc endpoint thực tế. Khi thay đổi `spring.data.rest.base-path`, context path hoặc reverse proxy, hãy rà soát lại rule và integration tests.

Quyền còn có thể phụ thuộc bản ghi hoặc tenant. Khi đó, kiểm tra ở service bằng method security:

~~~java
@Service
public class PersonService {

    @PreAuthorize("@personAccess.canUpdate(authentication, #personId)")
    public Person update(Long personId, UpdatePersonCommand command) {
        // Load the authorized Person and apply permitted changes.
        return null;
    }
}
~~~

Bean `personAccess` cần kiểm tra ownership/tenant theo dữ liệu thực tế. Chỉ kiểm tra authority chung như `people:update` có thể chưa đủ để cho phép sửa mọi Person.

Ẩn link trong HAL có thể cải thiện trải nghiệm, nhưng mọi request vẫn phải được authorization ở server. Không dựa vào frontend hoặc metadata để enforce quyền.

## 7. Nhận diện logic nghiệp vụ bị đặt trong repository event listener

Spring Data REST repository event handler hữu ích cho logic gắn với vòng đời HTTP repository resource. Ví dụ:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        person.setFirstName(person.getFirstName().trim());
    }

    @HandleBeforeSave
    public void beforeSave(Person person) {
        person.setLastName(person.getLastName().trim());
    }
}
~~~

Các listener kiểu này có thể phù hợp cho thao tác mỏng gắn với REST boundary, chẳng hạn chuẩn hóa dữ liệu đầu vào hoặc gọi một application service.

Nhưng nếu listener chứa toàn bộ workflow hoặc invariant, ứng dụng sẽ gặp các vấn đề:

- Logic chỉ chạy khi thao tác đi qua Spring Data REST event pipeline.
- Batch job, message consumer hoặc service khác có thể ghi repository mà không kích hoạt cùng handler.
- Quy tắc bị ẩn khỏi use case chính và khó tìm khi debug.
- Thứ tự nhiều listener có thể làm kết quả phụ thuộc vào registration/order.
- Side effect như gửi email hoặc gọi HTTP có thể không nhất quán với transaction database.
- Unit test domain phải khởi tạo event handler thay vì kiểm tra service/use case.

Dấu hiệu thường thấy là listener chứa nhiều truy vấn repository, chuyển trạng thái, kiểm tra quyền, tính giá, tạo đơn hàng, gửi message hoặc gọi nhiều service để hoàn thành một workflow.

## 8. Đưa invariant vào application service hoặc domain model

Quy tắc cần đúng với mọi entry point nên nằm ở application service/domain layer. Listener chỉ nên là adapter mỏng nếu vẫn cần tích hợp với Spring Data REST.

Ví dụ service thực hiện use case:

~~~java
@Service
public class PersonApplicationService {

    private final PersonRepository repository;

    public PersonApplicationService(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Person create(CreatePersonCommand command) {
        Person person = new Person();
        person.setFirstName(normalize(command.firstName()));
        person.setLastName(normalize(command.lastName()));

        validateNewPerson(person);
        return repository.save(person);
    }

    private String normalize(String value) {
        return value == null ? null : value.trim();
    }

    private void validateNewPerson(Person person) {
        if (person.getFirstName() == null
                || person.getFirstName().isBlank()) {
            throw new IllegalArgumentException("First name is required");
        }
    }
}
~~~

Service là nơi điều phối transaction, validation nghiệp vụ và lưu dữ liệu. Domain method có thể giữ invariant cục bộ của entity/aggregate; application service điều phối nhiều repository hoặc hệ thống.

Nếu Spring Data REST vẫn cần event handler, hãy để handler ủy quyền cho logic dùng chung khi phù hợp:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    private final PersonRestAdapter restAdapter;

    public PersonEventHandler(PersonRestAdapter restAdapter) {
        this.restAdapter = restAdapter;
    }

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        restAdapter.prepareForCreate(person);
    }
}
~~~

Adapter này nên gọi logic có thể tái sử dụng và tránh tự thực hiện một workflow riêng. Không gọi `repository.save(person)` lại trên chính object đang được xử lý trong before-save listener; việc đó có thể gây vòng lặp hoặc tạo side effect khó đoán.

## 9. Phân biệt listener, validation và domain event

Ba cơ chế thường bị trộn lẫn:

| Cơ chế | Vai trò |
|---|---|
| Spring Data REST repository event handler | Hook vào lifecycle request qua repository REST |
| Spring Validator/Bean Validation | Kiểm tra dữ liệu và ghi nhận lỗi validation |
| Domain/application event | Thông báo một sự kiện nghiệp vụ đã xảy ra để các thành phần khác xử lý |

Ví dụ:

- Chuẩn hóa tên từ request có thể ở adapter/service.
- Kiểm tra field bắt buộc thuộc validation.
- Kiểm tra chuyển trạng thái Person có hợp lệ hay không thuộc domain/business rule.
- Thông báo `PersonCreated` cho hệ thống khác là application/domain event.

Không dùng `@HandleAfterCreate` làm nơi duy nhất để phát mọi thông báo nghiệp vụ nếu Person cũng có thể được tạo từ batch hoặc message consumer. Hãy phát domain/application event từ use case dùng chung.

## 10. Xử lý side effect và transaction

Một listener chạy sau thao tác repository không tự bảo đảm side effect bên ngoài đã được commit cùng database.

Ví dụ gửi email ngay trong `@HandleAfterSave` có thể tạo tình huống email đã gửi nhưng transaction database rollback. Ngược lại, database đã commit nhưng lời gọi hệ thống ngoài thất bại.

Các lựa chọn tùy yêu cầu:

- Dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` cho xử lý chỉ chạy sau khi transaction commit.
- Dùng transactional outbox khi cần bảo đảm event được ghi cùng transaction và worker có thể retry.
- Thiết kế consumer idempotent để xử lý message lặp.
- Ghi log/correlation ID để truy vết lỗi và retry.

Không giả định callback after-save luôn tương đương after-commit. Xác nhận transaction boundary thực tế trước khi đặt side effect.

## 11. Nhận diện URL ghép cứng

URL ghép cứng xuất hiện khi code tự nối host, base path, plural name hoặc identifier:

~~~java
String url = "https://api.example.com/api/people/" + person.getId();
~~~

Hoặc client tự tạo path:

~~~javascript
const url = baseUrl + "/api/people/" + personId;
~~~

Các chuỗi này có thể hỏng khi:

- Đổi host giữa local, staging và production.
- Đổi `spring.data.rest.base-path` hoặc servlet context path.
- Đổi repository path qua `@RepositoryRestResource(path = "...")`.
- Thêm reverse proxy hoặc API gateway prefix.
- Đổi pluralization hoặc resource naming.
- Thay đổi version prefix.
- Chuyển endpoint sang một route tùy chỉnh.

URL ghép cứng cũng khiến client phụ thuộc cấu trúc triển khai thay vì relation mà server công bố.

## 12. Dùng hypermedia links thay vì tự ghép URL

Với HAL, client nên bắt đầu từ entry point đã biết, sau đó theo relation trong `_links`:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/people/42"
    },
    "people": {
      "href": "https://api.example.com/api/people"
    }
  }
}
~~~

Client dùng URI từ `self` hoặc relation tương ứng thay vì dựng lại `/api/people/{id}`. Với search resource, theo link `search` rồi chọn relation của query method. Với association, theo link association mà server trả.

Trong server-side controller, dùng Spring HATEOAS link builder cho route của ứng dụng:

~~~java
Link personLink = linkTo(
        methodOn(PersonController.class).getPerson(personId)
    ).withSelfRel();
~~~

Với Spring Data REST repository resource, ưu tiên infrastructure link/entity assembler phù hợp với mapping đã cấu hình. Không giả định tên collection hoặc base path luôn là `/api/people`.

### Tạo Location cho resource mới

Khi custom endpoint tạo resource, tạo URI từ link builder:

~~~java
URI location = linkTo(
        methodOn(PersonController.class).getPerson(saved.getId())
    ).toUri();

return ResponseEntity.created(location).body(response);
~~~

Cách này gắn URI với mapping controller thay vì chuỗi literal. Nếu endpoint trả resource Spring Data REST, dùng link builder/EntityLinks tương ứng với resource mapping của ứng dụng.

## 13. Khi nào URL string vẫn phù hợp?

Không phải mọi URL đều có thể loại bỏ khỏi cấu hình. Một số địa chỉ là external service endpoint hoặc callback URL do môi trường triển khai cung cấp.

Trong trường hợp đó:

- Đưa host/base URL vào configuration hoặc environment variable.
- Không hard-code URL production trong source.
- Dùng URI builder để encode path/query parameters.
- Validate scheme/host nếu URL được người dùng cung cấp.
- Không tự nối query string khi giá trị có ký tự đặc biệt.
- Dùng hypermedia links cho resource nội bộ của API khi server đã công bố chúng.

Ví dụ xây dựng URL có query parameter:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString(externalServiceBaseUrl)
        .path("/v1/people")
        .queryParam("status", status)
        .build()
        .encode()
        .toUri();
~~~

`externalServiceBaseUrl` lấy từ configuration; path và query cần phù hợp contract của external service. URI builder giúp encode giá trị đúng cách, nhưng không thay thế kiểm tra URL đầu vào nếu host đến từ dữ liệu không tin cậy.

## 14. Quy trình khắc phục theo từng bước

Khi rà soát một API Spring Data REST:

1. Liệt kê repository, finder method và association đang được export.
2. Xác định resource nào thực sự cần public; tắt export cho repository/method/association nội bộ.
3. Xem xét repository detection strategy để yêu cầu export tường minh nếu phù hợp.
4. Tách representation bằng projection/DTO và kiểm tra field nhạy cảm.
5. Kiểm tra URL-level, method-level và resource-level authorization.
6. Tìm `@RepositoryEventHandler` có chứa workflow hoặc invariant; chuyển logic dùng chung sang application service/domain.
7. Giữ listener mỏng và tránh side effect không có transaction/retry policy.
8. Tìm chuỗi URL literal trong source, template và client; thay bằng hypermedia relation, link builder hoặc configuration.
9. Kiểm tra `Location`, ETag, Cache-Control và các header khi custom endpoint tạo response.
10. Viết integration tests cho trực tiếp HTTP endpoint, kể cả request không đi qua giao diện.

## 15. Kiểm thử sau khi refactor

Các test cần chứng minh hành vi và contract đã được kiểm soát:

- **Exposure:** repository/method/association nội bộ không còn được export.
- **Read representation:** response public không chứa field nhạy cảm.
- **Authorization:** user thiếu quyền bị từ chối dù gọi URI trực tiếp.
- **Resource policy:** tenant/owner khác không thể truy cập hoặc sửa resource.
- **Business rules:** invariant vẫn chạy khi gọi từ REST, service, batch hoặc message entry point.
- **Listener:** listener chỉ làm nhiệm vụ adapter dự kiến và không lưu lặp.
- **Transaction:** rollback không để lại side effect ngoài hệ thống; retry có tính idempotent.
- **Links:** client vẫn theo được self/search/association links sau khi đổi base path hoặc resource path.
- **Location:** URI tạo mới đúng theo mapping hiện tại.
- **Environment:** staging/production dùng base URL từ cấu hình thay vì source literal.

Có thể dùng MockMvc/WebTestClient cho HTTP contract, unit test cho service/domain logic và integration test cho transaction/event pipeline.

## 16. Những nhầm lẫn thường gặp

- **Không hiện link nghĩa là endpoint không truy cập được.** Client có thể gọi URI trực tiếp; security phải chặn ở server.
- **Projection ẩn field nên field không thể bị ghi.** Projection chủ yếu định hình response; write contract và authorization cần bảo vệ riêng.
- **Listener là nơi thích hợp cho mọi nghiệp vụ.** Listener chỉ thuộc repository REST lifecycle; logic dùng chung cần ở service/domain.
- **After event luôn chạy sau commit.** Xác nhận transaction boundary; dùng AFTER_COMMIT/outbox khi cần.
- **Gọi repository.save trong before-save listener là vô hại.** Có thể gây gọi lặp hoặc vòng lặp lifecycle.
- **URL ghép cứng chỉ là vấn đề đổi host.** Base path, reverse proxy, repository mapping và versioning cũng có thể làm hỏng URL.
- **Dùng link builder là đủ cho mọi URL.** External service URL vẫn cần configuration và validation.
- **Chỉ tắt repository là đã khóa mọi dữ liệu.** Cần kiểm tra các controller, query method, association và đường truy cập khác.
- **Unit test listener chứng minh mọi entry point đều chạy logic.** Cần kiểm tra service/domain logic từ các entry point khác nhau.

## 17. Ghi nhớ

- Chỉ export repository, method và association thực sự thuộc API contract.
- Dùng `exported = false` và repository detection strategy để giới hạn bề mặt Spring Data REST.
- Projection/DTO kiểm soát representation; Spring Security và resource policy kiểm soát quyền.
- Đưa invariant và workflow dùng chung vào application service/domain model.
- Giữ repository event listener mỏng, tránh lưu lặp và side effect không có transaction policy.
- Dùng `@TransactionalEventListener(AFTER_COMMIT)` hoặc transactional outbox khi side effect cần gắn với commit.
- Theo HAL links từ server và dùng Spring HATEOAS link builder cho URL nội bộ.
- Lấy external base URL từ configuration và xây dựng URI bằng builder.
- Kiểm thử trực tiếp exposure, authorization, business rules, links, headers và transaction sau refactor.

## Tài liệu tham khảo

- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST Reference — Security](https://docs.spring.io/spring-data/rest/reference/security.html)
- [Spring HATEOAS Reference — Building links](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring Security Reference — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Spring Framework Reference — Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
