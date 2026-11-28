# Phân biệt MyBatis với JDBC trực tiếp và ORM

Khi một ứng dụng Java cần làm việc với cơ sở dữ liệu quan hệ, JDBC trực tiếp, MyBatis và ORM đều có thể đọc, ghi cùng một bảng. Khác biệt quan trọng nằm ở phần việc lập trình viên tự làm, cách ứng dụng mô tả truy vấn và cách dữ liệu sau truy vấn được quản lý.

Trong chương Định hướng của module MYBATIS, bài này giúp bạn xác định MyBatis đứng ở đâu: một framework ánh xạ SQL, cho phép chủ động viết SQL và ánh xạ tham số, kết quả về đối tượng Java. Từ đó, bạn có cơ sở lựa chọn công cụ và hiểu vì sao các nội dung như Mapper, SqlSession, resultMap, SQL động, TypeHandler, giao dịch, cache và batch xuất hiện trong MyBatis.

Sau bài học, bạn có thể:

- Phân biệt JDBC API, SQL mapper và ORM, đồng thời phân biệt JPA với Hibernate.
- So sánh ba cách triển khai cùng một yêu cầu đọc, ghi dữ liệu.
- Giải thích vì sao một đối tượng được MyBatis trả về không tự động có cơ chế theo dõi thay đổi như một entity đang được ORM quản lý.
- Chọn cách tiếp cận dựa trên mô hình dữ liệu, truy vấn và giao dịch thay vì dựa vào nhận định “công cụ nào luôn nhanh hơn”.

## 1. Ba cách tiếp cận đang giải quyết phần việc nào?

### JDBC trực tiếp: làm việc với API truy cập cơ sở dữ liệu

JDBC là API chuẩn của Java để làm việc với cơ sở dữ liệu thông qua JDBC driver. Những đối tượng quen thuộc gồm `Connection`, `PreparedStatement` và `ResultSet`.

Khi dùng JDBC trực tiếp, bạn thường tự thực hiện chuỗi công việc:

1. Nhận hoặc mở kết nối.
2. Viết SQL và tạo statement.
3. Gán tham số đúng vị trí, đúng kiểu dữ liệu.
4. Thực thi SQL.
5. Đọc từng hàng, từng cột và dựng đối tượng Java.
6. Đóng tài nguyên và phối hợp commit hoặc rollback theo ranh giới giao dịch.

JDBC cho quyền kiểm soát chi tiết, nhưng các thao tác lặp lại cũng nằm trong mã ứng dụng. Việc dùng connection pool giúp quản lý kết nối hiệu quả hơn; nó không tự viết truy vấn hay ánh xạ `ResultSet` thay bạn.

### MyBatis: ánh xạ câu SQL do bạn viết

MyBatis là một SQL mapper. Bạn định nghĩa các thao tác truy cập dữ liệu thông qua Mapper, cung cấp SQL bằng XML hoặc annotation, rồi mô tả cách liên kết tham số và ánh xạ kết quả.

MyBatis xử lý nhiều công việc lặp lại quanh JDBC: chuẩn bị statement, gán tham số, thực thi và dựng kết quả theo cấu hình. Khi kiểu Java và kiểu JDBC cần quy tắc chuyển đổi riêng, `TypeHandler` là điểm mở rộng phù hợp.

Điều MyBatis đặt ở trung tâm vẫn là câu SQL. Framework không tự suy ra đầy đủ các câu CRUD và toàn bộ quan hệ miền chỉ từ một lớp Java có các trường dữ liệu.

### ORM: ánh xạ và quản lý mô hình đối tượng

ORM là viết tắt của Object-Relational Mapping. Một ORM như Hibernate ánh xạ entity và quan hệ giữa các entity sang mô hình quan hệ. Ngoài ánh xạ dữ liệu, ORM thường cung cấp persistence context, quản lý định danh đối tượng, theo dõi thay đổi và cơ chế đồng bộ trạng thái với cơ sở dữ liệu.

Cần phân biệt hai tên thường đi cùng nhau:

- **Jakarta Persistence, thường gọi là JPA:** đặc tả API và hành vi cho persistence dựa trên entity.
- **Hibernate ORM:** một triển khai phổ biến của JPA, đồng thời có các API và khả năng riêng.

JPA không phải tên của một JDBC driver, và ORM không đồng nghĩa với việc lập trình viên không bao giờ viết truy vấn. Bạn vẫn có thể viết JPQL, Criteria hoặc native SQL tùy nhu cầu và khả năng của công cụ.

