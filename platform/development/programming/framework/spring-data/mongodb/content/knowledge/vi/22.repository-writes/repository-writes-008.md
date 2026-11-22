# Xóa mềm bằng điều kiện đọc và lệnh cập nhật nhất quán

> **Chương:** Ghi qua repository  
> **Module:** `SPRING_DATA_MONGODB`

**Xóa mềm** (*soft delete*) là kỹ thuật đánh dấu một document không còn hiển thị trong luồng nghiệp vụ thông thường nhưng **không xóa vật lý** nó khỏi MongoDB. Kỹ thuật này hữu ích khi cần phục hồi đơn hàng, kiểm tra lịch sử thao tác, bảo vệ quan hệ tham chiếu hoặc trì hoãn xóa dữ liệu theo chính sách lưu trữ. Tuy nhiên, chỉ thêm field `deleted = true` là **chưa đủ**: nếu repository vẫn dùng `findById()` hoặc `findAll()` mặc định, bản ghi đã xóa vẫn có thể xuất hiện; nếu việc xóa chỉ đơn giản là đọc entity rồi `save`, thay đổi đồng thời hoặc field BSON không có trong model Java có thể bị ghi đè.

Một triển khai đáng tin cậy phải thống nhất **hai nửa của hợp đồng**:

- **Đường đọc**: tất cả truy vấn nghiệp vụ cần thấy bản ghi còn hiệu lực phải giới hạn theo tenant/quyền và trạng thái **chưa xóa**; chỉ đường đọc quản trị/phục hồi được phép nhìn thấy tombstone.
- **Đường ghi**: thao tác xóa mềm phải cập nhật **nguyên tử trên một document**, kiểm tra bản ghi còn hiệu lực cùng phiên bản dự kiến, đặt dấu xóa và metadata; mọi thao tác ghi khác cũng phải tôn trọng trạng thái đã xóa.

Bài học thuộc module `SPRING_DATA_MONGODB`: kết nối và ánh xạ document, thao tác qua `MongoTemplate` hoặc repository, thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu. Phần này tập trung vào **sự nhất quán giữa điều kiện đọc và lệnh cập nhật trong chương Ghi qua repository**, không đồng nhất soft delete với lệnh delete vật lý.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa trạng thái `ACTIVE`/`DELETED` và các bất biến dữ liệu cho `deleted`, `deletedAt`, `deletedBy`, `version`.
2. Viết repository methods chỉ đọc tài liệu chưa xóa; chỉ ra vì sao `findById`, `findAll`, `count` và `existsById` kế thừa **không tự có filter soft delete**.
3. Phân biệt derived finder với `@Query` khi cần điều kiện tenant, `OR` và dữ liệu legacy thiếu field.
4. Tạo lệnh xóa mềm có điều kiện bằng repository `@Query` + `@Update` hoặc custom repository fragment dùng `MongoTemplate`.
5. Bảo vệ bản ghi khỏi lost update bằng **expected version**, kiểm tra số bản ghi khớp và xử lý retry/idempotency.
6. Thiết kế phục hồi, unique index có điều kiện, migration dữ liệu cũ và chính sách xóa vật lý sau thời gian lưu giữ.
7. Kiểm thử tích hợp trên BSON thật để chứng minh không rò rỉ bản ghi đã xóa và không sửa nhầm tenant.

## 2. Chốt hợp đồng dữ liệu trước khi viết repository

Ta dùng collection `orders` trong một hệ thống có nhiều tenant. Đề xuất schema:

```javascript
{
  _id: "ORD-101",
  tenantId: "TENANT-A",
  orderCode: "SO-2026-101",
  status: "PAID",
  deleted: false,         // BSON Boolean, có giá trị tường minh
  version: NumberLong(3),
  updatedAt: ISODate("2026-11-19T08:00:00Z")
  // deletedAt/deletedBy không có khi ACTIVE.
}
```

Khi xóa mềm:

```javascript
{
  _id: "ORD-101",         // GIỮ NGUYÊN ID
  tenantId: "TENANT-A",
  orderCode: "SO-2026-101",
  status: "PAID",         // trạng thái nghiệp vụ cũ được giữ
  deleted: true,
  deletedAt: ISODate("2026-11-20T03:00:00Z"),
  deletedBy: "user-42",
  version: NumberLong(4),
  updatedAt: ISODate("2026-11-20T03:00:00Z")
}
```

### 2.1. Bảng trạng thái

| Trạng thái | `deleted` | `deletedAt` | `deletedBy` | Truy vấn nghiệp vụ |
| --- | --- | --- | --- | --- |
| `ACTIVE` | BSON `false` | Vắng mặt | Vắng mặt | Được đọc khi đúng tenant/quyền và điều kiện khác |
| `DELETED` | BSON `true` | Timestamp UTC | Actor ID đã xác minh | Không xuất hiện trong truy vấn thông thường |
| `RESTORED` | BSON `false` | Được xóa hoặc chuyển vào audit log | Được xóa hoặc chuyển vào audit log | Được đọc trở lại nếu thỏa ràng buộc nghiệp vụ |

**Bất biến quan trọng:** trong schema canonical, mọi document còn hiệu lực phải có `deleted: false` **tường minh**. Không để lẫn `false`, `null` và field thiếu nếu không có kế hoạch tương thích. Khi document đã xóa, cần có timestamp và actor theo chính sách kiểm toán; nếu metadata audit cần bất biến, nên ghi thêm một lịch sử sự kiện riêng thay vì chỉ dùng hai field có thể bị xóa lúc phục hồi.

### 2.2. Tại sao không chỉ dùng deletedAt?

Một phương án khác là coi `deletedAt != null` đồng nghĩa đã xóa. Phương án này có thể áp dụng, nhưng phải nhớ trong MongoDB `{ deletedAt: null }` thường khớp cả **BSON null** và **field không tồn tại**. Khi dùng các điều kiện như `$ne: null`, `$exists` hoặc index một phần, ngữ nghĩa có thể khác suy luận từ Java.

Bài dùng **`deleted` Boolean làm nguồn sự thật của trạng thái**, còn `deletedAt`/`deletedBy` là metadata. Nếu dự án chọn mô hình chỉ có `deletedAt`, phải viết lại **toàn bộ** finder, update predicate, index và test tương ứng; không trộn hai quy ước trong cùng hệ thống.

### 2.3. Chỉ đổi cờ hay xóa thật?

Một thao tác soft delete **không** gọi `MongoRepository.delete(...)`, `deleteById(...)`, `MongoTemplate.remove(...)` hoặc `deleteMany(...)`. Các phương thức này thường dẫn tới **xóa vật lý** document. Ngay cả tên repository `deleteByStatus(...)` nếu được suy diễn theo cơ chế delete query cũng không tự biến thành việc đặt `deleted = true`.

Soft delete trong bài là **update có điều kiện**. Việc xóa vật lý chỉ thuộc quy trình retention/purge riêng, có quyền, log và chính sách khôi phục.

## 3. Luồng nghiệp vụ cần nhất quán

```text
                       HTTP / Service
                            |
                   kiểm tra quyền tenant
                            |
         +------------------+------------------+
         |                                     |
     READ ACTIVE                           SOFT DELETE
         |                                     |
 tenantId = allowedTenant             tenantId = allowedTenant
 AND deleted = false                 AND _id = requestedId
 AND filter nghiệp vụ                AND deleted = false
         |                            AND version = expectedVersion
         v                                     |
  Repository finder                            v
  / Query / count                         Atomic $set flags
  / exists / aggregation                  + $inc version
         |                                     |
         v                                     v
  không thấy tombstone                   matchedCount = 1 ?
                                               |
                                 +-------------+--------------+
                                 |                            |
                            Có: thành công            Không: conflict/not found/
                                                    đã xóa/khác tenant
```

Một phần mềm có thể che được tombstone ở trang danh sách nhưng vẫn sai nếu tìm bằng ID, đếm tổng, search, export hoặc aggregation không áp điều kiện `deleted: false`. Ngược lại, filter đọc có thể rất chặt nhưng thao tác xóa mềm vẫn sai nếu update theo ID mà không kiểm tra tenant, trạng thái còn hiệu lực hoặc version hiện hành.

### 3.1. Những tình huống cần quy định

- Xóa lần đầu: từ `ACTIVE` sang `DELETED`, tăng version đúng một lần.
- Xóa lại cùng document: chọn **không thao tác** (idempotent theo trạng thái) hoặc trả conflict theo hợp đồng API; không ghi đè `deletedAt`/`deletedBy` lần đầu một cách ngẫu nhiên.
- Hai người cùng xóa: một update khớp, update còn lại không khớp version/trạng thái.
- Xóa đồng thời với thanh toán: thao tác cập nhật trạng thái đơn cũng phải kiểm tra `deleted: false` và version để không sửa document đã bị xóa.
- Đọc document của tenant khác: không được trả document hoặc tiết lộ sự tồn tại của nó vì lỗi trả về quá cụ thể.
- Phục hồi: là một **chuyển trạng thái có điều kiện** riêng, có quyền và ràng buộc unique key.

