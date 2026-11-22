# Kiểm thử Spring Data REST: chọn @SpringBootTest, MockMvc hay HTTP thật

## 1. Mục tiêu và cách phân loại

Spring Data REST xuất các Spring Data repository thành REST resource thông qua Spring MVC. Vì vậy, kiểm thử API cần xác nhận repository được công bố đúng, đường dẫn và HTTP method hoạt động, representation JSON/HAL chính xác, cùng các cấu hình ứng dụng có tham gia vào request hay không.

Ba tên thường được đặt cạnh nhau thực ra nằm ở hai trục khác nhau:

- **@SpringBootTest** quyết định phạm vi Spring ApplicationContext được nạp. Đây là cách tải cấu hình ứng dụng Spring Boot để kiểm thử tích hợp.
- **MockMvc** là công cụ tạo request và kiểm tra response qua Spring MVC bằng request/response giả lập. Nó không mở cổng HTTP và không khởi động embedded server.
- **HTTP client + server thật** gửi request qua cổng mạng tới embedded server đang chạy hoặc tới môi trường đã triển khai. Cách này kiểm chứng thêm hành vi phụ thuộc servlet container và network.

Do đó, @SpringBootTest và MockMvc thường được dùng cùng nhau. Với Spring Data REST, tổ hợp mặc định nên bắt đầu là **@SpringBootTest + @AutoConfigureMockMvc**: tải cấu hình ứng dụng, repository, exporter và cấu hình MVC thật, sau đó gọi endpoint bằng MockMvc. Chỉ chuyển sang server thật khi câu hỏi kiểm thử yêu cầu xác nhận hành vi của container, port hoặc network.

## 2. Chọn công cụ theo phạm vi cần xác nhận

| Phạm vi cần kiểm chứng | Cách kiểm thử phù hợp | Điều được kiểm tra | Giới hạn chính |
|---|---|---|---|
| Quy tắc nghiệp vụ trong service | Unit test với JUnit và Mockito | Nhánh xử lý, điều kiện, lỗi và tương tác với dependency | Không xác nhận Spring wiring hay HTTP |
| Entity, repository query, mapping dữ liệu | @DataJpaTest hoặc slice tương ứng với datastore | Mapping, query, ràng buộc và truy cập dữ liệu | Không kiểm tra resource Spring Data REST được xuất ra |
| Endpoint do Spring Data REST tạo, HAL, CRUD, search, paging | @SpringBootTest + @AutoConfigureMockMvc | Cấu hình ứng dụng, Spring MVC, repository exporter, serialization và response | Không kiểm tra embedded server hay network thật |
| Một controller MVC tự viết, không cần toàn bộ ứng dụng | @WebMvcTest + MockMvc | Mapping và hành vi web layer của controller với dependency giả lập | Slice không tự nạp toàn bộ repository/exporter configuration |
| Cần kiểm tra embedded servlet container, port, cookie/session hoặc hành vi container | @SpringBootTest(webEnvironment = RANDOM_PORT) + HTTP client | Request đi qua server thật trên port ngẫu nhiên | Khởi động server và tốn thời gian hơn; phải quản lý dữ liệu test |
| Cần xác nhận gateway, reverse proxy, DNS, TLS hoặc cấu hình môi trường đã triển khai | HTTP test bên ngoài, smoke test hoặc end-to-end test | Toàn bộ đường đi từ client tới môi trường đích | Phụ thuộc môi trường và thường chậm, khó cô lập hơn |

### Những lựa chọn dễ nhầm

**@SpringBootTest mặc định không khởi động server.** Giá trị mặc định của webEnvironment là MOCK. Với ứng dụng MVC, có thể kết hợp @AutoConfigureMockMvc để lấy MockMvc. Muốn khởi động server, đặt webEnvironment thành RANDOM_PORT hoặc DEFINED_PORT.

**MockMvc không đồng nghĩa với unit test.** Khi được cấu hình bằng WebApplicationContext, MockMvc đi qua Spring MVC infrastructure và cấu hình ứng dụng thật. Đây là kiểm thử tích hợp web layer. MockMvc ở chế độ standalone chỉ nhận controller được chỉ định và cấu hình MVC do test cung cấp; nó gần unit test hơn và cần một lượt integration test riêng để xác nhận cấu hình MVC thực tế.

