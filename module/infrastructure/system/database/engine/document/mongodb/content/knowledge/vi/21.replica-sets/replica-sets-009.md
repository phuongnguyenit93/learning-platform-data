# Hidden member, delayed member và giới hạn sử dụng trong MongoDB Replica Set

## 1. Vì sao replica set cần các thành viên đặc biệt?

Một MongoDB replica set thông thường có **primary** nhận phần lớn thao tác ghi và các **secondary** đồng bộ dữ liệu qua oplog. Khi primary lỗi, những thành viên đủ điều kiện có thể tham gia bầu cử để chọn primary mới. Secondary cũng có thể phục vụ một số đọc theo cấu hình read preference.

Tuy nhiên, không phải node nào cũng nên tham gia cùng một vai trò:

- Một máy chủ dành riêng cho **backup** hoặc **báo cáo nặng** không nên bất ngờ trở thành primary.
- Một node dùng để giữ **dữ liệu trễ có chủ đích** nhằm tăng cơ hội cứu dữ liệu sau khi có thao tác xóa nhầm không được phục vụ request đọc thông thường.
- Một node có phần cứng yếu hoặc đặt ở mạng xa không nên làm suy giảm khả năng failover và write concern của các node chính.

MongoDB có các thuộc tính thành viên hỗ trợ những mục đích đó. Hai cấu hình quan trọng trong bài:

1. **Hidden member:** secondary có `hidden: true`, `priority: 0`; không được driver phát hiện cho việc đọc thông thường qua replica set topology, nhưng vẫn đồng bộ dữ liệu và có thể được truy cập trực tiếp khi cần.
2. **Delayed member:** secondary đặt `secondaryDelaySecs` để **cố ý áp dụng các thay đổi chậm hơn**. Trong cấu hình an toàn, node này cần đồng thời `hidden: true`, `priority: 0` và **nên `votes: 0`** để tránh làm ảnh hưởng majority acknowledgment.

> **Điểm cần nhớ:** *hidden* là chính sách **ẩn khỏi lựa chọn đọc thông thường**; *delayed* là chính sách **chậm cập nhật dữ liệu có chủ đích**. Một hidden member không mặc định có độ trễ, nhưng delayed member nên được cấu hình hidden.

Các member đặc biệt **không thay thế** một thiết kế replica set có quorum ổn định, hệ thống backup độc lập hay quy trình khôi phục được kiểm thử.

---

## 2. Ôn nhanh cơ chế primary, secondary và oplog

Với một replica set gồm ba data-bearing voting members:

```text
                        Replica set rsMain
                    +----------------------+
Application writes -> PRIMARY    db1 (vote=1)
                    |          |
                    |          +--> oplog / replication
                    |                      |
                    |           +----------+---------+
                    |           v                    v
                    |    SECONDARY db2          SECONDARY db3
                    |      vote=1                vote=1
                    +----------------------+
```

- **Primary:** nhận thao tác ghi thông thường và ghi các operation tương ứng để replica set đồng bộ.
- **Secondary:** sao chép/applies các thao tác từ nguồn đồng bộ để duy trì một bản dữ liệu gần với primary.
- **Oplog (`local.oplog.rs`):** log có thứ tự, kích thước có giới hạn theo thời gian lưu; secondary cần đủ các thao tác chưa áp dụng để đuổi kịp.
- **Election:** những thành viên có quyền bầu chọn bỏ phiếu chọn primary đủ điều kiện khi cần.
- **Write concern:** quy định số lượng và loại acknowledgment cần nhận trước khi client coi thao tác ghi đã được xác nhận.

Đồng bộ secondary là **bất đồng bộ**. “Đã ghi trên primary” không đồng nghĩa tất cả secondary lập tức nhìn thấy thay đổi. Hidden member cũng là secondary, nên có thể có lag bình thường ngay cả khi **không** bật delayed.

### 2.1. Ba thuộc tính dễ nhầm: `priority`, `votes`, `hidden`

| Thuộc tính | Câu hỏi nó giải quyết | Giá trị liên quan |
| --- | --- | --- |
| `priority` | Node này có thể trở thành primary và được ưu tiên bầu đến mức nào? | `0` nghĩa là **không được trở thành primary**. |
| `votes` | Node này có phiếu bầu và có tính vào voting majority không? | `0` hoặc `1`; `0` là **non-voting**. |
| `hidden` | Driver có được giới thiệu node này như secondary để chọn đọc thông thường không? | `true` ẩn node khỏi topology mà client khám phá qua `hello`. |
| `secondaryDelaySecs` | Node phải trễ bao lâu trong việc áp dụng replication operations? | Số giây; `0` nghĩa là không cố ý làm trễ. |

`priority: 0` **không tự động** có nghĩa `votes: 0`. Một secondary priority 0 vẫn có thể bỏ phiếu. Tương tự, `hidden: true` **không tự động** có nghĩa non-voting.

### 2.2. Cấu hình và trạng thái runtime khác nhau

Một node hidden vẫn có thể hiển thị trạng thái **SECONDARY** trong `rs.status()`. `hidden` và `secondaryDelaySecs` là **cấu hình vai trò**, không phải những trạng thái lifecycle riêng thay thế `SECONDARY`.

---

## 3. So sánh thành viên thông thường, priority 0, hidden và delayed

| Loại thành viên | `priority` | `hidden` | `votes` | Độ trễ được cấu hình | Có thể thành primary? | Đường đọc thường |
| --- | ---: | --- | ---: | --- | --- | --- |
| Secondary thông thường | Thường `1` | `false` | Thường `1` | Không | Có, nếu đủ điều kiện | Có thể được chọn bằng secondary read preference. |
| Priority-0 secondary | `0` | `false` | `0` hoặc `1` | Không | Không | Vẫn có thể phục vụ đọc thông thường từ secondary. |
| Hidden secondary | `0` | `true` | `0` hoặc `1` | Không | Không | Phải kết nối trực tiếp để đọc. |
| Delayed secondary khuyến nghị | `0` | `true` | **`0`** | Có, `secondaryDelaySecs > 0` | Không | Không dành cho request bình thường; truy cập trực tiếp có kiểm soát khi khôi phục. |
| Arbiter | `0` | Không phải kiểu secondary giữ dữ liệu | `1` | Không | Không | **Không lưu bản dữ liệu để đọc/backup.** |

Sự khác nhau giữa **priority-0 visible** và **hidden** rất quan trọng:

```text
priority=0, hidden=false:
  vẫn được driver nhìn thấy như secondary,
  có thể được chọn cho secondary reads.

priority=0, hidden=true:
  không xuất hiện như secondary thông thường trong hello,
  không được chọn cho secondary reads qua replica-set discovery.
```

Nếu mục tiêu **chỉ** là ngăn một member làm primary nhưng vẫn cần phục vụ đọc từ ứng dụng, một **priority-0 secondary không hidden** có thể phù hợp hơn.

Nếu mục tiêu **cách ly tải backup/báo cáo khỏi các đường đọc ứng dụng**, một **hidden secondary** thường phù hợp hơn.

---

## 4. Hidden member thực chất làm gì?

MongoDB mô tả hidden member là một secondary giữ bản sao dữ liệu nhưng bị ẩn đối với client applications trong quá trình khám phá topology.

Ví dụ cấu hình một member:

```javascript
{
  _id: 3,
  host: "mongo-hidden.example.net:27017",
  priority: 0,
  hidden: true,
  votes: 0
}
```

Ý nghĩa:

- `priority: 0`: node không được bầu làm primary.
- `hidden: true`: client kết nối qua topology thông thường không được giới thiệu node như secondary để phân phối đọc.
- `votes: 0`: tùy chọn ở ví dụ này để node không tham gia quorum; **hidden không bắt buộc phải non-voting**.
- Không có `secondaryDelaySecs` khác 0: node vẫn **cố gắng đồng bộ gần thời gian thực**, với replication lag thực tế tùy tải.

### 4.1. Hidden không phải “đã tắt replication”

Hidden member tiếp tục đồng bộ dữ liệu với replica set. Nó vẫn:

1. Duy trì bản sao dữ liệu của mình.
2. Nhận và áp dụng replication operations từ sync source.
3. Xây và duy trì index theo cơ chế replica set.
4. Tiêu thụ CPU, RAM, I/O, lưu trữ, network và tài nguyên vận hành.
5. Có replication lag và có thể phải initial sync/resync như secondary khác.

Hidden chỉ thay đổi **khả năng được chọn cho request đọc thông thường** và yêu cầu `priority: 0`, không giảm replication workload về 0.

### 4.2. Hidden không phải “không thể đọc”

Với quyền phù hợp, người vận hành **có thể kết nối trực tiếp** đến hidden node để chạy báo cáo hoặc thao tác backup đúng quy trình. Hidden không phải là cơ chế bảo mật, mã hóa hay tường lửa.

