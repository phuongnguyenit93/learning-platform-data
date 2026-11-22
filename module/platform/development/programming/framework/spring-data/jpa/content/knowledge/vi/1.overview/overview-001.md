# Spring Data JPA là gì và giải quyết vấn đề truy cập dữ liệu nào?

## 1. Bối cảnh: vì sao ứng dụng cần một lớp truy cập dữ liệu?

Một ứng dụng Java thường làm việc với dữ liệu nghiệp vụ như người dùng, đơn hàng, sản phẩm hoặc hóa đơn. Trong cơ sở dữ liệu quan hệ, dữ liệu đó được lưu trong bảng, hàng và cột. Trong Java, chương trình lại thao tác với đối tượng, thuộc tính và quan hệ giữa các lớp.

Để đọc hoặc ghi dữ liệu, ứng dụng phải chuyển đổi giữa hai cách biểu diễn này và phối hợp nhiều công việc:

- Mở và quản lý kết nối đến cơ sở dữ liệu.
- Viết câu lệnh SQL, truyền tham số và thực thi câu lệnh.
- Đọc `ResultSet`, chuyển từng hàng thành đối tượng Java và xử lý giá trị `NULL`.
- Thực hiện các thao tác thêm, đọc, sửa, xóa (CRUD).
- Quản lý transaction để nhiều thao tác cùng thành công hoặc cùng thất bại.
- Xây dựng truy vấn tìm kiếm, sắp xếp và phân trang.
- Xử lý lỗi truy cập dữ liệu và giải phóng tài nguyên đúng cách.

Nếu tự làm tất cả bằng JDBC, mỗi DAO thường phải lặp lại nhiều đoạn mã tương tự. Khi số lượng entity và truy vấn tăng, phần mã hạ tầng có thể chiếm nhiều thời gian hơn phần logic nghiệp vụ. Đây là vấn đề mà JPA và Spring Data JPA giúp giải quyết ở những tầng khác nhau.

## 2. Spring Data JPA là gì?

**Spring Data JPA** là một module thuộc hệ sinh thái Spring Data. Nó cung cấp cách xây dựng lớp truy cập dữ liệu dựa trên **JPA (Jakarta Persistence)** bằng các repository interface. Thay vì phải tự viết một lớp DAO với các phương thức CRUD phổ biến, lập trình viên khai báo interface và Spring Data JPA tạo phần triển khai phù hợp khi ứng dụng khởi động.

Cần phân biệt ba thành phần:

- **JPA / Jakarta Persistence** là đặc tả chuẩn của Java cho việc ánh xạ đối tượng Java với dữ liệu quan hệ (ORM), quản lý entity, persistence context và truy vấn bằng JPQL.
- **JPA provider** là thư viện thực thi đặc tả JPA. Hibernate là provider được sử dụng phổ biến; EclipseLink là một lựa chọn khác. Provider chịu trách nhiệm theo dõi trạng thái entity và tạo SQL để làm việc với cơ sở dữ liệu.
- **Spring Data JPA** xây dựng trên JPA, bổ sung repository abstraction, cơ chế tạo truy vấn từ tên phương thức và tích hợp với Spring để giảm mã truy cập dữ liệu lặp lại.

Vì vậy, Spring Data JPA không phải là cơ sở dữ liệu, không phải bản thân đặc tả JPA và cũng không phải JPA provider. Nó không thay thế Hibernate; trong một ứng dụng thông thường, Spring Data JPA sử dụng một provider như Hibernate ở phía dưới.

### Luồng xử lý tổng quát

~~~text
Controller / lớp gọi
        |
        v
Service (logic nghiệp vụ, transaction)
        |
        v
Repository interface
        |
        v
Spring Data JPA tạo proxy triển khai repository
        |
        v
JPA EntityManager / Persistence Context
        |
        v
JPA provider (ví dụ: Hibernate)
        |
        v
JDBC và driver
        |
        v
Cơ sở dữ liệu quan hệ
~~~

Khi ứng dụng khởi động, Spring phát hiện các repository interface và tạo đối tượng triển khai dạng proxy. Khi mã ứng dụng gọi `userRepository.findById(1L)`, proxy chuyển yêu cầu xuống JPA. JPA provider thực hiện công việc ánh xạ và truy vấn, sau đó kết quả được trả về dưới dạng entity hoặc kiểu dữ liệu mà phương thức khai báo.

## 3. Những vấn đề Spring Data JPA giải quyết

### 3.1. Giảm mã DAO và CRUD lặp lại

