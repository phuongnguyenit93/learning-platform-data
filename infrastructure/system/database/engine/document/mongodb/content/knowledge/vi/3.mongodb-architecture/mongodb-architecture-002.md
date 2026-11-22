# Đường đi của một yêu cầu đọc hoặc ghi trong MongoDB

## 1. Từ một lệnh của ứng dụng đến dữ liệu thực tế

Khi ứng dụng gọi `find()`, `insertOne()` hoặc `updateOne()`, MongoDB không chỉ thực hiện một thao tác đơn giản trên một tệp dữ liệu. Yêu cầu đi qua nhiều lớp: **driver phía ứng dụng → kết nối mạng → chọn máy chủ → xử lý lệnh → bộ máy truy vấn/lưu trữ → cơ chế nhân bản → phản hồi**. Với cụm phân mảnh (sharded cluster), còn có tầng định tuyến `mongos`.

Hiểu đường đi này giúp giải thích những tình huống thực tế:

- Vì sao hai truy vấn có cùng điều kiện nhưng độ trễ khác nhau?
- Vì sao một yêu cầu ghi đã được xác nhận ở máy chủ chính nhưng chưa thấy trên máy chủ phụ?
- Vì sao tạo index có thể giảm số tài liệu phải đọc mà không loại bỏ hoàn toàn thời gian chờ?
- Vì sao lỗi mạng xảy ra sau khi gửi lệnh ghi **không chứng minh** rằng ghi thất bại?
- Vì sao `writeConcern`, `readConcern` và `readPreference` là ba lựa chọn khác nhau?

Hãy theo dõi collection `orders` trong database `shop`:

```javascript
// Ví dụ tài liệu được lưu dưới dạng BSON.
{
  _id: "ORD-001",
  customerId: "C01",
  status: "PAID",
  total: NumberDecimal("240000"),
  createdAt: ISODate("2026-10-20T09:00:00Z")
}
```

Ứng dụng có thể yêu cầu lấy 10 đơn mới nhất của khách hàng hoặc thêm một đơn mới. Dù cú pháp sử dụng rất ngắn, quá trình xử lý phía sau phụ thuộc vào **kiểu triển khai MongoDB**, **kế hoạch truy vấn**, **cấu hình consistency/durability** và **trạng thái cụm tại thời điểm thực thi**.

## 2. Những thành phần tham gia

| Thành phần | Vai trò trong đường đi |
|---|---|
| **Ứng dụng + MongoDB driver** | Tạo lệnh, mã hóa/giải mã BSON, quản lý phiên, kết nối và lựa chọn máy chủ |
| **Connection pool** | Tái sử dụng kết nối TCP/TLS; tránh mở một kết nối mới cho mỗi thao tác |
| **`mongod`** | Tiến trình máy chủ thực thi lệnh, kiểm tra quyền, lập kế hoạch truy vấn và quản lý dữ liệu |
| **Primary trong replica set** | Máy chủ chính thường nhận các thao tác ghi và tạo chuỗi thay đổi để nhân bản |
| **Secondary trong replica set** | Nhận và áp dụng các mục thay đổi từ primary; có thể phục vụ đọc theo cấu hình |
| **`mongos`** | Bộ định tuyến tiếp nhận lệnh từ ứng dụng trong sharded cluster và gửi đến shard thích hợp |
| **Config server** | Lưu metadata của cụm phân mảnh: collection nào được shard, phân bố các khoảng dữ liệu... |
| **WiredTiger** | Storage engine thông dụng của MongoDB, phụ trách cache, cấu trúc lưu trữ, đồng thời hỗ trợ cơ chế bền vững dữ liệu |
| **Index** | Cấu trúc phục vụ tìm kiếm/sắp xếp một số kiểu truy vấn, bổ sung cho dữ liệu tài liệu |
| **Oplog** | Nhật ký thao tác theo thứ tự trong replica set để secondary tái hiện các thay đổi |

**Phân biệt hai topology thường gặp:**

- **Replica set không phân mảnh:** ứng dụng kết nối tới các `mongod` thành viên; driver chọn một thành viên đủ điều kiện để thực hiện lệnh.
- **Sharded cluster:** ứng dụng kết nối qua một hoặc nhiều `mongos`; mỗi shard thường là một replica set và dữ liệu được chia giữa nhiều shard.

Máy chủ đứng sau driver có thể là một `mongod` hoặc một `mongos`. Đây là điểm rẽ quan trọng nhất khi lần theo đường đi của yêu cầu.

