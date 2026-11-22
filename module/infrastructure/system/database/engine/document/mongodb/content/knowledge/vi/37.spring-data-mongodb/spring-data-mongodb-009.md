# Auditing, thời gian tạo sửa và callback vòng đời trong Spring Data MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Spring Data MongoDB  
> **Bài học:** Auditing, thời gian tạo sửa và callback vòng đời

## 1. Bài toán: ai đã tạo, ai đã sửa và mã nào thực sự chạy trước khi lưu?

Một dịch vụ Java quản lý đơn hàng sử dụng Spring Boot, Spring Data MongoDB và MongoDB replica set. Mỗi document cần có metadata:

- `createdAt`: thời điểm tạo.
- `updatedAt`: thời điểm sửa gần nhất.
- `createdBy`: danh tính actor tạo document.
- `updatedBy`: danh tính actor sửa document.
- `version`: phiên bản phục vụ optimistic locking.

Nghe có vẻ chỉ cần bốn annotations. Nhưng ngay khi hệ thống có nhiều cách cập nhật dữ liệu, các câu hỏi trở nên quan trọng:

1. `repository.save(entity)` tự cập nhật timestamps như thế nào?
2. `mongoTemplate.updateFirst(...)` có chạy auditing giống `save()` không?
3. `MongoRepository.save()` với ID được cấp sẵn được phân loại là insert hay update?
4. Có thể lấy actor từ `SecurityContextHolder` ở HTTP request, scheduled job và async worker không?
5. Nên đặt normalize/validate dữ liệu vào `BeforeConvertCallback` hay `BeforeSaveCallback`?
6. Nếu callback gửi Kafka event rồi transaction rollback, điều gì xảy ra?
7. Tại sao `@CreatedDate` có thể bị gán lại trong một số flow lưu entity mới?
8. Khi dùng reactive repository, có được sử dụng `AuditorAware` đồng bộ không?
9. Nếu raw MongoDB driver cập nhật collection, annotations còn có hiệu lực không?
10. Có cần một audit log bất biến riêng cho yêu cầu compliance hay không?

Spring Data MongoDB cung cấp **auditing infrastructure** để tự điền metadata trên một số đường lưu entity, cùng **entity lifecycle callbacks** để can thiệp vào quá trình chuyển đổi, lưu và đọc document. Các cơ chế đó thuận tiện, nhưng **không phải database triggers**, không thay thế change history và không áp dụng cho mọi đường ghi dữ liệu.

### 1.1. Kiến trúc tổng quan

```text
HTTP request / scheduled job
             │
             ▼
Service layer: validate actor + business input
             │
             ▼
MongoRepository.save / MongoTemplate.save
             │
             ├── xác định entity mới/cũ (isNew)
             │
             ├── BeforeConvert event
             │
             ├── BeforeConvert callbacks
             │     ├── custom normalize/validate
             │     └── AuditingEntityCallback
             │          createdAt/updatedAt
             │          createdBy/updatedBy
             │
             ├── MappingMongoConverter
             │     POJO -> BSON Document
             │
             ├── BeforeSave event/callbacks
             │     BSON Document đã được tạo
             │
             ├── MongoDB write
             │
             └── AfterSave event/callbacks
                         │
                         ▼
                  entity trả về
```

Khi đọc:

```text
MongoDB BSON Document
          │
          ├── AfterLoad event
          ├── MappingMongoConverter (BSON -> entity)
          ├── AfterConvert event/callbacks
          ▼
       Java entity
```

Thứ tự event/callback và khả năng hỗ trợ phụ thuộc API và phiên bản; bài này sẽ giải thích các điểm cần kiểm soát để không gán sai trách nhiệm cho từng hook.

### 1.2. Mục tiêu học tập

Sau bài này, bạn có thể:

- Thiết lập `@EnableMongoAuditing` và bốn annotations audit.
- Viết `AuditorAware<String>` từ Spring Security.
- Hiểu mặc định `setDates` và `modifyOnCreate`.
- Dùng `Instant`, `DateTimeProvider` và `Clock` có kiểm soát.
- Phân biệt `BeforeConvertCallback`, `BeforeSaveCallback`, `AfterSaveCallback`, `AfterConvertCallback` và lifecycle events.
- Chọn chính xác callback để normalize, validate, thêm metadata hoặc enrich entity đọc.
- Biết `updateFirst`, `updateMulti`, `findAndModify`, repository `@Update`, bulk writes và raw driver có thể bỏ qua entity auditing.
- Xử lý actor identity trong imperative, reactive, batch và async contexts.
- Thiết kế optimistic locking với `@Version` và test concurrency.
- Kiểm thử auditing thực sự trên database, không chỉ giả lập annotations.
- Tránh sử dụng timestamps như một audit history bất biến.

---

## 2. Auditing nghĩa là gì trong Spring Data?

Trong Spring Data, **auditing** là khả năng tự điền các trường mô tả *ai* và *khi nào* đã tạo hoặc sửa entity, tại các điểm trong vòng đời lưu entity được framework hỗ trợ.

Bốn annotations phổ biến:

| Annotation | Ý nghĩa | Kiểu dữ liệu thường gặp |
|---|---|---|
| `@CreatedDate` | Mốc thời gian tạo entity | `Instant`, `Date`, `LocalDateTime`, kiểu thời gian được hỗ trợ |
| `@LastModifiedDate` | Mốc thời gian entity được sửa gần nhất | Kiểu thời gian được hỗ trợ |
| `@CreatedBy` | Actor tạo entity | Ví dụ `String`, `UserId` |
| `@LastModifiedBy` | Actor sửa entity gần nhất | Thường cùng kiểu với `AuditorAware<T>` |

### 2.1. Audit metadata không phải nhật ký mọi thay đổi

Document:

```json
{
  "_id": "order-100",
  "status": "SHIPPED",
  "createdBy": "user-7",
  "createdAt": {"$date": "2026-11-14T07:00:00Z"},
  "updatedBy": "warehouse-worker",
  "updatedAt": {"$date": "2026-11-14T08:35:00Z"}
}
```

cho bạn biết actor và thời gian *đầu/cuối*, nhưng không trả lời:

- Trước `SHIPPED` là `PAID` hay `CANCELLED`?
- Đã có bao nhiêu lần thay đổi?
- Ai đã thay giá trị `shippingAddress`?
- Có actor nào sửa rồi hoàn nguyên dữ liệu không?
- Metadata có bị một raw update thay đổi không?

Muốn lịch sử thay đổi đầy đủ, cần thiết kế **audit trail/version history/outbox/change streams** với chính sách quyền, retention và tính toàn vẹn riêng.

### 2.2. Auditing thuộc tầng mapping/application

Spring Data MongoDB auditing được tích hợp vào pipeline của Spring Data để xử lý Java entities. MongoDB Server không đọc annotation Java trong BSON document.

Hệ quả:

- Java code dùng Spring Data entity save có thể được audit.
- `mongosh` hoặc raw MongoDB Java Driver ghi document không tự chạy Spring callbacks.
- Một service khác dùng cùng database có thể bỏ qua Spring auditing.
- Query-based update của MongoTemplate không đi qua pipeline save entity theo cách tương tự.

**Không coi `@LastModifiedDate` là database trigger áp dụng toàn cluster.**

---

## 3. Dependency và cách tổ chức project

Với Spring Boot, thông thường dùng starter MongoDB:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
```

Nếu lấy actor từ Spring Security, thêm starter phù hợp:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

Nếu dùng reactive stack:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
```

**Không cần đưa cả synchronous và reactive starter vào cùng ví dụ nếu ứng dụng chỉ dùng một mô hình.** Phiên bản Spring Data MongoDB nên được quản lý bằng Spring Boot BOM/dependency management của project để tránh xung đột binary compatibility.

### 3.1. Cấu trúc code tham khảo

```text
src/main/java/com/example/orders/
  OrdersApplication.java
  config/
    MongoAuditConfiguration.java
  domain/
    OrderDocument.java
  repository/
    OrderRepository.java
  service/
    OrderService.java
  callbacks/
    OrderNormalizationCallback.java
    OrderBeforeSaveCallback.java
src/test/java/com/example/orders/
  OrderAuditingIntegrationTest.java
```

Cấu trúc là ví dụ. Các classes chỉ có hiệu lực khi Spring component scan/import bắt được bean tương ứng.

### 3.2. Application MongoDB URI

```yaml
spring:
  data:
    mongodb:
      uri: "mongodb://127.0.0.1:27017/orders_lab"
```

Ví dụ dùng localhost lab chưa có authentication/TLS. Production cần connection string, credentials, TLS, topology và secrets theo chuẩn bảo mật.

---

## 4. Entity cơ bản có auditing fields

Ví dụ một order document dùng trường mutable để minh họa dễ hiểu:

```java
package com.example.orders.domain;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.Instant;

@Document(collection = "orders")
public class OrderDocument {

    @Id
    private String id;

    private String customerId;
    private String status;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;

    @Version
    private Long version;

    public OrderDocument() {
    }

    public OrderDocument(String customerId, String status) {
        this.customerId = customerId;
        this.status = status;
    }

    public String getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
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

    public String getCreatedBy() {
        return createdBy;
    }

    public String getUpdatedBy() {
        return updatedBy;
    }

    public Long getVersion() {
        return version;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
```

Các fields audit không cần setter công khai nếu Spring Data mapping có khả năng truy cập/set property theo entity design. Với immutable classes, cần constructor/wither/record mapping được thiết kế phù hợp.

### 4.1. Phân biệt @Id và @Version

- `@Id` ánh xạ field ID Java tới `_id` trong MongoDB.
- `@Version` phục vụ optimistic locking và có thể tham gia xác định entity mới/cũ.
- `@CreatedDate` không phải ID.
- `@LastModifiedDate` không phải version counter.

### 4.2. Chọn String cho actor

`String createdBy` đơn giản và tránh phải serialize cả principal/security object vào document. Hãy lưu **ID ổn định**, không nên lưu JWT, session token hoặc đối tượng chứa quyền/credential.

### 4.3. Không cho client ghi audit fields

API request DTO nên chỉ nhận các trường nghiệp vụ cần thiết:

```json
{
  "customerId": "customer-100",
  "status": "CREATED"
}
```

Không cho phép client tùy ý gửi:

```json
{
  "createdBy": "admin",
  "createdAt": "2000-01-01T00:00:00Z"
}
```

rồi copy vào entity mà không kiểm soát. Audit metadata nên do server xử lý theo actor và time policy.

---

## 5. Bật @EnableMongoAuditing

Cấu hình imperative:

```java
package com.example.orders.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing
public class MongoAuditConfiguration {
}
```

Điều này đăng ký auditing infrastructure khi Spring context và Mongo mapping được cấu hình phù hợp.

### 5.1. Chỉ cần timestamps có cần AuditorAware không?

**Không bắt buộc.** Theo Spring Data documentation, nếu bạn chỉ sử dụng `@CreatedDate`/`@LastModifiedDate` mà không có `@CreatedBy`/`@LastModifiedBy`, không cần triển khai `AuditorAware`.

Nếu dùng các trường actor, cần cơ chế tìm actor hiện tại.

### 5.2. Auditing không mặc định xuất hiện chỉ vì dùng MongoRepository

Cần bật auditing theo configuration; việc thêm annotations lên entity **không bảo đảm** có bean auditing được đăng ký nếu thiếu `@EnableMongoAuditing`.

### 5.3. Đặt configuration ở package được scan

Nếu `OrdersApplication` nằm tại `com.example.orders` thì `com.example.orders.config` thường được scan theo component scanning mặc định của Spring Boot.

Nếu configuration ngoài phạm vi scan, phải import hoặc chỉnh scan hợp lý.

### 5.4. Không nhầm với JPA auditing

MongoDB dùng:

```java
@EnableMongoAuditing
```

không phải `@EnableJpaAuditing`. Tương tự, MongoDB lifecycle callbacks không dựa vào `@PrePersist`, `@PreUpdate` của JPA theo cách mặc định.

---

