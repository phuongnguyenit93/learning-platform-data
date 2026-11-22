# Phân biệt đặc tả JPA với thư viện triển khai như Hibernate

## Mục tiêu học tập

Sau khi hoàn thành bài học, người học có thể:

1. Phân biệt **JPA/Jakarta Persistence là đặc tả** với **Hibernate ORM là một thư viện triển khai (persistence provider)**.
2. Xác định vai trò riêng của Jakarta Persistence API, Hibernate ORM, Spring Data JPA, JDBC driver và hệ quản trị cơ sở dữ liệu.
3. Dùng các khái niệm chuẩn như `@Entity`, `EntityManager`, persistence context, JPQL, `@Version` và transaction mà không nhầm với API riêng của Hibernate.
4. Nhận diện điểm một ứng dụng phụ thuộc vào provider: annotation mở rộng, HQL, cache, batching, fetch strategy, dialect và hành vi phát sinh SQL.
5. Đánh giá tính di động giữa các provider/DBMS bằng **bằng chứng chạy thử**, thay vì nghĩ rằng dùng JPA đồng nghĩa SQL và hiệu năng giống nhau ở mọi môi trường.
6. Chọn ranh giới persistence phù hợp trong Java, kiểm tra N+1, transaction, schema migration, xử lý lỗi và tính đúng đắn của dữ liệu.

Bài thuộc chương **Hệ sinh thái Java** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module hướng đến hiểu lưu trữ bền vững từ mô hình dữ liệu, lược đồ, truy vấn, chỉ mục đến transaction, isolation và concurrency. Trong hệ thống Java, hiểu sự khác biệt giữa **hợp đồng tiêu chuẩn** và **một hiện thực cụ thể** giúp thiết kế repository dễ bảo trì mà không che giấu chi phí truy vấn, lỗi kết nối, bảo mật hay yêu cầu phục hồi dữ liệu.

## 1. Câu trả lời ngắn: JPA là hợp đồng, Hibernate là một cách thực hiện

**JPA (Java Persistence API)** là tên gọi quen thuộc trong hệ sinh thái Java cho chuẩn ánh xạ đối tượng – quan hệ (ORM) và truy cập persistence. Trong hệ sinh thái Jakarta EE hiện nay, tên đặc tả chính thức là **Jakarta Persistence**, với các API như `jakarta.persistence.EntityManager`, `jakarta.persistence.Entity` và `jakarta.persistence.Query`.

**Hibernate ORM** là một triển khai ORM có thể đóng vai trò **Jakarta Persistence provider**. Nó đọc metadata mapping, quản lý persistence context, thực thi dirty checking, tạo và gửi SQL, phối hợp JDBC và chuyển đổi dữ liệu giữa object Java với các hàng trong database.

Nói ngắn gọn:

- **Đặc tả Jakarta Persistence** định nghĩa những hành vi và API mà một provider tương thích phải hỗ trợ.
- **Thư viện API** cung cấp các interface, annotation và class chuẩn để mã ứng dụng sử dụng.
- **Provider** như Hibernate ORM thực hiện những hành vi đó khi ứng dụng chạy.
- **JDBC driver** đưa lệnh tới database theo giao thức của từng hệ quản trị.
- **Database** mới là nơi thực thi SQL, constraint, transaction, khóa, isolation và bảo đảm durability theo cấu hình.

**Không thể chỉ thêm Jakarta Persistence API rồi kỳ vọng mọi thao tác persistence tự chạy.** Cần một provider và cấu hình kết nối/database tương thích.

### 1.1. Sơ đồ các tầng trong một ứng dụng

~~~text
                        Java application
                 Controller / business service
                              |
                  Repository / persistence port
                              |
               +--------------+----------------+
               |                               |
          JPA EntityManager              Spring Data JPA
          (API theo chuẩn)               (lớp repository tiện ích)
               |                               |
               +---------------+---------------+
                               |
                       Hibernate ORM
                 (Jakarta Persistence provider)
                               |
                       JDBC / JDBC driver
                               |
                  PostgreSQL / MySQL / ...
                               |
                  Bảng, chỉ mục, transaction,
                     WAL, lưu trữ bền vững
~~~

Sơ đồ minh họa một stack **có chọn Hibernate và Spring Data JPA**. Spring Data JPA là tùy chọn, không phải tầng bắt buộc: ứng dụng có thể gọi `EntityManager` trực tiếp. Ứng dụng cũng có thể dùng JDBC thuần, jOOQ, MyBatis hoặc công nghệ khác cho một số use case; chọn JPA không làm mọi đường truy cập dữ liệu phải đi qua entity.

### 1.2. Bảng phân biệt vai trò

