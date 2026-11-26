# Nhúng tài liệu, tham chiếu khóa và phi chuẩn hóa theo nhu cầu trong Spring Data Couchbase

Trong cơ sở dữ liệu quan hệ, nhóm phát triển thường bắt đầu từ bảng, khóa ngoại và `JOIN`. Với Couchbase, điểm khởi đầu phù hợp hơn là **mẫu truy cập dữ liệu**: ứng dụng cần lấy những gì cùng lúc, đối tượng nào được cập nhật độc lập, số lượng phần tử liên quan có thể tăng đến đâu, và khi dữ liệu thay đổi thì cần nhất quán đến mức nào.

Ba kỹ thuật quan trọng để biểu diễn quan hệ giữa các thực thể trong Couchbase là:

1. **Nhúng (embedding):** đặt object hoặc mảng con ngay trong document cha, để có thể đọc hoặc thay đổi như một đơn vị dữ liệu.
2. **Tham chiếu bằng khóa (key reference):** lưu document ID của thực thể liên quan, truy cập nó bằng KV API hoặc kết hợp dữ liệu qua SQL++ khi cần.
3. **Phi chuẩn hóa có chủ đích (denormalization):** lưu thêm một phần thông tin từ thực thể khác để tối ưu truy vấn hoặc bảo tồn bản chụp lịch sử, kèm chính sách xử lý khi dữ liệu nguồn thay đổi.

Không có lựa chọn nào tốt nhất cho tất cả quan hệ. Nhúng mọi thứ có thể tạo document quá lớn và điểm ghi nóng; tham chiếu mọi thứ có thể khiến ứng dụng phải thực hiện nhiều lượt đọc; sao chép mọi thứ lại dẫn đến khó đồng bộ và sai lệch dữ liệu.

Bài thuộc chương **Quan hệ và JOIN** của module **SPRING_DATA_COUCHBASE**. Nội dung gắn với document mapping, repository, `CouchbaseTemplate` và SQL++, thiết kế bucket/scope/collection, secondary index, TTL, CAS, giao dịch và reactive API. Mục tiêu xuyên suốt là **chọn mô hình dữ liệu phù hợp với từng nhu cầu đọc–ghi và yêu cầu vận hành**, thay vì mô phỏng nguyên xi quan hệ trong một hệ quản trị SQL.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích điểm khác biệt giữa nhúng object, tham chiếu document ID và phi chuẩn hóa dữ liệu trong Couchbase.
2. Chọn cách biểu diễn cho quan hệ một–một, một–nhiều và nhiều–nhiều dựa trên cardinality, vòng đời, tần suất đọc/ghi và chủ sở hữu dữ liệu.
3. Tổ chức entity Spring Data Couchbase với `@Document`, `@Id`, `@Scope` và `@Collection`; phân biệt một field ID tham chiếu với cơ chế tự động tải quan hệ.
4. Truy cập quan hệ bằng KV repository, `CouchbaseTemplate` hoặc SQL++ `JOIN ... ON KEYS`; phân biệt `JOIN` với `UNNEST` trên mảng đã nhúng.
5. Xác định cách lập chỉ mục cho bên lọc, bên tìm kiếm và collection chứa phần tử tách rời.
6. Thiết kế quy tắc đồng bộ, làm mới snapshot, xóa/TTL, CAS, giao dịch và xử lý quan hệ bị đứt.
7. Nhận biết khi nào cần chuyển một mảng nhúng lớn thành collection riêng hoặc tạo read model phi chuẩn hóa.

## 2. Tình huống nghiệp vụ: khách hàng, đơn hàng, dòng hàng và sản phẩm

Giả sử hệ thống bán hàng lưu trong bucket `commerce`:

```text
commerce
├── scope crm
│   └── collection customers
├── scope catalog
│   └── collection products
└── scope sales
    ├── collection orders
    ├── collection order_lines   (chỉ khi cần tách dòng hàng)
    └── collection order_views   (chỉ khi cần read model)
```

Có ba nhóm dữ liệu với hành vi khác nhau:

| Dữ liệu | Nhu cầu chính | Đặc tính thay đổi |
| --- | --- | --- |
| Khách hàng | Xem hồ sơ, email, tên hiển thị và địa chỉ mặc định | Có thể đổi tên/email/địa chỉ |
| Đơn hàng | Đọc chi tiết, trạng thái, giá thanh toán, địa chỉ nhận hàng tại thời điểm mua | Trạng thái thay đổi; giá đã chốt phải có ý nghĩa lịch sử |
| Sản phẩm | Tra cứu tồn tại, giá hiện tại, mô tả và catalog | Giá và tên có thể thay đổi theo thời gian |

Ví dụ document khách hàng, ID `customer::C-42` tại `commerce.crm.customers`:

```json
{
  "_class": "customer",
  "tenantId": "TENANT-A",
  "displayName": "Nguyen An",
  "email": "an@example.test",
  "defaultAddress": {
    "city": "Ha Noi",
    "district": "Ba Dinh"
  }
}
```

Document sản phẩm, ID `product::SKU-42` tại `commerce.catalog.products`:

```json
{
  "_class": "product",
  "tenantId": "TENANT-A",
  "sku": "SKU-42",
  "name": "Binh giu nhiet",
  "currentPrice": 390000,
  "status": "ACTIVE"
}
```

Document đơn hàng, ID `order::1001` tại `commerce.sales.orders`:

```json
{
  "_class": "salesOrder",
  "tenantId": "TENANT-A",
  "customerId": "customer::C-42",
  "customerNameAtPurchase": "Nguyen An",
  "status": "PAID",
  "createdAt": "2026-11-20T08:15:00Z",
  "shippingAddress": {
    "city": "Ha Noi",
    "district": "Ba Dinh",
    "line1": "12 Example Street"
  },
  "items": [
    {
      "lineId": "L1",
      "productId": "product::SKU-42",
      "productNameAtPurchase": "Binh giu nhiet",
      "unitPriceAtPurchase": 350000,
      "quantity": 2
    }
  ],
  "total": 700000,
  "currency": "VND"
}
```

Document đơn hàng này cố ý **kết hợp cả ba kỹ thuật**:

- `shippingAddress` và `items` là dữ liệu **nhúng**, phục vụ đọc đầy đủ đơn hàng và lưu thông tin cần chốt theo đơn.
- `customerId` và `productId` là **document ID tham chiếu**, dùng khi cần hồ sơ khách hàng hoặc sản phẩm hiện tại.
- `customerNameAtPurchase`, `productNameAtPurchase` và `unitPriceAtPurchase` là dữ liệu **phi chuẩn hóa dạng snapshot**, không nhằm luôn khớp giá trị catalog hiện tại.

Đây là một mô hình minh họa, không phải schema bắt buộc. Việc document ID có tiền tố chỉ là quy ước để dễ định danh; cần đảm bảo ID không va chạm và có phạm vi tenant rõ ràng trong kiến trúc thật.

## 3. Chọn mô hình từ câu hỏi truy cập dữ liệu

### 3.1. Bốn trục quyết định

Trước khi viết Java entity, hãy trả lời:

| Câu hỏi | Khi thiên về nhúng | Khi thiên về tham chiếu |
| --- | --- | --- |
| **Đọc cùng nhau?** | Phần con gần như luôn được trả cùng cha | Phần con thường được truy cập riêng |
| **Vòng đời?** | Phần con thuộc về cha và thường bị xóa cùng cha | Thực thể có vòng đời/owner độc lập |
| **Quy mô?** | Số phần tử nhỏ, có giới hạn rõ ràng | Số phần tử lớn hoặc tăng không giới hạn |
| **Cập nhật?** | Thay đổi cùng cha, ít tranh chấp ghi | Cập nhật độc lập/tần suất cao |