Cần giới hạn:

- Network access tới node.
- Tài khoản và quyền đọc/backup.
- TLS/xác thực replica set.
- Số truy vấn đồng thời và tài nguyên dành cho báo cáo.
- Việc cho phép kết nối trực tiếp tới sharded nodes (xem phần giới hạn sharding).

### 4.3. Hidden có thể bỏ phiếu

Một hidden member `votes: 1` có thể bỏ phiếu trong election. Nó **không thể trở thành primary** vì `priority: 0`, nhưng vẫn có thể ảnh hưởng tới:

- Mẫu số và ngưỡng voting majority.
- Khả năng election thành công khi một số node mất kết nối.
- Việc ghi với `w: "majority"` có cần acknowledgment từ node này hay không.

Do đó, không được diễn giải “ẩn khỏi client” thành “không tham gia bầu cử”. Hai đặc tính này độc lập.

### 4.4. Hidden không xuất hiện trong `db.hello()` như secondary bình thường

Client kết nối đến replica set sẽ sử dụng topology discovery, thường qua `hello`. Hidden member không được quảng bá như một địa chỉ secondary phục vụ các read preference thông thường.

Tuy nhiên, node vẫn là thành viên thật và có thể được kiểm tra trong `rs.conf()`/`rs.status()` bởi tài khoản quản trị. Không dùng việc vắng mặt trong danh sách host của `hello` để kết luận node không tồn tại.

Tài liệu gốc: [Hidden Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-hidden-member/).

---

## 5. Các trường hợp sử dụng hidden member

### 5.1. Backup với tải I/O được cách ly

Backup có thể tạo nhiều thao tác đọc, filesystem snapshot, I/O hoặc CPU. Nếu đặt workload backup lên một secondary thông thường phục vụ đọc của ứng dụng, các truy vấn khác và replication có thể chậm lại.

Hidden member giúp tạo node riêng:

```text
PRIMARY ------------------> Secondary ứng dụng
    |
    +---------------------> Hidden secondary
                                  |
                                  +--> Công việc backup
                                  +--> Kiểm tra dữ liệu / export
```

Lợi ích: hoạt động backup ít tranh tài nguyên trực tiếp với primary và các secondary phục vụ người dùng.

**Giới hạn:** chạy backup nặng trên hidden vẫn có thể làm chính hidden tụt replication lag. Nếu hidden có `votes: 1`, node này còn có thể ảnh hưởng tới majority availability trong một số tình huống. Cần theo dõi tài nguyên và tình trạng oplog.

**Backup đúng cách:** không tự sao chép data files của `mongod` đang chạy bằng `cp`, `scp` hoặc `tar` rồi mặc định bản sao nhất quán. Hãy dùng công cụ/quy trình backup MongoDB hỗ trợ, snapshot đảm bảo nhất quán hoặc các bước như `fsyncLock` khi tài liệu vận hành cho phép. Phải kiểm thử restore.

### 5.2. Báo cáo nặng, chạy định kỳ

Ví dụ ban đêm cần quét lịch sử đơn hàng để tính thống kê lớn:

```javascript
db.orders.aggregate([
  {
    $match: {
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      totalRevenueMinor: { $sum: "$totalMinor" }
    }
  }
]);
```

Có thể định tuyến **job báo cáo chuyên dụng** tới hidden secondary qua kết nối trực tiếp, nhưng phải chấp nhận dữ liệu có độ trễ theo replication và phải giới hạn tải. Không tự xem hidden member là một hệ OLAP không giới hạn tài nguyên.

### 5.3. Maintenance hoặc kiểm thử dữ liệu

Hidden có thể hỗ trợ một số tác vụ kiểm tra độc lập, nhưng không nên để các script sửa dữ liệu nguồn chạy trực tiếp trên hidden. Với replica set, **ghi ứng dụng phải đi qua primary**; secondary chỉ áp dụng thao tác replicated theo cơ chế của MongoDB.

Nếu một script cần cập nhật dữ liệu, nó nên đi theo API/đường ghi được kiểm soát của replica set, không “ghi thử riêng” vào hidden rồi mong thay đổi không lan sang nơi khác.

---

## 6. Kết nối đọc trực tiếp tới hidden member

Ví dụ dùng `mongosh` cho một **self-managed replica set**:

```shell
mongosh "mongodb://mongo-hidden.example.net:27017/?directConnection=true&readPreference=secondary"
```

Đây là URI minh họa. Môi trường production cần cấu hình TLS, authentication và network policy tương ứng. Không hardcode password trong ví dụ hoặc script lưu trên repository.

`directConnection=true` hướng client tới **server cụ thể**, thay vì dựa vào topology discovery để chọn một secondary khác. `readPreference=secondary` thể hiện ý định đọc từ secondary, không phải yêu cầu node làm primary.

### 6.1. Vì sao chỉ `readPreference=secondary` là chưa đủ?

Trong URI kết nối replica set bình thường:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/
  ?replicaSet=rsMain&readPreference=secondary
```

Driver chọn secondary từ những node được topology công bố. **Hidden không được công bố cho đường chọn này**, vì vậy thêm `readPreference=secondary` không khiến request tự động chạy trên hidden.

Khi cần hidden, sử dụng cấu hình kết nối **riêng** và chỉ cấp nó cho tác vụ được phép đọc hidden.

### 6.2. Không dùng hidden làm secondary đọc mặc định

Nếu toàn bộ ứng dụng dùng hidden để đọc:

- Workload báo cáo/backup có thể tranh tài nguyên với API.
- Dữ liệu có thể stale so với primary.
- Connection trực tiếp làm mất lợi ích chọn server/failover theo topology thông thường.
- Nếu node hidden bị lỗi, kết nối trực tiếp không tự chuyển sang secondary thường.

Hidden thích hợp cho **đường đọc đặc biệt có kiểm soát**, không phải thủ thuật tăng throughput bằng cách tùy tiện ẩn mọi secondary.

### 6.3. Ranh giới an toàn trong sharded cluster

Trong sharded cluster, đọc trực tiếp từ hidden node của một shard **bỏ qua `mongos`**, có thể dẫn đến kết quả không nhất quán hoặc thiếu dữ liệu vì metadata/shard routing và chunk migrations.

Tài liệu MongoDB cảnh báo không dùng direct read trên hidden shard member như cách thay thế `mongos`. Từ MongoDB 8.0, một số command khi kết nối trực tiếp tới shard node còn bị từ chối.

Nếu cần cách ly workload đọc trong sharded cluster, xem **tag-based read preferences** và kiến trúc được hỗ trợ qua router, thay vì đơn giản kết nối trực tiếp một hidden shard node.

---

## 7. Delayed member là gì?

Một **delayed secondary** giữ bản dữ liệu có trạng thái **cũ hơn primary một khoảng thời gian được định cấu hình**. Thay vì áp dụng oplog operations ngay khi có thể, node trì hoãn theo `secondaryDelaySecs`.

Ví dụ cấu hình trễ 1 giờ:

```javascript
{
  _id: 4,
  host: "mongo-delayed.example.net:27017",
  priority: 0,
  hidden: true,
  votes: 0,
  secondaryDelaySecs: 3600
}
```

Khi primary ở khoảng **10:00**, delayed member được cấu hình 3.600 giây có thể phản ánh trạng thái gần **09:00** nếu đồng bộ đang hoạt động bình thường. Đây là hình dung về một **mốc lịch sử**, không phải bảo đảm luôn có snapshot chính xác đúng từng giây.

```text
PRIMARY (gần realtime)
09:00 ---- 09:15 ---- 09:30 ---- 09:45 ---- 10:00
                                              ^
                                              | hiện tại
DELAYED (trễ khoảng 1 giờ)
08:00 ---- 08:15 ---- 08:30 ---- 08:45 ---- 09:00
                                              ^
                                              | dữ liệu đã áp dụng
