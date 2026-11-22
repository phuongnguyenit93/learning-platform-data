# Phân biệt journal với oplog và dữ liệu sao lưu trong MongoDB

## Mục tiêu bài học

Trong kiến trúc MongoDB, **journal**, **oplog** và **backup** đều liên quan đến dữ liệu đã ghi, nhưng chúng phục vụ ba mục đích khác nhau. Nhầm lẫn giữa chúng dễ dẫn đến thiết kế sai: cho rằng replica set đã thay thế backup, hoặc tưởng journal có thể hoàn tác lệnh xóa nhầm.

Sau bài học, người học có thể:

- Giải thích vì sao **WiredTiger journal** giúp MongoDB phục hồi sau lỗi tiến trình hoặc mất điện, và vai trò của checkpoint trong quá trình ấy.
- Mô tả **replica set oplog** ghi lại các thay đổi phục vụ đồng bộ primary–secondary, và hiểu **oplog window**.
- Phân biệt **bản sao lưu có thể khôi phục** với dữ liệu đang hoạt động, checkpoint nội bộ, journal và oplog.
- Liên hệ ba cơ chế với **write concern**, **replication**, **recovery point objective (RPO)** và **recovery time objective (RTO)**.
- Chọn cách xử lý khi gặp crash, secondary bị tụt đồng bộ, xóa nhầm dữ liệu hoặc hỏng toàn bộ cụm.
- Thực hành quan sát oplog, thống kê journal và xây dựng bản dump nhất quán cho một replica set thử nghiệm.

> **Ghi nhớ:** Journal hỗ trợ phục hồi **trạng thái bền vững của một node**; oplog giúp **các node của replica set theo kịp thay đổi**; backup cung cấp **điểm khôi phục độc lập** khi dữ liệu đang chạy không còn đúng hoặc không còn tồn tại.

---

## 1. Ba câu hỏi, ba cơ chế

Giả sử ứng dụng ghi một đơn hàng vào MongoDB lúc 09:00, sau đó gặp sự cố. Câu hỏi cần trả lời sẽ quyết định cơ chế nào có ích.

| Câu hỏi | Cơ chế liên quan chính | Vì sao |
|---|---|---|
| Node đang ghi bất ngờ mất điện, khi khởi động lại có lấy lại được các ghi bền vững chưa kịp đưa vào data file không? | **Journal + checkpoint** | WiredTiger dùng log trên đĩa để khôi phục các thay đổi sau checkpoint gần nhất |
| Primary vừa thay đổi đơn hàng, làm sao secondary nhận và áp dụng thay đổi đó? | **Oplog + replication** | Secondary đọc các operation từ oplog của nguồn đồng bộ rồi áp dụng vào dữ liệu của mình |
| Một nhân viên xóa nhầm hàng nghìn đơn hàng và thao tác xóa đã được nhân bản đến mọi node, làm sao quay về dữ liệu trước lúc xóa? | **Backup / point-in-time recovery** | Phải khôi phục từ dữ liệu được lưu giữ độc lập và, nếu có, tái phát các thay đổi đến mốc thời gian mong muốn |

Ba cơ chế có thể cùng xuất hiện trong một hệ thống:

~~~text
                              Ứng dụng
                                 |
                            Ghi dữ liệu
                                 |
                                 v
                       Replica set PRIMARY
                       +------------------+
                       | Collections      |
                       | Indexes          |
                       | WiredTiger       |
                       | Journal +        |
                       | Checkpoint       |
                       |                  |
                       | local.oplog.rs   |
                       +------------------+
                                 |
                      Đồng bộ operation qua oplog
                        /                    \
                       v                      v
                SECONDARY A              SECONDARY B
              +-------------+          +-------------+
              | Dữ liệu     |          | Dữ liệu     |
              | Journal     |          | Journal     |
              | Oplog riêng |          | Oplog riêng |
              +-------------+          +-------------+

          Hệ thống backup độc lập
          = snapshot/dump + lịch sử thay đổi theo chính sách
          = lưu trữ riêng + khả năng restore đã kiểm thử
~~~

**Lưu ý:** Hình trên minh họa đường đi khái niệm. WiredTiger journal không được phát trực tiếp như một luồng journal từ primary sang secondary. Replication dùng oplog; mỗi node tự duy trì tính bền vững của phần dữ liệu nó ghi bằng cơ chế storage engine tương ứng.

---

## 2. Journal là gì?

### 2.1. Vai trò trong storage engine

Với storage engine **WiredTiger**, MongoDB sử dụng cơ chế **write-ahead logging (WAL)**: ghi thông tin cần thiết vào các journal file trên đĩa để có thể phục hồi sau khi tiến trình dừng bất ngờ. Journal là cơ chế nội bộ của **từng mongod**; không phải một database dành cho người dùng truy vấn.

WiredTiger vừa quản lý dữ liệu trên đĩa vừa giữ những thay đổi đang diễn ra trong bộ nhớ. Theo chu kỳ, nó tạo **checkpoint** — một trạng thái dữ liệu nhất quán đã được ghi vào data files. Nếu tiến trình ngừng đúng giữa hai checkpoint, journal có thể giúp áp dụng lại những thay đổi phù hợp sau checkpoint cuối.

Một cách hình dung:

~~~text
Thời gian trên một node
--------------------------------------------------------------------->
T0                     T1                    T2                  T3
|                      |                     |                   |
Checkpoint A           Ghi X                 Ghi Y               CRASH
(dữ liệu nhất quán)    (journaled)           (journaled)

Khởi động lại:
1. Đọc checkpoint A trong data files.
2. Xác định các journal record hợp lệ sau checkpoint A.
3. Áp dụng các record cần thiết để phục hồi trạng thái nhất quán.

Nếu X hoặc Y chưa bền vững trong journal trước crash,
chúng có thể không nằm trong trạng thái đã phục hồi.
~~~

Điểm quan trọng: **một thao tác đã chạy trong bộ nhớ không mặc nhiên đồng nghĩa với thao tác đã được ghi bền vững xuống đĩa**. Điều kiện xác nhận của write concern sẽ quyết định ứng dụng nhận phản hồi thành công vào thời điểm nào.

### 2.2. Journal ghi những gì?

WiredTiger journal lưu thông tin ở cấp storage engine để phục hồi các biến đổi dữ liệu, bao gồm cả biến đổi nội bộ liên quan đến index. Nó khác với một bản ghi nghiệp vụ kiểu “người dùng A đã sửa đơn hàng B vì lý do C”.

Tài liệu kỹ thuật MongoDB mô tả WiredTiger tạo journal record cho thao tác ghi và các thay đổi nội bộ liên quan. Journal **không được thiết kế** để ứng dụng đọc thành một bảng lịch sử thay đổi document, truy vấn theo collection hoặc chọn một ngày trong tháng trước để khôi phục.

