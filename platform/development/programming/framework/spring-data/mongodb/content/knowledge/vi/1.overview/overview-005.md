# So sánh mô hình tài liệu với mô hình quan hệ và key-value

## 1. Vì sao cần phân biệt ba mô hình dữ liệu?

Khi xây dựng ứng dụng, lựa chọn cách **tổ chức dữ liệu** ảnh hưởng trực tiếp đến cách đọc, ghi, kiểm soát tính nhất quán, mở rộng hệ thống và bảo trì về sau. Ba mô hình thường gặp là:

- **Quan hệ (relational):** dữ liệu nằm trong các bảng gồm hàng và cột; các bảng liên hệ với nhau bằng khóa, thường truy vấn bằng SQL. PostgreSQL và MySQL là những ví dụ quen thuộc.
- **Tài liệu (document):** dữ liệu được nhóm thành những tài liệu có cấu trúc phân cấp, thường chứa đối tượng lồng nhau và mảng. MongoDB lưu tài liệu ở định dạng BSON; Spring Data MongoDB giúp ánh xạ tài liệu sang đối tượng Java và thao tác qua `MongoTemplate` hoặc repository.
- **Key-value:** mỗi giá trị được truy cập chủ yếu bằng một khóa duy nhất. Redis là ví dụ điển hình; ngoài chuỗi, Redis còn hỗ trợ các kiểu dữ liệu như hash, set và sorted set.

Ba mô hình này không chia ứng dụng thành ba nhóm tuyệt đối. Một hệ thống có thể dùng cơ sở dữ liệu quan hệ cho dữ liệu giao dịch, MongoDB cho các tài liệu nghiệp vụ có cấu trúc linh hoạt và Redis cho cache hoặc phiên đăng nhập. Điều cần quyết định là **dữ liệu nào thường được đọc và thay đổi cùng nhau**, các quan hệ cần bảo đảm đến đâu và ứng dụng phải hỗ trợ những loại truy vấn nào.

## 2. Cùng một bài toán: lưu đơn hàng

Giả sử hệ thống bán hàng cần lưu một đơn hàng gồm mã đơn, khách hàng, địa chỉ giao nhận, các dòng sản phẩm, số lượng, đơn giá tại thời điểm mua và tổng tiền. Các thao tác điển hình là:

1. Hiển thị toàn bộ đơn hàng theo mã đơn.
2. Liệt kê 20 đơn mới nhất của một khách hàng.
3. Cập nhật trạng thái đơn hàng mà không làm mất dữ liệu khác.
4. Thống kê số lượng sản phẩm đã bán trong một khoảng thời gian.

### 2.1. Mô hình quan hệ: tách thành các bảng

Một thiết kế thông dụng có bảng `customers`, `products`, `orders` và `order_items`. Ví dụ sau tập trung vào hai bảng của đơn hàng; giả định `customers(id)` và `products(id)` đã tồn tại:

```sql
CREATE TABLE orders (
    id          VARCHAR(32) PRIMARY KEY,
    customer_id VARCHAR(32) NOT NULL REFERENCES customers(id),
    created_at  TIMESTAMP NOT NULL,
    status      VARCHAR(32) NOT NULL,
    total       DECIMAL(18, 2) NOT NULL
);

CREATE TABLE order_items (
    order_id              VARCHAR(32) NOT NULL REFERENCES orders(id),
    line_no               INTEGER NOT NULL,
    product_id            VARCHAR(32) NOT NULL REFERENCES products(id),
    product_name_snapshot VARCHAR(200) NOT NULL,
    quantity              INTEGER NOT NULL,
    unit_price            DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no)
);
```

Khi cần lấy đơn hàng cùng các dòng sản phẩm, ứng dụng có thể dùng `JOIN`:

```sql
SELECT o.id, o.customer_id, o.status,
       i.line_no, i.product_id, i.quantity, i.unit_price
FROM orders AS o
JOIN order_items AS i ON i.order_id = o.id
WHERE o.id = 'order-1001'
ORDER BY i.line_no;
```

