# Documents, collections và mô hình hóa dữ liệu Firestore

> **Chương:** Firestore và Firebase  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một cửa hàng trực tuyến cần quản lý khách hàng, sản phẩm và đơn hàng. Với cơ sở dữ liệu quan hệ, ta thường bắt đầu từ bảng, khóa ngoại và phép `JOIN`. Với **Cloud Firestore**, câu hỏi đầu tiên là: **ứng dụng sẽ đọc những nhóm dữ liệu nào cùng nhau, lọc theo trường nào, ai được quyền truy cập và dữ liệu tăng trưởng ra sao?**

Firestore là cơ sở dữ liệu NoSQL hướng **document**, hỗ trợ đọc/ghi theo document, truy vấn có index và đồng bộ dữ liệu cho ứng dụng. Firebase cung cấp SDK, Authentication, Security Rules và công cụ phát triển cho mobile/web; ứng dụng backend chạy trên **Cloud Run/GKE/Compute Engine** có thể dùng Google Cloud Firestore server client libraries. Bài này dùng mô hình **Firestore Standard edition, Native mode** làm nền để giải thích các thao tác phổ biến. Khi sử dụng Firestore Enterprise edition hoặc chế độ khác, phải đối chiếu khả năng truy vấn, index và mô hình phí tương ứng.

Trong lộ trình **CLOUD_PROVIDERS_GCP**, kiến thức này giúp chọn cơ sở dữ liệu phù hợp, bảo vệ dữ liệu bằng IAM/Rules, phát hành ứng dụng và theo dõi chi phí/độ tin cậy.

**Sau bài học, bạn có thể:**

1. Phân biệt **collection, document, document ID, field, map, array** và **subcollection**.
2. Đọc đường dẫn Firestore đúng thứ tự collection/document; hiểu document cha có thể không tồn tại nhưng subcollection vẫn còn.
3. Chọn **embedded map/array**, **subcollection** hoặc **root collection** theo truy vấn và quy mô.
4. Thiết kế mô hình `users / products / orders / items` cho ứng dụng đặt hàng.
5. Viết Java server SDK tạo/đọc/cập nhật document và truy vấn collection; phân biệt Firebase web SDK.
6. Hiểu vai trò **single-field/composite indexes**, collection group query và pagination.
7. Nhận biết **Security Rules không phải bộ lọc truy vấn**, còn server SDK dựa vào IAM.
8. Tránh hot document, ID tuần tự, document quá lớn và xóa cha nhưng để lại dữ liệu con.
9. Ước tính reads/writes/index/storage và thực hành cải tiến một mô hình dữ liệu.

## 1. Mô hình tư duy: document nằm trong collection

Firestore lưu các **documents**, mỗi document chứa một tập **fields** (cặp key/value). Các documents được tổ chức thành **collections**. Một document có thể chứa maps/arrays trong fields và các **subcollections** nằm bên dưới.

~~~mermaid
flowchart TD
    DB["Firestore database"] --> USERS["collection: users"]
    DB --> ORDERS["collection: orders"]
    USERS --> U["document: user_123"]
    ORDERS --> O["document: order_abc"]
    U --> MAP["fields: displayName, email,\npreferences (map)"]
    U --> ADDRS["subcollection: addresses"]
    ADDRS --> A["document: address_01"]
    O --> OF["fields: userId, status,\ntotalCents, createdAt"]
    O --> ITEMS["subcollection: items"]
    ITEMS --> I["document: line_01"]
~~~

### 1.1. Quy tắc đường dẫn xen kẽ

Đường dẫn luôn luân phiên **collection / document / collection / document**:

| Đường dẫn | Đối tượng | Hợp lệ? |
| --- | --- | --- |
| `users` | Collection gốc | Có |
| `users/user_123` | Document | Có |
| `users/user_123/addresses` | Subcollection | Có |
| `users/user_123/addresses/address_01` | Document trong subcollection | Có |
| `orders/order_abc/items/line_01` | Document trong subcollection | Có |
| `users/addresses` nếu xem `addresses` là collection ngay sau `users` | Không đúng mô hình kỳ vọng | Không phải collection path; nó là document path |

**Độ dài đường dẫn không xác định “bảng”.** `orders/order_abc` là document reference; `orders/order_abc/items` là collection reference. Không đặt một collection trực tiếp dưới collection hoặc document trực tiếp dưới document.

### 1.2. Collections và documents được tạo khi có dữ liệu

Khi ghi `users/user_123` lần đầu, Firestore tạo document và collection tương ứng nếu chưa tồn tại; không cần lệnh SQL `CREATE TABLE`. Tạo reference **chưa đồng nghĩa dữ liệu đã tồn tại**. Tương tự, có thể tồn tại `orders/order_abc/items/line_01` dù document cha `orders/order_abc` không có dữ liệu.

**Lưu ý rất quan trọng:** Xóa document cha bằng SDK **không tự xóa subcollections**. Cần quy trình recursive deletion riêng, kiểm tra quyền và phí đọc/xóa. Không tưởng rằng xóa `orders/order_abc` sẽ xóa mọi `items` của đơn.

### 1.3. Document không phải một JSON file tùy ý

Ví dụ dữ liệu document `users/user_123` ở dạng minh họa:

~~~json
{
  "displayName": "Mai",
  "status": "active",
  "preferences": {
    "language": "vi",
    "notifications": true
  },
  "roles": ["buyer"],
  "loyaltyPoints": 120
}
~~~

Firestore hỗ trợ kiểu giá trị đặc thù như **Timestamp, GeoPoint, Bytes, Reference**, bên cạnh String, Boolean, Number, Null, Map, Array. Khi đưa ra JSON cho API, cần chuyển các kiểu đặc thù sang biểu diễn phù hợp; đừng mặc định Firestore Timestamp bằng chuỗi ISO trong database.

## 2. Những giới hạn ảnh hưởng thiết kế dữ liệu

| Giới hạn/đặc điểm trong Firestore Standard | Mức tham chiếu | Hệ quả |
| --- | --- | --- |
| Kích thước mỗi document | **Tối đa 1 MiB** | Không đặt toàn bộ lịch sử đơn hàng/chat trong một document |
| Độ sâu map/array fields | **Tối đa 20** | Không lồng object vô hạn trong một document |
| Độ sâu subcollections | **Tối đa 100 cấp** | Subcollection hierarchy khác map depth |
| Tên collection/document ID | Thường tối đa **1.500 bytes**, không chứa dấu `/` | Kiểm tra ID, không lấy tùy ý raw user input làm path |
| Tên document đầy đủ | Tối đa **6 KiB** | Đường dẫn quá sâu/tên dài có thể vượt giới hạn |
| Index entries mỗi document | Tối đa **40.000** | Array/map lớn và nhiều indexes có thể tăng index fanout |
| Truy vấn trong Standard mode | Dựa trên indexes | Filter + sort phức tạp có thể đòi composite index |

