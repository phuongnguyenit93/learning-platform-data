# Ngăn lặp vô hạn khi biểu diễn đồ thị hai hướng trong quan hệ một-nhiều JPA

## 1. Vấn đề: đồ thị đối tượng có chu kỳ, còn JSON thường là cây

Trong JPA, một quan hệ **một-nhiều hai hướng** (*bidirectional one-to-many*) cho phép entity cha giữ danh sách entity con và mỗi entity con tham chiếu ngược lại entity cha. Ví dụ, một đơn hàng có nhiều dòng hàng; mỗi dòng hàng biết nó thuộc đơn hàng nào:

~~~text
PurchaseOrder
  ├── id = 100
  └── lines = [OrderLine #1, OrderLine #2]
                  │             │
                  └── order ─────┴──> PurchaseOrder #100
~~~

Đồ thị này **có chu kỳ tham chiếu hợp lệ** trong Java. Tuy nhiên, khi mã chương trình cố gắng biểu diễn toàn bộ đối tượng bằng cách đi theo mọi thuộc tính, nó có thể lặp:

~~~text
order
  -> order.lines[0]
  -> order.lines[0].order
  -> order.lines[0].order.lines[0]
  -> order.lines[0].order.lines[0].order
  -> ...
~~~

Hiện tượng này dễ xảy ra khi:

- Trả trực tiếp entity JPA từ REST API và để Jackson chuyển thành JSON.
- Tự viết phương thức chuyển entity thành Map, XML hoặc JSON bằng đệ quy.
- Sinh **toString()** tự động trên cả hai phía quan hệ, sau đó ghi log hoặc debug.
- Sinh **equals() / hashCode()** tự động dựa trên toàn bộ thuộc tính, khiến thao tác so sánh đi qua quan hệ hai chiều.
- Công cụ hiển thị, ghi log hoặc lập sơ đồ cố duyệt toàn bộ đồ thị mà không theo dõi đối tượng đã thăm.

Biểu hiện có thể là **StackOverflowError**, ngoại lệ serialization, lỗi độ sâu lồng nhau hoặc việc truy vấn tải quá nhiều dữ liệu. Thông báo chính xác phụ thuộc Jackson, provider, module và cách duyệt đối tượng.

> **Bản thân quan hệ JPA hai hướng không phải lỗi.** Lỗi phát sinh khi thuật toán biểu diễn cố mở rộng mọi liên kết của một **đồ thị có chu kỳ** thành một cấu trúc lồng nhau vô hạn. Cần xác định rõ dữ liệu đầu ra và điểm dừng khi duyệt.

## 2. Quan hệ hai hướng trong JPA được ánh xạ như thế nào?

Một quan hệ phổ biến gồm:

- **@OneToMany(mappedBy = "order")** ở phía cha: danh sách các dòng hàng.
- **@ManyToOne** ở phía con: tham chiếu về đơn hàng, thường là phía sở hữu khóa ngoại.
- **@JoinColumn(name = "order_id")** ở phía con: cột khóa ngoại thực tế trong bảng dòng hàng.

Sơ đồ ở tầng cơ sở dữ liệu:

~~~text
purchase_orders                     purchase_order_lines
----------------                   --------------------
id (PK)          <---------------- order_id (FK)
order_number                       id (PK)
                                   sku
                                   quantity
~~~

Quan hệ trong database thường là **một khóa ngoại từ bảng con tới bảng cha**. JPA có thể cung cấp tham chiếu ở cả hai phía để mã Java điều hướng thuận tiện, nhưng điều đó không đòi hỏi hai cột khóa ngoại vật lý. **mappedBy** chỉ ra rằng tập hợp ở phía cha phản ánh quan hệ do trường **order** bên con sở hữu.

### 2.1. Entity PurchaseOrder

~~~java
package com.example.orders;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
        // Constructor dành cho JPA
    }

    public PurchaseOrder(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(OrderLine line) {
        if (line == null) {
            throw new IllegalArgumentException("line must not be null");
        }
        if (line.getOrder() != null && line.getOrder() != this) {
            throw new IllegalStateException("line belongs to another order");
        }
        if (!lines.contains(line)) {
            lines.add(line);
        }
        line.attachToOrder(this);
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.attachToOrder(null);
        }
    }
}
~~~

### 2.2. Entity OrderLine

~~~java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_order_lines")
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    protected OrderLine() {}

    public OrderLine(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
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

    void attachToOrder(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

Ví dụ cố ý dùng tên bảng **purchase_orders** thay vì bảng có tên **order**, vì ORDER là từ khóa có ý nghĩa trong SQL. Cấu hình sinh ID, dependencies, cách khởi tạo persistence unit và transaction được giả định đã có trong ứng dụng.

**CascadeType.ALL** và **orphanRemoval = true** chỉ là lựa chọn phù hợp khi dòng hàng thuộc vòng đời của đơn hàng, không phải yêu cầu của quan hệ hai hướng. Nếu một entity con có thể thuộc nhiều aggregate hoặc sống độc lập, cần điều chỉnh cascade và orphan removal theo nghiệp vụ.

### 2.3. Hai phía cần đồng bộ trong bộ nhớ

Sau khi tạo:

~~~java
PurchaseOrder order = new PurchaseOrder("PO-2026-001");
OrderLine line = new OrderLine("SKU-100", 2);

order.addLine(line);

System.out.println(order.getLines().contains(line)); // true
System.out.println(line.getOrder() == order);          // true
~~~

Phương thức **addLine()** thay đổi cả tập hợp **order.lines** và tham chiếu **line.order**. Việc làm này giữ mô hình đối tượng nhất quán trong bộ nhớ và phù hợp với việc trường **OrderLine.order** là phía sở hữu khóa ngoại.

Nếu chỉ gọi **order.getLines().add(line)** trong một thiết kế cho phép sửa danh sách trực tiếp mà không đặt **line.order**, khóa ngoại có thể không được thiết lập như ý muốn. Ngược lại, nếu chỉ đặt **line.order** mà không cập nhật tập hợp cha, mô hình Java trong bộ nhớ có thể không phản ánh đúng quan hệ cho đến khi được tải lại.

Điểm quan trọng: **giữ nhất quán hai phía quan hệ** và **ngăn đệ quy khi biểu diễn dữ liệu** là hai vấn đề khác nhau. Không nên xóa tham chiếu ngược trong entity chỉ để che lỗi JSON nếu nghiệp vụ thực sự cần điều hướng hai hướng.

## 3. Lặp vô hạn xuất hiện khi nào?

### 3.1. Trả trực tiếp entity từ REST controller

Trong Spring Web, một controller có thể được viết như sau:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderRepository repository;

    public OrderController(OrderRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    public PurchaseOrder getOrder(@PathVariable Long id) {
        return repository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order not found"
            ));
    }
}
~~~

