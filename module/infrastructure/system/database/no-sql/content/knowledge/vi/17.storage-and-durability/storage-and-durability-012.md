# Khôi phục sau crash và giới hạn của từng chế độ độ bền trong NoSQL

## 1. Một lần ghi thành công có chắc chắn sống sót sau sự cố?

Một dịch vụ đặt hàng nhận yêu cầu thanh toán và ghi:

```json
{
  "_id": "PAY-1001",
  "orderId": "ORD-1001",
  "amountVnd": 520000,
  "status": "CONFIRMED",
  "version": 1
}
```

Database trả kết quả **ghi thành công**. Ngay sau đó, process database bị tắt đột ngột, máy chủ mất điện, hoặc node chính không còn truy cập được. Khi hệ thống hoạt động trở lại, liệu bản ghi `PAY-1001` còn tồn tại?

Không thể trả lời chỉ bằng câu “NoSQL có độ bền cao” hoặc “dữ liệu đã được ghi xuống database”. Kết quả phụ thuộc vào ít nhất bốn yếu tố:

1. **Cơ chế xác nhận ghi (acknowledgment):** database trả thành công ở thời điểm nào?
2. **Chế độ độ bền (durability mode):** dữ liệu đã nằm trong bộ nhớ, nhật ký ghi hay đã được đồng bộ tới lưu trữ bền vững?
3. **Số và vị trí bản sao:** có replica khác giữ dữ liệu không, và replica đó đã ghi bền chưa?
4. **Loại sự cố:** chỉ process chết, cả hệ điều hành sập, mất đĩa, mất node hay mất cả vùng triển khai?

Bài học tập trung vào **khôi phục sau crash** và **giới hạn của từng chế độ độ bền** trong bối cảnh lưu trữ NoSQL: từ WAL/commit log, fsync, snapshot, replication đến backup và khôi phục thảm họa. Các ví dụ minh họa trên Redis, MongoDB, Cassandra, DynamoDB, Elasticsearch/OpenSearch, Neo4j và RocksDB.

### Một tình huống mở đầu

```text
10:00:00.000  Client gửi tạo thanh toán PAY-1001
10:00:00.015  Database nhận và ghi thay đổi vào bộ nhớ
10:00:00.020  Database trả ACK thành công
10:00:00.021  Hệ điều hành mất điện
10:00:07.000  Máy khởi động lại
10:00:08.000  Ứng dụng tìm PAY-1001
```

Nếu ACK chỉ xác nhận **đã có trong bộ nhớ**, một crash có thể khiến bản ghi biến mất. Nếu ACK yêu cầu **journal/WAL đã được đồng bộ xuống thiết bị bền vững**, cơ hội khôi phục sau crash của host sẽ tốt hơn. Nếu disk của node bị mất hẳn, chỉ lưu bền trên node đó vẫn chưa đủ; phải xét replication hoặc backup.

**Điểm cốt lõi:** độ bền không phải một nhãn “có/không” tách khỏi loại lỗi. Nó là **một cam kết dưới một mô hình sự cố cụ thể**.

## 2. Phân biệt acknowledgment, visibility, durability và recoverability

Các thuật ngữ dưới đây liên quan nhưng không đồng nghĩa.

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Acknowledgment (ACK)** | Server đã trả kết quả gì cho client? | Lệnh ghi trả thành công |
| **Visibility** | Một lần đọc có thấy giá trị mới không? | Truy vấn search thấy đơn mới |
| **Durability** | Dữ liệu có sống sót qua loại crash được bảo đảm không? | Journal đã được fsync và replay |
| **Replication** | Dữ liệu có bản sao ở node/vùng khác không? | Ba replica nhận bản ghi |
| **Recoverability** | Có thể khôi phục dữ liệu/dịch vụ đến trạng thái yêu cầu không? | Restore backup + replay log |
| **Consistency** | Các bản sao và thao tác đọc/ghi quan sát trạng thái có đúng hợp đồng không? | Đọc sau ghi có thấy phiên bản mới? |
| **Atomicity** | Một thao tác/transaction có xảy ra trọn vẹn hay không? | Không thấy nửa transaction |

Ba ví dụ:

- Một record có thể **visible** qua bộ nhớ cache nhưng chưa được fsync. Một lần đọc thấy nó **không chứng minh** nó sẽ sống sau khi mất điện.
- Một record có thể đã được lưu bền ở primary nhưng chưa hiện trong search index do refresh bất đồng bộ. **Chưa tìm thấy khi search không có nghĩa record đã mất**.
- Một record có thể được sao chép sang hai replica nhưng các replica vẫn chưa đảm bảo persist theo chính sách journaling đang dùng. **Replication và persistence là hai trục độc lập**.

### ACID không nên bị diễn giải thành “miễn nhiễm mọi thảm họa”

Trong ACID, chữ **D (Durability)** mô tả tính bền của những thay đổi đã commit theo hợp đồng của hệ thống. Nó **không tự hứa** rằng dữ liệu không thể mất khi đồng thời hỏng tất cả ổ đĩa, mất cả region, bị administrator xóa nhầm hoặc có lỗi ứng dụng cập nhật sai.

Một transaction có thể atomic nhưng không có mức replication mong muốn. Một hệ eventual consistency vẫn có thể bảo vệ tính bền của từng ghi. Vì thế cần đọc **cấu hình write concern, journal, replica và recovery** thay vì chỉ dựa vào nhãn công nghệ.

## 3. Phân loại sự cố trước khi bàn đến độ bền

| Sự cố | Điều gì không còn đáng tin? | Cơ chế bảo vệ thường cần |
|---|---|---|
| **Process crash** | Bộ nhớ của process, thao tác chưa commit | WAL/transaction log, dữ liệu đã ghi, restart/replay |
| **OS/kernel crash** | Bộ nhớ và page cache của hệ điều hành có thể mất | Đồng bộ dữ liệu/log tới lưu trữ bền vững |
| **Mất điện host** | RAM, cache chưa được bảo vệ nguồn, ghi dở | fsync với storage đáng tin cậy, kiểm tra checksum/recovery |
| **Hỏng disk/node** | Lưu trữ cục bộ trên node không sử dụng được | Replica độc lập, backup/restore |
| **Primary failover** | Node tiếp nhận ghi thay đổi; bản ghi chưa nhân bản có thể bị rollback | Write concern/quorum và giao thức bầu leader phù hợp |
| **Mất Availability Zone** | Một nhóm node và hạ tầng cục bộ không sẵn sàng | Phân bố replica sang AZ khác |
| **Mất region** | Nhiều AZ/hệ liên quan trong region không sẵn sàng | Sao chép/backup sang region khác và kế hoạch DR |
| **Corruption/bug/xóa nhầm** | Dữ liệu sai có thể được nhân bản rất nhanh | Backup độc lập, PITR, audit, kiểm tra toàn vẹn |
| **Mất phản hồi ACK** | Client không biết thao tác có commit hay không | Idempotency key, truy vấn xác minh, retry an toàn |

**Không gộp “crash” thành một sự kiện duy nhất.** Ví dụ restart process có thể vẫn đọc được dữ liệu nằm trong OS page cache, nhưng reboot hoặc mất điện có thể loại bỏ page cache đó. Việc một thử nghiệm `kill` process thành công **không chứng minh** hệ an toàn trước mất điện.

### Mô hình độ bền theo cấp

```text
                     Nhiều vùng, backup độc lập
                               ▲
                               │ chống mất site/region
                   Replica ở nhiều node/AZ
                               ▲
                               │ chống mất một node/đĩa
                 fsync journal trên một node
                               ▲
                               │ chống OS crash/mất nguồn
                     Ghi log vào page cache
                               ▲
                               │ thường còn khi process chết
                     Trạng thái trong RAM process
                               ▲
                               │ dễ mất khi process chết
                          Request nhận
```

Sơ đồ là **mô hình trực giác**, không phải thứ tự chính xác của mọi write path. Một số hệ thống đồng thời ghi nhiều replica hoặc có thiết kế persistence không theo các tầng này. Càng lên cao có thể bảo vệ trước nhiều loại lỗi hơn, nhưng còn phụ thuộc giao thức replication, cách xử lý leader failover và độ tin cậy của thiết bị.

## 4. Từ bộ nhớ đến WAL: điều gì xảy ra trước ACK?

Một write path điển hình của hệ có write-ahead log (WAL) hoặc commit log:

```text
Client gửi WRITE
        |
        v
Kiểm tra điều kiện / transaction
        |
        v
Tạo bản ghi trong WAL / commit log
        |
        +------> Đồng bộ log ra thiết bị? (fsync)
        |
        +------> Gửi tới replica?       (replication)
        |
        v
Đưa trạng thái vào memtable/cache/index nội bộ
        |
        v
ACK theo policy đã cấu hình
        |
        v
Flush/compaction/checkpoint/snapshot về sau
```

**Thứ tự các bước có thể khác nhau theo engine** và phụ thuộc write concern, transaction, replication. Một số hệ có thể trả ACK trước khi fsync; một số yêu cầu log bền ở nhiều node; một số thực hiện replication song song. Không dùng sơ đồ này để suy ra bảo đảm cụ thể mà không đọc cấu hình của hệ quản trị.

### WAL bảo vệ điều gì?

