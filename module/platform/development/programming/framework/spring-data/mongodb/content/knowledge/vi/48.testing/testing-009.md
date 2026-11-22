# Kiểm thử null, trường thiếu, document nhúng và tham chiếu

> **Chương:** Kiểm thử  
> **Phạm vi:** Spring Data MongoDB — kiểm thử mapping document, truy vấn bằng `MongoTemplate`/repository, giá trị null và missing, embedded document và reference giữa các collection.

## 1. Tại sao chủ đề này quan trọng?

MongoDB không bắt buộc các document trong một collection có cùng cấu trúc. Một trường có thể thiếu hẳn, có giá trị BSON `null`, hoặc là chuỗi rỗng, mảng rỗng, object rỗng. Document con cũng có thể được nhúng trực tiếp hoặc được tham chiếu qua một collection khác.

Ví dụ:

```javascript
// A: thiếu hoàn toàn nickname
{ _id: "a", tenantId: "t1" }

// B: key nickname tồn tại, giá trị BSON Null
{ _id: "b", tenantId: "t1", nickname: null }

// C: nickname có nội dung
{ _id: "c", tenantId: "t1", nickname: "Lan" }
```

Khi Spring Data chuyển các document này sang POJO có property `String nickname`, cả A và B thường cho Java `null`. Nếu chỉ xác nhận `profile.nickname == null`, bài kiểm thử không biết field có tồn tại trong BSON hay không.

Sự khác biệt ảnh hưởng đến `$exists`, `$type`, query, index unique, cập nhật bằng `$unset`, migration dữ liệu cũ và quy tắc nghiệp vụ. Đối với reference, một đối tượng Java có vẻ chứa dữ liệu con nhưng database thực tế có thể chỉ lưu một ID hoặc DBRef.

**Mục tiêu:** kiểm tra riêng **BSON thật**, kết quả **mapping Java** và **hành vi query/update**, thay vì chỉ kiểm tra object Java sau khi đọc.

## 2. Phân biệt BSON null, missing và giá trị rỗng

| Predicate cho field scalar `nickname` | Field thiếu | `nickname: null` | `nickname: "Lan"` |
| --- | :---: | :---: | :---: |
| `{ nickname: null }` | Có | Có | Không |
| `{ nickname: { $type: 10 } }` | Không | Có | Không |
| `{ nickname: { $exists: false } }` | Có | Không | Không |
| `{ nickname: { $exists: true } }` | Không | Có | Có |
| `{ nickname: { $ne: null } }` | Không | Không | Có |

Đây là quy tắc cho field scalar. Khi field là mảng, toán tử so khớp có thể xét phần tử trong mảng; cần kiểm thử riêng mảng có phần tử null.

Trong Spring Data MongoDB, dùng:

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query nullOrMissing = Query.query(
    Criteria.where("nickname").isNull()
);
Query explicitNullOnly = Query.query(
    Criteria.where("nickname").isNullValue()
);
Query missingOnly = Query.query(
    Criteria.where("nickname").exists(false)
);
Query present = Query.query(
    Criteria.where("nickname").exists(true)
);
```

- `isNull()` dùng phép so sánh với null, khớp **cả null và missing**.
- `isNullValue()` dùng kiểm tra kiểu BSON Null, **chỉ khớp explicit null**.
- `exists(false)` yêu cầu key không có mặt; `exists(true)` vẫn nhận key có giá trị null.

Hai helper `isNull()`, `isNullValue()` có từ Spring Data MongoDB 3.3. Một repository method dạng `findByNicknameIsNull()` có thể sinh truy vấn null equality, nên **không mặc nhiên** hiểu đó là truy vấn chỉ dành cho field BSON Null. Khi yêu cầu nghiệp vụ cần phân biệt, hãy xác minh query BSON thật.

Chuỗi rỗng `""`, số `0`, boolean `false`, object `{}` và array `[]` là những giá trị BSON tồn tại thực sự. Đừng gộp chúng với null/missing trong thiết kế fixture.

## 3. Mapping Java có thể làm mất thông tin về field

`MappingMongoConverter` chuyển BSON thành Java object. Đặc biệt, với property tham chiếu `String`, cả trường hợp thiếu và explicit null có thể được biểu diễn bằng cùng Java `null`. Ngoài ra, constructor, giá trị khởi tạo mặc định và converter tùy chỉnh có thể ảnh hưởng kết quả khi property thiếu.

Ở chiều ghi, Spring Data MongoDB có hai chiến lược:

| Mapping | Giá trị Java | BSON khi ghi qua converter |
| --- | --- | --- |
| Mặc định, `Field.Write.NON_NULL` | `null` | Thường **bỏ qua key** |
| `@Field(write = Field.Write.ALWAYS)` | `null` | Lưu **key: null** |
| Bất kỳ mapping thông thường | Giá trị khác null | Lưu giá trị BSON tương ứng |

Ví dụ entity minh họa:

```java
package example.mongodb;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("profiles")
public class Profile {
    @Id
    public String id;

