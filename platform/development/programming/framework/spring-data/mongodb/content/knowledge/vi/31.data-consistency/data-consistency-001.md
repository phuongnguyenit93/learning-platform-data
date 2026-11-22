# Read preference và lựa chọn primary hoặc secondary

> **Chương:** Nhất quán dữ liệu  
> **Module:** `SPRING_DATA_MONGODB`

Khi chạy MongoDB dưới dạng **replica set**, dữ liệu được nhân bản từ một nút **primary** sang các nút **secondary**. Primary nhận các lệnh ghi thông thường; secondary sao chép các thay đổi qua cơ chế replication và có thể phục vụ một số truy vấn đọc. Khi một ứng dụng Spring Data MongoDB sử dụng repository hoặc `MongoTemplate`, câu hỏi “đọc ở primary hay secondary?” ảnh hưởng trực tiếp tới **độ mới của dữ liệu, độ trễ, tải máy chủ và hành vi khi replica set xảy ra failover**.

**Read preference** là chính sách giúp driver chọn thành viên replica set cho các thao tác đọc có hỗ trợ. Nó **không phải** cam kết dữ liệu luôn mới nhất, cũng không thay thế `readConcern`, `writeConcern`, transaction hoặc logic nghiệp vụ. Một báo cáo chạy trên secondary có thể chấp nhận độ trễ replication; nhưng thao tác “vừa đặt hàng xong, mở lại để xác nhận đơn đã được lưu” cần một hợp đồng nhất quán khác.

Bài học thuộc `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác qua `MongoTemplate` hoặc repository, thực hành truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng. Trọng tâm là **cách chọn primary/secondary và quyết định phù hợp cho mỗi đường đọc**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả primary, secondary, replication lag và failover của replica set.
2. Phân biệt năm chế độ `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred` và `nearest`.
3. Chọn read preference cho thao tác nhạy với dữ liệu mới, dashboard/báo cáo, API đọc nhiều và trường hợp mất primary/secondary.
4. Giải thích vì sao `readPreference`, `readConcern` và `writeConcern` xử lý những vấn đề khác nhau; áp dụng causal consistency khi cần.
5. Cấu hình MongoDB connection string, MongoDB Java driver và Spring Data `MongoTemplate` theo nhu cầu; biết khi nào nên dùng hai read clients.
6. Kiểm soát secondary selection bằng tag sets và `maxStalenessSeconds`, không coi `nearest` là lựa chọn “secondary gần người dùng”.
7. Kiểm thử replica set nhiều nút, quan sát replication lag, xử lý timeout/failover và rà soát các bẫy nhất quán dữ liệu.

## 2. Replica set: dữ liệu đi từ primary sang secondary như thế nào?

Ví dụ một replica set có ba thành viên:

```text
                         MongoDB driver
                               |
                     Replica-set discovery
                               |
             +-----------------+-----------------+
             |                 |                 |
             v                 v                 v
        [PRIMARY P]       [SECONDARY S1]    [SECONDARY S2]
        accepts writes     replicates data    replicates data
             |                 ^                 ^
             |     replication |     replication |
             +-----------------+-----------------+

  Data at time T:
    P:  includes write W10
    S1: includes write W9, W10 not yet applied
    S2: includes write W8, W9 and W10 not yet applied
```

Replica set cho khả năng chịu lỗi và phân phối một số truy vấn đọc. Các nút secondary sao chép các thao tác từ replication log (*oplog*) của primary và áp dụng chúng theo tiến độ của mình. Việc nhân bản **không được giả định là đồng bộ tức thời trên mọi secondary**.

### 2.1. Dòng thời gian cho một lần cập nhật đơn hàng

```text
Time  | Primary (P)                     | Secondary (S)
------+---------------------------------+-----------------------------
t0    | order.status = "NEW"            | order.status = "NEW"
t1    | update status = "PAID"          | chưa thấy thay đổi
t2    | acknowledged write              | vẫn có thể thấy "NEW"
t3    |                                 | áp dụng update: "PAID"

READ tại t2:
  readPreference=primary    => đọc "PAID" nếu đọc theo sau write thành công
  readPreference=secondary  => có thể đọc "NEW"
```

Đây là mô hình giải thích hiện tượng **đọc dữ liệu cũ (*stale read*)**. Thời gian thực tế phụ thuộc write concern, trạng thái replica set, tải replication, network và thời điểm đọc. `writeConcern:"majority"` đòi hỏi số thành viên cần thiết xác nhận theo quy tắc majority, nhưng **không đồng nghĩa mọi secondary đều đã áp dụng write**.

### 2.2. Primary không đồng nghĩa “luôn tồn tại”

Khi primary mất kết nối hoặc xảy ra election, hệ thống có thể có một khoảng thời gian **chưa có primary được bầu và được driver nhìn thấy**. Đọc với `primary` có thể chờ server selection rồi timeout. Thay `primary` bằng `secondaryPreferred` không bảo đảm mọi truy vấn luôn thành công: các secondary cũng có thể không sẵn sàng, không đủ điều kiện tag/staleness hoặc chưa có dữ liệu cần thiết.

### 2.3. Replica set không phải phân mảnh dữ liệu

Các secondary thường nhân bản **cùng một tập dữ liệu** từ primary. Chúng không phải các shard chứa những phần dữ liệu riêng. Dùng secondary để phục vụ báo cáo chỉ **phân phối tải đọc giữa replica-set members**; nó không tự thay thế sharding, index hoặc tối ưu query.

## 3. Read preference là gì, và nó không làm gì?

`readPreference` hướng dẫn driver **chọn server nào** xử lý thao tác đọc. Giá trị mặc định của MongoDB driver cho hoạt động đọc thông thường là `primary` nếu không có cấu hình khác.

Nó **không**:

- Làm cho dữ liệu nhân bản tới secondary nhanh hơn.
- Bảo đảm secondary luôn có write mới nhất.
- Bảo đảm một request luôn đọc **cùng một** secondary ở nhiều truy vấn khác nhau.
- Thay thế transaction hoặc optimistic locking để tránh lost update.
- Tự tạo chỉ mục, tối ưu aggregation hoặc đưa write sang secondary.
- Tự thay đổi các điều kiện lọc tenant, phân quyền hay soft delete.

### 3.1. Bảng năm chế độ

| Mode | Nút ưu tiên/được chọn | Khi không có nút phù hợp | Cách hiểu ngắn |
| --- | --- | --- | --- |
| `primary` | **Chỉ primary** | Chờ hoặc lỗi khi không chọn được primary | Ưu tiên đường đọc từ nút nhận ghi |
| `primaryPreferred` | Primary; nếu không có primary thì tìm secondary | Lỗi nếu không có thành viên phù hợp | Bình thường đọc primary, fallback sang secondary |
| `secondary` | **Chỉ secondary** | Chờ hoặc lỗi khi không chọn được secondary | Cố ý dành đọc cho secondary |
| `secondaryPreferred` | Secondary; nếu không có secondary đủ điều kiện thì có thể fallback primary | Lỗi nếu không có thành viên phù hợp | Ưu tiên secondary, nhưng có đường lùi primary |
| `nearest` | Thành viên phù hợp trong **latency window**, có thể là primary hoặc secondary | Lỗi nếu không có thành viên phù hợp | Ưu tiên độ trễ mạng tới server, không ưu tiên vai trò |

**Lưu ý:** “không có server phù hợp” có thể đến từ topology, tag sets, `maxStalenessSeconds`, khả năng kết nối hoặc server selection. Driver áp dụng các quy tắc chọn server, không đơn giản gửi request tuần tự tới những hostname ghi trong URI.

## 4. primary: mặc định và thường phù hợp cho đường đọc giao dịch

`primary` giới hạn các lệnh đọc thông thường vào thành viên primary:

```javascript
// Trong mongosh đã kết nối replica set:
db.getMongo().setReadPref("primary")

db.orders.findOne({ _id: "ORD-101" })
```

**Ưu điểm:**

- Tránh trường hợp chọn một secondary **chưa kịp nhận write mới**.
- Thường là lựa chọn dễ suy luận nhất cho hành vi “ghi xong rồi đọc lại”.
- Phù hợp với nhiều đường đọc phục vụ quyết định cập nhật ngay sau đó, miễn là ứng dụng cũng xử lý version/transaction như yêu cầu.

**Giới hạn cần hiểu:**

- Primary có thể chịu tải đọc lớn khi nhiều API/dashboard cùng truy cập.
- Khi election hoặc không có primary, thao tác có thể chờ rồi lỗi.
- `primary` **không tự bảo đảm linearizability cho mọi cấu hình**. Mức nhất quán còn phụ thuộc `readConcern`, `writeConcern`, session và lịch sử failover.
- Một câu `find` trên primary và một lệnh `update` tiếp theo là **hai thao tác riêng**, không tự trở thành một transaction. Có thể xảy ra race nếu không kiểm tra expected version hoặc không dùng atomic conditional update.

### 4.1. Ví dụ nghiệp vụ nên ưu tiên primary

Người dùng vừa thanh toán đơn `ORD-101`; API chi tiết cần phản ánh trạng thái đã cập nhật trước khi trả trang xác nhận. Đọc secondary không có cơ chế causal consistency có thể trả trạng thái cũ `NEW` và khiến người dùng thanh toán lại. Với đường đọc này, ưu tiên `primary` hoặc thiết kế causal session có ràng buộc phù hợp, và **không cố giảm tải primary bằng cách đánh đổi cam kết nhất quán mà UI đang yêu cầu**.

## 5. primaryPreferred: ưu tiên primary nhưng chấp nhận fallback

`primaryPreferred` có hành vi:

1. Nếu có primary phù hợp và driver nhìn thấy, sử dụng primary cho read.
2. Nếu không có primary, có thể đọc từ secondary theo quy tắc chọn server.
3. Khi primary được bầu lại, driver thường quay về chọn primary ở các lần đọc sau.

```javascript
db.getMongo().setReadPref("primaryPreferred")
db.products.find({ active: true })
```

**Trường hợp phù hợp:** API danh mục sản phẩm, thông tin công khai, dữ liệu mà thời gian không có primary vẫn muốn cố gắng phục vụ read **với chấp nhận dữ liệu có thể cũ**.

**Điểm dễ nhầm:** `primaryPreferred` không tạo ra bảo đảm “luôn đọc fresh”: đúng lúc failover, request có thể đi qua secondary đang lag. Vì vậy nếu sản phẩm **không cho phép** stale read, không dùng preferred mode rồi hy vọng nó tương đương `primary` trong mọi tình huống.

## 6. secondary: chỉ đọc trên secondary

`secondary` chỉ chọn secondary. Nếu không có secondary đủ điều kiện thì **không tự fallback về primary**:

```javascript
db.getMongo().setReadPref("secondary")

