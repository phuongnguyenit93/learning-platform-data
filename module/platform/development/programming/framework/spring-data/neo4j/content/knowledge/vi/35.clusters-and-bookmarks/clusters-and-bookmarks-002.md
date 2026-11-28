# Định tuyến đọc–ghi trong cụm Neo4j

Một cụm Neo4j có thể có nhiều máy chủ để phân phối tải và duy trì khả năng sẵn sàng. Trong kiến trúc causal clustering, các máy chủ giữ vai trò xử lý ghi và xử lý đọc. Ứng dụng cần gửi transaction ghi đến máy chủ có quyền ghi, đồng thời tận dụng các máy chủ đọc khi truy vấn chỉ đọc.

Spring Data Neo4j (SDN) sử dụng Neo4j Java Driver để kết nối và định tuyến. Driver có thể tự lấy routing table từ cụm, còn SDN truyền thông tin read-only của transaction xuống driver. Vì vậy, để phân phối tải đúng, ứng dụng phải khai báo rõ thao tác nào chỉ đọc và thao tác nào có thể ghi. SDN không phân tích nội dung Cypher để tự suy luận điều đó.

## 1. Vai trò của primary, secondary và routing table

Trong cụm Neo4j, các máy chủ có vai trò khác nhau:

- **Primary/writer:** nhận và điều phối transaction ghi. Primary cũng có thể phục vụ truy vấn đọc.
- **Secondary/reader:** phục vụ truy vấn đọc và nhận các thay đổi được đồng bộ từ primary. Reader không nhận transaction ghi thông thường.
- **Router:** điểm truy cập mà driver dùng để lấy thông tin định tuyến. Một cụm có thể công bố nhiều địa chỉ router để tránh phụ thuộc vào một máy duy nhất.

Driver không cần ứng dụng tự chọn tên máy chủ cho từng truy vấn. Với routing driver, driver lấy routing table gồm các địa chỉ phù hợp cho thao tác đọc, ghi và lấy thông tin định tuyến. Routing table được làm mới theo thời hạn hoặc khi driver phát hiện thông tin cũ, chẳng hạn writer hiện tại không còn nhận ghi.

```text
                         Neo4j Java Driver
                                  |
                            Routing table
                                  |
                  +---------------+---------------+
                  |                               |
             WRITE transaction              READ transaction
                  |                               |
                  v                               v
              Primary / Writer               Reader pool
                  |                          +----+----+
                  |                          |         |
                  v                          v         v
             Commit changes              Secondary  Secondary
                  |
                  +------ replication -------> Readers
```

Sơ đồ thể hiện hướng định tuyến khái quát. Thành viên thực tế được chọn dựa trên routing table, trạng thái cụm và cấu hình routing policy; ứng dụng không nên gắn cứng logic nghiệp vụ với một địa chỉ máy chủ cụ thể.

## 2. Chọn URI để bật routing

Scheme trong URI quyết định loại driver được tạo:

| URI scheme | Hành vi |
|---|---|
| `neo4j://` | Tạo routing driver, có thể khám phá thành viên cụm và định tuyến theo access mode |
| `neo4j+s://` | Routing driver với TLS và chứng chỉ CA được tin cậy |
| `neo4j+ssc://` | Routing driver với TLS, chấp nhận self-signed certificate theo cấu hình driver |
| `bolt://` | Kết nối trực tiếp tới host được chỉ định, không tự định tuyến trong cụm |
| `bolt+s://` | Kết nối Bolt trực tiếp với TLS và chứng chỉ CA được tin cậy |
| `bolt+ssc://` | Kết nối Bolt trực tiếp với TLS và self-signed certificate theo cấu hình driver |

Với ứng dụng kết nối cụm, thông thường dùng `neo4j://` hoặc biến thể TLS mà hạ tầng yêu cầu. `bolt://` chỉ phù hợp khi chủ đích kết nối trực tiếp một máy chủ, chẳng hạn công cụ quản trị hoặc một cấu hình đặc biệt. Nếu dùng Bolt direct URI, driver không lấy routing table để tự phân phối đọc–ghi qua các thành viên.

Ví dụ cấu hình Spring Boot:

```properties
spring.neo4j.uri=neo4j+s://<cluster-endpoint>
spring.neo4j.authentication.username=${NEO4J_USERNAME}
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
spring.data.neo4j.database=neo4j
```

