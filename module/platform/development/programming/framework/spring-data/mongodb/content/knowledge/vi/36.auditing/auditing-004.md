# DateTimeProvider, UTC và thời gian kiểm thử xác định

## 1. Một lỗi auditing khó phát hiện: thời gian phụ thuộc máy chủ

Một dịch vụ đặt hàng lưu thời gian tạo và cập nhật document trong MongoDB. Khi chạy ở máy phát triển, kiểm thử thấy createdAt và updatedAt hợp lý. Nhưng khi triển khai hai instance ở hai vùng hạ tầng hoặc khi CI chạy với múi giờ khác, các phép so sánh thời gian, log và test lại có kết quả không ổn định.

Ba vấn đề thường bị trộn với nhau:

1. **Thời gian đến từ đâu?** Có phải đồng hồ thật của máy đang chạy hay một nguồn thời gian được inject?
2. **Múi giờ được biểu diễn thế nào?** Java Instant, LocalDateTime, OffsetDateTime và BSON Date có semantics khác nhau.
3. **Kiểm thử có xác định không?** Test phụ thuộc Instant.now() thực có thể thất bại ngẫu nhiên hoặc phải sleep để đợi thời gian thay đổi.

Spring Data MongoDB auditing cung cấp một điểm mở rộng tên **DateTimeProvider**. Khi được đăng ký với **@EnableMongoAuditing(dateTimeProviderRef = "...")**, provider quyết định thời điểm auditing sử dụng để gắn **@CreatedDate** và **@LastModifiedDate**.

Một thiết kế dễ kiểm thử là:

~~~text
Clock.systemUTC() trong môi trường chạy thật
           |
           v
  DateTimeProvider được inject
           |
           v
 Spring Data AuditingEntityCallback
           |
           v
  @CreatedDate / @LastModifiedDate
           |
           v
 MappingMongoConverter -> BSON Date -> MongoDB
~~~

Trong bài này, **Clock** là nguồn thời gian, **DateTimeProvider** là cầu nối đến Spring Data auditing, còn **Instant** biểu diễn một thời điểm tuyệt đối, không phụ thuộc múi giờ hiển thị.

Bài **DateTimeProvider, UTC và thời gian kiểm thử xác định** thuộc chương **Auditing** của module **SPRING_DATA_MONGODB**. Module nghiên cứu cách kết nối, ánh xạ document và thao tác MongoDB qua MongoTemplate hoặc repository, đồng thời thực hành truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.

### 1.1. Mục tiêu

Sau bài, bạn có thể:

- Bật MongoDB auditing bằng **@EnableMongoAuditing**.
- Viết **DateTimeProvider** dựa trên **java.time.Clock**, sử dụng UTC rõ ràng.
- Dùng **Instant** cho @CreatedDate và @LastModifiedDate.
- Phân biệt thời điểm tuyệt đối và múi giờ hiển thị.
- Kiểm thử với **Clock.fixed** và nguồn giờ thay đổi có kiểm soát.
- Xác minh thời gian ở entity và **raw BSON Date**.
- Hiểu **modifyOnCreate**, **setDates**, thứ tự lifecycle callback và read/write conversion.
- Phân biệt auditing của **insert/save** với **MongoTemplate.updateFirst**, bulk và raw driver.
- Tránh flakiness, sai số mili giây, transaction retry, sai timezone và test dùng Thread.sleep.
- Mở rộng sang reactive auditing và chiến lược thời gian ở môi trường nhiều instance.

## 2. Auditing trong Spring Data MongoDB giải quyết gì?

Auditing là việc tự động ghi lại metadata của một bản ghi, ví dụ:

| Metadata | Annotation phổ biến | Ý nghĩa |
| --- | --- | --- |
| Thời điểm tạo | @CreatedDate | Khi entity được tạo theo lifecycle auditing |
| Thời điểm sửa gần nhất | @LastModifiedDate | Khi entity được save/update qua lifecycle có auditing |
| Người tạo | @CreatedBy | Principal/người tạo, qua AuditorAware |
| Người sửa | @LastModifiedBy | Principal/người sửa, qua AuditorAware |

Bài tập trung vào **thời gian**, không yêu cầu ứng dụng phải bật @CreatedBy/@LastModifiedBy.

### 2.1. Trường hợp sử dụng

Một document order có thể cần:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  orderNo: "ORD-001",
  status: "CREATED",
  createdAt: ISODate("2025-06-01T08:30:00.000Z"),
  updatedAt: ISODate("2025-06-01T08:30:00.000Z")
}
~~~

Khi save trạng thái mới:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  orderNo: "ORD-001",
  status: "PAID",
  createdAt: ISODate("2025-06-01T08:30:00.000Z"),
  updatedAt: ISODate("2025-06-01T08:35:00.000Z")
}
~~~

**createdAt** không đổi; **updatedAt** được cập nhật theo thời điểm auditing thấy lần ghi mới. Đây là mục tiêu thông thường, nhưng kết quả còn phụ thuộc cấu hình auditing, xác định entity mới/cũ và đường ghi thực tế.

### 2.2. Auditing không phải lịch sử thay đổi đầy đủ

Hai trường createdAt/updatedAt không ghi lại:

- Ai đã sửa từng field.
- Giá trị cũ và giá trị mới.
- Một save thất bại hoặc transaction bị rollback.
- Mọi update từ ứng dụng khác/raw MongoDB driver.
- Mọi phiên bản trung gian của document.

Muốn audit trail pháp lý hoặc event log, cần **append-only events, movement records hoặc change streams/outbox** tùy nghiệp vụ. Không dùng hai timestamp như bằng chứng đầy đủ của toàn bộ lịch sử.

## 3. Nắm rõ Instant, OffsetDateTime và LocalDateTime

Trước khi cấu hình DateTimeProvider, hãy quyết định kiểu thời gian lưu trữ.

| Kiểu Java | Mang thông tin gì? | Có phù hợp cho createdAt/updatedAt? |
| --- | --- | --- |
| Instant | Một điểm trên trục UTC timeline | **Rất phù hợp** |
| OffsetDateTime | Ngày-giờ cùng độ lệch UTC | Dùng được khi cần giữ offset, phải hiểu mapping |
| ZonedDateTime | Ngày-giờ và ZoneId/rules | Cần conversion/policy rõ |
| LocalDateTime | Ngày-giờ, **không có offset/zone** | Dễ sai nếu coi là timestamp toàn cục |
| LocalDate | Chỉ ngày, không có thời điểm | Phù hợp ngày nghiệp vụ, không đủ cho audit timestamp |
| java.util.Date | Thời điểm trên timeline với độ chính xác millisecond | Có thể dùng, nhưng API cũ |

### 3.1. Một Instant, nhiều cách hiển thị

~~~text
Instant UTC:       2025-06-01T08:30:00Z
Asia/Ho_Chi_Minh:  2025-06-01 15:30:00 +07:00
Europe/London:     biểu diễn tùy quy tắc DST tại thời điểm đó
~~~

**Hai cách hiển thị không phải hai thời điểm khác nhau.** Instant giữ thời điểm; ZoneId được áp dụng khi chuyển thành ngày/giờ cho người xem.

### 3.2. UTC không phải lời cam kết mọi máy luôn đúng giờ

**Clock.systemUTC()** sử dụng múi giờ UTC ở API java.time; nó **không tự đồng bộ đồng hồ hệ điều hành của các node**. Máy lệch đồng hồ vẫn có thể tạo timestamps sai. Hạ tầng cần NTP/time synchronization, quan sát clock drift và chính sách xử lý khi cần thứ tự sự kiện nghiêm ngặt.

### 3.3. Tránh LocalDateTime làm “thời điểm” mặc định

~~~java
LocalDateTime createdAt;
~~~

LocalDateTime chỉ mô tả ví dụ “08:30 ngày 1/6”, không nói đó là UTC hay múi giờ của người dùng. Khi chuyển sang Instant, phải chọn ZoneId/ZoneOffset; đổi zone có thể tạo thời điểm khác.

Với audit timestamps qua nhiều khu vực, **Instant** là lựa chọn gọn và ít nhập nhằng hơn.

## 4. BSON Date lưu dữ liệu như thế nào?

MongoDB BSON **Date** biểu diễn số mili giây kể từ Unix epoch, tương ứng một thời điểm tuyệt đối. Nó không lưu trực tiếp một ZoneId như **Asia/Ho_Chi_Minh**.

~~~javascript
{
  createdAt: ISODate("2025-06-01T08:30:00.000Z")
}
~~~

Khi đọc thành Java:

~~~java
java.util.Date rawDate =
    rawDocument.getDate("createdAt");

Instant createdAt = rawDate.toInstant();
~~~

### 4.1. Độ chính xác mili giây

Một Instant có thể có nanoseconds:

~~~text
2025-06-01T08:30:00.123456789Z
~~~

Nhưng BSON Date có độ chính xác **milliseconds**. Sau round-trip bằng BSON Date, ta thường còn:

~~~text
2025-06-01T08:30:00.123Z
~~~

Vì vậy, **không nên assert nanoseconds chưa được persist**. Với test chính xác, chọn một Instant có phần mili giây rõ ràng hoặc so sánh sau khi truncateTo(ChronoUnit.MILLIS).

### 4.2. Dấu Z là UTC offset

Trong chuỗi ISO-8601, ký hiệu **Z** nghĩa là UTC offset +00:00. Nó không có nghĩa document có một thuộc tính timezone nằm trong BSON Date.

### 4.3. Múi giờ người dùng ở tầng hiển thị

Nếu API trả ISO instant:

~~~json
{"createdAt":"2025-06-01T08:30:00Z"}
~~~

frontend có thể hiển thị 15:30 tại Việt Nam. Nếu nghiệp vụ cần ghi nhớ timezone nguồn/người dùng, lưu thêm field **businessZoneId** hoặc tương tự, thay vì cố nhúng ZoneId vào BSON Date.

## 5. Entity minh họa: @CreatedDate và @LastModifiedDate

~~~java
package com.example.auditing;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "audit_orders")
public class AuditedOrder {

    @Id
    private ObjectId id;

    private String tenantId;
    private String orderNo;
    private String status;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    public AuditedOrder() {}