Kết quả truy vấn có nhiều hàng, mỗi hàng mang thông tin của một dòng sản phẩm. Ứng dụng hoặc ORM sẽ tập hợp chúng thành đối tượng `Order`. Khóa ngoại hỗ trợ bảo đảm một dòng sản phẩm thuộc về một đơn hàng có thật; giao dịch có thể phối hợp thay đổi nhiều bảng một cách nguyên tử.

**Điểm mạnh:** các thực thể và mối quan hệ được thể hiện rõ; dễ áp dụng ràng buộc dữ liệu, `JOIN`, truy vấn tùy biến và cập nhật một thực thể dùng chung ở nhiều nơi. **Chi phí:** một nghiệp vụ có nhiều bảng có thể cần `JOIN` hoặc nhiều lần truy cập dữ liệu. Điều này không mặc nhiên chậm: hiệu năng còn phụ thuộc chỉ mục, kế hoạch truy vấn, kích thước dữ liệu và cách ứng dụng tải các quan hệ.

### 2.2. Mô hình tài liệu: nhóm dữ liệu thành một document

Trong MongoDB, nếu ứng dụng thường đọc cả đơn hàng, có thể lưu dữ liệu gắn chặt với đơn trong một tài liệu thuộc collection `orders`:

```json
{
  "_id": "order-1001",
  "customerId": "customer-01",
  "createdAt": "2026-10-15T08:30:00Z",
  "status": "PAID",
  "shippingAddress": {
    "recipient": "Nguyen An",
    "city": "Da Nang",
    "street": "12 Nguyen Van Linh"
  },
  "items": [
    {
      "productId": "product-10",
      "productNameSnapshot": "Ban phim co",
      "quantity": 1,
      "unitPrice": 1200000
    },
    {
      "productId": "product-20",
      "productNameSnapshot": "Chuot khong day",
      "quantity": 2,
      "unitPrice": 450000
    }
  ],
  "total": 2100000
}
```

Đây là biểu diễn JSON dễ đọc; khi lưu thực tế, MongoDB dùng BSON và có thể sử dụng các kiểu chuyên biệt như `ObjectId`, `Date` hoặc `Decimal128`. Trong dữ liệu sản xuất, cần chọn kiểu phù hợp cho thời điểm và tiền tệ thay vì suy rằng chuỗi thời gian hay số JSON ở ví dụ đã thể hiện đầy đủ kiểu lưu trữ.

Một lần truy vấn có thể lấy toàn bộ document:

```javascript
db.orders.findOne({ _id: "order-1001" });

db.orders.find({ customerId: "customer-01" })
         .sort({ createdAt: -1 })
         .limit(20);
```

Hai trường `shippingAddress` và `items` được **nhúng (embedding)** vì chúng phục vụ việc đọc một đơn hàng. Trường `customerId` và `productId` đóng vai trò **tham chiếu (referencing)** đến thực thể có vòng đời riêng. Tên và đơn giá sản phẩm được giữ trong đơn dưới dạng *snapshot*: việc đổi giá sản phẩm hiện tại không được tự ý làm thay đổi lịch sử mua hàng.

**Điểm mạnh:** cấu trúc lưu trữ gần với đối tượng nghiệp vụ; thuận lợi cho việc đọc hoặc cập nhật các dữ liệu thường đi cùng nhau; tài liệu có thể chứa trường tùy chọn và cấu trúc lồng nhau. **Chi phí:** khi cùng một thông tin bị lặp trong nhiều document, ứng dụng phải hiểu thông tin nào là ảnh chụp lịch sử và thông tin nào phải đồng bộ; các quan hệ xuyên collection phức tạp có thể cần truy vấn bổ sung hoặc aggregation với `$lookup`.

### 2.3. Mô hình key-value: truy xuất theo khóa đã biết