| Thành phần | Bản chất | Định nghĩa/cung cấp điều gì? | Không tự làm điều gì? |
| --- | --- | --- | --- |
| Jakarta Persistence (JPA) | Đặc tả tiêu chuẩn | Mapping, entity lifecycle, `EntityManager`, JPQL, Criteria, lock/version, hợp đồng persistence | Không phải một database hoặc công cụ SQL hoàn chỉnh độc lập |
| Jakarta Persistence API artifact | Thư viện API | Interface, annotation, enum và type trong namespace `jakarta.persistence` | Không tự triển khai toàn bộ engine ORM |
| Hibernate ORM | Provider và thư viện ORM | Hiện thực JPA, sinh SQL, mapping, caching/flush, tính năng mở rộng riêng | Không thay thế DBMS và constraint ở DB |
| EclipseLink | Một provider khác | Hiện thực Jakarta Persistence với các công cụ và tính năng riêng | Không bảo đảm cấu hình, extension và hiệu năng trùng Hibernate |
| Spring Data JPA | Thư viện hỗ trợ truy cập dữ liệu | Repository interface, query derivation, `JpaRepository`, integration với Spring | Không phải đặc tả JPA và không tự thay thế provider ORM |
| Spring transaction manager | Hạ tầng điều phối transaction | Ranh giới `@Transactional`, commit/rollback theo cấu hình | Không tự biến mọi thao tác nhiều DB thành một transaction nguyên tử |
| JDBC driver | Triển khai giao tiếp DB cho Java | Connection, statement, bind parameter, truyền/nhận dữ liệu | Không quyết định quy tắc nghiệp vụ hay schema |
| PostgreSQL/MySQL/... | DBMS | SQL, locking, index, WAL/redo, transaction, constraint | Không tự hiểu mọi bất biến nằm ngoài schema/transaction |

Một câu thường gặp: “Dự án này dùng JPA hay Hibernate?” Thực ra hai điều không đối lập. Dự án có thể **lập trình theo Jakarta Persistence API và chọn Hibernate làm provider**.

## 2. Bối cảnh tên gọi: `javax.persistence` và `jakarta.persistence`

Trong các dự án Java cũ, JPA 2.x thuộc Java EE thường được sử dụng qua namespace:

~~~java
import javax.persistence.Entity;
import javax.persistence.EntityManager;
~~~

Với các phiên bản Jakarta Persistence 3.x hiện đại, namespace chuẩn chuyển thành:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityManager;
~~~

Sự thay đổi này liên quan đến việc chuyển Java EE sang Jakarta EE. **Hai namespace không thể hoán đổi tùy ý trong cùng một stack.** Provider, framework, dependency và code mapping phải tương thích với nhau.

Ví dụ, một ứng dụng Spring Boot/Hibernate cũ dùng API `javax.persistence` có thể cần nâng cấp đồng bộ nhiều dependency khi chuyển sang stack `jakarta.persistence`. Chỉ thay import của entity mà giữ provider không tương thích có thể dẫn đến lỗi bootstrapping, thiếu class hoặc entity không được nhận diện.

Không nên ghi nhớ một bảng phiên bản cố định để áp vào mọi dự án. Cần kiểm tra **version của Jakarta Persistence API, Hibernate ORM, Spring Framework/Boot và Java runtime** theo compatibility matrix của chính stack đang vận hành.

## 3. Những gì thuộc API chuẩn Jakarta Persistence

Các thành phần tiêu biểu:

| Nhóm | API/annotation chuẩn | Ý nghĩa |
| --- | --- | --- |
| Entity mapping | `@Entity`, `@Table`, `@Id`, `@Column` | Ánh xạ lớp/field với dữ liệu quan hệ |
| Quan hệ | `@OneToMany`, `@ManyToOne`, `@OneToOne`, `@ManyToMany` | Mô tả liên kết giữa các entity |
| Khóa và sinh ID | `@GeneratedValue`, `@SequenceGenerator` | Mô tả cách sinh khóa theo strategy |
| Kiểm soát phiên bản | `@Version`, `LockModeType` | Hỗ trợ optimistic/pessimistic locking theo hợp đồng |
| Truy cập persistence | `EntityManagerFactory`, `EntityManager` | Tạo context, tìm, lưu, xóa, query entity |
| Truy vấn | JPQL, Criteria API, `TypedQuery`, named/native query | Biểu đạt truy vấn bằng object model hoặc SQL |
| Vòng đời | `persist`, `find`, `merge`, `remove`, `flush`, `clear` | Thay đổi và đồng bộ trạng thái entity |
| Transaction | `EntityTransaction` ở resource-local; integration JTA | Gắn thao tác với transaction |

Đặc tả mô tả **kết quả/hành vi được kỳ vọng** theo điều kiện chuẩn. Nó không buộc mọi provider phát ra cùng câu SQL, chọn cùng kế hoạch fetch, dùng cùng thuật toán dirty checking hay có cùng hiệu năng.

### 3.1. Một entity thuần Jakarta Persistence

Giả sử PostgreSQL có bảng:

~~~sql
CREATE TABLE orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL CHECK (total_amount >= 0),
    status       VARCHAR(32) NOT NULL,
    version      BIGINT NOT NULL DEFAULT 0
);
~~~

Entity Java 17 dùng API chuẩn:

~~~java
package com.example.persistence;

import java.math.BigDecimal;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "total_amount", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "status", nullable = false, length = 32)
    private String status;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected OrderEntity() {
        // Constructor không tham số cho provider JPA.
    }

    public OrderEntity(Long tenantId, BigDecimal totalAmount) {
        this.tenantId = tenantId;
        this.totalAmount = totalAmount;
        this.status = "PENDING";
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public void markPaid() {
        this.status = "PAID";
    }
}
~~~