### 2.1. Sơ đồ cụm replica set

```text
  Ứng dụng
      |
  MongoDB driver ── Connection pool, khám phá topology
      |
      | Lệnh ghi (mặc định)
      v
  mongod PRIMARY  ────── đọc/ghi WiredTiger
      |                         |
      |                         +-- Cache, dữ liệu, index
      |                         +-- Journal / checkpoint
      |
      +---- oplog / replication ----> mongod SECONDARY 1
      |
      +---- oplog / replication ----> mongod SECONDARY 2

  Lệnh đọc:
    readPreference=primary   -> primary
    readPreference=secondary -> secondary đủ điều kiện
```

Sơ đồ cho thấy **đường logic**, không khẳng định các bước mạng, ghi journal, checkpoint hay nhân bản luôn diễn ra theo một thứ tự tuyến tính cứng. MongoDB xử lý nhiều việc song song và tối ưu theo phiên bản, topology và tải hệ thống.

## 3. Trước khi đọc hoặc ghi: driver chọn nơi gửi lệnh

### 3.1. Mở kết nối và khám phá topology

Ví dụ URI replica set:

```text
mongodb://mongo-a.example:27017,mongo-b.example:27017,mongo-c.example:27017/shop?replicaSet=rs0
```

Đây là URI minh họa. Driver không hiểu danh sách máy chủ chỉ như một chuỗi địa chỉ để thử ngẫu nhiên. Nó sử dụng cơ chế **Server Discovery and Monitoring (SDAM)** để nhận diện topology, vai trò primary/secondary, tình trạng máy chủ và khả năng đáp ứng lựa chọn đọc/ghi. Trong quá trình đó, driver trao đổi thông tin như lệnh `hello`, theo dõi thay đổi topology và duy trì tập kết nối trong pool.

Khi cần thực hiện một lệnh, driver thường:

1. Xác định yêu cầu đang đọc hay ghi và các tùy chọn đi kèm.
2. Chọn máy chủ thỏa `readPreference`, loại thao tác và tình trạng topology; với sharded cluster, chọn `mongos` thích hợp.
3. Lấy kết nối sẵn có trong pool hoặc thiết lập kết nối khi cần; thực hiện xác thực và bảo vệ TLS nếu được cấu hình.
4. Mã hóa command cùng dữ liệu đầu vào dưới dạng BSON và gửi qua giao thức mạng MongoDB.
5. Đọc phản hồi BSON, chuyển về đối tượng/ngoại lệ tương ứng ở ngôn ngữ lập trình.

**Không phải mỗi lệnh đều cần bắt tay mạng, đăng nhập hoặc dò lại toàn bộ topology.** Driver liên tục cập nhật trạng thái và tái sử dụng kết nối. Thời gian đợi một kết nối rảnh hoặc thời gian chờ chọn máy chủ vẫn có thể tạo độ trễ trước khi máy chủ bắt đầu truy vấn.

### 3.2. Ba nhóm tùy chọn rất dễ bị nhầm

| Tùy chọn | Áp dụng chủ yếu cho | Câu hỏi nó trả lời |
|---|---|---|
| `readPreference` | Đọc | **Đọc từ đâu?** Primary, secondary hay cấu hình ưu tiên khác? |
| `readConcern` | Đọc | **Dữ liệu ở mức nhất quán nào được phép nhìn thấy?** |
| `writeConcern` | Ghi | **Cần những xác nhận nào trước khi báo ghi thành công?** |

Ba tùy chọn phối hợp nhưng không thay thế nhau. Ví dụ đọc từ secondary với `readConcern: "majority"` có nghĩa đọc dữ liệu ở mức commit đa số có sẵn tại secondary đó; nó **không bảo đảm** secondary đã theo kịp thay đổi mới nhất của primary.

## 4. Đường đi chi tiết của một yêu cầu đọc

Giả sử ứng dụng cần 10 đơn mới nhất của khách `C01`:

```javascript
db.orders.find(
  { customerId: "C01", status: "PAID" },
  { customerId: 1, status: 1, createdAt: 1, _id: 0 }
).sort({ createdAt: -1 }).limit(10);
```

### Bước 1 — Driver đóng gói và gửi command

Driver tạo một command dạng BSON với các thành phần tương đương `find`, `filter`, `projection`, `sort` và `limit`. Mongosh cung cấp cú pháp `find()` thân thiện; lệnh thực truyền tới máy chủ là command của giao thức MongoDB.

