# Chọn database cố định bằng cấu hình Spring Boot

Một Neo4j DBMS có thể quản lý nhiều database. Mỗi database chứa một graph và có phạm vi transaction riêng. Trong ứng dụng Spring Data Neo4j (SDN), nếu mọi repository của một service luôn làm việc với cùng một database, bạn có thể chọn database đó ngay trong cấu hình Spring Boot.

Thuộc tính cần dùng là **spring.data.neo4j.database**. Thuộc tính này xác định database đích cho các thao tác do SDN quản lý. Nó tách biệt với **spring.neo4j.uri**, vốn xác định địa chỉ DBMS mà Neo4j Java Driver kết nối tới.

Ví dụ, ứng dụng quản lý đơn hàng có thể kết nối tới server tại `bolt://localhost:7687` và chọn database `orders`. Khi cấu hình cố định này được áp dụng, các repository imperative/reactive và `Neo4jTemplate`/`ReactiveNeo4jTemplate` của ứng dụng sẽ truy vấn database `orders`.

Sau bài học, bạn có thể:

- Phân biệt Neo4j DBMS, database và địa chỉ kết nối Bolt.
- Cấu hình database đích bằng `spring.data.neo4j.database`.
- Đặt database khác nhau theo Spring profile hoặc biến môi trường.
- Hiểu phạm vi áp dụng của lựa chọn database đối với repository và template SDN.
- Xác định khi nào cần cấu hình thêm cho Neo4j Java Driver thuần.
- Kiểm tra database tồn tại, trạng thái hoạt động và quyền truy cập.
- Nhận biết giới hạn của cấu hình cố định khi ứng dụng cần chọn database theo tenant hoặc request.

## 1. Phân biệt DBMS, database và kết nối Driver

Neo4j Java Driver kết nối tới một Neo4j DBMS thông qua Bolt. Một DBMS có thể quản lý một hoặc nhiều database tùy edition và dịch vụ triển khai.

~~~mermaid
flowchart TD
    A["Spring Boot application"] --> B["Neo4j Java Driver"]
    B -->|"Bolt URI: bolt://localhost:7687"| C["Neo4j DBMS"]
    C --> D["Database: neo4j"]
    C --> E["Database: orders"]
    C --> F["Database: reporting"]
    G["spring.data.neo4j.database = orders"] --> H["SDN database selection"]
    H --> E
~~~

Ba khái niệm cần tách biệt:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| DBMS/server | Tiến trình hoặc cụm Neo4j quản lý database | `localhost:7687` |
| Database | Graph mà truy vấn sẽ đọc hoặc ghi | `orders` |
| Driver URI | Địa chỉ kết nối tới DBMS | `bolt://localhost:7687` |

URI không nhất thiết chỉ ra database đích. Driver kết nối tới server; database được xác định khi mở session hoặc khi SDN chọn database cho thao tác. Nếu không chỉ định database, Neo4j sẽ dùng database mặc định hoặc home database theo cấu hình người dùng trên server.

Vì vậy, để một ứng dụng SDN dùng database có tên `orders`, cần cấu hình thuộc tính database riêng ngoài URI.

## 2. Cấu hình database cố định trong application.yml

Trong `src/main/resources/application.yml`, khai báo:

~~~yaml
spring:
  neo4j:
    uri: bolt://localhost:7687
    authentication:
      username: neo4j
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: orders
~~~

Trong ví dụ:

- `spring.neo4j.uri` cấu hình endpoint mà Driver kết nối.
- `spring.neo4j.authentication.username` và `password` cấu hình thông tin xác thực.
- `spring.data.neo4j.database` chọn database `orders` cho các thao tác SDN.

Trong môi trường thật, không ghi mật khẩu trực tiếp vào file cấu hình được commit. Hãy đưa bí mật vào biến môi trường hoặc secret manager:

~~~yaml
spring:
  neo4j:
    uri: bolt://neo4j.internal:7687
    authentication:
      username: app_user
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: orders
~~~

Spring Boot hỗ trợ cấu hình cùng thuộc tính bằng file `.properties`:

~~~properties
spring.neo4j.uri=bolt://localhost:7687
spring.neo4j.authentication.username=neo4j
spring.neo4j.authentication.password=secret
spring.data.neo4j.database=orders
~~~

Không dùng `spring.neo4j.database` cho lựa chọn database của SDN. Tên thuộc tính chính xác là `spring.data.neo4j.database`.

## 3. Dùng biến môi trường khi triển khai

Spring Boot hỗ trợ relaxed binding, vì vậy có thể ghi đè cấu hình bằng biến môi trường:

~~~text
SPRING_NEO4J_URI=bolt://neo4j.internal:7687
SPRING_NEO4J_AUTHENTICATION_USERNAME=app_user
SPRING_NEO4J_AUTHENTICATION_PASSWORD=secret-from-secret-store
SPRING_DATA_NEO4J_DATABASE=orders
~~~

Đặt `SPRING_DATA_NEO4J_DATABASE=orders` trong môi trường chạy giúp chọn database mà không cần thay file cấu hình đóng gói cùng ứng dụng.

Biến môi trường có thể được cung cấp bởi Docker Compose, Kubernetes Secret/ConfigMap, hệ thống triển khai hoặc nền tảng cloud. Với mật khẩu, dùng cơ chế quản lý secret của nền tảng.

## 4. Chọn database theo Spring profile

Một ứng dụng có thể dùng database riêng ở từng môi trường:

~~~yaml
# application-dev.yml
spring:
  data:
    neo4j:
      database: orders_dev
~~~

~~~yaml
# application-prod.yml
spring:
  data:
    neo4j:
      database: orders
~~~

Kích hoạt profile khi chạy:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Khi profile `prod` hoạt động, Spring Boot nạp cấu hình tương ứng và SDN dùng database `orders`. Trong môi trường dev, profile `dev` chọn `orders_dev`.

Profile giúp tách dữ liệu giữa môi trường phát triển, kiểm thử và production. Hãy bảo đảm database tương ứng đã tồn tại ở từng môi trường; thay đổi tên trong YAML không tự tạo database mới.

## 5. Những thành phần SDN sử dụng database đã chọn

Spring Data Neo4j cung cấp cơ chế chọn database cho repository và template. Khi cấu hình `spring.data.neo4j.database` trong Spring Boot, các truy vấn được tạo từ repository imperative và reactive, cùng các template SDN, sẽ chạy trên database được chỉ định.

| Thành phần | Database đích |
|---|---|
| `Neo4jRepository` | Database cố định đã cấu hình |
| `ReactiveNeo4jRepository` | Database cố định đã cấu hình |
| `Neo4jTemplate` | Database cố định đã cấu hình |
| `ReactiveNeo4jTemplate` | Database cố định đã cấu hình |
| `Neo4jClient` do SDN cấu hình | Dùng database selection provider của hạ tầng SDN |
| `ReactiveNeo4jClient` do SDN cấu hình | Dùng reactive database selection provider tương ứng |

Ví dụ repository:

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface OrderRepository
        extends Neo4jRepository<Order, Long> {

    Optional<Order> findByOrderCode(String orderCode);
}
~~~

Repository không cần truyền tên database vào từng phương thức:

~~~java
Order order = orderRepository.findByOrderCode("ORD-2026-001")
    .orElseThrow();
~~~

SDN sử dụng database đã chọn từ cấu hình để thực hiện truy vấn. Tương tự, `Neo4jTemplate` và `Neo4jClient` do hạ tầng SDN cung cấp sử dụng database selection provider được cấu hình trong application context.

Với một ứng dụng dùng database cố định, không cần tự tạo `DatabaseSelectionProvider` chỉ để lặp lại tên database trong YAML. Một bean provider tùy chỉnh có thể thay đổi hoặc ghi đè cách chọn database, vì vậy chỉ thêm provider khi thật sự cần logic chọn riêng.

## 6. Cấu hình database không tạo database trên Neo4j

`spring.data.neo4j.database` chỉ chọn tên database để SDN truy cập. Spring Data Neo4j không tự tạo database đó.

Trước khi khởi chạy ứng dụng, cần bảo đảm:

- Database có tên đúng như cấu hình.
- Database đang ở trạng thái online.
- Tài khoản ứng dụng có quyền truy cập database.
- Database tương thích với phiên bản Neo4j và các tính năng mà ứng dụng sử dụng.

Có thể kiểm tra database hiện có bằng Cypher:

~~~cypher
SHOW DATABASES
~~~

Lệnh quản trị tạo database trong Neo4j self-managed Enterprise:

~~~cypher
CREATE DATABASE orders IF NOT EXISTS
~~~

Các lệnh quản trị database phải được thực hiện bởi tài khoản có quyền phù hợp. Khả năng tạo nhiều database còn phụ thuộc edition và dịch vụ Neo4j đang sử dụng. Neo4j Community Edition hiện hỗ trợ đúng một standard database; Enterprise Edition hỗ trợ nhiều standard database. Một số dịch vụ managed có giới hạn quản trị riêng.

Nếu database không tồn tại, bị dừng hoặc tài khoản không có quyền, thao tác repository có thể thất bại khi Driver mở session hoặc chạy truy vấn. Đổi tên trong `application.yml` không thay thế bước provisioning database và cấp quyền.

## 7. Database cố định và transaction