Đoạn mã giả định **OrderRepository** là repository JPA phù hợp, các class Spring đã được import và Jackson được dùng làm JSON serializer. Nếu JSON serializer cố biểu diễn toàn bộ đối tượng từ các getter, kết quả lý tưởng mà nó tưởng phải tạo sẽ có cấu trúc đệ quy:

~~~json
{
  "id": 100,
  "orderNumber": "PO-2026-001",
  "lines": [
    {
      "id": 900,
      "sku": "SKU-100",
      "quantity": 2,
      "order": {
        "id": 100,
        "orderNumber": "PO-2026-001",
        "lines": [
          {
            "id": 900,
            "order": "tiếp tục quay lại cha và con..."
          }
        ]
      }
    }
  ]
}
~~~

Đây là **minh họa đường duyệt**, không phải một JSON thực sự được tạo đầy đủ. Nếu không có cơ chế dừng, serializer tiếp tục đi từ child về parent rồi từ parent về child. Jackson có thể báo lỗi nesting depth, direct self-reference hoặc một lỗi serialization khác tùy phiên bản và cấu hình; một số cách duyệt tự viết có thể làm tràn stack.

### 3.2. toString() và ghi log

Ngay cả khi ứng dụng không tạo JSON, phương thức **toString()** cũng có thể đi qua đồ thị:

~~~java
// Ví dụ thiết kế nguy hiểm:
public String toString() {
    return "PurchaseOrder{lines=" + lines + "}";
}

// Và ở OrderLine:
public String toString() {
    return "OrderLine{order=" + order + "}";
}
~~~

Khi log **order.toString()**, Java có thể liên tục gọi OrderLine.toString() rồi PurchaseOrder.toString(). Logger hoặc debugger hiển thị object cũng có thể kích hoạt đường truy cập tương tự.

Vì vậy, lỗi StackOverflowError ở bước **log đối tượng** chưa chắc do Jackson hoặc JPA. Cần xem stack trace để biết nó đi qua serialization, toString, equals/hashCode hay một phương thức duyệt tùy chỉnh.

### 3.3. equals() và hashCode()

Một hàm equals() so sánh toàn bộ collection ở cha, trong khi equals() của con lại so sánh trường order, có thể tạo vòng gọi. Tương tự, hashCode() của cha tính hash từ lines, còn hashCode() của line tính hash từ order, có thể lặp vô hạn.

Đây cũng là rủi ro của việc dùng các công cụ tự sinh equals/hashCode trên toàn bộ trường entity mà không loại trừ association. Hậu quả không chỉ là StackOverflowError: việc vô tình duyệt association lazy còn có thể phát sinh truy vấn và làm thay đổi hiệu năng hoặc gây lỗi khi entity detached.

### 3.4. Vòng lặp trong thuật toán tự viết

Một hàm duyệt object graph như sau không phù hợp với đồ thị có chu kỳ:

~~~java
void visit(Object current) {
    for (Object related : relationshipsOf(current)) {
        visit(related);
    }
}
~~~

Ngay cả khi không dùng Jackson, thuật toán cần tập đối tượng đã thăm hoặc quy tắc giới hạn đường duyệt. Nếu mục tiêu là hiển thị dữ liệu nghiệp vụ, thường nên chọn những thuộc tính cần đưa vào đầu ra thay vì duyệt mọi quan hệ có thể tìm thấy.

## 4. Cách ưu tiên: thiết kế DTO cho API

Đối với REST API có yêu cầu hợp đồng đầu ra rõ ràng, **Data Transfer Object (DTO)** thường là cách dễ kiểm soát nhất để biểu diễn một đồ thị JPA hai hướng.

Thay vì xuất nguyên entity:

~~~text
PurchaseOrder <--> OrderLine
~~~

hãy định nghĩa một cây JSON hữu hạn:

~~~text
OrderResponse
  ├── id
  ├── orderNumber
  └── lines[]
        ├── id
        ├── sku
        └── quantity
~~~

Mỗi dòng hàng trong response không chứa một **PurchaseOrder** nữa. Đây là **chọn hình dạng dữ liệu trả về theo use case**, không phải làm mất quan hệ trong entity hay database.

### 4.1. Định nghĩa DTO Java

Ví dụ dùng Java record (Java 16+):

~~~java
package com.example.orders.api;

import java.util.List;

public record OrderLineResponse(
    Long id,
    String sku,
    int quantity
) {}

public record OrderResponse(
    Long id,
    String orderNumber,
    List<OrderLineResponse> lines
) {}
~~~

Với dự án Java cũ, có thể dùng các class DTO với constructor và getter tương ứng. DTO không cần @Entity, @OneToMany hoặc @ManyToOne. Nó mô tả **dữ liệu API muốn trả về**, không mô tả toàn bộ ánh xạ persistence.

### 4.2. Ánh xạ entity sang DTO trong tầng service

~~~java
package com.example.orders;

import com.example.orders.api.OrderLineResponse;
import com.example.orders.api.OrderResponse;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderQueryService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public OrderResponse findOrder(long id) {
        List<PurchaseOrder> found = em.createQuery(
            "select distinct o from PurchaseOrder o " +
            "left join fetch o.lines where o.id = :id",
            PurchaseOrder.class
        ).setParameter("id", id)
         .getResultList();

        if (found.isEmpty()) {
            throw new IllegalArgumentException("Order not found");
        }

        PurchaseOrder order = found.get(0);
        List<OrderLineResponse> lineDtos = order.getLines().stream()
            .map(line -> new OrderLineResponse(
                line.getId(),
                line.getSku(),
                line.getQuantity()
            ))
            .toList();

        return new OrderResponse(
            order.getId(),
            order.getOrderNumber(),
            lineDtos
        );
    }
}
~~~

Ví dụ giả định Spring transaction manager, persistence unit, DTO và entity đã được cấu hình đúng. Phương thức **Stream.toList()** yêu cầu Java 16+; có thể dùng Collectors.toList() trên phiên bản cũ.

