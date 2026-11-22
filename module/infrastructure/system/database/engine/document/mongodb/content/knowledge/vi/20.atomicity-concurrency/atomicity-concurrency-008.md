# Lựa chọn giữa nhúng dữ liệu, cập nhật nguyên tử và giao dịch

Trong MongoDB, nhiều vấn đề đồng thời không nhất thiết phải giải bằng một **multi-document transaction**. Một số bất biến nghiệp vụ có thể được giữ an toàn bằng cách **nhúng dữ liệu liên quan vào cùng một document**, rồi thực hiện **một thao tác cập nhật nguyên tử**. Những bất biến khác trải qua nhiều document hoặc nhiều collection thì một update đơn lẻ không đủ; khi đó cần **transaction** hoặc một cơ chế phối hợp nhất quán khác.

Bài học thuộc chương **Nguyên tử và cạnh tranh** của module *Database Engine Document MongoDB*. Trọng tâm không phải “API transaction viết thế nào” riêng lẻ, mà là **quyết định đúng ranh giới nhất quán từ lúc thiết kế dữ liệu**, tránh cả hai cực đoan: ép toàn bộ hệ thống vào một document khổng lồ hoặc dùng transaction cho mọi thao tác nhỏ.

Sau bài, bạn có thể:

1. Phân biệt **atomicity một document**, **điều kiện chống race**, **tính nhất quán nhiều document** và **durability**.
2. Chọn **embedding** khi các trường có vòng đời và bất biến chung, nhưng nhận diện giới hạn 16 MiB, hot document và mảng tăng vô hạn.
3. Viết `updateOne()` có `$inc`, `$set`, `$push`, `$addToSet`, `arrayFilters` để thay đổi nhiều trường **trong cùng một document**.
4. Dùng **compare-and-set (CAS)**, phiên bản `version` và filter có điều kiện để chống lost update / overselling.
5. Phân biệt `updateMany()`, `bulkWrite()` và multi-document transaction: **gom nhiều lệnh không tự tạo atomicity toàn nhóm**.
6. Viết transaction bằng `ClientSession`/`mongosh` cho thao tác nhiều document, xử lý commit/abort và hiểu lỗi retry.
7. Chọn **read concern**, **write concern** và phương án idempotency đúng yêu cầu mà không nhầm chúng với transaction.
8. Đánh giá chi phí transaction, contention, mối quan hệ giữa mô hình dữ liệu và hiệu năng, cũng như lựa chọn saga/outbox khi có hệ thống bên ngoài.

> **Phạm vi phiên bản:** Ví dụ sử dụng cú pháp MongoDB hiện đại phổ biến trên replica set/sharded cluster và Java Sync Driver các dòng được hỗ trợ. Các giới hạn transaction, session, retry và read/write concern cần đối chiếu MongoDB Server/Driver đang chạy. Ví dụ transaction không chạy theo cùng cách trên một **standalone mongod**, vì multi-document transactions đòi deployment hỗ trợ. Mọi lệnh demo dùng database `atomic_choice_lab`; không chạy trên production.

## 1. Ba lớp quyết định: dữ liệu nằm đâu, cập nhật thế nào, cần commit bao nhiêu document?

Khi gặp yêu cầu “phải cập nhật A và B cùng nhau”, trước tiên cần xác định **A/B là gì**:

~~~text
Yêu cầu nghiệp vụ
       |
       v
A và B có thể thuộc CÙNG một aggregate/document không?
       |
    +-- Có --> Nhúng các phần liên quan có giới hạn
    |          |
    |          v
    |      Một update nguyên tử + filter bảo vệ
    |          |
    |          +-- Nếu chỉ cần cập nhật trạng thái 1 document:
    |               không cần multi-document transaction.
    |
    +-- Không --> Dữ liệu phải sống ở nhiều documents/collections
               |
               v
         Cần tất cả thay đổi cùng commit/abort?
               |
           +---+---+
           |       |
          Có      Không
           |       |
           v       v
       Transaction   Updates độc lập / eventual consistency
       khi deployment   / saga-outbox, có idempotency
       hỗ trợ
~~~

Đây là sơ đồ **định hướng**, không phải một thuật toán áp dụng máy móc. Có trường hợp dù nhúng được về mặt kỹ thuật nhưng số phần tử tăng không giới hạn, nhiều writer cùng cập nhật document nóng, hoặc các thành phần có vòng đời độc lập — khi đó **tham chiếu (reference)** hợp lý hơn.

### 1.1. Bảng so sánh ba chiến lược

| Chiến lược | Ranh giới nguyên tử | Ưu điểm | Chi phí/rủi ro |
|---|---|---|---|
| **Nhúng dữ liệu + một update** | Một document chứa nhiều field/subdocument/array item. | Đơn giản, thường hiệu quả, giữ nhiều trường cùng lúc. | Document có thể phình to; hot spot; dữ liệu bị lặp; khó tách vòng đời. |
| **Update nguyên tử có điều kiện trên document hiện có** | Một document, dù data model chứa scalar hay embedded fields. | Kiểm tra điều kiện và thay đổi tại server trong một write; chống nhiều race đơn giản. | Không bảo đảm thay đổi ở document khác; filter/logic phải đúng; retry nghiệp vụ cần thiết kế. |
| **Multi-document transaction** | Nhiều thao tác/document/collection/shard trong phạm vi transaction được hỗ trợ. | All-or-nothing và isolation theo concern; phù hợp bất biến liên tài liệu. | Đắt hơn, tăng contention/cache/lock, cần session, retry logic, giới hạn tài nguyên. |

**Embedding** là quyết định **mô hình dữ liệu**; **atomic update** và **transaction** là quyết định **cách thực thi ghi**. Không xem chúng như ba API đối lập hoàn toàn. Bạn có thể dùng atomic update trên một document embedded; cũng có thể dùng transaction trong một hệ thống chủ yếu embedded khi thực sự có nghiệp vụ nhiều document.

### 1.2. Ba câu hỏi cốt lõi

1. **Bất biến cần bảo vệ ở đâu?** Ví dụ `available >= 0` và danh sách checkout của một quyển sách nằm trong **một book document**; tổng số dư hai tài khoản nằm trong **hai account documents**.
2. **Có bao nhiêu document phải đổi trong cùng một bước nghiệp vụ?** Một `updateMany()` sửa 10 document **không phải** một thay đổi nguyên tử toàn tập.
3. **Nếu request bị thực thi hai lần hoặc fail ở giữa, điều gì xảy ra?** `$inc` có thể tăng/giảm hai lần nếu ứng dụng replay; transaction rollback không thay thế idempotency cho **request nghiệp vụ lặp**.

## 2. “Nguyên tử” trong MongoDB nghĩa là gì?

Theo MongoDB Database Manual, một **write operation sửa một document là atomic**: các field trong document đó được thay đổi **toàn bộ hoặc không thay đổi**, ngay cả khi update sửa nhiều field và nhiều phần tử của array.

~~~javascript
db.books.updateOne(
  { _id: "BOOK-1", available: { $gt: 0 } },
  {
    $inc: { available: -1 },
    $push: {
      checkout: {
        userId: "U-100",
        at: new Date()
      }
    }
  }
)
~~~

Nếu document khớp filter và update thành công, cả **`available` giảm một** và **`checkout` thêm một phần tử** trong cùng document. Một reader không thấy document ở trạng thái “đã giảm available nhưng checkout chưa được thêm” chỉ do update này được thực hiện từng nửa.

### 2.1. Một lệnh sửa nhiều document thì sao?

~~~javascript
db.products.updateMany(
  { category: "stationery" },
  { $set: { promotionEligible: true } }
)
~~~

Mỗi product document được sửa **một cách nguyên tử riêng**, nhưng **toàn bộ `updateMany()` không atomic như một transaction**. Khi có lỗi hoặc ghi đồng thời, có thể tồn tại trạng thái một số products đã đổi và số khác chưa đổi; các thao tác khác có thể xen vào.

Đây là phân biệt cơ bản:

| Thao tác | Atomicity mặc định |
|---|---|
| `insertOne()` | Một document được chèn hoặc không. |
| `updateOne()` | Một document. |
| `replaceOne()` | Một document. |
| `deleteOne()` | Một document. |
| `updateMany()` | **Từng document**, không nguyên tử toàn nhóm. |
| `deleteMany()` | **Từng document**, không nguyên tử toàn nhóm. |
| `bulkWrite()` | Mỗi operation/document theo semantics tương ứng; **không tự là transaction cả batch**. |
| Multi-document transaction | Nhóm thay đổi trong transaction **commit cùng nhau hoặc abort cùng nhau**. |

### 2.2. Atomicity khác durability và “exactly once”

Ba tính chất khác nhau:

- **Atomicity**: trong ranh giới được đảm bảo, thay đổi không ở trạng thái “làm một nửa”.
- **Durability/acknowledgment**: tùy write concern và điều kiện replica set/commit, thay đổi được xác nhận/bền vững tới mức nào.
- **Idempotency**: cùng một yêu cầu nghiệp vụ được **gửi lặp** có gây thêm tác động không.

Một `$inc:{stock:-1}` là **atomic** trên document nhưng **không idempotent** nếu một request mới được gửi lại sau khi request trước đã thành công. Một transaction có thể đảm bảo debit/credit cùng commit, nhưng nếu ứng dụng chạy **một transaction mới** lần thứ hai cho cùng mã chuyển tiền, tiền vẫn có thể bị chuyển hai lần trừ khi có cơ chế dedupe.

### 2.3. Bảo đảm “một document” không phải “không có race”

Hai client cùng chạy:

~~~javascript
// Client A
db.counters.updateOne(
  { _id: "C-1" },
  { $set: { value: 100 } }
)

// Client B
db.counters.updateOne(
  { _id: "C-1" },
  { $set: { value: 200 } }
)
~~~

Mỗi update là atomic, nhưng cả hai cùng match `_id`. Giá trị cuối có thể là **100 hoặc 200 tùy thứ tự thực thi**; không có bảo đảm ứng dụng sẽ được thông báo “bạn vừa ghi đè một thay đổi hợp lệ”. Khi cần phát hiện xung đột, dùng **filter theo giá trị kỳ vọng** hoặc **version**.

## 3. Embedding: đưa những dữ liệu phải thay đổi cùng nhau vào một document

MongoDB là document database, hỗ trợ embedded subdocuments/arrays. Nếu các thành phần của một **aggregate** thường được đọc/cập nhật cùng nhau và có cardinality được kiểm soát, nhúng dữ liệu giúp thực hiện một write nguyên tử.

### 3.1. Ví dụ tài liệu mượn sách

Mô hình tham chiếu có thể tách:

~~~javascript
// books
{ _id: "BOOK-1", title: "Sách A", available: 3 }

// checkouts
{ _id: "CO-1", bookId: "BOOK-1", userId: "U-1" }
~~~

Một nghiệp vụ mượn sách cần giảm `available` **và** tạo checkout, tức thay đổi **hai documents**. Không có transaction, nếu bước thứ nhất thành công rồi bước thứ hai lỗi, hai collection có thể lệch nhau.

Nếu danh sách checkout được giữ có giới hạn và phần dữ liệu có vòng đời chung, có thể **nhúng**:

~~~javascript
{
  _id: "BOOK-1",
  title: "Sách A",
  available: 3,
  checkout: [
    { userId: "U-1", at: ISODate("2026-11-12T08:00:00Z") },
    { userId: "U-2", at: ISODate("2026-11-13T08:00:00Z") }
  ]
}
~~~

Giờ chỉ một `updateOne` có thể cùng giảm available và thêm checkout. Đây là **thiết kế mô hình để thu nhỏ ranh giới nhất quán**, không phải chỉ thay cú pháp từ transaction thành update.

