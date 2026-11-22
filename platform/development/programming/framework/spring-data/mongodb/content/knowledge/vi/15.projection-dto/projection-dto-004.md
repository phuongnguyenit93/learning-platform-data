# Projection lồng nhau và giới hạn dữ liệu được tải

> **Chương:** Projection và DTO  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document, truy vấn bằng `MongoTemplate` hoặc repository, thiết kế truy vấn và kiểm thử hiệu năng.  
> **Mục tiêu:** Phân biệt nested interface projection với class-based DTO, biết khi nào Spring Data có thể giới hạn trường truy vấn, viết field projection tường minh ở MongoDB và tránh nhầm việc ẩn trường trong API với việc không tải trường đó từ database.

## 1. Projection giải quyết vấn đề gì?

Một document đơn hàng có thể chứa rất nhiều thông tin: khách hàng, địa chỉ giao hàng, dòng sản phẩm, ghi chú nội bộ, lịch sử thao tác. Nhưng màn hình danh sách thường chỉ cần **mã đơn hàng, trạng thái, tên khách hàng và thành phố**.

Nếu mỗi request đọc toàn bộ document rồi mới chuyển thành DTO nhỏ, ứng dụng vẫn có thể:

- Nhận các trường không cần thiết qua kết nối MongoDB.
- Giải mã BSON và tạo object Java cho dữ liệu dư thừa.
- Tăng dung lượng heap, tải GC và thời gian xử lý, đặc biệt với mảng lớn.
- Vô tình để lộ thông tin khi log hoặc serialize nhầm một entity đầy đủ.

**Projection** là kỹ thuật chỉ lấy hoặc chỉ trình bày một tập thuộc tính của entity. Trong Spring Data MongoDB, cần tách ba tầng:

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **MongoDB field projection** | Server trả về những trường BSON nào? | `{ state: 1, "customer.name": 1 }` |
| **Spring Data projection** | Repository cung cấp hình dạng Java nào? | `OrderCardView`, `OrderCardDto` |
| **API DTO/JSON** | Client nhìn thấy những trường nào? | `{ "id": "o401", "customer": { "name": "An" } }` |

Một DTO không chứa email **không tự chứng minh** email chưa được đọc từ MongoDB. Đặc biệt với projection lồng nhau, proxy ở Java có thể chỉ expose `customer.name`, trong khi query vẫn tải cả object `customer` hoặc dữ liệu khác tùy hình thức projection và cách tối ưu truy vấn.

Mục tiêu của bài là hiểu cả **hình dạng kết quả** lẫn **khối lượng dữ liệu thật sự được tải**.

## 2. Dữ liệu thử nghiệm và mô hình domain

Các lệnh `mongosh` dưới đây chỉ dùng trên database thực hành được cô lập. Tạo một collection dành riêng cho bài:

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_projection_demo_004;

orders.insertMany([
  {
    _id: "o401",
    state: "PAID",
    customer: {
      name: "An",
      email: "an@example.invalid",
      phone: "0000000001",
      segment: "VIP"
    },
    shippingAddress: {
      city: "Hà Nội",
      street: "Phố A",
      postalCode: "100000",
      deliveryInstructions: "Giao giờ hành chính"
    },
    lines: [
      { sku: "A", quantity: 1, unitPriceVnd: 120000, internalCostVnd: 80000 },
      { sku: "B", quantity: 8, unitPriceVnd: 20000, internalCostVnd: 9000 }
    ],
    internalNotes: "Thông tin chỉ dành cho nhân viên",
    auditTrail: [
      "CREATED", "CONFIRMED", "PACKED", "PAID"
    ],
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "o402",
    state: "PAID",
    customer: {
      name: "Bình",
      email: "binh@example.invalid",
      phone: "0000000002",
      segment: "STANDARD"
    },
    shippingAddress: {
      city: "Hồ Chí Minh",
      street: "Đường B",
      postalCode: "700000",
      deliveryInstructions: "Gọi trước khi giao"
    },
    lines: [
      { sku: "A", quantity: 6, unitPriceVnd: 120000, internalCostVnd: 80000 }
    ],
    internalNotes: "Ghi chú xử lý nội bộ",
    auditTrail: ["CREATED", "PAID"],
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "o403",
    state: "DRAFT",
    customer: { name: "Chi", email: "chi@example.invalid" },
    lines: [],
    internalNotes: "Chưa xác nhận địa chỉ",
    auditTrail: ["CREATED"],
    createdAt: ISODate("2026-10-03T08:00:00Z")
    // Không có shippingAddress.
  }
]);
~~~

Kết quả của các truy vấn minh họa được tính từ ba document trên, trước khi thay đổi dữ liệu. `_id` là **BSON string**. Nếu chạy lại `insertMany` trên collection cũ sẽ gặp lỗi trùng `_id`; hãy dùng một database/collection test mới khi cần reset, không xóa collection của ứng dụng thật.

### 2.1. Domain Java tương ứng

Mỗi class sau nằm trong file riêng thuộc package `com.example.projections`. Trong ví dụ này, các object khách hàng, địa chỉ và dòng hàng **được nhúng**, không phải các tài liệu ở collection khác.

~~~java
// CustomerInfo.java
package com.example.projections;

public class CustomerInfo {
    private String name;
    private String email;
    private String phone;
    private String segment;

    protected CustomerInfo() { }

    public String getName() { return name; }
    public String getEmail() { return email; }
    public String getPhone() { return phone; }
    public String getSegment() { return segment; }
}
~~~

~~~java
// ShippingAddress.java
package com.example.projections;

public class ShippingAddress {
    private String city;
    private String street;
    private String postalCode;
    private String deliveryInstructions;

    protected ShippingAddress() { }

    public String getCity() { return city; }
    public String getStreet() { return street; }
    public String getPostalCode() { return postalCode; }
    public String getDeliveryInstructions() {
        return deliveryInstructions;
    }
}
~~~

~~~java
// OrderLine.java
package com.example.projections;

