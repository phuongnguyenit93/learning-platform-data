# Nhúng dữ liệu so với tham chiếu bằng khóa tài liệu trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **nhúng dữ liệu (embedding)** với **tham chiếu bằng document key (referencing)** trong Couchbase.
2. Chọn cách lưu phù hợp theo **vòng đời dữ liệu, bất biến nghiệp vụ, tần suất đọc/ghi, kích thước và mức độ dùng chung**.
3. Xây dựng document vừa chứa dữ liệu lồng nhau vừa lưu khóa của document khác, ánh xạ bằng Spring Data Couchbase.
4. Thiết kế cách lấy dữ liệu liên quan qua **Key-Value (KV)**, repository, `CouchbaseTemplate` và **SQL++ JOIN ON KEYS**.
5. Giải quyết các vấn đề thực tế: **ảnh chụp lịch sử, tham chiếu bị mất, CAS, giao dịch đa document, TTL, N+1 và chỉ mục**.

Chủ đề thuộc chương **Mô hình tài liệu** của module **SPRING_DATA_COUCHBASE**. Spring Data Couchbase giúp ánh xạ Java object sang JSON, truy cập bằng repository và `CouchbaseTemplate`, hoặc truy vấn SQL++. Tuy vậy, framework không tự quyết định quan hệ nào nên nhúng và quan hệ nào nên tham chiếu: quyết định đó phải bắt đầu từ miền nghiệp vụ và mẫu truy cập thực tế.

## 1. Hai cách biểu diễn quan hệ dữ liệu

Giả sử ứng dụng bán hàng có `Order`, `Customer`, `Product` và `OrderLine`.

**Nhúng** nghĩa là ghi dữ liệu con vào **JSON body của chính document gốc**:

~~~json
{
  "status": "CONFIRMED",
  "shipping_address": {
    "recipient": "Minh",
    "city": "Hồ Chí Minh",
    "detail": "Số 10, đường A"
  },
  "lines": [
    {
      "productId": "product::coffee250",
      "productNameAtPurchase": "Cà phê 250 g",
      "unitPriceVnd": 150000,
      "quantity": 2
    }
  ]
}
~~~

`shipping_address` và các phần tử `lines` nằm **trong cùng document Order**; chúng không tự có document key, CAS hoặc TTL độc lập.

**Tham chiếu bằng khóa** nghĩa là document chỉ lưu key của document khác:

~~~json
{
  "customerId": "customer::u100",
  "lines": [
    {"productId": "product::coffee250", "quantity": 2}
  ]
}
~~~

Một Product riêng có key `product::coffee250`:

~~~json
{
  "display_name": "Cà phê 250 g",
  "current_price_vnd": 165000,
  "active": true
}
~~~

Ở cách thứ hai, `productId` chỉ là một **chuỗi trong JSON**. Couchbase không tự xem chuỗi đó là foreign key có ràng buộc, và Spring Data Couchbase không tự tải Product khi đọc Order. Ứng dụng quyết định có đọc thêm document đích hay không.

~~~mermaid
flowchart LR
    O["Order document"] -->|nhúng| A["ShippingAddress"]
    O -->|nhúng| L["OrderLine array"]
    O -.->|customerId| C["Customer document"]
    L -.->|productId| P["Product document"]
~~~

**Câu hỏi trọng tâm:** dữ liệu có cần nằm trong cùng đơn vị cập nhật nguyên tử và thường được đọc cùng nhau không, hay cần tồn tại và được sửa độc lập?

## 2. Đơn vị nguyên tử và giới hạn của embedding

Một mutation trên **một document Couchbase** là nguyên tử. Nếu Order lưu các dòng hàng và tổng tiền trong cùng body, một lần ghi thành công có thể lưu các thay đổi đó như một trạng thái document thống nhất. Còn khi Order và Inventory là hai document khác nhau, hai lệnh `save` độc lập **không tạo thành một transaction nguyên tử**.

Khái niệm **aggregate** trong Domain-Driven Design giúp chọn ranh giới: aggregate root bảo vệ những điều kiện phải luôn đúng (*invariants*). Dữ liệu con có cùng vòng đời và được thay đổi qua root là ứng viên tốt để nhúng. Tuy nhiên, **aggregate là ranh giới nghiệp vụ, document là đơn vị lưu trữ**; chúng thường có thể khớp nhau nhưng không mặc nhiên là một.

| Tiêu chí | Nhúng trong document gốc | Tham chiếu bằng document key |
| --- | --- | --- |
| Đọc dữ liệu liên quan | Một lần đọc root thường đã đủ | Thường cần đọc thêm key hoặc truy vấn JOIN |
| Ghi nhiều trường liên quan | Có thể cùng một mutation document | Cần phối hợp nhiều document nếu cùng thay đổi |
| Vòng đời | Gắn với root | Có thể độc lập |
| Dữ liệu dùng chung | Có thể bị nhân bản ở nhiều root | Một document nguồn có thể được nhiều nơi tham chiếu |
| Thay đổi dữ liệu nguồn | Bản nhúng chỉ thay đổi nếu được ghi lại | Lần đọc document nguồn có thể thấy giá trị mới |
| Tăng trưởng dữ liệu | Làm phình document gốc | Tăng số document, root thường nhỏ |
| Tranh chấp ghi | Nhiều tác nhân sửa cùng root có thể xung đột CAS | Writer của các document tách biệt ít đụng cùng CAS |
| TTL | Cùng TTL của root | Mỗi document có expiry riêng |
| Truy vấn liên quan | Đọc qua đường dẫn JSON, array index khi cần | KV lấy theo key hoặc SQL++ JOIN ON KEYS |