**Write-Ahead Logging** lưu đủ thông tin để sau crash có thể tái hiện những thay đổi đã được chấp nhận. Về mặt ý tưởng, hệ thống cần có cơ chế bền cho phần nhật ký tương ứng trước khi tuyên bố một thao tác có độ bền mà nó đã cam kết.

Khi process restart:

```text
Đọc snapshot/checkpoint gần nhất
               |
               v
Đọc WAL/commit log còn hợp lệ
               |
               v
Replay các thao tác cần thiết
               |
               v
Khôi phục trạng thái nhất quán
               |
               v
Cho phép truy vấn/ghi theo chính sách
```

Đây là mô hình phổ biến, nhưng định dạng log, thứ tự replay, cách loại thao tác chưa commit và việc phục hồi index là chi tiết của engine.

### Checkpoint và snapshot có vai trò gì?

Nếu luôn phải replay toàn bộ log từ ngày đầu hệ thống chạy, thời gian khởi động có thể rất dài. **Checkpoint/snapshot** ghi lại một mốc trạng thái để giảm lượng log phải đọc lại. Nó giúp recovery nhanh hơn, nhưng một snapshot cũ **không chứa** các thay đổi sau thời điểm snapshot nếu log bổ sung không có hoặc đã mất.

Một hệ có thể dùng:

```text
Snapshot lúc 10:00
  + WAL từ 10:00 đến 10:05
  -> khôi phục trạng thái tới 10:05
```

Nếu WAL từ 10:03 đến 10:05 chưa được đồng bộ bền vững và biến mất, chỉ snapshot 10:00 và phần log còn tồn tại được replay. Chính sách ACK quyết định **những write nào đáng lẽ phải tồn tại** sau crash.

## 5. `write()` khác `fsync()`: hiểu ranh giới lưu trữ

Trong nhiều hệ điều hành, thao tác ghi vào file có thể đưa dữ liệu vào **page cache** rồi trả về; việc thiết bị vật lý nhận và lưu bền những byte đó diễn ra sau. Các lời gọi đồng bộ như `fsync` hoặc cơ chế tương đương nhằm yêu cầu dữ liệu và metadata liên quan được đẩy xuống tầng lưu trữ bền vững.

Ví dụ:

```text
Ứng dụng       OS page cache          Thiết bị lưu trữ
    |                |                       |
    | write(log)     |                       |
    +--------------->|                       |
    | write returns  |                       |
    |                |---- flush later ----->|
    | fsync(log)     |                       |
    +--------------->|---- sync ----------->|
    | fsync returns  |                       |
```

### Những giới hạn cần nhớ

- `write()` thành công **không luôn có nghĩa** dữ liệu đã bền trước OS crash.
- `fsync()` giúp bảo vệ theo hợp đồng của OS/file system/storage, nhưng phần cứng lỗi, firmware sai, bộ điều khiển có cache không được bảo vệ nguồn hoặc các lớp ảo hóa có thể làm giảm bảo đảm thực tế.
- Nếu transaction thay đổi nhiều file hoặc metadata, việc bảo đảm **khôi phục trạng thái nhất quán** còn phụ thuộc cách engine ghi log, checkpoint, rename, checksum và đồng bộ metadata.
- Ghi bền một file WAL trên một node **không** bảo vệ khi node/disk không thể khôi phục.
- Nếu ứng dụng gọi nhiều thao tác trên các hệ khác nhau, fsync của từng hệ không tự tạo **giao dịch nguyên tử xuyên hệ thống**.

Vì vậy, “đã flush xuống disk” cần được hiểu trong **mô hình thiết bị và lỗi** cụ thể, không phải lời hứa rằng mọi bản lưu trên toàn thế giới không thể mất.

## 6. Group commit: độ bền và hiệu năng không nhất thiết đối lập tuyệt đối

Gọi fsync cho từng ghi đơn lẻ có thể làm tăng latency và I/O. Nhiều engine dùng **group commit**: gom một nhóm thao tác để cùng đồng bộ log.

```text
WRITE A ----+
WRITE B ----+--> một đợt sync log --> ACK cho các write đủ điều kiện
WRITE C ----+
```

Điều này có thể cải thiện throughput và giảm chi phí fsync trên mỗi thao tác. Đổi lại, cách xếp lịch đồng bộ ảnh hưởng latency và độ dao động. Khi engine có chế độ **periodic sync**, hệ có thể xác nhận các thao tác trước đợt fsync tiếp theo; khi đó tồn tại một cửa sổ có nguy cơ mất write dưới một số loại crash.

**Không nên diễn giải “fsync mỗi giây” thành một cam kết toán học rằng luôn chỉ mất tối đa đúng một giây dữ liệu**. Hệ thống có thể bị trễ fsync, dồn tải, gặp lỗi thiết bị hoặc ứng dụng quan sát ACK ở thời điểm khác. Phải đo và thử chế độ cụ thể.

## 7. Replication và quorum: còn bản sao không đồng nghĩa đã commit bền

Giả sử có ba node:

```text
                    WRITE
                      |
                      v
                Primary / Leader
                   /      \
                  v        v
               Replica B  Replica C
```

Một chính sách ACK có thể yêu cầu:

- Chỉ leader xác nhận.
- Một số replica phản hồi.
- Đa số replica xác nhận.
- Các replica còn sống xác nhận theo chính sách nhất quán.

Khi primary chết, khả năng giữ write phụ thuộc:

1. **Replica nào đã nhận write trước ACK?**
2. **Nhận vào bộ nhớ hay ghi bền?**
3. **Giao thức bầu leader/failover chọn trạng thái nào làm authoritative?**
4. **Write chưa được commit theo quorum có thể bị rollback không?**
5. **Các replica có phân bố trên miền lỗi độc lập không?**

Ví dụ:

```text
T0: Leader A ghi v7, ACK một mình
T1: A chết trước khi B/C nhận v7
T2: B được bầu leader
T3: Trạng thái mới của cluster không chứa v7
```

Ở một hệ có failover và rollback phù hợp, write mà client từng thấy ACK ở chế độ yếu có thể không tồn tại sau khi chọn leader mới.

### Quorum không loại bỏ mọi rủi ro

Quorum có thể bảo vệ tốt hơn khỏi mất một node hoặc phân hoạch mạng, nhưng không tự bảo vệ:

- Cùng lúc mất đủ số node để không còn dữ liệu cần thiết.
- Corruption lan sang các bản sao.
- Xóa nhầm hoặc logic ứng dụng sai được sao chép hợp lệ.
- Trễ replication sang region khác.
- Replica trả ACK **trước khi sync xuống disk** nếu chế độ persistence cho phép.

**Quorum là quy tắc về số/nhóm bản sao tham gia quyết định; durability còn có chiều sâu là thao tác đã được lưu bền ở từng bản sao hay chưa.**

## 8. MongoDB: write concern, journal và khả năng rollback

Trong MongoDB, các điều khiển quan trọng là **write concern** và journaling. Ví dụ một replica set có primary cùng các secondary.

### 8.1. Phân biệt `w` và `j`

- `w: 1`: client yêu cầu xác nhận từ primary theo mức write concern được thiết lập. Không yêu cầu đa số replica đã xác nhận.
- `w: "majority"`: chờ thao tác đạt điều kiện xác nhận bởi đa số voting data-bearing members theo quy tắc MongoDB.
- `j: true`: yêu cầu điều kiện journaling liên quan trước khi ACK, theo write concern và cấu hình hệ.
- `wtimeout`: giới hạn thời gian đợi write concern; timeout **không có nghĩa thao tác chắc chắn đã rollback hoặc chưa diễn ra**.

Ví dụ bảng suy luận khái niệm:

| Cấu hình | Chờ điều gì trước ACK (khái quát)? | Giới hạn quan trọng |
|---|---|---|
| `{w:1}`, journaling không yêu cầu | Primary xác nhận write | Có thể mất khi crash hoặc rollback sau failover, tùy thời điểm/cấu hình |
| `{w:1,j:true}` | Primary còn phải đáp ứng yêu cầu journal | Không bảo vệ mất disk của primary hoặc rollback do write chưa đủ replication |
| `{w:"majority"}` | Đạt điều kiện majority | Bảo đảm journal còn phụ thuộc thiết lập journaling/phiên bản; không tự chống lỗi toàn cluster |
| `{w:"majority",j:true}` | Majority cùng yêu cầu journal theo hợp đồng | Mạnh hơn trong replica set thông thường, vẫn không là backup hay bảo vệ mất toàn vùng |

**Giới hạn bảng:** hành vi chính xác của majority journaling phụ thuộc phiên bản và cấu hình MongoDB (ví dụ `writeConcernMajorityJournalDefault` ở những triển khai hỗ trợ). Nên kiểm tra topology/phiên bản thực tế trước khi đưa ra cam kết RPO. Không suy luận tất cả chế độ mặc định của mọi MongoDB deployment đều giống nhau.

### 8.2. Ví dụ lệnh MongoDB có write concern rõ ràng

Trong `mongosh` trên **database thử nghiệm**:

```javascript
db.runCommand({
  insert: "payments_demo",
  documents: [
    {
      _id: "PAY-1001",
      orderId: "ORD-1001",
      amountVnd: 520000,
      status: "CONFIRMED"
    }
  ],
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 5000
  }
});
```

Trước khi sử dụng trong hệ thật, cần xác nhận replica set có đủ thành viên đáp ứng `majority` và journaling phù hợp. Không viết code “nuốt” lỗi write concern rồi coi thao tác hoàn tất chỉ vì không có exception ở tầng khác.