### Quan hệ với JDBC

Trong ứng dụng Java truy cập cơ sở dữ liệu quan hệ qua JDBC, các lớp thường được tổ chức như sau:

```text
JDBC trực tiếp: Java -> JDBC API -> JDBC driver -> cơ sở dữ liệu
MyBatis:       Java -> Mapper / SqlSession -> JDBC -> driver -> cơ sở dữ liệu
JPA/Hibernate: Java -> EntityManager / ORM -> JDBC -> driver -> cơ sở dữ liệu
```

Vì vậy, chọn MyBatis hay Hibernate không có nghĩa là loại bỏ JDBC khỏi nền tảng. Bạn đang chọn mức trừu tượng và trách nhiệm mà framework đảm nhận phía trên JDBC.

## 2. Một yêu cầu chung để so sánh

Giả sử hệ thống bán hàng có bảng `product`. Ví dụ DDL dưới đây dùng cú pháp phù hợp với PostgreSQL; khi đổi hệ quản trị, cần kiểm tra kiểu dữ liệu và cú pháp tương ứng.

```sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(19, 2) NOT NULL,
    active BOOLEAN NOT NULL
);
```

Ứng dụng cần hai thao tác:

1. Lấy `id`, `name`, `price` của sản phẩm đang hoạt động và có giá ít nhất bằng `minPrice`, sắp xếp theo `id` giảm dần.
2. Đổi giá của một sản phẩm theo `id`.

SQL cho thao tác đọc là:

```sql
SELECT id, name, price
FROM product
WHERE active = TRUE
  AND price >= ?
ORDER BY id DESC;
```

Ta dùng `BigDecimal` cho giá để phù hợp với dữ liệu thập phân chính xác. Một DTO chung cho kết quả đọc có thể được định nghĩa như sau:

```java
package example.lesson;

import java.math.BigDecimal;

public class ProductView {
    private Long id;
    private String name;
    private BigDecimal price;

    public ProductView() {
    }

    public ProductView(Long id, String name, BigDecimal price) {
        this.id = id;
        this.name = name;
        this.price = price;
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }
}
```

Các đoạn mã tiếp theo minh họa phần truy cập dữ liệu. Ứng dụng cung cấp JDBC driver, `DataSource` hoặc cấu hình persistence tương ứng. Những đối tượng như `Connection`, `SqlSessionFactory` và `EntityManager` phải được tạo, cấu hình và quản lý vòng đời tại lớp hạ tầng của ứng dụng.

## 3. Triển khai bằng JDBC trực tiếp

Với JDBC, mã ứng dụng viết SQL, gán tham số và chuyển từng dòng kết quả thành DTO:

```java
package example.lesson;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public class ProductJdbcRepository {
    public List<ProductView> findActiveProducts(
            Connection connection, BigDecimal minPrice) throws SQLException {
        String sql = "SELECT id, name, price FROM product "
                + "WHERE active = TRUE AND price >= ? ORDER BY id DESC";

        List<ProductView> products = new ArrayList<>();
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setBigDecimal(1, minPrice);
            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    products.add(new ProductView(
                            rows.getLong("id"),
                            rows.getString("name"),
                            rows.getBigDecimal("price")));
                }
            }
        }
        return products;
    }

    public int changePrice(Connection connection, Long id,
                           BigDecimal newPrice) throws SQLException {
        String sql = "UPDATE product SET price = ? WHERE id = ?";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setBigDecimal(1, newPrice);
            statement.setLong(2, id);
            return statement.executeUpdate();
        }
    }
}
```

Phương thức nhận `Connection` từ bên ngoài nên chỉ đóng statement và result set mà nó tạo. Bên cấp kết nối quyết định lúc đóng connection và lúc kết thúc giao dịch. Cách phân chia này cho phép nhiều thao tác repository cùng tham gia một giao dịch.

Ở đây, `id` là khóa chính không null nên `getLong("id")` phù hợp. Nếu cột số có thể null, việc đọc thành kiểu primitive cần xử lý thêm, chẳng hạn kiểm tra `wasNull()`. Đây là một ví dụ về chi tiết ánh xạ mà JDBC trực tiếp để lập trình viên tự chịu trách nhiệm.

Điểm đáng chú ý:

- Tham số `minPrice` tương ứng vị trí `1` trong câu SELECT.
- Kết quả được đọc từng hàng bằng vòng lặp.
- Việc thay đổi cấu trúc DTO hoặc cột trả về có thể kéo theo sửa mã ánh xạ.
- `changePrice()` chỉ thực thi UPDATE và trả số hàng bị tác động; phương thức không tự commit.
- Một lời gọi `productView.setPrice(...)` sau khi SELECT chỉ thay đổi đối tượng trong bộ nhớ, không tạo UPDATE.

