# Thực nghiệm cùng nghiệp vụ bằng dữ liệu nhúng và dữ liệu tham chiếu

Trong cơ sở dữ liệu tài liệu (*document database*), một quan hệ nghiệp vụ có thể được biểu diễn theo hai cách phổ biến: **nhúng dữ liệu** (*embedding*) vào tài liệu cha, hoặc **tách thành tài liệu riêng và lưu khóa tham chiếu** (*referencing*). Hai cách có thể cho ra cùng kết quả nghiệp vụ nhưng đường đọc, số thao tác ghi, khả năng cập nhật đồng thời và chi phí mở rộng rất khác nhau.

Bài này xây dựng **cùng một nghiệp vụ đơn hàng** theo cả hai mô hình, sau đó hướng dẫn chạy thử trên MongoDB. Mục tiêu không phải tuyên bố một mô hình luôn nhanh hơn, mà là biết **thiết kế phép thử công bằng**, nhìn dữ liệu và chỉ số thực thi, rồi chọn cấu trúc đáp ứng các truy vấn quan trọng của ứng dụng.

Sau bài thực nghiệm, bạn sẽ biết cách:

- Biểu diễn đơn hàng và các dòng sản phẩm bằng **mảng nhúng** hoặc bằng **collection chi tiết tham chiếu tới đơn hàng**.
- Tạo hai bộ dữ liệu **tương đương về nội dung và quy tắc nghiệp vụ** để so sánh.
- Thử các thao tác **xem chi tiết đơn, lọc đơn theo sản phẩm, liệt kê đơn theo khách hàng, cập nhật số lượng**.
- Phân tích **số truy vấn, chỉ mục, lượng dữ liệu đọc, ranh giới cập nhật nguyên tử và khả năng tăng trưởng**.
- Đưa ra quyết định thiết kế dựa trên khối lượng dữ liệu và yêu cầu thực tế.

> **Phạm vi:** Cú pháp thực hành sử dụng `mongosh` và MongoDB. Các nguyên tắc nhúng/tham chiếu có thể chuyển sang nhiều document database, nhưng chi tiết về truy vấn, chỉ mục, transaction và giới hạn tài liệu cần đối chiếu với sản phẩm cụ thể.

## 1. Bài toán cố định: đơn hàng có nhiều dòng sản phẩm

Hệ thống bán hàng cần quản lý mỗi **đơn hàng** và các **dòng hàng** (*order lines*). Mỗi đơn có mã, khách hàng, trạng thái, ngày tạo, địa chỉ giao hàng và tổng tiền. Mỗi dòng hàng ghi mã sản phẩm, số lượng và **đơn giá tại thời điểm đặt hàng**.

Yêu cầu nghiệp vụ được giữ nguyên ở cả hai cách lưu:

1. Xem đơn hàng kèm tất cả dòng hàng.
2. Liệt kê các đơn gần đây của một khách hàng.
3. Tìm đơn có chứa một SKU.
4. Tăng số lượng của một dòng và tăng tổng tiền tương ứng.
5. Không để tổng tiền lệch so với các dòng hàng sau khi cập nhật thành công.
6. Giữ được giá lịch sử ngay cả khi giá niêm yết hiện tại của sản phẩm thay đổi.

Một đơn hàng ví dụ:

~~~json
{
  "_id": "ORD-000001",
  "customerId": "C-001",
  "status": "CREATED",
  "createdAt": "2026-10-01T00:01:00Z",
  "shippingAddress": {
    "city": "Ha Noi",
    "country": "VN"
  },
  "totalAmount": 70000,
  "items": [
    {
      "lineId": "L1",
      "sku": "SKU-0004",
      "quantity": 2,
      "unitPrice": 10000
    },
    {
      "lineId": "L2",
      "sku": "SKU-0005",
      "quantity": 1,
      "unitPrice": 20000
    },
    {
      "lineId": "L3",
      "sku": "SKU-0006",
      "quantity": 1,
      "unitPrice": 30000
    }
  ]
}
~~~

Tổng tiền:

\[
2 \times 10\,000 + 1 \times 20\,000 + 1 \times 30\,000 = 70\,000\ \text{VND}
\]

Đơn giá được lưu ở dòng hàng là **snapshot lịch sử**, không phải phép tra cứu giá hiện tại từ danh mục sản phẩm. Giữ quy tắc này cho cả hai mô hình để phép so sánh không bị thay đổi ý nghĩa nghiệp vụ.

## 2. Mô hình A: dữ liệu nhúng trong document đơn hàng

Trong mô hình nhúng, mỗi đơn hàng là **một document** của collection `orders_embedded`. Dòng hàng nằm trong mảng `items` của tài liệu đó.

~~~text
orders_embedded
┌───────────────────────────────────────────┐
│ Document ORD-000001                       │
│  customerId, status, createdAt            │
│  shippingAddress, totalAmount             │
│  items[]                                  │
│   ├─ {lineId: L1, sku: SKU-0004, ...}      │
│   ├─ {lineId: L2, sku: SKU-0005, ...}      │
│   └─ {lineId: L3, sku: SKU-0006, ...}      │
└───────────────────────────────────────────┘
┌───────────────────────────────────────────┐
│ Document ORD-000002                       │
│  ...                                      │
└───────────────────────────────────────────┘
~~~

**Đặc điểm quan trọng:**

- Khi tải đơn theo `_id`, ứng dụng có thể nhận **đầy đủ dòng hàng trong một lần đọc document**.
- Các dòng hàng thuộc cùng **ranh giới document**. Với MongoDB, một thao tác cập nhật đơn document là nguyên tử, kể cả khi sửa nhiều field hoặc phần tử mảng trong document đó.
- Mảng có thể tăng kích thước. Nếu đơn hàng chứa số dòng không giới hạn, document có thể phình to, làm tăng chi phí cập nhật và có nguy cơ vượt giới hạn kích thước.
- Truy vấn “đơn nào chứa SKU X?” có thể dùng chỉ mục **multikey** trên `items.sku`.
- Một dòng hàng nhúng là **subdocument/embedded document**; nó không tự động có vòng đời, chỉ mục và khóa lưu trữ độc lập như document ở collection khác.

Mô hình này có xu hướng phù hợp khi dòng hàng **thường được đọc cùng đơn** và **số dòng mỗi đơn có thể kiểm soát**.