    public String nickname; // null mặc định có thể bị bỏ khỏi BSON

    @Field(value = "note", write = Field.Write.ALWAYS)
    public String note;     // null vẫn ghi BSON key "note"

    public Contact contact; // embedded document

    public Profile() {}
    public Profile(String id) { this.id = id; }
}

class Contact {
    public String phone;

    @Field("postal_code")
    public String postalCode;

    public Contact() {}
}
```

Trong ví dụ học tập dùng public field để giản lược. Dự án thật có thể dùng field private và getter/setter hoặc constructor phù hợp với Spring Data. Tùy phiên bản, `@Field(write = Field.Write.ALWAYS)` có từ Spring Data MongoDB 3.3.

Muốn xác minh tình trạng field gốc, hãy đọc **raw BSON document** bằng `MongoTemplate.getCollection(...)` và sử dụng `org.bson.Document.containsKey(...)`. Chỉ dựa vào getter của entity thì không đủ.

## 4. Bộ kiểm thử tích hợp dùng `@DataMongoTest`

Để kiểm tra đúng ngữ nghĩa MongoDB, dùng MongoDB test instance thật, chẳng hạn Testcontainers. Đoạn dưới dùng **Spring Boot 3.x, Spring Data MongoDB tương ứng, JUnit Jupiter, AssertJ và Testcontainers 1.x**. Cần có MongoDB starter, starter test, `spring-boot-testcontainers` và các dependency Testcontainers MongoDB/JUnit Jupiter; Docker phải chạy được.

```java
package example.mongodb;

import static org.assertj.core.api.Assertions.assertThat;
import static com.mongodb.client.model.Filters.eq;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataMongoTest
@Testcontainers
class ProfileTest {
    @Container
    @ServiceConnection
    static final MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"));

    @Autowired
    MongoTemplate template;

    @BeforeEach
    void clean() {
        // Chỉ dùng container/database dành riêng cho kiểm thử.
        template.dropCollection(Profile.class);
    }

    @Test
    void distinguishesMissingAndNullInQueries() {
        // Fixture raw BSON giữ nguyên khác biệt null và missing.
        template.getCollection("profiles").insertMany(List.of(
            new Document("_id", "missing"),
            new Document("_id", "null").append("nickname", null),
            new Document("_id", "value").append("nickname", "Lan")
        ));

        assertThat(template.count(
            Query.query(Criteria.where("nickname").isNull()), Profile.class
        )).isEqualTo(2);

        assertThat(template.count(
            Query.query(Criteria.where("nickname").isNullValue()), Profile.class
        )).isEqualTo(1);

        assertThat(template.count(
            Query.query(Criteria.where("nickname").exists(false)), Profile.class
        )).isEqualTo(1);

        assertThat(template.count(
            Query.query(Criteria.where("nickname").exists(true)), Profile.class
        )).isEqualTo(2);

        Document absent = template.getCollection("profiles")
            .find(eq("_id", "missing")).first();
        Document hasNull = template.getCollection("profiles")
            .find(eq("_id", "null")).first();

        assertThat(absent).isNotNull();
        assertThat(absent.containsKey("nickname")).isFalse();
        assertThat(hasNull).isNotNull();
        assertThat(hasNull.containsKey("nickname")).isTrue();
        assertThat(hasNull.get("nickname")).isNull();

        // Java object không thể hiện sự khác nhau này qua String:
        assertThat(template.findById("missing", Profile.class).nickname).isNull();
        assertThat(template.findById("null", Profile.class).nickname).isNull();
    }