```

Nếu primary bị xóa nhầm collection lúc 09:50, ở thời điểm 10:00 delayed 1 giờ có thể vẫn chưa áp dụng thao tác xóa nhầm đó. Đây là một **cơ hội ứng phó sự cố**: kịp bảo toàn dữ liệu trước khi thao tác xóa đến lượt được áp dụng.

### 7.1. Delayed không có nghĩa dừng replication vô hạn

Delayed member vẫn đồng bộ theo cơ chế replica set, nhưng **chậm áp dụng** so với một secondary bình thường. Sau khi thời gian delay trôi qua, thao tác xóa hoặc sửa dữ liệu lỗi **cũng sẽ được áp dụng** nếu node tiếp tục chạy.

Vì vậy, delayed member là **cửa sổ thời gian hỗ trợ khôi phục một số lỗi người dùng**, không phải kho bản sao được bảo vệ vĩnh viễn.

### 7.2. Không phải mọi lỗi đều nằm trong cửa sổ delay

Delayed member không bảo đảm cứu được:

- Dữ liệu bị sai từ trước khi khoảng delay bắt đầu.
- Xóa nhầm chỉ được phát hiện **sau khi delay đã trôi qua**.
- Dữ liệu bị mất do lỗi phần cứng tác động cả primary và delayed.
- Mã độc hoặc tài khoản quản trị xâm nhập có quyền phá cả replica set.
- Sai lệch do sharding/chunk migrations trong các trường hợp không thể phục hồi nhất quán bằng delayed node.
- Sự cố khiến oplog không còn đủ lịch sử để delayed member đuổi kịp.

Không nên mô tả delayed member như “backup 1 giờ gần nhất luôn có thể restore”.

---

## 8. Ba điều kiện cấu hình delayed member

Đối với delayed secondary:

```javascript
{
  priority: 0,
  hidden: true,
  votes: 0,
  secondaryDelaySecs: 3600
}
```

### 8.1. `priority: 0` — bắt buộc

Delayed member **không được trở thành primary**, vì dữ liệu cố ý chậm. Nếu một node giữ dữ liệu lịch sử được bầu làm primary, các client có thể quan sát trạng thái không phù hợp và failover trở nên nguy hiểm.

MongoDB yêu cầu delayed member có priority 0.

### 8.2. `hidden: true` — bắt buộc

Delayed member phải được ẩn để driver không tự gửi các request `readPreference=secondary` tới node đang giữ dữ liệu cũ. Nếu không ẩn, khi topology thay đổi hoặc các secondary khác lỗi, ứng dụng có thể vô tình đọc dữ liệu cũ nhiều phút/giờ.

Việc ẩn không có nghĩa node không thể bị truy cập trực tiếp bởi người có quyền. Đó là lý do phải có network/security policy riêng.

### 8.3. `votes: 0` — khuyến nghị rất mạnh

Về mặt cơ chế, delayed member **có thể** bỏ phiếu nếu được cấu hình `votes: 1`. Nhưng tài liệu MongoDB nhấn mạnh nên giữ delayed **hidden và non-voting** để tránh làm chậm majority acknowledgment.

Vì sao? Một delayed member có phiếu có thể cần tham gia quá trình xác nhận write concern `"majority"` trong tình huống replica set suy giảm. Nó không thể xác nhận thao tác trước khi phần replication tương ứng tới thời điểm áp dụng, dẫn đến nguy cơ chậm ít nhất bằng delay cấu hình.

Vì vậy, **`votes: 0` là lựa chọn nên áp dụng khi thiết kế delayed member**, trừ khi có lý do vận hành được phân tích và chấp nhận rủi ro rõ ràng.

### 8.4. `secondaryDelaySecs` — số giây delay

Ví dụ:

```javascript
secondaryDelaySecs: 3600 // 1 giờ
```

Một số ví dụ quy đổi:

| Khoảng delay | Giá trị |
| --- | ---: |
| 5 phút | `300` |
| 30 phút | `1800` |
| 1 giờ | `3600` |
| 6 giờ | `21600` |
| 24 giờ | `86400` |

Thời gian nên dựa trên **thời gian phát hiện sự cố**, tốc độ ứng phó và năng lực lưu trữ oplog, không chọn một con số chỉ vì dễ nhớ.

Trong MongoDB 5.0 trở đi, dùng tên cấu hình `secondaryDelaySecs`. Các tài liệu cũ có thể đề cập `slaveDelay`; không sao chép cú pháp của phiên bản cũ mà chưa đối chiếu compatibility.

Tài liệu chính: [Delayed Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-delayed-member/) và [Configure a Delayed Self-Managed Replica Set Member](https://www.mongodb.com/docs/manual/tutorial/configure-a-delayed-replica-set-member/).

---

## 9. Cấu trúc replica set có hidden và delayed member

Một thiết kế minh họa gồm **ba thành viên voting thông thường** và **hai secondary đặc biệt non-voting**:

```text
                  rsCommerce (minh họa 5 thành viên)
                   ______________________________
                  |                              |
                  |  db1 PRIMARY       vote=1    |
Client writes --->|  db2 SECONDARY     vote=1    |
                  |  db3 SECONDARY     vote=1    |
                  |                              |
                  |  db4 HIDDEN        vote=0    |--> Backup / reporting
                  |       priority=0             |
                  |                              |
                  |  db5 DELAYED+HIDDEN vote=0   |--> Recovery window
                  |       priority=0, delay=1h   |
                  |______________________________|

Bầu cử/majority: db1, db2, db3 là 3 voting members.
Backup/reporting: db4 không được bầu làm primary.
Dữ liệu lịch sử: db5 không được bầu làm primary và không bỏ phiếu.
```

Ví dụ tài liệu cấu hình hai member đặc biệt:

```javascript
// Phần tử trong cfg.members, không phải toàn bộ config replica set.
{
  _id: 3,
  host: "db4.example.net:27017",
  priority: 0,
  hidden: true,
  votes: 0,
  secondaryDelaySecs: 0
}

{
  _id: 4,
  host: "db5.example.net:27017",
  priority: 0,
  hidden: true,
  votes: 0,
  secondaryDelaySecs: 3600
}
```

**Đây không phải hướng dẫn dựng replica set mới chỉ bằng hai object.** Các member cần hostname hợp lệ, quá trình initial sync, cấu hình security, oplog và topology được kiểm tra trước khi thêm.

### 9.1. Tại sao giữ ba voters bình thường?

Nếu chỉ có một primary và một secondary có quyền voting rồi bổ sung một **delayed voter** làm lá phiếu thứ ba, hệ thống có thể rơi vào tình huống majority phụ thuộc vào node đang cố ý trễ. Thiết kế trên đặt khả năng failover cơ bản ở các node đồng bộ bình thường.

Ví dụ ba voting members cần **2/3 phiếu** để hình thành majority. Khi một voter mất kết nối, hai voter còn lại vẫn có thể duy trì election/quorum nếu điều kiện khác đáp ứng. Hai node non-voting không làm tăng mẫu số majority.

### 9.2. Hidden voting member không giống hidden non-voting member

Nếu `db4` có `votes: 1`, nó được tính là voter và có thể giúp elect primary. Nhưng khi đặt máy backup dưới tải cao, node này có thể lag hoặc mất kết nối; ảnh hưởng tới khả năng majority trong một số topology.

Tùy kiến trúc, hidden voting member có thể là lựa chọn hợp lệ, nhưng **không nên gán `votes: 1` chỉ để “thêm độ an toàn”** mà chưa phân tích các network partition và quorum.

---

## 10. Hidden và delayed tác động tới election ra sao?

### 10.1. Điều kiện trở thành primary

Một thành viên cần đủ điều kiện bầu làm primary, trong đó có `priority > 0`. Hidden và delayed có `priority: 0`, nên **không thể trở thành primary**.

Nhưng việc bị loại khỏi ứng viên **không đồng nghĩa** bị loại khỏi quá trình bầu cử. Hidden member có `votes: 1` vẫn có thể bỏ phiếu cho một node khác.

### 10.2. Tính majority dựa trên voter

Hãy so sánh:

```text
Cấu hình A:
P vote=1, S1 vote=1, S2 vote=1,
Hidden vote=0, Delayed vote=0
=> 3 voters; majority cần 2 phiếu.

Cấu hình B:
P vote=1, S1 vote=1, Hidden vote=1
=> 3 voters; majority cần 2 phiếu.
```

Trong cấu hình A, hidden và delayed **không tăng quorum**. Trong cấu hình B, hidden là một phần của majority mặc dù không thể làm primary.

### 10.3. Những trường hợp dễ gây nhầm

- Chỉ còn một hidden voter hoạt động, tất cả member eligible primary đều hỏng: hidden **không thể tự trở thành primary**.
- Hidden non-voting còn khỏe nhưng mất đa số voting nodes: replica set vẫn có thể **không có primary**; một node dữ liệu non-voting không thay thế quorum.
- Một hidden voting node bị tắt để backup mà không kiểm tra số voter còn lại: primary có thể mất majority trong các tình huống khác.

Do đó, khi thay đổi `votes`, phải phân tích election trước/sau chứ không chỉ xem tổng số máy.

---

## 11. Write concern `"majority"` và delayed voting member

Đây là rủi ro vận hành quan trọng nhất của delayed member.

Giả sử replica set có ba voting nodes:

```text
P  : primary  vote=1, cập nhật gần realtime
S  : secondary vote=1, cập nhật gần realtime
D  : delayed  vote=1, chậm 10 phút
```

Một write concern `"majority"` cần điều kiện đa số thành viên voting data-bearing theo cơ chế tương ứng.

### 11.1. Khi cả P và S khỏe

P và S có thể cung cấp majority mà không cần D. Một write thường không phải đợi 10 phút chỉ vì D là voter nếu các điều kiện khác cho phép ghi được xác nhận.

### 11.2. Khi S bị ngắt kết nối

Chỉ còn P và D là các voting members hoạt động. Majority giờ có thể cần D. Vì D cố ý áp dụng replication trễ 10 phút, acknowledgment của những write mới theo `"majority"` có thể phải **đợi khoảng delay**, hoặc timeout theo cấu hình ứng dụng.

```text
P -- write at 10:00 ------> D applies around 10:10
|                                   |
+-- cần majority gồm P+D -----------+
                |
                +--> write acknowledgment bị chậm
