# Cấu hình MyBatisJdbcConfiguration và SqlSessionFactory

Spring Data JDBC có thể giao việc thực thi một số thao tác CRUD và query cho **MyBatis**. Tích hợp này giữ repository và mô hình aggregate của Spring Data JDBC, đồng thời cho phép viết SQL và mapping chi tiết bằng MyBatis khi câu SQL mặc định chưa đáp ứng yêu cầu.

Hai thành phần cấu hình chính là:

- `MyBatisJdbcConfiguration`: thay `DataAccessStrategy` mặc định bằng chiến lược có khả năng tìm và sử dụng các mapped statement của MyBatis.
- `SqlSessionFactory`: chứa cấu hình MyBatis và các statement đã nạp từ mapper XML hoặc annotation. Trong Spring, `SqlSessionFactoryBean` là cách thông dụng để tạo factory này.

Điểm quan trọng là tích hợp này không biến repository thành MyBatis mapper thông thường. Spring Data JDBC vẫn điều phối vòng đời aggregate; ở từng bước persistence, nó kiểm tra xem MyBatis có cung cấp statement theo quy ước tên hay không. Nếu có, statement đó được dùng để thực thi thao tác tương ứng.

## 1. Khi nào cần tích hợp MyBatis?

Spring Data JDBC tự tạo SQL cho các thao tác aggregate thông thường. Cách này phù hợp với phần lớn CRUD. Tuy nhiên, có những trường hợp cần kiểm soát SQL hoặc mapping ở mức thấp hơn:

- Dùng cú pháp đặc thù của database.
- Tối ưu câu INSERT/UPDATE hoặc truy vấn theo execution plan.
- Dùng stored procedure, CTE, hint hoặc biểu thức SQL đặc thù.
- Ánh xạ kết quả query phức tạp theo cấu trúc MyBatis.
- Giữ repository Spring Data JDBC nhưng thay một số câu lệnh persistence bằng SQL do nhóm phát triển quản lý.

Ví dụ, ứng dụng có OrderRepository extends CrudRepository<Order, Long>, nhưng muốn tùy chỉnh câu INSERT của bảng orders và câu SELECT theo ID. Có thể định nghĩa các mapped statement tương ứng trong MyBatis, sau đó để Spring Data JDBC gọi chúng trong quá trình repository hoạt động.

~~~mermaid
flowchart TD
    App["Application Service"]
    Repo["Spring Data JDBC Repository"]
    Strategy["MyBatisDataAccessStrategy"]
    Check{"SqlSessionFactory có<br/>mapped statement phù hợp?"}
    MB["MyBatis mapped statement"]
    Default["Default Spring Data JDBC strategy"]
    DB[("Database")]
    App --> Repo --> Strategy --> Check
    Check -->|Có| MB --> DB
    Check -->|Không| Default --> DB
~~~

MyBatis integration cho phép thay thế theo từng bước. Không nhất thiết phải viết lại toàn bộ CRUD bằng MyBatis; chỉ định nghĩa những statement thực sự cần tùy chỉnh.

## 2. Các thành phần cần hiểu

| Thành phần | Vai trò |
|---|---|
| `MyBatisJdbcConfiguration` | Cấu hình Spring Data JDBC dùng `MyBatisDataAccessStrategy` |
| `DataAccessStrategy` | Lớp chiến lược thực hiện các thao tác đọc/ghi aggregate |
| `SqlSessionFactoryBean` | Spring `FactoryBean` tạo `SqlSessionFactory` |
| `SqlSessionFactory` | Giữ cấu hình MyBatis và tập mapped statement đã nạp |
| Mapper XML | Khai báo SQL, parameter mapping và result mapping |
| `MyBatisContext` | Đối tượng Spring Data JDBC truyền vào mapped statement |
| `CrudRepository` | API repository mà application service vẫn gọi |

### SqlSessionFactoryBean và SqlSessionFactory khác nhau

