# Quy ước namespace, statement và MyBatisContext

Trong **Spring Data Relational JDBC**, MyBatis có thể thay thế phần thực thi SQL mặc định của Spring Data JDBC cho các thao tác persistence. Điều này hữu ích khi ứng dụng cần kiểm soát câu SQL, cách lấy khóa được sinh, mapping kết quả hoặc cách truy vấn các bảng child trong một aggregate.

Để Spring Data JDBC tìm đúng câu lệnh MyBatis, mapper phải tuân theo một quy ước tên cụ thể. **Namespace được suy ra từ kiểu entity, statement ID được đặt theo tên thao tác, còn `MyBatisContext` là đối tượng tham số mà Spring Data JDBC truyền vào mapped statement.** Nếu namespace hoặc statement ID sai, Spring Data JDBC không tìm thấy câu lệnh tùy chỉnh và có thể dùng chiến lược SQL mặc định thay thế.

Bài học trình bày cách đặt namespace, danh sách statement được Spring Data JDBC tìm kiếm, dữ liệu có trong `MyBatisContext`, cách cấu hình mapper XML và cách kiểm thử hợp đồng giữa repository, aggregate mapping và MyBatis.

## 1. MyBatis tích hợp với Spring Data JDBC ở đâu?

Spring Data JDBC dùng `DataAccessStrategy` để thực hiện các thao tác đọc/ghi trên từng entity trong aggregate. Mặc định, `DefaultDataAccessStrategy` sinh SQL từ mapping metadata của Spring Data Relational.

Khi tích hợp MyBatis, `MyBatisDataAccessStrategy` có thể nhận trách nhiệm thực thi một số statement. Spring Data JDBC tra cứu mapped statement trong `SqlSessionFactory`. Nếu tìm thấy statement có đúng tên, statement MyBatis đó được dùng cùng mapping kết quả mà MyBatis đã cấu hình. Nếu không tìm thấy, chiến lược kết hợp có thể tiếp tục dùng `DefaultDataAccessStrategy`.

Luồng khái quát:

~~~text
CrudRepository / JdbcAggregateTemplate
                |
                v
        Spring Data JDBC
                |
                v
        DataAccessStrategy
                |
                v
     Tìm mapped statement trong MyBatis
                |
         +------+------+
         |             |
      Có statement   Không có
         |             |
         v             v
      MyBatis SQL   DefaultDataAccessStrategy
         |             |
         +------+------+
                |
                v
             Database
~~~

Điều này cho phép tùy chỉnh từng bước. Ví dụ, ứng dụng có thể để Spring Data JDBC xử lý `insert` và `update` theo mặc định nhưng cung cấp statement MyBatis riêng cho `findById`. Khi statement tùy chỉnh tồn tại, nó chịu trách nhiệm cho SQL và mapping của thao tác đó.

### 1.1. MyBatis mapper convention không phải mọi mapper method tùy ý

Các tên statement trong bài này là hợp đồng giữa `MyBatisDataAccessStrategy` và các thao tác persistence của Spring Data JDBC. Chúng không tự động ánh xạ mọi method tùy ý được khai báo trong repository interface hoặc mọi method trong một MyBatis mapper interface.

Nếu ứng dụng cần một query nghiệp vụ riêng, chẳng hạn `findOrdersForDashboard`, có thể dùng MyBatis mapper interface/statement riêng và gọi nó từ custom repository fragment hoặc service. Còn để thay thế thao tác `CrudRepository.save`, `findById`, `deleteById`..., phải tuân theo statement ID mà Spring Data JDBC tìm kiếm.

## 2. Quy ước namespace mặc định

Theo mặc định, namespace MyBatis được tạo từ **tên lớp entity đầy đủ (fully qualified class name) cộng hậu tố `Mapper`**.

Ví dụ entity:

~~~java
package com.example.orders;

public class PurchaseOrder {
    // ...
}
~~~

Namespace mặc định:

~~~text
com.example.orders.PurchaseOrderMapper
~~~

Statement `findById` trong namespace đó có tên đầy đủ:

~~~text
com.example.orders.PurchaseOrderMapper.findById
~~~

Trong mapper XML:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <select id="findById" resultMap="purchaseOrderMap">
        SELECT id, order_number, status
        FROM purchase_order
        WHERE id = #{id}
    </select>
</mapper>
~~~

MyBatis ghép `namespace` với `id` để tạo statement key. Vì vậy, namespace và statement ID phải khớp chính xác với quy ước Spring Data JDBC.

### 2.1. Dùng fully qualified class name

Namespace mặc định có cả package:

| Entity class | Namespace |
| --- | --- |
| `com.example.orders.PurchaseOrder` | `com.example.orders.PurchaseOrderMapper` |
| `com.example.catalog.Product` | `com.example.catalog.ProductMapper` |
| `com.example.customer.Customer` | `com.example.customer.CustomerMapper` |

Không rút gọn namespace thành `PurchaseOrderMapper` nếu ứng dụng đang dùng strategy mặc định. Hai entity ở package khác nhau có thể cùng tên lớp; fully qualified name giúp phân biệt chúng.