db.audit_events.find({
  tenantId: "TENANT-A",
  eventType: "LOGIN"
}).limit(100)
```

**Phù hợp khi:**

- Một tác vụ phân tích có thể chấp nhận replication lag.
- Muốn tránh tải đọc phụ lên primary để bảo vệ đường ghi giao dịch.
- Có secondary được chuẩn bị tài nguyên/index/monitoring cho workload báo cáo.

**Rủi ro:**

- Nếu không có secondary (ví dụ replica set một thành viên), query sẽ không thành công sau server selection timeout.
- Một secondary có thể đi sau primary, khiến báo cáo mới nhất chưa đủ dữ liệu.
- Báo cáo nặng vẫn dùng CPU/RAM/I/O trên secondary, có thể làm **tăng replication lag** và ảnh hưởng khả năng phục hồi.
- Không nên coi `secondary` là nơi thích hợp cho thao tác read-modify-write cần nhìn thấy dữ liệu mới nhất.

## 7. secondaryPreferred: giảm tải nhưng có đường fallback

`secondaryPreferred` ưu tiên một secondary đủ điều kiện và có thể fallback về primary khi không có secondary phù hợp:

```javascript
db.getMongo().setReadPref("secondaryPreferred")

db.orders.aggregate([
  { $match: { tenantId: "TENANT-A", status: "PAID" } },
  { $group: { _id: "$channel", count: { $sum: 1 } } }
])
```

**Trường hợp sử dụng tốt:** màn hình thống kê hoặc báo cáo không yêu cầu cập nhật tới từng write gần nhất, nhưng vẫn muốn tăng khả năng phục vụ khi secondary tạm không sẵn sàng.

**Nhược điểm của fallback:** Trong giai đoạn chỉ còn primary phù hợp, một báo cáo nặng có thể **chạy trên primary**, trái với mục tiêu cách ly tải. Nếu yêu cầu vận hành là “tuyệt đối không để báo cáo nặng chạy trên primary”, chọn `secondary` và chấp nhận trả lỗi/tạm dừng khi không có secondary.

### 7.1. Không có một “secondaryPreferred đúng cho mọi API”

Ví dụ phân loại:

| Đường đọc | Mong đợi độ mới | Lựa chọn ban đầu nên cân nhắc |
| --- | --- | --- |
| Xác nhận payment ngay sau khi ghi | Cao | `primary`; kiểm tra read/write concern |
| Lấy danh sách đơn vừa tạo để điều hướng tiếp | Cao hoặc cần read-your-writes | `primary` hoặc causal session có kiểm chứng |
| Dashboard số đơn 5 phút trước | Có thể trễ | `secondaryPreferred` nếu chấp nhận fallback primary |
| Báo cáo phân tích chi phí cao | Có thể trễ | `secondary` để tránh fallback primary |
| Danh mục sản phẩm ít thay đổi | Có thể trễ ngắn | `primaryPreferred` hoặc `secondaryPreferred` theo SLA |
| Giao dịch đa document trong transaction | Cần các bảo đảm transaction | Dùng cấu hình transaction phù hợp, thường đọc từ primary |

Không chọn chỉ vì loại API là GET/POST. Một GET dùng để kiểm tra số dư hoặc quyền truy cập có thể nghiêm ngặt hơn một báo cáo chạy theo lịch.

## 8. nearest: lựa chọn theo latency, không đồng nghĩa secondary

`nearest` chọn một thành viên **đủ điều kiện** với độ trễ mạng nằm trong khoảng chấp nhận của driver so với nút nhanh nhất. Nút được chọn có thể là primary hoặc secondary:

```javascript
db.getMongo().setReadPref("nearest")
db.catalog.find({ category: "BOOK" }).limit(20)
```

**Hai hiểu nhầm cần tránh:**

1. “nearest” không tự xác định khoảng cách địa lý từ người dùng tới dữ liệu; driver đánh giá **latency mạng từ client tới thành viên replica set**. Một proxy, trung tâm dữ liệu hoặc cấu hình mạng có thể làm lựa chọn khác với suy luận vị trí địa lý.
2. “nearest” không đồng nghĩa “secondary gần nhất”; **primary vẫn có thể được chọn**.

Lựa chọn theo độ trễ có thể giúp một số workload đọc phân tán địa lý, nhưng tính nhất quán vẫn phụ thuộc replica lag và read concern. Nếu nghiệp vụ cần stale-free read sau write, không dùng `nearest` đơn lẻ như một bảo đảm.

## 9. Read preference khác read concern và write concern

Ba tên thường xuất hiện cạnh nhau nhưng giải quyết **ba câu hỏi độc lập**:

| Cơ chế | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Read preference** | **Đọc từ thành viên nào?** | `primary`, `secondaryPreferred` |
| **Read concern** | **Read có yêu cầu mức nhìn thấy/độ bền dữ liệu nào?** | `local`, `majority`, `snapshot`, `linearizable` trong những điều kiện hỗ trợ |
| **Write concern** | **Một write được xác nhận sau những điều kiện nào?** | `w:1`, `w:"majority"`, `j:true`, timeout |

Không nên suy ra:

- `readPreference=primary` ⇒ tự động dùng `readConcern=majority`. **Sai.**
- `readPreference=secondary` + `readConcern=majority` ⇒ luôn nhận write mới nhất trên primary. **Sai.**
- `writeConcern=majority` ⇒ mọi secondary đã bắt kịp write tại thời điểm client nhận ACK. **Sai.**
- `readPreference=nearest` ⇒ độ trễ ứng dụng luôn thấp nhất. **Không đủ cơ sở** nếu chưa xét replication lag, server load, query/index và network.

### 9.1. Read concern local

`local` cho phép đọc dữ liệu mà server đã có ở thời điểm nó phục vụ query, không yêu cầu dữ liệu đó đã được majority xác nhận. Trên primary, một thay đổi chưa majority committed có thể có nguy cơ bị rollback khi failover. Trên secondary, `local` vẫn có thể đọc dữ liệu **đang trễ replication** so với primary.

Vì vậy câu “tôi đọc từ primary” chưa nói hết độ bền của lịch sử write; và câu “tôi đọc từ secondary” cũng chưa nói dữ liệu đã majority committed hay chưa.

### 9.2. Read concern majority

`majority` giới hạn những phiên bản dữ liệu được coi là đã được phần lớn các thành viên có quyền biểu quyết ghi nhận theo quy tắc replica set. Nó cung cấp bảo đảm về **khả năng tồn tại qua failover** mạnh hơn `local` trong các điều kiện được hỗ trợ, nhưng không có nghĩa một secondary ngay lập tức có kết quả mới nhất đã có trên primary.

Ví dụ write `W10` có thể đã được majority xác nhận nhờ primary và một secondary, trong khi secondary khác còn ở `W9`. Một read `majority` trực tiếp đến secondary còn chậm vẫn có thể chưa quan sát `W10` nếu không có yêu cầu causal/snapshot bổ sung phù hợp.

### 9.3. Read concern snapshot và linearizable

`snapshot` được sử dụng trong những bối cảnh/loại thao tác được hỗ trợ để nhìn dữ liệu theo một snapshot nhất quán, thường quan trọng trong transaction. Nhưng snapshot nhất quán **không tự đồng nghĩa với thời điểm mới nhất ngay lúc query**.

`linearizable` là mức nghiêm ngặt hơn cho những phép đọc hỗ trợ trên **primary**, với điều kiện và chi phí liên quan. Nó không phải một lựa chọn có thể gắn tùy ý lên secondary để buộc secondary trở thành primary. Khi cần bảo đảm mạnh như vậy, phải đối chiếu yêu cầu read/write concern, session, topology và timeout với tài liệu của phiên bản server/driver đang vận hành.

### 9.4. Write concern majority và replication lag

`w:"majority"` yêu cầu acknowledgment của một majority theo quy tắc MongoDB; không có nghĩa tất cả secondaries đã bắt kịp. Đây là lý do một phép đọc sau write ở **một secondary tùy ý** không được xem là read-your-writes chỉ vì write trước đó đã nhận majority ACK.

Ví dụ mongosh:

```javascript
// Ví dụ với replica set và collection orders.
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { status: "PAID" } },
  { writeConcern: { w: "majority", wtimeout: 10000 } }
)
```

Lệnh ghi vẫn được gửi tới primary. Nếu kết quả trả về timeout của write concern, **không tự suy ra write chắc chắn chưa xảy ra**. Cần kiểm tra trạng thái hoặc dùng idempotency/CAS phù hợp trước khi retry.

## 10. Read-your-writes và causal consistency

“Read-your-writes” nghĩa là sau khi một client/session ghi một giá trị thành công, lần đọc tiếp theo trong cùng chuỗi nhân quả không nhìn thấy trạng thái **cũ hơn** kết quả đã được ghi.

### 10.1. Vì sao secondary thường không đủ

```text
Client                    Primary                 Secondary
  |                         |                        |
  |--- update ORD-101 ----->|                        |
  |<-- acknowledged --------|                        |
  |                         |--- replication pending |
  |--- find ORD-101 -------------------------------->|
  |<-- status = "NEW" --------------------------------|
