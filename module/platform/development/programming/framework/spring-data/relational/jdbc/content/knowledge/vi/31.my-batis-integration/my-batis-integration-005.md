# Ánh xạ kết quả và xử lý quan hệ bằng statement tùy chỉnh

## 1. Khi nào cần statement MyBatis tùy chỉnh?

Spring Data JDBC cung cấp một chiến lược mặc định để tạo câu SQL từ metadata của aggregate. Cách này phù hợp với phần lớn thao tác CRUD: framework biết tên bảng, cột, khóa ngoại, vị trí phần tử trong List/Map và cách chuyển đổi kiểu dữ liệu.

Một hệ thống thực tế có thể cần SQL riêng:

- Bảng được thiết kế theo schema cũ hoặc quy ước tên không theo mặc định.
- Cần dùng JOIN, CTE, hàm cửa sổ hoặc biểu thức đặc thù của database.
- Một aggregate có nhiều bảng con và cần câu SELECT/INSERT/UPDATE tối ưu.
- Kết quả query phải ánh xạ vào DTO hoặc object có cấu trúc lồng nhau.
- Cần điều khiển cách ghi khóa ngoại, thứ tự phần tử List hoặc giá trị được sinh.
- Cần tái sử dụng các đoạn SQL trong nhiều statement.

Spring Data JDBC có thể giao việc thực thi một số bước persistence cho MyBatis. MyBatis cung cấp mapped statement và ResultMap để mô tả SQL cũng như cách ánh xạ ResultSet thành object.

Điểm quan trọng là tích hợp này không biến Spring Data JDBC thành JPA và cũng không thay đổi mô hình aggregate. Spring Data JDBC vẫn quyết định các bước cần thực hiện khi lưu hoặc tải aggregate; MyBatis cung cấp câu SQL và mapping cho từng bước mà ứng dụng đã tùy chỉnh.

Bài này đi từ cách Spring Data JDBC tìm statement, dữ liệu được truyền qua MyBatisContext, đến cách ánh xạ root và các quan hệ bằng statement tùy chỉnh. Phần cuối trình bày cách dùng association/collection cho các truy vấn trả về object graph, cách kiểm soát transaction và cách kiểm thử.

## 2. Hai lớp trách nhiệm khi tích hợp

Spring Data JDBC và MyBatis giải quyết hai phần khác nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| Spring Data JDBC | Quản lý repository, aggregate boundary, thứ tự các thao tác persistence và việc phân giải quan hệ trong aggregate. |
| MyBatis | Thực thi mapped statement, bind tham số, ánh xạ kết quả bằng resultType/resultMap và xử lý SQL tùy chỉnh. |

Ví dụ một aggregate PurchaseOrder có các dòng hàng:

~~~text
PurchaseOrder
  id
  orderNumber
  status
  lines: List<PurchaseOrderLine>
    - sku
      quantity
      unitPrice
    - sku
      quantity
      unitPrice
~~~

Khi gọi repository save, Spring Data JDBC tạo một kế hoạch thay đổi aggregate. Kế hoạch đó có thể gồm:

1. Insert hoặc update hàng PurchaseOrder.
2. Xóa các hàng con cũ theo semantics lưu aggregate.
3. Insert các PurchaseOrderLine mới cùng khóa ngoại và vị trí trong List.

Khi gọi findById, Spring Data JDBC cần tải root và phân giải các đường dẫn quan hệ. MyBatis có thể cung cấp statement riêng cho root và statement riêng cho từng property path.

Vì vậy, không nên nghĩ rằng chỉ cần viết một câu SQL JOIN lớn là đã thay thế toàn bộ cơ chế aggregate persistence. Cần biết Spring Data JDBC đang yêu cầu statement nào và statement đó phải trả về kiểu dữ liệu nào.

## 3. Cấu hình MyBatis cho Spring Data JDBC

### 3.1. Import MyBatisJdbcConfiguration

Spring Data Relational cung cấp cấu hình MyBatis chuyên dụng:

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
@EnableJdbcRepositories
@Import(MyBatisJdbcConfiguration.class)
public class JdbcPersistenceConfiguration {

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

    @Bean
    SqlSessionTemplate sqlSessionTemplate(SqlSessionFactory factory) {
        return new SqlSessionTemplate(factory);
    }
}
~~~

Đây là skeleton cấu hình. Nếu MyBatis Spring Boot starter đã tạo SqlSessionFactory hoặc SqlSessionTemplate cho ứng dụng, hãy dùng các bean được auto-configure và tránh khai báo trùng. Điều quan trọng là ApplicationContext có SqlSession phù hợp để MyBatisJdbcConfiguration sử dụng.

MyBatisJdbcConfiguration thay thế DataAccessStrategy mặc định bằng chiến lược tích hợp MyBatis. Cấu hình này cho phép Spring Data JDBC kiểm tra mapped statement cho từng bước persistence. Khi statement tùy chỉnh tồn tại, statement đó được sử dụng; các bước chưa được tùy chỉnh tiếp tục dùng cơ chế mặc định theo cấu hình tích hợp.

### 3.2. SqlSessionTemplate và transaction của Spring

Không tự mở một DefaultSqlSession trong repository hoặc service. Với MyBatis-Spring, nên dùng SqlSessionTemplate:

- Thread-safe và có thể được chia sẻ giữa các bean.
- Dùng SqlSession gắn với transaction Spring hiện tại.
- Quản lý vòng đời session, bao gồm commit, rollback và close.
- Chuyển MyBatis exception sang hệ exception DataAccessException của Spring.

