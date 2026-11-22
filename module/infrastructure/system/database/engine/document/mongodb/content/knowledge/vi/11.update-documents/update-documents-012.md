# Thiết kế bộ lọc cập nhật có điều kiện và kiểm soát kết quả không khớp trong MongoDB

## 1. Vì sao cập nhật document cần có điều kiện?

Trong MongoDB, một lệnh cập nhật không chỉ có **giá trị muốn ghi**, mà còn có **điều kiện cho phép thay đổi**. Chẳng hạn:

- Đơn hàng chỉ được chuyển từ `PAID` sang `SHIPPED`, không được giao khi vẫn ở `DRAFT`.
- Tồn kho chỉ được giảm nếu số lượng hiện tại đủ cho yêu cầu.
- Nhân viên chỉ được sửa document thuộc tenant hoặc phạm vi họ được phép quản lý.
- Một yêu cầu ghi từ giao diện chỉ được áp dụng nếu version trên server chưa thay đổi kể từ lúc người dùng mở bản ghi.
- Coupon chỉ được sử dụng nếu còn lượt và chưa hết hạn.
- Một cập nhật không khớp phải được nhận diện đúng: document không tồn tại, sai trạng thái, xung đột đồng thời hay chỉ đơn giản là bộ lọc quá chặt?

Ví dụ thiếu điều kiện:

~~~javascript
db.orders.updateOne(
  { _id: "ord-100" },
  { $set: { status: "SHIPPED" } }
);
~~~

Lệnh này có thể chuyển trạng thái đơn hàng **bất kể trạng thái hiện tại**. Nếu yêu cầu nghiệp vụ là “chỉ giao đơn đã thanh toán”, hãy đưa điều kiện ấy vào chính filter:

~~~javascript
db.orders.updateOne(
  { _id: "ord-100", status: "PAID" },
  { $set: { status: "SHIPPED" } }
);
~~~

**Nguyên tắc cốt lõi:** Bộ lọc cập nhật là một phần của quy tắc nghiệp vụ, không chỉ là cách tìm document. Kết quả `matchedCount = 0` thường là tín hiệu quan trọng chứ không phải lỗi có thể bỏ qua.

Bài học thuộc chương **Cập nhật document**, module **Database Engine Document MongoDB**. Bạn sẽ thực hành:

1. Thiết kế filter theo `_id`, tenant, trạng thái, version và điều kiện số học.
2. Sử dụng `updateOne()`, các toán tử `$set`, `$inc`, `$unset` và điều kiện trên trường lồng nhau/mảng.
3. Phân biệt kết quả **không khớp**, **khớp nhưng không thay đổi**, **upsert** và **lỗi thực thi**.
4. Áp dụng compare-and-set và optimistic concurrency để tránh ghi đè dữ liệu.
5. Biết khi nào cần tránh `upsert: true` và `updateMany()`.
6. Diễn giải kết quả trong `mongosh`, Java Driver và MongoDB Compass.

## 2. Cấu trúc lệnh updateOne và tính nguyên tử

Trong `mongosh`:

~~~javascript
db.collection.updateOne(
  filter,
  update,
  options
);
~~~

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `filter` | Điều kiện tìm document và điều kiện tiên quyết trước khi ghi | `{ _id: "ord-100", status: "PAID" }` |
| `update` | Các toán tử thay đổi dữ liệu hoặc pipeline cập nhật hợp lệ | `{ $set: { status: "SHIPPED" } }` |
| `options` | Tùy chọn như `upsert`, `arrayFilters`, `collation`, `hint` trong ngữ cảnh hỗ trợ | `{ upsert: false }` |

Với update dùng toán tử:

~~~javascript
{
  $set: { status: "SHIPPED" },
  $inc: { version: 1 }
}
~~~

`$set` ghi hoặc thay giá trị; `$inc` tăng một trường số bằng lượng chỉ định. Trong một `updateOne`, MongoDB áp dụng update lên document được chọn theo ngữ nghĩa atomic ở phạm vi **một document**.

Luồng logic:

~~~text
             Client gửi filter + update
                         |
                         v
          MongoDB tìm document phù hợp filter
                         |
                   +-----+------+
                   |            |
                Khớp          Không khớp
                   |            |
                   v            v
              Kiểm tra     upsert: false?
             ràng buộc         |       |
                   |           Có     Không
             Thành công        |       |
                   |           v       v
                   v       Không ghi  Có thể insert
            Áp dụng update             khi upsert:true
                   |
                   v
               Write result
~~~

**Atomic trên một document không đồng nghĩa transaction cho nhiều document.** Nếu nghiệp vụ phải đồng thời đổi trạng thái đơn hàng, trừ tồn kho ở collection khác và ghi sổ kế toán, bạn cần cân nhắc transaction và thiết kế nhất quán phù hợp. Bài này tập trung vào filter cập nhật của từng document.

### 2.1. Vì sao filter phải chứa điều kiện tiên quyết?

Một cách kém an toàn:

~~~javascript
const order = db.orders.findOne({ _id: "ord-100" });

if (order.status === "PAID") {
  db.orders.updateOne(
    { _id: "ord-100" },
    { $set: { status: "SHIPPED" } }
  );
}
~~~

Giữa hai lệnh, một tiến trình khác có thể đổi `status` thành `CANCELLED`. Khi đó thao tác ghi cuối vẫn đặt `SHIPPED` nếu filter chỉ có `_id`. Đây là lỗi **time-of-check to time-of-use (TOCTOU)**.

Cách đúng cho một chuyển trạng thái:

~~~javascript
db.orders.updateOne(
  { _id: "ord-100", status: "PAID" },
  { $set: { status: "SHIPPED" } }
);
~~~

Điều kiện `status: "PAID"` được kiểm tra như một phần của thao tác cập nhật, tránh khoảng trống logic giữa “đọc” và “ghi” đối với document đó.

## 3. Bộ dữ liệu thực hành độc lập

Mở MongoDB Server bằng `mongosh` với tài khoản được phép ghi vào database thử nghiệm:

~~~javascript
use conditional_update_lab
~~~

Tạo bộ dữ liệu đơn hàng:

~~~javascript
const demoOrders = [
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    customerId: "cus-01",
    status: "PAID",
    version: NumberInt(1),
    amount: NumberDecimal("125.50"),
    shipping: { city: "Hà Nội", method: "STANDARD" },
    lines: [
      { sku: "BK-01", quantity: NumberInt(2) },
      { sku: "BK-02", quantity: NumberInt(1) }
    ]
  },
  {
    _id: "ord-200",
    tenantId: "tenant-A",
    customerId: "cus-02",
    status: "DRAFT",
    version: NumberInt(1),
    amount: NumberDecimal("49.00"),
    shipping: { city: "Đà Nẵng", method: "EXPRESS" },
    lines: [{ sku: "BK-03", quantity: NumberInt(1) }]
  },
  {
    _id: "ord-300",
    tenantId: "tenant-A",
    customerId: "cus-03",
    status: "SHIPPED",
    version: NumberInt(3),
    amount: NumberDecimal("89.90"),
    shipping: { city: "Huế", method: "STANDARD" },
    lines: [{ sku: "BK-01", quantity: NumberInt(1) }]
  },
  {
    _id: "ord-400",
    tenantId: "tenant-B",
    customerId: "cus-04",
    status: "PAID",
    version: NumberInt(1),
    amount: NumberDecimal("210.00"),
    shipping: { city: "TP. Hồ Chí Minh", method: "EXPRESS" },
    lines: [{ sku: "BK-04", quantity: NumberInt(3) }]
  },
  {
    _id: "ord-500",
    tenantId: "tenant-A",
    customerId: "cus-05",
    status: "CANCELLED",
    version: NumberInt(2),
    amount: NumberDecimal("35.00"),
    shipping: { city: "Hà Nội", method: "STANDARD" },
    lines: []
  }
];

demoOrders.forEach(order => {
  db.orders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true }
  );
});

db.orders.find(
  {},
  { _id: 1, tenantId: 1, status: 1, version: 1 }
).sort({ _id: 1 });
~~~

Tạo dữ liệu tồn kho và coupon để thực hành điều kiện số:

~~~javascript
db.inventory.replaceOne(
  { _id: "stock-BK-01" },
  {
    _id: "stock-BK-01",
    tenantId: "tenant-A",
    sku: "BK-01",
    available: NumberInt(8),
    reserved: NumberInt(0),
    version: NumberInt(1)
  },
  { upsert: true }
);