## 3. Mô hình B: dữ liệu tham chiếu qua hai collection

Trong mô hình tham chiếu, phần đầu đơn hàng nằm ở `orders_reference`. Mỗi dòng hàng là **một document riêng** trong `order_items_reference`, có field `orderId` trỏ tới đơn hàng.

~~~text
orders_reference
┌───────────────────────────────────────────┐
│ Document ORD-000001                       │
│  customerId, status, createdAt            │
│  shippingAddress, totalAmount             │
└───────────────────────────────────────────┘
                    │
                    │ _id = orderId
                    ▼
order_items_reference
┌───────────────────────────────────────────┐
│ _id: ORD-000001:L1                        │
│ orderId: ORD-000001                       │
│ lineId: L1, sku: SKU-0004                 │
│ quantity: 2, unitPrice: 10000             │
├───────────────────────────────────────────┤
│ _id: ORD-000001:L2                        │
│ orderId: ORD-000001                       │
│ lineId: L2, sku: SKU-0005                 │
│ quantity: 1, unitPrice: 20000             │
├───────────────────────────────────────────┤
│ _id: ORD-000001:L3                        │
│ orderId: ORD-000001                       │
│ lineId: L3, sku: SKU-0006                 │
│ quantity: 1, unitPrice: 30000             │
└───────────────────────────────────────────┘
~~~

Document đầu đơn minh họa:

~~~json
{
  "_id": "ORD-000001",
  "customerId": "C-001",
  "status": "CREATED",
  "createdAt": "2026-10-01T00:01:00Z",
  "shippingAddress": {
    "city": "Ha Noi",
    "country": "VN"
  },
  "totalAmount": 70000
}
~~~

Một dòng hàng riêng:

~~~json
{
  "_id": "ORD-000001:L2",
  "orderId": "ORD-000001",
  "lineId": "L2",
  "sku": "SKU-0005",
  "quantity": 1,
  "unitPrice": 20000
}
~~~

**Đặc điểm quan trọng:**

- Muốn xem đầy đủ một đơn, ứng dụng cần **đọc document đầu đơn và những document dòng hàng**; có thể làm bằng hai truy vấn hoặc một aggregation dùng `$lookup`.
- Mỗi dòng hàng có khóa lưu trữ riêng; hệ có thể tìm, cập nhật và quản lý từng dòng độc lập.
- Mảng dòng hàng không làm document đầu đơn tăng kích thước.
- Nếu thay đổi dòng hàng **và** `totalAmount` trên đầu đơn, thao tác liên quan **hai document**. Muốn bảo đảm nguyên tử trên cả hai phải dùng transaction trong phạm vi được MongoDB hỗ trợ hoặc một chiến lược nhất quán khác.
- Khi xóa đơn hàng, cần xử lý các dòng liên quan; khóa `orderId` không mặc nhiên là foreign key với hành vi cascade như trong nhiều mô hình quan hệ.

**Hai mô hình lưu cùng thông tin nghiệp vụ.** Dòng hàng trong mô hình B **vẫn lưu `unitPrice` lịch sử**; nếu bỏ giá này và chỉ tham chiếu sang danh mục sản phẩm đang thay đổi, đó đã là một bài toán khác.

## 4. Thiết kế thí nghiệm để so sánh công bằng

Chúng ta tạo cùng **3.000 đơn hàng**, mỗi đơn **3 dòng**, rồi ghi sang hai cấu trúc.

| Tham số | Mô hình A: nhúng | Mô hình B: tham chiếu |
| --- | ---: | ---: |
| Số đơn hàng | 3.000 | 3.000 |
| Số dòng mỗi đơn | 3 | 3 |
| Tổng số dòng hàng logic | 9.000 | 9.000 |
| Số document chứa đầu đơn | 3.000 | 3.000 |
| Số document dòng hàng riêng | 0 | 9.000 |
| Tổng số document được lưu | 3.000 | 12.000 |
| Field nghiệp vụ | Như nhau | Như nhau |
| Tổng tiền, đơn giá, SKU | Cùng giá trị | Cùng giá trị |

Số lượng document khác nhau là **hệ quả của mô hình**, không phải số lượng nghiệp vụ khác nhau. Đừng kết luận “tham chiếu xử lý gấp bốn lần dữ liệu” chỉ vì có 12.000 document; kích thước BSON, index, số lần đọc và kiểu truy vấn mới là những đại lượng cần đo.

Để giảm yếu tố gây nhiễu, cả hai bên được dùng cùng dữ liệu đầu vào, cùng môi trường MongoDB, chỉ mục phù hợp với cùng đường truy vấn và cùng số lần lặp. **Không điền trước số mili-giây giả định vào bảng kết quả.** Máy tính, dữ liệu cache, phiên bản MongoDB, bộ tối ưu và chỉ mục đều ảnh hưởng kết quả đo.

### Chuẩn bị môi trường

Cần có MongoDB và công cụ `mongosh` có quyền tạo collection và index trong database thử nghiệm. Bài này dùng database riêng tên `nosql_embed_ref_lab`.

Ví dụ thiết lập **xóa ba collection thử nghiệm** trong database này để tạo lại bộ dữ liệu từ đầu. Chỉ thực hiện trong môi trường thực hành, tránh đặt dữ liệu thật trong ba collection đó.

## 5. Khởi tạo cùng một bộ dữ liệu cho hai mô hình

Mở `mongosh` và chạy toàn bộ khối sau. Các giá trị được tạo **có quy luật, không dùng random**, nên có thể tái lập cùng bộ dữ liệu sau mỗi lần khởi tạo.

~~~javascript
const lab = db.getSiblingDB("nosql_embed_ref_lab");

// Chỉ làm mới ba collection được dùng cho bài thực nghiệm.
["orders_embedded", "orders_reference", "order_items_reference"]
  .forEach(name => lab.getCollection(name).drop());

const N = 3000;
const embeddedOrders = [];
const referenceOrders = [];
const referenceItems = [];

