# Kết hợp read concern, write concern và read preference theo nghiệp vụ trong MongoDB

## 1. Bài toán thực tế: ghi thành công nhưng đọc lại không thấy?

Giả sử ứng dụng thương mại điện tử đang chạy trên MongoDB replica set. Người dùng vừa đặt một đơn hàng, API thông báo “Đặt hàng thành công”. Ngay sau đó, màn hình lịch sử đơn hàng gọi một API khác nhưng không thấy đơn mới. Trong một tình huống khác, ứng dụng đọc được đơn trên primary, sau failover lại không thấy nữa.

Hai hiện tượng có thể liên quan đến **replication**, nhưng nguyên nhân và cách xử lý không giống nhau:

1. **Secondary chưa bắt kịp primary:** đơn đã được xác nhận đủ bền vững nhưng node đang phục vụ request đọc còn trễ, nên trả kết quả cũ.
2. **Write chưa majority-committed:** primary đã xác nhận ở mức yếu hơn, sau sự cố lịch sử oplog chứa write có thể bị rollback.
3. **Ứng dụng đọc trong một ngữ cảnh khác:** request ghi và request đọc dùng read preference, session hoặc read concern khác nhau, không bảo đảm read-your-writes.

MongoDB cung cấp ba nhóm cấu hình quan trọng, giải quyết **ba câu hỏi khác nhau**:

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| **write concern** | Khi nào MongoDB được coi là đã xác nhận một lệnh ghi? | **w: 1** hay **w: "majority"** |
| **read concern** | Một lệnh đọc được phép nhìn thấy loại trạng thái dữ liệu nào? | **local**, **majority**, **snapshot**, **linearizable** |
| **read preference** | Driver sẽ chọn loại node nào để phục vụ lệnh đọc? | **primary**, **secondaryPreferred**, **nearest** |

Ba lựa chọn này **không thể thay thế lẫn nhau**. Dùng readPreference primary không tự động biến một write w:1 thành majority-committed. Dùng readConcern majority không bắt buộc truy vấn phải chạy trên primary. Dùng w:majority không buộc mọi secondary nhìn thấy write mới ngay lập tức.

Bài học này tập trung vào **cách kết hợp ba cơ chế theo yêu cầu nghiệp vụ**, không chỉ giải thích từng option rời rạc.

### Sau bài này, bạn sẽ làm được

- Phân biệt **độ bền ghi**, **mức bảo đảm của dữ liệu đọc** và **vị trí node phục vụ đọc**.
- Lựa chọn tổ hợp phù hợp cho **đặt hàng, thanh toán, tồn kho, hồ sơ người dùng, dashboard, báo cáo và audit**.
- Giải thích hiện tượng **stale read**, **rollback**, **read-your-writes** và **unknown write outcome**.
- Dùng **causally consistent session** khi cần đọc được tác động vừa ghi trên secondary.
- Hiểu **readConcern snapshot/linearizable**, transaction và các giới hạn triển khai.
- Viết truy vấn mongosh và Node.js driver với cấu hình rõ ràng.
- Xây dựng ma trận chính sách nhất quán gắn với **SLA, rủi ro mất dữ liệu và độ trễ**.
- Quan sát replica set mà không cần cố tình gây failover.

> Quy tắc an toàn: tính nhất quán là thuộc tính của **toàn bộ quy trình nghiệp vụ**. Một cấu hình database mạnh không thay thế điều kiện cập nhật tồn kho, unique index, idempotency, transaction hoặc kiểm tra quyền tenant.

## 2. Mô hình hệ thống cần hiểu trước khi chọn option

### 2.1. Primary, secondary và oplog

Replica set ba data-bearing voting members có thể được hình dung như sau:

~~~text
                        Ứng dụng
                     /              \
          request ghi                request đọc
               |                    /         \
               v                   v           v
         Primary P              Primary P    Secondary S1
               |
               | oplog, replication bất đồng bộ
               +------------------------> Secondary S1
               |
               +------------------------> Secondary S2
~~~

Primary thường nhận các thao tác ghi. Secondary theo dõi oplog để áp dụng các thay đổi. Vì replication bất đồng bộ, tại cùng thời điểm:

~~~text
Primary P:     ... E100 E101 E102 E103
Secondary S1:  ... E100 E101 E102
Secondary S2:  ... E100 E101
~~~

Một truy vấn trên S2 có thể chưa thấy E102/E103; truy vấn trên P có thể thấy E103. Nhưng nhìn thấy E103 **không đủ để khẳng định E103 đã majority-committed**.

### 2.2. Majority commit point

**Majority commit point** là mốc trong lịch sử oplog mà MongoDB xem các entry tới đó đã được đa số thành viên phù hợp sao chép và đáp ứng quy tắc durability tương ứng.

Trong hình trên, nếu P và S1 đã có E102 thì E102 có thể đạt majority trong cấu hình ba data-bearing voting members; E103 mới chỉ ở P thì chưa. Những entry **chưa majority-committed** có thể bị rollback khi một lịch sử khác trở thành lịch sử hợp lệ sau election.

~~~text
Lịch sử của P:
  E100 -- E101 -- E102 || E103
                 ^
          majority commit point

E103: primary có thể đã nhận, nhưng chưa được bảo vệ
      như lịch sử majority-committed.
~~~

**Không có nghĩa w:1 luôn mất dữ liệu.** Một write xác nhận ở mức w:1 vẫn có thể được secondary sao chép đủ nhanh để trở thành majority-committed trước khi sự cố xảy ra. Vấn đề là **client chưa được bảo đảm điều đó tại thời điểm nhận acknowledgment w:1**.

### 2.3. Hai chiều độc lập: an toàn và độ mới

Một write có thể:

- **An toàn trước rollback thông thường** vì đã majority-committed.
- Nhưng **chưa nhìn thấy trên S2** vì S2 chưa áp dụng tới vị trí đó.

Một read có thể:

- **Rất mới** vì đọc trực tiếp primary.
- Nhưng đang thấy một write **chưa majority-committed**, có nguy cơ bị rollback.

Vì vậy, “đọc mới nhất” và “đọc dữ liệu khó bị rollback” là hai đặc tính khác nhau. Cần chọn read concern và read preference dựa trên cả hai.

## 3. Write concern: ghi đến mức nào mới trả thành công?

### 3.1. Cấu trúc phổ biến

Ví dụ mongosh:

~~~javascript
db.orders.insertOne(
  {
    _id: "order-001",
    status: "created"
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 10000
    }
  }
);
~~~

Các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| **w: 0** | Không chờ acknowledgment ghi thông thường |
| **w: 1** | Primary xác nhận thao tác theo semantics w:1 |
| **w: "majority"** | Chờ điều kiện sao chép tới majority theo cấu hình replica set |
| **j: true** | Yêu cầu độ bền journal theo semantics write concern và storage engine |
| **wtimeout** | Thời gian chờ điều kiện write concern, tính bằng mili giây |

**wtimeout không tự rollback thao tác đã được áp dụng trên primary.** Khi có write concern error, ứng dụng có thể không biết ngay write đã thành công ở mức nào; cần xử lý trạng thái không xác định.

### 3.2. w:1 và nguy cơ rollback

Giả sử P có E201, S1/S2 chưa có:

~~~text
P  : E200 E201  (client đã nhận ACK w:1)
S1 : E200
S2 : E200
~~~

Nếu P bị cô lập và S1/S2 bầu primary mới, E201 có thể bị rollback khi P trở lại. Người dùng từng nhận thông báo “đã tạo” nhưng document có thể mất.

**w:1** có thể phù hợp với dữ liệu có thể tái tạo hoặc nghiệp vụ chấp nhận một khoảng rủi ro. Nó không phù hợp nếu chính sách yêu cầu việc đặt hàng đã xác nhận phải được bảo vệ khỏi rollback failover bình thường.

### 3.3. w:"majority"

Với ba node có dữ liệu và phiếu biểu quyết phù hợp:

~~~text
P  : E200 E201
S1 : E200 E201
S2 : E200

E201 đã được xác nhận ở majority (P + S1),
giả định đáp ứng điều kiện durability.
~~~

Khi client nhận **acknowledgment thành công w:"majority"**, write đã đáp ứng điều kiện majority của lệnh. Điều này giúp bảo vệ write khỏi rollback trong failover/election hợp lệ thông thường.

**w:"majority" không có nghĩa mọi secondary đã cập nhật**, không phải backup, và không biến một ghi sai nghiệp vụ thành đúng.

### 3.4. j:true và writeConcernMajorityJournalDefault

**j:true** liên quan tới journal durability. **Journal không thay thế replication majority**: một write đã được journal ở primary vẫn có thể nằm trên nhánh oplog bị rollback sau election.

Nhiều replica set dùng cấu hình **writeConcernMajorityJournalDefault: true**, khiến majority write concern chờ yêu cầu journal tương ứng. Tuy nhiên, cần xác nhận cấu hình và version cụ thể; không tự giả định mọi môi trường có hành vi như nhau.

Đối với giao dịch tài chính hoặc trạng thái khó tái tạo, hãy thiết kế mức bảo đảm trên cả **replication, durability, idempotency và backup**, không chỉ một tham số.

### 3.5. wtimeout và kết quả không xác định