db.coupons.replaceOne(
  { _id: "coupon-WELCOME" },
  {
    _id: "coupon-WELCOME",
    tenantId: "tenant-A",
    status: "ACTIVE",
    remainingUses: NumberInt(2),
    expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
  },
  { upsert: true }
);
~~~

Bộ dữ liệu này là môi trường thử nghiệm. Nếu chạy lại các lệnh nạp mẫu, `replaceOne(..., {upsert:true})` sẽ **đặt lại document mẫu** theo nội dung trên. Những thao tác cập nhật phía sau có thể khiến kết quả bài tập thay đổi nếu chạy nhiều lần mà không reset.

Để xem trạng thái hiện tại:

~~~javascript
db.orders.findOne({ _id: "ord-100" });
db.inventory.findOne({ _id: "stock-BK-01" });
db.coupons.findOne({ _id: "coupon-WELCOME" });
~~~

## 4. Thiết kế filter từ khóa định danh đến quy tắc nghiệp vụ

### 4.1. Bắt đầu bằng khóa duy nhất

Một update nhắm vào một bản ghi xác định nên có điều kiện định danh chính xác:

~~~javascript
{ _id: "ord-100" }
~~~

`_id` của collection thông thường có unique index. Dùng đúng kiểu BSON: string `"ord-100"` khác ObjectId hoặc một kiểu dữ liệu khác có cách in tương tự.

Nếu dùng filter rộng:

~~~javascript
db.orders.updateOne(
  { status: "PAID" },
  { $set: { reviewed: true } }
);
~~~

MongoDB chỉ cập nhật **một** trong số các document khớp. Không nên dựa vào thứ tự tự nhiên để đoán đó là đơn nào. Khi nghiệp vụ nhắm một đơn xác định, dùng `_id` hoặc unique key; khi nghiệp vụ thật sự cập nhật nhiều đơn, cân nhắc `updateMany` với kiểm soát phạm vi.

### 4.2. Thêm phạm vi tenant

Với ứng dụng đa tenant:

~~~javascript
{
  _id: "ord-100",
  tenantId: "tenant-A"
}
~~~

Điều kiện tenant giúp bảo đảm cập nhật không vô tình áp dụng cho document ngoài phạm vi đã xác định. Tuy nhiên, **filter tenant không thay thế xác thực/phân quyền**. Server-side application phải lấy tenant được phép từ danh tính đã xác thực, không tin tuyệt đối vào tenantId tùy ý từ request.

Ví dụ minh họa:

~~~javascript
db.orders.updateOne(
  { _id: "ord-400", tenantId: "tenant-A" },
  { $set: { reviewed: true } }
);
~~~

Không có document khớp vì `ord-400` thuộc `tenant-B`. Đây là kết quả mong muốn trong bộ dữ liệu mẫu.

### 4.3. Thêm trạng thái hiện tại làm precondition

~~~javascript
{
  _id: "ord-100",
  tenantId: "tenant-A",
  status: "PAID"
}
~~~

Bộ lọc này bảo vệ quy tắc “chỉ cập nhật nếu đơn đã thanh toán”. Điều kiện không chỉ tìm tài liệu mà còn **diễn đạt trạng thái trước chuyển đổi**.

Thao tác:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    status: "PAID"
  },
  {
    $set: {
      status: "SHIPPED",
      shippedAt: new Date()
    }
  }
);

printjson(result);
~~~

Khi mẫu ở trạng thái ban đầu, `matchedCount: 1` và `modifiedCount: 1` là kết quả kỳ vọng. Nếu chạy lại ngay, document đã là `SHIPPED` nên không còn khớp precondition `status: "PAID"`: `matchedCount: 0`.

Đây là cách chuyển trạng thái có điều kiện, khác với cập nhật trạng thái một cách vô điều kiện.

### 4.4. Nhiều điều kiện là AND mặc định

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-200",
    tenantId: "tenant-A",
    status: "DRAFT",
    "shipping.method": "EXPRESS"
  },
  {
    $set: {
      "shipping.city": "Cần Thơ"
    }
  }
);
~~~

Các điều kiện phải **đồng thời đúng**. Dấu chấm trong `"shipping.method"` truy cập field lồng nhau. Tương tự, update với `$set: {"shipping.city": "..."}` sửa đúng trường con thay vì thay cả object `shipping`.

### 4.5. Dùng $in khi có nhiều trạng thái hợp lệ

Một hành động có thể chấp nhận nhiều trạng thái xuất phát:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-200",
    tenantId: "tenant-A",
    status: { $in: ["DRAFT", "PENDING"] }
  },
  {
    $set: { lastCheckedAt: new Date() }
  }
);
~~~

Điều kiện này nói rõ danh sách trạng thái được phép. Khi nghiệp vụ yêu cầu một **allowlist trạng thái**, `$in` thường chính xác hơn `$nin`, bởi `$nin` có thể khớp field thiếu hoặc null.

## 5. Kết quả update: matchedCount khác modifiedCount

Một kết quả cập nhật có xác nhận thường chứa:

~~~javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedId: null,
  upsertedCount: 0
}
~~~

Tùy phiên bản mongosh/driver và write concern, định dạng in có thể khác, nhưng các ý nghĩa chính là:

| Thuộc tính | Ý nghĩa |
|---|---|
| `acknowledged` | Thao tác ghi có được xác nhận theo write concern hay không |
| `matchedCount` | Số document khớp filter; với `updateOne` thường là 0 hoặc 1 |
| `modifiedCount` | Số document có nội dung được sửa; thường là 0 hoặc 1 |
| `upsertedCount` | Số document được chèn bằng upsert; thường là 0 hoặc 1 |
| `upsertedId` | Định danh document được tạo khi upsert xảy ra |

Phân biệt ba tình huống:

~~~text
matchedCount = 1, modifiedCount = 1
    → Tìm được document và nội dung đã thay đổi.

matchedCount = 1, modifiedCount = 0
    → Tìm được document nhưng không có thay đổi thực tế,
      ví dụ $set cùng giá trị đã có.

matchedCount = 0, modifiedCount = 0, upsertedCount = 0
    → Không có document nào khớp và không chèn mới.
~~~

Nếu `upsertedCount = 1` thì đã xảy ra **insert**; không xem đó là update một document hiện hữu.

### 5.1. Ví dụ matched nhưng không modified

~~~javascript
db.orders.updateOne(
  { _id: "ord-300", tenantId: "tenant-A" },
  { $set: { status: "SHIPPED" } }
);
~~~

`ord-300` đã có `status: "SHIPPED"`. Khi không có field nào khác thay đổi, kết quả có thể là:

~~~javascript
{
  matchedCount: 1,
  modifiedCount: 0
}
~~~

**`modifiedCount = 0` không đồng nghĩa không tìm thấy document.** Đây là trường hợp *no-op* hợp lệ: ghi cùng giá trị hiện có.

### 5.2. Ví dụ không khớp

~~~javascript
db.orders.updateOne(
  { _id: "ord-300", status: "PAID" },
  { $set: { status: "SHIPPED" } }
);
~~~

Trên dữ liệu mẫu, đơn `ord-300` đã ở `SHIPPED`, nên filter không khớp:

~~~javascript
{
  matchedCount: 0,
  modifiedCount: 0
}
~~~

Không thể chỉ từ hai con số này khẳng định document **không tồn tại**. Trong ví dụ, document vẫn tồn tại, nhưng **không thỏa điều kiện trạng thái**.

### 5.3. Bảng quyết định xử lý kết quả

| Kết quả | Diễn giải tối thiểu có thể kết luận | Bước tiếp theo |
|---|---|---|
| Matched 1, modified 1 | Có bản ghi khớp và đã thay đổi | Xác nhận thành công |
| Matched 1, modified 0 | Có bản ghi khớp nhưng không thay đổi | Kiểm tra yêu cầu có cho phép no-op không |
| Matched 0, upserted 0 | Không bản ghi nào thỏa toàn bộ filter | Phân loại not found / conflict / precondition |
| Upserted 1 | Đã tạo bản ghi mới | Trả kết quả created/upserted phù hợp |
| Throw exception | Có lỗi lệnh, quyền, validation, unique key, network... | Phân tích loại lỗi, không đánh đồng với no-match |
| Write chưa được xác nhận | Không có đủ số liệu chắc chắn từ kết quả ghi | Kiểm tra write concern và trạng thái theo quy trình |