SqlSessionTemplate phải dùng SqlSessionFactory được cấu hình với cùng DataSource mà Spring Data JDBC dùng nếu các thao tác cần tham gia cùng transaction.

### 3.3. Vị trí mapper XML

Ví dụ cấu trúc:

~~~text
src/main/resources/
  mybatis/
    orders/
      PurchaseOrderMapper.xml
      PurchaseOrderLineMapper.xml
    customers/
      CustomerMapper.xml
~~~

Thuộc tính mapperLocations trong SqlSessionFactoryBean nạp các file XML theo pattern. Mỗi mapper XML khai báo namespace tương ứng với domain type hoặc namespace strategy mà Spring Data JDBC sử dụng.

## 4. Quy ước tên statement mà Spring Data JDBC tìm kiếm

Theo mặc định, namespace được tạo từ fully qualified class name của entity cộng hậu tố Mapper. Tên statement được ghép thêm operation.

Ví dụ, với class:

~~~java
package com.example.orders;

public class PurchaseOrder {
    // ...
}
~~~

Spring Data JDBC tìm namespace:

~~~text
com.example.orders.PurchaseOrderMapper
~~~

Statement tìm kiếm:

~~~text
com.example.orders.PurchaseOrderMapper.findById
com.example.orders.PurchaseOrderMapper.insert
com.example.orders.PurchaseOrderMapper.update
~~~

Một số operation có tên kèm property path:

~~~text
com.example.orders.PurchaseOrderMapper.findAllByPath-lines
com.example.orders.PurchaseOrderMapper.delete-lines
com.example.orders.PurchaseOrderMapper.deleteAll-lines
~~~

Tên property path phải khớp property path mà Spring Data JDBC dùng trong mapping, không phải tên bảng tùy ý. Nếu thay đổi namespace bằng NamespaceStrategy, namespace trong mapper XML phải theo strategy mới.

### 4.1. Những statement thường gặp

| Statement ID | Mục đích | Thường được gọi bởi |
| --- | --- | --- |
| insert | Insert một entity, bao gồm entity được tham chiếu trong aggregate | save, saveAll |
| update | Update một entity | save, saveAll |
| delete | Xóa một entity theo ID | delete, deleteById |
| deleteAll | Xóa tất cả aggregate root của kiểu tương ứng | deleteAll |
| delete-propertyPath | Xóa các entity được tham chiếu qua property path | deleteById |
| deleteAll-propertyPath | Xóa các entity được tham chiếu qua property path của các root | deleteAll |
| findById | Tải một aggregate root theo ID | findById |
| findAll | Tải tất cả aggregate root | findAll |
| findAllById | Tải một nhóm aggregate root theo ID | findAllById |
| findAllByPath-propertyPath | Tải các entity được tham chiếu qua property path | Các thao tác find |
| findAllSorted | Tải aggregate root theo sort | findAll(Sort) |
| findAllPaged | Tải aggregate root theo pageable | Các thao tác phân trang tương ứng |
| count | Đếm aggregate root | count |

Spring Data JDBC không bắt buộc phải có mapper cho tất cả statement. Có thể chỉ tùy chỉnh bước đang cần SQL đặc thù và để các bước còn lại dùng chiến lược mặc định.

API cũ có statement findAllByProperty-propertyName. Tài liệu hiện hành đánh dấu cách này deprecated và khuyến nghị dùng findAllByPath-propertyPath.

## 5. MyBatisContext: tham số Spring Data JDBC truyền cho statement

Khi chạy mapped statement, Spring Data JDBC truyền một MyBatisContext. Object này cung cấp thông tin để SQL có thể thao tác đúng entity hoặc quan hệ.

Các giá trị quan trọng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| getInstance() | Entity đang được lưu; với query, giá trị này là null vì object chưa tồn tại trước khi chạy SELECT. |
| getDomainType() | Kiểu domain của entity mà statement đang thao tác. Với statement quan hệ, đây có thể là kiểu entity ở cuối property path. |
| getId() | ID của entity được tải hoặc xóa; có thể là danh sách ID trong thao tác nhiều hàng. |
| getIdentifier() | Identifier mô tả đường dẫn quan hệ, gồm ID root và các key/index cần thiết. |
| get(key) | Lấy giá trị ID của entity cha theo tên back-reference column được NamingStrategy xác định. |

Không giả định tất cả getter luôn có giá trị. Ví dụ getInstance() là null trong các query load entity. MyBatisContext được thiết kế để cùng một kiểu tham số có thể phục vụ nhiều loại operation.

### 5.1. Insert entity con

Khi insert một entity được tham chiếu bởi aggregate root, MyBatisContext chứa instance của entity con và giá trị ID của entity cha. Key truyền cho get(key) là tên cột back-reference do NamingStrategy xác định.

Ví dụ bảng child có cột order_id:

~~~xml
<insert id="insert">
    INSERT INTO purchase_order_line (
        order_id,
        sku,
        quantity,
        unit_price
    )
    VALUES (
        #{_parameter.get('order_id')},
        #{instance.sku},
        #{instance.quantity},
        #{instance.unitPrice}
    )
</insert>
~~~

Đây là ví dụ minh họa cho child entity có back-reference column order_id. Tên key phải khớp chính xác tên cột được NamingStrategy hoặc @MappedCollection tạo ra. Với List/Map, schema còn có cột lưu index/key; statement insert phải ghi đúng giá trị đó theo metadata của quan hệ.

### 5.2. Query quan hệ

Với query quan hệ, MyBatisContext có getIdentifier(). Identifier có thể chứa:

- ID của aggregate root.
- ID/key của các entity trung gian trong property path.
- Index của List hoặc key của Map.