~~~javascript
db.orders.insertOne(
  { _id: "order-002", status: "created" },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

Nếu secondary quá chậm hoặc không đủ node để đáp ứng majority, MongoDB có thể trả **write concern timeout/error**. Những tình huống có thể xảy ra:

1. Primary đã ghi document, chưa được majority xác nhận.
2. Write đã được áp dụng và sau đó đạt majority, dù client nhận timeout.
3. Failover khiến write chưa majority-committed bị rollback.
4. Response mạng bị mất nên client không biết chính xác server đã làm gì.

**Không tự động gửi lại một lệnh $inc hoặc tạo một order với ID mới chỉ vì timeout.** Dùng requestId/idempotency key và cơ chế đối chiếu để xác định kết quả.

## 4. Read concern: dữ liệu được đọc phải đạt mức bảo đảm nào?

Read concern được đặt cho thao tác đọc; nó quy định khả năng chấp nhận các trạng thái dữ liệu và tính nhất quán theo mô hình MongoDB.

### 4.1. readConcern "local"

**local** có thể trả dữ liệu đã được node đang phục vụ áp dụng, kể cả khi dữ liệu đó **chưa majority-committed**. Đây là một mức đọc hữu ích cho nhiều nhu cầu thông thường, nhưng không đưa ra bảo đảm chống quan sát dữ liệu có thể rollback.

Ví dụ:

~~~text
Primary P:
  đã áp dụng E103
  majority commit point hiện ở E102

readConcern local từ P:
  có thể nhìn thấy tác động của E103.

Nếu E103 bị rollback sau failover:
  client từng thấy dữ liệu nhưng dữ liệu không còn trong lịch sử mới.
~~~

Đọc local không có nghĩa document bị lỗi hoặc query trả dữ liệu sai theo node; nghĩa là **mức read concern này cho phép nhìn thấy dữ liệu chưa qua majority commit point**.

### 4.2. readConcern "majority"

**majority** chỉ trả dữ liệu đã đạt trạng thái majority-committed theo semantics của read concern này. Nó thích hợp khi ứng dụng cần tránh đọc những write sau đó có thể bị rollback trong failover thông thường.

Ví dụ mongosh qua database command:

~~~javascript
const lab = db.getSiblingDB("mongo_consistency_lab");

const response = lab.runCommand({
  find: "lab_orders",
  filter: { dataset: "consistency-v1", tenantId: "t001" },
  sort: { createdAt: -1, _id: 1 },
  limit: 10,
  readConcern: { level: "majority" }
});

if (response.ok !== 1) {
  throw new Error(tojson(response));
}

printjson(response.cursor.firstBatch);
~~~

**readConcern majority không đồng nghĩa đọc mới nhất trên mọi secondary.** Nếu node đang đọc trễ so với primary, majority read có thể trả một trạng thái cũ hơn mà vẫn hợp lệ theo mức đảm bảo này.

### 4.3. readConcern "snapshot"

**snapshot** dùng khi cần đọc một ảnh chụp nhất quán tại mốc phù hợp, quan trọng trong multi-document transaction và những ngữ cảnh đọc snapshot được hỗ trợ. Ví dụ:

~~~text
Transaction đọc:
  Orders tại snapshot T
  Payments tại snapshot T
  Inventory tại snapshot T

=> các lần đọc trong transaction nhìn vào một ảnh chụp
   nhất quán theo semantics transaction.
~~~

Trong transaction, đặt **readConcern: {level:"snapshot"}** và dùng **writeConcern majority khi commit** nếu ứng dụng cần tính bền vững tương ứng.

**Snapshot không mặc nhiên là trạng thái mới nhất theo đồng hồ thực**, cũng không tự tạo transaction xuyên những hệ thống khác MongoDB.

### 4.4. readConcern "linearizable"

**linearizable** hướng tới một bảo đảm mạnh hơn về thứ tự thời gian thực của **các thao tác đọc một document từ primary**, trong phạm vi MongoDB hỗ trợ và với điều kiện dữ liệu ghi đã được majority-acknowledged theo yêu cầu tương ứng.

Tình huống thích hợp: trước khi thực hiện một quyết định quan trọng, service cần kiểm tra trạng thái một document đang được nhiều bên tranh chấp và không muốn nhận một trạng thái cũ do đổi primary.

Ví dụ command minh họa:

~~~javascript
const lab = db.getSiblingDB("mongo_consistency_lab");

const result = lab.runCommand({
  find: "lab_order_controls",
  filter: { _id: "control-001", dataset: "consistency-v1" },
  limit: 1,
  singleBatch: true,
  readConcern: { level: "linearizable" },
  maxTimeMS: 2000
});

printjson(result);
~~~

Khi dùng linearizable:

- Chọn **primary** và tuân thủ các giới hạn của mức đọc này.
- Dùng **maxTimeMS/deadline** để tránh request chờ quá lâu trong giai đoạn không có quorum.
- Xét chi phí latency; không dùng cho mọi trang danh sách chỉ vì “nghe mạnh hơn”.
- Không thay thế **conditional update** hoặc transaction để giữ invariant khi có concurrent writes.

**Read linearizable rồi update không điều kiện vẫn có khoảng race giữa hai thao tác.** Nếu yêu cầu là chỉ giảm hàng tồn khi available đủ, cách đúng là điều kiện **available >= quantity trong chính update**, không chỉ đọc một giá trị mới trước đó.

### 4.5. readConcern "available"

MongoDB có **available** trong các ngữ cảnh triển khai, đặc biệt cần chú ý ở sharded cluster. Mức đọc này hướng tới khả dụng, với ít bảo đảm hơn đối với dữ liệu có thể rollback và có các khác biệt như hành vi với orphaned documents trong một số tình huống sharding.

Không dùng available cho những quyết định cần tránh dữ liệu rollback hoặc yêu cầu nhất quán mạnh. Khi dùng trong sharding phải đọc đúng tài liệu phiên bản; không suy ra từ tên gọi rằng nó luôn “nhanh nhất và an toàn”.

### 4.6. Bảng so sánh read concern

| Mức | Mục tiêu/đặc tính chính | Điểm không nên hiểu nhầm |
| --- | --- | --- |
| **local** | Đọc trạng thái node đã áp dụng | Không bảo đảm tránh dữ liệu chưa majority-committed |
| **majority** | Đọc dữ liệu majority-committed | Không mặc nhiên mới nhất trên secondary |
| **snapshot** | Ảnh chụp nhất quán ở mốc được hỗ trợ | Không đồng nghĩa linearizable hoặc “luôn mới nhất” |
| **linearizable** | Bảo đảm mạnh về thời gian thực cho thao tác đọc một document từ primary | Chi phí/khả dụng khác; không thay conditional write |
| **available** | Ưu tiên khả dụng ở ngữ cảnh hỗ trợ | Không có bảo đảm majority; cần xem semantics sharding |

## 5. Read preference: driver chọn node đọc nào?

### 5.1. Các mode chính

| Read preference | Cách chọn node | Điểm cần cân nhắc |
| --- | --- | --- |
| **primary** | Chỉ primary cho read thông thường | Tránh độ trễ secondary nhưng primary có thể bị quá tải |
| **primaryPreferred** | Ưu tiên primary, fallback secondary khi không thể chọn primary | Khi fallback có thể trả dữ liệu cũ hơn |
| **secondary** | Chỉ secondary phù hợp | Có thể stale, và có thể không có node phù hợp |
| **secondaryPreferred** | Ưu tiên secondary, fallback primary nếu không chọn được secondary | Kết quả có thể khác độ mới giữa các lần đọc |
| **nearest** | Chọn node phù hợp dựa trên độ trễ mạng đo được, tags/staleness constraints và selection rules | Không có nghĩa “node có dữ liệu mới nhất” |

Read preference quyết định **đi đâu đọc**, còn read concern quyết định **loại trạng thái dữ liệu được phép đọc**. Hai cơ chế cùng tồn tại trong một truy vấn.

### 5.2. Đọc primary không tự loại bỏ nguy cơ rollback

Nếu primary đã áp dụng write w:1 nhưng chưa majority-committed, một read local từ **primary** có thể nhìn thấy write ấy. Sau failover, write vẫn có thể rollback.

~~~text
WRITE w:1 -> primary ACK
READ  local + primary -> thấy write
FAILOVER trước majority -> write có thể rollback
~~~

Do đó, “chỉ đọc primary” không thay thế write concern majority khi cần bảo vệ dữ liệu đã xác nhận.

### 5.3. Đọc secondary có thể stale dù dùng majority

~~~text
WRITE majority -> đã được đa số xác nhận
READ majority + secondary S2

S2 chưa áp dụng đến write:
  có thể vẫn trả dữ liệu majority-committed cũ hơn.
~~~

Vì vậy, **majority read trên secondary không tự tạo read-your-writes xuyên hai request độc lập**. Cần thiết kế session có tính nhân quả, hoặc đọc primary theo nhu cầu.

### 5.4. Tag sets, vùng địa lý và maxStalenessSeconds

Driver cho phép cấu hình read preference với **tag sets** và, khi phù hợp, **maxStalenessSeconds** để giảm khả năng chọn secondary quá trễ.

Ví dụ Node.js driver:

~~~javascript
import { ReadPreference } from "mongodb";

const preference = new ReadPreference(
  "secondaryPreferred",
  [{ region: "ap-southeast-1" }],
  { maxStalenessSeconds: 120 }
);
~~~

Tính hợp lệ của cấu hình phụ thuộc topology và driver. Với nhiều triển khai, **maxStalenessSeconds tối thiểu là 90 giây** (ngoài các chế độ thử nghiệm/đặc biệt được tài liệu cho phép), và chỉ số staleness là **ước lượng dùng để chọn node**.

**Không quảng cáo maxStalenessSeconds = 120 là SLA cứng “dữ liệu không bao giờ cũ quá 120 giây”.** Nó không thay thế causal consistency và không tự đồng bộ dữ liệu khi replica set bị trễ.

### 5.5. Secondary không chỉ dành cho “đọc rẻ”

Chuyển tải đọc sang secondary có thể giảm bớt một phần công việc trên primary, nhưng đồng thời:

- Secondary vẫn phải áp dụng replication writes.
- Truy vấn nặng có thể tăng lag hoặc tranh tài nguyên với replication.
- Mỗi node có thể khác cache warmup, disk I/O và network latency.
- Fallback của **secondaryPreferred** làm query đôi khi quay về primary.
- Nếu chỉ định tags quá hẹp, có thể không có node phù hợp.

Quyết định read preference phải được đo trên **topology thực**; không coi secondary là “miễn phí”.

## 6. Ghép ba trục: không có một tổ hợp đúng cho mọi nghiệp vụ

Hãy xem các mục tiêu phổ biến:

| Nghiệp vụ | Độ bền ghi mong muốn | Độ mới khi đọc | Chi phí có thể chấp nhận |
| --- | --- | --- | --- |
| Xác nhận đặt hàng | Rất cao | Người dùng cần thấy đơn vừa tạo | Chấp nhận chờ majority và chính sách retry rõ |
| Xử lý thanh toán | Rất cao | Không đọc trạng thái có thể rollback | Chấp nhận transaction/session và đối soát |
| Giữ tồn kho | Cao | Quyết định dựa trên trạng thái cạnh tranh hiện tại | Cần conditional atomic update, không chỉ read |
| Người dùng sửa hồ sơ rồi mở trang xem | Cao hoặc trung bình theo SLA | **Read-your-writes** | Có thể dùng primary hoặc causal session |
| Dashboard thống kê tổng quan | Theo nguồn dữ liệu | Chấp nhận chậm vài giây/phút nếu định nghĩa rõ | Có thể đọc secondary hoặc read model |
| Báo cáo ngày/tuần | Phụ thuộc dữ liệu nguồn | Có thể chấp nhận snapshot theo mốc | Có thể ưu tiên secondary/snapshot |
| Telemetry có thể phát lại | Có thể chấp nhận mất nhỏ | Không bắt buộc ngay lập tức | Chính sách nhẹ hơn nếu đã đánh giá rủi ro |
| Điều khiển trạng thái một tài nguyên duy nhất | Cao | Cần bảo đảm đọc một document có ý nghĩa thời gian thực | Cân nhắc linearizable read và guarded write |

Không nên chọn bằng cách gán nhãn “read concern mạnh nhất” cho tất cả request. Nhu cầu chính xác phải được viết thành **hợp đồng nghiệp vụ**: sau khi API báo thành công, người dùng cần thấy gì, thời gian cho phép, rủi ro rollback, khả năng chấp nhận dữ liệu cũ và hành vi khi không có quorum.

## 7. Mẫu 1 — Đặt hàng: không báo thành công trước khi ghi đủ bền

### 7.1. Hợp đồng nghiệp vụ

API **POST /orders** trả thành công khi Order đã được ghi với write concern thỏa chính sách bảo vệ failover, và một yêu cầu lặp không tạo thêm đơn.

Đề xuất khởi đầu:

- **Write:** w:"majority", với durability/journaling theo cấu hình phù hợp.
- **Read sau ghi:** primary + majority nếu cần tránh dữ liệu có thể rollback; hoặc causal session nếu đọc ở secondary mà cần read-your-writes.
- **Read preference cho API kiểm tra vừa ghi:** primary thường đơn giản hơn.
- **Idempotency:** requestId/orderId cố định và unique index thích hợp.
- **Lỗi:** write concern timeout/network timeout phải được đối chiếu, không tái tạo order bừa bãi.

### 7.2. Hai timeline

**Thiết kế dễ gặp rủi ro:**

~~~text
Client             API            P              S1/S2
  | POST /orders    |             |               |
  |---------------->| insert w:1  |               |
  |                 |------------>| apply         |
  |                 |<------------| ACK w:1       |
  |<----------------| 201 Created |               |
  | GET /orders     |             |               |
  |---------------->| secondaryPreferred          |
  |                 |---------------------------->|
  |<----------------| có thể chưa thấy Order      |
~~~

**Thiết kế phù hợp hơn khi yêu cầu bảo đảm bền vững và read-your-writes:**

~~~text
POST /orders:
  writeConcern majority + idempotency key
         |
         v
  Server đáp ứng majority -> API xác nhận
         |
         v
GET /orders:
  Đọc primary, hoặc dùng causally consistent session
  majority read khi phải đọc secondary.
~~~

**Lưu ý:** nếu POST và GET là hai HTTP request trên hai instance API khác nhau, causal session không tự được truyền xuyên request. Cần thiết kế cách duy trì/truyền context phù hợp, hoặc dùng primary read theo chính sách độ mới.

### 7.3. Hệ quả của wtimeout

Nếu POST /orders gặp wtimeout, API không được khẳng định “đơn chưa được tạo”. Có thể trả trạng thái cần kiểm tra/đối soát, giữ requestId và cung cấp endpoint truy vấn theo requestId. Lựa chọn HTTP status cụ thể phụ thuộc hợp đồng API, nhưng **không biến unknown outcome thành một xác nhận thất bại chắc chắn**.

## 8. Mẫu 2 — Read-your-writes khi người dùng vừa sửa hồ sơ

### 8.1. Bài toán

Người dùng đổi displayName thành “Minh”. API cập nhật thành công, sau đó frontend gọi GET /profile. Nếu GET chọn secondary đang trễ, người dùng có thể thấy tên cũ.

**Read concern majority riêng lẻ không khắc phục chắc chắn điều này** nếu secondary vẫn chưa áp dụng write mới.

### 8.2. Causal consistency

MongoDB hỗ trợ **causally consistent sessions**, trong những điều kiện phù hợp, để bảo vệ một số quan hệ nhân quả giữa các thao tác trong cùng session. Với mô hình được tài liệu khuyến nghị, kết hợp:

- **Write concern "majority"** cho writes trong phiên.
- **Read concern "majority"** cho reads trong phiên.
- Các thao tác được thực hiện theo đúng thứ tự, **không chạy song song tùy ý trên cùng session**.
- Dùng session/context liên quan xuyên những operation cần causal relationship.

Các đặc tính có thể bao gồm **read-your-writes**, **monotonic reads**, **monotonic writes** và **writes-follow-reads** trong phạm vi cam kết của causal consistency.

~~~text
Trong cùng causally consistent session:
    UPDATE profile (w: majority)
           |
           | causal ordering / operation time
           v
    READ profile (readConcern: majority)
    từ node phù hợp với readPreference

=> read được ràng buộc bởi causal history của session.
~~~

Khi đọc secondary chưa bắt kịp mốc cần thiết, driver/server có thể phải chờ đến mốc phù hợp hoặc gặp timeout/lỗi theo giới hạn. Causal consistency **không làm replication tức thời**.

### 8.3. Code Node.js driver

~~~javascript
import { MongoClient } from "mongodb";

async function updateThenReadProfile(uri) {
  const client = new MongoClient(uri, {
    retryWrites: true
  });
  await client.connect();

  const session = client.startSession({
    causalConsistency: true
  });

  try {
    const profiles = client
      .db("mongo_consistency_lab")
      .collection("lab_profiles");

    const filter = {
      _id: "profile-001",
      dataset: "consistency-v1",
      tenantId: "t001"
    };

    const update = await profiles.updateOne(
      filter,
      { $set: { displayName: "Minh" } },
      {
        session,
        writeConcern: {
          w: "majority",
          wtimeoutMS: 10000
        }
      }
    );

    if (update.matchedCount !== 1) {
      throw new Error("Không tìm thấy profile hợp lệ");
    }

    const readBack = await profiles.findOne(
      filter,
      {
        session,
        readConcern: { level: "majority" },
        readPreference: "secondaryPreferred",
        maxTimeMS: 5000
      }
    );

    return readBack;
  } finally {
    await session.endSession();
    await client.close();
  }
}

// await updateThenReadProfile(process.env.MONGODB_URI);
~~~

Điểm quan trọng:

1. **Cùng session** được truyền vào updateOne và findOne.
2. Update dùng **w:"majority"**, read dùng **readConcern majority**.
3. Read có thể chọn secondaryPreferred nhưng phải đáp ứng causal ordering của session.
4. Nếu không thể đáp ứng đúng thời hạn, ứng dụng phải xử lý timeout; không đổi thành dữ liệu cũ mà vẫn báo “đảm bảo read-your-writes”.
5. Đoạn code minh họa chạy trên replica set lab có sẵn profile; phần seed sẽ được cung cấp ở mục 14.

### 8.4. Session không tự tồn tại qua nhiều HTTP request

Nếu update được xử lý bởi API instance A và read bởi API instance B với session mới, **quan hệ nhân quả không tự được kế thừa**. Các hướng thiết kế:

- Đọc primary sau khi ghi cho luồng cần đơn giản và mới.
- Giữ một workflow trong cùng session ở backend khi có thể.
- Dùng cơ chế truyền causal context/cluster time theo tài liệu driver khi kiến trúc thật sự cần; phải kiểm soát nguồn và cách sử dụng metadata.
- Thiết kế UI optimistic và tự làm mới có kiểm soát nếu nghiệp vụ chấp nhận eventual visibility.

Không nên dùng một MongoDB ClientSession như đối tượng toàn cục để nhiều request đồng thời cùng thao tác. ClientSession không được thiết kế để tùy ý chạy nhiều operation song song với cùng ngữ cảnh nhân quả/transaction.

## 9. Mẫu 3 — Tồn kho: tính đúng đắn đến từ conditional write

### 9.1. Chỉ đọc mức concern mạnh chưa đủ chống oversell

Giả sử có **available = 1**:

~~~text
Request A: đọc available=1
Request B: đọc available=1

A: giảm 1
B: giảm 1

Nếu cả hai chỉ dựa vào kết quả đọc rồi ghi không điều kiện,
available có thể âm hoặc một update ghi đè update khác.
~~~

Dù A và B đều đọc với **linearizable read** đúng phạm vi, vẫn có khoảng thời gian giữa read và update. **Read concern không thay thế atomic conditional update.**

### 9.2. Cập nhật đúng với filter có điều kiện

~~~javascript
const stock = db.getSiblingDB("mongo_consistency_lab")
  .getCollection("lab_stock");

const result = stock.updateOne(
  {
    _id: "sku-001",
    dataset: "consistency-v1",
    tenantId: "t001",
    available: { $gte: 1 }
  },
  {
    $inc: {
      available: -1,
      reserved: 1,
      version: 1
    }
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);

printjson(result);
~~~

Một update trên một document là nguyên tử, gồm cả điều kiện filter. Nếu chỉ còn 0, thao tác tiếp theo không khớp filter. **w:"majority"** giúp bảo vệ kết quả ghi khỏi rollback failover bình thường sau acknowledged thành công; **filter** bảo vệ invariant available không âm.

Để chống **cùng request gửi lại**, cần thêm reservationId/idempotency. Nếu reservation và stock nằm ở **nhiều document**, có thể cần transaction hoặc mô hình event/ledger.

### 9.3. Chính sách đọc tồn kho

- Trên trang sản phẩm, có thể chấp nhận số lượng tồn hiển thị chậm vài giây (tùy SLA), vì đây chỉ là thông tin tham khảo.
- Ở thời điểm **giữ hàng/checkout**, dùng **conditional write vào primary**, không tin giá trị tồn kho đã hiển thị.
- Khi kiểm tra một reservation vừa tạo, chọn primary hoặc causal session phù hợp để tránh trạng thái cũ.
- Với đơn đã xác nhận, bảo đảm durability và có cơ chế đối soát khi nhận timeout.

Một nghiệp vụ có thể dùng **hai chính sách đọc khác nhau cho cùng một field** vì mục đích khác nhau.

## 10. Mẫu 4 — Dashboard và báo cáo: chấp nhận lag có chủ đích

### 10.1. Trang tổng quan

Dashboard hiển thị tổng số đơn trong hôm nay có thể chấp nhận dữ liệu trễ một khoảng nhỏ đã công bố. Khi đó:

- Dữ liệu Order được ghi với chính sách durability thích hợp.
- Truy vấn báo cáo có thể dùng **secondaryPreferred** hoặc chạy trên read model.
- **readConcern majority** nếu cần tránh tính trên dữ liệu có thể rollback.
- Đo replication lag và xác định freshness của response.
- API có thể trả **asOf** hoặc thời điểm dữ liệu được tính, thay vì ngụ ý “real-time tuyệt đối”.

**Không hạ write concern của Order xuống w:1 chỉ vì dashboard có thể trễ.** Độ bền của nguồn dữ liệu và độ mới của màn hình là hai quyết định riêng.

### 10.2. Báo cáo cần tính nhất quán giữa nhiều collection

Nếu báo cáo tính tổng từ Orders và Payments rồi so sánh, đọc hai collection ở hai thời điểm không đồng bộ có thể cho tỷ lệ tạm thời sai. Khi yêu cầu một **ảnh chụp logic nhất quán**, có thể dùng transaction đọc **snapshot** hoặc một cơ chế snapshot/read model phù hợp.

Không dùng hai truy vấn majority độc lập rồi mặc nhiên coi chúng cùng snapshot:

~~~text
READ Orders với readConcern majority tại T1
          ...
WRITE Payment commit giữa hai lần đọc
          ...
READ Payments với readConcern majority tại T2

=> T1 và T2 có thể khác nhau.
~~~

Read concern majority bảo vệ tính chất rollback của dữ liệu được đọc, **không tự đồng bộ các lời gọi độc lập về cùng một mốc snapshot**.

### 10.3. Không dùng secondary làm nơi thoát mọi tải nặng

Một truy vấn aggregation trên secondary có thể:

- Cạnh tranh I/O với replication.
- Gây lag cao hơn.
- Làm cache của secondary không còn tối ưu cho reads thông thường.
- Bị chậm khi topology thay đổi.

Với báo cáo nặng, cân nhắc **materialized summary**, batch job, read replica được sizing phù hợp và chính sách stale/timeout rõ ràng.

## 11. Mẫu 5 — Payment và audit: toàn vẹn xuyên document

### 11.1. Yêu cầu

Payment API thường phải:

- Không ghi nhận cùng một payment hai lần.
- Khi chuyển trạng thái Order paid thì ghi Payment/Audit đúng.
- Một kết quả “đã xác nhận” chịu được failover thông thường.
- Sau mất kết nối, service xác định được payment đã commit hay chưa.

Một tổ hợp thường cần xem xét:

| Giai đoạn | Công cụ |
| --- | --- |
| Xác thực request/payment | Business validation, unique idempotency key |
| Cập nhật Order + Payment + Outbox | **Transaction** nhiều document |
| Đọc trong transaction | **readConcern snapshot** khi phù hợp |
| Commit transaction | **writeConcern "majority"** |
| Đọc sau commit | Primary + majority, hoặc causal session khi cần |
| Mất response commit | Driver transaction retry/reconciliation theo requestId |
| Gọi cổng thanh toán/email bên ngoài | Outbox/saga và idempotency, **không** coi là cùng MongoDB transaction |

**readPreference** cho thao tác transaction thường là **primary**. Không cố chuyển writes trong transaction sang secondary.

### 11.2. Ví dụ transaction Node.js

~~~javascript
import { MongoClient } from "mongodb";

async function markPaid(uri, orderId, paymentId) {
  const client = new MongoClient(uri, { retryWrites: true });
  await client.connect();

  const session = client.startSession();
  const lab = client.db("mongo_consistency_lab");
  const orders = lab.collection("lab_orders");
  const payments = lab.collection("lab_payments");

  try {
    await session.withTransaction(async () => {
      // _id của Payment đại diện idempotency key cho lab.
      const already = await payments.findOne(
        { _id: paymentId, dataset: "consistency-v1" },
        { session }
      );

      if (already) {
        if (already.orderId !== orderId) {
          throw new Error("paymentId đã gắn với Order khác");
        }
        return;
      }

      const updated = await orders.updateOne(
        {
          _id: orderId,
          dataset: "consistency-v1",
          tenantId: "t001",
          status: "created"
        },
        {
          $set: { status: "paid" },
          $currentDate: { paidAt: true }
        },
        { session }
      );

      if (updated.matchedCount !== 1) {
        throw new Error("Order không ở trạng thái hợp lệ");
      }

      await payments.insertOne(
        {
          _id: paymentId,
          dataset: "consistency-v1",
          tenantId: "t001",
          orderId,
          status: "recorded",
          createdAt: new Date()
        },
        { session }
      );
    }, {
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" },
      readPreference: "primary"
    });
  } finally {
    await session.endSession();
    await client.close();
  }
}

// Chỉ chạy trên replica set lab sau khi seed ở mục 14.
// await markPaid(process.env.MONGODB_URI, "order-001", "pay-001");
~~~

Đoạn ví dụ chỉ mô phỏng việc ghi trạng thái Payment **trong MongoDB**, không gọi hay thực hiện thanh toán thật. Với request đồng thời dùng cùng paymentId, cần xử lý duplicate key/write conflict và kiểm tra lại commit outcome; không chỉ dựa vào câu findOne trước insert. Unique _id bảo vệ một phần idempotency trong database.

**withTransaction có thể retry callback.** Không gọi payment gateway hoặc gửi email không idempotent bên trong callback.

### 11.3. Majority không tự bảo đảm đúng nghiệp vụ

Nếu một thao tác ghi sai số tiền rồi được majority-committed, majority bảo vệ **giá trị sai ấy** khỏi rollback thông thường. Để tránh sai:

- Unique index và idempotency.
- Điều kiện trạng thái trong filter.
- Transaction boundary đúng.
- Validation/currency handling.
- Reconciliation và audit.

Chọn concern là cần thiết nhưng chưa đủ.

## 12. Causal consistency, snapshot và linearizable: chọn khác nhau

Ba thuật ngữ có thể đều được gọi chung là “đọc nhất quán”, nhưng phục vụ các bài toán riêng.

### 12.1. Causal consistency

Mục tiêu: bảo toàn quan hệ nhân quả của các operation trong một phiên, chẳng hạn **ghi hồ sơ rồi đọc hồ sơ**.

Đặc tính chính:

- Gắn với **session context** và thứ tự hoạt động.
- Có thể cho phép đọc từ secondary với readPreference phù hợp.
- Dựa trên majority reads/writes cho bảo đảm nhân quả như tài liệu nêu.
- Không làm secondary bắt kịp tức thì; có thể chờ hoặc timeout.

### 12.2. Snapshot consistency

Mục tiêu: nhiều lần đọc thấy **một ảnh chụp logic nhất quán** để phân tích/giao dịch, tránh kết hợp dữ liệu ở các mốc khác nhau.

Đặc tính chính:

- Rất hữu ích với multi-document transactions.
- Không mặc nhiên trả dữ liệu mới nhất theo thời gian thực.
- Có chi phí tài nguyên, transaction lifetime và xử lý write conflict.
- Không thay thế idempotency hoặc write concern khi commit.

### 12.3. Linearizable read

Mục tiêu: đảm bảo mạnh về thứ tự thời gian thực cho thao tác đọc một document trong phạm vi hỗ trợ, với primary và điều kiện ghi thích hợp.

Đặc tính chính:

- Phù hợp một số quyết định trạng thái quan trọng.
- Có thể chờ trong một số trạng thái không có quorum; đặt maxTimeMS.
- Không tự biến read–modify–write thành thao tác nguyên tử.
- Không phải lựa chọn mặc định cho dashboard hoặc phân trang hàng triệu document.

### 12.4. Bảng lựa chọn

| Mục tiêu | Công cụ chủ đạo | Không đủ nếu chỉ dùng |
| --- | --- | --- |
| Vừa ghi xong phải đọc được chính ghi đó | **Causal session** hoặc đọc primary theo hợp đồng | readConcern majority trên secondary độc lập |
| Một báo cáo đọc nhiều collection tại cùng snapshot | **Snapshot** trong transaction/đọc snapshot hỗ trợ | Hai read majority độc lập |
| Đọc trạng thái một document với bảo đảm thời gian thực mạnh | **Linearizable** từ primary | secondaryPreferred |
| Giảm hàng tồn nhưng không âm | **Conditional atomic update** | linearizable read rồi update không điều kiện |
| Commit Order + Payment cùng nhau | **Transaction + majority commit** | Chỉ dùng w:majority cho hai updateOne độc lập |
| Không mất Order đã xác nhận vì rollback bình thường | **w:"majority"** | Chỉ đọc primary |

## 13. Tình huống lỗi và cách đọc nguyên nhân

### 13.1. “POST thành công nhưng GET rỗng”

Các nguyên nhân cần kiểm tra theo thứ tự:

1. GET có đúng **tenantId**, _id và filter không?
2. POST có dùng đúng write concern và nhận acknowledged success hay chỉ timeout?
3. GET có chọn secondary không? Secondary lag bao nhiêu?
4. GET dùng readConcern gì?
5. POST/GET có cùng causal session hay không?
6. Có election/failover, rollback hoặc write conflict gần đó?
7. Có cache/queue/eventual read model ở tầng ứng dụng không?

Không kết luận “MongoDB mất dữ liệu” từ một lần GET rỗng. Một query sai tenant hoặc secondary stale có thể tạo triệu chứng giống nhau.

### 13.2. “Đã đọc thấy rồi sau đó biến mất”

Nếu dữ liệu từng đọc với readConcern local trên primary, và write chưa majority-committed, rollback có thể là lời giải thích. Nhưng cũng có thể có một lệnh delete/update hợp lệ của ứng dụng.

Để điều tra:

- Kiểm tra write concern của thao tác tạo.
- Xem thời điểm election/stepdown.
- Xem log hoặc tín hiệu rollback.
- Đối chiếu audit/transaction/outbox.
- Kiểm tra quyền và truy vấn, tránh tự sửa dữ liệu trên production khi chưa rõ nguyên nhân.

### 13.3. “Majority write thường xuyên timeout”

Đây có thể là:

- Không đủ data-bearing voting members khỏe mạnh.
- Secondary lag, disk I/O hoặc network congestion.
- Workload write quá lớn hoặc index maintenance tốn kém.
- Timeout thiết lập quá ngắn so với latency thực.
- Cấu hình replica set có arbiter hoặc member đặc biệt khiến cách tính khác kỳ vọng.

**Không âm thầm đổi về w:1** nếu dữ liệu có yêu cầu chống rollback. Điều tra quorum và replication trước khi nới chính sách.

### 13.4. “Đọc secondary nhanh hơn nhưng số liệu khác nhau”

Đọc từ secondary có thể stale ở các mức độ khác nhau. Với **nearest**, driver có thể chọn node khác qua từng lần; mỗi node có tiến độ replication khác nhau. Nếu ứng dụng yêu cầu monotonic reads hoặc read-your-writes, dùng causal session đúng cách hoặc chọn primary, không phụ thuộc vào may mắn của node selection.

### 13.5. “Đặt maxStalenessSeconds rồi vẫn không đúng SLA”

maxStalenessSeconds là cơ chế **node selection** dựa trên độ trễ ước lượng, không phải cam kết snapshot tươi tối đa tuyệt đối cho từng record. Để có SLA freshness chặt chẽ, cần cơ chế đo/đồng bộ mốc dữ liệu, kiểm tra timestamp/asOf và thiết kế fallback khi không có nguồn đủ mới.

## 14. Lab mongosh: dữ liệu cố định và các lệnh quan sát an toàn

Các ví dụ dưới đây chỉ dùng **replica set riêng cho thực hành**. Không chủ động tắt node hoặc gây election/rollback. Mục tiêu là quan sát được cách cấu hình và nhìn thấy dữ liệu sau khi write concern được đáp ứng.

### 14.1. Kiểm tra topology

~~~javascript
(() => {
  const hello = db.hello();

  printjson({
    setName: hello.setName,
    primary: hello.primary,
    isWritablePrimary: hello.isWritablePrimary,
    hosts: hello.hosts
  });

  if (!hello.setName) {
    throw new Error("Cần kết nối tới replica set lab");
  }
})();
~~~

Lệnh **db.hello()** không thay đổi cấu hình. Nếu không có setName thì môi trường không phải replica set như bài yêu cầu. Trên standalone, không thể quan sát majority replication/election như trên ba data-bearing nodes.

### 14.2. Seed ba collection thực hành

Database: **mongo_consistency_lab**.

Nhãn: **consistency-v1**.

Chạy nguyên khối bằng mongosh:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_consistency_lab");
  const tag = "consistency-v1";
  const orders = lab.getCollection("lab_orders");
  const profiles = lab.getCollection("lab_profiles");
  const stock = lab.getCollection("lab_stock");
  const controls = lab.getCollection("lab_order_controls");
  const payments = lab.getCollection("lab_payments");

  // Dữ liệu lab: chỉ dọn document có đúng nhãn dataset.
  const collections = [orders, profiles, stock, controls, payments];
  for (const collection of collections) {
    collection.deleteMany(
      { dataset: tag },
      { writeConcern: { w: "majority", wtimeout: 10000 } }
    );
  }

  orders.insertMany(
    [
      {
        _id: "order-001",
        dataset: tag,
        tenantId: "t001",
        status: "created",
        amount: NumberDecimal("100.00"),
        createdAt: ISODate("2026-01-01T08:00:00.000Z")
      },
      {
        _id: "order-002",
        dataset: tag,
        tenantId: "t001",
        status: "created",
        amount: NumberDecimal("200.00"),
        createdAt: ISODate("2026-01-02T08:00:00.000Z")
      },
      {
        _id: "order-003",
        dataset: tag,
        tenantId: "t002",
        status: "created",
        amount: NumberDecimal("300.00"),
        createdAt: ISODate("2026-01-03T08:00:00.000Z")
      }
    ],
    { writeConcern: { w: "majority", wtimeout: 10000 } }
  );

  profiles.insertOne(
    {
      _id: "profile-001",
      dataset: tag,
      tenantId: "t001",
      displayName: "Tên ban đầu",
      version: NumberInt(0)
    },
    { writeConcern: { w: "majority", wtimeout: 10000 } }
  );

  stock.insertOne(
    {
      _id: "sku-001",
      dataset: tag,
      tenantId: "t001",
      available: NumberInt(2),
      reserved: NumberInt(0),
      version: NumberInt(0)
    },
    { writeConcern: { w: "majority", wtimeout: 10000 } }
  );

  controls.insertOne(
    {
      _id: "control-001",
      dataset: tag,
      tenantId: "t001",
      enabled: true
    },
    { writeConcern: { w: "majority", wtimeout: 10000 } }
  );

  orders.createIndex(
    { dataset: 1, tenantId: 1, createdAt: -1, _id: 1 },
    { name: "ix_consistency_lab_tenant_time" }
  );

  printjson({
    orders: orders.countDocuments({ dataset: tag }),
    profiles: profiles.countDocuments({ dataset: tag }),
    stock: stock.countDocuments({ dataset: tag }),
    controls: controls.countDocuments({ dataset: tag }),
    payments: payments.countDocuments({ dataset: tag })
  });
})();
~~~

