# Các giai đoạn đọc, chuyển đổi, lưu và xóa document

## 1. Vì sao cần hiểu vòng đời document?

Trong chương **Vòng đời và callback** của **Spring Data MongoDB**, một lần gọi `repository.save(product)` không đơn thuần là chuyển một object Java thành BSON rồi gửi lệnh ghi. Spring Data còn có thể thực hiện ánh xạ ID, xử lý auditing, chạy các **EntityCallback**, phát **mapping lifecycle events**, chuyển đổi kiểu dữ liệu và trả kết quả cho ứng dụng.

Tương tự, khi đọc bằng `MongoTemplate.findOne(...)` hoặc `MongoRepository.findById(...)`, document BSON phải được chuyển thành object Java. Với thao tác xóa, database thường chỉ nhận **điều kiện xóa** chứ không nhất thiết tải từng entity rồi mới xóa.

Đây là những điểm đặc biệt quan trọng khi hệ thống cần:

- Chuẩn hóa một mã SKU trước khi lưu, nhưng **không** phá hủy định danh gốc.
- Kiểm tra dạng BSON sau mapping, ví dụ `@Field("sku_normalized")`.
- Quan sát hoạt động đọc/ghi để ghi metric hoặc chẩn đoán.
- Dùng `@CreatedDate`/`@LastModifiedDate` thay vì tự cập nhật thời gian ở mọi service.
- Hiểu vì sao một lần `updateFirst(...)` hoặc bulk update **không gọi cùng hooks** như `save(entity)`.
- Tránh gửi email, gọi HTTP hoặc publish message từ callback trước khi transaction thật sự commit.
- Không nhầm delete event với việc nhận được **đầy đủ từng entity** đã xóa.

**Mục tiêu bài:** vẽ đúng các giai đoạn đọc → chuyển đổi → lưu → xóa; phân biệt `EntityCallback` với `AbstractMongoEventListener`; xây ví dụ Spring Data MongoDB có callback trên Java record, đọc/ghi MongoDB thật và thiết kế kiểm thử để xác nhận giới hạn của từng cơ chế.

> Ví dụ theo Java 17+, Spring Boot 3.x và Spring Data MongoDB 4.x, sử dụng `MongoTemplate`/`MongoRepository` đồng bộ. API callback và thời điểm phát event có những chi tiết phụ thuộc phiên bản/framework. Các sơ đồ dưới đây mô tả **thứ tự logic** của các giai đoạn, không cam kết thứ tự chính xác giữa mọi listener, converter, auditing callback và driver hook trong mọi phiên bản.

## 2. Ba lớp cần phân biệt

| Lớp | Đối tượng xử lý | Mục đích |
|---|---|---|
| **MongoDB server / Java Driver** | BSON Document, query và lệnh `insert`/`update`/`delete` | Đọc/ghi dữ liệu, kiểm tra điều kiện, atomicity, write concern |
| **Spring Data mapping/converter** | Object Java ↔ BSON Document | Đọc annotation như `@Document`, `@MongoId`, `@Field`, conversion và mapping |
| **Lifecycle hooks của Spring Data** | Object hoặc event liên quan các giai đoạn | Callback có thể can thiệp vào entity ở những điểm hỗ trợ; event quan sát quá trình xử lý |

Ví dụ field:

~~~java
@Field("sku_normalized")
String normalizedSku
~~~

Ở Java, tên property là `normalizedSku`; trên MongoDB, field vật lý là `sku_normalized`. Một callback **trước chuyển đổi** thao tác với property Java, trong khi callback **trước lưu** có thể nhìn thấy cả BSON Document đã map. Chọn sai giai đoạn dẫn đến kiểm tra nhầm tên field hoặc sửa object quá muộn.

### 2.1. EntityCallback và application lifecycle event không giống nhau

**EntityCallback** là giao diện callback của Spring Data, được gọi như một phần của chu trình xử lý entity ở những điểm được hỗ trợ. Nó có thể **trả về entity thay thế**, ví dụ tạo bản immutable record mới sau chuẩn hóa.

**Mapping lifecycle event** là Spring `ApplicationEvent`, thường được lắng nghe qua `AbstractMongoEventListener<T>`. Event thích hợp cho **quan sát/chẩn đoán**, nhưng phụ thuộc cơ chế phát event. Nếu `ApplicationEventMulticaster` dùng executor bất đồng bộ, thứ tự và thời điểm listener chạy **không thể dùng để bảo đảm mutation nghiệp vụ**.

Không dùng hai thuật ngữ “callback” và “event listener” như cùng một cơ chế. Chúng có khả năng, thứ tự và điều kiện thực thi khác nhau.

### 2.2. Không có hook cho mọi thao tác

Một lệnh ghi **raw driver**, một `MongoTemplate.updateFirst(...)` dùng update operators và một `repository.save(entity)` có đường xử lý khác nhau. Không tự suy rằng tất cả đều đi qua `BeforeConvertCallback`, `BeforeSaveCallback` và `AfterSaveCallback` của một entity.

## 3. Sơ đồ vòng đời đọc document

Đối với truy vấn ánh xạ kết quả thành entity Java, chuỗi ý tưởng:

~~~mermaid
flowchart TD
    A["Repository.find... / MongoTemplate.find..."] --> B["MongoDB trả BSON Document"]
    B --> C["AfterLoadEvent (raw Document, nếu event được phát)"]
    C --> D["MappingMongoConverter đọc Document"]
    D --> E["Khởi tạo entity / record"]
    E --> F["AfterConvert callback và event tương ứng"]
    F --> G["Trả entity Java cho caller"]
~~~

Các giai đoạn:

1. **Query chạy trên MongoDB**: index/filter/sort vẫn là trách nhiệm của server.
2. **Nhận BSON**: document có tên field lưu trữ, không phải nhất thiết tên property Java.
3. **Sau tải, trước convert**: `AfterLoadEvent` cung cấp điểm quan sát document thô trong những operation phát event.
4. **Chuyển đổi**: `MappingMongoConverter` ánh xạ field, kiểu dữ liệu, ID, constructor/record components, custom conversions.
5. **Sau convert**: `AfterConvertCallback<T>` có thể nhận entity đã tạo và trả về phiên bản phù hợp; `AfterConvertEvent<T>` cho listener quan sát.
6. **Caller nhận kết quả**: đã là entity Java, không phải raw BSON.

**Lưu ý:** `AfterLoadEvent` là một **mapping event**, không đồng nghĩa tồn tại một `AfterLoadCallback<T>` tương ứng với mọi bản Spring Data. Chọn đúng API thực sự được Spring Data MongoDB cung cấp.

### 3.1. Đọc không có nghĩa lưu

Một callback sau convert có thể tạo giá trị hiển thị cho object kết quả, nhưng điều đó **không tự ghi trở lại MongoDB**. Nếu cần migration schema bền vững, phải có một lệnh write rõ ràng và kế hoạch migration/transaction riêng.

### 3.2. Projection, aggregation và DTO

Không phải mọi query đều trả về entity root đã đăng ký callback:

~~~java
mongo.find(query, ProductSummary.class, "catalog_entries");
~~~

Khi trả về DTO/projection hoặc raw `Document`, callback dành cho `CatalogEntry` có thể không được gọi theo cách một lần `find(..., CatalogEntry.class)` thực hiện. Phải test riêng **đường query cụ thể**; không xây invariant dựa trên giả định mọi cách đọc đều chạy cùng listener.

## 4. Sơ đồ vòng đời ghi insert/save

Với ghi entity đi qua mapping của Spring Data:

~~~mermaid
flowchart TD
    A["Repository.save / MongoTemplate.insert hoặc save"] --> B["Trước convert: BeforeConvert hook"]
    B --> C["MappingMongoConverter: entity -> BSON"]
    C --> D["Trước write: BeforeSave hook, BSON đã map"]
    D --> E["MongoDB insert/replace/upsert theo semantics API"]
    E --> F["Sau write: AfterSave hook / event"]
    F --> G["Trả kết quả cho caller"]
~~~

Các điểm quan trọng:

- **BeforeConvert**: có entity Java; hợp lý để chuẩn hóa field hoặc tạo một entity mới trước mapping.
- **BeforeSave**: converter đã tạo BSON; phù hợp để kiểm tra cấu trúc BSON hoặc một số điều chỉnh representation được hỗ trợ.
- **Driver write**: MongoDB thực hiện `insertOne`/`replaceOne`/`update` theo operation thực tế.
- **AfterSave**: code đã đi qua thao tác ghi và nhận kết quả phù hợp; **không đồng nghĩa transaction đã commit**.

Các điểm này có thể có **EntityCallback** và **application event** tương ứng. Không giả định event và callback cùng một giai đoạn luôn có thứ tự tương đối cố định trên mọi phiên bản và cấu hình event multicaster.

### 4.1. insert không phải save

