# Thiết kế document, tham chiếu, ID và index

Trong một dự án **Spring Data MongoDB**, thiết kế dữ liệu tốt bắt đầu từ cách ứng dụng **đọc và ghi dữ liệu**, chứ không chỉ từ danh sách các entity Java. Một lựa chọn sai ở cấp document có thể khiến hệ thống phải join nhiều collection cho mỗi request; một mảng nhúng tăng không giới hạn có thể vượt giới hạn kích thước document; một index đặt sai thứ tự có thể không hỗ trợ truy vấn và sort thường xuyên nhất.

Bài **thực hành tổng hợp** này hướng dẫn thiết kế mô hình dữ liệu cho một dịch vụ đặt hàng đa tenant. Người học sẽ kết hợp mô hình document, embedding và reference, định danh `_id`, ràng buộc duy nhất, compound index, thao tác `MongoTemplate`/repository, truy vấn kiểm chứng và các phép thử hiệu năng. Phần giải pháp là một kiến trúc tham khảo có giải thích quyết định và giới hạn, có thể điều chỉnh theo yêu cầu dự án thực tế.

## 1. Đề bài và hành vi cần phục vụ

Xây dựng dịch vụ quản lý đơn hàng cho nhiều cửa hàng (*tenant*). Mỗi đơn hàng thuộc đúng một tenant và một khách hàng; mỗi đơn có từ một đến nhiều dòng hàng. Sản phẩm có thể đổi tên hoặc giá trong tương lai, nhưng đơn hàng đã đặt phải giữ được thông tin giá và tên tại thời điểm mua. Tồn kho được cập nhật thường xuyên và cần bảo vệ khỏi tình trạng bán vượt số lượng.

Ứng dụng cần hỗ trợ các thao tác:

| Mã | Nhu cầu | Đặc điểm truy cập |
| --- | --- | --- |
| Q1 | Lấy đơn theo `tenantId` + `orderNumber` | Truy vấn điểm, tần suất cao, phải duy nhất trong tenant |
| Q2 | Xem 30 đơn `PAID` mới nhất trong một tenant | Filter bằng + sort giảm dần + phân trang |
| Q3 | Xem lịch sử đơn hàng của một khách | Filter tenant, customer và sort theo thời gian |
| Q4 | Đọc chi tiết đơn, gồm tên/giá từng dòng tại thời điểm đặt | Đọc cùng một lần, nhất quán theo snapshot đơn hàng |
| Q5 | Lấy thông tin sản phẩm hiện tại để hiển thị catalog | Sản phẩm độc lập, có thể cập nhật thường xuyên |
| Q6 | Trừ tồn kho khi xác nhận đặt hàng | Cập nhật có điều kiện, tránh trừ khi không đủ hàng |
| Q7 | Báo cáo đơn chứa một sản phẩm cụ thể | Tần suất thấp hơn, có thể cần index hoặc luồng phân tích riêng |

Giả định ban đầu: mỗi đơn có tối đa 100 dòng hàng; lịch sử đơn phải được giữ nhiều năm; sản phẩm có thể được sử dụng bởi hàng nghìn đơn; tenant nào cũng có mã đơn riêng; không có yêu cầu đổi chủ sở hữu đơn sau khi tạo. Đây là **giả định của bài tập**, phải thay bằng dữ liệu quan sát thực tế trước khi triển khai sản xuất.

### Kết quả cần hoàn thành

Người học cần tạo: sơ đồ collection và quan hệ, mẫu BSON cho mỗi collection, quy tắc tạo `_id`/khóa nghiệp vụ, danh sách index gắn với Q1–Q7, mapping Java cơ bản, truy vấn đối chiếu bằng `MongoTemplate` hoặc repository, các phép kiểm chứng `explain("executionStats")` và bộ test cho ràng buộc dữ liệu/cập nhật cạnh tranh.

## 2. Bắt đầu từ aggregate và ranh giới cập nhật

Một **aggregate** là cụm dữ liệu cần được kiểm tra nhất quán theo quy tắc nghiệp vụ. Trong MongoDB, thiết kế thường thuận lợi khi dữ liệu hay được đọc và sửa cùng nhau nằm trong một document, vì thao tác ghi lên **một document** có tính nguyên tử. Tuy nhiên aggregate nghiệp vụ không bắt buộc tương ứng chính xác với một collection trong mọi hệ thống.

Với đề bài này:

- **Order** là aggregate gồm thông tin đơn và danh sách `lines`. Các dòng hàng cùng tạo nên nội dung và tổng tiền của đơn; số dòng bị giới hạn, nên chúng phù hợp để **embed** trong `orders`.
- **Product** có vòng đời riêng: tên, mô tả, giá hiện hành, trạng thái bán. Hàng nghìn đơn có thể tham chiếu cùng sản phẩm, nên lưu thành document riêng trong `products`.
- **Customer** có thông tin liên hệ riêng, có thể thay đổi; đơn hàng lưu `customerId`, nhưng có thể nhúng snapshot địa chỉ nhận hàng để bảo toàn thông tin giao hàng tại thời điểm mua.
- **Inventory** có tần suất ghi cao và quy tắc cạnh tranh riêng; đưa tồn kho vào document `inventory` riêng cho mỗi `(tenantId, productId)` để cập nhật có điều kiện.

