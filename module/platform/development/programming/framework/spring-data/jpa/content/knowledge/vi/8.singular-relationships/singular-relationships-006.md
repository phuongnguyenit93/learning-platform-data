# Đồng bộ hai phía quan hệ bằng phương thức nghiệp vụ

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao một quan hệ hai chiều trong JPA có hai tham chiếu object nhưng chỉ một phía thường là chủ sở hữu quan hệ ở database.
- Xác định owning side và inverse side qua `mappedBy`.
- Viết phương thức nghiệp vụ để thêm, xóa và thay đổi quan hệ mà luôn đồng bộ cả hai phía trong bộ nhớ.
- Phân biệt cascade với orphanRemoval và chọn đúng vòng đời cho entity con.
- Kiểm thử trạng thái object graph, khóa ngoại được lưu và hành vi xóa orphan.
- Tránh lỗi thường gặp như chỉ cập nhật inverse side, sửa collection trực tiếp, tạo vòng lặp JSON hoặc phát sinh N+1 query.

## 1. Vì sao cần đồng bộ hai phía?

JPA cho phép mô hình hóa quan hệ hai chiều giữa các entity. Ví dụ một đơn hàng có nhiều dòng hàng, và mỗi dòng hàng biết đơn hàng mà nó thuộc về.

Trong Java, quan hệ đó có hai đường truy cập:

- Từ đơn hàng đến các dòng hàng: `order.getLines()`.
- Từ một dòng hàng đến đơn hàng: `line.getOrder()`.

Hai tham chiếu này mô tả cùng một quan hệ nghiệp vụ. Nếu code chỉ thêm dòng hàng vào collection của đơn hàng mà không gán ngược đơn hàng vào dòng hàng, object graph trong bộ nhớ trở nên không nhất quán.

Ví dụ lỗi:

~~~java
order.getLines().add(line);
// line.getOrder() vẫn null
~~~

Ngược lại:

~~~java
line.setOrder(order);
// order.getLines() chưa chứa line
~~~

Trong cả hai trường hợp, hai phía của quan hệ không đồng bộ. Điều này có thể làm code nghiệp vụ đọc kết quả khác nhau tùy hướng truy cập và khiến trạng thái object không phản ánh đúng dữ liệu mong muốn.

Cách tổ chức tốt là đóng gói thao tác thay đổi quan hệ trong phương thức nghiệp vụ như `addLine()`, `removeLine()`, `assignTo()` hoặc `enroll()`. Phương thức đó cập nhật cả hai phía và bảo vệ invariant của domain.

## 2. Owning side và inverse side

Đồng bộ object graph và ghi quan hệ xuống database là hai vấn đề liên quan nhưng không giống nhau.

Trong JPA, owning side là phía quyết định giá trị khóa ngoại hoặc bản ghi join table. Với quan hệ một-nhiều phổ biến:

- `@ManyToOne` ở entity con thường là owning side vì nó chứa foreign key.
- `@OneToMany(mappedBy = "...")` ở entity cha là inverse side vì nó trỏ đến thuộc tính owning side.

Ví dụ:

~~~java
@Entity
public class PurchaseOrder {
    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}

@Entity
public class OrderLine {
    @ManyToOne
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;
}
~~~

Ở đây `mappedBy = "order"` trỏ đến tên thuộc tính Java `order` trong entity `OrderLine`, không phải tên cột `order_id`.

Nếu chỉ thêm phần tử vào collection `PurchaseOrder.lines` mà không cập nhật `OrderLine.order`, provider không có giá trị owning side đúng để ghi foreign key. Ngược lại, nếu chỉ cập nhật `OrderLine.order`, foreign key có thể được ghi đúng nhưng collection `PurchaseOrder.lines` trong bộ nhớ vẫn chưa phản ánh quan hệ đó.

Vì vậy, với quan hệ hai chiều, hãy luôn cập nhật cả hai phía trong cùng một thao tác nghiệp vụ. Owning side quyết định dữ liệu quan hệ được ghi; helper method bảo đảm object graph nhất quán.

### Quy tắc cho các kiểu quan hệ

| Quan hệ | Owning side thường gặp | Inverse side |
|---|---|---|
| One-to-many / many-to-one | `@ManyToOne` ở phía nhiều | `@OneToMany(mappedBy = ...)` ở phía một |
| One-to-one | Phía có `@JoinColumn` | Phía có `mappedBy` |
| Many-to-many | Phía khai báo `@JoinTable` hoặc không có mappedBy | Phía khai báo `mappedBy` |

