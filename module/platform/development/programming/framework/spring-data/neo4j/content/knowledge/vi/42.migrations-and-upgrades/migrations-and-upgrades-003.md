# Chuyển annotation, session và API độ sâu từ hệ thống dùng OGM

Bài học này thuộc chương **Chuyển đổi và nâng cấp** của module **SPRING_DATA_NEO4J**. Nhiều ứng dụng cũ dùng Spring Data Neo4j kết hợp Neo4j-OGM (thường gọi là SDN+OGM) để ánh xạ node và relationship thành Java object. Khi chuyển sang Spring Data Neo4j thế hệ mới (SDN 6 trở lên), lớp Neo4j-OGM được loại bỏ. SDN dùng Spring Data Mapping Context và Neo4j Java Driver trực tiếp.

Đây là thay đổi về mô hình truy cập dữ liệu, không đơn thuần là thay tên package. Annotation, cách quản lý session, identity map, transaction, truy vấn và cách giới hạn số relationship được tải đều có khác biệt. Nếu chỉ đổi import rồi giữ nguyên cách sử dụng `Session.load(..., depth)` hoặc `@Depth`, ứng dụng sẽ không còn biên dịch hoặc có thể đọc/ghi một graph khác với mong đợi.

Bài học tập trung vào đường chuyển đổi từ SDN+OGM 5.x/Neo4j-OGM 3.x sang SDN 6+ và cách áp dụng tư duy đó ở các phiên bản SDN hiện hành. Hãy luôn kiểm tra ma trận tương thích giữa Spring Boot, Spring Framework, Spring Data Neo4j, Neo4j Java Driver và phiên bản Neo4j server trước khi chọn phiên bản đích.

## 1. Hiểu ranh giới giữa SDN+OGM và SDN mới

Trong kiến trúc cũ, Neo4j-OGM chịu trách nhiệm chính cho object graph mapping. `SessionFactory` tạo các `org.neo4j.ogm.session.Session`; session theo dõi entity đã tải, giữ cache trong phạm vi làm việc và phát hiện thay đổi để tạo Cypher khi gọi `save()`.

Trong SDN mới, Neo4j-OGM không còn là backend mapping và không được SDN sử dụng. SDN dùng Spring Data Mapping Context để đọc metadata của entity và thực hiện mapping. Neo4j Java Driver chịu trách nhiệm giao tiếp Bolt với server. SDN cung cấp các tầng truy cập tích hợp với Spring:

~~~text
SDN + Neo4j-OGM

Repository / Neo4jTemplate
          |
          v
     SessionFactory
          |
          v
    OGM Session
  (identity map, dirty tracking,
   load/save depth, transaction)
          |
          v
      OGM Driver
          |
          v
       Neo4j


Spring Data Neo4j mới

Repository
    |
    v
Neo4jTemplate --------> Neo4jClient
                              |
                              v
                       Neo4j Java Driver
                              |
                              v
                            Neo4j

Spring Mapping Context ánh xạ entity
Neo4jTransactionManager tích hợp transaction
~~~

Các thành phần tương ứng cần hiểu:

| Khái niệm cũ | Thành phần ở SDN mới | Vai trò |
|---|---|---|
| Neo4j-OGM mapping metadata | Spring Data Mapping Context | Đọc annotation và xây dựng metadata entity |
| `SessionFactory` | `Driver` do Spring Boot cấu hình cùng SDN infrastructure | Quản lý kết nối Bolt; không còn tạo OGM session |
| `org.neo4j.ogm.session.Session` | Repository, `Neo4jTemplate`, `Neo4jClient` | CRUD, truy vấn domain hoặc chạy Cypher |
| OGM Session transaction | `Neo4jTransactionManager` và `@Transactional` | Quản lý transaction Neo4j trong Spring |
| `Session.query(...)` | `Neo4jClient.query(...)` hoặc repository `@Query` | Thực thi Cypher và ánh xạ kết quả |
| OGM identity map/dirty tracking | Entity instance được quản lý theo từng thao tác mapping; gọi `save` tường minh | Không còn session cache theo dõi toàn bộ unit of work như OGM |
| `Session.load(..., depth)` / `@Depth` | Projection, custom Cypher và mô hình quan hệ có chủ đích | Xác định phần graph cần đọc |

Không nên giữ đồng thời hai bộ mapping cho cùng một entity. Neo4j-OGM có thể được dùng độc lập trong một ứng dụng Java khác, nhưng SDN mới không dùng OGM làm persistence backend. Hai lớp mapping riêng sẽ tạo ra hai cách hiểu entity và hai persistence context không đồng bộ.

## 2. Kiểm tra transport và dependency trước khi đổi code

SDN mới giao tiếp với Neo4j server qua Bolt. Nếu ứng dụng cũ dùng database embedded do OGM khởi chạy hoặc dùng HTTP transport của OGM, phải chuyển transport trước khi thay mapping.

