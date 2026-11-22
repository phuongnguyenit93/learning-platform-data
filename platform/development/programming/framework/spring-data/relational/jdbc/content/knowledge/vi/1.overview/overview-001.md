# Spring Data JDBC là gì và giải quyết vấn đề lưu trữ dữ liệu nào?

Khi xây dựng một ứng dụng Java, dữ liệu thường phải tồn tại lâu hơn thời gian chạy của chương trình. Tài khoản khách hàng, đơn hàng, tồn kho hay lịch sử thanh toán không thể chỉ nằm trong biến hoặc một `List` trong bộ nhớ: khi ứng dụng khởi động lại, bộ nhớ đó bị mất. Ứng dụng cần **lưu dữ liệu bền vững**, đọc lại dữ liệu đã lưu, cập nhật đúng bản ghi và phối hợp nhiều thao tác ghi một cách an toàn.

**Spring Data JDBC** là một thành viên của hệ sinh thái Spring Data, hỗ trợ ánh xạ đối tượng Java với bảng trong cơ sở dữ liệu quan hệ và cung cấp các **repository** để thực hiện các thao tác truy cập dữ liệu thông dụng. Nó sử dụng JDBC làm nền tảng, nhưng giúp lập trình viên tập trung vào mô hình dữ liệu và quy tắc nghiệp vụ hơn là tự viết cùng một lượng mã kết nối, truy vấn và ánh xạ ở nhiều nơi.

> **Ý chính:** Spring Data JDBC giải quyết phần lớn công việc lặp lại khi lưu và truy xuất **aggregate** của ứng dụng Java trên cơ sở dữ liệu quan hệ. Bản thân nó không phải cơ sở dữ liệu, không tự bảo đảm dữ liệu được lưu bền vững nếu bạn dùng cơ sở dữ liệu chỉ nằm trong RAM, và không thay thế việc thiết kế bảng, ràng buộc dữ liệu hoặc giao dịch.

## 1. Bài toán lưu trữ dữ liệu xuất phát từ đâu?

Giả sử một cửa hàng có chức năng đăng ký khách hàng. Khi người dùng gửi tên và email, hệ thống cần:

1. Kiểm tra dữ liệu đầu vào và quy tắc nghiệp vụ.
2. Ghi khách hàng vào bảng `customers` của cơ sở dữ liệu.
3. Lấy lại mã định danh do cơ sở dữ liệu cấp.
4. Cho phép tìm khách hàng theo mã hoặc email ở những lần truy cập sau.
5. Không tạo hai khách hàng trùng email nếu cơ sở dữ liệu quy định email là duy nhất.

Một mô hình rất nhỏ đã phải trả lời những câu hỏi kỹ thuật sau:

| Nhu cầu của ứng dụng | Cơ sở dữ liệu và tầng truy cập dữ liệu phải xử lý |
| --- | --- |
| Lưu lâu dài | Chuyển dữ liệu thành câu lệnh `INSERT` vào bảng trên cơ sở dữ liệu có lưu trữ bền vững. |
| Đọc dữ liệu | Chạy `SELECT`, nhận các hàng kết quả và tạo lại đối tượng Java. |
| Sửa, xóa | Xác định đúng bản ghi và thực hiện `UPDATE`/`DELETE`. |
| Đồng nhất dữ liệu | Áp dụng khóa chính, ràng buộc `UNIQUE`, `NOT NULL`, khóa ngoại và quy tắc nghiệp vụ phù hợp. |
| Nhiều thao tác liên quan | Dùng giao dịch để một nhóm thay đổi cùng thành công hoặc cùng được hoàn tác. |
| Truy cập đồng thời | Thiết kế ràng buộc, mức cô lập hoặc cơ chế khóa/kiểm tra phiên bản tùy bài toán. |

**Cơ sở dữ liệu quan hệ** (như PostgreSQL, MySQL hoặc H2) chịu trách nhiệm quản lý bảng, bản ghi, ràng buộc và lưu trữ thực tế. **JDBC** là API chuẩn của Java để gửi lệnh SQL đến cơ sở dữ liệu thông qua driver. **Spring Data JDBC** nằm ở tầng ứng dụng, tổ chức việc dùng JDBC theo mô hình đối tượng và repository. Ba thành phần này có vai trò khác nhau.

