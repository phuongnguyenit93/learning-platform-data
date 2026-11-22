# Giữ mô hình miền độc lập với chi tiết ORM trong phạm vi hợp lý

**ORM (Object–Relational Mapping)** giúp ánh xạ đối tượng trong chương trình sang các bảng, cột và quan hệ trong cơ sở dữ liệu quan hệ. Công cụ như JPA/Hibernate có thể giảm lượng SQL thao tác thủ công, quản lý danh tính đối tượng và hỗ trợ transaction. Tuy nhiên, nếu để các đặc điểm của ORM quyết định toàn bộ mô hình nghiệp vụ, mã nguồn sẽ khó kiểm thử, khó thay đổi và đôi khi **sai cả ngữ nghĩa dữ liệu**.

Chẳng hạn, một đơn hàng được phép chuyển từ **DRAFT** sang **PLACED** chỉ khi có ít nhất một dòng hàng. Đây là **quy tắc miền (domain invariant)**, không phải quy tắc của Hibernate. Trái lại, **@Entity**, **fetch = LAZY**, **@JoinColumn**, **EntityManager** hay cách xử lý proxy là chi tiết lưu trữ. Phân biệt hai nhóm trách nhiệm này là nền tảng của **persistence ignorance**: mô hình nghiệp vụ không nhất thiết phải hiểu cơ chế persistence để diễn đạt và bảo vệ hành vi nghiệp vụ.

Bài thuộc chương **Ánh xạ đối tượng** của mô-đun **DATABASE_DATA_MODELING**. Mục tiêu là học cách xây dựng ranh giới giữa mô hình miền, mô hình quan hệ và ORM **một cách thực dụng**: tách nơi cần tách, chấp nhận phụ thuộc framework ở nơi hợp lý, và luôn kiểm chứng thiết kế bằng khóa, khóa ngoại, ràng buộc, phép nối, giao dịch và hành vi thực tế.

## 1. Độc lập với ORM thực sự nghĩa là gì?

Một mô hình miền có tính độc lập phù hợp khi:

1. **Tên và hành vi xuất phát từ nghiệp vụ**: Order, OrderLine, place(), cancel(), quantity, unitPriceAtOrder; không xuất phát từ cơ chế lazy proxy hay tên bảng.
2. **Bất biến nằm gần đối tượng sở hữu chúng**: không đặt đơn trống, không thêm số lượng âm, không sửa đơn đã chốt theo quy tắc ví dụ.
3. **Đơn vị kiểm thử miền không cần kết nối database**: có thể tạo đối tượng Java thuần và kiểm tra việc chuyển trạng thái.
4. **Mã nghiệp vụ không cần gọi EntityManager hoặc SQL**: việc truy xuất là trách nhiệm của lớp cổng lưu trữ (repository port), application service hoặc adapter.
5. **Lược đồ quan hệ vẫn được thiết kế nghiêm túc**: khóa, phụ thuộc hàm, lịch sử, ràng buộc tham chiếu, chỉ mục và transaction không bị xem là “chi tiết có thể mặc kệ”.

Điều này **không** có nghĩa mô hình miền được phép bỏ qua thực tế rằng thông tin phải lưu bền vững, rằng thao tác qua nhiều aggregate cần transaction, hoặc rằng việc đọc hàng nghìn dòng có chi phí. “Độc lập” là **giảm sự lan truyền của chi tiết triển khai**, không phải phủ nhận giới hạn dữ liệu và hiệu năng.

### 1.1. Phân loại trách nhiệm

| Trách nhiệm | Nơi phù hợp | Ví dụ |
| --- | --- | --- |
| Định nghĩa thực thể và quy tắc miền | Domain | Không đặt đơn trống; số lượng một dòng phải dương |
| Phối hợp một ca sử dụng | Application | Tải đơn, gọi **place()**, lưu kết quả, trả thông báo |
| Ranh giới transaction | Application/infrastructure | Một thao tác đặt đơn cần commit hoặc rollback đồng bộ |
| Ánh xạ đối tượng–hàng dữ liệu | Persistence adapter | Ánh xạ Order sang **orders** và OrderLine sang **order_lines** |
| Khóa, khóa ngoại, CHECK và chỉ mục | Database schema | **PRIMARY KEY (order_id, line_no)**; **CHECK (quantity > 0)** |
| Hình dạng dữ liệu trả cho API | Presentation/read model | DTO **OrderDetailsResponse**, không trả trực tiếp proxy ORM |

Quy tắc quan trọng có thể được bảo vệ **ở nhiều lớp**. Ví dụ, **quantity > 0** được kiểm tra khi tạo OrderLine để có thông báo lỗi nghiệp vụ rõ ràng, đồng thời được bảo vệ bằng **CHECK** trong database để chặn đường ghi khác. Đây là **phòng thủ nhiều lớp**, không phải dư thừa xấu cần loại bỏ.

## 2. Vì sao dùng thẳng ORM entity làm mô hình nghiệp vụ có thể gây vấn đề?

Một lớp JPA có thể dễ dàng phình to thành đối tượng mang tất cả trách nhiệm:

~~~java
@Entity
class OrderEntity {
    @Id
    private UUID id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;
}
~~~

Đoạn trên chỉ minh họa mapping, chưa định nghĩa các bất biến miền. Nếu application service thao tác bằng các setter công khai, một nơi có thể đặt **status = PLACED** khi **lines** rỗng, trong khi nơi khác gọi **lines.clear()** trên đơn đã đặt. Database có thể lưu được trạng thái không phù hợp với nghiệp vụ.

Các rủi ro thường gặp:

- **Anemic domain model**: entity chỉ chứa getter/setter; quy tắc bị phân tán trong service/controller.
- **ORM leak**: nghiệp vụ phải biết khi nào association được lazy load, session còn mở hay đã đóng.
- **N+1 query**: đi qua collection trong vòng lặp khiến một thao tác nghiệp vụ vô tình phát nhiều truy vấn.
- **Mapping convenience lấn át nghiệp vụ**: tạo quan hệ một-nhiều chỉ vì dễ ánh xạ, dù grain thực tế là quan hệ nhiều-nhiều có thuộc tính riêng.
- **Vòng đời ORM chi phối hành vi**: gắn toàn bộ logic vào callback như **@PrePersist** hoặc phụ thuộc dirty checking để điều kiện nghiệp vụ “tự nhiên” xảy ra.
- **Khó kiểm thử logic thuần**: muốn gọi một hành vi đơn giản phải khởi động Spring context, EntityManager hoặc database.

Tuy vậy, **không phải mọi entity JPA có hành vi đều sai**. Với ứng dụng CRUD đơn giản, mapping trực tiếp lên đối tượng nghiệp vụ có thể giảm lớp trung gian và vẫn giữ bất biến bằng phương thức miền thay vì setter tự do. Việc tách domain entity và persistence entity là một **quyết định chi phí–lợi ích**, không phải giáo điều.

## 3. Ranh giới điển hình: miền, ca sử dụng và adapter lưu trữ

Một cấu trúc có thể sử dụng theo hướng **Ports & Adapters**:

~~~mermaid
flowchart TD
    UI["HTTP API / CLI / Consumer"]
    APP["Application: PlaceOrder"]
    PORT["OrderRepository (port)"]
    DOM["Domain: Order, OrderLine, invariant"]
    ADAPTER["Persistence adapter: JpaOrderRepository"]
    ORM["JPA / Hibernate"]
    DB[("Relational Database")]
    UI --> APP
    APP --> DOM
    APP --> PORT
    ADAPTER -. "implements" .-> PORT
    ADAPTER --> ORM
    ORM --> DB
~~~

**Hướng phụ thuộc mã nguồn** nên rõ:

- Domain phụ thuộc thư viện Java và các khái niệm miền, **không** phụ thuộc JPA/Hibernate nếu chủ đích là domain thuần.
- Application phụ thuộc domain và **cổng lưu trữ** được định nghĩa bằng khái niệm nghiệp vụ.
- Persistence adapter phụ thuộc application/domain và framework ORM.
- Web/API map request/response sang command/DTO, không phụ thuộc vào trạng thái proxy của ORM.