| Cấu hình cũ | Yêu cầu khi chuyển sang SDN mới |
|---|---|
| OGM embedded driver và database nhúng trong ứng dụng | Triển khai Neo4j server độc lập hoặc cluster, sau đó kết nối bằng Bolt |
| OGM HTTP driver và endpoint HTTP | Chuyển sang Bolt URI như `bolt://host:7687` hoặc routing URI `neo4j://host:7687` |
| OGM Bolt driver | Có thể giữ URI Bolt hiện tại sau khi kiểm tra authentication và routing |

SDN mới không cung cấp embedded Neo4j và không hỗ trợ kết nối HTTP. Neo4j Test Harness có thể dùng trong test, nhưng không thay thế một database embedded production.

Khi chuyển dependency:

1. Loại bỏ các dependency `org.neo4j:neo4j-ogm-*` khỏi ứng dụng SDN mới.
2. Thêm `spring-boot-starter-data-neo4j` nếu dùng Spring Boot.
3. Dùng dependency management của Spring Boot hoặc Spring Data BOM để chọn các phiên bản tương thích.
4. Kiểm tra dependency tree để bảo đảm không còn OGM phiên bản cũ được kéo vào gián tiếp.
5. Không nâng đồng thời Neo4j server lên một major version khác nếu chưa có kế hoạch kiểm thử và nâng cấp DBMS riêng.

Ví dụ dependency Gradle cho ứng dụng Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-neo4j'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Không khai báo phiên bản tùy tiện cho Spring Data Neo4j và Neo4j Java Driver khi Spring Boot đã quản lý các dependency này. Nếu cần override, hãy kiểm tra rõ phiên bản Driver tương thích với SDN và Neo4j server.

## 3. Đổi cấu hình kết nối

Tên property kết nối trong Spring Boot thay đổi giữa SDN+OGM và SDN mới.

| Cấu hình SDN+OGM cũ | Cấu hình SDN mới |
|---|---|
| `spring.data.neo4j.uri` | `spring.neo4j.uri` |
| `spring.data.neo4j.username` | `spring.neo4j.authentication.username` |
| `spring.data.neo4j.password` | `spring.neo4j.authentication.password` |
| `spring.data.neo4j.embedded.enabled` | Không còn hỗ trợ |
| `org.neo4j.ogm.config.Configuration` bean | Cấu hình Neo4j Java Driver qua Spring Boot |

Ví dụ `application.yml` mới:

~~~yaml
spring:
  neo4j:
    uri: bolt://localhost:7687
    authentication:
      username: neo4j
      password: secret
~~~

Nếu dùng cluster hoặc Neo4j Aura, cấu hình URI và TLS theo môi trường thực tế. URI `neo4j://` dùng routing; URI `bolt://` kết nối trực tiếp tới endpoint. Không chuyển nguyên cấu hình OGM sang SDN mới mà không rà soát tên property, driver options, timeout và authentication.

SDN mới không còn cấu hình bằng XML theo cách cũ của OGM. Với Spring Boot, starter tự cấu hình phần lớn infrastructure. Nếu không dùng Boot, sử dụng các lớp cấu hình SDN như `AbstractNeo4jConfig` hoặc `AbstractReactiveNeo4jConfig` và khai báo repository/transaction infrastructure tương ứng.

## 4. Bảng chuyển annotation node và property

Các annotation chính chuyển sang package `org.springframework.data.neo4j.core.schema`.

| Annotation SDN+OGM/OGM cũ | Annotation SDN mới | Ghi chú |
|---|---|---|
| `@NodeEntity` | `@Node` | Khai báo lớp ánh xạ node |
| `@Id` | `@Id` của SDN | Dùng `org.springframework.data.neo4j.core.schema.Id` |
| `@GeneratedValue` | `@GeneratedValue` của SDN | Dùng cùng `@Id` khi cần ID do Neo4j/SDN sinh |
| `@Property` | `@Property` của SDN | Giữ tên property lưu trong graph |
| `@Relationship` | `@Relationship` của SDN | Giữ type và direction, rà soát import enum |
| `@RelationshipEntity` | `@RelationshipProperties` | Mô hình hóa property của relationship |
| `@StartNode`, `@EndNode` | `@TargetNode` và direction ở phía node sở hữu | Một relationship properties class có một target node |
| `@Fetch` / `@Depth` (nếu ứng dụng cũ sử dụng) | Không có annotation thay thế trực tiếp | Dùng projection hoặc custom Cypher để định nghĩa read shape |
| `@QueryResult` | Interface projection hoặc DTO projection | Với mapping tùy biến phức tạp, dùng `Neo4jClient` |

Ví dụ OGM cũ:

~~~java
import java.util.Set;

import org.neo4j.ogm.annotation.GeneratedValue;
import org.neo4j.ogm.annotation.Id;
import org.neo4j.ogm.annotation.NodeEntity;
import org.neo4j.ogm.annotation.Property;
import org.neo4j.ogm.annotation.Relationship;

@NodeEntity(label = "Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @Property(name = "full_name")
    private String name;

    @Relationship(type = "KNOWS", direction = Relationship.OUTGOING)
    private Set<Person> friends;
}
~~~

Phiên bản SDN mới:

~~~java
import java.util.HashSet;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Property;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.Relationship.Direction;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @Property("full_name")
    private String name;

    @Relationship(type = "KNOWS", direction = Direction.OUTGOING)
    private Set<Person> friends = new HashSet<>();

    public Long getId() {
        return id;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

`@Node("Person")` giữ label graph hiện tại. `@Property("full_name")` giữ tên property hiện tại. Đổi tên class Java không bắt buộc phải đổi label hoặc property trong Neo4j nếu mapping vẫn trỏ về tên cũ.

Hãy so sánh dữ liệu thực tế trước và sau migration. Không tự ý đổi label hoặc relationship type chỉ vì tên class Java đã thay đổi.

## 5. Chú ý identity và GeneratedValue

ID là một phần của hợp đồng mapping. Trước khi đổi annotation, xác định entity cũ đang dùng loại ID nào:

- Internal Neo4j ID được OGM sinh.
- ID do ứng dụng hoặc hệ thống bên ngoài cấp.
- Business key như email, mã khách hàng hoặc mã đơn hàng.

Với internal ID, SDN mới có thể dùng `@Id @GeneratedValue`. Với ID do ứng dụng cấp, dùng `@Id` và gán giá trị trước khi lưu; không thêm `@GeneratedValue` nếu không muốn framework sinh ID.

Ví dụ business key:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personCode;

    private String name;

    public Person(String personCode, String name) {
        this.personCode = personCode;
        this.name = name;
    }
}
~~~

Không đổi internal ID sang business key hoặc ngược lại chỉ để làm cho code mới biên dịch. Nếu muốn thay chiến lược ID, hãy lập kế hoạch backfill property, tạo uniqueness constraint, cập nhật quan hệ tham chiếu và kiểm tra tất cả query đang dùng ID cũ.

Đối với entity có `@Version`, kiểm tra riêng optimistic locking sau khi mapping. Không dùng version như business ID và không tự tăng version trong code nghiệp vụ.

## 6. Chuyển RelationshipEntity sang RelationshipProperties

OGM dùng một class `@RelationshipEntity` có cả `@StartNode` và `@EndNode`. Trong SDN mới, class mang property của relationship được đánh dấu `@RelationshipProperties`. Một field `@TargetNode` trỏ tới node ở đầu bên kia; node đang khai báo field `@Relationship` là đầu còn lại. `direction` quyết định chiều từ node sở hữu.

Ví dụ OGM cũ:

~~~java
import org.neo4j.ogm.annotation.EndNode;
import org.neo4j.ogm.annotation.GeneratedValue;
import org.neo4j.ogm.annotation.Id;
import org.neo4j.ogm.annotation.RelationshipEntity;
import org.neo4j.ogm.annotation.StartNode;

@RelationshipEntity(type = "RATED")
public class Rating {

    @Id
    @GeneratedValue
    private Long id;

    @StartNode
    private User user;

    @EndNode
    private Movie movie;

    private Integer stars;
}
~~~

Trong SDN mới, khai báo relationship từ phía `User`:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.Relationship.Direction;

@Node("User")
public class User {

    @Id
    private String id;

    @Relationship(type = "RATED", direction = Direction.OUTGOING)
    private List<Rating> ratings = new ArrayList<>();
}
~~~

Class relationship properties:

~~~java
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Rating {

    @RelationshipId
    private Long id;

    private Integer stars;

    @TargetNode
    private Movie movie;

    public Rating(Movie movie, Integer stars) {
        this.movie = movie;
        this.stars = stars;
    }

    public Movie getMovie() {
        return movie;
    }

    public Integer getStars() {
        return stars;
    }
}
~~~

Các điểm cần kiểm tra:

- `@RelationshipProperties` thay vai trò class `@RelationshipEntity`.
- `@RelationshipId` giữ internal relationship ID để SDN phân biệt các relationship khi ghi. Đây không phải ID nghiệp vụ của `Movie` hoặc `User`.
- `@TargetNode` chỉ xuất hiện đúng một lần trong relationship properties class.
- Node sở hữu field `@Relationship` đóng vai trò đầu bên kia; không khai báo cả `@StartNode` và `@EndNode` như OGM.
- `type` và `direction` phải khớp relationship type và hướng thực tế trong graph.
- Property như `stars`, `joinedAt`, `role` vẫn là property trên relationship.

SDN mặc định dùng direction `OUTGOING`. Dù vậy, khi chuyển code cũ, hãy khai báo direction tường minh để tránh đọc nhầm cạnh hoặc truy vấn thiếu relationship.
Trong ví dụ này, `User` là đầu nguồn và `Movie` là target, nên graph được ánh xạ thành `(User)-[:RATED]->(Movie)`. Nếu quan hệ trong graph có chiều ngược lại, đổi `direction` và xác định lại node được đặt ở `@TargetNode`.

## 7. Thay SessionFactory và OGM Session

OGM `SessionFactory` là factory của persistence session. OGM `Session` giữ cache entity, theo dõi object đã tải và quản lý load/save depth. Những đối tượng này không còn trong SDN mới.

SDN mới cung cấp ba mức truy cập:

| Thành phần | Khi nào dùng |
|---|---|
| `Neo4jRepository` | CRUD, finder method và query khai báo |
| `Neo4jTemplate` | Thao tác domain tổng quát khi không muốn tạo repository cho từng entity |
| `Neo4jClient` | Chạy Cypher tùy biến, ánh xạ record thủ công hoặc trả kết quả không phải domain entity |