| API | Ý nghĩa tổng quát | Điều cần lưu ý |
|---|---|---|
`MongoTemplate.insert(entity)` | Tạo document mới | Duplicate `_id`/unique key có thể lỗi |
`MongoTemplate.save(entity)` | Lưu entity theo semantics save, thường upsert/replace tùy mapping và ID | Ghi đè document từ entity stale/thiếu field là rủi ro |
`MongoRepository.save(entity)` | Repository abstraction cho save entity | Lifecycle mapping tương ứng, không tự transaction nhiều document |
`MongoTemplate.updateFirst(query, update, Entity.class)` | Partial update bằng operators | Không nhất thiết chạy entity save callbacks |
`MongoTemplate.findAndModify(...)` | Một update có điều kiện và có thể trả pre/post-image | Không coi là `save(entity)`; callback đọc kết quả có thể khác |
Raw `MongoCollection.updateOne(...)` | Lệnh Java Driver trực tiếp | Không đi qua toàn bộ lifecycle mapping Spring Data |

Một lần `save` trên **entity đã đọc thiếu field** có thể làm mất dữ liệu khi đường ghi thay thế cả document. Khi chỉ muốn thay đổi một field, thường cân nhắc conditional/partial update; khi cần bảo vệ stale state, dùng `@Version` và business CAS phù hợp.

### 4.2. ID sinh trong pipeline

ID có thể được xác định trước hoặc trong quá trình ghi tùy entity mapping, kiểu ID và nguồn ID. Không xây một quy tắc cứng “mọi ID đều đã có trước BeforeConvert” hay “mọi ID đều chưa có trước BeforeSave”. Nếu logic callback yêu cầu ID, hãy **kiểm thử kiểu ID/đường ghi đang dùng** hoặc chủ động cấp ID trước khi save.

## 5. Vòng đời xóa: thường có query, không có mỗi entity

Delete operation khác read-modify-save:

~~~javascript
db.catalog_entries.deleteMany({
  tenantId: "tenant-a",
  archived: true
});
~~~

MongoDB có thể xóa nhiều document dựa trên **query selector** mà không tải từng entity đầy đủ về Java. Spring Data có các lifecycle events như `BeforeDeleteEvent` và `AfterDeleteEvent` ở những đường operation hỗ trợ event publication, nhưng event không nhất thiết chứa từng entity bị xóa.

~~~mermaid
flowchart TD
    A["MongoTemplate.remove / Repository.delete"] --> B["Chuẩn bị điều kiện và collection"]
    B --> C["BeforeDeleteEvent khi đường API hỗ trợ"]
    C --> D["MongoDB deleteOne/deleteMany"]
    D --> E["AfterDeleteEvent khi đường API hỗ trợ"]
    E --> F["Trả DeleteResult / kết quả repository"]
~~~

**Không giả định có EntityCallback onBeforeDelete/onAfterDelete áp dụng cho từng root entity** như một phương thức thay thế cho `BeforeConvertCallback`. Để biết một document cụ thể đã xóa những gì, phải chủ động lưu identifier/ảnh dữ liệu/sự kiện nghiệp vụ ở tầng service hoặc sử dụng cơ chế outbox/audit phù hợp.

### 5.1. Delete by query không phải callback N lần

Một `remove(query, CatalogEntry.class)` có thể xóa 100 document nhưng listener **không được xem là 100 lần gọi với 100 entity**. Đừng dùng delete lifecycle event để gửi email cho từng bản ghi hoặc duy trì counter nghiệp vụ theo từng document.

### 5.2. Các thao tác native/bulk và bypass

`MongoCollection.deleteMany(...)` của Java Driver không đi qua các mapping events của `MongoTemplate`. Bulk writes và các đường xóa tùy biến cũng cần được kiểm chứng theo API thực tế. Nếu cần audit chính xác mọi đường ghi/xóa, nên đặt invariant vào dịch vụ, schema/unique index/transaction hoặc một pipeline event đáng tin cậy, không trông đợi các callback của entity bao phủ mọi write path.

## 6. Bảng sự kiện và callback theo thời điểm

| Giai đoạn | Mapping event thường gặp | EntityCallback tương ứng nếu được hỗ trợ | Dữ liệu chính |
|---|---|---|---|
Trước convert sang BSON | `BeforeConvertEvent<T>` | `BeforeConvertCallback<T>` | Entity Java |
Trước lưu sau convert | `BeforeSaveEvent<T>` | `BeforeSaveCallback<T>` | Entity + mapped BSON Document |
Sau lưu | `AfterSaveEvent<T>` | `AfterSaveCallback<T>` | Entity + mapped BSON Document |
Sau tải BSON trước convert | `AfterLoadEvent<T>` | Không giả định có callback cùng tên | BSON Document |
Sau convert về Java | `AfterConvertEvent<T>` | `AfterConvertCallback<T>` | Entity Java + BSON Document |
Trước xóa | `BeforeDeleteEvent<T>` | Không mặc định có per-entity delete callback | Delete selector/collection |
Sau xóa | `AfterDeleteEvent<T>` | Không mặc định có per-entity delete callback | Thông tin thao tác, không phải mọi deleted entity |

Tên interfaces cụ thể cho mapping EntityCallbacks:

~~~java
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveCallback;
import org.springframework.data.mongodb.core.mapping.event.AfterConvertCallback;
~~~

Trong MongoDB reactive infrastructure, Spring Data có các **Reactive...Callback** tương ứng cho những giai đoạn hỗ trợ, nhưng contract trả publisher và context khác imperative. Không trộn callback imperative với reactive session/transaction mà chưa xác minh đường pipeline.

### 6.1. Khi nào dùng cái gì?

- Cần **đổi entity trước mapping**: ưu tiên `BeforeConvertCallback<T>`.
- Cần **kiểm tra mapped BSON**: `BeforeSaveCallback<T>` có thể là điểm phù hợp.
- Cần **enrichment sau đọc**: `AfterConvertCallback<T>` nếu phù hợp với contract.
- Cần **quan sát raw BSON trước mapping**: `AfterLoadEvent<T>`.
- Cần **log/metric ít ràng buộc**: `AbstractMongoEventListener<T>`, chú ý async multicaster.
- Cần **bảo đảm nghiệp vụ xuyên mọi write paths**: dùng service, database constraints, transactions/outbox; không chỉ callback.

## 7. Entity ví dụ: mã SKU chuẩn hóa và tên BSON

Giả sử collection `catalog_entries` chứa sản phẩm theo tenant. Ứng dụng giữ mã SKU do người dùng nhập và một khóa đã chuẩn hóa dùng để tìm/đảm bảo uniqueness.

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "sku": " bottle-500 ",
  "displayName": "Bình nước 500 ml",
  "sku_normalized": "BOTTLE-500",
  "createdAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

**CatalogEntry.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_entries")
public record CatalogEntry(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        String sku,
        String displayName,
        @Field("sku_normalized") String normalizedSku,
        Instant createdAt) {
}
~~~

Một repository:

**CatalogEntryRepository.java**

~~~java
package com.example.catalog;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogEntryRepository
        extends MongoRepository<CatalogEntry, String> {

    Optional<CatalogEntry> findFirstByTenantIdAndNormalizedSku(
            String tenantId, String normalizedSku);
}
~~~

Ở đây `findFirstByTenantIdAndNormalizedSku` minh họa **tên property Java** trong derived query; repository query được mapping sang field BSON `sku_normalized`. `Optional<CatalogEntry>` biểu diễn rõ trạng thái không tìm thấy; một lời gọi tìm kiếm không có document không nên được hiểu là một entity mang giá trị null hợp lệ.

### 7.1. Khóa duy nhất không thể chỉ dựa vào callback

Nếu nghiệp vụ cấm hai sản phẩm cùng SKU đã chuẩn hóa trong một tenant:

~~~javascript
db.catalog_entries.createIndex(
  { tenantId: 1, sku_normalized: 1 },
  { name: "uq_entry_tenant_sku", unique: true }
);
~~~

**Callback chuẩn hóa không bảo vệ uniqueness dưới concurrency.** Hai request có thể cùng chuẩn hóa thành `BOTTLE-500`; chính unique index mới bảo vệ không có hai document trùng cặp `tenantId`/`sku_normalized`.

### 7.2. Không để callback đổi tenant

`tenantId` phải được kiểm soát tại tầng authentication/authorization. Callback có thể validate rằng tenant ID tồn tại, nhưng không nên tự lấy tenant ID tùy ý từ request-local state rồi ghi đè entity ngầm. Với background jobs, nhiều tenant, reactive context và các đường ghi raw driver, cách đó dễ gây rò dữ liệu.

## 8. BeforeConvertCallback: chuẩn hóa immutable entity

`BeforeConvertCallback<T>` được dùng khi cần tính một giá trị từ entity **trước khi MappingMongoConverter biến nó thành BSON**. Với Java record, không thể gọi setter; callback nên **trả về một record mới**.

**NormalizeSkuBeforeConvert.java**

~~~java
package com.example.catalog;

