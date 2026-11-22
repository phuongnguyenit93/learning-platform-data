# Bulk operation, batch và khả năng thành công từng phần trong NoSQL

Khi cần nhập 50.000 sản phẩm, cập nhật trạng thái hàng nghìn đơn hàng hoặc dọn dữ liệu hết hạn, ứng dụng thường muốn gom nhiều thao tác ghi thành **bulk operation** hoặc **batch**. Làm như vậy có thể giảm số lần trao đổi với database và tăng thông lượng. Nhưng **một batch không nhất thiết là một giao dịch**: một số thao tác có thể đã thành công trước khi lệnh gặp lỗi, những thao tác khác chưa được thử, và có những trường hợp client hoàn toàn không biết server đã ghi đến đâu.

Một thiết kế đúng vì thế phải quản lý cả **thành công từng phần** (*partial success*), **kết quả không chắc chắn** (*unknown outcome*), **thử lại an toàn** (*idempotent retry*) và **đối soát** (*reconciliation*).

Bài học đặt các khái niệm trong ngữ cảnh **CRUD và truy vấn của NoSQL**, dùng MongoDB làm ví dụ thực hành, rồi mở rộng sang cách các nền tảng khác diễn đạt batch.

## 1. Phân biệt bulk, batch và transaction

| Khái niệm | Mục đích | Điều không được suy ra |
| --- | --- | --- |
| **Bulk operation** | Gửi nhiều lệnh insert/update/delete qua một API | Không mặc nhiên atomic cho cả tập |
| **Batch** | Nhóm các mục để xử lý trong một đợt | Không mặc nhiên rollback cùng nhau |
| **Client-side batching** | Gom mục để giảm overhead mạng | Không mặc nhiên chỉ có một lệnh ở server |
| **Transaction** | Commit hoặc abort theo một ranh giới nguyên tử được hỗ trợ | Không nhất thiết bao trùm các hệ ngoài transaction |
| **Job nhập liệu** | Một quy trình gồm nhiều batch, checkpoint và báo cáo | Không tự có tính toàn vẹn giao dịch trên hàng triệu record |
| **Pipeline** | Giảm chi phí trao đổi cho một chuỗi lệnh | Không mặc nhiên cùng ngữ nghĩa với transaction |

Có ba cấp cần nhìn rõ:

~~~text
JOB: nhập 10.000 sản phẩm
  |
  +-- Batch 1: 500 operations
  |     +-- insert product-001: thành công
  |     +-- insert product-002: thành công
  |     +-- insert product-003: lỗi
  |
  +-- Batch 2: 500 operations
  |     +-- ...
  |
  +-- Batch 20: 500 operations

Nguyên tử một document ≠ nguyên tử một batch ≠ nguyên tử toàn job
~~~

Trong MongoDB, **một thao tác sửa một document là nguyên tử**; nhưng nhiều thao tác trên nhiều document trong `bulkWrite` không tự trở thành một đơn vị all-or-nothing. Ngay cả `updateMany` không có transaction cũng không tự bảo đảm tất cả document cùng được cập nhật hoặc cùng rollback khi phát sinh lỗi.

**Mục tiêu của bulk chủ yếu là hiệu quả xử lý hàng loạt**, còn tính nguyên tử phải được thiết kế và xác nhận riêng.

## 2. Vì sao bulk thường nhanh hơn từng request riêng?

Một request database có thể phải trả chi phí:

- Gửi và nhận dữ liệu qua mạng.
- Xử lý giao thức request/response.
- Điều phối lệnh trong client, driver và server.
- Tra cứu chỉ mục và thực hiện ghi.
- Xác nhận kết quả theo mức durability đã chọn.

Nếu gửi 20.000 lệnh tuần tự, phần overhead này có thể trở thành nút nghẽn. Khi gom thao tác, driver có thể tối ưu việc đóng gói và gửi dữ liệu, giảm số round trip.

Tuy nhiên, batch lớn cũng có rủi ro:

- Chiếm nhiều bộ nhớ trong ứng dụng.
- Payload vượt giới hạn request/lệnh.
- Timeout và retry tốn hơn.
- Tạo tải ghi đột biến ảnh hưởng các truy vấn phục vụ người dùng.
- Làm khó xác định trạng thái từng mục khi có lỗi.
- Có thể khiến các partition hoặc một document “nóng” chịu cạnh tranh ghi.

Vì vậy, **batch size tối ưu phụ thuộc workload**, không có một con số cố định cho mọi database hoặc mọi kiểu document.

## 3. Các loại thao tác trong bulk MongoDB

MongoDB `collection.bulkWrite()` nhận danh sách thao tác. Những kiểu thường gặp:

| Operation | Ý nghĩa | Điểm chú ý |
| --- | --- | --- |
| `insertOne` | Thêm một document | Có thể lỗi duplicate key |
| `updateOne` | Sửa một document khớp filter | Có thể không khớp mà không phát sinh write error |
| `updateMany` | Sửa nhiều document | Một operation có thể ảnh hưởng nhiều bản ghi |
| `replaceOne` | Thay thế một document | Có thể làm mất field không xuất hiện trong replacement |
| `deleteOne` | Xóa một document | Không khớp có thể chỉ là deletedCount = 0 |
| `deleteMany` | Xóa mọi document khớp filter | Cần bảo vệ phạm vi và rủi ro xóa nhiều |

Hai tùy chọn xử lý lỗi cơ bản:

- **`ordered: true`:** thực hiện theo thứ tự thao tác và **dừng khi gặp lỗi ghi**. Đó thường là chế độ mặc định của bulk write.
- **`ordered: false`:** tiếp tục cố xử lý các thao tác khác dù có mục lỗi; **không bảo đảm thứ tự thực thi ban đầu**.

Chế độ ordered không đồng nghĩa transaction. Những mục đã ghi thành công trước khi lỗi **vẫn có thể nằm trong database**.

## 4. Thực hành 1: tạo dữ liệu minh họa

Dùng `mongosh`, tạo database riêng `nosql_bulk_lab`.

> Script dưới đây xóa collection `orders` trong **database thực hành** để mỗi lần thử có trạng thái giống nhau. Không chạy trên dữ liệu sản xuất.

~~~javascript
const lab = db.getSiblingDB("nosql_bulk_lab");

