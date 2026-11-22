# Phía sở hữu quan hệ, mappedBy, cascade và orphanRemoval trong JPA

## Mục tiêu

Khi ánh xạ quan hệ giữa các entity, JPA cần biết phía nào quyết định quan hệ được ghi xuống database, phía nào giữ liên kết ngược trong mô hình object, và thao tác vòng đời nào được truyền sang entity liên quan. Bốn khái niệm thường đi cùng nhau là owning side, mappedBy, cascade và orphanRemoval.

Bài này trình bày cách đọc mapping, cách cập nhật quan hệ hai chiều trong Java, cách chọn cascade theo vòng đời domain và cách dùng orphanRemoval cho child entity có vòng đời phụ thuộc parent.

## 1. Owning side và inverse side

Một quan hệ hai chiều có hai đầu để điều hướng trong Java, nhưng quan hệ trong database chỉ có một biểu diễn chính, thường là foreign key hoặc join table. JPA phân biệt:

- **Owning side (phía sở hữu):** phía quyết định thay đổi quan hệ được đồng bộ xuống database.
- **Inverse side (phía ngược):** phía điều hướng còn lại, khai báo mappedBy để chỉ ra thuộc tính ở owning side đang ánh xạ cùng association.

Owning side là khái niệm về persistence mapping, không nhất thiết là aggregate root, chủ sở hữu nghiệp vụ hay entity có vòng đời dài hơn.

Khi persistence context flush, provider sử dụng owning side để ghi thay đổi quan hệ. Nếu chỉ sửa collection ở inverse side mà không cập nhật tham chiếu owning side, thay đổi có thể không được lưu như mong đợi.

### Quy tắc theo loại quan hệ

| Quan hệ hai chiều | Owning side | Inverse side |
|---|---|---|
| OneToMany / ManyToOne | ManyToOne (phía nhiều) | OneToMany, có mappedBy |
| OneToOne | Phía ánh xạ foreign key | Phía còn lại, có mappedBy |
| ManyToMany | Một phía được chọn để ánh xạ join table | Phía còn lại, có mappedBy |

Trong quan hệ hai chiều OneToMany/ManyToOne, phía ManyToOne là owning side. Không đặt mappedBy ở ManyToOne.

### Ví dụ quan hệ đơn hàng và dòng hàng

Giả sử database có cấu trúc:

~~~text
purchase_order
--------------
id (PK)

order_line
----------
id (PK)
sku
quantity
purchase_order_id (FK -> purchase_order.id)
~~~

Foreign key purchase_order_id nằm trong bảng order_line. Vì vậy, OrderLine là owning side; PurchaseOrder là inverse side.

- OrderLine giữ tham chiếu tới PurchaseOrder bằng @ManyToOne và @JoinColumn.
- PurchaseOrder giữ collection OrderLine bằng @OneToMany(mappedBy = "purchaseOrder").
- Giá trị mappedBy là tên thuộc tính Java purchaseOrder trong OrderLine.

## 2. mappedBy và JoinColumn

mappedBy chỉ được khai báo ở inverse side của quan hệ hai chiều OneToOne, OneToMany hoặc ManyToMany. Giá trị là **tên thuộc tính Java ở owning side**, không phải tên cột SQL, tên bảng hay tên class.

~~~java
// PurchaseOrder: inverse side
@OneToMany(mappedBy = "purchaseOrder")
private List<OrderLine> lines = new ArrayList<>();

// OrderLine: owning side
@ManyToOne
@JoinColumn(name = "purchase_order_id")
private PurchaseOrder purchaseOrder;
~~~

Trong ví dụ:

- purchaseOrder là tên field Java.
- purchase_order_id là tên cột database.
- mappedBy phải nhận "purchaseOrder".

Tên thuộc tính có phân biệt chữ hoa/chữ thường. Nếu đổi tên field ở owning side, phải đổi giá trị mappedBy tương ứng.

Với quan hệ ManyToOne thông thường, @JoinColumn đặt ở phía ManyToOne vì đây là phía ánh xạ foreign key. Phía OneToMany dùng mappedBy để trỏ tới field đó. Không ánh xạ cùng association bằng một mappedBy ở inverse side và một @JoinColumn độc lập trên chính inverse side.

### Quan hệ một chiều và hai chiều

- **Unidirectional:** chỉ một entity giữ tham chiếu hoặc collection tới entity kia. Association có một owning side.
- **Bidirectional:** cả hai entity có thể điều hướng tới nhau. Một phía sở hữu mapping; phía còn lại tham chiếu tới owning field bằng mappedBy.
- Việc thêm field tham chiếu vào cả hai class không tự động làm cho JPA hiểu chúng là hai đầu của cùng một association. Cần khai báo mapping tương ứng.

