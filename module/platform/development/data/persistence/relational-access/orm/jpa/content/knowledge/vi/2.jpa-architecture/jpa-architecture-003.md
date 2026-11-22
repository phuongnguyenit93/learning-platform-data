# Mối liên hệ giữa persistence unit, nguồn dữ liệu và mô hình entity trong JPA

Trong Jakarta Persistence (JPA), **persistence unit (PU)**, **nguồn dữ liệu (DataSource/JDBC)** và **mô hình entity** là ba khái niệm liên kết với nhau nhưng có trách nhiệm khác nhau:

- **Persistence unit:** một tập cấu hình persistence có tên, chỉ ra những lớp nào được quản lý, kết nối nào được dùng và giao dịch được điều phối ra sao.
- **Nguồn dữ liệu:** cung cấp các kết nối JDBC tới cơ sở dữ liệu quan hệ.
- **Mô hình entity:** mô tả cách đối tượng Java, thuộc tính và quan hệ giữa đối tượng ánh xạ tới bảng, cột và khóa ngoại.

JPA provider (ví dụ Hibernate ORM) sử dụng **metadata của entity** để hiểu *cần đọc/ghi dữ liệu theo cấu trúc nào* và sử dụng **nguồn dữ liệu** để biết *đọc/ghi ở cơ sở dữ liệu nào*. Persistence unit là đầu mối ghép các cấu hình đó lại để ứng dụng làm việc thống nhất.

## 1. Nhìn toàn bộ đường đi từ Java tới database

~~~text
                         ỨNG DỤNG JAVA
                               |
                    EntityManagerFactory
                     (PU tên "storePU")
                               |
                        EntityManager
                    + persistence context
                               |
                          JPA provider
                    (ví dụ: Hibernate)
                       /            \
                      /              \
              Entity metadata     DataSource / JDBC
              Customer, Order...         |
              @Table, @Column...     Connection
                      \              /
                       \            /
                         DATABASE
                  tables, columns, indexes,
                      primary/foreign keys
~~~

| Thành phần | Câu hỏi mà nó trả lời | Vai trò |
| --- | --- | --- |
| Persistence unit | “Dùng tập entity và cấu hình persistence nào?” | Định danh tập metadata, lựa chọn provider/kết nối/giao dịch |
| DataSource hoặc JDBC properties | “Lấy connection từ đâu?” | Cung cấp `java.sql.Connection` tới DB; có thể dùng connection pool |
| Entity model | “Object nào tương ứng bảng/cột/quan hệ nào?” | Cung cấp ánh xạ ORM qua annotation hoặc XML |
| EntityManagerFactory | “Tạo các EntityManager dựa trên PU này bằng cách nào?” | Khởi tạo một lần cho cấu hình PU và tạo `EntityManager` |
| EntityManager + persistence context | “Instance entity nào đang được quản lý trong đơn vị làm việc?” | Đọc/ghi entity, theo dõi thay đổi, đồng bộ với DB |

**Phân biệt đặc biệt quan trọng:** *persistence unit* mô tả tập cấu hình và mapping dùng cho việc lưu trữ; *persistence context* theo dõi những **instance cụ thể** đang ở trạng thái managed. Persistence unit không phải một session, không phải database vật lý và cũng không phải một connection cố định.

## 2. Một persistence unit thực sự định nghĩa những gì?

Trong JPA, mỗi PU có một tên, ví dụ `storePU`. Tùy cách triển khai, nó chứa:

1. **Tập lớp được quản lý:** entity class, metadata từ `@Embeddable`, `@MappedSuperclass`, converter, mapping XML và các thành phần persistence liên quan.
2. **Cách lấy kết nối:** JTA DataSource, non-JTA DataSource hoặc các thuộc tính JDBC trong ứng dụng Java SE.
3. **Kiểu giao dịch:** `JTA` hoặc `RESOURCE_LOCAL`.
4. **Thuộc tính provider:** các tùy chọn xử lý SQL, schema, logging, cache…; nhiều tùy chọn là đặc thù Hibernate hay provider khác, không phải mọi thuộc tính đều thuộc tiêu chuẩn JPA.

