# Xóa mềm, xóa vật lý và tác động đến truy vấn, unique index

Trong MongoDB, “xóa một document” có thể mang ít nhất hai ý nghĩa khác nhau:

- **Xóa vật lý (hard delete):** loại document khỏi collection bằng `deleteOne()`, `deleteMany()` hoặc thao tác xóa tương ứng. Document không còn được truy vấn từ collection đó.
- **Xóa mềm (soft delete):** **không xóa document**, mà cập nhật trạng thái như `isDeleted: true` hoặc ghi `deletedAt`. Ứng dụng chỉ xem những document còn hiệu lực là đang tồn tại.

Hai cách này khác nhau về cách khôi phục, dung lượng lưu trữ, truy vấn, index, xử lý quan hệ, audit và đặc biệt là **ràng buộc duy nhất (unique index)**. Một document được xóa mềm vẫn là document thật trong collection. Vì vậy, nếu có unique index thông thường trên `emailNormalized`, giá trị email của bản ghi đã xóa mềm **vẫn có thể chặn việc đăng ký tài khoản mới cùng email**.

Bài học đi từ mô hình dữ liệu, câu lệnh xóa, câu lệnh lọc, thiết kế unique index đến quy trình xóa vật lý sau thời gian lưu giữ. Các ví dụ sử dụng `mongosh` với giả định ứng dụng đa tenant và cần tránh lộ bản ghi đã xóa qua API.

## 1. Nhìn tổng thể: xóa mềm hay xóa vật lý?

Giả sử collection `users` có document:

```javascript
{
  _id: ObjectId("65a12f010000000000000001"),
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  displayName: "An",
  role: "MEMBER",
  isDeleted: false,
  createdAt: ISODate("2026-02-01T09:00:00Z"),
  updatedAt: ISODate("2026-02-01T09:00:00Z")
}
```

Sau **xóa mềm**, document vẫn tồn tại, nhưng có thêm metadata xóa:

```javascript
{
  _id: ObjectId("65a12f010000000000000001"),
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  displayName: "An",
  role: "MEMBER",
  isDeleted: true,
  deletedAt: ISODate("2026-06-15T10:30:00Z"),
  deletedBy: "admin-42",
  createdAt: ISODate("2026-02-01T09:00:00Z"),
  updatedAt: ISODate("2026-06-15T10:30:00Z")
}
```

Nếu dùng **xóa vật lý**, document trên không còn được trả về từ collection `users`, kể cả truy vấn quản trị không lọc `isDeleted`.

| Khía cạnh | Xóa mềm | Xóa vật lý |
|---|---|---|
| Document còn trong collection? | Có | Không, sau khi xóa thành công |
| Có thể đọc lại từ collection? | Có, nếu query cho phép | Không |
| Có thể khôi phục bản ghi dễ dàng? | Có thể chuyển trạng thái, nhưng cần kiểm tra conflict | Cần nguồn backup, audit hoặc tái tạo nếu có |
| Dung lượng dữ liệu và index | Vẫn chiếm tài nguyên ở mức tương ứng | Record và index entries được loại; kích thước file trên OS có thể chưa giảm ngay |
| Truy vấn thông thường | Phải lọc document active | Không cần lọc theo cờ đã xóa vì document không còn |
| Unique index thông thường | Bản ghi soft-deleted vẫn tham gia | Giá trị unique được giải phóng sau khi xóa thành công |
| Audit | Giữ được một phần thông tin ngay trong document | Muốn lịch sử cần lưu riêng |
| Tuân thủ chính sách xóa dữ liệu | Có thể không đủ vì dữ liệu vẫn lưu | Cần xét backup, replica, log và retention, không chỉ thao tác delete |

**Không có lựa chọn luôn tốt hơn.** Tài khoản có thời gian khôi phục 30 ngày có thể hợp lý với soft delete. Dữ liệu nhạy cảm đã hết thời hạn lưu giữ có thể đòi hỏi hard delete hoặc quy trình xóa sâu hơn. Log theo TTL, chứng từ có nghĩa vụ lưu giữ, giao dịch tài chính và dữ liệu người dùng có thể cần những chính sách hoàn toàn khác nhau.

## 2. Mô hình xóa mềm: chọn một hợp đồng trạng thái nhất quán

Có nhiều kiểu biểu diễn soft delete:

### 2.1. Cờ `isDeleted`

```javascript
{
  _id: "U101",
  emailNormalized: "an@example.com",
  isDeleted: false
}
```

Ưu điểm: điều kiện active ngắn gọn `{ isDeleted: false }`. Nhược điểm: chỉ có Boolean chưa biết **ai xóa và xóa khi nào**.

### 2.2. Dấu thời gian `deletedAt`

```javascript
{
  _id: "U101",
  emailNormalized: "an@example.com",
  deletedAt: null
}
```

Bản ghi được xóa mềm bằng cách gán `deletedAt` thành BSON Date. Ưu điểm: ghi lại mốc thời gian xóa và có thể làm cơ sở cho chính sách lưu giữ. Tuy nhiên, điều kiện `{ deletedAt: null }` trong MongoDB khớp cả trường `null` và trường **không tồn tại**, nên cần hiểu rõ dữ liệu legacy.

### 2.3. Kết hợp cờ và metadata

Mô hình đề xuất cho những ví dụ trong bài:

```javascript
{
  _id: "U101",
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  displayName: "An",
  isDeleted: false,
  createdAt: ISODate("2026-02-01T09:00:00Z"),
  updatedAt: ISODate("2026-02-01T09:00:00Z")
}
```

Khi xóa, đặt:

```javascript
{
  isDeleted: true,
  deletedAt: ISODate("2026-06-15T10:30:00Z"),
  deletedBy: "admin-42"
}
```

Cách tổ chức này giúp **active query và partial unique index dùng cùng điều kiện rõ ràng `isDeleted: false`**, đồng thời ghi lại metadata để khôi phục, audit hoặc chuyển sang xóa vật lý sau thời gian lưu giữ.

Đổi lại, ứng dụng phải giữ những trường **đồng bộ về nghĩa**. Nếu `isDeleted: false` nhưng `deletedAt` vẫn có ngày xóa, hệ thống dễ sinh cách hiểu khác nhau giữa các endpoint. Có thể chọn một trường làm **nguồn trạng thái chuẩn** (ở đây là `isDeleted`) và ràng buộc quy tắc cập nhật/validation để giảm trường hợp mâu thuẫn.

### 2.4. Vì sao phải quan tâm field missing?

Nếu collection cũ chưa có `isDeleted`:

```javascript
{ _id: "U100", emailNormalized: "old@example.com" }
```

thì truy vấn:

```javascript
db.users.find({ isDeleted: false });
```

sẽ **không** tự hiểu mọi document thiếu `isDeleted` là active. Điều này có thể làm tài khoản cũ “biến mất” khỏi API sau khi triển khai filter mới.

Có hai hướng: migration đưa tất cả bản ghi active cũ về `isDeleted: false`, hoặc định nghĩa một predicate tương thích dữ liệu cũ. Với hệ thống cần **partial unique index**, migration về một biểu diễn active nhất quán thường đơn giản, dễ vận hành hơn.

## 3. Xóa vật lý bằng `deleteOne()` và `deleteMany()`

### 3.1. `deleteOne()`: xóa một document phù hợp