Một unidirectional OneToMany có thể dùng join table nếu không khai báo cách ánh xạ foreign key khác. Nếu muốn foreign key nằm ở bảng con, có thể dùng @JoinColumn trên collection mapping theo quy tắc JPA. Hãy xác định schema mong muốn trước khi chọn kiểu mapping.

## 3. Đồng bộ hai phía trong bộ nhớ

JPA dùng owning side để ghi quan hệ, nhưng ứng dụng cần giữ cả hai đầu của quan hệ hai chiều nhất quán trong bộ nhớ.

Ví dụ chỉ thêm child vào collection:

~~~java
order.getLines().add(line);
~~~

Collection có thể chứa line, nhưng line.getPurchaseOrder() vẫn là null. Vì OrderLine là owning side, foreign key có thể không được ghi đúng.

Hãy đóng gói việc cập nhật hai đầu trong helper method:

~~~java
public void addLine(OrderLine line) {
    lines.add(line);
    line.setPurchaseOrder(this);
}

public void removeLine(OrderLine line) {
    if (lines.remove(line)) {
        line.setPurchaseOrder(null);
    }
}
~~~

addLine cập nhật collection và owning reference. removeLine gỡ child khỏi collection và xóa tham chiếu ngược. Code service chỉ gọi một phương thức domain thay vì phải nhớ cập nhật hai field riêng.

Một số nguyên tắc khi viết helper method:

- Đặt helper method ở entity quản lý collection để đóng gói quy tắc quan hệ.
- Không để code bên ngoài tùy ý sửa collection mà quên owning side.
- Khi chuyển child sang parent khác, xử lý quan hệ cũ và mới một cách có chủ đích.
- Với orphanRemoval=true, không xem child là entity có thể chuyển tự do giữa các parent.
- Nếu dùng Set, thiết kế equals và hashCode cẩn thận, đặc biệt với entity có ID sinh tự động.
- Tránh dùng Lombok @Data máy móc cho entity hai chiều vì equals, hashCode và toString có thể đi qua quan hệ vòng lặp hoặc kích hoạt lazy loading.

## 4. Cascade: truyền thao tác vòng đời

Cascade xác định thao tác trên entity nguồn có được truyền tới entity đích đang được tham chiếu hay không. Cascade được khai báo trên association và truyền theo hướng từ entity có annotation tới entity liên quan.

Mặc định JPA không cascade thao tác nào. Các loại cascade:

| Cascade type | Hành vi |
|---|---|
| PERSIST | Khi persist entity nguồn, persist entity đích được cascade |
| MERGE | Khi merge entity nguồn, merge entity đích được cascade |
| REMOVE | Khi remove entity nguồn, remove entity đích được cascade |
| REFRESH | Khi refresh entity nguồn, refresh entity đích được cascade |
| DETACH | Khi detach entity nguồn, detach entity đích được cascade |
| ALL | Bao gồm PERSIST, MERGE, REMOVE, REFRESH và DETACH |

Ví dụ chỉ cascade persist:

~~~java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Khi persist PurchaseOrder, thao tác persist được truyền tới các OrderLine đang được tham chiếu qua association này.

Có thể chọn nhiều loại cascade:

~~~java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE}
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Hoặc dùng CascadeType.ALL khi vòng đời của child thực sự phụ thuộc vào parent:

~~~java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = CascadeType.ALL
)
private List<OrderLine> lines = new ArrayList<>();
~~~

ALL là tập hợp các loại cascade được liệt kê ở trên. Nó không có nghĩa là cascade mọi truy vấn, mọi transaction hoặc mọi thao tác HTTP.

### Chọn cascade theo vòng đời domain

Cascade thường phù hợp khi entity đích chỉ có ý nghĩa trong phạm vi entity nguồn. Ví dụ, OrderLine thường thuộc một PurchaseOrder; khi lưu đơn hàng mới, ta muốn các dòng hàng mới được persist cùng.

Không bật cascade một cách máy móc:

- Nếu entity đích được nhiều entity khác dùng chung, cascade REMOVE có thể xóa dữ liệu còn được tham chiếu.
- Với ManyToMany như Student–Course, xóa Student thường chỉ nên xóa các dòng join table; không nên cascade REMOVE để xóa Course đang được nhiều Student dùng chung.
- Cascade không thay thế việc phân biệt entity transient, managed và detached.
- PERSIST một entity detached có thể dẫn tới EntityExistsException hoặc PersistenceException khi flush/commit.
- MERGE sao chép trạng thái sang instance managed; sau merge, dùng instance được trả về hoặc làm việc trong persistence context đúng cách.