`SqlSessionFactoryBean` là đối tượng cấu hình/tạo factory theo cơ chế Spring `FactoryBean`. Bean mà các thành phần khác trong application context nhận được theo tên thông thường là sản phẩm của factory: `SqlSessionFactory`.

`SqlSessionFactory` tạo các session để MyBatis thực thi statement. Ứng dụng không nên tự giữ một `SqlSession` dùng chung trong field hoặc tự mở/đóng session cho từng thao tác repository. MyBatis-Spring quản lý vòng đời session và kết hợp nó với transaction Spring.

## 3. Dependency

Cần có Spring Data JDBC và MyBatis-Spring tương thích với phiên bản Spring Framework/Spring Boot đang dùng. MyBatis-Spring kết nối MyBatis core với Spring container.

Nếu dự án dùng Spring Boot, có thể dùng MyBatis Spring Boot starter tương thích để quản lý dependency:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    implementation("org.mybatis.spring.boot:mybatis-spring-boot-starter")
}
~~~

Đoạn Gradle trên giả định dự án quản lý version bằng Spring Boot dependency management hoặc version catalog/platform tương thích. Nếu không dùng starter, khai báo trực tiếp `org.mybatis:mybatis` và `org.mybatis:mybatis-spring` theo cặp phiên bản tương thích. Dự án vẫn cần dependency Spring Data JDBC như trước.

Không cần đồng thời khai báo starter và các dependency trực tiếp trùng lặp nếu starter đã cung cấp chúng. Kiểm tra dependency tree khi có lỗi class hoặc method không tương thích.

## 4. Import MyBatisJdbcConfiguration

Lớp cấu hình nằm trong package:

~~~java
import org.springframework.data.jdbc.repository.config.MyBatisJdbcConfiguration;
~~~

Ví dụ cấu hình:

~~~java
package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;
import org.springframework.data.jdbc.repository.config.MyBatisJdbcConfiguration;

@Configuration
@EnableJdbcRepositories(basePackages = "com.example.sales")
@Import(MyBatisJdbcConfiguration.class)
public class JdbcPersistenceConfiguration {
}
~~~

`@EnableJdbcRepositories` bật repository scanning cho package đã chỉ định. `@Import(MyBatisJdbcConfiguration.class)` đăng ký cấu hình thay thế `DataAccessStrategy` mặc định để Spring Data JDBC có thể dùng MyBatis.

Trong Spring Boot, repository scanning có thể đã được tự cấu hình theo package của application class. Khi đó hãy đặt `@Import(MyBatisJdbcConfiguration.class)` trong cấu hình được Spring scan và tránh khai báo repository scanning trùng lặp hoặc với base package không chủ ý.

Không tự tạo một `DataAccessStrategy` khác nếu mục tiêu chỉ là dùng MyBatis integration có sẵn. `MyBatisJdbcConfiguration` đã cung cấp bean chiến lược phù hợp.

## 5. Khai báo SqlSessionFactoryBean

MyBatis cần một `SqlSessionFactory` trong application context. Cách cấu hình tường minh với mapper XML:

~~~java
package com.example.config;

import java.io.IOException;
import javax.sql.DataSource;

import org.mybatis.spring.SqlSessionFactoryBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

@Configuration
public class MyBatisConfiguration {

    @Bean
    public SqlSessionFactoryBean sqlSessionFactoryBean(
            DataSource dataSource) throws IOException {

        SqlSessionFactoryBean factoryBean = new SqlSessionFactoryBean();
        factoryBean.setDataSource(dataSource);
        factoryBean.setMapperLocations(
            new PathMatchingResourcePatternResolver()
                .getResources("classpath*:mybatis/**/*.xml")
        );

        return factoryBean;
    }
}
~~~

Phương thức `@Bean` trả về `SqlSessionFactoryBean`. Vì đây là Spring `FactoryBean`, Spring tạo sản phẩm `SqlSessionFactory` và cung cấp factory đó trong application context. Đây là kiểu cấu hình được tài liệu tích hợp Spring Data JDBC minh họa.

### Dùng chung DataSource

