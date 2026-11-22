# Ánh xạ _class, kế thừa và @TypeAlias

> **Chương:** Ánh xạ cơ bản  
> **Module:** `SPRING_DATA_MONGODB`

Spring Data MongoDB chuyển đổi đối tượng Java thành document BSON và ngược lại thông qua `MappingMongoConverter`. Với lớp Java thông thường, kiểu đích có thể suy ra từ khai báo của thuộc tính hoặc tham số truy vấn. Nhưng khi một thuộc tính có kiểu **interface**, **abstract class**, hoặc cùng collection chứa nhiều lớp con, bộ chuyển đổi cần biết **kiểu thực tế** đã được lưu để khởi tạo đúng đối tượng. Theo cấu hình mặc định, Spring Data MongoDB dùng field metadata **`_class`** để mang thông tin kiểu đó.

Annotation `@TypeAlias` cho phép thay tên lớp Java dài trong `_class` bằng một mã định danh ngắn, ổn định hơn. Kết hợp cơ chế này với kế thừa giúp ứng dụng biểu diễn các biến thể nghiệp vụ, chẳng hạn nhiều loại sự kiện trong cùng collection, mà vẫn đọc về đúng kiểu Java. Tuy nhiên, cách lưu metadata ảnh hưởng đến tương thích dữ liệu, refactor package, migration và tính đúng đắn khi không còn type hint.

Bài này đặt trong phạm vi module `SPRING_DATA_MONGODB`: dùng Spring Data MongoDB để kết nối, ánh xạ document và truy cập qua `MongoTemplate` hoặc repository; đây cũng là nền tảng để xây dựng truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu ở những bài sau.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích field `_class` trong BSON, khi nào type hint được ghi và cách Spring Data dùng nó khi đọc.
2. Ánh xạ hệ phân cấp lớp cha–lớp con vào cùng collection hoặc trong document lồng nhau.
3. Dùng `@TypeAlias` cho các lớp cụ thể và giải thích tác động đến dữ liệu đã có.
4. Phân biệt `@TypeAlias` với `@Document`, `@Field`, `@Id`, discriminator nghiệp vụ và JSON polymorphism.
5. Nhận biết rủi ro khi tắt/đổi type mapping và thiết kế kiểm thử cho dữ liệu polymorphic.

## 2. _class là gì?

Xét một entity:

```java
package com.example.demo.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public class Product {
    @Id
    private String id;
    private String name;

    protected Product() {}

    public Product(String name) {
        this.name = name;
    }
}
```

Với `MappingMongoConverter` mặc định, một document có thể được ghi như sau (minh họa dưới dạng cú pháp `mongosh`):

```javascript
{
  _id: ObjectId("66a000000000000000000010"),
  name: "Bàn phím cơ",
  _class: "com.example.demo.model.Product"
}
```

Ở đây:

- `_id` là khóa nhận diện document trong collection; nó **không** xác định kiểu Java.
- `name` là dữ liệu nghiệp vụ của sản phẩm.
- `_class` là metadata của **Spring Data mapping**, giúp bộ chuyển đổi nhận diện lớp tương ứng. MongoDB server không tự hiểu chuỗi `"com.example.demo.model.Product"` là một kiểu Java hay một quan hệ kế thừa.

Theo cấu hình mặc định, Spring Data MongoDB có thể lưu tên lớp Java đầy đủ (*fully qualified class name*, FQCN) ở document gốc và tại các vị trí lồng nhau cần thông tin kiểu thực tế. Khi đọc, `MappingMongoConverter` kết hợp metadata `_class` với kiểu Java được yêu cầu để xác định cách tạo object.

> **Phân biệt:** `_class` không phải field bắt buộc của MongoDB. Một document được tạo trực tiếp bằng `mongosh` có thể hoàn toàn không có `_class`; MongoDB vẫn lưu và truy vấn được, nhưng việc ánh xạ sang kiểu trừu tượng trong Java có thể thất bại nếu không có thông tin thay thế.

### 2.1. Luồng chuyển đổi mặc định

```text
               Java -> BSON

new OrderCreatedEvent(...)
          |
          v
   MappingMongoConverter
   - tra @Document, @Id, field mapping
   - xác định kiểu Java thực tế
   - ghi type hint qua MongoTypeMapper
          |
          v
{ "_id": ..., "_class": "order_created", ... }


               BSON -> Java

{ "_class": "order_created", ... }
          |
          v
   MongoTypeMapper + MappingContext
   - giải mã alias/kiểu đã đăng ký
          |
          v
   MappingMongoConverter
   - tạo đúng lớp cụ thể
   - gán các field
          |
          v
   OrderCreatedEvent(...)
```

Nếu document chỉ có các field đơn giản và đích đọc đã là một lớp cụ thể, có thể đọc thành công mà không có `_class`. Vấn đề quan trọng xuất hiện khi Java chỉ biết một **kiểu cha**, còn dữ liệu thực tế tương ứng với nhiều lớp con.

