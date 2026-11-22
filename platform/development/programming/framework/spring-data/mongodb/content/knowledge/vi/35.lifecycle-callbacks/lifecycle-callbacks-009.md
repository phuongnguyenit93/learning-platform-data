# Callback với entity bất biến và đối tượng trả về

> **Chương:** Vòng đời và callback  
> **Module:** `SPRING_DATA_MONGODB`

Trong Spring Data MongoDB, một entity có thể là Java `record` hoặc một class có các field `final`, không có setter. Thiết kế **bất biến (immutable)** giúp tránh việc sửa trạng thái ngoài ý muốn, nhưng làm nảy sinh câu hỏi: một lifecycle callback sẽ gán mã tham chiếu chuẩn hóa, bổ sung metadata hoặc điều chỉnh kết quả đọc như thế nào khi **không thể sửa trực tiếp entity cũ**?

Giải pháp là sử dụng **`EntityCallback<T>`** theo hợp đồng trả về giá trị: callback nhận entity, có thể tạo **một instance mới cùng loại `T`**, rồi **trả instance đó cho Spring Data tiếp tục xử lý**. Tuy nhiên, không phải mọi checkpoint có cùng tác động lên dữ liệu: ở `BeforeConvertCallback`, entity trả về được dùng khi tạo BSON `Document`; ở `BeforeSaveCallback`, BSON đã được tạo nên phải thay đổi chính `Document` nếu muốn thay đổi dữ liệu ghi. `AfterSaveCallback` và `AfterConvertCallback` có thể thay đổi entity trả về cho caller nhưng không tự thực hiện một lần ghi mới.

Đây là một chủ đề trong module `SPRING_DATA_MONGODB`: sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác qua `MongoTemplate` hoặc repository; thực hành truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng. Bài tập trung vào **callback lifecycle, entity bất biến và ý nghĩa của đối tượng trả về**, thay vì giải thích lại toàn bộ mapping MongoDB.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt lifecycle `EntityCallback` với các `ApplicationEvent` của Spring Data MongoDB.
2. Xác định checkpoint **trước convert**, **trước save**, **sau save**, **sau convert** và tác động thực tế của giá trị trả về ở mỗi checkpoint.
3. Dùng Java `record` hoặc immutable class với **copy/with method** thay cho setter.
4. Viết `BeforeConvertCallback<T>` chuẩn hóa field persistent và trả entity mới.
5. Viết `BeforeSaveCallback<T>` cập nhật BSON `Document` đúng thời điểm; tránh nhầm “return object mới” với “BSON được map lại”.
6. Hiểu `AfterSaveCallback<T>` và `AfterConvertCallback<T>` có thể thay đổi kết quả Java mà **không tự ghi lại MongoDB**.
7. Đăng ký callback qua Spring bean, kiểm soát ordering và tương tác với auditing/ID/version.
8. So sánh callback imperative và reactive; viết kiểm thử đọc lại raw BSON, bản gốc và object được trả về.
9. Nhận diện các thao tác `updateFirst`/bulk/direct driver không đi qua full entity-conversion lifecycle.

## 2. Entity bất biến là gì trong ngữ cảnh MongoDB?

Một Java `record` có các component không thể thay đổi trực tiếp sau khi tạo:

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    String externalRef,
    String normalizedRef,
    Instant createdAt
) {
    public OrderDocument withNormalizedRef(String newRef) {
        return new OrderDocument(
            id, tenantId, externalRef, newRef, createdAt);
    }
}
```

Trong ví dụ:

- `id` là khóa có giá trị cố định do ứng dụng cung cấp, chẳng hạn `"ORD-101"`. Chọn ID không có hình dạng ObjectId để tránh nhầm mapping `String`/`ObjectId` trong bài.
- `tenantId` dùng cho phân vùng nghiệp vụ và phân quyền ở service.
- `externalRef` là tham chiếu như `" web-014 "` do hệ thống ngoài gửi.
- `normalizedRef` là giá trị chuẩn hóa dùng để tìm kiếm/đối soát, ví dụ `"WEB-014"`.
- `createdAt` là dấu thời gian được tạo trước khi ghi, dạng `Instant` được map theo converter.

Không có `setNormalizedRef(...)`; lệnh `withNormalizedRef` trả **bản sao mới** với bốn thuộc tính còn lại được giữ nguyên. Đây là pattern copy-on-write. Đối tượng gốc không đổi, và **caller phải sử dụng giá trị trả về** nếu muốn thấy thay đổi.

```java
OrderDocument original = new OrderDocument(
    "ORD-101",
    "TENANT-A",
    " web-014 ",
    null,
    Instant.parse("2026-11-20T02:00:00Z"));

OrderDocument changed = original.withNormalizedRef("WEB-014");

assert original.normalizedRef() == null;
assert changed.normalizedRef().equals("WEB-014");
assert original != changed;
```

Các lệnh `assert` này minh họa ngữ nghĩa Java và cần bật assertions khi chạy; trong JUnit thực tế dùng AssertJ/JUnit assertions.

### 2.1. Immutable không đồng nghĩa mọi trường đều không thể có giá trị do store sinh

Spring Data có thể tạo một instance mới qua constructor/copy/wither khi cần gán trường bất biến trong những đường mapping hỗ trợ. Tuy vậy, không nên giả định **đối tượng đầu vào ban đầu** sẽ bị mutate khi database cấp ID/version.

Với bài học, chúng ta chủ động dùng `id` cố định và `createdAt` có sẵn để cô lập hành vi callback. Khi triển khai auto-generated ID hoặc `@Version`, phải kiểm thử **instance được trả về**, giá trị được lưu và strategy mapping của phiên bản Spring Data đang sử dụng.

## 3. Luồng xử lý: khác biệt giữa Entity và BSON Document

Lưu một entity kiểu domain qua `MongoTemplate.insert/save` có thể hình dung:

```text
OrderDocument original (immutable)
        |
        v
BeforeConvertCallback<T>
        |  returns OrderDocument E1
        v
MappingMongoConverter
        |  maps E1 -> org.bson.Document D1
        v
BeforeSaveCallback<T>
        |  can change D1 (BSON to write)
        |  returns entity E2 (does NOT remap E2 to D1)
        v
MongoDB write(D1)
        |
        v
AfterSaveCallback<T>
        |  returns entity E3 to caller
        v
Template/repository save result

Read path:
MongoDB Document -> converter creates entity
        -> AfterConvertCallback<T>
        -> caller receives returned entity
```

Đây là sơ đồ **logic checkpoint**; còn có sự kiện mapping, auditing, ID generation/version handling và transaction/session tùy cấu hình/operation.

### 3.1. Bảng quyết định cực quan trọng

| Callback MongoDB | Signature imperative | Dữ liệu đã map thành BSON chưa? | Nếu trả entity mới, ảnh hưởng gì? |
| --- | --- | --- | --- |
| `BeforeConvertCallback<T>` | `T onBeforeConvert(T entity, String collection)` | **Chưa** | Entity mới được converter dùng làm nguồn cho BSON |
| `BeforeSaveCallback<T>` | `T onBeforeSave(T entity, Document doc, String collection)` | **Rồi** | Entity trả về có thể được đưa tiếp trong chain, nhưng **chỉ thay đổi `doc` mới đổi BSON ghi** |
| `AfterSaveCallback<T>` | `T onAfterSave(T entity, Document doc, String collection)` | **Đã ghi** | Entity trả về có thể là kết quả Java của save; **không tự ghi lại** |
| `AfterConvertCallback<T>` | `T onAfterConvert(T entity, Document doc, String collection)` | **Đang đọc, đã convert** | Caller nhận entity được thay thế, **không tự update DB** |

**Quy tắc nhớ nhanh:** Muốn chuẩn hóa **field persistent** của immutable entity trước khi lưu → `BeforeConvertCallback`. Muốn sửa chính BSON đã tạo → `BeforeSaveCallback` với `org.bson.Document`. Muốn làm giàu đối tượng trả về sau ghi/đọc → `AfterSave` hoặc `AfterConvert`, nhưng phải hiểu sự khác biệt giữa trạng thái trong JVM và trạng thái MongoDB.

### 3.2. Phân biệt với ApplicationEvent listener

MongoDB cũng có `BeforeConvertEvent`, `BeforeSaveEvent`, `AfterSaveEvent`, `AfterConvertEvent` qua `AbstractMongoEventListener`. Events phù hợp cho quan sát/tích hợp với event infrastructure, nhưng:

- Event listener mang tính phát sự kiện, thường **không có hợp đồng trả một entity khác để tiếp tục xử lý** giống `EntityCallback<T>`.
- Event multicaster có thể cấu hình xử lý bất đồng bộ; thứ tự và thời điểm event listener hoàn tất có thể khó dự đoán.
- Entity callback được Spring Data tích hợp trực tiếp tại checkpoint và có thể **trả object mới** hoặc Publisher phát object mới.
- Không nên vừa dùng event listener mutate entity vừa dùng callback copy-on-write cho cùng field mà không có quy tắc ordering/ownership.

Với immutable domain model, **ưu tiên EntityCallback khi cần sửa dữ liệu trong vòng đời persistence**. Dùng event listener cho mục đích khác nếu hiểu rõ giới hạn, thay vì coi hai cơ chế tương đương. Xem tài liệu Spring Data Commons và MongoDB ở cuối bài.

## 4. BeforeConvertCallback: trả immutable entity mới trước khi map BSON

Đây là checkpoint tự nhiên để tính `normalizedRef` từ `externalRef`:

File `NormalizeOrderRefCallback.java`:

```java
package com.example.shop.orders;

