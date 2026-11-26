# Nhiều loại entity và thông tin phân biệt kiểu trong JSON của Spring Data Couchbase

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **một collection Couchbase có thể lưu nhiều loại document** và Spring Data Couchbase cần thông tin phân biệt kiểu khi ánh xạ về Java.
2. Nhận diện vai trò của trường metadata kiểu (thường là `_class`), `@TypeAlias`, `@Document`, `@Id` và `@Field`.
3. Thiết kế **nhiều entity cùng collection** hoặc **giá trị lồng nhau đa hình**, chọn cấu trúc phù hợp với phạm vi nghiệp vụ.
4. Viết truy vấn SQL++ phân biệt loại document, thiết kế index và hiểu sự khác nhau giữa query theo ID với query theo thuộc tính.
5. Lập kế hoạch tương thích khi đổi tên lớp Java, đổi type alias, thay đổi schema và xử lý document thiếu thông tin loại.
6. Kiểm tra vòng ghi–đọc của từng loại entity, bao gồm tình huống sử dụng repository, `CouchbaseTemplate`, CAS, TTL và API reactive.

Bài thuộc chương **Mô hình tài liệu** của module **SPRING_DATA_COUCHBASE**. Spring Data Couchbase cung cấp document mapping, repository, `CouchbaseTemplate` và SQL++; lựa chọn giữa bucket/scope/collection, chỉ mục, TTL và giao dịch vẫn cần được thực hiện dựa trên mô hình dữ liệu thực tế.

## 1. Một collection có thể chứa nhiều hình dạng JSON

Couchbase không bắt buộc mọi document trong cùng collection có chung một schema. Ví dụ collection `shop.audit.events` có thể lưu những sự kiện khác nhau:

Document key `event::order::001`:

~~~json
{
  "event_type": "ORDER_CREATED",
  "schema_version": 1,
  "order_id": "order::125",
  "occurred_at": "2026-11-25T08:00:00Z"
}
~~~

Document key `event::payment::002`:

~~~json
{
  "event_type": "PAYMENT_CAPTURED",
  "schema_version": 1,
  "order_id": "order::125",
  "amount_vnd": 350000,
  "occurred_at": "2026-11-25T08:03:00Z"
}
~~~

Cả hai đều là JSON hợp lệ, nhưng các trường nghiệp vụ khác nhau. Ở tầng Java, ta có thể tạo `OrderCreatedEvent` và `PaymentCapturedEvent` thay vì một lớp chứa tất cả trường ở dạng nullable.

Khác với cơ sở dữ liệu quan hệ có table schema cố định, Couchbase cho phép cùng collection lưu nhiều cấu trúc. **Điều đó không tự động cung cấp cơ chế xác định class Java khi đọc document**. Spring Data Couchbase cần ánh xạ giữa JSON và kiểu đích. Với trường hợp đa hình hoặc cần chọn subtype từ dữ liệu, một **type discriminator** là thông tin thiết yếu.

~~~mermaid
flowchart LR
    A["OrderCreatedEvent"] -->|"mapping"| C["shop.audit.events"]
    B["PaymentCapturedEvent"] -->|"mapping"| C
    C --> D["JSON: _class = order-created"]
    C --> E["JSON: _class = payment-captured"]
    D -->|"read/mapping"| A
    E -->|"read/mapping"| B
~~~

Trong thực tế, dùng chung collection hay tách collection phải được cân nhắc dựa trên vòng đời, quyền truy cập, index, TTL, số lượng document và dạng truy vấn. Việc hai class cùng dùng một collection chỉ là **một lựa chọn kiến trúc**.

## 2. Type discriminator là gì?

**Type discriminator** là giá trị trong dữ liệu giúp một hệ thống mapping nhận biết kiểu đối tượng cần tạo. Spring Data Couchbase mặc định dùng một type key như **`_class`** trong JSON body để lưu thông tin kiểu khi cơ chế mapping yêu cầu.

Ví dụ mặc định nếu không khai báo alias:

~~~json
{
  "_class": "com.example.shop.audit.OrderCreatedEvent",
  "event_type": "ORDER_CREATED",
  "schema_version": 1,
  "order_id": "order::125"
}
~~~

Tên lớp đầy đủ với package là chi tiết triển khai Java. Nếu đổi package hoặc tên class, document cũ có thể chứa tên không còn tương ứng với kiểu hiện tại. Vì vậy, **`@TypeAlias`** giúp sử dụng tên kiểu ngắn, ổn định hơn trong JSON:

~~~java
import org.springframework.data.annotation.TypeAlias;

@TypeAlias("order-created")
public class OrderCreatedEvent {
    // Các thuộc tính persistence...
}
~~~

Khi mapper ghi thông tin loại, ví dụ JSON sẽ là:

~~~json
{
  "_class": "order-created",
  "event_type": "ORDER_CREATED",
  "schema_version": 1,
  "order_id": "order::125"
}
~~~

Chú ý ba điều:

- `@TypeAlias` **quy định tên loại cho Spring Data mapping**; nó không tự tạo field nghiệp vụ, index, ràng buộc khóa ngoại hay schema validator.
- Type key có thể được tùy chỉnh bởi cấu hình converter. Không viết SQL++ cứng vào `_class` nếu dự án đã thay đổi type key.
- Một alias chỉ đọc được thành class tương ứng khi **mapping context biết class đó**. Phải bảo đảm các entity/subtype được quét hoặc đăng ký với Spring Data trước khi đọc dữ liệu cũ, nhất là lớp chỉ xuất hiện trong object đa hình.

### Bốn khái niệm dễ nhầm lẫn

| Khái niệm | Ví dụ | Để làm gì? |
| --- | --- | --- |
| **Type discriminator** | `"_class": "order-created"` | Spring Data nhận biết loại Java khi materialize dữ liệu |
| **Loại nghiệp vụ** | `"event_type": "ORDER_CREATED"` | Consumer nghiệp vụ chọn cách xử lý sự kiện |
| **Phiên bản schema** | `"schema_version": 1` | Phân biệt định dạng payload cũ/mới để chuyển đổi |
| **CAS / `@Version`** | CAS trong metadata document | Phát hiện xung đột khi nhiều writer cập nhật cùng document |

Không dùng CAS làm schema version, không dùng `@TypeAlias` thay thế trường loại nghiệp vụ nếu dữ liệu còn được đọc bởi dịch vụ khác hoặc SDK không có Spring Data. Một ứng dụng có thể sử dụng **cả bốn** và mỗi giá trị có ý nghĩa khác nhau.

## 3. Các annotation và vị trí lưu dữ liệu

| Annotation | Package | Vai trò |
| --- | --- | --- |
| `@Document` | `org.springframework.data.couchbase.core.mapping.Document` | Đánh dấu entity được lưu thành document |
| `@Id` | `org.springframework.data.annotation.Id` | Ánh xạ Couchbase **document key**, nằm ngoài JSON body |
| `@Field` | `org.springframework.data.couchbase.core.mapping.Field` | Đánh dấu trường lưu trữ, tùy chọn tên JSON khác tên Java |
| `@TypeAlias` | `org.springframework.data.annotation.TypeAlias` | Đặt tên kiểu để Spring Data lưu/đọc trong discriminator |
| `@Scope`, `@Collection` | `org.springframework.data.couchbase.core.mapping` | Chọn scope và collection cho entity |
| `@Version` | `org.springframework.data.annotation.Version` | CAS/optimistic locking, không phải schema version |
| `@Transient` | `org.springframework.data.annotation.Transient` | Loại thuộc tính khỏi mapping persistence |

**Document key khác discriminator.** Ví dụ document có key `event::order::001` và field `_class: "order-created"`: key xác định **document cụ thể** trong collection, còn discriminator mô tả **kiểu đối tượng**. Hai document có thể cùng discriminator nhưng không được có cùng key trong một collection.

## 4. Ví dụ: hai entity khác nhau cùng collection

Giả sử bucket là `shop`, scope `audit`, collection `events`. Bucket được cấu hình qua kết nối; `@Scope` và `@Collection` đặt keyspace cho hai entity.

### 4.1. OrderCreatedEvent.java

~~~java
package com.example.shop.audit;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("audit")
@Collection("events")
@TypeAlias("order-created")
public class OrderCreatedEvent {

    @Id
    private String id;

    @Field("event_type")
    private String eventType;

    @Field("schema_version")
    private int schemaVersion;

    @Field("order_id")
    private String orderId;

    @Field("occurred_at")
    private Instant occurredAt;

    protected OrderCreatedEvent() {
        // Constructor để Spring Data materialize entity.
    }

    public OrderCreatedEvent(String id, String orderId, Instant occurredAt) {
        if (id == null || id.isBlank() ||
                orderId == null || orderId.isBlank() ||
                occurredAt == null) {
            throw new IllegalArgumentException("Thiếu dữ liệu sự kiện");
        }
        this.id = id;
        this.eventType = "ORDER_CREATED";
        this.schemaVersion = 1;
        this.orderId = orderId;
        this.occurredAt = occurredAt;
    }

    public String getId() { return id; }
    public String getOrderId() { return orderId; }
    public Instant getOccurredAt() { return occurredAt; }
}
~~~

### 4.2. PaymentCapturedEvent.java

~~~java
package com.example.shop.audit;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("audit")
@Collection("events")
@TypeAlias("payment-captured")
public class PaymentCapturedEvent {

    @Id
    private String id;

    @Field("event_type")
    private String eventType;

    @Field("schema_version")
    private int schemaVersion;

    @Field("order_id")
    private String orderId;

    @Field("amount_vnd")
    private long amountVnd;

    @Field("occurred_at")
    private Instant occurredAt;

    protected PaymentCapturedEvent() {}