## 6. Cấu hình AuditorAware<String> từ Spring Security

`AuditorAware<T>` là Spring Data interface để tìm actor hiện tại.

Ví dụ:

```java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.mongodb.config.EnableMongoAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.Optional;

@Configuration
@EnableMongoAuditing(auditorAwareRef = "currentAuditor")
public class MongoAuditConfiguration {

    @Bean("currentAuditor")
    AuditorAware<String> currentAuditor() {
        return () -> {
            Authentication authentication =
                    SecurityContextHolder.getContext()
                            .getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.empty();
            }

            return Optional.ofNullable(authentication.getName())
                    .filter(name -> !name.isBlank());
        };
    }
}
```

### 6.1. Luồng dữ liệu

```text
HTTP security filter chain
        │
        ▼
SecurityContextHolder
        │
        └── Authentication
               principal/user ID
                    │
                    ▼
          AuditorAware.getCurrentAuditor()
                    │
                    ▼
              CreatedBy/LastModifiedBy
```

### 6.2. Không tin danh tính do client tự khai

Sai:

```java
String actor = request.getHeader("X-User-Name");
```

nếu header không được xác minh bởi trusted authentication layer. Client có thể giả danh admin bằng cách đặt header.

Đúng hơn: lấy danh tính đã được xác thực bởi Spring Security hoặc một trusted service identity đã được xác minh.

### 6.3. Tại sao trả Optional.empty() cho anonymous?

Nếu không có actor được xác thực, `Optional.empty()` biểu thị không xác định actor từ security context. Tùy nghiệp vụ, ứng dụng có thể:

- Từ chối writes yêu cầu actor.
- Ghi actor là dedicated service account thông qua một chính sách riêng.
- Cho phép system-created document có actor rỗng trong phạm vi hợp lệ.

Không tự gán mọi request anonymous thành `"system"` nếu như vậy có thể che đi lỗi xác thực.

### 6.4. Multiple AuditorAware beans

Nếu Spring context có nhiều `AuditorAware<?>` beans, cần chỉ rõ:

```java
@EnableMongoAuditing(auditorAwareRef = "currentAuditor")
```

Nếu không, framework có thể không biết chọn bean nào.

### 6.5. Kiểu T phải tương thích

Nếu entity khai báo:

```java
@CreatedBy
private String createdBy;
```

thì `AuditorAware<String>` phù hợp. Nếu bạn dùng `UserId` value object hoặc `User` entity, phải đảm bảo Mongo mapping/converters hỗ trợ và không vô ý nhúng dữ liệu security nhạy cảm.

---

## 7. Auditing trong scheduled jobs và background workers

Không phải mọi write đều đến từ HTTP request.

Ví dụ:

- Scheduled job đánh dấu orders hết hạn.
- Kafka consumer cập nhật trạng thái fulfillment.
- Batch migration.
- Retry worker.
- Admin maintenance script.

Khi chạy ngoài HTTP request thread, `SecurityContextHolder` thường không có authentication.

### 7.1. Không cố lấy user identity từ thread bất kỳ

Nếu `AuditorAware` dùng thread-local security context, async worker không mặc định kế thừa context của request gốc. Kể cả khi context được propagate, phải cân nhắc có hợp lý về mặt nghiệp vụ khi ghi actor ban đầu hay không.

### 7.2. Dùng service actor rõ ràng

Một batch job nên có identity riêng, ví dụ:

```text
service:expiry-worker
service:shipment-consumer
service:nightly-import
```

Đừng gán mọi worker thành `admin` hoặc ghi token OAuth vào `updatedBy`.

### 7.3. Thiết kế actor context

Một cách có kiểm soát:

- HTTP request: actor từ authenticated principal.
- Message consumer: actor từ trusted message metadata đã xác minh hoặc service identity.
- Scheduled job: actor từ service identity.
- Migration: actor `migration:<change-id>` được tổ chức chấp thuận.

Actor nên được truyền qua application service context rõ ràng khi không thể dựa vào SecurityContextHolder.

### 7.4. Một vấn đề với @Async

Spring Security context thường liên quan current thread. Nếu business service gọi:

```java
@Async
public void updateOrderAsync(...) {
    repository.save(order);
}
```

thì `AuditorAware` dựa vào thread-local có thể không lấy được principal của HTTP request.

Cần dùng context propagation được hỗ trợ hoặc explicit actor parameter; không tự chia sẻ SecurityContext object giữa các tác vụ một cách thiếu kiểm soát.

### 7.5. Không dùng ThreadLocal tùy tiện trong Reactor

Reactive execution có thể chuyển threads. Với WebFlux/Reactor, actor nên lấy từ **Reactor Context** thông qua `ReactiveAuditorAware`, không dựa vào ThreadLocal security context của imperative code.

---

## 8. Hành vi @CreatedDate và @LastModifiedDate khi insert/save

Giả sử entity mới chưa có ID:

```java
OrderDocument order =
        new OrderDocument("customer-100", "CREATED");

OrderDocument saved = repository.save(order);
```

Khi auditing đã bật và entity được xác định là **new**:

- `@CreatedDate` được gán mốc tạo.
- `@CreatedBy` được gán actor tạo nếu provider trả về actor.
- `@LastModifiedDate` có thể cũng được gán lúc tạo theo `modifyOnCreate`.
- `@LastModifiedBy` có thể cũng được gán lúc tạo theo `modifyOnCreate`.

### 8.1. Mặc định modifyOnCreate=true

`@EnableMongoAuditing` có thuộc tính:

```java
modifyOnCreate = true
```

Đây là mặc định trong API được tài liệu hóa. Với mặc định này, khi tạo mới entity có thể được đánh dấu là “modified” ngay tại lần tạo đầu tiên.

Ví dụ document:

```json
{
  "_id": "order-100",
  "status": "CREATED",
  "createdAt": {"$date": "2026-11-14T09:00:00Z"},
  "updatedAt": {"$date": "2026-11-14T09:00:00Z"},
  "createdBy": "user-17",
  "updatedBy": "user-17"
}
```

Một số team lại muốn `updatedAt` chỉ xuất hiện sau lần sửa đầu tiên. Khi đó có thể đặt:

```java
@EnableMongoAuditing(modifyOnCreate = false)
```

Phải chọn policy và kiểm tra behavior trên Spring Data version thực tế.

### 8.2. setDates=true

Thuộc tính:

```java
@EnableMongoAuditing(setDates = true)
```

bật tự điền ngày/giờ, và mặc định của nó là `true`.

Nếu cấu hình:

```java
@EnableMongoAuditing(setDates = false)
```

thì annotations về thời gian không được auditing tự gán theo cơ chế đó. Chỉ chọn nếu bạn có giải pháp timestamp riêng.

### 8.3. Lần sửa tiếp theo

```java
OrderDocument existing =
        repository.findById(orderId).orElseThrow();

existing.setStatus("PAID");
OrderDocument updated = repository.save(existing);
```

Với auditing hoạt động đúng và entity được xác định là existing:

- `createdAt` thường được giữ nguyên.
- `createdBy` thường được giữ nguyên.
- `updatedAt` được cập nhật.
- `updatedBy` được cập nhật.

### 8.4. Save một entity không đổi fields có sửa updatedAt không?

Việc gọi `save()` có thể vẫn kích hoạt auditing vì đó là một lượt persist được framework xử lý, **không phải phép so sánh business fields đã thay đổi hay chưa**.

Không kỳ vọng `updatedAt` chỉ đổi khi có diff thực sự.

### 8.5. @CreatedDate không phải thời điểm commit

Thời gian thường được lấy từ application-side time provider tại lúc callback chạy trước khi write. Nó không nhất thiết trùng chính xác với thời điểm MongoDB commit.

Trong transaction kéo dài, có thể có khoảng cách giữa time của callback và database commit. Nếu transaction abort, timestamp đã được gán trên Java object không đồng nghĩa dữ liệu đã persisted.

---

## 9. Chọn kiểu thời gian: Instant, Date, LocalDateTime

### 9.1. Khuyến nghị dùng Instant cho event time

`Instant` biểu diễn một thời điểm trên UTC timeline:

```java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant updatedAt;
```

Nó phù hợp trao đổi qua hệ thống phân tán, API và database.

### 9.2. BSON Date và precision

MongoDB BSON Date biểu diễn thời điểm bằng số milliseconds từ Unix epoch.

Trong Java, `Instant` có thể có nanosecond precision; khi chuyển sang BSON Date, độ chính xác thường được biểu diễn ở **mức milliseconds**.

Ví dụ:

```text
Instant Java:
  2026-11-14T09:00:00.123456789Z

BSON Date:
  2026-11-14T09:00:00.123Z
```

Khi test equality, không kỳ vọng MongoDB giữ đầy đủ nanos từ Java Instant theo mapping mặc định.

### 9.3. LocalDateTime không có timezone

`LocalDateTime` biểu diễn ngày/giờ địa phương **không gắn offset/timezone**. Khi mapping sang BSON Date có thể cần conversion/timezone policy rõ ràng.

Nếu service chạy ở nhiều timezone, dùng `LocalDateTime` không kiểm soát dễ dẫn đến sai lệch.

Đối với createdAt/updatedAt, `Instant` thường đơn giản và ổn định hơn.

### 9.4. Date và long

Spring Data auditing hỗ trợ các kiểu ngày/giờ JDK 8, `java.util.Date`, các kiểu số timestamp phù hợp và một số kiểu legacy theo API.

Nếu dùng `Long`, cần biết mapping/đơn vị thời gian của hệ thống. Không tự nghĩ mọi trường `long` đều mang seconds nếu provider đang cung cấp milliseconds.

### 9.5. Lưu timestamp dưới dạng String?

Có thể lưu ISO-8601 string nhưng mất nhiều ưu điểm của BSON Date cho sorting/range/index/TTL semantics.

Ví dụ:

```json
{"updatedAt":"14/11/2026 16:00"}
```

khó dùng trực tiếp như BSON Date và còn phụ thuộc locale/timezone. Nên giữ BSON Date và format ở API/UI.

---

## 10. Kiểm soát nguồn thời gian bằng DateTimeProvider

Mặc định Spring Data có time provider lấy thời gian hiện tại. Nhưng các hệ thống cần:

- Test deterministic.
- Đồng nhất UTC.
- Controlled clock cho simulation.
- Tách wall-clock policy khỏi domain logic.

Có thể cung cấp `DateTimeProvider`.

### 10.1. Cấu hình Clock + DateTimeProvider

```java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

@Configuration
@EnableMongoAuditing(dateTimeProviderRef = "mongoDateTimeProvider")
public class MongoTimeConfig {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean("mongoDateTimeProvider")
    public DateTimeProvider mongoDateTimeProvider(Clock clock) {
        return () -> Optional.of(Instant.now(clock));
    }
}
```

Trong một ứng dụng thực, nếu bạn cũng cần `AuditorAware`, có thể gom các thuộc tính trong **một** `@EnableMongoAuditing` configuration phù hợp, thay vì vô ý đăng ký auditing hai lần.

### 10.2. Inject Clock để test

Trong test có thể cấp:

```java
Clock.fixed(
        Instant.parse("2026-11-14T09:30:00Z"),
        java.time.ZoneOffset.UTC);
```

Khi đó auditing có thể gán timestamp xác định; sau update đổi fake clock để test `updatedAt` tăng và `createdAt` giữ nguyên.

### 10.3. Đồng bộ đồng hồ hosts

Đây là application-generated timestamp nên thời gian có thể bị skew giữa các instances. Nếu hai services chạy đồng hồ lệch 3 phút, `updatedAt` có thể đi lùi.

Production cần đồng bộ NTP/time, chính sách UTC và phân biệt:

- Application write timestamp.
- Server-side `$currentDate` timestamp.
- Actual transaction commit time.
- Business effective date.

Không dùng `updatedAt` để đảm bảo total order trên hệ phân tán nếu clock synchronization/causal guarantees không phù hợp.

### 10.4. Không dùng DateTimeProvider cho business date tùy ý

