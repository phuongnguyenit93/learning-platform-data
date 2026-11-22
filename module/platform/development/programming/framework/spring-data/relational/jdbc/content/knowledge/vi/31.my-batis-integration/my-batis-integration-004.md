# Ủy quyền từng bước CRUD và xử lý generated keys trong Spring Data JDBC với MyBatis

## 1. Ý tưởng tích hợp: Spring Data JDBC điều phối, MyBatis thực thi SQL

Spring Data JDBC cung cấp repository theo aggregate. Khi gọi các method như save, saveAll, findById hoặc deleteById, framework phân tích aggregate và tạo ra một chuỗi thao tác persistence. Một thao tác lưu aggregate có thể cần nhiều câu SQL: insert hoặc update aggregate root, rồi insert/update/xóa các hàng thuộc collection con.

MyBatis có thể đảm nhiệm việc chạy SQL và ánh xạ kết quả cho từng bước đó. Spring Data JDBC vẫn quản lý repository, quyết định thao tác nào cần chạy và truyền thông tin của entity; MyBatis nhận mapped statement tương ứng để thực thi SQL.

Ví dụ:

- Ứng dụng gọi `customerRepository.save(customer)`.
- Spring Data JDBC xác định đây là insert hay update.
- Khi cần insert, framework tìm MyBatis statement có tên quy ước cho entity Customer.
- Nếu statement tồn tại, MyBatis chạy SQL và ánh xạ kết quả.
- Nếu không có statement MyBatis tương ứng, cấu hình combined strategy có thể chuyển bước đó về DefaultDataAccessStrategy.
- Spring Data JDBC tiếp tục các bước còn lại của aggregate.

Vì vậy, tích hợp này là **ủy quyền theo từng bước truy cập dữ liệu**, không phải thay toàn bộ repository bằng mapper interface. Ta có thể dùng MyBatis cho một số statement cần SQL riêng và để Spring Data JDBC xử lý các bước còn lại bằng strategy mặc định.

## 2. Các thành phần chính

| Thành phần | Vai trò |
|---|---|
| `CrudRepository` | API repository mà service sử dụng |
| `JdbcAggregateTemplate` | Điều phối thao tác trên aggregate |
| `DataAccessStrategy` | Abstraction cho từng bước SQL trên một entity |
| `MyBatisDataAccessStrategy` | Thực thi các bước thông qua MyBatis |
| `MyBatisJdbcConfiguration` | Cấu hình Spring Data JDBC để tích hợp MyBatis |
| `SqlSessionFactory` | Tạo MyBatis session và chứa các mapped statement |
| `SqlSessionTemplate` | `SqlSession` được quản lý bởi Spring, tham gia transaction |
| `MyBatisContext` | Object tham số Spring Data JDBC truyền cho mapped statement |

`DataAccessStrategy` xử lý thao tác ở mức một entity/statement. `JdbcAggregateOperations` mới là abstraction điều phối toàn bộ aggregate. Sự phân chia này giải thích vì sao một lần gọi repository có thể kích hoạt nhiều mapped statement khác nhau.

Trong Spring Data JDBC, các class quan trọng nằm trong những package sau:

~~~java
org.springframework.data.jdbc.repository.config.MyBatisJdbcConfiguration
org.springframework.data.jdbc.mybatis.MyBatisDataAccessStrategy
org.springframework.data.jdbc.mybatis.MyBatisContext
org.springframework.data.jdbc.core.convert.DataAccessStrategy
~~~

Tên package và API có thể thay đổi giữa các phiên bản Spring Data Relational. Hãy dùng tài liệu của đúng version đang được quản lý bởi Spring Boot hoặc dependency management của project.

## 3. Cấu hình Spring Data JDBC và MyBatis

Cách cấu hình được Spring Data JDBC hướng dẫn là import `MyBatisJdbcConfiguration` cùng với cấu hình repository, sau đó cung cấp `SqlSession` cho Spring context.

Ví dụ Java configuration:

~~~java
import javax.sql.DataSource;

import org.apache.ibatis.session.SqlSessionFactory;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;
import org.springframework.data.jdbc.repository.config.MyBatisJdbcConfiguration;

@Configuration
@EnableJdbcRepositories(
        basePackages = "com.example.persistence"
)
@Import(MyBatisJdbcConfiguration.class)
public class JdbcPersistenceConfiguration {

    @Bean
    public SqlSessionFactory sqlSessionFactory(DataSource dataSource)
            throws Exception {

        SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
        factory.setDataSource(dataSource);
        factory.setMapperLocations(
                new PathMatchingResourcePatternResolver()
                        .getResources("classpath*:mybatis/**/*.xml")
        );

        return factory.getObject();
    }

    @Bean
    public SqlSessionTemplate sqlSessionTemplate(
            SqlSessionFactory sqlSessionFactory
    ) {
        return new SqlSessionTemplate(sqlSessionFactory);
    }
}
~~~