for (let i = 1; i <= N; i++) {
  const orderId = "ORD-" + String(i).padStart(6, "0");
  const customerId = "C-" + String(i % 200).padStart(3, "0");

  const items = [1, 2, 3].map(j => ({
    lineId: "L" + j,
    sku: "SKU-" + String((i * 3 + j) % 1000).padStart(4, "0"),
    quantity: j === 1 ? 2 : 1,
    unitPrice: j * 10000
  }));

  const totalAmount = items.reduce(
    (sum, item) => sum + item.quantity * item.unitPrice,
    0
  );

  const order = {
    _id: orderId,
    customerId,
    status: i % 4 === 0 ? "PAID" : "CREATED",
    createdAt: new Date(Date.UTC(2026, 9, 1) + i * 60 * 1000),
    shippingAddress: {
      city: i % 2 === 0 ? "Da Nang" : "Ha Noi",
      country: "VN"
    },
    totalAmount
  };

  // Mô hình A: toàn bộ dòng hàng nằm trong một document đơn.
  embeddedOrders.push({ ...order, items });

  // Mô hình B: đầu đơn và dòng hàng là các document riêng.
  referenceOrders.push({ ...order });

  for (const item of items) {
    referenceItems.push({
      _id: orderId + ":" + item.lineId,
      orderId,
      ...item
    });
  }
}

lab.orders_embedded.insertMany(embeddedOrders);
lab.orders_reference.insertMany(referenceOrders);
lab.order_items_reference.insertMany(referenceItems);

print("Embedded orders:", lab.orders_embedded.countDocuments({}));
print("Reference orders:", lab.orders_reference.countDocuments({}));
print("Reference items:", lab.order_items_reference.countDocuments({}));
~~~

Kỳ vọng số lượng lần lượt là **3.000**, **3.000**, **9.000**. Đây là số lượng suy ra từ đoạn sinh dữ liệu; nếu lệnh chạy lỗi hoặc dừng giữa chừng, số lượng thực tế có thể khác và phải xử lý trước khi thử tiếp.

Với đơn `ORD-000001`, cả hai mô hình đều có ba dòng với tổng tiền ban đầu là **70.000 VND**. Timestamp lưu ở kiểu `Date` của MongoDB dù ví dụ JSON ở đầu bài biểu diễn bằng chuỗi.

### Tạo chỉ mục tương ứng với các đường truy vấn

~~~javascript
// Cả hai mô hình đều liệt kê đơn theo khách hàng và thời gian.
lab.orders_embedded.createIndex({
  customerId: 1,
  createdAt: -1
});
lab.orders_reference.createIndex({
  customerId: 1,
  createdAt: -1
});

// Mô hình nhúng: tìm đơn theo SKU trong mảng items.
lab.orders_embedded.createIndex({
  "items.sku": 1
});

// Mô hình tham chiếu: lấy các dòng của một đơn và tìm theo SKU.
lab.order_items_reference.createIndex({
  orderId: 1,
  lineId: 1
});
lab.order_items_reference.createIndex({
  sku: 1,
  orderId: 1
});
~~~

MongoDB có chỉ mục duy nhất mặc định trên `_id` cho mỗi collection thông thường. Chỉ mục `items.sku` của mô hình nhúng có thể là **multikey index** vì `items` là mảng. Mô hình tham chiếu cần index theo `orderId` để lấy tất cả dòng hàng của một đơn. Chi phí index là một phần của kết quả so sánh lưu trữ và ghi.

**Lưu ý khi đối chiếu:** không nhất thiết ép hai collection có đúng số index bằng nhau. Mô hình dữ liệu khác nhau tạo ra đường truy cập khác nhau; điều công bằng là mỗi mô hình được trang bị index hợp lý cho cùng yêu cầu nghiệp vụ, đồng thời ghi nhận chi phí của những index đó.

## 6. Thực nghiệm A: lấy chi tiết một đơn hàng

### Cách A: đọc một document có mảng nhúng

~~~javascript
const orderId = "ORD-000001";

const embeddedDetail = lab.orders_embedded.findOne({
  _id: orderId
});

printjson(embeddedDetail);
~~~

Dữ liệu trả về có ngay `items`. Ứng dụng thường chỉ cần một yêu cầu đọc document và không cần tự ghép thêm dòng hàng.

### Cách B: đọc đầu đơn, sau đó đọc những dòng tham chiếu

~~~javascript
const orderId = "ORD-000001";

const header = lab.orders_reference.findOne({
  _id: orderId
});

const lines = lab.order_items_reference
  .find({ orderId })
  .sort({ lineId: 1 })
  .toArray()
  .map(({ _id, orderId, ...item }) => item);

const referencedDetail = header === null
  ? null
  : { ...header, items: lines };

printjson(referencedDetail);
~~~

Nếu chỉ tính các truy vấn ứng dụng gửi, mô hình B dùng **hai lần đọc collection**: một tìm đầu đơn, một tìm dòng hàng. Mỗi truy vấn có thể tận dụng index riêng. Nếu cần giảm số lần trao đổi giữa client và database, có thể dùng aggregation với `$lookup`:

~~~javascript
lab.orders_reference.aggregate([
  { $match: { _id: "ORD-000001" } },
  {
    $lookup: {
      from: "order_items_reference",
      localField: "_id",
      foreignField: "orderId",
      as: "items"
    }
  }
]).toArray();
~~~

`$lookup` trả các document dòng hàng với field nội bộ `_id` và `orderId`. Nếu API cần cấu trúc giống mô hình A, có thể dùng `$project`/`$map` hoặc biến đổi ở ứng dụng; thứ tự phần tử từ `$lookup` không nên được giả định nếu không có bước sắp xếp xác định.

### Kiểm tra cùng kết quả nghiệp vụ

Trong trường hợp đọc bằng hai truy vấn ở trên, có thể so sánh giá trị sau khi chuẩn hóa:

~~~javascript
print(
  "Hai tài liệu chi tiết tương đương:",
  EJSON.stringify(embeddedDetail) ===
    EJSON.stringify(referencedDetail)
);
~~~

Với dữ liệu vừa seed và các dòng được sắp theo `lineId`, kết quả dự kiến là `true`. Nếu thay đổi dữ liệu ở một trong hai mô hình trước khi so sánh, kết quả có thể khác.

### Diễn giải