### 8.3. `w:1,j:true` có thể mất write khi failover?

Giả sử A là primary, B/C là secondary:

```text
A: ghi PAY-1001 vào journal, trả ACK (w:1, j:true)
B: chưa nhận PAY-1001
C: chưa nhận PAY-1001
A: mất node hoàn toàn
B: được bầu thành primary mới
```

Ngay cả khi dữ liệu đã bền trên ổ của A, cluster mới chưa chắc chứa write đó. Nếu A quay lại, dữ liệu không thuộc lịch sử được chọn có thể bị rollback. Bởi vậy **journal trên một node không thay thế write concern phù hợp với failover**.

### 8.4. Majority không đồng nghĩa đọc từ mọi replica đều thấy ngay

Đọc từ một secondary đang trễ có thể quan sát giá trị cũ, tùy read preference và read concern. Đây là vấn đề **tính mới của kết quả đọc**, khác với việc write đã đủ bền theo write concern.

Nếu UI cần *read-your-writes*, phải xác định read preference/read concern hoặc cách đồng bộ theo session phù hợp. Không được lấy việc một secondary trả dữ liệu cũ để kết luận write majority đã mất.

### 8.5. Transaction và journal

MongoDB hỗ trợ transaction nhiều document trong topology phù hợp. Atomicity của transaction và durability của commit vẫn phụ thuộc write concern, journaling và xác nhận commit.

Tình huống quan trọng:

```text
Client gửi commit transaction
Database commit thành công
Kết nối mạng mất trước khi client nhận phản hồi
Client thấy timeout
```

Client không thể suy ra transaction chắc chắn thất bại chỉ vì timeout. Một số driver có cơ chế retry commit hoặc phân loại trạng thái commit không rõ kết quả; ứng dụng cần thiết kế **idempotency** ở cấp thao tác nghiệp vụ và truy vấn xác minh, không tự chạy lại lệnh tạo thanh toán với ID mới.

### 8.6. Recovery và replica rollback

Sau crash/restart, MongoDB có thể dùng journal và cơ chế recovery để đưa dữ liệu trở lại trạng thái nhất quán. Khi failover replica set, cần quan sát **bầu primary mới, replication lag, các write chưa đạt majority và khả năng rollback**.

**Điều không được cam kết từ một phép thử đơn:** thấy bản ghi còn sau restart process không chứng minh nó sẽ tồn tại sau mất ổ đĩa, mất tất cả replica, restore backup cũ hoặc lỗi người vận hành.

## 9. Redis: RDB, AOF và bản sao không có cùng cam kết độ bền

Redis thường được dùng làm cache, session store, bộ đếm hoặc kho dữ liệu tốc độ cao. Khi dùng Redis như **nguồn dữ liệu không thể mất**, phải hiểu rõ cấu hình persistence.

### 9.1. Không có persistence

Nếu không cấu hình snapshot RDB hay AOF, dữ liệu trong bộ nhớ có thể biến mất khi Redis process/node restart. Đây có thể là lựa chọn hợp lý cho **cache có thể tái tạo**, nhưng không hợp lý làm nơi duy nhất giữ giao dịch tài chính.

### 9.2. RDB snapshot

RDB tạo các **ảnh chụp trạng thái tại một số thời điểm**. Ví dụ ý tưởng cấu hình:

```text
# Các điều kiện save kiểu cấu hình Redis phổ biến:
save 900 1
save 300 10
save 60 10000
```

Các dòng trên là ví dụ điều kiện snapshot theo số lần thay đổi trong khoảng thời gian, **không bảo đảm cứ đúng mỗi 60 giây sẽ có một snapshot**. Trong một số phiên bản, cấu hình mặc định và cơ chế thực hiện có thể khác.

Nếu crash xảy ra lúc 10:05 và snapshot gần nhất thể hiện trạng thái 10:00, những thay đổi sau đó **có nguy cơ không được khôi phục từ RDB**, nếu không còn nguồn log/bản sao khác.

RDB thuận tiện cho snapshot/restore nhưng **không tự cung cấp độ bền tới từng write vừa ACK**.

### 9.3. AOF — Append Only File

AOF ghi các thao tác thay đổi trạng thái theo một hình thức log có thể replay. Các chế độ sync thường được nêu:

| `appendfsync` | Ý tưởng | Đánh đổi |
|---|---|---|
| `always` | Đồng bộ AOF rất thường xuyên, gắn với write | Bảo vệ tốt hơn trước host crash, latency/throughput tốn hơn |
| `everysec` | Thường đồng bộ theo chu kỳ khoảng một giây | Cân bằng phổ biến; có cửa sổ write đã ACK nhưng chưa sync |
| `no` | Để OS quyết định thời điểm flush theo cơ chế của nó | Chi phí thấp hơn nhưng nguy cơ mất nhiều dữ liệu hơn khi crash |

Ví dụ cấu hình:

```text
appendonly yes
appendfsync everysec
```

**Không hiểu “everysec” thành bảo đảm tuyệt đối mất tối đa một giây** trong mọi loại crash. Độ trễ fsync, tải hệ thống, lỗi I/O, trạng thái rewrite và tầng phần cứng có thể làm hành vi phức tạp hơn.

### 9.4. AOF rewrite và dữ liệu lúc crash

Để AOF không tăng vô hạn, Redis có cơ chế viết lại log dựa trên trạng thái hiện tại. Các phiên bản mới có thể quản lý AOF bằng nhiều thành phần và metadata/manifest. Nếu crash đúng lúc rewrite, engine cần xử lý các file hợp lệ và metadata để restart.

Người vận hành không nên tự ý xóa các file AOF “có vẻ cũ” hoặc ghép log thủ công khi chưa hiểu **định dạng và quy trình recovery đúng phiên bản**. Một file rewrite nhỏ hơn không có nghĩa những write vừa ACK chắc chắn đã được bảo vệ hơn.

### 9.5. Replication của Redis và `WAIT`

Redis replication thông thường có tính **bất đồng bộ**. Một primary có thể ACK rồi gặp sự cố trước khi các replica nhận write.

Lệnh:

```redis
WAIT 1 1000
```

yêu cầu đợi tới khi ít nhất một replica xác nhận đã xử lý phần write trước đó từ kết nối client trong khoảng thời gian tối đa minh họa 1.000 ms. Kết quả trả về là số replica xác nhận; ứng dụng phải **kiểm tra kết quả thực tế**, không coi việc gọi `WAIT` là thành công vô điều kiện.

**Giới hạn rất quan trọng:** `WAIT` **không đồng nghĩa** write đã được fsync bền trên replica và cũng không biến Redis thành hệ có strong-consistency/quorum transaction. Failover vẫn có chính sách lựa chọn replica, trạng thái chưa nhận và rủi ro mất dữ liệu. Một số phiên bản có thêm các cơ chế chờ AOF/persistence chuyên biệt; phải đọc hợp đồng của phiên bản đang vận hành thay vì suy ra từ `WAIT`.

### 9.6. Redis có thể mất dữ liệu ngay cả khi app đã thấy thành công

Các tình huống điển hình:

- RDB snapshot chưa chạy từ lần ghi gần nhất.
- AOF `everysec` chưa sync batch cuối.
- AOF `no` phụ thuộc flush của OS.
- Primary ACK nhưng replica chưa bắt kịp trước failover.
- Disk hỏng dù AOF đã được sync cục bộ.
- Key bị eviction hoặc hết TTL dù không có crash: **đây là chính sách lưu trữ, không phải mất dữ liệu do crash**.

Nếu Redis chỉ là cache, sau restart có thể **rebuild từ source of truth**. Nếu Redis là nguồn dữ liệu độc quyền, cần phân tích RPO, persistence, replica, backup và cách khôi phục một cách nghiêm túc.

## 10. Cassandra và ScyllaDB: commit log, memtable và consistency level

Cassandra và nhiều hệ wide-column dùng kiến trúc gần LSM:

```text
WRITE đến replica
      |
      +--> commit log
      |
      +--> memtable trong RAM
                 |
                 v
              flush
                 |
                 v
              SSTable
                 |
                 v
             compaction
```

**Memtable trong RAM không phải lớp duy nhất bảo vệ dữ liệu.** Commit log giúp recovery các write chưa được flush sang SSTable. Khi restart sau crash, engine có thể replay commit log để dựng lại trạng thái cần thiết.

### 10.1. `durable_writes` và commit log

Trong Cassandra, keyspace có thuộc tính liên quan đến `durable_writes`. Ví dụ **cấu hình học tập**:

```sql
CREATE KEYSPACE shop_demo
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;
```

`dc1` chỉ là tên datacenter minh họa; muốn thực thi phải dùng tên DC thật và topology phù hợp. Khi `durable_writes` được tắt ở nơi hỗ trợ, ghi có thể không sử dụng commit log theo cách thông thường; điều đó **làm thay đổi đáng kể khả năng recovery sau crash**. Không tắt chỉ để giảm độ trễ nếu dữ liệu không thể tái tạo.

### 10.2. `commitlog_sync`: batch và periodic

Hai chế độ thường được nhắc tới:

- **`batch`:** chờ đồng bộ commit log trước khi ACK write ở replica theo cơ chế của engine, giảm cửa sổ mất dữ liệu do crash của replica nhưng có thể tăng latency.
- **`periodic`:** đồng bộ log theo khoảng cấu hình, cho phép ACK trước khi dữ liệu của batch đó được fsync; có **cửa sổ rủi ro mất write** khi OS/power crash.

Tên setting và các tham số liên quan có thể khác giữa phiên bản Cassandra/ScyllaDB; hãy xem cấu hình thực tế của cluster thay vì sao chép máy móc.

### 10.3. Consistency level không đồng nghĩa độ bền trên disk

CQL hỗ trợ những consistency level như `ONE`, `QUORUM`, `LOCAL_QUORUM`, `ALL`, với ý nghĩa số và phạm vi replica cần trả kết quả theo RF/topology. Chọn level phù hợp giúp quản lý **số replica tham gia ACK**, nhưng không tự thay đổi chế độ fsync của từng replica.

Ví dụ:

```text
RF = 3 replica trong một datacenter
CL = QUORUM -> cần phản hồi từ đa số replica theo quy tắc
commitlog_sync = periodic -> các replica có thể ACK trước sync log
```

Vì vậy, **QUORUM không tự mang nghĩa “ít nhất hai bản sao đã fsync đến đĩa”**. Muốn đánh giá durability, phải xét cả **consistency level, cấu hình commit log, độ an toàn disk và cơ chế repair**.

### 10.4. Hinted handoff và repair

Nếu một replica tạm thời không nhận write, hệ có thể có cơ chế lưu hint hoặc repair để giúp đồng bộ về sau. Tuy nhiên:

- Hint không phải backup đầy đủ.
- Hint có giới hạn retention/cấu hình và có thể không thay thế anti-entropy repair.
- Một số loại mất dữ liệu cần phục hồi từ replica khác hoặc backup.
- Nếu nhiều replica cùng mất write đã ACK trước fsync, việc repair giữa các replica không tự tái tạo một write không còn tồn tại ở đâu.

Không xem “cluster có ba node” là điều kiện đủ để không mất bất kỳ thay đổi nào.

### 10.5. Batch CQL không phải transaction ACID tổng quát

Cassandra có `BEGIN BATCH ... APPLY BATCH`, nhưng **CQL batch không tương đương một transaction quan hệ tổng quát** với isolation và rollback tùy ý giữa nhiều partition/service. Batch có semantics riêng; dùng batch rộng có thể gây tải lớn.

Không nên chọn batch chỉ vì mong “mọi thao tác sẽ bền sau mọi crash”. Cần xác định invariant nghiệp vụ, partition và consistency level; dùng cơ chế điều phối phù hợp khi có nhiều thực thể liên quan.

### 10.6. Tombstone, SSTable và recovery

Sau delete/TTL, tombstone có thể phải tồn tại cho tới khi compaction và điều kiện garbage collection cho phép purge. Nếu dọn tombstone quá sớm trong môi trường có replica chưa bắt kịp, dữ liệu cũ có thể tái xuất hiện.

**Crash recovery** và **compaction/garbage collection** là hai hoạt động liên quan nhưng khác nhau: replay log đảm bảo trạng thái sau sự cố; compaction tối ưu cấu trúc lưu, xử lý bản cũ/tombstone. Không dùng việc SSTable chưa giảm kích thước để kết luận crash recovery thất bại.

## 11. DynamoDB: dịch vụ quản lý độ bền, nhưng ứng dụng vẫn cần RPO/DR

DynamoDB là dịch vụ NoSQL được quản lý, có replication và cơ chế bền dữ liệu trong phạm vi region theo hợp đồng dịch vụ. Người dùng không trực tiếp chọn `fsync` như một hệ tự quản lý.

### 11.1. Khi `PutItem` trả thành công

Một yêu cầu `PutItem` đã được dịch vụ xác nhận thành công có mức durability theo bảo đảm của DynamoDB tại region đang dùng. Ứng dụng không phải tự đọc WAL hay bật AOF.

Tuy nhiên, **ACK thành công không giải quyết**:

- Client bị timeout và không biết đã commit hay chưa.
- Ứng dụng ghi trùng do retry.
- Một yêu cầu update sai được chấp nhận và nhân bản hợp lệ.
- Xóa nhầm nhiều item.
- Query qua GSI chưa thấy cập nhật mới vì GSI có độ trễ nhất quán.
- Sao chép sang region khác chưa hoàn tất ở cấu hình global tables.
- Cần khôi phục trạng thái của cả bảng về thời điểm trước sự cố logic.

### 11.2. Đọc strong và eventual không phải một chế độ durability

DynamoDB hỗ trợ những lựa chọn nhất quán đọc khác nhau trên các đường đọc được hỗ trợ. Strongly consistent read giúp giảm nguy cơ đọc giá trị cũ trong phạm vi tính năng cho phép; GSI có đặc điểm eventual consistency.

Nhưng:

> Một lần đọc không thấy record vừa ghi qua GSI không phải bằng chứng write đã biến mất sau crash.

Đó có thể là **độ trễ cập nhật chỉ mục**. Phải phân biệt write durability của base table với visibility trên index/bản sao.

### 11.3. Global tables và replication liên vùng

Nếu dùng global tables, dữ liệu được sao chép giữa các region theo cơ chế của dịch vụ, với đặc tính replication/conflict resolution phụ thuộc phiên bản/kiểu triển khai. ACK ở một region **không nên bị hiểu** là mọi region khác đã ngay lập tức nhìn thấy cùng bản ghi.

Khi thiết kế RPO cho mất region, phải đo replication lag, xác định hành vi failover và cách giải quyết conflict. Không đơn giản gọi sao chép nhiều region là “RPO = 0” cho mọi lỗi.

### 11.4. Backup và Point-in-Time Recovery

DynamoDB cung cấp cơ chế backup và **Point-in-Time Recovery (PITR)** trong các cấu hình được hỗ trợ. PITR phục vụ phục hồi table đến thời điểm trong cửa sổ giữ lại khi được bật; phạm vi và thời gian lưu cụ thể phụ thuộc cấu hình/tính năng hiện hành.

Đây là lớp khác với replication:

- **Replication** giúp dịch vụ tiếp tục hoạt động khi một số node không sẵn sàng.
- **Backup/PITR** giúp phục hồi trạng thái cũ sau lỗi logic, xóa nhầm hoặc cần khôi phục từ một mốc.

Khôi phục về thời điểm cũ có thể làm mất những giao dịch hợp lệ sau mốc đó nếu không có quy trình replay/đối soát. PITR không tự định nghĩa cách nhập lại thay đổi đã diễn ra sau điểm restore.

### 11.5. Điều kiện ghi và idempotency

Một yêu cầu tạo giao dịch có thể dùng ID ổn định và điều kiện không tồn tại:

```text
PutItem:
  Key = PAYMENT#PAY-1001
  ConditionExpression = attribute_not_exists(pk)
```

Đây là **pseudocode về ý tưởng**, không phải toàn bộ request SDK. Nếu client gửi lại sau timeout, điều kiện giúp chặn tạo cùng item hai lần. Với giao dịch nhiều item, sử dụng transaction API phù hợp, token/idempotency và kiểm tra điều kiện theo nghiệp vụ.

Không gọi “đúng một lần” chỉ vì transport retry bị hạn chế: **tác động nghiệp vụ phải có khóa chống trùng tại nguồn có thẩm quyền**.

## 12. Elasticsearch/OpenSearch: refresh, translog và flush là ba việc khác nhau

Trong Elasticsearch/OpenSearch, dữ liệu search được lưu trong các shard, dựa trên cấu trúc Lucene và transaction log (*translog*).

Một request index có thể nhận ACK nhưng document chưa xuất hiện ngay trong kết quả `_search` vì search thường có cơ chế **near-real-time refresh**.

### 12.1. Ba mốc dễ nhầm

| Mốc | Mục đích | Không chứng minh điều gì? |
|---|---|---|
| **Index request ACK** | Thao tác được chấp nhận theo chính sách ghi | Không mặc định nói search đã refresh hoặc toàn bộ replica đã persist như nhau |
| **Refresh** | Mở khả năng tìm kiếm những thay đổi gần đây | Không phải một thao tác backup hay commit bền thay cho translog |
| **Flush/Lucene commit** | Tạo điểm commit/giảm nhu cầu replay translog theo cơ chế engine | Không thay thế replica/backup/DR |

### 12.2. Chế độ durability của translog

Elasticsearch có các thiết lập như:

```json
{
  "index": {
    "translog.durability": "request"
  }
}
```

Đoạn trên là phần cấu hình minh họa, **không phải HTTP request hoàn chỉnh**. Với chế độ `request`, việc đồng bộ translog gắn gần với ranh giới ACK của request. Chế độ `async` cho phép đồng bộ theo chu kỳ, tạo cửa sổ mất write khi crash theo hợp đồng của engine.

Các tham số như `index.translog.sync_interval` và chi tiết replication/ack phụ thuộc phiên bản Elasticsearch/OpenSearch. Cần kiểm tra hiệu lực setting và semantics thực tế trước khi thay đổi production.

### 12.3. `refresh=wait_for` không có nghĩa “fsync”

Một client có thể gửi index request với tùy chọn refresh để chờ document được tìm thấy qua search. Việc này **giải quyết visibility**, không phải thay thế chính sách translog fsync.

```text
Index ACK ------> durable theo translog/replica policy
         \
          \----> refresh sau đó --> _search thấy document
```