## 4. Entity Java: ánh xạ cờ xóa, metadata và version

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    String orderCode,
    String status,
    Boolean deleted,
    Instant deletedAt,
    String deletedBy,
    @Version Long version,
    Instant updatedAt
) {}
```

`@Id` ánh xạ `id` sang BSON `_id`. Trong ví dụ, `ORD-101` là ID string không có dạng ObjectId 24 ký tự hex. Dự án thực tế phải kiểm tra kiểu BSON `_id` đã lưu, nhất là khi dùng `String` cho ID có thể chuyển thành ObjectId theo cách mapping mặc định.

`Boolean deleted` được dùng thay vì primitive `boolean` để khi đọc dữ liệu cũ, Java còn thể hiện được `null`/field bị thiếu. Tuy nhiên, **repository finder `findByDeletedFalse` chỉ khớp dữ liệu BSON thực sự bằng `false`**; việc đọc vào entity rồi thấy một giá trị mặc định Java không tự bổ sung field vào MongoDB. Nên chuẩn hóa `deleted: false` ở đường ghi và migration.

`@Version Long version` giúp các đường `save` của Spring Data có optimistic locking, nhưng **không làm mọi lệnh `@Update` hoặc raw update tự kiểm tra expectedVersion**. Khi dùng partial update, chúng ta sẽ viết filter version tường minh và tăng version cùng lệnh.

### 4.1. Vì sao không dùng save để xóa mềm?

Mã sau trông hợp lý nhưng tiềm ẩn rủi ro:

```java
// PHẢN VÍ DỤ: mô phỏng thao tác đọc - sửa - save nguyên entity.
OrderDocument original = repository.findById("ORD-101")
    .orElseThrow();

OrderDocument deleted = new OrderDocument(
    original.id(),
    original.tenantId(),
    original.orderCode(),
    original.status(),
    true,
    Instant.now(),
    "user-42",
    original.version(),
    Instant.now()
);
repository.save(deleted);
```

Với `@Version` và write concern được xác nhận, `save` có thể phát hiện stale write, nhưng nó có thể **ghi thay thế representation của entity**. Nếu BSON có field `legacyIntegration`/`externalMetadata` mà `OrderDocument` không biết, các field này **có nguy cơ biến mất** sau save. Việc xóa mềm chỉ cần thay vài field, vì vậy **partial update nguyên tử** thường phù hợp hơn.

## 5. Repository finder: luôn giới hạn deleted = false

File `OrderRepository.java`:

```java
package com.example.shop.orders;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    // Đọc theo ID phải có cả tenant và trạng thái chưa xóa.
    Optional<OrderDocument> findByIdAndTenantIdAndDeletedFalse(
        String id, String tenantId);

    Page<OrderDocument> findByTenantIdAndDeletedFalse(
        String tenantId, Pageable pageable);

    List<OrderDocument> findByTenantIdAndDeletedFalseAndStatus(
        String tenantId, String status);

    long countByTenantIdAndDeletedFalse(String tenantId);

    boolean existsByIdAndTenantIdAndDeletedFalse(
        String id, String tenantId);

    // Đường đọc quản trị, chỉ gọi sau khi kiểm tra quyền đặc biệt.
    Optional<OrderDocument> findByIdAndTenantIdAndDeletedTrue(
        String id, String tenantId);

    @Query("""
        {
          'tenantId': ?0,
          'deleted': false,
          '$or': [
            { 'status': 'NEW' },
            { 'status': 'PAID' }
          ]
        }
        """)
    List<OrderDocument> findActiveNewOrPaid(String tenantId);
}
```

Ở đây:

- `DeletedFalse` là **điều kiện suy diễn trên property Java** `deleted`; Spring Data gửi filter tương ứng tới MongoDB.
- `Pageable` hỗ trợ phân trang và sort; cần giới hạn kích thước trang ở service/API.
- `countBy...DeletedFalse` và `existsBy...DeletedFalse` phải dùng cùng hợp đồng với finder, nếu không UI có thể báo số lượng bao gồm cả bản ghi đã xóa.
- `@Query` cố ý đặt `tenantId` và `deleted: false` **ngoài nhóm `$or`** để mọi nhánh vẫn chịu giới hạn.
- `findByIdAndTenantIdAndDeletedTrue` chỉ là công cụ đọc tombstone phục vụ quản trị/phục hồi, **không được cung cấp không kiểm soát** cho client.

### 5.1. Các phương thức kế thừa KHÔNG tự ẩn bản ghi đã xóa

Vì repository vẫn `extends MongoRepository<...>`, những API kế thừa này tồn tại:

```java
repository.findById(id);
repository.findAll();
repository.existsById(id);
repository.count();
repository.deleteById(id);
repository.delete(entity);
repository.deleteAll();
```

**Không có cơ chế mặc định nào tự gắn `deleted: false` vào toàn bộ các phương thức đó chỉ vì entity có field `deleted`.** `findById`, `findAll`, `existsById` và `count` có thể nhìn thấy tombstone; `deleteById`/`deleteAll` có thể xóa vật lý.

Vì thế, cần tổ chức kiến trúc để các lớp nghiệp vụ chỉ sử dụng những phương thức **đã áp chính sách**:

- Đặt repository ở tầng persistence, không expose nguyên interface ra controller.
- Bao các thao tác trong service có phân quyền, với tên phương thức như `getVisibleOrder`/`listVisibleOrders`.
- Dùng code review/test để chặn việc gọi các phương thức không có filter.
- Nếu nhiều domain cần soft delete, cân nhắc custom base repository implementation hoặc abstraction riêng — nhưng phải thiết kế nhất quán cho cả find, count, exists, aggregation, raw template và delete; **không mặc định có global filter kiểu ORM**.

### 5.2. Một truy vấn bị thiếu điều kiện xóa vẫn là bug

```java
// PHẢN VÍ DỤ: chỉ giới hạn tenant, vẫn thấy tombstone.
Page<OrderDocument> findByTenantId(
    String tenantId, Pageable pageable);
```

Nên dùng:

```java
Page<OrderDocument> findByTenantIdAndDeletedFalse(
    String tenantId, Pageable pageable);
```

Khi viết query bằng `MongoTemplate` hoặc aggregation, cũng phải thêm filter tương tự. Filter repository không tự lan sang driver raw, aggregation pipeline hay câu truy vấn được xây ở một service khác.

## 6. Repository @Query + @Update: cập nhật thay vì xóa vật lý

Spring Data MongoDB hỗ trợ repository update methods với `@Update` trên những dòng phiên bản có API này. Đây là lựa chọn gọn khi câu filter và nội dung update **cố định**.

Thêm vào một repository riêng hoặc vào `OrderRepository`:

```java
import java.time.Instant;
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.mongodb.repository.Update;

public interface OrderStatusUpdateRepository
        extends org.springframework.data.mongodb.repository.MongoRepository<
            OrderDocument, String> {

    @Query("""
        {
          '_id': ?1,
          'tenantId': ?0,
          'deleted': false,
          'version': ?2
        }
        """)
    @Update("""
        {
          '$set': {
            'deleted': true,
            'deletedAt': ?3,
            'deletedBy': ?4,
            'updatedAt': ?3
          },
          '$inc': { 'version': 1 }
        }
        """)
    long markDeleted(
        String tenantId,
        String id,
        long expectedVersion,
        Instant deletedAt,
        String actorId
    );
}
```

**Cơ chế cần hiểu:**

1. `@Query` biểu diễn điều kiện **đúng ID + tenant + chưa xóa + version hiện hành**.
2. `@Update` tạo lệnh cập nhật `$set` các metadata và `$inc` version; không phải lệnh `delete`.
3. Kết quả `long` được sử dụng để biết có bao nhiêu document bị update theo query. Vì bộ lọc có `_id`, con số hợp lệ là **0 hoặc 1**.
4. `@Update` thao tác trực tiếp trên database, **không dựa vào lifecycle callbacks** hay tự chạy optimistic locking như `repository.save`. Vì thế expected version và tăng version phải có trong câu query/update.
5. Cú pháp hỗ trợ, binding và kiểu trả về cần được kiểm thử với **phiên bản Spring Data MongoDB thực tế** của dự án; nếu muốn kiểm soát kết quả chi tiết hoặc xây nhiều điều kiện tùy chọn, dùng repository fragment ở mục tiếp theo.

Không nên định nghĩa một repository thứ hai chỉ để chứa một method nếu không cần; trong dự án thực tế hãy **gộp phương thức** vào cùng `OrderRepository`. Đoạn interface riêng ở đây minh họa cách viết `@Query` + `@Update` mà không trộn với ví dụ fragment bên dưới.

### 6.1. Dùng kết quả cập nhật như thế nào?

```java
long changed = statusUpdateRepository.markDeleted(
    "TENANT-A",
    "ORD-101",
    3L,
    Instant.parse("2026-11-20T03:00:00Z"),
    "user-42"
);