- **Nhúng:** thuận lợi khi màn hình thường cần **toàn bộ chi tiết đơn**, nhất là số dòng nhỏ và ổn định.
- **Tham chiếu:** tốn thêm bước đọc/ghép dữ liệu, nhưng có thể tải **đầu đơn trước** và chỉ lấy dòng hàng khi cần; phù hợp hơn khi dòng hàng rất nhiều hoặc có vòng đời cập nhật riêng.

Kết luận về **độ trễ** phải dựa trên số đo thực nghiệm. “Một query” không mặc nhiên luôn nhanh hơn “hai query” nếu kích thước document, index, cache hoặc lượng dữ liệu trả về khác nhau rất lớn.

## 7. Thực nghiệm B: liệt kê đơn của một khách hàng

Giả sử trang “Đơn hàng của tôi” chỉ cần mã, thời gian, trạng thái và tổng tiền, **không cần các dòng hàng**.

### Cách A: dùng projection để không trả mảng items

~~~javascript
lab.orders_embedded.find(
  { customerId: "C-001" },
  {
    _id: 1,
    customerId: 1,
    status: 1,
    createdAt: 1,
    totalAmount: 1
  }
).sort({ createdAt: -1 }).limit(10).toArray();
~~~

### Cách B: đọc trực tiếp collection đầu đơn

~~~javascript
lab.orders_reference.find(
  { customerId: "C-001" },
  {
    _id: 1,
    customerId: 1,
    status: 1,
    createdAt: 1,
    totalAmount: 1
  }
).sort({ createdAt: -1 }).limit(10).toArray();
~~~

**Đầu ra nghiệp vụ giống nhau.** Điểm khác biệt là cách bố trí dữ liệu: mô hình A cất mảng `items` cùng document đơn, mô hình B để document đầu đơn gọn hơn. Projection làm giảm dữ liệu gửi về client ở mô hình A, nhưng không tự đảm bảo storage engine tránh tải các phần BSON chứa `items`. Việc có truy vấn được bao phủ hoàn toàn bởi index hay không cần xem execution plan.

Bởi thế, nếu ứng dụng có nhiều màn hình chỉ liệt kê **metadata đơn hàng**, mô hình tách riêng có thể đáng xem xét. Ngược lại, nếu mỗi lần hiển thị đơn đều phải tải dòng hàng, lợi thế đó có thể không đủ bù chi phí ghép.

## 8. Thực nghiệm C: tìm đơn có chứa một SKU

Yêu cầu: tìm những đơn có chứa sản phẩm `SKU-0007`, lấy mã đơn và trạng thái.

### Cách A: tìm bằng đường dẫn của mảng nhúng

~~~javascript
const embeddedMatches = lab.orders_embedded.find(
  { "items.sku": "SKU-0007" },
  { _id: 1, status: 1 }
).toArray();

printjson(embeddedMatches);
~~~

Index `items.sku` có thể hỗ trợ lọc. Vì field nằm trong mảng, hệ phải xử lý ánh xạ từ giá trị SKU tới document đơn hàng chứa phần tử phù hợp.

### Cách B: tìm dòng hàng trước, rồi lấy đơn hàng

~~~javascript
const matchedOrderIds = lab.order_items_reference.distinct(
  "orderId",
  { sku: "SKU-0007" }
);

const referencedMatches = lab.orders_reference.find(
  { _id: { $in: matchedOrderIds } },
  { _id: 1, status: 1 }
).toArray();

printjson(referencedMatches);
~~~

Index `{ sku: 1, orderId: 1 }` hỗ trợ đường truy cập của collection dòng hàng. Nhưng để lấy `status`, ứng dụng còn phải truy vấn collection đầu đơn hoặc dùng pipeline `$lookup`.

Nếu chỉ cần **danh sách ID đơn**, mô hình B có thể dừng ở `distinct("orderId")`; nếu cần **metadata của đơn**, phải tính chi phí ghép thêm. So sánh thực tế cần căn cứ đúng đầu ra nghiệp vụ được yêu cầu.

### Đối chiếu tập ID

~~~javascript
const idsEmbedded = lab.orders_embedded
  .distinct("_id", { "items.sku": "SKU-0007" })
  .sort();

const idsReferenced = lab.order_items_reference
  .distinct("orderId", { sku: "SKU-0007" })
  .sort();

print(
  "Tập đơn trùng nhau:",
  EJSON.stringify(idsEmbedded) === EJSON.stringify(idsReferenced)
);
~~~

Đoạn này giúp kiểm tra rằng hai cấu trúc vẫn trả về **cùng tập đơn**, trước khi so sánh hiệu năng. Giá trị “trùng nhau” chỉ có ý nghĩa khi cả hai bộ dữ liệu chưa bị thay đổi lệch nhau sau lúc seed.

## 9. Thực nghiệm D: cập nhật số lượng và tổng tiền

Đây là phép thử bộc lộ rõ **ranh giới cập nhật nguyên tử**. Yêu cầu: tăng số lượng dòng `L2` của đơn `ORD-000001` từ **1 lên 2**. Đơn giá dòng đó là **20.000 VND**, nên tổng tiền phải tăng từ **70.000 lên 90.000 VND**.

Hai giá trị phải thay đổi cùng nhau theo hợp đồng nghiệp vụ.

### Cách A: cập nhật một document nhúng

~~~javascript
const embeddedUpdate = lab.orders_embedded.updateOne(
  {
    _id: "ORD-000001",
    items: {
      $elemMatch: {
        lineId: "L2",
        quantity: 1
      }
    }
  },
  {
    $inc: {
      "items.$[line].quantity": 1,
      totalAmount: 20000
    }
  },
  {
    arrayFilters: [
      { "line.lineId": "L2", "line.quantity": 1 }
    ]
  }
);

printjson(embeddedUpdate);
~~~

MongoDB áp dụng hai phép `$inc` trong **cùng một thao tác trên document đơn hàng**. Điều kiện `quantity: 1` giúp tránh chạy lại thao tác tăng y nguyên lần thứ hai; ứng dụng cần kiểm tra `matchedCount`/`modifiedCount` và có quy ước xử lý retry rõ ràng.

Trong trường hợp thực tế, tiền tăng thêm phải được xác định đúng từ giá lịch sử và quy tắc giảm giá/thuế. Nếu số lượng có thể thay đổi đồng thời qua nhiều luồng, nên dùng điều kiện phiên bản hoặc mã thao tác idempotent để ngăn cập nhật trùng.