import java.util.Locale;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class NormalizeSkuBeforeConvert
        implements BeforeConvertCallback<CatalogEntry> {

    @Override
    public CatalogEntry onBeforeConvert(
            CatalogEntry entity, String collection) {
        if (!"catalog_entries".equals(collection)) {
            return entity;
        }

        if (entity.tenantId() == null
                || entity.tenantId().isBlank()) {
            throw new IllegalArgumentException(
                    "Tenant không hợp lệ");
        }
        if (entity.sku() == null || entity.sku().isBlank()) {
            throw new IllegalArgumentException("SKU rỗng");
        }

        String normalized = entity.sku()
                .strip()
                .toUpperCase(Locale.ROOT);

        return new CatalogEntry(
                entity.id(),
                entity.tenantId(),
                entity.sku(),
                entity.displayName(),
                normalized,
                entity.createdAt());
    }
}
~~~

Khi lưu một `CatalogEntry` có `sku = " bottle-500 "`, callback tạo record mới với `normalizedSku = "BOTTLE-500"`. Converter sau đó ánh xạ thành BSON `sku_normalized: "BOTTLE-500"`.

### 8.1. Vì sao trả về entity mà không chỉ sửa Document?

Nếu normalized SKU là thành phần quan trọng của domain state, nó nên hiện diện ở **entity**:

- Caller/mapper/validator có thể nhìn cùng giá trị.
- Mapping `@Field` tự chuyển đúng tên BSON.
- Test có thể xác minh Java object trước và sau callback.
- Không sinh ra một field “ẩn” ở BSON mà entity không phản ánh khi đọc/ghi lại.

Không dùng `BeforeSaveCallback` chỉ để âm thầm ghi một giá trị nghiệp vụ quan trọng vào raw Document trong khi object Java vẫn giữ state khác.

### 8.2. Chuẩn hóa là một quy tắc domain, không chỉ một tiện ích mapping

Chính sách `strip().toUpperCase(Locale.ROOT)` trong bài chỉ phù hợp với SKU có quy ước mã ASCII/chữ cái Latin đơn giản. Nó **không giải quyết mọi Unicode case-folding, dấu tiếng Việt, chuẩn hóa khoảng trắng nội bộ, ký tự đặc biệt hoặc chính sách locale của SKU thực tế**.

Phải định nghĩa chuẩn hóa ngay trong domain contract và đảm bảo **mọi đường nhập** dùng cùng chính sách (API, batch, import và migration). Raw driver writes có thể bypass callback; vì thế nếu nhiều service ghi chung collection, không nên tin callback một ứng dụng là ràng buộc toàn database.

### 8.3. @Order và nhiều callback

Spring Data có thể đăng ký nhiều `EntityCallback` cho cùng entity type. `@Order`/`Ordered` hỗ trợ điều khiển thứ tự callback. Nhưng một callback normalization không nên bí mật phụ thuộc vào một callback khác đã tạo tenant ID, vì điều này có thể thay đổi khi cấu hình auditing hoặc framework nâng cấp.

Nếu cần nhiều bước phụ thuộc nhau, hãy làm rõ thứ tự và **test kết quả toàn pipeline**. Đừng dùng callback để phát sinh một số ngẫu nhiên hoặc gọi dịch vụ ngoài trước khi biết write/commit có thành công.

## 9. BeforeSaveCallback: nhìn BSON sau mapping

`BeforeSaveCallback<T>` nhận:

- Entity đã đi qua một phần pipeline chuyển đổi;
- `org.bson.Document` chứa biểu diễn BSON mà Spring Data đã map;
- Tên collection.

Ví dụ yêu cầu raw BSON chứa đúng khóa chuẩn hóa:

**ValidateMappedDocumentBeforeSave.java**

~~~java
package com.example.catalog;

import java.util.Objects;
import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class ValidateMappedDocumentBeforeSave
        implements BeforeSaveCallback<CatalogEntry> {

    @Override
    public CatalogEntry onBeforeSave(
            CatalogEntry entity,
            Document document,
            String collection) {
        if (!"catalog_entries".equals(collection)) {
            return entity;
        }

        String mappedSku = document.getString("sku_normalized");
        if (mappedSku == null || mappedSku.isBlank()) {
            throw new IllegalStateException(
                    "Thiếu sku_normalized trong BSON");
        }
        if (!Objects.equals(mappedSku, entity.normalizedSku())) {
            throw new IllegalStateException(
                    "BSON và entity không nhất quán");
        }
        return entity;
    }
}
~~~

Sau `BeforeConvertCallback` và conversion, `document.getString("sku_normalized")` nhìn vào **tên field BSON**, không phải Java property `normalizedSku`.

### 9.1. Không dùng raw Document làm nguồn sự thật thứ hai

Một số callback có thể chỉnh sửa `Document` trực tiếp khi điểm mở rộng hỗ trợ. Tuy nhiên, nếu thay `document.put("sku_normalized", ...)` mà không đồng bộ với entity:

1. Database có giá trị khác object trả về.
2. Một lần save sau của object đó có thể ghi đè ngược.
3. Validation/domain logic trước conversion có thể dựa vào dữ liệu cũ.
4. Đường cập nhật partial hoặc driver raw không đi qua callback.

Vì vậy ví dụ chọn **kiểm tra BSON đã map**, không âm thầm sửa business key ở giai đoạn cuối.

### 9.2. Validation và exception trong callback

Nếu callback đồng bộ ném exception trước khi driver write được gửi, thao tác `save` thông thường sẽ thất bại. Nhưng đừng dùng callback làm **phòng tuyến duy nhất** cho invariant:

- Không bảo vệ raw update/bulk/driver đường khác.
- Không thay thế schema validation, unique index hay authorization.
- Không chứng minh transaction nhiều document đã commit.

Validation đầu vào vẫn nên được đặt ở service/domain layer; callback giúp bảo vệ một đường persistence cụ thể và có thể phát hiện mapping regression.

## 10. AfterConvertCallback: xử lý object sau khi đọc

Sau khi BSON được chuyển thành entity, `AfterConvertCallback<T>` có thể kiểm tra/enrich object được trả về.

**CheckLoadedEntryAfterConvert.java**

~~~java
package com.example.catalog;

import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class CheckLoadedEntryAfterConvert
        implements AfterConvertCallback<CatalogEntry> {

    @Override
    public CatalogEntry onAfterConvert(
            CatalogEntry entity,
            Document document,
            String collection) {
        if (!"catalog_entries".equals(collection)) {
            return entity;
        }

        // Ví dụ chẩn đoán schema legacy:
        // BSON document có thể thiếu trường mới trong dữ liệu cũ.
        if (!document.containsKey("sku_normalized")) {
            // Chính sách có thể là ghi metric/cảnh báo.
            // Không tự ghi lại database từ callback đọc.
        }
        return entity;
    }
}
~~~

Đoạn callback này có chủ đích không thay đổi entity. Nếu nghiệp vụ yêu cầu một **giá trị hiển thị tạm thời** không lưu DB, có thể trả bản immutable copy đã enrich, nhưng phải cân nhắc chuyện object đó có thể được save sau này; tránh khiến enrichment bị persist ngầm.

### 10.1. AfterConvert không phải nơi chạy migration tự động

Giả sử hàng triệu document cũ thiếu `sku_normalized`. Một callback đọc có thể nhận biết sự thiếu hụt, nhưng không nên tự:

~~~text
onAfterConvert:
  đọc document cũ
  tự update database ngay
  gọi API bên ngoài
  tiếp tục trả kết quả
~~~

Mô hình này tạo write side effect bất ngờ mỗi lần query, có thể lặp/đua nhau ghi, tăng latency và gây recursion. Dùng migration/job riêng có checkpoint, batching, idempotency và giám sát; còn callback read chỉ phản ánh dữ liệu hiện tại.

### 10.2. AfterLoad và AfterConvert khác thời điểm

| Giai đoạn | Quan sát gì? | Tên trường |
|---|---|---|
`AfterLoadEvent` | BSON Document trước object mapping | `sku_normalized` |
`AfterConvertCallback` | Object Java đã map + BSON Document | `entity.normalizedSku()` và `sku_normalized` |

Đừng viết listener kiểm tra `document.getString("normalizedSku")` nếu dữ liệu vật lý là `sku_normalized`.

## 11. AfterSaveCallback và tác dụng phụ ngoài database

`AfterSaveCallback<T>` có thể quan sát entity/document sau write mà Spring Data đã thực hiện:

~~~java
package com.example.catalog;

import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class CatalogAfterSaveMetric
        implements AfterSaveCallback<CatalogEntry> {

    @Override
    public CatalogEntry onAfterSave(
            CatalogEntry entity,
            Document document,
            String collection) {
        // Có thể ghi metric nhẹ/diagnostic nếu phù hợp.
        // Không gửi email hoặc publish message bảo đảm từ đây.
        return entity;
    }
}
~~~