import java.util.Locale;
import org.springframework.core.annotation.Order;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
@Order(200)
public final class NormalizeOrderRefCallback
        implements BeforeConvertCallback<OrderDocument> {

    @Override
    public OrderDocument onBeforeConvert(
            OrderDocument entity, String collection) {

        if (entity.externalRef() == null
                || entity.externalRef().isBlank()) {
            throw new IllegalArgumentException(
                "externalRef không được bỏ trống");
        }

        String normalized = entity.externalRef()
            .trim()
            .toUpperCase(Locale.ROOT);

        if (normalized.equals(entity.normalizedRef())) {
            return entity; // Không tạo bản sao nếu đã chuẩn.
        }

        // Immutable: tạo instance mới, KHÔNG sửa entity cũ.
        return entity.withNormalizedRef(normalized);
    }
}
```

Lưu ý `@Order(200)` chỉ minh họa thứ tự ưu tiên khi có nhiều callbacks cùng pha. Một số callbacks tích hợp (ví dụ auditing) cũng có order riêng; cần cân nhắc khi callback cùng sửa trường. Không coi `@Order(200)` là yêu cầu cứng của Spring Data.

### 4.1. Vì sao phải return bản copy?

Phản ví dụ:

```java
@Override
public OrderDocument onBeforeConvert(
        OrderDocument entity, String collection) {
    entity.withNormalizedRef("WEB-014");
    return entity; // SAI: bỏ giá trị copy vừa tạo.
}
```

`withNormalizedRef(...)` trả object mới nhưng code trên **bỏ đi** object đó. Converter nhận lại bản gốc, `normalizedRef` vẫn null.

Đúng:

```java
return entity.withNormalizedRef("WEB-014");
```

Đây không chỉ là style. **Hợp đồng return value là cách chuyển trạng thái mới xuyên qua lifecycle**.

### 4.2. Callback có thể trả chính object cũ nếu không cần thay đổi

Một callback không bắt buộc tạo instance mới ở mọi lần gọi. Nếu `normalizedRef` đã là `"WEB-014"`, trả `entity` cũ giúp tiết kiệm allocation và làm logic idempotent:

```java
if (normalized.equals(entity.normalizedRef())) {
    return entity;
}
return entity.withNormalizedRef(normalized);
```

Khi service `save(...)` nhiều lần hoặc callback chain lặp qua các operation khác nhau, một phép chuẩn hóa **ổn định** sẽ dễ debug hơn phép sinh giá trị ngẫu nhiên mỗi lần callback được gọi.

### 4.3. Caller và object original không đồng nhất

```java
OrderDocument original = new OrderDocument(
    "ORD-101", "TENANT-A", " web-014 ", null,
    Instant.parse("2026-11-20T02:00:00Z"));

OrderDocument persisted = template.insert(original);

// Callback đã tạo bản sao mới để lưu.
assert original.normalizedRef() == null;
assert persisted.normalizedRef().equals("WEB-014");
```

Đoạn này giả định `template` là `MongoTemplate` đã inject và callback đã đăng ký. Để xác minh persistence, **cần đọc raw BSON**, không chỉ assert `persisted`. `insert/save` và các bước callback/version/ID của từng phiên bản có thể tác động tới entity trả về; ví dụ này dùng ID có sẵn để tránh nhánh auto-ID.

### 4.4. Không đưa tác vụ external I/O vào BeforeConvert

Callback nên đơn giản, có tính xác định và hiệu năng phù hợp. Nếu lúc lưu một order, callback gọi HTTP tra tỷ giá hoặc gửi email, thao tác ấy có thể lặp khi caller retry, chậm hoặc fail không đúng ranh giới giao dịch. Với dữ liệu cần truy xuất ngoài MongoDB, ưu tiên xử lý ở service/workflow có timeout, cache, policy và outbox rõ ràng.

## 5. BeforeSaveCallback: BSON đã được tạo — return entity mới chưa đủ

Sau `BeforeConvertCallback`, `MappingMongoConverter` đã chuyển entity thành `org.bson.Document`. Lúc này Spring Data gọi `BeforeSaveCallback`:

```java
public interface BeforeSaveCallback<T> {
    T onBeforeSave(
        T entity,
        org.bson.Document document,
        String collection);
}
```

Đây là phần signature liên quan, không phải interface đầy đủ để ứng dụng tự định nghĩa. Điểm quan trọng được Spring Data MongoDB ghi rõ: **chỉ những thay đổi trên `Document` mới được dùng cho lần ghi đang diễn ra**. Callback có thể trả một entity khác, nhưng converter **không tự chạy lại** trên entity mới này.

### 5.1. Đúng: bổ sung field trực tiếp vào Document

Ví dụ một trường dữ liệu kỹ thuật `schemaVersion` luôn phải là số nguyên 2 khi ghi:

File `SchemaVersionBeforeSaveCallback.java`:

```java
package com.example.shop.orders;

import org.bson.Document;
import org.springframework.core.annotation.Order;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;
import org.springframework.stereotype.Component;

@Component
@Order(400)
public final class SchemaVersionBeforeSaveCallback
        implements BeforeSaveCallback<OrderDocument> {

    @Override
    public OrderDocument onBeforeSave(
            OrderDocument entity,
            Document document,
            String collection) {

        // BSON đã được map từ entity ở checkpoint trước.
        document.put("schemaVersion", 2);

        // Không cần biến đổi Java object cho field
        // chỉ tồn tại ở lớp lưu trữ.
        return entity;
    }
}
```

Kết quả của một lần insert:

```javascript
{
  _id: "ORD-101",
  tenantId: "TENANT-A",
  externalRef: " web-014 ",
  normalizedRef: "WEB-014",
  createdAt: ISODate("2026-11-20T02:00:00Z"),
  schemaVersion: 2
}
```

Trong ví dụ `schemaVersion` là trường BSON kỹ thuật chưa được ánh xạ vào record. Khi đọc lại `OrderDocument`, converter có thể bỏ qua trường này nếu không có property tương ứng. Nếu nghiệp vụ cần thấy `schemaVersion` trong domain entity, nên cân nhắc thêm nó vào model và cập nhật bằng `BeforeConvertCallback`, không phụ thuộc vào một trường “ẩn” khó phát hiện.

Tùy cấu hình type mapping, BSON thực tế còn có thể có field kỹ thuật `_class` của Spring Data; ví dụ trên chỉ liệt kê những field cần quan sát. Không bật `additionalProperties:false` trong MongoDB validator khi chưa tính đến các field framework thực sự ghi.

### 5.2. Sai: return một entity khác nhưng không sửa Document

```java
// PHẢN VÍ DỤ: callback sai về mục tiêu ghi BSON.
public OrderDocument onBeforeSave(
        OrderDocument entity,
        Document document,
        String collection) {

    return new OrderDocument(
        entity.id(),
        entity.tenantId(),
        "REF-REPLACED",
        entity.normalizedRef(),
        entity.createdAt());
}
```

Đoạn code trả về entity có `externalRef="REF-REPLACED"` nhưng **Document đã được map trước đó** vẫn giữ giá trị `externalRef` cũ, nếu callback không sửa `document`. Kết quả có thể gây nhầm lẫn giữa entity Java ở một số bước sau và dữ liệu đã được ghi.

Muốn thay đổi **persistent property** ở cấp entity, chuyển logic lên `BeforeConvertCallback`. Nếu thật sự muốn can thiệp vào BSON:

```java
public OrderDocument onBeforeSave(
        OrderDocument entity,
        Document document,
        String collection) {

    document.put("externalRef", "REF-REPLACED");
    return entity;
}
```

Nhưng hãy lưu ý: callback vừa sửa BSON có thể tạo sự **không đồng nhất** giữa object Java được trả về và dữ liệu MongoDB. Với những thuộc tính domain quan trọng, thường tốt hơn là tính trước convert và dùng một contract đồng nhất.

### 5.3. Đừng sửa tùy tiện _id, version hoặc tên field đã được ánh xạ

Ở `BeforeSaveCallback`, `Document` chứa **tên BSON**, không nhất thiết giống tên field Java nếu entity dùng `@Field("...")`. Việc ghi trực tiếp `document.put("foo", ...)` mà không biết tên field thực tế có thể tạo field mới sai schema.

Tương tự, đừng tùy tiện thay `_id` hoặc `version` ở checkpoint này. ID/version có quan hệ với phương thức `save`/`insert`, optimistic locking, khả năng nhận diện entity mới và điều kiện cập nhật. Nếu thay BSON nhưng không đồng bộ metadata/converter, có thể phát sinh lỗi khó phát hiện. Cần mô hình định danh/version rõ ràng và test trên MongoDB thật.

## 6. AfterSaveCallback: thay object trả về không có nghĩa ghi thêm lần nữa

`AfterSaveCallback<T>` chạy khi thao tác lưu đã đi qua bước ghi liên quan. Nó nhận entity và BSON `Document`, rồi có thể trả lại **entity khác** để dùng làm kết quả của đường save:

```java
package com.example.shop.orders;

import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveCallback;