`<cluster-endpoint>` là địa chỉ do quản trị viên Neo4j cung cấp. Với cụm tự quản lý không dùng TLS, URI có thể là `neo4j://<cluster-host>:7687`. Với Aura hoặc môi trường yêu cầu TLS, dùng scheme và endpoint tương ứng. Không tự đổi scheme chỉ để thử kết nối; scheme phải phù hợp cấu hình bảo mật và routing của server.

Driver cần truy cập được các địa chỉ mà cụm quảng bá trong routing table. DNS, firewall và `server.routing.advertised_address` phải được cấu hình sao cho ứng dụng có thể kết nối tới các địa chỉ đó. Nếu chỉ một seed endpoint được cấu hình và endpoint đó ngừng hoạt động trước khi driver lấy được routing table, việc khởi tạo kết nối có thể thất bại; môi trường production nên có phương án endpoint/DNS/resolver phù hợp.

## 3. READ và WRITE là access mode của transaction

Neo4j Java Driver dùng hai access mode chính:

| Access mode | Mục đích | Máy chủ được chọn trong cụm |
|---|---|---|
| `AccessMode.READ` | Transaction chỉ đọc | Một máy chủ thuộc nhóm reader theo routing table |
| `AccessMode.WRITE` | Transaction có thể thay đổi dữ liệu | Primary/writer có quyền ghi |

Khi driver thực thi transaction đọc, routing driver có thể chọn reader. Transaction ghi được định tuyến đến writer. Trên một Neo4j server đơn lẻ, khác biệt định tuyến này không có ý nghĩa vì máy chủ đó phục vụ cả đọc và ghi.

Một điểm dễ nhầm: access mode mô tả quyền truy cập mà transaction yêu cầu, không phải cơ chế phân tích Cypher. Nếu một transaction được đánh dấu READ nhưng câu lệnh lại chạy `CREATE`, `SET`, `DELETE` hoặc procedure có ghi dữ liệu, server reader sẽ từ chối thao tác. Ngược lại, một truy vấn chỉ đọc nhưng chạy trong transaction WRITE vẫn có thể thành công, song nó không tận dụng được khả năng phân phối đọc tới reader.

## 4. Driver mặc định dùng WRITE nếu không chỉ định

Theo mặc định, session của Neo4j Java Driver có access mode WRITE. Lý do là driver không phân tích Cypher để biết một chuỗi truy vấn có thể ghi dữ liệu hay không; procedure và custom query cũng có thể thay đổi graph.

Khi dùng Java Driver trực tiếp, hãy chọn transaction API thể hiện đúng ý định:

```java
import java.util.List;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public List<String> findNames(Driver driver) {
    try (Session session = driver.session(
            SessionConfig.builder()
                .withDatabase("neo4j")
                .build())) {

        return session.executeRead(tx ->
            tx.run("MATCH (p:Person) RETURN p.name AS name")
                .list(record -> record.get("name").asString())
        );
    }
}
```

`executeRead` tạo transaction đọc và cho routing driver biết có thể chọn reader. Với thao tác ghi, dùng `executeWrite`:

```java
import java.util.Map;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public void createPerson(Driver driver, String name) {
    try (Session session = driver.session(
            SessionConfig.builder()
                .withDatabase("neo4j")
                .build())) {

        session.executeWrite(tx -> {
            tx.run("CREATE (:Person {name: $name})", Map.of("name", name))
                .consume();
            return null;
        });
    }
}
```

Các phương thức `executeRead` và `executeWrite` tự chọn access mode tương ứng cho transaction. Nếu dùng auto-commit `session.run(...)` hoặc tự cấu hình session, cần hiểu access mode mặc định và đặt `withDefaultAccessMode(AccessMode.READ)` khi thật sự chỉ đọc. Không dùng READ làm cách phân quyền; quyền truy cập dữ liệu vẫn phải được quản lý bằng user/role của Neo4j.

Trong ứng dụng Spring Data Neo4j, thông thường không cần tự tạo session như ví dụ này. Hãy khai báo read-only bằng transaction annotation để SDN và driver phối hợp định tuyến.

## 5. Đánh dấu truy vấn đọc bằng @Transactional(readOnly = true)