**Không coi AfterSave là after-commit.** Nếu `repository.save(...)` chạy trong MongoDB transaction, callback có thể được gọi khi write command xong nhưng trước khi transaction commit; transaction vẫn có thể abort ở một bước sau.

Ví dụ phản chứng:

~~~text
BEGIN TRANSACTION
  save(Order)
    -> AfterSaveCallback gửi email "Đã đặt hàng"
  update(Inventory) thất bại
ROLLBACK TRANSACTION

Email đã gửi nhưng Order không được commit.
~~~

Giải pháp nên cân nhắc:

- **Transactional outbox**: lưu business state và outbox event trong cùng transaction, worker publish sau commit với idempotency.
- Đối với thông báo nội bộ không bền vững, có thể dùng transaction synchronization afterCommit khi transaction được quản lý đúng, nhưng vẫn có cửa sổ crash giữa commit và callback; không thay outbox cho delivery guarantee.
- Không dùng external API call trong callback vốn có thể chạy nhiều lần hoặc ở thread/event context không dự đoán được.

### 11.1. Một save có thể bị retry

Write có thể bị phát lại ở cấp application khi timeout, nên metric hoặc side effect trong after-save callback có thể phát sinh nhiều hơn số **ý định nghiệp vụ duy nhất**. Đừng tính doanh thu, điểm thưởng hay số lần thanh toán chỉ bằng increment ở callback sau save.

### 11.2. Không tự mở vòng lặp save

Nếu `AfterSaveCallback` gọi `repository.save(entity)` cho cùng entity, callback lại được kích hoạt, dễ sinh recursion hoặc ghi lặp. Tương tự `AfterConvertCallback` gọi lại `findById` không kiểm soát có thể tạo read loop.

Giữ callback **ngắn, xác định, ít side effect và không tự gọi lại cùng lifecycle path**.

## 12. AbstractMongoEventListener: quan sát raw BSON và delete

Với event-based lifecycle, `AbstractMongoEventListener<T>` cho phép override các hook ứng với event đã phát. Mẫu dưới đây chỉ đếm sự kiện cho mục đích kiểm thử/chẩn đoán.

**CatalogLifecycleObserver.java**

~~~java
package com.example.catalog;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.data.mongodb.core.mapping.event.AbstractMongoEventListener;
import org.springframework.data.mongodb.core.mapping.event.AfterLoadEvent;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveEvent;
import org.springframework.data.mongodb.core.mapping.event.BeforeDeleteEvent;
import org.springframework.stereotype.Component;

@Component
public class CatalogLifecycleObserver
        extends AbstractMongoEventListener<CatalogEntry> {

    private final AtomicInteger afterLoad = new AtomicInteger();
    private final AtomicInteger afterSave = new AtomicInteger();
    private final AtomicInteger beforeDelete = new AtomicInteger();

    @Override
    public void onAfterLoad(AfterLoadEvent<CatalogEntry> event) {
        // event.getSource() là raw BSON Document.
        afterLoad.incrementAndGet();
    }

    @Override
    public void onAfterSave(AfterSaveEvent<CatalogEntry> event) {
        afterSave.incrementAndGet();
    }

    @Override
    public void onBeforeDelete(BeforeDeleteEvent<CatalogEntry> event) {
        // Event delete liên quan selector/operation,
        // không phải một entity đầy đủ cho từng document bị xóa.
        beforeDelete.incrementAndGet();
    }

    public int afterLoadCount() { return afterLoad.get(); }
    public int afterSaveCount() { return afterSave.get(); }
    public int beforeDeleteCount() { return beforeDelete.get(); }
}
~~~

**Lưu ý quan trọng về ví dụ đếm sự kiện:** event dispatch có thể được cấu hình đồng bộ hoặc bất đồng bộ; số đếm không phải transactional business counter. Mục đích của observer là chẩn đoán. Không đưa các counter in-memory này thành nguồn dữ liệu kế toán hoặc SLA chính thức.

### 12.1. Event multicaster và thứ tự listener

Với `ApplicationEventMulticaster` chạy đồng bộ, listener được gọi trên luồng xử lý phát event. Khi multicaster dùng `TaskExecutor` bất đồng bộ:

- Listener có thể thực hiện sau khi lời gọi truy vấn đã trả.
- Thứ tự tương đối giữa nhiều listeners/operations có thể khác.
- Exception từ listener có thể không lan trở lại caller theo cùng cách như callback đồng bộ.
- Mutation của event source không phải cách đáng tin để thay đổi entity được persistence layer lưu.

**Khi logic phải ảnh hưởng tới entity đang save**, dùng `EntityCallback` thích hợp và kiểm thử đường save; không dựa vào một async event listener.

### 12.2. Event before/after delete không mang deleted entity cho từng dòng

Với `remove(Query.query(...), CatalogEntry.class)`, có thể phát `BeforeDeleteEvent`/`AfterDeleteEvent` ở scope operation. Do đó, không làm:

~~~text
onAfterDelete:
  giả định event.getSource() là entity đã xóa
  tính giá trị đơn hàng từ entity ấy
  gửi từng email dựa trên giá trị ấy
~~~

Một delete bằng filter có thể ảnh hưởng không, một hoặc nhiều document. Đếm `beforeDeleteCount = 1` không thể suy ra một document đã bị xóa.

### 12.3. Tránh log dữ liệu cá nhân

`AfterLoadEvent` có thể cung cấp raw BSON gồm toàn bộ field, kể cả PII, token hoặc thông tin nhạy cảm. Không log `event.getSource()` nguyên văn trong production. Nếu phải debug, chỉ log ID được phép, operation name và metrics đã khử dữ liệu nhạy cảm theo policy.

## 13. Đường API nào thực sự đi qua lifecycle?

Một ứng dụng Spring Data MongoDB có nhiều đường truy cập database. Không thể áp dụng quy tắc “mọi ghi đều có before/after save” cho chúng.

| Đường truy cập | Có entity mapping? | Có thể trông đợi save EntityCallbacks? | Ghi chú |
|---|---|---|---|
`repository.save(entity)` | Có | Có, cho đường lưu entity tương ứng | Chịu ảnh hưởng callbacks đã đăng ký |
`mongo.insert(entity)` | Có | Có, cho pipeline insert entity | Không tương đương replace/upsert |
`mongo.save(entity)` | Có | Có, cho pipeline save entity | Cẩn thận stale replacement |
`mongo.find(..., CatalogEntry.class)` | Có | Không phải save; đọc có hook riêng | After-load/after-convert |
`mongo.updateFirst(query, update, CatalogEntry.class)` | Có thể mapping property path trong query/update | **Không** coi là gọi `BeforeConvertCallback` của toàn entity | Update operators, không materialize entity để save |
`mongo.updateMulti(...)` | Có thể mapping query/update | Không phải một lần save từng entity | Nhiều document thay đổi nguyên tử riêng |
`mongo.findAndModify(...)` | Mapping query/update và có thể mapping entity kết quả | Không phải `save(entity)` | Read hooks cho kết quả phụ thuộc đường API/option |
`mongo.remove(query, CatalogEntry.class)` | Mapping query và collection | Không phải entity save callbacks | Có thể có delete lifecycle events |
`mongo.bulkOps(...).execute()` | Có một số mapping support theo operation | Không dựa vào before/after convert/save per item | Tối ưu bulk có đường lifecycle riêng |
`mongo.getCollection(...).updateOne(...)` | Raw driver path | Không | Bypass mapping/callback Spring Data |

Hãy đọc bảng như một **bản đồ rủi ro thiết kế**: khi cần guarantee về callback cho một method cụ thể, xác minh bằng integration test trên version đang chạy. Đặc biệt không dùng “có entity class trong tham số update” để suy rằng framework phải tạo entity object, gọi callback rồi mới update.

### 13.1. Phản ví dụ: partial update có thể bỏ qua normalized key

Giả sử một document đã lưu:

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "sku": " bottle-500 ",
  "sku_normalized": "BOTTLE-500"
}
~~~

Một code path khác chạy:

~~~java
mongo.updateFirst(
        Query.query(Criteria.where("id").is("p-101")
                .and("tenantId").is("tenant-a")),
        new Update().set("sku", "  mug-250  "),
        CatalogEntry.class);
~~~

Vì đây là partial update, code không được suy rằng `BeforeConvertCallback<CatalogEntry>` sẽ được gọi để tính lại `normalizedSku`. Database có thể còn:

~~~json
{
  "sku": "  mug-250  ",
  "sku_normalized": "BOTTLE-500"
}
~~~

Đó là **mất đồng bộ business invariant**, dù cả hai field đều có tên BSON hợp lệ.

Các phương án:

1. Tầng service chuẩn hóa SKU và update **cả `sku` + `sku_normalized` trong cùng một lệnh**.
2. Nếu cần tính bằng giá trị hiện tại trên server, dùng aggregation pipeline update phù hợp và kiểm tra semantics.
3. Tập trung quyền ghi thuộc tính vào một đường persistence đã được kiểm thử; hạn chế các writer khác.
4. Dùng unique index + schema validation phù hợp, nhưng nhớ rằng chúng **không tự suy ra** quan hệ `normalize(sku) == sku_normalized`.
5. Có job đối soát/migration dữ liệu legacy để phát hiện lệch.