```

Nếu người dùng vừa cập nhật trạng thái, việc chuyển read kế tiếp sang secondary **không có điều phối** có thể trả kết quả cũ. Cách đơn giản nhất là đọc từ primary. Nếu muốn sử dụng secondary mà vẫn có ràng buộc về trình tự, cần thiết kế **causally consistent session** và read/write concern đáp ứng điều kiện của MongoDB.

### 10.2. Causal session làm gì?

MongoDB hỗ trợ session nhân quả cho một chuỗi thao tác liên quan. Khi dùng đúng điều kiện — bao gồm read concern `majority`, write concern `majority` cho các bảo đảm nhân quả phù hợp — driver/server có thể dùng thông tin thời gian logic như `operationTime`/`afterClusterTime` để yêu cầu lần đọc sau **không đi lùi trước thao tác đã biết**.

Điều này có thể khiến đọc secondary **chờ replication bắt kịp** trước khi trả kết quả, thay vì đọc ngay một phiên bản cũ. Nhưng:

- Không tự xảy ra chỉ vì bật `readPreference=secondaryPreferred`.
- Session phải được **giữ nhất quán** trong chuỗi thao tác; không thể độc lập tạo session mới trong từng service rồi hy vọng chúng chia sẻ lịch sử nhân quả.
- Độ trễ có thể tăng hoặc request timeout khi secondary không thể bắt kịp đủ nhanh.
- Không có bảo đảm mạnh nếu ứng dụng dùng read/write concern không phù hợp, trộn session tùy tiện hoặc không bảo đảm thứ tự thao tác.
- Causal consistency không thay thế transaction cho bất biến nhiều document.

### 10.3. Ví dụ Java driver: causal session với secondary

Đoạn dưới đây minh họa cấu hình chủ đích; giả định `client` đã kết nối tới replica set có primary/secondary, MongoDB hỗ trợ session và người gọi giữ cùng session:

```java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public void writeThenCausallyRead(MongoClient client) {
    MongoCollection<Document> collection = client
        .getDatabase("shop")
        .getCollection("orders");

    MongoCollection<Document> writer = collection
        .withWriteConcern(WriteConcern.MAJORITY);

    MongoCollection<Document> reader = collection
        .withReadPreference(ReadPreference.secondary())
        .withReadConcern(ReadConcern.MAJORITY);

    ClientSessionOptions options = ClientSessionOptions.builder()
        .causallyConsistent(true)
        .build();

    try (ClientSession session = client.startSession(options)) {
        writer.updateOne(
            session,
            new Document("_id", "ORD-101"),
            new Document("$set",
                new Document("status", "PAID")));

        Document observed = reader.find(
                session, new Document("_id", "ORD-101"))
            .first();

        if (observed == null) {
            throw new IllegalStateException("Không thấy đơn hàng");
        }
        System.out.println(observed.getString("status"));
    }
}
```

Ví dụ chỉ nên chạy với database thử nghiệm và document đã tồn tại. `ClientSession` không được dùng đồng thời bởi nhiều luồng không kiểm soát; các thao tác trong chuỗi nhân quả cần tuần tự theo hợp đồng. Nếu không có secondary hợp lệ, `ReadPreference.secondary()` có thể thất bại; nếu secondary còn chậm, read có thể bị chờ. Cần cấu hình timeout và handling phù hợp cho SLA.

**Quan trọng:** đoạn code minh họa cơ chế causal consistency, **không chứng minh mọi read từ secondary đều mới nhất so với mọi client khác**. Nó chỉ liên quan tới những quan hệ nhân quả được theo dõi trong session theo các điều kiện hỗ trợ.

### 10.4. Read-after-write giữa nhiều HTTP requests

Nếu frontend gửi POST ở request 1 và GET ở request 2, hai request có thể đến các application instances khác nhau, dùng sessions khác nhau. Khi đó không nên giả định một `ClientSession` nằm trong request 1 tự được tái sử dụng cho request 2.

Lựa chọn thiết kế:

- Đọc từ primary cho endpoint xác nhận ngay sau write.
- Trả trực tiếp thông tin đã được xác nhận trong response ghi, nếu hợp đồng cho phép.
- Dùng session/causal tokens xuyên request **chỉ khi đã có thiết kế bảo mật, đời sống token và driver support rõ ràng**.
- Chấp nhận eventual consistency và thông báo UX/trạng thái “đang đồng bộ” với cơ chế polling có giới hạn nếu nghiệp vụ thật sự chịu được.

Không giải quyết vấn đề bằng cách cố định một giá trị `ThreadLocal` ngẫu nhiên rồi tin rằng mọi instance server chia sẻ cùng session.

## 11. Các trạng thái nhất quán cần phân loại trước khi chọn mode

| Yêu cầu nghiệp vụ | Điều thực sự cần | Read preference gợi ý |
| --- | --- | --- |
| Xem đơn vừa ghi thành công | Read-your-writes hoặc dữ liệu vừa xác nhận | `primary` thường là bước đầu đơn giản |
| Xem số dư để quyết định thanh toán | Tránh quyết định trên trạng thái cũ, cần bảo vệ cập nhật cạnh tranh | `primary` + atomic update/transaction/CAS phù hợp |
| Dashboard số đơn theo giờ | Eventual consistency có SLA lag | `secondaryPreferred` hoặc `secondary` theo chính sách tải |
| Xuất báo cáo phân tích lớn | Thường chấp nhận độ trễ có giới hạn | `secondary` + monitoring lag và read concern đã chọn |
| Danh mục ít thay đổi | Có thể chịu stale data | `primaryPreferred` hoặc `nearest` nếu đã đánh giá |
| Kiểm tra quyền truy cập hoặc soft delete | Có rủi ro rò rỉ nếu dùng snapshot cũ | Ưu tiên đường đọc bảo đảm chính sách mới và thiết kế authorization |
| Giao dịch nhiều bước | Transaction/session theo hợp đồng DB | Không tự chọn secondary nếu transaction yêu cầu primary |

**Một cấu hình mặc định duy nhất thường không đủ cho mọi loại truy vấn.** Tách workload có ràng buộc nhất quán và chi phí khác nhau giúp chọn read preference có chủ đích.

## 12. Replica set failover và hành vi fallback

Giả sử P là primary, S1/S2 là secondary:

```text
Trước failover:
  P = PRIMARY
  S1, S2 = SECONDARY

Trong election:
  P mất vai trò hoặc kết nối
  Chưa có PRIMARY được client nhìn thấy
  S1/S2 có thể vẫn đọc được (tùy trạng thái/topology)

Sau election:
  S1 = PRIMARY mới
  S2 = SECONDARY
```

Trong khoảng chưa có primary:

- `primary`: không có server phù hợp; đọc có thể chờ đến timeout hoặc đợi primary mới.
- `primaryPreferred`: có thể đọc từ secondary hiện đủ điều kiện; dữ liệu có thể trễ.
- `secondary`: tiếp tục đọc từ secondary khi có secondary phù hợp.
- `secondaryPreferred`: tiếp tục ưu tiên secondary; khi không còn secondary phù hợp, có thể fallback primary nếu đã có.
- `nearest`: chọn thành viên eligible theo latency, không bảo đảm vai trò và độ mới.

**Không cam kết read preference tự động hoàn thành mọi request khi failover.** Trạng thái topology thay đổi, driver phải nhận biết election, network có thể chập chờn; một số read đã gửi có thể lỗi, retry có điều kiện hoặc bị timeout.

### 12.1. Retryable reads không phải quyền retry vô hạn

MongoDB driver có khả năng retry một số loại read được hỗ trợ khi gặp lỗi nhất thời. Điều này không có nghĩa:

- Bất kỳ command nào cũng retry được.
- Read tự động chuyển thành transaction hoặc dữ liệu nhất quán hơn.
- Mọi aggregate có tác dụng ghi (`$out`/`$merge`) được coi như đọc thuần.
- Nên retry liên tục một request khi secondary đang không còn eligible.

Cần chọn timeout, giới hạn retry, idempotency khi tác vụ có side effect và chính sách degradation phù hợp. Khi server selection không tìm được node, phản hồi lỗi dịch vụ rõ ràng thường tốt hơn chờ vô hạn.

## 13. Cấu hình read preference bằng connection string

Một connection string kết nối tới **replica set**, không phải một hostname thứ cấp duy nhất:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=primary
```

