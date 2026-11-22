# Read preference: primary, secondary và các chế độ ưu tiên trong MongoDB

## 1. Bối cảnh và mục tiêu

MongoDB hỗ trợ **replica set** để cung cấp khả năng chịu lỗi và sao chép dữ liệu. Trong một replica set thông thường, **primary** nhận các thao tác ghi, còn **secondary** sao chép các thao tác đó và có thể phục vụ truy vấn đọc. Khi ứng dụng có nhiều lựa chọn node để đọc, cần một chính sách quyết định nên gửi query đến đâu.

**Read preference** là chính sách lựa chọn member phục vụ thao tác đọc. MongoDB có năm mode chính:

- `primary`
- `primaryPreferred`
- `secondary`
- `secondaryPreferred`
- `nearest`

Bài học này giúp bạn:

1. Hiểu cơ chế chọn node và điểm khác nhau giữa năm chế độ.
2. Phân tích khi nào dữ liệu từ secondary có thể cũ (*stale read*).
3. Sử dụng **read preference tags**, `maxStalenessSeconds` và `localThresholdMS`.
4. Cấu hình trong connection URI, `mongosh`, Node.js và Java Driver.
5. Phân biệt read preference với **read concern**, **write concern**, **causal consistency** và transaction.
6. Thiết kế chế độ phù hợp cho màn hình giao dịch, báo cáo, tra cứu nhiều vùng và xử lý failover.

**Điểm quan trọng nhất:** Read preference trả lời câu hỏi **“MongoDB đọc từ node nào?”**. Nó **không tự đảm bảo** “dữ liệu luôn mới nhất”, “đọc thấy write vừa thực hiện” hay “toàn bộ chuỗi thao tác có snapshot nhất quán”.

## 2. Replica set: primary, secondary và replication lag

Sơ đồ đơn giản:

~~~text
                Application / MongoDB Driver
                            |
                            v
                   Replica set rs0
                     /     |      \
                    v      v       v
              +--------+ +--------+ +--------+
              | PRIMARY| |SECONDARY| |SECONDARY|
              |  A     | |   B     | |   C     |
              +--------+ +--------+ +--------+
                  |           ^          ^
                  +-----------+----------+
                     Replication bất đồng bộ
~~~

Primary xử lý write thông thường. Secondary áp dụng các thao tác đã ghi vào luồng replication. Vì sao cần read preference?

- Nếu tất cả read vào primary, primary xử lý cả read/write và có thể quá tải.
- Nếu chuyển một phần read sang secondary, có thể phân phối tải nhưng phải chấp nhận độ trễ đồng bộ.
- Nếu cluster đặt ở nhiều khu vực, độ trễ mạng giữa ứng dụng và mỗi member khác nhau.
- Khi primary đang bầu chọn lại, một số mode có thể đọc secondary; một số mode cố ý không fallback.

### 2.1. Stale read xảy ra như thế nào?

~~~text
T0   Client ghi order O-100 lên primary A.
T1   A phản hồi ghi theo write concern đã chọn.
T2   Client đọc O-100 từ secondary B.
T3   B mới áp dụng bản ghi O-100.
~~~

Ở T2, secondary B có thể **chưa có** O-100. Truy vấn lúc đó có thể trả null, dù request ghi trước đã được primary chấp nhận. Đây là sự khác biệt giữa **trạng thái mới tại primary** và **trạng thái mà secondary đã áp dụng**.

Không nên nhầm:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| Read preference | Chọn thành viên để phục vụ read |
| Replication lag | Khoảng chậm trong việc nhận/áp dụng write của secondary |
| Read concern | Quy tắc về những phiên bản dữ liệu có thể được đọc |
| Write concern | Mức xác nhận write theo cơ chế replication |
| Causal consistency | Bảo đảm thứ tự nhân quả giữa các thao tác trong session thích hợp |
| Transaction | Nhóm thao tác có ngữ nghĩa giao dịch trong phạm vi được hỗ trợ |

## 3. Bảng so sánh năm chế độ

| Chế độ | Khi cluster khỏe | Không có primary | Không có secondary phù hợp | Có thể stale? |
| --- | --- | --- | --- | --- |
| `primary` | Chỉ đọc primary | Không có node đọc; có thể timeout/lỗi | Vẫn đọc primary | Không do replication lag của secondary, nhưng còn phụ thuộc read concern |
| `primaryPreferred` | Ưu tiên primary | Fallback secondary nếu có | Dùng primary nếu còn | Có khi fallback secondary |
| `secondary` | Chỉ đọc secondary | Vẫn có thể đọc secondary | Lỗi chọn server/timeout; không fallback primary | Có |
| `secondaryPreferred` | Ưu tiên secondary | Có thể đọc secondary | Fallback primary nếu có | Có khi dùng secondary |
| `nearest` | Chọn primary hoặc secondary theo latency window | Có thể đọc secondary | Có thể chọn primary | Có nếu chọn secondary |

**Mode mặc định là `primary`.**

Có thể ghi nhớ:

~~~text
primary            -> PRIMARY only
primaryPreferred   -> PRIMARY first, SECONDARY fallback
secondary          -> SECONDARY only
secondaryPreferred -> SECONDARY first, PRIMARY fallback
nearest            -> primary hoặc secondary hợp lệ theo độ trễ
~~~

Các từ **Preferred** thể hiện **ưu tiên và fallback**, không phải cam kết mọi thao tác đều đi tới loại node ưu tiên. Ngay cả khi chọn được member, operation vẫn có thể lỗi do mạng, tải hoặc trạng thái server thay đổi.

## 4. Mode primary: mặc định dành cho ứng dụng giao dịch

`primary` chỉ cho phép read từ primary:

~~~javascript
// Option minh họa của driver:
{ readPreference: "primary" }
~~~