Các annotation ở ví dụ đến từ `jakarta.persistence`; lớp không import `org.hibernate.*`. Nó là **code mapping theo chuẩn**. Tuy nhiên, việc mapping có hoạt động đúng với DB đã chọn, strategy `IDENTITY` có phù hợp, schema có tương thích và SQL được phát ra ra sao vẫn cần thử trên provider/DBMS thật.

`@Version` cho phép provider phối hợp optimistic locking; khi hai transaction cùng sửa một entity từ phiên bản cũ, một trong số đó có thể bị báo xung đột theo hợp đồng. Cột version **không** bảo vệ các câu UPDATE ngoài ORM nếu chúng bỏ qua quy tắc tăng/kiểm tra phiên bản.

### 3.2. `EntityManager` là một API, không phải tên riêng của Hibernate

Một ứng dụng có thể viết:

~~~java
OrderEntity order = entityManager.find(
        OrderEntity.class, orderId);

entityManager.persist(new OrderEntity(tenantId, amount));
entityManager.flush();
~~~

Đây là các thao tác theo hợp đồng JPA. Khi chọn Hibernate làm provider, Hibernate triển khai chúng; với provider khác, hiện thực thay đổi nhưng API mà application gọi vẫn là `EntityManager`.

Không được suy từ đoạn code rằng `persist()` lập tức phát INSERT hay `flush()` đồng nghĩa commit. Với một số ID strategy như `IDENTITY`, provider có thể cần INSERT sớm để lấy generated ID; với các strategy khác, SQL có thể bị trì hoãn đến flush. Điều quan trọng là **không xây logic nghiệp vụ trên giả định về thời điểm SQL nếu hợp đồng không bảo đảm**.

## 4. Persistence context và vòng đời entity

Một điểm cốt lõi của JPA là **persistence context**: nơi provider theo dõi những entity đang được quản lý.

Các trạng thái khái niệm:

~~~text
new/transient
      |
      | persist()
      v
managed  <-- find() / query
   |
   | thay đổi field của managed entity
   | provider nhận biết ở thời điểm đồng bộ phù hợp
   v
flush SQL (chưa chắc commit)
   |
   | transaction COMMIT thành công
   v
thay đổi được DB commit

managed -- detach()/clear()/đóng context --> detached
managed -- remove() --> removed (xóa theo transaction/flush)
~~~

`managed` có nghĩa một entity thuộc persistence context đang được quản lý, **không phải** lúc nào cũng có cùng dữ liệu với transaction khác vừa commit. Các mức isolation, snapshot và first-level cache có thể tác động đến những giá trị được nhìn thấy.

### 4.1. Dirty checking và flush

Giả sử trong transaction, application gọi:

~~~java
OrderEntity order = entityManager.find(
        OrderEntity.class, 501L);

order.markPaid();
// Không gọi entityManager.update(order) vì JPA không có
// một thao tác update chuẩn bắt buộc cho managed entity.
~~~

Provider có thể phát UPDATE trong đợt flush nếu phát hiện state đã đổi. Cách provider lưu snapshot, dùng bytecode enhancement hay quyết định batching là **chi tiết triển khai**.

`flush()` đồng bộ những thay đổi cần thiết xuống DB trong transaction đang hoạt động, nhưng **vẫn có thể rollback**. `COMMIT` mới kết thúc transaction; độ bền sau commit còn phụ thuộc WAL/redo, hạ tầng lưu trữ và cấu hình DB.

### 4.2. `merge()` không đơn giản là “UPDATE hàng”

Khi nhận một entity detached, `EntityManager.merge(detached)` trả về một **managed instance** với trạng thái được đồng bộ theo quy tắc merge. Đối tượng detached ban đầu không mặc nhiên trở thành managed.

Dùng merge bừa bãi với một entity graph lớn có thể dẫn đến SELECT và cập nhật ngoài dự đoán. Với nghiệp vụ chỉ sửa một vài trường, thường nên xác định rõ hàng cần cập nhật, ranh giới transaction và kiểm soát phiên bản. Một API repository tên `save()` cũng **không cam kết** nó luôn thực hiện đúng một câu INSERT hoặc UPDATE.

### 4.3. Giới hạn chia sẻ tài nguyên

`EntityManagerFactory` được thiết kế để dùng chung và có thể tạo nhiều `EntityManager`. Ngược lại, `EntityManager`/persistence context **không được chia sẻ tùy tiện giữa các thread**; vòng đời thường gắn với transaction hoặc request theo chính sách của framework/container.

Một service singleton có thể thread-safe nếu stateless và nhận `EntityManager` qua cơ chế proxy/injection do framework quản lý; không suy ra rằng một instance `EntityManager` tự tạo và lưu làm field có thể bị nhiều thread gọi cùng lúc an toàn.

## 5. JPQL khác SQL và HQL như thế nào?

**JPQL (Jakarta Persistence Query Language)** là ngôn ngữ truy vấn thuộc đặc tả; nó làm việc với **entity và thuộc tính Java** thay vì trực tiếp dùng tên bảng/cột vật lý.