Trong kiến trúc có MongoDB/DynamoDB làm source và Elasticsearch làm read model, **độ bền của source** và **độ mới của search projection** là hai cam kết khác nhau. Mất một shard/index dẫn xuất có thể khắc phục bằng rebuild từ source nếu pipeline và dữ liệu nguồn còn đầy đủ.

### 12.4. Shard replica và chờ số shard hoạt động

Tùy chọn như `wait_for_active_shards` liên quan đến số shard copy phải sẵn sàng trước khi xử lý write theo cấu hình. **Không nên hiểu một tùy chọn về shard availability là bằng chứng mọi bản sao đã ghi fsync xong và sẽ không mất dữ liệu**. Phải xét replication, translog durability, phản hồi shard failures, số replica thực tế và backup.

## 13. Neo4j: transaction log, commit và khôi phục graph

Neo4j dùng cơ chế transaction và transaction log để bảo vệ những thay đổi đã commit trong database. Sau crash, hệ có thể dùng log/recovery để đưa graph về trạng thái giao dịch hợp lệ.

Ví dụ một thay đổi graph:

```cypher
MATCH (o:Order {orderId: 'ORD-1001'})
CREATE (p:Payment {
  paymentId: 'PAY-1001',
  amountVnd: 520000,
  status: 'CONFIRMED'
})
CREATE (p)-[:FOR_ORDER]->(o);
```

**Đây chỉ là cú pháp minh họa.** Nếu chạy nhiều lần, `CREATE` có thể tạo nút/cạnh trùng logic; production cần định danh ổn định, unique constraint, xác thực nghiệp vụ và cách ghi idempotent.

### Khôi phục graph không chỉ là khôi phục node

Khi một transaction tạo node và edge, sau recovery hệ phải tuân theo **ranh giới transaction**, tránh để graph tồn tại nửa thay đổi đã commit. Nhưng điều này không có nghĩa:

- Một transaction ở Neo4j cũng commit nguyên tử với một write ở Redis hoặc hệ thanh toán ngoài.
- Mọi replica của một cluster đều đã nhận đúng phiên bản tại mọi thời điểm.
- Mất cả cluster/đĩa không cần backup.

Với Neo4j cluster, phải đọc **quy tắc ghi và replication của phiên bản/deployment** để xác định write nào được coi là bền qua failover. Các phiên bản mới và topology khác có thể thay đổi chi tiết.

### Backup và restore transaction logs

Backup, transaction logs và khả năng khôi phục tới một điểm (nếu được hỗ trợ ở triển khai) cần được vận hành theo quy trình riêng. Phải kiểm thử restore graph với constraint, index và các hệ phụ thuộc; không đủ chỉ thấy một node `Payment` còn tồn tại mà bỏ qua cạnh `FOR_ORDER` và các bất biến liên quan.

## 14. RocksDB và hệ nhúng: WAL còn tùy `sync` ở write options

RocksDB là một storage engine key–value thường được nhúng trong hệ thống khác. Nó dùng WAL và memtable/SSTable, nhưng **ứng dụng hoặc hệ sở hữu RocksDB chọn chính sách ghi**.

Ví dụ khái niệm ở C++:

```cpp
rocksdb::WriteOptions options;
options.sync = true;
options.disableWAL = false;

rocksdb::Status result = db->Put(
    options,
    "payment:PAY-1001",
    "CONFIRMED"
);
```

Ví dụ chỉ nêu phần write options, chưa phải chương trình C++ hoàn chỉnh. `sync=true` yêu cầu đường ghi phù hợp đồng bộ WAL theo ngữ nghĩa RocksDB, với chi phí hiệu năng tương ứng. Nếu `disableWAL=true`, dữ liệu có thể chỉ nằm trong memtable trước flush, tăng rủi ro mất khi crash.

**Hạn chế của engine nhúng:** RocksDB không tự cung cấp cơ chế replication đa node/đa region cho mọi ứng dụng. Hệ thống bao quanh nó phải tự thiết kế khả năng phục hồi khi mất toàn bộ disk/node và xử lý failover, snapshot, backup.

Đây là ví dụ rõ rằng **“dùng LSM + WAL” không đủ mô tả durability** nếu không biết write options và kiến trúc cấp cao.

## 15. Bảng so sánh chế độ và cơ chế khôi phục

| Công nghệ | Cấu hình/cơ chế trọng tâm | Khôi phục sau crash chủ yếu dựa vào | Rủi ro nếu chọn chế độ yếu |
|---|---|---|---|
| MongoDB | `writeConcern w`, `j`, replica set | Journal/recovery, replication, election | Primary ACK nhưng chưa bền hoặc chưa đủ replica; rollback |
| Redis | RDB, AOF `appendfsync`, replica | Snapshot/AOF replay hoặc replica | Mất write từ sau snapshot hoặc chưa fsync; replication lag |
| Cassandra | Commit log sync, `durable_writes`, CL, RF | Commit log replay, SSTable và replica/repair | Replica ACK trước sync; mất nhiều replica hoặc log chưa bền |
| DynamoDB | Managed persistence, regional replication, PITR | Hạ tầng dịch vụ, backup/PITR khi cần | Timeout mơ hồ, lỗi logic được nhân bản, lag global tables |
| Elasticsearch/OpenSearch | Translog `request/async`, refresh, flush, replica | Translog recovery, Lucene segments, replica | Chưa sync translog; index projection mất dữ liệu chưa thể xây lại |
| Neo4j | Transaction log, commit/cluster policy | Transaction log recovery, replica/backup | Không bảo vệ cross-service, disk/cluster loss nếu thiếu backup |
| RocksDB | WAL, `WriteOptions.sync`, `disableWAL` | WAL replay, SSTable/checkpoint | Memtable chưa flush; không có replication nếu ứng dụng không tạo |

Không nên xem bảng này như một bảng xếp hạng “hệ nào bền nhất”. Mỗi công nghệ giải một nhóm bài toán khác, có tùy chọn triển khai, chi phí và mô hình sự cố riêng. Độ bền phải được **chứng minh bằng hợp đồng và kiểm thử của cấu hình thật**.

## 16. ACK không rõ kết quả: vấn đề nguy hiểm ngang mất dữ liệu

Một client gọi tạo đơn:

```text
T0 Client: POST /payments, idempotencyKey=pay-order-1001
T1 Server: ghi thanh toán và COMMIT thành công
T2 Server: chuẩn bị trả HTTP 200
T3 Kết nối mất trước khi client nhận
T4 Client: timeout, không biết đã commit hay chưa
T5 Client: retry
```

Nếu mỗi retry tạo một `paymentId` mới và ghi nợ mới, có thể xảy ra **thanh toán trùng**, dù database không mất một byte nào. Độ bền của database **không tự đảm bảo exactly-once business effect**.

### Idempotency theo khóa nghiệp vụ

Một giải pháp là giữ khóa ổn định cho cùng yêu cầu logic:

```json
{
  "idempotencyKey": "pay-order-1001",
  "orderId": "ORD-1001",
  "amountVnd": 520000
}
```

Ở nguồn có thẩm quyền, áp unique constraint hoặc conditional insert phù hợp trên khóa đó. Khi request lặp:

- Nếu chưa có record: xử lý một lần theo giao thức nghiệp vụ.
- Nếu đã có kết quả thành công tương ứng: trả lại kết quả đã lưu.
- Nếu cùng key nhưng payload khác: báo conflict, không tự dùng giá trị mới.
- Nếu trạng thái đang xử lý/commit chưa rõ: dùng quy trình xác minh hoặc tiếp tục an toàn.

Ví dụ MongoDB:

```javascript
db.payment_requests.createIndex(
  { tenantId: 1, idempotencyKey: 1 },
  { unique: true }
);
```

Index bảo vệ **không có hai document cùng cặp key**; nó không tự đảm bảo một hệ thanh toán bên ngoài không nhận hai lệnh debit nếu ứng dụng gửi trước khi ghi dấu. Khi có hệ ngoài, phải thiết kế idempotency ở cả hai phía hoặc workflow có điều phối.

### Retry không phải rollback

Một write concern timeout, transaction commit không rõ kết quả hoặc mất kết nối **không nên bị diễn giải đơn giản thành thất bại tuyệt đối**. Retry mù có thể ghi trùng; từ chối tất cả retry lại có thể bỏ mất thao tác chưa commit. Hãy xác minh từ nguồn, dùng request ID ổn định và chọn policy retry theo loại lỗi.

## 17. Ghi qua nhiều hệ: source bền không có nghĩa projection đã cập nhật

Giả sử:

```text
Payment source: MongoDB
Search index: Elasticsearch
Cache: Redis
Event broker: hàng đợi sự kiện
```

Một chuỗi dual-write:

```text
1. Commit payment vào MongoDB          OK
2. Gửi message cho search projector    ERROR
3. API process crash
```

MongoDB có thể đã bền, nhưng search/cache **chưa phản ánh** giao dịch. Đây không hẳn là mất dữ liệu nguồn; đó là **mất ý định đồng bộ** nếu không có cơ chế phát lại.

### Transactional outbox

Một thiết kế phổ biến:

```text
               Cùng transaction ở nguồn
              +-------------------------+
API request ->| 1. Ghi payment          |
              | 2. Ghi outbox event     |
              +-------------------------+
                           |
                           v
                       COMMIT
                           |
                           v
                     Outbox relay
                           |
                        Broker
                       /      \
                      v        v
                Search index   Cache invalidation
```