### 3.2. Khi embedding là lựa chọn tốt

Thường cân nhắc nhúng khi:

- **One-to-few** hoặc tập con **có giới hạn rõ ràng**, chẳng hạn vài địa chỉ giao hàng, vài bước xử lý hiện tại.
- Các field/embedded items **được cập nhật cùng nhau** và cùng vòng đời nghiệp vụ.
- Ứng dụng cần **đọc cùng nhau** thường xuyên.
- Một invariant quan trọng có thể được bảo vệ bằng một **filter + update** duy nhất.
- Số lượng writes vào cùng document không gây hot spot không chấp nhận được.

Ví dụ hợp lý: đơn hàng có `status`, `shippingAddressSnapshot`, `totals` và danh sách line items có giới hạn. Khi xác nhận order, có thể cập nhật `status` và `confirmedAt` cùng một lần.

### 3.3. Khi **không** nên nhúng chỉ vì muốn atomicity

Nhúng toàn bộ sẽ phản tác dụng nếu:

- Array tăng **không giới hạn** như hàng triệu log events, comments hoặc các giao dịch lịch sử.
- Nhiều writer độc lập luôn cùng cập nhật **một hot document**.
- Quan hệ **many-to-many** có vòng đời riêng, cần index/query/pagination theo phần tử.
- Các child records cần cập nhật riêng, gắn quyền truy cập khác nhau hoặc được lưu giữ theo chính sách retention khác nhau.
- Kích thước document có thể chạm **giới hạn BSON 16 MiB**.
- Dữ liệu bị nhúng trùng ở quá nhiều cha, khiến mỗi thay đổi nguồn phải cập nhật hàng nghìn document.

Một document vừa có `book.available` vừa có toàn bộ lịch sử checkout **vô hạn** có thể không phù hợp. Một phương án thường tốt hơn là chỉ nhúng **checkout đang hoạt động có giới hạn**, còn lịch sử dài nằm trong collection khác và được cập nhật theo workflow riêng. Ranh giới consistency phải được định nghĩa rõ: liệu lịch sử chỉ là dữ liệu bổ trợ/eventually consistent, hay bắt buộc phải commit cùng tồn kho?

### 3.4. Snapshot nhúng không giống nguồn dữ liệu chuẩn

Trong order, `shippingAddress` có thể là **snapshot tại thời điểm đặt hàng** và không cần tự thay đổi khi user sửa địa chỉ profile. Nhúng snapshot vào order là đúng dù cùng địa chỉ có thể lặp ở nhiều orders, vì mỗi order phải bảo toàn lịch sử.

Ngược lại, nếu `customerCreditLimit` cần duy trì một giá trị chuẩn cho toàn bộ đơn hàng, sao chép và sửa limit ở mọi order dễ gây nhất quán sai. Nên giữ source of truth ở customer/account document; nếu nhiều documents phải đổi cùng nhau theo bất biến, cân nhắc transaction hoặc thay đổi mô hình.

## 4. Bộ dữ liệu thử nghiệm

Các ví dụ sau chỉ dùng database `atomic_choice_lab`. Mỗi collection demo tách biệt để tránh việc một ví dụ gây hiệu ứng không mong muốn lên ví dụ khác. **Không chạy lại `insertOne/insertMany` với cùng `_id` nếu đã có fixture**; hãy chọn collection lab mới hoặc reset có chủ đích.

~~~javascript
const lab = db.getSiblingDB("atomic_choice_lab")

lab.books.insertOne({
  _id: "BOOK-1",
  title: "Sách A",
  available: 2,
  checkout: [],
  version: 1
})

lab.counters.insertOne({
  _id: "COUNTER-1",
  value: 10,
  version: 1
})

lab.stock.insertMany([
  {
    _id: "SKU-A",
    available: 5,
    reserved: 0,
    version: 1
  },
  {
    _id: "SKU-B",
    available: 10,
    reserved: 0,
    version: 1
  }
])

lab.accounts.insertMany([
  { _id: "ACC-A", balance: 1000, currency: "VND" },
  { _id: "ACC-B", balance: 200, currency: "VND" }
])

lab.orders.insertOne({
  _id: "ORD-1",
  customerId: "C-1",
  status: "DRAFT",
  total: 300,
  version: 1,
  items: [
    { lineId: "L1", sku: "SKU-A", qty: 1, picked: false },
    { lineId: "L2", sku: "SKU-B", qty: 2, picked: false }
  ],
  events: []
})
~~~

Với tài chính thật, **không lưu tiền bằng floating-point binary** nếu cần chính xác đến đơn vị nhỏ nhất. Fixture dùng số nguyên nhỏ để minh họa; hệ thống thực có thể dùng **integer minor units** hoặc BSON Decimal128 kèm quy tắc precision/currency rõ ràng. Đừng suy rằng `balance:1000` trong demo đã là thiết kế sổ cái tài chính đầy đủ.

### 4.1. Trường hợp nào là một document?

| Invariant | Nơi dữ liệu nằm | Cách tiếp cận có thể dùng |
|---|---|---|
| `books.available` phải giảm khi `books.checkout` thêm một entry | Trong `BOOK-1` | Một `updateOne` nguyên tử. |
| `orders.status` đổi cùng `orders.confirmedAt` | Trong `ORD-1` | Một update có filter trạng thái/version. |
| `orders.items[L1].picked` và `orders.status` cùng đổi | Trong `ORD-1` | Một update với `arrayFilters` và điều kiện thích hợp. |
| `accounts[ACC-A]` giảm và `accounts[ACC-B]` tăng | **Hai account documents** | Transaction nếu cùng commit/abort. |
| `stock[SKU-A]` và `stock[SKU-B]` cùng được đặt giữ cho một order | **Hai stock documents** | Transaction hoặc workflow reservation/saga rõ ràng. |
| `orders` đổi sang PAID và gửi email | MongoDB + **hệ thống email bên ngoài** | Transaction không bao trùm email; cần outbox/idempotency. |

## 5. Một update nguyên tử trên embedded document: mượn sách

Trong fixture, `BOOK-1` có `available:2` và `checkout:[]`. Khi người dùng mượn một bản sao, yêu cầu là:

~~~text
Điều kiện: available > 0
Thay đổi cùng lúc:
  available := available - 1
  checkout := checkout + một bản ghi mượn mới
~~~

Đây là bất biến rất thích hợp với **một document**.

### 5.1. Update có điều kiện và hai update operators

~~~javascript
const lab = db.getSiblingDB("atomic_choice_lab")

const result = lab.books.updateOne(
  {
    _id: "BOOK-1",
    available: { $gt: 0 }
  },
  {
    $inc: { available: -1 },
    $push: {
      checkout: {
        checkoutId: "CH-1001",
        userId: "U-100",
        borrowedAt: ISODate("2026-11-14T08:00:00Z")
      }
    }
  }
)

printjson(result)
lab.books.findOne({ _id: "BOOK-1" })
~~~

Trên fixture ban đầu, `matchedCount:1` và `modifiedCount:1`; sau update, `available:1` và array `checkout` có entry CH-1001. Vì cả hai field nằm **trong BOOK-1**, MongoDB bảo đảm hai thay đổi của **một update** cùng có hiệu lực.

### 5.2. Khi hai người cùng mượn cuốn cuối

Giả sử còn `available:1` và Client A/B cùng gửi:

~~~javascript
lab.books.updateOne(
  { _id: "BOOK-1", available: { $gt: 0 } },
  {
    $inc: { available: -1 },
    $push: { checkout: { checkoutId: "CH-A", userId: "U-A" } }
  }
)
~~~

Ở client B, phần `checkout` có ID khác; filter vẫn giống. MongoDB kiểm tra lại điều kiện khi thực hiện update concurrent:

~~~text
BOOK-1 available = 1
   |
   +-- A match available > 0, giảm còn 0 và push checkout
   |
   +-- B kiểm tra điều kiện tại thời điểm ghi -> available > 0 sai
         => matchedCount = 0; không push, không giảm tiếp
~~~

Nếu B thực hiện trước, kết quả đảo lại; **không quá bán số lượng còn lại** trong riêng BOOK-1. Đây là một ví dụ **server-side conditional update** thay thế pattern nguy hiểm “client đọc available rồi tự giảm”.

### 5.3. Phân biệt thất bại điều kiện với exception

`updateOne` trả `matchedCount:0` và `modifiedCount:0` khi **không có document khớp filter**. Đây không nhất thiết là exception; có thể là nghiệp vụ “hết sách”, “bản ghi đã bị đổi bởi request khác” hoặc “ID không tồn tại”. Nếu endpoint cần trả lý do chính xác, có thể đọc lại trạng thái, nhưng tránh đổi logic thành check-then-write không bảo vệ.

### 5.4. Một vấn đề khác: retry cùng một yêu cầu

Giả sử CH-1001 đã được ghi thành công nhưng client timeout trước khi nhận response. Nếu tầng ứng dụng tạo **một request mới** và gửi lại `$inc:-1` cùng `$push`, `available` có thể giảm **lần thứ hai** khi vẫn còn số lượng. Tính **atomic** không chống được **duplicate business request**.

Một cách giảm rủi ro trên **cùng document** là đặt **checkoutId** ổn định trong filter và array:

~~~javascript
const checkoutId = "CH-1002" // ID ổn định từ request/event.

const result = lab.books.updateOne(
  {
    _id: "BOOK-1",
    available: { $gt: 0 },
    "checkout.checkoutId": { $ne: checkoutId }
  },
  {
    $inc: { available: -1 },
    $push: {
      checkout: {
        checkoutId,
        userId: "U-101",
        borrowedAt: ISODate("2026-11-14T08:10:00Z")
      }
    }
  }
)
~~~

Nếu update trước đã thêm CH-1002, lần gửi lại không còn thỏa điều kiện `"checkout.checkoutId":{$ne:"CH-1002"}`, nên không giảm thêm. Hai client dùng cùng checkoutId, cùng một document, cũng không thể cùng thực hiện update chứa điều kiện này tại thời điểm ghi.

**Giới hạn:** `matchedCount:0` có thể là “đã xử lý checkoutId”, “hết sách” hoặc “không có BOOK-1”; ứng dụng cần đối soát theo checkoutId. Mảng checkout không thể tăng vô hạn. Với lịch sử mượn dài, cân nhắc tách lịch sử ra collection riêng, đồng thời định nghĩa workflow/transaction nếu lịch sử phải commit cùng tồn kho.

### 5.5. Muốn lấy document sau khi cập nhật

`findOneAndUpdate()` có thể **chọn, cập nhật và trả document** trong một thao tác, tránh phải gọi `updateOne` rồi `findOne` ở một lượt đọc riêng:

~~~javascript
const updated = lab.books.findOneAndUpdate(
  { _id: "BOOK-1", available: { $gt: 0 } },
  { $inc: { available: -1 } },
  { returnDocument: "after" }
)

printjson(updated)
~~~

Nếu không match, kết quả có thể là `null`. Lệnh minh họa **decrement**, không push checkout. Trong nghiệp vụ thật cần thay đổi cả hai trường cùng một update như mục 5.1. Tùy shell/driver, cách chỉ định trả tài liệu trước/sau cập nhật có thể khác; chọn đúng API.

## 6. Chống overselling bằng `$inc` và filter số lượng

Giả sử `SKU-A` có `available:5` và `reserved:0`. Đặt giữ **3 đơn vị** yêu cầu `available >= 3`:

~~~javascript
const lab = db.getSiblingDB("atomic_choice_lab")
const quantity = 3