Ví dụ:

~~~java
var query = entityManager.createQuery(
        """
        SELECT o
        FROM OrderEntity o
        WHERE o.tenantId = :tenantId
        ORDER BY o.id DESC
        """,
        OrderEntity.class);

query.setParameter("tenantId", 42L);
query.setMaxResults(20);

var orders = query.getResultList();
~~~

Trong JPQL, `OrderEntity` là entity name, `tenantId` là thuộc tính Java. Khi thực thi với Hibernate, provider chuyển truy vấn thành SQL phù hợp với database dialect. SQL sinh ra có thể tương tự:

~~~sql
SELECT id, tenant_id, total_amount, status, version
FROM orders
WHERE tenant_id = ?
ORDER BY id DESC
LIMIT ?;
~~~

SQL trên **chỉ minh họa ý tưởng**. Tùy mapping, provider, dialect và phiên bản, SQL thực có thể dùng cú pháp, alias, join, bind và chiến lược paging khác.

**HQL (Hibernate Query Language)** là ngôn ngữ truy vấn của Hibernate. Nó có nhiều phần giao nhau với JPQL và có thể có tính năng mở rộng riêng theo phiên bản. Một câu HQL hợp lệ cho Hibernate chưa chắc là JPQL portable. Nếu muốn khả năng đổi provider, kiểm tra rằng truy vấn thực sự nằm trong phạm vi JPQL chuẩn.

### 5.1. Truy vấn native SQL vẫn là một phần của hệ sinh thái JPA

JPA hỗ trợ native SQL query. Khi cần dùng CTE, window function, JSONB operator, câu UPDATE phức tạp hay tính năng tối ưu riêng của PostgreSQL, có thể chọn native SQL có chủ đích.

~~~java
var rows = entityManager.createNativeQuery(
        """
        SELECT id, total_amount
        FROM orders
        WHERE tenant_id = ?
        ORDER BY id DESC
        LIMIT 20
        """)
    .setParameter(1, 42L)
    .getResultList();
~~~

API gọi native query là của JPA, nhưng **nội dung SQL vẫn phụ thuộc DBMS**, còn kết quả object array/scalar mapping có thể cần xử lý kiểu dữ liệu và mapping riêng. “Viết SQL qua EntityManager” không làm cú pháp SQL tự trở thành portable.

### 5.2. Projection DTO thay vì trả toàn bộ entity

Một DTO cho màn hình tóm tắt đơn hàng:

~~~java
package com.example.persistence;

import java.math.BigDecimal;

public record OrderSummary(Long id, BigDecimal totalAmount) {}
~~~

JPQL hỗ trợ constructor expression:

~~~java
var summaries = entityManager.createQuery(
        """
        SELECT new com.example.persistence.OrderSummary(
            o.id, o.totalAmount)
        FROM OrderEntity o
        WHERE o.tenantId = :tenantId
        ORDER BY o.id DESC
        """,
        OrderSummary.class)
    .setParameter("tenantId", tenantId)
    .setMaxResults(20)
    .getResultList();
~~~

Cách này chỉ trả về dữ liệu cần dùng và tránh để serializer tự đi qua mọi quan hệ của entity. Khi áp dụng, kiểm tra constructor/type mapping, số hàng, SQL thật và các trường hợp null với provider được chọn. DTO phù hợp cho đường đọc; entity managed thường phù hợp hơn khi cần cập nhật một aggregate qua persistence context.

## 6. Spring Data JPA nằm ở đâu?

Spring Data JPA thường cho phép khai báo interface:

~~~java
package com.example.persistence;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {

    List<OrderEntity> findTop20ByTenantIdOrderByIdDesc(
            Long tenantId);
}
~~~

Spring Data JPA phân tích tên method hoặc dùng annotation `@Query` để tạo lớp thực thi repository, rồi sử dụng **JPA provider** bên dưới. Nếu provider là Hibernate, SQL cuối cùng thường do Hibernate sinh ra.

Vì thế:

- **Spring Data JPA không phải JPA specification.**
- **`JpaRepository` không phải API chuẩn Jakarta Persistence.**
- **Hibernate không phải Spring Data JPA.**
- Dùng `JpaRepository` không đảm bảo endpoint chỉ phát một SQL hoặc không bị N+1.
- Một dự án dùng Spring Data JPA có thể đổi provider ở mức kiến trúc nếu stack hỗ trợ, nhưng phải xem các đặc tính và assumption riêng.

`save()`, query derivation, paging abstraction và `@EntityGraph` của Spring Data JPA là tiện ích có ích. Chúng giảm boilerplate, nhưng số SQL, flush timing, transaction configuration và chi phí fetch vẫn cần được đo.

### 6.1. `@Transactional` là hợp đồng của framework/transaction infrastructure

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PayOrderService {
    private final OrderRepository orders;

    public PayOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void markPaid(Long orderId) {
        OrderEntity order = orders.findById(orderId)
                .orElseThrow();
        order.markPaid();
    }
}
~~~

Trong một cấu hình Spring transaction manager thông dụng, transaction được quản lý quanh method gọi qua proxy; provider ORM đồng bộ và commit theo thứ tự tích hợp. Bản thân **Jakarta Persistence không định nghĩa `org.springframework.transaction.annotation.Transactional`**.

