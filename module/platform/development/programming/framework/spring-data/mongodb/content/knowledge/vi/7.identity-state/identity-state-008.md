# Giá trị ID trả về sau insert hoặc save

## 1. Vì sao phải quan tâm ID sau khi ghi?

Trong MongoDB, mỗi document có trường **_id** dùng để định danh duy nhất trong một collection. Khi tạo một document mới, ứng dụng có thể tự cung cấp _id hoặc để cơ chế ghi dữ liệu sinh ID. Một câu hỏi rất thực tế là: **sau khi gọi insert hoặc save, lấy ID vừa lưu ở đâu và giá trị ấy có giống với ID trước khi gọi không?**

Trong module **SPRING_DATA_MONGODB**, câu hỏi này xuất hiện ở cả **MongoTemplate** và **MongoRepository**. ID còn liên quan đến cách ánh xạ BSON với entity Java, truy vấn theo khóa, update, optimistic locking, transaction, reactive access, kiểm thử và chẩn đoán các lỗi như ghi trùng hoặc truy vấn không tìm thấy document. Hiểu đúng giá trị ID sau thao tác ghi giúp ứng dụng trả ID cho API, tạo liên kết giữa document và tránh lưu hai lần một thực thể.

**Ý chính của bài:** Các phương thức insert/save cấp cao của Spring Data MongoDB thường **trả về entity đã lưu**, không trả về một ID rời. Để lấy ID, hãy đọc từ **entity được phương thức trả về**. Nếu entity là immutable hoặc có cơ chế mapping tùy chỉnh, không được mặc định đối tượng đầu vào đã bị thay đổi tại chỗ.

Sau bài này, bạn có thể:

1. Phân biệt _id BSON, trường ID Java và kiểu giá trị ID được trả về.
2. Lấy ID sau **MongoTemplate.insert**, **MongoTemplate.save**, **MongoRepository.insert** và **MongoRepository.save**.
3. Hiểu trường hợp ID được sinh tự động, được cung cấp trước hoặc bị trùng.
4. Xử lý ID đúng cách với entity mutable, immutable và reactive.
5. Phân biệt ID với trạng thái new/existing và với trường **@Version**.
6. Viết kiểm thử vòng đời ID và tìm nguyên nhân khi ID không như mong đợi.

## 2. ID của MongoDB được biểu diễn như thế nào?

Một document MongoDB có dạng:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  orderNumber: "ORD-1001",
  customerName: "Lan"
}
~~~

**_id** là field định danh của document. MongoDB tạo một unique index trên _id cho collection thông thường; hai document trong cùng collection không thể có cùng giá trị _id. Nếu document được tạo mà không cung cấp _id, driver thường sinh **ObjectId**. MongoDB cũng có thể sử dụng các kiểu ID hợp lệ khác như String hoặc UUID/Binary theo thiết kế ứng dụng; ObjectId là lựa chọn phổ biến nhưng không bắt buộc.

Trong Java, Spring Data MongoDB thường ánh xạ một thuộc tính mang **@Id** thành field **_id**:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;

@Id
private ObjectId id;
~~~

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Field BSON | _id | Khóa lưu trong document MongoDB. |
| Thuộc tính Java | id | Nơi entity biểu diễn khóa document. |
| Giá trị ObjectId | ObjectId("507f1f77bcf86cd799439011") | Giá trị BSON 12 byte, thường hiển thị bằng 24 ký tự hex. |
| Chuỗi ID API | "507f1f77bcf86cd799439011" | Cách biểu diễn ở ranh giới HTTP/JSON; bản thân chuỗi không phải ObjectId BSON. |
| Giá trị ID trả về | saved.getId() | ID được đọc từ entity sau thao tác lưu. |

Một lưu ý quan trọng: **ObjectId và String có cùng chuỗi ký tự hiển thị vẫn khác kiểu BSON**. Truy vấn bằng chuỗi thuần có thể không tìm thấy document có _id là ObjectId nếu việc chuyển đổi kiểu không được thực hiện. Nên thống nhất chính sách ID ngay từ lúc khai báo entity.

## 3. Phương thức insert và save trả về gì?

Đối với API Spring Data MongoDB thông dụng, các phương thức sau trả về entity:

| API | Chữ ký minh họa | Bạn lấy ID ở đâu? |
| --- | --- | --- |
| MongoTemplate.insert | T insert(T objectToSave) | Đọc ID từ đối tượng kết quả. |
| MongoTemplate.save | T save(T objectToSave) | Đọc ID từ đối tượng kết quả. |
| MongoRepository.insert | S insert(S entity) | Đọc ID từ entity kết quả. |
| MongoRepository.save | S save(S entity) | Đọc ID từ entity kết quả. |
| ReactiveMongoTemplate.insert/save | Mono<T> | Lấy ID khi Mono phát ra entity đã ghi. |
| ReactiveMongoRepository.insert/save | Mono<S> | Lấy ID trong luồng reactive sau khi ghi thành công. |