if (changed == 0) {
    // Không tự suy ra nguyên nhân, vì filter bao gồm nhiều điều kiện.
    throw new IllegalStateException(
        "Không tìm thấy hoặc trạng thái/version đã thay đổi");
}
```

Ví dụ này giả định `statusUpdateRepository` đã được inject và `tenantId`/`actorId` đã được xác thực. Không tin các giá trị này chỉ vì chúng xuất hiện trong request. Với endpoint thực tế, 0 bản ghi khớp có thể là not found, đã xóa, stale version hoặc không thuộc quyền; tránh tiết lộ sự tồn tại của đơn hàng tenant khác.

## 7. Custom repository fragment: lệnh cập nhật có điều kiện rõ ràng

Khi cần logic kiểm tra input, kết quả chi tiết, quy tắc kiểm toán hoặc khôi phục, **repository fragment** với `MongoTemplate` là cách tổ chức dễ mở rộng.

```text
OrderRepository
  ├── MongoRepository<OrderDocument, String>
  └── OrderSoftDeleteOperations
        └── OrderSoftDeleteOperationsImpl
              └── MongoTemplate + Query + Criteria + Update
```

File `OrderSoftDeleteOperations.java`:

```java
package com.example.shop.orders;

public interface OrderSoftDeleteOperations {
    boolean softDelete(
        String permittedTenantId,
        String id,
        long expectedVersion,
        String actorId);

    boolean restore(
        String permittedTenantId,
        String id,
        long expectedVersion);
}
```

File `OrderSoftDeleteOperationsImpl.java`:

```java
package com.example.shop.orders;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class OrderSoftDeleteOperationsImpl
        implements OrderSoftDeleteOperations {

    private final MongoTemplate template;
    private final Clock clock;

    public OrderSoftDeleteOperationsImpl(
            MongoTemplate template, Clock clock) {
        this.template = template;
        this.clock = clock;
    }

    @Override
    public boolean softDelete(
            String permittedTenantId,
            String id,
            long expectedVersion,
            String actorId) {

        validate(permittedTenantId, id, expectedVersion);
        if (actorId == null || actorId.isBlank()) {
            throw new IllegalArgumentException("actorId rỗng");
        }

        Instant now = clock.instant();

        Query filter = Query.query(
            Criteria.where("id").is(id)
                .and("tenantId").is(permittedTenantId)
                .and("deleted").is(false)
                .and("version").is(expectedVersion));

        Update patch = new Update()
            .set("deleted", true)
            .set("deletedAt", now)
            .set("deletedBy", actorId)
            .set("updatedAt", now)
            .inc("version", 1L);

        return template.updateFirst(
            filter, patch, OrderDocument.class
        ).getMatchedCount() == 1;
    }

    @Override
    public boolean restore(
            String permittedTenantId,
            String id,
            long expectedVersion) {

        validate(permittedTenantId, id, expectedVersion);
        Instant now = clock.instant();

        Query filter = Query.query(
            Criteria.where("id").is(id)
                .and("tenantId").is(permittedTenantId)
                .and("deleted").is(true)
                .and("version").is(expectedVersion));

        Update patch = new Update()
            .set("deleted", false)
            .unset("deletedAt")
            .unset("deletedBy")
            .set("updatedAt", now)
            .inc("version", 1L);

        return template.updateFirst(
            filter, patch, OrderDocument.class
        ).getMatchedCount() == 1;
    }

    private static void validate(
            String tenantId, String id, long expectedVersion) {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(id, "id");

        if (tenantId.isBlank() || id.isBlank()
                || expectedVersion < 0) {
            throw new IllegalArgumentException(
                "Tenant, ID hoặc version không hợp lệ");
        }
    }
}
```

`Criteria.where("id")` sử dụng **tên property Java**, được Spring Data ánh xạ thành BSON `_id` khi đi qua `MongoTemplate` với entity mapping. `Update` chỉ đụng đến các field soft delete và version; những field như `orderCode`, `status` hay metadata legacy **không bị ghi lại**.

**Với `@Version`:** một số API update của Spring Data MongoDB có thể tự tăng version nếu update không chỉ định version. Ở đây `inc("version", 1L)` được viết **tường minh** trong `Update` để thể hiện CAS hoàn chỉnh; framework không nên thêm một phép tăng version thứ hai khi trường version đã có trong update. Cần kiểm thử giá trị version sau mỗi lệnh theo phiên bản dependency thực tế.

### 7.1. Ghép fragment vào OrderRepository

Thay chữ ký repository ban đầu bằng:

```java
package com.example.shop.orders;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String>,
                OrderSoftDeleteOperations {

    // Giữ các finder có DeletedFalse đã khai báo ở mục 5.
}
```

Spring Data có thể ghép `OrderSoftDeleteOperationsImpl` vào repository dựa trên quy ước fragment interface và hậu tố `Impl` khi package scanning/bean registration phù hợp. Nếu dự án có nhiều implementation hoặc đổi hậu tố, phải kiểm tra cấu hình thực tế. Một bean `Clock` (ví dụ `Clock.systemUTC()`) cần được cung cấp cho constructor và có thể thay bằng fixed clock trong test.

Ví dụ cấu hình `Clock`:

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClockConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

### 7.2. Có nên dùng boolean làm kết quả?

`true` nghĩa là câu update đã **match đúng một document**, còn `false` nghĩa là **không match**. Nó không phân biệt các nguyên nhân not found, đã xóa, version cũ hoặc không đúng tenant; đây là hành vi hữu ích để tránh rò rỉ thông tin. Nếu service cần trả `409 Conflict` khi stale version và `404 Not Found` khi không tìm thấy, có thể thực hiện bước đọc/kiểm tra bổ sung **sau** khi CAS thất bại, nhưng chỉ trong phạm vi tenant/ủy quyền và phải chấp nhận dữ liệu có thể tiếp tục thay đổi.

**Không tự động retry với version mới nhất** khi xóa mềm: điều đó có thể xóa một đơn hàng vừa được chuyển sang trạng thái không cho phép xóa. Nếu cần retry, phải đọc lại, áp dụng lại quy tắc nghiệp vụ và có chính sách idempotency rõ ràng.

## 8. Vì sao phải kiểm tra trạng thái và version trong cùng lệnh?

Xét quy trình không an toàn:

```text
Request A                     Request B
   |                             |
   |-- findById ORD-101 ----------|
   |  thấy deleted=false          |
   |                              |-- cập nhật trạng thái PAID
   |                              |-- tăng version 3 -> 4
   |-- update { _id: ORD-101 }     |
   |   set deleted=true           |
   v                              v
Đơn đã thay đổi nghiệp vụ vẫn bị xóa theo quyết định cũ.
```

Ngay cả khi bước đọc ban đầu có filter `deleted=false`, **bước ghi sau đó** vẫn có thể chạy dựa trên dữ liệu cũ. Sửa bằng **một lệnh cập nhật nguyên tử**:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    tenantId: "TENANT-A",
    deleted: false,
    version: NumberLong(3)
  },
  {
    $set: {
      deleted: true,
      deletedAt: ISODate("2026-11-20T03:00:00Z"),
      deletedBy: "user-42",
      updatedAt: ISODate("2026-11-20T03:00:00Z")
    },
    $inc: { version: NumberLong(1) }
  }
)
```

Phần filter và cập nhật của **một document** được MongoDB thực hiện nguyên tử theo hợp đồng update. Nếu version đã đổi, câu query không khớp; nếu document đã được xóa, `deleted=false` không khớp. Đó là lý do không dùng quy trình “`find` rồi `update` theo ID” mà bỏ điều kiện trạng thái/version trong lệnh ghi.

### 8.1. @Version với save không phải giải pháp duy nhất

Với entity có `@Version`, `repository.save(entity)` trên entity stale có thể ném `OptimisticLockingFailureException` (khi write concern cho phép xác nhận kết quả). Nhưng như đã nêu, `save` toàn entity có thể làm mất field BSON chưa map. Một lệnh `$set` có điều kiện version vừa **giữ field khác**, vừa **chống stale write**.

Nếu ứng dụng đã có cơ chế optimistic locking cho các thao tác khác, nhất quán tốt nhất là chúng **đều kiểm tra trạng thái `deleted=false`** trước khi sửa đơn còn hiệu lực. Ngược lại, một worker thanh toán chạy sau khi đơn bị xóa vẫn có thể ghi lại dữ liệu nghiệp vụ trong tombstone nếu query của nó không kiểm tra `deleted`.

### 8.2. Các trường hợp tranh chấp

| Tình huống | Điều kiện bảo vệ | Kết quả mong muốn |
| --- | --- | --- |
| A và B cùng soft delete version 3 | `version=3 AND deleted=false` | Một lệnh khớp; lệnh còn lại không khớp |
| Soft delete cùng lúc với sửa status | Cả hai kiểm tra version và `deleted=false` | Chỉ một thay đổi dựa trên version 3 thành công |
| Soft delete lặp lại sau timeout | `deleted=false` và expected version | Không ghi đè thời điểm/actor xóa lần đầu |
| Restore một tombstone version 4 | `deleted=true AND version=4` | Chuyển sang active và version 5 |
| Update order tenant khác | `tenantId` bắt buộc | Không khớp và không lộ chi tiết dữ liệu |
| Document bị xóa vật lý giữa hai bước | Update theo ID không khớp | Không tự động upsert |

### 8.3. Không tự suy đoán kết quả sau timeout

