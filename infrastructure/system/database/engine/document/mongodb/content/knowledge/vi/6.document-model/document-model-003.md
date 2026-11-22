# Mô hình quan hệ một một, một nhiều và nhiều nhiều trong MongoDB

## 1. Vì sao MongoDB vẫn cần mô hình hóa quan hệ?

MongoDB lưu dữ liệu theo **document BSON** trong các **collection**. Một document có thể chứa trường đơn, object lồng nhau và mảng, nhờ đó nhiều thành phần của một thực thể có thể nằm chung một bản ghi. Tuy nhiên, dữ liệu nghiệp vụ vẫn có quan hệ với nhau: một người dùng có một hồ sơ, một khách hàng có nhiều đơn hàng, và một học viên có thể đăng ký nhiều khóa học.

**Cardinality** (lực lượng quan hệ) cho biết mỗi bản ghi ở phía A có thể liên hệ với bao nhiêu bản ghi ở phía B:

| Quan hệ | Diễn giải | Ví dụ |
| --- | --- | --- |
| **Một – một (1:1)** | Một A gắn với tối đa một B, và một B gắn với tối đa một A | Người dùng – hồ sơ tùy chọn |
| **Một – nhiều (1:N)** | Một A có thể gắn với nhiều B; mỗi B thuộc một A trong mô hình đang xét | Khách hàng – đơn hàng |
| **Nhiều – nhiều (N:N)** | Một A có nhiều B và một B cũng có nhiều A | Học viên – khóa học |

Con số “1”, “N” mô tả **quy tắc nghiệp vụ**, chưa tự quyết định cách lưu dữ liệu. Trong MongoDB, cần chọn đặt dữ liệu ở **cùng document** (*embedding*), giữ **định danh tham chiếu** trong document khác (*referencing*), hoặc kết hợp hai cách.

Ví dụ cùng một quan hệ khách hàng – đơn hàng:

```text
Mô hình nhúng:
customers
└── customer KH01
    └── orders: [DH01, DH02, ...]

Mô hình tham chiếu:
customers                   orders
└── KH01                    ├── DH01 (customerId = KH01)
                           └── DH02 (customerId = KH01)
```

Việc nhúng toàn bộ đơn hàng vào khách hàng có thể hợp lý khi số lượng rất nhỏ và có giới hạn, nhưng không phù hợp nếu lịch sử đơn hàng tăng liên tục. Mục tiêu của thiết kế document là **phục vụ các thao tác đọc/ghi thực tế, giữ kích thước dữ liệu có kiểm soát và bảo đảm tính nhất quán cần thiết**.

Sau bài học, người học có thể:

1. Phân biệt quan hệ 1:1, 1:N, N:N ở cấp nghiệp vụ.
2. Quyết định khi nào nên nhúng hoặc tham chiếu, xác định phía nào giữ tham chiếu.
3. Dùng `mongosh` để tạo và truy vấn các dạng quan hệ cơ bản.
4. Áp dụng `unique index`, `compound index` và `$lookup` đúng trường hợp.
5. Hiểu giới hạn của mảng nhúng, ràng buộc tham chiếu và cập nhật nhiều document.

## 2. Hai cách biểu diễn quan hệ: embedding và referencing

### 2.1. Nhúng dữ liệu (embedding)

Nhúng nghĩa là lưu dữ liệu liên quan ngay trong document cha:

```javascript
{
  _id: "USER-01",
  name: "Minh",
  profile: {
    displayName: "Minh Nguyen",
    locale: "vi-VN"
  },
  addresses: [
    { label: "Nhà", city: "Hồ Chí Minh" },
    { label: "Cơ quan", city: "Đà Nẵng" }
  ]
}
```

Ưu điểm thường thấy:

- Có thể đọc document cha và dữ liệu liên quan chỉ bằng một truy vấn.
- Không cần kết hợp collection cho mỗi lần hiển thị.
- Một thao tác ghi trên **một document** là nguyên tử, kể cả khi sửa nhiều trường hoặc phần tử lồng nhau trong document đó.
- Cấu trúc dữ liệu phản ánh trực tiếp đối tượng mà ứng dụng thường sử dụng.

Đổi lại:

- Document tăng kích thước khi mảng hoặc object con phát triển.
- BSON document có giới hạn kích thước **16 MiB**.
- Thông tin nhúng bị lặp lại trong nhiều document có thể khó đồng bộ khi thay đổi.
- Dữ liệu cần truy vấn, phân quyền hoặc cập nhật độc lập có thể phù hợp hơn với collection riêng.

### 2.2. Tham chiếu dữ liệu (referencing)

Tham chiếu nghĩa là giữ document riêng và lưu một định danh để liên hệ:

```javascript
// Collection users
{
  _id: "USER-01",
  name: "Minh"
}

// Collection orders
{
  _id: "ORDER-01",
  customerId: "USER-01",
  totalAmount: 750000
}
```

Ưu điểm:

- Các thực thể có thể phát triển và được cập nhật độc lập.
- Có thể truy vấn một nhóm con rất lớn bằng index và phân trang.
- Tránh việc đưa mảng tăng vô hạn vào document cha.
- Các document có vòng đời hoặc chính sách truy cập khác nhau được quản lý riêng.

Đổi lại:

- Có thể phải chạy nhiều truy vấn hoặc dùng aggregation `$lookup`.
- Nếu nghiệp vụ sửa nhiều document cùng lúc, cần giải pháp bảo đảm tính nhất quán phù hợp.
- MongoDB không tự áp đặt ràng buộc khóa ngoại kiểu SQL giữa hai collection chỉ vì một trường có tên `customerId`.

