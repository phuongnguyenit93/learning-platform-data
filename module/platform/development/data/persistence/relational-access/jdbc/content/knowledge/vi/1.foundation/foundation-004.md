# Phân biệt JDBC thuần, Spring JDBC, MyBatis và ORM

**JDBC** (*Java Database Connectivity*) là API chuẩn trong Java để làm việc với cơ sở dữ liệu quan hệ: mở kết nối, gửi SQL, truyền tham số, xử lý kết quả và quản lý giao dịch. Khi xây dựng một ứng dụng Java, ta có thể dùng trực tiếp JDBC hoặc đặt thêm một thư viện lên trên để giảm mã lặp và tổ chức truy cập dữ liệu.

Trong chương **Nền tảng**, bài này so sánh bốn lựa chọn thường gặp: **JDBC thuần**, **Spring JDBC**, **MyBatis** và **ORM** (minh họa bằng **JPA/Hibernate**). Mục đích là hiểu mỗi công cụ làm thay phần nào, phần nào lập trình viên vẫn phải chịu trách nhiệm, và chọn công cụ dựa trên mô hình dữ liệu cùng kiểu truy vấn của ứng dụng.

Sau bài học, bạn có thể:

- Giải thích mối quan hệ giữa JDBC, framework truy cập dữ liệu và driver JDBC.
- So sánh quyền kiểm soát SQL, cách ánh xạ hàng dữ liệu thành đối tượng Java và cách quản lý transaction.
- Đọc một truy vấn giống nhau khi viết bằng bốn phương án.
- Phân biệt JPA với Hibernate, Spring JDBC với Spring Data JDBC, và MyBatis với ORM.
- Chọn cách triển khai cho CRUD, truy vấn báo cáo, quan hệ phức tạp và hệ thống yêu cầu hiệu năng.

## 1. JDBC là tầng nền, không chỉ là một cách viết DAO

Ở ứng dụng Java dùng cơ sở dữ liệu quan hệ thông thường, các thư viện khác nhau có thể cùng sử dụng JDBC driver để giao tiếp với database:

```text
                         ỨNG DỤNG JAVA
                               |
          +--------------------+--------------------+
          |                    |                    |
       JDBC thuần         Spring JDBC        MyBatis hoặc ORM
          |                    |                    |
          +--------------------+--------------------+
                               |
                          JDBC API
                               |
                         JDBC driver
                               |
                    Database quan hệ
```

Sơ đồ mô tả cách triển khai phổ biến; nó không khẳng định mọi hệ thống ORM đều chỉ có một kiểu giao tiếp nội bộ. Các thành phần đảm nhận trách nhiệm khác nhau:

- **JDBC API** định nghĩa các kiểu như `Connection`, `PreparedStatement`, `ResultSet` và `SQLException`.
- **Driver JDBC** triển khai giao thức và quy tắc của database cụ thể, ví dụ PostgreSQL hoặc MySQL.
- **Spring JDBC** cung cấp template để thực thi JDBC và đóng tài nguyên theo mẫu nhất quán.
- **MyBatis** gắn SQL do lập trình viên viết với phương thức mapper và đối tượng Java.
- **ORM** ánh xạ mô hình đối tượng và quan hệ giữa các đối tượng sang dữ liệu quan hệ; trong Java, JPA/Hibernate là tổ hợp rất phổ biến.

Vì đều có thể chạy qua JDBC driver, việc đổi từ JDBC thuần sang ORM **không loại bỏ** nhu cầu hiểu SQL, index, transaction, khóa và kế hoạch thực thi truy vấn. Nó thay đổi nơi viết SQL và ai quản lý trạng thái đối tượng.

## 2. Bảng so sánh nhanh