Nếu client nhận timeout sau lệnh update, có thể server đã thực hiện lệnh nhưng response chưa tới. Không nên đổi actor/timestamp rồi retry vô hạn. Có thể tra cứu trạng thái mới theo đúng tenant, đối chiếu `version`/audit event/idempotency key và trả kết quả thích hợp; nếu không thể xác định, ghi nhận trạng thái chưa rõ để điều phối.

Ví dụ, khi yêu cầu soft delete có `requestId` duy nhất, một hệ thống cần tính chính xác cao có thể lưu ID thao tác xóa hoặc audit record với khóa duy nhất. Điều đó giúp phân biệt retry của **cùng một ý định** với một yêu cầu mới sau khi trạng thái đã thay đổi.

## 9. Đọc và cập nhật phải dùng cùng định nghĩa “active”

Đây là lỗi thiết kế rất thường gặp:

```text
Repository list    -> filter deleted=false
Repository findById -> không có filter
MongoTemplate count -> không có filter
Aggregation export -> không có $match deleted=false
Soft delete update -> filter chỉ theo _id
```

Kết quả là ứng dụng có thể trả 404 khi xem danh sách nhưng vẫn tìm được bản ghi từ endpoint detail, báo cáo tổng đếm sai hoặc tiếp tục sửa một đơn đã xóa. Không có annotation `@Document` chuẩn nào tự khiến mọi API khác nhau cùng tuân theo một bộ lọc soft delete toàn cục.

### 9.1. Quy ước tối thiểu cho từng đường đọc

| Đường đọc | Truy vấn an toàn |
| --- | --- |
| Xem chi tiết | `_id = id AND tenantId = permittedTenantId AND deleted = false` |
| Danh sách có phân trang | `tenantId = permittedTenantId AND deleted = false` + filter/sort/page |
| Đếm số đơn còn hiệu lực | `tenantId = permittedTenantId AND deleted = false` |
| Kiểm tra có tồn tại không | `_id = id AND tenantId = permittedTenantId AND deleted = false` |
| Search theo trạng thái | Filter trạng thái **AND** tenant **AND** deleted false |
| Aggregation báo cáo | Stage `$match` đúng tenant/quyền và `deleted=false` |
| API quản trị tombstone | `tenantId` và `deleted=true`, cộng kiểm tra quyền quản trị |
| Export/Batch jobs | Phải quyết định rõ có loại tombstone hay không, không dựa vào mặc định |

### 9.2. MongoTemplate không kế thừa filter từ repository

```java
Query query = Query.query(
    Criteria.where("tenantId").is(permittedTenantId)
        .and("deleted").is(false)
        .and("status").is("PAID"));

List<OrderDocument> paidOrders =
    template.find(query, OrderDocument.class);
```

Nếu một service dùng `MongoTemplate` thay vì repository, nó phải tự thêm điều kiện soft delete vào `Query`/`Criteria`. Với nhiều bộ lọc động, nên viết helper có tên rõ như `activeOrdersOfTenant(...)` và kiểm thử rằng mọi nhánh AND/OR vẫn nằm trong phạm vi tenant/active.

### 9.3. OR không được thoát khỏi phạm vi

**Đúng:**

```javascript
db.orders.find({
  tenantId: "TENANT-A",
  deleted: false,
  $or: [
    { status: "NEW" },
    { status: "PAID" }
  ]
})
```

**Sai:**

```javascript
db.orders.find({
  $or: [
    { tenantId: "TENANT-A", deleted: false, status: "NEW" },
    { status: "PAID" }
  ]
})
```

Câu thứ hai nhận được mọi đơn `PAID`, kể cả document đã xóa hoặc của tenant khác. Một test chức năng chỉ chạy trên dữ liệu của một tenant có thể không phát hiện vấn đề; test phải có **bản ghi tenant khác và tombstone cùng trạng thái**.

### 9.4. Sort và phân trang

```java
PageRequest page = PageRequest.of(
    0, 20,
    Sort.by(
        Sort.Order.desc("updatedAt"),
        Sort.Order.desc("id")));

Page<OrderDocument> result =
    repository.findByTenantIdAndDeletedFalse(
        "TENANT-A", page);
```

Đoạn này nằm trong service đã có `repository` và cần import `Page`, `PageRequest`, `Sort`. Khóa `id` bổ sung thứ tự xác định khi timestamp trùng; áp giới hạn size từ API, đừng cho user gửi page size vô hạn. Số lượng trang sẽ thay đổi khi document được xóa mềm giữa các lần lấy trang; nếu muốn duyệt khối dữ liệu lớn ổn định hơn, cân nhắc scrolling/keyset với sort key không null và chính sách snapshot phù hợp.

## 10. Dữ liệu legacy bị thiếu deleted: false

Giả sử một document cũ:

```javascript
{
  _id: "ORD-LEGACY",
  tenantId: "TENANT-A",
  status: "NEW",
  version: NumberLong(2)
  // Không có deleted, deletedAt hoặc deletedBy.
}
```

Trong MongoDB:

```javascript
db.orders.find({ deleted: false })
```

**Không khớp** document này vì field `deleted` bị thiếu. Nếu ứng dụng mới thay toàn bộ finder bằng `DeletedFalse` ngay lập tức, các đơn cũ có thể **biến mất khỏi UI** dù chưa bị xóa.

### 10.1. Ưu tiên backfill sang quy ước canonical

Sau khi đã kiểm kê dữ liệu và đánh giá writer đang chạy:

```javascript
// Ví dụ migration: chỉ trên document CHƯA CÓ field deleted.
db.orders.updateMany(
  { deleted: { $exists: false } },
  { $set: { deleted: false } }
)
```

Với BSON `deleted: null`:

```javascript
// Chỉ làm nếu nghiệp vụ xác nhận null có nghĩa chưa bị xóa.
db.orders.updateMany(
  { deleted: { $type: "null" } },
  { $set: { deleted: false } }
)
```

Không tự coi mọi `null` là active nếu hệ thống cũ dùng null với ý nghĩa khác. Với hệ thống nhiều writer, cần kế hoạch rollout: writer cũ có thể tiếp tục tạo document thiếu field sau khi backfill, khiến vấn đề xuất hiện lại. Nên triển khai writer mới, thống kê kiểu BSON và chạy migration theo nhóm có thể kiểm tra lại.

### 10.2. Giai đoạn chuyển tiếp đọc hai dạng

Nếu buộc phải đọc trước khi backfill hoàn tất, có thể tạm định nghĩa “active” là:

```javascript
{
  tenantId: "TENANT-A",
  $or: [
    { deleted: false },
    { deleted: { $exists: false } }
  ]
}
```

Repository method tạm thời:

```java
@Query("""
    {
      'tenantId': ?0,
      '$or': [
        { 'deleted': false },
        { 'deleted': { '$exists': false } }
      ]
    }
    """)
List<OrderDocument> findLegacyAwareActive(String tenantId);
```

Đây là **phương án tạm thời**, không phải mặc định vĩnh viễn. Nếu cho phép xóa mềm các document thiếu field, **lệnh update cũng phải dùng cùng định nghĩa active** và giải quyết trường version tương thích. Nếu chỉ đổi finder để nhìn thấy legacy nhưng update vẫn yêu cầu `deleted:false`, người dùng sẽ thấy đơn nhưng bấm xóa không thành công.

Cách ổn định dài hạn là **backfill đầy đủ**, quy định writer luôn ghi `deleted:false`, rồi dùng một predicate đơn nhất cho cả đọc và ghi. Việc thêm `$or` cho dữ liệu legacy cũng có thể ảnh hưởng tính chọn lọc của index; cần đo.

### 10.3. Document legacy thiếu version

Thêm `@Version Long version` vào model không tự làm MongoDB có version. Document cũ thiếu `version` có thể được ánh xạ thành `null`; câu `version: NumberLong(0)` sẽ không khớp.

Nếu hệ thống chọn optimistic locking, cần backfill version và giải quyết writer đang chạy trước khi áp CAS nghiêm ngặt:

```javascript
// Ví dụ, chỉ sau khi đã kiểm chứng chính sách concurrency.
db.orders.updateMany(
  { version: { $exists: false } },
  { $set: { version: NumberLong(0) } }
)
```

Đừng tự tăng hoặc đặt lại version của document đã có version. Khi nguồn cũ lưu version dạng String, cần migration BSON type riêng; custom reading converter **không** tự làm câu update so sánh BSON NumberLong khớp String cũ.

## 11. Phục hồi: đảo trạng thái nhưng không đảo lịch sử

Phục hồi (*restore/undelete*) không phải đơn giản gọi `repository.save` với `deleted=false`. Nó phải kiểm tra:

- Document đang ở trạng thái `deleted=true`.
- Caller có quyền phục hồi trong tenant.
- Expected version còn phù hợp.
- Không vi phạm unique business key hoặc quy tắc nghiệp vụ mới.
- Lịch sử ai đã xóa, lúc nào vẫn được giữ trong audit log nếu yêu cầu.

### 11.1. Lệnh phục hồi có điều kiện

```javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    tenantId: "TENANT-A",
    deleted: true,
    version: NumberLong(4)
  },
  {
    $set: {
      deleted: false,
      updatedAt: ISODate("2026-11-20T04:00:00Z")
    },
    $unset: { deletedAt: "", deletedBy: "" },
    $inc: { version: NumberLong(1) }
  }
)
```

Phương thức `restore(...)` của fragment ở mục 7 thực hiện cùng ý tưởng. Sau restore, document lại hiện trong các finder `DeletedFalse`, nhưng nếu dữ liệu đã có trạng thái không được phép hồi phục thì service phải chặn từ trước hoặc đưa điều kiện trạng thái vào CAS.

### 11.2. Không làm mất lịch sử kiểm toán

Nếu `deletedAt` và `deletedBy` là nguồn audit **duy nhất**, `$unset` lúc restore sẽ xóa dấu vết của lần xóa. Trong hệ thống có yêu cầu truy vết, hãy ghi một sự kiện audit bất biến như:

```javascript
{
  orderId: "ORD-101",
  tenantId: "TENANT-A",
  action: "RESTORED",
  actorId: "admin-5",
  occurredAt: ISODate("2026-11-20T04:00:00Z")
}
```

Nếu audit log nằm ở collection khác và phải nhất quán với lệnh restore, cân nhắc transaction nhiều document khi hạ tầng MongoDB hỗ trợ hoặc outbox/event-driven consistency khi phù hợp. Chỉ `updateFirst` một document không đảm bảo audit event ở collection khác được ghi cùng lúc.

### 11.3. Lệnh restore cũng cần idempotency

Một lệnh restore thành công chuyển `deleted=true` sang `false` và tăng version. Lần restore thứ hai với cùng expected version sẽ không khớp; không nên tự tạo document mới. Nếu API muốn trả “đã phục hồi” cho retry, phải đối chiếu request ID hoặc trạng thái hợp lệ, không tự bỏ qua mọi failure.

## 12. Unique index và trường hợp dùng lại mã sau xóa mềm

Soft delete giữ document cũ trong collection, vì vậy một index unique thông thường trên `(tenantId, orderCode)` **vẫn xem tombstone là bản ghi đang chiếm khóa**.

Ví dụ:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderCode: 1 },
  { unique: true, name: "uq_all_orders_by_tenant_code" }
)
```

Nếu đơn `SO-2026-101` bị soft delete, ứng dụng **không thể tạo đơn mới trùng mã** trong cùng tenant nếu unique index này còn hiệu lực. Đây có thể là điều đúng khi mã đơn phải duy nhất **vĩnh viễn** để tránh nhầm lẫn thanh toán và lịch sử.

### 12.1. Unique chỉ cho bản ghi active

Nếu sản phẩm **cho phép tái sử dụng mã sau khi xóa mềm**, có thể dùng partial unique index:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderCode: 1 },
  {
    unique: true,
    name: "uq_active_tenant_order_code",
    partialFilterExpression: {
      deleted: false
    }
  }
)
```

Index này áp ràng buộc unique cho các document **khớp `deleted:false`**. Các document tombstone `deleted:true` không thuộc tập được index, nên có thể tồn tại nhiều bản ghi đã xóa cùng mã nghiệp vụ.

**Hai hệ quả phải hiểu:**

1. Document legacy **thiếu `deleted`** cũng có thể **không tham gia partial index**. Nếu chưa backfill, thao tác thêm mới có thể không bị unique index chặn theo hợp đồng bạn tưởng. Hãy hoàn tất migration trước khi dựa vào index này.
2. Khi phục hồi một tombstone, nếu một document active khác đã chiếm cùng mã, update `deleted:true -> false` có thể **thất bại duplicate key**. Repository fragment phải xử lý lỗi và báo conflict phù hợp, không tự ép phục hồi.

Đừng tạo cả unique index toàn phần và unique index partial rồi mong partial index cho phép dùng lại mã: unique index toàn phần vẫn chặn. Phải chọn chính sách khóa nghiệp vụ trước khi triển khai index.

### 12.2. Index phục vụ truy vấn đọc active

Với màn hình theo tenant, status và thời điểm:

```javascript
db.orders.createIndex({
  tenantId: 1,
  deleted: 1,
  status: 1,
  updatedAt: -1,
  _id: -1
})
```

Đây là **index ứng viên** để đo, không phải cấu hình tối ưu mặc định. Nếu màn hình thường chỉ lọc `tenantId + deleted` và sort `updatedAt` mà không lọc `status`, index khác có thể phù hợp hơn. Sự xuất hiện của `status` giữa các key có thể ảnh hưởng khả năng dùng index cho sort khi không có điều kiện trạng thái.

Đo truy vấn thật bằng:

```javascript
db.orders
  .find({
    tenantId: "TENANT-A",
    deleted: false,
    status: "PAID"
  })
  .sort({ updatedAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Theo dõi `nReturned`, `totalKeysExamined`, `totalDocsExamined`, sort stage và thời gian thực thi. Index trên cờ boolean có độ chọn lọc thấp nếu gần như mọi document đều active; lợi ích phụ thuộc cách ghép với tenant và những field khác.

### 12.3. Index không thay thế quyền truy cập

Partial index hoặc compound index chỉ giúp ràng buộc/hiệu năng; nó **không tự lọc quyền** cho mọi query. Một `repository.findAll()` vẫn có thể trả tombstone và tenant khác dù collection có index trên `tenantId, deleted`.

## 13. Dọn dữ liệu sau thời gian lưu giữ

Soft delete không phải là cách xóa dữ liệu vĩnh viễn. Nếu phải tuân thủ retention hoặc yêu cầu xóa dữ liệu cá nhân, cần một **quy trình purge** riêng, có quyền và được kiểm toán.

### 13.1. Purge theo điều kiện chặt

Ví dụ chỉ xóa vật lý đơn đã soft delete hơn thời hạn:

```javascript
// Chỉ chạy sau khi được phê duyệt chính sách retention.
db.orders.deleteMany({
  tenantId: "TENANT-A",
  deleted: true,
  deletedAt: {
    $lt: ISODate("2026-01-01T00:00:00Z")
  }
})
```

Lệnh này là **hard delete** và không thể undo bằng lệnh restore thông thường. Trước khi chạy thật cần kiểm tra ràng buộc lưu trữ pháp lý, backup, tham chiếu từ collection khác, log kết quả và số lượng dự kiến.

### 13.2. TTL index khi thật sự phù hợp

Một lựa chọn cho dữ liệu có thể tự hết hạn là TTL index trên `deletedAt`:

```javascript
// Ví dụ giữ 30 ngày sau thời điểm xóa mềm.
db.orders.createIndex(
  { deletedAt: 1 },
  { expireAfterSeconds: 2592000 }
)
```

TTL hoạt động nền, **không bảo đảm xóa đúng ngay thời điểm hết hạn**. TTL trên `deletedAt` không xét chính sách nghiệp vụ nếu document active vẫn còn field này: vì vậy khi restore phải **unset `deletedAt`** nếu giữ thiết kế TTL. Không dùng TTL khi có legal hold hoặc retention phức tạp cần điều kiện từ nhiều collection. Nếu cần quyền/kiểm toán trước khi purge, một job có điều kiện tường minh thường phù hợp hơn TTL tự động.

### 13.3. Liên kết và tham chiếu giữa documents

Nếu `Order` có các `Payment`, `Shipment`, `AuditEvent` tham chiếu bằng ID:

- Soft delete order **không tự xóa** các document liên quan.
- Query thanh toán/giao hàng phải quyết định có trả order đã xóa hay không.
- Không nên dựa vào cascade tự động như nhiều ORM quan hệ; Spring Data MongoDB không mặc nhiên cascade toàn bộ quan hệ cho soft delete.
- Nếu phải khóa hủy đồng thời nhiều entities, cân nhắc transaction/outbox hoặc một state machine nghiệp vụ thay vì chỉ cập nhật `deleted` của order.

## 14. Lỗi thiết kế thường gặp: lối tắt không an toàn

### 14.1. Định nghĩa phương thức delete nhưng mong soft delete

```java
// PHẢN VÍ DỤ: derived delete là thao tác xóa, không phải soft delete.
long deleteByTenantIdAndStatus(
    String tenantId, String status);
```

Tên `deleteBy...` **không có nghĩa** “`$set deleted=true`”. Nếu yêu cầu là soft delete, sử dụng phương thức update rõ tên như `markDeleted`/`softDelete` và đảm bảo mọi lệnh gọi hard delete được kiểm soát.

### 14.2. Chỉ sửa findAll nhưng quên count, exists và export

```text
findActive(...)           -> đúng
countByTenantId(...)      -> còn đếm tombstone
existsById(...)           -> còn nhận tombstone
aggregation revenue       -> còn tính đơn đã xóa
report CSV                -> còn xuất thông tin đã xóa
```

Một chính sách soft delete phải có **ma trận mọi đường đọc**. Cần kiểm thử ít nhất finder chi tiết, danh sách, count, exists, search, sort/page, aggregation và đường đọc quản trị. Không có “automatic global soft delete filter” cho MongoTemplate chỉ vì repo đã có method `DeletedFalse`.

### 14.3. Lệnh update theo _id mà không kiểm tra deleted/version

```java
// PHẢN VÍ DỤ: có thể sửa cả tombstone hoặc ghi đè stale state.
template.updateFirst(
    Query.query(Criteria.where("id").is(id)),
    new Update().set("status", "PAID"),
    OrderDocument.class);