const result = lab.stock.updateOne(
  {
    _id: "SKU-A",
    available: { $gte: quantity }
  },
  {
    $inc: {
      available: -quantity,
      reserved: quantity
    }
  }
)

printjson(result)
~~~

Nếu thành công, `SKU-A` từ `(available:5,reserved:0)` thành `(available:2,reserved:3)`. Hai field đổi **trong một document**, nên reader không thấy tình huống chỉ available giảm nhưng reserved chưa tăng từ thao tác này.

### 6.1. Sai: đọc ở client rồi `$set`

~~~javascript
// Pattern nguy hiểm dưới concurrency:
const stock = lab.stock.findOne({ _id: "SKU-A" })

if (stock.available >= 3) {
  lab.stock.updateOne(
    { _id: "SKU-A" },
    {
      $set: {
        available: stock.available - 3,
        reserved: stock.reserved + 3
      }
    }
  )
}
~~~

Hai client có thể cùng đọc `available:5`, `reserved:0`, rồi cùng ghi `available:2`, `reserved:3`. Database nhìn thấy **hai lần update thành công**, nhưng trạng thái cuối chỉ phản ánh **một lần đặt giữ**, khiến ứng dụng dễ cấp phát hàng sai. Đó là **lost update**, không phải thiếu atomicity của từng lệnh.

Giải pháp là **đưa điều kiện số lượng và phép tăng/giảm vào cùng câu update**. MongoDB không cho hai update làm available âm chỉ vì cả hai từng đọc thấy đủ ở thời điểm cũ.

### 6.2. Khác biệt giữa `$set` và `$inc` khi concurrent

~~~javascript
// Client A:
lab.stock.updateOne(
  { _id: "SKU-B" },
  { $inc: { reserved: 2 } }
)

// Client B:
lab.stock.updateOne(
  { _id: "SKU-B" },
  { $inc: { reserved: 3 } }
)
~~~

Nếu cả hai thành công đúng một lần, `reserved` tăng tổng cộng 5. `$inc` thay đổi **giá trị hiện tại tại server**, không `$set` giá trị tính từ snapshot client có thể cũ.

Nhưng `$inc` không đủ khi phải đảm bảo giới hạn: kết hợp `available:{$gte:quantity}`, `$inc available:-quantity`, `$inc reserved:+quantity` **trong một update**. Nếu cùng operation nghiệp vụ được replay, vẫn cần idempotency.

### 6.3. Bất biến nhiều field trong một document

Một stock aggregate có thể có:

~~~text
available >= 0
reserved >= 0
available + reserved == totalSupply
~~~

Một update `$inc:{available:-q,reserved:q}` bảo toàn tổng khi dữ liệu đầu đúng. MongoDB không tự hiểu invariant tổng quát này nếu application có đường ghi khác làm sai. Cần kiểm soát mọi write path, schema validation khi phù hợp và kiểm thử chuyển trạng thái.

## 7. Compare-and-set (CAS) và optimistic concurrency control

Khi nghiệp vụ đọc một document để chuẩn bị thay đổi phức tạp, không phải lúc nào cũng thay được bằng `$inc`. Nếu người dùng sửa một bài viết, có thể cần **phát hiện người khác đã sửa trước** thay vì ghi đè.

### 7.1. CAS bằng giá trị kỳ vọng

Ban đầu:

~~~javascript
{ _id: "COUNTER-1", value: 10, version: 1 }
~~~

Client A muốn đổi 10 thành 20:

~~~javascript
const resultA = lab.counters.updateOne(
  { _id: "COUNTER-1", value: 10 },
  { $set: { value: 20 } }
)
~~~

Client B đã đọc cùng snapshot và muốn đổi thành 30:

~~~javascript
const resultB = lab.counters.updateOne(
  { _id: "COUNTER-1", value: 10 },
  { $set: { value: 30 } }
)
~~~

Nếu A thực hiện trước, B không còn match `value:10`, trả `matchedCount:0`; nếu B đi trước, A không match. Một update thành công và một update bị từ chối theo điều kiện — **không phải exception**.

### 7.2. CAS bằng trường `version`

~~~javascript
const expectedVersion = 1

const result = lab.counters.updateOne(
  {
    _id: "COUNTER-1",
    version: expectedVersion
  },
  {
    $set: { value: 20 },
    $inc: { version: 1 }
  }
)

printjson(result)
~~~

Nếu thành công, document thành `value:20,version:2`. Client khác vẫn mang expectedVersion=1 không còn match. Đây là **optimistic concurrency control**: cho phép đọc song song, kiểm tra conflict tại thời điểm ghi.

### 7.3. Tại sao version phải tăng trong cùng update?

Không nên:

~~~javascript
// Sai: tách thành hai thao tác.
lab.counters.updateOne(
  { _id: "COUNTER-1", version: 1 },
  { $set: { value: 20 } }
)
lab.counters.updateOne(
  { _id: "COUNTER-1" },
  { $inc: { version: 1 } }
)
~~~

Giữa hai lệnh có thể có writer khác hoặc lệnh thứ hai lỗi. Khi cập nhật giá trị và tăng version **trong một write**, điều kiện version và trạng thái mới thuộc cùng ranh giới nguyên tử.

### 7.4. Xử lý `matchedCount:0`

Không retry vô hạn cùng expectedVersion cũ. Một quy trình:

1. Đọc lại document/version mới.
2. So sánh thay đổi mong muốn với trạng thái hiện tại.
3. Quyết định **merge**, **báo conflict cho người dùng**, hoặc tính lại update.
4. Gửi CAS mới có expectedVersion phù hợp.
5. Giới hạn số lần thử khi contention lớn.

Nếu endpoint chuyển order từ DRAFT sang CONFIRMED, CAS có thể dựa trên `status:"DRAFT"`. Nếu cần phát hiện **mọi thay đổi của document**, version mạnh hơn việc chỉ kiểm tra status, miễn mọi write path đều tăng version.

### 7.5. Lỗi ABA khi chỉ dùng giá trị trạng thái

Nếu field chuyển A → B → A giữa lúc client đọc và ghi, filter `state:"A"` có thể lại match dù document đã từng đổi. Với nghiệp vụ cần phát hiện **mọi thay đổi trung gian**, tăng `version` mỗi lần sửa giúp tránh lỗi **ABA**, miễn tất cả writer tuân thủ tăng version và không reset giá trị.

CAS **không** thay thế transaction khi bất biến nằm ở nhiều documents; update có version chỉ bảo vệ chính document đó.

## 8. Cập nhật array và trạng thái trong một document

Document `ORD-1` có `items` và `status`. Một nhân viên kho muốn đánh dấu line L1 đã lấy hàng và đưa order từ DRAFT sang `PICKING`. Nếu cả hai thay đổi nằm trong **một order document**, dùng một update nguyên tử:

~~~javascript
const lab = db.getSiblingDB("atomic_choice_lab")

const result = lab.orders.updateOne(
  {
    _id: "ORD-1",
    status: "DRAFT",
    items: {
      $elemMatch: {
        lineId: "L1",
        picked: false
      }
    }
  },
  {
    $set: {
      "items.$[line].picked": true,
      status: "PICKING",
      pickedStartedAt: ISODate("2026-11-14T09:00:00Z")
    },
    $inc: { version: 1 }
  },
  {
    arrayFilters: [
      {
        "line.lineId": "L1",
        "line.picked": false
      }
    ]
  }
)

printjson(result)
~~~

**Tất cả field thay đổi bên trong ORD-1** thuộc một update nguyên tử. `arrayFilters` chọn những phần tử có `lineId:"L1"` và `picked:false`. `$elemMatch` trong filter bảo đảm một line phù hợp tồn tại trước lúc ghi; `status:"DRAFT"` bảo vệ chuyển trạng thái.

### 8.1. Rủi ro dù chỉ có một document

- Nếu có **hai phần tử trùng lineId**, `$[line]` có thể cập nhật cả hai. Unique multikey index trên `items.lineId` **không tự cấm trùng lineId trong cùng một order**. Cần invariant của domain hoặc mô hình line items riêng.
- Nếu workflow cho phép pick line thứ hai khi order đã `PICKING`, dùng filter `status:"DRAFT"` cho mọi lần pick tiếp theo sẽ khiến nó không match. Điều kiện phải phản ánh **trạng thái hợp lệ** của transition thật.
- Nếu mọi line cần picked trước `READY_TO_SHIP`, cần xác định predicate bảo vệ transition và thực hiện trong một update, hoặc duy trì state tổng hợp nhất quán.
- Nếu line items nằm ở **documents khác**, cập nhật order không đảm bảo cùng commit với từng line document.

### 8.2. Atomic update không có nghĩa miễn phí khi document lớn

Sửa array lớn có thể tốn CPU/I/O và chi phí cập nhật multikey index. Nhiều writers cùng sửa các phần tử khác nhau vẫn đang ghi **cùng một order document**, có thể xảy ra contention. Ranh giới document cần chọn theo **kích thước, frequency và quyền sở hữu dữ liệu**, không chỉ vì atomicity.

## 9. Khi nào reference phù hợp hơn embedding?

Giả sử một đơn hàng có thể có **hàng trăm nghìn line items**, mỗi line được nhiều worker cập nhật độc lập, cần phân trang/tìm theo SKU và lưu audit riêng. Nhúng tất cả vào `orders.items` có thể làm document rất lớn, ảnh hưởng indexes và tạo hot document.

Một mô hình tham chiếu:

~~~javascript
// orders:
{
  _id: "ORD-2",
  customerId: "C-2",
  status: "DRAFT",
  total: 0
}

// orderLines:
{
  _id: "LINE-2001",
  orderId: "ORD-2",
  sku: "SKU-A",
  qty: 3,
  state: "OPEN"
}
~~~

Ưu điểm: mỗi line là một document, có thể index theo `orderId`/`sku`, tìm/ghi/phân trang độc lập, không phình document order. Nhược điểm: nếu invariant là “`orders.total` bằng tổng tiền **tất cả** lines” và phải đúng **ngay lập tức ở mọi thời điểm ghi**, một update vào line và một update vào order **không tự atomic chung**. Lúc này cần:

- **Transaction** nếu bất biến nhiều document phải commit cùng nhau; hoặc
- **Eventual consistency** với recalculation, version/checkpoint và cơ chế repair nếu nghiệp vụ cho phép, thay vì khẳng định total luôn đồng bộ tức thời.

### 9.1. Phân biệt source of truth và dữ liệu dẫn xuất

Nếu `orderLines` là nguồn dữ liệu đúng còn `orders.total` chỉ phục vụ hiển thị và có thể chậm vài giây, có thể dùng asynchronous projection. Nhưng một chức năng **thu tiền** không được dùng bản total chậm đó như thể nó là giá trị đã kiểm chứng, trừ khi có version/snapshot/transition đã được khóa bằng một cơ chế nhất quán thích hợp.

Khi quyết định, hãy hỏi: **Nếu summary trễ 3 giây, có gây mất tiền, bán vượt tồn hay vi phạm hợp đồng không?** Nếu có, thiết kế cần kiểm soát đồng bộ mạnh hơn hoặc thay đổi ranh giới aggregate.

### 9.2. Một document không đồng nghĩa một entity

Trong domain-driven design, **aggregate boundary** là nhóm dữ liệu phải bảo vệ invariant cùng nhau. Một MongoDB document có thể chứa **nhiều entity nhỏ/value objects**. Chọn một aggregate hợp lý thường khiến single-document atomic update đủ dùng.

Ngược lại, đừng gom **mọi entity có liên quan** vào một document. Cần phân biệt “cùng hiển thị trên màn hình” với “cùng phải commit trong một bất biến”. Một dashboard có thể cần join nhiều collection mà **không cần** mọi thứ nằm chung document.