### Cách B: cập nhật hai document tham chiếu

Nếu cập nhật riêng dòng hàng rồi cập nhật tổng tiền như sau:

~~~javascript
lab.order_items_reference.updateOne(
  { _id: "ORD-000001:L2", quantity: 1 },
  { $inc: { quantity: 1 } }
);

lab.orders_reference.updateOne(
  { _id: "ORD-000001" },
  { $inc: { totalAmount: 20000 } }
);
~~~

thì **hai lệnh không tự động trở thành một giao dịch nguyên tử**. Nếu lệnh đầu thành công nhưng lệnh sau thất bại, dòng hàng và tổng tiền có thể lệch nhau. Ngoài ra, nếu lệnh đầu không khớp vì đã được thực hiện trước đó, lệnh sau vẫn tăng tổng tiền trong đoạn mã minh họa này. Đây chính là **điểm không an toàn cần quan sát**, không phải mẫu triển khai nên dùng cho nghiệp vụ tiền tệ.

Một lựa chọn khi MongoDB đang chạy dưới cấu hình hỗ trợ transaction (ví dụ replica set) là cập nhật có điều kiện trong transaction:

~~~javascript
const session = lab.getMongo().startSession();

try {
  session.startTransaction();

  const txDb = session.getDatabase("nosql_embed_ref_lab");

  const lineResult = txDb.order_items_reference.updateOne(
    { _id: "ORD-000001:L2", quantity: 1 },
    { $inc: { quantity: 1 } }
  );

  if (lineResult.matchedCount !== 1) {
    throw new Error("Dong hang da doi hoac khong ton tai");
  }

  const orderResult = txDb.orders_reference.updateOne(
    { _id: "ORD-000001", totalAmount: 70000 },
    { $inc: { totalAmount: 20000 } }
  );

  if (orderResult.matchedCount !== 1) {
    throw new Error("Tong tien da doi hoac don khong ton tai");
  }

  session.commitTransaction();
} catch (error) {
  session.abortTransaction();
  throw error;
} finally {
  session.endSession();
}
~~~

Ví dụ trên minh họa **biên transaction**, không bao gồm cơ chế retry đầy đủ cho transient transaction errors hoặc trường hợp kết quả commit chưa xác định. Ứng dụng thực cần dùng quy tắc retry/transaction của driver và cơ chế idempotency theo mã yêu cầu. **Transaction nhiều document thường có chi phí phối hợp lớn hơn cập nhật một document**, nhưng độ lớn thực tế cần đo.

**Cách chạy phép thử:** sau khi seed, chạy cập nhật của A một lần và của B một lần. Đọc lại cả hai mô hình rồi kiểm tra dòng `L2` có `quantity = 2` và `totalAmount = 90000`. Trước khi lặp lại phép thử với số liệu ban đầu, hãy chạy lại bước seed để đưa cả hai mô hình về trạng thái giống nhau.

### Nếu phải tạo thêm một dòng hàng?

Với mô hình nhúng, thêm dòng mới thường dùng một cập nhật mảng `$push`; nếu còn cập nhật `totalAmount` thì có thể kết hợp trong cùng document. Với mô hình tham chiếu, thêm document dòng hàng mới và cập nhật đầu đơn là hai thay đổi riêng: cần transaction hoặc cơ chế đồng bộ có kiểm soát nếu quy tắc nghiệp vụ yêu cầu tổng tiền luôn khớp ngay lập tức.

Khi số dòng có thể tăng không giới hạn, mô hình tham chiếu giúp tránh document đầu đơn phát triển vô hạn, dù phải trả chi phí phối hợp dữ liệu.

## 10. Thực nghiệm E: đọc metadata hay đọc toàn bộ dòng hàng?

Không phải truy vấn nào cũng cần document đầy đủ. Hãy so sánh hai yêu cầu có tần suất khác nhau:

| Truy vấn | Đầu ra cần thiết | Điểm đáng quan sát |
| --- | --- | --- |
| **E1: Danh sách đơn** | `_id`, `status`, `createdAt`, `totalAmount` | Trả ít field; mô hình nhúng có kéo theo tài liệu lớn hay không? |
| **E2: Chi tiết đơn** | Metadata **và toàn bộ `items`** | Mô hình tham chiếu cần ghép dữ liệu; mô hình nhúng có lợi thế cục bộ? |

Với E1, sử dụng projection ở phần 7. Với E2, dùng hai cách ở phần 6. Chạy mỗi workload nhiều lần với các mã đơn khác nhau hoặc một tập mã chọn trước, thay vì chỉ thử một đơn nhỏ duy nhất.

Một thiết kế nhúng có thể hoạt động rất tốt cho E2 nhưng không phải tối ưu nhất cho E1 khi mỗi đơn có hàng trăm dòng. Một thiết kế tham chiếu có thể phù hợp cho E1 nhưng cần thêm round trip hoặc `$lookup` cho E2.

Đây là lý do quyết định mô hình phải dựa trên **tỷ lệ các loại truy vấn**: nếu 95% request chỉ xem metadata đơn và 5% mở chi tiết, chiến lược khác với trường hợp 95% request luôn lấy đầy đủ item.

## 11. Thu thập số đo thực thi

### 11.1. Xem execution plan thay vì chỉ nhìn số mili-giây

Với MongoDB, chạy `explain("executionStats")` cho từng truy vấn đọc:

~~~javascript
// Lấy một đơn theo khóa.
printjson(
  lab.orders_embedded
    .find({ _id: "ORD-000001" })
    .explain("executionStats")
);

printjson(
  lab.orders_reference
    .find({ _id: "ORD-000001" })
    .explain("executionStats")
);

// Tìm đơn qua SKU.
printjson(
  lab.orders_embedded
    .find({ "items.sku": "SKU-0007" })
    .explain("executionStats")
);

printjson(
  lab.order_items_reference
    .find({ sku: "SKU-0007" })
    .explain("executionStats")
);
~~~

Nên đọc các chỉ số như:

- **`totalKeysExamined`:** số mục index được xem xét trong phần truy vấn đó.
- **`totalDocsExamined`:** số document được xem xét.
- **`nReturned`:** số document trả về.
- **`executionTimeMillis`:** thời gian thực thi được engine báo cáo trong ngữ cảnh explain, không nhất thiết bằng thời gian từ ứng dụng.
- **`winningPlan`:** các bước truy cập như dùng index, fetch document hay scan; cách hiển thị thay đổi theo phiên bản MongoDB.