Điều kiện “port” cần chú ý: một interface tên **OrderRepository** nhưng trả về **Page<OrderJpaEntity>**, nhận **Specification<JpaEntity>** hoặc **EntityManager** thực chất vẫn để chi tiết ORM đi vào mã gọi. Trên hệ thống thuần JPA, có thể chấp nhận API Spring Data ở phía adapter, nhưng không nên coi chúng là abstraction độc lập ORM.

## 4. Ví dụ xuyên suốt: đặt một đơn hàng

Quy tắc trong ví dụ:

1. Một đơn được định danh bằng **order_id** (UUID).
2. Dòng hàng được định danh bởi **(order_id, line_no)**; line_no chỉ duy nhất **trong đơn**.
3. Một đơn ở trạng thái **DRAFT** có thể chưa có dòng.
4. Chỉ được thêm dòng khi đơn đang **DRAFT**. Số lượng phải dương; đơn giá VND tại thời điểm đặt không âm.
5. Chỉ được **place()** khi đơn DRAFT đã có ít nhất một dòng; thao tác chuyển sang **PLACED**.
6. Một đơn PLACED không được tự ý thêm dòng qua ca sử dụng này.
7. Đơn giá của dòng là **ảnh chụp giao dịch**, không bị thay đổi ngược theo giá niêm yết hiện tại của sản phẩm.

Đây là một phiên bản **cố ý giới hạn**: chưa mô hình thuế, khuyến mại, huỷ, trả hàng, giao nhiều chuyến hoặc đặt hàng đồng thời từ nhiều luồng. Quy tắc trong phiên bản này không được suy rộng thành bất biến cho mọi hệ thống bán hàng.

### 4.1. Mô hình quan hệ — độc lập với việc có dùng ORM hay không

~~~sql
CREATE TABLE orders (
    order_id UUID PRIMARY KEY,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'PLACED')),
    version BIGINT NOT NULL DEFAULT 0
        CHECK (version >= 0)
);

CREATE TABLE order_lines (
    order_id UUID NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Ở đây:

- Một hàng **orders** là một đơn; một hàng **order_lines** là một dòng của đơn.
- **PRIMARY KEY (order_id, line_no)** bảo vệ định danh dòng; không dùng product_id thay line_no vì một sản phẩm có thể xuất hiện ở nhiều dòng.
- **version** dùng cho **optimistic locking**, **không phải** trường miền biểu diễn trạng thái nghiệp vụ.
- **CHECK** bảo vệ những điều kiện theo hàng, nhưng **không** tự bảo đảm “đơn PLACED có ít nhất một dòng” hoặc “không thêm dòng khi đơn đã PLACED”. Hai quy tắc này cần được bảo vệ trong đường ghi và transaction; nếu có luồng ghi khác, phải có cơ chế tương đương ở biên dữ liệu.

Lược đồ là hợp đồng về dữ liệu bền vững. ORM chỉ là một cách triển khai việc ghi/đọc hợp đồng đó.

### 4.2. Value object OrderLine dưới dạng Java thuần

~~~java
package example.domain;

import java.util.Objects;
import java.util.UUID;

public record OrderLine(
        int lineNo,
        UUID productId,
        int quantity,
        long unitPriceVnd
) {
    public OrderLine {
        if (lineNo <= 0) {
            throw new IllegalArgumentException("lineNo must be positive");
        }
        Objects.requireNonNull(productId, "productId");
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException("price cannot be negative");
        }
    }

    public long lineTotalVnd() {
        return Math.multiplyExact((long) quantity, unitPriceVnd);
    }
}
~~~

OrderLine trong ví dụ là **value object thuộc aggregate Order**: không có vòng đời độc lập khỏi đơn, còn **lineNo** chỉ định vị phần tử trong một đơn. Đối với ứng dụng khác, dòng đơn có thể là **entity con** với định danh bền vững và hành vi riêng. Phải chọn theo vòng đời nghiệp vụ, không chỉ theo việc JPA cần **@Id**.

Vì VND được biểu diễn bằng số nguyên trong ví dụ, **long** tránh sai số thập phân của **double**; **Math.multiplyExact** phát hiện tràn số. Với nhiều tiền tệ, số tiền lẻ, thuế hoặc làm tròn phức tạp, nên dùng **Money value object** với currency và chính sách precision/rounding rõ ràng thay vì suy từ kiểu Java.

### 4.3. Aggregate Order bảo vệ trạng thái

~~~java
package example.domain;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public final class Order {
    public enum Status { DRAFT, PLACED }

    private final UUID id;
    private final List<OrderLine> lines = new ArrayList<>();
    private Status status;

    public Order(UUID id) {
        this.id = Objects.requireNonNull(id);
        this.status = Status.DRAFT;
    }

    // Dùng khi phục hồi một aggregate từ dữ liệu lưu trữ.
    public static Order restore(
            UUID id, Status status, Collection<OrderLine> savedLines
    ) {
        Objects.requireNonNull(status);
        Objects.requireNonNull(savedLines);
        Order order = new Order(id);
        for (OrderLine line : savedLines) {
            if (order.lines.stream()
                    .anyMatch(x -> x.lineNo() == line.lineNo())) {
                throw new IllegalStateException("duplicate line number");
            }
            order.lines.add(Objects.requireNonNull(line));
        }
        if (status == Status.PLACED && order.lines.isEmpty()) {
            throw new IllegalStateException("placed order has no lines");
        }
        order.status = status;
        return order;
    }

    public UUID id() { return id; }
    public Status status() { return status; }
    public List<OrderLine> lines() { return List.copyOf(lines); }

    public void addLine(OrderLine line) {
        if (status != Status.DRAFT) {
            throw new IllegalStateException("order already placed");
        }
        Objects.requireNonNull(line);
        if (lines.stream().anyMatch(x -> x.lineNo() == line.lineNo())) {
            throw new IllegalArgumentException("duplicate line number");
        }
        lines.add(line);
    }

    public void place() {
        if (status != Status.DRAFT) {
            throw new IllegalStateException("order already placed");
        }
        if (lines.isEmpty()) {
            throw new IllegalStateException("cannot place empty order");
        }
        status = Status.PLACED;
    }
}
~~~

Trong lớp **Order** không có **@Entity**, **EntityManager**, **@Transactional** hoặc lời gọi SQL. Có thể tạo Order và gọi **addLine()/place()** trực tiếp trong một unit test. Những từ khóa như “đơn đã chốt”, “số dòng”, “dòng trùng số” đến từ nghiệp vụ; chúng không đổi khi chuyển từ JPA sang một adapter JDBC hoặc một hệ lưu trữ khác.

Hàm **restore(...)** tái tạo đối tượng từ dữ liệu và kiểm tra các bất biến **theo phiên bản miền đang được mô tả**. Trong hệ thống thực tế, cần chiến lược rõ ràng cho dữ liệu lịch sử không phù hợp với quy tắc mới, và tránh dùng hàm phục hồi để thực hiện những chuyển trạng thái cần kiểm tra theo luồng nghiệp vụ. Ví dụ này không cho phép chỉnh trực tiếp collection từ bên ngoài vì **lines()** trả bản sao bất biến.

## 5. Repository port: thao tác theo ngôn ngữ miền

Một cổng truy xuất đơn giản:

~~~java
package example.domain;

import java.util.Optional;
import java.util.UUID;

public interface OrderRepository {
    Optional<Order> findById(UUID id);
    void save(Order order);
}
~~~

Ứng dụng không cần biết Order được lưu trong hai bảng, dùng **@OneToMany**, hay được truy xuất bằng JDBC:

~~~java
package example.application;

import example.domain.Order;
import example.domain.OrderRepository;
import java.util.UUID;

public final class PlaceOrder {
    private final OrderRepository repository;

    public PlaceOrder(OrderRepository repository) {
        this.repository = repository;
    }

    public void execute(UUID orderId) {
        Order order = repository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException("order not found"));
        order.place();
        repository.save(order);
    }
}
~~~

**PlaceOrder** điều phối một ca sử dụng; **Order.place()** quyết định có được chốt đơn hay không. Nếu hệ thống cần kiểm tra tín dụng, tồn kho hoặc chính sách liên quan aggregate khác, application service có thể gọi những cổng dịch vụ tương ứng; không nên ép mọi thông tin nằm trong đối tượng Order chỉ để tránh gọi repository.