## 10. Khi cần multi-document transaction

Nếu nghiệp vụ bắt buộc **nhiều document cùng thay đổi hoặc cùng không thay đổi**, single-document atomicity không đủ. Ví dụ chuyển 150 đơn vị tiền từ ACC-A sang ACC-B:

~~~text
Trước: ACC-A = 1000, ACC-B = 200; tổng = 1200.

Chuyển 150:
  ACC-A := 850
  ACC-B := 350

Yêu cầu:
  hoặc cả hai số dư thay đổi;
  hoặc không số dư nào thay đổi.
~~~

Nếu dùng hai câu `updateOne` độc lập:

~~~javascript
// Lệnh 1:
lab.accounts.updateOne(
  { _id: "ACC-A", balance: { $gte: 150 } },
  { $inc: { balance: -150 } }
)

// Lệnh 2:
lab.accounts.updateOne(
  { _id: "ACC-B" },
  { $inc: { balance: 150 } }
)
~~~

nếu lệnh thứ nhất thành công nhưng lệnh thứ hai lỗi/network timeout, hai tài khoản có thể lệch nhau. **Mỗi lệnh riêng là atomic**, nhưng không có atomicity chung qua **hai account documents**.

### 10.1. Dữ liệu chuẩn bị cho transaction

Fixture `accounts` đã có ACC-A và ACC-B. Tạo trước collection lưu transfer record:

~~~javascript
const lab = db.getSiblingDB("atomic_choice_lab")
lab.createCollection("transfers")
lab.transfers.createIndex(
  { transferId: 1 },
  { unique: true, name: "ux_transferId" }
)
~~~

Chỉ chạy `createCollection` một lần khi collection chưa tồn tại. Trong hệ thống thật, tạo collection/index **trước** thời điểm xử lý transaction thay vì để mỗi request tự tạo cấu trúc. Với mỗi lần chuyển tiền, dùng `transferId` **ổn định và duy nhất theo yêu cầu nghiệp vụ**, để nhận biết duplicate request.

### 10.2. Ví dụ transaction trong `mongosh`

Chạy trên **replica set/sharded cluster** hỗ trợ transactions:

~~~javascript
const session = db.getMongo().startSession()
const txdb = session.getDatabase("atomic_choice_lab")
const amount = 150
const transferId = "TR-1001"

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  // Ghi dấu operation ID trong cùng transaction.
  txdb.transfers.insertOne({
    _id: transferId,
    transferId,
    fromAccount: "ACC-A",
    toAccount: "ACC-B",
    amount,
    state: "POSTED"
  })

  const debit = txdb.accounts.updateOne(
    { _id: "ACC-A", currency: "VND", balance: { $gte: amount } },
    { $inc: { balance: -amount } }
  )
  if (debit.matchedCount !== 1) {
    throw new Error("Source account missing or insufficient funds")
  }

  const credit = txdb.accounts.updateOne(
    { _id: "ACC-B", currency: "VND" },
    { $inc: { balance: amount } }
  )
  if (credit.matchedCount !== 1) {
    throw new Error("Destination account not found")
  }

  session.commitTransaction()
  print("Transfer committed")
} catch (err) {
  print("Transaction did not finish normally: " + err.message)
  try {
    session.abortTransaction()
  } catch (_) {
    // Có thể transaction đã abort hoặc commit outcome cần phân loại.
  }
  throw err
} finally {
  session.endSession()
}
~~~

Nếu commit thành công trên fixture ban đầu: ACC-A còn **850**, ACC-B thành **350**, `transfers` có TR-1001. Nếu lỗi trước commit và transaction bị abort, **không** có thay đổi số dư hoặc transfer record từ transaction đó.

**Cực kỳ quan trọng:** Đây là ví dụ về **ranh giới transaction và kiểm tra business condition**, **không phải transaction retry/commit code chuẩn production**. Nếu `commitTransaction()` trả **`UnknownTransactionCommitResult`**, bạn **không được kết luận transaction đã rollback** hay gửi một transfer mới vô điều kiện. Phải dùng transaction API/driver retry đúng quy tắc và đối soát theo `transferId`. `abortTransaction()` trong catch minh họa giải phóng transaction khi chưa commit; riêng kết quả commit không rõ phải được xử lý như một nhánh đặc biệt.

### 10.3. Tại sao transferId nằm trong cùng transaction?

Nếu transfer record được lưu ngoài transaction, có thể xảy ra:

~~~text
Transfer record ghi thành công
     |
     v
Debit thất bại -> không có chuyển tiền
     |
     v
Ledger lại ghi là POSTED (sai)
~~~

Đặt transfer record **cùng transaction** cho phép nó commit/abort cùng debit/credit. Unique index trên transferId giúp chặn một transaction khác tạo **cùng ID** nếu business request bị gửi lại. Tuy nhiên, client nhận duplicate key cần đọc lại transfer record và xác nhận nội dung đúng — không coi mọi duplicate ID là “đã chuyển thành công” nếu amount/from/to khác.

Trong hệ thống tài chính thật còn cần **double-entry ledger**, reconciliation, audit, account freezes, currency precision, quyền, và tính nhất quán với ngân hàng/payment provider. Demo này chỉ minh họa MongoDB transaction; không phải hệ thống thanh toán sẵn sàng triển khai.

### 10.4. Transaction có cả read và write

Một transaction có thể đọc trạng thái liên quan, tính toán và ghi nhiều documents. Nhưng điều kiện nghiệp vụ quan trọng vẫn nên được biểu diễn bằng **filter ở thời điểm ghi**, đặc biệt khi có contention. Ví dụ debit filter `balance:{$gte:amount}` là một lớp bảo vệ trực tiếp trên account.

Đừng nghĩ cứ đặt `findOne` đọc số dư trong transaction rồi `updateOne({_id},{$set:balance - amount})` là mọi bài toán cạnh tranh tự được giải đúng. Transaction có write conflict/retry semantics, nhưng application vẫn phải kiểm tra invariant và phản hồi kết quả khi xung đột.

## 11. Không dùng `updateMany` hoặc `bulkWrite` thay transaction

Một số developer thấy nhiều operation trong một API rồi suy ra chúng cùng commit. Sai:

~~~javascript
lab.accounts.bulkWrite([
  {
    updateOne: {
      filter: { _id: "ACC-A" },
      update: { $inc: { balance: -150 } }
    }
  },
  {
    updateOne: {
      filter: { _id: "ACC-B" },
      update: { $inc: { balance: 150 } }
    }
  }
], { ordered: true })
~~~

`ordered: true` buộc thực hiện theo thứ tự nhưng **không rollback bước trước khi bước sau lỗi**. `ordered: false` cho phép unordered, càng không phù hợp nếu operation có dependency.

Tương tự:

~~~javascript
lab.accounts.updateMany(
  { _id: { $in: ["ACC-A", "ACC-B"] } },
  { $set: { reviewed: true } }
)
~~~

Mỗi account được sửa nguyên tử nhưng **hai account không cùng một atomic boundary**. Nếu `reviewed:true` chỉ là metadata và cho phép kết quả một phần rồi retry, không cần transaction. Nếu hai account có invariant bắt buộc cùng trạng thái, dùng transaction khi hợp lý.

### 11.1. Khi bulk chạy *trong* transaction

`bulkWrite()` có thể được gọi với **session đang nằm trong transaction** trong deployment/API hỗ trợ. Khi đó **transaction** (không phải bản thân bulk) cung cấp all-or-nothing cho các operations thuộc session. Cần bảo đảm mọi call dùng **đúng session**; một write quên truyền session sẽ chạy **ngoài transaction**.

Không đặt `writeConcern` riêng cho từng write trong transaction; read/write concern được đặt ở **transaction level** và commit theo API. Nếu một write bị lỗi, transaction cần được abort/retry theo quy tắc tương ứng, không kỳ vọng unordered bulk bỏ qua lỗi rồi commit trạng thái còn lại.

## 12. Read concern, write concern và transaction giải quyết những vấn đề khác nhau

Thường có ba câu hỏi:

1. **Atomicity:** nhiều thay đổi có cần cùng commit/abort không?
2. **Isolation/consistency của đọc:** transaction/reader thấy snapshot nào, một loạt thay đổi có thể bị trộn giữa các thời điểm không?
3. **Acknowledgment/durability:** write đã được xác nhận ở replica/majority, journaling và failover theo mức nào?

**Multi-document transaction** giúp bảo vệ ranh giới nhiều documents; **read concern** và **write concern** điều khiển những bảo đảm đọc/ghi theo cấu hình. Không nhầm việc đặt `writeConcern:{w:"majority"}` cho hai update độc lập với việc hai update đó trở thành một transaction.

### 12.1. Write concern không tạo atomicity toàn nhóm

~~~javascript
// Hai writes độc lập, dù ứng dụng yêu cầu majority cho từng lệnh.
lab.accounts.updateOne(
  { _id: "ACC-A" },
  { $inc: { balance: -50 } },
  { writeConcern: { w: "majority" } }
)

lab.accounts.updateOne(
  { _id: "ACC-B" },
  { $inc: { balance: 50 } },
  { writeConcern: { w: "majority" } }
)
~~~

Nếu lần ghi A được xác nhận majority rồi B thất bại, **A không tự rollback**. Majoritiy acknowledgment chỉ nói về mức xác nhận mỗi write, không có **all-or-nothing** cho hai lệnh độc lập. (Các options trong code áp dụng khi API và deployment hỗ trợ.)

### 12.2. Read concern trong transaction

Trong transaction, MongoDB hỗ trợ những mức read concern như `"local"`, `"majority"`, `"snapshot"` theo tài liệu. Khi cần đọc một snapshot nhất quán phục vụ nhiều bước của transaction, `"snapshot"` là lựa chọn thường gặp, phối hợp với write concern ở transaction/commit.

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})
~~~

Các bảo đảm cụ thể của `snapshot` và `majority` còn phụ thuộc topology, nơi chạy transaction và điều kiện commit. Không đặt read concern riêng cho từng operation trong transaction; transaction-level options điều khiển.

### 12.3. Một committed transaction có luôn hiển thị đồng thời ở mọi phép đọc?

Atomic commit không đồng nghĩa mọi kiểu **đọc không đồng bộ ngoài transaction** đều quan sát tất cả shards ở cùng một snapshot. Trên sharded cluster, một số mức read concern bên ngoài transaction có thể quan sát các writes đã commit ở những shard khác nhau tại các thời điểm khác nhau. Nếu report cần một snapshot nhất quán xuyên nhiều documents/shards, cần chọn **read concern phù hợp** (ví dụ `snapshot` khi được hỗ trợ) và thiết kế read path theo yêu cầu.

Đừng suy rằng “đã dùng transaction cho write thì một dãy `find()` bất kỳ sau đó luôn là snapshot đọc nhất quán”.

### 12.4. Write concern timeout khác transaction abort

Một lệnh hoặc commit có thể trả **write concern error/timeout** vì chưa đạt mức acknowledgment yêu cầu đúng thời hạn. Điều đó **không chứng minh** dữ liệu chưa được áp dụng. Với commit outcome không rõ, cần xử lý theo driver transaction API và transaction labels; không gửi lại nghiệp vụ với ID mới chỉ vì client không nhận được success.

## 13. Retryable writes, retry transaction và idempotency

Trong hệ thống phân tán, một request có thể:

~~~text
Application ----> MongoDB
     |              |
     |             WRITE applied
     |              |
     X <---- network disconnected before response
     |
     v
  Application does not know whether write succeeded.
~~~

