# Bản đồ khái niệm: entity, value object, aggregate, repository và bảng dữ liệu

Trong **Spring Data Relational JDBC** (thường gọi ngắn là **Spring Data JDBC**), ta phải nhìn cùng một hệ thống từ hai phía:

- **Mô hình miền (domain model):** đối tượng nào có danh tính riêng, dữ liệu nào chỉ có ý nghĩa bởi giá trị, thay đổi nào phải được kiểm soát cùng nhau?
- **Mô hình quan hệ:** thông tin được lưu ở những bảng, cột, khóa chính và khóa ngoại nào?

Spring Data JDBC nối hai phía đó bằng cách ánh xạ các **aggregate** thành dữ liệu quan hệ và cung cấp **repository** để đọc/ghi qua **aggregate root**. Hiểu năm khái niệm *entity, value object, aggregate, repository, bảng dữ liệu* sẽ giúp thiết kế đúng ranh giới nghiệp vụ trước khi viết annotation hoặc câu SQL.

## 1. Nhìn toàn cảnh: năm khái niệm trả lời năm câu hỏi khác nhau

| Khái niệm | Câu hỏi cần trả lời | Trọng tâm | Ví dụ trong đơn hàng |
|---|---|---|---|
| **Entity** (thực thể) | “Đây có còn là cùng một đối tượng khi thuộc tính thay đổi?” | Danh tính và vòng đời | Đơn hàng, dòng hàng trong đơn |
| **Value object** (đối tượng giá trị) | “Hai giá trị này có tương đương về mặt nội dung không?” | Giá trị, thường bất biến | Địa chỉ giao hàng |
| **Aggregate** (cụm đối tượng nhất quán) | “Những thay đổi nào phải tuân theo quy tắc chung?” | Ranh giới nhất quán và quyền sở hữu | Đơn hàng cùng các dòng hàng, địa chỉ giao |
| **Repository** | “Ứng dụng lấy và lưu một aggregate bằng cách nào?” | Giao diện truy cập dữ liệu theo aggregate root | Kho lưu trữ đơn hàng |
| **Bảng dữ liệu** | “Trạng thái đối tượng được lưu vật lý ở đâu?” | Cột, hàng, khóa, ràng buộc quan hệ | Bảng đơn hàng và bảng dòng hàng |

Các khái niệm này **không tương ứng một-một**: một aggregate có thể gồm nhiều entity và value object, được lưu trên nhiều bảng, nhưng thường chỉ có **một repository của aggregate root**.

## 2. Bản đồ từ đối tượng nghiệp vụ đến dữ liệu

Xét chức năng tạo đơn hàng. Đơn hàng có mã định danh, trạng thái, địa chỉ giao và nhiều dòng sản phẩm; mỗi dòng có sản phẩm, số lượng và đơn giá. Khách hàng có vòng đời độc lập với đơn hàng.

~~~mermaid
flowchart TB
    Service["Ứng dụng / Use case"] --> Repo["PurchaseOrderRepository"]
    Repo -->|"tải và lưu root"| Root

    subgraph Aggregate["Aggregate: PurchaseOrder"]
        Root["PurchaseOrder<br/>Entity + Aggregate Root"]
        Line["PurchaseOrderLine<br/>Entity con"]
        Address["ShippingAddress<br/>Value Object"]
        Root -->|"sở hữu"| Line
        Root -->|"chứa"| Address
    end

    Root -. "customerId" .-> Customer["Customer<br/>Aggregate độc lập"]
    Root -->|"hàng dữ liệu"| Orders[("purchase_orders")]
    Line -->|"hàng dữ liệu"| Lines[("purchase_order_lines")]
    Address -->|"các cột ship_*"| Orders
    Lines -->|"FK: purchase_order_id"| Orders
~~~

**Đường nét liền trong aggregate** biểu diễn quyền sở hữu đối tượng. **Đường nét đứt theo customerId** biểu diễn tham chiếu tới aggregate khác bằng danh tính. Các mũi tên tới hình trụ minh họa cách dữ liệu được lưu; chúng không có nghĩa rằng entity bắt buộc phải có đúng một bảng hoặc value object luôn phải có bảng riêng.

## 3. Entity: nhận diện bằng danh tính, không chỉ bằng thuộc tính

**Entity** là đối tượng có **identity** và vòng đời riêng trong mô hình miền. Một đơn hàng có thể đổi trạng thái từ DRAFT sang CONFIRMED nhưng vẫn là **đơn hàng số 1001**. Hai đơn hàng cùng khách hàng, cùng dòng sản phẩm, cùng địa chỉ vẫn là hai đơn khác nhau nếu identity khác nhau.