JDBC trực tiếp phù hợp khi cần thao tác ở mức thấp hoặc có lượng SQL nhỏ, nhưng khi số truy vấn tăng, mã đóng tài nguyên, binding và mapping dễ lặp lại. Có thể tự xây các hàm dùng chung, song lúc đó nhóm phát triển đang tự tạo một phần lớp trừu tượng truy cập dữ liệu.

## 4. Triển khai bằng MyBatis

### 4.1. Khai báo Mapper

Mapper mô tả hợp đồng truy cập dữ liệu bằng phương thức Java:

```java
package example.lesson;

import java.math.BigDecimal;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface ProductMapper {
    List<ProductView> findActiveProducts(
            @Param("minPrice") BigDecimal minPrice);

    int changePrice(@Param("id") Long id,
                    @Param("newPrice") BigDecimal newPrice);
}
```

`@Param` đặt tên rõ ràng cho tham số để SQL tham chiếu bằng `#{minPrice}`, `#{id}` và `#{newPrice}`. Bạn không cần tự cài đặt interface này theo cách viết lớp repository JDBC ở trên; MyBatis tạo proxy Mapper dựa trên cấu hình đã đăng ký.

### 4.2. Viết SQL và ánh xạ kết quả

Một mapper XML tương ứng:

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE mapper
  PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
  "https://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="example.lesson.ProductMapper">

    <resultMap id="productViewMap" type="example.lesson.ProductView">
        <id property="id" column="id"/>
        <result property="name" column="name"/>
        <result property="price" column="price"/>
    </resultMap>

    <select id="findActiveProducts" resultMap="productViewMap">
        SELECT id, name, price
        FROM product
        WHERE active = TRUE
          AND price &gt;= #{minPrice}
        ORDER BY id DESC
    </select>

    <update id="changePrice">
        UPDATE product
        SET price = #{newPrice}
        WHERE id = #{id}
    </update>

</mapper>
```

`namespace` khớp tên đầy đủ của interface; `id` của statement khớp tên phương thức. Mapper XML cần được nạp trong cấu hình MyBatis, và interface cần được đăng ký theo cách phù hợp với môi trường chạy. Ví dụ, nếu XML nằm tại tài nguyên `example/lesson/ProductMapper.xml`, cấu hình MyBatis thuần có thể khai báo tài nguyên đó trong phần `mappers`:

```xml
<mappers>
    <mapper resource="example/lesson/ProductMapper.xml"/>
</mappers>
```

Trong Spring Boot, việc quét mapper và nạp mapper XML thường được thiết lập qua tích hợp MyBatis với Spring. Chỉ tạo hai tệp Java và XML nhưng không đăng ký hoặc không nạp chúng thì chưa đủ để gọi Mapper.

`resultMap` thể hiện rõ cột nào đi vào thuộc tính nào. Với DTO có constructor không tham số và setter như ví dụ, MyBatis có thể dựng đối tượng và gán các giá trị. MyBatis cũng hỗ trợ ánh xạ tự động hoặc ánh xạ constructor trong những cấu hình phù hợp; `resultMap` hữu ích khi cần minh bạch hoặc khi tên, kiểu dữ liệu và cấu trúc kết quả phức tạp.

`<id>` trong `resultMap` đánh dấu thành phần định danh khi MyBatis ánh xạ kết quả, đặc biệt hữu ích với cấu trúc lồng nhau. Nó không tự tạo khóa chính trong cơ sở dữ liệu hay biến DTO thành một entity được theo dõi thay đổi.

### 4.3. Gọi Mapper qua SqlSession

Với MyBatis thuần, ứng dụng có thể mở session từ factory đã được cấu hình:

```java
try (SqlSession session = sqlSessionFactory.openSession()) {
    ProductMapper mapper = session.getMapper(ProductMapper.class);
    List<ProductView> products =
            mapper.findActiveProducts(new BigDecimal("100000.00"));
    // Dùng danh sách kết quả trong phạm vi nghiệp vụ cần thiết.
}
```

Đoạn mã này dùng `org.apache.ibatis.session.SqlSession`, `java.util.List` và `java.math.BigDecimal`. `SqlSessionFactory` thường được tạo để dùng lâu dài; một `SqlSession` cụ thể gắn với một đơn vị công việc và không được dùng chung tùy tiện giữa nhiều luồng.

So với JDBC trực tiếp, phần Java không còn tự duyệt `ResultSet` hay gán từng tham số lên statement. Tuy nhiên, câu SELECT vẫn do bạn viết. Khi yêu cầu thay đổi, chẳng hạn bổ sung JOIN hoặc tối ưu điều kiện lọc, bạn tiếp tục làm việc trực tiếp với SQL.

### 4.4. MyBatis trả đối tượng nhưng không tự theo dõi thay đổi

Giả sử gọi:

```java
ProductView product = products.get(0);
product.setPrice(new BigDecimal("120000.00"));
```

Thao tác này chỉ đổi giá trị trong bộ nhớ. MyBatis không tự so sánh trạng thái cũ, mới của DTO để phát sinh UPDATE khi commit. Muốn lưu giá mới, ứng dụng phải gọi statement cập nhật, ví dụ `mapper.changePrice(product.getId(), product.getPrice())`.

MyBatis hỗ trợ `association`, `collection` và các kỹ thuật ánh xạ quan hệ trong kết quả truy vấn. Khả năng đó không đồng nghĩa với việc framework tự quản lý toàn bộ vòng đời đồ thị entity như một ORM.

## 5. Triển khai theo mô hình JPA/Hibernate

### 5.1. Ánh xạ entity

Một entity tối giản cho cùng bảng có thể được khai báo như sau:

```java
package example.lesson;