    public AuditedOrder(
            ObjectId id, String tenantId,
            String orderNo, String status) {
        this.id = id;
        this.tenantId = tenantId;
        this.orderNo = orderNo;
        this.status = status;
    }

    public ObjectId getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getOrderNo() {
        return orderNo;
    }

    public String getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Mẫu này dùng **mutable class** để minh họa Spring Data auditing có thể cập nhật các trường được annotation. Với immutable entity/record, cần bảo đảm Spring Data constructor binding/property accessors và cách tạo bản sao phù hợp. Không mặc định mọi record không setter sẽ được auditing mutate theo cách giống mutable POJO.

### 5.1. Không set thời gian bằng getter hoặc JSON request

Các trường createdAt/updatedAt nên do server/database auditing policy quản lý. Không lấy giá trị auditing trực tiếp từ client nếu đó là metadata tin cậy của hệ thống.

### 5.2. ID và nhận diện entity mới

Spring Data cần phân biệt **new entity** và **existing entity** để quyết định created/modified audit fields. Có ID được gán sẵn, @Version, Persistable.isNew và một số đường insert/save có thể ảnh hưởng cách xác định trạng thái mới.

Các ví dụ kiểm thử sẽ cố tình dùng **insert** cho lần tạo đầu tiên và **save** cho lần sửa tiếp theo. Không kết luận chỉ từ “id != null” rằng mọi đường insert/save đều được auditing xử lý giống nhau.

## 6. DateTimeProvider là gì?

Interface **org.springframework.data.auditing.DateTimeProvider** trong Spring Data Commons cung cấp thời điểm auditing:

~~~java
package org.springframework.data.auditing;

import java.time.temporal.TemporalAccessor;
import java.util.Optional;

@FunctionalInterface
public interface DateTimeProvider {
    Optional<TemporalAccessor> getNow();
}
~~~

Đây là **chữ ký giải thích**, không phải interface cần tự định nghĩa lại trong ứng dụng.

- **getNow()** được framework gọi khi cần timestamp auditing.
- **Optional<TemporalAccessor>** cho phép trả nhiều loại thời gian thuộc java.time.
- **Instant** triển khai TemporalAccessor nên có thể đưa vào Optional.
- DateTimeProvider không định nghĩa cách đồng bộ đồng hồ; nguồn thời gian do ứng dụng lựa chọn.

### 6.1. Tại sao không gọi Instant.now() rải rác?

~~~java
// Hạn chế dùng thời gian thực trực tiếp trong mọi service:
order.setCreatedAt(Instant.now());
~~~

Các lời gọi Instant.now() rải rác:

- Khó thay bằng thời gian xác định trong test.
- Khó kiểm soát mọi layer dùng cùng một nguồn thời gian.
- Làm test phải tạo khoảng dung sai và đôi khi sleep.
- Không định nghĩa rõ timezone/policy khi code dùng LocalDateTime hoặc Date xen lẫn.

**Inject Clock** tạo ra một điểm quản lý thời gian được dùng thống nhất.

### 6.2. Optional.empty() có ý nghĩa gì?

DateTimeProvider có thể trả Optional.empty(), nhưng điều đó không phải cách chọn UTC. Nó biểu thị provider không cung cấp một giá trị thời gian cho lần gọi; cách auditing xử lý việc không có giá trị phải theo contract cụ thể.

Với các trường audit timestamp bắt buộc, hãy thiết kế provider trả một **Instant hợp lệ** và kiểm thử, thay vì cố ý trả rỗng để mong framework tự gán thời gian khác.

## 7. Cấu hình Clock UTC trong Spring

~~~java
package com.example.auditing;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfiguration {

    @Bean("auditClock")
    public Clock auditClock() {
        return Clock.systemUTC();
    }
}
~~~

**Clock.systemUTC()** làm rõ convention lấy thời gian cho auditing và cho phép thay bằng **Clock.fixed(...)** trong test.

### 7.1. Clock là một dependency bình thường

Service có thể nhận:

~~~java
import java.time.Clock;
import java.time.Instant;

public class OrderExpiryPolicy {

    private final Clock clock;

    public OrderExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean expired(Instant deadline) {
        return !Instant.now(clock).isBefore(deadline);
    }
}
~~~

Hàm này dùng cùng nguyên tắc: thời gian đến từ dependency, không phải giá trị toàn cục khó thay thế.

### 7.2. Một hệ thống có thể có nhiều Clock

Nếu app còn dùng Clock khác cho billing hoặc scheduling, sử dụng **@Qualifier("auditClock")** để xác định Clock dành cho auditing. Đừng mặc định có một Clock bean duy nhất trong mọi application context.

### 7.3. Clock.systemUTC không tự chuẩn hóa dữ liệu cũ

Đổi provider sang UTC không migrate những document đã lưu dưới dạng string/LocalDateTime hoặc các giá trị thời gian sai từ trước. Cần migration/backfill theo đánh giá dữ liệu riêng.

## 8. Đăng ký DateTimeProvider với @EnableMongoAuditing

~~~java
package com.example.auditing;

import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing(
    dateTimeProviderRef = "mongoAuditDateTimeProvider"
)
public class MongoAuditingConfiguration {

    @Bean("mongoAuditClock")
    public Clock mongoAuditClock() {
        return Clock.systemUTC();
    }

    @Bean("mongoAuditDateTimeProvider")
    public DateTimeProvider mongoAuditDateTimeProvider(
            @Qualifier("mongoAuditClock") Clock clock) {
        return () -> Optional.of(Instant.now(clock));
    }
}
~~~

**@EnableMongoAuditing** kích hoạt auditing infrastructure cho mapping MongoDB đồng bộ, và **dateTimeProviderRef** chỉ định chính xác bean cung cấp thời điểm audit.

### 8.1. Cấu trúc wiring

~~~mermaid
flowchart TD
    A["@EnableMongoAuditing(dateTimeProviderRef)"] --> B["Mongo auditing infrastructure"]
    C["Clock.systemUTC bean"] --> D["DateTimeProvider bean"]
    D --> B
    B --> E["AuditingEntityCallback"]
    E --> F["@CreatedDate / @LastModifiedDate"]
    F --> G["MappingMongoConverter -> BSON"]
~~~

### 8.2. Không tạo hai cấu hình auditing cạnh tranh

Nếu ứng dụng đã có một @EnableMongoAuditing do module khác khai báo, đừng thêm một cấu hình thứ hai một cách mù quáng. Hai cấu hình auditing có thể tạo sự mơ hồ về callback/provider, hoặc lựa chọn bean không như mong đợi.

Hãy có một **nguồn cấu hình chính**, khai báo bean names rõ và kiểm thử Spring ApplicationContext.

### 8.3. Chưa cần AuditorAware nếu chỉ audit date

**DateTimeProvider** dùng cho thời điểm. **AuditorAware** dùng cho createdBy/lastModifiedBy. Nếu chỉ khai báo @CreatedDate và @LastModifiedDate, không cần tạo giả một principal để có timestamps.

### 8.4. Vì sao provider trả Optional.of(Instant.now(clock))?

~~~java
return () -> Optional.of(Instant.now(clock));
~~~

Đây là một supplier lấy thời gian **khi auditing yêu cầu**, không phải một Instant chụp lúc application khởi động. Việc gọi Instant.now(clock) nằm bên trong lambda, vì vậy mỗi lần lấy có thể nhận giờ mới.

Sai ví dụ:

~~~java
Instant startup = Instant.now(clock);
return () -> Optional.of(startup);
~~~

Đoạn trên cố định thời điểm từ khi Spring context khởi tạo: mọi document có thể nhận cùng timestamp startup, dù người dùng tạo chúng nhiều giờ sau.

## 9. Cấu hình đầy đủ: repository, entity và save

Repository:

~~~java
package com.example.auditing;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface AuditedOrderRepository
        extends MongoRepository<AuditedOrder, ObjectId> {
}
~~~

Service:

~~~java
package com.example.auditing;

import org.bson.types.ObjectId;
import org.springframework.stereotype.Service;

@Service
public class AuditedOrderService {

    private final AuditedOrderRepository orders;

    public AuditedOrderService(AuditedOrderRepository orders) {
        this.orders = orders;
    }

    public AuditedOrder create(
            String tenantId, String orderNo) {
        AuditedOrder order = new AuditedOrder(
            null, tenantId, orderNo, "CREATED");
        return orders.insert(order);
    }

