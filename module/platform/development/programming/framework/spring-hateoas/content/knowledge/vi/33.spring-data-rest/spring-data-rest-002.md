# Repository resource

Spring Data REST tự động công bố các REST resource dựa trên Spring Data repository. Thay vì phải viết controller cho từng thao tác CRUD cơ bản, ứng dụng có thể định nghĩa repository interface và để Spring Data REST tạo collection resource, item resource, các liên kết điều hướng và endpoint tìm kiếm tương ứng.

Các resource này được tổ chức theo mô hình hypermedia. Client bắt đầu từ API root, theo link relation để đến collection, sau đó theo self link để mở một item hoặc theo link quan hệ để truy cập tài nguyên liên quan. Mặc định, Spring Data REST dùng HAL để biểu diễn link trong JSON.

Bài học này giải thích repository resource là gì, cách Spring Data REST phát hiện và công bố repository, cấu trúc collection và item resource, cách tùy chỉnh path và relation bằng annotation, cách giới hạn resource được export, và cách kiểm thử hợp đồng hypermedia.

## 1. Repository resource là gì?

Repository resource là REST resource được Spring Data REST tạo từ một Spring Data repository interface. Repository cung cấp các thao tác truy cập dữ liệu; Spring Data REST ánh xạ những thao tác được export thành HTTP resource và method.

Ví dụ repository đơn giản:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~

Nếu ứng dụng đã cấu hình Spring Data REST và repository được phát hiện, framework tạo:

- Collection resource tại đường dẫn đại diện cho tập hợp Person.
- Item resource cho từng Person, nằm dưới collection resource.
- Link đến các resource liên quan nếu entity có association được export.
- Search resource nếu repository khai báo query method được export.

Với domain type Person, đường dẫn mặc định thường được pluralize thành /persons. Một item có thể nằm tại /persons/42. Đây là quy ước mặc định; có thể tùy chỉnh path và relation bằng annotation.

Repository resource không phải là một controller do lập trình viên viết thủ công. Spring Data REST sử dụng metadata của repository để xây dựng HTTP API, sau đó serialize kết quả thành representation hypermedia.

## 2. Spring Data REST phát hiện repository như thế nào?

Spring Data REST cần được thêm vào ứng dụng qua dependency phù hợp với nền tảng Spring Data đang dùng. Với Spring Boot, starter thường được khai báo như sau:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-rest</artifactId>
</dependency>
~~~

Khi ứng dụng khởi động, Spring Data REST tìm các repository interface thuộc phạm vi cấu hình Spring Data. Theo cấu hình mặc định, các repository public thường được export; repository package-private bị loại khỏi mặc định. Có thể thay đổi hành vi này bằng RepositoryDetectionStrategy.

Việc một repository được phát hiện không có nghĩa mọi method đều tự động trở thành endpoint. Các resource và HTTP method được tạo dựa trên những method repository có thể export, cấu hình của exporter và các annotation giới hạn exposure.

Ví dụ, CrudRepository cung cấp các thao tác cơ bản như tìm theo ID, tìm tất cả, lưu và xóa. Spring Data REST sử dụng những method tương ứng để phục vụ collection và item resource.

## 3. API root là điểm bắt đầu khám phá

Client nên bắt đầu bằng request đến root URL của Spring Data REST:

~~~http
GET /
Accept: application/hal+json
~~~

Một response rút gọn có thể như sau:

~~~json
{
  "_links": {
    "people": {
      "href": "http://localhost:8080/people"
    }
  }
}
~~~

Ví dụ giả định repository được cấu hình path people. Nếu không tùy chỉnh, collection path thường được suy ra từ tên domain type và pluralize thành persons.

Mỗi key trong _links là một relation. Relation people dẫn đến collection resource. Một số cấu hình còn công bố relation profile để client khám phá metadata mô tả API. Client có thể lấy href của people từ response để tiếp tục, thay vì tự ghép /people vào base URL.

Spring Data REST mặc định dùng HAL. HAL đặt link trong thuộc tính _links, còn các phần tử của collection thường nằm trong _embedded. Cách biểu diễn này cho phép client khám phá API theo relation thay vì phụ thuộc vào cấu trúc đường dẫn cụ thể.