Một subscription renewal date hoặc invoice due date không phải audit timestamp. Đừng gán `@CreatedDate` cho mọi field ngày tháng.

---

## 11. AuditorAware và DateTimeProvider có nhiệm vụ khác nhau

| Thành phần | Câu hỏi | Trường liên quan |
|---|---|---|
| `AuditorAware<T>` | Ai đang tác động? | `CreatedBy`, `LastModifiedBy` |
| `DateTimeProvider` | Bây giờ là khi nào? | `CreatedDate`, `LastModifiedDate` |
| `@EnableMongoAuditing` | Có bật infrastructure không? | Tất cả |
| `IsNewStrategy / @Version` | Entity được coi mới hay cũ? | Nhánh create/modify |
| `BeforeConvertCallback` | Có cần thay entity trước mapping không? | Normalization, auditing |
| `BeforeSaveCallback` | BSON document đã convert cần bổ sung gì? | Document-level metadata |
| `AfterConvertCallback` | Sau khi đọc entity cần xử lý gì? | Enrichment/transient view |

Một bug audit timestamp null có thể do missing enablement/date provider. Một bug actor null có thể do missing `AuditorAware` hoặc thiếu authentication context. Không nên sửa nhầm bằng cách gán thời gian trong controller.

---

## 12. isNew(): Spring Data biết đây là insert hay update từ đâu?

Spring Data cần xác định entity là **new** hay **existing** cho nhiều lựa chọn persistence/auditing.

### 12.1. Quy tắc khái quát

Trong các trường hợp thường gặp:

- Nếu có `@Version` phù hợp, value chưa được khởi tạo có thể báo entity mới.
- Nếu không có version, ID null thường báo entity mới.
- ID non-null thường được coi là existing nếu không có tín hiệu khác.
- Entity triển khai `Persistable<ID>` có thể chủ động quyết định `isNew()`.
- Behavior chi tiết phụ thuộc mapping/version type và operation.

### 12.2. ID do ứng dụng cấp sẵn

Ví dụ:

```java
OrderDocument order = new OrderDocument(...);
// Giả sử app gán id trước khi gọi repository.save.
```

Nếu entity **không có `@Version`** mà ID đã có giá trị, Spring Data có thể coi entity là existing dù document chưa từng được insert. Điều đó ảnh hưởng cách auditing phân biệt created vs modified và cách repository chọn persistence path.

Đừng giải quyết bằng cách đặt `createdAt` trong mọi `save()` vô điều kiện.

### 12.3. @Version có thể giúp new detection

Ví dụ:

```java
@Version
private Long version;
```

Khi version là `null`, infrastructure thường xem đó là dấu hiệu entity mới; sau khi lưu, version được quản lý theo optimistic locking semantics.

Với primitive version types, behavior giá trị ban đầu khác wrapper types. Đối chiếu documentation đúng release.

### 12.4. Persistable<ID>

Một entity có ID business key từ đầu có thể chủ động triển khai:

```java
import org.springframework.data.domain.Persistable;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;

public class ExternalOrder implements Persistable<String> {
    @Id
    private String id;

    @Transient
    private boolean isNew = true;

    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return isNew;
    }

    // Cần lifecycle xử lý flag sau load/save
    // theo ví dụ trong docs của phiên bản Spring Data.
}
```

**Đoạn trên chỉ minh họa strategy, chưa phải entity hoàn chỉnh để sử dụng production.** Phải thiết kế cách chuyển flag khi entity đã persist/load, tránh đánh dấu new mãi mãi và gây duplicate key errors.

### 12.5. Không dùng repository.save như “upsert tự thông minh”

`save()` phải tuân theo mapping/new detection và optimistic locking. Không bảo đảm luôn tự biết document chưa có nếu ID đã được cấp. Nếu cần upsert theo key, sử dụng operation đúng semantics và cập nhật audit fields rõ ràng.

---

## 13. @Version và optimistic locking

Một vấn đề tách biệt nhưng liên quan: hai service cùng đọc order rồi ghi.

```text
Order version = 4
Service A đọc version 4
Service B đọc version 4

A sửa status → save
  version 4 -> 5

B sửa shippingAddress → save
  vẫn nghĩ version 4
  → optimistic locking failure
```

Với `@Version`, Spring Data MongoDB có cơ chế optimistic locking trên entity save phù hợp.

### 13.1. Ví dụ entity

```java
@Document("orders")
class OrderDocument {
    @Id String id;
    @Version Long version;
    @CreatedDate Instant createdAt;
    @LastModifiedDate Instant updatedAt;
    String status;
}
```

### 13.2. Ví dụ save

```java
OrderDocument order = repository.findById(id).orElseThrow();
order.setStatus("PAID");
repository.save(order);
```

Nếu đã có concurrent update, save có thể ném `OptimisticLockingFailureException` theo điều kiện mapping và write concern.

### 13.3. Write concern

Spring Data MongoDB documentation nhấn mạnh cần write concern phù hợp, đặc biệt `ACKNOWLEDGED` trở lên, để thấy optimistic locking errors. Không dùng unacknowledged writes rồi kỳ vọng client luôn nhận được conflict.

### 13.4. Auditing không thay optimistic locking

`updatedAt` không đủ để chống lost updates một cách mặc định. Hai clients có thể cập nhật cùng document vào thời điểm rất gần nhau và timestamps không bảo đảm được compare-and-swap.

Dùng `@Version` hoặc conditional update theo expected version.

### 13.5. Lỗi sau optimistic conflict

Không tự động lưu đè document cũ. Cần:

1. Đọc lại trạng thái mới nhất.
2. Xác định thay đổi có thể merge không.
3. Áp dụng business conflict policy.
4. Retry với giới hạn và idempotency nếu phù hợp.

---

## 14. Lifecycle callback là gì?

Spring Data cung cấp `EntityCallback<T>` interfaces được gọi tại các điểm cụ thể trong mapping/persistence pipeline.

Chúng là cơ chế type-safe hơn cho việc sửa entities tại những giai đoạn nhất định, so với các application event listeners cũ.

### 14.1. Các callback quan trọng

| Callback | Thời điểm | Use case phù hợp |
|---|---|---|
| `BeforeConvertCallback<T>` | Trước khi entity được chuyển thành BSON `Document` | Normalize field, chuẩn bị giá trị persist, auditing |
| `BeforeSaveCallback<T>` | Sau convert, trước khi MongoDB ghi | Chỉnh BSON Document, low-level metadata |
| `AfterSaveCallback<T>` | Sau thao tác save theo framework | Quan sát/điều chỉnh returned entity có kiểm soát |
| `AfterConvertCallback<T>` | Sau khi BSON được chuyển thành Java entity | Tạo derived transient view, normalize read model |
| `ReactiveBeforeConvertCallback<T>` | Đường reactive tương ứng | Reactor-safe async transformation |
| `ReactiveBeforeSaveCallback<T>` | Đường reactive tương ứng | Sửa BSON trước write trong reactive API |
| `ReactiveAfterConvertCallback<T>` | Đường reactive tương ứng | Enrich entity đọc |

Spring Data MongoDB auditing sử dụng `AuditingEntityCallback` trong giai đoạn **BeforeConvert**.

### 14.2. Vì sao BeforeConvert là vị trí phù hợp?

Tại thời điểm này, mapper chưa chuyển Java entity sang BSON. Thay đổi persistent properties trên Java object sẽ được phản ánh vào BSON được tạo sau đó.

### 14.3. Vì sao BeforeSave phải cẩn thận?

`BeforeSaveCallback` chạy **sau khi BSON Document đã được tạo**. Spring Data API mô tả rằng thay đổi persistent properties chỉ trên Java entity lúc này **không còn được phản ánh vào Document đang lưu**.

Nếu cần thay field thực sự được ghi, hãy:

- Thay entity ở `BeforeConvertCallback`; hoặc
- Thay BSON `Document` argument ở `BeforeSaveCallback` khi có lý do rõ.

### 14.4. Vì sao AfterSave không bảo đảm external event?

Callback có thể chạy sau một thao tác save, nhưng nó không đồng nghĩa toàn bộ business transaction đã commit thành công. Nếu nằm trong multi-document transaction và callback gọi external API, DB transaction có thể rollback sau đó.

Không gửi payment/email/Kafka event quan trọng một cách mù quáng trong `AfterSaveCallback`.

---

## 15. BeforeConvertCallback: chuẩn hóa entity trước khi lưu

Ví dụ: tên sản phẩm không nên có spaces thừa, mã trạng thái phải viết hoa.

```java
package com.example.orders.callbacks;

import com.example.orders.domain.OrderDocument;
import org.springframework.core.annotation.Order;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
@Order(50)
public class OrderNormalizationCallback
        implements BeforeConvertCallback<OrderDocument> {

    @Override
    public OrderDocument onBeforeConvert(
            OrderDocument entity,
            String collection) {

        if (!"orders".equals(collection)) {
            return entity;
        }

        if (entity.getStatus() != null) {
            entity.setStatus(
                    entity.getStatus().trim().toUpperCase(
                            java.util.Locale.ROOT));
        }

        return entity;
    }
}
```

### 15.1. Vì sao dùng @Order(50)?

Theo tài liệu Spring Data MongoDB, `AuditingEntityCallback` có order **100** ở các releases hiện hành. Callback custom order 50 có thể chạy trước auditing khi cùng giai đoạn BeforeConvert.

Thứ tự được dùng để biểu đạt dependency:

```text
BeforeConvert callbacks:
  order 50 → normalize
  order 100 → auditing
  order 200 → optional post-audit adjustment
```

Không mặc định mọi callback ứng dụng chạy theo tên class hoặc thứ tự đăng ký bean.

### 15.2. Không mutate ngoài phạm vi cần thiết

Callbacks là cross-cutting infrastructure. Tránh:

- Gọi network API.
- Truy vấn database khác trong callback không có giới hạn.
- Sinh random business values mỗi lượt retry.
- Thay `createdAt` một cách tùy tiện.
- Gọi repository.save chính entity bên trong callback rồi tạo recursion.

### 15.3. Mutable và immutable entities

Ví dụ trên mutate entity vì `OrderDocument` mutable. Với immutable entity/Java record, callback phải **trả về instance mới** được copy với persistent changes; không cố set final field bằng reflection tùy tiện.

### 15.4. Vòng lặp lặp lại

Callback có thể chạy nhiều lần nếu entity được save nhiều lần hoặc business transaction retry. Logic normalize nên **idempotent**, ví dụ trim/uppercase, để tránh thay đổi ngoài dự kiến.

---

## 16. BeforeSaveCallback: BSON Document đã được tạo

Ví dụ thêm một field schema marker trực tiếp vào BSON trước khi lưu.

```java
package com.example.orders.callbacks;

import com.example.orders.domain.OrderDocument;
import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderBeforeSaveCallback
        implements BeforeSaveCallback<OrderDocument> {

    @Override
    public OrderDocument onBeforeSave(
            OrderDocument entity,
            Document document,
            String collection) {

        if ("orders".equals(collection)) {
            document.put("schemaRevision", 2);
        }

        return entity;
    }
}
```

### 16.1. Điều gì được lưu?

BSON document chứa `schemaRevision: 2`, dù Java class ví dụ chưa có mapped property `schemaRevision`.

### 16.2. Cảnh báo về consistency giữa entity và BSON

Nếu chỉ sửa Document mà Java entity không có field tương ứng, entity trả về sau save có thể **không phản ánh đầy đủ** dữ liệu thực đã ghi.

Nếu field thuộc business/domain model, thường nên khai báo mapped property và set trong `BeforeConvertCallback`.

### 16.3. Anti-pattern

Sai:

```java
@Override
public OrderDocument onBeforeSave(
        OrderDocument entity,
        Document document,
        String collection) {

    entity.setStatus("PAID");
    return entity;
}
```

Nếu BSON đã được tạo với `status: CREATED`, việc chỉ mutate entity ở BeforeSave không bảo đảm Document được cập nhật.