Lệnh **left join fetch** tải lines trong phạm vi truy vấn để có thể lập DTO ngay trong transaction. Đây là một ví dụ cho **một đơn hàng theo ID**, không phải gợi ý dùng fetch join collection cùng phân trang trên toàn bộ bảng: fetch join collection và pagination có thể gây kết quả hoặc hiệu năng không mong muốn tùy provider. Với danh sách lớn, cân nhắc truy vấn projection, phân trang riêng và cách tải dữ liệu phù hợp.

Một điểm đáng chú ý: service **không hề đọc line.getOrder()** khi ánh xạ sang DTO. Đường tham chiếu từ child ngược về parent vẫn tồn tại trong entity, nhưng không được đưa vào đầu ra JSON.

### 4.3. Controller chỉ trả DTO

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderQueryService service;

    public OrderController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public OrderResponse getOrder(@PathVariable long id) {
        return service.findOrder(id);
    }
}
~~~

Kết quả dự kiến:

~~~json
{
  "id": 100,
  "orderNumber": "PO-2026-001",
  "lines": [
    {
      "id": 900,
      "sku": "SKU-100",
      "quantity": 2
    },
    {
      "id": 901,
      "sku": "SKU-200",
      "quantity": 1
    }
  ]
}
~~~

JSON kết thúc tự nhiên sau các trường của dòng hàng. Không có chu kỳ vì DTO không chứa liên kết ngược tới OrderResponse.

### 4.4. Nếu API cần đường liên kết về cha?

Không nhất thiết phải nhúng toàn bộ parent. Một DTO của dòng hàng có thể chứa **orderId**:

~~~java
public record OrderLineDetailResponse(
    Long id,
    String sku,
    int quantity,
    Long orderId
) {}
~~~

Khi lập DTO từ entity, lấy **line.getOrder().getId()** trong một transaction phù hợp, hoặc truy vấn trực tiếp ID bằng projection. Response có thể dùng:

~~~json
{
  "id": 900,
  "sku": "SKU-100",
  "quantity": 2,
  "orderId": 100
}
~~~

Một ID là giá trị scalar, không khiến serializer quay lại toàn bộ PurchaseOrder. Đây thường là hình thức biểu diễn liên kết phù hợp hơn cho API muốn mô tả quan hệ nhưng không cần mở rộng mọi entity.

## 5. Phương án Jackson: @JsonIgnore

Nếu ứng dụng chấp nhận dùng entity làm dữ liệu phản hồi trong tình huống đơn giản, có thể ngắt chu kỳ serialization bằng **@JsonIgnore** ở một cạnh quan hệ. Ví dụ, giữ danh sách lines trong PurchaseOrder nhưng bỏ thuộc tính order khi serialize một OrderLine:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "order_id", nullable = false)
@JsonIgnore
private PurchaseOrder order;
~~~

Khi serialize PurchaseOrder, Jackson có thể đi vào lines, nhưng mỗi line không xuất tiếp order. Đồ thị JSON hữu hạn:

~~~json
{
  "id": 100,
  "orderNumber": "PO-2026-001",
  "lines": [
    { "id": 900, "sku": "SKU-100", "quantity": 2 }
  ]
}
~~~

**@JsonIgnore là annotation của Jackson**, không phải JPA. Nó điều khiển những thuộc tính Jackson nhìn thấy; association trong persistence context vẫn tồn tại và JPA vẫn có thể lưu khóa ngoại như bình thường.

Điều cần cân nhắc:

- Thuộc tính bị ignore sẽ không xuất hiện khi serialize entity theo cấu hình này, kể cả khi một endpoint chi tiết OrderLine muốn biểu diễn parent.
- Tùy vị trí annotation và cấu hình Jackson, @JsonIgnore có thể ảnh hưởng cả serialization lẫn deserialization.
- Việc giấu trường trên JSON không làm field trở thành bất biến hoặc bảo vệ quyền truy cập dữ liệu trong entity.
- Nếu cần hai response khác nhau cho hai endpoint, DTO thường linh hoạt hơn việc chỉnh annotation entity liên tục.

### 5.1. @JsonIgnoreProperties

Có thể bỏ qua một hoặc nhiều thuộc tính bằng:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties({"order"})
public class OrderLine {
    // Phần mapping JPA như các ví dụ ở trên.
}
~~~

Hoặc áp dụng cấu hình Jackson lên tham chiếu cần giới hạn thuộc tính. Tuy nhiên, phải xác định đúng nơi áp dụng để tránh ẩn các trường ngoài ý muốn. Nếu cả hai phía được biểu diễn trong những context khác nhau, DTO hoặc cấu hình serialization theo từng view có thể phù hợp hơn.

Không nên coi **@JsonIgnoreProperties({"hibernateLazyInitializer", "handler"})** là giải pháp cho vòng tham chiếu. Các tên này liên quan một số proxy/triển khai Hibernate; ẩn chúng không cắt đường **order -> lines -> order**, và phụ thuộc chi tiết provider.

## 6. Phương án Jackson: @JsonManagedReference và @JsonBackReference

Jackson cung cấp một cặp annotation dành cho quan hệ cha–con:

- **@JsonManagedReference** ở cạnh đi từ parent xuống child mà ta muốn hiển thị.
- **@JsonBackReference** ở cạnh đi ngược từ child về parent. Jackson không xuất cạnh ngược này trong JSON tương ứng.

Ví dụ đặt trên entity:

~~~java
// Trong PurchaseOrder
@OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true)
@JsonManagedReference("order-lines")
private List<OrderLine> lines = new ArrayList<>();

// Trong OrderLine
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "order_id", nullable = false)
@JsonBackReference("order-lines")
private PurchaseOrder order;
~~~

Cần import:

~~~java
import com.fasterxml.jackson.annotation.JsonManagedReference;
import com.fasterxml.jackson.annotation.JsonBackReference;
~~~

Khi serialize từ PurchaseOrder, lines vẫn xuất hiện; trường order trong mỗi line bị bỏ qua. Đường lặp vì vậy dừng tại line. Khi deserialization một cấu trúc được hỗ trợ, Jackson còn có cơ chế thiết lập liên kết back-reference về đối tượng chủ.

Ví dụ đầu ra thường có dạng:

~~~json
{
  "id": 100,
  "orderNumber": "PO-2026-001",
  "lines": [
    { "id": 900, "sku": "SKU-100", "quantity": 2 }
  ]
}
~~~

### 6.1. Khi nào cách này phù hợp?

Cặp managed/back reference khá tự nhiên khi JSON luôn có **hướng cha → con**, chẳng hạn đơn hàng chứa dòng hàng, bài viết chứa bình luận, phòng ban chứa nhân viên.