Một câu hỏi hữu ích khi chọn cascade là: nếu thực hiện thao tác vòng đời trên entity nguồn, entity đích có nên chịu cùng thao tác không? Chỉ thêm những loại cascade phù hợp với câu trả lời đó.

Theo Jakarta Persistence, cascade REMOVE chỉ nên áp dụng cho association OneToOne hoặc OneToMany để bảo đảm tính portable. Áp dụng nó cho ManyToMany hoặc association khác không portable giữa các provider.

## 5. orphanRemoval: xóa entity khi bị tách khỏi quan hệ

orphanRemoval là tùy chọn của OneToOne và OneToMany. Khi entity đích bị loại khỏi quan hệ, ví dụ bị xóa khỏi collection hoặc tham chiếu được đặt về null, JPA áp dụng thao tác remove lên entity bị orphan. Việc xóa được thực hiện khi persistence context flush.

~~~java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Khi một OrderLine bị gỡ khỏi PurchaseOrder bằng helper method, JPA sẽ xóa entity child khỏi database tại flush/commit. Không cần gọi repository.delete(line) riêng cho trường hợp này.

### Cascade REMOVE và orphanRemoval khác nhau

| Tình huống | Cascade REMOVE | orphanRemoval |
|---|---|---|
| Xóa entity nguồn | Truyền remove tới entity đích nếu có cascade REMOVE | Thao tác remove trên nguồn cũng được truyền tới target theo quy tắc JPA |
| Chỉ gỡ child khỏi collection | Không tự xóa child chỉ vì association bị gỡ | Xóa child bị orphan tại flush |
| Đặt tham chiếu về null | Không tự xóa child chỉ vì tham chiếu bị gỡ | Xóa child bị orphan tại flush |
| Phạm vi association portable | Nên dùng với OneToOne/OneToMany | Chỉ hỗ trợ OneToOne/OneToMany |

orphanRemoval=true đã bao hàm hành vi xóa target khi parent bị xóa theo quy tắc JPA. Không cần thêm cascade=REMOVE chỉ để đạt hành vi đó; các cascade khác như PERSIST hoặc MERGE vẫn có thể cần thiết.

### Chỉ dùng cho child có vòng đời phụ thuộc parent

orphanRemoval thể hiện child là thành phần có quyền sở hữu riêng của parent và không có vòng đời độc lập. Ví dụ:

- OrderLine thuộc riêng một PurchaseOrder.
- AddressDetail thuộc riêng một CustomerProfile.
- TaskStep thuộc riêng một WorkflowDefinition.

Không dùng orphan removal cho entity được chia sẻ độc lập giữa nhiều parent. Khi child bị gỡ khỏi một quan hệ, việc xóa nó có thể làm hỏng dữ liệu nơi khác.

Ứng dụng portable không nên dựa vào thứ tự xóa cụ thể, cũng không nên gán lại entity đã thành orphan sang quan hệ khác hoặc cố persist lại nó. Quy tắc orphan removal không áp dụng với target đang detached, new hoặc removed.

### orphanRemoval không phải ON DELETE CASCADE

Hai cơ chế nằm ở hai tầng:

- **JPA cascade/orphanRemoval:** persistence provider quản lý vòng đời entity trong persistence context.
- **Foreign key ON DELETE CASCADE:** database tự xóa hàng liên quan khi hàng được tham chiếu bị xóa.

Một hệ thống có thể dùng một hoặc cả hai, nhưng không nên giả định chúng tương đương. Bulk JPQL delete cũng bỏ qua lifecycle của từng entity trong persistence context; không trông đợi cascade/orphanRemoval chạy giống khi xóa entity managed bằng EntityManager.remove.

## 6. Ví dụ hoàn chỉnh: PurchaseOrder và OrderLine

Mô hình minh họa:

- PurchaseOrder là parent.
- OrderLine là child riêng của một đơn hàng.
- Foreign key nằm trong bảng order_line.
- OrderLine là owning side.
- PurchaseOrder là inverse side nhờ mappedBy.
- Cascade ALL giúp lưu/xóa child theo parent.
- Orphan removal xóa child khi gỡ khỏi collection.

### 6.1. Schema

~~~text
purchase_order
--------------
id              PK

order_line
----------
id              PK
sku
quantity
purchase_order_id  FK -> purchase_order.id
~~~

### 6.2. Entity PurchaseOrder

