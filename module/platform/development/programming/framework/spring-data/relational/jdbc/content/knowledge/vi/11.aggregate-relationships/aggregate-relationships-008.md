# Quan hệ sở hữu nhiều tầng và thứ tự thao tác trên bảng

Trong Spring Data JDBC, một aggregate có thể chứa nhiều tầng đối tượng được sở hữu: aggregate root quản lý entity con, và entity con có thể tiếp tục quản lý các entity cháu. Khi ánh xạ xuống database, mỗi tầng có thể nằm ở một bảng riêng, được liên kết bằng khóa ngoại trỏ về **khóa chính của đối tượng cha trực tiếp**.

Thiết kế này cần làm rõ hai điều:

- **Sở hữu trong domain:** đối tượng nào quyết định vòng đời và được phép thay đổi đối tượng nào?
- **Phụ thuộc trong database:** bảng nào cần có bản ghi cha trước khi chèn bản ghi con, và bảng nào phải được xóa trước để không vi phạm khóa ngoại?

Bài học dùng ví dụ đơn hàng có nhiều chuyến giao, mỗi chuyến giao có nhiều kiện hàng:

~~~text
PurchaseOrder (aggregate root)
    |
    +-- Shipment (entity con)
    |      |
    |      +-- Parcel (entity cháu)
    |      +-- Parcel
    |
    +-- Shipment
           |
           +-- Parcel
~~~

Toàn bộ cây này thuộc một aggregate nếu các thành phần có cùng ranh giới nhất quán và vòng đời. Khi đó ứng dụng thao tác qua `PurchaseOrderRepository`; không tạo repository riêng cho `Shipment` hoặc `Parcel` chỉ vì chúng được lưu ở các bảng riêng.

## 1. Sở hữu nhiều tầng là gì?

Một quan hệ sở hữu mô tả việc đối tượng cha kiểm soát vòng đời của đối tượng con. Nếu bỏ một đối tượng con khỏi aggregate, Spring Data JDBC xem đối tượng được tham chiếu đó là thành phần cần được loại khỏi dữ liệu aggregate khi lưu.

Ví dụ:

- `PurchaseOrder` sở hữu các `Shipment`.
- Mỗi `Shipment` sở hữu các `Parcel`.
- Một `Parcel` không tồn tại độc lập với chuyến giao của nó.
- Một `Shipment` không có repository riêng nếu nó vẫn chỉ được quản lý thông qua đơn hàng.

Đây là quan hệ một-cha-nhiều-con theo từng tầng. Một đối tượng con thuộc về một chủ sở hữu trong aggregate; không nên dùng cùng một entity làm con của hai root khác nhau.

### 1.1. Sở hữu khác với tham chiếu

Không phải mọi quan hệ giữa hai đối tượng đều là quan hệ sở hữu.

| Quan hệ | Ví dụ | Cách thể hiện |
|---|---|---|
| Root sở hữu child | `PurchaseOrder` → `Shipment` | Nested entity / `@MappedCollection` |
| Child sở hữu grandchild | `Shipment` → `Parcel` | Nested `@MappedCollection` |
| Aggregate tham chiếu aggregate khác | `Shipment` → `Warehouse` | ID hoặc `AggregateReference` |
| Nhiều aggregate cùng dùng một đối tượng | Nhiều đơn dùng chung `Customer` | Aggregate riêng, tham chiếu bằng ID |

Spring Data JDBC giới hạn quan hệ entity được quản lý trong aggregate ở dạng một-một hoặc một-nhiều. Quan hệ nhiều-một hoặc nhiều-nhiều thường là ranh giới giữa các aggregate; khi đó nên tham chiếu bằng ID hoặc `AggregateReference`.

Ví dụ một kho có thể phục vụ nhiều chuyến giao. Không nên nhúng toàn bộ `Warehouse` vào từng `Shipment` như một entity con được sở hữu. Có thể lưu `warehouseId` hoặc dùng `AggregateReference<Warehouse, Long>`.

### 1.2. Vì sao phải có một chủ sở hữu rõ ràng?

Nếu cùng một entity con được hai root cùng tham chiếu, việc xóa hoặc lưu một root có thể làm thay đổi dữ liệu mà root còn lại đang sử dụng. Quy tắc vòng đời sẽ trở nên mơ hồ.

Một aggregate nên có cấu trúc cây sở hữu:

~~~text
Một root
   |
   +-- Child A
   |     +-- Grandchild A1
   |     +-- Grandchild A2
   |
   +-- Child B
         +-- Grandchild B1
~~~

Các liên kết tham chiếu sang aggregate khác là những đường riêng, không phải nhánh ownership trong cây này.

## 2. Từ mô hình Java đến các khóa ngoại

Spring Data JDBC dùng `@MappedCollection` để cấu hình collection được lưu ở bảng riêng. Hai thuộc tính quan trọng:

- `idColumn`: cột khóa ngoại trong bảng con, tham chiếu đến khóa chính của **đối tượng cha trực tiếp**.
- `keyColumn`: cột lưu vị trí của `List` hoặc key của `Map`.

Ở tầng lồng nhau, quy tắc được áp dụng theo từng quan hệ. Nếu `Shipment` có ID riêng, bảng `parcels` có thể chứa `shipment_id` tham chiếu đến `shipments.id`.

~~~text
Java object graph                         Relational tables

PurchaseOrder (id=100)                    purchase_orders
  |                                          id = 100
  +-- Shipment (id=700)                       |
  |      |                                    v
  |      +-- Parcel                           shipments
  |      +-- Parcel                             id = 700
  |                                             order_id = 100
  +-- Shipment                                  |
                                                v
                                              parcels
                                                shipment_id = 700
~~~

Điểm quan trọng: `parcels.shipment_id` tham chiếu `shipments.id`, không tham chiếu thẳng `purchase_orders.id`. Mỗi tầng sử dụng khóa của chủ sở hữu trực tiếp để biểu diễn quan hệ.

## 3. Thiết kế ví dụ ba tầng

Giả sử nghiệp vụ quy định:

- Một đơn hàng có nhiều chuyến giao.
- Mỗi chuyến giao có nhiều kiện hàng.
- Một chuyến giao thuộc duy nhất một đơn hàng.
- Một kiện hàng thuộc duy nhất một chuyến giao.
- Không được thay đổi nội dung chuyến giao sau khi đơn đã đóng.
- Các kiện hàng chỉ có ý nghĩa trong chuyến giao của chúng.

| Kiểu domain | Vai trò | Bảng | Khóa liên kết |
|---|---|---|---|
| `PurchaseOrder` | Aggregate root | `purchase_orders` | `id` |
| `Shipment` | Entity con cấp 1 | `shipments` | `order_id` |
| `Parcel` | Entity con cấp 2 | `parcels` | `shipment_id` |

Ta cấp ID riêng cho `Shipment` vì tầng `Parcel` cần tham chiếu đến khóa chính của `Shipment`. `Parcel` không cần ID riêng trong ví dụ này; cặp `(shipment_id, parcel_no)` xác định một kiện trong chuyến giao.

## 4. Ánh xạ PurchaseOrder sở hữu Shipment

Aggregate root:

~~~java
package com.example.shipping.order.domain;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    @MappedCollection(
            idColumn = "order_id",
            keyColumn = "shipment_no"
    )
    private List<Shipment> shipments = new ArrayList<>();

    private PurchaseOrder() {
    }

    private PurchaseOrder(String status) {
        this.status = status;
    }

    public static PurchaseOrder open() {
        return new PurchaseOrder("OPEN");
    }

    public void addShipment(Shipment shipment) {
        if (!"OPEN".equals(status)) {
            throw new IllegalStateException(
                    "Cannot add a shipment to a closed order"
            );
        }
        shipments.add(shipment);
    }

    public void close() {
        if (shipments.isEmpty()) {
            throw new IllegalStateException(
                    "Cannot close an order without shipments"
            );
        }
        status = "CLOSED";
    }

    public void addParcel(int shipmentIndex, Parcel parcel) {
        if (!"OPEN".equals(status)) {
            throw new IllegalStateException(
                    "Cannot change shipments of a closed order"
            );
        }
        shipments.get(shipmentIndex).addParcel(parcel);
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public List<Shipment> getShipments() {
        return Collections.unmodifiableList(shipments);
    }
}
~~~

`@MappedCollection(idColumn = "order_id")` yêu cầu bảng `shipments` có cột `order_id` để tham chiếu đến `purchase_orders.id`.

Vì thuộc tính là `List`, cần thêm cột key để lưu vị trí phần tử. Ở đây tên cột là `shipment_no`; trong mapping này nó là **vị trí của phần tử trong List**, không tự động là mã chuyến giao nghiệp vụ ổn định.

## 5. Ánh xạ Shipment sở hữu Parcel

Entity con cấp một:

~~~java
package com.example.shipping.order.domain;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("shipments")
public class Shipment {

    @Id
    private Long id;

    private String carrierCode;

    @MappedCollection(
            idColumn = "shipment_id",
            keyColumn = "parcel_no"
    )
    private List<Parcel> parcels = new ArrayList<>();

    private Shipment() {
    }

    public Shipment(String carrierCode) {
        if (carrierCode == null || carrierCode.isBlank()) {
            throw new IllegalArgumentException(
                    "Carrier code is required"
            );
        }
        this.carrierCode = carrierCode;
    }

    void addParcel(Parcel parcel) {
        parcels.add(parcel);
    }

    public Long getId() {
        return id;
    }

    public String getCarrierCode() {
        return carrierCode;
    }

    public List<Parcel> getParcels() {
        return Collections.unmodifiableList(parcels);
    }
}
~~~

