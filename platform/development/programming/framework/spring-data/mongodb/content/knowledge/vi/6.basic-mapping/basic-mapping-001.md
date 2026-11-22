# Đánh dấu entity bằng @Document và chọn tên collection

## 1. Bối cảnh và mục tiêu

MongoDB tổ chức dữ liệu theo **database → collection → document**. Collection chứa các document BSON; mỗi document thường biểu diễn một thực thể hoặc một nhóm dữ liệu có vòng đời chung trong nghiệp vụ. Khi viết ứng dụng Java, Spring Data MongoDB ánh xạ đối tượng Java thành BSON để lưu và đọc dữ liệu.

Annotation **@Document** thuộc Spring Data MongoDB dùng để khai báo một lớp là kiểu document gốc và, khi cần, gắn lớp đó với **tên collection** cụ thể. Trong module **SPRING_DATA_MONGODB**, đây là nền tảng để kết nối, ánh xạ và thao tác MongoDB bằng **MongoTemplate** hoặc **repository**. Việc chọn collection còn liên quan đến thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.

Sau bài này, bạn có thể:

1. Khai báo một entity bằng annotation @Document, @Id và các field Java.
2. Phân biệt tên lớp Java, tên collection và tên database.
3. Hiểu tên collection mặc định, cách chọn tên tường minh và rủi ro khi đổi tên class.
4. Truy cập cùng collection bằng MongoRepository và MongoTemplate.
5. Quyết định ranh giới collection theo yêu cầu nghiệp vụ, truy vấn và vận hành.
6. Kiểm tra collection thực tế và xử lý các lỗi đọc/ghi sai đích.

## 2. Quan hệ giữa entity Java và document MongoDB

Hãy xét một đơn hàng có số đơn, tên người mua và thời gian tạo. Đối tượng Java biểu diễn đơn hàng sẽ được chuyển thành BSON khi lưu:

~~~mermaid
flowchart LR
    A["OrderDocument (Java)"] --> B["MappingMongoConverter"]
    B --> C["BSON document"]
    C --> D["Database shop"]
    D --> E["Collection orders"]
~~~

Một document tương ứng được nhìn thấy trong **mongosh** có thể như sau:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  orderNumber: "ORD-1001",
  customerName: "Lan",
  createdAt: ISODate("2025-05-20T09:00:00Z")
}
~~~

Những yếu tố khác nhau cần phân biệt:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Lớp Java | OrderDocument | Mô hình để lập trình và áp dụng mapping. |
| Database | shop | Không gian chứa nhiều collection, thường do cấu hình kết nối quyết định. |
| Collection | orders | Tập hợp document cùng phạm vi lưu trữ. |
| Document BSON | Bản ghi ORD-1001 | Dữ liệu thực tế, có khóa định danh _id. |
| Thuộc tính Java | orderNumber | Có thể ánh xạ thành field BSON cùng tên hoặc tên được tùy chỉnh. |

Tài liệu dùng từ **entity** để chỉ đối tượng thuộc mô hình lưu trữ MongoDB. Đây không phải entity JPA theo nghĩa bảng quan hệ. Annotation @Document không tạo khóa ngoại hay phép join SQL, đồng thời không quyết định một field sẽ được nhúng hay tham chiếu chỉ qua việc đánh dấu class.

## 3. Cú pháp của @Document

Annotation được import từ package của Spring Data MongoDB:

~~~java
import org.springframework.data.mongodb.core.mapping.Document;
~~~

Ví dụ tối giản:

~~~java
@Document
public class ProductDocument {
    // Các field, constructor và getter/setter.
}
~~~

Trong nhiều trường hợp, Spring Data MongoDB vẫn có thể mapping một kiểu Java chưa gắn @Document khi thao tác qua MongoTemplate; tuy nhiên, **khai báo @Document tường minh** cho document gốc giúp thể hiện ý định và tránh sự phụ thuộc khó nhận biết vào quy tắc tên mặc định.