| Tiêu chí | JDBC thuần | Spring JDBC | MyBatis | ORM (JPA/Hibernate) |
|---|---|---|---|---|
| Ai viết SQL thường ngày? | Lập trình viên | Lập trình viên | Lập trình viên, qua mapper | Framework tạo SQL cho phần lớn CRUD; có JPQL/native SQL khi cần |
| Ai ánh xạ `ResultSet`? | Lập trình viên | `RowMapper` hoặc callback do lập trình viên cung cấp | MyBatis dùng result mapping | ORM dùng metadata entity |
| Quản lý `Connection` và statement | Tự quản lý hoặc dùng helper | Template quản lý trong phạm vi thao tác | `SqlSession` hoặc tích hợp Spring quản lý | `EntityManager` và transaction manager quản lý |
| Có theo dõi thay đổi của entity? | Không | Không | Không theo mô hình persistence context của JPA | Có, với managed entity và dirty checking |
| Quan hệ giữa các bảng | Tự viết JOIN, tự ghép dữ liệu | Tự viết JOIN, tự ghép dữ liệu | Result map, nested mapping, nested select | Annotation quan hệ, fetch plan và truy vấn |
| Điều khiển SQL phức tạp | Rất trực tiếp | Rất trực tiếp | Rất trực tiếp, có dynamic SQL | Làm được nhưng cần hiểu JPQL/native query, fetch và SQL được sinh |
| Độ phức tạp khởi đầu | Ít phụ thuộc, nhiều mã thủ công | Thường ngắn gọn trong ứng dụng Spring | Cần cấu hình mapper và mapping | Cần mô hình entity, lifecycle và persistence context |
| Rủi ro hay gặp | Rò rỉ tài nguyên, lặp mã, SQL injection | Mapping hoặc truy vấn sai, quản lý transaction chưa đúng | Mapper sai, SQL động không an toàn, N+1 do nested select | N+1, fetch dư, flush ngoài dự kiến, cập nhật sai vòng đời entity |
| Nhu cầu phù hợp | Ứng dụng nhỏ, thư viện nền tảng, thao tác đặc thù | SQL minh bạch, CRUD và báo cáo, ứng dụng Spring | Nhiều truy vấn SQL chủ động tối ưu | Mô hình nghiệp vụ giàu quan hệ và vòng đời entity |

Bảng là định hướng, không phải xếp hạng hiệu năng. **Không có công cụ nào mặc nhiên nhanh nhất cho mọi truy vấn**: SQL thực sự gửi đi, index, kích thước kết quả, số lượt round-trip, cấu hình kết nối và cách sử dụng framework thường ảnh hưởng nhiều hơn tên thư viện.

## 3. Cùng một yêu cầu, bốn cách đọc dữ liệu

Giả sử ứng dụng quản lý sản phẩm có bảng sau. Cú pháp tạo bảng là ví dụ SQL thường gặp; kiểu cột và cách tạo khóa cần điều chỉnh theo hệ quản trị:

```sql
CREATE TABLE products (
    id       BIGINT PRIMARY KEY,
    name     VARCHAR(200) NOT NULL,
    price    DECIMAL(12, 2) NOT NULL,
    version  BIGINT NOT NULL DEFAULT 0
);
```

Yêu cầu: **tìm sản phẩm theo ID**, trả về tên, giá tiền và phiên bản bản ghi. `price` dùng `BigDecimal` để giữ giá trị thập phân đúng với kiểu `DECIMAL`. Chọn `DataSource` thay vì hard-code URL/password trong DAO; ứng dụng thực tế thường cấp `DataSource` qua cấu hình và connection pool.

### 3.1. JDBC thuần: kiểm soát trực tiếp toàn bộ vòng đời

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

record Product(long id, String name, BigDecimal price, long version) {}

public final class PlainJdbcProductDao {
    private final DataSource dataSource;

