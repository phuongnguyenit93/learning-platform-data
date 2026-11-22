# Phân biệt metadata Spring Data MongoDB với annotation JPA

Khi chuyển từ Spring Data JPA sang **Spring Data MongoDB**, nhiều lớp Java nhìn khá giống nhau: đều có thuộc tính `id`, annotation đánh dấu entity, trường được đổi tên khi lưu và repository để truy vấn. Nhưng hai công nghệ dùng **mô hình dữ liệu và bộ ánh xạ khác nhau**. Annotation JPA mô tả bảng, cột, quan hệ và vòng đời entity trong cơ sở dữ liệu quan hệ; metadata Spring Data MongoDB mô tả **collection, BSON document, trường lồng nhau và tham chiếu document**.

Nếu chỉ đổi `JpaRepository` thành `MongoRepository` rồi giữ nguyên `@Entity`, `@Table`, `@Column` hoặc `@ManyToOne`, ứng dụng có thể lưu dữ liệu theo cấu trúc khác dự kiến, sai kiểu `_id`, mất chỉ mục hoặc ghi đè field. Bài này giúp bạn đọc đúng metadata, chọn đúng annotation và kiểm tra BSON thực tế khi dùng `MongoTemplate` hoặc repository.

Sau bài học, bạn có thể:

- Phân biệt annotation của `org.springframework.data.*` với `jakarta.persistence.*` (hoặc `javax.persistence.*` trong dự án JPA cũ).
- Ánh xạ class, `_id`, field BSON, nested object, tham chiếu, index và version theo Spring Data MongoDB.
- Hiểu vì sao các khái niệm `@GeneratedValue`, `@JoinColumn`, `@OneToMany` và dirty checking của JPA không áp dụng tương đương cho MongoDB.
- Cấu hình auditing, converter, kiểu lưu và transaction khi cần.
- Đọc document bằng `mongosh` để xác minh metadata thực sự có hiệu lực.

## 1. Hai hệ metadata giải quyết hai mô hình dữ liệu

Với **JPA**, một entity thường tương ứng bảng quan hệ. Annotation như `@Entity`, `@Table`, `@Column`, `@ManyToOne` và `@JoinColumn` hướng dẫn JPA provider (ví dụ Hibernate) ánh xạ đối tượng thành hàng, cột và quan hệ giữa bảng. JPA còn có *persistence context* và cơ chế theo dõi thay đổi (*dirty checking*) đối với managed entity.

Với **Spring Data MongoDB**, bộ ánh xạ `MappingMongoConverter` chuyển object Java sang BSON và ngược lại. Điểm đích thường là một document trong collection; object con có thể được lưu **nhúng** trong document, hoặc lưu tham chiếu đến document ở collection khác. Các annotation chính nằm trong `org.springframework.data.annotation` và `org.springframework.data.mongodb.core.mapping`.

| Khía cạnh | Spring Data JPA | Spring Data MongoDB |
| --- | --- | --- |
| Đơn vị lưu trữ | Row trong table | BSON document trong collection |
| Khai báo loại lưu trữ | `@Entity`, tùy chọn `@Table` | `@Document(collection = "...")` |
| Khóa định danh | `jakarta.persistence.Id`; có thể dùng `@GeneratedValue` | `org.springframework.data.annotation.Id` hoặc `@MongoId` ánh xạ tới `_id` |
| Đổi tên thuộc tính lưu | `@Column(name = "...")` | `@Field("...")` |
| Quan hệ | `@ManyToOne`, `@OneToMany`, `@JoinColumn`, join/FK theo mô hình SQL | Nhúng object; `@DBRef` hoặc `@DocumentReference`; hoặc lưu ID thủ công |
| Chỉ mục | `@Table(indexes = ...)`, DDL/migration của RDBMS | `@Indexed`, `@CompoundIndex`, tạo index trong MongoDB |
| Version | `jakarta.persistence.Version` | `org.springframework.data.annotation.Version` |
| Theo dõi thay đổi | Managed entity có dirty checking trong persistence context | Object đọc ra không tự được ghi lại khi bạn thay đổi thuộc tính; cần `save`/update rõ ràng |
| Truy vấn | JPQL, SQL, Criteria API | JSON/BSON query, `Criteria`, `Query`, aggregation pipeline |
| Transaction | Thường gắn với transaction manager của RDBMS/JPA | Cần cấu hình MongoDB transaction manager và hạ tầng MongoDB hỗ trợ khi dùng transaction nhiều document |