### 3.1. Chọn collection bằng thuộc tính collection

~~~java
@Document(collection = "products")
public class ProductDocument {
    // Lưu trong collection products.
}
~~~

Giá trị **products** là tên collection, không phải tên database. Một cách viết tương đương qua alias của annotation là:

~~~java
@Document(value = "products")
public class ProductDocument {
}
~~~

Trong tài liệu và mã dự án, cách viết **collection = "products"** thường rõ ý nghĩa hơn. Đặt tên tường minh còn giúp thay đổi tên class Java mà vẫn giữ nguyên địa chỉ lưu dữ liệu.

### 3.2. Tên mặc định khi không khai báo

Khi không ghi tên collection, quy tắc mặc định thông dụng của Spring Data MongoDB là lấy tên đơn giản của class và viết thường chữ cái đầu:

| Class Java | Collection mặc định thường gặp | Tên nếu khai báo rõ |
| --- | --- | --- |
| Customer | customer | customers |
| OrderDocument | orderDocument | orders |
| ProductCatalog | productCatalog | product_catalog |

Đây là hành vi của tầng mapping và có thể bị ảnh hưởng bởi cấu hình quy ước tên. Trong dự án cần lưu dữ liệu lâu dài, hãy kiểm tra tên được framework thực sự chọn bằng API và **khai báo collection rõ ràng** để ổn định.

Một lỗi nguy hiểm là đổi class **Order** thành **CustomerOrder** khi chưa khai báo collection. Các thao tác có thể chuyển từ collection mặc định **order** sang **customerOrder**. Dữ liệu cũ vẫn còn tại collection trước, nhưng ứng dụng mới có thể đọc thấy collection mới rỗng.

### 3.3. Annotation không phải lệnh tạo collection

Khai báo @Document không tự động tạo collection khi chỉ tải class Java. Một collection có thể được MongoDB tạo khi thực hiện lần ghi đầu tiên nếu cấu hình và quyền cho phép; ứng dụng cũng có thể chủ động tạo collection.

Tương tự, @Document **không tự tạo index, validator, quyền truy cập hoặc di chuyển dữ liệu**. Những cấu hình đó có vòng đời quản lý riêng.

## 4. Ví dụ entity hoàn chỉnh: OrderDocument

Ví dụ sau chọn một kiểu ID rõ ràng là **ObjectId**. Nếu ID Java dùng String, Spring Data có các quy tắc chuyển đổi riêng khi mapping tới trường _id; cách chọn ObjectId dưới đây giúp người mới tập trung vào collection.

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
    private String customerName;
    private Instant createdAt;

    public OrderDocument() {
    }

    public OrderDocument(String orderNumber, String customerName,
                         Instant createdAt) {
        this.orderNumber = orderNumber;
        this.customerName = customerName;
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

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
}
~~~

Giải thích:

- **@Document(collection = "orders")** chỉ định collection của document gốc.
- **@Id** đánh dấu thuộc tính được ánh xạ với trường BSON **_id**; nó không đặt tên collection.
- ID ban đầu có thể để null khi tạo đối tượng mới; khi insert, MongoDB/driver có thể tạo ObjectId cho document.
- **Instant** thường được ánh xạ sang BSON Date; thời điểm không chứa tên múi giờ.
- Các thuộc tính Java không có annotation @Field thường được lưu theo tên thuộc tính.
- Spring Data có thể ghi metadata **_class** vào BSON theo cấu hình type mapper mặc định. Đây là thông tin phục vụ mapping kiểu Java, không phải tên collection hoặc phiên bản schema nghiệp vụ.

Trong mô hình production, cần bổ sung validation ở đầu vào, bất biến nghiệp vụ và các quy tắc định danh. Những trách nhiệm đó không được giải quyết chỉ bằng @Document.

## 5. Database do cấu hình kết nối quyết định

Ví dụ cấu hình Spring Boot với MongoDB chạy ở môi trường phát triển:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017/shop
~~~

