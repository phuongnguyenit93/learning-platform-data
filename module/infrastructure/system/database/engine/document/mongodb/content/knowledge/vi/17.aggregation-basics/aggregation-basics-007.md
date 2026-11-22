# Các accumulator $sum, $avg, $min, $max, $push và $addToSet trong MongoDB

## 1. Accumulator giúp trả lời câu hỏi gì?

Trong MongoDB, một document có thể biểu diễn một đơn hàng, một lượt truy cập hay một giao dịch. Khi cần trả lời “mỗi khách có bao nhiêu đơn?”, “tổng doanh thu theo trạng thái?”, “giá trị nhỏ nhất/lớn nhất trong tháng?”, hoặc “danh sách các loại sản phẩm đã xuất hiện?”, việc đọc từng document về ứng dụng để tính toán thường không phải cách hiệu quả nhất.

**Aggregation pipeline** cho phép xử lý dữ liệu theo chuỗi stage ngay tại MongoDB. Trong nhiều stage như **$group**, các **accumulator** nhận các giá trị từ nhiều document và tạo một kết quả tổng hợp.

Ví dụ đơn giản:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" },
      averageAmount: { $avg: "$amount" }
    }
  }
]);
~~~

Mỗi document đi vào **$group** được phân vào một nhóm theo status. Các accumulator xử lý những document của từng nhóm:

| Accumulator | Câu hỏi thường gặp | Kiểu kết quả điển hình |
| --- | --- | --- |
| **$sum** | Tổng số tiền/số lượng; hoặc đếm số document | Number |
| **$avg** | Giá trị trung bình | Number hoặc null |
| **$min** | Giá trị nhỏ nhất theo quy tắc so sánh BSON | Giá trị nhỏ nhất hoặc null |
| **$max** | Giá trị lớn nhất theo quy tắc so sánh BSON | Giá trị lớn nhất hoặc null |
| **$push** | Lưu các giá trị của từng document vào danh sách, có thể trùng | Array |
| **$addToSet** | Thu thập các giá trị phân biệt trong nhóm | Array với các phần tử khác nhau, **không có thứ tự đảm bảo** |

**Quan trọng:** accumulator không phải lúc nào cũng “một hàm áp dụng cho cả collection”. Kết quả phụ thuộc **$group._id**, các stage lọc trước đó, kiểu BSON của đầu vào và thứ tự document đi vào stage.

### 1.1. Từ document riêng lẻ sang document tổng hợp

Giả sử có:

~~~javascript
{ orderNo: "SO-001", status: "paid", amount: NumberDecimal("100.00") }
{ orderNo: "SO-002", status: "paid", amount: NumberDecimal("250.00") }
{ orderNo: "SO-003", status: "pending", amount: NumberDecimal("80.00") }
~~~

Sau khi nhóm theo status:

~~~text
Document đầu vào
   SO-001 -> paid     amount 100
   SO-002 -> paid     amount 250
   SO-003 -> pending  amount  80
          |
          v
      $group theo status
          |
          +-- paid:    count=2, sum=350, avg=175
          |
          +-- pending: count=1, sum= 80, avg= 80
~~~

Không có lý do mặc định để tính tổng của **tất cả** trạng thái nếu người dùng chỉ cần số đơn đã thanh toán. Một **$match** đúng đặt trước $group vừa thể hiện chính xác nghiệp vụ vừa giảm số document phải tổng hợp.

## 2. Cấu trúc $group và cú pháp chung

### 2.1. Trường _id trong $group là khóa nhóm

~~~javascript
{
  $group: {
    _id: <grouping-expression>,
    outputField1: { $sum: <expression> },
    outputField2: { $avg: <expression> }
  }
}
~~~

Trong cú pháp trên:

- **_id: "$status"** tạo một nhóm cho mỗi giá trị status.
- **_id: { tenantId: "$tenantId", status: "$status" }** tạo nhóm theo cặp tenant–status.
- **_id: null** đưa toàn bộ document đi vào $group vào **một nhóm duy nhất**.
- Mỗi trường đầu ra khác _id chứa accumulator và biểu thức đầu vào.
- **$group không đảm bảo thứ tự các document nhóm đầu ra**. Muốn hiển thị theo thứ tự, thêm **$sort sau $group**.

Ví dụ nhóm theo hai chiều:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenant: "$tenantId",
        status: "$status"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { "_id.tenant": 1, "_id.status": 1 } }
]);
~~~

### 2.2. Các dấu $ mang ý nghĩa khác nhau

Đọc đúng ba ví dụ:

~~~javascript
{ $sum: 1 }          // Mỗi document đóng góp số 1.
{ $sum: "$amount" }  // Mỗi document đóng góp giá trị trường amount.
{ $push: "$status" } // Mỗi document đóng góp một giá trị status vào Array.
~~~

**Số 1** là literal. **"$amount"** là field path của document đầu vào. Bỏ dấu $ sẽ đổi ý nghĩa: **{ $sum: "amount" }** dùng một chuỗi literal không phải giá trị trường; với $sum trong $group, chuỗi là phi số và sẽ không đóng góp vào tổng.

### 2.3. Accumulator trong $group và expression trong stage khác

Các tên **$sum, $avg, $min, $max** cũng có dạng **aggregation expression** dùng trong một số stage như **$project** hoặc **$set**. Khi dùng trên **một document**, chúng xử lý biểu thức của document đó thay vì tổng hợp trên nhiều document như trong $group. Đặc biệt, cách chúng xử lý Array có thể khác theo ngữ cảnh.

Ngược lại, **$push** và **$addToSet** dùng để tích lũy các giá trị từ nhiều document trong những stage hỗ trợ accumulator như **$group** và **$setWindowFields**, không phải hàm chung dùng tùy ý trong $project.

Bài này lấy **$group** làm ngữ cảnh chính, sau đó giải thích các ngoại lệ đáng chú ý khi chuyển sang những stage khác.

## 3. Bộ dữ liệu thực hành có thể chạy lại

Ta mô phỏng hệ thống đơn hàng của hai tenant, có nhiều khách, trạng thái và mức tiền. Mục đích là làm rõ **$sum/$avg** cho số, **$min/$max** cho giá trị cực trị, và **$push/$addToSet** cho danh sách.

Database: **mongo_accumulators_lab**.

Collection: **lab_orders_agg**.

Nhãn của bộ dữ liệu: **accumulators-v1**.

### 3.1. Khởi tạo 12 đơn bằng mongosh