## 6. Không khớp là một trạng thái nghiệp vụ, không mặc định là lỗi server

Một filter có thể gồm nhiều điều kiện:

~~~javascript
{
  _id: "ord-100",
  tenantId: "tenant-A",
  status: "PAID",
  version: NumberInt(1)
}
~~~

Nếu `matchedCount: 0`, những khả năng thường gặp:

1. **Không tồn tại:** document `_id` tương ứng đã bị xóa hoặc chưa từng tạo.
2. **Sai phạm vi:** document thuộc tenant khác; ứng dụng không được tiết lộ dữ liệu của tenant đó.
3. **Sai trạng thái:** document đang `DRAFT`, `SHIPPED`, `CANCELLED` hoặc trạng thái khác.
4. **Xung đột version:** document vẫn tồn tại nhưng đã được một tác nhân khác cập nhật.
5. **Sai kiểu dữ liệu:** ID, version, ngày hoặc số được truyền theo kiểu BSON không mong muốn.
6. **Điều kiện bổ sung không còn đúng:** tồn kho không đủ, coupon hết lượt, thời hạn đã qua.
7. **Dữ liệu không nhất quán với hợp đồng:** trường bị thiếu hoặc chứa null, khiến filter loại document.

Từ `matchedCount: 0` **không biết chắc nguyên nhân duy nhất**. Cần một chiến lược kiểm tra phù hợp nghiệp vụ, quyền đọc và mức độ tiết lộ thông tin được phép.

### 6.1. Chẩn đoán bằng truy vấn đọc sau khi no-match

Một ví dụ trên database thực hành:

~~~javascript
const orderId = "ord-300";
const tenantId = "tenant-A";

const result = db.orders.updateOne(
  {
    _id: orderId,
    tenantId: tenantId,
    status: "PAID"
  },
  {
    $set: { status: "SHIPPED" }
  }
);

if (result.matchedCount === 0) {
  const current = db.orders.findOne(
    { _id: orderId, tenantId: tenantId },
    { _id: 1, status: 1, version: 1 }
  );

  if (current === null) {
    print("Không tìm thấy bản ghi trong phạm vi được phép.");
  } else {
    print("Bản ghi còn tồn tại nhưng không thỏa điều kiện cập nhật.");
    printjson(current);
  }
}
~~~

Điều kiện tenant **vẫn có mặt trong truy vấn chẩn đoán**. Đây là điểm quan trọng đối với multi-tenant: không nên đọc theo `_id` bỏ qua phạm vi cho phép rồi tiết lộ trạng thái thật của tài nguyên mà người dùng không có quyền.

Kết quả đọc sau update chỉ là **quan sát ở thời điểm mới**. Nếu có thay đổi đồng thời, document có thể lại đổi trạng thái trước hoặc sau khi bạn chẩn đoán. Không dùng câu trả lời này làm bằng chứng rằng trạng thái đọc được chắc chắn là trạng thái vào đúng thời điểm update thất bại.

### 6.2. Phân loại kết quả ở tầng API

Một cách thiết kế HTTP API thường gặp:

| Tình huống đã xác nhận theo chính sách ứng dụng | Phản hồi có thể phù hợp |
|---|---|
| Đối tượng không tồn tại trong phạm vi được phép | `404 Not Found` |
| Version không khớp hoặc trạng thái đã thay đổi | `409 Conflict` |
| Điều kiện nếu-match của HTTP không thỏa | `412 Precondition Failed` |
| Dữ liệu đầu vào không hợp lệ | `400 Bad Request` hoặc `422 Unprocessable Content` tùy quy ước |
| Đã xử lý thành công, kể cả no-op được phép | `200 OK` hoặc `204 No Content` |
| Lỗi hạ tầng chưa rõ kết quả ghi | Phản hồi lỗi phù hợp, kết hợp cơ chế đối soát/retry |

Không có quy tắc bắt buộc “mọi `matchedCount: 0` đều là 404”. Status code phải phù hợp hợp đồng API và chính sách bảo mật.

## 7. Compare-and-set: chuyển trạng thái một cách nguyên tử

**Compare-and-set (CAS)** là mô hình: chỉ ghi giá trị mới nếu dữ liệu hiện tại còn bằng giá trị kỳ vọng.

~~~text
Expected state: PAID
New state:      SHIPPED

Nếu server còn PAID  → ghi SHIPPED
Nếu server khác PAID → không ghi
~~~

Ví dụ:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    status: "PAID"
  },
  {
    $set: {
      status: "SHIPPED",
      shippedAt: new Date()
    }
  }
);
~~~

Khi hai worker đồng thời muốn chuyển một document từ `PAID` sang `SHIPPED`, chỉ worker nào còn thấy document thỏa `status: "PAID"` tại thao tác cập nhật mới thực hiện được chuyển đổi. Worker còn lại nhận `matchedCount: 0` sau khi trạng thái đã đổi.

Điều này đặc biệt hữu ích cho chuyển trạng thái, khóa tác vụ, đặt cờ xử lý một lần hoặc các thao tác mà chỉ một bên được giành quyền chuyển trạng thái.

### 7.1. Không dùng $ne khi chỉ có một trạng thái được phép

~~~javascript
// Rộng hơn nghiệp vụ "chỉ từ PAID":
db.orders.updateOne(
  {
    _id: "ord-100",
    status: { $ne: "SHIPPED" }
  },
  { $set: { status: "SHIPPED" } }
);
~~~

`$ne: "SHIPPED"` có thể khớp document đang `DRAFT`, `CANCELLED` hoặc **thiếu trường status**. Nếu chỉ cho phép chuyển từ `PAID`, filter nên ghi đúng `status: "PAID"`.

Tương tự, `$nin` dùng để loại một số trạng thái không tự bảo vệ quy tắc whitelist; hãy xác định rõ danh sách trạng thái xuất phát hợp lệ.

### 7.2. Tránh gửi lại yêu cầu gây tác động phụ

Nếu thao tác chuyển trạng thái còn gửi email, phát event hoặc trừ tồn kho ở nơi khác, việc worker đầu tiên thành công không có nghĩa worker thứ hai có thể lặp lại các tác động đó. Nên phân biệt:

- **Thao tác đổi trạng thái:** thực hiện có điều kiện trong database.
- **Tác động ngoài database:** được xử lý theo cơ chế đảm bảo phát và xử lý một lần theo hợp đồng (ví dụ outbox/idempotency).

Không kết luận một hệ thống “exactly once” chỉ từ việc dùng `status: "PAID"` trong filter.

## 8. Optimistic concurrency bằng trường version

Filter theo trạng thái hữu ích, nhưng đôi khi trạng thái vẫn giống nhau trong khi một trường khác đã đổi. Khi client đọc cả document rồi gửi một bản cập nhật, dùng **version** để tránh ghi đè snapshot cũ.

Ví dụ document ban đầu:

~~~javascript
{
  _id: "ord-200",
  tenantId: "tenant-A",
  status: "DRAFT",
  version: NumberInt(1),
  shipping: { city: "Đà Nẵng", method: "EXPRESS" }
}
~~~

### 8.1. Đọc version hiện hành

~~~javascript
const current = db.orders.findOne(
  { _id: "ord-200", tenantId: "tenant-A" }
);

printjson({
  id: current._id,
  status: current.status,
  version: current.version
});
~~~

Trong ứng dụng thật, bản ghi có thể được đọc trước đó vài giây hoặc lâu hơn; `version` là giá trị mà client tin là còn đúng.

### 8.2. Update có expectedVersion

~~~javascript
const expectedVersion = NumberInt(1);

const result = db.orders.updateOne(
  {
    _id: "ord-200",
    tenantId: "tenant-A",
    version: expectedVersion
  },
  {
    $set: {
      "shipping.city": "Cần Thơ"
    },
    $inc: {
      version: NumberInt(1)
    }
  }
);

printjson(result);
~~~

Khi document còn version 1, update thành công và version tăng lên 2. Sau đó một client khác gửi lại filter với version 1 thì không còn khớp. Không cần khóa pessimistic để phát hiện phiên bản cũ trong trường hợp này.