Nếu dùng replica set và cấu hình mặc định, driver thường chọn primary để đọc. Nếu ứng dụng chọn `secondaryPreferred`, driver có thể chọn secondary phù hợp; khi không có secondary phù hợp, nó có thể dùng primary. Với các chế độ đọc khác, quy tắc lựa chọn sẽ khác.

### Bước 2 — Máy chủ kiểm tra lệnh và quyền

`mongod` nhận command trên kết nối đã được thiết lập, kiểm tra cú pháp, ngữ cảnh database/collection, quyền truy cập và các tùy chọn của lệnh. Một lệnh không hợp lệ hoặc thiếu quyền có thể bị từ chối ở đây, trước khi đọc tài liệu.

Nếu có `readConcern`, MongoDB còn phải cung cấp cách nhìn dữ liệu thích hợp với mức nhất quán đã yêu cầu. Một số yêu cầu có thể phải đợi trạng thái dữ liệu đáp ứng điều kiện đọc.

### Bước 3 — Query planner chọn cách lấy tài liệu

Máy chủ phân tích điều kiện lọc, thứ tự sắp xếp và phép chiếu. Bộ lập kế hoạch có thể cân nhắc những cách thực thi như:

- **Collection scan (`COLLSCAN`):** đọc tuần tự các tài liệu liên quan trong collection.
- **Index scan (`IXSCAN`):** dùng index để giới hạn vị trí tìm kiếm hoặc tận dụng thứ tự khóa.
- **Index scan rồi fetch:** tìm khóa index trước, sau đó đọc BSON của tài liệu để kiểm tra/hoàn thành kết quả.
- **Covered query:** khi thỏa các điều kiện thích hợp, chỉ dùng thông tin trong index mà không cần đọc tài liệu gốc.

Nếu thường xuyên chạy truy vấn ở trên, có thể cân nhắc:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
});
```

Với hai điều kiện bằng nhau đứng trước `createdAt`, index này có cơ hội giúp lọc và lấy dữ liệu theo thứ tự mới nhất. Tuy vậy, **có index không đồng nghĩa planner chắc chắn chọn index**; kế hoạch phụ thuộc dữ liệu, độ chọn lọc, thống kê và nhiều điều kiện khác.

### Bước 4 — Storage engine lấy khóa và tài liệu BSON

Khi execution engine cần khóa index hoặc tài liệu, storage engine lấy dữ liệu qua cấu trúc lưu trữ của WiredTiger. Dữ liệu có thể đã nằm trong **cache** hoặc cần đọc từ đĩa. Một truy vấn được hỗ trợ bằng index vẫn có thể phải đọc nhiều tài liệu nếu projection hoặc bộ lọc không nằm trọn trong index.

WiredTiger dùng các cơ chế điều khiển đồng thời và cách nhìn dữ liệu theo phiên bản để các thao tác đọc/ghi có thể cùng diễn ra. Không nên hình dung mọi lệnh đọc đều khóa toàn bộ collection cho đến khi hoàn thành.

### Bước 5 — Lọc, sắp xếp, chiếu và trả kết quả

Máy chủ áp dụng những phần còn lại của truy vấn: lọc bổ sung, sắp xếp nếu index chưa đáp ứng được, chọn trường và giới hạn số kết quả. Đối với kết quả lớn, máy chủ có thể trả **một batch đầu tiên và một cursor ID**. Driver sau đó gửi `getMore` để lấy các batch tiếp theo; đây vẫn là một thao tác đọc logic ở phía ứng dụng nhưng có thể bao gồm nhiều lượt trao đổi mạng.

```text
find() trong ứng dụng
      |
      v
Driver chọn server và gửi command BSON
      |
      v
mongod: kiểm tra quyền + readConcern
      |
      v
Query planner / execution engine
      |
      +--> index scan ---------+
      |                        |
      +--> collection scan     v
                           WiredTiger
                         cache / đĩa
                              |
                              v
                     Lọc / sort / projection
                              |
                              v
                     Batch BSON + cursor
                              |
                              v
                    Driver trả về ứng dụng
                         (getMore nếu cần)