**Nguyên tắc chọn sơ bộ:** nhúng các phần dữ liệu **có giới hạn, thường được đọc cùng nhau và gắn chặt vòng đời**; tham chiếu khi **số lượng tăng nhiều, truy vấn độc lập, được chia sẻ hoặc cập nhật độc lập**. Đây là định hướng để bắt đầu, không phải luật cứng.

### 2.3. Hỏi gì trước khi quyết định?

| Câu hỏi | Nếu câu trả lời là “có” |
| --- | --- |
| Có thường lấy A và B trong cùng một màn hình/API không? | Nghiêng về nhúng |
| Số lượng B trong một A có giới hạn nhỏ và ổn định không? | Nhúng dễ quản lý hơn |
| Số lượng B có thể tăng hàng nghìn/hàng triệu không? | Nghiêng về tham chiếu |
| B có cần tồn tại hoặc được truy vấn độc lập với A không? | Nghiêng về tham chiếu |
| Một B được nhiều A cùng dùng không? | Tham chiếu giúp tránh nhân bản không cần thiết |
| A và B có cần sửa cùng lúc như một đơn vị nguyên tử không? | Nhúng có thể giảm nhu cầu giao dịch đa document |
| B có chứa dữ liệu cần phân quyền, vòng đời hoặc tần suất cập nhật khác A không? | Collection riêng thường linh hoạt hơn |

Đặc biệt, cần quan tâm **hướng truy cập**: ứng dụng hay hỏi “tất cả đơn hàng của khách hàng X”, hay “thông tin khách hàng cho đơn hàng Y”, hay cả hai? Hướng truy cập sẽ ảnh hưởng đến nơi lưu khóa tham chiếu và lựa chọn index.

## 3. Quan hệ một – một (1:1)

### 3.1. Khi nào là 1:1?

Ví dụ một tài khoản có tối đa một bộ tùy chọn cá nhân:

```text
users                       userPreferences
_id = USER-01       1 : 0..1   userId = USER-01
```

Ký hiệu `0..1` nói rằng phần tùy chọn có thể chưa được tạo, nhưng không được có hai bản ghi tùy chọn cho một user. Nếu nghiệp vụ bắt buộc phải có đúng một bản ghi ở cả hai phía, phải thêm quy trình tạo và duy trì tương ứng.

### 3.2. Cách 1: nhúng một object con

```javascript
{
  _id: "USER-01",
  email: "minh@example.test",
  preferences: {
    language: "vi",
    theme: "dark",
    emailNotifications: true
  }
}
```

Nhúng tốt khi phần tùy chọn nhỏ, luôn đi cùng tài khoản và không cần quyền truy cập khác biệt. Khi đổi ngôn ngữ, có thể cập nhật một trường lồng nhau:

```javascript
db.users.updateOne(
  { _id: "USER-01" },
  { $set: { "preferences.language": "en" } }
);
```

Đây là một thao tác trên một document; không cần tạo quan hệ giữa hai collection.

### 3.3. Cách 2: tách collection và dùng unique index

Tách riêng có ích khi phần liên quan rất lớn, ít được đọc cùng nhau, có chu kỳ cập nhật khác hoặc cần phân quyền riêng. Ví dụ profile nội bộ có thể đặt riêng với tài khoản đăng nhập.

Ví dụ thực hành trong `mongosh`, với database thử nghiệm `mongo_relations_lab` và dữ liệu được gắn `runId`:

```javascript
const lab = db.getSiblingDB("mongo_relations_lab");
const runId = "row71-" + new ObjectId().toHexString();
const userId = new ObjectId();

lab.users.insertOne({
  _id: userId,
  runId: runId,
  username: "minh-row71",
  email: "minh@example.test"
});

// Mỗi userId xuất hiện tối đa một lần trong userPreferences.
lab.userPreferences.createIndex(
  { userId: 1 },
  { unique: true }
);

lab.userPreferences.insertOne({
  _id: new ObjectId(),
  runId: runId,
  userId: userId,
  language: "vi",
  theme: "dark"
});

printjson(lab.userPreferences.findOne({ userId: userId }));
```

Ở đây, `userId` phải có **cùng kiểu dữ liệu** với `users._id`. Trong ví dụ, cả hai đều là `ObjectId`; nếu một bên là chuỗi và bên kia là `ObjectId`, truy vấn đối chiếu sẽ không khớp dù ký tự nhìn có vẻ giống nhau.

**Unique index** trên `userPreferences.userId` ngăn hai document preferences có cùng user ID. Tuy nhiên, nó **không kiểm tra user đó có thật trong collection `users` hay không**, cũng không bắt buộc mọi user phải có preferences. Nếu `userId` là trường tùy chọn, cần chú ý unique index một trường xử lý giá trị `null` và trường thiếu như một khóa `null` trong chỉ mục; nên yêu cầu trường này hợp lệ hoặc thiết kế partial index phù hợp với dữ liệu thực tế.

### 3.4. Truy vấn hai phía của quan hệ 1:1

Đọc hai lần theo ID:

```javascript
const account = lab.users.findOne({ _id: userId });
const preferences = lab.userPreferences.findOne({ userId: userId });
printjson({ account: account, preferences: preferences });
```

Hoặc dùng `$lookup` để trả về dữ liệu kết hợp:

```javascript
lab.users.aggregate([
  { $match: { _id: userId } },
  {
    $lookup: {
      from: "userPreferences",
      localField: "_id",
      foreignField: "userId",
      as: "preferences"
    }
  },
  {
    $unwind: {
      path: "$preferences",
      preserveNullAndEmptyArrays: true
    }
  }
]);
```

`$lookup` tạo trường mảng `preferences` vì có thể ghép nhiều phần tử theo cơ chế tổng quát. `$unwind` biến phần tử mảng thành một kết quả; với unique index, mỗi user có tối đa một preferences. Tùy chọn `preserveNullAndEmptyArrays` giúp giữ user chưa có preferences trong kết quả.