```text
Mã nghiệp vụ Java
       |
       v
Repository / tầng truy cập dữ liệu
       |
       v
JDBC + driver cơ sở dữ liệu
       |
       v
PostgreSQL / MySQL / cơ sở dữ liệu quan hệ khác
       |
       v
Bảng, hàng dữ liệu, khóa và giao dịch
```

## 2. Nếu chỉ dùng JDBC thuần, lập trình viên phải làm gì?

JDBC cho phép toàn quyền viết SQL nhưng phần mã bao quanh một truy vấn thường lặp lại: lấy `Connection`, tạo `PreparedStatement`, truyền tham số, thực thi, duyệt `ResultSet`, chuyển kiểu dữ liệu, xử lý lỗi và đóng tài nguyên.

Ví dụ, phương thức tìm một khách hàng theo ID bằng JDBC có thể trông như sau:

```java
public Optional<Customer> findById(DataSource dataSource, long id)
        throws SQLException {
    String sql = "SELECT id, full_name, email FROM customers WHERE id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, id);

        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                return Optional.empty();
            }
            Customer customer = new Customer(
                    result.getString("full_name"),
                    result.getString("email")
            );
            customer.setId(result.getLong("id"));
            return Optional.of(customer);
        }
    }
}
```

`PreparedStatement` là cách đúng để truyền tham số, thay vì ghép dữ liệu người dùng trực tiếp vào chuỗi SQL. Dù vậy, đoạn mã vẫn dành nhiều dòng để quản lý tài nguyên và chuyển đổi kết quả. Khi có hàng chục bảng và thao tác CRUD, phần lặp lại này làm tầng truy cập dữ liệu dài và khó duy trì.

**Spring JDBC** đã giảm bớt công việc đó qua `JdbcTemplate`: framework quản lý tài nguyên, thực thi SQL, chuẩn hóa lỗi và cho phép lập trình viên cung cấp hàm ánh xạ hàng dữ liệu. **Spring Data JDBC** đi xa hơn một bước: nó có thể cung cấp triển khai repository và sinh câu lệnh cho nhiều thao tác thông dụng dựa trên mô hình đối tượng.

```text
JDBC thuần       → Tự viết SQL + tự quản lý JDBC + tự ánh xạ
Spring JDBC      → Tự viết SQL + JdbcTemplate hỗ trợ thực thi/ánh xạ
Spring Data JDBC → Repository + ánh xạ aggregate + CRUD thông dụng
```

Đây là các tầng trừu tượng có thể **phối hợp** với nhau. Dùng Spring Data JDBC không có nghĩa là mất quyền viết SQL khi có truy vấn chuyên biệt.

## 3. Spring Data JDBC thực chất là gì?

Spring Data JDBC cung cấp cơ chế **object mapping** và **repository abstraction** cho dữ liệu quan hệ:

- **Đối tượng Java:** lớp đại diện cho dữ liệu nghiệp vụ, ví dụ `Customer`, `Order` hoặc `OrderLine`.
- **Ánh xạ:** metadata từ lớp, trường và annotation như `@Table`, `@Id`, `@Column`, `@MappedCollection` giúp framework biết dữ liệu được lưu ở đâu.
- **Repository:** interface như `CrudRepository<T, ID>` cho phép gọi `save`, `findById`, `findAll`, `deleteById` mà không cần tự xây dựng lớp DAO cho mỗi thao tác cơ bản.
- **Truy vấn theo tên phương thức:** một số truy vấn đơn giản có thể được suy ra từ tên phương thức, ví dụ `findByEmail(String email)`.
- **Tích hợp Spring:** quản lý dependency injection, chuyển đổi ngoại lệ truy cập dữ liệu và làm việc với giao dịch thông qua Spring.

Một repository được khai báo như sau:

```java
public interface CustomerRepository extends CrudRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);
}
```

Khi ứng dụng đã cấu hình Spring Data JDBC đúng cách, Spring tạo triển khai repository ở thời gian chạy. Mã nghiệp vụ chỉ cần tiêm `CustomerRepository` và gọi phương thức. Đối với thao tác CRUD thông thường, Spring Data JDBC tạo SQL và ánh xạ kết quả dựa trên kiểu `Customer`.