    public PlainJdbcProductDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<Product> findById(long id) throws SQLException {
        String sql =
                "SELECT id, name, price, version FROM products WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, id);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Product(
                        rs.getLong("id"),
                        rs.getString("name"),
                        rs.getBigDecimal("price"),
                        rs.getLong("version")));
            }
        }
    }
}
```

**Điểm nhận diện của JDBC thuần:** mã tự lấy và đóng `Connection`, tự tạo `PreparedStatement`, bind tham số, gọi `executeQuery()`, duyệt `ResultSet` và chuyển cột SQL thành trường Java.

Ưu điểm là ít tầng trừu tượng và dễ xác định câu SQL được chạy. Chi phí là mỗi DAO phải lặp lại quy trình đóng tài nguyên, ánh xạ lỗi, xử lý `NULL` và transaction. Nếu một thao tác nghiệp vụ gồm nhiều lệnh SQL, cần **truyền cùng `Connection`** cho các lệnh trong cùng transaction; việc mỗi hàm DAO tự lấy kết nối mới có thể làm vỡ ranh giới giao dịch.

`PreparedStatement` dùng dấu `?` cho **giá trị** đầu vào, giúp tránh ghép trực tiếp input vào SQL. Dấu `?` không thay được tên bảng hoặc tên cột; các identifier động phải đi qua allowlist.

### 3.2. Spring JDBC: vẫn viết SQL, bớt mã quản lý JDBC

Spring JDBC có `JdbcTemplate` và `NamedParameterJdbcTemplate`. Template thực thi SQL, phối hợp với cơ chế lấy kết nối của Spring, quản lý statement/result set và chuyển các lỗi JDBC thường gặp sang họ `DataAccessException`.

```java
import java.util.List;
import java.util.Map;
import java.util.Optional;
import javax.sql.DataSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

public final class SpringJdbcProductDao {
    private final NamedParameterJdbcTemplate jdbc;

    public SpringJdbcProductDao(DataSource dataSource) {
        this.jdbc = new NamedParameterJdbcTemplate(dataSource);
    }

    public Optional<Product> findById(long id) {
        String sql =
                "SELECT id, name, price, version FROM products WHERE id = :id";

        List<Product> rows = jdbc.query(
                sql,
                Map.of("id", id),
                (rs, rowNum) -> new Product(
                        rs.getLong("id"),
                        rs.getString("name"),
                        rs.getBigDecimal("price"),
                        rs.getLong("version")));

        return rows.stream().findFirst();
    }
}
```

`Product` ở đây là `record` được khai báo trong ví dụ JDBC thuần. Phương thức này trả `Optional.empty()` khi không tìm thấy hàng. Nếu dùng `queryForObject()` để tìm một bản ghi, cần biết rằng API có thể ném ngoại lệ nếu kết quả rỗng hoặc không đúng số hàng dự kiến.

**Điểm nhận diện của Spring JDBC:** SQL vẫn do người viết; kết quả vẫn được ánh xạ chủ động qua `RowMapper`; template loại bỏ phần lặp quanh tài nguyên JDBC. Trong ứng dụng Spring, `@Transactional` kết hợp với transaction manager cấu hình đúng cho `DataSource` giúp nhiều lời gọi template tham gia một giao dịch.

**Spring JDBC khác Spring Data JDBC.** Spring JDBC là tập API thao tác JDBC với template/callback. Spring Data JDBC là một dự án khác, cung cấp repository và ánh xạ aggregate theo cách riêng; không nên xem hai tên này là cùng một thư viện.

### 3.3. MyBatis: SQL là trung tâm, mapper nối SQL với Java

MyBatis cho phép gắn truy vấn vào một interface bằng annotation hoặc XML mapper. Framework bind tham số, chạy SQL và ánh xạ kết quả. Với nhiều hệ thống có câu SQL phức tạp hoặc cần kiểm soát truy vấn từ đầu, cách tổ chức này giúp SQL nằm gần phương thức nghiệp vụ mà không cần tự duyệt `ResultSet`.

Giả sử `ProductRow` là JavaBean có constructor không tham số, các thuộc tính `id`, `name`, `price`, `version` và đầy đủ getter/setter:

```java
import java.math.BigDecimal;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper  // Khi dùng tích hợp MyBatis-Spring
public interface ProductMapper {
    @Select("""
            SELECT id, name, price, version
            FROM products
            WHERE id = #{id}
            """)
    ProductRow findById(@Param("id") long id);