```

Tài liệu MongoDB cảnh báo tình huống này có thể làm **majority commit point tụt lại**, gây cache pressure và vấn đề hiệu năng.

### 11.3. Delayed non-voting giải quyết phần nào?

Nếu D có `votes: 0`, node này **không tham gia xác nhận `w: "majority"`** và không làm tăng voting majority. Replica set vẫn phải giữ quorum bằng các voter bình thường; D không thể “cứu” majority khi chúng đã mất quá nhiều.

**Non-voting không có nghĩa không bao giờ tham gia write acknowledgment:**

| Write concern | Hidden/delayed `votes: 0` | Lưu ý |
| --- | --- | --- |
| `w: 1` | Không cần chờ secondary. | Primary đáp ứng điều kiện w=1. |
| `w: "majority"` | **Không được tính vào acknowledgment majority**. | Quorum dựa trên voting data-bearing members theo rule của server. |
| `w: <number>` với số cụ thể | **Có thể được tính** nếu là data-bearing member. | Nếu tính cả delayed, acknowledgment có thể phải đợi tới khi delay trôi qua. |

Vì vậy, ngay cả khi đặt `votes: 0`, một ứng dụng dùng `w: 4` trong topology chỉ có ba non-delayed data-bearing nodes vẫn có thể vô tình chờ delayed node. Cần kiểm tra **numeric write concern** của ứng dụng, không chỉ `"majority"`.

Tài liệu: [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).

---

## 12. Chọn thời gian delay dựa trên oplog window

Delayed member cần truy cập các oplog operations đủ lâu để áp dụng sau khoảng delay. Oplog là cấu trúc có dung lượng và **cửa sổ thời gian thực tế phụ thuộc tốc độ ghi**, không phải một kho lịch sử vô hạn.

### 12.1. Vì sao `secondaryDelaySecs` phải nhỏ hơn oplog window?

Ví dụ:

```text
Oplog chỉ giữ được khoảng 45 phút operations.
Delayed secondary được cấu hình chậm 1 giờ.
```

Khi delayed node đến lượt xử lý một operation cũ hơn một giờ, các entry cần thiết có thể đã bị oplog ở nguồn đồng bộ ghi đè. Node không thể tiếp tục đuổi kịp như mong đợi và có nguy cơ trở thành **stale** rồi phải resync.

Tài liệu MongoDB yêu cầu độ dài delay phải nằm trong khả năng cửa sổ oplog. Trong thực tế nên có **biên an toàn** cho:

- Khoảng delay được chủ ý cấu hình.
- Thời gian node tạm dừng hoặc bảo trì.
- Replication lag bổ sung vì CPU/I/O/network.
- Các đợt tăng tải ghi khiến oplog window co lại.
- Thời gian để phát hiện và giải quyết sự cố trước khi node cần catch up.

### 12.2. Ví dụ đánh giá

Giả sử:

```text
Configured delay            : 60 phút
Oplog window hiện đo        : 240 phút
Biên hiện có                : khoảng 180 phút
```

Đây **không phải bảo đảm** an toàn cho mọi thời điểm. Nếu một job bulk write làm tốc độ sinh oplog tăng mạnh, window có thể giảm nhanh. Cần xem tải đỉnh và outage dự kiến, không dùng riêng kết quả đo vào buổi tối vắng tải.

Một ví dụ nguy hiểm:

```text
Configured delay            : 6 giờ
Oplog window lúc cao điểm   : 4 giờ
```

Cấu hình này có thể khiến node delayed **không duy trì được replication** như thiết kế.

### 12.3. Xem thông tin oplog

Trong `mongosh`, tùy node và quyền quản trị:

```javascript
rs.printReplicationInfo();
```

Có thể xem khả năng lưu trữ và khoảng thời gian oplog được giữ trên node. Để xem tiến độ secondary:

```javascript
rs.printSecondaryReplicationInfo();
```

Lệnh/format có thể thay đổi theo phiên bản. Trong production, nên kết hợp monitoring tự động và kiểm tra oplog window trên các sync source liên quan thay vì tin một lần chạy lệnh.

### 12.4. Stale khác lag thông thường

- **Lag:** secondary chậm hơn primary nhưng vẫn còn đường đồng bộ/các oplog cần thiết.
- **Stale:** nguồn đồng bộ đã mất những oplog entries mà secondary cần; node không thể chỉ “chờ thêm” rồi bắt kịp.

Nếu stale, có thể phải **initial sync/resync** theo quy trình được hỗ trợ. Đây là công việc tốn tài nguyên, không nên cố sửa bằng thao tác thủ công vào oplog.

---

## 13. Hidden member không phải delayed member

Để thấy sự khác nhau, xét cùng một thao tác xóa dữ liệu:

```javascript
db.orders.deleteMany({
  status: "CANCELLED"
});
```

Giả sử thao tác được thực hiện trên primary lúc 10:00.

| Member | Cấu hình | Khi nào có thể phản ánh thao tác xóa? |
| --- | --- | --- |
| Primary | Normal | Theo quá trình thực thi ghi trên primary. |
| Normal secondary | Không cố ý delay | Sau khi áp dụng oplog, thường có lag nhỏ nhưng không được bảo đảm chính xác. |
| Hidden secondary | `hidden: true`, `secondaryDelaySecs: 0` | Sau replication thông thường, không giữ lịch sử có chủ ý. |
| Delayed hidden secondary | `secondaryDelaySecs: 3600` | Theo lịch áp dụng trễ khoảng một giờ nếu replication khỏe. |

**Ẩn node** không làm nó “quay về quá khứ”. Nếu xóa nhầm lúc 10:00 và hidden secondary đã đồng bộ đến 10:01, dữ liệu trên hidden cũng đã bị xóa.

Ngược lại, **delayed** tạo một khoảng thời gian để can thiệp, nhưng sau delay nó vẫn áp dụng thao tác xóa.

---

## 14. Delayed member là cơ hội khôi phục, không phải backup đầy đủ

Một delayed secondary đôi khi được mô tả như “bản sao lịch sử đang chạy”. Cách diễn đạt này tiện, nhưng có giới hạn:

1. **Không bất biến:** theo thời gian, mọi thao tác ghi/xóa/hỏng logic sẽ được áp dụng.
2. **Không lưu nhiều mốc thời gian tùy chọn:** thường chỉ phản ánh trạng thái trễ theo cấu hình; không thể chọn ngẫu nhiên thời điểm bất kỳ như từ hệ PITR.
3. **Không đảm bảo thời điểm chính xác:** lag thực tế có thể lệch khỏi giá trị cấu hình vì replication health.
4. **Không độc lập khỏi replica set:** cần oplog, kết nối, quản trị và thường cùng phạm vi credentials/infrastructure.
5. **Không thay thế lưu trữ offsite/immutable:** mất toàn bộ cluster, tài khoản bị xâm nhập hoặc lỗi vận hành lớn có thể gây mất cả delayed node.
6. **Không tự chữa dữ liệu đã sai từ trước:** dữ liệu sai có thể đã có trên mọi member.
7. **Khôi phục có thể làm phát sinh downtime:** phải bảo toàn trạng thái cũ và dựng đường restore an toàn, không thể cứ đổi vai trò node là xong.

### 14.1. Bài toán xóa nhầm

Giả sử:

```text
09:00  : dữ liệu bình thường.
09:30  : admin vô tình drop một collection trên primary.
09:40  : phát hiện sự cố.
10:30  : delayed 1 giờ có thể tới lượt áp dụng lệnh drop.
```

Có một **cửa sổ khoảng 50 phút sau lúc phát hiện** để bảo toàn bản dữ liệu trước khi thao tác drop được delayed node áp dụng, giả sử lag và tình trạng replication đúng như dự kiến.

Không nên ngồi đợi. Quy trình ứng phó cần lập tức:

1. Xác định chính xác operation lỗi và thời điểm.
2. Xác nhận trên delayed node rằng dữ liệu cần cứu **vẫn tồn tại**.
3. Theo runbook quản trị, **ngăn member tiếp tục áp dụng operation gây hại** bằng thao tác cô lập/tạm dừng thích hợp được phê duyệt.
4. Tạo **bản sao nhất quán** bằng phương pháp backup được hỗ trợ trước khi thử phục hồi.
5. Khôi phục dữ liệu sang môi trường tách biệt để kiểm tra.
6. Đối soát dữ liệu, khóa, index, mối quan hệ giữa collection và tác động tới ứng dụng.
7. Xác định cách import/restore trở lại hệ thống, tránh ghi đè dữ liệu hợp lệ phát sinh sau sự cố.

Cần có runbook cụ thể trước khi sự cố xảy ra. **Không tự ý ép một delayed secondary thành primary bằng `rs.reconfig(..., { force: true })`**. Forced reconfiguration hoặc thao tác đổi primary không kiểm soát có thể gây split-brain, rollback hoặc mất những thay đổi hợp lệ.

### 14.2. Backup cần có restore test

Một kiến trúc dữ liệu tin cậy thường cần:

- Backup định kỳ, có thể với point-in-time recovery (PITR) theo yêu cầu.
- Bản backup nằm ở vùng lỗi hoặc tài khoản khác nếu có thể.
- Chính sách retention và kiểm soát quyền xóa bản backup.
- Kiểm tra checksum/khả năng đọc và **diễn tập restore**.
- Runbook xử lý accidental delete, lỗi migration và sự cố an ninh.

Hidden hoặc delayed member là **một lớp bổ sung**, không phải sự thay thế cho các lớp đó.

---

## 15. Giới hạn của delayed member trong sharded cluster

MongoDB cảnh báo delayed member có **giá trị khôi phục hạn chế trong sharded cluster khi balancer hoạt động**. Nguyên nhân là việc **chunk migrations** cũng được phản ánh theo cơ chế replication/sharding; một shard ở thời điểm lịch sử không tự đại diện cho trạng thái nhất quán của **toàn bộ cluster** trước khi migration xảy ra.

Ví dụ:

```text
09:00: Chunk X thuộc Shard A.
09:30: Balancer chuyển Chunk X sang Shard B.
10:00: Xảy ra xóa nhầm dữ liệu.
```

Một delayed member riêng của Shard A không đủ thông tin để khôi phục toàn bộ cluster về 09:15 theo cách nhất quán, vì các shard còn lại và metadata phân vùng cũng phải khớp với thời điểm đó.

Do đó:

- Không xây phương án disaster recovery cho sharded cluster chỉ dựa vào delayed member của từng shard.
- Dùng giải pháp backup/PITR **aware về sharded cluster và metadata**.
- Tránh direct query vào hidden shard member để tạo báo cáo nhiều shard; hãy dùng `mongos` và đường đọc được hỗ trợ.

Tài liệu: [Delayed Replica Set Members — Sharding](https://www.mongodb.com/docs/manual/core/replica-set-delayed-member/).

---

## 16. Cấu hình hidden member trong self-managed replica set

**Các bước sau chỉ minh họa thao tác vận hành.** Chúng đòi quyền quản trị, phải được làm trong maintenance window với runbook và kiểm tra quorum. Không chạy trên production chỉ để thử cú pháp.

### 16.1. Trạng thái trước khi thay đổi

Kết nối `mongosh` tới primary, kiểm tra:

```javascript
rs.status();
rs.conf();
```

Cần xác định:

- Member đích là một **secondary** đang khỏe.
- Member có tên host/port chính xác.
- Replica set có quorum và các member eligible primary thích hợp.
- Oplog và dung lượng lưu trữ đủ.
- Hidden sẽ ảnh hưởng thế nào tới đọc/backup và bầu cử.
- `votes` và `priority` hiện tại là bao nhiêu.

### 16.2. Thay một secondary hiện hữu thành hidden

Ví dụ member đích:

```text
mongo-report.example.net:27017
```

Lấy cấu hình:

```javascript
const cfg = rs.conf();

