# Phân biệt quản lý entity và quản lý kết nối JDBC

Trong kiến trúc JPA, hai khái niệm dễ bị nhầm lẫn là **quản lý entity** và **quản lý kết nối JDBC**. Cả hai đều tham gia quá trình lưu dữ liệu vào cơ sở dữ liệu quan hệ, nhưng chúng quản lý những tài nguyên khác nhau và giải quyết những vấn đề khác nhau.

- **Quản lý entity** trả lời: *Đối tượng Java nào đang được theo dõi? Trạng thái của nó thay đổi thế nào? Khi nào các thay đổi cần được đồng bộ thành câu lệnh SQL?*
- **Quản lý kết nối JDBC** trả lời: *Ứng dụng lấy kết nối đến cơ sở dữ liệu ở đâu? Câu lệnh SQL chạy qua kết nối nào? Giao dịch được commit/rollback và kết nối được trả về pool ra sao?*

Hiểu sự khác biệt này giúp giải thích vì sao đổi một thuộc tính của entity có thể cập nhật cơ sở dữ liệu mà không viết câu lệnh `UPDATE`, vì sao gọi `flush()` chưa phải là `commit()`, và vì sao đóng `EntityManager` không đồng nghĩa với đóng toàn bộ connection pool.

## 1. Hai tầng trách nhiệm trong cùng một luồng lưu trữ

Trong ứng dụng dùng JPA, lập trình viên thường thao tác ở tầng đối tượng. JPA provider (ví dụ Hibernate) quản lý persistence context, tạo SQL cần thiết và thường sử dụng JDBC để giao tiếp với cơ sở dữ liệu quan hệ.

~~~text
Ứng dụng / tầng nghiệp vụ
    |
    | thao tác đối tượng Java
    v
JPA API: EntityManager
    |
    v
Persistence Context
    |  theo dõi entity, nhận biết thay đổi, quyết định đồng bộ
    v
JPA Provider / ORM (ví dụ Hibernate)
    |  sinh và thực thi SQL
    v
JDBC: DataSource -> Connection -> PreparedStatement
    |
    v
Cơ sở dữ liệu quan hệ
~~~

Nếu dùng JDBC trực tiếp, đường đi ngắn hơn ở tầng ứng dụng:

~~~text
Ứng dụng / tầng nghiệp vụ
    |
    | tự viết SQL, tự gán tham số và đọc kết quả
    v
DataSource / Connection Pool
    |
    v
JDBC: Connection -> PreparedStatement -> ResultSet
    |
    v
Cơ sở dữ liệu quan hệ
~~~

JPA và JDBC không phải hai loại kết nối cạnh tranh nhau. **JPA là API quản lý persistence và ánh xạ đối tượng–quan hệ; JDBC là API giao tiếp với cơ sở dữ liệu bằng SQL và kết nối.** Trong cách triển khai JPA quan hệ phổ biến, JPA provider sử dụng JDBC ở tầng thấp hơn.

### Bảng phân biệt nhanh

| Góc nhìn | Quản lý entity với JPA | Quản lý kết nối với JDBC |
|---|---|---|
| Đối tượng trung tâm | `EntityManager`, persistence context, entity | `DataSource`, `Connection`, `Statement`, `ResultSet` |
| Tài nguyên được quản lý | Đối tượng Java và trạng thái của chúng | Kết nối/phiên làm việc với cơ sở dữ liệu và tài nguyên JDBC |
| Cách làm việc | `persist`, `find`, `remove`, sửa thuộc tính entity | Viết SQL, bind tham số, chạy lệnh, đọc kết quả |
| Theo dõi thay đổi đối tượng | Có, với entity đang ở trạng thái managed | Không; object Java là object thông thường |
| Tạo câu lệnh SQL | Provider có thể tự sinh SQL từ thao tác entity | Lập trình viên chủ động viết SQL |
| Đơn vị phạm vi | Persistence context, thường gắn với giao dịch hoặc `EntityManager` | Kết nối được mượn từ `DataSource`/pool, thường phục vụ một đơn vị công việc |
| Giao dịch | Thông qua JPA/JTA/Spring; thay đổi entity được flush trong giao dịch | Qua `Connection` hoặc bộ quản lý giao dịch bên ngoài |
| Giải phóng | Đóng `EntityManager`, kết thúc context theo cấu hình | Đóng `ResultSet`/`Statement`/`Connection`; connection pool thường nhận lại kết nối |
| Liên kết một–một? | Không thể suy ra mỗi entity hay mỗi `EntityManager` có một kết nối riêng | Một kết nối có thể thực thi nhiều câu lệnh SQL |
| Rủi ro hay gặp | Entity detached, dữ liệu stale, flush bất ngờ, N+1 query | Rò rỉ connection, quên rollback/close, SQL injection, sai phạm vi giao dịch |