Trong một ứng dụng SDN dùng database cố định, các thao tác repository trong cùng service transaction sẽ làm việc với database đã cấu hình:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final CustomerRepository customerRepository;

    public OrderService(
            OrderRepository orderRepository,
            CustomerRepository customerRepository) {
        this.orderRepository = orderRepository;
        this.customerRepository = customerRepository;
    }

    @Transactional
    public Order createOrder(Order order) {
        customerRepository.findById(order.getCustomerId())
            .orElseThrow();

        return orderRepository.save(order);
    }
}
~~~

Cả hai repository sử dụng database được chọn bởi cấu hình SDN. Transaction manager đồng bộ transaction Neo4j cho database đó.

Một transaction Neo4j thuộc về một database. Không thể dùng một transaction thông thường để commit nguyên tử các thay đổi trên nhiều database khác nhau. Nếu một use case cần ghi nhiều database, phải thiết kế ranh giới transaction và cơ chế phối hợp riêng, chẳng hạn saga hoặc outbox tùy nghiệp vụ.

Đây là lý do cấu hình database cố định phù hợp khi một ứng dụng hoặc một deployment chịu trách nhiệm cho một graph chính. Nó cũng giúp tránh vô tình trộn entity đọc từ database này với entity ghi vào database khác.

## 8. Truy cập bằng Neo4j Java Driver thuần

Thuộc tính `spring.data.neo4j.database` dành cho database selection của hạ tầng Spring Data Neo4j. Nếu tự mở session bằng Neo4j Java Driver, hãy chỉ định database trực tiếp qua `SessionConfig`:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public void writeAuditRecord(Driver driver) {
    SessionConfig config = SessionConfig.builder()
        .withDatabase("orders")
        .build();

    try (Session session = driver.session(config)) {
        session.executeWrite(tx ->
            tx.run(
                "CREATE (:AuditRecord {event: $event})",
                java.util.Map.of("event", "ORDER_CREATED")
            ).consume()
        );
    }
}
~~~

Session được mở trực tiếp bằng Driver không tự đọc `spring.data.neo4j.database`. Nếu bỏ qua `SessionConfig.withDatabase(...)`, Driver sẽ dùng database mặc định/home database do server xác định.

Nếu cần Cypher tùy chỉnh nhưng vẫn muốn dùng database selection và transaction do SDN quản lý, hãy ưu tiên inject `Neo4jClient` hoặc `ReactiveNeo4jClient` do Spring cấu hình thay vì tự mở Driver session.

## 9. Kiểm tra database mà ứng dụng đang truy cập

Có thể kiểm tra từ Neo4j Browser hoặc cypher-shell:

~~~cypher
SHOW DATABASES
~~~

Để xác nhận database hiện tại của một session, chạy:

~~~cypher
CALL db.info() YIELD name
RETURN name
~~~

Kết quả phải khớp với giá trị `spring.data.neo4j.database` của profile đang chạy. Có thể chạy cùng câu lệnh qua `Neo4jClient`:

~~~java
String databaseName = neo4jClient.query("""
        CALL db.info() YIELD name
        RETURN name
        """)
    .fetchAs(String.class)
    .mappedBy((typeSystem, record) ->
        record.get("name").asString()
    )
    .one()
    .orElseThrow();
~~~

Trong kiểm thử tích hợp, nên tạo dữ liệu có thể nhận diện trong database mục tiêu rồi gọi repository để xác minh. Không chỉ kiểm tra ứng dụng khởi động thành công, vì kết nối tới DBMS chưa chứng minh repository đang dùng đúng database.

## 10. Lưu ý về Spring Boot Actuator health indicator

Neo4j Java Driver kết nối tới DBMS, không gắn cố định với một database. Thông tin chọn database của SDN nằm ở lớp Spring Data. Vì vậy, health indicator Neo4j mặc định của Spring Boot có thể kiểm tra database mặc định của server thay vì database được cấu hình bằng `spring.data.neo4j.database`.

Nếu tài khoản ứng dụng có quyền trên database `orders` nhưng không có quyền trên database mặc định `neo4j`, health check mặc định có thể báo lỗi dù truy vấn SDN tới `orders` vẫn hoạt động.

Khi gặp tình huống này:

- Kiểm tra log để phân biệt lỗi kết nối DBMS với lỗi quyền trên database mặc định.
- Xác minh trực tiếp truy vấn qua repository hoặc `Neo4jClient` của SDN.
- Cân nhắc cấp quyền phù hợp trên database mặc định nếu chính sách bảo mật cho phép.
- Nếu cần health check chính xác theo database SDN, triển khai health contributor biết database selection provider.

Không nên kết luận database ứng dụng bị down chỉ từ một health check không sử dụng cùng database selection.

## 11. Khi nào cấu hình cố định không còn phù hợp?