**Chú ý:** tên annotation giống nhau không làm chúng tương đương. Ví dụ `jakarta.persistence.Id` và `org.springframework.data.annotation.Id` là hai kiểu annotation khác package; cần kiểm tra chính xác dòng `import` trong code. Không có một bước chuyển đổi tự động, đầy đủ từ metadata JPA sang metadata MongoDB.

## 2. `@Document` khác `@Entity` và `@Table` thế nào?

### 2.1. Entity JPA điển hình

Đây là một lớp dành cho JPA, minh họa bảng `catalog_items`:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "catalog_items")
public class CatalogItemJpa {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Version
    private Long version;
}
```

`@Entity` đánh dấu entity do JPA quản lý, `@Table` nêu tên bảng và `@Column` nêu tên cột. `@GeneratedValue(strategy = IDENTITY)` yêu cầu cơ chế tạo khóa phù hợp với RDBMS và JPA provider. Không thể mang nguyên các annotation này sang lớp MongoDB rồi kỳ vọng chúng có cùng ý nghĩa.

### 2.2. Document MongoDB tương ứng

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "catalog_items")
public class CatalogItem {
    @Id
    private ObjectId id;

    private String sku;

    @Field("display_name")
    private String displayName;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal price;

    @Version
    private Long version;

    private List<Variant> variants = new ArrayList<>();

    protected CatalogItem() { } // Cho quá trình ánh xạ dữ liệu

    public CatalogItem(String sku, String displayName, BigDecimal price) {
        this.sku = sku;
        this.displayName = displayName;
        this.price = price;
    }

    public ObjectId getId() { return id; }
    public String getSku() { return sku; }
    public String getDisplayName() { return displayName; }

    public static class Variant {
        private String color;
        private int stock;

        protected Variant() { }

        public Variant(String color, int stock) {
            this.color = color;
            this.stock = stock;
        }
    }
}
```

Khi lưu bằng Spring Data MongoDB, cấu trúc BSON tương ứng có thể là:

```javascript
{
  _id: ObjectId("665f1f2a4b6c7d8e9f001234"),
  sku: "PEN-101",
  display_name: "Bút bi xanh",
  price: NumberDecimal("12500.00"),
  version: NumberLong(0),
  variants: [
    { color: "blue", stock: 25 },
    { color: "black", stock: 10 }
  ],
  _class: "com.example.catalog.CatalogItem"
}
```

Đây là **hình minh họa**: giá trị `_id` và tên lớp sẽ tùy ứng dụng; `_class` thường xuất hiện với cấu hình mapping mặc định, nhưng có thể được thay đổi bằng type alias hoặc cấu hình converter. Kiểu BSON của số và version còn phụ thuộc metadata và cách sinh dữ liệu. Điểm cần nhìn là `displayName` đã thành `display_name`, `id` thành `_id` và `variants` thành **mảng document nhúng**, không cần bảng phụ.

`@Document` cho phép chỉ rõ collection và mang metadata MongoDB. Trong một số trường hợp Spring Data MongoDB vẫn ánh xạ class không gắn `@Document` theo quy ước, nhưng khai báo tường minh thường giúp dễ hiểu cấu trúc, tránh chọn tên collection ngoài ý muốn và hỗ trợ quản lý index/metadata.

## 3. Đổi tên field: `@Field` khác `@Column`

Đổi tên thuộc tính trong Java khi lưu BSON:

```java
import org.springframework.data.mongodb.core.mapping.Field;

@Field("display_name")
private String displayName;
```