Khi primary còn hoạt động, driver gửi read đến primary. Nếu primary không khả dụng trong lúc election, client có thể đợi đến hết thời gian server selection rồi báo lỗi.

**Ưu điểm:**

- Tránh việc đọc secondary chưa áp dụng write mới.
- Phù hợp cho các API cần phản hồi sát trạng thái vừa cập nhật.
- Đơn giản khi vận hành các thao tác giao dịch.
- Phù hợp với quy tắc của transaction có read.

**Đánh đổi:**

- Primary phải gánh phần tải đọc.
- Không có secondary fallback trong cửa sổ primary mất khả dụng.
- Nếu ứng dụng ở xa primary, RTT có thể lớn hơn một secondary gần đó.

### 4.1. Primary không có nghĩa mọi read là linearizable

`readPreference: "primary"` **không tự biến read concern thành `majority` hay `linearizable`**. Nó chỉ chọn thành viên phục vụ read. Tính nhất quán, khả năng rollback và snapshot phụ thuộc read concern/write concern cùng topology.

### 4.2. Primary không tương thích tag sets và max staleness

Không dùng:

~~~text
readPreference=primary&readPreferenceTags=region:vn
readPreference=primary&maxStalenessSeconds=120
~~~

Read preference tags và `maxStalenessSeconds` không tương thích với mode `primary`; driver có thể từ chối cấu hình.

## 5. Mode primaryPreferred: primary trước, secondary khi cần

`primaryPreferred` chọn primary khi nó có sẵn. Khi primary không khả dụng, driver xét secondary đủ điều kiện theo tags, staleness và độ trễ:

~~~javascript
{ readPreference: "primaryPreferred" }
~~~

Sơ đồ:

~~~text
Primary đang có?
  |
  +-- CÓ --> chọn primary
  |
  +-- KHÔNG --> tìm eligible secondary
                   |
                   +-- có --> chọn secondary
                   +-- không --> selection timeout / lỗi
~~~

**Use case:** ứng dụng ưu tiên trạng thái gần primary, nhưng có thể chấp nhận **stale reads trong failover** để tăng khả năng phục vụ truy vấn.

Điều dễ bị bỏ sót: khi một request chuyển sang secondary trong thời gian không có primary, kết quả có thể **cũ hơn những gì user vừa thấy** ở lần đọc primary trước đó. Không nên chọn mode này nếu quy tắc nghiệp vụ tuyệt đối không chấp nhận đọc lùi trạng thái.

### 5.1. Tags chỉ có tác dụng khi fallback

Ví dụ muốn fallback tới secondary khu vực Việt Nam:

~~~javascript
{
  readPreference: "primaryPreferred",
  readPreferenceTags: [
    { region: "vn" }
  ]
}
~~~

Khi primary ở Singapore còn hoạt động, driver vẫn ưu tiên primary đó; tag `region: "vn"` **không ép primary phải có tag phù hợp**. Tags chỉ được áp dụng khi secondary là ứng viên.

## 6. Mode secondary: chỉ đọc secondary

`secondary` chọn **secondary** đủ điều kiện và **không fallback primary** khi không có secondary:

~~~javascript
{ readPreference: "secondary" }
~~~

Phù hợp với:

- Dashboard chấp nhận dữ liệu chậm một khoảng thời gian.
- Báo cáo/analytics hoặc batch query không bắt buộc vừa ghi vừa thấy.
- Workload đọc có thể tách khỏi primary.
- Một số tác vụ export với giới hạn tài nguyên rõ ràng.

Nếu replica set chỉ có một primary và không có secondary hợp lệ, `secondary` sẽ không có server đáp ứng mode. Thời gian đợi phụ thuộc `serverSelectionTimeoutMS` và cơ chế driver.

**Không nên chọn secondary** cho việc quyết định một điều kiện ghi quan trọng dựa trên giá trị vừa đọc, ví dụ trừ tồn kho hoặc xác thực quyền vừa bị thu hồi, nếu chưa thiết kế cơ chế nhất quán/atomicity phù hợp.

### 6.1. Secondary read cũng có chi phí

Read trên secondary có thể giảm CPU query ở primary nhưng vẫn tiêu thụ CPU, I/O và cache trên secondary. Một query báo cáo nặng có thể làm secondary áp dụng oplog chậm hơn, làm lag tăng. Không mặc định “càng chuyển nhiều read sang secondary càng tốt”.

## 7. Mode secondaryPreferred: secondary trước, primary khi cần

`secondaryPreferred` chọn secondary khi có, nhưng **fallback về primary** nếu không có eligible secondary:

~~~javascript
{ readPreference: "secondaryPreferred" }
~~~

~~~text
Có secondary phù hợp?
  |
  +-- CÓ --> chọn secondary
  |
  +-- KHÔNG --> có primary?
                   |
                   +-- có --> đọc primary
                   +-- không --> lỗi
~~~

Ưu điểm: phân phối read sang secondary trong điều kiện bình thường, có khả năng tiếp tục đọc khi secondary unavailable.

Nhược điểm: khi secondary lỗi, khối lượng query có thể **đổ vào primary đúng lúc hệ thống đang có sự cố**. Cần đo tải đọc và thiết kế rate limiting/circuit breaker nếu cần.

Nếu mục tiêu là **không bao giờ** để job báo cáo đọc primary, dùng `secondary`, không dùng `secondaryPreferred`.

### 7.1. Vì sao tags có thể không giữ được cách ly tải?

Với `secondaryPreferred` + tag `workload: "analytics"`, client ưu tiên secondary có tag phù hợp. Khi không có secondary đủ điều kiện, policy vẫn có thể fallback primary. Tags không được dùng để loại primary trong nhánh fallback của mode này.