Thêm trục thứ năm: **ý nghĩa lịch sử và độ mới**. Một field cần giữ nguyên tại thời điểm tạo đơn nên có thể phải được sao chép vào đơn hàng; một thông tin cần luôn mới, như trạng thái tài khoản hiện tại, nên có nguồn dữ liệu được định danh rõ và chiến lược lấy/đồng bộ phù hợp.

### 3.2. Bảng lựa chọn nhanh

| Bài toán | Lựa chọn khởi đầu hợp lý | Vì sao |
| --- | --- | --- |
| Địa chỉ giao hàng được chốt theo đơn | Nhúng snapshot vào order | Thuộc lịch sử đơn và đọc cùng đơn |
| Vài dòng hàng trong một đơn có giới hạn | Nhúng mảng `items` | Đọc/ghi một aggregate nhỏ |
| Hồ sơ khách hàng dùng lại ở nhiều đơn | Tham chiếu bằng `customerId` | Khách hàng có vòng đời và quyền cập nhật riêng |
| Giá và tên sản phẩm tại thời điểm mua | Nhúng snapshot giá/tên, đồng thời giữ `productId` | Không làm hóa đơn cũ đổi khi catalog thay đổi |
| 100.000 sự kiện của một đơn | Collection sự kiện riêng, tham chiếu `orderId` | Cardinality lớn, ghi và phân trang độc lập |
| Danh sách dashboard cần tên khách hàng rất thường xuyên | Read model phi chuẩn hóa có hợp đồng độ mới | Tránh join lặp lại, nhưng phải duy trì bản sao |
| Danh sách đơn hàng theo ID cụ thể | KV `findById` | Không cần query index chỉ để tra ID |

Đây là điểm xuất phát để thiết kế. Nếu workload hay yêu cầu nhất quán khác đi, lựa chọn có thể thay đổi.

## 4. Nhúng object và mảng: coi đơn hàng là một aggregate

### 4.1. Đọc một document lấy đủ thông tin của aggregate

Với `shippingAddress` và `items` nằm trong đơn hàng:

```sql
SELECT META(o).id AS orderId,
       o.status,
       o.shippingAddress,
       o.items,
       o.total
FROM `commerce`.`sales`.`orders` AS o
USE KEYS "order::1001";
```

Hoặc dùng repository `findById("order::1001")` theo KV. Khi biết ID, KV thường là đường truy cập trực tiếp; không cần secondary index của Query Service cho thao tác này.

Một document thể hiện các dữ liệu được quản lý cùng nhau. Khi ứng dụng thay đổi toàn bộ document như một KV mutation thành công, không có tình huống chỉ cập nhật được một nửa nội dung của chính mutation đó. Tuy nhiên, việc kiểm soát xung đột ghi vẫn quan trọng khi nhiều request cùng cập nhật mảng `items` hoặc `status`.

### 4.2. Vì sao địa chỉ giao hàng nên nhúng?

Địa chỉ mặc định của khách hàng có thể thay đổi, nhưng địa chỉ đã được dùng để giao đơn ngày 20/11 phải giữ lại để tra cứu vận chuyển, đối soát và khiếu nại. Nếu chỉ lưu `customerId` rồi luôn đọc `defaultAddress` hiện tại, hệ thống có thể hiển thị **địa chỉ mới cho một đơn cũ**.

Do đó:

```json
{
  "customerId": "customer::C-42",
  "shippingAddress": {
    "city": "Ha Noi",
    "district": "Ba Dinh",
    "line1": "12 Example Street"
  }
}
```

là một lựa chọn có ý nghĩa nghiệp vụ: `shippingAddress` là **snapshot của đơn**, không phải bản copy phải đồng bộ liên tục với hồ sơ khách hàng.

### 4.3. Vì sao mảng dòng hàng vừa tốt vừa nguy hiểm?

Nhúng `items` phù hợp khi:

- Số dòng hàng tối đa có thể quản lý được.
- Dòng hàng gắn chặt với đơn và thường được đọc cùng đơn.
- Phần lớn thay đổi dòng hàng diễn ra trong cùng luồng cập nhật đơn.
- Không cần thường xuyên phân trang từng dòng hàng qua nhiều request.

Nhưng hãy cẩn trọng khi `items` tăng không giới hạn, nhiều tác nhân cùng sửa các phần tử khác nhau hoặc cần đọc từng item độc lập. Một thay đổi trong mảng lớn có thể dẫn đến nhiều dữ liệu phải xử lý hơn, tăng kích thước document và làm khó xử lý xung đột cập nhật.

Couchbase có các giới hạn về kích thước document theo phiên bản/cấu hình. Không dựa vào việc “hiện tại mới có 10 item” nếu nghiệp vụ có thể cho phép hàng trăm nghìn item trong tương lai.

### 4.4. Khi query bên trong mảng, đó không phải `JOIN` giữa hai collection

Tìm đơn có SKU:

```sql
SELECT META(o).id AS orderId, o.status
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND ANY i IN o.items
      SATISFIES i.productId = "product::SKU-42"
      END;
```

Nếu cần một hàng kết quả cho mỗi dòng hàng, dùng `UNNEST`:

```sql
SELECT META(o).id AS orderId,
       i.lineId,
       i.productId,
       i.quantity
FROM `commerce`.`sales`.`orders` AS o
UNNEST o.items AS i
WHERE o.tenantId = "TENANT-A"
  AND i.productId = "product::SKU-42";
```

`ANY` trả **document cha nào thỏa**; `UNNEST` mở rộng phần tử mảng thành những **hàng riêng**. Hai phép có ngữ nghĩa và cardinality khác nhau. `UNNEST` không yêu cầu tạo một collection `items` riêng: dữ liệu vốn nằm trong JSON của order.

## 5. Tham chiếu document ID: khi dữ liệu có vòng đời độc lập

### 5.1. Lưu ID, không lưu toàn bộ khách hàng trong mọi đơn

Order chỉ giữ:

```json
{
  "tenantId": "TENANT-A",
  "customerId": "customer::C-42",
  "status": "PAID"
}
```

Customer được lưu độc lập ở `commerce.crm.customers`. Nhờ vậy, khi email khách hàng thay đổi, không cần sửa email trên hàng nghìn order nếu order không chủ đích lưu email lịch sử.

**ID tham chiếu không phải foreign key tự kiểm tra.** Một document order có thể chứa `customerId` không tồn tại, đã bị xóa, hoặc thuộc tenant khác nếu ứng dụng không kiểm soát. Couchbase không tự áp đặt ràng buộc khóa ngoại kiểu SQL chỉ vì có chuỗi `customerId`.

### 5.2. Dùng KV lookup nếu đã biết ID của cả hai bên

Một luồng lấy chi tiết đơn và tên khách hàng:

```text
GET order::1001 từ sales.orders
    |
    +-- customerId = customer::C-42
           |
           +-- GET customer::C-42 từ crm.customers
    |
    +-- kết hợp kết quả trong service
```

Đây có thể là hai lượt KV read từ hai collection. Với một màn hình chi tiết, chi phí đơn giản và dễ kiểm soát. Nếu trang list có 100 order của 100 khách hàng, thực hiện một KV read độc lập cho mỗi hàng có thể dẫn đến **N+1 reads** ở tầng service. Khi đó cần xem xét bulk fetch, SQL++ join hoặc read model.

### 5.3. Đừng coi quan hệ là association tự tải giống ORM

