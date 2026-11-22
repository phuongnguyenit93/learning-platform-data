# Phân biệt POST, PUT, PATCH khi cùng dựa trên phương thức save

## Mục tiêu

Spring Data REST ánh xạ nhiều HTTP method vào cùng một phương thức repository `save(…)`. Trên collection resource, `POST` dùng để tạo entity. Trên item resource, `PUT` thay thế trạng thái tài nguyên và `PATCH` cập nhật một phần. Vì vậy, nhìn thấy cả ba request đều gọi `save()` không có nghĩa chúng có cùng ý nghĩa.

Cần phân biệt hai lớp quyết định:

- **HTTP method và URI** xác định ý định của client: tạo tài nguyên trong collection, thay thế một item hay thay đổi một phần item.
- **Spring Data repository** quyết định cách lưu entity theo trạng thái mới/cũ và cơ chế của data store. Với Spring Data JPA, `save()` thường chọn `EntityManager.persist()` hoặc `EntityManager.merge()` dựa trên chiến lược phát hiện entity mới.

Bài này dùng repository `PersonRepository` làm ví dụ. Các quy tắc HTTP mô tả hành vi mặc định của Spring Data REST; cấu hình export, phiên bản, mapping và store cụ thể vẫn có thể ảnh hưởng kết quả.

## 1. Cùng gọi save nhưng khác ý nghĩa HTTP

Giả sử repository được export tại đường dẫn `/people`:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Spring Data REST cung cấp collection resource `/people` và item resource `/people/{id}`. Các request thường gặp:

| HTTP request | Resource đích | Ý định | Cách xử lý dữ liệu |
|---|---|---|---|
| `POST /people` | Collection | Tạo một entity mới | Tạo entity từ body rồi gọi `save()` |
| `PUT /people/42` | Item 42 | Thay thế trạng thái item | Dùng representation đầy đủ để thay trạng thái rồi gọi `save()` |
| `PATCH /people/42` | Item 42 | Cập nhật một phần item | Áp dụng các thay đổi lên trạng thái hiện tại rồi gọi `save()` |

Trong Spring Data REST, `POST` được hỗ trợ trên collection resource; `PUT` và `PATCH` được hỗ trợ trên item resource. Một số endpoint association có quy tắc HTTP riêng, vì vậy không nên áp dụng bảng này cho URI association.

## 2. POST: tạo entity qua collection resource

Client gửi `POST` đến URI collection:

~~~http
POST /people
Content-Type: application/json
Accept: application/hal+json

{
  "firstName": "An",
  "lastName": "Nguyen",
  "city": "Ho Chi Minh City"
}
~~~

Spring Data REST đọc request body, tạo entity và gọi phương thức `save()` của repository. Đây là thao tác tạo mới theo ý nghĩa của endpoint: client gửi một representation để collection tiếp nhận và tạo ra một item. Nếu ID do database hoặc persistence provider sinh, client thường không gửi ID trong body. Với ID được gán thủ công, ứng dụng cần thiết kế quy tắc ID và entity-newness rõ ràng.

Response tạo mới thường có trạng thái `201 Created` và header `Location` trỏ đến URI item vừa được tạo. Việc response có body hay không phụ thuộc header `Accept` và cấu hình `RepositoryRestConfiguration.setReturnBodyOnCreate(…)`.

Ví dụ, server có thể trả về:

~~~http
HTTP/1.1 201 Created
Location: http://localhost:8080/people/42
Content-Type: application/hal+json
~~~

Điểm cần nhớ: `POST` hướng đến collection, để server tiếp nhận dữ liệu và tạo item. Nếu client gửi lại cùng một `POST`, server có thể tạo thêm một item khác; POST không mặc nhiên có tính idempotent.

## 3. PUT: thay thế trạng thái của một item

Client gửi `PUT` đến URI đã xác định item:

~~~http
PUT /people/42
Content-Type: application/json
Accept: application/hal+json

{
  "firstName": "An",
  "lastName": "Tran",
  "city": "Da Nang"
}
~~~

Spring Data REST dùng body để thay thế trạng thái của tài nguyên đích rồi gọi `save()`. Client nên gửi representation đầy đủ của các thuộc tính cần duy trì. Nếu bỏ một thuộc tính khỏi body, giá trị cũ có thể bị thay bằng `null` hoặc giá trị mặc định theo cách ánh xạ entity. Ví dụ, nếu body bỏ `city`, client không nên kỳ vọng giá trị `city` cũ luôn được giữ nguyên.

