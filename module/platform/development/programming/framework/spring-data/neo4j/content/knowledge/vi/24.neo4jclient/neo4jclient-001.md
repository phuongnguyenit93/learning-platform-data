# Khởi tạo hoặc dùng Neo4jClient do Spring Boot cung cấp

`Neo4jClient` là API truy vấn imperative của Spring Data Neo4j (SDN), được xây dựng trên Neo4j Java Driver. Nó cho phép gửi Cypher, bind tham số và ánh xạ record trả về thành kiểu Java mà ứng dụng cần. Trong ứng dụng Spring Boot dùng starter Spring Data Neo4j, bạn thường không cần tự tạo client: hãy inject bean `Neo4jClient` do cấu hình tự động cung cấp.

Hiểu cách khởi tạo và vòng đời của client giúp tránh tạo nhiều driver không cần thiết, cấu hình kết nối trùng lặp và truy vấn sai tầng. Repository phù hợp với thao tác entity theo hợp đồng miền; `Neo4jClient` phù hợp khi cần Cypher tùy chỉnh, kết quả tổng hợp hoặc projection do ứng dụng tự ánh xạ.

## 1. Neo4jClient nằm ở đâu trong ứng dụng?

`Neo4jClient` nằm ở tầng truy cập dữ liệu và làm việc trên Neo4j Java Driver. Nó cung cấp API fluent để tạo query, truyền tham số và đọc kết quả. Client không thay thế Neo4j Server, không tự tạo schema và cũng không phải một connection pool độc lập.

~~~mermaid
flowchart TD
    A[Controller hoặc API] --> B[Service]
    B --> C[Repository / Neo4jTemplate]
    B --> D[Custom data access dùng Neo4jClient]
    C --> E[Neo4j Java Driver]
    D --> E
    E --> F[(Neo4j Database)]
~~~

Các thành phần có vai trò riêng:

- `Neo4jRepository`: thao tác entity, CRUD và derived query theo tên phương thức.
- `Neo4jTemplate`: thao tác entity ở mức template, sử dụng metadata mapping của SDN.
- `Neo4jClient`: thực thi Cypher và cho phép ánh xạ record theo nhu cầu.
- Neo4j Java Driver: quản lý giao tiếp, session và transaction với Neo4j Server.

Bạn có thể inject `Neo4jClient` vào một repository tùy chỉnh hoặc service chuyên truy vấn. Không nên để controller trực tiếp quản lý driver hoặc viết truy vấn cơ sở dữ liệu.

## 2. Thêm dependency và cấu hình kết nối

Với Spring Boot, dependency thường dùng là starter:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-neo4j")
}
~~~

Khai báo kết nối trong `application.yml`:

~~~yaml
spring:
  neo4j:
    uri: bolt://localhost:7687
    authentication:
      username: neo4j
      password: ${NEO4J_PASSWORD}
    database: neo4j
~~~

Các thuộc tính có ý nghĩa:

- `spring.neo4j.uri`: địa chỉ Neo4j, thường dùng scheme `bolt://` hoặc `neo4j://` tùy topology và cách kết nối.
- `spring.neo4j.authentication.username`: tài khoản kết nối.
- `spring.neo4j.authentication.password`: mật khẩu, nên lấy từ biến môi trường hoặc secret store.
- `spring.neo4j.database`: database đích nếu ứng dụng cần chọn database cụ thể.

Khi starter và cấu hình hợp lệ, Spring Boot tự cấu hình Neo4j Java Driver cùng các thành phần truy cập dữ liệu của SDN, trong đó có `Neo4jClient`. Các bean tùy chỉnh do ứng dụng cung cấp có thể khiến một phần auto-configuration lùi lại theo cơ chế điều kiện của Spring Boot.

Không đưa mật khẩu thật vào source control. Ở môi trường triển khai, dùng secret manager hoặc cơ chế cấu hình bảo mật tương ứng.

## 3. Inject Neo4jClient do Spring Boot cung cấp

Đây là cách dùng thông thường trong ứng dụng Spring Boot:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class PersonQueryRepository {

    private final Neo4jClient neo4jClient;

    public PersonQueryRepository(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }
}
~~~

Spring quản lý vòng đời bean và inject client vào constructor. Bạn không cần gọi `new Neo4jClient(...)` trong từng repository hoặc tạo một driver mới cho mỗi request.