`Driver` vẫn có thể được inject để sử dụng API cấp thấp. Tuy nhiên, transaction mở trực tiếp bằng Driver không tự tham gia Spring-managed transaction. Nếu thao tác cần phối hợp với `@Transactional`, ưu tiên repository, template hoặc client.

### Chuyển thao tác load và save

OGM cũ:

Giả sử `session` đã được mở và `fullName` là giá trị đầu vào của method:

~~~java
import org.neo4j.ogm.session.Session;
import org.neo4j.ogm.session.SessionFactory;

public class PersonService {

    private final SessionFactory sessionFactory;

    public PersonService(SessionFactory sessionFactory) {
        this.sessionFactory = sessionFactory;
    }

    public Person rename(Long id, String name) {
        Session session = sessionFactory.openSession();
        Person person = session.load(Person.class, id, 1);
        person.setName(name);
        session.save(person, -1);
        return person;
    }
}
~~~

SDN mới với repository:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonService {

    private final PersonRepository personRepository;

    public PersonService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @Transactional
    public Person rename(Long id, String name) {
        Person person = personRepository.findById(id)
            .orElseThrow();

        person.setName(name);
        return personRepository.save(person);
    }
}
~~~

Repository:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, Long> {
}
~~~

Trong SDN mới, gọi `save()` tường minh để ghi thay đổi. Không giả định object tự được dirty-check rồi tự lưu khi method kết thúc. Entity trả về từ repository là object Java được ánh xạ; không phải object đang được một OGM session theo dõi suốt request.

### Khi cần chạy Cypher trực tiếp

OGM cũ:

~~~java
session.query(
    "MATCH (p:Person {full_name: $fullName}) RETURN p.full_name AS name",
    Map.of("fullName", fullName)
);
~~~

SDN mới với `Neo4jClient`:

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class PersonQueries {

    private final Neo4jClient neo4jClient;

    public PersonQueries(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Optional<String> findName(String fullName) {
        return neo4jClient.query("""
                MATCH (p:Person {full_name: $fullName})
                RETURN p.full_name AS name
                """)
            .bind(fullName).to("fullName")
            .fetchAs(String.class)
            .mappedBy((typeSystem, record) -> record.get("name").asString())
            .one();
    }
}
~~~

`Neo4jClient` có API bind parameter và ánh xạ record, đồng thời tích hợp Spring transaction. Không nối dữ liệu đầu vào trực tiếp vào chuỗi Cypher.

## 8. Phân biệt OGM Session với Neo4j Driver Session

Tên `Session` vẫn tồn tại trong Neo4j Java Driver, nhưng đó là một API khác:

| OGM `Session` | Driver `Session` |
|---|---|
| Quản lý mapping và cache object graph | Mở kênh làm việc với database qua Driver |
| Có `load`, `loadAll`, `save`, `delete` entity | Có `run` và transaction function |
| Theo dõi entity đã tải và thay đổi | Không theo dõi domain entity của ứng dụng |
| Có API depth cho load/save | Không có API depth mapping |
| Là một phần của OGM persistence context | Không thay thế repository hoặc Neo4jTemplate |

Ví dụ Driver Session cấp thấp:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public long countPeople(Driver driver) {
    try (Session session = driver.session()) {
        return session.run(
                "MATCH (p:Person) RETURN count(p) AS total")
            .single()
            .get("total")
            .asLong();
    }
}
~~~

Đoạn code này chạy Cypher và đọc record thô. Driver không tự chuyển record thành entity SDN và không tự tham gia transaction do Spring quản lý. Hãy đóng Driver Session đúng vòng đời và dùng transaction API của Driver nếu thao tác cấp thấp cần transaction riêng.

Không đổi `org.neo4j.ogm.session.Session` thành `org.neo4j.driver.Session` rồi giữ nguyên các lời gọi `load`, `save`, `loadAll` hoặc `depth`. Các method đó không tồn tại trên Driver Session.

## 9. Vì sao @Depth và load horizon bị loại bỏ?

OGM có persistence horizon (depth) để giới hạn số hop relationship được load hoặc save:

| Giá trị OGM | Ý nghĩa thường gặp |
|---:|---|
| `0` | Chỉ load property của node gốc |
| `1` | Node gốc và các node láng giềng trực tiếp |
| `2` | Mở rộng thêm một lớp relationship |
| `-1` | Không giới hạn depth theo cấu hình load/save |

OGM `Session` còn giữ session cache. Nếu cùng entity được load nhiều lần trong một session với depth khác nhau, graph trong cache có thể tiếp tục mở rộng và giữ các relationship đã tải ở depth lớn hơn.

SDN mới không có `@Depth` hoặc tham số số nguyên tương đương trong repository. SDN xây dựng query dựa trên toàn bộ graph có thể đi tới từ các relationship được khai báo trong domain model. Không có một con số depth mặc định để cắt graph theo số hop.

Điều này có hai hệ quả:

1. Một entity có nhiều relationship hoặc mapping hai chiều có thể làm query đi xa hơn dự kiến.
2. Không thể dùng `@Depth(0)` để yêu cầu một repository method chỉ đọc property gốc trong khi vẫn trả về toàn bộ domain entity như trước.

Nếu model khai báo `Person.friends`, rồi `Person` lại khai báo `friends` hai chiều hoặc nhiều nhánh quan hệ khác, SDN có thể cần truy vấn cả những nhánh có thể đi tới từ model đó. Với graph rộng, query có thể trả nhiều dữ liệu hơn màn hình hoặc use case thực sự cần.

Không nên cố thay `@Depth(1)` bằng cách xóa các relationship khỏi entity domain dùng chung. Hãy xác định read shape theo từng use case.

## 10. Thay depth đọc bằng projection

Projection là cách phù hợp khi một màn hình hoặc API chỉ cần một phần thuộc tính và relationship. SDN hỗ trợ interface projection, DTO projection và projection lồng nhiều cấp.

Ví dụ projection dưới đây dùng entity có assigned ID dạng `String` được lưu trong property `id`; đây là read model minh họa riêng với entity dùng internal ID ở phần trước.

Giả sử entity domain:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    @Relationship(type = "KNOWS")
    private List<Person> friends = new ArrayList<>();

    public String getName() {
        return name;
    }

    public List<Person> getFriends() {
        return friends;
    }
}
~~~