    public PaymentCapturedEvent(
            String id, String orderId, long amountVnd, Instant occurredAt) {
        if (id == null || id.isBlank() ||
                orderId == null || orderId.isBlank() ||
                amountVnd < 0 || occurredAt == null) {
            throw new IllegalArgumentException("Dữ liệu thanh toán không hợp lệ");
        }
        this.id = id;
        this.eventType = "PAYMENT_CAPTURED";
        this.schemaVersion = 1;
        this.orderId = orderId;
        this.amountVnd = amountVnd;
        this.occurredAt = occurredAt;
    }

    public String getId() { return id; }
    public long getAmountVnd() { return amountVnd; }
}
~~~

Các ví dụ dùng hai lớp Java ở **hai tệp riêng**. Nếu lớp sự kiện là append-only trong hệ thống thật, cần dùng thao tác **insert only** và quy ước event ID/idempotency; không nên cho phép tùy ý ghi đè một sự kiện lịch sử.

### 4.3. Hai JSON sau khi lưu

Document `event::order::001`:

~~~json
{
  "_class": "order-created",
  "event_type": "ORDER_CREATED",
  "schema_version": 1,
  "order_id": "order::125",
  "occurred_at": "2026-11-25T08:00:00Z"
}
~~~

Document `event::payment::002`:

~~~json
{
  "_class": "payment-captured",
  "event_type": "PAYMENT_CAPTURED",
  "schema_version": 1,
  "order_id": "order::125",
  "amount_vnd": 350000,
  "occurred_at": "2026-11-25T08:03:00Z"
}
~~~

Hai document đều ở `shop.audit.events`. Tuy nhiên, lớp Java, alias và tập field khác nhau; `_class` giúp bộ mapping phân biệt chúng trong trường hợp cần materialize đúng kiểu. Cách thời điểm `Instant` được biểu diễn phụ thuộc mapping/converter của phiên bản Spring Data và cấu hình thực tế, nên cần kiểm tra JSON sau khi ghi.

## 5. Dùng repository và CouchbaseTemplate với nhiều entity

Mỗi loại có thể có repository riêng dù cùng dùng collection:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderCreatedEventRepository
        extends CouchbaseRepository<OrderCreatedEvent, String> {
}

public interface PaymentCapturedEventRepository
        extends CouchbaseRepository<PaymentCapturedEvent, String> {
}
~~~

Trong service:

~~~java
import java.time.Instant;

OrderCreatedEvent created = new OrderCreatedEvent(
    "event::order::001",
    "order::125",
    Instant.parse("2026-11-25T08:00:00Z")
);
orderCreatedEventRepository.save(created);

OrderCreatedEvent loaded = orderCreatedEventRepository
    .findById("event::order::001")
    .orElseThrow();
~~~

`findById` dùng **document key** và thường đi qua Key-Value (KV). Không cần secondary index chỉ để lấy một event đã biết ID. Các hàm query như `findByOrderId(...)` sẽ đi qua đường truy vấn theo thuộc tính và cần index phù hợp.

**Không đọc một document với kiểu repository tùy ý.** Ví dụ dùng `OrderCreatedEventRepository.findById("event::payment::002")` là sai về mặt thiết kế: key có thể tồn tại, nhưng document mang kiểu khác. Tùy converter và cách gọi, bạn có thể gặp lỗi mapping, kết quả không như mong đợi hoặc đối tượng không phản ánh payload thật. Tầng service cần biết loại mong đợi hoặc có chiến lược đọc đa hình rõ ràng.

`CouchbaseTemplate` dùng cùng mapping metadata:

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;

public OrderCreatedEvent loadEvent(CouchbaseTemplate template, String id) {
    return template.findById(OrderCreatedEvent.class).one(id);
}
~~~

Template phù hợp khi cần điều khiển các thao tác/điều kiện phức tạp; nó **không tự biến mọi document trong collection thành một superclass chung** nếu thiết kế và mapping context không hỗ trợ. Nếu cần đọc nhiều loại vào một mô hình chung, hãy định nghĩa lớp cha/interface, chú ý discriminator của từng subtype và kiểm tra cách truy vấn/materialize với phiên bản framework sử dụng.

### Điều gì xảy ra khi dùng nhiều repository cùng collection?

Trong hệ thống có nhiều entity type, một truy vấn repository theo thuộc tính có thể được Spring Data tạo kèm điều kiện giới hạn **kiểu entity** dựa trên type metadata. Query tùy chỉnh và một số cấu hình converter có thể xử lý khác. Vì vậy:

- Xem SQL++ thực tế do repository tạo và kiểm tra kết quả khi collection chứa nhiều kiểu.
- Nếu tự viết `@Query`, **chỉ định loại mong muốn** hoặc quy định rõ cách materialize.
- Đừng giả định `findAll()` của một repository sẽ trả một tập hợp đa hình theo ý bạn.
- Mỗi type dùng cùng collection cần tránh va chạm document key và nên thống nhất prefix/ID convention.