**shop** là database trong URI, còn **orders** là collection từ @Document. Cấu trúc tương ứng:

~~~text
MongoDB server
└── shop                         # database do kết nối chọn
    ├── orders                   # collection từ @Document
    │   ├── document ORD-1001
    │   └── document ORD-1002
    └── customers
~~~

Một lớp OrderDocument mang cùng annotation có thể được ghi vào các database khác nhau nếu các MongoTemplate được cấu hình trỏ tới những database khác nhau. Annotation chọn **collection bên trong database đang sử dụng**, không khóa class vào một database toàn cục.

Vì vậy, khi gặp lỗi “dữ liệu biến mất”, cần kiểm tra **cả database và collection**, đặc biệt sau khi đổi profile môi trường, connection URI hoặc MongoTemplate.

## 6. Sử dụng MongoRepository

Spring Data tạo repository dựa trên kiểu document và kiểu khóa định danh:

~~~java
package com.example.orders;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, ObjectId> {

    OrderDocument findFirstByOrderNumber(String orderNumber);
}
~~~

Repository dùng metadata của **OrderDocument** để xác định collection **orders**. Một service có thể tạo và tra cứu đơn hàng:

~~~java
import java.time.Instant;

public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderDocument create(String number, String customer) {
        OrderDocument order = new OrderDocument(
            number,
            customer,
            Instant.now()
        );
        return repository.save(order);
    }

    public OrderDocument findByNumber(String number) {
        return repository.findFirstByOrderNumber(number);
    }
}
~~~

Lưu ý **findFirstByOrderNumber** trả về một bản ghi nếu có nhiều bản trùng. Nếu nghiệp vụ yêu cầu số đơn duy nhất, cần **unique index thật trên collection orders**; tên phương thức repository không tự tạo ràng buộc duy nhất.

## 7. Sử dụng MongoTemplate

MongoTemplate cũng có thể xác định collection theo cùng lớp:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderQueryService {
    private final MongoTemplate template;

    public OrderQueryService(MongoTemplate template) {
        this.template = template;
    }

    public OrderDocument findById(ObjectId id) {
        return template.findById(id, OrderDocument.class);
    }

    public OrderDocument findByNumber(String number) {
        Query query = Query.query(
            Criteria.where("orderNumber").is(number)
        );
        return template.findOne(query, OrderDocument.class);
    }

    public OrderDocument insert(OrderDocument order) {
        return template.insert(order);
    }
}
~~~

Các method này truy cập **orders** bởi vì chúng nhận kiểu OrderDocument hoặc một thể hiện của kiểu đó. Cùng database và cùng metadata mapping, MongoRepository và MongoTemplate có thể đọc ghi nhất quán trên cùng collection.

Tuy nhiên, MongoTemplate có các overload cho phép **chỉ định tên collection riêng từng thao tác**:

~~~java
template.insert(order, "archived_orders");

// Sau thao tác trên, lệnh này vẫn đọc collection "orders":
OrderDocument found = template.findById(order.getId(), OrderDocument.class);
~~~

Đoạn ví dụ minh họa một lỗi thường gặp: document được ghi vào **archived_orders**, nhưng lệnh findById tự chọn **orders** theo annotation nên có thể trả null. Nếu dùng collection khác có chủ đích, phải đồng bộ tên ở tất cả đường ghi, đọc, cập nhật, xóa và tạo index.

**Quy tắc thực hành:** không sử dụng tên collection dưới dạng chuỗi rải rác trong code khi metadata entity đã mô tả đúng collection của nghiệp vụ. Nếu buộc override, đặt logic chọn tên tại một điểm dễ kiểm tra.

## 8. Quy ước đặt tên collection

Tên collection là một phần của hợp đồng lưu trữ lâu dài. Không có yêu cầu mọi dự án phải dùng số ít hay số nhiều; điều quan trọng là có **một quy ước nhất quán**.