Những giới hạn:

- Với response lấy **OrderLine làm gốc**, thông tin parent thường không được hiển thị qua trường đánh dấu back-reference.
- Một đối tượng có nhiều loại quan hệ hai hướng cần các **tên logical reference khác nhau**, chẳng hạn "order-lines" và "invoice-lines", để Jackson phân biệt cặp.
- Back-reference thường phải là một thuộc tính object/bean thích hợp, không đơn giản áp dụng cho mọi collection hoặc cấu trúc Map ở phía ngược.
- Không nên đặt @JsonManagedReference và @JsonBackReference tùy tiện chỉ để hết exception mà chưa xác định hướng dữ liệu API.
- Đây là cơ chế của Jackson; XML serializer, GraphQL hoặc công cụ xuất dữ liệu khác có quy tắc riêng.

Khi API cần biểu diễn nhiều đường đi, một cách cố định managed/back reference cho mọi endpoint có thể gây khó mở rộng. DTO vẫn cho phép mô tả chính xác từng use case hơn.

### 6.2. Hai quan hệ hai hướng trong cùng entity

Ví dụ một Task có hai collection: comments và attachments. Nếu hai cặp đều dùng tên logical mặc định của Jackson, có thể xảy ra lỗi không phân biệt được back-reference khi xử lý nhiều quan hệ.

Đặt tên rõ:

~~~java
@JsonManagedReference("task-comments")
private List<Comment> comments;

@JsonManagedReference("task-attachments")
private List<Attachment> attachments;
~~~

Ở Comment:

~~~java
@JsonBackReference("task-comments")
private Task task;
~~~

Ở Attachment:

~~~java
@JsonBackReference("task-attachments")
private Task task;
~~~

Mỗi cặp dùng cùng một tên tương ứng. Không nên đổi tên một phía mà quên phía còn lại.

## 7. Phương án Jackson: @JsonIdentityInfo

Thay vì luôn cắt liên kết ngược, Jackson có thể biểu diễn các đối tượng đã xuất hiện thông qua **ID** bằng **@JsonIdentityInfo**.

Ví dụ đặt trên cả hai loại entity:

~~~java
import com.fasterxml.jackson.annotation.JsonIdentityInfo;
import com.fasterxml.jackson.annotation.ObjectIdGenerators;

@Entity
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
public class PurchaseOrder {
    // id, orderNumber, lines, ...
}

@Entity
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
public class OrderLine {
    // id, sku, quantity, order, ...
}
~~~

Với một đồ thị đã có ID ổn định, Jackson có thể biểu diễn lần xuất hiện đầu tiên của object bằng dữ liệu đầy đủ, còn những lần tham chiếu tiếp theo bằng ID. Một dạng kết quả minh họa:

~~~json
{
  "id": 100,
  "orderNumber": "PO-2026-001",
  "lines": [
    {
      "id": 900,
      "sku": "SKU-100",
      "quantity": 2,
      "order": 100
    }
  ]
}
~~~

Trong ví dụ này, order bên trong line là giá trị tham chiếu **100**, nên Jackson không cần mở rộng tiếp thành PurchaseOrder đầy đủ lần nữa.

### 7.1. Ưu điểm

- Có thể giữ thông tin rằng child tham chiếu parent.
- Biểu diễn cấu trúc giống **đồ thị có định danh** hơn là cây thuần túy.
- Có thể giúp những trường hợp nhiều đối tượng chia sẻ cùng một entity đích.

### 7.2. Giới hạn và rủi ro

- **ID của entity mới** có thể còn null trước persist/flush hoặc trước khi provider cấp khóa. Generator dựa trên property "id" cần giá trị phù hợp để nhận diện đối tượng một cách nhất quán.
- Kiểu ID của PurchaseOrder và OrderLine có thể trùng về giá trị số; khi dùng identity annotation, phải xác định scope và cách Jackson quản lý object ID theo cấu hình thực tế.
- JSON có thể chứa **object đầy đủ ở lần đầu** và **ID ở lần sau**, khiến client phải hiểu hai dạng giá trị tùy vị trí và thứ tự duyệt.
- Hibernate proxy, collection lazy, chu kỳ phức tạp và cách định danh có thể làm response khó dự đoán nếu không kiểm thử.
- Đặt annotation trên entity khiến cấu trúc JSON phụ thuộc vào nội bộ ORM và không tự giải quyết vấn đề dữ liệu nhạy cảm, phân trang hay N+1.

Nếu JSON cần một schema ổn định và rõ kiểu dữ liệu, việc dùng DTO với trường **orderId** thường đơn giản hơn việc cho Jackson tự định danh toàn bộ đồ thị.

## 8. So sánh các cách biểu diễn

| Cách xử lý | JSON đầu ra | Điểm mạnh | Giới hạn |
|---|---|---|---|
| **DTO/projection** | Chọn chính xác các trường | Hợp đồng API rõ, kiểm soát dữ liệu và hiệu năng | Cần lớp DTO và mã ánh xạ |
| **@JsonIgnore** | Bỏ hẳn một thuộc tính | Dễ áp dụng cho tình huống đơn giản | Không có thuộc tính bị bỏ ở các endpoint khác nếu cùng mapping Jackson |
| **@JsonManagedReference / @JsonBackReference** | Cây cha → con, bỏ cạnh ngược | Phù hợp cấu trúc phân cấp | Khó khi API cần hướng ngược hoặc nhiều quan hệ |
| **@JsonIdentityInfo** | Object và tham chiếu bằng ID | Có thể biểu diễn đồ thị có chia sẻ đối tượng | Hình dạng JSON phức tạp, cần ID và kiểm thử kỹ |
| **@JsonIgnoreProperties** | Bỏ trường chỉ định | Có thể cấu hình gọn | Phụ thuộc vị trí áp dụng, có thể ẩn thông tin nhiều hơn dự định |
| **Tự viết serializer có visited set** | Theo quy tắc tùy chỉnh | Kiểm soát thuật toán đồ thị đặc thù | Dễ sai, tăng chi phí bảo trì, thường không cần cho REST CRUD |

**Gợi ý theo use case:** API công khai, lâu dài và có nhiều kiểu response nên ưu tiên DTO. Với ứng dụng nội bộ đơn giản, endpoint cố định cha–con, có thể dùng cặp annotation Jackson. Nếu thực sự cần xuất cấu trúc đồ thị, cân nhắc dùng ID tham chiếu có schema rõ ràng.