Có cả những API transaction khác trong hệ sinh thái, chẳng hạn Jakarta Transactions (`jakarta.transaction.Transactional`, JTA). Cần biết hệ thống đang dùng transaction manager nào thay vì nghĩ tất cả annotation có cùng mặc định.

Chú ý: self-invocation trong cấu hình Spring proxy thường không đi qua interceptor; checked exception có chính sách rollback riêng. Việc `@Transactional` có mặt trên method không tự bảo đảm hai datasource khác nhau cùng tham gia một transaction phân tán.

## 7. Hibernate cung cấp những gì ngoài JPA?

Một provider có thể đưa ra API riêng để giải quyết các vấn đề chưa được chuẩn hóa đầy đủ hoặc tối ưu trên một stack cụ thể.

Ví dụ với Hibernate:

| Loại extension | Minh họa | Chi phí đi kèm |
| --- | --- | --- |
| API native | `org.hibernate.Session`, `SessionFactory` | Source phụ thuộc Hibernate |
| Mapping đặc thù | `org.hibernate.annotations.BatchSize`, `Filter` | Provider khác có thể không hiểu |
| HQL mở rộng | Cú pháp/tính năng ngoài tập JPQL chuẩn | Khó chuyển provider |
| Cấu hình batching | Các property như `hibernate.jdbc.batch_size` | Phụ thuộc provider và workload |
| Cache và fetch tuning | Fetch profile, cache region, batch/subselect strategy | Phải đo tính nhất quán, bộ nhớ và query count |
| Kiểu dữ liệu chuyên biệt | JSON, array hoặc user-defined type theo hỗ trợ Hibernate/DBMS | Có thể phụ thuộc cả dialect và schema |

Ví dụ một annotation riêng:

~~~java
import org.hibernate.annotations.BatchSize;
import jakarta.persistence.OneToMany;

// Đặt trong entity với field quan hệ đã khai báo phù hợp:
@OneToMany(mappedBy = "order")
@BatchSize(size = 25)
private java.util.List<OrderItemEntity> items;
~~~

Ở đây `@OneToMany` là JPA chuẩn; `@BatchSize` là extension của Hibernate. Kích thước 25 là ví dụ và không phải lời hứa rằng luôn đúng một SQL cho 25 collection. Cần kiểm tra SQL thực, cache, số quan hệ được truy cập và cách Hibernate chọn batch fetch.

Có thể chủ động truy cập native API khi thực sự cần:

~~~java
import org.hibernate.Session;

Session session = entityManager.unwrap(Session.class);
~~~

Từ dòng này, mã phụ thuộc vào việc provider bên dưới hỗ trợ unwrap sang Hibernate `Session`. Với một provider khác, lời gọi có thể thất bại. Tính di động không còn ở phạm vi “chỉ đổi dependency” mà phải viết lại phần phụ thuộc extension.

### 7.1. Sử dụng extension không đồng nghĩa thiết kế kém

Các ứng dụng thực tế đôi khi cần tính năng riêng để đạt yêu cầu:

- Batch lớn hoặc kiểm soát fetch đặc biệt.
- Lưu JSON/array theo DBMS.
- Full-text search hoặc tính năng truy vấn riêng.
- Thao tác bulk, stateless processing hay cache với workload đặc thù.

Nếu extension là lựa chọn hợp lý, hãy **cô lập nó trong persistence adapter**, tài liệu hóa sự phụ thuộc và có integration test. Đừng bắt domain service import `Session` hoặc annotation chuyên biệt chỉ vì một optimization nhỏ trong repository.

## 8. Những thứ đặc tả JPA không làm biến mất

### 8.1. SQL và kế hoạch thực thi vẫn có chi phí thật

Một lệnh JPQL trông ngắn có thể phát nhiều SQL. Ví dụ:

~~~java
var orders = entityManager.createQuery(
        "SELECT o FROM OrderEntity o WHERE o.tenantId = :tenant",
        OrderEntity.class)
    .setParameter("tenant", 42L)
    .getResultList();

for (OrderEntity order : orders) {
    // Nếu items là collection LAZY chưa nạp, truy cập có thể
    // kích hoạt thêm SQL cho mỗi order.
    int itemCount = order.getItems().size();
}
~~~

Nếu truy vấn đầu lấy N order và mỗi lần truy cập collection làm một SELECT riêng, hệ thống sinh **N+1 query**. Nhưng con số thực tế có thể khác nhờ cache, batch fetching, fetch join hoặc provider strategy. Không kết luận bằng cảm giác; hãy đếm SQL trong một integration test.

Một entity `@ManyToOne` mặc định **EAGER** theo JPA; `@OneToMany` mặc định **LAZY**. Điều đó không có nghĩa EAGER chắc chắn được triển khai bằng một SQL JOIN, cũng không bảo đảm LAZY không bao giờ đọc sớm. Fetch strategy là một phần ngữ nghĩa/hint cần được xem xét cùng mapping và provider.