Ví dụ chuyển sang đọc ưu tiên secondary:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=secondaryPreferred
```

`db1/db2/db3` là **hostname minh họa**, không phải server có thể kết nối ngay. Cần dùng DNS/credentials/TLS/replica-set name thực tế của môi trường, và quản lý URI chứa mật khẩu bằng secret manager thay vì commit vào Git.

| Tùy chọn URI | Ý nghĩa |
| --- | --- |
| `replicaSet=rs0` | Xác định replica set mà client dự kiến kết nối |
| `readPreference=primary` | Chỉ đọc từ primary |
| `readPreference=secondary` | Chỉ đọc từ secondary |
| `readPreference=secondaryPreferred` | Ưu tiên secondary, fallback primary theo rule |
| `readPreference=primaryPreferred` | Ưu tiên primary, fallback secondary |
| `readPreference=nearest` | Chọn thành viên hợp lệ dựa trên độ trễ mạng |
| `readPreferenceTags=...` | Ưu tiên/chọn members theo tag sets khi mode cho phép |
| `maxStalenessSeconds=...` | Loại các secondary ước tính quá stale theo chính sách |
| `serverSelectionTimeoutMS=...` | Giới hạn thời gian driver đợi server phù hợp |

### 13.1. Cấu hình ứng dụng Spring Boot

Ở nhiều dự án Spring Boot 3.x, URI mặc định được cấu hình qua:

```properties
spring.data.mongodb.uri=mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=primary
```

Khi framework major version thay đổi, **tên property cấu hình MongoDB có thể khác**; hãy đối chiếu phiên bản Spring Boot mà dự án thực tế sử dụng. Ví dụ ở đây cho thấy **tham số URI của MongoDB driver** mới là phần quyết định read preference.

Nếu thay URI này thành `secondaryPreferred` cho một ứng dụng dùng chung `MongoTemplate`, nhiều repository reads và template reads có thể chịu ảnh hưởng. Đây là lý do không nên thay read preference mặc định của **cả ứng dụng** chỉ để tối ưu một báo cáo.

### 13.2. Đừng dùng directConnection để mô phỏng replica-set routing

Trong một số cấu hình `directConnection=true`, client kết nối trực tiếp tới một member thay vì thực hiện topology discovery/routing thông thường. Điều này khác về ý nghĩa với việc kết nối vào replica set và để driver chọn thành viên theo read preference.

Khi muốn chuyển read từ primary sang secondary trong một replica set, hãy để driver **khám phá topology** đúng cách; không hardcode hostname đang là secondary rồi hy vọng nó luôn giữ vai trò đó sau failover. Với MongoDB Atlas/SRV, dùng URI được nhà cung cấp cấp và thêm option theo tài liệu tương ứng.

## 14. Java driver: cấu hình mức client

MongoDB Java driver cung cấp `com.mongodb.ReadPreference`. Mã dưới đây tạo client có read preference toàn cục cho những lần đọc dùng client ấy.

File `MongoReadClientFactory.java`:

```java
package com.example.shop.config;

import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoReadClientFactory {

    private MongoReadClientFactory() {}

    public static MongoClient primaryClient(String uri) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .readPreference(ReadPreference.primary())
            .build();

        return MongoClients.create(settings);
    }

    public static MongoClient reportingClient(String uri) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .readPreference(ReadPreference.secondaryPreferred())
            .build();

        return MongoClients.create(settings);
    }
}
```

`applyConnectionString` đọc các tùy chọn URI. Lời gọi `readPreference(...)` **sau đó** đặt read preference mà đoạn code chủ đích chọn; nếu URI chứa một giá trị khác, nên định nghĩa quy tắc cấu hình rõ ràng để tránh xung đột khó phát hiện.

Client là đối tượng thường được **tái sử dụng** lâu dài cùng connection pool, không tạo mới cho từng HTTP request. Quản lý vòng đời của `MongoClient`, đóng khi ứng dụng kết thúc và không chia sẻ credentials rộng hơn quyền cần thiết.

### 14.1. Đặt read preference trên một MongoCollection

Khi chỉ một tác vụ báo cáo cần secondary, Java driver có thể đặt read preference ngay trên collection handle:

```java
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> reportingOrders = client
    .getDatabase("shop")
    .getCollection("orders")
    .withReadPreference(ReadPreference.secondary());

Document row = reportingOrders
    .find(new Document("_id", "ORD-101"))
    .first();
```

Đoạn này nằm trong method có `MongoClient client` đã được inject. `MongoCollection.withReadPreference(...)` tạo một collection handle với option tương ứng; không đổi read preference của mọi collection cùng client.

**Lưu ý về Spring Data mapping:** đây là **MongoDB driver API**, trả `org.bson.Document`, không tự ánh xạ vào entity qua converter của `MongoTemplate`. Với logic nghiệp vụ dựa vào `@Field`, custom converter hoặc callbacks, nên dùng một `MongoTemplate` cấu hình phù hợp hoặc tự quản lý mapping output cẩn thận.

### 14.2. Read preference không chuyển write sang secondary

Đặt `ReadPreference.secondary()` không khiến lệnh `insertOne` hoặc `updateOne` được thực thi trực tiếp trên secondary. Trong replica set, write thông thường vẫn được gửi tới primary; thao tác trên secondary không hỗ trợ write sẽ không được chấp nhận như primary.

Điều này rất quan trọng khi đặt tên `reportingClient` hoặc `reportingTemplate`: tên gọi **không phải cơ chế phân quyền đọc-only**. Nếu cần giới hạn chỉ được đọc, dùng user/role MongoDB có quyền chỉ đọc, kiểm soát API, và cấu hình riêng của job báo cáo.

## 15. Spring Data MongoDB: giữ đường ghi chính xác, tách đường báo cáo

Trong một ứng dụng vừa có giao dịch vừa có báo cáo, cách tổ chức dễ hiểu là:

```text
Application Service
    |
    +-- OrderRepository (default primary MongoTemplate)
    |       |
    |       +-- create/update/delete; read-after-write
    |
    +-- ReportingService (reportingMongoTemplate)
            |
            +-- aggregate/read chấp nhận eventual consistency
                    |
                    +-- MongoClient readPreference=secondaryPreferred
```

**Tách template là tách cấu hình đọc**, không tách database logic: hai client vẫn có thể trỏ cùng replica set và collection. Phân quyền MongoDB và quy tắc trạng thái dữ liệu phải được áp dụng nhất quán ở hai đường.

### 15.1. Ví dụ hai MongoTemplate

Ví dụ dưới đây cố ý cấu hình client/template tường minh để kiểm soát route. File `MongoRoutingConfiguration.java`:

```java
package com.example.shop.config;

import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.env.Environment;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;

@Configuration(proxyBeanMethods = false)
public class MongoRoutingConfiguration {

    private static MongoClient client(
            String uri, ReadPreference readPreference) {

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .readPreference(readPreference)
            .build();

        return MongoClients.create(settings);
    }

    @Bean(name = "primaryMongoClient", destroyMethod = "close")
    @Primary
    public MongoClient primaryMongoClient(Environment env) {
        return client(
            env.getRequiredProperty("app.mongo.uri"),
            ReadPreference.primary());
    }

    @Bean(name = "reportingMongoClient", destroyMethod = "close")
    public MongoClient reportingMongoClient(Environment env) {
        return client(
            env.getRequiredProperty("app.mongo.uri"),
            ReadPreference.secondaryPreferred());
    }

    @Bean(name = "mongoTemplate")
    @Primary
    public MongoTemplate mongoTemplate(
            @Qualifier("primaryMongoClient") MongoClient client) {

        return new MongoTemplate(
            new SimpleMongoClientDatabaseFactory(client, "shop"));
    }

    @Bean(name = "reportingMongoTemplate")
    public MongoTemplate reportingMongoTemplate(
            @Qualifier("reportingMongoClient") MongoClient client) {

        return new MongoTemplate(
            new SimpleMongoClientDatabaseFactory(client, "shop"));
    }
}
```

Ví dụ đặt `app.mongo.uri` thành một **property của dự án** (không phải property có sẵn bắt buộc của Spring Boot) và chọn database `shop` cho cả hai template. Với nhiều MongoClients/templates, **cần kiểm tra cấu hình autoconfiguration/repository scanning** của phiên bản Spring Boot thực tế để tránh tạo bean trùng/nhầm. Nếu có `@EnableMongoRepositories` tùy chỉnh, có thể dùng `mongoTemplateRef = "mongoTemplate"` để chỉ rõ repository thường dùng primary template.

Không copy nguyên cấu hình này vào ứng dụng đã có routing MongoDB riêng rồi tạo hai tập beans trùng nhau. Đây là một **mẫu kiến trúc**, phải tích hợp với security, TLS, sessions, metrics và transaction manager hiện hữu.

### 15.2. Reporting service dùng riêng reportingMongoTemplate

File `OrderReportingService.java`:

```java
package com.example.shop.orders;

import java.util.List;
import org.bson.Document;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.stereotype.Service;

@Service
public class OrderReportingService {

    private final MongoTemplate reportingTemplate;

    public OrderReportingService(
            @Qualifier("reportingMongoTemplate")
            MongoTemplate reportingTemplate) {
        this.reportingTemplate = reportingTemplate;
    }

    public List<Document> countPaidOrdersByChannel(
            String permittedTenantId) {

        if (permittedTenantId == null
                || permittedTenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant không hợp lệ");
        }

        Aggregation pipeline = Aggregation.newAggregation(
            Aggregation.match(
                Criteria.where("tenantId").is(permittedTenantId)
                    .and("status").is("PAID")),
            Aggregation.group("channel")
                .count().as("orders"),
            Aggregation.project("orders")
                .and("_id").as("channel")
                .andExclude("_id")
        );

        return reportingTemplate.aggregate(
                pipeline, "orders", Document.class)
            .getMappedResults();
    }
}
```

Báo cáo này nhận số lượng đơn đã `PAID` theo kênh bán trên dữ liệu hiện có ở node được chọn. **Nếu vừa có đơn được thanh toán, tổng có thể chưa tăng ở secondary**. SLA của báo cáo cần nêu rõ chấp nhận độ trễ; không được dùng số này làm nguồn sự thật cho việc quyết định thanh toán hay ghi sổ tức thời.

### 15.3. Repository mặc định và @Aggregation

Nếu `OrderRepository` được tạo dựa trên `mongoTemplate` primary, derived queries và `@Aggregation` trên repository đó thường dùng đường cấu hình primary. Chuyển đọc sang secondary ở một annotation **không phải lúc nào cũng có một annotation chung, khả dụng trên mọi phiên bản Spring Data**. Đừng tự giả định mọi repository method đều có thể khai báo read preference per method giống nhau ở các major versions.

Với một pipeline báo cáo cần routing rõ ràng, một repository fragment hoặc query service dùng `reportingMongoTemplate` được inject tường minh thường dễ hiểu hơn và dễ integration-test hơn. Nếu hệ thống hỗ trợ API override read preference theo operation trong phiên bản đang chạy, vẫn phải xác minh nó có hiệu lực với loại lệnh aggregation cụ thể.

### 15.4. Đường reactive

Nếu ứng dụng sử dụng `ReactiveMongoTemplate`, cách chọn read preference được thực hiện qua reactive MongoDB client/factory tương ứng. Bản chất replica set không đổi:

- Chọn secondary vẫn có khả năng stale read.
- Một `Flux` không tự có read-your-writes.
- Không dùng `MongoTemplate` blocking trong reactive event loop.
- Session/causal consistency cần API reactive session và read/write concern được hỗ trợ thực tế.

Không mặc định chuyển sang reactive có thể giảm replication lag hay làm dữ liệu fresh hơn.

## 16. Tag sets: chọn loại secondary phù hợp với workload

Replica set members có thể được quản trị viên gắn tag metadata, ví dụ:

```javascript
// Hình dung tags được đặt bởi quản trị replica set:
{
  "db1.example.net:27017": { region: "north", workload: "primary" },
  "db2.example.net:27017": { region: "south", workload: "reporting" },
  "db3.example.net:27017": { region: "north", workload: "general" }
}
```

Đây là **sơ đồ tag mang tính minh họa**, không phải câu lệnh cấu hình replica set. Việc gắn tag thật phải do người quản trị triển khai và kiểm tra trên members. Một tag không thay đổi bản chất primary/secondary, không tạo khả năng đọc dữ liệu mới nhất và không thay thế bảo mật.

### 16.1. URI lọc secondary theo tag

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=secondary&readPreferenceTags=workload:reporting
```