## 4. Quan hệ một – nhiều (1:N)

Một khách hàng có thể tạo nhiều đơn hàng; mỗi đơn hàng thuộc một khách hàng trong mô hình cơ bản:

```text
customers                         orders
KH01 ---------------------------> DH01 (customerId = KH01)
     ---------------------------> DH02 (customerId = KH01)
     ---------------------------> DH03 (customerId = KH01)
```

Quan hệ 1:N có ít nhất hai cách biểu diễn đáng chú ý: **mảng nhúng ở phía “một”** và **tham chiếu ở phía “nhiều”**.

### 4.1. Nhúng khi tập con nhỏ và được đọc cùng nhau

Một đơn hàng có một số dòng hàng được chốt tại thời điểm đặt:

```javascript
{
  _id: "ORDER-01",
  customerId: "USER-01",
  items: [
    { productId: "P01", name: "Sổ tay", quantity: 2, unitPrice: 50000 },
    { productId: "P02", name: "Bút", quantity: 3, unitPrice: 15000 }
  ],
  totalAmount: 145000
}
```

Trong ví dụ này, `items` là tập con của đơn hàng. Việc nhúng thuận tiện vì API chi tiết đơn hàng thường lấy toàn bộ danh sách dòng hàng. Thông tin `name` và `unitPrice` là **bản chụp tại thời điểm mua** nên không nhất thiết cần đồng bộ khi tên/giá trong catalog thay đổi.

Nhúng không đồng nghĩa phải nhúng mọi thứ: `customerId` vẫn tham chiếu đến customer, còn các dòng hàng được nhúng.

Ví dụ cập nhật số lượng của một dòng hàng đã tồn tại:

```javascript
db.orders.updateOne(
  { _id: "ORDER-01", "items.productId": "P02" },
  { $set: { "items.$.quantity": 4 } }
);
```

Toán tử vị trí `$` trong ví dụ cập nhật phần tử mảng đầu tiên khớp điều kiện; nếu nghiệp vụ yêu cầu cập nhật nhiều phần tử theo tiêu chí riêng, có thể dùng `arrayFilters` hoặc mô hình hóa mỗi phần tử có định danh duy nhất. Với đơn hàng thực tế, cần tính lại các trường tổng tiền theo quy tắc nhất quán; ví dụ chỉ minh họa cách thao tác với mảng nhúng.

### 4.2. Tham chiếu khi tập con tăng liên tục

Nếu nhúng **toàn bộ lịch sử đơn hàng** vào document customer, mảng `orders` có thể tăng mãi. Cách phổ biến hơn là để mỗi order là document riêng và lưu `customerId` ở phía “nhiều”.

Ví dụ tiếp tục với `lab`, `runId`, `userId` từ mục 3.3:

```javascript
const order1Id = new ObjectId();
const order2Id = new ObjectId();

lab.orders.insertMany([
  {
    _id: order1Id,
    runId: runId,
    customerId: userId,
    createdAt: ISODate("2026-11-10T02:00:00Z"),
    status: "PAID",
    items: [
      { productId: "P01", quantity: 2, unitPrice: 50000 }
    ],
    totalAmount: 100000
  },
  {
    _id: order2Id,
    runId: runId,
    customerId: userId,
    createdAt: ISODate("2026-11-12T03:00:00Z"),
    status: "NEW",
    items: [
      { productId: "P02", quantity: 3, unitPrice: 15000 }
    ],
    totalAmount: 45000
  }
]);

// Phục vụ truy vấn lịch sử đơn hàng theo khách hàng, mới nhất trước.
lab.orders.createIndex({ customerId: 1, createdAt: -1 });
```

Đọc lịch sử đơn hàng của một khách hàng:

```javascript
lab.orders.find(
  { customerId: userId },
  { _id: 1, createdAt: 1, status: 1, totalAmount: 1 }
).sort({ createdAt: -1 }).limit(20);
```

Truy vấn theo `customerId` và sắp xếp `createdAt` giảm dần là mẫu rất phổ biến; index ghép `{ customerId: 1, createdAt: -1 }` thường phù hợp. Với dữ liệu lớn, nên dùng phân trang dựa trên khóa sắp xếp ổn định (ví dụ kết hợp `createdAt` và `_id`), thay vì mặc định dùng `skip` rất lớn.

Đọc thông tin customer từ order:

```javascript
const order = lab.orders.findOne({ _id: order1Id });
const customer = lab.users.findOne({ _id: order.customerId });
printjson({ order: order, customer: customer });
```

Hoặc kết hợp bằng `$lookup`:

```javascript
lab.orders.aggregate([
  { $match: { _id: order1Id } },
  {
    $lookup: {
      from: "users",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  {
    $project: {
      _id: 1,
      totalAmount: 1,
      createdAt: 1,
      "customer.username": 1
    }
  }
]);
```

Nếu document customer bị xóa hoặc không tồn tại, `$lookup` có thể trả về mảng rỗng; `$unwind` mặc định sẽ loại bản ghi khỏi kết quả. Nếu muốn vẫn thấy order dù mất tham chiếu, dùng `preserveNullAndEmptyArrays: true` và xử lý tình huống nghiệp vụ đó.

### 4.3. Vì sao không nên lưu danh sách ID ở cả hai phía?

Có thể gặp mô hình như sau:

```javascript
// users
{ _id: "U1", orderIds: ["O1", "O2"] }

// orders
{ _id: "O1", customerId: "U1" }
{ _id: "O2", customerId: "U1" }
```

