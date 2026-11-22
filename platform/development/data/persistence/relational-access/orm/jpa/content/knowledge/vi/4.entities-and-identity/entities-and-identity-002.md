# Vai trò của Entity, Table và tên entity trong JPA

Khi bắt đầu sử dụng Java Persistence API (JPA), ba khái niệm thường xuất hiện gần nhau là **entity**, **table** và **tên entity**. Chúng liên quan trực tiếp đến ánh xạ giữa đối tượng Java và dữ liệu quan hệ, nhưng không có cùng vai trò:

- **Entity** là một loại đối tượng Java có định danh và vòng đời được JPA quản lý.
- **Table** là bảng vật lý trong cơ sở dữ liệu quan hệ mà entity được ánh xạ tới, thông thường là bảng chính của entity.
- **Tên entity** là tên logic dùng để nhận diện loại entity trong mô hình JPA, đặc biệt khi viết JPQL. Tên này có thể khác tên lớp Java và tên bảng SQL.

Bên cạnh đó còn có **khóa chính** (primary key), được khai báo bằng `@Id` hoặc `@EmbeddedId`. Đây là định danh của **một bản ghi/instance**, khác với tên entity vốn chỉ định **loại entity**.

Bài này tập trung vào vai trò, cách khai báo và quan hệ giữa các tên, cũng như những lỗi thường gặp khi truy vấn JPQL hoặc sửa ánh xạ.

## 1. Nhìn tổng thể: Từ lớp Java đến bảng cơ sở dữ liệu

Giả sử ứng dụng bán hàng có một lớp `Customer` và bảng `customer_account`:

~~~text
                        TẦNG JAVA / JPA

            package com.example.shop.domain;
                    class Customer
                          |
                 @Entity(name = "CustomerAccount")
                          |
                   tên entity: CustomerAccount
                          |
              JPQL: FROM CustomerAccount c
                          |
                    JPA provider
                   (Hibernate, EclipseLink...)
                          |
                 @Table(name = "customer_account")
                          |
                        TẦNG SQL

                bảng sales.customer_account
                  customer_id | full_name
                  ----------- | -----------
                           1  | Lan
                           2  | Minh
~~~

Trong ví dụ này có ít nhất bốn tên/giá trị độc lập:

| Thành phần | Giá trị | Dùng để làm gì? |
|---|---|---|
| Tên lớp Java | `Customer` | Khai báo kiểu, tạo đối tượng, tham chiếu trong mã Java |
| Tên entity JPA | `CustomerAccount` | Chỉ tên loại entity trong JPQL và metadata JPA |
| Tên bảng SQL | `customer_account` | Chỉ bảng vật lý khi database thực thi SQL |
| Khóa chính | `customer_id`, ví dụ `1` | Xác định bản ghi cụ thể và danh tính entity |

Không nên suy ra tên bảng chỉ từ tên lớp hoặc dùng tên bảng trong một câu JPQL nếu entity đã có tên logic khác.

## 2. `@Entity`: Khai báo loại đối tượng được JPA quản lý

### 2.1. Vai trò của `@Entity`

Annotation `@Entity` trong `jakarta.persistence` đánh dấu một lớp Java là entity thuộc mô hình persistence. Một entity có thể được quản lý bởi `EntityManager` trong *persistence context*, được ánh xạ sang dữ liệu quan hệ và tham gia các thao tác như:

- `persist(entity)`: đưa một entity mới vào trạng thái managed để lưu.
- `find(Customer.class, id)`: tìm entity theo loại Java và khóa chính.
- `remove(entity)`: đánh dấu xóa entity đang được quản lý.
- `merge(detachedEntity)`: hợp nhất trạng thái của entity detached và trả về đối tượng managed.
- Sửa thuộc tính của managed entity: JPA provider có thể nhận biết thay đổi (*dirty checking*) và đồng bộ thành SQL khi cần.

Một lớp Java bình thường không tự động trở thành entity vì có trường `id` hoặc vì tên lớp giống tên bảng. Cần khai báo hoặc ánh xạ loại entity theo cơ chế JPA phù hợp.