const idx = cfg.members.findIndex(
  member => member.host === "mongo-report.example.net:27017"
);

if (idx < 0) {
  throw new Error("Member đích không tồn tại trong rs.conf()");
}

// Minh họa: chọn hidden + non-voting.
cfg.members[idx].priority = 0;
cfg.members[idx].hidden = true;
cfg.members[idx].votes = 0;

// Chỉ thực hiện trong maintenance window sau khi
// đã phân tích tác động election/quorum:
// rs.reconfig(cfg);
```

**Cố ý để `rs.reconfig` dưới dạng comment** để bản ví dụ không vô tình thay đổi một replica set khi người học copy cả khối. Lệnh thực thi khi đã phê duyệt:

```javascript
rs.reconfig(cfg);
```

Điểm quan trọng: `idx` là **vị trí trong mảng `cfg.members`**, không phải `members[n]._id`. Hai giá trị không bắt buộc trùng nhau.

### 16.3. Có nhất thiết thay `votes: 0` không?

Không. Một hidden member có thể giữ `votes: 1`. Ví dụ ở đây chủ động dùng non-voting để dành node cho workload chuyên dụng. Chọn `votes` phải dựa vào thiết kế majority và ràng buộc voting member của replica set.

Không thay đổi votes ở nhiều node cùng lúc khi chưa hiểu các giới hạn reconfiguration. MongoDB có giới hạn tối đa **7 voting members** trong một replica set và giới hạn thay đổi voting membership qua từng lần reconfig.

### 16.4. Cẩn trọng với `rs.reconfig()`

Reconfiguration có thể khiến primary step down, xảy ra election và client connection bị gián đoạn tạm thời. Không thực hiện một reconfig trong giờ cao điểm nếu chưa có quy trình chuyển đổi/giám sát. Tránh reconfigure replica set có mixed server versions nếu validation rules có thể khác nhau.

**Không dùng `{ force: true }` như cách “cho lệnh chạy được”** khi gặp lỗi quorum hoặc validation. Forced reconfig là thao tác đặc biệt, có rủi ro cao về consistency và cần hướng dẫn vận hành riêng.

---

## 17. Cấu hình delayed member trong self-managed replica set

Để biến một secondary thành delayed 1 giờ, các thuộc tính mục tiêu:

```javascript
{
  priority: 0,
  hidden: true,
  votes: 0,
  secondaryDelaySecs: 3600
}
```

Ví dụ trên primary:

```javascript
const cfg = rs.conf();

const idx = cfg.members.findIndex(
  member => member.host === "mongo-delayed.example.net:27017"
);

if (idx < 0) {
  throw new Error("Delayed member đích không tồn tại");
}

cfg.members[idx].priority = 0;
cfg.members[idx].hidden = true;
cfg.members[idx].votes = 0;
cfg.members[idx].secondaryDelaySecs = 3600;

// Sau khi xác nhận điều kiện vận hành:
// rs.reconfig(cfg);
```

Một lần nữa, không có lệnh thực thi reconfig trong đoạn mẫu chính để tránh copy nhầm.

### 17.1. Kiểm tra điều kiện trước reconfig

1. Đây là secondary data-bearing, không phải primary/arbiter.
2. Thời lượng oplog **lớn hơn** configured delay, với margin cho peak load/outage.
3. Dung lượng đĩa, CPU, RAM và network đủ cho replication liên tục.
4. Quorum không phụ thuộc vào delayed node nếu đặt `votes: 0`.
5. Workload đọc ứng dụng không sử dụng node này.
6. Chính sách khôi phục có quy định cách dừng/preserve delayed data trong cửa sổ sự cố.
7. Nếu có sharding, đã xét giới hạn chunk migrations.
8. Các member còn lại vẫn có capacity và primary eligibility phù hợp.

### 17.2. Không chuyển từ normal secondary sang delayed mà kỳ vọng lập tức có snapshot quá khứ

Đổi cấu hình làm thay đổi cách member áp dụng những operation tiếp theo theo cơ chế server. Không được khẳng định rằng sau `rs.reconfig` node **ngay lập tức** đã có trạng thái của đúng một giờ trước. Cần giám sát optime, actual lag và trạng thái dữ liệu cho tới khi đạt điều kiện vận hành mong muốn.

### 17.3. Tên trường theo phiên bản

Với MongoDB 5.0+ dùng:

```javascript
secondaryDelaySecs: 3600
```

Đừng dùng tùy tiện tên cũ `slaveDelay` lấy từ bài hướng dẫn phiên bản cũ. Khi upgrade, đối chiếu thay đổi tương thích và cập nhật configuration automation.

---

## 18. Kiểm tra cấu hình sau khi cập nhật

Sau một thay đổi được thực thi hợp lệ, xem cấu hình:

```javascript
const cfg = rs.conf();