### 8.3. Gộp version và trạng thái

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-200",
    tenantId: "tenant-A",
    status: "DRAFT",
    version: NumberInt(2)
  },
  {
    $set: { status: "PENDING" },
    $inc: { version: NumberInt(1) }
  }
);
~~~

Filter này bảo vệ **cả** quy tắc chuyển trạng thái lẫn kỳ vọng về version. Nếu bất kỳ điều kiện nào không còn đúng, lệnh không cập nhật.

### 8.4. Điều kiện để version có ý nghĩa

Mọi đường ghi làm thay đổi những trường mà client cần bảo vệ phải thống nhất cập nhật version:

~~~javascript
db.orders.updateOne(
  { _id: "ord-200", tenantId: "tenant-A" },
  {
    $set: { "shipping.method": "STANDARD" },
    $inc: { version: NumberInt(1) }
  }
);
~~~

Nếu một tiến trình khác sửa document nhưng không tăng version, client giữ version cũ vẫn có thể ghi đè dữ liệu. Vì vậy **version là giao thức giữa các luồng ghi**, không phải chỉ một trường trang trí.

### 8.5. Version conflict xử lý thế nào?

Khi `matchedCount: 0` do version cũ:

1. Không tự động dùng cùng payload để ghi đè.
2. Đọc lại trạng thái hiện tại trong phạm vi được phép.
3. Cho client biết dữ liệu đã đổi và cung cấp cách tải lại/merge phù hợp.
4. Nếu tự retry, phải xây lại thay đổi dựa trên document mới và xác định rằng hành động còn hợp lệ.
5. Với thay đổi số lượng/tiền, cân nhắc dùng update operator atomic thay vì thay lại số đã tính trước.

Một câu lệnh không khớp version thường nên được coi là **xung đột có thể dự kiến**, không phải lỗi server cần retry liên tục.

## 9. Điều kiện số học: chỉ trừ tồn kho khi đủ

Một nghiệp vụ phổ biến là giảm tồn kho mà không để số lượng âm.

**Cách không an toàn:**

~~~javascript
const inv = db.inventory.findOne({ _id: "stock-BK-01" });

if (inv.available >= 3) {
  db.inventory.updateOne(
    { _id: "stock-BK-01" },
    { $inc: { available: -3, reserved: 3 } }
  );
}
~~~

Hai tiến trình có thể cùng đọc `available = 8`, cùng thấy đủ hàng rồi cùng trừ, dẫn tới oversell khi số lượng yêu cầu cộng dồn vượt tồn kho.

**Cách an toàn hơn trong một document:**

~~~javascript
const requested = NumberInt(3);

const result = db.inventory.updateOne(
  {
    _id: "stock-BK-01",
    tenantId: "tenant-A",
    available: { $gte: requested }
  },
  {
    $inc: {
      available: NumberInt(-3),
      reserved: NumberInt(3),
      version: NumberInt(1)
    }
  }
);

printjson(result);
db.inventory.findOne({ _id: "stock-BK-01" });
~~~

Với dữ liệu mẫu ban đầu, `available` từ 8 còn 5, `reserved` từ 0 lên 3. Nếu muốn trừ 6 khi chỉ còn 5:

~~~javascript
db.inventory.updateOne(
  {
    _id: "stock-BK-01",
    tenantId: "tenant-A",
    available: { $gte: 6 }
  },
  {
    $inc: {
      available: -6,
      reserved: 6
    }
  }
);
~~~

Kết quả mong đợi `matchedCount: 0`, không làm tồn kho âm.

### 9.1. Vì sao cần $inc thay vì $set số đã tính trước?

Giả sử hai worker cùng đọc `available = 8`. Nếu cả hai tính `8 - 3 = 5` rồi dùng `$set: {available:5}`, hai lần cập nhật có thể làm tồn kho chỉ giảm 3 dù thực tế đã có hai yêu cầu giữ hàng. `$inc` thực hiện phép thay đổi theo giá trị hiện hành trong cùng thao tác ghi.

Kết hợp `available: {$gte: requested}` và `$inc` cho phép MongoDB đánh giá điều kiện tồn kho và cập nhật document theo thao tác atomic.

### 9.2. Không tự suy ra lý do từ matchedCount = 0

Không khớp có thể vì:

- SKU/ID kho không tồn tại.
- `tenantId` khác.
- Số lượng `available` không đủ.
- Field `available` thiếu hoặc sai kiểu.

Ứng dụng có thể đọc thông tin tồn kho được phép hiển thị để đưa thông báo phù hợp. Không trả thông tin của tenant khác chỉ vì muốn phân loại kết quả chính xác hơn.

### 9.3. Đơn vị và kiểu số

Dùng số nguyên phù hợp miền giá trị cho tồn kho. Nếu ứng dụng cho phép số lượng hàng rất lớn, cần xét Int64 và giới hạn tràn số. Với tiền tệ, tránh phép tính giảm tiền bằng Double không chính xác; nên dùng Decimal128 hoặc đơn vị nhỏ nhất dạng số nguyên theo hợp đồng riêng.

## 10. Điều kiện thời gian và giới hạn lượt sử dụng

Một coupon chỉ còn hiệu lực nếu đang ACTIVE, chưa hết hạn và còn lượt. Có thể kết hợp các điều kiện trong cùng một filter.

~~~javascript
const result = db.coupons.updateOne(
  {
    _id: "coupon-WELCOME",
    tenantId: "tenant-A",
    status: "ACTIVE",
    remainingUses: { $gt: 0 },
    expiresAt: { $gt: new Date() }
  },
  {
    $inc: { remainingUses: NumberInt(-1) },
    $set: { lastUsedAt: new Date() }
  }
);

printjson(result);
~~~

Bộ dữ liệu ở mục 3 tạo coupon hết hạn sau 7 ngày tính từ thời điểm nạp mẫu, giúp chạy ví dụ trong phiên thực hành. Với coupon còn 2 lượt, hai lần dùng thành công có thể đưa `remainingUses` về 0; lần tiếp theo không khớp.

### 10.1. Dấu thời gian phải đúng kiểu BSON

`expiresAt` được lưu dạng Date. Nếu API gửi một chuỗi ISO nhưng database lưu BSON Date, ứng dụng phải parse thành Date trước khi tạo điều kiện so sánh. Không mặc định chuỗi ngày giờ được MongoDB tự chuyển thành Date.

### 10.2. Thời gian kiểm tra khác thời gian hiển thị

Thao tác trên dùng `new Date()` để lấy thời gian ở client tạo request. Nếu hệ thống cần quy định thời gian kiểm tra theo server và tránh lệch đồng hồ nhiều client, cần thiết kế chính sách thời gian nhất quán; không mặc định máy client luôn đồng bộ hoàn hảo.

Đối với tính đúng đắn nghiêm ngặt về thời hạn, cần xét thời điểm điều kiện được đánh giá, cơ chế tạo thời gian, và hậu quả nếu đồng hồ client bị lệch. Không chỉ đổi cách viết filter mà bỏ qua hợp đồng về thời gian.

### 10.3. Không dùng $nin cho điều kiện “còn hạn”

Filter `status: {$nin:["EXPIRED"]}` có thể chọn coupon thiếu status hoặc còn trạng thái không được phép. Nếu yêu cầu là ACTIVE, viết đúng `status:"ACTIVE"` kết hợp điều kiện `expiresAt`.

## 11. Trường lồng nhau và mảng trong filter cập nhật

### 11.1. Điều kiện trên object lồng nhau

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-200",
    tenantId: "tenant-A",
    status: "DRAFT",
    "shipping.method": "EXPRESS"
  },
  {
    $set: {
      "shipping.city": "Hải Phòng"
    }
  }
);
~~~

Điều kiện `"shipping.method"` được kiểm tra trước khi cập nhật field `"shipping.city"`. Sử dụng dot notation giúp thay trường con mà không thay toàn bộ object `shipping`.

Nếu `shipping` thiếu hoặc giá trị sai kiểu, điều kiện trên có thể không khớp. Không nên sửa rộng bằng cách bỏ điều kiện nếu field đó đại diện một precondition nghiệp vụ quan trọng.

### 11.2. Phần tử mảng: điều kiện phải nằm trên cùng một object

Giả sử `ord-100` có:

~~~javascript
lines: [
  { sku: "BK-01", quantity: NumberInt(2) },
  { sku: "BK-02", quantity: NumberInt(1) }
]
~~~

