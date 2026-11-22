# deleteOne, deleteMany và giới hạn thao tác xóa trong MongoDB

## 1. Xóa document không chỉ là viết một câu lệnh

Trong MongoDB, hai thao tác xóa phổ biến nhất là **deleteOne()** và **deleteMany()**. Chúng đều nhận một **filter** để chọn document, nhưng khác nhau ở số document có thể bị xóa, cách dùng trong ứng dụng và rủi ro khi filter quá rộng.

Ví dụ:

~~~javascript
db.orders.deleteOne({ _id: "o001" });

db.orders.deleteMany({
  tenantId: "t001",
  status: "cancelled"
});
~~~

Lệnh đầu có mục tiêu xóa tối đa một đơn. Lệnh thứ hai có thể xóa hàng nghìn hoặc hàng triệu đơn nếu chúng khớp filter. MongoDB không tự hiểu “xóa vài bản ghi thử trước”, “giữ lại đơn cần đối soát” hay “chỉ xóa trong một tenant” nếu ứng dụng không diễn đạt các điều kiện đó.

Trong chương **Xóa và ghi theo lô**, bài này tập trung vào:

1. Cú pháp và kết quả trả về của **deleteOne()** và **deleteMany()**.
2. Ý nghĩa của filter, khả năng chọn sai document và tính bất định khi nhiều document cùng khớp.
3. Những giới hạn thật sự của lệnh xóa: số lượng, sắp xếp, tính nguyên tử, đồng thời, timeout và phạm vi.
4. Cách giới hạn số document mỗi đợt khi dọn dữ liệu lớn.
5. Kết hợp với **bulkWrite**, transaction, write concern, TTL và soft delete khi yêu cầu nghiệp vụ phức tạp.
6. Quy trình an toàn trước khi thực hiện thao tác phá hủy dữ liệu.

> Các ví dụ chạy bằng **mongosh** trên database riêng **mongo_delete_lab**. Không chạy những lệnh xóa minh họa trên collection production. Dữ liệu mẫu có nhãn riêng để tất cả ví dụ thực hành đều giới hạn phạm vi.

## 2. deleteOne(): xóa tối đa một document

### 2.1. Cú pháp

~~~javascript
db.collection.deleteOne(filter, options);
~~~

- **filter** là biểu thức truy vấn dùng để chọn document.
- **options** là đối tượng tùy chọn, có thể chứa một số cấu hình như collation, hint, write concern hoặc comment tùy phiên bản và driver.
- Kết quả được mongosh/driver trả về dưới dạng kết quả ghi; khi ghi được xác nhận, thuộc tính quan trọng là **deletedCount**.

Ví dụ:

~~~javascript
const result = db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .deleteOne({
    _id: "o001",
    dataset: "delete-lab-v1",
    tenantId: "t001"
  });

printjson(result);
print("Số document đã xóa: " + result.deletedCount);
~~~

Nếu o001 tồn tại và khớp các điều kiện, **deletedCount = 1**. Nếu o001 không tồn tại, đã bị xóa hoặc đã đổi điều kiện khiến filter không còn khớp, **deletedCount = 0**.

**deleteOne không báo lỗi chỉ vì không tìm thấy document.** Thao tác có thể được xác nhận thành công với deletedCount bằng 0. Ứng dụng cần xác định trường hợp này mang nghĩa “đã xóa từ trước”, “không tìm thấy” hay “trạng thái không còn cho phép xóa”.

### 2.2. Nếu nhiều document cùng khớp thì sao?

~~~javascript
db.orders.deleteOne({ status: "cancelled" });
~~~

Lệnh trên chỉ xóa **một document** trong các document khớp. Nhưng **không được giả định document nào sẽ bị chọn** nếu không có ràng buộc khóa đủ cụ thể. deleteOne không cung cấp tùy chọn sort để bảo đảm xóa đơn cũ nhất, mới nhất hay có giá trị _id nhỏ nhất.

Trong nghiệp vụ, nên ưu tiên filter có định danh ổn định, thường là **_id**, và thêm điều kiện tenant/ownership/trạng thái cần bảo vệ. Ví dụ:

~~~javascript
db.orders.deleteOne({
  _id: "o001",
  tenantId: "t001",
  status: "draft"
});
~~~

Lệnh này có nghĩa: **chỉ xóa o001 nếu đơn vẫn thuộc tenant t001 và vẫn ở trạng thái draft tại thời điểm MongoDB áp dụng lệnh**. Filter trạng thái giúp tránh xóa đơn đã chuyển sang paid giữa lúc người dùng nhìn thấy màn hình và lúc server xử lý yêu cầu.

### 2.3. Muốn xóa một document theo thứ tự thì dùng gì?

Khi yêu cầu là “xóa **một** bản ghi cancelled **cũ nhất**”, nên cân nhắc **findOneAndDelete()** với sort:

~~~javascript
const removed = db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .findOneAndDelete(
    {
      dataset: "delete-lab-v1",
      tenantId: "t001",
      status: "cancelled",
      legalHold: false
    },
    { sort: { createdAt: 1, _id: 1 } }
  );

printjson(removed);
~~~

Lệnh này chọn một document theo sort và trả về **document đã xóa** hoặc **null** nếu không khớp. Tính nguyên tử áp dụng cho thao tác trên một document. Việc lấy danh sách bằng find rồi gọi deleteOne sau đó **không tương đương** với một lệnh chọn-và-xóa nguyên tử: có khoảng thời gian khiến các tác vụ khác thay đổi dữ liệu ở giữa.

Khi làm việc với sharded collection, phải kiểm tra yêu cầu định tuyến và giới hạn của phiên bản MongoDB/driver đang dùng; đừng chuyển trực tiếp mẫu xóa có sort sang môi trường sharded mà không đánh giá.

## 3. deleteMany(): xóa tất cả document khớp filter

### 3.1. Cú pháp

~~~javascript
db.collection.deleteMany(filter, options);
~~~