## 9. Lombok: cẩn trọng với @Data, @ToString và @EqualsAndHashCode

Nhiều dự án dùng Lombok để giảm boilerplate:

~~~java
@Data
@Entity
public class PurchaseOrder {
    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}

@Data
@Entity
public class OrderLine {
    @ManyToOne
    private PurchaseOrder order;
}
~~~

**@Data** có thể sinh **toString(), equals() và hashCode()** dựa trên các field của entity. Khi các phương thức đó đi qua lines và order, việc log, so sánh hoặc sử dụng entity trong collection có thể làm phát sinh vòng gọi hoặc kích hoạt lazy loading.

### 9.1. Kiểm soát toString()

Ví dụ chỉ đưa thông tin scalar cần thiết vào toString:

~~~java
import lombok.Getter;
import lombok.ToString;

@Getter
@ToString(onlyExplicitlyIncluded = true)
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue
    @ToString.Include
    private Long id;

    @ToString.Include
    private String orderNumber;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}
}
~~~

Đoạn code chỉ minh họa Lombok trên một phiên bản entity rút gọn, không đặt đồng thời với class PurchaseOrder đầy đủ ở phần trước. Trường lines không được chọn để xuất trong toString.

Cách khác, nếu đang dùng **@ToString** bình thường, có thể đặt **@ToString.Exclude** trên association:

~~~java
@ToString.Exclude
@OneToMany(mappedBy = "order")
private List<OrderLine> lines = new ArrayList<>();
~~~

Ở phía con cũng cần cân nhắc bỏ trường order khỏi toString. Nếu chỉ loại một cạnh, một đường duyệt khác vẫn có thể bị kích hoạt bởi các method được sinh còn lại.

### 9.2. Kiểm soát equals() và hashCode()

**@EqualsAndHashCode.Exclude** có thể giúp loại association khỏi equals/hashCode do Lombok sinh:

~~~java
@EqualsAndHashCode.Exclude
@ManyToOne(fetch = FetchType.LAZY)
private PurchaseOrder order;
~~~

Tuy nhiên, việc thiết kế equals/hashCode cho **JPA entity** còn phải xét entity mới có ID null, ID được cấp sau persist, proxy và vòng đời entity. Không nên mặc định mọi entity đều an toàn khi sinh equals/hashCode từ tất cả scalar field hoặc chỉ từ ID chưa được cấp.

Một chiến lược phổ biến là viết equals/hashCode theo danh tính bền vững phù hợp với mô hình và provider, hoặc dùng quy tắc tham chiếu nếu nghiệp vụ cho phép. Không dùng collection quan hệ hay business key mutable làm đầu vào trực tiếp cho hashCode của entity đang được giữ trong HashSet.

### 9.3. Logging và debug

Thay vì:

~~~java
log.info("Order: {}", order);
~~~

có thể log dữ liệu scalar:

~~~java
log.info(
    "Order id={}, orderNumber={}, lineCount={}",
    order.getId(),
    order.getOrderNumber(),
    order.getLines().size()
);
~~~

Ngay cả **getLines().size()** có thể kích hoạt lazy loading nếu collection chưa được tải; vì vậy nên cân nhắc mục đích log và trạng thái transaction. Nếu chỉ cần ID và số đơn, log hai trường đó để tránh truy cập association không cần thiết.

## 10. Đệ quy, lazy loading và N+1 là những vấn đề khác nhau

Khi trả entity trực tiếp, ứng dụng có thể đồng thời gặp:

1. **Vòng tham chiếu:** cha chứa con, con chứa cha, serializer lặp.
2. **LazyInitializationException hoặc lỗi tương đương:** serializer truy cập association chưa tải khi persistence context đã kết thúc.
3. **N+1 query:** serializer đi qua nhiều association và kích hoạt thêm truy vấn cho từng entity.
4. **Lộ dữ liệu ngoài ý muốn:** JSON xuất những field nội bộ, quan hệ hoặc thông tin người dùng không cần.
5. **Payload quá lớn:** collection nhiều phần tử hoặc đồ thị sâu bị mở rộng.

Cắt vòng bằng **@JsonIgnore** có thể giúp vấn đề thứ nhất nhưng không nhất thiết giải quyết các vấn đề còn lại.

### 10.1. Không đổi mọi quan hệ sang EAGER

Một phản ứng thường gặp là sửa:

~~~java
@OneToMany(fetch = FetchType.EAGER)
private List<OrderLine> lines;
~~~

Việc tải eager **không cắt chu kỳ** order → lines → order. Nó còn có thể làm tăng lượng dữ liệu tải, JOIN hoặc truy vấn bổ sung. Chọn fetch plan theo **use case**, không theo mong muốn tránh recursion.

### 10.2. Open Session in View không phải cách sửa recursion

Một số framework có cơ chế giữ persistence context mở trong giai đoạn serialize response. Điều này có thể khiến lazy association còn truy cập được, nhưng **không tự giới hạn đồ thị**. Serializer thậm chí có thể tải thêm nhiều quan hệ khi đi sâu vào đồ thị.

Thiết kế DTO và tải đủ dữ liệu trong transaction thường giúp xác định điểm truy cập DB rõ ràng hơn. Nếu sử dụng Open Session in View, cần hiểu chi phí và giới hạn của kiến trúc đó; không nên bật chỉ để che lỗi lặp vô hạn.

### 10.3. Jackson Hibernate module cũng không thay thế thiết kế API

Jackson có các module tích hợp với proxy/collection lazy của những phiên bản Hibernate tương ứng. Chúng có thể thay đổi cách serializer xử lý proxy chưa tải, nhưng **không mặc nhiên thiết kế một cây JSON hợp lệ cho mọi chu kỳ hai hướng**.

Phiên bản module cần phù hợp với phiên bản Hibernate/Jakarta Persistence. Không nên dùng module để thay thế việc xác định rõ những quan hệ và dữ liệu nào được xuất từ API.

### 10.4. Chọn fetch plan đúng mục đích

Với một đơn hàng có danh sách dòng hàng, một số cách là:

- JPQL **join fetch** cho một aggregate cụ thể, như ví dụ service ở trên.
- **Entity graph** để chỉ rõ quan hệ cần tải trong một use case.
- Truy vấn DTO/projection trực tiếp từ database.
- Phân trang order và tải lines theo nhóm khi danh sách lớn.

Nếu dùng fetch join collection với pagination, cần kiểm tra cách provider xử lý việc nhân bản hàng SQL và giới hạn kết quả. Việc tránh vòng JSON không nên được đánh đổi bằng truy vấn khó kiểm soát.