| Nguyên tắc | Ví dụ phù hợp | Lý do |
| --- | --- | --- |
| Thể hiện tập hợp nghiệp vụ | orders, customers, products | Dễ hiểu nội dung collection. |
| Giữ tên ổn định | @Document(collection = "orders") | Đổi tên class không đổi nơi lưu dữ liệu. |
| Dùng chữ thường, ký tự dễ thao tác | order_events, inventory_movements | Dễ dùng trong script, monitoring và query. |
| Tránh chữ viết tắt khó hiểu | order_events thay cho oe2 | Dễ bảo trì lâu dài. |
| Không tạo collection theo input tùy ý | Giới hạn tên bằng cấu hình đáng tin cậy | Tránh số collection tăng không kiểm soát. |
| Tuân thủ quy tắc namespace MongoDB | Tránh tên dành riêng như system.* | Không xung đột với thành phần nội bộ. |

Nếu nhóm chọn snake_case và tên số nhiều, có thể quy định:

~~~text
customers
orders
order_events
products
product_categories
inventory_movements
~~~

Tránh đổi tên collection chỉ vì muốn làm đẹp tên class. Thay đổi tên class có thể là refactor mã nguồn; thay đổi tên collection là **thay đổi cơ sở dữ liệu và hành vi truy xuất**, cần kế hoạch tương ứng.

## 9. Chọn ranh giới collection theo mô hình document

Không nên quyết định “mỗi class Java tương ứng một collection”. Ranh giới collection phải dựa vào **dữ liệu được truy cập và cập nhật cùng nhau**, kích thước document, vòng đời và nhu cầu lập index.

### 9.1. Nhúng dữ liệu khi thuộc cùng aggregate

Một đơn hàng với vài dòng sản phẩm có thể lưu trong cùng document:

~~~javascript
{
  orderNumber: "ORD-1001",
  customerName: "Lan",
  items: [
    { sku: "BOOK-01", quantity: NumberInt(2) },
    { sku: "PEN-03", quantity: NumberInt(1) }
  ],
  createdAt: ISODate("2025-05-20T09:00:00Z")
}
~~~

**items** là mảng embedded documents nằm bên trong collection **orders**. Trong Java có thể tạo lớp **OrderItem** để ánh xạ các phần tử này mà không cần đánh dấu mỗi phần tử thành một document gốc hay tạo collection riêng.

Nhúng giúp đọc và cập nhật dữ liệu cùng aggregate bằng một document, nhưng cần lưu ý giới hạn kích thước document của MongoDB và nguy cơ mảng tăng quá lớn.

### 9.2. Tách collection khi vòng đời khác biệt

Ví dụ:

- **orders** lưu trạng thái hiện tại của đơn hàng.
- **order_events** lưu các sự kiện thay đổi trạng thái với số lượng có thể tăng lâu dài.
- **customers** lưu thông tin khách hàng có vòng đời độc lập với từng đơn hàng.

Cách tách này có thể phù hợp khi mỗi nhóm cần retention, index, quyền truy cập, truy vấn hoặc tần suất ghi khác nhau. Khi tách ra nhiều collection, ứng dụng phải xử lý quan hệ và tính nhất quán giữa các document. Giao dịch nhiều document chỉ nên sử dụng khi thật sự có bất biến nghiệp vụ cần bảo vệ; nó không tự phát sinh từ @Document.

### 9.3. Collection theo tenant hoặc theo năm

Đặt tên như **orders_2025** hoặc **orders_tenant_17** có thể phục vụ một thiết kế đặc thù, nhưng mang thêm chi phí:

1. Mỗi collection có index và cấu hình validation riêng cần bảo trì.
2. Các truy vấn xuyên năm hoặc xuyên tenant phức tạp hơn.
3. Repository với @Document thông thường mặc định có tên collection theo metadata entity.
4. Số lượng collection có thể tăng rất nhanh khi tenant hoặc phân vùng tăng.