### 2.2. Namespace của entity child

Với thao tác `insert` hoặc `update` trên một entity child thuộc aggregate, namespace mặc định dựa trên kiểu của entity đang được xử lý. Ví dụ:

~~~java
package com.example.orders;

public class OrderLine {
    // ...
}
~~~

Namespace của entity child:

~~~text
com.example.orders.OrderLineMapper
~~~

Vì vậy, có thể có:

- `PurchaseOrderMapper.insert` cho root `PurchaseOrder`.
- `OrderLineMapper.insert` cho entity child `OrderLine`.

Các thao tác theo property path là trường hợp khác: statement prefix dùng kiểu của aggregate root, sau đó thêm path cần xử lý. Phần sau sẽ trình bày rõ quy tắc này.

### 2.3. NamespaceStrategy

Spring Data JDBC có `NamespaceStrategy` để xác định namespace từ domain type. `NamespaceStrategy.DEFAULT_INSTANCE` dùng quy tắc lớp entity cộng hậu tố `Mapper`.

Trong những cấu hình nâng cao, `MyBatisDataAccessStrategy` hỗ trợ thiết lập một `NamespaceStrategy` khác. Nếu thay đổi quy tắc namespace, toàn bộ mapper XML phải dùng đúng tên namespace mới. Đây là cấu hình phụ thuộc phiên bản Spring Data Relational; hãy kiểm tra API của release đang dùng trước khi tùy chỉnh.

Không nên đổi namespace strategy chỉ để rút ngắn XML nếu không có nhu cầu rõ ràng. Quy ước mặc định dễ suy ra, dễ tìm kiếm và nhất quán giữa các module.

## 3. Quy ước statement ID

Statement ID là phần sau dấu chấm trong tên đầy đủ của mapped statement. Với namespace `com.example.orders.PurchaseOrderMapper`, Spring Data JDBC tìm các ID như:

~~~text
insert
update
delete
deleteAll
findById
findAll
findAllById
findAllByPath-lines
findAllSorted
findAllPaged
count
~~~

Các thao tác có property path dùng hậu tố thể hiện đường dẫn trong aggregate, ví dụ `delete-lines` hoặc `findAllByPath-lines`.

### 3.1. Bảng statement convention

Bảng dưới đây mô tả các statement được Spring Data JDBC sử dụng trong MyBatis integration. Một thao tác repository có thể kích hoạt nhiều statement vì việc đọc/ghi aggregate có thể bao gồm root và các entity được tham chiếu.

| Statement ID | Mục đích | Repository operation có thể kích hoạt |
| --- | --- | --- |
| `insert` | Insert một entity; áp dụng cho root và entity được root tham chiếu | `save`, `saveAll` |
| `update` | Update một entity; áp dụng cho root và entity được root tham chiếu | `save`, `saveAll` |
| `delete` | Xóa một entity theo ID | `delete`, `deleteById` |
| `deleteAll` | Xóa tất cả aggregate root của kiểu dùng làm namespace prefix | `deleteAll` |
| `delete-<propertyPath>` | Xóa các entity được root tham chiếu qua property path cho một root ID | `deleteById` |
| `deleteAll-<propertyPath>` | Xóa các entity được tham chiếu qua property path từ mọi aggregate root | `deleteAll` |
| `findById` | Đọc một aggregate root theo ID | `findById` |
| `findAll` | Đọc tất cả aggregate root | `findAll` |
| `findAllById` | Đọc các aggregate root theo danh sách ID | `findAllById` |
| `findAllByPath-<propertyPath>` | Đọc entity được tham chiếu qua property path | Các thao tác `find*` khi cần resolve relation |
| `findAllSorted` | Đọc aggregate root có sắp xếp | `findAll(Sort)` |
| `findAllPaged` | Đọc một trang aggregate root, có thể kèm sort | `findAll(Pageable)` |
| `count` | Đếm aggregate root của kiểu dùng làm namespace prefix | `count` |

`findAllByProperty-<propertyName>` là quy ước cũ đã deprecated. Với mapper mới, dùng `findAllByPath-<propertyPath>`.

### 3.2. Tên property path trong statement ID

Giả sử aggregate root:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(idColumn = "purchase_order_id")
    private Set<OrderLine> lines;
}
~~~

Property path từ root đến child là `lines`. Một số statement tương ứng:

~~~text
com.example.orders.PurchaseOrderMapper.delete-lines
com.example.orders.PurchaseOrderMapper.deleteAll-lines
com.example.orders.PurchaseOrderMapper.findAllByPath-lines
~~~

Điểm cần nhớ: namespace prefix trong các statement path này là kiểu aggregate root `PurchaseOrder`, không phải kiểu child `OrderLine`. Với thao tác insert/update riêng trên entity child, namespace lại dựa trên kiểu child.