**Transaction boundary** phải bao trọn **tải → kiểm tra/đổi trạng thái → lưu**. Trong Spring, có thể đặt **@Transactional** ở application service hoặc ở một wrapper/infrastructure decorator gọi ca sử dụng. Dùng annotation framework ở application là **một sự đánh đổi thực dụng**; nếu yêu cầu cô lập nghiêm ngặt, đặt transaction ở decorator để lớp ca sử dụng vẫn là Java thuần. Một repository port tự nó **không tạo transaction**.

## 6. Persistence adapter: JPA phụ trách ánh xạ, không quyết định quy tắc đặt đơn

Khi tách miền và ORM, ta có hai mô hình với hai mục tiêu khác nhau:

- **Domain Order**: diễn đạt hành vi, trạng thái, giá trị và bất biến của đơn.
- **Persistence rows**: diễn đạt cách các hàng trong **orders** và **order_lines** được JPA định danh, nạp và cập nhật.

Việc có hai loại đối tượng chứa thông tin tương ứng là **chi phí tách lớp có chủ đích**. Mục tiêu không phải xóa mọi sự lặp cú pháp, mà là ngăn những điều kiện như *lazy proxy*, no-arg constructor và cascade trở thành yếu tố quyết định hành vi miền.

### 6.1. Một entity JPA chỉ cho hàng orders

Mã JPA minh họa theo hướng **Jakarta Persistence**:

~~~java
package example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.util.UUID;

@Entity
@Table(name = "orders")
public class OrderJpaRow {
    @Id
    @Column(name = "order_id", nullable = false)
    private UUID id;

    @Column(name = "status", nullable = false, length = 16)
    private String status;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected OrderJpaRow() {}  // JPA cần constructor không tham số.

    public OrderJpaRow(UUID id, String status) {
        this.id = id;
        this.status = status;
    }

    public UUID id() { return id; }
    public String status() { return status; }

    public void updateStatus(String newStatus) {
        this.status = newStatus;
    }
}
~~~

Trong ví dụ này, không có **@OneToMany** ở **OrderJpaRow**. Chọn cách nạp dòng bằng truy vấn rõ ràng để tránh buộc domain phải chứa một collection proxy. Đó là **một lựa chọn**, không phải nguyên tắc cấm **@OneToMany**: ORM relationship vẫn hữu ích khi vòng đời và fetch plan phù hợp.

**@Version** cho phép JPA phát hiện một số cập nhật đồng thời làm thay đổi hàng **orders**, dựa trên giá trị phiên bản mà ORM quản lý. Về mặt kỹ thuật, trường version ở đây thuộc **persistence row**; domain không phải expose setter **setVersion(...)** chỉ để phục vụ ORM.

### 6.2. Ánh xạ khóa ghép của dòng hàng

Trong SQL, khóa **order_lines** là **(order_id, line_no)**. Persistence adapter có thể ánh xạ khóa này bằng **@EmbeddedId**:

~~~java
package example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

@Embeddable
public class OrderLineKey implements Serializable {
    @Column(name = "order_id", nullable = false)
    private UUID orderId;

    @Column(name = "line_no", nullable = false)
    private int lineNo;

    protected OrderLineKey() {}

    public OrderLineKey(UUID orderId, int lineNo) {
        this.orderId = Objects.requireNonNull(orderId);
        this.lineNo = lineNo;
    }

    public UUID orderId() { return orderId; }
    public int lineNo() { return lineNo; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderLineKey that)) return false;
        return lineNo == that.lineNo &&
               Objects.equals(orderId, that.orderId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNo);
    }
}
~~~

~~~java
package example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "order_lines")
public class OrderLineJpaRow {
    @EmbeddedId
    private OrderLineKey id;

    @Column(name = "product_id", nullable = false)
    private UUID productId;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(name = "unit_price_vnd", nullable = false)
    private long unitPriceVnd;

    protected OrderLineJpaRow() {}

    public OrderLineJpaRow(
            OrderLineKey id, UUID productId,
            int quantity, long unitPriceVnd
    ) {
        this.id = id;
        this.productId = productId;
        this.quantity = quantity;
        this.unitPriceVnd = unitPriceVnd;
    }

    public OrderLineKey id() { return id; }
    public UUID productId() { return productId; }
    public int quantity() { return quantity; }
    public long unitPriceVnd() { return unitPriceVnd; }
}
~~~

Khóa ghép trong persistence là một **cách ánh xạ** cùng sự thật mà miền biết: lineNo chỉ duy nhất **trong một Order**. Domain OrderLine ở trên không phải mang **@EmbeddedId**, cũng không cần implement **Serializable** hay cung cấp constructor không tham số.

Nếu bảng chọn **line_id** thay thế làm khóa chính và đặt **UNIQUE(order_id, line_no)**, persistence adapter có thể ánh xạ khác. Nhưng vẫn cần bảo vệ quy tắc lineNo duy nhất trong mỗi đơn; thêm khóa thay thế không thay thế được ràng buộc nghiệp vụ.

### 6.3. Mapper khôi phục domain từ các hàng

Mapper là nơi chuyển đổi giữa hai thế giới:

~~~java
package example.persistence;

import example.domain.Order;
import example.domain.OrderLine;
import java.util.List;

public final class OrderMapper {
    public Order toDomain(
            OrderJpaRow header, List<OrderLineJpaRow> rows
    ) {
        List<OrderLine> lines = rows.stream()
                .map(row -> new OrderLine(
                        row.id().lineNo(),
                        row.productId(),
                        row.quantity(),
                        row.unitPriceVnd()
                ))
                .toList();

        return Order.restore(
                header.id(),
                Order.Status.valueOf(header.status()),
                lines
        );
    }
}
~~~

Mapper **không** tự quyết định khi nào cho phép gọi **place()**. Nó khôi phục dữ liệu và có thể báo lỗi nếu dữ liệu lưu trữ vi phạm bất biến, ví dụ một đơn PLACED nhưng không có dòng. Cần một chiến lược xử lý dữ liệu cũ/không hợp lệ trước khi thay đổi quy tắc miền; không nên âm thầm bỏ qua sai lệch.

### 6.4. Adapter truy vấn đầy đủ aggregate trước khi thực thi hành vi

Một phương thức đọc trong adapter JPA có thể thực hiện hai truy vấn rõ ràng:

~~~java
// Trích từ JpaOrderRepository, bên trong một transaction đang hoạt động.
public Optional<Order> findById(UUID id) {
    OrderJpaRow header = em.find(OrderJpaRow.class, id);
    if (header == null) {
        return Optional.empty();
    }

    List<OrderLineJpaRow> rows = em.createQuery(
            "select l from OrderLineJpaRow l " +
            "where l.id.orderId = :orderId " +
            "order by l.id.lineNo",
            OrderLineJpaRow.class
    ).setParameter("orderId", id).getResultList();

    return Optional.of(mapper.toDomain(header, rows));
}
~~~

Đây là **trích đoạn minh họa**: **em** là EntityManager do adapter quản lý, **mapper** là OrderMapper. Nó không phải file Java tự chạy độc lập.

Đối tượng Order trở về chứa dữ liệu Java thường, **không chứa proxy JPA**. Vì thế, khi ca sử dụng gọi **order.lines()** hoặc **order.place()**, hành vi không tự phát SQL. Trách nhiệm của repository là nạp đủ dữ liệu mà hành vi cần trước khi thoát khỏi ranh giới lưu trữ.

**Quan trọng:** khi ứng dụng thay đổi aggregate, phương thức **save(Order)** phải đồng bộ **toàn bộ trạng thái liên quan** (header và các dòng), không chỉ cập nhật status trong mọi trường hợp. Có thể triển khai bằng cách so sánh các dòng theo **(order_id, line_no)** và thêm/sửa/xóa những hàng thay đổi, hoặc một chiến lược cập nhật có kiểm soát khác. Không nên viết một phương thức tên **save** nhưng âm thầm bỏ qua thay đổi dòng hàng.

### 6.5. Đâu là phần ORM-specific?