```javascript
const result = db.users.deleteOne({
  _id: "U101",
  tenantId: "TENANT-A"
});

print(result.deletedCount);
```

Lệnh xóa tối đa **một** document khớp filter; `deletedCount` thường là `0` hoặc `1`. Trường hợp `0` có thể do ID không tồn tại, sai tenant hoặc document đã bị xóa trước đó.

Nên lọc theo định danh duy nhất và **scope quyền truy cập**. Nếu hệ thống đa tenant, chỉ đưa `_id` vào filter có thể không đủ để biểu đạt biên phân quyền tại tầng truy cập dữ liệu.

### 3.2. `deleteMany()`: xóa nhiều document phù hợp

```javascript
const result = db.sessions.deleteMany({
  tenantId: "TENANT-A",
  expiresAt: { $lt: ISODate("2026-04-01T00:00:00Z") }
});

print(result.deletedCount);
```

`deleteMany()` xóa tất cả document thỏa điều kiện tại thời điểm xử lý tương ứng, theo semantics MongoDB. Nếu dùng filter `{}`, có thể xóa **toàn bộ document trong collection**:

```javascript
// Nguy hiểm: xóa toàn bộ document trong collection.
db.users.deleteMany({});
```

Không chạy lệnh này trên dữ liệu production nếu không có kế hoạch cụ thể. Các lệnh xóa hàng loạt nên có scope rõ như `tenantId`, loại dữ liệu, thời điểm và tiêu chí trạng thái; ứng dụng cần log số document dự kiến/xóa thực tế và quyền thực thi.

### 3.3. Xóa vật lý không giống `drop()`

| Thao tác | Tác động chính |
|---|---|
| `deleteOne(filter)` | Xóa tối đa một document |
| `deleteMany(filter)` | Xóa những document khớp filter |
| `deleteMany({})` | Xóa tất cả document trong collection nhưng giữ collection/index |
| `drop()` | Xóa toàn bộ collection và các index của nó |

Không dùng `drop()` thay cho “xóa toàn bộ dữ liệu thử rồi tiếp tục nhập vào cùng collection” nếu cần giữ lại index, validator hoặc cấu hình collection. Trong các môi trường production, thao tác drop có hậu quả lớn và quy trình phân quyền/backup riêng.

### 3.4. Xóa vật lý và không gian lưu trữ WiredTiger

Khi hard delete thành công, các record và index entries liên quan được loại khỏi cấu trúc dữ liệu logic. Tuy nhiên, không nên kỳ vọng dung lượng tệp `.wt` trên filesystem giảm đúng bằng kích thước document đã xóa ngay lập tức: WiredTiger có thể **giữ và tái sử dụng vùng trống**. Việc thu hồi dung lượng về hệ điều hành là chủ đề vận hành khác và tùy thuộc phiên bản, filesystem, cơ chế compact/resync, workload.

Đồng thời, hard delete không tự động có nghĩa dữ liệu đã biến mất khỏi mọi **backup, snapshot, bản sao hoặc hệ thống downstream**. Chính sách xóa dữ liệu cần bao gồm cả những nơi đó khi có yêu cầu pháp lý/bảo mật.

## 4. Xóa mềm bằng `updateOne()`: giữ document, đổi trạng thái

Một lệnh xóa mềm nên làm tối thiểu ba việc trong **cùng update trên document**:

1. Chỉ nhắm vào document active đúng tenant/định danh.
2. Đặt `isDeleted: true`.
3. Ghi metadata xóa như `deletedAt` và `deletedBy`.

Ví dụ:

```javascript
const result = db.users.updateOne(
  {
    _id: "U101",
    tenantId: "TENANT-A",
    isDeleted: false
  },
  {
    $set: {
      isDeleted: true,
      deletedBy: "admin-42"
    },
    $currentDate: {
      deletedAt: true,
      updatedAt: true
    }
  }
);

printjson({
  matched: result.matchedCount,
  modified: result.modifiedCount
});
```

Nếu document được xóa mềm lần đầu, `matchedCount`/`modifiedCount` thường bằng `1`. Nếu lệnh lặp lại sau khi `isDeleted` đã thành `true`, filter `isDeleted: false` không còn khớp và kết quả thường bằng `0`. Điều này giúp tránh cập nhật lại `deletedAt` do request retry thông thường.

**Điều kiện trong filter là một phần của bảo vệ concurrency.** Nếu client đọc `isDeleted: false` rồi mới gửi một lệnh update chỉ dựa trên `_id`, nó có thể vô tình ghi đè trạng thái của một yêu cầu khác diễn ra giữa hai bước.

### 4.1. Xóa mềm hàng loạt

```javascript
const result = db.users.updateMany(
  {
    tenantId: "TENANT-A",
    isDeleted: false,
    inactiveSince: { $lt: ISODate("2025-01-01T00:00:00Z") }
  },
  {
    $set: {
      isDeleted: true,
      deletedBy: "retention-job"
    },
    $currentDate: { deletedAt: true, updatedAt: true }
  }
);

printjson({
  matched: result.matchedCount,
  modified: result.modifiedCount
});
```

`updateMany()` áp dụng thay đổi ở mức nhiều document. **Mỗi update trên một document là nguyên tử**, nhưng cả lô không mặc nhiên là một transaction all-or-nothing. Nếu gặp lỗi giữa chừng hoặc có thay đổi đồng thời, có thể còn những document chưa cập nhật; cần quản lý job bằng log, retry và thống kê.

Nếu cần cập nhật record cha và nhiều record con có ràng buộc nhất quán tức thời, cân nhắc transaction phù hợp hoặc thiết kế cơ chế propagation có trạng thái trung gian rõ ràng.

### 4.2. Xóa mềm khác với đổi trạng thái nghiệp vụ

Không phải mọi `status: "INACTIVE"` đều là soft delete. Một user có thể tạm khóa tài khoản, còn đơn hàng có thể bị hủy nhưng **vẫn phải được giữ** để phục vụ kế toán. Nếu gộp “bị khóa”, “đã hủy”, “đang lưu trữ” và “đã xóa” thành một Boolean, nhiều nghiệp vụ sẽ khó phân biệt.

Có thể thiết kế độc lập:

```javascript
{
  _id: "U101",
  accountStatus: "SUSPENDED", // trạng thái nghiệp vụ
  isDeleted: false,          // trạng thái tồn tại logic
  deletedAt: null
}
```

Trong một số ứng dụng, state machine với `status: "ACTIVE" | "DELETED" | "ARCHIVED"` tốt hơn cờ Boolean, nhưng khi thiết kế index phải dùng đúng điều kiện tương ứng và đảm bảo mọi luồng ghi nhất quán.

## 5. Tác động đến truy vấn: document xóa mềm vẫn được tìm thấy nếu quên lọc

Đây là khác biệt vận hành lớn nhất giữa soft delete và hard delete:

```javascript
db.users.find({ tenantId: "TENANT-A" });
```

Truy vấn trên **trả cả active lẫn soft-deleted users**, trừ khi có một tầng kiểm soát tự động khác thật sự áp dụng filter. MongoDB không có cơ chế mặc định “tự ẩn document có `isDeleted: true`” cho mọi câu lệnh.

### 5.1. Truy vấn active

```javascript
db.users.find({
  tenantId: "TENANT-A",
  isDeleted: false
});
```

Nếu cần lấy một user theo email:

```javascript
db.users.findOne({
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  isDeleted: false
});
```