```

Điểm đáng nhớ: quá trình đọc gồm **hai chi phí khác nhau**: đến đúng máy chủ (kết nối, chọn server, định tuyến) và lấy/xử lý đúng dữ liệu (index, cache, đĩa, sắp xếp, cursor).

### 4.1. Đọc từ primary, secondary và mức nhất quán

| Lựa chọn | Ý nghĩa cơ bản | Giới hạn cần nhớ |
|---|---|---|
| `readPreference: primary` | Đọc từ primary, mặc định trong replica set | Không tự biến `readConcern: local` thành dữ liệu đã commit đa số |
| `readPreference: secondary` | Đọc từ secondary phù hợp | Có thể thấy dữ liệu trễ so với primary |
| `readPreference: secondaryPreferred` | Ưu tiên secondary, có thể dự phòng primary | Nơi đọc thực tế tùy topology tại thời điểm chọn |
| `readConcern: local` | Đọc dữ liệu đang có sẵn trên thành viên được chọn | Có thể bao gồm ghi chưa được commit đa số và có nguy cơ rollback |
| `readConcern: majority` | Đọc dữ liệu đã được xác nhận commit theo đa số | Không nhất thiết là trạng thái mới nhất của toàn bộ cụm |
| `readConcern: snapshot` | Đọc từ một ảnh chụp dữ liệu nhất quán tại một thời điểm được hỗ trợ | Phụ thuộc ngữ cảnh thao tác/transaction và điều kiện triển khai |
| `readConcern: linearizable` | Áp dụng cho đọc phù hợp trên primary, cung cấp bảo đảm mạnh về thứ tự thời gian thực | Có ràng buộc và chi phí chờ riêng; không phải tùy chọn phổ quát |

Các mức read concern có điều kiện hỗ trợ tùy phiên bản và loại thao tác. Đặc biệt, cấu hình `secondary` không tự bảo đảm đọc thấy ngay lệnh ghi vừa thực hiện. Với luồng cần **read-your-writes** qua nhiều nút, ứng dụng nên hiểu session nhân quả (causal consistency), cùng điều kiện thích hợp về `readConcern` và `writeConcern`, thay vì giả định mọi thành viên luôn đồng bộ tức thì.

## 5. Đường đi chi tiết của một yêu cầu ghi

Xét lệnh thêm đơn:

```javascript
db.runCommand({
  insert: "orders",
  documents: [{
    _id: "ORD-002",
    customerId: "C01",
    status: "PAID",
    total: NumberDecimal("480000"),
    createdAt: ISODate("2026-10-21T09:00:00Z")
  }],
  writeConcern: { w: "majority", wtimeout: 5000 }
});
```

Ví dụ này dùng lệnh cấp database để thể hiện rõ `writeConcern`. Trong ứng dụng, driver có thể cung cấp API tương đương như `insertOne()` kèm tùy chọn ghi.

### Bước 1 — Chọn máy chủ tiếp nhận ghi

Trong replica set thông thường, thao tác ghi hướng tới **primary**. Driver có thể đã biết primary nhờ quá trình theo dõi topology; khi đổi primary sau sự cố, driver cần cập nhật thông tin và chọn lại đích.

Với sharded cluster, command trước hết đi đến `mongos`; router quyết định shard liên quan, rồi shard primary xử lý ghi.

### Bước 2 — Kiểm tra lệnh và những ràng buộc

Máy chủ kiểm tra xác thực/quyền, cấu trúc BSON, kích thước tài liệu, quy tắc xác thực schema nếu được cấu hình và các ràng buộc liên quan đến index. Ví dụ `_id` phải duy nhất trong collection; ghi trùng khóa duy nhất có thể trả lỗi **duplicate key**.

Đối với `updateOne()`, máy chủ còn phải tìm tài liệu khớp điều kiện trước khi thay đổi. Vì vậy index có thể ảnh hưởng mạnh đến hiệu năng **ghi có điều kiện**, dù bản thân index còn phải được cập nhật sau khi sửa dữ liệu.

### Bước 3 — Storage engine áp dụng thay đổi

Primary dùng WiredTiger thực hiện thay đổi trên tài liệu và các index liên quan. MongoDB cung cấp tính **nguyên tử ở mức một tài liệu**: một lần cập nhật tài liệu được áp dụng như một đơn vị, kể cả khi thay đổi nhiều trường của tài liệu đó.

Khả năng thực hiện đồng thời không có nghĩa hai lệnh tranh chấp cùng tài liệu luôn chạy trơn tru; hệ thống có thể đợi, giải quyết xung đột hoặc yêu cầu thử lại tùy loại thao tác. Các lệnh thay đổi **nhiều tài liệu** không mặc nhiên tạo thành một giao dịch nguyên tử trên toàn bộ tập, trừ khi dùng transaction thích hợp.

WiredTiger quản lý dữ liệu trong cache và có cơ chế ghi bền vững qua **journal** cùng các lần **checkpoint**. Không nên hình dung mỗi lần `insertOne()` đều đợi ghi nguyên một tài liệu vào tệp dữ liệu cuối cùng trước khi trả lời; thời điểm trả lời phụ thuộc các bảo đảm ghi đã yêu cầu.

### Bước 4 — Ghi thay đổi vào lịch sử nhân bản

Trong replica set, primary tạo các mục thay đổi phục vụ **oplog**. Secondary kéo và áp dụng oplog theo trình tự để cập nhật bản sao của mình. Hoạt động này không đồng bộ hoàn toàn với thời điểm ứng dụng gửi lệnh; tại một khoảnh khắc, secondary có thể vẫn đang theo sau primary.

Trong quá trình nhân bản:

1. Primary thực hiện thay đổi và ghi lại thông tin thay đổi theo cơ chế của replica set.
2. Các secondary nhận các mục oplog chưa áp dụng.
3. Secondary tái hiện các thay đổi trên dữ liệu và index tại nút của mình.
4. Trạng thái xác nhận của các thành viên quyết định khi nào thao tác đáp ứng `writeConcern`.

Đây là mô tả **quan hệ nhân quả logic**. Chi tiết thời điểm ghi journal, commit và đồng bộ thay đổi được MongoDB phối hợp bên trong, không phải một lịch phát mạng cố định cho từng lệnh.

### Bước 5 — Xác nhận ghi theo write concern

MongoDB trả kết quả khi các điều kiện ghi đã yêu cầu được đáp ứng, hoặc trả lỗi/thông báo hết thời gian chờ tương ứng. Ba cấu hình dễ gặp:

| Cấu hình minh họa | Khi nào xem là đáp ứng | Điều cần hiểu |
|---|---|---|
| `{ w: 1 }` | Primary đã xác nhận ghi | Chưa đòi xác nhận đa số; ghi có thể bị rollback khi có failover |
| `{ w: "majority" }` | Ghi đã được xác nhận theo quy tắc đa số thành viên có quyền tham gia xác nhận dữ liệu của replica set | Tăng bảo đảm tồn tại qua failover so với `w: 1`; thời gian chờ có thể lớn hơn |
| `{ w: "majority", j: true }` | Ngoài xác nhận majority, yêu cầu các bảo đảm journal áp dụng theo cấu hình | `j` điều khiển yêu cầu bền vững trên journal, không thay thế `w` |

Trong replica set gồm primary và hai secondary đều có quyền bỏ phiếu, `w: "majority"` thông thường cần **hai trong ba thành viên** xác nhận. Thành viên **arbiter** không lưu dữ liệu nên không thay thế một bản sao dữ liệu trong việc bảo vệ bản ghi.

Hãy phân biệt:

- **Journal:** hỗ trợ khôi phục trạng thái cục bộ sau sự cố tiến trình/máy.
- **Checkpoint:** định kỳ đưa trạng thái lưu trữ đến một mốc bền vững; không phải mỗi ACK ghi đều chờ checkpoint mới.
- **Oplog/replication:** sao chép thay đổi giữa các nút để có nhiều bản dữ liệu.
- **Write concern:** điều kiện cần đạt trước khi client nhận xác nhận.

Sự kết hợp bảo đảm journal và majority phụ thuộc storage engine, phiên bản và cấu hình replica set. Không thể suy ra chỉ từ `w: "majority"` rằng mọi nút đã ghi tất cả tệp dữ liệu đến checkpoint mới nhất.

### 5.1. Hết thời gian chờ không đồng nghĩa dữ liệu chưa được ghi

Trong ví dụ `wtimeout: 5000`, primary có thể đã áp dụng lệnh nhưng secondary xác nhận chậm. Khi thời gian chờ write concern hết, client nhận lỗi write concern mặc dù **tác động ghi có thể đã xảy ra**. Tương tự, nếu mạng đứt sau khi primary xử lý lệnh nhưng trước khi client nhận ACK, trạng thái cuối cùng từ góc nhìn client có thể chưa rõ.

Vì vậy, đừng tự động viết lại cùng một lệnh ghi với ID mới sau mọi lỗi. Có thể:

- Kiểm tra kết quả bằng khóa nghiệp vụ hoặc `_id` ổn định.
- Dùng tính năng **retryable writes** của driver khi thao tác/topology đáp ứng điều kiện hỗ trợ.
- Thiết kế thao tác có tính lặp an toàn (idempotency) khi cần, nhất là với nghiệp vụ thanh toán, tạo đơn và xử lý sự kiện.

Retryable write cũng không có nghĩa mọi dạng ghi hoặc mọi lỗi đều được thử lại tự động. Cần phân biệt lỗi do dữ liệu (ví dụ trùng unique key), mất kết nối, failover và lỗi write concern.

### 5.2. Hai trường hợp xác nhận ghi trên cùng một replica set

```text
                   Replica set: P, S1, S2

