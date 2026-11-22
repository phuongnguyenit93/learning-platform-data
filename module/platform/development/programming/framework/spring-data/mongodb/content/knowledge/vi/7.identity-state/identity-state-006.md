# Phân biệt ID chưa có với document đã tồn tại

Trong MongoDB, trường `_id` dùng để định danh một document trong **một collection**. Trong ứng dụng Java dùng **Spring Data MongoDB**, trường `id` trên một đối tượng có thể được tạo tự động, được ứng dụng gán trước, hoặc được đọc từ dữ liệu đã lưu. Tuy nhiên, **có ID không đồng nghĩa với document đã tồn tại trong database**.

Đây là khác biệt quyết định giữa các nghiệp vụ tạo mới, chỉnh sửa, ghi đè và tạo hoặc cập nhật. Ví dụ, ứng dụng cấp trước mã `"ORD-2026-001"` cho đơn hàng mới; mã này đã có trong bộ nhớ Java, nhưng database chưa chắc có document tương ứng. Nếu gọi sai API, ứng dụng có thể vô tình chèn, ghi đè hoặc tạo lại một document đã xóa.

Bài học thuộc chương **Định danh và trạng thái** của module `SPRING_DATA_MONGODB`. Kiến thức này là nền tảng khi ánh xạ document, dùng `MongoTemplate` hoặc repository, thiết kế query/update, optimistic locking, transaction, reactive access, kiểm thử và chẩn đoán dữ liệu.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt bốn khái niệm: **ID đã được gán**, **document tồn tại trong collection**, **entity được Spring Data coi là mới** và **ý định thao tác của nghiệp vụ**.
2. Hiểu mapping `@Id`, `@MongoId`, `_id` và cơ chế tự sinh ObjectId.
3. Giải thích cách Spring Data xác định `isNew` khi có `@Id`, `@Version` hoặc interface `Persistable`.
4. Chọn giữa `insert`, `save`, `updateFirst`, `findAndModify` và `upsert` dựa vào yêu cầu tạo mới hoặc cập nhật.
5. Phân biệt kết quả `existsById`, `findById`, `matchedCount`, `modifiedCount`, `upsertedId` và exception.
6. Ngăn các lỗi mất cập nhật, tạo trùng, tái tạo document đã xóa và kiểm tra tồn tại bị thay đổi do thao tác đồng thời.
7. Thiết kế API và bộ kiểm thử phù hợp cho dữ liệu có ID tự sinh hoặc ID do ứng dụng cấp.

## 2. Bốn trạng thái cần tách riêng

Khi viết một service Spring Data MongoDB, không nên dùng một biến duy nhất như `hasId` để thay thế mọi câu hỏi về trạng thái.

| Câu hỏi | Thuộc phạm vi nào? | Ví dụ |
| --- | --- | --- |
| Đối tượng Java **có giá trị ID** chưa? | Trạng thái **trong bộ nhớ** | `entity.getId() != null`. |
| Trong collection có document ứng với ID đó chưa? | Trạng thái **database tại thời điểm đọc** | `repository.existsById(id)`. |
| Spring Data **đánh giá entity có mới** không? | Quy tắc mapping/framework | `@Id`, `@Version` hoặc `Persistable.isNew()`. |
| Người dùng muốn **tạo**, **chỉnh sửa** hay **upsert**? | Quy tắc **nghiệp vụ** | POST create-only, PATCH update-only, import có upsert. |

Ví dụ:

```text
Java object:  { id: "CUS-42", name: "Lan" }
Database:     collection customers chưa có _id = "CUS-42"

Kết luận:
- Java object có ID                 -> ĐÚNG
- Document đã tồn tại trong MongoDB -> SAI
- Đây có thể là entity mới theo nghiệp vụ -> ĐÚNG
- Cần chọn insert/save/upsert        -> PHỤ THUỘC nghiệp vụ
```

Một ID có thể được tạo bằng UUID ngay lúc nhận request. Việc cấp UUID không ghi bất kỳ dữ liệu nào xuống MongoDB. Ngược lại, một document có thể đã tồn tại nhưng entity Java hiện tại có `id == null` do ứng dụng bỏ qua ID khi ánh xạ DTO, tạo object mới hoặc dùng sai định dạng ID.

### Ma trận tình huống

Giả sử document thuộc collection `customers`, không có `@Version` và dùng quy tắc nhận diện mặc định theo ID:

| Java `id` | Document trong DB | Spring Data mặc định coi entity là mới? | Điều cần hiểu |
| --- | --- | --- | --- |
| `null` | Chưa tồn tại dưới ID mới | **Có** | Có thể cần sinh ID khi insert. |
| `"CUS-42"` | Chưa tồn tại | **Không** | ID đã gán khiến framework suy đoán “không mới”, dù thực tế DB trống. |
| `"CUS-42"` | Đã tồn tại | **Không** | Phù hợp với thao tác cập nhật nhưng vẫn cần xử lý đồng thời. |
| `null` | Có document khác mang cùng thông tin nghiệp vụ | **Có** | Sinh ID khác không ngăn trùng email/mã bên ngoài nếu thiếu unique index. |

Bảng phản ánh **quy tắc isNew mặc định**, không phải lời khẳng định framework luôn phải hỏi database trước khi ghi.

## 3. MongoDB _id và ánh xạ ID của Spring Data

### 3.1. MongoDB yêu cầu _id cho mỗi document

MongoDB lưu document với trường `_id`. Giá trị `_id` phải duy nhất **trong collection**. Nó có thể là ObjectId, string hoặc kiểu BSON hợp lệ khác theo giới hạn của MongoDB.