public final class ReturnNormalizedAfterSaveCallback
        implements AfterSaveCallback<OrderDocument> {

    @Override
    public OrderDocument onAfterSave(
            OrderDocument entity,
            Document document,
            String collection) {

        // Ví dụ GIẢNG DẠY: trả một immutable copy khác.
        return new OrderDocument(
            entity.id(),
            entity.tenantId(),
            entity.externalRef().trim(),
            entity.normalizedRef(),
            entity.createdAt());
    }
}
```

Ở đây ta cố tình **không gắn `@Component`** để tránh âm thầm biến đổi kết quả của mọi save trong ví dụ production.

Nếu bản ghi `externalRef` đã được lưu là `" web-014 "`, callback này có thể trả object Java với `externalRef="web-014"`. Nó **không thực hiện một write mới**, vì vậy MongoDB vẫn lưu chuỗi ban đầu. Nếu caller về sau `save(...)` object đã được làm sạch đó, dữ liệu có thể đổi ở một lần ghi **khác**.

Đây là ví dụ để hiểu hợp đồng trả về, **không phải khuyến nghị biến đổi field persistent sau save**. Trong ứng dụng thật:

- Dùng `BeforeConvertCallback` nếu field lưu trữ phải được chuẩn hóa.
- Dùng một DTO/view riêng nếu UI muốn định dạng cách hiển thị.
- Tránh làm cho API trả một entity giống hệt model MongoDB nhưng âm thầm khác BSON khi gọi lại.

### 6.1. AfterSave không phải cơ chế “after commit”

Một điểm quan trọng về transaction: **`AfterSaveCallback` không phải callback “transaction đã commit bền vững”**. Nó xảy ra trong vòng đời thao tác save. Nếu `save(...)` nằm trong transaction nhiều thao tác, transaction vẫn có thể rollback ở bước sau hoặc commit lỗi.

Không phát email, gọi payment API, gửi Kafka message không idempotent ngay trong `AfterSaveCallback` rồi cho rằng DB đã commit chắc chắn. Với side effect bền vững, dùng outbox được ghi cùng transaction và dispatcher chạy sau commit; hoặc cơ chế after-commit có giới hạn được thiết kế riêng.

## 7. AfterConvertCallback: biến đổi entity khi đọc mà không cập nhật DB

Giả sử một document legacy thiếu `normalizedRef`. Ta muốn caller đọc được dạng chuẩn hóa trong giai đoạn migration nhưng không muốn đọc lại đồng nghĩa ghi DB:

File `LegacyRefAfterConvertCallback.java`:

```java
package com.example.shop.orders;

import java.util.Locale;
import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterConvertCallback;
import org.springframework.stereotype.Component;

@Component
public final class LegacyRefAfterConvertCallback
        implements AfterConvertCallback<OrderDocument> {

    @Override
    public OrderDocument onAfterConvert(
            OrderDocument entity,
            Document document,
            String collection) {

        if (entity.normalizedRef() != null
                || entity.externalRef() == null) {
            return entity;
        }

        String calculated = entity.externalRef()
            .trim()
            .toUpperCase(Locale.ROOT);

        return entity.withNormalizedRef(calculated);
    }
}
```

Điều xảy ra:

```text
MongoDB document:
  { externalRef: " web-014 " }  (không có normalizedRef)
             |
             v
MappingMongoConverter -> OrderDocument(normalizedRef=null)
             |
             v
AfterConvertCallback -> NEW OrderDocument(normalizedRef="WEB-014")
             |
             v
Caller nhận normalizedRef="WEB-014"

MongoDB vẫn thiếu normalizedRef cho đến khi có một write thực sự.
```

### 7.1. “Đọc trả giá trị đã chuẩn” chưa chứng minh dữ liệu đã được migration

`AfterConvertCallback` có thể khiến một integration test chỉ gọi repository `findById` trông như dữ liệu đã đủ field. Vì thế nếu cần kiểm tra **migration ở MongoDB**, phải đọc raw `org.bson.Document` hoặc query schema thật.

Một callback kiểu này là biện pháp **tương thích dữ liệu đọc**, không thay thế migration. Nếu người dùng đọc rồi save chính object đã được tính toán, lần save tiếp theo có thể ghi `normalizedRef`; đó là một write mới, không phải side effect của read.

### 7.2. Không dùng AfterConvert để triển khai bảo mật đa tenant

Nếu một document chưa được phép đọc, callback chạy **sau khi dữ liệu đã được lấy và map** thì quá muộn để thay thế filter phân quyền. Tenant-scoped query, authorization và projection phải được thực hiện **trước/trong truy vấn**. Không dựa vào callback để che field nhạy cảm trong mọi đường đọc hoặc làm ranh giới bảo mật chính.

## 8. Bốn checkpoint trong một ca end-to-end

Sử dụng các callback `NormalizeOrderRefCallback`, `SchemaVersionBeforeSaveCallback` và `LegacyRefAfterConvertCallback` đã đăng ký:

| Bước | Input/Output | Bản nào bị thay đổi? |
| --- | --- | --- |
| Caller tạo `original` | `externalRef=" web-014 "`, `normalizedRef=null` | Object gốc |
| `BeforeConvert` | Trả copy có `normalizedRef="WEB-014"` | **Entity được converter dùng** |
| Converter | Tạo BSON có `normalizedRef="WEB-014"` | `Document` mới |
| `BeforeSave` | Thêm `schemaVersion:2` vào BSON | **Document được ghi** |
| MongoDB write | Lưu BSON với hai giá trị trên | Database |
| `AfterSave` (không cài biến thể demo) | Trả entity từ đường save | Object Java của caller |
| Find/read | Load BSON rồi map thành record | Object Java mới |
| `AfterConvert` | Chỉ tính normalized nếu legacy thiếu | **Object Java trả về**, không ghi lại |

**Đặc biệt:** một callback có thể trả **cùng instance** nếu không có gì cần thay đổi. Không mặc định mỗi checkpoint tạo bản sao; điều quan trọng là code sử dụng đúng instance được trả về khi thực sự có thay đổi.

## 9. Đăng ký EntityCallback và kiểm soát thứ tự

Spring Data tìm các `EntityCallback` beans đã đăng ký trong Spring `ApplicationContext` rồi tích hợp với đường mapping tương ứng. Có hai cách phổ biến:

### 9.1. @Component có type rõ ràng

```java
@Component
public final class NormalizeOrderRefCallback
        implements BeforeConvertCallback<OrderDocument> {
    @Override
    public OrderDocument onBeforeConvert(
            OrderDocument entity, String collection) {
        return entity; // Chỉ minh họa chữ ký và đăng ký bean.
    }
}
```

Code trên là **lược đồ**, không thay thế phiên bản đầy đủ ở mục 4. Việc khai báo `BeforeConvertCallback<OrderDocument>` cho biết loại domain, để Spring Data định tuyến callback cho entity phù hợp.

### 9.2. @Bean trong @Configuration

Không muốn dùng component scanning, có thể định nghĩa bean tường minh:

```java
package com.example.shop.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;

@Configuration(proxyBeanMethods = false)
public class OrderCallbackConfiguration {

    @Bean
    BeforeConvertCallback<OrderDocument> orderRefCallback() {
        return (entity, collection) -> {
            if (entity.externalRef() == null) {
                throw new IllegalArgumentException(
                    "Thiếu externalRef");
            }
            String value = entity.externalRef()
                .trim()
                .toUpperCase(java.util.Locale.ROOT);
            return entity.withNormalizedRef(value);
        };
    }
}
```

**Không đăng ký bean này cùng lúc với `NormalizeOrderRefCallback` ở mục 4** nếu muốn đúng một callback chuẩn hóa: cả hai cùng được gọi và sẽ tạo cấu hình trùng lặp không cần thiết. Hai ví dụ thể hiện **hai lựa chọn đăng ký**, không phải hai bước phải thực hiện đồng thời.

### 9.3. Lambda callback và type filtering

Lựa chọn `@Bean` trả generic `BeforeConvertCallback<OrderDocument>` giúp code ngắn, nhưng các tài liệu Spring Data lưu ý: lambda object có thể không phơi bày đủ generic type ở runtime cho bộ lọc type tối ưu trong mọi trường hợp. Với hệ thống nhiều entity/callback, **class implements interface có generic cụ thể** thường dễ quan sát và tối ưu filtering hơn.

Không viết callback dạng `BeforeConvertCallback<Object>` rồi kiểm tra `instanceof` hàng chục loại entity, trừ khi thật sự có use case toàn cục và test đủ đường mapping. Một callback quá rộng có thể làm chậm mỗi lệnh insert/save.

### 9.4. Thứ tự các callbacks

Một entity có thể có nhiều `BeforeConvertCallback<OrderDocument>`:

```text
Callback A  @Order(50)   -> entity E1
Callback B  @Order(200)  -> entity E2
Callback C  (default)    -> entity E3
Converter              -> Document from E3
```

Thông thường giá trị thứ tự **nhỏ hơn được ưu tiên chạy trước**. Các callback cùng phase được áp lần lượt; callback sau nhận entity mà callback trước trả về.

Ví dụ:

```java
@Component
@Order(50)
public final class ValidateTenantCallback
        implements BeforeConvertCallback<OrderDocument> {
    @Override
    public OrderDocument onBeforeConvert(
            OrderDocument entity, String collection) {
        if (entity.tenantId() == null
                || entity.tenantId().isBlank()) {
            throw new IllegalArgumentException(
                "tenantId bắt buộc");
        }
        return entity;
    }
}
```

Callback validation này có thể chạy trước normalization `@Order(200)`. Tuy nhiên, cùng một luật validation cần được đặt có chủ đích: nếu một callback sửa field rồi callback khác kiểm tra field ấy, thứ tự nên phản ánh **kiểm tra trước hay sau khi chuẩn hóa**.

### 9.5. Tránh phụ thuộc vào thứ tự không được khai báo

Nếu hai callback cùng áp vào `normalizedRef` mà không có `@Order` hoặc `Ordered` rõ ràng, thứ tự thực tế có thể khó suy luận hoặc đổi theo cấu hình. Đừng dựa vào tên bean hay thứ tự class file trong package. Càng tốt hơn là **chỉ có một nơi sở hữu một invariant**, hoặc gom các bước phụ thuộc chặt thành một callback duy nhất.

## 10. Auditing và entity bất biến

Spring Data MongoDB hỗ trợ auditing, ví dụ `@CreatedDate` và `@LastModifiedDate`. Auditing được tích hợp thông qua các entity callbacks trước convert. Điều này liên quan trực tiếp tới các object không có setter:

- Auditing có thể cần điền timestamp hoặc user.
- Một entity bất biến không thể được sửa như bean mutable.
- Mapping/auditing infrastructure phải tạo **instance mới hoặc dùng cơ chế property accessor tương thích**.
- Caller nên dùng **entity được save trả về**, không mong original đã bị mutate.

### 10.1. Ví dụ model với @CreatedDate

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("audited_orders")
public record AuditedOrder(
    @Id String id,
    String tenantId,
    String externalRef,
    @CreatedDate Instant createdAt,
    @LastModifiedDate Instant updatedAt
) {}
```

