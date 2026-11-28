# Auto-configuration của Spring Boot cho driver và Spring Data Neo4j

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích Spring Boot auto-configuration chuẩn bị các thành phần cần thiết để ứng dụng kết nối Neo4j.
- Cấu hình Neo4j Java Driver bằng các thuộc tính **spring.neo4j.\***.
- Hiểu vai trò của **Driver**, **Neo4jClient**, **Neo4jTemplate**, mapping context, repository và transaction manager.
- Biết khi nào nên dùng cấu hình mặc định và khi nào cần khai báo bean tùy chỉnh.
- Chẩn đoán các lỗi cấu hình thường gặp và kiểm tra ứng dụng sau khi khởi động.

## 1. Vì sao cần auto-configuration?

Một ứng dụng Spring Data Neo4j cần nhiều thành phần phối hợp để chuyển lời gọi Java thành thao tác trên Neo4j. Ở mức cơ bản, ứng dụng cần:

- Neo4j Java Driver để mở kết nối và gửi lệnh đến máy chủ Neo4j.
- Thành phần truy cập dữ liệu như Neo4jClient hoặc Neo4jTemplate.
- Mapping context và converter để chuyển đổi giữa node/relationship với domain object.
- Hạ tầng repository để cung cấp các phương thức lưu, tìm và truy vấn entity.
- Transaction manager để Spring quản lý ranh giới giao dịch.

Nếu tự tạo từng bean trong mọi ứng dụng, cấu hình sẽ dài và dễ không đồng nhất. Spring Boot auto-configuration dựa trên dependency có trong classpath, cấu hình ứng dụng và các bean đã được khai báo để thiết lập các thành phần phù hợp.

Với ứng dụng dùng Spring Boot, dependency khởi đầu thường là:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-neo4j")
}
~~~

Hoặc Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-neo4j</artifactId>
</dependency>
~~~

Nên dùng dependency management của Spring Boot để chọn phiên bản tương thích cho Spring Data Neo4j và Neo4j Java Driver. Tránh tự nâng riêng driver hoặc Spring Data Neo4j lên một phiên bản không tương thích với phiên bản Boot đang sử dụng.

## 2. Kiến trúc các thành phần được cấu hình

Luồng tổng quát khi ứng dụng khởi động có thể hình dung như sau:

~~~text
Spring Boot application
        |
        v
Auto-configuration + application properties
        |
        v
Neo4j Java Driver
        |
        +-----------------------+
        |                       |
        v                       v
   Neo4jClient             Transaction manager
        |                       |
        v                       |
   Neo4jTemplate                |
        |                       |
        +-----------+-----------+
                    |
                    v
       Mapping context + entity converter
                    |
                    v
       Spring Data Neo4j repositories
                    |
                    v
             Neo4j database
~~~

Các thành phần có trách nhiệm riêng:

| Thành phần | Vai trò |
|---|---|
| **Driver** | Quản lý kết nối, session và việc gửi lệnh đến Neo4j |
| **Neo4jClient** | Cung cấp API truy vấn mức thấp hơn, hỗ trợ chạy Cypher và ánh xạ kết quả |
| **Neo4jTemplate** | Cung cấp thao tác hướng entity và hỗ trợ các tác vụ persistence |
| Mapping context | Giữ metadata về domain class, node label, ID và property |
| Entity converter | Chuyển đổi dữ liệu đồ thị thành đối tượng Java và ngược lại |
| Repository | Cung cấp các thao tác CRUD, truy vấn dẫn xuất và truy vấn khai báo |
| Transaction manager | Kết hợp giao dịch Neo4j với cơ chế transaction của Spring |

Đây là sơ đồ khái niệm. Chi tiết bean và cách khởi tạo có thể thay đổi theo phiên bản Spring Boot và Spring Data Neo4j, nhưng vai trò của các thành phần vẫn là nền tảng để đọc và chẩn đoán cấu hình.

## 3. Cấu hình kết nối bằng application.yml

Trong cấu hình mặc định, Spring Boot đọc các thuộc tính dưới namespace **spring.neo4j** để tạo và cấu hình Neo4j Driver.

Ví dụ môi trường phát triển chạy Neo4j ở máy cục bộ:

~~~yaml
spring:
  neo4j:
    uri: neo4j://localhost:7687
    authentication:
      username: neo4j
    database: neo4j
