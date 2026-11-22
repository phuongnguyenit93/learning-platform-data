# Ghi kết quả bằng `$out`, `$merge` và kiểm soát tác động lên dữ liệu đích trong MongoDB

## 1. Bài toán: kết quả aggregation có thể trở thành dữ liệu được lưu

Aggregation pipeline thường được giới thiệu như một công cụ **đọc, lọc, biến đổi và tổng hợp document**:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$channel",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  }
]);
```

Pipeline trên trả các document tổng hợp cho ứng dụng. Nhưng trong thực tế, nhiều hệ thống muốn **lưu kết quả tổng hợp** để phục vụ dashboard, báo cáo hoặc các tác vụ phía sau:

- Mỗi đêm tính lại bảng doanh thu theo ngày và kênh bán.
- Đưa dữ liệu đã chuẩn hóa vào một collection phục vụ tra cứu.
- Bổ sung hoặc cập nhật các chỉ số của một ngày mà không ghi đè chỉ số của những ngày khác.
- Thay thế toàn bộ collection báo cáo sau khi tính lại đầy đủ.
- Kết hợp kết quả từ một nguồn vào collection đang tồn tại theo khóa nghiệp vụ.

MongoDB cung cấp hai **aggregation pipeline stage ghi dữ liệu**:

- **`$out`**: ghi toàn bộ kết quả pipeline thành một collection đích; nếu đích đã tồn tại, thao tác hoàn tất bằng cách **thay thế collection đích**.
- **`$merge`**: ghi từng document kết quả vào collection đích theo quy tắc **khớp khóa, cập nhật, giữ nguyên, bỏ qua, chèn mới hoặc báo lỗi**.

Hai stage đều tạo **tác động ghi dữ liệu thật**. Chúng khác hoàn toàn với `$project` hay `$group`, vốn chỉ biến đổi luồng kết quả. Vì vậy, khi sử dụng, câu hỏi không chỉ là “pipeline tính đúng chưa?” mà còn là:

> **Dữ liệu nào ở collection đích sẽ được tạo, thay thế, giữ nguyên hoặc bị ảnh hưởng khi pipeline chạy lại hay thất bại giữa chừng?**

### 1.1. Một sơ đồ để nhớ

```text
                    Collection nguồn
                           |
                           v
                $match / $group / $project
                           |
                    Kết quả aggregation
                           |
                  +--------+--------+
                  |                 |
                  v                 v
                 $out             $merge
                  |                 |
      Tạo collection mới      So khớp từng document
      hoặc thay toàn bộ       theo khóa on
      collection đích              |
                  |          +-----+------+
                  |          |            |
                  |      Đã khớp      Chưa khớp
                  |          |            |
                  |     whenMatched  whenNotMatched
                  |          |            |
                  +----------+------------+
                             |
                         Dữ liệu đích
```

**Nguyên tắc thiết kế đầu tiên:** nếu mục tiêu là **thay toàn bộ snapshot báo cáo**, nghĩ tới `$out`; nếu mục tiêu là **đồng bộ từng bản ghi theo khóa**, nghĩ tới `$merge`. Không được coi hai stage này là hai cách viết tương đương.

## 2. Những quy tắc chung trước khi ghi

### 2.1. Cả `$out` và `$merge` đều là stage cuối của pipeline

Ví dụ hợp lệ:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$channel", orderCount: { $sum: 1 } } },
  { $out: "paidOrdersByChannel" }
]);
```

Ví dụ không đúng về cấu trúc:

```javascript
// Không đặt thêm $project sau một stage ghi đầu ra.
db.orders.aggregate([
  { $out: "paidOrdersByChannel" },
  { $project: { _id: 0 } }
]);
```

`$out` và `$merge` là **terminal stages**: chúng kết thúc việc đưa kết quả tới collection đích. Không đặt các stage xử lý khác phía sau chúng.

### 2.2. Không trả các document tổng hợp như một pipeline đọc

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $count: "total" }
]);
```

Pipeline này có thể trả `{ total: ... }` trong cursor kết quả. Ngược lại:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $count: "total" },
  { $out: "paidOrderCount" }
]);
```

Pipeline thứ hai **ghi** document tổng vào collection `paidOrderCount`. Đừng kỳ vọng ứng dụng nhận được document tổng như một kết quả đọc bình thường; muốn xem nội dung, hãy truy vấn collection đích.

### 2.3. Chúng không phải thao tác chỉ đọc

Một tài khoản chỉ có quyền xem dữ liệu có thể chạy pipeline gồm `$match` hoặc `$group`, nhưng không có nghĩa nó có quyền thực hiện `$out` hay `$merge`. Những stage ghi cần **quyền ghi và các quyền liên quan đến collection đích**, có thể gồm tạo collection hoặc thay thế collection tùy lệnh.

Các lệnh ghi này cũng **không dùng trong transaction nhiều document**. Nếu cần một bản công bố báo cáo an toàn cho người đọc, phải thiết kế cơ chế phù hợp với ngữ nghĩa riêng của từng stage, không cố bọc `$out`/`$merge` vào transaction.

### 2.4. Chọn tên đích thật rõ

Một lệnh `$out: "orders"` chạy nhầm trong database production có thể thay thế collection `orders` quan trọng. Vì vậy:

- Dùng tên tách biệt cho collection nguồn và collection báo cáo.
- Tách database thử nghiệm, staging, analytics và production khi phù hợp.
- Đọc kỹ tên đích, database đích và quyền trước khi chạy.
- Không bao giờ sao chép một lệnh `$out` có tên đích thật mà chưa hiểu tác động.

## 3. Bộ dữ liệu thử nghiệm cho toàn bài

Mọi ví dụ ghi trong bài dùng database **`mongo_training_208`** và các collection có hậu tố `208` để tránh nhầm với dữ liệu thật. Chạy bằng **mongosh** trên MongoDB phục vụ thực hành, không dùng database sản xuất.

```javascript
const demo = db.getSiblingDB("mongo_training_208");
const source = demo.salesOrders208;

// Dừng nếu đã có dữ liệu, tránh chèn trùng hoặc trộn hai bộ mẫu.
if (source.countDocuments({}) !== 0) {
  throw new Error(
    "salesOrders208 da co du lieu; dung database thu nghiem rong"
  );
}

source.insertMany([
  {
    _id: "O01",
    status: "PAID",
    channel: "web",
    amount: 100000,
    createdAt: ISODate("2026-11-01T02:00:00Z")
  },
  {
    _id: "O02",
    status: "PAID",
    channel: "web",
    amount: 200000,
    createdAt: ISODate("2026-11-01T06:00:00Z")
  },
  {
    _id: "O03",
    status: "PENDING",
    channel: "app",
    amount: 50000,
    createdAt: ISODate("2026-11-01T09:00:00Z")
  },
  {
    _id: "O04",
    status: "PAID",
    channel: "app",
    amount: 300000,
    createdAt: ISODate("2026-11-01T11:00:00Z")
  },
  {
    _id: "O05",
    status: "PAID",
    channel: "web",
    amount: 150000,
    createdAt: ISODate("2026-11-02T03:00:00Z")
  },
  {
    _id: "O06",
    status: "CANCELLED",
    channel: "app",
    amount: 90000,
    createdAt: ISODate("2026-11-02T05:00:00Z")
  },
  {
    _id: "O07",
    status: "PAID",
    channel: "app",
    amount: 70000,
    createdAt: ISODate("2026-11-02T07:00:00Z")
  },
  {
    _id: "O08",
    status: "PAID",
    channel: "web",
    amount: 80000,
    createdAt: ISODate("2026-11-02T08:00:00Z")
  }
]);
```

Với bộ mẫu, có **tám đơn**, trong đó **sáu đơn đã thanh toán**. Tiền được biểu diễn bằng **số nguyên theo đơn vị tiền giả định** để dễ quan sát. Hệ thống thật cần chuẩn hóa cách lưu tiền, làm tròn và xử lý đơn hủy/hoàn theo chính sách nghiệp vụ.

### 3.1. Pipeline chuẩn hóa dữ liệu báo cáo

Ta muốn tạo một document báo cáo cho mỗi **ngày kinh doanh + kênh bán**, chỉ xét đơn `PAID`. Ngày được xác định theo múi giờ `Asia/Ho_Chi_Minh`.

```javascript
const dailyPipeline = [
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: {
        day: {
          $dateToString: {
            format: "%Y-%m-%d",
            date: "$createdAt",
            timezone: "Asia/Ho_Chi_Minh"
          }
        },
        channel: "$channel"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  {
    $project: {
      _id: 0,
      day: "$_id.day",
      channel: "$_id.channel",
      orderCount: 1,
      totalAmount: 1
    }
  }
];
```

**Điểm cần ghi nhớ:** `_id: 0` trong `$project` cố tình bỏ khóa nhóm tổng hợp; ở những ví dụ `$merge` phía sau, ta dùng cặp **`day + channel`** làm khóa nghiệp vụ. Nếu để nguyên `_id` của `$group` mà chọn một khóa `on` khác, cách xử lý `_id` có thể gây xung đột immutable field trong những tình huống ghi đè.

### 3.2. Xem trước kết quả mà chưa ghi gì

```javascript
source.aggregate([
  ...dailyPipeline,
  { $sort: { day: 1, channel: 1 } }
]).toArray();
```

Kết quả mong đợi:

| `day` | `channel` | `orderCount` | `totalAmount` |
|---|---|---:|---:|
| 2026-11-01 | app | 1 | 300000 |
| 2026-11-01 | web | 2 | 300000 |
| 2026-11-02 | app | 1 | 70000 |
| 2026-11-02 | web | 2 | 230000 |