~~~mermaid
flowchart LR
    C[(customers)] -->|customerId tham chiếu| O[(orders)]
    P[(products)] -->|productId + snapshot trong lines| O
    P -->|productId| I[(inventory)]
    O --> L[lines nhúng: SKU, tên, đơn giá, số lượng]
~~~

MongoDB **không tự cưỡng chế khóa ngoại** giữa `orders.customerId` và `customers._id`, hoặc giữa `orders.lines.productId` và `products._id`. Ứng dụng phải có quy tắc kiểm tra tồn tại, quyền truy cập theo tenant, xóa mềm/khôi phục và cách xử lý tham chiếu mồ côi. Nếu cần một thao tác cập nhật nhiều document nhất quán, cân nhắc transaction khi MongoDB và ứng dụng đã được cấu hình phù hợp.

## 3. Quyết định embed hay reference

Không có câu trả lời cố định “MongoDB phải embed tất cả” hoặc “giữ mọi thứ tách riêng”. Hãy trả lời từng câu hỏi về vòng đời, kích thước, tần suất cập nhật và query shape.

| Dữ liệu | Lựa chọn | Lý do trong bài tập |
| --- | --- | --- |
| Các dòng hàng của một đơn | **Embed** `lines[]` trong `orders` | Thường đọc cùng đơn, số lượng bị chặn, giữ snapshot giá/tên cùng trạng thái đơn |
| Tên/giá của product tại thời điểm đặt | **Nhúng bản sao** trong `lines[]` | Sau khi catalog đổi giá hoặc tên, lịch sử đơn vẫn đúng |
| Khách hàng sở hữu đơn | **Reference** qua `customerId` | Một khách có nhiều đơn; thông tin khách thay đổi độc lập |
| Địa chỉ giao nhận đã xác nhận | **Snapshot embed** trong `orders` | Địa chỉ nhận của đơn không được đổi theo hồ sơ khách |
| Tồn kho hiện tại | **Collection riêng** `inventory` | Thay đổi thường xuyên, tránh ghi vào mọi đơn hoặc document sản phẩm lớn |
| Bình luận/tracking log tăng không giới hạn | **Collection riêng**, truy xuất theo `orderId` | Không nhúng mảng vô hạn vào document đơn |

### Những dấu hiệu nên ưu tiên embedding

Embedding phù hợp khi phần tử con có vòng đời gắn chặt với cha, được đọc cùng cha, số lượng nhỏ/có giới hạn và cần cập nhật nguyên tử cùng document. Ví dụ một `OrderLine` gồm `productId`, `sku`, `nameAtPurchase`, `unitPriceMinor`, `quantity` là một **snapshot**. Đổi tên catalog không được ghi đè lịch sử của đơn.

### Những dấu hiệu nên ưu tiên reference

Reference phù hợp khi dữ liệu có vòng đời độc lập, được chia sẻ cho nhiều document, cập nhật thường xuyên hoặc có tập con không giới hạn. Chẳng hạn không nhúng toàn bộ lịch sử đơn vào một customer: lịch sử có thể tăng mãi, gây update lớn và có nguy cơ chạm giới hạn **16 MiB cho một BSON document** của MongoDB.

**Đánh đổi cần nhớ:** Reference có thể khiến ứng dụng cần thêm query hoặc `$lookup`. Với nhiều reference, tải truy vấn phụ thuộc cách batch fetch và phân trang; không nên mặc định một thao tác đọc nhiều ID là không tốn chi phí. Embed giúp giảm số lần đọc nhưng làm tăng kích thước document và có thể khiến cập nhật lặp nhiều bản sao. Chọn cách lưu theo use case thực tế.

## 4. Thiết kế mẫu document

### Collection `orders`

~~~javascript
{
  _id: "ord_01K8XYN7H4RG25K9P12B3A",          // ID kỹ thuật ổn định
  tenantId: "shop_01",
  orderNumber: "SO-2026-00127",                // Mã nghiệp vụ trong tenant
  customerId: "cus_01K8XYG0N3E4K41ZTY0Q",
  status: "PAID",
  createdAt: ISODate("2026-11-20T03:15:00Z"),
  updatedAt: ISODate("2026-11-20T03:20:00Z"),
  currency: "VND",
  totalMinor: NumberLong("310000"),
  shippingAddress: {
    recipientName: "Nguyễn An",
    city: "Hồ Chí Minh",
    addressLine: "Địa chỉ nhận hàng tại thời điểm đặt"
  },
  lines: [
    {
      productId: "prd_01K8XX52P30A4T5ZXM6Q",
      skuAtPurchase: "MUG-RED",
      nameAtPurchase: "Cốc gốm đỏ",
      unitPriceMinor: NumberLong("120000"),
      quantity: 2,
      lineTotalMinor: NumberLong("240000")
    },
    {
      productId: "prd_01K8XX8BTB0Y7F5CAW1R",
      skuAtPurchase: "BOOK-01",
      nameAtPurchase: "Sổ tay",
      unitPriceMinor: NumberLong("70000"),
      quantity: 1,
      lineTotalMinor: NumberLong("70000")
    }
  ],
  version: NumberLong("2")
}
~~~