Ví dụ mô hình chung:

~~~java
OrderDocument saved = repository.insert(order);
ObjectId id = saved.getId();
~~~

Điều đó khác với MongoDB Java Driver cấp thấp: **insertOne** trả một **InsertOneResult** và có thể cung cấp **getInsertedId()**. Không nên áp dụng nhầm kiểu trả về của driver trực tiếp cho MongoRepository hoặc MongoTemplate.

### 3.1. Khác nhau về ý định giữa insert và save

- **insert** biểu đạt ý định tạo document mới. Nếu _id bị trùng một document đã tồn tại, MongoDB báo lỗi duplicate key thay vì ghi đè document ấy.
- **save** thường là thao tác lưu trạng thái entity. Với entity mới, nó có thể dẫn tới insert; với entity đã có ID, tùy API, cách xác định entity mới và cơ chế optimistic locking, nó có thể thực hiện replace/update hoặc upsert.
- **MongoTemplate.save** thường thay thế document theo _id hoặc insert khi chưa có bản tương ứng, trong khi **MongoRepository.save** dùng thông tin trạng thái entity để quyết định đường insert hoặc save. Vì vậy, không suy từ tên save rằng luôn dùng đúng một lệnh ở tầng driver.

**Cả hai đều có thể trả về entity mang ID.** Nhưng việc có ID không chứng minh một document mới vừa được tạo: save với ID đã tồn tại có thể ghi lại document cũ.

## 4. Ví dụ hoàn chỉnh: entity có ObjectId

Định nghĩa một entity mutable:

~~~java
package com.example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public class OrderDocument {

    @Id
    private ObjectId id;

    private String orderNumber;
    private Instant createdAt;

    public OrderDocument() {
    }

    public OrderDocument(String orderNumber, Instant createdAt) {
        this.orderNumber = orderNumber;
        this.createdAt = createdAt;
    }

    public ObjectId getId() {
        return id;
    }

    public void setId(ObjectId id) {
        this.id = id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public void setOrderNumber(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
}
~~~

Trước lần ghi đầu tiên, đối tượng được tạo bằng constructor hai tham số có **id == null**:

~~~java
OrderDocument draft = new OrderDocument(
    "ORD-1001",
    Instant.parse("2025-05-20T09:00:00Z")
);
System.out.println(draft.getId()); // null
~~~

Lúc ghi, Spring Data MongoDB và MongoDB driver xử lý document, có thể sinh _id theo cơ chế ObjectId rồi trả giá trị đó về entity. Giá trị cụ thể thay đổi theo từng lần tạo, vì vậy không nên hardcode ID ví dụ thành giá trị kỳ vọng trong test.

~~~mermaid
sequenceDiagram
    participant A as Java application
    participant S as Spring Data MongoDB
    participant M as MongoDB
    A->>S: insert(entity, id = null)
    S->>M: Insert BSON document
    M-->>S: Xác nhận ghi với _id
    S-->>A: Entity kết quả có ID
    A->>A: saved.getId()
~~~

**Đừng phụ thuộc vào việc mọi entity đầu vào đều bị sửa trực tiếp.** Hãy xem đối tượng được trả về là nguồn đáng tin cậy cho trạng thái đã ghi, đặc biệt khi entity immutable hoặc sử dụng converter riêng.

## 5. MongoTemplate.insert: lấy ID sau insert

Ví dụ thao tác trong một service có MongoTemplate:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;

public class CreateOrderWithTemplate {
    private final MongoTemplate mongoTemplate;

    public CreateOrderWithTemplate(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public ObjectId create(String orderNumber) {
        OrderDocument draft = new OrderDocument(
            orderNumber,
            Instant.now()
        );

        OrderDocument inserted = mongoTemplate.insert(draft);
        ObjectId generatedId = inserted.getId();

        if (generatedId == null) {
            throw new IllegalStateException("Insert returned entity without id");
        }
        return generatedId;
    }
}
~~~

Khi dùng **mongoTemplate.insert(draft)**, Spring Data chọn collection theo **@Document(collection = "orders")**. Trả về ID vừa sinh cho tầng API giúp client có thể gọi tiếp endpoint truy xuất theo ID.

Với entity mutable như OrderDocument, cơ chế mapping có thể gán ID lên chính đối tượng được truyền vào. Tuy nhiên, cách viết **inserted.getId()** vẫn phù hợp hơn, vì Spring Data cũng hỗ trợ immutable entity hoặc thiết kế trong đó kết quả mapping là một instance khác.

### 5.1. Chỉ định collection trực tiếp

MongoTemplate có overload nhận tên collection:

~~~java
OrderDocument saved =
    mongoTemplate.insert(draft, "orders_archive");
ObjectId id = saved.getId();
~~~

ID vẫn được đọc từ entity kết quả. Nhưng document thực tế được ghi vào collection **orders_archive**, không phải collection mặc định **orders** trong @Document. Lệnh đọc sau đó phải chọn đúng database/collection; lấy đúng ID mà truy vấn sai collection vẫn có thể trả null.

## 6. MongoTemplate.save: ID sau lưu mới và lưu lại

Lệnh save có hai tình huống cần phân biệt:

### 6.1. Lưu entity mới, chưa có ID

~~~java
OrderDocument draft = new OrderDocument(
    "ORD-1002",
    Instant.now()
);

OrderDocument saved = mongoTemplate.save(draft);
ObjectId id = saved.getId();
~~~

Trong kịch bản mặc định với ID kiểu ObjectId để null, **save có thể tạo document mới và trả entity mang ID**.

### 6.2. Lưu entity đã có ID

~~~java
OrderDocument existing = mongoTemplate.findById(
    id,
    OrderDocument.class
);

if (existing != null) {
    existing.setOrderNumber("ORD-1002-UPDATED");
    OrderDocument savedAgain = mongoTemplate.save(existing);
    ObjectId sameId = savedAgain.getId();
}
~~~

Với cùng một document, **ID không tự tăng sau mỗi lần save**. ID xác định danh tính document; thay đổi tên đơn hoặc các thuộc tính khác không phải lý do tạo một _id mới. Nếu muốn tạo một document khác, ứng dụng phải thực hiện thao tác tạo mới với ID thích hợp.

### 6.3. Save với ID do ứng dụng tự cung cấp

~~~java
ObjectId chosenId = new ObjectId();

OrderDocument order = new OrderDocument(
    "ORD-1003",
    Instant.now()
);
order.setId(chosenId);

OrderDocument saved = mongoTemplate.save(order);
System.out.println(saved.getId().equals(chosenId)); // true nếu ghi thành công
~~~

**Có ID từ trước không đồng nghĩa document đã tồn tại.** Với MongoTemplate.save và không có @Version hay ràng buộc bổ sung, thao tác có thể upsert theo _id. Điều này dễ làm một thao tác tưởng là “update” thực tế lại tạo document mới.

Nếu nghiệp vụ yêu cầu “chỉ cập nhật document chắc chắn tồn tại”, hãy dùng câu lệnh update có điều kiện, kiểm tra matchedCount, hoặc chọn cơ chế concurrency/optimistic locking phù hợp thay vì chỉ dựa vào save.

## 7. MongoRepository.insert và MongoRepository.save

Khai báo repository:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, ObjectId> {
}
~~~

Ví dụ dùng insert:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;

public class RepositoryOrderService {
    private final OrderRepository repository;

    public RepositoryOrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public ObjectId create(String orderNumber) {
        OrderDocument entity = new OrderDocument(
            orderNumber,
            Instant.now()
        );

        OrderDocument inserted = repository.insert(entity);
        return inserted.getId();
    }

    public ObjectId save(OrderDocument entity) {
        OrderDocument saved = repository.save(entity);
        return saved.getId();
    }
}
~~~

Trong hai phương thức, ID được lấy qua **getId()** của entity trả về. Repository không trả trực tiếp ObjectId ở cấp phương thức insert/save.

**Điểm cần phân biệt:** MongoRepository.save xác định entity mới hay đã tồn tại dựa trên thông tin entity của Spring Data, bao gồm ID, @Version hoặc giao diện Persistable nếu được sử dụng. Do đó:

- Một entity **id == null** thường được coi là mới.
- Một entity có ID hợp lệ có thể được coi là đã tồn tại, nhưng điều đó không phải bằng chứng database có bản ghi ấy.
- Nếu entity triển khai **Persistable**, kết quả **isNew()** có thể chi phối cách repository chọn đường lưu.
- Khi có **@Version**, quy tắc nhận diện entity mới và kiểm tra cạnh tranh ghi cũng ảnh hưởng cách save hoạt động.

Chọn insert khi ý định là **tạo mới, không ghi đè**. Chọn save khi cần lưu trạng thái entity theo hợp đồng repository, đồng thời hiểu rõ chính sách new/existing và optimistic locking.

## 8. Có thể lấy ID trực tiếp từ entity đầu vào không?

Câu hỏi này phụ thuộc tính **mutable/immutable** của entity và cơ chế mapping.

### 8.1. Entity mutable

~~~java
OrderDocument input = new OrderDocument(
    "ORD-1004",
    Instant.now()
);

OrderDocument output = repository.insert(input);

ObjectId reliableId = output.getId();
~~~

Với một JavaBean mutable, ID thường có thể được gán vào thuộc tính id khi ghi thành công. Nhưng viết mã phụ thuộc vào việc **input.getId()** được đổi tại chỗ khiến code kém bền vững khi chuyển sang record, immutable constructor hoặc converter tùy chỉnh. Luôn dùng **output** để lấy trạng thái kết quả.

### 8.2. Immutable entity / Java record

Spring Data hỗ trợ mô hình immutable, trong đó object không có setter:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record ImmutableOrder(
    @Id ObjectId id,
    String orderNumber,
    Instant createdAt
) {}
~~~

Sử dụng:

~~~java
ImmutableOrder input = new ImmutableOrder(
    null,
    "ORD-1005",
    Instant.now()
);

ImmutableOrder persisted = mongoTemplate.insert(input);
ObjectId id = persisted.id();

// Lấy ID từ persisted; input là record immutable.
~~~

Với immutable entity, Spring Data có thể tạo **một instance mới** phản ánh ID sau khi ghi. Không dùng **input.id()** làm căn cứ xác nhận ID đã lưu. Khi chuyển mã từ mutable class sang record, cách xử lý dựa trên giá trị trả về giúp tránh lỗi khó phát hiện.

### 8.3. Trạng thái entity không chỉ có ID

Nếu entity mang các thuộc tính được Spring Data cập nhật trong lúc ghi, chẳng hạn **@Version**, kết quả trả về cũng nên được giữ lại thay vì chỉ giữ object đầu vào:

~~~java
OrderDocument saved = repository.save(order);
// Dùng saved làm trạng thái mới sau thao tác persistence.
~~~

Không mặc định rằng object đầu vào, object trả về và document trong database luôn có cùng trạng thái vào mọi thời điểm. Callback, converter, default value, concurrent writer và chính sách cập nhật có thể ảnh hưởng dữ liệu.

## 9. ID được sinh tự động hay ứng dụng tự chọn?

### 9.1. ObjectId được sinh khi ID chưa có

Với **@Id ObjectId id** và **id == null**, MongoDB driver hoặc tầng persistence có thể sinh ObjectId cho document mới. Một ObjectId có thể hiển thị thành chuỗi hex:

~~~java
ObjectId generatedId = repository.insert(order).getId();
String hex = generatedId.toHexString();
~~~

**hex** tiện cho HTTP API hoặc log, nhưng BSON ObjectId và Java String vẫn là hai dạng biểu diễn khác nhau. Nếu API nhận lại hex, có thể parse:

~~~java
ObjectId parsed = new ObjectId(hex);
~~~

Hãy kiểm tra định dạng đầu vào và xử lý lỗi nếu client gửi chuỗi không hợp lệ; không để lỗi parse làm ứng dụng trả thông tin nội bộ không cần thiết.

### 9.2. ID dạng String

Spring Data MongoDB hỗ trợ **@Id String id**, nhưng việc chuyển đổi String hợp lệ theo định dạng ObjectId sang BSON ObjectId có thể diễn ra theo quy tắc mapping. Vì vậy cần phân biệt **kiểu Java được trả về** và **kiểu BSON thật sự được lưu**.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class CustomerWithStringId {
    @Id
    private String id;
    private String name;

    // Constructor, getter, setter được lược bỏ.
}
~~~

Với String ID để null, cơ chế sinh ObjectId thường cho phép ứng dụng nhận lại dạng chuỗi hex sau khi mapping. Khi String ID đã được cung cấp, cách lưu thành BSON ObjectId hoặc BSON String cần được kiểm tra theo quy tắc converter.

Nếu mục tiêu là **luôn lưu _id ở kiểu BSON String**, hãy khai báo chính sách rõ bằng **@MongoId**:

~~~java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "external_orders")
public class ExternalOrder {
    @MongoId(FieldType.STRING)
    private String id;
    private String externalReference;

    // Constructor, getter, setter được lược bỏ.
}
~~~

Với ID String nghiệp vụ, **ứng dụng nên tự tạo và gán ID trước khi insert**; không giả định cơ chế sinh ObjectId phù hợp với chính sách BSON String. @MongoId cho phép chỉ định rõ kiểu lưu _id và tránh một số chuyển đổi ngầm của @Id.

### 9.3. ID nghiệp vụ khác với ID kỹ thuật

Một đơn hàng có thể có đồng thời:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  orderNumber: "ORD-1001",
  externalReference: "PAY-9988"
}
~~~

Trong đó:

- **_id** là định danh document ở MongoDB.
- **orderNumber** là số đơn hiển thị cho người dùng.
- **externalReference** là mã tham chiếu sang hệ thống ngoài.

Các trường nghiệp vụ có thể cần unique index riêng nếu phải duy nhất. Chúng không trở thành _id chỉ vì tên giống một mã định danh. Khi thiết kế API, quyết định sẽ trả ID kỹ thuật, ID nghiệp vụ hay cả hai và mô tả ý nghĩa cho client.

### 9.4. ID do ứng dụng tự sinh

Nếu hệ thống cần tạo ID trước khi ghi để gửi trong sự kiện hoặc liên kết với dữ liệu khác, ứng dụng có thể sinh **ObjectId**:

~~~java
ObjectId preassignedId = new ObjectId();

OrderDocument order = new OrderDocument(
    "ORD-1006",
    Instant.now()
);
order.setId(preassignedId);

OrderDocument saved = repository.insert(order);
ObjectId returnedId = saved.getId();
~~~

Trong trường hợp ghi thành công, **returnedId** tương ứng với **preassignedId**. Tuy nhiên, **đã sinh ID không chứng minh insert thành công**: chỉ xem ID là đã được lưu sau khi thao tác persistence hoàn tất thành công.

Với loại ID khác ObjectId, chẳng hạn UUID hoặc mã chuỗi nghiệp vụ, nên quy định cách mã hóa BSON và thuật toán sinh ID ở tầng ứng dụng. Không trông đợi MongoDB tự tạo đúng kiểu ID tùy ý khi chưa gán giá trị.

## 10. Duplicate key: ID đã tồn tại thì sao?

MongoDB không cho phép hai document trong cùng collection có cùng _id. Nếu gọi **insert** với ID đã tồn tại, server sẽ từ chối:

~~~java
ObjectId sameId = new ObjectId();

OrderDocument first = new OrderDocument(
    "ORD-2001", Instant.now()
);
first.setId(sameId);
repository.insert(first); // Thành công nếu chưa có _id này.

OrderDocument second = new OrderDocument(
    "ORD-2002", Instant.now()
);
second.setId(sameId);
repository.insert(second); // Có thể ném DuplicateKeyException.
~~~

Trong ứng dụng Spring Data, lỗi duplicate key thường được chuyển thành **DuplicateKeyException** thuộc Spring DAO hierarchy. Cần xử lý lỗi tại tầng thích hợp, ví dụ API trả trạng thái xung đột và không công bố rằng đã tạo đơn hàng mới.

**Đừng khắc phục duplicate key bằng cách đổi insert thành save một cách máy móc.** Nếu save được chuyển thành replace/upsert cho một ID trùng, dữ liệu cũ có thể bị ghi đè. Đây là thay đổi ngữ nghĩa nghiệp vụ, không phải cách “sửa lỗi sinh ID”.

Khi thao tác thất bại, có thể đối tượng Java đã có ID do ứng dụng cung cấp hoặc do một tầng trung gian đã tạo. ID trên object **không phải bằng chứng ghi thành công**. Cần dựa vào kết quả thao tác, exception, transaction và chính sách write concern.

## 11. ID và trạng thái entity: new, existing, version

ID và trạng thái lưu trữ liên quan nhưng không đồng nhất:

| Tình huống | ID Java | Document có chắc đã tồn tại? | Hành động cần cân nhắc |
| --- | --- | --- | --- |
| Entity mới chưa được ghi | null | Không | insert hoặc save theo hợp đồng. |
| Entity mới được ứng dụng gán ID trước | khác null | Không | insert để bảo đảm không ghi đè. |
| Entity đọc thành công từ database | khác null | Có tại thời điểm đọc | Có thể thay đổi trước khi ghi lại. |
| Entity vừa được insert thành công | khác null | Có tại thời điểm hoàn tất ghi | Dùng ID trả về cho các bước tiếp. |
| Entity vừa save thành công | khác null | Có tại thời điểm hoàn tất ghi | Không có nghĩa document vừa được tạo mới. |

### 11.1. @Version không phải @Id

Spring Data MongoDB hỗ trợ optimistic locking qua **@Version**:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "carts")
public class CartDocument {
    @Id
    private ObjectId id;