function seedOrders() {
  lab.orders.drop();

  lab.orders.insertMany([
    {
      _id: "order-A",
      customerId: "c1",
      status: "PENDING",
      totalAmount: 100000
    },
    {
      _id: "order-C",
      customerId: "c3",
      status: "PENDING",
      totalAmount: 300000
    }
  ]);
}

function makeOperations() {
  return [
    {
      insertOne: {
        document: {
          _id: "order-B",
          customerId: "c2",
          status: "PENDING",
          totalAmount: 200000
        }
      }
    },
    {
      insertOne: {
        // Cố ý trùng _id để phát sinh lỗi duplicate key.
        document: {
          _id: "order-A",
          customerId: "c1",
          status: "PENDING",
          totalAmount: 999999
        }
      }
    },
    {
      updateOne: {
        filter: {
          _id: "order-C",
          status: "PENDING"
        },
        update: {
          $set: { status: "PAID" }
        }
      }
    }
  ];
}
~~~

Một collection MongoDB thông thường có chỉ mục duy nhất mặc định trên `_id`. Vì `order-A` đã tồn tại, operation thứ hai sẽ bị từ chối vì trùng khóa.

Ta dùng cùng ba thao tác cho hai lần thử, chỉ thay đổi `ordered`.

## 5. Thực hành 2: ordered bulk và thao tác chưa được thử

~~~javascript
seedOrders();

try {
  const result = lab.orders.bulkWrite(
    makeOperations(),
    { ordered: true }
  );

  printjson(result);
} catch (error) {
  print("Ordered bulk failed:", error.message);
}

printjson(
  lab.orders.find(
    {},
    { _id: 1, status: 1, totalAmount: 1 }
  )
  .sort({ _id: 1 })
  .toArray()
);
~~~

Với lỗi trùng khóa dự kiến, đường đi là:

~~~text
Operation 0: INSERT order-B         ✓ thành công
Operation 1: INSERT order-A         ✗ duplicate key
Operation 2: UPDATE order-C         — chưa thực hiện
~~~

| Document | Kết quả dự kiến sau ordered bulk |
| --- | --- |
| `order-A` | Vẫn là đơn cũ, totalAmount = 100000 |
| `order-B` | Đã được tạo |
| `order-C` | Vẫn PENDING |

**Điểm quan trọng:** operation 0 đã hoàn tất **không bị rollback** chỉ vì operation 1 lỗi. Operation 2 không được thử vì ordered bulk đã dừng.

Nếu client mất kết nối hoặc server gặp lỗi khác ngoài duplicate key mô tả ở trên, phải kiểm tra lại dữ liệu trước khi kết luận trạng thái. Bảng này là **kết quả dự kiến của kịch bản thực hành**, không phải lời cam kết cho mọi loại lỗi.

## 6. Thực hành 3: unordered bulk và nhiều kết quả trong cùng request

~~~javascript
seedOrders();

try {
  const result = lab.orders.bulkWrite(
    makeOperations(),
    { ordered: false }
  );

  printjson(result);
} catch (error) {
  print("Unordered bulk reported errors:", error.message);
}

printjson(
  lab.orders.find(
    {},
    { _id: 1, status: 1, totalAmount: 1 }
  )
  .sort({ _id: 1 })
  .toArray()
);
~~~

Đối với ba thao tác độc lập theo document, đường đi thường là:

~~~text
Operation 0: INSERT order-B         ✓ thành công
Operation 1: INSERT order-A         ✗ duplicate key
Operation 2: UPDATE order-C         ✓ thành công
~~~

| Document | Kết quả dự kiến sau unordered bulk |
| --- | --- |
| `order-A` | Không bị thay đổi |
| `order-B` | Được tạo |
| `order-C` | Được chuyển sang PAID |

Unordered có thể giúp **xử lý tối đa các mục độc lập** thay vì dừng toàn batch ở lỗi đầu tiên.

Nhưng không được mặc định operation thứ nhất luôn được thực thi trước operation thứ hai. Ví dụ nếu một operation tạo đơn và một operation khác cập nhật chính đơn đó, `ordered:false` không phải lựa chọn an toàn khi update phụ thuộc insert.

## 7. Partial success: phân loại từng mục như thế nào?

Một lệnh bulk có thể chứa **nhiều trạng thái kết quả**. Chỉ gắn nhãn “thành công” hoặc “thất bại” cho toàn request thường làm mất thông tin quan trọng.

| Trạng thái mục | Ý nghĩa | Hành động kế tiếp |
| --- | --- | --- |
| **APPLIED** | Đã xác nhận hiệu ứng mong muốn được áp dụng | Ghi checkpoint hoàn tất |
| **NO_MATCH** | Update/delete hợp lệ nhưng không tìm được document khớp | Kiểm tra điều kiện nghiệp vụ |
| **REJECTED** | Bị từ chối rõ ràng, ví dụ duplicate key/validation | Sửa input hoặc xử lý conflict |
| **NOT_ATTEMPTED** | Chưa được thử do ordered bulk dừng sớm | Đưa vào hàng chờ xử lý phù hợp |
| **UNKNOWN** | Không biết chắc do timeout/network/write concern | Đối soát trước khi retry |
| **PENDING_RETRY** | Được xác định nên thử lại sau | Retry có backoff và idempotency |

Trong ordered bulk ví dụ, ta có thể phân loại:

~~~text
row-001 / insert B  -> APPLIED
row-002 / insert A  -> REJECTED
row-003 / update C  -> NOT_ATTEMPTED
~~~

Nhưng khi client chỉ thấy **timeout**, không được tự gán ba trạng thái này theo giả định. Một số operation có thể đã được ghi mà phản hồi chưa tới. Khi đó cần trạng thái **UNKNOWN**.

### 7.1. Không khớp filter không có nghĩa server bị lỗi

~~~javascript
lab.orders.updateOne(
  {
    _id: "order-C",
    status: "PENDING"
  },
  {
    $set: { status: "PAID" }
  }
);
~~~

Nếu `order-C` đã ở trạng thái PAID thì `matchedCount` có thể bằng 0. Operation có thể **được xử lý hợp lệ** nhưng không có document phù hợp.

Lý do có thể là:

1. Document không tồn tại.
2. Document thuộc tenant khác.
3. Trạng thái đã được thay đổi trước đó.
4. Version/precondition khác dự kiến.

Do đó, phải kiểm tra **trạng thái cuối và hợp đồng nghiệp vụ**, không chỉ số count.

### 7.2. Ý nghĩa các count trong BulkWriteResult

Thông tin phản hồi thành công thường có:

- `insertedCount`: số insert được xác nhận.
- `matchedCount`: số document khớp với các update.
- `modifiedCount`: số document thực sự thay đổi.
- `deletedCount`: số document đã xóa.
- `upsertedCount` và `upsertedIds`: các upsert đã tạo document mới.

**Không cộng các con số này rồi gọi là “số input thành công”.** Một `updateMany` có thể sửa hàng nghìn document dù là **một operation**; một `updateOne` có thể matched nhưng không modified; một upsert có thể tạo document mới.

Khi báo cáo theo dòng CSV hay item API, nên giữ **inputId riêng** để đối chiếu từng operation với dữ liệu nguồn.

## 8. Các nhóm lỗi và cách xử lý phù hợp

| Nhóm lỗi | Ví dụ | Có nên retry nguyên payload? |
| --- | --- | --- |
| **Duplicate key** | Hai input cùng `_id` | Không tự động; cần xác định retry hay conflict |
| **Validation** | Thiếu field bắt buộc, kiểu không hợp lệ | Không, phải sửa dữ liệu |
| **Kích thước** | Document/request vượt giới hạn | Không; cần đổi mô hình/chia dữ liệu |
| **Điều kiện ghi không khớp** | Version hoặc status khác | Không mặc định; tải lại trạng thái |
| **Throttling/tạm quá tải** | Hết quota thông lượng hoặc resource | Có thể retry với backoff |
| **Write concern** | Ghi có thể đã diễn ra nhưng chưa đạt xác nhận | Phải đối soát |
| **Network timeout** | Mất kết nối sau khi gửi | Trạng thái có thể UNKNOWN |
| **Lỗi code/toán tử** | Update expression sai | Sửa code trước |

Lỗi duplicate key là ví dụ dễ hiểu. Nó có thể nghĩa là:

- **Cùng một input gửi lại sau khi lần trước đã chèn thành công**: trạng thái đích đã đạt.
- **Một input khác dùng cùng business key nhưng payload khác**: xung đột thực sự, không được bỏ qua.

Vì vậy, không nên viết `catch duplicate key => success` mà không so sánh dữ liệu/operation ID.

### 8.1. Lỗi theo index của thao tác

Một số driver cung cấp danh sách write errors có **index, code và message**. Cấu trúc exception cụ thể phụ thuộc phiên bản client. Một ví dụ `mongosh` có thể dùng:

~~~javascript
seedOrders();

try {
  lab.orders.bulkWrite(
    makeOperations(),
    { ordered: false }
  );
} catch (error) {
  print("Error name:", error.name);
  print("Message:", error.message);

  if (Array.isArray(error.writeErrors)) {
    for (const itemError of error.writeErrors) {
      printjson({
        index: itemError.index,
        code: itemError.code,
        message: itemError.errmsg || itemError.message
      });
    }
  }
}
~~~

MongoDB thường trả code **11000** cho duplicate key. Trong production, cần dựa vào **API lỗi chính thức của driver đang sử dụng**, không phụ thuộc một hình dạng error object duy nhất ở mọi phiên bản.

Với lỗi xác nhận ghi hoặc mất kết nối, việc một operation không xuất hiện trong `writeErrors` **không tự chứng minh operation đó đã commit**.

## 9. Ordered và unordered không nên chọn chỉ dựa vào tốc độ

| Tình huống | Chiến lược đáng cân nhắc |
| --- | --- |
| Nhiều insert độc lập, muốn xử lý tối đa dù vài bản ghi sai | Unordered |
| Mục sau cần kết quả của mục trước | Ordered, hoặc thiết kế lại thành transaction/atomic update |
| Muốn dừng ngay khi có lỗi dữ liệu đầu tiên | Ordered |
| Muốn gom nhiều lỗi dữ liệu thành báo cáo sửa một lượt | Unordered |
| Cập nhật nhiều field trong **cùng document** | Một update atomic thay vì nhiều operation |
| Ghi nhiều document phải cùng thành công | Transaction hoặc cơ chế bất biến nghiệp vụ phù hợp |
| Import hàng triệu bản ghi, chấp nhận một số item bị từ chối | Batch độc lập + kết quả từng mục |
| Chuyển tiền giữa nhiều tài khoản | Không chỉ bulk; cần thiết kế giao dịch/ledger |

### 9.1. Vì sao ordered bulk không đủ để chuyển tiền?

~~~text
1. Trừ 100.000 khỏi ví A
2. Cộng 100.000 vào ví B
~~~

Nếu bước 1 thành công và bước 2 lỗi, ordered bulk có thể để lại ví A bị trừ. **Ordered không rollback hiệu ứng đã xảy ra**. Nghiệp vụ phải dùng transaction trong phạm vi hệ hỗ trợ hoặc cơ chế ledger/saga có kiểm soát nhất quán.

## 10. Chia batch để cân bằng throughput và khôi phục lỗi

Một job có 100.000 item có thể được chia thành 100 batch, mỗi batch 1.000 item. Tuy nhiên số 1.000 chỉ là **tham số thử**, không phải mức tối ưu phổ quát.

Ba giới hạn phải cùng xét:

1. **Số operation tối đa** của API/driver/server.
2. **Kích thước byte** của batch và từng document.
3. **Thời gian xử lý**, memory, CPU, disk và replication.

Một batch 1.000 record 100 byte khác rất xa 1.000 record 100 KB. Driver có thể phải **chia một bulk lớn thành nhiều batch nội bộ**, nhưng điều đó không tạo rollback xuyên các batch.

### 10.1. Hàm chia lô đơn giản

~~~javascript
function* chunked(items, batchSize) {
  if (!Number.isInteger(batchSize) || batchSize <= 0) {
    throw new Error("batchSize must be a positive integer");
  }

  for (let i = 0; i < items.length; i += batchSize) {
    yield items.slice(i, i + batchSize);
  }
}