`SqlSessionFactoryBean` tạo `SqlSessionFactory` từ DataSource và các file mapper XML. `SqlSessionTemplate` triển khai `SqlSession` và có thể được inject vào cấu hình Spring Data JDBC. Nếu dùng MyBatis Spring Boot starter, starter thường tự cấu hình SqlSessionFactory và SqlSessionTemplate; không khai báo thêm bean trùng nếu chúng đã tồn tại.

Cấu hình trên minh họa cách khai báo tường minh. Trong ứng dụng thực tế, cần bảo đảm:

- Mapper XML nằm trong đường dẫn được cấu hình.
- DataSource của MyBatis là DataSource mà Spring Data JDBC sử dụng.
- Bean SqlSession có thể được tìm thấy bởi MyBatisJdbcConfiguration.
- Repository scanning bao phủ đúng package chứa repository.
- Phiên bản MyBatis, MyBatis-Spring, Spring Data JDBC và Spring Boot tương thích.

### 3.1. Dependency

Nếu không dùng starter, ứng dụng cần các thư viện MyBatis và MyBatis-Spring cùng Spring Data JDBC. Với Gradle, cấu trúc dependency có thể như sau:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    implementation("org.mybatis:mybatis")
    implementation("org.mybatis:mybatis-spring")
}
~~~

Nếu dùng MyBatis Spring Boot starter, hãy chọn version tương thích với Spring Boot của project và để dependency management kiểm soát các version liên quan. Không trộn nhiều phiên bản MyBatis-Spring hoặc khai báo đồng thời các starter có cấu hình trùng lặp.

## 4. Vì sao cần SqlSessionTemplate?

MyBatis có thể tạo session trực tiếp từ SqlSessionFactory, nhưng Spring Data JDBC cần các thao tác MyBatis tham gia đúng transaction của Spring.

`SqlSessionTemplate` là implementation thread-safe của `SqlSession`. Nó tìm session gắn với transaction hiện tại, quản lý vòng đời session và thực hiện commit/rollback theo transaction configuration của Spring.

Không nên inject hoặc giữ một `DefaultSqlSession` tự tạo trong repository/service. Session tự mở có thể dùng connection hoặc transaction riêng, làm cho thao tác MyBatis không cùng commit/rollback với thao tác Spring Data JDBC.

Các nguyên tắc cấu hình:

- `SqlSessionTemplate` phải được tạo từ SqlSessionFactory đang dùng cho ứng dụng.
- `SqlSessionFactoryBean` phải dùng cùng DataSource với Spring transaction manager.
- Các thao tác cần atomic nên được gọi trong cùng transaction service.
- Không tự gọi commit, rollback hoặc close trên SqlSessionTemplate do Spring quản lý.

Nếu MyBatis và Spring Data JDBC dùng hai DataSource khác nhau, một transaction JDBC thông thường không tự bao phủ cả hai resource. Khi đó cần cấu hình transaction phù hợp hoặc thiết kế quy trình phân tán riêng.

## 5. Quy ước namespace và tên mapped statement

Mặc định, namespace MyBatis được tạo từ tên đầy đủ của entity class cộng hậu tố `Mapper`. Sau đó, statement ID xác định thao tác.

Ví dụ entity:

~~~java
package com.example.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String name;

    private String email;

    // constructors, getters and setters
}
~~~

Namespace tương ứng:

~~~xml
<mapper namespace="com.example.domain.CustomerMapper">
    <insert id="insert">
        ...
    </insert>
</mapper>
~~~

Với entity `com.example.domain.Customer`, Spring Data JDBC tìm statement:

~~~text
com.example.domain.CustomerMapper.insert
~~~

Một số statement ID phổ biến:

| Statement ID | Mục đích |
|---|---|
| `insert` | Insert một entity |
| `update` | Update một entity |
| `delete` | Delete entity theo ID |
| `findById` | Đọc aggregate root theo ID |
| `findAll` | Đọc tất cả aggregate root |
| `findAllById` | Đọc các aggregate theo danh sách ID |
| `findAllByPath-<propertyPath>` | Đọc entity con theo property path |
| `findAllSorted` | Đọc aggregate có sắp xếp |
| `findAllPaged` | Đọc aggregate theo phân trang |
| `count` | Đếm aggregate root |
| `delete-<propertyPath>` | Xóa entity con theo property path của aggregate |
| `deleteAll-<propertyPath>` | Xóa các entity con theo property path |
| `deleteAll` | Xóa toàn bộ aggregate root của domain type |

Không đặt namespace theo tên repository interface. Namespace mặc định dựa trên domain entity type. Nếu thay đổi naming convention, Spring Data JDBC có `NamespaceStrategy` để tùy chỉnh cách tạo namespace; hãy cấu hình nhất quán với các mapper XML.

## 6. Spring Data JDBC ủy quyền từng bước CRUD như thế nào?

Một method repository không nhất thiết tương ứng với đúng một SQL statement. Spring Data JDBC xử lý aggregate theo mapping và có thể gọi strategy nhiều lần cho root và các entity con.

Bảng sau mô tả những statement thường được tra cứu theo quy ước MyBatis:

| Statement | Repository operation có thể kích hoạt | Dữ liệu trong MyBatisContext |
|---|---|---|
| `insert` | `save`, `saveAll` | Instance cần lưu, domain type, khóa tham chiếu từ aggregate cha |
| `update` | `save`, `saveAll` | Instance cần lưu, domain type |
| `delete` | `delete`, `deleteById` | ID và domain type |
| `delete-<propertyPath>` | `deleteById` | ID aggregate root và domain type của entity con |
| `deleteAll-<propertyPath>` | `deleteAll` | Domain type của entity con |
| `deleteAll` | `deleteAll` | Domain type của aggregate root |
| `findById` | `findById` | ID và domain type |
| `findAll` | `findAll` | Domain type |
| `findAllById` | `findAllById` | Danh sách ID và domain type |
| `findAllByPath-<propertyPath>` | Các thao tác đọc quan hệ | Identifier của aggregate và đường dẫn property |
| `findAllSorted` | `findAll(Sort)` | Sort |
| `findAllPaged` | `findAll(Pageable)` | Pageable |
| `count` | `count` | Domain type |

Các tên statement và chi tiết context có thể phụ thuộc version. Bảng này thể hiện quy ước trong tài liệu tích hợp Spring Data JDBC; khi nâng cấp, hãy kiểm tra lại reference documentation và API của version đang dùng.

### 6.1. Insert và update của aggregate

Giả sử aggregate Order có collection lines. Khi lưu một Order mới, Spring Data JDBC có thể cần:

1. Insert hàng vào bảng orders.
2. Nhận ID được database tạo cho order.
3. Insert từng OrderLine với khóa ngoại order_id.
4. Nhận generated key của child nếu child có ID riêng.

Với aggregate đã tồn tại, framework có thể update root và đồng bộ các entity con theo persistence strategy của Spring Data JDBC. Mỗi entity cần thao tác sẽ được chuyển đến DataAccessStrategy tương ứng.

Vì vậy, nếu muốn MyBatis xử lý cả root lẫn child, cần định nghĩa statement insert/update cho đúng entity type và những statement xử lý property path liên quan.

### 6.2. Delete aggregate và entity con

Khi xóa một aggregate root theo ID, Spring Data JDBC có thể phải xóa các entity con theo property path trước khi xóa root, tùy mapping và chiến lược persistence.

Ví dụ aggregate:

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;
}
~~~

Nếu property path là `lines`, namespace của aggregate root có thể cần statement:

~~~xml
<delete id="delete-lines">
    DELETE FROM order_lines
    WHERE order_id = #{id}
</delete>
~~~

Statement này thuộc namespace của Order root, vì nó xóa các entity được tham chiếu bởi aggregate Order. Nó không nhất thiết thuộc namespace OrderLineMapper.

Với `deleteAll`, statement cho collection có thể dùng tên `deleteAll-lines`. Phải kiểm tra property path, tên back-reference column và thứ tự xóa phù hợp với foreign key trong schema.

## 7. MyBatisContext: object tham số của statement

Các mapped statement không nhận trực tiếp entity như một mapper method thông thường. Spring Data JDBC truyền một `MyBatisContext` để cung cấp dữ liệu cần thiết cho thao tác.

Các accessor quan trọng:

| Accessor | Ý nghĩa |
|---|---|
| `getInstance()` | Entity instance đang được insert/update; có thể null với thao tác đọc |
| `getId()` | ID của entity/aggregate được thao tác |
| `getDomainType()` | Class domain type liên quan |
| `getIdentifier()` | Identifier mô tả aggregate root và các thành phần trong property path |
| `get(key)` | Giá trị bổ sung, chẳng hạn ID của aggregate cha hoặc khóa/index của collection |

Trong mapper XML, MyBatis có thể truy cập các property JavaBean của context. Ví dụ:

~~~xml
#{instance.name}
#{instance.email}
#{instance.id}
#{id}
~~~

`instance.name` lấy property từ entity được bọc trong context. `id` là ID mà context cung cấp cho thao tác. Không nhầm hai giá trị này: khi insert entity mới, ID của context có thể chưa có, trong khi ID được database tạo sẽ được ghi vào property của instance.

Với entity con, context còn mang thông tin liên kết với aggregate cha. Tên khóa được cung cấp phụ thuộc NamingStrategy và property path. Hãy dùng đúng tên back-reference key được Spring Data JDBC cung cấp thay vì tự đoán tên cột trong mapper.

## 8. Ví dụ mapper XML cho CRUD cơ bản

Với Customer có ID tự tăng trong database, mapper XML có thể khai báo:

~~~xml
<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE mapper
        PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
        "http://mybatis.org/dtd/mybatis-3-mapper.dtd">