Yêu cầu: chỉ giảm một đơn vị `quantity` của dòng có `sku = "BK-01"` nếu **cùng dòng đó** còn ít nhất 1.

Không nên chỉ dùng hai dot-path độc lập:

~~~javascript
{
  "lines.sku": "BK-01",
  "lines.quantity": { $gte: 1 }
}
~~~

Hai điều kiện trên **có thể được thỏa bởi các phần tử khác nhau** trong cùng mảng. Dùng `$elemMatch` để ràng buộc một phần tử thỏa cả hai:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    lines: {
      $elemMatch: {
        sku: "BK-01",
        quantity: { $gte: 1 }
      }
    }
  },
  {
    $inc: {
      "lines.$.quantity": NumberInt(-1)
    }
  }
);
~~~

Toán tử vị trí `$` trong đường dẫn cập nhật tham chiếu phần tử array được filter tìm thấy. Với dữ liệu mẫu ban đầu, `BK-01` giảm từ 2 còn 1.

### 11.3. Nếu mảng có nhiều phần tử cùng SKU?

Toán tử vị trí `$` trong ví dụ cập nhật một phần tử khớp; nếu cùng SKU lặp lại và nghiệp vụ muốn cập nhật tất cả, cần một chiến lược khác, thường dùng `arrayFilters` với `$[identifier]` và điều kiện rõ.

Ví dụ minh họa:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    lines: {
      $elemMatch: {
        sku: "BK-01",
        quantity: { $gte: 1 }
      }
    }
  },
  {
    $inc: {
      "lines.$[line].quantity": NumberInt(-1)
    }
  },
  {
    arrayFilters: [
      {
        "line.sku": "BK-01",
        "line.quantity": { $gte: 1 }
      }
    ]
  }
);
~~~

Đoạn này cập nhật **mọi phần tử** trong `lines` thỏa `arrayFilters`, không phải chỉ một phần tử. Khi nghiệp vụ chỉ cho phép một SKU xuất hiện một lần, nên thực thi ràng buộc đó ở mô hình dữ liệu/ứng dụng. Nếu không, việc cập nhật tất cả có thể giảm nhiều dòng ngoài ý định.

### 11.4. Không dùng điều kiện array mơ hồ trong nghiệp vụ nhạy cảm

Một document có:

~~~javascript
lines: [
  { sku: "BK-01", quantity: NumberInt(0) },
  { sku: "BK-02", quantity: NumberInt(10) }
]
~~~

Filter dùng hai dot-path độc lập có thể nhận thấy SKU BK-01 ở dòng đầu và quantity >= 1 ở dòng sau, rồi coi document hợp lệ. `$elemMatch` ngăn kiểu “khớp chéo phần tử” này.

## 12. matchedCount = 0 và các lựa chọn ứng xử

Trước khi xử lý no-match, phải phân biệt hai loại API:

- **Lệnh có điều kiện bắt buộc:** ví dụ giao đơn chỉ khi PAID. Không khớp là precondition thất bại; không được bỏ filter rồi thử lại vô điều kiện.
- **Lệnh hướng tới trạng thái cuối cùng:** ví dụ “đặt cờ reviewed = true”; nếu cờ đã true, một no-op có thể được xem là thành công theo hợp đồng API.

### 12.1. “Không tìm thấy” và “trạng thái đã thay đổi” là hai vấn đề khác nhau

~~~javascript
const filter = {
  _id: "ord-300",
  tenantId: "tenant-A",
  status: "PAID"
};

const result = db.orders.updateOne(
  filter,
  { $set: { status: "SHIPPED" } }
);
~~~

Nếu no-match, đừng kết luận `ord-300` không tồn tại. Đơn này hiện `SHIPPED`. Nhưng nếu client không có quyền xem trạng thái, ứng dụng có thể cố ý trả cùng thông điệp cho nhiều trường hợp để không lộ thông tin.

### 12.2. Không được bỏ điều kiện để “sửa” zero matched

Sai:

~~~javascript
const conditional = db.orders.updateOne(
  { _id: "ord-300", status: "PAID" },
  { $set: { status: "SHIPPED" } }
);

if (conditional.matchedCount === 0) {
  // Sai: bỏ status thì thay đổi quy tắc nghiệp vụ.
  db.orders.updateOne(
    { _id: "ord-300" },
    { $set: { status: "SHIPPED" } }
  );
}
~~~

Nhánh fallback phá bỏ ý nghĩa của precondition. Nếu trạng thái khác kỳ vọng, cần trả conflict hoặc điều hướng sang quy trình nghiệp vụ khác.

### 12.3. Retry khi nào?

Phân biệt:

| Tình huống | Hướng xử lý |
|---|---|
| `matchedCount: 0` vì status/version không đúng | Không retry cùng filter mù quáng; đọc lại, phân loại conflict |
| `matchedCount: 1`, `modifiedCount: 0` | Xem có phải no-op hợp lệ; không coi là lỗi mạng |
| Lỗi mạng trước/giữa thao tác, chưa chắc server đã ghi | Dùng cơ chế retryable writes/đối soát phù hợp; không giả định chắc chắn “chưa ghi” |
| Duplicate key từ upsert | Kiểm tra race/unique key, quyết định retry có điều kiện |
| Lỗi validation | Sửa dữ liệu đầu vào hoặc schema, không retry nguyên lệnh |
| Lỗi không đủ quyền | Điều chỉnh phân quyền theo quy trình, không bỏ tenant/filter |

Một số MongoDB Driver hỗ trợ **retryable writes** với điều kiện triển khai thích hợp. Cơ chế driver không đồng nghĩa mọi logic nghiệp vụ và mọi tác động phụ bên ngoài có thể được retry vô hạn mà không tạo bản ghi hoặc thanh toán trùng.

## 13. Thiết kế tính idempotent

**Idempotent** nghĩa là lặp lại một yêu cầu không làm thay đổi kết quả cuối cùng ngoài ý định, theo hợp đồng đã định.

### 13.1. $set cùng một giá trị có thể là idempotent

~~~javascript
db.orders.updateOne(
  { _id: "ord-300", tenantId: "tenant-A" },
  { $set: { reviewed: true } }
);
~~~

Chạy lần đầu có thể `modifiedCount: 1`; chạy lại `matchedCount: 1, modifiedCount: 0`. Trạng thái cuối cùng vẫn là `reviewed: true`.

### 13.2. $inc không tự idempotent

~~~javascript
db.inventory.updateOne(
  { _id: "stock-BK-01" },
  { $inc: { available: -1 } }
);
~~~

Nếu chạy hai lần với cùng yêu cầu nghiệp vụ, tồn kho giảm hai đơn vị. Với các hành động cần thực hiện **chính xác một lần theo requestId**, phải thiết kế idempotency key và nơi lưu trạng thái xử lý, thường kết hợp unique constraint hoặc transaction/outbox khi tác động tới nhiều document.

Một filter theo trạng thái chỉ giúp chặn tác động trùng nếu trạng thái **thực sự đổi theo cách loại lần chạy tiếp theo**.

### 13.3. CAS giúp idempotency trong một trường hợp

~~~javascript
db.orders.updateOne(
  { _id: "ord-100", status: "PAID" },
  { $set: { status: "SHIPPED" } }
);
~~~

Nếu thao tác đã thành công lần đầu, lần sau với precondition `PAID` không khớp nữa. Tuy nhiên, ứng dụng vẫn cần xác định phản hồi cho request lặp lại: trả conflict, chấp nhận “đã SHIPPED” là thành công logic, hay đối chiếu theo requestId. Không thể biết yêu cầu lặp lại thuộc cùng một người gửi chỉ từ trạng thái `SHIPPED`.

## 14. Upsert: hữu ích nhưng nguy hiểm với precondition

`upsert: true` yêu cầu MongoDB chèn document mới nếu filter không khớp. Nó phù hợp với mục đích “lưu nếu có, tạo nếu chưa”, nhưng có thể **sai ngữ nghĩa** khi no-match là tín hiệu vi phạm điều kiện nghiệp vụ.

### 14.1. Ví dụ dễ gây nhầm

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    status: "PAID"
  },
  {
    $set: { status: "SHIPPED" }
  },
  {
    upsert: true
  }
);
~~~

Nếu `ord-100` đã chuyển sang `SHIPPED`, filter `status: "PAID"` không còn khớp. Vì bật upsert, server có thể **thử chèn document mới** theo quy tắc upsert thay vì báo no-match thông thường. Khi `_id: "ord-100"` đã tồn tại, việc chèn có thể vi phạm unique index và trả lỗi duplicate key.