### 2.2. Vì sao _class không phải schema nghiệp vụ?

Không nên sử dụng FQCN như mã loại nghiệp vụ công khai, vì refactor package hoặc thay ngôn ngữ triển khai có thể làm giá trị này thay đổi. Nếu API hoặc báo cáo cần “loại đơn” hay “loại sự kiện”, hãy cân nhắc một field nghiệp vụ tường minh như `eventType` có ý nghĩa ổn định, độc lập với chi tiết mapping.

`@TypeAlias` giúp metadata kỹ thuật gọn và ít phụ thuộc package hơn, nhưng bản thân alias vẫn là **hợp đồng giữa dữ liệu lưu và bộ chuyển đổi**; đổi alias tùy tiện cũng có thể làm dữ liệu cũ không đọc được.

## 3. Kế thừa: một collection chứa nhiều loại sự kiện

Giả sử hệ thống bán hàng lưu các sự kiện phát sinh từ đơn hàng:

- `OrderCreatedEvent`: đơn hàng được tạo, có `orderId` và `amountMinor`.
- `OrderCancelledEvent`: đơn hàng bị hủy, có `orderId` và `reason`.

Cả hai là `AuditEvent`, có cùng các field nền tảng như thời điểm phát sinh. Ta muốn lưu chúng vào **cùng collection `audit_events`**, rồi đọc danh sách chung nhưng vẫn nhận được đúng lớp con.

### 3.1. Lớp cha

File `AuditEvent.java`:

```java
package com.example.shop.audit;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "audit_events")
public abstract class AuditEvent {
    @Id
    private String id;
    private Instant occurredAt;

    protected AuditEvent() {}

    protected AuditEvent(Instant occurredAt) {
        this.occurredAt = occurredAt;
    }

    public String getId() {
        return id;
    }

    public Instant getOccurredAt() {
        return occurredAt;
    }
}
```

Lớp cha là abstract vì nghiệp vụ không tạo một “sự kiện chung” không có loại. Các thuộc tính kế thừa như `id` và `occurredAt` được Spring Data MongoDB mapping cùng với thuộc tính riêng của lớp con.

### 3.2. Lớp con: tạo đơn

File `OrderCreatedEvent.java`:

```java
package com.example.shop.audit;

import java.time.Instant;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "audit_events")
@TypeAlias("order_created_v1")
public class OrderCreatedEvent extends AuditEvent {
    private String orderId;
    private long amountMinor;

    protected OrderCreatedEvent() {}

    public OrderCreatedEvent(
            Instant occurredAt, String orderId, long amountMinor) {
        super(occurredAt);
        this.orderId = orderId;
        this.amountMinor = amountMinor;
    }

    public String getOrderId() {
        return orderId;
    }

    public long getAmountMinor() {
        return amountMinor;
    }
}
```

### 3.3. Lớp con: hủy đơn

File `OrderCancelledEvent.java`:

```java
package com.example.shop.audit;

import java.time.Instant;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "audit_events")
@TypeAlias("order_cancelled_v1")
public class OrderCancelledEvent extends AuditEvent {
    private String orderId;
    private String reason;

    protected OrderCancelledEvent() {}

    public OrderCancelledEvent(
            Instant occurredAt, String orderId, String reason) {
        super(occurredAt);
        this.orderId = orderId;
        this.reason = reason;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getReason() {
        return reason;
    }
}
```

**Điểm cần nhớ:** cả hai lớp con khai báo cùng `@Document(collection = "audit_events")` nhằm làm rõ collection đích khi thực hiện thao tác theo kiểu cụ thể. Annotation `@TypeAlias` chỉ quyết định tên kiểu được lưu trong metadata; nó không tự đặt collection.

### 3.4. Lưu và đọc bằng MongoTemplate

File service minh họa:

```java
package com.example.shop.audit;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class AuditEventService {
    private final MongoTemplate mongoTemplate;

    public AuditEventService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void appendDemoEvents() {
        mongoTemplate.insert(
            new OrderCreatedEvent(
                Instant.parse("2026-11-20T01:00:00Z"),
                "ORD-100", 350000L),
            "audit_events"
        );
        mongoTemplate.insert(
            new OrderCancelledEvent(
                Instant.parse("2026-11-20T02:00:00Z"),
                "ORD-101", "Khách đổi ý"),
            "audit_events"
        );
    }

    public List<AuditEvent> loadAll() {
        return mongoTemplate.findAll(
            AuditEvent.class, "audit_events");
    }
}
```

Trong database, hai document có thể trông như sau:

```javascript
// Document 1
{
  _id: ObjectId("66a000000000000000000011"),
  occurredAt: ISODate("2026-11-20T01:00:00Z"),
  orderId: "ORD-100",
  amountMinor: NumberLong(350000),
  _class: "order_created_v1"
}

// Document 2
{
  _id: ObjectId("66a000000000000000000012"),
  occurredAt: ISODate("2026-11-20T02:00:00Z"),
  orderId: "ORD-101",
  reason: "Khách đổi ý",
  _class: "order_cancelled_v1"
}
```

Giá trị `_class` là alias do `@TypeAlias` cung cấp thay cho FQCN của hai lớp con. Khi mapping context biết hai alias, lời gọi `findAll(AuditEvent.class, "audit_events")` có thể khôi phục đúng `OrderCreatedEvent` và `OrderCancelledEvent`.

Ví dụ xử lý kết quả:

```java
for (AuditEvent event : service.loadAll()) {
    if (event instanceof OrderCreatedEvent created) {
        System.out.println(
            "Created " + created.getOrderId()
            + ": " + created.getAmountMinor());
    } else if (event instanceof OrderCancelledEvent cancelled) {
        System.out.println(
            "Cancelled " + cancelled.getOrderId()
            + ": " + cancelled.getReason());
    }
}
```

Đoạn trên giả định biến `service` là một instance của `AuditEventService` và Java hỗ trợ pattern matching cho `instanceof`. Trong logic nghiệp vụ thực tế, có thể tách xử lý theo từng loại sự kiện thay vì tập trung tất cả vào một vòng lặp.

### 3.5. Repository cho lớp cha

Có thể khai báo repository chung:

```java
package com.example.shop.audit;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface AuditEventRepository
        extends MongoRepository<AuditEvent, String> {
}
```

Repository này có domain type là `AuditEvent`, nhưng collection chứa nhiều kiểu con. Khi đọc, việc tạo đúng subtype vẫn phụ thuộc type hint và mapping context. Repository không tự suy luận biến thể từ `reason` hay `amountMinor` nếu thiếu metadata phù hợp.

Nếu các loại sự kiện có vòng đời, index hoặc quyền truy cập rất khác nhau, dùng **collection riêng cho từng loại** cũng có thể phù hợp hơn. Đặt nhiều lớp vào cùng collection là quyết định thiết kế dữ liệu, không phải yêu cầu bắt buộc của kế thừa Java.

## 4. @TypeAlias hoạt động như thế nào?

Annotation nằm ở `org.springframework.data.annotation.TypeAlias`, áp dụng lên **lớp mapping**, ví dụ:

```java
@TypeAlias("order_created_v1")
public class OrderCreatedEvent extends AuditEvent {
    // ...
}
```

So sánh document khi có và không có alias:

| Cấu hình | Giá trị `_class` minh họa | Đặc điểm |
| --- | --- | --- |
| Mặc định, không có `@TypeAlias` | `com.example.shop.audit.OrderCreatedEvent` | Gắn chặt với tên package/lớp Java |
| Có `@TypeAlias("order_created_v1")` | `order_created_v1` | Ngắn hơn, có thể giữ ổn định khi refactor Java |
| Tắt ghi type hint qua `DefaultMongoTypeMapper(null)` | Không có `_class` được ghi bởi mapper | Phải giải quyết việc đọc subtype bằng cơ chế khác |

### 4.1. Chọn alias ổn định, duy nhất

Một alias nên:

- Có ý nghĩa rõ trong phạm vi ứng dụng, ví dụ `order_created_v1` hoặc `payment_card_v1`.
- **Duy nhất** giữa các lớp được mapping context biết đến, tránh cùng một alias chỉ đến hai kiểu Java.
- Được coi như một phần của định dạng dữ liệu đã lưu; giữ nguyên qua refactor package nếu hành vi dữ liệu không đổi.
- Được thay đổi có kiểm soát khi cần version mới của định dạng lưu trữ.

Không cần tăng version mỗi lần thay tên phương thức hoặc chuyển file Java. Hậu tố `_v1` trong ví dụ chỉ thể hiện chủ ý versioning của ứng dụng, không phải quy định của framework.

### 4.2. @TypeAlias không giống @Field hay @Document

```java
@Document(collection = "audit_events") // collection đích
@TypeAlias("order_created_v1")         // giá trị metadata kiểu
public class OrderCreatedEvent extends AuditEvent {

    @Field("order_ref")               // tên field trong BSON
    private String orderId;
}
```

Đoạn riêng lẻ này minh họa sự khác nhau của annotation; nếu áp dụng `@Field("order_ref")` vào code ở phần 3, BSON mới sẽ dùng `order_ref` thay vì `orderId`. Không nên thay tên field của model đang chạy mà không đánh giá dữ liệu cũ.

| Annotation | Ảnh hưởng |
| --- | --- |
| `@Document(collection = "...")` | Xác định collection dùng khi lưu/đọc entity theo kiểu Java |
| `@Id` | Ánh xạ thuộc tính định danh Java sang `_id` |
| `@Field("...")` | Đổi tên hoặc tinh chỉnh metadata field BSON |
| `@TypeAlias("...")` | Đặt mã kiểu để Spring Data lưu/đọc thay cho tên lớp đầy đủ |

