# Kiểm thử mapping, cascade, orphanRemoval và ràng buộc dữ liệu

Kiểm thử Spring Data JPA không chỉ xác nhận repository trả về đúng entity. Một mapping có thể đọc được nhưng ghi sai phía sở hữu quan hệ; cascade có thể lưu hoặc xóa nhiều entity hơn dự kiến; orphanRemoval có thể xóa nhầm dữ liệu; và constraint chỉ được database phát hiện khi câu SQL thực sự được flush.

Một bộ kiểm thử tốt cần xác nhận cả trạng thái object trong persistence context lẫn dữ liệu sau khi ghi và tải lại từ database. Bài học này dùng quan hệ PurchaseOrder – OrderLine để minh họa cách kiểm tra mapping, vòng đời entity và các ràng buộc quan trọng.

## 1. Phân biệt trách nhiệm của mapping và database

JPA mapping mô tả cách entity liên hệ với bảng và cột:

- @OneToMany, @ManyToOne và @OneToOne mô tả quan hệ giữa entity.
- mappedBy xác định phía inverse; phía còn lại là owning side, nơi JPA lấy thông tin để ghi khóa ngoại.
- cascade xác định thao tác vòng đời nào được truyền từ entity cha sang entity liên quan.
- orphanRemoval xác định entity con nào phải bị xóa khi bị loại khỏi quan hệ sở hữu.
- @Column, @JoinColumn và @Table mô tả một số đặc tính cột, khóa ngoại và tính duy nhất.

Database mới là nơi thực thi các constraint như NOT NULL, UNIQUE, FOREIGN KEY và CHECK. Annotation có thể được dùng để sinh schema trong môi trường phù hợp, nhưng nếu production schema được quản lý bằng Flyway hoặc Liquibase thì migration phải tạo constraint tương ứng. Không nên giả định chỉ thêm nullable = false trong code là database production đã có NOT NULL.

Vì vậy, cần có cả kiểm thử mapping ở tầng JPA và kiểm thử tích hợp constraint trên hệ quản trị database mà ứng dụng thực sự sử dụng.

## 2. Ví dụ mapping quan hệ hai chiều

Một đơn hàng có nhiều dòng hàng. Mỗi dòng hàng thuộc về đúng một đơn hàng. Đây là quan hệ cha – con có vòng đời phụ thuộc, nên ví dụ sử dụng cascade và orphanRemoval.

**Entity PurchaseOrder:**

~~~java
import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(
    name = "purchase_orders",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_purchase_orders_external_ref",
        columnNames = "external_ref"
    )
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "external_ref", nullable = false, length = 40)
    private String externalRef;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String externalRef) {
        this.externalRef = externalRef;
    }

    public Long getId() {
        return id;
    }

    public String getExternalRef() {
        return externalRef;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }

    public void removeLine(OrderLine line) {
        lines.remove(line);
        line.setOrder(null);
    }
}
~~~

**Entity OrderLine:**

~~~java
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
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

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

    public PurchaseOrder getOrder() {
        return order;
    }

    void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

Trong mapping này:

- OrderLine.order là owning side vì nó khai báo @ManyToOne và chứa khóa ngoại order_id.
- PurchaseOrder.lines là inverse side vì mappedBy = "order" trỏ đến thuộc tính order ở entity con.
- addLine() cập nhật cả collection của cha và tham chiếu của con.
- removeLine() loại phần tử khỏi collection và đồng bộ tham chiếu hai phía.
- cascade = CascadeType.ALL truyền các thao tác vòng đời được hỗ trợ từ cha sang con.
- orphanRemoval = true đánh dấu con bị loại khỏi collection là orphan và cần xóa khi đồng bộ persistence context.

Nếu chỉ gọi order.getLines().add(line) mà không gán line.setOrder(order), phía sở hữu không được cập nhật. Database có thể nhận order_id là NULL hoặc quan hệ không được ghi như mong muốn. Helper method giúp tránh quên đồng bộ hai phía.

## 3. Cascade và orphanRemoval khác nhau thế nào?

Hai cơ chế thường được dùng cùng nhau nhưng ý nghĩa khác nhau.

### Cascade

Cascade truyền một thao tác JPA từ entity này sang entity liên quan. Các giá trị thường gặp:

| Cascade type | Ý nghĩa |
|---|---|
| PERSIST | persist cha thì persist các entity con được cascade |
| MERGE | merge cha thì merge các entity con được cascade |
| REMOVE | remove cha thì remove các entity con được cascade |
| REFRESH | refresh cha thì refresh các entity con được cascade |
| DETACH | detach cha thì detach các entity con được cascade |
| ALL | bao gồm tất cả các thao tác trên |

Ví dụ cascade = CascadeType.PERSIST phù hợp khi muốn lưu mới cha và các con cùng lúc. CascadeType.ALL rộng hơn: nó cũng truyền REMOVE. Vì thế, không nên dùng ALL một cách máy móc nếu entity liên quan có thể được chia sẻ hoặc có vòng đời độc lập.

### orphanRemoval

orphanRemoval = true áp dụng cho quan hệ @OneToOne hoặc @OneToMany. Khi entity con bị loại khỏi quan hệ sở hữu, provider sẽ xóa entity con khi đồng bộ persistence context.

Ví dụ:

~~~java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, orderId);
OrderLine line = order.getLines().get(0);

order.removeLine(line);
entityManager.flush();
~~~

Sau flush, OrderLine đã bị tách khỏi quan hệ và được đánh dấu để xóa. orphanRemoval hữu ích khi entity con thực sự thuộc sở hữu của cha, như dòng hàng của đơn hàng.

Phân biệt tình huống:

- Xóa entity cha: CascadeType.REMOVE có thể truyền thao tác remove xuống con.
- Xóa một phần tử khỏi collection của cha: orphanRemoval xử lý entity con bị mồ côi.
- Xóa một entity dùng chung: không nên bật cascade REMOVE hoặc orphanRemoval nếu entity đó còn được tham chiếu bởi đối tượng khác.

Cascade JPA cũng khác với ON DELETE CASCADE của database. Cascade JPA được provider thực hiện theo vòng đời entity; ON DELETE CASCADE là constraint/hành vi ở database. Nếu dùng cả hai, hãy hiểu rõ đường đi xóa dữ liệu và kiểm thử bằng database thật.

## 4. Kiểm thử mapping với @DataJpaTest

@DataJpaTest của Spring Boot tạo test slice cho JPA: cấu hình entity, repository và transaction phục vụ kiểm thử persistence. Mặc định, test thường chạy trong transaction và rollback sau mỗi phương thức.

Có thể dùng TestEntityManager để persist, flush, clear và tải lại entity. Đây là cách tốt để tránh chỉ kiểm tra object đang nằm trong bộ nhớ.

**Repository:**

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

**Kiểm thử cascade persist và mapping hai phía:**

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class PurchaseOrderMappingTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void persistsChildThroughCascadeAndOwningSide() {
        PurchaseOrder order = new PurchaseOrder("PO-100");
        OrderLine line = new OrderLine("SKU-1", 2);
        order.addLine(line);

        entityManager.persist(order);
        entityManager.flush();

        Long orderId = order.getId();
        Long lineId = line.getId();

        entityManager.clear();

        PurchaseOrder reloaded =
                entityManager.find(PurchaseOrder.class, orderId);
        OrderLine reloadedLine =
                entityManager.find(OrderLine.class, lineId);

        assertThat(reloaded.getLines()).hasSize(1);
        assertThat(reloaded.getLines().get(0).getSku()).isEqualTo("SKU-1");
        assertThat(reloadedLine.getOrder().getId()).isEqualTo(orderId);
    }
}
~~~

Kiểm thử xác nhận ba điều:

1. Chỉ persist PurchaseOrder nhưng OrderLine vẫn được insert nhờ cascade PERSIST nằm trong CascadeType.ALL.
2. Quan hệ được ghi xuống database vì helper method đã cập nhật owning side.
3. Sau clear(), dữ liệu được đọc lại từ database; kết quả không chỉ dựa trên object ban đầu.

Nếu test chỉ assert order.getLines().size() trước khi flush/clear, nó chưa chứng minh khóa ngoại được ghi đúng. Collection có thể chứa phần tử trong bộ nhớ trong khi owning side vẫn null.

## 5. Kiểm thử orphanRemoval

Cần xác nhận việc bỏ một con khỏi collection thực sự xóa hàng tương ứng trong database.