Các giới hạn khác còn phụ thuộc database edition và thời điểm sản phẩm. Kiểm tra [Usage and limits](https://firebase.google.com/docs/firestore/quotas) trước khi chọn schema production.

### 2.1. Chọn document ID

- Với document không có key tự nhiên, ưu tiên **auto-generated IDs** phân tán.
- Nếu dùng business ID, phải đảm bảo unique, không tiết lộ PII và có thể truy cập ổn định.
- Tránh ID tăng tuần tự như `order-00001`, `order-00002` nếu ghi với tốc độ cao; chúng có thể tạo **hotspot** trên dải key gần nhau.
- Không đưa email/số điện thoại, access token hoặc thông tin khách hàng vào document path; path có thể hiện trong logs/metrics.
- ID tự sinh giúp phân phối writes; **không tự đảm bảo** truy vấn theo `createdAt` không bị hotspot ở index.

### 2.2. Dữ liệu tiền và thời gian

Ví dụ ứng dụng bán hàng nên lưu `totalCents: 129900` (số nguyên theo đơn vị nhỏ nhất) kèm `currency: "VND"` hoặc mô hình decimal được quy định; tránh mặc định dùng floating-point cho phép tính tiền. Với VND, đặt tên `amountMinor`/quy ước tiền tệ rõ hơn nếu hệ thống nhiều loại tiền.

Dùng **server timestamp** cho `createdAt`/`updatedAt` khi được hỗ trợ, không tin thời gian gửi từ thiết bị của người dùng để xác định thứ tự xử lý nghiệp vụ. Nếu buộc truy vấn liên tục theo timestamp ở tần suất ghi rất cao, đánh giá index hotspot và kiến trúc partition/sharding.

## 3. Ba cách tổ chức dữ liệu liên quan

Mô hình hóa Firestore thường cần chọn giữa **map/array trong document**, **subcollection**, hoặc **nhiều root collections**. Lựa chọn tốt tùy cách đọc, tăng trưởng và phân quyền.

| Phương án | Phù hợp khi | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **Map/array trong document** | Dữ liệu nhỏ, có giới hạn, thường đọc cùng parent | Một document read, dễ trả đầy đủ | Parent phình lớn; mỗi thay đổi tác động document/index |
| **Subcollection** | Danh sách có thể tăng không giới hạn, gắn tự nhiên với cha | Dễ truy vấn từng danh sách, phân trang, cập nhật phần tử riêng | Nhiều reads khi cần tất cả; cleanup subcollections phức tạp |
| **Root collection** | Cần lọc/truy vấn xuyên nhiều cha; entities có lifecycle độc lập | Dễ truy vấn theo user/status/time trên toàn database | Cần lưu reference/ID liên kết, không có SQL JOIN |

### 3.1. Embedded map: dữ liệu có giới hạn

Ví dụ thông tin giao hàng hiện tại nằm trong đơn:

~~~json
{
  "userId": "user_123",
  "status": "CREATED",
  "shipping": {
    "recipient": "Mai",
    "city": "Ho Chi Minh City",
    "country": "VN"
  },
  "totalMinor": 129900,
  "currency": "VND"
}
~~~

Thông tin `shipping` là **snapshot** tại thời điểm đặt hàng; nên nằm cùng order để không phụ thuộc việc user đổi địa chỉ về sau. Một document read lấy cả dữ liệu order, nhưng không nên nhúng toàn bộ các địa chỉ người dùng từng khai báo vào order.

### 3.2. Array: danh sách nhỏ, ổn định

`tags: ["new", "fragile"]` có thể phù hợp trong document sản phẩm. Nhưng danh sách `comments`, `reviews` hoặc `orderItems` không giới hạn số lượng sẽ khiến document tăng và khó phân trang/ghi đồng thời. Với các danh sách đó, dùng **subcollection** hoặc root collection.

**Cập nhật một phần field:** `update("shipping.city", "Da Nang")` sửa nested field; thay toàn bộ map `shipping` bằng `set` không có merge có thể làm mất các nested fields khác. Chỉ dùng dot notation đúng với field path đã quy hoạch.

### 3.3. Subcollection: con tăng trưởng độc lập

~~~text
orders/order_abc
  ├── fields: userId, status, createdAt, totalMinor
  └── items/line_01
        ├── productId: sku_001
        ├── quantity: 2
        └── priceMinor: 64950
      items/line_02
        ├── productId: sku_002
        └── quantity: 1
~~~

Có thể lấy 10 items đầu, phân trang tiếp, update mỗi line item riêng. Nhưng **đọc `orders/order_abc` không kèm tự động tất cả items**; phải gọi subcollection. Một document cha bị xóa không tự xóa items.

### 3.4. Root collections: truy vấn xuyên cha

Nếu màn hình “Đơn hàng của tôi” thường liệt kê tất cả đơn của một user, lưu `orders` ở **root** với field `userId` sẽ trực tiếp hỗ trợ:

~~~text
orders.where(userId == currentUser).orderBy(createdAt, desc).limit(20)
~~~

Thay thế bằng `users/user_123/orders/...` cũng hợp lý khi mọi truy vấn đều gắn user; nhưng nghiệp vụ “tất cả đơn đang chờ xử lý”, “đơn của một chi nhánh” sẽ cần collection group query hoặc duplicate/search index bổ sung. **Thiết kế theo access patterns**, không phải sở thích đặt cây sâu.

## 4. Thiết kế từ truy vấn: ví dụ ứng dụng đặt hàng

### 4.1. Liệt kê use cases trước khi quyết định schema

| Yêu cầu | Truy vấn mong muốn | Tổ chức đề xuất |
| --- | --- | --- |
| Xem thông tin user sau đăng nhập | Document by UID | `users/{uid}` |
| Xem chi tiết sản phẩm | Document by productId | `products/{productId}` |
| Danh sách sản phẩm đang bán theo category | `where(status, active)` + `where(categoryId)` + `orderBy(displayRank)` | Root `products` + composite index |
| Danh sách đơn của một user | `where(userId)` + `orderBy(createdAt desc)` | Root `orders` |
| Xem chi tiết một đơn và dòng hàng | Parent read + subcollection query | `orders/{orderId}/items` |
| Truy vấn toàn hệ thống các dòng hàng của SKU | Collection group `items`, hoặc bảng/projection khác | Chỉ tạo nếu có use case thật |
| Cập nhật lượng tồn kho | Transaction/atomic counter theo thiết kế | `products/{productId}` hoặc partition phù hợp tải |

**Quan hệ không được Firestore tự JOIN.** Nếu cần tên sản phẩm tại thời điểm mua, nên lưu **snapshot `productName`, `unitPriceMinor`** vào item. Nếu cần thông tin sản phẩm mới nhất, lưu `productId` để đọc thêm document sản phẩm. Đó là **denormalization có chủ đích**.

### 4.2. Một sơ đồ schema nhất quán

~~~mermaid
flowchart LR
  USERS["users/{uid}\ndisplayName, status"] --> ADDR["addresses/{addressId}\nrecipient, city"]
  ORDERS["orders/{orderId}\nuserId, status, createdAt,\ntotalMinor, currency, shipping"] --> ITEMS["items/{lineId}\nproductId, productName,\nquantity, unitPriceMinor"]
  PRODUCTS["products/{productId}\nname, categoryId,\nstatus, priceMinor, stock"] -. "product snapshot tại checkout" .-> ITEMS
  USERS -. "tham chiếu qua userId" .-> ORDERS
~~~

Cấu trúc đường dẫn:

~~~text
users/user_123
users/user_123/addresses/address_01

products/sku_001
products/sku_002

orders/order_abc
orders/order_abc/items/line_01
orders/order_abc/items/line_02
~~~

**Bất biến nghiệp vụ nên được định nghĩa rõ:**

- `orders.userId` là danh tính owner, không cho client tự đổi để đọc đơn người khác.
- `totalMinor` của order do backend tính từ items, không tin giá do client gửi.
- `items.unitPriceMinor` là **snapshot** giá tại checkout; giá hiện hành ở `products.priceMinor` có thể thay đổi.
- Một item không thể tồn tại mà không có order hợp lệ theo nghiệp vụ, dù Firestore **không tự enforce foreign key**.
- Checkout cần đảm bảo việc tạo parent/order items và cập nhật stock theo giao dịch/batch phù hợp với giới hạn thực tế, không chỉ hai lệnh ghi rời rạc.

## 5. Mẫu truy vấn và chỉ mục (indexes)

### 5.1. Chỉ mục phục vụ query, không phải chỉ để tối ưu tùy ý

Trong Firestore Standard, **single-field indexes** thường được tạo tự động. Truy vấn kết hợp lọc nhiều fields/sắp xếp có thể cần **composite index**. Nếu index cần thiết chưa tồn tại, SDK thường trả lỗi với hướng dẫn/link tạo index; query **không tự quét toàn collection** như một SQL table scan.

Ví dụ:

~~~text
orders
  .where("userId", "==", "user_123")
  .orderBy("createdAt", "desc")
  .limit(20)
~~~

Tùy index hiện có và database edition, có thể cần composite index:

~~~text
collection: orders
fields:
  userId    ASC
  createdAt DESC
query scope: Collection
~~~

Thiết kế index theo **truy vấn thật**; nhiều indexes không cần thiết làm tăng index storage/write fanout và chi phí. Nên dùng link trong lỗi query, Firebase Console/CLI hoặc IaC để cấu hình rồi kiểm tra index build hoàn tất.

### 5.2. Collection-group query

Nếu nhiều parent có subcollection cùng ID `items`, bạn có thể truy vấn **tất cả** `items` theo collection group:

~~~text
orders/order_abc/items/line_01
orders/order_xyz/items/line_02
...
collectionGroup("items")
  .where("productId", "==", "sku_001")
~~~

**Điều kiện quan trọng:**

1. Truy vấn phạm vi **tất cả collections tên `items`** trong database, kể cả nếu ứng dụng khác dùng cùng ID ở cấu trúc khác.
2. Cần **collection-group index** tương ứng.
3. Truy cập mobile/web còn cần **Security Rules hỗ trợ collection group queries**, thường sử dụng rules version 2.
4. Phải thiết kế thông tin ownership/tenant (ví dụ `ownerUid`/`tenantId`) ở items nếu muốn lọc theo người dùng/tenant; không suy từ parent path rằng client được đọc mọi item.

Nếu use case chính là truy vấn toàn bộ dòng hàng theo SKU trong hàng triệu đơn, cân nhắc projection/root collection hoặc BigQuery analytics thay vì collection-group query tốn nhiều reads. **Firestore không thay công cụ analytical join/reporting**.

### 5.3. Pagination dùng cursor

Đọc 20 orders mới nhất, lấy document cuối làm cursor rồi truy vấn trang tiếp theo bằng `startAfter(lastSnapshot)` với cùng filter/order/limit. Cursor theo **document snapshot** giảm vấn đề duplicate field sort; tránh dùng `offset` để “bỏ qua 10.000 dòng” vì Firestore có thể tính reads cho các documents bị bỏ qua.

**Hạn chế:** Tài liệu phân trang cần quy tắc ổn định khi documents bị thêm/xóa giữa các lượt; dữ liệu theo thời gian thực có thể thay đổi thứ tự trong lúc người dùng lật trang.

### 5.4. Query và dữ liệu thiếu field

Truy vấn có `orderBy("createdAt")` chỉ trả về documents **có trường `createdAt`**. Nếu migrate schema và nhiều documents cũ chưa được backfill, chúng có thể biến mất khỏi danh sách dù vẫn tồn tại trong database. Đặt default values/backfill và test compatibility khi thêm sort field.

## 6. Java server SDK: tạo document và subcollection

Ví dụ dùng thư viện `com.google.cloud:google-cloud-firestore` qua **Application Default Credentials (ADC)**. Trên Cloud Run/GKE, runtime service account cần IAM phù hợp trên database/project; phát triển local dùng tài khoản test hoặc Firestore Emulator. Không đưa service account JSON key vào mã nguồn.

**Điều kiện:** Project đã bật Firestore database, ứng dụng Java có dependency Google Cloud Firestore phiên bản tương thích với JDK, quyền phù hợp và database mặc định `(default)`. Đoạn mã sau minh họa API cơ bản; chưa phải order service production.

### 6.1. Tạo parent order với auto ID

~~~java
import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.FieldValue;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import java.util.HashMap;
import java.util.Map;

public class CreateOrderExample {
    public static void main(String[] args) throws Exception {
        Firestore db = FirestoreOptions.getDefaultInstance().getService();

        try {
            DocumentReference order = db.collection("orders").document();

            Map<String, Object> data = new HashMap<>();
            data.put("userId", "user_123");
            data.put("status", "CREATED");
            data.put("currency", "VND");
            data.put("totalMinor", 129900L);
            data.put("createdAt", FieldValue.serverTimestamp());

            order.set(data).get();
            System.out.println("Created order ID: " + order.getId());
        } finally {
            db.close();
        }
    }
}
~~~

`document()` tạo reference có **ID tự sinh**; `set(data)` mới ghi document. `get()` đợi kết quả từ asynchronous future; ứng dụng production nên quản lý timeout/exceptions/latency và **tái sử dụng `Firestore` client** theo vòng đời service, không tạo/đóng trong mỗi HTTP request.

### 6.2. Tạo subcollection item

Giả sử `orderId` là ID order vừa tạo và được kiểm tra hợp lệ:

~~~java
DocumentReference orderRef =
    db.collection("orders").document(orderId);

DocumentReference itemRef =
    orderRef.collection("items").document("line_01");

Map<String, Object> item = Map.of(
    "productId", "sku_001",
    "productName", "Cốc giữ nhiệt",
    "quantity", 2L,
    "unitPriceMinor", 64950L
);

itemRef.set(item).get();
~~~

Đây là **đoạn code** trong scope có biến `db`/`orderId` hợp lệ, không chạy một mình. Ghi order và item bằng **hai lần `set()` riêng biệt không atomic**: nếu ghi item lỗi, order có thể tồn tại mà không có items. Với dữ liệu cần tính nhất quán, dùng **batched write** hoặc **transaction** và xử lý business invariants trước/đúng trong giao dịch.

### 6.3. Đọc và truy vấn theo user

~~~java
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Query;
import com.google.cloud.firestore.QuerySnapshot;

DocumentSnapshot order = db.collection("orders")
    .document(orderId)
    .get()
    .get();

if (!order.exists()) {
    throw new IllegalArgumentException("Order not found");
}

QuerySnapshot page = db.collection("orders")
    .whereEqualTo("userId", "user_123")
    .orderBy("createdAt", Query.Direction.DESCENDING)
    .limit(20)
    .get()
    .get();

page.getDocuments().forEach(doc ->
    System.out.println(doc.getId() + ": " + doc.getString("status"))
);
~~~

Nếu không có composite index phù hợp, câu query có thể báo lỗi index cần tạo. Đừng dùng mã này để in toàn bộ thông tin đơn hàng chứa PII lên logs. **Backend bắt buộc xác thực request và kiểm tra user được phép đọc**; server SDK không được Firestore Security Rules tự động chặn.

### 6.4. Cập nhật có giới hạn

~~~java
import com.google.cloud.firestore.FieldValue;

db.collection("orders").document(orderId)
    .update(
        "status", "CONFIRMED",
        "updatedAt", FieldValue.serverTimestamp()
    )
    .get();
~~~

`update()` báo lỗi nếu document không tồn tại; `set()` không có merge có thể **ghi đè toàn bộ fields**. Nếu muốn upsert giữ lại các fields, dùng `set(data, SetOptions.merge())`. Đối với `status`, production nên dùng transaction/precondition hoặc state machine để ngăn update trái quy tắc (ví dụ `CANCELLED → SHIPPED`).

## 7. Firebase web SDK và phân quyền đọc dữ liệu

Với ứng dụng web/mobile truy cập Firestore trực tiếp, **Firebase Authentication + Firestore Security Rules** là lớp kiểm soát quyền của client. Với Java server SDK chạy trên Cloud Run/GKE, ứng dụng dùng **Application Default Credentials và IAM**; **server client libraries bỏ qua Security Rules**, do đó backend phải tự kiểm tra quyền nghiệp vụ của caller.

### 7.1. Web client truy vấn đơn của người đang đăng nhập

Ví dụ dùng **Firebase Web modular SDK**; giả định `app` được khởi tạo bằng Firebase config hợp lệ và Firebase Authentication đã đăng nhập:

~~~javascript
import { getAuth } from "firebase/auth";
import {
  getFirestore, collection, query, where,
  orderBy, limit, getDocs
} from "firebase/firestore";

const db = getFirestore(app);
const uid = getAuth(app).currentUser?.uid;
if (!uid) throw new Error("Authentication required");

const q = query(
  collection(db, "orders"),
  where("userId", "==", uid),
  orderBy("createdAt", "desc"),
  limit(20)
);

const snapshot = await getDocs(q);
const orders = snapshot.docs.map(d => ({ id: d.id, ...d.data() }));
~~~

Đây là **đoạn mã trong ứng dụng đã cấu hình Firebase**, không phải một script chạy độc lập. Query này cần index tương ứng và **Rules cho phép đọc dữ liệu của chính user**. Không được dùng client-provided `userId` thay cho UID đã xác thực khi ra quyết định quyền.

### 7.2. Security Rules mẫu: chỉ đọc đơn của chính mình

~~~javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /orders/{orderId} {
      allow get, list: if request.auth != null
        && resource.data.userId == request.auth.uid;

      // Ứng dụng này chỉ ghi đơn qua backend được kiểm soát.
      allow create, update, delete: if false;

      match /items/{itemId} {
        allow get, list: if request.auth != null
          && get(/databases/$(database)/documents/orders/$(orderId))
               .data.userId == request.auth.uid;
        allow create, update, delete: if false;
      }
    }
  }
}
~~~