Tham số `DataSource` được inject từ cấu hình Spring Boot hoặc cấu hình database của ứng dụng. Hãy dùng **cùng DataSource** cho:

- Spring Data JDBC.
- `SqlSessionFactoryBean` của MyBatis.
- Transaction manager JDBC của ứng dụng.

Khi hai framework dùng cùng DataSource và transaction manager phù hợp, các câu SQL do Spring Data JDBC và MyBatis thực hiện có thể tham gia cùng transaction. Nếu tạo hai DataSource độc lập, transaction có thể không bao trùm cả hai đường truy cập dữ liệu.

### Cấu hình mapper location

Đường dẫn `classpath*:mybatis/**/*.xml` cho phép nạp các mapper XML bên dưới thư mục `mybatis` trong classpath. Cấu trúc thư mục có thể là:

~~~text
src/main/resources/
└── mybatis/
    └── com/
        └── example/
            └── sales/
                ├── CustomerMapper.xml
                └── OrderMapper.xml
~~~

Nếu mapper XML đặt cạnh mapper interface hoặc dùng annotation, cấu hình nạp có thể khác. Điều quan trọng là các mapped statement cần thiết phải có mặt trong `SqlSessionFactory` khi ứng dụng khởi động.

## 6. Cấu hình MyBatis bằng Configuration object

Có thể thiết lập một số tùy chọn MyBatis bằng Java thay vì file mybatis-config.xml. Ví dụ bật ánh xạ tên cột underscore sang property camelCase:

~~~java
import org.apache.ibatis.session.Configuration;
import org.mybatis.spring.SqlSessionFactoryBean;

@Bean
public SqlSessionFactoryBean sqlSessionFactoryBean(
        DataSource dataSource) throws IOException {

    SqlSessionFactoryBean factoryBean = new SqlSessionFactoryBean();
    factoryBean.setDataSource(dataSource);
    factoryBean.setMapperLocations(
        new PathMatchingResourcePatternResolver()
            .getResources("classpath*:mybatis/**/*.xml")
    );

    Configuration myBatisConfiguration = new Configuration();
    myBatisConfiguration.setMapUnderscoreToCamelCase(true);
    factoryBean.setConfiguration(myBatisConfiguration);

    return factoryBean;
}
~~~

Với cấu hình trên, customer_name có thể ánh xạ sang customerName khi dùng cơ chế tự động mapping. Có thể bổ sung settings, type aliases, type handlers hoặc plugin theo nhu cầu. Nếu dùng resultMap tường minh, mapping được khai báo trực tiếp trong XML và ít phụ thuộc naming convention hơn.

Một lựa chọn khác là dùng `configLocation` để nạp file cấu hình MyBatis. Không nên cấu hình trùng lặp các settings ở nhiều nơi; chọn một nguồn cấu hình rõ ràng. Khi dùng `SqlSessionFactoryBean` với Spring, DataSource và transaction do Spring quản lý; không sao chép một environment độc lập trong MyBatis config rồi giả định nó tự tham gia transaction Spring.

## 7. Quy ước tên mapper statement

Mapper XML có hai phần quan trọng:

- `namespace`: định danh nhóm mapped statement.
- `id`: tên statement cụ thể.

Spring Data JDBC tìm statement theo quy ước:

~~~text
<fully-qualified-domain-type>Mapper.<operation>
~~~

Ví dụ entity có tên đầy đủ `com.example.sales.Customer`. Statement insert cần có tên:

~~~text
com.example.sales.CustomerMapper.insert
~~~

Vì vậy mapper XML có namespace `com.example.sales.CustomerMapper` và statement id `insert`:

~~~xml
<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE mapper
  PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
  "https://mybatis.org/dtd/mybatis-3-mapper.dtd">

<mapper namespace="com.example.sales.CustomerMapper">
    <!-- Mapped statements được khai báo ở đây. -->
</mapper>
~~~

Namespace là quy ước tên statement mà Spring Data JDBC tìm kiếm. Nó không nhất thiết phải là tên một Java mapper interface có `@Mapper`; trong tích hợp này, tên entity đầy đủ và hậu tố `Mapper` quyết định namespace.