Khi payment và outbox được lưu **nguyên tử trong cùng transaction mà datastore hỗ trợ**, sau crash có thể tìm những event chưa phát và gửi tiếp. Consumer cần idempotency/version để xử lý event trùng hoặc sai thứ tự.

**Ranh giới:** outbox không tạo một transaction ACID xuyên MongoDB, broker, Redis và Elasticsearch. Nó giúp **khôi phục ý định cập nhật** để các projection cuối cùng hội tụ, nếu relay và consumer được vận hành đúng.

### Recovery sau crash của worker

Nếu relay đã phát event nhưng crash trước khi đánh dấu outbox là “đã gửi”, event có thể bị phát lại. Cần:

- Event ID ổn định.
- Consumer idempotent.
- Theo dõi offset/checkpoint.
- Retry có backoff và dead-letter handling.
- Đối soát read model với source.

Một hệ thống có độ bền cao ở từng database nhưng thiếu các biện pháp trên vẫn có thể tạo **dữ liệu không nhất quán kéo dài**.

## 18. Khôi phục đúng trạng thái không chỉ là “khởi động lại process”

Với một database có WAL/transaction log, quy trình recovery có thể tự động khi process restart. Nhưng trong hệ phân tán, khôi phục vận hành cần hiểu cả cluster và ứng dụng:

```text
Phát hiện sự cố
        |
        v
Phân loại: process? OS? disk? node? region? corruption?
        |
        v
Giới hạn tác động, bảo vệ log và dữ liệu còn lại
        |
        v
Chọn đường khôi phục:
  +-----+---------+------------------+
  |               |                  |
Restart/replay   Replica failover   Backup/PITR restore
  |               |                  |
  +---------------+------------------+
                  |
                  v
        Kiểm chứng dữ liệu nguồn
                  |
                  v
        Khôi phục event/projection
                  |
                  v
       Đối soát invariant và mở traffic
```

### 18.1. Bước 1 — Xác nhận phạm vi lỗi

Thu thập:

- Client thấy error hay timeout?
- Database có ACK write nào trước crash?
- Node process chết hay mất cả storage?
- Replica nào còn, election đã ổn định chưa?
- Log/journal có lỗi checksum hay corruption?
- Có thay đổi cấu hình hoặc deployment ngay trước sự cố?

Không vội xóa file WAL/commit log “cho database chạy được”. Đó có thể là dữ liệu duy nhất để phục hồi các write chưa được snapshot.

### 18.2. Bước 2 — Bảo vệ dữ liệu còn lại

Khi nghi ngờ corruption hoặc mất một phần replica, tránh thao tác có thể ghi đè chứng cứ. Tùy hệ có thể cần ngừng ghi, cô lập node hoặc tạo bản sao hiện trạng để điều tra.

**Không tự ý ép một replica cũ thành leader** mà không hiểu giao thức bầu leader/quorum: hành động này có thể làm mất những write đã được commit trên replica khác.

### 18.3. Bước 3 — Chọn nguồn khôi phục phù hợp

- **Restart/replay log:** khi storage còn nguyên, journal/log hợp lệ.
- **Replica failover:** khi một node mất nhưng cluster còn các bản sao đáp ứng hợp đồng.
- **Restore backup/PITR:** khi nhiều bản sao không còn, dữ liệu hỏng/xóa nhầm hoặc cần quay về thời điểm trước lỗi logic.
- **Rebuild projection:** khi search/cache/index dẫn xuất bị mất nhưng source of truth còn đủ.

Điểm khó là quyết định **trạng thái nào có thẩm quyền**: bản lưu mới nhất theo đồng hồ chưa chắc là bản đã commit hợp lệ theo protocol.

### 18.4. Bước 4 — Đối soát sau phục hồi

Kiểm tra theo phạm vi nghiệp vụ:

- Những write ACK chắc chắn trước crash có còn?
- Các request timeout/không rõ kết quả được phân loại thế nào?
- Có trùng payment/order do retry không?
- Version/sequence của dữ liệu nguồn có nhất quán?
- Outbox/CDC đã bắt kịp chưa?
- Search index, cache và aggregate có còn bản cũ?
- Có record mồ côi hoặc invariant tài chính bị vi phạm không?

Một recovery “database đã mở cổng TCP” không đồng nghĩa ứng dụng đã an toàn để tiếp nhận mọi loại ghi.

### 18.5. Bước 5 — Ghi nhận kết quả

Đo thời gian gián đoạn, mốc dữ liệu cuối cùng đã phục hồi, dữ liệu nghi vấn, nguyên nhân gốc và việc cần làm để giảm rủi ro lần sau. Không tuyên bố **RPO=0** nếu chưa chứng minh toàn bộ write thuộc phạm vi cam kết vẫn còn.

## 19. RPO và RTO: biến “độ bền” thành yêu cầu vận hành

Hai mục tiêu thường dùng trong khôi phục thảm họa:

- **RPO (Recovery Point Objective):** mức mất dữ liệu theo thời gian tối đa **mà tổ chức chấp nhận được**.
- **RTO (Recovery Time Objective):** khoảng thời gian tối đa mục tiêu để khôi phục dịch vụ sau gián đoạn.

Ví dụ minh họa:

```text
Mốc dữ liệu khôi phục:  10:00
Thời điểm thảm họa:    10:05
Hệ thống phục vụ lại:  10:30

Mất dữ liệu theo mốc: 5 phút
Thời gian phục hồi:   25 phút
```

Trong ví dụ, **độ mất dữ liệu thực tế** là 5 phút và **thời gian phục hồi thực tế** là 25 phút theo cách đo. **RPO/RTO mục tiêu** phải được định nghĩa từ trước; không suy từ kết quả sự cố rồi gọi chúng là objective.

### RPO=0 khó hơn nghe có vẻ

Muốn đặt mục tiêu không mất các write đã xác nhận, cần:

1. Định nghĩa **write nào được coi là đã xác nhận** (ACK nào, ở mức concern/replication nào).
2. Định nghĩa **lỗi nào nằm trong phạm vi** (một node, một AZ hay cả region).
3. Bảo đảm giao thức ghi bền trên số miền lỗi phù hợp trước ACK.
4. Xử lý ambiguity khi client timeout.
5. Thường xuyên thử failover/recovery và xác minh write ACK có còn.

RPO=0 cho hỏng một node **không tự thành RPO=0 cho mất toàn region** nếu replication liên vùng bất đồng bộ.

### Ví dụ phân nhóm theo nghiệp vụ

| Loại dữ liệu | Đề xuất yêu cầu trước khi chọn công nghệ | Lý do |
|---|---|---|
| Cache trang sản phẩm có thể tái tạo | Có thể chấp nhận mất cache và rebuild | Source tồn tại ở hệ khác |
| Thống kê lượt xem gần đây | Có thể chấp nhận một mức trễ/mất theo quyết định sản phẩm | Không phải giao dịch tài chính |
| Đơn đã xác nhận | Cần bảo toàn các write được ACK theo phạm vi lỗi đã định | Ảnh hưởng tiền và fulfillment |
| Idempotency ledger của thanh toán | Cần bền tương xứng với giao dịch | Mất ledger có thể dẫn tới xử lý trùng |
| Nhật ký audit bắt buộc | Có chính sách retention, backup và khôi phục | Cần chứng cứ và truy vết |
| Search projection | Có thể rebuild từ nguồn đáng tin cậy | Dữ liệu dẫn xuất |

Đây là **định hướng thiết kế**, không phải SLA mặc định cho tất cả ứng dụng.

## 20. Replication không phải backup, backup không phải failover

Hai cơ chế giải quyết những loại lỗi khác nhau:

| Cơ chế | Bảo vệ tốt trước | Giới hạn |
|---|---|---|
| Replica cùng cluster | Hỏng một số node, hỗ trợ availability | Xóa nhầm/corruption có thể nhân bản; không tự phục hồi mốc cũ |
| Replica ở AZ khác | Mất một AZ theo topology phù hợp | Không tự bảo vệ mất region |
| Sao chép liên vùng | Mất region, tùy lag và failover | Có thể bất đồng bộ và conflict |
| Snapshot định kỳ | Khôi phục một bản trạng thái cũ | Có thể mất thay đổi sau snapshot |
| Backup + log/PITR | Phục hồi đến điểm trong khoảng được lưu | Phụ thuộc retention/log chain và restore procedure |
| Offline/immutable backup | Giảm rủi ro xóa nhầm hoặc tấn công cùng hệ | RTO có thể dài; vẫn cần thử restore |

### Khôi phục backup cần kiểm tra bản sao phụ thuộc

Ví dụ phục hồi MongoDB về lúc 10:00 nhưng Redis cache và Elasticsearch index vẫn phản ánh trạng thái lúc 10:05. Nếu ứng dụng đọc dữ liệu từ nhiều nơi, có thể hiển thị một trạng thái **chưa từng tồn tại đồng thời**.

Sau restore nên:

- Xác định nguồn có thẩm quyền theo mốc restore.
- Invalidate/rebuild cache và read model khi cần.
- Replay những sự kiện được phép giữ hoặc tạo các bản điều chỉnh có kiểm soát.
- Không vô ý phát lại giao dịch tài chính mà hệ ngoài đã xử lý.
- Đối soát payment provider, inventory, order và event log.