~~~java
import jakarta.persistence.CascadeType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "purchaseOrder",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line, "line must not be null");

        if (line.getPurchaseOrder() != null
                && line.getPurchaseOrder() != this) {
            throw new IllegalArgumentException(
                "OrderLine already belongs to another order"
            );
        }

        if (!lines.contains(line)) {
            lines.add(line);
            line.setPurchaseOrder(this);
        }
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.setPurchaseOrder(null);
        }
    }
}
~~~

### 6.3. Entity OrderLine

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String sku;

    private int quantity;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "purchase_order_id", nullable = false)
    private PurchaseOrder purchaseOrder;

    protected OrderLine() {
    }

    public OrderLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public PurchaseOrder getPurchaseOrder() {
        return purchaseOrder;
    }

    void setPurchaseOrder(PurchaseOrder purchaseOrder) {
        this.purchaseOrder = purchaseOrder;
    }
}
~~~

Chú ý hai annotation:

- @OneToMany nằm ở PurchaseOrder và dùng mappedBy = "purchaseOrder".
- @ManyToOne nằm ở OrderLine và dùng @JoinColumn để ánh xạ foreign key.

Chỉ OrderLine quyết định giá trị purchase_order_id được ghi xuống database. Helper method của PurchaseOrder cập nhật cả collection lẫn tham chiếu này.

### 6.4. Repository và service

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

~~~java
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long createOrder() {
        PurchaseOrder order = new PurchaseOrder();
        order.addLine(new OrderLine("KB-01", 2));
        order.addLine(new OrderLine("MS-02", 1));

        return repository.save(order).getId();
    }

    @Transactional
    public void removeLine(Long orderId, Long lineId) {
        PurchaseOrder order = repository.findById(orderId)
            .orElseThrow();

        OrderLine line = order.getLines().stream()
            .filter(item -> Objects.equals(item.getId(), lineId))
            .findFirst()
            .orElseThrow();

        order.removeLine(line);
        // orphanRemoval xóa OrderLine khi persistence context flush.
    }
}
~~~

Trong createOrder, lưu một PurchaseOrder mới sẽ persist các OrderLine theo cascade PERSIST, là một phần của ALL. Khi removeLine chạy trong transaction, entity đang managed; dirty checking phát hiện thay đổi collection và orphanRemoval yêu cầu xóa child khi flush/commit. Không cần gọi save lại parent trong trường hợp này.

### 6.5. Dependency và cấu hình kiểm thử

Ví dụ Maven dùng Spring Boot 3.5.16 và Java 17. Spring Boot quản lý version của các starter:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Tạo class ứng dụng trong package cha của entity và repository:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JpaDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JpaDemoApplication.class, args);
    }
}
~~~

Với demo local, cấu hình H2 in-memory:

~~~properties
spring.datasource.url=jdbc:h2:mem:orders;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
~~~

Trong production, quản lý schema bằng migration tool như Flyway hoặc Liquibase và không để credential trong source code.

### 6.6. Kiểm thử orphanRemoval

Một integration test với @DataJpaTest xác nhận child bị xóa sau khi gỡ khỏi collection:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class PurchaseOrderRelationshipTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void removesLineWhenItIsRemovedFromOrder() {
        PurchaseOrder order = new PurchaseOrder();
        OrderLine line = new OrderLine("KB-01", 2);
        order.addLine(line);

        entityManager.persist(order);
        entityManager.flush();

        Long orderId = order.getId();
        Long lineId = line.getId();

        entityManager.clear();

        PurchaseOrder managedOrder =
            entityManager.find(PurchaseOrder.class, orderId);
        OrderLine managedLine =
            entityManager.find(OrderLine.class, lineId);

        assertThat(managedLine.getPurchaseOrder().getId())
            .isEqualTo(orderId);

        managedOrder.removeLine(managedLine);
        entityManager.flush();
        entityManager.clear();

        assertThat(entityManager.find(OrderLine.class, lineId))
            .isNull();
    }
}
~~~

Chạy test bằng Maven:

~~~bash
mvn test
~~~

Test dùng H2 từ dependency ở trên. Nó tạo một đơn hàng cùng dòng hàng, flush để ghi foreign key, tải lại entity trong persistence context mới, gỡ child và flush lần nữa. Sau đó truy vấn lại child để xác nhận entity đã bị xóa.

## 7. Owning side trong OneToOne và ManyToMany

### OneToOne

Với OneToOne, owning side là phía ánh xạ foreign key. Ví dụ bảng app_user có cột profile_id:

~~~java
@Entity
public class AppUser {

    @OneToOne
    @JoinColumn(name = "profile_id", unique = true)
    private UserProfile profile;
}
~~~

Phía UserProfile là inverse side:

~~~java
@Entity
public class UserProfile {

    @OneToOne(mappedBy = "profile")
    private AppUser user;
}
~~~