Không có quy tắc rằng collection luôn là owning side. Hãy đọc mapping và xác định nơi đặt foreign key hoặc join table.

## 3. Ví dụ chính: PurchaseOrder và OrderLine

Giả sử một đơn hàng có nhiều dòng hàng. Mỗi dòng hàng chỉ thuộc về một đơn hàng. Dòng hàng không có ý nghĩa độc lập nếu đã bị gỡ khỏi đơn hàng, nên mô hình dùng `orphanRemoval = true`.

### Entity cha: PurchaseOrder

~~~java
package com.example.orders;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
        // Required by JPA
    }

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line, "line must not be null");

        if (line.getOrder() != null && line.getOrder() != this) {
            throw new IllegalArgumentException(
                "OrderLine already belongs to another order"
            );
        }

        if (lines.contains(line)) {
            return;
        }

        lines.add(line);
        line.attachTo(this);
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.attachTo(null);
        }
    }
}
~~~

### Entity con: OrderLine

~~~java
package com.example.orders;

import java.util.Objects;

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

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false, length = 40)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
        // Required by JPA
    }

    public OrderLine(String sku, int quantity) {
        this.sku = Objects.requireNonNull(sku, "sku must not be null");
        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    // Package-private: relationship changes go through PurchaseOrder.
    void attachTo(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

Trong ví dụ:

- `OrderLine.order` là owning side và chứa foreign key `order_id`.
- `PurchaseOrder.lines` là inverse side do `mappedBy = "order"`.
- `addLine()` thêm vào collection và gán owning side.
- `removeLine()` gỡ khỏi collection và xóa tham chiếu ngược trong object graph.
- `getLines()` trả về view không sửa được để code bên ngoài không thể bỏ qua helper method.
- `orphanRemoval = true` biểu thị dòng hàng là entity phụ thuộc vào đơn hàng; khi bị gỡ khỏi collection của parent đang được quản lý, nó sẽ được đánh dấu xóa khi flush.
- `cascade = CascadeType.ALL` phù hợp với mô hình aggregate này vì dòng hàng có vòng đời thuộc về đơn hàng.

Ví dụ này dùng Java 17+ và Jakarta Persistence, phù hợp với stack Spring Boot 3 / Spring Framework 6. Các entity được đặt trong cùng package để entity cha gọi phương thức package-private `attachTo()`. Mã ví dụ là hai file entity riêng, không phải một chương trình Java độc lập có thể chạy nếu thiếu dependency JPA và cấu hình database.

### Vì sao không public setter cho quan hệ?

Nếu mọi nơi đều gọi được `line.setOrder(order)` hoặc sửa trực tiếp collection, quy tắc đồng bộ bị phân tán. Một service có thể quên cập nhật phía còn lại hoặc gán một dòng hàng sang đơn hàng khác mà không kiểm tra invariant.

Giới hạn setter quan hệ ở package hoặc chỉ cung cấp phương thức nghiệp vụ giúp domain model kiểm soát cách quan hệ thay đổi. Các trường hợp cần reassign nên được mô hình hóa bằng một thao tác nghiệp vụ riêng, có kiểm tra trạng thái và quy tắc vòng đời.

## 4. Dùng phương thức nghiệp vụ để bảo vệ invariant

Helper method không chỉ là hai dòng add/remove. Nó là nơi bảo vệ các quy tắc của domain.

Ví dụ, một đơn hàng có thể chỉ nhận dòng hàng khi đang ở trạng thái DRAFT:

~~~java
public void addLine(OrderLine line) {
    if (status != OrderStatus.DRAFT) {
        throw new IllegalStateException(
            "Only draft orders can be changed"
        );
    }

    Objects.requireNonNull(line, "line must not be null");

    if (line.getOrder() != null && line.getOrder() != this) {
        throw new IllegalArgumentException(
            "OrderLine already belongs to another order"
        );
    }

    if (lines.contains(line)) {
        return;
    }

    lines.add(line);
    line.attachTo(this);
}
~~~

Các invariant có thể bao gồm:

- Không thêm dòng hàng vào đơn đã xác nhận hoặc đã thanh toán.
- Số lượng phải lớn hơn 0.
- Một dòng hàng chỉ thuộc một đơn hàng.
- Một đơn hàng phải có ít nhất một dòng hàng trước khi xác nhận.
- Không xóa dòng hàng sau khi hóa đơn đã phát hành.
- Tổng tiền được tính từ các dòng hàng hoặc được cập nhật theo một quy tắc nhất quán.

Nếu một thao tác cần thay đổi nhiều entity, hãy thực hiện trong transaction. Helper method bảo vệ object graph trong bộ nhớ; transaction bảo đảm các thay đổi được commit hoặc rollback cùng nhau.

### Tránh chuyển một orphan sang parent khác

Với `orphanRemoval = true`, việc gỡ entity con khỏi parent mang ý nghĩa xóa entity con khi flush. Không nên dùng `removeLine()` rồi ngay sau đó thêm cùng entity sang parent khác như một thao tác chuyển giao thông thường. Hibernate có thể đánh dấu entity để xóa, dẫn đến lỗi hoặc hành vi không như mong đợi.

Nếu nghiệp vụ thật sự cần chuyển dòng hàng giữa hai đơn, hãy xác định rõ quy tắc chuyển trạng thái và vòng đời. Có thể cần bỏ orphanRemoval, thiết kế thao tác chuyển giao riêng hoặc tạo entity mới theo quy tắc domain. Không tái sử dụng một helper xóa orphan cho mục đích reparent.

## 5. Cascade và orphanRemoval khác nhau thế nào?

Hai thuộc tính này thường được dùng cùng nhau nhưng có ý nghĩa khác nhau.

**Cascade** quyết định thao tác trên parent có được lan truyền sang child hay không.

- `PERSIST`: persist parent có thể persist child.
- `MERGE`: merge parent có thể merge child.
- `REMOVE`: remove parent có thể remove child.
- `REFRESH`, `DETACH`: lan truyền các thao tác tương ứng.

**orphanRemoval** quyết định entity con có bị xóa khi không còn được liên kết với parent hay không. Nó thường phù hợp với entity phụ thuộc, không tồn tại độc lập ngoài aggregate.

Với ví dụ PurchaseOrder/OrderLine:

- `cascade = ALL` cho phép persist, merge và remove các dòng hàng cùng đơn hàng.
- `orphanRemoval = true` làm cho việc gọi `order.removeLine(line)` xóa dòng hàng khỏi database khi flush.

Không nên dùng `CascadeType.REMOVE` hoặc orphanRemoval cho entity được nhiều parent dùng chung như Product, Category hoặc Role. Xóa một association không có nghĩa phải xóa entity dùng chung.

Nếu bỏ orphanRemoval và chỉ đặt `line.order = null`, cột `order_id` phải cho phép null. Với `optional = false` và `nullable = false`, thao tác đó không hợp lệ nếu child không bị xóa hoặc gán sang parent khác trước khi flush.

## 6. Quan hệ hai chiều trong Many-to-Many

Với many-to-many, một đối tượng có thể liên kết với nhiều đối tượng ở phía kia. Ví dụ Student và Course.

Nếu quan hệ chỉ là liên kết và không có thuộc tính riêng, có thể dùng `@ManyToMany`. Hai phía nên có helper method để cập nhật cả hai collection.

Ví dụ minh họa ở phía Student:

~~~java
@Entity
public class Student {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "student_courses",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();

    public void enroll(Course course) {
        Objects.requireNonNull(course, "course must not be null");
        if (courses.add(course)) {
            course.addStudentFromStudent(this);
        }
    }

    public void drop(Course course) {
        if (courses.remove(course)) {
            course.removeStudentFromStudent(this);
        }
    }
}
~~~

Phía Course có collection inverse:

~~~java
@Entity
public class Course {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();

    void addStudentFromStudent(Student student) {
        students.add(student);
    }

    void removeStudentFromStudent(Student student) {
        students.remove(student);
    }
}
~~~

Trong ví dụ, Student là owning side vì nó khai báo `@JoinTable`; Course là inverse side vì có `mappedBy = "courses"`. `enroll()` cập nhật cả hai collection. Phương thức nội bộ ở Course không gọi ngược lại `student.enroll()`, tránh đệ quy vô hạn.

Không nên dùng `CascadeType.REMOVE` cho nhiều quan hệ many-to-many thông thường. Course có thể được nhiều Student đăng ký; xóa một Student không được xóa Course. Khi bỏ liên kết, cần xóa dòng join table, không xóa entity còn được sử dụng.

Nếu quan hệ có thuộc tính như `enrolledAt`, `grade`, `status` hoặc `role`, hãy tạo entity trung gian như `Enrollment` với hai quan hệ many-to-one thay vì many-to-many thuần.

## 7. One-to-One và Many-to-One

Nguyên tắc đồng bộ hai phía cũng áp dụng cho các kiểu quan hệ khác.

### One-to-One

Một phía chứa `@JoinColumn` là owning side; phía còn lại dùng `mappedBy`. Helper method cần đặt cả hai tham chiếu và kiểm tra quy tắc thay thế liên kết cũ.

Nếu entity phụ thuộc hoàn toàn vào parent, có thể cân nhắc orphanRemoval. Nếu hai entity có vòng đời độc lập, không dùng orphanRemoval chỉ vì hiện tại chúng thường được tạo cùng lúc.

### Many-to-One

Quan hệ many-to-one thường chỉ cần phía con biết parent. Không nhất thiết phải tạo collection ngược ở parent nếu nghiệp vụ không cần truy cập ngược. Quan hệ một chiều thường đơn giản hơn và giảm khả năng vô tình tải một collection lớn.

Chỉ thêm inverse collection khi có nhu cầu truy vấn hoặc thao tác domain thực tế. Một quan hệ hai chiều không tự động tốt hơn quan hệ một chiều.

## 8. Cascade, dirty checking và transaction

Khi parent và child đang được quản lý trong cùng persistence context, thay đổi thuộc tính owning side sẽ được Hibernate phát hiện qua dirty checking và ghi xuống database khi flush.

Ví dụ:

~~~java
@Transactional
public Long createOrder() {
    PurchaseOrder order = new PurchaseOrder();
    order.addLine(new OrderLine("SKU-001", 2));
    order.addLine(new OrderLine("SKU-002", 1));

    PurchaseOrder saved = orderRepository.save(order);
    return saved.getId();
}
~~~

Do quan hệ dùng cascade PERSIST, khi persist đơn hàng mới, các dòng hàng cũng được persist. Không cần gọi repository.save() riêng cho từng dòng hàng.

Với parent đang managed, có thể chỉ cần gọi helper method trong transaction; JPA dirty checking sẽ ghi thay đổi. Nếu object detached, việc sửa object không tự động ghi database. Cần merge đúng aggregate hoặc nạp parent vào persistence context rồi áp dụng phương thức nghiệp vụ.

Đừng dựa vào việc gọi `save()` nhiều lần để sửa một object graph không nhất quán. Trước khi lưu, hãy bảo đảm owning side và inverse side đã được cập nhật đúng.

## 9. Truy vấn, fetch và hiệu năng

Đồng bộ hai phía không có nghĩa lúc nào cũng nên tải cả hai phía.

- `@ManyToOne` mặc định là EAGER theo Jakarta Persistence; nên cân nhắc chỉ định LAZY và tải theo use case.
- `@OneToMany` mặc định là LAZY.
- Truy cập collection trong vòng lặp có thể gây N+1 query.
- Tải hai collection cùng lúc bằng join fetch có thể nhân số dòng kết quả và tạo dữ liệu trùng ở SQL.

Khi cần đọc parent cùng child, có thể dùng `@EntityGraph` hoặc fetch join phù hợp với truy vấn. Không thay đổi fetch type toàn cục chỉ để sửa một màn hình cụ thể. Hãy thiết kế truy vấn theo use case và đo số query.

Nếu API trả entity trực tiếp, quan hệ hai chiều có thể tạo vòng lặp serialize: Order chứa Lines, mỗi Line lại chứa Order. Nên dùng DTO hoặc mapping riêng ở tầng API thay vì để serializer duyệt toàn bộ object graph. Annotation như `@JsonManagedReference` và `@JsonBackReference` có thể giải quyết một số trường hợp Jackson, nhưng DTO thường làm contract rõ ràng hơn.

## 10. Kiểm thử đồng bộ quan hệ

Một integration test nên xác nhận cả hai phía trong bộ nhớ và foreign key được lưu đúng.

Repository:

~~~java
package com.example.orders;

import java.util.Optional;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = "lines")
    Optional<PurchaseOrder> findWithLinesById(Long id);
}
~~~