**Cách hiểu:**

- Client chỉ đọc document `orders/{orderId}` nếu field `userId` bằng Firebase Auth UID.
- Client đọc subcollection items khi là chủ sở hữu document cha.
- Ví dụ chỉ cho **read**, writes đi qua backend đã kiểm tra user, giá tiền, tồn kho và trạng thái.
- Rule `get(parent)` có thể phát sinh **document reads** và chịu quota số lần đọc trong Rules; không dùng vô hạn trên hàng nghìn document.
- Đây là **mẫu một phần** của ruleset; nếu app còn collections khác phải định nghĩa chúng riêng, không thêm `match /{document=**} { allow read, write: if true; }`.

**Rules không phải bộ lọc.** Query `collection("orders")` không lọc `userId` sẽ bị **từ chối toàn bộ** nếu Firestore không thể bảo đảm mọi document có thể trả về đều thuộc user hiện tại. Client phải truy vấn `where("userId","==",uid)`; không thể “tải tất cả rồi để Rules lọc các đơn người khác”.

### 7.3. Collection-group security rules

Khi mobile/web chạy `collectionGroup("items")`, cần **rules version 2** với match phù hợp cả các đường dẫn subcollection trong nhóm, và index ở **collection group scope**. Nếu các nhánh cha khác nhau dùng cùng tên `items`, quy tắc phải bao phủ **tất cả** trường hợp có thể được query trả về, đồng thời giới hạn đúng owner/tenant.

