# Phân biệt JDBC, ORM, Jakarta Persistence và Hibernate

Khi ứng dụng Java làm việc với cơ sở dữ liệu quan hệ (RDBMS), bốn thuật ngữ **JDBC**, **ORM**, **Jakarta Persistence** và **Hibernate** thường xuất hiện cùng nhau. Chúng liên quan chặt chẽ nhưng **không cùng loại khái niệm**: JDBC là API truy cập cơ sở dữ liệu, ORM là kỹ thuật ánh xạ dữ liệu, Jakarta Persistence là đặc tả chuẩn cho persistence/ORM trong Java, còn Hibernate ORM là một framework triển khai khả năng ORM và có thể đóng vai trò nhà cung cấp Jakarta Persistence.

Hiểu đúng ranh giới này giúp chọn công cụ, đọc tài liệu, thiết kế tầng truy cập dữ liệu và xử lý lỗi khi SQL thực tế không như mong đợi.

## 1. Nhìn nhanh: mỗi thuật ngữ trả lời câu hỏi nào?

| Thuật ngữ | Bản chất | Câu hỏi nó giải quyết |
| --- | --- | --- |
| **JDBC** (*Java Database Connectivity*) | Bộ API tiêu chuẩn của Java để tương tác với nguồn dữ liệu quan hệ qua driver | “Làm sao mở kết nối, gửi SQL, nhận kết quả và quản lý giao dịch?” |
| **ORM** (*Object–Relational Mapping*) | Kỹ thuật/kiểu giải pháp ánh xạ dữ liệu giữa mô hình đối tượng và mô hình quan hệ | “Làm sao biểu diễn và thao tác bản ghi, quan hệ bằng đối tượng Java?” |
| **Jakarta Persistence** (trước đây thường gọi **JPA**) | Đặc tả và API chuẩn cho quản lý entity, persistence context, truy vấn và ánh xạ quan hệ | “Các ORM provider cần tuân theo giao diện và hành vi chuẩn nào?” |
| **Hibernate ORM** | Framework ORM cụ thể, đồng thời là một Jakarta Persistence provider phổ biến | “Phần mềm nào thực hiện mapping, theo dõi entity và phát sinh/thực thi SQL?” |

Điểm cần nhớ: **JDBC không phải một ORM**; **ORM không phải tên một thư viện**; **Jakarta Persistence không tự là một công cụ thực thi đầy đủ**; **Hibernate không phải tên khác của Jakarta Persistence**.

## 2. Quan hệ giữa bốn khái niệm trong kiến trúc Java

Ứng dụng có thể truy cập cơ sở dữ liệu theo hai hướng tiêu biểu:

```text
Hướng A — trực tiếp qua JDBC

Ứng dụng Java
    └── JDBC API (java.sql / javax.sql)
            └── JDBC driver của hệ quản trị CSDL
                    └── PostgreSQL / MySQL / Oracle / ...

Hướng B — dùng ORM với API chuẩn Jakarta Persistence

Ứng dụng Java
    └── Jakarta Persistence API (jakarta.persistence)
            └── Hibernate ORM (một provider triển khai API)
                    └── JDBC + driver
                            └── Cơ sở dữ liệu quan hệ

Hướng C — dùng API riêng của Hibernate

Ứng dụng Java
    └── Hibernate API (ví dụ: org.hibernate.Session)
            └── Hibernate ORM
                    └── JDBC + driver
                            └── Cơ sở dữ liệu quan hệ
```

Sơ đồ thể hiện các đường đi thường gặp, không phải mọi cơ chế tích hợp đều có cùng cấu hình. **ORM là kỹ thuật được Hibernate áp dụng**, không phải một tầng thư viện độc lập bắt buộc phải lắp giữa Jakarta Persistence và Hibernate. Hibernate có thể được gọi thông qua API chuẩn Jakarta Persistence hoặc API riêng; trong cấu hình RDBMS thông thường, cuối cùng nó vẫn dùng JDBC để giao tiếp với database.