Đối với mô hình tham chiếu, phải tính **tất cả bước để tạo cùng kết quả nghiệp vụ**. Chỉ so sánh find `orders_embedded` với find `order_items_reference` mà bỏ qua bước lấy đầu đơn có thể tạo kết luận sai.

### 11.2. Đo thời gian trọn thao tác ở mức mongosh

Có thể định nghĩa hai hàm đọc chi tiết để benchmark cùng đầu ra:

~~~javascript
function loadEmbedded(orderId) {
  return lab.orders_embedded.findOne({ _id: orderId });
}

function loadReferenced(orderId) {
  const header = lab.orders_reference.findOne({ _id: orderId });
  if (header === null) return null;

  const items = lab.order_items_reference
    .find({ orderId })
    .sort({ lineId: 1 })
    .toArray()
    .map(({ _id, orderId, ...item }) => item);

  return { ...header, items };
}

function measure(label, operation, iterations = 300) {
  // Chạy thử trước để giảm ảnh hưởng khởi động.
  for (let i = 0; i < 20; i++) operation(i);

  const start = Date.now();

  for (let i = 0; i < iterations; i++) {
    operation(i);
  }

  const elapsedMs = Date.now() - start;

  print(label + ": total=" + elapsedMs + " ms"
    + ", average=" + (elapsedMs / iterations).toFixed(3) + " ms");
}

// Thay đổi ID giữa các lần để giảm thiên lệch do một tài liệu duy nhất.
measure("Embedded detail", i =>
  loadEmbedded("ORD-" + String((i % 3000) + 1).padStart(6, "0"))
);

measure("Referenced detail", i =>
  loadReferenced("ORD-" + String((i % 3000) + 1).padStart(6, "0"))
);
~~~

Đoạn đo dùng `Date.now()` đơn giản, phù hợp để học quy trình nhưng có độ phân giải và sai số của môi trường shell. Để có số liệu đáng tin cậy cho quyết định sản xuất, cần đo qua **ứng dụng thực** với client pool, concurrency, percentile p50/p95/p99, nhiều lần chạy, dữ liệu đại diện và cache đã được xử lý theo kế hoạch.

Một phép thử chỉ chạy 300 yêu cầu lần lượt trong `mongosh` chưa mô phỏng được tải đồng thời của hàng trăm người dùng. Nó giúp **quan sát sự khác nhau giữa các đường đi**, không bảo đảm dự báo hiệu năng sản xuất.

### 11.3. So sánh dung lượng và chỉ mục

Collection nhúng chứa ít document hơn nhưng mỗi document lớn hơn. Collection tham chiếu chứa nhiều document nhỏ hơn và thường có thêm khóa/field tham chiếu ở từng dòng.

~~~javascript
for (const name of [
  "orders_embedded",
  "orders_reference",
  "order_items_reference"
]) {
  const stats = lab.getCollection(name).stats();

  printjson({
    collection: name,
    count: stats.count,
    logicalSizeBytes: stats.size,
    storageSizeBytes: stats.storageSize,
    indexSizeBytes: stats.totalIndexSize
  });
}
~~~

Khi so sánh tổng dung lượng của mô hình B, phải cộng **`orders_reference` + `order_items_reference`**, kể cả index của cả hai. `stats.size` thể hiện kích thước dữ liệu logic theo cách MongoDB báo cáo; `storageSize` phản ánh dung lượng storage engine phân bổ và chịu ảnh hưởng bởi nén, cấp phát, xóa/ghi lại. Những số này không nên được suy diễn thành kích thước lưu trữ của mọi môi trường.

## 12. Bảng ghi kết quả sau khi thực nghiệm

Không cần cố đo một chỉ số duy nhất để tuyên bố “A thắng B”. Hãy ghi kết quả theo **một nghiệp vụ có đầu ra xác định**.

| Phép thử | Embedded (A) | Referenced (B) | Điều cần rút ra |
| --- | --- | --- | --- |
| Xem chi tiết một đơn | Điền số lần đọc, ms và docs/keys examined | Điền tổng cả đầu đơn và các dòng | Độ trễ và chi phí ghép |
| Danh sách đơn theo khách hàng | Điền ms, số document trả về | Điền ms, số document trả về | Khi không cần dòng hàng |
| Tìm đơn theo SKU | Điền index và tổng lượt đọc | Điền tìm dòng và lấy đầu đơn | Index mảng so với index dòng riêng |
| Tăng quantity và totalAmount | Một cập nhật document | Transaction hoặc quy trình phối hợp | Ranh giới nguyên tử và retry |
| Dung lượng dữ liệu | `orders_embedded` | Tổng hai collection | Chi phí nhúng so với metadata lặp |
| Kích thước khi mỗi đơn có nhiều dòng | Quan sát tài liệu tăng | Quan sát số document tăng | Giới hạn tăng trưởng và khả năng phân tách |

Trong phép thử cập nhật, **độ đúng nghiệp vụ** quan trọng ngang hiệu năng. Một thao tác nhanh nhưng có thể để tổng tiền sai không phải là phương án chấp nhận được.

### Kiểm soát yếu tố gây nhiễu

- Đo sau khi tạo đầy đủ index, tránh tính nhầm chi phí build index vào truy vấn.
- Dùng cùng kích thước và kiểu dữ liệu, cùng tần suất đọc/ghi của hai mô hình.
- Trộn thứ tự chạy A/B giữa các vòng để giảm ảnh hưởng cache, tải máy và thứ tự khởi động.
- Đo nhiều lượt, xem phân bố và percentile, không lấy một lần nhanh nhất.
- Đếm mọi lần trao đổi với database, bước ghép dữ liệu và network round trip của một yêu cầu.
- Khi thử cập nhật, seed lại trạng thái ban đầu hoặc dùng các đơn khác nhau với điều kiện đầu vào tương đương.
- Đọc log lỗi và kiểm tra tính đúng của dữ liệu trước khi so sánh số đo; không cộng các lần thất bại như thao tác hợp lệ.