Một field Java:

```java
private String customerId;
```

là **giá trị ID**. Nó không tự biến thành navigation property có lazy loading, cascade save/delete hay foreign-key constraint như một mô hình JPA/Hibernate. Các cơ chế hỗ trợ association cụ thể phụ thuộc phiên bản/thư viện, nhưng thiết kế an toàn ở đây là **ứng dụng chủ động quyết định khi nào lấy customer và xử lý kết quả không tồn tại**.

Nếu dùng một API/thư viện có tính năng ánh xạ tham chiếu riêng, vẫn phải đánh giá cách nó sinh truy vấn, độ trễ và vòng đời dữ liệu; không giả định phép JOIN được thực hiện hoàn toàn miễn phí.

## 6. Phi chuẩn hóa có chủ đích: cache đọc hay snapshot nghiệp vụ?

Hai kiểu sao chép nhìn giống nhau trong JSON nhưng cần chính sách cập nhật khác nhau.

### 6.1. Snapshot bất biến theo sự kiện nghiệp vụ

Khi khách mua sản phẩm có giá 350.000 VND, catalog có thể tăng giá ngày hôm sau lên 390.000 VND. Nếu đơn hàng chỉ tham chiếu `productId` rồi luôn lấy `currentPrice` từ catalog, hóa đơn cũ sẽ tính sai.

Do đó, dòng hàng nên lưu:

```json
{
  "productId": "product::SKU-42",
  "productNameAtPurchase": "Binh giu nhiet",
  "unitPriceAtPurchase": 350000,
  "quantity": 2
}
```

`productId` cho phép truy cập catalog hiện tại, còn `unitPriceAtPurchase` và `productNameAtPurchase` bảo tồn thông tin của giao dịch. Nếu chính sách nghiệp vụ cho phép điều chỉnh hóa đơn, đó phải là một sự kiện/luồng thay đổi được quản lý rõ, không phải tự đồng bộ snapshot khi giá sản phẩm đổi.

### 6.2. Bản sao để tăng tốc đọc, cần quy tắc làm mới

Một dashboard thường hiển thị tên khách hàng ngay cạnh order:

```json
{
  "customerId": "customer::C-42",
  "customerDisplayNameCache": "Nguyen An",
  "customerProfileVersion": 12
}
```

Đây là **read cache/denormalized field** có thể cần cập nhật khi customer đổi tên. Khác với `customerNameAtPurchase`, field `customerDisplayNameCache` thể hiện tên hiện tại **trong một giới hạn độ trễ được chấp nhận**.

Phải định nghĩa:

- **Nguồn chân lý:** `commerce.crm.customers`.
- **Đơn vị bản sao:** field nào được copy, field nào không.
- **Trigger cập nhật:** thay đổi hồ sơ, event, job đồng bộ hoặc on-demand refresh.
- **Độ trễ chấp nhận:** vài giây, vài phút hay phải nhất quán tức thời?
- **Chống ghi cũ đè ghi mới:** version, CAS hoặc sequencing sự kiện.
- **Khả năng sửa sai:** backfill/reconciliation nếu consumer bỏ lỡ sự kiện.

Nếu ứng dụng không có khả năng bảo trì bản sao, hãy ưu tiên đọc tham chiếu trực tiếp hoặc giữ một snapshot bất biến có tên field diễn đạt rõ ý nghĩa.

### 6.3. Phân biệt hai cột tên ngay từ lúc thiết kế

| Trường | Ý nghĩa | Có cập nhật khi Customer đổi tên? |
| --- | --- | --- |
| `customerId` | Khóa tham chiếu đến Customer | Thường không; thay khách hàng là nghiệp vụ khác |
| `customerNameAtPurchase` | Tên chụp tại thời điểm mua | Không, trừ nghiệp vụ điều chỉnh lịch sử có kiểm soát |
| `customerDisplayNameCache` | Tên hiện tại được sao chép để tối ưu đọc | Có, theo chính sách làm mới |
| `Customer.displayName` | Nguồn chân lý cho tên hiện tại | Có, khi hồ sơ được sửa |

Sử dụng cùng một tên field `customerName` cho cả snapshot và cache có thể làm chính sách cập nhật mơ hồ. Đặt tên phản ánh **hợp đồng dữ liệu** giúp tránh lỗi nghiệp vụ.

## 7. Mô hình quan hệ một–một, một–nhiều và nhiều–nhiều

### 7.1. Một–một hoặc một–ít

Ví dụ hồ sơ thanh toán có một `billingAddress` và một `shippingAddress` cho mỗi đơn. Nếu chúng gắn chặt với đơn, tương đối nhỏ và ít được cập nhật độc lập, nhúng phù hợp.

Nếu một đối tượng cần phân quyền khác, chứa dữ liệu nhạy cảm hoặc có vòng đời xóa khác (ví dụ hồ sơ xác minh danh tính), cân nhắc collection riêng dù quan hệ chỉ một–một. **Cardinality thấp không tự quyết định phải nhúng.**

### 7.2. Một–nhiều có giới hạn

Order có 1–20 dòng hàng, việc đọc chi tiết gần như luôn cần cả danh sách: nhúng `items` có thể tiết kiệm lượt đọc và đơn giản hóa tính toàn vẹn trong một aggregate.

Vẫn cần kiểm tra ngưỡng nghiệp vụ. Nếu sản phẩm cho phép mỗi order có hàng chục nghìn dòng, chiến lược nhúng ban đầu có thể không còn đúng.

### 7.3. Một–nhiều tăng không giới hạn

Một order có thể có hàng chục nghìn sự kiện trạng thái/fulfillment sau nhiều năm. Thay vì tăng mãi mảng `events` trong document:

```json
{
  "orderId": "order::1001",
  "eventType": "STATUS_CHANGED",
  "eventTime": "2026-11-20T09:00:00Z"
}
```

lưu mỗi sự kiện dưới một ID riêng tại `commerce.sales.order_events`. Có thể phân trang và lập index:

```sql
CREATE INDEX ix_events_by_order_time
ON `commerce`.`sales`.`order_events`(
    `tenantId`,
    `orderId`,
    `eventTime` DESC
);
```

Tham chiếu `orderId` cho phép truy vấn các sự kiện liên quan mà không phải cập nhật document cha sau mọi lần thêm event.

### 7.4. Nhiều–nhiều

Ví dụ người dùng theo dõi nhiều danh sách yêu thích, một sản phẩm thuộc nhiều danh sách. Nếu số quan hệ lớn hoặc cần thêm metadata như thời điểm theo dõi và vai trò, có thể biểu diễn **document liên kết**:

```json
{
  "tenantId": "TENANT-A",
  "listId": "wishlist::W-9",
  "productId": "product::SKU-42",
  "addedAt": "2026-11-20T12:00:00Z"
}
```

Lưu vào collection `wishlist_items` với document ID ổn định/duy nhất theo quy tắc nghiệp vụ, chẳng hạn được xác định từ cặp `listId`–`productId`. Cần cân nhắc escape/chuẩn hóa ID để tránh va chạm và không làm lộ thông tin nhạy cảm.

Một index cho chiều “các sản phẩm của danh sách” và một index khác cho chiều “danh sách chứa sản phẩm” có thể cần thiết, nhưng chỉ tạo khi có truy vấn thực:

```sql
CREATE INDEX ix_wishlist_items_by_list
ON `commerce`.`sales`.`wishlist_items`(
    `tenantId`, `listId`, `addedAt` DESC
);

CREATE INDEX ix_wishlist_items_by_product
ON `commerce`.`sales`.`wishlist_items`(
    `tenantId`, `productId`
);
```