Chế độ này yêu cầu một secondary khớp tag `workload:reporting`. Nếu không có secondary đủ điều kiện, driver **không tự chuyển sang primary** vì mode là `secondary`; read có thể thất bại sau server-selection timeout.

### 16.2. Nhiều tag sets theo thứ tự ưu tiên

Một số URI cho phép khai báo nhiều `readPreferenceTags` theo thứ tự:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=secondary&readPreferenceTags=workload:reporting&readPreferenceTags=region:north&readPreferenceTags=
```

Ý định là ưu tiên secondary có tag `workload:reporting`, nếu không có thì cân nhắc tập tag tiếp theo, và cuối cùng cho phép secondary bất kỳ qua tag set rỗng. Phải xác nhận cú pháp URL encoding và kết quả selection theo MongoDB driver version đang dùng.

**Lưu ý:** `readPreferenceTags` không được dùng với mode `primary` thông thường. Với `primaryPreferred`, primary được chọn trước và tags chủ yếu có ý nghĩa cho phương án secondary fallback. Đừng cấu hình tags rồi nghĩ chúng có thể “lọc” primary giống secondary trong mọi mode.

### 16.3. Tags không đảm bảo cùng một server

Tag xác định nhóm thành viên eligible. Nếu nhiều secondary cùng match và có latency tương tự nhau, driver có thể chọn các thành viên khác nhau qua các lần query. Khi một secondary đổi vai trò thành primary sau election, quy tắc chọn thành viên tiếp tục phụ thuộc **mode + topology**, không chỉ tag còn trên host.

Nếu workload có yêu cầu **pin chính xác một server** để điều tra hoặc backup, đó là một bài toán vận hành khác; không nên dùng readPreference tags như một khóa phiên cố định cho các request ứng dụng.

## 17. maxStalenessSeconds: sàng lọc secondary quá chậm

`maxStalenessSeconds` cho phép driver loại các secondary được **ước tính quá chậm** so với tiến độ replica set theo thuật toán lựa chọn server.

Ví dụ:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=secondary&maxStalenessSeconds=120
```

Ý nghĩa: muốn loại những secondary có độ stale **ước tính** vượt quá khoảng hai phút theo cơ chế server selection.

### 17.1. Không phải SLA cứng “dữ liệu <= 120 giây tuổi”

Đây là một ràng buộc **chọn server**, không phải lệnh buộc server đợi tới khi có write cụ thể. MongoDB driver tính staleness từ thông tin topology/replication có độ trễ thu thập. Kết quả có tính xấp xỉ, không bảo đảm:

- Mọi write gần đây nhất đã có trong query.
- Thời điểm snapshot không chậm hơn đúng `120` giây trong mọi điều kiện.
- Query luôn trả kết quả kể cả khi không còn secondary eligible.
- Client có read-your-writes như causal session.

Nếu yêu cầu là “người dùng phải thấy thao tác vừa hoàn tất”, không dùng `maxStalenessSeconds` thay cho primary read hoặc causal consistency.

### 17.2. Giới hạn giá trị

MongoDB driver yêu cầu mức `maxStalenessSeconds` tối thiểu theo quy tắc chọn server; trong cấu hình replica set thông dụng, **mức tối thiểu là 90 giây** và còn phụ thuộc heartbeat interval + khoảng dự phòng. Không đặt `maxStalenessSeconds=3` rồi mong secondary chỉ được trễ tối đa ba giây: driver/server có thể từ chối cấu hình.

Nếu SLA của báo cáo cho phép lệch **5 giây**, max staleness setting không tự đáp ứng SLA đó. Cần dùng mô hình đọc khác, đo lag theo metric và thiết kế cách kiểm tra độ mới của kết quả.

### 17.3. Kết hợp tags và staleness

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=secondary&readPreferenceTags=workload:reporting&maxStalenessSeconds=120
```

Driver chọn secondary khớp tag và đủ điều kiện staleness. Nếu máy reporting đang lag quá ngưỡng, có thể **không còn server phù hợp** và request lỗi. Đây có thể là hành vi **mong muốn** để tránh trả dữ liệu quá cũ, nhưng phải được tính vào SLA và cơ chế fallback của sản phẩm.

### 17.4. secondaryPreferred có thể fallback primary

Với `secondaryPreferred`, khi không còn secondary đủ điều kiện do tags/staleness/topology, driver có thể chọn primary. Nếu mục đích của `maxStalenessSeconds` là **không bao giờ đánh tải báo cáo lên primary**, cần kiểm tra lại: `secondaryPreferred` không cho cam kết cách ly tải. Với yêu cầu cách ly cứng, `secondary` thường rõ ràng hơn.

## 18. Latency window, server selection timeout và giới hạn throughput

Trong read preference `nearest`, driver lựa chọn từ nhóm server phù hợp và nằm trong khoảng độ trễ (*latency window*) so với server đáp ứng nhanh nhất. Mức mặc định thường là **15 ms**, nhưng có thể cấu hình; kiểm tra driver hiện hành để tránh suy đoán.

### 18.1. Network nhanh không đảm bảo query nhanh

Một secondary có ping thấp nhưng CPU cao hoặc index không đủ cho query vẫn có thể phản hồi chậm. Server selection không thay thế:

- Thiết kế compound/multikey indexes.
- Giới hạn page size, batch size và response payload.
- Tối ưu aggregation (`$match` sớm, tránh `$unwind`/`$group` không cần thiết).
- Kiểm tra bộ nhớ, I/O và replication lag trên từng member.

### 18.2. Server selection timeout

Ví dụ URI:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=secondary&serverSelectionTimeoutMS=5000
```

Nếu không chọn được secondary trong khoảng cấu hình, driver có thể báo server-selection timeout. Tăng timeout có thể giúp chịu đựng election ngắn, nhưng **cũng kéo dài thời gian người dùng chờ**. Cần quy định SLA và timeout ở driver, tầng service, load balancer/gateway, đồng thời đảm bảo lỗi được chuyển về API rõ ràng.

### 18.3. Không tạo quá nhiều MongoClients vô ích

Hai client với hai read preference khác nhau tạo các connection pools tương ứng. Với nhiều service instances, điều này làm tăng tổng số connections tới replica set. Chỉ tạo các client/template riêng khi sự khác biệt SLA và routing có giá trị; theo dõi pool size, connection churn và số request tới từng node.

## 19. Read preference với aggregation và các thao tác đặc biệt

Không phải mọi lệnh có hình thức “đọc” đều là một `find` thuần túy:

| Thao tác | Điều cần lưu ý |
| --- | --- |
| `find`, `countDocuments` trên collection | Thường có thể phục vụ theo read preference khi topology cho phép |
| Aggregation chỉ có `$match/$group/$project` | Có thể dùng secondary nếu command/server hỗ trợ |
| Aggregation chứa `$lookup` | Có thể đọc nhiều collection; quan tâm read concern và replication lag ở dữ liệu join |
| Aggregation có `$out` hoặc `$merge` | Có **side effect ghi**; không tự coi là truy vấn read-only hoặc cho rằng read preference được áp như aggregate thường |
| Transaction nhiều document | Cần session/transaction options; **read preference primary** thường là yêu cầu của transaction |
| `findAndModify` / find-and-update | Là thao tác **ghi**, không được chuyển sang secondary chỉ vì nó trả document |
| Change streams | Có cơ chế theo dõi thay đổi và yêu cầu riêng; không dùng readPreference đơn lẻ để tạo bảo đảm đồng bộ tức thì |

Một pipeline `$lookup` trên secondary có thể nhìn thấy trạng thái đã nhân bản ở các collection khác nhau không đồng bộ với ý định nghiệp vụ nếu không dùng cơ chế snapshot/consistency phù hợp. Nếu báo cáo tài chính cần số liệu chính xác tại một thời điểm, hãy xác định snapshot/read concern, không chỉ chọn `secondary` vì nó nhanh hơn.

### 19.1. Transaction: giữ primary và scope rõ

Trong MongoDB, transaction nhiều document sử dụng session và có yêu cầu nhất định về read preference; **primary** là lựa chọn bắt buộc trong những trường hợp transaction được hỗ trợ theo giao thức MongoDB. Đừng khởi tạo transaction trên `reportingMongoTemplate` đã cấu hình `secondaryPreferred` rồi tin rằng mọi lệnh đọc trong transaction tự chạy secondary.

Với Spring Data, `MongoTransactionManager`/reactive transaction manager phải được gắn với đúng database factory và session. Nếu dùng nhiều clients/templates, một transaction không tự lan sang client/factory khác. Điều này quan trọng khi repository thao tác primary nhưng một service đồng thời gọi reporting template dùng secondary.