| Trách nhiệm | Ví dụ chi tiết | Có nên đi vào domain? |
| --- | --- | --- |
| Trạng thái managed/detached của JPA | Persistence context, merge, flush | Không |
| Tạo đối tượng domain từ hàng | Mapper, kiểm tra dữ liệu phục hồi | Không nhất thiết; để tại adapter |
| Đặt đơn phải có dòng | **Order.place()** | **Có, là hành vi miền** |
| Dòng có số lượng dương | **OrderLine** và **CHECK** trong DB | **Có** trong miền, **cũng có** ở DB |
| Cách gắn child record với parent | @OneToMany, @MapsId, @EmbeddedId | Không |
| Tìm kiếm danh sách đơn phân trang | Query object, projection, index | Chủ yếu là application/read adapter |
| Sản phẩm có được thêm vào đơn không | Chính sách nghiệp vụ và dữ liệu liên quan | Domain/application, không giao cho ORM callback |

Việc tách hai mô hình giúp **giới hạn nơi phải sửa khi thay mapping**. Ví dụ, chuyển bảng order_lines sang khóa thay thế không buộc **OrderLine** trong domain nhận thêm trường **jpaLineId**, miễn là định danh nghiệp vụ lineNo không đổi.

## 7. Giao dịch, đồng thời và vòng đời persistence

Độc lập với ORM không có nghĩa những tình huống đồng thời được giải quyết tự động. Hai người dùng cùng đọc một đơn DRAFT và cùng thêm dòng có thể tạo **lost update** hoặc làm sai một bất biến nếu không có cơ chế kiểm soát giao dịch.

### 7.1. Đặt transaction ở ranh giới ca sử dụng

Ví dụ:

~~~text
HTTP POST /orders/{id}/place
    -> PlaceOrder.execute(id)
        -> repository.findById(id)
        -> order.place()
        -> repository.save(order)
    -> COMMIT
~~~

Cần **một transaction bao trùm** thao tác đọc–kiểm tra–ghi, có rollback khi xảy ra lỗi. Chỉ đặt transaction riêng cho **findById** và **save** có thể không bảo vệ được sự nhất quán giữa hai bước.

Trong Spring, một triển khai thực dụng có thể có wrapper:

~~~java
package example.infrastructure;

import example.application.PlaceOrder;
import java.util.UUID;
import org.springframework.transaction.annotation.Transactional;

public final class TransactionalPlaceOrder {
    private final PlaceOrder useCase;

    public TransactionalPlaceOrder(PlaceOrder useCase) {
        this.useCase = useCase;
    }

    @Transactional
    public void execute(UUID orderId) {
        useCase.execute(orderId);
    }
}
~~~

Trong ứng dụng thật, wrapper phải được quản lý như Spring bean và phương thức phải được gọi **qua proxy/interceptor transaction**, không tự gọi nội bộ làm bỏ qua cơ chế proxy. Đoạn trên minh họa vị trí trách nhiệm chứ không thay thế cấu hình Spring hoàn chỉnh.

Đây là một ví dụ về **độc lập ở mức source dependency**: lớp **PlaceOrder** không import Spring, trong khi lớp hạ tầng quyết định cách mở transaction. Với dự án nhỏ, đặt **@Transactional** ngay trên application service cũng có thể hợp lý nếu sự đơn giản mang lại giá trị lớn hơn mức cô lập framework.

### 7.2. Optimistic locking với @Version

Giả sử hai transaction T1 và T2 cùng tải đơn phiên bản **5**:

~~~text
T1 đọc Order(version=5, status=DRAFT)
T2 đọc Order(version=5, status=DRAFT)

T1 đặt đơn thành PLACED và commit -> version mới 6.
T2 cũng muốn cập nhật phiên bản đã đọc từ 5.
=> ORM phát hiện xung đột cập nhật phiên bản và từ chối một lượt ghi.
~~~

**@Version** trên **OrderJpaRow** là cơ chế persistence thường dùng để tránh *lost update* trên hàng root. Ứng dụng cần quyết định: báo lỗi cho người dùng, tải lại và thử lại **một cách an toàn**, hay yêu cầu thao tác lại. Không tự động retry mọi nghiệp vụ (đặc biệt thanh toán hay gọi dịch vụ bên ngoài) khi chưa thiết kế tính **idempotent**.

**Giới hạn quan trọng:** nếu chỉ thêm/xóa/sửa **order_lines** mà **không** thay đổi hàng **orders**, **@Version** trên hàng cha có thể **không** tăng tự động tùy chiến lược mapping và provider. Để bảo vệ bất biến trên **toàn aggregate**, adapter cần bảo đảm những thay đổi child cũng tham gia kiểm soát phiên bản root, ví dụ sử dụng khóa optimistic force-increment thích hợp hoặc cơ chế cập nhật phiên bản root có kiểm soát. Không được coi **@Version** trên cha là phép màu bảo vệ mọi hàng con.

### 7.3. Transaction không thay thế tất cả ràng buộc

Một ca sử dụng có thể gọi:

~~~java
order.addLine(new OrderLine(1, productId, 2, 300_000));
~~~

trong một transaction hợp lệ, nhưng nếu hai luồng khác nhau cùng ghi **line_no = 1**, ràng buộc **PRIMARY KEY (order_id, line_no)** tại DB vẫn là tuyến phòng thủ cuối. Logic miền chặn việc thêm hai dòng trùng **trong cùng một đối tượng đã nạp**, còn khóa DB chặn trùng **giữa những transaction cạnh tranh**.

Ngược lại, chỉ trông vào database để báo lỗi duplicate key cho người dùng không đem lại thông báo nghiệp vụ rõ ràng hoặc luồng xử lý tốt. Thiết kế nên có cả **thông điệp nghiệp vụ ở domain/application** và **bảo vệ cuối ở DB**.

### 7.4. Dirty checking và merge là kỹ thuật, không phải bất biến

Trong JPA, một đối tượng **managed** có thể được phát hiện thay đổi và ghi khi flush/commit. Một đối tượng **detached** không có cùng cơ chế. Việc **merge** một cây đối tượng từ request mà không kiểm soát dữ liệu thường gây rủi ro ghi đè trường, thêm/xóa child không mong muốn hoặc bỏ qua quyền sửa.

Phương án an toàn hơn thường là:

1. Tải aggregate theo định danh trong transaction.
2. Thực hiện **phương thức nghiệp vụ được phép** trên mô hình miền.
3. Adapter áp dụng **những thay đổi dự kiến** lên hàng được quản lý.
4. Flush và xử lý vi phạm version/constraint như lỗi nghiệp vụ hoặc xung đột theo thiết kế.

Không nên coi **entityManager.merge(requestBody)** là cách mặc định để triển khai một lệnh thay đổi nghiệp vụ.

## 8. Lazy loading, N+1 và cách đọc đúng theo ca sử dụng

Lỗi thường xuất hiện khi đưa JPA entity lên tầng API và sử dụng association ở bất kỳ nơi nào:

~~~java
// Ví dụ minh họa phản mẫu:
List<OrderJpaEntity> orders = jpaRepository.findAll();
for (OrderJpaEntity order : orders) {
    // Nếu lines LAZY, có thể kích hoạt truy vấn riêng từng đơn.
    System.out.println(order.getLines().size());
}
~~~

Nếu tải N đơn bằng một truy vấn và sau đó mỗi collection lines kích hoạt một truy vấn, tổng có thể thành **1 + N query**. Nếu đã đóng persistence context, thao tác đọc association còn có thể thất bại do lazy loading không khả dụng.

Đây là hệ quả của **kế hoạch truy xuất**, không phải yêu cầu nghiệp vụ “mỗi đơn có nhiều dòng”. Domain không nên sửa quy tắc bằng cách buộc mọi association thành **EAGER**.

### 8.1. Chọn chiến lược truy xuất theo mục đích

| Mục đích | Cách đọc phù hợp | Điều cần chú ý |
| --- | --- | --- |
| Chốt **một** đơn cần toàn bộ dòng | Tải root và các dòng trong transaction; join fetch hoặc truy vấn thứ hai | Bảo đảm aggregate đủ dữ liệu để kiểm tra bất biến |
| Liệt kê 100 đơn theo ngày | DTO/projection chỉ lấy id, ngày, trạng thái, tổng nếu có dữ liệu tổng hợp phù hợp | Không cần tạo 100 aggregate đầy đủ |
| Báo cáo số lượng sản phẩm đã bán | SQL tổng hợp hoặc read model riêng | Không tải toàn bộ object graph để cộng trong Java |
| Xem chi tiết một đơn | Truy vấn có fetch plan được xác định | Chú ý số truy vấn, phân trang và kết quả nhân hàng |
| Xử lý hàng loạt nhiều đơn | Batch fetch hoặc truy vấn theo nhóm khóa | Đo query count, memory và kích thước batch |