## 8. MyBatisContext được truyền vào statement

Khi Spring Data JDBC tìm thấy mapped statement phù hợp và thực thi nó, MyBatis nhận một `MyBatisContext` làm parameter object. Class nằm trong package:

~~~java
import org.springframework.data.jdbc.mybatis.MyBatisContext;
~~~

Các thông tin chính:

| Thuộc tính | Ý nghĩa | Có thể null? |
|---|---|---|
| `getInstance()` | Entity đang được insert/update/delete | Có, tùy loại statement |
| `getId()` | ID của entity cần đọc/xóa | Có, tùy thao tác |
| `getDomainType()` | Class domain type đang được xử lý | Có, tùy thao tác |
| `getIdentifier()` | Identifier mô tả đường dẫn tham chiếu tới entity | Có, tùy thao tác |
| `get(key)` | Giá trị bổ sung, thường dùng để lấy ID của entity cha theo tên back-reference column | Có, tùy thao tác |

Trong MyBatis XML, các getter có thể được truy cập bằng property expression. Ví dụ `getInstance()` được tham chiếu như `instance`; `getId()` như `id`. Không giả định mọi property đều tồn tại trong mọi statement: tài liệu API cho biết các giá trị có thể null tùy loại thao tác.

### Ví dụ dùng instance

Khi insert/update, `instance` là object đang được ghi:

~~~xml
#{instance.name}
#{instance.email}
~~~

### Ví dụ dùng ID

Khi tìm hoặc xóa theo ID:

~~~xml
#{id}
~~~

### ID của entity cha

Khi insert một thành phần con thuộc aggregate, Spring Data JDBC có thể cung cấp ID của entity tham chiếu thông qua `get(key)`. Key là tên back-reference column theo `NamingStrategy`. Điều này cho phép mapper ghi khóa ngoại của child mà không cần tự truy vấn lại aggregate root.

## 9. Những mapped statement được Spring Data JDBC tìm kiếm

Spring Data JDBC thực hiện nhiều SQL statement cho một thao tác repository. MyBatis integration dùng quy ước tên để tìm statement cho từng bước. Các tên phổ biến được mô tả trong bảng:

| Statement id | Mục đích | Repository method có thể kích hoạt |
|---|---|---|
| `insert` | Insert một entity; áp dụng cả entity được aggregate root tham chiếu | `save`, `saveAll` |
| `update` | Update một entity; áp dụng cả entity được aggregate root tham chiếu | `save`, `saveAll` |
| `delete` | Delete một entity theo ID | `delete`, `deleteById` |
| `deleteAll-<propertyPath>` | Xóa các entity được tham chiếu qua property path từ aggregate root | `deleteAll` |
| `deleteAll` | Xóa tất cả aggregate root có kiểu được dùng làm prefix | `deleteAll` |
| `delete-<propertyPath>` | Xóa các entity được tham chiếu theo property path khi xóa root theo ID | `deleteById` |
| `findById` | Tải aggregate root theo ID | `findById` |
| `findAll` | Tải tất cả aggregate root | `findAll` |
| `findAllById` | Tải aggregate root theo tập ID | `findAllById` |
| `findAllByPath-<propertyPath>` | Tải entity được tham chiếu theo property path | Các `find*` method |
| `findAllSorted` | Tải aggregate root theo sort | `findAll(Sort)` |
| `findAllPaged` | Tải một trang aggregate root | `findAll(Pageable)` |
| `count` | Đếm aggregate root của kiểu được dùng làm prefix | `count` |

Tên statement đầy đủ luôn gồm namespace dựa trên domain type và statement id. Ví dụ với `com.example.sales.Order`:

~~~text
com.example.sales.OrderMapper.insert
com.example.sales.OrderMapper.update
com.example.sales.OrderMapper.findById
com.example.sales.OrderMapper.count
~~~

Statement `findAllByProperty-<propertyName>` là quy ước cũ đã deprecated; dùng `findAllByPath-<propertyPath>` cho trường hợp mới theo tài liệu hiện hành.