SDN không phân tích Cypher để nhận biết truy vấn chỉ đọc. Vì vậy, phần lớn thao tác được xem là read-write theo mặc định để bảo đảm custom query có thể thực hiện ghi. Các finder dựng sẵn như `findById`, `findAllById`, `findAll` và các phương thức existential được định nghĩa sẵn đã được đánh dấu read-only.

Ví dụ dưới đây giả định entity `Person` có các property `personId`, `city` và `name`:

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    @Version
    private Long version;

    private String city;
    private String name;

    protected Person() {
    }

    public Person(String personId, String name) {
        this.personId = personId;
        this.name = name;
    }

    public String getPersonId() {
        return personId;
    }

    public void rename(String newName) {
        this.name = newName;
    }
}
```

Với service chỉ đọc, khai báo:

```java
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonQueryService {

    private final PersonRepository personRepository;

    public PersonQueryService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @Transactional(readOnly = true)
    public List<Person> findPeople(String city) {
        return personRepository.findByCity(city);
    }
}
```

Khi method được gọi qua Spring transaction proxy, `readOnly = true` được chuyển thành transaction read-only. Routing driver có thể định tuyến transaction này đến reader trong cụm.

Nếu toàn bộ repository chỉ phục vụ đọc, có thể đặt `@Transactional(readOnly = true)` ở cấp interface repository. Nếu repository có cả đọc và ghi, nên đánh dấu từng method hoặc đặt transaction ở service theo đúng nghiệp vụ.

## 6. Derived query và custom @Query cần khai báo rõ

Một derived finder thường chỉ đọc, nhưng SDN không tự đánh dấu mọi method do người dùng định nghĩa là read-only. Custom `@Query` càng cần cẩn trọng vì Cypher có thể chứa `MERGE`, `CREATE`, `SET`, `DELETE` hoặc gọi procedure có side effect.

Ví dụ repository có cả hai loại method:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.transaction.annotation.Transactional;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Transactional(readOnly = true)
    List<Person> findByCity(String city);

    @Transactional
    @Query("""
        MATCH (p:Person {personId: $personId})
        SET p.lastSeenAt = datetime()
        RETURN p
        """)
    Person markAsSeen(String personId);
}
```

`findByCity` được khai báo read-only để có thể định tuyến tới reader. `markAsSeen` thay đổi property nên phải chạy trong transaction read-write và được định tuyến tới writer.

Không đánh dấu một method là read-only chỉ vì tên của nó bắt đầu bằng `find`. Nếu custom Cypher gọi procedure, hãy kiểm tra procedure đó có ghi dữ liệu, tạo log hoặc gây side effect hay không. Tương tự, nếu một method được đánh dấu read-only nhưng bên trong gọi một service khác thực hiện ghi trong cùng transaction, thiết kế đó không phù hợp và có thể thất bại trên reader.

## 7. Phân biệt transaction read-only và read-write trong service

Một service có thể chứa cả hai luồng. Có thể đặt read-only ở cấp class rồi ghi đè trên method ghi:

```java
import java.util.Optional;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class PersonService {

    private final PersonRepository repository;

    public PersonService(PersonRepository repository) {
        this.repository = repository;
    }

    public Optional<Person> getPerson(String personId) {
        return repository.findById(personId);
    }

    @Transactional
    public Person rename(String personId, String newName) {
        Person person = repository.findById(personId)
            .orElseThrow();
        person.rename(newName);
        return repository.save(person);
    }
}
```

`getPerson` tham gia transaction read-only. `rename` ghi đè metadata transaction ở cấp method bằng transaction read-write. Khi method được gọi qua Spring proxy, các thao tác repository bên trong tham gia transaction tương ứng.

Nếu service gọi nhiều repository trong cùng method, tất cả thao tác thuộc cùng transaction và cùng access mode. Không thể kỳ vọng một lệnh đọc trong transaction read-write tự được chuyển sang reader trong khi lệnh ghi trong cùng transaction chạy ở writer; routing được xác định cho transaction, không phải từng câu lệnh độc lập.

## 8. Custom procedure và truy vấn có side effect

Một truy vấn có thể trông giống truy vấn đọc nhưng gọi procedure thực hiện ghi. Ví dụ procedure có thể cập nhật node, tạo relationship, ghi audit hoặc kích hoạt tác vụ phụ. Vì SDN không phân tích được logic bên trong procedure, method gọi nó không nên mặc định là read-only.

