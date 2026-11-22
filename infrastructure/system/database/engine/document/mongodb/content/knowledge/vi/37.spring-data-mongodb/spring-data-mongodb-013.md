# Kiểm chứng hành vi Spring Data với BSON, truy vấn và index thực tế trong MongoDB

## 1. Vì sao cần kiểm chứng tận MongoDB?

Spring Data MongoDB giúp mã Java thao tác với MongoDB bằng `MongoRepository`, `MongoTemplate`, `Criteria` và mapping annotations. Tuy nhiên, việc code biên dịch được, repository trả kết quả hoặc unit test mock pass **không bảo đảm** hệ thống thực sự lưu đúng BSON types, gửi đúng truy vấn hoặc sử dụng index mong muốn.

Giả sử entity có:

```java
@Field(name = "total", targetType = FieldType.DECIMAL128)
private BigDecimal amount;
```

Những câu hỏi thiết yếu:

1. Java `amount` có thật sự nằm ở BSON field `total`, kiểu `decimal`/Decimal128?
2. Derived method `findByAmountGreaterThanEqual` có tạo filter trên `total`?
3. Spring Data có thực sự bind tham số `BigDecimal` thành BSON Decimal128?
4. `@Indexed` hay `@CompoundIndex` trong source có làm index tồn tại trên server?
5. Khi index đã tồn tại, query planner có dùng nó không?
6. `null`, missing, Date timezone, embedded object và array có tạo kết quả bất ngờ?
7. Có rò dữ liệu giữa các tenant do điều kiện `$or` hoặc mất dữ liệu vì `save` entity partial?

Để kiểm chứng, phải quan sát **nhiều tầng bằng chứng**:

```text
Java: entity @Document, @Field, @MongoId
          |
          v
Spring Data: MappingMongoConverter / QueryMapper
          |
          v
Driver: actual BSON command
          |
          v
MongoDB: persisted BSON document
          |
          v
Index catalog: keys + options
          |
          v
Query planner: explain("executionStats")
          |
          v
Integration test + staging performance benchmark
```

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Dựng lab Spring Data MongoDB kết nối một MongoDB thật.
- So sánh Java entity với raw `org.bson.Document`, `$type` và collection options.
- Phân biệt `@Id`, `@MongoId`, `@Field`, BSON String/ObjectId, Decimal128, Date/Instant và field null/missing.
- So kết quả của derived query, `@Query`, `MongoTemplate` và `mongosh`.
- Kiểm tra actual command/filter/projection thay vì chỉ nhìn method name.
- Xác nhận index được tạo thật với `getIndexes()`/`listIndexes`.
- Đọc `IXSCAN`, `COLLSCAN`, `FETCH`, `SORT`, `nReturned`, `totalKeysExamined`, `totalDocsExamined`.
- Kiểm chứng unique/compound/partial/TTL/collation indexes.
- Viết integration tests với `@DataMongoTest`, Testcontainers hoặc database thử nghiệm riêng.
- Tránh test plan mong manh trên tập dữ liệu nhỏ.
- Xây quy trình kiểm chứng schema/query/index sau release hoặc migration.

**Phạm vi:** tập trung vào Spring Data MongoDB trong Java; bản chất của truy vấn và index vẫn do MongoDB Server quyết định.

---

## 2. Phân biệt năm lớp bằng chứng

| Lớp | Kiểm chứng gì? | Công cụ | Không tự chứng minh |
| --- | --- | --- | --- |
| Entity metadata | Developer dự định map Java thế nào | `@Document`, `@Field`, `@MongoId` | Dữ liệu server có đúng |
| Persisted BSON | MongoDB thật sự lưu kiểu và field gì | `mongosh`, `$type`, raw `Document` | Query đang dùng index |
| Emitted command | Filter/sort/projection nào được gửi | Driver `CommandListener`, query logs được redact | Lệnh có nhanh |
| Index catalog | Index đã tồn tại và option đúng | `getIndexes`, `listIndexes`, `IndexOperations` | Planner đã chọn index |
| Execution | Server đã quét keys/docs thế nào | `explain("executionStats")`, profiler | HTTP p95/p99 toàn ứng dụng |

### 2.1. Ba khẳng định dễ sai

- **“Đã viết `@Indexed`”** là bằng chứng từ source, không phải catalog.
- **“Index đã tồn tại”** là bằng chứng catalog, không chứng minh MongoDB sử dụng index cho query cụ thể.
- **“Explain có IXSCAN”** chứng minh có index scan, không chứng minh số keys examined nhỏ hoặc truy vấn tối ưu khi có traffic thật.

### 2.2. Mock không kiểm chứng MongoDB behavior

```java
when(repository.findByTenantIdAndStatus("A", "PAID"))
    .thenReturn(List.of(fakeOrder));
```

Mock xác minh service logic nhưng **không chạy** Spring Data query parser, BSON conversion, MongoDB filter, unique constraint, index catalog hay query planner. Vì vậy bài tập phải có **integration test trên MongoDB thật**, bên cạnh unit test.

---

## 3. Môi trường và dependencies

Ví dụ dùng:

- Java **17+**, có `record` để mô tả entity ngắn gọn.
- Spring Boot/Spring Data MongoDB phiên bản tương thích nhau.
- `spring-boot-starter-data-mongodb` cho API imperative.
- MongoDB Server phù hợp driver; MongoDB 8.0 là một lựa chọn lab.
- `mongosh`, JUnit 5, AssertJ.
- Testcontainers tùy môi trường CI/local.

Trong Gradle Kotlin DSL:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "<approved-boot-version>"
    id("io.spring.dependency-management") version "<approved-version>"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-mongodb")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Placeholders **không phải version có thể build**. Khi làm project thật phải dùng versions đã được duyệt và đối chiếu compatibility giữa Boot, Spring Data, driver và MongoDB Server. Spring Boot BOM thường quản lý Java Driver.

Cấu hình MongoDB lab:

```properties
spring.data.mongodb.uri=mongodb://127.0.0.1:27017/spring_data_bson_lab
```

Cách khai báo connection properties có thể khác giữa Spring Boot major versions. Đọc reference của đúng release khi kết nối Atlas hoặc production.

**An toàn thực hành:** chỉ dùng `drop()`, `insertMany()`, `createIndex()` và test destructive operations trong **lab**. Không mở public access, ghi password vào URI trong source, bật log BSON chứa PII, hoặc chạy explain query nặng trên production không được phép.

---

## 4. Entity: cố ý đặt Java property khác BSON field

Một cách dễ nhìn thấy mapping hoạt động là dùng các tên Java **khác tên field lưu ở MongoDB**.

### 4.1. OrderDoc.java

```java
package com.example.mongo;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDoc(
    @MongoId(FieldType.STRING)
    String id,

    String tenantId,

    @Field("order_no")
    String orderNo,

    String status,

    @Field(name = "total", targetType = FieldType.DECIMAL128)
    BigDecimal amount,

    @Field("created_at")
    Instant createdAt,

    @Field("ship")
    Shipping shipping,

    List<LineItem> items,

    String note
) {}

record Shipping(String city, String district) {}

record LineItem(String sku, int quantity) {}
```

Ba records cùng package minh họa domain model; tổ chức files/public visibility theo project.

### 4.2. Mapping contract

| Java property | BSON field | BSON type kỳ vọng |
| --- | --- | --- |
| `id` | `_id` | `string` bởi `@MongoId(FieldType.STRING)` |
| `tenantId` | `tenantId` | `string` |
| `orderNo` | `order_no` | `string` |
| `status` | `status` | `string` |
| `amount` | `total` | `decimal` (Decimal128) |
| `createdAt` | `created_at` | `date` |
| `shipping` | `ship` | `object` |
| `shipping.city` | `ship.city` | `string` |
| `items` | `items` | `array` |
| `note` | `note` | `string`, `null` hoặc missing tùy document |

### 4.3. @Id và @MongoId không tương đương tuyệt đối

Với `@Id String id`, Spring Data MongoDB có quy tắc tự chuyển giá trị String sang BSON ObjectId khi chuỗi có định dạng hợp lệ. Với `@MongoId(FieldType.STRING)`, yêu cầu lưu `_id` như String được diễn đạt rõ ràng.

Một ID dạng `"507f1f77bcf86cd799439011"` có thể được kiểm thử bằng:

```javascript
db.orders.findOne({ _id: "507f1f77bcf86cd799439011" });
db.orders.findOne({ _id: ObjectId("507f1f77bcf86cd799439011") });
```

Hai BSON values **khác kiểu** và không phải cùng key. Đừng đổi ID mapping khi chưa đo và migration dữ liệu cũ.

### 4.4. BigDecimal và Decimal128

`BigDecimal` là kiểu Java; BSON Decimal128 là representation ở MongoDB. `@Field(targetType = FieldType.DECIMAL128)` chỉ rõ chiến lược mapping. Điều này quan trọng khi dữ liệu tiền tệ cần độ chính xác thập phân.