const ops = [
  { insertOne: { document: { _id: "x1" } } },
  { insertOne: { document: { _id: "x2" } } },
  { insertOne: { document: { _id: "x3" } } }
];

for (const batch of chunked(ops, 2)) {
  print("Batch size:", batch.length);
}
~~~

Đây chỉ là minh họa chia theo **số mục**. Với dữ liệu lớn, nên đọc nguồn theo luồng, giữ bộ đệm giới hạn và bổ sung tính tổng byte khi nhóm.

### 10.2. Tại sao batch quá lớn có thể kém hơn?

- Một item lỗi khiến việc phân loại và retry khó hơn.
- Timeout gây nhiều item UNKNOWN.
- Gửi lại toàn bộ batch có thể tạo tải dư thừa.
- Client giữ dữ liệu và response lâu hơn.
- Database chịu burst gây ảnh hưởng truy vấn trực tuyến.

Khi thử nghiệm, hãy so sánh batch 50/250/1.000 hoặc những mức phù hợp với sản phẩm; đo **throughput item thành công**, p95 latency, retries, CPU, disk và queue backlog.

## 11. Idempotency: điều kiện cốt lõi để retry an toàn

**Idempotent** có nghĩa là áp dụng lại cùng một logical operation vẫn đưa hệ tới **trạng thái nghiệp vụ tương đương với một lần áp dụng**.

| Thao tác | Retry có thể gây gì? | Bảo vệ |
| --- | --- | --- |
| Insert với `_id` ổn định | Lần lặp báo duplicate key | Đọc và so payload theo key |
| Insert với ID mới mỗi lần | Tạo nhiều bản ghi trùng nghiệp vụ | Business key / operation ID cố định |
| `$set` cùng giá trị | Thường tạo cùng trạng thái | Kết hợp version nếu có concurrency |
| `$inc` | **Cộng/trừ nhiều lần** | Operation ID, ledger hoặc transaction |
| `$push` | Thêm phần tử trùng | Khóa phần tử, điều kiện hoặc idempotency |
| `$addToSet` | Không thêm lại giá trị đã có | Vẫn cần định nghĩa equality |
| Delete theo `_id` | Lần sau deletedCount = 0 | Diễn giải trạng thái đích theo hợp đồng |
| Upsert thiếu ràng buộc unique | Hai writer có thể tạo bản ghi trùng | Unique index đúng phạm vi |

### 11.1. Upsert với business key ổn định

~~~javascript
lab.orders.updateOne(
  { _id: "external-order-001" },
  {
    $setOnInsert: {
      customerId: "c100",
      status: "PENDING",
      totalAmount: 150000,
      source: "external-system"
    }
  },
  { upsert: true }
);
~~~

Nếu record đã tồn tại, `$setOnInsert` không ghi đè giá trị hiện tại. Retry thường dễ an toàn hơn một insert có ID ngẫu nhiên mới mỗi lần.

Nhưng nếu một record trùng ID có nội dung **khác payload mong muốn**, không được coi đó là thành công. Có thể lưu `sourceId`, `operationId` hoặc `payloadHash` để đối chiếu.

### 11.2. Update có điều kiện theo version

~~~javascript
lab.orders.updateOne(
  {
    _id: "order-C",
    status: "PENDING",
    version: 7
  },
  {
    $set: { status: "PAID" },
    $inc: { version: 1 }
  }
);
~~~

Lần đầu có thể đổi version 7 → 8; retry với expected version 7 sẽ không khớp. Nhưng **matchedCount = 0** có thể do lần đầu thành công hoặc do một người khác đã sửa record. Muốn xác nhận một logical operation phải lưu/đối soát operation ID hoặc trạng thái và lịch sử đáng tin cậy.

### 11.3. Thao tác $inc không thể retry mù

Giả sử một thanh toán làm giảm số dư:

~~~javascript
lab.accounts.updateOne(
  { _id: "wallet-A" },
  { $inc: { balance: -100000 } }
);
~~~

Nếu request timeout sau khi server đã áp dụng, gửi lại sẽ trừ thêm 100.000. Đối với tiền, phải có **paymentId/transactionId** và cơ chế ghi nhận đã xử lý trong cùng một phạm vi nhất quán với số dư hoặc ledger. BulkWrite không tự bảo đảm exactly-once cho hiệu ứng nghiệp vụ này.

## 12. Write concern và kết quả chưa chắc chắn

Bốn tình huống cần phân biệt:

- **Write error:** server từ chối thao tác, ví dụ duplicate key hoặc schema validation.
- **Write concern error:** việc ghi có thể đã xảy ra nhưng chưa đạt mức xác nhận mong muốn trước hạn.
- **Network error/timeout:** client không biết server đã nhận hoặc thực thi đến đâu.
- **Không khớp filter:** thao tác được xử lý nhưng không thay đổi record; thường không phải write error.

Khi client timeout, có thể xảy ra:

~~~text
A. Lệnh chưa tới server
B. Lệnh đã tới và xử lý một phần
C. Lệnh đã hoàn tất nhưng response bị mất
~~~

Vì client không biết chắc, phải dùng trạng thái **UNKNOWN** và đối soát, không suy rằng tất cả chưa được ghi.

Một số driver hỗ trợ **retryable writes** trong điều kiện cụ thể, nhưng điều đó không tự cho phép ứng dụng retry **toàn job** hoặc thao tác gọi sang dịch vụ ngoài mà không có thiết kế idempotent.

Nếu dùng chế độ ghi **không được xác nhận** (*unacknowledged write*), ứng dụng cũng không thể dựa vào result chi tiết để khẳng định từng item đã được lưu. Với dữ liệu cần đối soát chặt, mức xác nhận và độ bền phải theo yêu cầu nghiệp vụ.

## 13. Transaction khi phải cùng commit hoặc cùng abort

Ví dụ một đơn cần:

1. Đánh dấu thanh toán thành công.
2. Giảm số lượng hàng còn lại.
3. Ghi nhận một ledger entry.

Nếu nghiệp vụ yêu cầu **tất cả cùng thành công** trong một phạm vi được database hỗ trợ, cần transaction hoặc kiến trúc bảo toàn bất biến tương đương. Ordered bulk **không đủ**.

Ví dụ minh họa transaction MongoDB:

~~~javascript
const session = lab.getMongo().startSession();