Ví dụ:

~~~javascript
const result = db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .deleteMany({
    dataset: "delete-lab-v1",
    tenantId: "t001",
    status: "cancelled",
    legalHold: false
  });

printjson(result);
print("Đã xóa: " + result.deletedCount);
~~~

MongoDB cố xóa các document khớp filter. Khi kết quả được xác nhận thành công, **deletedCount** cho biết số document thực sự bị xóa. Nếu không có document khớp, deletedCount bằng 0.

**deleteMany không có tham số limit hoặc sort** tương đương cách dùng find().limit().sort(). Một filter rộng có thể xóa toàn bộ collection.

### 3.2. Filter rỗng là lệnh xóa nguy hiểm

~~~javascript
// CẢNH BÁO: xóa mọi document trong collection!
// db.orders.deleteMany({});
~~~

Đây là thao tác hợp lệ, nhưng nghĩa của nó là **xóa tất cả document** mà collection chứa, không phải “xóa document rỗng”. MongoDB vẫn giữ collection và các index sau khi xóa; khác với **drop()**, vốn loại bỏ collection và các index của nó.

So sánh:

| Thao tác | Phạm vi | Giữ collection/index? | Mục đích điển hình |
| --- | --- | --- | --- |
| **deleteOne(filter)** | Tối đa một document khớp | Có | Xóa một đối tượng cụ thể |
| **deleteMany(filter)** | Mọi document khớp | Có | Xóa nhiều đối tượng theo tiêu chí |
| **deleteMany({})** | Tất cả document trong collection | Có | Làm sạch toàn bộ nội dung có chủ đích |
| **drop()** | Xóa collection | **Không** | Loại bỏ toàn bộ collection, kể cả index |
| **dropDatabase()** | Xóa cả database | **Không** | Loại bỏ toàn bộ dữ liệu trong database |

Không dùng deleteMany({}) như một “lệnh thử” để xem dữ liệu có bị xóa hay không. Trong thực hành, tất cả câu lệnh xóa đều có **dataset** và **tenantId** hoặc **_id** để giảm nguy cơ vượt phạm vi.

### 3.3. Cách nhìn đúng về số lượng

**deleteMany** không có giới hạn cố định “tối đa N document” ở cấp API. Khối lượng dữ liệu có thể rất lớn, nhưng tốc độ và khả năng hoàn thành chịu ảnh hưởng bởi:

- Số document khớp và khả năng tìm được chúng qua index.
- Kích thước document và các index phải cập nhật.
- Tải ghi đồng thời, tài nguyên đĩa, replication và write concern.
- Thời gian thực thi, gián đoạn, lỗi mạng hoặc lỗi server.
- Việc collection có sharding, các chunk có di chuyển hay không.

Nếu phải xóa hàng triệu document, cần chiến lược **batch có giới hạn**, giám sát và cơ chế phục hồi thay vì cho rằng một deleteMany lớn luôn là phương án rẻ nhất.

## 4. Bộ dữ liệu mẫu để thực hành

Ta dùng collection **lab_orders** gồm mười đơn có hai tenant, nhiều trạng thái và một đơn được đánh dấu **legalHold = true**. Nhãn dataset là **delete-lab-v1**.

### 4.1. Tạo dữ liệu mẫu

Chạy nguyên khối sau trong mongosh:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_delete_lab");
  const orders = lab.getCollection("lab_orders");
  const tag = "delete-lab-v1";

  // Chỉ dọn document của bài; không drop collection/database.
  orders.deleteMany({ dataset: tag });

  orders.insertMany([
    {
      _id: "o001", dataset: tag, tenantId: "t001",
      status: "draft", legalHold: false,
      createdAt: ISODate("2026-01-01T08:00:00.000Z")
    },
    {
      _id: "o002", dataset: tag, tenantId: "t001",
      status: "draft", legalHold: false,
      createdAt: ISODate("2026-01-02T08:00:00.000Z")
    },
    {
      _id: "o003", dataset: tag, tenantId: "t001",
      status: "cancelled", legalHold: false,
      createdAt: ISODate("2026-01-03T08:00:00.000Z")
    },
    {
      _id: "o004", dataset: tag, tenantId: "t001",
      status: "cancelled", legalHold: false,
      createdAt: ISODate("2026-01-04T08:00:00.000Z")
    },
    {
      _id: "o005", dataset: tag, tenantId: "t001",
      status: "completed", legalHold: false,
      createdAt: ISODate("2026-01-05T08:00:00.000Z")
    },
    {
      _id: "o006", dataset: tag, tenantId: "t001",
      status: "pending", legalHold: false,
      createdAt: ISODate("2026-01-06T08:00:00.000Z")
    },
    {
      _id: "o007", dataset: tag, tenantId: "t002",
      status: "cancelled", legalHold: false,
      createdAt: ISODate("2026-01-07T08:00:00.000Z")
    },
    {
      _id: "o008", dataset: tag, tenantId: "t002",
      status: "pending", legalHold: false,
      createdAt: ISODate("2026-01-08T08:00:00.000Z")
    },
    {
      _id: "o009", dataset: tag, tenantId: "t001",
      status: "cancelled", legalHold: true,
      createdAt: ISODate("2026-01-09T08:00:00.000Z")
    },
    {
      _id: "o010", dataset: tag, tenantId: "t001",
      status: "cancelled", legalHold: false,
      createdAt: ISODate("2025-12-20T08:00:00.000Z")
    }
  ]);

  orders.createIndex(
    {
      dataset: 1,
      tenantId: 1,
      status: 1,
      legalHold: 1,
      createdAt: 1,
      _id: 1
    },
    { name: "ix_lab_delete_candidates" }
  );

  print("Số document lab: " +
    orders.countDocuments({ dataset: tag }));
})();
~~~