cfg.members.map(member => ({
  id: member._id,
  host: member.host,
  priority: member.priority,
  hidden: member.hidden,
  votes: member.votes,
  secondaryDelaySecs: member.secondaryDelaySecs
}));
```

Kiểm tra trạng thái:

```javascript
rs.status();
```

Đối với replica set nhiều member, chú ý:

- Node đang ở trạng thái `SECONDARY` hay lỗi startup/initial sync?
- Member nào hiện là `PRIMARY`?
- Member nào đang voting?
- Replication optime/lastAppliedWallTime có phù hợp không?
- Có member nào mất heartbeat?
- Hidden/delayed được cấu hình đúng tên host chưa?

**Không kết luận trạng thái delay chỉ bằng config.** `secondaryDelaySecs: 3600` là **ý định cấu hình**, còn mức lag thực tế phải quan sát ở runtime.

### 18.1. Monitoring replication lag

Các công cụ thường dùng:

```javascript
rs.printSecondaryReplicationInfo();
```

Và từ replica set status:

```javascript
const status = rs.status();

status.members.map(member => ({
  name: member.name,
  state: member.stateStr,
  optimeDate: member.optimeDate
}));
```

Field cụ thể trong output có thể khác theo phiên bản. Nếu so timestamps từ nhiều node, cần tính đến đồng bộ đồng hồ và khác biệt giữa oplog timestamp, wall time và thời điểm document thực sự được applied.

### 18.2. Lag mong đợi và lag vượt ngưỡng

Nếu cấu hình delayed 1 giờ:

```text
Expected configured delay: ~3600 giây
Observed lag:             ~3700 giây
```

Có thể còn ~100 giây lag vận hành bình thường. Nhưng nếu lag tăng liên tục tới 3 giờ rồi 5 giờ, cần điều tra:

- Primary/sync source đang sinh oplog rất nhanh.
- Disk/CPU trên delayed node bị bão hòa.
- Network chậm hoặc mất kết nối.
- Backup/report job tranh I/O.
- Oplog window sắp không còn đủ để catch up.

Không dùng cùng ngưỡng cảnh báo replication lag cho normal secondary (thường mong gần realtime) và delayed secondary (cố ý lệch theo cấu hình). Dashboard nên hiển thị **configured delay** và **excess lag** riêng.

---

## 19. Hidden và delayed trong MongoDB Atlas hoặc managed deployment

Không nên tự giả định mọi dịch vụ MongoDB managed đều cho phép thao tác trực tiếp `rs.reconfig()` hay đổi tùy ý từng member.

Một nền tảng managed có thể:

- Quản lý topology và voting config tự động.
- Chỉ cho phép một số vai trò node/chức năng nhất định.
- Cung cấp backup/PITR tích hợp.
- Hạn chế direct connection hoặc `fsyncLock`.
- Có chính sách vận hành riêng cho việc thêm member, delayed member và hidden node.

Vì vậy:

1. Đọc tài liệu **đúng nhà cung cấp, loại cluster và phiên bản**.
2. Dùng control plane/API hỗ trợ thay vì sửa một replica set đang được service quản lý.
3. Kiểm tra liệu backup/PITR tích hợp có giải quyết nhu cầu tốt hơn delayed secondary.
4. Không triển khai workaround bằng direct shard node access hoặc sửa cấu hình trái với cơ chế managed service.

---

## 20. Hidden, delayed và các mô hình backup: so sánh mục tiêu

| Phương án | Mục tiêu chính | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| Normal secondary | Availability, replication, có thể phục vụ đọc. | Cập nhật gần thời gian thực, có thể eligible primary. | Ghi xóa nhầm thường nhanh chóng lan sang. |
| Priority-0 visible secondary | Secondary không được bầu primary nhưng vẫn đọc được. | Phục vụ đọc theo read preference. | Vẫn nhận tải ứng dụng; không cách ly như hidden. |
| Hidden secondary | Cách ly backup/report reads khỏi topology thông thường. | Bản sao cập nhật gần thời gian thực; không eligible primary. | Không phải bản sao lịch sử; vẫn có thể bị đọc trực tiếp, vẫn tốn tài nguyên. |
| Delayed hidden secondary | Giữ trạng thái cũ trong cửa sổ trễ. | Có thể cứu dữ liệu sau một số lỗi logic được phát hiện sớm. | Hết delay sẽ áp dụng lỗi; phụ thuộc oplog và recovery workflow. |
| Backup/PITR được hỗ trợ | Lưu nhiều điểm khôi phục theo chính sách. | Phục vụ khôi phục theo thời gian/retention, có thể offsite/immutable. | Cần storage, vận hành, chi phí và kiểm thử restore. |

**Không có một phương án tối ưu mọi mục tiêu.** Hidden có thể là nguồn tải backup, delayed có thể giúp phản ứng nhanh sau lỗi con người, còn backup độc lập là lớp bảo vệ dài hạn.

### 20.1. Sự khác nhau giữa RPO và RTO

- **RPO (Recovery Point Objective):** lượng dữ liệu có thể mất theo thời gian trước sự cố mà tổ chức chấp nhận.
- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận để khôi phục dịch vụ.

Một delayed member cấu hình 60 phút **không tự chứng minh RPO = 60 phút**: thực tế bạn có thể phải kết hợp với những ghi hợp lệ phát sinh sau mốc delayed, và việc khôi phục không nhất thiết diễn ra tức thì.

Ngược lại, một backup gần đây với PITR có thể giúp chọn mốc sát sự cố hơn, nhưng RTO phụ thuộc restore time và khối lượng dữ liệu.

### 20.2. Đúng bài toán nào mới đáng thêm delayed node?

Delayed member thường có ý nghĩa nếu:

- Hệ thống có nguy cơ đáng kể từ thao tác phá dữ liệu do người dùng/automation.
- Đội vận hành phát hiện lỗi đủ sớm trong khoảng delay.
- Oplog window, hạ tầng và ngân sách đủ.
- Có runbook cô lập, bảo toàn và khôi phục dữ liệu.
- Hệ thống không dựa vào delayed member để đạt quorum.

Nếu chỉ cần backup định kỳ với khả năng PITR, giải pháp backup tích hợp có thể phù hợp hơn về chi phí và độ phức tạp.

---

## 21. Bốn sự cố giả định và cách suy luận

### Sự cố A — Hidden member bị lỗi

Topology:

```text
P, S1, S2: votes=1
H: votes=0, priority=0, hidden=true
```

Nếu H offline:

- Replica set vẫn có ba voters bình thường.
- Election majority cơ bản không thay đổi do H vốn non-voting.
- Backup/report workload trên H không chạy được.
- Các node khác vẫn tiếp tục chịu tải theo kiến trúc bình thường.

**Kết luận:** H giúp cách ly tải, nhưng không cung cấp thêm một phiếu bảo vệ election.

### Sự cố B — Hidden voting member offline

Topology:

```text
P vote=1
S vote=1
H vote=1, priority=0, hidden=true
```

Nếu H offline, P và S còn hai phiếu trên ba và có thể duy trì majority. Nhưng nếu S sau đó cũng offline, chỉ còn P một phiếu, không có majority; primary có thể phải step down.

**Kết luận:** Hidden vẫn tác động quorum nếu `votes=1`.

### Sự cố C — Delayed voting thành điểm nghẽn

Topology:

```text
P vote=1
S vote=1
D vote=1, priority=0, hidden=true, delay=600
```

Khi S offline, chỉ P và D còn kết nối. Write `"majority"` có thể phải đợi D nhận và áp dụng operation theo delay, dẫn đến mức chờ dài. **MongoDB khuyến nghị delayed non-voting.**

Nếu thay D thành `votes=0`, thì phải bảo đảm một bộ voters khác tạo majority theo yêu cầu; non-voting D không sửa được topology vốn thiếu quorum.

### Sự cố D — Phát hiện xóa nhầm sau quá lâu

Node D cấu hình delay 30 phút. Lệnh delete sai xảy ra lúc 10:00 nhưng chỉ phát hiện lúc 11:00.

D có thể đã áp dụng delete từ 10:30. Không có cơ sở để kỳ vọng D vẫn còn dữ liệu cũ. Cần dùng backup/PITR hoặc phương án recovery khác.

**Kết luận:** Chọn delay phải dựa trên thời gian phát hiện và xử lý, đồng thời phải nhỏ hơn oplog window với margin.

---

## 22. Rủi ro hiệu năng và tài nguyên

Thêm một hidden/delayed member không chỉ tăng chi phí lưu trữ một bản dữ liệu:

1. **Replication network:** các thao tác phải được truyền tới hoặc đồng bộ qua nguồn tương ứng.
2. **CPU và disk:** node phải duy trì document, index và oplog.
3. **Initial sync:** thêm node mới có thể cần sao chép lượng dữ liệu rất lớn.
4. **Oplog retention:** delayed cần cửa sổ đủ dài, có thể đòi cấu hình storage lớn hơn.
5. **Backup/report workload:** trên hidden có thể cạnh tranh với replication và làm tăng lag.
6. **Quorum:** voting config sai có thể tăng rủi ro mất primary hoặc chậm acknowledgment.
7. **Giám sát/alert:** cần phân biệt lag có chủ đích với lag vì lỗi.
8. **Vận hành sự cố:** phải có quy trình bảo toàn delayed node trong cửa sổ khôi phục.

**Đừng xem hidden node là tài nguyên miễn phí vì không phục vụ request ứng dụng.** Nó vẫn phải đạt yêu cầu ổn định của một secondary.

### 22.1. Replica set vẫn cần capacity planning

Nếu primary và secondary đang gần mức bão hòa I/O, thêm node mới và initial sync có thể tạo thêm tải trên sync source. Nên thêm capacity **trước** khi hệ thống đạt ngưỡng quá tải, triển khai có giám sát và theo khung giờ phù hợp.

### 22.2. Hidden backup có thể gây lag

Một hidden secondary vừa đọc dữ liệu làm backup vừa phải apply oplog. Nếu backup chiếm phần lớn disk throughput, replication có thể tụt sau. Nếu vượt oplog window, node có thể trở thành stale. Cần giới hạn tốc độ backup hoặc tăng tài nguyên riêng cho node này.

---

## 23. Quan sát bằng Java MongoDB Driver

Trong Java Sync Driver, ứng dụng bình thường nên kết nối đến replica set theo topology chuẩn, không chỉ định hidden làm endpoint mặc định.

Ví dụ cấu hình đọc bình thường từ secondary:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class NormalReplicaSetConnection {
    public static MongoClient create() {
        ConnectionString connectionString = new ConnectionString(
            "mongodb://db1.example.net:27017," +
            "db2.example.net:27017," +
            "db3.example.net:27017/?replicaSet=rsCommerce"
        );

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(connectionString)
            .readPreference(ReadPreference.secondaryPreferred())
            .build();

        return MongoClients.create(settings);
    }
}
```