Test:

~~~java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class PurchaseOrderRelationshipTest {

    @Autowired
    PurchaseOrderRepository orderRepository;

    @Autowired
    EntityManager entityManager;

    @Test
    void addLineSynchronizesBothSidesAndPersistsForeignKey() {
        PurchaseOrder order = new PurchaseOrder();
        OrderLine line = new OrderLine("SKU-001", 2);

        order.addLine(line);

        assertEquals(1, order.getLines().size());
        assertSame(order, line.getOrder());

        PurchaseOrder saved = orderRepository.saveAndFlush(order);
        Long orderId = saved.getId();

        entityManager.clear();

        PurchaseOrder loaded =
                orderRepository.findWithLinesById(orderId).orElseThrow();

        OrderLine loadedLine = loaded.getLines().get(0);

        assertEquals(1, loaded.getLines().size());
        assertSame(loaded, loadedLine.getOrder());
    }
}
~~~

Test dùng `@DataJpaTest` và giả định cấu hình test database cùng hai entity ở các phần trước. Sau khi flush và clear persistence context, test nạp lại aggregate để xác nhận quan hệ đã được ghi xuống database. Nếu chỉ kiểm tra hai tham chiếu trước khi save, test mới chứng minh object graph trong bộ nhớ chứ chưa chứng minh foreign key được lưu.