Ví dụ DTO truy vấn trực tiếp trên lược đồ:

~~~sql
SELECT
    o.order_id,
    o.status,
    COUNT(ol.line_no) AS line_count,
    COALESCE(
        SUM(ol.quantity::numeric * ol.unit_price_vnd),
        0
    ) AS order_value_vnd
FROM orders AS o
LEFT JOIN order_lines AS ol ON ol.order_id = o.order_id
GROUP BY o.order_id, o.status
ORDER BY o.order_id;
~~~

Đây là **read model** cho UI, không nhất thiết phải đi qua **Order.restore(...)**. Tách luồng đọc và ghi ở mức đơn giản có thể giúp mô hình miền tập trung vào hành vi và tránh sự phụ thuộc vào fetch plan.

### 8.2. Vì sao không nên trả JPA entity trực tiếp qua HTTP?

Trả một entity JPA từ controller có thể:

- Kích hoạt lazy loading trong quá trình serialize JSON.
- Gây vòng tham chiếu **Order → Lines → Order** khi có quan hệ hai chiều.
- Lộ cột kỹ thuật (version, internal ID) hoặc trường nội bộ ngoài ý muốn.
- Khiến thay đổi mapping persistence làm thay đổi API contract.
- Gây lỗi sau khi transaction kết thúc hoặc tăng số query khó quan sát.

Nên map sang **response DTO** với trường dữ liệu chủ đích. DTO không phải domain entity: nó được tối ưu cho một màn hình hoặc hợp đồng API và không nhất thiết mang các hành vi nghiệp vụ.

### 8.3. Aggregate boundary không đồng nghĩa fetch toàn bộ đồ thị

Nếu **Order** có nhiều dòng và mỗi dòng tham chiếu **Product**, điều đó không có nghĩa phải tải **mọi thuộc tính, tồn kho, nhà cung cấp, đánh giá** của Product khi đặt đơn. **ProductId** và các ảnh chụp cần cho quy tắc là đủ khi Product thuộc aggregate khác.

Một aggregate nên bảo vệ những bất biến có thể duy trì trong **một ranh giới nhất quán**. Không biến mọi quan hệ SQL thành quan hệ sở hữu object có cascade xuyên hàng loạt thực thể. Thiết kế aggregate và foreign key có liên quan nhưng **không hoàn toàn trùng nhau**.

## 9. Value object, danh tính và các quy tắc ORM cần cách ly

### 9.1. Value object không phải mọi thứ “không có bảng”

Một **MoneyVnd**, **EmailAddress** hoặc **AddressSnapshot** có thể là value object của miền. Chúng được so sánh theo **giá trị**, không theo danh tính hàng dữ liệu.

Ở mức lưu trữ:

- MoneyVnd có thể là một cột **BIGINT**.
- Một AddressSnapshot có thể trải thành nhiều cột **street, city, postal_code**.
- Một danh sách nhiều địa chỉ có vòng đời riêng có thể cần một bảng con hoặc aggregate khác.

JPA **@Embeddable** có thể ánh xạ một value object trực tiếp nếu chấp nhận annotation trong lớp giá trị; hoặc persistence row giữ các cột rời, mapper tạo value object Java thuần. Chọn theo nhu cầu tách biệt, tránh bắt domain value object thừa hưởng những yêu cầu constructor và mutability không cần thiết chỉ để phù hợp ORM.

### 9.2. Entity equality và hashCode

Trong domain, hai bản tham chiếu tới cùng **OrderId** thường được xem là cùng thực thể nghiệp vụ, dù các thuộc tính khác đã thay đổi theo thời gian.

Đối với JPA entity, **equals()/hashCode()** cần được thiết kế thận trọng:

- Đối tượng mới có ID do database sinh sau **persist** có thể thay đổi danh tính trong quá trình sống.
- Proxy của Hibernate có thể làm việc so sánh theo lớp runtime phức tạp hơn.
- Nếu đưa các collection mutable vào **hashCode()**, việc thay đổi dòng hàng khi entity đã nằm trong **HashSet** có thể phá cấu trúc tập.
- Những annotation tự động sinh equals/hashCode/toString cho mọi trường có thể đi qua association lazy, gây truy vấn hoặc vòng lặp.

Đừng áp một công thức equals/hashCode chung cho mọi entity. Hãy xác định danh tính thực sự, chiến lược cấp ID và vòng đời; nếu dùng khóa nghiệp vụ ổn định thì nêu rõ phạm vi và chính sách thay đổi của khóa đó.

### 9.3. ID và version có hai vai trò khác nhau

**UUID order_id** là danh tính của đơn và có ý nghĩa khi gọi ca sử dụng. **@Version** là cơ chế lưu trữ để phát hiện xung đột ghi; nó không phải số đơn hay một trạng thái nghiệp vụ.

Nếu ID do DB tạo khi insert, application cần xác định khi nào đơn đã có danh tính và cách xử lý sự kiện/phụ thuộc trước khi insert. Nếu ID được tạo ngay ở application (như UUID trong ví dụ), domain có thể có định danh trước khi ghi; cách này không loại bỏ yêu cầu unique tại DB.

### 9.4. Không để cascade và orphanRemoval thay thế định nghĩa vòng đời

Ví dụ **Order** sở hữu **OrderLine** theo nghiệp vụ; xóa một dòng DRAFT có thể được phép, nhưng xóa mọi dòng của đơn đã PLACED có thể bị cấm.

**cascade = ALL** hoặc **orphanRemoval = true** quyết định ORM sẽ làm gì với các hàng khi collection thay đổi, **không quyết định hành vi ấy có được nghiệp vụ cho phép**. Khi cần lịch sử hóa đơn, việc cascade xóa cứng có thể còn bị cấm vì kiểm toán. Phải đặc tả vòng đời trước, rồi mới chọn cascade và quy tắc **ON DELETE** thích hợp.

### 9.5. Không nhét logic quan trọng vào callback ORM một cách vô hình

**@PrePersist**, **@PreUpdate** và các callback có thể phù hợp để điền vài trường kỹ thuật, nhưng không nên là nơi duy nhất thực thi những quy tắc lớn như:

- Đặt đơn chỉ khi có dòng.
- Chốt giá theo một chính sách khuyến mại.
- Giữ tổng xuất không vượt lượng đặt.
- Phát sự kiện thanh toán sau khi commit.

Callback không luôn có ngữ cảnh nghiệp vụ cần thiết; hành vi có thể khó dự đoán khi flush, thay đổi nhiều entity hoặc chạy dưới các đường ghi không qua ORM. Những quy tắc này nên xuất hiện ở mô hình miền/ca sử dụng và cơ chế dữ liệu tương ứng, với transaction rõ ràng.

## 10. Khi nào tách domain entity và JPA entity, khi nào nên chấp nhận gộp?

“Trong phạm vi hợp lý” nghĩa là dùng **mức tách lớp tương ứng độ phức tạp và rủi ro thay đổi**, không cố theo một khẩu hiệu tuyệt đối.

### 10.1. Ba phương án thực tế

| Phương án | Đặc điểm | Phù hợp khi | Chi phí/rủi ro |
| --- | --- | --- | --- |
| **A. Một lớp domain kiêm JPA entity** | Lớp có **@Entity**, mapping và các phương thức miền | CRUD nhỏ, ít quy tắc, một hệ lưu trữ ổn định, tốc độ phát triển quan trọng | Domain phụ thuộc JPA, dễ bị proxy/mutability chi phối nếu không kiểm soát |
| **B. Domain thuần + persistence entity + mapper** | Hai mô hình tách rời; adapter chuyển đổi hai chiều | Nghiệp vụ phức tạp, nhiều trạng thái, aggregate rõ, cần unit test thuần, mô hình lưu trữ dự kiến thay đổi | Tốn mapper, đồng bộ trạng thái, xử lý version và identity phức tạp hơn |
| **C. Lai theo ngữ cảnh** | Aggregate quan trọng tách thuần; bảng CRUD/quản trị dùng JPA trực tiếp; read model dùng projection | Hệ thống lớn, độ phức tạp phân bố không đồng đều | Cần nguyên tắc đặt tên và ranh giới để không gây nhầm lẫn |