Không có annotation nào ở trên tự tạo quan hệ khóa ngoại hay cấu trúc kế thừa phía MongoDB server.

## 5. Metadata _class của đối tượng lồng nhau

Không chỉ document gốc mới cần type hint. Xét một đơn giao hàng có trường `destination` khai báo là interface. Lúc lưu, giá trị thực tế có thể là email hoặc webhook.

File `Destination.java`:

```java
package com.example.shop.delivery;

public interface Destination {
}
```

File `EmailDestination.java`:

```java
package com.example.shop.delivery;

import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.mongodb.core.mapping.Document;

@Document
@TypeAlias("destination_email_v1")
public record EmailDestination(String address)
        implements Destination {
}
```

File `WebhookDestination.java`:

```java
package com.example.shop.delivery;

import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.mongodb.core.mapping.Document;

@Document
@TypeAlias("destination_webhook_v1")
public record WebhookDestination(String endpoint)
        implements Destination {
}
```

File `DeliveryJob.java`:

```java
package com.example.shop.delivery;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "delivery_jobs")
public record DeliveryJob(
    @Id String id,
    String message,
    Destination destination
) {
}
```

Ví dụ ghi qua repository/`MongoTemplate`:

```java
var job = new DeliveryJob(
    null,
    "Đơn hàng đã được giao",
    new EmailDestination("contact@example.com")
);

mongoTemplate.insert(job);
```

Đoạn này giả định có biến `MongoTemplate mongoTemplate` được inject trong service. Document minh họa:

```javascript
{
  _id: ObjectId("66a000000000000000000013"),
  message: "Đơn hàng đã được giao",
  destination: {
    address: "contact@example.com",
    _class: "destination_email_v1"
  },
  _class: "com.example.shop.delivery.DeliveryJob"
}
```

Ở đây **`destination._class` xác định lớp triển khai interface** `Destination`. Nếu viết:

```java
DeliveryJob restored =
    mongoTemplate.findById(id, DeliveryJob.class);

if (restored != null
        && restored.destination() instanceof EmailDestination email) {
    System.out.println(email.address());
}
```

thì `id` là giá trị định danh đã có của document. Bộ chuyển đổi dùng metadata ở vị trí lồng nhau để tạo `EmailDestination` thay vì cố khởi tạo interface `Destination`.

**Vì sao ví dụ đánh dấu `@Document` trên hai lớp lồng nhau?** Trong ứng dụng có cấu hình quét entity của Spring Data, annotation này giúp các subtype được phát hiện và đăng ký metadata khi khởi động. Nó **không** có nghĩa MongoDB tự tách `destination` thành document ở collection riêng: field vẫn được nhúng vào `delivery_jobs`. Nếu dự án dùng cơ chế cấu hình mapping context riêng, phải bảo đảm các subtype có mặt trong initial entity set hoặc được đăng ký phù hợp.

### 5.1. Khi nào nested _class không xuất hiện?

Spring Data không bắt buộc ghi `_class` ở mọi object con. Khi kiểu được khai báo đủ cụ thể và mapper không cần giữ một kiểu thực tế khác kiểu được khai báo, có thể không có type hint ở vị trí đó. Vì thế, không nên xây logic nghiệp vụ với giả định “mọi object lồng nhau luôn có `_class`”.

Ngược lại, khi một field khai báo là `Destination` nhưng lưu `EmailDestination`, metadata kiểu thường cần thiết để khôi phục subtype bằng cơ chế mặc định. Quyết định tắt metadata phải tính cả các field lồng nhau, không chỉ document gốc.

## 6. Điều kiện để đọc được alias sau khi khởi động lại

`@TypeAlias` **không** tạo ra một bảng alias toàn cục trên MongoDB server. Việc ánh xạ chuỗi alias sang class Java nằm ở `MongoMappingContext` và cơ chế type mapper của ứng dụng.

Một vấn đề dễ bị bỏ sót:

1. Ứng dụng A ghi `_class: "destination_email_v1"`.
2. Ứng dụng A tắt và khởi động lại.
3. Ứng dụng mới đọc `delivery_jobs` trước khi từng ghi một `EmailDestination`.
4. Nếu mapping context **chưa biết** class chứa `@TypeAlias("destination_email_v1")`, việc phân giải alias có thể không thành công.

Để tránh phụ thuộc vào việc “ghi trước rồi đọc”, cần bảo đảm Spring Data mapping context nhận diện các lớp cụ thể ngay từ khởi động. Có thể thực hiện bằng cơ chế entity scanning phù hợp với cấu hình Spring Boot/Spring Data của dự án, hoặc thiết lập **initial entity set** chứa các subtype. Khi dùng `@Document` trên subtype như ví dụ, cần xác nhận package của chúng thực sự nằm trong vùng entity scan.