Với JDBC thuần, một phương thức tìm người dùng thường phải viết SQL, tạo `PreparedStatement`, truyền tham số, đọc `ResultSet`, dựng đối tượng và đóng tài nguyên. Các phương thức thêm, sửa, xóa lại có phần mã tương tự.

Spring Data JPA cung cấp sẵn các thao tác repository phổ biến. Chỉ cần khai báo:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {
}
~~~

Với `JpaRepository<User, Long>`, ứng dụng có sẵn những thao tác như:

- `save(user)`: lưu entity mới hoặc cập nhật entity theo cơ chế trạng thái của JPA.
- `findById(id)`: tìm entity theo khóa chính, kết quả được biểu diễn bằng `Optional<User>`.
- `findAll()`: lấy danh sách entity.
- `existsById(id)`: kiểm tra entity có tồn tại theo khóa chính hay không.
- `deleteById(id)`: xóa entity theo khóa chính.
- `count()`: đếm số entity.

Tham số kiểu `User` là loại entity được quản lý; `Long` là kiểu của khóa chính. Spring Data JPA cung cấp phần triển khai cho các phương thức kế thừa, nên không cần tự viết lớp `UserRepositoryImpl` chỉ để thực hiện CRUD cơ bản.

### 3.2. Tạo truy vấn từ tên phương thức

Nhiều truy vấn tìm kiếm thông thường có thể được mô tả bằng tên phương thức. Spring Data JPA phân tích tên phương thức và tạo truy vấn dựa trên thuộc tính của entity.

Ví dụ, nếu entity `User` có các thuộc tính `email` và `name`:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {
    Optional<User> findByEmail(String email);

    List<User> findByNameContainingIgnoreCase(String keyword);
}
~~~

Ý nghĩa:

- `findByEmail`: tìm entity có thuộc tính `email` bằng giá trị truyền vào.
- `Containing`: tìm giá trị có chứa chuỗi được truyền vào.
- `IgnoreCase`: so sánh không phân biệt chữ hoa và chữ thường đối với phép so sánh chuỗi được hỗ trợ.

Tên phương thức phải khớp với thuộc tính entity. Ví dụ, `findByMail` sẽ không hợp lệ nếu entity chỉ có thuộc tính `email`. Spring Data JPA kiểm tra và phân tích phương thức khi khởi tạo repository; lỗi tên thuộc tính hoặc cú pháp có thể khiến ứng dụng không khởi động được.

Cơ chế này giúp tránh phải viết SQL hoặc JPQL cho mọi truy vấn đơn giản. Tuy nhiên, tên phương thức có thể trở nên dài và khó đọc nếu điều kiện quá phức tạp.

### 3.3. Hỗ trợ truy vấn tùy chỉnh bằng JPQL hoặc SQL

Khi truy vấn cần biểu đạt rõ ràng hơn, có thể khai báo `@Query` ngay trong repository:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    @Query("select u from User u where lower(u.email) = lower(:email)")
    Optional<User> findOneByEmail(@Param("email") String email);
}
~~~

JPQL truy vấn theo **entity và thuộc tính Java**, không truy vấn trực tiếp theo tên bảng và tên cột như SQL thông thường. JPA provider chuyển JPQL thành câu lệnh phù hợp với cơ sở dữ liệu đang sử dụng.

Nếu thật sự cần cú pháp riêng của một hệ quản trị cơ sở dữ liệu, có thể dùng native SQL:

~~~java
@Query(value = "select * from users where email = :email", nativeQuery = true)
Optional<User> findUsingSql(@Param("email") String email);
~~~

Native query hữu ích khi cần tính năng đặc thù hoặc câu SQL đã được tối ưu cho một hệ quản trị cụ thể. Đổi lại, nó có thể làm giảm tính độc lập với hệ quản trị cơ sở dữ liệu. Tên bảng và cột trong ví dụ phải khớp với schema thực tế.

### 3.4. Chuẩn hóa phân trang và sắp xếp

Một màn hình danh sách thường không nên tải toàn bộ dữ liệu cùng lúc. Spring Data JPA tích hợp `Pageable`, `Page` và `Sort` để yêu cầu một phần dữ liệu theo trang và thứ tự mong muốn.

~~~java
Page<User> findByNameContainingIgnoreCase(
    String keyword,
    Pageable pageable
);
~~~

Cách gọi:

~~~java
Pageable request = PageRequest.of(
    0,
    20,
    Sort.by("name").ascending()
);

Page<User> result =
    userRepository.findByNameContainingIgnoreCase("an", request);
~~~