```

Nên thêm tenant được phép, `deleted=false` và expected version. Với update đã áp dụng version tường minh trong lệnh, hãy kiểm tra `matchedCount` thay vì tin thành công chỉ vì không có exception.

### 14.4. Dùng repository.save với entity chưa tải đủ field

Một projection chỉ có vài field hoặc entity Java không chứa metadata do service khác ghi **không** phải replacement đầy đủ an toàn. Soft delete bằng `$set` đúng field cần sửa giúp tránh làm mất dữ liệu ngoài phạm vi, dù vẫn phải có CAS để bảo vệ các writer đồng thời.

### 14.5. Đánh đồng “false” với field thiếu

Nếu finder dùng `DeletedFalse` nhưng writer legacy còn tạo document thiếu `deleted`, dữ liệu vẫn bị bỏ qua. Dùng một mô hình canonical và migration; đừng để một API coi missing là active còn API khác coi missing là không tồn tại.

### 14.6. Thao tác xóa mềm không phân biệt quyền

Soft delete **vẫn là hành động thay đổi dữ liệu**, không phải chỉ thay một cờ UI. Service phải xác minh actor, tenant, quyền xóa và ràng buộc nghiệp vụ (ví dụ không xóa đơn đã xuất hóa đơn) trước khi gọi repository. Nếu quyền phụ thuộc trạng thái hiện hành, hãy đưa trạng thái hoặc version vào **chính điều kiện update** để tránh race giữa bước kiểm tra và bước ghi.

## 15. Kiểm thử tích hợp: không ẩn nhầm và không ghi sai

Mock repository có thể trả đúng danh sách do ta lập trình nhưng **không chứng minh** rằng Spring Data tạo đúng filter `deleted:false`, fragment được ghép thành công, `@Update` giữ field ngoài model hoặc MongoDB xử lý version atomically. Cần integration test trên MongoDB riêng, seed BSON thật bằng driver.

Ví dụ dùng JUnit 5/AssertJ và Spring Boot `@DataMongoTest`. Tên package của annotation có thể thay đổi khi nâng major version Spring Boot; dưới đây là biến thể import phổ biến ở dòng Spring Boot 3.x. Cần cấu hình MongoDB test instance phù hợp, chẳng hạn Testcontainers, trước khi chạy.

### 15.1. Fixture có active, tombstone, tenant khác và legacy missing field

File `OrderSoftDeleteIntegrationTest.java`:

```java
package com.example.shop.orders;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class OrderSoftDeleteIntegrationTest {

    private static final Instant NOW =
        Instant.parse("2026-11-20T03:00:00Z");

    @TestConfiguration
    static class TestClockConfig {
        @Bean
        Clock clock() {
            return Clock.fixed(NOW, ZoneOffset.UTC);
        }
    }

    @Autowired MongoTemplate template;
    @Autowired OrderRepository repository;

    private static Document order(
            String id, String tenant, String status,
            Boolean deleted, long version) {

        Document d = new Document("_id", id)
            .append("tenantId", tenant)
            .append("orderCode", "CODE-" + id)
            .append("status", status)
            .append("version", version)
            .append("updatedAt", Date.from(
                Instant.parse("2026-11-19T08:00:00Z")))
            // Dữ liệu có thật ở BSON nhưng không có trong Java entity.
            .append("legacyIntegration",
                new Document("source", "erp-v1")
                    .append("syncToken", "sync-7788"));

        if (deleted != null) {
            d.append("deleted", deleted);
        }
        if (Boolean.TRUE.equals(deleted)) {
            d.append("deletedAt", Date.from(
                Instant.parse("2026-11-19T12:00:00Z")));
            d.append("deletedBy", "admin-old");
        }
        return d;
    }

    private Document raw(String id) {
        return template.getCollection("orders")
            .find(new Document("_id", id))
            .first();
    }

    @BeforeEach
    void seed() {
        // CHỈ được xóa toàn collection trong database TEST cô lập.
        var collection = template.getCollection("orders");
        collection.deleteMany(new Document());

        collection.insertMany(List.of(
            order("ORD-101", "TENANT-A", "PAID", false, 3L),
            order("ORD-102", "TENANT-A", "NEW", false, 1L),
            order("ORD-201", "TENANT-A", "PAID", true, 7L),
            order("ORD-OLD", "TENANT-A", "NEW", null, 2L),
            order("ORD-B01", "TENANT-B", "PAID", false, 3L)
        ));
    }

    @Test
    void normalReadsHideDeletedAndUnnormalizedLegacyDocuments() {
        assertThat(repository
            .findByIdAndTenantIdAndDeletedFalse(
                "ORD-101", "TENANT-A")).isPresent();

        assertThat(repository
            .findByIdAndTenantIdAndDeletedFalse(
                "ORD-201", "TENANT-A")).isEmpty();

        // Hàm CRUD kế thừa KHÔNG có filter soft delete.
        assertThat(repository.findById("ORD-201")).isPresent();

        // Legacy thiếu deleted không khớp DeletedFalse.
        assertThat(repository
            .findByIdAndTenantIdAndDeletedFalse(
                "ORD-OLD", "TENANT-A")).isEmpty();

        assertThat(repository.countByTenantIdAndDeletedFalse(
            "TENANT-A")).isEqualTo(2L);

        assertThat(repository
            .existsByIdAndTenantIdAndDeletedFalse(
                "ORD-201", "TENANT-A")).isFalse();

        var ids = repository.findActiveNewOrPaid("TENANT-A")
            .stream().map(OrderDocument::id).toList();
        assertThat(ids).containsExactlyInAnyOrder(
            "ORD-101", "ORD-102");
        assertThat(ids).doesNotContain("ORD-B01", "ORD-201");
    }

    @Test
    void softDeleteUsesCasAndPreservesUnmappedBsonFields() {
        boolean changed = repository.softDelete(
            "TENANT-A", "ORD-101", 3L, "user-42");
        assertThat(changed).isTrue();

        Document stored = raw("ORD-101");
        assertThat(stored).isNotNull();
        assertThat(stored.getString("_id")).isEqualTo("ORD-101");
        assertThat(stored.getBoolean("deleted")).isTrue();
        assertThat(stored.getDate("deletedAt").toInstant())
            .isEqualTo(NOW);
        assertThat(stored.getString("deletedBy"))
            .isEqualTo("user-42");
        assertThat(stored.get("version", Number.class)
            .longValue()).isEqualTo(4L);

        // $set cập nhật có chọn lọc: metadata legacy vẫn được giữ.
        Document legacy = stored.get(
            "legacyIntegration", Document.class);
        assertThat(legacy.getString("source"))
            .isEqualTo("erp-v1");
        assertThat(legacy.getString("syncToken"))
            .isEqualTo("sync-7788");

        assertThat(repository
            .findByIdAndTenantIdAndDeletedFalse(
                "ORD-101", "TENANT-A")).isEmpty();

        // Retry với version cũ hoặc đã deleted -> không cập nhật lần hai.
        assertThat(repository.softDelete(
            "TENANT-A", "ORD-101", 3L, "user-42")).isFalse();
        assertThat(raw("ORD-101").get("version", Number.class)
            .longValue()).isEqualTo(4L);
    }

    @Test
    void staleVersionOrWrongTenantCannotDelete() {
        assertThat(repository.softDelete(
            "TENANT-A", "ORD-101", 2L, "user-42")).isFalse();

        assertThat(repository.softDelete(
            "TENANT-B", "ORD-101", 3L, "user-42")).isFalse();

        Document stored = raw("ORD-101");
        assertThat(stored.getBoolean("deleted")).isFalse();
        assertThat(stored.get("version", Number.class)
            .longValue()).isEqualTo(3L);
    }

    @Test
    void restoreIsCasAndClearsTombstoneFields() {
        assertThat(repository.restore(
            "TENANT-A", "ORD-201", 7L)).isTrue();

        Document stored = raw("ORD-201");
        assertThat(stored.getBoolean("deleted")).isFalse();
        assertThat(stored.containsKey("deletedAt")).isFalse();
        assertThat(stored.containsKey("deletedBy")).isFalse();
        assertThat(stored.get("version", Number.class)
            .longValue()).isEqualTo(8L);

        assertThat(repository
            .findByIdAndTenantIdAndDeletedFalse(
                "ORD-201", "TENANT-A")).isPresent();

        assertThat(repository.restore(
            "TENANT-A", "ORD-201", 7L)).isFalse();
    }

    @Test
    void otherBusinessUpdatesMustExcludeTombstones() {
        Query safeCondition = Query.query(
            Criteria.where("id").is("ORD-201")
                .and("tenantId").is("TENANT-A")
                .and("deleted").is(false)
                .and("version").is(7L));

        var result = template.updateFirst(
            safeCondition,
            new Update().set("status", "PAID_AGAIN")
                .inc("version", 1L),
            OrderDocument.class);

        assertThat(result.getMatchedCount()).isZero();
        assertThat(raw("ORD-201").getString("status"))
            .isEqualTo("PAID");
    }
}
```

**Điều kiện chạy:** test này cần MongoDB thực hoặc Testcontainers được cấu hình làm **database test cô lập**. Lệnh `deleteMany(new Document())` trong `@BeforeEach` sẽ xóa mọi bản ghi của collection `orders` trên database đang kết nối. Tuyệt đối không trỏ test vào database dùng chung hoặc production. Khi nâng cấp Spring Boot, cần kiểm tra import của `@DataMongoTest` và `@TestConfiguration` với đúng dependency được chọn.

Fixture được chèn bằng `getCollection(...).insertMany(...)` thay vì `repository.save(...)` vì cần **BSON thật với field `legacyIntegration` không có trong entity**, cùng một document legacy thiếu `deleted`. Sau update, dùng raw driver đọc lại để xác minh field không bị mất.

### 15.2. Kiểm tra annotation @Query + @Update riêng

Nếu dự án chọn cách dùng `OrderStatusUpdateRepository` ở mục 6 thay vì fragment, hãy bổ sung test:

```java
// statusUpdateRepository là bean được inject theo interface ở mục 6.
long changed = statusUpdateRepository.markDeleted(
    "TENANT-A", "ORD-102", 1L,
    Instant.parse("2026-11-20T03:00:00Z"),
    "user-42");