**Restore là khởi điểm của recovery nghiệp vụ, không phải bước cuối cùng.**

### Backup tồn tại chưa đủ để gọi là recoverable

Một file backup chưa từng được restore thử có thể thiếu quyền, metadata, khóa mã hóa, log segment hoặc version phần mềm cần thiết. Recovery drill phải kiểm tra **đọc được dữ liệu, tái tạo index/constraint, kiểm tra ứng dụng và đo RTO**.

## 21. Kịch bản crash test: đo điều gì và kiểm chứng ra sao?

Muốn xác nhận hợp đồng độ bền, nên thử trên môi trường **cô lập, có dữ liệu giả và có thể phá hủy**. Không dùng dữ liệu thật và không chạy thí nghiệm làm mất điện/kill process trên production.

### 21.1. Thử process crash

Quy trình mức cao:

1. Tạo một tập write có **ID duy nhất, có thứ tự**.
2. Ghi log bên ngoài database về thời điểm nhận ACK và mã ID.
3. Dừng process database đột ngột trong môi trường test.
4. Khởi động lại theo runbook của engine.
5. Truy vấn toàn bộ những ID đã nhận ACK.
6. Ghi nhận ID nào còn, bị thiếu, duplicate hoặc ở trạng thái không nhất quán.

**Giới hạn thử nghiệm:** process crash không tự mô phỏng mất OS page cache, lỗi disk hoặc mất cả node. Nếu dữ liệu còn sau thử nghiệm này, chưa thể kết luận chế độ fsync là đủ an toàn trước mất điện.

### 21.2. Thử OS/power loss

Chỉ thực hiện trên hạ tầng lab được chuẩn bị và cho phép, với phương thức fault injection phù hợp. Không đề xuất thao tác tắt nguồn thật một host đang phục vụ người dùng.

Mục tiêu là kiểm tra **cửa sổ write đã ACK nhưng chưa bền** cho từng chế độ persistence, sau đó đối chiếu với giả định RPO.

### 21.3. Thử node loss và failover

Trong replica set/cluster lab:

- Ghi với mức ACK đã chỉ định.
- Làm mất quyền truy cập primary trước khi secondary bắt kịp ở các mốc khác nhau.
- Quan sát leader election/failover và rollback khi phù hợp.
- Kiểm tra những ID nào đã ACK với `w:1` hoặc `majority` còn tồn tại.
- Ghi lại thời gian dịch vụ phục hồi và consistency của các bản sao.

Không thay đổi số node, quorum hoặc loại bỏ replica trong production chỉ để xem điều gì xảy ra.

### 21.4. Thử timeout sau commit

Đây là một test nghiệp vụ quan trọng:

```text
Client gửi request payment với idempotencyKey=K1
Server commit thành công nhưng response bị mất
Client retry cùng K1

Kỳ vọng:
  Một payment logic duy nhất
  Không có debit thứ hai
  Response hoặc trạng thái truy vấn cho biết kết quả trước đó
```

Nếu retry tạo bản ghi/hiệu ứng thứ hai, hệ có lỗi mặc dù WAL và replica hoạt động hoàn hảo.

### 21.5. Thử restore backup

Tạo backup, đưa vào một môi trường phục hồi độc lập, chạy restore, kiểm tra version dữ liệu và các invariant quan trọng. Nếu dùng PITR, thử khôi phục trước/sau một thao tác xóa nhầm giả lập và xác định chính xác thay đổi hợp lệ sau mốc phục hồi được xử lý ra sao.

## 22. Đọc số liệu vận hành để phát hiện rủi ro độ bền

Không đủ xem latency của API. Cần giám sát những tín hiệu liên quan đến lớp lưu bền và khôi phục:

| Nhóm metric | Tín hiệu cần quan tâm | Vấn đề có thể chỉ ra |
|---|---|---|
| **Write ACK** | p95/p99 write latency, lỗi write concern, timeout | Không đạt SLA hoặc xác nhận không rõ kết quả |
| **Journal/WAL** | fsync latency, lỗi sync, backlog/unsynced data | Nguy cơ cửa sổ chưa bền hoặc nghẽn I/O |
| **Replication** | Replica lag, health/quorum, failover/rollback events | Bản sao chưa đủ mới, nguy cơ mất write yếu |
| **Storage** | Disk I/O, độ bền thiết bị, checksum/corruption, disk full | Không thể persist/khởi động lại an toàn |
| **Redis** | `INFO persistence`, trạng thái AOF/RDB, replication lag | Snapshot/log lỗi hoặc rewrite backlog |
| **MongoDB** | Write concern failures, replication status, journal và operation metrics | Majority hoặc journal không đạt kỳ vọng |
| **Cassandra** | Commit log, pending compaction, dropped mutations, replica availability | Đường ghi/recovery bị nghẽn |
| **DynamoDB** | Write errors/throttling, replication lag liên vùng, backup/PITR status | Request retry hoặc DR có lỗ hổng |
| **Elasticsearch** | Translog trạng thái, shard failures, refresh/indexing lag | Search và durability/indexing khác nhau |
| **Backup** | Backup age, restore-test age, PITR coverage | Không đủ điều kiện RPO/RTO |
| **Ứng dụng** | Idempotency conflicts, outbox backlog, consumer lag | Lỗi cross-system dù source còn nguyên |

Các metric/endpoint chính xác phụ thuộc phiên bản và dịch vụ. **Đừng xây alert chỉ dựa trên sự tồn tại của tên metric**: cần biết nó đo cái gì, có bị reset khi restart không và biểu diễn theo node, shard hay toàn cluster.

### Số liệu “đã ACK nhưng mất” cần đo độc lập

Khi chạy crash test, phải có một ledger độc lập ghi:

```text
writeId, requestId, ackedAt, ackMode, server/cluster, result
```

Sau recovery, so tập ID đã ACK với tập ID còn tồn tại trong nguồn. Nếu ledger chỉ được lưu trong **chính database đang thử crash**, nó cũng có thể mất và làm lệch kết luận.

Không chứa dữ liệu thanh toán nhạy cảm hoặc thông tin bí mật trong log thử nghiệm; dùng ID giả và môi trường cô lập.

## 23. Những đánh đổi khi tăng độ bền

### Tăng fsync

Ưu điểm: giảm khoảng thời gian write được ACK nhưng chưa bền trên đĩa, trong phạm vi hợp đồng storage.

Chi phí: tăng latency write và I/O; có thể bị ảnh hưởng bởi group commit và thiết bị chậm.

### Tăng số replica/phạm vi quorum

Ưu điểm: tăng khả năng tồn tại khi một số node lỗi, hỗ trợ failover và availability theo topology.

Chi phí: traffic mạng, latency ACK, chi phí hạ tầng, khả năng tạm thời không ghi được khi mất quorum.

### Sao chép liên vùng

Ưu điểm: giảm phụ thuộc một region.

Chi phí: độ trễ mạng, replication lag và conflict; có thể phải chọn giữa latency/availability và RPO mục tiêu.

### Snapshot/PITR nhiều hơn

Ưu điểm: phục hồi tốt hơn khỏi xóa nhầm hoặc corruption logic.

Chi phí: lưu trữ, truyền dữ liệu, độ phức tạp restore và kiểm soát backup encryption/retention.

### Tăng độ bền nhưng vẫn sai nghiệp vụ

Nếu ứng dụng lưu sai giá hoặc ghi trùng thanh toán, hệ thống có thể **bảo vệ rất bền chính dữ liệu sai đó**. Độ bền giúp giữ thay đổi đã commit; nó **không chứng minh các thay đổi là hợp lệ**. Cần kết hợp validation, transaction, idempotency, audit, reconciliation và backup.

## 24. Những ngộ nhận thường gặp

| Ngộ nhận | Sự thật cần nhớ |
|---|---|
| “Database trả HTTP 200 tức là đã fsync” | ACK phụ thuộc write concern/persistence mode |
| “Process restart không mất dữ liệu tức là chống mất điện” | OS page cache có thể còn khi chỉ process chết |
| “Có WAL là không thể mất write” | Cần xét WAL đã được đồng bộ chưa, còn disk không và log có hợp lệ không |
| “Có ba replica thì chắc chắn dữ liệu bền” | Cần xem ACK ở replica nào, sync và failover |
| “Write concern `w:1,j:true` bảo vệ mọi failover” | Primary journal có thể còn nhưng write chưa được nhân bản đủ |
| “Majority nghĩa là mọi replica đã cập nhật” | Không phải mọi replica, đọc từ replica trễ có thể còn cũ |
| “Redis `WAIT` tạo transaction bền trên replica” | Chờ replica ACK không đồng nghĩa fsync/quorum durable |
| “Redis AOF everysec mất tối đa đúng 1 giây trong mọi lỗi” | Đó không phải SLA tuyệt đối dưới mọi tình huống |
| “Cassandra CL QUORUM nghĩa là fsync ở quorum” | Consistency level và commitlog sync là hai trục khác nhau |
| “DynamoDB có replica nên không cần backup” | Xóa nhầm và lỗi logic có thể được nhân bản |
| “Search không thấy document tức là write đã mất” | Có thể chưa refresh/index đồng bộ |
| “Elasticsearch refresh là flush bền xuống disk” | Visibility và durability là hai cơ chế khác |
| “Neo4j PROFILE chỉ giải thích plan mà không ghi” | PROFILE thực thi query; lệnh ghi có tác động thật |
| “Transaction của MongoDB đảm bảo cả thao tác Redis cùng commit” | Transaction chỉ có phạm vi hệ hỗ trợ |
| “Retry sau timeout luôn an toàn” | Commit có thể đã xảy ra; cần idempotency |
| “Replica là backup” | Replica có thể nhân bản xóa/corruption |
| “Có backup nghĩa là RTO ngắn” | Chỉ restore thử mới biết khôi phục mất bao lâu |
| “Data tồn tại sau recovery thì toàn bộ nghiệp vụ đúng” | Còn phải kiểm tra cross-system, thứ tự event và invariant |