**Kết quả mong đợi:** có **10 document**. Mỗi document có _id cố định. Nếu đã thực hiện một số lệnh xóa và muốn đối chiếu lại kết quả ban đầu, chạy lại toàn bộ khối seed này.

### 4.2. Xem trước tập document sẽ xóa

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");

  const filter = {
    dataset: "delete-lab-v1",
    tenantId: "t001",
    status: "cancelled",
    legalHold: false
  };

  print("Số ứng viên: " + orders.countDocuments(filter));
  printjson(
    orders.find(
      filter,
      { _id: 1, tenantId: 1, status: 1, legalHold: 1, createdAt: 1 }
    )
    .sort({ createdAt: 1, _id: 1 })
    .toArray()
  );
})();
~~~

Từ bộ dữ liệu nguyên gốc, ứng viên là **o010, o003, o004** theo thứ tự createdAt tăng dần, tổng cộng **3**. Document **o009** không nằm trong danh sách vì legalHold = true; **o007** thuộc tenant t002 nên cũng không khớp.

Khi chuẩn bị xóa thật, xem trước bằng find/countDocuments giúp phát hiện filter sai. Tuy nhiên, đây **không phải snapshot bảo đảm tập kết quả sẽ giữ nguyên đến lúc deleteMany chạy**: các writer khác có thể thay đổi dữ liệu giữa bước kiểm tra và bước xóa.

## 5. Thực hành deleteOne, findOneAndDelete và deleteMany

Các bước sau là **một chuỗi liên tiếp** sau khi seed; không reset giữa các bước trừ khi được chỉ rõ.

### 5.1. Bước A — Xóa một draft bằng _id

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");

  const result = orders.deleteOne({
    _id: "o001",
    dataset: "delete-lab-v1",
    tenantId: "t001",
    status: "draft"
  });

  printjson(result);
  print("deletedCount=" + result.deletedCount);
})();
~~~

**Kết quả mong đợi lần đầu:** deletedCount = **1**. Chạy lại ngay lệnh này thì deletedCount = **0**, vì o001 đã không còn.

Điều kiện **status: "draft"** làm nhiệm vụ bảo vệ: nếu đơn đã chuyển sang paid, câu lệnh sẽ không xóa nó chỉ vì client vẫn giữ _id cũ. Đây là một dạng thao tác có điều kiện trên một document.

### 5.2. Bước B — Xóa đúng một đơn cancelled cũ nhất

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");

  const removed = orders.findOneAndDelete(
    {
      dataset: "delete-lab-v1",
      tenantId: "t001",
      status: "cancelled",
      legalHold: false
    },
    { sort: { createdAt: 1, _id: 1 } }
  );

  printjson(removed);
})();
~~~

**Kết quả mong đợi:** document được trả về có **_id = "o010"**, vì nó có createdAt sớm nhất trong nhóm cancelled của t001 không bị legal hold. Nếu không có document nào khớp, kết quả trả về là null.

Khác với deleteOne, findOneAndDelete có thể sắp xếp rồi xóa một document và trả về nội dung document đã xóa. Khi không cần sort và không cần document cũ, deleteOne theo _id thường đơn giản hơn.

### 5.3. Bước C — Xóa nhiều đơn cancelled còn lại

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");

  const result = orders.deleteMany({
    dataset: "delete-lab-v1",
    tenantId: "t001",
    status: "cancelled",
    legalHold: false
  });

  printjson(result);
  print("deletedCount=" + result.deletedCount);
})();
~~~

**Kết quả mong đợi khi thực hiện sau bước A và B:** deletedCount = **2** (o003, o004). Đơn o009 được bảo vệ bởi legalHold = true.

Nếu chạy Bước C **trực tiếp ngay sau seed**, deletedCount sẽ là **3** vì o010 chưa bị xóa ở Bước B. Số document bị xóa phụ thuộc trạng thái dữ liệu ngay lúc lệnh thực hiện, không phụ thuộc câu ví dụ nào bạn đã đọc.

### 5.4. Bước D — Xác nhận phạm vi còn lại

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");

  const filter = { dataset: "delete-lab-v1" };
  print("Còn lại: " + orders.countDocuments(filter));
  printjson(
    orders.find(
      filter,
      { _id: 1, tenantId: 1, status: 1, legalHold: 1 }
    )
    .sort({ _id: 1 })
    .toArray()
  );
})();
~~~

**Kết quả mong đợi:** còn **6 document** gồm **o002, o005, o006, o007, o008, o009**. Đây là kiểm tra kỹ thuật phạm vi thao tác trong lab, không phải bằng chứng về tính nguyên tử của cả chuỗi A–C.

## 6. “Giới hạn thao tác xóa” thực sự có những nghĩa nào?

Từ **giới hạn** có thể chỉ nhiều yêu cầu khác nhau:

| Mục tiêu | Cách tiếp cận |
| --- | --- |
| Chỉ xóa một document | **deleteOne** với filter theo _id và điều kiện nghiệp vụ |
| Xóa một document theo thứ tự | **findOneAndDelete** với sort |
| Xóa tất cả document thỏa điều kiện | **deleteMany** |
| Xóa tối đa N document trong một đợt | Chọn trước N _id rồi xóa theo **_id: { $in: ids }** với điều kiện bảo vệ |
| Giới hạn theo tenant/trạng thái/thời gian | Filter cụ thể, đánh giá trước bằng find/countDocuments |
| Giới hạn tải lên database | Batch, điều tiết tốc độ, index, theo dõi latency và replication |
| Giữ tài liệu để khôi phục hoặc đối soát | Soft delete, archive, backup, hoặc retention policy |

**Không có cú pháp deleteMany(filter).limit(N)** giống một cursor find. Phương pháp gần đúng đúng là **lấy danh sách ứng viên có giới hạn**, rồi xóa những _id đã chọn. Cần giải quyết cạnh tranh ghi để tránh xóa bản ghi vừa thay đổi trạng thái.

### 6.1. Xóa tối đa N ứng viên bằng hai bước