Ví dụ đơn giản:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected Product() {
        // Constructor để JPA khởi tạo entity.
    }

    public Product(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
~~~

Ở đây:

- `Product` là tên lớp Java.
- `@Entity` không truyền `name` nên tên entity mặc định là `Product`.
- `@Id` đánh dấu khóa chính của entity.
- `@GeneratedValue` yêu cầu cơ chế sinh khóa chính theo chiến lược được khai báo.
- Không có `@Table` nên tên bảng dùng quy tắc mặc định của JPA và chiến lược đặt tên của provider/framework.

### 2.2. Một số yêu cầu cơ bản đối với lớp entity

Để là một entity JPA hợp lệ và dễ di chuyển giữa provider, lớp cần tuân thủ các quy tắc của đặc tả, tiêu biểu:

1. Có constructor không tham số với mức truy cập `public` hoặc `protected`.
2. Là lớp phù hợp cho JPA quản lý, không khai báo `final` cho entity class hoặc các phương thức/thuộc tính persistent theo những hạn chế của đặc tả.
3. Có định danh khóa chính bằng `@Id` hoặc `@EmbeddedId`, khai báo trên lớp hoặc được kế thừa qua ánh xạ phù hợp.
4. Cấu hình ánh xạ thuộc tính đúng theo kiểu truy cập field/property đang dùng.
5. Được đưa vào phạm vi xử lý của persistence unit theo cấu hình ứng dụng.

Tùy phiên bản Jakarta Persistence, provider có thể hỗ trợ những kiểu triển khai nâng cao, nhưng không nên dựa vào tiện ích riêng nếu mục tiêu là tính di động.

### 2.3. `@Entity` không có nghĩa “một object luôn bằng một dòng đang được lưu”

Một object `new Product("Bút")` có thể đang ở trạng thái **new/transient**, chưa được persistence context quản lý. Sau `persist`, object có thể được quản lý và được ghi SQL vào thời điểm phù hợp. Khi context kết thúc, object vẫn tồn tại trong Java nhưng trở thành **detached**; setter trên detached object không tự ghi database.

`@Entity` nói rằng **loại Java này có thể được JPA quản lý**, không nói rằng bất kỳ instance nào của lớp cũng được tự động theo dõi suốt đời.

## 3. Tên entity: Tên logic mà JPQL dùng

### 3.1. Giá trị mặc định

Khi viết:

~~~java
@Entity
public class Customer {
    @Id
    private Long id;
}
~~~

Tên entity mặc định thường là **tên lớp không kèm package** (unqualified class name): `Customer`.

Nếu lớp có tên đầy đủ `com.example.shop.domain.Customer`, câu JPQL thông thường vẫn dùng:

~~~jpql
SELECT c
FROM Customer c
WHERE c.id = :id
~~~

Không viết tên bảng `customer` thay cho entity nếu dự án sử dụng ánh xạ hoặc tên entity khác.

### 3.2. Đặt tên entity tường minh

`@Entity` có thuộc tính `name`:

~~~java
@Entity(name = "CustomerAccount")
public class Customer {
    @Id
    private Long id;
}
~~~

Tên entity chính thức lúc này là `CustomerAccount`. Câu JPQL phù hợp:

~~~jpql
SELECT c FROM CustomerAccount c
~~~

Tên `Customer` vẫn là tên lớp Java trong mã nguồn, ví dụ:

~~~java
Customer customer = entityManager.find(Customer.class, 42L);
~~~

**`@Entity(name = "...")` không đổi tên lớp Java.** Nó đặt tên logic dùng trong ngôn ngữ truy vấn và metadata persistence.

### 3.3. JPQL tham chiếu entity, không tham chiếu bảng SQL

JPQL (*Jakarta Persistence Query Language*) làm việc theo mô hình đối tượng:

~~~java
TypedQuery<Customer> query = entityManager.createQuery(
    "SELECT c FROM CustomerAccount c WHERE c.fullName = :name",
    Customer.class
);
query.setParameter("name", "Lan");
List<Customer> customers = query.getResultList();
~~~

Trong câu truy vấn:

- `CustomerAccount` là tên entity.
- `c` là biến định danh trong truy vấn.
- `fullName` là tên thuộc tính Java được ánh xạ của entity.
- `:name` là tham số JPQL.
- JPA provider chuyển đổi truy vấn thành SQL tương ứng với bảng/cột vật lý.

Nếu bảng thực tế có tên `customer_account` và cột thực tế có tên `full_name`, câu JPQL vẫn tham chiếu tên entity và tên thuộc tính Java. Đó chính là lớp trừu tượng mà JPA cung cấp.

Một tên bảng vô tình trùng tên entity có thể làm hai loại tên khó phân biệt. Cách kiểm tra là nhìn nơi biểu thức được thực thi: `createQuery(...)` sử dụng JPQL, còn `createNativeQuery(...)` sử dụng SQL do người viết cung cấp.

### 3.4. Tên entity cần duy nhất trong persistence unit

Hai lớp ở hai package khác nhau có thể có cùng tên đơn `Employee`:

~~~text
com.example.internal.Employee
com.example.partner.Employee
~~~

Nếu cả hai đều là entity trong cùng persistence unit và đều mặc định tên `Employee`, tên logic có thể bị trùng và dẫn đến lỗi metadata/bootstrap. Có thể đặt tên tường minh:

~~~java
@Entity(name = "InternalEmployee")
class Employee {
    @Id Long id;
}
~~~

và với lớp `Employee` ở package khác:

~~~java
@Entity(name = "PartnerEmployee")
class Employee {
    @Id Long id;
}
~~~

Đây là hai đoạn minh họa trong **hai package/file khác nhau**. Tên entity được đặt tách biệt để JPQL có thể tham chiếu chính xác từng loại. Tên entity nên dễ đọc và nhất quán; trong truy vấn, sử dụng đúng cách viết hoa/thường đã khai báo.

## 4. `@Table`: Chỉ định bảng vật lý chứa dữ liệu entity

### 4.1. Vai trò của `@Table`

`@Table` từ `jakarta.persistence` cấu hình **bảng chính** (*primary table*) của entity:

~~~java
@Entity
@Table(name = "customer_account")
public class Customer {
    @Id
    private Long id;
}
~~~

Trong ví dụ này:

- Tên entity mặc định là `Customer`.
- Tên bảng chính là `customer_account`.
- JPQL dùng `Customer`, còn SQL chạy với bảng `customer_account`.

Không có `@Table` vẫn có thể là một entity hợp lệ. JPA có quy tắc tên bảng mặc định dựa trên tên entity; tuy nhiên Hibernate, Spring Boot hoặc các provider/framework khác có thể áp dụng **naming strategy**, ví dụ biến dạng CamelCase sang snake_case.

Để hạn chế bất ngờ khi dùng schema đã có sẵn hoặc khi thay provider, hãy khai báo `@Table(name = "...")` rõ ràng cho những bảng quan trọng.

### 4.2. Thuộc tính `name`, `schema` và `catalog`

Ví dụ:

~~~java
@Entity(name = "CustomerAccount")
@Table(name = "customer_account", schema = "sales")
public class Customer {
    @Id
    private Long id;
}
~~~

JPA được hướng dẫn ánh xạ entity `CustomerAccount` tới bảng `customer_account` trong schema `sales`. Ở PostgreSQL, cách biểu diễn SQL thường tương ứng:

~~~sql
SELECT *
FROM sales.customer_account;
~~~

Các thuộc tính thường gặp:

| Thuộc tính của `@Table` | Ý nghĩa | Ví dụ |
|---|---|---|
| `name` | Tên bảng chính | `customer_account` |
| `schema` | Tên schema chứa bảng | `sales` |
| `catalog` | Tên catalog chứa bảng, nếu hệ DB hỗ trợ theo cách tương ứng | `shopdb` |
| `uniqueConstraints` | Mô tả ràng buộc UNIQUE khi tạo DDL | `@UniqueConstraint(...)` |
| `indexes` | Mô tả chỉ mục khi tạo DDL | `@Index(...)` |

Khái niệm *schema* và *catalog* không được các DB dùng giống hệt nhau. Khi triển khai, cần xác định provider và hệ quản trị cơ sở dữ liệu hiểu các thuộc tính này theo cách nào, cùng với quyền của tài khoản kết nối.

### 4.3. `@Table` không tự tạo bảng trong mọi ứng dụng

Annotation `@Table` cung cấp **metadata ánh xạ**. Việc tạo bảng thực tế còn phụ thuộc cấu hình schema generation và quy trình triển khai:

- Nếu ứng dụng được cấu hình để không sinh DDL, bảng phải được tạo trước bằng migration hoặc lệnh SQL.
- Nếu bật schema generation, provider có thể dùng metadata `@Table` và `@Column` để tạo DDL, trong phạm vi khả năng hỗ trợ.
- Nếu đã có dữ liệu ở production, đổi `@Table(name = "...")` trong mã nguồn **không tự di chuyển hoặc đổi tên bảng cũ** một cách an toàn.

Công cụ migration như Flyway hoặc Liquibase thường được dùng để kiểm soát thay đổi cấu trúc dữ liệu theo phiên bản. JPA mapping cần khớp schema hiện có sau migration.

### 4.4. `@Table` và `@Column` có vai trò khác nhau

~~~java
@Entity(name = "CustomerAccount")
@Table(name = "customer_account")
public class Customer {
    @Id
    @Column(name = "customer_id")
    private Long id;

    @Column(name = "full_name")
    private String fullName;
}
~~~

- `@Table(name = "customer_account")` ánh xạ **loại entity** tới bảng.
- `@Column(name = "customer_id")` và `@Column(name = "full_name")` ánh xạ **thuộc tính đơn giản** tới cột.
- `@Id` đánh dấu khóa chính; nó không đặt tên entity hoặc tên bảng.
- Tên thuộc tính Java `fullName` là thứ JPQL truy cập; tên cột SQL `full_name` là thứ SQL truy cập.

Các trường hợp liên kết quan hệ còn có `@JoinColumn` và `@JoinTable`; chúng có trách nhiệm riêng, không thay thế `@Table` cho bảng chính.

## 5. `@Id`: Định danh của từng entity, không phải tên entity

Đây là một điểm dễ nhầm trong chương “Entity và định danh”.

| Thành phần | Xác định cái gì? | Ví dụ |
|---|---|---|
| Tên entity | **Loại** entity trong metadata/JPQL | `CustomerAccount` |
| `@Table(name = ...)` | **Bảng vật lý** chứa dữ liệu | `customer_account` |
| `@Id` / `@EmbeddedId` | **Khóa chính của từng entity** | `id = 42` |
| Tên lớp Java | **Kiểu Java** dùng trong code | `Customer` |
| `@Column(name = ...)` | **Cột SQL** cho một thuộc tính | `customer_id` |

Ví dụ:

~~~java
Customer customer = entityManager.find(Customer.class, 42L);
~~~

JPA tìm instance có khóa chính `42` thuộc kiểu Java `Customer`. Khi câu JPQL:

~~~jpql
SELECT c FROM CustomerAccount c WHERE c.id = :id
~~~

được thực thi với `id = 42`, `CustomerAccount` cho biết **loại entity**, `c.id` truy cập thuộc tính định danh và `42` là **giá trị khóa chính**.

Trong cùng persistence context, JPA bảo đảm identity đối với cùng một loại entity và khóa chính (có xét các quy tắc kế thừa của mô hình). Gọi `find` hai lần cho cùng entity và ID thường nhận lại cùng một managed object:

~~~java
Customer first = entityManager.find(Customer.class, 42L);
Customer second = entityManager.find(Customer.class, 42L);

System.out.println(first == second); // true trong cùng persistence context
~~~

Điều này không liên quan đến việc có bao nhiêu connection JDBC hoặc việc tên bảng có giống tên entity hay không.

## 6. Ví dụ hoàn chỉnh: Tách tên lớp, entity, bảng và cột

Giả sử database PostgreSQL có schema `sales` với bảng:

~~~sql
CREATE SCHEMA sales;

CREATE TABLE sales.customer_account (
    customer_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE
);
~~~

Đây là DDL minh họa của PostgreSQL; cú pháp tự sinh khóa chính có thể khác ở những database khác.

Định nghĩa entity:

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity(name = "CustomerAccount")
@Table(name = "customer_account", schema = "sales")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "customer_id")
    private Long id;

    @Column(name = "full_name", nullable = false, length = 150)
    private String fullName;

    @Column(name = "email", nullable = false, unique = true, length = 255)
    private String email;

    protected Customer() {
        // JPA cần constructor không tham số.
    }

    public Customer(String fullName, String email) {
        this.fullName = fullName;
        this.email = email;
    }

    public Long getId() {
        return id;
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
~~~

Đọc cùng dữ liệu qua ba góc nhìn:

**A. Java API dùng lớp Java và khóa chính**

~~~java
Customer customer = entityManager.find(Customer.class, 42L);
~~~

**B. JPQL dùng tên entity và tên thuộc tính**

~~~java
List<Customer> customers = entityManager.createQuery(
        "SELECT c FROM CustomerAccount c WHERE c.email = :email",
        Customer.class)
    .setParameter("email", "lan@example.com")
    .getResultList();
~~~

**C. SQL dùng tên bảng và tên cột**

~~~sql
SELECT customer_id, full_name, email
FROM sales.customer_account
WHERE email = 'lan@example.com';
~~~

Trong chương trình, nên bind tham số cho SQL/JPQL thay vì ghép dữ liệu đầu vào vào chuỗi truy vấn. SQL trên chỉ minh họa tên bảng và cột; với JDBC thực tế, dùng `PreparedStatement`.

### JPA tạo SQL như thế nào?

Ở mức khái niệm, provider giải quyết các bước:

~~~text
JPQL: SELECT c FROM CustomerAccount c WHERE c.email = :email
                 |             |
                 v             v
       @Entity(name=...)    field email
                 |             |
                 v             v
          Java class       @Column(name="email")
                 |
         @Table(name="customer_account", schema="sales")
                 |
                 v
SQL: SELECT ... FROM sales.customer_account WHERE email = ?
~~~

Cú pháp SQL thực tế có thể khác theo provider, dialect, các cột được chọn, khóa và chiến lược fetching. Tuy nhiên nguyên tắc ánh xạ giữa **tên entity/thuộc tính ở JPQL** và **bảng/cột ở SQL** không đổi.

## 7. Khi không khai báo tên tường minh thì điều gì xảy ra?

Xét bốn trường hợp sau.

### Trường hợp A: Chỉ có `@Entity`

~~~java
@Entity
public class Book {
    @Id
    Long id;
}
~~~

Tên entity mặc định: `Book`. Tên bảng mặc định dựa trên tên entity theo quy tắc JPA, còn tên bảng vật lý quan sát được có thể bị tác động bởi naming strategy của provider/framework.

JPQL:

~~~jpql
SELECT b FROM Book b
~~~

### Trường hợp B: Có `@Table`, không có `@Entity(name)`

~~~java
@Entity
@Table(name = "library_book")
public class Book {
    @Id
    Long id;
}
~~~

Tên entity vẫn là `Book`. Tên bảng chính là `library_book`.

~~~jpql
SELECT b FROM Book b
~~~

### Trường hợp C: Có `@Entity(name)`, không có `@Table`

~~~java
@Entity(name = "CatalogBook")
public class Book {
    @Id
    Long id;
}
~~~

Tên entity là `CatalogBook`. Tên bảng sẽ theo ánh xạ mặc định gắn với tên entity và cách provider xử lý tên vật lý; không nên mặc định hệ thống sẽ dùng chính xác chữ hoa/thường `CatalogBook` trong SQL trên mọi DB/framework.

~~~jpql
SELECT b FROM CatalogBook b
~~~

### Trường hợp D: Đặt cả hai tên

~~~java
@Entity(name = "CatalogBook")
@Table(name = "library_book")
public class Book {
    @Id
    Long id;
}
~~~

Tên entity: `CatalogBook`. Tên bảng: `library_book`. Đây là trường hợp dễ minh họa nhất vì hai tầng tên được chỉ định rõ.

~~~jpql
SELECT b FROM CatalogBook b
~~~

~~~sql
SELECT * FROM library_book;
~~~

**Kết luận của bốn trường hợp:** `@Entity(name = "...")` điều khiển tên logic của entity; `@Table(name = "...")` điều khiển tên bảng chính. Không nên hoán đổi vị trí hai thuộc tính chỉ vì chúng đều tên `name`.

## 8. JPQL, native SQL và Spring Data JPA

### 8.1. Với `EntityManager.createQuery`

`createQuery` nhận JPQL, nên phần `FROM` tham chiếu tên entity:

~~~java
entityManager.createQuery(
    "SELECT c FROM CustomerAccount c WHERE c.fullName = :name",
    Customer.class
);
~~~

Nếu thay `CustomerAccount` bằng `customer_account`, truy vấn thường thất bại vì `customer_account` là tên bảng, không phải tên entity được khai báo.

### 8.2. Với `EntityManager.createNativeQuery`

`createNativeQuery` nhận câu SQL native:

~~~java
entityManager.createNativeQuery(
    "SELECT customer_id, full_name, email " +
    "FROM sales.customer_account WHERE customer_id = ?",
    Customer.class
).setParameter(1, 42L).getResultList();
~~~

Ở đây `sales.customer_account` và `customer_id` thuộc ngôn ngữ SQL; phần `Customer.class` chỉ yêu cầu JPA ánh xạ kết quả sang loại entity tương ứng. Ánh xạ kết quả native SQL phải cung cấp các cột cần thiết cho entity theo quy tắc và cấu hình của provider.

### 8.3. Với `@Query` của Spring Data JPA

Khi `nativeQuery` không bật, chuỗi trong `@Query` thường là JPQL:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface CustomerRepository extends JpaRepository<Customer, Long> {

    @Query("SELECT c FROM CustomerAccount c WHERE c.email = :email")
    List<Customer> findByEmailJpql(@Param("email") String email);

    @Query(
        value = "SELECT * FROM sales.customer_account WHERE email = :email",
        nativeQuery = true
    )
    List<Customer> findByEmailSql(@Param("email") String email);
}
~~~

Trong cùng interface:

- Method đầu tiên dùng `CustomerAccount` vì đó là tên entity JPQL.
- Method thứ hai dùng `sales.customer_account` vì `nativeQuery = true`.
- Kiểu `JpaRepository<Customer, Long>` dùng **lớp Java `Customer`** và **kiểu khóa chính `Long`**.

Spring Data có thêm truy vấn suy ra từ tên method (*derived query methods*), cũng sử dụng metadata thuộc tính của entity; không cần đặt tên method theo cột SQL.

## 9. Quan hệ một entity và một table không phải lúc nào cũng 1:1

Ví dụ một entity đơn giản thường ánh xạ một bảng chính. Nhưng JPA hỗ trợ các cách ánh xạ phức tạp hơn.

### 9.1. `@SecondaryTable`: Một entity có thể trải trên nhiều bảng

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.SecondaryTable;
import jakarta.persistence.Table;

@Entity(name = "UserProfile")
@Table(name = "app_user")
@SecondaryTable(name = "user_details")
public class User {

    @Id
    private Long id;

    @Column(name = "login")
    private String login;

    @Column(table = "user_details", name = "bio")
    private String bio;
}
~~~

`app_user` là bảng chính, `user_details` là bảng bổ sung. Hai bảng cần quan hệ khóa phù hợp để JPA ánh xạ các bản ghi về cùng một entity. Có thể cần `@PrimaryKeyJoinColumn` hoặc cấu hình bổ sung theo schema thực tế.

Tên entity vẫn là `UserProfile` và JPQL vẫn truy vấn cùng một entity:

~~~jpql
SELECT u FROM UserProfile u WHERE u.bio IS NOT NULL
~~~

### 9.2. Kế thừa entity có thể thay đổi số bảng

Với `@Inheritance`:

- `SINGLE_TABLE` thường lưu nhiều loại entity con vào cùng một bảng.
- `JOINED` có thể dùng bảng của lớp cha và các bảng lớp con, liên kết qua khóa.
- `TABLE_PER_CLASS` có mô hình bảng cho mỗi lớp concrete theo chiến lược riêng.

Vì vậy, không thể áp dụng quy tắc cứng “mỗi `@Entity` luôn tương ứng đúng một bảng khác biệt”.

### 9.3. Bảng trung gian trong quan hệ không phải bảng chính của entity

Trong quan hệ nhiều-nhiều, `@JoinTable` có thể xác định bảng liên kết:

~~~java
@ManyToMany
@JoinTable(
    name = "student_course",
    joinColumns = @JoinColumn(name = "student_id"),
    inverseJoinColumns = @JoinColumn(name = "course_id")
)
private Set<Course> courses = new HashSet<>();
~~~

Ở đây `student_course` là bảng liên kết của association, không phải tên entity `Student` hay bảng chính của nó. Tương tự, `@JoinColumn` thường xác định cột khóa ngoại, không dùng để đổi tên bảng entity.

### 9.4. `@MappedSuperclass` và `@Embeddable` không đồng nghĩa `@Entity`

~~~java
@MappedSuperclass
public abstract class AuditedRecord {
    @Column(name = "created_at")
    private java.time.Instant createdAt;
}
~~~

`@MappedSuperclass` đóng góp ánh xạ thuộc tính cho các entity con nhưng không tự tạo một entity có tên để JPQL truy vấn độc lập.

~~~java
@Embeddable
public class Address {
    private String city;
    private String street;
}
~~~

`@Embeddable` mô tả kiểu giá trị có thể nhúng vào entity bằng `@Embedded`; mặc định nó không phải một entity có identity và bảng riêng do chính annotation này tạo ra.

Những phân biệt này đặc biệt hữu ích khi thấy một class có annotation JPA nhưng không thể viết `SELECT x FROM ClassName x`.

## 10. `@Table` và các khai báo ràng buộc/chỉ mục

Bên cạnh tên bảng, `@Table` có thể mô tả unique constraints và indexes cho quá trình tạo schema:

~~~java
@Entity(name = "CustomerAccount")
@Table(
    name = "customer_account",
    schema = "sales",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_customer_account_email",
            columnNames = {"email"}
        )
    },
    indexes = {
        @Index(
            name = "idx_customer_account_full_name",
            columnList = "full_name"
        )
    }
)
public class Customer {
    @Id
    private Long id;