Trong Spring Data REST, `PUT` trên item resource còn có thể tạo tài nguyên tại URI chỉ định nếu tài nguyên chưa tồn tại. Đây là khả năng PUT-for-creation của Spring Data REST; có thể tắt riêng cho domain type bằng `disablePutForCreation()` trong `RepositoryRestConfiguration.getExposureConfiguration()`. Hãy xác định rõ hành vi này trong API contract để client biết khi nào PUT tạo mới và khi nào chỉ cập nhật.

PUT có ngữ nghĩa idempotent: gửi lại cùng một representation đến cùng URI phải đưa tài nguyên về cùng trạng thái đích, dù các event hoặc thao tác phụ của ứng dụng có thể được thực thi nhiều lần. Khi cập nhật thành công, response thường là `200 OK` nếu trả representation hoặc `204 No Content` nếu không trả body. Khi PUT tạo item mới, response thường là `201 Created`. Các tùy chọn `setReturnBodyOnUpdate(…)` và `setReturnBodyCreate(…)` có thể điều chỉnh response.

## 4. PATCH: cập nhật một phần item

Client gửi `PATCH` đến URI item và chỉ đưa các trường cần thay đổi:

~~~http
PATCH /people/42
Content-Type: application/merge-patch+json
Accept: application/hal+json

{
  "city": "Can Tho"
}
~~~

Spring Data REST áp dụng các thay đổi trong body lên trạng thái tài nguyên hiện tại rồi gọi `save()`. Trong ví dụ này, `city` được thay đổi; các thuộc tính không xuất hiện trong patch, như `firstName` và `lastName`, được giữ theo trạng thái hiện tại.

Spring Data REST hỗ trợ các media type patch như `application/patch+json` và `application/merge-patch+json`, ngoài `application/json`. Media type quyết định cách diễn giải patch document. Đặc biệt, cần phân biệt thuộc tính bị bỏ qua với thuộc tính được gửi tường minh là `null`; ý nghĩa của `null` phụ thuộc định dạng patch và cơ chế mapping. Hãy kiểm tra đúng media type và quy tắc dữ liệu của endpoint.

PATCH không đảm bảo idempotent cho mọi loại patch document. Ví dụ, một phép tăng giá trị có thể cho kết quả khác khi gửi lặp lại. Nếu client cần gửi lại request sau timeout, hãy thiết kế patch operation có thể lặp an toàn hoặc dùng cơ chế kiểm soát phiên bản.

## 5. Vì sao save() có thể insert hoặc update?

HTTP method không trực tiếp quyết định JPA sẽ gọi `persist()` hay `merge()`. Với Spring Data JPA, `SimpleJpaRepository.save(entity)` kiểm tra entity có được xem là mới hay không:

- Entity mới: gọi `EntityManager.persist(entity)`.
- Entity đã tồn tại: gọi `EntityManager.merge(entity)`.

Mặc định, Spring Data JPA phát hiện trạng thái entity theo thứ tự sau:

1. Nếu có thuộc tính `@Version` không phải kiểu primitive, giá trị version là `null` thì entity được xem là mới.
2. Nếu không có version property phù hợp, kiểm tra ID: ID là `null` thì entity được xem là mới; ID khác `null` thì được xem là đã tồn tại.
3. Nếu entity triển khai `Persistable<ID>`, Spring Data dùng `isNew()` của entity để xác định trạng thái.
4. Ứng dụng có thể tùy chỉnh `EntityInformation` trong những trường hợp đặc biệt.

Ví dụ entity JPA:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @Version
    private Long version;

    private String firstName;
    private String lastName;
    private String city;

    // constructors, getters, setters
}
~~~

Với entity này, version `null` là dấu hiệu entity mới theo chiến lược phát hiện của Spring Data JPA. Khi entity đã được lưu và version có giá trị, entity được xem là không mới. Nếu không dùng `@Version`, ID thường được dùng để phát hiện trạng thái.

Điều đó giải thích vì sao không thể chỉ nhìn HTTP method hoặc ID trong JSON để kết luận chắc chắn SQL cuối cùng là INSERT hay UPDATE. Endpoint xác định cách diễn giải request; chiến lược entity-newness của store xác định đường lưu. Với datastore khác JPA, chi tiết bên dưới `save()` có thể khác.