    @Test
    void writesExplicitNullOnlyForConfiguredField() {
        template.save(new Profile("p-1"));

        Document raw = template.getCollection("profiles")
            .find(eq("_id", "p-1")).first();
        assertThat(raw).isNotNull();
        assertThat(raw.containsKey("nickname")).isFalse();
        assertThat(raw.containsKey("note")).isTrue();
        assertThat(raw.get("note")).isNull();
    }
}
```

Với fixture cần phân biệt null/missing, chèn bằng MongoDB driver trực tiếp như ví dụ là cách rõ ràng nhất: lưu hai POJO có property null có thể khiến cả hai trở thành document thiếu field khi converter bỏ qua null.

`@DataMongoTest` nạp hạ tầng MongoDB nhưng **không tự tạo server**. `@ServiceConnection` của Spring Boot 3.1+ nhận thông tin kết nối từ Testcontainers. Nếu phiên bản chưa hỗ trợ, dùng `@DynamicPropertySource` với `mongo.getReplicaSetUrl()` và property `spring.data.mongodb.uri` theo cấu hình Spring Boot phù hợp.

## 5. Kiểm thử `$set: null` khác `$unset`

Khi document `p-1` đã tồn tại, hai thao tác sau có kết quả BSON khác nhau:

```java
Query byId = Query.query(Criteria.where("_id").is("p-1"));

template.updateFirst(
    byId, new Update().set("nickname", null), Profile.class
);
Document setNull = template.getCollection("profiles")
    .find(eq("_id", "p-1")).first();
assertThat(setNull.containsKey("nickname")).isTrue();
assertThat(setNull.get("nickname")).isNull();

template.updateFirst(
    byId, new Update().unset("nickname"), Profile.class
);
Document removed = template.getCollection("profiles")
    .find(eq("_id", "p-1")).first();
assertThat(removed.containsKey("nickname")).isFalse();
```

Đây là đoạn mở rộng đặt trong test method với `template` đã inject và fixture `p-1` đã tạo. `Update.set(..., null)` đặt field thành BSON Null; `Update.unset(...)` xóa hẳn field. Sau cả hai thao tác, POJO đọc ra vẫn có thể chứa cùng Java `null`, nên assertion raw BSON là thiết yếu.

Đừng trộn kỳ vọng về `save(entity)` với `Update.set`/`Update.unset`: `save` chuyển toàn bộ entity theo mapping của converter, còn update operator thay đổi trường cụ thể tại database.

## 6. Document nhúng: cấu trúc, nested path và null

Với `Profile.contact` (không dùng annotation tham chiếu), dữ liệu nằm **trong cùng document**:

```javascript
{
  _id: "p-contact",
  contact: { phone: "0901234567", postal_code: "700000" }
}
```

Ví dụ test tiếp theo có thể đặt trong `ProfileTest`:

```java
@Test
void mapsEmbeddedDocumentAndNestedQuery() {
    Profile p = new Profile("p-contact");
    p.contact = new Contact();
    p.contact.phone = "0901234567";
    p.contact.postalCode = "700000";
    template.insert(p);

    Document raw = template.getCollection("profiles")
        .find(eq("_id", "p-contact")).first();
    assertThat(raw).isNotNull();
    assertThat(raw.get("contact")).isInstanceOf(Document.class);

    Document nested = raw.get("contact", Document.class);
    assertThat(nested.getString("phone")).isEqualTo("0901234567");
    assertThat(nested.getString("postal_code")).isEqualTo("700000");
    assertThat(nested.containsKey("postalCode")).isFalse();

    Query query = Query.query(
        Criteria.where("contact.postalCode").is("700000")
    );
    List<Profile> results = template.find(query, Profile.class);
    assertThat(results).hasSize(1);
    assertThat(results.get(0).contact.postalCode).isEqualTo("700000");
}
```

Trong `MongoTemplate` query gắn với kiểu `Profile`, `QueryMapper` có thể ánh xạ đường dẫn Java `contact.postalCode` sang BSON `contact.postal_code`. Ngược lại, khi dùng trực tiếp driver `MongoCollection<Document>`, phải truy vấn đúng tên BSON `contact.postal_code`.

### 6.1. Các trạng thái khác nhau của field nested

| Raw BSON | Trạng thái parent | Trạng thái đường dẫn `contact.phone` |
| --- | --- | --- |
| `{}` | Không có `contact` | Missing |
| `{contact: null}` | Parent là BSON Null | Không có nested key |
| `{contact: {}}` | Object tồn tại nhưng rỗng | Missing |
| `{contact: {phone: null}}` | Object tồn tại | Explicit BSON Null |
| `{contact: {phone: ""}}` | Object tồn tại | Chuỗi rỗng |
| `{contact: {phone: "090..."}}` | Object tồn tại | Có giá trị |

Để tìm nested phone thiếu:

```java
Query phoneMissing = Query.query(
    Criteria.where("contact.phone").exists(false)
);
Query phoneExplicitlyNull = Query.query(
    Criteria.where("contact.phone").isNullValue()
);
```

`exists(false)` trên `contact.phone` có thể khớp cả document không có `contact` lẫn document có `contact` nhưng thiếu `phone`. Nếu chỉ muốn parent đã tồn tại và là object, cần điều kiện bổ sung về parent và BSON type. Một assertion Java `profile.contact == null` không thể khẳng định raw parent bị thiếu hay có explicit null.

### 6.2. Embedded array và `$elemMatch`

Với `List<Contact> contacts`, bộ fixture nên gồm: missing, null, `[]`, một phần tử hợp lệ, một phần tử null và nhiều object với thuộc tính nằm ở **những phần tử khác nhau**. Query như:

```javascript
{
  "contacts.phone": "0901234567",
  "contacts.postal_code": "700000"
}
```

có thể khớp khi hai điều kiện đúng ở hai phần tử khác nhau. Khi phải yêu cầu **cùng một contact**, hãy kiểm tra với `$elemMatch`:

```javascript
{
  contacts: {
    $elemMatch: {
      phone: "0901234567",
      postal_code: "700000"
    }
  }
}
```

Không lấy test POJO list không null làm bằng chứng raw document đã lưu mảng thay vì null/missing; hãy so sánh qua BSON.

## 7. Document nhúng và document tham chiếu khác nhau thế nào?

| Đặc tính | Embedded `Contact` | `@DocumentReference` | `@DBRef` |
| --- | --- | --- | --- |
| Dữ liệu cha lưu | Object con trực tiếp | Pointer, mặc định là ID của đích | Giá trị DBRef (`$ref`, `$id`) |
| Document đích | Không cần document riêng | Nằm ở collection riêng | Nằm ở collection riêng |
| Cách đọc | Ánh xạ BSON con | Spring Data resolve reference | Spring Data DBRef resolver |
| Lưu target khi save parent | Cùng một document | **Không tự cascade** | **Không tự cascade** |
| Khi target mất | Không có foreign target | Pointer có thể trở thành mồ côi | DBRef có thể thành mồ côi |
| Kiểm thử chính | Cấu trúc nested | Pointer BSON, resolution, dangling ref | DBRef BSON, lazy/eager resolution |

**Đừng đồng nhất `@DocumentReference` với `@DBRef`**: chúng có biểu diễn BSON khác nhau, nên thay annotation có thể cần migration dữ liệu.

### 7.1. Model với `@DocumentReference`

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.DocumentReference;

@Document("customers")
class Customer {
    @Id public String id;
    public String name;

    public Customer() {}
    public Customer(String id, String name) {
        this.id = id;
        this.name = name;
    }
}

@Document("orders")
class SalesOrder {
    @Id public String id;

    @DocumentReference
    public Customer customer;

    public SalesOrder() {}
    public SalesOrder(String id, Customer customer) {
        this.id = id;
        this.customer = customer;
    }
}
```