    @Update("""
            UPDATE products
            SET price = #{price}, version = version + 1
            WHERE id = #{id} AND version = #{expectedVersion}
            """)
    int updatePrice(
            @Param("id") long id,
            @Param("price") BigDecimal price,
            @Param("expectedVersion") long expectedVersion);
}
```

**Điểm nhận diện của MyBatis:** SQL nằm rõ trong `@Select`/`@Update` hoặc file XML; tên `#{id}` được MyBatis bind thành tham số của `PreparedStatement`. Với cấu trúc phức tạp, có thể khai báo `resultMap` để ánh xạ tên cột, đối tượng lồng nhau và các quan hệ một-nhiều; mapper XML còn hỗ trợ các thẻ điều kiện, vòng lặp và SQL động.

MyBatis **không phải ORM theo mô hình persistence context của JPA**: lấy một POJO về, sửa trường của nó rồi kết thúc phương thức **không tự động** có nghĩa là database được cập nhật. Phải thực thi `UPDATE` rõ ràng (hoặc gọi mapper cập nhật). Các quan hệ có thể được ánh xạ bằng result map hoặc nhiều câu truy vấn, nhưng không có cùng cơ chế dirty checking/unit of work như JPA.

MyBatis độc lập quản lý `SqlSession` và transaction theo cách riêng. Khi tích hợp Spring, thường dùng `SqlSessionTemplate`/MyBatis-Spring để tham gia transaction Spring; tránh tự mở và commit các session ngoài cơ chế đó nếu muốn một giao dịch thống nhất.

**Cẩn thận với SQL động:** `#{value}` là parameter binding; cú pháp `${value}` chèn văn bản trực tiếp vào SQL và có thể gây SQL injection nếu giá trị đến từ người dùng. Với tên cột hay hướng sắp xếp, phải chọn từ danh sách được phép.

### 3.4. ORM: làm việc qua entity và persistence context

ORM (*Object-Relational Mapping*) ánh xạ lớp/đối tượng Java với bảng/hàng, đồng thời có thể quản lý trạng thái entity và quan hệ của chúng. Trong hệ Java:

- **JPA** (*Jakarta Persistence*) là đặc tả API và mô hình ánh xạ.
- **Hibernate ORM** là một triển khai JPA phổ biến, đồng thời có API mở rộng riêng.
- **Spring Data JPA** hỗ trợ lớp repository dựa trên JPA; nó không đồng nghĩa với bản thân JPA hay Hibernate.

Ví dụ entity tương ứng với bảng `products`:

```java
import java.math.BigDecimal;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "products")
public class ProductEntity {
    @Id
    private Long id;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Version
    private long version;

    protected ProductEntity() {} // JPA cần constructor không tham số

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }
}
```

Đoạn trên dùng **ID được ứng dụng gán trước** để khớp DDL minh họa. Nếu database tự sinh khóa, có thể dùng `@GeneratedValue` theo chiến lược phù hợp và thay đổi DDL tương ứng.

Trong một service Spring đã cấu hình JPA và transaction manager:

```java
import java.math.BigDecimal;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductPriceService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void changePrice(long id, BigDecimal newPrice) {
        ProductEntity entity = entityManager.find(ProductEntity.class, id);
        if (entity == null) {
            throw new IllegalArgumentException("Không tìm thấy sản phẩm");
        }
        entity.setPrice(newPrice);
        // Entity đang được quản lý; ORM sẽ đồng bộ thay đổi khi flush.
    }
}
```

**Điểm nhận diện của ORM:** `EntityManager.find()` tải entity vào *persistence context*. Khi entity ở trạng thái **managed**, thay đổi trường có thể được ORM phát hiện bằng *dirty checking* và chuyển thành SQL `UPDATE` lúc *flush*, thường trước khi transaction hoàn tất. Không phải mọi lời gọi setter đều sinh SQL ngay lập tức. Với đối tượng **detached** hoặc ngoài transaction phù hợp, cơ chế và thời điểm ghi sẽ khác.

Annotation `@Version` giúp JPA thực hiện *optimistic locking*: khi hai transaction cùng sửa một phiên bản entity, việc ghi sau có thể bị từ chối bằng ngoại lệ xung đột. Thao tác này cần transaction và xử lý ngoại lệ phù hợp ở lớp service. JPA cũng hỗ trợ JPQL, Criteria API và native SQL cho những truy vấn không thuận tiện khi chỉ điều hướng entity.