Điểm đáng chú ý là `Shipment` có `@Id` dù nó không phải aggregate root. ID này là khóa chính của bản ghi trong bảng `shipments`, đồng thời cho phép bảng `parcels` tham chiếu đến chuyến giao cụ thể.

`@MappedCollection(idColumn = "shipment_id")` nằm trên thuộc tính `parcels` của `Shipment`, vì vậy `shipment_id` trong bảng `parcels` tham chiếu `shipments.id`.

Không nên hiểu `@Id` trên `Shipment` là ứng dụng được phép tạo `ShipmentRepository` và sửa chuyến giao ngoài `PurchaseOrder`. Vai trò aggregate root vẫn thuộc `PurchaseOrder`.

### 5.1. Entity con cấp hai Parcel

~~~java
package com.example.shipping.order.domain;

import java.math.BigDecimal;
import org.springframework.data.relational.core.mapping.Table;

@Table("parcels")
public class Parcel {

    private String trackingCode;
    private BigDecimal weightKg;

    private Parcel() {
    }

    public Parcel(String trackingCode, BigDecimal weightKg) {
        if (trackingCode == null || trackingCode.isBlank()) {
            throw new IllegalArgumentException(
                    "Tracking code is required"
            );
        }
        if (weightKg == null || weightKg.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Weight must be positive"
            );
        }

        this.trackingCode = trackingCode;
        this.weightKg = weightKg;
    }

    public String getTrackingCode() {
        return trackingCode;
    }

    public BigDecimal getWeightKg() {
        return weightKg;
    }
}
~~~

`Parcel` không có `@Id` riêng. Trong ví dụ, nó được xác định bằng vị trí trong `List` của một `Shipment`. Bảng dùng khóa ghép `(shipment_id, parcel_no)`.

Nếu nghiệp vụ cần mã kiện ổn định, được tham chiếu từ hệ thống vận chuyển khác, hãy thêm một mã định danh phù hợp. Có thể dùng `Map<ParcelId, Parcel>` và `keyColumn` để lưu key của Map. Không nên dùng vị trí List làm ID bền vững vì chèn, xóa hoặc sắp xếp có thể làm thay đổi vị trí.

## 6. Schema quan hệ tương ứng

DDL mẫu cho PostgreSQL:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT ck_purchase_order_status
        CHECK (status IN ('OPEN', 'CLOSED', 'CANCELLED'))
);

CREATE TABLE shipments (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    shipment_no INTEGER NOT NULL,
    carrier_code VARCHAR(80) NOT NULL,

    CONSTRAINT fk_shipment_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_shipment_order_position
        UNIQUE (order_id, shipment_no),

    CONSTRAINT ck_shipment_no
        CHECK (shipment_no >= 0)
);