Khi bật auditing theo cấu hình Spring Data MongoDB phù hợp (chẳng hạn `@EnableMongoAuditing` cho imperative, hoặc `@EnableReactiveMongoAuditing` cho reactive nếu phiên bản hỗ trợ), auditing có thể điền các field đúng checkpoint. **Không** chỉ thêm annotation và khẳng định timestamps sẽ được gán khi auditing chưa được cấu hình.

### 10.2. Tránh callback tự cập nhật cùng field auditing

Phản thiết kế:

```java
// Cùng một createdAt bị thay ở nhiều nơi:
// 1) @CreatedDate của AuditingEntityCallback
// 2) custom BeforeConvertCallback tự đặt Instant.now()
// 3) MongoDB trigger bên ngoài còn thay tiếp
```

Nếu auditing đảm nhiệm `createdAt/updatedAt`, không nên viết một callback khác tùy tiện gán những field đó trong mỗi lần save. Với entity bất biến, copy từ callback sau có thể vô tình **ghi đè** những giá trị mà auditing vừa cập nhật khi dùng bản snapshot cũ.

Một chiến lược:

- Để auditing sở hữu các trường audit chuẩn.
- Để callback nghiệp vụ chỉ xử lý field riêng như `normalizedRef`.
- Nếu các callbacks phụ thuộc thứ tự, đặt `@Order` tường minh và test cả insert/update.
- Với thời gian nghiệp vụ cần tính theo request, truyền từ service theo hợp đồng; không lạm dụng `Instant.now()` ở mọi callback.

### 10.3. Order của AuditingEntityCallback

Tài liệu Spring Data MongoDB có bảng thứ tự callback; auditing mặc định thường được đăng ký với thứ tự riêng (ví dụ `100` trong những phiên bản có bảng này), còn callback tùy chỉnh mặc định là mức ưu tiên thấp. Số thứ tự chỉ có ý nghĩa **khi cùng loại callback checkpoint**; không dùng nó để đảo `BeforeSave` lên trước `BeforeConvert`.

Khi upgrade Spring Data, xem chính bảng lifecycle callbacks của version dự án thay vì trông cậy một thứ tự ngầm được ghi nhớ từ phiên bản khác.

## 11. Immutable @Id và @Version: callback không phải nơi thay mọi store-managed field

Spring Data có những quy tắc riêng khi xử lý:

- `@Id`: nhận diện document; driver/converter có thể tạo ID ở insert nếu entity chưa có ID.
- `@Version`: optimistic locking/version field; save/update có thể dùng điều kiện version và tăng giá trị.
- `@CreatedDate`, `@LastModifiedDate`: auditing.

Với immutable entity, những giá trị này phải được biểu diễn bằng instance/constructor/wither phù hợp. Không nên vừa để framework quản lý vừa tự can thiệp trực tiếp vào `_id`/version ở `BeforeSaveCallback`.

### 11.1. ID ban đầu null: cần hiểu ai sở hữu ID

Ví dụ khác:

```java
@Document("notes")
public record NoteDocument(
    @Id String id,
    String tenantId,
    String body
) {}
```

Khi insert `NoteDocument(null, "TENANT-A", "hello")`, MongoDB/Spring Data có thể cấp identifier tùy mapping/driver/version. Với entity bất biến, bản gốc không có setter để tự nhận ID. Hãy xem kết quả `insert(...)` và đọc lại BSON để xác nhận:

```java
NoteDocument original = new NoteDocument(
    null, "TENANT-A", "hello");

NoteDocument saved = template.insert(original);

// Kiểm chứng phiên bản đang dùng:
assert saved.id() != null;
// KHÔNG mặc định assert original.id() != null.
```

Trên một số kiểu immutable mapping, cần constructor/wither thích hợp để Spring Data có thể tạo instance mới khi gán property. Với ID String có thể được map thành BSON ObjectId nếu phù hợp hình dạng, cần dùng strategy rõ khi dự án yêu cầu String canonical.

### 11.2. Không biến BeforeConvert thành máy tăng version

Giả sử entity có `@Version Long version`. Nếu callback cứ chạy:

```java
// PHẢN VÍ DỤ: tự tăng version tại BeforeConvert.
return new OrderWithVersion(
    entity.id(), entity.version() + 1, /* ... */);
```

trong khi Spring Data cũng xử lý version, điều kiện optimistic locking có thể sai hoặc cập nhật bị từ chối. `OrderWithVersion` ở đây là kiểu giả định để minh họa anti-pattern, không phải class đầy đủ.

Nếu cần optimistic locking, dùng cơ chế `@Version`/conditional update phù hợp và test update cạnh tranh; không tự sửa giá trị store-managed ở callback mà không nắm rõ trình tự persistence.

### 11.3. Tương tác giữa immutable copy và @Version khi save

Khi copy entity, phải giữ nguyên `id/version` của phiên bản hiện tại, trừ khi thật sự muốn tạo một aggregate mới. Nếu vô tình tạo copy có `id=null`, `save(...)` có thể thành insert document mới; nếu version bị thay sai, optimistic locking có thể báo conflict.

Trong các method `with...` của immutable entity, luôn copy **tất cả thuộc tính cần giữ**. Nếu thêm field mới vào record constructor, compiler buộc sửa constructor call có thể giúp phát hiện một số chỗ cần cập nhật; với builder tùy ý, cần có test để tránh mất dữ liệu.

## 12. Callback không chạy cho mọi thao tác MongoDB

`EntityCallback` gắn với những checkpoint mà Spring Data **convert entity** trong các đường template/repository được hỗ trợ. Điều đó **khác với** mọi lệnh ghi MongoDB bất kỳ.

### 12.1. Insert/save qua MongoTemplate hoặc repository

```java
OrderDocument saved = template.insert(order);
OrderDocument savedAgain = repository.save(saved);
```

Trong cấu hình callback đang hoạt động, các operation kiểu lưu entity này đi qua lifecycle có liên quan. Kiểm tra hành vi cụ thể khi sử dụng `insertAll`, entity inheritance hoặc tùy chọn template đặc thù ở phiên bản dự án.

### 12.2. updateFirst/updateMulti không tự tạo OrderDocument

```java
template.updateFirst(
    Query.query(Criteria.where("_id").is("ORD-101")),
    new Update().set("externalRef", " new-ref "),
    OrderDocument.class);
```

Đây là **update theo field**, không phải “load một `OrderDocument` → chạy BeforeConvert → map rồi save”. Vì vậy **không được giả định** `NormalizeOrderRefCallback` sẽ tính lại `normalizedRef` sau lệnh trên.

Nếu code cập nhật trực tiếp `externalRef`, có thể:

- Cập nhật `externalRef` và `normalizedRef` cùng trong một atomic update.
- Dùng aggregation update pipeline khi phù hợp.
- Đặt logic chuẩn hóa ở service và dùng chung helper với callback.
- Thiết kế schema/read model sao cho invariant được bảo vệ bằng cơ chế phù hợp hơn.

### 12.3. BulkOperations, raw driver và script không tự kích hoạt entity callback

```java
template.getCollection("orders").updateOne(
    new Document("_id", "ORD-101"),
    new Document("$set",
        new Document("externalRef", " raw-from-driver ")));
```

Đây là API driver trực tiếp. Nó không đi qua converter/callback của entity Spring Data. Tương tự, lệnh từ `mongosh` hoặc service sử dụng một driver khác không biết custom Spring beans.

**Kết luận:** callback là một lớp nhất quán **trên đường Spring Data mapping**, không phải database constraint áp cho mọi writer. Nếu normalizedRef phải luôn tương ứng externalRef bất kể nguồn ghi, cần hợp đồng cho tất cả writers, migration/validation hoặc thiết kế lưu trữ/query thích hợp.

### 12.4. Aggregation projections và nested objects

Không mặc định một `@Aggregation` trả DTO, projection interface hay một subdocument được map theo mọi checkpoint như root entity. Tài liệu Spring Data MongoDB nêu lifecycle events áp cho **root-level types**, và các callback kiểu entity gắn với các đường mapped entity tương ứng.

Nếu yêu cầu callback phải chạy với kết quả aggregate/projection, hãy viết integration test cụ thể của loại return type, converter và method repository đang dùng. Không dựa trên một test `findById(OrderDocument.class)` để khẳng định mọi aggregation đều qua `AfterConvertCallback<OrderDocument>`.

## 13. Callback reactive: trả Publisher phát entity mới

Spring Data tách các interfaces sync và reactive. Với `ReactiveMongoTemplate` hoặc `ReactiveMongoRepository`, các callbacks phù hợp thường có tiền tố `Reactive...` và trả `org.reactivestreams.Publisher<T>`:

| Imperative | Reactive tương ứng |
| --- | --- |
| `BeforeConvertCallback<T>` → `T` | `ReactiveBeforeConvertCallback<T>` → `Publisher<T>` |
| `BeforeSaveCallback<T>` → `T` | `ReactiveBeforeSaveCallback<T>` → `Publisher<T>` |
| `AfterSaveCallback<T>` → `T` | `ReactiveAfterSaveCallback<T>` → `Publisher<T>` |
| `AfterConvertCallback<T>` → `T` | `ReactiveAfterConvertCallback<T>` → `Publisher<T>` |

Thao tác reactive cần có subscription. Callback reactive nên phát đúng **một entity hợp lệ** qua Publisher để Spring Data có thể tiếp tục lifecycle. Trả `Mono.empty()`, `null` hoặc Publisher không bao giờ complete không phải cách “bỏ qua callback” an toàn; hãy trả `Mono.just(entity)` khi không cần thay đổi.

### 13.1. ReactiveBeforeConvertCallback với Java record

File `ReactiveNormalizeOrderRefCallback.java`:

```java
package com.example.shop.orders;

import java.util.Locale;
import org.reactivestreams.Publisher;
import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public final class ReactiveNormalizeOrderRefCallback
        implements ReactiveBeforeConvertCallback<OrderDocument> {

    @Override
    public Publisher<OrderDocument> onBeforeConvert(
            OrderDocument entity, String collection) {

        return Mono.fromSupplier(() -> {
            if (entity.externalRef() == null
                    || entity.externalRef().isBlank()) {
                throw new IllegalArgumentException(
                    "externalRef không hợp lệ");
            }

            String value = entity.externalRef()
                .trim()
                .toUpperCase(Locale.ROOT);

            return value.equals(entity.normalizedRef())
                ? entity
                : entity.withNormalizedRef(value);
        });
    }
}
```

Ví dụ dùng import đầy đủ của API reactive. Callback reactive không chặn luồng và không cần `block()`.

### 13.2. ReactiveBeforeSaveCallback: sửa Document bên trong Publisher

```java
package com.example.shop.orders;

import org.bson.Document;
import org.reactivestreams.Publisher;
import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeSaveCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public final class ReactiveSchemaVersionCallback
        implements ReactiveBeforeSaveCallback<OrderDocument> {

    @Override
    public Publisher<OrderDocument> onBeforeSave(
            OrderDocument entity,
            Document document,
            String collection) {

        return Mono.fromSupplier(() -> {
            document.put("schemaVersion", 2);
            return entity;
        });
    }
}
```

`document` ở đây vẫn là BSON đã được converter tạo ra. Kết quả Publisher là entity được tiếp tục xử lý; việc cập nhật dữ liệu ghi nằm ở `document.put(...)`, **không** ở `Mono.just(entity.with...())` sau khi đã convert.

### 13.3. Không trộn sync callback và reactive callback như thể chúng là một chain

Spring Data Commons tách callback theo API type: đường imperative xem xét synchronous callbacks; đường reactive xem xét reactive callbacks. Vì vậy, nếu cùng một collection được ghi qua cả `MongoTemplate` và `ReactiveMongoTemplate`, cần:

1. Cấu hình mỗi nhóm callback phù hợp với đường API thật.
2. Dùng chung một **hàm thuần** tính normalizedRef để tránh hai thuật toán lệch nhau.
3. Viết test cho cả hai template/repository nếu cả hai cùng được sử dụng.
4. Không tự giả định bean `BeforeConvertCallback<OrderDocument>` sẽ áp cho mọi insert reactive.

### 13.4. ReactiveAfterConvertCallback và immutable copy

```java
package com.example.shop.orders;

import java.util.Locale;
import org.bson.Document;
import org.reactivestreams.Publisher;
import org.springframework.data.mongodb.core.mapping.event.ReactiveAfterConvertCallback;
import reactor.core.publisher.Mono;

public final class ReactiveLegacyReadCallback
        implements ReactiveAfterConvertCallback<OrderDocument> {

    @Override
    public Publisher<OrderDocument> onAfterConvert(
            OrderDocument entity,
            Document document,
            String collection) {

        if (entity.normalizedRef() != null
                || entity.externalRef() == null) {
            return Mono.just(entity);
        }

        String normalized = entity.externalRef()
            .trim()
            .toUpperCase(Locale.ROOT);

        return Mono.just(entity.withNormalizedRef(normalized));
    }
}
```

Đây là class minh họa; nếu muốn Spring Data tự gọi callback, cần **đăng ký thành bean** (`@Component` hoặc `@Bean`). Nó chỉ thay object được trả về cho read, không tự cập nhật `normalizedRef` ở MongoDB.

### 13.5. Reactive callback không phải nơi cho blocking I/O

Một callback reactive gọi `RestTemplate`, JDBC blocking hoặc `Thread.sleep` trực tiếp có thể chiếm event-loop thread. Nếu buộc phải dùng một nguồn blocking, cần thiết kế riêng với scheduler/timeout, nhưng tốt hơn là **đưa logic đó ra khỏi callback** và giải quyết ở service/adapter có contract rõ.

Tương tự, `Mono.defer`/`Mono.fromSupplier` chưa có nghĩa “tự động an toàn khi retry”: Publisher có thể được subscribe lại và callback có thể chạy nhiều lần. Không dùng callback tạo một operation ID ngẫu nhiên mới mỗi lần cho một nghiệp vụ đã có idempotency key cố định.

## 14. Integration test: so sánh original, returned entity và raw BSON

Để chứng minh copy-on-write, unit test chỉ gọi `onBeforeConvert` là chưa đủ. Cần kiểm tra:

- **Original**: đối tượng immutable đầu vào không đổi.
- **Returned**: kết quả từ `MongoTemplate.insert(...)` đã đi qua callback.
- **Stored**: BSON `Document` thật chứa `normalizedRef` đã chuẩn hóa và `schemaVersion` được set ở `BeforeSave`.
- **Loaded**: `findById(...)` áp `AfterConvert` cho dữ liệu legacy nhưng không tự ghi ngược DB.
- **Direct update**: `updateFirst` có thể thay `externalRef` mà không tái chạy `BeforeConvert`.

### 14.1. Chuẩn bị JUnit 5 + @DataMongoTest

Với Spring Boot 3.x, có thể dùng `@DataMongoTest` và `@Import` để đăng ký đúng những callbacks cần kiểm tra. Test phải trỏ tới MongoDB/database **test cô lập**. Spring Boot ở major version khác có thể thay đổi package annotation/test slice; xác minh dependency đang sử dụng.

File `OrderCallbackIntegrationTest.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Date;
import java.util.UUID;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
@Import({
    NormalizeOrderRefCallback.class,
    SchemaVersionBeforeSaveCallback.class,
    LegacyRefAfterConvertCallback.class,
    ReturnNormalizedAfterSaveCallback.class
})
class OrderCallbackIntegrationTest {

    @Autowired
    MongoTemplate template;

    private static String newId() {
        return "ORD-" + UUID.randomUUID();
    }

    private static Query byId(String id) {
        return Query.query(Criteria.where("_id").is(id));
    }

    private Document raw(String id) {
        return template.getCollection("orders")
            .find(new Document("_id", id))
            .first();
    }

    private void cleanup(String id) {
        template.getCollection("orders")
            .deleteOne(new Document("_id", id));
    }

    @Test
    void beforeConvertUsesCopyAndBeforeSaveChangesBson() {
        String id = newId();

        OrderDocument original = new OrderDocument(
            id,
            "TENANT-TEST",
            " web-014 ",
            null,
            Instant.parse("2026-11-20T02:00:00Z"));

        try {
            OrderDocument returned = template.insert(original);

            // 1. Bản gốc vẫn immutable.
            assertThat(original.normalizedRef()).isNull();

            // 2. Callback đã trả copy cho đường save.
            assertThat(returned.normalizedRef())
                .isEqualTo("WEB-014");
            // AfterSave demo trả object với externalRef đã trim.
            assertThat(returned.externalRef())
                .isEqualTo("web-014");
            assertThat(original.externalRef())
                .isEqualTo(" web-014 ");

            // 3. MongoDB thực sự lưu giá trị đã chuẩn hóa.
            Document document = raw(id);
            assertThat(document).isNotNull();
            assertThat(document.getString("normalizedRef"))
                .isEqualTo("WEB-014");
            assertThat(document.getString("externalRef"))
                .isEqualTo(" web-014 ");
            assertThat(document.getInteger("schemaVersion"))
                .isEqualTo(2);
            assertThat(document.get("createdAt"))
                .isInstanceOf(Date.class);
        } finally {
            cleanup(id);
        }
    }

    @Test
    void afterConvertReplacesReturnedEntityNotStoredDocument() {
        String id = newId();

        Document legacy = new Document("_id", id)
            .append("tenantId", "TENANT-TEST")
            .append("externalRef", " old-007 ")
            .append("createdAt", Date.from(
                Instant.parse("2026-11-20T02:00:00Z")));

        try {
            // Raw driver bypasses Spring Data entity callbacks.
            template.getCollection("orders")
                .insertOne(legacy);

            OrderDocument loaded =
                template.findById(id, OrderDocument.class);

            assertThat(loaded).isNotNull();
            assertThat(loaded.normalizedRef())
                .isEqualTo("OLD-007");

            // Nhưng BSON nguồn vẫn không có field.
            assertThat(raw(id).containsKey("normalizedRef"))
                .isFalse();
        } finally {
            cleanup(id);
        }
    }

    @Test
    void directFieldUpdateDoesNotReRunBeforeConvert() {
        String id = newId();

        OrderDocument original = new OrderDocument(
            id,
            "TENANT-TEST",
            " web-014 ",
            null,
            Instant.parse("2026-11-20T02:00:00Z"));

        try {
            template.insert(original);

            template.updateFirst(
                byId(id),
                new Update().set("externalRef", " new-008 "),
                OrderDocument.class);

            Document document = raw(id);
            assertThat(document).isNotNull();
            assertThat(document.getString("externalRef"))
                .isEqualTo(" new-008 ");
            assertThat(document.getString("normalizedRef"))
                .isEqualTo("WEB-014");
        } finally {
            cleanup(id);
        }
    }
}
```