Có thể bổ sung test xóa orphan:

1. Tạo đơn hàng có một dòng hàng.
2. Persist và flush.
3. Gọi `order.removeLine(line)` trên parent managed.
4. Flush.
5. Kiểm tra dòng hàng không còn trong database.

Test này xác nhận orphanRemoval hoạt động theo cấu hình thực tế.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Collection có child nhưng foreign key không đổi | Chỉ sửa inverse side | Cập nhật owning side trong helper method |
| Foreign key đúng nhưng collection trong Java không có child | Chỉ sửa owning side | Cập nhật cả inverse collection |
| Child bị xóa ngoài dự kiến | orphanRemoval hoặc cascade REMOVE không phù hợp | Xác định vòng đời child và cấu hình cascade có chủ đích |
| Thêm child sang parent khác gây lỗi | Child đã thuộc parent cũ; orphanRemoval đánh dấu xóa | Không tái sử dụng thao tác remove để chuyển parent; thiết kế transfer riêng |
| JSON serialize lặp vô hạn | Quan hệ hai chiều tạo vòng tham chiếu | Trả DTO hoặc cấu hình serialization có chủ đích |
| N+1 query khi đọc parent và child | Truy cập lazy collection trong vòng lặp | Dùng EntityGraph/fetch join theo use case và đo query |
| Entity bị cập nhật quan hệ không nhất quán | Setter và collection public cho phép sửa tùy tiện | Đóng gói thay đổi trong phương thức nghiệp vụ |
| Test thấy object graph đúng nhưng DB sai | Chỉ assert trước flush hoặc không clear persistence context | Flush, clear và nạp lại entity để xác minh |