Đối với dòng hàng, ta có thể cần xác định “dòng hàng nào vừa được sửa”, ngay cả khi hai dòng có cùng SKU và số lượng. Khi đó, **PurchaseOrderLine** là một entity *nằm trong* aggregate đơn hàng. Nó không vì thế trở thành aggregate root hay được sửa tùy ý từ bên ngoài.

Ở mức Spring Data JDBC:

- Annotation **@Id** xác định thuộc tính ID dùng cho lưu trữ; entity không cần annotation **@Entity** của JPA.
- **@Table** tùy chọn dùng để chỉ rõ bảng; mặc định framework có chiến lược suy ra tên bảng/cột.
- ID cơ sở dữ liệu hỗ trợ nhận diện bản ghi, nhưng **danh tính nghiệp vụ** có thể là một mã khác. Không nên mặc định hai loại định danh luôn đồng nghĩa.

**Phân biệt:** nếu đổi số lượng trên một dòng hàng thì entity ấy có thể vẫn là cùng dòng hàng; nếu đổi hoàn toàn một địa chỉ giao, ta thường coi đó là một **giá trị mới**.

## 4. Value object: nhận diện bằng giá trị

**Value object** biểu diễn một khái niệm dựa trên tập thuộc tính, **không cần identity riêng**. Ví dụ hai địa chỉ có cùng đường và thành phố có thể coi là cùng giá trị theo quy tắc miền. Kiểu bất biến như Java **record** phù hợp khi tất cả trường tạo nên giá trị của đối tượng.

~~~java
public record ShippingAddress(String street, String city) {
    public ShippingAddress {
        if (street == null || street.isBlank()) {
            throw new IllegalArgumentException("Street is required");
        }
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("City is required");
        }
    }
}
~~~

Việc thay địa chỉ nên được diễn đạt thành **gán một ShippingAddress mới**, thay vì cho phép các phần bên ngoài sửa độc lập từng trường bên trong.

Trong ví dụ dưới đây, Spring Data JDBC dùng **@Embedded** để trải phẳng ShippingAddress thành các cột **ship_street** và **ship_city** ngay trong bảng đơn hàng. Đây là **một lựa chọn ánh xạ**, không phải định nghĩa của value object: một value object cũng có thể được chuyển đổi thành một cột bằng converter, hoặc được lưu theo cấu trúc khác nếu thiết kế yêu cầu.

## 5. Aggregate: ranh giới giữ bất biến nghiệp vụ

**Aggregate** là một nhóm entity và value object phải duy trì các **bất biến (invariant)** chung. Mỗi aggregate có một **aggregate root**, là entity đại diện cho việc truy cập và thay đổi nhóm đó.

Trong ví dụ:

- **PurchaseOrder** là root. Chỉ root cung cấp các thao tác như thêm dòng hàng, đổi địa chỉ, xác nhận đơn.
- **PurchaseOrderLine** thuộc quyền sở hữu của đơn hàng; không có nghiệp vụ “dòng hàng tồn tại độc lập ngoài đơn”.
- **ShippingAddress** là giá trị nằm trong đơn.
- **Customer** là aggregate khác. Đơn hàng chỉ lưu **customerId**, vì khách hàng có vòng đời riêng.

Một số bất biến có thể đặt trên root:

1. Không chấp nhận số lượng dòng hàng nhỏ hơn hoặc bằng 0.
2. Không cho xác nhận đơn khi chưa có dòng hàng.
3. Không cho sửa dòng hàng sau khi đã xác nhận (nếu quy tắc nghiệp vụ đòi hỏi).

Nhờ đó, caller không cập nhật trực tiếp từng dòng hàng trong cơ sở dữ liệu và vô tình bỏ qua quy tắc của đơn.

**Ranh giới aggregate khác với ranh giới bảng:** một đơn hàng cùng danh sách dòng hàng là một aggregate dù được lưu trong hai bảng. Ngược lại, hai hàng có khóa ngoại liên kết chưa chắc thuộc cùng aggregate; tiêu chí quyết định là **quyền sở hữu và tính nhất quán nghiệp vụ**.

### Aggregate không bao trùm toàn bộ giao dịch ứng dụng

Ví dụ khi xác nhận đơn và trừ tồn kho, **PurchaseOrder** và **InventoryItem** có thể là hai aggregate độc lập. Khi đó cần một application service phối hợp, chọn cơ chế transaction/event/đồng bộ thích hợp; không nên ép chúng thành cùng aggregate chỉ vì có một use case sử dụng cả hai.

