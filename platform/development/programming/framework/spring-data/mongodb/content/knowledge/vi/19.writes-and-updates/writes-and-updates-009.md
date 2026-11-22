# Giữ _id, version và dữ liệu không có trong mô hình Java

> **Chương:** Ghi và cập nhật  
> **Module:** `SPRING_DATA_MONGODB`

Trong Spring Data MongoDB, một thao tác `save` trông rất đơn giản: đọc entity, đổi trạng thái, lưu lại. Nhưng nếu document MongoDB có thêm field **không được khai báo trong lớp Java** — chẳng hạn metadata của hệ thống cũ, thông tin do dịch vụ khác bổ sung hoặc field của một phiên bản schema mới hơn — thì thao tác ghi lại toàn bộ entity có thể làm **mất dữ liệu mà Java chưa từng đọc vào model**. Cùng lúc đó, việc xử lý `_id` và trường `@Version` không đúng có thể dẫn tới ghi nhầm document, tạo bản ghi mới hoặc mất cập nhật đồng thời.

Bài này phân biệt rõ **thay thế document** với **cập nhật một phần**, giải thích vai trò của `_id` và optimistic locking với `@Version`, rồi xây cách cập nhật có chọn lọc để giữ những field không có trong model Java. Đây là kiến thức nền của module `SPRING_DATA_MONGODB`: kết nối và ánh xạ document, thao tác qua `MongoTemplate` hoặc repository, thiết kế query, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `insert`, `save`, `replace`, `updateFirst`, `findAndModify` và `upsert` theo ảnh hưởng tới các field trong BSON.
2. Giải thích vì sao `_id` **bất biến** trên một document và cách `@Id`/`@MongoId` ảnh hưởng đến mapping ID.
3. Sử dụng `@Version` để phát hiện cập nhật dựa trên phiên bản cũ, xử lý `OptimisticLockingFailureException` và kiểm tra write concern.
4. Giữ nguyên các field legacy/không có trong Java model bằng `$set`/`$unset` có chủ đích, đồng thời quản lý version bằng điều kiện so khớp.
5. Tránh các lỗi khi dùng partial update, raw driver, callback/auditing, transaction và migration dữ liệu chưa có version.
6. Viết kiểm thử tích hợp chứng minh các bất biến `_id`, `version` và các field không được model Java khai báo.

## 2. Vấn đề thực tế: document BSON rộng hơn Java entity

Giả sử database có document đơn hàng do một ứng dụng cũ tạo:

```javascript
{
  _id: "ORD-100",
  tenantId: "TENANT-A",
  status: "NEW",
  amountMinor: NumberLong(150000),
  version: NumberLong(3),
  legacy_note: "Đã đối soát với hệ thống cũ",
  externalPayload: {
    source: "warehouse-v1",
    trackingKey: "WH-7788"
  },
  updatedAt: ISODate("2026-11-18T08:00:00Z")
}
```

Phiên bản Java hiện tại chỉ biết các field `id`, `tenantId`, `status`, `amountMinor`, `version` và `updatedAt`. Nó **không khai báo** `legacy_note` hay `externalPayload`. Khi đọc BSON vào entity, `MappingMongoConverter` thường bỏ qua những field không được model ánh xạ.

Điều này **không có nghĩa** field lạ đã bị xóa ngay khi đọc. MongoDB vẫn giữ đầy đủ document. Rủi ro xảy ra khi ứng dụng **ghi lại** bản ghi bằng một đường ghi thay thế toàn bộ document.

### 2.1. Ba thao tác dễ bị nhầm lẫn

```text
MongoDB trước cập nhật:
  _id, tenantId, status, version, legacy_note, externalPayload
                          |
           +--------------+-----------------+
           |              |                 |
      save(entity)     $set(status)       $unset(legacy_note)
           |              |                 |
           v              v                 v
    Ghi representation    Chỉ thay         Chỉ xóa field
    của entity mới        status           được chỉ định
           |              |                 |
    Field chưa map        Field lạ         Field khác
    có thể biến mất       được giữ         được giữ
```

Trong một document đã lưu, **`_id` là định danh**, **`version` là dấu kiểm soát cạnh tranh ghi** của ứng dụng nếu sử dụng `@Version`, còn **các field legacy là dữ liệu thực** cần chính sách bảo toàn hoặc chuyển đổi minh bạch. Ba vấn đề này liên quan nhưng không thể giải quyết chỉ bằng một annotation.

## 3. Bảng so sánh các đường ghi

| Thao tác | Ý nghĩa chính | Field không có trong entity/BSON thay thế | Tác động tới ID/version |
| --- | --- | --- | --- |
| `MongoTemplate.insert(entity)` | Thêm document mới | Chỉ ghi những field được mapping | Tạo/chọn `_id`; khởi tạo `@Version` phù hợp |
| `MongoRepository.save(entity)` | Lưu entity mới hoặc cập nhật entity hiện có | **Có nguy cơ mất** khi ghi thay thế document | Sử dụng ID và cơ chế version theo mapping |
| `MongoTemplate.save(entity)` | Lưu entity theo mapping | **Có nguy cơ mất** vì document được tái tạo từ entity | Có xử lý `@Id`, `@Version` theo API |
| `MongoTemplate.replace(query, entity, options)` | Thay document khớp bằng representation mới | **Có nguy cơ mất** vì replacement đầy đủ | Phải giữ `_id` hợp lệ; xem riêng hợp đồng version |
| `MongoTemplate.updateFirst(query, update, Entity.class)` | Cập nhật field chọn lọc | **Giữ** field không bị `$set`/`$unset` ảnh hưởng | Không đổi `_id`; version có thể được framework tăng tự động nếu không khai báo trong Update |
| `MongoTemplate.updateMulti(...)` | Cập nhật nhiều document | **Giữ** các field ngoài phạm vi update | Không tự bảo đảm optimistic locking cho từng entity nếu thiếu điều kiện version |
| `MongoTemplate.findAndModify(...)` | Đọc và sửa một document theo điều kiện | **Giữ** field không bị sửa | Có thể trả document trước/sau sửa; cần thiết kế version check |
| Raw driver `updateOne(..., {$set:...})` | Cập nhật trực tiếp BSON | **Giữ** field ngoài phạm vi update | Bỏ qua custom mapping và `@Version` tự động của Spring |
| Raw driver `replaceOne(...)` | Thay document trực tiếp | **Mất** field không có trong replacement | `_id` bất biến; không có optimistic lock tự động |
| `upsert` | Update nếu khớp, insert nếu không | Phụ thuộc dạng update/replacement | Có thể tạo document mới; cần kiểm tra khóa, version và race |

