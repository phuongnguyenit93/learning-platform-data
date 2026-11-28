# Phân biệt phạm vi cấu hình driver với phạm vi cấu hình SDN

Spring Data Neo4j (SDN) xây dựng tầng dữ liệu đồ thị trên Neo4j Java Driver. Hai thành phần này liên quan chặt chẽ nhưng đảm nhiệm hai phạm vi cấu hình khác nhau. Driver quản lý việc kết nối và giao tiếp với Neo4j Server; SDN dùng Driver để ánh xạ node và relationship thành entity, cung cấp repository, truy vấn và tích hợp transaction với Spring.

Nếu đặt một tùy chọn ở sai tầng, ứng dụng có thể khởi động nhưng vẫn không kết nối được database, hoặc kết nối thành công nhưng mapping và repository hoạt động không như mong đợi. Bài học này giúp xác định cấu hình nào thuộc Driver, cấu hình nào thuộc SDN, cách Spring Boot tự động tạo các thành phần và khi nào cần tùy chỉnh thủ công.

## 1. Kiến trúc từ ứng dụng đến Neo4j Server

Một ứng dụng dùng SDN thường có luồng xử lý như sau:

~~~mermaid
flowchart TD
    A["Service và nghiệp vụ ứng dụng"] --> B["Spring Data Neo4j"]
    B --> C["Repository / Neo4jTemplate / Neo4jClient"]
    C --> D["Neo4j Java Driver"]
    D --> E["Bolt / TLS / Connection Pool"]
    E --> F["Neo4j Server và Database"]
~~~

Có thể chia trách nhiệm cấu hình thành hai lớp:

| Phạm vi | Thành phần chịu trách nhiệm | Ví dụ cấu hình |
| --- | --- | --- |
| Kết nối và giao tiếp | Neo4j Java Driver | URI, xác thực, TLS, pool, timeout, retry |
| Ánh xạ và truy cập dữ liệu | Spring Data Neo4j | entity mapping, repository scan, custom conversions, database mặc định, transaction integration |

Driver không biết entity Java nào tương ứng với nhãn node nào. SDN không tự triển khai giao thức Bolt hay quản lý socket và connection pool; SDN sử dụng Driver để thực hiện các thao tác đó.

## 2. Phạm vi cấu hình của Neo4j Java Driver

Driver là lớp giao tiếp cấp thấp giữa ứng dụng và Neo4j Server. Một đối tượng Driver quản lý kết nối, pool kết nối và việc tạo session để gửi lệnh đến server. Trong ứng dụng Spring, thông thường nên dùng một Driver dùng chung trong suốt vòng đời ứng dụng; tạo Driver mới cho từng request sẽ làm tăng chi phí khởi tạo và quản lý pool.

Các nhóm cấu hình thường thuộc Driver gồm:

- **URI và chế độ kết nối:** địa chỉ máy chủ, cổng và lựa chọn kết nối trực tiếp hay routing.
- **Xác thực:** token hoặc thông tin xác thực dùng để đăng nhập Neo4j.
- **Mã hóa kết nối:** TLS và cách xác minh chứng chỉ máy chủ.
- **Connection pool:** số kết nối tối đa, thời gian chờ lấy connection và thời gian sống của connection.
- **Timeout và retry:** giới hạn thời gian thiết lập kết nối hoặc thời gian driver thử lại một số giao dịch tạm thời.
- **Quan sát vận hành:** logging, metrics và phát hiện session bị rò rỉ nếu bật các tùy chọn tương ứng.

Ví dụ URI thường gặp:

| URI scheme | Ý nghĩa khái quát |
| --- | --- |
| `bolt://` | Kết nối Bolt trực tiếp, không bật TLS theo scheme này |
| `neo4j://` | Kết nối có routing, phù hợp khi topology Neo4j hỗ trợ routing |
| `bolt+s://` | Bolt trực tiếp với TLS và xác minh chứng chỉ CA |
| `neo4j+s://` | Routing với TLS và xác minh chứng chỉ CA |
| `bolt+ssc://` hoặc `neo4j+ssc://` | TLS với chứng chỉ tự ký được chấp nhận theo cấu hình scheme |

Hãy chọn URI theo topology và chính sách bảo mật của môi trường. Trong production, ưu tiên kết nối mã hóa có xác minh chứng chỉ hợp lệ; không dùng scheme chấp nhận chứng chỉ tự ký một cách tùy tiện.

## 3. Khai báo cấu hình Driver bằng Spring Boot