Với Redis, một cách đơn giản là lưu toàn bộ đơn hàng thành chuỗi JSON theo khóa. Ví dụ ở đây minh họa tư duy truy xuất, không phải khuyến nghị dùng Redis làm nguồn dữ liệu đơn hàng chính:

```text
SET order:1001 '{"id":"order-1001","customerId":"customer-01","total":2100000}'
GET order:1001
```

Lệnh `GET` rất thuận tiện khi ứng dụng biết `order:1001`. Nhưng nếu muốn tìm *tất cả đơn hàng của customer-01*, mô hình key-value cơ bản không tự suy ra quan hệ từ nội dung JSON. Ứng dụng có thể duy trì một cấu trúc chỉ mục phụ:

```text
SADD customer:customer-01:orders order:1001
SMEMBERS customer:customer-01:orders
```

Khi thêm hoặc xóa đơn, ứng dụng phải cập nhật cả dữ liệu chính lẫn tập khóa phụ. `SMEMBERS` cũng không sắp xếp theo thời gian; muốn truy vấn đơn mới nhất, có thể cần sorted set và thêm quy tắc đồng bộ. Một số kho key-value và phần mở rộng cung cấp khả năng truy vấn phong phú hơn, nhưng đó là tính năng cụ thể của sản phẩm chứ không phải đặc trưng mặc định của mọi mô hình key-value.

**Điểm mạnh:** truy xuất bằng khóa rất trực tiếp, thích hợp cho cache, session, bộ đếm, token tạm thời và một số trạng thái thời gian thực. **Chi phí:** nhiều truy vấn ngoài khóa chính đòi hỏi ứng dụng tự thiết kế chỉ mục, cập nhật nhiều khóa hoặc dùng tính năng bổ sung của hệ quản trị.

## 3. Bảng so sánh theo các tiêu chí kỹ thuật

| Tiêu chí | Quan hệ | Tài liệu (MongoDB) | Key-value (ví dụ Redis) |
| --- | --- | --- | --- |
| Đơn vị dữ liệu chính | Hàng trong bảng; nhiều bảng liên kết bằng khóa | Document BSON với trường, object và array lồng nhau | Khóa và giá trị/kiểu dữ liệu gắn với khóa |
| Thiết kế cấu trúc | Schema bảng và ràng buộc tường minh | Schema linh hoạt giữa các document; có thể áp dụng schema validation | Cấu trúc thường được ứng dụng hoặc kiểu giá trị quyết định |
| Quan hệ dữ liệu | Khóa ngoại, `JOIN`, ràng buộc toàn vẹn | Nhúng dữ liệu hoặc lưu mã tham chiếu; có `$lookup` | Thường liên hệ bằng quy ước đặt khóa và chỉ mục do ứng dụng quản lý |
| Truy vấn nhiều điều kiện | SQL với lọc, `JOIN`, nhóm, tổng hợp | Filter, projection, index, aggregation pipeline | Truy xuất theo key là cơ bản; khả năng khác tùy hệ quản trị/tính năng |
| Thay đổi cấu trúc | Thường dùng migration schema và dữ liệu | Có thể thêm trường dần, nhưng cần kiểm soát phiên bản tài liệu | Thường thay đổi định dạng value và xử lý tương thích ở ứng dụng |
| Cập nhật nhiều thực thể | Transaction trên nhiều hàng/bảng là cách làm phổ biến | Một thao tác ghi trên một document có tính nguyên tử; có multi-document transaction | Lệnh đơn thường nguyên tử; cơ chế nhóm lệnh, transaction hoặc script tùy sản phẩm |
| Dữ liệu lặp | Có thể giảm nhờ chuẩn hóa; vẫn có denormalization khi cần | Có chủ đích khi nhúng/sao chép để tối ưu luồng đọc | Thường lưu snapshot hoặc duy trì nhiều khóa phục vụ truy cập |
| Mở rộng | Có replication, partitioning/sharding tùy hệ quản trị | Có replication và sharding | Có replication/cluster tùy hệ quản trị |
| Trường hợp thuận lợi | Nhiều quan hệ, ràng buộc chéo và báo cáo SQL phức tạp | Dữ liệu phân cấp, aggregate nghiệp vụ được đọc cùng nhau | Tra cứu theo khóa, cache, session, cấu trúc truy cập đơn giản |

