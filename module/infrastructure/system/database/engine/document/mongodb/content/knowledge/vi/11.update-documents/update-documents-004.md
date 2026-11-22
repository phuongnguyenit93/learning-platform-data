# Cập nhật số và thời gian với $inc, $mul, $min, $max và $currentDate

Trong MongoDB, thao tác cập nhật không bắt buộc phải đọc document về ứng dụng, tính toán một giá trị mới rồi ghi cả document trở lại. Các **update operator** cho phép yêu cầu máy chủ thực hiện phép cộng, phép nhân, so sánh giới hạn hoặc lấy thời điểm hiện tại trực tiếp trên những trường được chỉ định.

Năm toán tử thường gặp là:

| Toán tử | Ý nghĩa | Ví dụ nghiệp vụ |
|---|---|---|
| `$inc` | Tăng hoặc giảm giá trị số theo một lượng | Tăng lượt xem, giảm tồn kho, cộng số lần thử |
| `$mul` | Nhân giá trị số với hệ số | Điều chỉnh giá theo tỷ lệ, quy đổi một chỉ số |
| `$min` | Chỉ thay nếu giá trị đề xuất **nhỏ hơn** giá trị hiện tại | Ghi nhận điểm thấp nhất, ngày bắt đầu sớm nhất |
| `$max` | Chỉ thay nếu giá trị đề xuất **lớn hơn** giá trị hiện tại | Ghi nhận điểm cao nhất, thời điểm sự kiện muộn nhất |
| `$currentDate` | Ghi ngày giờ hiện tại do máy chủ xử lý update | `updatedAt`, thời điểm thay đổi trạng thái |

Các toán tử này dùng được trong `updateOne()`, `updateMany()` và những API cập nhật tương ứng. Một thao tác cập nhật **một document là nguyên tử**, nên phép tính giá trị mới diễn ra trong chính thao tác ghi đó. Tuy nhiên, điều này **không tự tạo giao dịch nguyên tử giữa nhiều document** và không biến mọi phép cập nhật thành idempotent khi lệnh bị gửi lại.

## 1. Chuẩn bị dữ liệu và hiểu cấu trúc update

Giả sử collection `inventory` lưu sản phẩm cùng các số liệu vận hành:

```javascript
db.inventory.insertMany([
  {
    _id: "SKU-101",
    name: "Bàn phím cơ",
    price: NumberDecimal("1200000.00"),
    stock: NumberInt(40),
    metrics: {
      views: NumberLong("250"),
      sold: NumberLong("12"),
      ratingMax: 4.5,
      ratingMin: 3.0
    },
    firstSoldAt: ISODate("2026-03-10T08:00:00Z"),
    lastSoldAt: ISODate("2026-03-15T16:00:00Z"),
    updatedAt: ISODate("2026-03-15T16:00:00Z")
  },
  {
    _id: "SKU-102",
    name: "Chuột không dây",
    price: NumberDecimal("350000.00"),
    stock: NumberInt(8),
    metrics: { views: NumberLong("30") }
  }
]);
```

Các giá trị số BSON có thể là `Int32`, `Int64`, `Double` hoặc `Decimal128`. Trường `updatedAt` chứa BSON Date, khác với chuỗi ISO được lưu dưới dạng String.

Hình thức chung:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },                // Filter: document cần cập nhật
  { $inc: { stock: -2 } }             // Update: thao tác trên field
);
```

Khác với cập nhật thay thế toàn document, **update document** dùng các toán tử như `$inc`, `$set` và `$currentDate` để sửa đúng trường cần thiết. Có thể phối hợp **nhiều toán tử khác nhau trên các đường dẫn không xung đột**:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  {
    $inc: {
      stock: -2,
      "metrics.sold": 2
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
```

Dấu chấm trong `"metrics.sold"` là **dot notation** để truy cập trường lồng nhau. Nếu parent là object phù hợp, cập nhật có thể tạo trường con chưa tồn tại. Nếu parent đang là kiểu không thể chứa đường dẫn đó, chẳng hạn `metrics: null`, thao tác có thể lỗi thay vì tự biến mọi giá trị thành object.

## 2. $inc: cộng hoặc trừ một lượng số

Cú pháp:

```javascript
{ $inc: { fieldName: amount } }
```

Với `amount > 0`, giá trị tăng. Với `amount < 0`, giá trị giảm. Có thể thay đổi nhiều trường số trong cùng một document bằng một update.

### 2.1. Tăng số lượt xem

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  {
    $inc: { "metrics.views": NumberLong("1") }
  }
);
```

Nếu `metrics.views` trước đó là `250`, kết quả sau một lần cập nhật thành `251`.

### 2.2. Giảm số lượng hàng tồn

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  { $inc: { stock: -3 } }
);
```

Nếu `stock` trước đó là `40` thì giảm còn `37`. Tuy nhiên, chỉ dùng `$inc: -3` **không ngăn tồn kho âm** khi lượng hàng còn ít hơn mức cần trừ.

Để bảo vệ invariant không bán quá tồn kho, đặt điều kiện ngay trong filter:

```javascript
const quantity = 3;

const result = db.inventory.updateOne(
  {
    _id: "SKU-101",
    stock: { $gte: quantity }
  },
  {
    $inc: { stock: -quantity },
    $currentDate: { updatedAt: true }
  }
);

if (result.modifiedCount !== 1) {
  print("Sản phẩm không tồn tại hoặc không còn đủ tồn kho");
}
```