    @Version
    private Long revision;

    private String status;

    // Constructor, getter, setter được lược bỏ.
}
~~~

**id** định danh document, còn **revision** dùng phát hiện cập nhật cạnh tranh. Khi save một document đã tồn tại, Spring Data có thể kiểm tra giá trị version và tăng revision nếu cập nhật thành công. **ID vẫn là ID cũ**. Nếu version không khớp do một writer khác vừa cập nhật, thao tác có thể ném **OptimisticLockingFailureException** thay vì ghi đè.

Khi dùng optimistic locking, cần cấu hình write concern phù hợp để biết thao tác được xác nhận; các thao tác ghi ngoài cơ chế version của Spring Data cũng phải được thiết kế nhất quán. Đừng suy rằng mọi lệnh update thô đều tự tăng @Version.

### 11.2. Save không tương đương “update chắc chắn tồn tại”

Nếu nghiệp vụ muốn “chỉ sửa trạng thái đơn hàng hiện hữu”, thay vì dựa vào save với ID tự gán, có thể dùng lệnh update có filter theo ID và kiểm tra kết quả:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

Query query = Query.query(Criteria.where("_id").is(existingId));
Update update = new Update().set("status", "PAID");

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    "orders"
);

boolean matched = result.getMatchedCount() == 1;
~~~