**Kết quả mong đợi khi replica set có đủ majority:** 3 orders, 1 profile, 1 stock, 1 control, 0 payments.

Script không drop collection hay database; nhưng các deleteMany/insert là những thao tác riêng, **không phải một transaction chung**. Chỉ dùng trên database thực hành và tránh đồng thời chạy các thí nghiệm khác trên cùng nhãn dataset.

### 14.3. Ghi với majority rồi đọc local

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_consistency_lab");
  const orders = lab.getCollection("lab_orders");
  const tag = "consistency-v1";

  const result = orders.insertOne(
    {
      _id: "order-majority-004",
      dataset: tag,
      tenantId: "t001",
      status: "created",
      amount: NumberDecimal("50.00"),
      createdAt: ISODate("2026-01-04T08:00:00.000Z")
    },
    {
      writeConcern: { w: "majority", wtimeout: 10000 }
    }
  );

  printjson(result);
  printjson(orders.findOne({
    _id: "order-majority-004",
    dataset: tag
  }));
})();
~~~

Khi lệnh được acknowledged majority, document đã đạt mức xác nhận yêu cầu. **findOne mặc định ở kết nối primary** có thể thấy document; tuy nhiên thao tác đọc mặc định theo cấu hình client không tự chứng minh mọi loại read concern đều đã được kiểm thử.