Không tạo `BigDecimal` tiền từ một double như `new BigDecimal(19.99)` rồi kỳ vọng giá trị thập phân gốc được biểu diễn chính xác. Dùng `new BigDecimal("19.99")` hoặc dữ liệu đã được parse theo chính sách business.

### 4.5. Instant và Date

BSON Date lưu timestamp tính theo milliseconds từ epoch UTC. `Instant` có độ phân giải cao hơn; phần nanoseconds nhỏ hơn millisecond có thể mất khi round-trip. Với lọc “ngày theo múi giờ Việt Nam”, cần chuyển ngày local thành khoảng UTC trước khi query.

### 4.6. Metadata _class

Spring Data có thể thêm `_class` khi ghi entity do default type mapper. Field này giúp polymorphic type mapping nhưng có thể không phù hợp tài liệu do hệ thống khác ghi. Việc tắt hay thay type mapper phải được kiểm chứng với inheritance/subtypes và schema migration.

---

## 5. Dựng fixture BSON độc lập với Spring Data

Tạo dữ liệu từ `mongosh`, để test Java không tự tạo oracle cho chính converter mà nó đang dùng.

**Lệnh sau xóa collection lab: không chạy trên production.**

```javascript
const lab = db.getSiblingDB("spring_data_bson_lab");
lab.orders.drop();

lab.orders.insertMany([
  {
    _id: "A-001", tenantId: "A",
    order_no: "ORD-A-001", status: "PAID",
    total: NumberDecimal("125.50"),
    created_at: ISODate("2026-11-10T08:00:00Z"),
    ship: { city: "Hà Nội", district: "Ba Đình" },
    items: [
      { sku: "PEN", quantity: 2 },
      { sku: "BOOK", quantity: 1 }
    ],
    note: "ready"
  },
  {
    _id: "A-002", tenantId: "A",
    order_no: "ORD-A-002", status: "NEW",
    total: NumberDecimal("15.00"),
    created_at: ISODate("2026-11-11T08:00:00Z"),
    ship: { city: "Đà Nẵng", district: "Hải Châu" },
    items: [{ sku: "PEN", quantity: 1 }]
    // note missing
  },
  {
    _id: "A-003", tenantId: "A",
    order_no: "ORD-A-003", status: "PAID",
    total: NumberDecimal("200.00"),
    created_at: ISODate("2026-11-12T08:00:00Z"),
    ship: { city: "Hà Nội", district: "Cầu Giấy" },
    items: [{ sku: "BOOK", quantity: 5 }],
    note: null
  },
  {
    _id: "A-004", tenantId: "A",
    order_no: "ORD-A-004", status: "CANCELLED",
    total: NumberDecimal("5.00"),
    created_at: ISODate("2026-11-13T08:00:00Z"),
    ship: { city: "Cần Thơ", district: "Ninh Kiều" },
    items: []
  },
  {
    _id: "A-005", tenantId: "A",
    order_no: "ORD-A-005", status: "PAID",
    total: NumberDecimal("75.25"),
    created_at: ISODate("2026-11-12T08:00:00Z"),
    ship: { city: "Hải Phòng", district: "Lê Chân" },
    items: [{ sku: "PEN", quantity: 3 }]
  },
  {
    _id: "B-001", tenantId: "B",
    order_no: "ORD-B-001", status: "PAID",
    total: NumberDecimal("999.99"),
    created_at: ISODate("2026-11-10T09:00:00Z"),
    ship: { city: "Hà Nội", district: "Long Biên" },
    items: [{ sku: "BOOK", quantity: 2 }]
  },
  {
    _id: "B-002", tenantId: "B",
    order_no: "ORD-B-002", status: "PAID",
    total: NumberDecimal("30.00"),
    created_at: ISODate("2026-11-11T09:00:00Z"),
    ship: { city: "TP. Hồ Chí Minh", district: "Quận 1" },
    items: []
  },
  {
    _id: "B-003", tenantId: "B",
    order_no: "ORD-B-003", status: "NEW",
    total: NumberDecimal("15.00"),
    created_at: ISODate("2026-11-13T09:00:00Z"),
    ship: { city: "Đà Nẵng", district: "Sơn Trà" },
    items: [{ sku: "PEN", quantity: 1 }]
  }
]);

lab.orders.countDocuments({});
// 8
```

### 5.1. Oracle cho integration tests

| Điều kiện | ID mong đợi | Số |
| --- | --- | ---: |
| Tất cả | A-001..A-005 và B-001..B-003 | 8 |
| Tenant A | A-001..A-005 | 5 |
| Tenant B | B-001..B-003 | 3 |
| Tenant A và PAID | A-001, A-003, A-005 | 3 |
| Tenant A và total ≥100 | A-001, A-003 | 2 |
| Ship city là Hà Nội | A-001, A-003, B-001 | 3 |
| note missing | A-002, A-004, A-005, B-001, B-002, B-003 | 6 |
| note explicit null | A-003 | 1 |
| note bằng null theo MongoDB equality | Missing + explicit null | 7 |
| Same element sku=BOOK và quantity≥3 | A-003 | 1 |

Không assert thứ tự kết quả khi query không có sort.

---

## 6. Kiểm chứng raw BSON với $type

### 6.1. Quan sát trực tiếp trên server

```javascript
lab.orders.aggregate([
  {
    $project: {
      idType: { $type: "$_id" },
      orderNoType: { $type: "$order_no" },
      amountType: { $type: "$total" },
      dateType: { $type: "$created_at" },
      shipType: { $type: "$ship" },
      itemsType: { $type: "$items" },
      noteType: { $type: "$note" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
```

Mong đợi:

- `_id` → `string`.
- `order_no` → `string`.
- `total` → `decimal`.
- `created_at` → `date`.
- `ship` → `object`.
- `items` → `array`.
- `note` → `string`, `null` hoặc `missing`.

### 6.2. Kiểm tra decimal

```javascript
lab.orders.countDocuments({
  total: { $type: "decimal" }
});
// 8

lab.orders.find({
  tenantId: "A",
  total: { $gte: NumberDecimal("100.00") }
}).sort({ _id: 1 });
// A-001 và A-003
```

Một giá trị hiển thị là `125.50` trong GUI **không tự chứng minh** nó là Decimal128; có thể là double hoặc string nếu dữ liệu legacy lẫn kiểu.

### 6.3. Kiểm tra null/missing

```javascript
lab.orders.countDocuments({ note: null });
// 7

lab.orders.countDocuments({
  note: { $exists: false }
});
// 6

lab.orders.countDocuments({
  note: { $type: "null" }
});
// 1
```

MongoDB `{ note: null }` khớp explicit null **và missing**. Entity Java đọc cả hai thành `note == null` trong nhiều mapping configurations, nên chỉ đọc mapped entity không đủ để phân biệt.

### 6.4. Xem collection metadata

```javascript
lab.getCollectionInfos({ name: "orders" });
lab.orders.getIndexes();
```

Hai lệnh trả thông tin collection và index thật; không suy ra những thông tin đó chỉ từ annotation.

---

## 7. Kiểm chứng BSON trực tiếp từ Java

Spring Data thường chuyển BSON sang entity Java. Để kiểm tra **dữ liệu raw**, dùng MongoDB Java Driver qua `MongoTemplate.getDb()`:

```java
import org.bson.Document;
import org.bson.types.Decimal128;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import java.util.Date;

MongoCollection<Document> rawCollection =
    mongoTemplate.getDb().getCollection("orders");

Document raw = rawCollection.find(
    Filters.eq("_id", "A-001")
).first();

if (raw == null) {
    throw new AssertionError("Missing test document A-001");
}

System.out.println(raw.get("_id").getClass());
// class java.lang.String

System.out.println(raw.get("total").getClass());
// class org.bson.types.Decimal128

System.out.println(raw.get("created_at").getClass());
// class java.util.Date
```

`mongoTemplate` ở đây là bean được inject từ Spring context. `Document` trả về qua driver không được map thành `OrderDoc`, nên cung cấp một góc nhìn độc lập với entity conversion.

### 7.1. So hai mặt của một document

```java
OrderDoc mapped =
    mongoTemplate.findById("A-001", OrderDoc.class);

Document raw =
    mongoTemplate.getDb()
        .getCollection("orders")
        .find(Filters.eq("_id", "A-001"))
        .first();

assert mapped != null;
assert raw != null;

System.out.println(mapped.amount());   // BigDecimal
System.out.println(raw.get("total"));  // Decimal128

System.out.println(mapped.createdAt());     // Instant
System.out.println(raw.get("created_at"));  // Date
```

### 7.2. Converter.write chỉ là dự định serialize

```java
Document serialized = new Document();
mongoTemplate.getConverter().write(orderDoc, serialized);
System.out.println(serialized.toJson());
```