Hãy cân nhắc **tenantId** trong cùng collection với index phù hợp, hoặc database riêng theo tenant nếu cần cách ly, trước khi chọn tạo một collection cho mỗi tenant. Nếu dùng collection động qua MongoTemplate, cần kiểm soát tên hợp lệ và thống nhất giữa tất cả thao tác.

## 10. @Document và các annotation ánh xạ khác

Đánh dấu @Document chỉ là một phần trong cơ chế ánh xạ:

| Annotation | Vai trò | Có chọn lại collection không? |
| --- | --- | --- |
| @Document(collection = "orders") | Xác định tên collection cho document gốc | Có. |
| @Id | Mapping thuộc tính định danh thành _id | Không. |
| @Field("customer_name") | Đổi tên field BSON được lưu | Không. |
| @Transient | Không persist field qua mapping | Không. |
| @Version | Hỗ trợ optimistic locking của Spring Data | Không. |
| @Indexed | Khai báo metadata index của field | Không. |
| @TypeAlias | Tùy chỉnh alias cho metadata kiểu | Không. |

Ví dụ field Java vẫn tên **customerName** nhưng trường BSON được ghi với tên **customer_name**:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "orders")
public class OrderSummary {
    @Id
    private ObjectId id;

    @Field("customer_name")
    private String customerName;

    // Constructor và accessor được lược bỏ.
}
~~~

Collection của OrderSummary vẫn là **orders**. Annotation @Field chỉ thay đổi tên field; nó không làm xuất hiện collection **customer_name**.

Không dùng annotation **@Table** của JPA để chỉ định collection MongoDB. Cơ chế ORM quan hệ và cơ chế document mapping có metadata riêng.

## 11. Tạo collection và index

### 11.1. Tạo collection có chủ đích

MongoTemplate có API kiểm tra và tạo collection theo metadata entity:

~~~java
if (!mongoTemplate.collectionExists(OrderDocument.class)) {
    mongoTemplate.createCollection(OrderDocument.class);
}
~~~

Đây là ví dụ trong một ngữ cảnh kiểm soát được; nếu nhiều instance đồng thời khởi động, hai instance có thể cùng kiểm tra và cùng thử tạo. Trong production nên có cơ chế provisioning/migration nhất quán và xử lý tình huống collection đã tồn tại.

Với collection cần cấu hình đặc biệt như validation hoặc một kiểu collection chuyên biệt, chỉ ghi @Document không đủ để áp dụng các tùy chọn đó.

### 11.2. Index là cấu hình riêng

Ví dụ orderNumber phải duy nhất. Có thể khai báo:

~~~java
import org.springframework.data.mongodb.core.index.Indexed;

@Indexed(unique = true)
private String orderNumber;
~~~

Nhưng **@Indexed không chứng minh index đã được tạo trên MongoDB**. Việc tạo index tự động phụ thuộc vào cấu hình Spring Data; nhiều hệ thống quản lý index qua migration. Có thể tạo index tường minh bằng MongoTemplate:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;

mongoTemplate.indexOps(OrderDocument.class).ensureIndex(
    new Index().on("orderNumber", Sort.Direction.ASC).unique()
);
~~~

Trong ví dụ, **indexOps(OrderDocument.class)** chọn collection **orders** theo metadata. Nếu collection đã có các số đơn trùng nhau, việc tạo unique index có thể thất bại; trước khi bật ràng buộc phải kiểm tra dữ liệu thực tế.

### 11.3. Collection validation là một cơ chế khác

MongoDB có thể dùng **$jsonSchema** để yêu cầu các field có kiểu BSON phù hợp. Ví dụ tạo một collection minh họa riêng:

~~~javascript
db.createCollection("orders_validated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderNumber", "createdAt"],
      properties: {
        orderNumber: { bsonType: "string" },
        createdAt: { bsonType: "date" }
      }
    }
  }
});
~~~

Validator trong ví dụ chỉ áp dụng cho **orders_validated**. Nếu entity OrderDocument dùng **orders**, collection đó phải được cấu hình validation riêng. Chọn tên collection, tạo index và đặt schema validation là **ba quyết định độc lập**.