Các cách khắc phục N+1 theo use case: projection DTO, join fetch có kiểm soát, entity graph, batch fetching hoặc hai bước query theo danh sách ID. Cẩn thận với **JOIN FETCH qua collection và phân trang**: kết quả SQL có thể nhân số hàng và provider có thể cảnh báo hoặc phân trang trong bộ nhớ ở một số cấu hình.

### 8.2. Transaction và isolation vẫn do runtime/DBMS thực thi

JPA hỗ trợ entity lifecycle và lock mode, nhưng transaction isolation, row lock, deadlock, MVCC và durability là trách nhiệm của môi trường transaction và DBMS.

Ví dụ **READ COMMITTED** ở PostgreSQL cho phép hai SELECT thông thường trong một transaction nhìn thấy snapshot khác nhau khi một transaction khác commit ở giữa. Dùng `EntityManager` không tự biến các SELECT đó thành một snapshot cố định.

Một transaction JPA bị `OptimisticLockException` hoặc lỗi transaction khác có thể phải rollback và chạy lại **toàn nghiệp vụ** trên một transaction mới. Các thao tác gọi hệ thống ngoài không tự rollback với database.

### 8.3. Schema và migration không tự “đúng” chỉ vì có annotation

Trong môi trường phát triển, provider có thể tạo hoặc kiểm tra schema từ mapping. Nhưng ở production, thay đổi bảng/cột/index, constraint, migration dữ liệu và khả năng rollback cần quy trình có kiểm soát.

Ví dụ JPA:

~~~java
@Column(name = "total_amount", nullable = false, precision = 14, scale = 2)
private BigDecimal totalAmount;
~~~

Điều này mô tả mapping và có thể hướng dẫn schema generation, nhưng **không thay thế**:

- Constraint trong database thực.
- Migration có thứ tự và tương thích với phiên bản code đang chạy.
- Chỉ mục phục vụ workload và truy vấn thực.
- Kiểm tra kiểu dữ liệu, collation, timezone, sequence/identity.
- Backup, restore và chính sách bảo mật.

Công cụ như Flyway hoặc Liquibase thường được dùng để quản lý migration; chúng **không phải một phần của đặc tả JPA**. Không bật thay đổi schema tự động trên production chỉ vì entity annotation mới đã được commit.

### 8.4. JDBC connection và tài nguyên vẫn tồn tại

Hibernate có thể mượn connection từ datasource/pool và gửi SQL qua JDBC. Một lời gọi JPA dài, transaction kéo dài hoặc việc serialize lazy entity có thể giữ tài nguyên DB và gây cạn pool.

Connection pool (ví dụ HikariCP) là thành phần khác với ORM. Hibernate không tự làm biến mất connect timeout, query timeout, deadlock, transaction timeout, leak và lỗi commit chưa xác định. Cần xem cấu hình pool, transaction manager và mô hình thất bại của hệ thống.

## 9. Khi nào nên lập trình theo JPA chuẩn, khi nào dùng Hibernate-specific?

Có thể dùng khung quyết định sau:

1. **Bắt đầu từ yêu cầu nghiệp vụ:** hệ thống cần CRUD đơn giản, aggregate có quan hệ, truy vấn báo cáo hay bulk processing?
2. **Chọn API ít phụ thuộc nhất đủ giải quyết:** `EntityManager` và JPQL chuẩn thường phù hợp với đường CRUD có entity lifecycle.
3. **Đo chi phí thực:** SQL count, số hàng, execution plan, p95/p99, memory, connection hold time và write throughput.
4. **Nếu cần một extension riêng**, xác định lợi ích và nơi cách ly: mapping, repository adapter, query helper hoặc module DB-specific.
5. **Ghi rõ hợp đồng migration/provider:** nếu đổi Hibernate sang provider khác, phần nào phải viết lại? Nếu chỉ đổi PostgreSQL sang DB khác, SQL native/index nào phải thay?
6. **Kiểm thử transaction và sự cố:** `@Version`, concurrent update, lazy loading, rollback, deadlock, retry, kết quả COMMIT chưa rõ.
7. **Ưu tiên tính đúng đắn:** chọn SQL nguyên tử/constraint ở DB cho bất biến quan trọng, không giả định ORM bảo vệ mọi tình huống đồng thời.

Ví dụ, một ứng dụng quản lý danh mục sản phẩm có thể sử dụng JPA cho entity và Spring Data JPA repository. Nhưng báo cáo phân tích hàng chục triệu bản ghi có thể được thực thi hiệu quả hơn bằng SQL được tối ưu riêng, projection hoặc pipeline chuyên biệt. Hai cách có thể cùng tồn tại sau **một ranh giới persistence rõ ràng**.

### 9.1. Tính di động có nhiều cấp độ

| Cấp độ | Ví dụ | Mức độ rủi ro khi chuyển |
| --- | --- | --- |
| Source Java dùng annotation/API chuẩn | `@Entity`, `EntityManager.find()`, JPQL cơ bản | Thường ít phụ thuộc provider hơn |
| Tính năng provider | `@BatchSize`, `Session`, HQL extension | Cần kiểm tra và có thể viết lại |
| Behavior/hiệu năng | Thời điểm flush, strategy fetch, batching, cache | Có thể thay đổi dù source vẫn biên dịch |
| SQL/dialect | `jsonb`, upsert, window function, sequence/identity | Phụ thuộc DBMS, dialect và phiên bản |
| Semantics dữ liệu | Isolation, deadlock, locking, timestamp, collation | Phải thử nghiệm trên DB thật |
| Vận hành | Migration, backup, driver timeout, pool, replica | Phụ thuộc hạ tầng và cấu hình |