**An toàn test:** các test này chỉ nên chạy trên MongoDB TEST riêng. `cleanup(id)` chỉ xóa document có ID ngẫu nhiên được test tạo, không gọi `dropDatabase()` hay `deleteMany({})`. Nếu test setup khác dùng cùng collection, hãy cấu hình database riêng cho mỗi job để tránh va chạm.

### 14.2. Test cho riêng hợp đồng BeforeSave và AfterSave

Một unit test nhỏ minh họa rõ việc **return một object khác không remap BSON**:

```java
package com.example.shop.orders;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;

import static org.assertj.core.api.Assertions.assertThat;

class ReturnValueContractTest {

    @Test
    void beforeSaveReturningCopyDoesNotChangeDocument() {
        OrderDocument original = new OrderDocument(
            "ORD-X", "TENANT-A", " raw ", null, null);
        Document document = new Document(
            "externalRef", " raw ");

        BeforeSaveCallback<OrderDocument> callback =
            (entity, target, collection) ->
                new OrderDocument(
                    entity.id(), entity.tenantId(),
                    "changed-in-memory",
                    entity.normalizedRef(),
                    entity.createdAt());

        OrderDocument returned = callback.onBeforeSave(
            original, document, "orders");

        assertThat(returned.externalRef())
            .isEqualTo("changed-in-memory");
        assertThat(document.getString("externalRef"))
            .isEqualTo(" raw ");
    }
}
```

Đây là **unit test trực tiếp gọi callback**, không chứng minh toàn bộ Spring Data pipeline — nó mô tả chính xác sự khác nhau giữa **entity trả về** và **Document được đưa vào callback**. Integration test mục 14.1 mới chứng minh MongoDB thật đã lưu BSON như kỳ vọng.

### 14.3. Test phản ví dụ: không có callback trên updateFirst

Test `directFieldUpdateDoesNotReRunBeforeConvert` cố tình tạo trạng thái:

```javascript
{
  externalRef: " new-008 ",
  normalizedRef: "WEB-014"
}
```

Đây là **dữ liệu không còn nhất quán** vì updateFirst chỉ sửa `externalRef`. Test này không khuyến khích ghi dữ liệu sai; nó chứng minh rằng callback không phải database constraint và application phải có chính sách cập nhật đồng bộ cả hai field.

### 14.4. Riêng AfterSave: trả object khác BSON đã ghi

Trong integration test mục 14.1, `ReturnNormalizedAfterSaveCallback` được đăng ký **chỉ ở test**. Vì thế ta cố tình có ba giá trị:

```text
Original Java object:
  externalRef = " web-014 "
  normalizedRef = null

Returned Java object after insert:
  externalRef = "web-014"
  normalizedRef = "WEB-014"

Stored MongoDB Document:
  externalRef = " web-014 "
  normalizedRef = "WEB-014"
  schemaVersion = 2
```

Sự khác biệt được tạo ra có chủ đích để **chứng minh hợp đồng của từng callback**. Trong một API nghiệp vụ thật, **không nên để returned entity và stored document lệch nhau về field persistent** như vậy. Test này giúp tránh nhầm “giá trị API trả đúng” với “dữ liệu BSON đã đúng”.

### 14.5. Test trực tiếp đối tượng trong callback

Đôi khi cần unit test callback mà không khởi động MongoDB:

```java
@Test
void immutableBeforeConvertCallbackReturnsCopy() {
    OrderDocument original = new OrderDocument(
        "ORD-X", "TENANT-A",
        " web-014 ", null,
        java.time.Instant.parse("2026-11-20T02:00:00Z"));

    NormalizeOrderRefCallback callback =
        new NormalizeOrderRefCallback();

    OrderDocument result =
        callback.onBeforeConvert(original, "orders");

    assertThat(result).isNotSameAs(original);
    assertThat(result.normalizedRef()).isEqualTo("WEB-014");
    assertThat(original.normalizedRef()).isNull();
}
```

Đây là phần test method với JUnit/AssertJ đã import ở class phù hợp. Unit test chứng minh **copy semantics** của code Java, nhưng không chứng minh MongoDB đã thực hiện mapping và lưu đúng, nên vẫn cần test tích hợp.

## 15. Reactive integration test: phải kiểm tra cả subscription

Với reactive API, việc gọi `reactiveTemplate.insert(entity)` chỉ tạo một Publisher. Callback reactive chạy theo lifecycle khi **được subscribe**:

```java
Mono<OrderDocument> pipeline =
    reactiveTemplate.insert(original);

// Tới đây chưa coi là đã insert.

StepVerifier.create(pipeline)
    .assertNext(saved -> {
        assertThat(saved.normalizedRef())
            .isEqualTo("WEB-014");
    })
    .verifyComplete();
```

Đây là đoạn thuộc một integration test có `reactiveTemplate`, `original`, `StepVerifier` và AssertJ imports. Bài học muốn chứng minh **sự khác biệt giữa assemble và subscribe**, không tuyên bố có thể dùng một callback imperative làm thay đổi entity ở reactive template.

### 15.1. Một test reactive đầy đủ cần những gì?

1. Một Spring test context với `ReactiveMongoTemplate` và `ReactiveBeforeConvertCallback<OrderDocument>` đã được đăng ký.
2. MongoDB test instance hoặc cluster phù hợp, không trỏ production.
3. Đoạn test tạo ID riêng để tránh trùng.
4. `StepVerifier`/subscription chờ kết thúc.
5. Đọc raw BSON bằng driver/reactive collection hoặc bằng một test client riêng, không chỉ dựa vào `findById` vốn có thể bị `AfterConvertCallback` biến đổi.
6. Dọn đúng ID do test tạo sau khi Publisher hoàn tất, không gọi `deleteMany({})` trên collection dùng chung.

Nếu chỉ viết:

```java
Mono<OrderDocument> unused =
    reactiveTemplate.insert(original);
assertThat(unused).isNotNull();
```

thì test chỉ chứng minh có một Publisher, **không chứng minh callback, insert hay commit đã chạy**.

### 15.2. Publisher trả về từ reactive callback phải có tín hiệu entity

Phản ví dụ:

```java
// PHẢN VÍ DỤ: Mono.empty() không phải cách "không chỉnh sửa".
@Override
public Publisher<OrderDocument> onBeforeConvert(
        OrderDocument entity, String collection) {
    return Mono.empty();
}
```

Đối với callback thay entity, Spring Data cần giá trị entity cho bước tiếp theo. Publisher rỗng có thể khiến luồng lưu không có giá trị cần thiết hoặc lỗi. Đúng:

```java
return Mono.just(entity);
```

Để bác bỏ một dữ liệu không hợp lệ, dùng `Mono.error(new IllegalArgumentException(...))` hoặc một exception domain phù hợp; không trả `Mono.empty()` rồi hy vọng save tự rollback đúng ý nghĩa business.

## 16. Điều gì xảy ra khi callback ném exception?

Một callback có thể kiểm tra invariant trước khi lưu:

```java
@Component
public final class RejectMissingTenantCallback
        implements BeforeConvertCallback<OrderDocument> {

    @Override
    public OrderDocument onBeforeConvert(
            OrderDocument entity, String collection) {

        if (entity.tenantId() == null
                || entity.tenantId().isBlank()) {
            throw new IllegalArgumentException(
                "Thiếu tenantId");
        }
        return entity;
    }
}
```

Nếu Spring Data thực thi callback này trước conversion và nó ném exception, đường lưu có thể thất bại **trước khi gửi lệnh ghi của entity đó**. Với reactive callback, dùng `Mono.error(...)` để truyền lỗi.

**Nhưng:** không diễn giải một callback ném lỗi thành “mọi thay đổi trong workflow đã rollback”. Nếu ứng dụng đã ghi một document **trước đó** bằng lệnh khác ở ngoài transaction, callback thất bại ở lệnh thứ hai không tự rollback lệnh đầu. Cần transaction nếu nghiệp vụ yêu cầu atomicity nhiều document.

### 16.1. Callback không thay thế validation phía database

Ví dụ `RejectMissingTenantCallback` chỉ hoạt động với các writer đi qua mapping path tương ứng. Một `db.orders.insertOne(...)` từ `mongosh`, raw MongoDB driver hoặc service khác vẫn có thể ghi document thiếu tenant nếu MongoDB không có validator hoặc nếu quyền/validation bị bypass.

Các lớp bổ trợ:

| Cơ chế | Đối tượng được bảo vệ |
| --- | --- |
| Bean Validation/service validation | Input/domain object ở lớp ứng dụng nơi được gọi |
| Spring Data EntityCallback | Entity đi qua checkpoint mapping của Spring Data |
| MongoDB `$jsonSchema` validator | Lệnh ghi BSON thuộc phạm vi validation trên server |
| Unique index | Trùng key theo ràng buộc index |
| Authorization/tenant filter | Quyền người dùng được đọc/ghi dữ liệu nào |

Đừng dùng callback để thiết lập một **quyền** mà caller có thể giả mạo. `tenantId` phải được xác minh từ security context trước khi giao cho repository; callback có thể kiểm tra nó không rỗng, không thể tự chứng minh user được phép thao tác tenant đó.

### 16.2. Không bắt mọi exception rồi lưu bằng raw driver