Không tự thêm quy tắc wildcard `allow read: if request.auth != null` cho cả collection group. Khi yêu cầu phân quyền phức tạp, cân nhắc truy vấn qua backend đã kiểm tra IAM/business auth hoặc bổ sung field `ownerUid` trên mỗi item và kiểm thử Rules bằng emulator.

### 7.4. Firestore server SDK không bị Rules chặn

Một backend Java dùng ADC với IAM `roles/datastore.user` (hoặc role tùy chỉnh có đúng permissions) có thể truy cập dữ liệu nằm trong phạm vi được cấp **không đi qua Firebase Security Rules**. Nếu endpoint backend nhận `GET /orders/{id}`, phải tự đối chiếu order `userId` với principal đã được xác thực; không trông chờ Rules ở phía client bảo vệ server endpoint.

**Phân lớp:**

| Lớp | Bảo vệ gì? |
| --- | --- |
| Firebase Authentication | Danh tính người dùng cuối |
| Firestore Security Rules | Quyền đọc/ghi của web/mobile SDK dựa trên auth/data |
| Google Cloud IAM | Quyền của workloads/servers/service accounts đối với Firestore |
| Backend business checks | Tồn kho, quyền đặt hàng, tính giá và trạng thái giao dịch |
| App Check khi phù hợp | Giảm lưu lượng từ client giả mạo; **không thay auth hoặc Rules** |