Index của collection `wishlist_items` không tự lập chỉ mục cho `products` hoặc `orders`.

## 8. Spring Data Couchbase: mapping nhúng và field tham chiếu

### 8.1. Entity Order dùng nhúng và reference ID

Ví dụ Java:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@TypeAlias("salesOrder")
@Scope("sales")
@Collection("orders")
public class SalesOrder {
    @Id
    private String id;

    @Version
    private Long version;

    private String tenantId;
    private String customerId;
    private String customerNameAtPurchase;
    private String status;
    private Instant createdAt;
    private ShippingAddress shippingAddress;
    private List<OrderLine> items;
    private long total;

    // Constructor, getter, setter được lược bỏ.
}
```

Hai kiểu `ShippingAddress` và `OrderLine` là các lớp giá trị bình thường được mapping vào các field nested của JSON:

```java
public class ShippingAddress {
    private String city;
    private String district;
    private String line1;
    // Constructor, getter, setter được lược bỏ.
}

public class OrderLine {
    private String lineId;
    private String productId;
    private String productNameAtPurchase;
    private long unitPriceAtPurchase;
    private int quantity;
    // Constructor, getter, setter được lược bỏ.
}
```

Ở mô hình này, `OrderLine` **không** là entity Couchbase riêng và không có repository riêng. Spring Data lưu danh sách `items` như các object lồng trong document `SalesOrder`. Khi cần đọc một order theo ID, dữ liệu dòng hàng đã nằm trong cùng JSON.

`@Version` trên entity Couchbase được Spring Data dùng hỗ trợ optimistic concurrency dựa trên CAS theo cơ chế phiên bản phù hợp; cách lưu/thao tác metadata cần được kiểm tra theo phiên bản Spring Data Couchbase đang dùng. CAS giúp phát hiện việc ghi đè phiên bản cũ, chứ không phải tự động merge mọi thay đổi mảng của hai request cạnh tranh.

### 8.2. Entity Customer độc lập

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@TypeAlias("customer")
@Scope("crm")
@Collection("customers")
public class Customer {
    @Id
    private String id;
    private String tenantId;
    private String displayName;
    private String email;
    // Constructor, getter, setter được lược bỏ.
}
```

Bucket `commerce` không được tự suy ra từ hai annotation `@Scope`/`@Collection`; nó phải đến từ cấu hình Couchbase/operations mapping đang hoạt động. Nếu order và customer thuộc bucket khác nhau, cần xác định rõ bucket ở mỗi đường truy cập.

### 8.3. Repository chỉ đọc quan hệ khi service yêu cầu

```java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface SalesOrderRepository
        extends CouchbaseRepository<SalesOrder, String> {
}

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {
}
```

Service có thể lấy hai document bằng ID:

```java
import java.util.Optional;

public class OrderDetailsService {
    private final SalesOrderRepository orders;
    private final CustomerRepository customers;

    public OrderDetailsService(
            SalesOrderRepository orders,
            CustomerRepository customers) {
        this.orders = orders;
        this.customers = customers;
    }

    public Optional<OrderWithCustomer> findByOrderId(String orderId) {
        return orders.findById(orderId)
                .map(order -> {
                    Customer customer = customers
                        .findById(order.getCustomerId())
                        .filter(c -> c.getTenantId().equals(order.getTenantId()))
                        .orElse(null);
                    return new OrderWithCustomer(order, customer);
                });
    }

    public record OrderWithCustomer(SalesOrder order, Customer customer) {}
}
```

Đoạn code dùng các getter được lược bỏ ở entity và Java record (Java 16+). Việc trả `customer = null` là **chính sách minh họa** khi reference không còn hợp lệ hoặc tenant không khớp; API thật có thể chọn lỗi `404`, fallback snapshot hoặc cảnh báo dữ liệu tùy nghiệp vụ.

Quan trọng: vì đây là **hai lượt đọc độc lập**, không thể mặc nhiên khẳng định kết quả thể hiện cùng một thời điểm snapshot toàn hệ thống. Nếu cần nhất quán nhiều document theo giao dịch, thiết kế truy cập/transaction riêng theo API Couchbase được hỗ trợ.

### 8.4. Với nhiều order, tránh vòng lặp N+1

Một cách thường chậm:

```java
for (SalesOrder order : ordersPage) {
    Customer c = customerRepository
        .findById(order.getCustomerId())
        .orElse(null);
    // Tạo một dòng của trang danh sách.
}
```

Nó có thể phát sinh một lượt KV read cho mỗi order. Nếu nhiều order thuộc cùng customer, nên **khử trùng lặp customerId**, lấy dữ liệu theo lô hoặc dùng join/read model phù hợp. `findAllById` và các API bulk/reactive cụ thể cần được sử dụng theo phiên bản; không mặc định một API bulk tương đương một round trip vật lý.

Ngoài tổng số lượt đọc, hãy đo p95 latency, mức đồng thời, timeout, số customer phân biệt và phân bố dữ liệu. Một số trường hợp truy vấn SQL++ join gọn hơn; một số trường hợp KV lookup ít và dữ liệu đã cache lại hiệu quả hơn.

## 9. SQL++ `JOIN ... ON KEYS`: kết hợp hai document đã có khóa

### 9.1. Key join khi bên phải được tìm theo document ID

Order giữ `customerId = "customer::C-42"`, trùng với document ID bên customer. SQL++ có thể dùng **key join**:

```sql
SELECT META(o).id AS orderId,
       o.status,
       o.createdAt,
       META(c).id AS customerId,
       c.displayName AS customerName
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`crm`.`customers` AS c
  ON KEYS o.customerId
WHERE o.tenantId = "TENANT-A"
  AND c.tenantId = o.tenantId
ORDER BY o.createdAt DESC
LIMIT 20;
```

Ý nghĩa:

- Tập `orders` là phía trái; `customerId` của mỗi order chỉ ra document ID của phía phải.
- `JOIN ... ON KEYS o.customerId` yêu cầu kết hợp theo khóa của document customer, không phải theo một cột SQL có foreign key constraint.
- `c.tenantId = o.tenantId` là điều kiện kiểm soát dữ liệu cùng tenant trong ví dụ. Quyền truy cập nghiệp vụ vẫn phải kiểm tra ở tầng service/API.
- Với inner join, order **không có customer tương ứng** sẽ không tạo hàng kết quả.

Đây là một câu SQL++ mẫu với đường dẫn collection đầy đủ. Để tối ưu thực tế, phải kiểm tra `EXPLAIN` trên phiên bản Couchbase đang dùng, chỉ mục phục vụ việc lọc/sắp xếp phía order và đường lookup bên customer.

### 9.2. `LEFT JOIN` khi cần giữ đơn dù khách hàng đã không còn

Trong hệ thống có chính sách xóa/tách customer, có thể vẫn cần hiển thị các đơn hàng lịch sử. Ví dụ:

```sql
SELECT META(o).id AS orderId,
       o.customerNameAtPurchase AS nameAtPurchase,
       c.displayName AS currentCustomerName
FROM `commerce`.`sales`.`orders` AS o
LEFT JOIN `commerce`.`crm`.`customers` AS c
  ON KEYS o.customerId
WHERE o.tenantId = "TENANT-A"
  AND o.status = "PAID"
LIMIT 20;
```

Đối với order có customer thiếu, những field của phía customer trong kết quả có thể là `MISSING`/`NULL` tùy phép chiếu và ngữ nghĩa SQL++. Nếu API cần giá trị dự phòng, có thể dùng một biểu thức như `COALESCE` trong projection sau khi đã thống nhất cách xử lý dữ liệu thiếu.