Nếu ứng dụng thay đổi base path hoặc path của repository, client tuân theo link mới được công bố từ API root.

## 4. Collection resource

Collection resource đại diện cho tập hợp entity do repository quản lý. Với PersonRepository, collection mặc định thường được công bố tại /persons. Các ví dụ request bên dưới dùng path tùy chỉnh /people để thống nhất với cấu hình RepositoryRestResource ở phần sau.

Collection resource hỗ trợ các thao tác phổ biến:

| HTTP method | Mục đích |
| --- | --- |
| GET | Lấy danh sách entity, có thể kèm phân trang và sắp xếp |
| POST | Tạo entity mới bằng cách gửi representation trong request body |

Các method khác thường không được áp dụng trực tiếp trên collection resource. Việc cập nhật hoặc xóa một entity cụ thể được thực hiện trên item resource tương ứng.

Ví dụ request:

~~~http
GET /people
Accept: application/hal+json
~~~

Response HAL minh họa:

~~~json
{
  "_embedded": {
    "people": [
      {
        "firstName": "An",
        "lastName": "Nguyen",
        "_links": {
          "self": {
            "href": "http://localhost:8080/people/42"
          }
        }
      },
      {
        "firstName": "Binh",
        "lastName": "Tran",
        "_links": {
          "self": {
            "href": "http://localhost:8080/people/43"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/people"
    }
  }
}
~~~

Tên people trong _embedded là collection relation. Mỗi item có self link để client truy cập representation riêng của item đó. Response thực tế có thể có thêm link search và page metadata tùy repository.

### Tạo entity qua collection

Spring Data REST có thể ánh xạ POST trên collection resource đến thao tác save của repository:

~~~http
POST /people
Content-Type: application/json
Accept: application/hal+json

{
  "firstName": "Chi",
  "lastName": "Le"
}
~~~

Khi tạo thành công, response thường có status 201 Created. Header Location chỉ đến item resource vừa được tạo. Response body phụ thuộc Accept header và cấu hình trả body khi tạo resource.

Client nên đọc Location hoặc link trong response để mở item mới. Không tự đoán ID được sinh bởi persistence layer.

## 5. Item resource

Item resource đại diện cho một entity cụ thể trong collection. Với Person có ID 42, item resource có thể ở /people/42.

Các HTTP method thường được hỗ trợ:

| HTTP method | Mục đích |
| --- | --- |
| GET | Đọc entity |
| PUT | Thay thế trạng thái resource bằng representation gửi lên |
| PATCH | Cập nhật một phần trạng thái resource |
| DELETE | Xóa entity |

Việc một method được expose còn phụ thuộc repository method tương ứng có tồn tại và có bị tắt bằng cấu hình hay không.

Ví dụ đọc một item:

~~~http
GET /people/42
Accept: application/hal+json
~~~

Response minh họa:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

Nếu entity có association được export, item resource có thể chứa thêm link mang tên property quan hệ. Ví dụ, một Person có department thì response có thể công bố link department để client khám phá association resource.

PUT thay thế trạng thái resource theo semantics của HTTP PUT. PATCH chỉ thay đổi một phần. Client cần gửi đúng Content-Type và representation phù hợp với converter được cấu hình. DELETE xóa item nếu thao tác đó được export và người gọi có quyền.

## 6. Repository interface và domain type

Một ví dụ tối giản cho domain Person:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String firstName;
    private String lastName;

    protected Person() {
    }

    public Person(String firstName, String lastName) {
        this.firstName = firstName;
        this.lastName = lastName;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }

    public void setLastName(String lastName) {
        this.lastName = lastName;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~

Spring Data REST sử dụng domain type để xác định resource và repository metadata để biết những thao tác có thể export. Với JPA, ID được lấy từ thuộc tính được đánh dấu @Id.

Ví dụ dùng jakarta.persistence theo các phiên bản Spring hiện đại. Dự án dùng nền tảng cũ hơn có thể sử dụng package javax.persistence tương ứng.

## 7. Tùy chỉnh path và relation bằng RepositoryRestResource

Annotation RepositoryRestResource cho phép tùy chỉnh cách repository được export:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people",
        itemResourceRel = "person"
)
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~

Ba thuộc tính quan trọng:

| Thuộc tính | Tác dụng |
| --- | --- |
| path | Đổi path segment của repository resource |
| collectionResourceRel | Đổi relation dùng cho collection resource |
| itemResourceRel | Đổi relation dùng cho item resource |

Trong ví dụ, collection được công bố ở /people. Relation collection là people và relation item là person. Path và relation có vai trò khác nhau: path xác định URI, còn relation cho client biết ý nghĩa của link.

Annotation còn có exported để bật hoặc tắt việc export repository, cùng các thuộc tính mô tả resource và excerptProjection. Chỉ nên công bố các repository mà API thực sự cần cung cấp.

## 8. Tùy chỉnh base path toàn ứng dụng

Nếu muốn đặt toàn bộ Spring Data REST resource dưới một prefix, có thể cấu hình base path qua RepositoryRestConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors
    ) {
        config.setBasePath("/api");
    }
}
~~~

Sau cấu hình này, collection people được truy cập qua /api/people. API root của Spring Data REST cũng nằm dưới base path. Các link được exporter tạo ra phản ánh prefix đã cấu hình.

Base path giúp phân biệt API với các route khác của ứng dụng. Nếu có reverse proxy hoặc gateway đứng trước ứng dụng, cần cấu hình forwarded headers và external URL phù hợp để link tuyệt đối được sinh đúng host, scheme và prefix.

## 9. Search resource từ query method

Nếu repository khai báo query method, Spring Data REST có thể công bố search resource. Ví dụ:

~~~java
import java.util.List;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people",
        itemResourceRel = "person"
)
public interface PersonRepository
        extends CrudRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    List<Person> findByLastName(@Param("name") String lastName);
}
~~~