**Điểm phân biệt quan trọng:** Spring Data JDBC không sử dụng JPA `EntityManager`, không có Hibernate persistence context, không tự theo dõi mọi thay đổi trên đối tượng và không có lazy loading theo kiểu ORM của JPA. Hành vi lưu dữ liệu được xác định rõ thông qua thao tác repository và ranh giới aggregate.

## 4. Ví dụ: lưu khách hàng vào PostgreSQL

Ví dụ dưới đây sử dụng Spring Boot, Spring Data JDBC và PostgreSQL. PostgreSQL là cơ sở dữ liệu lưu dữ liệu thực tế; ứng dụng cần có một database `shopdb` và tài khoản được cấp quyền phù hợp trước khi chạy.

### 4.1. Thêm dependency

Với dự án Spring Boot dùng Gradle và đã quản lý phiên bản các dependency qua Spring Boot, cấu hình tối thiểu là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

Starter cung cấp các thành phần Spring Data JDBC/Spring JDBC cần thiết; driver PostgreSQL cho phép JDBC kết nối đến PostgreSQL. Dự án không cần thêm `spring-boot-starter-data-jpa` cho ví dụ này.

### 4.2. Tạo bảng

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE
);
```

Ở đây:

- `id` là khóa chính, được cơ sở dữ liệu sinh khi thêm bản ghi.
- `full_name` và `email` là các cột bắt buộc.
- `UNIQUE (email)` ngăn hai bản ghi có cùng giá trị email theo quy tắc so sánh của cơ sở dữ liệu.

Spring Data JDBC **không tự tạo hoặc tự cập nhật schema theo cơ chế `hibernate.ddl-auto` của JPA/Hibernate**. Trong dự án thực tế, nên quản lý DDL qua migration như Flyway/Liquibase; có thể chạy SQL tạo bảng thủ công để hiểu ví dụ.

### 4.3. Cấu hình kết nối

Trong `src/main/resources/application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shopdb
    username: ${DB_USER}
    password: ${DB_PASSWORD}
```

Biến môi trường `DB_USER` và `DB_PASSWORD` chứa thông tin đăng nhập tương ứng. Giá trị URL, tên database và tài khoản chỉ là ví dụ, cần điều chỉnh theo PostgreSQL đang chạy. Kết nối thành công không đồng nghĩa bảng đã tồn tại: bảng phải được tạo trước khi gọi repository.

### 4.4. Khai báo lớp ánh xạ bảng

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;
    private String fullName;
    private String email;

    public Customer() {
    }

    public Customer(String fullName, String email) {
        this.fullName = fullName;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

`@Table("customers")` chỉ định bảng. `@Id` chỉ định thuộc tính khóa chính. Theo quy ước đặt tên mặc định, thuộc tính `fullName` ánh xạ đến cột `full_name`; khi quy ước khác với schema, có thể dùng `@Column("ten_cot")`. Kiểu `Long` cho `id` cho phép giá trị `null` trước khi đối tượng được lưu lần đầu.

### 4.5. Khai báo repository

```java
import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository extends CrudRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);
}
```

`CrudRepository<Customer, Long>` diễn đạt hai thông tin: repository quản lý đối tượng `Customer`, còn khóa chính có kiểu `Long`. Spring Data JDBC cung cấp triển khai cho các thao tác chuẩn như `save`, `findById`, `findAll`, `count` và `deleteById`.

### 4.6. Dùng repository trong nghiệp vụ

```java
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public Customer register(String fullName, String email) {
        Customer customer = new Customer(fullName, email);
        return customers.save(customer);
    }

    @Transactional(readOnly = true)
    public Optional<Customer> find(long customerId) {
        return customers.findById(customerId);
    }

    @Transactional(readOnly = true)
    public Optional<Customer> findByEmail(String email) {
        return customers.findByEmail(email);
    }
}
```

Khi gọi:

```java
Customer saved = customerService.register("Nguyễn Minh An", "an@example.com");
System.out.println(saved.getId()); // ID do PostgreSQL cấp

Optional<Customer> loaded = customerService.find(saved.getId());
```

Luồng xử lý về mặt ý tưởng là:

```text
CustomerService.register(...)
       |
       v
CustomerRepository.save(customer)
       |
       v
Spring Data JDBC xác định đối tượng mới (id == null)
       |
       v
SQL INSERT được gửi qua JDBC tới PostgreSQL
       |
       v