Đừng chọn theo ý nghĩ “NoSQL luôn nhúng” hoặc “chuẩn hóa dữ liệu luôn tốt hơn”. Couchbase hỗ trợ **cả hai**, thậm chí dùng đồng thời trong một document.

## 3. Quy trình quyết định embed hay reference

Trước khi tạo class Java, liệt kê **các thao tác thực tế**. Ví dụ:

| Mẫu truy cập | Dữ liệu cần | Gợi ý ban đầu |
| --- | --- | --- |
| Xem chi tiết đơn đã chốt | Order, danh sách dòng, địa chỉ giao lúc mua, số tiền | Nhúng các giá trị đã chốt vào Order |
| Xem thông tin khách hàng hiện tại | Customer và thông tin liên hệ mới nhất | Tham chiếu `customerId` |
| Xem tên/giá Product trong catalog | Product hiện hành | Document Product độc lập |
| Chốt giá đơn hàng | Giá và tên tại thời điểm mua | Nhúng **snapshot** trong OrderLine |
| Ghi nhận thay đổi tồn kho | Số lượng khả dụng của Product | Inventory là document/aggregate riêng |
| Danh sách đánh giá sản phẩm | Có thể rất nhiều Review | Review riêng, lọc theo `productId` |
| Báo cáo đơn theo khách | Nhiều Order theo `customerId`, có phân trang | Order riêng, index theo customerId/thời gian |

Sau khi liệt kê workload, áp dụng các câu hỏi theo thứ tự:

1. **Tính nhất quán:** các field có phải thay đổi cùng nhau để giữ bất biến không? Nếu có, ưu tiên cùng aggregate và cân nhắc cùng document.
2. **Vòng đời:** thành phần con có còn ý nghĩa khi root bị xóa không, và có ai cập nhật nó độc lập không?
3. **Mức độ đọc cùng:** màn hình có thường cần cả root và dữ liệu con không? Bao nhiêu lượt KV/SQL++ sẽ tiết kiệm được khi nhúng?
4. **Giới hạn tăng trưởng:** mảng/object có số phần tử tối đa đáng tin cậy không? Document có thể lớn đến mức tốn băng thông hoặc gần giới hạn kích thước không?
5. **Mức độ dùng chung:** một thông tin có được nhiều root cùng tham chiếu không? Nếu sao chép, ai chịu trách nhiệm đồng bộ?
6. **Cạnh tranh ghi:** nhiều request có đồng thời sửa những phần khác nhau của cùng document không? Embedding có tạo **hot document** không?
7. **Lịch sử và tính mới:** cần bản chụp tại thời điểm giao dịch hay giá trị mới nhất ở nguồn? Hai yêu cầu này đôi khi phải lưu cả snapshot lẫn reference.
8. **Retention/TTL:** dữ liệu con có thời hạn sống, quyền truy cập hoặc chính sách xóa khác root không?

**Quy tắc thực hành:** nhúng **dữ liệu con hữu hạn và thuộc cùng vòng đời**; tham chiếu **thực thể độc lập, dùng chung hoặc có tăng trưởng/ghi lớn**. Quy tắc này là điểm khởi đầu, phải kiểm chứng bằng số liệu.

## 4. Trường hợp cần nhúng: value object, dòng hàng và snapshot

### 4.1. Value object được đọc và ghi cùng root

Địa chỉ giao hàng đã chốt của một Order thường được nhúng:

~~~json
{
  "shipping_address": {
    "recipient": "Minh",
    "phone_last4": "1234",
    "city": "Hồ Chí Minh",
    "detail": "Số 10, đường A"
  }
}
~~~

Địa chỉ giao hàng của **đơn đã chốt** là một sự kiện lịch sử. Khi khách đổi địa chỉ mặc định trên hồ sơ, đơn cũ vẫn cần giữ nơi giao đã xác nhận. Vì vậy, thay vì chỉ tham chiếu `customer.addressId`, Order có thể giữ snapshot phù hợp với nghiệp vụ, đồng thời lưu `customerId` để tra cứu hồ sơ khách hiện hành khi cần.

Một đối tượng `ShippingAddress` lồng trong Order không cần `@Document`, `@Id` hay repository riêng nếu nó chỉ sống cùng Order.

### 4.2. Dòng hàng thường là thành phần của Order

Giả sử mỗi đơn có tối đa 50 dòng, và khi thay đổi dòng, tổng tiền cần đồng bộ. Nhúng `List<OrderLine>` thường hợp lý:

~~~json
{
  "lines": [
    {
      "productId": "product::coffee250",
      "productNameAtPurchase": "Cà phê 250 g",
      "unitPriceVnd": 150000,
      "quantity": 2
    },
    {
      "productId": "product::cup01",
      "productNameAtPurchase": "Ly sứ",
      "unitPriceVnd": 50000,
      "quantity": 1
    }
  ],
  "total_amount_vnd": 350000
}
~~~

`productId` vẫn là **tham chiếu tới Product hiện tại**, nhưng `productNameAtPurchase` và `unitPriceVnd` là **snapshot đã chốt**. Khi catalog thay tên hoặc tăng giá, dữ liệu đơn cũ không bị thay đổi vô ý. Điều này minh họa **nhúng và tham chiếu hoàn toàn có thể kết hợp**.

### 4.3. Snapshot không phải bản sao cần đồng bộ mãi

Cần phân loại rõ từng field được nhân bản:

- **Snapshot lịch sử:** giá lúc mua, tên hàng ghi trên hóa đơn, địa chỉ giao lúc chốt. Chủ ý **không cập nhật** khi dữ liệu nguồn thay đổi.
- **Bản sao phục vụ đọc (denormalized read copy):** tên khách hiện hành hiển thị ở danh sách đơn. Có thể phải cập nhật theo sự kiện, chấp nhận độ trễ hoặc đọc trực tiếp từ Customer.
- **Nguồn sự thật:** Product giữ giá hiện hành; Inventory giữ lượng tồn; Customer giữ thông tin hồ sơ. Nếu nhiều nơi đều được sửa tùy ý, dễ phát sinh dữ liệu mâu thuẫn.

Việc đặt tên field có hậu tố `AtPurchase`, `AtCheckout` hoặc `Snapshot` giúp diễn đạt chính sách; đây là quy ước ứng dụng, không phải annotation Couchbase.

## 5. Trường hợp cần tham chiếu: thực thể độc lập, dùng chung, tăng trưởng lớn

### 5.1. Product và Customer

Catalog Product có vòng đời và quy tắc chỉnh sửa độc lập với Order. Một Product có thể được hàng nghìn Order tham chiếu; không hợp lý nếu mọi thay đổi giá hiện hành buộc cập nhật toàn bộ Order. Tương tự, Customer có nhiều Order và quản lý quyền truy cập, chính sách xóa/thông tin cá nhân riêng.

Document Order vì vậy có thể lưu:

~~~json
{
  "customerId": "customer::u100",
  "lines": [
    {"productId": "product::coffee250", "quantity": 2}
  ]
}
~~~

**Không có foreign key tự động:** Couchbase không chặn bạn lưu `customerId` sai hoặc trỏ tới document đã bị xóa. Ứng dụng phải chọn một trong các cách xử lý: kiểm tra tồn tại khi ghi, lưu snapshot đủ cho lịch sử, **soft-delete** thực thể nguồn, hiển thị “không còn tồn tại”, hoặc có quy trình dọn tham chiếu.

### 5.2. Review, sự kiện và dữ liệu không có giới hạn trên

Một Product có thể có rất nhiều Review. Nếu nhúng mọi Review vào mảng `product.reviews`:

- Kích thước document tăng theo số Review.
- Mỗi lần đọc Product phải xử lý body lớn dù màn hình chỉ cần tên/giá.
- Nhiều người đánh giá đồng thời dễ cùng ghi vào một document, tạo xung đột CAS.
- Phân trang, giữ/xóa đánh giá và kiểm soát quyền sửa riêng khó hơn.

Nên lưu `Review` thành document riêng với `productId` là field tham chiếu, thiết kế index theo `productId`, thời gian và trạng thái duyệt. Có thể lưu **tóm tắt** như số lượng/rating trung bình trong Product dưới dạng read model, nhưng phải quy định cơ chế tính lại và chấp nhận độ trễ.

### 5.3. Inventory và các workflow cạnh tranh ghi

Inventory cần bảo vệ invariant không bán vượt số lượng khả dụng, thường được nhiều đơn cập nhật đồng thời. Nếu nhúng tồn kho vào Product hay Order, nhiều luồng sẽ cùng sửa một root không phù hợp. Tách aggregate/document Inventory cho phép tối ưu đường ghi riêng; phối hợp với Order có thể dùng transaction đa document hoặc reservation/workflow bù tùy yêu cầu.

**Không tách chỉ vì có quan hệ tham chiếu:** một `OrderLine` luôn được sửa cùng Order, không có vòng đời riêng và số lượng hữu hạn vẫn có thể nhúng dù nó chứa `productId`.

## 6. Thiết kế document key và nơi lưu

Couchbase tổ chức dữ liệu bằng **bucket, scope, collection**. Document key là duy nhất **trong collection**; key giống nhau có thể tồn tại ở các collection khác. Ví dụ minh họa dưới cùng bucket `shop`:

| Keyspace | Document key | Chức năng |
| --- | --- | --- |
| `shop.sales.orders` | `order::2026::00125` | Root Order với các giá trị con |
| `shop.crm.customers` | `customer::u100` | Hồ sơ khách hàng |
| `shop.catalog.products` | `product::coffee250` | Thông tin sản phẩm hiện tại |
| `shop.catalog.reviews` | `review::01J...` | Review độc lập, có `productId` |
| `shop.stock.inventory` | `stock::coffee250` | Số lượng và reservation theo thiết kế |

Các key trên chỉ là quy ước ví dụ. Có thể dùng UUID/ULID hoặc khóa miền đã chuẩn hóa; chọn ID **ổn định**, đủ duy nhất, tránh chứa bí mật hoặc dữ liệu nhạy cảm, không đổi theo tên hiển thị. Khi tham chiếu giữa collection, biết **key thôi chưa đủ** nếu ứng dụng không biết collection của đích; phải quy định nơi tra cứu hoặc lưu thêm kiểu/thông tin định tuyến khi thực sự cần.

Cần phân biệt:

- **Document key:** được truy cập bằng `@Id` và KV.
- **Field tham chiếu:** như `customerId` hay `productId` nằm trong JSON; không biến thành liên kết bắt buộc chỉ vì chứa chuỗi trông giống key.
- **Đường dẫn SQL++:** dùng đúng `bucket.scope.collection` và tên field thực tế khi truy vấn.

Không dùng `@Id` cho mỗi `OrderLine` lồng trong Order nếu không chủ định lưu riêng một document. Một phần tử trong mảng có thể có `lineId` **nghiệp vụ** để sửa đúng phần tử, nhưng `lineId` đó không trở thành Couchbase document key độc lập.