Property path là đường dẫn trong object mapping, không phải tên bảng SQL hoặc tên cột foreign key. Nếu đường dẫn lồng nhau, hãy dùng đúng cách biểu diễn property path mà phiên bản Spring Data Relational yêu cầu và xác nhận statement key thực tế trong integration test.

## 4. MyBatisContext là gì?

Khi Spring Data JDBC gọi mapped statement, nó truyền một đối tượng `org.springframework.data.jdbc.mybatis.MyBatisContext` làm parameter object. MyBatisContext cung cấp dữ liệu về entity và thao tác hiện tại để mapper không cần nhận một tham số đơn giản như ID hoặc entity trực tiếp.

Các accessor quan trọng:

| Accessor | Ý nghĩa | Khi thường cần |
| --- | --- | --- |
| `getInstance()` | Entity instance đang được xử lý | Insert/update |
| `getId()` | ID của entity hoặc root cần xử lý | Find/delete; `findAllById` có thể nhận danh sách ID |
| `getDomainType()` | Class của entity/domain type hiện tại | Khi cần phân biệt kiểu dữ liệu |
| `get(key)` | Giá trị bổ sung theo key, thường là ID của entity cha | Insert entity child có back-reference |
| `getIdentifier()` | `Identifier` gồm root ID và các phần key/index của property path | Resolve collection hoặc relation theo path |

Các giá trị có thể null tùy loại statement. Không giả định mọi accessor đều có giá trị trong mọi thao tác. Ví dụ `getInstance()` là null đối với query vì entity chưa tồn tại trước khi truy vấn.

### 4.1. instance: dữ liệu entity đang được lưu

Với `insert` và `update`, `getInstance()` trả entity được lưu. MyBatis có thể truy cập getter/property của entity qua `instance` trong parameter expression.

Ví dụ entity:

~~~java
public class PurchaseOrder {
    private Long id;
    private String orderNumber;
    private String status;

    // getters/setters
}
~~~

Các property có thể được tham chiếu trong XML:

~~~xml
#{instance.id}
#{instance.orderNumber}
#{instance.status}
~~~

Không nhầm `instance` với một object có cấu trúc tùy ý do client truyền vào. Đây là entity instance Spring Data JDBC đang xử lý trong thao tác persistence.

### 4.2. id: định danh entity cần đọc hoặc xóa

Với `findById`:

~~~xml
<select id="findById" resultMap="purchaseOrderMap">
    SELECT id, order_number, status
    FROM purchase_order
    WHERE id = #{id}
</select>
~~~

Với `delete`:

~~~xml
<delete id="delete">
    DELETE FROM purchase_order
    WHERE id = #{id}
</delete>
~~~

Đối với `findAllById`, `getId()` có thể là danh sách ID thay vì một giá trị đơn. Mapper cần xử lý collection theo cú pháp MyBatis, chẳng hạn `<foreach>`, thay vì luôn giả định ID là scalar.

Ví dụ minh họa:

~~~xml
<select id="findAllById" resultMap="purchaseOrderMap">
    SELECT id, order_number, status
    FROM purchase_order
    WHERE id IN
    <foreach collection="id" item="orderId"
             open="(" separator="," close=")">
        #{orderId}
    </foreach>
</select>
~~~

Tên property `id` ở đây là accessor của MyBatisContext. Kiểm tra parameter binding của phiên bản MyBatis đang dùng nếu thay đổi cách cấu hình mapper.

### 4.3. domainType: kiểu entity đang được thao tác

`getDomainType()` trả class của entity. Nó hữu ích khi statement cần biết kiểu domain đang được xử lý, nhất là khi cùng một cấu trúc SQL phục vụ nhiều kiểu entity.

Trong mapper XML, getter có thể được truy cập như property `domainType`. Tuy nhiên, SQL thông thường nên dựa trên namespace/statement đã phân loại sẵn thay vì cố dùng tên class để ghép tên bảng động.

Không dùng `domainType.name` để tạo SQL identifier. Tên bảng nên được xác định bởi mapper có kiểm soát hoặc mapping cụ thể.

### 4.4. get(key): ID của entity cha

Khi insert entity child, Spring Data JDBC cần truyền ID của aggregate root để ghi foreign key vào hàng child. Giá trị này có thể được lấy bằng `get(key)`, trong đó key là tên back-reference column do `NamingStrategy` cung cấp.

Ví dụ root khai báo:

~~~java
@MappedCollection(idColumn = "purchase_order_id")
private Set<OrderLine> lines;
~~~

Với child `OrderLine`, statement insert có thể dùng:

~~~xml
<mapper namespace="com.example.orders.OrderLineMapper">
    <insert id="insert">
        INSERT INTO order_line (
            purchase_order_id,
            product_code,
            quantity,
            unit_price
        )
        VALUES (
            #{get('purchase_order_id')},
            #{instance.productCode},
            #{instance.quantity},
            #{instance.unitPrice}
        )
    </insert>
</mapper>
~~~