Constructor injection có một số lợi ích:

- Phụ thuộc được thể hiện rõ trong constructor.
- Object có thể giữ tham chiếu `final`.
- Dễ thay thế bean bằng cấu hình kiểm thử.
- Không để lớp truy cập dữ liệu tự quản lý kết nối ngoài cấu hình chung của ứng dụng.

Nếu ứng dụng không dùng Spring Boot, hoặc bạn đang tự cấu hình SDN ngoài auto-configuration, có thể tạo client từ một `Driver` đã được quản lý:

~~~java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.Neo4jClient;

@Configuration
public class Neo4jClientConfiguration {

    @Bean
    Neo4jClient neo4jClient(Driver driver) {
        return Neo4jClient.create(driver);
    }
}
~~~

Chỉ khai báo bean thủ công khi cấu hình hiện tại chưa cung cấp `Neo4jClient` hoặc khi bạn có chủ đích thay đổi cách tạo client. Nếu auto-configuration đã tạo bean, việc khai báo thêm một bean cùng kiểu có thể gây xung đột hoặc làm thay đổi hành vi cấu hình.

## 4. Khi cần tạo Driver thủ công

Trong ứng dụng Spring Boot thông thường, hãy ưu tiên dùng `Driver` đã được Boot cấu hình. Nếu bạn cần tự cấu hình kết nối trong một ứng dụng Spring không dùng auto-configuration, hãy tạo một bean `Driver` dùng chung:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class Neo4jDriverConfiguration {

    @Bean(destroyMethod = "close")
    Driver neo4jDriver(
            @Value("${app.neo4j.uri}") String uri,
            @Value("${app.neo4j.username}") String username,
            @Value("${app.neo4j.password}") String password) {

        return GraphDatabase.driver(
            uri,
            AuthTokens.basic(username, password)
        );
    }
}
~~~

Ví dụ này dùng các thuộc tính riêng `app.neo4j.*` vì ứng dụng đang tự quản lý cấu hình. `destroyMethod = "close"` yêu cầu Spring đóng driver khi application context dừng.

`Driver` là đối tượng dùng chung trong suốt vòng đời ứng dụng và được thiết kế để tái sử dụng giữa các request. Không tạo `GraphDatabase.driver(...)` trong từng method truy vấn. Việc tạo driver mới liên tục làm tăng chi phí kết nối và gây khó khăn khi quản lý tài nguyên.

Sau khi có `Driver`, có thể tạo `Neo4jClient` bằng `Neo4jClient.create(driver)` như ví dụ phần trước. Driver cần được đóng đúng một lần khi ứng dụng kết thúc; không đóng driver sau mỗi query.

## 5. Thực thi truy vấn và bind tham số