`totalMinor` và `unitPriceMinor` dùng đơn vị nhỏ nhất của tiền tệ theo quy ước hệ thống. Với VND trong ví dụ, quy ước một đơn vị nguyên tương ứng một đồng; với tiền tệ khác phải xử lý số chữ số thập phân theo hợp đồng nghiệp vụ. `long` tránh nhiều lỗi làm tròn của số thực dấu phẩy động, nhưng vẫn cần kiểm tra overflow khi tính tổng và quy tắc thuế/khuyến mại. Một lựa chọn khác là **Decimal128** cùng quy ước rounding rõ ràng.

### Collection `products`

~~~javascript
{
  _id: "prd_01K8XX52P30A4T5ZXM6Q",
  tenantId: "shop_01",
  sku: "MUG-RED",
  displayName: "Cốc gốm đỏ phiên bản mới",
  currentPriceMinor: NumberLong("135000"),
  currency: "VND",
  active: true,
  updatedAt: ISODate("2026-11-21T02:00:00Z")
}
~~~

Tên và giá trong product có thể thay đổi; chúng **không làm thay đổi** `nameAtPurchase` và `unitPriceMinor` trong các đơn đã đặt.

### Collection `customers`

~~~javascript
{
  _id: "cus_01K8XYG0N3E4K41ZTY0Q",
  tenantId: "shop_01",
  displayName: "Nguyễn An",
  emailNormalized: "an@example.com",
  active: true
}
~~~

### Collection `inventory`

~~~javascript
{
  _id: "stock_shop01_mugred",
  tenantId: "shop_01",
  productId: "prd_01K8XX52P30A4T5ZXM6Q",
  available: 21,
  reserved: 3,
  updatedAt: ISODate("2026-11-20T03:20:00Z")
}
~~~

`inventory` có một document cho từng cặp `(tenantId, productId)`. `_id` trong ví dụ chỉ có tính minh họa; khi tạo ID thật cần tránh xung đột do cách nối chuỗi, phân biệt hoa/thường và các ký tự đặc biệt. Dù đã mã hóa tenant/product vào `_id`, vẫn nên dùng **unique index** trên cặp trường nghiệp vụ để ràng buộc bằng chính dữ liệu cần được bảo vệ.

## 5. Thiết kế ID và khóa nghiệp vụ

### Phân biệt `_id`, khóa tự nhiên và mã hiển thị

| Khóa | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `_id` | Định danh kỹ thuật duy nhất **trong một collection**; MongoDB tự tạo unique index | Nên bất biến, có thể dùng ObjectId hoặc String định dạng nhất quán |
| `orderNumber` | Mã đơn người dùng nhìn thấy | Chỉ cần duy nhất **trong tenant** theo đề bài; không dùng làm khóa kỹ thuật nếu có khả năng đổi format |
| `(tenantId, sku)` | Khóa nghiệp vụ xác định SKU trong catalog tenant | Dùng compound unique index; cùng SKU có thể xuất hiện ở tenant khác |
| `(tenantId, productId)` của inventory | Mỗi sản phẩm có một bản ghi tồn kho trong một tenant | Dùng compound unique index và kiểm soát cập nhật đồng thời |
| `customerId` trong order | Tham chiếu đến customer | Không tự bảo đảm customer tồn tại, đúng tenant hoặc chưa bị xóa |

**ObjectId** là lựa chọn mặc định phổ biến cho `_id`: gọn, có tính duy nhất cao và có thành phần thời gian, nhưng không nên dùng phần thời gian của ObjectId thay cho trường nghiệp vụ `createdAt`. ID kiểu UUID/ULID/String cũng có thể phù hợp khi các dịch vụ cần tạo ID từ trước; phải cân nhắc kích thước index, khả năng lộ thông tin, tính đơn điệu và tương thích giữa hệ thống.

Với **Spring Data MongoDB**, `@Id String id` có hành vi chuyển đổi sang BSON ObjectId trong một số trường hợp giá trị chuỗi có định dạng hợp lệ. Nếu hợp đồng đòi `_id` luôn lưu dưới dạng BSON string, có thể dùng `@MongoId(FieldType.STRING)` và kiểm tra mapping trên phiên bản Spring Data đang dùng. Không thay kiểu `_id` của collection đã có dữ liệu một cách tùy tiện: ObjectId và string nhìn giống nhau khi in log nhưng là **hai kiểu BSON khác nhau** và không tự truy vấn trùng khớp.