**@WebMvcTest là slice test.** Nó hữu ích khi kiểm tra controller tự viết và thay service bằng mock. Slice này giới hạn bean được quét; các Spring Data repository và cấu hình xuất resource của Spring Data REST có thể không được nạp. Vì thế, không nên chọn @WebMvcTest làm bài kiểm thử chính cho endpoint được sinh từ repository. Nếu cần dùng slice, phải chủ động import đúng cấu hình và hiểu rõ phần nào đang được bỏ qua.

## 3. Chuẩn bị dependency và dữ liệu

Với ứng dụng Spring Boot, thường chỉ cần starter kiểm thử ở test scope; phiên bản được quản lý bằng Spring Boot dependency management.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Starter cung cấp các thành phần kiểm thử phổ biến như JUnit Jupiter, AssertJ, Hamcrest và Spring Boot test support. Ứng dụng vẫn cần dependency Spring Data REST và dependency datastore tương ứng ở cấu hình chạy thông thường.

Nếu kiểm thử hành vi phụ thuộc hệ quản trị dữ liệu, hãy dùng cùng loại database với môi trường ứng dụng, thường qua Testcontainers. Database in-memory hữu ích cho test nhanh nhưng không thay thế được kiểm chứng về dialect, constraint, collation, transaction hoặc SQL đặc thù của database thật. Có thể tham khảo các sample chính thức của Spring Data; nhiều sample dùng Testcontainers hoặc datastore nhúng.

## 4. Ví dụ tích hợp: kiểm tra resource được xuất bằng MockMvc

Giả sử ứng dụng có entity Person và muốn xuất repository tại đường dẫn /people.