Trên một hệ thống tự quản lý dùng WiredTiger, journal thường nằm dưới thư mục dữ liệu:

~~~text
<dbPath>/
  WiredTiger...
  collection-...
  index-...
  journal/
    WiredTigerLog.0000000...
    WiredTigerLog.0000000...
~~~

Đây là **các file do storage engine quản lý**. Không mở, sửa, xóa, di chuyển hay “dọn dẹp” riêng journal file trong lúc MongoDB đang vận hành. Thao tác đó có thể làm database hỏng hoặc mất khả năng khôi phục.

### 2.3. Checkpoint không phải backup

Checkpoint là **mốc nhất quán nội bộ** để storage engine quản lý data files và phục hồi. WiredTiger thường tạo checkpoint định kỳ; tài liệu MongoDB mô tả khoảng mặc định 60 giây. Journal hỗ trợ phục hồi những thay đổi sau checkpoint gần nhất.

Một checkpoint:

- Nằm trong bộ dữ liệu đang hoạt động của node.
- Có thể bị mất cùng ổ đĩa hoặc host.
- Không phải bản sao lịch sử để lựa chọn tùy ý lúc restore.
- Không thay cho cơ chế backup lưu dữ liệu ở nơi độc lập.

Vì vậy, câu “MongoDB đã checkpoint nên chúng ta không cần backup” là sai.

### 2.4. Journal bảo vệ được gì và không bảo vệ được gì?

**Journal hữu ích khi:**

- Tiến trình mongod crash.
- Hệ điều hành hoặc máy chủ khởi động lại bất ngờ.
- Data files chưa phản ánh đầy đủ các ghi sau checkpoint nhưng journal bền vững vẫn còn.

**Journal không phải giải pháp trực tiếp khi:**

- Xóa nhầm document và xóa đã được ghi thành công.
- Chạy nhầm câu lệnh cập nhật hàng loạt.
- Mất toàn bộ thiết bị lưu trữ cùng data files và journal.
- Dữ liệu bị mã độc làm hỏng hoặc mã hóa, gây ảnh hưởng đến cả tệp đang hoạt động.
- Muốn khôi phục database tại một thời điểm tùy ý cách đây nhiều ngày.

Journal bảo vệ tính nhất quán và độ bền của trạng thái **đã được chấp nhận ghi**, chứ không phân biệt thao tác đúng nghiệp vụ hay thao tác sai do con người.

### 2.5. Phiên bản và ngoại lệ cần nhớ

Với **WiredTiger**, journaling là cơ chế chuẩn. Từ **MongoDB 6.1**, tài liệu MongoDB nêu journaling luôn được bật, và các tùy chọn bật/tắt journal kiểu cũ đã bị loại bỏ.

Đừng suy luận điều này cho mọi storage engine: MongoDB Enterprise từng/đang có **in-memory storage engine** với hành vi durability khác vì dữ liệu chủ yếu nằm trong bộ nhớ và không dùng cùng mô hình journal trên đĩa. Khi xem cấu hình production, xác định đúng phiên bản và storage engine.

---

## 3. Oplog là gì?

### 3.1. Operation log dành cho replica set

**Oplog** là viết tắt của **operations log**. Trong một replica set, MongoDB duy trì một collection hệ thống tên **local.oplog.rs** ghi lại những operation thay đổi dữ liệu và một số hoạt động liên quan đến replication.

Khi primary nhận một thay đổi, sự kiện thay đổi thích hợp được ghi vào oplog. Các secondary lấy những oplog entry mới từ nguồn đồng bộ, sau đó áp dụng để duy trì bản sao dữ liệu. Mỗi thành viên replica set duy trì **oplog của chính mình**; đây không phải một file journal được chép nguyên xi giữa các máy.

~~~text
PRIMARY                            SECONDARY
-------                            ---------
insert/update/delete
        |
        v
Dữ liệu + oplog entry  ----->     Đọc entry mới
                                      |
                                      v
                                 Áp dụng thay đổi
                                      |
                                      v
                                 Dữ liệu secondary
                                 Oplog secondary
~~~

Replica set có thể giúp hệ thống tiếp tục phục vụ khi một node lỗi, với điều kiện topology và bầu chọn đáp ứng yêu cầu. Nhưng **replication không tạo ra lịch sử backup độc lập**: một lệnh xóa hợp lệ trên primary cũng được secondary sao chép.

### 3.2. Oplog entry có dạng nào?

Một entry trong oplog có cấu trúc BSON, thường chứa timestamp và thông tin operation. Ví dụ **minh họa ý nghĩa**, không phải lời hứa về schema chính xác ở mọi phiên bản:

~~~javascript
{
  ts: Timestamp({ t: 1790000000, i: 1 }),
  op: "i",
  ns: "shop.orders",
  o: {
    _id: ObjectId("68f000000000000000000001"),
    orderNo: "ORD-101",
    status: "NEW"
  }
}
~~~

Một số trường phổ biến:

| Trường | Ý nghĩa khái quát |
|---|---|
| **ts** | Logical timestamp giúp xác định thứ tự thay đổi trong luồng replication |
| **op** | Loại operation; ví dụ **i** (insert), **u** (update), **d** (delete), **c** (command), **n** (no-op) |
| **ns** | Namespace, thường dạng **database.collection** |
| **o** | Nội dung operation theo định dạng thích hợp |
| **o2**, **ui**, các trường khác | Thông tin bổ sung tùy loại thao tác và phiên bản |

Không nên viết ứng dụng phụ thuộc vào biểu diễn thô của oplog. Với bài toán tiêu thụ thay đổi theo thời gian thực, ưu tiên **MongoDB Change Streams** là API được hỗ trợ. Change streams dựa trên cơ chế replication/oplog và sử dụng resume token, nhưng không phải bản backup.

### 3.3. Oplog là collection có giới hạn lịch sử

**local.oplog.rs** là collection kiểu **capped**. Oplog hoạt động như một vùng lịch sử có dung lượng được quản lý: khi có nhiều ghi mới, các entry cũ có thể bị loại bỏ để giải phóng chỗ.

**Oplog window** là khoảng thời gian giữa entry cũ nhất còn được giữ và entry mới nhất. Ví dụ:

~~~text
Oplog hiện lưu các thay đổi từ 08:00 thứ Hai đến 08:00 thứ Tư
=> Oplog window xấp xỉ 48 giờ

Secondary mất kết nối từ 12:00 thứ Hai đến 09:00 thứ Tư
=> Các entry nó cần có thể đã bị loại bỏ.
=> Có thể không tiếp tục đồng bộ tăng dần từ vị trí cũ.
=> Cần quy trình initial sync/resync phù hợp.
~~~

Cần phân biệt:

- **Oplog size**: dung lượng được cấu hình cho oplog.
- **Oplog window**: khoảng thời gian lịch sử còn giữ được, biến động theo tốc độ ghi.
- **Replication lag**: secondary hiện đang chậm sau nguồn đồng bộ bao lâu.
- **Minimum oplog retention**: một cấu hình có thể đặt ngưỡng giữ entry tối thiểu theo giờ; không biến oplog thành bản backup dài hạn.

Khi tốc độ ghi tăng, cùng một oplog size thường cho **window ngắn hơn**. MongoDB có ngoại lệ trong cơ chế capped oplog: oplog có thể vượt dung lượng danh định để tránh xóa dữ liệu cần cho majority commit point. Vì thế không nên dùng phép chia dung lượng/tốc độ ghi như một SLA tuyệt đối.

### 3.4. Oplog giúp khôi phục secondary như thế nào?

Một secondary offline ngắn hạn có thể tiếp tục nhận những entry nó bỏ lỡ nếu nguồn đồng bộ còn lịch sử cần thiết. Nếu khoảng thiếu vượt quá window, quá trình đồng bộ tăng dần có thể không tiếp tục được và node cần **initial sync** hoặc quy trình khôi phục được thiết kế cho tình huống đó.

Oplog vì thế phục vụ hai nhu cầu vận hành gần nhau:

1. **Nhân bản thay đổi từ primary/nguồn đồng bộ sang secondary**.
2. **Cho phép node bị tụt bắt kịp** mà không phải sao chép lại toàn bộ dữ liệu, miễn còn đủ lịch sử.

Nhưng nếu người dùng xóa nhầm một collection và lệnh xóa đã được ghi vào oplog, secondary sẽ thực hiện lệnh tương ứng. Oplog không tự hiểu đâu là “xóa nhầm”.

---

## 4. Dữ liệu backup là gì?

**Backup** là một bản dữ liệu được lưu giữ theo chính sách để có thể phục hồi khi hệ thống đang hoạt động mất dữ liệu, bị thay đổi sai, hỏng thiết bị hoặc cần quay về một mốc lịch sử. Muốn được coi là backup hữu dụng, ngoài bản dữ liệu cần có **quy trình restore kiểm chứng được**.

Một bộ backup có thể gồm:

- **Bản sao logic**: collection/document và metadata do công cụ như **mongodump** tạo ra.
- **Bản sao vật lý/snapshot**: trạng thái các data files được chụp bằng hệ thống snapshot có tính nhất quán.
- **Lịch sử thay đổi liên tục**: oplog được hệ thống backup thu thập/lưu riêng để hỗ trợ **point-in-time recovery (PITR)** khi cấu hình cho phép.
- **Metadata vận hành**: thời điểm snapshot, phiên bản, topology, mã hóa, vị trí lưu, chính sách giữ bản sao và thông tin phục hồi.

### 4.1. Backup logic bằng mongodump

**mongodump** đọc dữ liệu MongoDB và xuất thành các file BSON kèm metadata. **mongorestore** dùng để phục hồi từ định dạng đó.

Ví dụ xuất một database thử nghiệm:

~~~bash
mongodump \
  --uri="mongodb://USER:PASSWORD@HOST:27017/?authSource=admin" \
  --db=shop \
  --out=./backup-shop
~~~

Lệnh minh họa theo cú pháp shell kiểu Bash; thay USER, PASSWORD, HOST bằng thông tin lab, và lưu secret ngoài lịch sử terminal trong môi trường thực. Với dữ liệu đang thay đổi trong lúc dump, một bản dump đơn giản có thể **không phản ánh đúng một thời điểm nhất quán**.

Nếu dùng replica set, **mongodump --oplog** cho phép ghi lại các operation xảy ra trong thời gian dump, để khi restore có thể phát lại thành trạng thái nhất quán ở thời điểm tương ứng. Phương án này có các giới hạn rõ ràng, sẽ giải thích ở phần sau.

### 4.2. Backup vật lý bằng filesystem snapshot

Filesystem snapshot tạo bản sao trạng thái các block trên ổ dữ liệu tại một thời điểm. Với MongoDB tự quản lý, snapshot có thể nhanh, nhưng **không được coi mọi bản copy thư mục dbPath lúc mongod đang chạy là backup nhất quán**.

Đối với deployment có WiredTiger, MongoDB quy định điều kiện về journal và vị trí journal cùng logical volume với data files để snapshot một mongod đang chạy được chính xác. Nếu dữ liệu trải trên nhiều volume, phải đảm bảo snapshot nhất quán giữa chúng theo hướng dẫn chính thức.

Với **sharded cluster**, backup nhất quán còn cần phối hợp các shard và config server, cân nhắc balancer và metadata. Không thể chỉ chụp ngẫu nhiên một shard rồi gọi đó là backup toàn cluster.

### 4.3. Backup managed trên Atlas hoặc công cụ quản trị

Các dịch vụ/công cụ backup có thể tự động hóa snapshot, incremental backup, lưu trữ độc lập, theo dõi trạng thái và khôi phục. Trong Atlas, **Cloud Backup** và **Continuous Cloud Backup** có tính năng khác nhau; khả năng PITR phụ thuộc loại cluster, backup policy và cấu hình dịch vụ.

Điểm quan trọng là **dịch vụ có backup không có nghĩa mọi bản backup đều cho phép chọn từng giây bất kỳ để quay lại**. Cần xác minh cửa sổ khôi phục, tính năng theo tier, thời gian giữ lịch sử, quyền thực hiện restore và chi phí.

---

## 5. So sánh trực diện journal, oplog và backup

| Tiêu chí | WiredTiger journal | Replica set oplog | Backup |
|---|---|---|---|
| Mục đích chính | Crash recovery của từng node | Replication và bắt kịp thay đổi | Khôi phục dữ liệu sau lỗi/sai sót, theo mốc cho phép |
| Tầng chịu trách nhiệm | Storage engine | Cơ chế replica set | Hệ thống/công cụ sao lưu |
| Dạng lưu trữ | File log nội bộ dưới dbPath | Collection **local.oplog.rs** | Dump, snapshot, archive hoặc đối tượng trong backup store |
| Phạm vi | Một tiến trình/node và data files của nó | Những operation thuộc luồng replication | Phạm vi dữ liệu, cluster và metadata theo chính sách backup |
| Thời gian lưu | Theo nhu cầu phục hồi sau checkpoint | Rolling window giới hạn | Theo lịch và retention policy |
| Phục hồi sau crash của một mongod | **Có**, khi journal/data còn và ghi đã bền vững | **Không phải cơ chế crash recovery chính** | Có thể restore nhưng thường chậm và không cần nếu node tự phục hồi |
| Giúp secondary theo kịp | Không | **Có**, nếu lịch sử cần thiết còn | Có thể khôi phục node theo một quy trình riêng, không phải đồng bộ oplog thông thường |
| Phục hồi lệnh xóa nhầm đã replicate | Không | Không, thao tác xóa cũng được replicate | **Có thể**, nếu còn bản backup trước lúc xóa |
| Khôi phục đến thời điểm tùy chọn | Không | Chỉ có oplog tự nó là chưa đủ | Có thể với **PITR** nếu có base backup + lịch sử thay đổi liên tục phù hợp |
| Thay được backup độc lập? | **Không** | **Không** | Chính là thành phần cốt lõi của kế hoạch backup/restore |
| Ứng dụng nên truy cập trực tiếp? | Không | Không cho luồng nghiệp vụ; dùng Change Streams khi cần | Qua quy trình backup/restore có kiểm soát |