    @Column(name = "email", nullable = false)
    private String email;

    @Column(name = "full_name")
    private String fullName;
}
~~~

Ý nghĩa:

- `uniqueConstraints` mô tả ràng buộc duy nhất của bảng trong metadata DDL; thuộc tính `columnNames` tham chiếu **tên cột SQL**, không phải Java field.
- `indexes` mô tả các chỉ mục phục vụ schema generation; `columnList` dùng danh sách tên cột SQL với cú pháp được JPA hỗ trợ.
- Nếu schema production được quản lý bằng migration và JPA không sinh DDL, chỉ thêm annotation chưa bảo đảm ràng buộc/chỉ mục đã tồn tại trong DB.

Cơ sở dữ liệu mới là nơi thực sự thực thi tính duy nhất/khóa và tối ưu truy vấn bằng index. Tại tầng ứng dụng, vẫn cần xử lý exception khi constraint bị vi phạm.

## 11. Đặt tên thế nào để dễ bảo trì?

### 11.1. Dùng tên có ý nghĩa ở đúng tầng

Ví dụ một quy ước:

| Tầng | Ví dụ | Cách chọn |
|---|---|---|
| Java class | `PurchaseOrder` | PascalCase, diễn đạt đối tượng nghiệp vụ |
| Entity name | `PurchaseOrder` hoặc `OrderRecord` | Tên logic dễ hiểu, duy nhất trong PU |
| Table | `purchase_order` hoặc `purchase_orders` | Theo quy ước DB của dự án |
| Java property | `createdAt` | camelCase |
| SQL column | `created_at` | Theo quy ước DB |
| Primary key | `id`/`orderId` trong Java, `order_id` trong DB | Rõ ràng và nhất quán |