## 12. Kiểm tra tên collection ở runtime

MongoTemplate cung cấp API để xác nhận mapping thực tế:

~~~java
String name = mongoTemplate.getCollectionName(OrderDocument.class);
boolean exists = mongoTemplate.collectionExists(OrderDocument.class);

System.out.println(name);   // orders
System.out.println(exists); // true nếu collection đã tồn tại.
~~~

Phương thức **getCollectionName** trả tên collection theo metadata mapping; **collectionExists** kiểm tra sự tồn tại. Chúng không bảo đảm collection đã chứa document.

Với mongosh, hãy xác nhận database và collection trước khi phân tích dữ liệu:

~~~javascript
db.getName();                  // Database đang chọn.
db.getCollectionNames();       // Danh sách collection.
db.orders.findOne();           // Một document ví dụ, nếu có.
db.orders.countDocuments({});  // Số document.
db.orders.getIndexes();        // Index thực tế.
~~~

Trong quá trình kiểm thử hoặc chẩn đoán, có thể đối chiếu tên collection Spring Data báo với danh sách collection MongoDB thật sự đang có. Nếu dữ liệu không xuất hiện, kiểm tra đồng thời URI, database, tên collection, filter truy vấn và quyền của account MongoDB.

## 13. Đổi tên collection khi ứng dụng đã có dữ liệu

Xét phiên bản cũ:

~~~java
@Document(collection = "order")
public class OrderDocument {
}
~~~

Sau đó code được sửa thành:

~~~java
@Document(collection = "orders")
public class OrderDocument {
}
~~~

Thay đổi trên **không di chuyển document** từ collection **order** sang **orders**. API mới có thể trả về danh sách trống trong khi toàn bộ bản ghi cũ vẫn nằm ở collection cũ.

Đổi tên collection cần xử lý như một migration có kế hoạch:

1. Kiểm tra mọi reader, writer, job, report và dịch vụ phụ thuộc tên cũ.
2. Kiểm kê document, index, validator, quyền và các thao tác quản trị đang sử dụng collection.
3. Chọn phương án chuyển dữ liệu hoặc thao tác renameCollection phù hợp với điều kiện triển khai.
4. Xử lý các instance cũ và mới đang chạy đồng thời để tránh ghi vào hai collection khác nhau.
5. Đối soát dữ liệu và kiểm tra mọi truy vấn cùng index sau chuyển đổi.
6. Giữ khả năng rollback theo chính sách trước khi ngừng hoàn toàn đường truy cập tên cũ.

MongoDB có thao tác **renameCollection**, nhưng việc sử dụng phải phù hợp với khả năng server, quyền truy cập và tác động tới ứng dụng. Trong hệ thống đang có ghi liên tục, không nên đổi tên theo một lệnh tùy tiện mà chưa xác định thời điểm chuyển đổi và các consumer liên quan.

Nếu chỉ đổi tên class Java, giữ nguyên **@Document(collection = "orders")** thường tránh được thay đổi đích lưu trữ. Tuy nhiên, nếu đang sử dụng metadata kiểu **_class**, vẫn cần xét khả năng đọc lại document đã ghi bằng tên class cũ.

## 14. Những lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Insert thành công nhưng truy vấn không thấy | Đã override collection khi insert | Kiểm tra overload template và tên đích ở cả read/write. |
| Đổi tên class xong danh sách rỗng | Tên collection bị suy ra từ class | Khai báo tên tường minh, lập kế hoạch dữ liệu cũ. |
| Xuất hiện collection không mong muốn | Gõ nhầm tên collection | Kiểm tra mapping và dữ liệu đã ghi trước khi sửa. |
| Repository và MongoTemplate trả kết quả khác nhau | Khác database, collection hoặc query | Xác nhận URI, getCollectionName và điều kiện truy vấn. |
| Không có unique constraint dù đánh dấu @Indexed | Index chưa được tạo trên MongoDB | Kiểm tra getIndexes, chạy quy trình index phù hợp. |
| Dữ liệu field có tên lạ | Có @Field hoặc custom mapping | Đọc BSON thực tế và kiểm tra metadata. |
| Đọc ID không khớp | Khác kiểu BSON ObjectId/String | Kiểm tra kiểu _id và cách ánh xạ @Id. |
| Lớp nested không có collection | Object đang được nhúng | Xem lại quyết định embedded/reference và ranh giới aggregate. |