Chạy nguyên khối:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_accumulators_lab");
  const orders = lab.getCollection("lab_orders_agg");
  const tag = "accumulators-v1";

  // Chỉ dọn dữ liệu bài này. Không drop collection hoặc database.
  orders.deleteMany({ dataset: tag });

  // Mỗi hàng: id, tenant, customer, status, amount, units, coupon, tags.
  // undefined biểu thị document KHÔNG có trường coupon.
  const rows = [
    ["agg-o001", "t001", "c01", "paid",     "100.00", 2, null,       ["new", "web"]],
    ["agg-o002", "t001", "c01", "paid",     "250.00", 3, "SAVE10",   ["sale", "app"]],
    ["agg-o003", "t001", "c02", "pending",   "80.00", 1, undefined,  ["web"]],
    ["agg-o004", "t001", "c02", "paid",     "120.00", 2, null,       ["web"]],
    ["agg-o005", "t001", "c03", "refunded",  "60.00", 1, "SAVE10",   ["sale", "app"]],
    ["agg-o006", "t001", "c01", "paid",     "130.00", 2, "SAVE20",   ["web", "vip"]],
    ["agg-o007", "t001", "c03", "paid",      "90.00", 1, "SAVE10",   ["web", "sale"]],
    ["agg-o008", "t001", "c03", "pending",   "40.00", 1, "",         ["app"]],
    ["agg-o009", "t002", "c04", "paid",     "200.00", 4, null,       ["web"]],
    ["agg-o010", "t002", "c04", "paid",     "150.00", 3, "SAVE10",   ["app", "sale"]],
    ["agg-o011", "t002", "c05", "pending",   "75.00", 1, undefined,  ["web"]],
    ["agg-o012", "t002", "c05", "paid",      "50.00", 1, null,       ["web", "new"]]
  ];

  const documents = rows.map((r, i) => {
    const [id, tenantId, customerId, status,
           amount, units, coupon, tags] = r;

    const doc = {
      _id: id,
      dataset: tag,
      tenantId: tenantId,
      customerId: customerId,
      status: status,
      amount: NumberDecimal(amount),
      units: NumberInt(units),
      tags: tags,
      createdAt: new Date(Date.UTC(2026, 0, 1, 0, i + 1, 0))
    };

    if (coupon !== undefined) {
      doc.coupon = coupon;
    }
    return doc;
  });

  orders.insertMany(documents);

  // Phục vụ các ví dụ lọc tenant và duyệt theo thứ tự.
  orders.createIndex(
    { dataset: 1, tenantId: 1, createdAt: 1, _id: 1 },
    { name: "ix_acc_lab_tenant_time" }
  );

  orders.createIndex(
    { dataset: 1, tenantId: 1, status: 1 },
    { name: "ix_acc_lab_tenant_status" }
  );

  printjson({
    total: orders.countDocuments({ dataset: tag }),
    tenant001: orders.countDocuments({
      dataset: tag,
      tenantId: "t001"
    }),
    tenant002: orders.countDocuments({
      dataset: tag,
      tenantId: "t002"
    })
  });
})();
~~~

**Kết quả mong đợi:** tổng cộng **12 đơn**, tenant t001 có **8**, tenant t002 có **4**. Tất cả amount có kiểu BSON **Decimal128**, còn units là Int32.

Script dùng _id cố định và chỉ xóa theo nhãn dataset. Nếu bạn thay đổi dữ liệu trong một bài tập, chạy lại script này để trở về dữ liệu chuẩn. Đây không phải transaction nguyên tử giữa bước dọn và insert, nên chỉ dùng trên database thực hành.

### 3.2. Nhìn nhanh các nhóm trong dữ liệu

| Tenant | Trạng thái | Số đơn | Tổng amount |
| --- | --- | ---: | ---: |
| t001 | paid | 5 | 690.00 |
| t001 | pending | 2 | 120.00 |
| t001 | refunded | 1 | 60.00 |
| t002 | paid | 3 | 400.00 |
| t002 | pending | 1 | 75.00 |
| **Tổng** | | **12** | **1345.00** |

Các con số trong bảng có được bằng phép cộng từ bộ dữ liệu cố định, dùng để giải thích kết quả kỳ vọng. Trong hệ thống thật, cần xác định rõ **đơn nào được tính vào doanh thu**: refunded, cancelled hoặc pending có thể không được cộng vào doanh thu đã ghi nhận.

## 4. $sum: tính tổng và đếm document

### 4.1. Đếm bằng $sum: 1

Ở $group, mẫu đếm:

~~~javascript
const orders = db.getSiblingDB("mongo_accumulators_lab")
  .getCollection("lab_orders_agg");

orders.aggregate([
  { $match: { dataset: "accumulators-v1" } },
  {
    $group: {
      _id: "$status",
      numberOfOrders: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

**$sum: 1** cộng thêm một cho mỗi document trong nhóm. Nó **không** đếm giá trị khác null của một trường; tất cả document đã đi qua $match đều đóng góp một đơn vị.

Từ bộ dữ liệu:

| status | numberOfOrders |
| --- | ---: |
| paid | 8 |
| pending | 3 |
| refunded | 1 |

**$count** trong pipeline cũng giúp đếm tổng số document sau các bước lọc; **$count accumulator** có thể dùng trong các stage được hỗ trợ trên phiên bản tương ứng. Nhưng **$sum: 1** là mẫu phổ biến và dễ hiểu khi đã nhóm theo một khóa.

### 4.2. Cộng giá trị số của một field

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid"
    }
  },
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 },
      amountTotal: { $sum: "$amount" },
      unitsTotal: { $sum: "$units" }
    }
  }
]).toArray();
~~~

Kết quả logic:

~~~text
_id         = "t001"
count       = 5
amountTotal = NumberDecimal("690.00")
unitsTotal  = 10
~~~

Do amount được lưu bằng Decimal128, tổng amount tiếp tục bảo toàn kiểu số thập phân chính xác trong phạm vi số học của MongoDB. Đối với tiền, cần thống nhất **Decimal128 và đồng tiền/đơn vị**. Không cộng VND và USD chỉ vì đều có trường amount.

### 4.3. Tính tổng có điều kiện

Nếu muốn một pipeline tạo báo cáo tổng đơn và số đơn paid trong từng tenant:

~~~javascript
orders.aggregate([
  { $match: { dataset: "accumulators-v1" } },
  {
    $group: {
      _id: "$tenantId",
      allOrders: { $sum: 1 },
      paidOrders: {
        $sum: {
          $cond: [{ $eq: ["$status", "paid"] }, 1, 0]
        }
      },
      paidAmount: {
        $sum: {
          $cond: [
            { $eq: ["$status", "paid"] },
            "$amount",
            NumberDecimal("0.00")
          ]
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

Kết quả:

| Tenant | allOrders | paidOrders | paidAmount |
| --- | ---: | ---: | ---: |
| t001 | 8 | 5 | 690.00 |
| t002 | 4 | 3 | 400.00 |

**$cond** chọn giá trị đóng góp cho từng document, rồi $sum cộng các giá trị đó. Cách này thường hữu ích cho báo cáo gồm nhiều chỉ tiêu khác nhau. Nếu chỉ quan tâm paid, đặt **$match: {status:"paid"}** trước $group có thể giảm lượng dữ liệu cần xử lý.

### 4.4. Tổng của biểu thức tính toán

Giả sử cần tổng “số đơn vị nhân đơn giá”. Nếu mỗi document có unitPrice thay cho amount, có thể:

~~~javascript
{
  $group: {
    _id: "$tenantId",
    totalValue: {
      $sum: {
        $multiply: ["$units", "$unitPrice"]
      }
    }
  }
}
~~~

Đó là cú pháp biểu thức, không phải lệnh chạy trực tiếp trên dữ liệu lab vì bộ dữ liệu hiện tại không có unitPrice. Với dữ liệu lab, bạn có thể thử phép toán minh họa trên amount hoặc tạo một field unitPrice có nghĩa nghiệp vụ riêng. Khi nhân, cộng các giá trị tài chính, phải xét làm tròn, loại tiền và quy tắc tính thuế.

### 4.5. $sum và dữ liệu phi số

Trong **$group**, $sum **bỏ qua các giá trị không phải số**. Nếu mọi giá trị đầu vào của một nhóm đều không có số hợp lệ (null, thiếu field, String...), kết quả sum là **0**, không phải một phép cộng chuỗi hay báo lỗi chỉ vì gặp String.

Điều này là con dao hai lưỡi: pipeline vẫn chạy, nhưng có thể tạo tổng thấp hơn thực tế nếu một phần amount đang lưu dưới dạng String. Phải kiểm tra kiểu BSON của dữ liệu trước khi tin báo cáo tài chính.

## 5. $avg: giá trị trung bình và mẫu số thực sự

### 5.1. Cú pháp

~~~javascript
{
  $group: {
    _id: "$status",
    avgAmount: { $avg: "$amount" }
  }
}
~~~

**$avg** tính trung bình của các giá trị số được xét trong mỗi nhóm. Nó **bỏ qua** những giá trị không phải số, null hoặc field thiếu trong ngữ cảnh accumulator của $group.

### 5.2. Trung bình theo tenant và status

~~~javascript
orders.aggregate([
  { $match: { dataset: "accumulators-v1" } },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" },
      averageAmount: { $avg: "$amount" }
    }
  },
  { $sort: { "_id.tenantId": 1, "_id.status": 1 } }
]).toArray();
~~~

Kết quả logic:

| tenantId | status | orderCount | totalAmount | averageAmount |
| --- | --- | ---: | ---: | ---: |
| t001 | paid | 5 | 690.00 | 138.00 |
| t001 | pending | 2 | 120.00 | 60.00 |
| t001 | refunded | 1 | 60.00 | 60.00 |
| t002 | paid | 3 | 400.00 | Khoảng 133.33 |
| t002 | pending | 1 | 75.00 | 75.00 |

Với nhóm t002 paid, phép chia 400/3 có phần thập phân lặp; biểu diễn chính xác cuối cùng phụ thuộc kiểu số và quy tắc số học. Không nên kiểm tra bằng cách so sánh chuỗi biểu diễn trong response. Với báo cáo tiền, xác định chính sách **rounding** ở bước hiển thị hoặc lưu kết quả.

### 5.3. $avg không phải tổng chia cho số document nếu có dữ liệu bẩn

Giả sử nhóm có:

~~~javascript
{ group: "A", value: 10 }
{ group: "A", value: 20 }
{ group: "A", value: null }
{ group: "A" }
~~~

**$sum: "$value" = 30**; **$avg: "$value" = 15**, vì chỉ có **hai** giá trị số tham gia trung bình. Trong khi **$sum: 1 = 4**, vì có bốn document.

Nếu bạn lấy **sum / documentCount**, kết quả sẽ là **7,5**, khác với $avg. Đây là lý do phải phân biệt:

- **Số document trong nhóm**.
- **Số document thực sự có giá trị số hợp lệ**.
- **Số document mà nghiệp vụ cho phép tham gia trung bình**.

Nếu một trường bắt buộc nhưng bị thiếu ở dữ liệu cũ, tốt nhất nên kiểm kê/migrate trước, thay vì coi việc $avg bỏ qua giá trị thiếu là một phép sửa dữ liệu.

### 5.4. Khi không có giá trị số

Nếu toàn bộ giá trị mà $avg nhìn thấy đều phi số hoặc không tồn tại, **$avg trả null**. Đó là khác biệt quan trọng với **$sum**, vốn trả 0 trong tình huống không có giá trị số.

Vì thế, khi hiển thị báo cáo:

- **sum = 0** có thể là tổng số học bằng 0 hoặc không có dữ liệu số hợp lệ.
- **avg = null** có nghĩa không tính được trung bình theo dữ liệu số đầu vào.
- Không tự thay avg null thành 0 nếu nghiệp vụ cần phân biệt “chưa có dữ liệu” và “trung bình thực sự bằng 0”.

## 6. $min và $max: tìm cực trị theo BSON comparison

### 6.1. Cú pháp và ví dụ

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid"
    }
  },
  {
    $group: {
      _id: null,
      minAmount: { $min: "$amount" },
      maxAmount: { $max: "$amount" },
      oldestDate: { $min: "$createdAt" },
      newestDate: { $max: "$createdAt" }
    }
  }
]).toArray();
~~~

Kết quả của nhóm paid t001:

~~~text
minAmount  = 90.00
maxAmount  = 250.00
oldestDate = 2026-01-01T00:01:00.000Z
newestDate = 2026-01-01T00:07:00.000Z
~~~

**$min** lấy giá trị nhỏ nhất; **$max** lấy giá trị lớn nhất trong nhóm theo **BSON comparison order**, không phải lúc nào cũng là “giá trị số lớn nhất” nếu dữ liệu trộn nhiều kiểu.

### 6.2. Không nhầm giá trị cực trị với document tương ứng

Khi viết:

~~~javascript
{ $group: { _id: "$tenantId", maxAmount: { $max: "$amount" } } }
~~~

bạn nhận **giá trị maxAmount**, không mặc nhiên nhận đầy đủ document chứa giá trị ấy. Nếu cần lấy “đơn có amount lớn nhất” cùng orderNo, customerId và createdAt, có các hướng:

- **$sort theo amount giảm dần**, sau đó **$group** với **$first** để chọn document đầu mỗi nhóm, có khóa phụ để phá hòa.
- Dùng những accumulator phù hợp như **$top/$topN** trên phiên bản hỗ trợ.
- Tách bài toán thành bước chọn cực trị và truy vấn tương ứng, kiểm soát thay đổi dữ liệu giữa các bước.

Ví dụ lấy orderNo của đơn t001 paid có amount lớn nhất:

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid"
    }
  },
  { $sort: { amount: -1, _id: 1 } },
  {
    $group: {
      _id: "$tenantId",
      maxOrder: { $first: "$$ROOT" }
    }
  },
  {
    $project: {
      _id: 1,
      maxOrderId: "$maxOrder._id",
      amount: "$maxOrder.amount",
      customerId: "$maxOrder.customerId"
    }
  }
]).toArray();
~~~

Kết quả logic: **agg-o002** có amount 250.00. Ở đây $sort theo amount và _id tạo thứ tự chọn document ổn định hơn khi có các giá trị bằng nhau. **$first** dùng để minh họa cách lấy document đi cùng cực trị; chủ đề chính vẫn là ý nghĩa của $max.

### 6.3. Null, missing và kiểu hỗn hợp

Trong **$group**, nếu một nhóm có cả giá trị null/missing và giá trị khác null, **$min/$max bỏ qua null/missing** khi xét các giá trị còn lại. Nếu tất cả giá trị của nhóm đều null/missing, chúng trả **null**.

Tuy nhiên, nếu field có cả Number, String, Date hoặc Array, **$min/$max so sánh theo thứ tự loại BSON**, không tự ép mọi thứ thành Number. Ví dụ có một amount số 100 và một amount String "200", kết quả max có thể thuộc kiểu String vì thứ tự loại BSON, dù điều đó không phải “đơn lớn nhất” theo số học.

Quy tắc thực hành: với báo cáo min/max số tiền, hãy đảm bảo schema là **Decimal128** (hoặc kiểu số được chuẩn hóa). Với thời gian, dùng BSON Date, không trộn Date với chuỗi ngày.