Không nên rút ra kết luận rằng một mô hình luôn nhanh hơn hoặc nhất quán hơn hai mô hình còn lại. Ví dụ, truy vấn MongoDB không có index phù hợp có thể phải quét nhiều document; một truy vấn SQL sử dụng index và `JOIN` hợp lý lại có thể rất hiệu quả. Hiệu năng phải được đánh giá trên cùng dữ liệu, mẫu truy cập và yêu cầu độ trễ.

## 4. Phân biệt embedding, referencing và chuẩn hóa

Trong Spring Data MongoDB, quyết định quan trọng nhất thường không phải là đặt tên collection, mà là **chọn ranh giới document**.

### Khi nên nhúng dữ liệu?

Nhúng hợp lý khi dữ liệu con có vòng đời phụ thuộc dữ liệu cha, số lượng phần tử có giới hạn hợp lý và phần lớn thao tác đọc/ghi xảy ra cùng nhau. Địa chỉ giao nhận ghi tại thời điểm đặt hàng và các dòng hàng của một đơn là những ví dụ thường phù hợp. Một thao tác cập nhật đơn document có thể thay đổi nhiều trường trong cùng document một cách nguyên tử.

### Khi nên tham chiếu?

Tham chiếu hợp lý khi thực thể được dùng chung, có vòng đời độc lập hoặc danh sách liên quan tăng không giới hạn. Khách hàng có thể có hàng triệu đơn hàng: không nên đưa toàn bộ đơn vào một mảng nằm trong document khách hàng. Thay vào đó, đặt `customerId` trên mỗi đơn và đánh index để truy vấn theo khách hàng.

Trong mô hình quan hệ, chuẩn hóa tách thực thể thành các bảng và quản lý liên hệ qua khóa. Trong MongoDB, **embedding và referencing có thể cùng tồn tại** trong một aggregate. Spring Data hỗ trợ các cơ chế tham chiếu như `@DBRef` và `@DocumentReference`, nhưng chúng không biến MongoDB thành hệ cơ sở dữ liệu có khóa ngoại hoặc tự động tạo một phép `JOIN` SQL. Cần cân nhắc số lần đọc phát sinh, quy tắc cập nhật và việc có thực sự cần tự động giải tham chiếu hay không. Với nhiều trường hợp, lưu ID và truy vấn có kiểm soát là đủ.

### Hai giới hạn dễ bị bỏ qua

- **Mảng tăng vô hạn:** danh sách sự kiện, lượt xem hoặc tất cả đơn hàng trong một document có thể khiến document phình to, tăng chi phí cập nhật và chạm giới hạn kích thước document MongoDB (16 MiB đối với BSON document thông thường). Nên tách những tập hợp tăng không giới hạn thành collection riêng.
- **Sao chép thiếu quy tắc:** `productNameSnapshot` của đơn hàng nên được cố định theo lịch sử; tên hiển thị hiện tại của sản phẩm, nếu lặp ở nhiều nơi và phải cập nhật đồng loạt, cần chiến lược đồng bộ hoặc chuyển sang tham chiếu. Không phải mọi dữ liệu trùng lặp đều là lỗi, nhưng mỗi bản sao cần có ý nghĩa rõ ràng.

## 5. Tính nhất quán và transaction khác nhau thế nào?

Xét nghiệp vụ **chốt đơn và giảm tồn kho**:

- **Quan hệ:** nếu đơn hàng, dòng hàng và tồn kho nằm ở các bảng khác nhau, ứng dụng thường dùng transaction để bảo đảm tất cả thay đổi cùng thành công hoặc cùng được hoàn tác. Mức cô lập và hiện tượng đọc/ghi đồng thời vẫn phụ thuộc cấu hình và câu lệnh cụ thể.
- **MongoDB:** một thao tác cập nhật *một* document là nguyên tử, kể cả khi cập nhật đồng thời nhiều trường và phần tử lồng nhau trong document ấy. Nếu ghi vào document `orders` và một document `inventory` khác, cần thiết kế xử lý lỗi và điều kiện cạnh tranh; MongoDB có hỗ trợ transaction trên nhiều document khi triển khai đáp ứng các yêu cầu tương ứng. Transaction đa document có chi phí, nên cần cân nhắc ranh giới nghiệp vụ và mẫu truy cập trước khi dựa vào nó thường xuyên.
- **Key-value:** một lệnh Redis như `INCR` mang tính nguyên tử đối với khóa/giá trị mà lệnh thao tác. Redis còn hỗ trợ `MULTI`/`EXEC` và script cho các trường hợp cần phối hợp lệnh; tuy nhiên mức bảo đảm, xử lý lỗi và độ bền không nên mặc định giống transaction của cơ sở dữ liệu quan hệ, nhất là khi thao tác còn liên quan hệ thống khác.

Đừng đồng nhất **atomicity** (một thao tác được áp dụng trọn vẹn), **isolation** (cách các thao tác đồng thời quan sát nhau), **durability** (khả năng lưu bền) và **consistency của nghiệp vụ** (chẳng hạn không được bán quá tồn kho). Muốn đánh giá đúng phải xác định những bất biến cần giữ, phạm vi thay đổi và cơ chế hỗ trợ của hệ quản trị thực tế.

## 6. Truy vấn, chỉ mục và chi phí đọc ghi

### 6.1. Cùng một nhu cầu truy vấn, các cách tối ưu khác nhau

Với yêu cầu *20 đơn mới nhất của một khách hàng*:

**Quan hệ:** dùng `WHERE customer_id = ? ORDER BY created_at DESC LIMIT 20` và thường cân nhắc index tổng hợp `(customer_id, created_at)` theo đặc điểm bảng, hệ quản trị và kế hoạch truy vấn.

**MongoDB:** dùng filter trên `customerId`, sắp xếp `createdAt` và index tổng hợp:

```javascript
db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find({ customerId: "customer-01" })
         .sort({ createdAt: -1 })
         .limit(20);
```

Một index phù hợp có thể hỗ trợ cả lọc và sắp xếp. Khi phân tích hiệu năng thật, dùng `explain("executionStats")` để quan sát kế hoạch truy vấn và các chỉ số như số document/index key đã duyệt:

```javascript
db.orders.find({ customerId: "customer-01" })
         .sort({ createdAt: -1 })
         .limit(20)
         .explain("executionStats");
```

**Key-value:** nếu đã có `order:1001`, đọc theo khóa rất đơn giản. Để có danh sách đơn theo khách hàng và thứ tự thời gian, có thể duy trì sorted set, dùng timestamp làm score, đồng thời phải cập nhật tập này khi dữ liệu đơn thay đổi. Tính đúng đắn của chỉ mục ứng dụng vì vậy là một phần của thiết kế.

### 6.2. Aggregation và `JOIN`

SQL hỗ trợ các phép kết hợp và tổng hợp trên bảng qua `JOIN`, `GROUP BY`, hàm cửa sổ và các phép truy vấn khác. MongoDB cung cấp **aggregation pipeline** với các stage như `$match`, `$unwind`, `$group`, `$project`, `$sort` và `$lookup` để xử lý dữ liệu trong hoặc giữa các collection. Ví dụ tổng số lượng mặt hàng từng khách hàng đã đặt:

```javascript
db.orders.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: "$customerId",
      totalUnits: { $sum: "$items.quantity" }
    }
  },
  { $sort: { totalUnits: -1 } }
]);
```

