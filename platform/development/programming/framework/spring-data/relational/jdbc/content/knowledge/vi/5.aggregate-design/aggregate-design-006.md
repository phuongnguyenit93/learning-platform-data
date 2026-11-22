# Thiết kế repository cho aggregate root thay vì cho mọi bảng

Trong ứng dụng dùng **Spring Data JDBC**, một bảng trong cơ sở dữ liệu không nhất thiết tương ứng với một repository. Repository nên đại diện cho một **aggregate root** — điểm truy cập chính vào một nhóm đối tượng cần được thay đổi nhất quán theo quy tắc nghiệp vụ. Đây là một quyết định kiến trúc quan trọng khi thiết kế aggregate trong Spring Data Relational JDBC.

Ví dụ, một đơn hàng có thể lưu vào hai bảng `purchase_orders` và `order_lines`. Nếu mỗi bảng có một repository độc lập rồi các service cập nhật từng bảng tùy ý, ứng dụng dễ bỏ qua các quy tắc như “không thể thêm hàng vào đơn đã gửi” hoặc “đơn được gửi phải có ít nhất một dòng hàng”. Mô hình phù hợp hơn là coi `PurchaseOrder` là aggregate root và thao tác qua `PurchaseOrderRepository`; `OrderLine` là thành phần thuộc vòng đời của đơn hàng.

Bài học trình bày cách nhận diện aggregate root, ánh xạ quan hệ sở hữu bằng Spring Data JDBC, thiết kế repository và service, xử lý đọc dữ liệu qua nhiều bảng, đồng thời làm rõ những trường hợp **nên** có repository riêng.

## 1. Repository trong Spring Data JDBC đại diện cho điều gì?

### 1.1. Bảng, entity, aggregate và repository là các khái niệm khác nhau

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **Table** | Lưu dữ liệu theo cấu trúc quan hệ | `purchase_orders`, `order_lines`, `customers` |
| **Entity** | Đối tượng có danh tính trong domain; có thể là root hoặc phần tử con | `PurchaseOrder`, `OrderLine` |
| **Value object** | Giá trị được xác định bởi thuộc tính, thường không có danh tính độc lập | `Money`, `Address` |
| **Aggregate** | Ranh giới sở hữu và bảo vệ tính nhất quán của một nhóm đối tượng | Đơn hàng cùng các dòng hàng của nó |
| **Aggregate root** | Entity được dùng làm điểm truy cập để thay đổi aggregate | `PurchaseOrder` |
| **Repository** | Giao diện lưu, đọc, xóa **aggregate root** | `PurchaseOrderRepository` |

**Một aggregate có thể trải trên nhiều bảng**, và **một database có thể chứa nhiều aggregate**. Bởi vậy, số lượng repository không nhất thiết bằng số lượng bảng.

Spring Data JDBC sử dụng Spring Data repository abstraction, nhưng khác JPA ở cách quản lý đồ thị đối tượng. Nó **không có persistence context, dirty checking hay lazy loading kiểu JPA**. Khi lưu một aggregate, Spring Data JDBC xem aggregate là đơn vị mà repository thao tác và thực hiện các câu SQL cần thiết theo mapping của các thành phần thuộc sở hữu root.

### 1.2. Repository được tổ chức quanh root

~~~mermaid
flowchart TB
    S["OrderApplicationService"] --> R["PurchaseOrderRepository"]
    R --> A["PurchaseOrder\naggregate root"]
    A --> L1["OrderLine #1"]
    A --> L2["OrderLine #2"]
    A -. "customerId" .-> C["Customer\naggregate root khác"]
    R --> P[("purchase_orders")]
    R --> Q[("order_lines")]
    CR["CustomerRepository"] --> C
    CR --> T[("customers")]
~~~

Trong sơ đồ:

- `PurchaseOrderRepository` là cổng ghi và tải đơn hàng, bao gồm những `OrderLine` thuộc aggregate.
- Không cần `OrderLineRepository` chỉ để thêm, sửa hoặc xóa từng dòng hàng thuộc đơn hàng.
- `Customer` có vòng đời và nghiệp vụ riêng nên có thể có `CustomerRepository` riêng.
- `customerId` là tham chiếu đến aggregate khác, không làm `Customer` trở thành entity con của `PurchaseOrder`.

Mục tiêu không phải giảm số lượng interface bằng mọi giá. Mục tiêu là **giữ đường đi của thay đổi dữ liệu phù hợp với ranh giới bảo vệ quy tắc nghiệp vụ**.

## 2. Vì sao thiết kế “mỗi bảng một repository” dễ gây lỗi?

Giả sử database có ba bảng:

~~~text
purchase_orders
├── id
├── customer_id
└── status

order_lines
├── id
├── order_id
├── product_id
└── quantity

customers
├── id
└── name
~~~

Một cách chia repository theo bảng là:

~~~java
interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {}

// Ví dụ cách chia không phù hợp khi OrderLine thuộc aggregate PurchaseOrder:
interface OrderLineRepository
        extends CrudRepository<OrderLine, Long> {}

interface CustomerRepository
        extends CrudRepository<Customer, Long> {}
~~~