Trong ví dụ này, `purchase_order_id` là tên cột back-reference đã khai báo. Nếu dùng naming strategy mặc định hoặc `@MappedCollection` khác, key cần dùng cũng có thể khác. Hãy kiểm tra tên cột thật trong schema và metadata mapping, không đoán từ tên property Java.

`get(key)` được thiết kế để truyền ID của parent entity. Không dùng nó như một map tùy ý cho mọi request parameter.

### 4.5. identifier: đường dẫn và khóa của relation

Khi Spring Data JDBC tải entity qua một property path, chỉ một ID đơn có thể không đủ. Ví dụ root có một `Map` hoặc `List`, path có thể cần:

- ID của aggregate root.
- Khóa của từng phần tử trong `Map`.
- Chỉ số phần tử của `List`.
- Các thành phần khóa của những path lồng nhau.

`getIdentifier()` cung cấp một `Identifier` chứa các phần đó. Nó khác `getId()` ở chỗ biểu diễn định danh tổng hợp theo path, không chỉ một ID root.

Trong statement `findAllByPath-<propertyPath>`, `MyBatisContext` có `Identifier` này và `domainType` tương ứng với kiểu entity ở cuối path. Khi viết SQL cho path phức tạp, cần map đủ các thành phần ID/key/index theo `Identifier`; không thay toàn bộ bằng một điều kiện `WHERE parent_id = #{id}` nếu path còn có key hoặc index.

`Identifier` là API của Spring Data JDBC; cấu trúc và tên SQL identifier chịu ảnh hưởng mapping. Hãy xác nhận cách trích xuất từng phần trong phiên bản cụ thể thay vì hard-code giả định về thứ tự.

### 4.6. Sort và Pageable

Các statement `findAllSorted` và `findAllPaged` nhận thông tin sắp xếp hoặc phân trang từ thao tác repository tương ứng:

- `findAll(Sort)` cung cấp sort specification.
- `findAll(Pageable)` cung cấp pageable specification.

MyBatisContext cung cấp các giá trị tương ứng cho statement. Mapper phải chuyển chúng thành `ORDER BY`, `LIMIT/OFFSET` hoặc cú pháp tương ứng với database.

Không nối trực tiếp chuỗi sort do người dùng gửi vào SQL. Chỉ cho phép các thuộc tính sort đã được whitelist và dùng cú pháp database phù hợp.

## 5. Cấu hình MyBatisJdbcConfiguration

Cách tích hợp thông dụng là import `MyBatisJdbcConfiguration` vào cấu hình Spring Data JDBC và cung cấp `SqlSessionFactoryBean`.

~~~java
import javax.sql.DataSource;

import org.mybatis.spring.SqlSessionFactoryBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;
import org.springframework.data.jdbc.repository.config.MyBatisJdbcConfiguration;

@Configuration
@EnableJdbcRepositories
@Import(MyBatisJdbcConfiguration.class)
public class JdbcConfiguration {

    @Bean
    SqlSessionFactoryBean sqlSessionFactoryBean(DataSource dataSource)
            throws Exception {
        SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
        factory.setDataSource(dataSource);
        factory.setMapperLocations(
                new PathMatchingResourcePatternResolver()
                        .getResources("classpath*:mybatis/**/*.xml")
        );
        return factory;
    }
}
~~~

Đây là cấu hình minh họa cho ứng dụng dùng Spring Data JDBC và MyBatis-Spring. `MyBatisJdbcConfiguration` dựa vào `SqlSession` có trong application context; `SqlSessionFactoryBean` tạo `SqlSessionFactory` từ cấu hình MyBatis.

Trong ứng dụng Spring Boot, MyBatis starter có thể tự cấu hình `SqlSessionFactory` và `SqlSessionTemplate`. Khi đó cần kiểm tra bean nào đã được auto-configure và tránh khai báo trùng. Điều bắt buộc là Spring Data JDBC nhìn thấy đúng `SqlSession`/`SqlSessionFactory` và mapper XML đã được nạp.

### 5.1. Dùng cùng DataSource

Spring Data JDBC và MyBatis thường cần dùng cùng `DataSource` để tham gia cùng transaction. Nếu MyBatis kết nối sang datasource khác, một lần lưu aggregate có thể bị chia thành hai transaction độc lập.

Hãy kiểm tra:

- `SqlSessionFactoryBean` nhận đúng datasource.
- `SqlSessionTemplate` dùng đúng `SqlSessionFactory`.
- Spring transaction manager quản lý datasource tương ứng.
- MyBatis-Spring quản lý session theo transaction, không tự mở session độc lập cho từng câu lệnh.

### 5.2. Đặt mapper XML ở vị trí rõ ràng

Ví dụ:

~~~text
src/main/resources/
  mybatis/
    orders/
      PurchaseOrderMapper.xml
      OrderLineMapper.xml
    catalog/
      ProductMapper.xml
      CategoryMapper.xml
~~~

Tên file không quyết định statement namespace; thuộc tính `namespace` bên trong `<mapper>` mới là khóa quan trọng. Dù tên file có hậu tố `Mapper.xml`, namespace vẫn phải khớp `NamespaceStrategy`.