Điều này cho biết converter dự định ghi BSON gì, nhưng **không xác minh đã có write được server chấp nhận**. Sau `insert/save`, phải đọc lại raw document bằng query thực tế.

### 7.3. @Field remapping không thể bỏ qua

Một Java query theo `amount` phải trở thành filter theo BSON `total`; một Java query theo `shipping.city` phải trở thành BSON `ship.city`. Nếu viết raw query trực tiếp qua driver, phải dùng **BSON field names**, không dùng Java property names.

---

## 8. Kiểm chứng Java save → MongoDB → Java

Tạo một entity rồi lưu qua converter:

```java
OrderDoc newOrder = new OrderDoc(
    "A-100",
    "A",
    "ORD-A-100",
    "NEW",
    new BigDecimal("19.99"),
    Instant.parse("2026-11-14T08:00:00Z"),
    new Shipping("Hà Nội", "Ba Đình"),
    List.of(new LineItem("PEN", 2)),
    null
);

mongoTemplate.insert(newOrder);
```

Sau đó chạy:

```javascript
lab.orders.findOne(
  { _id: "A-100" },
  { total: 1, created_at: 1, ship: 1 }
);

lab.orders.aggregate([
  { $match: { _id: "A-100" } },
  {
    $project: {
      amountType: { $type: "$total" },
      createdAtType: { $type: "$created_at" }
    }
  }
]).toArray();
```

Kỳ vọng BSON `total` là Decimal128, `created_at` là Date, `_id` là String. Trên Java, đọc lại bằng `mongoTemplate.findById()` và so bằng `BigDecimal.compareTo()` hoặc AssertJ `isEqualByComparingTo`.

### 8.1. Instant có thể mất sub-millisecond precision

```java
Instant t =
    Instant.parse("2026-11-14T08:00:00.123456789Z");
```

BSON Date lưu milliseconds nên không đảm bảo bảo toàn `.456789` nanoseconds. Khi test round-trip, phải phát biểu contract độ chính xác chấp nhận được (ví dụ millisecond).

### 8.2. Tính khoảng ngày theo timezone business

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = LocalDate.of(2026, 11, 14)
    .atStartOfDay(zone)
    .toInstant();

Instant until = LocalDate.of(2026, 11, 15)
    .atStartOfDay(zone)
    .toInstant();
```

Truy vấn `[from, until)` bằng `$gte` và `$lt` để lấy “ngày 14/11 tại Việt Nam”. Không dùng timezone mặc định của JVM rồi coi là UTC.

---

## 9. Derived query: Java names và BSON names

Repository:

```java
package com.example.mongo;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDoc, String> {

    List<OrderDoc> findByTenantIdAndStatus(
        String tenantId,
        String status
    );

    List<OrderDoc> findByTenantIdAndAmountGreaterThanEqual(
        String tenantId,
        BigDecimal minimum
    );

    List<OrderDoc> findByShipping_City(String city);

    List<OrderDoc> findByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
        String tenantId,
        String status
    );

    long countByTenantIdAndStatus(
        String tenantId,
        String status
    );

    boolean existsByTenantIdAndOrderNo(
        String tenantId,
        String orderNo
    );
}
```

### 9.1. So với native query

| Java method | Native BSON filter/option |
| --- | --- |
| `findByTenantIdAndStatus("A","PAID")` | `{tenantId:"A",status:"PAID"}` |
| `findByTenantIdAndAmountGreaterThanEqual("A",100)` | `{tenantId:"A",total:{$gte:NumberDecimal("100")}}` |
| `findByShipping_City("Hà Nội")` | `{"ship.city":"Hà Nội"}` |
| `countByTenantIdAndStatus("A","PAID")` | Count theo tenant/status |
| `existsByTenantIdAndOrderNo("A","ORD-A-001")` | Exist filter theo `tenantId`, `order_no` |
| `...OrderByCreatedAtDescIdDesc` | Sort `{created_at:-1,_id:-1}` |

Kỳ vọng count PAID của tenant A = **3**; total≥100 = **A-001, A-003**.

### 9.2. Nested path và underscore

`findByShipping_City` chỉ rõ đường đi `shipping.city`; mapper đổi root property `shipping` thành BSON `ship`. Nếu entity có đồng thời Java property `shippingCity`, tên `findByShippingCity` có thể gây ambiguity trong parser. Underscore là một cách chỉ ra điểm tách.

### 9.3. Reserved ID methods

`findById` là method được định nghĩa sẵn, nhắm đến **identifier property**, không phải tùy ý một Java property tên `id` không được đánh dấu ID. Khi refactor ID entity, hãy test riêng `findById` và raw `_id`.

### 9.4. Derived query không tự kiểm soát tenant

Tên method như `findByTenantIdAndStatusOrActive` có thể tạo logic:

```javascript
{
  $or: [
    { tenantId: "A", status: "PAID" },
    { active: true }
  ]
}
```

Nhánh `active` không còn tenant filter, có thể trả dữ liệu tenant B. Viết explicit grouping và integration test **negative cases**.

---

## 10. @Query: khai báo filter và kiểm tra parameter binding

Spring Data cho phép khai báo MongoDB JSON:

```java
import org.springframework.data.mongodb.repository.Query;

@Query("{ 'tenantId': ?0, 'amount': { '$gte': ?1 } }")
List<OrderDoc> amountByQuery(
    String tenantId,
    BigDecimal minimum
);
```

- `?0`: tham số thứ nhất.
- `?1`: tham số thứ hai.
- Spring Data bind và map giá trị cùng query theo metadata của entity.

**Không nhầm** method string trong annotation là BSON command hoàn chỉnh sau mapping: field `amount` phải được đối chiếu với raw `total`, và có thể có sort/projection/options khác.

### 10.1. Query có OR đúng scope

```java
@Query("""
    {
      'tenantId': ?0,
      '$or': [
        { 'status': ?1 },
        { 'amount': { '$gte': ?2 } }
      ]
    }
    """)
List<OrderDoc> findTenantCandidates(
    String tenantId,
    String status,
    BigDecimal minimum
);
```

Kỳ vọng mọi kết quả đều có `tenantId` được yêu cầu. Một `@Query` khác đặt tenant filter **chỉ trong một nhánh** sẽ tạo lỗ hổng access control.

### 10.2. Tham số String và injection

Spring Data docs mô tả các tham số String được escaped khi binding, nên truyền chuỗi chứa `$ne` không tự biến chuỗi thành MongoDB operator. Tuy nhiên SpEL `?#{...}` có khả năng tạo expression/subdocument mạnh hơn; input phải được kiểm soát. Không nối JSON command từ input người dùng.

### 10.3. Projection fields

```java
@Query(
    value = "{ 'tenantId': ?0, 'status': ?1 }",
    fields = "{ 'status': 1, 'amount': 1, 'createdAt': 1 }"
)
List<OrderDoc> findLightweight(
    String tenantId,
    String status
);
```

Spring Data mapping sẽ áp field names BSON tương ứng trong hoàn cảnh được hỗ trợ. Cần kiểm chứng actual projection. Entity trả về chỉ chứa một số properties, có thể có nhiều `null` do **không được load**. **Không gọi `save` trên entity partial**; dùng read-only interface/DTO projection cho endpoints danh sách.

---

## 11. MongoTemplate, Criteria và QueryMapper

Spring Data có Fluent API:

```java
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Criteria;

Query query = new Query(
    Criteria.where("tenantId").is("A")
        .and("amount").gte(new BigDecimal("100.00"))
);

List<OrderDoc> result =
    mongoTemplate.find(query, OrderDoc.class);
```

`Query` được xây bằng **Java properties**. `Query.getQueryObject()` phản ánh query object ở tầng application và **có thể chưa qua mapping**.

### 11.1. Kiểm tra mapped query

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.convert.QueryMapper;

var converter = mongoTemplate.getConverter();
var mappingContext = converter.getMappingContext();
var entity = mappingContext.getPersistentEntity(OrderDoc.class);

QueryMapper mapper = new QueryMapper(converter);

Document mapped = mapper.getMappedObject(
    query.getQueryObject(),
    entity
);

System.out.println(mapped.toJson());
// Mong đợi BSON field "total", không phải Java "amount".
```

Điều này kiểm tra **mapping của filter**, chưa kiểm tra server actual plan hay final command chứa sort/skip/limit/session.

### 11.2. Đọc command thực bằng driver listener

MongoDB Java Driver có `CommandListener`, nhận `CommandStartedEvent`, `CommandSucceededEvent` và `CommandFailedEvent`.

```java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;
import java.util.concurrent.TimeUnit;

public final class SafeCommandListener implements CommandListener {