Tổng doanh thu của sáu đơn PAID là **900000**. Những đơn `PENDING` hoặc `CANCELLED` không được tính.

Đây là bước rất quan trọng trong workflow: **trước khi thêm stage ghi, chạy đúng phần đọc và tính toán, kiểm tra số nhóm/khóa/tổng**. Khi dùng `$out`, một lỗi filter có thể dẫn tới thay cả collection đích; khi dùng `$merge`, lỗi khóa nhóm có thể khiến cập nhật nhầm document.

## 4. `$out`: xuất toàn bộ kết quả thành một collection

### 4.1. Cú pháp

Hai hình thức thường gặp:

```javascript
// Collection trong cùng database với collection nguồn.
{ $out: "dailyReportOut208" }

// Chỉ rõ database và collection đích.
{
  $out: {
    db: "mongo_training_208",
    coll: "dailyReportOut208"
  }
}
```

Trong ví dụ, kết quả được ghi vào collection `dailyReportOut208`:

```javascript
source.aggregate([
  ...dailyPipeline,
  { $out: "dailyReportOut208" }
]).toArray();

demo.dailyReportOut208.find(
  {},
  { _id: 0, day: 1, channel: 1, orderCount: 1, totalAmount: 1 }
).sort({ day: 1, channel: 1 });
```

Nếu collection đích **chưa tồn tại**, MongoDB tạo collection để chứa kết quả. Nếu collection đích **đã tồn tại**, `$out` không chỉ bổ sung các document mới: nó chuẩn bị kết quả rồi **thay thế nội dung collection đích**.

### 4.2. Cơ chế ghi với collection đích đã tồn tại

Ở mức khái niệm, `$out` làm việc như sau:

```text
Collection nguồn -> aggregation -> collection tạm
                                         |
                                  Ghi đủ kết quả
                                         |
                                  Đáp ứng điều kiện
                                  ghi/index đích
                                         |
                              Thay collection đích
                              bằng collection mới
                                         |
                                  Bản báo cáo mới
```

Đối với collection đích đã tồn tại, MongoDB xây dựng kết quả trong một **collection tạm**, sao chép những index thích hợp từ đích hiện hữu và tiến hành thay thế qua thao tác rename/swap khi hoàn tất. Mục đích là tránh để người đọc thấy một collection đang được nạp từng phần như cách xóa rồi insert thủ công.

**Tính nguyên tử của việc thay thế đích** không có nghĩa toàn bộ quá trình *đọc nguồn + tổng hợp + công bố* là một transaction snapshot bao trùm mọi thao tác ghi đồng thời vào nguồn. Nếu ứng dụng khác đang thay đổi đơn hàng trong lúc chạy, cần thiết kế read concern, cutoff hoặc quy trình chốt dữ liệu phù hợp.

### 4.3. `$out` thay cả nội dung: document cũ không nằm trong kết quả sẽ mất

Giả sử collection `dailyReportOut208` đang có thêm một document thủ công:

```javascript
demo.dailyReportOut208.insertOne({
  day: "2026-10-31",
  channel: "web",
  orderCount: 99,
  totalAmount: 999999,
  note: "Ghi chu thu cong"
});
```

Sau khi chạy lại:

```javascript
source.aggregate([
  ...dailyPipeline,
  { $out: "dailyReportOut208" }
]).toArray();
```

collection đích chỉ còn **những document được sinh bởi pipeline hiện tại**. Document ngày `2026-10-31` và trường `note` thủ công không nằm trong pipeline sẽ không được giữ lại.

Đây là **tác động có chủ đích của `$out`**, không phải lỗi. Vì vậy, **không dùng `$out` trên collection chứa dữ liệu gốc hoặc các chỉnh sửa thủ công cần giữ**, trừ khi nghiệp vụ thật sự muốn thay toàn bộ.

### 4.4. Nếu kết quả pipeline rỗng?

Giả sử filter không khớp đơn nào:

```javascript
source.aggregate([
  { $match: { status: "REFUNDED" } },
  { $project: { _id: 0, status: 1 } },
  { $out: "emptyReportOut208" }
]).toArray();
```

Collection đích sẽ có **không document kết quả**. Nếu đích đã tồn tại và chứa dữ liệu cũ, thao tác xuất snapshot rỗng có thể **thay thế nó bằng collection rỗng**. Không nên xem “không khớp kết quả” như tình huống vô hại nếu đang dùng `$out`.

Một hệ thống báo cáo có thể cần **chặn xuất bản snapshot rỗng** trừ khi đó là kết quả nghiệp vụ hợp lệ. Việc chặn phải diễn ra **trước stage ghi**, dựa trên chính sách rõ ràng.

### 4.5. Index và ràng buộc ở collection đích

Khi `$out` thay thế một collection đã có, MongoDB cố duy trì những index tương ứng của collection đích khi tạo kết quả tạm. Nếu kết quả mới **vi phạm unique index** hoặc không đáp ứng những ràng buộc áp dụng, thao tác có thể lỗi; không nên giả định mọi document tổng hợp sẽ được chấp nhận.

Ví dụ một unique index:

```javascript
demo.dailyReportOut208.createIndex(
  { day: 1, channel: 1 },
  { unique: true }
);
```

Nếu một pipeline lỗi tạo **hai document cùng `day + channel`** nhưng có `_id` khác nhau, unique index có thể khiến `$out` thất bại. Bản đích cũ thường vẫn được giữ nếu lỗi xảy ra trước bước thay thế; không tự suy ra đã xuất thành công chỉ vì pipeline chạy được một phần.

### 4.6. Các giới hạn đáng nhớ của `$out`

- Phải là stage cuối.
- Ghi vào collection cùng database hoặc database khác trên cùng triển khai MongoDB trong những hình thức được hỗ trợ.
- **Không thể ghi đích là sharded collection** bằng `$out` theo quy tắc thông thường; nếu muốn ghi từng bản ghi vào đích đã shard, xem `$merge` và các ràng buộc sharding.
- Không dùng trong transaction nhiều document.
- Không phải cách để trả dữ liệu đọc cho ứng dụng.
- Nếu đích thuộc loại collection đặc biệt (ví dụ time series), khả năng hỗ trợ và cú pháp có thể phụ thuộc phiên bản; không áp dụng quy tắc collection thường một cách máy móc.

## 5. `$merge`: ghi từng document theo khóa nghiệp vụ

Khác `$out`, `$merge` **không thay toàn bộ collection đích**. Nó xét từng document được pipeline tạo ra và quyết định có document phù hợp ở đích hay chưa.

### 5.1. Cú pháp

```javascript
{
  $merge: {
    into: "targetCollection",
    on: ["keyA", "keyB"],
    whenMatched: "replace",
    whenNotMatched: "insert"
  }
}
```

Các thành phần:

| Trường | Ý nghĩa |
|---|---|
| `into` | Collection đích, hoặc document gồm `db` và `coll` |
| `on` | Một trường hoặc mảng các trường dùng làm **khóa xác định document đích** |
| `whenMatched` | Quy tắc khi đích đã có document khớp `on` |
| `whenNotMatched` | Quy tắc khi đích chưa có document khớp |
| `let` | Tùy chọn định nghĩa biến để dùng trong update pipeline của `whenMatched` |

Ví dụ dạng đầy đủ:

```javascript
{
  $merge: {
    into: {
      db: "mongo_training_208",
      coll: "dailyReportMerge208"
    },
    on: ["day", "channel"],
    whenMatched: "replace",
    whenNotMatched: "insert"
  }
}
```

### 5.2. Giá trị mặc định

Với một collection **không shard**, nếu không chỉ rõ `on`, MongoDB thường sử dụng **`_id`** làm khóa so khớp. Với collection sharded, các quy tắc mặc định còn liên quan tới **shard key**. Vì vậy, không nên phụ thuộc vào mặc định khi báo cáo có khóa nghiệp vụ như `day + channel`.

Nếu không chỉ rõ hai tùy chọn còn lại, thông thường:

- `whenMatched: "merge"`.
- `whenNotMatched: "insert"`.

Điều đó nghĩa là MongoDB sẽ **gộp các trường** khi tìm thấy document đích, và **chèn document mới** khi chưa tìm thấy.

Nếu mục tiêu là cập nhật một snapshot chính xác cho từng khóa, hãy ghi tường minh `whenMatched: "replace"` để tránh giữ lại những trường cũ ngoài ý muốn.

## 6. Chuẩn bị unique index cho `on`

MongoDB yêu cầu các trường `on` tùy chỉnh được hỗ trợ bởi **unique index thích hợp** trên collection đích. Index đó cho phép xác định duy nhất document tương ứng với một khóa nghiệp vụ. Một index thường không unique **không thay thế** được điều kiện này.

Với báo cáo theo ngày/kênh:

```javascript
const mergeTarget = demo.dailyReportMerge208;

mergeTarget.createIndex(
  { day: 1, channel: 1 },
  { unique: true }
);
```

Lệnh trên đồng thời tạo collection đích nếu nó chưa tồn tại. Như vậy, trước khi chạy `$merge`, collection đã có unique compound index trên đúng hai trường `day` và `channel`.

### 6.1. Vì sao cần unique?

Giả sử collection đích vô tình chứa:

```javascript
{ _id: 1, day: "2026-11-01", channel: "web", totalAmount: 100 }
{ _id: 2, day: "2026-11-01", channel: "web", totalAmount: 200 }
```

Nếu `on: ["day", "channel"]`, MongoDB không thể có một kết quả cập nhật xác định duy nhất cho khóa `("2026-11-01", "web")`. Unique index giúp ngăn dữ liệu có hai document với cùng khóa báo cáo.

### 6.2. Các điều kiện bổ sung của `on`

Khi thiết kế khóa `on`, cần ghi nhớ:

- Các trường khóa phải có mặt và mang kiểu dữ liệu phù hợp với quy tắc của phiên bản/unique index; những giá trị **null/missing** có hạn chế phụ thuộc phiên bản MongoDB và đặc tính index.
- Giá trị trường `on` **không được là mảng**; đừng dùng mảng tag làm khóa ghép theo cách này.
- Unique index hỗ trợ `on` phải có các trường phù hợp; một **partial unique index** không thể mặc nhiên dùng thay index được yêu cầu.
- **Collation** của aggregation và unique index cần tương thích. Một index phân biệt chữ hoa/thường có thể không đáp ứng quy tắc đối chiếu `on` của pipeline dùng collation khác.
- Khi đích là sharded collection, khóa `on` và unique index còn chịu các ràng buộc shard key và quy tắc sharding của deployment.

**Khuyến nghị:** với một báo cáo, hãy tạo các trường khóa tổng hợp **rõ ràng, không null, cùng kiểu** và chỉ định `on` tường minh. Tránh phụ thuộc vào những trường có thể thiếu hoặc tự do đổi giá trị.

### 6.3. `on` không phải `_id`

Trong ví dụ, khóa đích là cặp `day + channel`, còn `_id` là định danh nội bộ của document báo cáo. Chúng có thể là hai bộ khóa khác nhau.

Khi pipeline dùng `$group`, kết quả thường có `_id` kiểu object:

```javascript
{
  _id: {
    day: "2026-11-01",
    channel: "web"
  },
  totalAmount: 300000
}
```

Nếu muốn `on: ["day", "channel"]`, cần tạo đúng **hai trường top-level** `day` và `channel`. Pipeline `dailyPipeline` đã làm việc này trong `$project` và **loại `_id` nguồn** để tránh cố ghi đè một giá trị `_id` bất biến không khớp với document đích.

## 7. Ví dụ `$merge` đầy đủ: làm mới từng nhóm báo cáo

Với collection/index chuẩn bị ở phần 6:

```javascript
source.aggregate([
  ...dailyPipeline,
  {
    $merge: {
      into: "dailyReportMerge208",
      on: ["day", "channel"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]).toArray();

demo.dailyReportMerge208.find(
  {},
  { _id: 0, day: 1, channel: 1, orderCount: 1, totalAmount: 1 }
).sort({ day: 1, channel: 1 });
```

Kết quả ban đầu là bốn nhóm như `dailyPipeline` đã tính. So với `$out`, ở đây MongoDB:

1. Đọc một document kết quả, ví dụ `{ day: "2026-11-01", channel: "web", orderCount: 2, totalAmount: 300000 }`.
2. Tìm document đích khớp cặp `day`, `channel`.
3. Nếu đã có, **`replace`** document đích bằng dữ liệu báo cáo mới theo quy tắc không được đổi khóa bất biến.
4. Nếu chưa có, **`insert`** một document báo cáo mới.
5. Tiếp tục những kết quả khác của pipeline.

### 7.1. Chạy lại cùng dữ liệu

Nếu không có đơn nào thay đổi, chạy lại pipeline trên cho kết quả báo cáo **tương đương về dữ liệu nghiệp vụ**: không có thêm một document khác chỉ vì cùng khóa ngày/kênh được xử lý lại.

Đây là một dạng **idempotency theo khóa và dữ liệu** của mẫu `whenMatched: "replace"` + `whenNotMatched: "insert"`.

**Đừng nhầm tính lặp an toàn của mẫu này với tính nguyên tử toàn bộ `$merge`.** Các document được ghi riêng; khi pipeline lỗi sau khi đã ghi vài document, đích có thể ở trạng thái cập nhật một phần.

### 7.2. Sau khi dữ liệu nguồn thay đổi

Thêm một đơn `PAID` ở kênh web ngày 2026-11-01:

```javascript
source.insertOne({
  _id: "O09",
  status: "PAID",
  channel: "web",
  amount: 25000,
  createdAt: ISODate("2026-11-01T12:00:00Z")
});
```

Chạy lại `$merge`:

```javascript
source.aggregate([
  ...dailyPipeline,
  {
    $merge: {
      into: "dailyReportMerge208",
      on: ["day", "channel"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]).toArray();
```

Nhóm `2026-11-01 + web` chuyển từ:

```javascript
{ day: "2026-11-01", channel: "web", orderCount: 2, totalAmount: 300000 }
```

sang:

```javascript
{ day: "2026-11-01", channel: "web", orderCount: 3, totalAmount: 325000 }
```

Các nhóm khác vẫn giữ số liệu tương ứng. Vì `dailyPipeline` tính lại **toàn bộ số liệu từ nguồn**, `replace` không cộng thêm giá trị cũ, nên không tạo lỗi đếm đôi chỉ vì chạy lại cùng tính toán.

**Lưu ý khi thực hành:** việc chèn O09 làm thay đổi bộ dữ liệu gốc; các ví dụ ở phần sau có thể giả định tám document ban đầu và sẽ ghi rõ khi dùng một trạng thái cụ thể.

## 8. Bảng đầy đủ `whenMatched` và `whenNotMatched`

### 8.1. `whenMatched`: khi đã tìm được document đích

| Giá trị | Hành vi |
|---|---|
| `"replace"` | Thay document đích bằng document kết quả; không được vi phạm trường bất biến như `_id` hay shard key |
| `"merge"` | Gộp trường từ document kết quả vào document đích; giữ những trường đích không bị ghi đè |
| `"keepExisting"` | Giữ nguyên document đích, bỏ qua document kết quả |
| `"fail"` | Báo lỗi khi gặp document đích đã tồn tại |
| Pipeline cập nhật | Cho phép tính toán cách sửa document đích bằng một tập stage cập nhật được hỗ trợ |

### 8.2. `whenNotMatched`: khi chưa có document đích

| Giá trị | Hành vi |
|---|---|
| `"insert"` | Chèn document kết quả vào collection đích |
| `"discard"` | Bỏ qua document kết quả, không chèn mới |
| `"fail"` | Báo lỗi khi chưa tìm thấy document đích khớp |

Mặc định thường là `whenMatched: "merge"` và `whenNotMatched: "insert"`. Các giá trị khác là **lựa chọn về ý nghĩa cập nhật**, không phải tùy chọn hiệu năng.

### 8.3. Bảng tình huống

Giả sử kết quả pipeline:

```javascript
{
  day: "2026-11-01",
  channel: "web",
  orderCount: 3,
  totalAmount: 325000
}
```

và document đích hiện tại:

```javascript
{
  _id: ObjectId("64b000000000000000000001"),
  day: "2026-11-01",
  channel: "web",
  orderCount: 2,
  totalAmount: 300000,
  owner: "analytics",
  note: "Duyet thu cong"
}
```

Với khóa `on: ["day", "channel"]`:

- `replace`: số lượng và doanh thu thành 3/325000, các trường `owner` và `note` cũ **không tự được giữ lại** nếu không nằm trong document mới; `_id` hiện có phải được giữ theo quy tắc trường bất biến.
- `merge`: số lượng/doanh thu thành 3/325000, nhưng `owner` và `note` **vẫn còn** vì document mới không ghi đè chúng.
- `keepExisting`: toàn bộ document đích giữ trạng thái cũ 2/300000.
- `fail`: nếu đã khớp, pipeline báo lỗi.
- Pipeline cập nhật: ta tự xác định trường nào bị thay đổi và cách tính giá trị mới.

### 8.4. `merge` không có nghĩa cộng dồn

Đây là lỗi diễn giải rất phổ biến:

```javascript
whenMatched: "merge"
```

không có nghĩa `totalAmount_new = totalAmount_old + totalAmount_incoming`. Nó là **gộp trường của document**, ví dụ giá trị `totalAmount` mới thường **ghi đè** giá trị cùng tên ở đích.

Muốn cộng dồn số liệu khi đã khớp, phải viết **`whenMatched` bằng update pipeline** hoặc thiết kế thao tác cập nhật khác. Việc cộng dồn có nguy cơ đếm đôi khi retry, được giải thích ở phần 10.

## 9. Khác biệt quan trọng giữa `replace` và `merge`

### 9.1. Bài toán snapshot toàn bộ bản ghi theo khóa

Mỗi lần chạy, `dailyPipeline` tạo một document đầy đủ chứa:

```javascript
{
  day: "2026-11-01",
  channel: "web",
  orderCount: 3,
  totalAmount: 325000
}
```

Nếu xem đây là **nguồn sự thật mới** cho bản ghi báo cáo, `whenMatched: "replace"` thường phù hợp: mọi trường do pipeline kiểm soát phản ánh đúng dữ liệu tính lại, và những trường rác cũ không còn được giữ một cách vô tình.

Nhưng `replace` cũng có thể **xóa các trường bổ sung ở đích** như `reviewedBy` hoặc `manualComment`. Nếu đích chứa các trường do con người chỉnh sửa cần được bảo toàn, không nên áp dụng `replace` thiếu kiểm soát.

### 9.2. Bài toán cập nhật vài trường, giữ những trường còn lại

Giả sử đích lưu:

```javascript
{
  day: "2026-11-01",
  channel: "web",
  orderCount: 2,
  totalAmount: 300000,
  reviewedBy: "analyst-01",
  reviewNote: "Da kiem tra"
}
```

Pipeline chỉ tạo `day`, `channel`, `orderCount` và `totalAmount`. Với `whenMatched: "merge"`, `reviewedBy` và `reviewNote` được giữ, trong khi hai số liệu được cập nhật.

Điều này phù hợp nếu collection báo cáo **cố ý chứa cả trường tự động lẫn trường thủ công**. Đổi lại, nếu schema của pipeline đã thay đổi và không còn xuất trường cũ, những trường lỗi thời có thể **tiếp tục nằm ở đích**.