Đoạn này **không tự chọn hidden**, vì node hidden không được quảng bá trong topology thông thường.

### 23.1. Đường đọc trực tiếp dành riêng cho hidden

Ví dụ một backup/report job riêng (self-managed replica set):

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class HiddenReportConnection {
    public static MongoClient create() {
        ConnectionString connectionString = new ConnectionString(
            "mongodb://mongo-hidden.example.net:27017/" +
            "?directConnection=true"
        );

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(connectionString)
            .readPreference(ReadPreference.secondary())
            .build();

        return MongoClients.create(settings);
    }
}
```

Trong production, thêm TLS, authentication và các timeout phù hợp. Quản lý secrets bằng cơ chế secret management; không đưa mật khẩu vào source code. Connection trực tiếp này **không có khả năng tự chọn secondary khác qua topology** khi hidden node lỗi.

### 23.2. Không dùng delayed để đọc giao dịch thông thường

Một URI trực tiếp trỏ tới delayed node vẫn có thể mở và đọc trong tình huống nhất định, nhưng ứng dụng sẽ thấy dữ liệu cũ **theo chủ đích**, làm sai:

- Đọc đơn hàng ngay sau khi ghi.
- Hiển thị số dư/tồn kho hiện tại.
- Xác nhận trạng thái thanh toán.
- Các quy trình quyết định dựa trên dữ liệu mới nhất.

Delayed member chỉ nên được truy cập bởi runbook hoặc job chuyên dụng đã hiểu và chấp nhận staleness. Không nên đặt nó vào pool của service API chính.

---

## 24. Các giới hạn và ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Hidden không nằm trong replica set thật.” | Nó là secondary thật, vẫn sao chép và áp dụng replication. |
| “Hidden luôn là non-voting.” | Hidden có thể `votes: 1` hoặc `votes: 0`. |
| “Priority 0 có nghĩa không bỏ phiếu.” | Priority 0 không tự triệt tiêu quyền vote. |
| “Hidden vẫn được chọn bởi `secondaryPreferred`.” | Hidden bị ẩn khỏi topology khám phá thông thường; muốn đọc phải kết nối trực tiếp. |
| “Hidden không thể bị đọc từ bất kỳ đâu.” | Người có quyền vẫn có thể kết nối trực tiếp; không phải firewall. |
| “Hidden sẽ giữ dữ liệu cũ để cứu xóa nhầm.” | Hidden bình thường vẫn đồng bộ gần realtime; chỉ delayed tạo delay có chủ ý. |
| “Delayed có thể làm primary khi cần.” | Delayed yêu cầu `priority: 0`, không eligible primary. |
| “Delayed bắt buộc phải bỏ phiếu.” | Khuyến nghị `votes: 0`, tránh ảnh hưởng majority. |
| “Delayed voter không ảnh hưởng `w: "majority"`.” | Khi replica set suy giảm, majority acknowledgment có thể phải chờ delay. |
| “Delayed non-voter có thể giúp duy trì election quorum.” | Non-voting không góp phiếu. |
| “Delayed non-voter không bao giờ được tính vào numeric write concern.” | `w: <number>` có thể tính data-bearing non-voter. |
| “Có `secondaryDelaySecs: 3600` thì node luôn chính xác chậm 3600 giây.” | Lag thực còn phụ thuộc tình trạng replication, tải và sync source. |
| “Oplog đủ 1 giờ là an toàn cho delay 1 giờ.” | Cần lớn hơn delay và có margin cho tải đỉnh, sự cố và catch-up. |
| “Delayed là backup immutable.” | Thao tác xóa/sửa cũng sẽ được áp dụng sau delay. |
| “Delayed phục hồi được mọi thời điểm lịch sử.” | Nó không có khả năng PITR tùy ý như hệ backup chuyên dụng. |
| “Phát hiện lỗi sau delay vẫn cứu được trên delayed.” | Có thể node đã áp dụng thao tác lỗi. |
| “Direct read hidden shard thay thế `mongos`.” | Có thể sai metadata/nhất quán; MongoDB cảnh báo tránh. |
| “Cứ dùng `rs.reconfig(..., {force:true})` nếu cấu hình lỗi.” | Forced reconfig có thể gây mất dữ liệu và thay đổi topology nguy hiểm. |
| “Hidden backup không gây tác động hiệu năng nào.” | Nó vẫn tiêu thụ CPU, I/O, disk, replication và có thể lag. |
| “Atlas/managed cluster cho sửa `rs.conf()` tùy ý.” | Quyền và quy trình phụ thuộc service; dùng cơ chế hỗ trợ của nhà cung cấp. |
| “Node delayed là một trạng thái ngoài `SECONDARY`.” | Đây là cấu hình secondary; vẫn có runtime state tương ứng. |
| “Đã có replica set thì không cần backup.” | Replication sao chép cả thao tác xóa nhầm và lỗi logic. |

---

## 25. Bài tập vận dụng

### Bài 1 — Phân biệt hidden và delayed

Một node có:

```javascript
{
  priority: 0,
  hidden: true,
  votes: 0,
  secondaryDelaySecs: 0
}
```

**Hỏi:** Đây là hidden hay delayed? Có giữ được dữ liệu trước khi bị xóa nhầm một giờ không?

**Gợi ý:** Hidden non-voting, nhưng **không có delay có chủ ý**. Dữ liệu xóa nhầm sẽ được replicated thông thường.

### Bài 2 — Delayed có cấu hình phù hợp?

```javascript
{
  priority: 1,
  hidden: false,
  votes: 1,
  secondaryDelaySecs: 3600
}
```

**Hỏi:** Có nên áp dụng cấu hình này?

**Đáp án:** Không. Delayed phải `priority: 0`, `hidden: true`; nên đặt `votes: 0` để không ảnh hưởng `"majority"`.

### Bài 3 — Câu hỏi quorum

Replica set:

```text
P: vote=1, priority=1
S: vote=1, priority=1
H: vote=1, priority=0, hidden=true
```

**Hỏi:** Nếu S hỏng, H có thể trở thành primary không? H có thể giúp P có majority không?

**Gợi ý:** H không thể làm primary, nhưng nếu H còn kết nối và có phiếu, nó có thể góp vào majority.

### Bài 4 — Rủi ro write concern

Replica set gồm P, S và D đều có `votes: 1`; D chậm 15 phút. S hỏng.

**Hỏi:** Vì sao ghi với `w: "majority"` có thể chậm?

**Gợi ý:** Majority có thể cần P và D. D không áp dụng operation mới trước khoảng delay, nên acknowledgment bị trì hoãn.

### Bài 5 — Cửa sổ oplog

```text
Configured delay:       4 giờ
Oplog window peak load: 3 giờ
```

**Hỏi:** An toàn không?

**Đáp án:** Không. Oplog window nhỏ hơn configured delay, delayed member có nguy cơ không thể tiếp tục replicate và phải resync.

### Bài 6 — Cần cơ chế nào cho báo cáo?

Một secondary đặt ở data center xa, có phần cứng vừa phải, nhưng ứng dụng muốn đọc báo cáo định kỳ từ node này theo read preference.

**Hỏi:** Nên chọn visible priority-0 hay hidden?

**Gợi ý:** Nếu cần driver chọn node qua read preference thì visible priority-0 phù hợp hơn. Hidden phù hợp khi chỉ job kết nối trực tiếp được phép sử dụng.

### Bài 7 — Xóa nhầm dữ liệu

Delayed 1 giờ. Xóa nhầm lúc 10:00, phát hiện lúc 10:10.

**Hỏi:** Điều cần làm đầu tiên là gì?

**Gợi ý:** Kích hoạt runbook sự cố, xác định thao tác/khả năng còn dữ liệu, kịp thời bảo toàn delayed state trước lúc nó áp dụng delete, tạo snapshot/backup nhất quán, thử restore trên môi trường cách ly. Không tự ép delayed làm primary.

### Bài 8 — Cửa sổ ứng phó bị vượt

Delayed 30 phút, xóa nhầm lúc 10:00, phát hiện lúc 11:00.

**Hỏi:** Delayed có chắc còn dữ liệu cũ không?

**Đáp án:** Không, thao tác lỗi có thể đã được áp dụng. Cần backup/PITR khác.

### Bài 9 — Backup trên hidden có thật sự “zero impact”?

Một hidden backup node chỉ có đĩa chậm, trong lúc backup bulk, replication lag tăng từ 10 giây lên 35 phút.

**Hỏi:** Cần xem chỉ số gì?

**Gợi ý:** Disk latency/IOPS, CPU, oplog window, replication lag, backup throughput, khả năng catch up; và xem votes của hidden có ảnh hưởng majority hay không.

### Bài 10 — Sharded cluster

Balancer vừa chuyển một chunk giữa shard A và shard B; đội vận hành định khôi phục toàn cluster chỉ từ delayed member của shard A.

**Hỏi:** Vì sao kế hoạch này không đáng tin?

**Gợi ý:** Không có bảo đảm trạng thái chunk ownership và metadata nhất quán xuyên shard; phải dùng giải pháp backup/recovery hiểu sharding.

### Bài 11 — Kết nối Java

Ứng dụng dùng `ReadPreference.secondaryPreferred()` tới replica set ba nodes, và một hidden node có `priority: 0`.

**Hỏi:** Driver có tự định tuyến query tới hidden không?

**Đáp án:** Không. Hidden không được quảng bá cho đường chọn secondary thông thường; phải có direct connection riêng nếu thao tác đó được phép.

### Bài 12 — Numeric write concern

Delayed node có `votes: 0`, nhưng ứng dụng dùng numeric `w: 4` trong một topology có ba data-bearing nodes đồng bộ bình thường và một delayed data-bearing node.

**Hỏi:** Có thể bị ảnh hưởng bởi delay không?

**Gợi ý:** Có. Numeric `w` có thể tính data-bearing non-voter; nếu delayed là node thứ tư cần acknowledgment, thời gian xác nhận có thể chịu delay.

---

## 26. Checklist triển khai và vận hành

Trước khi thêm hoặc chỉnh hidden/delayed member:

1. **Mục đích:** backup, reporting, ngăn election hay giữ bản dữ liệu trễ?
2. **Phân loại vai trò:** chỉ cần priority 0 visible, hay cần hidden?
3. **Primary eligibility:** mọi hidden/delayed đã `priority: 0`?
4. **Votes:** đã phân tích quorum trước/sau? Delayed đã non-voting theo khuyến nghị?
5. **Write concern:** ứng dụng dùng majority, numeric `w`, timeout gì?
6. **Failover:** khi bất kỳ một hoặc hai voter hỏng, còn primary eligible và quorum không?
7. **Oplog window:** có đủ lớn hơn delay với biên cho peak load/outage?
8. **Initial sync:** hạ tầng chịu được việc thêm một data-bearing member mới không?
9. **Monitoring:** có phân biệt configured delay và excess lag?
10. **Network/security:** có tài khoản, TLS, firewall và quyền direct read phù hợp?
11. **Managed service:** thay đổi cấu hình có được nhà cung cấp hỗ trợ không?
12. **Backup:** đã có bản độc lập/immutable hoặc PITR và restore test?
13. **Incident response:** có runbook cô lập delayed node trước khi nó áp dụng thao tác xấu?
14. **Sharding:** có đang định dùng delayed để restore dữ liệu sau chunk migration không?
15. **Đọc ứng dụng:** các service có vô tình trỏ tới delayed node không?
16. **Backup resource usage:** hidden có đủ CPU, I/O, storage cho backup mà vẫn replicate?
17. **Change management:** reconfig có maintenance window, rollback plan, giám sát client disconnect?
18. **Kiểm tra sau thay đổi:** `rs.conf()`, `rs.status()`, replication info, các write/read smoke tests hợp lệ?
19. **Tài liệu vận hành:** ghi nhận host, role, owner, delay, votes, alert threshold, runbook.
20. **Diễn tập:** có thể khôi phục dữ liệu thật trong thời gian mục tiêu không?

Một sơ đồ chọn lựa:

```text
Muốn thêm một replica set member
              |
              v