CREATE TABLE parcels (
    shipment_id BIGINT NOT NULL,
    parcel_no INTEGER NOT NULL,
    tracking_code VARCHAR(100) NOT NULL,
    weight_kg NUMERIC(10, 3) NOT NULL,

    CONSTRAINT pk_parcel
        PRIMARY KEY (shipment_id, parcel_no),

    CONSTRAINT fk_parcel_shipment
        FOREIGN KEY (shipment_id)
        REFERENCES shipments(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_parcel_tracking
        UNIQUE (tracking_code),

    CONSTRAINT ck_parcel_no
        CHECK (parcel_no >= 0),

    CONSTRAINT ck_parcel_weight
        CHECK (weight_kg > 0)
);

CREATE INDEX idx_shipments_order_id
    ON shipments(order_id);

CREATE INDEX idx_parcels_shipment_id
    ON parcels(shipment_id);
~~~

Các ràng buộc chính:

- `shipments.order_id` tham chiếu `purchase_orders.id`.
- `parcels.shipment_id` tham chiếu `shipments.id`.
- `shipment_no` là vị trí List trong một đơn.
- `parcel_no` là vị trí List trong một chuyến giao.
- `tracking_code` có unique constraint nếu nghiệp vụ yêu cầu mã vận đơn không trùng toàn hệ thống.

`ON DELETE CASCADE` ở hai khóa ngoại thể hiện chính sách xóa bản ghi con khi bản ghi cha bị xóa. Đây là hành vi ở tầng database. Spring Data JDBC cũng quản lý các thành phần thuộc aggregate khi xóa hoặc lưu root; không nên nhầm `ON DELETE CASCADE` với annotation cascade của JPA.

Trong hệ thống thực tế, cần quyết định có cho phép xóa đơn/chuyến giao vật lý hay chỉ chuyển trạng thái sang `CANCELLED`. Với dữ liệu vận chuyển và kiểm toán, soft delete hoặc lưu lịch sử thường phù hợp hơn xóa vật lý.

## 7. Sơ đồ quan hệ và hướng khóa ngoại

~~~mermaid
erDiagram
    PURCHASE_ORDERS ||--o{ SHIPMENTS : owns
    SHIPMENTS ||--o{ PARCELS : owns

    PURCHASE_ORDERS {
        bigint id PK
        bigint version
        varchar status
    }

    SHIPMENTS {
        bigint id PK
        bigint order_id FK
        integer shipment_no
        varchar carrier_code
    }

    PARCELS {
        bigint shipment_id PK,FK
        integer parcel_no PK
        varchar tracking_code
        numeric weight_kg
    }
~~~

Hướng ownership trong Java đi từ cha xuống con:

~~~text
PurchaseOrder -> Shipment -> Parcel
~~~

Khóa ngoại trong database nằm ở phía bảng con:

~~~text
shipments.order_id -> purchase_orders.id
parcels.shipment_id -> shipments.id
~~~

Đây là mẫu chung cho các quan hệ sở hữu nhiều tầng. Nếu có thêm cấp `ParcelItem`, bảng đó sẽ chứa FK đến khóa chính của `Parcel`, và thao tác ghi phải tiếp tục tuân theo phụ thuộc đó.

## 8. Thứ tự insert khi tạo aggregate mới

Khi lưu một aggregate mới, Spring Data JDBC chèn aggregate root trước, sau đó chèn các entity được tham chiếu trực tiếp và gián tiếp.

Với ví dụ trên, quan hệ khóa ngoại yêu cầu thứ tự:

~~~text
1. INSERT purchase_orders
       |
       | sinh purchase_orders.id
       v
2. INSERT shipments
       |
       | lấy shipments.id
       v
3. INSERT parcels
~~~

Lý do:

- `shipments.order_id` cần giá trị `purchase_orders.id`.
- `parcels.shipment_id` cần giá trị `shipments.id`.
- Nếu chèn `parcels` trước khi có `shipments`, FK không thể được thỏa mãn.

Ví dụ use case:

~~~java
@Transactional
public Long createOrder() {
    PurchaseOrder order = PurchaseOrder.open();

    Shipment shipment = new Shipment("FAST-EXPRESS");
    shipment.addParcel(
            new Parcel("TRACK-001", new BigDecimal("1.250"))
    );
    shipment.addParcel(
            new Parcel("TRACK-002", new BigDecimal("0.850"))
    );

    order.addShipment(shipment);

    PurchaseOrder saved = orderRepository.save(order);
    return saved.getId();
}
~~~

Khi database sinh ID cho root và `Shipment`, Spring Data JDBC sử dụng các giá trị đó để ghi các tầng phía dưới. Dùng đối tượng trả về từ `save(...)` để lấy ID của root đã lưu.

Thứ tự trên là thứ tự phụ thuộc logic giữa các bảng. Không nên dựa vào một thứ tự cố định giữa các bản ghi anh em không có quan hệ phụ thuộc; nếu cần xem chính xác SQL, hãy bật log JDBC hoặc kiểm tra bằng integration test trên database thực tế.

## 9. Thứ tự delete và update khi có khóa ngoại

### 9.1. Xóa aggregate

Nếu database dùng FK thông thường và không có cascade, phải xóa bản ghi phụ thuộc trước bản ghi cha:

~~~text
DELETE parcels
       |
       v
DELETE shipments
       |
       v
DELETE purchase_orders
~~~

Nếu xóa `purchase_orders` trước, database có thể từ chối vì vẫn còn `shipments` tham chiếu. Tương tự, không thể xóa `shipments` khi `parcels` còn tham chiếu.

Với `ON DELETE CASCADE`, database có thể tự xóa các tầng con khi root bị xóa. Tuy nhiên, cần thống nhất chính sách cascade giữa schema và cách Spring Data JDBC quản lý aggregate; không thêm cascade tùy tiện vào những tham chiếu sang aggregate khác.

Spring Data JDBC cung cấp thao tác xóa aggregate qua repository root. Mục tiêu là xóa root cùng toàn bộ entity thuộc aggregate đó. Không cần gọi từng repository con để xóa thủ công khi các entity thực sự là thành phần của cùng aggregate.

### 9.2. Lưu aggregate đã tồn tại

Khi lưu một aggregate root đã tồn tại, cơ chế persistence tiêu chuẩn của Spring Data JDBC:

1. Xóa các entity được tham chiếu trong aggregate.
2. Cập nhật hàng của aggregate root.
3. Chèn lại các entity được tham chiếu theo trạng thái hiện tại.

Với quan hệ nhiều tầng, thao tác xóa phải tôn trọng các khóa ngoại ở các tầng con; các entity được chèn lại phải tuân theo thứ tự cha trước con.

~~~text
DELETE descendants
        |
        v
UPDATE aggregate root
        |
        v
INSERT direct children
        |
        v
INSERT nested children
~~~

Spring Data JDBC không giữ snapshot cũ của toàn bộ aggregate để so sánh từng trường như dirty checking của JPA. Vì vậy, dù chỉ thay đổi một thuộc tính nhỏ ở `Parcel`, việc `save(order)` vẫn có thể dẫn tới xóa và chèn lại các entity được tham chiếu.

Điều này có hệ quả về hiệu năng:

- Aggregate càng lớn, số thao tác SQL có thể càng nhiều.
- Bảng con có unique constraint hoặc FK đến hệ thống khác cần được thiết kế để chịu được chiến lược thay thế này.
- Nếu chỉ muốn cập nhật một bản ghi độc lập thường xuyên, cần xem lại aggregate boundary.
- Nếu cần một thao tác cập nhật đặc biệt, có thể dùng SQL/repository custom có chủ đích, nhưng phải bảo đảm không phá vỡ invariant của root.

### 9.3. Vì sao không thể chỉ UPDATE một bảng con tùy ý?

Nếu `Parcel` là thành phần thuộc `Shipment`, và `Shipment` thuộc `PurchaseOrder`, cập nhật trực tiếp `Parcel` có thể bỏ qua quy tắc của `Shipment` và `PurchaseOrder`.

Ví dụ đơn đã đóng nhưng service cập nhật `parcels.weight_kg` trực tiếp. Database có thể vẫn chấp nhận vì FK và CHECK đều hợp lệ, trong khi nghiệp vụ yêu cầu không được thay đổi nội dung giao hàng sau khi đóng đơn.

Aggregate root bảo vệ quy tắc đó. Việc sử dụng custom SQL phải đi kèm kiểm tra trạng thái và concurrency tương đương.

## 10. Transaction bảo vệ chuỗi thao tác nhiều tầng

Khi một use case thay đổi nhiều bảng trong cùng aggregate, các câu SQL cần được thực hiện trong một transaction để đảm bảo tính nguyên tử.

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository repository;

    public OrderApplicationService(
            PurchaseOrderRepository repository
    ) {
        this.repository = repository;
    }

    @Transactional
    public void addParcel(
            Long orderId,
            int shipmentIndex,
            String trackingCode,
            BigDecimal weightKg
    ) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order not found"));

        order.addParcel(
                shipmentIndex,
                new Parcel(trackingCode, weightKg)
        );

        repository.save(order);
    }
}
~~~

Ví dụ minh họa việc tải root, truy cập thành phần con rồi lưu root. Trong domain thực tế, nên đặt phương thức như `PurchaseOrder.addParcel(...)` để root tự kiểm tra trạng thái đơn và tìm chuyến giao; không để service thay đổi collection bên trong trực tiếp.

Nếu insert ở tầng `parcels` thất bại do trùng `tracking_code`, transaction cần rollback các thao tác trước đó của lần lưu. Nếu không có transaction bao trùm một chuỗi nhiều repository call, có nguy cơ dữ liệu chỉ được ghi một phần.

Spring Data JDBC repository CRUD có transaction semantics riêng; `@Transactional` ở application service giúp xác định rõ ranh giới cho use case phối hợp nhiều thao tác.

### 10.1. Optimistic locking trên aggregate root

Nếu root có `@Version`, Spring Data JDBC kiểm tra version khi cập nhật. Khi một transaction khác đã sửa root, thao tác lưu có thể thất bại với `OptimisticLockingFailureException`.

~~~text
Transaction A                 Transaction B
-------------                 -------------
Read order #100, v4           Read order #100, v4
Add parcel A                  Add parcel B
Save -> root v5
                              Save using v4
                              -> optimistic lock conflict
~~~

Version thuộc root và bảo vệ việc cập nhật aggregate. Nó không thay thế khóa ngoại giữa các tầng, cũng không tự bảo vệ các thao tác SQL tùy chỉnh bỏ qua root.

Khi xung đột xảy ra, ứng dụng cần tải lại và áp dụng chính sách nghiệp vụ; không nên tự động ghi đè trạng thái mới.

## 11. Quan hệ nhiều tầng và quan hệ nhiều-nhiều

Một điểm dễ nhầm là nhìn vào bảng có nhiều khóa ngoại rồi kết luận tất cả các quan hệ đều thuộc một aggregate.

Ví dụ `Shipment` có `Warehouse`:

- Một kho có thể được nhiều chuyến giao sử dụng.
- Một chuyến giao chỉ chọn một kho.
- Kho có vòng đời độc lập với đơn hàng.
- Xóa hoặc đổi đơn hàng không được xóa kho.

Đây là tham chiếu từ aggregate này sang aggregate khác, không phải ownership. Có thể biểu diễn:

~~~java
import org.springframework.data.relational.core.mapping.AggregateReference;

public class Shipment {

    private AggregateReference<Warehouse, Long> warehouse;

    // ...
}
~~~

Và bảng:

~~~sql
ALTER TABLE shipments
    ADD COLUMN warehouse_id BIGINT NOT NULL;

ALTER TABLE shipments
    ADD CONSTRAINT fk_shipment_warehouse
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id);
~~~