*Đoạn trên minh họa một quyết định thiết kế cần xem xét, không phải các file hoàn chỉnh để sao chép vào dự án.*

Khi `OrderLine` có thể được cập nhật độc lập qua repository riêng, một service có thể vô tình:

1. Ghi thêm dòng hàng vào đơn đã ở trạng thái `SUBMITTED`, mặc dù nghiệp vụ không cho phép.
2. Xóa dòng hàng cuối cùng mà không kiểm tra quy tắc tối thiểu của đơn hàng.
3. Sửa số lượng qua một transaction không gắn với thao tác kiểm tra trạng thái đơn.
4. Cho phép nhiều chỗ trong hệ thống tự đặt ra logic lưu `OrderLine`, làm các quy tắc nghiệp vụ phân tán.

Database vẫn có thể bảo vệ khóa ngoại và `NOT NULL`, nhưng không phải mọi quy tắc nghiệp vụ đều biểu diễn được bằng các ràng buộc đó. Repository theo root giúp các thao tác thay đổi đi qua các phương thức domain như `addLine`, `changeQuantity`, `submit` và `cancel`.

Ngoài ra, với Spring Data JDBC, một entity con được ánh xạ qua `@MappedCollection` thường có cột khóa ngoại đến root do cơ chế mapping quản lý. Nếu chuyển entity con thành aggregate root riêng bằng một `CrudRepository` khác, bạn phải thiết kế lại mô hình ownership và cách ghi khóa ngoại; nó không chỉ là việc thêm một interface.

## 3. Cách xác định ranh giới aggregate trước khi viết code

Nên trả lời bốn nhóm câu hỏi sau **trước khi** tạo repository:

### 3.1. Đối tượng nào quyết định các bất biến nghiệp vụ?

*Bất biến (invariant)* là điều kiện phải luôn đúng sau một thay đổi nghiệp vụ hoàn tất.

Ví dụ với đơn hàng:

- Đơn ở trạng thái `SUBMITTED` không được thêm dòng hàng.
- Số lượng của mỗi dòng hàng phải dương.
- Đơn hàng phải có ít nhất một dòng hàng trước khi gửi.
- Dòng hàng thuộc về đúng một đơn hàng; không tự ý chuyển sang đơn khác.

`PurchaseOrder` là ứng viên root vì nó cần kiểm tra trạng thái và tập hợp dòng hàng trước khi chấp nhận thay đổi.

### 3.2. Đối tượng nào có vòng đời độc lập?

`OrderLine` thường sinh ra, thay đổi và biến mất cùng `PurchaseOrder`. Khi xóa đơn hàng, các dòng hàng thường được xử lý cùng đơn.

Ngược lại, một `Product` có thể được bán trong hàng nghìn đơn hàng và tiếp tục tồn tại khi một đơn bị xóa. Vì thế `Product` là một aggregate riêng, đơn hàng chỉ lưu `productId` và thông tin giá tại thời điểm giao dịch nếu nghiệp vụ yêu cầu.

### 3.3. Điều gì cần nhất quán trong cùng thao tác?

Nếu trạng thái của đơn và danh sách dòng hàng cần được kiểm tra và lưu nhất quán cùng nhau, hãy cân nhắc đặt chúng trong một aggregate. Nếu hai đối tượng có thể thay đổi độc lập và chỉ kết hợp khi đọc, thường nên tách chúng thành hai aggregate.

Không nên suy ra ranh giới aggregate chỉ từ foreign key, cấu trúc JOIN hoặc sơ đồ entity quan hệ. Foreign key biểu diễn liên kết và ràng buộc dữ liệu, **không tự động quyết định ownership trong domain**.

### 3.4. Aggregate có quá lớn không?

Một aggregate bao trùm mọi bảng liên quan có thể làm số lượng SQL khi tải và lưu tăng mạnh. Trong Spring Data JDBC, việc cập nhật aggregate có collection con có thể dẫn tới **xóa rồi chèn lại các hàng con** theo cơ chế lưu aggregate, thay vì theo dõi thay đổi từng object như JPA.

Vì vậy, ranh giới nên đủ lớn để bảo vệ bất biến, nhưng đủ gọn để một thao tác lưu không trở thành thay đổi hàng nghìn dòng không cần thiết.

| Đối tượng | Thuộc aggregate `PurchaseOrder`? | Lý do |
|---|---|---|
| `PurchaseOrder` | Có, chính là root | Kiểm soát trạng thái đơn và các quy tắc của đơn |
| `OrderLine` | Thường có | Là thành phần của đơn, không có vòng đời nghiệp vụ độc lập |
| `Customer` | Không | Hồ sơ khách hàng thay đổi độc lập |
| `Product` | Không | Sản phẩm tồn tại độc lập và được nhiều đơn tham chiếu |
| `Payment` | Tùy nghiệp vụ | Nếu thanh toán có vòng đời, retry, hoàn tiền và xử lý riêng, thường là aggregate khác |
| `Shipment` | Tùy nghiệp vụ | Nếu giao vận được quản lý độc lập, nên cân nhắc ranh giới riêng |