## 6. Phân biệt kiểu trong SQL++ và thiết kế chỉ mục

Trong ví dụ dùng type key mặc định `_class` và alias ở trên, câu SQL++ lọc sự kiện tạo đơn:

~~~sql
SELECT META(e).id AS eventId,
       e.event_type,
       e.order_id,
       e.occurred_at
FROM `shop`.`audit`.`events` AS e
WHERE e._class = "order-created"
  AND e.order_id = $orderId
ORDER BY e.occurred_at DESC
LIMIT 50;
~~~

Index ứng viên:

~~~sql
CREATE INDEX ix_events_type_order_time
ON `shop`.`audit`.`events`(
    `_class`,
    order_id,
    occurred_at DESC
);
~~~

Ở đây:

- `_class` chỉ là field JSON của type mapper (nếu cấu hình dùng tên khác, sửa cả query/index).
- `order_id` và `occurred_at` là tên JSON do `@Field` quy định.
- Alias `order-created` là **giá trị chuỗi** đã lưu, không phải tên Java class.
- Index cần được kiểm tra với `EXPLAIN` và workload thật. Index tăng chi phí lưu trữ và mutation.

Nếu ứng dụng khác không biết `@TypeAlias`, nó vẫn có thể lọc theo **trường nghiệp vụ**:

~~~sql
SELECT META(e).id AS eventId, e.event_type, e.schema_version
FROM `shop`.`audit`.`events` AS e
WHERE e.event_type = "PAYMENT_CAPTURED";
~~~

Khi query này chạy thường xuyên, cân nhắc index phù hợp với `event_type` và những field lọc/sắp xếp khác. Không nên tạo chỉ mục trùng lặp trên cả `_class` và `event_type` nếu không có workload cần thiết. Nếu nhiều consumer cùng truy cập, một field nghiệp vụ rõ ràng thường dễ duy trì hơn việc buộc tất cả hiểu metadata nội bộ của Spring Data.

### Type metadata không tự tạo ranh giới quyền truy cập

Một collection dùng chung nhiều loại có thể đơn giản khi truy vấn hợp nhất, nhưng cũng khiến mọi loại chia sẻ chính sách truy cập ở mức collection và chi phí index. Nếu có loại document chứa dữ liệu nhạy cảm, TTL/retention khác hoặc tải ghi rất lớn, cân nhắc **tách collection** thay vì dựa vào `_class` để phân quyền.

## 7. Đa hình ở đối tượng lồng nhau

Ngoài nhiều root entity chung collection, một **field lồng nhau** có thể khai báo interface hoặc lớp cha, còn dữ liệu thực tế là một trong nhiều subtype.

Ví dụ một lần thực hiện đơn hàng có thể chọn **giao tận nhà** hoặc **nhận tại cửa hàng**:

~~~java
package com.example.shop.sales;

public interface FulfillmentChoice {
}
~~~

Hai value object triển khai interface (đặt trong các file Java tương ứng):

~~~java
package com.example.shop.sales;

import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Field;

@TypeAlias("home-delivery")
public class HomeDelivery implements FulfillmentChoice {

    @Field
    private String city;

    @Field
    private String addressLine;

    protected HomeDelivery() {}

    public HomeDelivery(String city, String addressLine) {
        if (city == null || city.isBlank() ||
                addressLine == null || addressLine.isBlank()) {
            throw new IllegalArgumentException("Địa chỉ không hợp lệ");
        }
        this.city = city;
        this.addressLine = addressLine;
    }
}
~~~

~~~java
package com.example.shop.sales;

import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Field;

@TypeAlias("store-pickup")
public class StorePickup implements FulfillmentChoice {

    @Field("store_id")
    private String storeId;

    protected StorePickup() {}

    public StorePickup(String storeId) {
        if (storeId == null || storeId.isBlank()) {
            throw new IllegalArgumentException("Store ID không hợp lệ");
        }
        this.storeId = storeId;
    }
}
~~~

Root chứa field interface:

~~~java
package com.example.shop.sales;

import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Fulfillment {
    @Id
    private String id;

    @Field
    private FulfillmentChoice choice;

    protected Fulfillment() {}

    public Fulfillment(String id, FulfillmentChoice choice) {
        if (id == null || id.isBlank() || choice == null) {
            throw new IllegalArgumentException("Thiếu dữ liệu");
        }
        this.id = id;
        this.choice = choice;
    }

    public FulfillmentChoice getChoice() { return choice; }
}
~~~

Khi mapping theo cấu hình ghi thông tin subtype, body có thể có dạng:

~~~json
{
  "_class": "com.example.shop.sales.Fulfillment",
  "choice": {
    "_class": "store-pickup",
    "store_id": "store::hcm01"
  }
}
~~~

Ở cấp root, `_class` cho biết loại document `Fulfillment`. Bên trong `choice`, discriminator cho biết object có kiểu `StorePickup`, cho phép khôi phục đúng subtype thay vì cố khởi tạo interface `FulfillmentChoice`.