## 8. Mode nearest: ưu tiên cửa sổ latency, không ưu tiên vai trò

`nearest` xem primary và secondary là ứng viên cùng cấp, sau đó lọc theo tiêu chí và chọn node trong **latency window**:

~~~javascript
{ readPreference: "nearest" }
~~~

Thuật toán khái quát:

1. Tìm các member có trạng thái phù hợp.
2. Lọc theo `maxStalenessSeconds` cho secondary nếu cấu hình.
3. Lọc theo read preference tag sets nếu cấu hình.
4. Xác định RTT nhỏ nhất và cộng `localThresholdMS` để tạo cửa sổ.
5. Chọn một member trong nhóm đủ điều kiện nằm trong cửa sổ.

Ngưỡng `localThresholdMS` mặc định thông thường là **15 ms**.

Ví dụ:

| Member | Role | RTT |
| --- | --- | ---: |
| A | primary | 11 ms |
| B | secondary | 17 ms |
| C | secondary | 43 ms |

Với ngưỡng 15 ms, cửa sổ có RTT tối đa **26 ms**. A và B là ứng viên, C bị loại. Driver có thể chọn **A hoặc B**, không bắt buộc chọn A.

**Nearest không có nghĩa:**

- Thành viên gần về địa lý nhất.
- Thành viên có dữ liệu mới nhất.
- Thành viên luôn phản hồi nhanh nhất trong từng query.
- Luôn tránh primary.

`nearest` phù hợp khi độ trễ mạng quan trọng hơn việc cố định vai trò primary/secondary và ứng dụng có cách xử lý stale reads.

## 9. Cơ chế server selection và thời gian chờ

Read preference được đánh giá **theo từng operation**, không cố định toàn bộ vòng đời ứng dụng vào một member duy nhất. Các tiêu chí ảnh hưởng:

- Current replica set topology: primary, secondary, unreachable/recovering.
- Mode đọc được chọn.
- Tag set lists.
- `maxStalenessSeconds`.
- `localThresholdMS` hoặc ngưỡng tương ứng của router.
- Server selection timeout và tình trạng kết nối.

### 9.1. Selection timeout không phải query timeout

Ví dụ connection URI:

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0&readPreference=secondary&serverSelectionTimeoutMS=5000
~~~

`serverSelectionTimeoutMS=5000` giới hạn quá trình **tìm member phù hợp**, không làm query đang chạy trên member đã chọn tự kết thúc sau 5 giây.

Nếu không có secondary, mode `secondary` có thể gây lỗi lựa chọn server khi hết timeout. Tăng thời gian này không tự làm xuất hiện secondary mới.

### 9.2. Đọc từ secondary không chuyển write sang secondary

Read preference không đổi quy tắc ghi thông thường của replica set. Những lệnh insert/update/delete cần primary phù hợp. Khi primary chưa có sau election, `secondaryPreferred` có thể tiếp tục đọc nhưng **không làm write khả dụng trên secondary**.

## 10. Read preference tags: nhóm server theo metadata

Người quản trị có thể gắn tag cho từng replica set member, ví dụ:

~~~javascript
// Ví dụ cấu hình ý tưởng, không phải lệnh thay đổi
// replica set thực tế.
{
  host: "db-secondary-vn.example.net:27017",
  priority: 0,
  tags: {
    region: "vn",
    workload: "analytics"
  }
}
~~~

Các tag `region` và `workload` là quy ước do hệ thống định nghĩa, không phải các thuộc tính MongoDB tự thêm.

Policy đọc:

~~~javascript
{
  readPreference: "secondary",
  readPreferenceTags: [
    { region: "vn", workload: "analytics" }
  ]
}
~~~

Chỉ các secondary thỏa tag set và những điều kiện khác mới đủ điều kiện.

### 10.1. Danh sách tag sets là danh sách ưu tiên

Ví dụ:

~~~javascript
[
  { region: "vn", workload: "analytics" },
  { region: "sg" },
  {}
]
~~~

Driver xét các tag sets theo thứ tự:

1. Tìm eligible member khớp tag set đầu tiên.
2. Nếu không có, thử tag set thứ hai.
3. Nếu vẫn không có, `{}` cho phép bất kỳ member nào đã vượt qua các tiêu chí mode/staleness khác.

Một member không phải khớp cả ba tag sets cùng lúc.

### 10.2. Tags được áp dụng theo mode

| Mode | Quy tắc tags |
| --- | --- |
| `primary` | Không tương thích |
| `primaryPreferred` | Chỉ khi chọn secondary |
| `secondary` | Luôn khi chọn secondary |
| `secondaryPreferred` | Khi chọn secondary, không ép primary fallback khớp tags |
| `nearest` | Lọc cả primary và secondary |

Nếu không có member khớp tag và mode là `secondary`, client không bỏ qua tags tự động. Nếu cần fallback rộng, thêm tag set rỗng trong danh sách theo chính sách đã thống nhất.

**Tags không bảo đảm freshness.** Tag `region: "vn"` không nói secondary đó có lag bao nhiêu.

## 11. maxStalenessSeconds: lọc secondary quá chậm

`maxStalenessSeconds` cho phép hạn chế các secondary có **replication staleness ước lượng** vượt ngưỡng.

Ví dụ:

~~~text
readPreference=secondaryPreferred
maxStalenessSeconds=120
~~~

Ứng viên secondary có lag ước lượng lớn hơn 120 giây bị loại theo cơ chế server selection.

### 11.1. Ngưỡng thấp nhất 90 giây

MongoDB yêu cầu giá trị `maxStalenessSeconds` **ít nhất 90 giây** (và đáp ứng yêu cầu liên quan heartbeat frequency của driver).