## 11. Thuật toán duyệt đồ thị có visited set

Trong một số công cụ nội bộ, mục tiêu thực sự là **duyệt đồ thị** của entity hoặc domain object, không chỉ tạo response REST. Khi đó, cần nhận diện những node đã thăm.

Ví dụ một hàm thăm Order và OrderLine có thể dùng tập theo **danh tính object trong JVM**:

~~~java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public final class OrderGraphWalker {

    private final Set<Object> visited =
        Collections.newSetFromMap(new IdentityHashMap<>());

    public void walkOrder(PurchaseOrder order) {
        if (order == null || !visited.add(order)) {
            return;
        }

        System.out.println("orderId=" + order.getId());
        for (OrderLine line : order.getLines()) {
            walkLine(line);
        }
    }

    private void walkLine(OrderLine line) {
        if (line == null || !visited.add(line)) {
            return;
        }

        System.out.println("lineId=" + line.getId());
        walkOrder(line.getOrder());
    }
}
~~~

Ở ví dụ, **IdentityHashMap** dùng so sánh tham chiếu Java thay vì gọi equals/hashCode của entity, giúp tránh lặp do những phương thức equals/hashCode có thể được thiết kế phức tạp. Việc kiểm tra **visited.add()** xảy ra trước khi duyệt các cạnh tiếp theo, nên khi quay lại cùng object, thuật toán dừng.

Các giới hạn cần hiểu:

- Hai object Java khác nhau có thể đại diện cùng một hàng DB nếu đến từ hai persistence context khác nhau; visited theo tham chiếu JVM không đồng nghĩa visited theo khóa chính DB.
- Nếu muốn nhận diện node theo entity ID, cần xét type, composite key, ID null của entity mới và proxy.
- Nếu quan hệ lazy chưa tải, việc duyệt có thể phát sinh SQL hoặc lỗi khi context đã đóng.
- Với đồ thị cực sâu, thuật toán đệ quy vẫn có nguy cơ tràn stack dù không có chu kỳ; có thể cần stack/queue lặp và giới hạn số node.
- Với API REST thông thường, tạo DTO có cấu trúc rõ là giải pháp đơn giản hơn tự viết graph walker tổng quát.

## 12. Không cắt quan hệ JPA bằng cách gán null trước khi serialize

Một cách sửa lỗi nguy hiểm:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, id);

for (OrderLine line : order.getLines()) {
    line.attachToOrder(null); // Tránh làm điều này chỉ để tạo JSON.
}

return order;
~~~

Nếu các entity đang managed, việc đặt **line.order = null** có thể bị JPA nhận là thay đổi quan hệ sở hữu và dẫn tới UPDATE khóa ngoại, lỗi NOT NULL hoặc thay đổi dữ liệu không mong muốn khi flush. Với cascade và orphan removal, thao tác có thể gây hậu quả khác tùy cách sửa collection.

Không nên đụng vào **trạng thái entity được quản lý** chỉ để điều chỉnh output JSON. Hãy ngắt cạnh ở **lớp biểu diễn**: DTO, Jackson annotation phù hợp hoặc serializer có quy tắc.

Tương tự, không xóa **@ManyToOne** hay **mappedBy** khỏi mapping khi ứng dụng cần quan hệ hai hướng. Điều này thay đổi cách JPA hiểu quan hệ và có thể khiến dữ liệu hoặc SQL khác với mục đích ban đầu.

## 13. Kiểm thử hình dạng JSON và khả năng dừng

Sau khi chọn cách biểu diễn, nên có các tình huống kiểm thử tập trung vào **contract đầu ra** và **điểm dừng đồ thị**. Đây là ví dụ test cho DTO, độc lập với JPA provider:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OrderResponseSerializationTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void childResponseDoesNotEmbedParentAgain() throws Exception {
        OrderResponse response = new OrderResponse(
            100L,
            "PO-2026-001",
            List.of(new OrderLineResponse(900L, "SKU-100", 2))
        );

        String json = mapper.writeValueAsString(response);
        JsonNode root = mapper.readTree(json);

        assertEquals(100L, root.get("id").asLong());
        assertEquals(1, root.get("lines").size());
        assertEquals("SKU-100", root.get("lines").get(0).get("sku").asText());
        assertFalse(root.get("lines").get(0).has("order"));
    }
}
~~~

Ví dụ giả định dependencies Jackson databind và JUnit 5 cùng các DTO đã khai báo. Nếu dùng Java record với Jackson phiên bản phù hợp, việc serialize diễn ra bình thường. Đoạn này minh họa kiểm tra JSON shape, không yêu cầu chạy framework Spring hay kết nối database.

### 13.1. Tình huống cần kiểm tra với entity thật

Với ứng dụng thực tế, có thể kiểm tra những kịch bản:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Đơn hàng có 0 dòng | JSON hợp lệ, collection rỗng theo hợp đồng |
| Đơn hàng có 1 hoặc nhiều dòng | JSON có đúng dữ liệu, không lặp parent vô hạn |
| Dòng hàng trả qua endpoint riêng | Có đúng orderId hoặc thông tin parent được thiết kế |
| Entity được tải với quan hệ lazy | Không phát sinh lỗi khi serialize ngoài transaction |
| Collection lớn | Không trả payload không giới hạn hoặc tạo N+1 không dự kiến |
| Entity mới có ID null | Cách xử lý @JsonIdentityInfo không mơ hồ |
| Nhiều quan hệ bidirectional cùng entity | Không nhầm các cặp managed/back reference |
| Log entity | Không gọi toString/equals/hashCode lặp hoặc tải quá nhiều |
| Deserialization dữ liệu đầu vào | Không sửa quan hệ hoặc ghi đè field nhạy cảm ngoài ý muốn |
| Có người dùng khác quyền truy cập | Không lộ trường/quan hệ không được phép |

Trong các phép kiểm thử thực tế, ngoài việc không xuất hiện StackOverflowError, nên xác nhận **cấu trúc JSON, số query, quyền dữ liệu và kích thước response**. Một response không lỗi nhưng chứa toàn bộ graph nhiều nghìn entity vẫn có thể là vấn đề thiết kế.

## 14. Phân tích lỗi theo stack trace