Ví dụ, câu lệnh “dự án dùng JPA với Hibernate” nghĩa là mã ứng dụng chủ yếu gọi `EntityManager` từ Jakarta Persistence, còn Hibernate là provider thực hiện việc lưu và truy vấn. Câu “dự án dùng Hibernate” có thể nói đến chính cấu hình đó, hoặc mã sử dụng trực tiếp `Session` và các tiện ích riêng của Hibernate.

## 3. JDBC: làm việc trực tiếp với SQL và dữ liệu dạng bảng

### 3.1. JDBC cung cấp gì?

Các thành phần thường gặp:

- `DataSource` (`javax.sql`) cung cấp kết nối, thường thông qua connection pool.
- `Connection` (`java.sql`) đại diện cho kết nối với nguồn dữ liệu; có thể điều khiển `commit()` và `rollback()`.
- `PreparedStatement` gửi câu SQL đã được chuẩn bị và gắn tham số an toàn.
- `ResultSet` cho phép đọc từng hàng của kết quả truy vấn.
- JDBC driver chuyển các lời gọi JDBC thành giao tiếp phù hợp với hệ quản trị cơ sở dữ liệu.

JDBC **không tự biết** một hàng trong bảng `customers` tương ứng với đối tượng `Customer` nào, hoặc khi trường `fullName` trên đối tượng đổi thì phải cập nhật cột `full_name` ra sao. Ứng dụng tự viết SQL, chuyển kiểu, dựng đối tượng và quyết định thời điểm thực hiện các lệnh ghi.

### 3.2. Ví dụ đọc dữ liệu bằng JDBC

Giả sử cơ sở dữ liệu có bảng `customers(id, full_name)`. Ví dụ sau dùng kiểu dữ liệu bất biến để nhận kết quả:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;

record CustomerView(long id, String fullName) {}

class CustomerJdbcDao {
    private final DataSource dataSource;

    CustomerJdbcDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    Optional<CustomerView> findById(long id) throws SQLException {
        String sql = "SELECT id, full_name FROM customers WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                return Optional.of(new CustomerView(
                    rs.getLong("id"), rs.getString("full_name")
                ));
            }
        }
    }
}
```

Ở đây người lập trình kiểm soát hoàn toàn SQL, tự đọc `ResultSet` và tự tạo `CustomerView`. Dấu `?` cùng `setLong()` dùng **bind parameter**; không nên ghép trực tiếp dữ liệu người dùng vào chuỗi SQL vì có nguy cơ SQL injection.

Khi cần nhiều lệnh ghi phải thành công hoặc thất bại cùng nhau, JDBC cho phép tắt auto-commit bằng `connection.setAutoCommit(false)`, sau đó `commit()` khi thành công và `rollback()` khi lỗi. Cần trả kết nối về pool và bảo đảm trạng thái kết nối được quản lý đúng bởi hạ tầng đang dùng.

### 3.3. Điểm mạnh và chi phí của JDBC

JDBC phù hợp khi cần kiểm soát SQL cụ thể, tận dụng tính năng đặc thù của database, thực hiện báo cáo/truy vấn phức tạp hoặc xây dựng luồng xử lý ít entity. Đổi lại, nếu domain có nhiều bảng và quan hệ, phần SQL lặp lại và mã chuyển đổi giữa hàng dữ liệu với object có thể tăng đáng kể. JDBC không mặc định cung cấp persistence context, dirty checking hay lazy loading của một ORM.

## 4. ORM: kỹ thuật nối hai mô hình dữ liệu

Trong Java, domain thường được biểu diễn bằng **object**: một `Customer` có trường `id`, `fullName`, các method và có thể tham chiếu đến danh sách `Order`. Trong database quan hệ, dữ liệu nằm ở **bảng, hàng, cột, khóa chính và khóa ngoại**. ORM đặt ra các quy tắc để kết nối hai thế giới này.

Một bản ánh xạ điển hình:

| Mô hình đối tượng | Mô hình quan hệ |
| --- | --- |
| Lớp `Customer` | Bảng `customers` |
| Thuộc tính `id` | Cột `id` / khóa chính |
| Thuộc tính `fullName` | Cột `full_name` |
| `Customer.orders` | Quan hệ một-nhiều qua khóa ngoại |
| Tham chiếu `Order.customer` | Quan hệ nhiều-một qua khóa ngoại |

Framework ORM thường hỗ trợ việc ánh xạ này bằng annotation, XML hoặc cấu hình tương đương. Một ORM như Hibernate còn cung cấp nhiều cơ chế quan trọng:

1. **Identity và persistence context:** theo dõi entity đang được quản lý trong phạm vi làm việc; tránh tạo nhiều object được quản lý khác nhau cho cùng một khóa định danh trong cùng context.
2. **Dirty checking:** phát hiện thay đổi ở entity được quản lý và đồng bộ chúng thành câu lệnh SQL khi flush.
3. **Quan hệ và chiến lược fetch:** quản lý `@ManyToOne`, `@OneToMany`, `LAZY`, `EAGER`... tùy mapping và khả năng provider.
4. **Truy vấn theo mô hình entity:** JPQL/HQL dùng tên entity và thuộc tính Java thay vì luôn viết SQL theo tên bảng và cột.
5. **Unit of work và đồng bộ:** gom các thay đổi của những entity được quản lý để đồng bộ với cơ sở dữ liệu trong ranh giới giao dịch thích hợp.

ORM **không xóa bỏ SQL hoặc schema quan hệ**. Hibernate vẫn phát ra SQL thật, cần kết nối JDBC, chịu ảnh hưởng của index, khóa, transaction isolation và execution plan. ORM cũng không bảo đảm truy vấn sẽ tự động tối ưu: tải quá nhiều quan hệ, N+1 query hoặc batch không phù hợp vẫn có thể làm ứng dụng chậm.

## 5. Jakarta Persistence: hợp đồng chuẩn cho persistence trong Java

### 5.1. Đặc tả, API và provider

**Jakarta Persistence** là một đặc tả thuộc hệ sinh thái Jakarta EE, mô tả API và các quy tắc quản lý entity, mapping, persistence context, vòng đời entity, query và giao dịch. Tên cũ **Java Persistence API (JPA)** vẫn được sử dụng rộng rãi trong tài liệu và tên sản phẩm như Spring Data JPA.

Phân biệt ba vai trò:

- **Đặc tả:** quy định hành vi và API cần tuân thủ.
- **API:** các kiểu Java được ứng dụng import, ví dụ `jakarta.persistence.Entity`, `EntityManager`, `EntityManagerFactory`, `Query`.
- **Provider:** phần mềm triển khai đặc tả, ví dụ **Hibernate ORM** hoặc **EclipseLink**.

Chỉ thêm Jakarta Persistence API vào classpath **không đủ** để có một hệ ORM chạy được: cần provider, driver và cấu hình kết nối/datasource phù hợp. Khi chuyển provider, mã phụ thuộc vào API chuẩn thường dễ giữ lại hơn mã dựa trên phần mở rộng riêng; mức độ portable thực tế còn tùy mapping, dialect SQL và các tính năng được sử dụng.

> **Lưu ý tên package:** trong ứng dụng Jakarta Persistence hiện đại, annotation và interface thường thuộc `jakarta.persistence.*`. Những hệ thống JPA cũ trước giai đoạn chuyển đổi namespace dùng `javax.persistence.*`. Riêng JDBC vẫn ở `java.sql.*` và `javax.sql.*`; không đổi thành `jakarta.sql.*`.

### 5.2. Mapping một entity bằng annotation chuẩn

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    protected Customer() { } // Constructor không tham số cho JPA

    public Customer(String fullName) {
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public void rename(String name) {
        this.fullName = name;
    }
}
```

Mapping trên yêu cầu bảng `customers` có cột `id` và `full_name`, với cách sinh khóa chính tương thích chiến lược `IDENTITY` của database đang sử dụng. Annotation mô tả cách ánh xạ; việc phát sinh SQL và đọc/ghi database do provider đảm nhiệm.

### 5.3. EntityManager và thay đổi được quản lý