## 4. Cơ chế transaction và quản lý tài nguyên

Sự khác nhau lớn nằm ở ai chịu trách nhiệm tạo ranh giới giao dịch. **Một transaction thuộc database connection/session thích hợp, không thuộc riêng một phương thức DAO.**

| Công cụ | Cách quản lý thường gặp | Điều phải kiểm tra |
|---|---|---|
| JDBC thuần | `setAutoCommit(false)`, `commit()`, `rollback()` trên cùng `Connection` | Tất cả các lệnh thuộc nghiệp vụ dùng đúng một connection |
| Spring JDBC | `@Transactional` với transaction manager phù hợp | Các template dùng cùng nguồn kết nối được manager quản lý |
| MyBatis | `SqlSession`/commit; hoặc MyBatis-Spring với `@Transactional` | Không mở session/commit riêng làm lệch ranh giới transaction |
| JPA/Hibernate | `EntityTransaction`, JTA hoặc transaction manager của framework | Entity đang managed, thời điểm flush, lỗi optimistic locking |

Ví dụ thủ công với JDBC:

```java
try (Connection connection = dataSource.getConnection()) {
    boolean originalAutoCommit = connection.getAutoCommit();
    connection.setAutoCommit(false);
    try {
        // Gửi nhiều PreparedStatement trên cùng connection.
        // Ví dụ: tạo order và các order_item của nó.
        connection.commit();
    } catch (SQLException failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    } finally {
        connection.setAutoCommit(originalAutoCommit);
    }
}
```

Đây là khung minh họa ranh giới giao dịch: câu lệnh SQL và kiểm tra nghiệp vụ phải được bổ sung vào khối `try`. Trong ứng dụng thực tế, việc khôi phục trạng thái kết nối cũng cần theo chính sách của connection pool/transaction manager, và phải xử lý cả trường hợp connection không còn sử dụng được sau lỗi nghiêm trọng.

Với Spring, `@Transactional` thường chỉ có hiệu lực khi lời gọi đi qua cơ chế proxy/transaction interceptor được cấu hình. Một phương thức gọi nội bộ trực tiếp trong cùng đối tượng có thể không được proxy chặn; không nên mặc định annotation tự bảo đảm transaction trong mọi ngữ cảnh.

Với ORM, cần phân biệt:

- **Persistence context** giữ các managed entity và theo dõi trạng thái trong phạm vi nhất định.
- **Flush** đồng bộ thay đổi thành SQL, nhưng không đồng nghĩa với transaction đã được commit.
- **Commit** hoàn tất transaction nếu thành công; lỗi constraint hoặc xung đột version có thể xuất hiện khi flush/commit.
- **Lazy loading** có thể đòi một persistence context/session còn hiệu lực để tải quan hệ chưa được fetch.

## 5. Cách CRUD thay đổi giữa bốn phương án

Xét nghiệp vụ “đổi giá sản phẩm nếu bản ghi vẫn ở phiên bản người dùng đã đọc”:

```sql
UPDATE products
SET price = ?, version = version + 1
WHERE id = ? AND version = ?
```

- **JDBC thuần:** tự chuẩn bị SQL, bind ba tham số rồi đọc `executeUpdate()`; `0` dòng thường nghĩa là bản ghi không tồn tại hoặc phiên bản đã đổi.
- **Spring JDBC:** chạy cùng SQL bằng `jdbcTemplate.update(...)` hoặc `namedParameterJdbcTemplate.update(...)`; vẫn cần xử lý số dòng ảnh hưởng.
- **MyBatis:** đặt SQL trong mapper, bind bằng `#{...}`, cho phương thức trả `int` số dòng ảnh hưởng; ứng dụng chủ động xử lý xung đột.
- **JPA/Hibernate:** tải managed entity có `@Version` và sửa giá; ORM có thể sinh `UPDATE` kèm điều kiện version, rồi báo xung đột qua ngoại lệ khi phát hiện số dòng không khớp.