`spring.data.neo4j.database` áp dụng một lựa chọn cố định cho hạ tầng SDN trong application context. Đây là cách phù hợp khi mỗi deployment chỉ phục vụ một database.

Nếu ứng dụng cần chọn database theo tenant, user hoặc request, một giá trị cấu hình cố định không đủ. Spring Data Neo4j cung cấp `DatabaseSelectionProvider` cho imperative và `ReactiveDatabaseSelectionProvider` cho reactive để chọn database theo ngữ cảnh.

Không nên cố thay đổi tên database trong cấu hình sau mỗi request hoặc thay provider tùy tiện giữa các thao tác. SDN hỏi database selection trước các tương tác; thay đổi lựa chọn giữa các transaction có thể làm entity được đọc từ database này nhưng lại được ghi sang database khác.

Với bài toán tenant, cần thiết kế rõ:

- Cách xác thực tenant và xác định database hợp lệ.
- Cách giữ lựa chọn nhất quán trong toàn bộ transaction.
- Cách giới hạn tenant không thể truy cập database của tenant khác.
- Cách quản lý connection, transaction và migration trên nhiều database.
- Cách xử lý một use case cần phối hợp dữ liệu giữa các database.

## 12. Những lỗi thường gặp

**Dùng sai property.** `spring.neo4j.uri` cấu hình endpoint Driver; `spring.data.neo4j.database` chọn database cho SDN. Không thay thế thuộc tính này bằng `spring.neo4j.database`.

**Cho rằng database name nằm trong Bolt URI.** URI chỉ định DBMS. SDN chọn database riêng qua database selection provider.

**Cho rằng Spring Data Neo4j tự tạo database.** Database phải được provision trước và đang online.

**Quên profile ghi đè database.** Ứng dụng có thể vô tình ghi vào database dev nếu profile production không được kích hoạt hoặc cấu hình bị ghi đè.

**Cho rằng tất cả truy cập Driver đều dùng property SDN.** Session mở trực tiếp bằng Driver cần `SessionConfig.withDatabase(...)`.

**Tạo nhiều transaction manager hoặc provider không cần thiết.** Spring Boot đã tự cấu hình hạ tầng SDN thông thường. Chỉ thêm provider tùy chỉnh khi có logic chọn database riêng.

**Nhầm một transaction có thể trải qua nhiều database.** Transaction Neo4j có phạm vi một database; nhiều database cần cơ chế phối hợp khác.

**Health check kiểm tra database mặc định.** Health indicator mặc định có thể không biết lựa chọn database của SDN; cần xác minh đúng database mục tiêu.

## 13. Tự kiểm tra

1. `spring.neo4j.uri` và `spring.data.neo4j.database` khác nhau ở điểm nào?
2. Vì sao một Neo4j DBMS có thể có nhiều database nhưng Driver URI không đại diện cho từng database?
3. Cấu hình YAML nào chọn database `orders` cho SDN?
4. Các repository imperative và reactive có sử dụng chung database được cấu hình không?
5. Spring Data Neo4j có tự tạo database nếu tên cấu hình chưa tồn tại không?
6. Vì sao session mở trực tiếp bằng Driver cần `SessionConfig.withDatabase(...)`?
7. Một transaction Neo4j có thể ghi nguyên tử trên hai database không?
8. Vì sao health indicator mặc định có thể kiểm tra database khác với database SDN đang sử dụng?
9. Khi nào nên dùng `DatabaseSelectionProvider` thay cho cấu hình database cố định?

**Bài tập thực hành:** Tạo một ứng dụng Spring Boot với `OrderRepository` và `CustomerRepository`. Cấu hình `application-dev.yml` dùng database `orders_dev`, còn `application-prod.yml` dùng database `orders`. Khởi chạy ứng dụng với từng profile, xác minh database hiện tại bằng `CALL db.info()`, sau đó lưu và đọc một đơn hàng qua repository. Thử mở một session Driver thuần để truy vấn database `orders` bằng `SessionConfig.withDatabase(...)` và so sánh với session không chỉ định database. Cuối cùng, kiểm tra quyền truy cập của tài khoản ứng dụng và xác minh rằng database đích đã được provision trước khi ứng dụng khởi động.

## Tài liệu tham khảo

- [Spring Data Neo4j FAQ — Neo4j supports multiple databases](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j API — DatabaseSelectionProvider](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/DatabaseSelectionProvider.html)
- [Spring Data Neo4j API — Neo4jTransactionManager](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jTransactionManager.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html)
- [Neo4j Operations Manual — Database administration](https://neo4j.com/docs/operations-manual/current/database-administration/)
- [Neo4j Operations Manual — Create databases](https://neo4j.com/docs/operations-manual/current/database-administration/standard-databases/create-databases/)