try {
  session.startTransaction();

  const txDb = session.getDatabase("nosql_bulk_lab");

  const result = txDb.orders.bulkWrite(
    [
      {
        updateOne: {
          filter: { _id: "order-A", status: "PENDING" },
          update: { $set: { status: "PAID" } }
        }
      },
      {
        updateOne: {
          filter: { _id: "order-C", status: "PENDING" },
          update: { $set: { status: "PAID" } }
        }
      }
    ],
    { ordered: true }
  );

  // Minh họa: phải kiểm tra các điều kiện trước commit.
  if (result.matchedCount !== 2) {
    throw new Error("At least one order was not PENDING");
  }

  session.commitTransaction();
} catch (error) {
  session.abortTransaction();
  throw error;
} finally {
  session.endSession();
}
~~~

Đây là ví dụ về **ranh giới giao dịch**, chưa phải trình xử lý transaction production hoàn chỉnh. Ứng dụng thực cần chiến lược retry cho lỗi tạm thời, trạng thái commit không chắc chắn, hạn mức giao dịch và bảo vệ chống xử lý lại tác vụ ngoài database.

**Transaction nhiều document có chi phí**, không nên bao trùm cả file nhập hàng triệu bản ghi chỉ để tránh thiết kế checkpoint. Thường nên định nghĩa transaction theo **đơn vị nghiệp vụ** (ví dụ một đơn và những thay đổi liên quan), còn toàn job sử dụng nhiều đơn vị xử lý độc lập và báo cáo từng phần.

## 14. Java MongoDB Driver: bulkWrite và thông tin lỗi

Trong Java synchronous driver, một collection nhận danh sách `WriteModel<Document>`. Ví dụ sau giả định `collection` là `MongoCollection<Document>` đã được tạo từ một kết nối đến database thực hành.

~~~java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.bulk.BulkWriteError;
import com.mongodb.bulk.BulkWriteResult;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.InsertOneModel;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.WriteModel;
import org.bson.Document;

import java.util.List;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.set;

public class BulkImportExample {
    public static void write(MongoCollection<Document> collection) {
        List<WriteModel<Document>> operations = List.of(
            new InsertOneModel<>(
                new Document("_id", "order-B")
                    .append("status", "PENDING")
            ),
            new InsertOneModel<>(
                new Document("_id", "order-A")
                    .append("status", "PENDING")
            ),
            new UpdateOneModel<>(
                eq("_id", "order-C"),
                set("status", "PAID")
            )
        );

        try {
            BulkWriteResult result = collection.bulkWrite(
                operations,
                new BulkWriteOptions().ordered(false)
            );

            System.out.println(
                "Inserted=" + result.getInsertedCount()
                + ", Matched=" + result.getMatchedCount()
                + ", Modified=" + result.getModifiedCount()
            );
        } catch (MongoBulkWriteException ex) {
            for (BulkWriteError err : ex.getWriteErrors()) {
                System.out.println(
                    "Operation index=" + err.getIndex()
                    + ", code=" + err.getCode()
                    + ", message=" + err.getMessage()
                );
            }

            if (ex.getWriteConcernError() != null) {
                System.out.println(
                    "Write concern issue: "
                    + ex.getWriteConcernError().getMessage()
                );
            }

            // Phân loại kết quả, đối soát với trạng thái thực tế
            // và retry chỉ những logical operations phù hợp.
        }
    }
}
~~~

Các class và accessor tương ứng với MongoDB Java sync driver; chi tiết exception có thể thay đổi theo phiên bản. Ngoài `MongoBulkWriteException`, hệ xử lý cần xét **network error và những loại exception khác** để tránh bỏ sót trạng thái UNKNOWN.

### 14.1. Lưu ánh xạ operation index → inputId

~~~text
operations[0] -> row-001 / order-B
operations[1] -> row-002 / order-A
operations[2] -> row-003 / order-C
~~~

Khi kết quả cho biết lỗi ở index 1, ứng dụng xác định **row-002** cần xử lý. Để không phụ thuộc chỉ số tạm trong nhiều tầng chia batch, nên dùng `inputId` và `operationId` ổn định trong dữ liệu trạng thái job.

Không ghi nguyên payload nhạy cảm vào log lỗi nếu không có nhu cầu và quyền phù hợp.

## 15. API nhập liệu phải trả trạng thái từng mục

Một request giả định:

~~~json
{
  "jobId": "import-01",
  "items": [
    {
      "inputId": "row-001",
      "orderId": "order-B",
      "action": "CREATE"
    },
    {
      "inputId": "row-002",
      "orderId": "order-A",
      "action": "CREATE"
    },
    {
      "inputId": "row-003",
      "orderId": "order-C",
      "action": "MARK_PAID"
    }
  ]
}
~~~

Một kết quả ứng dụng có thể được thiết kế như:

~~~json
{
  "jobId": "import-01",
  "state": "COMPLETED_WITH_ERRORS",
  "items": [
    { "inputId": "row-001", "state": "APPLIED" },
    {
      "inputId": "row-002",
      "state": "REJECTED",
      "code": "DUPLICATE_BUSINESS_KEY"
    },
    { "inputId": "row-003", "state": "APPLIED" }
  ]
}
~~~

Đây là **schema API minh họa**, không phải response trực tiếp của MongoDB. Với ordered bulk, row-003 sẽ là `NOT_ATTEMPTED` trong kịch bản lỗi đã nêu. Với kết quả network timeout, một số mục có thể là `UNKNOWN`.

Một API có thể dùng HTTP `200` kèm kết quả từng mục, hoặc `202 Accepted` nếu công việc chạy dưới dạng job, hoặc cách trình bày phù hợp khác. **HTTP thành công không chứng minh mọi item thành công**, đặc biệt với API bulk.

### 15.1. Trạng thái job khác trạng thái mục

~~~text
QUEUED -> RUNNING
           |
           +--> COMPLETED
           +--> COMPLETED_WITH_ERRORS
           +--> RECOVERING (còn UNKNOWN/PENDING_RETRY)
           +--> CANCELLED/FAILED theo hợp đồng
~~~

Không được đánh dấu job hoàn tất chỉ vì **đã gửi hết batch**. Cần biết mục nào đã được xác nhận và mục nào vẫn chờ đối soát.