Trong document MongoDB, tên trường là `display_name`. Khi viết truy vấn thông qua `MongoTemplate` với **loại entity**, bạn thường dùng đường dẫn thuộc tính Java để Spring Data ánh xạ:

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("displayName").is("Bút bi xanh")
);
CatalogItem item = mongoTemplate.findOne(
    query, CatalogItem.class
);
```

Vì truy vấn mang thông tin `CatalogItem.class`, mapping có thể chuyển `displayName` thành `display_name` ở tầng MongoDB. Nhưng khi dùng `mongosh` hoặc MongoDB Java Driver trực tiếp, phải viết **tên BSON thật**:

```javascript
db.catalog_items.findOne({ display_name: "Bút bi xanh" });
```

Với field lồng nhau, tiếp tục dùng dot notation theo cấu trúc lưu, ví dụ `"variants.color"`. Nếu thay đổi metadata `@Field` nhưng có query JSON tự viết, pipeline hoặc script khác, hãy kiểm tra chúng vẫn truy cập đúng trường.

**Khác biệt về ràng buộc:** JPA `@Column(nullable = false, length = 80, unique = true)` có thể liên quan đến DDL và ràng buộc trên RDBMS. `@Field` của MongoDB chủ yếu mô tả **tên/kiểu lưu**, không tự biến các điều kiện nullable/length/unique kiểu JPA thành validation rule. Muốn ràng buộc ở database, thiết kế **MongoDB JSON Schema validation**, unique index hoặc các cơ chế kiểm tra phù hợp; ở API còn cần validation nghiệp vụ.

## 4. Định danh: `@Id`, `@MongoId` và `@GeneratedValue`

MongoDB yêu cầu mỗi document đã lưu có `_id` duy nhất trong collection. Định danh mặc định thường được tạo dạng BSON `ObjectId`, nhưng `_id` có thể dùng loại BSON hợp lệ khác theo thiết kế. Các cách ánh xạ phổ biến:

| Java declaration | Ý nghĩa khi dùng Spring Data MongoDB |
| --- | --- |
| `@Id ObjectId id` | Ánh xạ tới BSON `_id` dạng ObjectId, thuận tiện cho ID kỹ thuật |
| `@Id String id` | Có cơ chế chuyển đổi chuỗi hợp lệ thành ObjectId khi thích hợp; cần kiểm chứng loại BSON thực tế |
| `@MongoId String id` | Giữ ID String theo kiểu khai báo; không chủ ý ép chuỗi 24 hex thành ObjectId như `@Id String` |
| `@MongoId(FieldType.OBJECT_ID) String id` | Yêu cầu chiến lược chuyển đổi sang BSON ObjectId khi giá trị chuyển đổi được |
| `@Id UUID id` | Cần cân nhắc representation/codec của UUID để dữ liệu đọc ghi nhất quán |

Ví dụ giữ mã nghiệp vụ như `"SKU-001"` dưới dạng chuỗi:

```java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "inventory")
public class InventoryItem {
    @MongoId
    private String id;

    private int available;

    protected InventoryItem() { }

    public InventoryItem(String id, int available) {
        this.id = id;
        this.available = available;
    }
}
```

Trong ứng dụng, đặt `id` rõ ràng khi tạo `InventoryItem` nếu chọn khóa nghiệp vụ do ứng dụng cấp. Ví dụ MongoDB:

```javascript
{
  _id: "SKU-001",
  available: 12
}
```

**Không dùng `@GeneratedValue` của JPA cho MongoDB.** MongoDB không có chiến lược sinh khóa `IDENTITY` hoặc database sequence theo nghĩa JPA. Nếu dùng ObjectId, có thể để Spring Data/driver sinh; nếu yêu cầu UUID, ULID hoặc mã nghiệp vụ, hãy thiết kế cơ chế sinh ID rõ ràng, bảo đảm duy nhất và nhất quán kiểu lưu.

### 4.1. Hai chuỗi nhìn giống nhau có thể có kiểu BSON khác nhau

```javascript
const text = "665f1f2a4b6c7d8e9f001234";

db.ids_demo.insertOne({ _id: ObjectId(text), kind: "objectId" });
db.ids_demo.insertOne({ _id: text, kind: "string" });

db.ids_demo.findOne({ _id: ObjectId(text) }); // Document "objectId"
db.ids_demo.findOne({ _id: text });           // Document "string"
```

Hai document tồn tại đồng thời vì MongoDB phân biệt BSON ObjectId với BSON String. Đây là lỗi chuyển đổi thường gặp khi Java dùng `String id` nhưng script mongosh lại truy vấn bằng kiểu khác.

### 4.2. Repository dùng đúng kiểu ID

```java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogItemRepository
        extends MongoRepository<CatalogItem, ObjectId> {
}
```

`MongoRepository<CatalogItem, ObjectId>` tương ứng với `@Id ObjectId id` trong lớp `CatalogItem` ở ví dụ trên. Đừng sao chép máy móc `JpaRepository<Entity, Long>` sang MongoDB nếu `_id` đã đổi kiểu.

## 5. Object nhúng và quan hệ: không có `@ManyToOne` tự động

Trong JPA, quan hệ nhiều-một thường có `@ManyToOne` và `@JoinColumn`; quan hệ một-nhiều có thể có `@OneToMany`, `@JoinTable` hoặc `@ElementCollection`. JPA provider quyết định cách tải/ghi các bảng và quan hệ theo metadata.

Trong MongoDB, hãy quyết định ranh giới document dựa vào **dữ liệu cần đọc/ghi cùng nhau**, vòng đời và kích thước:

### 5.1. Nhúng nested object trực tiếp

```java
@Document(collection = "orders")
public class Order {
    @Id
    private ObjectId id;

    private List<OrderLine> lines;
    private ShippingAddress shippingAddressSnapshot;
}