assertThat(changed).isEqualTo(1L);

Document stored = template.getCollection("orders")
    .find(new Document("_id", "ORD-102"))
    .first();

assertThat(stored).isNotNull();
assertThat(stored.getBoolean("deleted")).isTrue();
assertThat(stored.get("version", Number.class)
    .longValue()).isEqualTo(2L);
```

Đây là **đoạn bổ sung trong test** sau khi inject đúng repository và seed ở `@BeforeEach`; không phải một class test độc lập. Phải có thêm case cùng ID nhưng expectedVersion sai để chứng minh update annotation không ghi đè stale document.

### 15.3. Đừng kiểm tra chỉ bằng số document

Một test đơn giản như `assert count = 4` có thể xanh dù một tombstone bị đưa vào kết quả và một active document bị lọc nhầm. Với soft delete, nên kiểm tra:

- **ID cụ thể** nào xuất hiện/không xuất hiện ở finder và search.
- Điều kiện tenant ở mọi nhánh của `OR`.
- `deleted`, `deletedAt`, `deletedBy` và `version` trong BSON thô.
- Field legacy/unknown vẫn tồn tại sau partial update.
- Retry và stale version không ghi đè timestamp/actor xóa trước.
- Count/exists/page/aggregation tuân thủ cùng chính sách active.
- Restore không làm mất dữ liệu và không bỏ qua unique key.

### 15.4. Ma trận kiểm thử bắt buộc

| Kịch bản | Kỳ vọng |
| --- | --- |
| Active document đúng tenant | Finder trả về |
| Tombstone đúng tenant | Finder thường ẩn, finder quản trị có thể đọc |
| Document tenant khác | Không được trả hoặc sửa bởi request của tenant hiện tại |
| Legacy thiếu `deleted` | Không khớp `DeletedFalse` trước migration; xử lý theo kế hoạch |
| `deleted: null` | Không tự coi là false |
| Xóa mềm lần đầu | `deleted=true`, timestamp/actor đúng, version tăng một lần |
| Xóa lặp với expectedVersion cũ | Không đổi document lần hai |
| Xóa khi version đã bị writer khác tăng | Không khớp; không ghi đè |
| Xóa khi đơn đã bị xóa | Không khớp; không ghi đè deletedAt/deletedBy |
| Một update nghiệp vụ chạy trên tombstone | Không khớp nếu đã áp deleted=false |
| Restore đúng version | `deleted=false`, metadata xóa được xử lý đúng, version tăng |
| Restore khi mã nghiệp vụ trùng active | Xung đột unique nếu dùng partial unique index |
| Soft delete trên document có unknown fields | Unknown fields vẫn giữ nguyên |
| `repository.findById` mặc định | Vẫn có thể nhìn thấy tombstone; cảnh báo kiến trúc |
| Query pagination/count/aggregation | Đều chỉ xử lý active trong luồng nghiệp vụ |
| Tác vụ purge/TTL | Chỉ thực hiện theo chính sách retention và quyền được duyệt |

## 16. Reactive repository và ReactiveMongoTemplate

Ngữ nghĩa soft delete **không thay đổi** khi ứng dụng chuyển sang reactive. `ReactiveMongoRepository` vẫn có các phương thức kế thừa như `findById` và `deleteById`; chúng không tự áp filter `deleted:false`. Finder phải chỉ rõ điều kiện active.

Ví dụ:

```java
package com.example.shop.orders;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    Mono<OrderDocument> findByIdAndTenantIdAndDeletedFalse(
        String id, String tenantId);

    Flux<OrderDocument> findByTenantIdAndDeletedFalse(
        String tenantId);
}
```

Với cập nhật có điều kiện, dùng `ReactiveMongoTemplate` và kiểm tra `UpdateResult` trong publisher:

```java
import java.time.Instant;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public Mono<Boolean> softDeleteReactive(
        ReactiveMongoTemplate template,
        String permittedTenantId,
        String id,
        long expectedVersion,
        String actorId,
        Instant now) {

    // Caller cần xác minh quyền và validate input trước khi gọi.
    Query filter = Query.query(
        Criteria.where("id").is(id)
            .and("tenantId").is(permittedTenantId)
            .and("deleted").is(false)
            .and("version").is(expectedVersion));

    Update patch = new Update()
        .set("deleted", true)
        .set("deletedAt", now)
        .set("deletedBy", actorId)
        .set("updatedAt", now)
        .inc("version", 1L);

    return template.updateFirst(
            filter, patch, OrderDocument.class)
        .map(result -> result.getMatchedCount() == 1);
}
```

Đây là phương thức minh họa đặt trong class Java phù hợp. Caller cần xác minh tenant/actor và `expectedVersion`; ứng dụng thật nên tạo `now` bằng Clock được inject. Một `Mono` chưa được subscribe sẽ không thực hiện update. Kiểm thử reactive nên sử dụng `StepVerifier`, xác nhận cả lần thành công, zero match, stale version và document của tenant khác.

Không gọi `MongoTemplate` blocking bên trong reactive pipeline rồi coi đó là non-blocking. Cũng không nên dùng `repository.save` reactive trên một entity chỉ có vài field để thay thế cách cập nhật chọn lọc khi cần bảo vệ dữ liệu ngoài model.

## 17. Transaction, auditing và event-driven consistency

### 17.1. Đổi cờ trên một document không cần transaction nhiều document

Lệnh `$set + $inc` có filter `_id/tenant/deleted/version` làm thay đổi **một document** atomically. Chỉ để set cờ xóa, transaction nhiều document thường là quá mức cần thiết.

Tuy nhiên, nếu xóa mềm một order phải:

- Đồng thời chặn shipment hoặc giữ chỗ tồn kho ở collection khác.
- Ghi audit event bắt buộc ở collection riêng.
- Cập nhật số liệu tồn nợ theo một bất biến nhất quán tức thì.

thì cần xác định liệu có phải dùng **multi-document transaction** với MongoDB deployment hỗ trợ, hay mô hình outbox/saga eventual consistency có khả năng xử lý lỗi. Soft delete không tự động cascade tới toàn bộ tham chiếu khác.

### 17.2. Auditing cập nhật một phần

Các annotation như `@LastModifiedDate` có thể được xử lý bởi entity callbacks/auditing khi `save`; nhưng các lệnh `@Update`, `MongoTemplate.updateFirst(...)` không nên bị giả định chạy cùng toàn bộ chu trình callback của việc lưu entity. Vì vậy bài đã **set `updatedAt` tường minh** trong `Update`.

`deletedBy` phải đến từ danh tính/authorization của server; không lấy user ID bất kỳ từ request mà không đối chiếu quyền. Nếu cần lưu thêm lý do xóa, mã thao tác hoặc correlation ID, định nghĩa metadata/validation rõ ràng và bảo vệ thông tin nhạy cảm trong log.

### 17.3. Trạng thái đã xóa không phải trạng thái nghiệp vụ thay thế

`status = PAID` và `deleted = true` có thể cùng tồn tại. Soft delete là một **trục trạng thái quản trị vòng đời document**, không nhất thiết đổi `status` sang `DELETED`. Nếu hệ thống chọn một enum trạng thái duy nhất thay cho cờ, phải viết lại quy tắc đọc, update, index và state machine cho nhất quán.

Việc giữ `status` giúp khôi phục trạng thái nghiệp vụ trước đó, nhưng cũng có nghĩa các báo cáo về `status=PAID` phải **bổ sung `deleted=false`** khi ý định là tính đơn còn hiệu lực.

## 18. Quy trình triển khai trên hệ thống đang hoạt động

### 18.1. Chuẩn bị và thống kê

Trước khi bật soft delete, thống kê:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$deleted" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
```

Đếm các kiểu `bool`, `null`, `missing`, String hoặc kiểu khác để nhận diện dữ liệu legacy. Thống kê thêm sự có mặt/kiểu của `version` và các field dùng để index. Không giả định collection cũ đã tuân thủ model Java mới.