Cần node có thể trở thành PRIMARY?
       |                    |
      Có                  Không
       |                    |
Normal eligible       priority: 0
secondary                 |
                          v
         Có muốn app chọn qua read preference?
                    |             |
                   Có           Không
                    |             |
             Visible           Hidden
             priority 0        priority 0
                                  |
                                  v
                   Cần giữ trạng thái trễ có chủ đích?
                             |          |
                            Không      Có
                             |          |
                          Hidden      Delayed
                          backup/     + hidden
                          reporting   + priority 0
                                      + votes 0 khuyến nghị
                                      + oplog window đủ dài
```

---

## 27. Tài liệu MongoDB chính thức

- [Hidden Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-hidden-member/): cách hidden được phát hiện, kết nối trực tiếp, voting và write concern.
- [Configure a Hidden Self-Managed Replica Set Member](https://www.mongodb.com/docs/manual/tutorial/configure-a-hidden-replica-set-member/): thủ tục thay đổi cấu hình với `rs.reconfig()`.
- [Delayed Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-delayed-member/): yêu cầu priority, hidden, votes, oplog và giới hạn sharding.
- [Configure a Delayed Self-Managed Replica Set Member](https://www.mongodb.com/docs/manual/tutorial/configure-a-delayed-replica-set-member/): `secondaryDelaySecs` và các điều kiện cấu hình.
- [Priority 0 Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-priority-0-member/): priority 0 khác hidden như thế nào.
- [Self-Managed Replica Set Configuration](https://www.mongodb.com/docs/manual/reference/replica-configuration/): `members[n].priority`, `votes`, `hidden`, `secondaryDelaySecs`.
- [Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/): voting majority và khả năng bầu primary.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): quy tắc numeric w và `"majority"` với các member đặc biệt.
- [Replication Lag Troubleshooting](https://www.mongodb.com/docs/manual/troubleshooting/replication-lag/): giám sát oplog window và replication lag.
- [Resync a Member of a Self-Managed Replica Set](https://www.mongodb.com/docs/manual/tutorial/resync-replica-set-member/): trường hợp stale và initial sync.
- [Replica Set Deployment Architectures](https://www.mongodb.com/docs/manual/core/replica-set-architectures/): mục tiêu backup, reporting, high availability.

Khi triển khai trên MongoDB mới hoặc managed service, cần đối chiếu tài liệu với phiên bản server, driver, FCV và topology thực tế. Một số ngữ nghĩa như acknowledgment majority cũng có thay đổi theo phiên bản, nên tránh dựa vào ví dụ cũ để suy luận chi tiết mọi thời điểm commit.

---

## 28. Kết luận

**Hidden member** là một secondary được ẩn khỏi đường đọc theo topology thông thường và luôn có `priority: 0`. Nó hữu ích để cách ly backup, reporting hoặc workload chuyên dụng. Hidden có thể **voting hoặc non-voting**, vẫn replicate và vẫn tiêu tốn tài nguyên; nó **không mặc định giữ dữ liệu quá khứ**.

**Delayed member** là secondary cố ý giữ trạng thái dữ liệu chậm hơn thông qua `secondaryDelaySecs`. Nó phải `priority: 0`, phải `hidden: true` và **nên `votes: 0`** để không gây hậu quả xấu cho majority write concern. Nó chỉ hữu ích cho cứu dữ liệu nếu lỗi được phát hiện và trạng thái cũ được bảo toàn **trước khi operation gây hại được áp dụng**; oplog window phải đủ dài.

Cả hai loại node đều là công cụ thiết kế replica set, không phải giải pháp toàn năng. Một hệ thống an toàn phải cân bằng **quorum/election**, **độ nhất quán**, **chi phí replication**, **khả năng khôi phục**, **security** và **backup/PITR độc lập**.

**Hidden giúp cách ly đường đọc; delayed giúp tạo cửa sổ phản ứng với lỗi. Không nên đánh đổi tính sẵn sàng của primary hoặc khả năng bảo toàn dữ liệu chỉ để có thêm một bản sao.**