### 19.2. Đọc từ secondary không làm báo cáo tài chính tự chính xác

Cho dù dữ liệu đã replication xong, báo cáo vẫn có thể sai vì:

- Dùng số tiền Double thay vì Decimal128/số nguyên nhỏ nhất.
- Dùng aggregation thiếu điều kiện status/tenant.
- Dữ liệu bị xóa mềm nhưng report chưa lọc deleted.
- Tính tổng trên nhiều đơn nhưng `$unwind` làm nhân số dòng.
- Đọc từng trang trong các thời điểm khác nhau khi số liệu đang thay đổi.

Read preference chỉ là **một** yếu tố trong bảo đảm chất lượng dữ liệu.

## 20. Kiểm thử tích hợp: phải có replica set nhiều thành viên

Một `@DataMongoTest` kết nối MongoDB standalone có thể kiểm tra repository mapping, nhưng **không thể chứng minh** read preference chọn primary hoặc secondary đúng. Ngay cả một Testcontainers MongoDB được cấu hình làm **replica set một thành viên** vẫn **không có secondary** để kiểm tra.

Với bài này cần môi trường test replica set có:

- Một primary được bầu và ít nhất một secondary đang hoạt động.
- Tài khoản test có quyền đọc/ghi vào database **test riêng**.
- Write concern `majority` được hỗ trợ và thời gian chờ hợp lý.
- Mạng/hostname được driver phát hiện và kết nối đúng (không chỉ thấy một địa chỉ container chưa thể truy cập).
- Không có giả định “secondary luôn đọc stale đúng N giây”: replication có thể nhanh đến mức test đọc ngay đã thấy dữ liệu mới.

### 20.1. Test eventual convergence với Java driver

Ví dụ JUnit 5 (chạy **chỉ khi** `TEST_MONGODB_REPLICA_URI` trỏ tới replica set kiểm thử thật):

```java
package com.example.shop.consistency;

import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import java.time.Duration;
import java.util.UUID;
import org.bson.Document;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ReplicaReadPreferenceIntegrationTest {

    @Test
    void primaryWriteEventuallyAppearsOnSecondary()
            throws InterruptedException {

        String uri = System.getenv("TEST_MONGODB_REPLICA_URI");
        Assumptions.assumeTrue(
            uri != null && !uri.isBlank(),
            "Cần replica set test có primary và secondary");

        try (MongoClient client = MongoClients.create(uri)) {
            // Chỉ dùng database TEST, không chia sẻ với production.
            MongoCollection<Document> base = client
                .getDatabase("read_pref_it")
                .getCollection("orders");

            MongoCollection<Document> primary = base
                .withReadPreference(ReadPreference.primary())
                .withWriteConcern(WriteConcern.MAJORITY);

            MongoCollection<Document> secondary = base
                .withReadPreference(ReadPreference.secondary())
                .withReadConcern(ReadConcern.MAJORITY);

            String id = "RP-" + UUID.randomUUID();

            try {
                primary.insertOne(
                    new Document("_id", id)
                        .append("status", "NEW")
                        .append("tenantId", "TENANT-TEST"));

                primary.updateOne(
                    new Document("_id", id),
                    new Document("$set",
                        new Document("status", "PAID")));

                // Primary đã xác nhận trạng thái mới.
                Document onPrimary = primary.find(
                    new Document("_id", id)).first();

                assertThat(onPrimary).isNotNull();
                assertThat(onPrimary.getString("status"))
                    .isEqualTo("PAID");

                // Không assert secondary PHẢI stale ngay sau write.
                // Chờ có giới hạn cho secondary bắt kịp.
                long deadline = System.nanoTime()
                    + Duration.ofSeconds(30).toNanos();

                Document onSecondary = null;
                while (System.nanoTime() < deadline) {
                    onSecondary = secondary.find(
                        new Document("_id", id)).first();

                    if (onSecondary != null
                            && "PAID".equals(
                                onSecondary.getString("status"))) {
                        break;
                    }
                    Thread.sleep(250);
                }

                assertThat(onSecondary).isNotNull();
                assertThat(onSecondary.getString("status"))
                    .isEqualTo("PAID");
            } finally {
                primary.deleteOne(new Document("_id", id));
            }
        }
    }
}
```

**Các giới hạn của test:**

1. Test kiểm tra eventual convergence **không thể chứng minh secondary sẽ chậm**: server có thể nhân bản gần như tức thì.
2. Nếu secondary không sẵn sàng hoặc driver không kết nối được, `secondary.find(...)` có thể ném server-selection timeout; đây là lỗi test setup hoặc availability cần điều tra.
3. Lời gọi `find` trong mỗi vòng có timeout riêng. Đặt server-selection timeout/maxTime phù hợp với môi trường để tránh mỗi lần read mất lâu hơn toàn bộ budget của test.
4. Write concern majority giúp có bảo đảm acknowledgment tốt hơn nhưng không cho phép kết luận **mọi** secondary đã cập nhật.
5. Cleanup dùng `deleteOne` theo ID ngẫu nhiên trên database test; không dùng `dropDatabase`/`deleteMany({})` khi đang chia sẻ test environment.
6. Nếu chạy CI parallel, ID ngẫu nhiên tránh đụng nhau nhưng không thay thế cách ly credentials/database.

Test này là **mã ví dụ để triển khai và chạy trong môi trường replica set phù hợp**, chưa được thực thi ở bước tạo tài liệu.

### 20.2. Kiểm thử điều kiện không có secondary

Một test tách biệt có thể chạy với replica set chỉ một thành viên:

```java
MongoCollection<Document> onlySecondary = client
    .getDatabase("read_pref_it")
    .getCollection("orders")
    .withReadPreference(ReadPreference.secondary());

// Với replica set không có SECONDARY, lệnh read không có node
// phù hợp và có thể timeout; không kỳ vọng tự fallback PRIMARY.
onlySecondary.find(new Document("_id", "RP-DEMO")).first();
```

Đoạn này minh họa trường hợp **dự kiến thất bại**, không phải test assertion hoàn chỉnh. Trong test thật, hãy đặt `serverSelectionTimeoutMS` ngắn nhưng đủ tin cậy, dùng `assertThatThrownBy`/`assertThrows` cho exception được driver phiên bản đó phát ra và kiểm tra thông tin nguyên nhân.

Đối chiếu với `secondaryPreferred`: nếu replica set có primary nhưng không có secondary eligible, chế độ preferred có thể đọc từ primary. Với một primary vẫn hoạt động, thử nghiệm này giúp làm rõ sự khác biệt giữa **isolation** (`secondary`) và **availability fallback** (`secondaryPreferred`).

### 20.3. Không dùng test cố tình giết primary trên production

Kiểm thử failover/election cần một môi trường riêng và quyền điều phối hạ tầng:

```text
Phase 1: P đang primary; S1/S2 đang secondary.
Phase 2: mô phỏng P mất vai trò trong cluster test.
Phase 3: kiểm tra ứng dụng phát hiện election, timeout/retry đúng.
Phase 4: sau khi có primary mới, lệnh đọc/ghi phục hồi.
Phase 5: xác minh dữ liệu và không có retry tạo side effect ngoài ý muốn.
```

Không cung cấp một lệnh `rs.stepDown(...)` để chạy tùy tiện trong hệ thống dùng chung. Cách gây failover phụ thuộc topology và chính sách vận hành; chỉ thực hiện trên cluster thử nghiệm được cấp quyền.

### 20.4. Test matrix theo read preference

| Tình huống | primary | primaryPreferred | secondary | secondaryPreferred | nearest |
| --- | --- | --- | --- | --- | --- |
| Primary và secondary đều healthy | Primary | Primary | Secondary | Secondary | Nút eligible theo latency |
| Không có secondary eligible, có primary | Primary | Primary | Không chọn được | Fallback primary | Primary nếu eligible |
| Tạm chưa có primary, secondary eligible | Không chọn được | Secondary | Secondary | Secondary | Secondary nếu eligible |
| Secondary lag vượt max staleness | Không ảnh hưởng selection primary | Có thể primary hoặc secondary eligible | Có thể không chọn được | Có thể fallback primary | Chỉ cân nhắc thành viên eligible |
| Secondary bắt kịp write ngay lập tức | Đọc giá trị mới từ primary | Thường primary | Có thể đã thấy mới | Có thể đã thấy mới | Phụ thuộc node |
| Secondary chưa bắt kịp write | Đọc từ primary | Thường primary | Có thể stale | Có thể stale | Có thể stale nếu chọn secondary |

Ma trận là **mô hình theo trạng thái topology**, không cam kết request sẽ thành công trong mọi thời điểm. Còn có auth/network/server selection/read concern/timeout và các thao tác không hỗ trợ secondary read.

## 21. Quan sát replication lag và việc chọn server

Muốn khai thác secondary an toàn, cần giám sát khả năng bắt kịp primary. **Đừng chỉ theo dõi CPU primary giảm sau khi bật secondaryPreferred**.

### 21.1. Kiểm tra trạng thái replica set

Trong `mongosh` có quyền quản trị phù hợp:

```javascript
rs.status()
```

Khi được phép, có thể xem một số field chẩn đoán:

```javascript
const status = rs.status();

status.members.map(m => ({
  name: m.name,
  state: m.stateStr,
  optimeDate: m.optimeDate,
  syncSourceHost: m.syncSourceHost
}));
```

Các field hiện diện và cách hiển thị có thể khác tùy phiên bản/topology; đây là quan sát phục vụ quản trị, không phải API business. Dùng monitoring của cluster/cloud provider để có metric replication lag ổn định và biểu đồ lịch sử.

### 21.2. Phải đọc thêm log client/server selection

Các dấu hiệu:

- Driver báo không tìm thấy secondary phù hợp.
- Tags mới cấu hình nhưng không có member match.
- `maxStalenessSeconds` loại toàn bộ secondaries.
- Một địa chỉ trong replica set chỉ truy cập được từ một mạng khác.
- Election xảy ra thường xuyên hoặc client kết nối tới nhầm replica-set name.
- Báo cáo vẫn chạy trên primary vì `secondaryPreferred` fallback.

Thông tin `hello`/`isWritablePrimary` của một kết nối riêng giúp điều tra vai trò server, nhưng **không nên coi một lệnh hello gửi thủ công là bằng chứng mọi query của ứng dụng đều chạy tại server đó**. Muốn kiểm tra routing ở thực tế, dùng command monitoring/driver logs, server-side metrics và topology monitoring theo phiên bản driver.

### 21.3. Nhóm metrics nên theo dõi

| Metric | Phát hiện |
| --- | --- |
| Replication lag từng secondary | Báo cáo có nguy cơ stale, áp dụng chậm |
| Read ops/QPS theo member | Tải báo cáo có thật sự rời primary không |
| CPU, RAM, disk I/O trên secondary | Báo cáo có chiếm tài nguyên replication không |
| Server selection failures/timeouts | Không có member đủ điều kiện hoặc network lỗi |
| Query latency p50/p95/p99 theo operation | Tác động tới SLA người dùng |
| Secondary rollback/election events | Sự thay đổi topology, độ tin cậy |
| Number of connections/pools per client | Chi phí do dùng nhiều MongoClients |
| Keys/docs examined cho report query | Index phù hợp, query có đang quét rộng không |

Nếu báo cáo yêu cầu dữ liệu không quá trễ 60 giây, chỉ cấu hình `maxStalenessSeconds=120` là **không đáp ứng trực tiếp** yêu cầu ấy. Cần một cơ chế đo độ mới của dữ liệu trả về, hoặc đọc primary/causal consistency theo yêu cầu.

### 21.4. Dấu thời gian tài liệu không tự đo replication lag

Field `updatedAt` trên document do ứng dụng ghi có thể đến từ clock của app, không nhất thiết bằng thời gian server commit; các clock khác nhau có thể lệch. Khi xác định replication lag, ưu tiên metric replication/optime của MongoDB và hệ thống monitoring, không tự lấy `now() - updatedAt` của một document bất kỳ làm bằng chứng lag.

## 22. Kịch bản chẩn đoán sản xuất

### 22.1. “Đặt hàng xong nhưng trang danh sách không có đơn”

**Nguyên nhân khả dĩ:** write thành công trên primary, sau đó API danh sách được route tới secondary chưa replicate.

**Kiểm tra:** đọc cùng `_id` từ primary; đọc từ secondary; xác định read preference hiện tại, lag và write concern. Trước khi kết luận là stale read, cũng phải kiểm tra filter tenant, soft-delete, status và pagination.

**Khắc phục:** route endpoint xác nhận vừa tạo qua primary; hoặc thiết kế causal read với majority/session phù hợp nếu cần secondary. Không mặc định retry 100 lần đến khi “trông có vẻ đúng”.

### 22.2. “SecondaryPreferred vẫn khiến primary quá tải”

**Nguyên nhân khả dĩ:** không có secondary eligible do outage, tag mismatch, staleness, network hoặc quá ít thành viên. Driver fallback primary theo chính sách.

**Kiểm tra:** topology, tag sets, max staleness, command/server metrics. Cần biết read nào là báo cáo nặng.

**Khắc phục:** nếu yêu cầu cách ly cứng, dùng `secondary` với giới hạn timeout/error rõ; tăng capacity secondary khi cần; tối ưu pipeline và index. Không giải quyết bằng cách tăng timeout vô hạn.

### 22.3. “Secondary read bị timeout dù rs.status() thấy SECONDARY”

**Nguyên nhân khả dĩ:** địa chỉ server không truy cập được từ app, server chưa đủ điều kiện, tag mismatch, staleness, driver chưa cập nhật topology hoặc server quá tải.

**Kiểm tra:** connection URI, replica-set member hostnames, TLS/auth, `serverSelectionTimeoutMS`, tags, maxStaleness và metrics. Một thành viên hiển thị SECONDARY ở một môi trường quản trị không chứng minh ứng dụng có thể kết nối tới nó.

### 22.4. “Read concern majority rồi mà vẫn đọc trạng thái cũ”

**Nguyên nhân:** majority nói về trạng thái majority-committed được đọc, không tự bảo đảm node secondary đã theo kịp **write cụ thể từ client hiện tại**.

**Khắc phục:** phân biệt yêu cầu majority durability với read-your-writes; dùng cùng causal session và majority read/write concern khi thiết kế hỗ trợ, hoặc đọc primary. Kiểm tra timeout khi secondary cần chờ nhân quả.

### 22.5. “Báo cáo thỉnh thoảng nhảy số”

**Nguyên nhân có thể:** các request liên tiếp dùng các secondary có lag khác nhau; dữ liệu đang thay đổi; báo cáo phân trang không snapshot; query khác nhau về filter.

**Khắc phục:** định nghĩa thời điểm nhất quán/snapshot nếu cần, cache/materialized report, gắn as-of timestamp có ý nghĩa nghiệp vụ và xác nhận phân trang/sort ổn định. Không cho rằng set read preference duy nhất sẽ giải quyết mọi độ lệch.

## 23. Những hiểu nhầm cần tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| `primary` nghĩa là mọi đọc đều linearizable | Read preference chỉ chọn server; cần read/write concern và điều kiện hỗ trợ phù hợp |
| `secondary` luôn nhanh hơn primary | Secondary có thể lag, quá tải hoặc thiếu index; phải đo |
| `secondaryPreferred` không bao giờ làm tăng tải primary | Khi không có secondary đủ điều kiện, có thể fallback primary |
| `primaryPreferred` luôn trả kết quả mới | Khi primary vắng mặt, fallback secondary có thể trả stale data |
| `nearest` luôn chọn secondary gần nhất | Có thể chọn primary và dựa vào độ trễ **từ client**, không phải vị trí người dùng |
| `writeConcern: majority` khiến mọi secondary đã có write | Chỉ yêu cầu mức majority theo quy tắc acknowledgment |
| `readConcern: majority` khiến secondary có write mới nhất | Majority-committed không tự có read-your-writes từ secondary bất kỳ |
| `maxStalenessSeconds=120` bảo đảm dữ liệu mới trong đúng 120 giây | Chỉ là giới hạn ước tính cho server selection, không phải SLA freshness cứng |
| `maxStalenessSeconds=5` là cách buộc stale tối đa 5 giây | Vi phạm mức tối thiểu thông dụng; phải thiết kế consistency khác |
| URI chứa ba host nghĩa là driver chia đều read cho ba host | Mode, topology, latency, tags và staleness quyết định lựa chọn |
| Chỉ định hostname secondary cố định sẽ luôn đọc secondary | Member có thể đổi vai trò sau election |
| Đặt read preference trên reporting template làm template read-only | Write vẫn đi primary; read-only là yêu cầu RBAC/kiến trúc khác |
| Tạo nhiều MongoClients không tốn tài nguyên | Mỗi client có pool và chi phí giám sát/kết nối |
| `@Aggregation` luôn chạy primary | Phụ thuộc template/client và loại aggregate; cần xác minh cấu hình |
| `findAndModify` là read vì trả document | Nó là thao tác thay đổi dữ liệu, cần write semantics |
| Streaming/reactive sẽ loại replication lag | Đổi cách nhận kết quả không đổi tốc độ replica apply |
| Có session bất kỳ sẽ bảo đảm causal consistency | Phải duy trì đúng session/trình tự và read/write concern hỗ trợ |
| Query stale có thể khắc phục bằng unique index | Index hỗ trợ hiệu năng/duy nhất, không giải quyết replication lag |
| Read preference bảo vệ quyền tenant | Tenant scoping và authorization độc lập hoàn toàn |

## 24. Checklist thiết kế read preference cho ứng dụng

Trước khi triển khai một route đọc trên secondary, hãy trả lời:

1. **Đường đọc phục vụ quyết định gì?** Xác nhận giao dịch, hiển thị thông tin, báo cáo hay hành động có tác dụng ghi?
2. **Độ mới mong muốn là gì?** Dữ liệu vừa ghi phải thấy ngay, hay trễ 30 giây/5 phút là chấp nhận?
3. **Độ mới có phải yêu cầu bảo mật?** Quyền vừa bị thu hồi, soft delete hoặc trạng thái khóa tài khoản có thể gây rò rỉ nếu đọc cũ?
4. **Có read-after-write giữa các requests không?** Cùng session hay các application instances khác nhau?
5. **Write/read concern nào được dùng?** Majority có đáp ứng độ bền, session có đáp ứng causal consistency không?
6. **Mode fallback phù hợp SLA không?** `secondaryPreferred` có thể tăng tải primary; `secondary` có thể gây unavailable.
7. **Topology có đủ members?** Replica set thực hay standalone/single-member test?
8. **Tags và staleness đang loại thành viên nào?** Kiểm tra đủ secondary eligible trong điều kiện thực tế.
9. **Server-selection timeout, query timeout và retry có giới hạn không?**
10. **Đang dùng một client hay nhiều clients?** Có bean naming, transaction/session wiring và lifecycle rõ?
11. **Có index và explain cho read workload không?** Không tạo tải báo cáo lớn làm secondary trễ replication.
12. **Đã thử failover trên cluster test chưa?** Quan sát routing, lỗi, availability và dữ liệu khi election.
13. **Có giám sát replication lag và read ops từng member?** Không chỉ xem latency tổng của API.
14. **Có cơ chế degraded mode khi không còn secondary?** Trả lỗi rõ, cache có tuổi dữ liệu hoặc fallback được chấp thuận.
15. **Có integration test read-only/casual session không?** Tránh test giả định độ trễ nhân bản luôn cố định.
16. **Đã kiểm tra cloud/driver/server version chưa?** Một số operation có hạn chế routing riêng.