Một cách khai báo tường minh là file `META-INF/persistence.xml`. Trong Spring Boot, framework có thể tự cấu hình `EntityManagerFactory`, nguồn dữ liệu và bước quét entity, nên không nhất thiết có file XML; vai trò kiến trúc của các thành phần vẫn tương tự.

Việc class được đăng ký trong PU **không có nghĩa** bảng sẽ tự xuất hiện. Cần chuẩn bị schema khớp với mapping, thường qua migration SQL (Flyway/Liquibase) hoặc schema generation khi chủ động cấu hình.

## 3. Ví dụ xuyên suốt: khách hàng và đơn hàng

Giả sử có PostgreSQL database `store_db`. Java có hai loại object: `Customer` và `PurchaseOrder`. Một khách hàng có nhiều đơn hàng; một đơn hàng thuộc một khách hàng.

~~~text
Java domain model                  Relational schema

Customer                            customers
  id: Long             ---------->   id BIGINT PRIMARY KEY
  name: String         ---------->   name VARCHAR(255)

PurchaseOrder                       purchase_orders
  id: Long             ---------->   id BIGINT PRIMARY KEY
  total: BigDecimal    ---------->   total NUMERIC(12,2)
  customer: Customer   ---------->   customer_id BIGINT
                                     FOREIGN KEY -> customers.id
~~~

### 3.1. Khai báo entity model

Ví dụ dùng Jakarta Persistence 3.x với package `jakarta.persistence`:

~~~java
package com.example.store;

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

    @Column(nullable = false)
    private String name;

    protected Customer() {
        // JPA cần constructor không tham số.
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
}
~~~

~~~java
package com.example.store;

import java.math.BigDecimal;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal total;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer, BigDecimal total) {
        this.customer = customer;
        this.total = total;
    }

    public Long getId() {
        return id;
    }
}
~~~

- `@Entity` đánh dấu loại object có thể được JPA quản lý, với điều kiện class nằm trong tập managed classes của PU.
- `@Table`, `@Column` định nghĩa bảng và cột; `@Id` là khóa định danh entity; `@GeneratedValue` yêu cầu cơ chế tạo khóa.
- `@ManyToOne` biểu diễn quan hệ nhiều đơn hàng cùng tham chiếu một khách hàng; `@JoinColumn` xác định cột `customer_id` chứa khóa ngoại.
- `FetchType.LAZY` là yêu cầu trì hoãn tải quan hệ ở mức gợi ý; thời điểm truy cập dữ liệu thực tế còn phụ thuộc provider và cách truy vấn.

**Quan hệ object và quan hệ database khác cách thể hiện:** code giữ một tham chiếu `PurchaseOrder.customer`, còn database giữ giá trị khóa ngoại `purchase_orders.customer_id`. Provider áp dụng mapping để chuyển đổi hai chiều.

Nếu chủ động tạo schema PostgreSQL cho ví dụ, có thể dùng:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    total NUMERIC(12, 2) NOT NULL,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~

Schema thực tế có thể thêm index, ràng buộc nghiệp vụ và migration. Mapping JPA cần khớp với cấu trúc đã triển khai.

### 3.2. Khai báo persistence unit nối entity với nguồn dữ liệu

