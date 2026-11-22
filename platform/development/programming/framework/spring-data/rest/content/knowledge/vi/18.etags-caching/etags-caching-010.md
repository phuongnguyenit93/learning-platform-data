# Phân biệt kiểm tra freshness bằng header và bộ nhớ đệm dữ liệu của ứng dụng

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt HTTP cache ở client/proxy với application cache ở phía server.
- Giải thích vai trò của **ETag**, **Last-Modified**, **If-None-Match** và **If-Modified-Since**.
- Hiểu response **304 Not Modified** và cách client tái sử dụng representation đã lưu.
- Cấu hình **Cache-Control** và **Vary** phù hợp cho HTTP representation.
- Nhận biết optimistic locking bằng **@Version** và **If-Match**.
- Dùng Spring Cache với **@Cacheable**, **@CachePut** và **@CacheEvict**.
- Thiết kế cache invalidation khi dữ liệu thay đổi qua service hoặc Spring Data REST.
- Tránh nhầm kiểm tra freshness với việc lưu dữ liệu trong cache của ứng dụng.

## 1. Hai lớp cache giải quyết hai vấn đề khác nhau

Khi một client gọi Spring Data REST, dữ liệu có thể được lưu ở nhiều nơi. Hai lớp thường gặp là:

**HTTP cache** lưu representation của response ở trình duyệt, reverse proxy hoặc CDN. Server điều khiển cách cache này bằng các HTTP response header như Cache-Control, ETag, Last-Modified và Vary. Client có thể hỏi server xem bản đã lưu còn mới không.

**Application cache** lưu kết quả xử lý hoặc dữ liệu ở phía server, thường trong bộ nhớ của ứng dụng hoặc một cache dùng chung như Redis. Spring Cache cung cấp abstraction để cache kết quả method và loại bỏ hoặc cập nhật entry khi dữ liệu thay đổi.

| Tiêu chí | HTTP cache / freshness | Application cache |
|---|---|---|
| Lưu ở đâu? | Browser, proxy, CDN hoặc HTTP client | Bộ nhớ server, Caffeine, Redis hoặc cache provider khác |
| Đối tượng lưu | HTTP representation và metadata | Kết quả method, DTO, dữ liệu hoặc object |
| Cơ chế chính | Cache-Control, ETag, Last-Modified, conditional request | @Cacheable, @CachePut, @CacheEvict |
| Kiểm tra còn mới? | Client gửi validator; server trả 304 hoặc representation mới | Ứng dụng dùng TTL, key, eviction hoặc refresh |
| Ai điều khiển? | HTTP server và cache tuân theo HTTP semantics | Code và cấu hình ứng dụng |
| Ví dụ | Browser giữ HAL JSON và gửi If-None-Match | Service giữ PersonDto theo ID trong Redis |

Hai lớp có thể hoạt động cùng lúc. Browser có thể giữ một response HTTP, trong khi server dùng Redis để lấy nhanh dữ liệu khi cần tạo response mới. Việc xóa entry Redis không tự xóa bản response trong browser; header HTTP cũng không tự xóa cache server.

## 2. Freshness và validation trong HTTP cache

HTTP cache có thể sử dụng hai cách để quyết định một response đã lưu có thể được tái sử dụng hay cần hỏi lại server:

1. **Freshness lifetime**: response còn mới theo thời gian được khai báo, ví dụ Cache-Control: max-age=60.
2. **Validation**: response đã hết thời gian fresh hoặc cần kiểm tra lại; client gửi validator như ETag hoặc Last-Modified.

Nếu response còn fresh, cache có thể trả lại ngay mà không cần gọi origin server. Nếu cần revalidate, cache gửi conditional request kèm validator. Server xác định representation có thay đổi hay không.

Ví dụ một response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Cache-Control: private, max-age=60
ETag: "person-42-v7"

{ "name": "Lan" }
~~~

Browser có thể lưu body cùng ETag. Khi response hết thời gian fresh, browser gửi:

~~~http
GET /api/people/42 HTTP/1.1
If-None-Match: "person-42-v7"
Accept: application/hal+json
~~~