**Phải kiểm chứng bằng vòng ghi–đọc thực tế:** cấu hình type mapper, converter tùy biến, entity scanning và phiên bản Spring Data có thể thay đổi thời điểm/định dạng type hint. Nếu runtime không biết alias `store-pickup`, mapper không thể tự suy ra class chỉ từ chuỗi alias. Có thể đăng ký các subtype vào mapping context hoặc để chúng được phát hiện thông qua cấu hình entity scanning.

### Nếu không lưu discriminator ở object đa hình?

Một JSON như:

~~~json
{
  "choice": {
    "store_id": "store::hcm01"
  }
}
~~~

có thể không đủ để mapper biết phải tạo `StorePickup` hay một subtype khác, nhất là khi các subtype có field trùng nhau. Với interface trừu tượng, việc materialize thiếu loại cụ thể có thể thất bại.

Có ba hướng thiết kế:

1. Lưu type hint theo cơ chế Spring Data và bảo đảm subtype được đăng ký.
2. Lưu **trường nghiệp vụ `kind`** và viết converter/factory rõ ràng để dựng subtype theo whitelist.
3. Không dùng polymorphism ở persistence; lưu một POJO/DTO có schema ổn định và chuyển đổi sang các class nghiệp vụ ở tầng service.

Chọn phương án theo mức độ sử dụng chéo ngôn ngữ, yêu cầu schema lâu dài và khả năng bảo trì. Với dữ liệu trao đổi qua nhiều dịch vụ, trường nghiệp vụ có schema/phiên bản tường minh thường bền vững hơn việc phụ thuộc tên class Java.

## 8. @TypeAlias và tính tương thích khi refactor mã nguồn

Giả sử ngày đầu tiên lớp có tên:

~~~text
com.example.shop.audit.OrderCreatedEvent
~~~

Không có `@TypeAlias`, JSON có thể chứa:

~~~json
{"_class": "com.example.shop.audit.OrderCreatedEvent"}
~~~

Sau một lần refactor, class được chuyển sang:

~~~text
com.example.shop.events.OrderCreatedEvent
~~~

**JSON cũ không tự đổi `_class`** theo mã nguồn. Nếu mapper tìm class theo tên cũ mà class không còn tồn tại/được đăng ký, việc đọc có thể không khôi phục đúng loại.

Dùng alias từ đầu giúp giữ giá trị lưu trữ ổn định:

~~~java
@TypeAlias("order-created")
public class OrderCreatedEvent {
}
~~~

Về sau có thể chuyển package nhưng giữ `"order-created"` trong JSON, miễn là cấu hình mapping context biết alias đó đang thuộc về class mới. Tuy nhiên:

- **Thêm `@TypeAlias` sau khi đã có dữ liệu** không tự chuyển các document đang chứa tên lớp đầy đủ.
- **Đổi chính alias** (ví dụ từ `order-created` sang `order-created-v2`) cũng là thay đổi dữ liệu cần kế hoạch tương thích.
- **Đổi tên field nghiệp vụ** (`orderId` sang `order_id`) là migration khác; type alias không tự chuyển field.
- Alias phải **duy nhất và có ý nghĩa rõ** trong phạm vi các kiểu mà mapper cần phân biệt; hai class khác nhau dùng chung alias có thể gây mơ hồ.

### Lộ trình migration an toàn

1. **Khảo sát:** thống kê từng giá trị `_class`, tỷ lệ document thiếu type key, loại JSON và client/worker đang đọc chúng.
2. **Xác định hợp đồng:** chọn alias ổn định, xác định trường `event_type` và `schema_version` có cần cho giao tiếp giữa dịch vụ không.
3. **Triển khai giai đoạn tương thích:** bảo đảm reader có thể hiểu dữ liệu cũ/mới thông qua mapping context, converter hoặc migration theo lô trước khi chỉ dùng alias mới.
4. **Đổi dữ liệu có kiểm soát:** cập nhật discriminator hoặc field nghiệp vụ theo batch với điều kiện chính xác; kiểm tra ghi đồng thời, CAS và quyền truy cập.
5. **Cập nhật query/index:** mọi câu SQL++ lọc `_class` phải biết giá trị được lưu thực tế trong giai đoạn chuyển tiếp.
6. **Đối chiếu:** kiểm thử round-trip, số lượng document từng loại, tỷ lệ lỗi mapping và khả năng rollback.

Ví dụ tìm các kiểu đang lưu trong một collection:

~~~sql
SELECT e._class AS storedType, COUNT(1) AS total
FROM `shop`.`audit`.`events` AS e
GROUP BY e._class;
~~~

Truy vấn thống kê có thể cần index/phương án scan phù hợp với dataset. Đừng chạy một lệnh UPDATE diện rộng chỉ dựa trên suy đoán về loại document, nhất là khi collection dùng chung nhiều schema.

## 9. Document không có type discriminator hoặc có metadata sai