Khi cần đánh giá hiệu năng, **đừng suy rằng tên collection đẹp giúp truy vấn nhanh**. Hãy xem index, kích thước document, mẫu query và kết quả **explain("executionStats")**. Ranh giới collection ảnh hưởng thiết kế index và truy vấn; tên tự nó không thay thế công việc tối ưu.

## 15. Kiểm thử ánh xạ collection

Một bài kiểm thử tích hợp có ích sẽ kiểm tra cả metadata và thao tác round trip. Ví dụ dưới đây dùng JUnit 5 và Spring Boot Test, với repository và MongoTemplate được cấu hình kết nối tới **database test**:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class OrderMappingTest {

    @Autowired
    private MongoTemplate mongoTemplate;

    @Autowired
    private OrderRepository repository;

    @Test
    void repositoryAndTemplateUseSameCollection() {
        assertThat(mongoTemplate.getCollectionName(OrderDocument.class))
            .isEqualTo("orders");

        OrderDocument saved = repository.save(new OrderDocument(
            "TEST-" + UUID.randomUUID(),
            "Lan",
            Instant.parse("2025-05-20T09:00:00Z")
        ));

        try {
            OrderDocument loaded = mongoTemplate.findById(
                saved.getId(),
                OrderDocument.class
            );
            assertThat(loaded).isNotNull();
            assertThat(loaded.getOrderNumber())
                .isEqualTo(saved.getOrderNumber());
        } finally {
            repository.deleteById(saved.getId());
        }
    }
}
~~~

Bài kiểm thử không nên chạy trên production; cấu hình datasource/URI dành cho test là điều kiện bắt buộc. Kiểm thử này xác minh repository và MongoTemplate đọc ghi cùng collection trong cùng database; nó chưa thay thế các kiểm thử về unique index, validation hoặc quyền truy cập.

## 16. Liên hệ với aggregation và reactive access

Collection mapping của @Document được Spring Data sử dụng trong nhiều API:

- **MongoTemplate.find** và **MongoTemplate.aggregate** có overload nhận class để suy collection đầu vào.
- **MongoRepository** dùng metadata document khi tạo truy vấn.
- **MongoTemplate.indexOps(OrderDocument.class)** chọn collection để quản lý index.
- **ReactiveMongoTemplate** và **ReactiveMongoRepository** vẫn dùng metadata collection tương ứng, nhưng truy cập bất đồng bộ qua các publisher reactive.

Ví dụ aggregation nhóm số đơn theo khách hàng:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;

Aggregation aggregation = Aggregation.newAggregation(
    Aggregation.group("customerName").count().as("orders")
);

AggregationResults<Document> result = mongoTemplate.aggregate(
    aggregation,
    OrderDocument.class,
    Document.class
);
~~~

Đối số **OrderDocument.class** xác định collection **orders** qua mapping. Một overload nhận chuỗi tên collection sẽ dùng đúng chuỗi được truyền, nên cần nhất quán với cấu hình tên khi dùng các API khác nhau.

Ví dụ repository reactive:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, ObjectId> {
}
~~~

Reactive access thay đổi cách thực thi, hủy và backpressure của luồng truy cập dữ liệu, **không thay đổi ý nghĩa của @Document(collection = "orders")**.

## 17. Bài tập thực hành

### Bài tập 1: chọn collection

Cho ba lớp:

~~~java
@Document
class Customer {}

@Document(collection = "purchase_orders")
class PurchaseOrder {}