Trước khi đánh dấu custom query là read-only, hãy xác minh:

- Tất cả clause Cypher chỉ đọc dữ liệu.
- Procedure được gọi không ghi node, relationship hoặc property.
- Không có trigger/hành vi mở rộng ở phía server làm thay đổi dữ liệu.
- Method không gọi tiếp service ghi trong cùng transaction.

Nếu không thể chứng minh truy vấn chỉ đọc, hãy để transaction read-write. Điều đó có thể giảm khả năng offload sang reader, nhưng tránh gửi một thao tác ghi tới máy chủ không có quyền ghi.

## 9. Bookmark bảo đảm đọc được dữ liệu vừa ghi

Trong cụm, một transaction ghi được thực hiện trên primary và các thay đổi được đồng bộ đến các reader theo tiến trình replication. Có thể có một khoảng thời gian ngắn reader chưa áp dụng xong thay đổi mới nhất. Nếu ứng dụng ghi xong rồi ngay lập tức đọc từ một reader bất kỳ mà không có causal consistency, nó có nguy cơ nhận dữ liệu cũ.

Neo4j giải quyết thứ tự nhân quả bằng **bookmark**. Bookmark là token biểu thị một transaction đã commit và trạng thái mà transaction sau cần quan sát. Khi transaction sau mang bookmark đó, driver chỉ bắt đầu đọc trên một thành viên đã đạt ít nhất trạng thái tương ứng. Nếu reader chưa theo kịp, truy vấn có thể phải chờ hoặc được định tuyến lại theo cơ chế của driver/cụm.

Spring Data Neo4j tự quản lý bookmark cho các transaction, không cần thêm annotation hoặc cấu hình riêng trong trường hợp thông thường. Các transaction nối tiếp trong cùng thread imperative hoặc cùng reactive stream có thể đọc được thay đổi mà transaction trước đó vừa commit.

Ví dụ service ghi rồi đọc tiếp:

```java
import java.util.Optional;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonWorkflow {

    private final PersonRepository repository;

    public PersonWorkflow(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Person create(String personId, String name) {
        return repository.save(new Person(personId, name));
    }

    @Transactional(readOnly = true)
    public Optional<Person> read(String personId) {
        return repository.findById(personId);
    }
}
```

Khi caller gọi `create` rồi gọi `read` như hai lời gọi riêng biệt trên cùng thread, mỗi method có transaction riêng. SDN tự quản lý bookmark để transaction đọc sau tôn trọng transaction ghi trước. Nếu hai method được gọi nội bộ bằng `this.method()` trong cùng bean, Spring proxy không tạo transaction boundary riêng như mong đợi; hãy gọi qua bean được Spring quản lý.

Bookmark không phải bản sao dữ liệu, không khóa reader và cũng không buộc mọi truy vấn sau đó phải đọc dữ liệu mới nhất của mọi người dùng trên toàn cụm. Nó bảo đảm transaction sau tôn trọng các transaction nằm trong chuỗi nhân quả được bookmark chỉ ra.

## 10. Khi nào cần truyền bookmark giữa các luồng độc lập?

Trong một ứng dụng SDN thông thường, bookmark management tự động đã đủ. Tuy nhiên, có thể cần chuyển bookmark ra ngoài khi một workflow đi qua nhiều JVM, nhiều ứng dụng hoặc một thành phần dùng Neo4j Driver trực tiếp cần tiếp tục đọc sau khi một thành phần khác đã ghi.

SDN phát `Neo4jBookmarksUpdatedEvent` khi bookmark được cập nhật. Ứng dụng có thể lắng nghe sự kiện này để thu thập bookmark, lưu hoặc truyền nó theo cơ chế thread-safe của hệ thống. Khi cần khởi tạo transaction manager với bookmark từ bên ngoài, có thể cấu hình `Neo4jBookmarkManager` với một supplier cung cấp các bookmark cần seed.

Đây là phần tích hợp nâng cao, không phải bước cấu hình bắt buộc cho mọi cluster. Cần xác định rõ ai sở hữu bookmark, cách đồng bộ giữa instance và thời điểm xóa bookmark cũ. Không chia sẻ một tập bookmark mutable giữa các thread mà không có cơ chế an toàn đồng thời.