Ở bộ dữ liệu nhỏ gồm ba dòng mỗi đơn, chênh lệch có thể không lớn. Muốn đánh giá tính mở rộng, cần thử thêm trường hợp **nhiều dòng trên mỗi đơn** và **tỷ lệ truy vấn metadata/chi tiết khác nhau**. Những trường hợp đó là thí nghiệm bổ sung, không nên thay đổi đầu vào ở giữa lần so sánh A và B.

## 13. Phân tích trade-off: đâu là nguyên nhân, đâu là triệu chứng?

### 13.1. Ranh giới của document quyết định thao tác nguyên tử

Với nhúng, `items[]` và `totalAmount` thuộc cùng một document. MongoDB có thể cập nhật chúng nguyên tử trong một lệnh. Với tham chiếu, dòng hàng và tổng tiền thuộc hai document, nên cần transaction hoặc quy trình khác để duy trì bất biến.

Lưu ý rằng **nguyên tử không đồng nghĩa với mọi bất biến nghiệp vụ đều tự được bảo vệ**. Nếu cập nhật số lượng mà không cập nhật tổng tiền dù nằm cùng document, kết quả vẫn sai. Thiết kế phải cập nhật đúng các field và dùng điều kiện kiểm soát đồng thời phù hợp.

### 13.2. Đọc một lần khác đọc có chọn lọc

Mô hình nhúng thuận lợi khi cần toàn bộ đơn hàng. Mô hình tham chiếu thuận lợi khi chỉ cần đầu đơn hoặc chỉ cần một số dòng. Nhưng khi tham chiếu, việc ghép có thể làm tăng round trip và độ phức tạp của ứng dụng.

Nếu một document có nhiều field lớn ít dùng, projection giúp giới hạn dữ liệu trả về nhưng không phải là bằng chứng rằng engine không đọc tài liệu lớn. Nên đo theo **đường truy cập thực tế**.

### 13.3. Tăng kích thước một document khác tăng số document

Một mảng nhúng có thể phát triển theo số dòng hàng. MongoDB có giới hạn kích thước BSON document (thường là **16 MiB** đối với MongoDB), nên không nên nhúng tập dữ liệu phát triển vô hạn vào một document. Mô hình tham chiếu không bị chính giới hạn đó ở cấp đầu đơn, nhưng số lượng document và index tăng lên; truy vấn nhiều dòng vẫn cần đọc nhiều dữ liệu.

Giới hạn tối đa không phải ngưỡng thiết kế tối ưu. Một document nhỏ hơn 16 MiB nhiều lần vẫn có thể gây vấn đề nếu liên tục được sửa, truyền hoặc đọc trong các tác vụ chỉ cần ít field.

### 13.4. Tham chiếu không mặc nhiên giống foreign key quan hệ

Field `orderId` trong `order_items_reference` chỉ là dữ liệu tham chiếu. MongoDB không tự động xóa mọi dòng khi document đơn hàng bị xóa. Ứng dụng cần xác định hành vi:

- Cấm xóa đơn nếu còn dòng hàng?
- Xóa các dòng liên quan trong một transaction?
- Đánh dấu đơn đã xóa và làm sạch các dòng bằng tác vụ nền?
- Giữ dữ liệu lịch sử theo quy tắc lưu trữ?

Cách nào phù hợp phụ thuộc nghiệp vụ, yêu cầu nhất quán và chính sách lưu giữ. Nếu không xác định, có thể xuất hiện **dòng hàng mồ côi**.

### 13.5. Đừng trộn snapshot lịch sử và dữ liệu danh mục hiện tại

Trong cả hai mô hình, `unitPrice` của dòng là **giá đã chốt khi đặt**. Danh mục sản phẩm hiện tại có thể vẫn nằm trong collection riêng `products` để quản lý tên, mô tả, ảnh và giá mới nhất. Một dòng đơn hàng có thể vừa lưu `sku` tham chiếu danh mục, vừa giữ `unitPrice` và tên sản phẩm tại thời điểm mua.

Nếu mô hình B chỉ giữ `productId` rồi lấy **giá hiện tại** từ `products`, màn hình đơn hàng lịch sử có thể cho ra tổng tiền sai. Khi đó vấn đề không nằm ở embedding hay referencing, mà do **hai mô hình không còn cùng semantics nghiệp vụ**.

## 14. Nếu số dòng trong mỗi đơn tăng mạnh

Phần seed gốc có ba dòng mỗi đơn. Hãy tưởng tượng ứng dụng chuyển sang các đơn sỉ có 500–2.000 dòng, hoặc dữ liệu biến thành **dòng sự kiện hoạt động** tăng không giới hạn.

| Câu hỏi | Nhúng | Tham chiếu |
| --- | --- | --- |
| Kích thước document đầu đơn | Tăng theo số dòng | Gần như không đổi theo số dòng nếu chỉ lưu metadata |
| Tải toàn bộ chi tiết | Một document nhưng payload lớn | Nhiều dòng, có thể phân trang |
| Cập nhật một dòng | Sửa phần tử của mảng trong document lớn | Sửa document dòng riêng |
| Lấy 20 dòng đầu | Có thể dùng projection/slice nhưng vẫn cần xem cách engine đọc | Có thể truy vấn giới hạn theo `orderId` và thứ tự |
| Tính tổng tiền | Dễ giữ nhất quán trong một lần update đơn nếu cùng document | Cần phối hợp khi tổng tiền lưu ở đầu đơn |
| Dòng hàng tăng không giới hạn | Rủi ro về kích thước document, cập nhật và đường đọc | Nhiều document riêng, vẫn cần quản lý phân trang/index |
| Xóa đơn và dòng | Xóa document đơn | Phải xử lý các dòng tham chiếu |

Trong trường hợp mảng tăng không giới hạn, tách dòng thành collection riêng thường hợp lý hơn. Tuy nhiên, nếu ứng dụng chỉ có 1–10 dòng/đơn và hầu hết request tải toàn bộ chi tiết, mô hình nhúng có thể đơn giản và hiệu quả hơn.

Một **thiết kế lai** cũng thường xuất hiện: document đơn chứa vài trường snapshot, địa chỉ giao hàng và một số dòng tóm tắt được giới hạn, còn dữ liệu chi tiết hoặc lịch sử khối lượng lớn nằm ở collection riêng. Mô hình lai cần hợp đồng đồng bộ rõ ràng nếu thông tin xuất hiện ở nhiều nơi.