Nếu cần tìm trong các document đã xóa để quản trị:

```javascript
db.users.find({
  tenantId: "TENANT-A",
  isDeleted: true
}).sort({ deletedAt: -1, _id: 1 });
```

Nên tách **API cho người dùng** với **API thùng rác/admin** để tránh một option thiếu kiểm soát như `includeDeleted=true` làm lộ dữ liệu.

### 5.2. `countDocuments()` và phân trang

Nếu dashboard hiển thị số tài khoản active, không nên đếm mọi document:

```javascript
// Có thể bao gồm cả tài khoản xóa mềm.
db.users.countDocuments({ tenantId: "TENANT-A" });

// Chỉ đếm tài khoản đang còn hiệu lực.
db.users.countDocuments({
  tenantId: "TENANT-A",
  isDeleted: false
});
```

Tương tự, truy vấn phân trang cần đưa điều kiện active vào filter **trước khi tính toán số trang**, để không tạo ra những trang ít hoặc rỗng sau khi tầng ứng dụng lọc bỏ các document deleted.

```javascript
db.users.find({
  tenantId: "TENANT-A",
  isDeleted: false
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Nếu đang sử dụng cursor pagination, khóa sort và filter phải được giữ nhất quán qua các trang. Soft delete giữa các lần tải trang có thể khiến số kết quả biến động; không nên hứa kết quả là snapshot bất biến nếu không có cơ chế đọc phù hợp.

### 5.3. Aggregation không tự thêm filter soft delete

Ví dụ thống kê user active theo vai trò:

```javascript
db.users.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      isDeleted: false
    }
  },
  {
    $group: {
      _id: "$role",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

Nếu bỏ `isDeleted: false` khỏi `$match`, những user xóa mềm vẫn có thể được tính vào báo cáo. Đặt `$match` phù hợp ở đầu pipeline thường có lợi để giới hạn tập dữ liệu trước khi group/sort/join.

### 5.4. `$lookup`: đừng chỉ lọc collection cha

Giả sử `orders` tham chiếu `customers`. Ngay cả khi chỉ lấy order active, truy vấn join vẫn có thể đưa vào khách hàng đã xóa mềm nếu pipeline lookup không lọc đúng:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      isDeleted: false
    }
  },
  {
    $lookup: {
      from: "customers",
      let: {
        customerId: "$customerId",
        tenant: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$customerId"] },
                { $eq: ["$tenantId", "$$tenant"] }
              ]
            }
          }
        },
        { $match: { isDeleted: false } },
        { $project: { _id: 1, displayName: 1 } }
      ],
      as: "customer"
    }
  }
]);
```

Ở đây cả phía `orders` và `customers` đều được giới hạn theo trạng thái/tenant theo chính sách truy cập. Truy vấn có thể cần đánh giá lại semantics nếu đơn hàng lịch sử **phải giữ snapshot tên khách tại thời điểm mua**, ngay cả khi customer hiện đã bị xóa mềm. Khi đó, một snapshot được phép lưu hợp lệ ở order có thể thích hợp hơn join live vào user.

### 5.5. Cập nhật và xóa vật lý cũng phải tôn trọng trạng thái

Một lỗi điển hình:

```javascript
// Có thể cập nhật cả document đã xóa mềm.
db.users.updateOne(
  { _id: "U101" },
  { $set: { displayName: "Tên mới" } }
);
```

Đối với API người dùng thông thường, nên dùng:

```javascript
db.users.updateOne(
  {
    _id: "U101",
    tenantId: "TENANT-A",
    isDeleted: false
  },
  { $set: { displayName: "Tên mới" } }
);
```

Không chỉ `find()` mà cả `updateOne()`, `replaceOne()`, `countDocuments()`, `aggregate()` và những code path xuất dữ liệu cũng phải hiểu trạng thái xóa. Một repository helper chung hoặc lớp dịch vụ kiểm soát chính sách có thể giảm việc quên filter, nhưng cần phân biệt rõ query active với tác vụ quản trị intentionally xem các bản ghi deleted.

## 6. Unique index thông thường: xóa mềm không giải phóng khóa

Đây là tình huống thường gây lỗi khi áp dụng soft delete cho email, username, slug, mã sản phẩm hoặc mã đơn.

Giả sử tạo unique index:

```javascript
db.users.createIndex(
  { emailNormalized: 1 },
  { unique: true }
);
```

Bản ghi ban đầu:

```javascript
{
  _id: "U101",
  emailNormalized: "an@example.com",
  isDeleted: false
}
```

Ứng dụng xóa mềm:

```javascript
db.users.updateOne(
  { _id: "U101" },
  {
    $set: { isDeleted: true },
    $currentDate: { deletedAt: true }
  }
);
```

Sau đó thử tạo user mới cùng email:

```javascript
db.users.insertOne({
  _id: "U202",
  emailNormalized: "an@example.com",
  isDeleted: false
});
```

**Lệnh insert vẫn vi phạm unique index**, thường báo lỗi `E11000 duplicate key error`. Lý do: unique index thông thường vẫn lập chỉ mục document `U101` vì nó **chưa bị xóa vật lý**.

Không có quy tắc MongoDB rằng `isDeleted: true` tự khiến record biến mất khỏi unique index. Tình huống này không phụ thuộc việc API có lọc active hay không: **ràng buộc duy nhất được áp dụng tại database khi ghi**, không phải từ danh sách kết quả của một truy vấn.

### 6.1. Unique index đơn trường và giá trị thiếu/null

Trong unique index đơn trường thông thường, trường unique thiếu hoặc `null` được biểu diễn theo quy tắc index tương ứng; nhiều document thiếu field hoặc có `null` có thể gây trùng khóa unique. Nếu nghiệp vụ chỉ yêu cầu giá trị duy nhất khi field có giá trị, cần cân nhắc partial index, schema validation hoặc thiết kế khác.

Đừng cho rằng “chưa nhập email” mặc định cho phép vô hạn record trong một unique index đơn trường trên email.

### 6.2. Thêm `isDeleted` vào unique compound index có đủ không?

Một ý tưởng thường thấy:

```javascript
db.users.createIndex(
  { emailNormalized: 1, isDeleted: 1 },
  { unique: true }
);
```

Index này cho phép một email xuất hiện một lần với `isDeleted: false` và một lần với `isDeleted: true`. Tuy nhiên nó **không cho phép nhiều bản ghi soft-deleted cùng email**: sau khi user đầu tiên bị xóa mềm, user thứ hai cùng email được tạo rồi xóa mềm, cả hai cùng tạo khóa `("an@example.com", true)` và xung đột.

Vì vậy, compound unique `{ emailNormalized, isDeleted }` **không tương đương** với quy tắc “chỉ email của user còn hiệu lực phải duy nhất”. Nó có thể phù hợp với một nghiệp vụ đặc biệt, nhưng thường không phải lựa chọn tốt cho soft delete có khả năng tái sử dụng identifier nhiều lần.

## 7. Partial unique index: chỉ ràng buộc duy nhất cho document active

Để cho phép tạo tài khoản mới với email của tài khoản đã xóa mềm, nhưng vẫn bảo đảm **không có hai user active cùng email**, dùng **partial unique index**:

```javascript
db.users.createIndex(
  { emailNormalized: 1 },
  {
    unique: true,
    partialFilterExpression: { isDeleted: false }
  }
);
```

Ý nghĩa:

- Chỉ document thỏa `isDeleted: false` được đưa vào **unique index này**.
- Hai user active không được có cùng `emailNormalized`.
- Document `isDeleted: true` không tham gia ràng buộc của index này.
- Có thể có nhiều document deleted dùng lại cùng email, miễn những ràng buộc khác không ngăn chúng.
- Khi restore một document thành `isDeleted: false`, unique constraint được kiểm tra lại.

**Quan trọng:** Nếu collection vẫn còn **một unique index cũ** trên `emailNormalized` không có partial filter, index cũ **tiếp tục chặn trùng email** dù bạn đã tạo thêm partial unique index. Cần lập kế hoạch chuyển đổi index, không chỉ thêm index mới rồi kỳ vọng mọi ràng buộc cũ biến mất.

### 7.1. Unique trong hệ thống đa tenant

Nếu email được phép lặp giữa các tenant nhưng phải duy nhất trong từng tenant, đưa tenant vào index:

```javascript
db.users.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  {
    name: "uniq_active_email_per_tenant",
    unique: true,
    partialFilterExpression: {
      isDeleted: false
    }
  }
);
```

Quy tắc:

- Trong `TENANT-A`, hai user active không thể cùng `an@example.com`.
- `TENANT-B` có thể có user active cùng email.
- Nhiều user soft-deleted của cùng tenant có thể giữ lịch sử dùng email.
- Mỗi thao tác đọc/ghi theo email nên xác định **tenantId** và `isDeleted: false` theo đúng ranh giới nghiệp vụ.

Ví dụ insert:

```javascript
db.users.insertMany([
  {
    _id: "U-A1",
    tenantId: "TENANT-A",
    emailNormalized: "an@example.com",
    isDeleted: false
  },
  {
    _id: "U-B1",
    tenantId: "TENANT-B",
    emailNormalized: "an@example.com",
    isDeleted: false
  }
]);
```

Hai document trên thỏa partial unique index theo tenant.

### 7.2. Query phải hàm ý điều kiện của partial index

Partial index chỉ chứa các document thỏa filter của index. MongoDB query planner chỉ có thể dùng nó cho truy vấn mà việc dùng index **không làm thiếu kết quả**, nghĩa là query cần có điều kiện tương thích/hàm ý partial filter tương ứng.

Ví dụ:

```javascript
// Có thể tận dụng partial index trên active users.
db.users.findOne({
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  isDeleted: false
});
```

Ngược lại:

```javascript
// Muốn tìm cả active và deleted, không thể chỉ dựa
// vào index vốn loại bỏ deleted users.
db.users.find({
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com"
});
```

Planner có thể chọn collection scan hoặc index khác nếu phù hợp. Partial index dùng để giảm dung lượng/index maintenance cho một tập con có ý nghĩa, nhưng **không thể thay thế mọi index** cho các truy vấn bao gồm cả dữ liệu đã xóa.

### 7.3. Vì sao dùng `isDeleted: false` thay cho `deletedAt: { $exists: false }`?

MongoDB hỗ trợ những biểu thức nhất định trong `partialFilterExpression`, ví dụ equality, một số phép so sánh, `$type`, `$in` và `$exists: true` theo các phiên bản được hỗ trợ. **Không nên giả định `$exists: false` được phép trong partial filter**; đây không phải lựa chọn chung được hỗ trợ như `$exists: true`.

Với quy tắc active `isDeleted: false`, partial index dễ định nghĩa và dễ truy vấn. Nếu chọn `deletedAt: null` làm active, cần chú ý equality với `null` có thể khớp cả document **thiếu trường**, và việc viết filter/index/truy vấn phải có semantics thống nhất. Đừng trộn nhiều cách biểu diễn active trên cùng collection mà không migration.

### 7.4. Normalization và collation cho unique identifier

Đối với email hoặc username, `"An@Example.com"` và `"an@example.com"` có được xem là trùng hay không phụ thuộc chính sách nghiệp vụ và cách tạo index/collation.

Một cách phổ biến là lưu trường chuẩn hóa:

```javascript
{
  email: "An@Example.com",
  emailNormalized: "an@example.com",
  isDeleted: false
}
```

Ứng dụng cần chuẩn hóa theo quy tắc được chốt cho sản phẩm. Không nên tùy tiện biến đổi mọi địa chỉ email phức tạp bằng một hàm không phù hợp với chính sách xác định danh tính. Có thể thiết kế unique index với collation tương thích khi muốn so sánh chuỗi không phân biệt hoa/thường, nhưng cả truy vấn lẫn index phải hiểu cùng quy tắc collation.

**Partial unique index và collation giải quyết hai vấn đề khác nhau:** partial filter quyết định **document nào tham gia ràng buộc**, còn collation quyết định **khóa String được so sánh như thế nào**.

### 7.5. Sharding và unique index

Trong sharded collection, unique index chịu các ràng buộc với **shard key** và phiên bản triển khai. Một unique index không chứa shard key cần thiết có thể không được phép tạo hoặc không bảo đảm uniqueness toàn cluster theo ý định.

Ví dụ muốn unique email theo tenant trên sharded collection cần đánh giá shard key và dạng index hợp lệ; đừng mặc định một partial unique index kiểu standalone hoạt động giống hệt trên mọi topology. Unique constraint cũng không phải giải pháp thay thế thiết kế shard key phân tải phù hợp.

## 8. Điều gì xảy ra khi xóa mềm rồi đăng ký lại cùng email?

Đây là kịch bản cốt lõi để kiểm tra partial unique index.

**Bước 1 — Có user active cũ:**

```javascript
{
  _id: "U101",
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  isDeleted: false
}
```

**Bước 2 — Xóa mềm U101:**

```javascript
db.users.updateOne(
  {
    _id: "U101",
    tenantId: "TENANT-A",
    isDeleted: false
  },
  {
    $set: { isDeleted: true, deletedBy: "admin-42" },
    $currentDate: { deletedAt: true }
  }
);
```

**Bước 3 — Tạo tài khoản mới U202 cùng email:**

```javascript
db.users.insertOne({
  _id: "U202",
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  isDeleted: false
});
```

Nếu chỉ có partial unique index active phù hợp (và không có unique index khác chặn), bước 3 có thể thành công vì U101 đã rời tập khóa active.

**Bước 4 — Thử khôi phục U101:**

```javascript
db.users.updateOne(
  {
    _id: "U101",
    tenantId: "TENANT-A",
    isDeleted: true
  },
  {
    $set: { isDeleted: false },
    $unset: { deletedAt: "", deletedBy: "" }
  }
);
```

Lệnh restore **không thể thành công** nếu sẽ tạo hai user active cùng email trong tenant. MongoDB áp dụng unique constraint khi U101 quay trở lại vùng `isDeleted: false`, và có thể báo duplicate key.

Đây không phải lỗi của partial index; chính index đang bảo vệ invariant nghiệp vụ. Ứng dụng cần một chính sách restore:

1. **Không restore** nếu email đã được một tài khoản active khác sử dụng.
2. **Yêu cầu chọn identifier mới**, đồng thời xác minh quyền sở hữu.
3. **Hợp nhất tài khoản** theo quy trình được phê duyệt, thay vì ghi đè user mới.
4. **Giữ identifier được đặt trước** trong thời gian grace period nếu chính sách sản phẩm không cho tái sử dụng ngay sau xóa mềm.

Không nên tự động xóa U202 để khôi phục U101: đó là hành động có thể mất dữ liệu và sai quyền sở hữu.

### 8.1. Race condition: hai request tạo cùng email

Hai request có thể cùng chạy:

```javascript
db.users.findOne({
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  isDeleted: false
});
```

Cả hai cùng không thấy user active rồi cùng `insertOne()`. **Kiểm tra tồn tại trước insert không đủ bảo đảm uniqueness**. Partial unique index ở database là lớp bảo vệ cuối cùng: một insert có thể thành công, insert còn lại có thể nhận duplicate key. Ứng dụng phải bắt lỗi và chuyển thành thông báo nghiệp vụ phù hợp.

Tương tự, đồng thời giữa **đăng ký lại** và **restore** cũng được unique index phân xử theo trạng thái các thao tác thực sự được ghi.

## 9. Xóa mềm ảnh hưởng index và hiệu năng thế nào?

Soft delete thay đổi bản ghi nhưng không xóa nó. Hậu quả:

- Dữ liệu và metadata của document vẫn chiếm không gian trong collection.
- Những **index thông thường** trên field của document vẫn có mục tương ứng.
- **Partial index active** có thể loại document khỏi cấu trúc index khi `isDeleted` chuyển sang `true`.
- Việc cập nhật `isDeleted`, `deletedAt` và index liên quan vẫn phát sinh I/O, log, replication và chi phí quản lý version/page.
- Truy vấn không có filter soft delete có thể quét nhiều document không còn hữu ích về mặt nghiệp vụ.

### 9.1. Index cho danh sách active

Ví dụ API liệt kê user active theo thời điểm tạo:

```javascript
db.users.createIndex(
  {
    tenantId: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_active_users_by_created",
    partialFilterExpression: { isDeleted: false }
  }
);