### 6.4. $min/$max khác sort theo business ranking

**$max: "$status"** sẽ lấy status lớn nhất theo phép so sánh BSON/chuỗi, **không** có nghĩa trạng thái nghiệp vụ ưu tiên cao nhất. Nếu cần thứ tự pending → paid → shipped hoặc severity low → medium → high, hãy ánh xạ sang một **rank số** có định nghĩa nghiệp vụ, rồi tổng hợp trên rank đó.

## 7. $push: giữ tất cả các giá trị trong nhóm

### 7.1. Cú pháp

~~~javascript
{
  $group: {
    _id: "$customerId",
    orderIds: { $push: "$_id" }
  }
}
~~~

**$push** xây một Array gồm các giá trị biểu thức ở những document được đưa vào nhóm. Nó **không tự loại các giá trị trùng nhau**.

### 7.2. Ví dụ lịch sử đơn của từng khách

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid"
    }
  },
  { $sort: { createdAt: 1, _id: 1 } },
  {
    $group: {
      _id: "$customerId",
      paidOrderIds: { $push: "$_id" },
      paidAmounts: { $push: "$amount" },
      paidCount: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

Kết quả theo nhóm:

| customerId | paidOrderIds theo createdAt tăng | paidCount |
| --- | --- | ---: |
| c01 | [agg-o001, agg-o002, agg-o006] | 3 |
| c02 | [agg-o004] | 1 |
| c03 | [agg-o007] | 1 |

Ở ví dụ này, **$sort nằm trước $group**, có khóa phụ _id giúp xác định thứ tự toàn bộ đầu vào trong cùng một mốc createdAt. Thứ tự **phần tử trong $push** phụ thuộc thứ tự các document đi vào $group.

**Không nhầm hai loại thứ tự:**

- Thứ tự các **giá trị được $push vào mảng** có thể được xác định bằng $sort trước $group.
- Thứ tự các **document nhóm đầu ra** vẫn không được $group đảm bảo; cần **$sort sau $group** để sắp xếp các nhóm.

### 7.3. $push giữ duplicate

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid"
    }
  },
  { $sort: { createdAt: 1, _id: 1 } },
  {
    $group: {
      _id: null,
      customerSequence: { $push: "$customerId" }
    }
  }
]).toArray();
~~~

Kết quả:

~~~text
["c01", "c01", "c02", "c01", "c03"]
~~~

Khách **c01** xuất hiện ba lần vì có ba đơn paid. Đây là hành vi mong muốn khi cần danh sách gốc để audit hoặc phân tích theo từng bản ghi; không phải lỗi duplicate của $push.

### 7.4. $push có thể tạo mảng các object

Không bắt buộc chỉ push một field. Có thể push một object:

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      customerId: "c01"
    }
  },
  { $sort: { createdAt: 1, _id: 1 } },
  {
    $group: {
      _id: "$customerId",
      orders: {
        $push: {
          orderId: "$_id",
          amount: "$amount",
          status: "$status",
          date: "$createdAt"
        }
      }
    }
  }
]).toArray();
~~~

Lợi ích là tạo danh sách gọn theo cấu trúc mong muốn. Rủi ro là một nhóm có hàng triệu document có thể tạo một **Array đầu ra cực lớn** và chạm giới hạn BSON hoặc giới hạn tài nguyên. Không sử dụng $push như cách phân trang mọi giao dịch của một khách có lịch sử vô hạn.

## 8. $addToSet: lấy các giá trị phân biệt

### 8.1. So sánh với $push

**$addToSet** tích lũy một giá trị cho mỗi phần tử phân biệt trong nhóm. Nó không đảm bảo thứ tự các phần tử kết quả.

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid"
    }
  },
  { $sort: { createdAt: 1, _id: 1 } },
  {
    $group: {
      _id: null,
      allCustomers: { $push: "$customerId" },
      distinctCustomers: { $addToSet: "$customerId" }
    }
  }
]).toArray();
~~~

Kết quả về ý nghĩa:

~~~text
allCustomers:
  ["c01", "c01", "c02", "c01", "c03"]

distinctCustomers:
  chứa chính xác các giá trị "c01", "c02", "c03"
  nhưng THỨ TỰ KHÔNG ĐƯỢC BẢO ĐẢM
~~~

Nếu cần hiển thị danh sách mã khách theo thứ tự chữ cái, có thể dùng **$sortArray** trên kết quả của $addToSet (ở phiên bản MongoDB hỗ trợ) hoặc xử lý sắp xếp bằng một cách phù hợp sau aggregation. Không giả định $sort trước $group sẽ làm **$addToSet** có thứ tự ổn định.

### 8.2. Số phần tử phân biệt

Một ví dụ thường dùng là **$size** của kết quả $addToSet:

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid"
    }
  },
  {
    $group: {
      _id: "$tenantId",
      customerIds: { $addToSet: "$customerId" },
      paidOrders: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 1,
      paidOrders: 1,
      distinctCustomerCount: { $size: "$customerIds" },
      customerIds: 1
    }
  }
]).toArray();
~~~

Kết quả logic:

~~~text
tenantId              = "t001"
paidOrders            = 5
distinctCustomerCount = 3
customerIds           = tập {"c01", "c02", "c03"}, thứ tự tùy ý
~~~

**Lưu ý hiệu năng:** cách lấy số phần tử phân biệt bằng $addToSet phải xây tập giá trị trong nhóm. Nếu cardinality rất lớn, lượng bộ nhớ và kích thước mảng đầu ra có thể tăng mạnh; khi mục tiêu chỉ là đếm unique, cân nhắc phương án nhóm hai cấp, index, dữ liệu tổng hợp hoặc giải pháp khác theo workload.

### 8.3. $addToSet có thể thu thập Array như một phần tử duy nhất

Trong lab, trường **tags** của mỗi order là một Array. Nếu:

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001"
    }
  },
  {
    $group: {
      _id: "$tenantId",
      tagArrays: { $addToSet: "$tags" }
    }
  }
]).toArray();
~~~

thì mỗi Array tags của một order được coi là **một giá trị toàn mảng** trong ngữ cảnh accumulator. Kết quả là **Array chứa các Array**, không tự làm phẳng thành danh sách tag duy nhất.

Ví dụ về hình dạng:

~~~text
tagArrays = [
  ["new", "web"],
  ["sale", "app"],
  ["web"],
  ["web", "vip"],
  ...
]
~~~

Không nên suy luận rằng **$addToSet: "$tags"** tự động tương đương lấy unique các phần tử tag.

### 8.4. Muốn lấy từng tag phân biệt: $unwind trước khi nhóm

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001"
    }
  },
  { $unwind: "$tags" },
  {
    $group: {
      _id: "$tenantId",
      distinctTags: { $addToSet: "$tags" },
      tagOccurrences: { $sum: 1 }
    }
  }
]).toArray();
~~~

Kết quả gồm năm tag phân biệt:

~~~text
{"new", "web", "sale", "app", "vip"}
~~~

Ở dữ liệu t001, tập đúng có **5** tag phân biệt: new, web, sale, app, vip. Trường **tagOccurrences** đếm số **phần tử tag** sau $unwind, không phải số order.

Đếm theo dữ liệu lab:

| Order | Số phần tử tags |
| --- | ---: |
| agg-o001 | 2 |
| agg-o002 | 2 |
| agg-o003 | 1 |
| agg-o004 | 1 |
| agg-o005 | 2 |
| agg-o006 | 2 |
| agg-o007 | 2 |
| agg-o008 | 1 |
| **Tổng** | **13** |

Vì vậy **tagOccurrences = 13**, còn **số order t001 = 8**. Nếu đặt **{ $sum: "$amount" }** sau $unwind mà không kiểm soát, mỗi order có hai tag sẽ bị cộng tiền **hai lần**. Đây là một lỗi tổng hợp thường gặp.

### 8.5. Giá trị document và thứ tự field

Với $addToSet, hai embedded documents được coi là trùng khi có **cùng các trường, giá trị và thứ tự trường theo tiêu chí so sánh document**. Chẳng hạn:

~~~javascript
{ sku: "A", qty: 1 }
{ qty: 1, sku: "A" }
~~~

không nên mặc định sẽ bị $addToSet coi là một object duy nhất chỉ vì ứng dụng diễn giải hai cặp key–value tương đương nhau. Nếu cần unique theo một khóa nghiệp vụ, nên dùng một scalar ổn định như **sku**, hoặc chuẩn hóa object trước khi đưa vào tập.

Đối với String, so sánh còn có thể chịu ảnh hưởng bởi collation của thao tác. Muốn unique theo nghĩa case-insensitive hoặc chuẩn hóa mã nghiệp vụ, cần xác định rõ quy tắc so sánh thay vì trông chờ $addToSet tự xử lý mọi khác biệt.

## 9. Tạo báo cáo kết hợp cả sáu accumulator

Ví dụ báo cáo **theo tenant và status**, gồm:

- Số đơn.
- Tổng giá trị.
- Trung bình giá trị.
- Giá trị nhỏ nhất và lớn nhất.
- Danh sách orderId theo thời gian.
- Tập customerId phân biệt.

~~~javascript
orders.aggregate([
  { $match: { dataset: "accumulators-v1" } },
  { $sort: { createdAt: 1, _id: 1 } },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      orderCount: { $sum: 1 },
      amountTotal: { $sum: "$amount" },
      amountAverage: { $avg: "$amount" },
      amountMinimum: { $min: "$amount" },
      amountMaximum: { $max: "$amount" },
      orderIds: { $push: "$_id" },
      customerIds: { $addToSet: "$customerId" }
    }
  },
  {
    $project: {
      _id: 0,
      tenantId: "$_id.tenantId",
      status: "$_id.status",
      orderCount: 1,
      amountTotal: 1,
      amountAverage: 1,
      amountMinimum: 1,
      amountMaximum: 1,
      orderIds: 1,
      customerIds: 1,
      distinctCustomerCount: { $size: "$customerIds" }
    }
  },
  { $sort: { tenantId: 1, status: 1 } }
]).toArray();
~~~

Với tenant **t001** và status **paid**, kết quả mang ý nghĩa:

~~~text
tenantId             = "t001"
status               = "paid"
orderCount           = 5
amountTotal          = 690.00
amountAverage        = 138.00
amountMinimum        = 90.00
amountMaximum        = 250.00
orderIds             = ["agg-o001", "agg-o002", "agg-o004",
                        "agg-o006", "agg-o007"]
customerIds          = tập {"c01", "c02", "c03"}
distinctCustomerCount= 3
~~~

**orderIds** tuân theo thứ tự đầu vào đã sort; **customerIds** không có thứ tự bảo đảm. **$sort cuối cùng** chỉ sắp xếp các nhóm, không sửa thứ tự các phần tử nằm trong hai Array accumulator.

Khi áp dụng vào production, chỉ thêm **$push orderIds** nếu số order trong mỗi nhóm có giới hạn hữu ích. Nếu chỉ cần tổng, trung bình và số lượng, bỏ các Array accumulator để tránh chi phí tích lũy không cần thiết.

## 10. Null, missing, String và Array: accumulator không xử lý giống nhau

Một bộ dữ liệu sạch thường không bộc lộ hết hành vi của accumulator. Ta tạo collection thứ hai để minh họa **giá trị phi số** và **kiểu hỗn hợp**. Đây là ví dụ minh họa, không phải khuyến nghị lưu dữ liệu nghiệp vụ như thế.

### 10.1. Seed dữ liệu bất thường

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_accumulators_lab");
  const c = lab.getCollection("lab_measurement_edges");
  const tag = "accumulators-edges-v1";

  c.deleteMany({ dataset: tag });

  c.insertMany([
    { _id: "m01", dataset: tag, group: "A", value: NumberInt(10) },
    { _id: "m02", dataset: tag, group: "A", value: NumberInt(20) },
    { _id: "m03", dataset: tag, group: "A", value: null },
    { _id: "m04", dataset: tag, group: "A" },
    { _id: "m05", dataset: tag, group: "B", value: null },
    { _id: "m06", dataset: tag, group: "B" },
    { _id: "m07", dataset: tag, group: "C", value: "bad" },
    { _id: "m08", dataset: tag, group: "C", value: NumberInt(5) },
    { _id: "m09", dataset: tag, group: "D", value: [4, 6] },
    { _id: "m10", dataset: tag, group: "D", value: NumberInt(5) }
  ]);

  print(c.countDocuments({ dataset: tag }));
})();
~~~

**Kết quả mong đợi:** 10 document. Các giá trị bất thường được cố ý tạo để so sánh accumulator.

### 10.2. $sum và $avg bỏ qua phi số trong $group