Hai dòng cuối là quyết định thiết kế phụ thuộc domain. Không có quy tắc cứng rằng tên `Payment` hoặc `Shipment` luôn nằm trong hay ngoài `PurchaseOrder`.

## 4. Thiết kế mẫu: PurchaseOrder và OrderLine

Phần thực hành sử dụng **Spring Boot, Spring Data JDBC và H2**. Mục tiêu là minh họa repository quản lý root trên hai bảng. Bạn có thể áp dụng cấu trúc tương tự với PostgreSQL hoặc MySQL bằng cách đổi driver và điều chỉnh DDL theo database.

### 4.1. Dependency cần thiết

Tạo dự án Java 17+ bằng Spring Initializr và chọn các dependency **Spring Data JDBC**, **H2 Database**. Trong Maven, phần khai báo phụ thuộc có dạng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Giữ phần parent và plugin do Spring Initializr tạo để Spring Boot quản lý các phiên bản phụ thuộc tương thích.

### 4.2. Schema cho hai bảng

Tạo `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
~~~

Các bảng sử dụng ID được H2 sinh tự động. Cột `order_id` trong `order_lines` là khóa ngoại cho quan hệ sở hữu. `customer_id` và `product_id` ở đây chỉ lưu định danh tham chiếu sang aggregate khác; để đơn giản, ví dụ chưa tạo hai bảng khách hàng và sản phẩm.

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:orderdb;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always

logging:
  level:
    org.springframework.jdbc.core: DEBUG
~~~

H2 trong bộ nhớ phù hợp với thực hành; dữ liệu không tồn tại sau khi tiến trình kết thúc. Với ứng dụng production, nên dùng database bền vững và quản lý schema bằng công cụ migration như Flyway hoặc Liquibase.

### 4.3. Enum trạng thái đơn

Tạo `src/main/java/com/example/orders/domain/OrderStatus.java`:

~~~java
package com.example.orders.domain;

public enum OrderStatus {
    DRAFT,
    SUBMITTED,
    CANCELLED
}
~~~

Với kiểu enum đơn giản, Spring Data JDBC có thể lưu tên enum vào cột `status` và chuyển từ cột chuỗi về enum khi đọc. Nếu database dùng mã trạng thái khác tên enum, cần cấu hình converter hoặc mapping phù hợp.

### 4.4. Entity con OrderLine

Tạo `src/main/java/com/example/orders/domain/OrderLine.java`:

~~~java
package com.example.orders.domain;

import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_lines")
public class OrderLine {

    @Id
    private Long id;

    private Long productId;
    private int quantity;
    private BigDecimal unitPrice;

    protected OrderLine() {
        // Dành cho cơ chế ánh xạ dữ liệu của Spring Data.
    }

    OrderLine(Long productId, int quantity, BigDecimal unitPrice) {
        if (productId == null) {
            throw new IllegalArgumentException("Thiếu productId");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Đơn giá không hợp lệ");
        }

        this.productId = productId;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public Long getId() {
        return id;
    }

    public Long getProductId() {
        return productId;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public BigDecimal subtotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

Chú ý: `OrderLine` **vẫn là một entity** và có `@Id` vì mỗi dòng hàng có danh tính trong database. Nhưng nó **không phải aggregate root** trong ví dụ này. Vì vậy, việc có `@Id` không có nghĩa phải tạo `OrderLineRepository`.

Trong class này không cần khai báo trường `orderId`. Quan hệ sở hữu sẽ được khai báo ở collection của root bằng `@MappedCollection(idColumn = "order_id")`; Spring Data JDBC chịu trách nhiệm ánh xạ cột khóa ngoại trong bảng con khi lưu và đọc aggregate.

Constructor tạo `OrderLine` có phạm vi package-private. Phương thức nghiệp vụ của root nằm cùng package `domain` có thể tạo dòng hàng, còn mã bên ngoài nên gọi API của root.

### 4.5. Aggregate root PurchaseOrder

Tạo `src/main/java/com/example/orders/domain/PurchaseOrder.java`:

~~~java
package com.example.orders.domain;

import java.math.BigDecimal;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private Long customerId;
    private OrderStatus status;

    @MappedCollection(idColumn = "order_id")
    private Set<OrderLine> lines = new LinkedHashSet<>();

    protected PurchaseOrder() {
        // Dành cho Spring Data JDBC.
    }

    private PurchaseOrder(Long customerId) {
        if (customerId == null) {
            throw new IllegalArgumentException("Thiếu customerId");
        }
        this.customerId = customerId;
        this.status = OrderStatus.DRAFT;
    }

    public static PurchaseOrder forCustomer(Long customerId) {
        return new PurchaseOrder(customerId);
    }

    public void addLine(Long productId, int quantity, BigDecimal unitPrice) {
        requireDraft();
        lines.add(new OrderLine(productId, quantity, unitPrice));
    }

    public void submit() {
        requireDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "Không thể gửi đơn hàng không có dòng hàng");
        }
        status = OrderStatus.SUBMITTED;
    }

    public void cancel() {
        if (status == OrderStatus.CANCELLED) {
            return;
        }
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Ví dụ này chỉ cho hủy đơn ở trạng thái DRAFT");
        }
        status = OrderStatus.CANCELLED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Chỉ có thể sửa đơn hàng ở trạng thái DRAFT");
        }
    }

    public Long getId() {
        return id;
    }

    public Long getCustomerId() {
        return customerId;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Set<OrderLine> getLines() {
        return Set.copyOf(lines);
    }

    public BigDecimal total() {
        return lines.stream()
            .map(OrderLine::subtotal)
            .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}
~~~

Ở đây, `PurchaseOrder` là root vì các thao tác thay đổi quan trọng phải đi qua nó:

- `forCustomer` tạo đơn ở trạng thái `DRAFT`.
- `addLine` kiểm tra trạng thái đơn và điều kiện của dòng hàng.
- `submit` ngăn gửi đơn rỗng và chuyển trạng thái.
- `cancel` định nghĩa quy tắc hủy của ví dụ.
- `getLines` trả tập hợp không sửa được từ bên ngoài, giúp tránh gọi `getLines().clear()` để bỏ qua các quy tắc của root.

Một hệ thống thực tế thường còn có `removeLine`, `changeQuantity`, giới hạn số dòng, kiểm tra tổng tiền và quy tắc chuyển trạng thái. Khi thêm các chức năng đó, hãy triển khai dưới dạng phương thức của root thay vì cho phép các service sửa collection trực tiếp.

**Giới hạn của ví dụ:** `Set<OrderLine>` được dùng để minh họa collection thuộc sở hữu. Nó không tự bảo đảm một `productId` chỉ xuất hiện một lần; nếu đó là bất biến nghiệp vụ, root phải kiểm tra hoặc hợp nhất các dòng hàng cùng sản phẩm. Nếu cần giữ thứ tự dòng hàng, cân nhắc `List` và ánh xạ cột vị trí phù hợp.

## 5. Chỉ tạo repository cho PurchaseOrder

Tạo `src/main/java/com/example/orders/repository/PurchaseOrderRepository.java`:

~~~java
package com.example.orders.repository;

import com.example.orders.domain.PurchaseOrder;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Spring Data JDBC tự tạo bean triển khai repository này. Từ `CrudRepository`, ứng dụng có thể sử dụng:

| Phương thức | Ý nghĩa trong ví dụ |
|---|---|
| `save(order)` | Lưu trạng thái `PurchaseOrder` và các `OrderLine` thuộc sở hữu |
| `findById(id)` | Tải một `PurchaseOrder` theo ID, với các thành phần được mapping thuộc aggregate |
| `findAll()` | Tải nhiều root; cần cân nhắc chi phí với aggregate lớn |
| `existsById(id)` | Kiểm tra một đơn có tồn tại |
| `count()` | Đếm các root đơn hàng |
| `deleteById(id)` | Xóa aggregate theo cơ chế của repository |

Việc repository trỏ vào `PurchaseOrder` thay vì `OrderLine` không có nghĩa database chỉ dùng bảng `purchase_orders`. Spring Data JDBC dựa vào `@MappedCollection` để biết còn những entity con phải xử lý qua bảng `order_lines`.

Nên thống nhất một cách nhìn:

~~~text
PurchaseOrderRepository
    save(PurchaseOrder)
        ├── ghi root vào purchase_orders
        └── ghi các OrderLine vào order_lines

    findById(orderId)
        ├── đọc root từ purchase_orders
        └── đọc các OrderLine thuộc root từ order_lines
~~~

Số lượng câu SQL cụ thể do mapping, phiên bản Spring Data JDBC và thao tác quyết định. Sơ đồ trên chỉ diễn tả ranh giới lưu/tải, không cam kết rằng mỗi nhánh luôn đúng một SQL statement.

### Không cần class triển khai repository

Interface kế thừa `CrudRepository` được Spring Data xử lý tự động thông qua cấu hình repository của Spring Boot. Trong cấu trúc package điển hình, class có `@SpringBootApplication` ở `com.example.orders` và các class con nằm trong `com.example.orders.domain`, `com.example.orders.repository`, `com.example.orders.service`.

Đảm bảo import annotation theo Spring Data:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;
import org.springframework.data.relational.core.mapping.MappedCollection;
~~~

Không thay chúng bằng `jakarta.persistence.Id`, `jakarta.persistence.Entity` hay `jakarta.persistence.OneToMany`; đó là mô hình JPA khác với Spring Data JDBC.

## 6. Để application service điều phối các thao tác qua root

Aggregate root giữ quy tắc nghiệp vụ; **application service** nhận yêu cầu, tải root và yêu cầu repository lưu trạng thái mới. Đây là nơi thích hợp để xác định ranh giới transaction của use case.

Tạo `src/main/java/com/example/orders/service/OrderApplicationService.java`:

~~~java
package com.example.orders.service;

import java.math.BigDecimal;
import java.util.List;
import java.util.NoSuchElementException;

import com.example.orders.domain.PurchaseOrder;
import com.example.orders.repository.PurchaseOrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;

    public OrderApplicationService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    public record NewLine(
            Long productId,
            int quantity,
            BigDecimal unitPrice
    ) {}

    @Transactional
    public Long createDraft(Long customerId, List<NewLine> items) {
        if (items == null) {
            throw new IllegalArgumentException("Thiếu danh sách dòng hàng");
        }

        PurchaseOrder order = PurchaseOrder.forCustomer(customerId);
        for (NewLine item : items) {
            order.addLine(item.productId(), item.quantity(), item.unitPrice());
        }

        PurchaseOrder saved = orders.save(order);
        return saved.getId();
    }

    @Transactional
    public void submit(Long orderId) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow(() ->
                new NoSuchElementException("Không tìm thấy đơn: " + orderId));

        order.submit();
        orders.save(order);
    }
}
~~~

Hai phương thức này chỉ phụ thuộc **một repository cho root**. Ngay cả khi `submit` phải xem các dòng hàng, nó kiểm tra collection đang thuộc aggregate sau khi tải root, thay vì truy vấn một `OrderLineRepository` riêng và tự ghép kết quả.

Thao tác `createDraft` nhận giá để đơn giản hóa ví dụ. Trong ứng dụng bán hàng thực tế, **không tin đơn giá do client cung cấp**: giá cần được lấy và xác minh từ nguồn nghiệp vụ đáng tin cậy, rồi lưu thành giá chốt của từng dòng hàng.

### Chạy một ví dụ ngắn

Tạo class `src/main/java/com/example/orders/OrdersApplication.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.util.List;