Ở đây, matchedCount cho biết có document phù hợp tại thời điểm cập nhật. Một thao tác update như trên **không trả entity có ID**, vì đó là một API khác với MongoTemplate.insert/save. Nếu yêu cầu optimistic locking, bổ sung điều kiện version và chính sách tăng version phù hợp.

## 12. ID trong reactive access

Với **ReactiveMongoTemplate** hoặc **ReactiveMongoRepository**, thao tác ghi trả về một **Mono<Entity>**. Không đọc ID trước khi luồng ghi hoàn tất:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;
import reactor.core.publisher.Mono;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;

public class ReactiveOrderService {
    private final ReactiveMongoTemplate template;

    public ReactiveOrderService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<ObjectId> create(String orderNumber) {
        OrderDocument draft = new OrderDocument(
            orderNumber,
            Instant.now()
        );

        return template.insert(draft)
            .map(OrderDocument::getId);
    }
}
~~~

Phương thức **create** trả một Mono phát ra ObjectId **sau khi thao tác insert thành công**. Nếu xảy ra lỗi kết nối, duplicate key hoặc validation, Mono phát lỗi và không nên có bước tiếp theo giả định ID đã được lưu.

Với repository reactive:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, ObjectId> {
}

// Trong service:
Mono<ObjectId> idPublisher =
    reactiveRepository.save(order).map(OrderDocument::getId);