## 8. Tính nhất quán: batch, transaction và snapshot

Firestore không tự tạo **foreign key** giữa `orders.userId` và `users/{uid}`. Nó cũng không tự kiểm tra `totalMinor = sum(items)`. Khi nhiều documents phải được cập nhật cùng một giao dịch, cần chủ động thiết kế.

### 8.1. Batched write: ghi nhiều documents nguyên tử

Nếu chỉ cần tạo order và items theo dữ liệu **đã kiểm tra trong backend**, dùng WriteBatch:

~~~java
import com.google.cloud.firestore.WriteBatch;

DocumentReference orderRef =
    db.collection("orders").document();
DocumentReference itemRef =
    orderRef.collection("items").document("line_01");

Map<String, Object> orderData = Map.of(
    "userId", "user_123",
    "status", "CREATED",
    "totalMinor", 129900L
);
Map<String, Object> itemData = Map.of(
    "productId", "sku_001",
    "quantity", 2L,
    "unitPriceMinor", 64950L
);

WriteBatch batch = db.batch();
batch.set(orderRef, orderData);
batch.set(itemRef, itemData);
batch.commit().get();
~~~

**Toàn batch commit hoặc không có ghi nào được áp dụng.** Mẫu này chưa cập nhật stock, chưa gắn createdAt, chưa tính thuế và không kiểm tra business validation; chỉ minh họa tính nguyên tử khi ghi parent và item. Với bulk import lớn, không gom vô hạn documents vào một batch; dùng công cụ phù hợp như BulkWriter và xem giới hạn API.

### 8.2. Transaction: đọc rồi quyết định ghi

Nếu cần trừ tồn kho có kiểm tra, dùng transaction. Ví dụ logic **chỉ làm rõ thao tác trên một sản phẩm**:

~~~java
DocumentReference product =
    db.collection("products").document("sku_001");

db.runTransaction(tx -> {
    DocumentSnapshot snapshot = tx.get(product).get();
    Long available = snapshot.getLong("stock");
    long requested = 2L;

    if (available == null || available < requested) {
        throw new IllegalStateException("Out of stock");
    }
    tx.update(product, "stock", available - requested);
    return null;
}).get();
~~~

Firestore có thể **retry transaction callback** khi tranh chấp. Vì vậy **không gửi email, gọi cổng thanh toán hoặc publish Pub/Sub ngay trong callback**: tác dụng phụ có thể chạy lặp. Để checkout đúng nghiệp vụ, cần thêm order ID/idempotency, xử lý ghi documents liên quan trong transaction hợp lệ và kiểm chứng tình huống retry.

Một **stock document nóng** của SKU bán chạy có thể bị contention ngay cả khi transaction đúng. Khi lưu lượng rất lớn, cân nhắc distributed counters, reservation/queue hoặc mô hình tồn kho riêng; không tăng throughput chỉ bằng việc thêm nhiều clients.

### 8.3. Khi nào nên giữ snapshot thay vì đọc tham chiếu?

Một order item nên lưu `unitPriceMinor` và `productName` tại thời điểm mua. Sau một năm, giá sản phẩm có thể thay đổi hoặc sản phẩm bị xóa, nhưng hóa đơn cũ vẫn cần thể hiện dữ liệu lịch sử. Việc lặp một vài fields là chủ đích:

- **Read model** nhanh hơn vì không JOIN nhiều documents.
- **Write path** cần chịu trách nhiệm đồng bộ/snapshot đúng thời điểm.
- **Consistency** là lựa chọn thiết kế, không có một quy tắc “luôn chuẩn hóa” hay “luôn nhúng”.

## 9. Mở rộng quy mô và tránh hotspot

### 9.1. Những anti-pattern thường gặp

| Thiết kế dễ mắc lỗi | Vì sao nguy hiểm | Cách cải thiện |
| --- | --- | --- |
| Một document `orders-summary` ghi counter cho mọi đơn | Tranh chấp khi nhiều writers cập nhật cùng document | Distributed counter/aggregation phù hợp |
| Document IDs `order-000001`, `order-000002` | Key tuần tự tạo hotspot ở tải ghi cao | Auto IDs hoặc IDs phân tán |
| Mọi tin nhắn chat trong array ở `rooms/{id}` | Document phình, giới hạn 1 MiB, update contention | `rooms/{id}/messages/{messageId}` |
| Field `createdAt` tăng tuần tự và **được index** với tốc độ ghi cao | Index hotspot; với collection có indexed sequential field có ngưỡng khoảng **500 writes/s** | Exempt index khi không truy vấn field đó; phân hoạch workload nếu cần query |
| Index toàn bộ `largeBlobText`, map/array lớn | Tốn storage và index fanout | Single-field index exemption khi không query |
| Client đọc mọi `orders` rồi lọc theo user | Phí cao và không phù hợp Rules | Filter trong Firestore query và Rule |
| `offset(10000)` để phân trang | Bỏ qua nhiều documents vẫn có thể bị tính reads | Query cursor + limit |
| Xóa order cha, tưởng items biến mất | Orphan subcollection documents | Quy trình recursive cleanup/TTL theo mô hình |
| Ghi đè document bằng `set` với fields thiếu | Mất dữ liệu fields cũ | Update/merge/precondition |
| Thiết kế quá sâu không có mục tiêu | Rules/index/cleanup và query phức tạp | Chọn hierarchy phục vụ đường đọc thật |