import com.example.orders.repository.PurchaseOrderRepository;
import com.example.orders.service.OrderApplicationService;
import com.example.orders.service.OrderApplicationService.NewLine;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            OrderApplicationService service,
            PurchaseOrderRepository repository) {
        return args -> {
            Long orderId = service.createDraft(
                101L,
                List.of(
                    new NewLine(501L, 2, new BigDecimal("120000.00")),
                    new NewLine(502L, 1, new BigDecimal("90000.00"))
                )
            );

            service.submit(orderId);
            var savedOrder = repository.findById(orderId).orElseThrow();

            System.out.println("Order ID: " + savedOrder.getId());
            System.out.println("Status: " + savedOrder.getStatus());
            System.out.println("Line count: " + savedOrder.getLines().size());
            System.out.println("Total: " + savedOrder.total());
        };
    }
}
~~~

Với Maven Wrapper trên Windows, chạy:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Trên macOS hoặc Linux:

~~~bash
./mvnw spring-boot:run
~~~

Kết quả nghiệp vụ dự kiến (ID có thể khác):

~~~text
Order ID: 1
Status: SUBMITTED
Line count: 2
Total: 330000.00
~~~

Khi `submit` chạy, phương thức `order.submit()` quyết định việc chuyển trạng thái có hợp lệ không. Repository chỉ chịu trách nhiệm **lưu aggregate đã được domain điều khiển**; nó không cần biết từng quy tắc trạng thái của đơn.