Nếu representation vẫn tương ứng với ETag đó, server trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "person-42-v7"
Cache-Control: private, max-age=60
~~~

Response **304 Not Modified** không gửi lại body. Client dùng body đã lưu trước đó và cập nhật metadata cache theo response mới. 304 là kết quả bình thường của conditional GET, không phải lỗi.

Nếu representation đã thay đổi, server trả response mới, thường là **200 OK**, kèm body và validator mới.

## 3. ETag là validator của representation

**ETag** (Entity Tag) là một validator dạng chuỗi do server phát cho một representation. Client lưu giá trị này và gửi lại trong request tiếp theo để server so sánh.

Ví dụ:

~~~http
ETag: "person-42-v7"
~~~

ETag là opaque identifier: client không nên phân tích nội dung bên trong để suy ra version hay business data. Server quyết định cách tạo nó, chẳng hạn từ version của entity, checksum representation hoặc một mã phiên bản.

Có hai dạng:

- **Strong ETag**: không có tiền tố W/; dùng khi representation được xem là byte-for-byte tương đương theo quy tắc strong validator.
- **Weak ETag**: có tiền tố **W/**, ví dụ **W/"person-42-v7"**; cho biết representation tương đương về mặt ngữ nghĩa nhưng có thể khác byte.

Ví dụ:

~~~http
ETag: W/"person-42-v7"
~~~

Với conditional GET sử dụng If-None-Match, HTTP cho phép so sánh weak validator. Với các thao tác cần kiểm tra phiên bản chính xác như If-Match, strong comparison được yêu cầu; weak ETag không phù hợp để bảo đảm optimistic concurrency.

ETag phải thay đổi khi representation liên quan thay đổi theo cách mà validator cần phát hiện. Nếu response phụ thuộc vào projection, Accept, ngôn ngữ, quyền người dùng hoặc dữ liệu liên quan, cách tạo ETag phải tính đến những yếu tố có thể làm representation khác nhau. Không dùng cùng một ETag cho hai representation khác nhau chỉ vì chúng đến từ cùng một entity ID.

## 4. If-None-Match và conditional GET

**If-None-Match** cho client gửi lại một hoặc nhiều ETag mà nó đang giữ:

~~~http
If-None-Match: "person-42-v7"
~~~

Đối với GET hoặc HEAD:

- Nếu representation hiện tại khớp validator theo quy tắc weak comparison, server có thể trả **304 Not Modified**.
- Nếu không khớp, server trả representation mới, thường là **200 OK**.

Ví dụ kiểm tra bằng curl:

~~~bash
curl -i \
  -H 'Accept: application/hal+json' \
  -H 'If-None-Match: "person-42-v7"' \
  http://localhost:8080/api/people/42
~~~

Nếu cần kiểm tra nhiều ETag, header có thể chứa danh sách tag hoặc dấu **\*** theo cú pháp HTTP. Hãy để HTTP client xây dựng header đúng cú pháp; không tự so sánh chuỗi ETag ở client rồi bỏ qua server.

**If-None-Match** còn được dùng trong một số request ghi với ý nghĩa điều kiện không tồn tại/không khớp; khi điều kiện thất bại, server có thể trả **412 Precondition Failed**. Đối với bài học này, trường hợp quan trọng nhất là conditional GET để tái sử dụng response đã cache.

Nếu request có cả If-None-Match và If-Modified-Since, If-None-Match có mức ưu tiên cao hơn theo HTTP semantics. Server không nên bỏ qua ETag để chỉ dựa vào thời gian sửa đổi.

## 5. Last-Modified và If-Modified-Since

**Last-Modified** cho biết thời điểm representation được sửa lần cuối:

~~~http
Last-Modified: Tue, 10 Nov 2026 09:30:00 GMT
~~~

Client lưu giá trị này và gửi ở request sau:

~~~http
If-Modified-Since: Tue, 10 Nov 2026 09:30:00 GMT
~~~

Nếu representation không thay đổi kể từ thời điểm đó, server có thể trả 304. Nếu đã thay đổi, server trả body mới cùng Last-Modified mới.

Ví dụ:

~~~bash
curl -i \
  -H 'Accept: application/hal+json' \
  -H 'If-Modified-Since: Tue, 10 Nov 2026 09:30:00 GMT' \
  http://localhost:8080/api/people/42
~~~

Last-Modified dễ triển khai khi dữ liệu có timestamp cập nhật đáng tin cậy. Tuy nhiên, HTTP date có độ phân giải theo giây; nhiều lần cập nhật trong cùng một giây có thể khó phân biệt chỉ bằng thời gian. Đồng hồ server không chính xác hoặc timestamp không được cập nhật đúng cũng làm validator sai.

ETag thường chính xác và linh hoạt hơn vì có thể dựa trên version hoặc checksum. Ứng dụng có thể phát cả ETag và Last-Modified; khi client gửi cả hai validator, server phải tuân theo thứ tự ưu tiên của HTTP.

## 6. Cache-Control quyết định response được lưu và dùng lại thế nào

**Cache-Control** điều khiển chính sách cache cho response. Một số directive thường gặp:

| Directive | Ý nghĩa |
|---|---|
| **max-age=60** | Response được xem là fresh trong 60 giây kể từ thời điểm thích hợp theo HTTP caching rules |
| **private** | Chỉ private cache như browser được lưu; shared cache không được dùng response đó |
| **public** | Cho phép shared cache lưu response nếu các điều kiện khác của HTTP cho phép |
| **no-cache** | Có thể lưu response nhưng phải revalidate trước khi dùng lại |
| **no-store** | Không lưu response vào HTTP cache |
| **must-revalidate** | Khi đã stale, cache phải revalidate trước khi dùng lại |
| **s-maxage=120** | Freshness lifetime cho shared cache; ghi đè max-age ở shared cache |

Đặc biệt cần phân biệt:

- **no-cache** không có nghĩa là không lưu. Nó yêu cầu kiểm tra lại trước khi tái sử dụng.
- **no-store** yêu cầu cache không lưu response.
- **private** giới hạn nơi lưu vào private cache; nó không mã hóa dữ liệu và không thay thế authorization.

Ví dụ response cá nhân có thể dùng:

~~~http
Cache-Control: private, max-age=60
~~~

Một response chứa dữ liệu nhạy cảm mà chính sách yêu cầu không lưu có thể dùng:

~~~http
Cache-Control: no-store
~~~

Một response có thể lưu nhưng phải kiểm tra freshness trước khi dùng:

~~~http
Cache-Control: private, no-cache
ETag: "person-42-v7"
~~~

Chọn directive theo dữ liệu và rủi ro thực tế. Không đặt public cho response phụ thuộc người dùng đang đăng nhập nếu shared cache có thể phục vụ nhầm representation cho người khác.

## 7. Vary: phân biệt các biến thể response

Một URL có thể trả representation khác nhau tùy request header. Ví dụ client yêu cầu HAL hoặc JSON khác, hoặc server thay đổi nội dung theo ngôn ngữ.

Header **Vary** cho cache biết request header nào làm thay đổi representation:

~~~http
Vary: Accept, Accept-Language
~~~

Cache phải xem các giá trị Accept và Accept-Language khác nhau là những biến thể khác nhau của response cho cùng URL.

Nếu server phát HAL theo Accept, hãy kiểm tra response có Vary: Accept khi cần. Nếu response được cá nhân hóa theo cookie hoặc authorization, phải chọn chính sách cache phù hợp và không dựa riêng vào Vary để bảo vệ dữ liệu.

Vary không phải danh sách field trong body. Nó mô tả request header ảnh hưởng đến cách server tạo representation.

## 8. Freshness header trong Spring MVC

Với custom controller, Spring MVC cung cấp **WebRequest.checkNotModified(...)** để kiểm tra conditional request. Controller có thể tính ETag hoặc Last-Modified, rồi để Spring thiết lập trạng thái 304 khi validator vẫn hợp lệ.

Ví dụ:

~~~java
import java.time.Duration;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;

@RestController
public class PersonController {

    private final PersonService personService;

    public PersonController(PersonService personService) {
        this.personService = personService;
    }

    @GetMapping("/api/people/{id}")
    public ResponseEntity<PersonDto> getPerson(
            @PathVariable Long id,
            WebRequest request) {

        PersonDto person = personService.findById(id);

        String etag = "\"" + person.version() + "\"";
        long lastModified = person.updatedAt().toEpochMilli();

        if (request.checkNotModified(etag, lastModified)) {
            return null;
        }

        return ResponseEntity.ok()
            .eTag(etag)
            .lastModified(lastModified)
            .cacheControl(
                CacheControl.maxAge(Duration.ofSeconds(60)).cachePrivate()
            )
            .body(person);
    }
}
~~~

Đây là ví dụ minh họa cho custom MVC endpoint. **version()** và **updatedAt()** là các accessor giả định của DTO. Trong ứng dụng thật, ETag phải đại diện cho đúng representation và lastModified phải được lấy từ timestamp đáng tin cậy.

**checkNotModified** cần được gọi trước khi tạo hoặc serialize body tốn kém. Nếu request đã có validator phù hợp, Spring có thể kết thúc response với 304 mà không gửi body. Hãy kiểm tra hành vi trên phiên bản Spring MVC và servlet container đang dùng.

Không phải cứ thêm header ETag vào ResponseEntity là mọi request tự động được so sánh. Với custom controller, cần xử lý conditional request rõ ràng hoặc dùng cơ chế framework đã hỗ trợ.

## 9. Spring Data REST và optimistic locking bằng @Version

ETag còn có thể phục vụ mục đích khác: ngăn client ghi đè thay đổi mới hơn của người khác. Đây là **optimistic locking**.

Với JPA, khai báo version field:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @Version
    private Long version;
}
~~~

Version được persistence provider tăng khi entity được cập nhật. Spring Data REST có thể sử dụng version property để hỗ trợ optimistic locking và ETag cho item resource tùy cấu hình/phiên bản. Hãy đọc response thực tế để xác nhận ETag mà API đang phát.

Luồng minh họa:

~~~http
GET /api/people/42
Accept: application/hal+json
~~~

Response có ETag:

~~~http
ETag: "7"
~~~

Client sửa tài nguyên và gửi validator đã đọc:

~~~http
PUT /api/people/42
If-Match: "7"
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Lan Nguyen"
}
~~~

Nếu một client khác đã cập nhật entity và version hiện tại không còn khớp, server từ chối thao tác có điều kiện, thường bằng **412 Precondition Failed** hoặc lỗi optimistic locking theo cách framework ánh xạ.

Phân biệt hai chiều sử dụng ETag:

- **If-None-Match** trong GET: “Bản tôi đang giữ có còn mới không?” Nếu khớp, server trả 304.
- **If-Match** trong PUT/PATCH/DELETE: “Chỉ thực hiện nếu tài nguyên vẫn ở phiên bản tôi đã đọc.” Nếu không khớp, server từ chối để tránh lost update.

ETag có thể dùng cho cả cache validation và optimistic concurrency, nhưng ý nghĩa phụ thuộc request header. Không tự lấy ETag từ một response khác hoặc sửa chuỗi tag ở client.

## 10. Application cache trong Spring

Application cache lưu kết quả xử lý ở phía server. Spring Cache cung cấp annotation để đánh dấu method có thể cache, cập nhật cache hoặc loại bỏ entry.

Bật caching:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {
}
~~~

Ví dụ cache kết quả đọc Person:

~~~java
@Service
public class PersonQueryService {

    private final PersonRepository personRepository;

    public PersonQueryService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @Cacheable(cacheNames = "peopleById", key = "#id")
    public PersonDto findById(Long id) {
        Person person = personRepository.findById(id)
            .orElseThrow();

        return PersonDto.from(person);
    }
}
~~~

Khi gọi **findById(42)** lần đầu, method chạy và kết quả được lưu theo key 42. Những lần gọi tiếp theo có thể lấy kết quả từ cache mà không thực hiện lại truy vấn bên trong method.

**@Cacheable** không tạo HTTP ETag, không thêm Cache-Control và không làm browser trả 304. Nó chỉ tác động đến việc thực thi method phía server.

Spring Boot có thể tự cấu hình cache provider phù hợp với dependency có trong ứng dụng. Caffeine thường phù hợp với cache local trong một process; Redis phù hợp khi nhiều instance cần chia sẻ cache. Cần cấu hình TTL, dung lượng, serialization và chính sách eviction theo provider đang dùng.

## 11. @CacheEvict và @CachePut khi dữ liệu thay đổi

Cache chỉ hữu ích khi ứng dụng có chiến lược cập nhật hoặc loại bỏ entry cũ.

### Xóa entry sau khi cập nhật

~~~java
@Service
public class PersonCommandService {

    private final PersonRepository personRepository;

    public PersonCommandService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @CacheEvict(cacheNames = "peopleById", key = "#id")
    @Transactional
    public Person update(Long id, PersonUpdateRequest request) {
        Person person = personRepository.findById(id)
            .orElseThrow();

        person.setName(request.name());
        return personRepository.save(person);
    }
}
~~~

Sau khi method cập nhật thành công, entry có key tương ứng bị xóa. Lần đọc tiếp theo sẽ tải dữ liệu mới và điền lại cache.

### Xóa cache danh sách và truy vấn

Nếu cache thêm kết quả tìm kiếm hoặc collection, cập nhật một Person có thể làm thay đổi nhiều kết quả. Có thể dùng:

~~~java
@Caching(evict = {
    @CacheEvict(cacheNames = "peopleById", key = "#id"),
    @CacheEvict(cacheNames = "peopleSearch", allEntries = true)
})
@Transactional
public Person update(Long id, PersonUpdateRequest request) {
    // Tải, sửa và lưu Person.
}
~~~

**@CachePut** có thể cập nhật entry bằng kết quả method thay vì xóa:

~~~java
@CachePut(cacheNames = "peopleById", key = "#result.id")
public PersonDto updateAndReturn(PersonUpdateRequest request) {
    // Cập nhật dữ liệu và trả về DTO đầy đủ.
}
~~~

Chỉ dùng **@CachePut** khi chắc chắn kết quả method là representation đầy đủ và đúng với key. Với các cache phụ thuộc query, filter, sort hoặc quyền người dùng, xóa các entry liên quan thường an toàn hơn việc tự cập nhật từng biến thể.

## 12. Ranh giới transaction và cache invalidation

Cache invalidation phải đồng bộ với thời điểm dữ liệu được commit.

Nếu xóa cache quá sớm, một request khác có thể đọc dữ liệu cũ từ database rồi nạp lại vào cache trước khi transaction cập nhật commit. Nếu transaction rollback sau khi cache đã bị xóa, hệ thống có thể phải tải lại dữ liệu dù dữ liệu thực tế không đổi; việc đó thường an toàn nhưng gây cache miss không cần thiết.

Với use case cần kiểm soát chặt chẽ, có thể phát domain event trong transaction và chỉ xóa cache sau commit:

~~~java
public record PersonChanged(Long personId) {
}
~~~

~~~java
@Service
public class PersonCommandService {

    private final PersonRepository repository;
    private final ApplicationEventPublisher events;

    public PersonCommandService(
            PersonRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public Person update(Long id, PersonUpdateRequest request) {
        Person person = repository.findById(id).orElseThrow();
        person.setName(request.name());

        Person saved = repository.save(person);
        events.publishEvent(new PersonChanged(saved.getId()));
        return saved;
    }
}
~~~

~~~java
@Component
public class PersonCacheInvalidator {

    private final CacheManager cacheManager;

    public PersonCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterPersonChanged(PersonChanged event) {
        Cache byId = cacheManager.getCache("peopleById");
        if (byId != null) {
            byId.evict(event.personId());
        }

        Cache searches = cacheManager.getCache("peopleSearch");
        if (searches != null) {
            searches.clear();
        }
    }
}
~~~

Listener chỉ chạy sau khi transaction chứa event commit thành công. Nếu transaction rollback, cache không bị xóa bởi listener này. Ví dụ cần import các type Spring Cache, transaction event và event publisher tương ứng.

Spring Data REST mặc định gọi repository trực tiếp cho các repository resource. Nếu cache được đặt trong một service mà REST exporter không gọi, annotation **@CacheEvict** trên service đó sẽ không chạy khi client ghi qua endpoint repository mặc định.

Nếu ứng dụng cho phép ghi qua cả service và Spring Data REST endpoint, phải có một chiến lược invalidation bao phủ mọi đường ghi. Có thể dùng custom endpoint gọi command service, đặt cache policy ở repository/event integration thích hợp, hoặc xử lý repository event với cơ chế đồng bộ sau commit phù hợp phiên bản. Không giả định một event AfterSave luôn đồng nghĩa transaction đã commit; hãy xác minh lifecycle và transaction thực tế.

## 13. Những dữ liệu nào nên cache?

Cache các kết quả đọc lặp lại, tương đối ổn định và có key rõ ràng. Ví dụ:

- DTO chi tiết theo ID.
- Danh mục ít thay đổi.
- Cấu hình hoặc metadata công khai.
- Kết quả tìm kiếm phổ biến có TTL ngắn và chính sách invalidation rõ ràng.

Cần thận trọng với:

- Entity JPA có lazy association hoặc persistence context state.
- Collection có nhiều biến thể filter, sort, page và projection.
- Dữ liệu phụ thuộc tenant, user, role hoặc quyền truy cập.
- Số dư, tồn kho hoặc trạng thái cần freshness cao.
- Kết quả chứa dữ liệu cá nhân hoặc bí mật.

Thường nên cache DTO bất biến hoặc dữ liệu đã tách khỏi persistence context thay vì giữ entity JPA sống lâu trong cache. Key phải bao gồm mọi yếu tố làm thay đổi kết quả, ví dụ tenant ID, locale hoặc loại projection. Không dùng chung key chỉ theo ID nếu cùng ID có thể được nhìn thấy khác nhau theo người dùng.

## 14. HTTP cache và application cache phối hợp thế nào?

Một request có thể đi qua cả hai lớp:

1. Browser kiểm tra bản HTTP response đã lưu.
2. Nếu bản còn fresh, browser trả dữ liệu từ cache mà không gọi server.
3. Nếu cần revalidate, browser gửi If-None-Match hoặc If-Modified-Since.
4. Server xác định ETag/Last-Modified hiện tại.
5. Để tạo representation mới hoặc tính validator, server có thể đọc dữ liệu từ application cache.
6. Nếu validator khớp, server trả 304; nếu không, trả 200 cùng body mới.
7. Browser cập nhật HTTP cache theo Cache-Control và validator mới.

Ví dụ, Redis có thể cache PersonDto trong 5 phút, còn browser cache response trong 30 giây. Hai TTL không cần giống nhau vì chúng quản lý hai lớp khác nhau. Nhưng khi Person thay đổi, ứng dụng cần invalidation Redis và response HTTP tiếp theo phải phát validator/chính sách freshness phản ánh dữ liệu mới.

Không được cho rằng Redis đã xóa thì browser tự biết. Browser chỉ biết response thay đổi khi hết freshness, revalidate, bị purge bởi cơ chế ngoài hoặc nhận request mới theo chính sách HTTP.

Ngược lại, đặt **Cache-Control: no-store** không ngăn server dùng Caffeine hoặc Redis. Nó chỉ điều khiển HTTP cache, không phải application cache.

## 15. Kiểm tra freshness và application cache

Khi debug, hãy kiểm tra riêng hai lớp.

### Kiểm tra HTTP cache

1. Gọi GET và lưu ETag, Last-Modified, Cache-Control, Vary.
2. Gọi lại với If-None-Match.
3. Xác nhận 304 không có response body khi representation chưa đổi.
4. Thay đổi dữ liệu rồi gọi lại với ETag cũ.
5. Xác nhận server trả representation mới và validator mới.
6. Kiểm tra response có phân biệt representation theo Accept hoặc người dùng hay không.

Ví dụ:

~~~bash
curl -i \
  -H 'Accept: application/hal+json' \
  -H 'If-None-Match: "person-42-v7"' \
  http://localhost:8080/api/people/42
~~~

### Kiểm tra application cache

1. Gọi service method lần đầu và xác nhận truy vấn repository được thực hiện.
2. Gọi lại cùng cache key và xác nhận kết quả được lấy từ cache.
3. Cập nhật dữ liệu qua từng đường ghi mà ứng dụng hỗ trợ.
4. Xác nhận key item và các cache query liên quan được evict hoặc refresh.
5. Kiểm tra cache local và distributed khi chạy nhiều instance.
6. Kiểm tra rollback không để cache chứa dữ liệu chưa commit.

Không dùng riêng thời gian response để kết luận cache đang hoạt động. Hãy quan sát cache metrics, hit/miss, log truy vấn và dữ liệu thực tế.

## 16. Những lỗi thường gặp

### Nhầm ETag với nơi lưu dữ liệu

ETag chỉ là validator. Nó không chứa body và không phải cache store. Client hoặc proxy lưu representation; ETag giúp kiểm tra bản đã lưu.

### Nghĩ 304 là lỗi

304 cho biết client có thể dùng representation đã lưu. Response không cần gửi lại body.

### Dùng no-cache với ý nghĩa no-store

no-cache yêu cầu revalidate trước khi dùng lại; no-store yêu cầu không lưu response vào HTTP cache.

### ETag không đổi dù dữ liệu đã đổi

Validator không phản ánh đầy đủ version hoặc các trường ảnh hưởng representation. Hãy dùng version/checksum phù hợp và tính đến projection, media type, locale hoặc quyền.

### Cache-Control không phù hợp với dữ liệu cá nhân

Response phụ thuộc người dùng bị cache ở shared cache có thể làm lộ dữ liệu. Chọn private/no-store và kiểm soát authorization theo yêu cầu thực tế.

### Xóa application cache nhưng browser vẫn hiển thị dữ liệu cũ

Hai lớp cache độc lập. Kiểm tra max-age, validator và cơ chế revalidation ở HTTP cache.

### Service cache không bị evict khi ghi qua Spring Data REST

REST exporter mặc định gọi repository resource, có thể bỏ qua service mang @CacheEvict. Phải bao phủ mọi đường ghi bằng chiến lược invalidation phù hợp.

### Cache bị nạp lại dữ liệu cũ trong lúc transaction chưa commit

Invalidation xảy ra trước commit hoặc reader tải dữ liệu khi transaction cập nhật chưa hoàn tất. Với yêu cầu nhất quán chặt, xử lý invalidation sau commit và kiểm tra concurrency.

### Dùng key cache thiếu tenant hoặc projection

Hai request có cùng ID nhưng khác tenant, locale, projection hoặc quyền có thể nhận nhầm kết quả. Đưa các yếu tố ảnh hưởng kết quả vào key hoặc không cache dữ liệu đó.

### Nghĩ @Version tự thay thế mọi HTTP cache policy

@Version hỗ trợ phát hiện xung đột cập nhật và có thể được dùng làm ETag trong Spring Data REST. Nó không tự quyết định max-age, private/public, no-store hoặc Vary.

## 17. Ghi nhớ

- HTTP cache lưu representation ở client/proxy; application cache lưu dữ liệu hoặc kết quả method ở server.
- **ETag** và **Last-Modified** là validator; **If-None-Match** và **If-Modified-Since** yêu cầu kiểm tra freshness.
- Khi representation chưa đổi, conditional GET có thể nhận **304 Not Modified** và client tái sử dụng body đã lưu.
- **Cache-Control** quyết định freshness và khả năng lưu; **Vary** phân biệt biến thể theo request header.
- **If-Match** có thể bảo vệ cập nhật khỏi lost update; JPA **@Version** hỗ trợ optimistic locking.
- Spring Cache dùng **@Cacheable**, **@CachePut** và **@CacheEvict** cho cache phía server.
- Invalidation phải bao phủ mọi đường ghi, kể cả repository endpoint do Spring Data REST công bố.
- Khi cần nhất quán chặt, gắn invalidation với thời điểm transaction commit.
- HTTP cache và application cache độc lập; cấu hình hoặc xóa một lớp không tự tác động lớp còn lại.
- Kiểm tra riêng HTTP status/header, cache hit/miss, repository query và hành vi sau cập nhật.

## Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics: Conditional Requests](https://www.rfc-editor.org/rfc/rfc9110.html#name-conditional-requests)
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