**Lưu ý:** Nếu thêm `AND c.tenantId = o.tenantId` vào `WHERE` của left join mà không xử lý trường hợp vắng customer, điều kiện đó có thể loại luôn order chưa join được, khiến hành vi giống inner join. Muốn giữ order, hãy thiết kế predicate và fallback cẩn thận, kiểm thử trường hợp `MISSING`.

### 9.3. `JOIN ... ON` theo điều kiện không phải document ID

Khi liên kết theo một thuộc tính, ví dụ customer có field `externalCode` và order lưu `customerExternalCode`, có thể cần một dạng ANSI join:

```sql
SELECT META(o).id AS orderId, c.displayName
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`crm`.`customers` AS c
  ON o.customerExternalCode = c.externalCode
WHERE o.tenantId = "TENANT-A"
  AND c.tenantId = o.tenantId;
```

Truy vấn này **không** có khóa document bên phải trong order, nên không phải key join. Cần xem chỉ mục cho trường `externalCode`, lọc tenant, cardinality, plan join và nguy cơ mã trùng. Nếu có thể lưu document ID ổn định của customer, tham chiếu theo ID thường làm quan hệ rõ ràng hơn.

Không nên kết luận mọi `JOIN` đều chậm hoặc mọi key join đều nhanh: chi phí còn phụ thuộc số bản ghi phía trái, số field trả về, dữ liệu, chỉ mục và kế hoạch thực.

## 10. `UNNEST` khác `JOIN`: làm việc với dữ liệu đã nhúng

So sánh các mô hình:

```text
Order + items nhúng:
  orders JSON -> UNNEST o.items -> từng item trong cùng document

Order + Customer tham chiếu:
  orders.customerId -> JOIN customers ON KEYS -> document ở collection khác
```

### 10.1. Không nhầm số hàng với số đơn

Một order có 3 item, câu `UNNEST` có thể tạo 3 hàng. Nếu đặt `LIMIT 20` sau `UNNEST`, đó là giới hạn **hàng item**, không nhất thiết là 20 order phân biệt.

Ví dụ:

```sql
SELECT META(o).id AS orderId,
       i.lineId,
       i.productId
FROM `commerce`.`sales`.`orders` AS o
UNNEST o.items AS i
WHERE o.tenantId = "TENANT-A"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Khi UI yêu cầu “20 đơn mới nhất”, hãy lấy 20 order trước và quyết định bước mở rộng item phù hợp; không tự động áp `LIMIT 20` lên kết quả đã unnest rồi hiểu đó là 20 đơn. Cần test với order nhiều item và mảng rỗng.

### 10.2. Bài toán hai cấp mảng lồng nhau

Nếu một order có `packages[*].lines[*]`, có thể dùng `UNNEST` nhiều lần. Nhưng cardinality tăng theo số phần tử ở mỗi cấp; rất nhiều hàng trung gian có thể làm `ORDER BY`, tổng hợp hoặc phân trang tốn kém.

Nếu màn hình thường cần duyệt mọi dòng hàng theo đơn và phân trang sâu, mô hình `order_lines` riêng có thể phù hợp hơn mảng lồng nhiều cấp; khi đó index theo `orderId` sẽ phục vụ đường đọc.

## 11. Tách phần tử thành document riêng khi mảng tăng lớn

### 11.1. Mô hình `order_lines` độc lập

Thay vì nhúng toàn bộ dòng hàng, một line được lưu ở `commerce.sales.order_lines`:

```json
{
  "_class": "orderLine",
  "tenantId": "TENANT-A",
  "orderId": "order::1001",
  "lineId": "L1",
  "position": 1,
  "productId": "product::SKU-42",
  "productNameAtPurchase": "Binh giu nhiet",
  "unitPriceAtPurchase": 350000,
  "quantity": 2
}
```

Order giữ tổng tiền, trạng thái và metadata cấp đơn. Dòng hàng có ID riêng, có thể đọc/ghi/phân trang độc lập. Một query:

```sql
SELECT META(l).id AS lineDocumentId,
       l.lineId, l.position, l.productId,
       l.quantity, l.unitPriceAtPurchase
FROM `commerce`.`sales`.`order_lines` AS l
WHERE l.tenantId = "TENANT-A"
  AND l.orderId = "order::1001"
ORDER BY l.position ASC
LIMIT 50;
```

Index ứng viên:

```sql
CREATE INDEX ix_order_lines_by_order_position
ON `commerce`.`sales`.`order_lines`(
    `tenantId`, `orderId`, `position` ASC
);
```

### 11.2. Lợi ích và đánh đổi

**Lợi ích:** không cần đọc tất cả dòng hàng chỉ để lấy trang đầu, giảm document cha quá lớn, cập nhật độc lập dễ hơn và có thể phân bổ tài nguyên theo collection.

**Đánh đổi:** một order nay gồm **nhiều document**. Tạo order và các lines không còn là một KV mutation nguyên tử. Cần xác định:

- Có dùng transaction khi phải đảm bảo tạo đầy đủ order/lines không?
- Có chấp nhận trạng thái trung gian, và nếu có thì làm sao không hiển thị order chưa hoàn tất?
- Khi xóa order, những line còn lại được xử lý ra sao?
- Tổng tiền `total` được cập nhật và đối soát với các lines thế nào?
- Có cần idempotency key để retry tạo line mà không sinh bản ghi trùng?

**Không tách mảng chỉ vì “NoSQL luôn không nên nhúng”.** Chỉ tách khi giới hạn kích thước, nhu cầu truy cập độc lập, concurrency hoặc phân trang làm mô hình nhúng không còn hợp lý.

## 12. Chỉ mục cho từng cách mô hình hóa quan hệ

### 12.1. Tham chiếu theo ID và key join

Nếu order có `customerId` là document ID, bên customer có thể được tra theo khóa trong key join hoặc KV. Không cần tạo secondary index trên `customers.id` chỉ vì muốn tìm theo document ID; tên trường `@Id` là metadata của KV lookup, không đồng nghĩa phải tạo primary index SQL++.

Nhưng query cần tìm **tất cả order của một customer**:

```sql
SELECT META(o).id AS orderId, o.createdAt, o.status
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND o.customerId = "customer::C-42"
ORDER BY o.createdAt DESC
LIMIT 20;
```

nên cân nhắc index trên **phía chứa reference**:

```sql
CREATE INDEX ix_orders_by_customer_time
ON `commerce`.`sales`.`orders`(
    `tenantId`, `customerId`, `createdAt` DESC
);
```

Index này khác hoàn toàn thao tác KV lấy customer theo ID. Một loại phục vụ **tìm nhiều order theo reference**, loại còn lại phục vụ **lấy customer cụ thể**.

### 12.2. Tra customer theo thuộc tính

Nếu query tìm customer theo email:

```sql
SELECT META(c).id AS customerId, c.displayName
FROM `commerce`.`crm`.`customers` AS c
WHERE c.tenantId = "TENANT-A"
  AND c.email = "an@example.test";