### 5.1. Trường hợp ID được gán thủ công

Nếu ứng dụng tự gán ID ngay khi tạo entity, ID khác `null` có thể khiến chiến lược mặc định xem entity là đã tồn tại. Khi đó, một entity mới có thể bị gửi qua nhánh `merge()`.

Một cách xử lý là triển khai `Persistable<ID>` và quản lý cờ `isNew` phù hợp với vòng đời entity:

~~~java
@MappedSuperclass
public abstract class BaseEntity implements Persistable<Long> {

    @Id
    private Long id;

    @Transient
    private boolean newEntity = true;

    @Override
    public Long getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    @PostPersist
    @PostLoad
    void markNotNew() {
        this.newEntity = false;
    }
}
~~~

Đây là ví dụ về chiến lược, không phải đoạn code có thể sao chép nguyên trạng cho mọi domain. Cần bảo đảm cờ được cập nhật đúng sau khi insert và khi entity được tải lại; nếu dùng property access, kiểm tra thêm cách JPA nhận diện thuộc tính `Persistable`.

### 5.2. Dùng giá trị trả về của save()

Với JPA, `merge()` có thể trả về một instance được quản lý khác với instance truyền vào. Vì vậy, hãy dùng entity mà `save()` trả về:

~~~java
Person saved = personRepository.save(person);
~~~

Không nên mặc định rằng object ban đầu luôn được cập nhật ID, version hoặc trạng thái persistence sau khi gọi `save()`.

## 6. Đặt ba request cạnh nhau

Giả sử person 42 đang có dữ liệu:

~~~json
{
  "id": 42,
  "firstName": "An",
  "lastName": "Nguyen",
  "city": "Ha Noi"
}
~~~

**POST – tạo item mới**

~~~http
POST /people
Content-Type: application/json

{
  "firstName": "Binh",
  "lastName": "Le",
  "city": "Hue"
}
~~~

Kết quả là một item mới. URI được server cung cấp qua header `Location`.

**PUT – thay thế item 42**

~~~http
PUT /people/42
Content-Type: application/json

{
  "firstName": "An",
  "lastName": "Tran",
  "city": "Da Nang"
}
~~~

Kết quả là trạng thái đầy đủ của item 42 được thay bằng representation gửi lên. Các trường bị bỏ khỏi body có thể mất giá trị cũ.

**PATCH – chỉ sửa một trường của item 42**

~~~http
PATCH /people/42
Content-Type: application/merge-patch+json

{
  "city": "Can Tho"
}
~~~

Kết quả là city đổi thành Can Tho; firstName và lastName giữ theo trạng thái trước đó.

| Tiêu chí | POST | PUT | PATCH |
|---|---|---|---|
| URI điển hình | Collection | Item | Item |
| Mục tiêu | Tạo item | Thay thế item | Sửa một phần item |
| Body | Dữ liệu để tạo | Representation đầy đủ | Các thay đổi cần áp dụng |
| Spring Data REST gọi | `save()` | `save()` | `save()` |
| Có thể tạo item? | Có | Có thể, nếu PUT-for-creation được bật | Không dùng PATCH để tạo item mới |
| Idempotent theo ngữ nghĩa HTTP | Không mặc nhiên | Có | Không được bảo đảm cho mọi patch |
| Response tạo mới | Thường 201 Created | Thường 201 Created nếu tạo qua PUT | Không phải thao tác tạo resource |

## 7. Kiểm soát việc export và hành vi cập nhật

Do `save()` được dùng cho POST trên collection và PUT/PATCH trên item, ẩn phương thức save bằng `@RestResource(exported = false)` có thể làm mất nhiều endpoint ghi cùng lúc. Nếu chỉ muốn tắt một HTTP method hoặc một khả năng cụ thể, dùng `RepositoryRestConfiguration.getExposureConfiguration()` để cấu hình theo domain type hoặc item exposure.

Ví dụ tắt khả năng PUT tạo item mới cho `Person`:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getExposureConfiguration()
            .forDomainType(Person.class)
            .disablePutForCreation();
    }
}
~~~

Có thể tắt PATCH trên các item resource qua item exposure:

~~~java
config.getExposureConfiguration()
    .withItemExposure((metadata, methods) ->
        methods.disable(HttpMethod.PATCH));
~~~