Bộ lọc và phép giảm được kiểm tra trong **một thao tác ghi nguyên tử trên document**. Khi hai request cùng mua sản phẩm gần như đồng thời, điều kiện `stock >= quantity` được đánh giá theo trạng thái áp dụng của mỗi cập nhật, tránh mô hình đọc số cũ ở ứng dụng rồi cùng ghi đè.

Nếu còn phải tạo đơn hàng ở collection khác hoặc gọi cổng thanh toán ngoài, phải thiết kế transaction hoặc quy trình nghiệp vụ bổ sung; phép giảm tồn kho đơn lẻ không tự bao trùm toàn bộ hệ thống.

### 2.3. $inc với trường thiếu và null

Hai trạng thái quan trọng:

| Giá trị trường trước update | `$inc: { count: 2 }` |
|---|---|
| `count: 5` | Thành `7` |
| Không tồn tại `count` | Tạo `count: 2` |
| `count: 0` | Thành `2` |
| `count: null` | **Lỗi**, không tự xem null là 0 |
| `count: "5"` | Không phải trường numeric hợp lệ; thao tác lỗi |

Ví dụ:

```javascript
db.counterLab.insertMany([
  { _id: "missing" },
  { _id: "isNull", count: null },
  { _id: "five", count: NumberInt(5) }
]);

// Tạo count = 2 vì trường chưa tồn tại:
db.counterLab.updateOne(
  { _id: "missing" },
  { $inc: { count: 2 } }
);

// Trường count đang null -> thao tác lỗi:
db.counterLab.updateOne(
  { _id: "isNull" },
  { $inc: { count: 2 } }
);
```

Đừng dựa vào việc `$inc` tự xử lý `null`. Khi dữ liệu legacy có thể chứa null/string, cần chuẩn hóa schema hoặc migration trước khi cập nhật. Có thể kiểm tra kiểu bằng `$type`, tạo validator cho trường numeric và thống nhất xử lý lỗi.

### 2.4. Vì sao $inc an toàn hơn đọc–cộng–set?

Cách dễ bị **lost update**:

```javascript
const product = db.inventory.findOne({ _id: "SKU-101" });
const newViews = product.metrics.views + 1;

db.inventory.updateOne(
  { _id: "SKU-101" },
  { $set: { "metrics.views": newViews } }
);
```

Hai request có thể cùng đọc `250`, rồi cùng `$set` thành `251`: một lượt tăng biến mất.

Dùng:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  { $inc: { "metrics.views": NumberLong("1") } }
);
```

MongoDB tính toán cộng trên trạng thái của document trong thao tác ghi, tránh lỗi lost update theo mẫu đọc–ghi ở trên. Đây là **nguyên tử một document**, không phải bảo đảm mỗi yêu cầu nghiệp vụ sẽ luôn chỉ được thực thi một lần dưới mọi tình huống retry.

## 3. $mul: nhân giá trị hiện tại với một hệ số

Cú pháp:

```javascript
{ $mul: { fieldName: multiplier } }
```

Trường đích phải có giá trị số thích hợp. Hệ số có thể là số nguyên, Double hoặc Decimal128. Một trường hợp ứng dụng là tăng giá theo tỷ lệ:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  {
    $mul: {
      price: NumberDecimal("1.05")
    },
    $currentDate: { updatedAt: true }
  }
);
```

Với giá ban đầu `1200000.00`, giá mới sau một lần nhân là `1260000.0000` về giá trị toán học (cách hiển thị Decimal128 có thể khác). Hãy thiết kế quy tắc **làm tròn tiền** theo đơn vị và hợp đồng nghiệp vụ; `$mul` không tự hiểu rằng tiền phải luôn có đúng hai chữ số thập phân.

### 3.1. Hệ số lớn hơn, nhỏ hơn hoặc bằng 1

| Hệ số | Ý nghĩa | Ví dụ giá ban đầu 200 |
|---:|---|---:|
| `2` | Gấp đôi | 400 |
| `1.10` | Tăng 10% | 220 |
| `0.80` | Giảm 20% | 160 |
| `1` | Không đổi giá trị | 200 |
| `0` | Đặt kết quả bằng 0 | 0 |
| `-1` | Đổi dấu | -200 |

Chỉ nên dùng `$mul` nếu nghiệp vụ thực sự muốn phép **nhân trên giá trị hiện tại**. Nếu mục tiêu là “giá khuyến mại cố định bằng 80% giá gốc”, gọi `$mul: 0.8` mỗi lần request được xử lý sẽ tạo ra giảm giá lặp:

```text
Giá gốc:                  200
Sau lần $mul 0.8 đầu:     160
Sau lần $mul 0.8 tiếp:    128
```

Tác vụ có thể retry, được chạy lại theo lịch hoặc nhiều worker cùng xử lý cần một **mốc giá chuẩn** hoặc cơ chế idempotency. Đừng coi `$mul` là phép ghi idempotent.

### 3.2. $mul với trường thiếu: tạo giá trị 0

Khác `$inc`, nếu trường không tồn tại, `$mul` tạo trường mới với **giá trị 0 cùng kiểu numeric với toán hạng nhân**:

```javascript
db.priceLab.insertOne({ _id: "missingPrice" });

db.priceLab.updateOne(
  { _id: "missingPrice" },
  { $mul: { price: NumberDecimal("1.20") } }
);

// price được tạo bằng giá trị Decimal128 0,
// KHÔNG phải 1.20 và cũng không phải null.
```

Điều này hợp lý theo phép nhân với một giá trị mặc định 0 ở cấp cập nhật, nhưng **không tạo ra giá khởi điểm đúng nghiệp vụ**. Nếu muốn “chưa có giá thì dùng giá mặc định, ngược lại nhân hệ số”, cần thiết kế update theo điều kiện hoặc aggregation pipeline thay vì dùng `$mul` đơn thuần.

Với trường đã tồn tại, `$mul` yêu cầu giá trị số. Không dùng trực tiếp trên một string hay `null` và trông chờ MongoDB tự ép kiểu sang số.

### 3.3. Kiểu số và độ chính xác khi nhân

MongoDB có `Int32`, `Int64`, `Double` và `Decimal128`. Khi hai toán hạng khác kiểu, MongoDB có quy tắc **chuyển kiểu số** cho `$mul`:

- `Int32 × Int32` có thể cho `Int32` hoặc tăng lên `Int64` khi vượt ngưỡng 32 bit.
- `Int64 × Int64` giữ kiểu `Int64` khi kết quả trong giới hạn hỗ trợ.
- Phép toán có `Double` có thể cho kết quả kiểu Double nếu không có Decimal128 tham gia.
- Nếu một toán hạng là `Decimal128`, kết quả thuộc nhóm Decimal128 theo quy tắc chuyển kiểu.

Các phép nhân integer vượt giới hạn Int64 có thể báo lỗi; cần tránh giả định MongoDB luôn tự chuyển vô hạn sang số lớn. Với số tiền, cân nhắc `Decimal128` hoặc số nguyên đại diện đơn vị tiền nhỏ nhất, kèm quy tắc làm tròn và giới hạn miền giá trị.

Ví dụ dùng Decimal128 cho hệ số:

```javascript
db.inventory.updateOne(
  { _id: "SKU-102" },
  {
    $mul: { price: NumberDecimal("0.95") }
  }
);
```

Nếu `price` đã là Decimal128 thì kết quả được tính theo kiểu decimal tương ứng. Nếu vô tình dùng Double cho một phần chuỗi xử lý, có thể phát sinh sai số biểu diễn dấu phẩy động.

## 4. $min: chỉ thay khi giá trị mới nhỏ hơn

Cú pháp:

```javascript
{ $min: { fieldName: candidateValue } }
```

MongoDB so sánh giá trị hiện tại với giá trị đề xuất. Nếu đề xuất **nhỏ hơn**, trường được thay bằng đề xuất; nếu đề xuất **bằng hoặc lớn hơn**, trường giữ nguyên. Nếu trường **chưa tồn tại**, MongoDB tạo trường với giá trị đề xuất.

### 4.1. Lưu điểm thấp nhất

```javascript
db.playerStats.insertOne({
  _id: "player-01",
  bestScore: 900,
  worstScore: 120
});

db.playerStats.updateOne(
  { _id: "player-01" },
  { $min: { worstScore: 95 } }
);

// worstScore: 95

db.playerStats.updateOne(
  { _id: "player-01" },
  { $min: { worstScore: 150 } }
);

// worstScore vẫn là 95.
```

Dùng `$min` khi muốn lưu **minimum đã quan sát được** mà không cần ứng dụng đọc lại giá trị cũ.

### 4.2. Ghi nhận ngày sớm nhất

```javascript
db.userActivity.insertOne({
  _id: "user-01",
  firstSeenAt: ISODate("2026-04-20T10:00:00Z")
});

db.userActivity.updateOne(
  { _id: "user-01" },
  {
    $min: {
      firstSeenAt: ISODate("2026-04-15T09:30:00Z")
    }
  }
);

// firstSeenAt thành 2026-04-15T09:30:00Z.
```

Với field được thống nhất kiểu BSON Date, `$min` là cách gọn để ghi nhận **thời điểm sớm nhất** trong nhiều sự kiện có thể tới không theo thứ tự. Tuy nhiên, thời gian sự kiện từ hệ thống ngoài có thể khác thời gian server xử lý update; cần phân biệt rõ hai khái niệm này.

### 4.3. $min không phải phép lấy nhỏ nhất trên nhiều document

`$min` trong **update document** giữ minimum của một trường thuộc **một document đang được cập nhật**. Nó khác toán tử `$min` dùng trong aggregation `$group` để tính minimum trên **nhiều document**:

```javascript
// Update: giữ điểm thấp nhất bên trong document player-01.
db.playerStats.updateOne(
  { _id: "player-01" },
  { $min: { worstScore: 80 } }
);

// Aggregation: tính điểm nhỏ nhất trên tập document.
db.playerStats.aggregate([
  {
    $group: {
      _id: null,
      minScoreAcrossPlayers: { $min: "$worstScore" }
    }
  }
]);
```

Tên toán tử giống nhau nhưng **ngữ cảnh, cú pháp và mục đích khác nhau**.