Đây là lý do statement findAllByPath cần xử lý Identifier thay vì chỉ giả định có một root ID đơn giản. Nếu path chứa composite ID, List/Map lồng nhau hoặc nhiều cấp quan hệ, hãy bind đúng các phần identifier tương ứng.

## 6. Mô hình quan hệ cần hiểu trước khi viết SQL

Spring Data JDBC xem các object được tham chiếu trực tiếp trong aggregate là một phần của aggregate đó. Các quan hệ được quản lý như một phần của aggregate có thể là:

- One-to-one.
- One-to-many.

Quan hệ many-to-one hoặc many-to-many giữa các aggregate thường thể hiện bằng ID hoặc AggregateReference, vì hai phía thuộc hai aggregate độc lập.

Ví dụ:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;
    private OrderStatus status;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<PurchaseOrderLine> lines;

    // Constructor, getters, domain methods...
}
~~~

Entity con:

~~~java
public class PurchaseOrderLine {

    private String sku;
    private int quantity;
    private BigDecimal unitPrice;

    // Constructor, getters...
}
~~~

Schema tương ứng có thể là:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE purchase_order_line (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(19, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES purchase_order(id)
);
~~~

Trong ví dụ này:

- order_id là back-reference từ dòng hàng về aggregate root.
- line_no lưu vị trí của phần tử trong List.
- Spring Data JDBC dùng @MappedCollection để biết tên hai cột đó.
- SQL MyBatis phải ghi và đọc đúng các cột tương ứng.

Nếu không khai báo tên riêng, Spring Data JDBC dùng NamingStrategy để tạo tên back-reference và key column. Khi SQL tùy chỉnh, phải kiểm tra naming strategy thực tế thay vì tự đoán tên.

## 7. Ánh xạ aggregate root bằng resultMap

ResultMap mô tả cách MyBatis chuyển một hàng ResultSet thành object. Với statement findById của Spring Data JDBC, resultMap thường ánh xạ dữ liệu của aggregate root.

Ví dụ:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">

    <resultMap id="purchaseOrderRow"
               type="com.example.orders.PurchaseOrder">
        <id property="id" column="id"/>
        <result property="orderNumber" column="order_number"/>
        <result property="status" column="status"/>
    </resultMap>

    <select id="findById"
            parameterType="org.springframework.data.jdbc.mybatis.MyBatisContext"
            resultMap="purchaseOrderRow">
        SELECT
            id,
            order_number,
            status
        FROM purchase_order
        WHERE id = #{id}
    </select>

</mapper>
~~~

Statement ID là findById trong namespace PurchaseOrderMapper. Tham số id được lấy từ MyBatisContext.getId().

### 7.1. Vì sao cần khai báo id trong resultMap?

Thẻ id đánh dấu cột định danh object. Khi kết quả có JOIN và lặp lại thông tin root trên nhiều hàng, MyBatis cần biết hàng nào thuộc cùng một object. Khai báo id rõ ràng giúp MyBatis nhận diện object và xử lý nested result tốt hơn.

### 7.2. Ánh xạ constructor hoặc immutable object

Nếu domain type dùng constructor hoặc record, MyBatis có thể dùng phần constructor của resultMap:

~~~xml
<resultMap id="customerRow"
           type="com.example.customers.Customer">
    <constructor>
        <idArg name="id" column="id" javaType="long"/>
        <arg name="name" column="display_name" javaType="string"/>
        <arg name="email" column="email" javaType="string"/>
    </constructor>
</resultMap>
~~~

Tên tham số và thứ tự constructor phải phù hợp với kiểu Java thực tế và phiên bản MyBatis đang dùng. Nếu dùng JavaBean mutable, có thể dùng property mapping như ví dụ PurchaseOrder.

## 8. Tải collection qua findAllByPath

Trong tích hợp Spring Data JDBC, statement tải quan hệ có tên:

~~~text
<AggregateRootFullyQualifiedName>Mapper.findAllByPath-<propertyPath>
~~~

Với property lines của PurchaseOrder:

~~~text
com.example.orders.PurchaseOrderMapper.findAllByPath-lines
~~~

Statement này trả về các entity PurchaseOrderLine. Spring Data JDBC dùng chúng để phân giải property path và lắp ráp aggregate.

Ví dụ mapper:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">

    <resultMap id="purchaseOrderLineRow"
               type="com.example.orders.PurchaseOrderLine">
        <result property="sku" column="sku"/>
        <result property="quantity" column="quantity"/>
        <result property="unitPrice" column="unit_price"/>
    </resultMap>

    <select id="findAllByPath-lines"
            parameterType="org.springframework.data.jdbc.mybatis.MyBatisContext"
            resultMap="purchaseOrderLineRow">
        SELECT
            sku,
            quantity,
            unit_price
        FROM purchase_order_line
        WHERE order_id = #{identifier.parts[0].value}
        ORDER BY line_no
    </select>

</mapper>
~~~

Trong ví dụ đơn giản này, Identifier chỉ chứa một phần ID của aggregate root. Biểu thức parts[0].value minh họa việc lấy giá trị từ phần đầu tiên của Identifier; không được coi index 0 là quy ước dùng được cho mọi aggregate. Với composite ID, property path nhiều cấp hoặc quan hệ List/Map lồng nhau, Identifier có nhiều phần. Hãy xác định đúng phần theo tên cột và đường dẫn quan hệ thực tế.

### 8.1. Vì sao ORDER BY line_no quan trọng?

List lưu cả thứ tự phần tử. Cột keyColumn trong @MappedCollection giữ vị trí của phần tử. Khi tải collection, statement nên trả các dòng theo đúng key/index để kết quả phản ánh thứ tự đã lưu.

Với Set, thứ tự không có cùng ý nghĩa. Với Map, cột key lưu khóa Map thay vì index tuần tự.

### 8.2. Property path lồng nhau

Giả sử aggregate có:

~~~text
PurchaseOrder
  shipments: List<Shipment>
    packages: List<Package>
~~~

Một query phân giải property path sâu có thể cần statement:

~~~text
PurchaseOrderMapper.findAllByPath-shipments
PurchaseOrderMapper.findAllByPath-shipments.packages
~~~

Statement thứ hai nhận Identifier có thông tin về root và phần tử trung gian cần thiết. SQL phải dùng các phần đó để giới hạn đúng packages của shipment thuộc đúng purchase order. Không chỉ lọc theo một root ID nếu path có nhiều cấp và nhiều phần tử trung gian.

## 9. Insert và update entity được tham chiếu

Khi Spring Data JDBC lưu aggregate, các entity con cũng được insert/update theo semantics của aggregate. MyBatis có thể cung cấp statement cho từng kiểu entity.

Ví dụ namespace của entity con:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderLineMapper">

    <insert id="insert">
        INSERT INTO purchase_order_line (
            order_id,
            sku,
            quantity,
            unit_price
        )
        VALUES (
            #{_parameter.get('order_id')},
            #{instance.sku},
            #{instance.quantity},
            #{instance.unitPrice}
        )
    </insert>

</mapper>
~~~

Spring Data JDBC truyền instance của entity đang được insert và ID của parent thông qua MyBatisContext. Trong ví dụ, get('order_id') lấy back-reference value theo naming strategy.

Nếu entity có ID riêng, insert statement cần xử lý ID theo schema. Nếu database sinh ID, cấu hình generated keys hoặc cơ chế selectKey phù hợp với database và cách Spring Data JDBC nhận ID. Nếu child dùng khóa tổng hợp gồm parent ID và list index, SQL phải ghi đủ các thành phần đó.

### 9.1. Update và version

Statement update dùng instance hiện tại:

~~~xml
<update id="update">
    UPDATE purchase_order
    SET order_number = #{instance.orderNumber},
        status = #{instance.status}
    WHERE id = #{instance.id}
</update>
~~~

Nếu aggregate dùng @Version hoặc yêu cầu optimistic locking, SQL tùy chỉnh phải giữ đúng điều kiện version và cập nhật version theo semantics mong muốn. Không bỏ qua cột version chỉ vì câu UPDATE tùy chỉnh đang chạy thành công.

### 9.2. Delete quan hệ

Khi xóa aggregate, các hàng con thuộc aggregate phải được xử lý theo đúng thứ tự và ràng buộc khóa ngoại. Statement delete theo property path có thể được đặt tên:

~~~text
PurchaseOrderMapper.delete-lines
PurchaseOrderMapper.deleteAll-lines
~~~

Statement delete-lines thường xóa các dòng con thuộc một root cụ thể. Statement deleteAll-lines xử lý các dòng con theo phạm vi thao tác deleteAll. SQL phải giữ điều kiện khóa ngoại và không xóa nhầm dữ liệu thuộc aggregate khác.

## 10. MyBatis association và collection

MyBatis có khả năng ánh xạ một ResultSet thành object graph bằng các thành phần:

- resultMap: định nghĩa cách map cột thành object.
- association: ánh xạ quan hệ một-một.
- collection: ánh xạ quan hệ một-nhiều.
- constructor: tạo object qua constructor.
- id/result: ánh xạ định danh và thuộc tính.

Các kỹ thuật này rất hữu ích cho truy vấn tùy chỉnh trả về DTO hoặc object graph do mapper quản lý.

### 10.1. Association cho quan hệ một-một

Ví dụ một báo cáo customer kèm địa chỉ:

~~~xml
<resultMap id="customerWithAddress"
           type="com.example.report.CustomerView">
    <id property="id" column="customer_id"/>
    <result property="name" column="customer_name"/>

    <association property="address"
                 javaType="com.example.report.AddressView">
        <id property="id" column="address_id"/>
        <result property="city" column="address_city"/>
        <result property="street" column="address_street"/>
    </association>
</resultMap>
~~~

SQL:

~~~xml
<select id="findCustomerView" resultMap="customerWithAddress">
    SELECT
        c.id AS customer_id,
        c.name AS customer_name,
        a.id AS address_id,
        a.city AS address_city,
        a.street AS address_street
    FROM customers c
    LEFT JOIN customer_address a ON a.customer_id = c.id
    WHERE c.id = #{id}
</select>
~~~

Alias cột giúp tránh trùng tên id, name giữa các bảng.

### 10.2. Collection cho quan hệ một-nhiều

Ví dụ một report view có danh sách dòng hàng:

~~~xml
<resultMap id="orderReport"
           type="com.example.report.OrderReport">
    <id property="id" column="order_id"/>
    <result property="orderNumber" column="order_number"/>

    <collection property="lines"
                ofType="com.example.report.OrderLineView">
        <id property="id" column="line_id"/>
        <result property="sku" column="line_sku"/>
        <result property="quantity" column="line_quantity"/>
    </collection>
</resultMap>
~~~

SQL:

~~~xml
<select id="findOrderReport" resultMap="orderReport">
    SELECT
        o.id AS order_id,
        o.order_number,
        l.id AS line_id,
        l.sku AS line_sku,
        l.quantity AS line_quantity
    FROM purchase_order o
    LEFT JOIN purchase_order_line l ON l.order_id = o.id
    WHERE o.id = #{id}
    ORDER BY l.line_no
</select>
~~~

MyBatis gom nhiều hàng ResultSet thành một OrderReport với collection lines. Thẻ id ở root và child giúp nhận diện hàng lặp thuộc cùng object.

### 10.3. Nested select và nested result

MyBatis có hai cách phổ biến để tải association/collection:

| Cách | Hoạt động | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| Nested select | Statement chính gọi statement khác để tải quan hệ | SQL riêng cho từng quan hệ, dễ tách logic | Có thể tạo N+1 query nếu tải nhiều root |
| Nested result | JOIN dữ liệu liên quan trong một ResultSet rồi gom object | Có thể giảm số round trip | Hàng bị lặp, cần alias/id mapping chính xác và có thể tăng lượng dữ liệu truyền |

Nested select:

~~~xml
<resultMap id="orderWithLines"
           type="com.example.report.OrderReport">
    <id property="id" column="id"/>
    <result property="orderNumber" column="order_number"/>
    <collection property="lines"
                column="id"
                ofType="com.example.report.OrderLineView"
                select="findLinesByOrderId"/>
</resultMap>

<select id="findOrder" resultMap="orderWithLines">
    SELECT id, order_number
    FROM purchase_order
    WHERE id = #{id}
</select>

<select id="findLinesByOrderId" resultType="com.example.report.OrderLineView">
    SELECT sku, quantity
    FROM purchase_order_line
    WHERE order_id = #{id}
</select>
~~~

Nested result dùng JOIN và collection như ví dụ trước. Chọn cách nào cần đo số root, số child, số round trip và kích thước ResultSet.

## 11. Không nhầm MyBatis object graph với aggregate path resolution

Đây là điểm kiến trúc cần giữ rõ.

MyBatis tự nó có thể dùng association/collection để dựng một object graph từ một query. Nhưng tích hợp Spring Data JDBC còn có cơ chế RelationResolver riêng để tải các entity thuộc aggregate theo property path.

Khi tùy chỉnh repository CRUD của Spring Data JDBC:

- findById tải aggregate root bằng statement findById.
- Các quan hệ được phân giải qua statement findAllByPath-propertyPath.
- Kết quả path statement phải ánh xạ đúng kiểu entity ở cuối path.
- Identifier cho biết root ID và các key/index cần thiết.
- Spring Data JDBC lắp ráp các phần tử quan hệ vào aggregate.

Vì vậy, nếu muốn thay cách Spring Data JDBC tải collection trong một aggregate, hãy triển khai statement findAllByPath-... theo hợp đồng tích hợp. Đừng mặc định rằng một collection được MyBatis nested result map trong câu findById sẽ tự động thay thế mọi bước relation resolution của Spring Data JDBC.

Ngược lại, nếu đang xây dựng một query riêng trả về report DTO hoặc read model, MyBatis association/collection là cách phù hợp để map toàn bộ object graph trong một statement.

Giữ hai mục tiêu này tách bạch:

- Aggregate persistence: Spring Data JDBC điều phối aggregate và property path; MyBatis cung cấp SQL cho từng bước.
- Read model/report: MyBatis có thể điều phối toàn bộ JOIN và object graph theo resultMap riêng.

## 12. AggregateReference và quan hệ giữa các aggregate

Spring Data JDBC không coi mọi object reference là quan hệ có thể cascade tùy ý. Các entity được tham chiếu như một phần của aggregate phải tuân theo aggregate boundary.

Ví dụ PurchaseOrder có thể chứa các PurchaseOrderLine. Nhưng Customer mà đơn hàng tham chiếu thường là aggregate độc lập. Khi đó, nên lưu customer ID hoặc AggregateReference thay vì nhúng Customer object để Spring Data JDBC coi nó là child.

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private AggregateReference<Customer, Long> customer;
}
~~~