**Không coi callback là trigger MongoDB server.** Callback Java chỉ chạy trên những operation đi qua infrastructure của Spring Data tương ứng.

### 13.2. Phản ví dụ: raw insert bỏ qua cả before-convert

~~~java
mongo.getCollection("catalog_entries").insertOne(
        new org.bson.Document("_id", "raw-1")
                .append("tenantId", "tenant-a")
                .append("sku", " mug-250 "));
~~~

Đây là raw driver operation, không đi qua `NormalizeSkuBeforeConvert`. Document có thể thiếu `sku_normalized` nếu MongoDB schema validation không từ chối. Sau này đọc qua repository **không tự chạy lại before-convert của đường save**.

### 13.3. Lúc nào chọn custom converter thay vì callback?

Nếu cần chuyển đổi một **kiểu dữ liệu** (ví dụ một value object thành biểu diễn BSON riêng và ngược lại), `MongoCustomConversions`/`Converter` có thể phù hợp hơn. Nếu cần chuẩn hóa một **entity trước save**, `BeforeConvertCallback` phù hợp hơn.

Không dùng entity callback để thay thế mapping type converter cho mọi field cùng kiểu; cũng không dùng converter để gọi HTTP, cấp quyền tenant hay ghi audit.

## 14. Root entity, nested object, DBRef và scope callback

Lifecycle events của Spring Data MongoDB thường được phát cho **root-level document types** trong các hoạt động mapping/CRUD phù hợp. Một object lồng như `ShippingAddress` trong document `Order` **không nhất thiết nhận lifecycle event riêng**.

Ví dụ:

~~~java
@Document(collection = "orders")
public record OrderDocument(
        @MongoId String id,
        String tenantId,
        ShippingAddress address) {
}

public record ShippingAddress(
        String street,
        String city) {
}
~~~

Khi `OrderDocument` được save:

- `BeforeConvertCallback<OrderDocument>` là callback cho root entity khi đường save hỗ trợ.
- Không được mặc định rằng `BeforeConvertCallback<ShippingAddress>` sẽ được gọi như một write độc lập.
- Embedded object được converter ánh xạ như thành phần của root document.
- `@DBRef`/`@DocumentReference` và các cơ chế lazy resolution có lifecycle/lookup khác; không coi chúng là một embedded object luôn được load cùng lúc.

### 14.1. Vì sao giới hạn root-level quan trọng?

Nếu bạn đặt validation quan trọng trong một callback chỉ đăng ký cho nested `ShippingAddress`, save root `OrderDocument` có thể không gọi callback đó theo cách dự đoán. Hãy validate nested object từ root callback/domain validation hoặc áp dụng schema validation phù hợp.

Không dựa vào callback của một value object để bảo đảm dữ liệu từ bulk update, raw driver hoặc hệ thống đồng bộ ngoài Java luôn hợp lệ.

### 14.2. Constructor mapping không giống vòng đời save

Khi đọc BSON thành Java record, `MappingMongoConverter` dùng constructor/record components để materialize object. Logic trong constructor có thể chạy trên **mọi lần tạo object**, kể cả khi không có database write; ngược lại `BeforeConvertCallback` thường gắn với một đường chuẩn bị ghi entity.

Nếu constructor có side effect như increment counter/gửi event, nó có thể chạy trong cả read paths và gây tác dụng ngoài mong muốn. Constructor nên phục vụ dữ liệu bất biến/validation thuần, không thay callback persistence.

## 15. Auditing callbacks: createdAt, updatedAt, createdBy

Spring Data MongoDB có cơ chế auditing cho các metadata thường gặp:

- `@CreatedDate`: thời điểm tạo entity;
- `@LastModifiedDate`: thời điểm sửa entity;
- `@CreatedBy` và `@LastModifiedBy`: định danh người thực hiện, cần `AuditorAware<?>` hoặc cơ chế tương ứng.

Thay vì tự viết callback tạo thời gian cho mọi entity, có thể bật auditing trong cấu hình:

~~~java
package com.example.catalog;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing
public class CatalogAuditingConfig {
}
~~~

Fragment trên chỉ minh họa **bật auditing**. Nếu cần `@CreatedBy` hoặc `@LastModifiedBy`, phải có `AuditorAware` bean phù hợp với security context. Với reactive auditing, dùng hạ tầng `ReactiveAuditorAware` và annotation/cấu hình reactive tương ứng theo phiên bản.

Một entity có thể khai báo:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;

public class AuditedCatalogEntry {
    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;
}
~~~

Đây là **fragment field minh họa** chứ chưa phải một `@Document` hoàn chỉnh. Trong ứng dụng thật phải bổ sung mapping ID, collection, constructor và getters/setters phù hợp.

### 15.1. Auditing và callback tự viết

Auditing thường được thực hiện trong lifecycle entity conversion; thứ tự tương đối với custom callbacks chịu ảnh hưởng của `@Order`/`Ordered` và implementation. Nếu custom callback yêu cầu `createdAt` đã được điền trước, phải kiểm tra order hoặc chuyển logic tới service/domain thay vì dựa vào may mắn.

### 15.2. Update operators có thể bỏ qua created/updated auditing

`mongo.updateFirst(query, new Update().set("status", "ACTIVE"), Entity.class)` không giống `repository.save(entity)`. Đừng mặc nhiên khẳng định `@LastModifiedDate` của mọi document được partial update sẽ luôn tăng do auditing callback.

Với partial update, có thể đặt `updatedAt` trong cùng `Update` hoặc dùng toán tử server phù hợp, theo consistency contract. Nếu cần auditing toàn diện trên các đường ghi khác nhau, thiết kế một chiến lược thống nhất thay vì giả định mọi API tự cập nhật timestamps.

### 15.3. createdAt và ID cũng có tính thời điểm

`@CreatedDate` có thể được thiết lập khi lifecycle của entity xác định một bản ghi mới. Nhưng cơ chế “new entity” phụ thuộc ID/version và mapping; một object mang ID cấp sẵn không mặc định có cùng nhận diện “mới” như object không ID.

Nếu logic cần phân biệt create/update chặt chẽ, hãy dùng các APIs phù hợp (`insert` vs `save`, unique index, hoặc `Persistable` khi thật sự cần) và test phiên bản framework. Không chỉ so sánh `id == null` trong callback rồi coi là cơ chế phân loại toàn hệ thống.

## 16. @Version, optimistic locking và callback: hai trách nhiệm khác

`@Version` trên entity hỗ trợ phát hiện stale write trong những đường persistence được Spring Data hỗ trợ. Nó **không phải lifecycle event** và không tự được áp dụng giống nhau cho raw driver/bulk/custom update.

Ví dụ:

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long version;
~~~

Fragment trên nằm trong entity class có trường version và mapping đúng. Khi `repository.save(entity)` dùng optimistic locking, version cũ có thể khiến write bị từ chối với `OptimisticLockingFailureException` nếu acknowledged write được bật.

### 16.1. Không thay version trong callback để “sửa” stale data

Một callback thấy version cũ rồi tự tăng version không giống CAS server. Việc kiểm tra xung đột phải gắn với **điều kiện write** bảo vệ phiên bản. Không dùng callback để bỏ qua lỗi stale entity hoặc ghi đè tài liệu mới.

### 16.2. AfterSave chưa chắc entity đã bền vững ở replica

Write concern, transaction commit và replication là các bảo đảm khác với callback được gọi:

- `AfterSaveCallback` có thể chạy trước transaction commit.
- Một lệnh write đã gửi nhưng có lỗi mạng có thể khiến application không biết outcome.
- Một reader trên secondary có thể thấy dữ liệu trễ tùy read preference/concern.

Đừng dùng sự xuất hiện của after-save event làm chứng từ “đã commit và mọi hệ thống đều nhìn thấy”.

## 17. Thiết kế xóa có kiểm soát: result, tenant và outbox

Để xóa một entity theo tenant một cách an toàn, nên đặt **tenant filter vào chính delete query**:

**CatalogEntryDeletionService.java**

~~~java
package com.example.catalog;

import com.mongodb.client.result.DeleteResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class CatalogEntryDeletionService {
    private final MongoTemplate mongo;

    public CatalogEntryDeletionService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public boolean removeOne(
            String authenticatedTenantId,
            String entryId) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || entryId == null || entryId.isBlank()) {
            throw new IllegalArgumentException("Input không hợp lệ");
        }

        Query query = Query.query(
                Criteria.where("id").is(entryId)
                        .and("tenantId").is(authenticatedTenantId));

        DeleteResult result =
                mongo.remove(query, CatalogEntry.class);
        return result.getDeletedCount() == 1;
    }
}
~~~