## 5. $max: chỉ thay khi giá trị mới lớn hơn

Cú pháp:

```javascript
{ $max: { fieldName: candidateValue } }
```

Nếu giá trị đề xuất **lớn hơn**, thay trường; nếu bằng hoặc nhỏ hơn, giữ nguyên. Trường thiếu được tạo với giá trị đề xuất.

### 5.1. Điểm cao nhất

```javascript
db.playerStats.updateOne(
  { _id: "player-01" },
  { $max: { bestScore: 950 } }
);

// bestScore: 950

db.playerStats.updateOne(
  { _id: "player-01" },
  { $max: { bestScore: 870 } }
);

// bestScore vẫn là 950.
```

Có thể theo dõi cực trị của cùng một luồng dữ liệu bằng cách cập nhật **hai field khác nhau** trong một thao tác:

```javascript
const observedScore = 785;

db.playerStats.updateOne(
  { _id: "player-01" },
  {
    $min: { worstScore: observedScore },
    $max: { bestScore: observedScore },
    $currentDate: { updatedAt: true }
  }
);
```

Đoạn này có ý nghĩa khi `worstScore`, `bestScore` cùng dùng một kiểu số và được tính từ cùng đơn vị/tiêu chuẩn đo.

### 5.2. Ghi thời điểm muộn nhất

```javascript
db.userActivity.updateOne(
  { _id: "user-01" },
  {
    $max: {
      lastSeenAt: ISODate("2026-04-21T18:45:00Z")
    }
  }
);
```

Nếu sự kiện tới chậm theo mạng, `$max` giúp tránh một sự kiện cũ ghi đè `lastSeenAt` bằng thời điểm sớm hơn.

**Đừng nhầm `lastSeenAt` từ event timestamp với `updatedAt` do server ghi.** Khi ingest sự kiện lịch sử, một event của tháng trước vẫn có thể được nhập hôm nay; `lastSeenAt` nên phản ánh sự kiện mới nhất đã biết, còn `updatedAt` phản ánh lúc record được cập nhật.

## 6. $min/$max so sánh theo thứ tự BSON, kể cả khi khác kiểu

Một khác biệt quan trọng: `$min` và `$max` không bắt buộc hai giá trị cùng kiểu số. Chúng có thể dùng **thứ tự so sánh BSON** khi gặp các kiểu khác nhau.

Thứ tự liên quan, từ thấp đến cao:

```text
MinKey < Null < Number < String < Object < Array < BinData
       < ObjectId < Boolean < Date < Timestamp < ... < MaxKey
```

Ví dụ:

```javascript
db.mixedTypeLab.insertOne({
  _id: "demo",
  threshold: null
});

db.mixedTypeLab.updateOne(
  { _id: "demo" },
  { $max: { threshold: 100 } }
);

// Number xếp sau Null -> threshold trở thành 100.

db.mixedTypeLab.updateOne(
  { _id: "demo" },
  { $min: { threshold: "50" } }
);

// String xếp sau Number theo BSON -> vẫn giữ Number 100.
```

Điều này **không có nghĩa** `"50"` được tự chuyển thành số `50`. Nếu một field lẫn String, Double, Date và Null, giá trị mà `$min`/`$max` giữ có thể không còn đúng nghĩa nghiệp vụ.

Các trường thực tế nên có **schema thống nhất**: điểm là numeric, giá là Decimal128 hoặc integer theo đơn vị tiền, thời gian là BSON Date. Có thể dùng MongoDB JSON Schema validation, kiểm tra ở API hoặc migration dữ liệu cũ.

### 6.1. Khác $gt/$lt trong bộ lọc như thế nào?

Predicate bất đẳng thức như `{ score: { $gt: 10 } }` thường áp dụng **type bracketing**: nó kiểm tra giá trị tương thích với kiểu số của toán hạng. Trong khi đó `$min`/`$max` update có thể so sánh **khác kiểu** bằng thứ tự BSON.

Vì vậy, không nên suy ra kết quả `$max` từ những gì một query `$gt` trả về trên dữ liệu lẫn kiểu. MongoDB không coi mọi kiểu BSON có thể chuyển tự động thành một kiểu đơn nhất.

## 7. $currentDate: thời điểm cập nhật do MongoDB ghi

Cú pháp:

```javascript
{
  $currentDate: {
    updatedAt: true
  }
}
```

Khi dùng `true`, MongoDB tạo hoặc ghi đè field với **BSON Date hiện tại** tại thời điểm thao tác. Có thể chỉ định rõ kiểu:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  {
    $currentDate: {
      updatedAt: { $type: "date" }
    }
  }
);
```

Hai cách trên cùng chọn BSON Date.

### 7.1. Date và Timestamp là hai kiểu BSON khác nhau

`$currentDate` hỗ trợ:

| Cú pháp | Kiểu BSON được ghi | Mục đích thường gặp |
|---|---|---|
| `{ updatedAt: true }` | Date | Thời gian cập nhật ứng dụng |
| `{ updatedAt: { $type: "date" } }` | Date | Chỉ định kiểu Date rõ ràng |
| `{ touchTs: { $type: "timestamp" } }` | Timestamp | Một số trường hợp cần BSON Timestamp |

Ví dụ:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  {
    $currentDate: {
      updatedAt: true,
      internalTouchTimestamp: { $type: "timestamp" }
    }
  }
);
```