**Phương án C** thường là cách thực dụng: chẳng hạn quy trình **đặt hàng, thanh toán, phân bổ tồn kho** có nhiều bất biến nên đầu tư mô hình miền rõ; còn bảng **country_codes**, **system_settings** hoặc màn hình quản trị ít hành vi có thể dùng JPA entity/DTO trực tiếp mà không cần tạo ba lớp đối tượng giống nhau.

### 10.2. Tín hiệu nên tách

Nên nghiêng về domain thuần khi:

- Một aggregate có nhiều hành vi: **place, cancel, reserve, settle, refund** với quy tắc chuyển trạng thái.
- Nhiều ca sử dụng cần tái dùng đúng cùng bất biến.
- Domain phải chạy trong unit test mà không khởi động ORM/database.
- Persistence gồm nhiều bảng, mô hình lịch sử, version hoặc mapping phức tạp, trong khi ngôn ngữ miền tương đối ổn định.
- Dữ liệu phải đọc từ nhiều nguồn hoặc cần hỗ trợ cách ghi khác, ví dụ SQL và event-sourcing/read model riêng.
- Việc thay cấu trúc lưu trữ không nên buộc sửa các phương thức nghiệp vụ.

Nên cân nhắc **không tách** nếu bảng chỉ có hành vi CRUD đơn giản, các object gần như giống nhau và mapper chỉ sao chép trường mà không tạo được ranh giới có giá trị.

### 10.3. Nếu dùng JPA entity trực tiếp, vẫn bảo vệ ranh giới miền

Không bắt buộc phải tạo class thứ hai để có hành vi tốt. Dù lớp kiêm JPA entity, vẫn nên:

- Giới hạn setter công khai; dùng **place()**, **addLine(...)**, **changePrice(...)** thay vì cho mọi service sửa trạng thái tùy ý.
- Đặt invariant có thể kiểm tra trong đối tượng gần dữ liệu mà nó sở hữu.
- Không để controller nhận/trả trực tiếp entity được quản lý; dùng request/response DTO.
- Xác định transaction ở application service.
- Chỉ dùng lazy association bên trong phạm vi dữ liệu đã nạp có chủ đích.
- Không đưa **EntityManager** vào code tính toán thuần.
- Bảo vệ khóa/unique/check/foreign key trong schema dù domain đã kiểm tra.

Đây là **độc lập về khái niệm và hành vi**, dù chưa hoàn toàn độc lập về kiểu/import. Với hệ nhỏ, đạt mức này có thể mang lại giá trị tốt hơn một kiến trúc nhiều tầng dư thừa.

### 10.4. Một câu hỏi quyết định hữu ích

> Nếu ngày mai đổi cách lưu **order_lines** từ quan hệ @OneToMany sang truy vấn riêng bằng JDBC, những phương thức **Order.place()** và **Order.addLine()** có phải đổi không?

- Nếu **không**, ranh giới miền đã được giữ khá tốt.
- Nếu **có** vì logic nghiệp vụ đang gọi **getHibernateLazyInitializer()**, **entityManager.flush()**, hoặc giả định collection phải managed, chi tiết ORM đã xâm nhập miền.

Không cần hứa trước rằng sẽ thay Hibernate bằng công nghệ khác. Giá trị thực tế của ranh giới là **giảm chi phí thay đổi và tăng khả năng kiểm thử ngay trong hiện tại**.

## 11. Kiểm thử ba lớp: miền, persistence và ca sử dụng

Tách trách nhiệm chỉ hữu ích khi kiểm thử chứng minh mỗi lớp thực hiện đúng phần của mình.

### 11.1. Unit test miền không cần Spring hoặc DB

Ví dụ theo JUnit 5:

~~~java
package example.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderTest {
    @Test
    void cannotPlaceEmptyOrder() {
        Order order = new Order(UUID.randomUUID());
        assertThrows(IllegalStateException.class, order::place);
    }

    @Test
    void canPlaceDraftWithLineButCannotChangeAfterPlace() {
        Order order = new Order(UUID.randomUUID());
        OrderLine line = new OrderLine(
                1, UUID.randomUUID(), 2, 300_000
        );
        order.addLine(line);
        order.place();

        assertEquals(Order.Status.PLACED, order.status());
        assertThrows(
                IllegalStateException.class,
                () -> order.addLine(
                        new OrderLine(2, UUID.randomUUID(), 1, 100_000)
                )
        );
    }

    @Test
    void cannotDuplicateLineNumber() {
        Order order = new Order(UUID.randomUUID());
        order.addLine(new OrderLine(1, UUID.randomUUID(), 1, 10_000));

        assertThrows(
                IllegalArgumentException.class,
                () -> order.addLine(
                        new OrderLine(1, UUID.randomUUID(), 1, 20_000)
                )
        );
    }
}
~~~

Các phép kiểm tra trên không cần Hibernate, SQL, container database hay Spring context. Nếu chỉ đổi tên bảng, chiến lược fetch, index hoặc ORM provider, những test này **không nên phải sửa**.

### 11.2. Integration test persistence cần database thực

Unit test thuần **không chứng minh** mapping hoặc ràng buộc DB đúng. Với persistence adapter, cần integration test kiểm tra:

1. Tạo Order DRAFT, thêm dòng và lưu; đọc lại phải khôi phục đúng id, trạng thái, số dòng, đơn giá.
2. Lưu/đọc các dòng có khóa **(order_id, line_no)**; hai dòng cùng lineNo trong một đơn phải bị từ chối.
3. **CHECK(quantity > 0)** phải từ chối dữ liệu âm kể cả một đường ghi bỏ qua domain.
4. Thay đổi Order thành PLACED phải được flush/commit và đọc lại đúng.
5. Hai transaction cạnh tranh cập nhật cùng order root phải kích hoạt chiến lược **optimistic locking** như thiết kế.
6. Thêm/xóa dòng phải được persistence adapter đồng bộ chính xác; nếu invariant phụ thuộc toàn aggregate, phiên bản root phải bảo vệ thay đổi child.
7. Đo số lượng SQL khi tải nhiều đơn và kiểm tra các truy vấn projection, tránh N+1.

Nên kiểm thử trên **đúng hệ quản trị mục tiêu** hoặc một môi trường tương đương. Một database in-memory khác engine có thể xử lý kiểu UUID, SQL dialect, khóa ngoại, locking và transaction khác PostgreSQL. Công cụ chạy database phục vụ integration test là lựa chọn triển khai; **bản thân nội dung bài không cần khẳng định đã chạy test**.

### 11.3. Kiểm thử ca sử dụng và transaction

Với **PlaceOrder**, có thể dùng fake repository để xác nhận orchestration:

- Repository không tìm thấy đơn → báo lỗi phù hợp, không lưu.
- Đơn DRAFT không có dòng → domain từ chối, không thực hiện commit.
- Đơn có dòng → gọi place rồi lưu trạng thái PLACED.

Riêng kiểm thử rollback, xung đột phiên bản và nhiều luồng ghi phải dùng transaction/persistence thật. Fake repository **không** mô phỏng đầy đủ isolation, dirty checking hay khóa tại database.

### 11.4. Contract test ở biên API

Đảm bảo API:

- Không trả trực tiếp JPA proxy hay trường version ngoài ý muốn.
- Trả lỗi nghiệp vụ có ý nghĩa khi đặt đơn trống hoặc đặt lại đơn đã chốt.
- Không chấp nhận payload tự ý sửa thuộc tính nội bộ do API cho phép **mass assignment**.
- Phản ánh trạng thái đã commit; không báo thành công trước khi transaction ghi thành công.

## 12. Phát sự kiện miền và tích hợp hệ thống khác

Một đơn được **PLACED** có thể cần gửi thông báo, đặt giữ hàng hoặc phát thông điệp cho hệ thống vận chuyển. Không nên viết:

~~~java
// Phản mẫu: thực hiện tác động bên ngoài ngay trong logic Order.place().
emailClient.sendOrderPlaced(...);
~~~

nếu mục tiêu là domain thuần và khả năng kiểm thử độc lập. Thay vào đó:

- Domain biểu đạt sự kiện **OrderPlaced(orderId)** như kết quả hành vi, hoặc ghi nhận sự kiện trong aggregate theo một giao thức rõ ràng.
- Application phối hợp commit và gửi thông điệp theo chính sách tích hợp.
- Persistence adapter ghi dữ liệu và có thể ghi **outbox event trong cùng transaction** nếu hệ thống cần tránh trường hợp database commit nhưng thông điệp bị mất.
- Một worker/publisher sau đó phát sự kiện từ outbox; consumer cần xử lý idempotency và việc thông điệp được gửi/lặp lại theo cơ chế của hệ thống.

**Lưu ý:** chỉ gọi message broker sau **order.place()** nhưng trước khi commit không bảo đảm toàn vẹn phân tán; nếu commit thất bại, bên ngoài có thể đã nhận sự kiện về một đơn chưa tồn tại ở trạng thái mong đợi. **Transactional outbox** là một giải pháp thường được cân nhắc, không phải hệ quả tự động của việc dùng ORM hay domain event.

## 13. Lược đồ dữ liệu vẫn là một mô hình độc lập cần được đánh giá

Không nên để ORM tự sinh DDL rồi mặc định đó là mô hình dữ liệu phù hợp. Một lược đồ đúng phải trả lời:

- **Grain của bảng:** mỗi hàng biểu diễn một thực thể, dòng, sự kiện hay ảnh chụp thời gian nào?
- **Khóa ứng viên:** id kỹ thuật có thay thế mất ràng buộc nghiệp vụ không?
- **Phụ thuộc hàm:** có đang sao chép cùng tên hiện hành hoặc cùng sự thật vào nhiều bảng?
- **Lịch sử:** giá đã chốt, địa chỉ giao và thay đổi trạng thái cần được giữ thế nào?
- **Quan hệ và vòng đời:** một-nhiều, nhiều-nhiều, cascade, soft delete, archived data?
- **Tính nhất quán:** những bất biến theo nhiều hàng cần transaction hoặc constraint nào?
- **Hiệu năng:** chỉ mục, query shape, phân trang, thống kê, số SQL sinh ra?

Với bảng **order_lines** trong ví dụ, **product_id** hiện chỉ là UUID vì ví dụ chưa tạo bảng danh mục sản phẩm. Khi hệ thống có bảng **products(product_id)** là nguồn chuẩn, nên xem xét **FOREIGN KEY (product_id) REFERENCES products(product_id)**; nếu sản phẩm có thể được xóa hoặc ngừng bán sau khi đặt đơn, cần xác định chính sách tham chiếu và lưu ảnh chụp lịch sử phù hợp. Đừng dùng thiếu quan hệ JPA như lý do bỏ qua toàn vẹn dữ liệu.

**Schema migration** cần được quản lý bằng phiên bản và quy trình triển khai (ví dụ công cụ migration SQL phù hợp). Tự đồng bộ schema từ annotation lúc ứng dụng khởi động có thể tiện trong giai đoạn phát triển, nhưng môi trường production cần kiểm soát thay đổi dữ liệu, thứ tự deploy và khả năng rollback theo đặc thù dự án.

Một nguyên tắc tốt: **miền định nghĩa hành vi; lược đồ định nghĩa sự thật bền vững và những ràng buộc có thể thực thi; ORM kết nối hai phía**. Không phía nào được thay thế toàn bộ công việc của phía kia.

## 14. Bài tập thực hành

### Bài 1 — Phân loại mã miền và mã hạ tầng

Cho các trách nhiệm:

1. **Không** cho chuyển đơn DRAFT thành PLACED nếu không có dòng.
2. Tải danh sách dòng hàng bằng câu JPQL có tham số orderId.
3. Kiểm tra quantity phải lớn hơn 0 khi khởi tạo dòng.
4. Chọn **@EmbeddedId** hay **@IdClass** để ánh xạ khóa dòng.
5. Chuyển Order sang DTO trả về giao diện.
6. Tăng version khi child của aggregate thay đổi để ngăn ghi đè đồng thời.
7. Tính tổng tiền đã chốt từ số lượng và đơn giá của dòng.
8. Tạo chỉ mục cho truy vấn tìm dòng theo productId.

**Yêu cầu:** xác định nơi sở hữu trách nhiệm: domain, application/API, persistence adapter hay database schema. Nếu một quy tắc cần nhiều lớp cùng bảo vệ, hãy giải thích.

<details>
<summary>Gợi ý lời giải bài 1</summary>

| Số | Nơi sở hữu chính | Ghi chú |
| --- | --- | --- |
| 1 | **Domain** | Order.place() bảo vệ trạng thái |
| 2 | **Persistence adapter** | JPQL là chi tiết truy vấn |
| 3 | **Domain + database** | Constructor OrderLine và CHECK trong SQL cùng bảo vệ |
| 4 | **Persistence adapter** | Khác biệt mapping không phải hành vi đơn hàng |
| 5 | **API/application** | DTO thuộc hợp đồng giao tiếp, không phải aggregate |
| 6 | **Persistence adapter / transaction** | Version root phải bảo vệ toàn aggregate khi cần |
| 7 | **Domain** hoặc query projection theo mục đích | Domain tính khi là quy tắc hành vi; báo cáo đọc có thể dùng SQL |
| 8 | **Database schema** | Index phụ thuộc workload và kế hoạch truy vấn |

</details>

### Bài 2 — Tìm dấu hiệu ORM đã xâm nhập miền

Xét đoạn mã minh họa:

~~~java
public void placeOrder(OrderJpaEntity order) {
    Hibernate.initialize(order.getLines());
    if (order.getLines().size() == 0) {
        throw new IllegalStateException("empty order");
    }
    order.setStatus("PLACED");
    entityManager.flush();
}
~~~

**Yêu cầu:**

1. Chỉ ra ít nhất ba dấu hiệu nghiệp vụ đang phụ thuộc ORM.
2. Viết lại luồng ở mức trách nhiệm, không bắt buộc viết toàn bộ Java.
3. Nếu hệ thống rất nhỏ và vẫn dùng JPA entity trực tiếp, đề xuất cách cải thiện ít tốn công hơn việc tách hai cây đối tượng hoàn chỉnh.

<details>
<summary>Gợi ý lời giải bài 2</summary>

- **OrderJpaEntity** đi thẳng vào use case; **Hibernate.initialize(...)** là thao tác hạ tầng; **setStatus("PLACED")** bỏ qua phương thức kiểm soát bất biến; **entityManager.flush()** làm ca sử dụng biết cơ chế ghi và vòng đời ORM.
- Luồng thay thế: application nhận **orderId** → repository nạp **Order** đầy đủ → **order.place()** bảo vệ bất biến → repository lưu thay đổi → transaction commit.
- Với dự án nhỏ, có thể giữ JPA entity nhưng thêm **place()** vào entity, giới hạn setter trạng thái và bảo đảm fetch plan/transaction ở service; như vậy vẫn kiểm soát hành vi và tránh gọi Hibernate utility trong nghiệp vụ dù chưa tách domain/persistence thành hai lớp.

</details>

### Bài 3 — Khóa dòng, snapshot giá và aggregate boundary

Hệ thống bán hàng đưa ra ba quy tắc:

- Một sản phẩm có thể xuất hiện hai lần trên một đơn với hai mức giá đã chốt khác nhau.
- Sản phẩm hiện hành có thể đổi tên và giá.
- Đơn đã đặt phải giữ giá đã chốt theo từng dòng; việc chỉnh sửa danh mục sản phẩm không được sửa hóa đơn cũ.

**Yêu cầu:**

1. Vì sao **(order_id, product_id)** không nhất thiết là khóa ứng viên?
2. Nên lưu **unit_price_vnd_at_order** ở Product hay OrderLine?
3. Domain Order có cần kéo toàn bộ đối tượng Product vào mỗi dòng không?
4. Nếu dùng JPA, điều gì xảy ra khi ánh xạ **OrderLine.unitPrice** thành giá trị đọc trực tiếp từ **Product.currentPrice** mỗi lần truy vấn?