~~~text
maxStalenessSeconds=5    -> không hợp lệ
maxStalenessSeconds=30   -> không hợp lệ
maxStalenessSeconds=90   -> đạt ngưỡng tối thiểu
maxStalenessSeconds=120  -> đạt ngưỡng tối thiểu
~~~

Việc ước lượng độ chậm dựa trên heartbeat và thời điểm write mà driver quan sát, không diễn ra chính xác từng mili-giây. Đây là lý do không thể yêu cầu ngưỡng 5 giây chỉ bằng option này.

### 11.2. Mode tương thích

| Mode | maxStalenessSeconds |
| --- | --- |
| `primary` | **Không dùng được** |
| `primaryPreferred` | Có, khi fallback secondary |
| `secondary` | Có |
| `secondaryPreferred` | Có |
| `nearest` | Có, để lọc secondary |

Nếu không có primary, các secondary có thể được so sánh với secondary có thời điểm write mới nhất theo thuật toán của driver, chứ không nhất thiết với một primary đã mất.

### 11.3. Không hiểu nhầm giới hạn stale

`maxStalenessSeconds=120` **không bảo đảm** dữ liệu “cũ tối đa đúng 120 giây” cho mỗi thao tác. Đây là **bộ lọc node theo ước lượng thô**. Một secondary có thể bắt đầu lag thêm ngay sau lần heartbeat; một query có thể phục vụ trên primary khi mode fallback cho phép; read concern và causal context cũng ảnh hưởng trạng thái quan sát.

Muốn read-your-writes có bảo đảm, xem causal consistency ở phần sau.

## 12. Cấu hình URI

Các ví dụ giả định replica set tên `rs0` có ba endpoint. URI production cần thay hostname/credential thực và không lưu thông tin bí mật trong source.

**Mặc định primary:**

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0
~~~

**Chỉ secondary:**

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0&readPreference=secondary
~~~

**PrimaryPreferred:**

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0&readPreference=primaryPreferred
~~~

**SecondaryPreferred với staleness:**

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0&readPreference=secondaryPreferred&maxStalenessSeconds=120
~~~

**Nearest với ngưỡng latency:**

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0&readPreference=nearest&localThresholdMS=20
~~~

**Secondary có tag sets ưu tiên:**

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0&readPreference=secondary&readPreferenceTags=region:vn,workload:analytics&readPreferenceTags=region:sg
~~~

Lặp tham số `readPreferenceTags` biểu diễn **danh sách tag sets**, không phải hai tag bắt buộc phải khớp cùng lúc.

Khi dùng Atlas với URI `mongodb+srv://...`, read preference cũng có thể được cấu hình theo options được driver và deployment hỗ trợ; không thay đổi DNS/SRV/credential chỉ để thử nghiệm.

## 13. Thực hành mongosh trên replica set

### 13.1. Chuẩn bị

Các thao tác sau cần **replica set đang hoạt động**. Trên standalone, không có eligible secondary để kiểm thử.

~~~javascript
const lab = db.getSiblingDB("read_preference_lab");

lab.events.insertOne({
  _id: "e1",
  eventType: "created",
  createdAt: new Date()
});

lab.events.findOne({ _id: "e1" });
~~~

Việc ghi được gửi đến primary theo quy tắc ghi của replica set. Nếu đọc primary ngay sau một write đã xác nhận, thường thấy document mới; độ bền và khả năng rollback còn phụ thuộc write/read concern.

### 13.2. Đổi read preference của connection mongosh

~~~javascript
db.getMongo().setReadPref("primary");

const lab = db.getSiblingDB("read_preference_lab");
lab.events.find({}).limit(5).toArray();

db.getMongo().setReadPref("secondary");
lab.events.find({}).limit(5).toArray();

db.getMongo().setReadPref("secondaryPreferred");
lab.events.find({}).limit(5).toArray();

db.getMongo().setReadPref("primaryPreferred");
lab.events.find({}).limit(5).toArray();

db.getMongo().setReadPref("nearest");
lab.events.find({}).limit(5).toArray();
~~~

Trên hệ thống replication chậm, một read secondary có thể chưa thấy `e1` dù write đã hoàn tất. Nếu không có secondary, đọc `secondary` có thể timeout.

Sau khi thực hành, trả về default:

~~~javascript
db.getMongo().setReadPref("primary");
~~~

### 13.3. Quan sát topology

Nếu kết nối đúng `mongod` của replica set và có quyền:

~~~javascript
rs.status();
rs.printSecondaryReplicationInfo();
~~~

Quan sát member state và thời điểm replication. Output tùy phiên bản và có thể yêu cầu quyền vận hành. Trên `mongos`, không dùng các lệnh này như thể router là một replica set member.

`db.hello()` cho biết thông tin server/topology ở ngữ cảnh lệnh đó, **không phải bằng chứng** mọi lệnh `find()` tiếp theo đều đến cùng thành viên. Driver có thể chọn node khác ở từng operation.

## 14. MongoDB Node.js Driver: chọn mode theo operation

Ví dụ chạy trong ứng dụng Node.js, không phải mongosh:

~~~javascript
const { MongoClient } = require("mongodb");

const uri =
  "mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0";