## 7. Ánh xạ bằng Spring Data Couchbase

Ví dụ sau ánh xạ **Order là root**, **ShippingAddress và OrderLine được nhúng**, **Customer và Product được tham chiếu bằng chuỗi ID**. Bucket `shop` được cấu hình từ kết nối; annotation scope/collection chọn nơi lưu entity.

### 7.1. Entity Order.java

~~~java
package com.example.shop.sales;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class Order {

    @Id
    private String id;

    @Version
    private Long version;

    @Field
    private String customerId;  // document key của Customer, không tự JOIN

    @Field("shipping_address")
    private ShippingAddress shippingAddress;

    @Field
    private List<OrderLine> lines = new ArrayList<>();

    @Field("total_amount_vnd")
    private long totalAmountVnd;

    @Field
    private String status = "DRAFT";

    @Field
    private Instant createdAt;

    protected Order() {}

    public Order(String id, String customerId, ShippingAddress address) {
        if (id == null || id.isBlank() ||
                customerId == null || customerId.isBlank() || address == null) {
            throw new IllegalArgumentException("Thiếu thông tin đơn hàng");
        }
        this.id = id;
        this.customerId = customerId;
        this.shippingAddress = address;
        this.createdAt = Instant.now();
    }

    public void addLine(OrderLine line) {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException("Không thể sửa đơn đã chốt");
        }
        if (line == null || lines.size() >= 50) {
            throw new IllegalArgumentException("Dòng hàng không hợp lệ");
        }
        long lineTotal = Math.multiplyExact(
            line.getUnitPriceVnd(), line.getQuantity()
        );
        lines.add(line);
        totalAmountVnd = Math.addExact(totalAmountVnd, lineTotal);
    }

    public String getId() { return id; }
    public String getCustomerId() { return customerId; }
    public long getTotalAmountVnd() { return totalAmountVnd; }
    public List<OrderLine> getLines() { return List.copyOf(lines); }
}
~~~

`@Version` giữ CAS metadata để Spring Data phát hiện ghi đồng thời. `@Id` giữ document key; `@Field` điều khiển JSON body. `customerId` được lưu như chuỗi bình thường, nên việc load Order không tự gọi repository Customer.

### 7.2. Các value object được nhúng

~~~java
package com.example.shop.sales;

import org.springframework.data.couchbase.core.mapping.Field;

public class ShippingAddress {
    @Field
    private String recipient;

    @Field
    private String city;

    @Field
    private String detail;

    protected ShippingAddress() {}

    public ShippingAddress(String recipient, String city, String detail) {
        if (recipient == null || recipient.isBlank() ||
                city == null || city.isBlank() ||
                detail == null || detail.isBlank()) {
            throw new IllegalArgumentException("Địa chỉ không hợp lệ");
        }
        this.recipient = recipient;
        this.city = city;
        this.detail = detail;
    }
}

public class OrderLine {
    @Field
    private String productId;

    @Field
    private String productNameAtPurchase;

    @Field
    private long unitPriceVnd;

    @Field
    private int quantity;

    protected OrderLine() {}

    public OrderLine(
            String productId, String productNameAtPurchase,
            long unitPriceVnd, int quantity) {
        if (productId == null || productId.isBlank() ||
                productNameAtPurchase == null ||
                productNameAtPurchase.isBlank() ||
                unitPriceVnd < 0 || quantity <= 0) {
            throw new IllegalArgumentException("Dòng hàng không hợp lệ");
        }
        this.productId = productId;
        this.productNameAtPurchase = productNameAtPurchase;
        this.unitPriceVnd = unitPriceVnd;
        this.quantity = quantity;
    }

    public long getUnitPriceVnd() { return unitPriceVnd; }
    public int getQuantity() { return quantity; }
    public String getProductId() { return productId; }
}
~~~

Trong dự án Java thật, đặt hai lớp `public` trên vào **hai tệp `.java` tương ứng**. Có thể dùng record/immutable value object nếu phiên bản mapper xử lý được constructor; nên xác minh vòng ghi–đọc trên Couchbase thật.

### 7.3. Document JSON của Order

Một đơn hai dòng được lưu dưới key `order::2026::00125` trong `shop.sales.orders`:

~~~json
{
  "_class": "com.example.shop.sales.Order",
  "customerId": "customer::u100",
  "shipping_address": {
    "recipient": "Minh",
    "city": "Hồ Chí Minh",
    "detail": "Số 10, đường A"
  },
  "lines": [
    {
      "productId": "product::coffee250",
      "productNameAtPurchase": "Cà phê 250 g",
      "unitPriceVnd": 150000,
      "quantity": 2
    },
    {
      "productId": "product::cup01",
      "productNameAtPurchase": "Ly sứ",
      "unitPriceVnd": 50000,
      "quantity": 1
    }
  ],
  "total_amount_vnd": 350000,
  "status": "CONFIRMED",
  "createdAt": "2026-11-25T02:00:00Z"
}
~~~

`_class` có thể được thêm bởi mapping mặc định để nhận biết loại entity, tùy cấu hình. `id` và `version` là key/CAS metadata, không cần nằm trong body. `ShippingAddress` và `OrderLine` là các object JSON con, trong khi `customerId`/`productId` trỏ đến document độc lập.

## 8. Repository: load root trước, tham chiếu khi thật sự cần

Khai báo repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository extends CouchbaseRepository<Order, String> {
}

public interface ProductRepository extends CouchbaseRepository<Product, String> {
}
~~~