MongoDB BSON `Date` biểu diễn thời điểm theo mili-giây tính từ Unix epoch và được hiển thị kiểu `ISODate(...)` trong `mongosh`. BSON `Timestamp` là kiểu riêng, thường thấy ở ngữ cảnh kỹ thuật như replication/oplog; nó không phải lựa chọn mặc định cho ngày mua hàng, ngày hết hạn hay `updatedAt`.

Trường `updatedAt` có thể chưa tồn tại: `$currentDate` **tự tạo trường**. Nếu đã tồn tại, nó **ghi đè** bằng thời điểm hiện tại.

### 7.2. So sánh với set bằng new Date() ở client

Cách lấy thời gian từ phía ứng dụng:

```javascript
const clientNow = new Date();

db.inventory.updateOne(
  { _id: "SKU-101" },
  { $set: { updatedAt: clientNow } }
);
```

Cách dùng `$currentDate`:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  { $currentDate: { updatedAt: true } }
);
```

Với `new Date()`, mốc thời gian được tạo tại **client** trước khi gửi lệnh, phụ thuộc đồng hồ client và độ trễ mạng. Với `$currentDate`, giá trị được xác định khi MongoDB thực hiện cập nhật. Dù vậy, đây không phải lời hứa về đồng hồ toàn cầu tuyệt đối: các máy có thể có sai lệch đồng hồ, và nếu cần so sánh thứ tự sự kiện phân tán, phải thiết kế thêm quy tắc thứ tự/sequence.

### 7.3. Cập nhật trạng thái kèm dấu thời gian

```javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    status: "PAID"
  },
  {
    $set: { status: "SHIPPED" },
    $currentDate: { updatedAt: true }
  }
);
```

Điều kiện `status: "PAID"` giúp tránh chuyển trạng thái sai nếu đơn đã thay đổi giữa chừng. `$currentDate` ghi thời điểm **của lần cập nhật trạng thái** trong cùng document.

Nếu muốn `createdAt` chỉ được ghi khi **insert lần đầu**, dùng `$setOnInsert` với giá trị phù hợp hoặc thiết kế pipeline/upsert, không dùng `$currentDate` cho `createdAt` trên mọi cập nhật vì nó sẽ ghi đè ngày tạo.

### 7.4. $currentDate khác thời gian sự kiện đã xảy ra

Giả sử ứng dụng nhận event được tạo vào ngày 1 nhưng nhập đến MongoDB ngày 3. Khi lưu event:

- `eventAt` nên là timestamp từ nguồn nếu có độ tin cậy và ngữ nghĩa phù hợp.
- `receivedAt` hoặc `updatedAt` dùng `$currentDate` để ghi mốc hệ thống xử lý.

Đây là hai loại thời gian, không nên trộn nếu cần báo cáo theo thời gian thực tế của nghiệp vụ.

## 8. Phối hợp năm toán tử trong một update

MongoDB cho phép nhiều update operator trong cùng update document **nếu không cùng sửa những đường dẫn xung đột**.

Ví dụ bộ thống kê bán hàng:

```javascript
db.salesStats.insertOne({
  _id: "SKU-101",
  soldUnits: NumberLong("100"),
  revenue: NumberDecimal("125000000.00"),
  minOrderValue: NumberDecimal("50000.00"),
  maxOrderValue: NumberDecimal("2500000.00"),
  lastSaleAt: ISODate("2026-05-01T08:00:00Z")
});
```

Khi nhận một đơn bán 2 sản phẩm, tổng giá trị 1.900.000 và thời điểm giao dịch là 2026-05-02:

```javascript
const orderValue = NumberDecimal("1900000.00");
const saleAt = ISODate("2026-05-02T10:30:00Z");

db.salesStats.updateOne(
  { _id: "SKU-101" },
  {
    $inc: {
      soldUnits: NumberLong("2"),
      revenue: orderValue
    },
    $min: { minOrderValue: orderValue },
    $max: {
      maxOrderValue: orderValue,
      lastSaleAt: saleAt
    },
    $currentDate: { updatedAt: true }
  }
);
```

Sau thao tác:

- `soldUnits` tăng 2.
- `revenue` được cộng theo giá trị đơn.
- `minOrderValue` giữ số nhỏ nhất đã quan sát.
- `maxOrderValue` giữ số lớn nhất.
- `lastSaleAt` chỉ tiến về thời gian giao dịch muộn hơn.
- `updatedAt` là thời gian MongoDB xử lý lần ghi.

**Chú ý:** đây là ví dụ thống kê cho một document. Nó không tự bảo đảm rằng đơn hàng chỉ được xử lý đúng một lần. Nếu consumer gửi lại event, `$inc` tiếp tục cộng doanh thu/số lượng. Với số liệu tài chính, cần event ID, idempotency, đối soát và đôi khi transaction/outbox phù hợp.

### 8.1. Không cùng cập nhật một field bằng hai modifier

Ví dụ nên tránh:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  {
    $inc: { stock: 5 },
    $max: { stock: 0 }
  }
);
```

Hai modifier cùng sửa `stock` trong một update; MongoDB có thể báo **conflicting update paths**, không phải lần lượt cộng rồi áp giới hạn. Tương tự, tránh vừa `$set` vừa `$currentDate` lên `updatedAt` trong một update.