Nếu filter không ràng buộc `_id` duy nhất, hệ thống còn có nguy cơ tạo thêm document ngoài ý định. Vì vậy:

> **Không bật upsert chỉ để “xử lý” matchedCount = 0 của một thao tác chuyển trạng thái có điều kiện.**

### 14.2. Dùng upsert cho tạo cấu hình theo khóa duy nhất

Một ví dụ hợp lý hơn là lưu cấu hình theo `_id`:

~~~javascript
db.settings.updateOne(
  { _id: "tenant-A:notification" },
  {
    $set: {
      enabled: true,
      updatedAt: new Date()
    },
    $setOnInsert: {
      createdAt: new Date()
    }
  },
  { upsert: true }
);
~~~

Nếu chưa có, document sẽ được chèn. Nếu đã có, các field trong `$set` được cập nhật; `$setOnInsert` chỉ áp dụng cho nhánh insert.

Kết quả phải được phân biệt:

~~~text
matchedCount: 1, upsertedCount: 0 → cập nhật document hiện có
matchedCount: 0, upsertedCount: 1 → tạo document mới
~~~

Với upsert cạnh tranh từ nhiều tiến trình, vẫn cần unique index và xử lý duplicate key theo thiết kế.

## 15. updateMany: không thể xử lý như updateOne

`updateMany` thay đổi **tất cả document khớp filter**, vì vậy lỗi filter rộng có tác động lớn hơn.

~~~javascript
db.orders.updateMany(
  {
    tenantId: "tenant-A",
    status: "DRAFT"
  },
  {
    $set: {
      needsReview: true
    }
  }
);
~~~

Trên dữ liệu mẫu ban đầu, điều kiện này nhắm `ord-200`. Nhưng trong database lớn, có thể có hàng nghìn document cùng trạng thái.

### 15.1. Xem trước phạm vi

~~~javascript
const filter = {
  tenantId: "tenant-A",
  status: "DRAFT"
};

db.orders.find(
  filter,
  { _id: 1, tenantId: 1, status: 1 }
);

db.orders.countDocuments(filter);
~~~

Sau khi xác nhận đúng mục tiêu, mới thực hiện update:

~~~javascript
db.orders.updateMany(
  filter,
  {
    $set: {
      needsReview: true
    }
  }
);
~~~

**Chú ý:** `countDocuments` chạy trước không đóng băng dữ liệu. Những document mới có thể khớp hoặc ngừng khớp giữa lúc đếm và lúc update. Nếu cần một tập document cố định, hãy thiết kế quy trình batch/snapshot/transaction thích hợp thay vì coi preview là một lock.

### 15.2. Vì sao matchedCount và modifiedCount khác?

`updateMany` có thể trả:

~~~javascript
{
  matchedCount: 50,
  modifiedCount: 35
}
~~~

Điều này có thể xảy ra nếu 15 document đã có `needsReview: true`. Nó không tự chứng minh có 15 lỗi. Cần đối chiếu update operator và trạng thái trước đó.

### 15.3. Không có transaction toàn bộ chỉ từ updateMany

Tính atomic của cập nhật nằm ở từng document. Khi thao tác nhiều document, các cập nhật có thể diễn ra từng document; đừng giả định tất cả document cùng đổi trạng thái nguyên tử như một giao dịch chỉ vì dùng một lệnh `updateMany`. Nếu nghiệp vụ cần all-or-nothing giữa nhiều document, phải cân nhắc transaction và các giới hạn vận hành của môi trường.

## 16. Các trường hợp biên của filter

### 16.1. $ne và $nin có thể khớp field thiếu

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-200",
    status: { $ne: "SHIPPED" }
  },
  {
    $set: { readyForShipping: true }
  }
);
~~~

Nếu `status` thiếu, điều kiện `$ne` vẫn có thể khớp. Tương tự, `$nin` có thể khớp field thiếu. Khi nghiệp vụ yêu cầu trạng thái thuộc tập nhất định, hãy dùng `status: {$in:["PAID","READY"]}`.

### 16.2. null không giống missing

~~~javascript
{ status: null }
~~~

Trong MongoDB, điều kiện equality-null có ngữ nghĩa bao gồm field null và có thể cả field thiếu. Nếu muốn chỉ kiểm tra BSON Null, cân nhắc:

~~~javascript
{ status: { $type: "null" } }
~~~

Nếu muốn field bắt buộc tồn tại:

~~~javascript
{ status: { $exists: true } }
~~~

Nhưng `$exists: true` vẫn chấp nhận field bằng null. Có thể dùng `$type: "string"` hoặc ràng buộc schema nếu yêu cầu trạng thái là chuỗi.

### 16.3. Kiểu BSON phải phù hợp

~~~javascript
{ version: NumberInt(1) }
~~~

Nếu client gửi `"1"` dạng chuỗi, so sánh với version số sẽ không khớp. Với các kiểu số BSON, MongoDB có quy tắc so sánh số riêng, nhưng **string khác number** và **ObjectId khác string hex**.

Ở ranh giới API, parse/validate ID, số, ngày trước khi xây filter. Một no-match vì sai kiểu có thể trông giống xung đột trạng thái.

### 16.4. $or cần nhóm điều kiện chính xác

Ví dụ cho phép chuyển đơn từ `PAID` hoặc `READY`, nhưng luôn phải giữ `_id` và tenant:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    $or: [
      { status: "PAID" },
      { status: "READY" }
    ]
  },
  {
    $set: { status: "SHIPPED" }
  }
);
~~~

Ở đây `_id` và `tenantId` là các điều kiện AND với nhóm OR. Cách ngắn hơn là:

~~~javascript
{
  _id: "ord-100",
  tenantId: "tenant-A",
  status: { $in: ["PAID", "READY"] }
}
~~~

Không đặt một nhánh OR thiếu ràng buộc tenant, vì có thể khiến filter chấp nhận nhiều đối tượng ngoài ý định.

### 16.5. Điều kiện trống

~~~javascript
db.orders.updateOne(
  {},
  { $set: { accidentallyTouched: true } }
);
~~~

Filter `{}` có thể chọn một document bất kỳ trong phạm vi collection. Nếu bạn muốn cập nhật đúng một đơn, `{}` là điều kiện quá rộng.

Với `updateMany({}, ...)`, thao tác có thể ảnh hưởng toàn collection. Backend nên có guard ngăn lệnh ghi thiếu điều kiện định danh/phạm vi nếu API không chủ ý hỗ trợ thao tác toàn bộ.

### 16.6. Điều kiện không có index

Filter có thể chính xác về logic nhưng chậm khi collection lớn. Các filter theo `_id` tận dụng unique index mặc định. Nếu thường cập nhật theo khóa nghiệp vụ như `{tenantId, externalOrderId}`, cần cân nhắc unique compound index đúng đặc tả nghiệp vụ.

Không tự tạo quá nhiều index chỉ để phục vụ mọi điều kiện phụ `status`/`version`; hãy xem kế hoạch truy vấn và chi phí ghi/index thực tế.

## 17. Theo dõi kết quả cập nhật bằng MongoDB Compass

MongoDB Compass cho phép quan sát document, nhập filter trong tab Documents và sửa dữ liệu tùy phiên bản. Để học chính xác semantics của `updateOne` và đọc `matchedCount`/`modifiedCount`, nên chạy lệnh trong `mongosh` rồi kiểm tra kết quả trên Compass.

Quy trình:

1. Kết nối Compass đến cùng cluster/server dùng cho `mongosh`.
2. Chọn `conditional_update_lab` và collection `orders`.
3. Nhập filter:

   ~~~json
   {"_id":"ord-100","tenantId":"tenant-A","status":"PAID"}
   ~~~

4. Xem document trước khi cập nhật. Chạy lệnh `updateOne` chuyển trạng thái trong `mongosh`.
5. Refresh Documents; dùng filter chỉ gồm `_id` và `tenantId` để xem trạng thái sau cập nhật.
6. Giữ lại filter có `status: "PAID"` rồi refresh; nếu thao tác thành công, danh sách sẽ rỗng vì document không còn ở trạng thái cũ.
7. Thử lệnh version conflict trên `ord-200`, xác minh phiên bản mới trong Compass.
8. Mở collection `inventory`, quan sát `available` và `reserved` trước/sau ví dụ `$inc` có điều kiện.