Chạy lại cùng _id có thể nhận duplicate key; đó là hậu quả có chủ đích của ID cố định, không phải tín hiệu thất bại của lần đầu. Khi muốn làm lại, chạy lại seed.

### 14.4. Đọc một snapshot majority bằng command

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_consistency_lab");
  const result = lab.runCommand({
    find: "lab_orders",
    filter: {
      dataset: "consistency-v1",
      tenantId: "t001"
    },
    sort: { createdAt: -1, _id: 1 },
    limit: 10,
    singleBatch: true,
    readConcern: { level: "majority" }
  });

  if (result.ok !== 1) {
    throw new Error(tojson(result));
  }

  printjson(result.cursor.firstBatch);
})();
~~~

Kết quả gồm các order t001 đã majority-committed tại mốc phục vụ read. Nếu vừa chạy bước insert majority, order-majority-004 thuộc tập kết quả. **Tùy phiên mongosh/server và topology**, việc chỉ định readPreference khi đọc từ secondary nên được thực hiện qua cấu hình kết nối/driver; command trên không tự chuyển node sang secondary.

### 14.5. Ghi với w:1

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_consistency_lab");
  const orders = lab.getCollection("lab_orders");

  const result = orders.insertOne(
    {
      _id: "order-w1-005",
      dataset: "consistency-v1",
      tenantId: "t001",
      status: "created",
      amount: NumberDecimal("20.00"),
      createdAt: ISODate("2026-01-05T08:00:00.000Z")
    },
    { writeConcern: { w: 1 } }
  );

  printjson(result);
})();
~~~