```javascript
db.customers.insertOne({
  _id: "CUS-42",
  name: "Lan",
  status: "ACTIVE"
});
```

Nếu collection đã có document có cùng `_id`, lần insert nữa sẽ gây **duplicate key error**; nó không tự chuyển thành update.

Một ObjectId là **định danh**, không phải dấu hiệu có document trong DB. Bạn có thể tạo ObjectId trong ứng dụng rồi không bao giờ insert nó.

### 3.2. @Id và ObjectId

Spring Data MongoDB có thể ánh xạ trường Java `id` sang MongoDB `_id`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customers")
public class Customer {
    @Id
    private String id;
    private String name;

    public Customer() {}

    public Customer(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
```

Một trường `String` có annotation `@Id` thường được converter tự chuyển thành BSON `ObjectId` **nếu chuỗi là ObjectId hex hợp lệ**. Nếu không chuyển được, giá trị có thể được giữ dưới dạng string. Điều này làm phát sinh lỗi khó nhận ra nếu một phần dữ liệu trong collection lưu `_id` kiểu ObjectId, phần khác lưu kiểu string nhưng trông giống nhau.

Ví dụ:

```text
Java id = "507f1f77bcf86cd799439011"

Với @Id String:
  MongoDB _id thường là ObjectId("507f1f77bcf86cd799439011")

Với @MongoId String:
  MongoDB _id được lưu là chuỗi "507f1f77bcf86cd799439011"
```

Hai giá trị này **khác kiểu BSON**, vì vậy không nên tự giả định một thao tác tìm kiếm bằng string thô ở mọi công cụ sẽ trả cùng kết quả.

### 3.3. Dùng @MongoId khi cần kiểm soát kiểu ID

```java
import org.springframework.data.mongodb.core.mapping.MongoId;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("external_orders")
public class ExternalOrder {
    @MongoId
    private String id;

    private String description;

    public ExternalOrder() {}

    public ExternalOrder(String id, String description) {
        this.id = id;
        this.description = description;
    }
}
```

`@MongoId` không có tham số giúp giữ string ID dạng string, kể cả khi chuỗi tình cờ giống ObjectId hex. Nếu thực sự muốn cách chuyển như `@Id`, có thể chỉ định `@MongoId(FieldType.OBJECT_ID)` với kiểu tương thích.

Khi tích hợp dữ liệu cũ, hãy **xác minh kiểu thực tế của `_id`** trước khi đổi annotation. Đổi annotation trên entity mà không migrate dữ liệu có thể khiến `findById`/`existsById` không tìm ra document vốn vẫn đang tồn tại.

### 3.4. ID tự sinh không có nghĩa được lưu ngay

Nếu entity có `@Id String id` với `id == null`, một lần insert/save thích hợp có thể sinh BSON ObjectId và gán chuỗi tương ứng về entity. Điều này thường áp dụng cho `String`, `ObjectId` và `BigInteger` trong mapping mặc định.

```java
Customer newCustomer = new Customer(null, "Lan");
Customer saved = mongoTemplate.insert(newCustomer);

// Sau thao tác insert thành công, saved.getId() có giá trị.
System.out.println(saved.getId());
```

Tuy nhiên, **không phải mọi kiểu ID đều tự sinh đúng với mô hình Java**. Nếu muốn mã kiểu `Long` hoặc mã nghiệp vụ như `CUS-2026-001`, ứng dụng thường phải sinh/gán giá trị tương thích trước khi insert. `@GeneratedValue` theo kiểu JPA không tự biến MongoDB thành cơ chế sequence quan hệ.

Không dùng “ID trông có vẻ hợp lệ” làm bằng chứng thao tác insert đã thành công.

## 4. Spring Data nhận diện entity mới bằng cách nào?

Ở tầng repository, Spring Data cần quyết định một entity nên đi qua nhánh **insert** hay nhánh **save**. Việc phân loại này có thể dựa trên metadata của entity, **không phải truy vấn `existsById` trước mọi lần ghi**.

| Quy tắc | Spring Data kiểm tra | Khi nào được coi là mới? |
| --- | --- | --- |
| **Không có @Version, dùng mặc định theo @Id** | ID của entity | ID `null` (hoặc `0` với kiểu nguyên thủy theo quy tắc chung). |
| **Có @Version** | Giá trị version | Wrapper version `null` hoặc primitive version `0` được coi là mới. |
| **Implements Persistable** | Kết quả `isNew()` | Entity tự quyết định qua `isNew()`. |

### 4.1. ID được cấp trước nhưng entity vẫn là bản mới

```java
Customer customer = new Customer("CUS-42", "Lan");
System.out.println(customer.getId() != null); // true
```

Nếu không có `@Version` hoặc `Persistable`, Spring Data mặc định phân loại `customer` là **not new** chỉ vì ID khác `null`. Nhưng đó là **dự đoán ở tầng ứng dụng**; MongoDB có thể chưa có `_id: "CUS-42"`.

Đây là nguyên nhân của nhầm lẫn “vì `save()` nhận object có ID nên chắc chắn DB đã có document”.

### 4.2. @Version điều chỉnh cách xác định entity mới

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("members")
public class Member {
    @Id
    private String id;

    private String displayName;

    @Version
    private Long version;

    public Member() {}

    public Member(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() { return id; }
    public String getDisplayName() { return displayName; }
    public Long getVersion() { return version; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Với:

```java
Member member = new Member("member-42", "Lan");

// id = "member-42"
// version = null
Member saved = memberRepository.save(member);
```

Ở repository, `@Version Long version == null` là tín hiệu entity **mới**, dù ID đã được gán. Nhánh ghi sẽ là **insert**. Nếu collection đã có `_id = "member-42"`, insert gây duplicate key. Nếu insert thành công, framework khởi tạo version ban đầu, thường là `0` với kiểu wrapper như `Long`.

Lưu ý: với version thuộc kiểu primitive như `long`, quy tắc trạng thái mới và giá trị khởi tạo khác. Đối với bài học và dữ liệu có ID cấp trước, `Long` dạng wrapper thường thể hiện rõ “chưa lưu” bằng `null`.

### 4.3. Persistable.isNew() cho phép entity tự xác định

Nếu ID luôn được cấp bởi ứng dụng, có thể triển khai `org.springframework.data.domain.Persistable<ID>`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("invoices")
public class Invoice implements Persistable<String> {
    @Id
    private String id;

    private long totalCents;

    @Transient
    private boolean newlyCreated = true;

    public Invoice() {}

    public Invoice(String id, long totalCents) {
        this.id = id;
        this.totalCents = totalCents;
    }

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newlyCreated;
    }

    public void markPersisted() {
        newlyCreated = false;
    }
}
```

Trường `newlyCreated` được đánh dấu `@Transient` để **không ghi vào MongoDB**. Khi lưu hoặc đọc một document đã tồn tại, ứng dụng phải chuyển cờ này về `false` bằng lifecycle callback hoặc cơ chế rehydration phù hợp.

Ví dụ callback cho entity mutable trên:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.mapping.event.AfterConvertCallback;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveCallback;

@Configuration(proxyBeanMethods = false)
class InvoiceCallbacks {

    @Bean
    AfterConvertCallback<Invoice> invoiceLoaded() {
        return (invoice, document, collection) -> {
            invoice.markPersisted();
            return invoice;
        };
    }

    @Bean
    AfterSaveCallback<Invoice> invoiceSaved() {
        return (invoice, document, collection) -> {
            invoice.markPersisted();
            return invoice;
        };
    }
}
```

Ví dụ này chỉ minh họa cách duy trì cờ cho repository khi đọc/ghi qua Spring Data. Cần thiết kế thêm constructor/hydration cho immutable entity hoặc các đường dữ liệu không đi qua callbacks. Nếu cờ `isNew()` luôn trả `true`, mỗi lần `repository.save` sẽ cố **insert**, dẫn đến lỗi duplicate key khi document đã tồn tại.

**Khi nào nên dùng cách nào?**

- ID tự sinh và mô hình đơn giản: dùng nhận diện mặc định theo `@Id`.
- ID cấp trước nhưng cần optimistic locking: cân nhắc `@Version`.
- Quy tắc tạo mới phức tạp hoặc yêu cầu đặc thù: `Persistable` kèm vòng đời được thiết kế cẩn thận.
- Muốn chắc chắn chỉ tạo hoặc chỉ sửa: lựa chọn **API ghi phù hợp**, không chỉ trông chờ vào `isNew`.

## 5. Repository.save không đồng nghĩa với “chỉ update”

Bản triển khai tiêu chuẩn `SimpleMongoRepository.save` có thể mô tả về mặt ý nghĩa như sau:

```java
// Minh họa logic lựa chọn nhánh, không phải code bạn cần tự viết:
if (entityInformation.isNew(entity)) {
    return mongoOperations.insert(entity, collectionName);
}
return mongoOperations.save(entity, collectionName);
```

Trong MongoDB, `mongoOperations.save` với entity **không dùng optimistic locking** có thể thực hiện kiểu **upsert/replacement**: document cùng ID đã có thì được thay thế; nếu chưa có, có thể tạo mới.

Vì vậy, khi dùng `MongoRepository.save` trên entity có ID do ứng dụng gán:

- Nếu Spring Data phân loại **new**, repository đi nhánh **insert**.
- Nếu Spring Data phân loại **not new**, repository dùng `MongoOperations.save`.
- Nhánh thứ hai **không bảo đảm** document đã tồn tại.
- Với entity có `@Version`, optimistic locking thêm điều kiện về version và có thể báo lỗi khi document thay đổi hoặc bị xóa; không suy từ hành vi `save` không-version sang trường hợp versioned.

### Ví dụ ID đã gán nhưng MongoDB chưa có document

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<Customer, String> {
}
```

```java
Customer candidate = new Customer("CUS-42", "Lan");
Customer saved = customerRepository.save(candidate);
```

Nếu không có `@Version` hay `Persistable` và MongoDB chưa có `CUS-42`, lời gọi có thể **tạo document mới** mặc dù Spring Data đã phân loại entity là “not new”. Nếu MongoDB đã có, tài liệu cùng ID có thể bị **thay thế** theo nội dung entity được lưu. Điều này không giống “chỉ chỉnh một trường”.

Cẩn trọng với DTO thiếu trường: tạo một entity mới chỉ có `id` và `name` rồi `save` có nguy cơ ghi mất các trường khác của document cũ do thao tác replacement.

### Khi dùng repository.insert

```java
Customer created = customerRepository.insert(
    new Customer("CUS-42", "Lan")
);
```

`insert` biểu diễn ý định **create-only**. Nếu cùng `_id` đã tồn tại, thao tác báo lỗi trùng khóa (trong Spring thường được dịch sang `DuplicateKeyException`), thay vì ghi đè. Khi ID được cấp trước, `insert` là công cụ rõ nghĩa hơn cho endpoint chỉ cho phép tạo mới.

## 6. So sánh insert, save, updateFirst, findAndModify và upsert

| Thao tác | Khi chưa có document khớp | Khi đã có document khớp | Dùng cho |
| --- | --- | --- | --- |
| `MongoTemplate.insert(entity)` | Tạo mới | Duplicate key nếu cùng `_id` | **Create-only** |
| `MongoRepository.insert(entity)` | Tạo mới | Duplicate key nếu cùng `_id` | **Create-only** |
| `MongoRepository.save(entity)` | Theo nhánh `isNew`; có thể insert hoặc save/upsert | Có thể insert trùng hoặc save/replacement tùy trạng thái entity | Lưu entity theo semantics của repository, cần hiểu `isNew` |
| `MongoTemplate.save(entity)` | Thường upsert (khi không có version) | Save/replacement; với `@Version` có optimistic locking | Lưu entity toàn phần |
| `MongoTemplate.updateFirst(query, update, type)` | **Không** tạo mới | Sửa document đầu tiên khớp query | **Update-only** |
| `MongoTemplate.findAndModify(query, update, options, type)` | Mặc định không tạo mới | Tìm và sửa trong một lệnh, có thể trả document | Update-only hoặc upsert **nếu bật tùy chọn** |
| `MongoTemplate.upsert(query, update, type)` | **Tạo mới** | Cập nhật document khớp | **Create-or-update** |

Ở bảng này, các mô tả `save` phản ánh trường hợp thông thường và có thể thay đổi do `@Version`, event callbacks hoặc cấu hình tùy biến.

### Trường hợp 1 — Chỉ tạo mới

Dùng `insert`. Duplicate key là tín hiệu xung đột chính xác khi ID đã được cấp và không thể tái sử dụng.

```java
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;

@Service
public class CustomerCreationService {
    private final CustomerRepository repository;

    public CustomerCreationService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer create(String id, String name) {
        try {
            return repository.insert(new Customer(id, name));
        } catch (DuplicateKeyException duplicate) {
            throw new IllegalStateException(
                "Customer ID đã tồn tại", duplicate);
        }
    }
}
```

Trong API HTTP, dịch xung đột sang HTTP **409 Conflict** nếu phù hợp hợp đồng API. Đừng dùng `existsById` rồi `insert` như cơ chế tránh trùng duy nhất; chỉ unique index/`_id` constraint mới bảo vệ đáng tin cậy khi hai request chạy đồng thời.

### Trường hợp 2 — Chỉ cập nhật khi đã có document

Dùng một lệnh cập nhật với query xác định document mục tiêu.

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class CustomerUpdateService {
    private final MongoTemplate template;

    public CustomerUpdateService(MongoTemplate template) {
        this.template = template;
    }

    public boolean renameExisting(String id, String newName) {
        Query query = Query.query(Criteria.where("_id").is(id));
        Update update = new Update().set("name", newName);

        UpdateResult result =
                template.updateFirst(query, update, Customer.class);

        return result.getMatchedCount() == 1;
    }
}
```

Nếu ID không có document tương ứng tại thời điểm ghi, `matchedCount == 0` và **không có document mới được tạo**. Phương thức trả `false` có thể được ánh xạ thành HTTP 404 nếu nghiệp vụ coi “không có đối tượng” là lỗi.

**Vì sao kiểm tra `matchedCount` thay vì chỉ `modifiedCount`?** Khi đặt lại `name` bằng đúng giá trị cũ, có thể có document khớp nhưng không có dữ liệu đổi. `matchedCount=1`, `modifiedCount=0` vẫn là một lần cập nhật vào đối tượng có thật.

Ví dụ trên giả định entity có `_id` kiểu string như `"CUS-42"`. Với ID kiểu khác, hãy kiểm tra quy tắc conversion của `@Id`/`@MongoId`.

### Trường hợp 3 — Chỉ cập nhật khi trạng thái phù hợp

Nếu một đơn hàng chỉ được chuyển từ `DRAFT` sang `SUBMITTED` đúng một lần:

```java
Query query = Query.query(
    Criteria.where("_id").is(orderId).and("status").is("DRAFT")
);
Update update = new Update()
    .set("status", "SUBMITTED")
    .set("submittedAt", java.time.Instant.now());

UpdateResult result =
    mongoTemplate.updateFirst(query, update, Order.class);

if (result.getMatchedCount() != 1) {
    // Không có order hoặc order đã không còn DRAFT.
}
```

Kiểm tra điều kiện và thay đổi diễn ra trong cùng một lệnh ghi trên **một document**, tránh kiểu “đọc status rồi sửa sau”. Nếu cần phân biệt cụ thể not found với trạng thái đã đổi, có thể đọc thêm để tạo thông báo, nhưng quyết định ghi thành công vẫn dựa vào kết quả cập nhật có điều kiện.

### Trường hợp 4 — Có thể tạo hoặc cập nhật: upsert

```java
Query query = Query.query(Criteria.where("_id").is(customerId));

Update update = new Update()
    .set("name", newName)
    .setOnInsert("createdAt", java.time.Instant.now());

UpdateResult result = mongoTemplate.upsert(
    query, update, Customer.class
);
```

Khi không có document khớp, MongoDB có thể insert document mới; khi có, cập nhật các trường chỉ định. `$setOnInsert` chỉ áp dụng khi insert mới, không sửa `createdAt` của document đã tồn tại.

Với lệnh upsert một document, có thể dùng `result.getUpsertedId() != null` để nhận biết trường hợp lệnh đã insert mới (tùy kiểu API và write concern có phản hồi đầy đủ). `matchedCount` phản ánh số document có sẵn đã khớp trước cập nhật.

**Quan trọng:** Chỉ dùng upsert khi nghiệp vụ **cho phép tạo mới**. Endpoint PATCH “chỉ sửa đơn hàng đã tồn tại” không nên vô tình upsert đơn hàng đã xóa.

### Trường hợp 5 — Cần trả về document sau cập nhật

```java
import org.springframework.data.mongodb.core.FindAndModifyOptions;

Customer updated = mongoTemplate.findAndModify(
    Query.query(Criteria.where("_id").is(customerId)),
    new Update().set("name", newName),
    FindAndModifyOptions.options().returnNew(true),
    Customer.class
);

if (updated == null) {
    // Không tìm thấy document, mặc định không insert mới.
}
```

`findAndModify` có thể kết hợp query có điều kiện và trả bản trước/sau trong cùng một thao tác. Hãy nhớ tùy chọn `upsert(true)`, nếu được bật, sẽ thay đổi semantics thành tạo document khi chưa có.

## 7. Optimistic locking: khi document đã tồn tại nhưng đã bị thay đổi

ID hợp lệ và document tồn tại vẫn chưa đủ để bảo đảm cập nhật đúng. Hai yêu cầu có thể cùng đọc một bản document rồi sửa trong thời gian khác nhau.

Giả sử `Member` có `@Version Long version` như mục 4:

```text
T0: Member(_id="member-42", displayName="Lan", version=0)

T1: Request A đọc version=0
T2: Request B đọc version=0
T3: A thay tên và save thành công => version=1
T4: B save bản version=0 => OptimisticLockingFailureException
```

Spring Data MongoDB thêm điều kiện version trong update cho những thao tác hỗ trợ optimistic locking. Nếu version không còn khớp, thao tác có thể ném `OptimisticLockingFailureException`; ứng dụng không được im lặng ghi đè dữ liệu mới.

```java
import org.springframework.dao.OptimisticLockingFailureException;

Member member = memberRepository.findById(id).orElseThrow();
member.setDisplayName("Tên mới");

try {
    memberRepository.save(member);
} catch (OptimisticLockingFailureException conflict) {
    // Có thay đổi hoặc xóa xảy ra đồng thời: báo conflict
    // hoặc đọc lại để áp dụng chiến lược retry nghiệp vụ.
}
```

Các chú ý quan trọng:

- Optimistic locking cần thao tác ghi **được xác nhận** (acknowledged write concern) để phát hiện kết quả thất bại đáng tin cậy.
- Không phải mọi API update tùy biến đều tự bảo vệ bằng version bạn vừa đọc. Nếu viết query riêng, phải xem cách API đó xử lý `@Version`; khi cần hãy thêm điều kiện version rõ ràng.
- Nếu document bị xóa sau khi tải, một lần save **có version cũ** thường thất bại thay vì khôi phục tùy tiện.
- Với entity **không có `@Version`**, `save` dạng replacement có thể gây lost update khi hai request cùng sửa toàn bộ entity.
- Version không thay thế unique index; hai request tạo cùng `_id` vẫn cần xử lý duplicate key.

### Update với expectedVersion trong query

```java
Query query = Query.query(
    Criteria.where("_id").is(memberId)
            .and("version").is(expectedVersion)
);

Update update = new Update().set("displayName", newName);

UpdateResult outcome = mongoTemplate.updateFirst(
    query, update, Member.class
);
```

Với entity có `@Version`, Spring Data MongoDB có thể tự tăng trường version trên các phương thức update được hỗ trợ khi `Update` không đề cập version. Đừng cộng version **hai lần** bằng cách vừa `inc("version", 1)` thủ công vừa dựa vào cơ chế tự tăng. Khi `matchedCount == 0`, nguyên nhân có thể là document vắng mặt hoặc phiên bản đã thay đổi; cần phân biệt theo yêu cầu API.

## 8. existsById cho ta biết gì và không cho ta biết gì?

`existsById(id)` trả lời việc document được tìm thấy **tại thời điểm thực hiện truy vấn**. Nó không tạo khóa, không đánh dấu entity Java đã lưu và không bảo đảm document vẫn tồn tại khi câu lệnh tiếp theo chạy.

Mẫu dễ mắc lỗi:

```java
if (!repository.existsById(id)) {
    repository.save(new Customer(id, "Lan"));
}
```

Nếu hai request cùng chạy:

```text
Request A                          Request B
---------                          ---------
existsById("CUS-42") => false
                                   existsById("CUS-42") => false
save(new Customer(...))
                                   save(new Customer(...))
```

Hai request đều nghĩ ID chưa có; vì `save` có thể upsert/replace, request sau có thể ghi đè nội dung request trước mà không báo duplicate key.

**Cách phù hợp với create-only:** dùng `insert` trực tiếp và bắt duplicate key. **Cách phù hợp với update-only:** dùng update có điều kiện, kiểm tra `matchedCount`. **Cách phù hợp với create-or-update:** dùng upsert có chủ đích.

Đọc trước khi ghi vẫn cần thiết khi tính toán nghiệp vụ phức tạp, nhưng phải kết hợp điều kiện trên update, optimistic locking hoặc transaction để tránh khoảng hở giữa đọc và ghi.

## 9. Document bị xóa rồi lại xuất hiện

Đây là lỗi nghiêm trọng khi service dùng `save` không version như “chỉnh sửa”.

1. User A đọc document `_id="CUS-42"`.
2. User B xóa document này.
3. User A chỉnh tên rồi gọi `repository.save`.
4. Nếu đi vào semantics `save`/upsert không version, document có thể được **tạo lại**.

Đó là tình huống “resurrection” (tái tạo ngoài ý muốn) do không phân biệt cập nhật document đã có với quyền tạo mới.

Các cách xử lý theo nhu cầu:

- **Update-only:** `updateFirst` có query theo `_id` và điều kiện nghiệp vụ, mặc định không upsert.
- **Optimistic locking:** lưu version để cập nhật thất bại khi document đã đổi/xóa (với phương thức hỗ trợ version).
- **Soft delete:** thêm trường `deletedAt` hoặc `status` và bộ lọc `deletedAt: null` trong các truy vấn cần document còn hoạt động; cần nhất quán ở toàn bộ đường ghi.
- **Đảm bảo không tái sử dụng ID:** giữ lịch sử/tombstone hoặc quy tắc ID không tái sử dụng nếu nghiệp vụ đòi hỏi; chỉ xóa cứng rồi kiểm tra tồn tại trước khi tạo không loại bỏ race condition.

Không nên xóa rồi tự động `save` để “khôi phục” nếu API không có chức năng phục hồi được xác nhận.

## 10. REST API: nói rõ ngữ nghĩa thay vì đoán từ ID

| Endpoint/nghiệp vụ | Ý định | Gợi ý thao tác | Trạng thái khi không tìm thấy/trùng |
| --- | --- | --- | --- |
| `POST /customers` | **Tạo mới** | `insert` | 409 nếu ID/unique key trùng; 201 khi tạo thành công |
| `PUT /customers/{id}` với hợp đồng **replace-only** | **Thay thế nếu đã có** | Replace/update có điều kiện, **không upsert** | 404 nếu document không tồn tại |
| `PUT /customers/{id}` với hợp đồng **create-or-replace** | **Upsert có chủ đích** | `upsert` hoặc replace với upsert option | 201 nếu tạo, 200/204 nếu cập nhật tùy hợp đồng |
| `PATCH /customers/{id}` | **Sửa vài trường nếu đã có** | `updateFirst` hoặc `findAndModify` không upsert | 404 nếu không có |
| `DELETE /customers/{id}` | **Xóa** | Delete có điều kiện theo ID/version tùy nghiệp vụ | 404 hoặc 204 nếu không có theo hợp đồng |
| Import/sync dữ liệu ngoài | **Tạo hoặc cập nhật** | Upsert có unique key phù hợp | Ghi nhận inserted/updated đúng thực tế |

Các mã HTTP là lựa chọn thiết kế API, không phải hành vi bắt buộc của Spring Data. Điều quan trọng là hợp đồng nêu rõ **không tồn tại thì có được tạo không**.

### Cần phân biệt ID với business key

Khách hàng có thể có:

```json
{
  "_id": "CUS-42",
  "email": "lan@example.test",
  "displayName": "Lan"
}
```

`_id` duy nhất không tự bảo vệ `email`. Nếu email phải duy nhất, tạo **unique index** và xử lý duplicate key tương ứng. Một lần `existsByEmail` trước `insert` không đủ loại bỏ xung đột đồng thời.

Tương tự, khi đồng bộ từ hệ thống ngoài, nên thiết kế ID ổn định hoặc khóa duy nhất phù hợp để upsert an toàn và có idempotency. Không coi một mã nghiệp vụ chưa từng xuất hiện trong cache là bằng chứng collection chưa chứa dữ liệu ấy.

## 11. Đọc dữ liệu đúng kiểu và đúng collection

Khi `findById` trả `Optional.empty()`, có nhiều nguyên nhân cần kiểm tra:

- Document thực sự chưa tồn tại trong collection.
- Kết nối đang trỏ sang **database** hoặc **collection** khác.
- ID Java được convert sang `ObjectId`, nhưng document lưu `_id` dạng string hoặc ngược lại.
- Dữ liệu vừa bị xóa hoặc việc đọc dùng read preference/consistency không đáp ứng kỳ vọng thời gian của nghiệp vụ.
- Bộ lọc query bổ sung (nếu có) không thỏa, ví dụ chỉ lấy document chưa bị soft delete.

Ví dụ khi debug bằng Mongo shell:

```javascript
db.customers.findOne({ _id: "CUS-42" });

// Chỉ để minh họa khác biệt BSON:
db.customers.findOne({
  _id: ObjectId("507f1f77bcf86cd799439011")
});
db.customers.findOne({
  _id: "507f1f77bcf86cd799439011"
});
```

Hai query cuối tìm **hai kiểu BSON khác nhau**. Hãy kiểm tra annotation `@Id`/`@MongoId` và conversion của Spring Data, đừng chỉ so sánh chuỗi in ra log.

Nếu `findById` của repository trả empty nhưng `MongoTemplate` query dạng thô trả document, trước hết xem đúng mapping, collection và kiểu ID; không vội sửa bằng cách tạo document mới.

## 12. Reactive Spring Data MongoDB cũng có cùng bài toán

Với reactive access, `ReactiveMongoRepository` và `ReactiveMongoTemplate` phản hồi qua `Mono`/`Flux`, nhưng bản chất các khái niệm vẫn vậy:

- ID được cấp chưa chứng minh database có document.
- `save` có semantics của repository và state detection; `insert` rõ nghĩa cho create-only.
- `updateFirst` không tự upsert; hãy kiểm tra số document khớp.
- Kiểm tra tồn tại rồi ghi tiếp ở hai bước reactive cũng có thể gặp race condition.

Ví dụ:

```java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface ReactiveCustomerRepository
        extends ReactiveMongoRepository<Customer, String> {
}
```

```java
reactiveCustomerRepository.insert(new Customer("CUS-42", "Lan"))
    .onErrorMap(
        org.springframework.dao.DuplicateKeyException.class,
        ex -> new IllegalStateException("Customer ID đã tồn tại", ex)
    );
```

Không dùng `block()` tùy tiện trong reactive pipeline. Để xử lý quy tắc cập nhật có điều kiện, `ReactiveMongoTemplate` cung cấp API tương đương theo kiểu phản ứng; kiểm tra `matchedCount` sau khi `Mono<UpdateResult>` phát kết quả.

## 13. Kiểm thử những tình huống dễ bị nhầm

Khi xây dựng bài kiểm thử tích hợp, dùng collection/database riêng. Có thể dùng MongoDB test container với cùng dòng MongoDB Server mục tiêu. Nên kiểm thử các kịch bản sau:

| Kịch bản | Thao tác | Kỳ vọng |
| --- | --- | --- |
| **ID null, create-only** | `insert(new Customer(null, ...))` | Sinh ID phù hợp và có document sau insert. |
| **ID gán trước, DB trống** | `insert(new Customer("CUS-42", ...))` | Tạo mới thành công. |
| **ID gán trước, DB đã có** | `insert` cùng ID | Duplicate key, không ghi đè document cũ. |
| **ID gán trước, DB trống** | `repository.save` với entity không version | Có thể upsert tạo mới; đừng coi là update-only. |
| **ID gán trước, DB trống** | `updateFirst` | `matchedCount == 0`, không có document mới. |
| **ID gán trước, DB trống** | `upsert` | Tạo document mới; quan sát `upsertedId`. |
| **@Version null, ID gán trước** | `repository.save` với versioned entity | Đi nhánh insert; bản đã có cùng ID gây duplicate key. |
| **Version cũ** | Hai lần save bản copy với cùng version ban đầu | Lần save sau thất bại do optimistic locking. |
| **Document bị xóa sau khi đọc** | Update-only không upsert | Không phục hồi document ngoài ý muốn. |
| **Dùng @Id và @MongoId khác nhau** | Query chuỗi hex 24 ký tự | Phát hiện khác biệt kiểu BSON, điều chỉnh mapping. |
| **Hai request create đồng thời** | Cùng `insert` với một ID | Một thành công, một duplicate key. |
| **Hai request kiểm tra rồi save** | Cùng ID, không version | Có thể ghi đè; test phải phát hiện vấn đề. |

### Test minh họa: tạo trùng ID

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DuplicateKeyException;

@SpringBootTest
class CustomerIdentityIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void insertRejectsDuplicateId() {
        // Dùng ID duy nhất cho mỗi lần chạy, tránh phụ thuộc dữ liệu cũ.
        String id = "CUS-" + java.util.UUID.randomUUID();

        repository.insert(new Customer(id, "Lan"));

        assertThatThrownBy(() ->
            repository.insert(new Customer(id, "Minh"))
        ).isInstanceOf(DuplicateKeyException.class);

        Customer stored = repository.findById(id).orElseThrow();
        assertThat(stored.getName()).isEqualTo("Lan");
    }
}
```

Test này đòi hỏi MongoDB test thực sự được cấu hình; mã minh họa nằm trong dự án có Spring Boot test starter và repository đã khai báo. Test nên chạy trên môi trường có quyền ghi, với dữ liệu không chứa thông tin cá nhân thật.

### Test minh họa: update không tự tạo mới

```java
@Test
void updateOnlyDoesNotCreateMissingDocument() {
    String id = "CUS-" + java.util.UUID.randomUUID();

    UpdateResult result = mongoTemplate.updateFirst(
        Query.query(Criteria.where("_id").is(id)),
        new Update().set("name", "Lan"),
        Customer.class
    );

    assertThat(result.getMatchedCount()).isZero();
    assertThat(customerRepository.existsById(id)).isFalse();
}
```

Trong class test thực tế cần inject `MongoTemplate` và `CustomerRepository`, thêm các import `Query`, `Criteria`, `Update`, `UpdateResult` và AssertJ. Hai test chứng minh đúng nghĩa vụ **create-only** và **update-only**; không chỉ chứng minh lời gọi không ném lỗi.

## 14. Những sai lầm phổ biến

**“ID khác null thì document chắc chắn đã tồn tại.”**  
Sai. ID có thể được cấp trước hoặc sinh trong bộ nhớ mà chưa ghi xuống MongoDB.

**“Repository.save luôn cập nhật bản cũ.”**  
Sai. Repository dựa vào `isNew` để chọn nhánh; `MongoOperations.save` có thể upsert khi không dùng version. Một endpoint chỉ được update nên dùng lệnh không upsert.

**“Có @Version thì mọi thao tác đều tự an toàn.”**  
Không. Optimistic locking hoạt động theo các API có hỗ trợ; query update tùy biến và external writers phải tuân thủ cùng quy tắc nếu muốn bảo vệ xung đột.

**“existsById=false rồi insert chắc chắn không trùng.”**  
Không. Một request khác có thể insert giữa hai lệnh. Dựa vào unique constraint và bắt lỗi trùng.

**“modifiedCount=0 nghĩa là document chưa tồn tại.”**  
Không. Document có thể khớp nhưng dữ liệu mới bằng dữ liệu cũ. Dùng `matchedCount` để kiểm tra có document khớp.

**“findById không thấy thì cứ save một bản mới.”**  
Không. Kiểm tra database/collection, conversion `_id`, trạng thái xóa và chính sách tạo mới của nghiệp vụ.

**“save khi cập nhật không làm mất trường khác.”**  
Không nên giả định. Save entity toàn phần có thể thay thế document; với thay đổi một vài trường, dùng `Update.set` và query phù hợp.

## 15. Bài tập thực hành

### Bài 1 — ID đã cấp nhưng chưa lưu

Tạo object `Customer("CUS-77", "Hà")` mà chưa insert. Nêu kết quả dự kiến của:

1. `customer.getId() != null`.
2. `repository.existsById("CUS-77")` (giả sử DB trống).
3. `repository.save(customer)` với entity không có `@Version`.
4. `repository.insert(customer)` nếu `save` ở bước 3 đã thành công.

Giải thích vì sao phải phân biệt trạng thái Java, database và `isNew`.

### Bài 2 — Chọn API theo hợp đồng

Thiết kế ba phương thức: `createOnly`, `updateOnly`, `upsertAllowed`. Mỗi phương thức nhận `id` và `name`. Chọn API MongoDB thích hợp, cách xử lý ID trùng hoặc document vắng mặt và kết quả HTTP tương ứng.

### Bài 3 — @Version với assigned ID

Dùng entity `Member` với `id = "member-22"` và `version = null`. Dự đoán lựa chọn insert/save của repository và version sau insert. Sau đó thực hiện hai lần đọc, sửa và lưu đồng thời để quan sát optimistic locking.

### Bài 4 — ID mapping gây lỗi tìm kiếm

Tạo hai document trong môi trường thử: một document có `_id` kiểu ObjectId, một document có `_id` kiểu string với cùng chuỗi hex biểu diễn. Thử entity `@Id String` và `@MongoId String`; giải thích query nào khớp giá trị nào.

### Bài 5 — Đơn hàng đã xóa xuất hiện trở lại

Một request đọc Order A, request khác xóa Order A, rồi request đầu gọi `save`. Hãy phân tích kết quả khi entity có và không có `@Version`; đề xuất cách tránh tái tạo document ngoài ý muốn.

### Gợi ý đáp án

1. Object có ID, DB ban đầu chưa có, `isNew` mặc định đánh giá “không mới” vì ID khác null; `save` có thể tạo document qua upsert; `insert` sau đó trùng ID.
2. Create-only → `insert`; update-only → `updateFirst`/`findAndModify` không upsert; create-or-update → `upsert` có chủ đích.
3. Wrapper `@Version Long` null → nhận diện “mới” và insert. Khi đã tồn tại và thay đổi version, lần save bằng bản cũ phát sinh optimistic locking conflict.
4. BSON ObjectId và string khác kiểu; mapping ID phải trùng với dữ liệu được lưu.
5. Không-version `save` có thể tạo lại document; dùng update-only, optimistic locking hoặc cơ chế xóa mềm phù hợp.

## 16. Checklist trước khi phát hành tính năng

- [ ] Xác định ID do MongoDB tự sinh hay do ứng dụng cấp trước.
- [ ] Kiểm tra `@Id` hoặc `@MongoId` và kiểu BSON thật của `_id`.
- [ ] Xác định rõ entity state detection theo ID, `@Version` hay `Persistable`.
- [ ] Chọn create-only, update-only hoặc upsert có chủ đích.
- [ ] Không dùng `existsById` trước khi ghi như biện pháp tránh trùng duy nhất.
- [ ] Dùng `matchedCount` để xác nhận document khớp; không suy từ `modifiedCount`.
- [ ] Bảo vệ trường hợp nhiều request cùng cập nhật bằng query có điều kiện hoặc optimistic locking.
- [ ] Xem xét rủi ro document bị xóa rồi tự xuất hiện lại.
- [ ] Kiểm tra unique index của business key và cơ chế idempotency.
- [ ] Test từng tình huống ID null, assigned ID, missing document, duplicate ID, stale version và query mapping.
- [ ] Không kết luận “không tồn tại” trước khi xác nhận database/collection/kiểu ID đúng.

## 17. Tài liệu tham khảo chính thức

1. [Spring Data Commons — Entity State Detection Strategies](https://docs.spring.io/spring-data/data-mongo/reference/4.5/repositories/core-concepts.html): quy tắc `@Id`, `@Version` và `Persistable`.
2. [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `insert`, `save`, `upsert`, `@MongoId` và optimistic locking.
3. [Spring Data MongoDB — MongoOperations API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/MongoOperations.html): ngữ nghĩa của API ghi.
4. [Spring Data MongoDB — SimpleMongoRepository Source](https://github.com/spring-projects/spring-data-mongodb/blob/main/spring-data-mongodb/src/main/java/org/springframework/data/mongodb/repository/support/SimpleMongoRepository.java): cách repository sử dụng `isNew` để chọn insert/save.
5. [Spring Data MongoDB — Entity Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html): `AfterSaveCallback` và `AfterConvertCallback`.
6. [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): bảo vệ tính duy nhất của khóa.
7. [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): tính nguyên tử và các thao tác cập nhật có điều kiện.

**Ghi nhớ:** Một ID chỉ là **giá trị định danh**. Nó không chứng minh rằng MongoDB có document tương ứng, và `isNew` là quy tắc Spring Data áp dụng cho entity chứ không phải một truy vấn tồn tại mặc định. Hãy chọn chính xác ngữ nghĩa **insert**, **update không upsert** hoặc **upsert**, đồng thời bảo vệ tính đúng đắn khi nhiều thao tác diễn ra đồng thời.