Một điểm dễ nhầm: **backup có thể sử dụng oplog**. Trong trường hợp đó, hệ thống backup **thu thập và lưu một phần lịch sử oplog ra nơi độc lập**. Bản sao đã lưu và có thể replay theo quy trình restore là thành phần của backup; collection **local.oplog.rs** đang quay vòng trên node vẫn không phải backup.

---

## 6. Đường đi của một lệnh ghi qua journal và oplog

Xét một replica set gồm ba thành viên data-bearing:

~~~text
          Client
            |
       insertOne()
            |
            v
      PRIMARY nhận ghi
            |
        Dữ liệu + oplog
            |
       WiredTiger journal
            |
        +---+------------------------------+
        |                                  |
        v                                  v
   SECONDARY A                        SECONDARY B
   Nhận oplog entry                   Nhận oplog entry
   Áp dụng thay đổi                   Áp dụng thay đổi
   Journal riêng                      Journal riêng
~~~

Mỗi cơ chế trả lời một lớp câu hỏi:

- **Thực thi:** MongoDB đã xử lý operation chưa?
- **Durability tại node:** operation đã được ghi bền vững qua journal/checkpoint chưa?
- **Replication:** bao nhiêu member đã đáp ứng điều kiện xác nhận?
- **Recoverability lịch sử:** bản backup nào có thể dùng để đưa database trở lại mốc phù hợp?

Không thể gộp bốn câu hỏi thành một boolean “write đã an toàn”.

### 6.1. Vai trò của write concern

Write concern cho phép ứng dụng yêu cầu mức xác nhận phù hợp. Hai tham số cơ bản:

- **w**: số member cần xác nhận, hoặc **"majority"**.
- **j**: yêu cầu ghi bền vững vào journal trên đĩa tại các member tương ứng.

Ví dụ trong mongosh, trên **replica set thử nghiệm**:

~~~javascript
db.getSiblingDB("shop").orders.insertOne(
  {
    orderNo: "ORD-201",
    amount: 450000,
    status: "CREATED"
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
);
~~~

Ở mức khái quát:

| Cấu hình | Điều kiện đáng chú ý | Giới hạn cần hiểu |
|---|---|---|
| **{ w: 1 }** | Primary xác nhận theo điều kiện của node | Không đảm bảo ghi đã được majority thừa nhận; có nguy cơ rollback khi failover |
| **{ w: 1, j: true }** | Yêu cầu ghi bền vững vào journal của member xác nhận | Độ bền ở primary không có nghĩa dữ liệu chắc chắn sống sót qua mọi lần bầu primary mới |
| **{ w: "majority" }** | Chờ số member đủ majority theo quy tắc write concern | Hành vi journaling mặc định phụ thuộc **writeConcernMajorityJournalDefault** và cấu hình replica set |
| **{ w: "majority", j: true }** | Kết hợp xác nhận majority với yêu cầu journal durability | Không chống lại xóa nhầm, hỏng dữ liệu logic hoặc mất cả cụm; vẫn cần backup |

**Chú ý chi tiết phiên bản:** Trong MongoDB hiện đại, write concern mặc định của nhiều replica set là **w: "majority"**, nhưng có trường hợp đặc biệt với arbiter và cấu hình tùy chỉnh. Thông thường **writeConcernMajorityJournalDefault** là **true**, nên majority write concern bao hàm journaling; không nên suy đoán hành vi mặc định khi chưa xem topology và cấu hình thực tế.

Thêm nữa, từ MongoDB 8.0, quy tắc xác nhận majority có chi tiết riêng về thời điểm các member ghi bền vững oplog và lúc secondary áp dụng thay đổi. Vì thế **majority acknowledgment không đồng nghĩa mọi truy vấn đọc ở mọi secondary thấy ngay dữ liệu mới**. Nếu ứng dụng cần bảo đảm thứ tự đọc/ghi giữa các phiên, cần nghiên cứu read concern và causally consistent session.

### 6.2. Journal không ngăn rollback khi failover

Giả sử ứng dụng ghi với **{ w: 1, j: true }** vào primary cũ. Journal của primary đã bền vững, nhưng secondary chưa nhận ghi. Primary mất kết nối, một secondary được bầu thành primary mới. Ghi chưa được majority thừa nhận có thể bị rollback khi primary cũ gia nhập lại.

Đây là hai rủi ro khác nhau:

- **Crash của chính node**: journal có thể giữ ghi bền vững của node đó.
- **Thay đổi primary trong replica set**: cần xét số member đã xác nhận và khả năng rollback.

Nếu dữ liệu quan trọng, cân nhắc **majority write concern** cùng các ràng buộc durability phù hợp. Không dùng journal để thay thế replication, cũng không dùng replication để thay thế backup.

### 6.3. Write concern timeout không luôn đồng nghĩa “chưa ghi”

Nếu quá thời gian **wtimeout**, ứng dụng có thể nhận write concern error dù thao tác đã thực thi trên primary. Nó không nhất thiết bị tự động hoàn tác. Khi xử lý retry, cần thiết kế **idempotency** cho API hoặc giao dịch phù hợp, đồng thời xác minh trạng thái thực tế.

---

## 7. Oplog và backup gặp nhau ở đâu?

Oplog không phải backup, nhưng nó có thể trở thành **nguồn thay đổi** cho một hệ thống backup muốn đạt tính nhất quán hoặc khôi phục theo thời điểm.

### 7.1. Dump nhất quán trong lúc hệ thống vẫn có ghi

Giả sử sao lưu các collection trong 10 phút:

~~~text
10:00  Bắt đầu mongodump
10:02  Dump xong collection A
10:04  Ứng dụng chuyển đơn hàng từ A sang B
10:08  Dump collection B
10:10  Hoàn thành dump
~~~

Nếu chỉ đọc các collection tuần tự khi dữ liệu liên tục thay đổi, bản dump có thể ghi nhận các collection ở **những thời điểm khác nhau**. Dữ liệu logic giữa các collection có thể không nhất quán.

Với một replica set đủ điều kiện, lệnh:

~~~bash
mongodump \
  --uri="mongodb://USER:PASSWORD@RS_HOST:27017/?replicaSet=rs0&authSource=admin" \
  --oplog \
  --out=./backup-rs0
~~~

sẽ lưu dữ liệu dump và các oplog entry phát sinh trong giai đoạn dump. Khi dump ra thư mục, công cụ tạo file **oplog.bson** ở cấp cao nhất trong output.

Sau đó có thể restore vào **môi trường đích dành riêng cho kiểm thử**:

~~~bash
mongorestore \
  --uri="mongodb://RESTORE_USER:RESTORE_PASSWORD@RESTORE_HOST:27017/?authSource=admin" \
  --oplogReplay \
  ./backup-rs0
~~~

Mục đích **--oplogReplay** ở ví dụ này là phát lại các operation có trong bản dump để thu được trạng thái nhất quán. Hãy kiểm tra quyền, namespace, version, metadata và các lựa chọn mongorestore theo tài liệu tương ứng trước khi thực thi.

**Các ràng buộc phải nhớ:**

- **--oplog** hoạt động với **full dump của một replica set member**; không kết hợp với **--db**, **--collection**, **--query** hoặc các tùy chọn hạn chế phạm vi không tương thích.
- Không dùng giả định rằng **mongodump --oplog** trên **mongos** cho một sharded cluster sẽ tự tạo backup nhất quán toàn cluster. Sharded deployment cần quy trình riêng.
- Một số operation quản trị/DDL diễn ra trong lúc dump có thể khiến thao tác dump với **--oplog** thất bại.
- Cần đảm bảo oplog đủ lịch sử trong thời gian dump, đủ dung lượng backup, và kiểm thử restore.
- **--oplog chỉ thu giai đoạn dump**, không tự duy trì lịch sử thay đổi liên tục trong nhiều ngày sau đó.

Ví dụ trên là hướng dẫn khái niệm cho môi trường lab, không phải lệnh tự động nên chạy trực tiếp lên cluster production đang có dữ liệu.

### 7.2. Point-in-time recovery (PITR)

**PITR** cho phép khôi phục database tới một **mốc thời gian hợp lệ** nằm trong cửa sổ khôi phục. Một hệ thống PITR điển hình cần:

1. **Bản backup nền (base backup/snapshot)** nhất quán tại thời điểm T0.
2. **Dòng thay đổi liên tục sau T0** được thu và lưu riêng, đủ để khôi phục đến T1.
3. **Quy trình replay/restore** chọn lọc các thay đổi đến đúng mốc và được kiểm chứng.
4. **Chính sách retention** bảo đảm còn đủ base backup và log tương ứng.

Ví dụ:

~~~text
01:00  Snapshot nhất quán S0
01:01  Thay đổi bình thường
...
09:29  Trạng thái đúng cuối cùng
09:30  Ứng dụng xóa nhầm 50.000 document
09:31  Lệnh xóa đã replicate đến các secondary
09:40  Phát hiện sự cố

Có S0 + lịch sử thay đổi liên tục đến 09:29:
    Restore S0 -> Replay thay đổi đến 09:29
    -> Có thể quay về trước thao tác xóa nhầm.

Chỉ có S0, không giữ lịch sử thay đổi:
    Restore S0 -> Chỉ có trạng thái 01:00,
    -> Mất mọi cập nhật hợp lệ từ 01:00 đến 09:29.
~~~

Mốc có thể chọn và độ chính xác thực tế còn phụ thuộc tính năng backup, topology, loại dữ liệu và chính sách retention. **Không thể lấy journal hiện tại để tùy ý “undo” các thay đổi đã được ghi thành công từ nhiều ngày trước.**

Trong Atlas, **Continuous Cloud Backup** là ví dụ về hệ thống dùng snapshot cộng lịch sử oplog được dịch vụ lưu vào backup storage để hỗ trợ PITR theo cấu hình. Không phải mọi tier hay mọi cluster Atlas đều có cùng tính năng/cửa sổ khôi phục.

### 7.3. Oplog window khác PITR window

Hai khái niệm này thường bị nhầm:

| Khái niệm | Thuộc thành phần | Ý nghĩa |
|---|---|---|
| **Oplog window** | Oplog của member replica set đang chạy | Khoảng thời gian operation gần đây vẫn còn trên member đó |
| **PITR window** | Dịch vụ/hệ thống backup | Khoảng thời gian có thể chọn để restore, dựa trên snapshot và lịch sử lưu giữ độc lập |

Một hệ thống có oplog window 24 giờ **không tự động** có PITR 24 giờ. Ngược lại, backup platform có thể lưu lịch sử oplog ra storage riêng để cung cấp PITR dài hơn oplog window tại thời điểm hiện tại trên member.

---

## 8. Chọn cơ chế theo loại sự cố

### Tình huống A — Mongod crash giữa hai checkpoint

**Hiện tượng:** Node khởi động lại sau mất điện, volume dữ liệu và journal vẫn còn.

**Cơ chế chính:** WiredTiger phục hồi từ checkpoint và journal record bền vững.

**Cách xử lý:** Giám sát quá trình startup/recovery, kiểm tra log/health, xác định trạng thái member và tính đúng đắn dữ liệu theo quy trình vận hành. Không vội copy/delete journal file bằng tay.

**Giới hạn:** Những thay đổi chưa bền vững trước crash có thể mất, tùy write concern và thời điểm sync.

### Tình huống B — Một secondary bị ngắt mạng vài giờ

**Hiện tượng:** Secondary chậm hơn primary, lúc kết nối lại cố tiếp tục đồng bộ.

**Cơ chế chính:** Oplog để secondary bắt kịp những operation bị lỡ.

**Cách xử lý:** Kiểm tra replication lag, oplog window, tình trạng node, tốc độ ghi và mạng. Nếu nguồn không còn lịch sử cần thiết, phải dùng quy trình initial sync/resync.

**Giới hạn:** Journal trên secondary không thay thế những entry oplog mà nó chưa từng nhận.

### Tình huống C — Primary mất vĩnh viễn nhưng replica set còn majority lành mạnh

**Hiện tượng:** Các node còn lại thực hiện bầu primary mới.

**Cơ chế chính:** Replica set, election, write concern và oplog/replication state.

**Cách xử lý:** Xác minh bầu chọn, ứng dụng reconnect/retry đúng, khôi phục độ dự phòng, xem có write chưa đạt majority bị rollback không.

**Giới hạn:** Journal của primary đã mất không giúp member khác nhận những operation chưa replicate.

### Tình huống D — Xóa nhầm dữ liệu, thao tác đã đồng bộ đến tất cả node

**Hiện tượng:** Sau lệnh deleteMany không có điều kiện đúng, dữ liệu biến mất ở primary và secondary.

**Cơ chế chính:** Backup trước khi xóa và PITR nếu đã được cấu hình.

**Cách xử lý:** Dừng luồng ghi gây hại theo runbook, bảo toàn bằng chứng, chọn mốc restore đúng, thử restore sang cluster tách biệt và kiểm chứng dữ liệu trước cutover.

**Giới hạn:** Replica set nhân bản cả lệnh xóa. Journal phục hồi trạng thái sau xóa, chứ không tự đưa dữ liệu về trước xóa.

### Tình huống E — Tất cả disk của cluster bị hỏng hoặc dữ liệu bị ransomware tấn công

**Hiện tượng:** Không còn data files/journal/oplog có thể sử dụng trên các member.

**Cơ chế chính:** Backup ở storage độc lập, lý tưởng có bản sao cách ly/khó bị sửa và quy trình khôi phục đã diễn tập.

**Cách xử lý:** Khôi phục hạ tầng sạch, kiểm soát lại credential, dùng bản backup đã xác minh, kiểm tra checksum/tính nhất quán, khởi động ứng dụng có kiểm soát.

**Giới hạn:** Một replica set ba node nhưng cả ba nằm trong cùng vùng rủi ro hoặc cùng tài khoản bị xâm nhập vẫn có thể mất đồng thời.

### Bảng chọn nhanh

| Sự cố | Journal | Oplog/replication | Backup |
|---|---|---|---|
| Mongod crash, disk còn | **Chính** | Hỗ trợ replica set sau restart | Dự phòng khi không thể phục hồi local |
| Secondary mất kết nối ngắn | Giữ độ bền local | **Chính** | Thường chưa cần |
| Secondary tụt quá oplog window | Không giải quyết khoảng thiếu | Không đủ để catch up incremental | Có thể hỗ trợ quy trình khôi phục tùy hệ thống |
| Primary failover | Giữ ghi bền vững theo từng node | **Chính**, cùng election/write concern | Dự phòng thảm họa |
| Delete/update nhầm đã replicate | Không khôi phục bản cũ | Nhân bản cả thao tác sai | **Chính** |
| Mất cùng lúc mọi bản dữ liệu đang chạy | Không còn trên disk | Không còn node nguồn | **Chính**, nếu lưu độc lập |

---

## 9. Thực hành quan sát trên replica set thử nghiệm

Các lệnh dưới đây dành cho **replica set lab** có quyền đọc thông tin trạng thái, **không thực hiện thao tác cấu hình phá hủy dữ liệu**. Với standalone, có journal nhưng không có luồng replication oplog như replica set; hãy kiểm tra topology trước khi chạy.

### 9.1. Xem trạng thái replica set

Trong mongosh:

~~~javascript
rs.status()
~~~

Quan sát các member, trạng thái primary/secondary và timestamp liên quan. Trên các phiên bản MongoDB khác nhau, cấu trúc trả về và các trường trạng thái có thể khác.

### 9.2. Xem oplog window

~~~javascript
rs.printReplicationInfo()
~~~

Ví dụ giả lập:

~~~text
configured oplog size:   2048MB
log length start to end: 86400secs (24hrs)
oplog first event time: ...
oplog last event time:  ...
now:                    ...
~~~

Diễn giải:

- **Configured oplog size**: kích thước oplog được cấu hình.
- **Log length start to end**: khoảng thời gian giữa operation cũ nhất và mới nhất còn trong oplog.
- **Oplog first/last event time**: các mốc thời gian của dữ liệu đang lưu.

Thông số này thay đổi theo workload. Oplog window hiển thị ở thời điểm quan sát **không phải một cam kết 24 giờ cố định** cho các ngày tiếp theo.

Với script, có thể lấy dữ liệu dạng object:

~~~javascript
db.getReplicationInfo()
~~~

### 9.3. Xem một vài oplog entry

Dùng tài khoản lab có quyền đọc collection hệ thống phù hợp:

~~~javascript
db.getSiblingDB("local")
  .oplog.rs
  .find(
    {},
    { ts: 1, op: 1, ns: 1, o: 1 }
  )
  .sort({ $natural: -1 })
  .limit(5);
~~~

Quan sát **ts**, **op**, **ns**, **o** rồi so với thao tác insert/update/delete vừa thực hiện ở database thử nghiệm. Cấu trúc thực tế có thể khác ví dụ, đặc biệt với transaction, lệnh DDL và các phiên bản mới.

**Không sửa local.oplog.rs bằng tay.** Đây là dữ liệu hệ thống điều khiển replication, không phải collection dành cho thao tác ứng dụng.

### 9.4. Xem thống kê journal

Trên member sử dụng WiredTiger, tài khoản có quyền giám sát có thể truy vấn:

~~~javascript
const status = db.serverStatus();

printjson(status.wiredTiger?.log);
~~~

Nhóm thống kê **wiredTiger.log** có thể thể hiện số lần ghi, lượng dữ liệu log và trạng thái liên quan đến journaling. Đây là **chỉ số vận hành**, không phải danh sách các document có thể replay thủ công.

### 9.5. Thử hai kiểu write concern

Trong database lab, chạy hai thao tác với write concern khác nhau:

~~~javascript
const orders = db.getSiblingDB("lab").orders;

orders.insertOne(
  { _id: "wc-1", type: "w1" },
  { writeConcern: { w: 1 } }
);

orders.insertOne(
  { _id: "wc-majority", type: "majority-journal" },
  { writeConcern: { w: "majority", j: true, wtimeout: 5000 } }
);
~~~

Đọc hai document:

~~~javascript
orders.find({ _id: { $in: ["wc-1", "wc-majority"] } });
~~~

**Điều rút ra:** Cả hai thao tác đều có thể cho ra document giống nhau trong điều kiện bình thường, nhưng **ý nghĩa của phản hồi thành công khác nhau**. Không nên gây crash hoặc bầu cử primary trong một môi trường dùng chung chỉ để minh họa. Nếu muốn làm fault injection, cần bộ lab tách biệt, có snapshot và quy trình reset.

### 9.6. Thử backup và restore có chủ đích

Với một replica set lab:

1. Tạo dữ liệu mẫu và ghi lại tổng số document.
2. Dùng **mongodump --oplog** tạo full dump trong khi sinh một lượng ghi nhỏ.
3. Xác nhận output có dữ liệu dump, metadata và **oplog.bson** ở vị trí dự kiến.
4. Restore bằng **mongorestore --oplogReplay** vào một **mongod/cluster đích trống** chỉ dành cho bài tập.
5. Đếm document, đối chiếu các bản ghi mẫu và kiểm tra index/metadata.
6. Ghi lại thời gian tạo backup, thời gian restore và khả năng đọc lại dữ liệu.

Mục tiêu bài tập là thấy rằng **backup phải được phục hồi thử**, còn oplog được công cụ dump thu thập **chỉ để đảm bảo tính nhất quán trong phạm vi phiên backup ấy**. Một thư mục dump chưa từng được thử restore chưa đủ để kết luận hệ thống đã có khả năng khôi phục.

---

## 10. Thiết kế chính sách backup: RPO, RTO và tính độc lập

### 10.1. RPO là gì?

**Recovery Point Objective (RPO)** là lượng dữ liệu mới tối đa doanh nghiệp chấp nhận mất khi cần khôi phục.

Ví dụ: RPO 15 phút nghĩa là phương án phải có khả năng phục hồi dữ liệu đến mốc cách thời điểm sự cố không quá khoảng 15 phút, theo điều kiện được cam kết và kiểm chứng. Backup 1 lần mỗi ngày **thường không đủ** để đáp ứng RPO 15 phút nếu không có cơ chế thu thập thay đổi bổ sung.

Journal và replica set có thể giảm rủi ro mất ghi trong những loại sự cố cụ thể, nhưng **không tự tạo RPO lịch sử cho tình huống xóa nhầm đã replicate**.

### 10.2. RTO là gì?

**Recovery Time Objective (RTO)** là thời gian tối đa được phép để khôi phục dịch vụ sau sự cố.

Ví dụ: hệ thống có bản dump 2 TB nhưng cần 10 giờ để restore có thể không đáp ứng RTO 1 giờ, dù bản backup có thể đọc được. Snapshot và các cơ chế restore nhanh có thể cần thiết tùy quy mô.

RPO và RTO là hai yêu cầu khác nhau. RPO thấp không có nghĩa RTO tự động thấp.

### 10.3. Bản backup cần được cách ly

Một thiết kế backup phù hợp thường cần:

- **Vị trí lưu độc lập** với data files và journal đang hoạt động; tránh mất cả production và backup trong một sự cố disk.
- **Quyền truy cập riêng, mã hóa và cơ chế quản lý khóa** phù hợp.
- **Chính sách retention** theo yêu cầu nghiệp vụ và pháp lý.
- **Bản sao ở vùng lỗi khác** hoặc cơ chế chống sửa/xóa trái phép khi đánh giá rủi ro yêu cầu.
- **Tự động phát hiện job backup lỗi** hoặc dung lượng/hạn mức quá thấp.
- **Restore drill định kỳ**: phục hồi vào môi trường cô lập và kiểm chứng tính nhất quán, dữ liệu, index, quyền và khả năng chạy ứng dụng.
- **Runbook rõ ràng** cho quyết định chọn điểm khôi phục, xác nhận người phê duyệt và quy trình chuyển lưu lượng sang dữ liệu đã phục hồi.

Với sharded cluster hoặc workload có transaction/phụ thuộc giữa nhiều collection, phải kiểm tra công cụ backup được hỗ trợ để bảo đảm tính nhất quán xuyên các thành phần cần thiết.

### 10.4. Chiến lược bảo vệ theo nhiều lớp

Có thể hình dung chiến lược production như sau:

~~~text
Lớp 1: Write concern + WiredTiger journal
        -> Chống mất những ghi đã bền vững do crash một node.

Lớp 2: Replica set + đủ oplog window
        -> Tăng độ sẵn sàng; secondary theo kịp thay đổi.

Lớp 3: Snapshot/dump backup được lưu riêng
        -> Khôi phục sau mất dữ liệu hoặc sai sót nghiệp vụ.

Lớp 4: Continuous backup/PITR khi cần
        -> Giảm mất dữ liệu hợp lệ sau snapshot trước đó.

Lớp 5: Restore drill + runbook + kiểm soát truy cập
        -> Biến bản sao đang lưu thành năng lực khôi phục thực tế.
~~~

Từng lớp giải quyết một nhóm rủi ro. Không nên bỏ lớp backup chỉ vì đã có journal và replica set.

---

## 11. Những hiểu lầm thường gặp

### “Journal và oplog đều là log, nên có thể thay thế nhau.”

Không. Journal ghi theo yêu cầu của storage engine để crash recovery; oplog ghi các operation phục vụ replication. Hình thức log không quyết định chức năng.

### “Journal có thể phát lại để quay về hôm qua.”

Không. Journal không phải lịch sử thao tác dài hạn dành cho người quản trị chọn mốc restore. Nó được WiredTiger quản lý theo checkpoint và nhu cầu phục hồi của chính node.

### “Chúng tôi có ba secondary nên không cần backup.”

Không. Xóa nhầm, thay đổi sai, mã độc hoặc sự cố ảnh hưởng đến mọi member vẫn có thể khiến tất cả bản sao mất dữ liệu đúng. Replication truyền cả những thay đổi hợp lệ về mặt kỹ thuật nhưng sai về nghiệp vụ.

### “Oplog window 72 giờ nghĩa là có thể restore đến bất kỳ giây nào trong 72 giờ.”

Không. Oplog tự nó thiếu bản backup nền phù hợp và quy trình replay/restore. PITR đòi hỏi một hệ thống backup hoàn chỉnh và chính sách lưu trữ tương ứng.

### “mongodump --oplog là Continuous Backup.”

Không. Tùy chọn này thu các oplog entry phát sinh **trong giai đoạn dump** để tạo trạng thái nhất quán. Muốn lưu liên tục các thay đổi sau bản dump phải có hạ tầng backup/PITR riêng.

### “Chỉ cần copy thư mục dbPath trong lúc mongod chạy là xong.”

Không bảo đảm nhất quán. Phải sử dụng phương pháp snapshot được MongoDB hỗ trợ, bảo đảm các điều kiện về journal, volume, topology, hoặc dừng ghi theo quy trình thích hợp.

### “Ghi với j:true bảo đảm không bao giờ mất.”

Không. Yêu cầu journaling làm tăng độ bền trên node liên quan. Nó không bảo vệ trước mất disk toàn bộ, lỗi vùng hạ tầng hoặc rollback do primary failover nếu ghi chưa đạt majority.

### “Một lệnh ghi trả timeout thì chắc chắn chưa được lưu.”

Không nhất thiết. Với write concern timeout, primary có thể đã chấp nhận thao tác nhưng chưa đạt điều kiện acknowledgment cần thiết. Phải kiểm tra trạng thái và thiết kế retry an toàn.

### “Checkpoint và filesystem snapshot là giống nhau.”

Không. Checkpoint là mốc nhất quán **nội bộ WiredTiger**, còn filesystem snapshot là cơ chế sao chụp ở tầng lưu trữ. Snapshot có thể tham gia một hệ thống backup nếu được lấy và lưu giữ đúng cách.

### “Atlas có backup nên mặc nhiên phục hồi được từng thời điểm.”

Không. Khả năng backup/PITR phụ thuộc loại cluster, gói và chính sách được bật. Cần xác minh **restore window**, retention, RPO/RTO và khả năng phục hồi thực tế.

---

## 12. Bài tập tình huống

### Bài tập 1 — Xác định cơ chế đúng

Với từng hiện tượng sau, chọn **journal**, **oplog**, **backup** hoặc **kết hợp** và nêu giới hạn:

| Tình huống | Hướng trả lời |
|---|---|
| Node A crash sau lần checkpoint gần nhất | Journal cùng checkpoint trên A |
| Secondary B mất kết nối 30 phút, oplog window còn 8 giờ | Oplog, nếu các operation cần thiết vẫn còn |
| Lệnh update sai làm thay đổi toàn bộ giá sản phẩm và đã replicate | Backup/PITR có mốc trước lệnh lỗi |
| Primary chết sau ghi w:1, j:true nhưng chưa replicate | Journal bền vững trên primary cũ chưa bảo đảm dữ liệu tồn tại ở primary mới |
| Cụm mất đồng thời mọi disk và journal | Backup độc lập |
| Muốn tạo bản dump nhất quán của replica set đang nhận ghi | Backup qua công cụ đúng, có thể dùng mongodump --oplog với giới hạn thích hợp |

### Bài tập 2 — Tính khoảng mất dữ liệu

Một database có:

- Snapshot mỗi ngày lúc **00:00**.
- Không thu lịch sử oplog ra backup storage.
- Một thao tác xóa nhầm xảy ra lúc **17:30** và được phát hiện lúc **17:45**.
- Replica set vẫn hoạt động bình thường, các secondary đều đã áp dụng lệnh xóa.

Hãy trả lời:

1. Có thể lấy lại document vừa xóa từ journal không? Vì sao?
2. Secondary có tự giữ trạng thái trước lệnh xóa không?
3. Nếu chỉ có snapshot 00:00, tối đa có thể mất bao nhiêu thời gian cập nhật hợp lệ khi khôi phục theo snapshot?
4. Muốn chọn mốc **17:29:59**, hệ thống cần được thiết kế thêm cơ chế gì?

**Định hướng:** Journal/oplog của hệ thống đang chạy không thay một bản backup lịch sử. Để phục hồi đến ngay trước lệnh xóa, cần PITR có base backup và đủ các thay đổi liên tục.

### Bài tập 3 — Oplog window và secondary lag

Một secondary đã offline 10 giờ. Trước đó oplog window trên nguồn là 12 giờ, nhưng trong lúc offline có đợt ghi lớn khiến window còn 7 giờ.

Hãy giải thích vì sao secondary có thể không đồng bộ tăng dần được, và đề xuất:

- Cách xem window thực tế tại thời điểm khôi phục.
- Những chỉ số cần giám sát: oplog window, replication lag, tốc độ ghi và tình trạng member.
- Hướng xử lý nếu entry còn thiếu đã bị loại bỏ khỏi nguồn đồng bộ.
- Vì sao tăng oplog size có thể hữu ích nhưng không thay thế backup.

### Bài tập 4 — Lập chính sách backup

Một hệ thống bán hàng có các ràng buộc:

- RPO tối đa **10 phút** đối với sự cố mất dữ liệu.
- RTO tối đa **2 giờ**.
- Production là replica set ba node.
- Các thao tác xóa nhầm có thể chỉ được phát hiện sau vài giờ.
- Yêu cầu giữ lịch sử khôi phục tối thiểu 14 ngày.

Hãy thiết kế một phương án đáp ứng: backup nền, thu thập thay đổi liên tục, nơi lưu, retention, restore drill, phương pháp kiểm tra thời gian khôi phục và quyền truy cập. Chỉ dùng “ba node replication” sẽ không đáp ứng được phần khôi phục về quá khứ.

---

## 13. Câu hỏi ôn tập

1. Journal thuộc tầng nào của MongoDB? Nó kết hợp với checkpoint như thế nào?
2. Tại sao journal không phải nơi tra cứu lịch sử thao tác cập nhật document?
3. Oplog nằm ở database/collection nào trong replica set?
4. Secondary sử dụng oplog ra sao khi bị tụt đồng bộ?
5. Điều gì làm oplog window ngắn lại dù oplog size không đổi?
6. Vì sao xóa nhầm một collection đã replicate không thể cứu đơn giản bằng secondary?
7. Sự khác biệt giữa **w:1, j:true** và **w:"majority", j:true** là gì?
8. **mongodump --oplog** giúp giải quyết vấn đề gì? Nó có tự tạo PITR lâu dài không?
9. Sự khác nhau giữa checkpoint nội bộ và một bản filesystem snapshot được dùng cho backup?
10. Một hệ thống được coi là đã có chiến lược backup khi chưa từng thử restore không? Vì sao?

## 14. Tổng kết

- **Journal** thuộc WiredTiger storage engine, kết hợp với checkpoint để phục hồi một node sau crash, với giới hạn về những ghi đã bền vững.
- **Oplog** là lịch sử operation gần đây của **replica set**, giúp secondary nhân bản và theo kịp các thay đổi, nhưng bị giới hạn bởi oplog window.
- **Backup** là dữ liệu được lưu **độc lập và có khả năng restore**, phục vụ khôi phục sau xóa nhầm, hỏng dữ liệu, mất disk hoặc thảm họa.
- **PITR** dùng backup nền cộng lịch sử thay đổi được thu thập và giữ riêng để khôi phục đến mốc phù hợp; oplog trên node đang chạy chưa đủ để đạt mục tiêu đó.
- **Write concern, journal, replication và backup là các lớp bảo vệ bổ sung**, mỗi lớp có phạm vi và điều kiện riêng.

Khi thiết kế MongoDB production, hãy bắt đầu bằng câu hỏi **“Cần phục hồi sau loại sự cố nào, mất tối đa bao nhiêu dữ liệu và phải khôi phục trong bao lâu?”**. Câu trả lời đó quyết định cách cấu hình journaling/write concern, replica set/oplog và chính sách backup/restore.

## Tài liệu chính thức tham khảo

- [MongoDB Manual — Journaling](https://www.mongodb.com/docs/manual/core/journaling/)
- [MongoDB Manual — WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/)
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Backup Methods for Self-Managed Deployments](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB Database Tools — mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Atlas — Continuous Cloud Backup and Point-in-Time Recovery](https://www.mongodb.com/docs/atlas/recover-pit-continuous-cloud-backup/)
- [MongoDB Manual — rs.printReplicationInfo](https://www.mongodb.com/docs/manual/reference/method/rs.printReplicationInfo/)