Trên replica set lab khỏe mạnh, order-w1-005 cũng có thể nhanh chóng majority-commit và xuất hiện ở các lệnh đọc majority sau đó. **Thực tế đó không chứng minh w:1 có bảo đảm tương đương w:"majority"**. Khác biệt nằm ở **điều kiện acknowledgment tại thời điểm response**, không nhất thiết ở dữ liệu nhìn thấy vài giây sau.

### 14.6. Đọc replica set status

~~~javascript
const status = rs.status();

printjson({
  set: status.set,
  myState: status.myState,
  optimes: status.optimes
});

printjson(
  status.members.map(m => ({
    name: m.name,
    state: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate
  }))
);
~~~

Nếu đủ quyền, hãy quan sát các trường như **lastCommittedOpTime**, **appliedOpTime**, **durableOpTime**, cũng như vai trò PRIMARY/SECONDARY và độ trễ. Đây là **ảnh chụp trạng thái**, không phải một phép chứng minh từng request cụ thể đã commit ra sao nếu không có thông tin thời điểm/acknowledgment.

Không cần chạy rs.stepDown, rs.reconfig hoặc tắt node. Để học rollback, dùng sơ đồ và bài tập tư duy thay vì gây sự cố trên máy chia sẻ.

## 15. Node.js driver: cấu hình theo operation và theo workflow