Nếu muốn thay status persistent, làm ở `BeforeConvertCallback` hoặc sửa chính `document.put("status","PAID")` với các ràng buộc phù hợp.

### 16.4. Không tạo security-critical authority trong callback tùy tiện

Đừng dùng BeforeSave để bí mật override ownership/tenant ID từ một nguồn không tin cậy. Quyền truy cập phải được kiểm soát ở auth/service layer và MongoDB authorization phù hợp.

---

## 17. AfterSaveCallback: sau khi write operation hoàn thành

Một ví dụ an toàn: ghi metric ngắn hoặc điều chỉnh thuộc tính transient ở entity trả về.

```java
package com.example.orders.callbacks;

import com.example.orders.domain.OrderDocument;
import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderAfterSaveCallback
        implements AfterSaveCallback<OrderDocument> {

    @Override
    public OrderDocument onAfterSave(
            OrderDocument entity,
            Document document,
            String collection) {

        // Có thể thu thập metric đã sanitize ở đây.
        // Không gửi email/Kafka/payment trực tiếp.
        return entity;
    }
}
```

### 17.1. Đừng hiểu callback này là transaction committed

Ví dụ service:

```text
start MongoDB transaction
  save order → AfterSaveCallback chạy
  save inventory → gặp lỗi
abort transaction
```

Nếu callback đã gửi Kafka event lúc save order, Kafka có thể nhận event dù transaction MongoDB cuối cùng abort.

### 17.2. Dùng outbox thay external side effects

Nếu cần phát sự kiện sau khi order được commit:

1. Ghi order.
2. Ghi outbox document.
3. Commit MongoDB transaction.
4. Worker đọc outbox rồi publish.
5. Consumer có idempotency.

Đây là giải pháp cho dual-write consistency; AfterSaveCallback chỉ là extension point, không phải transaction completion hook toàn hệ thống.

### 17.3. Logging trong AfterSave

Không log nguyên Document nếu chứa PII hoặc dữ liệu thanh toán. Dùng metadata ngắn:

- Entity type.
- Namespace.
- Operation class.
- Trace ID đã xác thực và xử lý an toàn.
- Metric counter.

---

## 18. AfterConvertCallback: tác động khi đọc

Ví dụ entity có trường hiển thị chỉ tính trong JVM:

```java
import org.springframework.data.annotation.Transient;

@Transient
private String displayStatus;
```

Callback:

```java
import com.example.orders.domain.OrderDocument;
import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderAfterConvertCallback
        implements AfterConvertCallback<OrderDocument> {

    @Override
    public OrderDocument onAfterConvert(
            OrderDocument entity,
            Document document,
            String collection) {

        // Với entity mutable, có thể điền dữ liệu transient
        // thông qua setter tương ứng.
        return entity;
    }
}
```

### 18.1. Dùng cho trường hợp nào?

- Derived display field.
- In-memory normalization của dữ liệu cũ.
- Enrichment nhỏ không cần I/O bên ngoài.
- Compatibility khi đọc schema cũ.

### 18.2. Không sửa audit metadata sau read một cách âm thầm

Nếu callback sửa `createdAt` trong Java object mà database vẫn giữ giá trị cũ, dễ tạo nhầm lẫn khi API trả response. Hãy phân biệt derived view với persistent source of truth.

### 18.3. Không dùng AfterConvert để load hàng loạt phụ thuộc

Nếu mỗi entity sau khi đọc lại query một collection khác, một `findAll()` 1.000 entities có thể dẫn tới N+1 queries và latency tăng mạnh.

Dùng DTO projection, aggregation hoặc batch loading phù hợp.

---

## 19. EntityCallbacks khác ApplicationEvents như thế nào?

Spring Data MongoDB còn có lifecycle **mapping events** dựa trên Spring `ApplicationEvent`.

Ví dụ:

- `BeforeConvertEvent`.
- `BeforeSaveEvent`.
- `AfterSaveEvent`.
- `AfterLoadEvent`.
- `AfterConvertEvent`.

### 19.1. Ví dụ legacy event listener

```java
import org.springframework.data.mongodb.core.mapping.event.AbstractMongoEventListener;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertEvent;
import org.springframework.stereotype.Component;

@Component
public class LegacyOrderListener
        extends AbstractMongoEventListener<OrderDocument> {

    @Override
    public void onBeforeConvert(
            BeforeConvertEvent<OrderDocument> event) {
        // Legacy event hook. Ưu tiên EntityCallback
        // nếu mục tiêu là sửa entity có thứ tự rõ ràng.
    }
}
```

### 19.2. Vì sao ưu tiên EntityCallback cho entity modifications?

Theo Spring Data docs:

- `EntityCallback` được gọi ở checkpoints đã xác định.
- Có thể trả về entity mới/thay đổi.
- Hỗ trợ imperative và reactive APIs riêng.
- Có thể sắp thứ tự callbacks.

ApplicationEvents phụ thuộc `ApplicationEventMulticaster`. Nếu sử dụng asynchronous task executor, thứ tự xử lý/event completion **không được bảo đảm** theo cách tương tự.

### 19.3. Thứ tự event và callback

Tài liệu Spring Data MongoDB nêu các store-specific ApplicationEvents vẫn có thể được phát **trước** EntityCallback tương ứng.

Không nhầm:

```text
BeforeConvertEvent
      ≠
BeforeConvertCallback
```

Nếu bạn dùng cả listener cũ và callback mới, phải tính rõ thứ tự và tránh hai nơi cùng chỉnh audit fields.

### 19.4. Event không phải Kafka event

Spring ApplicationEvent chỉ là event trong application context. Nó không tự trở thành một message broker event có durability, retry và delivery guarantees.

### 19.5. Root entity vs nested types

MongoDB lifecycle events thường áp dụng cho **root-level mapped types**, không tự phát sự kiện cho mọi embedded object trong một document. DBRef/relationships có những quy tắc riêng.

Đừng kỳ vọng embedded `Address` tự kích hoạt event lifecycle như một root `OrderDocument` mỗi khi order save.

---

## 20. Thứ tự auditing callback và callbacks tự viết

Spring Data MongoDB dùng `AuditingEntityCallback` để điền auditing fields ở giai đoạn BeforeConvert. Tài liệu hiện hành nêu order mặc định của auditing callback là **100**.

### 20.1. Vì sao thứ tự quan trọng?

Ví dụ cần:

1. Chuẩn hóa `status`.
2. Ghi auditing metadata.
3. Tạo derived field dựa trên actor/time.

Một callback order thấp hơn 100 sẽ chạy trước auditing; callback order lớn hơn 100 trong cùng stage có thể chạy sau.

### 20.2. @Order và Ordered

Có thể dùng:

```java
@Component
@Order(50)
class NormalizeBeforeConvert
        implements BeforeConvertCallback<OrderDocument> {
    // ...
}
```

Hoặc implement `Ordered` và trả về numeric order.

### 20.3. LOWEST_PRECEDENCE

Callbacks không đặt order có thể được xếp ở mức `Ordered.LOWEST_PRECEDENCE`. Không nên dựa vào tên bean hoặc classpath scan order để quyết định behavior nghiệp vụ.

### 20.4. Các stage khác nhau không thể đảo bằng @Order

Dù có `@Order(-100)` cho BeforeSave, nó vẫn là **BeforeSave stage sau conversion**, không thể biến thành BeforeConvert.

Ordering chỉ sắp xếp **các callbacks ở checkpoint tương ứng**, không thay thứ tự tổng thể của mapping pipeline.

### 20.5. Tránh callback cùng sửa một field

Nếu auditing callback đặt `updatedAt` nhưng callback custom đặt lại giá trị khác, khó biết ai là source of truth. Tốt hơn một nơi chịu trách nhiệm metadata, có test chứng minh kết quả.

---

## 21. Không phải mọi write qua Spring Data đều chạy auditing callback

Đây là phần dễ gây bug nhất.

### 21.1. Entity save/insert

Các đường như:

```java
repository.save(entity);
mongoTemplate.save(entity);
mongoTemplate.insert(entity);
```

thường đi qua mapping pipeline với entity callbacks, trong đó có auditing khi được bật.

### 21.2. Query-based update

Các lệnh dạng:

```java
mongoTemplate.updateFirst(query, update, OrderDocument.class);
mongoTemplate.updateMulti(query, update, OrderDocument.class);
mongoTemplate.findAndModify(query, update, OrderDocument.class);
```

là **update MongoDB theo query**, không phải lưu lại một Java entity qua pipeline `BeforeConvert/BeforeSave` như `save()`. Vì vậy không kỳ vọng `@LastModifiedDate` tự điền như entity save.

### 21.3. Repository @Update

Ví dụ declarative update:

```java
@Query("{ '_id': ?0 }")
@Update("{ '$set': { 'status': ?1 } }")
long setStatusById(String id, String status);
```

nếu version/interface hỗ trợ, đây là query update, không phải `save(entity)`. Phải thiết kế updatedAt/updatedBy rõ ràng trong update expression hoặc service layer.

### 21.4. BulkOperations

```java
mongoTemplate.bulkOps(
        BulkOperations.BulkMode.ORDERED,
        OrderDocument.class);
```

Bulk operations thường gửi batches theo update/insert models và **không đi qua entity lifecycle callbacks theo cùng semantics như save**; nhiều version cũng có những giới hạn về `@Version` trong bulk operations.

Không kỳ vọng mọi item được audit tự động. Hãy đặt audit fields trong chính bulk update/insert payload hoặc dùng một abstraction đã được kiểm thử.

### 21.5. Raw Java Sync Driver

```java
mongoClient.getDatabase("orders_lab")
        .getCollection("orders")
        .updateOne(
                Filters.eq("_id", id),
                Updates.set("status", "PAID"));
```

Spring `AuditingEntityCallback` hoàn toàn không tham gia luồng này.

### 21.6. MongoDB shell và migration scripts

Lệnh `mongosh`:

```javascript
db.orders.updateOne(
  { _id: "order-100" },
  { $set: { status: "PAID" } }
);
```

không tự gọi Java annotations/callbacks. Migration/runbook phải cập nhật audit metadata theo chính sách riêng.

---

## 22. Cập nhật updatedAt/updatedBy trong MongoTemplate.updateFirst

Ví dụ imperative:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import java.time.Clock;
import java.time.Instant;

public class OrderUpdateService {

    private final MongoTemplate mongoTemplate;
    private final Clock clock;

    public OrderUpdateService(
            MongoTemplate mongoTemplate, Clock clock) {
        this.mongoTemplate = mongoTemplate;
        this.clock = clock;
    }

    public void markPaid(String id, String actorId) {
        if (actorId == null || actorId.isBlank()) {
            throw new IllegalArgumentException("Missing actor");
        }

        Query query = Query.query(
                Criteria.where("_id").is(id));

        Update update = new Update()
                .set("status", "PAID")
                .set("updatedAt", Instant.now(clock))
                .set("updatedBy", actorId);

        mongoTemplate.updateFirst(
                query,
                update,
                OrderDocument.class);
    }
}
```

### 22.1. Vì sao tự set auditing fields?

Vì đây là query-based update. Entity auditing annotations không có cơ hội chạy trên một `OrderDocument` được convert/saved theo pipeline entity.

### 22.2. Server clock với $currentDate

Có thể dùng:

```java
Update update = new Update()
        .set("status", "PAID")
        .set("updatedBy", actorId)
        .currentDate("updatedAt");
```

MongoDB sẽ dùng timestamp server-side cho `updatedAt` theo semantics của `$currentDate`.

### 22.3. Client clock hay server clock?

Chọn **một policy nhất quán**:

- Entity save với `@LastModifiedDate` thường lấy application clock.
- `$currentDate` lấy server clock.
- Kết hợp cả hai trong cùng collection có thể tạo chênh lệch nhỏ hoặc clock skew đáng chú ý.
- Với nhiều services, phải document rõ timestamp source.

### 22.4. Validate actor và changes

Không nhận `actorId` từ raw header không xác thực. Tránh update khi status không thực sự cần đổi nếu business muốn updatedAt chỉ đổi khi có transition.

---

## 23. Query upsert: trường tạo và trường sửa

Upsert cần xử lý đặc biệt: một query có thể insert document mới hoặc update document cũ.

MongoDB update modifiers:

- `$setOnInsert`: chỉ áp dụng khi thao tác upsert thực sự insert.
- `$set`: áp dụng khi insert hoặc update theo semantics.
- `$currentDate`: tạo/cập nhật timestamp ở server.

Ví dụ:

```java
Instant now = Instant.now(clock);