public class OrderLine {
    private String sku;
    private int quantity;
    private long unitPriceVnd;
    private long internalCostVnd;

    protected OrderLine() { }

    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
    public long getUnitPriceVnd() { return unitPriceVnd; }
    public long getInternalCostVnd() { return internalCostVnd; }
}
~~~

~~~java
// OrderDocument.java
package com.example.projections;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_projection_demo_004")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;
    private String state;
    private CustomerInfo customer;
    private ShippingAddress shippingAddress;
    private List<OrderLine> lines;
    private String internalNotes;
    private List<String> auditTrail;
    private Instant createdAt;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getState() { return state; }
    public CustomerInfo getCustomer() { return customer; }
    public ShippingAddress getShippingAddress() {
        return shippingAddress;
    }
    public List<OrderLine> getLines() { return lines; }
    public String getInternalNotes() { return internalNotes; }
    public List<String> getAuditTrail() { return auditTrail; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

`@MongoId(FieldType.STRING)` giúp `_id` luôn là BSON string, kể cả khi có giá trị tình cờ là chuỗi 24 ký tự hex. `CustomerInfo`, `ShippingAddress` và `OrderLine` không cần `@Document` vì chúng chỉ làm thành phần nhúng của `OrderDocument`.

## 3. Closed interface projection: chỉ khai báo những getter cần dùng

Với Spring Data, một **closed interface projection** là interface mà các accessor của nó có thể được suy ra từ thuộc tính của aggregate/domain. Ví dụ màn hình danh sách cần:

~~~java
// CustomerNameView.java
package com.example.projections;

public interface CustomerNameView {
    String getName();
}
~~~

~~~java
// AddressCityView.java
package com.example.projections;

public interface AddressCityView {
    String getCity();
}
~~~

~~~java
// LineBriefView.java
package com.example.projections;

public interface LineBriefView {
    String getSku();
    int getQuantity();
}
~~~

~~~java
// OrderCardView.java
package com.example.projections;

import java.util.List;

public interface OrderCardView {
    String getId();
    String getState();
    CustomerNameView getCustomer();
    AddressCityView getShippingAddress();
    List<LineBriefView> getLines();
}
~~~

`OrderCardView` là projection **lồng nhau**:

~~~text
OrderCardView
├── id
├── state
├── customer: CustomerNameView
│   └── name
├── shippingAddress: AddressCityView
│   └── city
└── lines: List<LineBriefView>
    ├── sku
    └── quantity
~~~

Nó không khai báo `customer.email`, `customer.phone`, `shippingAddress.street`, `lines.internalCostVnd` hoặc `internalNotes`. Những thuộc tính ấy vì thế **không nằm trong API của projection**. Tuy nhiên, việc **không expose getter** không đồng nghĩa server chắc chắn chỉ truyền về các leaf field được khai báo.

### 3.1. Repository trả về projection thay vì entity

~~~java
// OrderRepository.java
package com.example.projections;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    List<OrderCardView> findByState(String state);

    Page<OrderCardView> findByState(
        String state, Pageable pageable
    );

    <T> Optional<T> findById(String id, Class<T> type);
}
~~~

Sử dụng:

~~~java
List<OrderCardView> cards =
    repository.findByState("PAID");

for (OrderCardView card : cards) {
    System.out.println(card.getId());
    System.out.println(card.getCustomer().getName());
    System.out.println(card.getShippingAddress().getCity());
}
// Trên dữ liệu gốc: o401/An/Hà Nội và o402/Bình/Hồ Chí Minh.
~~~

Spring Data tạo projection ở lớp repository, thường bằng proxy cho interface, giúp tầng gọi code chỉ phụ thuộc những accessor đã định nghĩa. Nếu một trường nhúng bị thiếu như `shippingAddress` của `o403`, `getShippingAddress()` có thể là `null`; tránh dereference trực tiếp mà không kiểm tra.

### 3.2. Có phải closed projection luôn làm MongoDB chỉ tải từng getter?

**Không nên giả định như vậy.** Spring Data MongoDB có thể dùng metadata của projection để tối ưu danh sách trường ở query, nhưng phạm vi tối ưu còn phụ thuộc:

- Loại projection (closed, open, dynamic, class/DTO).
- Trường là thuộc tính **top-level** hay một object/mảng lồng nhau.
- Query do repository tạo, query khai báo thủ công hoặc `MongoTemplate`.
- Phiên bản Spring Data MongoDB và quy tắc ánh xạ đang được dùng.

Với nested projection, framework có thể cần tải **toàn bộ thuộc tính gốc** như `customer`, `shippingAddress` hoặc `lines` để tạo nested proxy, dù nested interface chỉ đưa ra một số getter. Tài liệu về projection của Spring Data lưu ý giới hạn tối ưu với thuộc tính lồng nhau. Vì vậy cần phân biệt:

~~~text
CustomerNameView chỉ có getName()
          ≠
Đảm bảo MongoDB chỉ truyền customer.name
~~~

Nếu yêu cầu giảm payload là điều kiện quan trọng về hiệu năng hay bảo mật, hãy khai báo **field selection tường minh** (`@Query(fields=...)`/`MongoTemplate`/aggregation), sau đó kiểm chứng BSON và câu lệnh được thực thi.

## 4. MongoDB field projection: giới hạn BSON ngay tại server

### 4.1. Từ truy vấn đầy đủ đến chỉ chọn trường

Truy vấn không có field projection:

~~~javascript
orders.find({ state: "PAID" });
~~~

thông thường trả về **toàn bộ trường** của `o401` và `o402`, gồm `email`, `phone`, `internalNotes`, `auditTrail` và mọi phần tử `lines`.

Nếu chỉ cần ID, state, tên khách hàng và thành phố:

~~~javascript
orders.find(
  { state: "PAID" },
  {
    _id: 1,
    state: 1,
    "customer.name": 1,
    "shippingAddress.city": 1
  }
);
~~~