~~~

Ý nghĩa:

- **spring.neo4j.uri**: địa chỉ kết nối đến Neo4j. Cổng Bolt mặc định thường là **7687**.
- **spring.neo4j.authentication.username**: tài khoản dùng để xác thực.
- **spring.neo4j.authentication.password**: mật khẩu tương ứng, có thể được cấp qua biến môi trường.
- **spring.neo4j.database**: database đích khi máy chủ hỗ trợ nhiều database và ứng dụng cần chọn một database cụ thể.

Một URI thường gặp là **bolt://localhost:7687** khi kết nối trực tiếp đến một máy chủ. Với môi trường cần routing, chẳng hạn cluster, URI dạng **neo4j://** có thể được sử dụng để driver áp dụng cơ chế routing phù hợp. Hãy chọn scheme và cấu hình bảo mật theo cách triển khai Neo4j thực tế.

Không nên ghi mật khẩu thật vào file cấu hình được commit lên Git. Spring Boot có thể đọc mật khẩu từ biến môi trường **SPRING_NEO4J_AUTHENTICATION_PASSWORD**; cùng cách đó, URI, username và database cũng có thể được cấp qua môi trường triển khai.

Các biến môi trường thường dùng:

~~~text
SPRING_NEO4J_URI=neo4j://localhost:7687
SPRING_NEO4J_AUTHENTICATION_USERNAME=neo4j
SPRING_NEO4J_AUTHENTICATION_PASSWORD=<secret>
SPRING_NEO4J_DATABASE=neo4j
~~~

Cách này phù hợp với container, máy chủ triển khai và pipeline CI/CD vì thông tin nhạy cảm được quản lý bên ngoài source code.

## 4. Những gì Spring Boot thiết lập từ cấu hình

Khi starter có mặt trên classpath và ứng dụng không cung cấp bean thay thế, auto-configuration có thể chuẩn bị các thành phần chính.

### Neo4j Driver

Driver là điểm kết nối nền tảng. Nó quản lý connection pool và tạo session để thực thi truy vấn. Ứng dụng thông thường nên dùng một Driver được quản lý như bean dùng chung, thay vì tự tạo một driver mới cho mỗi request.

Các thuộc tính kết nối được đọc từ **spring.neo4j.\***. Driver cần URI, thông tin xác thực và các tùy chọn phù hợp với môi trường. Nếu kết nối thất bại, những lỗi như URI sai, máy chủ chưa chạy, cổng bị chặn hoặc credential không hợp lệ thường xuất hiện ở giai đoạn này.

### Neo4jClient và Neo4jTemplate

Từ Driver, hạ tầng SDN cung cấp các API để thao tác dữ liệu.

- Dùng **Neo4jClient** khi cần kiểm soát truy vấn Cypher và xử lý kết quả theo dạng record hoặc projection.
- Dùng **Neo4jTemplate** khi muốn làm việc ở mức entity và các thao tác persistence của Spring Data Neo4j.
- Dùng repository khi thao tác phù hợp với phương thức CRUD, truy vấn dẫn xuất hoặc một truy vấn Cypher khai báo.

Không phải ứng dụng nào cũng cần inject cả ba thành phần. Hãy chọn API theo độ phức tạp của thao tác và mức kiểm soát cần thiết.

### Mapping context và converter

SDN cần biết lớp Java nào tương ứng với node nào. Mapping context quản lý metadata từ các domain type; converter sử dụng metadata đó khi chuyển đổi dữ liệu.

Ví dụ:

~~~java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String fullName;
}
~~~

Khi repository lưu hoặc đọc Person, SDN dùng metadata để xác định nhãn Person, trường ID và property fullName. Annotation chỉ mô tả mapping; node được ghi xuống database khi ứng dụng thực hiện thao tác ghi.

### Repository infrastructure

Repository được xây dựng từ domain type và ID type:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    Optional<Person> findOneByFullName(String fullName);
}
~~~

Trong ứng dụng Spring Boot thông thường, repository được phát hiện dựa trên package scanning của ứng dụng. Nếu interface nằm dưới package gốc của lớp **@SpringBootApplication**, cấu hình mặc định thường đã đủ.