Trang được đánh số từ `0`, nên `PageRequest.of(0, 20, ...)` yêu cầu trang đầu tiên với tối đa 20 bản ghi. `Page` cung cấp dữ liệu trang hiện tại cùng thông tin như tổng số phần tử và tổng số trang. Để có tổng số phần tử, truy vấn phân trang thường cần thêm truy vấn đếm. Nếu chỉ cần biết còn trang tiếp theo hay không mà không cần tổng số bản ghi, có thể cân nhắc `Slice`.

Tên trường trong `Sort` phải là thuộc tính entity hợp lệ. Không nên nhận trực tiếp tên cột hoặc biểu thức sắp xếp tùy ý từ đầu vào người dùng.

### 3.5. Tích hợp với Spring và transaction

Repository là bean do Spring quản lý nên có thể được inject vào service bằng constructor. Điều này giúp phân chia trách nhiệm: repository tập trung vào truy cập dữ liệu, còn service điều phối quy tắc nghiệp vụ và ranh giới transaction.

~~~java
@Service
public class UserService {
    private final UserRepository users;

    public UserService(UserRepository users) {
        this.users = users;
    }

    @Transactional
    public User register(String name, String email) {
        User user = new User(name, email);
        return users.save(user);
    }

    @Transactional(readOnly = true)
    public Optional<User> findByEmail(String email) {
        return users.findByEmail(email);
    }
}
~~~

`@Transactional` đặt ranh giới transaction ở thao tác nghiệp vụ. Ví dụ, nếu một nghiệp vụ phải lưu đơn hàng và các dòng chi tiết, đặt các thao tác trong cùng một transaction giúp chúng được commit hoặc rollback như một đơn vị. `readOnly = true` thể hiện ý định chỉ đọc và có thể giúp framework/provider tối ưu trong một số trường hợp; đây không phải cơ chế bảo đảm rằng mã bên trong tuyệt đối không thể ghi dữ liệu.

Các phương thức CRUD kế thừa từ repository có cấu hình transaction mặc định của Spring Data JPA. Với phương thức nghiệp vụ gồm nhiều bước hoặc truy vấn tự khai báo, nên xác định transaction ở service để ranh giới giao dịch phản ánh đúng nghiệp vụ.

## 4. Entity và repository phối hợp như thế nào?