### 18.2. Triển khai theo thứ tự tránh mất hiển thị

Quy trình tham khảo:

1. **Chốt hợp đồng:** `deleted:false` là active, `deleted:true` là tombstone, vai trò của deletedAt/deletedBy, restore và retention.
2. **Chuẩn hóa writer:** bảo đảm bản ghi mới luôn có `deleted:false` và version đúng định dạng BSON.
3. **Bổ sung compatibility tạm thời nếu cần:** reader có thể nhìn được legacy missing field trong giai đoạn chuyển tiếp, nhưng phải định nghĩa lệnh update tương ứng.
4. **Backfill có checkpoint:** chuyển document thiếu/null đã được xác nhận thành `deleted:false`, chuẩn hóa version, đối soát theo tenant.
5. **Cập nhật toàn bộ đường đọc:** finder chi tiết, danh sách, count, exists, @Query, MongoTemplate, aggregation, export và job nội bộ.
6. **Bật soft delete atomically:** sử dụng expectedVersion, deleted=false, tenant trong update filter; kiểm tra kết quả.
7. **Triển khai index:** index cho đọc active và unique key theo chính sách dùng lại mã; kiểm tra dữ liệu trùng trước khi tạo.
8. **Kiểm thử restore và conflict:** đặc biệt trường hợp unique partial index đã cho phép một mã mới thay mã cũ.
9. **Theo dõi sau triển khai:** số tombstone, CAS failure, no-match update, duplicate key, tỷ lệ missing deleted, chi phí query.
10. **Gỡ compatibility legacy** chỉ sau khi xác nhận không còn document cũ thuộc phạm vi hỗ trợ và các writer cũ không còn tạo dữ liệu thiếu field.

### 18.3. Triển khai đa phiên bản phải tính cả hai chiều

Ứng dụng mới biết soft delete **không có nghĩa** ứng dụng cũ sẽ tự ẩn tombstone. Nếu rolling deployment vẫn có instance phiên bản cũ gọi `findAll`, instance đó có thể tiếp tục hiển thị bản ghi đã bị xóa mềm bởi instance mới.

Khi thay đổi hợp đồng dữ liệu có ý nghĩa bảo mật/tuân thủ, phải điều phối thời điểm **bật hành vi ghi `deleted=true`** với thời điểm mọi reader bắt buộc đã biết lọc. Có thể cần feature flag, triển khai reader trước writer, bảo vệ endpoint ở gateway/service hoặc cắt dần phiên bản cũ.

## 19. Checklist rà soát và lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Bản ghi đã xóa vẫn thấy ở endpoint detail | Dùng `findById` kế thừa, không có `DeletedFalse` | Dùng finder có tenant + deleted=false |
| UI báo tổng số đơn lớn hơn danh sách | `count` không lọc deleted | Dùng `countByTenantIdAndDeletedFalse` |
| Báo cáo doanh thu tính cả tombstone | Aggregation thiếu `$match deleted:false` | Thêm điều kiện ở pipeline |
| Bản ghi legacy “biến mất” sau nâng cấp | BSON thiếu `deleted`, finder chỉ khớp false | Backfill hoặc compatibility reader có kế hoạch |
| Xóa mềm không thành công với bản ghi legacy | Update filter yêu cầu `deleted:false` nhưng field thiếu | Chuẩn hóa schema hoặc đồng bộ predicate đọc/ghi tạm thời |
| Hai request cùng xóa làm thay đổi deletedAt hai lần | Update không kiểm tra active/version | CAS trong cùng một lệnh; retry có idempotency |
| Xóa đơn tenant khác | Filter chỉ theo ID hoặc quyền chưa xác minh | Tenant/authorization bắt buộc |
| Xóa xong vẫn sửa status được | Business update không lọc deleted=false | Cập nhật tất cả đường ghi |
| Soft delete bằng save làm mất metadata ngoài Java model | Full document replacement | Dùng `$set` chọn lọc với CAS |
| `@Version` có nhưng `@Update` không ngăn stale | Chưa thêm expectedVersion vào query | Viết điều kiện và `$inc` version tường minh |
| Restore báo duplicate key | Partial unique index cho phép dùng lại mã active | Kiểm tra xung đột mã trước khi restore, xử lý conflict |
| Đã restore nhưng bản ghi bị TTL xóa | `deletedAt` vẫn còn và TTL chưa được xử lý | Unset deletedAt hoặc thay đổi chiến lược retention |
| Xóa mềm nhưng dữ liệu cá nhân vẫn nằm trong DB | Soft delete không phải hard delete | Quy trình purge/retention phù hợp |
| Search theo OR rò rỉ tombstone hoặc tenant khác | Điều kiện bảo vệ nằm sai nhánh OR | Tenant/deleted ở nhóm AND ngoài cùng |
| Test mock xanh nhưng BSON thực sai | Không test mapping/filter/update thật | Integration test raw BSON và xác minh kết quả |

## 20. Bài tập vận dụng

Một hệ thống quản lý thiết bị lưu collection `devices`:

```javascript
{
  _id: "DEV-001",
  tenantId: "TENANT-X",
  serial: "SN-001",
  state: "ONLINE",
  deleted: false,
  version: NumberLong(8),
  updatedAt: ISODate("2026-11-19T10:00:00Z"),
  vendorMetadata: {
    firmware: "2.4",
    lastSyncBatch: "B-992"
  }
}
```

Một endpoint được phép “gỡ thiết bị” bằng soft delete, có thể phục hồi nếu thiết bị chưa bị thay thế bằng serial mới.

Hãy thực hiện các yêu cầu:

1. Viết `DeviceRepository` với finder theo `id + tenant + deleted=false`, list có phân trang, `count`/`exists` nhất quán.
2. Viết lệnh soft delete dựa trên `_id = DEV-001`, `tenantId = TENANT-X`, `deleted=false`, `version=8`; dùng `$set` cho cờ, actor, timestamp và `$inc` version.
3. Chứng minh vì sao `repository.deleteById(...)` không phải soft delete và vì sao `save` toàn entity có thể làm mất `vendorMetadata`.
4. Thêm một document tenant Y có cùng state ONLINE và một tombstone tenant X; kiểm thử cả finder lẫn aggregate count không rò rỉ.
5. Mô phỏng hai request cùng expectedVersion 8, xác minh chỉ một request có matched count 1.
6. Cho phép dùng lại serial khi thiết bị bị xóa mềm: đề xuất partial unique index `(tenantId, serial)`; mô tả điều gì xảy ra khi restore device cũ mà serial đã được dùng lại.
7. Đối với device legacy thiếu `deleted` và `version`, lập kế hoạch migration trước khi bật finder và CAS mới.
8. Kiểm thử dữ liệu raw BSON để xác nhận `vendorMetadata` không bị xóa khi soft delete và được giữ qua restore.
9. Đề xuất thời hạn retention và chỉ ra vì sao TTL có thể không phù hợp nếu có yêu cầu legal hold.

**Gợi ý giải:** dùng finder `DeletedFalse` chỉ sau khi canonical hóa schema, đặt tenant + deleted + version trong cùng điều kiện cập nhật và sửa các field lifecycle bằng `Update` có chọn lọc. Partial unique index có thể cho phép tạo device mới cùng serial nhưng làm phát sinh conflict khi phục hồi; quyết định cần được chốt trong hợp đồng nghiệp vụ, không tự giải quyết bằng việc xóa record cũ.

## 21. Tài liệu tham khảo

- Spring Data MongoDB — [MongoDB Repositories: Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): derived finders, `@Query` và method naming.
- Spring Data MongoDB — [MongoDB Repositories: Modifying Queries](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/modifying-methods.html): `@Update` và các lưu ý về update trực tiếp.
- Spring Data MongoDB — [Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `MongoTemplate.updateFirst`, `@Version`, `findAndModify`, remove và write result.
- Spring Data Commons — [Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html): cách ghép repository fragment.
- MongoDB Manual — [Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/): `$set`, `$unset`, `$inc` và cập nhật document.
- MongoDB Manual — [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/): partial unique index và điều kiện tham gia index.
- MongoDB Manual — [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/): tự động hết hạn dữ liệu theo field Date.
- MongoDB Manual — [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): atomic update một document và transaction nhiều document.

## Ghi nhớ

**Xóa mềm đúng** là một **hợp đồng xuyên suốt đường đọc và đường ghi**, không phải chỉ thêm cờ `deleted`. Với các truy vấn nghiệp vụ, luôn áp **`tenantId AND deleted=false`** — cả chi tiết, danh sách, count, exists, aggregation và export. Khi xóa, thực hiện **một update nguyên tử** theo `_id`, tenant, `deleted=false` và expected version; dùng `$set` cho metadata, `$inc` cho version và kiểm tra matched count. Không dùng các phương thức `delete` vật lý hay `save` full replacement như một cách xóa mềm mặc định. Chuẩn hóa dữ liệu legacy, kiểm soát unique index/restore, giữ audit và kiểm thử trên BSON thật để chính sách hoạt động nhất quán trong toàn bộ ứng dụng.