Nếu repository nằm ngoài phạm vi scan, có thể đặt lớp ứng dụng ở package gốc phù hợp hoặc cấu hình phạm vi repository rõ ràng bằng **@EnableNeo4jRepositories**:

~~~java
@Configuration
@EnableNeo4jRepositories(
    basePackages = "com.example.graph.repositories"
)
public class Neo4jRepositoryConfiguration {
}
~~~

Chỉ cần khai báo rõ phạm vi khi cấu trúc package yêu cầu. Tránh thêm annotation cấu hình lặp lại nếu auto-configuration đã phát hiện repository đúng.

### Transaction manager

Spring Data Neo4j tích hợp transaction của Spring với giao dịch Neo4j. Với cấu hình tiêu chuẩn, ứng dụng có thể đánh dấu nghiệp vụ bằng **@Transactional**:

~~~java
@Service
public class PersonService {

    private final PersonRepository people;

    public PersonService(PersonRepository people) {
        this.people = people;
    }

    @Transactional
    public Person rename(String id, String newName) {
        Person person = people.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Person not found"));

        person.setFullName(newName);
        return people.save(person);
    }
}
~~~

Ranh giới giao dịch nên đặt quanh nghiệp vụ gồm các thao tác cần cùng thành công hoặc rollback. Không cần mở transaction thủ công cho từng lệnh nếu Spring đã quản lý ranh giới phù hợp.

Lưu ý rằng **@Transactional** thường được thực thi thông qua proxy Spring. Gọi một phương thức transactional từ một phương thức khác trong cùng instance (self-invocation) có thể bỏ qua proxy và khiến transaction không được áp dụng như mong đợi. Hãy đặt nghiệp vụ transactional ở bean được gọi qua Spring proxy.

## 5. Một ứng dụng Spring Boot tối thiểu

Ví dụ cấu trúc package:

~~~text
com.example.films
    FilmApplication.java
    domain/
        Person.java
    repository/
        PersonRepository.java
    service/
        PersonService.java
~~~

Lớp khởi động:

~~~java
@SpringBootApplication
public class FilmApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilmApplication.class, args);
    }
}
~~~

Entity:

~~~java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String fullName;

    protected Person() {
        // Constructor phục vụ cơ chế tạo entity của persistence framework.
    }

    public Person(String personId, String fullName) {
        this.personId = personId;
        this.fullName = fullName;
    }

    public String getPersonId() {
        return personId;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }
}
~~~

Repository:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, String> {
}
~~~

Service:

~~~java
@Service
public class PersonService {

    private final PersonRepository people;

    public PersonService(PersonRepository people) {
        this.people = people;
    }

    @Transactional
    public Person create(String id, String name) {
        return people.save(new Person(id, name));
    }

    @Transactional(readOnly = true)
    public Optional<Person> find(String id) {
        return people.findById(id);
    }
}
~~~

Với dependency starter và cấu hình kết nối hợp lệ, Spring Boot có thể tạo các bean cần thiết để inject PersonRepository vào service. Không cần tự khởi tạo Driver, client, template hoặc transaction manager trong ví dụ tiêu chuẩn này.

## 6. Tách cấu hình theo môi trường

Thông tin kết nối ở máy phát triển thường khác môi trường kiểm thử và production. Spring Boot hỗ trợ profile để giữ cấu hình theo từng môi trường.

Ví dụ cấu hình mặc định không chứa mật khẩu:

~~~yaml
# application.yml
spring:
  application:
    name: film-service
  neo4j:
    uri: neo4j://localhost:7687
    authentication:
      username: neo4j
    database: neo4j
~~~

Khi chạy profile production, có thể cung cấp các biến môi trường tương ứng:

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_NEO4J_URI=neo4j+s://graph.example.com
SPRING_NEO4J_AUTHENTICATION_USERNAME=film-service
SPRING_NEO4J_AUTHENTICATION_PASSWORD=<secret-from-secret-manager>
SPRING_NEO4J_DATABASE=neo4j
~~~

URI **neo4j+s://** yêu cầu kết nối bảo mật theo cơ chế TLS được driver hỗ trợ. Chứng chỉ và trust configuration cần phù hợp với môi trường máy chủ. Không nên tắt kiểm tra chứng chỉ để xử lý tạm thời lỗi kết nối production.

Một số nguyên tắc cấu hình:

- Mỗi môi trường dùng URI và credential riêng.
- Lưu mật khẩu trong secret manager hoặc cơ chế quản lý secret của nền tảng triển khai.
- Cấp quyền database tối thiểu cần thiết cho tài khoản ứng dụng.
- Không bật log chứa credential hoặc dữ liệu nhạy cảm.
- Kiểm tra kết nối từ chính môi trường chạy ứng dụng, vì hostname và network route trong container có thể khác máy phát triển.

## 7. Khi nào cần tùy chỉnh bean Driver?

Cấu hình thuộc tính là đủ cho phần lớn ứng dụng. Tuy nhiên, đôi khi cần cấu hình Driver bằng Java, chẳng hạn để thiết lập một tùy chọn đặc thù, cơ chế xác thực riêng hoặc trust strategy theo hạ tầng.

Ví dụ khung cấu hình:

~~~java
@Configuration
public class CustomNeo4jDriverConfiguration {

    @Bean
    Driver neo4jDriver(Environment environment) {

        String uri = environment.getRequiredProperty("spring.neo4j.uri");
        String username = environment.getRequiredProperty(
            "spring.neo4j.authentication.username"
        );
        String password = environment.getRequiredProperty(
            "spring.neo4j.authentication.password"
        );

        return GraphDatabase.driver(
            uri,
            AuthTokens.basic(username, password)
        );
    }
}
~~~

Ví dụ cần các import tương ứng từ Neo4j Driver và Spring, chẳng hạn Driver, GraphDatabase, AuthTokens, Configuration, Bean và Environment. Khi dùng trong dự án thật, hãy bổ sung các tùy chọn kết nối và trust phù hợp với môi trường. Driver là tài nguyên dài hạn và nên được Spring quản lý vòng đời. Không tạo driver mới trong mỗi lần gọi service hoặc request.

Auto-configuration của Spring Boot thường được thiết kế để lùi lại khi ứng dụng đã cung cấp bean tương ứng. Vì vậy, khi tự khai báo Driver, hãy kiểm tra các bean còn lại mà SDN cần vẫn được tạo từ Driver đó. Nếu tự thay thế thêm Neo4jClient, Neo4jTemplate hoặc transaction manager, bạn cũng phải bảo đảm chúng dùng cùng cấu hình và cùng nguồn kết nối mong muốn.

Không nên tùy chỉnh bean chỉ để thay đổi URI, username hoặc password; các thuộc tính **spring.neo4j.\*** đã dành cho mục đích đó. Cấu hình Java nên dành cho nhu cầu mà property không diễn đạt được.

## 8. Kiểm tra auto-configuration khi ứng dụng khởi động

Nếu ứng dụng không khởi động được, nên phân loại lỗi theo từng lớp:

1. **Dependency:** starter có nằm trong runtime classpath không? Phiên bản Spring Boot và SDN có được quản lý đồng bộ không?
2. **Property binding:** URI và thông tin xác thực có được nạp từ đúng file/profile/biến môi trường không?
3. **Network và authentication:** ứng dụng có truy cập được hostname, cổng và database không? Tài khoản có đăng nhập được không?
4. **Bean creation:** Driver, client, template hoặc transaction manager có bị thiếu hay bị khai báo trùng không?
5. **Repository scanning:** repository có nằm trong phạm vi package scanning và domain type có mapping hợp lệ không?
6. **Query và mapping:** Cypher có trả về hình dạng dữ liệu phù hợp với kiểu Java khai báo không?

Có thể bật log cấu hình của Spring Boot trong môi trường phát triển để xem auto-configuration nào được áp dụng hoặc bị bỏ qua. Với condition evaluation report, kiểm tra điều kiện classpath, property và bean hiện có để hiểu lý do một cấu hình không được tạo.

Không nên bật debug hoặc log chi tiết một cách tùy tiện trong production nếu log có thể chứa dữ liệu nhạy cảm. Hãy giới hạn phạm vi và thời gian bật chẩn đoán.