```

index ứng viên:

```sql
CREATE INDEX ix_customers_by_tenant_email
ON `commerce`.`crm`.`customers`(
    `tenantId`, `email`
);
```

Chỉ mục này thuộc **collection customers**, còn `ix_orders_by_customer_time` thuộc **orders**. Không tồn tại một secondary index duy nhất tự trải qua cả hai collection.

### 12.3. Query trên mảng nhúng

Với `ANY ... SATISFIES` theo `items`, có thể cần array index:

```sql
CREATE INDEX ix_orders_tenant_item_product
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    DISTINCT ARRAY i.productId FOR i IN items END
);
```

Index mảng có thể tăng số entry theo số phần tử và giá trị phân biệt; nếu mảng lớn hoặc bị cập nhật nhiều, phải đo chi phí ghi. `EXPLAIN` sẽ cho biết query thực dùng array index hay vẫn phải đọc document gốc rồi lọc.

### 12.4. Read model và covering index

Một dashboard chỉ cần ID order, trạng thái, thời gian và tên khách hàng có thể dùng collection `order_views` chứa dữ liệu đã tổng hợp. Chỉ mục trên `order_views` phải được thiết kế theo `WHERE`/`ORDER BY` của dashboard, không sao chép máy móc index của `orders`.

Trong một số trường hợp, thay vì tạo read model riêng, chỉ cần index bao phủ các field đã phi chuẩn hóa ngay trên `orders`. Cả hai cách đều tăng chi phí duy trì; hãy đo và chọn phương án đơn giản nhất đáp ứng SLA.

## 13. Tính nhất quán khi có nhiều document

### 13.1. Một document: cập nhật nguyên tử không đồng nghĩa miễn xung đột

Nhúng aggregate giúp một lần mutation của document bao gồm tất cả field cần cập nhật. Tuy nhiên, nếu hai request cùng đọc cùng một phiên bản order rồi thay `status` và `items`, request ghi sau có thể ghi đè thay đổi của request trước nếu không có kiểm soát.

CAS hoặc optimistic locking qua `@Version` giúp phát hiện trường hợp cạnh tranh và buộc ứng dụng quyết định retry/merge theo nghiệp vụ. **CAS không tự động hợp nhất hai object graph**.

### 13.2. Nhiều document: phải định nghĩa bất biến nghiệp vụ

Với order và customer riêng, thay đổi tên customer không cần transaction với hàng nghìn order **nếu** order chỉ giữ snapshot lịch sử. Nếu order chứa cache tên hiện tại, việc cập nhật có thể chấp nhận eventual consistency với cơ chế phát sự kiện và sửa lệch.

Nhưng nếu tạo order và nhiều `order_lines` riêng, yêu cầu “đơn ở trạng thái CONFIRMED phải có đủ tất cả line đã tính vào total” là một bất biến nhiều document. Khi đó cần thiết kế transaction, quy trình ghi nhiều bước với trạng thái trung gian, hoặc một cơ chế phù hợp với yêu cầu nhất quán và tính sẵn sàng.

### 13.3. Giao dịch không thay thế thiết kế quan hệ

Couchbase có các khả năng giao dịch cho một phạm vi hoạt động được hỗ trợ theo SDK/version. Tuy nhiên, không nên tạo nhiều document quan hệ phức tạp rồi giả định “dùng transaction là mọi thứ miễn phí”. Giao dịch làm tăng độ phức tạp, thời gian/chi phí thao tác và yêu cầu xử lý retry/timeout; cũng không loại nhu cầu lập index cho SQL++.

Chỉ dùng giao dịch khi cần tính nguyên tử của nhiều thao tác và đã kiểm tra API, giới hạn và ngữ nghĩa commit/rollback của phiên bản đang triển khai.

### 13.4. DCP, event và đồng bộ read model

Nếu duy trì `order_views` hoặc `customerDisplayNameCache`, có thể dùng event từ ứng dụng hoặc cơ chế CDC/stream tương ứng để cập nhật bản sao. Thiết kế phải chịu được:

- Event trễ, lặp hoặc xử lý sai thứ tự.
- Consumer tạm ngừng rồi hoạt động lại.
- Bản ghi nguồn bị xóa hoặc hết hạn.
- Cùng một thay đổi được retry nhiều lần.
- Backfill trong khi stream vẫn tiếp tục cập nhật.

Một hướng là lưu `sourceVersion`/thời điểm hoặc sequence được kiểm soát và xử lý update idempotent; không chấp nhận event version cũ ghi đè mới. Bổ sung job đối soát để phát hiện và sửa bản sao bị lệch.

### 13.5. TTL và xóa dữ liệu liên quan

TTL trên order không tự xóa customer, và TTL trên customer không tự xóa các đơn đã tham chiếu customer đó. Tương tự, xóa order không tự xóa `order_lines` hay `order_events` trong collection riêng.

Phải đặt chính sách rõ:

| Quan hệ | Khi nguồn bị xóa/hết hạn | Chính sách khả dĩ |
| --- | --- | --- |
| Order → Customer | Customer không còn | Giữ order và snapshot; thông báo reference thiếu |
| Order → OrderLine riêng | Order bị xóa | Xóa có điều phối hoặc giữ theo retention |
| Customer → OrderView | Customer đổi tên/bị xóa | Làm mới, ẩn dữ liệu hoặc tombstone theo chính sách |
| Product → Order item snapshot | Product ngừng bán | Giữ giá/tên đã chốt; reference hiện tại có thể không tìm thấy |

Nhất là dữ liệu cá nhân, cần đánh giá retention, phân quyền và yêu cầu xóa theo quy định áp dụng. Phi chuẩn hóa có thể làm thông tin được sao chép sang nhiều collection, khiến việc xóa hoặc cập nhật chính sách trở nên khó hơn.

### 13.6. Scan consistency tách biệt tính nguyên tử

Global Secondary Index (GSI) được cập nhật bất đồng bộ. Sau khi lưu order, SQL++ tìm theo `customerId` có thể tạm chưa thấy mutation nếu dùng chế độ không chờ index bắt kịp:

| Scan consistency | Ý nghĩa |
| --- | --- |
| `NOT_BOUNDED` | Không yêu cầu chờ index bắt kịp mutation trước query; có thể trả dữ liệu tạm cũ |
| `REQUEST_PLUS` | Chờ index bắt kịp mutation liên quan tại thời điểm query; dữ liệu mới hơn nhưng có thể tăng độ trễ |

Điều này không thay thế CAS hoặc transaction. **CAS/transaction** quản lý tính đúng của thao tác ghi; **scan consistency** điều chỉnh việc Query Service đọc index mới đến đâu. Khi biết document ID vừa ghi và cần đọc lại chính document ấy, KV lookup thường đơn giản hơn truy vấn SQL++ theo thuộc tính.

## 14. Đọc nhiều quan hệ: KV, SQL++ JOIN hay read model?

### 14.1. So sánh hướng thực thi

| Cách đọc | Phù hợp nhất | Chi phí/rủi ro cần đánh giá |
| --- | --- | --- |
| Một KV read lấy aggregate nhúng | Trang chi tiết một order có item/address | Document quá lớn, cập nhật chồng chéo |
| KV order rồi KV customer | Trang chi tiết, số reference ít | Nhiều lượt đọc, kết quả khác thời điểm |
| Bulk KV nhiều reference | Một trang nhiều order, nhiều customer ID phân biệt | Memory, concurrency, mapping và batch-size |
| SQL++ `JOIN ... ON KEYS` | Query liên kết theo document ID, filter/sort phía trái | Query planning, join cardinality, số Fetch |
| SQL++ ANSI `JOIN ... ON` | Join theo thuộc tính thay vì document ID | Có thể cần GSI phía join và lọc tốt |
| `UNNEST` | Query từng item của mảng nhúng | Tăng số hàng trung gian, phân trang khác |
| Read model phi chuẩn hóa | Dashboard đọc rất nhiều, projection ổn định | Event/CDC, độ trễ đồng bộ, backfill và lưu trữ |

Quyết định nên dựa trên số liệu có thật: p95/p99 latency, số lượt KV fetch, entries scanned, số hàng join/unnest, lượng data chuyển về Java, mutation throughput và chi phí maintain index/read model.

### 14.2. Tránh so sánh thiếu công bằng

Nếu so sánh một `JOIN` trả cả customer với một KV lookup chỉ trả order ID, đó là hai hợp đồng dữ liệu khác nhau. Hãy xác định cùng tập field cần trả, cùng filter, cùng kích thước trang và yêu cầu độ mới. SQL++ `EXPLAIN` cho kế hoạch dự kiến; Query Profile/metrics cho chi phí thực tế.

### 14.3. Reactive không làm biến mất N+1 hoặc JOIN tốn kém

`ReactiveCouchbaseRepository` hoặc API reactive của template/SDK cho phép xử lý bất đồng bộ. Nhưng viết:

```java
ordersFlux.flatMap(order ->
    reactiveCustomerRepository.findById(order.getCustomerId())
        .map(customer -> /* ghép order và customer */ customer)
);
```

vẫn có thể tạo nhiều KV reads. Reactive không tự biến N lượt lookup thành một phép đọc; phải chủ động giới hạn concurrency, khử trùng lặp ID, batch hoặc thay chiến lược bằng join/read model khi phù hợp.

Đo cả mức đồng thời của ứng dụng và tải KV/Query Service. Không chỉ tăng `flatMap` concurrency để che latency nếu việc đó làm cụm quá tải.

## 15. Quyền truy cập và đa tenant khi đi qua reference

Một ID `customer::C-42` không chứng minh customer thuộc tenant đang đăng nhập. Với mỗi lần join/fetch qua reference:

1. Đảm bảo request đã được xác thực và có quyền trên tenant.
2. Giới hạn query order theo `tenantId` từ context tin cậy, không chỉ lấy tenant do client tự nhập.
3. Kiểm tra customer/prod/line có `tenantId` tương thích nếu mô hình cho phép nhiều tenant chia collection.
4. Không hiển thị dữ liệu nhạy cảm chỉ vì một document chứa reference ID.
5. Áp dụng RBAC theo bucket/scope/collection và kiểm soát nghiệp vụ riêng.

Index chứa `tenantId` giúp lọc hiệu quả, **không thay thế authorization**. Trong schema multi-tenant, cần quy ước ID nhất quán và xem xét khả năng trùng ID giữa các collection/tenant, kể cả khi tên collection được dùng ở nhiều scope.

Phi chuẩn hóa tên, email hoặc thông tin khách hàng vào order cũng làm tăng số nơi phải kiểm soát truy cập và xử lý yêu cầu xóa dữ liệu; cần chọn tối thiểu những trường thật sự cần cho API.

## 16. Quy trình chuyển đổi mô hình quan hệ khi ứng dụng đã chạy

### 16.1. Từ mảng nhúng sang document line riêng

Nếu sau một thời gian `items` vượt ngưỡng thiết kế, một migration an toàn cần:

1. Xác định schema mới, collection `order_lines` và ID ổn định cho từng line.
2. Tạo index trên collection mới trước khi chuyển truy vấn phụ thuộc.
3. Backfill từ `orders.items` sang `order_lines`, có khả năng retry idempotent.
4. Xử lý các mutation mới phát sinh trong lúc backfill (dual-write hoặc luồng đồng bộ có kiểm soát).
5. Đối soát số lượng, đơn giá, quantity và tổng tiền giữa mô hình cũ/mới.
6. Chuyển đọc theo canary/feature flag, quan sát latency và lỗi.
7. Chỉ gỡ dữ liệu nhúng cũ khi không còn code/job phụ thuộc và đủ điều kiện rollback.

Không dùng việc “index mới online” làm bằng chứng rằng dữ liệu đã được chuyển đủ; đó là hai vấn đề độc lập.

### 16.2. Thêm snapshot khách hàng vào order cũ

Nếu bổ sung `customerNameAtPurchase` cho dữ liệu lịch sử, phải xác định **có thể khôi phục đúng giá trị tại thời điểm mua hay không**. Lấy `displayName` hiện tại rồi gán ngược cho tất cả order cũ sẽ tạo lịch sử giả nếu khách đã đổi tên.

Có thể chọn:

- Chỉ ghi snapshot cho order mới.
- Backfill từ event/audit lịch sử nếu có nguồn đáng tin cậy.
- Để `MISSING` cho order cũ và có fallback UI được ghi rõ là “tên hiện tại”.

Không gán nhãn `AtPurchase` cho dữ liệu mà hệ thống không thực sự biết tại thời điểm mua.

### 16.3. Version dữ liệu và read model

Khi thêm `customerDisplayNameCache` hoặc `order_views`, triển khai theo *expand → backfill → validate → switch → observe → contract*. Trong giai đoạn chuyển tiếp, phải xác định ứng dụng đọc schema nào và sự kiện mới được đồng bộ ra sao.

Rollback code không đồng nghĩa nên xóa collection/index mới ngay. Giữ khả năng phục hồi và chỉ thu hồi sau khi xác định các phiên bản ứng dụng/batch không còn phụ thuộc.

## 17. Các sai lầm phổ biến và cách chẩn đoán

| Dấu hiệu | Nguyên nhân điển hình | Hướng xử lý |
| --- | --- | --- |
| Order có mảng con tăng mãi | Nhúng một quan hệ không giới hạn | Xem cardinality, tách collection và index theo `orderId` |
| Trang list phát hàng trăm KV lookups | N+1 khi lấy customer cho từng order | Khử trùng lặp ID, batch, SQL++ join hoặc read model |
| Đổi tên khách làm hóa đơn cũ đổi theo | Chỉ đọc tên hiện tại qua reference | Lưu snapshot có ý nghĩa lịch sử |
| Đổi tên khách nhưng dashboard không đổi | Dữ liệu cache không có cơ chế làm mới | Event/CDC, version, retry và reconciliation |
| Giá đơn hàng cũ biến động theo catalog | Không chốt `unitPriceAtPurchase` | Lưu giá snapshot khi checkout |
| Order tham chiếu ID không tồn tại | Không có ràng buộc FK tự động | Kiểm tra khi ghi, chính sách thiếu reference và job đối soát |
| `LEFT JOIN` làm mất các order thiếu customer | Lọc field phía customer trong `WHERE` | Kiểm tra ngữ nghĩa join và xử lý `MISSING` |
| Query `UNNEST` trả “quá nhiều order” | Mỗi item biến thành một hàng | Phân biệt số order với số item, thiết kế phân trang phù hợp |
| Cập nhật song song làm mất item | Ghi đè document cũ không kiểm CAS | Dùng optimistic locking và retry/merge theo nghiệp vụ |
| Tách line ra collection riêng rồi có “đơn nửa chừng” | Nhiều document không còn nguyên tử mặc định | Transaction hoặc state machine với trạng thái trung gian |
| SQL++ join chậm dù customer lookup theo ID | Phía order scan rộng, join nhiều hàng | Kiểm tra index lọc order, `EXPLAIN` và Query Profile |
| Query order vừa ghi chưa xuất hiện | GSI chưa bắt kịp mutation | Chọn consistency hoặc KV theo ID khi phù hợp |
| Xóa customer nhưng PII vẫn trong order cache | Phi chuẩn hóa nhiều nơi, thiếu chính sách retention | Kiểm kê dữ liệu copy, xử lý theo yêu cầu xóa phù hợp |

## 18. Bài thực hành: thiết kế ba cách lưu đơn hàng

### Bước 1 — Xác định hợp đồng đọc

Giả sử có ba màn hình:

| Màn hình | Dữ liệu yêu cầu | Tần suất ví dụ |
| --- | --- | --- |
| Chi tiết đơn | Tất cả item, địa chỉ, giá chốt, tên người mua tại thời điểm mua | Cao |
| Danh sách đơn | ID, status, createdAt, tên khách hiện tại | Rất cao |
| Dòng thời gian giao vận | Các event của một order, phân trang theo thời điểm | Trung bình, có thể tăng dài hạn |

Hãy quyết định mỗi trường nên nhúng, tham chiếu hay phi chuẩn hóa. Đặc biệt giải thích vì sao **giá tại thời điểm mua** khác **tên khách hiện tại** về chính sách đồng bộ.

### Bước 2 — Thiết kế hai mô hình thay thế

**Mô hình A — nhúng item:**

```json
{
  "customerId": "customer::C-42",
  "customerNameAtPurchase": "Nguyen An",
  "items": [
    {
      "productId": "product::SKU-42",
      "unitPriceAtPurchase": 350000,
      "quantity": 2
    }
  ],
  "total": 700000
}
```

**Mô hình B — dòng hàng riêng:**

```text
sales.orders:
  order::1001 -> customerId, status, total