### Vai trò của `@Transactional`

`@Transactional` tại service giúp các thao tác đọc, kiểm tra và ghi trong cùng use case tham gia transaction phù hợp khi được gọi qua Spring proxy. Nếu một phương thức ném unchecked exception, mặc định Spring sẽ rollback transaction.

Tuy nhiên, transaction **không tự ngăn mọi xung đột đồng thời**. Hai request có thể đọc cùng trạng thái `DRAFT` rồi cùng cố cập nhật. Khi cần phát hiện thay đổi song song, bổ sung optimistic locking hoặc cơ chế đồng bộ hóa tương ứng với yêu cầu nghiệp vụ.

## 7. Khi nào một bảng khác phải có repository riêng?

Quy tắc phù hợp là: **mỗi aggregate root cần một đường truy cập dữ liệu rõ ràng; không tạo repository chỉ vì phát hiện một bảng mới**.

Ví dụ, `Customer` có thể được sửa tên, địa chỉ, trạng thái tài khoản mà không phụ thuộc vào một đơn hàng cụ thể. Khi đó, nó là root riêng:

~~~java
// Domain: ánh xạ vào bảng customers (minh họa).
@Table("customers")
class Customer {
    @Id Long id;
    String name;
}

// Repository cho một root độc lập.
interface CustomerRepository extends CrudRepository<Customer, Long> {
}
~~~

Các import của hai kiểu trên theo `org.springframework.data.annotation.Id`, `org.springframework.data.relational.core.mapping.Table` và `org.springframework.data.repository.CrudRepository`. Đoạn mã minh họa ý tưởng tách aggregate; nó không phải phần cần bổ sung để chạy ví dụ H2 ở trên.

Giữa `PurchaseOrder` và `Customer`, hãy lưu ID:

~~~java
private Long customerId;
~~~

Spring Data Relational cũng có thể biểu diễn tham chiếu này bằng kiểu `AggregateReference<Customer, Long>`. Dù chọn `Long` hay `AggregateReference`, ý nghĩa kiến trúc vẫn là: **đơn hàng chỉ giữ tham chiếu, không sở hữu toàn bộ Customer**.

### Ma trận quyết định repository