Trong Spring Data JDBC, việc lưu aggregate thường được thực hiện bằng **save(root)**. Với một aggregate đã tồn tại, các đối tượng con được tham chiếu có thể được **xóa và ghi lại** trong quá trình lưu toàn bộ trạng thái hiện tại. Vì vậy tránh coi **save(root)** là phép cập nhật tối thiểu từng entity con hoặc là cơ chế dirty checking của JPA.

## 6. Bảng dữ liệu là cách lưu trạng thái, không phải ranh giới miền

Một lược đồ quan hệ minh họa có thể như sau (cú pháp identity và kiểu dữ liệu cần điều chỉnh theo hệ quản trị cơ sở dữ liệu):

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    ship_street VARCHAR(200),
    ship_city VARCHAR(100)
);

CREATE TABLE purchase_order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL
        REFERENCES purchase_orders(id),
    line_position INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents BIGINT NOT NULL CHECK (unit_price_cents >= 0),
    UNIQUE (purchase_order_id, line_position)
);
~~~

| Thành phần mô hình miền | Vị trí lưu trong lược đồ minh họa |
|---|---|
| Identity của PurchaseOrder | **purchase_orders.id** |
| Customer tham chiếu bằng ID | **purchase_orders.customer_id** |
| Trạng thái đơn hàng | **purchase_orders.status** |
| ShippingAddress | **purchase_orders.ship_street**, **ship_city** |
| Identity của từng PurchaseOrderLine | **purchase_order_lines.id** |
| Quyền sở hữu dòng hàng | **purchase_order_lines.purchase_order_id** (FK tới root) |
| Thứ tự các dòng trong danh sách | **purchase_order_lines.line_position** |

**Khóa chính (PK)** giúp xác định hàng dữ liệu; **khóa ngoại (FK)** duy trì liên kết quan hệ; **CHECK/UNIQUE** bảo vệ một số điều kiện ở mức cơ sở dữ liệu. Chúng **bổ sung** cho bất biến nghiệp vụ trên aggregate root, nhưng không thể tự biểu diễn mọi quy tắc, chẳng hạn “chỉ được xác nhận đơn có ít nhất một dòng”.

Trường **customer_id** có thể có FK tới bảng khách hàng nếu schema yêu cầu. Việc tồn tại FK **không buộc** Customer phải trở thành đối tượng con của PurchaseOrder trong domain model.

## 7. Spring Data JDBC ánh xạ aggregate như thế nào?

Ví dụ tối giản dưới đây thể hiện các annotation cốt lõi. Để dùng trong dự án, hãy đặt các kiểu Java vào các tệp thích hợp và bổ sung những thao tác nghiệp vụ còn thiếu.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;
import org.springframework.data.repository.CrudRepository;

@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    private Long customerId;
    private String status;

    @Embedded(onEmpty = Embedded.OnEmpty.USE_NULL, prefix = "ship_")
    private ShippingAddress shippingAddress;

    @MappedCollection(
        idColumn = "purchase_order_id",
        keyColumn = "line_position"
    )
    private List<PurchaseOrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
        // Cho bộ ánh xạ khởi tạo đối tượng.
    }

    public PurchaseOrder(Long customerId, ShippingAddress shippingAddress) {
        if (customerId == null || shippingAddress == null) {
            throw new IllegalArgumentException("Customer and address required");
        }
        this.customerId = customerId;
        this.shippingAddress = shippingAddress;
        this.status = "DRAFT";
    }

    public void addLine(String sku, int quantity, long unitPriceCents) {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException("Order is already confirmed");
        }
        if (sku == null || sku.isBlank()
                || quantity <= 0 || unitPriceCents < 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
        lines.add(new PurchaseOrderLine(sku, quantity, unitPriceCents));
    }

    public void confirm() {
        if (lines.isEmpty()) {
            throw new IllegalStateException("Cannot confirm an empty order");
        }
        status = "CONFIRMED";
    }

    public Long getId() {
        return id;
    }
}

// Value object: các thành phần giá trị nằm trong cùng hàng với root.
record ShippingAddress(String street, String city) {}

@Table("purchase_order_lines")
class PurchaseOrderLine {
    @Id
    private Long id;
    private String sku;
    private int quantity;
    private long unitPriceCents;

    protected PurchaseOrderLine() {}

    PurchaseOrderLine(String sku, int quantity, long unitPriceCents) {
        this.sku = sku;
        this.quantity = quantity;
        this.unitPriceCents = unitPriceCents;
    }
}

interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {}
~~~

**Đọc sơ đồ ánh xạ từ code:**

- **@Table("purchase_orders") + @Id:** PurchaseOrder là một entity được lưu trong bảng đơn hàng. Trong mô hình này nó đồng thời là aggregate root.
- **@Embedded(..., prefix = "ship_"):** các trường của ShippingAddress trở thành cột có tiền tố tương ứng ở bảng root. **OnEmpty.USE_NULL** cho phép nhận lại **null** nếu toàn bộ cột của giá trị nhúng đều null.
- **@MappedCollection:** các PurchaseOrderLine được sở hữu bởi root; **idColumn** là cột FK trỏ về root, còn **keyColumn** lưu vị trí của phần tử trong **List**.
- **CrudRepository<PurchaseOrder, Long>:** repository thao tác theo **root**, không cần một repository độc lập cho PurchaseOrderLine trong thiết kế này.

Spring Data JDBC hỗ trợ ánh xạ các đối tượng con theo quan hệ sở hữu. Nó **không hoạt động theo cơ chế JPA**: không mặc định lazy-loading proxy, không quản lý một persistence context với dirty checking, và không dùng **@OneToMany/@ManyToOne** của JPA để khai báo mọi quan hệ. Nếu tham chiếu trực tiếp một entity khác dưới dạng đối tượng được framework ánh xạ, hãy xem xét liệu bạn đang vô tình đưa entity đó vào cùng aggregate hay không.

### Lưu và tải aggregate qua repository

~~~java
PurchaseOrder order = new PurchaseOrder(
    42L,
    new ShippingAddress("12 Nguyen Trai", "Ho Chi Minh City")
);
order.addLine("BOOK-01", 2, 150_000L);
order.addLine("PEN-02", 1, 20_000L);
order.confirm();

PurchaseOrder saved = repository.save(order);
Long orderId = saved.getId();

PurchaseOrder loaded = repository.findById(orderId)
    .orElseThrow();
~~~

Trong đoạn mã sử dụng này, **repository** là biến kiểu PurchaseOrderRepository được inject vào lớp dịch vụ; các lớp domain ở ví dụ trên chỉ minh họa phần ánh xạ. Khi tạo mới, Spring Data JDBC ghi bảng root và các dòng con; khi tải, nó dựng lại aggregate từ những hàng liên quan theo mapping. Gọi **save** với root đã tồn tại có thể tạo nhiều thao tác SQL đối với các bảng con, kể cả xóa rồi chèn lại. Nếu application service thực hiện nhiều thao tác cần nhất quán cùng nhau, khai báo **@Transactional** theo phạm vi nghiệp vụ phù hợp.

## 8. Repository: một cửa vào aggregate root

Repository thể hiện một tập hợp các aggregate root có thể lấy ra theo danh tính hoặc truy vấn:

~~~java
interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
    // Có thể bổ sung truy vấn phục vụ các use case về đơn hàng.
}
~~~

**Repository không đồng nghĩa bảng dữ liệu**, và cũng không buộc mọi entity phải có repository. Trong ví dụ:

- PurchaseOrderRepository cho phép đọc/ghi **PurchaseOrder**, gồm những phần được sở hữu bên trong aggregate.
- Không tạo PurchaseOrderLineRepository chỉ vì có bảng **purchase_order_lines**.
- Nếu cần màn hình báo cáo ghép nhiều bảng hoặc nhiều aggregate, có thể dùng một **read model/truy vấn riêng**; không cần thay đổi ranh giới aggregate chỉ để đáp ứng một truy vấn hiển thị.

Lợi ích là các thao tác thay đổi đi qua root, nơi các bất biến nghiệp vụ được giữ nhất quán. Chỉ thêm repository cho một entity con khi thật sự xác định lại ranh giới sở hữu và vòng đời của nó.

## 9. Đọc đúng các kiểu quan hệ

Giả sử có ba mối liên hệ sau:

| Liên hệ | Ý nghĩa miền | Cách thể hiện phù hợp |
|---|---|---|
| PurchaseOrder → PurchaseOrderLine | Root **sở hữu** dòng hàng; dòng hàng sống/chết theo đơn | Tập đối tượng con (**@MappedCollection**), FK tới root |
| PurchaseOrder → ShippingAddress | Root **chứa một giá trị** | Value object, có thể nhúng cột bằng **@Embedded** |
| PurchaseOrder → Customer | Hai aggregate **độc lập**; đơn cần biết khách nào đặt | Lưu **customerId**; truy cập Customer qua repository riêng khi cần |