Cần lưu ý cách JPA tạo SQL cụ thể phụ thuộc provider, chiến lược ánh xạ và thời điểm flush; nếu ứng dụng viết một lệnh **bulk JPQL update** trực tiếp, cơ chế dirty checking/optimistic locking cho từng managed entity không tự động có cùng ý nghĩa như sửa entity thông thường. Phải thiết kế kiểm soát version riêng cho kiểu lệnh bulk khi cần.

Với thao tác **tạo bản ghi**, JDBC/Spring JDBC/MyBatis thường cần chỉ định cách nhận ID tự sinh của driver hoặc mapper. JPA có `@GeneratedValue` và provider quản lý ID theo chiến lược tương ứng, nhưng phải đồng bộ với cơ chế sinh khóa của database. Với **xóa bản ghi**, `DELETE` thủ công dễ kiểm soát điều kiện `WHERE`; ORM có thể xử lý thêm quy tắc cascade, orphan removal hoặc ràng buộc quan hệ đã khai báo, nên cần xem SQL thực sự được sinh.

## 6. Mối quan hệ giữa bảng và bài toán N+1

Giả sử có 100 đơn hàng và mỗi đơn hàng liên kết một khách hàng. Nếu ứng dụng tải danh sách đơn hàng rồi truy vấn thêm một lần cho từng khách hàng, nó có thể thực hiện **1 + 100 câu SQL**. Hiện tượng này thường được gọi là *N+1 queries*.

- JDBC/Spring JDBC: nếu lập trình viên viết vòng lặp gọi DAO tìm khách hàng, N+1 vẫn xảy ra. Có thể dùng JOIN hoặc truy vấn `WHERE id IN (...)` rồi nhóm kết quả.
- MyBatis: nested select trong result map hoặc vòng lặp mapper có thể gây N+1; một JOIN với result map hoặc truy vấn theo lô thường giúp giảm số round-trip.
- ORM: quan hệ lazy được truy cập lần lượt dễ gây N+1; có thể chọn `JOIN FETCH`, entity graph, batch fetching hoặc projection tùy ngữ cảnh.

**Lazy loading không tự động xấu; eager loading cũng không tự động tốt.** Fetch thừa dữ liệu, JOIN tạo nhiều hàng lặp cho tập quan hệ một-nhiều và phân trang trên JOIN fetch đều có thể gây vấn đề khác. Điều quan trọng là xác định **kế hoạch lấy dữ liệu** cho từng use case, đo số câu SQL và kích thước kết quả.

ORM đặc biệt hữu ích khi cần quản lý một *aggregate* nhiều entity và nhiều thay đổi trong một transaction. Với dashboard chỉ đọc hàng nghìn dòng theo nhiều phép JOIN/tổng hợp, DTO/projection hoặc SQL riêng đôi khi dễ hiểu hơn việc tải cả đồ thị entity.

## 7. Hiệu năng: chọn theo SQL và hành vi thực tế

Một hiểu lầm phổ biến là “JDBC thuần luôn nhanh hơn ORM” hoặc “ORM tự tối ưu mọi thứ”. Cả hai nhận định đều quá đơn giản. Hiệu năng chịu ảnh hưởng của:

1. **Câu SQL và execution plan:** index, số dòng quét, JOIN, điều kiện lọc và sắp xếp.
2. **Số round-trip:** 1 truy vấn lớn phù hợp hay 101 truy vấn nhỏ ngoài ý muốn.
3. **Số dòng/cột truyền về:** truy vấn chỉ đọc cột cần thiết thường nhẹ hơn tải toàn bộ entity.
4. **Transaction và khóa:** thời gian giữ connection/lock, deadlock và mức cô lập.
5. **Batching:** gom nhiều thao tác ghi có thể giảm round-trip, nhưng cách kích hoạt khác nhau giữa framework/driver.
6. **Cache và persistence context:** có thể giảm truy vấn lặp trong phạm vi phù hợp, nhưng không thay thế chính sách cache dữ liệu của ứng dụng.