Projection chỉ lấy tên:

~~~java
public interface PersonNameView {
    String getName();
}
~~~

Projection lồng để lấy bạn bè trực tiếp:

~~~java
import java.util.List;

public interface PersonWithFriendsView {

    String getName();

    List<FriendView> getFriends();

    interface FriendView {
        String getName();
    }
}
~~~

Repository có thể khai báo method projection:

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    Optional<PersonNameView> findNameById(String id);

    Optional<PersonWithFriendsView> findDetailsById(String id);
}
~~~

Projection xác định rõ dữ liệu cần chuyển qua mạng. `PersonNameView` chỉ cần tên; `PersonWithFriendsView` chỉ cần tên và danh sách bạn bè trực tiếp. Nếu cần thêm cấp lồng, khai báo thêm nested projection thay vì yêu cầu OGM depth bằng số.

Projection phù hợp cho read model. Không mặc định rằng projection interface có thể được chỉnh sửa rồi lưu như một entity thông thường. Nếu cần cập nhật, tải entity phù hợp hoặc tạo domain object từ dữ liệu projection theo quy tắc nghiệp vụ.

## 11. Thay depth bằng custom Cypher và DTO

Khi query cần điều kiện, traversal hoặc aggregation riêng, dùng `@Query` và DTO. Đây là cách thay cho nhiều trường hợp OGM `Session.query()` hoặc `@QueryResult`.

Ví dụ chỉ cần tên người và tên những người bạn:

~~~java
import java.util.List;

public record PersonDetails(
    String name,
    List<String> friends
) {
}
~~~