JPA không bắt buộc tất cả các tầng phải cùng một tên. Nên chọn quy ước đủ rõ để người đọc biết khi nào đang nói đến Java, JPQL hay SQL.

### 11.2. Hạn chế phụ thuộc vào naming strategy khi có schema sẵn

Một framework có thể tự chuyển `PurchaseOrder` thành `purchase_order`; framework khác có thể sinh tên khác hoặc yêu cầu cấu hình bổ sung. Nếu database đã được thiết kế và quản lý độc lập với JPA, ánh xạ tường minh giúp code phù hợp với schema hơn:

~~~java
@Entity(name = "PurchaseOrder")
@Table(name = "purchase_order")
public class OrderEntity {

    @Id
    @Column(name = "order_id")
    private Long id;
}
~~~

Dù lớp Java tên `OrderEntity`, JPQL vẫn là `FROM PurchaseOrder` và SQL vẫn làm việc với bảng `purchase_order`.

### 11.3. Cẩn thận với chữ hoa/thường và từ khóa SQL

Một số cơ sở dữ liệu phân biệt hoặc chuẩn hóa chữ hoa/thường của identifier, đặc biệt khi dùng dấu nháy cho tên bảng/cột. Tên như `user`, `order` có thể đụng từ khóa trong một số hệ DB. Provider có cơ chế quoting/escaping identifier nhưng cú pháp và chiến lược khác nhau.