Nếu ứng dụng gửi lại yêu cầu **với một ID mới** và không kiểm tra kết quả trước, nó có thể tạo duplicate document hoặc lặp số tiền/stock.

### 13.1. Phân biệt ba cơ chế

| Cơ chế | Tác dụng | Không bảo đảm |
|---|---|---|
| **Retryable writes** ở driver/server | Retry một số single-document writes được hỗ trợ khi có lỗi tạm thời theo session/statement. | Không biến mọi `updateMany`/`deleteMany` hay mọi business request thành exactly-once. |
| **Retry toàn transaction** | Chạy lại transaction sau lỗi nhất định như `TransientTransactionError`. | Không tự chống cùng một request được **khởi tạo lại** lần thứ hai. |
| **Retry commit** | Xử lý commit có outcome không rõ, theo nhãn `UnknownTransactionCommitResult`. | Không nên thay bằng “tạo một transaction mới và chuyển tiền lại”. |
| **Idempotency nghiệp vụ** | Gắn operation ID ổn định, chống ứng dụng xử lý cùng yêu cầu hai lần. | Không tự đảm bảo mọi thay đổi liên tài liệu atomic nếu không có transaction/workflow tương ứng. |

### 13.2. Những transaction error labels quan trọng

Theo tài liệu MongoDB:

- **`TransientTransactionError`:** lỗi tạm thời khiến transaction không hoàn tất; có thể cần **retry toàn transaction**.
- **`UnknownTransactionCommitResult`:** không biết commit đã thành công hay chưa; thường cần **retry commit** bằng chính transaction/session API thay vì replay toàn business flow.
- **`DuplicateKey`:** yêu cầu có thể vi phạm unique business identity, thường cần phân loại/xác minh chứ không retry mù.
- **`TransactionTooLargeForCache`** hoặc lỗi tài nguyên: transaction quá lớn/hot, thường cần **thiết kế nhỏ lại** thay vì gửi lại vô hạn.

Driver có các **convenient transaction APIs** xử lý một số nhãn lỗi/retry tự động. Tuy nhiên callback transaction có thể được gọi lại, nên không đặt **email, charge payment gateway, phát event bên ngoài** một cách không idempotent bên trong callback đó.

### 13.3. Những thao tác không idempotent

| Write | Replay cùng yêu cầu sau khi đã success có thể gây tác động thêm? |
|---|---|
| `$set:{status:"PAID"}` trên đúng ID | Thường không làm đổi trạng thái tiếp, nhưng phải xét transition hợp lệ. |
| `$inc:{balance:-100}` | **Có**: có thể debit lần hai. |
| `$push:{events:event}` | **Có**: thêm event lặp nếu không có điều kiện. |
| `insertOne` với cùng `_id` | Lần sau duplicate key; cần đối soát xem đã làm đúng request. |
| `updateOne` với `version` kỳ vọng | Replay sau version tăng sẽ không match; cần phân biệt conflict với success trước đó. |
| `deleteMany` filter rộng | Replay sau có thể xóa thêm documents mới thỏa filter. |
| Transaction transfer với transferId unique trong cùng transaction | Có thể phát hiện cùng transfer đã tồn tại; cần verify nội dung để phân loại. |

### 13.4. Idempotency key phải ổn định theo nghiệp vụ

Ví dụ một API:

~~~text
POST /transfers
Idempotency-Key: t-abc-123
Body: {from:"ACC-A",to:"ACC-B",amount:150}
~~~

Server cần bảo đảm:

1. **Cùng idempotency key + cùng payload** chỉ tạo một nghiệp vụ logic.
2. **Cùng idempotency key + payload khác** bị từ chối như conflict.
3. Nếu request trước chưa rõ kết quả, server có thể tra trạng thái bền vững theo key và reconcile.
4. Nếu thao tác nhiều documents cần all-or-nothing, ghi dấu key và thực hiện các thay đổi **trong cùng transaction** hoặc workflow nhất quán khác.
5. Key có retention/TTL theo policy; xóa idempotency record quá sớm có thể làm request cũ bị xử lý lại.

`retryWrites=true` ở connection string giúp những retry kỹ thuật được hỗ trợ, nhưng **không thay thế** các quy tắc trên cho API level.

### 13.5. Tại sao không nên retry mọi transaction bất kỳ?

Nếu transaction thất bại do **insufficient funds**, một lần retry nguyên xi không giúp. Nếu do duplicate transferId, gửi lại nhiều lần chỉ báo duplicate. Nếu do short-lived write conflict, một số retry có **bounded exponential backoff/jitter** có thể phù hợp. Phân loại lỗi và giới hạn số lần retry là bắt buộc để không tạo áp lực thừa lên cluster.

## 14. Transaction không bao trùm email, thanh toán hoặc message broker

Một business workflow có thể yêu cầu:

~~~text
1. Đơn hàng đổi từ CONFIRMED sang PAID.
2. Lưu payment event.
3. Gửi email xác nhận.
4. Phát message sang kho vận.
~~~

MongoDB transaction có thể bao trùm những writes **bên trong MongoDB**, nhưng **không tự commit/rollback** lời gọi SMTP, payment provider hay Kafka/RabbitMQ ở cùng một transaction. Một email đã gửi **không được thu hồi** chỉ vì MongoDB transaction sau đó abort.

### 14.1. Sai: gọi dịch vụ bên ngoài giữa transaction rồi hy vọng rollback

~~~text
Start MongoDB transaction
    |
    +-- Update order (uncommitted)
    +-- Call payment gateway -> charged successfully
    +-- Insert payment record -> validation error
    |
Abort MongoDB transaction
    |
    +-- Order rollback, gateway vẫn đã charge!
~~~

Đây là một **distributed workflow** chứ không chỉ là vấn đề MongoDB atomicity. Kể cả transaction retry callback, nếu gọi payment gateway trong callback, một retry có thể charge **lần thứ hai**.

### 14.2. Transactional outbox

Một mẫu thường dùng:

~~~text
MongoDB transaction:
  - Update order -> PAID
  - Insert outbox event: {eventId, orderId, type:"ORDER_PAID"}
Commit
       |
       v
Outbox dispatcher đọc event chưa phát
       |
       v
Publish message tới broker / gửi email
       |
       v
Đánh dấu dispatched (có thể retry)
~~~

**Outbox record** được commit trong MongoDB cùng order, nên không có trạng thái order PAID mà **thiếu ý định phát event** nếu transaction thành công. Phần giao tiếp ngoài MongoDB có thể thực hiện **at-least-once**: dispatcher có thể phát hai lần nếu phát thành công nhưng chết trước khi đánh dấu. Vì vậy consumer phải **idempotent theo eventId**, không coi outbox tự đảm bảo exactly-once across systems.

### 14.3. Saga/compensation

Nếu các bước trải qua nhiều service độc lập, cần cân nhắc **saga**:

~~~text
Reserve stock
    |
    +--> Charge payment
             |
             +--> Arrange shipment

If payment fails:
  release reservation (compensating action)

If shipment fails:
  compensate according to business rules
~~~

Compensation **không phải rollback vật lý đồng thời**: có thể có trạng thái trung gian, cần audit, retry, idempotency và xử lý lỗi của chính compensating action. Sử dụng saga khi nghiệp vụ chấp nhận eventual consistency và có hành động bù trừ hợp lệ. Với hai updates MongoDB đơn giản phải cùng commit, transaction thường dễ hiểu hơn saga thủ công.

### 14.4. Không có một lựa chọn duy nhất cho mọi bước

Một hệ thống thực tế có thể kết hợp:

- **Embedded order** để một status transition + timestamp + snapshot địa chỉ luôn atomic.
- **Một conditional update cho từng SKU** để giữ tồn kho không âm.
- **Transaction giữa order và inventory reservations** nếu invariants yêu cầu đồng thời nhiều documents.
- **Outbox** để phát sự kiện sau commit mà không mất ý định phát.
- **Saga** để phối hợp payment gateway, kho vận và hoàn tiền.

Thiết kế tốt đặt **ranh giới đồng bộ mạnh** ở nơi thật sự cần, chứ không bắt mọi bước liên hệ xa cùng nằm trong một transaction lớn.

## 15. Chi phí transaction và quyết định vận hành

Multi-document transactions có giá trị khi cần ACID qua nhiều documents, nhưng chi phí thường lớn hơn single-document writes. Một transaction giữ trạng thái session/snapshot, có thể chiếm lock/tài nguyên WiredTiger cache và tăng khả năng write conflict khi nhiều client cùng thay đổi dữ liệu.

### 15.1. Các giới hạn cần biết

Theo tài liệu **Production Considerations** của MongoDB:

- MongoDB có tham số **`transactionLifetimeLimitSeconds`**, mặc định thường **60 giây**, dùng giới hạn tuổi thọ transaction. Deployment/version có thể cấu hình khác; không thiết kế một job dựa vào giả định transaction chạy vô thời hạn.
- Transaction lâu/có nhiều thay đổi làm tăng áp lực **WiredTiger cache**, có thể abort do write conflict hoặc lỗi như `TransactionTooLargeForCache`.
- Transaction cần lấy locks theo quy tắc và timeout của deployment, có thể abort nếu không lấy lock kịp.
- Những tác vụ tạo collection/index, thay đổi metadata, resharding, DDL và topology có các giới hạn riêng khi chạy cùng transaction.
- Transaction trên sharded cluster có chi phí điều phối và failure modes phức tạp hơn một write đơn lẻ.

Không nên diễn giải “MongoDB có transaction” là có thể mở transaction đầu job import một triệu records rồi commit khi xong. Một job lớn thường nên chia thành **những đơn vị nghiệp vụ nhỏ**, mỗi đơn vị có checkpoint/idempotency và transaction riêng **nếu cần**.

### 15.2. Hot document vs contention nhiều documents

Embedding nhiều trạng thái vào một document giúp update nguyên tử, nhưng cũng tập trung writes:

~~~text
Document ORDER-1
  Worker A -> sửa item L1
  Worker B -> sửa item L2
  Worker C -> cập nhật status
  Worker D -> append event
~~~

Đây là bốn writers cùng tác động một document; dù mỗi update có thể nguyên tử, workload có thể **contention** và thậm chí lost update nếu dùng `$set` bản sao cũ.

Tách line items thành nhiều documents giảm hot spot, nhưng nếu muốn cập nhật summary order đồng thời mọi line, sẽ cần transaction hoặc eventual consistency. Không có một chiến lược luôn tối ưu; hãy đo **write frequency, contention, read pattern và invariant boundary**.

### 15.3. Đặc biệt với các mảng không giới hạn

Nếu một account lưu mọi transaction history trong array nhúng:

~~~javascript
{
  _id: "ACC-A",
  balance: 1000,
  entries: [ /* tăng mãi theo thời gian */ ]
}
~~~

thì dù mỗi `$push` cùng `$inc` có thể atomic, document vẫn phình to, dễ nóng, khó query/paginate và chạm 16 MiB. Đối với ledger thực, thường lưu **entries thành records riêng**; nếu cần bảo vệ balance và entry cùng commit, transaction có thể cần thiết. Trong một số thiết kế, ledger là source of truth và balance là summary dẫn xuất được reconcile theo version/checkpoint.

### 15.4. Đo thay vì suy đoán

Các số liệu nên quan sát:

| Thước đo | Biểu hiện cần chú ý |
|---|---|
| P50/P95/P99 write latency | Update document lớn hoặc transaction có chậm bất thường? |
| Write conflicts/retries | Có nhiều clients tranh nhau cùng document? |
| Transaction abort rate | Có nhiều transaction thất bại do contention/timeouts? |
| Transaction duration | Có giữ snapshot/locks quá lâu? |
| WiredTiger cache pressure | Có tràn cache hay history pressure không? |
| Replication lag/write concern latency | Mức xác nhận ghi gây độ trễ cao không? |
| BSON document size | Mảng embedded có tiến gần 16 MiB không? |
| Index size/write overhead | Index trên mảng/field có làm cập nhật đắt thêm? |
| Outbox lag/reconciliation count | Eventual workflow có đang tụt hậu hoặc bỏ sót? |

Một test 10 document không đủ để quyết định schema production. Nên thử trên **dữ liệu đại diện**, nhiều writers đồng thời, và kiểm chứng bất biến sau lỗi/timeout/stepdown.

### 15.5. Tối ưu ranh giới transaction

Một transaction hiệu quả thường:

1. Chỉ gồm **những writes phải commit cùng nhau**.
2. Không chứa network calls tới service ngoài.
3. Không duy trì thời gian chờ user hoặc thao tác UI.
4. Tránh đọc/quét lớn khi không cần.
5. Có indexes cho filters quan trọng (tài khoản, transferId, orderId).
6. Dùng **bounded retry** theo error labels và API driver.
7. Có **operation ID** để phát hiện business request lặp.
8. Có logging/monitoring mà không tiết lộ dữ liệu nhạy cảm.

### 15.6. Khi có nhiều documents nhưng không cần transaction

Không phải mọi multi-document write cần ACID. Ví dụ job đánh dấu 50.000 bài viết đã được index lại:

~~~javascript
lab.articles.updateMany(
  { reindexVersion: { $lt: 42 } },
  { $set: { reindexVersion: 42 } }
)
~~~

Mỗi document cập nhật riêng, có thể retry/reconcile. Nếu trạng thái “một số bài đã reindex, một số chưa” được phép, transaction không cần thiết và có thể rất tốn. Nếu dữ liệu **không được phép** lộ trạng thái mixed-version, có thể dùng **versioned dataset/pointer switch** hoặc workflow rollout thay vì ép mọi document vào một transaction khổng lồ.

## 16. MongoDB Java Sync Driver: single-document update và transaction

Trong Java, việc chọn **mô hình dữ liệu** vẫn quan trọng hơn builder API. Java Driver cung cấp `MongoCollection.updateOne()`, `findOneAndUpdate()`, `ClientSession` và `withTransaction()`.

### 16.1. Update tồn kho có điều kiện

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;

// Giả sử database đã kết nối tới atomic_choice_lab.
MongoCollection<Document> stock = database.getCollection("stock");

int quantity = 3;
UpdateResult result = stock.updateOne(
    and(
        eq("_id", "SKU-A"),
        gte("available", quantity)
    ),
    combine(
        inc("available", -quantity),
        inc("reserved", quantity)
    )
);

if (result.getMatchedCount() == 1) {
    System.out.println("Reservation accepted");
} else {
    System.out.println("Not enough stock or SKU not found");
}
~~~

`UpdateResult.getMatchedCount()` xác nhận document có khớp filter tại lúc ghi. Code không tách một `findOne` trước rồi `$set` bằng giá trị client tính từ state cũ.

### 16.2. CAS bằng version trong Java

~~~java
import static com.mongodb.client.model.Updates.set;

long expectedVersion = 1L;

UpdateResult casResult = database.getCollection("counters").updateOne(
    and(
        eq("_id", "COUNTER-1"),
        eq("version", expectedVersion)
    ),
    combine(
        set("value", 20),
        inc("version", 1)
    )
);

if (casResult.getMatchedCount() == 0) {
    // Caller quyết định read-retry, merge hoặc trả 409 Conflict.
    System.out.println("Concurrent modification detected");
}
~~~

Trong fixture, field `version` ban đầu là số nguyên BSON phù hợp với `eq("version",1L)` theo numeric comparison semantics của MongoDB; trong dự án thật nên chuẩn hóa loại BSON/Java của field và test codec để không gặp lỗi kiểu hoặc precision. Mỗi write path phải tăng version, nếu không optimistic locking mất ý nghĩa.

### 16.3. Transaction nhiều tài liệu với `withTransaction()`

Java Sync Driver có **convenient transaction API** giúp xử lý một số retry/commit cases theo labels mà không phải tự viết toàn bộ vòng lặp transaction:

~~~java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import com.mongodb.TransactionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.inc;

// client: MongoClient đã kết nối tới replica set/sharded deployment.
MongoDatabase database = client.getDatabase("atomic_choice_lab");
MongoCollection<Document> accounts = database.getCollection("accounts");
MongoCollection<Document> transfers = database.getCollection("transfers");

TransactionOptions txOptions = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .build();

String transferId = "TR-JAVA-1001";
long amount = 150L;

try (ClientSession session = client.startSession()) {
    String committedId = session.withTransaction(() -> {
        transfers.insertOne(
            session,
            new Document("_id", transferId)
                .append("transferId", transferId)
                .append("fromAccount", "ACC-A")
                .append("toAccount", "ACC-B")
                .append("amount", amount)
                .append("state", "POSTED")
        );

        UpdateResult debit = accounts.updateOne(
            session,
            and(
                eq("_id", "ACC-A"),
                eq("currency", "VND"),
                gte("balance", amount)
            ),
            inc("balance", -amount)
        );
        if (debit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                "Account missing or insufficient balance"
            );
        }

        UpdateResult credit = accounts.updateOne(
            session,
            and(eq("_id", "ACC-B"), eq("currency", "VND")),
            inc("balance", amount)
        );
        if (credit.getMatchedCount() != 1) {
            throw new IllegalStateException("Destination account missing");
        }

        return transferId;
    }, txOptions);

    System.out.println("Committed transfer: " + committedId);
}
~~~

Các điểm phải nhớ:

- Mọi thao tác thuộc transaction phải truyền **cùng `ClientSession`**, ví dụ `transfers.insertOne(session, ...)` và `accounts.updateOne(session, ...)`.
- Tạo collection/index trước khi vào transaction trong môi trường demo.
- `withTransaction` có thể chạy lại callback trong một số trường hợp lỗi tạm thời. Không gọi payment gateway hoặc gửi email không idempotent **trong callback**.
- Nếu business request được gửi lại như một **API call mới**, transaction vẫn có thể chạy lại; unique transferId giúp nhận biết trùng nhưng phải **reconcile payload/trạng thái**.
- Với `IllegalStateException` do business rule, callback bị lỗi và transaction không commit; nó không phải transient database error nên retry vô hạn sẽ không giải quyết.
- Chi tiết transaction retry và exceptions phụ thuộc **Java Driver version**. Code là mẫu cấu trúc cần tích hợp với logging, authorization, checkpoint, nghiệp vụ và deployment thực.

### 16.4. Không chạy các operations song song trên cùng session

Trong transaction, hãy thực hiện các thao tác **tuần tự theo API driver** thay vì tự khởi tạo nhiều thread/async operations dùng chung một `ClientSession` mà mong chúng chạy an toàn song song. Transaction session có quy tắc sử dụng riêng; nhiều drivers không hỗ trợ parallel operations trong một transaction.

### 16.5. Kết hợp transaction với outbox trong Java

Thay vì gửi email ngay trong callback, thêm một write:

~~~java
MongoCollection<Document> outbox = database.getCollection("outbox");

// Trong callback withTransaction, cùng session:
outbox.insertOne(
    session,
    new Document("_id", "EV-TR-JAVA-1001")
        .append("eventType", "TRANSFER_POSTED")
        .append("transferId", transferId)
        .append("createdAt", new java.util.Date())
);
~~~

Sau commit, một dispatcher riêng gửi event và ghi nhận trạng thái phát. Nếu event bị phát lặp do retry, consumer dùng `eventId` để chống xử lý hai lần. Outbox giúp bảo vệ **ý định phát event** trong MongoDB, không tự tạo atomicity giữa MongoDB và broker.

## 17. Những tình huống lựa chọn thiết kế

### 17.1. Bài toán A — Cập nhật trạng thái và thời gian của order

**Yêu cầu:** Chỉ cho phép order ở trạng thái DRAFT chuyển sang CONFIRMED, ghi thời gian xác nhận trong cùng bước.

**Giải pháp:** Hai field trong cùng document, dùng **một conditional update**:

~~~javascript
const lab = db.getSiblingDB("atomic_choice_lab")

lab.orders.updateOne(
  {
    _id: "ORD-1",
    status: "DRAFT"
  },
  {
    $set: {
      status: "CONFIRMED",
      confirmedAt: ISODate("2026-11-14T10:00:00Z")
    },
    $inc: { version: 1 }
  }
)
~~~

**Không cần transaction nhiều document.** Nếu hai clients cùng xác nhận, một client có thể chuyển trạng thái, client còn lại match 0. Nếu workflow phải chống lặp ở cấp request cần operation ID/version hoặc logic trả kết quả hiện có.

### 17.2. Bài toán B — Giữ hàng cho một SKU

**Yêu cầu:** Không cho `available` âm khi nhiều orders đặt cùng SKU, giữ lại số lượng trong `reserved`.

**Giải pháp:** Một stock document cho SKU, `updateOne` filter `available >= quantity`, `$inc available:-quantity` và `$inc reserved:+quantity`. Nếu phải ghi một reservation record khác **cùng thời điểm**, cần xác định record đó có thể eventual hay phải cùng commit:

- **Không bắt buộc đồng bộ tức thì:** conditional update + outbox/repair/ledger theo workflow idempotent.
- **Bắt buộc cùng commit:** transaction giữa stock và reservation document.

### 17.3. Bài toán C — Đặt hai SKU theo nguyên tắc “đủ cả hai hoặc không lấy gì”

**Yêu cầu:** Một order cần SKU-A và SKU-B. Nếu bất kỳ SKU nào thiếu, không được giữ SKU còn lại.

Hai stock documents:

~~~text
SKU-A: available=5
SKU-B: available=10
Request: reserve SKU-A 3, SKU-B 4
~~~

Hai conditional updates độc lập **đều atomic riêng** nhưng có thể xảy ra:

~~~text
Reserve SKU-A thành công
Reserve SKU-B không match (hết hàng hoặc document không còn)
=> SKU-A vẫn bị giữ dù order không đủ cả hai.
~~~

Nếu bất biến **all-or-nothing ngay lập tức**, dùng **transaction** cho cả hai updates, kiểm tra `matchedCount` từng lệnh, abort nếu một lệnh không match. Nếu business cho phép giữ tạm từng SKU rồi giải phóng khi SKU khác thiếu, có thể dùng **reservation saga** với compensation, expiration và idempotency.

### 17.4. Bài toán D — Chuyển tiền giữa hai tài khoản

**Yêu cầu:** Debit một account và credit account khác, cùng một transfer record phải commit cùng nhau.

**Giải pháp điển hình:** Hai account documents và transfer record trong **transaction**, dùng business transferId unique, kiểm tra điều kiện balance/currency ở lúc ghi, xử lý commit outcome không rõ. Không nhúng tất cả user accounts vào một document toàn hệ thống chỉ để tránh transaction: document sẽ quá lớn, hot và có vòng đời độc lập.

### 17.5. Bài toán E — Ghi 100.000 log events

**Yêu cầu:** Mỗi log entry độc lập, cho phép eventual ingestion, có thể checkpoint.

**Giải pháp:** Documents riêng, `insertMany`/`bulkWrite` chia batches, unique event ID nếu cần dedupe và retry có kiểm soát. **Không** nhúng toàn bộ log vào một document dài vô hạn. **Không** mở một transaction khổng lồ cho 100.000 events nếu không có một invariant thực sự yêu cầu all-or-nothing.