Trong MyBatis SQL, trường reference được lưu như một giá trị khóa ngoại đơn giản. Không tạo statement findAllByPath-customer với ý định cascade tải một aggregate khác như thể Customer là child của PurchaseOrder.

Nếu use case cần thông tin customer cùng đơn hàng, có thể:

- Tải Customer qua CustomerRepository riêng.
- Dùng một query report có JOIN và map sang DTO.
- Dùng application service để phối hợp hai aggregate.

Điều này giữ ranh giới nhất quán của mỗi aggregate rõ ràng.

## 13. Tham số SQL và dynamic SQL

MyBatis hỗ trợ dynamic SQL bằng các thẻ như:

- if
- choose/when/otherwise
- where
- set
- foreach
- trim

Ví dụ query lọc theo trạng thái tùy chọn:

~~~xml
<select id="findOrders" resultMap="purchaseOrderRow">
    SELECT id, order_number, status
    FROM purchase_order
    <where>
        <if test="status != null">
            status = #{status}
        </if>
        <if test="orderNumber != null">
            AND order_number = #{orderNumber}
        </if>
    </where>
</select>
~~~

### 13.1. Dùng #{} cho giá trị

Biểu thức #{} tạo PreparedStatement parameter và bind giá trị. Đây là lựa chọn mặc định cho dữ liệu từ request, ID, trạng thái và các giá trị lọc.