~~~javascript
db.getSiblingDB("mongo_accumulators_lab")
  .getCollection("lab_measurement_edges")
  .aggregate([
    {
      $match: {
        dataset: "accumulators-edges-v1",
        group: { $in: ["A", "B", "C", "D"] }
      }
    },
    {
      $group: {
        _id: "$group",
        documentCount: { $sum: 1 },
        total: { $sum: "$value" },
        average: { $avg: "$value" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Kết quả mong đợi:

| Group | documentCount | total | average | Diễn giải |
| --- | ---: | ---: | ---: | --- |
| A | 4 | 30 | 15 | Chỉ hai giá trị 10 và 20 tham gia toán số |
| B | 2 | 0 | null | Null và missing không tạo đầu vào số |
| C | 2 | 5 | 5 | String "bad" bị bỏ qua ở sum/avg |
| D | 2 | 5 | 5 | Array [4,6] không được duyệt từng phần tử trong $group |

Đặc biệt group **D** cho thấy sự khác biệt quan trọng: trong ngữ cảnh **$group**, khi expression của $sum/$avg trỏ đến **một Array**, Array đó được coi là **giá trị phi số**, không được tự tách thành phần tử 4 và 6 rồi cộng.

Không áp quy tắc này một cách máy móc cho các stage như $project: ở một số ngữ cảnh **$sum expression** và **$avg expression** có thể duyệt phần tử của một Array khi dùng cú pháp một operand. Phải xem **stage và dạng operand**.

### 10.3. $min/$max dùng BSON comparison order

~~~javascript
db.getSiblingDB("mongo_accumulators_lab")
  .getCollection("lab_measurement_edges")
  .aggregate([
    { $match: { dataset: "accumulators-edges-v1" } },
    {
      $group: {
        _id: "$group",
        minimum: { $min: "$value" },
        maximum: { $max: "$value" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Với group **A**, min = 10 và max = 20; với group **B**, cả min/max là null. Group **C** có Number 5 và String "bad", còn group **D** có Number 5 và Array [4,6]. Vì MongoDB so sánh theo loại BSON trước khi so sánh giá trị trong một số trường hợp, kết quả cực trị ở C/D không có nghĩa là một phép xếp hạng **theo số học**.

Muốn min/max là cực trị số, có thể kiểm tra/chuẩn hóa dữ liệu trước khi group:

~~~javascript
db.getSiblingDB("mongo_accumulators_lab")
  .getCollection("lab_measurement_edges")
  .aggregate([
    { $match: { dataset: "accumulators-edges-v1" } },
    {
      $match: {
        value: { $type: ["int", "long", "double", "decimal"] }
      }
    },
    {
      $group: {
        _id: "$group",
        minNumeric: { $min: "$value" },
        maxNumeric: { $max: "$value" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Trong lab, bộ lọc số loại null, String và Array chứa các Number? **Chú ý:** $type dạng query predicate có thể khớp khi Array chứa Number. Để bảo đảm **toàn field là scalar numeric** và không chấp nhận Array, dùng aggregation expression:

~~~javascript
db.getSiblingDB("mongo_accumulators_lab")
  .getCollection("lab_measurement_edges")
  .aggregate([
    { $match: { dataset: "accumulators-edges-v1" } },
    {
      $match: {
        $expr: {
          $in: [
            { $type: "$value" },
            ["int", "long", "double", "decimal"]
          ]
        }
      }
    },
    {
      $group: {
        _id: "$group",
        minNumeric: { $min: "$value" },
        maxNumeric: { $max: "$value" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Với kiểu hỗn hợp trong production, nên đặt **schema validation** và migration có chủ đích, không chỉ dựa vào các accumulator có thể bỏ qua dữ liệu sai.

### 10.4. Chuẩn hóa coupon null/missing bằng $ifNull

Trong bộ dữ liệu order, một số document có coupon bằng null, một số **không có field**, và một document có coupon là chuỗi rỗng.

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001"
    }
  },
  {
    $group: {
      _id: "$tenantId",
      coupons: {
        $addToSet: {
          $ifNull: ["$coupon", "(none)"]
        }
      },
      couponsAll: {
        $push: {
          $ifNull: ["$coupon", "(none)"]
        }
      }
    }
  }
]).toArray();
~~~

**$ifNull** trong ví dụ đưa null/missing về chuỗi "(none)" để hành vi có chủ đích. Kết quả coupons gồm các giá trị phân biệt:

~~~text
{"(none)", "SAVE10", "SAVE20", ""}
~~~

Thứ tự không được đảm bảo. **Chuỗi rỗng** vẫn là một giá trị khác "(none)" vì $ifNull chỉ xử lý các trạng thái null/missing/undefined được coi là null theo semantics của biểu thức. Nếu chuỗi rỗng cũng là “không có coupon” trong nghiệp vụ, cần thêm quy tắc chuyển đổi riêng.

## 11. $unwind và rủi ro cộng trùng dữ liệu

Các báo cáo trên Array thường có một lỗi âm thầm: **$unwind biến một document thành nhiều document**, làm các accumulator như $sum: 1 hoặc $sum: "$amount" tính theo số dòng sau unwind chứ không phải số order gốc.

### 11.1. Ví dụ sai ngữ nghĩa nếu muốn doanh thu order

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001"
    }
  },
  { $unwind: "$tags" },
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 },
      amountTotal: { $sum: "$amount" }
    }
  }
]).toArray();
~~~

Ở đây **count = 13**, không phải 8; amountTotal cũng bị cộng lặp theo số tag của từng order. Không được gọi count này là “số đơn” hay amountTotal là “tổng tiền đơn” nếu chưa chủ động thiết kế phép tổng hợp theo dữ liệu đã nhân bản.

### 11.2. Tách hai phép đo cần thiết

Một thiết kế rõ ràng hơn là chạy hai nhánh trong **$facet**, một nhánh tổng hợp theo order gốc, một nhánh unwind tags:

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001"
    }
  },
  {
    $facet: {
      orderMetrics: [
        {
          $group: {
            _id: null,
            orderCount: { $sum: 1 },
            totalAmount: { $sum: "$amount" }
          }
        }
      ],
      tagMetrics: [
        { $unwind: "$tags" },
        {
          $group: {
            _id: null,
            tagOccurrences: { $sum: 1 },
            distinctTags: { $addToSet: "$tags" }
          }
        }
      ]
    }
  }
]).toArray();
~~~

Kết quả logic:

~~~text
orderMetrics: orderCount=8, totalAmount=870.00
tagMetrics:   tagOccurrences=13, distinctTags có 5 giá trị
~~~

**$facet** chỉ là một cách tổ chức pipeline; nó cũng sử dụng tài nguyên và có các giới hạn bộ nhớ/kích thước kết quả riêng. Chọn cách tính và mô hình dữ liệu phù hợp khi tập dữ liệu rất lớn.

## 12. Một số lỗi ngữ nghĩa cần tránh

### 12.1. Group theo khóa sai

~~~javascript
{ $group: { _id: "$status", total: { $sum: "$amount" } } }
~~~

gộp các tenant lại với nhau. Trong ứng dụng multi-tenant, nếu muốn kết quả từng tenant cần **$match tenant** đúng quyền hoặc **_id gồm tenantId**. Lỗi này không chỉ gây thống kê sai mà có thể gây rò rỉ dữ liệu thống kê giữa các tenant.

### 12.2. Không lọc status khi gọi là doanh thu

Nếu tổng hợp tất cả đơn bao gồm pending/refunded, số tiền là **tổng amount các record**, không nhất thiết là doanh thu được ghi nhận. Hãy định nghĩa metric rõ: paid amount, net revenue sau hoàn, gross order value, number of orders... Các accumulator không biết định nghĩa kế toán của doanh nghiệp.

### 12.3. $addToSet không sắp xếp

~~~javascript
{ $group: { _id: null, ids: { $addToSet: "$customerId" } } }
~~~

trả một Array có các giá trị phân biệt nhưng thứ tự tùy ý. Nếu ứng dụng sử dụng Array đó để tạo khóa cache, so sánh snapshot hay hiển thị danh sách, cần chuẩn hóa thứ tự ở bước sau.

### 12.4. $push không giới hạn độ dài

~~~javascript
{ $group: { _id: "$tenantId", allOrders: { $push: "$$ROOT" } } }
~~~

có nguy cơ tạo một document kết quả chứa hàng triệu order, không thực tế và có thể vượt giới hạn. Cần thiết kế phân trang danh sách chi tiết riêng; dùng accumulator để tính những metric nhỏ gọn.

### 12.5. Không giả định thứ tự đầu ra của $group

MongoDB không bảo đảm thứ tự các nhóm sau $group. Dù có index và dù các document đầu vào theo thứ tự tăng, muốn hiển thị thứ tự nhóm vẫn phải dùng **$sort sau $group**.

## 13. Hiệu năng: $group, memory và thứ tự pipeline

### 13.1. $group là một stage tổng hợp có thể tiêu tốn bộ nhớ

Để hoàn thành nhiều loại $group, MongoDB cần giữ trạng thái của các nhóm (khóa nhóm, sum, avg, set giá trị, mảng tích lũy...). Trong pipeline có nhiều nhóm hoặc nhiều giá trị $push/$addToSet, lượng bộ nhớ có thể tăng nhanh.

MongoDB có cơ chế quản lý bộ nhớ và khả năng **spill ra đĩa** cho một số stage theo phiên bản/cấu hình (liên quan ngưỡng bộ nhớ thường được nhắc đến là **100 MB** cho các stage được hỗ trợ). **allowDiskUse** có thể cho phép các stage hỗ trợ dùng đĩa tạm nếu vượt ngưỡng. Ví dụ:

~~~javascript
orders.aggregate(
  [
    { $match: { dataset: "accumulators-v1" } },
    {
      $group: {
        _id: "$tenantId",
        orderCount: { $sum: 1 },
        totalAmount: { $sum: "$amount" }
      }
    }
  ],
  { allowDiskUse: true }
).toArray();
~~~

**allowDiskUse không vô hiệu hóa giới hạn 16 MiB của một BSON document kết quả** và không bảo đảm mọi phép tích lũy Array đều xử lý được khi dữ liệu vô hạn. Đặc biệt, $push một danh sách hàng triệu object có thể vượt giới hạn kích thước đầu ra trước khi vấn đề được giải quyết bằng đĩa tạm.

### 13.2. Đưa $match đủ chọn lọc lên trước

Không nên đưa toàn bộ collection qua nhiều stage nặng trước khi lọc theo tenant/time range.

Tốt hơn:

~~~javascript
orders.aggregate([
  {
    $match: {
      dataset: "accumulators-v1",
      tenantId: "t001",
      status: "paid",
      createdAt: {
        $gte: ISODate("2026-01-01T00:00:00.000Z"),
        $lt: ISODate("2026-02-01T00:00:00.000Z")
      }
    }
  },
  {
    $group: {
      _id: "$customerId",
      count: { $sum: 1 },
      total: { $sum: "$amount" }
    }
  }
]).toArray();
~~~

Một index phù hợp với filter (và khi cần là sort) có thể giảm lượng document phải kiểm tra. Tuy nhiên **index không thay thế toàn bộ chi phí group**: MongoDB vẫn cần tổng hợp những document khớp theo khóa nhóm.

### 13.3. Chỉ sort trước $group khi thật sự cần

**$sum, $avg, $min, $max, $addToSet** không cần document đầu vào được sắp thứ tự để tính giá trị theo ngữ nghĩa của chúng. **$push** cần quan tâm thứ tự nếu ứng dụng dùng thứ tự Array kết quả.

Do đó:

- Nếu chỉ tính tổng, trung bình, cực trị hoặc tập giá trị không có thứ tự, bỏ **$sort trước $group** nếu nó không phục vụ mục đích khác.
- Nếu cần **$push** theo createdAt, thêm **$sort trước $group** có khóa phụ phù hợp.
- Nếu cần sắp xếp các **nhóm đầu ra**, thêm **$sort sau $group**.

Sort có thể trở thành blocking stage và dùng nhiều tài nguyên khi tập kết quả lớn. Chỉ dùng khi yêu cầu kết quả thật sự cần.

### 13.4. Đọc explain để xem pipeline thực thi thế nào

~~~javascript
db.getSiblingDB("mongo_accumulators_lab")
  .getCollection("lab_orders_agg")
  .explain("executionStats")
  .aggregate([
    {
      $match: {
        dataset: "accumulators-v1",
        tenantId: "t001"
      }
    },
    {
      $group: {
        _id: "$status",
        count: { $sum: 1 },
        amount: { $sum: "$amount" }
      }
    }
  ]);
~~~

Trong explain, tìm **IXSCAN/COLLSCAN**, số key/document được xét, sự xuất hiện của SORT và các thông tin liên quan tới group. Cấu trúc explain khác nhau theo phiên bản MongoDB và query engine.

Với lab 12 document, COLLSCAN có thể rẻ hơn IXSCAN; không dùng quan sát đó để kết luận index sẽ vô ích trên collection production lớn.

### 13.5. Tránh lấy tất cả dữ liệu từ database rồi mới tính

Một pipeline tính tổng trong MongoDB thường giúp giảm lượng dữ liệu phải gửi qua mạng so với phương án kéo hàng triệu document về API rồi lặp cộng ở bộ nhớ ứng dụng. Nhưng không nên suy luận rằng tất cả phép tổng hợp đều nhẹ: nếu nhóm có quá nhiều khóa hoặc chứa Array lớn, aggregator vẫn có thể tốn CPU/bộ nhớ/đĩa tạm.

Với dashboard cập nhật liên tục trên tập dữ liệu rất lớn, có thể cần **incremental aggregation**, bảng tổng hợp riêng hoặc materialized read model, cùng chiến lược đồng bộ và xử lý dữ liệu thay đổi.

## 14. $sum/$avg/$min/$max ngoài $group: phân biệt operand Array

Ví dụ giả định một document:

~~~javascript
{
  _id: "s001",
  values: [4, 6, 10],
  tax: 2
}
~~~

Trong một số stage như **$project**, có thể dùng các biểu thức:

~~~javascript
db.someCollection.aggregate([
  {
    $project: {
      summedValues: { $sum: "$values" },
      averagedValues: { $avg: "$values" },
      totalWithTax: { $sum: ["$tax", 10] }
    }
  }
]);
~~~

Với **một operand** là Array, $sum/$avg ở ngữ cảnh biểu thức có thể duyệt các phần tử số. Khi dùng **danh sách nhiều operand**, quy tắc duyệt Array khác; Array có thể được coi là operand phi số. Trong **$group**, khi expression trực tiếp trỏ tới Array, $sum/$avg xem Array là phi số.

Với **$min/$max**, cách xử lý Array cũng phụ thuộc stage và dạng operand; đừng áp một ví dụ ở $project thành quy tắc chung cho $group. Khi cần tính toán phần tử bên trong một Array, cách rõ ràng là **$unwind** hoặc dùng biểu thức Array phù hợp, rồi kiểm soát lại số lần document đóng góp.

Tóm lại, luôn đọc **đầy đủ ngữ cảnh stage + cú pháp accumulator/expression**, thay vì chỉ nhìn tên toán tử.

## 15. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| $sum bằng 0 dù thấy giá trị "100" | Dữ liệu là String, không phải Number | Thống kê BSON types, chuyển đổi có kiểm soát |
| $avg khác tổng chia số document | $avg bỏ qua null/missing/phi số | Phân biệt documentCount và numericCount |
| $avg là null | Không có giá trị số hợp lệ trong nhóm | Hiển thị trạng thái thiếu dữ liệu thay vì tự coi là 0 |
| $max trả String thay vì giá trị số | Field lẫn BSON types; BSON comparison order | Chuẩn hóa schema trước khi tổng hợp |
| $push có phần tử trùng | $push giữ các giá trị xuất hiện | Dùng $addToSet nếu cần tập giá trị phân biệt |
| $addToSet trả thứ tự khác giữa các lần chạy | Kết quả set không có thứ tự đảm bảo | Sắp xếp Array sau khi tạo set nếu cần |
| $addToSet: "$tags" trả Array của Array | tags là Array, được thêm nguyên mảng như một phần tử | $unwind tags trước nếu muốn unique từng tag |
| Tổng tiền bị tăng sau $unwind | Một order đóng góp tiền lặp nhiều lần | Tổng hợp tiền trước unwind hoặc tách nhánh $facet |
| $group ra một dòng duy nhất | _id: null hoặc expression nhóm có cùng giá trị | Kiểm tra grouping key |
| Group gộp dữ liệu các tenant | Thiếu tenant trong $match/_id | Bổ sung ràng buộc tenant có kiểm soát quyền |
| $push Array quá lớn | Một nhóm có quá nhiều document | Không dùng group thay phân trang; thiết kế output nhỏ |
| $group dùng nhiều bộ nhớ | Cardinality nhóm hoặc set/array accumulator lớn | $match sớm, giới hạn dữ liệu, xem allowDiskUse và mô hình |
| Nhóm đầu ra không theo thứ tự mong muốn | $group không bảo đảm thứ tự output | $sort sau $group |
| Muốn dùng $push như hàm của $project | $push là accumulator trong stage hỗ trợ | Chọn $group/$setWindowFields hoặc Array expression phù hợp |
| Kết quả nhóm không có khi filter rỗng | Không document đầu vào nên $group không tạo nhóm | Xử lý trường hợp không có kết quả ở ứng dụng hoặc pipeline |

## 16. Bài tập thực hành

### Bài 1 — Đếm đơn theo trạng thái

Viết pipeline chỉ dùng **$match**, **$group** và **$sort** để đếm paid/pending/refunded trên tất cả tenant. Dự đoán ba kết quả **8, 3, 1** và giải thích vì sao $sum: 1 đếm document chứ không cộng amount.

### Bài 2 — Tính tổng, trung bình, min và max

Với đơn paid của t001, dùng một $group để tính bốn metric: totalAmount, averageAmount, minAmount, maxAmount. Dự đoán kết quả **690.00**, **138.00**, **90.00** và **250.00**. Tại sao không nên thay tất cả NumberDecimal bằng String?

### Bài 3 — Hai cách tính paidAmount

So sánh:

1. $match trước chỉ lấy status paid, rồi $sum: "$amount".
2. $group trên mọi status và dùng $sum kết hợp $cond để chỉ cộng paid.

Hai cách khác nhau thế nào khi báo cáo còn cần cả số đơn pending/refunded?

### Bài 4 — Trùng lặp và thứ tự

Với t001 paid, dùng **$push** và **$addToSet** trên customerId. Giải thích vì sao $push chứa ba lần c01, còn $addToSet chỉ một lần c01. Dùng $sort trước group để kiểm soát thứ tự $push và nêu vì sao không được dự đoán thứ tự $addToSet.

### Bài 5 — Danh sách object theo thời gian

Tạo mảng các object {orderId, amount, createdAt} theo từng customer của t001 bằng $push. Đặt $sort đủ ổn định trước group. Vì sao không nên push nguyên $$ROOT của hàng triệu order chỉ để hiển thị trang lịch sử?

### Bài 6 — Tags và $unwind

Tìm các tag phân biệt của t001:

1. Thử $addToSet: "$tags" mà không unwind.
2. Thử $unwind: "$tags" rồi $addToSet: "$tags".

Giải thích vì sao kết quả đầu tiên là Array của Array, kết quả thứ hai có **5 tag** phân biệt và tổng số lần xuất hiện của tag là **13**.

### Bài 7 — Tránh nhân bản doanh thu

Viết pipeline cố tình dùng $unwind tags trước khi $sum amount. So sánh kết quả với tổng **870.00** của t001 tính từ order gốc. Sửa bằng $facet hoặc bằng hai pipeline độc lập, giải thích vì sao hai loại metric phải được tính trên các mức độ hạt (granularity) khác nhau.

### Bài 8 — Null và sai kiểu

Chạy seed lab_measurement_edges. Dự đoán:

- Group A: sum = 30, avg = 15.
- Group B: sum = 0, avg = null.
- Group C: sum = 5, avg = 5.
- Group D: sum = 5, avg = 5.

Giải thích vì sao $sum/$avg trong $group không cộng các số nằm trong Array [4,6] của group D. Thêm một bộ lọc scalar numeric trước group để loại dữ liệu sai kiểu.

### Bài 9 — Extreme value và toàn bộ document

Tìm max amount trong t001 paid. Sau đó viết pipeline lấy **_id và customerId của document** có amount cao nhất, có tie-breaker theo _id. Vì sao $max: "$amount" một mình không trả về document?

### Bài 10 — Thiết kế metric đúng nghiệp vụ

Sản phẩm báo cáo “doanh thu thuần” của tháng. Dữ liệu có paid, refunded, pending; một số đơn khác loại tiền. Hãy mô tả những quy tắc cần xác định **trước** khi dùng $sum. Ví dụ: đổi tiền, thuế, hoàn tiền toàn phần/một phần, thời điểm ghi nhận và các status được tính.

### Bài 11 — Quan sát hiệu năng

Chạy explain cho pipeline nhóm order theo tenant/status. Ghi nhận IXSCAN/COLLSCAN, totalDocsExamined, nReturned và stage sort/group nếu xuất hiện. Nêu lý do dữ liệu lab nhỏ không đủ đại diện cho hiệu năng collection nhiều triệu document.

### Bài 12 — Kiểm soát độ dài Array

Giả sử một tenant có hai triệu order và pipeline cần trả **unique customerIds** cùng **tất cả orderIds** trong một document. Nêu giới hạn rủi ro của $push/$addToSet, sự khác nhau giữa spill bộ nhớ và giới hạn BSON 16 MiB, và đề xuất giải pháp trả **thống kê gọn + phân trang danh sách chi tiết**.

## 17. Tham khảo chính thức

- MongoDB Manual — [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/).
- MongoDB Manual — [$group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/).
- MongoDB Manual — [$sum](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sum/).
- MongoDB Manual — [$avg](https://www.mongodb.com/docs/manual/reference/operator/aggregation/avg/).
- MongoDB Manual — [$min](https://www.mongodb.com/docs/manual/reference/operator/aggregation/min/).
- MongoDB Manual — [$max](https://www.mongodb.com/docs/manual/reference/operator/aggregation/max/).
- MongoDB Manual — [$push](https://www.mongodb.com/docs/manual/reference/operator/aggregation/push/).
- MongoDB Manual — [$addToSet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/addToSet/).
- MongoDB Manual — [$unwind](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/).
- MongoDB Manual — [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/).

**Điều cần nhớ:** **$sum** cộng hoặc đếm, **$avg** lấy trung bình của giá trị số hợp lệ, **$min/$max** tìm cực trị theo BSON comparison, **$push** giữ các giá trị kể cả trùng lặp, và **$addToSet** chỉ giữ giá trị phân biệt nhưng **không đảm bảo thứ tự**. Trước khi tổng hợp, cần xác định đúng **khóa nhóm, bộ lọc, kiểu BSON và độ hạt dữ liệu sau $unwind**. Các accumulator mạnh nhất khi chúng tạo **kết quả nhỏ gọn, có ngữ nghĩa nghiệp vụ rõ ràng**, thay vì xây những mảng kết quả vô hạn.