**Portable về API không đồng nghĩa portable về hiệu năng hoặc hành vi vận hành.** Một ứng dụng có thể chạy được với provider khác nhưng chậm hơn, hoặc phát sinh khác biệt về truy vấn và khóa trong các tình huống biên.

## 10. Java SE và container-managed transaction: hai cấu hình triển khai

Ngoài Spring, JPA còn được dùng trực tiếp trong Java SE hoặc Jakarta EE container.

Ví dụ khái niệm cho **resource-local transaction** trong Java SE:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

public final class ExampleApplication {
    public static void main(String[] args) {
        // Giả định persistence unit "shop-pu" đã được cấu hình
        // với một provider tương thích và kết nối DB hợp lệ.
        try (EntityManagerFactory emf =
                     Persistence.createEntityManagerFactory("shop-pu")) {

            EntityManager em = emf.createEntityManager();
            try {
                EntityTransaction tx = em.getTransaction();
                try {
                    tx.begin();
                    em.persist(new OrderEntity(42L,
                            new java.math.BigDecimal("250000.00")));
                    tx.commit();
                } catch (RuntimeException failure) {
                    if (tx.isActive()) {
                        try {
                            tx.rollback();
                        } catch (RuntimeException rollbackFailure) {
                            failure.addSuppressed(rollbackFailure);
                        }
                    }
                    throw failure;
                }
            } finally {
                em.close();
            }
        }
    }
}
~~~

Ví dụ dành cho stack hỗ trợ `EntityManagerFactory` là `AutoCloseable` theo API tương ứng; với các phiên bản cũ, đóng factory bằng `close()` trong `finally`. Nếu muốn giữ khả năng chạy trên nhiều phiên bản JPA hơn, có thể dùng `try/finally` cho cả factory. Đây là mô tả việc gọi API, **không bao gồm cấu hình persistence unit, JDBC driver hay kết nối**.

Trong ứng dụng Spring/Jakarta EE quản lý transaction, thường không gọi `em.getTransaction()` và `commit()` tùy tiện trên entity manager do container quản lý. Hãy để transaction manager sở hữu ranh giới commit/rollback, tránh tạo hai cách điều phối xung đột.

### 10.1. Lỗi commit có thể chưa rõ kết quả

Nếu mất kết nối trong khi `commit()` đang được thực thi, client có thể không nhận phản hồi dù DB đã commit. Không retry một lần tạo đơn bằng khóa nghiệp vụ mới mà thiếu idempotency. Một đặc tả ORM không thay thế cơ chế request key, UNIQUE constraint và đối soát trên database.

## 11. Một quy trình kiểm thử để biết mình có thực sự đang dùng JPA theo chuẩn

Trong một dự án Java thực tế, có thể tiến hành:

1. **Đọc import và dependency của chính dự án:** `jakarta.persistence.*` hay `javax.persistence.*`? Có dùng `org.hibernate.*` ngoài persistence adapter không?
2. **Xác nhận provider lúc khởi động:** framework đang chọn Hibernate, EclipseLink hay triển khai khác? Đúng phiên bản với Jakarta Persistence API không?
3. **Ghi nhận SQL thật:** bật SQL statistics/log phù hợp trong môi trường test; kiểm tra `persist`, flush, lazy loading và repository method nào tạo thêm SQL.
4. **Thử truy vấn theo workload:** dữ liệu tenant nhỏ và lớn, cache lạnh và ấm, truy vấn đọc nhiều hàng và truy vấn ghi có tranh chấp.
5. **Đo DB:** với PostgreSQL, dùng `EXPLAIN (ANALYZE, BUFFERS)` trên SQL thực, quan sát index condition, sort, số hàng và I/O.
6. **Thử optimistic locking:** hai transaction đọc cùng entity có `@Version`, rồi cùng cập nhật; kiểm tra xung đột được báo và nghiệp vụ không mất dữ liệu.
7. **Thử các đường rollback:** lỗi constraint, deadlock, COMMIT không rõ kết quả, transaction timeout và connection pool exhaustion.
8. **Kiểm tra migration:** mapping có tương thích với schema đã triển khai, constraint và index có tồn tại thật, code cũ/mới cùng chạy được trong giai đoạn rollout không?
9. **Nếu định đổi provider:** chạy cùng test tích hợp, ghi các vị trí dùng extension rồi đánh giá khác biệt semantic và plan trước khi quyết định.

Không nên định nghĩa “dùng JPA chuẩn” chỉ bằng việc không nhìn thấy import Hibernate trong một class. Cấu hình, query extension, annotation, native SQL, provider-specific hint và schema dialect ở những tầng khác vẫn có thể tạo phụ thuộc.

## 12. Những ngộ nhận thường gặp