PostgreSQL ghi hàng và cấp id
       |
       v
Đối tượng trả về có id; có thể truy vấn lại bằng findById(...)
```

Ví dụ SQL tương đương về **ý nghĩa** với thao tác lưu và đọc (SQL thực tế do framework/driver sinh có thể khác):

```sql
INSERT INTO customers (full_name, email)
VALUES ('Nguyễn Minh An', 'an@example.com');

SELECT id, full_name, email
FROM customers
WHERE id = 1;
```

Giá trị `1` chỉ để minh họa; ID thực tế phụ thuộc dữ liệu trong bảng. Khi mã ứng dụng chạy, các giá trị động được truyền dưới dạng tham số SQL, không nên tạo câu lệnh bằng cách nối chuỗi đầu vào của người dùng như ví dụ SQL tĩnh trên.

**Kết quả:** mã nghiệp vụ không phải tự mở kết nối, tự tạo `PreparedStatement` hoặc tự ánh xạ `ResultSet` cho những thao tác này. Dữ liệu được lưu tại PostgreSQL và có thể đọc lại sau khi ứng dụng khởi động lại, miễn là cơ sở dữ liệu và dữ liệu của nó vẫn được giữ nguyên.

## 5. Khái niệm trung tâm: aggregate và aggregate root

Spring Data JDBC dùng tư duy của **Domain-Driven Design (DDD)** cho việc lưu đối tượng: một **aggregate** là nhóm đối tượng được coi như một đơn vị nhất quán; **aggregate root** là đối tượng bên ngoài được phép thao tác trực tiếp qua repository.

Ví dụ, một đơn hàng có nhiều dòng hàng:

```text
Order (aggregate root)
  ├── OrderLine: sách A, số lượng 2
  └── OrderLine: sách B, số lượng 1
```

Các dòng hàng thuộc đơn hàng này, cùng tham gia quy tắc như “tổng tiền đơn hàng bằng tổng tiền dòng hàng”. Ta có thể thiết kế một `OrderRepository` quản lý `Order` và các `OrderLine` nằm trong aggregate. Annotation `@MappedCollection` thường được dùng để ánh xạ collection các đối tượng con thuộc aggregate.

Ngược lại, `Customer` và `Order` thường nên là **hai aggregate độc lập**. Đơn hàng có thể lưu `customerId` (hoặc biểu diễn tham chiếu ID qua `AggregateReference`) để tham chiếu khách hàng, thay vì mặc định tải và quản lý toàn bộ khách hàng trong mỗi lần lưu đơn hàng.

```text
Customer aggregate                   Order aggregate
┌─────────────────┐                  ┌────────────────────────┐
│ Customer        │                  │ Order                  │
│ id = 10         │◄──customerId─────│ customerId = 10        │
└─────────────────┘                  │ ├─ OrderLine A         │
                                   │ └─ OrderLine B         │
                                   └────────────────────────┘