Không dùng các annotation `@EnableBookmarkManagement` hoặc `@UseBookmark` của Neo4j-OGM cũ. Cơ chế bookmark hiện tại của Spring Data Neo4j đã tự động và không cần các annotation đó.

## 11. Vì sao không nên tắt bookmark management tùy tiện?

SDN cung cấp `Neo4jBookmarkManager.noop()` để bỏ qua việc lưu và gửi bookmark. Khi dùng manager này, các transaction không còn mang thông tin causal consistency do SDN quản lý.

Trong một cụm có replication bất đồng bộ, lần đọc tiếp theo có thể đến reader chưa áp dụng xong thay đổi vừa ghi. Ứng dụng có thể nhìn thấy dữ liệu cũ hoặc ghi đè dữ liệu dựa trên trạng thái cũ nếu nghiệp vụ không có cơ chế bảo vệ khác.

Chỉ cân nhắc tắt bookmark khi ứng dụng chấp nhận stale read và đã đánh giá rõ tác động nghiệp vụ. Không tắt bookmark chỉ để giảm một ít độ trễ mà chưa đo đạc và chưa xác định được các luồng cần read-your-own-writes.

## 12. Chọn read routing hay write routing theo nghiệp vụ

| Tình huống | Transaction nên dùng | Lý do |
|---|---|---|
| Tải hồ sơ hoặc danh sách để hiển thị | Read-only | Có thể phân phối sang reader |
| Chạy báo cáo chỉ đọc | Read-only | Giảm tải truy vấn đọc trên writer |
| Tìm kiếm bằng derived query | Read-only nếu method chỉ đọc | Cần khai báo rõ cho method do ứng dụng định nghĩa |
| Custom `@Query` có `MERGE`, `CREATE`, `SET` | Read-write | Cần writer để thay đổi graph |
| Gọi procedure có side effect | Read-write | Không thể giả định procedure chỉ đọc |
| Ghi dữ liệu rồi đọc ngay trong cùng workflow | Transaction ghi và causal bookmark khi tách transaction | Đảm bảo đọc tôn trọng thay đổi đã commit |
| Kiểm tra dữ liệu có thể chấp nhận độ trễ replication | Read-only | Có thể đọc từ reader, nhưng phải chấp nhận stale read nếu không có bookmark ràng buộc |

Việc chọn read-only phải dựa trên ngữ nghĩa thực sự của toàn bộ transaction. Đừng chỉ dựa vào tên method, HTTP GET hoặc việc câu Cypher có bắt đầu bằng `MATCH`.

## 13. Quan sát và kiểm tra định tuyến

Khi triển khai cụm, cần xác nhận ứng dụng đang dùng routing driver và transaction được đánh dấu đúng access mode. Có thể kiểm tra:

1. URI runtime dùng `neo4j://` hoặc biến thể routing TLS, không phải direct `bolt://` nếu muốn driver tự định tuyến.
2. Các địa chỉ router/reader/writer do cụm quảng bá có thể truy cập từ mạng ứng dụng.
3. Các method đọc tùy chỉnh có `@Transactional(readOnly = true)` ở method hoặc service boundary thích hợp.
4. Các method có ghi hoặc gọi procedure có side effect không nằm trong transaction read-only.
5. Các thao tác ghi rồi đọc tiếp vẫn dùng bookmark management mặc định.
6. Log/metrics và công cụ quản trị cho thấy transaction được gửi đến đúng nhóm máy chủ.