public class OrderLine {
    private String sku;
    private int quantity;
    private long unitPriceMinor;
}

public class ShippingAddress {
    private String city;
    private String street;
}
```

Đây là **phác thảo cấu trúc** (để chạy cần khai báo các import, constructor/getter phù hợp). Spring Data MongoDB có thể ánh xạ `OrderLine` và `ShippingAddress` thành document con ngay trong `orders` mà **không cần** gắn `@Embeddable` / `@Embedded` của JPA. Mỗi thao tác cập nhật một document được MongoDB thực hiện nguyên tử, gồm các field lồng nhau trong document đó.

```javascript
{
  _id: ObjectId("665f1f2a4b6c7d8e9f001234"),
  lines: [{ sku: "BK-101", quantity: 2, unitPriceMinor: 129000 }],
  shippingAddressSnapshot: { city: "Ha Noi", street: "Duong Mau" }
}
```

Không nên nhúng mảng tăng vô hạn: một BSON document có giới hạn **16 MiB**. Với bình luận, lịch sử sự kiện hoặc bản ghi có vòng đời độc lập, hãy cân nhắc collection riêng và tham chiếu bằng ID.

### 5.2. Tham chiếu bằng ID do ứng dụng quản lý

Ví dụ lưu `customerId` trên Order:

```java
@Document(collection = "orders")
public class Order {
    @Id
    private ObjectId id;

    private ObjectId customerId;
    private List<OrderLine> lines;
}
```

MongoDB không tự tạo foreign key từ `customerId` đến collection `customers`. Ứng dụng có thể gọi repository của Customer hoặc dùng aggregation với `$lookup` khi cần. Đây thường là cách đơn giản và minh bạch để liên kết các aggregate độc lập.

### 5.3. `@DBRef` và `@DocumentReference`

Spring Data MongoDB còn hỗ trợ metadata tham chiếu:

```java
import org.springframework.data.mongodb.core.mapping.DocumentReference;

@DocumentReference
private Customer customer;
```

Theo cách dùng mặc định phổ biến, `@DocumentReference` lưu ID của document đích và dùng thông tin mapping để tìm lại entity. `@DBRef` sử dụng cấu trúc BSON DBRef; hai cơ chế khác nhau về **dạng dữ liệu lưu** và cách resolve. Chúng không tạo khóa ngoại quan hệ, cũng không mặc nhiên thực hiện cascade insert/update/delete của JPA.

Nếu chọn lazy reference, cần tính đến truy vấn phát sinh lúc truy cập thuộc tính, cấu hình proxy và việc truy cập ngoài phạm vi phiên xử lý. Với dữ liệu được đọc thường xuyên cùng aggregate, embedding hoặc lưu bản snapshot có thể hợp lý hơn. Đừng coi `@DocumentReference` là cách tự động tái tạo `@ManyToOne` của Hibernate.

### 5.4. Những annotation JPA không nên bê nguyên sang MongoDB

| Annotation JPA | Lý do cần thiết kế lại với MongoDB |
| --- | --- |
| `@ManyToOne` / `@OneToMany` | Không tự sinh join/cascade JPA; chọn nhúng, tham chiếu ID, `@DBRef` hoặc `@DocumentReference` |
| `@JoinColumn` / `@JoinTable` | Không tự tạo cột khóa ngoại hay bảng nối; thiết kế field BSON và chỉ mục cần truy vấn |
| `@Embedded` / `@Embeddable` | MongoDB ánh xạ object thường thành nested document theo quy tắc mapping; không cần phụ thuộc hai annotation JPA |
| `@ElementCollection` | Mảng/list các giá trị thường lưu trực tiếp dưới BSON array nếu thiết kế cho phép |
| `@Enumerated` | Chọn biểu diễn enum và conversion của Spring Data; đừng phụ thuộc metadata JPA |
| `@Lob` | Chọn cách lưu Binary, String hoặc GridFS theo nhu cầu; không có ánh xạ JPA LOB tương đương trực tiếp |

## 6. Chỉ mục: `@Indexed`, `@CompoundIndex` khác DDL JPA

JPA có thể khai báo chỉ mục trong `@Table(indexes = ...)`, rồi JPA provider hoặc migration quản lý DDL quan hệ. Với MongoDB, dùng annotation mapping của Spring Data hoặc quản lý index bằng migration/script:

```java
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "catalog_items")
@CompoundIndex(
    name = "uniq_tenant_sku",
    def = "{ 'tenantId': 1, 'sku': 1 }",
    unique = true
)
public class CatalogItem {
    @Id
    private ObjectId id;
    private String tenantId;
    private String sku;