Với ID `"c-1"`, document `orders` thường chứa `customer: "c-1"`, không chứa cả object customer. ID đơn giản được dùng ở đây để tránh việc String trông giống ObjectId 24 chữ số hex được driver/converter đổi kiểu.

### 7.2. Test reference và ranh giới cascade

```java
@Test
void storesPointerAndResolvesReference() {
    Customer customer = template.insert(new Customer("c-1", "Lan"));
    template.insert(new SalesOrder("o-1", customer));

    Document raw = template.getCollection("orders")
        .find(eq("_id", "o-1")).first();
    assertThat(raw).isNotNull();
    assertThat(raw.get("customer")).isEqualTo("c-1");

    SalesOrder loaded = template.findById("o-1", SalesOrder.class);
    assertThat(loaded).isNotNull();
    assertThat(loaded.customer).isNotNull();
    assertThat(loaded.customer.name).isEqualTo("Lan");
}

@Test
void saveParentDoesNotCascadeInsertToTarget() {
    Customer unsaved = new Customer("c-unsaved", "Bình");
    template.insert(new SalesOrder("o-2", unsaved));

    Document raw = template.getCollection("orders")
        .find(eq("_id", "o-2")).first();
    assertThat(raw.get("customer")).isEqualTo("c-unsaved");
    assertThat(template.findById("c-unsaved", Customer.class)).isNull();
}
```