Client ---- insert ----> P (primary)
                         |
                         +-- áp dụng thay đổi
                         +-- ghi oplog
                         |
                         +-------------> S1 (nhận/áp dụng oplog)
                         |
                         +-------------> S2 (nhận/áp dụng oplog)

  w:1       -> ACK có thể đến sau xác nhận từ P
  w:majority-> đợi điều kiện xác nhận đa số (ví dụ P + S1)

  ACK không nói rằng tất cả secondary đã bắt kịp.
```

Ví dụ không nhằm ấn định thứ tự vật lý giữa ghi cache/journal/oplog hay thứ tự trả ACK giữa các nút, mà chỉ diễn giải **ngưỡng xác nhận**.

## 6. Khi có sharding: thêm tầng định tuyến

MongoDB có thể chia một collection giữa nhiều **shard** dựa trên **shard key**. Ứng dụng thông thường không cần tự biết tài liệu đang nằm ở shard nào: nó kết nối tới `mongos`.

```text
                          ỨNG DỤNG
                              |
                            Driver
                              |
                         mongos router
                              |
                 Metadata định tuyến (cache)
                      từ config servers
                       /             \
                      v               v
                  SHARD A           SHARD B
                replica set       replica set
               P / S1 / S2       P / S1 / S2
                    |                  |
                 WiredTiger         WiredTiger