`warehouse_id` là tham chiếu đến aggregate khác. Spring Data JDBC không tải và xóa `Warehouse` như một entity con của `PurchaseOrder`.

Nếu có quan hệ nhiều-nhiều giữa hai tập hợp độc lập, ví dụ sản phẩm và chương trình khuyến mãi, thường cần một mô hình liên kết phù hợp (association table hoặc aggregate liên kết riêng). Không nên tạo một đồ thị object tham chiếu vòng quanh rồi kỳ vọng Spring Data JDBC quản lý nó như một aggregate duy nhất.

## 12. Lựa chọn ON DELETE CASCADE, RESTRICT hay soft delete

Chính sách xóa trong database phải phản ánh vòng đời nghiệp vụ.

| Chính sách | Hành vi | Phù hợp khi |
|---|---|---|
| `ON DELETE CASCADE` | Xóa bản ghi con khi cha bị xóa | Thành phần con không có ý nghĩa tồn tại độc lập |
| `ON DELETE RESTRICT` / `NO ACTION` | Chặn xóa cha khi còn bản ghi tham chiếu | Dữ liệu lịch sử phải được giữ hoặc có aggregate khác tham chiếu |
| Soft delete | Giữ bản ghi, chuyển trạng thái | Cần audit, tra cứu lịch sử hoặc tuân thủ quy trình |