`Product` ở đây là một entity riêng được ánh xạ đến `shop.catalog.products`, có `@Id`, `displayName`, `currentPriceVnd` và các getter tương ứng.

### Đọc Order khi biết key

~~~java
Order order = orderRepository.findById("order::2026::00125")
    .orElseThrow();
~~~

Đây thường là truy cập **KV theo ID**, không đòi secondary index trên `customerId` hoặc `lines.productId`. Các object lồng trong Order được ánh xạ cùng với root. Trường chuỗi `customerId` vẫn chỉ chứa key.

### Đọc Product để tạo snapshot đúng thời điểm

Ví dụ service thêm dòng dựa trên Product hiện tại:

~~~java
public Order addProduct(
        String orderId, String productId, int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("Số lượng phải dương");
    }

    Product product = productRepository.findById(productId)
        .orElseThrow(() ->
            new IllegalArgumentException("Không tìm thấy Product")
        );

    Order order = orderRepository.findById(orderId)
        .orElseThrow(() ->
            new IllegalArgumentException("Không tìm thấy Order")
        );

    order.addLine(new OrderLine(
        productId,
        product.getDisplayName(),
        product.getCurrentPriceVnd(),
        quantity
    ));
    return orderRepository.save(order);
}
~~~

Trong code trên, lấy Product theo key để tạo **snapshot** trong OrderLine. `save(order)` không tự lưu Product và cũng không tạo transaction với Product. Giá có thể bị sửa trong catalog ngay sau khi đọc; hệ thống thật phải xác định thời điểm khóa giá, chính sách xác nhận lại giá khi checkout và cách xử lý thay đổi đồng thời.

**Không giả định reference là quan hệ ORM tự động:** thêm `Product product` làm field trong Order có thể khiến mapper **nhúng object Product** vào JSON, trừ khi bạn chủ động xây cơ chế reference riêng. Với cách lưu key, hãy khai báo `String productId` rõ ràng và nạp Product ở service/read model khi cần.

## 9. Truy xuất dữ liệu tham chiếu: KV, SQL++ và tránh N+1

### 9.1. Lấy từng document theo key

Khi mở chi tiết Order, có thể chỉ cần snapshot của dòng hàng, hoàn toàn không phải đọc Product. Khi màn hình cần trạng thái còn bán của Product, service có thể lấy các `productId` cần thiết từ Order và gọi repository/SDK KV.

Nếu tải danh sách 20 đơn, mỗi đơn 10 dòng, việc gọi KV tuần tự cho 200 tham chiếu có thể gây **N+1 reads** và độ trễ lớn. Cách giảm chi phí:

- Chỉ tải Product khi màn hình cần dữ liệu hiện tại.
- Loại khóa trùng (`distinct productId`) để tránh tải cùng Product nhiều lần.
- Dùng truy cập đồng thời **có giới hạn** hoặc cơ chế đa truy xuất KV phù hợp ở SDK; không mở vô hạn request.
- Cache thông tin catalog có chính sách hết hạn, invalidation và quyền truy cập rõ ràng.
- Khi cần hàng loạt kết quả theo filter, cân nhắc SQL++/read model thay vì chuỗi gọi KV nhỏ.

Reactive repository/template có thể hỗ trợ tổ chức I/O không chặn và giới hạn concurrency, nhưng **không giảm số document bắt buộc phải đọc** hay tự giải quyết consistency.

### 9.2. JOIN ON KEYS qua các collection

Couchbase SQL++ có **lookup JOIN** bằng document key. Giả sử `shop.sales.orders` và `shop.crm.customers` thuộc những collection mà tài khoản truy vấn có quyền:

~~~sql
SELECT META(o).id AS orderId,
       o.status,
       o.total_amount_vnd AS totalAmountVnd,
       c.full_name AS currentCustomerName
FROM `shop`.`sales`.`orders` AS o
USE KEYS $orderId
LEFT JOIN `shop`.`crm`.`customers` AS c
ON KEYS o.customerId;
~~~

- `USE KEYS $orderId` chọn Order gốc theo key đã biết.
- `LEFT JOIN ... ON KEYS o.customerId` tra cứu Customer bằng key được lưu trong Order.
- `LEFT JOIN` giữ hàng Order kể cả khi Customer bị thiếu; `currentCustomerName` khi đó có thể không có giá trị.
- Kết quả là **projection cho việc đọc**; không mặc nhiên thành entity `Order` đầy đủ. Nếu viết `@Query` của Spring Data để materialize entity, phải chọn đúng field và metadata ID/type mà mapper yêu cầu.

JOIN có thể tiện nhưng không miễn phí: server vẫn cần tra cứu document đích, quyền truy cập các collection và bộ nhớ/CPU thực thi query. Với những thao tác chỉ có một ID đã biết, KV trực tiếp thường đơn giản hơn. Khi không có tham chiếu hợp lệ, chọn quy tắc hiển thị hoặc báo lỗi thay vì bỏ qua dữ liệu âm thầm.

### 9.3. Tìm tất cả Order của Customer

Tìm theo **field tham chiếu** `customerId` là một truy vấn theo thuộc tính JSON, nên thường cần secondary index:

~~~sql
CREATE INDEX ix_orders_customer_created
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

~~~sql
SELECT META(o).id AS orderId,
       o.status,
       o.createdAt,
       o.total_amount_vnd
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Truy vấn danh sách cần index trên trường **của Order**; một câu `get(Customer)` theo key không cần index `customerId`. Kiểm tra `EXPLAIN` và số liệu thật trước khi chọn thêm index; mỗi index có chi phí cập nhật, lưu trữ và vận hành.