Một cách thực tế là chọn tên bảng tránh từ khóa dễ gây xung đột (ví dụ `app_user`, `purchase_order`), dùng tên chữ thường nhất quán và khai báo ánh xạ chính xác. Đừng giả định đổi `@Entity(name = "...")` sẽ giải quyết lỗi SQL liên quan tên bảng reserved keyword.

### 11.4. Đổi tên ở tầng nào gây ảnh hưởng gì?

| Thay đổi | Ảnh hưởng trực tiếp |
|---|---|
| Đổi tên lớp `Customer` thành `Client` | Code Java, import, repository, reflection và có thể tên entity mặc định |
| Đổi `@Entity(name = "CustomerAccount")` | JPQL, named queries và các tham chiếu logic đến tên entity |
| Đổi `@Table(name = "customer_account")` | Ánh xạ tới bảng SQL; cần đồng bộ cấu trúc database/migration |
| Đổi `@Column(name = "full_name")` | Ánh xạ tên cột SQL; cần khớp schema và query native |
| Đổi tên thuộc tính `fullName` | Code Java, JPQL, derived repository methods và mapping liên quan |
| Đổi giá trị khóa chính `id` | Ảnh hưởng định danh bản ghi, quan hệ và tính toàn vẹn tham chiếu; không phải thao tác đổi tên |