Khi sử dụng `spring-boot-starter-data-neo4j`, Spring Boot có thể tự cấu hình Driver từ các thuộc tính ứng dụng. Ví dụ `application.yml` cho môi trường phát triển:

~~~yaml
spring:
  neo4j:
    uri: bolt://localhost:7687
    authentication:
      username: neo4j
      password: ${NEO4J_PASSWORD}
~~~

Trong ví dụ này, `spring.neo4j.uri` và `spring.neo4j.authentication` cung cấp thông tin để tạo kết nối. Mật khẩu được lấy từ biến môi trường thay vì ghi trực tiếp vào file cấu hình được commit.

Một số thuộc tính pool và timeout cũng thuộc nhóm `spring.neo4j`. Tên thuộc tính chi tiết có thể thay đổi theo phiên bản Spring Boot, vì vậy hãy đối chiếu metadata cấu hình và tài liệu của đúng phiên bản dự án trước khi thêm các giá trị như kích thước pool, thời gian chờ lấy connection hoặc thời gian retry.

Đối với môi trường khác nhau, có thể đặt URI và thông tin xác thực qua biến môi trường hoặc cấu hình profile. Ví dụ, máy phát triển có thể dùng `bolt://localhost:7687`, trong khi môi trường triển khai dùng URI do cụm Neo4j cung cấp. Không nên dùng chung một mật khẩu trong source code cho mọi môi trường.

## 4. Phạm vi cấu hình của Spring Data Neo4j

SDN hoạt động ở tầng persistence của ứng dụng. Nó sử dụng Driver nhưng bổ sung những khái niệm mà Driver không quản lý:

- **Mapping context:** xác định cách SDN nhận diện và ánh xạ các lớp `@Node`, thuộc tính và `@Relationship`.
- **Repository:** tạo implementation cho các interface kế thừa `Neo4jRepository` và phát hiện các phương thức truy vấn.
- **Neo4jClient và Neo4jTemplate:** cung cấp API làm việc với Cypher và thao tác dữ liệu ở mức thấp hơn repository.
- **Custom conversions:** chuyển đổi giữa kiểu dữ liệu Java và kiểu dữ liệu mà Neo4j lưu trữ.
- **Transaction integration:** kết nối thao tác SDN với cơ chế transaction của Spring.
- **Database mặc định và phạm vi quét:** chọn database cho thao tác SDN và package chứa repository hoặc entity.

Ví dụ, ứng dụng có thể chỉ định database mặc định cho SDN bằng thuộc tính `spring.data.neo4j.database` nếu phiên bản Spring Boot đang dùng hỗ trợ thuộc tính này:

~~~yaml
spring:
  data:
    neo4j:
      database: graphdb
~~~

Thuộc tính database này chọn database mà tầng SDN sử dụng mặc định. Nó không thay thế URI hay thông tin xác thực của Driver. Tài khoản kết nối vẫn cần có quyền truy cập database được chọn.

### 4.1. Entity mapping

Các annotation như `@Node`, `@Id`, `@Relationship` thuộc mô hình dữ liệu mà SDN ánh xạ. Chúng mô tả nhãn node, định danh và quan hệ giữa entity. Ví dụ:

~~~java
@Node("Person")
public class Person {
    @Id
    private String id;

    private String name;

    @Relationship(type = "FOLLOWS", direction = Relationship.Direction.OUTGOING)
    private Set<Person> follows = new HashSet<>();
}
~~~

Các annotation này không cấu hình địa chỉ server, TLS hay connection pool. Nếu mapping sai, kết nối Driver vẫn có thể hoạt động bình thường; vấn đề nằm ở mô hình hoặc cấu hình SDN.

### 4.2. Repository và phạm vi quét

Spring Boot thường tự phát hiện repository trong package của ứng dụng theo quy ước auto-configuration. Chỉ khi repository nằm ngoài package mặc định hoặc cần kiểm soát phạm vi rõ ràng, mới cần khai báo cấu hình quét riêng, ví dụ:

~~~java
@Configuration
@EnableNeo4jRepositories(basePackages = "com.example.graph.repository")
public class Neo4jRepositoryConfiguration {
}
~~~

Không khai báo thêm cấu hình quét một cách máy móc nếu Spring Boot đã phát hiện repository đúng. Cấu hình quét trùng hoặc đặt sai package có thể làm repository không được khởi tạo như dự kiến.

### 4.3. Custom conversions và mapping