### 9.4. Tham chiếu trong mảng

Khi cần tìm đơn có một dòng tham chiếu Product cụ thể:

~~~sql
SELECT META(o).id AS orderId, o.status
FROM `shop`.`sales`.`orders` AS o
WHERE ANY line IN o.lines
      SATISFIES line.productId = $productId END;
~~~

Với truy vấn thường xuyên, cân nhắc array index:

~~~sql
CREATE INDEX ix_orders_line_product
ON `shop`.`sales`.`orders`
(DISTINCT ARRAY line.productId FOR line IN lines END);
~~~

Không tạo index chỉ vì field tồn tại. Xem planner có sử dụng index, đo latency, chi phí ghi và cân nhắc liệu chức năng có cần một read model danh sách đơn theo Product hay không.

## 10. Tính nhất quán: giá trị nhúng và document được tham chiếu

### 10.1. Thay đổi cùng một document

Nếu thêm `OrderLine` và cập nhật `total_amount_vnd` trong một lần `save(order)`, body mới được ghi như một document. Khi có hai request đồng thời sửa Order:

1. Cả hai đọc Order cùng CAS.
2. Request A thêm dòng, ghi thành công.
3. Request B cố ghi dựa trên CAS cũ và có thể nhận `OptimisticLockingFailureException` nếu dùng `@Version`.

Cách xử lý là **đọc lại, kiểm tra lại bất biến và thử lại cả thao tác nghiệp vụ** với giới hạn retry; không gọi lại `save` trên snapshot cũ. Tránh lặp side effect như trừ tiền hoặc gửi email trong đoạn có thể retry.

### 10.2. Thay đổi nhiều document

Khi xác nhận đơn và giữ tồn kho, Order và Inventory độc lập. Có hai chiến lược chính:

| Chiến lược | Phù hợp khi | Cần kiểm soát |
| --- | --- | --- |
| **Transaction đa document** | Bắt buộc commit nguyên tử Order và các document Inventory liên quan | Cấu hình transaction, CAS/lock contention, retry và độ trễ |
| **Reservation/workflow** | Có thể có trạng thái `PENDING` và xử lý nhiều bước | Idempotency, timeout, hủy giữ hàng, bù trừ, tái xử lý event |

Couchbase có transaction nhiều document; Spring Data Couchbase hỗ trợ tham gia transaction theo cấu hình phù hợp. Nhưng không nên biến mọi quan hệ reference thành một transaction: chỉ phối hợp khi **bất biến nghiệp vụ** yêu cầu. Việc `orderRepository.save(order)` rồi `inventoryRepository.save(inventory)` liên tiếp **không tự bảo đảm nguyên tử**.

### 10.3. Độ tươi của SQL++ và KV

KV theo key và query dùng secondary index có cơ chế quan sát dữ liệu khác nhau. Sau khi ghi một Order, SQL++ lọc theo `customerId` có thể chưa nhìn thấy document mới ngay nếu scan consistency mặc định cho phép index cập nhật bất đồng bộ. Nếu cần read-your-own-write, cân nhắc đọc theo key hoặc thiết lập mức scan consistency phù hợp, rồi đo tác động tới latency.

### 10.4. Reference bị mất và việc xóa nguồn

Nếu Product bị xóa nhưng Order còn giữ `productId`, Order không biến mất và reference không tự được sửa. Bởi vậy:

- Với dữ liệu lịch sử, snapshot tên/giá trong Order phải đủ để hiển thị chứng từ mà không cần Product hiện hành.
- Với dữ liệu đang hoạt động, kiểm tra tồn tại/active status của Product ở thời điểm thực hiện hành động quan trọng.
- Với Customer/Inventory, chọn **soft-delete**, tombstone hoặc chính sách cleanup có chủ đích khi được phép.
- Luôn xác định hành vi UI/API khi đích vắng mặt: không tìm thấy, bỏ qua một phần, hoặc hiển thị bản chụp lịch sử.

## 11. TTL, kích thước document, hot key và vận hành

### TTL thuộc về document

Nếu giỏ hàng `Cart` chứa các dòng nhúng và có TTL, khi Cart hết hạn thì **toàn bộ document** hết hạn. Một dòng hàng nhúng không có TTL riêng. Nếu một reservation cần hạn 15 phút còn Order phải giữ lâu dài, reservation có thể cần document riêng với expiry độc lập hoặc một cơ chế kiểm tra thời hạn nghiệp vụ.

Reference cũng có thể trỏ tới document đã hết hạn: phải xử lý **dangling reference** khi đọc. Không nên áp TTL lên Order cần giữ chứng từ chỉ vì một trong các thành phần con là dữ liệu tạm thời.

### Kích thước và tần suất ghi

Một document nhúng nhiều dữ liệu gây:

- Payload đọc lớn hơn, đặc biệt khi lấy cả root chỉ để hiện vài field.
- Chi phí chuyển đổi Java/JSON và truyền mạng tăng.
- Một CAS chung cho các writer làm tăng khả năng conflict.
- Vấn đề tăng trưởng mảng và giới hạn dung lượng document.

Một thiết kế reference quá mức lại gây nhiều lượt KV, JOIN phức tạp, độ trễ và sự phụ thuộc vào tính sẵn có của các collection khác. Cần đo **p95 latency**, số KV request mỗi API, kích thước document p95/max, số phần tử mảng, tỷ lệ CAS conflict, chi phí index và throughput ghi.

### Reactive không sửa mô hình dữ liệu