### 17.6. Bài toán F — Order PAID và gửi email

**Yêu cầu:** Khi order PAID, phải có ý định gửi email xác nhận, nhưng email service có thể thất bại.

**Giải pháp:** Nếu cần bảo đảm không mất event, commit order transition và outbox record **trong MongoDB** (một document nếu cùng aggregate và thiết kế phù hợp, hoặc transaction nhiều documents). Dispatcher gửi email sau commit, retry idempotent. Không gọi SMTP trong transaction rồi hy vọng rollback email.

### 17.7. Bài toán G — Cập nhật nhiều documents nhưng cho phép trạng thái trung gian

**Yêu cầu:** Đánh dấu hàng triệu reports đã được migrate sang schema version 3; job có thể tạm dừng và tiếp tục.

**Giải pháp:** Batches có checkpoint, `updateMany`/`bulkWrite` với filter theo version, idempotent update và reconcile; không cần một transaction toàn bộ. Khi version 3 chưa đủ dùng ở downstream, app có thể **đọc theo version hoặc feature flag** tới khi migration hoàn tất.

### 17.8. Bài toán H — Cùng một khách có nhiều địa chỉ giao hàng

Nếu mỗi user có tối đa một số lượng địa chỉ nhỏ, thường xem cùng profile và đổi trong một thao tác, nhúng `addresses` vào user document có thể hợp lý. Nếu địa chỉ có quyền/vòng đời riêng, được chia sẻ bởi nhiều entities hoặc số lượng không giới hạn, reference có thể phù hợp hơn. **Không chọn embedding chỉ dựa trên việc “MongoDB hỗ trợ array”**; phải xét access patterns.

### 17.9. Tóm tắt theo tình huống

| Nghiệp vụ | Ranh giới dữ liệu | Lựa chọn ưu tiên | Lý do |
|---|---|---|---|
| Giảm available và thêm checkout active của cùng book | Một book document | Embedding + conditional update | Hai thay đổi atomic cùng nhau. |
| Đổi status và timestamp của order | Một order document | CAS theo status/version | Chống transition xung đột. |
| Đánh dấu một line item trong order nhỏ | Một order document | `$[line]` + một update | Không cần nhiều document transaction. |
| Đặt giữ một SKU | Một stock document | `$inc` có filter available | Chống overselling trên SKU. |
| Đặt giữ hai SKU phải cùng thành công | Hai stock documents | Transaction hoặc saga có compensation | Tùy invariant tức thì hay eventual. |
| Chuyển tiền từ A sang B | Hai accounts + transfer record | Transaction + unique transferId | All-or-nothing và chống request lặp. |
| Lưu toàn bộ audit log dài hạn | Nhiều log documents | Reference + batch/idempotency | Không tạo unbounded array. |
| Gửi email sau order PAID | MongoDB + SMTP | Outbox, dispatcher, dedupe | Transaction không bao trùm SMTP. |
| Migration độc lập theo document | Nhiều documents | Batches + checkpoint | Chấp nhận partial progress; tránh transaction lớn. |
| Nhiều child entities cập nhật độc lập | Nhiều documents | Reference; transaction chỉ nếu cần | Giảm hot document và hỗ trợ truy vấn riêng. |

## 18. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “MongoDB là document DB nên không có transaction.” | MongoDB hỗ trợ multi-document ACID transactions trên deployment thích hợp. |
| “Có transaction rồi thì không cần thiết kế schema.” | Embedded data và single-document atomicity vẫn thường là cách đơn giản/hiệu quả hơn. |
| “Nhúng mọi thứ vào một document là an toàn nhất.” | Có rủi ro 16 MiB, hot document, unbounded arrays và vòng đời độc lập. |
| “Atomicity của một update đảm bảo không có lost update.” | Hai `$set` theo `_id` có thể ghi đè nhau; cần CAS/`$inc`/conditional update. |
| “`$inc` tự ngăn overselling.” | Cần filter `available >= quantity` trong cùng update. |
| “`$inc` atomic thì gửi lại request bao nhiêu lần cũng được.” | `$inc` không idempotent ở cấp business request. |
| “Kiểm tra số lượng bằng `findOne` trước update là đủ.” | Race giữa đọc và ghi; điều kiện cần nằm ở filter của write. |
| “`matchedCount:0` nghĩa là MongoDB gặp lỗi.” | Thường chỉ là không có document khớp; có thể là business rejection/conflict. |
| “CAS theo status luôn phát hiện mọi sửa đổi.” | Có thể có ABA hoặc field khác đổi nhưng status giữ nguyên; dùng version nếu cần. |
| “Gọi hai updateOne liên tiếp là một transaction.” | Không; có thể thành công một phần. |
| “`ordered:true` trong bulkWrite sẽ rollback khi lỗi.” | Không; ordered chỉ điều khiển thứ tự và dừng. |
| “`updateMany` nguyên tử toàn collection.” | Mỗi document atomic, toàn operation không atomic chung. |
| “Transaction chắc chắn giải quyết mọi request replay.” | Một transaction nghiệp vụ **mới** có thể chạy cùng thao tác lần hai; cần idempotency ID. |
| “`writeConcern:majority` thay thế transaction.” | Majority là acknowledgment/durability, không tạo all-or-nothing nhiều documents. |
| “Commit timeout nghĩa là transaction đã abort.” | Outcome có thể chưa rõ; xử lý `UnknownTransactionCommitResult` đúng API. |
| “Chỉ cần retry lại toàn bộ business flow khi thấy timeout.” | Có thể double debit/charge, nhất là khi commit trước đã thành công. |
| “Trong transaction có thể tự gọi dịch vụ payment rồi rollback được.” | External side effects không thuộc MongoDB transaction. |
| “Outbox đảm bảo exactly-once tới mọi consumer.” | Dispatch có thể at-least-once, consumer phải dedupe bằng eventId. |
| “Saga tương đương rollback nguyên tử.” | Compensation là bước nghiệp vụ riêng, có trạng thái trung gian và có thể lỗi. |
| “Transaction lớn hơn luôn tốt vì commit một lần.” | Transaction dài/lớn tăng cache, lock, conflict và nguy cơ abort. |
| “Một document chỉ nên chứa đúng một entity nhỏ.” | Document có thể chứa aggregate gồm nhiều embedded value objects nếu cùng invariant. |
| “Một dashboard đọc nhiều collection thì phải dùng transaction.” | Chỉ cần transaction/snapshot mạnh khi **yêu cầu consistency thực sự đòi hỏi**; nhiều báo cáo cho phép eventual/stale. |

### 18.1. Câu hỏi kiểm tra trong code review

Khi review một đoạn ghi MongoDB, hãy hỏi:

1. **Ranh giới bất biến là document nào hoặc tập documents nào?**
2. **Tại sao cần embedding?** Có giới hạn số phần tử và vòng đời chung không?
3. **Có điều kiện kiểm tra tại thời điểm ghi?** Ví dụ status, available, version, eventId.
4. **Có thể có hai concurrent writers không?** Nếu có, câu update nào thắng/thua và cách app xử lý matchedCount=0?
5. **Nếu request timeout sau khi ghi, retry ra sao?** ID nghiệp vụ có ổn định không?
6. **Có external side effects không?** Outbox/saga có cần thiết?
7. **Nếu dùng transaction, tất cả DB operations dùng cùng session chứ?**
8. **Nếu transaction conflict/commit outcome unknown, retry/catch đã đúng chưa?**
9. **Transaction có nhỏ và bounded không?** Có indexes phục vụ filter không?
10. **Nếu tách dữ liệu thành nhiều docs, hệ thống có chấp nhận eventual consistency không?**

## 19. Bài tập thực hành có đáp án

Mỗi bài tập độc lập, giả định dữ liệu đầu vào theo đề. Nếu chạy trên `atomic_choice_lab` sau những ví dụ update ở các phần trước, hãy tạo collection lab riêng hoặc khôi phục fixture có chủ đích; các giá trị đã bị cập nhật có thể khác ví dụ.

### Bài 1 — Chọn mô hình cho một book checkout

Một thư viện chỉ lưu tối đa **5 lượt mượn đang hoạt động** trong mỗi book document. Khi mượn, phải đồng thời giảm `available` và thêm checkout active. Có cần transaction hai documents?

**Đáp án:** Có thể nhúng hai field trong một book document và dùng **một `updateOne`** atomic với filter `available:{$gt:0}`, `$inc available:-1` và `$push checkout`. Không cần multi-document transaction chỉ cho hai field đó. Lịch sử mượn dài hạn có thể lưu riêng bằng một workflow được xác định.

### Bài 2 — Hai client sửa counter từ cùng snapshot

Counter ban đầu 10. Client A đọc 10 muốn thêm 5, Client B đọc 10 muốn thêm 3. Cả hai `$set` counter bằng 15 và 13. Counter cuối có chắc bằng 18 không?

**Đáp án:** Không. Một update có thể ghi đè update kia, kết quả cuối là 13 hoặc 15, tùy thứ tự. Dùng:

~~~javascript
// Client A
db.counters.updateOne(
  { _id: "COUNTER-1" },
  { $inc: { value: 5 } }
)

// Client B
db.counters.updateOne(
  { _id: "COUNTER-1" },
  { $inc: { value: 3 } }
)
~~~

Khi cả hai thành công đúng một lần, giá trị cuối là **18**. Nếu business request bị replay, vẫn cần idempotency.

### Bài 3 — Chống tồn kho âm

`SKU-A` có `available:4`, hai clients cùng đặt giữ 3 sản phẩm. Viết update sao cho không làm available âm.

**Đáp án:**

~~~javascript
db.stock.updateOne(
  { _id: "SKU-A", available: { $gte: 3 } },
  {
    $inc: {
      available: -3,
      reserved: 3
    }
  }
)
~~~

Nếu chỉ có 4 sản phẩm, **tối đa một request** có thể giảm 3; request còn lại không match khi available còn 1.

### Bài 4 — `matchedCount:0` mang ý nghĩa gì?

Một `updateOne({_id:"SKU-A",available:{$gte:5}},...)` trả `matchedCount:0`. Có nghĩa server hỏng không?

**Đáp án:** Không nhất thiết. Có thể SKU-A không tồn tại hoặc available nhỏ hơn 5. Đây là **không thỏa filter**, thường là business rejection. Nếu phải phân biệt chính xác, ứng dụng có thể đọc lại hoặc kiểm tra trạng thái phù hợp, nhưng không bỏ điều kiện an toàn khỏi update.

### Bài 5 — Chống checkout lặp khi request timeout

Một client mượn sách với `checkoutId:"CH-1"` rồi timeout. Nếu retry với `$inc:-1` và `$push checkout` y nguyên, có nguy cơ gì?

**Đáp án:** Nếu lần trước đã ghi, một retry nghiệp vụ mới có thể giảm available và push checkout lần nữa. Thêm filter `"checkout.checkoutId":{$ne:"CH-1"}` trong cùng update, giữ ID ổn định, rồi đối soát khi matchedCount=0. Với lịch sử dài, cân nhắc unique ledger/transaction thay vì mảng nhúng không giới hạn.

### Bài 6 — CAS bằng version

Document:

~~~javascript
{ _id: "P-1", title: "Bản cũ", version: 7 }
~~~

Hai người dùng cùng đọc version 7 rồi sửa title. Viết một update bảo vệ xung đột.

**Đáp án:**

~~~javascript
db.posts.updateOne(
  { _id: "P-1", version: 7 },
  {
    $set: { title: "Bản mới của người A" },
    $inc: { version: 1 }
  }
)
~~~