Query query = Query.query(
        Criteria.where("externalOrderId")
                .is(externalOrderId));

Update update = new Update()
        .setOnInsert("createdAt", now)
        .setOnInsert("createdBy", actor)
        .set("updatedAt", now)
        .set("updatedBy", actor)
        .set("status", "RECEIVED");

mongoTemplate.upsert(
        query,
        update,
        OrderDocument.class);
```

### 23.1. Tại sao setOnInsert?

Nếu document đã tồn tại, `createdAt`/`createdBy` phải được giữ nguyên.

### 23.2. Tránh operator conflict

Không đặt cùng field dưới hai operators xung đột trong một update, ví dụ vừa `$setOnInsert.updatedAt` vừa `$currentDate.updatedAt` nếu MongoDB không chấp nhận conflict.

### 23.3. Unique index

Upsert theo external key khi concurrent cần unique index để giảm nguy cơ tạo trùng documents:

```javascript
db.orders.createIndex(
  { externalOrderId: 1 },
  { unique: true }
);
```

### 23.4. Auditing và upsert

Query upsert không dùng entity auditing theo cùng luồng entity save. Metadata cần có trong update expression như ví dụ.

### 23.5. Version

Nếu dùng `@Version` với query updates, Spring Data có thể áp dụng những behavior tự động theo version/tùy operation; nhưng **đừng suy ra optimistic locking của `save()` được bảo đảm đầy đủ nếu query update không có expected version predicate**.

Cần thể hiện điều kiện `version` và increment semantics rõ ràng khi correctness phụ thuộc conflict detection.

---

## 24. Atomic update với expected version và audit metadata

Giả sử client đọc order version 4, chỉ muốn update nếu không có ai thay đổi sau đó.

```java
Query query = new Query()
        .addCriteria(Criteria.where("_id").is(orderId))
        .addCriteria(Criteria.where("version").is(4L));

Update update = new Update()
        .set("status", "PAID")
        .set("updatedAt", Instant.now(clock))
        .set("updatedBy", actor)
        .inc("version", 1L);

UpdateResult result = mongoTemplate.updateFirst(
        query,
        update,
        OrderDocument.class);
```

### 24.1. Kiểm tra modifiedCount/matchedCount

Nếu không match document với expected version, có thể do:

- Order không tồn tại.
- Order tồn tại nhưng version đã thay đổi.
- Các điều kiện khác của query không đúng.

Không trả success mà không xem update result.

### 24.2. Tránh double increment

Spring Data MongoDB có cơ chế version handling trong một số update operations. Nếu bạn tự `inc("version",1)`, cần kiểm tra mapping/version logic của **đúng Spring Data version** để không increment hai lần.

Khi có doubt, dùng repository save với `@Version` hoặc viết explicit update được integration-test cùng expected version.

### 24.3. Trường updatedAt không thay thế version

Hai writes cùng millisecond có thể có cùng timestamp. Optimistic version counter có semantics compare-and-swap phù hợp hơn để nhận diện lost updates.

---

## 25. Embedded audit metadata

Spring Data Commons cho phép đặt auditing annotations trong một object nhúng trong nhiều store mappings phù hợp.

Ví dụ:

```java
public class AuditMetadata {
    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;

    // Constructors/getters/setters hoặc immutable mapping.
}

@Document("orders")
public class OrderDocument {
    @Id
    private String id;

    private String status;

    private AuditMetadata audit = new AuditMetadata();
}
```

### 25.1. Khi nào phù hợp?

Nếu nhiều entities có cùng metadata và muốn thống nhất structure/schema.

### 25.2. Không nhầm embedded với separate lifecycle callback

Annotations có thể được auditing infrastructure xử lý trên embedded object theo store support. Nhưng **không nên kỳ vọng MongoDB phát lifecycle event riêng cho mọi embedded object** như một root entity.

### 25.3. Null embedded object

Nếu `audit=null` và không có cách instantiate phù hợp, một số mapping/auditing flows có thể không điền giá trị như kỳ vọng. Cần integration test để xác minh nested metadata được tạo và persist.

### 25.4. Đánh đổi schema

Dạng nested:

```json
{
  "audit": {
    "createdAt": {"$date":"..."},
    "updatedAt": {"$date":"..."}
  }
}
```

khác với flat fields ở root. Query/index/reporting phải dùng path tương ứng, ví dụ `audit.updatedAt`.

---

## 26. Auditing với immutable entity, record và constructors

Ngày càng nhiều ứng dụng Java dùng immutable domain model.

### 26.1. Vấn đề

Một Java record:

```java
public record OrderRecord(
        String id,
        String status,
        Instant createdAt,
        Instant updatedAt) {
}
```

không có setter; auditing cần cách tạo ra instance được cập nhật metadata.

### 26.2. Spring Data mapping với constructor/wither

Các phiên bản Spring Data hỗ trợ immutable mapping theo các convention cụ thể:

- Persistence constructor.
- Constructor parameter names.
- Wither methods.
- Kotlin data classes/Java records ở phạm vi tương thích.
- Mapping metadata và converters.

Không ép Spring Data sửa final fields bằng reflection trong mọi Java runtime/version.

### 26.3. Callback phải trả về entity đúng

Với `BeforeConvertCallback<T>`:

```java
@Override
public OrderRecord onBeforeConvert(
        OrderRecord entity,
        String collection) {

    return new OrderRecord(
            entity.id(),
            entity.status().trim(),
            entity.createdAt(),
            entity.updatedAt());
}
```

Đây là minh họa immutable normalization, chưa ghép đầy đủ auditing behavior cho record. Khi dùng `@CreatedDate`/`@LastModifiedDate` với immutable types, phải bảo đảm Spring Data có cách cập nhật property tương ứng.

### 26.4. Test là điều bắt buộc về mặt chức năng

Đừng chỉ kiểm tra unit test gọi callback trực tiếp. Hãy kiểm tra:

1. Insert record immutable.
2. Timestamps/actors thực được ghi trong BSON.
3. Read entity khôi phục đúng.
4. Update entity không làm mất `createdAt`.
5. Version increment/conflict.
6. Callback trả về instance mới được framework sử dụng.

---

## 27. Reactive auditing: không dùng nhầm AuditorAware

Với reactive Spring Data MongoDB, sử dụng:

- `@EnableReactiveMongoAuditing`.
- `ReactiveAuditorAware<T>`.
- Các `Reactive...Callback` tương ứng.

### 27.1. Cấu hình

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.data.mongodb.config.EnableReactiveMongoAuditing;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

@Configuration
@EnableReactiveMongoAuditing(
        auditorAwareRef = "reactiveCurrentAuditor")
public class ReactiveMongoAuditConfiguration {

    @Bean("reactiveCurrentAuditor")
    ReactiveAuditorAware<String> reactiveCurrentAuditor() {
        return () -> ReactiveSecurityContextHolder
                .getContext()
                .map(context -> context.getAuthentication())
                .filter(Authentication::isAuthenticated)
                .map(Authentication::getName);
    }
}
```

### 27.2. Reactor Context

Reactive SecurityContext không nên lấy qua thread-local `SecurityContextHolder` trong mọi operators. Reactor có thể chuyển execution threads, còn authentication thường được propagate qua Reactor Context.

### 27.3. Reactive callbacks

Ví dụ:

```java
import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeConvertCallback;
import reactor.core.publisher.Mono;

@Component
public class ReactiveOrderCallback
        implements ReactiveBeforeConvertCallback<OrderDocument> {

    @Override
    public Mono<OrderDocument> onBeforeConvert(
            OrderDocument entity,
            String collection) {

        entity.setStatus(entity.getStatus().trim());
        return Mono.just(entity);
    }
}
```

### 27.4. Imperative và reactive infrastructure tách nhau

Spring Data docs nêu synchronous API xử lý synchronous entity callbacks, reactive API xử lý reactive callbacks. Đừng kỳ vọng `BeforeConvertCallback<T>` tự chạy trong mọi `ReactiveMongoTemplate` operation.

Tương tự, đăng ký `@EnableMongoAuditing` không thay thế việc bật auditing cho reactive stack khi cần.

### 27.5. Không block trong reactive callback

Tránh `.block()` hoặc blocking JDBC/HTTP call trong reactive callback. Nếu cần lấy dữ liệu bất đồng bộ, dùng reactive composition phù hợp, đồng thời cân nhắc rủi ro N+1/latency.

---

## 28. Auditing trong MongoDB transactions

Spring Data MongoDB có thể tham gia transactions khi cấu hình transaction manager và topology phù hợp.

### 28.1. Cần transaction manager

Với imperative Spring Data MongoDB:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
```

Sau khi cấu hình Spring transaction infrastructure phù hợp, service có thể dùng `@Transactional`.

### 28.2. Service minh họa

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public CheckoutService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void createOrder(OrderDocument order,
                            OutboxDocument event) {
        orders.insert(order);
        outbox.insert(event);
    }
}
```

Ví dụ khái niệm, yêu cầu các beans/repositories và server replica set/sharded cluster hỗ trợ transactions.

### 28.3. Timestamp phát sinh khi nào?

Auditing callback có thể đặt `createdAt`/`updatedAt` **trước database commit**. Nếu transaction rollback, object Java vẫn có thể giữ timestamp trên heap trong khi MongoDB không lưu document.

Không đồng nhất “entity có createdAt khác null” với “transaction đã commit”.

### 28.4. AfterSave chưa chắc là after commit

Nếu callback gửi email ngay khi `orders.insert` thành công trong transaction nhưng transaction abort ở `outbox.insert`, email vẫn đã gửi.

Với yêu cầu external events: dùng outbox hoặc after-commit coordination có recovery design; không dùng AfterSave như durable publication boundary.

### 28.5. Transaction retry

Khi transaction callback được retry, entity callbacks có thể chạy lại trong attempt mới. Vì vậy:

- Normalization nên idempotent.
- Không sinh external side effects.
- Không ngẫu nhiên thay business identity mỗi attempt.
- Không gửi event thẳng từ callbacks.
- DateTimeProvider có thể cho mốc khác giữa attempts.

### 28.6. @Transactional không biến raw driver calls thành Spring entity callbacks

Nếu một service dùng Spring Data repository và raw MongoDB Java Driver cùng trong transaction mà không đảm bảo session binding, bạn có thể vừa mất atomicity vừa bỏ qua audit metadata. Phải hiểu transaction propagation và driver/session integration.

---

## 29. Auditing không phải công cụ bảo vệ createdAt khỏi bị sửa

### 29.1. Raw update có thể thay metadata

Một user có quyền update document có thể chạy:

```javascript
db.orders.updateOne(
  { _id: "order-100" },
  { $set: { createdAt: new Date("2000-01-01T00:00:00Z") } }
);
```

MongoDB không tự hiểu `@CreatedDate` của Spring Data để chặn thao tác.

### 29.2. Chiến lược bảo vệ

- RBAC theo least privilege.
- Không nhận auditing fields trong public DTO.
- Service layer không cho sửa createdAt/createdBy.
- Update expressions chỉ cho phép danh sách fields.
- Database schema validation nếu phù hợp.
- Tách append-only audit collection khi có compliance requirement.
- Audit log access controls và retention.
- Dùng optimistic locking cho concurrent writes.
- Quan sát sửa metadata bất thường.

### 29.3. Không có “last writer identity” đáng tin nếu actor spoof

Nếu `AuditorAware` lấy user từ một header do client tùy chọn, thông tin `updatedBy` không còn đáng tin.

Audit identity phải đến từ trusted authentication/authorization context.