Document có thể được ghi bởi SDK Couchbase khác, truy vấn SQL++ hoặc import, nên không phải mọi JSON đều chứa `_class`. Hai trường hợp:

**(A) Đọc với loại cụ thể đã biết.** Nếu gọi repository của một entity rõ ràng và JSON đủ field tương ứng, mapper có thể dựng đối tượng từ kiểu đích. Tuy nhiên, hành vi còn phụ thuộc converter/cấu hình; không được coi thiếu `_class` là luôn vô hại.

**(B) Đọc dưới kiểu cha/interface.** Khi không có type hint và có nhiều subtype hợp lệ, mapper thường không đủ thông tin để lựa chọn class. Cần một discriminator nghiệp vụ và converter, hoặc bổ sung type hint qua migration.

Một trường `_class` sai có thể khiến Java dựng nhầm loại, thiếu field hoặc lỗi chuyển đổi. Nếu document đến từ nguồn ngoài Spring Data, nên xử lý nó như **dữ liệu đầu vào cần kiểm tra**: xác nhận kind/schema version, kiểm tra field bắt buộc, không cho phép payload từ người dùng tự quyết định class sẽ được khởi tạo.

Bảng tình huống:

| JSON lưu trữ | Khi đọc | Hướng xử lý |
| --- | --- | --- |
| `_class` đúng alias đã đăng ký | Có thể dựng đúng entity/subtype | Kiểm tra field nghiệp vụ và version |
| `_class` là tên Java cũ | Có thể không còn resolve sau refactor | Giữ tương thích hoặc migrate |
| `_class` thiếu nhưng biết loại đích cụ thể | Có thể đọc tùy converter | Kiểm thử cụ thể trên phiên bản framework |
| `_class` thiếu, property khai báo interface | Không đủ thông tin để chọn subtype | Dùng type hint, converter hoặc schema tường minh |
| `_class` trùng alias của class khác | Có thể dựng nhầm kiểu | Thiết kế alias duy nhất, kiểm tra dữ liệu |
| `_class` đúng nhưng `schema_version` cũ | Mapping vẫn có thể thiếu/sai field | Xử lý migration nội dung riêng |

## 10. Chọn một hay nhiều collection?

Couchbase tổ chức **bucket/scope/collection** để quản lý dữ liệu và tài nguyên. Type discriminator thuộc body JSON, còn collection là không gian lưu trữ, phân quyền và chỉ mục.

| Tiêu chí | Nhiều loại trong **một collection** | **Collection riêng** cho từng nhóm |
| --- | --- | --- |
| Truy vấn tổng hợp | Dễ tìm nhiều loại trong cùng keyspace | Có thể cần UNION/đọc nhiều collection |
| Chỉ mục | Có thể cần index theo `_class` hoặc `event_type`; các kiểu chia sẻ ngân sách index | Index theo workload riêng từng collection |
| Phân quyền | Cùng boundary quyền collection, phải lọc ở tầng ứng dụng khi cần | Dễ quản lý quyền khác nhau theo collection |
| TTL/retention | Phải quản lý khác biệt cẩn thận trong từng kiểu | Tách nhóm retention tự nhiên hơn |
| Độ phân bố lưu lượng | Các kiểu chia sẻ tài nguyên collection | Có thể vận hành và quan sát theo nhóm rõ hơn |
| Thay đổi schema | Nhiều schema cùng tồn tại, cần discriminator và tương thích | Schema của từng collection thường đồng nhất hơn |

Ví dụ các **domain events** append-only có cùng vòng đời và chính sách truy cập có thể hợp lý khi cùng `shop.audit.events`. Ngược lại, hồ sơ khách hàng, thanh toán và giỏ hàng tạm thường có vòng đời, quyền truy cập và retention khác nhau; việc đưa tất cả vào một collection chỉ vì có `_class` sẽ gây khó khăn.

**Không dùng type discriminator thay cho phân quyền.** SQL++ lọc `_class` chỉ chọn dữ liệu trong một câu query; nó không tự tạo giới hạn bảo mật ở cấp collection.

## 11. Tác động của CAS, TTL, transaction và reactive API

Các cơ chế vận hành này **không thay đổi ý nghĩa của `_class`**:

| Cơ chế | Ý nghĩa trong mô hình nhiều entity |
| --- | --- |
| **CAS / `@Version`** | Phát hiện xung đột khi cùng document bị ghi đồng thời; thuộc document, không phải kiểu entity |
| **TTL / expiry** | Document có thể hết hạn theo chính sách; không phụ thuộc discriminator và không chỉ xóa một subtype lồng trong body |
| **Transaction** | Khi một nghiệp vụ phải cập nhật nhiều document cùng commit, cần transaction phù hợp; cùng collection không tự khiến hai document nguyên tử |
| **SQL++ index** | Hỗ trợ lọc theo type/field; cần được thiết kế theo workload thực |
| **KV** | Đọc theo key, không cần secondary index; vẫn phải dùng class mapping phù hợp |
| **Reactive API** | I/O không chặn, không tự tìm subtype hoặc sửa metadata thiếu |