Với job chứa một triệu mục, không cần gửi cả triệu trạng thái trong một response. Có thể trả `jobId`, cung cấp endpoint tiến độ và báo cáo lỗi theo trang hoặc file riêng.

## 16. Checkpoint và khôi phục sau worker crash

Sai lầm thường gặp:

~~~text
Worker đọc 10.000 dòng CSV
Worker ghi thành công 7.000 dòng
Worker lưu checkpoint: "đã đọc xong dòng 10.000"
Worker crash

Restart từ dòng 10.001 => bỏ sót 3.000 dòng.
~~~

Checkpoint phải phản ánh **mục đã đạt trạng thái cuối**, không chỉ số mục đã đọc hay đã gửi.

### 16.1. Luồng xử lý gợi ý

~~~mermaid
flowchart TD
    A[Đọc input, gắn ID ổn định] --> B[Validate và chuẩn hóa]
    B --> C[Chia batch có giới hạn số mục/byte]
    C --> D[Gửi bulkWrite]
    D --> E{Kết quả xác định?}
    E -->|Có| F[Phân loại từng input]
    E -->|Không| G[Đánh dấu UNKNOWN]
    G --> H[Đối soát theo business key và operationId]
    H --> F
    F --> I{Đạt trạng thái đích?}
    I -->|Có| J[Checkpoint APPLIED]
    I -->|Không| K[REJECTED hoặc PENDING_RETRY]
    K --> L[Retry có điều kiện và backoff]
    L --> C
~~~

### 16.2. Đối soát trạng thái UNKNOWN

Với một input:

~~~text
inputId       = row-042
businessKey   = external-order-042
operationId   = import-01:row-042
payloadHash   = sha256(normalizedPayload)
~~~

Sau timeout:

- Document tồn tại và chứa `operationId` hoặc payload/hash phù hợp → có bằng chứng thao tác đã áp dụng.
- Không tồn tại → cần xác định liệu lệnh cũ còn có khả năng hoàn tất; retry với khóa duy nhất và thao tác idempotent.
- Tồn tại cùng khóa nhưng payload khác → conflict, không ghi đè tùy tiện.
- Bản ghi có version mới hơn → cần đánh giá nghiệp vụ trước khi retry.

**Một lần đọc ngay sau timeout không luôn chứng minh server sẽ không ghi sau thời điểm đọc.** Cơ chế unique key, conditional write và idempotency vẫn cần được bảo vệ ở tầng database.

### 16.3. Ghi checkpoint cũng có thể thất bại

Nếu dữ liệu nghiệp vụ đã ghi nhưng hệ thống lưu `job_items` bị lỗi, worker sẽ chạy lại mục. Vì vậy, mỗi logical operation vẫn phải an toàn khi retry. Nếu cần trạng thái job và dữ liệu nghiệp vụ **cùng nguyên tử**, có thể cân nhắc transaction hoặc thiết kế ghi nhận sự kiện trong cùng ranh giới nhất quán.

## 17. Không chỉ insert: updateMany, replace và delete

### 17.1. UpdateMany có thể ảnh hưởng nhiều document

~~~javascript
lab.orders.bulkWrite([
  {
    updateOne: {
      filter: { _id: "order-A" },
      update: { $set: { status: "PAID" } }
    }
  },
  {
    updateMany: {
      filter: { status: "PENDING" },
      update: { $set: { needsReview: true } }
    }
  }
], { ordered: true });
~~~

Có hai operation nhưng `updateMany` có thể sửa nhiều document. Do đó `modifiedCount` **không tương đương số operation thành công**.

Với unordered, nếu operation sau phụ thuộc trạng thái được thay ở operation trước, kết quả có thể không như dự định.

### 17.2. ReplaceOne có thể làm mất field

~~~javascript
lab.orders.replaceOne(
  { _id: "order-A" },
  {
    _id: "order-A",
    customerId: "c1",
    status: "PAID"
  }
);
~~~

Nếu document cũ có `totalAmount`, replacement không giữ field đó nếu không đưa vào nội dung thay thế. Bulk importer phải biết đang thực hiện **replace toàn bộ** hay chỉ **cập nhật một phần**. Với vài field, `$set` thường ít rủi ro hơn.

### 17.3. DeleteMany và soft delete

~~~javascript
lab.orders.deleteMany({
  status: "CANCELLED",
  createdAt: {
    $lt: new Date("2025-01-01T00:00:00Z")
  }
});
~~~

Một operation `deleteMany` có thể xóa rất nhiều document. Nếu yêu cầu phải **soft delete**, không được thay bằng hard delete cho tiện bulk. Nếu cần báo cáo kết quả theo từng record, một lệnh xóa rộng cũng không cung cấp danh sách riêng từng item như các deleteOne có ID.

## 18. Batch trong các hệ NoSQL khác

Chữ “batch” có các bảo đảm khác nhau tùy sản phẩm.

### 18.1. DynamoDB BatchWriteItem

`BatchWriteItem` cho phép nhóm thao tác **Put/Delete**, có giới hạn số mục và payload; theo khả năng API phổ biến, tối đa **25 yêu cầu Put/Delete** trong một request. Những điểm cần nhớ:

- Không hỗ trợ UpdateItem tùy ý trong API này.
- Put có thể ghi đè item hiện có; các điều kiện phức tạp không được biểu diễn như PutItem có ConditionExpression.
- **Không phải transaction toàn batch**.
- Response có thể trả danh sách **`UnprocessedItems`** khi một số mục chưa được xử lý.
- Nên retry **những mục unprocessed**, với exponential backoff và jitter.

Ví dụ response minh họa:

~~~json
{
  "UnprocessedItems": {
    "Orders": [
      {
        "PutRequest": {
          "Item": {
            "PK": { "S": "ORDER#42" },
            "status": { "S": "PENDING" }
          }
        }
      }
    ]
  }
}
~~~

Dữ liệu trong `UnprocessedItems` chưa được xử lý trong lần request tương ứng. Khi toàn request bị lỗi hoặc client mất kết nối, tình huống không chắc chắn phải được xử lý riêng.

Nếu cần nhiều thay đổi cùng atomic, DynamoDB có **transaction API** với phạm vi và hạn mức khác.

### 18.2. Elasticsearch / OpenSearch Bulk API