Lưu cả `orderIds` và `customerId` khiến mọi lần tạo, đổi chủ hoặc xóa order đều phải cập nhật **hai phía**. Nếu một lần ghi thất bại, hai biểu diễn có thể không khớp. Mảng `orderIds` cũng tăng theo lịch sử. Thường chỉ cần nguồn tham chiếu chính ở `orders.customerId`, kèm index để truy vấn ngược.

Đôi khi cần một danh sách nhỏ và ổn định (như `recentOrderIds` hoặc một vài mục được ghim) để tối ưu màn hình; đây là **dữ liệu dẫn xuất có giới hạn**, phải có quy tắc đồng bộ rõ ràng, không nên coi là bản sao hoàn chỉnh của toàn bộ quan hệ.

### 4.4. Chiến lược “subset” cho quan hệ một nhiều

Một giải pháp trung gian là nhúng **một phần dữ liệu thường xem** và giữ bản ghi đầy đủ ở collection riêng. Ví dụ document customer lưu tối đa vài order gần đây để hiển thị nhanh, còn collection `orders` chứa toàn bộ lịch sử.

```javascript
{
  _id: "USER-01",
  recentOrders: [
    { orderId: "ORDER-200", totalAmount: 90000 },
    { orderId: "ORDER-199", totalAmount: 120000 }
  ]
}
```

Cách này giảm số truy vấn cho màn hình ngắn, nhưng phải duy trì logic cập nhật, giới hạn kích thước mảng và xác định nguồn sự thật là collection `orders`. Nếu dùng cache/denormalization, ứng dụng cần chấp nhận hoặc xử lý độ trễ đồng bộ theo yêu cầu nghiệp vụ.

## 5. Quan hệ nhiều – nhiều (N:N)

Ví dụ một học viên có thể tham gia nhiều khóa học và một khóa học có nhiều học viên:

```text
students                       courses
An      ────────────────────── MongoDB
  └────────────┐           ┌── Java
Bình ──────────┴───────────┘
```

Mô hình này khác 1:N vì không thể đơn giản nói mỗi course thuộc đúng một student hoặc mỗi student thuộc đúng một course. Có hai cách thường gặp:

1. Lưu một mảng ID nhỏ ở một phía (khi quan hệ có giới hạn và chỉ dùng theo một hướng).
2. Tạo collection trung gian **join/association collection** để mỗi document biểu diễn một cặp liên kết. Đây thường là lựa chọn linh hoạt khi số lượng liên kết lớn hoặc liên kết có thuộc tính riêng.

### 5.1. Nhúng mảng ID khi quan hệ nhỏ, có giới hạn

Ví dụ một bài viết có tập thẻ nhỏ và ổn định:

```javascript
// posts
{
  _id: "POST-01",
  title: "MongoDB cơ bản",
  tagIds: ["mongo", "nosql", "database"]
}

// tags
{ _id: "mongo", name: "MongoDB" }
{ _id: "nosql", name: "NoSQL" }
{ _id: "database", name: "Database" }
```

Một tag có thể gắn với nhiều post; mỗi post có nhiều tag. Truy vấn post theo tag:

```javascript
db.posts.find({ tagIds: "mongo" });
db.posts.createIndex({ tagIds: 1 });
```

MongoDB có thể đối chiếu một giá trị với các phần tử trong mảng và tạo **multikey index** cho trường mảng. Mô hình này phù hợp nếu mỗi post chỉ có một số lượng tag giới hạn và không cần lưu nhiều thuộc tính trên từng mối liên kết.

Không nên tự động thêm `postIds` vào mỗi tag và cập nhật đồng thời với `posts.tagIds` nếu chưa có lý do rõ ràng; việc nhân đôi hai chiều tạo gánh nặng đồng bộ.

### 5.2. Collection trung gian cho N:N lớn hoặc có thuộc tính riêng

Trong hệ thống học trực tuyến, bản thân quan hệ đăng ký có thể chứa:

- thời điểm đăng ký (`enrolledAt`);
- trạng thái (`ACTIVE`, `CANCELLED`);
- tiến độ hoặc điểm số;
- mã học kỳ/lần mở lớp nếu học viên được đăng ký lại ở những đợt khác.

Khi đó collection `enrollments` là một thực thể nghiệp vụ:

```text
students                  enrollments                     courses
_id = S01   <--- studentId = S01, courseId = C01 --->   _id = C01
_id = S02   <--- studentId = S02, courseId = C01 --->
            <--- studentId = S01, courseId = C02 --->   _id = C02
```

Mỗi enrollment có một document riêng. Phía `students` và `courses` không cần chứa mảng toàn bộ các liên kết.

### 5.3. Thực hành tạo ba collection

Tiếp tục phiên `mongosh` có `lab` và `runId` từ mục 3.3:

```javascript
const studentAnId = new ObjectId();
const studentBinhId = new ObjectId();
const courseMongoId = new ObjectId();
const courseJavaId = new ObjectId();

lab.students.insertMany([
  { _id: studentAnId, runId: runId, name: "An" },
  { _id: studentBinhId, runId: runId, name: "Bình" }
]);

lab.courses.insertMany([
  { _id: courseMongoId, runId: runId, title: "MongoDB cơ bản" },
  { _id: courseJavaId, runId: runId, title: "Java nền tảng" }
]);

// Chỉ một enrollment cho mỗi cặp studentId + courseId.
lab.enrollments.createIndex(
  { studentId: 1, courseId: 1 },
  { unique: true }
);

// Dùng khi truy vấn danh sách học viên theo khóa học.
lab.enrollments.createIndex({ courseId: 1, studentId: 1 });

const enrollment1Id = new ObjectId();
const enrollment2Id = new ObjectId();
const enrollment3Id = new ObjectId();

lab.enrollments.insertMany([
  {
    _id: enrollment1Id,
    runId: runId,
    studentId: studentAnId,
    courseId: courseMongoId,
    status: "ACTIVE",
    enrolledAt: ISODate("2026-11-10T01:00:00Z")
  },
  {
    _id: enrollment2Id,
    runId: runId,
    studentId: studentAnId,
    courseId: courseJavaId,
    status: "ACTIVE",
    enrolledAt: ISODate("2026-11-11T02:00:00Z")
  },
  {
    _id: enrollment3Id,
    runId: runId,
    studentId: studentBinhId,
    courseId: courseMongoId,
    status: "ACTIVE",
    enrolledAt: ISODate("2026-11-12T03:00:00Z")
  }
]);
```