Search resource được công bố tại /people/search. Link byLastName trỏ đến query method resource, ví dụ:

~~~http
GET /people/search/by-last-name?name=Nguyen
Accept: application/hal+json
~~~

Thuộc tính path của @RestResource tùy chỉnh URI segment của query method. Thuộc tính rel tùy chỉnh relation của link. @Param đặt tên query parameter công khai.

Search resource là một điểm khám phá. Client nên theo link byLastName từ search resource thay vì tự giả định tên method hoặc URL.

## 10. Tắt export repository, method hoặc association

Mặc định, repository được phát hiện có thể được export. Nếu một repository không nên trở thành API resource, dùng exported = false:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends CrudRepository<AuditEntry, Long> {
}
~~~

Để tắt một query method, đặt @RestResource(exported = false) trên method:

~~~java
@RestResource(exported = false)
List<Person> findByInternalFlag(boolean internalFlag);
~~~

Có thể dùng @RestResource(exported = false) trên association property để không công bố association resource tương ứng:

~~~java
import jakarta.persistence.ManyToOne;
import org.springframework.data.rest.core.annotation.RestResource;

@ManyToOne
@RestResource(exported = false)
private Department department;
~~~

Nếu cần tắt một CRUD method kế thừa, repository có thể override method đó và đặt annotation lên method override. Cần kiểm tra tất cả overload liên quan theo phiên bản Spring Data đang sử dụng.

exported = false kiểm soát việc công bố resource hoặc method qua Spring Data REST. Đây không phải cơ chế phân quyền. Các endpoint còn được export vẫn cần được bảo vệ bằng Spring Security và chính sách truy cập phù hợp.

## 11. Repository detection strategy

Ứng dụng có thể kiểm soát repository nào được Spring Data REST phát hiện thông qua RepositoryDetectionStrategy. Một số lựa chọn thường gặp:

| Strategy | Quy tắc khái quát |
| --- | --- |
| DEFAULT | Export repository public hoặc repository được đánh dấu rõ ràng và không bị tắt |
| ALL | Export mọi Spring Data repository trong phạm vi phát hiện |
| VISIBILITY | Dựa vào visibility của repository interface |
| ANNOTATED | Chỉ export repository được đánh dấu bằng RepositoryRestResource và không bị tắt |