Một request HTTP có thể thành công nhưng **một vài item bên trong lỗi**. Mẫu response:

~~~json
{
  "errors": true,
  "items": [
    {
      "index": {
        "_id": "p1",
        "status": 201
      }
    },
    {
      "index": {
        "_id": "p2",
        "status": 429,
        "error": {
          "type": "es_rejected_execution_exception"
        }
      }
    }
  ]
}
~~~

Cần kiểm tra `errors` và trạng thái **từng item**. Item lỗi mapping thường phải được sửa; lỗi throttling có thể thử lại với backoff. Không thể chỉ nhìn HTTP `200` để kết luận toàn bộ dữ liệu đã được index.

### 18.3. Redis pipeline

Redis pipelining giảm round trip bằng cách gửi nhiều command không chờ phản hồi từng lệnh. Nhưng **pipeline không tự atomic**.

~~~text
SET key:a 1       -> thành công
INCR key:b        -> có thể lỗi nếu key:b có kiểu không phù hợp
SET key:c 3       -> thành công
~~~

Redis `MULTI/EXEC` có cơ chế transaction riêng nhưng không cung cấp rollback hiệu ứng của mọi command nếu một command phát sinh runtime error theo cách nhiều người quen với transaction SQL. Cần hiểu ngữ nghĩa của Redis trước khi dùng cho bất biến nghiệp vụ.

### 18.4. Cassandra CQL BATCH

Cassandra có `BEGIN BATCH ... APPLY BATCH` với các dạng logged/unlogged. Nó **không phải lựa chọn mặc định để tăng tốc nhập dữ liệu độc lập**:

- Logged batch có cơ chế phục hồi nhằm bảo đảm những mutation trong batch được áp dụng cuối cùng theo bảo đảm của Cassandra, **không có nghĩa isolation đầy đủ như giao dịch SQL**.
- Unlogged batch có ngữ nghĩa và bảo đảm khôi phục khác logged batch.
- Batch xuyên nhiều partition có thể tăng chi phí điều phối, không nhất thiết nhanh hơn gửi các thao tác phù hợp qua driver.

Thiết kế cần dựa trên partition key, consistency level, topology, loại batch và tài liệu phiên bản đang chạy.

## 19. Đo hiệu năng bulk đúng cách

Những chỉ số có ích:

| Chỉ số | Diễn giải |
| --- | --- |
| **Applied items/second** | Số mục **đạt trạng thái đích** trên mỗi giây |
| **Latency p50/p95/p99** | Phân bố độ trễ, gồm cả phần đuôi |
| **Error rate** | Tỷ lệ mục bị từ chối |
| **Retry rate** | Tỷ lệ phải gửi lại |
| **UNKNOWN rate** | Số mục chưa rõ trạng thái sau lỗi |
| **Queue/backlog** | Mục còn chờ xử lý, độ trễ của job |
| **CPU, RAM, disk, network** | Tài nguyên client và database |
| **Index/replication lag** | Ảnh hưởng lên những đường đọc khác |
| **Recovery time** | Thời gian resume sau crash |

Một benchmark báo 20.000 operations/giây nhưng 30% phải retry và 10% bị từ chối **không có nghĩa đã nhập 20.000 bản ghi hợp lệ mỗi giây**.

### 19.1. Test theo nhiều mức batch và concurrency

| Lượt | Batch size | Số worker đồng thời | Câu hỏi |
| --- | ---: | ---: | --- |
| A | 50 | 1 | Overhead request lớn đến đâu? |
| B | 250 | 1 | Tăng throughput được bao nhiêu? |
| C | 1.000 | 1 | Batch lớn có làm tăng tail latency? |
| D | 250 | 4 | Database có chịu được ghi đồng thời? |
| E | 1.000 | 4 | Có xảy ra throttling/hot partition? |

Đây là các **điểm thử đề xuất để quan sát**, không phải giá trị tối ưu mặc định. Cần dùng dữ liệu đại diện: document lớn/nhỏ, lỗi dữ liệu, keys nóng, index thực tế, lượng đọc đồng thời và tải nền.

### 19.2. Không chỉ kiểm tra tốc độ

Ngoài latency phải kiểm tra:

- Không thiếu record.
- Không tạo bản ghi trùng nghiệp vụ.
- Không tăng số dư/số lượng hai lần khi retry.
- Không mất field vì replace sai.
- Không bỏ qua những mục sau lỗi ordered.
- Không đánh dấu job `COMPLETED` khi còn UNKNOWN.
- Không làm API hiện hành vượt SLO do bulk chiếm tài nguyên.

Một hệ rất nhanh nhưng ghi thiếu hoặc ghi trùng là **không đạt yêu cầu**.

## 20. Các bẫy thiết kế thường gặp

### 20.1. Coi ordered là all-or-nothing

Ordered dừng khi lỗi nhưng không rollback các thao tác trước. Nếu phải cùng commit/abort, xem transaction hoặc cơ chế nghiệp vụ tương đương.

### 20.2. Retry cả batch chứa $inc

Có mục đã được cộng trước timeout nên retry lại làm cộng hai lần. Dùng operation ID hoặc trạng thái đích có điều kiện.

### 20.3. Dùng unordered cho thao tác phụ thuộc

Một update cần document vừa insert có thể chạy trước insert. Tách phụ thuộc hoặc dùng ordered/transaction có ranh giới phù hợp.

### 20.4. Thấy exception liền báo tất cả thất bại

Một số item đã được ghi trước lỗi. Phải phân loại per-item.

### 20.5. Thấy HTTP thành công liền báo tất cả item thành công

Bulk API có thể chứa lỗi ở cấp item. Luôn đọc result chi tiết.

### 20.6. Checkpoint theo số item đọc thay vì đã xác nhận

Worker crash rồi resume bỏ sót dữ liệu. Checkpoint theo trạng thái có thể chứng minh.

### 20.7. Chỉ lưu offset, không lưu input ID

Nguồn input đổi thứ tự, offset không còn đại diện những record trước đó. Cần snapshot/cursor đáng tin cậy và ID ổn định.

### 20.8. Batch quá lớn

Payload lớn, memory nhiều, timeout và retry tốn. Giới hạn cả số operation lẫn byte và concurrency.