### 5.3. Mapper XML có thể chứa nhiều statement

Một mapper XML có thể khai báo nhiều statement trong cùng namespace:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <resultMap id="purchaseOrderMap" type="com.example.orders.PurchaseOrder">
        <!-- column/property mapping -->
    </resultMap>

    <insert id="insert">
        <!-- SQL insert -->
    </insert>

    <update id="update">
        <!-- SQL update -->
    </update>

    <select id="findById" resultMap="purchaseOrderMap">
        <!-- SQL select -->
    </select>

    <select id="findAll" resultMap="purchaseOrderMap">
        <!-- SQL select -->
    </select>
</mapper>
~~~

Không khai báo hai statement trùng ID trong cùng namespace. MyBatis không thể phân biệt hai mapped statement có cùng tên đầy đủ.

## 6. Ví dụ end-to-end: PurchaseOrder và OrderLine

Giả sử ứng dụng có aggregate:

~~~text
PurchaseOrder
  id
  orderNumber
  status
  lines: Set<OrderLine>

OrderLine
  productCode
  quantity
  unitPrice
~~~

Schema:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL
);

CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(19, 2) NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_order(id)
);
~~~

Mapping:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;
    private String status;

    @MappedCollection(idColumn = "purchase_order_id")
    private Set<OrderLine> lines;
}
~~~

~~~java
@Table("order_line")
public class OrderLine {

    @Id
    private Long id;

    private String productCode;
    private Integer quantity;
    private BigDecimal unitPrice;
}
~~~

### 6.1. Insert root