Trước ví dụ này, hãy **chạy lại seed ở mục 4** để có tập dữ liệu ban đầu.

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");
  const tag = "delete-lab-v1";
  const cutoff = ISODate("2026-01-05T00:00:00.000Z");
  const batchSize = 2;

  const eligibility = {
    dataset: tag,
    tenantId: "t001",
    status: "cancelled",
    legalHold: false,
    createdAt: { $lt: cutoff }
  };

  // Bước 1: chọn tối đa 2 document theo thứ tự ổn định.
  const ids = orders.find(eligibility, { _id: 1 })
    .sort({ createdAt: 1, _id: 1 })
    .limit(batchSize)
    .toArray()
    .map(doc => doc._id);

  printjson({ ids: ids });

  // Bước 2: kiểm tra lại điều kiện nghiệp vụ khi xóa.
  const result = ids.length === 0
    ? { deletedCount: 0 }
    : orders.deleteMany({
        ...eligibility,
        _id: { $in: ids }
      });

  print("deletedCount=" + result.deletedCount);
})();
~~~

Từ dữ liệu seed, hai ứng viên cũ nhất là **o010** và **o003**, nên deletedCount dự kiến bằng **2** nếu không có writer khác xen vào. Điều kiện **_id: { $in: ids }** khiến phạm vi xóa tối đa bằng số ID trong batch, còn việc lặp lại status, legalHold, tenantId và cutoff giúp tránh xóa một ứng viên đã đổi sang trạng thái không còn đủ điều kiện ở giữa hai bước.

Đây **không phải transaction nguyên tử giữa find và deleteMany**. Có thể xảy ra:

- Document bị tác vụ khác xóa trước → deletedCount nhỏ hơn ids.length.
- Document chuyển từ cancelled thành paid → lệnh deleteMany không xóa vì filter kiểm tra lại status.
- Document vừa được thêm vào nhưng không có trong ids → không bị xóa trong batch hiện tại.
- Document vừa được chỉnh sửa nhưng vẫn thỏa toàn bộ điều kiện → có thể vẫn bị xóa; nếu nghiệp vụ đòi “không đổi bất kỳ trường nào”, cần thêm version hoặc cơ chế khóa/transaction thích hợp.

### 6.2. Lặp nhiều batch có ngân sách rõ ràng

Thay vì một lệnh xóa hàng triệu bản ghi, tác vụ dọn dữ liệu có thể chạy các batch giới hạn. Ví dụ dưới đây minh họa **tối đa ba batch, mỗi batch hai ID**, không chạy vô hạn:

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");

  const cutoff = ISODate("2026-01-05T00:00:00.000Z");
  const batchSize = 2;
  const maxBatches = 3;

  const eligibility = {
    dataset: "delete-lab-v1",
    tenantId: "t001",
    status: "cancelled",
    legalHold: false,
    createdAt: { $lt: cutoff }
  };

  let totalDeleted = 0;

  for (let batch = 1; batch <= maxBatches; batch++) {
    const ids = orders.find(eligibility, { _id: 1 })
      .sort({ createdAt: 1, _id: 1 })
      .limit(batchSize)
      .toArray()
      .map(doc => doc._id);

    if (ids.length === 0) {
      break;
    }

    const result = orders.deleteMany({
      ...eligibility,
      _id: { $in: ids }
    });

    printjson({
      batch: batch,
      selected: ids.length,
      deleted: result.deletedCount
    });

    totalDeleted += result.deletedCount;

    // Tránh lặp liên tục khi có xung đột hoặc không tiến triển.
    if (result.deletedCount === 0) {
      break;
    }
  }

  print("Tổng số đã xóa trong lượt: " + totalDeleted);
})();
~~~

Trong production, bổ sung **checkpoint**, **metrics**, **giới hạn tốc độ**, **thời gian nghỉ giữa batch nếu cần**, **cảnh báo lỗi** và cách tiếp tục sau gián đoạn. Không bắt buộc tải toàn bộ ID của hàng triệu bản ghi vào bộ nhớ ứng dụng; từng batch chỉ nên giữ lượng ID vừa đủ.

### 6.3. Vì sao không dùng skip cho việc dọn theo trang?

Nếu chọn batch bằng **skip(1000).limit(100)** rồi xóa, các document ở trước bị loại bỏ sẽ làm vị trí trang thay đổi. Batch tiếp theo có thể **bỏ sót** document. Đó là lỗi phổ biến khi phân trang trên một tập kết quả đang bị chính quy trình xử lý thay đổi.

Đối với deletion job, có thể:

- Lặp lấy **N document đầu tiên còn thỏa filter** rồi xóa như ví dụ trên.
- Hoặc dùng **keyset/cursor theo (createdAt, _id)** với checkpoint và điều kiện nhất quán nếu phải đi tuần tự qua dữ liệu rất lớn.

Chọn theo _id với sort ổn định chỉ giúp chọn ứng viên có thể dự đoán; không biến nhiều lệnh thành một transaction.

## 7. deleteOne, deleteMany và bulkWrite

### 7.1. Gom các thao tác xóa trong một lời gọi

Khi có nhiều thao tác có filter khác nhau, **bulkWrite()** cho phép gửi một danh sách operations, bao gồm **deleteOne** và **deleteMany**:

~~~javascript
// Chạy lại seed mục 4 trước khi thử.
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");

  const result = orders.bulkWrite(
    [
      {
        deleteOne: {
          filter: {
            _id: "o001",
            dataset: "delete-lab-v1",
            tenantId: "t001",
            status: "draft"
          }
        }
      },
      {
        deleteMany: {
          filter: {
            dataset: "delete-lab-v1",
            tenantId: "t001",
            status: "cancelled",
            legalHold: false
          }
        }
      }
    ],
    { ordered: true }
  );

  printjson(result);
  print("Đã xóa: " + result.deletedCount);
})();
~~~