    public AuditedOrder markPaid(AuditedOrder order) {
        order.setStatus("PAID");
        return orders.save(order);
    }
}
~~~

Với auditing được bật, insert/save qua mapping lifecycle có thể gán **@CreatedDate** và **@LastModifiedDate** dựa trên DateTimeProvider.

### 9.1. Chọn method theo ý nghĩa

- **insert** biểu thị tạo document mới, lỗi nếu ID đã tồn tại.
- **save** có thể insert hoặc replace/update tùy nhận diện entity và semantics MongoTemplate/repository.
- Auditing phải biết entity đang **new** hay **existing** để phân biệt createdAt và updatedAt.

Không dùng **save** như một upsert không kiểm soát chỉ vì nó “ngắn gọn”, nhất là với entity có tenant, version và các invariant khác.

### 9.2. Trường hợp @Version và entity mới

Nếu entity có @Version, Spring Data có thể dùng version để xác định trạng thái mới. Điều này liên hệ đến auditing isNew detection. Trong use case cần chính xác, kiểm thử **insert -> save -> save** trên kiểu entity và version thực tế. Trong service ở trên, ta cố ý truyền **id=null** khi tạo entity; Spring Data sẽ xử lý ID trong quá trình insert. Nếu gán sẵn một ObjectId trước lần insert đầu tiên, cơ chế isNew dựa trên ID có thể coi entity là cũ, khiến @CreatedDate không được gắn như mong đợi dù lệnh insert thật sự tạo document mới. Khi buộc phải gán ID từ trước, hãy dùng @Version/Persistable hoặc chiến lược new-state phù hợp và kiểm thử.

### 9.3. Những trường hợp không đi qua service này

Raw MongoDB driver, job migration hoặc một ứng dụng khác có thể ghi vào cùng collection mà không biết DateTimeProvider của Spring. Auditing tự động của Spring không thay collection validation, quyền ghi hoặc quy ước timestamp của các hệ thống khác.

## 10. modifyOnCreate và setDates

**@EnableMongoAuditing** có các tùy chọn điều khiển việc đặt timestamp và việc cập nhật modified date khi entity mới được tạo.

Ví dụ khi muốn lúc tạo chỉ có createdAt, còn updatedAt để trống:

~~~java
@EnableMongoAuditing(
    dateTimeProviderRef = "mongoAuditDateTimeProvider",
    modifyOnCreate = false
)
~~~

Với cấu hình này, trường **@LastModifiedDate** không được tự điền tại thời điểm tạo nếu không có yếu tố khác gán giá trị. Sau một lần save của existing entity, updatedAt được đặt theo auditing.

### 10.1. Giá trị mặc định

Trong các phiên bản Spring Data thông dụng, **modifyOnCreate** mặc định là **true**. Khi đó một entity mới có thể nhận cả createdAt và updatedAt trong lần tạo đầu tiên.

**Không viết test mặc định đòi updatedAt == null** nếu chưa đặt modifyOnCreate=false.

### 10.2. setDates=false

~~~java
@EnableMongoAuditing(
    dateTimeProviderRef = "mongoAuditDateTimeProvider",
    setDates = false
)
~~~

Tùy chọn này tắt việc auditing tự gán date fields theo cấu hình auditing tương ứng. Đó **không phải** là lựa chọn “chỉ đổi timezone mà vẫn giữ timestamps tự động”.

Nếu đã tắt setDates, service hoặc database cần một cơ chế quản lý timestamps khác. Hãy hiểu rõ lý do trước khi tắt.

### 10.3. @CreatedBy và @LastModifiedBy độc lập với date provider

DateTimeProvider không quyết định username. Nếu muốn ghi người tạo/sửa, dùng **AuditorAware** (hoặc reactive counterpart tương ứng) và chính sách authentication có kiểm soát.

## 11. Auditing chạy trong lifecycle nào?

Trong Spring Data MongoDB mapping, auditing sử dụng **AuditingEntityCallback** ở giai đoạn **BeforeConvertCallback**. Tức là Spring có cơ hội gắn createdAt/updatedAt lên entity **trước khi MongoConverter tạo BSON Document**.

~~~mermaid
sequenceDiagram
    participant R as Repository/MongoTemplate
    participant A as AuditingEntityCallback
    participant P as DateTimeProvider
    participant M as MappingMongoConverter
    participant B as MongoDB
    R->>A: BeforeConvert(entity)
    A->>P: getNow()
    P-->>A: Optional(Instant)
    A-->>R: Entity có createdAt/updatedAt
    R->>M: Entity -> BSON Document
    M-->>R: createdAt/updatedAt dạng BSON Date
    R->>B: insert/save
    B-->>R: Write result
~~~

Các lifecycle events/callbacks khác có thể chạy trong pipeline; sơ đồ lược bỏ chúng để làm nổi bật vị trí date provider.

### 11.1. BeforeConvert khác BeforeSave

**BeforeSaveCallback** nhận cả entity và Document đã được chuyển đổi. Nếu chỉ thay entity.updatedAt trong BeforeSaveCallback, Document có thể vẫn chứa updatedAt cũ, vì converter không tự được gọi lại.

**AuditingEntityCallback** chạy trước conversion, nên timestamp gắn lên persistent entity được converter đưa xuống BSON.

### 11.2. Thứ tự với custom BeforeConvertCallback

Spring Data hỗ trợ callback ordering, và auditing callback có thứ tự của nó trong BeforeConvert phase. Nếu bạn còn một BeforeConvertCallback tự gán createdAt/updatedAt, hai callback có thể cạnh tranh.

Không xây hai cơ chế cùng sở hữu timestamp mà thiếu một hợp đồng rõ ràng về ordering. Tốt nhất để auditing sở hữu createdAt/updatedAt và custom callbacks xử lý metadata khác.

### 11.3. setDates và isNew

Auditing cần xác định entity mới/cũ. Nếu entity có ID gán trước, custom Persistable hoặc version, kết quả có thể khác. Kiểm thử với chính cấu trúc entity/ID policy của dự án, không dựa vào một quy tắc giản lược duy nhất.

## 12. Clock.fixed: loại bỏ sự phụ thuộc vào thời gian thực

Giả sử test cần một thời điểm được kiểm soát:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Instant expected = Instant.parse(
    "2025-06-01T08:30:00.123Z");

Clock fixed = Clock.fixed(expected, ZoneOffset.UTC);

Instant actual = Instant.now(fixed);

assert actual.equals(expected);
~~~

**Clock.fixed** luôn trả cùng một thời điểm cho các lần gọi instant() của chính clock đó. Test không phụ thuộc CPU speed, scheduling, múi giờ hệ điều hành hay giờ thực lúc chạy.

### 12.1. Kết nối Clock.fixed với DateTimeProvider

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import org.springframework.data.auditing.DateTimeProvider;

Clock fixed = Clock.fixed(
    Instant.parse("2025-06-01T08:30:00.123Z"),
    ZoneOffset.UTC
);

DateTimeProvider provider =
    () -> Optional.of(Instant.now(fixed));
~~~

Khi auditing gọi provider.getNow(), nó nhận Instant đã được cố định. Đây là cùng thiết kế như production, chỉ khác Clock được inject.

### 12.2. Tránh test dựa vào một khoảng dung sai tùy tiện

Phản ví dụ:

~~~java
Instant before = Instant.now();
repository.insert(order);
Instant after = Instant.now();

assertThat(saved.getCreatedAt())
    .isBetween(before, after);
~~~

Đây có thể là test hữu ích cho một integration smoke test trong một số trường hợp, nhưng dễ nhiễu do clock skew, precision, callback timing và môi trường CI. Nếu mục tiêu là chứng minh **provider đã được sử dụng**, so sánh với **một Instant cố định** rõ ràng hơn nhiều.

### 12.3. Test không cần sleep

Phản ví dụ khác:

~~~java
repository.insert(order);
Thread.sleep(1000);
repository.save(order);
~~~

Sleep tăng thời gian chạy và vẫn không đảm bảo behavior dưới tải hay môi trường clock giả lập. Đối với kiểm thử updatedAt thay đổi, điều khiển Clock/DateTimeProvider thay vì chờ đồng hồ thật trôi.

## 13. Test DateTimeProvider thuần, chưa cần MongoDB

Có thể bắt đầu với unit test nhỏ:

~~~java
package com.example.auditing;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.data.auditing.DateTimeProvider;

class DateTimeProviderUnitTest {

    @Test
    void returnsTheExactInstantFromInjectedClock() {
        Instant instant = Instant.parse(
            "2025-06-01T08:30:00.123Z");

        Clock clock = Clock.fixed(instant, ZoneOffset.UTC);
        DateTimeProvider provider =
            () -> Optional.of(Instant.now(clock));

        Optional<TemporalAccessor> result =
            provider.getNow();

        assertThat(result).isPresent();
        assertThat(Instant.from(result.orElseThrow()))
            .isEqualTo(instant);
        assertThat(clock.getZone())
            .isEqualTo(ZoneOffset.UTC);
    }
}
~~~

Test này chứng minh code provider đọc từ Clock được inject, không tự gọi Instant.now() không tham số. **Nó chưa chứng minh Mongo auditing infrastructure đã sử dụng bean đó**. Việc này cần integration test.

### 13.1. Vì sao Instant.from?

DateTimeProvider khai báo kiểu **TemporalAccessor**. **Instant.from(temporalAccessor)** chuyển một TemporalAccessor chứa đủ thông tin về instant trở lại Instant. Nếu provider trả **LocalDateTime** thì không thể tùy tiện chuyển thành Instant mà không biết offset/zone.

### 13.2. Test timezone của Clock

Một Clock có thể mang ZoneId khác, nhưng:

~~~java
Clock inHcm = Clock.fixed(
    Instant.parse("2025-06-01T08:30:00Z"),
    java.time.ZoneId.of("Asia/Ho_Chi_Minh"));

Instant sameMoment = Instant.now(inHcm);
~~~

**sameMoment** vẫn là **2025-06-01T08:30:00Z**. ZoneId của Clock ảnh hưởng các thao tác suy ra local date/time (như LocalDate.now(clock)), không thay đổi instant cơ sở.

Đây là lý do nên trả **Instant** cho auditing thay vì đổi sang LocalDateTime theo múi giờ máy.

## 14. Integration test với @DataMongoTest và Clock cố định

Để kiểm tra Spring Data thực sự sử dụng DateTimeProvider, tạo một MongoDB test slice có cấu hình auditing **dành riêng cho test**.

Ví dụ:

~~~java
package com.example.auditing;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.mongodb.config.EnableMongoAuditing;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import(FixedClockMongoAuditTest.AuditTestConfiguration.class)
class FixedClockMongoAuditTest {

    private static final Instant FIXED_INSTANT =
        Instant.parse("2025-06-01T08:30:00.123Z");

    @Autowired MongoTemplate template;

    @TestConfiguration
    @EnableMongoAuditing(
        dateTimeProviderRef = "fixedAuditDateTimeProvider")
    static class AuditTestConfiguration {

        @Bean("fixedAuditClock")
        Clock fixedAuditClock() {
            return Clock.fixed(
                FIXED_INSTANT, ZoneOffset.UTC);
        }

        @Bean("fixedAuditDateTimeProvider")
        DateTimeProvider fixedAuditDateTimeProvider(
                @Qualifier("fixedAuditClock") Clock clock) {
            return () -> Optional.of(Instant.now(clock));
        }
    }