**Nên quyết định rõ quyền sở hữu của từng trường:** trường nào do pipeline tính, trường nào do người dùng quản lý, trường nào cần xóa khi làm mới.

### 9.3. Tách dữ liệu tự động và chú thích thủ công

Một thiết kế thường dễ kiểm soát hơn là:

```text
dailyReport208
  day, channel, orderCount, totalAmount

dailyReportAnnotations208
  day, channel, reviewedBy, note, approvalStatus
```

Khi đó có thể làm mới dữ liệu tổng hợp độc lập, còn chú thích được lưu theo khóa nghiệp vụ trong collection khác. API đọc kết hợp chúng khi cần. Đổi lại, hệ thống phải xử lý việc join, đồng bộ khóa và phân quyền.

Đây là ví dụ **thiết kế dữ liệu để giảm rủi ro ghi đè**, thay vì chỉ chọn một tham số `whenMatched`.

## 10. `whenMatched` dạng pipeline: cập nhật có tính toán

Một điểm mạnh của `$merge` là có thể tùy chỉnh cách cập nhật document đã khớp bằng **aggregation update pipeline**.

### 10.1. Ví dụ cộng dồn số đếm

Giả sử nguồn đầu vào chỉ chứa **delta mới phát sinh** cho mỗi khóa `day + channel`, chứ không phải toàn bộ tổng lịch sử. Khi đó:

```javascript
{
  $merge: {
    into: "dailyReportMerge208",
    on: ["day", "channel"],
    whenMatched: [
      {
        $set: {
          orderCount: {
            $add: ["$orderCount", "$$new.orderCount"]
          },
          totalAmount: {
            $add: ["$totalAmount", "$$new.totalAmount"]
          }
        }
      }
    ],
    whenNotMatched: "insert"
  }
}
```

Ở đây:

- `"$orderCount"` và `"$totalAmount"` tham chiếu dữ liệu **đang có trong document đích**.
- `"$$new.orderCount"` và `"$$new.totalAmount"` tham chiếu **document kết quả mới từ pipeline nguồn** khi dùng ngữ cảnh biến mặc định tương ứng.
- `$add` tạo giá trị cộng dồn để lưu vào đích.

Đây là **mẫu minh họa delta**, không dùng nó với `dailyPipeline` tính **toàn bộ snapshot** của nguồn: nếu chạy lại cùng snapshot, bạn sẽ cộng lại toàn bộ doanh thu một lần nữa.

### 10.2. Tại sao cộng dồn dễ gây đếm đôi?

Giả sử đích có:

```javascript
{ day: "2026-11-01", channel: "web", orderCount: 5, totalAmount: 500000 }
```

Một delta mới là:

```javascript
{ day: "2026-11-01", channel: "web", orderCount: 1, totalAmount: 100000 }
```

Lần chạy thứ nhất cộng thành `6 / 600000`. Nếu job timeout và ứng dụng **phát lại cùng delta như một yêu cầu nghiệp vụ mới**, kết quả có thể thành `7 / 700000`.

Đó là **không idempotent**.

Muốn xây bộ đếm đáng tin cậy từ sự kiện:

- Mỗi sự kiện/delta cần **ID duy nhất** và cơ chế ghi nhận đã xử lý.
- Chỉ cập nhật tổng khi sự kiện chưa được áp dụng.
- Cần quan tâm atomicity giữa việc ghi dấu sự kiện và ghi counter; không suy rằng một `$merge` tự bảo đảm exactly-once.
- Có quy trình đối soát hoặc tính lại từ nguồn sự thật nếu xảy ra sai lệch.

Với nhiều dashboard thông thường, **tính lại toàn bộ nhóm rồi `replace` theo khóa** dễ phục hồi hơn cộng dồn delta không có kiểm soát trùng.

### 10.3. Những stage hợp lệ trong `whenMatched` pipeline

Pipeline của `whenMatched` không phải pipeline aggregation tổng quát. MongoDB chỉ hỗ trợ một tập **stage biến đổi document** thích hợp trong ngữ cảnh cập nhật, chẳng hạn `$set`/`$addFields`, `$project`/`$unset` và `$replaceRoot`/`$replaceWith` theo quy tắc của phiên bản.

Không đặt `$group`, `$out` hoặc `$merge` vào pipeline cập nhật này rồi mong chúng tạo một luồng tổng hợp mới.

Pipeline cũng không được thay các trường **`on`**, `_id` hoặc shard key theo cách vi phạm ràng buộc bất biến. Nếu cần thay khóa định danh nghiệp vụ, thường phải thiết kế thao tác tạo/xóa riêng và cân nhắc tính nhất quán.

### 10.4. Biến `let` khi cần chỉ rõ dữ liệu mới

`$merge` cho phép định nghĩa biến qua `let` để biểu thức cập nhật tham chiếu dữ liệu từ pipeline nguồn. Khi dùng `let`, phải hiểu phạm vi tên biến và cách tham chiếu `$$variableName` theo MongoDB version. Không trộn mặc định `$$new` và biến tự định nghĩa mà không xác nhận ngữ cảnh thực tế.

Với mẫu `replace` và `merge` đơn giản, **không cần** viết `let`.

## 11. Ngữ nghĩa lỗi và tính nguyên tử: hai stage khác nhau rất xa

### 11.1. `$out`: công bố toàn bộ snapshot ở bước thay thế

Ở collection đích thông thường, `$out` tạo bộ dữ liệu thay thế rồi thực hiện bước công bố cuối. Nếu aggregation lỗi **trước khi thay thế thành công**, collection đích cũ thường vẫn còn để người đọc sử dụng.

Đây là một lợi thế lớn của `$out` cho **full refresh**. Tuy nhiên:

- Nó không giúp phục hồi nội dung collection cũ **sau khi bạn đã công bố một snapshot sai nhưng hợp lệ**.
- Không được coi việc tạo snapshot nguồn là snapshot transaction nhất quán nếu dữ liệu nguồn thay đổi trong lúc đọc.
- Quyền tạo/thay thế collection và các ràng buộc loại collection đích phải được đáp ứng.

Nếu đã công bố dữ liệu sai, cần backup/versioned snapshot hoặc quy trình tái tính toán có kiểm soát để khôi phục.

### 11.2. `$merge`: từng document được ghi, không phải một lần thay toàn bộ

`$merge` áp dụng quy tắc ghi lên từng document kết quả. Các thao tác ghi một document tuân theo ranh giới atomicity của MongoDB ở **mức document**, nhưng **toàn bộ một pipeline `$merge` không phải transaction nguyên tử nhiều document**.

Giả sử pipeline sinh 1.000 bản ghi:

```text
Document kết quả #1  -> ghi thành công
Document kết quả #2  -> ghi thành công
...
Document kết quả #600 -> ghi thành công
Document kết quả #601 -> gặp duplicate key / validation / lỗi ghi
                         |
                         v
              Pipeline có thể kết thúc lỗi
                         |
                         v
       Những ghi trước đó có thể đã nằm ở đích
```

Không có bảo đảm “một lỗi bất kỳ sẽ tự rollback toàn bộ 600 document đã ghi”.

Đó là lý do `whenMatched: "fail"` hoặc `whenNotMatched: "fail"` **không phải** công cụ kiểm tra trước rồi ghi tất cả-or-không-gì. Nó có thể phát hiện lỗi khi đi tới một document cụ thể, sau khi những document trước đã được áp dụng.

### 11.3. Nếu nguồn thay đổi trong khi chạy

Một aggregation có thể mất nhiều giây/phút để đọc collection nguồn. Trong lúc đó, ứng dụng khác có thể chèn, sửa hoặc xóa đơn hàng.

Kết quả của pipeline cần được hiểu trong **ngữ cảnh read concern và tính nhất quán** được sử dụng, không mặc định là một snapshot nghiệp vụ chốt tại thời điểm cố định.

Với báo cáo cuối ngày, nên xác định:

- Khoảng thời gian chốt báo cáo và timezone.
- Có cho ghi muộn/sửa đơn quá khứ không?
- Khi nào dữ liệu nguồn được coi là ổn định?
- Có cần chạy lại nhóm của ngày trước khi phát sinh hoàn tiền hoặc chỉnh sửa không?
- Cần log phiên bản nguồn, thời điểm chốt hoặc watermark ra sao?

Thao tác ghi kết quả an toàn chỉ là **một phần** của kiến trúc báo cáo nhất quán.

## 12. `$merge` không tự xóa những nhóm đã biến mất khỏi nguồn

Đây là một trong những khác biệt nghiệp vụ nguy hiểm nhất khi so sánh `$out` và `$merge`.

Giả sử sau lần chạy trước, đích có:

```javascript
{ day: "2026-11-02", channel: "app", orderCount: 1, totalAmount: 70000 }
```

Sau đó, đơn O07 đổi từ `PAID` sang `CANCELLED`. Không còn đơn PAID nào thuộc nhóm `2026-11-02 + app` trong bộ dữ liệu ban đầu.

Khi chạy lại `dailyPipeline`:

- Pipeline **không phát ra** document cho nhóm `2026-11-02 + app`.
- `$merge` **không được yêu cầu xử lý** nhóm đó vì không có document nguồn.
- Document cũ ở collection đích **vẫn tồn tại**, dù số liệu đã hết hợp lệ.

Đây là tình huống **stale target row**.

### 12.1. Minh họa trên bộ dữ liệu

Ví dụ sau làm thay đổi nguồn nếu chạy; chỉ thử sau khi đã quan sát kết quả ban đầu:

```javascript
source.updateOne(
  { _id: "O07" },
  { $set: { status: "CANCELLED" } }
);

source.aggregate([
  ...dailyPipeline,
  {
    $merge: {
      into: "dailyReportMerge208",
      on: ["day", "channel"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]).toArray();
```

Lệnh `$merge` không tự xóa bản ghi đích ngày 2026-11-02/kênh app. Trong khi đó, nếu chạy lại `$out` thành công trên cùng công thức, collection được tạo mới từ **những nhóm hiện còn trong nguồn**, nên nhóm không tồn tại không xuất hiện trong bản snapshot mới.

### 12.2. Cách kiểm soát khi cần đồng bộ đầy đủ

Tùy mục tiêu:

1. **Full refresh:** ưu tiên `$out` khi muốn collection báo cáo bằng đúng toàn bộ kết quả pipeline hiện tại.
2. **Partial refresh có khóa phạm vi:** xác định ngày/tenant/kênh nào được tái tính, cách xóa dữ liệu cũ trong phạm vi đó và cách xử lý lỗi giữa bước xóa/ghi. **Không xóa trước bằng `deleteMany()` trên production mà chưa có cơ chế bảo vệ khỏi ghi một phần**.
3. **Staging rồi công bố:** ghi kết quả vào collection staging, kiểm tra, sau đó công bố qua cơ chế thay thế/đổi tên collection thích hợp với deployment.
4. **Đánh dấu version hoặc active:** lưu version của lần tổng hợp, rồi chỉ đọc bản hiện hành; cần có quy tắc chuyển version và dọn dữ liệu cũ.

Không có một tham số của `$merge` tự hiểu ý nghĩa “xóa mọi document đích không có trong snapshot nguồn”.

## 13. Rủi ro khi đọc và ghi vào cùng collection

MongoDB có thể cho phép những pipeline ghi vào cùng collection mà chúng đọc, nhưng đây không phải cách triển khai mặc định nên chọn.

### 13.1. Tại sao cùng nguồn và đích rủi ro với `$merge`?

Ví dụ khái niệm:

```javascript
db.someCollection.aggregate([
  { $match: { active: true } },
  { $set: { updatedAt: new Date() } },
  {
    $merge: {
      into: "someCollection",
      on: "_id",
      whenMatched: "merge",
      whenNotMatched: "insert"
    }
  }
]);
```

Khi pipeline đọc một collection rồi cập nhật lại các document của chính collection đó, một thao tác ghi có thể làm document thay đổi vị trí trong cách thực thi lưu trữ/index. Trong những điều kiện nhất định, cursor đọc có thể gặp lại document đã cập nhật, gây rủi ro xử lý lặp — thường được gọi là **Halloween problem**.

Đừng xem ví dụ trên là công thức migration an toàn.

### 13.2. Cách tiếp cận thực tế

- Nếu chuyển đổi lớn, cân nhắc ghi vào **collection mới** rồi công bố.
- Nếu cập nhật một tập document có điều kiện, xem xét **update pipeline** trực tiếp với filter phù hợp.
- Nếu cần `$merge` vào chính nguồn, phải hiểu rủi ro reprocessing, khóa định danh, điều kiện truy vấn và khả năng chạy lại, đồng thời thử nghiệm trên dữ liệu đại diện.
- Không coi `on: "_id"` tự động loại bỏ mọi rủi ro đọc-ghi trên cùng collection.

## 14. Chọn giữa `$out` và `$merge`

| Tiêu chí | `$out` | `$merge` |
|---|---|---|
| Mục đích chính | Công bố **toàn bộ kết quả** như một collection mới | Đồng bộ **từng document** theo khóa |
| Collection đích đã có | Thay toàn bộ tập dữ liệu khi thành công | Giữ collection, áp dụng insert/update theo quy tắc |
| Nhóm cũ không xuất hiện trong kết quả mới | Bị loại khỏi snapshot đích | **Vẫn tồn tại**, trừ khi có cơ chế riêng |
| Khóa `on` | Không có tham số `on` | Có `on`, cần unique index phù hợp |
| Chọn xử lý document đã khớp | Không áp dụng theo từng document | `replace`, `merge`, `keepExisting`, `fail` hoặc pipeline |
| Chọn xử lý document chưa khớp | Tạo từ kết quả | `insert`, `discard` hoặc `fail` |
| Nguy cơ ghi một phần nhìn thấy ở đích | Công bố bằng thao tác thay collection sau khi chuẩn bị kết quả | Có thể đã ghi một số document trước khi lỗi |
| Index hiện có | Có cơ chế sao chép index khi thay collection đích thông thường | Dùng index của đích hiện tại; `on` cần unique index thích hợp |
| Sharded destination | Không hỗ trợ trực tiếp theo quy tắc thông thường | Có thể hỗ trợ, với ràng buộc shard key và unique index |
| Bảo toàn trường đích không có ở nguồn | Không | Có thể, với `whenMatched: "merge"` |
| Khả năng chạy lại | Thường tái tạo snapshot; bản cũ bị thay | Tùy quy tắc: `replace` snapshot ổn định hơn cộng delta |
| Khi phù hợp | Full materialization, batch snapshot, bảng báo cáo tái tạo hoàn toàn | Upsert, đồng bộ theo khóa, bổ sung/điều chỉnh nhóm |

**Không có lựa chọn nào “an toàn hơn” trong mọi trường hợp.** `$out` có lợi thế công bố snapshot toàn bộ, nhưng rất nguy hiểm khi đích có dữ liệu cần bảo toàn. `$merge` linh hoạt, nhưng có thể để lại dữ liệu cũ hoặc cập nhật một phần khi lỗi.

## 15. Thiết kế khóa và tính duy nhất của kết quả tổng hợp

### 15.1. Khóa tổng hợp phải mô tả đúng đơn vị thống kê

Với báo cáo theo **ngày + kênh**, khóa là:

```javascript
{ day: "2026-11-01", channel: "web" }
```

Nhưng nếu hệ thống đa tenant, một ngày/kênh có thể xuất hiện ở nhiều khách hàng doanh nghiệp. Khi đó cần khóa:

```javascript
{
  tenantId: "T01",
  day: "2026-11-01",
  channel: "web"
}
```

và index tương ứng:

```javascript
demo.someTenantReport208.createIndex(
  { tenantId: 1, day: 1, channel: 1 },
  { unique: true }
);
```

Nếu quên `tenantId` trong `on`, các tenant khác nhau có thể **ghi đè báo cáo của nhau** hoặc không có cách phân biệt document đích. Đây là lỗi nghiêm trọng hơn một vấn đề hiệu năng.

### 15.2. Giữ kiểu khóa nhất quán

Đừng để một job xuất:

```javascript
{ day: "2026-11-01", channel: "web" }
```

nhưng job khác dùng:

```javascript
{ day: ISODate("2026-11-01T00:00:00Z"), channel: "web" }
```

Vì `day` là String ở job thứ nhất nhưng BSON Date ở job thứ hai, khóa không tương đương theo cùng schema. Hệ quả là chèn thêm bản ghi trùng **về ý nghĩa nghiệp vụ** hoặc không match vào bản ghi cần cập nhật.

Chọn một chuẩn:

- Ngày lưu dạng Date đã chuẩn hóa về đầu ngày theo quy tắc timezone.
- Hoặc ngày là chuỗi ISO `YYYY-MM-DD` và quy định timezone dùng để tính.

Không để nhiều job tùy ý lựa chọn cách biểu diễn.

### 15.3. Không thay khóa `on` trong quá trình cập nhật

Khi sử dụng `$merge`, các trường xác định document đích phải được xem là **định danh của bản ghi báo cáo**, không phải thuộc tính mà update pipeline tự do sửa. Nếu nghiệp vụ đổi `channel` từ `"web"` sang `"app"`, đó có thể là:

- Một bản ghi nguồn được đổi thuộc tính.
- Một nhóm báo cáo cũ cần giảm số liệu hoặc biến mất.
- Một nhóm mới cần tăng số liệu.

`$merge` theo snapshot sẽ tạo/cập nhật nhóm mới, nhưng **không tự giải quyết việc xóa nhóm cũ**. Phần 12 đã chỉ rõ vì sao cần cơ chế đồng bộ đầy đủ.

## 16. Bảo vệ collection đích trước khi chạy job

### 16.1. Dùng collection staging

Một workflow phổ biến:

```text
orders
  |
  v
Aggregation đọc + biến đổi
  |
  v
report_daily_staging_<run_id>
  |
  +-- kiểm tra tập khóa, số nhóm, tổng tiền, ràng buộc
  |
  +-- nếu không đạt: giữ bản production cũ
  |
  +-- nếu đạt: công bố qua bước thay thế phù hợp
  |
  v
report_daily_current
```

Staging cho phép ứng dụng **quan sát trước bộ kết quả ghi** mà không phải thay bảng đang phục vụ người dùng ngay lập tức.

Nếu dùng `$out`, MongoDB vốn đã có cơ chế collection tạm trong quá trình xây dựng kết quả trước khi thay đích. Nhưng **collection tạm nội bộ** không thay cho staging có tên riêng nếu quy trình cần bước duyệt số liệu bởi người vận hành trước khi công bố.

### 16.2. Preview bằng pipeline chỉ đọc

Trước khi thêm `$out` hoặc `$merge`, chạy:

```javascript
const preview = source.aggregate([
  ...dailyPipeline,
  { $sort: { day: 1, channel: 1 } }
]).toArray();

printjson(preview);
```

Có thể kiểm tra:

- Số nhóm đầu ra có hợp lý không?
- Mỗi nhóm có đủ trường `day`, `channel`, `orderCount`, `totalAmount` không?
- Tổng `orderCount` có đúng số đơn PAID cần tính không?
- Tổng `totalAmount` có đúng tổng tiền theo quy tắc nghiệp vụ không?
- Có khóa bị null/missing, sai kiểu hoặc thiếu tenant không?
- Có nhóm ngoài phạm vi ngày dự kiến không?

Đối với dữ liệu lớn, không nhất thiết gọi `toArray()` trên **mọi document kết quả**. Có thể dùng một pipeline kiểm tra các chỉ số tổng trên dữ liệu staging, hoặc đọc một mẫu đủ đại diện. Tránh chuyển toàn bộ hàng triệu document về RAM chỉ để preview.

### 16.3. Đếm nguồn và đếm đầu ra theo đúng phạm vi

Đếm số đơn PAID:

```javascript
source.countDocuments({ status: "PAID" });
// 6 trên bộ dữ liệu tám đơn ban đầu.
```

Đếm số nhóm sau tổng hợp:

```javascript
source.aggregate([
  ...dailyPipeline,
  { $count: "groups" }
]).toArray();
// [{ groups: 4 }] trên bộ dữ liệu ban đầu.
```

Hai con số khác nhau vì **một nhóm có thể gộp nhiều đơn**. Không dùng `countDocuments()` của collection nguồn để kết luận số document đích sau `$group` phải bằng số document nguồn.

Nếu pipeline đầu vào rỗng, `$count` có thể không trả document; code kiểm tra cần xử lý trường hợp đó và xác định rõ liệu snapshot rỗng có hợp lệ.

## 17. Kiểm soát ràng buộc và quyền khi ghi

### 17.1. Unique index và schema validation

Một pipeline tính toán có thể tạo dữ liệu đúng theo cú pháp nhưng sai theo schema:

```javascript
{
  day: null,
  channel: ["web", "app"],
  orderCount: "two",
  totalAmount: -100
}
```

Những giá trị này không phù hợp với khóa `on` và ý nghĩa báo cáo đã chọn. Trước khi ghi:

- Chuẩn hóa kiểu `day`, `channel`.
- Kiểm tra rằng khóa là scalar và không null/missing theo yêu cầu.
- Bảo đảm `orderCount` và `totalAmount` được tính đúng kiểu số.
- Cân nhắc collection validation để chặn dữ liệu sai định dạng.
- Xem ràng buộc unique index và collation.

Nếu bị lỗi unique key hoặc validation trong `$merge`, **những cập nhật trước lỗi có thể đã được áp dụng**. Với `$out`, lỗi có thể khiến bước thay collection không hoàn tất. Vì thế, hai stage yêu cầu chiến lược vận hành khác nhau.

### 17.2. Nguyên tắc quyền tối thiểu

Tài khoản chạy báo cáo chỉ nên có quyền **đọc collection nguồn** và **ghi đúng collection/database đích cần thiết**. Nếu dùng `$out`, quyền tạo, rename hoặc thay thế collection có thể là điều kiện quan trọng; không cấp quyền xóa/thay thế toàn bộ database cho tài khoản job chỉ vì tiện triển khai.

Nếu một tài khoản có thể chỉ cần upsert vào collection báo cáo, `$merge` cùng quyền hạn được giới hạn có thể giảm phạm vi tác động so với một tài khoản được phép thay collection lớn. Nhưng rủi ro ghi nhầm theo `on` vẫn phải được kiểm soát.

### 17.3. Ghi thông tin job ở nơi riêng

Một công việc batch nên có thông tin vận hành như:

```javascript
{
  job: "dailyRevenue",
  runId: "run-2026-11-03-001",
  sourceFrom: ISODate("2026-11-01T00:00:00Z"),
  sourceTo: ISODate("2026-11-03T00:00:00Z"),
  startedAt: ISODate("2026-11-03T01:00:00Z"),
  completedAt: ISODate("2026-11-03T01:00:12Z"),
  status: "COMPLETED",
  expectedGroups: 4
}
```

Đây là **mẫu log metadata**, không phải dữ liệu sẽ tự được `$out` hoặc `$merge` tạo ra. Có thể lưu job log ở collection khác hoặc hệ thống giám sát, với chính sách retry và phân quyền phù hợp.

Đừng chỉ dựa vào một log `"COMPLETED"` của ứng dụng để kết luận dữ liệu đã được công bố đúng: nên đối chiếu trạng thái collection đích hoặc marker phiên bản khi job thực sự kết thúc.

## 18. Chống chạy đồng thời và chạy lại

### 18.1. Hai job cùng ghi vào một đích

Giả sử:

- Job A tính báo cáo từ dữ liệu đến 10:00.
- Job B tính báo cáo từ dữ liệu đến 10:05.
- B hoàn thành trước, A hoàn thành sau.

Nếu cả hai ghi cùng một collection, trạng thái cuối có thể phản ánh **bản cũ** của A dù B đã tính dữ liệu mới hơn.

Với `$out`, cả hai đều muốn thay toàn bộ collection. Với `$merge`, từng nhóm có thể được cập nhật bởi các lần chạy xen kẽ, khiến dữ liệu đích chứa **hỗn hợp version**.

### 18.2. Các cách ngăn ghi đè ngược thời gian

Có thể cân nhắc:

- Chỉ cho **một job cùng loại/phạm vi** chạy tại một thời điểm.
- Dùng run ID, watermark hoặc version để xác định phiên nào được phép công bố.
- Ghi vào staging riêng theo run ID, rồi chỉ công bố bản đã kiểm tra và được đánh giá mới nhất.
- Với `$merge`, nếu giữ history nhiều version, đưa `version` vào khóa và có quy trình lựa chọn bản hiện hành; không coi điều đó tự giải quyết mọi cuộc đua cập nhật.

Việc quản lý concurrency phải nằm trong **cơ chế điều phối** hoặc kiến trúc dữ liệu, không thể chỉ dựa vào `$merge` sẽ tự biết job nào mới hơn.

### 18.3. Các loại chạy lại cần phân biệt

| Tình huống | Hệ quả cần lưu ý |
|---|---|
| Chạy lại `$out` với cùng snapshot | Đích được thay bằng dữ liệu nghiệp vụ tương đương; vẫn có chi phí xây lại và thay |
| Chạy lại `$merge` với `replace` và cùng snapshot | Bản ghi có khóa khớp được thay bằng dữ liệu tương đương |
| Chạy lại `$merge` với `merge` | Trường mới được ghi đè, trường cũ ngoài nguồn có thể còn |
| Chạy lại `$merge` dạng cộng delta | Có thể **cộng hai lần** nếu delta đã được áp dụng |
| Chạy lại sau lỗi `$merge` giữa chừng | Cần chiến lược phục hồi các bản đã cập nhật và những bản chưa |
| Chạy lại sau khi dữ liệu nguồn đổi trạng thái | Nhóm cũ có thể biến mất khỏi nguồn nhưng `$merge` không xóa ở đích |

Một job có thể **chạy lại an toàn** trong một số trạng thái nhưng không trong trạng thái khác. Phải xác định idempotency bằng ngữ nghĩa cụ thể của `whenMatched`, `on` và nguồn dữ liệu.

## 19. Điều gì xảy ra khi nguồn hoặc đích được shard?

MongoDB có thể chạy aggregation trên một deployment sharded; tuy nhiên, **khả năng đọc từ shard và ghi đến sharded destination là hai câu hỏi khác nhau**.

### 19.1. `$out` và sharded destination

`$out` không hỗ trợ việc trực tiếp thay thế **một collection đích đã shard** theo quy tắc thông thường. Nó vẫn có thể đọc kết quả aggregation từ nguồn phù hợp, nhưng đích cần đáp ứng giới hạn của stage.

Nếu mục tiêu là làm mới một collection đã shard, xem `$merge` hoặc kiến trúc staging/công bố riêng, tùy yêu cầu toàn bộ snapshot và quy tắc shard key.

### 19.2. `$merge` và sharded destination

`$merge` có thể ghi vào sharded collection khi các điều kiện phù hợp được đáp ứng. Khóa `on` mặc định hoặc tùy chỉnh phải tương thích với **shard key** và yêu cầu unique index trên đích.

Không thể dùng một khóa `on` tùy ý vốn không có khả năng định tuyến hoặc không đáp ứng unique index của sharded collection rồi kỳ vọng MongoDB tự tìm một bản ghi duy nhất trên tất cả shard.

### 19.3. Chỉ số báo cáo đa tenant

Nếu sharding theo `tenantId`, hãy bảo đảm pipeline không làm mất `tenantId` khi tổng hợp:

```javascript
{
  $group: {
    _id: {
      tenantId: "$tenantId",
      day: "$day",
      channel: "$channel"
    },
    orderCount: { $sum: 1 },
    totalAmount: { $sum: "$amount" }
  }
}
```

Sau đó project các trường khóa lên top-level để dùng trong `on`. Thiết kế cụ thể còn phụ thuộc chiến lược sharding và phiên bản MongoDB; cần kiểm tra trước khi triển khai thực tế.

## 20. Tác động hiệu năng và vận hành

### 20.1. Công việc trên nguồn

Trước khi ghi, MongoDB vẫn phải chạy các stage đọc và tính:

```text
$match -> $group -> $project -> write stage
```

Nếu `$match` quét toàn collection, `$group` phải giữ rất nhiều nhóm, hoặc pipeline sort dữ liệu lớn, việc tăng số tài nguyên đích không loại bỏ được chi phí nguồn.

Ví dụ index có thể hỗ trợ lọc theo trạng thái và thời gian:

```javascript
source.createIndex({
  status: 1,
  createdAt: 1
});
```