| Câu hỏi | Nếu câu trả lời là “Có” | Hàm ý thiết kế |
|---|---|---|
| Đối tượng có thể được tạo, thay đổi, xóa theo nghiệp vụ độc lập? | Ví dụ `Customer`, `Product` | Cân nhắc aggregate root và repository riêng |
| Đối tượng phải luôn được sửa qua một đối tượng cha? | Ví dụ `OrderLine` | Đặt trong aggregate của cha |
| Đối tượng có các bất biến cần cha kiểm tra? | Không thêm dòng sau khi gửi đơn | Cung cấp method trên root; tránh repository ghi độc lập cho con |
| Nhiều aggregate chỉ liên hệ bằng ID? | `PurchaseOrder.customerId` | Mỗi aggregate có repository riêng nếu có nhu cầu truy cập |
| Một màn hình cần dữ liệu ghép từ nhiều bảng? | Danh sách đơn kèm tổng tiền | Tạo read query/DAO/projection; không bắt buộc tạo repository cho mỗi bảng |
| Aggregate chứa quá nhiều bản ghi và cập nhật tốn kém? | Hàng nghìn lịch sử giao nhận | Xem lại ranh giới aggregate và read/write model |

Khi một entity trước đây là con bắt đầu có vòng đời độc lập, việc tách nó thành root **có thể hợp lý**. Nhưng đó là thay đổi về mô hình domain, transaction, khóa ngoại và cách đồng bộ trạng thái, không chỉ là thêm repository.

## 8. Không có repository cho mỗi bảng thì đọc dữ liệu JOIN thế nào?

Một câu hỏi thường gặp: màn hình cần danh sách đơn cùng tổng số tiền, trong khi một aggregate trải trên `purchase_orders` và `order_lines`. Có phải tạo `OrderLineRepository` mới truy vấn được bảng con?

**Không.** Ranh giới repository phục vụ thao tác domain không bắt buộc mọi truy vấn đọc đều đi qua object graph của root. Có thể dùng **Spring JDBC** song song với Spring Data JDBC để xây **read model** có SQL phù hợp màn hình.

Ví dụ một DAO chỉ đọc bảng:

~~~java
package com.example.orders.read;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReadDao {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderReadDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record OrderSummary(
            Long orderId,
            String status,
            long lineCount,
            BigDecimal totalAmount
    ) {}

    public List<OrderSummary> findSummaries() {
        String sql = """
            SELECT o.id AS order_id,
                   o.status AS status,
                   COUNT(l.id) AS line_count,
                   COALESCE(SUM(l.quantity * l.unit_price), 0)
                       AS total_amount
            FROM purchase_orders o
            LEFT JOIN order_lines l ON l.order_id = o.id
            GROUP BY o.id, o.status
            ORDER BY o.id
            """;

        return jdbc.query(sql, (rs, rowNum) ->
            new OrderSummary(
                rs.getLong("order_id"),
                rs.getString("status"),
                rs.getLong("line_count"),
                rs.getBigDecimal("total_amount")
            )
        );
    }
}
~~~

DAO này trả `OrderSummary`, không trả `PurchaseOrder` để ứng dụng chỉnh sửa. SQL đọc nhiều bảng thuận tiện cho thống kê và phân trang, trong khi thay đổi nghiệp vụ tiếp tục đi qua `PurchaseOrderRepository`. Đây là cách phân tách **write model** và **read model** ở mức đơn giản; không nhất thiết phải triển khai đầy đủ CQRS hoặc dùng hai database.

Với truy vấn lớn, còn cần phân trang, index ở `order_lines.order_id` và quan sát query plan. Repository không thay thế việc tối ưu SQL.

### Có dùng `@Query` trong repository được không?

Có. Spring Data JDBC hỗ trợ `@Query` cho SQL tùy chỉnh và các derived query phù hợp. Với một truy vấn đọc thuộc chính aggregate, bạn có thể đặt query trên repository của root. Khi kết quả là báo cáo JOIN phức tạp, trả DTO/projection qua DAO chuyên đọc thường giúp tránh nhầm lẫn nó là một aggregate có thể lưu ngược bằng `save`.

Điểm chính là: **không cần CRUD repository cho entity con chỉ để SELECT từ bảng con**.

## 9. Cách Spring Data JDBC lưu aggregate ảnh hưởng đến thiết kế

### 9.1. Không dùng cơ chế dirty checking của JPA

Với JPA, entity được quản lý trong persistence context có thể được theo dõi thay đổi và flush. Spring Data JDBC không cung cấp cơ chế đó.

~~~java
PurchaseOrder order = orders.findById(orderId).orElseThrow();
order.addLine(productId, 1, price);

// Đối tượng thay đổi trong bộ nhớ, nhưng chưa yêu cầu lưu xuống DB.
orders.save(order);
~~~

Sau khi gọi `save`, Spring Data JDBC xử lý root cùng các thành phần được mapping thuộc aggregate. Nếu quên `save`, việc sửa object trong Java không tự động ghi database chỉ vì service có `@Transactional`.

### 9.2. Collection con có thể được xóa/chèn lại khi update

Với aggregate có entity con, Spring Data JDBC có thể xóa các bản ghi con rồi chèn lại theo trạng thái collection khi cập nhật root. Hành vi này làm đơn giản hóa mô hình nhất quán nhưng có hệ quả:

- Thêm một dòng vào aggregate lớn có thể gây nhiều lệnh ghi hơn dự kiến.
- ID của các entity con hoặc các liên kết bên ngoài dựa vào ID đó có thể gặp vấn đề nếu mô hình phụ thuộc vào việc giữ nguyên hàng con.
- Audit, trigger và foreign key tham chiếu đến entity con phải được cân nhắc.
- Việc chọn aggregate quá lớn có thể ảnh hưởng đến hiệu năng và mức độ cạnh tranh transaction.

Nếu một dòng hàng cần được hệ thống khác tham chiếu trực tiếp bằng danh tính ổn định, hoặc được cập nhật độc lập với đơn, cần **xem lại ranh giới aggregate** thay vì cố điều khiển entity con như một root nhưng vẫn giữ mapping sở hữu cũ.

### 9.3. Phân biệt “gắn ID” và “dữ liệu tồn tại”

Mặc định, Spring Data JDBC dùng thông tin như `@Id` để nhận diện aggregate mới hay đã tồn tại. Với khóa `Long id`, giá trị `null` thường biểu thị đối tượng mới. Sau khi lưu, nên dùng giá trị từ:

~~~java
PurchaseOrder saved = orders.save(newOrder);
Long generatedId = saved.getId();
~~~

Đừng giả định gán một ID tùy ý rồi gọi `save` là phép *upsert* chắc chắn thành công. Với ID không tồn tại, thao tác cập nhật có thể thất bại tùy cơ chế lưu và ràng buộc database.

### 9.4. Bổ sung optimistic locking cho aggregate root

Nếu nghiệp vụ cần phát hiện hai request cùng sửa một đơn, có thể thêm `@Version` ở root:

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long version;
~~~

Đồng thời thêm cột tương ứng vào bảng `purchase_orders`:

~~~sql
ALTER TABLE purchase_orders ADD COLUMN version BIGINT;
~~~

Đây là **thay đổi tùy chọn** cho ví dụ: chỉ thêm annotation sau khi database có cột tương ứng. Spring Data JDBC sử dụng version để phát hiện cập nhật lạc hậu và có thể ném `OptimisticLockingFailureException` khi có xung đột. Ứng dụng cần quyết định báo lỗi xung đột, tải lại dữ liệu hay retry theo nghiệp vụ; không tự động retry vô hạn.

## 10. Transaction giữa nhiều aggregate

Ranh giới aggregate và ranh giới transaction liên quan nhưng không hoàn toàn trùng nhau.

Trong một aggregate, các thay đổi cần được lưu nhất quán cùng nhau. Khi service thực hiện nhiều thao tác ở **hai aggregate khác nhau** (ví dụ tạo đơn và giữ chỗ tồn kho), cần xác định tính nhất quán mong muốn:

- Nếu cả hai cùng ở một database và phải cùng thành công/thất bại, một transaction JDBC ở service có thể bao cả hai repository. Nhưng điều đó làm tăng phạm vi khóa và coupling.
- Nếu inventory có vòng đời độc lập, lượng truy cập cao hoặc nằm ở service/database khác, nên thiết kế cơ chế phối hợp thích hợp: sự kiện, outbox, idempotency, reservation hoặc saga khi thực sự cần.
- Không coi một aggregate là root của mọi đối tượng chỉ để dùng một transaction lớn.

Với Spring JDBC và Spring Data JDBC, transaction thông thường được Spring quản lý qua connection. Nên đặt `@Transactional` ở service được Spring gọi thông qua proxy. Cần lưu ý self-invocation, ngoại lệ rollback và isolation level khi nghiệp vụ có cạnh tranh cao.

Một aggregate root bảo vệ bất biến bên trong nó; tính đúng đắn giữa nhiều aggregate còn cần quy tắc phối hợp ở tầng application/domain phù hợp.

## 11. Các dấu hiệu thiết kế repository chưa phù hợp

| Dấu hiệu | Vấn đề có thể phát sinh | Hướng xử lý |
|---|---|---|
| Có `XRepository` cho mọi bảng, kể cả bảng chi tiết | Bỏ qua ranh giới ownership và bất biến | Xác định root; đưa các thao tác thay đổi chi tiết qua root |
| Service gọi `OrderLineRepository.save` trực tiếp khi đơn đã gửi | Logic kiểm tra trạng thái bị phân tán | Gọi phương thức nghiệp vụ trên `PurchaseOrder` |
| Tải mọi bảng liên quan thành một aggregate rất lớn | Truy vấn và cập nhật tốn kém; collection con bị xử lý lại | Thu gọn aggregate; dùng read model và tham chiếu bằng ID |
| Ánh xạ `Customer` như entity con của `PurchaseOrder` | Vô tình coi dữ liệu độc lập là phần sở hữu | Lưu `customerId` hoặc `AggregateReference` |
| Dùng phương thức `save` nhưng không gọi method bảo vệ invariant | Root trở thành DTO công khai để sửa tùy ý | Đặt invariant và hành vi ở root; hạn chế setter công khai |
| Dùng repository để lấy báo cáo JOIN nhiều bảng rồi sửa và lưu lại DTO | Lẫn read model với write aggregate | DAO/projection chỉ đọc; nghiệp vụ ghi qua repository root |
| Thấy `@Id` trên entity con rồi tạo repository mới | Đánh đồng danh tính database với root | Kiểm tra lifecycle và boundary trước khi tạo repository |
| Trông chờ `@Transactional` tự đồng bộ object đã đổi | Nhầm Spring Data JDBC với JPA dirty checking | Gọi `save` trên root sau thay đổi |
| Xung đột cập nhật gây mất thay đổi | Không có chiến lược concurrency | Cân nhắc `@Version`, transaction isolation và quy tắc retry |