Giả sử đã cấu hình một `EntityManagerFactory` tên `emf`, ví dụ thay đổi tên khách hàng trong ứng dụng Java SE với **resource-local transaction**:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;

EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Customer customer = em.find(Customer.class, 10L);
    if (customer == null) {
        throw new IllegalArgumentException("Customer not found");
    }
    customer.rename("Nguyen An");

    tx.commit(); // Provider đồng bộ thay đổi (flush) trước/khi commit
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Không có `UPDATE` viết tay: đối tượng trả về bởi `em.find()` đang **managed** trong persistence context và provider có thể phát hiện thay đổi của `fullName`. Trong môi trường container quản lý giao dịch hoặc Spring `@Transactional`, giao dịch thường do hạ tầng quản lý; không dùng mẫu `getTransaction()` để tự mở transaction trong bối cảnh JTA/container-managed.

Các phương thức cần phân biệt:

| API Jakarta Persistence | Ý nghĩa cơ bản |
| --- | --- |
| `persist(entity)` | Đưa entity mới vào trạng thái managed để được chèn vào database khi đồng bộ |
| `find(Entity.class, id)` | Tìm entity theo khóa chính; trả `null` nếu không có |
| `merge(entity)` | Sao chép trạng thái từ đối tượng được truyền vào sang một bản managed và **trả về bản managed** |
| `remove(entity)` | Đánh dấu entity managed để xóa khi đồng bộ |
| `flush()` | Đồng bộ các thay đổi đang chờ với database, **không đồng nghĩa commit** |
| `clear()` / `detach(entity)` | Ngừng quản lý entity trong persistence context hiện tại |

Một entity có thể ở trạng thái mới (*new/transient*), managed, detached hoặc removed. Điểm dễ nhầm là **đổi thuộc tính trên detached entity không tự động được theo dõi**; `merge()` không biến chính instance được truyền vào thành managed mà trả về instance managed tương ứng. `EntityManager` thông thường gắn với một đơn vị công việc và không an toàn để chia sẻ tùy ý giữa các luồng; `EntityManagerFactory` được thiết kế để chia sẻ và dùng tạo các `EntityManager`.

### 5.4. JPQL khác SQL như thế nào?

```java
// JPQL: Customer là tên entity; fullName là thuộc tính Java.
var customers = em.createQuery(
        "SELECT c FROM Customer c WHERE c.fullName = :name",
        Customer.class
    )
    .setParameter("name", "Nguyen An")
    .getResultList();
```

So với SQL tương ứng:

```sql
SELECT id, full_name
FROM customers
WHERE full_name = ?;
```

JPQL được diễn giải theo mapping entity và provider dịch sang SQL cho database cụ thể. Jakarta Persistence cũng có Criteria API và native SQL query khi cần. Tham số trong JPQL nên được bind bằng `setParameter()` tương tự `PreparedStatement` của JDBC.

## 6. Hibernate ORM: framework thực thi ORM và provider của Jakarta Persistence

Hibernate ORM làm các việc cụ thể như phân tích mapping, tạo kế hoạch truy vấn, quản lý persistence context, theo dõi entity, phát sinh SQL, kết hợp với JDBC driver và đồng bộ thay đổi trong transaction. Hibernate **triển khai chuẩn Jakarta Persistence** nhưng còn cung cấp nhiều khả năng riêng: API `Session`/`SessionFactory`, HQL, hỗ trợ batching, các tính năng mapping mở rộng, bộ nhớ đệm tùy cấu hình và các cơ chế tối ưu khác.

Một ứng dụng sử dụng Jakarta Persistence với Hibernate provider có thể chỉ import `jakarta.persistence.*` trong tầng nghiệp vụ. Nhưng cũng có thể dùng trực tiếp Hibernate API:

```java
import org.hibernate.Session;

// sessionFactory đã được cấu hình cho cùng mô hình entity và database.
try (Session session = sessionFactory.openSession()) {
    Customer customer = session.get(Customer.class, 10L);
    if (customer != null) {
        System.out.println(customer.getFullName());
    }
}
```