Khi domain model dùng kiểu Java riêng, chẳng hạn `Money`, `Coordinate` hoặc kiểu value object, SDN có thể cần converter để chuyển đổi kiểu đó thành giá trị mà Neo4j hỗ trợ và ngược lại. Đây là tùy chỉnh mapping của SDN, không phải tùy chọn connection pool của Driver.

Hãy đăng ký converter theo cơ chế `Neo4jConversions` của phiên bản SDN đang dùng. Converter đọc và ghi cần nhất quán: giá trị ghi vào Neo4j phải có thể được đọc lại thành kiểu Java tương ứng. Nên có kiểm thử cho cả hai chiều chuyển đổi và dữ liệu cũ nếu schema đã tồn tại.

## 5. Transaction: Driver và SDN đảm nhiệm phần nào?

Driver cung cấp session và transaction ở mức giao tiếp với Neo4j. SDN tích hợp các thao tác repository, template và client với transaction management của Spring. Trong ứng dụng Spring Boot, transaction manager Neo4j thường được auto-configure cùng các thành phần persistence.

Ví dụ, một use case có thể cập nhật quan hệ và ghi thêm một bản ghi nghiệp vụ trong cùng transaction:

~~~java
@Service
public class FollowService {

    private final PersonRepository personRepository;

    public FollowService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @Transactional
    public void follow(String followerId, String targetId) {
        personRepository.createFollow(followerId, targetId);
        // Các thao tác SDN khác trong cùng transaction có thể đặt tại đây.
    }
}
~~~

`@Transactional` là cơ chế transaction ở tầng Spring/SDN. Các thiết lập retry của Driver không thay thế ranh giới transaction của nghiệp vụ. Tương tự, việc gọi nhiều phương thức repository không tự động có nghĩa chúng luôn thuộc cùng một transaction nếu không có transaction boundary phù hợp.

Với thao tác chỉ đọc, có thể dùng `@Transactional(readOnly = true)` khi phù hợp với use case. Đây là metadata transaction cho Spring; không nên coi nó là cơ chế phân quyền ở Neo4j.

## 6. Tùy chỉnh Driver khi cấu hình mặc định chưa đủ

Nếu cần điều chỉnh sâu connection pool hoặc timeout, có thể tạo Driver bean tùy chỉnh. Ví dụ minh họa phần cấu hình Driver:

~~~java
Config driverConfig = Config.builder()
    .withMaxConnectionPoolSize(50)
    .withConnectionAcquisitionTimeout(Duration.ofSeconds(30))
    .withMaxConnectionLifetime(Duration.ofMinutes(30))
    .build();

Driver driver = GraphDatabase.driver(
    uri,
    AuthTokens.basic(username, password),
    driverConfig
);
~~~

Các giá trị trên chỉ là ví dụ để minh họa những tùy chọn thuộc Driver; cần chọn con số dựa trên tải thực tế, giới hạn kết nối của Neo4j Server và phiên bản Driver. Không nên tăng pool vô hạn vì mỗi kết nối tiêu thụ tài nguyên ở cả client và server.

Khi tự khai báo một bean `Driver`, auto-configuration của Spring Boot thường sẽ lùi lại vì đã có bean cùng kiểu. Khi đó, ứng dụng phải tự bảo đảm URI, authentication, TLS và các tùy chọn cần thiết đã được chuyển vào Driver tùy chỉnh. Tránh tạo hai Driver bean độc lập nếu toàn bộ SDN và phần truy cập thủ công không có chủ đích dùng các kết nối khác nhau.

Driver nên được quản lý theo vòng đời ứng dụng và đóng khi ứng dụng dừng. Không tạo rồi đóng Driver ở mỗi phương thức service. Session là tài nguyên ngắn hạn hơn và nên được quản lý trong phạm vi thao tác hoặc transaction.

## 7. Chọn đúng tầng khi xử lý một yêu cầu cấu hình

| Yêu cầu | Nơi cấu hình phù hợp |
| --- | --- |
| Đổi địa chỉ Neo4j Server | Driver / `spring.neo4j.uri` |
| Đổi username hoặc password | Driver authentication / `spring.neo4j.authentication` |
| Bật TLS hoặc chọn scheme kết nối | URI và cấu hình bảo mật của Driver |
| Điều chỉnh số kết nối đồng thời | Driver connection pool |
| Đổi database mặc định của thao tác SDN | SDN / `spring.data.neo4j.database` |
| Đổi package chứa repository | SDN repository scanning |
| Chuyển đổi kiểu domain riêng | SDN custom conversions |
| Điều chỉnh cách ánh xạ node và relationship | SDN mapping và entity annotations |
| Bao nhiều thao tác repository trong một nghiệp vụ | Spring transaction management tích hợp SDN |