```java
// PHẢN VÍ DỤ: callback báo lỗi, service bỏ qua và ghi thô.
try {
    template.insert(entity);
} catch (Exception ignored) {
    template.getCollection("orders")
        .insertOne(new Document("tenantId", null));
}
```

Đoạn này không phải fallback hợp lệ. Nó phá quy tắc chất lượng dữ liệu và biến một lỗi đáng phải sửa thành đường vòng để tạo BSON sai. Thay vào đó, xử lý validation error phù hợp ở API/service và không tạo đường ghi bypass không được kiểm soát.

## 17. Transaction, retry và callbacks có side effects

Nếu `MongoTemplate.save(...)` nằm trong transaction, các callbacks được thực thi trong vòng đời operation tương ứng, nhưng **thứ tự callback không đồng nghĩa commit thành công**:

```text
Transaction begins
    |
    +-- save(Order A)
    |     BeforeConvert/BeforeSave
    |     MongoDB write in transaction
    |     AfterSaveCallback
    |
    +-- save(Order B)
    |     callback throws
    |
    +-- transaction aborts
          |
          +-- A and B changes not committed
          +-- AfterSave of A had ALREADY RUN
```

Vì vậy:

- Không gửi email, thanh toán, phát thông điệp không idempotent trong `AfterSaveCallback`.
- Không dùng callback để ghi một audit event ở MongoDB **bằng session mới độc lập** rồi mặc định event rollback cùng transaction.
- Nếu cần event bền vững, lưu **outbox document** trong cùng transaction và dispatch sau commit.
- Callback có thể chạy nhiều lần nếu application/driver thực thi lại một transaction attempt, nên mọi thay đổi domain cần có idempotency/operation ID.

### 17.1. MongoTemplate callback không đồng nghĩa HTTP request exactly-once

Một gateway có thể retry HTTP POST sau timeout. Nếu callback sinh ID ngẫu nhiên và mỗi request mới lại tạo document khác, transaction trước có thể đã commit mà request sau vẫn insert lần nữa.

Một chiến lược ổn định:

1. Tạo `operationId` từ request ở ranh giới API/application.
2. Xác minh tenant và nội dung request.
3. Dùng ID hoặc unique key ở database ngăn double apply.
4. Để callback chỉ làm biến đổi deterministic của entity, không phát side effects.
5. Khi commit outcome chưa rõ, **reconcile** theo operation ID thay vì tự chạy lại nghiệp vụ tùy tiện.

### 17.2. Tránh tự sửa @Version, ID trong callback

Retry có thể khiến `BeforeConvertCallback` chạy lại. Nếu callback luôn set `version=version+1` hoặc tạo ID mới, attempt sau có thể không còn cùng identity với attempt trước, phá optimistic locking/idempotency. Hãy để store-managed properties do đúng layer sở hữu, và chỉ chuẩn hóa field thực sự thuộc callback.

## 18. Hiệu năng và thiết kế callback có trách nhiệm

Callbacks nằm trên đường nóng của nhiều thao tác insert/save/find. Một callback chạy chậm có thể tác động đến latency toàn bộ repository.

### 18.1. Nguyên tắc ưu tiên

- **Thuần và xác định:** chuẩn hóa chuỗi, kiểm tra invariant, điền giá trị mặc định có quy tắc.
- **Không gọi external API** mỗi lần đọc/ghi; đặc biệt `AfterConvertCallback` có thể chạy với hàng nghìn entities trong một query.
- **Không giữ state mutable dùng chung** trong singleton callback bean; cùng bean có thể được gọi đồng thời.
- **Không ghi chéo collection tùy tiện** khi callback đang được gọi; nguy cơ recursion, retry và sai transaction context.
- **Không đoán collection:** tham số `collection` hữu ích khi entity được lưu vào tên collection khác; nếu callback chỉ áp dụng cho `orders`, làm rõ policy với collection override.
- **Giữ logic idempotent:** save lại một entity đã chuẩn hóa không làm phát sinh thay đổi mỗi lần.

### 18.2. Phân biệt projection và post-processing

Nếu mục tiêu chỉ là hiển thị `externalRef` không có khoảng trắng trên API, một lớp mapper sang DTO có thể đơn giản hơn `AfterConvertCallback` chạy trên **mọi query** của entity đó.

Nếu mục tiêu là **bất biến của dữ liệu lưu**, nên giải quyết trước convert và trên mọi đường ghi liên quan, không chỉ làm đẹp đối tượng khi đọc.

Nếu mục tiêu là **migration legacy**, có thể dùng `AfterConvert` tạm thời để thích nghi nhưng vẫn cần audit/sửa dữ liệu thực; không coi kết quả getter đã chuẩn là bằng chứng MongoDB được backfill.

### 18.3. Đo hiệu năng đúng chỗ

Theo dõi:

- Số lần callback chạy theo type/phase.
- Latency callback ở p50/p95/p99 với tập dữ liệu thực.
- Tỉ lệ lỗi validation trong callback.
- Số lần copy immutable object/allocations nếu đang xử lý tập lớn.
- Query latency, BSON conversion time và MongoDB I/O tách biệt khi có tracing phù hợp.
- Các báo cáo chậm khi `AfterConvert` xử lý N entities, hoặc khi nhiều callback cùng làm việc trùng lặp.

Không gắn ID entity hoặc user ID làm metric label có cardinality cao. Log có kiểm soát và không ghi dữ liệu nhạy cảm trong quá trình debug callback.

## 19. Ma trận chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `withNormalizedRef(...)` được gọi nhưng MongoDB vẫn lưu null | Callback tạo bản sao nhưng **return bản gốc** | Trả đúng instance mới từ `BeforeConvertCallback` |
| Java object sau save có giá trị mới, raw BSON vẫn cũ | Sửa entity ở `BeforeSave`/`AfterSave` sau khi đã convert/ghi | Chuyển thay đổi persistent lên `BeforeConvert`; hoặc sửa BSON có kiểm soát |
| `BeforeSaveCallback` đổi `document.put("x",...)` nhưng object trả về không có `x` | `x` không thuộc domain model/không remap object | Thêm property vào model nếu cần; test cả returned entity lẫn raw BSON |
| `AfterConvertCallback` trả giá trị đúng nhưng collection còn document legacy | Read callback chỉ chỉnh object Java | Migration/backfill dữ liệu thật; không dùng getter làm bằng chứng |
| `MongoTemplate.insert` gọi callback, `updateFirst` không | Update trực tiếp field không tạo domain entity lifecycle | Đồng bộ invariant trong update hoặc dùng service/helper chung |
| Repository save trả đối tượng mới nhưng original không đổi | Entity immutable/record | Sử dụng object **return** thay vì dựa trên mutation |
| `@Version` conflict sau copy | Copy làm mất/đổi version hoặc callback tự bump version | Copy đầy đủ; để framework sở hữu version |
| Duplicate insert sau callback tạo ID | ID được random hóa lại qua attempts/retries | Operation ID cố định, unique key và idempotency |
| Callback không được gọi | Bean không đăng ký, sai generic type hoặc đường API không hỗ trợ | Kiểm tra `ApplicationContext`, class/interface, template path |
| Sync callback hoạt động nhưng reactive không | Đăng ký chỉ `BeforeConvertCallback`, thiếu `ReactiveBeforeConvertCallback` | Đăng ký đúng API type và test subscription |
| Reactive test không có dữ liệu | Không subscribe hoặc Publisher không hoàn thành | `StepVerifier.verifyComplete()`, xử lý error đúng |
| Callback reactive trả `Mono.empty()` | Không phát entity cho checkpoint | Trả `Mono.just(entity)` hoặc phát error có chủ đích |
| Lỗi callback chỉ xảy ra với entity type khác | Generic callback quá rộng, class/lambda type filtering sai | Dùng class typed cụ thể, test nhiều domain types |
| Auditing timestamp bị thay nhiều lần | Custom callback và auditing cùng sở hữu field | Chốt owner, ordering và test update |
| Event listener sửa immutable object nhưng không lưu | Event không truyền bản copy theo value-return contract | Dùng EntityCallback thay vì dựa vào mutation event |
| AfterSave gọi email rồi transaction sau đó rollback | AfterSave xảy ra trước commit transaction cuối cùng | Transactional outbox, dispatch sau commit |
| Callback không áp cho subdocument | Root-level lifecycle khác mapping nested object | Đặt invariant ở root callback/service hoặc custom converter khi cần |
| Performance giảm sau bật callback | N+1 external calls hoặc callback chạy trên tập lớn | Loại external I/O, đo overhead, cân nhắc DTO/mapper khác |
| BSON field tên sai với property Java | Bỏ qua `@Field` khi sửa `Document` | Kiểm tra mapped BSON name, không đoán bằng tên getter |
| Raw driver bỏ qua callback | Driver không đi qua Spring Data entity mapping | Dùng MongoDB validator/contract giữa writers |

## 20. Cách thiết kế callback an toàn cho immutable entity

Một quy trình review trước khi thêm callback:

1. **Xác định invariant:** cần thay đổi persistent field, BSON metadata, entity trả về hay DTO hiển thị?
2. **Chọn checkpoint đúng:** persistent field → `BeforeConvert`; BSON document → `BeforeSave`; đối tượng read → `AfterConvert`; object sau save → `AfterSave` khi thật sự cần.
3. **Chọn cơ chế copy:** record constructor, copy constructor hoặc `with...` method; không bỏ quên thuộc tính/ID/version.
4. **Giữ tính xác định:** chuẩn hóa là hàm thuần, không gọi HTTP hoặc sinh random ID mới mỗi attempt.
5. **Kiểm tra thứ tự:** có auditing/callback khác sửa cùng field không?
6. **Chọn API type:** imperative hay reactive? Có cấu hình cả hai đường gọi nếu ứng dụng dùng cả hai?
7. **Kiểm tra đường ghi:** có `updateFirst`, `bulkOps`, raw driver, migration script hoặc other services không?
8. **Viết test ba lớp:** original Java object, object returned, raw BSON persisted.
9. **Viết test đọc legacy:** afterconvert thay object nhưng không tự ghi DB.
10. **Kiểm tra transaction:** error/rollback và side effects sau save được quản lý ra sao?
11. **Kiểm tra hiệu năng:** callback chạy N lần trên query lớn, có blocking I/O hoặc allocations quá mức không?
12. **Có chiến lược schema evolution:** field mới/legacy được migrate theo quy định, không che lỗi mãi bằng afterconvert.