Hai test này đặt trong class `@DataMongoTest` có `MongoTemplate`, và cleanup phải bao gồm `orders` lẫn `customers` để tránh dữ liệu từ test khác. Cần lưu target trước khi lưu parent nếu nghiệp vụ yêu cầu tham chiếu luôn hợp lệ. Một object Java có ID trong memory **không tự trở thành document ở collection đích**.

### 7.3. Dangling reference và lazy loading

Kịch bản cần kiểm tra:

1. Lưu `Customer` và `SalesOrder` tham chiếu customer đó.
2. Xóa customer nhưng giữ order.
3. Đọc BSON raw của order: pointer vẫn còn.
4. Thử đọc property tham chiếu bằng Spring Data, quan sát hành vi thực tế theo phiên bản/resolver.

Không nên luôn assert một kết quả duy nhất (ví dụ bắt buộc null) cho mọi kiểu reference và phiên bản. Resolver có thể xử lý tham chiếu gãy khác nhau. Với `@DocumentReference(lazy = true)` hoặc `@DBRef(lazy = true)`, lời gọi `findById(...)` có thể chưa resolve đích; phải thực sự truy cập property. Các phương thức debug như `toString()` cũng có thể bất ngờ kích hoạt lazy loading.

### 7.4. DBRef

Ví dụ:

```java
@Document("legacy_orders")
class LegacyOrder {
    @Id public String id;

    @DBRef
    public Customer customer;
}
```

Raw BSON của `customer` được biểu diễn bằng DBRef, tương đương:

```javascript
{ _id: "legacy-1", customer: DBRef("customers", "c-1") }
```

Test cần kiểm tra DBRef tồn tại đúng collection/ID, sau đó xác minh resolver đọc được `Customer`. Không có foreign-key constraint ở server và không có cascade save tự động. Với list tham chiếu, việc cùng trỏ một collection hoặc nhiều collection ảnh hưởng đến cách resolver và số lần tải dữ liệu.

## 8. Index và validation khi có null/missing

### 8.1. Unique index có thể gây lỗi với null/missing

Một unique index **đơn field** của MongoDB coi cả missing và explicit null là index key null. Hệ quả: nhiều document cùng không có email có thể gặp lỗi duplicate key nếu dùng index `{ email: 1 }` với `unique: true`.

Nếu quy tắc chỉ yêu cầu email string không trùng, có thể dùng **partial unique index**:

```javascript
db.profiles.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: { email: { $type: "string" } }
  }
)
```

Test phải xác minh ba trường hợp: nhiều document thiếu email được chấp nhận, nhiều document `email: null` được chấp nhận (ngoài partial filter), và hai email string bằng nhau bị từ chối. Chú ý `partialFilterExpression: { email: { $exists: true } }` **vẫn bao gồm explicit null**, nên không tương đương với filter chỉ dành cho string.

Nếu uniqueness phải tính theo tenant hoặc không phân biệt hoa thường, thiết kế compound index/collation và normalization tương ứng. `@Indexed(unique = true)` chỉ khai báo metadata; index phải thực sự được tạo trong môi trường test, bởi Spring Data MongoDB mặc định không bật auto index creation.

### 8.2. Index nested path và schema validation

MongoDB có thể đánh index `contact.postal_code` và sử dụng index ấy cho truy vấn phù hợp. Hãy phân biệt property path Java (`contact.postalCode`) với tên trường BSON thật khi kiểm tra `getIndexes()` và `explain`. Với array of embedded documents, index có thể là multikey và yêu cầu kiểm tra kỹ `$elemMatch`.

Annotation như `@Field` trên entity không tự bắt buộc mọi document cũ có đủ key. Khi nghiệp vụ đòi hỏi bắt buộc field hoặc đúng BSON type, cần cấu hình MongoDB `$jsonSchema` validation hoặc migration riêng, rồi test cả ghi thành công và ghi bị từ chối.

## 9. Ma trận kiểm thử đề xuất

| Nhóm | Fixture nên có | Assertion quan trọng |
| --- | --- | --- |
| Scalar | missing, null, `""`, một giá trị bình thường | `containsKey`, `isNull`/`isNullValue`, `exists` |
| Ghi/đọc POJO | Property Java null và non-null | `Field.Write`, BSON raw và round-trip |
| Update | `set(null)`, `unset` | Có key/không key trên server |
| Nested object | missing parent, null parent, `{}`, child null, child có giá trị | Đường dẫn BSON, query nested |
| Embedded list | missing, null, `[]`, list nhiều phần tử | Mapping, `$elemMatch` |
| Document reference | Target tồn tại, chưa lưu, bị xóa | Raw pointer, resolution, không cascade |
| DBRef | Target tồn tại, dangling, lazy | Cấu trúc DBRef, thời điểm resolution |
| Index | Null/missing, trùng giá trị, nested | Unique/partial index và query plan |