Không phải mọi repository method đều tương ứng một SQL statement duy nhất. Khi save aggregate có child collection, Spring Data JDBC có thể thực hiện nhiều thao tác insert/update/delete cho các thành phần. Vì vậy, nếu tùy chỉnh persistence của aggregate, hãy xem xét cả statement cho root và child mà thao tác đó có thể cần.

## 10. Ví dụ entity và mapper insert/update/find

Entity Customer đơn giản:

~~~java
package com.example.sales;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;
    private String name;
    private String email;

    protected Customer() {
    }

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Mapper XML:

~~~xml
<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE mapper
  PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
  "https://mybatis.org/dtd/mybatis-3-mapper.dtd">

<mapper namespace="com.example.sales.CustomerMapper">

    <resultMap id="customerResult"
               type="com.example.sales.Customer">
        <id column="id" property="id"/>
        <result column="name" property="name"/>
        <result column="email" property="email"/>
    </resultMap>

    <insert id="insert"
            parameterType="org.springframework.data.jdbc.mybatis.MyBatisContext"
            useGeneratedKeys="true"
            keyProperty="instance.id">
        INSERT INTO customers (name, email)
        VALUES (#{instance.name}, #{instance.email})
    </insert>

    <update id="update"
            parameterType="org.springframework.data.jdbc.mybatis.MyBatisContext">
        UPDATE customers
        SET name = #{instance.name},
            email = #{instance.email}
        WHERE id = #{instance.id}
    </update>

    <select id="findById"
            parameterType="org.springframework.data.jdbc.mybatis.MyBatisContext"
            resultMap="customerResult">
        SELECT id, name, email
        FROM customers
        WHERE id = #{id}
    </select>
</mapper>
~~~

Ví dụ dùng generated key của MyBatis (`useGeneratedKeys`) và `keyProperty="instance.id"` để minh họa cách đưa khóa được database tạo trở lại object. Khả năng lấy generated key phụ thuộc database/driver và chiến lược ID của dự án. Nếu dùng UUID hoặc ID được ứng dụng cấp trước, bỏ cấu hình generated key và bind ID theo thiết kế tương ứng.

Schema:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL
);
~~~

Repository vẫn là Spring Data JDBC:

~~~java
package com.example.sales;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Service tiếp tục gọi repository như bình thường:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    public Customer create(String name, String email) {
        return customers.save(new Customer(name, email));
    }
}
~~~

Khi `save` chạy, Spring Data JDBC kiểm tra `SqlSessionFactory` xem statement `com.example.sales.CustomerMapper.insert` có tồn tại hay không. Nếu có, MyBatis thực thi SQL đã định nghĩa và dùng result/parameter mapping tương ứng.

## 11. Tùy chỉnh SQL cho child entity

Một aggregate có thể chứa collection con:

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    private String status;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;
}
~~~

`OrderLine` được lưu trong bảng riêng nhưng vòng đời persistence do aggregate root quản lý. Khi Spring Data JDBC insert root và các line, statement `insert` có thể được tìm cho cả entity được tham chiếu.

Namespace của mapper statement cho child dựa trên fully qualified class name của child entity. MyBatisContext cung cấp ID của entity cha qua key tương ứng với back-reference column do `NamingStrategy` tạo.

Vì tên cột tham chiếu có thể phụ thuộc `NamingStrategy` hoặc `@MappedCollection(idColumn = ...)`, mapper phải dùng đúng tên key mà mapping cung cấp. Không hardcode giả định tên cột luôn là `order_id` nếu cấu hình thực tế khác.

## 12. Tích hợp query methods và phân trang

MyBatis integration hỗ trợ các bước đọc mà Spring Data JDBC thực hiện. Một số statement có quy ước riêng:

- `findById`: tải một aggregate root theo ID.
- `findAll`: tải tất cả aggregate root.
- `findAllById`: tải root theo danh sách ID.
- `findAllSorted`: tải theo `Sort`.
- `findAllPaged`: tải theo `Pageable`.
- `count`: đếm aggregate root.