```

### 6.1. Đọc trong sharded cluster

Giả sử collection được shard theo `customerId`. Với truy vấn:

```javascript
db.orders.find({ customerId: "C01" });
```

Nếu router có đủ thông tin shard key để xác định nơi lưu `C01`, nó có thể **định tuyến có mục tiêu (targeted query)** tới shard liên quan. Nếu truy vấn chỉ có `status: "PAID"` và không đủ thông tin chọn shard, `mongos` có thể phải gửi tới **nhiều shard (scatter-gather)** rồi gộp kết quả.

Khi có `sort`, `limit` hoặc aggregation, router và các shard có thể chia nhau công việc. Việc gộp kết quả có thể tạo thêm chi phí mạng, CPU và bộ nhớ; thời gian phản hồi của một truy vấn trên nhiều shard còn có thể chịu ảnh hưởng của shard chậm nhất.

### 6.2. Ghi trong sharded cluster

Với lệnh thêm mới, `mongos` dựa vào shard key và metadata để xác định shard đích. Primary thuộc shard đó thực hiện ghi và nhân bản trong replica set của shard. Với một số dạng ghi không đủ thông tin để chọn một shard, MongoDB có các quy tắc và giới hạn khác nhau tùy thao tác, lựa chọn shard key và phiên bản; không nên mặc định lệnh ghi sẽ tự động cập nhật được mọi shard.

Nếu metadata thay đổi do di chuyển các khoảng dữ liệu, router có thể cần làm mới thông tin và thử định tuyến lại. Sự di chuyển dữ liệu là một lớp vận hành bổ sung, nhưng **không thay thế** cơ chế lưu trữ hoặc replication trong từng shard.

### 6.3. Giao dịch nhiều tài liệu, nhiều shard

Thao tác trên **một tài liệu** vẫn có bảo đảm nguyên tử ở mức tài liệu. Khi nghiệp vụ bắt buộc cập nhật đồng thời nhiều tài liệu hoặc nhiều collection như một đơn vị, có thể dùng **multi-document transaction** nếu topology hỗ trợ. Trong sharded cluster, giao dịch nhiều shard phải có phối hợp commit giữa các bên; chi phí và điều kiện lỗi phức tạp hơn một lệnh ghi đơn lẻ.

Không nên mặc định mọi lệnh ứng dụng đều chạy trong transaction. Phần lớn thao tác đơn giản được máy chủ xử lý như các command độc lập.

## 7. Đối chiếu đường đọc và đường ghi

| Giai đoạn | Yêu cầu đọc | Yêu cầu ghi |
|---|---|---|
| Điểm bắt đầu | Driver gửi `find`/`aggregate` | Driver gửi `insert`/`update`/`delete` |
| Chọn server | Theo `readPreference` và topology | Thường hướng tới primary của replica set hoặc `mongos` |
| Quy tắc nhất quán | `readConcern` quyết định mức dữ liệu nhìn thấy | `writeConcern` quyết định ngưỡng xác nhận |
| Truy cập dữ liệu | Query planner chọn index hoặc quét tài liệu | Có thể dùng index để tìm bản ghi cần sửa; phải cập nhật index liên quan |
| Storage engine | Đọc từ cache/đĩa, áp dụng cách nhìn dữ liệu thích hợp | Thay đổi tài liệu/index, sử dụng cơ chế journal/checkpoint |
| Replica set | Secondary có thể phục vụ đọc nhưng có độ trễ | Primary phát sinh thay đổi và secondary sao chép |
| Kết quả trả về | Tài liệu hoặc batch/cursor | Kết quả ghi hoặc lỗi; trạng thái sau lỗi mạng có thể chưa rõ |
| Điểm nghẽn thường gặp | Quét nhiều tài liệu, sort, I/O, getMore, định tuyến | Tranh chấp ghi, số index phải cập nhật, journal, replication và write concern |

Một lệnh **đọc** phải trả lời “lấy dữ liệu nào, từ bản sao nào, ở mức nhất quán nào?”. Một lệnh **ghi** phải trả lời “thay đổi gì, ghi vào đâu, cần bao nhiêu xác nhận thì đủ?”.

## 8. Quan sát đường đi bằng công cụ của MongoDB

Không cần đoán rằng một truy vấn chậm là do mạng, do index hay do replica set. Hãy quan sát đúng lớp liên quan.

### 8.1. Xem kế hoạch đọc

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 }).explain("executionStats");
```