Strategy ảnh hưởng phạm vi repository được công bố. Khi ứng dụng có nhiều repository nội bộ, hãy chọn strategy phù hợp và kiểm tra API root để tránh vô tình tạo endpoint cho dữ liệu không dành cho client.

Có thể chọn strategy trong cấu hình:

~~~java
import org.springframework.data.rest.core.mapping.RepositoryDetectionStrategy;

config.setRepositoryDetectionStrategy(
        RepositoryDetectionStrategy.RepositoryDetectionStrategies.ANNOTATED
);
~~~

Đặt lệnh này trong phương thức configureRepositoryRestConfiguration của RepositoryRestConfigurer. Với ANNOTATED, chỉ repository được đánh dấu bằng RepositoryRestResource và không bị tắt mới được export. Đây là lựa chọn phù hợp khi muốn opt-in rõ ràng cho từng repository.

## 12. Phân trang và sắp xếp trên collection resource

Nếu repository hỗ trợ paging, collection resource có thể nhận các query parameter:

| Parameter | Ý nghĩa | Mặc định thường gặp |
| --- | --- | --- |
| page | Chỉ số trang, bắt đầu từ 0 | 0 |
| size | Số phần tử tối đa trong một trang | 20 |
| sort | Trường và hướng sắp xếp | Không có |

Ví dụ:

~~~http
GET /people?page=1&size=10&sort=lastName,asc
Accept: application/hal+json
~~~

Response có thể chứa _embedded, _links và page metadata. Link next, prev, first và last giúp client điều hướng giữa các trang. Khi dùng link, client không phải tự ghép các tham số page và size.

Để hỗ trợ paging, repository cần expose các method phân trang phù hợp, thường là findAll(Pageable). Trong các phiên bản Spring Data hiện đại, PagingAndSortingRepository không thay thế các thao tác CRUD; có thể kết hợp nó với CrudRepository nếu cần cả hai nhóm method.

Đây là biến thể của PersonRepository ở phần trước, khai báo cả thao tác CRUD và paging:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.PagingAndSortingRepository;

public interface PersonRepository
        extends CrudRepository<Person, Long>,
                PagingAndSortingRepository<Person, Long> {
}
~~~

## 13. Association resource

Khi domain type có quan hệ với domain type khác, Spring Data REST có thể công bố link tới association resource. Ví dụ Person có một Department:

~~~java
import jakarta.persistence.ManyToOne;

@ManyToOne
private Department department;
~~~

Item resource của Person có thể có link department. Client theo link này để truy cập hoặc cập nhật quan hệ theo các HTTP method mà association resource hỗ trợ.

Association resource giúp client làm việc với mối quan hệ giữa entity mà không cần đoán endpoint theo cấu trúc entity hoặc tên bảng. Cấu trúc cụ thể phụ thuộc loại association, mapping JPA và cấu hình exposure.

Hãy cân nhắc việc export association có phù hợp với hợp đồng API hay không. Quan hệ nội bộ hoặc dữ liệu nhạy cảm có thể cần được ẩn bằng @RestResource(exported = false), projection hoặc API resource được thiết kế riêng.

## 14. Repository resource và projection

Repository resource thường serialize domain object theo cấu hình exporter. Nếu cần thay đổi representation mà vẫn giữ repository resource, Spring Data REST hỗ trợ projection và excerpt projection.

Projection cho phép chọn tập thuộc tính được hiển thị cho một response hoặc embedded item. RepositoryRestResource có thuộc tính excerptProjection để cấu hình projection dùng khi nhúng item trong collection và related resources.

Projection hữu ích để tránh trả về toàn bộ cấu trúc domain trong collection response. Tuy nhiên, projection cũng có thể làm xuất hiện các thuộc tính mà ứng dụng tưởng đã ẩn ở entity. Không dùng projection như một cơ chế bảo mật; hãy kiểm tra mọi projection được export và không đưa trường nhạy cảm vào representation.

Khi cần một response có cấu trúc khác hẳn domain model, quy tắc nghiệp vụ phức tạp hoặc orchestration nhiều repository, có thể xây endpoint/controller riêng thay vì ép mọi thứ vào repository exporter.

## 15. Kiểm thử repository resource bằng MockMvc