### Khi nào repository cho entity con lại hợp lý?

Nếu theo nghiệp vụ, đối tượng từng được coi là “con” thực ra có **vòng đời và bất biến độc lập**, nó có thể trở thành aggregate root mới. Ví dụ, một `Shipment` được cập nhật trạng thái bởi hệ thống vận chuyển nhiều lần sau khi đơn được gửi có thể có `ShipmentRepository` riêng. Khi đó:

1. Xác định lại ownership và invariants của `Shipment`.
2. Bỏ mapping khiến `Shipment` được lưu như collection con của `PurchaseOrder`.
3. Tham chiếu giữa các aggregate bằng ID.
4. Xác định cách đồng bộ sự kiện/trạng thái liên quan đến đơn hàng.
5. Tạo `ShipmentRepository` cho aggregate mới.

Đó là một quyết định thiết kế có lý do nghiệp vụ cụ thể, khác với việc tạo repository cho bảng `shipments` chỉ vì bảng tồn tại.

## 12. Thực hành phân tích một domain khác

Giả sử hệ thống học trực tuyến có các bảng:

~~~text
courses
lessons
students
enrollments
lesson_progress
payments
~~~

Không nên lập tức tạo sáu repository. Hãy khảo sát:

**Course–Lesson:** nếu `Lesson` là thành phần được biên soạn và xuất bản qua `Course`, có thể coi `Course` là root và `Lesson` là entity con. Nếu lesson có vòng đời xuất bản, tái sử dụng và phân quyền độc lập, cân nhắc root khác.

**Student:** hồ sơ học viên là aggregate độc lập với khóa định danh riêng.

**Enrollment:** việc ghi danh có trạng thái, thời điểm và quy tắc nghiệp vụ riêng; thường đáng cân nhắc là aggregate root, tham chiếu `courseId` và `studentId`.

**LessonProgress:** nếu tiến độ học được cập nhật với tần suất cao, nên xem xét ranh giới riêng phù hợp với workload, thay vì gắn mọi bản ghi tiến độ vào một aggregate `Course` hoặc `Student` khổng lồ.

**Payment:** nếu có hoàn tiền, đối soát và nhận callback từ nhà cung cấp thanh toán, khả năng cao cần vòng đời độc lập và repository riêng.

Không có câu trả lời duy nhất chỉ dựa trên tên bảng. Kết quả phụ thuộc các bất biến nghiệp vụ, khối lượng dữ liệu, tần suất cập nhật và yêu cầu nhất quán.

### Bài tập tự triển khai

1. Thêm phương thức `removeLine(Long lineId)` cho `PurchaseOrder`, chỉ cho phép xóa khi `status == DRAFT`.
2. Không tạo `OrderLineRepository`. Mọi thao tác xóa dòng hàng phải đi qua service tải root, gọi `removeLine` rồi `save` root.
3. Thêm quy tắc: đơn chỉ được gửi khi tổng tiền lớn hơn 0; kiểm tra trong `submit`.
4. Quan sát SQL khi thay đổi một dòng hàng và lưu aggregate; so sánh với trường hợp chỉ thay đổi `status`.
5. Tạo DAO chỉ đọc trả số dòng hàng và tổng tiền theo từng đơn, không cho DAO cập nhật `order_lines`.
6. Thảo luận điều gì thay đổi khi `OrderLine` cần được đối tác vận chuyển tham chiếu bằng ID và cập nhật độc lập.

## 13. Nguyên tắc kết thúc

Trong **Spring Data Relational JDBC**, repository nên được thiết kế theo **aggregate root** vì root là nơi bảo vệ bất biến và quyết định vòng đời các entity con. Bảng là cấu trúc lưu trữ; repository là ranh giới truy cập dữ liệu ở mức domain. Một aggregate có thể ánh xạ xuống nhiều bảng, nhưng người dùng domain thao tác qua root.

Với ví dụ đơn hàng, `PurchaseOrderRepository` quản lý `PurchaseOrder` và `OrderLine` được ánh xạ bằng `@MappedCollection`; `Customer` và `Product` tồn tại độc lập, được tham chiếu bằng ID. Khi cần JOIN hay thống kê, một read DAO chuyên biệt có thể đọc nhiều bảng mà không cần phát sinh repository CRUD cho từng bảng.

**Câu hỏi thiết kế cần đặt trước khi tạo repository là:** *“Đối tượng nào chịu trách nhiệm bảo vệ quy tắc nghiệp vụ và được thay đổi như một đơn vị nhất quán?”* Câu trả lời dẫn đến aggregate root, và từ aggregate root mới suy ra repository.