<mapper namespace="com.example.domain.CustomerMapper">

    <resultMap id="customerMap"
               type="com.example.domain.Customer">
        <id property="id" column="id"/>
        <result property="name" column="name"/>
        <result property="email" column="email"/>
    </resultMap>

    <insert id="insert"
            useGeneratedKeys="true"
            keyProperty="instance.id"
            keyColumn="id">
        INSERT INTO customers (name, email)
        VALUES (#{instance.name}, #{instance.email})
    </insert>

    <update id="update">
        UPDATE customers
        SET name = #{instance.name},
            email = #{instance.email}
        WHERE id = #{instance.id}
    </update>

    <delete id="delete">
        DELETE FROM customers
        WHERE id = #{id}
    </delete>

    <select id="findById" resultMap="customerMap">
        SELECT id, name, email
        FROM customers
        WHERE id = #{id}
    </select>

    <select id="findAll" resultMap="customerMap">
        SELECT id, name, email
        FROM customers
        ORDER BY id
    </select>

    <select id="findAllById" resultMap="customerMap">
        SELECT id, name, email
        FROM customers
        WHERE id IN
        <foreach collection="id"
                 item="customerId"
                 open="("
                 separator=","
                 close=")">
            #{customerId}
        </foreach>
    </select>

    <select id="count" resultType="long">
        SELECT COUNT(*)
        FROM customers
    </select>

</mapper>
~~~

Đây là ví dụ minh họa các statement cơ bản. Trong ứng dụng thật, cần điều chỉnh resultMap, kiểu ID, SQL dialect, schema và tên cột theo entity. Đặc biệt, collection hoặc entity con có thể cần mapper riêng và statement theo property path.

Spring Data JDBC sẽ gọi repository method bình thường:

~~~java
Customer saved = customerRepository.save(
        new Customer("An", "an@example.com")
);

Customer loaded = customerRepository.findById(saved.getId())
        .orElseThrow();
~~~

Service không cần gọi trực tiếp `sqlSession.insert("...")` cho thao tác CRUD được Spring Data JDBC ủy quyền. Framework tìm statement dựa trên namespace và ID theo convention.

## 9. Generated keys: database tạo ID và MyBatis trả ID về entity

Generated key là giá trị khóa chính do database sinh khi insert, thường gặp với cột identity/auto-increment hoặc sequence.

Với MyBatis, có hai cách phổ biến:

1. JDBC generated keys qua `useGeneratedKeys` và `keyProperty`.
2. Lấy khóa bằng `selectKey` trước hoặc sau câu INSERT.

Khi tích hợp Spring Data JDBC, cần nhớ parameter của mapped statement là `MyBatisContext`. Entity nằm bên trong property `instance`. Vì vậy, khi muốn MyBatis ghi khóa vừa sinh vào entity, keyProperty phải trỏ đến property lồng bên trong context.

### 9.1. JDBC generated keys với useGeneratedKeys

Ví dụ:

~~~xml
<insert id="insert"
        useGeneratedKeys="true"
        keyProperty="instance.id"
        keyColumn="id">
    INSERT INTO customers (name, email)
    VALUES (#{instance.name}, #{instance.email})
</insert>
~~~

Ý nghĩa:

- `useGeneratedKeys="true"` yêu cầu MyBatis sử dụng JDBC `getGeneratedKeys()` để lấy khóa do database tạo.
- `keyProperty="instance.id"` chỉ ra property nhận giá trị khóa trên entity được bọc trong MyBatisContext.
- `keyColumn="id"` chỉ rõ cột khóa trong database; một số database/driver cần cấu hình này.

**Vì sao là instance.id?** Parameter object của mapped statement là MyBatisContext, không phải Customer trực tiếp. Context có accessor getInstance(), vì vậy property entity nằm dưới nhánh instance. Nếu chỉ dùng `keyProperty="id"`, MyBatis sẽ cố ghi khóa vào property id của context thay vì Customer.id.

Sau khi insert, MyBatis ghi khóa vào `instance.id`. Spring Data JDBC có thể tiếp tục dùng ID đó trong các bước còn lại của aggregate, ví dụ insert các OrderLine có foreign key trỏ đến Order vừa được tạo.

Khả năng lấy generated key phụ thuộc JDBC driver và database. Hãy kiểm tra driver hỗ trợ getGeneratedKeys và cấu hình keyColumn khi hệ quản trị yêu cầu.

### 9.2. Dùng selectKey với sequence

Một số database hoặc chiến lược ID cần lấy giá trị từ sequence. Có thể dùng `selectKey` để lấy ID trước khi INSERT:

~~~xml
<insert id="insert">
    <selectKey keyProperty="instance.id"
               resultType="long"
               order="BEFORE">
        SELECT nextval('customer_id_seq')
    </selectKey>

    INSERT INTO customers (id, name, email)
    VALUES (
        #{instance.id},
        #{instance.name},
        #{instance.email}
    )
</insert>
~~~

Trong ví dụ PostgreSQL, câu SELECT lấy giá trị tiếp theo của sequence trước khi insert. MyBatis ghi giá trị vào `instance.id`, rồi câu INSERT sử dụng giá trị đó.

Với database khác, cú pháp lấy sequence khác nhau. Ví dụ Oracle có cú pháp sequence riêng. Không sao chép câu SELECT của PostgreSQL sang database khác mà không điều chỉnh.

Có thể dùng `selectKey order="AFTER"` nếu database cung cấp cách lấy identity sau insert. Hãy chọn cách lấy key phù hợp với database và bảo đảm key được gán vào đúng property.

### 9.3. Generated key không phải update count

Cần phân biệt hai kết quả:

- Insert statement thường trả số hàng được insert, ví dụ 1.
- Generated key là giá trị ID được ghi vào property mà keyProperty chỉ định.

`useGeneratedKeys` không biến giá trị trả về của insert thành ID. Nó yêu cầu MyBatis lấy khóa và gán vào entity. Spring Data JDBC cần giá trị ID đó để tiếp tục persistence và trả entity đã lưu cho caller.

### 9.4. Entity cần property có thể ghi được

MyBatis phải gán giá trị generated key vào property được chỉ định. Với POJO mutable, hãy cung cấp setter hoặc field mà MyBatis có thể truy cập theo cấu hình reflection.

Nếu dùng record hoặc immutable entity, việc ghi generated key vào nested property có thể không phù hợp với cách MyBatis tạo key. Trong trường hợp này, hãy kiểm tra khả năng mapping của version đang dùng và cân nhắc sinh ID trước insert bằng callback/sequence hoặc một chiến lược phù hợp với immutable model.

## 10. ID do ứng dụng cấp và ID do database cấp

Không phải entity nào cũng dùng auto-increment. Có thể chia thành hai trường hợp:

| Chiến lược | Cách insert |
|---|---|
| Database tự sinh ID | Không đưa ID vào danh sách cột insert; cấu hình useGeneratedKeys hoặc selectKey |
| Ứng dụng đã gán ID | Truyền ID từ instance vào câu INSERT; không cần lấy generated key |
| ID lấy từ sequence trước insert | Dùng selectKey BEFORE hoặc callback sinh ID |
| ID là UUID được ứng dụng tạo | Gán UUID trước khi save và ghi giá trị vào cột ID |

Ví dụ ID được gán trước:

~~~xml
<insert id="insert">
    INSERT INTO customers (id, name, email)
    VALUES (
        #{instance.id},
        #{instance.name},
        #{instance.email}
    )
</insert>
~~~

Trong trường hợp này, ID đã có trong entity. Không bật generated keys một cách máy móc vì database không phải nguồn tạo ID.

Cần thống nhất chiến lược ID giữa entity mapping, database schema và MyBatis statement. Nếu entity được thiết kế để database sinh ID nhưng SQL lại tự truyền null hoặc bỏ qua cơ chế key retrieval, aggregate có thể không nhận được ID sau save.

## 11. Generated keys cho entity con trong aggregate

Giả sử Order có nhiều OrderLine, và mỗi OrderLine cũng có ID riêng:

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;
}
~~~

Khi lưu một Order mới, Spring Data JDBC cần ID của root để ghi các hàng con. Trình tự khái quát:

~~~text
1. INSERT orders
2. MyBatis lấy generated key và ghi vào Order.id
3. Spring Data JDBC có ID của Order
4. INSERT order_lines với order_id tương ứng
5. Nếu OrderLine có ID riêng, MyBatis lấy key và gán vào OrderLine.id
~~~

Statement insert của OrderLine thuộc namespace của entity OrderLine. Statement cần dùng giá trị instance cho các property của child và giá trị tham chiếu cha mà MyBatisContext cung cấp.

Nếu child cũng dùng auto-increment, mapper child cần cấu hình generated key riêng:

~~~xml
<insert id="insert"
        useGeneratedKeys="true"
        keyProperty="instance.id"
        keyColumn="id">
    INSERT INTO order_lines (order_id, sku, quantity)
    VALUES (
        #{orderId},
        #{instance.sku},
        #{instance.quantity}
    )
</insert>
~~~

Trong ví dụ, `orderId` đại diện cho khóa back-reference được context cung cấp. Tên khóa thực tế phụ thuộc NamingStrategy và mapping của ứng dụng; hãy xác định đúng key được cung cấp trong MyBatisContext thay vì giả định luôn là orderId.

Nếu root ID chưa được lấy hoặc không được ghi lại vào entity, insert child có thể thất bại do foreign key NULL hoặc trỏ sai parent. Vì vậy, kiểm thử generated key trên cả root lẫn child nếu aggregate có nhiều cấp.

## 12. Update, delete và optimistic locking

Đối với update, MyBatis statement nhận entity qua `instance`. Câu SQL cần sử dụng ID hiện tại để xác định hàng:

~~~xml
<update id="update">
    UPDATE customers
    SET name = #{instance.name},
        email = #{instance.email}
    WHERE id = #{instance.id}
</update>
~~~

Nếu entity sử dụng `@Version`, SQL update tùy chỉnh cần giữ đúng semantics optimistic locking: so sánh version cũ trong WHERE và tăng version khi update thành công. API `DataAccessStrategy.updateWithVersion(...)` nhận riêng giá trị `previousVersion`; MyBatisDataAccessStrategy cũng triển khai thao tác này và có contract ném optimistic locking exception nếu không cập nhật được hàng.

Không mặc định rằng `instance.version` luôn là giá trị version cũ mà statement cần so sánh. Cách Spring Data JDBC truyền `previousVersion` vào MyBatisContext và statement mapping phụ thuộc version API đang sử dụng. Hãy kiểm tra MyBatisContext/implementation của đúng version, dùng giá trị previous version được truyền cho operation, rồi bảo đảm SQL cập nhật version theo contract. Nếu statement bỏ qua điều kiện version hoặc không báo xung đột khi không có hàng nào được cập nhật, optimistic locking sẽ không còn bảo vệ dữ liệu.

Delete root:

~~~xml
<delete id="delete">
    DELETE FROM customers
    WHERE id = #{id}
</delete>
~~~

Delete entity con theo property path cần statement riêng trong namespace của aggregate root, như `delete-lines`. Câu DELETE root không tự thay thế các bước xóa child nếu mapping yêu cầu framework xử lý chúng.

## 13. Partial delegation và fallback strategy

Một ứng dụng không nhất thiết phải viết mapper cho mọi thao tác. Cấu hình tích hợp của Spring Data JDBC có thể kiểm tra mapped statement cho từng bước. Khi có statement tương ứng, MyBatis thực thi statement đó. Khi không có, strategy mặc định có thể xử lý bước còn lại nếu ứng dụng đang dùng combined access strategy.

API `MyBatisDataAccessStrategy.createCombinedAccessStrategy(...)` được cung cấp để tạo strategy kết hợp MyBatis và `DefaultDataAccessStrategy`. Điều này hữu ích khi chỉ muốn ủy quyền các truy vấn phức tạp cho MyBatis nhưng vẫn để Spring Data JDBC tự sinh SQL cho CRUD đơn giản.

Cần phân biệt hai cách khởi tạo:

- Dùng cấu hình tích hợp `MyBatisJdbcConfiguration` theo hướng dẫn của Spring Data JDBC.
- Tự tạo `new MyBatisDataAccessStrategy(sqlSession)`.

Javadoc của `MyBatisDataAccessStrategy` lưu ý instance được tạo trực tiếp theo constructor chỉ xử lý MyBatis và không chứa chức năng của `DefaultDataAccessStrategy`. Nếu tự cấu hình và cần fallback, hãy dùng API combined strategy phù hợp với version.

Đừng giả định mọi thao tác đều fallback nếu bạn đã tự thay thế DataAccessStrategy bằng một implementation MyBatis-only. Kiểm tra cấu hình bean và test những statement không có mapper XML.

## 14. Query mapping và resultMap

Với thao tác đọc, MyBatis chịu trách nhiệm ánh xạ result set về entity. Dùng `resultMap` khi tên cột khác tên property hoặc cần mapping rõ ràng.

Ví dụ:

~~~xml
<resultMap id="orderMap" type="com.example.domain.Order">
    <id property="id" column="order_id"/>
    <result property="status" column="order_status"/>
</resultMap>

<select id="findById" resultMap="orderMap">
    SELECT
        order_id,
        order_status
    FROM orders
    WHERE order_id = #{id}
</select>
~~~

Nếu query cần dựng cả aggregate root và các collection con, resultMap có thể cần association/collection hoặc Spring Data JDBC có thể gọi statement tìm entity theo property path. Hãy chọn một chiến lược mapping nhất quán để không bỏ sót child rows hoặc tạo dữ liệu trùng khi join.

Với collection lớn hoặc quan hệ phức tạp, tránh giả định một SELECT root đơn giản sẽ tự điền mọi property. Kiểm tra statement cho findAllByPath và các quy ước đọc quan hệ của phiên bản Spring Data JDBC.

## 15. Transaction khi trộn MyBatis và Spring Data JDBC

Một use case có thể thực hiện một phần bằng MyBatis và một phần bằng DefaultDataAccessStrategy. Để các thao tác này cùng commit/rollback, chúng phải dùng cùng transaction resource phù hợp.

Ví dụ:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository customers;
    private final AuditRepository audit;

    public CustomerService(
            CustomerRepository customers,
            AuditRepository audit
    ) {
        this.customers = customers;
        this.audit = audit;
    }

    @Transactional
    public Customer register(Customer customer) {
        Customer saved = customers.save(customer);
        audit.recordCreated(saved.getId());
        return saved;
    }
}
~~~