Từ dữ liệu seed, lần đầu kết quả mong đợi là **4 document**: một đơn draft o001 và ba đơn cancelled o003, o004, o010. Document o009 vẫn không bị xóa vì legalHold = true.

**ordered: true** yêu cầu thực thi các thao tác theo thứ tự trong danh sách và thường dừng sau lỗi ghi; **ordered: false** cho phép MongoDB có thêm linh hoạt về thứ tự thực thi và tiếp tục các thao tác không phụ thuộc trong nhiều trường hợp lỗi. Không được coi ordered: false là cam kết mọi thao tác đều thành công, hoặc ordered: true là một transaction.

### 7.2. BulkWrite không tự bảo đảm nguyên tử toàn batch

Một bulkWrite gồm nhiều lệnh deleteOne/deleteMany **không tự biến toàn bộ nhóm thành một đơn vị all-or-nothing**. Một số thao tác có thể đã xóa dữ liệu trước khi thao tác sau thất bại. Ứng dụng phải:

- Xem **BulkWriteResult** và **write errors** nếu có.
- Ghi rõ thao tác nào đã thành công, thao tác nào phải được đánh giá lại.
- Tránh retry cả một batch nhiều điều kiện rộng mà không kiểm tra tác động.
- Nếu cần all-or-nothing trên nhiều document, xem xét transaction trên triển khai MongoDB hỗ trợ.

BulkWrite giảm số lần trao đổi với server và gom cách gửi operations, **không giải quyết tự động tính đúng đắn nghiệp vụ hoặc giới hạn tổng số document bị xóa**.

### 7.3. Khi nào nên dùng mỗi phương án?

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Xóa một user bằng _id | deleteOne |
| Xóa một bản ghi cũ nhất và nhận về nội dung | findOneAndDelete với sort |
| Xóa tất cả phiên tạm hết hạn trong phạm vi riêng | deleteMany có filter cụ thể hoặc TTL theo chính sách |
| Dọn hàng triệu log từng đợt nhỏ | Batch chọn ID + deleteMany; checkpoint và điều tiết |
| Gửi nhiều thao tác xóa khác filter | bulkWrite |
| Xóa nhiều document với all-or-nothing bắt buộc | Transaction với giới hạn và chi phí vận hành phù hợp |

## 8. Tính nguyên tử, cạnh tranh ghi và transaction

### 8.1. deleteOne nguyên tử ở phạm vi document

MongoDB bảo đảm thao tác ghi trên **một document** mang tính nguyên tử, kể cả khi thao tác thay đổi nhiều field của document. Với deleteOne, một document hoặc bị xóa, hoặc không bị xóa; filter được đánh giá khi thao tác thực hiện.

Điều này giúp bảo vệ việc xóa theo trạng thái:

~~~javascript
db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .deleteOne({
    _id: "o002",
    dataset: "delete-lab-v1",
    tenantId: "t001",
    status: "draft"
  });
~~~

Nếu writer khác đã chuyển o002 sang pending trước khi lệnh xóa được áp dụng, lệnh không khớp nữa và deletedCount có thể bằng 0. Nhưng nếu nhiều service cùng cần xóa tài liệu, ghi audit, giải phóng tài nguyên và thông báo ra ngoài, **tính nguyên tử của một deleteOne không bao trùm tất cả tác động đó**.

### 8.2. deleteMany không nguyên tử ở phạm vi toàn bộ tập kết quả

Mặc dù **mỗi lần xóa một document** trong deleteMany là nguyên tử, **toàn bộ lệnh xóa nhiều document không phải transaction all-or-nothing**. Có thể có những document đã bị xóa còn document khác chưa bị xóa nếu lệnh bị gián đoạn hoặc có tác vụ đồng thời.

Ứng dụng khác có thể quan sát trạng thái trung gian trong quá trình deleteMany, tùy read concern và cách truy cập. Không xây giả định “hoặc toàn bộ hàng triệu document biến mất, hoặc không document nào biến mất” chỉ từ một lệnh deleteMany.

### 8.3. Khi cần transaction

Nếu nghiệp vụ yêu cầu xóa Order, xóa một số bản ghi liên quan và ghi AuditEvent cùng thành công hoặc cùng thất bại, có thể cân nhắc **multi-document transaction** trên môi trường MongoDB có hỗ trợ. Ví dụ về ý tưởng ở tầng driver:

~~~text
START TRANSACTION
  Delete Order khi còn ở trạng thái draft
  Delete các record tạm liên quan
  Insert AuditEvent với lý do và người thực hiện
COMMIT
~~~

Không nên đưa một thao tác xóa hàng triệu document vào một transaction khổng lồ chỉ để “an toàn hơn”: transaction có chi phí quản lý, thời gian, tài nguyên và khả năng xung đột. Thiết kế transaction boundary phải khớp số document thực sự cần tính nguyên tử.

Một số nghiệp vụ cần giữ audit **ngay cả khi transaction xóa thất bại**; đó là một chính sách khác và phải được thiết kế tường minh, không giả định audit sẽ cùng rollback.

### 8.4. Xóa nhiều document liên quan không có cascade mặc định

Trong MongoDB, xóa Customer không tự xóa Orders theo foreign key như một số mô hình quan hệ. Các trường customerId, orderId thường chỉ là tham chiếu logic. Nếu cần cascade hoặc giữ snapshot:

- Xác định rõ dữ liệu con phải xóa, giữ lại hay ẩn danh.
- Xác định thứ tự và tính nguyên tử cần thiết.
- Tránh xóa dữ liệu có nghĩa vụ pháp lý, tài chính hoặc audit.
- Thiết kế lại cách ứng dụng xử lý tham chiếu mồ côi.

Xóa “cho gọn” nhưng bỏ qua vòng đời dữ liệu liên quan có thể tạo lỗi nghiệp vụ khó sửa hơn việc giữ lại document.

## 9. Write concern, lỗi và khả năng retry

### 9.1. deletedCount không phải bản sao lưu