Nếu dùng `@Version`, giá trị version tương ứng với **CAS của Couchbase**, không phải `schema_version` lưu trong JSON. Cũng không nên đổi `_class` trực tiếp trên một entity đang hoạt động như cách “chuyển trạng thái” của workflow; việc đổi kind nghiệp vụ cần được thể hiện bằng trạng thái/sự kiện rõ ràng và quy tắc migration riêng nếu thật sự đổi kiểu entity.

## 12. Kiểm thử dữ liệu đa loại trên Couchbase thật

Vì việc ghi/đọc discriminator phụ thuộc mapping context và phiên bản framework, một kiểm thử tích hợp có giá trị hơn chỉ thử constructor Java.

### Các tình huống cần xác nhận

1. **Ghi đúng:** lưu `OrderCreatedEvent` và `PaymentCapturedEvent` vào cùng collection, đọc body JSON và xác minh alias `_class`.
2. **Đọc đúng:** dùng repository tương ứng đọc theo document key; kiểm tra mọi field và kiểu đối tượng.
3. **Đọc sai loại:** cố đọc document loại Payment qua repository Order và xác định hành vi thực tế để tầng service xử lý an toàn.
4. **Query phân loại:** tạo index cần thiết, chạy query `_class` và `event_type`, xác nhận kết quả/EXPLAIN và xem SQL++ sinh bởi repository.
5. **Đa hình lồng nhau:** lưu `Fulfillment` với `HomeDelivery` và `StorePickup`; đọc lại và kiểm tra `choice instanceof ...`.
6. **Tương thích:** đọc document cũ có tên lớp đầy đủ, alias cũ, không có type key hoặc có `schema_version` trước khi migration.
7. **Cập nhật:** nếu dùng `@Version`, hai writer sửa cùng document và kiểm tra hành vi CAS; đối với event append-only, kiểm tra tạo trùng key bị từ chối theo ngữ nghĩa insert.
8. **Dữ liệu sai:** thiếu trường bắt buộc, alias không biết, kiểu field không tương thích và JSON do một hệ thống khác ghi.

Một phép kiểm tra kiểu rõ ràng:

~~~java
Fulfillment stored = fulfillmentRepository.save(
    new Fulfillment("fulfillment::125",
        new StorePickup("store::hcm01"))
);

Fulfillment loaded = fulfillmentRepository
    .findById("fulfillment::125")
    .orElseThrow();

if (!(loaded.getChoice() instanceof StorePickup)) {
    throw new AssertionError("Mapping subtype không đúng");
}
~~~

Đoạn mã giả định bạn đã khai báo `FulfillmentRepository extends CouchbaseRepository<Fulfillment, String>` trong dự án. Mục tiêu kiểm thử là **đọc lại qua Couchbase thật**, không chỉ so sánh giá trị ở đối tượng trước khi `save`.

### Dấu hiệu lỗi và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Việc cần kiểm tra |
| --- | --- | --- |
| Class bị đọc thành kiểu không mong đợi | Alias trùng, type hint sai hoặc class đích chưa đăng ký | Body JSON, `@TypeAlias`, mapping context |
| Query repository bỏ sót loại cần tìm | Có điều kiện type discriminator tự thêm hoặc alias mismatch | SQL++ phát sinh, `_class` thực tế, index |
| Sau refactor xuất hiện lỗi khi load | JSON cũ lưu FQCN cũ hoặc alias đổi | Tỷ lệ document theo `_class`, kế hoạch migration |
| Đọc object interface bị lỗi | Thiếu subtype discriminator hoặc mapping context không biết subtype | JSON lồng nhau, converter/type alias registration |
| Kết quả query có nhiều loại không mong muốn | SQL++ không lọc `_class`/`event_type` | Điều kiện WHERE và projection |
| Đổi `schema_version` nhưng code vẫn lỗi | Chưa có logic chuyển schema nội dung | Field cũ/mới, converter, kiểm thử dữ liệu lịch sử |
| Đọc theo ID từ repository khác loại | ID đúng nhưng kiểu entity mong đợi sai | Prefix key, collection và discriminator |
| Dữ liệu có `_class` nhưng REST API vẫn mất field | HTTP serialization khác persistence mapper | DTO, Jackson annotations, projection |

## 13. Bài thực hành: một collection lưu nhiều loại thông báo

Một hệ thống có collection `shop.communication.notifications`, gồm:

- `EmailNotification`: `notificationId`, `recipientEmail`, `subject`.
- `PushNotification`: `notificationId`, `deviceId`, `title`.
- Cả hai có `createdAt`, `status` và `schemaVersion`.
- Một màn hình quản trị lọc loại thông báo, trạng thái và thời gian; người dùng chỉ có quyền thấy thông báo của mình.

**Yêu cầu:**