Dùng `ReactiveCouchbaseRepository` hoặc `ReactiveCouchbaseTemplate` hữu ích khi cần I/O không chặn dưới tải đồng thời. Nhưng reactive không làm reference tự dereference, không tự quản lý invariant giữa document và không thay đổi lựa chọn embed/reference. Khi load hàng trăm Product, vẫn cần giới hạn concurrency/backpressure và xử lý lỗi từng tham chiếu.

## 12. Những phương án kết hợp thường hiệu quả

| Nhu cầu | Cấu trúc đề xuất | Lý do |
| --- | --- | --- |
| Chi tiết Order sau khi mua | Embed OrderLine + giá/tên snapshot, reference Customer/Product | Bảo toàn lịch sử, vẫn liên kết dữ liệu mới |
| Giỏ hàng có vài chục dòng | Embed CartLine, lưu `productId` | Ghi/xóa dòng cùng Cart, kích thước có trần |
| Danh sách Order của Customer | Order riêng, field `customerId`, index | Phân trang và tránh Customer document phình to |
| Product có hàng triệu Review | Review riêng có `productId`, Product giữ tổng hợp nhỏ | Tránh hot document, dễ phân trang/kiểm duyệt |
| Thông tin Profile dùng ở nhiều nơi | Customer document riêng, reference bằng key | Một nguồn sự thật |
| Địa chỉ giao nhận đã chốt | Snapshot nhúng vào Order | Không đổi khi Customer cập nhật hồ sơ |
| Danh mục nhãn ít, không trùng | `Set<String>` nhúng vào Product | Đọc một lần, số phần tử có giới hạn |
| Dữ liệu tồn kho tranh chấp cao | Inventory riêng, Order tham chiếu SKU/Product | Tối ưu thao tác ghi và nhất quán kho |

Điểm then chốt của mô hình kết hợp là xác định **field nào biểu diễn lịch sử bất biến** và **field nào luôn phải phản ánh trạng thái hiện hành**. Nếu hai nhóm có mục đích khác nhau, cố ép một dạng tham chiếu hoặc một dạng nhúng cho toàn bộ quan hệ có thể tạo lỗi nghiệp vụ.

## 13. Những sai lầm thường gặp

1. **Nhúng toàn bộ Order vào Customer.** Khi lịch sử tăng không giới hạn, document Customer phình to và khó phân trang. Lưu Order riêng có `customerId` và index.
2. **Chỉ lưu `productId` trong Order đã chốt.** Khi Product đổi tên hoặc giá, không thể khôi phục chính xác dữ liệu lúc mua nếu thiếu snapshot. Lưu các trường lịch sử cần thiết trong OrderLine.
3. **Nhúng toàn bộ Product vào mỗi dòng Order.** Sao chép quá nhiều thuộc tính không cần thiết, gây tăng dung lượng và nhầm tưởng phải đồng bộ. Chỉ snapshot đúng trường phục vụ chứng từ.
4. **Cho rằng một chuỗi ID là foreign key.** Couchbase không tự enforce quan hệ tồn tại hoặc cascade delete. Kiểm tra và định nghĩa chính sách xóa ở tầng nghiệp vụ.
5. **Cho rằng Spring Data tự JOIN khi có `customerId`.** Repository đọc Order thông qua mapping của chính Order; reference phải được nạp chủ động.
6. **Gọi `findById` trong vòng lặp lớn mà không giới hạn.** Dẫn tới N+1 và độ trễ; hãy deduplicate, giới hạn concurrency, cache hoặc chọn query/read model hợp lý.
7. **Quên index cho truy vấn theo field tham chiếu.** `findById` dùng KV, nhưng tìm Order bằng `customerId` thường cần secondary index.
8. **Bỏ `@Version` khi nhiều writer cùng sửa một root lớn.** Ghi dựa trên snapshot cũ có nguy cơ mất dữ liệu. Dùng CAS/optimistic locking hoặc thiết kế lại hot aggregate.
9. **Giữ dữ liệu có TTL độc lập trong document lâu dài.** TTL document không tác động riêng một item trong mảng; tách document hoặc kiểm tra expiry nghiệp vụ.
10. **Dùng transaction cho mọi cập nhật tham chiếu.** Tăng overhead mà không giải quyết được mô hình. Chỉ đưa document vào cùng transaction khi bất biến thật sự đòi hỏi.
11. **Đổi document key khi thuộc tính hiển thị thay đổi.** Tất cả reference cũ trở nên sai. Chọn ID ổn định, tách khỏi tên/số điện thoại/email có thể đổi.
12. **Phân tán bản sao dữ liệu hiện hành nhưng không có cơ chế cập nhật.** Quy định nguồn sự thật, sự kiện cập nhật, retry/idempotency hoặc đọc trực tiếp khi cần độ tươi.

## 14. Bài thực hành: mô hình hóa hệ thống khóa học

Một nền tảng học trực tuyến có:

- `Course`: tên khóa học, mô tả ngắn, danh sách tối đa 20 `Section`; mỗi section có vài `LessonRef` với `lessonId` và thứ tự.
- `Lesson`: nội dung có thể dài, được biên tập độc lập, có lịch sử version.
- `Instructor`: hồ sơ giảng viên, có thể giảng nhiều khóa, thông tin thường được cập nhật.
- `Enrollment`: mỗi học viên có nhiều lượt ghi tiến độ và trạng thái theo khóa.
- Màn hình Course detail cần cấu trúc section nhanh; màn hình Lesson detail chỉ tải nội dung bài khi người học mở.