**Lưu ý:** `@EnableMongoRepositories` quét interface repository, không đồng nghĩa đăng ký tất cả subtype để phân giải `@TypeAlias`. Phạm vi quét repository, component scan và entity/mapping scan là những cơ chế khác nhau.

## 7. Lớp cha, lớp con và _class: những tình huống đọc cụ thể

| Tình huống đọc | Có type hint hợp lệ | Không có type hint |
| --- | --- | --- |
| Đọc document trực tiếp thành `OrderCreatedEvent.class` | Mapper có thể dùng metadata và ánh xạ sang lớp con | Thường vẫn có thể khởi tạo lớp cụ thể nếu các field phù hợp |
| Đọc document thành `AuditEvent.class` (abstract) | Có thể chọn đúng subclass đã đăng ký | Có thể thất bại vì không biết lớp cụ thể nào để tạo |
| Field `Destination` khai báo là interface | Có thể chọn `EmailDestination` hoặc `WebhookDestination` | Không thể tự suy ra subtype đáng tin cậy chỉ từ interface |
| Document có `_class` alias nhưng alias không đăng ký | Mapper không phân giải được subtype như mong muốn | Cần khai báo/đăng ký ánh xạ kiểu hoặc cơ chế chuyển đổi tùy chỉnh |
| Document cũ có FQCN đã bị đổi hoặc xóa | Đọc phụ thuộc khả năng phân giải lớp cũ | Cần chiến lược tương thích hoặc migration |

Không nên giả định rằng Spring Data sẽ quyết định subtype bằng cách “thấy field `reason` thì là sự kiện hủy”. Nếu muốn suy luận như vậy phải viết converter/logic riêng và kiểm thử các trường hợp thiếu field, thay đổi schema và giá trị không hợp lệ.

### 7.1. Đọc cùng collection bằng kiểu khác nhau

Ví dụ:

```java
// Đọc ở mức lớp cha: phù hợp khi cần xử lý nhiều subtype.
List<AuditEvent> all = mongoTemplate.findAll(
    AuditEvent.class, "audit_events");

// Đọc một lớp cụ thể: cần hiểu collection có những loại document nào.
List<OrderCreatedEvent> created = mongoTemplate.findAll(
    OrderCreatedEvent.class, "audit_events");
```

**Cẩn trọng với câu thứ hai:** một lời gọi đọc trực tiếp vào `OrderCreatedEvent.class` không đương nhiên là một bộ lọc discriminator nghiệp vụ an toàn cho collection đa kiểu. Hãy thêm điều kiện lọc rõ ràng hoặc thiết kế repository/query phù hợp; nếu không, dữ liệu của subtype khác có thể bị ánh xạ sai hoặc phát sinh lỗi tùy metadata và phiên bản converter.

Khi bộ lọc cần bền vững với refactor hoặc tương tác nhiều ngôn ngữ, dùng field `eventType` riêng thay vì trói hoàn toàn truy vấn nghiệp vụ vào `_class`.

## 8. Có nên tắt _class?

Đôi khi ứng dụng muốn document BSON không phụ thuộc vào Java hoặc muốn schema gọn cho dịch vụ nhiều ngôn ngữ. Spring Data MongoDB hỗ trợ tùy chỉnh `MongoTypeMapper`; cách thường được nhắc đến là:

```java
import org.springframework.data.mongodb.core.convert.DefaultMongoTypeMapper;
import org.springframework.data.mongodb.core.convert.MappingMongoConverter;

// Gọi khi tạo/cấu hình converter trước lúc sử dụng để đọc/ghi.
public static void disableTypeHints(MappingMongoConverter converter) {
    converter.setTypeMapper(new DefaultMongoTypeMapper(null));
}
```

Đây là **phương thức minh họa**, đặt bên trong một class cấu hình Java và gọi khi tạo/cấu hình converter trước khi sử dụng; nó chưa phải một bean Spring hoàn chỉnh. `DefaultMongoTypeMapper(null)` dùng để **không ghi field type discriminator mặc định**. Việc tạo một bean `MappingMongoConverter` thực tế cần phối hợp `MongoDatabaseFactory`, `MongoMappingContext`, custom conversions và auto-configuration của ứng dụng. Thay converter tùy tiện có thể vô hiệu hóa hoặc thay đổi phần cấu hình sẵn có.

### 8.1. Điều gì thay đổi khi bỏ _class?

Giả sử ta đọc `AuditEvent` abstract hoặc `Destination` interface. Khi không có type hint, mapper mặc định thiếu thông tin để chọn lớp con. Có một số hướng thiết kế:

- **Tránh polymorphism tại vùng lưu trữ:** mỗi collection chỉ dùng một lớp cụ thể, truy vấn rõ kiểu.
- **Dùng field discriminator nghiệp vụ ổn định:** lưu `eventType`/`destinationType` và triển khai converter đọc/ghi phù hợp.
- **Đọc bằng concrete type khi đã biết:** chọn đúng lớp cụ thể từ API hoặc điều kiện truy vấn, không cần suy ra từ interface.
- **Giữ type hint tại nơi cần thiết:** không nhất thiết xóa metadata để tiết kiệm vài byte nếu chi phí phức tạp và rủi ro đọc sai cao hơn.

Việc giảm kích thước một field `_class` thường không phải nguyên nhân chính khiến truy vấn chậm. Hiệu năng còn phụ thuộc index, kích thước document, projection, mô hình truy vấn và số lượt gọi database. Nên đo đạc trước khi đưa ra quyết định thay toàn bộ cơ chế mapping.

### 8.2. Đổi tên field metadata, không chỉ giá trị

`MongoTypeMapper` có thể được cấu hình với khóa type hint khác:

```java
// Đặt trong class cấu hình, áp dụng trên converter đã tạo:
public static void useCustomHintField(MappingMongoConverter converter) {
    converter.setTypeMapper(new DefaultMongoTypeMapper("javaType"));
}
```

Khi đó field được dùng làm discriminator kỹ thuật là `javaType` thay vì `_class`. Điều này **thay đổi định dạng document lưu trữ**; các document cũ dùng `_class` có thể không được xử lý tương đương nếu không có chiến lược tương thích hoặc migration. `@TypeAlias` chỉ quyết định **giá trị**, còn `DefaultMongoTypeMapper("javaType")` thay đổi **tên field**.

## 9. Tương thích ngược và migration khi thay class hoặc alias

Với dữ liệu tồn tại nhiều năm, các thay đổi Java có thể ảnh hưởng trực tiếp tới `_class`:

| Thay đổi | Nếu lưu FQCN | Nếu dùng alias ổn định |
| --- | --- | --- |
| Đổi tên package | Document cũ trỏ tới tên lớp cũ | Alias có thể tiếp tục ánh xạ tới class mới nếu được đăng ký |
| Đổi tên class | Có nguy cơ không tìm thấy kiểu cũ | Thường không ảnh hưởng nếu giữ alias và schema tương thích |
| Xóa một subtype | Document cũ có thể không đọc được | Vẫn cần lớp/converter thay thế tương ứng |
| Đổi alias từ `order_created_v1` sang `order_created_v2` | Không liên quan nếu vốn không dùng alias | Phải hỗ trợ hoặc chuyển đổi dữ liệu dùng alias cũ |
| Đổi tên field/kiểu BSON | Cần migration/converter phù hợp | Alias **không** tự giải quyết thay đổi schema |

### 9.1. Kiểm tra những kiểu đang được lưu

Trong `mongosh`:

```javascript
db.audit_events.aggregate([
  { $group: { _id: "$_class", count: { $sum: 1 } } },
  { $sort: { count: -1 } }
])
```

Kết quả có thể gồm alias mới, FQCN cũ, giá trị khác thường và nhóm thiếu `_class`. Trước khi migration, cần xác định toàn bộ nơi có metadata: root document, object lồng nhau và array chứa nhiều subtype.

### 9.2. Ví dụ đổi metadata từ FQCN sang alias

Giả sử một số document cũ từng lưu:

```javascript
{ _class: "com.example.shop.audit.OrderCreatedEvent", orderId: "ORD-100" }
```

Một lệnh migration cho **root** document có thể là:

```javascript
db.audit_events.updateMany(
  { _class: "com.example.shop.audit.OrderCreatedEvent" },
  { $set: { _class: "order_created_v1" } }
)
```

Lệnh này chỉ đổi `_class` trên document gốc khớp điều kiện; **không** chuyển đổi type hint nằm trong object lồng nhau hoặc array. Nó cũng không chứng minh các document còn lại đã tương thích với lớp Java mới.

Quy trình triển khai an toàn nên gồm:

1. **Thống kê dữ liệu trước:** có bao nhiêu document theo từng `_class`, alias nào đang tồn tại và có các vị trí lồng nhau nào.
2. **Định nghĩa định dạng đích:** alias mới, kiểu Java cụ thể, mapping field và phiên bản tương thích.
3. **Bảo đảm giai đoạn chuyển tiếp:** nếu nhiều phiên bản ứng dụng cùng chạy, các reader phải đọc được dữ liệu có cả dạng cũ và mới; có thể cần giữ class/converter tương thích.
4. **Thử migration trên dữ liệu đại diện:** kiểm tra cả root và nested type hint, các document không đầy đủ, đặc biệt dữ liệu có inheritance.
5. **Triển khai migration được kiểm soát và quan sát lỗi:** bảo đảm có phương án sao lưu/khôi phục và không chạy nhiều lần gây sai lệch.
6. **Kiểm tra sau khi đổi:** đọc document bằng repository/template trong phiên bản ứng dụng mới; đối chiếu số lượng document và kiểu trả về.