    @Indexed
    private String category;
}
```

Đây là **ví dụ khai báo metadata index**, độc lập với lớp `CatalogItem` ở phần 2; không tạo thêm một class trùng tên trong cùng project. Chỉ mục ghép cho phép cùng `sku` ở những tenant khác nhau, đồng thời chặn trùng `(tenantId, sku)` *khi index unique thực sự tồn tại và được thực thi*.

**Điểm khác quan trọng:** annotation index **không đồng nghĩa** với index đã tồn tại trong database. Trong các phiên bản Spring Data MongoDB hiện đại, tự động tạo index thường **tắt theo mặc định**; nếu muốn dùng cơ chế đó cần bật cấu hình tương ứng, hoặc chủ động tạo/quản lý index qua migration và `IndexOperations`. Trong production, thường nên quản lý index có kiểm soát để tránh thao tác DDL bất ngờ khi ứng dụng khởi động.

Kiểm tra chỉ mục thực có:

```javascript
db.catalog_items.getIndexes();
db.catalog_items.find({
  tenantId: "vn",
  sku: "PEN-101"
}).explain("executionStats");
```

Với `explain`, xem `winningPlan`, `totalKeysExamined`, `totalDocsExamined` và số document trả về để đánh giá query. Một unique index bảo đảm tính duy nhất theo định nghĩa index; nó **không tự kiểm tra** quan hệ với collection khác hay mọi quy tắc nghiệp vụ.

## 7. Version và auditing: giống mục đích, khác metadata

### 7.1. Optimistic locking với Spring Data `@Version`

```java
import org.springframework.data.annotation.Version;

@Version
private Long version;
```

Khi lưu entity có `@Version` qua cơ chế `save` hỗ trợ versioning của Spring Data MongoDB, phiên bản được kiểm tra và tăng lên phù hợp. Nếu hai request cùng đọc phiên bản cũ rồi lưu, request đến sau có thể nhận `OptimisticLockingFailureException` thay vì âm thầm ghi đè. Cần **acknowledged write concern** để phát hiện thất bại cập nhật đáng tin cậy.

JPA cũng có `@Version` nhưng là **`jakarta.persistence.Version`** và gắn với persistence context/SQL update của JPA provider. Khi dùng MongoDB, hãy import `org.springframework.data.annotation.Version`.

**Không suy ra rằng mọi lệnh cập nhật tùy biến đều kiểm tra version.** Nếu `MongoTemplate` update chỉ lọc theo `_id` hoặc script mongosh ghi trực tiếp, hãy đưa điều kiện version vào query khi cần và kiểm tra kết quả. Một số API Spring Data có thể tự tăng version khi cập nhật, nhưng việc tự tăng **không đồng nghĩa** với việc đã so khớp phiên bản client đang giữ.

Ví dụ kiểm tra version có điều kiện:

```java
Query query = Query.query(
    Criteria.where("_id").is(itemId)
        .and("version").is(expectedVersion)
);
Update update = new Update()
    .set("displayName", "Bút bi xanh mới")
    .inc("version", 1);

long changed = mongoTemplate
    .updateFirst(query, update, CatalogItem.class)
    .getModifiedCount();

if (changed == 0) {
    throw new IllegalStateException(
        "Document không tồn tại hoặc phiên bản đã thay đổi"
    );
}
```

Đây là mô hình *compare-and-set* cho một document; ví dụ giả định `itemId` và `expectedVersion` đã được xác định từ dữ liệu hiện có. Khi có logic tăng version riêng, bảo đảm không có hai con đường ghi áp dụng hai chính sách phiên bản khác nhau.

### 7.2. Auditing với `@CreatedDate` và `@LastModifiedDate`

Spring Data hỗ trợ lưu thời gian tạo/sửa thông qua auditing metadata:

```java
import java.time.Instant;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;

@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant updatedAt;
```

Cấu hình cho stack đồng bộ:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing
public class MongoAuditingConfig {
}
```

Metadata `@CreatedDate`/`@LastModifiedDate` chỉ phát huy tác dụng khi auditing được bật và thao tác ghi đi qua cơ chế hỗ trợ. Script `mongosh` hoặc lệnh driver trực tiếp không tự kích hoạt auditing của Spring Data. Với reactive stack dùng cơ chế auditing reactive tương ứng (ví dụ `@EnableReactiveMongoAuditing`) và các repository/template reactive phù hợp.