    @Test
    void insertUsesFixedAuditInstantAndPersistsBsonDate() {
        AuditedOrder order = new AuditedOrder(
            null, "TEST-shop-a", "ORD-FIXED-001", "CREATED");

        ObjectId insertedId = null;
        try {
            AuditedOrder inserted = template.insert(order);
            insertedId = inserted.getId();

            assertThat(insertedId).isNotNull();
            assertThat(inserted.getCreatedAt())
                .isEqualTo(FIXED_INSTANT);
            assertThat(inserted.getUpdatedAt())
                .isEqualTo(FIXED_INSTANT);

            Document raw = template
                .getCollection("audit_orders")
                .find(new Document("_id", insertedId))
                .first();

            assertThat(raw).isNotNull();
            assertThat(raw.getDate("createdAt").toInstant())
                .isEqualTo(FIXED_INSTANT);
            assertThat(raw.getDate("updatedAt").toInstant())
                .isEqualTo(FIXED_INSTANT);
        } finally {
            if (insertedId != null) {
                template.remove(
                    Query.query(
                        Criteria.where("_id").is(insertedId)),
                    AuditedOrder.class
                );
            }
        }
    }
}
~~~

**Điều kiện:** chạy trên MongoDB test instance, dependency **spring-boot-starter-data-mongodb**, JUnit 5, Spring Boot Test, AssertJ; cấu hình môi trường test do dự án cung cấp (ví dụ Testcontainers). Không chạy test trên database production.

### 14.1. Vì sao dùng @TestConfiguration?

AuditTestConfiguration khai báo **Clock.fixed** và **DateTimeProvider** riêng cho test slice; không phải sửa cấu hình thời gian của production. Việc có @EnableMongoAuditing đảm bảo auditing được bật trong context đang kiểm thử.

Nếu ứng dụng test vô tình import thêm một cấu hình @EnableMongoAuditing khác, cần hợp nhất/điều chỉnh cấu hình test thay vì để hai cấu hình tranh quyền. Một context có một lựa chọn DateTimeProvider rõ ràng sẽ dễ kiểm soát hơn.

### 14.2. Vì sao để id=null trước insert?

Auditing phân biệt entity mới/cũ. Với entity mới kiểu POJO dùng @Id ObjectId và không có @Version, **id=null** giúp quá trình new-state detection không bị nhầm do ID đã được gán trước.

### 14.3. Vì sao so sánh raw BSON?

Nếu chỉ kiểm tra:

~~~java
assertThat(inserted.getCreatedAt())
    .isEqualTo(FIXED_INSTANT);
~~~

ta mới biết entity Java có giá trị. Đọc:

~~~java
raw.getDate("createdAt").toInstant()
~~~

chứng minh field thực đã được chuyển thành **BSON Date** và ghi vào MongoDB.

### 14.4. Precision của test

FIXED_INSTANT có **123 milliseconds**, không có phần nanosecond dư. Vì vậy, kỳ vọng **Instant trước/sau round-trip MongoDB bằng nhau chính xác**, không cần khoảng sai số.

Nếu test dùng Instant dạng .123456789Z, so sánh raw BSON sau khi truncate milliseconds theo chính sách conversion.

### 14.5. Test isolation

Ví dụ cleanup bằng ID thực được insert, chỉ trong test database. Để chạy test song song ổn định, nên dùng unique orderNo/tenant test hoặc một database/schema riêng cho suite.

## 15. Kiểm thử thời gian thay đổi mà không đợi thời gian trôi

Clock.fixed không thể “tiến lên” trong cùng instance. Để kiểm tra **createdAt giữ nguyên** và **updatedAt thay đổi**, có hai cách:

1. Dùng hai test application contexts với Clock.fixed ở hai thời điểm.
2. Dùng một **Clock có thể điều khiển** trong test, nhưng không bao giờ sử dụng class đó ở production.

Với một test kiểm tra cả insert và save trong cùng application context, cách 2 thuận tiện.

### 15.1. Clock có thể điều khiển, thread-safe

~~~java
package com.example.auditing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class AdjustableClock extends Clock {

    private final AtomicReference<Instant> now;
    private final ZoneId zone;

    public AdjustableClock(Instant initial) {
        this(new AtomicReference<>(
            Objects.requireNonNull(initial)),
            ZoneOffset.UTC);
    }

    private AdjustableClock(
            AtomicReference<Instant> now,
            ZoneId zone) {
        this.now = now;
        this.zone = zone;
    }

    public void setInstant(Instant instant) {
        now.set(Objects.requireNonNull(instant));
    }

    @Override
    public Instant instant() {
        return now.get();
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new AdjustableClock(now, newZone);
    }
}
~~~

**AtomicReference** giúp các lần đọc và cập nhật Instant có tính thread-safe cơ bản, nhưng không biến thứ tự thao tác nghiệp vụ thành transaction. Đây chỉ là một **test clock** có thể thay đổi có chủ đích.

### 15.2. Không dùng clock test như clock production

Production nên dùng Clock.systemUTC() hoặc một nguồn thời gian được tổ chức quản lý. Không để endpoint/debug command có thể gọi setInstant trên production auditing clock.

### 15.3. Vì sao withZone chia sẻ cùng AtomicReference?

Hai Clock khác zone có thể biểu diễn cùng một dòng thời gian. Bản test clock dùng chung **AtomicReference<Instant>**, nên khi thay instant, các instance dẫn xuất qua withZone đều quan sát cùng giá trị thời gian.

### 15.4. Clock cố định và Clock điều khiển giải quyết hai nhu cầu

| Nhu cầu test | Nguồn thời gian |
| --- | --- |
| Kiểm tra insert dùng đúng một thời điểm | Clock.fixed |
| Kiểm tra lần sửa thứ hai có thời gian mới | AdjustableClock |
| Kiểm tra business expiry sau 5 phút | AdjustableClock hoặc Clock.offset |
| Kiểm tra timezone presentation | Clock/ZoneId rõ + conversion |
| Kiểm tra độ bền BSON Date | Clock cố định ở millisecond |

Không cần **Thread.sleep** cho những bài kiểm thử này.

## 16. Integration test: createdAt không đổi, updatedAt tăng

Tạo một test slice khác với AdjustableClock và DateTimeProvider.

~~~java
package com.example.auditing;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.Optional;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.mongodb.config.EnableMongoAuditing;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import(AdvancingClockMongoAuditTest.AuditTestConfiguration.class)
class AdvancingClockMongoAuditTest {

    private static final Instant CREATED = Instant.parse(
        "2025-06-01T08:30:00.000Z");

    private static final Instant MODIFIED = Instant.parse(
        "2025-06-01T08:35:00.000Z");

    @Autowired MongoTemplate template;
    @Autowired AdjustableClock clock;

    @TestConfiguration
    @EnableMongoAuditing(
        dateTimeProviderRef = "advancingAuditDateTimeProvider")
    static class AuditTestConfiguration {

        @Bean
        AdjustableClock testAuditClock() {
            return new AdjustableClock(CREATED);
        }

        @Bean("advancingAuditDateTimeProvider")
        DateTimeProvider provider(AdjustableClock clock) {
            return () -> Optional.of(clock.instant());
        }
    }