    @Override
    public void commandStarted(CommandStartedEvent event) {
        System.out.println(
            "command=" + event.getCommandName()
            + " db=" + event.getDatabaseName()
        );
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        System.out.println(
            "completed=" + event.getCommandName()
            + " nanos=" + event.getElapsedTime(TimeUnit.NANOSECONDS)
        );
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        System.err.println(
            "failed=" + event.getCommandName()
        );
    }
}
```

Gắn listener vào `MongoClientSettings.Builder.addCommandListener(...)` trong cấu hình client/Spring Boot customizer phù hợp version.

Trong **lab riêng không có dữ liệu nhạy cảm**, có thể tạm xem `event.getCommand().toJson()` để xác minh mapped filter/sort/projection. Trong production, **không log raw command values** vì có thể lộ email, tenant identifiers, query literals, credentials và business data.

### 11.3. Không đánh đồng ba kết quả

- `query.getQueryObject()` = biểu thức được ứng dụng xây.
- `QueryMapper.getMappedObject(...)` = biểu thức đã mapping.
- `CommandStartedEvent.getCommand()` = command thực tế gửi lên driver wire protocol, có thể chứa filter, sort, projection và các metadata khác.

Ngay cả command đúng cũng không chứng minh query nhanh; cần execution evidence.

---

## 12. Index phải tồn tại thật, không chỉ nằm trong annotation

Spring Data hỗ trợ index annotations như:

```java
@Indexed
String status;
```

```java
@CompoundIndex(
    name = "ix_tenant_status",
    def = "{ 'tenantId': 1, 'status': 1 }"
)
```

Nhưng **automatic index creation bị tắt mặc định từ Spring Data MongoDB 3.0**. Một entity có `@Indexed` không chứng minh collection đã có index.

### 12.1. Xác minh trực tiếp từ server

```javascript
lab.orders.getIndexes();

lab.runCommand({ listIndexes: "orders" });
```

Kỳ vọng ban đầu sau `insertMany`: chỉ có `_id_` index, nếu không có tác nhân khác tạo index.

### 12.2. Tạo indexes cho bài lab

```javascript
lab.orders.createIndex(
  { tenantId: 1, order_no: 1 },
  {
    name: "uq_tenant_order_no",
    unique: true
  }
);

lab.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    created_at: -1,
    _id: -1
  },
  {
    name: "ix_tenant_status_time"
  }
);

lab.orders.getIndexes();
```

Hai indexes khác nhau:

- Unique key `(tenantId, order_no)` bảo vệ business identifier.
- Compound key `(tenantId, status, created_at, _id)` hỗ trợ lọc theo tenant/status và sắp xếp theo thời gian+tie-breaker.

### 12.3. IndexOperations trong Spring Data

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;

mongoTemplate.indexOps(OrderDoc.class).ensureIndex(
    new Index()
        .on("tenantId", Sort.Direction.ASC)
        .on("orderNo", Sort.Direction.ASC)
        .unique()
        .named("uq_tenant_order_no")
);

mongoTemplate.indexOps(OrderDoc.class).ensureIndex(
    new Index()
        .on("tenantId", Sort.Direction.ASC)
        .on("status", Sort.Direction.ASC)
        .on("createdAt", Sort.Direction.DESC)
        .on("id", Sort.Direction.DESC)
        .named("ix_tenant_status_time")
);
```

Sau khi chạy phải **đọc lại `getIndexes()`** để xác nhận Spring Data đã mapping `orderNo` thành `order_no`, `createdAt` thành `created_at`, `id` thành `_id`.

Không dùng `ensureIndex` để tự ý đổi định nghĩa index cùng tên trên production. Nếu data/index options xung đột, phải có migration plan và change window.

### 12.4. Vì sao không luôn bật auto-index?

- Index build có cost CPU/disk/memory.
- Unique index có thể fail nếu dữ liệu đã trùng.
- Drop/recreate collection khi app đang chạy không mặc định tự tạo lại index.
- Cần kiểm soát thứ tự migrations và rollback.
- Sharded cluster có constraints riêng về unique indexes/shard keys.
- Có thể cần index hidden/partial/collation theo workload.

**Source annotations là ý định; index catalog mới là hiện trạng.**

---

## 13. Explain: index đã được sử dụng chưa?

Truy vấn repository:

```java
repository.findByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
    "A", "PAID"
);
```

MongoDB BSON query tương đương:

```javascript
lab.orders.find({
  tenantId: "A",
  status: "PAID"
})
.sort({
  created_at: -1,
  _id: -1
})
.explain("executionStats");
```

Các chỉ số cần đọc:

| Chỉ số/stage | Ý nghĩa |
| --- | --- |
| `nReturned` | Số documents trả trong execution |
| `totalKeysExamined` | Index keys đã quét |
| `totalDocsExamined` | Documents đã quét |
| `executionTimeMillis` | Thời gian của một lần thực thi explain |
| `IXSCAN` | Đã quét index |
| `COLLSCAN` | Đã quét collection |
| `FETCH` | Đã lấy document sau index |
| `SORT` | Có stage sắp xếp riêng |
| `winningPlan` | Plan được optimizer chọn |

### 13.1. Trên 8 records có thể vẫn COLLSCAN

MongoDB có quyền chọn `COLLSCAN` với dataset chỉ 8 documents dù index tồn tại; full scan đôi khi rẻ hơn đọc index. Đừng viết integration test cứng rằng `winningPlan` phải có `IXSCAN` trên tiny fixture.

### 13.2. Hint để kiểm tra index capability

```javascript
lab.orders.find({
  tenantId: "A",
  status: "PAID"
})
.sort({
  created_at: -1,
  _id: -1
})
.hint("ix_tenant_status_time")
.explain("executionStats");
```

`hint` ép một index cụ thể cho thử nghiệm phù hợp; nó **không chứng minh** planner sẽ tự chọn index đó khi không hint, hoặc plan này nhanh nhất cho tất cả workloads.

### 13.3. Đọc targeting ratio

\[
\text{Docs per result} =
\frac{\text{totalDocsExamined}}{\text{nReturned}}
\]

Ví dụ quét 100.000 documents, trả 20 documents → tỷ lệ 5.000. Nhưng nếu `nReturned=0`, không có mẫu số ý nghĩa; báo riêng docs scanned và zero results, đừng tự tạo một “per result ratio” giả.

### 13.4. IXSCAN vẫn có thể tệ

```text
IXSCAN keysExamined=400000
FETCH docsExamined=250000
nReturned=5
```

Query có index nhưng selectivity/prefix có thể không phù hợp. Cần xem predicates, sort, cardinality, index size và dữ liệu đại diện.

### 13.5. Plan JSON thay đổi theo server version

MongoDB có các execution engines khác nhau (classic/SBE) và output explain khác theo version, query shape. Tránh viết test bám cứng vào một đường JSON nội bộ của winningPlan mà không có compatibility strategy.

---

## 14. Compound index: filter và sort phải khớp

Index:

```javascript
{
  tenantId: 1,
  status: 1,
  created_at: -1,
  _id: -1
}
```

Phù hợp với:

```javascript
lab.orders.find({
  tenantId: "A",
  status: "PAID"
}).sort({
  created_at: -1,
  _id: -1
});
```

Nhưng query:

```javascript
lab.orders.find({ status: "PAID" })
  .sort({ created_at: -1 });
```

không có equality trên leading field `tenantId`, nên index trên có thể không phải lựa chọn hiệu quả.

### 14.1. Index field order

`{tenantId:1,status:1,created_at:-1}` khác `{created_at:-1,tenantId:1,status:1}`. Chọn thứ tự theo equality/range/sort, query patterns, cardinality và write cost.

### 14.2. Sort tie-breaker

A-003 và A-005 có cùng `created_at`, vì vậy nếu chỉ sort theo thời gian, thứ tự hai orders có thể thay đổi giữa các pages. Sắp xếp thêm `_id` giúp một thứ tự xác định cho dữ liệu đứng yên.

### 14.3. Covered query

Query có thể chỉ đọc index khi tất cả fields cần cho filter/projection đều có trong index và thỏa điều kiện của planner:

```javascript
lab.orders.find(
  { tenantId: "A", status: "PAID" },
  { tenantId: 1, status: 1, created_at: 1, _id: 0 }
);
```

Nếu phải trả `total` nhưng index không có `total`, thường cần `FETCH`. Đừng coi interface-based projection của Spring Data tự động làm query “covered”.

---

## 15. Unique index: kiểm chứng bằng duplicate error

Tạo index unique:

```javascript
lab.orders.createIndex(
  { tenantId: 1, order_no: 1 },
  { unique: true, name: "uq_tenant_order_no" }
);
```

Thử chèn trùng business key nhưng khác `_id` **chỉ trong lab**:

```javascript
lab.orders.insertOne({
  _id: "A-DUP",
  tenantId: "A",
  order_no: "ORD-A-001",
  status: "NEW",
  total: NumberDecimal("1.00"),
  created_at: ISODate("2026-11-14T08:00:00Z")
});
```

Mong đợi MongoDB từ chối với duplicate key (`E11000`), không thêm document.