@Document(collection = "product_catalog")
class Catalog {}
~~~

**Câu hỏi:** class nào có collection tường minh? Nếu đổi PurchaseOrder thành OrderAggregate nhưng vẫn giữ annotation, tên collection thay đổi không?

**Gợi ý đáp án:** PurchaseOrder và Catalog có tên tường minh. Customer theo tên mặc định, thường là customer. Đổi tên class PurchaseOrder không đổi collection **purchase_orders** khi giữ nguyên annotation. Cần kiểm tra type metadata nếu đã có document chứa thông tin class cũ.

### Bài tập 2: tìm lỗi đọc/ghi khác collection

~~~java
@Document(collection = "orders")
class OrderDocument { /* ... */ }

mongoTemplate.insert(order, "archived_orders");
OrderDocument found =
    mongoTemplate.findById(order.getId(), OrderDocument.class);
~~~

**Câu hỏi:** tại sao found có thể là null?

**Gợi ý đáp án:** Lệnh insert dùng collection **archived_orders**, nhưng lệnh findById dùng metadata class để đọc **orders**. Phải sử dụng cùng database và đúng collection khi muốn đọc lại bản ghi vừa ghi.

### Bài tập 3: nhúng hay tách collection?

Một đơn hàng có 5 dòng sản phẩm và lịch sử thay đổi trạng thái tăng hàng nghìn bản ghi. Bạn sẽ tạo những collection nào?

**Gợi ý đáp án:** có thể giữ các dòng hàng nhỏ cùng document orders, và tách dòng lịch sử dài thành order_events nếu yêu cầu truy vấn/retention độc lập. Cần xác định index, quan hệ và tính nhất quán khi ghi giữa hai collection.

### Bài tập 4: kiểm tra lỗi sau triển khai

Trước khi deploy, code dùng class Order không có @Document(collection). Sau deploy, đổi class thành CustomerOrder và API tìm đơn trả rỗng. Hãy trình bày cách điều tra.

**Gợi ý đáp án:** xem getCollectionName của mapping cũ/mới, xác nhận database, liệt kê collection thực tế, đối chiếu dữ liệu và truy vấn. Khôi phục cấu hình collection ổn định hoặc có migration được lên kế hoạch, tránh xóa collection cũ trước khi xác minh dữ liệu.

### Bài tập 5: khác biệt giữa annotation và index thật

~~~java
@Document(collection = "customers")
class CustomerDocument {
    @Id ObjectId id;
    @Indexed(unique = true) String email;
}
~~~

**Câu hỏi:** tên collection và điều kiện nào mới giúp bảo đảm email duy nhất?

**Đáp án:** tên collection là **customers** trong database hiện tại. Chỉ annotation chưa đủ chứng minh có unique index; cần xác nhận index đã được tạo thành công trên MongoDB, dữ liệu không xung đột và tất cả writer ghi đúng collection này.

## 18. Nguyên tắc cần ghi nhớ

1. **@Document** là điểm khai báo document gốc và tên collection; **@Id** khai báo định danh document.
2. **Database do kết nối/template quyết định**; collection do mapping entity hoặc tên được truyền vào API quyết định.
3. **Khai báo tên collection tường minh** để refactor class không vô tình đổi đích lưu dữ liệu.
4. **Repository và MongoTemplate có thể dùng cùng mapping**, nhưng overload nhận tên collection có thể thay đổi đích một cách cục bộ.
5. **Ranh giới collection phải xuất phát từ mô hình nghiệp vụ và truy vấn**, không phải số class Java.
6. **Index, validation và di chuyển dữ liệu được quản lý riêng**. Annotation không tự thay thế các bước vận hành này.

Nắm chắc việc đánh dấu entity bằng @Document và chọn tên collection giúp bạn xây nền tảng ánh xạ ổn định trong **SPRING_DATA_MONGODB**, trước khi phát triển truy vấn, aggregation, index, transaction, reactive access và các phần xử lý dữ liệu nâng cao.