async function main() {
  const client = new MongoClient(uri);

  try {
    await client.connect();

    const orders = client.db("app").collection("orders");

    await orders.insertOne({
      _id: "ORD-100",
      status: "PAID",
      createdAt: new Date()
    });

    // Đọc nhạy cảm với freshness: primary.
    const detail = await orders.findOne(
      { _id: "ORD-100" },
      { readPreference: "primary" }
    );

    // Báo cáo chịu stale: secondaryPreferred.
    const history = await orders.find(
      { status: "PAID" },
      { readPreference: "secondaryPreferred" }
    )
    .limit(20)
    .toArray();

    console.log({
      detail,
      reportCount: history.length
    });
  } finally {
    await client.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
~~~

Lưu ý:

- Ví dụ giả định đã có replica set và quyền ghi.
- `detail` và `history` dùng **read preference khác nhau** nhưng cùng collection handle.
- Không nên suy ra rằng `history` luôn chứa ngay ORD-100.
- `toArray()` phù hợp với kết quả nhỏ; báo cáo lớn nên đọc qua cursor theo batch.
- Production nên tránh `_id` cố định giữa các test run để không tạo duplicate key nếu chạy lại.

### 14.1. Command monitoring để kiểm tra node phục vụ

Node.js Driver hỗ trợ command events ở các phiên bản phù hợp:

~~~javascript
const { MongoClient } = require("mongodb");

const client = new MongoClient(process.env.MONGODB_URI, {
  monitorCommands: true,
  readPreference: "secondaryPreferred"
});

client.on("commandStarted", event => {
  if (["find", "aggregate"].includes(event.commandName)) {
    console.log({
      command: event.commandName,
      address: event.address
    });
  }
});
~~~

Trong replica set, địa chỉ ở command event có thể giúp xem member nhận lệnh. Trong sharded cluster, event phía driver có thể chỉ cho thấy **mongos/router**, không xác nhận shard member cuối cùng. Không ghi raw query hoặc thông tin nhạy cảm vào log.

## 15. Java Sync Driver: giới hạn scope bằng collection handle

Ví dụ Java:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ReadPreferenceExample {
    public static void main(String[] args) {
        ConnectionString uri = new ConnectionString(
            "mongodb://db1:27017,db2:27017,db3:27017/"
                + "?replicaSet=rs0"
        );

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(uri)
            .readPreference(ReadPreference.primary())
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            MongoDatabase database = client.getDatabase("app");
            MongoCollection<Document> orders =
                database.getCollection("orders");

            // Handle mới chỉ dành cho báo cáo.
            MongoCollection<Document> reportingOrders =
                orders.withReadPreference(
                    ReadPreference.secondaryPreferred()
                );

            Document detail = orders.find(
                new Document("_id", "ORD-100")
            ).first();

            reportingOrders.find(
                new Document("status", "PAID")
            ).limit(20).forEach(
                doc -> System.out.println(doc.toJson())
            );

            System.out.println(detail);
        }
    }
}
~~~

`withReadPreference()` trả một collection handle với policy đã chọn, không cần đổi default cho mọi query của ứng dụng. Nếu báo cáo **không được phép fallback primary**, thay bằng `ReadPreference.secondary()`.

Để cấu hình advanced tags, max staleness hay custom server selection, sử dụng API `ReadPreference` phù hợp với **phiên bản driver đang dùng**, vì các overload và builder có thể khác nhau.

## 16. Read preference khác read concern và write concern

| Thiết lập | Câu hỏi giải quyết | Giá trị ví dụ |
| --- | --- | --- |
| Read preference | Đọc từ member nào? | `primary`, `secondaryPreferred` |
| Read concern | Dữ liệu đọc được phép ở mức commit/snapshot nào? | `local`, `majority`, `snapshot`, `linearizable` |
| Write concern | Khi nào client được xác nhận write đã được ghi/replicate? | `w:1`, `w:"majority"` |
| Causal consistency | Những thao tác có quan hệ nhân quả có quan sát theo thứ tự phù hợp không? | Session với majority read/write concerns |

### 16.1. Read concern local

Với `local`, query đọc dữ liệu có sẵn trên member theo semantics của local read concern. Trên secondary, dữ liệu có thể chậm do replication. Dữ liệu được đọc có thể bao gồm write chưa majority-committed, với các tình huống rollback cần xem xét.

### 16.2. Read concern majority

`majority` tập trung vào dữ liệu đã được majority commit. Tuy nhiên, đọc secondary với `readConcern: "majority"` **không đồng nghĩa** đã có mọi write mới nhất được primary xác nhận. Member vẫn cần áp dụng write hoặc phục vụ điểm thời gian phù hợp.

### 16.3. Write concern majority

`w:"majority"` giúp đạt mức xác nhận ghi theo phần lớn các member quy định. Nó **không ép** từng secondary phục vụ query sau ngay tại thời điểm mà client muốn, cũng không biến một secondary read bình thường thành read-your-writes.

### 16.4. Read concern linearizable

`linearizable` được hỗ trợ trong những điều kiện cụ thể, gắn với **read trên primary**. Không thể đặt read preference secondary rồi đòi tuyến đọc đó có ngữ nghĩa linearizable như đọc primary.

### 16.5. Transaction có read

Theo MongoDB, transaction chứa read operations phải dùng **readPreference primary**; các thao tác của transaction được định tuyến theo các quy tắc transaction. Không đổi read preference thành secondaryPreferred cho transaction chỉ để giảm tải.

**Kết luận:** Chọn read preference là bước đầu, không thay thế việc xác định freshness/durability/isolation cần thiết.

## 17. Causal consistency: khi cần read-your-writes qua secondary

Một tình huống quen thuộc:

~~~text
T1: User cập nhật displayName trên primary.
T2: API GET profile đọc secondary.
T3: Secondary chưa áp dụng write.
=> GET trả displayName cũ.
~~~

Nếu ứng dụng cần thấy write của chính người dùng, có hai phương án thường được cân nhắc:

1. Đọc từ **primary** cho các bước nhạy cảm với độ mới.
2. Dùng **causally consistent session** với điều kiện read/write concerns phù hợp nếu cần đọc secondary mà vẫn giữ quan hệ nhân quả.

### 17.1. Session với majority write/read concern

Ví dụ Node.js:

~~~javascript
const { MongoClient } = require("mongodb");

async function writeThenReadSecondary(client) {
  const orders = client.db("app").collection("orders");
  const session = client.startSession({
    causalConsistency: true
  });

  try {
    await orders.insertOne(
      {
        _id: "causal-order-001",
        status: "PAID"
      },
      {
        session,
        writeConcern: { w: "majority" }
      }
    );

    const document = await orders.findOne(
      { _id: "causal-order-001" },
      {
        session,
        readPreference: "secondary",
        readConcern: { level: "majority" }
      }
    );

    return document;
  } finally {
    await session.endSession();
  }
}
~~~

MongoDB mô tả **read your writes**, **monotonic reads** và những đảm bảo nhân quả khác cho session khi đọc dùng `majority` read concern và ghi dùng `majority` write concern theo điều kiện tài liệu.

**Đánh đổi:** Nếu secondary đã chọn chưa phục vụ được điểm thời gian cần thiết, read có thể chờ hoặc báo lỗi/timeout. Causal consistency **không làm replication xảy ra tức thì**.

**Không nhầm:** Session causal consistency không phải transaction đa document, không ngăn writer khác sửa dữ liệu và không tự truyền quan hệ nhân quả giữa những request không dùng cùng causal context.

### 17.2. Các bảo đảm thường được nói đến

- **Read your writes:** đọc sau phản ánh write trước đó trong quan hệ nhân quả.
- **Monotonic reads:** đọc sau không quay về trạng thái trước một trạng thái đã quan sát.
- **Monotonic writes:** thứ tự write có liên hệ được giữ.
- **Writes follow reads:** write sau một read tuân theo quan hệ nhân quả của read.

Một session không nên được sử dụng đồng thời không kiểm soát bởi nhiều luồng xử lý nếu driver yêu cầu tuần tự để duy trì causal ordering.

## 18. Failover: năm mode sẽ ra sao?

Giả sử:

~~~text
Ban đầu:
  A = primary
  B = secondary
  C = secondary

Khi A mất:
  A = unavailable
  B = secondary
  C = secondary

Sau election:
  B = primary mới
  C = secondary
~~~

Trong cửa sổ chưa có primary:

| Mode | Kết quả có thể xảy ra |
| --- | --- |
| `primary` | Không có primary; đợi rồi lỗi nếu hết thời hạn |
| `primaryPreferred` | Fallback sang secondary đủ điều kiện |
| `secondary` | Vẫn có thể đọc secondary đủ điều kiện |
| `secondaryPreferred` | Vẫn có thể đọc secondary |
| `nearest` | Có thể chọn secondary trong cửa sổ latency |

Sau election, driver cập nhật topology và tiếp tục áp dụng mode. Read preference được đánh giá lại qua các operation.

Những điều có thể khiến lựa chọn thất bại dù còn node chạy:

- Node không ở trạng thái cho phép phục vụ read.
- Không có eligible node thỏa tags.
- Secondary quá stale theo maxStalenessSeconds.
- Network partition hoặc timeout.
- Member vừa đổi vai trò trong lúc server selection.

Chọn mode dựa trên hợp đồng nghiệp vụ:

- **Chấp nhận lỗi tạm thời để không đọc stale:** có thể giữ `primary`.
- **Ưu tiên availability hơn freshness trong election:** cân nhắc `primaryPreferred`.
- **Báo cáo không được chuyển vào primary:** chọn `secondary`.

## 19. Read preference trong sharded cluster

Ứng dụng thường gửi query tới `mongos` hoặc cluster router được dịch vụ hỗ trợ. Router có thể định tuyến đọc tới những member phù hợp của từng shard replica set.

~~~text
Application
     |
   mongos
     |
     +---- Shard 1 replica set
     |      primary + secondaries
     |
     +---- Shard 2 replica set
            primary + secondaries
~~~

Read preference trong cluster nhiều shard có thêm các cân nhắc:

- Một query không target shard key có thể **scatter-gather** tới nhiều shard.
- Mỗi shard có thể chọn member khác nhau dựa trên policy.
- Latency trên router không phản ánh hoàn toàn độ trễ tới từng shard member.
- Dữ liệu giữa các shard có thể có mức tiến triển replication khác nhau.
- Query thiếu index vẫn chậm dù đọc từ secondary hoặc nearest.

Vì vậy **read preference không thay thế shard key tốt, index phù hợp và kế hoạch query**.

### 19.1. Long-running secondary reads

Ở MongoDB 8.2 trở lên có thay đổi về xử lý một số secondary reads chạy lâu trong sharded cluster khi cleanup orphaned documents sau chunk migration. Với job export/analytics dài, cần kiểm tra tài liệu phiên bản thật và có cơ chế resume/retry phù hợp.

## 20. Chọn mode theo workload

| Workload | Mode thường cân nhắc | Rủi ro và ghi chú |
| --- | --- | --- |
| Người dùng vừa tạo đơn rồi mở chi tiết | `primary` | Ưu tiên freshness |
| Login/quyền truy cập vừa thay đổi | `primary` | Cần consistency phù hợp; không chỉ dựa read preference |
| Báo cáo định kỳ chấp nhận trễ | `secondary` | Cần xử lý timeout nếu secondary lỗi |
| Danh sách sản phẩm nhiều read | `secondaryPreferred` | Có thể stale; fallback primary tăng tải |
| Tra cứu chịu stale trong election | `primaryPreferred` | Độ mới có thể thay đổi khi fallback |
| Ứng dụng nhiều khu vực ưu tiên RTT | `nearest` + tags | Không đảm bảo vai trò hoặc freshest state |
| Job báo cáo không bao giờ dùng primary | `secondary` + tags | Không có eligible secondary thì fail |
| Transaction có read | `primary` | Theo ràng buộc transaction |
| Counter/tồn kho dùng làm điều kiện ghi | `primary` + atomic conditional update | Không được chỉ đọc rồi ghi vô điều kiện |

### 20.1. Tránh quyết định ghi bằng stale read

Ví dụ sai:

~~~javascript
const product = await products.findOne(
  { _id: "SKU-1" },
  { readPreference: "secondary" }
);

if (product && product.stock > 0) {
  await products.updateOne(
    { _id: "SKU-1" },
    { $inc: { stock: -1 } }
  );
}
~~~

Secondary có thể stale; hai request cũng có thể cùng thấy stock dương. Khi đó update không có điều kiện có thể làm stock âm.

Hướng an toàn là **atomic conditional update**:

~~~javascript
const result = await products.updateOne(
  { _id: "SKU-1", stock: { $gte: 1 } },
  { $inc: { stock: -1 } }
);

if (result.modifiedCount === 0) {
  // Không còn stock hoặc document không khớp.
}
~~~

Điều kiện và thay đổi được thực hiện trên **một document trong một write**, không phụ thuộc một giá trị cũ được đọc từ secondary.

## 21. Giám sát replication lag và read routing

Các nguyên nhân secondary đọc chậm/stale:

- Mạng giữa các member nghẽn hoặc latency cao.
- Secondary áp dụng oplog chậm vì CPU/đĩa.
- Query báo cáo cạnh tranh tài nguyên với replication.
- Node đang initial sync/recovery hoặc mất khả dụng.
- Election thay đổi thành viên primary/secondary.
- Driver lọc hết eligible secondary vì tags hoặc max staleness.

Trong môi trường được phân quyền, có thể dùng:

~~~javascript
rs.status();
rs.printSecondaryReplicationInfo();
~~~

Các lệnh này phù hợp khi kết nối trực tiếp `mongod` của replica set và có quyền; không chạy tương tự trên `mongos` rồi mong có thống kê của toàn cluster.

Phía driver theo dõi:

- Server Discovery and Monitoring (SDAM) events.
- Command monitoring và địa chỉ member nhận read.
- Server selection timeouts.
- Read latency p50/p95/p99.
- Replication lag và số lượng eligible secondaries.
- Tải read/write trên primary và secondaries.
- Tỷ lệ read-after-write chưa thấy dữ liệu nếu nghiệp vụ quan tâm.

**Không chỉ nhìn replication lag trung bình.** Một secondary có thể có lag thấp nhưng query chậm do index hoặc CPU; một mode nearest có thể giảm network RTT nhưng vẫn gặp backend query tốn thời gian.

## 22. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Read secondary chưa thấy write vừa ghi | Replication lag | Đọc primary hoặc causal session majority |
| Mode secondary timeout | Không có eligible secondary | Kiểm tra member state, tags, staleness, timeout |
| SecondaryPreferred bỗng đẩy tải vào primary | Fallback khi secondary không có | Capacity/rate limit, chọn secondary nếu cần isolation |
| PrimaryPreferred trả dữ liệu cũ trong election | Fallback secondary | Tránh mode này cho dữ liệu bắt buộc mới |
| Nearest chọn primary lúc này, secondary lúc khác | Window RTT và chọn member đủ điều kiện | Chọn role-specific mode nếu cần |
| Primary kèm tag sets bị lỗi | Tags không tương thích primary | Bỏ tags hoặc dùng mode khác |
| Primary kèm maxStaleness bị lỗi | Max staleness không tương thích | Bỏ option |
| MaxStaleness 5 giây bị từ chối | Tối thiểu 90 giây | Chọn giá trị hợp lệ, đo lag thực |
| Tags vn không tìm thấy server | Không có eligible member khớp | Kiểm tra cấu hình replica set và fallback tags |
| Có majority read concern nhưng vẫn đọc chưa thấy write | Secondary chưa đạt causal point | Causal session với majority read/write |
| Query chậm dù nearest | Query plan/index hoặc scatter-gather | Explain và kiểm tra shard targeting |
| Transaction báo lỗi khi dùng secondary read | Transaction read yêu cầu primary | Đặt primary cho transaction |
| Mongosh query trên standalone không có secondary | Topology không hỗ trợ replica selection | Thử bằng replica set |
| `rs.status()` lỗi qua mongos | Router không phải replSet member | Dùng endpoint/quyền phù hợp |
| Thay batch size nhưng không hết stale | Batch size khác server selection | Chọn read preference và consistency đúng |

## 23. Bài tập thực hành

### Bài 1 — Phân biệt năm mode

Giải thích trong một câu cho mỗi mode: primary, primaryPreferred, secondary, secondaryPreferred, nearest. Trong mode nào primary **không bao giờ** được dùng cho query read?

**Đáp án:** `secondary` không đọc primary; `primary` chỉ đọc primary; các preferred modes có fallback; nearest có thể chọn cả hai.

### Bài 2 — Không có primary

A primary mất, B/C còn là secondary và election chưa xong. Dự đoán read theo từng mode. Mode nào chắc chắn không fallback secondary?

**Đáp án:** primary; các mode khác có thể chọn secondary khi phù hợp.

### Bài 3 — Không có secondary

A còn primary, B/C không khả dụng. So sánh secondary với secondaryPreferred.

**Đáp án:** secondary không có target và có thể timeout; secondaryPreferred fallback primary.

### Bài 4 — Latency window

A RTT=11ms (primary), B=17ms (secondary), C=43ms (secondary). `localThresholdMS=15`. Với nearest, node nào thuộc cửa sổ?

**Đáp án:** A và B (RTT tối đa 26ms), không phải C.

### Bài 5 — Tag set list

Muốn ưu tiên secondary `{region:"vn",workload:"analytics"}`, nếu không có thì `{region:"sg"}`, cuối cùng mọi eligible secondary. Viết tag set list.

**Đáp án:**

~~~javascript
[
  { region: "vn", workload: "analytics" },
  { region: "sg" },
  {}
]
~~~

### Bài 6 — PrimaryPreferred với tag

Primary ở region sg, secondary ở vn. Mode primaryPreferred + tags vn. Khi primary sg còn hoạt động, driver đọc đâu?

**Đáp án:** Primary sg; tag áp dụng khi fallback secondary.

### Bài 7 — Ngưỡng max staleness

Giá trị nào hợp lệ về ngưỡng tối thiểu: 10, 30, 90, 120 giây? Có dùng với primary được không?

**Đáp án:** 90 và 120 đạt ngưỡng tối thiểu; không tương thích primary.

### Bài 8 — URI

Viết URI cho ba member, replica set rs0, dùng secondaryPreferred và maxStalenessSeconds 120.

**Ví dụ:**

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0&readPreference=secondaryPreferred&maxStalenessSeconds=120
~~~

### Bài 9 — Read-your-writes

User đổi tên rồi đọc ngay từ secondary và thấy tên cũ. Tại sao? Nêu hai cách cải thiện.

**Đáp án:** Replication bất đồng bộ; đọc primary hoặc dùng causally consistent session cùng majority read/write concerns phù hợp.

### Bài 10 — Majority read concern

Nhận định sau đúng hay sai: “`secondary` với `readConcern=majority` luôn thấy write vừa được primary xác nhận.”

**Đáp án:** Sai; majority read concern không đồng nghĩa secondary đã theo kịp hay có causal context.

### Bài 11 — Node.js override

Viết code dùng `primary` cho màn hình đơn vừa tạo, `secondaryPreferred` cho báo cáo. Vì sao nên override từng operation thay vì thay default cho cả client?

### Bài 12 — Java collection handle

Dùng `ReadPreference.primary()` trong `MongoClientSettings` rồi tạo handle `orders.withReadPreference(ReadPreference.secondaryPreferred())`. Chỉ ra những query nào dùng policy nào.

### Bài 13 — Secondary read để kiểm tra stock

Tại sao việc đọc stock từ secondary rồi `$inc: -1` vô điều kiện có thể làm số lượng âm? Viết atomic conditional update đúng.

**Đáp án:** Dùng filter `{_id, stock: {$gte:1}}` và `$inc: {stock:-1}` trên primary; kiểm tra modifiedCount.

### Bài 14 — Xử lý failover

Ứng dụng có nhiều báo cáo chấp nhận stale nhưng **không cho phép báo cáo chiếm CPU primary**. Nên dùng secondary hay secondaryPreferred?

**Đáp án:** Secondary, vì secondaryPreferred fallback primary nếu không có eligible secondary.

### Bài 15 — Sharded cluster

Một query không chứa shard key, dùng readPreference nearest. Vì sao nó có thể vẫn chậm?

**Đáp án:** Scatter-gather nhiều shard, index/query plan không phù hợp và tải backend; nearest chỉ tác động lựa chọn member, không thay query routing.

### Bài 16 — Thiết kế policy theo SLA

Một sản phẩm có ba API:

- GET chi tiết đơn vừa tạo, yêu cầu thấy ngay.
- Dashboard thống kê, chấp nhận chậm vài phút.
- Tìm kiếm nội dung nhiều region ưu tiên RTT, chấp nhận dữ liệu cũ.

Đề xuất read preference, tags/max staleness và cơ chế consistency bổ sung. Giải thích tradeoff khi secondary bị mất khả dụng.

## 24. Tổng kết

**Read preference** là chính sách chọn MongoDB member cho thao tác đọc:

1. `primary`: chỉ primary, mặc định.
2. `primaryPreferred`: primary trước, fallback secondary.
3. `secondary`: chỉ secondary, không fallback primary.
4. `secondaryPreferred`: secondary trước, fallback primary.
5. `nearest`: primary/secondary theo latency window.

**Tag sets** chọn nhóm thành viên; **`maxStalenessSeconds`** lọc secondary lag quá lớn bằng ước lượng thô (tối thiểu 90 giây); **`localThresholdMS`** tạo cửa sổ RTT cho lựa chọn server.

Read preference **không phải** read concern, write concern hay transaction. Với các yêu cầu **read-your-writes** hoặc **monotonic reads** qua secondary, cần hiểu causal consistency và những điều kiện majority read/write concern. Với giao dịch đa document, tuân thủ quy tắc read preference primary. Với dữ liệu dùng để quyết định write, ưu tiên **atomic conditional update** thay vì tin vào snapshot cũ từ secondary.

### Tài liệu MongoDB chính thức

- [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — định nghĩa và các mode.
- [Read Preference Modes](https://www.mongodb.com/docs/manual/core/read-preference-modes/) — hành vi từng mode.
- [Server Selection / Read Preference Mechanics](https://www.mongodb.com/docs/manual/core/read-preference-mechanics/) — chọn member và latency threshold.
- [Read Preference Tag Sets](https://www.mongodb.com/docs/manual/core/read-preference-tags/) — danh sách tag ưu tiên.
- [Read Preference maxStalenessSeconds](https://www.mongodb.com/docs/manual/core/read-preference-staleness/) — đo lag và ngưỡng tối thiểu.
- [Read Preference Use Cases](https://www.mongodb.com/docs/manual/core/read-preference-use-cases/) — chọn mode theo workload.
- [Read Isolation, Consistency, and Recency](https://www.mongodb.com/docs/manual/core/read-isolation-consistency-recency/) — stale reads và causal consistency.
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — các mức read concern.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — mức xác nhận ghi.
- [Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/) — readPreference, staleness, tags và timeout.
- [MongoDB Node.js Driver Documentation](https://www.mongodb.com/docs/drivers/node/current/) — cấu hình driver và sessions.
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/) — ReadPreference và collection handle.