### 29.4. Actor là con người hay service?

Một scheduled job có thể sửa order thay người dùng. `updatedBy` nên phản ánh service actor thực hiện thay đổi, còn initiator gốc nếu cần nên lưu ở trường riêng:

```json
{
  "updatedBy": "service:shipment-consumer",
  "initiatedBy": "user-17"
}
```

Đừng trộn hai ý nghĩa rồi kết luận người dùng trực tiếp thực hiện write khi thực tế là worker.

---

## 30. Phân biệt audit metadata và change history

| Yêu cầu | createdAt/updatedAt/By | Audit history riêng |
|---|---|---|
| Hiển thị thời gian tạo/sửa gần nhất | Phù hợp | Có thể thừa |
| Hiển thị actor sửa gần nhất | Phù hợp | Có thể thừa |
| Xem toàn bộ các lần thay đổi | Không đủ | Cần |
| Lưu before/after values | Không | Cần thiết kế |
| Compliance/audit investigation | Chỉ bổ trợ | Cần cơ chế mạnh hơn |
| Event-driven integration | Không đủ | Outbox/change streams phù hợp |
| Khôi phục lại version cũ | Không đủ | Version history/backups |
| Phát hiện sửa audit fields bằng raw update | Không bảo đảm | Cần controls/monitoring |

### 30.1. Audit collection

Một audit record có thể gồm:

```json
{
  "_id": "audit-...",
  "entityType": "Order",
  "entityId": "order-100",
  "actorId": "user-17",
  "action": "STATUS_CHANGED",
  "eventTime": {"$date": "2026-11-14T09:30:00Z"},
  "before": {"status": "CREATED"},
  "after": {"status": "PAID"},
  "requestId": "req-..."
}
```

Dữ liệu audit rất nhạy cảm; cần encryption, retention, access control và nguyên tắc không ghi secrets/PII quá mức.

### 30.2. Atomic write của business và audit event

Nếu audit history phải đồng bộ tuyệt đối với business update, cân nhắc ghi cùng transaction trong MongoDB khi topology hỗ trợ; hoặc một kiến trúc outbox có business guarantees phù hợp.

Không chỉ gọi save order xong rồi insert audit history riêng nếu chấp nhận rằng bước hai có thể fail và làm mất audit evidence.

### 30.3. Change streams

Change streams có thể quan sát thay đổi MongoDB và phục vụ integration pipeline, nhưng cần:

- Replica set/sharded cluster và quyền phù hợp.
- Resume token management.
- Retention/oplog window awareness.
- Dedupe/idempotent consumer.
- Schema change handling.

Change streams không tự thay thế application actor nếu document không chứa actor metadata và sự kiện không ghi đủ danh tính.

---

## 31. Auditing và time-to-live index

Một câu hỏi dễ nhầm: muốn tự xóa dữ liệu sau 30 ngày, nên tạo TTL index trên `updatedAt` hay `createdAt`?

### 31.1. TTL theo createdAt

Nếu policy là “xóa sau 30 ngày kể từ khi tạo”, dùng `createdAt` làm TTL field phù hợp nếu không có legal hold/retention exception.

### 31.2. TTL theo updatedAt

Nếu policy là “xóa sau 30 ngày không có update”, TTL trên `updatedAt` có thể phù hợp.

Nhưng có nguy cơ:

- `repository.save()` vì lý do kỹ thuật cập nhật updatedAt dù business không đổi.
- Query-based updates quên set updatedAt nên TTL không gia hạn.
- Some services cập nhật server-side timestamp khác app-side timestamp.
- TTL monitor xóa asynchronous, không đảm bảo đúng thời điểm tuyệt đối.

### 31.3. Không dùng createdAt như business expiration

`createdAt` là audit metadata, còn `expiresAt` là business policy field; đôi khi cần tách rõ hai khái niệm.

Ví dụ:

```json
{
  "createdAt": {"$date": "..."},
  "updatedAt": {"$date": "..."},
  "expiresAt": {"$date": "..."}
}
```

### 31.4. TTL không phải cơ chế xóa chính xác từng millisecond

MongoDB TTL monitor hoạt động theo chu kỳ; không thiết kế bảo mật hoặc business SLA mà giả định document biến mất chính xác ở giây hết hạn.

---

## 32. Auditing khi import/migration/backfill

Legacy documents có thể không có `createdAt`/`updatedAt`. Nếu bạn đọc rồi `save()` chúng, auditing có thể điền metadata theo **thời điểm migration**, không phải thời điểm dữ liệu thực được tạo.

### 32.1. Vấn đề dữ liệu lịch sử

Ví dụ document order thực tạo từ 2022 nhưng chưa có createdAt. Migration năm 2026 bật auditing và save order.

Nếu framework coi document như new hoặc logic tự gán thiếu timestamp, bạn có thể mất ý nghĩa thời gian lịch sử.

### 32.2. Chiến lược

- Xác định source timestamp gốc.
- Thiết kế migration field mapping.
- Có `migrationAt`/`migratedBy` riêng.
- Không giả mạo `createdAt` từ migration time nếu cần đúng lịch sử.
- Giới hạn service account được phép backfill audit metadata.
- Dùng batch/query updates có policy rõ.
- Kiểm tra sample before/after và backups.

### 32.3. Raw bulk migration bỏ qua callbacks

Đó đôi khi là điều mong muốn nếu bạn đang backfill đúng một field và muốn tránh toàn bộ entity save overhead. Nhưng bắt buộc script phải tự xử lý audit metadata nếu business yêu cầu.

### 32.4. Không tự làm lại hàng loạt bởi callback

Nếu callback tự truy vấn/external calls cho hàng triệu entities trong migration, overhead tăng mạnh. Dùng migration tool/batching với checkpoints và metric.

---

## 33. Repository và service: ví dụ hoàn chỉnh

### 33.1. Repository

```java
package com.example.orders.repository;

import com.example.orders.domain.OrderDocument;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    List<OrderDocument> findByCustomerId(String customerId);
}
```

### 33.2. Service tạo và sửa

```java
package com.example.orders.service;

import com.example.orders.domain.OrderDocument;
import com.example.orders.repository.OrderRepository;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderDocument create(
            String customerId, String status) {

        OrderDocument order =
                new OrderDocument(customerId, status);

        return repository.insert(order);
    }

    public OrderDocument changeStatus(
            String id, String newStatus) {

        OrderDocument order = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Order not found: " + id));

        order.setStatus(newStatus);
        return repository.save(order);
    }
}
```

### 33.3. Lúc tạo

- `insert(order)` đi qua entity mapping/callbacks được hỗ trợ.
- created/modified metadata được điền theo config.
- ID/version được quản lý theo mapping.
- Trả về entity đã lưu.

### 33.4. Lúc sửa

- `findById` load object.
- `save` chạy callback trước convert.
- `updatedAt/updatedBy` được cập nhật nếu auditing hoạt động.
- `createdAt/createdBy` giữ nguyên theo semantics của existing entity.
- Nếu có `@Version`, concurrency conflict được kiểm soát.

### 33.5. Không cho client toàn quyền sửa document

API nên map DTO chỉ gồm allowable fields, không deserialize request trực tiếp vào entity có auditing fields rồi `save` vô điều kiện. Cần authorization và business validation.

---

## 34. Test integration với MongoDB thật

Một unit test gọi trực tiếp method `onBeforeConvert()` chỉ chứng minh code callback, không chứng minh Spring đã đăng ký bean, xác định isNew và persist đúng BSON.

### 34.1. Công cụ test

Các lựa chọn:

- `@DataMongoTest` cho slice testing.
- `@SpringBootTest` khi cần Spring Security, auditing config và transaction integration.
- Testcontainers MongoDB với replica set khi cần transactions.
- Isolated MongoDB test service/CI.
- Fixed Clock khi muốn assertions deterministic.

### 34.2. Ví dụ kiểm tra timestamps

Giả sử repository và auditing config đã được khởi tạo trong integration test:

```java
OrderDocument created =
        repository.insert(
                new OrderDocument(
                        "customer-100", "CREATED"));

assertNotNull(created.getCreatedAt());
assertNotNull(created.getUpdatedAt());

Instant firstCreatedAt = created.getCreatedAt();
Instant firstUpdatedAt = created.getUpdatedAt();

created.setStatus("PAID");
OrderDocument saved = repository.save(created);

assertEquals(firstCreatedAt, saved.getCreatedAt());
assertNotNull(saved.getUpdatedAt());
assertFalse(saved.getUpdatedAt().isBefore(firstUpdatedAt));
```

Đây là assertion minh họa khi `modifyOnCreate=true`. Nếu `modifyOnCreate=false`, updatedAt khi insert có thể null và test phải đổi theo policy.

### 34.3. Kiểm tra BSON ở MongoDB

Trong `mongosh`:

```javascript
db.getSiblingDB("orders_lab")
  .orders.findOne({ _id: "..." });
```

Xác nhận:

- Audit fields có thực trong document.
- Date fields là BSON Date.
- Actor IDs đúng.
- ID/version hợp lệ.

Không chỉ kiểm tra Java getter.

### 34.4. Test actor

Dùng một identity đã xác thực hoặc controlled `AuditorAware` test bean:

- Insert dưới actor A → createdBy=A.
- Update dưới actor B → createdBy=A, updatedBy=B.
- Không có authentication → policy đúng (empty/reject/service identity).

### 34.5. Test query update không tự audit

1. Tạo document và lưu `updatedAt`.
2. Gọi `mongoTemplate.updateFirst` chỉ set status.
3. Đọc document từ database.
4. Kiểm tra `updatedAt` **không tự đổi** vì query update không chạy entity auditing callback.
5. Lặp lại với explicit `updatedAt` để xác nhận policy.

### 34.6. Test version conflict

Hai bản entity cùng version:

1. Load A và B.
2. Save A.
3. Save B.
4. Xác nhận optimistic locking exception theo transaction/write concern phù hợp.
5. Không cho B lặng lẽ overwrite A.

### 34.7. Test callback ordering

Đăng ký hai BeforeConvert callbacks có `@Order` rõ và test thứ tự transformation. Không dựa vào log timing không ổn định.

### 34.8. Test transaction rollback

Nếu dùng transactions:

- Insert entity trong transaction.
- Callback gán createdAt/actor.
- Abort transaction.
- Đọc DB không có document.
- Không có event bên ngoài được publish từ callback.

---

## 35. Test với fixed Clock và actor

Một integration test có thể cấu hình:

```java
@TestConfiguration
class TestAuditConfig {

    @Bean
    @Primary
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-11-14T09:30:00Z"),
                ZoneOffset.UTC);
    }

    @Bean("testAuditor")
    AuditorAware<String> testAuditor() {
        return () -> Optional.of("test-user");
    }
}
```

**Chú ý:** Nếu production configuration đã đăng ký nhiều `AuditorAware` beans và `@EnableMongoAuditing(auditorAwareRef=...)` chỉ đích danh bean khác, thêm `@Primary` chưa đủ để audit dùng test bean. Phải đảm bảo bean reference được xác định đúng trong test context.

### 35.1. Vì sao fixed Clock tốt hơn Thread.sleep?

Nếu test:

```java
Thread.sleep(1000);
```

để chờ updatedAt lớn hơn createdAt, test sẽ chậm, flakier và không chứng minh thời gian do framework lấy từ đâu.

Fixed/mutable Clock cho phép kiểm soát thời điểm mà không cần ngủ.

### 35.2. BSON precision

Khi so sánh thời gian đọc lại từ MongoDB, chọn mốc thời gian có milliseconds chính xác hoặc normalize precision theo BSON Date.

### 35.3. Đừng tự mock toàn MongoTemplate nếu muốn test callbacks

Mock repository/MongoTemplate chỉ kiểm tra method invocation, không chạy real mapping lifecycle. Dùng integration test cho auditing registration và BSON mapping.

---

## 36. Performance: callbacks có chi phí gì?

### 36.1. Auditing metadata thường nhẹ