Đặc biệt, nếu tên entity đang dùng giá trị mặc định theo tên lớp, đổi tên class có thể làm hỏng JPQL trước đây dù database chưa thay đổi. Có thể cố định `@Entity(name = "...")` nếu cần giữ tên truy vấn ổn định qua quá trình refactor class.

## 12. Lỗi thường gặp và cách suy luận

### Lỗi 1: JPQL báo không tìm thấy entity

Cấu hình:

~~~java
@Entity(name = "CustomerAccount")
@Table(name = "customer_account")
class Customer {
    @Id
    Long id;
}
~~~

Nhưng code dùng:

~~~java
entityManager.createQuery("SELECT c FROM Customer c");
~~~

**Nguyên nhân:** tên entity đã khai báo là `CustomerAccount`, không phải `Customer`.

**Cách sửa:**

~~~java
entityManager.createQuery("SELECT c FROM CustomerAccount c");
~~~

Với truy vấn dùng `Customer.class` để ánh xạ kết quả, tên lớp vẫn là `Customer`.

### Lỗi 2: Dùng tên bảng trong JPQL

~~~java
entityManager.createQuery(
    "SELECT c FROM customer_account c WHERE c.full_name = :name");
~~~

Trong JPQL thuần, `customer_account` không phải tên entity và `full_name` không phải thuộc tính Java `fullName`.