Entity minh họa:

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

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public void setLastName(String lastName) {
        this.lastName = lastName;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people"
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Spring Data REST có thể tạo collection resource và item resource từ repository. Trong ví dụ này, collection là /people; item có dạng /people/{id}. Mặc định response dùng HAL, với các liên kết được đặt trong thuộc tính _links.

### Test bằng Spring Boot context và MockMvc

Ví dụ dưới đây dùng API Spring Boot 3.5.x và JUnit Jupiter. Với Spring Boot 3.x, import AutoConfigureMockMvc là org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc. Trong Spring Boot 4.x, package của annotation được chuyển sang org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc. Hãy dùng package tương ứng với phiên bản đang được quản lý trong dự án.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PersonRestApiTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    PersonRepository people;

    @BeforeEach
    void prepareData() {
        people.deleteAll();
        people.save(new Person("Ada", "Lovelace"));
    }

    @Test
    void rootPublishesPeopleLink() throws Exception {
        mvc.perform(get("/").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.people.href").exists());
    }

    @Test
    void collectionIsReturnedAsHal() throws Exception {
        mvc.perform(get("/people").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._embedded.people[0].firstName").value("Ada"))
            .andExpect(jsonPath("$._links.self.href").exists());
    }

    @Test
    void postCreatesResource() throws Exception {
        mvc.perform(post("/people")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaTypes.HAL_JSON)
                .content("""
                    {
                      "firstName": "Grace",
                      "lastName": "Hopper"
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().exists(HttpHeaders.LOCATION));
    }
}
~~~

Các điểm cần hiểu trong ví dụ:

1. @SpringBootTest nạp cấu hình ứng dụng chính. Repository, Spring Data REST exporter, mapping, serializer, security và cấu hình MVC của ứng dụng có cơ hội tham gia vào test.
2. @AutoConfigureMockMvc tạo MockMvc trong mock web environment. Không cần chạy server ở cổng 8080.
3. Accept: application/hal+json yêu cầu representation HAL. Content-Type của request POST là application/json vì body gửi lên là JSON.
4. Collection HAL có cấu trúc _embedded.people. Không nên giả định response collection là một JSON array thuần.
5. Test POST xác nhận status 201 Created và Location header. Header này trỏ tới resource mới; tránh hard-code ID được sinh tự động.
6. Dữ liệu được xóa và tạo lại trước từng test để test không phụ thuộc thứ tự chạy. Với dữ liệu có quan hệ hoặc test chạy song song, nên dùng fixture riêng, khóa định danh riêng hoặc database/schema cô lập.

Nếu repository có custom path hoặc custom collection relation, hãy cập nhật URL và JSONPath theo chính cấu hình đó. Nếu ứng dụng đặt base path bằng cấu hình Spring Data REST, URL trong test cũng phải tính cả base path.

## 5. Khi cần HTTP thật: khởi động server bằng RANDOM_PORT

Dùng RANDOM_PORT khi mục tiêu bao gồm embedded server hoặc hành vi mà MockMvc không mô phỏng đầy đủ. Spring Boot khuyến nghị port ngẫu nhiên để tránh xung đột với tiến trình khác và tránh phụ thuộc port cố định.

Ví dụ cho Spring Boot 3.5.x dùng TestRestTemplate:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class PersonHttpApiTests {

    @Autowired
    TestRestTemplate client;

    @Test
    void collectionIsReachableOverHttp() {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(
            MediaType.parseMediaType("application/hal+json")
        ));

        ResponseEntity<String> response = client.exchange(
            "/people",
            HttpMethod.GET,
            new HttpEntity<>(headers),
            String.class
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getHeaders().getContentType())
            .isCompatibleWith(MediaType.parseMediaType("application/hal+json"));
        assertThat(response.getBody()).contains("_embedded");
    }
}
~~~

TestRestTemplate được Spring Boot cấu hình cho test có server đang chạy. Đường dẫn tương đối như /people được gửi tới port ngẫu nhiên mà test server sử dụng.

Với Spring Boot 4.x, có thể dùng RestTestClient cùng @AutoConfigureRestTestClient:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureRestTestClient
class PersonHttpApiTests {

    @Autowired
    RestTestClient client;

    @Test
    void collectionIsReachableOverHttp() {
        client.get()
            .uri("/people")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/hal+json")
            );
    }
}
~~~

RestTestClient là lựa chọn client trong tài liệu Spring Boot 4.x. Kiểm tra package import theo phiên bản Boot và Spring Framework đang dùng. WebTestClient cũng có thể dùng với server thật; trong một số cấu hình MVC, nó cần spring-webflux trên classpath. Không thêm WebFlux chỉ để có một HTTP client nếu TestRestTemplate hoặc RestTestClient đã đáp ứng yêu cầu.

### Gọi trực tiếp bằng curl

Khi ứng dụng đã chạy ở môi trường local hoặc môi trường test, có thể smoke test endpoint bằng HTTP thật:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/people
~~~

Cách này hữu ích để xem status, response headers, content type và HAL body. Nó phù hợp cho kiểm tra nhanh hoặc smoke test sau deploy. Với CI, nên tự động hóa bằng HTTP client và cấu hình base URL rõ ràng thay vì phụ thuộc thao tác thủ công.

## 6. Chọn giữa MockMvc standalone và WebApplicationContext

Spring Framework hỗ trợ hai kiểu thiết lập MockMvc:

- **webAppContextSetup(WebApplicationContext)**: dùng Spring MVC configuration thực tế đã nạp. Đây là lựa chọn phù hợp cho integration test của Spring Data REST vì cần repository exporter và MVC infrastructure thực.
- **standaloneSetup(controller)**: truyền trực tiếp controller và dependency giả lập, không nạp Spring configuration. Phù hợp để kiểm tra hành vi riêng của một controller tự viết hoặc tái hiện nhanh một lỗi.

Ví dụ standalone:

~~~java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new GreetingController())
    .build();
~~~

Không thể dùng standalone setup để khẳng định Spring Data REST đã xuất repository đúng. Nó không tự khởi tạo toàn bộ Spring Data REST infrastructure. Nếu dùng standalone để test controller tùy chỉnh, vẫn cần một nhóm integration test khác để kiểm chứng cấu hình ứng dụng.

## 7. Checklist cho REST API được xuất từ repository

Chọn các trường hợp cần thiết theo tính năng ứng dụng. Không cần viết mọi test cho mọi repository.

| Khu vực | Điều nên xác nhận |
|---|---|
| Resource discovery | GET root trả 200; _links có relation của repository được xuất |
| Collection | GET collection trả đúng media type, dữ liệu, metadata và link |
| Item | GET item theo URI hợp lệ trả representation mong đợi; URI không tồn tại trả lỗi theo contract |
| Create | POST body hợp lệ tạo resource; kiểm tra 201 và Location |
| Update | PUT thay thế, PATCH cập nhật một phần; kiểm tra dữ liệu sau cập nhật và status theo cấu hình response body |
| Delete | DELETE xóa resource; GET sau đó xác nhận resource không còn |
| Search | Link search xuất hiện khi repository có query method được công bố; gọi query với tham số hợp lệ |
| Pagination và sorting | page, size, sort cho kết quả đúng; kiểm tra page metadata và các link điều hướng |
| Association | Link quan hệ có đúng relation; thao tác gắn/bỏ association dùng URI và media type phù hợp |
| Representation | HAL links, embedded relation, projection và trường JSON được serialize đúng |
| Validation | Input không hợp lệ bị từ chối theo validation rule và error contract của ứng dụng |
| Security | Endpoint yêu cầu authentication/authorization trả kết quả đúng cho anonymous, user hợp lệ và user thiếu quyền |
| Content negotiation | Accept và Content-Type được xử lý đúng; kiểm tra cả request JSON lẫn response HAL nếu API hỗ trợ |

Spring Data REST mặc định dùng HAL để biểu diễn link. Root resource cho phép client khám phá các relation được công bố. Collection resource thường hỗ trợ GET và POST; item resource thường hỗ trợ GET, PUT, PATCH và DELETE, tùy repository method và cấu hình export. Các HTTP method có thể không được xuất nếu repository không cung cấp method tương ứng hoặc method bị đánh dấu exported = false.

Đối với status code, GET thông thường trả 200; POST tạo resource trả 201. PUT, PATCH và DELETE có thể trả 200 hoặc 204 tùy cấu hình có trả response body hay không và Accept header. Vì vậy, hãy cố định response contract trong cấu hình ứng dụng trước khi viết assertion cho update/delete.

## 8. Dữ liệu test, transaction và tốc độ

### Transaction rollback không giống nhau ở hai kiểu test

Spring TestContext có thể rollback transaction của test sau mỗi test method. Điều này hữu ích khi test chạy trong cùng thread và transaction được chia sẻ.

Với RANDOM_PORT hoặc DEFINED_PORT, HTTP client và server chạy ở các thread riêng và dùng transaction riêng. Transaction do server xử lý request không nằm trong transaction của test method. Do đó, gắn @Transactional lên test không tự động rollback dữ liệu được tạo qua HTTP request.

Khi test qua server thật, hãy chọn một chiến lược dọn dữ liệu rõ ràng:

- Dùng database hoặc schema riêng cho test.
- Tạo fixture có khóa duy nhất và xóa sau test.
- Reset database trước mỗi suite hoặc mỗi nhóm test.
- Dùng Testcontainers để có datastore cô lập theo vòng đời test.

Không dựa vào transaction rollback của test method để dọn dữ liệu được ghi bởi HTTP request tới server thật.

### Giữ test nhanh và ổn định

- Dùng unit test cho quy tắc nghiệp vụ thuần; không cần khởi động Spring context cho mọi nhánh xử lý.
- Dùng @DataJpaTest cho truy vấn và mapping JPA; dùng integration test MVC cho endpoint được xuất.
- Dùng chung cấu hình test khi có thể. Spring TestContext cache ApplicationContext giữa các test có cùng cấu hình.
- Không thay đổi profile, properties hoặc imported configuration không cần thiết giữa các test vì có thể tạo nhiều context khác nhau.
- Dùng RANDOM_PORT thay vì một port cố định nếu cần server thật.
- Tránh assertion vào ID tự sinh, thứ tự dữ liệu không được bảo đảm hoặc absolute URL phụ thuộc host/port. Ưu tiên kiểm tra relation, path và contract.
- Khi database engine ảnh hưởng kết quả, chạy test với cùng loại engine thay vì chỉ dựa vào H2.

## 9. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| GET /people trả 404 | Sai base path, sai repository path, repository chưa được scan hoặc resource không được export | Gọi GET root để xem _links; kiểm tra @RepositoryRestResource, package scanning và cấu hình base path |
| GET /people trả 405 | findAll không được cung cấp hoặc bị tắt export | Kiểm tra repository interface và @RestResource(exported = false) |
| POST /people trả 405 | Repository không có save được export hoặc method bị vô hiệu hóa | Kiểm tra repository có CrudRepository/JpaRepository phù hợp và save có được export |
| 406 Not Acceptable | Accept yêu cầu representation không được endpoint hỗ trợ | Gửi Accept: application/hal+json hoặc application/json theo API |
| 415 Unsupported Media Type | Content-Type không khớp với body gửi lên | Với JSON request, đặt Content-Type: application/json |
| JSONPath không tìm thấy field collection | Test đang đọc JSON như array thuần nhưng response là HAL | Đọc dữ liệu qua _embedded.<collection-rel>; kiểm tra collectionResourceRel |
| Link trong assertion sai | Path hoặc relation đã được tùy chỉnh, base path thay đổi hoặc host/port khác | Kiểm tra _links và Location; tránh hard-code absolute URL |
| MockMvc test trả 401/403 | Security filter chain vẫn tham gia request và test chưa cung cấp authentication | Dùng Spring Security Test support, ví dụ @WithMockUser hoặc request postprocessor; chỉ tắt filter nếu đó thực sự là phạm vi test |
| @WebMvcTest không tìm thấy repository | Slice chỉ nạp nhóm MVC bean được hỗ trợ | Dùng @SpringBootTest cho endpoint Spring Data REST hoặc import cấu hình cần thiết một cách tường minh |
| Test HTTP để lại dữ liệu | Server xử lý request trong thread/transaction khác với test | Dọn dữ liệu bằng fixture/schema riêng; không trông chờ @Transactional của test rollback |
| Test context không tìm thấy cấu hình chính | Package của test không nằm dưới package có @SpringBootApplication hoặc có cấu hình scan đặc biệt | Đặt test đúng package hoặc chỉ định classes/configuration phù hợp |
| Test lỗi khi chạy song song | Các test dùng chung dữ liệu, ID hoặc database | Dùng dữ liệu định danh riêng, schema/database riêng hoặc tuần tự hóa nhóm test phụ thuộc nhau |

Khi gặp lỗi, hãy kiểm tra response thực tế trước: status, Content-Type, Location, body và HAL _links. Với endpoint Spring Data REST, GET root thường là cách nhanh để biết resource nào thực sự được công bố.

## 10. Chạy test

Chạy toàn bộ test:

Maven:

~~~bash
./mvnw test
~~~

Gradle:

~~~bash
./gradlew test
~~~

Chạy riêng một lớp test:

Maven:

~~~bash
./mvnw -Dtest=PersonRestApiTests test
~~~

Gradle:

~~~bash
./gradlew test --tests '*PersonRestApiTests'
~~~

Nếu test cần database ngoài, khởi động Testcontainers hoặc dịch vụ test theo cấu hình của dự án trước khi chạy. Đừng dùng lệnh chạy ứng dụng thay cho lệnh test: mục tiêu là để test runner tạo context/server, gửi request và đánh giá assertion tự động.

## 11. Tài liệu và ví dụ chính thức

- [Spring Boot Reference — Testing Spring Boot Applications (3.5)](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest, mock web environment, MockMvc, RANDOM_PORT, TestRestTemplate và test slices.
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/): starter và các module hỗ trợ test.
- [Spring Boot Reference — Testing Spring Boot Applications (4.1)](https://docs.spring.io/spring-boot/4.1/reference/testing/spring-boot-applications.html): API hiện hành cho MockMvc và RestTestClient.
- [Spring Framework Reference — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): MockMvc xử lý request Spring MVC bằng mock request/response.
- [Spring Framework Reference — MockMvc Setup Options](https://docs.spring.io/spring-framework/reference/testing/mockmvc/setup-options.html): so sánh WebApplicationContext và standalone setup.
- [Spring Framework Reference — MockMvc vs End-to-End Tests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/vs-end-to-end-integration-tests.html): giới hạn của mock servlet environment so với server thật.
- [Spring Data REST Reference — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection, item, association, search, HTTP methods, media type và status code.
- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/): tổng quan repository export, representation, validation, security và tùy chỉnh.
- [Spring Data Examples — thư mục REST](https://github.com/spring-projects/spring-data-examples/tree/main/rest): sample chính thức về headers/conditional GET, multi-store, projections, security, Starbucks và URI customization.