Việc gán vài fields là overhead nhỏ trong phần lớn workload, nhưng vẫn có:

- Time provider call.
- Auditor lookup.
- Mapping metadata.
- Callback invocation.
- Object mutation/copy.
- Serialization BSON.
- Additional field size.

### 36.2. Callback có I/O làm chậm mọi save

Nếu `BeforeConvertCallback` gọi API user service để lấy actor profile cho mỗi document:

```text
1000 saves/s
× 1 HTTP request/callback
= 1000 extra network calls/s
```

Không nên làm việc này nếu chỉ cần actor ID đã có trong security context.

### 36.3. N+1 khi AfterConvert

Một `findAll()` trả 10.000 documents có thể gọi 10.000 callback instances. Nếu mỗi callback query phụ trợ, tổng latency và pool load tăng mạnh.

### 36.4. Bulk path đánh đổi

Bulk/query updates thường bỏ qua per-entity auditing/callbacks để hiệu quả hơn. Vì vậy:

- Tăng throughput.
- Giảm số object conversions.
- Nhưng phải tự cập nhật metadata và invariants.

Không chọn bulk rồi mong vẫn có mọi hook.

### 36.5. Metrics phù hợp

Theo dõi:

- Save/insert latency p95/p99.
- MongoDB writes/s.
- Callback execution duration khi custom callback có logic đáng kể.
- Error rate do validation/version conflict.
- Actor lookup failures.
- MongoDB latency.
- Size của documents audit metadata.
- Batch throughput.

### 36.6. Không log actor cho mọi write ở INFO nếu không cần

Nó có thể tăng log volume và lộ thông tin. Metrics nên dùng labels low-cardinality, không đặt user ID làm metric tag cho mỗi request.

---

## 37. Những lỗi hay gặp và hướng xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `createdAt` null sau save | Chưa bật `@EnableMongoAuditing` | Xem config/component scan |
| `updatedBy` null | `AuditorAware` trả empty | Kiểm tra SecurityContext/service identity |
| `updatedAt` không đổi khi `updateFirst` | Query update bỏ qua entity auditing | Set field trong Update |
| `createdAt` bị thay khi save | Entity bị coi là new | Kiểm tra ID/@Version/isNew |
| `updatedAt` có giá trị ngay lúc insert | `modifyOnCreate=true` | Chọn policy hoặc đặt false |
| `updatedAt` không có lúc insert | `modifyOnCreate=false` | Đúng policy nếu muốn |
| Không tìm được AuditorAware bean | Bean ngoài scan/multiple beans | Đăng ký và chỉ rõ auditorAwareRef |
| Actor sai trong @Async | Thread-local security context không propagate | Explicit actor hoặc context propagation |
| Reactive auditing không chạy | Dùng imperative infrastructure | EnableReactiveMongoAuditing/ReactiveAuditorAware |
| BeforeSave đổi entity nhưng BSON không đổi | Conversion đã diễn ra | Sửa Document hoặc dùng BeforeConvert |
| Event listener chạy không đúng thứ tự | Async ApplicationEventMulticaster | Dùng EntityCallback cho mutation |
| Callback không chạy trên nested object | Chỉ root lifecycle được xử lý như root entity | Audit metadata trên root/đúng mapping |
| Callback không chạy với raw driver | Bỏ qua Spring mapping | Tự set audit fields |
| Bulk operation không set actor/time | Không qua per-entity callbacks | Explicit audit update |
| OptimisticLockingFailureException | Concurrent save version cũ | Read/reconcile/retry có kiểm soát |
| Date lệch timezone | LocalDateTime/default zone | Dùng Instant/UTC policy |
| Instant nanos bị đổi | BSON Date millisecond precision | Normalize expected precision |
| Callback gửi event nhưng transaction abort | AfterSave không đồng nghĩa commit | Dùng outbox/after-commit strategy |
| Sau migration mọi createdAt là ngày migration | Backfill sai source | Giữ original timestamp, migration metadata |
| Security actor giả | Tin client header | Dùng authenticated identity |
| Không thấy auditing trong unit test mock | Mock bypass mapping | Integration test |
| Version không tăng như nghĩ với bulk | Bulk/version semantics riêng | Explicit policy/test |
| Tên collection khác expected | Custom collection name/SpEL | Kiểm tra callback collection arg |
| Dùng nhiều @EnableMongoAuditing | Config trùng/không rõ auditor | Một cấu hình rõ ràng |
| createdBy là object lớn | AuditorAware trả principal entity | Lưu stable user ID |
| Service không tìm được entity | Save ID/upsert/new detection | Kiểm tra @Id/@Version/Persistable |
| Callback tự save gây recursion | Lưu lại cùng entity trong hook | Tách logic khỏi hook |

---

## 38. Case study: lỗi âm thầm khi chuyển save sang updateFirst

### 38.1. Ban đầu

Service thay đổi trạng thái đơn bằng:

```java
OrderDocument order =
        repository.findById(id).orElseThrow();

order.setStatus("SHIPPED");
repository.save(order);
```

Auditing hoạt động:

```text
status: SHIPPED
updatedAt: now
updatedBy: warehouse-user
```

### 38.2. Tối ưu hiệu năng

Team thay bằng:

```java
mongoTemplate.updateFirst(
        Query.query(Criteria.where("_id").is(id)),
        Update.update("status", "SHIPPED"),
        OrderDocument.class);
```

Update thành công, nhưng `updatedAt` và `updatedBy` giữ nguyên.

### 38.3. Vì sao?

Query update không nạp entity để đi qua entity save pipeline và `AuditingEntityCallback`.

### 38.4. Khắc phục

```java
Update update = new Update()
        .set("status", "SHIPPED")
        .set("updatedBy", authenticatedActorId)
        .currentDate("updatedAt");

mongoTemplate.updateFirst(
        Query.query(Criteria.where("_id").is(id)),
        update,
        OrderDocument.class);
```

### 38.5. Bài học kiến trúc

Một ứng dụng có cả entity saves và query updates cần **chính sách audit ở tầng data-access service**, tránh rải rác mỗi nơi tự nhớ set fields.

Có thể tạo helper:

```java
public Update withAudit(
        Update update, String actorId) {
    return update
            .set("updatedBy", actorId)
            .currentDate("updatedAt");
}
```

Nhưng helper phải được sử dụng đồng bộ bởi tất cả query update paths được chấp thuận và test. Nó không can thiệp tự động vào raw drivers hay migration scripts ngoài ứng dụng.

---

## 39. Case study: event bị phát mặc dù transaction rollback

### 39.1. Anti-pattern

```java
@Component
class NotifyAfterSave
        implements AfterSaveCallback<OrderDocument> {

    @Override
    public OrderDocument onAfterSave(
            OrderDocument order,
            Document bson,
            String collection) {

        kafkaPublisher.publish("OrderCreated", order.getId());
        return order;
    }
}
```

### 39.2. Điều gì xảy ra?

Một service:

```text
start transaction
insert order
  → AfterSaveCallback publishes event
update inventory
  → WriteConflict
abort transaction
```

Kafka đã nhận event cho order không commit.

### 39.3. Thiết kế tốt hơn

- Ghi order và outbox event cùng MongoDB transaction.
- Commit transaction.
- Background worker đọc outbox và publish.
- Consumer deduplicate bằng event ID.

### 39.4. Callback vẫn dùng để làm gì?

Có thể dùng callback để điền metadata, validate, normalize hoặc thu metric nhẹ, nhưng không nên coi nó là durable integration event dispatcher.

---

## 40. Case study: actor bị mất ở asynchronous message consumer

### 40.1. Triệu chứng

HTTP service ghi `createdBy=user-17` đúng. Kafka consumer dùng cùng repository lưu order cập nhật `updatedBy=null`.

### 40.2. Nguyên nhân

AuditorAware chỉ đọc `SecurityContextHolder`, còn worker thread không có HTTP authentication.

### 40.3. Giải pháp

- Xác định service actor `service:fulfillment-consumer`.
- Ghi initiator gốc ở field riêng nếu cần.
- Cung cấp actor context đã xác thực/có scope cho worker.
- Không giả mạo user actor trong ThreadLocal.
- Test async flow thực tế.

### 40.4. Không tự suy actor từ document hiện có

Đừng luôn lấy `createdBy` để điền `updatedBy` khi thiếu context; điều đó làm sai audit history về actor thực sự sửa lần cuối.

---

## 41. Case study: dữ liệu legacy bị ghi sai createdAt

### 41.1. Triệu chứng

Sau migration, hàng triệu documents có `createdAt` bằng ngày triển khai migration.

### 41.2. Nguyên nhân có thể

- Backfill không lấy source creation time.
- Save entity với ID/version metadata khiến framework coi là new.
- Migration tự set createdAt=now cho mọi row.
- Dữ liệu cũ không có auditing fields và business process không phân biệt creation vs migration.

### 41.3. Xử lý

1. Xác định document creation evidence từ source.
2. Phân biệt `createdAt` và `migratedAt`.
3. Thiết kế migration job có snapshot/backup.
4. Chạy dry-run/small batch.
5. Cập nhật idempotent theo điều kiện field missing.
6. Test sample đã có/thiếu fields.
7. Không chạy `save()` hàng loạt nếu auditing side effects không mong muốn.

---

## 42. Bài tập 1: bật auditing tối thiểu

Yêu cầu:

1. Tạo Spring Boot project có MongoDB starter.
2. Tạo entity `Customer` với ID, name, createdAt, updatedAt.
3. Bật `@EnableMongoAuditing`.
4. Insert document qua `MongoRepository`.
5. Đọc BSON trong `mongosh`.
6. Update qua `save()`.
7. So createdAt và updatedAt.

Câu hỏi: nếu không khai báo `AuditorAware` thì timestamp annotations có hoạt động không?

---

## 43. Bài tập 2: createdBy/updatedBy

Tạo `AuditorAware<String>` với ba actors:

- user-A.
- user-B.
- service:batch.

Thực hiện:

1. user-A insert document.
2. user-B update.
3. batch update.
4. Đọc `createdBy`/`updatedBy` sau mỗi bước.
5. Không giả định SecurityContext có sẵn trong scheduled job.

Yêu cầu giải thích vì sao không nên lưu nguyên JWT token vào createdBy.

---

## 44. Bài tập 3: modifyOnCreate

Chạy hai cấu hình trên lab:

- `modifyOnCreate=true`.
- `modifyOnCreate=false`.

So sánh trạng thái `updatedAt` và `updatedBy` ngay sau insert. Hãy viết policy phù hợp khi UI muốn hiển thị “Chưa từng chỉnh sửa” cho document mới.

---

## 45. Bài tập 4: BeforeConvert so với BeforeSave

Viết hai callbacks:

1. `BeforeConvertCallback` trim tên sản phẩm.
2. `BeforeSaveCallback` thêm `schemaRevision` vào BSON Document.

Thử mutate persistent field Java object trong BeforeSave mà không sửa BSON. Dùng `mongosh` kiểm tra document thực tế và giải thích kết quả.

---

## 46. Bài tập 5: save và updateFirst

Tạo order rồi:

1. Update status qua `repository.save()`.
2. Ghi lại updatedAt/updatedBy.
3. Update status qua `mongoTemplate.updateFirst` chỉ có `$set status`.
4. Kiểm tra auditing fields.
5. Viết lại updateFirst với `$currentDate` và actor.
6. Giải thích vì sao annotation không phải MongoDB trigger.

---

## 47. Bài tập 6: thời gian và precision

Dùng:

```text
2026-11-14T09:00:00.123456789Z
```

làm fixed clock time:

1. Insert entity với `@CreatedDate Instant`.
2. Đọc Java object.
3. Đọc BSON document.
4. Giải thích millisecond precision.
5. Thảo luận LocalDateTime vs Instant.
6. Thiết kế UTC policy cho ba services chạy ở các timezone khác nhau.

---

## 48. Bài tập 7: optimistic locking

Tạo entity có `@Version Long version`:

1. Load thành hai objects A và B.
2. Sửa A và save.
3. Sửa B và save.
4. Quan sát exception.
5. Đề xuất merge/retry policy.
6. Giải thích vì sao updatedAt không phải cơ chế thay thế @Version.

---

## 49. Bài tập 8: reactive auditing

Dùng WebFlux/ReactiveMongoRepository:

1. Bật `@EnableReactiveMongoAuditing`.
2. Cấu hình `ReactiveAuditorAware<String>`.
3. Lấy actor từ ReactiveSecurityContextHolder.
4. Insert bằng reactive repository.
5. Kiểm tra createdBy khi subscribe.
6. Viết ReactiveBeforeConvertCallback.
7. Giải thích vì sao không dùng ThreadLocal SecurityContextHolder đơn thuần.

---

## 50. Bài tập 9: transaction và after-save side effects

Một callback đang gửi email trong `AfterSaveCallback`. Service lưu order trong transaction nhưng lệnh update inventory sau đó fail.

Trả lời:

1. Email có thể đã gửi không?
2. Order có còn trong database không?
3. Điều gì khiến hai hệ thống lệch nhau?
4. Đề xuất outbox.
5. Lập integration test rollback.
6. Nêu cách xử lý callback nếu transaction retry.

---

## 51. Bài tập 10: backfill legacy data

Có 100.000 documents thiếu `createdAt` nhưng có `legacyCreatedDate`.

1. Thiết kế migration chỉ điền khi createdAt missing.
2. Không ghi đè documents đã có createdAt.
3. Ghi `migratedAt` và `migratedBy` riêng.
4. Đảm bảo batch retry idempotent.
5. Giải thích vì sao entity save callback không nên quyết định toàn bộ migration policy.
6. Xác minh counts và sample documents sau backfill.

---

## 52. Bài tập 11: auditor security

Một hệ thống lấy actor ID từ HTTP header `X-User` không được xác minh.

1. Mô tả cách giả mạo createdBy/updatedBy.
2. Thay bằng principal của Spring Security.
3. Xử lý AnonymousAuthenticationToken.
4. Xử lý async scheduled job.
5. Thiết kế service actor và initiator riêng.
6. Viết test cho request thiếu authentication.

---

## 53. Bài tập 12: chọn giải pháp audit history

Yêu cầu compliance:

- Biết mọi lần sửa status.
- Có before/after values.
- Có actor/time.
- Giữ records 7 năm.
- Không cho người dùng sửa audit evidence.

Phân tích vì sao `@LastModifiedDate`/`@LastModifiedBy` không đủ. Đề xuất audit collection hoặc event history, RBAC, encryption, retention, tamper-evidence và transaction/outbox consistency.

---

## 54. Checklist triển khai

### 54.1. Enablement

- [ ] Đã thêm MongoDB starter tương thích.
- [ ] Có `@EnableMongoAuditing` hoặc `@EnableReactiveMongoAuditing` phù hợp.
- [ ] Configuration nằm trong ApplicationContext.
- [ ] Dùng đúng annotations của Spring Data.
- [ ] Chỉ định `auditorAwareRef` khi có nhiều provider.
- [ ] Đã xác định `modifyOnCreate` và `setDates` policy.

### 54.2. Entity model

- [ ] `createdAt`/`updatedAt` dùng kiểu thời gian phù hợp, ưu tiên Instant khi hợp lý.
- [ ] `createdBy`/`updatedBy` lưu stable actor identity, không lưu secrets.
- [ ] Có @Version nếu cần optimistic locking.
- [ ] Hiểu isNew của ID cấp sẵn.
- [ ] Không để public DTO ghi audit fields tùy ý.
- [ ] Immutable entity mapping/callback đã được kiểm thử.

### 54.3. Callback lifecycle

- [ ] Logic trước conversion nằm ở BeforeConvert.
- [ ] Logic sửa BSON nằm ở BeforeSave.
- [ ] Không kỳ vọng sửa entity persistent ở BeforeSave sẽ sửa BSON.
- [ ] Đã đặt callback order khi cần.
- [ ] Tránh side effects trong AfterSave.
- [ ] Không dùng JPA lifecycle annotations thay Mongo callbacks.
- [ ] Không cho callbacks gọi I/O chậm hoặc recursion.
- [ ] Reactive code dùng reactive callbacks.

### 54.4. Write paths

- [ ] Đã kiểm kê repository save/insert.
- [ ] Đã kiểm kê MongoTemplate updateFirst/updateMulti/findAndModify/upsert.
- [ ] Đã kiểm kê repository @Update queries.
- [ ] Đã kiểm kê bulk operations.
- [ ] Đã kiểm kê raw driver/mongosh/migration writers.
- [ ] Mọi query update cần audit đều set metadata explicitly.
- [ ] Có policy timestamp source và actor source nhất quán.

### 54.5. Transactions và security

- [ ] Actor lấy từ trusted authentication context.
- [ ] Scheduled jobs có service actor riêng.
- [ ] Không coi AfterSave là transaction commit.
- [ ] Event integration có outbox/recovery strategy.
- [ ] Optimistic locking/write concern được kiểm tra.
- [ ] Audit history compliance được thiết kế riêng khi cần.

### 54.6. Tests và monitoring

- [ ] Có real MongoDB integration test cho insert/save/update.
- [ ] Có test actor A/B và no-auth.
- [ ] Có test createdAt không đổi sau update.
- [ ] Có test modifyOnCreate.
- [ ] Có test query update bỏ qua callbacks.
- [ ] Có test version conflict.
- [ ] Có test reactive flow nếu dùng.
- [ ] Có test transaction rollback.
- [ ] Có kiểm tra BSON Date/precision.
- [ ] Có monitoring actor null hoặc audit timestamp missing bất thường.

---

## 55. Những nhầm lẫn phổ biến

| Hiểu lầm | Thực tế |
|---|---|
| Gắn `@CreatedDate` là đủ | Phải bật auditing infrastructure |
| Auditing luôn cần AuditorAware | Chỉ timestamps không bắt buộc |
| `@LastModifiedDate` chỉ đổi khi field nghiệp vụ có diff | Save vẫn có thể cập nhật |
| updatedAt khi tạo luôn null | `modifyOnCreate=true` mặc định có thể điền |
| createdAt lấy từ MongoDB commit clock | Thường là time provider ở application trước write |
| Spring Data tự audit mọi write trong collection | Chỉ những đường đi qua pipeline được hỗ trợ |
| updateFirst kích hoạt BeforeConvert | Query update không giống entity save |
| Raw driver cũng chạy annotations | Không |
| Bulk writes luôn chạy callbacks | Không nên giả định |
| BeforeSave sửa Java property là đủ | BSON đã được convert |
| AfterSave luôn đồng nghĩa transaction commit | Không |
| ApplicationEvent listener có thứ tự chắc chắn khi async | Không |
| Callback nào cũng chạy trên embedded object | Root lifecycle không tương đương nested event |
| Callback không có overhead | Có; nhất là nếu gọi network/query |
| @Id nonnull luôn là existing | Còn @Version/Persistable/isNew rules |
| @Version và updatedAt cùng chức năng | Khác nhau |
| updatedAt đủ để chống concurrent overwrite | Không |
| ActorAware luôn có user trong @Async | Không |
| Header X-User là actor đáng tin | Chỉ nếu trusted/verified |
| ReactiveAuditorAware dùng ThreadLocal thông thường | Nên dùng Reactor Context |
| String date giống BSON Date | Không |
| Instant nanos luôn được giữ nguyên trong BSON Date | Precision thường là milliseconds |
| Save trong transaction có createdAt nghĩa đã commit | Transaction có thể rollback |
| Auditing fields là audit trail đầy đủ | Chỉ metadata đầu/cuối |
| Spring Security principal nên lưu toàn object vào document | Nên lưu stable ID |
| Migration save không thể thay metadata lịch sử | Có thể nếu isNew/logic sai |
| Audit metadata tự chống tampering ở DB | Cần RBAC/validation/history riêng |
| Mọi callback lỗi sẽ được retry an toàn | Cần idempotency/transaction semantics |
| Tests chỉ dùng Mockito đủ xác minh auditing | Cần integration test mapping |

---

## 56. Tài liệu tham khảo chính thức

Các tài liệu sau thuộc Spring Data MongoDB và Spring Data Commons. Khi ứng dụng dùng phiên bản cũ hoặc mới, đối chiếu đúng release line để xem callback signature, auditing options và mapping behavior.

- [Spring Data MongoDB — Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/mongodb/reference/data-commons/auditing.html)
- [Spring Data MongoDB — Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html)
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [Spring Data MongoDB — Template API](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB — Repositories](https://docs.spring.io/spring-data/mongodb/reference/repositories.html)
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking)
- [Spring Data MongoDB API — EnableMongoAuditing](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/config/EnableMongoAuditing.html)
- [Spring Data MongoDB API — BeforeConvertCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeConvertCallback.html)
- [Spring Data MongoDB API — BeforeSaveCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeSaveCallback.html)
- [Spring Data MongoDB API — AuditingEntityCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/AuditingEntityCallback.html)
- [Spring Data MongoDB — Bulk Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.bulk-operations)
- [MongoDB Manual — BSON Date](https://www.mongodb.com/docs/manual/reference/bson-types/#date)
- [MongoDB Manual — Optimistic Concurrency and Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [Spring Security — Servlet Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/index.html)
- [Spring Security — Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html)

> **Chú ý:** Những ví dụ trình bày khung cấu hình và Java operations nhằm làm rõ lifecycle. Khi triển khai, chọn đúng dependency versions theo Spring Boot BOM, đảm bảo class/interface signature tương ứng và chạy integration tests trên MongoDB thật. Không coi ví dụ là script thay thế cho security, schema migration và audit compliance runbook của hệ thống.

---

## 57. Tổng kết

1. **Spring Data MongoDB auditing** tự điền created/modified timestamps và actor metadata khi entity lưu qua những mapping paths được hỗ trợ.
2. Bật qua **`@EnableMongoAuditing`**, dùng `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, `@LastModifiedBy`; nếu chỉ cần timestamps thì không bắt buộc `AuditorAware`.
3. **`AuditorAware<T>`** lấy actor từ trusted identity context; batch/async/reactive flows cần chính sách truyền actor phù hợp.
4. **`DateTimeProvider`** quyết định nguồn thời gian; `Instant` và UTC phù hợp cho nhiều hệ thống phân tán, còn BSON Date thường có millisecond precision.
5. **`modifyOnCreate=true`** mặc định có thể điền updatedAt/updatedBy ngay lúc tạo; chọn policy minh bạch.
6. Việc phân biệt **new/existing** thông qua ID/version/Persistable ảnh hưởng trực tiếp auditing creation vs modification.
7. **`AuditingEntityCallback`** hoạt động ở **BeforeConvert**. `BeforeConvertCallback` phù hợp sửa persistent entity; `BeforeSaveCallback` chạy khi BSON Document đã tạo và nên sửa chính Document nếu muốn thay dữ liệu lưu.
8. **Query-based updates, bulk writes, raw driver và mongosh** không tự đi qua entity auditing pipeline như `save(entity)`; phải cập nhật `updatedAt/updatedBy` rõ ràng theo policy.
9. **AfterSave không phải after-commit của business transaction**, vì vậy không gửi external event quan trọng trực tiếp trong callback; cân nhắc outbox.
10. **Audit metadata không phải lịch sử bất biến**: yêu cầu compliance cần cơ chế audit history, access controls, retention và transaction consistency riêng.
11. Luôn có **integration tests** xác minh BSON thực, actor identity, timestamps, version conflict, update paths và callback ordering.

**Nguyên tắc vận hành:** Để auditing đáng tin, phải làm rõ **đường ghi dữ liệu nào chạy callback, actor/time lấy từ nguồn nào, trạng thái entity được phân loại ra sao và những cập nhật nào cố tình bỏ qua framework**. Chỉ khi kiểm soát đủ bốn điểm đó, các trường `createdAt`, `updatedAt`, `createdBy` và `updatedBy` mới phản ánh nhất quán hành vi hệ thống.