Câu JPQL tương ứng là:

~~~jpql
SELECT c FROM CustomerAccount c WHERE c.fullName = :name
~~~

Nếu muốn dùng bảng và cột SQL, cần chọn truy vấn native phù hợp.

### Lỗi 3: Nghĩ `@Table` đã khiến bảng tồn tại

Entity được khai báo:

~~~java
@Entity
@Table(name = "order_line")
class OrderLine {
    @Id
    Long id;
}
~~~

Nhưng database báo không thấy bảng `order_line`. **`@Table` chỉ là metadata ánh xạ**; phải xác nhận bảng thực sự tồn tại trong schema/catalog đang kết nối và có đúng quyền truy cập. Nếu bật schema generation, cần xem cấu hình và log thực thi; nếu dùng migration, cần kiểm tra migration đã chạy.

### Lỗi 4: Hai entity trùng tên logic

Hai class `User` ở package khác nhau đều `@Entity` nhưng không đặt `name`. Có thể gây trùng tên entity trong persistence unit. Giải pháp là đặt tên logic riêng bằng `@Entity(name = "...")`, hoặc điều chỉnh phạm vi PU nếu đó mới là nguyên nhân của trùng lặp.

### Lỗi 5: Tên bảng chạy sai dù `@Table` có vẻ đúng

Xem thêm các yếu tố: `schema`, `catalog`, naming strategy, quoting/case sensitivity, cấu hình datasource, phiên bản schema thực tế và SQL mà provider tạo. Việc đổi tên entity thường không sửa được lỗi tên bảng sai nếu đã chỉ định `@Table(name)` tường minh.

### Lỗi 6: Đổi tên entity làm named query hỏng

~~~java
@NamedQuery(
    name = "Customer.findAll",
    query = "SELECT c FROM CustomerAccount c"
)
~~~

`Customer.findAll` là **tên định danh named query**; `CustomerAccount` bên trong là **tên entity JPQL**. Hai tên có vai trò khác nhau. Khi đổi tên entity, phải rà soát phần nội dung JPQL của named query và các query khác. Không nên sửa tất cả chuỗi giống chữ “Customer” một cách máy móc.