Không nối trực tiếp dữ liệu người dùng vào SQL. Nếu cần thay tên cột hoặc ORDER BY động, hãy ánh xạ input sang danh sách identifier được whitelist trong code. Thay thế chuỗi SQL trực tiếp có thể mở ra SQL injection vì identifier không thể bind như một giá trị thông thường.

### 13.2. Collection parameter với foreach

Ví dụ tìm nhiều đơn hàng theo danh sách ID:

~~~xml
<select id="findByIds" resultMap="purchaseOrderRow">
    SELECT id, order_number, status
    FROM purchase_order
    WHERE id IN
    <foreach collection="ids"
             item="id"
             open="("
             separator=","
             close=")">
        #{id}
    </foreach>
</select>
~~~

Nếu statement được gọi từ MyBatisContext, tên collection và cách truy cập tham số phải theo cấu trúc context thực tế. Đừng copy nguyên ví dụ tham số List độc lập vào statement nhận MyBatisContext mà không điều chỉnh đường dẫn thuộc tính.

## 14. resultType hay resultMap?

Hai cách khai báo có mục đích khác nhau:

| Cách | Dùng khi |
| --- | --- |
| resultType | Kết quả đơn giản, tên cột có thể ánh xạ trực tiếp vào property/constructor |
| resultMap | Cần alias phức tạp, constructor mapping, association, collection, discriminator hoặc ánh xạ nhiều bảng |