Tên API và chữ ký phương thức có thể khác theo thế hệ Spring Data REST đang dùng. Kiểm tra phiên bản dependency trước khi áp dụng đoạn cấu hình.

## 8. Validation, event và cập nhật đồng thời

Cả ba request có thể đi qua cùng repository save path, nhưng dữ liệu đầu vào và ý định khác nhau. Vì vậy:

- Validation cần kiểm tra trạng thái cuối cùng của entity. Với PATCH, hãy kiểm tra sau khi áp dụng patch lên entity hiện tại, vì body có thể chỉ chứa một trường.
- Các repository event như before-save/after-save phản ánh vòng đời lưu entity. Đừng suy luận POST, PUT hay PATCH chỉ từ một event save chung nếu ứng dụng cần phân nhánh theo HTTP method.
- PUT và PATCH có thể ghi đè thay đổi của request khác nếu hai client cùng đọc một version cũ. Với JPA, dùng `@Version` để bật optimistic locking; Spring Data REST cũng hỗ trợ conditional request qua ETag và `If-Match`.
- Khi cần quy tắc nghiệp vụ riêng theo thao tác, đặt logic ở service/domain layer với ngữ cảnh thao tác rõ ràng hoặc xây dựng endpoint tùy chỉnh. Không nên dựa vào việc cùng gọi `save()` để suy ra ý định nghiệp vụ.

## 9. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể gặp | Cách kiểm tra |
|---|---|---|
| POST tạo thêm bản ghi ngoài dự kiến | Client dùng POST cho thao tác cập nhật | Kiểm tra URI collection và HTTP method |
| PUT làm mất giá trị các trường không gửi | PUT thay thế representation | Gửi đủ trường cần duy trì hoặc chuyển sang PATCH |
| PATCH làm thay đổi trường không mong muốn | Media type hoặc ý nghĩa null/association chưa rõ | Kiểm tra Content-Type và patch document |
| PUT tới URI mới không tạo được item | PUT-for-creation đã bị tắt hoặc ID không hợp lệ với store | Kiểm tra ExposureConfiguration và ID strategy |
| POST/PUT gọi save nhưng insert/update khác dự kiến | Entity-newness detection không khớp ID/version | Kiểm tra `@Version`, ID và `Persistable.isNew()` |
| Dữ liệu lưu đúng nhưng object trong code cũ chưa có version/ID | Không dùng instance do `save()` trả về | Gán kết quả `save()` vào biến và dùng kết quả đó |
| Hai client ghi đè dữ liệu của nhau | Không có kiểm soát cập nhật đồng thời | Dùng `@Version` và conditional request ETag/If-Match |

## 10. Checklist chọn HTTP method

- Chọn POST trên collection khi muốn server tạo một item mới.
- Chọn PUT trên item khi client có representation đầy đủ và muốn thay thế trạng thái tại URI đó.
- Chọn PATCH trên item khi chỉ muốn thay đổi một phần trạng thái.
- Kiểm tra khả năng PUT-for-creation đã bật hay tắt trong Spring Data REST.
- Kiểm tra media type của PATCH và cách xử lý thuộc tính bị bỏ qua hoặc gửi `null`.
- Kiểm tra chiến lược phát hiện entity mới của store, đặc biệt khi ID được gán thủ công.
- Luôn dùng instance trả về từ `save()`.
- Dùng optimistic locking/ETag khi nhiều client có thể cập nhật cùng tài nguyên.
- Xem response status, `Location` và representation trả về để xác định request đã tạo hay cập nhật.

## Kết luận

POST, PUT và PATCH có thể cùng gọi `save()` nhưng mang ba ý định khác nhau. POST tạo item qua collection; PUT thay thế representation của item và trong Spring Data REST có thể tạo item nếu PUT-for-creation được bật; PATCH áp dụng một phần thay đổi lên item hiện tại. Sau khi endpoint chuẩn bị entity, Spring Data JPA tự phát hiện entity mới hay cũ để chọn persist hoặc merge. Muốn hiểu đúng kết quả, hãy đọc cả HTTP method, URI, body, cấu hình exposure và chiến lược entity-newness thay vì chỉ nhìn tên phương thức save.

## Tài liệu tham khảo

- Spring Data REST Reference – Repository resources: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST Reference 3.7 – Customizing supported HTTP methods: https://docs.spring.io/spring-data/rest/docs/3.7.0/reference/html/
- Spring Data JPA Reference – Persisting entities: https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html