JPA thường dùng `@PrePersist`/`@PreUpdate` hay auditing của thư viện khác để thực hiện công việc tương tự. Các lifecycle callback của JPA không phải là callback của Spring Data MongoDB; nếu cần can thiệp lúc chuyển đổi/lưu, tìm hiểu các `EntityCallback` chuyên biệt như `BeforeConvertCallback`, `BeforeSaveCallback` hoặc `AfterSaveCallback`.

## 8. `@Transient`, type alias, constructor và converter

### 8.1. Field chỉ phục vụ tính toán

Đánh dấu thuộc tính không muốn lưu trong BSON:

```java
import org.springframework.data.annotation.Transient;

@Transient
private String displayLabel;
```

Đây là `org.springframework.data.annotation.Transient`. JPA có `jakarta.persistence.Transient` với tên giống nhau; khi làm việc với MongoDB, dùng metadata Spring Data để biểu đạt ý định một cách tường minh. Nếu field không được lưu mà vẫn cần lúc tạo object, hãy cân nhắc constructor và dữ liệu nào thực sự có thể phục hồi từ database.

### 8.2. Phân biệt `_class` với bảng kế thừa JPA

Spring Data MongoDB thường ghi metadata kiểu như `_class` để có thể phục hồi polymorphic types. Bạn có thể dùng:

```java
import org.springframework.data.annotation.TypeAlias;

@TypeAlias("catalogItem")
@Document(collection = "catalog_items")
public class CatalogItem {
    // Các thuộc tính của document
}
```

Đây là ví dụ metadata độc lập, không phải khai báo class thứ hai cùng tên trong project. `@TypeAlias` giúp rút ngắn giá trị type discriminator khi cấu hình mapping phù hợp; nếu đọc dữ liệu chỉ chứa alias, cần bảo đảm mapping context biết loại entity đó. Cơ chế này khác `@Inheritance` và `@DiscriminatorColumn` của JPA.

### 8.3. Constructor và chuyển đổi kiểu BSON

Khi Spring Data tái tạo object từ document, nó dùng các quy tắc chọn constructor và property population của Spring Data. Với kiểu bất biến hoặc nhiều constructor, có thể dùng `org.springframework.data.annotation.PersistenceCreator` để làm rõ đường tạo object.

Chuyển đổi phức tạp dùng `MongoCustomConversions` kết hợp Spring `Converter`, `@ReadingConverter` hoặc `@WritingConverter` nếu cần. Đừng bê nguyên `jakarta.persistence.Convert` và `AttributeConverter` của JPA rồi mong MongoDB tự xử lý như Hibernate.

Ví dụ chọn kiểu lưu thập phân:

```java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Field(targetType = FieldType.DECIMAL128)
private BigDecimal price;
```

Khi truy vấn/ghi giá tiền, cần chọn mô hình tiền tệ rõ ràng, ví dụ số nguyên ở đơn vị nhỏ nhất hoặc BSON Decimal128 theo độ chính xác nghiệp vụ. Không suy ra `@Column(precision = ..., scale = ...)` của JPA sẽ quy định BSON Decimal128.

## 9. Query và lifecycle: `JpaRepository` khác `MongoRepository`

Sự tương đồng về tên phương thức như `save`, `findById`, `deleteById` dễ gây cảm giác hai repository vận hành hệt nhau. Trong thực tế:

- JPA có persistence context; thay đổi một managed entity trong transaction có thể được flush bằng dirty checking.
- MongoDB repository đọc object từ BSON; **sửa thuộc tính Java không tự ghi lại**. Cần gọi `save` hoặc một API update rõ ràng.
- `save` trên MongoDB có thể tạo mới hoặc thay thế dữ liệu document tùy trạng thái ID/version; khi chỉ định sửa một field, nên cân nhắc `MongoTemplate.updateFirst` với điều kiện phù hợp.
- MongoDB không tự bật transaction nhiều document theo JPA. Nếu workflow cần commit đồng thời, cấu hình `MongoTransactionManager` và dùng deployment MongoDB hỗ trợ (thường replica set hoặc sharded cluster).
- `@Query` của Spring Data JPA thường chứa JPQL/SQL; `@Query` của Spring Data MongoDB dùng chuỗi JSON truy vấn MongoDB. Giữ nguyên query JPA sẽ không tạo query MongoDB tương đương.

### 9.1. Derived query và `MongoTemplate`

```java
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogItemRepository
        extends MongoRepository<CatalogItem, ObjectId> {
    List<CatalogItem> findByDisplayName(String displayName);
}
```

Tên method vẫn viết theo **thuộc tính Java** `displayName`, còn BSON field có thể là `display_name` nhờ `@Field`. Với `MongoTemplate`:

```java
Query query = Query.query(
    Criteria.where("displayName").is("Bút bi xanh")
);
List<CatalogItem> items =
    mongoTemplate.find(query, CatalogItem.class);
```

Khi chuyển sang `mongosh`, tên field cần dùng là `display_name`. Khi cần query phức tạp, Spring Data MongoDB hỗ trợ `Criteria`, aggregation pipeline, index, projection và cả reactive access; đó là API của document database, không phải một lớp bao quanh JPQL.

### 9.2. Ví dụ transaction nhiều document

Nếu thao tác cần thay đổi hai document trong MongoDB và bảo đảm đồng thời, dùng Spring transaction management với `MongoTransactionManager`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
class MongoTransactionConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
```

Ví dụ này chỉ giới thiệu hạ tầng; method nghiệp vụ cần `@Transactional`, gọi qua Spring proxy và dùng các thao tác MongoDB có tham gia cùng session/transaction. Thao tác đơn lẻ trên một document vốn đã atomic; transaction nhiều document cần được cân nhắc khi bất biến thực sự trải rộng qua nhiều document.

## 10. Checklist kiểm tra migration từ entity JPA

Giả sử nhận một entity cũ và cần dùng trong Spring Data MongoDB. Hãy kiểm tra theo thứ tự:

1. **Imports:** còn `jakarta.persistence.*` hoặc `javax.persistence.*` được dùng để mô tả mapping không? Chọn annotation Spring Data MongoDB tương ứng với thiết kế BSON.
2. **Collection:** đã khai báo `@Document` với tên collection phù hợp chưa? Class không có `@Document` có đang dựa vào quy ước tên ngoài ý muốn không?
3. **ID:** đã quyết định BSON type của `_id`, cách sinh ID và generic type repository chưa? Kiểm tra `@Id String` với chuỗi hex hoặc chọn `@MongoId` khi cần cố định kiểu.
4. **Field naming:** `@Column(name)` có được thay bằng `@Field` nếu cần? Truy vấn, index và script raw MongoDB có dùng đúng tên BSON không?
5. **Quan hệ:** các `@ManyToOne`/`@OneToMany` được thiết kế lại thành nested document hay tham chiếu? Đã xác định dữ liệu phải cập nhật cùng nhau chưa?
6. **Index/constraint:** unique index thực sự tồn tại chưa? Có validator nào bảo vệ kiểu/độ dài/giá trị nghiệp vụ không?
7. **Version/audit:** đang import `@Version`, `@CreatedDate`, `@LastModifiedDate` của Spring Data? Auditing đã được cấu hình chưa?
8. **Converter/enum:** những kiểu đặc biệt có representation BSON nhất quán chưa (UUID, BigDecimal, Instant, enum, binary)?
9. **Ghi và transaction:** code có đang trông chờ JPA dirty checking/cascade/transaction không? Đường ghi MongoDB có bảo vệ bất biến và xung đột đồng thời không?
10. **Kiểm chứng trên dữ liệu thật:** sau khi insert/read/update thử, kết quả BSON có đúng `_id`, field name, field type, nested structure và index mong đợi không?

### Quan sát bằng `mongosh`

Trên database thử nghiệm, kiểm tra trực tiếp document đã ghi bởi ứng dụng:

```javascript
use spring_data_training

db.catalog_items.findOne(
  { sku: "PEN-101" },
  {
    _id: 1,
    sku: 1,
    display_name: 1,
    price: 1,
    version: 1,
    variants: 1,
    _class: 1
  }
);