mappedBy = "profile" trỏ tới field profile trong AppUser. Nếu foreign key nằm ở bảng khác, vị trí owning side cũng thay đổi theo mapping database.

### ManyToMany

Với ManyToMany, ứng dụng chọn một phía làm owning side. Owning side thường khai báo join table:

~~~java
@Entity
public class Student {

    @ManyToMany
    @JoinTable(
        name = "student_course",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();
}
~~~

Phía Course khai báo inverse:

~~~java
@Entity
public class Course {

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();
}
~~~

Khi thêm hoặc xóa quan hệ Student–Course, cập nhật owning side và đồng bộ inverse side trong bộ nhớ. Xóa một liên kết ManyToMany thông thường chỉ xóa dòng join table, không xóa Student hoặc Course. Tránh cascade REMOVE giữa các entity có thể được nhiều đối tượng dùng chung.

Nếu quan hệ ManyToMany có thêm thuộc tính như thời điểm đăng ký, điểm số, vai trò hoặc trạng thái, cân nhắc chuyển join table thành entity liên kết riêng, ví dụ Enrollment. Khi đó association có vòng đời và dữ liệu riêng.

## 8. Fetch, cascade và ownership là các vấn đề khác nhau

| Khái niệm | Câu hỏi |
|---|---|
| Owning side | Phía nào quyết định quan hệ được ghi xuống database? |
| mappedBy | Phía inverse tham chiếu tới thuộc tính owning nào? |
| cascade | Thao tác vòng đời nào được truyền tới entity liên quan? |
| orphanRemoval | Entity có bị xóa khi bị tách khỏi quan hệ không? |
| fetch | Khi đọc entity, association được tải khi nào? |

Ví dụ @ManyToOne mặc định EAGER trong JPA, trong khi @OneToMany mặc định LAZY. Fetch strategy không quyết định owning side và cũng không bật cascade. Chọn cách tải dữ liệu theo use case để tránh tải đồ thị entity quá lớn hoặc gặp N+1 query.

## 9. Một số tình huống cần chú ý

- **Chỉ sửa inverse collection:** owning side chưa đổi nên foreign key không được cập nhật như mong đợi. Dùng helper method cập nhật cả hai đầu.
- **mappedBy trỏ tới tên cột:** mappedBy phải trỏ tới tên thuộc tính Java ở owning entity, không phải tên SQL column.
- **Đặt mappedBy ở ManyToOne:** trong quan hệ hai chiều OneToMany/ManyToOne, ManyToOne là owning side.
- **Khai báo JoinColumn ở cả hai phía:** có thể tạo mapping mâu thuẫn cho cùng association.
- **Cascade ALL cho entity dùng chung:** xóa parent có thể xóa entity được parent khác tham chiếu.
- **Cascade REMOVE trên ManyToMany:** có nguy cơ xóa entity đích dùng chung và không portable theo JPA.
- **orphanRemoval cho entity dùng chung:** gỡ association ở một parent có thể xóa dữ liệu cần ở nơi khác.
- **Gỡ child nhưng không cập nhật owning reference:** bộ nhớ và database có thể không đồng nhất.
- **Quên transaction:** lazy collection có thể không truy cập được ngoài persistence context; dirty checking cần flush trong transaction.
- **Cho rằng orphanRemoval xóa ngay lập tức:** thao tác remove được áp dụng khi flush, thường ở cuối transaction hoặc khi gọi flush.
- **Bulk JPQL delete:** không đi qua lifecycle từng entity như EntityManager.remove.
- **equals/hashCode không phù hợp:** collection Set có thể thêm/xóa entity không như mong muốn khi ID sinh tự động hoặc equality thay đổi sau persist.

## 10. Tài liệu tham khảo

- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): owning/inverse side, mappedBy, cascade và orphanRemoval.
- [Jakarta Persistence — OneToMany API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/onetomany): cascade, mappedBy, fetch và orphanRemoval.
- [Jakarta Persistence — ManyToOne API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/manytoone): mapping phía nhiều và foreign key.
- [Hibernate ORM User Guide — Associations](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html): bidirectional association, helper method, orphan removal và SQL.
- [Spring Data JPA Reference — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): ranh giới transaction khi dùng Spring Data JPA.
- [Spring Boot 3.5 — Data Access](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): cấu hình truy cập dữ liệu và JPA trong Spring Boot.

Thiết kế ownership và lifecycle từ mô hình miền trước khi chọn cascade. Khi mapping phản ánh đúng quan hệ thật, thao tác lưu, gỡ liên kết và xóa entity sẽ dễ dự đoán hơn.