Khi thao tác được server xác nhận, **deletedCount** cho biết số document đã bị xóa trong lệnh đó. Nó **không lưu lại nội dung đầy đủ** của những document đã mất. Nếu cần khả năng khôi phục, phải có chính sách backup, point-in-time recovery, snapshot, archive hoặc một luồng ghi audit/pre-image phù hợp.

Đối với thao tác không được xác nhận (**unacknowledged write**, ví dụ write concern w:0), client không thể dựa vào deletedCount như một kết quả chính xác; ứng dụng cần chính sách write concern phù hợp với mức độ rủi ro.

### 9.2. Write concern ảnh hưởng độ bền được xác nhận

Ví dụ minh họa một thao tác xóa yêu cầu xác nhận ghi theo chính sách **majority**:

~~~javascript
db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .deleteOne(
    {
      _id: "o002",
      dataset: "delete-lab-v1",
      tenantId: "t001",
      status: "draft"
    },
    {
      writeConcern: { w: "majority", wtimeout: 5000 }
    }
  );
~~~

Ý nghĩa của majority phụ thuộc topology của replica set/sharded deployment. Với standalone server và các cấu hình môi trường khác nhau, yêu cầu write concern có thể cần điều chỉnh; không dùng mẫu trên mà không hiểu topology thực tế. **WriteConcernError** hoặc timeout không có nghĩa chắc chắn thao tác chưa xảy ra: cần đối chiếu lại trạng thái và thiết kế xử lý kết quả không xác định.

### 9.3. Retry thao tác xóa

Về cơ bản, **deleteOne** là thao tác xóa một document và thuộc nhóm có thể tham gia cơ chế **retryable writes** khi đáp ứng điều kiện của driver/server/session. **deleteMany** không nằm trong tập thao tác single-document retryable theo cùng cơ chế đó. Khả năng retry tự động thực tế phải xem cấu hình driver, topology và các phiên bản được hỗ trợ.

Không nên coi retry là vô hại trong mọi trường hợp:

- Retry deleteOne theo **_id cố định** sau khi đã xóa thường cho deletedCount = 0 nếu lệnh mới được thực hiện, nhưng kết quả trả về có thể bị cơ chế retryable writes xử lý theo ngữ nghĩa riêng của phiên ghi.
- Retry một filter rộng như **{ status: "cancelled" }** có thể xóa **một document khác** ở lần sau.
- Retry deleteMany với filter theo thời gian/trạng thái có thể bắt thêm document vừa đủ điều kiện trong lúc retry.

Với request API quan trọng, nên dùng khóa ổn định, điều kiện trạng thái rõ ràng, idempotency key nếu nghiệp vụ đòi hỏi, và khả năng đối chiếu sau lỗi mạng.

### 9.4. Một số loại lỗi cần phân biệt

| Tình huống | Ý nghĩa |
| --- | --- |
| deletedCount = 0, không có exception | Không có document khớp tại lúc xóa; không nhất thiết là lỗi hệ thống |
| Unauthorized | Tài khoản không có quyền delete hoặc không có quyền trên collection |
| Write concern error/timeout | Không đạt điều kiện xác nhận ghi; trạng thái thực tế có thể cần kiểm tra |
| Network error | Có thể chưa biết server đã thực thi thao tác hay chưa |
| Write conflict/transaction aborted | Cần xử lý retry theo hợp đồng transaction và driver |
| Hint không phù hợp hoặc index không tồn tại | Tùy chọn truy vấn không hợp lệ cho trạng thái index hiện có |
| Collection/shard thay đổi | Có thể cần retry hoặc phối hợp với quy trình vận hành sharded |

## 10. Xóa dữ liệu lớn và hiệu năng

### 10.1. Index giúp xác định document ứng viên

Nếu ứng dụng thường xóa phiên tạm theo **tenantId + status + createdAt**, index theo các trường lọc quan trọng có thể giảm số document phải quét để tìm ứng viên. Ví dụ index lab:

~~~javascript
{
  dataset: 1,
  tenantId: 1,
  status: 1,
  legalHold: 1,
  createdAt: 1,
  _id: 1
}
~~~

Index này phản ánh filter/sort của batch cleanup trong bài. Tuy vậy, mỗi lần xóa document cũng phải làm sạch các index entry liên quan, nên **nhiều index làm tăng write amplification**. Không tạo index chỉ vì một job chạy một lần nếu chi phí duy trì dài hạn cao hơn lợi ích.

### 10.2. Xem explain cho bước chọn ứng viên

~~~javascript
db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .find({
    dataset: "delete-lab-v1",
    tenantId: "t001",
    status: "cancelled",
    legalHold: false,
    createdAt: { $lt: ISODate("2026-01-05T00:00:00.000Z") }
  })
  .sort({ createdAt: 1, _id: 1 })
  .limit(2)
  .explain("executionStats");
~~~

Đọc **winningPlan**, **totalKeysExamined**, **totalDocsExamined**, **nReturned**. Với mười document, MongoDB có thể chọn COLLSCAN vì rẻ hơn index scan; không thể suy ra hiệu quả ở hệ thống thực từ tập lab nhỏ. Cần thử trên dữ liệu gần production và cân nhắc cả tốc độ tìm ứng viên, tốc độ xóa, dung lượng index, thời gian replication và ảnh hưởng tới tác vụ đọc khác.

### 10.3. Xóa trên sharded collection

Trong cluster sharded, vị trí document phụ thuộc **shard key**. Một filter có đầy đủ shard key thường giúp định tuyến chính xác hơn; filter rộng hoặc thiếu thông tin định tuyến có thể làm thao tác phải khảo sát nhiều shard. Các giới hạn và chiến lược định tuyến của deleteOne, findOneAndDelete và deleteMany cần được đối chiếu với phiên bản MongoDB của triển khai.