### Quy tắc ID cho môi trường đa tenant

MongoDB chỉ đảm bảo `_id` duy nhất trong collection, không suy ra quyền truy cập dựa vào ID. Mọi query từ người dùng vẫn phải kiểm tra `tenantId` phù hợp. Khi request gửi `orderId` của tenant khác, endpoint phải từ chối hoặc trả không tìm thấy theo chính sách của API, kể cả khi `_id` có thể truy vấn được.

Nếu chọn sharding, cần đánh giá thêm **shard key** và các quy tắc unique index của MongoDB. Trong sharded collection, để thực thi ràng buộc duy nhất toàn cục theo nhiều trường, unique index thường phải phù hợp với quy tắc shard key prefix và cấu hình sharding tương ứng; không tự giả định mọi unique index hợp lệ như trên collection không sharded.

## 6. Mapping entity với Spring Data MongoDB

Ví dụ entity ánh xạ document `orders`, sử dụng `@MongoId` để giữ ID kỹ thuật dạng chuỗi và `@Version` để bảo vệ thao tác `save` có kiểm tra phiên bản:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;
    private String tenantId;
    private String orderNumber;
    private String customerId;
    private String status;
    private Instant createdAt;
    private Instant updatedAt;
    private String currency;
    private long totalMinor;
    private List<OrderLine> lines;

    @Version
    private Long version;

    // Constructors, getters và setters được lược bỏ để tập trung vào thiết kế.
}

record OrderLine(
    String productId,
    String skuAtPurchase,
    String nameAtPurchase,
    long unitPriceMinor,
    int quantity,
    long lineTotalMinor
) {}
~~~

`@Version` giúp các thao tác được Spring Data hỗ trợ kiểm tra phiên bản khi cập nhật document, nhưng không bảo vệ những câu lệnh driver hoặc update tùy chỉnh **bỏ qua điều kiện version**. Khi dùng Spring Data với `Instant`, hãy kiểm tra BSON Date và chính sách múi giờ trong dữ liệu thực tế. Nếu dùng `@Field` để đổi tên trường, mọi truy vấn qua driver trực tiếp phải dùng đúng tên field vật lý.

Có thể khai báo chỉ lưu `customerId` và `productId` là các scalar reference như ví dụ, sau đó query qua repository/MongoTemplate theo lô. Spring Data MongoDB cũng có `@DBRef` và `@DocumentReference` để biểu diễn reference theo những cơ chế khác nhau. Tuy nhiên MongoDB **không tự kiểm tra tính toàn vẹn** của các reference này; cách tải eager/lazy, số truy vấn sinh ra, vòng tham chiếu và document bị xóa vẫn cần thiết kế. Với luồng lấy chi tiết đơn vốn đã có snapshot, không cần tự động truy vấn product/customer cho mọi dòng hàng.

## 7. Thiết kế index xuất phát từ truy vấn Q1–Q7

MongoDB tự có unique index trên `_id`. Các index còn lại cần phục vụ **query shape** cụ thể, đồng thời phải cân nhắc chi phí ghi và dung lượng. Mỗi index làm cho lệnh `insert`/`update`/`delete` tốn thêm công duy trì.

| Truy vấn | Filter/sort chủ yếu | Index đề xuất | Lý do |
| --- | --- | --- | --- |
| Q1 | `tenantId`, `orderNumber` | `{ tenantId: 1, orderNumber: 1 }` **unique** | Tìm nhanh và cưỡng chế mã đơn duy nhất trong tenant |
| Q2 | `tenantId`, `status`, sort `createdAt -1, _id -1` | `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }` | Equality ở đầu, tiếp theo là thứ tự kết quả ổn định |
| Q3 | `tenantId`, `customerId`, sort `createdAt -1, _id -1` | `{ tenantId: 1, customerId: 1, createdAt: -1, _id: -1 }` | Phân trang lịch sử trong phạm vi khách và tenant |
| Q4 | `tenantId` + `_id` | Index mặc định `_id` (kết hợp kiểm tra tenant ở query) | Truy vấn điểm theo ID, bảo vệ scope tenant ở tầng ứng dụng |
| Q5 | `tenantId`, `sku` | `{ tenantId: 1, sku: 1 }` **unique** trên `products` | Một SKU duy nhất trong tenant |
| Q6 | `tenantId`, `productId` | `{ tenantId: 1, productId: 1 }` **unique** trên `inventory` | Xác định đúng document để cập nhật tồn kho |
| Q7 | `tenantId`, `lines.productId` | `{ tenantId: 1, "lines.productId": 1 }` nếu cần | Multikey index khi cần tìm đơn chứa sản phẩm; chỉ tạo khi tần suất đủ lớn |