Index là ứng viên cần thử theo mẫu `$match` thực tế, chẳng hạn lọc trạng thái `PAID` cùng một khoảng ngày. Nó không tự làm `$group` theo ngày/kênh nhanh trong mọi tình huống. Dùng `explain("executionStats")` trên **pipeline chỉ đọc** để xem `COLLSCAN`/`IXSCAN`, tài nguyên và số document đầu vào.

### 20.2. Công việc trên đích

`$out`:

- Cần xây dựng collection kết quả mới.
- Có thể phải tạo/copy các index của đích.
- Có chi phí thay thế collection và làm mới cache/index liên quan.
- Phù hợp cho snapshot lớn khi chi phí tạo lại chấp nhận được.

`$merge`:

- Thực hiện đối chiếu khóa `on` cho từng document kết quả.
- Có chi phí tìm kiếm bằng index và insert/update.
- Nhiều index phụ trên đích làm thao tác ghi tốn thêm công.
- Có thể chỉ ghi một tập nhóm thay đổi, nhưng đòi hỏi kiểm soát nhóm cũ và dữ liệu đến muộn.

Không có công thức phổ quát “`$merge` luôn nhanh hơn `$out`”. Với full refresh hàng triệu dòng, upsert từng bản ghi có thể tốn chi phí đáng kể; với thay đổi vài trăm nhóm trong một collection rất lớn, thay toàn bộ qua `$out` có thể lãng phí.

### 20.3. `allowDiskUse` không giải quyết lỗi dữ liệu đích

```javascript
source.aggregate(
  [
    ...dailyPipeline,
    { $out: "dailyReportOut208" }
  ],
  { allowDiskUse: true }
).toArray();
```

Trong những phiên bản/cấu hình hỗ trợ, `allowDiskUse` cho phép một số stage tiêu thụ bộ nhớ lớn dùng không gian tạm trên đĩa. Nó **không**:

- Biến `$merge` thành all-or-nothing.
- Bỏ qua unique index hoặc validation.
- Giúp `$out` ghi vào sharded collection đích không được hỗ trợ.
- Tự tối ưu một filter sai hoặc một khóa `on` không ổn định.

### 20.4. Read concern và write concern

Tính đúng và độ bền của kết quả còn phụ thuộc các chính sách MongoDB như:

- **Read concern:** dữ liệu nguồn được đọc với mức đảm bảo nào.
- **Write concern:** yêu cầu xác nhận ghi ở mức nào.
- **Read preference:** nguồn có thể được đọc từ thành viên nào trong deployment, theo các giới hạn của thao tác.
- **Session, topology và failover:** thao tác kéo dài có thể bị gián đoạn bởi sự cố hạ tầng.

Không nên chỉ nhìn việc lệnh aggregate trả về mà tự suy ra mọi replica đều đã áp dụng dữ liệu hoặc snapshot nguồn luôn nhất quán theo một thời điểm. Những bảo đảm đó cần được xác định theo cấu hình thực tế và yêu cầu nghiệp vụ.

## 21. Java MongoDB Driver: chạy pipeline có stage ghi

Trong ứng dụng Java dùng **MongoDB Sync Driver**, có thể xây dựng aggregation pipeline bằng các `Bson` stage. Ví dụ rút gọn ghi một collection đích bằng `$merge`:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;

public class MergeExample {
    public static void main(String[] args) {
        try (MongoClient client = MongoClients.create(
                "mongodb://localhost:27017")) {

            MongoCollection<Document> source = client
                    .getDatabase("mongo_training_208")
                    .getCollection("salesOrders208");

            // Ví dụ đơn giản: ghi số đơn PAID theo channel.
            List<Bson> pipeline = List.of(
                    new Document("$match",
                            new Document("status", "PAID")),

                    new Document("$group",
                            new Document("_id", "$channel")
                                    .append("orderCount",
                                            new Document("$sum", 1))),

                    new Document("$project",
                            new Document("_id", 0)
                                    .append("channel", "$_id")
                                    .append("orderCount", 1)),

                    new Document("$merge",
                            new Document("into", "channelSummary208")
                                    .append("on", "channel")
                                    .append("whenMatched", "replace")
                                    .append("whenNotMatched", "insert"))
            );

            // Cần tạo sẵn unique index {channel: 1} ở đích.
            source.aggregate(pipeline).toCollection();
        }
    }
}
```

Trước khi chạy đoạn Java, tạo unique index:

```javascript
demo.channelSummary208.createIndex(
  { channel: 1 },
  { unique: true }
);
```

Điểm đáng nhớ:

- API Java gọi `aggregate(pipeline)` nhưng **tác động cuối cùng là ghi** do có `$merge`.
- `toCollection()` là cách sử dụng của Sync Driver cho pipeline ghi kết quả; không phải mong chờ một danh sách document đầu ra.
- Driver phải có quyền trên nguồn và đích.
- Các ngoại lệ duplicate key, validation, quyền hoặc mạng cần được ghi nhận và xử lý; không đánh dấu job thành công nếu không biết lệnh ghi đã hoàn tất.
- Khi gặp lỗi không rõ thao tác đã ghi đến đâu, phải dựa vào tính idempotent của workflow và việc kiểm tra kết quả đích trước khi quyết định retry.

Ví dụ Java trên dùng schema đơn giản để giải thích cách gọi driver; với job báo cáo ngày/kênh, ứng dụng có thể dùng chính các stage của `dailyPipeline` và tạo unique compound index tương ứng.

## 22. Các anti-pattern cần tránh

### 22.1. Dùng `$out` vào collection gốc chỉ để “cập nhật vài trường”

```javascript
// Nguy hiểm nếu orders là collection nghiệp vụ cần được bảo toàn.
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $project: { customerId: 1, amount: 1 } },
  { $out: "orders" }
]);
```

Nếu chạy thành công, collection `orders` có thể chỉ còn tập document `PAID` với một phần trường được project. Những đơn không khớp và các trường không được giữ lại **có thể biến mất**. Đây không phải một lệnh cập nhật cột an toàn.

### 22.2. Dùng `$merge` với `on` không đại diện đúng khóa

```javascript
// Sai ý định nếu báo cáo phải phân biệt từng ngày và từng kênh.
{
  $merge: {
    into: "dailyReport",
    on: "day",
    whenMatched: "replace",
    whenNotMatched: "insert"
  }
}
```

Ở cùng một ngày, kênh web và app cần hai document. Dùng chỉ `day` có thể gây xung đột uniqueness, hoặc một bản ghi ghi đè bản ghi khác nếu thiết kế index/khóa cho phép. Phải dùng `on: ["day", "channel"]` và unique index phù hợp.

### 22.3. Tưởng `whenMatched: "merge"` tự cộng dồn

`merge` ở đây là **gộp field**, không tự tính tổng số. Nếu muốn cộng, cần expression rõ ràng và cơ chế tránh đếm đôi khi phát lại.

### 22.4. Cho rằng `$merge` xóa nhóm không còn trong nguồn

`$merge` không đi qua những document đích **không có kết quả nguồn khớp**. Vì thế, một full refresh bằng upsert có thể để lại các nhóm báo cáo cũ, dẫn tới dashboard sai.

### 22.5. Cho rằng lỗi ở cuối pipeline không ảnh hưởng dữ liệu đã ghi

Với `$merge`, một số document có thể đã được insert/update trước khi lỗi. Không tự retry mù quáng những phép cộng dồn hoặc dùng tình trạng lỗi như bằng chứng rằng “chưa ghi gì”.

### 22.6. Coi thứ tự kết quả pipeline là thứ tự lưu trong collection

`$sort` trước `$out` không khiến `find()` trên collection đích tự trả đúng thứ tự đó mãi mãi. **Collection không có thứ tự đọc mặc định mang ý nghĩa nghiệp vụ**. Nếu ứng dụng cần theo `day` hoặc `channel`, hãy `sort()` ở câu truy vấn đọc.

### 22.7. Lấy `_id` của `$group` làm khóa tùy tiện

`$group` có thể tạo `_id` kiểu object. Nếu `on` là các field khác hoặc khóa nhóm được biểu diễn không nhất quán, lệnh `$merge` có thể tạo bản ghi ngoài ý muốn hoặc vi phạm trường bất biến. Hãy **chủ động thiết kế khóa** và project ra schema rõ ràng.

### 22.8. Ghi đè trường do người dùng quản lý

Không để một pipeline báo cáo `replace` xóa nhận xét phê duyệt của chuyên viên nếu các trường đó nằm trong cùng document. Tách quyền sở hữu dữ liệu hoặc dùng quy tắc `merge` phù hợp.

## 23. Một quy trình vận hành có kiểm soát

Đối với một job xây bảng tổng hợp mỗi ngày, có thể tổ chức:

### Bước 1 — Xác định hợp đồng dữ liệu đích

Ví dụ:

```javascript
{
  day: "YYYY-MM-DD",
  channel: "web | app | partner",
  orderCount: Number,
  totalAmount: Number
}
```

Xác định rõ:

- Ai sở hữu collection đích?
- Nó là snapshot toàn bộ hay các bản upsert từng khóa?
- Các trường nào được phép sửa thủ công?
- Khóa định danh duy nhất là gì?
- Dữ liệu đến muộn/sửa quá khứ được xử lý ra sao?

### Bước 2 — Chạy pipeline chỉ đọc để tính trước

```javascript
source.aggregate(dailyPipeline).toArray();
```

Với dữ liệu lớn, có thể kiểm tra tóm tắt trên pipeline chỉ đọc thay vì lấy tất cả về RAM.

### Bước 3 — Xác định chính sách snapshot hoặc upsert

- Nếu cần collection đích phản ánh **chính xác toàn bộ kết quả hiện tại**, chọn full refresh bằng `$out` hoặc staging/swap có kiểm soát.
- Nếu cần cập nhật/chèn **từng khóa**, chọn `$merge` với `on` và unique index phù hợp.
- Nếu pipeline là **delta**, phải có chiến lược idempotency trước khi sử dụng phép cộng dồn.

### Bước 4 — Kiểm tra ràng buộc đích

Đảm bảo target namespace đúng, quyền hạn phù hợp, unique index đúng khóa và dữ liệu không vi phạm schema. Với sharding hoặc collection đặc biệt, xác nhận stage ghi được hỗ trợ.

### Bước 5 — Kiểm soát job chạy song song

Tạo run ID và cơ chế ngăn hai job cùng công bố dữ liệu không theo thứ tự. Nếu là staging, mỗi run cần tên staging và chính sách dọn dẹp được kiểm soát.

### Bước 6 — Ghi kết quả

Chỉ thêm `$out` hoặc `$merge` khi dữ liệu nguồn và chính sách ghi đã xác định. Dùng write concern phù hợp với yêu cầu độ bền.

### Bước 7 — Đối chiếu sau ghi

Ví dụ với snapshot ban đầu:

```javascript
demo.dailyReportOut208.countDocuments({});
// 4 trên dữ liệu tám đơn ban đầu.