    @Test
    void savePreservesCreatedDateAndAdvancesModifiedDate() {
        ObjectId savedId = null;
        clock.setInstant(CREATED);

        try {
            AuditedOrder order = template.insert(
                new AuditedOrder(
                    null, "TEST-shop-a",
                    "ORD-ADVANCING-001", "CREATED")
            );
            savedId = order.getId();

            assertThat(order.getCreatedAt())
                .isEqualTo(CREATED);
            assertThat(order.getUpdatedAt())
                .isEqualTo(CREATED);

            clock.setInstant(MODIFIED);
            order.setStatus("PAID");
            AuditedOrder changed = template.save(order);

            assertThat(changed.getCreatedAt())
                .isEqualTo(CREATED);
            assertThat(changed.getUpdatedAt())
                .isEqualTo(MODIFIED);

            Document raw = template
                .getCollection("audit_orders")
                .find(new Document("_id", savedId))
                .first();

            assertThat(raw).isNotNull();
            assertThat(raw.getString("status"))
                .isEqualTo("PAID");
            assertThat(raw.getDate("createdAt").toInstant())
                .isEqualTo(CREATED);
            assertThat(raw.getDate("updatedAt").toInstant())
                .isEqualTo(MODIFIED);
        } finally {
            if (savedId != null) {
                template.remove(
                    Query.query(
                        Criteria.where("_id").is(savedId)),
                    AuditedOrder.class
                );
            }
        }
    }
}
~~~

Test này tập trung vào **auditing qua insert rồi save** và không dùng giờ thật. Cả hai timestamps được so sánh bằng giá trị cụ thể và kiểm chứng lại trong MongoDB.

### 16.1. Vì sao dùng hai context test?

FixedClockMongoAuditTest và AdvancingClockMongoAuditTest có configuration riêng để không chia sẻ bean clock theo cách gây xung đột. Chúng là **hai test class độc lập** trong hai source files Java, mỗi class có một inner TestConfiguration phù hợp.

### 16.2. Nguy cơ context cache khi test chạy song song

Spring Test có cơ chế cache application context. Nếu nhiều test cùng thay đổi một AdjustableClock bean, kết quả có thể ảnh hưởng nhau. Với test ở trên, nên giữ suite cô lập, reset clock ở đầu case, không dùng chung mutable clock giữa những test có thể chạy song song, hoặc sử dụng context riêng theo cấu hình.

### 16.3. Kiểm thử modifyOnCreate=false

Nếu bật:

~~~java
@EnableMongoAuditing(
    dateTimeProviderRef = "advancingAuditDateTimeProvider",
    modifyOnCreate = false
)
~~~

thì assertion lúc insert nên đổi thành kỳ vọng **updatedAt chưa được tự gán** (giả sử entity khởi đầu null), còn sau save updatedAt nhận MODIFIED. Không copy cùng assertion của cấu hình mặc định sang test với modifyOnCreate=false.

## 17. Cách viết service testable mà không cần MongoDB

Ngay cả ngoài auditing, service có thể cần thời điểm phục vụ nghiệp vụ, ví dụ hạn thanh toán:

~~~java
package com.example.auditing;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public class PaymentDeadlinePolicy {

    private final Clock clock;

    public PaymentDeadlinePolicy(Clock clock) {
        this.clock = clock;
    }

    public Instant dueIn(Duration duration) {
        if (duration.isNegative()) {
            throw new IllegalArgumentException(
                "Duration must not be negative");
        }
        return Instant.now(clock).plus(duration);
    }
}
~~~

Unit test:

~~~java
Instant origin = Instant.parse(
    "2025-06-01T08:30:00Z");

PaymentDeadlinePolicy policy = new PaymentDeadlinePolicy(
    Clock.fixed(origin, java.time.ZoneOffset.UTC));

Instant deadline = policy.dueIn(
    java.time.Duration.ofMinutes(15));

assertThat(deadline).isEqualTo(
    Instant.parse("2025-06-01T08:45:00Z"));
~~~

**Cùng một Clock** có thể phục vụ auditing và các policy nghiệp vụ nếu có cùng yêu cầu về nguồn giờ. Nhưng cần phân biệt **thời gian thực hiện hành động** với **thời gian MongoDB commit** hoặc **thời gian event thực sự được xử lý downstream**.

## 18. UTC khi gửi API và hiển thị

Một API nên công bố rõ contract thời gian, ví dụ ISO-8601 UTC instant:

~~~json
{
  "id": "507f1f77bcf86cd799439011",
  "createdAt": "2025-06-01T08:30:00Z",
  "updatedAt": "2025-06-01T08:35:00Z"
}
~~~

Frontend có thể hiển thị:

~~~text
UTC:             2025-06-01 08:35
Asia/Ho_Chi_Minh: 2025-06-01 15:35
~~~

Hai dòng biểu thị cùng một Instant. Đừng convert sang local string rồi bỏ zone/offset nếu dữ liệu được chuyển qua các hệ thống khác.

### 18.1. Khi cần ngày nghiệp vụ

“Ngày giao hàng” hoặc “ngày lập báo cáo theo giờ cửa hàng” không phải lúc nào cũng là một UTC date. Nếu business rule định nghĩa ngày theo **Asia/Ho_Chi_Minh**, nên lưu hoặc xác định rõ **ZoneId của cửa hàng**, rồi chuyển Instant sang LocalDate theo zone đó khi tính ngày.

Không ép mọi LocalDate business field thành Instant midnight UTC mà không xem chính sách.

### 18.2. Lưu offset riêng khi thực sự cần

BSON Date không lưu offset gốc. Nếu phải biết khách đã xác nhận “15:35 +07:00”, có thể lưu **Instant + originalOffset/originalZoneId** theo hợp đồng nghiệp vụ. Tránh thêm offset chỉ để hiển thị khi frontend đã biết timezone người xem.

### 18.3. Không dùng string sorting cho ngày audit khi BSON Date phù hợp

Nếu các document lưu timestamp dạng ISO string không nhất quán offset/format, sort lexical có thể không phản ánh timeline theo cách mong muốn. Sử dụng **BSON Date** và index thời gian phù hợp, truy vấn bằng Instant/Date qua Spring mapping.

## 19. Timezone của JVM có liên quan thế nào?

Java có **systemDefault ZoneId**, có thể khác nhau ở máy lập trình, container và CI:

~~~java
java.time.ZoneId defaultZone =
    java.time.ZoneId.systemDefault();
~~~

Nếu code lấy:

~~~java
LocalDateTime.now();
~~~

thì giá trị phụ thuộc zone hệ thống. Nếu code lấy:

~~~java
Instant.now(clock);
~~~

thì nó xác định một instant từ Clock; hiển thị tại timezone khác là một bước riêng.

### 19.1. Đặt JVM timezone UTC có giải quyết mọi thứ không?

Đặt timezone JVM mặc định thành UTC có thể giảm một số lỗi conversion legacy. Nhưng nó không thay thế:

- Sử dụng Instant thay cho LocalDateTime khi biểu diễn timestamp.
- Inject Clock để test deterministic.
- Định nghĩa dateTimeProviderRef.
- Kiểm tra Java/BSON temporal converters.
- Quy ước business timezone cho ngày lịch/giờ cửa hàng.

Timezone JVM mặc định là một setting môi trường, còn DateTimeProvider là chính sách nguồn thời gian trong ứng dụng.

### 19.2. Tại sao LocalDateTime có thể tạo bug quanh DST?

Ở những vùng có Daylight Saving Time, có những local time không tồn tại hoặc lặp lại. LocalDateTime không mang ZoneId nên không đủ thông tin để xác định một instant duy nhất.

**Instant + ZoneId ở ranh giới hiển thị/nghiệp vụ** làm rõ lúc nào cần giải quyết quy tắc DST.

## 20. Auditing của entity save khác MongoTemplate.updateFirst

Đây là một trong những bẫy quan trọng nhất khi áp dụng auditing ở production.

~~~java
AuditedOrder order = repository.findById(id)
    .orElseThrow();
order.setStatus("PAID");
repository.save(order);
~~~

Trong đường **repository.save(entity)**, mapping lifecycle có thể chạy **AuditingEntityCallback** ở BeforeConvert và cập nhật trường **@LastModifiedDate**.

Nhưng:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(id)
        .and("tenantId").is(tenantId)
);

Update update = new Update()
    .set("status", "PAID");

mongoTemplate.updateFirst(
    query, update, AuditedOrder.class);
~~~

đây là **operator-based update**. Nó không tạo nguyên một entity rồi đưa qua BeforeConvertCallback như một save(entity) thông thường.

**Không mặc định DateTimeProvider được gọi để cập nhật @LastModifiedDate trong mọi updateFirst**, kể cả khi entity class có annotation.

### 20.1. Đồng bộ timestamp trong query update

Nếu app chọn **application clock** làm nguồn thời gian:

~~~java
import java.time.Clock;
import java.time.Instant;
import org.springframework.data.mongodb.core.query.Update;

Instant now = Instant.now(auditClock);

Update update = new Update()
    .set("status", "PAID")
    .set("updatedAt", now);
~~~

Khi đó service update rõ ràng **hai field**, nhưng cần có một helper/policy dùng cùng Clock như provider để các đường ghi không bất đồng với nhau.

### 20.2. Dùng $currentDate khi muốn giờ server

MongoDB hỗ trợ:

~~~javascript
db.audit_orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    tenantId: "shop-a"
  },
  {
    $set: { status: "PAID" },
    $currentDate: { updatedAt: true }
  }
);
~~~

Spring Data:

~~~java
new Update()
    .set("status", "PAID")
    .currentDate("updatedAt");
~~~

Lúc này **updatedAt do MongoDB Server xác định**, không phải Clock từ DateTimeProvider. Hai cơ chế có thể tạo mốc rất gần nhau nhưng không được suy rằng chúng luôn bằng chính xác.

### 20.3. Chọn một chính sách nhất quán

| Đường ghi | Chính sách timestamp |
| --- | --- |
| Repository.save(entity) | @LastModifiedDate qua DateTimeProvider |
| MongoTemplate.insert(entity) | @CreatedDate/@LastModifiedDate qua auditing lifecycle |
| MongoTemplate.updateFirst(query,update) | Set updatedAt từ Clock hoặc $currentDate |
| MongoTemplate.findAndModify(query,update) | Có chiến lược updatedAt tường minh |
| BulkOperations | Thêm updatedAt vào từng UpdateDefinition nếu cần |
| Raw MongoCollection.updateOne | Tự bổ sung field theo server policy |
| Writer ở ứng dụng khác | Chia sẻ hợp đồng schema/time hoặc database-side policy riêng |

**Không để một nửa document dùng application UTC và nửa còn lại dùng local JVM time mà không biết.** Nếu chọn nguồn app clock cho auditing và nguồn MongoDB server cho operator updates, phải chấp nhận chênh lệch có thể có và thiết kế comparison logic tương ứng.

### 20.4. Test phân biệt save và updateFirst

Integration test nên:

1. Chèn entity khi Clock=FIRST.
2. Dùng updateFirst khi Clock=SECOND mà **không set updatedAt**.
3. Xác nhận field updatedAt không tự đổi do auditing lifecycle.
4. Dùng updateFirst có **set("updatedAt", Instant.now(clock))**.
5. Xác nhận raw BSON Date đổi sang SECOND.
6. Dùng save(entity) khi Clock=THIRD và xác nhận @LastModifiedDate ở THIRD.

Test này quan trọng hơn việc chỉ kiểm tra annotation có tồn tại trong source.

## 21. Reactive auditing: @EnableReactiveMongoAuditing

Trong stack **ReactiveMongoTemplate/ReactiveMongoRepository**, Spring Data MongoDB có configuration annotation **@EnableReactiveMongoAuditing**.

~~~java
package com.example.auditing;

import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.mongodb.config.EnableReactiveMongoAuditing;

@Configuration
@EnableReactiveMongoAuditing(
    dateTimeProviderRef = "reactiveAuditDateTimeProvider")
public class ReactiveMongoAuditingConfiguration {

    @Bean("reactiveAuditClock")
    Clock reactiveAuditClock() {
        return Clock.systemUTC();
    }

    @Bean("reactiveAuditDateTimeProvider")
    DateTimeProvider reactiveAuditDateTimeProvider(
            @Qualifier("reactiveAuditClock") Clock clock) {
        return () -> Optional.of(Instant.now(clock));
    }
}
~~~

**DateTimeProvider ở đây vẫn là nguồn thời gian đồng bộ, nhẹ, không I/O**. Reactive auditing được tích hợp vào reactive entity mapping lifecycle; nó không có nghĩa phải dùng một Publisher để đọc đồng hồ.

### 21.1. Vì sao không gọi HTTP time server trong provider?

Nếu getNow() gọi network synchronously, nó có thể block đường ghi. Nếu cần đồng bộ với một nguồn thời gian bên ngoài, nên giải quyết ở hạ tầng clock synchronization hoặc một service/time policy có kiểm soát; DateTimeProvider nên trả timestamp nhanh và deterministic.

### 21.2. Reactive save chỉ thực thi khi subscribe

~~~java
Mono<AuditedOrder> write =
    reactiveMongoTemplate.insert(
        new AuditedOrder(
            null, "shop-a", "ORD-RX-001", "CREATED"));
~~~

Publisher này thường mô tả thao tác; auditing và insert xảy ra khi pipeline được **subscribe**, không phải khi biến write được tạo.

**Không tự subscribe() trong service** rồi trả lại cùng Mono cho WebFlux, vì có thể kích hoạt hai lần ghi/callback và gây duplicate key.

### 21.3. Reactive repository và auditing

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface ReactiveAuditedOrderRepository
        extends ReactiveMongoRepository<AuditedOrder, ObjectId> {
}
~~~

Repository reactive tham gia auditing mapping lifecycle theo cấu hình reactive. Tự tạo **MongoRepository** blocking để lấy timestamp trong một pipeline Reactor là sai mục tiêu của reactive access.

### 21.4. Test reactive bằng StepVerifier

~~~java
Instant fixed = Instant.parse(
    "2025-06-01T08:30:00.123Z");