Đối với `purchase_orders → shipments → parcels`, cascade có thể hợp lý nếu việc xóa vật lý một đơn đồng nghĩa xóa toàn bộ cây dữ liệu. Nhưng trong hệ thống thật, đơn đã giao thường cần giữ lại để kiểm toán; khi đó chuyển trạng thái hoặc lưu lịch sử có thể phù hợp hơn.

Đối với `shipments → warehouses`, thường không dùng cascade từ shipment sang warehouse vì warehouse không thuộc sở hữu của shipment.

**Không cấu hình cascade chỉ để làm cho một lỗi FK biến mất.** Hãy xác định dữ liệu nào thực sự được phép bị xóa cùng dữ liệu cha.

## 13. Các giới hạn và chi phí của aggregate lồng nhiều tầng

Sở hữu nhiều tầng giúp domain phản ánh cấu trúc nghiệp vụ, nhưng không nên lồng sâu chỉ để tạo một cây object đẹp.

### 13.1. Chi phí ghi tăng theo toàn bộ cây

Nếu một đơn có 30 chuyến giao, mỗi chuyến có 100 kiện, aggregate có thể chứa 3.000 entity con. Một thay đổi nhỏ có thể làm Spring Data JDBC xóa và chèn lại nhiều bản ghi được tham chiếu.

Trước khi đưa thêm một tầng vào aggregate, hãy hỏi:

- Có cần thay đổi tầng đó cùng một use case với root không?
- Có cần giữ invariant xuyên qua tất cả các tầng không?
- Số lượng phần tử tối đa là bao nhiêu?
- Tần suất cập nhật từng tầng ra sao?
- Có hệ thống nào cần cập nhật một phần tử độc lập không?

Nếu một tầng có kích thước lớn và vòng đời độc lập, tách thành aggregate riêng có thể hợp lý hơn.

### 13.2. Loading nhiều tầng có thể dùng nhiều câu SQL

Trong cách tải truyền thống, Spring Data JDBC tải root và các entity được tham chiếu bằng những câu truy vấn riêng. Single Query Loading được bổ sung từ Spring Data JDBC 3.2 nhưng có các điều kiện và giới hạn; nested collections là một trường hợp không được hỗ trợ trong chế độ này theo tài liệu hiện hành.

Vì vậy, đừng giả định aggregate có nhiều tầng luôn được tải bằng một câu SQL. Khi hiệu năng quan trọng, hãy đo số câu query, dữ liệu trả về và cân nhắc projection/read model dành riêng cho màn hình.

### 13.3. Tránh chu trình sở hữu

Không thiết kế:

~~~text
Order -> Shipment -> Parcel -> Order
~~~

Một chu trình object khiến ownership không còn là cây rõ ràng và khó ánh xạ quan hệ. Nếu `Parcel` cần biết mã đơn, hãy truyền thông tin cần thiết hoặc dùng ID tham chiếu ở tầng ứng dụng; không tạo back-reference object để khép vòng.

Spring Data JDBC cũng không khuyến khích giữ thuộc tính back-reference hoặc collection key trong domain object chỉ để phản ánh cột FK do framework quản lý. Nếu thật sự cần các giá trị đó trong object, có thể bổ sung sau khi convert bằng callback và thuộc tính transient.

## 14. Thứ tự thao tác trong schema migration

Thứ tự tạo bảng và constraint trong migration cũng nên tuân theo phụ thuộc:

1. Tạo bảng root `purchase_orders`.
2. Tạo bảng `shipments` có FK đến `purchase_orders`.
3. Tạo bảng `parcels` có FK đến `shipments`.
4. Tạo các index và constraint bổ sung.

Khi rollback migration hoặc xóa schema, thứ tự thường đảo lại:

1. Xóa bảng `parcels`.
2. Xóa bảng `shipments`.
3. Xóa bảng `purchase_orders`.