Mapper:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <insert id="insert"
            useGeneratedKeys="true"
            keyProperty="instance.id"
            keyColumn="id">
        INSERT INTO purchase_order (order_number, status)
        VALUES (#{instance.orderNumber}, #{instance.status})
    </insert>
</mapper>
~~~

Statement nhận `MyBatisContext`; `instance` là `PurchaseOrder`. Cấu hình generated key phải tương thích database driver và chiến lược ID của entity. Nếu ID do ứng dụng gán sẵn, câu SQL và mapping phải ghi nhận ID đó thay vì chờ database sinh.

### 6.2. Insert child

Mapper child:

~~~xml
<mapper namespace="com.example.orders.OrderLineMapper">
    <insert id="insert"
            useGeneratedKeys="true"
            keyProperty="instance.id"
            keyColumn="id">
        INSERT INTO order_line (
            purchase_order_id,
            product_code,
            quantity,
            unit_price
        )
        VALUES (
            #{get('purchase_order_id')},
            #{instance.productCode},
            #{instance.quantity},
            #{instance.unitPrice}
        )
    </insert>
</mapper>
~~~

Ở đây:

- `instance` là `OrderLine`.
- `get('purchase_order_id')` là ID của root được truyền theo back-reference column.
- Namespace là `OrderLineMapper` vì entity đang insert là `OrderLine`.

Nếu cột back-reference được đặt tên khác, cả mapping `@MappedCollection` và expression `get(...)` phải thay đổi tương ứng.

### 6.3. Update root

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <update id="update">
        UPDATE purchase_order
        SET order_number = #{instance.orderNumber},
            status = #{instance.status}
        WHERE id = #{instance.id}
    </update>
</mapper>
~~~

Ví dụ chỉ minh họa câu update cơ bản. Nếu entity dùng `@Version`, statement tùy chỉnh cần giữ đúng semantics optimistic locking của phiên bản Spring Data JDBC đang sử dụng: điều kiện version phải được kiểm tra và version phải được cập nhật phù hợp. Không bỏ qua version chỉ vì SQL đã chạy thành công.

### 6.4. Find root by ID

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <resultMap id="purchaseOrderMap"
               type="com.example.orders.PurchaseOrder">
        <id property="id" column="id"/>
        <result property="orderNumber" column="order_number"/>
        <result property="status" column="status"/>
    </resultMap>

    <select id="findById" resultMap="purchaseOrderMap">
        SELECT id, order_number, status
        FROM purchase_order
        WHERE id = #{id}
    </select>
</mapper>
~~~

`findById` lấy dữ liệu root. Spring Data JDBC có thể thực hiện các statement khác để resolve collection child theo property path; không giả định một câu select root tự động nạp collection nếu mapping convention yêu cầu statement path riêng.

### 6.5. Resolve child collection

Với property `lines`, statement path được đặt trong namespace của root:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <resultMap id="orderLineMap"
               type="com.example.orders.OrderLine">
        <id property="id" column="id"/>
        <result property="productCode" column="product_code"/>
        <result property="quantity" column="quantity"/>
        <result property="unitPrice" column="unit_price"/>
    </resultMap>

    <select id="findAllByPath-lines" resultMap="orderLineMap">
        <!-- Truy vấn các OrderLine theo các phần khóa trong MyBatisContext.identifier -->
        <!-- Binding các phần Identifier cần khớp với mapping path thực tế. -->
    </select>
</mapper>
~~~

Tên statement `findAllByPath-lines` được tạo từ aggregate root và path `lines`. `MyBatisContext.getIdentifier()` mang ID root và các key/index cần thiết cho path. Phần điều kiện SQL cần lấy đúng các thành phần Identifier mà schema sử dụng. Với collection `List` hoặc `Map`, path có thể cần thêm vị trí hoặc key; hãy test trường hợp đó riêng.

## 7. Các thao tác delete theo property path

Spring Data JDBC có thể xóa entity child theo root ID hoặc xóa child rows thuộc tất cả aggregate root. Hai thao tác này có statement khác nhau.

### 7.1. Xóa child của một root

Ví dụ xóa các dòng hàng của đơn hàng khi xóa một aggregate:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <delete id="delete-lines">
        DELETE FROM order_line
        WHERE purchase_order_id = #{id}
    </delete>
</mapper>
~~~

`id` ở đây là ID của aggregate root. Namespace dùng `PurchaseOrderMapper`, vì property path `lines` bắt đầu từ `PurchaseOrder`.

### 7.2. Xóa child của mọi root

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <delete id="deleteAll-lines">
        DELETE FROM order_line
    </delete>
</mapper>
~~~

Statement `deleteAll-lines` xóa toàn bộ entity được tham chiếu qua path đó. Đây là thao tác rộng; cần hiểu chính xác repository operation nào kích hoạt nó và schema/foreign key có cho phép hay không.

### 7.3. Xóa toàn bộ root

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <delete id="deleteAll">
        DELETE FROM purchase_order
    </delete>
</mapper>
~~~

`deleteAll` là thao tác xóa tất cả aggregate root của kiểu được dùng làm prefix. Việc xử lý child rows phải phù hợp với mapping và quy trình delete aggregate. Không thay statement path delete bằng một câu lệnh chỉ xóa root nếu điều đó làm vi phạm foreign key hoặc bỏ qua child data.

## 8. Mapping kết quả và trách nhiệm của resultMap

Khi một statement MyBatis được chọn, MyBatis chịu trách nhiệm mapping kết quả theo cấu hình statement, `resultType` hoặc `resultMap`.

Một `resultMap` cần xác định:

- Cột nào ánh xạ vào property nào.
- Cột ID nào nhận diện object.
- Kiểu dữ liệu nào được chuyển đổi.
- Quan hệ lồng nhau có được ánh xạ trong cùng kết quả hay được Spring Data JDBC resolve qua property path.

### 8.1. Column label phải khớp resultMap

Ví dụ:

~~~sql
SELECT
    id,
    order_number,
    status
FROM purchase_order
~~~

`resultMap`:

~~~xml
<resultMap id="purchaseOrderMap"
           type="com.example.orders.PurchaseOrder">
    <id property="id" column="id"/>
    <result property="orderNumber" column="order_number"/>
    <result property="status" column="status"/>
</resultMap>
~~~

Nếu SQL đổi alias thành `order_no` nhưng resultMap vẫn đọc `order_number`, property có thể không nhận giá trị đúng. Hãy giữ alias/column label nhất quán với resultMap.

### 8.2. Type handler

MyBatis dùng TypeHandler để chuyển đổi giữa JDBC type và Java type. Khi property là enum, JSON, kiểu tiền tệ, UUID hoặc kiểu riêng, cần kiểm tra TypeHandler phù hợp.

Spring Data JDBC có hệ thống conversion riêng cho mapping mặc định. Khi chuyển một statement sang MyBatis, đừng giả định mọi Spring Converter đều tự động được MyBatis sử dụng. SQL, JDBC type và MyBatis TypeHandler phải tương thích.

### 8.3. Generated key

Với ID do database sinh, mapper insert phải trả lại ID theo cơ chế MyBatis và JDBC driver. Nếu ID không được gán lại vào entity root, Spring Data JDBC không thể truyền đúng ID đó cho insert child tiếp theo.

Kiểm tra:

- `useGeneratedKeys` và `keyProperty` nếu driver hỗ trợ.
- `selectKey` nếu database cần cách lấy sequence/key khác.
- Tên cột generated key.
- Giá trị ID thực sự được cập nhật vào entity instance.
- Insert child dùng đúng ID root sau khi insert root hoàn tất.

Đừng chỉ assert insert trả số hàng bị ảnh hưởng; hãy đọc lại entity để xác nhận ID được sinh và quan hệ child được lưu đúng.

## 9. Namespace và statement cho query có sort/page

Spring Data JDBC có thể gọi statement riêng cho thao tác sort và phân trang.

### 9.1. findAllSorted

`findAll(Sort)` có thể kích hoạt statement `findAllSorted`. MyBatisContext cung cấp sort specification. Mapper cần chuyển sort thành `ORDER BY` an toàn.

Không dùng string substitution để ghép trực tiếp sort expression vào SQL nếu `sort` có thể bị điều khiển bởi request. MyBatis có cú pháp thay thế chuỗi trực tiếp bằng dollar-brace; cách đó có thể đưa nội dung vào SQL. Hãy whitelist property và direction, sau đó dùng một tập biểu thức SQL cố định hoặc một cơ chế mapping được kiểm soát.

### 9.2. findAllPaged

`findAll(Pageable)` có thể kích hoạt statement `findAllPaged`. Context cung cấp thông tin page, size và sort. Câu SQL phải dùng cú pháp phân trang của database đang chạy.

Ví dụ PostgreSQL/MySQL:

~~~sql
SELECT id, order_number, status
FROM purchase_order
ORDER BY id
LIMIT #{pageable.pageSize}
OFFSET #{pageable.offset}
~~~

Đây là ví dụ ý tưởng; cách truy cập property của `Pageable` và cú pháp phân trang cần xác nhận theo MyBatis expression, database dialect và phiên bản Spring Data Relational. Với SQL Server/Oracle hoặc database khác, cú pháp có thể khác.

## 10. Lỗi thường gặp khi đặt namespace và statement

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Namespace thiếu package | Không khớp fully qualified domain type | Dùng namespace đầy đủ theo `NamespaceStrategy` |
| Thiếu hậu tố `Mapper` | Sai namespace mặc định | Thêm `Mapper` sau tên lớp entity |
| Statement ID sai chữ hoa/chữ thường | MyBatis không tìm thấy mapped statement | Dùng đúng ID như `findById`, `findAllByPath-lines` |
| Đặt path statement trong namespace child | Nhầm kiểu entity với aggregate root | Với thao tác property path, dùng root type làm prefix |
| Dùng tên bảng thay property path | Statement key không theo mapping path | Dùng tên property path trong aggregate |
| Dùng `findAllByProperty` cho mapper mới | Đây là convention deprecated | Dùng `findAllByPath` |
| Dùng `#{id}` trong insert child để lấy parent ID | Parent ID nằm trong additional context value | Dùng `get(key)` với tên back-reference column |
| Giả định `getInstance()` luôn có giá trị | Query không có entity instance trước khi đọc | Chọn accessor theo loại statement |
| Giả định `getId()` luôn là scalar | `findAllById` có thể truyền danh sách ID | Xử lý collection |
| Quên `Identifier` cho path lồng nhau | Thiếu root ID/key/index của relation | Dùng `getIdentifier()` và map đủ thành phần |
| ResultMap sai column label | SQL alias không khớp mapping | Đồng bộ SQL và resultMap |
| Generated ID không trở lại entity | Child insert không có root ID | Cấu hình generated key và kiểm thử driver |
| Mapper XML không được nạp | Sai `mapperLocations` hoặc resource path | Kiểm tra SqlSessionFactory và classpath |
| MyBatis dùng datasource khác | Không tham gia transaction dự kiến | Dùng cùng DataSource/transaction manager |
| Coi mọi query method đều dùng convention này | Nhầm DataAccessStrategy statements với mapper method tùy ý | Dùng custom fragment/mapper bean cho query riêng |

## 11. Kiểm thử MyBatis integration

Kiểm thử cần xác nhận không chỉ XML hợp lệ mà cả Spring Data JDBC có tìm đúng statement và truyền đúng context.

### 11.1. Kiểm tra statement được nạp

Khi khởi tạo `SqlSessionFactory`, kiểm tra mapped statement bằng tên đầy đủ:

~~~java
String statementId =
        "com.example.orders.PurchaseOrderMapper.findById";

assertThat(sqlSessionFactory.getConfiguration()
        .hasStatement(statementId))
        .isTrue();
~~~

Điều này giúp phát hiện namespace hoặc statement ID sai trước khi gọi repository.

### 11.2. Test repository operation

Với `PurchaseOrderRepository`:

- `save` tạo root và child.
- `save` cập nhật root theo statement update.
- `findById` đọc root và resolve collection child.
- `findAllById` xử lý danh sách ID.
- `deleteById` xử lý child path và root theo mapping.
- `deleteAll` xử lý các statement path cần thiết.
- `count` trả đúng số aggregate root.

Không chỉ gọi trực tiếp MyBatis mapper. Mục tiêu là kiểm tra lời gọi `CrudRepository` thực sự đi qua statement convention.

### 11.3. Test MyBatisContext cho child

Tạo một aggregate có nhiều child, lưu qua repository và xác nhận:

- Child insert nhận đúng root ID qua `get(key)`.
- Cột foreign key của mọi child trỏ đúng root.
- Generated ID của root được gán trước khi child insert.
- List/Map key hoặc index được lưu đúng nếu aggregate dùng cấu trúc đó.

### 11.4. Test rollback

Buộc child insert vi phạm constraint sau khi root đã được insert. Xác nhận transaction của repository/service rollback toàn bộ aggregate. MyBatis và Spring Data JDBC cần dùng transaction manager/datasource tương thích.

### 11.5. Test fallback

Nếu chiến lược kết hợp dùng SQL mặc định khi statement MyBatis không tồn tại, có thể kiểm tra có chủ đích một operation chưa override. Điều này xác nhận mapper chỉ thay thế những statement được định nghĩa.

Không để fallback trở thành cách che giấu lỗi tên statement. Với operation mà nhóm kỳ vọng dùng MyBatis, hãy assert `SqlSessionFactory` có statement tương ứng.

## 12. Quy trình thêm một statement mới

Khi cần thay thế một thao tác Spring Data JDBC bằng MyBatis:

1. **Xác định thao tác:** `insert`, `update`, `findById`, path relation hay một operation khác.
2. **Xác định domain type:** entity đang thao tác hay aggregate root của property path.
3. **Tính namespace:** fully qualified entity class cộng `Mapper`, trừ khi có `NamespaceStrategy` tùy chỉnh.
4. **Chọn statement ID:** dùng chính xác tên trong convention.
5. **Xác định MyBatisContext:** cần `instance`, `id`, `domainType`, parent ID hay `identifier`?
6. **Viết SQL và mapping:** dùng `resultMap`/`resultType`, TypeHandler và generated key phù hợp.
7. **Đặt XML đúng mapper location:** bảo đảm `SqlSessionFactory` nạp file.
8. **Kiểm tra datasource/transaction:** dùng cấu hình tham gia cùng transaction của Spring Data JDBC.
9. **Test qua repository:** xác nhận statement được tìm thấy và dữ liệu đúng.
10. **Test trường hợp biên:** child collection, generated ID, empty result, null, sort/page và rollback.

## 13. Tổ chức mapper theo aggregate

Một cấu trúc dễ tìm:

~~~text
src/main/resources/
  mybatis/
    orders/
      PurchaseOrderMapper.xml
      OrderLineMapper.xml
    catalog/
      ProductMapper.xml
      CategoryMapper.xml
    customers/
      CustomerMapper.xml
~~~

Trong từng XML:

- Namespace root dùng fully qualified class name + `Mapper`.
- Statement ID dùng convention của Spring Data JDBC.
- SQL được chia theo thao tác để dễ review.
- ResultMap được đặt tên rõ ràng.
- Fragment SQL có thể dùng `<sql>` và `<include>` để tránh lặp.

Không gom tất cả entity vào một namespace chung như `CommonMapper` nếu đang dùng namespace strategy mặc định. Việc gom như vậy khiến Spring Data JDBC không tìm thấy statement theo domain type.

### 13.1. Dùng SQL fragment tái sử dụng

MyBatis hỗ trợ `<sql>`:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <sql id="purchaseOrderColumns">
        id, order_number, status
    </sql>

    <select id="findById" resultMap="purchaseOrderMap">
        SELECT
        <include refid="purchaseOrderColumns"/>
        FROM purchase_order
        WHERE id = #{id}
    </select>
</mapper>
~~~

Đặt fragment trong namespace liên quan để tránh phụ thuộc chéo không cần thiết. Nếu dùng `<include refid="...">` từ namespace khác, cần tham chiếu đầy đủ theo cú pháp MyBatis.

## Ghi nhớ

Trong MyBatis integration của Spring Data JDBC, **namespace mặc định là fully qualified domain type cộng hậu tố `Mapper`**, còn statement ID là tên thao tác như `insert`, `update`, `findById` hoặc tên path như `findAllByPath-lines`. Spring Data JDBC tra cứu từng statement theo convention; statement nào được tìm thấy sẽ dùng SQL và mapping MyBatis, còn statement không được định nghĩa có thể tiếp tục dùng chiến lược mặc định.

`MyBatisContext` là parameter object cung cấp `instance`, `id`, `domainType`, `get(key)` và `identifier` tùy thao tác. Với child insert, `get(key)` truyền ID parent theo tên back-reference column; với path lồng nhau, `identifier` mang root ID cùng key/index cần thiết. Các statement property path dùng aggregate root làm namespace prefix, còn insert/update entity child dùng namespace của chính kiểu child. `findAllByProperty` đã deprecated; mapper mới nên dùng `findAllByPath`.

Hãy cấu hình `MyBatisJdbcConfiguration` cùng `SqlSessionFactory`, nạp mapper XML, dùng datasource/transaction phù hợp và kiểm thử qua repository thật. Namespace đúng nhưng context hoặc resultMap sai vẫn có thể làm aggregate lưu/đọc không đầy đủ; vì vậy cần kiểm tra cả statement lookup, generated ID, foreign key child và rollback.

## Tài liệu tham khảo

- [Spring Data Relational — MyBatis Integration](https://docs.spring.io/spring-data/relational/reference/jdbc/mybatis.html)
- [MyBatisContext API](https://docs.spring.io/spring-data/data-jdbc/docs/current/api/org/springframework/data/jdbc/mybatis/MyBatisContext.html)
- [NamespaceStrategy API](https://docs.spring.io/spring-data/data-jdbc/docs/current/api/org/springframework/data/jdbc/mybatis/NamespaceStrategy.html)
- [MyBatisDataAccessStrategy API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/jdbc/mybatis/MyBatisDataAccessStrategy.html)