Chỉ dùng một trong hai cho cùng statement SELECT. Nếu query có JOIN với nhiều cột cùng tên như id, name, status, hãy dùng alias và resultMap tường minh.

### 14.1. Cẩn thận với auto-mapping khi JOIN

MyBatis có các chế độ auto-mapping NONE, PARTIAL và FULL. FULL có thể gây lỗi khi JOIN nhiều bảng có cột trùng tên. Ví dụ id của child có thể vô tình nhận id của parent nếu alias và mapping không được kiểm soát.

Với query nhiều bảng:

- Đặt alias cho tất cả cột có khả năng trùng.
- Khai báo id cho root và child.
- Dùng columnPrefix khi tái sử dụng resultMap lồng nhau.
- Tắt autoMapping cho resultMap nếu muốn mapping tường minh.
- Chỉ dùng FULL khi đã hiểu toàn bộ cột trong ResultSet.

## 15. Tùy chỉnh statement nhưng giữ cơ chế mặc định cho phần còn lại

Không cần chuyển tất cả operation sang MyBatis cùng lúc.

Ví dụ:

| Operation | Cách xử lý |
| --- | --- |
| PurchaseOrder.findById | MyBatis vì cần SQL root đặc thù |
| PurchaseOrder.findAllByPath-lines | MyBatis vì bảng line dùng tên cột riêng |
| PurchaseOrder.insert | Mặc định Spring Data JDBC |
| PurchaseOrder.update | Mặc định Spring Data JDBC |
| PurchaseOrder.delete | Mặc định Spring Data JDBC |

Spring Data JDBC kiểm tra mapped statement cho từng bước. Khi tìm thấy statement phù hợp, statement đó được sử dụng. Các bước chưa có statement tùy chỉnh có thể tiếp tục đi qua default strategy trong cấu hình tích hợp.

Lưu ý về API cấu hình thấp hơn: tạo trực tiếp new MyBatisDataAccessStrategy(sqlSession) chỉ cung cấp chiến lược MyBatis, không tự bao gồm chức năng của DefaultDataAccessStrategy. Nếu tự xây dựng DataAccessStrategy thay vì import MyBatisJdbcConfiguration, hãy dùng factory createCombinedAccessStrategy(...) khi cần fallback về chiến lược mặc định.

## 16. Transaction khi phối hợp Spring Data JDBC và MyBatis

Một use case có thể gọi repository Spring Data JDBC, đồng thời thực thi mapped statement MyBatis. Nếu hai bên dùng chung DataSource và MyBatis-Spring quản lý SqlSession qua SqlSessionTemplate, các câu lệnh có thể tham gia cùng transaction Spring.

Ví dụ:

~~~java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository orders;
    private final SqlSession sqlSession;

    public PurchaseOrderService(
            PurchaseOrderRepository orders,
            SqlSession sqlSession
    ) {
        this.orders = orders;
        this.sqlSession = sqlSession;
    }

    @Transactional
    public Long create(PurchaseOrder order) {
        PurchaseOrder saved = orders.save(order);

        sqlSession.insert(
                "com.example.audit.AuditMapper.insert",
                Map.of(
                        "aggregateId", saved.getId(),
                        "action", "ORDER_CREATED"
                )
        );

        return saved.getId();
    }
}
~~~

Đây là ví dụ điều phối một repository operation và một statement MyBatis độc lập. Nếu cả hai dùng cùng transaction manager/DataSource, lỗi trong audit insert có thể làm rollback thao tác lưu đơn hàng.

Không gọi commit() hoặc rollback() thủ công trên SqlSessionTemplate trong một transaction được Spring quản lý. Để transaction interceptor và SqlSessionTemplate phối hợp vòng đời transaction.

Nếu MyBatis và Spring Data JDBC dùng hai DataSource khác nhau, một @Transactional thông thường không tự tạo distributed transaction. Cần thiết kế transaction manager hoặc cơ chế phối hợp riêng.

## 17. Những điểm cần kiểm soát khi tùy chỉnh ghi aggregate

Khi thay statement insert/update/delete, SQL cần giữ các quy tắc mà Spring Data JDBC mong đợi:

1. **Back-reference:** child row phải ghi đúng foreign key trỏ về parent.
2. **List/Map key:** ghi đúng index/key column nếu mapping cần.
3. **Generated ID:** trả hoặc gán ID theo cơ chế mà DataAccessStrategy mong đợi.
4. **Update semantics:** không làm mất dữ liệu hoặc cập nhật nhầm hàng.
5. **Delete order:** xử lý child row trước khi xóa parent nếu foreign key yêu cầu.
6. **Version:** giữ điều kiện optimistic locking và cập nhật version khi cần.
7. **Affected rows:** kiểm tra số hàng bị tác động nếu nghiệp vụ phụ thuộc vào việc update/delete thành công.
8. **Transaction:** các statement thuộc một lần lưu aggregate phải cùng tham gia transaction.