~~~sql
DROP TABLE parcels;
DROP TABLE shipments;
DROP TABLE purchase_orders;
~~~

Nếu dùng migration framework, nên đặt các thay đổi schema theo version và không sửa migration đã chạy trên môi trường dùng chung. Khi đổi tên cột FK hoặc thay cấu trúc tầng con, cần migration dữ liệu nếu các bản ghi hiện hữu phải được bảo toàn.

DDL tạo bảng không phải là thứ tự SQL khi `repository.save(...)` chạy. Hai quy trình có liên quan đến FK nhưng diễn ra ở hai thời điểm khác nhau.

## 15. Kiểm tra thứ tự thao tác bằng integration test và SQL log

Để xác nhận mapping nhiều tầng, hãy kiểm tra trên đúng database và JDBC driver của ứng dụng.

Các kịch bản có giá trị:

- Lưu đơn mới với một chuyến giao và hai kiện; xác nhận root, child và grandchild được tạo.
- Đọc lại root; xác nhận các tầng được dựng đúng.
- Thêm một kiện rồi lưu; xác nhận trạng thái cuối cùng phản ánh object graph.
- Xóa một chuyến giao khỏi collection rồi lưu; xác nhận các kiện thuộc chuyến đó không còn.
- Xóa aggregate; xác nhận toàn bộ thành phần được xử lý theo chính sách.
- Cố ghi FK không hợp lệ; xác nhận database từ chối và transaction rollback.
- Thử hai transaction cùng cập nhật root có `@Version`; xác nhận conflict được phát hiện.

Có thể bật log SQL của JDBC để quan sát các lệnh `INSERT`, `DELETE` và `UPDATE`. Khi phân tích, hãy so sánh thứ tự với phụ thuộc FK thay vì chỉ đếm số câu SQL.

Không nên viết một unit test chỉ xác nhận annotation tồn tại. Điều cần xác minh là **cấu trúc bảng, dữ liệu liên kết, transaction và hành vi thực tế của repository**.

## 16. Các nhầm lẫn thường gặp

| Nhận định | Cách hiểu đúng |
|---|---|
| Mỗi bảng phải có repository riêng | Repository thường được tạo cho aggregate root; các bảng con có thể được root quản lý |
| `@Id` trên child biến child thành root | `@Id` có thể là PK của bảng child; ownership vẫn do root quyết định |
| `idColumn` luôn trỏ về root ID | Với quan hệ lồng nhau, nó tham chiếu khóa chính của parent entity trực tiếp |
| Chỉ cần chèn root, thứ tự child tùy ý | FK yêu cầu bản ghi cha tồn tại trước bản ghi con |
| Có `ON DELETE CASCADE` thì domain không cần quan tâm vòng đời | Cascade là chính sách database; domain vẫn quyết định được phép xóa hay không |
| `save(root)` chỉ update phần tử vừa đổi | Spring Data JDBC có thể xóa và chèn lại các entity được tham chiếu |
| Quan hệ FK nào cũng là ownership | FK chỉ thể hiện liên kết lưu trữ; phải xét vòng đời và aggregate boundary |
| Transaction chỉ cần cho bảng root | Một lần lưu aggregate có thể tác động nhiều bảng; transaction bảo vệ tính nguyên tử |
| Nested collection luôn tải bằng một query | Cách tải phụ thuộc phiên bản/tính năng; không nên giả định một câu SQL |

## 17. Quy trình thiết kế quan hệ sở hữu nhiều tầng

Khi chuyển một mô hình nghiệp vụ thành Spring Data JDBC mapping, có thể làm theo các bước:

**Bước 1 — Chọn aggregate root.** Xác định điểm vào duy nhất cho thao tác cần nhất quán.

**Bước 2 — Vẽ cây ownership.** Mỗi child có một parent rõ ràng; chỉ thêm tầng khi có ý nghĩa vòng đời.

**Bước 3 — Phân biệt tham chiếu ngoài.** Nhiều-một hoặc nhiều-nhiều thường dùng ID/`AggregateReference`, không nhúng entity được sở hữu.

**Bước 4 — Quyết định ID ở từng tầng.** Tầng nào cần được tầng dưới tham chiếu bằng FK thì cần khóa chính phù hợp. Collection List/Map có key column tương ứng.

**Bước 5 — Ánh xạ từng quan hệ.** Dùng `@MappedCollection(idColumn=..., keyColumn=...)` với tên cột khớp schema. `idColumn` trỏ về PK của parent trực tiếp.

**Bước 6 — Thiết kế PK/FK/UNIQUE/CHECK.** Bảo vệ tính duy nhất, toàn vẹn và thứ tự phụ thuộc.

**Bước 7 — Xác định chính sách delete.** Chọn cascade, restrict hoặc soft delete theo vòng đời thực tế.