## Checklist trước khi merge

- [ ] Đã xác định owning side và inverse side từ mapping.
- [ ] `mappedBy` trỏ đúng tên thuộc tính Java ở owning side.
- [ ] Helper method cập nhật cả hai phía.
- [ ] Collection không bị sửa trực tiếp từ bên ngoài aggregate.
- [ ] Cascade và orphanRemoval phản ánh đúng vòng đời entity con.
- [ ] Không dùng orphanRemoval để chuyển child sang parent khác.
- [ ] Transaction bao trọn thay đổi aggregate.
- [ ] Fetch plan tránh N+1 và không tải collection không cần thiết.
- [ ] API không serialize vòng lặp entity hai chiều.
- [ ] Integration test flush, clear và nạp lại để xác minh foreign key.

## Kết luận

Trong quan hệ hai chiều JPA, owning side quyết định foreign key hoặc join table được ghi xuống database, còn helper method bảo đảm object graph trong bộ nhớ luôn nhất quán. Với one-to-many/many-to-one, phía many-to-one thường là owning side; collection phía one-to-many dùng mappedBy. Hãy đóng gói thêm/xóa quan hệ trong phương thức nghiệp vụ, chọn cascade và orphanRemoval theo vòng đời thực, và kiểm thử bằng cách flush rồi nạp lại entity. Điều đó giúp tránh trạng thái lệch giữa hai phía, lỗi foreign key và hành vi xóa ngoài ý muốn.