demo.dailyReportMerge208.countDocuments({});
// 4 nếu đây là lần chạy đầu vào collection rỗng.
```

Sau khi đã chạy các ví dụ thêm O09 hoặc đổi trạng thái O07, số liệu có thể khác. Phải đối chiếu với **phiên dữ liệu đang dùng**, không ép mọi lần chạy phải bằng bộ số ban đầu.

### Bước 8 — Ghi nhận run thành công và có phương án khôi phục

Ghi log run, thời điểm hoàn tất, số nhóm, phiên bản/cutoff của nguồn. Nếu cần rollback một snapshot đã công bố, phải có nguồn để tái tạo hoặc bản lưu trước khi thay thế; `$out` không tự cung cấp nút “quay về version cũ”.

## 24. Bài tập thực hành

### Bài 1 — Tạo báo cáo snapshot bằng `$out`

Từ bộ dữ liệu tám đơn:

1. Lọc chỉ đơn `PAID`.
2. Gom theo `day` trong múi giờ `Asia/Ho_Chi_Minh` và `channel`.
3. Tính `orderCount` và `totalAmount`.
4. Ghi vào `dailyReportOut208` bằng `$out`.
5. Đọc collection đích và xác nhận bốn nhóm ban đầu.

Hãy giải thích vì sao việc thêm `$sort` vào pipeline trước `$out` không thay thế cho `sort()` khi truy vấn collection đích về sau.

### Bài 2 — Đo tác động của chạy lại `$out`

Sau bài 1, thêm một document báo cáo giả lập **chỉ trong collection đích thử nghiệm**:

```javascript
demo.dailyReportOut208.insertOne({
  day: "2026-10-31",
  channel: "web",
  orderCount: 99,
  totalAmount: 999999
});
```

Chạy lại `$out` từ nguồn. Document ngày 2026-10-31 còn tồn tại không? Nếu không, điều đó minh họa ngữ nghĩa nào của `$out`? Vì sao thao tác này nguy hiểm nếu đích lưu cả những chú thích do người dùng nhập?

### Bài 3 — Chuẩn bị `$merge` theo khóa ghép

Tạo collection `dailyReportMerge208` và unique index trên `{ day: 1, channel: 1 }`. Viết pipeline `$merge` có:

```javascript
on: ["day", "channel"],
whenMatched: "replace",
whenNotMatched: "insert"
```

Chạy hai lần với nguồn không thay đổi và quan sát vì sao không xuất hiện hai document cho cùng một cặp ngày/kênh.

### Bài 4 — Phân biệt `replace` và `merge`

Trên collection thử nghiệm riêng, tạo một document đích có:

```javascript
{
  day: "2026-11-01",
  channel: "web",
  orderCount: 2,
  totalAmount: 300000,
  note: "Checked"
}
```

So sánh kết quả khi một document nguồn cùng khóa chỉ chứa `day`, `channel`, `orderCount` và `totalAmount`, với:

1. `whenMatched: "replace"`.
2. `whenMatched: "merge"`.
3. `whenMatched: "keepExisting"`.

Trường `note` có còn không? Các chỉ số tổng có được cập nhật không?

### Bài 5 — Kiểm tra nhóm đã biến mất

Sau khi tạo báo cáo lần đầu:

1. Chuyển O07 từ `PAID` sang `CANCELLED`.
2. Chạy lại `$merge` dùng `replace`.
3. Quan sát nhóm `2026-11-02 + app` ở đích.
4. Chạy lại `$out` vào collection snapshot thử nghiệm khác.
5. Giải thích vì sao kết quả hai collection khác nhau.

Đề xuất cách đồng bộ phù hợp nếu báo cáo phải phản ánh đúng **tất cả và chỉ những nhóm hiện tại**.

### Bài 6 — Tìm lỗi thiết kế khóa `on`

Một hệ thống đa tenant xuất:

```javascript
{
  tenantId: "T01",
  day: "2026-11-01",
  channel: "web",
  totalAmount: 1000
}
```

nhưng `$merge` dùng `on: ["day", "channel"]`. Hãy giải thích rủi ro khi hai tenant có cùng ngày/kênh. Sửa khóa `on`, unique index và `$group` cho đúng.

### Bài 7 — Vì sao cộng dồn delta không an toàn khi retry?

Giả sử đích có tổng `500`, delta mới là `+100`. Dùng `whenMatched` pipeline cộng dồn rồi ứng dụng tự gửi lại cùng delta do timeout.

1. Kết quả có thể thành bao nhiêu sau lần chạy thứ nhất và thứ hai?
2. Cần lưu ID của sự kiện/delta ở đâu?
3. Nếu chỉ ghi ID đã xử lý nhưng chưa cộng counter thì có vấn đề gì?
4. Nếu chỉ cộng counter nhưng chưa ghi ID đã xử lý thì có vấn đề gì?
5. Khi nào nên ưu tiên tính lại snapshot đầy đủ?

### Bài 8 — Ngăn lỗi ghi một phần

Một `$merge` sinh 100 document. Đến document thứ 61, lệnh gặp lỗi unique index.

Hãy trả lời:

- Có thể khẳng định 60 document trước chưa được ghi không?
- `whenMatched: "fail"` có phải cơ chế transaction không?
- Có thể làm gì để phục hồi từ một kết quả đã ghi một phần?
- Vì sao staging/version và job log giúp vận hành an toàn hơn?

### Bài 9 — Dữ liệu đích có field thủ công

Collection báo cáo lưu `day`, `channel`, `orderCount`, `totalAmount`, `approvalStatus` và `reviewNote`. Số liệu tự động được làm mới hằng giờ, còn `approvalStatus`/`reviewNote` do chuyên viên cập nhật.

Hãy so sánh:

- Một collection duy nhất với `whenMatched: "merge"`.
- Hai collection tách số liệu tự động và phần phê duyệt.
- Full `$out` trên collection chung.

Thiết kế nào giảm nguy cơ mất thông tin phê duyệt nhất? Những đánh đổi về truy vấn và đồng bộ là gì?

### Bài 10 — Lập kế hoạch vận hành có thể kiểm tra

Thiết kế một job chạy mỗi đêm trên 50 triệu đơn hàng:

1. Chọn phạm vi ngày, múi giờ và watermark.
2. Xác định `$match` nào có khả năng dùng index.
3. Chọn full refresh bằng `$out` hay upsert theo khóa bằng `$merge`.
4. Định nghĩa khóa đích và unique index.
5. Quy định xử lý đơn hoàn tiền/phát sinh muộn.
6. Quy định cách ngăn hai job công bố sai thứ tự.
7. Định nghĩa kiểm tra số nhóm và tổng tiền.
8. Lập phương án retry, staging, quan sát lỗi và phục hồi.

Giải thích vì sao chỉ viết được một pipeline chạy thành công **chưa đủ** để kết luận bảng báo cáo luôn đáng tin cậy.

## 25. Ghi nhớ

**`$out` dùng để công bố toàn bộ kết quả pipeline thành một collection.** Khi đích đã tồn tại, nó chuẩn bị dữ liệu mới rồi thay collection đích; các document cũ không có trong snapshot mới sẽ không được giữ lại. Đây là công cụ phù hợp cho **full refresh** khi nội dung đích hoàn toàn do pipeline sở hữu.

**`$merge` dùng để ghi theo từng khóa `on`.** Nó có thể chèn, thay, gộp trường, giữ nguyên, bỏ qua hoặc báo lỗi theo `whenMatched`/`whenNotMatched`. Khóa `on` phải phản ánh đúng định danh nghiệp vụ và được hỗ trợ bởi unique index phù hợp; những document đích **không còn xuất hiện ở nguồn** không tự bị xóa.

**Ngữ nghĩa lỗi khác nhau:** `$out` có bước công bố snapshot, còn `$merge` có thể đã ghi một phần trước khi báo lỗi. Không coi `$merge` là transaction nhiều document và không mặc định một phép cộng delta sẽ an toàn khi job chạy lại.

**Kiểm soát tác động lên dữ liệu đích là một phần của thiết kế aggregation.** Preview kết quả, kiểm tra khóa và schema, xác định quyền sở hữu trường, ngăn job chạy song song, quản lý retry/idempotency, theo dõi version và chuẩn bị cơ chế phục hồi trước khi đưa stage ghi vào môi trường thật. Khi chọn đúng giữa full snapshot và upsert theo khóa, MongoDB không chỉ tính được số liệu mà còn giúp duy trì collection tổng hợp theo một hợp đồng dữ liệu rõ ràng.