sales.order_lines:
  line::1001::L1 -> orderId=order::1001, price, quantity
  line::1001::L2 -> orderId=order::1001, price, quantity
```

Lập bảng so sánh số document, số KV read cho màn hình chi tiết, khả năng phân trang line, chi phí update và yêu cầu atomicity. Không cần ép mô hình B tốt hơn: nếu đơn hàng luôn chỉ có vài dòng, mô hình A có thể đơn giản và hiệu quả hơn.

### Bước 3 — Thử key join trên reference

Chuẩn bị customer và order trong hai collection. Chạy:

```sql
EXPLAIN
SELECT META(o).id AS orderId,
       c.displayName AS customerName
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`crm`.`customers` AS c
  ON KEYS o.customerId
WHERE o.tenantId = "TENANT-A"
  AND c.tenantId = o.tenantId;
```

Sau đó thử `LEFT JOIN` và xóa customer trong lab. So sánh số order còn hiển thị, giá trị field customer và phương án fallback snapshot. **Không** làm thí nghiệm xóa trên production.

### Bước 4 — Thử `ANY` và `UNNEST`

```sql
-- Những đơn có một item chứa productId
SELECT META(o).id AS orderId
FROM `commerce`.`sales`.`orders` AS o
WHERE ANY i IN o.items
      SATISFIES i.productId = "product::SKU-42"
      END;