**Đọc bảng đúng ngữ cảnh:** các phương thức Spring Data có thể áp dụng mapping, entity callbacks hoặc logic version khác nhau tùy phiên bản và overload. Không nên giả định chúng hoàn toàn tương đương chỉ vì cuối cùng đều viết dữ liệu vào collection.

## 4. _id là bất biến: giữ đúng định danh khi ghi

MongoDB yêu cầu mỗi document trong collection có `_id` duy nhất; một document **không thể thay đổi giá trị `_id`** sau khi đã tồn tại. Khi `_id` mới khác `_id` cũ, đó không phải “sửa khóa chính tại chỗ”.

### 4.1. Phân biệt _id, id trong Java và mã nghiệp vụ

File `OrderRecord.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public class OrderRecord {

    @Id
    private String id;
    private String tenantId;
    private String status;
    private long amountMinor;
    @Version
    private Long version;
    private Instant updatedAt;

    protected OrderRecord() {}

    public OrderRecord(
            String id, String tenantId, String status,
            long amountMinor, Instant updatedAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
        this.amountMinor = amountMinor;
        this.updatedAt = updatedAt;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public long getAmountMinor() {
        return amountMinor;
    }

    public Long getVersion() {
        return version;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(Instant updatedAt) {
        this.updatedAt = updatedAt;
    }
}
```

`@Id` ánh xạ property `id` thành `_id`. Trong ví dụ này, giá trị `ORD-100` là chuỗi không có dạng ObjectId hợp lệ nên phù hợp với BSON String. Với ID string gồm 24 ký tự hex, Spring Data có thể chuyển thành BSON ObjectId theo quy tắc mặc định; khi cần kiểm soát chặt kiểu BSON, cân nhắc `@MongoId` hoặc metadata `FieldType` phù hợp và kiểm thử dữ liệu lịch sử.

**Không cho client sửa `id` qua DTO cập nhật.** Những thao tác “đổi mã đơn” nên thay field nghiệp vụ riêng `orderCode` nếu yêu cầu, chứ không tự gán giá trị mới vào property `id` của document đã tồn tại.

### 4.2. Ví dụ _id bất biến ở mongosh

```javascript
// PHẢN VÍ DỤ: MongoDB không cho đổi _id của document hiện có.
db.orders.updateOne(
  { _id: "ORD-100" },
  { $set: { _id: "ORD-NEW" } }
)
```

Thao tác này thất bại vì cố sửa `_id`. Tương tự, dùng `replaceOne` với replacement mang `_id` khác với document được khớp là không hợp lệ.

```javascript
// Giữ _id, chỉ đổi trạng thái:
db.orders.updateOne(
  { _id: "ORD-100" },
  { $set: { status: "PAID" } }
)
```

**Lưu ý về `save` với id bị đổi:** ứng dụng có thể tìm nhầm document, tạo bản ghi mới hoặc gặp lỗi optimistic locking/duplicate key tùy cách gọi và trạng thái entity; không coi việc sửa id Java là một lệnh đổi `_id` trong MongoDB.

### 4.3. Insert, save và upsert khác nhau khi thiếu document

`insert` là thao tác **chỉ thêm** và sẽ lỗi nếu đã có `_id` trùng. `save` dùng cho tạo/cập nhật entity theo cơ chế mapping của Spring Data; không nên coi nó là “update đúng một field”.