Với JDBC, kiểm soát SQL và vòng đời `ResultSet` rất rõ, nhưng cần tự quản lý mapping và batching. Spring JDBC giảm mã lặp với SQL tương tự. MyBatis hỗ trợ tối ưu từng truy vấn viết tay, nhưng SQL động/result mapping cần được kiểm tra cẩn thận. ORM có thể giảm số dòng code nghiệp vụ, nhưng phải hiểu fetch plan, flush, cache, cascade và quan sát SQL được sinh.

Một quy trình đánh giá có cơ sở: dùng **cùng tập dữ liệu và yêu cầu đầu ra**, bật ghi log SQL an toàn, đo thời gian truy vấn/transaction, xem `EXPLAIN` hoặc công cụ phân tích của database và kiểm tra throughput khi có nhiều request đồng thời. Đừng kết luận chỉ từ độ dài mã Java hoặc một phép benchmark không có tải thực tế.

## 8. Chọn công cụ theo kiểu hệ thống

| Bối cảnh | Phương án thường phù hợp | Vì sao |
|---|---|---|
| Học JDBC hoặc viết một module hạ tầng nhỏ, ít truy vấn | JDBC thuần | Thấy rõ connection, statement, result set và transaction |
| Ứng dụng Spring có SQL đơn giản hoặc báo cáo tùy biến | Spring JDBC | Giữ SQL rõ ràng và giảm mã lặp |
| Hệ thống lấy SQL làm trung tâm, nhiều truy vấn động/phức tạp | MyBatis | Mapper chứa SQL chủ động kiểm soát, dễ gắn DTO |
| Ứng dụng domain phức tạp, nhiều entity/quan hệ và thay đổi trạng thái | JPA/Hibernate | Persistence context, mapping quan hệ và dirty checking giảm thao tác thủ công |
| Dịch vụ có cả CRUD entity và báo cáo SQL đặc thù | Kết hợp ORM với Spring JDBC/MyBatis khi có lý do rõ | Mỗi truy vấn dùng đúng công cụ; cần thống nhất transaction và trách nhiệm dữ liệu |

Không nhất thiết chọn một công cụ duy nhất cho toàn bộ sản phẩm. Chẳng hạn một service dùng JPA cho vòng đời đơn hàng nhưng dùng `JdbcTemplate` để chạy truy vấn thống kê. Việc kết hợp cần xác định rõ transaction manager, cùng nguồn dữ liệu, trạng thái entity đã nạp và tình huống dữ liệu bị thay đổi qua SQL trực tiếp trong lúc persistence context còn giữ bản cũ.

**Lựa chọn theo tiêu chí cụ thể:**

- Nếu nhóm cần **kiểm soát chính xác SQL**, bảng báo cáo phức tạp và ánh xạ sang DTO: Spring JDBC hoặc MyBatis có thể dễ duy trì.
- Nếu nghiệp vụ tập trung vào **đối tượng sống lâu trong một transaction và quan hệ giữa nhiều entity**: JPA/Hibernate cung cấp cơ chế hữu ích.
- Nếu mục tiêu là **hiểu hoặc gỡ lỗi cách ứng dụng truy cập RDBMS**, cần nắm JDBC kể cả khi code sản phẩm sử dụng framework khác.
- Nếu ứng dụng có ít truy vấn và không dùng Spring, JDBC thuần có thể đủ; thêm framework chỉ khi lợi ích bù được chi phí cấu hình và học tập.