-- Những dòng hàng cụ thể khớp productId
SELECT META(o).id AS orderId, i.lineId, i.quantity
FROM `commerce`.`sales`.`orders` AS o
UNNEST o.items AS i
WHERE i.productId = "product::SKU-42";
```

Với một order chứa hai item có cùng product ID, hãy giải thích tại sao câu đầu chỉ trả một order nhưng câu sau có thể trả hai hàng. Đo plan, số hàng và chi phí khi mảng lớn hơn.

### Bước 5 — Thiết kế read model cho trang list

Phác thảo document `order_views`:

```json
{
  "tenantId": "TENANT-A",
  "orderId": "order::1001",
  "status": "PAID",
  "createdAt": "2026-11-20T08:15:00Z",
  "customerId": "customer::C-42",
  "customerDisplayNameCache": "Nguyen An",
  "customerProfileVersion": 12
}
```

Chọn nguồn chân lý, trigger tạo/cập nhật, thứ tự xử lý event, cách idempotent retry và job đối soát. Chạy thử một sự kiện tên version 13, rồi một sự kiện cũ version 12 đến muộn; hệ thống phải tránh ghi đè bản sao mới bằng dữ liệu cũ.

### Bước 6 — Thiết kế dữ liệu thiếu và xóa

Viết phương án khi:

- `customerId` không tồn tại nhưng order đã thanh toán.
- Product bị ngừng bán nhưng order cần hóa đơn lịch sử.
- Order bị hủy/xóa còn nhiều `order_lines` riêng.
- Document `order_views` đang giữ dữ liệu cá nhân nhưng customer yêu cầu xóa theo chính sách áp dụng.

Đối với mỗi tình huống, nêu rõ cần transaction, sự kiện, cleanup theo lô, tombstone hay fallback snapshot, và lý do.

### Câu hỏi tự kiểm tra

1. Vì sao `shippingAddress` của một order thường phù hợp để nhúng hơn `Customer.defaultAddress`?
2. `customerId` có phải foreign key do Couchbase tự kiểm tra không?
3. Vì sao nhúng toàn bộ sự kiện lịch sử của order vào một mảng có thể gây vấn đề dài hạn?
4. Khi nào nên lưu `productNameAtPurchase` và `unitPriceAtPurchase` dù đã có `productId`?
5. Sự khác nhau giữa `customerNameAtPurchase` và `customerDisplayNameCache` là gì?
6. `JOIN ... ON KEYS` cần kiểu liên kết nào? Nó khác `JOIN ... ON` theo field ra sao?
7. `UNNEST` thay đổi cardinality thế nào và tại sao `LIMIT 20` sau unnest không đồng nghĩa 20 order?
8. Tách `order_lines` thành collection riêng giúp gì cho phân trang và ảnh hưởng atomicity thế nào?
9. Vì sao reactive `flatMap(findById)` vẫn có thể gây N+1 lookups?
10. CAS giải quyết vấn đề gì khi hai request đồng thời sửa mảng `items`?
11. Khi nào cần transaction nhiều document, khi nào chấp nhận eventual consistency với sự kiện?
12. Vì sao scan consistency `REQUEST_PLUS` không thay thế transaction/CAS?
13. Phải kiểm tra điều gì khi xóa dữ liệu gốc đã được phi chuẩn hóa sang nhiều collection?
14. Trước khi quyết định thêm index cho `JOIN`, cần xem `EXPLAIN` và Query Profile của bên nào?

## 19. Tổng kết

Thiết kế quan hệ trong Couchbase không bắt đầu từ câu hỏi “làm sao ánh xạ mọi khóa ngoại?”, mà từ **ranh giới aggregate và cách ứng dụng thực sự đọc–ghi**:

- **Nhúng** khi dữ liệu nhỏ, có giới hạn, có cùng vòng đời và thường được đọc/cập nhật cùng cha.
- **Tham chiếu ID** khi dữ liệu có vòng đời riêng, được dùng lại và cần truy cập độc lập; lựa chọn KV lookup, bulk read hoặc SQL++ `JOIN` theo nhu cầu.
- **Phi chuẩn hóa** khi cần snapshot lịch sử hoặc tối ưu màn hình đọc nhiều; phải phân biệt dữ liệu bất biến với cache cần làm mới.

Trong **Spring Data Couchbase**, hãy đặt entity đúng bucket/scope/collection, tránh kỳ vọng chuỗi `customerId` tự tải quan hệ, dùng `UNNEST` cho mảng nhúng và `JOIN ... ON KEYS` cho document tham chiếu phù hợp. Sau đó thiết kế index theo đường truy vấn thật, kiểm tra `EXPLAIN`, đo tải đọc/ghi và quy định rõ CAS, giao dịch, TTL, đồng bộ event, tính nhất quán và quyền truy cập. Một mô hình quan hệ tốt phải **đúng nghiệp vụ, đủ nhanh, có khả năng mở rộng và có kế hoạch duy trì khi dữ liệu thay đổi**.