StepVerifier.create(
    reactiveRepository.insert(new AuditedOrder(
        null, "TEST-shop-a", "ORD-RX-001", "CREATED"))
)
.assertNext(saved -> {
    assertThat(saved.getCreatedAt()).isEqualTo(fixed);
    assertThat(saved.getUpdatedAt()).isEqualTo(fixed);
})
.verifyComplete();
~~~

Đoạn trên giả định **ReactiveMongoAuditingConfiguration** trong test đã được cấu hình để DateTimeProvider dùng Clock.fixed(fixed, UTC), cùng **reactor-test** và repository bean đã inject. Không dùng nguyên cấu hình production Clock.systemUTC() rồi kỳ vọng test đúng fixed instant.

### 21.5. Reactive transaction là vấn đề khác

**@EnableReactiveMongoAuditing** chỉ bật auditing. Nếu một service cần ghi nhiều document cùng transaction, dùng **ReactiveMongoTransactionManager** và Reactive transactional context theo tài liệu; DateTimeProvider không thay thế transaction manager.

## 22. Auditing trong MongoDB transaction

Một service có thể ghi nhiều document:

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager"
)
public AuditedOrder createWithOutbox(
        AuditedOrder order) {
    AuditedOrder saved = orderRepository.insert(order);
    outboxRepository.insert(
        buildOrderCreatedEvent(saved));
    return saved;
}
~~~

Tại đây **orderRepository, outboxRepository, buildOrderCreatedEvent** là các thành phần nghiệp vụ cần được định nghĩa trong dự án.

Auditing timestamp được gắn khi mapper xử lý entity trong transaction. **Nó không đồng nghĩa thời điểm commit**; transaction còn có thể mất thời gian thực thi những bước sau.

### 22.1. Transaction rollback không đảo ngược đồng hồ

~~~text
T0: DateTimeProvider trả 08:30:00
T1: Order được map với createdAt=08:30:00
T2: Ghi Outbox lỗi
T3: Transaction rollback
~~~

Timestamp đã được tạo trong memory, nhưng document của transaction không commit. Nếu ứng dụng retry ở T4, provider có thể trả thời điểm khác, trừ khi dùng Clock.fixed hoặc một business-event timestamp được xác định riêng.

### 22.2. Retry có làm createdAt đổi không?

Nếu một lần thử transaction bị abort rồi thử lại như một new entity, DateTimeProvider có thể cung cấp thời điểm khác. Điều này thường phản ánh thời gian ghi attempt, không phải thời điểm client gửi request.

Nếu nghiệp vụ cần **requestedAt** cố định giữa các lần thử, hãy lưu một field nghiệp vụ **requestedAt** riêng được xác định từ đầu request, không ép @CreatedDate phải mang nghĩa đó.

### 22.3. Commit time và write time khác nhau

Timestamps được gắn ở callback/mapping time. Thời điểm commit thành công, thời điểm replica nhìn thấy document và thời điểm consumer xử lý event có thể khác. Đừng dùng updatedAt để kết luận chính xác “transaction commit lúc nào” nếu không có nguồn event/commit time phù hợp.

### 22.4. Tác dụng của write concern

Một document có updatedAt hợp lệ không chứng minh dữ liệu đã majority committed nếu cấu hình write concern không yêu cầu điều đó. DateTimeProvider chỉ cung cấp thời gian, còn độ bền dữ liệu do MongoDB write concern/transaction options quyết định.

## 23. Nhiều instance: UTC cần nhưng chưa đủ

Giả sử có hai instance:

~~~text
App A: đồng hồ +400ms so với thời gian chuẩn
App B: đồng hồ -300ms so với thời gian chuẩn
~~~

Cả hai đều dùng **Clock.systemUTC()**, nhưng timestamps được tạo vẫn có thể lệch nhau khoảng 700ms.

### 23.1. Tại sao không được dùng updatedAt làm sequence tuyệt đối?

Một event được xử lý sau có thể mang updatedAt nhỏ hơn event xử lý trước, do:

- Clock skew giữa node.
- Retry hoặc queue delays.
- Một transaction start sớm nhưng commit muộn.
- Precision chỉ tới milliseconds trong BSON Date.
- Hai event trùng timestamp.

**Timestamp không phải một sequence number duy nhất hoặc total order**.

Nếu cần điều kiện cạnh tranh:

- Dùng @Version/optimistic locking.
- Dùng update filter với expected state/version.
- Dùng unique operation ID.
- Dùng event sequence/transactional outbox phù hợp.

### 23.2. NTP/time synchronization

Production cần đồng bộ đồng hồ OS/container/VM, đo drift, cảnh báo khi lệch quá ngưỡng. Việc set ZoneId UTC cho Clock không sửa được clock drift.

### 23.3. Dùng server-generated time khi nào?

Nếu yêu cầu nguồn timestamp nhất quán hơn tại MongoDB cho một số operator updates, **$currentDate** hoặc update pipeline có **$$NOW** (theo server/API hỗ trợ) có thể phù hợp.

Nhưng khi đó nó **khác nguồn DateTimeProvider** trên app. Hãy quyết định và document policy: application time cho entity auditing hay database time cho write operations, cùng quy trình kiểm thử tương ứng.

### 23.4. TTL là một use case khác

MongoDB TTL cần trường kiểu **BSON Date** và TTL index phù hợp, nhưng TTL cleanup là bất đồng bộ. Nếu **expiresAt** là thời điểm hết hạn nghiệp vụ, service vẫn phải kiểm tra deadline khi xác thực, không chỉ đợi TTL xóa.

Không dùng @CreatedDate như một deadline có thể sửa trừ khi nghiệp vụ thật sự muốn expiration dựa trên thời điểm tạo.

## 24. Truy vấn theo khoảng thời gian UTC

Với order đã lưu **createdAt** dạng BSON Date, Spring Data có thể truy vấn từ Instant:

~~~java
import java.time.Instant;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Instant from = Instant.parse(
    "2025-06-01T00:00:00Z");

Instant to = Instant.parse(
    "2025-06-02T00:00:00Z");

Query query = Query.query(
    Criteria.where("tenantId").is("shop-a")
        .and("createdAt").gte(from).lt(to)
);
~~~

Đây là khoảng **[from, to)**: bao gồm đầu và loại trừ cuối. Nó tránh chồng lấp giữa hai ngày/khoảng liên tiếp.

### 24.1. Khi business day ở Việt Nam

Ngày 01/06 theo **Asia/Ho_Chi_Minh** là:

~~~text
Local start: 2025-06-01T00:00:00+07:00
UTC start:   2025-05-31T17:00:00Z
Local end:   2025-06-02T00:00:00+07:00
UTC end:     2025-06-01T17:00:00Z
~~~

Ví dụ:

~~~java
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId businessZone =
    ZoneId.of("Asia/Ho_Chi_Minh");

LocalDate day = LocalDate.of(2025, 6, 1);

Instant from = day.atStartOfDay(
    businessZone).toInstant();

Instant to = day.plusDays(1)
    .atStartOfDay(businessZone)
    .toInstant();
~~~

Lưu timestamp dưới UTC Instant, nhưng **tính ranh giới ngày theo business zone**. Không lấy day UTC rồi dùng nó cho mọi cửa hàng quốc tế.

### 24.2. DST và khoảng ngày

Ở vùng có DST, một ngày theo local zone có thể không dài đúng 24 giờ. Dùng **startOfDay của ngày hiện tại và startOfDay của ngày kế tiếp** theo ZoneId, thay vì cứ lấy from.plus(Duration.ofHours(24)) nếu mục tiêu là ngày địa phương.

### 24.3. Index

Nếu thường xuyên truy vấn order theo tenant và createdAt:

~~~javascript
db.audit_orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "idx_audit_orders_tenant_created" }
);
~~~

Index chọn theo filter, sort, cardinality và workload; không tạo index ở mọi audit field chỉ vì có annotation. Kiểm tra explain và chi phí index trên write-heavy collection.

## 25. Các lỗi hay gặp khi cấu hình DateTimeProvider

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| createdAt/updatedAt đều null | @EnableMongoAuditing chưa được bật, bean chưa scan hoặc entity không được nhận là new | Xem Spring context, entity state, test insert thật |
| createdAt null nhưng updatedAt có giá trị ở insert | ID gán trước làm isNew=false hoặc policy khác | Test isNew, dùng ID null lúc tạo hoặc Persistable/@Version phù hợp |
| Test luôn thấy một timestamp từ lúc app khởi động | Provider chụp Instant ở @Bean creation | Đặt Instant.now(clock) **bên trong** lambda |
| Test phụ thuộc giờ máy CI | Code gọi Instant.now() trực tiếp | Inject Clock.fixed từ test context |
| updatedAt bằng createdAt ở lần tạo | modifyOnCreate mặc định true | Nếu muốn khác, cấu hình modifyOnCreate=false |
| updatedAt null ở entity mới | modifyOnCreate=false, setDates=false hoặc init khác | Đối chiếu cấu hình và test |
| updatedAt không đổi khi updateFirst | Query update không đi qua BeforeConvert auditing | Set updatedAt hoặc $currentDate tường minh |
| updatedAt từ raw driver không theo Clock | Driver không biết DateTimeProvider | Áp timestamp policy cho từng writer |
| Timestamp lệch 7 giờ trong UI | Nhầm UTC instant với local time | Hiển thị bằng ZoneId, không thay Instant |
| Timestamp lệch giữa node dù cùng UTC | Clock drift | Đồng bộ giờ hạ tầng, theo dõi NTP |
| Assertion sai vài micro/nanosecond | BSON Date chỉ có milliseconds | Truncate đến millis hoặc dùng fixed millis |
| LocalDateTime đọc khác sau deploy | Default zone/JDK conversion khác | Dùng Instant và temporal conversion rõ |
| Test updatedAt không tăng | Clock.fixed luôn trả cùng giờ | Dùng AdjustableClock hoặc cố định hai context |
| Có hai DateTimeProvider beans | dateTimeProviderRef thiếu/sai hoặc nhiều config | Dùng bean name rõ, một auditing configuration |
| @CreatedBy trống dù date đã đúng | Chưa cấu hình AuditorAware | Tách policy actor và time |
| Reactive insert không nhận ngày | Bật auditing imperative thay vì reactive | @EnableReactiveMongoAuditing |
| Reactive test không chạy lệnh insert | Mono chưa được subscribe | StepVerifier/compose publisher |
| Test đọc entity đúng nhưng raw BSON sai type | Conversion hoặc raw writer | Kiểm tra raw.getDate và converter |
| Thời gian commit và createdAt khác | Timestamp gắn lúc callback trước commit | Phân biệt write preparation với commit instant |
| updatedAt giảm khi request mới chạy | Clock skew hoặc lần ghi từ snapshot/nguồn giờ khác | Không dùng timestamp như version; dùng @Version |
| DateTimeProvider block hoặc ném lỗi | Provider gọi network/time service | Dùng Clock nhẹ, fail-fast/monitor nguồn giờ |