Khi gặp lỗi, bước đầu tiên là xác định **điểm phát sinh vòng lặp**, không chỉ nhìn tên exception:

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Lỗi Jackson khi writeValueAsString | Đi từ parent tới child rồi quay về parent | DTO, @JsonIgnore, managed/back reference hoặc identity reference |
| StackOverflowError khi log entity | toString của hai phía chứa nhau | Chỉ log scalar, loại association khỏi toString |
| StackOverflowError khi contains/hashCode | equals/hashCode đi qua quan hệ | Thiết kế identity/equality hợp lý, không đưa association vào hash |
| LazyInitializationException | Serializer truy cập association sau khi context đóng | Lấy dữ liệu đủ trong transaction và map DTO |
| Rất nhiều SELECT khi trả API | Serializer kích hoạt lazy loading từng entity | Projection, fetch plan hoặc truy vấn có tổ chức |
| JSON quá lớn dù không StackOverflow | Đồ thị mở rộng quá nhiều cạnh | Định nghĩa API response hữu hạn, phân trang |
| Back-reference bị thiếu hoặc báo conflict | Annotation Jackson đặt sai cặp/tên | Đặt đúng managed/back, tên riêng cho mỗi cặp |
| @JsonIdentityInfo xuất ID null hoặc hình dạng khó dùng | Entity chưa có ID hoặc cấu hình identity không phù hợp | Kiểm tra lifecycle, chọn DTO hoặc ID đã cấp |
| SQL UPDATE order_id thành NULL sau serialize | Code đã sửa quan hệ managed để tránh recursion | Không thay entity cho mục đích trình bày |
| Lộ thông tin ngoài endpoint | Trả nguyên entity có field/association nhạy cảm | DTO với danh sách trường được phép |

Nếu stack trace có nhiều lần gọi vào **BeanSerializer**, getter của PurchaseOrder/OrderLine hoặc những đường đi qua collection, hãy kiểm tra chu kỳ Jackson. Nếu lặp lại **toString**, **hashCode** hoặc **equals**, hướng xử lý nằm ở phương thức Java hoặc Lombok, không nhất thiết ở Jackson.

## 15. Các phương án xử lý không phù hợp

### 15.1. Thay hết LAZY bằng EAGER

EAGER làm quan hệ được tải sớm hơn, nhưng **không phá chu kỳ** của đồ thị. Nó có thể khiến truy vấn nặng và payload lớn hơn.

### 15.2. Tắt mọi association trong JSON

Đặt @JsonIgnore bừa bãi lên cả lines và order có thể làm API mất dữ liệu cần thiết. Phải chọn hướng biểu diễn phù hợp từng endpoint.

### 15.3. Bỏ mappedBy để “xóa vòng”

Xóa mappedBy có thể làm thay đổi ownership/mapping DB, phát sinh join table hoặc DDL khác tùy cấu hình. Đây không phải giải pháp cho serializer đi qua các object tham chiếu nhau.

### 15.4. Trả DTO nhưng đưa entity vào DTO

Ví dụ:

~~~java
public record OrderResponse(Long id, List<OrderLine> lines) {}
~~~

Đây chưa thực sự cắt đồ thị: OrderLine vẫn có thuộc tính **order** và có thể quay về PurchaseOrder. DTO nên chứa **các DTO con hoặc trường scalar có chủ đích**, không đơn giản bao entity trong wrapper.

### 15.5. Để serializer quyết định kích thước response

Nếu JSON lặp được khống chế bằng identity reference nhưng vẫn chứa hàng nghìn association không cần thiết, API vẫn khó dùng và tốn tài nguyên. Thiết kế dữ liệu trả về và pagination cần được xác định ở tầng use case.

### 15.6. Dùng @JsonIgnore như cơ chế phân quyền

Ẩn một trường khỏi JSON không thay thế kiểm soát truy cập. Endpoint phải quyết định user được phép xem đơn hàng và những field nào. Một serializer khác hoặc đường truy cập khác vẫn có thể làm lộ field không được bảo vệ ở tầng nghiệp vụ.

### 15.7. Không kiểm tra dữ liệu đầu vào

Khi Jackson deserialize trực tiếp entity JPA, client có thể gửi cả collection và parent reference. Nếu không có quy tắc cập nhật rõ, application có thể vô tình thay ownership hoặc cascade. DTO cho request thường nên tách khỏi DTO response và entity.

## 16. Thiết kế request và response riêng

Ví dụ nghiệp vụ tạo đơn hàng có thể chấp nhận dữ liệu đầu vào dạng cây:

~~~json
{
  "orderNumber": "PO-2026-001",
  "lines": [
    { "sku": "SKU-100", "quantity": 2 },
    { "sku": "SKU-200", "quantity": 1 }
  ]
}
~~~

Định nghĩa request:

~~~java
public record CreateOrderLineRequest(
    String sku,
    int quantity
) {}

public record CreateOrderRequest(
    String orderNumber,
    List<CreateOrderLineRequest> lines
) {}
~~~

Service tạo entity và giữ hai phía nhất quán:

~~~java
@Transactional
public Long create(CreateOrderRequest request) {
    PurchaseOrder order = new PurchaseOrder(request.orderNumber());

    for (CreateOrderLineRequest item : request.lines()) {
        order.addLine(new OrderLine(item.sku(), item.quantity()));
    }

    em.persist(order);
    em.flush();
    return order.getId();
}
~~~

Ví dụ giả định EntityManager và transaction manager đã sẵn sàng. @OneToMany có cascade PERSIST (ở mẫu entity đầu bài dùng CascadeType.ALL), vì vậy persist order có thể lan truyền tới các line. **Đối tượng request không chứa tham chiếu ngược đến order**, còn entity sau khi tạo vẫn có quan hệ hai hướng đúng theo mapping.

Trong hệ thống thật, cần kiểm tra quyền tạo đơn, tính hợp lệ của SKU, số lượng, unique order number và các ràng buộc nghiệp vụ trước khi commit. Đối với một API tạo mới, có thể trả ID hoặc OrderResponse thay vì trả trực tiếp entity có đồ thị nhiều chiều.

## 17. Bài tập thực hành

### Bài 1: Xác định vòng lặp

Một entity Department có danh sách employees qua @OneToMany(mappedBy = "department"), Employee có @ManyToOne Department department.

**Câu hỏi:** Khi serialize Department không có annotation Jackson đặc biệt, đường nào có thể lặp?

**Gợi ý:** Department → employees[0] → department → employees[0] → ... Đây là vòng tham chiếu Java hợp lệ nhưng không thể mở rộng toàn bộ thành JSON lồng nhau vô hạn.

### Bài 2: Thiết kế response hữu hạn