**“JPA là một framework ORM hoàn chỉnh giống Hibernate.”** JPA/Jakarta Persistence là đặc tả và API; Hibernate là một triển khai.

**“Spring Data JPA chính là Hibernate.”** Spring Data JPA hỗ trợ repository, còn Hibernate là provider thường được dùng bên dưới; chúng có vai trò khác nhau.

**“JPA và Hibernate phải chọn một trong hai.”** Một ứng dụng có thể dùng API JPA với Hibernate provider.

**“Chỉ cần thay `javax` thành `jakarta` là nâng cấp thành công.”** Cần kiểm tra provider, framework, dependency và runtime tương thích.

**“Viết JPQL là không cần hiểu SQL.”** Provider vẫn sinh SQL và DB vẫn thực thi join, index, sort, lock và transaction.

**“Một method repository luôn tương đương một SQL.”** Lazy loading, cascade, flush và fetch strategy có thể sinh thêm câu SQL.

**“Dùng `@OneToMany(fetch = EAGER)` luôn sửa N+1.”** EAGER không đảm bảo một JOIN hay một SQL; có thể dẫn đến tải dữ liệu thừa.

**“`entityManager.flush()` nghĩa là commit đã bền vững.”** Flush đồng bộ state vào DB trong transaction; vẫn có thể rollback.

**“`@Version` bảo vệ mọi UPDATE trong cả hệ thống.”** Các đường ghi ngoài ORM cần tuân thủ cùng quy tắc version/constraint nếu muốn giữ bất biến.

**“Dùng JPA là đổi PostgreSQL sang MySQL không cần kiểm thử.”** Dialect, SQL native, isolation, sequence, kiểu dữ liệu và hiệu năng có thể khác.

**“Annotation tự thay thế migration.”** Schema production phải có quy trình thay đổi, kiểm chứng ràng buộc và phục hồi.

**“Dùng Hibernate extension là vi phạm kiến trúc.”** Extension có thể hợp lý nếu mang lại lợi ích được đo và được cô lập, ghi rõ sự phụ thuộc.

## 13. Bài tập thực hành

**Bài 1 — xác định tầng.** Với các từ `@Entity`, `EntityManager`, `JpaRepository`, `Session`, `PreparedStatement`, `PostgreSQL`, hãy phân loại chúng thuộc Jakarta Persistence API, Hibernate-specific API, Spring Data, JDBC hay DBMS. Giải thích vai trò và quan hệ giữa các tầng.

**Bài 2 — kiểm tra import.** Một dự án Spring có entity dùng `javax.persistence.Entity`, trong khi phần còn lại nâng cấp lên stack Jakarta Persistence 3.x. Vì sao ứng dụng có thể không nhận mapping? Liệt kê những dependency/phiên bản cần kiểm tra cùng nhau và đề xuất bước migration an toàn.

**Bài 3 — phân biệt API và thực thi.** Viết entity với `@Id`, `@Column` và `@Version`, sau đó chạy hai transaction cập nhật cùng hàng. Quan sát trường hợp xung đột optimistic locking trên provider đang dùng. Giải thích tại sao lỗi có thể được báo khi flush hoặc commit, không nhất thiết ngay khi gọi setter.

**Bài 4 — đọc chi phí truy vấn.** Tạo một `OrderEntity` có `@OneToMany` tới `OrderItemEntity`; dùng danh sách 20 order rồi gọi `items.size()` trong vòng lặp. Đếm SQL với cấu hình mặc định, so sánh với DTO projection hoặc batch fetching. Không giả định query count mà không đo.

**Bài 5 — tính di động.** Một repository đang dùng JPQL chuẩn, riêng màn hình tìm kiếm dùng HQL extension và JSONB operator của PostgreSQL. Nếu chuyển provider hoặc chuyển DBMS, hãy lập bảng những phần cần kiểm tra/chỉnh sửa. Vì sao hai loại chuyển đổi có mức rủi ro khác nhau?

**Bài 6 — chọn công cụ.** Với ba use case: quản lý entity đơn giản, báo cáo hàng triệu hàng và trừ tồn kho có điều kiện, hãy chọn JPA entity lifecycle, DTO/native SQL hoặc JDBC SQL nguyên tử theo nhu cầu. Nêu ranh giới transaction, chỉ mục cần đo và bất biến dữ liệu cần bảo vệ.

## Ghi nhớ

**Jakarta Persistence (JPA) là đặc tả và API; Hibernate ORM là một thư viện hiện thực có thể làm persistence provider; Spring Data JPA là thư viện hỗ trợ repository ở tầng cao hơn.** Dùng `EntityManager`, entity mapping và JPQL giúp giảm phụ thuộc vào API riêng, nhưng không xóa bỏ sự phụ thuộc vào database, SQL thực, transaction, bộ đệm, migration hoặc các tính năng provider-specific.

Khi thiết kế persistence cho Java, hãy chọn abstraction theo use case, cô lập extension khi cần, kiểm chứng SQL và hiệu năng trên DB thật, bảo vệ dữ liệu bằng transaction/constraint/locking phù hợp, và đảm bảo kết quả commit hoặc lỗi kết nối được xử lý đúng ranh giới nghiệp vụ.