### 25.1. Quy trình chẩn đoán một document không được audit

1. Xác định thao tác ghi: repository.insert/save, MongoTemplate.updateFirst hay raw driver?
2. Xem entity có đúng **@CreatedDate/@LastModifiedDate** và kiểu java.time tương thích không.
3. Kiểm tra **@EnableMongoAuditing / @EnableReactiveMongoAuditing** đã được đăng ký chưa.
4. Xác minh tên **dateTimeProviderRef** trỏ đúng DateTimeProvider bean.
5. Kiểm tra provider đọc **Instant.now(clock)** tại thời điểm getNow(), không phải startup.
6. Xác định entity được Spring Data nhận diện là **new** hay **existing**.
7. Đối chiếu **modifyOnCreate** và **setDates**.
8. Đọc raw BSON document để kiểm tra field name, BSON type và milliseconds.
9. Kiểm tra timezone conversion, client display và clock drift.
10. Dùng test Clock.fixed/AdjustableClock để tái hiện thay vì thêm sleep.

## 26. Những lỗi thường gặp trong kiểm thử thời gian

### 26.1. Dựa vào wall clock thay vì một giá trị xác định

~~~java
// Không nên nếu muốn assert chính xác:
assertThat(saved.getCreatedAt())
    .isEqualTo(Instant.now());
~~~

Hai lần gọi Instant.now() xảy ra tại **hai thời điểm khác nhau**, nên test có thể sai ngay cả khi auditing hoạt động đúng.

**Thay bằng** Clock.fixed cùng một Instant được inject cho provider.

### 26.2. Sleep để đợi updatedAt thay đổi

~~~java
// Không nên:
Thread.sleep(50);
~~~

Sleep làm test chậm và không chứng minh clock/provider được cấu hình. Dùng AdjustableClock.setInstant.

### 26.3. So sánh Instant nanosecond với BSON millisecond

~~~java
import java.time.temporal.ChronoUnit;

Instant expected = Instant.parse(
    "2025-06-01T08:30:00.123456789Z");

Instant expectedStored =
    expected.truncatedTo(ChronoUnit.MILLIS);
~~~

Sau BSON round-trip thông thường, so sánh với **expectedStored**, không đòi MongoDB giữ 456789 nanoseconds không có trong BSON Date.

### 26.4. Thay timezone hệ thống trong test chạy song song

~~~java
// Dễ gây nhiễu trên toàn JVM:
java.util.TimeZone.setDefault(
    java.util.TimeZone.getTimeZone("UTC"));
~~~

Thao tác này thay một state **global của JVM**, có thể ảnh hưởng test khác chạy song song. Thay vì đổi global timezone chỉ để test auditing, dùng **Clock.fixed(instant, ZoneOffset.UTC)** và explicit ZoneId trong conversion.

Nếu phải kiểm thử legacy code phụ thuộc systemDefault, nên chạy trong môi trường/process riêng hoặc cô lập nghiêm ngặt.

### 26.5. Dùng mutable clock singleton qua nhiều test class

Nếu cả suite cùng inject một AdjustableClock rồi các test cùng set giá trị, chúng sẽ gây race. Dùng context isolation, test resource scope hoặc tạo Clock mới cho test; không để thời gian của test A ảnh hưởng test B.

### 26.6. Mock DateTimeProvider nhưng không đăng ký vào auditing context

~~~java
DateTimeProvider provider = () ->
    Optional.of(fixedInstant);
~~~

Đoạn trên chỉ tạo một object Java. Nếu @EnableMongoAuditing đang trỏ đến bean khác, auditing sẽ không dùng provider này. Integration test phải xác nhận **bean name và wiring** thực.

### 26.7. Bỏ qua ngày creation với ID được gán sẵn

Khi dùng new ObjectId() trước insert, isNew detection có thể thấy ID đã có. Nếu test đang kiểm tra @CreatedDate, phải mô tả rõ ID strategy:

- ID null và được tạo trong insert path.
- Entity implement Persistable với isNew được quản lý.
- @Version dùng để hỗ trợ newness semantics.

Không giấu khác biệt này bằng một annotation khác mà không test.

## 27. Chiến lược kiểm thử theo tầng

| Tầng test | Đối tượng kiểm tra | Có cần MongoDB? |
| --- | --- | --- |
| Unit: Clock.fixed | Clock trả đúng Instant | Không |
| Unit: DateTimeProvider | Provider gọi Clock và trả TemporalAccessor | Không |
| Unit: time policy | Expiry/deadline tính đúng theo Clock | Không |
| Integration: @DataMongoTest | Provider được auditing infrastructure sử dụng | Có |
| Integration: raw BSON Date | Date mapping và millisecond precision | Có |
| Integration: create vs update | createdAt giữ nguyên, updatedAt đổi | Có |
| Integration: updateFirst | Không giả định callback được chạy | Có |
| Integration: reactive | Publisher auditing đúng và được subscribe | Có |
| Integration: multiple instances | Clock drift/consistency policy | Cần test hạ tầng hoặc fault injection |

### 27.1. Một ma trận test tối thiểu

~~~text
Case A — create, Clock=2025-06-01T08:30Z, modifyOnCreate=true
  expect createdAt=08:30Z, updatedAt=08:30Z

Case B — save existing, Clock=2025-06-01T08:35Z
  expect createdAt=08:30Z, updatedAt=08:35Z

Case C — create, modifyOnCreate=false
  expect createdAt=08:30Z, updatedAt không tự được gán

Case D — updateFirst(status only)
  expect updatedAt không tự đổi do AuditingEntityCallback

Case E — updateFirst(status + updatedAt)
  expect updatedAt được ghi theo policy đã chọn

Case F — BSON Date
  expect Instant sau round-trip đúng đến milliseconds

Case G — entity có ID preassigned
  expect behavior theo isNew policy thực, không suy đoán

Case H — timezone hiển thị
  expect cùng Instant khi đổi UTC sang Asia/Ho_Chi_Minh
~~~

### 27.2. Không nhầm chữ deterministic với “mock mọi thứ”

Mục tiêu là **kiểm soát nguồn thời gian**, không cần mock MongoTemplate, Spring converter và mọi auditing callback ở integration test. Một test đúng phải vẫn dùng MongoDB thật để xác minh mapping, trong khi Clock là dependency có thể thay.

### 27.3. Kiểm tra regression khi nâng cấp Spring Data

Khi thay Spring Boot/Spring Data MongoDB version, kiểm tra:

- Cấu hình auditing annotation và provider bean name.
- Cách xác định entity mới/cũ.
- Kiểu date mapping mặc định.
- Lifecycle callbacks được kích hoạt theo đường ghi.
- Thứ tự callback nếu có custom BeforeConvertCallback.
- Reactive auditing và các API imports.

Chạy ma trận integration tests thay vì chỉ kiểm tra compile thành công.

## 28. Bài tập thực hành

### Bài tập 1: chọn kiểu dữ liệu

Yêu cầu: lưu chính xác thời điểm document được tạo, không phụ thuộc múi giờ người xem. Chọn **Instant** hay **LocalDateTime**?

**Đáp án:** **Instant** biểu diễn một thời điểm tuyệt đối. LocalDateTime cần thêm offset/zone để chuyển thành instant và dễ nhập nhằng giữa máy.

### Bài tập 2: khai báo annotation

~~~java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant updatedAt;
~~~

**Câu hỏi:** Cần bật cấu hình nào?

**Đáp án:** @EnableMongoAuditing trong imperative stack hoặc @EnableReactiveMongoAuditing trong reactive stack, với dateTimeProviderRef nếu muốn provider tùy chỉnh.

### Bài tập 3: DateTimeProvider

Viết provider lấy thời gian từ một Clock inject:

~~~java
@Bean("mongoAuditDateTimeProvider")
DateTimeProvider provider(Clock clock) {
    return () -> Optional.of(Instant.now(clock));
}
~~~

**Đáp án:** Tạo thời gian **bên trong** getNow lambda, không lấy một lần lúc tạo bean.

### Bài tập 4: UTC

Instant là **2025-06-01T08:30:00Z**. Ở Asia/Ho_Chi_Minh (UTC+7), hiển thị lúc nào?

**Đáp án:** **2025-06-01 15:30:00** cùng ngày. Đó vẫn là cùng một thời điểm.

### Bài tập 5: startup clock bug

~~~java
Instant startup = Instant.now(clock);
return () -> Optional.of(startup);
~~~

Lỗi là gì?

**Đáp án:** Mỗi lần auditing đều trả timestamp startup. Cần gọi Instant.now(clock) bên trong lambda.

### Bài tập 6: fixed test

~~~java
Clock fixed = Clock.fixed(
    Instant.parse("2025-06-01T08:30:00Z"),
    ZoneOffset.UTC);
~~~

Gọi Instant.now(fixed) 100 lần trả gì?

**Đáp án:** Cùng một Instant **2025-06-01T08:30:00Z**, không phụ thuộc thời gian thực.

### Bài tập 7: thay đổi ngày modified

Bạn cần test createdAt=08:30 và updatedAt=08:35 trong cùng test mà không sleep. Giải pháp?

**Đáp án:** Inject AdjustableClock vào DateTimeProvider, đặt 08:30 khi insert và 08:35 trước save existing entity.

### Bài tập 8: modifyOnCreate

@LastModifiedDate có được điền ngay lúc entity mới được tạo không?

**Đáp án:** Trong cấu hình phổ biến modifyOnCreate=true, **có**. Nếu muốn không điền khi tạo mới, đặt modifyOnCreate=false và kiểm thử.