~~~

**Không gọi block() trong chuỗi xử lý WebFlux/reactive** để lấy ID đồng bộ; cách đúng là tiếp tục pipeline bằng map, flatMap hoặc các phép biến đổi reactive phù hợp. Khi kết hợp insert với hành động khác, hãy thiết kế lỗi, retry và idempotency. Subscribe lại một publisher ghi dữ liệu có thể kích hoạt thêm thao tác, nên không tự động retry insert khi chưa có chính sách tránh ghi trùng.

## 13. Khi thao tác ở tầng MongoDB Java Driver

MongoTemplate cho phép truy cập driver, nhưng chữ ký API thấp hơn khác Spring Data mapping:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.InsertOneResult;
import org.bson.BsonValue;
import org.bson.Document;

MongoCollection<Document> collection =
    mongoTemplate.getCollection("orders");

Document raw = new Document("orderNumber", "ORD-3001");
InsertOneResult result = collection.insertOne(raw);

BsonValue insertedId = result.getInsertedId();
System.out.println(insertedId);
~~~

**getInsertedId()** ở đây đến từ **InsertOneResult**, không phải phương thức MongoTemplate.insert. Driver có thể sinh _id cho Document đầu vào trước khi gửi lệnh. Tùy write concern và cách sử dụng driver, API kết quả có thể có các giới hạn quan sát cần kiểm tra.

Một ví dụ khác là thao tác **upsert** cấp thấp trả UpdateResult có thể cung cấp **getUpsertedId()** khi một document mới được chèn bởi upsert. Điều này **không có nghĩa** MongoRepository.save trả UpdateResult hoặc luôn cung cấp trường upsertedId.

Không trộn code đọc ID từ **BsonValue** với code đọc ID từ entity Java. Khi sử dụng Spring Data MongoDB ở tầng ứng dụng, ưu tiên entity kết quả của template/repository để giữ nhất quán với converter.

## 14. Gửi ID về HTTP API

Một endpoint tạo đơn hàng thường cần trả về mã định danh cho client. Có thể thiết kế DTO chỉ chứa ID dạng chuỗi:

~~~java
public record CreateOrderResponse(String id) {}
~~~

Ví dụ trong service:

~~~java
public CreateOrderResponse createOrder(String number) {
    OrderDocument draft = new OrderDocument(number, Instant.now());
    OrderDocument inserted = repository.insert(draft);

    return new CreateOrderResponse(
        inserted.getId().toHexString()
    );
}
~~~

Một JSON response minh họa:

~~~json
{
  "id": "507f1f77bcf86cd799439011"
}
~~~

Đây là định dạng biểu diễn ID trong API. **Không nên buộc client biết về lớp ObjectId của Java**. Nếu ID kỹ thuật không nên xuất hiện ra bên ngoài, có thể trả mã public riêng, nhưng phải giữ rõ quan hệ giữa mã đó và _id MongoDB.

Với API tạo tài nguyên, việc trả **201 Created** và đường dẫn tài nguyên trong **Location** là một lựa chọn REST phổ biến khi phù hợp. Việc lập response thành công chỉ nên xảy ra sau khi thao tác ghi đã hoàn tất theo yêu cầu về write concern/transaction của hệ thống.

### 14.1. Khi có transaction

Trong transaction, phương thức insert/save có thể trả entity đã có ID trước khi **transaction commit**. Nếu transaction về sau bị rollback, ID đó không chứng minh document đã tồn tại bền vững trong database. Tách khái niệm **ID đã được cấp** và **transaction đã commit** khi phát sự kiện hoặc trả kết quả cho hệ thống ngoài.