Nếu SQL tùy chỉnh bỏ sót một bước trong chuỗi operation, lỗi có thể chỉ xuất hiện khi save aggregate có collection rỗng, khi thay thế collection, hoặc khi xóa aggregate có nhiều cấp con. Hãy kiểm thử đủ các trường hợp này.

## 18. Hiệu năng khi ánh xạ quan hệ

Ánh xạ quan hệ không chỉ là vấn đề đúng/sai; cách tải dữ liệu ảnh hưởng trực tiếp đến số câu SQL và lượng dữ liệu truyền.

### 18.1. N+1 query

Nested select có thể tạo một query cho root và thêm một query cho mỗi quan hệ hoặc mỗi root. Với danh sách lớn, số round trip tăng nhanh.

Nếu query là report/read model, cân nhắc JOIN và nested result map để lấy dữ liệu trong một lần truy vấn. Nếu đang dùng aggregate repository, cân nhắc số path statement được thực hiện và chỉ tải aggregate khi use case thật sự cần toàn bộ aggregate.

### 18.2. Dữ liệu JOIN bị lặp

JOIN một root với nhiều collection có thể nhân số hàng. Ví dụ một đơn có 5 lines và 3 payments; JOIN cả hai collection có thể tạo tới 15 hàng cho một đơn. MyBatis cần id mapping để khử lặp, còn database và network vẫn phải xử lý lượng hàng lớn.

Có thể tách query theo từng collection hoặc dùng projection phù hợp thay vì tạo một JOIN khổng lồ.

### 18.3. Index và thứ tự

Với statement quan hệ, thường cần index trên foreign key và key column:

~~~sql
CREATE INDEX idx_order_line_order_id
    ON purchase_order_line(order_id);
~~~

Nếu truy vấn sắp xếp theo line_no:

~~~sql
CREATE INDEX idx_order_line_order_line_no
    ON purchase_order_line(order_id, line_no);
~~~

Cú pháp tạo index và khả năng tạo online phụ thuộc database. Đo execution plan và dữ liệu thực tế trước khi quyết định.

## 19. Kiểm thử statement tùy chỉnh

Không chỉ kiểm tra statement chạy được. Cần kiểm tra statement được Spring Data JDBC gọi đúng lúc và trả về object graph đúng.

### 19.1. Kiểm thử load root

- Gọi repository.findById.
- Xác nhận statement findById được MyBatis thực thi.
- Kiểm tra root ID, enum, nullable field và kiểu dữ liệu.

### 19.2. Kiểm thử quan hệ

- Tạo một aggregate có nhiều child.
- Gọi findById.
- Xác nhận statement findAllByPath-lines được tìm thấy.
- Kiểm tra foreign key filter.
- Kiểm tra thứ tự List theo key column.
- Kiểm tra collection rỗng và aggregate không có child.

### 19.3. Kiểm thử save

- Insert aggregate mới cùng child.
- Update root.
- Thay đổi một child.
- Xóa một child khỏi collection.
- Xóa toàn bộ collection.
- Xóa aggregate root.

Kiểm tra cả parent ID, key/index và foreign key trong database sau mỗi thao tác.

### 19.4. Kiểm thử fallback

Chỉ tùy chỉnh một statement, để các statement còn lại dùng mặc định. Xác nhận cấu hình tích hợp vẫn chạy đúng. Điều này đặc biệt quan trọng nếu dùng combined strategy hoặc MyBatisJdbcConfiguration.

### 19.5. Kiểm thử transaction

Trong một service @Transactional:

1. Lưu aggregate.
2. Chạy một mapped statement khác.
3. Cố tình làm bước cuối thất bại.
4. Xác nhận mọi thay đổi cùng transaction rollback.

Dùng database thật hoặc Testcontainers với cùng loại engine như production khi statement phụ thuộc cú pháp SQL, generated key hoặc hành vi khóa.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Spring Data JDBC không tìm thấy statement | Namespace hoặc statement ID không theo quy ước | Kiểm tra fully qualified domain type, hậu tố Mapper và operation ID. |
| Root tải được nhưng collection rỗng | Thiếu findAllByPath-propertyPath hoặc WHERE dùng sai back-reference | Kiểm tra statement path, Identifier và tên cột FK. |
| Child được gắn sai parent | SQL không bind đúng parent ID từ MyBatisContext | Dùng get(key) hoặc Identifier phù hợp với path; xác nhận NamingStrategy. |
| Thứ tự List thay đổi | Không ghi hoặc không ORDER BY key/index column | Dùng @MappedCollection(keyColumn=...) và sắp xếp theo cột đó. |
| JOIN tạo child trùng lặp | ResultMap thiếu id mapping hoặc alias cột không rõ | Khai báo id cho root/child và alias các cột trùng tên. |
| Constructor mapping lỗi | Tham số, tên hoặc kiểu constructor không khớp | Kiểm tra resultMap constructor và kiểu Java thực tế. |
| SQL tùy chỉnh insert root nhưng child không được lưu | Chỉ tạo statement cho root, bỏ qua statement child hoặc path cần thiết | Xác định toàn bộ DbAction/statement phát sinh từ aggregate save. |
| Xóa root bị lỗi foreign key | Statement delete không xử lý child đúng thứ tự | Bổ sung delete-propertyPath hoặc cấu hình cascade/schema phù hợp. |
| Một phần thao tác commit dù use case lỗi | MyBatis session không tham gia transaction Spring hoặc dùng DataSource khác | Dùng SqlSessionTemplate và cùng DataSource/transaction manager. |
| Mất fallback mặc định | Tự tạo MyBatisDataAccessStrategy thuần | Dùng MyBatisJdbcConfiguration hoặc createCombinedAccessStrategy. |
| Query report chậm do N+1 | Nested select chạy lặp cho nhiều root | Cân nhắc JOIN/nested result, batch hoặc projection phù hợp. |