Ở đây `Session` đóng vai trò tương tự một phiên làm việc ORM/persistence context. `SessionFactory` thường được tạo một lần và tái sử dụng, còn `Session` gắn với từng đơn vị công việc và không dùng đồng thời từ nhiều luồng. Trong nhiều phiên bản Hibernate hiện đại, `Session` cũng có các phương thức quen thuộc với `EntityManager`; khi cần tính portable, nên ưu tiên API Jakarta Persistence chuẩn.

**HQL** (*Hibernate Query Language*) là ngôn ngữ truy vấn theo entity của Hibernate, có quan hệ gần với JPQL nhưng có các phần mở rộng riêng. Không nên giả định tất cả cú pháp HQL đều được mọi Jakarta Persistence provider hỗ trợ. Tương tự, annotation hoặc API của `org.hibernate.*` có thể tạo sự phụ thuộc vào Hibernate.

## 7. So sánh theo các tiêu chí thường gặp

| Tiêu chí | JDBC | ORM (khái niệm) | Jakarta Persistence | Hibernate ORM |
| --- | --- | --- | --- | --- |
| Loại | API truy cập dữ liệu | Kỹ thuật/kiến trúc | Đặc tả + API | Framework/implementation |
| Độ trừu tượng | SQL, hàng/cột, connection | Entity/quan hệ đối tượng | Entity, `EntityManager`, JPQL | Entity, `Session` hoặc `EntityManager`, HQL/JPQL |
| SQL do ai viết? | Chủ yếu do lập trình viên | Tùy công cụ ORM | API cho phép provider sinh SQL hoặc chạy native SQL | Thường sinh SQL từ mapping/query; vẫn cho viết SQL gốc |
| Mapping object–table | Tự lập trình | Là mục đích chính | Có metadata/annotation chuẩn | Thực thi mapping và có extension |
| Dirty checking | Không mặc định | Tùy công cụ | Hành vi đồng bộ managed entity theo đặc tả | Cơ chế thực thi do Hibernate cung cấp |
| Quản lý transaction | `Connection`, hoặc hạ tầng bên ngoài | Tùy giải pháp | Resource-local hoặc JTA/container | Tích hợp transaction, hỗ trợ API chuẩn và riêng |
| Tính portable | API JDBC chung; SQL có thể phụ thuộc DB | Không đánh giá độc lập được | Có hợp đồng chuẩn giữa các provider | Dùng API riêng sẽ gắn chặt với Hibernate hơn |
| Mức kiểm soát SQL | Rất trực tiếp | Tùy ORM | Có JPQL và native SQL | Có HQL/JPQL, native SQL, cấu hình fetch và batching |

Không thể khẳng định “JDBC luôn nhanh hơn Hibernate” hoặc “ORM luôn tốt hơn JDBC”. Hiệu năng phụ thuộc câu SQL thực thi, index, số lần truy cập mạng, cách fetch, kích thước batch, cache, mô hình dữ liệu và chất lượng thiết kế giao dịch.

## 8. Một thao tác, ba cách lập trình

Với nghiệp vụ “tìm khách hàng theo ID”, cách viết cho thấy mức trừu tượng thay đổi:

**JDBC** — viết SQL và tự chuyển `ResultSet` thành object:

```java
String sql = "SELECT id, full_name FROM customers WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, id);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            return new CustomerView(rs.getLong("id"), rs.getString("full_name"));
        }
        return null;
    }
}
```

**Jakarta Persistence** — làm việc với entity và API chuẩn; provider được cấu hình sẽ triển khai truy vấn:

```java
Customer customer = entityManager.find(Customer.class, id);
```

**Hibernate native API** — làm việc với cùng entity thông qua `Session`:

```java
Customer customer = session.get(Customer.class, id);
```

Ba đoạn mã thể hiện cùng mục tiêu đọc dữ liệu, nhưng giả định `connection`, `entityManager` hoặc `session` đã được khởi tạo và quản lý vòng đời phù hợp. Trong hai cách ORM, SQL thật vẫn phải được database thực thi.

## 9. Transaction, persistence context và kết nối: ba thứ không nên đánh đồng