Ở đây quan hệ là:

- An đăng ký MongoDB và Java.
- Bình đăng ký MongoDB.
- Khóa MongoDB có cả An và Bình.

**Index duy nhất ghép** `{ studentId: 1, courseId: 1 }` bảo đảm không có hai enrollment cho cùng một cặp, theo quy tắc “mỗi học viên chỉ có một quan hệ đăng ký trên mỗi khóa học”. Nếu ứng dụng cho phép đăng ký lại theo các đợt khác nhau, cần đưa `offeringId`/`termId` vào khóa duy nhất hoặc mô hình hóa thêm thực thể lần mở lớp, thay vì dùng khóa duy nhất quá chặt.

### 5.4. Truy vấn N:N theo cả hai hướng

Tìm các khóa mà An đã đăng ký:

```javascript
lab.enrollments.find(
  { studentId: studentAnId },
  { _id: 0, courseId: 1, status: 1, enrolledAt: 1 }
);
```

Tìm học viên của khóa MongoDB:

```javascript
lab.enrollments.find(
  { courseId: courseMongoId },
  { _id: 0, studentId: 1, status: 1 }
);
```

Lấy tên khóa học thay vì chỉ ID:

```javascript
lab.enrollments.aggregate([
  { $match: { studentId: studentAnId } },
  {
    $lookup: {
      from: "courses",
      localField: "courseId",
      foreignField: "_id",
      as: "course"
    }
  },
  { $unwind: "$course" },
  {
    $project: {
      _id: 0,
      status: 1,
      enrolledAt: 1,
      courseId: "$course._id",
      courseTitle: "$course.title"
    }
  },
  { $sort: { enrolledAt: -1 } }
]);
```

Ngược lại, muốn lấy tên học viên của course, thực hiện `$match` theo `courseId` rồi `$lookup` đến collection `students` qua `studentId`. Collection trung gian cho phép truy vấn hai chiều và thêm thuộc tính của **chính mối quan hệ**.

### 5.5. Có nên lưu cả `studentIds` trong course và `courseIds` trong student?

Chỉ nên làm vậy khi có nhu cầu cụ thể, ví dụ cache một danh sách nhỏ được giới hạn. Nếu mỗi bên giữ một mảng toàn bộ ID của phía kia, một lần đăng ký mới có thể cần cập nhật hai document (hoặc nhiều hơn nếu kèm enrollment), làm tăng nguy cơ dữ liệu lệch nhau.

Với liên kết nhiều–nhiều có thể tăng lớn, collection `enrollments` thường là **nguồn dữ liệu chuẩn**. Các trường đếm hoặc danh sách ngắn trên `students`/`courses` nếu có chỉ là dữ liệu dẫn xuất, được cập nhật theo một quy trình xác định.

## 6. Ràng buộc quan hệ: MongoDB tự bảo đảm điều gì?

### 6.1. Mỗi document có `_id` duy nhất, nhưng tham chiếu không phải khóa ngoại

MongoDB mặc định tạo unique index cho `_id` trong collection. Có thể tạo unique index trên trường khác hoặc kết hợp nhiều trường. Tuy nhiên:

```javascript
// MongoDB có thể nhận document như sau nếu không có kiểm tra bổ sung:
{
  _id: "ORDER-NOT-FOUND",
  customerId: "CUSTOMER-DOES-NOT-EXIST"
}
```

Việc đặt tên `customerId` không tạo ràng buộc tự động rằng document customer phải tồn tại. Muốn bảo vệ quan hệ, ứng dụng thường thực hiện xác minh thực thể đích khi tạo bản ghi, có chính sách xử lý xóa cha và chọn giao dịch khi cần giữ nhiều thao tác đồng thời.

### 6.2. Những quy tắc nào có thể đặt bằng index?

| Quy tắc nghiệp vụ | Biện pháp ở MongoDB | Giới hạn của biện pháp |
| --- | --- | --- |
| Một document có một định danh trong collection | Unique index mặc định trên `_id` | Chỉ trong phạm vi collection |
| Mỗi user tối đa một preferences | `unique` trên `userPreferences.userId` | Không bắt buộc phải có user thật |
| Không đăng ký trùng một cặp student–course | `unique` trên `{studentId:1,courseId:1}` | Không kiểm tra student/course còn tồn tại |
| Truy vấn nhiều order theo một customer nhanh hơn | Index trên `customerId`, có thể ghép `createdAt` | Index tối ưu truy vấn, không bảo đảm khóa ngoại |
| Kiểm tra trường và kiểu dữ liệu | Collection validation, ví dụ `$jsonSchema` | Không thay thế toàn bộ quy tắc quan hệ xuyên collection |

Index duy nhất đảm bảo **tính duy nhất** theo các trường được index; không tự xác định số phần tử tối thiểu trong một quan hệ và không thay thế kiểm tra logic ở tầng nghiệp vụ.

### 6.3. Validation cho định danh tham chiếu

Ở mức schema, có thể yêu cầu `studentId` và `courseId` là ObjectId để tránh dữ liệu sai kiểu:

```javascript
db.createCollection("validatedEnrollments", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["studentId", "courseId", "status"],
      properties: {
        studentId: { bsonType: "objectId" },
        courseId: { bsonType: "objectId" },
        status: {
          enum: ["ACTIVE", "CANCELLED"]
        }
      }
    }
  }
});
```

`validatedEnrollments` chỉ là collection minh họa riêng. Validation có thể kiểm soát hình dạng và kiểu của document, nhưng không tự kiểm tra xem `studentId` thật sự xuất hiện trong collection `students`.

### 6.4. Atomicity trên một document và giao dịch nhiều document

Với document nhúng, một lệnh như `updateOne` thay đổi nhiều trường trong cùng document có tính nguyên tử ở phạm vi document đó. Với thao tác cần ghi vào nhiều collection, có thể phải cân nhắc **multi-document transaction** khi quy tắc nghiệp vụ yêu cầu các cập nhật cùng thành công hoặc cùng thất bại.

Ví dụ nghiệp vụ đăng ký khóa học có thể gồm ghi enrollment và giảm số ghế còn lại. Nếu chỉ ghi enrollment thành công mà số ghế không giảm, dữ liệu có thể mất nhất quán. Việc dùng transaction cần triển khai phù hợp với topology và môi trường MongoDB, đồng thời xử lý retry, lỗi tạm thời và tranh chấp ghi theo đúng quy tắc nghiệp vụ.

Một cách biểu đạt luồng xử lý:

```text
Bắt đầu giao dịch
    |
    +--> Kiểm tra/cập nhật sức chứa khóa học bằng điều kiện phù hợp
    |
    +--> Tạo enrollment (unique index chặn đăng ký trùng)
    |
    +--> Nếu tất cả thành công: COMMIT
    |
    +--> Nếu một bước lỗi: ABORT
```

Không phải mỗi quan hệ giữa hai collection đều cần transaction: một tham chiếu chỉ để đọc có thể chấp nhận chiến lược xử lý eventual consistency hoặc kiểm tra bằng ứng dụng. Cần xác định **điều kiện bất biến** (invariant) của nghiệp vụ trước khi chọn chi phí đồng bộ.

### 6.5. Xử lý khi xóa hoặc thay đổi quan hệ

Trong cơ sở dữ liệu quan hệ, khóa ngoại có thể được cấu hình hành vi `ON DELETE CASCADE`. Trong MongoDB, **không có tự động cascade** chỉ vì field `customerId` tham chiếu đến customer.

Ứng dụng phải quyết định:

- **Restrict:** không cho xóa customer khi còn order cần lưu.
- **Soft delete:** đánh dấu customer ngừng hoạt động, giữ order phục vụ lịch sử/kiểm toán.
- **Cascade do ứng dụng thực hiện:** xóa hoặc vô hiệu hóa document liên quan theo một quy trình được kiểm soát.
- **Detach:** loại tham chiếu khi nghiệp vụ cho phép bản ghi con sống độc lập.

Ví dụ hệ thống thương mại điện tử thường cần giữ đơn hàng ngay cả khi tài khoản khách hàng bị khóa; xóa tất cả đơn hàng theo customer có thể sai yêu cầu kế toán và lịch sử.

## 7. Thiết kế truy vấn và index theo cardinality

### 7.1. Query patterns quyết định nhiều hơn tên quan hệ

Hai hệ thống đều có quan hệ customer–order nhưng có thể có nhu cầu khác nhau:

- Trang hồ sơ hiển thị 5 đơn gần đây.
- Trang quản trị lọc mọi đơn theo thời gian và trạng thái.
- Báo cáo thống kê số tiền theo tháng cho nhiều customer.
- API chi tiết đơn hàng cần snapshot giá từng sản phẩm.

Một mô hình thường phù hợp là `orders` riêng với `customerId` và `items` nhúng. Nhưng index phải theo những truy vấn quan trọng nhất, ví dụ:

```javascript
// Tìm lịch sử đơn hàng của một customer, mới nhất trước.
lab.orders.createIndex({ customerId: 1, createdAt: -1 });

// Khi thường lọc theo trạng thái riêng trong một customer:
lab.orders.createIndex({ customerId: 1, status: 1, createdAt: -1 });
```

Không nên tạo cả hai index chỉ vì có thể: mỗi index tốn lưu trữ và chi phí cập nhật khi ghi. Chọn index dựa trên truy vấn và dùng `explain()` để xem kế hoạch thực thi khi có dữ liệu đại diện.

### 7.2. Index cho nhiều–nhiều

Trong `enrollments`:

```javascript
lab.enrollments.createIndex(
  { studentId: 1, courseId: 1 },
  { unique: true }
);
lab.enrollments.createIndex({ courseId: 1, studentId: 1 });
```

Index đầu tiên giúp truy vấn theo `studentId` và chặn cặp trùng; index thứ hai phục vụ truy vấn theo `courseId`. Thứ tự các trường trong index ghép có ý nghĩa đối với khả năng tận dụng tiền tố của index. Ví dụ chỉ mục bắt đầu bằng `studentId` không mặc nhiên tối ưu cho truy vấn chỉ lọc `courseId`.

Với `$lookup`, trường được ghép ở collection đích nên có index thích hợp. Ghép theo `_id` thường tận dụng index mặc định; ghép theo `userPreferences.userId` có thể dùng unique index đã tạo.

### 7.3. Dùng `$lookup` khi nào?

`$lookup` cho phép kết hợp dữ liệu giữa các collection trong aggregation. Nó hữu ích khi API cần trả về một kết quả gộp hoặc báo cáo cần đối chiếu dữ liệu. Tuy nhiên:

- Vẫn phải xem số lượng document đầu vào, độ chọn lọc của `$match` và index của phía ghép.
- Một quan hệ N:N nhiều bản ghi có thể làm kết quả nở rất lớn nếu dùng `$lookup`/`$unwind` không giới hạn.
- Trong API truy vấn danh sách, nên lọc và phân trang hợp lý trước khi mở rộng dữ liệu nếu ngữ nghĩa truy vấn cho phép.
- Khi chỉ cần vài trường, sử dụng `$project` để giảm dữ liệu trả về.

Thiết kế document tốt không yêu cầu tuyệt đối “không dùng `$lookup`”. Quan trọng là chọn cấu trúc và truy vấn phù hợp với độ lớn dữ liệu và tần suất truy cập.

## 8. Những mô hình dễ trở thành vấn đề

| Cách tổ chức dữ liệu | Vấn đề khi mở rộng | Hướng cải thiện |
| --- | --- | --- |
| Một customer chứa mảng tất cả order | Mảng tăng vô hạn, document phình to; khó phân trang | Tách `orders`, đặt `customerId` trong order, tạo index |
| Mỗi course chứa mọi student ID và mỗi student chứa mọi course ID | Phải cập nhật hai phía; dễ thiếu/đúp quan hệ | Dùng collection `enrollments` làm nguồn chuẩn |
| Copy toàn bộ profile customer vào từng order | Dữ liệu lớn và dễ lệch nếu profile phải luôn cập nhật | Chỉ lưu snapshot thông tin cần giữ tại thời điểm mua; tham chiếu các thuộc tính hiện tại |
| Không dùng unique index cho quan hệ tối đa một | Hai yêu cầu đồng thời có thể tạo bản ghi trùng | Unique index phù hợp với khóa nghiệp vụ |
| Tin rằng tham chiếu tự kiểm tra tồn tại | Dễ tạo orphan document | Kiểm tra ở ứng dụng và xử lý thay đổi/xóa có chủ đích |
| Lưu ID với nhiều kiểu dữ liệu | `ObjectId` và string không khớp khi join | Chuẩn hóa kiểu khóa ở hai phía |
| Nhúng thông tin cập nhật quá thường xuyên ở nhiều nơi | Tăng chi phí đồng bộ, tạo dữ liệu cũ | Tham chiếu nguồn chuẩn hoặc định nghĩa cơ chế đồng bộ |
| Tạo index tùy ý cho mọi khóa | Chi phí ghi và dung lượng index tăng | Dựa trên query patterns và đo thực tế |
| Coi mọi N:N là hai mảng ID | Khó lưu thuộc tính của liên kết, dễ thiếu nhất quán | Association collection chứa bản ghi liên kết |

### 8.1. Trường hợp cardinality thay đổi theo thời gian

Một tính năng khởi đầu chỉ có “một người dùng có tối đa năm địa chỉ” có thể sau này trở thành “một tổ chức có hàng chục nghìn địa điểm”. Quan hệ 1:N vẫn giữ nguyên về logic nhưng **phân bố số lượng N** đã thay đổi, và cách nhúng ban đầu có thể không còn phù hợp. Khi thiết kế, nên nêu giả định về số lượng phần tử hiện tại và giới hạn dự kiến.

### 8.2. Embedded document vẫn có vòng đời nghiệp vụ

Khi nhúng dữ liệu, cần xác định liệu phần tử con có cần định danh riêng hay không. Ví dụ một giỏ hàng có thể nhúng `items`, nhưng từng item đôi khi cần `itemId` để cập nhật chính xác trong mảng. Nếu phần tử được chỉnh sửa độc lập nhiều, tìm kiếm xuyên nhiều cha hoặc có vòng đời kéo dài, một collection riêng có thể đơn giản hơn.

### 8.3. Phân biệt snapshot với dữ liệu “luôn cập nhật”

Order thường lưu `shippingAddress`, `unitPrice` hoặc `productName` tại thời điểm đặt mua. Dù dữ liệu này có vẻ trùng với customer/product, nó được giữ như **snapshot lịch sử** và không nên tự động thay đổi. Ngược lại, ảnh đại diện hiện tại của customer nếu copy vào mọi order có thể làm hệ thống phải đồng bộ không cần thiết. Cần ghi rõ trường nào là snapshot, trường nào là tham chiếu đến nguồn chuẩn.

## 9. Quy trình lựa chọn mô hình cho một yêu cầu mới

Giả sử cần thiết kế tính năng “người dùng theo dõi tác giả và tác giả có nhiều người theo dõi”. Có thể bắt đầu theo các bước:

1. **Xác định quan hệ:** một người dùng theo dõi nhiều tác giả, một tác giả có nhiều người theo dõi → N:N.
2. **Đo cỡ quan hệ:** người nổi tiếng có thể có hàng triệu người theo dõi → không nhúng toàn bộ ID vào một document tác giả.
3. **Xác định truy vấn chính:** danh sách tác giả đang theo dõi, đếm số người theo dõi, kiểm tra có theo dõi hay chưa.
4. **Đặt nguồn sự thật:** collection `follows` chứa `followerId`, `authorId`, `followedAt`.
5. **Ngăn trùng:** unique index trên `{ followerId: 1, authorId: 1 }`.
6. **Tối ưu hai hướng:** index ngược `{ authorId: 1, followerId: 1 }` khi cần tìm người theo dõi của một tác giả.
7. **Quy định xóa:** bỏ theo dõi xóa một liên kết; khóa tài khoản cần chính sách xử lý các liên kết có liên quan.

Document có thể có dạng:

```javascript
{
  followerId: ObjectId("64b64a000000000000000001"),
  authorId: ObjectId("64b64a000000000000000002"),
  followedAt: ISODate("2026-11-14T08:00:00Z")
}
```