Nếu cần tính biểu thức tuần tự trên cùng trường, hãy dùng **aggregation pipeline update** với các stage biểu diễn rõ phép tính.

## 9. Khi cần clamp hoặc công thức phức tạp: update pipeline

Các modifier trong phần trên có cú pháp gọn và thường hiệu quả. Nhưng đôi khi nghiệp vụ yêu cầu:

- Tính giá trị mới từ một trường khác trong cùng document;
- Giới hạn giá trị trong một khoảng;
- Khi field thiếu/null thì dùng giá trị mặc định trước khi tính;
- Áp nhiều bước biến đổi lên cùng field.

MongoDB hỗ trợ cập nhật bằng **aggregation pipeline**. Ví dụ tăng số điểm 15 nhưng giữ tối đa 100:

```javascript
db.players.updateOne(
  { _id: "player-01" },
  [
    {
      $set: {
        score: {
          $min: [
            100,
            { $add: [{ $ifNull: ["$score", 0] }, 15] }
          ]
        },
        updatedAt: "$$NOW"
      }
    }
  ]
);
```

Ở đây `$min` là **aggregation expression**, không phải modifier update `$min: { score: ... }`. `$add` cộng các giá trị, `$ifNull` dùng `0` nếu trường thiếu/null, còn `$$NOW` lấy thời gian server cho biểu thức pipeline. Với một document, chuỗi tính toán và ghi kết quả vẫn nằm trong một thao tác cập nhật.

Ví dụ giảm tối đa 30% nhưng không thấp hơn giá sàn `floorPrice`:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  [
    {
      $set: {
        price: {
          $max: [
            "$floorPrice",
            {
              $multiply: [
                "$price",
                NumberDecimal("0.70")
              ]
            }
          ]
        },
        updatedAt: "$$NOW"
      }
    }
  ]
);
```

Ví dụ giả định `price` và `floorPrice` đều là Decimal128 hợp lệ và field tồn tại. Nếu thiếu dữ liệu, cần validation hoặc fallback được thiết kế cụ thể. Phép tính theo pipeline có thể phải đánh giá nhiều biểu thức hơn; chọn cách đơn giản nhất phù hợp với quy tắc nghiệp vụ.

## 10. Upsert, trường thiếu và giá trị khởi tạo

`upsert: true` nghĩa là nếu filter không khớp document nào, MongoDB có thể tạo document mới từ filter và update theo quy tắc upsert.

```javascript
db.dailyMetrics.updateOne(
  { _id: "2026-05-02" },
  {
    $inc: { views: NumberLong("1") },
    $currentDate: { updatedAt: true },
    $setOnInsert: { createdBy: "metrics-worker" }
  },
  { upsert: true }
);
```

Nếu document chưa tồn tại:

- `_id` lấy từ filter bằng.
- `views` được khởi tạo bằng lượng cộng của `$inc`.
- `updatedAt` lấy thời gian update.
- `createdBy` chỉ được gán khi tạo.

Nếu document đã tồn tại:

- `views` được cộng trên giá trị hiện tại.
- `updatedAt` được làm mới.
- `$setOnInsert` không có tác dụng.

**Không dùng `$setOnInsert` và `$inc` trên cùng đường dẫn để cố định nghĩa giá trị ban đầu theo hai cách.** Nếu cần khởi tạo phức tạp, chuyển logic sang pipeline hoặc tạo document rõ ràng trong một bước nghiệp vụ riêng.

### 10.1. Bảng hành vi với field không tồn tại và null

| Toán tử | Field không tồn tại | Field hiện có = `null` |
|---|---|---|
| `$inc: { x: 5 }` | Tạo `x = 5` | Lỗi |
| `$mul: { x: 5 }` | Tạo `x = 0` theo kiểu numeric của hệ số | Không phải giá trị numeric hợp lệ |
| `$min: { x: 5 }` | Tạo `x = 5` | So sánh BSON: Null nhỏ hơn Number, giữ `null` |
| `$max: { x: 5 }` | Tạo `x = 5` | So sánh BSON: Number lớn hơn Null, đổi thành `5` |
| `$currentDate: { x: true }` | Tạo BSON Date hiện tại | Ghi đè bằng BSON Date hiện tại |

Bảng giả định kiểu dữ liệu và đường dẫn parent hợp lệ. Khi dùng dot notation vào một parent không phải object, hoặc khi schema validation không cho phép kết quả, thao tác có thể lỗi.

## 11. Tính nguyên tử, đồng thời và retry

### 11.1. Một document là ranh giới nguyên tử

Một update như sau:

```javascript
db.inventory.updateOne(
  {
    _id: "SKU-101",
    stock: { $gte: 2 }
  },
  {
    $inc: {
      stock: -2,
      "metrics.sold": 2
    },
    $currentDate: { updatedAt: true }
  }
);
```

Nếu cập nhật thành công, các thay đổi trong cùng document được áp dụng như một thao tác nguyên tử. Một độc giả khác sẽ không quan sát trạng thái “stock đã trừ nhưng metrics.sold chưa tăng” như kết quả một phần của cùng update thành công.

Tuy nhiên, nếu thông tin nghiệp vụ nằm trong hai document (kho và đơn hàng) thì vẫn cần thiết kế cơ chế nhất quán nhiều document. `updateMany()` áp dụng update nguyên tử ở **từng document**, không làm toàn bộ collection có tính all-or-nothing như transaction.

### 11.2. $inc và $mul không idempotent

Một phép ghi **idempotent** là phép mà lặp lại cùng ý định không làm thay đổi kết quả sau lần đầu.

| Thao tác | Gọi lại cùng thao tác có giữ nguyên kết quả không? |
|---|---|
| `$inc: { views: 1 }` | **Không**; sẽ cộng thêm |
| `$mul: { price: 1.1 }` | **Không**; tiếp tục nhân |
| `$min: { low: 5 }` | Với giá trị/kiểu ổn định, gọi lại cùng candidate không làm low nhỏ hơn lần đầu |
| `$max: { high: 9 }` | Với giá trị/kiểu ổn định, gọi lại cùng candidate không làm high lớn hơn lần đầu |
| `$currentDate: { updatedAt: true }` | **Không**; mỗi lần áp dụng thành công ghi thời gian mới |

Đặc biệt khi client timeout hoặc mất mạng, không nên suy ra request chắc chắn chưa chạy rồi tự gửi `$inc` lần nữa. Driver MongoDB có **retryable writes** trong điều kiện hỗ trợ và có cơ chế nhận dạng thao tác, nhưng hệ thống vẫn cần **idempotency nghiệp vụ** nếu cùng event có thể được tạo/gửi lặp từ upstream, consumer hoặc job.

Một mô hình thường dùng là lưu `eventId` duy nhất của sự kiện, rồi cập nhật thống kê đúng một lần theo quy trình có bảo đảm. Nếu ghi event và cập nhật thống kê ở hai collection, cần cân nhắc transaction hoặc mô hình event log + materialized view có chống xử lý trùng.

### 11.3. Counter tập trung và throughput

Dù `$inc` an toàn cho phép cộng đơn giản, hàng nghìn writer cùng tăng **một document** có thể gây contention. Nếu counter chỉ là số lượt xem được phép tổng hợp bất đồng bộ, có thể phân counter thành nhiều document hoặc ghi event rồi tổng hợp. Nhưng đừng dùng eventual consistency cho tồn kho, số dư hoặc các invariant tài chính nếu chưa có cơ chế bảo vệ khác.

## 12. Mẫu Java và Spring Data MongoDB

Các ví dụ dưới đây minh họa cách dùng cùng update operator từ ứng dụng Java.

### 12.1. MongoDB Java Sync Driver

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;
import static com.mongodb.client.model.Updates.currentDate;

MongoCollection<Document> inventory =
    database.getCollection("inventory");

int quantity = 2;

UpdateResult result = inventory.updateOne(
    and(
        eq("_id", "SKU-101"),
        gte("stock", quantity)
    ),
    combine(
        inc("stock", -quantity),
        inc("metrics.sold", quantity),
        currentDate("updatedAt")
    )
);

if (result.getModifiedCount() != 1) {
    throw new IllegalStateException("Không đủ hàng hoặc sản phẩm không tồn tại");
}
```