- **Database transaction** quyết định tập thao tác nào cùng commit/rollback theo khả năng của database. Transaction có thể được điều khiển trực tiếp qua JDBC, hoặc qua Jakarta Persistence/Hibernate/hạ tầng quản lý transaction.
- **Persistence context** là phạm vi theo dõi các entity được quản lý. Nó biết trạng thái object và quyết định các thay đổi cần đồng bộ. `flush()` gửi các thay đổi tới database nhưng transaction vẫn có thể rollback; `commit()` là ranh giới xác nhận transaction.
- **JDBC connection** là kênh giao tiếp với database. Một `EntityManager` hoặc `Session` **không đồng nghĩa** với một kết nối vật lý cố định trong toàn bộ vòng đời; cách lấy và trả connection phụ thuộc provider và cấu hình.

Mối quan hệ này giải thích vì sao sửa field trên entity managed có thể dẫn đến `UPDATE` khi commit, trong khi sửa field trên object Java bình thường do JDBC tạo ra không làm database tự thay đổi.

## 10. Những hiểu nhầm thường gặp khi học Hibernate

### “Dùng Hibernate là không cần học SQL”

Sai. Hibernate che bớt mã SQL lặp lại, nhưng người phát triển vẫn phải hiểu `JOIN`, index, foreign key, locking, transaction isolation, execution plan và biết đọc log SQL. Một vòng lặp qua các association `LAZY` có thể gây **N+1 query**: một truy vấn lấy danh sách chính và thêm nhiều truy vấn riêng để lấy dữ liệu liên quan. Có thể xử lý bằng `JOIN FETCH`, entity graph, batch fetching hoặc projection tùy tình huống, sau khi đo SQL thực tế.

### “Có annotation `@Entity` là đã kết nối được database”

Sai. `@Entity` chỉ khai báo metadata ánh xạ. Ứng dụng vẫn cần provider, cấu hình datasource/connection, JDBC driver và ranh giới transaction đúng. Schema cũng phải tồn tại hoặc được tạo/quản lý bằng quy trình phù hợp, thường qua migration tool ở môi trường vận hành.

### “JPA và Hibernate là hai framework độc lập phải chọn một”

Sai ở mức phân loại: Jakarta Persistence là chuẩn; Hibernate là một implementation của chuẩn đó. Một dự án hoàn toàn có thể sử dụng **đồng thời Jakarta Persistence API và Hibernate provider**. Lựa chọn kỹ thuật chính là muốn lập trình theo API chuẩn hay cần thêm các tính năng đặc thù của Hibernate, cùng với việc chọn provider phù hợp.

### “Spring Data JPA chính là JPA hoặc Hibernate”

Không đúng. **Spring Data JPA** cung cấp abstraction repository như `JpaRepository` để giảm mã truy cập dữ liệu trong ứng dụng Spring. Nó xây trên Jakarta Persistence; bên dưới vẫn cần một provider như Hibernate. Một đường đi phổ biến là `Service → Spring Data JPA repository → EntityManager → Hibernate → JDBC → database`.

### “Đọc thuộc tính LAZY lúc nào cũng được”

Không phải lúc nào cũng được. Nếu association chưa được tải và persistence context/session đã đóng, Hibernate có thể ném `LazyInitializationException`. Thiết kế ranh giới transaction và kế hoạch fetch theo nhu cầu use case; tránh bật `EAGER` cho mọi quan hệ để chữa tạm vì có thể làm tăng lượng dữ liệu và truy vấn.

### “`flush()` cũng giống `commit()`”

Không. `flush()` đồng bộ thay đổi vào database trong ngữ cảnh transaction; transaction có thể vẫn chưa commit và có thể rollback. Việc phát sinh SQL cũng có thể diễn ra trước `flush()` tường minh, tùy operation, chiến lược sinh ID và flush mode. Hãy phân biệt **thời điểm gửi SQL** với **thời điểm transaction được commit**.

## 11. Chọn hướng tiếp cận trong dự án thực tế