Khi các chunk di chuyển hoặc có ghi đồng thời, không nên mặc định một lần deleteMany rộng sẽ xử lý tất cả document theo một ảnh chụp bất biến của cluster. Với quy trình dọn dài, cần theo dõi số còn lại, có thể chạy lại theo filter và kiểm tra dữ liệu mới phát sinh trong quá trình dọn.

## 11. Xóa cứng, soft delete, TTL và lưu trữ

Không phải mọi yêu cầu “xóa” đều cần gọi deleteOne hoặc deleteMany. Hãy chọn theo **vòng đời dữ liệu**.

### 11.1. Hard delete

**Hard delete** loại document khỏi collection:

~~~javascript
db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .deleteOne({
    _id: "o001",
    dataset: "delete-lab-v1",
    status: "draft"
  });
~~~

Phù hợp khi dữ liệu thật sự không cần giữ và có chính sách cho phép xóa vĩnh viễn khỏi collection. Lệnh xóa không bảo đảm mọi bản sao lưu ngoài hệ thống cũng bị xóa; nghĩa vụ xóa dữ liệu cần bao gồm các kho lưu trữ liên quan theo chính sách.

### 11.2. Soft delete

**Soft delete** đánh dấu document đã bị xóa về mặt nghiệp vụ, nhưng document vẫn tồn tại trong MongoDB:

~~~javascript
db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .updateOne(
    {
      _id: "o002",
      dataset: "delete-lab-v1",
      tenantId: "t001",
      status: "draft",
      deletedAt: { $exists: false }
    },
    {
      $set: {
        deletedAt: new Date(),
        deletionReason: "customer_request"
      }
    }
  );
~~~

Các truy vấn hiển thị document đang hoạt động phải thêm điều kiện:

~~~javascript
db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .find({
    dataset: "delete-lab-v1",
    tenantId: "t001",
    deletedAt: { $exists: false }
  });
~~~

Soft delete giúp có thời gian hoàn tác hoặc đối soát, nhưng **không làm dữ liệu biến mất khỏi database hoặc backup**. Nếu cần xóa dữ liệu cá nhân thực sự, phải có quy trình purge và kiểm soát quyền truy cập trong giai đoạn lưu tạm.

### 11.3. TTL index cho dữ liệu có hạn dùng

Với session/token tạm, MongoDB hỗ trợ **TTL index** để xóa tự động dựa trên field Date:

~~~javascript
const lab = db.getSiblingDB("mongo_delete_lab");
const sessions = lab.getCollection("lab_sessions");

sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0, name: "ttl_lab_expires_at" }
);

sessions.insertOne({
  _id: "session-example-001",
  dataset: "delete-lab-v1",
  tenantId: "t001",
  expiresAt: new Date(Date.now() + 15 * 60 * 1000)
});
~~~

TTL dọn dữ liệu bằng tiến trình nền và **không cam kết document biến mất đúng từng mili giây tại thời điểm hết hạn**. Ứng dụng phải kiểm tra expiresAt khi xác nhận một session còn hiệu lực. TTL thường là index trên một trường thời gian và không thay thế một chiến lược xóa theo nhiều điều kiện như legalHold, tenantId hoặc trạng thái nghiệp vụ.

Không áp dụng TTL cho các đơn hàng đã thanh toán chỉ vì chúng cũ: thời hạn lưu, audit, hoàn tiền và yêu cầu pháp lý phải được xác định trước.

### 11.4. Archive trước khi purge

Với dữ liệu cần tra soát nhiều năm nhưng ít truy cập trực tuyến, có thể cần **archive** thay vì xóa ngay. Một quy trình có kiểm soát:

~~~text
Chọn document đủ điều kiện lưu trữ
  -> Ghi sang kho archive
  -> Xác nhận dữ liệu archive đầy đủ và có thể đọc lại
  -> Ghi checkpoint / bằng chứng đối soát
  -> Xóa theo batch khỏi collection đang hoạt động
~~~

Không thực hiện bước xóa trước khi chắc chắn phần archive đã được ghi và xác minh đầy đủ. Nếu archive và delete nằm trên hai hệ thống khác nhau, cần cơ chế retry/idempotency và đối soát vì không có transaction nguyên tử xuyên hai hệ thống một cách mặc định.

## 12. Quy trình an toàn trước khi xóa production

Với một thao tác xóa nhiều document, có thể dùng trình tự:

**Bước 1 — Viết chính sách xóa.** Xác định ai yêu cầu, loại dữ liệu, retention, legal hold, tenant, khoảng thời gian, khả năng cần phục hồi và nguồn phê duyệt.

**Bước 2 — Khóa phạm vi.** Mỗi filter phải có điều kiện xác thực tenant/owner hoặc dataset theo đúng nghiệp vụ. Ưu tiên điều kiện _id khi xóa một document. Không nhận trực tiếp một filter MongoDB tùy ý từ client ngoài mà không giới hạn trường và toán tử.

**Bước 3 — Xem trước và đếm.** Dùng find với projection phù hợp, countDocuments, sample dữ liệu và xác minh biên của khoảng thời gian. Trong môi trường nhiều tenant, kiểm tra các tenant khác không nằm trong tập kết quả.

**Bước 4 — Đặt ngân sách.** Xác định số document tối đa mỗi batch, thời điểm chạy, tốc độ mong muốn, các chỉ số cần cảnh báo, điều kiện tạm dừng và cách tiếp tục sau lỗi.

**Bước 5 — Đảm bảo đường phục hồi.** Kiểm tra backup/point-in-time restore, archive hoặc audit phù hợp. Chú ý việc khôi phục cả document lẫn tham chiếu liên quan.

**Bước 6 — Chạy batch nhỏ có điều kiện bảo vệ.** Lấy ID giới hạn, xóa kèm trạng thái/tenant/legalHold như khi chọn, ghi deletedCount và checkpoint.