Pipeline này hữu ích khi cần tổng hợp dữ liệu lồng nhau; trên lượng dữ liệu lớn, cần cân nhắc lọc sớm bằng `$match`, index phù hợp, số phần tử bị `$unwind` và chi phí xử lý. Nếu nghiệp vụ cần nhiều phép nối tùy ý qua nhiều thực thể và báo cáo quan hệ phức tạp, một hệ cơ sở dữ liệu quan hệ hoặc kho phân tích chuyên dụng có thể phù hợp hơn.

### 6.3. Schema linh hoạt không có nghĩa là bỏ kiểm soát

MongoDB cho phép hai document cùng collection có tập trường khác nhau. Điều này hữu ích cho sản phẩm với thuộc tính biến thiên, nhưng ứng dụng Java vẫn cần hợp đồng dữ liệu ổn định: tên trường, kiểu, trường bắt buộc, quy tắc mặc định và cách nâng cấp dữ liệu cũ. Có thể sử dụng **schema validation** ở phía MongoDB, Bean Validation ở ứng dụng và migration khi thay đổi cấu trúc có ảnh hưởng lớn.

Một thuộc tính mới như `deliveryInstructions` có thể được thêm vào các đơn mới, nhưng mã xử lý đơn cũ vẫn phải chấp nhận trường không tồn tại. Hệ quan hệ thường giải quyết phần thay đổi đó bằng migration bảng; mô hình key-value thường phải quy định phiên bản hoặc định dạng của value. Cả ba đều cần chiến lược tương thích dữ liệu.

## 7. Áp dụng vào Spring Data MongoDB

Spring Data MongoDB là tầng truy cập dữ liệu cho ứng dụng Java/Spring. Nó **không thay đổi đặc trưng của MongoDB**, mà cung cấp ánh xạ giữa Java và document, repository, `MongoTemplate`, aggregation, quản lý chỉ mục và hỗ trợ cách truy cập reactive.

### 7.1. Ánh xạ một document có dữ liệu lồng nhau

Ví dụ dùng Java record để mô tả cùng một aggregate đơn hàng:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String customerId,
    Instant createdAt,
    String status,
    Address shippingAddress,
    List<OrderLine> items,
    BigDecimal total
) {}

record Address(String recipient, String city, String street) {}

record OrderLine(
    String productId,
    String productNameSnapshot,
    int quantity,
    BigDecimal unitPrice
) {}
```

`@Document` xác định collection, `@Id` ánh xạ định danh document, còn các record `Address` và `OrderLine` được lưu thành cấu trúc lồng nhau. Đây là ví dụ về mô hình hóa; trong hệ thống thật, cần thống nhất cách lưu số tiền (`BigDecimal`/`Decimal128` hoặc đơn vị tiền nhỏ nhất), kiểm tra dữ liệu đầu vào và cơ chế đổi schema theo phiên bản. Kiểu BSON và cách biểu diễn số cụ thể phụ thuộc cấu hình chuyển đổi của ứng dụng.

### 7.2. Truy vấn bằng repository hoặc `MongoTemplate`

Repository phù hợp cho những truy vấn đơn giản, có mẫu lặp lại:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {
    Page<OrderDocument> findByCustomerId(String customerId, Pageable pageable);
}
```

Khi gọi với `PageRequest` có sắp xếp giảm dần theo `createdAt`, repository trả về trang đơn hàng của một khách hàng. `Page` có thể phát sinh truy vấn đếm tổng số bản ghi; nếu chỉ cần biết có trang tiếp theo, cân nhắc `Slice` để tránh đếm không cần thiết.

`MongoTemplate` phù hợp khi cần tự xây dựng filter, sort, projection hoặc thao tác cập nhật đặc thù:

```java
Query query = Query.query(Criteria.where("customerId").is(customerId))
    .with(Sort.by(Sort.Direction.DESC, "createdAt"))
    .limit(20);

List<OrderDocument> orders =
    mongoTemplate.find(query, OrderDocument.class);
```