Với `o401`, cấu trúc BSON trả về có ý nghĩa tương đương:

~~~javascript
{
  _id: "o401",
  state: "PAID",
  customer: { name: "An" },
  shippingAddress: { city: "Hà Nội" }
}
~~~

Không có `customer.email`, `customer.phone`, `shippingAddress.street`, `lines` hay `internalNotes` trong kết quả. Đây là bằng chứng **server trả về ít dữ liệu hơn**, chứ không chỉ là DTO Java ẩn bớt getter.

### 4.2. Quy tắc include/exclude

MongoDB field projection thường dùng `1` để include và `0` để exclude. Có một số quy tắc quan trọng:

- Nếu không chỉ định projection, MongoDB trả về các trường phù hợp của document đầy đủ.
- `_id` **được include mặc định** ngay cả khi bạn chỉ include một số trường khác, trừ khi đặt `_id: 0`.
- Không trộn **include** và **exclude** cho các trường thông thường trong cùng projection; `_id` là ngoại lệ phổ biến.
- Dot notation `"customer.name": 1` cho phép chỉ đưa trường con cần thiết vào BSON kết quả.
- Projection không sửa document gốc; nó chỉ ảnh hưởng dữ liệu trả về từ truy vấn.

Ví dụ không cần `_id`:

~~~javascript
orders.find(
  { state: "PAID" },
  { _id: 0, state: 1, "customer.name": 1 }
);
~~~

Tuy nhiên, nếu DTO cần phân biệt mỗi order bằng ID, đừng loại `_id` một cách máy móc. Một DTO không có ID có thể phù hợp cho thống kê nhưng không phù hợp cho API xem chi tiết hoặc phân trang có khóa ổn định.

### 4.3. Include một object cha khác với include đường dẫn con

~~~javascript
// Lấy toàn bộ thông tin khách hàng trong embedded object.
orders.find(
  { _id: "o401" },
  { customer: 1 }
);

// Chỉ lấy tên khách hàng trong embedded object.
orders.find(
  { _id: "o401" },
  { "customer.name": 1 }
);
~~~

Truy vấn thứ nhất mang theo cả `email`, `phone` và `segment`; truy vấn thứ hai chỉ mang `customer.name` (và `_id` mặc định). Chính khác biệt này giải thích vì sao “projection lồng nhau ở Java” và “field projection lồng nhau ở MongoDB” không nên được đánh đồng.

## 5. Giới hạn trường qua `@Query(fields = ...)`

Spring Data MongoDB cho phép chỉ định trường cần lấy trong một repository method bằng thuộc tính `fields` của `@Query`.

### 5.1. Một interface gọn khớp trường lựa chọn

~~~java
// OrderLightCard.java
package com.example.projections;

public interface OrderLightCard {
    String getId();
    String getState();
    CustomerNameView getCustomer();
    AddressCityView getShippingAddress();
}
~~~

Thêm phương thức sau vào **cùng `OrderRepository` đã khai báo ở mục 3.1**:

~~~java
import org.springframework.data.mongodb.repository.Query;

@Query(
    value = "{ 'state': ?0 }",
    fields = "{ '_id': 1, 'state': 1, " +
             "  'customer.name': 1, 'shippingAddress.city': 1 }"
)
List<OrderLightCard> findLightCardsByState(String state);
~~~

Lời gọi:

~~~java
List<OrderLightCard> lightCards =
    repository.findLightCardsByState("PAID");
~~~

Ở đây:

1. `value` biểu diễn điều kiện chọn document (lọc `state`).
2. `fields` mô tả **server-side field projection**: chỉ các trường liệt kê được trả về.
3. Kiểu trả về `OrderLightCard` định nghĩa giao diện Java tiêu thụ kết quả.

Giá trị `?0` được Spring Data bind từ tham số `state`, không cần nối trực tiếp input của người dùng vào chuỗi JSON. Nếu model dùng `@Field` đổi tên BSON của một thuộc tính, cần kiểm tra cả mapping và JSON query để bảo đảm đường dẫn thực tế chính xác.

### 5.2. Vì sao cần cả `fields` lẫn interface?

`fields` kiểm soát **BSON trả về**; interface kiểm soát **hình dạng dữ liệu Java**. Có thể coi chúng là hai hợp đồng:

~~~text
MongoDB:
  state, customer.name, shippingAddress.city, _id
                         ↓
Spring Data:
  OrderLightCard / CustomerNameView / AddressCityView
                         ↓
API:
  DTO được serialize theo quy tắc của ứng dụng
~~~

Nếu `fields` bỏ sót một thuộc tính mà projection cần, property có thể trở thành `null` hoặc không có dữ liệu phù hợp để khởi tạo. **Đừng cấu hình field mask khác với hợp đồng DTO rồi im lặng điền default** khiến người dùng tưởng dữ liệu đã tồn tại.

### 5.3. Khi nào không nên đặt `fields` cố định?

Với màn hình có cột động hoặc nhiều kiểu người dùng cần trường khác nhau, một phương thức repository chứa field mask cố định có thể trở nên khó bảo trì. Các lựa chọn:

- Tạo vài projection cố định theo use case (`OrderListCard`, `OrderDetailCard`).
- Dùng `MongoTemplate` và tạo `Query.fields()` theo một **allowlist** trường đã định nghĩa.
- Dùng aggregation nếu cần tính/đổi cấu trúc dữ liệu, lọc phần tử mảng hoặc gộp nhiều collection.

Không cho client truyền nguyên JSON projection/filter tùy ý vào database nếu ứng dụng cần kiểm soát quyền đọc và giới hạn độ phức tạp của truy vấn.

## 6. `MongoTemplate`: kiểm soát chính xác các trường tải về

Khi truy vấn cần điều kiện hoặc danh sách trường tùy biến, `MongoTemplate` cho phép cấu hình field projection:

~~~java
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// Trong một @Service đã inject MongoTemplate template:
Query query = Query.query(
    Criteria.where("state").is("PAID")
);
query.fields()
    .include("_id")
    .include("state")
    .include("customer.name")
    .include("shippingAddress.city");