**Bước 7 — Đối chiếu và ghi nhận.** Theo dõi remaining candidates, tốc độ đọc/ghi, replication lag, lỗi/timeout và đối soát số lượng theo phạm vi. Không lấy deletedCount duy nhất làm chứng minh rằng mọi mục tiêu nghiệp vụ đã đạt.

**Bước 8 — Dừng đúng lúc.** Nếu deletedCount bất thường, phạm vi lệch dự kiến, backup không sẵn sàng hoặc dịch vụ bị ảnh hưởng, dừng job và đánh giá trước khi tiếp tục.

### 12.1. Ví dụ filter an toàn và filter rủi ro

| Filter | Đánh giá |
| --- | --- |
| **{ _id: id, tenantId: authenticatedTenantId, status: "draft" }** | Phù hợp cho xóa một draft có kiểm soát |
| **{ tenantId, status: "cancelled", legalHold: false, createdAt: { $lt: cutoff } }** | Có phạm vi cho batch retention nếu tenant/cutoff đã được kiểm soát |
| **{ status: "cancelled" }** | Có thể xóa của mọi tenant và mọi thời điểm |
| **{}** | Xóa toàn collection bằng deleteMany |
| **{ createdAt: { $lt: new Date() } }** | Rất rộng, có thể xóa hầu hết dữ liệu hiện có |
| Filter nhận trực tiếp từ HTTP request | Rủi ro injection/chọn sai phạm vi nếu không validate/allowlist |

## 13. Bài tập thực hành

### Bài 1 — Dự đoán deletedCount

Chạy lại seed. Thực hiện **deleteOne** với _id o001, sau đó chạy lần nữa. Ghi lại deletedCount ở từng lần và giải thích vì sao lệnh thứ hai không báo lỗi mặc dù không tìm thấy document.

### Bài 2 — Cùng filter nhưng deleteOne khác deleteMany

Từ seed, đếm các document có tenantId t001, status cancelled và legalHold false. So sánh kết quả nếu dùng deleteOne và nếu dùng deleteMany. Vì sao không được dự đoán chính xác document nào bị deleteOne xóa nếu filter chọn nhiều document?

### Bài 3 — Xóa một document cũ nhất

Từ seed, dùng **findOneAndDelete** với sort theo createdAt tăng dần rồi _id tăng dần để xóa một đơn cancelled không bị legal hold. Đối chiếu _id trả về và giải thích sự khác biệt với phương án gọi find trước rồi deleteOne sau.

### Bài 4 — Xóa tối đa hai document

Từ seed, chọn tối đa hai document cancelled của tenant t001, tạo danh sách _id rồi xóa bằng deleteMany có **_id: { $in: ids }**. Viết lại điều kiện tenantId/status/legalHold khi xóa. Giải thích vì sao deletedCount có thể nhỏ hơn số ID đã chọn khi có ghi đồng thời.

### Bài 5 — Dọn theo batch

Viết job tối đa năm batch, mỗi batch tối đa hai document, với cutoff và legalHold. Ghi log batch number, selected count, deletedCount và số lượng ứng viên còn lại. Giải thích vì sao dùng skip trên tập đang bị xóa có thể bỏ sót dữ liệu.

### Bài 6 — BulkWrite và transaction

Tạo một bulkWrite chứa deleteOne của một draft, deleteMany của các cancelled, và một updateOne thay đổi ghi chú. So sánh ordered true/false. Nếu thao tác thứ hai lỗi sau khi thao tác đầu thành công, liệu bulkWrite có tự rollback thao tác đầu không? Đề xuất transaction boundary khi ba thao tác phải all-or-nothing.

### Bài 7 — Chọn hard delete hay soft delete

Phân loại các tình huống: giỏ hàng bỏ dở, session hết hạn, đơn đã thanh toán, yêu cầu xóa tài khoản, event audit và bản ghi nhập sai. Đề xuất hard delete, soft delete, TTL hoặc archive dựa trên thời hạn lưu và quyền truy cập. Nêu một trường hợp soft delete không đáp ứng nghĩa vụ xóa dữ liệu cá nhân.

### Bài 8 — Lỗi mạng khi xóa

Client gửi deleteOne theo _id và kết nối bị mất trước khi nhận kết quả. Điều gì có thể đã xảy ra trên server? Bạn sẽ kiểm tra trạng thái và xử lý retry thế nào? So sánh với việc retry deleteMany dùng filter rất rộng trong khi document mới vẫn tiếp tục xuất hiện.

### Bài 9 — Thiết kế index cho retention

Giả sử có 50 triệu order, mỗi đêm dọn những đơn cancelled của một tenant đã quá hạn và không bị legal hold. Viết query chọn ứng viên, đề xuất compound index, xem explain và nêu các metric cần đo ngoài thời gian query (ví dụ write latency, replication lag, dung lượng index).

## 14. Tham khảo MongoDB

- MongoDB Manual — [db.collection.deleteOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteOne/).
- MongoDB Manual — [db.collection.deleteMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteMany/).
- MongoDB Manual — [db.collection.findOneAndDelete()](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOneAndDelete/).
- MongoDB Manual — [db.collection.bulkWrite()](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/).
- MongoDB Manual — [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).
- MongoDB Manual — [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/).
- MongoDB Manual — [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/).

**Kết luận:** **deleteOne** giới hạn số document bị xóa ở mức một, nhưng không cho phép giả định thứ tự chọn nếu filter khớp nhiều bản ghi. **deleteMany** xóa tất cả document khớp và không có limit/sort ở cấp API; cần tự thiết kế batch chọn ID khi muốn giới hạn N bản ghi mỗi lượt. Mọi thao tác xóa cần filter chính xác, hiểu ranh giới nguyên tử, xử lý lỗi/retry và có chính sách giữ hoặc phục hồi dữ liệu phù hợp. Trong hệ thống thật, chất lượng của một quy trình xóa không được đo chỉ bằng tốc độ, mà còn bằng khả năng **không xóa nhầm** và **giải thích được chính xác dữ liệu nào đã bị tác động**.