## 21. Quy trình thiết kế statement tùy chỉnh

Khi một thao tác cần SQL riêng, hãy thực hiện theo trình tự:

1. **Xác định operation:** đang tùy chỉnh insert, update, delete, findById hay relation path?
2. **Xác định domain type:** namespace dựa trên root hay entity con?
3. **Xác định statement ID:** operation có property path hay không?
4. **Đọc MyBatisContext:** cần instance, id, domainType, identifier hay parent back-reference?
5. **Kiểm tra schema:** tên bảng, FK, list index, map key và generated ID.
6. **Viết resultMap:** xác định rõ ID, property, constructor, association và collection.
7. **Giữ aggregate boundary:** quan hệ nào thuộc aggregate, quan hệ nào chỉ là AggregateReference?
8. **Kiểm tra fallback:** các operation chưa tùy chỉnh có còn dùng default strategy?
9. **Kiểm thử transaction:** tất cả statement liên quan có cùng commit/rollback không?
10. **Đo hiệu năng:** kiểm tra số query, execution plan, số hàng và lượng dữ liệu trả về.

## 22. Bài tập tự thực hành

**Bài tập 1 — Cấu hình MyBatis.** Import MyBatisJdbcConfiguration, cấu hình SqlSessionFactoryBean và SqlSessionTemplate. Xác nhận Spring Data JDBC vẫn tạo được repository.

**Bài tập 2 — Statement findById.** Viết mapper XML cho PurchaseOrderMapper.findById, dùng resultMap ánh xạ root và gọi repository.findById.

**Bài tập 3 — Statement quan hệ.** Viết findAllByPath-lines để tải PurchaseOrderLine theo Identifier. Kiểm tra FK và thứ tự List.

**Bài tập 4 — Insert child.** Viết PurchaseOrderLineMapper.insert, dùng MyBatisContext.instance và parent back-reference từ get(key). Kiểm tra khóa ngoại trong database.

**Bài tập 5 — Delete property path.** Tùy chỉnh delete-lines và kiểm tra xóa aggregate có nhiều dòng hàng không vi phạm foreign key.

**Bài tập 6 — Association và collection.** Viết một report query dùng JOIN, association và collection để trả OrderReport DTO. So sánh với cách Spring Data JDBC tải aggregate qua findAllByPath.

**Bài tập 7 — Nested select và nested result.** Thực hiện cùng một report theo hai cách, đo số query và lượng hàng ResultSet.

**Bài tập 8 — Composite path.** Tạo quan hệ List/Map lồng nhau và kiểm tra Identifier có các ID, key và index cần thiết. Viết statement lọc đúng phần tử cha.

**Bài tập 9 — Fallback.** Chỉ tùy chỉnh findById, để insert/update/delete mặc định. Xác nhận các operation còn lại vẫn hoạt động.

**Bài tập 10 — Transaction.** Lưu aggregate và ghi audit bằng MyBatis trong cùng service transaction. Làm audit statement thất bại và xác nhận aggregate rollback.

## 23. Ghi nhớ

Spring Data JDBC có thể ủy quyền từng bước CRUD/query cho MyBatis. Statement được tìm theo namespace mặc định gồm fully qualified domain class cộng Mapper, sau đó là operation ID. Với quan hệ, statement findAllByPath-propertyPath nhận MyBatisContext có Identifier chứa ID root cùng các key/index cần thiết để tải đúng entity ở cuối path.

ResultMap của MyBatis ánh xạ cột thành object; association mô tả quan hệ một-một và collection mô tả quan hệ một-nhiều. Nested select dễ tách nhưng có thể gây N+1; nested result dùng JOIN có thể giảm round trip nhưng cần alias và id mapping chính xác. Trong aggregate repository của Spring Data JDBC, hãy tuân thủ cơ chế property-path resolution; dùng association/collection để dựng object graph độc lập cho read model khi phù hợp.

Khi tùy chỉnh insert/update/delete, SQL phải giữ back-reference, list/map key, generated ID, version và thứ tự xóa. Dùng SqlSessionTemplate với cùng DataSource để MyBatis tham gia transaction Spring. Có thể tùy chỉnh từng statement và để phần còn lại dùng default strategy; nếu tự cấu hình DataAccessStrategy, cần dùng combined strategy khi vẫn muốn fallback mặc định.

### Tài liệu tham khảo

- [Spring Data Relational – MyBatis Integration](https://docs.spring.io/spring-data/relational/reference/jdbc/mybatis.html)
- [Spring Data Relational – MyBatisContext API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/mybatis/MyBatisContext.html)
- [Spring Data Relational – MyBatisDataAccessStrategy API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/mybatis/MyBatisDataAccessStrategy.html)
- [Spring Data Relational – Mapping and Relationships](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
- [MyBatis – Mapper XML Files and Result Maps](https://mybatis.org/mybatis-3/sqlmap-xml.html)
- [MyBatis-Spring – Using SqlSessionTemplate](https://mybatis.org/spring/sqlsession.html)