import java.math.BigDecimal;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "product")
public class ProductEntity {
    @Id
    private Long id;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    protected ProductEntity() {
    }

    public void changePrice(BigDecimal newPrice) {
        this.price = newPrice;
    }
}
```

Ví dụ dùng package `jakarta.persistence`. Annotation được đặt trên trường nên provider truy cập dữ liệu theo trường; các phương thức getter không cần xuất hiện chỉ để phục vụ đoạn ánh xạ này. Bảng được giả định đã tồn tại; annotation không phải cam kết rằng hệ thống tự tạo hoặc tự di trú schema.

### 5.2. Truy vấn theo entity và thuộc tính

Để đọc cùng DTO, có thể dùng JPQL constructor projection:

```java
List<ProductView> products = entityManager.createQuery(
        "select new example.lesson.ProductView(p.id, p.name, p.price) "
        + "from ProductEntity p "
        + "where p.active = true and p.price >= :minPrice "
        + "order by p.id desc",
        ProductView.class)
    .setParameter("minPrice", new BigDecimal("100000.00"))
    .getResultList();
```

`ProductEntity` và `p.price` là tên entity và thuộc tính Java. Provider chuyển truy vấn này thành SQL theo mapping và dialect cơ sở dữ liệu. Constructor public của `ProductView` phải phù hợp với các giá trị được chọn.

Đây là một khác biệt với MyBatis: ở ví dụ MyBatis, bạn viết trực tiếp tên bảng, tên cột trong SQL; ở JPQL, bạn truy vấn mô hình entity. ORM vẫn cho phép native SQL khi cần làm việc trực tiếp với cú pháp cơ sở dữ liệu.

Cần lưu ý rằng kết quả ở trên là **DTO projection**. Dù truy vấn được thực hiện qua JPA, `ProductView` không trở thành managed entity. Gọi setter trên DTO này cũng không khiến ORM tự cập nhật bảng.

### 5.3. Theo dõi thay đổi áp dụng cho managed entity

Khác biệt về vòng đời xuất hiện khi entity được nạp và còn nằm trong persistence context. Ví dụ sau giả định `EntityManager` đang mở, dùng giao dịch resource-local và entity được tìm thấy:

```java
EntityTransaction transaction = entityManager.getTransaction();
transaction.begin();
try {
    ProductEntity product = entityManager.find(ProductEntity.class, 10L);
    if (product == null) {
        throw new IllegalArgumentException("Không tìm thấy sản phẩm");
    }

    product.changePrice(new BigDecimal("120000.00"));
    transaction.commit();
} catch (RuntimeException exception) {
    if (transaction.isActive()) {
        transaction.rollback();
    }
    throw exception;
}
```

`EntityTransaction` thuộc `jakarta.persistence`. Trong điều kiện managed entity thông thường, provider phát hiện thay đổi và đồng bộ UPDATE khi flush, thường trong quá trình commit. Ví dụ không gọi một phương thức UPDATE riêng cho từng trường thay đổi.

Hành vi này có điều kiện: đối tượng phải là entity đang được quản lý trong persistence context thích hợp. Entity đã detached, DTO hoặc đối tượng vừa tự tạo bằng `new` không tự được theo dõi chỉ vì lớp của nó có hình dáng giống entity.

Ví dụ resource-local nhằm minh họa cơ chế. Trong môi trường Spring hoặc giao dịch do container quản lý, ranh giới giao dịch thường được khai báo và điều khiển bởi hạ tầng tương ứng, không sao chép nguyên cách gọi `getTransaction()` này.

## 6. Bảng so sánh theo trách nhiệm

| Tiêu chí | JDBC trực tiếp | MyBatis | ORM theo JPA/Hibernate |
|---|---|---|---|
| Điểm xuất phát | Connection, statement và SQL | Phương thức Mapper gắn với SQL | Entity, mapping và persistence context |
| Ai viết SQL? | Lập trình viên | Lập trình viên viết SQL tĩnh hoặc mô tả cách sinh SQL động | Provider sinh nhiều SQL từ thao tác entity, JPQL hoặc Criteria; vẫn có native SQL |
| Gán tham số | Tự gọi `setXxx()` theo vị trí | MyBatis binding từ tham số Mapper | Provider binding tham số truy vấn và giá trị entity |
| Ánh xạ kết quả | Tự đọc `ResultSet` và dựng đối tượng | `resultMap`, ánh xạ tự động, constructor và TypeHandler | Mapping entity hoặc projection theo truy vấn |
| Thay đổi đối tượng sau khi đọc | Không tự tạo UPDATE | Không tự tạo UPDATE | Có thể tự tạo UPDATE với managed entity khi flush |
| Quan hệ nhiều bảng | Tự JOIN, gom nhóm và dựng cấu trúc | JOIN hoặc truy vấn lồng, ánh xạ `association`/`collection` | Mapping quan hệ entity và kế hoạch fetch |
| Theo dõi vòng đời entity | Không có sẵn | Không có cơ chế ORM đầy đủ | Có persistence context và trạng thái entity |
| Cache | Ứng dụng hoặc lớp khác tự cung cấp | Cache cấp session; cache cấp namespace có thể cấu hình | Persistence context có bộ nhớ định danh; cache cấp hai tùy provider và cấu hình |
| Batch | `addBatch()` / `executeBatch()` | Có chế độ executor cho batch | Có thể cấu hình batching; hiệu quả phụ thuộc mapping và provider |
| Phụ thuộc dialect | SQL do bạn viết phụ thuộc hệ quản trị | SQL do bạn viết phụ thuộc hệ quản trị | Dialect xử lý nhiều khác biệt, nhưng native SQL và tính năng riêng vẫn có giới hạn |
| Tài nguyên và giao dịch | Ứng dụng hoặc transaction manager điều phối | SqlSession hoặc tích hợp Spring phối hợp | EntityManager và transaction manager phối hợp |

Không nên đọc bảng này như một bảng xếp hạng. Ví dụ, ít mã ánh xạ hơn không tự bảo đảm truy vấn tốt hơn; kiểm soát SQL nhiều hơn cũng không tự bảo đảm lập trình viên đã chọn đúng index hoặc đúng ranh giới giao dịch.

## 7. Giao dịch: cùng yêu cầu nghiệp vụ, khác cách điều phối

Giả sử đổi giá sản phẩm phải đi cùng thao tác ghi lịch sử. Cả hai câu lệnh cần thành công hoặc cùng rollback. Dù dùng cách tiếp cận nào, đây vẫn là một yêu cầu giao dịch của cơ sở dữ liệu.

### JDBC trực tiếp

Ở JDBC thuần, bên sở hữu connection có thể tắt auto-commit, gọi các thao tác trên cùng connection rồi commit hoặc rollback. Repository nhận connection như ví dụ ở trên không được tự đóng connection hoặc tự commit giữa chừng nếu giao dịch thuộc về lớp service.

Nếu mỗi repository tự mở một connection khác nhau, hai thao tác không tự trở thành một giao dịch chỉ vì chúng được gọi liên tiếp trong cùng một phương thức Java.

### MyBatis thuần

`sqlSessionFactory.openSession()` mặc định mở session không auto-commit. Một thao tác ghi cần được commit tại ranh giới phù hợp. Ví dụ tối giản cho một lần đổi giá:

```java
try (SqlSession session = sqlSessionFactory.openSession()) {
    try {
        ProductMapper mapper = session.getMapper(ProductMapper.class);
        int changedRows = mapper.changePrice(
                10L, new BigDecimal("120000.00"));
        if (changedRows != 1) {
            throw new IllegalStateException("Sản phẩm không tồn tại");
        }
        session.commit();
    } catch (RuntimeException exception) {
        session.rollback();
        throw exception;
    }
}
```

Việc kiểm tra số hàng bị tác động có ý nghĩa nghiệp vụ: một UPDATE chạy không lỗi nhưng không khớp bản ghi nào vẫn có thể không đáp ứng yêu cầu. Trong hệ thống dùng batch, thời điểm thực thi và nhận số hàng cập nhật có đặc điểm khác, cần xử lý theo chế độ executor đang dùng.

Đóng session không thay thế cho quyết định commit nghiệp vụ. Nếu cần ghi thêm lịch sử, thao tác đó phải được đặt vào cùng đơn vị giao dịch trước commit.

### Khi tích hợp Spring Boot

Với tích hợp MyBatis-Spring, Mapper thường được inject và `SqlSessionTemplate` phối hợp session theo giao dịch Spring. Lớp service có thể xác định ranh giới bằng `@Transactional`, với transaction manager và `DataSource` được cấu hình phù hợp.

Trong mô hình đó, không tự gọi `commit()`, `rollback()` hoặc `close()` trên session do Spring quản lý như ví dụ MyBatis thuần. Tương tự, ORM hoặc JDBC tham gia giao dịch Spring phải lấy tài nguyên qua cơ chế tích hợp thích hợp. Việc tự lấy một connection không được gắn với giao dịch có thể làm mất tính nguyên tử mà service mong đợi.

Các lựa chọn trên không tự giải quyết mất cập nhật khi nhiều giao dịch sửa cùng một sản phẩm. Khóa, mức cô lập, điều kiện UPDATE và optimistic locking là các thiết kế riêng. ORM có thể hỗ trợ optimistic locking qua mapping phiên bản; với MyBatis hoặc JDBC, bạn có thể chủ động thể hiện điều kiện phiên bản trong SQL và kiểm tra số hàng cập nhật.

## 8. SQL động, cache và quan hệ: tránh hiểu nhầm về mức tự động hóa

### SQL động vẫn là SQL do ứng dụng định nghĩa

Khi bộ lọc tìm kiếm có nhiều điều kiện tùy chọn, JDBC trực tiếp thường cần ghép các mảnh SQL và đồng thời quản lý danh sách tham số. MyBatis hỗ trợ các thành phần như `if`, `where`, `choose` và `foreach` để mô tả quá trình tạo SQL.

Ví dụ, nếu cho phép bỏ qua điều kiện giá:

```xml
<select id="findActiveProducts" resultMap="productViewMap">
    SELECT id, name, price
    FROM product
    <where>
        active = TRUE
        <if test="minPrice != null">
            AND price &gt;= #{minPrice}
        </if>
    </where>
    ORDER BY id DESC