Một số lỗi thiết kế thường gặp:

1. **Một bảng = một aggregate = một repository.** Điều này bỏ qua việc aggregate có thể trải nhiều bảng và entity con không được truy cập độc lập.
2. **Cứ có khóa ngoại là cùng aggregate.** Khóa ngoại chỉ thể hiện quan hệ dữ liệu; nó không nói ai sở hữu vòng đời hoặc quy tắc nghiệp vụ.
3. **Đưa Customer object trực tiếp vào PurchaseOrder vì muốn join tiện hơn.** Trong Spring Data JDBC, mối quan hệ object được ánh xạ có thể bị hiểu là quan hệ sở hữu. Lưu Customer ID và truy vấn riêng giữ ranh giới rõ ràng hơn.
4. **Sửa dòng hàng trực tiếp trong DB rồi tin rằng root vẫn hợp lệ.** Cách này dễ bỏ qua các quy tắc thêm dòng, chốt đơn, giới hạn số lượng; cân nhắc dùng API nghiệp vụ trên root.
5. **Cho rằng save(root) chỉ UPDATE một hàng đã thay đổi.** Spring Data JDBC hướng tới thao tác trên aggregate; với collection con có thể có nhiều DELETE/INSERT. Hãy hiểu chi phí ghi và thiết kế aggregate vừa đủ nhỏ.
6. **Cho rằng value object phải có ID.** Một địa chỉ giao hàng dùng theo giá trị thường không cần ID riêng, dù dữ liệu của nó có xuất hiện trong bảng.

## 10. Đi từ yêu cầu nghiệp vụ đến mô hình dữ liệu

Khi triển khai một chức năng mới, có thể lần lượt tự hỏi:

1. **Danh tính:** đối tượng nào phải nhận ra là “vẫn chính nó” dù thuộc tính thay đổi? Đó là ứng viên entity.
2. **Giá trị:** thông tin nào được nhận diện qua nội dung và nên thay thế nguyên khối? Đó là ứng viên value object.
3. **Bất biến:** quy tắc nào phải được bảo vệ khi thay đổi nhiều đối tượng cùng nhau? Gom các đối tượng cần sở hữu chung thành một aggregate.
4. **Root:** entity nào chịu trách nhiệm cung cấp các thao tác giữ bất biến? Chỉ truy cập thay đổi aggregate thông qua root.
5. **Ranh giới độc lập:** đối tượng nào có vòng đời riêng? Tham chiếu aggregate khác qua ID thay vì tự động chứa toàn bộ object graph.
6. **Lưu trữ và truy cập:** chọn bảng/cột/FK/ràng buộc; ánh xạ bằng Spring Data JDBC; tạo repository cho root và bổ sung truy vấn phù hợp.

Thứ tự này giúp tránh suy luận ngược từ sơ đồ bảng để ép ra mô hình nghiệp vụ.

## 11. Tự kiểm tra qua một tình huống

Một hệ thống bán hàng có **Giỏ hàng**, **Dòng sản phẩm trong giỏ**, **Địa chỉ nhận hàng** và **Sản phẩm trong catalog**. Hỏi:

1. Dòng sản phẩm trong giỏ có nhất thiết là aggregate root không?
2. Vì sao địa chỉ nhận hàng có thể là value object dù được lưu trong bảng?
3. Giỏ hàng có nên giữ trực tiếp cả aggregate Product, hay chỉ giữ **productId** cùng thông tin cần thiết?
4. Một giỏ hàng lưu trên hai bảng có phải hai aggregate không?

**Gợi ý đối chiếu:** (1) Không; nếu dòng chỉ tồn tại trong giỏ và phải tuân theo quy tắc của giỏ, nó là thành phần được root sở hữu. (2) Bởi identity miền dựa vào nội dung, còn vị trí lưu vật lý không quyết định loại đối tượng. (3) Giữ **productId** thường làm rõ quan hệ giữa hai aggregate độc lập; thông tin snapshot như tên/giá tại thời điểm thêm giỏ là quyết định nghiệp vụ riêng. (4) Không; số bảng không quyết định số aggregate.

Điều cần nắm vững là chuỗi quan hệ: **Entity / Value Object** tạo nên **Aggregate**; **Aggregate Root** bảo vệ bất biến và được truy cập qua **Repository**; **Spring Data JDBC** ánh xạ trạng thái aggregate xuống **bảng và cột quan hệ**. Quyết định ranh giới miền phải xuất phát từ danh tính, quyền sở hữu và quy tắc nghiệp vụ.