1. Đề xuất `@TypeAlias` cho hai loại và field nghiệp vụ `channel`.
2. Phác họa body JSON cho mỗi loại.
3. Nêu cách đọc theo document key và cách query danh sách theo filter.
4. Giải thích khi nào nên tách thành hai collection.

### Lời giải tham khảo

Alias: `email-notification` và `push-notification`. Field `channel` độc lập với mapping: `EMAIL` / `PUSH`. JSON ví dụ:

~~~json
{
  "_class": "email-notification",
  "channel": "EMAIL",
  "schema_version": 1,
  "recipient_email": "customer@example.test",
  "subject": "Xác nhận đơn",
  "status": "QUEUED",
  "created_at": "2026-11-25T08:10:00Z"
}
~~~

~~~json
{
  "_class": "push-notification",
  "channel": "PUSH",
  "schema_version": 1,
  "device_id": "device::demo01",
  "title": "Đơn đã được xác nhận",
  "status": "QUEUED",
  "created_at": "2026-11-25T08:12:00Z"
}
~~~

Từng document có key riêng, ví dụ `notification::email::001` hoặc `notification::push::002`. Biết key và class đích thì gọi repository theo ID (KV). Màn hình quản trị dùng SQL++ theo `channel`, `status`, `created_at`, có phân trang và index thiết kế theo truy vấn. **Quyền xem thông báo** phải được kiểm tra ở tầng API/theo người nhận; type alias không tạo hàng rào phân quyền.

Nếu Email và Push có chính sách truy cập, retention, TTL hay tải ghi rất khác nhau, có thể tách collection dù các trường chung giống nhau. Nếu cần truy vấn hợp nhất thường xuyên và chính sách giống nhau, lưu chung cũng hợp lý.

### Câu hỏi tự kiểm tra

1. **`@TypeAlias` có tạo key cho entity không?** Không; key được xác định bởi `@Id`.
2. **Hai entity cùng collection có thể chứa các tập field khác nhau không?** Có; Couchbase lưu JSON linh hoạt.
3. **`_class` có phải thuộc tính nghiệp vụ ổn định cho mọi consumer không?** Không nên coi như vậy; đây là metadata của mapper và có thể thay đổi bởi cấu hình/refactor.
4. **Tại sao cần `schema_version` dù đã có `_class`?** Type xác định loại, schema version xác định định dạng dữ liệu theo thời gian.
5. **Đổi package có tự sửa `_class` trong document cũ không?** Không; dùng alias ổn định/migration.
6. **Đọc theo ID có cần index trên `_class` không?** Không cần secondary index cho thao tác KV theo key.
7. **Đọc interface từ JSON thiếu discriminator có chắc thành công không?** Không; cần cơ chế chọn subtype.
8. **Dùng reactive repository có giúp tự xác định loại document không?** Không; logic mapping và dữ liệu type hint vẫn quan trọng.

## 14. Checklist áp dụng trong dự án

- [ ] Xác định liệu các loại entity có thực sự nên dùng chung collection dựa trên truy vấn, retention, quyền truy cập và tải ghi.
- [ ] Khai báo `@Document`, `@Id`, `@Field` đúng package; cân nhắc `@TypeAlias` ổn định cho nhiều kiểu.
- [ ] Thống nhất giá trị alias duy nhất và bảo đảm mapping context nhận biết mọi subtype cần đọc.
- [ ] Phân biệt type hint của Spring Data, trường loại nghiệp vụ, schema version và CAS.
- [ ] Quy định key ổn định, tránh trùng key giữa các entity chung collection.
- [ ] Dùng query và index theo tên field JSON thực tế; kiểm tra type filter, query sinh tự động và `EXPLAIN`.
- [ ] Có chiến lược đọc document cũ có FQCN, alias cũ, thiếu `_class` hoặc schema version cũ.
- [ ] Kiểm thử round-trip từng entity và nested polymorphism bằng dữ liệu Couchbase thật.
- [ ] Không dựa vào `_class` làm ranh giới bảo mật hay giao thức tích hợp bất biến.
- [ ] Đánh giá CAS, TTL, transaction và reactive API theo workload, không suy ra từ kiểu entity.

## Tài liệu tham khảo chính thức

- [Spring Data Couchbase — Modeling Entities](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): type information, `@Document`, field mapping và cơ chế dựng lại entity.
- [Spring Data Commons — Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html): metadata mapping, constructor và `@TypeAlias` cho dữ liệu đa hình.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): truy cập KV theo key, truy vấn dựa trên repository.
- [Spring Data Couchbase — Collection Support](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): `@Scope`, `@Collection` và nơi lưu entity.
- [Couchbase — The Couchbase Data Model](https://docs.couchbase.com/server/current/learn/data/document-data-model.html): document JSON, bucket/scope/collection và hình dạng dữ liệu linh hoạt.
- [Couchbase — CREATE INDEX](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/createindex.html): tạo index cho SQL++ trên type key và các thuộc tính.