## 25. Quy trình chọn mode theo SLA

```text
Read yêu cầu thấy kết quả write vừa được xác nhận?
    |
    +-- Có --> primary là lựa chọn đơn giản ban đầu
    |          hoặc causal session đã thiết kế/kiểm chứng.
    |
    +-- Không --> Có thể chấp nhận stale data?
                 |
                 +-- Không --> xác định read concern/
                 |          snapshot và nhất quán cần thiết.
                 |
                 +-- Có --> Muốn tuyệt đối không chạy trên primary?
                            |
                            +-- Có --> secondary; quản lý unavailable,
                            |          tags, lag, timeout và capacity.
                            |
                            +-- Không --> secondaryPreferred hoặc
                                       primaryPreferred/nearest
                                       theo mục tiêu availability,
                                       latency và độ mới dữ liệu.
```

Đây là **quy trình ra quyết định**, không phải thay thế việc đo dữ liệu thực. Một hệ thống có quy định tài chính/pháp lý đặc biệt cần thiết kế readConcern/transaction và khả năng ghi nhận snapshot riêng trước khi chọn mode.

### 25.1. Một cấu hình ứng dụng không nhất thiết là một SLA

Ví dụ ứng dụng bán hàng:

- **OrderCommandService:** ghi và đọc xác nhận đơn bằng primary, version/CAS hoặc transaction theo yêu cầu.
- **OrderQueryService:** đọc đơn thường xuyên bằng primary khi người dùng có kỳ vọng thấy thay đổi mới.
- **CatalogReadService:** có thể dùng secondaryPreferred nếu cập nhật sản phẩm không đòi hỏi real-time.
- **RevenueReportingService:** đọc secondary chuyên dụng với tag workload và staleness policy, nhưng có cơ chế lỗi/giới hạn tải rõ.
- **SecurityCheckService:** kiểm tra quyền và chính sách truy cập theo nguồn dữ liệu nhất quán đã thiết kế; không tự dùng secondary stale chỉ vì query là `find`.

Cách tổ chức này tách **phân loại nhất quán theo use case**, thay vì áp đặt `secondaryPreferred` cho toàn bộ ứng dụng rồi xử lý các lỗi phát sinh sau.

## 26. Bài tập thực hành

Một hệ thống quản lý kho có replica set ba members. Đường ghi `InventoryCommandService` cập nhật số lượng tồn tại primary, còn dashboard `InventoryDashboardService` gọi aggregation mỗi phút. Hai loại người dùng:

- **Thủ kho:** sau khi trừ 5 sản phẩm, phải thấy số lượng mới để quyết định có được xuất kho tiếp không.
- **Quản lý:** chỉ cần thống kê top SKU tồn kho thấp, chấp nhận dữ liệu trễ 2–3 phút, nhưng không muốn báo cáo nặng cạnh tranh I/O với primary.

### Bài tập 1: chọn read preference

Đề xuất mode phù hợp cho:

1. Read sau lệnh trừ tồn kho.
2. Dashboard chạy lịch có thể stale.
3. API danh mục hàng hóa nếu primary election.
4. Truy vấn chỉ được phục vụ khi secondary báo cáo sẵn sàng và không được fallback primary.
5. Truy vấn gần nhất theo network latency trong cụm đa vùng.

Giải thích các hạn chế riêng về freshness/fallback của mỗi đề xuất.

### Bài tập 2: viết URI

Tạo connection strings cho:

```text
Replica set: rs0
Members: inv1.example.net:27017, inv2.example.net:27017, inv3.example.net:27017
Database: warehouse
```

Yêu cầu:

1. Client command dùng `primary`.
2. Client reporting dùng `secondary`.
3. Client reporting chỉ chọn secondary có tag `workload:analytics`.
4. Dùng `maxStalenessSeconds=120` để lọc secondary quá chậm theo ước tính.
5. Thêm `serverSelectionTimeoutMS=5000` và mô tả tác động khi không có secondary.

**Gợi ý cấu hình:**

```text
mongodb://inv1.example.net:27017,inv2.example.net:27017,inv3.example.net:27017/warehouse?replicaSet=rs0&readPreference=secondary&readPreferenceTags=workload:analytics&maxStalenessSeconds=120&serverSelectionTimeoutMS=5000
```

Các hostname trên chỉ là ví dụ. Cần xác minh tags đã được quản trị viên cấu hình, replica set có secondary đủ điều kiện, URI có xác thực/TLS theo môi trường và credential không được commit vào repository.

### Bài tập 3: Java driver và Spring Data

1. Dùng `MongoClientSettings` xây hai clients, một primary, một secondaryPreferred.
2. Tạo hai `MongoTemplate` với `SimpleMongoClientDatabaseFactory`.
3. Dùng `@Qualifier` để báo cáo chỉ gọi reporting template.
4. Chứng minh repository mặc định vẫn thuộc primary template.
5. Chỉ ra vì sao reporting template **không được tự gọi là read-only** khi chưa giới hạn quyền ghi.
6. Khi có transaction, xác định MongoTransactionManager sử dụng factory nào và vì sao không trộn template tùy tiện.

### Bài tập 4: thử nghiệm read-after-write

Seed document:

```javascript
{
  _id: "STOCK-101",
  tenantId: "TENANT-A",
  sku: "SKU-X",
  available: NumberLong(20),
  version: NumberLong(1)
}
```

Trên môi trường test replica set:

1. Cập nhật tồn từ 20 xuống 15 trên primary bằng `$inc` hoặc conditional update.
2. Dùng `writeConcern:majority` và đọc từ primary.
3. Đọc bằng `secondary`, nhưng **không assert bắt buộc thấy giá trị cũ**.
4. Chờ secondary bắt kịp với timeout rõ, xác nhận giá trị cuối bằng 15.
5. Dùng cùng causal session để kiểm tra read-your-writes qua secondary theo điều kiện hỗ trợ.
6. Mô phỏng thiếu secondary bằng test setup riêng; so sánh lỗi của `secondary` và fallback của `secondaryPreferred`.
7. Đo read latency và replication lag; không tự lấy chênh lệch `updatedAt` của một document làm toàn bộ metric.

### Bài tập 5: sự cố thực tế

Trong giờ cao điểm, dashboard đột nhiên khiến primary tăng CPU dù đã cấu hình `secondaryPreferred`. Cùng lúc đó, người dùng có lúc thấy trạng thái đơn cũ.

Hãy đề xuất cách kiểm tra:

- Có secondary nào eligible không? Tags, staleness, network, election?
- Dashboard đang fallback primary hay vẫn có secondary phục vụ nhưng quá tải?
- Những endpoint cần read-your-writes có bị cấu hình secondaryPreferred trên client dùng chung không?
- Có thể tách primary/reporting templates và RBAC khác nhau không?
- Có index và giải pháp giới hạn aggregation trước khi thay read preference không?
- Nếu secondary không đủ điều kiện, sản phẩm chấp nhận lỗi tạm thời hay buộc fallback primary?

### Gợi ý đáp án tổng quát

**Thủ kho:** đọc primary và bảo vệ phép cập nhật tồn kho bằng atomic conditional update/version; không dựa trên dữ liệu stale để quyết định số lượng còn đủ. **Quản lý:** báo cáo trên secondary riêng nếu chấp nhận eventual consistency; dùng mode `secondary` nếu yêu cầu tuyệt đối tránh primary, và có phương án báo lỗi/cache với tuổi dữ liệu rõ. Causal session phù hợp khi cần kết quả của chính một chuỗi ghi–đọc trên secondary nhưng phải bảo đảm majority/session/timeout và không tạo ảo tưởng rằng mọi client cùng nhìn dữ liệu mới nhất.

## 27. Tài liệu tham khảo

- MongoDB Manual — [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/): nguyên tắc route read và các chế độ lựa chọn server.
- MongoDB Manual — [Read Preference Modes](https://www.mongodb.com/docs/manual/core/read-preference/#read-preference-modes): `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred` và `nearest`.
- MongoDB Manual — [Maximum Staleness for Read Preference](https://www.mongodb.com/docs/manual/core/read-preference-staleness/): thuật toán/staleness và mức giá trị hỗ trợ.
- MongoDB Manual — [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/): `local`, `majority`, `snapshot`, `linearizable` và phạm vi bảo đảm.
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): acknowledgment của write và majority.
- MongoDB Manual — [Causal Consistency and Read and Write Concerns](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/): yêu cầu session và các bảo đảm nhân quả.
- MongoDB Manual — [Replication](https://www.mongodb.com/docs/manual/replication/): members, oplog và replication lag.
- MongoDB Java Driver — [Read Preference](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/read-preference/): cấu hình qua driver Java và connection options.
- Spring Data MongoDB — [Reference Documentation](https://docs.spring.io/spring-data/mongodb/reference/): MongoTemplate, repository, mapping và session/transaction.
- Spring Data MongoDB — [Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): ClientSession, transaction manager và phạm vi session.

## Ghi nhớ

**Read preference trả lời “đọc ở nút nào”, không trả lời “dữ liệu có mới và nhất quán đến đâu”.** `primary` thường dễ suy luận cho read-after-write; `secondary` cách ly tải nhưng có thể stale và không fallback; `secondaryPreferred` ưu tiên secondary nhưng có thể đẩy báo cáo về primary khi cần; `primaryPreferred` ưu tiên primary và chỉ fallback khi không có; `nearest` chọn theo network latency và có thể chọn cả primary. Muốn bảo đảm cao hơn phải xét `readConcern`, `writeConcern`, session, transaction, latency/replication lag và điều kiện nghiệp vụ. Với Spring Data MongoDB, tách đường đọc báo cáo khỏi đường giao dịch khi có lý do rõ ràng, kiểm thử trên replica set thật, theo dõi server selection và lag, và không đánh đổi tính chính xác chỉ để giảm tải primary.