## 9. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Ghép input trực tiếp thành SQL | SQL injection, sai escaping | Parameter binding: `?`, `:name`, `#{name}` hoặc parameter JPQL |
| Mỗi thao tác DAO tự lấy connection khi cần transaction nhiều bước | Thay đổi có thể commit riêng, không rollback cùng nhau | Cố định ranh giới transaction ở tầng service |
| Nghĩ `@Transactional` luôn hoạt động ở mọi lời gọi | Thao tác có thể chạy ngoài transaction mong muốn | Xác minh proxy/interceptor và transaction manager |
| Nghĩ MyBatis tự lưu khi sửa một POJO | Dữ liệu trong DB không thay đổi | Gọi mapper `INSERT/UPDATE/DELETE` rõ ràng |
| Nghĩ mọi entity JPA đều đang managed | Thay đổi detached object không được flush như mong đợi | Hiểu lifecycle và dùng transaction phù hợp |
| Chỉ dựa vào `SELECT` trước `INSERT` để bảo đảm duy nhất | Race condition giữa các request | Ràng buộc `UNIQUE` ở database, xử lý lỗi |
| Xem `FetchType.EAGER` là cách chữa mọi N+1 | Có thể tải thừa dữ liệu hoặc thêm nhiều JOIN | Thiết kế fetch plan theo use case |
| Ghi đè bản ghi mà không kiểm tra version | Lost update khi sửa đồng thời | Điều kiện version trong SQL hoặc `@Version` của JPA |
| Chọn ORM để khỏi cần biết SQL | Khó phát hiện N+1, thiếu index, truy vấn quá nặng | Quan sát SQL được sinh và execution plan |
| Kết luận MyBatis/JPA luôn nhanh hơn hoặc chậm hơn JDBC | Tối ưu sai chỗ | Benchmark với dữ liệu, số request và driver thực tế |

Các framework đều cần quy tắc xử lý dữ liệu `NULL`, kiểu ngày giờ, số thập phân, transaction, giới hạn phân trang, bảo mật truy cập và ràng buộc database. Chúng không thay thế thiết kế schema hoặc kiểm soát quyền truy cập.

## 10. Bài tập phân biệt công cụ

**Tình huống A — Báo cáo:** Cần xuất doanh thu theo tháng với nhiều phép `JOIN`, `GROUP BY` và kết quả là DTO phẳng. Bạn muốn người đọc code nhìn thấy SQL hoàn chỉnh. Hãy giải thích vì sao Spring JDBC hoặc MyBatis là lựa chọn hợp lý, và JPA vẫn có thể làm được bằng projection/native query.

**Tình huống B — Đơn hàng:** Khi người dùng xác nhận đơn, hệ thống đổi trạng thái đơn, tạo nhiều dòng chi tiết và cập nhật giá trị liên quan. Hãy xác định ranh giới transaction, cơ chế rollback và tình huống xung đột sửa đồng thời. So sánh cách viết SQL tường minh với managed entity.

**Tình huống C — N+1:** Trang hiển thị 50 đơn hàng cùng tên khách hàng đang chạy 51 câu SQL. Hãy đề xuất ít nhất hai cách giảm số round-trip. Vì sao vấn đề này không chỉ xảy ra với ORM?

**Tình huống D — Chuyển công cụ:** Một dự án đã dùng `JdbcTemplate` và muốn chuyển một phần sang Hibernate. Những thay đổi nào cần tính đến ở mapping, lifecycle entity, transaction, testing và quan sát SQL? Có thể giữ DAO truy vấn báo cáo bằng Spring JDBC không?

**Tình huống E — Đọc code:** Với MyBatis, phân biệt `#{sortColumn}` và `${sortColumn}` khi tạo `ORDER BY` động. Vì sao nên ánh xạ tên cột từ một allowlist ở tầng ứng dụng?

## 11. Kết luận kiến thức

JDBC thuần cho phép viết và quản lý gần như mọi chi tiết của quá trình truy cập database. Spring JDBC giữ quyền viết SQL nhưng loại bỏ nhiều mã lặp. MyBatis đặt SQL và mapping vào mapper. JPA/Hibernate chuyển trọng tâm sang entity, quan hệ và persistence context, đồng thời tự xây dựng SQL cho nhiều thao tác CRUD. Dù chọn cách nào, **SQL thực thi, transaction, index, số lần truy vấn và ràng buộc dữ liệu** vẫn quyết định độ đúng đắn và hiệu quả của hệ thống.

Thực hành quan trọng nhất là lấy **cùng một use case** triển khai theo nhiều cách, đọc SQL thực sự được chạy và kiểm tra hành vi khi bản ghi không tồn tại, có lỗi ràng buộc hoặc hai phiên cập nhật đồng thời. Nhờ đó, quyết định chọn công cụ dựa trên nhu cầu dữ liệu thay vì chỉ dựa vào mức độ phổ biến của framework.