## 13. Bài tập áp dụng

### Bài 1: Đọc annotation

Cho lớp:

~~~java
@Entity(name = "InventoryItem")
@Table(name = "warehouse_product", schema = "warehouse")
public class Product {

    @Id
    @Column(name = "product_id")
    private Long id;

    @Column(name = "product_name")
    private String name;
}
~~~

Hãy chỉ ra tên lớp Java, tên entity, tên bảng, khóa chính, cột SQL cho `name`, JPQL hợp lệ và SQL tương ứng.

**Đáp án:**

- Lớp Java: `Product`.
- Tên entity: `InventoryItem`.
- Bảng: `warehouse.warehouse_product`.
- Thuộc tính định danh Java: `id`, ánh xạ cột `product_id`.
- Thuộc tính Java `name` ánh xạ cột `product_name`.
- JPQL: `SELECT p FROM InventoryItem p WHERE p.name = :name`.
- SQL (minh họa): `SELECT * FROM warehouse.warehouse_product WHERE product_name = ?`.

### Bài 2: Dự đoán tác động của đổi tên

Ban đầu:

~~~java
@Entity
@Table(name = "customer")
class Customer {
    @Id
    Long id;
}
~~~

Sau khi đổi tên class thành `Client` nhưng giữ nguyên `@Table(name = "customer")`, chuyện gì có thể xảy ra?

**Đáp án:** nếu không có `@Entity(name = "...")`, tên entity mặc định đổi từ `Customer` sang `Client`. JPQL `FROM Customer` cũ cần được cập nhật thành `FROM Client`, trong khi ánh xạ bảng chính vẫn là `customer`. Code Java dùng `Customer.class` cũng cần cập nhật thành `Client.class`.

### Bài 3: Nhận diện tên “id”

Có một managed entity kiểu `Customer` với `id = 7`. Có thể suy ra bảng tên `Customer` và tên entity bằng `7` không?

**Đáp án:** không. `7` là giá trị khóa chính của một instance, không phải tên entity. Tên entity lấy từ `@Entity(name)` hoặc giá trị mặc định; tên bảng lấy từ `@Table(name)` hoặc cơ chế mặc định và naming strategy. Cả ba độc lập về ý nghĩa.

### Bài 4: Chọn JPQL hay SQL

Entity:

~~~java
@Entity(name = "SalesInvoice")
@Table(name = "invoice_header")
class Invoice {
    @Id Long id;
}
~~~

Đánh dấu câu phù hợp:

| Câu truy vấn | Kết luận |
|---|---|
| `SELECT i FROM SalesInvoice i` dùng với `createQuery` | Hợp lệ về cách tham chiếu entity |
| `SELECT i FROM invoice_header i` dùng với `createQuery` | Sai nếu `invoice_header` không được khai báo là tên entity |
| `SELECT * FROM invoice_header` dùng với `createNativeQuery` | Hợp lệ về cách tham chiếu bảng (nếu bảng tồn tại) |
| `SELECT i FROM Invoice i` dùng với `createQuery` | Sai nếu tên entity đã được đặt là `SalesInvoice` |

Các câu hợp lệ về tên vẫn còn phụ thuộc schema, thuộc tính và ngữ cảnh thực thi; bảng chỉ đánh giá việc sử dụng đúng tầng tên.

## 14. Ghi nhớ cốt lõi

Có thể hình dung ba lớp tên như sau:

~~~text
Java code                    JPA / JPQL                 Database / SQL
-------------------------    -----------------------    --------------------------
class Customer               entity CustomerAccount    table sales.customer_account
field fullName               property c.fullName       column full_name
field id                     property c.id             PK column customer_id
Customer.class               FROM CustomerAccount c    FROM sales.customer_account
~~~

- **`@Entity`** xác nhận lớp là một entity được JPA quản lý; `@Entity(name)` đặt **tên logic** để truy vấn trong JPQL.
- **`@Table`** chỉ định **bảng chính** và tùy chọn schema/catalog, không quyết định tên entity JPQL.
- **`@Id` / `@EmbeddedId`** xác định **khóa chính của từng entity**, khác với tên loại entity.
- **JPQL dùng tên entity và thuộc tính Java; SQL dùng tên bảng và tên cột**.
- Một entity có thể liên quan nhiều bảng hoặc chia sẻ bảng theo chiến lược ánh xạ; `@MappedSuperclass` và `@Embeddable` không tự động là entity.
- Việc đổi tên phải xét đúng tầng: mã Java, metadata entity, JPQL hay schema database; các thay đổi bảng/cột vật lý cần phối hợp với migration.

Khi phân biệt rõ các khái niệm này, lập trình viên có thể đọc ánh xạ JPA chính xác, viết truy vấn đúng ngôn ngữ, lý giải được SQL do provider sinh ra và refactor tên lớp hoặc tên bảng mà không vô tình làm hỏng phần còn lại của ứng dụng.