Nếu MyBatis và Spring Data JDBC dùng chung DataSource và transaction manager, thao tác MyBatis qua SqlSessionTemplate có thể tham gia transaction do service mở.

Những điểm cần nhớ:

- SqlSessionTemplate phải được tạo từ SqlSessionFactory dùng cùng DataSource.
- Transaction manager phải quản lý chính DataSource đó.
- Không mở raw SqlSession riêng bên trong use case.
- Không tự commit hoặc rollback SqlSessionTemplate.
- Nếu có nhiều DataSource, phải chỉ rõ transaction manager và resource cho từng vùng persistence.
- Không mặc định hai transaction manager khác nhau sẽ tạo một transaction phân tán.

Nếu một thao tác MyBatis thất bại giữa khi lưu root và child, transaction cần rollback toàn bộ thay đổi liên quan. Đây là lý do cần kiểm thử transaction trên cấu hình thật.

## 16. Kiểm thử CRUD delegation và generated keys

Kiểm thử nên đi qua repository Spring Data JDBC thay vì chỉ gọi MyBatis statement trực tiếp. Mục tiêu là xác nhận Spring Data JDBC tìm đúng statement, truyền đúng MyBatisContext, nhận lại generated key và tiếp tục xử lý aggregate.

Ví dụ integration test:

~~~java
@DataJdbcTest
@Import(JdbcPersistenceConfiguration.class)
class CustomerMyBatisIntegrationTest {

    @Autowired
    CustomerRepository customers;

    @Test
    void insertsCustomerAndReceivesGeneratedId() {
        Customer saved = customers.save(
                new Customer("An", "an@example.com")
        );

        assertThat(saved.getId()).isNotNull();

        Customer loaded = customers.findById(saved.getId())
                .orElseThrow();

        assertThat(loaded.getName()).isEqualTo("An");
        assertThat(loaded.getEmail()).isEqualTo("an@example.com");
    }
}
~~~

Đây là skeleton minh họa; cấu hình test, entity constructor và repository phải khớp ứng dụng. Nếu dùng Spring Boot integration test thay vì DataJdbcTest, hãy bảo đảm mapper XML được nạp và transaction manager dùng đúng DataSource.

Các kịch bản nên kiểm tra:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Insert root có generated ID | Customer.id được điền sau save |
| Insert root có ID gán sẵn | SQL ghi đúng ID đã có |
| Insert aggregate có child | Parent ID được truyền tới child insert |
| Child có generated ID | Child ID được điền đúng |
| Update | Mapper dùng đúng instance và ID |
| Update entity có version | Version predicate và conflict hoạt động |
| Delete root | Statement delete đúng namespace |
| Delete root có child | Statement property path được gọi đúng |
| Read by ID | ResultMap trả entity đúng |
| Statement không có mapper | Fallback hoạt động nếu dùng combined strategy |
| Transaction rollback | MyBatis và Spring Data JDBC cùng rollback |
| Generated key theo database thật | JDBC driver trả đúng key theo cấu hình |