Trong Java SE, đặt file tại `src/main/resources/META-INF/persistence.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="https://jakarta.ee/xml/ns/persistence
                                 https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
             version="3.1">

    <persistence-unit name="storePU" transaction-type="RESOURCE_LOCAL">
        <class>com.example.store.Customer</class>
        <class>com.example.store.PurchaseOrder</class>
        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.postgresql.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:postgresql://localhost:5432/store_db"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="app_user"/>
            <property name="jakarta.persistence.jdbc.password"
                      value="YOUR_PASSWORD"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

| Cấu hình | Ý nghĩa |
| --- | --- |
| `name="storePU"` | Tên PU mà code dùng khi tạo `EntityManagerFactory` |
| `transaction-type="RESOURCE_LOCAL"` | Giao dịch do ứng dụng quản lý qua `EntityTransaction` |
| Hai thẻ `<class>` | Hai entity nằm trong mô hình do PU quản lý |
| `<exclude-unlisted-classes>true</exclude-unlisted-classes>` | Giới hạn việc lấy thêm class ngoài danh sách trong ví dụ |
| `jakarta.persistence.jdbc.*` | Địa chỉ database, JDBC driver và thông tin xác thực |

Ví dụ giả định project đã thêm Jakarta Persistence API, một JPA provider và PostgreSQL JDBC driver vào classpath. Mật khẩu `YOUR_PASSWORD` chỉ là ký hiệu minh họa; hệ thống thực nên lấy thông tin nhạy cảm từ cấu hình môi trường hoặc secret manager, không đưa mật khẩu thật vào source control.

~~~text
                 PU "storePU"
                /             \
               /               \
      Managed classes         JDBC config
      - Customer                   |
      - PurchaseOrder             v
                               store_db
                                /   \
                         customers  purchase_orders
~~~

Đổi JDBC URL có thể chuyển nơi ghi dữ liệu mà không cần đổi các annotation entity, **nếu schema ở nơi mới tương thích**. Ngược lại, thay `@Table(name = ...)` chỉ thay ánh xạ bảng, không thay nguồn kết nối.

### 3.3. Ứng dụng sử dụng persistence unit

~~~java
import java.math.BigDecimal;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
import com.example.store.Customer;
import com.example.store.PurchaseOrder;

public class StoreExample {
    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("storePU");

        try {
            EntityManager em = emf.createEntityManager();
            try {
                em.getTransaction().begin();

                Customer customer = new Customer("Mai");
                em.persist(customer);

                PurchaseOrder order =
                    new PurchaseOrder(customer, new BigDecimal("125.00"));
                em.persist(order);

                em.getTransaction().commit();
            } catch (RuntimeException ex) {
                if (em.getTransaction().isActive()) {
                    em.getTransaction().rollback();
                }
                throw ex;
            } finally {
                em.close();
            }
        } finally {
            emf.close();
        }
    }
}
~~~

Đường đi của dữ liệu:

1. `Persistence.createEntityManagerFactory("storePU")` tìm PU có tên tương ứng, đọc cấu hình, nạp metadata entity và khởi tạo provider.
2. `emf.createEntityManager()` tạo một `EntityManager` gắn với persistence context để quản lý các instance.
3. `begin()` mở giao dịch local. `persist(customer)` và `persist(order)` khiến hai object được quản lý và cần được ghi xuống database.
4. Provider tra metadata để biết bảng/cột/khóa ngoại; lấy connection từ nguồn JDBC của PU; thực thi SQL INSERT tại thời điểm phù hợp.
5. `commit()` đồng bộ các thay đổi còn chờ và hoàn tất giao dịch; `close()` giải phóng tài nguyên.

Với `GenerationType.IDENTITY`, provider có thể cần thực thi INSERT sớm để lấy ID; do đó không thể kết luận rằng SQL chỉ chạy khi gọi `commit()`, hay mọi lệnh `persist()` đều chạy SQL ngay lập tức.

Thông thường, một `EntityManagerFactory` được dùng lại trong thời gian chạy ứng dụng, còn `EntityManager` có phạm vi ngắn hơn và **không thread-safe**. Connection JDBC có thể được lấy và trả về pool theo nhu cầu; không có quan hệ cứng “một EntityManager = một JDBC connection”.

## 4. Khi nguồn dữ liệu do Jakarta EE container cung cấp

Trong Jakarta EE, container có thể cấu hình một `DataSource` có JNDI name và quản lý giao dịch JTA. Khi đó PU có thể ghi:

~~~xml
<persistence-unit name="storeJtaPU" transaction-type="JTA">
    <jta-data-source>java:comp/env/jdbc/StoreDS</jta-data-source>
    <class>com.example.store.Customer</class>
    <class>com.example.store.PurchaseOrder</class>
</persistence-unit>
~~~

`java:comp/env/jdbc/StoreDS` phải được môi trường triển khai định nghĩa và trỏ đến nguồn dữ liệu thật. Component do container quản lý có thể sử dụng:

~~~java
@PersistenceContext(unitName = "storeJtaPU")
private EntityManager entityManager;
~~~

Với JTA, transaction thường được điều khiển bởi container hoặc ranh giới `jakarta.transaction.Transactional`. Không gọi `entityManager.getTransaction().begin()` trên container-managed JTA entity manager như trong ví dụ `RESOURCE_LOCAL`.

| Khía cạnh | RESOURCE_LOCAL | JTA |
| --- | --- | --- |
| Nguồn kết nối minh họa | `jakarta.persistence.jdbc.*` hoặc non-JTA DataSource | `<jta-data-source>` |
| Chủ thể quản lý giao dịch | Ứng dụng qua `EntityTransaction` | Transaction manager/container |
| Cách nhận EntityManager thường gặp | `EntityManagerFactory.createEntityManager()` | `@PersistenceContext` hoặc cơ chế container |
| Mô hình entity | Các class `@Entity` | Có thể dùng cùng các class `@Entity` |

Trong cấu hình JTA nâng cao, PU có thể có thêm non-JTA DataSource phục vụ một số truy cập. Vì vậy không nên đồng nhất một PU với đúng một connection vật lý. Số lượng connection, pooling và thời gian giữ connection phụ thuộc provider, DataSource và transaction manager.

## 5. Quan hệ giữa PU, database và entity không phải lúc nào cũng một-một

| Tình huống | Ý nghĩa kiến trúc |
| --- | --- |
| **Một PU quản lý nhiều entity** | `Customer`, `PurchaseOrder`, `Product` có thể dùng chung một tập cấu hình kết nối/transaction. |
| **Một entity ánh xạ nhiều bảng** | Có thể do kế thừa entity, `@SecondaryTable` hoặc kiểu mapping phức tạp hơn. |
| **Nhiều entity dùng chung bảng** | Có thể gặp với inheritance mapping và một số trường hợp đặc biệt. |
| **Một PU truy cập nhiều schema** | Có thể ánh xạ các entity tới bảng ở các schema khác nhau khi DB và quyền cho phép. |
| **Hai PU cùng dùng một DataSource** | Vẫn là hai `EntityManagerFactory`/tập metadata khác nhau và có persistence context riêng. |
| **Hai PU dùng hai DataSource** | Thường chia nhóm entity và trách nhiệm truy cập dữ liệu; transaction local của một PU không tự bao trùm cả hai. |

Ví dụ hệ thống chia dữ liệu vận hành và báo cáo:

~~~text
                    Application
                     /      \
                    /        \
              ordersPU    reportsPU
                 |            |
           Order entities  Report entities
                 |            |
             OrdersDS      ReportsDS
                 |            |
             orders_db      reports_db
~~~

Truy vấn JPQL thông thường chạy trong một `EntityManager` của một PU. Không thể mặc nhiên viết một JPQL join giữa entity thuộc hai PU ở hai database rồi kỳ vọng JPA tự gộp kết quả. Cần giải pháp rõ ràng ở tầng service, tích hợp dữ liệu hoặc hạ tầng database phù hợp.

## 6. Persistence context nằm ở vị trí nào?

Đây là một ranh giới cần nắm chắc khi học kiến trúc JPA:

- **PU** cung cấp định nghĩa: `Customer` ánh xạ vào `customers` và sử dụng nguồn kết nối nào.
- **Persistence context** lưu trạng thái: instance `Customer` có ID bằng 10 đang managed, có thuộc tính nào bị sửa và cần flush hay không.
- **Database** lưu dữ liệu bền vững sau transaction được commit.

Ví dụ trong cùng một persistence context:

~~~java
Customer c1 = em.find(Customer.class, 10L);
Customer c2 = em.find(Customer.class, 10L);
boolean sameInstance = (c1 == c2); // true
~~~

Hai `EntityManager`/persistence context tách biệt có thể tạo hai Java object khác nhau cho cùng một dòng DB. Provider duy trì tính đồng nhất instance *trong một persistence context*, chứ PU không phải một cache managed entity toàn cục. Nếu entity đã detached hoặc context đóng, truy cập quan hệ lazy chưa nạp có thể thất bại; cần thiết kế transaction và phạm vi đọc dữ liệu phù hợp.

## 7. Các lỗi thường gặp và cách xác định tầng gây lỗi

| Triệu chứng | Kiểm tra đầu tiên | Giải thích |
| --- | --- | --- |
| Không tìm thấy persistence provider hoặc tạo factory thất bại | Dependency provider, vị trí `META-INF/persistence.xml`, tên PU | API JPA không tự triển khai ORM |
| “Not a managed type” / “Unknown entity” | `@Entity`, `<class>`, phạm vi entity scanning, PU được chọn | Class chưa thuộc tập managed entity |
| Không kết nối được, sai user/password | JDBC URL, driver, cổng, DB, DataSource/JNDI, credentials | Tầng nguồn dữ liệu không cấp được connection hợp lệ |
| Ghi vào nhầm database | PU, cấu hình môi trường, nguồn kết nối thực tế | Annotation entity không quy định máy chủ DB |
| Thiếu bảng/cột hoặc foreign key sai | `@Table`, `@Column`, `@JoinColumn` và schema/migration | Metadata ORM và cấu trúc relational không khớp |
| Transaction required hoặc ghi không hoàn tất | `JTA` hay `RESOURCE_LOCAL`, ranh giới transaction | Entity operation cần transaction phù hợp |
| Không thể lazy-load ngoài transaction/context | Phạm vi persistence context, `JOIN FETCH`/entity graph khi cần | Truy vấn bổ sung không còn ngữ cảnh truy cập |

Để tìm nguyên nhân, lần theo chuỗi **tên PU → tập entity → cấu hình nguồn dữ liệu → transaction → SQL/schema**. Logging SQL có thể hữu ích nhưng cần tránh ghi mật khẩu và dữ liệu nhạy cảm vào log.

## 8. Ba thay đổi thiết kế để tự kiểm tra hiểu biết

**A. Chuyển từ database thử nghiệm sang database sản xuất:** nếu hai database có schema tương thích, có thể giữ entity model và đổi thông số nguồn dữ liệu theo môi trường. Vẫn cần migration, quyền truy cập và cấu hình secrets đúng.

**B. Thêm entity `Product`:** tạo entity mapping, đăng ký hoặc đảm bảo được quét vào đúng PU, rồi bổ sung bảng/cột cần thiết. Việc thêm class Java hoặc thêm bảng SQL *một cách riêng lẻ* chưa đủ bảo đảm JPA quản lý được entity.

**C. Tách thành hai nguồn dữ liệu:** xác định nhóm entity thuộc PU nào, mỗi PU dùng factory và DataSource nào, cũng như cách đảm bảo nhất quán giữa các transaction nếu một thao tác liên quan cả hai nguồn.

## 9. Đúc kết theo một thao tác lưu đơn hàng

Với `em.persist(new PurchaseOrder(customer, total))`, provider kết hợp:

1. **Persistence unit** để nhận dạng tập metadata và cấu hình đang dùng.
2. **Mô hình entity** để suy ra `purchase_orders`, cột `total`, khóa ngoại `customer_id` và quy tắc quản lý định danh.
3. **Nguồn dữ liệu** để lấy connection đến `store_db`.
4. **Persistence context và transaction** để quản lý trạng thái object, phát sinh SQL ở thời điểm phù hợp và ghi dữ liệu nhất quán.

Muốn hệ thống lưu/truy xuất dữ liệu quan hệ chính xác, ba cấu phần **PU — nguồn dữ liệu — mô hình entity** phải được cấu hình nhất quán. Mỗi cấu phần có trách nhiệm riêng nhưng phối hợp với nhau trong mọi thao tác JPA.