</select>
```

Đây là **phiên bản thay thế** cho SELECT cùng `id` ở ví dụ trước, không thêm đồng thời hai statement trùng tên. Nó minh họa việc MyBatis hỗ trợ dựng SQL; không có nghĩa framework tự biết bộ lọc nghiệp vụ nào nên tồn tại. Khi thay đổi hợp đồng để cho phép `minPrice` null, cần kiểm thử cả nhánh có và không có điều kiện giá.

### Binding tham số khác với chèn văn bản

Trong các ví dụ MyBatis, `#{minPrice}` được binding thành tham số JDBC, tương tự dấu `?` trong `PreparedStatement`. `${...}` là thay thế văn bản trực tiếp vào SQL, không có cùng cơ chế binding giá trị.

Không nhận tùy ý nội dung từ người dùng để chèn qua `${...}`. Với tên cột hoặc chiều sắp xếp không thể binding như một giá trị, hãy ánh xạ lựa chọn đầu vào sang tập tên cột và hướng sắp xếp được cho phép. JDBC và ORM cũng cần nguyên tắc tương tự khi ứng dụng tự ghép SQL hoặc ngôn ngữ truy vấn.

### Có ánh xạ quan hệ chưa đủ để tránh N+1

Giả sử cần lấy 100 đơn hàng cùng tên khách hàng:

- Một truy vấn lấy danh sách đơn hàng, sau đó một truy vấn riêng cho khách của từng đơn có thể tạo mô hình 1 + N truy vấn.
- Một JOIN phù hợp hoặc cách nạp theo lô có thể giảm số lần đi tới cơ sở dữ liệu, nhưng cần xem số hàng trả về và dữ liệu bị lặp.

MyBatis có thể phát sinh N+1 nếu thiết kế nested select không phù hợp. ORM có thể gặp N+1 do cách fetch quan hệ. JDBC trực tiếp cũng có thể gặp nếu mã Java gọi SELECT trong vòng lặp. Vấn đề nằm ở cách truy cập dữ liệu thực tế, không chỉ ở tên framework.

### Cache không phải cơ chế theo dõi thay đổi

Cache cấp session của MyBatis có thể tái sử dụng kết quả truy vấn trong những điều kiện thích hợp; phạm vi và hành vi phụ thuộc cấu hình, khóa cache và các thao tác làm mất hiệu lực. Cache cấp namespace cần được cấu hình, không nên mặc định coi mọi Mapper đều đã có cache cấp hai.

Việc session có thể giữ hoặc tái sử dụng kết quả không khiến MyBatis trở thành ORM có dirty checking. Bạn vẫn phải gọi UPDATE để ghi thay đổi DTO.