**Điểm cần phân biệt:** 500 writes/s nói về hotspot khi **field có giá trị tăng/giảm tuần tự được index**, không phải một mức trần tuyệt đối áp lên mọi Firestore collection. Firestore có thể scale rất cao nếu ID, index, phân phối key và traffic ramp-up được thiết kế phù hợp.

### 9.2. Index fanout ảnh hưởng write latency

Mỗi lần ghi document, Firestore cập nhật các index entries liên quan. Một document có nhiều array elements, nhiều fields được index và hàng loạt composite indexes có thể tạo nhiều ghi index. Khi fields lớn không dùng để lọc/sort, hãy xem **single-field exemptions**, cân đối hiệu năng và khả năng truy vấn.

**Không vô hiệu hóa index của `userId` hoặc `createdAt` nếu các màn hình chính vẫn dùng chúng.** Đề xuất exemption phải đi kèm inventory truy vấn và regression tests.

### 9.3. Tăng traffic từng bước

Firestore tự quản lý phân vùng lưu trữ, nhưng khi đưa dữ liệu/traffic vào một dải key mới, không nên đẩy đột ngột toàn tải. Với migration và import, áp dụng **ramp-up dần**, random/scattered IDs và giám sát p95, lỗi retry/contention, index build. Có thể dùng **Key Visualizer** khi được hỗ trợ để tìm hotspots ở document/index key ranges.

## 10. Xóa dữ liệu, TTL và thay đổi schema

### 10.1. Xóa cha không tự dọn subcollection

Giả sử đã có:

~~~text
orders/order_abc
orders/order_abc/items/line_01
orders/order_abc/items/line_02
~~~

Nếu dùng SDK gọi `orders/order_abc.delete()`, các document `items/line_01` và `items/line_02` **vẫn tồn tại**. Vì vậy:

- Với **soft delete**, đặt `deletedAt`/`status` và loại khỏi query theo policy, sau đó dọn nền có kiểm soát.
- Với **hard delete**, có runbook truy vấn/xóa các subcollections và parent trong các batches thích hợp, xử lý retry/idempotency và phí reads/deletes.
- Với dữ liệu có yêu cầu lưu trữ/kiểm toán, xác định retention, backup và deletion policy trước khi xóa.
- **TTL** cho phép xóa documents dựa một timestamp field; việc TTL xóa parent cũng **không thay** recursive subcollection cleanup.

Một số thao tác **Delete document** từ Firebase Console có hành vi dọn lồng ghép riêng theo giao diện; không lấy hành vi của Console làm giả định cho lời gọi `delete()` qua SDK. Khi hướng dẫn code hoặc production automation, luôn kiểm chứng semantics của **API cụ thể**.

### 10.2. Di chuyển schema an toàn

Firestore không buộc mọi document trong cùng collection có đúng bộ fields như nhau. Điều này tạo linh hoạt nhưng khi API đổi từ `total` sang `totalMinor`, nhiều documents cũ có thể thiếu field mới.

Một migration an toàn:

1. **Expand:** ứng dụng đọc được cả schema cũ/mới; writes mới thêm field chuẩn.
2. **Backfill:** xử lý các documents cũ theo batches, có checkpoints và retry; tránh tải một lần toàn collection.
3. **Observe:** kiểm chứng số documents đã chuyển, query index và Rules.
4. **Switch:** đổi read paths sang field mới và đo lỗi.
5. **Contract:** ngừng hỗ trợ field cũ khi rollback window hết, dọn index/data sau phê duyệt.

Với hệ thống event-driven, Cloud Functions/Cloud Run triggers có thể đồng bộ projections nhưng phải xử lý **at-least-once delivery, duplicate events và out-of-order updates**. Không mặc định mỗi trigger chỉ chạy một lần.

## 11. Chi phí, khả năng quan sát và chọn database

### 11.1. Những yếu tố ảnh hưởng chi phí

Firestore Standard có phí theo **document reads, writes, deletes**, index entry reads tùy loại query, storage (documents và indexes), network egress, backup/PITR/TTL và tính năng phụ trợ. Với real-time listeners, cập nhật document có thể tạo thêm document reads cho clients đang lắng nghe.

Ví dụ màn hình danh sách tải **20 orders**, rồi mỗi order tải **5 items** riêng:

~~~text
Orders:         20 document reads (khái quát)
Items:       20 × 5 = 100 document reads
Tổng tối thiểu: 120 document reads cho lượt tải (giả định có đủ items)
~~~

Đây là **minh họa số documents được đọc**, không phải hóa đơn chính xác: phí còn phụ thuộc index reads, Rules additional reads, cache, listeners, offset và cách API thực thi. Nếu thiết kế một trang đơn chỉ cần summary, không nên tải toàn bộ items của tất cả đơn ngay lập tức.

### 11.2. Metrics/kiểm tra nên có

| Tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| Document reads/writes/deletes | Màn hình hoặc job nào gây tăng reads? |
| Index storage & index builds | Có index dư hoặc thiếu không? |
| Query latency/p95 | Query bị thiếu index, hotspot hay nhiều kết quả? |
| Permission denied | Rules sai, query không tương thích hay IAM thiếu? |
| Contention/retries | Một document bị ghi quá nhiều? |
| Orphan subcollections | Có xóa cha không cleanup đúng? |
| Billing/Budgets | Phí có vượt dự kiến theo reads, storage, egress không? |
| Data residency/location | Database region/multi-region phù hợp user/Cloud Run backend? |

Chọn location **gần nhóm người dùng và dịch vụ tính toán** để giảm latency/chi phí dữ liệu; regional và multi-region có đánh đổi về tính sẵn sàng, chi phí và write latency.

### 11.3. Khi nào không nên dùng Firestore?

| Yêu cầu | Cân nhắc |
| --- | --- |
| Giao dịch nhiều bảng với JOIN phức tạp, schema chặt, SQL reporting | **Cloud SQL / AlloyDB** |
| Analytics quét hàng tỷ records, joins/aggregations lớn | **BigQuery** |
| Key-value/cache với TTL tốc độ rất cao | **Memorystore/Redis-compatible cache** |
| Lưu file PDF, ảnh, video lớn | **Cloud Storage**, Firestore chỉ lưu metadata/URL |
| Document-oriented application dữ liệu nhỏ/đọc theo key/query indexed | **Firestore** phù hợp |