Ở đây `DeleteResult.getDeletedCount()` là số document đã xóa theo lệnh MongoDB có kết quả acknowledged. Không suy từ `BeforeDeleteEvent` rằng có đúng một document đã được xóa.

### 17.1. Nếu bắt buộc lưu audit cho mỗi document bị xóa?

Lựa chọn phù hợp tùy nhu cầu:

1. **Soft delete:** ghi `deletedAt`/`deletedBy` thay vì physical delete; cần index, TTL policy và quyền truy cập rõ.
2. **Delete một entity trong transaction:** đọc entity/ghi audit hoặc outbox cùng transaction rồi delete, với điều kiện/CAS bảo vệ document và test race.
3. **Change streams:** bắt thay đổi ở MongoDB để phục vụ đồng bộ/audit nếu topology/retention và cơ chế resume phù hợp; cần hiểu pre-images không mặc định luôn có.
4. **Outbox event:** lưu bền vững lý do/id/chính sách xóa trong transaction rồi publish bởi worker; consumer idempotent.

Một lifecycle listener không thể thay thế một log nghiệp vụ bền vững khi service crash hoặc một hệ thống khác xóa trực tiếp.

### 17.2. Xóa toàn bộ collection không phải 1000 before-delete callbacks

`dropCollection` và `deleteMany` có semantics khác entity-per-document delete. Tránh viết cơ chế audit bắt buộc phụ thuộc vào việc MongoDB sẽ phát **một Java event cho từng document**. Đối với `dropCollection`, còn cần kiểm tra quyền quản trị, scope test/prod và chiến lược migration.

## 18. Integration test: chứng minh BeforeConvert → BSON → AfterLoad

Mock `MongoTemplate` có thể chứng minh method được gọi, nhưng **không chứng minh** callback được đăng ký vào mapping infrastructure, BSON đã dùng đúng field name hay kết quả đọc thực sự materialize entity. Cần MongoDB test thật (ví dụ Testcontainers hoặc MongoDB test instance riêng).

`@DataMongoTest` trong Spring Boot 3.x tạo test slice cho Spring Data MongoDB, nhưng **không tự khởi động MongoDB server**. Phải cung cấp connection đến MongoDB test. Không dùng database production.

### 18.1. Seed và test luồng lưu/đọc

**CatalogEntryLifecycleIntegrationTest.java**

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import({
        NormalizeSkuBeforeConvert.class,
        ValidateMappedDocumentBeforeSave.class,
        CheckLoadedEntryAfterConvert.class,
        CatalogLifecycleObserver.class,
        CatalogEntryDeletionService.class
})
class CatalogEntryLifecycleIntegrationTest {

    @Autowired MongoTemplate mongo;
    @Autowired CatalogEntryRepository repository;
    @Autowired CatalogLifecycleObserver observer;
    @Autowired CatalogEntryDeletionService deletion;

    private CatalogEntry newEntry(String id, String sku) {
        return new CatalogEntry(
                id,
                "tenant-a",
                sku,
                "Bình nước 500 ml",
                null,
                Instant.parse("2026-11-20T08:00:00Z"));
    }

    @BeforeEach
    void prepare() {
        // Database test phải cô lập; không xóa collection thật.
        mongo.dropCollection(CatalogEntry.class);
    }

    @Test
    void beforeConvertNormalizesAndBeforeSaveChecksMappedBson() {
        repository.save(newEntry("p-101", " bottle-500 "));

        Document raw = mongo.getCollection("catalog_entries")
                .find(new Document("_id", "p-101"))
                .first();

        assertThat(raw).isNotNull();
        assertThat(raw.getString("sku")).isEqualTo(" bottle-500 ");
        assertThat(raw.getString("sku_normalized"))
                .isEqualTo("BOTTLE-500");
        assertThat(raw.containsKey("normalizedSku")).isFalse();
    }

    @Test
    void findByIdConvertsBsonBackToJavaRecord() {
        repository.save(newEntry("p-101", " bottle-500 "));

        int loadEventsBefore = observer.afterLoadCount();

        CatalogEntry loaded = repository.findById("p-101")
                .orElseThrow();

        assertThat(loaded.normalizedSku())
                .isEqualTo("BOTTLE-500");
        assertThat(loaded.tenantId()).isEqualTo("tenant-a");
        assertThat(loaded.sku()).isEqualTo(" bottle-500 ");

        // Chỉ khẳng định khi dùng event multicaster đồng bộ mặc định.
        assertThat(observer.afterLoadCount())
                .isGreaterThan(loadEventsBefore);
    }

    @Test
    void derivedQueryUsesJavaPropertyAndMappedBsonField() {
        repository.save(newEntry("p-101", " bottle-500 "));

        assertThat(repository
                .findFirstByTenantIdAndNormalizedSku(
                        "tenant-a", "BOTTLE-500"))
                .isPresent()
                .get()
                .extracting(CatalogEntry::id)
                .isEqualTo("p-101");
    }

    @Test
    void tenantScopedDeleteDoesNotRemoveOtherTenant() {
        repository.save(newEntry("p-101", " bottle-500 "));
        repository.save(new CatalogEntry(
                "p-201",
                "tenant-b",
                " bottle-500 ",
                "Bình nước tenant-b",
                null,
                Instant.parse("2026-11-20T08:00:00Z")));

        assertThat(deletion.removeOne(
                "tenant-b", "p-101")).isFalse();
        assertThat(deletion.removeOne(
                "tenant-a", "p-101")).isTrue();

        assertThat(repository.findById("p-101")).isEmpty();
        assertThat(repository.findById("p-201")).isPresent();
    }
}
~~~

### 18.2. Giải thích test

Test đầu chứng minh:

1. `repository.save(...)` chạy callback chuẩn hóa SKU.
2. Converter ánh xạ property `normalizedSku` thành `sku_normalized`.
3. `BeforeSaveCallback` không ném exception khi BSON đúng.
4. Raw driver read được chính Document đã lưu, không phải chỉ object do test tự tạo.

Test đọc chứng minh `findById(...)` materialize một `CatalogEntry` với Java property tương ứng. Test quan sát event chỉ được xem là **deterministic khi multicaster đồng bộ**; nếu dự án dùng multicaster async, không assert immediate event counts mà không có đồng bộ test riêng.

Test delete chứng minh **filter tenant được thực thi tại database**. Nó không khẳng định có một event cho mỗi document bị xóa. Một kết quả `false` có thể là không tồn tại hoặc sai tenant — không được tùy tiện tiết lộ thông tin tenant khác trong API response.

### 18.3. Khi test callback không được đăng ký

Nếu `@DataMongoTest` không nạp `@Component` callback tùy biến vì test slice chỉ quét một phần application context, `@Import(...)` như ví dụ giúp đăng ký chúng tường minh.

Tuy nhiên, nếu production đăng ký callback theo một cấu hình khác (thứ tự `@Order`, custom converter, auditing), phải có **ít nhất một integration test theo gần production context** để tránh test slice pass nhưng cấu hình runtime khác.

### 18.4. Kiểm thử unique index

Nếu doanh nghiệp yêu cầu unique (`tenantId`, `sku_normalized`), test cần tạo index trên **database test** trước khi insert:

~~~java
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;

mongo.getCollection("catalog_entries").createIndex(
        new Document("tenantId", 1)
                .append("sku_normalized", 1),
        new IndexOptions()
                .name("uq_entry_tenant_sku")
                .unique(true));
~~~

Fragment này đặt trong setup/test có `mongo`. Khi index tồn tại, hai SKU cùng chuẩn hóa trong cùng tenant phải bị MongoDB từ chối ở mức unique constraint; hai tenant khác nhau có thể dùng cùng normalized SKU nếu business rule cho phép.

Không lấy việc callback normalize đúng một lần làm bằng chứng uniqueness được bảo vệ dưới ghi cạnh tranh.

## 19. Integration test: partial update và raw driver bỏ qua save callback

Khi review một hệ thống có nhiều đường ghi, test chỉ `repository.save(...)` là chưa đủ.

### 19.1. Thử updateFirst trên document đã lưu

Phương thức test bổ sung vào `CatalogEntryLifecycleIntegrationTest`:

~~~java
@Test
void partialUpdateDoesNotRecalculateDerivedSkuField() {
    repository.save(newEntry("p-101", " bottle-500 "));

    mongo.updateFirst(
            Query.query(Criteria.where("id").is("p-101")
                    .and("tenantId").is("tenant-a")),
            new Update().set("sku", " mug-250 "),
            CatalogEntry.class);

    Document raw = mongo.getCollection("catalog_entries")
            .find(new Document("_id", "p-101")).first();

    assertThat(raw).isNotNull();
    assertThat(raw.getString("sku")).isEqualTo(" mug-250 ");
    assertThat(raw.getString("sku_normalized"))
            .isEqualTo("BOTTLE-500");
}
~~~