## 15. Kết luận thiết kế từ cùng một nghiệp vụ

| Căn cứ lựa chọn | Nghiêng về nhúng | Nghiêng về tham chiếu |
| --- | --- | --- |
| Các thành phần thường được đọc cùng cha | Có | Không phải lúc nào cũng |
| Số phần tử con có giới hạn nhỏ và dự đoán được | Có | Không phải yêu cầu |
| Muốn cập nhật cha và con nguyên tử trong một document | Có lợi thế | Cần transaction/phối hợp nếu khác document |
| Thành phần con có vòng đời độc lập | Ít phù hợp hơn | Phù hợp hơn |
| Cần truy vấn/phân trang thành phần con độc lập | Có thể bất tiện | Phù hợp hơn |
| Danh sách con có thể tăng không giới hạn | Nguy cơ lớn | Thường thuận lợi hơn |
| Muốn tránh nhiều lần đọc và ghép cho trang chi tiết | Có lợi thế | Cần thêm bước ghép |
| Cần kiểm soát quyền, cập nhật và lưu trữ riêng của từng con | Cần thiết kế bổ sung | Có ranh giới riêng rõ hơn |

Với **đơn hàng bán lẻ có số dòng hợp lý**, một lựa chọn thường gặp là **nhúng dòng hàng đã chốt vào tài liệu đơn**, vì trang chi tiết luôn cần các dòng và giá lịch sử phải đi cùng đơn. Với **những dòng dữ liệu lớn, tăng liên tục, được truy vấn hoặc quản lý độc lập**, sử dụng **document tham chiếu** đáng cân nhắc hơn. Đây là định hướng để đặt giả thuyết, không thay thế việc đo trên tải thật.

## 16. Bài tập thực hành và câu hỏi suy luận

### Bài tập 1: cùng kết quả, khác số lần đọc

Ứng dụng mở màn hình chi tiết đơn 500 lần mỗi phút. Mỗi đơn có 4 dòng và phải hiển thị toàn bộ dòng ngay lập tức. Hãy xác định đường đọc của A và B, rồi dự đoán mô hình nào có thể giảm số round trip.

**Gợi ý:** Mô hình nhúng thường đọc một document để lấy cả đầu đơn và dòng hàng; mô hình tham chiếu đọc đầu đơn và các dòng hoặc dùng `$lookup`. Cần đo độ trễ thật để xác nhận.

### Bài tập 2: cập nhật có điều kiện

Mỗi lần thay đổi `quantity`, ứng dụng phải giữ `totalAmount` đúng. Nếu tăng dòng `L2` thêm một đơn vị nhưng request bị gửi lại do timeout, điều gì có thể xảy ra?

**Gợi ý:** `$inc` lặp có thể tăng hai lần nếu không có điều kiện hoặc mã idempotency. Với nhúng, dùng điều kiện theo quantity/version trong một document; với tham chiếu, còn phải giải quyết tính nguyên tử giữa item và đầu đơn.

### Bài tập 3: tìm theo SKU

Vì sao mô hình nhúng cần chỉ mục trên `items.sku`, trong khi mô hình tham chiếu có thể dùng index `{ sku: 1, orderId: 1 }`? Nếu API yêu cầu thêm `status`, mô hình B cần làm gì?

**Gợi ý:** Hai chỉ mục hỗ trợ hai bố cục dữ liệu khác nhau. Mô hình B cần lấy đầu đơn theo `orderId` hoặc join để có `status`.

### Bài tập 4: dữ liệu tăng không giới hạn

Một tài khoản có thể tạo một triệu dòng sự kiện. Nhóm đề xuất nhúng toàn bộ sự kiện vào `users.events[]` để chỉ cần một document. Điều gì cần xem xét?

**Gợi ý:** Kích thước document, giới hạn BSON, tần suất cập nhật, tải từng trang sự kiện, phân trang, lập chỉ mục và vòng đời lưu trữ. Collection sự kiện riêng theo `userId` và thời gian có thể phù hợp hơn.

### Bài tập 5: thay đổi giá sản phẩm

Hôm nay giá niêm yết `SKU-0005` đổi từ 20.000 lên 25.000 VND. Có nên cập nhật `unitPrice` trong những đơn đã thanh toán?

**Gợi ý:** Thông thường không, nếu `unitPrice` là snapshot giá đã chốt. Có thể cập nhật collection `products` chứa giá hiện tại, giữ nguyên giá lịch sử trong dòng đơn hàng, bất kể dòng đang nhúng hay tham chiếu.

### Bài tập 6: tự điền kết quả thực nghiệm

Sau khi chạy phần 6–11 trên máy thử nghiệm, hãy lập báo cáo có các mục: **đầu ra nghiệp vụ có trùng không**, **số lần đọc/ghi**, **docs/keys examined**, **độ trễ đo được**, **dung lượng dữ liệu + index**, **cách bảo đảm tính nguyên tử**. Đưa ra khuyến nghị cho trường hợp 90% request đọc chi tiết và cho trường hợp 90% request chỉ liệt kê đầu đơn.

**Gợi ý:** Hai workload có thể dẫn đến hai quyết định khác nhau. Kết luận phải nêu phạm vi dữ liệu và phương pháp đo; không coi kết quả từ 3.000 đơn × 3 dòng là định luật cho mọi hệ thống.

## 17. Ghi nhớ qua một trục lựa chọn

**Nhúng** đặt dữ liệu có quan hệ chặt chẽ trong **cùng ranh giới document**, nên thuận tiện cho đọc và cập nhật nguyên tử của một đối tượng đầy đủ. **Tham chiếu** đặt dữ liệu thành **những document có định danh riêng**, giúp quản lý phần con độc lập và kiểm soát tăng trưởng, nhưng làm xuất hiện bước tra cứu/ghép và đôi khi cần transaction qua nhiều document.

Thực nghiệm có giá trị khi **giữ nguyên một nghiệp vụ và cùng nội dung dữ liệu**, thay đổi cách biểu diễn, rồi quan sát **đường truy vấn, chỉ mục, cách ghi và độ đúng sau cập nhật**. Đây là cách biến câu hỏi “nhúng hay tham chiếu?” thành quyết định thiết kế có thể kiểm chứng.