## 2. Quản lý entity: Persistence context theo dõi *đối tượng*

### 2.1. Entity là gì?

Một entity là lớp Java được ánh xạ với dữ liệu bền vững. Ví dụ:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
        // Constructor cho JPA
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

`@Entity` chỉ ra rằng lớp có thể được JPA quản lý và ánh xạ với bảng. Tuy nhiên, **một object được tạo từ lớp entity chưa chắc đang được JPA theo dõi**. Điều này phụ thuộc vào trạng thái của object trong persistence context.

### 2.2. Persistence context là gì?

*Persistence context* là môi trường mà JPA provider dùng để quản lý một tập entity. Một `EntityManager` làm việc với một persistence context; context đó giữ thông tin nhận dạng và trạng thái của các entity được quản lý.

Các tính chất chính:

1. **Identity trong context:** đối với cùng một loại entity và cùng khóa chính, context duy trì một instance managed tương ứng. Hai lần `find` trong cùng context thường trả về chính cùng object Java đó.
2. **Dirty checking:** provider phát hiện các thuộc tính của managed entity đã đổi và lập kế hoạch SQL cập nhật khi đồng bộ.
3. **First-level cache:** entity đã quản lý có thể được trả về ngay từ context mà không cần chạy lại `SELECT`, tùy thao tác.
4. **Unit of work:** nhiều thay đổi trên các entity có thể được đồng bộ thành SQL tại thời điểm flush, thay vì mỗi lần gọi setter đều gửi một câu SQL.

Đây là quản lý **trạng thái đối tượng ở tầng ứng dụng**, không phải thao tác cấp phát hay duy trì socket kết nối cơ sở dữ liệu.

### 2.3. Bốn trạng thái thường gặp của entity

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| **New / transient** | Object mới tạo, chưa thuộc persistence context | `new Customer("Lan")` |
| **Managed / persistent** | Được context theo dõi; thay đổi có thể được đồng bộ | Kết quả `em.find(Customer.class, id)` hoặc entity được `persist` |
| **Detached** | Từng được quản lý nhưng hiện nằm ngoài context đó | Sau `em.detach(entity)`, `em.clear()` hoặc đóng context |
| **Removed** | Entity managed đã được đánh dấu xóa trong context | `em.remove(entity)` trước khi hoàn thành xóa |

Một số phép chuyển trạng thái cần nhớ:

~~~text
new -- persist() ----------> managed
managed -- remove() -------> removed
managed -- detach()/clear()
        hoặc đóng context --> detached
detached -- merge() -------> trả về một instance managed
~~~

Chú ý `merge(detached)` **trả về instance managed** chứa trạng thái được hợp nhất; object detached truyền vào không tự động trở thành managed. Sau đó, nên tiếp tục làm việc với giá trị trả về:

~~~java
Customer managed = em.merge(detachedCustomer);
managed.setName("Tên đã sửa");
~~~

`remove()` yêu cầu đối tượng managed; nếu muốn xóa một detached entity, cần lấy lại managed instance phù hợp trong context trước.

### 2.4. Dirty checking: vì sao không cần viết UPDATE?

Giả sử `customer` đã là managed entity trong một giao dịch:

~~~java
Customer customer = em.find(Customer.class, 42L);
customer.setName("Lan Nguyễn");
~~~

Không có `em.update(customer)` trong JPA chuẩn. Khi flush, JPA provider có thể phát hiện `name` thay đổi và tạo SQL tương ứng:

~~~sql
UPDATE customer
SET name = ?
WHERE id = ?;
~~~

SQL bên trên minh họa ý tưởng; SQL thực tế còn phụ thuộc provider, mapping, chiến lược cập nhật và cấu hình. Nếu có `@Version`, SQL còn có thể tham gia cơ chế optimistic locking.

**Điều kiện quan trọng:** entity phải đang managed, và thao tác ghi cần nằm trong một giao dịch hợp lệ. Sửa một entity detached không tự động phát sinh cập nhật trong cơ sở dữ liệu.

## 3. Ví dụ JPA: cập nhật bằng trạng thái đối tượng

Ví dụ sau dùng **resource-local transaction** của JPA. `EntityManagerFactory` (`emf`) được khởi tạo và cấu hình ở cấp ứng dụng, không nên tạo mới cho mỗi lần gọi hàm.

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public class CustomerJpaService {
    private final EntityManagerFactory emf;

    public CustomerJpaService(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public void renameCustomer(long id, String newName) {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            Customer customer = em.find(Customer.class, id);
            if (customer == null) {
                throw new IllegalArgumentException("Customer not found: " + id);
            }

            customer.setName(newName); // Managed entity: JPA theo dõi thay đổi
            tx.commit();               // Provider flush khi cần, rồi commit
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
~~~

Trình tự tư duy đúng:

1. `emf.createEntityManager()` tạo một `EntityManager` và ngữ cảnh quản lý entity phù hợp.
2. `tx.begin()` bắt đầu giao dịch JPA resource-local.
3. `em.find(...)` lấy `Customer` và đưa entity vào trạng thái managed (nếu tìm thấy).
4. `customer.setName(...)` chỉ thay đổi object Java; provider đánh dấu hoặc nhận biết sự khác biệt theo cơ chế dirty checking.
5. Khi cần flush (thường trước hoặc trong commit), provider chuyển thay đổi thành SQL, thực thi thông qua JDBC.
6. `tx.commit()` yêu cầu hoàn tất giao dịch. `em.close()` kết thúc `EntityManager`; việc cung cấp và giải phóng kết nối vật lý thuộc hạ tầng bên dưới.

Ví dụ này giả định cấu hình JPA sử dụng `RESOURCE_LOCAL`. Với JTA hoặc framework quản lý giao dịch, không tự gọi `getTransaction()` theo cách này.

## 4. Quản lý kết nối JDBC: tài nguyên và câu lệnh SQL

### 4.1. Vai trò của các thành phần JDBC

- `DataSource`: nguồn cấp kết nối; thường được cấu hình với connection pool.
- `Connection`: đại diện cho một kết nối/session JDBC, nơi các câu lệnh SQL và điều khiển giao dịch được thực hiện.
- `PreparedStatement`: câu SQL có tham số được bind an toàn, tránh ghép chuỗi trực tiếp từ dữ liệu người dùng.
- `ResultSet`: kết quả truy vấn mà lập trình viên phải đọc và ánh xạ thành dữ liệu/object.
- Connection pool: tái sử dụng các kết nối vật lý, giảm chi phí mở kết nối mới.

`Connection` **không biết** object `Customer` nào đang là managed hay detached. Nó chỉ thực hiện lệnh SQL và các thao tác transaction/JDBC khác.

### 4.2. Cùng nghiệp vụ, viết bằng JDBC thuần

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public class CustomerJdbcService {
    private final DataSource dataSource;

    public CustomerJdbcService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void renameCustomer(long id, String newName) throws SQLException {
        String sql = "UPDATE customer SET name = ? WHERE id = ?";

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                try (PreparedStatement stmt =
                             connection.prepareStatement(sql)) {
                    stmt.setString(1, newName);
                    stmt.setLong(2, id);

                    int rowsUpdated = stmt.executeUpdate();
                    if (rowsUpdated != 1) {
                        throw new SQLException(
                            "Expected one customer, updated: " + rowsUpdated
                        );
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
                throw ex;
            }
        }
    }
}
~~~

Ở đây, lập trình viên trực tiếp xác định:

1. Khi nào mượn `Connection` từ `DataSource`.
2. Khi nào tắt auto-commit và bắt đầu phạm vi transaction.
3. SQL nào chạy, bind tham số gì, có bao nhiêu bản ghi bị tác động.
4. Khi nào gọi `commit()` hoặc `rollback()`.
5. Khi nào đóng `PreparedStatement` và `Connection` bằng `try-with-resources`.

Nếu `DataSource` dùng connection pool, `connection.close()` thường **trả kết nối về pool** thay vì đóng kết nối vật lý vĩnh viễn. Đây vẫn là thao tác thiết yếu để tránh cạn pool. Ví dụ trên dùng JDBC độc lập; trong Spring có thể để transaction manager điều khiển giao dịch và sử dụng `JdbcTemplate` hoặc cơ chế JDBC phù hợp thay vì tự commit/close connection được framework quản lý.

### 4.3. Điểm khác biệt rõ nhất giữa hai ví dụ

Nghiệp vụ giống nhau: đổi tên một khách hàng theo ID.

- **JPA:** truy xuất `Customer` → sửa thuộc tính Java → persistence context theo dõi → provider sinh/thực thi `UPDATE`.
- **JDBC:** lấy connection → chuẩn bị `UPDATE` → bind tên và ID → gọi `executeUpdate()` → commit.

JPA giảm lượng code ánh xạ object và đồng bộ trạng thái. JDBC cho quyền kiểm soát trực tiếp SQL và cách chạy SQL. Ở tầng thực thi, cả hai đều phải tôn trọng ranh giới giao dịch của cơ sở dữ liệu.

## 5. Flush, commit và connection không phải một khái niệm

Ba hành động dưới đây thường xuất hiện gần nhau nhưng có ý nghĩa khác nhau:

| Hành động | Ý nghĩa | Có làm dữ liệu được commit bền vững ngay không? |
|---|---|---|
| `em.flush()` | Đồng bộ các thay đổi đang chờ trong persistence context thành lệnh SQL gửi tới DB | **Không.** Giao dịch vẫn có thể rollback |
| `tx.commit()` / transaction manager commit | Yêu cầu hoàn tất giao dịch thành công, thường kéo theo flush cần thiết | **Có**, nếu commit thành công theo ngữ nghĩa giao dịch DB |
| `connection.close()` | Giải phóng tài nguyên JDBC/hoàn trả connection về pool | **Không thay thế commit.** Không được trông cậy vào close để commit |

Ví dụ:

~~~java
tx.begin();

Customer customer = em.find(Customer.class, 42L);
customer.setName("Lan");

em.flush();   // SQL UPDATE có thể đã chạy trong giao dịch
tx.rollback(); // UPDATE bị hủy bởi rollback
~~~

Sau `flush()`, những thay đổi có thể đã đến cơ sở dữ liệu trong transaction hiện tại, nhưng transaction vẫn chưa được xác nhận. Hành vi nhìn thấy dữ liệu từ transaction khác phụ thuộc mức cô lập và DB.

Ngược lại, `persist()` hay setter **không bảo đảm** SQL chỉ chạy lúc commit. Provider có thể thực thi SQL sớm hơn để lấy ID được sinh bởi database (chẳng hạn một số cách dùng `IDENTITY`), khi truy vấn cần đồng bộ dữ liệu, hoặc khi gọi `flush()`. Không nên xây dựng logic dựa vào một thời điểm phát SQL cố định mà JPA không bảo đảm.

### Flush mode

Trong JPA, `FlushModeType.AUTO` cho phép provider đồng bộ khi cần để kết quả truy vấn nhất quán với các thay đổi trong context; `COMMIT` đẩy trọng tâm đồng bộ về thời điểm commit, với một số hạn chế/khác biệt về khả năng hiển thị thay đổi trong các truy vấn chạy trước commit. Dù ở chế độ nào, **flush vẫn không tương đương commit**.

## 6. Vòng đời entity, persistence context và connection có thể khác nhau

Có ít nhất bốn vòng đời cần phân biệt:

~~~text
Entity Java:
    được new -> managed -> detached / removed

Persistence context:
    được tạo -> quản lý nhiều entity -> clear / đóng

Giao dịch:
    begin -> thực thi / flush -> commit hoặc rollback

JDBC Connection:
    được lấy từ pool -> thực thi SQL -> đóng handle / trả pool
~~~

Các vòng đời này có thể trùng một phần, nhưng không nên giả định chúng luôn bắt đầu và kết thúc cùng lúc.

**Ví dụ 1: hai entity dùng chung một context.** Một `EntityManager` có thể quản lý hàng chục `Customer` trong cùng một giao dịch; không có nghĩa là cần một connection cho mỗi entity.

**Ví dụ 2: context tồn tại trước khi cần SQL.** Trong một số cấu hình, JPA provider có thể tạo `EntityManager` nhưng chỉ lấy JDBC connection khi thật sự cần truy vấn hoặc flush. Thời điểm mượn/trả connection còn tùy provider, connection handling mode, transaction và pool.

**Ví dụ 3: đóng context không đóng pool.** `em.close()` kết thúc vòng đời `EntityManager` và ngữ cảnh tương ứng. `EntityManagerFactory` và pool có vòng đời dài hơn, thường được đóng khi ứng dụng dừng. Không nên suy luận rằng `em.close()` gọi trực tiếp một thao tác đóng socket nhất định.

**Ví dụ 4: context sống qua nhiều thời điểm.** JPA hỗ trợ transaction-scoped persistence context và extended persistence context. Với một số phạm vi, vòng đời context có thể không trùng hoàn toàn với một giao dịch; cấu hình và container quyết định hành vi cụ thể.

### Quy tắc về đồng thời

`EntityManagerFactory` được thiết kế để chia sẻ giữa các luồng và thường sống suốt vòng đời ứng dụng. **`EntityManager` không thread-safe**; đừng chia sẻ một instance tự quản lý giữa nhiều request/luồng. Tương tự, không nên chia sẻ một `Connection` JDBC đang dùng giữa các luồng xử lý độc lập nếu không có cơ chế điều phối được thiết kế rõ ràng.

## 7. Ai là người điều khiển transaction?

Quản lý entity không tự động giải quyết mọi trách nhiệm transaction. Khi JPA sử dụng JDBC, giao dịch thật vẫn phải được điều phối ở tầng transaction manager và cơ sở dữ liệu.

| Môi trường | Ai thường mở/đóng transaction? | Code ứng dụng thường thao tác gì? |
|---|---|---|
| JPA `RESOURCE_LOCAL` thuần | `EntityTransaction` | `begin()`, `commit()`, `rollback()` |
| JPA với JTA/container | JTA/container | Khai báo/điều phối transaction theo mô hình container |
| Spring + JPA | Spring transaction manager | Thường dùng `@Transactional` |
| JDBC thuần không có framework | Code dùng `Connection` | `setAutoCommit(false)`, `commit()`, `rollback()` |
| Spring JDBC | Spring transaction manager | Dùng `@Transactional`, `JdbcTemplate`/`DataSourceUtils` phù hợp |

Một transaction có thể bao gồm nhiều thay đổi entity và nhiều câu lệnh SQL. Mỗi `EntityManager` hoặc mỗi câu lệnh `UPDATE` **không mặc nhiên là một transaction riêng**.

### Ví dụ Spring Boot + JPA

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void renameCustomer(Long id, String newName) {
        Customer customer = entityManager.find(Customer.class, id);
        if (customer == null) {
            throw new IllegalArgumentException("Customer not found: " + id);
        }

        customer.setName(newName);
    }
}
~~~

Trong trường hợp thông thường, Spring mở/ghép transaction quanh lời gọi phương thức qua proxy, cung cấp `EntityManager` phù hợp với transaction và commit/rollback theo cấu hình. Do đó, code nghiệp vụ không cần tự gọi `entityManager.close()` hay `getTransaction().commit()`.

Cần lưu ý: `@Transactional` có hiệu lực theo cơ chế AOP/proxy và cấu hình transaction; ví dụ một lời gọi nội bộ đến phương thức khác trên cùng instance (*self-invocation*) thường không đi qua proxy. Ngoài ra, các quy tắc rollback của Spring có thể phụ thuộc loại exception và cấu hình.

## 8. Khi kết hợp JPA và JDBC trong cùng ứng dụng

Kết hợp hai API là hợp lệ: dùng JPA cho entity nghiệp vụ và JDBC cho truy vấn/batch SQL đặc biệt. Tuy nhiên phải hiểu hai hệ thống quản lý trạng thái khác nhau.

### 8.1. Đồng bộ giao dịch

Nếu một nghiệp vụ thực hiện cả `EntityManager` và `JdbcTemplate`, muốn chúng tham gia **cùng một transaction**, cần cấu hình đúng `DataSource`, transaction manager và cách lấy connection. Trong cấu hình Spring phù hợp, `JpaTransactionManager` có thể phối hợp JDBC truy cập cùng `DataSource`, và `JdbcTemplate` dùng connection được Spring quản lý.

Tự gọi `dataSource.getConnection()` rồi `commit()` trong lúc Spring đang quản lý transaction có thể tạo một transaction độc lập hoặc phá vỡ giả định đồng bộ, tùy cấu hình. Không được mặc định rằng có cùng URL database là chắc chắn cùng transaction.

### 8.2. Persistence context có thể chưa biết về thay đổi JDBC

Ví dụ cùng một transaction:

1. JPA đã `find` một `Customer`, instance `customer` đang managed.
2. Một câu SQL JDBC trực tiếp chạy `UPDATE customer SET name = ... WHERE id = ...`.
3. Object `customer` trong persistence context **không tự cập nhật thuộc tính** chỉ vì JDBC đã đổi bản ghi ở DB.

Khi cần đọc lại trạng thái DB, cân nhắc `em.refresh(customer)`, `em.clear()` rồi truy vấn lại, hoặc thiết kế lại thứ tự cập nhật. Cũng phải tính đến việc flush muộn của JPA có thể ghi đè giá trị do JDBC vừa thay đổi nếu hai đường ghi cùng cột.

Theo chiều ngược lại, nếu JDBC cần nhìn thấy dữ liệu mà JPA vừa thay đổi nhưng vẫn còn trong persistence context, có thể cần `em.flush()` trước khi chạy JDBC SQL. Điều kiện là chúng thật sự tham gia cùng transaction và cùng cơ sở dữ liệu theo cấu hình.

### 8.3. Bulk JPQL cũng cần lưu ý

Không chỉ JDBC trực tiếp: các câu `UPDATE`/`DELETE` hàng loạt bằng JPQL có thể thao tác trực tiếp trên database và **bỏ qua đồng bộ từng managed entity trong context**. Sau bulk operation, cần chủ động xử lý trạng thái context để tránh đọc dữ liệu cũ.

## 9. Những nhầm lẫn phổ biến

| Nhận định | Điều cần hiểu |
|---|---|
| “Mỗi entity giữ một JDBC connection.” | Sai. Entity là object được context quản lý, không sở hữu connection. |
| “EntityManager chính là Connection.” | Sai. `EntityManager` là API persistence; `Connection` là tài nguyên JDBC. |
| “Gọi setter trên mọi `@Entity` đều lưu DB.” | Sai. Dirty checking áp dụng cho **managed** entity trong điều kiện phù hợp; detached entity không tự đồng bộ. |
| “`persist()` luôn INSERT ngay lập tức.” | Không được bảo đảm; thời điểm thực thi SQL phụ thuộc provider, flush và cách sinh ID. |
| “`flush()` nghĩa là đã commit.” | Sai. Flush gửi SQL nhưng transaction vẫn có thể rollback. |
| “`em.clear()` trả connection về pool.” | Không phải ngữ nghĩa của `clear()`; nó detach các entity trong context. |
| “Đóng `Connection` làm mất object Java.” | Không. Object vẫn tồn tại trên heap; JDBC không theo dõi lifecycle entity. |
| “JDBC không thể có transaction.” | Sai. JDBC có `setAutoCommit`, `commit`, `rollback` hoặc tham gia transaction manager. |
| “Đã dùng JPA thì không cần biết JDBC.” | Không nên. Debug connection pool, timeout, isolation, lock và SQL vẫn cần hiểu tầng JDBC/DB. |
| “JPA lúc nào cũng chạy ít SQL hơn JDBC.” | Không chắc. Lazy loading, N+1 queries và flush có thể tạo nhiều SQL; cần đo và tối ưu theo truy vấn thực tế. |

## 10. Chọn cách tiếp cận và kiểm tra lỗi theo đúng tầng

**Ưu tiên JPA** khi mô hình nghiệp vụ có nhiều entity và quan hệ, cần theo dõi thay đổi, mapping, cache cấp một, cascade hoặc optimistic locking. Đây là lựa chọn tự nhiên cho phần lớn nghiệp vụ CRUD và domain model, miễn là nắm được ranh giới transaction và số truy vấn thực tế.

**Ưu tiên JDBC trực tiếp hoặc `JdbcTemplate`** khi cần chủ động SQL phức tạp, thao tác batch đặc thù, làm việc với cấu trúc kết quả không thuận với entity mapping, hoặc cần kiểm soát sát hành vi của driver/database. Không có quy tắc rằng một ứng dụng chỉ được dùng một cách.

Khi gặp sự cố, đặt câu hỏi ở đúng tầng:

- **Sửa object nhưng DB không đổi?** Xác định entity có còn managed không, transaction có commit không, provider đã flush chưa, và có rollback không.
- **Đọc được giá trị cũ sau khi SQL đã update?** Xem lại first-level cache/persistence context, các thao tác bulk/JDBC và nhu cầu refresh/clear.
- **Hết connection hoặc request treo chờ DB?** Kiểm tra pool, giao dịch kéo dài, connection/statement không được đóng, timeout và lock ở DB.
- **SQL chạy nhiều bất ngờ?** Kiểm tra fetching, lazy loading, N+1, query được gọi trong vòng lặp và thời điểm flush.
- **JPA và JDBC không thấy thay đổi của nhau?** Kiểm tra chúng có dùng cùng transaction và cùng connection được framework quản lý không; sau đó xét flush và dữ liệu đang cache trong context.

## 11. Tình huống củng cố

Giả sử một phương thức mở transaction, gọi:

~~~java
Customer a = em.find(Customer.class, 10L);
Customer b = em.find(Customer.class, 10L);

a.setName("Tên mới");
em.flush();
~~~

**Câu hỏi 1: `a == b` có đúng không?** Trong cùng persistence context, với cùng entity type và khóa chính, **đúng**: JPA giữ identity của managed entity.

**Câu hỏi 2: `em.flush()` đã lưu vĩnh viễn chưa?** **Chưa.** SQL có thể đã chạy trong transaction, nhưng chỉ khi transaction commit thành công mới hoàn tất; rollback có thể hủy thay đổi.

**Câu hỏi 3: Có thể kết luận đã mở hai JDBC connection vì gọi `find()` hai lần không?** **Không.** Số connection và thời điểm lấy connection là trách nhiệm quản lý tài nguyên ở tầng provider/JDBC, không suy ra từ số lần truy xuất entity.

**Ghi nhớ:** JPA quản lý *danh tính, vòng đời và thay đổi của entity* trong persistence context; JDBC quản lý *kênh thực thi SQL và tài nguyên kết nối* với database. Transaction là ranh giới quyết định thay đổi nào được commit hoặc rollback và liên kết hai tầng khi dữ liệu được lưu thực sự.