Ví dụ tìm tên một người theo email:

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class PersonQueryRepository {

    private final Neo4jClient neo4jClient;

    public PersonQueryRepository(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Optional<String> findNameByEmail(String email) {
        return neo4jClient.query("""
                MATCH (p:Person)
                WHERE p.email = $email
                RETURN p.name AS name
                """)
            .bind(email).to("email")
            .fetchAs(String.class)
            .mappedBy((typeSystem, record) -> record.get("name").asString())
            .one();
    }
}
~~~

Luồng thực hiện:

1. `query(...)` nhận câu Cypher.
2. `bind(email).to("email")` gắn giá trị Java vào tham số `$email`.
3. `fetchAs(String.class)` khai báo kiểu kết quả mà caller mong muốn.
4. `mappedBy(...)` chuyển record thành chuỗi từ cột `name`.
5. `one()` trả về `Optional<String>` cho trường hợp không có hoặc có một kết quả.

Dùng tham số thay vì nối chuỗi đầu vào vào Cypher. Điều này tách dữ liệu khỏi cú pháp truy vấn, xử lý đúng các ký tự đặc biệt và giảm nguy cơ Cypher injection.

`one()` phù hợp khi điều kiện truy vấn bảo đảm tối đa một record, chẳng hạn email có uniqueness constraint. Nếu query có thể trả về nhiều record, dùng `all()` hoặc giới hạn kết quả có chủ đích; không dùng `one()` để ngầm chọn một record tùy ý.

## 6. Các cách đọc kết quả phổ biến

`Neo4jClient` hỗ trợ nhiều cách lấy kết quả tùy theo số lượng và kiểu dữ liệu:

~~~java
// Tất cả record dưới dạng map
Collection<Map<String, Object>> rows = neo4jClient.query("""
        MATCH (p:Person)
        RETURN p.name AS name, p.email AS email
        """)
    .fetch()
    .all();
~~~

~~~java
// Một giá trị đã ánh xạ
Optional<Long> total = neo4jClient.query("""
        MATCH (p:Person)
        RETURN count(p) AS total
        """)
    .fetchAs(Long.class)
    .mappedBy((typeSystem, record) -> record.get("total").asLong())
    .one();
~~~

Các phương thức thường gặp:

| API | Kết quả | Khi dùng |
|---|---|---|
| `fetch().all()` | Collection record dưới dạng map | Cần nhiều cột và muốn xử lý dữ liệu tổng quát |
| `fetchAs(T.class).mappedBy(...).all()` | Collection kiểu `T` | Cần ánh xạ nhiều record thành DTO hoặc kiểu cụ thể |
| `fetchAs(T.class).mappedBy(...).one()` | `Optional<T>` | Query có tối đa một record |
| `fetchAs(T.class).mappedBy(...).first()` | `Optional<T>` đầu tiên | Cần lấy record đầu theo thứ tự query đã xác định |

Nếu dùng `first()`, hãy đặt `ORDER BY` trong Cypher khi thứ tự có ý nghĩa. Nếu không có thứ tự, “đầu tiên” không phải một lựa chọn ổn định theo nghiệp vụ.

## 7. Bind nhiều tham số

Khi query có nhiều tham số, có thể bind từng tham số:

~~~java
return neo4jClient.query("""
        MATCH (p:Person)
        WHERE p.active = $active
          AND p.age >= $minAge
        RETURN p.name AS name
        ORDER BY p.name
        """)
    .bind(true).to("active")
    .bind(18).to("minAge")
    .fetchAs(String.class)
    .mappedBy((typeSystem, record) -> record.get("name").asString())
    .all();
~~~

Hoặc truyền một map tham số:

~~~java
Map<String, Object> parameters = Map.of(
    "active", true,
    "minAge", 18
);

return neo4jClient.query("""
        MATCH (p:Person)
        WHERE p.active = $active
          AND p.age >= $minAge
        RETURN p.name AS name
        """)
    .bindAll(parameters)
    .fetchAs(String.class)
    .mappedBy((typeSystem, record) -> record.get("name").asString())
    .all();
~~~

Tên key trong map phải trùng với tên placeholder Cypher nhưng không có dấu `$`. Không truyền map có key thừa hoặc thiếu so với query mà không kiểm tra; quản lý query và tham số cùng một nơi giúp tránh lỗi khi thêm hoặc đổi điều kiện.

## 8. Dùng Neo4jClient trong service

Lớp truy vấn dữ liệu nên trả về kiểu phù hợp với use case. Service phối hợp kết quả với nghiệp vụ:

~~~java
import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class PersonService {

    private final PersonQueryRepository queries;

    public PersonService(PersonQueryRepository queries) {
        this.queries = queries;
    }

    public String getDisplayName(String email) {
        return queries.findNameByEmail(email)
            .orElseThrow(() -> new IllegalArgumentException("Person not found"));
    }
}
~~~

Ví dụ này giữ chi tiết Cypher trong lớp truy cập dữ liệu và để service quyết định cách xử lý trường hợp không tìm thấy. Với ứng dụng lớn, nên trả về DTO thay vì để service phụ thuộc vào `Map<String, Object>` hoặc kiểu `Record` của driver.

## 9. Transaction và vòng đời tài nguyên

`Neo4jClient` sử dụng driver và tham gia cơ chế transaction của Spring Data Neo4j khi được cấu hình trong application context. Với nghiệp vụ gồm nhiều thao tác đọc/ghi cần tính nguyên tử, đặt ranh giới ở tầng service bằng `@Transactional`:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonCommandService {

    private final PersonQueryRepository queries;

    public PersonCommandService(PersonQueryRepository queries) {
        this.queries = queries;
    }

    @Transactional
    public void updatePersonGraph() {
        // Gọi các thao tác SDN/Neo4jClient thuộc cùng use case.
    }
}
~~~

Đảm bảo các thao tác dùng cùng transaction manager và cùng cơ chế quản lý transaction. Nếu tự mở session hoặc transaction trực tiếp từ driver, không giả định chúng tự tham gia transaction Spring đang hoạt động; cần dùng cơ chế tích hợp phù hợp hoặc quản lý transaction driver tường minh.

Với các truy vấn thông thường qua `Neo4jClient`, không cần tự mở một driver `Session` cho mỗi query. Client quản lý việc thực thi qua driver. Khi dùng Java Driver trực tiếp ngoài client, phải quản lý vòng đời `Session` và `Result` theo API driver, đồng thời đóng session sau khi hoàn tất.

## 10. Khi nào dùng Neo4jClient thay cho Repository?

| Nhu cầu | API nên chọn | Lý do |
|---|---|---|
| CRUD entity theo ID | `Neo4jRepository` | Hợp đồng rõ và ít mã |
| Tìm entity theo property | Derived query hoặc `@Query` | SDN ánh xạ kết quả thành entity |
| Truy vấn tổng hợp như `count`, `sum` | `Neo4jClient` | Ánh xạ trực tiếp scalar hoặc DTO |
| Cypher tùy chỉnh trả về nhiều cột | `Neo4jClient` | Kiểm soát record và kiểu kết quả |
| Thao tác entity theo API template | `Neo4jTemplate` | Tận dụng mapping metadata của SDN |
| Tích hợp đặc thù cần API thấp của driver | Neo4j Java Driver | Kiểm soát trực tiếp session và transaction |

Không cần dùng `Neo4jClient` cho mọi truy vấn. Nếu một derived query hoặc repository method thể hiện nghiệp vụ rõ ràng, hãy ưu tiên nó. Chọn client khi bạn cần sự linh hoạt của Cypher hoặc kết quả không phải entity đầy đủ.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tạo `Driver` hoặc `Neo4jClient` trong mỗi request | Tăng chi phí khởi tạo và khó quản lý tài nguyên | Inject bean singleton do Spring quản lý |
| Tự khai báo client trong khi Boot đã tạo bean | Có thể gây xung đột hoặc thay đổi auto-configuration | Inject bean có sẵn; chỉ tùy chỉnh khi có lý do |
| Ghi mật khẩu trực tiếp trong source | Lộ thông tin đăng nhập | Dùng biến môi trường hoặc secret store |
| Nối giá trị người dùng vào Cypher | Có nguy cơ Cypher injection và lỗi escape | Bind bằng `.bind(...).to(...)` hoặc `.bindAll(...)` |
| Gọi `one()` cho query có thể trả nhiều record | Phát sinh lỗi kích thước kết quả | Dùng `all()` hoặc giới hạn và sắp xếp rõ ràng |
| Gọi `first()` mà không có `ORDER BY` | Kết quả đầu không ổn định | Xác định thứ tự trong Cypher |
| Mở driver session thủ công rồi quên đóng | Rò rỉ tài nguyên | Dùng try-with-resources và quản lý transaction phù hợp |
| Cho rằng client tự tạo schema | Node/constraint/index không tự xuất hiện | Quản lý schema bằng migration hoặc Cypher riêng |

## 12. Tự kiểm tra

1. Khi dùng `spring-boot-starter-data-neo4j`, vì sao thường không cần tự tạo `Neo4jClient`?
2. `Neo4jClient` khác `Neo4jRepository` ở mục đích sử dụng nào?
3. Vì sao `Driver` nên được dùng chung trong vòng đời ứng dụng?
4. `.bind(value).to("name")` liên kết với placeholder nào trong Cypher?
5. Khác biệt giữa `one()`, `first()` và `all()` là gì?
6. Khi nào nên tạo bean `Neo4jClient` thủ công?
7. Vì sao không nên tự mở driver session cho từng query khi đã dùng `Neo4jClient`?

Trong ứng dụng Spring Boot, hãy để cấu hình tự động cung cấp `Neo4jClient` và inject nó qua constructor. Chỉ tự tạo client khi bạn đang quản lý cấu hình driver thủ công hoặc cần một cấu hình riêng có chủ đích. Luôn bind giá trị, chọn kiểu fetch phù hợp và đặt transaction ở ranh giới nghiệp vụ.