Những trường/thông tin thường hữu ích:

| Dấu hiệu | Cách diễn giải |
|---|---|
| `COLLSCAN` | Có thao tác quét collection |
| `IXSCAN` | Có thao tác quét index |
| `FETCH` | Có bước lấy tài liệu sau khi đọc khóa index |
| `SORT` | Xem có bước sắp xếp tách khỏi thứ tự index không |
| `totalKeysExamined` | Có bao nhiêu khóa index được xem xét |
| `totalDocsExamined` | Có bao nhiêu tài liệu được xem xét |
| `nReturned` | Có bao nhiêu kết quả được trả về |

Cấu trúc kế hoạch và tên một số stage có thể thay đổi theo phiên bản MongoDB và execution engine. Lệnh `explain()` giúp phân tích **phần thực thi trên máy chủ**, nhưng không tự đo hết thời gian chờ chọn server, đợi pool, mạng giữa ứng dụng và máy chủ hoặc toàn bộ quá trình tải cursor của ứng dụng.

### 8.2. Xác định topology đang kết nối

```javascript
// Cho biết thông tin về máy chủ/router đang tiếp nhận lệnh.
db.adminCommand({ hello: 1 });

// Trong replica set, khi tài khoản có quyền phù hợp:
rs.status();
```

`hello` có thể cung cấp thông tin giúp nhận diện vai trò primary/secondary và thành viên replica set. Với sharded cluster, phản hồi từ `mongos` khác với phản hồi của `mongod` trong replica set. `rs.status()` cần chạy trong ngữ cảnh phù hợp và có thể yêu cầu quyền giám sát tương ứng.

Khi phân tích production, kết hợp số liệu về replication lag, số kết nối, độ trễ đọc/ghi, cache/I/O và thời gian chờ của driver. Các thông tin này bổ sung cho `explain`, không bị thay thế bởi nó.

## 9. Những tình huống minh họa

### Tình huống A — Có index nhưng đọc vẫn chậm

Truy vấn lọc `status: "PAID"` trong một collection mà phần lớn đơn hàng đều là `PAID`. Index trên `status` có thể không giảm nhiều dữ liệu đầu vào. Nếu ứng dụng còn sắp xếp một trường không phù hợp với index hoặc trả về nhiều megabyte, thời gian đọc tài liệu và truyền nhiều batch vẫn đáng kể.

**Cách suy nghĩ:** đối chiếu điều kiện lọc, tỷ lệ tài liệu khớp, index được chọn, sort, số tài liệu thực đọc và kích thước kết quả. Đừng chỉ nhìn việc index “đã tồn tại”.