db.catalog_items.getIndexes();
```

Với MongoDB Compass, mở collection và xem **kiểu BSON** của `_id`, `price` và cấu trúc `variants`. Nếu thấy field `displayName` trong BSON thay vì `display_name`, điều tra lại import `@Field`, lớp entity được lưu và đường ghi thực tế (Spring Data MongoDB hay driver trực tiếp).

Để quan sát loại BSON bằng aggregation:

```javascript
db.catalog_items.aggregate([
  { $match: { sku: "PEN-101" } },
  {
    $project: {
      _id: 0,
      idType: { $type: "$_id" },
      priceType: { $type: "$price" },
      hasVariants: { $isArray: "$variants" }
    }
  }
]);
```

Đây là truy vấn đọc; không thay đổi dữ liệu. Kết quả trống có thể đơn giản vì chưa có document với SKU ví dụ. Hãy thay điều kiện bằng một SKU thực có trong database thử nghiệm.

## 11. Những lỗi thường gặp và cách tìm nguyên nhân

| Hiện tượng | Khả năng cao | Cách xử lý |
| --- | --- | --- |
| Entity lưu vào collection không đúng tên | Quên `@Document(collection = ...)` hoặc ghi qua đường khác | Kiểm tra annotation, repository/template domain class, database và collection thực |
| BSON có `displayName` nhưng mong `display_name` | Vẫn dùng JPA `@Column` hoặc import `@Field` sai | Dùng `org.springframework.data.mongodb.core.mapping.Field`, đọc lại BSON |
| Tìm theo ID hợp lệ nhưng không ra kết quả | Java/BSON ID lệch kiểu String/ObjectId | Kiểm tra `_id` trong mongosh và metadata `@Id`/`@MongoId` |
| Tưởng `@GeneratedValue` tự sinh khóa như RDBMS | Annotation JPA không điều khiển ObjectId generation | Chọn ObjectId hoặc chiến lược ID ứng dụng riêng |
| Quan hệ `@ManyToOne` không tự load | MongoDB không có mapping JPA relationship tương ứng | Thiết kế ID reference, `@DocumentReference`/`@DBRef` hoặc embed |
| Đánh dấu `@Indexed(unique=true)` nhưng vẫn có dữ liệu trùng | Index chưa được tạo hoặc khác điều kiện/phạm vi | Xem `getIndexes()`, kế hoạch migration và lỗi index build |
| Thay đổi object Java nhưng MongoDB không đổi | Trông chờ dirty checking JPA | Gọi `repository.save` hoặc update có điều kiện |
| Hai request ghi đè dữ liệu nhau | Thiếu kiểm tra version hoặc query update quá rộng | Dùng `@Version`, compare-and-set, kiểm tra `modifiedCount` |
| `@CreatedDate` không có giá trị | Chưa bật auditing hoặc ghi ngoài Spring Data | Bật `@EnableMongoAuditing` phù hợp, xác nhận đường ghi |
| Lưu BigDecimal rồi thấy BSON type không như mong đợi | Chưa định nghĩa kiểu lưu, converter/driver có cấu hình khác | Dùng `@Field(targetType = FieldType.DECIMAL128)` và kiểm tra `$type` |

## 12. Bài tập thực hành

**Bài 1 — Sửa import.** Cho class JPA có `@Entity`, `@Table(name = "products")`, `@Id Long id`, `@GeneratedValue`, `@Column(name = "display_name")` và `@Version`. Hãy viết lại thành document MongoDB dùng `ObjectId` và `@Field`, khai báo đúng repository generic type. Giải thích từng thay đổi.

**Bài 2 — Kiểm chứng String/ObjectId.** Tạo hai document có `_id` cùng giá trị ký tự 24 hex nhưng khác BSON type. Viết hai truy vấn `mongosh` để tìm đúng từng document. Giải thích kết quả khi entity dùng `@Id String` so với `@MongoId String`.

**Bài 3 — Embed hay reference?** Thiết kế Order với `OrderLine[]`, `customerId` và `shippingAddressSnapshot`. Giải thích vì sao dòng hàng/địa chỉ chốt có thể nhúng, trong khi Customer thường có vòng đời riêng. Viết ví dụ document BSON.

**Bài 4 — Index có thật hay chỉ là metadata?** Khai báo một unique compound index cho `tenantId` + `sku` trên document sản phẩm; viết lệnh kiểm tra `getIndexes()` và mô tả cách xác minh dữ liệu trùng bị chặn. Nêu lý do không nên dựa vào annotation đơn lẻ ở môi trường production.

**Bài 5 — Ghi đồng thời.** Hai request cùng đọc phiên bản `2` của một CatalogItem và thay tên sản phẩm khác nhau. Trình bày kết quả khi dùng repository `save` với Spring Data `@Version`, và rủi ro khi dùng `MongoTemplate.updateFirst` chỉ lọc bằng `_id`.

**Bài 6 — Auditing và converter.** Bổ sung `createdAt`, `updatedAt` và `price` dạng BSON Decimal128. Cấu hình auditing, lưu một document thử bằng repository rồi dùng `mongosh` kiểm tra timestamp và `$type` của `price`.

### Ghi nhớ

Metadata **Spring Data MongoDB** mô tả cách chuyển Java object thành **BSON document**; annotation **JPA** mô tả entity trong mô hình quan hệ và có những cơ chế riêng như khóa ngoại, persistence context và dirty checking. Các annotation cùng tên như `@Id` hoặc `@Version` phải được import đúng package. Trong MongoDB, hãy chủ động thiết kế `_id`, field BSON, dữ liệu nhúng/tham chiếu, index, auditing và đường cập nhật; luôn kiểm chứng document và index thực tế bằng `mongosh` hoặc Compass.