Ví dụ tên statement:

~~~text
com.example.sales.OrderMapper.findAllPaged
com.example.sales.OrderMapper.findAllSorted
com.example.sales.OrderMapper.findAllById
com.example.sales.OrderMapper.count
~~~

Với `findAllPaged`, `MyBatisContext` cung cấp `getPageable()` để statement sử dụng thông tin trang và sort. Với `findAllSorted`, context cung cấp `getSort()`. SQL mapper phải chuyển thông tin đó thành ORDER BY và phân trang theo dialect database.

Không nối chuỗi sort từ request trực tiếp vào SQL XML. Hãy dùng property/sort đã được kiểm soát ở tầng API và chuyển nó sang các cột cố định trong mapper. Nếu dùng pagination, count query và content query phải có cùng điều kiện lọc để metadata trang chính xác.

## 13. SqlSessionFactory, SqlSession và transaction

`SqlSessionFactory` là factory dùng chung, nhưng session thực thi cần gắn với transaction và thread phù hợp.

Trong MyBatis-Spring:

- `SqlSessionFactoryBean` tạo factory.
- `SqlSessionTemplate` là implementation `SqlSession` thread-safe thường dùng khi viết DAO/mapper trực tiếp.
- MyBatis-Spring quản lý session lifecycle, commit/rollback và đóng session.
- Nếu có transaction Spring đang hoạt động và cùng DataSource, MyBatis dùng connection gắn với transaction đó.

Khi tích hợp qua `MyBatisJdbcConfiguration`, Spring Data JDBC dùng MyBatis data access strategy và `SqlSessionFactory` đã cấu hình. Không cần tự mở session thủ công trong repository hoặc callback.

Ví dụ application service:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;

    public OrderApplicationService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Order place(Order order) {
        return orders.save(order);
    }
}
~~~

Nếu một lần save aggregate dùng nhiều mapped statement MyBatis cho root và child, các câu lệnh đó nên cùng tham gia transaction. Cấu hình cùng DataSource và transaction manager là điều kiện quan trọng để rollback không để lại một phần aggregate đã ghi.

Không tự cấu hình một MyBatis transaction manager độc lập với DataSource khác rồi giả định nó sẽ phối hợp nguyên tử với transaction của Spring Data JDBC.

## 14. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy `SqlSessionFactory` | Chưa khai báo `SqlSessionFactoryBean` hoặc MyBatis starter chưa tạo factory | Kiểm tra bean factory và dependency |
| `MyBatisJdbcConfiguration` không được áp dụng | Quên `@Import` hoặc cấu hình không được scan | Import configuration trong application context |
| Statement không được tìm thấy | Namespace hoặc statement id sai quy ước | Dùng fully qualified entity name + `Mapper` + operation |
| Mapper XML không được nạp | `mapperLocations` sai hoặc resource không nằm trong classpath | Kiểm tra pattern và vị trí file |
| MyBatis không bind được `instance.name` | Parameter object hoặc property path sai | Dùng `MyBatisContext` và kiểm tra tên property |
| `findById` không trả entity đúng | ResultMap/resultType không khớp entity | Khai báo resultMap tường minh |
| Child insert thiếu foreign key | Không dùng parent reference từ `MyBatisContext` hoặc key sai | Kiểm tra back-reference column và `get(key)` |
| Generated ID vẫn null | Cấu hình key generation không phù hợp driver/database | Kiểm tra `useGeneratedKeys`, `keyProperty` hoặc ID strategy |
| Spring rollback nhưng MyBatis đã commit | Khác DataSource/transaction manager hoặc session quản lý sai | Dùng cùng DataSource và MyBatis-Spring integration |
| Một số thao tác chạy SQL mặc định, thao tác khác chạy MyBatis | Chỉ một số mapped statement tồn tại | Kiểm tra statement name cho từng bước |
| Lỗi binding do underscore/camelCase | Mapping tự động không khớp tên cột/property | Dùng resultMap hoặc cấu hình naming rõ ràng |