Entity là lớp Java được JPA quản lý và ánh xạ tới bảng trong cơ sở dữ liệu. Ví dụ dưới đây là một phần khai báo entity `User`:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "users")
public class User {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, unique = true)
    private String email;

    protected User() {
        // JPA cần constructor không tham số với phạm vi phù hợp.
    }

    public User(String name, String email) {
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

Các annotation chính:

- `@Entity` đánh dấu lớp là entity được JPA quản lý.
- `@Table(name = "users")` chỉ định bảng tương ứng.
- `@Id` đánh dấu khóa chính.
- `@GeneratedValue` cấu hình cách sinh khóa chính; `IDENTITY` thường dùng cột tự tăng nếu hệ quản trị hỗ trợ.
- `@Column` cấu hình ánh xạ và một số ràng buộc của cột.

Sau đó repository khai báo kiểu entity và kiểu khóa chính:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface UserRepository extends JpaRepository<User, Long> {
    Optional<User> findByEmail(String email);
}
~~~

Spring Data JPA sử dụng JPA metadata của `User` để làm việc với entity. Khi gọi `save`, repository chuyển entity tới JPA `EntityManager`. Với entity mới, JPA thường dùng thao tác persist; với entity đã tồn tại, cơ chế lưu có thể dùng merge dựa trên cách Spring Data nhận diện trạng thái mới của entity. Câu lệnh SQL thực tế có thể chưa chạy ngay tại thời điểm gọi `save`; JPA có thể trì hoãn việc đồng bộ xuống cơ sở dữ liệu cho tới lúc flush hoặc commit transaction.

**Lưu ý về phiên bản:** Spring Boot 3 trở lên sử dụng namespace `jakarta.persistence` như ví dụ. Các dự án Spring Boot 2 cũ thường dùng `javax.persistence`. Không trộn hai namespace trong cùng một dự án.

## 5. Spring Data JPA giúp được gì và không tự giải quyết điều gì?

| Nhu cầu | Spring Data JPA hỗ trợ như thế nào |
|---|---|
| CRUD lặp lại | Cung cấp sẵn phương thức repository qua `JpaRepository`. |
| Truy vấn lọc phổ biến | Sinh truy vấn từ tên phương thức như `findByEmail`. |
| Truy vấn tùy chỉnh | Hỗ trợ JPQL qua `@Query` và native SQL khi cần. |
| Phân trang, sắp xếp | Tích hợp `Pageable`, `Page`, `Slice` và `Sort`. |
| Tích hợp Spring | Repository được quản lý như bean và phối hợp với transaction của Spring. |
| Ánh xạ đối tượng và quan hệ | Dựa vào JPA và provider để ánh xạ entity, quản lý trạng thái và quan hệ. |

Tuy nhiên, Spring Data JPA không tự động giải quyết mọi vấn đề dữ liệu:

1. **Không thay thế thiết kế cơ sở dữ liệu.** Lập trình viên vẫn phải thiết kế bảng, khóa, ràng buộc, chỉ mục và quan hệ phù hợp.
2. **Không loại bỏ hoàn toàn SQL.** Truy vấn phức tạp có thể cần JPQL hoặc native SQL. Cần hiểu truy vấn được sinh ra để đánh giá hiệu năng.
3. **Không tự bảo đảm truy vấn luôn nhanh.** Tải quan hệ không phù hợp có thể gây vấn đề N+1; truy vấn phân trang sâu, thiếu index hoặc join không hợp lý vẫn có thể chậm.
4. **Không thay thế kiến thức về transaction.** Cần chọn ranh giới transaction, hiểu commit/rollback và cân nhắc xử lý đồng thời. Với dữ liệu cần phát hiện cập nhật cạnh tranh, có thể dùng optimistic locking với `@Version` hoặc cơ chế khóa phù hợp.
5. **Không loại bỏ việc quản lý vòng đời entity.** Cần hiểu entity mới, entity đang được quản lý, entity detached, persistence context, lazy loading và thời điểm flush.
6. **Không phải lựa chọn tốt nhất cho mọi tác vụ.** Các tác vụ báo cáo phức tạp, xử lý hàng loạt lớn hoặc phụ thuộc sâu vào tính năng riêng của cơ sở dữ liệu có thể phù hợp hơn với JDBC, truy vấn SQL chuyên biệt hoặc công cụ khác.

Ví dụ, việc gọi `findAll()` trên một bảng có hàng triệu bản ghi vẫn có thể gây tải lớn vì nó yêu cầu lấy toàn bộ kết quả. Có repository không đồng nghĩa với việc mọi truy vấn đều được phân trang hoặc tối ưu tự động.

## 6. Khi nào nên sử dụng Spring Data JPA?

Spring Data JPA phù hợp khi:

- Ứng dụng Java dùng Spring và lưu dữ liệu nghiệp vụ trong cơ sở dữ liệu quan hệ.
- Mô hình dữ liệu có entity và quan hệ rõ ràng.
- Phần lớn thao tác là CRUD và truy vấn theo điều kiện nghiệp vụ.
- Muốn tổ chức lớp truy cập dữ liệu nhất quán, dễ kiểm thử và giảm mã lặp.
- Cần kết hợp repository với transaction, dependency injection và các thành phần Spring khác.

Có thể cân nhắc JDBC hoặc giải pháp truy vấn chuyên biệt khi ứng dụng cần kiểm soát SQL rất chi tiết, thao tác hàng loạt lớn, truy vấn báo cáo phức tạp hoặc tận dụng sâu tính năng riêng của hệ quản trị cơ sở dữ liệu. Hai cách tiếp cận cũng có thể cùng tồn tại trong một ứng dụng nếu mỗi cách được dùng cho đúng loại công việc.

## 7. Cách ghi nhớ các khái niệm

- **JDBC:** API mức thấp để Java giao tiếp với cơ sở dữ liệu bằng SQL.
- **JPA:** đặc tả ORM quy định cách ánh xạ và quản lý entity.
- **Hibernate:** một JPA provider thực thi đặc tả JPA.
- **Spring Data JPA:** lớp tiện ích của Spring Data giúp khai báo repository, sinh các thao tác CRUD và truy vấn, đồng thời tích hợp với Spring.

Điểm cốt lõi là Spring Data JPA giảm công việc viết và duy trì mã truy cập dữ liệu lặp lại. Lập trình viên tập trung khai báo entity, repository và truy vấn theo nhu cầu nghiệp vụ; JPA provider đảm nhiệm phần ORM và tương tác SQL ở tầng thấp hơn. Để sử dụng hiệu quả, vẫn cần hiểu JPA, transaction, SQL và hiệu năng cơ sở dữ liệu.

---

**Phạm vi của các ví dụ:** Các đoạn Java ở trên là những phần mã minh họa trong một ứng dụng Spring Boot có dependency Spring Data JPA và driver cơ sở dữ liệu phù hợp; chúng không phải một chương trình Java độc lập có thể biên dịch chỉ bằng `javac`. Trong dự án thực tế, cần bổ sung cấu hình datasource, dependency của cơ sở dữ liệu, lớp khởi động Spring Boot và các phần còn lại của entity theo yêu cầu ứng dụng.