List<Document> rawCards = template.find(
    query,
    Document.class,
    "orders_projection_demo_004"
);
~~~

Trong ví dụ này, kết quả được đọc vào `org.bson.Document` để bạn có thể trực tiếp quan sát những trường **thực sự có mặt** trong BSON sau khi MongoDB xử lý field projection. Khác với việc chỉ chuyển `OrderDocument` thành một DTO sau khi đọc đầy đủ, đây là yêu cầu gửi tới server để giảm field list.

### 6.1. Cấu trúc object nhúng vẫn được bảo toàn

Nếu include `"customer.name"`, MongoDB trả về một object `customer` có property `name`; nó **không biến thành** field phẳng mang tên `"customer.name"` trong JSON kết quả. Vì vậy DTO lồng nhau là một lựa chọn hợp lý cho response.

~~~java
Document first = rawCards.get(0);
Document customer = first.get("customer", Document.class);
String customerName = customer.getString("name");
~~~

Code trên minh họa trên `o401`/`o402` là những document có `customer.name`. Trường hợp `customer` missing hoặc null cần kiểm tra trước khi gọi `getString`.

### 6.2. Projection có thể làm entity chỉ còn được tải một phần

Cũng có thể dùng:

~~~java
OrderDocument partial = template.findOne(
    query,
    OrderDocument.class
);
~~~

Nhưng `partial` lúc này **không phải entity đầy đủ**: những trường không được server gửi về có thể là `null`, giá trị mặc định Java, hoặc không được populate tùy kiểu thuộc tính và constructor.

**Cảnh báo quan trọng:** Đừng đọc entity với field mask một phần rồi gọi `repository.save(partial)` như một cách cập nhật bình thường. Với MongoDB, `save` có thể ghi thay thế document, khiến trường chưa tải bị mất hoặc trở về default; `@Version` cũng có thể ảnh hưởng đến kết quả. Đối tượng đọc một phần nên được xem như **read model**, không phải aggregate để ghi lại.

Khi chỉ muốn sửa một vài trường, dùng `MongoTemplate.updateFirst()`/`updateMulti()` với `Update.set` hoặc các operator phù hợp. Khi cần đọc để sửa toàn bộ, tải entity đầy đủ và áp dụng optimistic locking nếu nghiệp vụ cần.

### 6.3. Giới hạn trường theo allowlist

Một service có thể cho phép chọn một số trường, nhưng phải kiểm soát danh sách ở server:

~~~java
import java.util.Set;
import org.springframework.data.mongodb.core.query.Query;

Set<String> allowed = Set.of(
    "_id",
    "state",
    "customer.name",
    "shippingAddress.city",
    "createdAt"
);

Query query = Query.query(Criteria.where("state").is("PAID"));

for (String requestedField : requestedFields) {
    if (!allowed.contains(requestedField)) {
        throw new IllegalArgumentException("Unsupported projection field");
    }
    query.fields().include(requestedField);
}
~~~

`requestedFields` ở đây là danh sách đã được giới hạn kích thước do tầng API chuyển vào; phần minh họa giả định `Criteria` đã import. Không cho chọn `customer.email` hay `internalNotes` nếu vai trò người gọi không được phép. Đặt limit/pagination và tránh để người dùng tạo truy vấn quá rộng.

## 7. Mảng document nhúng: giới hạn field **không** đồng nghĩa giới hạn phần tử

Đây là giới hạn đặc biệt dễ nhầm khi projection lồng nhau bao gồm `List<LineBriefView>`.

### 7.1. Chỉ include `lines.sku`

~~~javascript
orders.find(
  { _id: "o401" },
  {
    _id: 0,
    "lines.sku": 1
  }
);
~~~

Kết quả có ý nghĩa tương đương:

~~~javascript
{
  lines: [
    { sku: "A" },
    { sku: "B" }
  ]
}
~~~

MongoDB đã loại `quantity`, `unitPriceVnd`, `internalCostVnd` **khỏi từng phần tử**, nhưng nó vẫn trả về **cả hai phần tử** trong mảng. Việc chọn **trường** trong mảng và việc chọn **phần tử** của mảng là hai câu hỏi khác nhau.

### 7.2. Filter `$elemMatch` không tự rút ngắn mảng kết quả

~~~javascript
orders.find({
  lines: {
    $elemMatch: {
      sku: "B",
      quantity: { $gte: 5 }
    }
  }
});
~~~

Trên dữ liệu gốc, truy vấn trên chọn `o401` nhờ dòng B × 8, nhưng **document trả về vẫn chứa cả mảng `lines`** nếu không có field projection riêng. `$elemMatch` trong **filter** chọn document; nó không có nghĩa server tự cắt mảng thành các phần tử khớp.

### 7.3. Projection `$elemMatch` chỉ trả phần tử khớp đầu tiên

~~~javascript
orders.find(
  { _id: "o401" },
  {
    lines: {
      $elemMatch: {
        sku: "B",
        quantity: { $gte: 5 }
      }
    }
  }
);
~~~

Ở phần `lines` của kết quả, MongoDB chỉ trả **phần tử đầu tiên** đáp ứng `$elemMatch`. Nó vẫn có thể mang những field khác của phần tử đó như `internalCostVnd`. Nếu mục tiêu là trả **tất cả dòng thỏa điều kiện nhưng chỉ giữ một số field**, dùng aggregation `$filter` kết hợp `$map`.

### 7.4. `$slice` rút số phần tử nhưng không rút field bên trong

~~~javascript
orders.find(
  { _id: "o401" },
  { lines: { $slice: 1 } }
);
~~~

`$slice: 1` lấy **một phần tử đầu** của mảng `lines`, nhưng không tự loại `unitPriceVnd` hay `internalCostVnd` khỏi phần tử ấy. Muốn giới hạn đồng thời phần tử **và** trường, phải chọn projection/aggregation đủ biểu đạt. `$slice` cũng không tương đương phân trang tất cả dòng hàng cho một hệ thống có mảng lớn; cân nhắc mô hình hóa dữ liệu khác khi cần phân trang từng line.