db.users.find({
  tenantId: "TENANT-A",
  isDeleted: false
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Index chỉ chứa user active nên có thể giúp giảm kích thước và chi phí duyệt đối với truy vấn thường xuyên của ứng dụng, nhất là khi tỷ lệ deleted lớn. Tùy số lượng dữ liệu, query planner và các index khác, MongoDB vẫn có thể chọn plan khác.

### 9.2. Index cho khu vực quản trị deleted

Một index chỉ active **không giúp liệt kê deleted users** theo thời gian xóa. Nếu workload quản trị thường xuyên cần trang “thùng rác”, có thể tạo index riêng:

```javascript
db.users.createIndex(
  {
    tenantId: 1,
    deletedAt: -1,
    _id: -1
  },
  {
    name: "idx_deleted_users",
    partialFilterExpression: { isDeleted: true }
  }
);

db.users.find({
  tenantId: "TENANT-A",
  isDeleted: true
})
.sort({ deletedAt: -1, _id: -1 })
.limit(20);
```

Không phải hệ thống nào cũng cần index này. Mỗi index đều tốn dung lượng và chi phí duy trì khi insert/update/delete; nên dựa vào tần suất truy vấn và `explain("executionStats")`.

### 9.3. Vì sao composite index với cờ xóa không phải luôn tối ưu?

Một index như:

```javascript
db.users.createIndex({
  tenantId: 1,
  isDeleted: 1,
  createdAt: -1
});
```

có thể phục vụ cả query active và deleted trong một số workload. Nhưng nó vẫn giữ khóa cho **cả hai trạng thái**, khác partial index chỉ chứa active. Việc chọn composite hay partial phụ thuộc phân bố dữ liệu, query pattern, yêu cầu unique, số index và chi phí ghi. Không có công thức “partial index luôn nhanh hơn”.

Đặc biệt, index dùng cho **uniqueness** phải phù hợp invariant; index hỗ trợ **đọc** chưa chắc là index phù hợp để cưỡng chế uniqueness.

### 9.4. Dùng `explain()`

```javascript
db.users.find({
  tenantId: "TENANT-A",
  isDeleted: false,
  emailNormalized: "an@example.com"
}).explain("executionStats");
```

Quan sát:

| Chỉ số/khái niệm | Câu hỏi |
|---|---|
| `winningPlan` | Query planner chọn phương án nào? |
| `IXSCAN` | Index nào được sử dụng? |
| `COLLSCAN` | Có quét collection không? |
| `FETCH` | Có cần đọc document ngoài index? |
| `totalKeysExamined` | Bao nhiêu khóa index đã được xét? |
| `totalDocsExamined` | Bao nhiêu document đã được kiểm tra? |
| `nReturned` | Bao nhiêu document trả về? |

Việc thêm `isDeleted: false` vào query không chỉ là yêu cầu nghiệp vụ; nó còn giúp query có thể chứng minh điều kiện của partial index với planner.

## 10. Khôi phục document xóa mềm

Một chức năng “Undo delete” thường gồm các bước:

1. Xác minh user có quyền khôi phục.
2. Đọc hoặc tìm document có `isDeleted: true` trong phạm vi tenant.
3. Kiểm tra quy tắc retention, trùng khóa unique, quyền sở hữu tài khoản, các ràng buộc khác.
4. Cập nhật trạng thái về active trong một thao tác có filter phù hợp.
5. Ghi log khôi phục/đối soát tác động tới các hệ thống liên quan.

Ví dụ:

```javascript
const result = db.users.updateOne(
  {
    _id: "U101",
    tenantId: "TENANT-A",
    isDeleted: true
  },
  {
    $set: { isDeleted: false },
    $unset: { deletedAt: "", deletedBy: "" },
    $currentDate: {
      restoredAt: true,
      updatedAt: true
    }
  }
);
```

Ở đây, `$unset` loại metadata trạng thái xóa khỏi document (nếu muốn giữ lịch sử nhiều lần xóa/restore, tốt hơn lưu event audit riêng thay vì mất metadata). `restoredAt` ghi lần restore gần nhất; nếu không dùng thì có thể bỏ.

Nếu email đang được user active khác dùng, unique index có thể khiến update thất bại. **Không bao giờ bắt lỗi duplicate key rồi âm thầm đánh dấu restore thành công**. Trả về tình trạng conflict cho workflow quản trị và quyết định chính sách.

### 10.1. Restore không tự khôi phục toàn bộ quan hệ

Nếu khi xóa mềm user, ứng dụng đã vô hiệu hóa token, xóa quyền truy cập, đưa dữ liệu ra kho lưu trữ hoặc xóa vật lý những bản ghi con, việc đổi `isDeleted` về `false` không tự đảo ngược những hành động đó. Cần định nghĩa rõ **bản ghi nào có thể khôi phục**, **cái gì không thể khôi phục**, và những bước bù trừ cần chạy.

Đối với quan hệ parent–child, một số chính sách hợp lý là:

- Soft delete parent thì child tạm không hiển thị do parent đã bị ẩn.
- Soft delete riêng cả parent và child, có quản lý lý do, thời điểm và trạng thái.
- Giữ giao dịch lịch sử không bị xóa theo user nếu có nghĩa vụ lưu giữ, nhưng hạn chế dữ liệu định danh theo chính sách.

Không được áp dụng một cascade chung cho mọi loại document mà bỏ qua hợp đồng nghiệp vụ.

## 11. Xóa vật lý sau thời gian lưu giữ

Nhiều sản phẩm dùng quy trình hai giai đoạn:

```text
ACTIVE
  |
  | Người dùng xóa / quản trị viên xóa mềm
  v
SOFT_DELETED ----> RESTORED (nếu còn cho phép và không conflict)
  |
  | Hết thời gian lưu giữ + kiểm tra điều kiện
  v
PURGED / HARD_DELETED
```

Ví dụ chính sách: sau 30 ngày kể từ `deletedAt`, document xóa mềm đủ điều kiện purge nếu không có legal hold hoặc ràng buộc nghiệp vụ khác.

### 11.1. Purge job chủ động

Ví dụ với mốc kiểm tra đã được tính sẵn:

```javascript
const cutoff = new Date(
  Date.now() - 30 * 24 * 60 * 60 * 1000
);

const result = db.users.deleteMany({
  isDeleted: true,
  deletedAt: { $lte: cutoff },
  legalHold: { $ne: true }
});

print(result.deletedCount);
```

Đây là ví dụ **mốc 30 ngày tính theo milliseconds**, không thay thế chính sách thời gian cụ thể của doanh nghiệp khi có timezone, ngày làm việc hoặc yêu cầu pháp lý. Filter `legalHold: { $ne: true }` cho phép cả field không tồn tại; nếu policy yêu cầu chỉ được purge khi có phê duyệt rõ `legalHold: false` thì cần thay điều kiện tương ứng.

Đối với collection lớn, nên xử lý theo batch có checkpoint, giới hạn tải và khả năng dừng. **Một lệnh `deleteMany()` rất lớn có thể tạo tải I/O và replication đáng kể**.

### 11.2. Dùng TTL index để tự động xóa vật lý

MongoDB hỗ trợ **TTL index** trên trường ngày giờ để xóa document sau một khoảng thời gian. Với document soft-deleted có `deletedAt` là BSON Date, có thể tạo:

```javascript
db.users.createIndex(
  { deletedAt: 1 },
  {
    name: "ttl_deleted_users_after_30_days",
    expireAfterSeconds: 2592000
  }
);
```

Giá trị `2592000` giây tương ứng 30 ngày × 24 giờ. Với một document:

```javascript
{
  _id: "U101",
  isDeleted: true,
  deletedAt: ISODate("2026-06-15T10:30:00Z")
}
```

TTL xóa document khi đã đến thời hạn tính từ `deletedAt` **theo cơ chế nền**, không bảo đảm đúng tại một mili-giây cụ thể. Document active **không nên có trường `deletedAt` là một Date quá hạn**, nếu không TTL cũng có thể xóa nó. Vì thế cần giữ invariant: chỉ document thực sự cần purge mới có `deletedAt` theo ý nghĩa TTL.

TTL index không biết các điều kiện nghiệp vụ như tranh chấp khôi phục, phê duyệt xóa, legal hold, phụ thuộc dữ liệu, hoặc quy trình xóa ở hệ thống ngoài. Nếu chính sách purge cần những kiểm tra đó, **job chủ động có điều kiện** thường an toàn hơn việc dựa hoàn toàn vào TTL.

### 11.3. Đặc điểm và giới hạn TTL cần nhớ

- TTL hoạt động bất đồng bộ qua tiến trình nền; việc quá hạn không đồng nghĩa document bị xóa ngay tức thì.
- TTL cần field thời gian ở dạng BSON Date phù hợp; lưu chuỗi ngày giờ có thể không được xử lý như mong muốn.
- TTL index là loại index có đặc tính và giới hạn riêng; không nên lẫn với partial unique index dùng cho email.
- Xóa bằng TTL là **hard delete**, không phải tự cập nhật `isDeleted` thành `true`.
- TTL có thể tạo tải xóa đáng kể khi nhiều document cùng hết hạn; phải giám sát hệ thống và replication.
- Với nhu cầu giữ dữ liệu theo điều kiện phức tạp, phải thiết kế riêng thay vì kỳ vọng TTL đọc tất cả metadata nghiệp vụ.

## 12. Xóa theo lô và tính đúng đắn khi xử lý hàng loạt

Trong chương “Xóa và ghi theo lô”, cần phân biệt giữa **một lệnh xử lý nhiều document** với **một giao dịch nguyên tử toàn bộ batch**.

### 12.1. Hard delete một tập ID

```javascript
const ids = ["U101", "U102", "U103"];

const result = db.users.deleteMany({
  tenantId: "TENANT-A",
  _id: { $in: ids },
  isDeleted: true
});

print(result.deletedCount);
```

Điều kiện `isDeleted: true` giúp đảm bảo job purge chỉ xóa bản ghi đã đi qua giai đoạn soft delete. Tuy nhiên, nếu có yêu cầu retention, phải thêm `deletedAt` và các ràng buộc chính sách, không chỉ dựa vào ID.

### 12.2. Dùng `bulkWrite()` cho nhiều thao tác xóa

```javascript
db.users.bulkWrite(
  [
    {
      deleteOne: {
        filter: {
          _id: "U101",
          tenantId: "TENANT-A",
          isDeleted: true
        }
      }
    },
    {
      deleteOne: {
        filter: {
          _id: "U102",
          tenantId: "TENANT-A",
          isDeleted: true
        }
      }
    }
  ],
  { ordered: false }
);
```

`ordered: false` cho phép xử lý các thao tác độc lập dù một thao tác có write error; `ordered: true` dừng theo ngữ nghĩa ordered khi gặp lỗi ghi. Cả hai **không tự bảo đảm all-or-nothing** ngoài transaction. Không được suy ra một lệnh bulk đã xóa tất cả ID chỉ vì một phần đã thành công.

### 12.3. Batch và kiểm soát quyền

Với thao tác xóa dữ liệu của nhiều tenant, rủi ro nghiêm trọng nhất là quên scope trong filter. Ví dụ:

```javascript
// Rủi ro: có thể xóa record của tenant khác nếu ID không đủ scope.
db.users.deleteMany({ status: "INACTIVE" });
```

Trong hệ thống đa tenant, luôn thêm scope được xác thực từ context tin cậy, không lấy tenant ID chỉ từ một input mà người dùng có thể giả mạo.

Hệ thống lớn nên có chính sách batching:

1. Lấy danh sách ID đủ điều kiện theo scope và cutoff.
2. Ghi nhận job/batch ID, phạm vi, tiêu chí và quyền thực thi.
3. Xóa theo batch giới hạn về số lượng, có timeout/retry rõ ràng.
4. Ghi lại số bản ghi đã xóa, lỗi và những ID chưa chắc trạng thái.
5. Đối soát lại dữ liệu và trạng thái liên quan.
6. Giám sát ảnh hưởng lên disk I/O, oplog/replication và tác vụ downstream.

### 12.4. Transaction có cần cho batch delete không?

MongoDB hỗ trợ multi-document transaction trên môi trường phù hợp. Nhưng một transaction chứa hàng trăm nghìn xóa có thể tốn tài nguyên, kéo dài, phát sinh conflict/timeout. Nếu dữ liệu độc lập và mục tiêu là purge theo chính sách, batch idempotent thường hiệu quả hơn.

Ngược lại, nếu xóa một entity bắt buộc đi kèm cập nhật vài document liên quan để giữ invariant, transaction nhỏ có thể phù hợp. **Đừng dùng transaction chỉ vì API gọi là “bulk”**; phải có lý do về tính nhất quán nghiệp vụ.

## 13. Quan hệ, audit và bảo mật khi xóa

### 13.1. MongoDB không tự cascade như khóa ngoại trong RDBMS

Giả sử xóa user nhưng `orders.customerId` vẫn tham chiếu ID đó. Dù hard delete user, order không tự bị xóa vì MongoDB không mặc định cưỡng chế foreign key/cascade trên các collection document thông thường.

Cần lựa chọn chính sách:

- Không xóa lịch sử đơn hàng vì yêu cầu kế toán, nhưng giới hạn thông tin định danh.
- Soft delete user, giữ đơn hàng nhưng dùng snapshot tên/địa chỉ đã được phép lưu theo quy định.
- Xóa/cắt liên kết phụ thuộc theo quy trình nghiệp vụ nếu được phép.
- Đánh dấu trạng thái pending để consumer nền xử lý các bản ghi con.

Đối với parent–child cần truy vấn cùng nhau, trạng thái deleted của parent có thể ảnh hưởng cách hiển thị child. Không phải cứ document con có `isDeleted: false` là được phép xuất hiện nếu parent đã bị xóa.

### 13.2. Audit event nên tách khỏi document nghiệp vụ

Soft delete cho phép xem `deletedAt` và `deletedBy`, nhưng nếu document bị xóa vật lý thì metadata đó cũng biến mất khỏi collection. Nếu cần chứng minh ai yêu cầu xóa, ai duyệt purge, thời điểm và lý do, có thể ghi một **audit event** vào nơi lưu phù hợp:

```javascript
{
  _id: "audit-delete-001",
  eventType: "USER_SOFT_DELETED",
  targetCollection: "users",
  targetId: "U101",
  tenantId: "TENANT-A",
  actorId: "admin-42",
  occurredAt: ISODate("2026-06-15T10:30:00Z"),
  requestId: "req-8a4f"
}
```

Audit log không nên chứa tất cả dữ liệu bí mật của user chỉ để “phòng khi khôi phục”. Bản thân log cũng cần chính sách truy cập, retention, bảo vệ chỉnh sửa và xóa theo quy định.

### 13.3. Soft delete không phải anonymization

Khi document còn `email`, `phone`, `address` hoặc thông tin nhạy cảm, xóa mềm **không khiến dữ liệu biến mất**. Nó chỉ thay đổi quy tắc hiển thị trong ứng dụng. Nếu mục đích là tuân thủ yêu cầu xóa dữ liệu, cần xem xét khả năng xóa vật lý, pseudonymization/anonymization khi phù hợp, backups, bản sao, cache và hệ thống ngoài.

Ngược lại, hard delete trực tiếp trên database cũng **không chứng minh** mọi bản lưu đã biến mất trên backup hay các hệ thống downstream. Một chính sách hoàn chỉnh mô tả phạm vi, thời hạn và các ngoại lệ lưu giữ bắt buộc.

## 14. Migration từ unique index thường sang partial unique index

Giả sử hệ thống hiện có:

```javascript
db.users.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  { name: "uniq_email_all_rows", unique: true }
);
```

Nhưng product muốn cho phép đăng ký lại email của tài khoản đã xóa mềm. Cần lập kế hoạch migration, không đổi index tùy tiện giữa giờ cao điểm.

**Bước 1 — Chốt invariant:** email duy nhất trong **các user active của cùng tenant**; soft-deleted user có thể trùng email với nhau và với active user.

**Bước 2 — Chuẩn hóa schema:** bảo đảm mọi user active có `isDeleted: false`, user đã xóa có `isDeleted: true`. Xử lý giá trị thiếu, `null` và các bản ghi sai kiểu trước khi dựa vào partial filter.

**Bước 3 — Đối soát uniqueness của tập active:** tìm các cặp `(tenantId, emailNormalized)` có nhiều hơn một user active, xử lý xung đột nghiệp vụ trước khi tạo index unique mới. Nếu dữ liệu chưa có đủ ID/tenant/emailNormalized, cần giải quyết trường hợp đặc biệt phù hợp với policy.

Một aggregation minh họa:

```javascript
db.users.aggregate([
  { $match: { isDeleted: false } },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        email: "$emailNormalized"
      },
      count: { $sum: 1 },
      userIds: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } }
]);
```

Đây là thao tác hỗ trợ phát hiện xung đột. Với tập dữ liệu lớn, gom toàn bộ `userIds` vào một mảng trong aggregation có thể gây áp lực bộ nhớ; có thể chỉ đếm hoặc giới hạn mẫu ID khi đánh giá thực tế.

**Bước 4 — Tạo partial unique index mới:** trên hệ thống và phiên bản hỗ trợ, tạo index với tên riêng:

```javascript
db.users.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  {
    name: "uniq_active_email_per_tenant",
    unique: true,
    partialFilterExpression: { isDeleted: false }
  }
);
```

**Bước 5 — Chuyển code:** mọi luồng đăng ký, khôi phục, kiểm tra tồn tại và truy vấn active phải dùng điều kiện/semantics mới. Xử lý duplicate key từ unique index theo thông báo nghiệp vụ phù hợp.

**Bước 6 — Loại unique index cũ khi an toàn:** index cũ vẫn cưỡng chế uniqueness trên deleted rows, nên cuối cùng phải được loại nếu muốn tái sử dụng identifier. Trước khi xóa index, cần xác minh index mới đã tạo thành công và mọi luồng ghi tương thích:

```javascript
// Chỉ thực hiện sau khi kiểm tra chính xác tên/index và quy trình thay đổi.
db.users.dropIndex("uniq_email_all_rows");
```

Nếu tạo hai index có cùng key pattern và option khác nhau, khả năng cùng tồn tại/giới hạn có thể phụ thuộc phiên bản MongoDB và cấu hình; cần xây lộ trình phù hợp, kiểm tra build index và khóa ghi trong giai đoạn chuyển đổi. Không chạy `dropIndex` một cách mù quáng.

**Bước 7 — Thử các ca ranh giới:** soft delete rồi tạo mới cùng email; tạo hai user active trùng email; restore user cũ sau khi email được dùng lại; query active/admin; các yêu cầu đồng thời; multi-tenant; quy tắc chuẩn hóa email và collation.

## 15. Java và Spring Data MongoDB: áp dụng chính sách soft delete

Khi code ứng dụng dùng Java, nên tập trung logic soft delete vào repository/service thay vì để từng API tự nhớ thêm `isDeleted: false`.

### 15.1. Java Sync Driver: soft delete có điều kiện

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.currentDate;
import static com.mongodb.client.model.Updates.set;

MongoCollection<Document> users =
    database.getCollection("users");

UpdateResult result = users.updateOne(
    and(
        eq("_id", "U101"),
        eq("tenantId", "TENANT-A"),
        eq("isDeleted", false)
    ),
    combine(
        set("isDeleted", true),
        set("deletedBy", "admin-42"),
        currentDate("deletedAt"),
        currentDate("updatedAt")
    )
);

if (result.getModifiedCount() != 1) {
    // Không tìm thấy user active hoặc trạng thái đã thay đổi.
}
```

Driver cho phép tạo partial index bằng cấu hình `IndexOptions.partialFilterExpression(...)` và unique index bằng `unique(true)` khi cần. Cách khai báo cụ thể tùy phiên bản Java Driver.

### 15.2. Spring Data MongoDB: query và update rõ điều kiện active

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

Query query = Query.query(
    Criteria.where("_id").is("U101")
        .and("tenantId").is("TENANT-A")
        .and("isDeleted").is(false)
);

Update update = new Update()
    .set("isDeleted", true)
    .set("deletedBy", "admin-42")
    .currentDate("deletedAt")
    .currentDate("updatedAt");

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    "users"
);
```

Lưu ý các phương thức repository tự động như `findById()` hoặc `findAll()` **không được giả định luôn tự thêm filter soft delete** trừ khi ứng dụng đã có custom repository/query convention được triển khai và kiểm chứng. Nên viết API tách biệt:

- `findActiveUserById(tenantId, id)`;
- `findDeletedUserForAdmin(tenantId, id)`;
- `softDeleteActiveUser(tenantId, id, actor)`;
- `restoreDeletedUser(tenantId, id, actor)`;
- `purgeExpiredDeletedUsers(cutoff)`.

Tên hàm này chỉ minh họa thiết kế service, không phải các phương thức có sẵn của thư viện.

## 16. Bảng quyết định theo yêu cầu nghiệp vụ

| Nhu cầu | Phương án để đánh giá | Lưu ý |
|---|---|---|
| Người dùng có 30 ngày khôi phục tài khoản | Soft delete + metadata + purge sau retention | Chính sách reuse email và restore conflict |
| Nhật ký tạm quá hạn phải xóa | Hard delete theo batch hoặc TTL | TTL không đúng chính xác thời điểm và có tải nền |
| Email chỉ duy nhất giữa tài khoản active | Partial unique index với `isDeleted: false` | Tất cả active phải có cờ nhất quán |
| Email phải mãi mãi không được tái sử dụng | Unique index thông thường hoặc registry riêng | Soft delete không giải phóng khóa là hành vi mong muốn |
| Đơn hàng đã hủy vẫn cần lưu | Trạng thái nghiệp vụ `CANCELLED`, chưa chắc là soft delete | Tuân thủ nghiệp vụ/audit |
| Cần báo cáo lịch sử có cả deleted | Query/admin/report cố ý bao gồm deleted | Không dùng partial active index nếu nó làm thiếu kết quả |
| API public không được thấy deleted | Bắt buộc filter active trong read/update/aggregate | Scope tenant và quyền truy cập |
| Xóa dữ liệu theo yêu cầu bảo mật | Quy trình xóa theo policy qua storage và backup | Soft delete đơn thuần thường chưa đủ |
| Xóa entity với nhiều bản ghi liên quan | Workflow/transaction hoặc tác vụ nền có đối soát | Không có cascade mặc định |
| Collection rất lớn, deleted chiếm phần lớn | Partial index active và retention purge | Đánh giá index size, query plan, I/O |

## 17. Bài tập thực hành

### Bài 1 — Quan sát soft delete và hard delete

Tạo collection `customersLab` có ba khách hàng, mỗi document có `isDeleted: false`. Thực hiện:

1. Xóa mềm một khách hàng bằng `updateOne()` với filter `isDeleted: false`.
2. Chạy `find({})` và `find({ isDeleted: false })`, giải thích kết quả khác nhau.
3. Dùng `countDocuments()` đếm active và deleted.
4. Xóa vật lý khách hàng đã soft delete bằng `deleteOne()` có filter trạng thái.
5. Kiểm tra `deletedCount` và quan sát rằng document không còn được tìm thấy trong collection.

### Bài 2 — Unique index cũ cản đăng ký lại

Tạo unique index `{ emailNormalized: 1 }`. Insert `"an@example.com"`, soft delete user rồi thử insert một user khác có cùng email.

- Dự đoán lỗi và giải thích vì sao có thể gặp `E11000`.
- Có phải query `{ isDeleted: false }` làm unique index bỏ qua deleted row không?
- Vì sao `{ emailNormalized: 1, isDeleted: 1 }` với `unique: true` không cho phép lịch sử nhiều lần xóa mềm cùng email?

### Bài 3 — Thiết kế partial unique index theo tenant

Tạo index `{ tenantId: 1, emailNormalized: 1 }` với `unique: true` và `partialFilterExpression: { isDeleted: false }`. Thử:

1. Hai tenant khác nhau có cùng email active.
2. Hai user cùng tenant và cùng email active.
3. Soft delete user thứ nhất, tạo user active mới cùng email.
4. Restore user cũ khi user mới vẫn active.

Giải thích kết quả được chấp nhận hoặc từ chối ở từng tình huống.

### Bài 4 — Tìm lỗi thiếu filter soft delete

Một API thống kê dùng:

```javascript
db.users.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  { $group: { _id: "$role", total: { $sum: 1 } } }
]);
```

Hãy sửa để chỉ đếm active users. Sau đó xem một aggregation dùng `$lookup` từ `orders` sang `customers` và bổ sung filter deleted phù hợp ở cả hai phía, theo chính sách truy cập.

### Bài 5 — Thiết kế purge 30 ngày

Tạo document đã xóa mềm có `deletedAt` là BSON Date. So sánh:

- `deleteMany()` với filter `isDeleted: true`, `deletedAt <= cutoff` và `legalHold`.
- TTL index `{ deletedAt: 1 }`, `expireAfterSeconds: 2592000`.

Trường hợp nào cần job chủ động vì có điều kiện nghiệp vụ? Vì sao `expireAfterSeconds` không cho phép bảo đảm xóa chính xác tại mili-giây thứ 2.592.000?

### Bài 6 — Migration thực tế

Hệ thống có vài triệu user, unique index cũ trên `(tenantId, emailNormalized)` và nhiều tài khoản đã xóa mềm. Hãy phác thảo kế hoạch migration sang partial unique index, bao gồm chuẩn hóa `isDeleted`, đối soát active duplicates, xử lý index cũ, đổi code, thử race condition và rollback khi phát hiện lỗi.

## 18. Tham khảo tài liệu MongoDB

- [Delete Documents](https://www.mongodb.com/docs/manual/tutorial/remove-documents/)
- [db.collection.deleteOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteOne/)
- [db.collection.deleteMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteMany/)
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/)
- [Write Operations Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)

## Kết luận

**Xóa mềm** là cập nhật trạng thái, nên document vẫn tồn tại trong collection và tiếp tục ảnh hưởng đến truy vấn, dung lượng, index và uniqueness. **Xóa vật lý** loại document khỏi collection, nhưng không tự xóa dữ liệu khỏi mọi backup/downstream hay bảo đảm file trên ổ đĩa thu nhỏ ngay. Vì vậy, lựa chọn chiến lược xóa là quyết định về **vòng đời dữ liệu và ràng buộc nghiệp vụ**, không chỉ là thay `deleteOne()` bằng `updateOne()`.

Nếu chỉ cần đảm bảo một giá trị duy nhất giữa những bản ghi **active**, **partial unique index** với điều kiện active nhất quán là công cụ quan trọng. Tất cả query thường phải lọc soft-deleted records; restore phải kiểm tra unique conflicts; purge phải theo chính sách retention và quyền truy cập. Khi có batch, concurrency, multi-tenant hoặc audit, cần thêm logging, idempotency, đối soát và thiết kế transaction phù hợp. Nhờ vậy, hệ thống có thể cho phép khôi phục khi cần mà vẫn giữ đúng ngữ nghĩa truy vấn và tính toàn vẹn dữ liệu.