## 15. Checklist triển khai

Trước khi bật MyBatis integration:

1. Chọn phiên bản MyBatis và MyBatis-Spring tương thích với Spring Boot/Spring Data JDBC.
2. Xác nhận dependency có cả MyBatis core và bridge MyBatis-Spring.
3. Import `MyBatisJdbcConfiguration`.
4. Cấu hình một `SqlSessionFactory` trong application context.
5. Dùng cùng `DataSource` với Spring Data JDBC.
6. Cấu hình mapper XML location hoặc cơ chế nạp statement tương ứng.
7. Đặt namespace theo fully qualified entity type cộng hậu tố `Mapper`.
8. Đặt statement id đúng operation name.
9. Dùng `MyBatisContext` để đọc instance, ID, domain type và parent reference.
10. Viết resultMap rõ ràng cho những kết quả cần mapping tùy chỉnh.
11. Kiểm tra generated ID, version field và foreign key nếu mapper tùy chỉnh insert/update aggregate.
12. Kiểm thử transaction rollback trên aggregate có root và child.

## 16. Bài thực hành

1. Thêm dependency Spring Data JDBC và MyBatis-Spring tương thích vào một ứng dụng mẫu.
2. Import `MyBatisJdbcConfiguration` trong cấu hình persistence.
3. Tạo `SqlSessionFactoryBean` dùng chung `DataSource` và nạp mapper XML từ `classpath*:mybatis/**/*.xml`.
4. Tạo entity Customer và `CustomerRepository extends CrudRepository<Customer, Long>`.
5. Tạo mapper XML có namespace `com.example.sales.CustomerMapper`.
6. Viết statement `insert`, `update` và `findById` dùng `MyBatisContext`.
7. Gọi `repository.save`, `findById` và xác minh MyBatis statement được dùng khi có mapping tương ứng.
8. Bỏ một mapped statement trong môi trường kiểm thử và quan sát chiến lược mặc định xử lý bước không có statement tương ứng.
9. Tạo Order aggregate có OrderLine; viết statement insert cho root và child.
10. Lấy parent ID trong statement child từ `MyBatisContext` theo back-reference key được cấu hình.
11. Viết `findAllPaged` và `count`; xác minh nội dung trang và tổng số dùng cùng điều kiện.
12. Tạo lỗi giữa chừng khi lưu aggregate và xác minh transaction rollback cả thao tác MyBatis lẫn Spring Data JDBC.

## 17. Ghi nhớ

Để tích hợp MyBatis với Spring Data JDBC, import `MyBatisJdbcConfiguration` và cung cấp `SqlSessionFactory` thông qua `SqlSessionFactoryBean` hoặc cấu hình tương đương. Factory phải dùng cùng `DataSource` với Spring Data JDBC để các thao tác có thể tham gia cùng transaction.

Spring Data JDBC vẫn điều phối aggregate và repository. Với từng bước CRUD/query, nó tìm mapped statement theo quy ước `<fully-qualified-domain-type>Mapper.<operation>`. Nếu có statement phù hợp, MyBatis thực thi SQL và mapping đã cấu hình. `MyBatisContext` cung cấp entity instance, ID, domain type và thông tin tham chiếu cha để mapper dùng đúng dữ liệu.

Hãy bắt đầu bằng việc tùy chỉnh một vài statement thực sự cần thiết, giữ tên namespace/statement chính xác, cấu hình mapper XML và transaction nhất quán, rồi mở rộng sang child entity hoặc phân trang khi cần.

## Tài liệu tham khảo

- [Spring Data Relational — MyBatis Integration](https://docs.spring.io/spring-data/relational/reference/jdbc/mybatis.html)
- [MyBatisJdbcConfiguration API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/MyBatisJdbcConfiguration.html)
- [MyBatisContext API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/mybatis/MyBatisContext.html)
- [MyBatis-Spring — SqlSessionFactoryBean](https://mybatis.org/spring/factorybean.html)
- [MyBatis-Spring — Transactions](https://mybatis.org/spring/transactions.html)