Nếu A thành công, version lên 8. Request B vẫn filter version 7 sẽ không match; ứng dụng có thể báo conflict và đề nghị merge.

### Bài 7 — Một order chứa nhiều line items

Đơn ORD-1 có hai line L1/L2 nhúng trong `items`. Một thao tác cần đặt `items[L1].picked = true` và `order.status = PICKING`. Cần transaction không?

**Đáp án:** Không cần multi-document transaction nếu mọi field nằm **trong cùng ORD-1** và có một `updateOne` với `arrayFilters` cùng filter trạng thái phù hợp. Nếu line items là các documents riêng và phải cùng commit với order, cần xem transaction/bất biến.

### Bài 8 — Embedding không giới hạn

Hệ thống lưu tất cả comments từ khi tạo bài viết tới nhiều năm sau vào `posts.comments`. Một bài viết có thể nhận hàng triệu comments. Dù `$push` atomic, có nên dùng một document không?

**Đáp án:** Thường **không**. Mảng không giới hạn làm document phình to, nguy cơ chạm 16 MiB và contention; comments nên là documents riêng hoặc dùng subset/bucket có giới hạn tùy access pattern. Atomicity của một document không khắc phục vấn đề kích thước và vòng đời.

### Bài 9 — Transfer A → B không dùng transaction

ACC-A balance=1000, ACC-B balance=200. Lệnh debit 150 thành công, lệnh credit 150 lỗi. Hai `updateOne` riêng đã atomic, hệ thống có giữ tổng 1200 không?

**Đáp án:** Không. Trạng thái có thể là A=850, B=200, tổng=1050. Cần **transaction** nếu debit/credit phải cùng commit, hoặc workflow compensation được chấp nhận nếu domain cho phép trạng thái trung gian.

### Bài 10 — Hai SKU cùng phải đặt giữ

Một order cần SKU-A và SKU-B; chỉ ship nếu **cả hai được giữ hàng**. Nếu update SKU-A thành công, SKU-B không đủ, phải làm gì?

**Đáp án:** Nếu yêu cầu all-or-nothing **tức thì**, đặt hai conditional updates trong **một transaction**; kiểm tra `matchedCount` từng operation và abort khi bất kỳ một item thiếu. Nếu chấp nhận eventual consistency, dùng reservation saga có bước release có idempotency, expiration và repair khi compensation lỗi.

### Bài 11 — `bulkWrite(ordered:true)` có thay transaction không?

~~~javascript
db.accounts.bulkWrite([
  {
    updateOne: {
      filter: { _id: "ACC-A" },
      update: { $inc: { balance: -150 } }
    }
  },
  {
    updateOne: {
      filter: { _id: "ACC-B" },
      update: { $inc: { balance: 150 } }
    }
  }
], { ordered: true })
~~~

**Đáp án:** Không. Ordered giữ thứ tự và dừng khi write error, **không rollback** update đầu. Chỉ có transaction bao trùm đúng operations/session mới cho all-or-nothing nhiều documents.

### Bài 12 — Majority write concern

Hai update độc lập mỗi lệnh có `writeConcern:{w:"majority"}`. Nếu update thứ hai fail, update thứ nhất tự rollback không?

**Đáp án:** Không. Write concern điều khiển mức xác nhận ghi, không tạo transaction cho hai lệnh. Ngay cả khi cả hai được majority-acknowledged độc lập, việc chúng có cùng một atomic unit không được bảo đảm.

### Bài 13 — Retry sau commit outcome không rõ

Client gọi `commitTransaction()` và nhận lỗi mang label `UnknownTransactionCommitResult`. Có nên ngay lập tức mở transaction mới và chuyển tiền cùng số lượng không?

**Đáp án:** Không. Commit trước **có thể đã thành công**. Dùng transaction API/driver để retry **commit** theo hướng dẫn, rồi reconcile bằng `transferId` ổn định nếu cần. Không tạo transfer ID mới để replay vô điều kiện.

### Bài 14 — Idempotency sau transaction success

Một transfer TR-1001 đã commit. HTTP caller vì timeout gửi lại cùng transfer request với **cùng transferId**, code chạy một transaction mới. Làm sao ngăn double debit?

**Đáp án:** Lưu transferId unique trong **cùng transaction** với debit/credit. Lần gửi lại phát hiện duplicate ID hoặc đọc trạng thái hiện có, xác minh `from/to/amount` nhất quán, trả kết quả idempotent phù hợp. Chỉ thấy một account balance sau timeout chưa đủ để chứng minh business request trước đã chạy hay chưa.

### Bài 15 — Payment gateway trong transaction

Một transaction update order rồi gọi external gateway để charge, sau đó insert payment record. Payment thành công nhưng insert thất bại. Rollback transaction có hoàn tiền ở gateway không?

**Đáp án:** Không. MongoDB chỉ rollback những writes thuộc transaction **trong MongoDB**. Gateway là hệ thống khác. Dùng workflow/saga với compensation có idempotency và lưu trạng thái phù hợp; có thể kết hợp outbox/ledger tùy kiến trúc.

### Bài 16 — Outbox có phát đúng một lần không?

Dispatcher phát event thành công nhưng chết trước khi đánh dấu outbox event là dispatched. Sau restart, event được phát lại. Outbox có thất bại hoàn toàn không?

**Đáp án:** Không. Đây là tình huống **at-least-once delivery** thường gặp. Outbox bảo đảm event intention được lưu cùng DB state; consumer dùng `eventId` dedupe để tránh lặp business side effect. Cần checkpoint và retry phù hợp.

### Bài 17 — Transaction lớn

Một migration muốn update 500.000 documents trong một transaction kéo dài nhiều phút. Có nên làm vì “tất cả cùng commit”?

**Đáp án:** Cần xem lại ranh giới bất biến. Transaction lớn tăng áp lực cache/lock, có lifetime limit và nguy cơ abort. Nếu được phép tiến từng phần, dùng batches idempotent, checkpoint, versioned rollout. Nếu bắt buộc chuyển đổi atomic đối với người đọc, cân nhắc mô hình copy/switch pointer/version để giảm ranh giới transaction.

### Bài 18 — Version và ABA

Một state đi A → B → A trong thời gian client giữ snapshot ban đầu. CAS chỉ kiểm tra `state:"A"` có phát hiện thay đổi trung gian không?

**Đáp án:** Không. Filter có thể match lại khi state quay về A. Dùng `version` tăng mỗi write để phát hiện một tài liệu đã thay đổi, miễn tất cả writers tuân thủ tăng version.

### Bài 19 — Transaction hay không cho report thống kê?

Một dashboard mỗi phút hiển thị số orders PAID và tổng revenue. Số liệu có thể trễ 10 giây mà không ảnh hưởng thanh toán. Có cần transaction để giữ mọi order/revenue summary luôn đồng bộ ngay lập tức không?

**Đáp án:** Có thể dùng projection/read model **eventually consistent**, change stream/outbox hoặc batch aggregation định kỳ, kèm timestamp/version của dữ liệu. Không cần transaction nhiều documents chỉ vì một dashboard cần nhìn nhiều collections, nếu yêu cầu chấp nhận độ trễ và dữ liệu không dùng làm quyết định thanh toán.

### Bài 20 — Ranh giới update trên một document

Một document `wallet` chứa `available`, `held` và `lastOperationId`. Một update có filter ID, available đủ và lastOperationId khác ID request, rồi cùng `$inc available:-q`, `$inc held:+q`, `$set lastOperationId:requestId`. Nó có thể chống duplicate request **không liên tiếp** sau khi có request khác chen vào không?

**Đáp án:** **Không chắc.** `lastOperationId` chỉ nhớ **request cuối cùng**. Nếu request A được xử lý, tiếp theo B thay lastOperationId thành B, rồi request A cũ được replay, filter “lastOperationId khác A” có thể match và xử lý A lần nữa. Muốn dedupe ổn định theo một khoảng retention, cần **set/ledger các operation IDs** có giới hạn và chính sách lưu trữ phù hợp, hoặc unique record của từng request trong transaction.

## 20. Tài liệu MongoDB chính thức

Khi tra cứu, hãy chọn đúng tài liệu MongoDB Server/Driver của deployment vì các chi tiết transaction, limits, error labels và tính năng mới có thể khác nhau giữa các bản phát hành.

- [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — single-document atomicity, concurrent updates, `$inc`, CAS và ranh giới `updateMany`.
- [Model Data for Atomic Operations](https://www.mongodb.com/docs/manual/tutorial/model-data-for-atomic-operations/) — mẫu nhúng `available` và `checkout` trong một document để cập nhật nguyên tử.
- [Embedded Data in Your MongoDB Schema](https://www.mongodb.com/docs/manual/data-modeling/embedding/) — lợi ích embedding cho đọc/cập nhật nguyên tử.
- [References](https://www.mongodb.com/docs/manual/data-modeling/references/) — mô hình nhiều documents và khi nào dùng reference.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — distributed ACID transactions, session, commit/abort và behavior.
- [Transactions — Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — WiredTiger cache, lifetime, lock timeout và lưu ý vận hành.
- [Read Concern, Write Concern, and Read Preference](https://www.mongodb.com/docs/manual/core/transactions/#read-concern-write-concern-and-read-preference) — concerns ở transaction level.
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — các mức đọc, trong/ngoài transaction và snapshot semantics.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — `w`, `j` và mức xác nhận ghi.
- [Read Isolation, Consistency, and Recency](https://www.mongodb.com/docs/manual/core/read-isolation-consistency-recency/) — phân biệt atomicity và tính quan sát của reads.
- [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — các write được retry, điều kiện hỗ trợ và ngoại lệ.
- [Transactions and Retry](https://www.mongodb.com/docs/manual/core/transactions-in-applications/) — hướng dẫn sử dụng transaction trong ứng dụng và retry theo driver.
- [`db.collection.updateOne()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/) — filter/update operators/`arrayFilters`/`upsert`.
- [`db.collection.findOneAndUpdate()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOneAndUpdate/) — cập nhật và trả document với atomic single-document semantics.
- [`db.collection.updateMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/) — ranh giới atomicity khi sửa nhiều documents.
- [`db.collection.bulkWrite()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/) — ordered/unordered và partial success không có transaction mặc định.
- [MongoDB Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/) — giới hạn document BSON và các giới hạn hệ thống.
- [FAQ: Concurrency](https://www.mongodb.com/docs/manual/faq/concurrency/) — locking, concurrency control và ghi đồng thời.
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession`, `TransactionOptions`, `withTransaction()` và best practices.
- [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/) — `updateOne`, `UpdateResult` và Java builders.
- [MongoDB 8.0 — Transactions](https://www.mongodb.com/docs/v8.0/core/transactions/) — tài liệu cố định theo phiên bản khi cần so sánh behavior.

**Kết luận:** Khi chọn giữa **nhúng dữ liệu, cập nhật nguyên tử và giao dịch**, hãy bắt đầu từ **bất biến nghiệp vụ** chứ không bắt đầu từ API. Nếu các field phải thay đổi cùng nhau có thể đặt hợp lý trong **một document**, hãy ưu tiên **một conditional update nguyên tử** với `$inc`, `$set`, `arrayFilters` hoặc CAS theo version khi phù hợp. Nếu dữ liệu có vòng đời độc lập, cardinality lớn hoặc contention cao, dùng **reference**; chỉ dùng **multi-document transaction** khi nhiều documents thực sự phải cùng commit/abort. Cuối cùng, dù dùng single-document write hay transaction, vẫn phải thiết kế **idempotency, retry, read/write concern và xử lý side effects ngoài MongoDB** — vì atomicity không tự giải quyết mọi vấn đề cạnh tranh và lỗi của hệ thống phân tán.