H2 hữu ích cho test nhanh, nhưng generated keys và SQL dialect có thể khác database production. Với hành vi phụ thuộc driver, hãy dùng Testcontainers hoặc database kiểm thử cùng hệ quản trị.

## 17. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy mapped statement | Namespace hoặc statement ID sai | Dùng FQCN entity cộng Mapper và tên operation đúng |
| Repository chạy SQL mặc định thay vì MyBatis | Mapper XML chưa được nạp hoặc statement chưa tồn tại | Kiểm tra mapperLocations và resource path |
| BindingException cho statement | Namespace không khớp entity type | Kiểm tra tên package và class |
| MyBatis không nhận được entity property | Quên wrapper MyBatisContext | Dùng instance.property cho dữ liệu entity |
| Generated ID vẫn NULL | Chưa bật useGeneratedKeys hoặc driver không hỗ trợ | Kiểm tra driver và cấu hình key generation |
| Generated ID không được gán vào entity | keyProperty trỏ sai property | Với entity nằm trong MyBatisContext, dùng instance.id |
| Insert thành công nhưng child insert lỗi | Parent ID chưa được lấy hoặc back-reference key sai | Kiểm tra generated key và MyBatisContext.get(key) |
| PostgreSQL không trả đúng key | Thiếu keyColumn hoặc cấu hình generated key không phù hợp | Khai báo cột khóa và kiểm thử driver |
| Sequence insert lỗi | Cú pháp selectKey không đúng database | Dùng sequence expression phù hợp dialect |
| Update không thay đổi hàng | WHERE dùng sai ID hoặc property path | Kiểm tra instance.id và SQL log |
| Optimistic locking không hoạt động | Mapper update bỏ qua version | Bổ sung version predicate/increment theo contract |
| Delete root bị foreign key từ chối | Chưa có statement xóa child path | Khai báo delete-propertyPath hoặc dùng FK cascade có chủ đích |
| Một số CRUD chạy, một số lỗi | Chỉ có một phần mapped statement và fallback không được cấu hình | Kiểm tra combined strategy |
| Thao tác MyBatis không rollback cùng repository | SqlSessionTemplate/DataSource/transaction manager không đồng nhất | Dùng cùng DataSource và Spring transaction |
| Test pass nhưng production key sai | Driver/database khác với môi trường test | Kiểm thử bằng database mục tiêu |

## 18. Quy trình triển khai

1. Xác định các aggregate và CRUD step muốn ủy quyền cho MyBatis.
2. Chọn phiên bản Spring Data JDBC, MyBatis và MyBatis-Spring tương thích.
3. Cấu hình SqlSessionFactory từ DataSource của ứng dụng.
4. Cung cấp SqlSessionTemplate để MyBatis tham gia Spring transaction.
5. Import MyBatisJdbcConfiguration và bật repository scanning.
6. Xác định namespace mặc định theo FQCN entity cộng Mapper.
7. Viết statement cho insert, update, delete và các thao tác đọc cần thiết.
8. Với entity con, khai báo statement theo namespace và property path đúng.
9. Cấu hình useGeneratedKeys/keyProperty hoặc selectKey cho từng loại ID.
10. Kiểm thử generated key được ghi vào instance.id và parent key được truyền cho child.
11. Kiểm thử update, delete, resultMap, transaction và fallback strategy.
12. Chạy integration test trên database/driver gần production.