Cần import `Criteria`, `Query` và `Update` từ `org.springframework.data.mongodb.core.query`. Đây là **test phản chứng có chủ đích**: sau partial update, normalized SKU trở nên cũ vì trước-convert callback **không chạy trên một entity đầy đủ**. Bài học không khuyến nghị tạo state sai như vậy ở production; phải cập nhật cả hai field nguyên tử hoặc thay kiến trúc.

### 19.2. Thử native driver insert

~~~java
@Test
void rawDriverInsertDoesNotInvokeSpringBeforeConvert() {
    mongo.getCollection("catalog_entries").insertOne(
            new Document("_id", "raw-1")
                    .append("tenantId", "tenant-a")
                    .append("sku", " raw-sku "));

    Document raw = mongo.getCollection("catalog_entries")
            .find(new Document("_id", "raw-1"))
            .first();

    assertThat(raw).isNotNull();
    assertThat(raw.containsKey("sku_normalized")).isFalse();
}
~~~

Kết quả chứng minh không thể coi callback Java là **MongoDB server trigger**. Nếu cần bắt buộc field ở **mọi** đường ghi, cân nhắc schema validation, API contract và kiến trúc chỉ cho phép write có kiểm soát. Schema validation có thể bắt field không được thiếu nhưng không tự tính normalized SKU theo quy tắc Java.

### 19.3. Kiểm tra callback exception

~~~java
@Test
void invalidSkuIsRejectedBeforeWriting() {
    assertThatThrownBy(() ->
            repository.save(newEntry("invalid", "   ")))
            .isInstanceOf(IllegalArgumentException.class);

    assertThat(repository.findById("invalid")).isEmpty();
}
~~~

Cần static import `org.assertj.core.api.Assertions.assertThatThrownBy`. Test này phụ thuộc callback `NormalizeSkuBeforeConvert` đã đăng ký và lệnh save không gửi tới driver nếu callback ném lỗi.

**Không kết luận** raw driver insert cũng bị từ chối bởi cùng callback. Muốn xác minh tính bắt buộc toàn database cần test riêng đường raw + JSON schema validation.

## 20. Callback trong Reactive MongoDB

Khi dùng `ReactiveMongoTemplate` hoặc `ReactiveMongoRepository`, Spring Data có các interfaces reactive như `ReactiveBeforeConvertCallback<T>`. Chúng trả `Publisher<T>` để tham gia luồng xử lý bất đồng bộ.

Ví dụ minh họa trong một ứng dụng reactive:

~~~java
package com.example.catalog;

import java.util.Locale;
import org.reactivestreams.Publisher;
import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReactiveSkuNormalization
        implements ReactiveBeforeConvertCallback<CatalogEntry> {

    @Override
    public Publisher<CatalogEntry> onBeforeConvert(
            CatalogEntry entity, String collection) {
        return Mono.fromSupplier(() -> {
            if (!"catalog_entries".equals(collection)) {
                return entity;
            }
            if (entity.sku() == null
                    || entity.sku().isBlank()) {
                throw new IllegalArgumentException("SKU rỗng");
            }
            String normalized = entity.sku().strip()
                    .toUpperCase(Locale.ROOT);
            return new CatalogEntry(
                    entity.id(),
                    entity.tenantId(),
                    entity.sku(),
                    entity.displayName(),
                    normalized,
                    entity.createdAt());
        });
    }
}
~~~

Lưu ý:

- Callback reactive dùng **Publisher** và được compose vào reactive pipeline, không được gọi `block()` hoặc `subscribe()` tùy tiện bên trong callback.
- `Mono.fromSupplier(...)` trì hoãn tính toán đến khi publisher được subscribe, giúp propagation lỗi phù hợp với Reactor.
- Transaction reactive dùng `ReactiveMongoTransactionManager` và Reactor Context; imperative `MongoTransactionManager` không tự bảo vệ reactive flow.
- Async event multicaster và reactive EntityCallbacks **không phải cùng cơ chế**.
- Cần thống nhất pure normalization policy giữa imperative và reactive code; không copy hai phiên bản khác nhau rồi để business keys lệch.

### 20.1. Bất đồng bộ không làm callback an toàn với side effect

Nếu một `ReactiveAfterSaveCallback` publish message ra Kafka, message có thể được gửi trước transaction commit hoặc lặp sau retry/resubscription. Điều đúng vẫn là **outbox, idempotency và kiểm soát commit**, không phải chuyển callback từ imperative sang reactive.

### 20.2. Không tự đăng ký callback trùng

Một ứng dụng có thể có cả bean callback imperative và reactive dành cho cùng entity class, nhưng cách infrastructure phát hiện/gọi từng loại phải được cấu hình và kiểm thử cụ thể. Không suy rằng một callback imperative sẽ tự áp dụng cho mọi operation của reactive repository.

## 21. Hiệu năng và observability của lifecycle hooks

Callback được gọi trong đường persistence có thể ảnh hưởng **latency của mọi insert/save/find** liên quan. Một đoạn code tưởng nhỏ nhưng thực hiện HTTP request, truy vấn thêm collection hoặc parse dữ liệu lớn ở từng entity sẽ làm hệ thống chậm rõ rệt.

| Công việc trong callback | Rủi ro | Lựa chọn phù hợp hơn |
|---|---|---|
Chuẩn hóa một chuỗi ngắn, thuần Java | Thường chi phí nhỏ | `BeforeConvertCallback` với unit/integration test |
Kiểm tra một field BSON đã map | Chi phí thấp nếu logic đơn giản | `BeforeSaveCallback` |
Gọi HTTP API để điền metadata | Latency không dự đoán, timeout, side effect | Service orchestration và retry policy rõ |
Publish message/email | Gửi trước commit, duplicate/retry | Transactional outbox |
Đọc nhiều document khác để validate | Race, N+1 query, deadlock/contension | Conditional write, transaction hoặc domain service |
Đọc và ghi lại entity trong AfterConvert | Recursion, mỗi read thành write | Migration/repair job |
Log nguyên raw Document | Lộ PII/secret, I/O lớn | Structured metrics, redaction |
Increment counter in-memory trong AfterSave | Không bền vững, không gắn commit, lỗi đa instance | Metrics chuyên dụng hoặc domain event bền vững |

### 21.1. Đo ở mức operation, không chỉ callback

Để biết callback có làm chậm ứng dụng hay không:

1. Đo latency p50/p95/p99 của query/save thực tế.
2. So sánh trên workload đại diện khi bật/tắt **một callback phụ** trong môi trường test.
3. Quan sát số lần callback chạy cho các đường API khác nhau.
4. Kiểm tra query plan bằng `explain("executionStats")` nếu độ trễ chủ yếu ở MongoDB.
5. Ghi lại lỗi do validation callback, network exception và transaction abort riêng biệt.
6. Tránh đo mỗi callback bằng log không đồng bộ rồi suy đó là thời gian commit.

Không đặt business invariant dưới một async observer chỉ vì observer có độ trễ thấp. Đúng đắn dữ liệu quan trọng hơn việc giảm vài microseconds khi thiết kế hook.

### 21.2. Root callbacks có thể chạy nhiều lần

Trong một API batch có nhiều lần `repository.save(entity)`, callbacks có thể chạy trên mỗi lần lưu entity. Nếu ứng dụng retry `save` sau lỗi hoặc caller gọi lại cùng operation, callbacks có thể được gọi lại. Vì vậy cần **idempotency/pure function** và không biến callback thành nơi thu tiền hoặc tăng counter nghiệp vụ.

### 21.3. Không cần callback cho logic thuần domain

Không phải mọi quy tắc chuẩn hóa đều nên “ẩn” ở persistence layer. Với SKU cần sử dụng ở nhiều nơi, có thể định nghĩa:

~~~java
public final class SkuPolicy {
    private SkuPolicy() {}