## 15. Kiểm thử vòng đời ID

Kiểm thử nên chạy với MongoDB dành riêng cho test, ví dụ Testcontainers hoặc một instance test kiểm soát được. Mock repository chỉ xác minh cách gọi, không xác nhận được thực tế sinh ObjectId và mapping ID của driver.

Ví dụ tích hợp với Spring Boot/JUnit 5:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.UUID;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class OrderIdIntegrationTest {

    @Autowired
    private OrderRepository repository;

    @Autowired
    private MongoTemplate template;

    @Test
    void insertReturnsEntityWithIdAndCanBeReadById() {
        OrderDocument draft = new OrderDocument(
            "TEST-" + UUID.randomUUID(),
            Instant.now()
        );
        assertThat(draft.getId()).isNull();

        OrderDocument inserted = repository.insert(draft);
        ObjectId id = inserted.getId();

        assertThat(id).isNotNull();
        try {
            OrderDocument found = template.findById(
                id,
                OrderDocument.class
            );
            assertThat(found).isNotNull();
            assertThat(found.getId()).isEqualTo(id);
            assertThat(found.getOrderNumber())
                .isEqualTo(inserted.getOrderNumber());
        } finally {
            repository.deleteById(id);
        }
    }
}
~~~

Test này kiểm tra ba hành vi quan trọng: **ID ban đầu null**, **ID trả về sau insert không null**, và **có thể đọc document bằng chính ID đó**. Cần dùng cấu hình kết nối test riêng và bảo đảm các dữ liệu test không tác động production.

Những tình huống kiểm thử bổ sung:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Insert entity chưa có ID | Entity trả về có ID hợp lệ, tìm được theo ID. |
| Insert entity có ID tự gán | Entity trả về giữ ID đã gán nếu thao tác thành công. |
| Insert ID trùng | Báo duplicate key; không thay đổi document trước. |
| Save entity đã tồn tại | ID vẫn giữ nguyên, dữ liệu cập nhật theo hợp đồng. |
| Save entity có ID tự gán nhưng chưa tồn tại | Hành vi thực tế theo template/repository và chính sách nhận diện new/existing. |
| Insert immutable entity | Lấy ID từ object kết quả, không phụ thuộc object đầu vào đổi tại chỗ. |
| Entity có @Version | Kiểm tra ID giữ nguyên, version thay đổi và xung đột bị phát hiện. |
| ID String/BSON ObjectId | Xác minh kiểu lưu thực tế và khả năng truy vấn sau khi parse ID. |
| Reactive insert thất bại | Publisher phát lỗi, không phát ID như thể đã ghi thành công. |
| Transaction rollback | ID được sinh nhưng document không còn sau rollback thành công. |

## 16. Các lỗi thường gặp khi lấy ID

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| getId() trả null trước insert | Đối tượng mới chưa được cấp ID | Gọi insert/save, lấy entity kết quả sau ghi thành công. |
| Lấy ID từ object đầu vào không chính xác | Immutable entity hoặc mapping trả instance mới | Dùng giá trị trả về của repository/template. |
| Gọi insert với ID có sẵn bị lỗi | Đụng unique index của _id | Xác minh nghiệp vụ và ID; không đổi sang save chỉ để bỏ lỗi. |
| Save trả cùng ID dù dữ liệu thay đổi | ID là danh tính document, không phải số lần cập nhật | Dùng @Version nếu cần quản lý xung đột ghi. |
| API nhận ID dạng String nhưng truy vấn không thấy | Kiểu BSON của _id không đúng với filter | Kiểm tra @Id/@MongoId và chuyển đổi String/ObjectId đúng cách. |
| Có ID nhưng tìm lại không ra | Sai database/collection, transaction rollback hoặc dữ liệu đã xóa | Kiểm tra kết nối, collection, trạng thái transaction và kết quả ghi. |
| Save tạo document ngoài ý muốn | ID đã gán nhưng không có document cũ, thao tác upsert | Dùng update có điều kiện nếu chỉ muốn sửa bản ghi hiện hữu. |
| Reactive code thấy ID null | Đọc trước khi publisher hoàn tất hoặc không subscribe đúng | Lấy ID trong map/flatMap của Mono kết quả. |
| Unit test giả định ID cố định | ObjectId được sinh theo mỗi lần ghi | Kiểm tra ID không null, đúng định dạng và dùng đọc lại dữ liệu. |
| Trường @Version thay đổi sau save | Version quản lý trạng thái ghi, khác ID | Dùng entity trả về để tiếp tục với phiên bản mới nhất. |

### 16.1. Kiểm tra bằng mongosh

Ví dụ xem field _id trong collection:

~~~javascript
db.orders.find(
  { orderNumber: "ORD-1001" },
  { _id: 1, orderNumber: 1 }
);
~~~