~~~java
@Test
void deletesChildWhenRemovedFromParentCollection() {
    PurchaseOrder order = new PurchaseOrder("PO-200");
    OrderLine line = new OrderLine("SKU-2", 1);
    order.addLine(line);

    entityManager.persist(order);
    entityManager.flush();

    Long orderId = order.getId();
    Long lineId = line.getId();

    entityManager.clear();

    PurchaseOrder managed =
            entityManager.find(PurchaseOrder.class, orderId);
    OrderLine child = managed.getLines().get(0);

    managed.removeLine(child);
    entityManager.flush();
    entityManager.clear();

    assertThat(entityManager.find(OrderLine.class, lineId)).isNull();

    PurchaseOrder reloaded =
            entityManager.find(PurchaseOrder.class, orderId);
    assertThat(reloaded.getLines()).isEmpty();
}
~~~

Điểm quan trọng là test gọi flush() trước clear(). flush buộc provider đồng bộ thao tác xóa xuống database; clear() bỏ các entity đang được quản lý để lần kiểm tra sau phải đọc lại trạng thái đã lưu.

Test này cũng xác nhận cha vẫn tồn tại sau khi xóa một dòng hàng. Đó là hành vi mong muốn của orphanRemoval: xóa con bị tách khỏi quan hệ, không xóa luôn cha.

## 6. Kiểm thử cascade REMOVE

Cascade REMOVE kiểm tra trường hợp xóa entity cha và xác nhận entity con được xóa theo.

~~~java
@Test
void removesChildrenWhenParentIsRemoved() {
    PurchaseOrder order = new PurchaseOrder("PO-300");
    order.addLine(new OrderLine("SKU-3", 1));
    order.addLine(new OrderLine("SKU-4", 2));

    entityManager.persist(order);
    entityManager.flush();

    Long orderId = order.getId();
    Long firstLineId = order.getLines().get(0).getId();
    Long secondLineId = order.getLines().get(1).getId();

    entityManager.clear();

    PurchaseOrder managed =
            entityManager.find(PurchaseOrder.class, orderId);

    entityManager.remove(managed);
    entityManager.flush();
    entityManager.clear();

    assertThat(entityManager.find(PurchaseOrder.class, orderId)).isNull();
    assertThat(entityManager.find(OrderLine.class, firstLineId)).isNull();
    assertThat(entityManager.find(OrderLine.class, secondLineId)).isNull();
}
~~~

CascadeType.ALL chứa CascadeType.REMOVE, nên khi xóa PurchaseOrder, thao tác remove được truyền đến các OrderLine liên quan. orphanRemoval cũng có tác dụng trong vòng đời quan hệ này; test xác nhận kết quả quan sát được là các hàng con không còn trong database.

Nếu entity con có thể được nhiều entity cha tham chiếu hoặc có vòng đời riêng, cần xem lại việc cascade REMOVE trước khi dùng mapping tương tự.

## 7. Kiểm thử constraint ở database

Mapping có thể khai báo một số thuộc tính:

- @Column(nullable = false): cột bắt buộc có giá trị khi schema được sinh theo mapping.
- @Column(unique = true): khai báo tính duy nhất cho một cột khi sinh schema.
- @Table(uniqueConstraints = ...): khai báo unique constraint nhiều cột hoặc đặt tên constraint.
- @JoinColumn(nullable = false): khóa ngoại không được NULL trong schema được sinh.
- @Column(length = ...): độ dài cột khi sinh schema.

Ví dụ PurchaseOrder có external_ref bắt buộc và duy nhất. Cần xác nhận migration production thực sự tạo NOT NULL và UNIQUE tương ứng.

**Kiểm thử UNIQUE:**

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.springframework.dao.DataIntegrityViolationException;

@Test
void rejectsDuplicateExternalReference() {
    repository.saveAndFlush(new PurchaseOrder("PO-DUPLICATE"));

    assertThatThrownBy(() ->
            repository.saveAndFlush(
                    new PurchaseOrder("PO-DUPLICATE")))
            .isInstanceOf(DataIntegrityViolationException.class);
}
~~~

saveAndFlush() buộc Hibernate gửi SQL ngay, nhờ vậy constraint thường được phát hiện tại vị trí test mong đợi thay vì đến cuối transaction. Spring Data repository dịch một số lỗi persistence thành DataIntegrityViolationException.