Với ORM, persistence context quản lý định danh entity và trạng thái của chúng. Đây cũng không phải một cache truy vấn tổng quát cho mọi truy vấn. Không nên giả định rằng gọi hai truy vấn bất kỳ sẽ luôn tránh được lần truy cập cơ sở dữ liệu thứ hai.

## 9. Hiệu năng cần được đánh giá bằng điều gì?

Nhận định “JDBC luôn nhanh nhất”, “MyBatis luôn nhanh hơn ORM” hoặc “ORM luôn chậm” đều bỏ qua hoàn cảnh thực thi.

Một lần gọi lấy sản phẩm có thể chịu chi phí từ:

- Kế hoạch thực thi, index, phép JOIN, sắp xếp và lượng hàng phải quét.
- Số lần trao đổi với cơ sở dữ liệu và độ trễ mạng.
- Số cột, số hàng được chuyển về, rồi chi phí dựng đối tượng.
- Cách dùng connection pool, giao dịch, khóa và thời gian giữ kết nối.
- Cơ chế fetch, cache, flush và batch đang hoạt động.

Nếu JDBC và MyBatis thực thi cùng SQL với cùng tham số trên cùng dữ liệu, phần công việc tại cơ sở dữ liệu có thể rất giống nhau. Khác biệt còn lại ở lớp Java vẫn có thể đáng đo, nhưng không thể suy ra mức chênh lệch chỉ từ số dòng mã.

ORM có thể giúp viết nghiệp vụ ngắn gọn, nhưng một kế hoạch fetch gây N+1 sẽ làm tăng số truy vấn. MyBatis cho phép nhìn rõ SQL, nhưng một câu SQL không dùng được index vẫn có thể chậm. Batch của cả ba hướng cũng cần được kiểm chứng cùng driver và cơ sở dữ liệu thực tế.

Khi đánh giá một phương án, hãy xác nhận SQL và tham số thực tế, số statement, số hàng trả về và kế hoạch thực thi. Sau đó đo với khối lượng dữ liệu và ranh giới giao dịch gần với nhu cầu của ứng dụng.

## 10. Chọn cách tiếp cận theo tình huống

| Tình huống | Hướng đáng cân nhắc | Lý do cần kiểm tra |
|---|---|---|
| Công cụ nhỏ chỉ có vài thao tác SQL và cần kiểm soát API JDBC chi tiết | JDBC trực tiếp | Phần mã lặp còn ít; nhóm chấp nhận tự quản lý binding, mapping và tài nguyên |
| Hệ thống có schema sẵn, nhiều truy vấn báo cáo, JOIN và tính năng SQL riêng của hệ quản trị | MyBatis | SQL là phần thiết kế trọng tâm; cần ánh xạ nhiều kiểu kết quả về DTO |
| Ứng dụng có nhiều entity và quan hệ, nhiều cập nhật theo trạng thái đối tượng | ORM | Cần đánh giá lợi ích từ persistence context, dirty checking và mapping quan hệ |
| Một số luồng đơn giản, một số truy vấn phân tích rất đặc thù | Có thể kết hợp | Cần ranh giới rõ về giao dịch, chủ sở hữu thao tác ghi và tính nhất quán dữ liệu |

Những tình huống này là điểm xuất phát để phân tích, không phải quy tắc cứng. MyBatis vẫn làm CRUD tốt; ORM vẫn thực hiện truy vấn báo cáo hoặc native SQL được; JDBC vẫn có thể dùng trong hệ thống lớn nếu có kiến trúc phù hợp.