Không nhất thiết tạo ngay index cho Q7: nếu báo cáo chạy rất ít, có thể dùng một luồng phân tích riêng thay vì bổ sung một multikey index làm tăng chi phí ghi trên mọi đơn. Với nhiều truy vấn trên một collection, đánh giá **index prefix reuse** và chỉ giữ những index thực sự phục vụ workload.

### Tạo index bằng `mongosh`

~~~javascript
db.orders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  { unique: true, name: "uq_orders_tenant_number" }
);

db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_orders_tenant_status_recent" }
);

db.orders.createIndex(
  { tenantId: 1, customerId: 1, createdAt: -1, _id: -1 },
  { name: "idx_orders_tenant_customer_recent" }
);

db.products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uq_products_tenant_sku" }
);

db.inventory.createIndex(
  { tenantId: 1, productId: 1 },
  { unique: true, name: "uq_inventory_tenant_product" }
);

// Chỉ thêm khi truy vấn Q7 thực tế cần đến:
db.orders.createIndex(
  { tenantId: 1, "lines.productId": 1 },
  { name: "idx_orders_tenant_line_product" }
);
~~~

Trước khi tạo unique index trên dữ liệu cũ, phải kiểm tra và xử lý **duplicate**; index có thể không được tạo nếu collection đã vi phạm ràng buộc. Index cũng cần có quy trình triển khai riêng, tránh phụ thuộc hoàn toàn vào auto-index creation lúc nhiều pod Spring Boot khởi động. Với `@Indexed` hoặc `@CompoundIndex` trên entity, cần xác minh chính sách tạo index của ứng dụng; trên các phiên bản Spring Data MongoDB hiện đại, việc tự động tạo index không được bật mặc định.

### Tạo index thông qua `MongoTemplate`

Nếu cần quản lý bằng mã, một bước migration hoặc tác vụ khởi tạo có kiểm soát có thể dùng `IndexOperations`:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

public final class OrderIndexMigration {
    private final MongoTemplate mongo;