| Tình huống | Hướng phù hợp để cân nhắc | Vì sao |
| --- | --- | --- |
| Công cụ nhỏ, truy vấn SQL cố định, ít entity | JDBC hoặc một thư viện JDBC mỏng | SQL rõ ràng, ít chi phí mapping và lifecycle |
| Dịch vụ có nhiều entity, association và nghiệp vụ cập nhật theo object | Jakarta Persistence với Hibernate provider | Giảm mã CRUD lặp lại, hỗ trợ quản lý trạng thái entity |
| Muốn tránh phụ thuộc API riêng của một provider | Viết phần lớn tầng persistence bằng Jakarta Persistence | Dễ thay provider hơn trong giới hạn tính năng chuẩn |
| Cần tính năng ORM đặc biệt mà chuẩn chưa cung cấp | Dùng Hibernate extension có chủ đích | Tận dụng tính năng riêng, đồng thời chấp nhận coupling |
| Báo cáo hoặc truy vấn tổng hợp rất phức tạp | SQL/native query, JDBC hoặc projection phù hợp | Dễ kiểm soát SQL và hình dạng kết quả |
| Dùng Spring Boot với repository cho domain thông thường | Spring Data JPA + Jakarta Persistence + Hibernate (nếu chọn provider này) | Repository đơn giản hóa API ứng dụng; provider vẫn xử lý ORM |

Các lựa chọn có thể **kết hợp trong cùng ứng dụng**: dùng JPA/Hibernate cho phần ghi và domain entity, đồng thời dùng JDBC hoặc native SQL cho một số truy vấn báo cáo. Khi kết hợp, cần quản lý nhất quán transaction, cache/persistence context và thứ tự ghi/đọc để tránh dữ liệu trong bộ nhớ không đồng bộ với thay đổi thực hiện ngoài ORM.

## 12. Cách nhận diện công nghệ khi xem mã nguồn

| Dấu hiệu trong code | Khả năng cao đang sử dụng |
| --- | --- |
| `Connection`, `PreparedStatement`, `ResultSet`, `DataSource` | JDBC trực tiếp hoặc hạ tầng truy cập dữ liệu dựa trên JDBC |
| `@Entity`, `@Id`, `@OneToMany` từ `jakarta.persistence` | Entity mapping theo Jakarta Persistence |
| `EntityManager`, `EntityManagerFactory`, JPQL | API Jakarta Persistence |
| `Session`, `SessionFactory`, `org.hibernate.*`, HQL extension | API hoặc tính năng riêng của Hibernate |
| `JpaRepository`, `@EnableJpaRepositories` | Spring Data JPA (vẫn cần Jakarta Persistence provider) |
| Log SQL do Hibernate phát ra dù không thấy SQL trong service | ORM đang tự chuyển thao tác entity/truy vấn thành SQL |

**Tự kiểm tra kiến thức:** Nếu đoạn code gọi `entityManager.persist(new Customer("An"))` nhưng ứng dụng cấu hình Hibernate làm provider, thư viện nào định nghĩa lời gọi `persist` và thành phần nào thực hiện thao tác ghi? Đáp án: `EntityManager.persist` thuộc **Jakarta Persistence API**; **Hibernate ORM** là provider xử lý mapping, đồng bộ dữ liệu và thực thi SQL qua JDBC/driver. Nếu thay `EntityManager` bằng `Connection`/`PreparedStatement`, lập trình viên phải tự viết SQL và mapping tương ứng.

## Kết luận

Để phân biệt chính xác, hãy nhớ **bốn tầng ý nghĩa**: **JDBC = cách Java giao tiếp với database bằng SQL**; **ORM = kỹ thuật ánh xạ object–relation**; **Jakarta Persistence = hợp đồng API/behavior chuẩn cho persistence**; **Hibernate ORM = phần mềm hiện thực ORM và có thể thực thi hợp đồng Jakarta Persistence**. Nhìn thấy Hibernate trong một hệ thống không có nghĩa JDBC biến mất; thông thường ORM chỉ nằm ở tầng cao hơn và vẫn dựa vào JDBC để tiếp cận database quan hệ.