### 15.1. Mặc định ở MongoClient

Một ứng dụng có thể đặt chính sách mặc định ở client:

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(process.env.MONGODB_URI, {
  readPreference: "primary",
  readConcern: { level: "majority" },
  writeConcern: {
    w: "majority",
    wtimeoutMS: 10000
  },
  retryWrites: true
});

await client.connect();

try {
  const orders = client
    .db("mongo_consistency_lab")
    .collection("lab_orders");

  const result = await orders.findOne({
    _id: "order-001",
    dataset: "consistency-v1"
  });

  console.log(result);
} finally {
  await client.close();
}
~~~

Đặt mặc định giúp giảm trường hợp một API vô tình dùng w:1 hoặc local khi sản phẩm yêu cầu chính sách mạnh hơn. Tuy nhiên, **không phải mọi operation đều cần cùng read preference**: báo cáo có thể chọn secondaryPreferred bằng cấu hình ở operation/collection thích hợp, trong khi checkout vẫn dùng primary.

### 15.2. Chính sách riêng cho dashboard

~~~javascript
const dashboard = await orders.aggregate(
  [
    {
      $match: {
        dataset: "consistency-v1",
        tenantId: "t001"
      }
    },
    {
      $group: {
        _id: "$status",
        count: { $sum: 1 }
      }
    }
  ],
  {
    readPreference: "secondaryPreferred",
    readConcern: { level: "majority" },
    maxTimeMS: 3000
  }
).toArray();
~~~

Mẫu này giả định biến **orders** là MongoCollection trong một scope Node.js đã kết nối. Với dashboard, khi chấp nhận lag, secondaryPreferred có thể hợp lý. **Không hứa giá trị mới nhất** chỉ vì dùng majority.

### 15.3. Chính sách riêng cho quyết định ghi

~~~javascript
const updated = await stock.updateOne(
  {
    _id: "sku-001",
    dataset: "consistency-v1",
    tenantId: "t001",
    available: { $gte: 1 }
  },
  {
    $inc: { available: -1, reserved: 1 }
  },
  {
    writeConcern: {
      w: "majority",
      wtimeoutMS: 10000
    }
  }
);

if (updated.matchedCount !== 1) {
  throw new Error("Không đủ tồn kho hoặc dữ liệu không hợp lệ");
}
~~~

Biến **stock** phải là MongoCollection hợp lệ. Đây là cập nhật một document nguyên tử có filter bảo vệ invariant; nó không dùng read preference vì **writes gửi tới primary**. Nếu ràng buộc qua nhiều document, thiết kế transaction cần xét riêng.

### 15.4. Định nghĩa chính sách ở đúng tầng

MongoDB drivers thường hỗ trợ kế thừa/override một số option giữa client, database, collection và operation. Khi một nhóm API đặt option riêng, hãy:

- Biết cấu hình nào sẽ được áp ở từng thao tác.
- Tránh mâu thuẫn giữa URI và code.
- Thử nghiệm failover và timeout trên staging.
- Gắn telemetry cho các thao tác thật sự dùng w/readConcern/readPreference nào.
- Không tin rằng một comment trong code nói “strong consistency” khi runtime option bị override.

Tổ chức code nên có helper đặt tên theo **nghiệp vụ** như “confirmedOrderWrite” hoặc “staleTolerantDashboardRead”, thay vì dùng một enum mơ hồ “strong/weak” không mô tả chính xác bảo đảm.

## 16. Thiết kế ma trận chính sách cho một hệ thống thực tế

Giả sử ứng dụng có năm luồng quan trọng. Một ma trận chính sách ban đầu có thể là:

| Luồng | Write concern | Read concern | Read preference | Ghi chú |
| --- | --- | --- | --- | --- |
| Tạo Order được xác nhận | majority | majority khi kiểm tra trạng thái | primary | requestId/idempotency; xử lý unknown outcome |
| Payment và Outbox commit | majority tại transaction commit | snapshot trong transaction | primary | Atomic nhiều document, kiểm tra status/unique |
| Người dùng vừa sửa profile | majority nếu cần tránh rollback | majority | primary hoặc secondaryPreferred **trong causal session** | Đảm bảo read-your-writes theo phạm vi workflow |
| Dashboard tổng đơn | Nguồn Order vẫn theo policy riêng | majority nếu cần dữ liệu không rollback | secondaryPreferred | Cho phép dữ liệu cũ, gắn asOf/lag |
| Hiển thị tồn kho tham khảo | Reservation writes majority | local/majority theo yêu cầu trang | secondaryPreferred nếu chấp nhận lag | Checkout phải dùng conditional write |
| Admin kiểm tra một control doc quan trọng | majority khi ghi control | cân nhắc linearizable | primary | Read hiện tại mạnh, maxTimeMS, không thay conditional update |
| Báo cáo đối soát nhiều collection | majority trên nguồn | snapshot phù hợp | primary cho transaction | Cần cùng mốc snapshot, không chỉ hai read majority |

Đây là **đề xuất khởi đầu**, không phải preset bắt buộc cho mọi tổ chức. Chính sách cuối phải phụ thuộc:

- Mức mất dữ liệu chấp nhận được sau API báo thành công.
- SLA thời gian ghi/đọc.
- Cho phép dữ liệu cũ bao nhiêu?
- Có cần đọc chính ghi vừa tạo trong một phiên không?
- Có nhiều document phải nhất quán với nhau không?
- Topology, số voting/data-bearing members, journaling và sharding.
- Khả năng chịu lỗi/mất quorum và hành vi khi không thể cung cấp mức nhất quán yêu cầu.

### 16.1. Phân loại theo hai trục quyết định

~~~text
                        Độ mới của READ
                  Có thể trễ         Cần mới/nhân quả
Độ bền WRITE  +------------------+------------------------+
  cao         | Dashboard dựa     | Đặt hàng; payment;     |
              | trên Order bền    | hồ sơ vừa cập nhật     |
              | vững              |                        |
              +------------------+------------------------+
  thấp hơn    | Telemetry có thể  | Trạng thái tạm thời    |
              | phát lại          | trong một session,     |
              |                   | nhưng phải xét rollback|
              +------------------+------------------------+
~~~

Một lỗi thiết kế phổ biến là gộp hai trục thành một nút “strong consistency”. Một dashboard có thể cần **nguồn write rất bền vững** nhưng **read trễ được**. Một màn hình nội bộ có thể đọc primary rất mới nhưng dữ liệu vốn được ghi w:1 và vẫn có nguy cơ rollback.

## 17. Sự cố, timeout và xử lý tính không chắc chắn

### 17.1. Ba trạng thái của một write

Ứng dụng nên phân biệt ít nhất:

1. **ACK thành công theo write concern yêu cầu**.
2. **Thất bại chắc chắn trước khi write được áp dụng**, nếu driver/server có thể chứng minh.
3. **Không biết kết quả cuối**: lỗi mạng, write concern timeout hoặc commit result chưa rõ.

Phân loại thứ ba rất quan trọng. Không thể cứ coi timeout là “lệnh chưa chạy”.

### 17.2. Retryable writes và idempotency

Drivers có thể hỗ trợ **retryable writes** trên replica set/sharded cluster cho những thao tác đủ điều kiện, giúp retry cùng một statement khi có lỗi tạm thời trong phạm vi cơ chế. Nhưng:

- Không phải mọi operation là retryable.
- Không phải một HTTP request mới sẽ dùng lại cùng statement identity.
- Một lệnh $inc được gửi lại như nghiệp vụ mới có thể trừ hai lần.
- Bulk workflow và tác động bên ngoài MongoDB cần thiết kế riêng.

Với Order/Payment, dùng **idempotency key** và kiểm tra payload tương ứng. Nếu có nhiều bước MongoDB cần atomically commit, dùng transaction; nếu có side effect ngoài database, dùng outbox/saga.

### 17.3. Nếu không đạt majority

Khi không đủ quorum hoặc secondary chưa bắt kịp, API có thể:

- Chờ trong ngân sách đã được thiết kế.
- Trả trạng thái tạm thời không thể xác nhận và cho phép đối chiếu sau.
- Ghi queue durable phù hợp (nếu có hệ thống đáp ứng yêu cầu).
- Từ chối nghiệp vụ quan trọng thay vì hạ mức durability.

**Không âm thầm hạ từ majority xuống w:1 cho giao dịch tài chính** chỉ để có response nhanh, trừ khi có một quyết định nghiệp vụ đã chấp nhận rủi ro và thiết kế bù trừ rõ ràng.

### 17.4. Timeout của read linearizable/causal

Một read có yêu cầu mạnh có thể phải chờ node đạt trạng thái cần thiết. Đặt **maxTimeMS** hoặc deadline client tương ứng; khi không đáp ứng được, trả lỗi phù hợp thay vì chuyển sang một read stale mà vẫn gọi đó là kết quả nhất quán mạnh.

Với màn hình chỉ mang tính gợi ý, có thể chủ động fallback sang dữ liệu stale **nếu hợp đồng cho phép** và response thể hiện điều đó. Còn với một quyết định được dùng để trừ tiền, không nên fallback âm thầm.

## 18. Tác động của topology: arbiter, hidden/delayed secondary và sharding

### 18.1. Arbiter

Trong replica set **Primary–Secondary–Arbiter (PSA)**:

~~~text
P: data-bearing, vote
S: data-bearing, vote
A: arbiter, vote, KHÔNG giữ bản sao dữ liệu
~~~

Arbiter tham gia bầu cử nhưng **không sao chép document/oplog như data-bearing member**. Không được tính arbiter như một bản sao đã giữ dữ liệu khi thảo luận majority write concern. Nếu S không sẵn sàng, P có thể không thể thỏa mãn majority replication chỉ bằng arbiter, dù tình trạng phiếu bầu còn những sắc thái riêng.

### 18.2. Hidden/delayed secondary

Một secondary có thể không được driver chọn cho reads thông thường hoặc được cấu hình trễ replication. Điều này ảnh hưởng khả năng dùng read preference, độ mới và chính sách phục hồi.

Không yêu cầu mọi secondary đều thích hợp để đọc báo cáo. Khi chọn tag sets/secondaryPreferred, hãy kiểm tra member có đủ điều kiện phục vụ read và hiểu trạng thái delayed/hidden/priority.

### 18.3. Sharded cluster

Với sharded MongoDB, một truy vấn có thể đi qua mongos và nhiều shard. Các option read concern, write concern và read preference vẫn liên quan, nhưng:

- Một operation có thể chạm nhiều shard với tiến độ replication khác nhau.
- Snapshot/cross-shard transactions có thêm chi phí và quy tắc triển khai.
- Read preference có thể chọn các replica set members ở từng shard theo chính sách.
- Cần xem shard key/targeting để tránh truy vấn phân tán không cần thiết.
- Một global SLA về freshness không tự suy ra từ một maxStalenessSeconds cục bộ.

Không lấy ví dụ replica set 3 node để khẳng định mọi sharded query có độ mới/độ trễ giống nhau.

## 19. Theo dõi để biết chính sách có đang hoạt động không

### 19.1. Những metric cốt lõi

| Metric | Câu hỏi |
| --- | --- |
| **Write concern majority latency p50/p95/p99** | Xác nhận bền vững mất bao lâu? |
| **Write concern timeout/errors** | Có đang thiếu quorum hoặc secondary quá chậm không? |
| **Primary stepdown/election events** | Failover diễn ra thường xuyên không? |
| **lastCommittedOpTime** | Majority commit point tiến ra sao? |
| **Applied/durable optime** | Thành viên theo kịp tới mốc nào? |
| **Replication lag per secondary** | Secondary nào thường bị trễ? |
| **Read preference distribution** | Read thực tế đang chạy trên primary/secondary nào? |
| **Read concern distribution** | Có API bị cấu hình local ngoài dự kiến không? |
| **Causal read wait/timeout** | Có node không theo kịp causal history? |
| **Transaction abort/write conflicts** | Có tranh chấp làm request phải retry không? |
| **Application stale-data reports** | Người dùng gặp stale UI ở những màn hình nào? |
| **Unknown write outcomes/reconciliation** | Bao nhiêu request cần đối soát trạng thái? |

Khi đo, phân nhóm theo **endpoint, query shape và nghiệp vụ**, không chỉ theo tổng số query của toàn MongoDB cluster.

### 19.2. Nhìn rs.status()

~~~javascript
const s = rs.status();

printjson({
  set: s.set,
  optimes: s.optimes,
  members: s.members.map(m => ({
    name: m.name,
    state: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate
  }))
});
~~~

Cấu trúc trường có thể thay đổi theo phiên bản, nhưng các mốc như **lastCommittedOpTime**, **appliedOpTime**, **durableOpTime** và trạng thái từng thành viên là những khái niệm cần quan sát. Chúng là **snapshot** tại thời điểm hỏi; không tự chứng minh outcome của một request cụ thể nếu thiếu log hoặc thông tin acknowledgment.

### 19.3. Không chỉ theo dõi replication lag trung bình

Với P/S1/S2, S2 có thể trễ 20 giây nhưng P+S1 vẫn đáp ứng majority. Ngược lại, nếu S1 cũng mất kết nối, P không thể dựa vào S2 đang trễ để xác nhận write majority ngay lập tức.

Do đó, cần nhìn **commit point, member health và topology**, không chỉ một số replication lag trung bình.

### 19.4. Ghi nhận freshness của báo cáo

Với dashboard stale-tolerant, có thể cung cấp metadata:

~~~javascript
{
  "data": {
    "paidOrders": 1432
  },
  "asOf": "2026-11-14T03:00:00.000Z",
  "consistencyPolicy": "majority-committed, stale-tolerant"
}
~~~

Đây là **hình dạng response do ứng dụng tự thiết kế**, không phải response MongoDB tự động trả. **asOf** phải có nguồn đáng tin cậy từ quá trình tổng hợp hoặc dữ liệu nguồn; không điền thời điểm “now” nếu số liệu thực tế được tính từ dữ liệu cũ.

## 20. Checklist thiết kế trước khi đưa một API vào production

### 20.1. Với thao tác ghi

Hãy trả lời:

1. Dữ liệu có thể tái tạo được không?
2. API đã báo thành công thì có được phép rollback sau failover không?
3. Cần cập nhật một document hay nhiều document cùng nguyên tử?
4. Có uniqueness, idempotency và conditional updates chưa?
5. Nếu wtimeout/network timeout, có endpoint/cơ chế đối chiếu không?
6. Config journal/majority của replica set thực tế là gì?
7. Mức write concern có kế thừa/override từ client hoặc collection không?

### 20.2. Với thao tác đọc

Hãy trả lời:

1. Có chấp nhận đọc giá trị chưa majority-committed không?
2. Có chấp nhận dữ liệu cũ bao lâu?
3. Có cần đọc được đúng thay đổi vừa ghi trong một session không?
4. Có cần nhiều collection cùng snapshot không?
5. Có cần đọc một control document với semantics thời gian thực mạnh không?
6. Read preference có thể fallback sang loại node khác không?
7. Khi không có node đủ điều kiện, ứng dụng fail hay downgrade có chủ đích?

### 20.3. Với vận hành

Hãy trả lời:

1. Replica set có bao nhiêu data-bearing voting members và arbiter?
2. Dashboard có hiển thị lastCommittedOpTime/replication lag không?
3. Có cảnh báo majority write timeout và election liên tục không?
4. Có log cấu hình concern thực tế theo endpoint không?
5. Có backup/PITR và diễn tập khôi phục độc lập với replication không?
6. Có test các trường hợp client mất response, delayed secondary, failover trên staging không?

Một chính sách tốt phải được **đo được và thực thi được khi có sự cố**, không chỉ có trong tài liệu kiến trúc.