### 15.1. existsBy không chống race

```java
if (!repository.existsByTenantIdAndOrderNo(
        "A", "ORD-A-001")) {
    repository.save(newOrder);
}
```

Hai requests đồng thời có thể cùng thấy `false` rồi insert. **Unique index** mới là bảo vệ ở database, ứng dụng cần xử lý `DuplicateKeyException` rõ ràng.

### 15.2. Unique index có thể không tạo được

Nếu dữ liệu cũ có duplicates, `createIndex(...,{unique:true})` sẽ lỗi. Trước migration cần:

1. Thống kê duplicates.
2. Xác định business merge/correction.
3. Kiểm tra null/missing business key fields.
4. Kiểm tra collation.
5. Tạo index trên staging có data đại diện.
6. Đánh giá write/index build overhead.
7. Thực hiện khi có change approval/rollback.

---

## 16. Partial index: không phải index toàn bộ documents

Một partial index chỉ chứa documents thỏa `partialFilterExpression`.

```javascript
lab.orders.createIndex(
  { tenantId: 1, created_at: -1 },
  {
    name: "ix_paid_recent",
    partialFilterExpression: {
      status: "PAID"
    }
  }
);
```

### 16.1. Query hợp lệ cho partial index

```javascript
lab.orders.find({
  tenantId: "A",
  status: "PAID"
}).sort({ created_at: -1 });
```

Query khớp subset có thể dùng partial index.

### 16.2. Query không đủ điều kiện

```javascript
lab.orders.find({
  tenantId: "A"
}).sort({ created_at: -1 });
```

Nếu dùng partial index chỉ chứa PAID để trả **mọi** đơn của tenant A, kết quả sẽ thiếu NEW/CANCELLED. Vì vậy planner không dùng partial index trong tình huống nó không thể đáp ứng kết quả đầy đủ.

### 16.3. Kiểm chứng

- Xem `partialFilterExpression` trong `getIndexes()`.
- So Explain có/không có điều kiện PAID.
- Không ép hint partial index thiếu điều kiện rồi lấy output thiếu làm business result.
- Với Spring Data, kiểm tra filter phát ra vẫn bao hàm partial predicate sau refactor repository.

---

## 17. TTL index: thời điểm xóa không tuyệt đối

MongoDB TTL monitor xóa documents đủ điều kiện **bất đồng bộ**, không phải đúng millisecond hết hạn.

Ví dụ collection sessions riêng, chỉ trong lab:

```javascript
lab.sessions.drop();

lab.sessions.insertMany([
  {
    _id: "S-old",
    createdAt: ISODate("2026-01-01T00:00:00Z")
  },
  {
    _id: "S-future",
    createdAt: ISODate("2030-01-01T00:00:00Z")
  }
]);

lab.sessions.createIndex(
  { createdAt: 1 },
  {
    name: "ttl_sessions_1day",
    expireAfterSeconds: 86400
  }
);
```

### 17.1. Kiểm thử đúng cách

- Kiểm tra raw field là BSON `date`.
- Kiểm tra index có option `expireAfterSeconds`.
- Nếu phải test deletion, dùng polling với timeout và bỏ giả định “biến mất ngay trong 1s”.
- TTL có các giới hạn về index type/options; không tự gắn TTL vào mọi compound index.
- Nếu business yêu cầu không hiển thị session quá hạn **ngay lập tức**, application phải lọc `expiresAt` đúng thời điểm, không chỉ trông chờ background TTL deletion.

### 17.2. Spring @Indexed(expireAfter)

Spring Data có TTL index metadata khi version hỗ trợ, nhưng annotation không chứng minh index đã tồn tại. Đọc `getIndexes()` và kiểm tra date type trên server.

---

## 18. Collation và Unicode: query/index phải phù hợp

Collation có thể quyết định so sánh chuỗi theo locale, case và dấu.

```javascript
lab.orders.createIndex(
  { "ship.city": 1 },
  {
    name: "ix_city_collated",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
```

Query:

```javascript
lab.orders.find({
  "ship.city": "hà nội"
}).collation({
  locale: "en",
  strength: 2
});
```

Locale `en` chỉ minh họa syntax; **không mặc định là lựa chọn chuẩn cho tiếng Việt**. Với business tiếng Việt phải xác định locale/normalization policy bằng test data thực.

### 18.1. Index collation và query collation

Index có collation khác với query có thể không hỗ trợ string comparison/sort như dự định. Kiểm chứng:

- `getIndexes()` cho collation.
- Actual command có collation gì?
- Explain index được chọn?
- Tests với chữ hoa/thường, dấu, Unicode normalization.

### 18.2. @Query collation

```java
@Query(
    value = "{ 'shipping.city': ?0 }",
    collation = "en"
)
List<OrderDoc> byCityWithCollation(String city);
```

Trên code thật dùng locale đúng policy và kiểm tra Spring Data mapping thành BSON `ship.city`. Không coi regex ignore-case là tương đương mọi collation-based equality.

---

## 19. Array query: cần $elemMatch nếu yêu cầu cùng phần tử

Fixture:

```javascript
{
  items: [
    { sku: "PEN", quantity: 2 },
    { sku: "BOOK", quantity: 1 }
  ]
}
```

Query:

```javascript
{
  "items.sku": "BOOK",
  "items.quantity": { $gte: 2 }
}
```

có thể khớp document trên bằng **hai phần tử khác nhau**, dù không có BOOK nào quantity≥2.

Dùng:

```javascript
{
  items: {
    $elemMatch: {
      sku: "BOOK",
      quantity: { $gte: 3 }
    }
  }
}
```

Kỳ vọng trong fixture: **A-003**.

Spring Data:

```java
@Query("""
{
  'tenantId': ?0,
  'items': {
    '$elemMatch': {
      'sku': ?1,
      'quantity': { '$gte': ?2 }
    }
  }
}
""")
List<OrderDoc> findWithLineItem(
    String tenantId,
    String sku,
    int minQty
);
```

Nếu có multikey index cho array field, cần đối chiếu compound multikey constraints, `$elemMatch` và Explain. Đừng chỉ kiểm tra Java result list mà không xem underlying array semantics.

---

## 20. Page, Slice, sort và count query

Một repository method:

```java
Page<OrderDoc> findByTenantIdAndStatus(
    String tenantId,
    String status,
    Pageable pageable
);
```

Gọi:

```java
Pageable pageRequest = PageRequest.of(
    0, 2,
    Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by(Sort.Direction.DESC, "id"))
);
```

`Page` chứa content và total. Framework **có thể chạy count query bổ sung** để tính `totalElements`, nhưng cũng có những tối ưu nên không assert cố định “luôn hai commands”.

### 20.1. Slice không nhất thiết tính total

```java
Slice<OrderDoc> findSliceByTenantIdAndStatus(
    String tenantId,
    String status,
    Pageable pageable
);
```

`Slice` thường chỉ cần biết có trang kế tiếp hay không, có thể lấy `pageSize + 1` kết quả và tránh count tổng.

**Không khai báo hai methods cùng tên/tham số nhưng chỉ khác Page/Slice return type**: Java không cho overload như thế.

### 20.2. Sort dùng Java properties

`Sort.by("createdAt", "id")` cần mapping thành BSON `created_at` và `_id`. Chỉ `createdAt` không đủ ổn định nếu timestamps trùng (fixture A-003 và A-005 có cùng created_at).

### 20.3. Deep offset có thể chậm

`PageRequest.of(50000,20)` chuyển thành skip lớn. Khi dữ liệu thay đổi giữa các requests, offset paging có thể gây duplicate/missing. Với large feeds nên cân nhắc keyset/scroll theo `(created_at, _id)` và index tương ứng.

---

## 21. Partial projection và nguy cơ save ghi đè

Một `@Query(fields=...)` có thể chỉ load `_id`, `status`, `total`:

```java
@Query(
    value = "{ 'tenantId': ?0 }",
    fields = "{ 'status': 1, 'amount': 1 }"
)
List<OrderDoc> findLightweight(String tenantId);
```

Dữ liệu bị bỏ khỏi projection có thể map thành `null`/default ở Java. Nếu service sửa một field rồi gọi `repository.save(partial)`, cơ chế save có thể **thay document với các fields bị thiếu**.

Giải pháp:

- Dùng DTO/interface projection cho read endpoints.
- Không dùng entity partial làm aggregate đầy đủ.
- Với patch, dùng targeted `MongoTemplate.updateFirst`/`@Update` theo filter và operator.
- Khi cần concurrency protection, dùng `@Version` hoặc conditional update, kiểm tra optimistic locking.

Ví dụ targeted update:

```java
Query q = new Query(
    Criteria.where("id").is("A-002")
        .and("tenantId").is("A")
);

Update update = new Update().set("status", "PAID");

mongoTemplate.updateFirst(
    q,
    update,
    OrderDoc.class
);
```