Một số lỗi phổ biến:

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Không tạo được Driver | URI sai, thiếu cấu hình xác thực hoặc driver không có trong classpath | Kiểm tra starter, property và log khởi tạo |
| Connection refused | Neo4j chưa chạy, sai cổng hoặc ứng dụng không truy cập được máy chủ | Kiểm tra trạng thái server, network và cổng |
| Authentication failure | Username/password sai hoặc credential chưa được nạp | Kiểm tra biến môi trường và quyền tài khoản |
| Không tìm thấy repository bean | Repository nằm ngoài phạm vi scan hoặc cấu hình repository không được kích hoạt | Kiểm tra package của application và repository |
| No qualifying bean cho API SDN | Auto-configuration bị loại trừ hoặc bean cần thiết đã bị thay thế không đầy đủ | Kiểm tra condition report và các bean tùy chỉnh |
| Truy vấn chạy nhưng không có kết quả | Sai database, nhãn, property hoặc dữ liệu chưa được tạo | Kiểm tra database đích và chạy Cypher trực tiếp |
| Lỗi mapping khi đọc kết quả | Kiểu trả về không khớp dữ liệu Cypher trả về | Trả về node phù hợp, projection hoặc DTO tương ứng |

## 9. Kiểm thử cấu hình Neo4j

Kiểm thử cấu hình cần xác nhận cả Spring context và khả năng kết nối đến Neo4j.

Với kiểm thử tích hợp toàn ứng dụng, có thể dùng **@SpringBootTest** để khởi tạo context gần với cấu hình chạy thật. Với kiểm thử tập trung vào repository và mapping, Spring Data Neo4j cung cấp test slice **@DataNeo4jTest** ở các phiên bản tương ứng. Test slice chỉ nạp một phần context; nó vẫn cần một Neo4j server hoặc test database phù hợp để thực thi truy vấn.

Ví dụ kiểm tra repository trong integration test:

~~~java
@DataNeo4jTest
class PersonRepositoryTest {

    @Autowired
    private PersonRepository people;

    @Test
    void savesAndLoadsPerson() {
        Person saved = people.save(
            new Person("person-test-1", "An")
        );

        Optional<Person> loaded = people.findById("person-test-1");

        assertThat(loaded).isPresent();
        assertThat(loaded.get().getFullName()).isEqualTo("An");
    }
}
~~~

Ví dụ giả định entity có constructor và getter tương ứng như phần trước. Cấu hình test phải trỏ đến database thử nghiệm có thể truy cập; không dùng database production để chạy test ghi dữ liệu.

Nếu dùng Testcontainers, có thể khởi chạy Neo4j riêng cho test và cung cấp URI/credential của container vào Spring context bằng cơ chế dynamic properties tương ứng với phiên bản Spring Boot và Testcontainers. Cách này giúp test độc lập với Neo4j đang cài trên máy cá nhân.

## 10. Checklist cấu hình trước khi triển khai

Trước khi đưa ứng dụng lên môi trường dùng chung, hãy xác nhận:

- Starter Spring Data Neo4j được khai báo và phiên bản tương thích với Spring Boot.
- URI trỏ đúng máy chủ và database.
- Credential được lấy từ nguồn secret an toàn.
- Tài khoản có quyền vừa đủ cho thao tác của ứng dụng.
- Repository nằm trong phạm vi scanning.
- Entity có nhãn và định danh phù hợp.
- Transaction manager và các thao tác transactional hoạt động theo ranh giới nghiệp vụ.
- Kiểm thử tích hợp chạy trên database thử nghiệm.
- Log không làm lộ mật khẩu, token hoặc dữ liệu nhạy cảm.
- Pool và timeout được đánh giá theo tải thực tế thay vì giữ nguyên cấu hình phát triển một cách máy móc.

## Kết luận

Spring Boot auto-configuration giảm đáng kể công việc thiết lập Spring Data Neo4j. Với starter phù hợp và các thuộc tính **spring.neo4j.\***, ứng dụng có thể nhận được Driver, client/template, mapping infrastructure, repository và transaction integration mà không phải tự tạo từng bean.

Hãy bắt đầu bằng cấu hình property và để Boot quản lý vòng đời các thành phần mặc định. Chỉ khai báo bean tùy chỉnh khi có yêu cầu kỹ thuật rõ ràng, đồng thời kiểm tra các thành phần SDN còn lại có dùng đúng Driver. Khi chẩn đoán sự cố, đi từ dependency và property đến kết nối, bean creation, repository scanning rồi mapping/query; cách phân lớp này giúp tìm nguyên nhân nhanh và giữ cấu hình nhất quán giữa các môi trường.