### 20.9. Giữ toàn bộ input trong RAM

Nhập dữ liệu theo luồng và flush từng batch, tránh giữ hàng triệu document trong một mảng.

### 20.10. Không tính write concern và network uncertainty

Mất response không chứng minh chưa ghi. Dùng UNKNOWN, đối soát và retry idempotent.

### 20.11. Duplicate key luôn được coi là thành công

Duplicate có thể là retry hợp lệ **hoặc conflict thật**. Cần đối chiếu business key/payload.

### 20.12. Dùng transaction khổng lồ để thay logic phục hồi

Transaction dài tốn tài nguyên; chọn ranh giới atomic nhỏ theo nghiệp vụ và checkpoint cho toàn job.

### 20.13. Không lưu kết quả theo inputId

Khi import lỗi, không biết dòng nào cần sửa. Giữ ánh xạ inputId → trạng thái/error/attempts.

### 20.14. Hủy job rồi giả rằng tất cả đã rollback

Cancel chỉ có thể dừng phần chưa gửi; các batch đã commit có thể cần nghiệp vụ bù trừ riêng.

## 21. Bài tập thực hành

### Bài 1. Bulk có phải transaction?

Một job nhập 100.000 sản phẩm chia thành 100 batch. Có được kết luận toàn job atomic không?

**Gợi ý:** Không. Một job gồm nhiều batch không mặc nhiên atomic.

### Bài 2. Ordered bulk bị duplicate

Thao tác 0 insert B, thao tác 1 insert A bị trùng, thao tác 2 update C. Sau ordered bulk, B và C thế nào?

**Gợi ý:** B đã có thể được tạo; C chưa được thử.

### Bài 3. Unordered bulk

Với cùng ba thao tác độc lập và chỉ lỗi duplicate key, kết quả khác ra sao?

**Gợi ý:** Server cố thực hiện thao tác còn lại, nên C có thể chuyển PAID dù A bị từ chối.

### Bài 4. MatchedCount bằng 0

Update điều kiện `status:"PENDING"` không khớp. Đây chắc chắn là write error không?

**Gợi ý:** Không. Có thể document không tồn tại hoặc đã đổi trạng thái.

### Bài 5. Retry phép trừ số dư

Lệnh `$inc:{balance:-100}` timeout, client gửi lại, số dư bị trừ hai lần. Cần thay đổi thiết kế gì?

**Gợi ý:** Idempotency theo transaction ID/ledger, không retry mù.

### Bài 6. Duplicate key hợp lệ hay conflict?

Insert `external-order-01` báo duplicate key. Khi nào được coi là kết quả đã đạt, khi nào phải báo xung đột?

**Gợi ý:** Đối chiếu bản ghi hiện có với logical operation/payload mong muốn.

### Bài 7. Write concern error

Bulk nhận lỗi write concern. Có được gán mọi item là NOT_ATTEMPTED không?

**Gợi ý:** Không. Có thể một số ghi đã áp dụng; đánh dấu UNKNOWN và đối soát.

### Bài 8. DynamoDB UnprocessedItems

BatchWriteItem trả 5 trong 25 item ở `UnprocessedItems`. Nên xử lý thế nào?

**Gợi ý:** Retry những item chưa xử lý với backoff/jitter, không gửi lại cả 25 một cách tùy tiện.

### Bài 9. Chọn transaction

Tạo order, trừ tồn kho và ghi ledger phải cùng thành công. Dùng ordered bulk đã đủ không?

**Gợi ý:** Không. Cần transaction hoặc cơ chế nhất quán theo ranh giới nghiệp vụ.

### Bài 10. Checkpoint sai

Worker đọc 10.000 dòng, ghi được 7.500 rồi crash; checkpoint lại ghi 10.000. Hậu quả?

**Gợi ý:** 2.500 dòng có thể bị bỏ sót. Chỉ checkpoint những trạng thái đã xác nhận.

### Bài 11. Thiết kế API

Hãy tạo response cho bốn input: hai APPLIED, một REJECTED vì duplicate key và một UNKNOWN do timeout.

**Gợi ý:** Dùng `jobId`, trạng thái job `RECOVERING` khi còn UNKNOWN, cùng danh sách item theo `inputId`.

### Bài 12. Đo thông lượng

Benchmark báo 10.000 operations/giây nhưng 25% retry và 5% bị từ chối. Có thể khẳng định 10.000 bản ghi hợp lệ/giây không?

**Gợi ý:** Không; cần đo số mục cuối cùng đạt trạng thái đích mỗi giây, chi phí retry và lỗi.

## 22. Quy trình áp dụng cho một job bulk NoSQL

Khi xây một chức năng ghi hàng loạt, có thể quyết định theo thứ tự:

1. **Định nghĩa đơn vị nghiệp vụ:** thao tác nào độc lập, thao tác nào phải cùng commit?
2. **Chọn atomic boundary:** một document, transaction nhỏ hoặc workflow có bù trừ.
3. **Gán ID ổn định:** business key, inputId, operationId và version.
4. **Chọn operation phù hợp:** insert/update/upsert/replace/delete, xác định idempotency.
5. **Chọn ordered/unordered** theo phụ thuộc, không chỉ theo tốc độ.
6. **Chia batch** theo số lượng, byte, timeout và giới hạn tài nguyên.
7. **Chọn mức xác nhận ghi** theo yêu cầu durability.
8. **Đọc và phân loại kết quả** theo từng item, không chỉ cấp request.
9. **Đối soát kết quả UNKNOWN**, không retry mù.
10. **Checkpoint theo bằng chứng hoàn tất**, cho phép worker resume.
11. **Đo tải có cả lỗi và retry**, theo dõi throughput và tail latency.
12. **Trả báo cáo rõ ràng** phân biệt đã nhận, đã gửi, đã áp dụng và đã đối soát.

**Kết luận:** Bulk operation và batch giúp tăng hiệu quả xử lý nhưng **không đảm bảo toàn bộ thao tác đều thành công**. Một thiết kế đáng tin cậy phải nắm được **mục đã áp dụng, mục bị từ chối, mục chưa được thử và mục chưa rõ trạng thái**, rồi có thể tiếp tục hoặc khôi phục **mà không ghi trùng và không làm sai dữ liệu nghiệp vụ**.