Spring Data mapping chuyển Java `id` thành `_id`.

---

## 22. Optimistic locking và concurrent writes

Một entity có:

```java
@Document("versioned_orders")
public class VersionedOrder {
    @MongoId(FieldType.STRING)
    private String id;

    @Version
    private Long version;

    private String status;

    // Constructors/getters/setters...
}
```

Spring Data có thể dùng version trong predicate khi save; hai clients cùng đọc version cũ rồi cùng sửa, một update sẽ bị từ chối khi version đã thay đổi.

Cần kiểm chứng bằng integration test với acknowledged write concern; low-level bulk/updates và custom paths **không tự có cùng semantics** của repository `save` trên versioned entity.

### 22.1. Scenario kiểm thử

1. Tạo document `id=V-1`, version ban đầu.
2. Hai sessions/application operations đọc cùng version.
3. Writer A đổi status và save.
4. Writer B save bản đọc cũ.
5. Mong đợi writer B bị optimistic locking failure theo API đã dùng.
6. Đọc raw document để xác minh chỉ state hợp lệ cuối cùng được lưu.

Đây là điều mock repository không xác nhận được.

---

## 23. Transactions phải kiểm chứng trên topology hỗ trợ

Hai lần `repository.save()` trên các collections khác nhau **không tự là atomic multi-document transaction**.

Trong Spring Data có `MongoTransactionManager`/`@Transactional` khi đã cấu hình. Multi-document transaction yêu cầu MongoDB deployment có hỗ trợ (replica set/sharded cluster theo version và điều kiện).

### 23.1. Test rollback

1. Bắt đầu transaction.
2. Insert order.
3. Insert audit event.
4. Ném exception trước commit.
5. Dùng raw BSON query sau transaction.
6. Assert không có partial side effects.

Không chạy transaction test trên standalone MongoDB rồi mặc định nó phải hoạt động giống replica set. Cần xem write concern/read concern, session lifecycle và retry semantics.

---

## 24. Kiểm chứng với @DataMongoTest

`@DataMongoTest` của Spring Boot tạo test slice tập trung vào Spring Data MongoDB/repositories và mapping.

Ví dụ minh họa cho package imports của Spring Boot 3.x:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class OrderRepositoryMappingTest {

    @Autowired
    MongoTemplate template;

    @Autowired
    OrderRepository repository;

    @Test
    void databaseIsLab() {
        assertThat(template.getDb().getName())
            .isEqualTo("spring_data_bson_lab");
    }
}
```

**Quan trọng:** test slice không tự tạo 8 fixture documents; cần seed riêng và một database URI cách ly. Với Spring Boot 4 hoặc phiên bản khác, test auto-configuration imports có thể thay đổi.

### 24.1. Testcontainers cho môi trường cách ly

Ví dụ **Testcontainers 1.x + Spring Boot 3.x** (module/package có thể khác ở Testcontainers 2.x):

```java
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@Testcontainers
@DataMongoTest
class OrderRepositoryIT {

    @Container
    static final MongoDBContainer mongo =
        new MongoDBContainer(
            DockerImageName.parse("mongo:8.0")
        );

    @DynamicPropertySource
    static void dbProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl
        );
    }

    // Inject MongoTemplate và OrderRepository.
    // Seed fixture trong @BeforeEach hoặc @Sql-equivalent setup.
    // Assert raw BSON, derived query và indexes.
}
```

Không trộn binary API/import của Testcontainers 1.x với 2.x. CI phải có container runtime hoặc dedicated MongoDB test deployment thay thế.

**Không fallback âm thầm** sang MongoDB production URI nếu Docker/test container không chạy được.

---

## 25. Integration test 1: kiểm tra field name và BSON type

Giả sử `mongoTemplate` được inject trong class test, code bên trong test:

```java
@Test
void persistsDecimal128AndMappedFields() {
    OrderDoc order = new OrderDoc(
        "A-TYPE",
        "A",
        "ORD-A-TYPE",
        "PAID",
        new BigDecimal("125.50"),
        Instant.parse("2026-11-14T08:00:00Z"),
        new Shipping("Hà Nội", "Ba Đình"),
        List.of(new LineItem("BOOK", 2)),
        "ok"
    );

    mongoTemplate.insert(order);

    Document raw = mongoTemplate.getDb()
        .getCollection("orders")
        .find(Filters.eq("_id", "A-TYPE"))
        .first();

    assertThat(raw).isNotNull();
    assertThat(raw.get("_id"))
        .isInstanceOf(String.class);
    assertThat(raw.get("total"))
        .isInstanceOf(Decimal128.class);
    assertThat(raw.get("created_at"))
        .isInstanceOf(Date.class);
    assertThat(raw.containsKey("amount")).isFalse();
    assertThat(raw.containsKey("createdAt")).isFalse();

    OrderDoc reread =
        mongoTemplate.findById("A-TYPE", OrderDoc.class);

    assertThat(reread.amount())
        .isEqualByComparingTo("125.50");
}
```

Imports gồm `org.bson.Document`, `org.bson.types.Decimal128`, `com.mongodb.client.model.Filters`, `java.util.Date`, `java.time.Instant`, `java.math.BigDecimal`, `java.util.List` và AssertJ.

Đây là **test contract BSON**, không chỉ test một giá trị Java.

---

## 26. Integration test 2: derived query bằng @Query

Giả sử fixture đã seed trên database test.

```java
List<OrderDoc> derived =
    repository.findByTenantIdAndAmountGreaterThanEqual(
        "A", new BigDecimal("100.00")
    );

List<OrderDoc> annotated =
    repository.amountByQuery(
        "A", new BigDecimal("100.00")
    );

Set<String> derivedIds = derived.stream()
    .map(OrderDoc::id)
    .collect(Collectors.toSet());

Set<String> annotatedIds = annotated.stream()
    .map(OrderDoc::id)
    .collect(Collectors.toSet());

assertThat(derivedIds)
    .containsExactlyInAnyOrder("A-001", "A-003");

assertThat(annotatedIds)
    .isEqualTo(derivedIds);
```

Với `@Query`:

```java
@Query("{ 'tenantId': ?0, 'amount': { '$gte': ?1 } }")
List<OrderDoc> amountByQuery(
    String tenantId,
    BigDecimal minimum
);
```

Đồng thời chạy native query bằng BSON field `total` để có oracle độc lập. Nếu Spring Data không map field như mong muốn, test phải thất bại.

### 26.1. Test nested mapping

```java
Set<String> ids =
    repository.findByShipping_City("Hà Nội")
        .stream()
        .map(OrderDoc::id)
        .collect(Collectors.toSet());

assertThat(ids).containsExactlyInAnyOrder(
    "A-001", "A-003", "B-001"
);
```

### 26.2. Test tenant isolation

Mọi API cho tenant A phải trả `tenantId == A` kể cả khi filter có `$or`, sort hoặc projection. Test A/B và thử điều kiện chỉ khớp một document của tenant B để phát hiện lỗ hổng truy cập chéo tenant.

---

## 27. Integration test 3: index catalog và duplicate

Sau khi tạo indexes trong test setup, kiểm tra:

```java
import org.springframework.data.mongodb.core.index.IndexInfo;

List<IndexInfo> infos =
    mongoTemplate.indexOps(OrderDoc.class)
        .getIndexInfo();

assertThat(infos)
    .extracting(IndexInfo::getName)
    .contains("uq_tenant_order_no", "ix_tenant_status_time");
```

Để xác minh **key order** và option `unique`, xem raw catalog:

```java
List<Document> rawIndexes =
    mongoTemplate.getDb()
        .getCollection("orders")
        .listIndexes()
        .into(new ArrayList<>());