`upsert` có nghĩa **khớp thì cập nhật, không khớp thì chèn**. Nếu người dùng đang yêu cầu *chỉ sửa một đơn đã tồn tại*, hãy ưu tiên `updateFirst`/**không upsert** và kiểm tra `matchedCount`. Bật upsert thiếu chủ đích có thể tạo bản ghi thiếu field bắt buộc hoặc mở rộng phạm vi dữ liệu không mong muốn.

## 5. @Version: phát hiện cập nhật dựa trên bản cũ

`@Version` là cơ chế **optimistic locking** của Spring Data MongoDB. Mỗi entity có một version được lưu vào document. Khi lưu theo đường API có hỗ trợ optimistic locking, framework thêm điều kiện **version hiện tại phải khớp**; nếu bản ghi đã bị người khác sửa, thao tác cập nhật dựa trên bản cũ không còn hợp lệ.

### 5.1. Ví dụ hai người cùng chỉnh một đơn

```text
Lúc bắt đầu: document có _id=ORD-100, version=3

Worker A                       Worker B
   |                              |
   +-- đọc version=3              +-- đọc version=3
   |                              |
   +-- save(status=PAID)           |
   |   điều kiện version=3        |
   |   thành công -> version=4    |
   |                              +-- save(status=CANCELLED)
   |                                  điều kiện version=3
   |                                  không khớp -> lỗi
   v
Không có việc B ghi đè âm thầm update của A.
```

Nếu không kiểm tra version, cách làm “đọc–sửa–ghi lại” có thể gây *lost update*: người ghi sau đè lên một thay đổi người khác vừa thực hiện.

### 5.2. Giá trị version ban đầu

Với property `@Version Long version` (wrapper), Spring Data thường khởi tạo version là **0** khi insert; với kiểu số primitive, giá trị khởi đầu theo quy tắc version có thể là **1**. Bài dùng `Long` để dễ biểu diễn trạng thái `null` trước khi insert và kiểm tra dữ liệu legacy thiếu trường version.

Version không phải timestamp và không bảo đảm một sự kiện xảy ra ở thời điểm nào; nó là **số thứ tự để kiểm soát cạnh tranh ghi**. Không tự tăng bằng code nghiệp vụ khi đang dùng những đường ghi Spring Data đã quản lý version, nếu không có lý do kỹ thuật được kiểm thử rõ ràng.

### 5.3. Repository.save với version

File `OrderRepository.java`:

```java
package com.example.shop.orders;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderRecord, String> {
}
```

Ví dụ service:

```java
OrderRecord order = repository.findById("ORD-100")
    .orElseThrow();

order.setStatus("PAID");
repository.save(order);
```

Nếu người khác đã đổi document sau khi `findById`, `save` có thể ném `OptimisticLockingFailureException` thay vì ghi đè âm thầm. Hãy trả lỗi conflict phù hợp cho client, hoặc đọc lại và thực hiện phép hợp nhất dữ liệu theo quy tắc nghiệp vụ. **Không retry nguyên entity stale bằng cách cưỡng ép tăng version**.

Optimistic locking của Spring Data đòi hỏi **write acknowledgement**. Với `WriteConcern.UNACKNOWLEDGED`, ứng dụng có thể không phát hiện được thao tác ghi thất bại vì điều kiện version không khớp. Đảm bảo môi trường dùng write concern phù hợp và kiểm thử hành vi cạnh tranh ở database thật.

### 5.4. @Version không phải ràng buộc do MongoDB server tự hiểu

MongoDB chỉ nhìn thấy field `version` và bộ lọc. Khi Spring Data thực hiện save có optimistic locking, framework biến hợp đồng thành điều kiện version trên lệnh ghi và kiểm tra kết quả. Một thao tác raw driver kiểu:

```javascript
db.orders.updateOne(
  { _id: "ORD-100" },
  { $set: { status: "PAID" } }
)
```

**Không tự tăng hay kiểm tra `version`** chỉ vì Java có annotation `@Version`. Nếu nhiều dịch vụ/worker cùng sửa document, cần thống nhất quy tắc version ở mọi đường ghi, kể cả batch job và migration.

## 6. Vì sao save có thể làm mất field không có trong Java model?

Giả sử entity `OrderRecord` từ mục 4 **không chứa** `legacy_note` và `externalPayload`. Khi đọc:

```java
OrderRecord order = repository.findById("ORD-100")
    .orElseThrow();

order.setStatus("PAID");
repository.save(order);
```

Đường đọc chỉ ánh xạ những thuộc tính được model nhận diện. Khi ghi lại entity, Spring Data tạo BSON theo model hiện hành và thực hiện thao tác lưu/thay thế phù hợp. Bản ghi sau đó có thể trở thành:

```javascript
{
  _id: "ORD-100",
  tenantId: "TENANT-A",
  status: "PAID",
  amountMinor: NumberLong(150000),
  version: NumberLong(4),
  updatedAt: ISODate("2026-11-18T08:00:00Z"),
  _class: "com.example.shop.orders.OrderRecord"
  // legacy_note và externalPayload không còn.
}
```

Điểm quan trọng:

1. **`_id` vẫn giữ nguyên** nếu save cập nhật đúng document ban đầu.
2. **`version` có thể tăng đúng** và optimistic locking vẫn hoạt động.
3. **Các field không được map vẫn có thể mất** vì representation mới không chứa chúng.

Vì vậy **`@Version` không bảo vệ các field ngoài model**. Nó chỉ giải quyết một lớp vấn đề khác: cập nhật đồng thời dựa trên phiên bản cũ.

### 6.1. Mất field không giống việc gán null

Một entity có `status = null` có thể được ghi với field null hoặc field bị bỏ qua, tùy quy tắc mapping. Nhưng đối với `legacy_note`, Java hoàn toàn không biết field này, nên không có giá trị để đưa vào BSON replacement.

Không nên kỳ vọng `MappingMongoConverter` giữ lại “phần BSON chưa biết” khi ghi lại entity. Chỉ khi ứng dụng có cơ chế đọc/ghi metadata bổ sung được thiết kế riêng hoặc sử dụng update một phần thì các field ngoài model mới được bảo toàn theo ý định.

### 6.2. @Transient cũng không có tác dụng bảo lưu field

`@Transient` cho Spring Data biết **không ánh xạ** thuộc tính Java vào document. Nó **không** phải annotation để giữ nguyên một field BSON cũ.

```java
import org.springframework.data.annotation.Transient;

@Transient
private String temporaryDisplayLabel;
```

Đoạn trên chỉ minh họa một property không được ghi. Nếu BSON cũ có field cùng tên nhưng model bỏ qua, `save` dạng replacement vẫn có thể làm field đó biến mất.

## 7. Update có chọn lọc: giữ field ngoài phạm vi thay đổi

Nếu yêu cầu là “đổi trạng thái đơn sang PAID”, thao tác an toàn với dữ liệu ngoài model thường là **`$set` đúng field cần đổi**, không phải ghi lại toàn bộ entity.

### 7.1. MongoDB $set

```javascript
db.orders.updateOne(
  {
    _id: "ORD-100",
    tenantId: "TENANT-A",
    version: NumberLong(3)
  },
  {
    $set: {
      status: "PAID",
      updatedAt: ISODate("2026-11-20T02:00:00Z")
    },
    $inc: { version: NumberLong(1) }
  }
)
```

Thao tác trên:

- Chỉ khớp khi **ID, tenant và version** đúng.
- Cập nhật `status`/`updatedAt`.
- Tăng `version` trong **cùng một update nguyên tử trên document**.
- Không sửa `legacy_note` hoặc `externalPayload`.

**Đây là ví dụ mongosh, không phải code Spring Data.** Với Spring Data entity có `@Version`, một số API update **tự động tăng** version nếu không nêu trong `Update`; không nên sao chép cả `$inc version` rồi thêm một phép tăng khác trong Java mà không kiểm tra hành vi API đang dùng.

### 7.2. MongoTemplate.updateFirst với CAS

CAS (*compare-and-set*) nghĩa là kiểm tra giá trị dự kiến ngay trong điều kiện update. File `OrderUpdateService.java`:

```java
package com.example.shop.orders;

import com.mongodb.client.result.UpdateResult;
import java.time.Clock;
import java.time.Instant;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class OrderUpdateService {
    private final MongoTemplate template;
    private final Clock clock;

    public OrderUpdateService(MongoTemplate template, Clock clock) {
        this.template = template;
        this.clock = clock;
    }

    public void markPaid(
            String permittedTenantId,
            String orderId,
            long expectedVersion) {

        if (permittedTenantId == null
                || permittedTenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant không hợp lệ");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("ID không hợp lệ");
        }
        if (expectedVersion < 0) {
            throw new IllegalArgumentException("Version không hợp lệ");
        }

        Query query = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(permittedTenantId)
                .and("version").is(expectedVersion));

        Update update = new Update()
            .set("status", "PAID")
            .set("updatedAt", Instant.now(clock));

        UpdateResult result =
            template.updateFirst(query, update, OrderRecord.class);

        if (result.getMatchedCount() != 1) {
            throw new OptimisticLockingFailureException(
                "Đơn không tồn tại, không thuộc phạm vi hoặc version đã đổi");
        }
    }
}
```

Trong ví dụ:

- `Criteria.where("id")` là property Java ánh xạ sang BSON `_id`.
- `tenantId` là ranh giới dữ liệu bắt buộc; ứng dụng phải xác minh quyền trước khi gọi.
- `version` được kiểm tra ngay trong câu update, tránh race giữa `findById` và `save`.
- `Update` **không** đặt `_id`, **không** ghi lại object và không dùng `upsert`.
- Với mapping/version handling của Spring Data MongoDB, `@Version` trong update được hỗ trợ thường **tự động tăng** nếu chưa có chỉ thị thay đổi version trong `Update`. Đừng tăng thủ công hai lần.
- `getMatchedCount() == 0` là tín hiệu không tìm thấy/đã bị sửa/không được phép; không tiết lộ chi tiết tồn tại của tài nguyên ngoài tenant cho client.

Một bean `Clock` có thể được đăng ký như sau:

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

**Phân biệt quan trọng:** `updateFirst` không tự thực hiện “so sánh version cũ” cho mọi lời gọi chỉ vì entity có `@Version`. Điều kiện `version == expectedVersion` được đưa vào `Query` **một cách tường minh** trong ví dụ. Việc tự tăng version khi cập nhật và việc **kiểm tra version đầu vào** là hai hành vi khác nhau.

### 7.3. matchedCount khác modifiedCount

`UpdateResult.getMatchedCount()` cho biết có document nào khớp filter, còn `getModifiedCount()` cho biết có document nào thực sự thay đổi theo kết quả MongoDB.

Không nên dùng `modifiedCount == 0` làm bằng chứng chắc chắn rằng document không tồn tại: một update no-op (đặt lại đúng giá trị đang có) có thể khớp nhưng không thay đổi gì. Khi sử dụng version bump, hành vi no-op có thể thay đổi tùy API; vẫn nên ưu tiên `matchedCount` để xác nhận CAS đã khớp, cùng với write acknowledgement.

## 8. Xóa field có chủ đích bằng $unset, không dùng replacement vô tình

Nếu business quyết định `legacy_note` phải bị loại bỏ, hãy thể hiện hành động đó tường minh:

```javascript
db.orders.updateOne(
  { _id: "ORD-100" },
  { $unset: { legacy_note: "" } }
)
```

Trong Spring Data:

```java
Update update = new Update()
    .unset("legacy_note");

template.updateFirst(
    Query.query(Criteria.where("id").is("ORD-100")),
    update,
    OrderRecord.class);
```

Đây là đoạn minh họa đặt trong một service/class có `MongoTemplate template`; trong sản phẩm thực phải thêm điều kiện tenant, version và xử lý kết quả như mục 7. Khi update trên entity có `@Version`, framework có thể tự thay đổi version theo đường API tương ứng.

Nếu mục tiêu là **giữ** `legacy_note`, tuyệt đối **không** đưa field đó vào `$unset`. Mỗi lần xóa field legacy nên có migration plan, số lượng document dự kiến, cách đối soát và phương án khôi phục khi cần.

### 8.1. Vì sao update từng field tốt hơn khi nhiều dịch vụ cùng quản lý schema?

Trong hệ thống có nhiều dịch vụ dùng chung một collection, một service chỉ sở hữu `status` và `updatedAt`; dịch vụ khác bổ sung `externalPayload`. Nếu cả hai dùng full replacement trên model riêng, chúng có thể **xóa dữ liệu của nhau**.

Chiến lược cập nhật chọn lọc là một cách giảm nguy cơ:

```text
Service Orders:       $set(status, updatedAt)
Service Integration:  $set(externalPayload.trackingKey)
Service Compliance:   $set(legacy_note)
```

Tuy nhiên, hai update cùng thay **một field** vẫn có thể ghi đè nhau. Nếu cần ngăn *lost update* trong cùng field hoặc các bất biến liên field, hãy kết hợp điều kiện CAS/version hoặc một thiết kế transaction phù hợp.

### 8.2. Update nested field bằng dot notation

Muốn đổi riêng tracking key:

```javascript
db.orders.updateOne(
  { _id: "ORD-100" },
  { $set: { "externalPayload.trackingKey": "WH-9000" } }
)
```

Lệnh này giữ `externalPayload.source`. Ngược lại:

```javascript
db.orders.updateOne(
  { _id: "ORD-100" },
  { $set: { externalPayload: { trackingKey: "WH-9000" } } }
)
```

sẽ **thay object `externalPayload`**, do đó có thể làm mất `source`. “`$set` giữ field khác” chỉ đúng **ngoài đường dẫn được thay thế**; nếu `$set` cả object con, các field con không được đưa vào giá trị mới sẽ mất.

## 9. findAndModify: sửa có điều kiện và đọc kết quả

Khi cần trả ngay document sau khi sửa, Spring Data MongoDB có `findAndModify`. Nó khác với quy trình “find rồi update” ở chỗ thao tác tìm–sửa một document được thực hiện phía MongoDB trong cùng lệnh phù hợp.

Ví dụ:

```java
import java.time.Instant;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query query = Query.query(
    Criteria.where("id").is("ORD-100")
        .and("tenantId").is("TENANT-A")
        .and("version").is(3L));

Update update = new Update()
    .set("status", "PAID")
    .set("updatedAt", Instant.parse("2026-11-20T02:00:00Z"));

OrderRecord updated = template.findAndModify(
    query,
    update,
    FindAndModifyOptions.options().returnNew(true),
    OrderRecord.class);

if (updated == null) {
    throw new IllegalStateException(
        "Không khớp ID/tenant/version");
}
```

`returnNew(true)` yêu cầu trả **document sau cập nhật**; mặc định của một số overload `findAndModify` trả bản **trước** cập nhật. `null` có thể nghĩa là không có document phù hợp với các điều kiện. Câu này không bật `upsert`; nếu có bật upsert, cần thiết kế riêng trường hợp tạo mới và khóa định danh.

Các field chưa có trong model **vẫn tồn tại trong BSON sau update**, nhưng Java object trả về chỉ ánh xạ các property mà `OrderRecord` biết. Vì vậy đọc lại Java object và không thấy `legacy_note` **không chứng minh** field đó đã bị xóa; phải kiểm tra document BSON trực tiếp.

## 10. Trường hợp đặc biệt: giữ field lạ bằng Map hoặc converter

Có ứng dụng muốn nắm toàn bộ metadata mở rộng và ghi lại chúng. Có thể **thiết kế schema** với một map được khai báo rõ:

```java
import java.util.Map;
import org.springframework.data.mongodb.core.mapping.Field;

@Field("extensions")
private Map<String, Object> extensions;
```

Điều này ánh xạ **field BSON `extensions`**, chẳng hạn:

```javascript
{
  _id: "ORD-100",
  extensions: {
    source: "warehouse-v1",
    trackingKey: "WH-7788"
  }
}
```

**Nó không tự thu thập mọi field không biết tại root** như `legacy_note` hoặc `externalPayload`. Không nên tự cho rằng thêm `Map<String,Object>` vào entity sẽ khiến Spring Data giữ lại tất cả field BSON lạ một cách tự động.

Khi thực sự cần round-trip toàn bộ BSON document không biết trước schema, có thể dùng:

- Một **read model dạng `org.bson.Document`** qua driver/`MongoTemplate` với logic hợp nhất được kiểm soát.
- **Custom conversions** để ánh xạ legacy format và bảo toàn đúng các field đã được hợp đồng chỉ định.
- Một **schema mở rộng có tên rõ ràng** (như `extensions`) để các phiên bản mới biết cách đọc/ghi nó.
- **Partial update** để không cần đọc/ghi lại những field mà service không sở hữu.

Đừng ghi toàn bộ `Document` do client gửi trở lại database mà không whitelist field hoặc kiểm tra quyền: có thể vô tình cho phép client sửa `_id`, `version`, tenantId hoặc các field nội bộ.

## 11. Dữ liệu phiên bản cũ chưa có trường version

Một tình huống thường gặp là document v1 lưu:

```javascript
{
  _id: "ORD-LEGACY",
  tenantId: "TENANT-A",
  status: "NEW"
  // Không có field version.
}
```

Khi entity Java mới thêm `@Version Long version`, property `version` có thể là `null` sau khi đọc document cũ. Trong Spring Data, version `null` thường liên quan đến nhận diện entity **mới**, khiến `save` có thể đi theo đường insert và dẫn tới **duplicate key** thay vì cập nhật như mong muốn. Không nên đọc dữ liệu legacy rồi gọi `save` hàng loạt mà không kiểm thử trường hợp này.

### 11.1. Chiến lược backfill version

Một cách tiếp cận là backfill trường version trong migration có kiểm soát:

```javascript
// CHỈ MINH HỌA: chạy sau khi đã đánh giá toàn vẹn dữ liệu,
// thứ tự triển khai dịch vụ và tác động đến luồng ghi.
db.orders.updateMany(
  { version: { $exists: false } },
  { $set: { version: NumberLong(0) } }
)
```

Lệnh này đặt version ban đầu cho những document thiếu field; **không tự giải quyết race** với một ứng dụng đang ghi song song. Hệ thống có thể cần tạm điều phối writers, chạy migration theo nhóm, hoặc triển khai reader/writer tương thích trước khi kích hoạt strict optimistic locking.

Không nên áp `version: 0` cho mọi document một cách mù quáng: những document đã có version cao hơn hoặc đang tham gia giao dịch cần được giữ nguyên.

### 11.2. Dữ liệu v1 có field version khác kiểu

Nếu v1 lưu `version: "3"` (BSON String) nhưng v2 dùng `Long`, query `version: NumberLong(3)` trên server có thể **không khớp** document chứa String, ngay cả khi một custom converter giúp Java đọc giá trị này. Cần chuyển đổi BSON type hoặc có một chiến lược tương thích rõ ràng; chỉ sửa type Java không đủ.

Tương tự, nếu bản cũ đặt tên `revision` còn bản mới dùng `version`, phải dùng `@Field("revision")` hoặc migration theo hợp đồng thực tế. Không được tự giả định document tự có field `version` chỉ vì đã thêm `@Version` vào model.

## 12. Những đường ghi có thể bỏ qua kiểm soát version của Spring

| Đường ghi | Có thể giữ field không liên quan? | Có tự kiểm tra expected version của caller? |
| --- | --- | --- |
| `repository.save(versionedEntity)` | Không đảm bảo; có thể ghi full replacement | **Có**, theo optimistic locking được hỗ trợ |
| `template.save(versionedEntity)` | Không đảm bảo; có thể ghi full replacement | **Có**, theo đường save/version được hỗ trợ |
| `template.updateFirst(query, update, Entity.class)` | Có, với update chọn lọc | **Chỉ khi query có điều kiện version phù hợp**; framework có thể tự tăng version |
| `template.findAndModify(query, update, ...)` | Có | **Chỉ khi query có điều kiện version phù hợp**; framework có thể tự tăng version |
| `template.updateMulti(...)` | Có | Cần thiết kế điều kiện phù hợp; không thay thế check optimistic locking riêng cho từng entity |
| `template.getCollection(...).updateOne(...)` | Có | **Không tự động**; caller phải đưa version vào filter và `$inc` nếu cần |
| `db.orders.updateOne(...)` trong mongosh | Có | **Không tự động**; phụ thuộc filter/update do người viết |
| `db.orders.replaceOne(...)` | Không | **Không tự động**; cần version condition và dữ liệu thay thế đúng |

Điểm quan trọng của bảng là **tự tăng version** khác với **so sánh version trước khi ghi**. Một phiên bản tăng đều không ngăn lost update nếu tác vụ không yêu cầu expected version trong filter.

### 12.1. Raw MongoDB driver: CAS phải được triển khai đủ

Nếu buộc dùng driver trực tiếp:

```java
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

UpdateResult result = template.getCollection("orders")
    .updateOne(
        new Document("_id", "ORD-100")
            .append("tenantId", "TENANT-A")
            .append("version", 3L),
        new Document("$set",
            new Document("status", "PAID"))
            .append("$inc",
                new Document("version", 1L))
    );

if (result.getMatchedCount() != 1) {
    throw new IllegalStateException("Version không khớp");
}
```

Đây là code minh họa trong class đã có biến `MongoTemplate template`. Nó sử dụng tên field **BSON trực tiếp** và không đi qua entity mapping, custom converters, auditing callbacks hoặc logic optimistic locking tự động của Spring. Vì thế phải dùng đúng kiểu BSON của `_id` và `version`, tự cập nhật timestamp/audit nếu yêu cầu, và kiểm tra write acknowledgement.

### 12.2. Auditing callbacks không phải phép màu cho partial update

Nếu entity dùng `@LastModifiedDate`, nhiều luồng `save(entity)` kích hoạt entity callbacks/auditing để cập nhật timestamp. Một lệnh `Update.set(...)` không nhất thiết đi qua cùng callback ánh xạ entity đầy đủ.

Vì vậy, với partial update, hãy cập nhật tường minh những field nghiệp vụ/audit bắt buộc, chẳng hạn `updatedAt` và `updatedBy`. Nếu ứng dụng có audit policy phức tạp, cần kiểm thử đúng overload được sử dụng và có thể gom logic vào service để mọi đường ghi tuân thủ cùng một hợp đồng.

## 13. Kiểm thử tích hợp: quan sát BSON trước và sau ghi

Để kiểm chứng đúng chủ đề của bài, unit test chỉ mock `OrderRepository` là **không đủ**. Mock có thể trả object đúng nhưng không chứng minh `save` có làm mất field ngoài model, `updateFirst` có tăng version hay CAS có ngăn ghi stale.

Nên dùng MongoDB test instance riêng và chèn document v1 **trực tiếp bằng driver**. Như vậy, fixture mang cả field mà Java entity không biết.

### 13.1. JUnit 5: seed dữ liệu legacy

Ví dụ dùng Spring Boot Data MongoDB Test và AssertJ. File `OrderWriteCompatibilityTest.java`:

```java
package com.example.shop.orders;

import com.mongodb.client.result.UpdateResult;
import java.time.Instant;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class OrderWriteCompatibilityTest {

    @Autowired
    MongoTemplate template;

    private static final String ID = "ORD-100";

    @BeforeEach
    void seed() {
        // Chỉ kết nối tới MongoDB kiểm thử được cô lập.
        var collection = template.getCollection("orders");
        collection.deleteMany(new Document());

        collection.insertOne(
            new Document("_id", ID)
                .append("tenantId", "TENANT-A")
                .append("status", "NEW")
                .append("amountMinor", 150000L)
                .append("version", 3L)
                .append("updatedAt",
                    java.util.Date.from(Instant.parse(
                        "2026-11-18T08:00:00Z")))
                .append("legacy_note",
                    "Đã đối soát với hệ thống cũ")
                .append("externalPayload",
                    new Document("source", "warehouse-v1")
                        .append("trackingKey", "WH-7788"))
        );
    }

    private Document raw() {
        return template.getCollection("orders")
            .find(new Document("_id", ID))
            .first();
    }

    @Test
    void readingEntityDoesNotDeleteUnknownFields() {
        OrderRecord entity = template.findById(
            ID, OrderRecord.class);

        assertThat(entity).isNotNull();
        assertThat(entity.getId()).isEqualTo(ID);
        assertThat(entity.getVersion()).isEqualTo(3L);
        assertThat(entity.getStatus()).isEqualTo("NEW");

        Document stillStored = raw();
        assertThat(stillStored).isNotNull();
        assertThat(stillStored.getString("legacy_note"))
            .isEqualTo("Đã đối soát với hệ thống cũ");
        assertThat(stillStored.get(
            "externalPayload", Document.class).getString("source"))
            .isEqualTo("warehouse-v1");
    }

    @Test
    void fullSaveCanDiscardUnmappedFields() {
        OrderRecord entity = template.findById(
            ID, OrderRecord.class);
        assertThat(entity).isNotNull();
        entity.setStatus("PAID");

        template.save(entity);

        Document afterSave = raw();
        assertThat(afterSave).isNotNull();
        assertThat(afterSave.getString("_id")).isEqualTo(ID);
        assertThat(afterSave.getString("status"))
            .isEqualTo("PAID");
        assertThat(afterSave.get("version", Number.class)
            .longValue()).isEqualTo(4L);

        // Đây là điều CẦN PHÁT HIỆN, không phải mục tiêu giữ dữ liệu.
        assertThat(afterSave.containsKey("legacy_note")).isFalse();
        assertThat(afterSave.containsKey("externalPayload"))
            .isFalse();
    }

    @Test
    void partialUpdatePreservesUnknownFieldsAndId() {
        Query condition = Query.query(
            Criteria.where("id").is(ID)
                .and("tenantId").is("TENANT-A")
                .and("version").is(3L));

        Update changes = new Update()
            .set("status", "PAID")
            .set("updatedAt", Instant.parse(
                "2026-11-20T02:00:00Z"));

        UpdateResult result = template.updateFirst(
            condition, changes, OrderRecord.class);
        assertThat(result.getMatchedCount()).isEqualTo(1);

        Document afterUpdate = raw();
        assertThat(afterUpdate).isNotNull();
        assertThat(afterUpdate.getString("_id"))
            .isEqualTo(ID);
        assertThat(afterUpdate.getString("status"))
            .isEqualTo("PAID");
        assertThat(afterUpdate.get("version", Number.class)
            .longValue()).isEqualTo(4L);

        assertThat(afterUpdate.getString("legacy_note"))
            .isEqualTo("Đã đối soát với hệ thống cũ");
        Document external = afterUpdate.get(
            "externalPayload", Document.class);
        assertThat(external.getString("source"))
            .isEqualTo("warehouse-v1");
        assertThat(external.getString("trackingKey"))
            .isEqualTo("WH-7788");
    }

    @Test
    void staleVersionCannotOverwriteWinner() {
        Query v3 = Query.query(
            Criteria.where("id").is(ID)
                .and("tenantId").is("TENANT-A")
                .and("version").is(3L));

        UpdateResult first = template.updateFirst(
            v3,
            new Update().set("status", "PAID"),
            OrderRecord.class);

        UpdateResult stale = template.updateFirst(
            Query.query(
                Criteria.where("id").is(ID)
                    .and("tenantId").is("TENANT-A")
                    .and("version").is(3L)),
            new Update().set("status", "CANCELLED"),
            OrderRecord.class);

        assertThat(first.getMatchedCount()).isEqualTo(1);
        assertThat(stale.getMatchedCount()).isZero();
        assertThat(raw().getString("status")).isEqualTo("PAID");
        assertThat(raw().get("version", Number.class)
            .longValue()).isEqualTo(4L);
    }
}
```

**Cảnh báo:** `collection.deleteMany(new Document())` xóa **toàn bộ collection `orders` trong database đang được kết nối**. Chỉ chạy test này với MongoDB cô lập, chẳng hạn Testcontainers và cấu hình test không thể trỏ nhầm tới production. Import `@DataMongoTest` có thể khác khi thay major version Spring Boot; đối chiếu dependency thực tế.

Các ví dụ giả định đường mapping của `OrderRecord` đã được kích hoạt và `@Version Long version` trong lớp model ở mục 4 hoạt động trên MongoDB test instance. Chưa chạy Gradle/test trong bước viết tài liệu; test là mã hướng dẫn để dự án triển khai và kiểm chứng.

### 13.2. Vì sao test phải chèn bằng driver thô?

Nếu tạo fixture bằng:

```java
template.insert(new OrderRecord(
    "ORD-100", "TENANT-A", "NEW", 150000L,
    Instant.parse("2026-11-18T08:00:00Z")));
```

Spring Data chỉ lưu những field Java model biết. Fixture này **không có `legacy_note` và `externalPayload` từ đầu**, nên kể cả `save` xóa dữ liệu legacy, test vẫn không thể phát hiện.

Dùng `template.getCollection("orders").insertOne(new Document(...))` để seed một BSON **thật sự mang dữ liệu cũ**. Sau đó test đọc bằng `MongoTemplate` và ghi bằng đúng API ứng dụng dùng; cuối cùng kiểm tra lại bằng `getCollection(...)` để nhìn thấy những field ngoài model.

### 13.3. Đánh giá cả version và dữ liệu không bị sửa

Ma trận kiểm thử khuyến nghị:

| Kịch bản | Bất biến phải xác nhận |
| --- | --- |
| Chỉ đọc entity từ BSON legacy | Document trong database không bị thay đổi |
| `save` toàn entity cũ | Phát hiện khả năng mất field ngoài model; nếu nghiệp vụ không cho phép thì không dùng đường ghi này |
| `updateFirst` với `$set` | `_id`, `legacy_note`, `externalPayload` giữ nguyên |
| Hai update cùng expectedVersion | Chỉ một update khớp; version tăng một lần |
| Update theo ID sai | `matchedCount = 0`; không upsert vô tình |
| Update theo tenant không được phép | `matchedCount = 0`; không đổi dữ liệu tenant khác |
| `$set` vào field con | Giữ các sibling field trong object |
| `$set` thay toàn object con | Test phát hiện các sibling cũ bị xóa |
| Document thiếu `version` | Có migration hoặc tương thích rõ, không dùng `save` mù quáng |
| Document có `_id` dạng ObjectId/String khác nhau | Query và mapping không nhầm kiểu |
| Update qua raw driver | Có CAS/version và timestamp tường minh nếu được yêu cầu |
| Update qua reactive API | Bất biến BSON và version như imperative |
| Cập nhật với network/write failure | Không báo thành công nếu chưa xác nhận outcome theo chính sách hệ thống |

## 14. Transaction, nguyên tử và nhất quán không thay thế version

MongoDB áp dụng một lệnh cập nhật lên **một document** theo tính nguyên tử của thao tác đó. Khi `updateOne` kiểm tra `_id` + `version` và dùng `$inc`, việc kiểm tra và ghi được thực hiện như một thao tác, giúp ngăn hai writer dựa trên cùng version đều thành công.

Tuy nhiên:

- Transaction nhiều document là công cụ cho **bất biến liên document**, không tự sửa lỗi ứng dụng ghi replacement thiếu field legacy.
- Nếu hai writer đọc dữ liệu cũ rồi mỗi người thực hiện một lệnh `$set` không có điều kiện CAS, kết quả vẫn phụ thuộc trường nào được viết và thứ tự thực hiện.
- Một transaction không có chính sách version/điều kiện nghiệp vụ phù hợp vẫn có thể tạo vấn đề khi client retry hoặc khi ứng dụng đọc lại một state không mong muốn.
- Việc retry thao tác ghi phải xét **idempotency**. Chẳng hạn retry `$inc: { amountMinor: 100 }` có thể cộng hai lần nếu không có khóa thao tác hoặc cơ chế chống lặp.

**Nguyên tắc:** dùng cập nhật chọn lọc để giữ dữ liệu ngoài model; dùng expected version/CAS để chống stale writes; dùng transaction khi cần nguyên tử trên nhiều document. Chúng giải quyết **ba mối lo khác nhau**.

## 15. Khi dùng ReactiveMongoTemplate

Với reactive access, cách xây `Query` và `Update` tương tự, nhưng phương thức trả `Mono<UpdateResult>`:

```java
import com.mongodb.client.result.UpdateResult;
import reactor.core.publisher.Mono;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public Mono<Void> markPaidReactive(
        ReactiveMongoTemplate template,
        String tenantId,
        String id,
        long expectedVersion) {

    Query condition = Query.query(
        Criteria.where("id").is(id)
            .and("tenantId").is(tenantId)
            .and("version").is(expectedVersion));

    Update changes = new Update()
        .set("status", "PAID");

    return template.updateFirst(
            condition, changes, OrderRecord.class)
        .flatMap(result -> {
            if (result.getMatchedCount() != 1) {
                return Mono.error(
                    new IllegalStateException(
                        "Không khớp ID/tenant/version"));
            }
            return Mono.<Void>empty();
        });
}
```

Đây là phương thức minh họa trong class service Java; caller phải xác thực `tenantId`, kiểm tra input và subscribe publisher mới kích hoạt cập nhật. Nếu có auditing timestamp bắt buộc, thêm nó vào `Update`. Trong kiểm thử reactive, dùng `StepVerifier` để xác nhận luồng thành công hoặc lỗi CAS.

**Reactive không thay đổi quy tắc BSON:** `$set` vẫn giữ field ngoài đường dẫn được sửa, raw driver vẫn không tự hiểu annotation `@Version`, và save toàn entity vẫn có rủi ro làm mất field không có trong model.

## 16. Checklist vận hành trước khi đổi cách ghi

1. **Chụp schema thực tế:** liệt kê những field đang lưu, kể cả field không có trong model Java, field lồng nhau, dữ liệu do dịch vụ khác sở hữu và kiểu BSON.
2. **Xác định ai sở hữu mỗi field:** một service có được xóa metadata từ dịch vụ khác không? Field nào phải được giữ nguyên qua migration?
3. **Khóa định danh:** bảo đảm `_id` đúng kiểu BSON, giữ nguyên khi cập nhật; phân biệt `_id` với mã nghiệp vụ có thể đổi.
4. **Chọn đường ghi:** dùng `save` khi thực sự muốn ghi trạng thái entity đầy đủ và schema được kiểm soát; dùng `updateFirst`/`findAndModify` khi chỉ cần sửa một phần.
5. **Bảo vệ cạnh tranh:** kiểm tra `@Version` và write concern; nếu dùng partial update, đưa expectedVersion vào query theo chính sách.
6. **Kiểm soát upsert:** với update-only, không bật upsert; kiểm tra `matchedCount`.
7. **Audit và thời gian:** đặt `updatedAt`/`updatedBy` rõ ràng trên partial update nếu các callback của entity không áp dụng.
8. **Migration version cũ:** lập kế hoạch cho các document thiếu version hoặc lưu version khác kiểu.
9. **Kiểm thử BSON thực:** seed field unknown bằng raw driver, chạy cả save và patch; kiểm tra `_id`, version và unknown fields trước/sau.
10. **Theo dõi ở production:** thống kê optimistic-lock conflicts, no-match updates, duplicate keys, số lần retry và lỗi migration; chỉ log ID/metadata cần thiết, không ghi dữ liệu nhạy cảm.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân chính | Cách xử lý |
| --- | --- | --- |
| Sau `save` biến mất `legacy_note` | Entity không map field, thao tác ghi thay thế document | Dùng `$set`/`$unset` có chủ đích hoặc thiết kế model/extension schema |
| Version tăng nhưng dữ liệu do service khác ghi vẫn mất | Optimistic locking chỉ kiểm tra stale write, không giữ unknown fields | Tách chiến lược bảo toàn dữ liệu khỏi chiến lược version |
| `updateFirst` không báo lỗi dù version cũ | Query không chứa expected version hoặc caller bỏ qua result | Thêm điều kiện version và kiểm tra `matchedCount` |
| Version tăng hai lần | Tự `inc("version")` trong Update mà API đã tự quản lý version | Chọn một cơ chế rõ, kiểm tra BSON sau update |
| Không tìm được document có ID dài 24 ký tự hex | String ID được map sang ObjectId, BSON lịch sử dùng String | Kiểm tra mapping `@Id`/`@MongoId` và kiểu BSON thực |
| Sửa `id` Java tạo bản ghi mới hoặc lỗi | `_id` không thể sửa tại chỗ | Giữ `_id` bất biến, tạo field mã nghiệp vụ riêng |
| Document legacy thiếu version gây lỗi ghi | Version null được hiểu như entity mới hoặc dữ liệu không hợp đồng | Backfill/migration và test riêng dữ liệu legacy |
| `$set` cả object con làm mất field sibling | Thay thế object tại đường dẫn cha | Dùng dotted path đúng field cần sửa |
| `@LastModifiedDate` không thay đổi trong partial update | Đường update không chạy giống save callback | Set auditing fields tường minh |
| Ghi raw driver vượt qua version và converter | Bỏ qua Spring mapping infrastructure | Tự làm CAS, mapping BSON, audit và kiểm tra write result |
| Update-only vô tình tạo document thiếu field | Bật upsert không có chủ đích | Tách update khỏi create, không upsert khi chỉ được sửa |
| Test mock luôn xanh, production mất dữ liệu | Mock không có BSON unknown fields | Integration test seed raw BSON và assert field preservation |

## 18. Bài tập vận dụng

Một hệ thống quản lý kho có document:

```javascript
{
  _id: "SKU-001",
  tenantId: "T-A",
  quantity: NumberLong(25),
  version: NumberLong(9),
  updatedAt: ISODate("2026-11-19T08:00:00Z"),
  supplierData: {
    supplierId: "SUP-7",
    restockCode: "RST-99"
  },
  legacyTags: ["fragile", "priority"]
}
```

Ứng dụng Java mới chỉ biết `id`, `tenantId`, `quantity`, `version` và `updatedAt`. Cần trừ 3 đơn vị khi tạo phiếu xuất kho:

1. Vì sao đọc entity, giảm `quantity` rồi gọi `save` có rủi ro làm mất dữ liệu?
2. Viết một câu `updateOne` kiểm tra `_id`, tenant, version 9 và `quantity >= 3` rồi dùng `$inc` giảm quantity và tăng version **một lần**.
3. Viết đoạn `MongoTemplate.updateFirst` tương đương với `Criteria` và `Update.inc("quantity", -3)`, cân nhắc cách Spring Data tự cập nhật `@Version`.
4. Khi hai yêu cầu cùng đọc version 9, điều gì xảy ra với yêu cầu ghi thứ hai?
5. Kiểm tra sau cập nhật rằng `supplierData.supplierId` và `legacyTags` không thay đổi.
6. Nếu dữ liệu cũ thiếu `version` hoặc `quantity` ở dạng BSON String, cần xử lý trước khi bật CAS như thế nào?
7. Nếu phiếu xuất kho được retry sau timeout, làm sao ngăn thao tác trừ số lượng hai lần?

**Định hướng:** `save` toàn entity có thể loại các field không được map. Dùng update nguyên tử với điều kiện:

```javascript
db.stock.updateOne(
  {
    _id: "SKU-001",
    tenantId: "T-A",
    version: NumberLong(9),
    quantity: { $gte: NumberLong(3) }
  },
  {
    $inc: {
      quantity: NumberLong(-3),
      version: NumberLong(1)
    },
    $set: {
      updatedAt: ISODate("2026-11-20T02:00:00Z")
    }
  }
)
```

Đối với Spring Data, chỉ nên thêm `inc("quantity", -3)` và điều kiện expected version; không tăng version thủ công nếu update entity có `@Version` đã được framework quản lý. Kiểm tra `matchedCount` để phân biệt thành công với thất bại điều kiện. Khi retry lệnh trừ số lượng, cần khóa idempotency của phiếu xuất hoặc thiết kế đảm bảo cùng một lệnh nghiệp vụ không bị áp dụng hai lần.

## 19. Tài liệu tham khảo

- Spring Data MongoDB — [Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `save`, `updateFirst`, `findAndModify`, replace/upsert và optimistic locking với `@Version`.
- Spring Data MongoDB — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): `@Id`, `@MongoId`, `@Field`, `@Transient` và metadata ánh xạ entity.
- Spring Data MongoDB — [Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html): callback auditing và thời điểm cập nhật.
- MongoDB Manual — [Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/): `$set`, `$unset`, `$inc` và tính nguyên tử của update.
- MongoDB Manual — [replaceOne](https://www.mongodb.com/docs/manual/reference/method/db.collection.replaceOne/): replacement, upsert và ràng buộc `_id`.
- MongoDB Manual — [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): thao tác nguyên tử trên document và điều kiện cập nhật.

## Ghi nhớ

**`_id`** phải được giữ bất biến khi cập nhật document. **`@Version`** giúp phát hiện stale writes trên các đường API Spring Data được hỗ trợ, nhưng không bảo vệ khỏi việc mất field BSON mà entity Java không biết. **`save`/replace** có thể ghi lại representation thiếu field legacy, trong khi **`$set`/`$unset` có chọn lọc** giúp bảo toàn những vùng dữ liệu không đụng tới. Khi cần cả tính đúng đắn và tương thích schema, hãy dùng **CAS với expected version**, cập nhật đúng field, kiểm tra kết quả ghi và kiểm thử với BSON legacy thực trước khi đưa vào production.