**Yêu cầu:** chọn embed/reference cho từng quan hệ và giải thích cách truy cập.

### Gợi ý lời giải

- **Course** là root. Nhúng **Section** và danh sách `LessonRef {lessonId, position}` vào Course vì chúng hữu hạn và thường đọc cùng cấu trúc khóa học.
- **Lesson** là document riêng vì nội dung lớn, được sửa/version độc lập, và người dùng chỉ tải khi mở bài. Course chỉ lưu `lessonId`.
- **Instructor** là document riêng; Course lưu `instructorId`, có thể nhúng snapshot tên giảng viên nếu UI cần đọc nhanh và có chính sách cập nhật hoặc đó là tên lịch sử được chấp nhận.
- **Enrollment/Progress** là document riêng theo học viên/khóa học hoặc theo phân vùng phù hợp với tần suất ghi, không nhúng vào Course vốn được mọi học viên đọc chung.
- **Truy cập:** Course detail đọc KV Course theo ID, đã có section/lesson IDs; Lesson detail đọc KV Lesson; danh sách khóa của Instructor dùng SQL++ lọc `instructorId` có index hoặc read model.

JSON Course minh họa:

~~~json
{
  "title": "Spring Data Couchbase",
  "instructorId": "instructor::42",
  "sections": [
    {
      "title": "Mô hình tài liệu",
      "lessons": [
        {"lessonId": "lesson::embed-reference", "position": 1},
        {"lessonId": "lesson::cas", "position": 2}
      ]
    }
  ]
}
~~~

Ở đây `sections` và `lessons` bên trong chúng là **danh sách giá trị cấu trúc khóa học**, còn `lessonId` trỏ đến nội dung Lesson độc lập. Việc dùng tên `LessonRef` trong Java giúp tránh vô tình nhúng toàn bộ nội dung Lesson.

### Câu hỏi tự kiểm tra

1. **Nếu OrderLine được nhúng, nó có CAS riêng không?** Không. CAS thuộc document Order chứa nó.
2. **Lưu `productId` trong Order có tự thực thi khóa ngoại không?** Không. Phải có kiểm tra và chính sách xử lý reference bị mất.
3. **Vì sao vừa giữ `productId` vừa giữ `unitPriceAtPurchase`?** ID giúp tra Product hiện hành, còn snapshot giá giữ đúng lịch sử giao dịch.
4. **Đọc Order bằng `findById` có cần secondary index không?** Không, vì đây là thao tác KV theo key.
5. **Tìm mọi Order có `customerId` có cần index không?** Thường có; đó là tìm theo field JSON chứ không theo key của Order.
6. **Mảng Review của Product phát triển không giới hạn nên làm gì?** Đưa Review thành document riêng, index theo `productId`, phân trang.
7. **Hai lần `save` trên Order và Inventory có tự là một transaction không?** Không. Cần cấu hình transaction hoặc thiết kế workflow phối hợp.
8. **TTL 15 phút của Cart có khiến một dòng hàng riêng lẻ hết hạn trước các dòng khác không?** Không. TTL áp dụng cho toàn bộ Cart document.
9. **Reactive API có tự loại N+1 hoặc xử lý consistency không?** Không; vẫn phải thiết kế số request, concurrency và ranh giới giao dịch.

## 15. Checklist trước khi triển khai

- [ ] Liệt kê các API đọc/ghi có tần suất và độ trễ mục tiêu.
- [ ] Xác định invariant, aggregate root và vòng đời của dữ liệu con.
- [ ] Quyết định từng quan hệ dùng embed, reference, snapshot hay read model.
- [ ] Đặt trần kích thước, số phần tử và mức cạnh tranh ghi cho document nhúng.
- [ ] Dùng document key ổn định; biết chính xác collection của reference đích.
- [ ] Thiết kế đọc theo key trước, query theo field reference/array sau; kiểm tra index và `EXPLAIN`.
- [ ] Định nghĩa hành vi khi reference đích bị xóa, hết TTL hoặc tạm thời không sẵn sàng.
- [ ] Dùng `@Version`/CAS khi root có writer đồng thời; đánh giá transaction nếu thay đổi nhiều document.
- [ ] Xác định nguồn sự thật, dữ liệu snapshot và chính sách đồng bộ các read model.
- [ ] Đo p95, kích thước payload, số lượt KV/JOIN, index lag và tỷ lệ conflict trên workload thật.
- [ ] Kiểm thử vòng đọc–ghi, trường hợp xóa reference, thay đổi Product sau khi tạo Order và ghi đồng thời.

## Tài liệu tham khảo chính thức

- [Couchbase — Document Data Model](https://docs.couchbase.com/server/current/learn/data/document-data-model.html): cấu trúc JSON, nhúng/tham chiếu và góc nhìn document-oriented.
- [Couchbase — Key-Value Operations](https://docs.couchbase.com/server/current/guides/kv-operations.html): truy cập document trực tiếp theo key.
- [Couchbase — SQL++ JOIN](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/join.html): các kiểu JOIN, bao gồm lookup JOIN theo document key.
- [Couchbase — SQL++ CREATE INDEX](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/createindex.html): chỉ mục trên field JSON và biểu thức mảng.
- [Spring Data Couchbase — Modeling Entities](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): ánh xạ `@Document`, `@Id`, field và optimistic locking.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): KV, các phương thức repository và truy vấn.
- [Spring Data Couchbase — Transactions](https://docs.spring.io/spring-data/couchbase/reference/couchbase/transactions.html): giao dịch nhiều document và các giới hạn cần cân nhắc.