Đây không phải tiêu chuẩn tuyệt đối; mỗi lựa chọn phải đánh giá SLA, dữ liệu, query patterns, IAM, chi phí và khả năng tích hợp.

## 12. Xử lý lỗi thường gặp

| Dấu hiệu | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `PERMISSION_DENIED` từ Firebase web SDK | Auth thiếu, Rules không cho query, collection-group rules sai | Kiểm tra UID, query constraints, Rules Emulator |
| Backend Java đọc được nhưng web không đọc được | Java server SDK đi qua IAM, **bỏ qua Rules** | Bổ sung Rules đúng scope, không mở public |
| Query filter+sort báo thiếu index | Chưa có composite index | Tạo index từ link lỗi/IaC, đợi build |
| Query có orderBy không trả document cũ | Document thiếu field sort | Backfill/đảm bảo defaults |
| Document vượt 1 MiB | Nhúng array/history tăng vô hạn | Đưa danh sách sang subcollection |
| Read latency tăng khi tải trang orders | N+1 queries tải tất cả items | Chỉ tải items khi mở order, phân trang |
| Ghi đơn liên tục chậm | Hot document/index hoặc tranh chấp stock | Auto IDs, tối ưu index, phân tán counters |
| Xóa user rồi vẫn thấy addresses từ direct path | SDK không cascade subcollections | Recursive cleanup/retention |
| Không thể cập nhật document chưa tồn tại | `update()` yêu cầu document tồn tại | Dùng `set(..., merge)` khi cần upsert |
| Thay map làm mất nested field | `set()` overwrite toàn document/map | Dot-path update hoặc merge |
| Transaction callback bị chạy lại | Firestore retry do contention | Loại side effects khỏi callback, dùng idempotency |
| Tiền tính sai | Dùng float hoặc tin giá do client gửi | Integer minor units, tính lại ở backend |
| Hóa đơn cũ đổi theo tên/giá product mới | Chỉ lưu reference mà không snapshot | Lưu immutable price/name vào order items |
| Index storage tăng nhanh | Index nhiều fields/arrays lớn | Query inventory + exemptions phù hợp |

**Thứ tự điều tra:** path/database đúng → document tồn tại → Auth/Rules/IAM → query/index → schema fields → read/write patterns → contention/cost. Không cấp role Owner hoặc đặt `allow read, write: if true` để chữa lỗi.

## 13. Case study: thiết kế tiến hóa từ bản MVP

**Bối cảnh:** Một nhóm xây ứng dụng đặt hàng trên Firebase, ban đầu chỉ có 200 đơn/ngày; sau sáu tháng là 100.000 đơn/ngày. Thiết kế MVP:

~~~json
{
  "userId": "user_123",
  "orders": [
    {"id": "o1", "totalMinor": 129900},
    {"id": "o2", "totalMinor": 259800}
  ]
}
~~~

Toàn bộ `orders` được nhúng trong `users/user_123`.

**Vấn đề khi tăng trưởng:** Document user phình lớn, ghi tranh chấp, khó phân trang/đếm, mỗi lần tải profile kéo cả danh sách đơn. Thay đổi đề xuất:

~~~text
users/user_123
  displayName, preferences

orders/order_abc
  userId, status, createdAt, totalMinor, currency, shipping
  items/line_01
  items/line_02
~~~

**Lợi ích:** Các orders là document riêng với auto IDs, hỗ trợ list/query theo user; subcollection items có thể tăng mà không tăng kích thước order cha. **Đánh đổi:** Chi tiết order cần thêm reads, cần composite indexes, Rules giới hạn theo `userId` và xử lý xóa parent/children cẩn thận.

**Quyết định khác:** Ứng dụng phân tích doanh thu đa chiều nên đưa sự kiện/đồng bộ được kiểm soát sang BigQuery thay vì yêu cầu Firestore tự thực hiện hàng loạt joins/aggregations.

## 14. Bài lab thiết kế và kiểm chứng

Có thể dùng **Firestore Emulator** để tránh ghi lên production. Nếu dùng cloud thật, chọn project lab và database được phép; không dùng dữ liệu khách hàng hoặc thông tin thanh toán thật.

### 14.1. Chuẩn bị an toàn

1. Chọn **Firestore in Native mode** với edition/dialect tương ứng hướng dẫn.
2. Dùng Firebase Emulator Suite nếu có Firebase CLI và project lab.
3. Với Java backend: thiết lập ADC cho môi trường phù hợp hoặc trỏ client tới emulator; không commit service account JSON keys.
4. Với web app: dùng Firebase Authentication test accounts và Rules emulator.
5. Bật budget/alerts nếu truy cập database cloud thật.

Ví dụ khởi động emulator trong **thư mục lab đã có `firebase.json` cấu hình emulator**, không phải trong repository bài học:

~~~bash
firebase emulators:start --only firestore --project demo-firestore-lab
~~~

Backend Java có thể dùng biến `FIRESTORE_EMULATOR_HOST=127.0.0.1:8080` (đúng port emulator đã cấu hình). Emulator không thay thế load testing ở production hay kiểm chứng toàn bộ khả năng của edition/multi-region, nhưng giúp thử schema và Security Rules.

### 14.2. Nhiệm vụ

| Bước | Thao tác | Bằng chứng |
| --- | --- | --- |
| 1 | Vẽ `users/products/orders/items` và paths xen kẽ | Sơ đồ collection/document |
| 2 | Tạo 2 users, 3 products, 3 orders bằng dữ liệu giả | Các paths và fields đúng loại |
| 3 | Thêm 1–3 items cho mỗi order | Không nhúng danh sách không giới hạn vào order |
| 4 | Query orders của một user, `orderBy(createdAt desc)` | Kết quả đúng, có index |
| 5 | Query items của một order | Không phải đọc lại tất cả orders |
| 6 | Thử Rules: user A đọc order A được, order B bị từ chối | Kết quả Emulator tests |
| 7 | Thử `collectionGroup("items")` và index phù hợp | Kết quả có đúng phạm vi không |
| 8 | Xóa **parent test order** bằng SDK | Chứng minh items còn; lập cleanup plan |
| 9 | So reads khi trang orders chỉ đọc summary và khi tải items | Ước lượng chi phí hai phương án |
| 10 | Viết kế hoạch backfill cho field mới | Không mất orders cũ |

**Không chạy thử delete trên dữ liệu thật.** Khi tạo tên `items` cho nhiều subcollections, kiểm tra group query/Roles trước khi expose API.

### 14.3. Tiêu chí hoàn thành