**Điểm dễ nhầm:** Filter trong Compass không có kết quả sau cập nhật **không đồng nghĩa document bị xóa**. Nó có thể đơn giản là document không còn đáp ứng điều kiện status/version của filter đang mở.

Giao diện Compass có thể thay đổi theo phiên bản. Việc nhấn Edit Document và Save không nhất thiết gửi cùng lệnh `updateOne` mà bài học đang phân tích. Hãy đối chiếu dữ liệu trên server và kết quả mongosh thay vì suy luận từ vị trí một nút giao diện.

## 18. Java Driver: đọc kết quả và phân loại no-match

Ví dụ sử dụng MongoDB Java Driver với `Filters` và `Updates`:

~~~java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;
import static com.mongodb.client.model.Updates.set;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Date;

MongoCollection<Document> orders = database.getCollection("orders");

Bson filter = and(
    eq("_id", "ord-100"),
    eq("tenantId", "tenant-A"),
    eq("status", "PAID"),
    eq("version", 1)
);

Bson update = combine(
    set("status", "SHIPPED"),
    set("shippedAt", new Date()),
    inc("version", 1)
);

UpdateResult result = orders.updateOne(filter, update);

if (result.getMatchedCount() == 0) {
    System.out.println("No match: not found or precondition conflict");
} else if (result.getModifiedCount() == 0) {
    System.out.println("Matched, but no effective change");
} else {
    System.out.println("Updated successfully");
}
~~~

Đoạn mã giả định biến `database` là một `MongoDatabase` đã kết nối; đây là ví dụ phần logic thao tác, không phải chương trình Java độc lập có đầy đủ connection/try-with-resources.

Giải thích:

- Filter chứa `_id`, `tenantId`, `status` và `version`.
- Update vừa đổi trạng thái vừa tăng version.
- `getMatchedCount() == 0` chưa đủ để kết luận nguyên nhân cụ thể.
- Muốn phân loại sâu hơn, ứng dụng cần đọc có phạm vi quyền và xử lý race phù hợp.

### 18.1. Mẫu xử lý no-match có quyền truy cập

~~~java
if (result.getMatchedCount() == 0) {
    Document current = orders.find(
        and(
            eq("_id", "ord-100"),
            eq("tenantId", "tenant-A")
        )
    ).first();

    if (current == null) {
        // Không thấy trong phạm vi tenant được phép.
        // Trả về Not Found theo chính sách API.
    } else {
        // Document có tồn tại nhưng precondition không còn đúng.
        // Trả Conflict/Precondition Failed theo hợp đồng API.
    }
}
~~~

Kết quả truy vấn sau cập nhật là thông tin quan sát tại thời điểm mới; nếu có concurrent writes, nó không phải snapshot thời điểm của update ban đầu. Ứng dụng nên quyết định phản hồi sao cho nhất quán, không rò rỉ thông tin nhạy cảm, đồng thời ghi log có kiểm soát.

### 18.2. Ví dụ tồn kho có điều kiện trong Java

~~~java
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.inc;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

MongoCollection<Document> inventory = database.getCollection("inventory");

int requested = 3;

Bson stockFilter = and(
    eq("_id", "stock-BK-01"),
    eq("tenantId", "tenant-A"),
    gte("available", requested)
);

Bson stockUpdate = combine(
    inc("available", -requested),
    inc("reserved", requested),
    inc("version", 1)
);

UpdateResult stockResult = inventory.updateOne(stockFilter, stockUpdate);

if (stockResult.getMatchedCount() == 0) {
    // Không đủ hàng hoặc không thấy bản ghi kho theo phạm vi cho phép.
}
~~~

Không chuyển `stockResult.getMatchedCount() == 0` thành thông báo “hết hàng” một cách vô điều kiện vì SKU có thể không tồn tại hoặc tenant không đúng.

## 19. Lập kế hoạch index và quan sát truy vấn

Cách đơn giản để xem đường tìm kiếm của filter là dùng cùng điều kiện trong `find`:

~~~javascript
const filter = {
  _id: "ord-100",
  tenantId: "tenant-A",
  status: "PAID",
  version: NumberInt(1)
};

db.orders.find(filter).explain("executionStats");
~~~

Chú ý dữ liệu mẫu có rất ít document, vì vậy kết quả explain không đại diện cho hiệu năng ở production.

Các trường nên quan sát:

| Thuộc tính | Ý nghĩa |
|---|---|
| `winningPlan` | Kế hoạch truy vấn được chọn |
| `IXSCAN` | Có bước quét index |
| `COLLSCAN` | Quét collection |
| `totalKeysExamined` | Số key trong index được xét |
| `totalDocsExamined` | Số document được xét |
| `nReturned` | Số document khớp từ truy vấn `find` |

Filter theo `_id` thường có index hỗ trợ trực tiếp. Với cập nhật theo `tenantId`, `externalId` hoặc state machine của nhiều bản ghi, nên thiết kế index theo mẫu truy vấn thực và kiểm soát tính unique. Index tối ưu truy tìm document; nó **không thay thế** precondition trong filter.

Nếu dùng collation hoặc trường nhiều kiểu BSON, đảm bảo query và index có cấu hình so sánh tương thích.

## 20. Những lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể xảy ra | Cách xử lý |
|---|---|---|
| `matchedCount: 0` dù thấy document khi tìm theo ID | Filter trạng thái/version/tenant không khớp | Kiểm tra từng precondition, không bỏ điều kiện rồi retry mù |
| `modifiedCount: 0` nhưng `matchedCount: 1` | `$set` trùng giá trị, thao tác là no-op | Diễn giải theo hợp đồng API, không kết luận not found |
| Lệnh chuyển trạng thái chạy lại không khớp | Trạng thái đã chuyển khỏi giá trị cũ | Có thể là CAS hoạt động đúng |
| Filter theo version không khớp | Snapshot trên client đã cũ | Đọc lại, báo conflict hoặc merge có kiểm soát |
| Tồn kho trở thành âm | Trừ số không có precondition hoặc đường ghi khác bỏ qua kiểm soát | `available: {$gte: requested}` kết hợp `$inc`, schema/invariant nhất quán |
| Update chạm nhầm đơn khác | Filter chỉ theo status hoặc field không duy nhất | Thêm `_id`/unique key và tenant |
| Filter theo `$ne` vẫn chọn bản ghi thiếu field | `$ne`/`$nin` có thể khớp missing | Dùng allowlist `$in`, `$exists`/`$type` khi cần |
| Update array sửa dòng không mong muốn | Điều kiện trên mảng khớp chéo phần tử | Dùng `$elemMatch` và positional update đúng |
| `upsert:true` gây duplicate key | No-match do precondition, nhưng server cố insert | Tắt upsert cho state transition; thiết kế create riêng |
| `matchedCount` trước/sau đọc khác nhau | Dữ liệu thay đổi đồng thời | Hiểu các lệnh đọc là snapshot ở thời điểm khác; CAS/transaction nếu cần |
| Retry khiến số lượng bị trừ hai lần | `$inc` không idempotent theo yêu cầu nghiệp vụ | Idempotency key, deduplication và kiểm soát kết quả |
| Filter ObjectId dạng string không khớp | Sai kiểu BSON | Parse ID đúng kiểu |
| Update bị từ chối dù filter khớp | Schema validation, unique index, quyền hoặc lỗi khác | Phân tích exception riêng, không gọi là no-match |
| Cập nhật nhiều document nhưng chỉ một bản ghi thay đổi | Dùng `updateOne` khi cần `updateMany` | Xác định đúng phạm vi, có preview và ràng buộc an toàn |
| Gọi `updateMany` với filter `{}` | Filter rỗng khớp quá rộng | Guard ở tầng ứng dụng, giới hạn quyền và kiểm tra trước |

## 21. Bài tập thực hành có hướng dẫn

Trước mỗi bài nếu cần trạng thái chính xác như mô tả, hãy nạp lại dữ liệu mẫu ở mục 3. Không dùng database sản xuất.

### Bài 1. Chuyển trạng thái có điều kiện

Từ `ord-100` ở trạng thái `PAID`, thực hiện:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    status: "PAID"
  },
  {
    $set: {
      status: "SHIPPED",
      shippedAt: new Date()
    }
  }
);
~~~