### 20.1. Không dùng BeforeSave để sửa entity persistent nếu có thể dùng BeforeConvert

Nguyên tắc này xuất phát từ thứ tự thực thi:

```text
BeforeConvert:
  OrderDocument E -> return E'
  Converter maps E' -> Document
  => persistent fields của E' được lưu.

BeforeSave:
  Converter already produced Document D
  return E' without changing D
  => D vẫn có dữ liệu từ entity trước đó.
```

Người học cần phân biệt **cơ chế trả object mới** (có ở nhiều callback) với **checkpoint còn tác động tới dữ liệu lưu hay không** (khác nhau). Đây là điểm thực hành quan trọng nhất của bài.

### 20.2. Khi chỉ cần tạo DTO, callback có thể không phải công cụ phù hợp

Ví dụ muốn hiển thị `"Web #014"` thay cho `" web-014 "`: nếu không thay dữ liệu lưu, nên dùng:

```java
public record OrderResponse(
    String id,
    String displayReference
) {
    public static OrderResponse from(OrderDocument order) {
        return new OrderResponse(
            order.id(),
            order.externalRef().trim());
    }
}
```

Đặt formatting trong mapper API giúp entity phản ánh gần với dữ liệu lưu, tránh callback `AfterConvert` chạy trên mọi truy vấn và che mất tình trạng legacy. Callback vẫn hữu ích khi **toàn bộ domain read** thật sự cần một quy tắc chuyển đổi nhất quán.

## 21. Bài tập vận dụng

Một ứng dụng quản lý vận chuyển có collection `shipments`:

```javascript
{
  _id: "SHIP-001",
  tenantId: "TENANT-A",
  rawTrackingCode: "  abc-789 ",
  trackingCode: "ABC-789",
  carrier: "VNPOST",
  createdAt: ISODate("2026-11-20T02:00:00Z"),
  schemaVersion: 2
}
```

Yêu cầu thiết kế entity bất biến và callbacks:

### Bài 1 — Immutable record

Tạo `ShipmentDocument` kiểu record, có `@Id String id`, `tenantId`, `rawTrackingCode`, `trackingCode`, `carrier`, `createdAt`. Cung cấp `withTrackingCode(String)` tạo bản sao mới mà giữ nguyên các trường khác.

Kiểm tra:

```java
ShipmentDocument original = new ShipmentDocument(
    "SHIP-001", "TENANT-A",
    "  abc-789 ", null, "VNPOST", createdAt);

ShipmentDocument next =
    original.withTrackingCode("ABC-789");
```

Trong code trên `createdAt` là biến `Instant` đã chuẩn bị. Giải thích vì sao `original.trackingCode()` vẫn null.

### Bài 2 — BeforeConvertCallback

Viết `BeforeConvertCallback<ShipmentDocument>`:

- Từ chối tracking code rỗng.
- Chuẩn hóa `trim().toUpperCase(Locale.ROOT)`.
- Nếu giá trị đã chuẩn, trả cùng instance.
- Nếu chưa chuẩn, trả bản sao mới.
- Không đổi `id/tenantId/createdAt`.

So sánh hai implementation:

```java
// Sai
entity.withTrackingCode(normalized);
return entity;

// Đúng
return entity.withTrackingCode(normalized);
```

### Bài 3 — BeforeSaveCallback

Viết `BeforeSaveCallback<ShipmentDocument>`:

```java
document.put("schemaVersion", 2);
return entity;
```

Vì sao đoạn này lưu được `schemaVersion` ngay cả khi record không có property tương ứng? Nếu chỉ trả một record copy có `trackingCode` mới mà không sửa `document`, BSON được lưu có thể vẫn khác thế nào?

### Bài 4 — AfterSaveCallback

Tạo một callback demo trả `ShipmentDocument` mới có `carrier` được chuẩn hóa cho **object trả về**, nhưng không sửa BSON. Viết test so sánh object từ save và BSON thực. Trả lời tại sao không nên làm cách này cho persistent field trong production, và vì sao `AfterSaveCallback` không phải after-commit event.

### Bài 5 — AfterConvertCallback

Seed một document legacy thiếu `trackingCode` bằng raw driver. Dùng `AfterConvertCallback` tạo bản sao có `trackingCode` được suy ra từ `rawTrackingCode` khi đọc. Viết test chứng minh:

- `findById` trả `trackingCode="ABC-789"`.
- Raw BSON vẫn thiếu `trackingCode`.
- Chỉ khi có một write hợp lệ, field mới có thể được lưu.

### Bài 6 — Auditing/ordering

Thêm `@CreatedDate` và `@LastModifiedDate`, bật Mongo auditing tương ứng. Nếu một custom callback cũng gán `createdAt`, thứ tự nào cần xác định và vì sao nên chỉ có một owner?

### Bài 7 — updateFirst bỏ qua lifecycle

Thử:

```java
template.updateFirst(
    Query.query(Criteria.where("_id").is("SHIP-001")),
    new Update().set("rawTrackingCode", " xy-901 "),
    ShipmentDocument.class);
```

Giải thích vì sao `trackingCode` có thể vẫn là `"ABC-789"`. Sửa update thành thao tác atomic cập nhật **cả hai field** với cùng quy tắc chuẩn hóa từ service.

### Bài 8 — Reactive callback

Viết `ReactiveBeforeConvertCallback<ShipmentDocument>` trả `Mono.just(copy)` hoặc `Mono.fromSupplier(...)`. Dùng `StepVerifier` kiểm tra insert và đọc BSON sau subscription. Trả lời tại sao `Mono.empty()` và `subscribe()` bên trong callback không phải lựa chọn an toàn.

### Bài 9 — Kiểm thử và bảo vệ dữ liệu

Viết thêm integration tests cho:

1. Original entity bất biến.
2. Returned entity khác original khi cần chuẩn hóa.
3. Raw BSON phản ánh `BeforeConvert` và `BeforeSave`.
4. AfterConvert không tự migration legacy.
5. Update trực tiếp và raw driver không chạy callback.
6. Callback validation ném lỗi khiến entity không được ghi.
7. Duplicate ID và `@Version` được xử lý bởi đúng layer, không tự sinh ID mới ở callback.
8. Transaction rollback và external side effects không bị đặt trong `AfterSave`.

### Hướng giải quyết

**Tách ba lớp trạng thái:** entity Java trước callback, entity được callback trả về, và BSON thực tế trong database. Kiểm tra cả ba. Dùng `BeforeConvert` cho **giá trị persistent**, `BeforeSave` cho **BSON đã map**, và `AfterConvert/AfterSave` chỉ để điều chỉnh kết quả Java khi có lý do rõ ràng. Không mở rộng phạm vi callback thành database constraint, authorization hoặc outbox workflow.

## 22. Tài liệu tham khảo

- Spring Data MongoDB — [Lifecycle Events and Entity Callbacks](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html): checkpoint lifecycle, phân biệt event listener và entity callback, bảng callback sync/reactive.
- Spring Data Commons — [Entity Callbacks](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html): cơ chế callback trả object, order, type filtering và immutable entities.
- Spring Data MongoDB API — [BeforeConvertCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeConvertCallback.html): trả entity được dùng trước conversion.
- Spring Data MongoDB API — [BeforeSaveCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeSaveCallback.html): `Document` đã được tạo; chỉ thay `Document` mới thay dữ liệu lần ghi.
- Spring Data MongoDB API — [AfterSaveCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/AfterSaveCallback.html): entity được trả về sau save.
- Spring Data MongoDB API — [AfterConvertCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/AfterConvertCallback.html): entity được trả về sau khi load và convert.
- Spring Data MongoDB API — [ReactiveBeforeConvertCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/ReactiveBeforeConvertCallback.html): Publisher phát entity trước conversion.
- Spring Data Commons — [Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html): immutable properties, constructors, withers và việc tạo instance mới khi mapping.
- Spring Data MongoDB — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): mapping `@Id`, `@Field`, converter và cách lưu BSON.
- Project Reactor — [Reference Guide](https://projectreactor.io/docs/core/release/reference/): subscription, `Mono`/`Flux` và chuỗi reactive.

## Ghi nhớ

**Với immutable entity, callback phải trả đúng instance mà nó muốn Spring Data sử dụng; gọi `with...` rồi bỏ return sẽ không có tác dụng.** `BeforeConvertCallback` thay persistent entity **trước khi mapping BSON**, vì vậy copy được trả về có thể ảnh hưởng dữ liệu lưu. `BeforeSaveCallback` chạy **sau mapping**; muốn thay BSON lần ghi đang diễn ra phải sửa `org.bson.Document`, không chỉ trả một entity mới. `AfterSaveCallback` và `AfterConvertCallback` có thể đổi **object Java trả về** nhưng không tự ghi lại MongoDB. Để tránh sai lệch giữa original, returned và stored state, kiểm tra cả ba bằng integration test, giữ callback deterministic, phân biệt reactive/sync, bảo vệ `@Id/@Version` và đừng dùng callback thay thế database validation, authorization hoặc transaction/outbox.