## 21. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế | Cách tránh |
| --- | --- | --- |
| Dùng primary thì chắc chắn đọc dữ liệu không rollback | Primary + local có thể thấy write chưa majority-committed | Chọn read concern/write concern phù hợp |
| Majority write nghĩa mọi secondary đã cập nhật | Chỉ yêu cầu đa số theo topology | Xem replication lag và read preference |
| Majority read trên secondary luôn mới nhất | Secondary có thể stale | Causal session hoặc primary read cho read-your-writes |
| w:1 có nghĩa chắc chắn mất dữ liệu sau failover | Write có thể đạt majority sau ACK | Phân biệt không có bảo đảm với chắc chắn rollback |
| wtimeout nghĩa write chưa chạy | Có thể đã áp dụng nhưng chưa ACK đủ | Xử lý unknown outcome và đối soát |
| j:true thay thế w:"majority" | Journal cục bộ khác replication majority | Xét cả durability và replication |
| Read concern majority đủ tạo snapshot xuyên hai query | Hai query có thể đọc ở các mốc khác nhau | Transaction/snapshot khi cần |
| Linearizable read ngăn oversell | Read và update vẫn có thể race | Guarded atomic update |
| secondaryPreferred luôn đọc secondary | Có thể fallback primary | Biết semantics fallback và quan sát node selection |
| nearest luôn chọn bản sao dữ liệu mới nhất | Nearest dựa trên network latency/selection constraints | Không dùng để hứa freshness |
| maxStalenessSeconds là ngưỡng freshness cứng | Đây là ước lượng cho node selection | Thiết kế SLA riêng và đánh dấu asOf |
| Causal session tự chạy qua hai HTTP request | Session/context không tự truyền sang request mới | Thiết kế workflow hoặc đọc primary |
| Transaction tự đảm bảo mọi side effect | Transaction chỉ bao trùm thao tác MongoDB trong session | Outbox/saga cho hệ thống ngoài |
| Snapshot tự đồng nghĩa linearizable | Snapshot là ảnh chụp tại một mốc | Chọn semantics theo bài toán |
| Dùng majority là đủ bảo vệ số dư không âm | Replication không kiểm tra invariant | Conditional update/transaction |
| Có replica set thì không cần backup | Replication sao chép cả xóa nhầm và lỗi logic | Backup/PITR độc lập |
| Mất quorum thì cứ hạ write concern cho nhanh | Tăng nguy cơ acknowledged write bị rollback | Chính sách fail/retry theo nghiệp vụ |
| Tất cả dữ liệu cần read concern mạnh nhất | Chi phí/khả dụng có thể không cần thiết | Ma trận theo SLA và risk |

## 22. Bài tập thực hành và tình huống thiết kế

### Bài 1 — Phân biệt ba cơ chế

Một API cấu hình **writeConcern majority**, **readConcern local**, **readPreference secondaryPreferred**. Hãy giải thích từng tùy chọn chi phối bước nào. Khi người dùng vừa tạo Order với ACK majority nhưng GET ở secondary chưa thấy, có thể vì sao?

### Bài 2 — Primary read và rollback

Primary P có entry E103 chưa majority-committed; S1/S2 mới tới E102. Client đọc từ primary bằng readConcern local và thấy E103. Nếu P bị cô lập, S1/S2 bầu primary mới, E103 có thể xảy ra chuyện gì? Đọc primary có đủ ngăn rollback không?

### Bài 3 — Majority chưa đồng nghĩa mới nhất

Write Order được ACK majority trên P+S1, S2 chưa bắt kịp. Một GET dùng readConcern majority từ S2 có chắc chắn thấy Order không? So sánh với GET dùng primary và với GET trong causally consistent session.

### Bài 4 — Thiết kế checkout

API tạo Order và xác nhận với người dùng. Chọn write concern, read concern, read preference, requestId/idempotency và hành vi khi majority timeout. Vì sao không nên trả thành công với w:1 khi business policy không chấp nhận rollback?

### Bài 5 — Hồ sơ vừa cập nhật

Người dùng đổi displayName và mở trang hồ sơ ngay. Viết code Node.js dùng **cùng session**, write concern majority, read concern majority và secondaryPreferred. Nếu ứng dụng có hai HTTP request đến hai instance khác nhau, bạn cần thay đổi kiến trúc thế nào?

### Bài 6 — Kiểm soát tồn kho

Hai khách cùng mua SKU còn đúng một sản phẩm. Giải thích vì sao chọn readConcern linearizable **chưa đủ**. Viết updateOne có filter available >= 1 và $inc tương ứng, với writeConcern majority. Nếu yêu cầu rút/giữ hàng được gửi lại, cần thêm gì?

### Bài 7 — Dashboard trễ có chủ đích

Dashboard chấp nhận dữ liệu trễ tối đa theo một SLA do nhóm sản phẩm đặt. Đề xuất đọc secondaryPreferred/majority và cách công bố asOf. Vì sao không tự tuyên bố maxStalenessSeconds = 120 nghĩa số liệu luôn chính xác tới 120 giây gần nhất?

### Bài 8 — Báo cáo nhiều collection

Một báo cáo đọc Orders lúc T1 và Payments lúc T2, cả hai với readConcern majority. Có thể xuất hiện sai khác tạm thời không? Nếu cần cùng ảnh chụp, giải thích cách dùng transaction/snapshot và trade-off.

### Bài 9 — Payment workflow

Một payment cần cập nhật Order, ghi Payment và phát email. Xác định thao tác nào thuộc MongoDB transaction, write concern khi commit, read concern trong transaction, read preference, và cách xử lý email qua outbox.

### Bài 10 — Write concern timeout

Primary đã ghi Order, client dùng w:"majority", wtimeout 5 giây và nhận lỗi. Liệt kê ít nhất ba trạng thái kết quả có thể xảy ra sau đó. Thiết kế endpoint tra cứu trạng thái theo requestId để không tạo Order trùng.

### Bài 11 — Arbiter và quorum

Replica set PSA gồm một primary, một secondary và một arbiter. Secondary bị lỗi. Arbiter có giúp primary thỏa majority write concern bằng cách giữ dữ liệu không? Giải thích sự khác nhau giữa phiếu bầu và bản sao dữ liệu.

### Bài 12 — Causal consistency và monotonic reads

Một người dùng gọi GET A rồi GET B, mỗi lần đọc từ một secondary khác nhau. GET B có thể cũ hơn GET A trong trường hợp không dùng causal session không? Causal consistency có ý nghĩa gì, và điều kiện read/write concern nào giúp bảo đảm nhân quả theo tài liệu?

### Bài 13 — Linearizable read

Một API kiểm tra một document control duy nhất, cần bảo đảm thời gian thực mạnh khi primary thay đổi. Chọn read concern/read preference nào? Vì sao cần maxTimeMS và vì sao vẫn cần guarded write nếu API sau đó sửa document?

### Bài 14 — Read preference fallback

So sánh **primaryPreferred** và **secondaryPreferred** khi một node không sẵn sàng. Với API không chấp nhận dữ liệu stale, tại sao fallback sang secondary có thể vi phạm hợp đồng dù read request vẫn trả 200?

### Bài 15 — Mã chạy trên lab

Chạy seed, sau đó insert **order-majority-004** với w:"majority" và **order-w1-005** với w:1. Đọc lại bằng readConcern majority khi replica set ổn định. Nếu cả hai cùng có mặt, điều đó chứng minh gì và **không** chứng minh gì về bảo đảm chống rollback?

### Bài 16 — Ma trận policy

Tạo ma trận cho ba endpoint: **POST /orders**, **GET /profile sau update**, **GET /analytics/daily**. Chọn các option và giải thích độ trễ, khả năng rollback, stale reads và cách xử lý lỗi.

### Bài 17 — Thất bại network sau $inc

Một lệnh giảm balance bằng $inc được server thực thi nhưng response mất. Nếu API gửi request mới với $inc tương tự, rủi ro gì? Phân biệt retryable write ở driver với idempotency key ở tầng nghiệp vụ.

### Bài 18 — Điều tra sự cố production

Sau một election, một số khách báo “trước đó nhìn thấy Order nhưng giờ không có”. Hãy đưa ra trình tự điều tra không phá hoại: xác nhận filter/tenant, write concern ACK, readConcern/readPreference, log election/rollback, session, replication lag, audit và reconciliation.

### Bài 19 — Chi phí và khả dụng

Khi secondary lag tăng, so sánh tác động tới w:"majority" writes, causal reads từ secondary và dashboard reads. Những nghiệp vụ nào nên fail khi không đủ bảo đảm, nghiệp vụ nào có thể trả dữ liệu stale nếu hiển thị trạng thái rõ ràng?

### Bài 20 — Tự thiết kế chính sách

Một công ty có ba cấp dữ liệu: **Payment** không chịu được rollback thông thường, **Product view count** có thể tổng hợp lại, **Admin feature flag** cần quyết định nhất quán với trạng thái mới. Hãy chọn policy cho mỗi loại và giải thích vì sao không dùng một preset chung cho tất cả.

## 23. Tài liệu tham khảo MongoDB

- MongoDB Manual — [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- MongoDB Manual — [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/).
- MongoDB Manual — [Read Concern "majority"](https://www.mongodb.com/docs/manual/reference/read-concern-majority/).
- MongoDB Manual — [Read Concern "snapshot"](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/).
- MongoDB Manual — [Read Concern "linearizable"](https://www.mongodb.com/docs/manual/reference/read-concern-linearizable/).
- MongoDB Manual — [Causal Consistency](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/).
- MongoDB Manual — [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/).
- MongoDB Manual — [Replica Set Rollbacks](https://www.mongodb.com/docs/manual/core/replica-set-rollbacks/).
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/).
- MongoDB Node.js Driver — [Read Preference](https://www.mongodb.com/docs/drivers/node/current/crud/configure/#read-preference).
- MongoDB Node.js Driver — [Client-Side Sessions](https://www.mongodb.com/docs/drivers/node/current/fundamentals/transactions/).

**Kết luận:** Đừng chọn read concern, write concern và read preference bằng cách xếp chúng trên một thang “yếu → mạnh” duy nhất. **Write concern** quyết định điều kiện xác nhận và mức bảo vệ write, **read concern** quyết định tính chất dữ liệu được đọc, còn **read preference** quyết định node phục vụ. Đối với dữ liệu quan trọng đã xác nhận, hãy xem **w:"majority"**, xử lý timeout và idempotency. Đối với **read-your-writes**, dùng primary hoặc **causally consistent session** với các điều kiện majority phù hợp. Đối với báo cáo chấp nhận độ trễ, có thể đọc secondary nhưng phải thể hiện freshness. Khi invariant trải nhiều document, dùng **transaction/snapshot đúng phạm vi**, còn quyết định cạnh tranh trên một document cần **conditional atomic update**. Chính sách nhất quán tốt là chính sách gắn với **hợp đồng nghiệp vụ, topology và phương án xử lý sự cố có thể kiểm chứng**.