Một integration test có thể xác nhận API root công bố collection relation và collection resource trả HAL:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class PersonRepositoryResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void apiRootPublishesPeopleCollectionLink() throws Exception {
        mockMvc.perform(get("/")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.people.href").exists());
    }

    @Test
    void collectionResourcePublishesSelfLink() throws Exception {
        mockMvc.perform(get("/people")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.self.href").exists());
    }
}
~~~

Ví dụ giả định ứng dụng dùng path people và relation people như repository đã khai báo. Nếu có base path, hãy đổi URL test theo base path đó. Test cần một Spring context có cấu hình Spring Data REST và repository được phát hiện.

Để kiểm tra collection item, hãy chuẩn bị dữ liệu test và xác nhận relation _embedded.people. Để kiểm tra item resource, lấy ID từ dữ liệu đã lưu và xác nhận _links.self. Tránh phụ thuộc vào hostname, port ngẫu nhiên hoặc thứ tự property JSON.

Nên bổ sung các trường hợp:

- Repository được export và repository có exported = false.
- Collection GET và POST.
- Item GET, PUT, PATCH và DELETE theo method đã bật.
- Search resource và query method link.
- Association link có xuất hiện đúng theo mapping.
- Phân trang giữ đúng metadata và link điều hướng.
- Security chặn request không được phép dù resource vẫn có link.

## 16. Những lỗi thường gặp

**Cho rằng mọi repository đều tự động trở thành endpoint.** Repository phải nằm trong phạm vi phát hiện và phù hợp detection strategy. Kiểm tra API root để biết resource nào thực sự được công bố.

**Nhầm path với relation.** path đổi URI; collectionResourceRel và itemResourceRel đổi tên relation. Client dùng relation để khám phá ý nghĩa link.

**Cho rằng repository method nào cũng được expose.** Method phải được exporter hỗ trợ và không bị đánh dấu exported = false.

**Dùng item URI để thao tác trên collection.** POST tạo entity thường gửi đến collection; PUT, PATCH và DELETE thao tác trên item resource.

**Tự ghép URL từ tên entity.** Hãy khám phá API root và theo link relation. Tên path mặc định có thể thay đổi do cấu hình.

**Coi exported = false là bảo mật.** Annotation chỉ kiểm soát exposure. Endpoint được export vẫn cần xác thực và phân quyền.

**Để lộ entity field nhạy cảm.** Kiểm tra entity, association và tất cả projection được export. Dùng representation phù hợp với dữ liệu công khai.

**Bỏ qua association resource.** Link association có thể làm client truy cập hoặc thay đổi quan hệ. Kiểm tra exposure của từng association.

**Không kiểm thử HAL contract.** Status 200 không chứng minh relation, embedded resource hoặc link đã đúng. Kiểm tra _links và _embedded trong response.

## 17. Ghi nhớ

Spring Data REST tạo repository resource từ Spring Data repository interface. API root công bố link đến các collection resource; collection đại diện cho tập hợp entity; item resource đại diện cho từng entity. Mặc định, Spring Data REST dùng HAL để công bố relation trong _links và item trong _embedded.

RepositoryRestResource cho phép tùy chỉnh path, collectionResourceRel, itemResourceRel và exported. Collection resource thường hỗ trợ GET và POST; item resource thường hỗ trợ GET, PUT, PATCH và DELETE nếu repository có các method cần thiết và chúng không bị tắt. Query method có thể tạo search resource, còn association có thể tạo association resource.

Client nên bắt đầu từ API root và theo link relation để khám phá resource. Kiểm soát repository detection và exported để giới hạn bề mặt API, nhưng luôn dùng Spring Security cho xác thực và phân quyền. Kiểm thử cả HTTP method, status, HAL relation, embedded item và link điều hướng để giữ hợp đồng repository resource ổn định.

## Tài liệu tham khảo

- [Spring Data REST Reference – Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference – Getting started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
- [Spring Data REST Reference – Configuring the REST URL path](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html)
- [Spring Data REST Reference – Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing/customizing-sdr.html)
- [RepositoryRestResource API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html)
- [RestResource API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RestResource.html)