### Tình huống B — Ghi được ACK nhưng secondary chưa thấy

Ứng dụng ghi vào primary với `w: 1`, ngay sau đó đọc từ secondary. Đường đọc có thể đến secondary chưa áp dụng oplog tương ứng. Kết quả đọc thiếu đơn hàng mới là biểu hiện độ trễ nhân bản, không đủ căn cứ để kết luận lệnh ghi trước đó không chạy.

**Cách suy nghĩ:** xem lựa chọn `readPreference`, mức `readConcern`, yêu cầu `writeConcern`, trạng thái replication và nhu cầu đọc nhất quán theo session.

### Tình huống C — Ghi trả write concern timeout

Primary chấp nhận thao tác nhưng secondary gặp độ trễ lớn; lệnh yêu cầu `w: "majority"` với thời gian chờ ngắn. Ứng dụng có thể nhận lỗi timeout ở mức write concern dù primary đã thay đổi dữ liệu.

**Cách suy nghĩ:** phân biệt thất bại thực thi command với chưa đáp ứng mức xác nhận. Kiểm tra lại bằng khóa ổn định hoặc dùng cơ chế retry an toàn trước khi tạo thêm một giao dịch nghiệp vụ.

### Tình huống D — Một query trở nên chậm sau khi sharding

Trước sharding, truy vấn quét một collection tại một cụm; sau sharding, cùng biểu thức thiếu shard key khiến `mongos` gửi tới nhiều shard. Tổng chi phí định tuyến, xử lý phân tán và gộp kết quả có thể tăng dù mỗi shard xử lý ít dữ liệu hơn.

**Cách suy nghĩ:** xác định query là targeted hay scatter-gather, kiểm tra shard key có xuất hiện trong bộ lọc không, và xem nơi thực hiện sort/aggregation.

## 10. Tự luyện tập theo đường đi thực tế

Có thể thực hiện các bước dưới đây trên môi trường MongoDB thử nghiệm, không cần sửa cấu hình production:

1. Tạo collection `orders` với trường `customerId`, `status`, `createdAt` và ít nhất vài tài liệu khác nhau.
2. Chạy `find` có lọc, sort và `explain("executionStats")`; quan sát index scan/collection scan khi **chưa** tạo compound index.
3. Tạo index `{ customerId: 1, status: 1, createdAt: -1 }` rồi xem lại kế hoạch. Với tập dữ liệu quá nhỏ, planner có thể vẫn chọn collection scan.
4. Nếu có replica set thử nghiệm, xem `hello` và trạng thái primary/secondary; tìm hiểu read preference của phiên kết nối hiện tại trước khi thử đọc secondary.
5. Gửi lệnh ghi với `writeConcern` phù hợp môi trường thử nghiệm. Phân biệt kết quả ghi trả về với trạng thái nhân bản quan sát được.
6. Nếu có sharded cluster thử nghiệm, so sánh truy vấn có shard key và thiếu shard key về số shard được nhắm tới và chi phí gộp kết quả.

### Câu hỏi tự kiểm tra

1. Tại sao `find()` có thể phát sinh nhiều lượt truyền mạng dù phía ứng dụng gọi một lần?
2. Vì sao `readPreference: secondary` và `readConcern: majority` không đồng nghĩa “luôn đọc dữ liệu mới nhất”?
3. Khi chạy `updateOne()` với điều kiện lọc, index có thể ảnh hưởng tới cả phần nào của quá trình ghi?
4. Điều gì khác nhau giữa journal, checkpoint và oplog?
5. Với `w: 1`, primary mất vai trò ngay sau khi ACK, ứng dụng có thể gặp rủi ro gì?
6. Vì sao `wtimeout` hoặc mất kết nối sau khi gửi write không đủ để kết luận rằng thao tác chưa được áp dụng?
7. Một truy vấn thiếu shard key ảnh hưởng đến quá trình định tuyến tại `mongos` như thế nào?

**Kết nối ý chính:** MongoDB là một hệ thống nhiều lớp. **Driver quyết định gửi lệnh đến đâu; `mongod` hoặc `mongos` định tuyến và xử lý; query planner và WiredTiger quyết định cách đọc/ghi; replica set và read/write concern quyết định mức dữ liệu nhìn thấy và ngưỡng xác nhận.** Khi một thao tác chậm hoặc trả kết quả không như mong đợi, lần theo đúng đường đi của yêu cầu sẽ giúp khoanh vùng vấn đề chính xác hơn.