Để xác định kiểu BSON của _id:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      orderNumber: 1,
      idType: { $type: "$_id" }
    }
  }
]);
~~~

Với ObjectId, **idType** thường là **objectId**; với ID String, kết quả là **string**. Nhìn chuỗi được in ra mà không kiểm tra kiểu BSON là chưa đủ để chẩn đoán lỗi mapping ID.

## 17. Thực hành tự kiểm tra

### Bài tập 1: Entity trả về mang ID nào?

~~~java
OrderDocument draft = new OrderDocument(
    "ORD-4001", Instant.now()
);
OrderDocument saved = repository.insert(draft);
ObjectId id = saved.getId();
~~~

**Câu hỏi:** phương thức insert trả ObjectId trực tiếp hay OrderDocument? Có nên kiểm tra draft.getId() để xác nhận giá trị hay không?

**Đáp án:** repository.insert trả **OrderDocument**; gọi **saved.getId()** để lấy ID. Với mutable entity, draft có thể cũng đã được gán ID, nhưng cách viết đáng tin cậy và tương thích với immutable entity là dùng **saved**.

### Bài tập 2: Ghi trùng ID

Hai entity mới được gán cùng một ObjectId và gọi repository.insert lần lượt. Điều gì xảy ra?

**Đáp án:** insert thứ hai bị từ chối do trùng _id trong cùng collection nếu insert thứ nhất đã thành công và còn tồn tại. Nên xử lý lỗi duplicate key theo nghiệp vụ. Chuyển ngay sang save có thể làm thay đổi bản ghi cũ nên không phải phương án an toàn mặc định.

### Bài tập 3: Save ID đã tồn tại

Một document có ID **X** và trạng thái PENDING. Sau khi cập nhật thành PAID rồi save thành công, ID có thành **Y** không?

**Đáp án:** không. ID vẫn là **X** vì đó là danh tính document. Nếu cần biết bản ghi đã được cập nhật mấy lần hoặc phát hiện xung đột, dùng version hoặc metadata thích hợp.

### Bài tập 4: Reactive insert

Viết cách trả **Mono<String>** chứa ID hex sau khi insert OrderDocument:

~~~java
Mono<String> idHex =
    reactiveTemplate.insert(order)
        .map(saved -> saved.getId().toHexString());
~~~

**Giải thích:** mã chuyển ID nằm **sau insert** trong reactive pipeline. Nếu insert lỗi, pipeline không phát ID thành công.

### Bài tập 5: ID String và BSON ObjectId

Ứng dụng dùng @Id String id, client gửi chuỗi hex có 24 ký tự nhưng câu lệnh truy vấn bằng driver thô không tìm thấy document. Bạn cần kiểm tra gì?

**Gợi ý:** xác minh _id được lưu ở BSON **objectId** hay **string**, kiểm tra mapper @Id/@MongoId và cách driver tạo filter. Chuỗi hex của ObjectId không tự trở thành BSON ObjectId khi dùng driver thô.

### Bài tập 6: Transaction đã rollback

Một thao tác insert trong transaction trả entity có ID, nhưng transaction bị rollback vì bước tiếp theo thất bại. Có được trả API thành công với ID đó không?

**Đáp án:** không. ID đã được cấp không đồng nghĩa transaction đã commit. Chỉ công bố tạo tài nguyên thành công khi transaction và các điều kiện ghi bắt buộc đã hoàn tất.

## 18. Nguyên tắc cần nhớ

1. **_id là khóa định danh của document** trong MongoDB; thuộc tính Java mang @Id thường ánh xạ với _id.
2. **MongoTemplate.insert/save và MongoRepository.insert/save trả entity**, vì vậy lấy ID từ **entity kết quả**.
3. **Insert dùng cho ý định tạo mới**; save có ngữ nghĩa lưu trạng thái và có thể chạm vào document đã có ID.
4. **Có ID không đồng nghĩa document đã được ghi thành công**, nhất là khi ID do ứng dụng cấp, có exception hoặc transaction rollback.
5. **Dùng @MongoId khi cần kiểm soát rõ kiểu BSON của ID**, đặc biệt với ID String.
6. **Immutable entity cần giữ lại đối tượng trả về**; reactive access cần lấy ID sau khi Mono phát entity thành công.
7. **ID và @Version là hai khái niệm khác nhau**: ID giữ danh tính, version hỗ trợ kiểm soát cạnh tranh cập nhật.
8. **Kiểm thử bằng MongoDB thật** để xác nhận việc sinh ID, loại BSON, đường đọc lại và lỗi duplicate key.

Hiểu chính xác **giá trị ID trả về sau insert hoặc save** giúp ứng dụng **SPRING_DATA_MONGODB** xây dựng luồng tạo dữ liệu an toàn, trả định danh đúng cho API và duy trì trạng thái nhất quán khi sử dụng MongoTemplate, repository hoặc reactive access.