Nếu ứng dụng hiển thị số follower ngay trên danh sách tác giả, có thể cân nhắc một trường đếm được duy trì có kiểm soát. Khi đó `follows` vẫn là nguồn dữ liệu liên kết, còn số đếm là dữ liệu dẫn xuất cần cơ chế cập nhật/chấp nhận độ trễ phù hợp.

## 10. Bài thực hành tổng hợp: quan hệ nào nên dùng?

Với mỗi tình huống, hãy phân tích ba yếu tố: **cardinality**, **số lượng dự kiến**, **cách truy vấn**.

| Tình huống | Cách khởi đầu nên cân nhắc | Vì sao |
| --- | --- | --- |
| Tài khoản có một cấu hình giao diện nhỏ | Nhúng object `preferences` | Nhỏ, thường đọc cùng account |
| Tài khoản có một hồ sơ y tế hoặc dữ liệu phân quyền riêng | Collection riêng, tham chiếu 1:1 và unique index | Vòng đời/chính sách truy cập khác nhau |
| Một order có vài dòng hàng | Nhúng `items` trong order | Đọc cùng, snapshot lịch sử và số lượng có giới hạn |
| Một user có hàng nghìn order | Collection `orders` và `customerId` | Tăng lâu dài, cần phân trang và lọc |
| Bài viết có vài tag | Mảng `tagIds` có giới hạn | Mô hình N:N đơn giản; có thể query theo tag |
| Học viên tham gia nhiều course, có điểm và trạng thái | Collection `enrollments` | Quan hệ N:N có thuộc tính và vòng đời riêng |
| Người dùng theo dõi tài khoản có quy mô lớn | Collection `follows` | Quan hệ N:N tăng lớn, cần truy vấn hai chiều |

### 10.1. Kiểm tra dữ liệu đã tạo trong bài thực hành

Nếu đã chạy các ví dụ trong **cùng phiên `mongosh`**, có thể đối chiếu:

```javascript
print("userPreferences=" +
  lab.userPreferences.countDocuments({ userId: userId }));

print("ordersOfUser=" +
  lab.orders.countDocuments({ customerId: userId }));

print("enrollmentsOfAn=" +
  lab.enrollments.countDocuments({ studentId: studentAnId }));

print("studentsOfMongoCourse=" +
  lab.enrollments.countDocuments({ courseId: courseMongoId }));
```

Với dữ liệu mẫu và khi chưa thay đổi gì, các số lượng tương ứng là `1`, `2`, `2`, `2`.

### 10.2. Dọn dữ liệu thử nghiệm theo dấu nhận diện riêng

Các ví dụ tạo dữ liệu trong database `mongo_relations_lab` với `runId` duy nhất. Trước khi dọn, xác nhận đúng kết nối và xem trước số bản ghi do lượt chạy này tạo:

```javascript
const ownedCollections = [
  "enrollments",
  "courses",
  "students",
  "orders",
  "userPreferences",
  "users"
];

print("database=" + lab.getName());
print("runId=" + runId);
for (const name of ownedCollections) {
  const collection = lab.getCollection(name);
  print(name + "=" + collection.countDocuments({ runId: runId }));
  printjson(
    collection.find(
      { runId: runId },
      { _id: 1, runId: 1 }
    ).limit(10).toArray()
  );
}
```

Nếu danh sách khớp với **dữ liệu mà bạn vừa tạo** và đó là môi trường thử nghiệm của bạn, có thể dọn chỉ theo `runId` đã xác nhận:

```javascript
// Chỉ chạy sau khi xác nhận đúng database, runId và số bản ghi ở trên.
for (const name of ownedCollections) {
  const collection = lab.getCollection(name);
  const result = collection.deleteMany({ runId: runId });
  print(name + ": deleted=" + result.deletedCount);
}

// Kiểm tra không còn document của lượt thực hành.
for (const name of ownedCollections) {
  print(name + ": remaining=" +
    lab.getCollection(name).countDocuments({ runId: runId }));
}
```

Không dùng `deleteMany({})`, `drop()` hoặc `dropDatabase()` để dọn bài tập khi môi trường có thể được chia sẻ. Nếu không nhớ `runId` hoặc kết quả xem trước bất thường, dừng lại để xác định đúng dữ liệu sở hữu trước khi xóa.

## 11. Tự kiểm tra kiến thức

1. Vì sao quan hệ 1:1 có thể lưu bằng object nhúng hoặc bằng một collection riêng? Điều gì quyết định lựa chọn?
2. Unique index trên `userPreferences.userId` có tự ngăn một document trỏ đến user không tồn tại không?
3. Vì sao `orders.customerId` thường linh hoạt hơn mảng toàn bộ `customers.orderIds` khi lịch sử đơn hàng tăng mãi?
4. Trong quan hệ student–course, khi nào mảng `courseIds` là đủ? Khi nào cần collection `enrollments`?
5. Nếu mỗi enrollment có `status`, `enrolledAt` và `score`, các trường đó thuộc thực thể student, course hay bản thân liên kết?
6. Vì sao cần index khác nhau khi truy vấn enrollment theo student và theo course?
7. Nếu xóa một customer, MongoDB có tự xóa tất cả order tham chiếu đến customer đó không? Ứng dụng nên quyết định những chính sách nào?
8. Trường hợp nào một bản sao dữ liệu trong order là snapshot nghiệp vụ đúng đắn, và trường hợp nào nó chỉ tạo rủi ro lệch dữ liệu?

**Điểm cốt lõi:** cardinality trả lời **“các thực thể liên hệ với nhau thế nào”**; embedding, referencing, index và quy trình ghi trả lời **“lưu và truy cập quan hệ đó thế nào trong MongoDB”**. Một thiết kế tốt xuất phát từ số lượng thực tế, mẫu truy vấn, vòng đời dữ liệu và mức nhất quán mà nghiệp vụ yêu cầu.