Repository:

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person {id: $id})
        OPTIONAL MATCH (p)-[:KNOWS]->(friend:Person)
        RETURN p.name AS name,
               collect(friend.name) AS friends
        """)
    Optional<PersonDetails> findDetails(@Param("id") String id);
}
~~~

Cypher quyết định số hop và kiểu dữ liệu được trả. Ở ví dụ này chỉ lấy một bước `KNOWS`, không trả toàn bộ entity graph.

Khi dùng custom query trả về domain entity, query phải cung cấp đủ cấu trúc mà mapping cần. Nếu chỉ trả root node trong khi domain entity có nhiều relationship, object kết quả có thể là một phần graph. Không nên dùng object partial đó làm đầu vào cho `save()`, vì SDN xem domain object được gửi lên là mô tả trạng thái cần lưu và có thể xóa hoặc thay đổi relationship không được tải.

Quy tắc an toàn:

- Query shape cho màn hình/report: trả projection hoặc DTO.
- Query trả entity để tiếp tục cập nhật: bảo đảm mapping đủ các field và relationship cần bảo toàn.
- Query cần mapping phức tạp không khớp entity: dùng `Neo4jClient` và mapper riêng.
- Không dùng một DTO đọc báo cáo như entity command để ghi lại graph.

## 12. Thay @QueryResult bằng projection hoặc Neo4jClient

OGM cũ có thể dùng `@QueryResult` để ánh xạ một hàng Cypher vào class kết quả tùy chỉnh. Trong SDN mới, arbitrary result mapping qua annotation này không còn được hỗ trợ.

Chọn cách thay thế theo loại kết quả:

| Kết quả cũ | Cách thay trong SDN mới |
|---|---|
| Một entity hoặc collection entity | Repository method hoặc `@Query` trả entity đã mapping |
| Một vài field scalar | Interface projection hoặc DTO |
| Kết quả tổng hợp, nhiều alias | DTO projection với tên alias khớp field/constructor |
| Map hoặc cấu trúc driver-specific | `Neo4jClient.fetchAs(...).mappedBy(...)` |
| Kết quả không phải domain và cần xử lý đặc biệt | Custom repository fragment dùng `Neo4jClient` |

Ví dụ custom mapping với `Neo4jClient`:

~~~java
public record RelationSummary(String personName, String relationType) {
}
~~~

~~~java
import java.util.List;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class RelationSummaryQueries {

    private final Neo4jClient client;

    public RelationSummaryQueries(Neo4jClient client) {
        this.client = client;
    }

    public List<RelationSummary> findRelations(String movieTitle) {
        return client.query("""
                MATCH (person:Person)-[r]->(:Movie {title: $title})
                RETURN person.name AS personName,
                       type(r) AS relationType
                """)
            .bind(movieTitle).to("title")
            .fetchAs(RelationSummary.class)
            .mappedBy((typeSystem, record) ->
                new RelationSummary(
                    record.get("personName").asString(),
                    record.get("relationType").asString()
                )
            )
            .all();
    }
}
~~~

`Neo4jClient` không tự suy ra domain model từ mọi cột trả về. Bạn chủ động ánh xạ từng record và giữ query/result contract rõ ràng.

## 13. Thay automatic index manager và các annotation schema

Neo4j-OGM từng cung cấp automatic index manager với các annotation như `@Index`, `@CompositeIndex` và `@Required`. SDN mới không thay thế các annotation này bằng annotation domain tương đương.

Thay vào đó, quản lý index và constraint bằng migration có version, ví dụ dùng Neo4j Migrations hoặc công cụ migration schema tương tự.

Ví dụ OGM:

~~~java
@CompositeIndex(properties = {"tagline", "released"})
public class Movie {

    @Index(unique = true)
    private String title;

    private String tagline;

    @Required
    private Integer released;
}
~~~

Ví dụ migration Cypher cho Neo4j hiện đại:

~~~cypher
CREATE CONSTRAINT movie_title_unique IF NOT EXISTS
FOR (m:Movie)
REQUIRE m.title IS UNIQUE;

CREATE INDEX movie_tagline_released_index IF NOT EXISTS
FOR (m:Movie)
ON (m.tagline, m.released);
~~~

`@Index(unique = true)` chuyển thành uniqueness constraint. `@CompositeIndex` chuyển thành index nhiều property. `@Required` cần được xem xét thành existence constraint nếu phiên bản và edition Neo4j mục tiêu hỗ trợ, hoặc được kiểm tra bằng validation trong ứng dụng/migration.

Không tạo index/constraint ngay trong mỗi lần ứng dụng khởi động. Migration schema có version giúp kiểm soát thứ tự rollout, dữ liệu hiện có, constraint vi phạm và nhiều phiên bản ứng dụng cùng hoạt động.

## 14. Bookmark management không cần cấu hình như OGM cũ

Các thành phần OGM/Spring Data cũ như:

- `@EnableBookmarkManagement`
- `@UseBookmark`
- `BookmarkManager`
- `CaffeineBookmarkManager`

đã bị loại khỏi quy trình cấu hình SDN mới. SDN tự sử dụng bookmark cho các transaction để hỗ trợ causal consistency, không cần bật annotation hoặc khai báo Caffeine bookmark manager theo cách cũ.

Hãy xóa cấu hình và dependency chỉ phục vụ bookmark manager cũ sau khi kiểm tra không còn code riêng đang tham chiếu chúng. Nếu ứng dụng có yêu cầu đặc biệt về bookmark, dùng API bookmark manager được hỗ trợ bởi phiên bản SDN hiện hành và kiểm thử riêng.

## 15. Transaction và truy cập Driver trực tiếp

Trong SDN mới, `Neo4jClient`, `Neo4jTemplate` và repository tích hợp với transaction của Spring. Có thể dùng `@Transactional` để gom nhiều thao tác repository và client vào cùng transaction.

Ví dụ:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonCommandService {

    private final PersonRepository repository;
    private final Neo4jClient client;

    public PersonCommandService(
            PersonRepository repository,
            Neo4jClient client) {
        this.repository = repository;
        this.client = client;
    }

    @Transactional
    public void createPersonAndMarker(Person person) {
        Person saved = repository.save(person);

        client.query("""
                CREATE (:AuditMarker {personId: $id})
                """)
            .bind(saved.getId()).to("id")
            .run();
    }
}
~~~

Nếu dùng `Driver` trực tiếp, transaction do Driver quản lý không tự tham gia Spring transaction. Hãy chỉ dùng Driver cấp thấp khi cần API mà client không cung cấp, và tự quản lý transaction/commit/rollback trong phạm vi thao tác đó.

Không trộn hai transaction độc lập trong một nghiệp vụ rồi kỳ vọng chúng rollback cùng nhau. Đây là một trong các lỗi phổ biến khi chuyển từ OGM session sang Driver Session.

## 16. Lưu ý quan trọng về session cache và partial graph

OGM Session giữ identity map và session cache. Trong cùng session, load lại một entity có thể trả object đã được cache; subgraph có thể mở rộng khi các relationship khác được load. OGM còn theo dõi những thay đổi trong object graph để tạo Cypher cập nhật delta.

SDN mới không giữ OGM session cache và không dựa vào dirty tracking theo cùng cơ chế. Mỗi lần đọc tạo object theo kết quả mapping của query. Vì vậy:

- Không giả định hai lần gọi repository luôn trả cùng một Java object instance.
- Không giả định object giữ trạng thái đồng bộ tự động với database sau khi một transaction khác cập nhật.
- Gọi `save()` tường minh khi muốn ghi thay đổi.
- Sau custom query chỉ trả một phần graph, không dùng object đó để ghi toàn bộ aggregate nếu chưa tải đủ dữ liệu cần bảo toàn.
- Tránh giữ entity qua nhiều request như một session-managed object.

Nếu cần xử lý một graph aggregate, hãy xác định rõ aggregate root, các relationship được sở hữu và ranh giới cập nhật. Nếu chỉ cần đọc, dùng projection/DTO để tránh biến kết quả đọc thành một graph command không đầy đủ.

## 17. Trình tự migration đề xuất

Chia chuyển đổi thành các giai đoạn có thể xác minh độc lập:

### Giai đoạn 1: Kiểm kê ứng dụng OGM

- Ghi nhận phiên bản Spring Data Neo4j, Neo4j-OGM, Spring Boot và Neo4j server.
- Tìm tất cả import `org.neo4j.ogm.*`.
- Tìm `SessionFactory`, `Session`, `@Depth`, `@Fetch`, `@QueryResult`.
- Tìm `@RelationshipEntity`, `@StartNode`, `@EndNode`.
- Tìm `@Index`, `@CompositeIndex`, `@Required` và bookmark manager.
- Liệt kê custom Cypher, transaction và code dùng Driver trực tiếp.

### Giai đoạn 2: Chuẩn hóa kết nối

- Chuyển database embedded sang Neo4j server nếu còn sử dụng.
- Chuyển HTTP transport sang Bolt.
- Xác nhận authentication, TLS, routing và database selection.
- Kiểm tra ứng dụng OGM cũ hoạt động ổn định qua Bolt trước khi thay mapping.

### Giai đoạn 3: Chuyển dependency và cấu hình

- Loại bỏ OGM dependencies.
- Thêm starter SDN mới.
- Đổi property URI/authentication.
- Để Spring Boot quản lý Driver và transaction infrastructure.
- Xác minh ứng dụng khởi động và kết nối được database.

### Giai đoạn 4: Chuyển entity mapping

- Đổi `@NodeEntity` thành `@Node`.
- Đổi import `@Id`, `@GeneratedValue`, `@Property`, `@Relationship`.
- Chuyển relationship entity sang `@RelationshipProperties`.
- Chuyển endpoint mapping sang `@TargetNode` và direction rõ ràng.
- Kiểm tra ID strategy, label, property name, relationship type và direction.

### Giai đoạn 5: Chuyển session và transaction

- Đổi `Session.load` thành repository finder hoặc template load.
- Đổi `Session.save` thành repository/template save.
- Đổi `Session.query` thành `Neo4jClient` hoặc `@Query`.
- Đổi transaction sang Spring `@Transactional`/transaction manager.
- Loại bỏ OGM session cache, dirty tracking và code phụ thuộc identity map.

### Giai đoạn 6: Chuyển depth và result mapping

- Xóa `@Depth` và tham số depth trong session methods.
- Tạo projection/DTO cho từng read use case.
- Viết custom Cypher cho traversal đặc biệt.
- Thay `@QueryResult` bằng DTO projection hoặc custom mapper.
- Kiểm tra không lưu object partial được trả về từ query chỉ đọc một phần graph.

### Giai đoạn 7: Chuyển schema và bookmark

- Chuyển index/constraint annotations sang migration Cypher có version.
- Xác minh constraint trên dữ liệu hiện có trước khi tạo.
- Xóa cấu hình bookmark OGM cũ.
- Xác nhận bookmark management của SDN hoạt động theo cấu hình mới.

### Giai đoạn 8: Kiểm thử và triển khai

- Kiểm thử repository CRUD và mapping.
- Kiểm thử các relationship có property.
- So sánh kết quả query quan trọng giữa ứng dụng cũ và mới.
- Kiểm thử rollback, transaction và concurrency.
- Đo query plan, số record trả về và memory khi thay depth bằng projections.
- Triển khai theo môi trường staging trước production và có kế hoạch rollback ứng dụng.

## 18. Checklist xác minh sau migration

| Hạng mục | Câu hỏi cần xác nhận |
|---|---|
| Dependency | Không còn OGM backend trong ứng dụng SDN mới? |
| Transport | Mọi kết nối dùng Bolt và URI đúng môi trường? |
| Authentication | Username/password/TLS được chuyển đúng? |
| Node mapping | Label cũ được giữ nguyên? |
| Property mapping | Tên property graph không bị đổi ngoài dự kiến? |
| Identity | Business key/internal ID vẫn trỏ đúng node? |
| Relationship | Type, direction và cardinality được giữ nguyên? |
| Relationship properties | Property class có `@RelationshipId` và đúng một `@TargetNode`? |
| Session | Không còn phụ thuộc OGM identity map hoặc dirty tracking? |
| Depth | Mỗi read use case đã có projection hoặc Cypher tương ứng? |
| Result mapping | `@QueryResult` đã chuyển thành DTO/projection/custom mapping? |
| Partial graph | Không ghi lại domain object được load thiếu relationship? |
| Schema | Index/constraint được quản lý qua migration và đã xác minh? |
| Bookmark | Cấu hình OGM cũ đã được gỡ? |
| Transaction | Repository, Template và Client tham gia đúng Spring transaction? |
| Performance | Query mới không tải nhiều graph hơn use case cần? |

## 19. Những lỗi thường gặp khi chuyển đổi

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Ứng dụng không khởi động do thiếu class OGM | Code vẫn import `org.neo4j.ogm.*` hoặc dependency cũ bị xóa | Thay annotation và API bằng SDN mới |
| Không kết nối được database | Vẫn dùng embedded/HTTP hoặc property cũ | Dùng Bolt và property `spring.neo4j.*` |
| Entity đọc được nhưng ghi sai label | `@Node` không giữ label cũ | Đặt label rõ bằng `@Node("OldLabel")` |
| Relationship không được hydrate | Direction hoặc type sai | So sánh mapping với dữ liệu graph và khai báo direction tường minh |
| Relationship properties không lưu | Thiếu `@RelationshipId` hoặc `@TargetNode` | Bổ sung đúng metadata theo SDN |
| Code không còn biên dịch với `@Depth` | API depth đã bị loại bỏ | Dùng projection hoặc custom Cypher |
| Query tải quá nhiều node | SDN đi theo các relationship được khai báo trong model, đặc biệt mapping hai chiều | Giới hạn read shape bằng projection/DTO và xem lại domain mapping |
| Save làm mất relationship | Entity trả về từ custom query không chứa đủ graph | Không save partial entity; tải đầy đủ hoặc dùng DTO cho read |
| `@QueryResult` không còn hoạt động | SDN không hỗ trợ arbitrary mapping theo annotation OGM | Dùng DTO projection hoặc `Neo4jClient` |
| Index không được tạo lúc startup | Automatic index manager đã bị loại | Tạo migration Cypher có version |
| Bookmark class không tìm thấy | Bookmark manager OGM đã bị loại | Xóa cấu hình cũ và dùng cơ chế bookmark tự động |
| Thao tác Driver không rollback cùng service | Driver transaction độc lập Spring transaction | Dùng Neo4jClient/Template hoặc quản lý transaction riêng có chủ đích |
| Dữ liệu trong object cũ không cập nhật | Trước đây code dựa vào session cache/identity map | Đọc lại entity trong transaction mới khi cần dữ liệu mới nhất |

## 20. Nguyên tắc cần nhớ

- SDN mới không dùng Neo4j-OGM; hãy loại bỏ OGM dependencies khi chuyển.
- SDN mới cần Bolt và Neo4j server, không dùng embedded database hoặc HTTP transport.
- `@NodeEntity` chuyển thành `@Node`; annotation mapping dùng package SDN schema.
- `@RelationshipEntity` chuyển thành `@RelationshipProperties`, endpoint còn lại được đánh dấu `@TargetNode`.
- OGM `SessionFactory` và OGM `Session` không tương đương với Neo4j Driver `Session`.
- Repository, `Neo4jTemplate` và `Neo4jClient` là các abstraction chính trong SDN.
- `@Depth` và load/save depth không có tham số số nguyên thay thế trực tiếp.
- Projection và custom Cypher xác định phần graph cần đọc; tránh mapping hai chiều không cần thiết.
- Không ghi lại domain object được trả về từ một query chỉ hydrate một phần graph.
- `@QueryResult` chuyển thành projection, DTO hoặc custom mapping bằng `Neo4jClient`.
- `@Index`, `@CompositeIndex` và `@Required` cần được thay bằng schema migration có version.
- Bookmark management được SDN thực hiện tự động; gỡ cấu hình OGM cũ.
- Driver transaction trực tiếp không tự tham gia Spring-managed transaction.
- Kiểm thử label, property, ID, relationship direction, query shape và transaction trước khi triển khai.

Chuyển từ Neo4j-OGM sang Spring Data Neo4j mới là thay đổi về persistence architecture. Khi đã thay annotation, session và depth API đúng cách, ứng dụng sẽ dùng Spring Mapping Context, Neo4j Java Driver và các abstraction repository/client/template thống nhất. Điều quan trọng nhất là xác định lại graph nào được đọc và ghi cho từng use case, để query mới không vô tình tải quá nhiều dữ liệu hoặc ghi đè những relationship chưa được tải.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.2 – Migrating from SDN+OGM to SDN](https://docs.spring.io/spring-data/neo4j/reference/appendix/migrating.html)
- [Spring Data Neo4j 8.2 – Metadata-based Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j 8.2 – Projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Spring Data Neo4j 6.1 – Neo4j Client and SDN building blocks](https://docs.spring.io/spring-data/neo4j/docs/6.1.0/reference/html/)
- [Neo4j-OGM Manual – Load depth and Session API](https://neo4j.com/docs/ogm-manual/current/reference/)
- [Neo4j Cypher Manual – Indexes and constraints](https://neo4j.com/docs/cypher-manual/current/schema/)