### 7.5. Aggregation `$filter` + `$map`: chọn cả phần tử và field

Yêu cầu: với order đã thanh toán, chỉ trả các dòng có `quantity >= 5`, và mỗi dòng chỉ chứa `sku` cùng `quantity`.

~~~javascript
orders.aggregate([
  { $match: { state: "PAID" } },
  {
    $project: {
      _id: 1,
      state: 1,
      "customer.name": 1,
      lines: {
        $map: {
          input: {
            $filter: {
              input: "$lines",
              as: "line",
              cond: { $gte: ["$$line.quantity", 5] }
            }
          },
          as: "line",
          in: {
            sku: "$$line.sku",
            quantity: "$$line.quantity"
          }
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả kỳ vọng:

~~~javascript
[
  {
    _id: "o401",
    state: "PAID",
    customer: { name: "An" },
    lines: [{ sku: "B", quantity: 8 }]
  },
  {
    _id: "o402",
    state: "PAID",
    customer: { name: "Bình" },
    lines: [{ sku: "A", quantity: 6 }]
  }
]
~~~

Ở đây:

- `$match` lọc **order**.
- `$filter` lọc **phần tử mảng** theo `quantity`.
- `$map` dựng lại mỗi phần tử chỉ có **hai field**.
- `$project` giới hạn field của **document kết quả**.

Với dữ liệu thực có `lines` null/missing, cần chuẩn hóa về mảng, ví dụ bằng `$ifNull: ["$lines", []]`; nếu không, các operator mảng có quy tắc riêng với null hoặc input sai kiểu. Spring Data MongoDB có Aggregation API và `MongoTemplate.aggregate(...)` để chạy pipeline tương tự khi cần DTO tính toán.

## 8. Class-based DTO và record: không giống nested interface proxy

Interface projection dùng proxy để expose các getter. **Class-based projection** trả về DTO/record được khởi tạo theo constructor, không dùng cùng cơ chế proxy lồng nhau.

### 8.1. DTO phẳng

~~~java
// OrderHeadlineDto.java
package com.example.projections;

public record OrderHeadlineDto(String id, String state) {
}
~~~

Trong `OrderRepository`, thêm phương thức:

~~~java
List<OrderHeadlineDto> findHeadlineByState(String state);
~~~

Với Spring Data hỗ trợ DTO projection, tên tham số constructor của class/record được dùng để suy ra các thuộc tính cần ánh xạ. Record là một lựa chọn thuận tiện nhờ constructor canonical rõ ràng. Nếu class có nhiều constructor, cần một constructor thích hợp và có thể dùng `@PersistenceCreator` theo quy tắc mapping.

**Lưu ý:** một DTO có hai trường không có nghĩa mọi đường truy vấn/phiên bản đều chọn chính xác hai field trên server. Kiểm tra câu lệnh và field mask khi vấn đề payload quan trọng.

### 8.2. DTO lồng nhau không tự hoạt động như nested interface projection

~~~java
public record CustomerNameDto(String name) { }

public record OrderCardDto(
    String id,
    String state,
    CustomerNameDto customer
) { }
~~~

Không nên giả định repository tự sinh **nested class-based projection** từ các class này giống như với `CustomerNameView` trong `OrderCardView`. Class-based projections không có nested proxying như interface projections; nếu cần kết quả lồng nhau chính xác, cân nhắc:

- Nested **interface** projection cho read model đơn giản.
- MongoDB field projection/aggregation rồi ánh xạ `Document` sang DTO bằng mapper tường minh.
- DTO chuyên biệt nhận trực tiếp kết quả aggregation khi shape và constructor tương thích.

Đối với kết quả tổng hợp, ví dụ `OrderCardDto` có `CustomerNameDto`, một mapper tường minh còn giúp kiểm soát null/missing và quyền xuất dữ liệu.

### 8.3. Open projection với `@Value`

Một interface dùng SpEL để tính thuộc tính:

~~~java
package com.example.projections;

import org.springframework.beans.factory.annotation.Value;

public interface OrderDisplayOpenView {
    @Value("#{target.customer != null ? " +
           "target.customer.name + ' / ' + target.state " +
           ": target.state}")
    String getDisplayLabel();
}
~~~

Đây là **open projection**: biểu thức SpEL có thể truy cập các thuộc tính tùy ý của `target`. Vì framework không thể suy chắc toàn bộ field mà biểu thức sẽ dùng, nó thường **không áp dụng tối ưu field selection kiểu closed projection**. Đừng chọn open projection khi mục tiêu chính là bảo đảm MongoDB chỉ tải vài trường BSON.

Nếu logic hiển thị phức tạp, thay vì SpEL gọi nhiều thuộc tính/hàm, hãy cân nhắc tính kết quả ở service sau khi đã truy vấn theo **field mask rõ ràng** hoặc dùng aggregation trên server.

### 8.4. Dynamic projection

Với phương thức generic:

~~~java
<T> List<T> findByState(String state, Class<T> type);
~~~

Bạn có thể chọn hình dạng kết quả ở từng lời gọi:

~~~java
List<OrderCardView> cards =
    repository.findByState("PAID", OrderCardView.class);

List<OrderHeadlineDto> headlines =
    repository.findByState("PAID", OrderHeadlineDto.class);
~~~

Spring Data nhận diện tham số `Class<T>` dùng để chọn projection động. Kiểu trả về và phương thức projection cụ thể có thể ảnh hưởng khả năng tối ưu truy vấn. Dynamic projection **không** tự tạo ràng buộc quyền truy cập: đừng cho client tùy chọn `OrderDocument.class` chỉ vì endpoint nhận tên kiểu DTO.

## 9. Nested projection và các trường hợp dữ liệu đặc biệt

### 9.1. Object nhúng missing hoặc null

`o403` không có `shippingAddress`. Một projection:

~~~java
OrderCardView draft = repository.findById(
    "o403", OrderCardView.class
).orElseThrow();

AddressCityView address = draft.getShippingAddress();
String city = address == null ? null : address.getCity();
~~~

Không nên gọi ngay `draft.getShippingAddress().getCity()` vì object nhúng có thể thiếu. `null` tại phía Java cũng không phân biệt chắc chắn dữ liệu BSON `null` với trường không tồn tại; nếu nghiệp vụ cần phân biệt, hãy truy vấn BSON thô hoặc dùng aggregation `$type`.

### 9.2. Mảng lớn và nested `List<...>`

`List<LineBriefView> getLines()` chỉ giới hạn **interface Java** của từng dòng hàng. Với hàng nghìn phần tử, ngay cả khi mỗi dòng chỉ expose hai getter, ứng dụng vẫn có thể phải tạo ra **hàng nghìn giá trị/proxy**, và việc tải mảng gốc có thể tốn tài nguyên.

Khi màn hình chỉ cần “tổng số dòng” hoặc “năm dòng đầu tiên”, lựa chọn tốt hơn có thể là:

- Lưu một field tổng hợp như `lineCount` được cập nhật nhất quán.
- Dùng aggregation `$size` khi dữ liệu và index cho phép.
- Dùng `$slice` hoặc `$filter`/`$map` cho trường hợp cụ thể.
- Tách dòng hàng thành collection riêng nếu cần tìm kiếm, sắp xếp và phân trang độc lập ở quy mô lớn.

Projection không khắc phục được mọi nhược điểm của mô hình lưu trữ một mảng quá lớn trong một document.

### 9.3. Tham chiếu `@DBRef`/`@DocumentReference` khác embedded document

Nested projection của một **object nhúng** khác với việc resolve **document reference**:

- Với embedded object, dữ liệu nằm trong cùng một BSON document.
- Với `@DBRef`/`@DocumentReference`, Spring Data có thể phải thực hiện truy vấn **đến document khác** để resolve giá trị; lazy loading và số round-trip là vấn đề riêng.
- Một getter nested không bảo đảm framework tự biến tham chiếu thành server-side `$lookup` hoặc tối ưu chỉ vài field của target reference.

Nếu màn hình cần dữ liệu từ nhiều collection, cân nhắc tự viết truy vấn phù hợp (hai lần đọc, projection read model riêng, hoặc `$lookup` trong aggregation). Đừng xem nested interface projection là giải pháp thay thế toàn diện cho thiết kế truy vấn liên collection.

## 10. Giới hạn dữ liệu tải về và hiệu năng thực tế

### 10.1. Bốn chi phí cần quan sát

~~~text
MongoDB lưu BSON document
          |
          | (1) Đọc document / index trong database
          v
MongoDB áp dụng filter + projection
          |
          | (2) Truyền BSON qua network
          v
MongoDB Java Driver + Spring Data Converter
          |
          | (3) Decode / materialize Java object hoặc proxy
          v
Service / HTTP JSON serialization
          |
          | (4) Tạo response trả client
          v
Client
~~~

Một projection có thể giảm tải mạng và việc tạo object. Nhưng **không mặc định** server chỉ cần đọc một phần vật lý của document từ storage để tạo kết quả. Nếu query vẫn phải fetch document đầy đủ rồi mới áp dụng projection, `totalDocsExamined` có thể không giảm.

### 10.2. Đo kết quả truy vấn với `explain`

~~~javascript
// So sánh một truy vấn trả đầy đủ document.
orders.find({ state: "PAID" })
  .explain("executionStats");

// Với cùng filter, nhưng giới hạn các trường.
orders.find(
  { state: "PAID" },
  {
    _id: 1,
    state: 1,
    "customer.name": 1,
    "shippingAddress.city": 1
  }
).explain("executionStats");
~~~

Quan sát `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `nReturned`. Để đo tải mạng và decode Java, còn cần metric của driver/ứng dụng, kích thước BSON/response và benchmark có dữ liệu đại diện; `explain` không trực tiếp thay thế phép đo end-to-end.

### 10.3. Index và covered query

Ví dụ:

~~~javascript
orders.createIndex({
  state: 1,
  "customer.name": 1,
  _id: 1
});
~~~

Một query với filter `state` và projection chỉ gồm các trường có trong index **có thể** đủ điều kiện cho *covered query*, tùy query plan và giới hạn của index. Nếu còn chọn `shippingAddress.city` mà index không có field đó, MongoDB có thể phải fetch document. Trường mảng/multikey còn có ràng buộc riêng khi muốn covered query.

**Không tạo index chỉ để phù hợp một DTO** nếu workload không cần. Index làm tăng chi phí ghi, lưu trữ và bảo trì. Trước khi thêm, xác định các filter/sort quan trọng, đo `explain` trên dữ liệu thật đại diện và đánh giá mức độ chọn lọc.

### 10.4. Projection không phải kiểm soát bảo mật

Đừng dùng duy nhất interface `OrderCardView` để bảo đảm thông tin nhạy cảm không rời database hoặc không thể xuất hiện trong log. Để giảm rủi ro:

1. Kiểm soát quyền truy cập theo user/role và phạm vi order ngay ở filter/service.
2. Dùng allowlist DTO rõ ràng cho từng endpoint.
3. Khi cần, gửi **field selection tường minh** tới MongoDB để không nhận email, điện thoại, giá vốn và ghi chú nội bộ.
4. Không log toàn bộ raw document và không trả entity domain trực tiếp nếu nó chứa dữ liệu nội bộ.
5. Kiểm thử JSON response và BSON thực tế của query; không chỉ kiểm tra số lượng trường getter của interface.

Trường bị loại bởi projection giúp giảm diện dữ liệu ứng dụng tiếp xúc, nhưng không thay thế xác thực, phân quyền và kiểm tra truy cập theo tenant.

## 11. Kiểm thử projection lồng nhau và field mask

Unit test mock `OrderRepository` có thể xác nhận mapping DTO ở service, nhưng **không** chứng minh MongoDB trả bao nhiêu field hay converter có xử lý nested projection đúng không. Với yêu cầu cần giới hạn dữ liệu, dùng integration test trên MongoDB test hoặc Testcontainers.

### 11.1. Ma trận kiểm thử

| Tình huống | Điều cần khẳng định |
| --- | --- |
| Closed projection theo state | Trả về đúng order và getter nested |
| Missing `shippingAddress` | Không gây `NullPointerException` khi map DTO |
| Nested `List<LineBriefView>` | Getter các phần tử ánh xạ đúng SKU/quantity |
| `@Query(fields)` | Không tải `customer.email`, `phone` hoặc `internalNotes` |
| `MongoTemplate` với `include("customer.name")` | BSON kết quả có `customer.name` nhưng không có `customer.email` |
| `lines.sku` field projection | Giữ các phần tử mảng, bỏ field không yêu cầu |
| `$elemMatch` trong filter | Chọn document đúng nhưng không tự cắt mảng |
| `$filter` + `$map` | Chọn đúng phần tử và đúng field trong output |
| DTO/JSON public | Không serialize trường nội bộ |
| Entity đọc một phần | Không bị dùng để `save` và xóa mất dữ liệu khác |

### 11.2. Test kiểm tra BSON thực sự được trả về

Ví dụ test với database **hoàn toàn dành cho kiểm thử** và `MongoTemplate`:

~~~java
package com.example.projections;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class NestedProjectionFieldsTest {
    @Autowired MongoTemplate template;

    @Test
    void queryReturnsOnlyExplicitlySelectedNestedFields() {
        var collection = template.getDb()
            .getCollection("orders_projection_demo_004");
        String id = "fixture-projection-004";

        collection.deleteOne(new Document("_id", id));
        try {
            collection.insertOne(
                new Document("_id", id)
                    .append("state", "PAID")
                    .append("customer",
                        new Document("name", "Test")
                            .append("email", "private@example.invalid"))
                    .append("internalNotes", "INTERNAL")
            );

            Query query = Query.query(
                Criteria.where("_id").is(id)
            );
            query.fields()
                .include("_id")
                .include("state")
                .include("customer.name");

            List<Document> result = template.find(
                query,
                Document.class,
                "orders_projection_demo_004"
            );

            assertThat(result).hasSize(1);
            Document raw = result.get(0);
            assertThat(raw.containsKey("internalNotes")).isFalse();

            Document customer = raw.get(
                "customer", Document.class
            );
            assertThat(customer.getString("name"))
                .isEqualTo("Test");
            assertThat(customer.containsKey("email")).isFalse();
        } finally {
            collection.deleteOne(new Document("_id", id));
        }
    }
}
~~~

Test cố ý kiểm tra **document BSON sau field projection** bằng `containsKey` thay vì chỉ so DTO. Fixture chỉ được chèn/xóa trong database test riêng; không dùng ID này ở môi trường dùng chung. Test thứ hai nên tải `OrderCardView` qua repository và xác nhận nested getters, nhưng **không suy từ đó rằng mọi field nhúng đều được loại ở server**.

### 11.3. Xác nhận behavior của phiên bản Spring Data đang dùng

Khi nâng cấp Spring Data MongoDB, nên kiểm tra lại:

- Query do derived method tạo có thêm field mask hay không.
- Nested closed projection có lấy cả object gốc hay chỉ field con.
- `@Query(fields)` có ánh xạ đúng tên BSON đối với `@Field` aliases.
- DTO constructor binding hoạt động thế nào với trường missing/null.
- Projection của mảng nhúng, đặc biệt khi mảng rỗng hoặc một phần tử không có field.

Các kiểm tra này quan trọng hơn việc suy luận chỉ từ tên phương thức hoặc số getter Java.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| DTO ít trường nhưng truy vấn vẫn chậm/tốn mạng | DTO được tạo **sau** khi tải entity đầy đủ; nested projection tải parent object | Kiểm tra field mask; dùng `@Query(fields)`/`MongoTemplate` |
| Nested getter trả `null` | Field missing, BSON null hoặc query projection bỏ sót | Kiểm tra BSON gốc và field selection |
| `customer.email` xuất hiện trong log dù DTO chỉ có `getName()` | Log entity/raw document trước khi chuyển DTO | Hạn chế field tải từ server, thay đổi logging |
| Interface getter chạy nhưng JSON sai cấu trúc | DTO mapping/serializer tạo shape khác API | Dùng API DTO tường minh, test JSON |
| `findByState` trả entity thay vì view | Return type khai báo `OrderDocument` hoặc gọi nhầm overload | Đổi return type/method và test |
| DTO record lỗi constructor binding | Parameter không khớp property hoặc constructor không rõ ràng | Kiểm tra tên property, constructor/`@PersistenceCreator` |
| `lines.sku` trả nhiều dòng hơn dự kiến | Field projection giới hạn **field** chứ không lọc phần tử | Dùng `$filter`/`$map` hoặc projection phù hợp |
| `$elemMatch` ở filter vẫn có cả mảng `lines` | Filter chọn document, không chọn phần tử output | Thêm projection/aggregation |
| `save(partial)` làm mất field | Entity trước đó chỉ được tải một phần | Không save entity partial; dùng update operator |
| `explain` không cho thấy docs examined giảm | Projection giảm network/decode nhưng vẫn fetch document | Đo kích thước response và app metrics; cân nhắc covered query |
| Open projection không giảm field tải | SpEL có thể truy cập target linh hoạt | Dùng closed projection hoặc field mask tường minh |
| Projection expose dữ liệu ngoài quyền tenant | Projection không tự tạo authorization | Bổ sung filter tenant, phân quyền và DTO allowlist |

## 13. Quy trình thiết kế projection an toàn

1. **Xác định use case**: danh sách, trang chi tiết, báo cáo hay API xuất dữ liệu; mỗi use case cần tập field khác nhau.
2. **Thiết kế hợp đồng trả về**: field nào public, field nào nội bộ, nested shape và nullability ra sao.
3. **Chọn cơ chế biểu diễn Java**: closed interface projection đơn giản, DTO/record phẳng, hoặc mapper tường minh cho kết quả phức tạp.
4. **Kiểm tra số trường được tải từ MongoDB**: với nested view, đừng suy luận từ getter; dùng field projection tường minh khi cần giảm payload.
5. **Xử lý mảng riêng**: chọn field bằng dot notation, chọn phần tử bằng `$elemMatch` projection, `$slice` hoặc `$filter`/`$map` tùy mục đích.
6. **Phân trang ở đúng cấp**: `Page<OrderCardView>` phân trang order, không phân trang `lines` bên trong mỗi order.
7. **Không ghi lại read model**: entity/DTO partial chỉ dành cho đọc; cập nhật bằng `Update` có điều kiện.
8. **Kiểm thử và đo**: kiểm BSON thực, nested getter, JSON output, `explain` và hiệu năng ứng dụng trên dữ liệu có quy mô đại diện.

## 14. Bài thực hành

Các bài dựa trên collection `orders_projection_demo_004` ở mục 2, trước khi các ví dụ thay đổi dữ liệu.

### Bài 1 — Dự đoán BSON server trả về

Cho:

~~~javascript
orders.find(
  { _id: "o401" },
  { _id: 0, state: 1, "customer.name": 1 }
);
~~~

Hãy nêu các field có trong kết quả và giải thích vì sao `customer.email` không xuất hiện.

**Đáp án:** document kết quả có `state: "PAID"` và `customer: { name: "An" }`; không có `_id` do `_id: 0`. MongoDB server đã nhận field projection chỉ include `customer.name`; email không được trả về.

### Bài 2 — Nested interface có đủ để bảo đảm ít dữ liệu được tải?

Một `CustomerNameView` chỉ có `String getName()`. Liệu điều đó bảo đảm MongoDB không tải `customer.email` hoặc `customer.phone`?

**Đáp án:** Không. Interface giới hạn accessor ở Java, còn cách tối ưu query với thuộc tính lồng nhau phụ thuộc loại projection và phiên bản Spring Data. Muốn chắc chắn, cấu hình field mask như `"customer.name": 1` và kiểm tra BSON/query thực tế.

### Bài 3 — Chọn một field của mỗi dòng hàng

Viết truy vấn trả về `lines.sku` của `o401`, không trả `quantity` và `unitPriceVnd`.

~~~javascript
orders.find(
  { _id: "o401" },
  { _id: 0, "lines.sku": 1 }
);
~~~

**Đáp án:** có `lines: [{sku:"A"},{sku:"B"}]`. Cả hai phần tử vẫn được giữ vì đây là **field projection**, không phải lọc phần tử.

### Bài 4 — Chỉ lấy dòng có số lượng lớn

Yêu cầu trả **tất cả** dòng có `quantity >= 5`, nhưng chỉ bao gồm `sku` và `quantity`. Có dùng projection `$elemMatch` không?

**Đáp án:** Không nên, vì projection `$elemMatch` chỉ trả phần tử khớp đầu tiên. Dùng `$filter` chọn tất cả dòng đạt điều kiện, rồi `$map` dựng mỗi dòng với hai field mong muốn; tham khảo pipeline mục 7.5.

### Bài 5 — Đọc một phần rồi save

Một service dùng `Query.fields().include("state").include("customer.name")` để đọc `OrderDocument`, sửa `state` và gọi `repository.save(partial)`. Rủi ro?

**Đáp án:** entity đã bị thiếu nhiều field vì không được tải, và save có thể thay thế/ghi lại document khiến field cũ mất hoặc thành default. Dùng `MongoTemplate.updateFirst()` với `Update.set("state", ...)` hoặc tải aggregate đầy đủ nếu cần sửa toàn bộ và kiểm tra version.

### Bài 6 — Phân tích hiệu năng

Truy vấn trả về 1.000 order, mỗi order có 100 dòng hàng. Màn hình chỉ dùng tên khách hàng và trạng thái. Hãy đề xuất các bước đo và cải tiến.

**Đáp án tham khảo:** dùng field projection chỉ gồm `_id`, `state` và `customer.name`, không lấy `lines`. Đặt filter, giới hạn kết quả/pagination, kiểm tra index theo điều kiện lọc/sort. So sánh BSON/response bytes, độ trễ và số object Java tạo ra; xem `explain` nhưng không kỳ vọng `totalDocsExamined` nhất thiết giảm chỉ vì bớt field.

## Tài liệu tham khảo

- [Spring Data Commons — Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html): closed/open interface projection, nested projection, DTO và dynamic projection.
- [Spring Data MongoDB — MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): `@Query(fields=...)`, projection và các method repository.
- [Spring Data MongoDB — Template Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `Query.fields()` và `MongoTemplate`.
- [MongoDB Manual — Project Fields to Return from Query](https://www.mongodb.com/docs/manual/tutorial/project-fields-from-query-results/): include/exclude, dot notation và mặc định `_id`.
- [MongoDB Manual — `$elemMatch` Projection](https://www.mongodb.com/docs/manual/reference/operator/projection/elemmatch/): trả phần tử đầu tiên của mảng thỏa điều kiện.
- [MongoDB Manual — `$slice` Projection](https://www.mongodb.com/docs/manual/reference/operator/projection/slice/): giới hạn số phần tử trả về.
- [MongoDB Manual — `$filter` Aggregation](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/) và [`$map`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/map/): lọc phần tử và đổi hình dạng kết quả.
- [MongoDB Manual — Covered Queries](https://www.mongodb.com/docs/manual/core/query-optimization/): khi nào truy vấn có thể được đáp ứng từ index, và cách xem execution plan.