Các builder `Updates.inc()`, `Updates.mul()`, `Updates.min()`, `Updates.max()` và `Updates.currentDate()` giúp tạo BSON update theo API driver. Đảm bảo dùng loại số Java phù hợp với schema BSON; ví dụ số tiền nên dùng mô hình decimal rõ ràng, không tự chuyển ngầm mọi giá trị thành `double`.

### 12.2. Spring Data MongoDB

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

Query query = Query.query(
    Criteria.where("_id").is("SKU-101")
            .and("stock").gte(2)
);

Update update = new Update()
    .inc("stock", -2)
    .inc("metrics.sold", 2)
    .currentDate("updatedAt");

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    "inventory"
);
```

Spring Data có các phương thức tương ứng như `Update.inc()`, `multiply()`, `min()`, `max()` và `currentDate()` tùy phiên bản. Đối với đường dẫn lồng nhau hoặc field Java được ánh xạ tên khác trong MongoDB, cần hiểu quy tắc mapping của entity/collection thực tế.

## 13. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Đọc counter rồi `$set` giá trị cộng ở client | Có thể mất lượt cập nhật khi nhiều writer cùng chạy | Dùng `$inc` |
| Dùng `$inc` trên field `null` | Update lỗi | Chuẩn hóa dữ liệu, định nghĩa default numeric |
| Nghĩ `$mul` trên field thiếu sẽ tạo hệ số nhân | Thực tế tạo `0` | Khởi tạo field đúng trước hoặc dùng pipeline |
| Dùng `$mul: 0.9` mỗi lần áp giá khuyến mại | Giảm giá lặp khi retry | Tính từ giá gốc, có idempotency |
| Dùng `Double` cho tiền rồi kỳ vọng kết quả thập phân tuyệt đối | Sai số biểu diễn và làm tròn | Dùng Decimal128/đơn vị tiền nguyên theo contract |
| Dùng `$min` hoặc `$max` cho field lẫn String/Number | So sánh theo thứ tự BSON, sai nghĩa số học | Validator/migration về một kiểu |
| Dùng `$currentDate` để giữ `createdAt` trong mọi update | Ghi đè ngày tạo | Khởi tạo một lần, chỉ làm mới `updatedAt` |
| Nhầm BSON Timestamp với BSON Date | Khác kiểu và ngữ nghĩa | Dùng Date cho thời gian nghiệp vụ |
| Cùng `$inc` và `$max` một field trong một update | Xung đột đường dẫn cập nhật | Dùng pipeline hoặc tách logic |
| Nghĩ `updateMany()` là một transaction toàn collection | Có thể cập nhật một phần khi lỗi ngoài transaction | Xác định ranh giới transaction |
| Retry `$inc` vô điều kiện sau timeout | Có thể cộng trùng | Retryable writes/idempotency/readback |
| Tăng/giảm tồn kho không có filter kiểm tra | Có thể âm kho | Conditional atomic update |

## 14. Bài tập thực hành

### Bài 1 — Counter và tồn kho

Tạo document `{ _id: "P1", views: 0, stock: 5 }`. Viết:
1. Câu lệnh tăng `views` một đơn vị.
2. Câu lệnh giảm `stock` 3 đơn vị chỉ khi còn đủ hàng.
3. Kiểm tra `matchedCount` và `modifiedCount` sau từng thao tác.
4. Giải thích vì sao không nên đọc stock ở client rồi `$set` số mới khi nhiều request đến đồng thời.

### Bài 2 — Nhân giá và xử lý null/missing

Tạo ba document có `price` lần lượt là `Decimal128("100.00")`, thiếu `price` và `price: null`. Thử `$mul: { price: NumberDecimal("1.10") }`. Dự đoán và quan sát hành vi từng trường hợp. Sau đó thiết kế quy tắc khởi tạo giá đúng nghiệp vụ.

### Bài 3 — Theo dõi cực trị

Một cảm biến gửi các giá trị `[22, 18, 26, 21]` theo thứ tự bất kỳ. Tạo document có `minValue` và `maxValue`, cập nhật bằng `$min`/`$max` sau mỗi sự kiện. Dự đoán kết quả cuối. Nếu sensor có thể gửi String `"18"` thay vì Number, giải thích vì sao cần kiểm soát BSON type.

### Bài 4 — Thời gian của sự kiện và thời gian cập nhật

Nhập sự kiện có `eventAt = 2026-01-01` vào ngày 2026-01-03. Viết update dùng:
- `$min` để giữ `firstEventAt`;
- `$max` để giữ `lastEventAt`;
- `$currentDate` để ghi `updatedAt`.

Giải thích vì sao ba field có thể có các giá trị thời gian rất khác nhau.

### Bài 5 — Clamp điểm trong khoảng

Trường `score` đang là `95`, muốn cộng `15` nhưng giới hạn tối đa `100`. Vì sao không thể an toàn diễn đạt bằng hai modifier `$inc` và `$min` cùng sửa `score` trong một update? Hãy viết update pipeline dùng `$add`, `$min` và `$$NOW`.

### Bài 6 — Xử lý retry

Một consumer đọc lại event “bán hai sản phẩm” sau khi đã cập nhật thống kê, nhưng lần đầu bị timeout. Nếu ghi lại cùng `$inc`, số lượng bán có thể sai thế nào? Đề xuất định danh `eventId`, cách xác minh event đã áp dụng và ranh giới transaction hoặc projection bất đồng bộ thích hợp.

## 15. Tài liệu tham khảo

- [MongoDB – Update Operators](https://www.mongodb.com/docs/manual/reference/mql/update/)
- [MongoDB – $inc](https://www.mongodb.com/docs/manual/reference/operator/update/inc/)
- [MongoDB – $mul](https://www.mongodb.com/docs/manual/reference/operator/update/mul/)
- [MongoDB – $min](https://www.mongodb.com/docs/manual/reference/operator/update/min/)
- [MongoDB – $max](https://www.mongodb.com/docs/manual/reference/operator/update/max/)
- [MongoDB – $currentDate](https://www.mongodb.com/docs/manual/reference/operator/update/currentDate/)
- [MongoDB – BSON comparison order](https://www.mongodb.com/docs/manual/reference/bson-type-comparison-order/)
- [MongoDB – Updates with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)

## Kết luận

`$inc` và `$mul` cập nhật giá trị số trực tiếp trong document; `$min` và `$max` giữ các cực trị thông qua phép so sánh; `$currentDate` ghi ngày giờ hiện tại từ MongoDB. Điểm quan trọng không chỉ là cú pháp: cần biết **trường thiếu khác trường null**, kiểu BSON ảnh hưởng phép tính/so sánh, cập nhật một document là nguyên tử nhưng việc gửi lại `$inc`/`$mul` vẫn có thể gây sai số liệu, và thời gian sự kiện khác thời gian hệ thống ghi nhận.

Dùng các toán tử theo ranh giới nghiệp vụ: conditional `$inc` để bảo vệ tồn kho, `$min`/`$max` để theo dõi giá trị sớm nhất/muộn nhất, `$currentDate` để theo dõi lần cập nhật, và aggregation pipeline khi công thức cần nhiều bước trên cùng field. Khi kết hợp schema nhất quán, index phù hợp, idempotency và đối soát, các thao tác cập nhật vừa rõ ràng vừa an toàn hơn dưới tải đồng thời.