## 19. Bài tập thực hành

### Bài 1 — Cấu hình MyBatis

Tạo cấu hình Spring Data JDBC có MyBatisJdbcConfiguration, SqlSessionFactory và SqlSessionTemplate. Xác nhận repository khởi động được và mapper XML được nạp.

### Bài 2 — Namespace convention

Tạo Customer entity trong package com.example.domain. Viết mapper XML với namespace com.example.domain.CustomerMapper và statement findById. Gọi CustomerRepository.findById để xác nhận statement được ủy quyền.

### Bài 3 — Insert và generated keys

Viết statement insert có useGeneratedKeys=true và keyProperty=instance.id. Gọi save với entity chưa có ID và kiểm tra entity trả về đã có ID.

### Bài 4 — Sequence với selectKey

Chuyển bảng sang dùng sequence. Dùng selectKey BEFORE để lấy ID, gán vào instance.id và dùng ID đó trong INSERT.

### Bài 5 — Aggregate có child collection

Tạo Order có List<OrderLine>. Viết insert statement cho root và child. Xác nhận ID của root được chuyển thành khóa ngoại order_id của child.

### Bài 6 — Update và optimistic locking

Viết update statement cho entity có @Version. Kiểm tra update bình thường và hai transaction cùng sửa một version. Xác nhận xung đột được phát hiện theo contract.

### Bài 7 — Delete theo property path

Viết delete-lines và deleteAll-lines cho aggregate Order. Kiểm tra deleteById và deleteAll với dữ liệu có child.

### Bài 8 — Partial delegation

Chỉ cung cấp mapper cho findById và insert, sau đó kiểm tra các thao tác khác có được xử lý bằng DefaultDataAccessStrategy hay không trong cấu hình combined strategy.

### Bài 9 — Transaction rollback

Trong một service transactional, lưu root qua MyBatis rồi gây lỗi ở thao tác persistence tiếp theo. Xác nhận mọi thay đổi trong cùng DataSource được rollback.

### Bài 10 — Database thật

Chạy bài generated keys trên database mục tiêu bằng Testcontainers. So sánh kết quả với H2 và ghi lại khác biệt driver nếu có.

## 20. Ghi nhớ

- Spring Data JDBC điều phối aggregate; MyBatis có thể thực thi SQL cho từng bước DataAccessStrategy.
- Repository API vẫn là CrudRepository/JdbcAggregateOperations; service không cần gọi mapper trực tiếp cho các thao tác đã được ủy quyền.
- Namespace mặc định là tên đầy đủ của entity cộng hậu tố Mapper; statement ID biểu thị operation như insert, update, delete hoặc findById.
- MyBatisContext bọc entity và cung cấp instance, id, domainType, identifier cùng các giá trị tham chiếu bổ sung.
- Một lần save aggregate có thể kích hoạt nhiều statement cho root và child; không giả định một repository method tương ứng một câu SQL.
- Khi dùng generated keys, MyBatis cần ghi khóa vào property của entity được bọc; với context này, keyProperty thường là instance.id.
- useGeneratedKeys dùng JDBC getGeneratedKeys; selectKey phù hợp với sequence hoặc chiến lược lấy ID riêng của database.
- Generated key khác update count: insert trả số hàng bị tác động, còn keyProperty nhận ID được database tạo.
- Entity con cần nhận parent key từ MyBatisContext và có statement xử lý đúng property path.
- Dùng SqlSessionTemplate cùng DataSource và transaction manager với Spring Data JDBC để các thao tác commit/rollback nhất quán.
- Nếu tự tạo MyBatisDataAccessStrategy, hãy hiểu nó chỉ xử lý MyBatis; dùng combined strategy nếu cần fallback sang DefaultDataAccessStrategy.
- Kiểm thử bằng repository thật, xác nhận generated ID, child mapping, transaction và JDBC driver trên database mục tiêu.

## Tài liệu tham khảo

- [Spring Data JDBC Reference — MyBatis Integration](https://docs.spring.io/spring-data/jdbc/docs/current-SNAPSHOT/reference/html/)
- [MyBatisDataAccessStrategy API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/jdbc/mybatis/MyBatisDataAccessStrategy.html)
- [MyBatisContext API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/jdbc/mybatis/MyBatisContext.html)
- [MyBatisJdbcConfiguration API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/MyBatisJdbcConfiguration.html)
- [MyBatis Mapper XML — Insert, Update, Delete and Generated Keys](https://mybatis.org/mybatis-3/sqlmap-xml.html)
- [MyBatis-Spring — SqlSessionTemplate](https://mybatis.org/spring/sqlsession.html)
- [MyBatis-Spring — Transactions](https://mybatis.org/spring/transactions.html)