Đoạn này giả định `mongoTemplate`, `customerId` và các import của `Query`, `Criteria`, `Sort`, `List` đã có trong service. Cả repository và template đều thực thi truy vấn trên cùng collection MongoDB; lựa chọn API phụ thuộc mức kiểm soát truy vấn mà ứng dụng cần.

### 7.3. Những năng lực cần kết nối với thiết kế document

- **Index:** thiết kế theo những filter, sort và phân trang thực tế. Có thể khai báo annotation như `@Indexed`/`@CompoundIndex` hoặc tạo index qua quy trình quản trị/migration. Đừng mặc định index annotation sẽ được tạo tự động ở mọi cấu hình Spring Data MongoDB.
- **Aggregation:** dùng `MongoTemplate.aggregate(...)` khi cần pipeline nhiều stage; kiểm tra khả năng tận dụng index và kích thước tập dữ liệu trung gian.
- **Transaction:** dùng `MongoTransactionManager` cùng môi trường MongoDB hỗ trợ transaction khi thao tác nhiều document thật sự cần tính nguyên tử; đánh giá chi phí và điều kiện triển khai.
- **Reactive:** `ReactiveMongoRepository` và `ReactiveMongoTemplate` hỗ trợ luồng truy cập không chặn trong ứng dụng reactive. Reactive không tự làm truy vấn MongoDB nhanh hơn; lợi ích phụ thuộc tải đồng thời, kiến trúc và việc tránh chặn luồng.
- **Kiểm thử:** thử ánh xạ document, document thiếu trường, truy vấn trên dữ liệu lồng nhau, index quan trọng và hành vi transaction bằng bài kiểm thử tích hợp trên MongoDB thực (chẳng hạn thông qua Testcontainers) với cấu hình triển khai phù hợp.
- **Chẩn đoán:** dùng `explain`, thống kê truy vấn chậm và số document quét để xác định vấn đề. Tăng hiệu năng bằng index, projection, giới hạn kết quả và điều chỉnh ranh giới document trước khi kết luận do chọn sai mô hình dữ liệu.

## 8. Chọn mô hình theo đặc điểm nghiệp vụ

| Nhu cầu cụ thể | Mô hình thường đáng cân nhắc trước | Lý do chính và điều cần kiểm tra |
| --- | --- | --- |
| Sổ cái, bút toán liên quan nhiều tài khoản, ràng buộc mạnh | Quan hệ | Transaction và ràng buộc qua nhiều hàng/bảng; vẫn phải thiết kế mức cô lập, kiểm toán và bất biến nghiệp vụ |
| Đọc một đơn hàng cùng địa chỉ và các dòng hàng | Tài liệu hoặc quan hệ | Document thuận lợi nếu dữ liệu có ranh giới aggregate rõ; quan hệ cũng tốt nếu có nhiều nhu cầu nối và báo cáo |
| Catalog sản phẩm có nhóm thuộc tính khác nhau | Tài liệu | Cấu trúc linh hoạt; vẫn cần schema validation, index và quy tắc tìm kiếm rõ ràng |
| Tra cứu session theo token, cache kết quả có TTL | Key-value | Đọc theo khóa và quản lý thời hạn đơn giản; cân nhắc độ bền và chiến lược làm mới cache |
| Báo cáo nhiều thực thể với nhiều phép nối tùy ý | Quan hệ hoặc hệ phân tích | SQL và công cụ phân tích có thể phù hợp hơn; đánh giá dữ liệu, tần suất và mô hình truy vấn |
| Dòng sự kiện rất dài cho từng người dùng | Nhiều document hoặc bảng độc lập | Không dồn toàn bộ sự kiện vào mảng tăng mãi; cần chiến lược phân trang, lưu trữ và lưu giữ dữ liệu |

Một phương pháp chọn thiết kế là bắt đầu từ **truy vấn và bất biến nghiệp vụ**, sau đó mới vẽ cấu trúc lưu trữ:

1. Liệt kê các thao tác đọc/ghi quan trọng, tần suất và độ trễ mong muốn.
2. Xác định những dữ liệu luôn thay đổi cùng nhau và những đối tượng có vòng đời độc lập.
3. Đánh dấu dữ liệu tăng không giới hạn, quan hệ nhiều-nhiều và những giá trị được dùng chung.
4. Liệt kê ràng buộc nhất quán phải được giữ khi có nhiều thao tác đồng thời.
5. Thiết kế index và đo bằng truy vấn mẫu trên tập dữ liệu đại diện, kể cả trường hợp phân trang và lượng dữ liệu tăng.

Nếu ứng dụng dùng đồng thời MongoDB và Redis, cần xác định đâu là **nguồn dữ liệu chuẩn (source of truth)**, thời điểm cache hết hạn hoặc bị vô hiệu hóa và hành vi khi cache lỗi. Việc thêm một cơ sở dữ liệu vào kiến trúc cũng tăng yêu cầu đồng bộ, vận hành và kiểm thử.

## 9. Các ngộ nhận thường gặp

**“MongoDB không có schema.”** MongoDB không yêu cầu mọi document trong collection giống hệt nhau, nhưng dữ liệu vẫn có cấu trúc. Có thể dùng schema validation; mã Java, truy vấn, index và báo cáo đều phụ thuộc hợp đồng trường dữ liệu.

**“Document là dữ liệu không có quan hệ.”** Document có thể chứa dữ liệu lồng nhau và tham chiếu tới document khác. Sự khác biệt nằm ở cách biểu diễn và quản lý quan hệ, không phải quan hệ biến mất.

**“MongoDB không hỗ trợ transaction hay join.”** MongoDB có multi-document transaction và `$lookup`. Câu hỏi quan trọng là chi phí và mức độ phù hợp của chúng với workload; không nên mặc định rằng cách sử dụng sẽ giống SQL.

**“Redis chỉ lưu chuỗi, hoặc không thể có truy vấn khác GET.”** Redis có nhiều cấu trúc dữ liệu và các khả năng mở rộng. Tuy vậy, khả năng tra cứu tùy ý dựa trên mọi trường trong một JSON value không phải điều tự nhiên có được chỉ từ cặp key-value.

**“Nhúng mọi thứ sẽ nhanh hơn.”** Nhúng một tập hợp tăng không giới hạn, chứa dữ liệu dùng chung hoặc thay đổi độc lập có thể làm document quá lớn và tạo nhiều lần ghi dư thừa. Cần xác định ranh giới aggregate trước khi nhúng.

**“NoSQL luôn mở rộng tốt hơn SQL.”** Khả năng mở rộng phụ thuộc sản phẩm, cấu hình phân vùng, khóa phân phối, index, truy vấn và giới hạn hạ tầng. Hệ quan hệ cũng có nhiều cơ chế mở rộng, còn MongoDB/Redis cũng có các kiểu truy cập gây nghẽn.

## 10. Kết luận cho người học Spring Data MongoDB

Mô hình **quan hệ** ưu tiên biểu diễn thực thể và các liên hệ bằng bảng, khóa và ràng buộc; mô hình **tài liệu** ưu tiên gom dữ liệu theo aggregate nghiệp vụ để đọc/ghi cùng nhau; mô hình **key-value** ưu tiên truy xuất bằng khóa và các cấu trúc gắn với khóa. Không có lựa chọn tốt nhất cho mọi ứng dụng.

Khi sử dụng Spring Data MongoDB, hãy xem `@Document`, repository và `MongoTemplate` là công cụ hiện thực hóa thiết kế đã chọn. Chất lượng hệ thống phụ thuộc vào việc chọn đúng ranh giới nhúng/tham chiếu, bảo đảm bất biến nghiệp vụ, tạo index theo truy vấn và kiểm chứng hiệu năng trên dữ liệu thật. Đó là nền tảng để học sâu hơn về aggregation, transaction, reactive access và tối ưu MongoDB.