    public OrderIndexMigration(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public void ensureIndexes() {
        mongo.indexOps("orders").ensureIndex(
            new Index()
                .on("tenantId", Sort.Direction.ASC)
                .on("orderNumber", Sort.Direction.ASC)
                .unique()
                .named("uq_orders_tenant_number")
        );

        mongo.indexOps("orders").ensureIndex(
            new Index()
                .on("tenantId", Sort.Direction.ASC)
                .on("status", Sort.Direction.ASC)
                .on("createdAt", Sort.Direction.DESC)
                .on("_id", Sort.Direction.DESC)
                .named("idx_orders_tenant_status_recent")
        );
    }
}
~~~

Code chỉ minh họa **hai index của `orders`**; những index còn lại phải được khai báo tương tự khi triển khai. Trong dự án thực tế nên chạy migration có phiên bản một lần trong pipeline hoặc dưới cơ chế phối hợp được thiết kế, kiểm tra index hiện có và dữ liệu trùng trước khi áp dụng thay đổi. Không khởi tạo lại index tốn kém trong mỗi HTTP request.

## 8. Kiểm tra truy vấn Q1, Q2, Q3 bằng Spring Data

Với `MongoTemplate`, query điểm Q1 có thể dùng:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderLookupService {
    private final MongoTemplate mongo;

    public OrderLookupService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public OrderDocument findByBusinessNumber(String tenantId, String orderNumber) {
        Query q = Query.query(Criteria.where("tenantId").is(tenantId)
            .and("orderNumber").is(orderNumber));
        return mongo.findOne(q, OrderDocument.class, "orders");
    }
}
~~~

Đối với Q2, cách phân trang theo offset (`skip`) sẽ phải bỏ qua ngày càng nhiều kết quả ở trang sâu. Nếu giao diện chỉ cần “trang tiếp theo”, nên thử **keyset pagination** với `(createdAt, _id)` để bảo đảm thứ tự ổn định khi nhiều đơn cùng timestamp:

~~~javascript
// Trang đầu tiên
db.orders.find({ tenantId: "shop_01", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(30);

// Trang sau: cursor là (createdAt, _id) của document cuối trang trước.
db.orders.find({
  tenantId: "shop_01",
  status: "PAID",
  $or: [
    { createdAt: { $lt: ISODate("2026-11-19T08:00:00Z") } },
    {
      createdAt: ISODate("2026-11-19T08:00:00Z"),
      _id: { $lt: "ord_01K8X6RJH5TWA9KAMV7Z" }
    }
  ]
}).sort({ createdAt: -1, _id: -1 }).limit(30);
~~~

Cursor phải đến từ kết quả thật của trang trước, phải gắn với filter và sort đang dùng, và phải được xác thực nếu đưa qua API. Sự kiện thêm/xóa dữ liệu giữa các trang vẫn có thể làm tập kết quả thay đổi; cần nêu rõ ngữ nghĩa phân trang cho người dùng. Nếu `_id` là chuỗi, so sánh `$lt` dựa theo thứ tự BSON của chuỗi (và collation); đừng suy rằng thứ tự chuỗi ID phản ánh chính xác thời gian tạo. `_id` ở đây chỉ đóng vai trò **khóa phá hòa** khi `createdAt` bằng nhau.

Q3 tương tự Q2, nhưng thêm `customerId` vào điều kiện bằng và dùng index `{ tenantId, customerId, createdAt, _id }`. Khi sử dụng repository với method tên dài, nên kiểm tra filter, sort, projection thực tế mà Spring Data gửi xuống MongoDB, nhất là khi có `@Field`, `@Query` hoặc converters.

## 9. Cập nhật tồn kho Q6 một cách nguyên tử

Một lỗi phổ biến là đọc `available = 3`, kiểm tra còn hàng ở Java, rồi thực hiện `save` sau khi trừ 2. Hai request đồng thời đều có thể đọc 3 và cùng cho rằng đơn hợp lệ. Với tồn kho một sản phẩm, hãy chuyển điều kiện **còn đủ hàng** vào chính câu lệnh update trên một document.

Ví dụ dùng `MongoTemplate.findAndModify`:

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class InventoryService {
    private final MongoTemplate mongo;

    public InventoryService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public InventoryDocument reserve(String tenantId, String productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải lớn hơn 0");
        }

        Query q = Query.query(Criteria.where("tenantId").is(tenantId)
            .and("productId").is(productId)
            .and("available").gte(quantity));

        Update u = new Update()
            .inc("available", -quantity)
            .inc("reserved", quantity);

        InventoryDocument after = mongo.findAndModify(
            q, u, FindAndModifyOptions.options().returnNew(true),
            InventoryDocument.class, "inventory");

        if (after == null) {
            throw new IllegalStateException("Không tìm thấy tồn kho hoặc không đủ hàng");
        }
        return after;
    }
}
~~~

`InventoryDocument` là entity ánh xạ collection `inventory` từ phần 4. Trường `available` và `reserved` phải được khởi tạo đúng kiểu số trong MongoDB. Do filter và `$inc` nằm trong cùng thao tác cập nhật document, hai request cạnh tranh không thể cùng vượt qua điều kiện `available >= quantity` trên cùng một giá trị tồn kho cũ.

**Giới hạn của ví dụ:** đây là tính nguyên tử **của một document tồn kho**. Đặt đơn gồm nhiều sản phẩm đồng thời ghi `orders` và cập nhật nhiều document `inventory` là một quy trình lớn hơn. Nếu nghiệp vụ đòi tất cả bước cùng thành công hoặc cùng thất bại, cần transaction MongoDB trên replica set/sharded cluster phù hợp, `MongoTransactionManager` và xử lý retry/commit cẩn thận; hoặc một saga/luồng reservation có bù trừ được thiết kế rõ. Không giả định vài lệnh `findAndModify` liên tiếp tự tạo thành giao dịch.

## 10. Quy tắc nhất quán và vòng đời tham chiếu

Tách collection khiến một số invariant phải được bảo vệ ở tầng ứng dụng:

| Quy tắc | Cách bảo vệ |
| --- | --- |
| Đơn chỉ chứa sản phẩm của cùng tenant | Query product theo **cả** `_id` và `tenantId` trước khi chụp snapshot |
| Khách hàng thuộc đúng tenant | Xác minh `(tenantId, customerId)` trong cùng bối cảnh ủy quyền |
| Không bán vượt số lượng | Atomic conditional update/transaction hoặc workflow reservation có bù trừ |
| Mỗi `orderNumber` duy nhất trong tenant | Unique index `(tenantId, orderNumber)` làm chốt chặn cuối cùng |
| Giá/tên đã mua không đổi theo catalog | Snapshot `nameAtPurchase`, `unitPriceMinor` trong `lines` |
| Tổng tiền đúng | Kiểm tra `quantity > 0`, giá không âm, currency nhất quán, dùng toán học nguyên/decimal và kiểm tra overflow |
| Không phát sinh đơn trùng khi retry request | Dùng `idempotencyKey` với unique index phù hợp hoặc khóa yêu cầu ổn định, kèm cách trả lại kết quả cũ |
| Lịch sử đơn còn đọc được sau khi xóa sản phẩm | Giữ snapshot trong order và xác định chính sách xóa mềm với product |

`@DBRef` hoặc `@DocumentReference` chỉ mô tả cơ chế truy xuất reference, **không thay thế** unique index, quyền truy cập tenant hay quy tắc transaction. Nếu có xóa customer vì yêu cầu dữ liệu cá nhân, phải cân bằng yêu cầu ẩn/xóa thông tin liên hệ với nghĩa vụ giữ chứng từ giao dịch; thiết kế snapshot tối thiểu và chính sách lưu giữ phù hợp.

### Partial, TTL và multikey index: dùng đúng mục đích

- **Partial index**: hữu ích cho các trường tùy chọn, ví dụ `externalOrderId` chỉ có ở một số đơn. Unique index thông thường trên trường tùy chọn có thể tạo bất ngờ với giá trị thiếu hoặc `null`; cần dùng partial filter đúng điều kiện và kiểm thử dữ liệu lịch sử.
- **TTL index**: phù hợp dữ liệu tự hết hạn như session hoặc token tạm, nhưng không nên dùng tùy tiện trên `orders` phải giữ lịch sử. Việc xóa bởi TTL không diễn ra chính xác tại thời điểm hết hạn; hệ thống vẫn phải xử lý thời gian hết hiệu lực ở tầng nghiệp vụ.
- **Multikey index**: được dùng khi index field trong mảng, như `lines.productId`. Một document có nhiều dòng làm index chứa nhiều entry; kiểm tra giới hạn multikey và không tạo tràn lan chỉ để hỗ trợ báo cáo ít chạy.
- **Collation**: truy vấn và index có quy tắc so sánh/chữ hoa chữ thường khác nhau có thể cho kết quả hoặc lựa chọn plan khác dự kiến. Chuẩn hóa `emailNormalized`/SKU theo hợp đồng dữ liệu, và kiểm thử collation thực dùng nếu cần so sánh theo ngôn ngữ.

## 11. Dùng `explain("executionStats")` để xác nhận index

Một index nhìn có vẻ đúng trên giấy vẫn có thể không hiệu quả với phân bố dữ liệu thật. Sau khi tạo index và nhập bộ dữ liệu thử, chạy `explain` cho Q2:

~~~javascript
db.orders.find({ tenantId: "shop_01", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(30)
  .explain("executionStats");
~~~

Các chỉ số cần ghi lại:

| Chỉ số | Điều cần xem |
| --- | --- |
| `winningPlan` / `indexName` | Có sử dụng `idx_orders_tenant_status_recent` hoặc index thực sự phù hợp không? |
| `COLLSCAN` / `IXSCAN` | Quét toàn collection hay giới hạn theo index? |
| `SORT` | Có sort tốn bộ nhớ ngoài thứ tự index không? |
| `nReturned` | Trả tối đa 30 document như yêu cầu chưa? |
| `totalKeysExamined` | Số index key đã duyệt có hợp lý so với kết quả không? |
| `totalDocsExamined` | Có phải đọc rất nhiều document để trả vài đơn không? |
| `executionTimeMillis` | Thời gian thực thi do `explain` đo; so sánh dưới điều kiện tương đương |

Một kết quả tốt với Q2 thường là vùng index quét hẹp theo `(tenantId, status)` và thứ tự `createdAt, _id` hỗ trợ sort, nhưng không có cam kết tuyệt đối về số key đọc. MongoDB có nhiều execution engine và hình dạng plan khác nhau tùy phiên bản; đừng kiểm tra bằng việc so khớp cứng một đường dẫn JSON `winningPlan.inputStage`.

Thử thêm dữ liệu có phân bố tenant/status không đều, sau đó so sánh plan. Dùng `explain` để hiểu chi phí tại database, rồi đo thêm latency p95/p99 của API Spring Data MongoDB, ảnh hưởng tới insert/update, kích thước index và tải hệ thống. Thêm index chỉ vì một lần `explain` chậm trên tập dữ liệu vài dòng có thể làm hệ thống ghi chậm hơn mà không đem lại lợi ích thực.

## 12. Bộ bài tập kiểm chứng

Thực hiện các bài kiểm tra trên MongoDB phục vụ kiểm thử. Với thao tác transaction đa document, dùng replica set hoặc sharded cluster có hỗ trợ transaction; môi trường MongoDB standalone không tương đương.

| Bài kiểm tra | Dữ liệu/điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| A. Unique theo tenant | Hai order cùng `(shop_01, SO-01)` | Lệnh thứ hai gặp duplicate key |
| B. Cùng mã ở tenant khác | `(shop_01, SO-01)` và `(shop_02, SO-01)` | Cả hai được tạo thành công |
| C. Giá sản phẩm đổi | Tạo đơn rồi sửa `products.currentPriceMinor` | Snapshot đơn vẫn lưu giá lúc đặt |
| D. Product bị vô hiệu hóa | Product `active=false`, order cũ có snapshot | Đọc được lịch sử đơn; logic đặt đơn mới từ chối product không hợp lệ |
| E. Mảng dòng hàng bị giới hạn | Gửi đơn vượt 100 lines | Ứng dụng từ chối theo quy tắc đầu vào; không để document phình vô hạn |
| F. Hai request giữ cùng tồn kho | `available=3`, hai request đặt 2 sản phẩm cùng lúc | Chỉ một request giữ hàng thành công |
| G. Cập nhật nhiều document bị lỗi | Một mặt hàng hết kho giữa quy trình đặt đơn | Transaction rollback hoặc bù trừ giữ invariant theo kiến trúc đã chọn |
| H. Query Q2 phân trang | Nhiều đơn trùng `createdAt` | Không bỏ sót/trùng do thứ tự không ổn định trong dữ liệu không đổi |
| I. Chặn cross-tenant | Gọi `orderId` của tenant khác | Không đọc được đơn ngoài tenant theo quyền người dùng |
| J. Hiệu năng | Nhiều order, tenant/status phân bố lệch | `explain` sử dụng index có ích; không phát sinh quét/sort quá mức |

Ngoài kiểm tra đúng dữ liệu, cần thử **sự cố khi viết**: exception do unique index, timeout sau khi ghi thành công nhưng client không nhận phản hồi, retry của request cũ và lỗi cập nhật cạnh tranh. Nếu có `@Version`, kiểm chứng không ghi đè được một document đã đổi phiên bản qua `save` được Spring Data quản lý.

## 13. Những phương án thường sai trong bài tập

| Phương án | Hệ quả | Thiết kế phù hợp hơn |
| --- | --- | --- |
| Nhúng tất cả đơn vào `customers.orders[]` | Mảng tăng vô hạn, document lớn, cập nhật/truy vấn tốn tài nguyên | Collection `orders` riêng, index theo `tenantId`/`customerId` |
| Chỉ lưu `productId` trong `OrderLine` và đọc giá hiện tại | Giá lịch sử thay đổi khi product đổi giá | Nhúng snapshot tên/giá tại thời điểm mua |
| Copy toàn bộ product vào mọi order | Document dư thừa, lộ field không cần thiết, khó bảo vệ dữ liệu | Snapshot tối thiểu phục vụ chứng từ và xử lý đơn |
| Dùng `orderNumber` làm `_id` nhưng chỉ duy nhất theo tenant | Xung đột giữa tenant hoặc phải tự mã hóa tenant vào khóa | `_id` riêng; unique index `(tenantId, orderNumber)` |
| Query chỉ theo `_id`, bỏ kiểm tra tenant | Có nguy cơ lộ dữ liệu giữa các cửa hàng | Ràng buộc tenant trong truy vấn hoặc ở biên phân quyền có kiểm chứng |
| Thêm index riêng lẻ cho từng field rồi hy vọng sort nhanh | MongoDB vẫn có thể quét rộng hoặc sort ngoài index | Thiết kế compound index theo filter + sort thực tế |
| Đếm tồn kho ở Java rồi `save` | Lost update/bán vượt khi có cạnh tranh | Atomic conditional update hoặc transaction phù hợp |
| Tạo unique index khi dữ liệu cũ đã trùng | Lệnh tạo index thất bại | Kiểm tra, làm sạch dữ liệu, rồi triển khai index có phiên bản |

## 14. Checklist hoàn thành capstone

Trước khi coi thiết kế đạt yêu cầu, tự đối chiếu:

1. Mỗi collection có **lý do tồn tại** dựa trên vòng đời và tần suất đọc/ghi; mảng nhúng có giới hạn và không vượt khả năng mở rộng document.
2. Mỗi reference có quy tắc **tenant scope**, xác minh tồn tại và chính sách khi document đích được xóa hoặc thay đổi.
3. `_id` có kiểu BSON ổn định; mã nghiệp vụ và các khóa tự nhiên được bảo vệ bằng unique index khi cần.
4. Mỗi index đã được gắn với một hoặc nhiều **query shape cụ thể**, gồm điều kiện lọc, sort, projection, collation và tần suất gọi.
5. `orders` giữ snapshot tên/giá sản phẩm; cập nhật catalog không làm đổi lịch sử đơn đã chốt.
6. Tồn kho được cập nhật bằng điều kiện nguyên tử; quy trình nhiều sản phẩm/document có cách đảm bảo nhất quán được lựa chọn rõ.
7. Các truy vấn đi qua `MongoTemplate` hoặc repository được kiểm tra trên BSON thực tế, có thử `explain("executionStats")` và đo tải phù hợp.
8. Bộ test xác minh ràng buộc unique, cross-tenant, pagination, concurrency, retry/idempotency và khả năng đọc dữ liệu cũ.

**Kết quả của bài thực hành** không phải một sơ đồ có nhiều collection hay nhiều index nhất. Một thiết kế tốt là thiết kế mà mỗi lần nhúng dữ liệu, mỗi reference, mỗi ID và mỗi index đều có thể giải thích bằng **truy vấn cần phục vụ, quy tắc nhất quán và chi phí vận hành**. Khi các giả định về số dòng hàng, số tenant, tần suất đọc/ghi hoặc báo cáo thay đổi, hãy đo lại và điều chỉnh mô hình thay vì xem cấu trúc ban đầu là bất biến.