Nếu đã chuyển package khiến FQCN cũ không còn tồn tại, chỉ thêm `@TypeAlias` vào class mới **không tự động** biến mọi chuỗi FQCN cũ thành alias mới. Cần cơ chế tương thích hoặc cập nhật dữ liệu thực sự.

## 10. Tác động tới truy vấn, aggregation và index

`_class` là một field BSON có thể được nhìn thấy và truy vấn bằng `mongosh`:

```javascript
db.audit_events.find(
  { _class: "order_created_v1" },
  { orderId: 1, amountMinor: 1, occurredAt: 1, _class: 1 }
)
```

Nếu nghiệp vụ thường lọc theo loại sự kiện và thời điểm, có thể cân nhắc index phù hợp:

```javascript
db.audit_events.createIndex({
  _class: 1,
  occurredAt: -1
})
```

Tuy nhiên:

- Index trên `_class` phụ thuộc vào chiến lược metadata hiện tại; thay alias hoặc tắt metadata sẽ ảnh hưởng câu truy vấn.
- Với dashboard, audit hoặc API cần phân loại lâu dài, trường `eventType` tường minh thường dễ quản trị, di chuyển dữ liệu và sử dụng từ các dịch vụ khác.
- Index mang chi phí ghi và dung lượng; chỉ tạo khi có truy vấn thực tế cần nó.
- Aggregation trên MongoDB làm việc với document BSON. Một pipeline `$match` không hiểu kế thừa Java trừ khi điều kiện được đưa vào pipeline cụ thể.

Kiểm tra kế hoạch thực thi:

```javascript
db.audit_events
  .find({ _class: "order_created_v1" })
  .sort({ occurredAt: -1 })
  .limit(20)
  .explain("executionStats")
```

Đọc các chỉ số như `totalDocsExamined`, `totalKeysExamined` và thời gian thực thi trên tập dữ liệu đại diện. Một collection chỉ có vài document không đủ để đánh giá lợi ích của index.

## 11. Những hiểu lầm thường gặp

| Nhận định dễ sai | Thực tế | Hướng xử lý |
| --- | --- | --- |
| “MongoDB cần `_class` để lưu document” | `_class` là metadata do Spring Data mapping tạo ra | Không gán ý nghĩa bắt buộc của database server cho field này |
| “`@TypeAlias` đổi tên collection” | Alias chỉ thay giá trị type hint | Dùng `@Document(collection = "...")` để chọn collection |
| “Lớp cha abstract đọc được document không có `_class`” | Không thể mặc định biết subtype phải khởi tạo | Giữ type hint hoặc dùng converter/discriminator khác |
| “Mọi object lồng nhau đều có `_class`” | Hint có thể chỉ xuất hiện khi cần biểu diễn kiểu thực tế | Kiểm tra BSON thật và quy tắc mapping |
| “Đổi package khi đã có alias thì luôn an toàn” | Alias giúp ổn định metadata nhưng các field và cách đọc vẫn phải tương thích | Kiểm thử lại dữ liệu tồn tại và subtype registration |
| “`@TypeAlias` tự động migrate `_class` cũ” | Annotation không sửa các BSON document đã ghi | Thiết kế migration hoặc khả năng đọc cả định dạng cũ |
| “Tắt `_class` luôn tăng tốc đáng kể” | Hiệu năng còn do schema, index, truy vấn, số lượt đọc và ghi | Đo hiệu năng và đánh giá chi phí mất polymorphism |
| “`@EnableMongoRepositories` đã đăng ký mọi alias” | Repository scan và entity/mapping discovery khác nhau | Bảo đảm subtype được mapping context biết đến ngay từ lúc đọc |
| “Lọc `findAll(Subclass.class)` thay cho điều kiện nghiệp vụ” | Chọn kiểu Java đích không phải luôn là discriminator query | Thêm bộ lọc cụ thể, cân nhắc field loại nghiệp vụ ổn định |

## 12. Kiểm thử ánh xạ polymorphic

Một kiểm thử đơn vị chỉ tạo trực tiếp `new OrderCreatedEvent(...)` không chứng minh BSON được đọc về đúng subtype. Cần **round-trip test** trên MongoDB thật hoặc môi trường MongoDB kiểm thử phù hợp.

Ví dụ dùng Spring Boot Test, JUnit 5 và AssertJ:

```java
package com.example.shop.audit;

import java.time.Instant;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class AuditEventMappingTest {

    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void readsStoredAliasBackAsConcreteSubtype() {
        String orderId = "TEST-ORDER-909";

        OrderCreatedEvent saved = mongoTemplate.insert(
            new OrderCreatedEvent(
                Instant.parse("2026-11-20T00:00:00Z"),
                orderId, 100000L),
            "audit_events"
        );

        Document stored = mongoTemplate
            .getCollection("audit_events")
            .find(new Document("orderId", orderId))
            .first();

        assertThat(stored).isNotNull();
        assertThat(stored.getString("_class"))
            .isEqualTo("order_created_v1");

        AuditEvent restored = mongoTemplate.findById(
            saved.getId(), AuditEvent.class, "audit_events");

        assertThat(restored).isInstanceOf(OrderCreatedEvent.class);
        assertThat(((OrderCreatedEvent) restored).getOrderId())
            .isEqualTo(orderId);
    }
}
```