**Câu hỏi:** Lần đầu `matchedCount` và `modifiedCount` thường bằng bao nhiêu? Nếu chạy lại nguyên lệnh ngay thì chúng thay đổi thế nào?

*Gợi ý:* Lần đầu thường là `1/1`, lần sau `0/0` vì precondition không còn đúng.

### Bài 2. Phân biệt no-match với no-op

Chạy trên `ord-300`:

~~~javascript
db.orders.updateOne(
  { _id: "ord-300", tenantId: "tenant-A" },
  { $set: { status: "SHIPPED" } }
);
~~~

Sau đó chạy:

~~~javascript
db.orders.updateOne(
  { _id: "ord-300", status: "PAID" },
  { $set: { status: "SHIPPED" } }
);
~~~

**Câu hỏi:** Vì sao câu đầu có thể là `matched=1, modified=0`, còn câu sau là `matched=0, modified=0`? Câu nào thực sự tìm thấy document?

### Bài 3. Filter phải giữ tenant

Thử:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-400",
    tenantId: "tenant-A",
    status: "PAID"
  },
  {
    $set: { needsReview: true }
  }
);
~~~

**Kỳ vọng:** `matchedCount: 0`. `ord-400` thuộc tenant khác. Vì sao truy vấn chẩn đoán trong API cũng phải giữ điều kiện tenant?

### Bài 4. Version conflict

Reset `ord-200` rồi chạy:

~~~javascript
const first = db.orders.updateOne(
  {
    _id: "ord-200",
    version: NumberInt(1)
  },
  {
    $set: { "shipping.city": "Hải Phòng" },
    $inc: { version: NumberInt(1) }
  }
);

const second = db.orders.updateOne(
  {
    _id: "ord-200",
    version: NumberInt(1)
  },
  {
    $set: { "shipping.city": "Cần Thơ" },
    $inc: { version: NumberInt(1) }
  }
);

printjson({ first, second });
~~~

**Kỳ vọng:** Lần đầu khớp, lần hai không khớp vì version đã tăng. Hãy giải thích cách client thông báo và xử lý xung đột.

### Bài 5. Giảm tồn kho đúng điều kiện

Sau khi nạp lại `stock-BK-01` có available = 8:

~~~javascript
db.inventory.updateOne(
  {
    _id: "stock-BK-01",
    available: { $gte: 3 }
  },
  {
    $inc: {
      available: -3,
      reserved: 3
    }
  }
);
~~~

**Kỳ vọng:** available = 5, reserved = 3.

Thử giảm tiếp 6:

~~~javascript
db.inventory.updateOne(
  {
    _id: "stock-BK-01",
    available: { $gte: 6 }
  },
  {
    $inc: {
      available: -6,
      reserved: 6
    }
  }
);
~~~

**Kỳ vọng:** Không khớp, available giữ nguyên 5. Vì sao phép kiểm tra tồn kho trước bằng `findOne` không đủ?

### Bài 6. Coupon hết hạn hoặc hết lượt

Chạy ba lần lệnh ở mục 10 trên coupon có `remainingUses = 2`. Phân tích kết quả `matchedCount` của từng lần. Nếu hết hạn trong lúc đang thực hành, reset coupon rồi chạy lại.

### Bài 7. Array cùng phần tử

Trên `ord-100` ban đầu, giảm quantity của SKU `BK-01` nếu còn ít nhất 1:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-100",
    lines: {
      $elemMatch: {
        sku: "BK-01",
        quantity: { $gte: 1 }
      }
    }
  },
  {
    $inc: { "lines.$.quantity": -1 }
  }
);
~~~

**Câu hỏi:** `$elemMatch` bảo vệ điều kiện nào? Khi nào nên dùng `arrayFilters`?

### Bài 8. Tránh upsert cho state transition

Giải thích rủi ro của lệnh:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-300",
    status: "PAID"
  },
  {
    $set: { status: "SHIPPED" }
  },
  {
    upsert: true
  }
);
~~~

**Gợi ý:** `ord-300` đang `SHIPPED`, filter không khớp. Upsert cố tạo document có cùng `_id` nên có thể vi phạm unique index. Hãy tắt upsert khi mục tiêu là chuyển trạng thái document hiện hữu.

### Bài 9. Chọn kết quả API

Giả sử một API cập nhật trả về:

| Kết quả | Cách giải thích |
|---|---|
| `matched=1, modified=1` | Có thay đổi |
| `matched=1, modified=0` | Khớp nhưng không thay đổi |
| `matched=0, upserted=0` | Không thỏa filter; cần phân loại |
| `upserted=1` | Đã chèn mới |
| Driver throw duplicate key | Vi phạm unique index hoặc race của upsert |
| Driver throw validation error | Document sau cập nhật không thỏa validator |

Hãy quyết định trường hợp nào cần xem là success, conflict hoặc lỗi dựa theo hợp đồng API. Không dùng một status code chung cho mọi kết quả `modifiedCount = 0`.

### Bài 10. Thiết kế filter theo yêu cầu

Viết filter cho các yêu cầu:

1. Đổi trạng thái đơn `ord-100` chỉ khi thuộc `tenant-A` và đang `PAID`.
2. Sửa địa chỉ `ord-200` chỉ khi `version = 1` và trạng thái `DRAFT`.
3. Giữ 4 sản phẩm `stock-BK-01` chỉ khi còn đủ available.
4. Dùng coupon `coupon-WELCOME` khi ACTIVE, chưa hết hạn và còn lượt.
5. Cập nhật dòng SKU `BK-01` của `ord-100` khi cùng phần tử có quantity ≥ 2.
6. Đánh dấu các đơn DRAFT của `tenant-A` để rà soát nhưng không đụng tenant khác.

**Mẫu tư duy:**

~~~text
Tôi muốn cập nhật đối tượng nào?
    ↓
Định danh nào là duy nhất và đúng tenant?
    ↓
Trạng thái/version/điều kiện số nào phải đúng NGAY KHI GHI?
    ↓
Toán tử cập nhật nào tránh ghi đè và giảm nguy cơ race?
    ↓
matchedCount / modifiedCount / upsertedCount phải được xử lý thế nào?
    ↓
Nếu không khớp, có được retry không, hay phải báo conflict?
~~~

## 22. Ghi nhớ khi áp dụng vào hệ thống thực

- **Filter là precondition:** đặt `_id`, tenant, status, version và điều kiện số ngay trong lệnh cập nhật thay vì chỉ kiểm tra bằng `findOne` rồi ghi vô điều kiện.
- **Một document được cập nhật atomic:** sử dụng `$inc`, `$set` và bộ lọc nhất quán để bảo vệ quy tắc trong phạm vi document; không nhầm với transaction nhiều document.
- **Đọc đúng kết quả:** `matchedCount = 0` không đồng nghĩa document không tồn tại; `modifiedCount = 0` không đồng nghĩa lỗi.
- **Không nới filter khi không khớp:** điều kiện thất bại phải được đưa vào xử lý nghiệp vụ, không tự bỏ status hoặc version để “cố cập nhật cho được”.
- **Sử dụng allowlist rõ ràng:** `$ne`/`$nin` có thể khớp field thiếu; khi chỉ một vài trạng thái hợp lệ, `$in` dễ kiểm soát hơn.
- **Cẩn trọng với upsert:** no-match do precondition khác hoàn toàn no-match vì chưa có bản ghi cần tạo.
- **Bảo vệ cạnh tranh:** version/CAS chỉ phát huy tác dụng nếu mọi luồng ghi tuân thủ cùng giao thức.
- **Xử lý retry riêng:** `$set` một giá trị và `$inc` một bộ đếm có tính lặp lại khác nhau; cân nhắc idempotency key đối với hành động tài chính, tồn kho và tác động bên ngoài.
- **Đo và quan sát:** dùng mongosh, Compass, logs và explain để xác minh dữ liệu, điều kiện lọc và kế hoạch truy vấn; luôn giữ phạm vi quyền truy cập.

Thiết kế tốt bộ lọc cập nhật có điều kiện giúp MongoDB thực hiện **đúng hành động, đúng document và đúng trạng thái**. Việc diễn giải kết quả không khớp một cách tường minh giúp hệ thống phân biệt xung đột hợp lệ với lỗi thật, tránh ghi đè dữ liệu và giữ nhất quán khi nhiều tác nhân thao tác đồng thời.