Một cách kiểm tra nhanh là tự hỏi yêu cầu đó liên quan đến việc thiết lập kết nối đến server hay cách ứng dụng biểu diễn và thao tác dữ liệu. Nếu là kết nối, bắt đầu từ Driver. Nếu là entity, repository, mapping hoặc transaction trong ứng dụng Spring, bắt đầu từ SDN và Spring.

## 8. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Ứng dụng không kết nối được server | URI, cổng, TLS hoặc authentication sai | Kiểm tra `spring.neo4j.*`, scheme URI và log Driver |
| Kết nối thành công nhưng truy vấn báo không có database | Tên database mặc định hoặc quyền tài khoản chưa đúng | Kiểm tra `spring.data.neo4j.database` và quyền của user Neo4j |
| Repository không được tạo | Package repository nằm ngoài phạm vi scan hoặc cấu hình enable không đúng | Kiểm tra package ứng dụng và `@EnableNeo4jRepositories` |
| Entity không được ánh xạ như mong đợi | Sai `@Node`, `@Id`, `@Relationship` hoặc custom conversion | Kiểm tra mapping model và dữ liệu trả về |
| Pool cạn hoặc request chờ lâu | Pool quá nhỏ, session không được đóng hoặc tải vượt khả năng server | Xem metrics/log, cấu hình pool và vòng đời session |
| Transaction không bao trùm các thao tác | Thiếu transaction manager hoặc gọi qua ranh giới proxy không phù hợp | Kiểm tra cấu hình transaction và vị trí `@Transactional` |
| Có hai kết nối với cấu hình khác nhau | Tạo Driver bean tùy chỉnh đồng thời với cấu hình tự động không có chủ đích | Kiểm tra số lượng bean Driver và nơi khởi tạo |

Không xử lý mọi lỗi bằng cách tăng connection pool hoặc timeout. Trước tiên hãy xác định lỗi nằm ở kết nối, quyền truy cập database, mapping, repository hay transaction. Điều chỉnh đúng tầng giúp tránh che giấu nguyên nhân và giữ cấu hình dễ vận hành.

## 9. Quy trình xác minh cấu hình

Sau khi thay đổi cấu hình, có thể kiểm tra theo thứ tự sau:

1. **Xác minh Driver:** kiểm tra URI và authentication của môi trường; có thể gọi `driver.verifyConnectivity()` trong một bước health check hoặc kiểm thử tích hợp phù hợp.
2. **Xác minh database:** xác nhận user có quyền truy cập database mặc định đã chọn.
3. **Xác minh SDN mapping:** đọc hoặc lưu thử một entity đơn giản có `@Node` và định danh hợp lệ.
4. **Xác minh repository:** gọi một phương thức repository hoặc một truy vấn Cypher có tham số.
5. **Xác minh transaction:** thử một use case gồm nhiều thao tác ghi và kiểm tra rollback khi có lỗi trong transaction.
6. **Quan sát tài nguyên:** theo dõi số connection, thời gian chờ pool, thời gian truy vấn và log khi chạy dưới tải dự kiến.

Kiểm tra Driver thành công chỉ xác nhận lớp kết nối có thể giao tiếp với server. Nó chưa chứng minh mapping entity, repository scan hay transaction của SDN đã đúng. Ngược lại, nếu repository không hoạt động, không nên kết luận ngay rằng Driver bị lỗi khi kết nối đã được xác minh.

## 10. Bài tập tự kiểm tra

1. Nêu ba ví dụ cấu hình thuộc Neo4j Java Driver và giải thích lý do.
2. Vì sao `spring.neo4j.uri` và `spring.data.neo4j.database` thuộc hai phạm vi khác nhau?
3. Một ứng dụng kết nối thành công nhưng repository không được tạo. Bạn sẽ kiểm tra những thành phần SDN nào?
4. Khi nào cần tạo Driver bean tùy chỉnh? Điều gì cần được kiểm tra khi auto-configuration lùi lại?
5. Giải thích vai trò của `@Transactional` trong use case gọi nhiều phương thức repository.
6. Vì sao tăng connection pool không phải cách xử lý mặc định cho mọi lỗi timeout?

Khi hoàn thành bài học, bạn cần xác định được cấu hình nào điều khiển kết nối Driver và cấu hình nào điều khiển mapping, repository, database mặc định và transaction của SDN. Sự phân tách này giúp cấu hình Spring Data Neo4j rõ ràng, dễ kiểm tra và phù hợp với từng môi trường triển khai.