Nếu kết hợp MyBatis và JPA để sửa cùng dữ liệu, hãy nhớ rằng một UPDATE qua MyBatis không tự cập nhật entity đang có trong persistence context của JPA. Ứng dụng cần điều phối thứ tự flush, việc refresh hoặc clear phù hợp và cache liên quan. Không gọi clear tùy tiện khi còn thay đổi entity chưa được xử lý vì các entity sẽ bị detach. Cùng một `DataSource` cũng chưa đủ để chứng minh hai cơ chế đã cùng tham gia một giao dịch.

Một quyết định có cơ sở nên trả lời được: nhóm muốn làm việc chủ yếu với câu SQL hay với trạng thái entity; dạng truy vấn nào chiếm phần lớn; ai chịu trách nhiệm kiểm tra SQL, giao dịch và ánh xạ; công cụ nào giúp nhóm thực hiện các trách nhiệm đó rõ ràng nhất.

## 11. Các nhận định cần phân biệt

| Nhận định | Cách hiểu chính xác hơn |
|---|---|
| “MyBatis thay thế JDBC.” | MyBatis giảm mã JDBC lặp lại và thường thực thi thông qua JDBC ở bên dưới. |
| “Có ánh xạ đối tượng là có đầy đủ ORM.” | Ánh xạ hàng dữ liệu về đối tượng khác với quản lý vòng đời và theo dõi thay đổi của entity. |
| “Dùng Hibernate thì không viết truy vấn.” | Vẫn cần thiết kế JPQL, Criteria, native SQL và kế hoạch fetch phù hợp. |
| “Sửa DTO rồi commit là MyBatis tự lưu.” | MyBatis cần statement INSERT, UPDATE hoặc DELETE được gọi rõ ràng. |
| “Mọi đối tượng do JPA trả về đều tự lưu thay đổi.” | DTO projection không phải managed entity; entity detached cũng không tự được dirty checking trong context cũ. |
| “SQL viết tay chắc chắn tối ưu.” | Cần kiểm tra kế hoạch thực thi, index, lượng dữ liệu và số lần truy cập. |
| “Có Spring Boot thì giao dịch tự đúng.” | Cần cấu hình hạ tầng và ranh giới giao dịch phù hợp, đồng thời bảo đảm tài nguyên thực sự tham gia giao dịch đó. |

## 12. Tự kiểm tra qua các quyết định nhỏ

### Tình huống 1: Cần đổi tên cột trong SELECT

Truy vấn trả `product_name` trong khi DTO có thuộc tính `name`. Phần nào chịu trách nhiệm ánh xạ?

- Với JDBC trực tiếp, sửa mã đọc cột và gán vào đối tượng.
- Với MyBatis, khai báo `column="product_name"` và `property="name"` trong `resultMap`, hoặc dùng alias SQL phù hợp khi chọn cách ánh xạ tự động.
- Với ORM, phân biệt cột của entity với alias hoặc kiểu projection đang dùng; JPQL làm việc theo tên thuộc tính entity, còn native SQL có yêu cầu ánh xạ kết quả riêng.

### Tình huống 2: Danh sách sản phẩm đã đọc bị đổi giá trong Java

Bạn gọi setter trên `ProductView` của các ví dụ. Có công cụ nào tự ghi giá mới không?

Không có trong cả ba ví dụ đọc DTO này. JDBC và MyBatis cần lệnh cập nhật rõ ràng; JPA constructor projection cũng trả DTO. Muốn minh họa dirty checking của ORM, cần làm việc với managed entity như ví dụ `entityManager.find(...)` trong giao dịch.

### Tình huống 3: Truy vấn chậm sau khi bổ sung thông tin liên quan

Không nên đổi framework ngay. Trước tiên xác định có truy vấn trong vòng lặp hay không, số statement thực thi, số hàng được trả về, điều kiện JOIN và kế hoạch thực thi. Sau đó chọn cách sửa phù hợp với công cụ đang dùng.

### Tình huống 4: Chọn MyBatis cho module này

Bạn cần chủ động thiết kế SQL và ánh xạ nhất quán sang Java. Hướng học tiếp theo là nắm hợp đồng Mapper, vòng đời `SqlSession`, binding tham số, `resultMap`, SQL động và `TypeHandler`. Khi phần ánh xạ đã rõ, hãy nối chúng với giao dịch, cache, batch và tích hợp Spring Boot, rồi kiểm chứng bằng kiểm thử truy vấn cùng tối ưu trên cơ sở dữ liệu mục tiêu.