- Đường dẫn đúng thứ tự collection/document.
- Đã giải thích vì sao một field được nhúng, một danh sách đặt ở subcollection.
- Có index phục vụ query chính và giới hạn quyền đọc theo UID.
- Phân biệt Java server IAM với Firebase client Rules.
- Có cách ghi order + items atomic khi nghiệp vụ yêu cầu.
- Có bản ghi về reads, hiệu năng và quy trình dọn subcollection.

## 15. Câu hỏi ôn tập và checklist

### 15.1. Câu hỏi kèm đáp án ngắn

1. **Firestore khác bảng SQL ở đâu?** Dữ liệu nằm trong documents thuộc collections, không có JOIN theo cách SQL truyền thống.
2. **Đường dẫn `users/u1/orders/o1` trỏ gì?** Document `o1` trong subcollection `orders` của document `users/u1`.
3. **Tạo collection có cần DDL không?** Không; collection xuất hiện khi ghi dữ liệu.
4. **Map khác subcollection?** Map nằm trong một document, subcollection chứa những documents riêng và query riêng.
5. **Dữ liệu nào nên lưu snapshot trong order?** Giá/tên sản phẩm tại checkout, địa chỉ giao hàng tại thời điểm đặt.
6. **Một document có thể lớn vô hạn?** Không; Standard giới hạn 1 MiB.
7. **Xóa order document có xóa items không?** Không qua SDK delete mặc định.
8. **Hai collections `items` dưới hai orders có thể query chung không?** Có, qua collection group query với index và Rules phù hợp.
9. **Dùng ID order tuần tự để ghi nhiều có tốt không?** Có nguy cơ hotspot; dùng IDs phân tán.
10. **Truy vấn `where(userId)` + `orderBy(createdAt)` có thể cần gì?** Composite index.
11. **Security Rules có tự lọc kết quả không?** Không; query phải thỏa Rules.
12. **Java server SDK có bị Security Rules giới hạn không?** Không; dùng IAM, backend tự kiểm quyền.
13. **Khi query orderBy mà field thiếu, document có được trả không?** Không.
14. **Transaction khác batch?** Transaction có thể đọc dữ liệu rồi quyết định ghi và retry; batch ghi atomically mà không cần đọc.
15. **Có nên đưa thao tác thanh toán vào transaction callback?** Không; callback có thể chạy lại.
16. **Dùng array lưu 10.000 chat messages trong một document?** Không phù hợp; nên tạo documents trong subcollection.
17. **Vì sao nhiều Firestore indexes có thể làm write chậm?** Index fanout làm tăng cập nhật entries.
18. **Pagination offset lớn hay cursor tốt hơn?** Cursor thường phù hợp hơn và tránh reads do skipped results.
19. **User xóa tài khoản có nghĩa mọi subcollection tự xóa?** Không; cần deletion workflow rõ ràng.
20. **Firestore có thay BigQuery analytics không?** Không; nên chọn theo workload/reporting.

### 15.2. Checklist production

- [ ] Use cases và query paths được ghi thành bảng trước khi tạo schema.
- [ ] Các document IDs phù hợp, không rò thông tin nhạy cảm.
- [ ] Fields có kiểu dữ liệu rõ: tiền minor units, timestamps, status enums.
- [ ] Embed maps/lists chỉ khi có giới hạn và đọc chung với parent.
- [ ] Subcollections chứa dữ liệu có thể phát triển nhiều phần tử hoặc cần phân trang.
- [ ] Root collections phục vụ truy vấn xuyên user/order và collections có lifecycle độc lập.
- [ ] Có indexes cho filter/sort, không tạo indexes dư thừa gây write fanout.
- [ ] Security Rules thử qua Emulator với users thật/giả; server IAM được cấp tối thiểu.
- [ ] Backend kiểm tra business ownership và quyền truy cập, không chỉ tin client fields.
- [ ] Batch/transaction/idempotency được dùng nơi cần consistency.
- [ ] Không có hot counter, hot document, sequential IDs/indexes ở tải cao.
- [ ] Có retention/TTL, recursive delete, backup/restore và migration plan.
- [ ] Pagination, read cost, listener lifecycle, data location và budgets được theo dõi.
- [ ] Logs/traces không chứa token, địa chỉ cá nhân hoặc dữ liệu đơn hàng nhạy cảm.

## 16. Tài liệu chính thức

- [Firestore data model](https://firebase.google.com/docs/firestore/data-model) — documents, collections, subcollections và collection group.
- [Choose a data structure](https://firebase.google.com/docs/firestore/manage-data/structure-data) — embedded data, root collections và subcollections.
- [Usage and limits](https://firebase.google.com/docs/firestore/quotas) — 1 MiB/document, nesting và indexes.
- [Add and update data](https://firebase.google.com/docs/firestore/manage-data/add-data) — `set`, `update`, server timestamps và nested fields.
- [Query data](https://firebase.google.com/docs/firestore/query-data/queries) — filters, sorting, collection group.
- [Indexes](https://firebase.google.com/docs/firestore/query-data/indexing) — single-field/composite indexes và index exemptions.
- [Query cursors](https://firebase.google.com/docs/firestore/query-data/query-cursors) — pagination không dựa offset.
- [Transactions and batched writes](https://firebase.google.com/docs/firestore/manage-data/transactions) — atomicity và transaction retries.
- [Security Rules](https://firebase.google.com/docs/firestore/security/get-started) — Firebase Auth vs server IAM.
- [Test Security Rules](https://firebase.google.com/docs/firestore/security/test-rules-emulator) — Emulator tests.
- [Delete documents and collections](https://firebase.google.com/docs/firestore/manage-data/delete-data) — xóa cha không cascade subcollections.
- [Best practices](https://docs.cloud.google.com/firestore/native/docs/best-practices) — index fanout, hotspotting và traffic ramp-up.
- [Firestore pricing](https://firebase.google.com/docs/firestore/pricing) — reads/writes/deletes, storage và index costs.
- [Firestore Java client](https://cloud.google.com/java/docs/reference/google-cloud-firestore/latest/overview) — Java SDK và ADC.

**Ghi nhớ:** Trong Firestore, **collection tổ chức documents; document chứa fields; subcollection chứa documents con**. Hãy thiết kế từ **truy vấn, quyền truy cập và tốc độ tăng trưởng**, không từ sơ đồ bảng SQL. Nhúng dữ liệu nhỏ, tách dữ liệu tăng trưởng thành documents riêng, tạo indexes đúng truy vấn và luôn tính tới **Security Rules, IAM, xóa dữ liệu con, hotspotting và chi phí reads**.