**Bước 8 — Dự đoán thứ tự SQL.** Insert từ cha xuống con; xóa theo chiều ngược lại để tôn trọng FK. Với update aggregate hiện hữu, hiểu chiến lược xóa entity tham chiếu, cập nhật root và chèn lại entity.

**Bước 9 — Bọc use case trong transaction.** Bảo đảm chuỗi thao tác nhiều bảng rollback cùng nhau khi lỗi.

**Bước 10 — Đo kích thước aggregate.** Nếu một tầng quá lớn hoặc cần cập nhật độc lập, xem xét tách aggregate và xây dựng quy trình phối hợp.

~~~text
Business rules
      |
      v
Aggregate root
      |
      v
Ownership tree
      |
      +---- Child entity
      |        |
      |        +---- Nested child entity
      |
      +---- External aggregate reference (ID)
      |
      v
Tables + PK/FK/key columns
      |
      v
Insert: parent -> child -> grandchild
Update: delete references -> update root -> reinsert references
Delete: descendants -> ancestors (or DB cascade)
      |
      v
Transaction + integration verification
~~~

## 18. Bài tập tự suy luận

**Tình huống A — Thêm một tầng chi tiết**

Một `PurchaseOrder` có nhiều `Shipment`, mỗi `Shipment` có nhiều `Parcel`, và mỗi `Parcel` có nhiều `ParcelItem`. Cột FK của `ParcelItem` nên tham chiếu bảng nào?

**Gợi ý:** Nếu `Parcel` là parent trực tiếp của `ParcelItem`, FK phải tham chiếu khóa chính của `parcels`, không phải `purchase_orders`.

**Tình huống B — Xóa một Shipment**

Một chuyến giao có 5 kiện. Nếu FK `parcels.shipment_id` không có cascade, có thể xóa hàng `shipments` trước không?

**Gợi ý:** Không khi vẫn còn kiện tham chiếu. Cần xóa các `parcels` trước hoặc cấu hình cascade phù hợp.

**Tình huống C — Thay đổi một Parcel**

Chỉ đổi `weightKg` của một kiện rồi gọi `orderRepository.save(order)`. Có thể giả định chỉ một câu UPDATE ở bảng `parcels` không?

**Gợi ý:** Không. Spring Data JDBC có thể xóa và chèn lại các entity được tham chiếu trong aggregate khi lưu root hiện hữu.

**Tình huống D — Warehouse dùng chung**

Nhiều đơn hàng cùng giao từ một kho. Có nên nhúng `Warehouse` như entity con của mỗi `PurchaseOrder` không?

**Gợi ý:** Không. Kho có vòng đời độc lập và được nhiều aggregate tham chiếu; dùng ID hoặc `AggregateReference`.

**Tình huống E — Đơn đã đóng**

Service cập nhật trực tiếp `parcels.tracking_code` bằng SQL, bỏ qua `PurchaseOrder`. FK vẫn hợp lệ nhưng nghiệp vụ không cho sửa đơn đã đóng. Vấn đề nằm ở đâu?

**Gợi ý:** SQL constraint không thể thay thế invariant của aggregate. Thao tác custom phải kiểm tra trạng thái root và concurrency theo chính sách nghiệp vụ.

## 19. Ghi nhớ

| Thành phần | Vai trò |
|---|---|
| Aggregate root | Điểm vào quản lý toàn bộ cây sở hữu |
| Entity con | Thành phần có vòng đời do parent/root kiểm soát |
| `@MappedCollection.idColumn` | FK đến khóa chính của parent trực tiếp |
| `@MappedCollection.keyColumn` | Vị trí List hoặc key Map |
| `@Id` trên child | Khóa chính cho bảng child khi cần |
| Foreign key | Bảo vệ quan hệ lưu trữ |
| Insert | Root/parent trước, child sau |
| Delete | Child trước parent, hoặc dùng cascade phù hợp |
| Update aggregate hiện hữu | Xóa entity tham chiếu, update root, chèn lại entity |
| `@Transactional` | Bảo vệ tính nguyên tử của use case |
| `@Version` | Phát hiện xung đột cập nhật ở root |
| `AggregateReference` | Tham chiếu một aggregate khác bằng ID |

**Sở hữu nhiều tầng phải rõ cả trong domain lẫn schema.** Trong Java, root kiểm soát child và child kiểm soát grandchild. Trong database, mỗi bảng con giữ FK đến khóa chính của parent trực tiếp. Vì FK tạo ra thứ tự phụ thuộc, insert đi từ cha xuống con và delete đi theo chiều ngược lại. Spring Data JDBC lưu aggregate theo toàn bộ cây tham chiếu, vì vậy cần thiết kế transaction, constraint và kích thước aggregate cùng lúc.

## Tài liệu tham khảo

- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): `@MappedCollection`, back references, nested entities và aggregate references.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): thứ tự insert, update và xóa các entity được tham chiếu khi lưu aggregate.
- [Spring Data Relational — Lifecycle Events](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html): vòng đời thao tác lưu/xóa ở aggregate root và callbacks.