## 25. Bài tập thực hành

### Bài 1 — Phân biệt loại crash

Một hệ dùng WAL nhưng ACK trước fsync. Hãy so sánh khả năng giữ write khi:

1. Chỉ process database bị kill, OS vẫn chạy.
2. OS kernel crash, page cache mất.
3. Disk trên node mất hẳn.
4. Primary bị cô lập rồi cluster bầu leader mới.

Tại sao một kết quả thành công của thử nghiệm (1) không đủ để cam kết cho (2)–(4)?

### Bài 2 — MongoDB write concern

Một MongoDB replica set có ba data-bearing members. Client chọn `w:1,j:true`. Primary ghi journal và ACK, nhưng secondary chưa nhận write; primary mất ổ đĩa.

Write có chắc chắn còn trong cluster sau failover không? Nếu thay bằng `w:"majority",j:true`, những điều kiện nào được bảo vệ tốt hơn và những loại lỗi nào vẫn còn rủi ro?

### Bài 3 — Redis snapshot và AOF

Redis RDB snapshot gần nhất lúc 10:00. Hệ ghi nhiều session từ 10:00 tới 10:05 rồi mất điện. So sánh:

- Chỉ dùng RDB.
- AOF với `appendfsync everysec`.
- AOF với `appendfsync always`.

Nêu xu hướng về RPO và chi phí hiệu năng; giải thích vì sao không thể tuyên bố một giới hạn mất dữ liệu tuyệt đối chỉ từ tên chế độ.

### Bài 4 — Cassandra consistency và commit log

RF=3, write ở `QUORUM`, các replica cấu hình `commitlog_sync: periodic`. Có thể kết luận hai replica đã fsync xuống disk khi ACK trả về không? Điều gì xảy ra nếu cùng lúc mất điện trên cả hai replica vừa ACK trước kỳ sync?

### Bài 5 — DynamoDB timeout

Client gọi `PutItem` với khóa thanh toán, request timeout. Sau đó client gửi lại bằng một ID mới và phát sinh hai đơn. Thiết kế idempotency key và conditional write để sửa lỗi. Vì sao đây không phải vấn đề “DynamoDB làm mất dữ liệu”?

### Bài 6 — Elasticsearch refresh

Một document đã được index thành công nhưng `_search` chưa thấy. Phân biệt:

- ACK write.
- Translog durability.
- Refresh.
- Flush.

Nếu thao tác `GET` theo ID có kết quả còn `_search` chưa thấy, vì sao không nên kết luận dữ liệu bị mất?

### Bài 7 — Đọc RPO/RTO từ sự cố

Backup gần nhất có thể restore tới 14:00, region lỗi lúc 14:08, dịch vụ chạy lại lúc 14:40. Tính **mất dữ liệu thực tế theo mốc** và **thời gian phục hồi thực tế**. Sau đó nêu vì sao chúng không tự trở thành RPO/RTO mục tiêu, và cần gì để bảo đảm mất dữ liệu thấp hơn.

### Bài 8 — Kiểm thử crash có ledger độc lập

Thiết kế thử nghiệm viết 10.000 bản ghi có ID duy nhất, log ACK ở nơi độc lập, gây process crash trong môi trường cô lập rồi restart. Hãy mô tả cách xác định record đã ACK nào bị thiếu. Test này chưa chứng minh những điều gì về mất điện và hỏng disk?

### Bài 9 — Outbox sau crash

Payment và outbox event được commit cùng transaction. Relay phát event nhưng crash trước khi cập nhật trạng thái đã phát. Event được gửi lại.

Vì sao đây là hành vi có thể xảy ra? Consumer cần những đặc tính nào để không tạo hai bản ghi thanh toán hoặc cộng doanh thu hai lần?

### Bài 10 — Khôi phục sau xóa nhầm

Một thao tác xóa nhầm đã lan qua primary và tất cả replica. Cluster khỏe, không node nào crash. Tại sao replication không giải quyết được? Hãy lập kế hoạch dùng backup/PITR để phục hồi, đồng thời tránh ghi đè các giao dịch hợp lệ phát sinh sau mốc restore.

### Bài 11 — Chọn chính sách theo nghiệp vụ

Với bốn loại dữ liệu: cache sản phẩm, giỏ hàng, payment ledger, audit log bắt buộc, hãy đề xuất:

- Lỗi được phép chịu (process/node/region).
- RPO/RTO mục tiêu.
- Mức ACK/persistence/replication cần khảo sát.
- Phương án backup và thử restore.
- Cách đối soát sau khi khôi phục.

Không cần chọn một database “tốt nhất”; trọng tâm là **lập hợp đồng độ bền dựa trên rủi ro**.

## 26. Quy trình lựa chọn chế độ độ bền cho hệ NoSQL mới

Một cách ra quyết định có hệ thống:

**Bước 1 — Liệt kê loại dữ liệu.** Phân biệt dữ liệu nguồn, cache, search projection, event log, ledger và snapshot lịch sử.

**Bước 2 — Chọn mô hình sự cố.** Chỉ cần chịu process crash, hay phải chịu host mất điện, disk loss, một AZ, toàn region và lỗi người vận hành?

**Bước 3 — Xác định ý nghĩa ACK.** Lệnh nào được phép trả thành công trước fsync/replication, lệnh nào phải đợi nhiều bản sao hoặc durable commit?

**Bước 4 — Xác định mốc phục hồi.** RPO, RTO, retention và quyền restore là bao nhiêu; backup/DR có phù hợp không?

**Bước 5 — Chọn cơ chế theo hệ quản trị.** Ví dụ MongoDB `w/j`, Redis RDB/AOF, Cassandra commitlog sync/CL/RF, DynamoDB PITR/replication, Elasticsearch translog/replica, Neo4j transaction log/cluster.

**Bước 6 — Thiết kế idempotency và event recovery.** Không để response timeout thành giao dịch trùng; bảo vệ outbox, consumer và read model.

**Bước 7 — Kiểm thử đúng loại crash.** Process crash khác mất điện, node loss khác region loss; test cần ghi nhận ACK độc lập.

**Bước 8 — Đo hiệu năng và chi phí.** p95/p99 write latency, fsync time, replication lag, throughput, backup/restore time và độ ổn định dưới tải.

**Bước 9 — Viết runbook vận hành.** Ai xác định authoritative leader? Khi nào restore? Những invariant nào kiểm chứng trước khi mở traffic?

**Bước 10 — Diễn tập định kỳ.** Cấu hình và volume dữ liệu thay đổi, vì vậy một bài test thành công năm trước không đủ bảo đảm trạng thái hiện tại.

## 27. Kết luận

**Khôi phục sau crash** và **độ bền của NoSQL** phải được hiểu theo từng ranh giới, không thể rút gọn thành câu “database có ghi log và có replica”.

- **ACK** cho biết server đã xác nhận theo một chính sách; cần biết chính sách yêu cầu bộ nhớ, journal, fsync hay replication đến đâu.
- **WAL/commit log, snapshot và checkpoint** giúp khôi phục sau process/OS crash, nhưng chỉ bảo vệ những thay đổi còn tồn tại trong tầng lưu trữ tương ứng.
- **Replication/quorum** giảm rủi ro mất node và hỗ trợ failover, nhưng không đồng nghĩa mọi replica đã sync bền, cũng không thay thế backup.
- **Redis RDB/AOF, MongoDB w/j, Cassandra commitlog/CL, DynamoDB managed durability, Elasticsearch translog, Neo4j transaction logs và RocksDB write options** có cách đặt ranh giới ACK khác nhau.
- **Backup/PITR và diễn tập restore** cần thiết để đối phó hỏng nhiều bản sao, lỗi logic, xóa nhầm hoặc mất region theo mục tiêu RPO/RTO.
- **Idempotency, transaction/outbox và reconciliation** bảo vệ tính đúng đắn khi kết quả commit không rõ hoặc các hệ phụ thuộc chưa đồng bộ.

Ba câu hỏi cần luôn trả lời trước khi chọn chế độ độ bền là: **“Một write đã ACK sẽ tồn tại sau loại crash nào?”, “Nếu write đã commit nhưng client không nhận được ACK thì retry thế nào cho an toàn?”, và “Nếu cả bản lưu nguồn không còn, khôi phục từ đâu, mất bao nhiêu dữ liệu và bao lâu mới hoạt động lại?”**

Khi câu trả lời được thể hiện bằng cấu hình có kiểm chứng, mục tiêu RPO/RTO và bài thử khôi phục phù hợp, tính **durability** mới trở thành một cam kết vận hành có thể đo lường, thay vì một kỳ vọng mơ hồ.