```

Ranh giới aggregate ảnh hưởng trực tiếp đến hiệu năng và ý nghĩa lưu dữ liệu:

- `save(root)` là thao tác lưu **trạng thái aggregate**, không đơn giản là tự động phát hiện những trường nào đã bị đổi trong mọi đối tượng đang nằm trong bộ nhớ.
- Với collection đối tượng con thuộc aggregate, khi cập nhật root, Spring Data JDBC có thể **xóa và chèn lại** các hàng con để đồng bộ trạng thái. Vì thế không nên gom cả đồ thị quan hệ rất lớn thành một aggregate.
- Các tham chiếu giữa **hai aggregate** không được tự động lazy-load như quan hệ ORM JPA; ứng dụng thường truy vấn repository của aggregate còn lại khi cần.
- Chọn aggregate nhỏ, có quy tắc nhất quán rõ ràng giúp cách lưu và ranh giới giao dịch dễ dự đoán hơn.

Đây là khác biệt nền tảng giữa Spring Data JDBC và cách tổ chức quan hệ đối tượng theo JPA/Hibernate. Khi mới học, nên bắt đầu bằng một aggregate root đơn giản như `Customer`, sau đó mới thực hành `Order` và `OrderLine`.

## 6. Spring Data JDBC giải quyết được gì, và không giải quyết được gì?

| Vấn đề | Spring Data JDBC hỗ trợ | Phần lập trình viên vẫn cần chịu trách nhiệm |
| --- | --- | --- |
| Mã CRUD lặp lại | Có sẵn repository, ánh xạ đối tượng và sinh SQL cho các thao tác phổ biến. | Thiết kế kiểu dữ liệu, repository, ranh giới aggregate. |
| Mã JDBC mức thấp | Tích hợp Spring JDBC để thực thi SQL và xử lý kết quả. | Cấu hình `DataSource`, driver và kết nối đúng. |
| Truy vấn đơn giản | Các phương thức CRUD và một số query derivation như `findByEmail`. | Viết `@Query`, custom repository hoặc dùng `JdbcTemplate`/`JdbcClient` cho SQL phức tạp. |
| Dữ liệu lưu bền vững | Gửi thao tác ghi đến cơ sở dữ liệu quan hệ. | Chọn và vận hành database có cơ chế lưu bền vững, sao lưu và phục hồi phù hợp. |
| Tính toàn vẹn | Có thể dùng giao dịch Spring và mapping dữ liệu. | Thiết kế khóa, `UNIQUE`, `NOT NULL`, khóa ngoại; xử lý xung đột đồng thời. |
| Schema | Ánh xạ vào schema hiện hữu. | Tạo và phiên bản hóa bảng bằng SQL migration. |
| Mối quan hệ dữ liệu | Mô hình aggregate và tham chiếu giữa aggregate. | Chọn ranh giới aggregate; cân nhắc chi phí đọc/ghi collection. |

### 6.1. Giao dịch không tự giải quyết mọi vấn đề đồng thời

Giả sử chức năng chuyển điểm thưởng cần trừ điểm từ tài khoản A và cộng điểm vào tài khoản B. Nếu một thao tác thành công nhưng thao tác kia lỗi, dữ liệu sẽ mất cân bằng. Một phương thức service dùng `@Transactional` có thể đặt cả hai lệnh ghi trong **cùng giao dịch** để rollback khi xảy ra lỗi phù hợp.

Tuy nhiên, giao dịch đơn thuần không thay thế việc xử lý xung đột khi hai yêu cầu cùng cập nhật một bản ghi. Với bài toán cần phát hiện cập nhật chồng lấn, Spring Data JDBC có hỗ trợ **optimistic locking** qua trường `@Version`; việc dùng cơ chế nào còn tùy quy tắc nghiệp vụ và mức cô lập giao dịch. Ràng buộc `UNIQUE` trong database vẫn là nơi bảo vệ dữ liệu trước hai yêu cầu đăng ký cùng một email cùng lúc.

### 6.2. Không phải mọi truy vấn đều nên ép vào phương thức suy diễn tên

Truy vấn lọc khách hàng theo email là trường hợp đơn giản. Nhưng với báo cáo doanh thu theo quý, nhiều phép `JOIN`, phân nhóm, tổng hợp hoặc truy vấn được tối ưu đặc biệt, việc viết SQL tường minh thường dễ kiểm soát hơn. Spring Data JDBC cho phép sử dụng `@Query` đối với truy vấn thích hợp, hoặc phối hợp Spring JDBC/custom implementation. Khả năng suy diễn query của Spring Data JDBC cũng không tương đương với hệ truy vấn quan hệ/phép nối đồ thị đối tượng của JPA.

## 7. So sánh với những lựa chọn thường gặp

| Công nghệ | Cách làm chủ đạo | Phù hợp khi |
| --- | --- | --- |
| **JDBC thuần** | Tự quản lý connection/statement/result và viết SQL. | Cần hiểu nền tảng JDBC hoặc tích hợp đặc thù rất nhỏ. |
| **Spring JDBC** (`JdbcTemplate`, `JdbcClient`) | Tự chủ SQL, Spring hỗ trợ các thao tác JDBC và ánh xạ kết quả. | Ứng dụng nặng về SQL tùy chỉnh, báo cáo, truy vấn tối ưu thủ công. |
| **Spring Data JDBC** | Repository cho aggregate, mapping đơn giản, SQL CRUD được hỗ trợ. | Nghiệp vụ có aggregate rõ ràng, muốn giảm CRUD boilerplate và giữ truy cập dữ liệu dễ dự đoán. |
| **Spring Data JPA** (thường dùng Hibernate) | ORM dựa trên JPA với persistence context và cơ chế quan hệ phong phú. | Mô hình đối tượng liên kết phức tạp, cần các tính năng ORM/JPA phù hợp. |
| **Spring Data R2DBC** | Truy cập cơ sở dữ liệu quan hệ theo giao diện reactive, không dựa trên JDBC blocking. | Ứng dụng reactive cần đường truy cập dữ liệu không chặn phù hợp toàn bộ stack. |

**Spring Data JDBC không phải “JPA phiên bản nhẹ” theo nghĩa giữ lại toàn bộ hành vi JPA.** Hai công nghệ lựa chọn cách quản lý đối tượng khác nhau: JDBC tập trung vào aggregate và thao tác lưu tường minh; JPA cung cấp persistence context, dirty checking và nhiều cơ chế quan hệ/lazy loading hơn. Chọn Spring Data JDBC vì sự đơn giản và phù hợp với mô hình, không chỉ vì thấy từ “JDBC” quen thuộc.

## 8. Những nhầm lẫn thường gặp

**“Có repository thì không còn SQL.”** Không đúng. Repository trừu tượng hóa truy cập dữ liệu, còn JDBC vẫn gửi SQL đến database. Với truy vấn đặc thù, bạn vẫn cần đọc và viết SQL, xem execution plan và thiết kế index.

**“Cứ thêm starter thì bảng tự được tạo.”** Không đúng. Spring Data JDBC ánh xạ vào schema; cần quản lý schema bằng SQL hoặc migration. Cấu hình `spring.jpa.hibernate.ddl-auto` không phải cơ chế tạo schema của Spring Data JDBC.

**“`save` luôn chỉ chạy một câu `UPDATE`.”** Không đúng. Framework xét đối tượng mới/cũ và trạng thái aggregate. Với aggregate có các collection đối tượng con, quá trình lưu có thể thực hiện nhiều lệnh SQL và tái tạo các hàng con.

**“Khai báo đối tượng có tham chiếu là tự động tải mọi quan hệ.”** Không đúng. Spring Data JDBC không cung cấp lazy loading kiểu JPA; quan hệ phải được mô hình hóa theo ownership của aggregate và tham chiếu bằng ID khi tách aggregate.

**“Dùng cơ sở dữ liệu H2 in-memory tức là dữ liệu luôn còn sau khi restart.”** Không đúng. H2 `jdbc:h2:mem:...` chỉ phù hợp demo/test mà không yêu cầu lưu bền qua vòng đời database. Với ứng dụng thật, cần dùng cơ sở dữ liệu và cấu hình lưu trữ bền vững phù hợp.

**“Có `@Transactional` thì mọi quy tắc dữ liệu đều an toàn.”** Không đúng. Giao dịch cung cấp ranh giới atomicity theo cấu hình, còn ràng buộc, mức cô lập, khóa và quy tắc xử lý xung đột cần được thiết kế cụ thể.

## 9. Tự kiểm tra mức hiểu

Hãy thử trả lời các câu sau trước khi chuyển sang chủ đề tiếp theo:

1. Tại sao `List<Customer>` trong service không đáp ứng yêu cầu lưu dữ liệu khách hàng lâu dài?
2. Trong luồng `CustomerRepository.save(...)`, thành phần nào thực sự lưu hàng dữ liệu vào đĩa và thành phần nào chuyển lời gọi Java thành truy cập SQL?
3. Vì sao repository giúp mã gọn hơn JDBC thuần, và khi nào vẫn cần viết SQL?
4. Trong mô hình `Order` và `OrderLine`, ai nên là aggregate root? Vì sao không nên gom toàn bộ `Customer`, `Order`, `Product` vào một aggregate khổng lồ?
5. Vì sao cần ràng buộc `UNIQUE (email)` ở cơ sở dữ liệu, ngay cả khi ứng dụng đã kiểm tra email trước lúc gọi `save`?

Nếu trả lời được các câu này, bạn đã nắm nền tảng quan trọng nhất: **Spring Data JDBC là công cụ ánh xạ và truy cập dữ liệu quan hệ theo repository/aggregate, giúp giảm mã JDBC lặp lại; cơ sở dữ liệu, thiết kế schema, giao dịch và ranh giới aggregate vẫn quyết định tính đúng đắn của hệ thống lưu trữ.**