<details>
<summary>Gợi ý lời giải bài 3</summary>

Khóa phù hợp theo quy tắc là **(order_id, line_no)**; cùng productId xuất hiện nhiều lần không làm trùng khóa. **unit_price_vnd_at_order** là một sự thật lịch sử của dòng, nên thuộc **OrderLine**, không suy lại từ giá niêm yết hiện hành. Domain chỉ cần **ProductId** và ảnh chụp giá, trừ khi một hành vi cụ thể thực sự cần thêm thông tin được xác nhận của Product.

Nếu tính lại giá dòng từ **Product.currentPrice**, hóa đơn lịch sử có thể đổi khi danh mục thay giá. Đây là **lỗi ngữ nghĩa thời gian**, không thể sửa chỉ bằng **FetchType.EAGER** hoặc đổi annotation ORM.

</details>

### Bài 4 — Quyết định mức tách lớp

Có hai phân hệ:

**Phân hệ A:** danh mục mã quốc gia và tên hiển thị, chỉ thêm/sửa/xóa qua trang quản trị, không có quy tắc nghiệp vụ đáng kể.

**Phân hệ B:** giao dịch đặt hàng có đặt chỗ tồn kho, hết hạn giữ hàng, giao nhiều đợt, hoàn tiền và nhiều người dùng thao tác đồng thời.

**Yêu cầu:** đề xuất A/B/C trong bảng quyết định ở mục 10 cho mỗi phân hệ, giải thích lợi ích và chi phí; nêu ba integration test quan trọng đối với B.

**Hướng giải:** A thường có thể dùng **JPA entity + DTO** trực tiếp, không cần thêm một lớp domain chỉ sao chép trường. B phù hợp với **domain aggregate độc lập**, repository port và persistence adapter; các bất biến, giao dịch và đồng thời cần được làm rõ. Các kiểm thử quan trọng: chặn chuyển trạng thái sai, bảo vệ khóa/version khi hai transaction ghi đồng thời, bảo vệ dữ liệu lịch sử và tính toàn vẹn khi phân bổ tồn kho hoặc giao hàng.

### Bài 5 — Phi chuẩn hóa có chủ đích không làm thay đổi nghĩa miền

Để tăng tốc màn hình danh sách, nhóm thêm **order_summary_read_model(order_id, status, line_count, total_vnd)** được cập nhật từ dữ liệu gốc.

**Câu hỏi:** bảng mới có cần trở thành một aggregate độc lập chứa hành vi **place()** không? Nếu cập nhật read model chậm một vài giây, API nên diễn đạt điều đó thế nào? Những dữ liệu nào vẫn là nguồn sự thật?

**Gợi ý:** read model là projection nhằm tối ưu đọc; nó không trở thành nơi quyết định đặt đơn. **Order** và dữ liệu giao dịch/nguồn chuẩn vẫn bảo vệ bất biến. Nếu read model cập nhật bất đồng bộ, giao diện cần hiểu độ trễ và không dùng dữ liệu có thể cũ để thực hiện quyết định ghi nhạy cảm mà không xác nhận lại nguồn chuẩn.

## 15. Checklist thiết kế thực dụng

| Câu hỏi trước khi chốt giải pháp | Dấu hiệu đáng tin cậy |
| --- | --- |
| Miền có định nghĩa được hành vi **không cần ORM** không? | Có phương thức như **place()**, **addLine()** với bất biến rõ |
| Repository port có diễn đạt nghiệp vụ không? | Dùng Order, OrderId, command/query có nghĩa, không expose EntityManager |
| Có đang tạo hai mô hình chỉ để sao chép trường không? | Chi phí mapper được cân nhắc với nhu cầu kiểm thử và thay đổi thực tế |
| ORM mapping có phản ánh đúng grain không? | Order, OrderLine, khóa ghép và các FK đúng quy tắc |
| Giá trị lịch sử có bị tính lại từ danh mục hiện hành không? | Snapshot thuộc giao dịch, không phụ thuộc Product.currentPrice |
| Một ca sử dụng ghi có transaction đủ rộng không? | Đọc/kiểm tra/ghi nằm trong ranh giới nhất quán |
| Version có bảo vệ thay đổi child không? | Đã thử xung đột ghi trên toàn aggregate, không chỉ hàng root |
| Association có kích hoạt N+1 hoặc lazy exception không? | Có fetch plan và kiểm thử số truy vấn |
| API có trả JPA entity/proxy ra ngoài không? | Có DTO/projection định nghĩa rõ |
| Quy tắc miền có bảo vệ ở DB khi thích hợp không? | Có PK, FK, UNIQUE, CHECK, transaction và ràng buộc nâng cao nếu cần |
| Có unit test thuần và integration test ORM không? | Tách rõ kiểm thử hành vi khỏi kiểm thử mapping/transaction |
| Lược đồ có được version hóa không? | Có migration, kế hoạch nâng cấp và cách đối soát dữ liệu |

## 16. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Domain không có annotation thì chắc chắn độc lập ORM.” | Nếu phương thức miền vẫn cần session mở, proxy hoặc EntityManager, sự phụ thuộc **vẫn tồn tại trong hành vi**. |
| “Mọi lớp @Entity đều là thiết kế xấu.” | Với CRUD đơn giản, JPA entity có hành vi được kiểm soát có thể là giải pháp hợp lý. |
| “Tách domain và JPA entity sẽ không còn vấn đề persistence.” | Mapper, transaction, version, locking, fetch plan và schema vẫn cần thiết kế. |
| “@OneToMany nghĩa là aggregate của miền.” | Quan hệ SQL/ORM không tự quyết định vòng đời và ranh giới bất biến của aggregate. |
| “@Version trên root bảo vệ mọi child.” | Phải xác minh cách root version thay đổi khi collection/child được ghi. |
| “LAZY luôn tốt hơn EAGER” hoặc ngược lại. | Fetch strategy phải dựa trên từng ca sử dụng và được đo bằng query count. |
| “Có transaction là không thể xảy ra ghi đè.” | Isolation, optimistic/pessimistic locking và ràng buộc DB vẫn cần xét. |
| “Mapper dư thừa nên phải xóa.” | Mapper có giá trị nếu nó cách ly sự biến động của persistence khỏi hành vi miền. |
| “Chuẩn hóa SQL và mô hình object nên có cùng cấu trúc.” | Aggregate object và các bảng chuẩn hóa phục vụ mục tiêu khác nhau; mapping nối hai phía. |
| “ORM tạo schema thì schema mặc nhiên đúng.” | Thiết kế dữ liệu vẫn cần grain, khóa, FD, FK, lịch sử, migration và kiểm chứng. |

## 17. Ghi nhớ

**Giữ mô hình miền độc lập với ORM trong phạm vi hợp lý** nghĩa là đặt **thuật ngữ, hành vi và bất biến nghiệp vụ** ở nơi chúng thuộc về, còn những chi tiết như **@Entity**, **@EmbeddedId**, fetch plan, proxy, **EntityManager**, dirty checking và transaction implementation được giới hạn tại các ranh giới kỹ thuật phù hợp.

Khi nghiệp vụ phức tạp, cách làm **domain thuần → repository port → JPA adapter → database** giúp thay đổi ánh xạ và kiểm thử quy tắc mà ít ảnh hưởng lẫn nhau. Khi nghiệp vụ chỉ là CRUD, **gộp JPA entity và domain behavior** có thể giảm chi phí thiết kế nếu vẫn giữ setter có kiểm soát, DTO, transaction rõ ràng và cơ sở dữ liệu có ràng buộc.

Độc lập framework **không** được đánh đổi lấy sự mơ hồ về dữ liệu: Order và OrderLine phải có grain/khóa rõ, giá dòng là ảnh chụp giao dịch, aggregate cần bảo vệ đồng thời, và việc đọc cần kế hoạch truy vấn. Hãy đánh giá thành công bằng **mức dễ hiểu, khả năng kiểm thử, chi phí thay đổi, hiệu năng và tính đúng đắn của dữ liệu**, không bằng số lượng lớp Java hay sự vắng mặt tuyệt đối của annotation.