    public static String normalize(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("SKU rỗng");
        }
        return input.strip()
                .toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Đây là một pure function có thể được service, callback, importer và unit test dùng chung. Callback chỉ là **một điểm áp dụng** của policy, không phải nguồn gốc duy nhất của quy tắc.

## 22. Chẩn đoán lỗi thường gặp

| Biểu hiện/sai lầm | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
`BeforeConvertCallback` không chạy | Bean chưa được scan/import | Kiểm tra `@Component`/`@Bean` và test context |
Chạy với `MongoCollection.insertOne` nhưng callback không chạy | Raw driver bypass Spring mapping | Đi qua Spring Data mapping hoặc áp dụng validation riêng |
`updateFirst` không tự chuẩn hóa field liên quan | Không materialize entity để save | Update đủ field nguyên tử; đừng dựa vào save callback |
`BeforeSaveCallback` đọc `normalizedSku` trong BSON và thấy null | Tên field vật lý là `sku_normalized` | Kiểm tra `@Field` và raw BSON |
Callback trả entity cũ dù tính ra bản mới | Không trả object đã biến đổi | Với immutable record, return bản mới |
Callback thay tenant từ thread-local | Có thể rò dữ liệu/sai tenant khi async | Tenant từ auth context và filter service |
Callback thay ID tùy thời điểm | ID mapping/generation thay đổi | Cấp ID rõ hoặc test lifecycle theo type |
`AfterConvertCallback` cập nhật DB mỗi lần đọc | Read trở thành write, có thể recursion | Migration job riêng |
`AfterSaveCallback` gửi email nhưng transaction rollback | Hook có thể chạy trước commit | Outbox/after-commit policy |
Application event listener sửa entity nhưng DB không đổi | Event không có contract mutation và có thể async | EntityCallback cho đường thao tác hỗ trợ |
Giả định listener chạy đúng thứ tự với auditing | Ordering không được định nghĩa theo ý người viết | `@Order` và test toàn pipeline |
Nested object không có event riêng | Event thường ở root entity | Validate từ root/domain/schema |
Delete event thiếu entity | Delete dùng query selector, không tải từng document | Lưu audit/ID chủ động |
`deleteMany` xóa 100 dòng nhưng listener đếm 1 | Event scope là operation, không per document | Xem `DeleteResult`, thiết kế audit riêng |
`findById` trả entity nhưng AfterLoad chưa được observer đếm | Multicaster async, listener chưa được đăng ký hoặc đường API khác | Test wiring và đồng bộ event nếu cần |
Callback ném lỗi nhưng raw driver ghi được | Callback chỉ chạy trong Spring path | DB schema validation/unique index và writer policy |
`@CreatedDate` không tăng trong partial update | Auditing callback không chạy như save | Đặt update timestamp trong write hoặc dùng policy riêng |
Custom callback và auditing ghi đè lẫn nhau | Thứ tự thực thi/ownership field không rõ | Xác định một owner và kiểm thử |
`@Version` không tự bảo vệ custom update | Version guard thiếu trong đường raw/bulk | CAS theo version trong filter |
Event observer đếm duplicate saves | Retry/subscription lặp | Idempotency và metric semantics |
Log `event.getSource()` làm lộ dữ liệu | Raw BSON chứa thông tin nhạy cảm | Redact/whitelist và điều chỉnh log level |
Test mock pass nhưng MongoDB dữ liệu sai | Mock không chạy converter/callback thật | Integration test trên MongoDB |
Test `dropCollection` trỏ nhầm DB | Test chưa cô lập URI | Database riêng, test connection validation |

### 22.1. Quy trình xác minh nhanh

Khi một normalized field bị thiếu sau save:

1. **Xác định operation** là `repository.save`, `MongoTemplate.save`, `updateFirst` hay raw driver.
2. **Kiểm tra bean wiring**: callback có nằm trong Spring context và đúng generic entity type?
3. **Kiểm tra collection/mapping**: `@Document(collection=...)`, `@Field`, kiểu ID, tên field BSON.
4. **Xác minh lệnh thực tế** bằng readback raw `Document` hoặc MongoDB Driver `CommandListener` trong môi trường test.
5. **Chạy integration test** chỉ riêng use case, không dựa vào Mockito verification.
6. **Đối chiếu với đường ghi khác**: import/bulk/migration có dùng cùng policy không?
7. **Xử lý dữ liệu đã sai** bằng migration/repair job, không kỳ vọng đọc lại sẽ tự sửa.

Đừng bật debug log toàn bộ BSON trong production để giải quyết một bug mapping; có thể vô tình ghi PII, credentials hoặc business payload vào log lâu dài.

## 23. Bài tập thực hành

**Bài 1 — Vẽ timeline.** Vẽ ba flow riêng cho `findById`, `save(entity)` và `remove(query)`. Đánh dấu chính xác điểm dùng object Java, raw BSON và MongoDB command. Phân biệt event với callback.

**Bài 2 — Root vs embedded.** Tạo entity `OrderDocument` có nested `ShippingAddress`. Đăng ký callback cho root và nested, kiểm tra đường save root thực sự gọi những hook nào. Giải thích vì sao không nên phụ thuộc vào nested event per object.

**Bài 3 — BeforeConvert immutable.** Tạo record `CatalogEntry`, callback trả record mới với SKU chuẩn hóa. Kiểm tra rằng SKU gốc không bị sửa và normalized SKU được lưu đúng.

**Bài 4 — BeforeSave BSON.** Ánh xạ `normalizedSku` thành `sku_normalized`, kiểm tra bằng `BeforeSaveCallback`. Cố ý đọc sai key `normalizedSku` để thấy khác biệt giữa Java property và BSON field.

**Bài 5 — AfterLoad vs AfterConvert.** Đăng ký `AbstractMongoEventListener<CatalogEntry>` để quan sát `AfterLoadEvent`, và `AfterConvertCallback<CatalogEntry>`. Ghi các đặc tính raw BSON/Java object mà từng hook quan sát, không log dữ liệu nhạy cảm.

**Bài 6 — AfterSave và rollback.** Trong MongoDB replica set test, thực hiện `save` rồi gây lỗi nghiệp vụ trong cùng transaction. Chứng minh after-save hook có thể chạy trước rollback; thiết kế outbox thay vì email trong callback.

**Bài 7 — Partial update bypass.** Lưu SKU đã chuẩn hóa rồi dùng `updateFirst` chỉ sửa `sku`. Kiểm tra normalized field có thể bị stale và sửa service để cập nhật cả hai field trong một lệnh.

**Bài 8 — Raw driver bypass.** Dùng `MongoCollection.insertOne` ghi document không có normalized field. Chứng minh Java callback không chạy, sau đó thiết kế schema validation hoặc writer policy.

**Bài 9 — Unique business key.** Tạo unique index `(tenantId, sku_normalized)`. Chạy hai concurrent inserts cùng normalized SKU. Phân biệt vai trò callback chuẩn hóa với database unique constraint.

**Bài 10 — Delete events.** Chạy `remove(query)` xóa nhiều document cùng tenant. So sánh `DeleteResult.getDeletedCount()` với số lần event listener được gọi. Không dùng event count như số document đã xóa.

**Bài 11 — Auditing.** Bật `@EnableMongoAuditing`, thêm `@CreatedDate` và `@LastModifiedDate` vào entity thật. Test insert/save/partial update, ghi lại operation nào cập nhật timestamps theo cấu hình đang dùng.

**Bài 12 — @Version.** Thêm `@Version`, đọc entity thành hai bản sao rồi save lần lượt. Chứng minh optimistic lock là điều kiện trên write, không phải cơ chế tự tăng version trong callback.

**Bài 13 — Event multicaster async.** Cấu hình một test event multicaster chạy bất đồng bộ, quan sát việc listener có thể chạy sau caller và thứ tự không được bảo đảm. Không viết assertion tức thời khi chưa có đồng bộ.

**Bài 14 — Reactive callback.** Tạo `ReactiveBeforeConvertCallback` trả `Mono`/`Publisher`; kiểm tra bằng `StepVerifier` khi save reactive. Không gọi `block()` hoặc `subscribe()` trong callback.

**Bài 15 — Integration test mapping.** Với `@DataMongoTest` và MongoDB test riêng, kiểm tra trước-convert, BSON mapping, read conversion, delete và raw driver bypass. Giải thích tại sao Mockito mock không đủ.

**Bài 16 — Hiệu năng.** Seed nhiều document; đo latency đọc/ghi khi callback chỉ chuẩn hóa chuỗi, khi callback làm việc nặng và khi callback chỉ ghi metric. Xác định cách giảm side effect và tránh query N+1 trong callback.

## 24. Ghi nhớ

Trong **Spring Data MongoDB**, cần phân biệt **đọc BSON → chuyển thành entity**, **entity → chuyển thành BSON → lưu**, và **xóa dựa trên selector**. Các giai đoạn này có lifecycle hooks riêng: `BeforeConvertCallback` xử lý entity Java trước mapping; `BeforeSaveCallback` nhìn mapped BSON; `AfterSaveCallback` quan sát sau write; `AfterLoadEvent` nhìn raw BSON trước mapping; `AfterConvertCallback` nhìn entity sau mapping. Delete events không có nghĩa bạn được cấp một entity đầy đủ cho từng document đã xóa.

**EntityCallback khác application mapping event.** Callback có thể trả entity mới và thuộc persistence pipeline ở đường operation được hỗ trợ; event thích hợp cho quan sát và có thể được phát bất đồng bộ. Không dựa vào event listener để sửa business state hay giả định callback áp dụng cho `updateFirst`, bulk writes và raw driver commands.

**Callback không thay thế các ràng buộc ở database hay transactional design**: normalized business key cần unique index khi phải duy nhất; invariant chống mất cập nhật cần CAS/`@Version`; multi-document consistency cần transaction khi phù hợp; gửi event/email sau commit cần outbox hoặc cơ chế delivery đáng tin. Tập trung validation/normalization thuần và nhẹ trong callback, giữ đúng filter tenant, và kiểm thử trên MongoDB thực với cả đường save lẫn các đường bypass trước khi triển khai production.