### Bài tập 9: setDates=false

Bạn bật @EnableMongoAuditing(setDates=false) và kỳ vọng createdAt vẫn được gán bởi DateTimeProvider. Giả định đúng không?

**Đáp án:** Không. setDates=false tắt việc auditing tự gán date fields theo cấu hình đó.

### Bài tập 10: ID preassigned

Entity có @Id ObjectId đã được gán từ trước, không có @Version. @CreatedDate có chắc được điền khi gọi insert?

**Đáp án:** Không chắc. Auditing newness detection có thể xem entity là existing vì ID khác null. Cần test và chọn chiến lược như id=null lúc tạo, @Version hoặc Persistable.isNew.

### Bài tập 11: BSON precision

Bạn persist Instant **2025-06-01T08:30:00.123456789Z** vào BSON Date. Phần nanosecond có được giữ nguyên không?

**Đáp án:** Không. BSON Date có precision milliseconds, nên thông thường chỉ còn **.123Z**.

### Bài tập 12: updateFirst

Service gọi:

~~~java
mongoTemplate.updateFirst(
    query,
    new Update().set("status", "PAID"),
    AuditedOrder.class
);
~~~

Có thể kỳ vọng @LastModifiedDate tự đổi không?

**Đáp án:** Không. Query update không tự chạy auditing BeforeConvert entity save. Cần update timestamp rõ, bằng Clock app hoặc $currentDate server.

### Bài tập 13: $currentDate

Sự khác biệt giữa:

~~~java
new Update().set("updatedAt", Instant.now(clock));
~~~

và:

~~~java
new Update().currentDate("updatedAt");
~~~

là gì?

**Đáp án:** Dòng đầu lấy thời gian ứng dụng từ Clock; dòng sau để MongoDB Server gán current date. Hai nguồn có thể lệch nhau.

### Bài tập 14: auditing và transaction

Transaction ghi Order, rồi Outbox insert lỗi khiến rollback. createdAt đã được provider tạo trong JVM. MongoDB có lưu Order hay không?

**Đáp án:** Không commit Order nếu transaction đã abort đúng cách. Timestamp được tính trong memory không đồng nghĩa record đã persist.

### Bài tập 15: createdAt không phải commit time

Transaction bắt đầu 08:30:00, callback gắn createdAt=08:30:01, nhưng commit xong 08:30:03. createdAt là gì?

**Đáp án:** Theo callback/provider ở thời điểm lấy giá trị, **08:30:01**, không phải 08:30:03.

### Bài tập 16: hai node đều UTC

Node A nhanh hơn giờ chuẩn 400ms, node B chậm hơn 300ms. Clock.systemUTC có tự sửa lệch đó không?

**Đáp án:** Không. UTC là zone convention, không phải clock synchronization; cần NTP/monitoring.

### Bài tập 17: snapshot không phải version

Hai update có cùng updatedAt milliseconds. Có thể dùng updatedAt để đảm bảo mọi update có thứ tự duy nhất không?

**Đáp án:** Không. Dùng @Version, expected state hoặc sequence number/idempotency key khi cần xử lý đồng thời.

### Bài tập 18: ngày cửa hàng tại Việt Nam

Ngày 01/06/2025 theo Asia/Ho_Chi_Minh bắt đầu vào UTC lúc nào?

**Đáp án:** **2025-05-31T17:00:00Z**. Cần convert startOfDay theo ZoneId của cửa hàng, không dùng UTC midnight.

### Bài tập 19: reactive auditing

Ứng dụng dùng ReactiveMongoRepository nhưng chỉ bật @EnableMongoAuditing. Có chắc reactive auditing được kích hoạt không?

**Đáp án:** Không. Dùng cấu hình @EnableReactiveMongoAuditing thích hợp và kiểm thử Reactor Publisher thực.

### Bài tập 20: unit và integration

Unit test DateTimeProvider trả Instant đúng. Đã đủ chứng minh field createdAt được lưu thành BSON Date không?

**Đáp án:** Chưa. Cần @DataMongoTest/installation test, gọi insert/save và kiểm tra raw BSON Date.

### Bài tập 21: TimeZone.setDefault

Một test sửa TimeZone global của JVM sang UTC để mong tính ổn định. Có rủi ro gì?

**Đáp án:** Ảnh hưởng các test khác và mã legacy cùng JVM; trong test song song có thể gây race. Nên inject Clock và chỉ chuyển ZoneId khi hiển thị.

### Bài tập 22: document từ hệ thống khác

Một job MongoDB raw driver ghi createdAt dạng String và updatedAt không có. DateTimeProvider của Spring có tự sửa document đó không?

**Đáp án:** Không. Raw writer bỏ qua auditing infrastructure; phải có schema policy/migration riêng.

## 29. Checklist triển khai

- **Nguồn giờ:** DateTimeProvider nhận Instant từ Clock được inject chưa?
- **UTC:** Clock.systemUTC được dùng theo policy đã thống nhất chưa?
- **Kiểu dữ liệu:** persisted audit timestamps dùng Instant/BSON Date chưa?
- **Bean name:** dateTimeProviderRef chỉ đúng bean chưa?
- **Lifecycle:** @EnableMongoAuditing hoặc @EnableReactiveMongoAuditing đúng stack chưa?
- **New state:** entity ID/Version/Persistable dẫn tới isNew đúng chưa?
- **Create:** createdAt gắn khi insert; modifyOnCreate theo yêu cầu chưa?
- **Update:** updatedAt đổi trên save; query updates có policy riêng chưa?
- **setDates:** không vô tình vô hiệu hóa auditing dates chưa?
- **Multi-writer:** các ứng dụng khác/raw driver có cùng schema/time policy chưa?
- **Precision:** test và API hiểu BSON Date chỉ có milliseconds chưa?
- **Timezones:** không dùng LocalDateTime như instant toàn cục chưa?
- **Business dates:** ngày lịch được tính theo ZoneId nghiệp vụ chưa?
- **Clock drift:** hạ tầng đồng bộ đồng hồ và theo dõi lệch giờ chưa?
- **Concurrency:** không dùng updatedAt như một version/sequence duy nhất chưa?
- **Transaction:** phân biệt callback time và commit time chưa?
- **Retry:** event requestedAt và document createdAt có semantics riêng chưa?
- **Reactive:** service không block hoặc tự subscribe hai lần chưa?
- **Test fixed:** có test Clock.fixed + DateTimeProvider đúng thời điểm không?
- **Test advancing:** có test createdAt giữ nguyên và updatedAt thay đổi không cần sleep không?
- **Test BSON:** có đọc raw getDate/toInstant sau insert/save không?
- **Test isolation:** mutable Clock không bị chia sẻ giữa các test song song chưa?
- **Operations:** index theo tenant/date, monitoring, cleanup policy phù hợp chưa?

## 30. Tổng kết

1. **DateTimeProvider** là cơ chế Spring Data auditing lấy thời điểm, được cấu hình qua **dateTimeProviderRef**.
2. **Clock.systemUTC()** giúp quy ước nguồn thời gian rõ ràng; **Clock.fixed** cho test deterministic.
3. **Instant** biểu diễn một thời điểm tuyệt đối; **LocalDateTime** không mang zone/offset và dễ gây nhầm lẫn.
4. **BSON Date** lưu số milliseconds từ epoch, không lưu ZoneId gốc.
5. **@CreatedDate** và **@LastModifiedDate** được cập nhật qua auditing lifecycle khi entity được xử lý đúng đường insert/save và new-state detection phù hợp.
6. **modifyOnCreate** quyết định có gắn LastModifiedDate ở thời điểm tạo; **setDates=false** tắt tự gán date metadata.
7. **AuditingEntityCallback chạy trước conversion**, khác với BeforeSaveCallback chạy sau khi Document đã tạo.
8. **Clock.fixed/AdjustableClock** cho phép kiểm thử create/update mà không lệ thuộc giờ thực hoặc Thread.sleep.
9. **Integration test** cần xác nhận provider wiring, timestamp trên entity và giá trị BSON Date thực.
10. **MongoTemplate.updateFirst/findAndModify/bulk/raw driver** không tự tương đương save(entity) auditing; cần cập nhật timestamp rõ trên các đường ghi.
11. **$currentDate** lấy giờ server; **Instant.now(clock)** lấy giờ app. Chọn chính sách nguồn thời gian có chủ đích.
12. **ReactiveMongoRepository** cần auditing configuration reactive thích hợp và một Publisher chain được subscribe đúng.
13. **UTC không thay NTP**; timestamp không thay optimistic locking hoặc operation ID.
14. **createdAt không đồng nghĩa transaction commit time**; một giao dịch rollback có thể đã tính timestamp trong memory nhưng không commit document.
15. **Timezone người dùng và ngày nghiệp vụ** nên được xử lý ở ranh giới hiển thị/tính toán với ZoneId rõ ràng.

Nắm chắc **DateTimeProvider, UTC và thời gian kiểm thử xác định** giúp dịch vụ **SPRING_DATA_MONGODB** tạo timestamps có nguồn gốc rõ ràng, kiểm thử được chính xác và giữ cùng một quy ước giữa entity mapping, repository, MongoTemplate, reactive access và các ứng dụng chạy nhiều instance.

### Tài liệu tham khảo

- [Spring Data MongoDB — Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html) — bật auditing, @CreatedDate, @LastModifiedDate và cấu hình.
- [Spring Data MongoDB — EnableMongoAuditing API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/config/EnableMongoAuditing.html) — dateTimeProviderRef, modifyOnCreate, setDates.
- [Spring Data MongoDB — EnableReactiveMongoAuditing API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/config/EnableReactiveMongoAuditing.html) — auditing trong reactive stack.
- [Spring Data Commons — DateTimeProvider API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/auditing/DateTimeProvider.html) — Optional<TemporalAccessor> và getNow().
- [Spring Data MongoDB — Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html) — AuditingEntityCallback và BeforeConvert lifecycle.
- [Spring Data MongoDB — MongoTemplate CRUD](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html) — insert/save/query-based update operators.
- [Java SE — Clock API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html) — systemUTC, fixed, offset và thời gian test.
- [MongoDB Manual — BSON Date](https://www.mongodb.com/docs/manual/reference/bson-types/#date) — BSON Date biểu diễn milliseconds từ Unix epoch.