Sau khi một lần flush thất bại, transaction thường đã bị đánh dấu rollback-only và persistence context không còn phù hợp để tiếp tục kiểm thử các thao tác persistence khác. Hãy để test kết thúc và rollback thay vì cố tiếp tục dùng cùng persistence context.

### 7.1. Những constraint cần kiểm tra

| Constraint | Ví dụ | Mục tiêu kiểm thử |
|---|---|---|
| NOT NULL | external_ref không được null | insert giá trị null bị từ chối |
| UNIQUE | external_ref không trùng | insert hai bản ghi cùng giá trị bị từ chối |
| FOREIGN KEY | order_lines.order_id phải tham chiếu đơn hàng tồn tại | insert con với parent ID không tồn tại bị từ chối |
| CHECK | quantity > 0 | insert quantity bằng 0 hoặc âm bị từ chối |
| UNIQUE nhiều cột | một sản phẩm chỉ xuất hiện một lần trong cùng đơn | cặp order_id, sku không trùng |

Các constraint trên cần được định nghĩa trong migration hoặc schema database. Ví dụ SQL migration:

~~~sql
ALTER TABLE order_lines
    ADD CONSTRAINT fk_order_lines_order
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id);

ALTER TABLE order_lines
    ADD CONSTRAINT ck_order_lines_quantity_positive
    CHECK (quantity > 0);

ALTER TABLE purchase_orders
    ADD CONSTRAINT uk_purchase_orders_external_ref
    UNIQUE (external_ref);
~~~

Cú pháp migration có thể cần điều chỉnh theo database và trạng thái schema hiện tại. Trước khi thêm constraint vào bảng đã có dữ liệu, cần xác định và xử lý các bản ghi vi phạm.

### 7.2. Bean Validation khác database constraint

Có thể dùng @NotBlank, @NotNull, @Positive hoặc @Size để kiểm tra dữ liệu ở tầng ứng dụng. Ví dụ:

~~~java
@NotBlank
@Size(max = 40)
@Column(name = "external_ref", nullable = false, length = 40)
private String externalRef;
~~~

Bean Validation giúp báo lỗi gần nơi nhận dữ liệu. Database constraint bảo vệ dữ liệu bất kể thao tác đến từ JPA, SQL trực tiếp, batch job hay ứng dụng khác.

Không nên xem hai lớp kiểm tra là thay thế nhau. Một test validation có thể chứng minh dữ liệu bị từ chối ở tầng Java nhưng không chứng minh database có constraint. Muốn kiểm tra database, cần thực thi câu SQL hoặc flush persistence operation đến database có constraint thực.

## 8. Kiểm thử khóa ngoại và phía sở hữu

Với quan hệ hai chiều, cần kiểm tra khóa ngoại thực sự được ghi ở bảng con. Một lỗi thường gặp là chỉ thêm child vào collection phía cha:

~~~java
PurchaseOrder order = new PurchaseOrder("PO-400");
OrderLine line = new OrderLine("SKU-5", 1);

// Sai: chỉ thay đổi inverse side.
order.getLines().add(line);
~~~

Vì PurchaseOrder.lines dùng mappedBy = "order", JPA lấy giá trị khóa ngoại từ OrderLine.order. Đoạn trên không gán OrderLine.order nên quan hệ không được thiết lập đúng.

Cách đúng:

~~~java
PurchaseOrder order = new PurchaseOrder("PO-400");
OrderLine line = new OrderLine("SKU-5", 1);

order.addLine(line);
~~~

Một kiểm thử có thể gọi flush() và tải lại OrderLine để xác nhận line.getOrder() trỏ về đúng đơn hàng. Nếu database có FK NOT NULL, test cũng phát hiện trường hợp owning side bị bỏ trống.

Không nên dựa riêng vào getter của collection để kết luận mapping hai chiều đúng. Hãy kiểm tra cả hai phía sau khi tải lại.

## 9. Kiểm thử với database thật bằng Testcontainers

@DataJpaTest thường có thể tự cấu hình database nhúng nếu project có H2. H2 tiện cho test nhanh nhưng không đảm bảo hoàn toàn giống MySQL, PostgreSQL hoặc Oracle về:

- Cú pháp và hành vi constraint.
- Kiểu dữ liệu, collation và so sánh chuỗi.
- Quy tắc khóa và transaction.
- SQL dialect và DDL.
- Cascade ở database, trigger và migration.

Với các hành vi phụ thuộc database, nên chạy integration test bằng Testcontainers với đúng engine production. Ví dụ trên Spring Boot 3.1+ có thể dùng @ServiceConnection:

~~~java
@Testcontainers
@DataJpaTest
class PurchaseOrderDatabaseTest {

    @Container
    @ServiceConnection
    static MySQLContainer<?> mysql =
            new MySQLContainer<>("mysql:8.4");
}
~~~

Cần có dependency Testcontainers cho JUnit Jupiter và MySQL, cùng cấu hình migration/schema phù hợp. Nếu dùng phiên bản Spring Boot cũ chưa có @ServiceConnection, có thể dùng @DynamicPropertySource để cung cấp JDBC URL, username và password của container.

Chạy migration trong test giúp xác nhận chính schema production được tạo đúng. Đặc biệt với CHECK, UNIQUE nhiều cột và hành vi FK, đây là cách kiểm tra đáng tin cậy hơn việc chỉ dựa vào H2.

## 10. Các lỗi thường gặp khi viết test

**Chỉ kiểm tra object trong bộ nhớ.** Collection có thể trông đúng nhưng owning side chưa được ghi. Hãy flush, clear và tải lại.

**Quên đồng bộ hai phía của quan hệ.** Thêm con vào collection inverse side mà không đặt tham chiếu cha ở child có thể làm khóa ngoại sai hoặc null.

**Nhầm cascade với orphanRemoval.** Cascade truyền thao tác vòng đời; orphanRemoval xóa con khi con bị tách khỏi quan hệ. Cần test riêng hai tình huống.

**Dùng CascadeType.ALL cho entity dùng chung.** Khi xóa cha, cascade REMOVE có thể xóa dữ liệu mà entity khác vẫn cần. Hãy chỉ cascade các thao tác phù hợp với ownership thực tế.

**Không flush trong test constraint.** Lỗi SQL có thể chỉ xuất hiện khi flush hoặc commit. Dùng saveAndFlush() hoặc entityManager.flush() để xác định chính xác điểm phát sinh.

**Kiểm thử constraint chỉ trên H2.** Hành vi khác database production có thể làm test xanh giả. Chạy thêm test với đúng engine khi cần xác nhận DDL và constraint.

**Tiếp tục dùng persistence context sau lỗi constraint.** Transaction có thể đã rollback-only. Hãy kết thúc test và để transaction test rollback.

**Bỏ qua migration.** Annotation mapping không tự cập nhật schema production nếu dự án dùng migration quản lý DDL. Kiểm tra migration và schema thực tế cùng với code entity.

## 11. Checklist cho một bộ kiểm thử mapping

1. Xác nhận đúng owning side và mappedBy.
2. Kiểm tra helper method cập nhật cả hai phía của quan hệ.
3. Persist cha và xác nhận cascade PERSIST lưu con.
4. Flush, clear và tải lại để xác nhận khóa ngoại.
5. Bỏ một con khỏi collection, flush và xác nhận orphanRemoval xóa con.
6. Xóa cha và xác nhận cascade REMOVE theo đúng ownership.
7. Thử vi phạm NOT NULL, UNIQUE, FOREIGN KEY và CHECK.
8. Xác nhận các lỗi constraint được phát hiện tại flush hoặc câu SQL dự kiến.
9. Chạy migration và kiểm thử trên đúng database khi có hành vi phụ thuộc engine.
10. Kiểm tra không có entity dùng chung bị xóa ngoài ý muốn.

## Kết luận

Kiểm thử mapping phải xác nhận dữ liệu được ghi đúng ở owning side và quan hệ vẫn đúng sau khi tải lại từ database. Cascade kiểm soát thao tác vòng đời được truyền từ cha sang con; orphanRemoval xóa con bị tách khỏi quan hệ sở hữu. Database constraint bảo vệ tính toàn vẹn dữ liệu ngay cả khi thao tác không đi qua JPA.

Kết hợp @DataJpaTest, flush/clear, kiểm thử constraint và Testcontainers khi cần sẽ giúp phát hiện lỗi mapping và vòng đời entity trước khi chúng xuất hiện trong production.