**Lưu ý về `_id` trong phép kiểm tra trực tiếp bằng driver:** ở ví dụ Java, `@Id String id` có thể được Spring Data chuyển thành BSON `ObjectId` khi giá trị phù hợp. `MongoTemplate.findById` xử lý chuyển đổi theo mapping, còn API `getCollection(...)` của driver làm việc trực tiếp với kiểu BSON. Vì vậy phép kiểm tra BSON phía trên tìm bằng `orderId` thay vì gán chuỗi Java vào bộ lọc `_id`. Dữ liệu test cần cô lập để `orderId` không trùng với document khác.

### 12.1. Ma trận kiểm thử nên có

| Trường hợp | Kỳ vọng |
| --- | --- |
| Ghi/readback `OrderCreatedEvent` | BSON có alias dự kiến, Java trả về đúng subtype và field kế thừa |
| Ghi/readback `OrderCancelledEvent` | Alias khác được phân giải đúng, không lẫn field |
| Ghi/readback `DeliveryJob` có `EmailDestination` | `destination._class` giúp đọc về đúng implementation |
| Ghi/readback `DeliveryJob` có `WebhookDestination` | Nhánh implementation còn lại được xử lý đúng |
| Khởi động context mới rồi đọc dữ liệu cũ | Alias đã được mapping context đăng ký, không phụ thuộc “ghi trước đọc sau” |
| Đọc document thiếu `_class` vào lớp abstract/interface | Ứng dụng có phản hồi kiểm soát được; không im lặng tạo object sai |
| Đọc document có alias không biết hoặc FQCN cũ | Có cách xử lý lỗi/tương thích đã định nghĩa |
| Đổi package Java nhưng giữ alias | Dữ liệu cũ vẫn đọc đúng nếu schema và metadata tương thích |

Với dự án Spring Data MongoDB, nên dùng instance MongoDB kiểm thử cô lập như Testcontainers nếu hạ tầng cho phép. Reactive access sử dụng `ReactiveMongoTemplate` hoặc reactive repository nhưng vẫn cần xác minh cùng hợp đồng BSON và cách phân giải subtype; khác biệt API reactive không tự loại bỏ nhu cầu mapping metadata.

## 13. Bài tập áp dụng

Một hệ thống thông báo có ba kênh gửi: email, SMS và webhook. Mỗi thông báo có `createdAt`, `userId`, `status` chung, trong khi mỗi kênh có field riêng (địa chỉ email, số điện thoại, URL webhook).

Hãy thử thiết kế:

1. Một lớp cha `Notification` (hoặc một interface hợp lý) và ba implementation có `@TypeAlias` riêng.
2. Quyết định lưu nhiều subtype trong collection `notifications` hay tách collection theo kênh; giải thích bằng cách đọc và cập nhật thường gặp.
3. Viết lời gọi `MongoTemplate` để lưu hai subtype và đọc về kiểu cha.
4. Kiểm tra BSON có `_class` đúng và xem xét trường hợp lịch sử dữ liệu thiếu field đó.
5. Mô tả chiến lược khi đổi tên package Java mà không làm hỏng các document cũ.

**Hướng giải tham khảo:** nếu ứng dụng cần một hàng đợi thông báo thống nhất, có thể giữ một collection và lưu alias như `notification_email_v1`, `notification_sms_v1`, `notification_webhook_v1`. Mỗi class con được mapping rõ ràng, đã được đăng ký với mapping context. Nếu các kênh có chu kỳ lưu giữ, index và tải ghi rất khác nhau, collection riêng có thể phù hợp hơn. Dù chọn cách nào, hãy kiểm tra round-trip BSON → Java và có kế hoạch tương thích dữ liệu lịch sử.

## Ghi nhớ

Field **`_class`** lưu thông tin kiểu mà Spring Data MongoDB có thể sử dụng khi ánh xạ document BSON thành đối tượng Java, đặc biệt quan trọng với **kế thừa và polymorphism**. **`@TypeAlias`** đặt tên kiểu ngắn và ổn định hơn FQCN nhưng không đổi collection, field nghiệp vụ hay dữ liệu đã ghi. Khi dùng nhiều subtype trong cùng collection hoặc trong object lồng nhau, hãy đảm bảo mapping context nhận diện các alias, bảo vệ khả năng đọc dữ liệu cũ và chỉ thay đổi cơ chế type hint khi đã có chiến lược chuyển đổi tương ứng.