Endpoint GET /departments/10 cần id, name và danh sách nhân viên chỉ gồm id, fullName.

**Yêu cầu:** đề xuất DTO.

**Gợi ý:**

~~~java
public record EmployeeResponse(Long id, String fullName) {}
public record DepartmentResponse(
    Long id,
    String name,
    List<EmployeeResponse> employees
) {}
~~~

Không chứa Department trong EmployeeResponse. Chu kỳ đã được cắt ở tầng hợp đồng API.

### Bài 3: Chọn đúng cặp Jackson annotation

Cho:

~~~java
@OneToMany(mappedBy = "post")
private List<Comment> comments;

@ManyToOne
private Post post;
~~~

**Câu hỏi:** Nếu JSON cần Post chứa comments mà không có trường post bên trong mỗi comment, dùng annotation nào?

**Gợi ý:** @JsonManagedReference("post-comments") trên collection comments ở Post; @JsonBackReference("post-comments") trên trường post của Comment. Cần đặt tên cặp thống nhất.

### Bài 4: Endpoint chi tiết con

GET /comments/50 cần thông tin bài viết cha nhưng không muốn serialize toàn bộ danh sách comment của bài viết.

**Câu hỏi:** Có nên dùng duy nhất @JsonBackReference trên Comment.post rồi trả trực tiếp Comment không?

**Gợi ý:** Cách đó khiến post không xuất hiện ở JSON. Một CommentDetailResponse chứa **postId**, **postTitle** hoặc một PostSummaryResponse do API định nghĩa thường phù hợp hơn.

### Bài 5: Lombok và log

Một entity @Data chứa List<OrderLine>, entity OrderLine @Data có PurchaseOrder order.

**Câu hỏi:** Vì sao chỉ gọi log.info với entity có thể phát sinh StackOverflowError?

**Gợi ý:** Lombok có thể sinh toString đi qua collection và association ngược, tạo vòng. equals/hashCode cũng cần được thiết kế an toàn. Không nên tự động dùng @Data trên toàn bộ các entity có quan hệ hai hướng.

### Bài 6: Phân biệt lỗi lazy với recursion

Controller trả PurchaseOrder sau khi transaction đã đóng. Jackson truy cập getLines() và gặp LazyInitializationException.

**Câu hỏi:** Thêm @JsonManagedReference có chắc sửa được lỗi không?

**Gợi ý:** Không. Annotation cặp managed/back chủ yếu xử lý vòng JSON; getLines() vẫn có thể là collection lazy chưa được tải. Dùng service transaction lấy dữ liệu cần thiết rồi map DTO, hoặc thiết kế fetch plan thích hợp.

### Bài 7: Không sửa entity để làm JSON

Một lập trình viên đặt mỗi line.order = null trước khi return order. Vì sao nguy hiểm?

**Gợi ý:** Nếu line đang managed, JPA có thể coi đó là thay đổi quan hệ sở hữu và thử UPDATE khóa ngoại thành NULL, gây lỗi NOT NULL hoặc thay đổi dữ liệu. Cần cắt vòng ở DTO/serialization, không thay đổi entity.

### Bài 8: Đồ thị lớn có nhiều chu kỳ

Ứng dụng có Company → Departments → Employees và Employee → Manager → Department. Muốn xuất sơ đồ tổ chức cho client.

**Gợi ý:** Định nghĩa schema rõ ràng như CompanyResponse chứa departments; DepartmentResponse chứa employees; EmployeeResponse chứa managerId. Có thể cần giới hạn độ sâu và phân trang. Không serialize tự động mọi association chỉ vì @JsonIdentityInfo có thể xử lý một số chu kỳ.

## 18. Bảng ghi nhớ

| Khi gặp | Điều cần làm |
|---|---|
| @OneToMany và @ManyToOne cùng tham chiếu | Giữ mapping hai hướng đúng, chỉ cắt đường khi biểu diễn |
| REST API cần JSON rõ ràng | Dùng DTO/projection với danh sách trường hữu hạn |
| Chỉ muốn parent chứa child | Có thể dùng @JsonManagedReference và @JsonBackReference hoặc @JsonIgnore ở child |
| Muốn thể hiện liên kết ngược | Dùng ID trong DTO hoặc cân nhắc @JsonIdentityInfo có kiểm soát |
| Nhiều cặp quan hệ Jackson | Đặt logical reference name riêng cho từng cặp |
| StackOverflowError khi log | Kiểm tra toString, Lombok và collection |
| StackOverflowError khi equals/hashCode | Không đưa toàn bộ association vào equality/hash |
| LazyInitializationException | Kiểm tra transaction, fetch plan và DTO mapping |
| N+1 khi serialize | Không để serializer tự tải toàn bộ graph, dùng query phù hợp |
| Cần duyệt graph tổng quát | Theo dõi node đã thăm và giới hạn phạm vi duyệt |
| Muốn bỏ parent khỏi JSON | Cắt cạnh ở serialization, không gán null lên entity managed |
| Trả entity trực tiếp làm lộ dữ liệu | Chuyển sang DTO và kiểm soát quyền truy cập ở tầng nghiệp vụ |

## 19. Tổng kết

Đồ thị quan hệ hai hướng của JPA **có thể chứa chu kỳ một cách hoàn toàn hợp lệ**. Khó khăn xuất hiện khi Java, Jackson hoặc một công cụ khác cố biểu diễn toàn bộ graph bằng các object lồng nhau mà không có quy tắc dừng. Vòng lặp có thể nằm trong JSON serializer, phương thức toString, equals/hashCode hoặc thuật toán duyệt tùy chỉnh.

Với REST API, lựa chọn có khả năng bảo trì tốt thường là **tạo DTO theo đúng use case**, chỉ đưa các trường cần thiết vào JSON và dùng ID để biểu diễn liên kết ngược khi cần. Các annotation Jackson như **@JsonIgnore**, **@JsonManagedReference/@JsonBackReference** và **@JsonIdentityInfo** vẫn hữu ích trong các ngữ cảnh thích hợp, nhưng mỗi cách có giới hạn về hợp đồng đầu ra và khả năng mở rộng.

Giữ **quan hệ JPA và phía sở hữu nhất quán trong bộ nhớ**, đồng thời thiết kế **biểu diễn dữ liệu hữu hạn, an toàn và có chủ đích**. Đó là cách ngăn lặp vô hạn mà không làm sai ý nghĩa nghiệp vụ của quan hệ một-nhiều hai hướng.