rawIndexes.forEach(index ->
    System.out.println(index.toJson())
);
```

Có index đúng name nhưng sai `key`, `collation` hoặc `partialFilterExpression` vẫn có thể làm query/uniqueness sai.

### 27.1. Duplicate test

Nếu fixture đã có A-001 và unique index:

```java
assertThatThrownBy(() ->
    repository.save(new OrderDoc(
        "A-DUP",
        "A",
        "ORD-A-001",
        "NEW",
        new BigDecimal("1.00"),
        Instant.parse("2026-11-14T08:00:00Z"),
        new Shipping("Hà Nội", "Ba Đình"),
        List.of(),
        null
    ))
).isInstanceOf(DuplicateKeyException.class);
```

Nếu thiếu index ở test database, operation có thể thành công và assertion sẽ **phơi bày lỗi index provisioning**.

---

## 28. Integration test 4: đừng assert IXSCAN trên tiny fixture

Với chỉ 8 documents, planner có thể chọn `COLLSCAN` hợp lý. Không viết test bắt buộc:

```java
// Không nên coi đây là hợp đồng correctness trên mọi dataset:
assertThat(explain.toJson()).contains("IXSCAN");
```

Thay vào đó, chia kiểm chứng:

1. **Correctness:** trả đúng IDs, types, null/missing.
2. **Index catalog:** key/unique/collation/TTL/partial tồn tại.
3. **Index capability:** dùng hint trong lab và Explain để kiểm tra index phù hợp.
4. **Performance:** tạo dataset đại diện, đo scan counts và p95/p99 qua nhiều lần chạy.
5. **Production:** so logs/Atlas metrics sau rollout, có rollback nếu regression.

`executionTimeMillis` của một lần Explain không phải p99 latency của API. Công cụ profiler/APM mới cung cấp độ trễ theo workload.

---

## 29. Khi dữ liệu production lệch schema

Dữ liệu legacy:

```javascript
{
  _id: "LEGACY-1",
  tenantId: "A",
  amount: 125.50,
  createdAt: "2026-11-10",
  status: "PAID"
}
```

Entity mới mong đợi:

```javascript
{
  _id: "LEGACY-1",
  tenantId: "A",
  total: NumberDecimal("125.50"),
  created_at: ISODate("2026-11-10T00:00:00Z"),
  status: "PAID"
}
```

Hậu quả:

- Entity mapping có thể đọc `amount` là `null` hoặc ném conversion errors.
- Derived query filter `amount` mapping thành `total` không tìm thấy document cũ.
- Date string không tương đương BSON Date.
- Index trên `total` không giúp query những documents còn dùng old field `amount`.
- Một migration viết lại có thể làm mất precision nếu chuyển qua double không chủ ý.

### 29.1. Thống kê schema drift

```javascript
lab.orders.aggregate([
  {
    $group: {
      _id: {
        totalType: { $type: "$total" },
        createdAtType: { $type: "$created_at" }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]).toArray();
```

Với production lớn, cần xem resource impact. Có thể sampling, chạy trên staging hoặc dùng job được phê duyệt.

### 29.2. Migration plan

1. Inventory old/new field names và BSON types.
2. Thống kê raw documents theo `$type`.
3. Thiết kế converter/migration không mất precision/timezone.
4. Đảm bảo backward compatibility khi rolling deploy.
5. Có backup/rollback/monitoring.
6. Test BSON round-trip và repository queries.
7. Thực hiện index migration.
8. Theo dõi query errors, duplicates, latency.
9. Gỡ compatibility shim khi mọi services đã cập nhật.

Không sửa production bằng một `updateMany()` lớn mà chưa kiểm chứng dữ liệu và kế hoạch phục hồi.

---

## 30. Ma trận kiểm chứng cho một release

| Contract | Dữ liệu kiểm tra | Bằng chứng |
| --- | --- | --- |
| ID type | Chuỗi thường và 24-hex | Raw `_id` + `$type` |
| Java `amount` → BSON `total` | 125.50, 19.99 | Raw BSON Decimal128 |
| Java `createdAt` → `created_at` | UTC boundaries | BSON Date + range |
| Nested `shipping.city` | Hà Nội/Đà Nẵng | Raw `ship.city` |
| Missing khác null | note missing/null | `$exists`/`$type` |
| Array same element | BOOK và quantity≥3 | `$elemMatch` |
| Derived query đúng | Tenant A + total≥100 | Expected IDs |
| @Query đúng | Cùng dữ liệu như derived | Set equality + command |
| Tenant isolation | A/B + OR filters | Negative integration tests |
| Unique business key | Trùng tenant/order_no | Index spec + E11000 |
| Index thực tế | Compound index name/keys | `getIndexes` |
| Index sử dụng | Filter + sort | Explain/Profiler |
| Projection field | Chỉ fields cần | Command + raw response |
| Page count | Page size 2 | Page + command metrics |
| Sort ổn định | Equal created_at | `_id` tie-breaker |
| TTL option | expireAfterSeconds | Catalog + eventual test |
| Partial index | PAID vs all statuses | Catalog + Explain |
| Collation | Upper/lower, dấu | Query + index collation |
| Optimistic version | Two stale writers | Real concurrent test |
| Transaction | Failure rollback | Raw post-transaction data |
| Performance | Dataset gần production | p95/p99 + scans + resources |

**Điểm quan trọng:** mỗi row trong ma trận nên có assertion độc lập và dữ liệu test rõ ràng, không gộp mọi thứ vào một câu `assertNotNull`.

---

## 31. Những sai lầm thường gặp

| Nhận định sai | Thực tế |
| --- | --- |
| “Repository mock pass thì BSON đúng” | Mock bỏ qua mapper/server |
| “Java property name luôn là BSON field name” | `@Field` có thể đổi tên |
| “`@Id String` luôn BSON string” | Có rules chuyển ObjectId |
| “BigDecimal mặc định chắc chắn Decimal128” | Cần mapping/targetType và raw test |
| “Instant lưu đủ nanoseconds” | BSON Date có độ phân giải milliseconds |
| “Java null phân biệt được missing và explicit null” | Cả hai có thể đọc thành null |
| “`IsNull` chỉ tìm explicit null” | Null equality cũng match missing |
| “Hai array dot conditions phải khớp cùng element” | Cần `$elemMatch` |
| “`@Indexed` nghĩa index đã tồn tại” | Auto-index creation tắt mặc định từ 3.0 |
| “Index tồn tại thì query chắc đã dùng” | Planner còn lựa chọn |
| “`IXSCAN` là chắc chắn tối ưu” | Có thể quét quá nhiều keys |
| “`COLLSCAN` trên 8 docs chứng minh thiếu index” | Tiny dataset có thể chọn scan |
| “`Query.getQueryObject` là wire command cuối” | Có thể chưa qua mapping/options |
| “JSON @Query nhanh hơn derived query” | Cùng query plan có thể cùng performance |
| “Page chắc không cần count” | Có thể count thêm |
| “Partial index dùng cho mọi query” | Query phải đáp ứng subset predicate |
| “TTL xóa đúng giây hết hạn” | Background TTL không deterministic |
| “existsBy chống race duplicate” | Unique index mới bảo vệ |
| “Partial entity có thể save như full entity” | Có nguy cơ mất fields |
| “Regex IgnoreCase luôn dùng index hiệu quả” | Phụ thuộc regex/collation |
| “Một lần Explain bằng p99 production” | Phải đo workload |
| “Không cần Testcontainers vì đã mock repository” | Cần thực thi MongoDB behavior |
| “Log toàn bộ command trong production không sao” | Lộ dữ liệu nhạy cảm |
| “Migrations chỉ thay Java model” | Data/index schema cũng cần chuyển |

---

## 32. Bài tập thực hành

### Bài 1 — Các tầng bằng chứng

Nêu ít nhất năm tầng từ entity Java đến execution plan cần xem khi kiểm chứng hành vi Spring Data MongoDB.

### Bài 2 — Java property và BSON field

`OrderDoc.amount` dùng `@Field(name="total",targetType=DECIMAL128)`. MongoDB lưu field/type nào?

**Đáp án:** `total`, BSON Decimal128.

### Bài 3 — ID 24-hex

So raw `_id` của entity dùng `@Id String` và `@MongoId(FieldType.STRING)` với cùng giá trị 24-hex.

### Bài 4 — Raw BSON

Viết Java code dùng `MongoTemplate.getDb().getCollection("orders")` để lấy Document A-001; kiểm tra type của `total`.

### Bài 5 — Converter vs persisted

Vì sao `converter.write()` không đủ chứng minh server đã lưu document như kỳ vọng?

### Bài 6 — $type

Viết aggregation đọc type của `_id`, `order_no`, `total`, `created_at`, `ship` và `items`.

### Bài 7 — Fixture count

Tenant A có bao nhiêu documents? Tenant A PAID có bao nhiêu?

**Đáp án:** 5 và 3.

### Bài 8 — Decimal128 range

Viết native query và derived method lấy tenant A có tổng tiền từ 100 trở lên.

**Đáp án:** A-001 và A-003.

### Bài 9 — Instant

Tạo khoảng UTC cho ngày 14/11/2026 theo timezone Việt Nam. Vì sao dùng `[from,to)`?

### Bài 10 — Milliseconds

`Instant` có nanoseconds; BSON Date có giữ toàn bộ không?

**Đáp án:** Không.

### Bài 11 — Missing vs null

Fixture có bao nhiêu missing note, bao nhiêu explicit null, và `{note:null}` trả mấy documents?

**Đáp án:** 6, 1, 7.

### Bài 12 — Nested path

Java `shipping.city` map sang BSON path nào?

**Đáp án:** `ship.city`.

### Bài 13 — $elemMatch

Tại sao dùng `$elemMatch` khi cần `sku=BOOK` và `quantity>=3` ở cùng line item?

### Bài 14 — Derived/@Query equivalence

Tạo hai methods tìm `tenantId=A,total>=100`, so returned ID sets và emitted command.

### Bài 15 — QueryMapper

Giải thích vì sao `Query.getQueryObject()` có thể khác final filter gửi server.

### Bài 16 — CommandListener

Thiết kế listener log name/duration, không log query literal values/PII.

### Bài 17 — Index catalog

Tạo unique `(tenantId,order_no)` rồi dùng `getIndexes()` xác nhận unique option.

### Bài 18 — Auto index

Spring Data tự tạo index từ `@CompoundIndex` mặc định không?

**Đáp án:** Không, automatic creation bị tắt mặc định từ 3.0.

### Bài 19 — Tiny dataset

Có index nhưng Explain trên 8 docs dùng COLLSCAN; có đủ kết luận index sai không?

**Đáp án:** Không.

### Bài 20 — Hint

`hint("ix_tenant_status_time")` chứng minh điều gì và không chứng minh điều gì?

### Bài 21 — Query targeting

100.000 docs examined, 20 results → tỷ lệ?

**Đáp án:** 5.000 docs/result.

### Bài 22 — Compound prefix

Index `(tenantId,status,created_at)` giúp query không lọc tenant trong trường hợp nào?

### Bài 23 — Covered query

Khi nào MongoDB có thể không cần FETCH documents? Tại sao projection không tự tạo index coverage?

### Bài 24 — Race existsBy

Hai requests đều nhận exists=false rồi insert trùng; cơ chế bảo vệ thực sự là gì?

**Đáp án:** Unique index + xử lý duplicate key.

### Bài 25 — Partial index

Vì sao partial index chỉ chứa PAID không đáp ứng query liệt kê mọi status?

### Bài 26 — TTL

Tạo TTL sessions 24h. Tại sao không assert document bị xóa đúng giây?

### Bài 27 — Collation

Một index có collation khác query có thể ảnh hưởng query plan thế nào?

### Bài 28 — Partial entity save

Giải thích nguy cơ đọc projection thiếu fields rồi gọi save.

### Bài 29 — Versioning

Thiết kế concurrent test cho `@Version`: một writer thành công, một writer stale thất bại.

### Bài 30 — Transaction

Tạo order và audit trong một transaction, cố tình ném exception, đọc raw database để kiểm tra rollback.

### Bài 31 — Page vs Slice

Khi chỉ cần nút “Load more”, vì sao Slice có thể tránh cost của count query?

### Bài 32 — Tenant isolation

Viết negative test cho điều kiện `(tenant=A AND status=PAID) OR amount>=100` có thể leak tenant B.

### Bài 33 — Legacy data

Dữ liệu cũ có field amount kiểu double, entity mới map total Decimal128. Kể ít nhất ba lỗi có thể xảy ra.

### Bài 34 — Testcontainers

Vì sao integration test cần MongoDB thật? Chú ý gì với Testcontainers 1.x/2.x imports?

### Bài 35 — Index migration

Local có unique index, staging chưa có. Lập checklist trước khi tạo index trên staging.

### Bài 36 — Explain regression

Index mới tạo xong nhưng p99 cao hơn. Cần thu metrics và plan nào?

### Bài 37 — Sort ổn định

A-003 và A-005 cùng created_at. Vì sao phải sort thêm `_id` khi paging?

### Bài 38 — Collection validation

Dùng `getCollectionInfos()` xem validator thực; thử insert document sai kiểu để xác minh enforcement trong lab.

### Bài 39 — Performance benchmark

Tạo data đại diện khoảng 100k documents, đo p95/p99, docsExamined, keysExamined, index storage và write overhead.

### Bài 40 — Tổng hợp

Thiết kế release checklist khi đổi Java property `amount` → `grossAmount` nhưng BSON field vẫn phải là `total` Decimal128; thêm range query và compound index, đảm bảo tenant isolation, kiểm thử mapping/query/index/explain trước rollout.

---

## 33. Checklist kiểm chứng production

### Java/BSON

- [ ] Entity mapping annotations khớp schema thực.
- [ ] Kiểm tra ID String/ObjectId bằng raw `$type`.
- [ ] Kiểm tra Decimal128, Date, null/missing, nested fields và arrays.
- [ ] Không dùng mock làm bằng chứng MongoDB behavior.
- [ ] Kiểm tra `_class`/custom conversions khi interop.
- [ ] Có schema migration plan cho dữ liệu legacy.

### Query

- [ ] Derived query dùng đúng Java property paths.
- [ ] `@Query` binding và mapped field names được xác minh.
- [ ] Tenant scope áp dụng mọi nhánh OR, writes/deletes.
- [ ] Sort có tie-breaker ổn định.
- [ ] Page/count cost được quan sát.
- [ ] Không dùng partial entity cho full save.
- [ ] Không materialize collection lớn không giới hạn.
- [ ] Logs/query tracing có redaction.

### Index và execution

- [ ] Index thực có trong catalog.
- [ ] Field order, options, uniqueness, collation, partial/TTL đúng.
- [ ] Auto-index behavior không bị suy đoán.
- [ ] Có versioned index migration và rollback.
- [ ] Explain đúng filter/sort/projection của actual command.
- [ ] Đọc nReturned, docsExamined, keysExamined, plan stages.
- [ ] Không assert IXSCAN cứng trên tiny dataset.
- [ ] Không dùng hint bừa bãi trên production.
- [ ] Theo dõi tác động index tới writes và replication.

### Testing và vận hành

- [ ] Integration test chạy MongoDB thật trong environment cách ly.
- [ ] Seed oracle có expected BSON types và ID sets.
- [ ] Có test duplicate, null/missing, nested array, tenant isolation.
- [ ] Có test transaction/versioning nếu dùng.
- [ ] Có benchmark với corpus và concurrency đại diện.
- [ ] Quan sát app p95/p99, errors, pool waits, DB CPU/disk.
- [ ] Có plan backout cho schema/index/query changes.
- [ ] Không log PII, passwords hoặc raw commands ở production.

---

## 34. Tổng kết

Kiểm chứng Spring Data MongoDB đòi xem **hành vi thật** của MongoDB, chứ không chỉ tin mã Java hoặc repository mock.

1. **Mapping không phải storage:** dùng raw BSON và `$type` để xác minh `@Field`, `@MongoId`, Decimal128, Date và nested fields.
2. **Query source không phải wire command:** derived methods, `@Query` và `MongoTemplate` đều đi qua conversion/mapping; cần xem mapped filter hoặc driver command khi nghi ngờ.
3. **Index annotation không phải index catalog:** automatic index creation tắt mặc định từ Spring Data MongoDB 3.0; dùng `getIndexes()`/`listIndexes`.
4. **Index tồn tại không đồng nghĩa được dùng:** dùng Explain, phân tích scans/sort và thử dataset đại diện; không áp rule IXSCAN cứng trên 8 docs.
5. **Correctness nằm ở nhiều semantics:** null/missing, arrays, collation, tenant scoping, unique constraint, transaction và versioning.
6. **Integration test trên MongoDB thật** là bằng chứng đáng tin cho mapping/query/index; mock chỉ hỗ trợ business-unit tests.
7. **Performance phải đo dưới workload thật**, kết hợp p95/p99, pool waits và MongoDB metrics.

Câu hỏi cuối cùng nên là:

> **“MongoDB đã lưu BSON gì, nhận command nào, có index nào và thực thi query ra sao?”**

### Tài liệu chính thức và tham khảo

- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html) — `MappingMongoConverter`, `@Id`, `@MongoId`, `@Field`, conversion.
- [Spring Data MongoDB — Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html) — auto-index default, `IndexResolver`, `IndexOperations`.
- [Spring Data MongoDB — Repository Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — derived methods, `@Query`, binding và paging.
- [Spring Data MongoDB — MongoTemplate Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html) — `Criteria`, `Query`, fields, hints, collation.
- [Spring Data MongoDB — Projections](https://docs.spring.io/spring-data/mongodb/reference/repositories/projections.html) — DTO/interface projections.
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — sessions và transaction management.
- [Spring Boot — MongoDB](https://docs.spring.io/spring-boot/reference/data/nosql.html) — starters/configuration.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html) — integration test support.
- [MongoDB — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — ObjectId, Date, Decimal128, null.
- [MongoDB — Query Operators](https://www.mongodb.com/docs/manual/reference/operator/query/) — `$type`, `$exists`, `$elemMatch` và ranges.
- [MongoDB — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — `IXSCAN`, `COLLSCAN`, execution stats.
- [MongoDB — Indexes](https://www.mongodb.com/docs/manual/indexes/) — compound, partial, unique, TTL, collation.
- [MongoDB — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — partialFilterExpression.
- [MongoDB — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — uniqueness enforcement.
- [MongoDB — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — TTL monitor.
- [MongoDB — Collation](https://www.mongodb.com/docs/manual/reference/collation/) — locale-based comparisons.
- [MongoDB Java Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/) — command listener/pool events.
- [Testcontainers — MongoDB](https://java.testcontainers.org/modules/databases/mongodb/) — isolated test database.