Có thể kiểm tra routing table và vai trò thành viên bằng các công cụ quản trị Neo4j phù hợp với phiên bản triển khai. Không nên suy luận routing chỉ từ việc truy vấn thành công: một truy vấn đọc chạy trên primary vẫn có thể thành công dù chưa được offload sang reader.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tải đọc vẫn dồn vào primary | Dùng `bolt://` direct URI hoặc transaction mặc định là read-write | Dùng routing URI và đánh dấu transaction đọc bằng `readOnly = true`. |
| Ghi thất bại trên reader | Method chứa ghi nhưng bị đánh dấu read-only | Đổi sang transaction read-write và kiểm tra procedure được gọi. |
| Derived finder không được định tuyến sang reader | Method tự định nghĩa chưa khai báo read-only | Thêm `@Transactional(readOnly = true)` ở method hoặc service. |
| Custom `@Query` chạy trên writer dù chỉ đọc | SDN không phân tích Cypher để tự nhận biết read-only | Đánh dấu rõ read-only nếu đã xác minh toàn bộ query chỉ đọc. |
| Đọc ngay sau ghi nhưng nhận dữ liệu cũ | Bookmark bị tắt, mất hoặc không được truyền qua ranh giới ứng dụng | Giữ bookmark management mặc định hoặc truyền bookmark cho workflow độc lập. |
| Driver không kết nối được thành viên sau khi lấy routing table | Địa chỉ advertised, DNS hoặc firewall không truy cập được từ ứng dụng | Kiểm tra cấu hình routing và khả năng phân giải/kết nối tới từng địa chỉ. |
| Một transaction vừa đọc vừa ghi bị gửi tới reader | Transaction được đánh dấu read-only dù có thao tác ghi | Chọn access mode theo toàn bộ transaction; tách workflow nếu cần ranh giới khác nhau. |
| Tắt bookmark làm tăng lỗi dữ liệu cũ | Cụm chưa đồng bộ xong khi truy vấn tới reader | Bật lại bookmark hoặc chỉ chấp nhận stale read khi nghiệp vụ cho phép. |

## 15. Quy trình cấu hình định tuyến đọc–ghi

1. Xác nhận cụm Neo4j hỗ trợ routing và lấy endpoint cùng scheme từ quản trị viên.
2. Cấu hình Spring Boot bằng `neo4j://` hoặc biến thể TLS phù hợp; tránh direct `bolt://` nếu cần routing tự động.
3. Bảo đảm địa chỉ router và địa chỉ các thành viên được quảng bá có thể truy cập từ ứng dụng.
4. Đánh dấu service chỉ đọc bằng `@Transactional(readOnly = true)`.
5. Đánh dấu method derived/custom query riêng là read-only khi đã xác minh không có side effect.
6. Giữ transaction read-write cho thao tác ghi và procedure có thể thay đổi dữ liệu.
7. Dùng một transaction boundary phù hợp cho workflow phối hợp nhiều repository.
8. Giữ bookmark management mặc định để duy trì causal consistency giữa các transaction nối tiếp.
9. Chỉ truyền hoặc seed bookmark thủ công khi workflow vượt qua ranh giới ứng dụng/JVM và có yêu cầu rõ ràng.
10. Kiểm tra routing thực tế, lỗi ghi trên reader và hành vi read-your-own-writes trong integration test với cụm.

## 16. Ghi nhớ

Định tuyến đọc–ghi trong cụm Neo4j dựa trên access mode của transaction. Routing driver được kích hoạt bằng URI `neo4j://` hoặc biến thể TLS; transaction READ có thể được gửi tới reader, còn transaction WRITE được gửi tới primary/writer. URI `bolt://` kết nối trực tiếp một máy chủ và không tự phân phối request trong cụm.

Spring Data Neo4j không phân tích Cypher để xác định query chỉ đọc. Các finder dựng sẵn như `findById`, `findAllById`, `findAll` và existential methods được đánh dấu read-only; derived finder và custom `@Query` cần khai báo rõ khi chỉ đọc. Đặt `@Transactional(readOnly = true)` ở service hoặc method phù hợp để tận dụng reader, và không đánh dấu read-only cho transaction có ghi hoặc gọi procedure có side effect.

Bookmark management được SDN thực hiện tự động để duy trì causal consistency và read-your-own-writes giữa các transaction nối tiếp. Chỉ cần can thiệp bookmark khi phải truyền trạng thái nhân quả qua các luồng hoặc ứng dụng độc lập. Giữ đúng routing URI, access mode và bookmark sẽ giúp cụm phân phối tải đọc–ghi mà vẫn bảo toàn thứ tự dữ liệu mà nghiệp vụ cần.

## Tài liệu tham khảo

- [Spring Data Neo4j – FAQ: Using a Neo4j cluster instance](https://docs.spring.io/spring-data/neo4j/reference/faq.html#using-a-neo4j-cluster-instance-from-spring-data-neo4j)
- [Neo4j Java Driver – Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver – Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Operations Manual – Leadership, routing, and load balancing](https://neo4j.com/docs/operations-manual/current/clustering/setup/routing/)