Unit test với mock repository hữu ích cho logic nghiệp vụ, nhưng **không xác nhận ngữ nghĩa BSON hoặc reference resolution**. Những hành vi này nên được test với MongoDB thật qua `@DataMongoTest` và môi trường có thể lặp lại. Bài test dùng chung application context không có nghĩa dữ liệu database tự rollback: hãy dọn collection riêng giữa các test, tránh dùng database ngoài môi trường kiểm thử.

## 10. Lỗi thường gặp và cách điều tra

| Triệu chứng | Khả năng | Cách kiểm tra |
| --- | --- | --- |
| `isNull()` trả quá nhiều dòng | Query bao gồm cả missing | Dùng `isNullValue()` nếu cần explicit null |
| POJO có null nhưng BSON không có key | Converter bỏ qua null mặc định | Đọc raw document, cân nhắc `Write.ALWAYS` |
| `$unset` rồi POJO vẫn là null | Java không lưu thông tin về field missing | Assert `containsKey` hoặc `exists(false)` |
| Query nested không khớp | Sai giữa property Java và tên BSON của `@Field` | So sánh raw field path |
| Query array trả false positive | Nhiều predicate đúng trên các phần tử khác nhau | Dùng `$elemMatch` nếu cần cùng phần tử |
| Save parent không thấy customer mới | Reference không tự cascade | Insert target riêng, kiểm tra collection đích |
| Reference lỗi khi đọc | Sai ID, target bị xóa, custom lookup không đúng | Kiểm tra raw pointer và đích |
| Lazy reference chỉ lỗi sau getter | Resolution diễn ra muộn | Cố ý truy cập property trong test |
| Unique index báo lỗi khi email thiếu | Missing/null tạo key null | Thiết kế partial index theo quy tắc |

## 11. Bài tập áp dụng

1. Chèn năm document với `nickname` lần lượt: thiếu, null, chuỗi rỗng, `"Lan"`, `"Bình"`. Viết test đếm kết quả của `isNull()`, `isNullValue()` và `exists(false)`.
2. Lưu `Profile` có `contact`, sau đó đổi `contact` từ embedded object sang một entity riêng dùng `@DocumentReference`. So sánh raw BSON trước và sau; thảo luận nhu cầu migration.
3. Tạo `List<Contact>` với hai phần tử có phone và postalCode hợp lệ ở **hai phần tử khác nhau**. Viết query `$elemMatch` và chứng minh kết quả khác query dotted path rời.
4. Tạo unique partial index email. Kiểm tra missing, explicit null và string trùng; xác nhận lỗi duplicate key chỉ ở trường hợp theo quy tắc đã chọn.

## 12. Ghi nhớ

- **BSON Null và missing khác nhau**: `isNull()` khớp cả hai, `isNullValue()` chỉ explicit null, `exists(false)` chỉ missing.
- **Mapping Java có thể che khác biệt**: dùng raw `Document.containsKey` để kiểm tra field thực sự có mặt.
- **Nhúng và tham chiếu khác nhau**: embedded ở cùng document; `@DBRef` và `@DocumentReference` lưu pointer và không tự cascade.
- **Test cả đọc, ghi, update, index và dữ liệu cũ** trên MongoDB thực để phát hiện các lỗi mà mock hoặc getter Java không bộc lộ.

## Tài liệu tham khảo

- [MongoDB — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/): equality null, BSON type null và missing.
- [MongoDB — `$exists`](https://www.mongodb.com/docs/manual/reference/operator/query/exists/): kiểm tra field có tồn tại, kể cả giá trị null.
- [Spring Data MongoDB — `Criteria` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Criteria.html): `isNull`, `isNullValue`, `exists`.
- [Spring Data MongoDB — `@Field` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/Field.html): `Field.Write.NON_NULL` và `ALWAYS`.
- [Spring Data MongoDB — Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): mapping object, embedded document và collection.
- [Spring Data MongoDB — Document References](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/document-references.html): `@DBRef`, `@DocumentReference` và lazy loading.
- [MongoDB — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): uniqueness với null/missing.
- [MongoDB — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/): partial unique index.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): cách kết nối database kiểm thử.
