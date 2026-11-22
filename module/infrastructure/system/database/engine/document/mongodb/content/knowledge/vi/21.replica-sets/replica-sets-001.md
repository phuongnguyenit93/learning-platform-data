# Mục tiêu sao chép và cấu trúc primary, secondary trong MongoDB Replica Set

## Mục tiêu bài học

Một database chỉ chạy trên một máy chủ dễ trở thành **điểm lỗi duy nhất**: khi máy hỏng, ổ đĩa gặp sự cố, mạng gián đoạn hoặc tiến trình `mongod` dừng để bảo trì, ứng dụng có thể mất khả năng đọc/ghi. **MongoDB Replica Set** là nhóm các tiến trình MongoDB phối hợp duy trì bản sao của cùng một tập dữ liệu và bầu ra một thành viên **primary** để phục vụ ghi. Những thành viên lưu dữ liệu khác thường là **secondary**, sao chép thay đổi từ oplog và có thể trở thành primary khi điều kiện bầu cử cho phép.

Bài học thuộc chủ đề **Database Engine Document MongoDB**, chương **Replica set** và tập trung trực tiếp vào **mục tiêu sao chép, cấu trúc primary, secondary** cùng những hệ quả quan trọng đối với thiết kế ứng dụng.

Sau bài học, người học có thể:

1. Giải thích replication khác sharding, backup, disaster recovery và journaling thế nào.
2. Nêu mục tiêu high availability, data redundancy, durability, failover, maintenance và đọc trên secondary.
3. Vẽ kiến trúc một primary và nhiều secondary, phân biệt vai trò từng thành viên.
4. Giải thích primary xử lý ghi, secondary theo oplog và vì sao replication có độ trễ.
5. Hiểu nguyên tắc majority voting, bầu cử primary và những khoảng gián đoạn khi failover.
6. So sánh replica set ba data-bearing members **P-S-S** với **P-S-Arbiter**.
7. Biết các tùy chọn priority, votes, hidden, delayed, non-voting member ở mức kiến trúc.
8. Phân biệt read preference, read concern và write concern, nhất là `w:1` với `w:"majority"`.
9. Hiểu khi nào ghi có thể bị rollback và tại sao replication không thay thế backup.
10. Thực hành với `rs.initiate()`, `rs.status()`, `rs.conf()`, `db.hello()`, connection string và Java Driver.
11. Đề xuất topology phù hợp với các failure domains, kiểm soát replication lag và vận hành an toàn.

> **Ghi nhớ:** Có nhiều bản sao không đồng nghĩa các bản sao cập nhật tức thì. Có đủ **phiếu bầu** để có primary không đồng nghĩa có đủ **bản sao dữ liệu** để xác nhận ghi majority. Replica set làm tăng khả năng chịu lỗi, nhưng không thay thế bản backup có thể khôi phục độc lập.

---

## 1. Replica Set là gì?

Một **replica set** là một nhóm `mongod` duy trì cùng **dataset logic**. Trong cấu trúc thông dụng, một member giữ vai trò **PRIMARY**, còn những data-bearing members khác giữ vai trò **SECONDARY**.

~~~text
                         REPLICA SET rs0

                   +-----------------------+
Client ghi -------->| PRIMARY mongo1:27017  |
                    | Dữ liệu + index       |
                    | Oplog                 |
                    +-----------+-----------+
                                |
                   Sao chép bất đồng bộ
                         /            \
                        v              v
          +--------------------+  +--------------------+
          | SECONDARY mongo2   |  | SECONDARY mongo3   |
          | Dữ liệu + index    |  | Dữ liệu + index    |
          | Oplog              |  | Oplog              |
          +--------------------+  +--------------------+
~~~

Mục tiêu của các members là giữ cùng bộ dữ liệu khi đã bắt kịp. Ứng dụng không phải tự ghi riêng cùng một đơn hàng lên ba máy. Driver biết cấu hình replica set, gửi ghi đến primary và tùy chính sách có thể đọc primary hoặc secondary.

### 1.1. Thuật ngữ cơ bản

| Thuật ngữ | Ý nghĩa |
|---|---|
| `mongod` | Tiến trình MongoDB database server |
| Replica set | Nhóm MongoDB members lưu bản sao và tham gia quản lý primary |
| Primary | Member được bầu để chấp nhận ghi thông thường |
| Secondary | Data-bearing member sao chép và áp dụng dữ liệu từ replication source |
| Data-bearing member | Member có dữ liệu người dùng và index |
| Arbiter | Member bỏ phiếu nhưng **không chứa dữ liệu người dùng** |
| Oplog | Log thao tác có thứ tự để sao chép |
| Election | Quá trình bầu primary |
| Majority | Đa số phiếu, áp dụng trong election và các quy tắc xác nhận phù hợp |
| Replication lag | Khoảng cách tiến độ sao chép giữa các member |
| Write concern | Mức xác nhận ghi mà client yêu cầu |
| Read preference | Quy tắc chọn member đọc |
| Read concern | Mức đảm bảo về dữ liệu được đọc |
| Failover | Chuyển sang primary mới khi primary hiện tại không khả dụng |
| Rollback | Loại bỏ/reconcile những thao tác không thuộc lịch sử được chấp nhận khi thành viên tái hòa nhập |

### 1.2. Replica Set không phải cách chia dữ liệu thành ba phần

Nếu:

~~~text
Server A chứa khách miền Bắc
Server B chứa khách miền Nam
Server C chứa khách miền Trung
~~~

thì mỗi máy đang chứa một nhóm **khác** nhau. Đó không phải mô hình replication của cùng một dataset.

Với replica set:

~~~text
Mongo1: orders + users + inventory (bản sao 1)
Mongo2: orders + users + inventory (bản sao 2)
Mongo3: orders + users + inventory (bản sao 3)
~~~

Các bản sao có thể khác nhau tạm thời vì replication lag, nhưng mục tiêu là đồng bộ cùng một lịch sử được chấp nhận.

Nếu cần **phân tán dữ liệu** theo nhiều shards để mở rộng dung lượng và throughput, MongoDB sử dụng **sharding**. Mỗi shard thường có replica set riêng để có dự phòng. Hai cơ chế bổ sung cho nhau, nhưng không đồng nghĩa.

---

## 2. Mục tiêu thứ nhất: High Availability

### 2.1. Một server đơn lẻ tạo điểm lỗi duy nhất

~~~text
App -> MongoDB duy nhất -> hỏng máy -> ứng dụng mất đường truy cập
~~~

Với replica set ba voting data-bearing members:

~~~text
App -> rs0
         |
         +-- Primary lỗi
         |
         +-- Hai secondary còn hoạt động, có đủ majority votes
         |
         +-- Election: một secondary thành primary mới
         |
         +-- Official driver nhận biết topology và định tuyến ghi
~~~

Đây là cơ chế **automatic failover** trong các điều kiện election phù hợp.

### 2.2. High Availability không phải zero downtime

Trong thời gian primary bị lỗi và primary mới chưa được bầu:

- Ghi có thể chờ hoặc thất bại tạm thời.
- Một số đọc phụ thuộc primary cũng có thể bị gián đoạn.
- Những operation đang thực hiện có thể nhận lỗi network hoặc not-primary.
- Driver cần phát hiện topology mới.
- Ứng dụng cần timeout/retry policy hợp lý.

Không được hứa một giá trị RTO cố định chỉ vì đã tạo replica set. Thời gian chuyển đổi phụ thuộc failure type, heartbeat/election settings, network, member state, data freshness và ứng dụng.

### 2.3. Khả năng bảo trì từng nút

Replica set giúp tổ chức bảo trì theo từng member:

- Thay disk/VM cho một secondary.
- Nâng cấp rolling theo hướng dẫn phiên bản.
- Kiểm tra backup từ member phù hợp.
- Chuyển primary có kiểm soát nếu cần.
- Khôi phục một member từ initial sync.

Nhưng **không** có nghĩa có thể dừng tùy ý hai trong ba voting nodes mà vẫn tiếp tục ghi. Phải tính majority và mức an toàn của dữ liệu trước khi thao tác.

---

## 3. Mục tiêu thứ hai: Data Redundancy và Durability

### 3.1. Có nhiều bản sao vật lý

Khi các member nằm trên các máy và failure domains độc lập, lỗi disk/host của một member không tự làm mất toàn bộ dữ liệu.

Ví dụ tốt hơn một máy duy nhất:

~~~text
Availability Zone A         Zone B             Zone C
     mongo1                  mongo2             mongo3
     data                    data               data
     vote 1                  vote 1             vote 1
~~~

Nếu một zone có vấn đề, hai zone còn lại có thể tiếp tục tạo quorum và giữ hai bản sao dữ liệu trong một P-S-S thông thường.

### 3.2. Ba `mongod` trên cùng host chỉ là lab

~~~text
Một VM:
  mongod :27101
  mongod :27102
  mongod :27103
~~~

Cấu hình trên có thể học replication/election, nhưng **VM lỗi thì cả ba ngừng**. Nó không tạo high availability trước lỗi host, nguồn điện hoặc shared storage.

### 3.3. Durability cần kết hợp write concern

Replication cung cấp các bản sao, còn **write concern** định nghĩa client đợi được xác nhận đến mức nào.

Ghi với `w:1`:

~~~javascript
db.orders.insertOne(
  { _id: "O-101", status: "PAID" },
  {
    writeConcern: {
      w: 1
    }
  }
);
~~~

Ghi với `w:"majority"`:

~~~javascript
db.orders.insertOne(
  { _id: "O-102", status: "PAID" },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

`w:1` yêu cầu primary xác nhận nhưng không chứng minh thao tác đã đến secondary. `w:"majority"` đòi majority acknowledgment theo quy tắc replica set, nâng mức bảo vệ trước một số tình huống rollback/failover.

Điều đó **không** có nghĩa mọi member đều đã nhận thao tác, cũng không bảo đảm mọi loại thảm họa đều không thể gây mất dữ liệu.

### 3.4. Replication không thay backup

Một thao tác sai:

~~~javascript
db.orders.deleteMany({});
~~~

nếu được primary chấp nhận, có thể được sao chép tới secondary. Tất cả những bản sao đều có thể chịu hậu quả.

Vì vậy, cần **backup/PITR** với khả năng khôi phục theo thời điểm, kiểm soát quyền, giữ bản sao tách biệt và kiểm thử restore. Replica set giúp chịu lỗi node; backup phục vụ khôi phục khi dữ liệu bị xóa/ghi đè/corrupt hoặc xảy ra thảm họa rộng hơn.

---

## 4. Mục tiêu thứ ba: Read Scalability khi thích hợp

Có thể dùng secondary cho một số read workloads khi ứng dụng chấp nhận đọc dữ liệu hơi cũ.

Ví dụ:

- Báo cáo lịch sử theo ngày.
- Dashboard gần thời gian thực có độ trễ chấp nhận được.
- Query phân tích có thể chạy trên member dành riêng nếu cấu hình cho phép.

Nhưng những giới hạn gồm:

1. Replication bất đồng bộ; secondary có thể chưa áp dụng write mới.
2. Đọc nặng có thể tranh CPU/RAM/disk với việc apply oplog.
3. Không phải mọi secondary đều được driver chọn (hidden members là ví dụ).
4. Một read preference không tự tạo bảo đảm consistency.
5. Một số nghiệp vụ như thanh toán, số dư và quyết định tồn kho cần dữ liệu mới hơn.
6. Đọc trên secondary có thể rẻ hơn cho primary nhưng tăng tổng tài nguyên cả cụm.

**Kết luận:** Replica set chủ yếu nhằm **redundancy và availability**; secondary reads là khả năng có điều kiện, không phải một cam kết scale-out vô hạn.

---

## 5. PRIMARY là gì?

Primary là data-bearing member được bầu giữ vai trò writable. Trong cấu hình thường, một replica set có **một primary hiện tại**.

### 5.1. Trách nhiệm của primary

- Chấp nhận các thao tác insert/update/delete thông thường.
- Áp dụng thay đổi vào dữ liệu và index của mình.
- Ghi thông tin thay đổi vào oplog để replica set sao chép.
- Hỗ trợ các thao tác đọc theo read preference.
- Cung cấp trạng thái tiến độ sao chép cho cơ chế replication.
- Tham gia heartbeat, election và phối hợp với members khác.

Ví dụ ghi:

~~~javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  {
    $set: {
      available: 20
    }
  }
);
~~~

Ứng dụng ghi thông qua URI replica set sẽ được driver định tuyến đến primary được phát hiện, không tự gọi mọi secondary.

### 5.2. Primary cũng lưu dữ liệu

Primary không phải router không có storage. Nó có collection, index, journal/storage engine và oplog như một data-bearing member.

~~~text
Ứng dụng ghi
     |
     v
   PRIMARY
     |
     +--> Dữ liệu/index của chính primary
     |
     +--> Oplog phục vụ sao chép
     |
     +--> Thông tin tiến độ write concern
                 |
        Secondary tiếp tục theo kịp
~~~

Đây là mô hình khái niệm, không phải sơ đồ thứ tự I/O tuyệt đối cho mọi phiên bản.

### 5.3. Không hard-code primary

Đừng giả định:

~~~text
mongo1 luôn là primary vì lúc khởi tạo nó là primary.
~~~

Một election có thể khiến mongo2 hay mongo3 làm primary. `priority` chỉ ảnh hưởng mức ưu tiên bầu cử, không phải một “khóa cố định” trên vai trò.

Ứng dụng nên sử dụng URI nhiều hosts:

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rsLearn
~~~

Driver sẽ thực hiện discovery/monitoring topology.

---

## 6. SECONDARY là gì?

Secondary là data-bearing member giữ bản sao của cùng dataset và tiếp tục áp dụng các thao tác replication.

### 6.1. Secondary làm gì?

- Nhận thông tin thay đổi từ sync source.
- Đọc và áp dụng các mục oplog cần thiết.
- Duy trì collections và indexes tương ứng.
- Công bố tiến độ replication.
- Có thể phục vụ read theo read preference và cấu hình.
- Có thể là ứng viên bầu primary nếu đủ điều kiện.
- Phục vụ các mục đích backup/reporting chuyên biệt trong phạm vi an toàn.

### 6.2. Secondary không phải bản sao tức thời

Ví dụ:

~~~text
12:00:00.100
PRIMARY:   order O-101.status = PAID
SECONDARY: order O-101.status = NEW

12:00:00.700
SECONDARY đã apply thay đổi:
  order O-101.status = PAID
~~~

Trong khoảng chênh lệch, read trên secondary có thể trả dữ liệu cũ. Đây là **replication lag**, không nhất thiết là một lỗi.

### 6.3. Secondary có thể làm primary mới

Một secondary muốn trở thành primary cần đáp ứng điều kiện election, như:

- Có quyền bỏ phiếu và priority phù hợp.
- Có trạng thái/tiến độ dữ liệu đáp ứng quy tắc.
- Nhận đủ majority votes.
- Đáp ứng các điều kiện election term, mạng và cấu hình.

Một thành viên `priority:0` vẫn là secondary lưu dữ liệu bình thường, nhưng **không đủ điều kiện được bầu primary**.

### 6.4. Secondary có thể nhận oplog từ secondary khác

Sơ đồ cơ bản thường vẽ primary phát trực tiếp tới mọi secondary. Trong thực tế, secondary có thể chọn **sync source** phù hợp khác, bao gồm một secondary khác theo quy tắc replication. Topology sao chép không bắt buộc là một hình sao cố định.

---

## 7. Oplog: cơ chế kết nối primary với secondary

### 7.1. Oplog là gì?

**Oplog** (operations log) là một log theo thứ tự các thao tác được sao chép. Trong replica set, nó được lưu tại:

~~~text
local.oplog.rs
~~~

Đây là collection nội bộ đặc biệt có tính rolling/capped theo cơ chế MongoDB, với giới hạn lưu trữ và lịch sử.

Luồng khái niệm:

~~~text
1. Client gửi write tới primary.
2. Primary xử lý write theo semantics MongoDB.
3. Thao tác được ghi vào lịch sử oplog.
4. Secondary lấy các oplog entries từ sync source.
5. Secondary áp dụng thay đổi theo thứ tự phù hợp.
6. Secondary cập nhật optime/tiến độ.
7. Majority confirmation phụ thuộc tiến độ các member phù hợp.
~~~

Không hiểu bước 3 đến 7 là một transaction toàn cụm ngay lập tức: **replication là bất đồng bộ**.

### 7.2. Oplog không phải journal

| Thành phần | Mục đích |
|---|---|
| Oplog | Sao chép những thay đổi giữa replica set members |
| Journal | Hỗ trợ durability và khôi phục local storage engine |
| Backup | Giữ dữ liệu có thể phục hồi độc lập theo chính sách |
| Change streams | API theo dõi thay đổi cho ứng dụng dựa trên cơ chế của MongoDB |
| Application audit log | Ghi nhận hoạt động người dùng/nghiệp vụ theo chính sách riêng |

### 7.3. Đọc oplog trong lab

~~~javascript
db.getSiblingDB("local")
  .getCollection("oplog.rs")
  .find({})
  .sort({ $natural: -1 })
  .limit(5);
~~~

Lệnh có thể cần quyền phù hợp. **Không chỉnh sửa hoặc xóa trực tiếp `local.oplog.rs`.** Đây là dữ liệu hệ thống rất quan trọng.

### 7.4. Oplog window

Giả sử workload hiện tại làm oplog chỉ giữ được lịch sử cần sao chép trong khoảng 10 giờ. Một secondary offline 24 giờ có thể không tìm đủ oplog entries để bắt kịp. Nó có thể phải thực hiện **initial sync** lại hoặc quy trình phục hồi khác.

Oplog window phụ thuộc vào:

- Kích thước oplog.
- Khối lượng và tốc độ ghi.
- Kích thước/thể loại operations.
- Cấu hình retention và phiên bản.
- Tình trạng mạng/replication lag.

Không chỉ giám sát “node có online không”; phải giám sát **lag so với khả năng giữ lịch sử oplog**.

---

## 8. Initial Sync và Steady-State Replication

### 8.1. Initial sync

Một secondary mới, chưa có dữ liệu phù hợp, cần **initial synchronization**. Ở mức khái niệm:

1. Chọn sync source phù hợp.
2. Lấy bản sao dữ liệu/indexes cần thiết.
3. Thu thập những thay đổi xảy ra trong lúc copy.
4. Apply những oplog entries để bắt kịp.
5. Trở thành SECONDARY khi hoàn thành và đủ điều kiện.

Chi tiết triển khai và các trạng thái phụ thuộc server version.

### 8.2. Steady state

Sau initial sync, secondary tiếp tục sao chép từ oplog để giữ bản sao theo kịp.

~~~text
Initial sync:
  Tạo bản sao dữ liệu ban đầu + bắt kịp lịch sử thay đổi.

Steady state:
  Duy trì bản sao liên tục khi primary có write mới.
~~~

### 8.3. Vì sao ping thành công chưa đủ?

Một member có thể mở TCP port nhưng đang STARTUP2, RECOVERING hoặc rollback. Không được suy rằng port mở tức là secondary đã sẵn sàng phục vụ read bình thường.

Hãy kiểm tra `rs.status()` và driver topology; theo dõi các tiến trình initial sync, lag và health.

---

## 9. Bầu cử primary bằng Majority Voting

### 9.1. Công thức majority

Nếu replica set có `V` voting members, số phiếu majority là:

\[
\mathrm{majorityVotes}=\left\lfloor\frac{V}{2}\right\rfloor+1
\]

| Voting members | Majority cần |
|---:|---:|
| 1 | 1 |
| 2 | 2 |
| 3 | 2 |
| 4 | 3 |
| 5 | 3 |
| 6 | 4 |
| 7 | 4 |

MongoDB replica set có giới hạn số thành viên và số voting members (thông thường tối đa 7 voting members, dù tổng thành viên có thể lớn hơn). Giới hạn chính xác cần đối chiếu tài liệu version nếu thiết kế topology lớn.

### 9.2. Quy trình election khái niệm

~~~text
PRIMARY bị mất khả dụng / mất điều kiện làm primary
                     |
                     v
Các members quan sát qua heartbeat/topology
                     |
                     v
Secondary đủ điều kiện khởi động election
                     |
                     v
            Có đủ majority votes?
                   /       \
                 Có        Không
                  |          |
                  v          v
          PRIMARY mới      Không thể bầu
                  |          primary hợp lệ
                  v
          Driver phát hiện và chuyển hướng ghi
~~~

Còn nhiều điều kiện kỹ thuật khác: term, độ mới của dữ liệu, priority, trạng thái node, network và replica set protocol. Sơ đồ này giúp hiểu mục đích quorum, không phải mô phỏng đầy đủ thuật toán.

### 9.3. Vì sao 3 voting nodes tiện hơn 2?

- Với **2 voters**, majority = 2. Mất một node không đủ phiếu.
- Với **3 voters**, majority = 2. Mất một node vẫn có thể đủ phiếu.
- Với **4 voters**, majority = 3. Mất hai nodes không đủ phiếu.
- Với **5 voters**, majority = 3. Mất hai nodes vẫn có thể đủ phiếu.

Do đó triển khai số phiếu lẻ như 3 hoặc 5 thường tránh thêm một voter chẵn mà không tăng khả năng chịu lỗi tương ứng. Nhưng lựa chọn cuối còn phụ thuộc placement, costs, read/write concerns và failure domains.

### 9.4. Một member còn dữ liệu vẫn có thể không ghi được

Nếu P-S-S ba phiếu bị mất hai members, node còn sống chỉ có 1/3 phiếu. Nó có thể giữ một bản sao dữ liệu tốt nhưng **không có quorum để làm primary**. Đây là đánh đổi phục vụ tính nhất quán của lịch sử bầu cử.

Không tự force reconfig trong sự cố mạng để tạo thêm primary khi chưa hiểu hậu quả phân kỳ dữ liệu.

---

## 10. Cấu trúc P-S-S: mô hình ba bản sao dữ liệu

### 10.1. Sơ đồ

~~~text
                  P-S-S — rs0

                PRIMARY P
                data + oplog
                votes = 1
                  /    \
                 v      v
        SECONDARY S1    SECONDARY S2
        data + oplog    data + oplog
        votes = 1       votes = 1
~~~

Có ba data-bearing members và, nếu cả ba votes=1, ba voting members. Majority election = 2/3.

### 10.2. Khi primary lỗi

Giả sử P chết, S1 + S2 còn khỏe:

- Hai secondary có đủ 2 phiếu.
- Một ứng viên phù hợp có thể làm primary mới.
- Ứng dụng có thể tạm mất đường ghi trong lúc election.
- Dữ liệu vẫn tồn tại ở S1 và S2.
- Trong điều kiện hai member data-bearing theo kịp, majority writes có thể được xác nhận.

### 10.3. Khi một secondary lỗi

P + S1 còn:

- Hai phiếu còn online, đủ majority.
- Primary có thể tiếp tục phục vụ.
- Vẫn có hai bản sao dữ liệu đang hoạt động.
- `w:"majority"` có thể được xác nhận nếu cả hai data-bearing members đạt tiến độ.
- Hệ thống đang ở trạng thái giảm dự phòng; thêm một lỗi voting node có thể làm mất quorum.

### 10.4. Khi hai voting nodes lỗi

Chỉ còn một member:

- Không có majority 2/3.
- Không thể bầu primary mới hợp lệ với config hiện tại.
- Đường ghi có thể không khả dụng.
- Có một bản sao dữ liệu không đồng nghĩa có quyền nhận ghi.

### 10.5. Ưu điểm và chi phí

**Ưu điểm:** redundancy mạnh hơn P-S-A, dễ bố trí rolling maintenance, khả năng chịu lỗi một voting node và có hai bản sao dữ liệu sau lỗi một node.

**Chi phí:** ba lần lưu trữ dataset/index, network replication, CPU/disk I/O sao chép, giám sát và bảo mật trên cả ba, write concern latency theo topology.

---

## 11. Cấu trúc P-S-Arbiter: phiếu bầu khác bản sao dữ liệu

### 11.1. Arbiter làm gì?

**Arbiter** là thành viên có thể bỏ phiếu trong election nhưng **không lưu dữ liệu người dùng** và không thể phục vụ read/write dữ liệu ứng dụng.

~~~text
            P-S-A

        PRIMARY P         SECONDARY S
        data + oplog  --> data + oplog
        1 vote            1 vote

                  ARBITER A
                  no user data
                  1 vote
~~~

Ba voting members → majority election = 2, nhưng chỉ có **hai data-bearing members**.

### 11.2. Arbiter không thể thay secondary

Arbiter:

- Có thể góp phiếu bầu.
- Không áp dụng oplog để giữ bản sao dữ liệu người dùng.
- Không phục vụ secondary reads.
- Không thể được bầu làm primary.
- Không thể khôi phục dữ liệu từ một bản sao không tồn tại.
- Không thể xác nhận dữ liệu đã được replicate thay cho data-bearing member.

### 11.3. Secondary hỏng, primary + arbiter còn

~~~text
S down
P còn data + 1 vote
A còn 1 vote
=> P + A có 2/3 phiếu.
=> Có thể vẫn có primary hợp lệ.

Nhưng chỉ P lưu dữ liệu.
=> Không thể coi A là một bản sao để đáp ứng
   w:"majority" cho dữ liệu ghi.
~~~

Trong P-S-A, khi chỉ một data-bearing member hoạt động, những ghi yêu cầu `w:"majority"` có thể chờ và trả write concern timeout. Đây là ví dụ quan trọng của việc **đủ election quorum nhưng không đủ data replication acknowledgments**.

### 11.4. Primary hỏng, secondary + arbiter còn

- S + A có 2/3 phiếu.
- S có thể được bầu thành primary nếu đủ điều kiện.
- Chỉ một data-bearing member còn hoạt động.
- Vẫn có vấn đề tương tự với majority write concern.

### 11.5. Tại sao thường ưu tiên P-S-S?

Nếu có điều kiện hạ tầng, P-S-S với ba data-bearing voting members là lựa chọn thường phù hợp hơn cho production cần data redundancy và durability. P-S-A có thể xuất hiện khi bị giới hạn tài nguyên, nhưng **không tương đương** về độ an toàn chỉ vì cũng có ba voting nodes.

| Tiêu chí | P-S-S | P-S-A |
|---|---|---|
| Tổng members | 3 | 3 |
| Data-bearing members | **3** | **2** |
| Voting members | 3 | 3 |
| Majority election | 2 | 2 |
| Có arbiter | Không | Có |
| Số data copies sau khi mất một data node | 2 | 1 |
| Majority write khi còn một data-bearing member | Không xảy ra sau chỉ một lỗi data node trong P-S-S ba data nodes | Có thể không đáp ứng dù P+A đủ phiếu |
| Đọc từ secondary | Có thể có hai candidates | Chỉ một secondary khi bình thường |
| Chi phí storage | Cao hơn | Thấp hơn |
| Mức độ bảo vệ dữ liệu | Tốt hơn trong cấu hình so sánh này | Có đánh đổi đáng kể |

Không phải mọi lỗi đều có cùng kết quả, nhưng bảng chỉ ra lý do cần thiết kế theo **số bản sao thật**, không chỉ số thành viên.

---

## 12. Những thành viên có cấu hình đặc biệt

### 12.1. `priority`

Ví dụ thành viên:

~~~javascript
{
  _id: 2,
  host: "mongo3:27017",
  priority: 0
}
~~~

`priority: 0`: member **không thể được bầu làm primary**, nhưng vẫn có thể là secondary sao chép dữ liệu bình thường.

Priority 2 không tương đương hai phiếu. Priority chỉ ảnh hưởng ưu tiên khi bầu, không đảm bảo node đó luôn trở thành primary.

### 12.2. `votes`

~~~javascript
{
  _id: 3,
  host: "mongo4:27017",
  votes: 0,
  priority: 0
}
~~~

`votes: 0`: member không góp phiếu bầu và không được làm primary. Nó vẫn có thể chứa dữ liệu nếu là secondary bình thường. Nó không được tính như một voting member khi xét election majority.

### 12.3. Hidden secondary

~~~javascript
{
  _id: 2,
  host: "mongo3:27017",
  hidden: true,
  priority: 0
}
~~~

Hidden secondary:

- Có dữ liệu và sao chép.
- Không trở thành primary.
- Không được chọn như secondary thông thường bởi driver server selection.
- Có thể có quyền bỏ phiếu tùy cấu hình.
- Có thể phù hợp cho tác vụ quản trị/backup chuyên biệt với kết nối trực tiếp đúng cách.

**Hidden không đồng nghĩa không có chi phí storage/index maintenance.**

### 12.4. Delayed secondary

Một secondary có thể cố ý chậm áp dụng operations theo cấu hình `secondaryDelaySecs` trong phiên bản hỗ trợ. Mục đích có thể tạo khoảng thời gian phát hiện thao tác nhầm trước khi nó xuất hiện trên delayed copy.

Nhưng:

- Sau delay, thay đổi xấu vẫn có thể được sao chép.
- Nó không phải immutable backup hoặc PITR.
- Cần tính oplog window và khoảng delay.
- Delayed secondary được cấu hình không thể làm primary và theo khuyến nghị cần bố trí hidden/votes phù hợp.
- Lag cố ý phải được phân biệt với lag bất thường.

### 12.5. Bảng so sánh

| Loại | Chứa user data? | Có thể primary? | Có thể vote? | Đọc bình thường qua driver? |
|---|---|---|---|---|
| Primary | Có | Đang là primary | Thường có | Có |
| Secondary thường | Có | Nếu đủ điều kiện | Có thể | Có với readPreference phù hợp |
| Priority 0 secondary | Có | **Không** | Có thể | Có nếu không hidden và được chọn |
| Hidden secondary | Có | **Không** | Có thể | Không như secondary thông thường |
| Delayed secondary | Có | Không theo cấu hình thích hợp | Tùy cấu hình | Không thích hợp cho đọc cần dữ liệu mới |
| Non-voting secondary | Có | **Không** | **Không** | Có thể tùy cấu hình |
| Arbiter | **Không** | **Không** | **Có** | **Không** |

Các thuộc tính có ràng buộc cụ thể khi kết hợp. Không tự tạo mọi tổ hợp được tưởng tượng từ bảng.

---

## 13. Member states và cách nhận biết

Trong `rs.status()` có thể thấy các trạng thái:

| State | Ý nghĩa ngắn |
|---|---|
| `STARTUP` | Vừa khởi động |
| `STARTUP2` | Giai đoạn khởi tạo/initial sync trong trường hợp phù hợp |
| `RECOVERING` | Đang hồi phục hoặc chưa thể phục vụ như secondary bình thường |
| `PRIMARY` | Đang được bầu làm primary |
| `SECONDARY` | Đang phục vụ vai trò secondary |
| `ARBITER` | Thành viên bỏ phiếu, không có user data |
| `DOWN` | Bị quan sát không liên lạc được |
| `UNKNOWN` | Không rõ trạng thái |
| `ROLLBACK` | Đang xử lý rollback |
| `REMOVED` | Không thuộc cấu hình replica set hiện tại |

**State khác config.** Một node có `priority: 2` vẫn có thể hiện state SECONDARY; một node state SECONDARY không có nghĩa bị cấu hình priority 0.

Không dựa vào ping TCP/`health:1` duy nhất để kết luận replication lag bằng 0.

---

## 14. Đọc dữ liệu: Read Preference và Read Concern

### 14.1. Read preference trả lời “đọc ở đâu?”

| Mode | Quy tắc tổng quát |
|---|---|
| `primary` | Chỉ đọc primary; mặc định phổ biến |
| `primaryPreferred` | Ưu tiên primary, có thể fallback secondary |
| `secondary` | Chỉ đọc secondary đủ điều kiện |
| `secondaryPreferred` | Ưu tiên secondary, có thể fallback primary |
| `nearest` | Chọn member phù hợp độ trễ, có thể là primary hoặc secondary |

Ví dụ URI:

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rsLearn&readPreference=secondaryPreferred
~~~

Không có nghĩa mọi lần đọc sẽ được phục vụ secondary: `secondaryPreferred` có thể fallback primary.

### 14.2. Read concern trả lời “đọc với bảo đảm gì?”

| Read concern | Ý tưởng |
|---|---|
| `local` | Dữ liệu tại member đọc, không yêu cầu majority commit |
| `majority` | Dữ liệu ở mức majority committed theo semantics server |
| `linearizable` | Mức bảo đảm mạnh cho một số đọc trên primary theo điều kiện riêng |
| `snapshot` | Snapshot nhất quán trong những ngữ cảnh được hỗ trợ |

Read preference và read concern là hai lựa chọn **độc lập**.

Ví dụ:

~~~text
readPreference: secondary
readConcern: majority
~~~

có thể đọc dữ liệu majority-committed từ một secondary nhưng **secondary vẫn có thể chậm hơn primary**. Majority read trên secondary không tự đảm bảo đọc chính xác thao tác mới nhất ngay thời điểm query.

### 14.3. Khi nào được đọc secondary?

Ví dụ có thể chấp nhận:

- Dashboard doanh thu ngày hôm trước.
- Tra cứu dữ liệu lịch sử cho mục đích thống kê.
- Báo cáo nội bộ có SLA chấp nhận chậm vài giây.

Ví dụ cần cân nhắc consistency kỹ:

- Số dư ngân sách ngay sau giao dịch.
- Kiểm tra trạng thái vừa thanh toán.
- Quyết định xuất kho sau một cập nhật tồn kho.
- Luồng cần read-your-writes hoặc causal consistency.

**Read preference không thay thế thiết kế consistency.** Official driver có sessions và các cơ chế khác để hỗ trợ bảo đảm mạnh hơn khi cấu hình đúng.

### 14.4. maxStalenessSeconds

Một số driver cho cấu hình `maxStalenessSeconds` để loại các secondary được đánh giá quá stale ra khỏi danh sách ứng viên đọc. Nhưng đây không phải hợp đồng “dữ liệu luôn mới dưới N giây” chính xác, và chịu giới hạn/thuật toán server selection của driver.

Không dùng thông số này để thay thế read concern phù hợp.

---

## 15. Write Concern: w:1, majority và timeout

### 15.1. `w:1` chỉ đợi primary

~~~javascript
db.orders.insertOne(
  { _id: "ORDER-W1", amount: 500 },
  {
    writeConcern: {
      w: 1
    }
  }
);
~~~

Nếu primary ack trước khi secondary nhận, rồi primary mất khả dụng, thao tác có thể nằm ngoài lịch sử đã được majority chấp nhận và có nguy cơ rollback.

### 15.2. `w:"majority"` đợi mức xác nhận lớn hơn

~~~javascript
db.orders.insertOne(
  { _id: "ORDER-WMAJ", amount: 800 },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

Trong P-S-S ba voting data-bearing members bình thường, một ghi có thể đạt majority khi **hai data-bearing voting members phù hợp** đã đạt tiến độ cần thiết. Không cần mặc định cả ba đã theo kịp.

### 15.3. Journaling và `j:true`

~~~javascript
db.orders.insertOne(
  { _id: "ORDER-JOURNAL" },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
);
~~~

Journaling là cơ chế local durability của storage engine, khác với replication. Quan hệ chính xác giữa majority acknowledgment, journal và durability phụ thuộc MongoDB version và cấu hình như `writeConcernMajorityJournalDefault`. Không xem mọi acknowledgment là “đã fsync lên toàn bộ disks ở tất cả nodes”.

### 15.4. `wtimeout` không có nghĩa ghi không xảy ra

Nếu hết thời gian chờ majority:

- Write có thể đã được primary áp dụng.
- Một hoặc nhiều secondary có thể đã sao chép.
- Mức acknowledgment yêu cầu chưa đạt vào lúc timeout.
- Client có thể nhận write concern error.
- Retry mù có thể gây ghi lặp.

Ví dụ `$inc`:

~~~javascript
db.accounts.updateOne(
  { _id: "ACC-101" },
  {
    $inc: {
      points: 10
    }
  }
);
~~~

Nếu đã áp dụng mà response mất, lặp lại không kiểm soát có thể tăng 20 thay vì 10. Cần idempotent request ID hoặc cơ chế đối soát nghiệp vụ.

### 15.5. Mặc định không bất biến

Default write concern có thay đổi theo MongoDB version và topology, đặc biệt với deployments có arbiter. Đừng dạy “mọi replica set mặc định w:1” hoặc “mọi nơi mặc định majority” mà không kiểm tra môi trường.

---

## 16. Replication Lag: secondary có thể đi sau như thế nào?

### 16.1. Khái niệm

~~~text
PRIMARY   lastApplied = 12:00:10
SECONDARY lastApplied = 12:00:07

Khoảng cách tiến độ: ví dụ ~3 giây.
~~~

Đây là minh họa. Khi vận hành thật, phải đọc optime/replication metrics đúng semantics; clock skew, lastApplied vs lastDurable và tiến độ nguồn sync có thể ảnh hưởng cách hiểu.

### 16.2. Nguyên nhân thường gặp

- Primary có write rate cao.
- Secondary thiếu CPU, RAM hoặc disk I/O.
- Latency hoặc packet loss giữa members.
- Secondary xử lý báo cáo nặng.
- Tạo index, backup hoặc bảo trì gây áp lực I/O.
- Secondary vừa restart.
- Sync source kém.
- Thao tác ghi lớn hoặc workload trộn nhiều index.
- Delayed secondary có chủ đích.

### 16.3. Hậu quả

- Secondary reads có thể stale.
- Majority writes có thể chậm trong topology ít bản sao theo kịp.
- Thành viên có thể không phù hợp làm primary tại một thời điểm.
- Nếu offline quá oplog window, có thể cần initial sync.
- Failover có thể kéo dài hoặc dẫn đến rollback cho writes chưa majority-committed.

### 16.4. Biện pháp xử lý

Đo metrics, kiểm tra network/disk, giảm read-heavy workloads trên secondary, kiểm soát index builds, xác minh oplog window. Không chỉ tăng timeout hoặc hạ write concern mà bỏ qua rủi ro durability.

---

## 17. Failover, Network Partition và Rollback

### 17.1. Một sự cố failover minh họa

~~~text
T0: mongo1 = PRIMARY, mongo2/mongo3 = SECONDARY
T1: App ghi W vào mongo1, w:1 trả success.
T2: mongo1 bị tách mạng trước khi W sao chép đủ.
T3: mongo2 + mongo3 có 2/3 votes.
T4: mongo2 được bầu làm PRIMARY.
T5: mongo1 quay lại.
T6: MongoDB đồng bộ lịch sử được chấp nhận;
    W có thể bị rollback nếu chưa majority committed.
~~~

Không phải mọi thao tác w:1 đều sẽ rollback, nhưng đây là rủi ro cần tính.

### 17.2. Majority ack và rollback

Majority-acknowledged writes có mức bảo vệ mạnh hơn trước rollback trong các kịch bản failover thông thường. Tuy nhiên, sự an toàn thực tế còn phụ thuộc storage durability, cấu hình journaling, sự cố đồng thời nhiều nodes và những điều kiện vận hành.

Không diễn đạt thành “không bao giờ mất dữ liệu trong mọi thảm họa” khi chỉ cấu hình majority.

### 17.3. Network partition 2–1

~~~text
Nhóm A: mongo1 + mongo2 = 2 votes -> có majority
Nhóm B: mongo3          = 1 vote  -> không majority
~~~

Quorum ngăn một phía chỉ có 1/3 phiếu tự bầu primary hợp lệ. Một primary cũ có thể cần thời gian phát hiện mất majority; ứng dụng phải dùng official driver discovery và write concern phù hợp, không tự đánh giá bằng host availability.

### 17.4. Không force reconfig tùy tiện

Trong partition, việc ép cấu hình để một phía thiếu quorum bầu primary có thể tạo lịch sử phân kỳ hoặc rủi ro rollback. Đây là thao tác cứu hộ đặc biệt, chỉ thực hiện theo runbook được kiểm chứng và với đánh giá dữ liệu/backup.

---

## 18. Bảo trì, lựa chọn topology và failure domains

### 18.1. Ba data-bearing members trên ba zones

Trong hạ tầng có vùng lỗi độc lập, một P-S-S trải ba zones thường cho phép tiếp tục bầu primary khi một zone mất.

Nhưng network giữa zones làm tăng:

- Replication latency.
- Latency `w:"majority"` khi cần node ở xa.
- Chi phí network.
- Nguy cơ partition.
- Độ phức tạp vận hành.

Không có công thức một topology hợp cho mọi môi trường. Cần đo latency và xác định RTO/RPO.

### 18.2. Quorum khác backup

Một P-S-S trên ba zones có thể chịu lỗi một zone, nhưng vẫn không cứu được dữ liệu bị xóa nhầm rồi được replicate. Backup cần được lưu trữ và bảo vệ độc lập.

### 18.3. Backup/Restore và RPO/RTO

- **RPO:** lượng dữ liệu tối đa chấp nhận mất khi sự cố.
- **RTO:** thời gian tối đa chấp nhận gián đoạn dịch vụ.

Replica set giúp giảm thời gian phục hồi khi một node lỗi, nhưng RPO thực tế còn phụ thuộc write concern và loại lỗi. Backup/PITR xử lý những sự cố khác, với RPO/RTO riêng cần kiểm thử.

---

## 19. Thực hành: tạo Replica Set trong Docker Compose

Phần này chỉ dành cho **lab cô lập**, không dùng nguyên mẫu cho production. Docker image mẫu `mongo:8.0` không bật authentication/TLS trong ví dụ. Không công bố Docker network cho mạng không tin cậy.

### 19.1. Tạo `compose.yml`

~~~yaml
services:
  mongo1:
    image: mongo:8.0
    command: ["mongod", "--replSet", "rsLearn", "--bind_ip_all"]
    volumes:
      - mongo1_data:/data/db

  mongo2:
    image: mongo:8.0
    command: ["mongod", "--replSet", "rsLearn", "--bind_ip_all"]
    volumes:
      - mongo2_data:/data/db

  mongo3:
    image: mongo:8.0
    command: ["mongod", "--replSet", "rsLearn", "--bind_ip_all"]
    volumes:
      - mongo3_data:/data/db

volumes:
  mongo1_data:
  mongo2_data:
  mongo3_data:
~~~

Ba containers có Docker-internal service DNS names và volumes riêng. Không publish cổng host. Với production, cần auth, TLS/member auth, backups, resources và version management.

Khởi chạy:

~~~bash
docker compose up -d
~~~

### 19.2. Khởi tạo replica set

Trong terminal tại thư mục chứa `compose.yml`:

~~~bash
docker compose exec mongo1 mongosh --quiet --eval 'rs.initiate({_id:"rsLearn",members:[{_id:0,host:"mongo1:27017",priority:2},{_id:1,host:"mongo2:27017",priority:1},{_id:2,host:"mongo3:27017",priority:1}]})'
~~~

Nếu chưa sẵn sàng, kiểm tra containers rồi thực hiện sau khi startup. Không lặp `rs.initiate()` sau khi replica set đã được khởi tạo thành công.

### 19.3. Xem trạng thái

~~~bash
docker compose exec mongo1 mongosh --quiet --eval 'rs.status()'
~~~

Trong mongosh:

~~~javascript
rs.status();
rs.conf();
db.hello();
~~~

Chờ các members hoàn tất initial sync và một member đạt PRIMARY.

### 19.4. Tạo document

Kết nối tới primary hiện tại bằng mongosh hoặc URI replica set phù hợp:

~~~javascript
use replica_lab

db.orders.insertOne({
  _id: "ORDER-001",
  status: "NEW",
  createdAt: new Date()
});
~~~

Nếu đang kết nối trực tiếp vào secondary và nhận lỗi not primary, xác định primary hiện tại hoặc dùng URI replica set; không sửa ứng dụng bằng cách hard-code IP primary.

### 19.5. Quan sát member roles

Trong mongosh từng member:

~~~javascript
db.hello().isWritablePrimary;
db.hello().secondary;
~~~

Thử xem `rs.status()` để tìm `stateStr` và `optimeDate`. Một secondary có thể chưa thấy document mới nếu replication chưa kịp áp dụng.

### 19.6. Mô phỏng primary lỗi

Nếu primary hiện là mongo1:

~~~bash
docker compose stop mongo1
~~~

Trên mongo2 hoặc mongo3:

~~~bash
docker compose exec mongo2 mongosh --quiet --eval 'rs.status()'
~~~

Sau election, xác định primary mới; không khẳng định luôn là mongo2. Bật lại member cũ:

~~~bash
docker compose start mongo1
~~~

Quan sát nó join lại và catch up. Với priority khác nhau, primary có thể thay đổi về sau tùy điều kiện thực tế.

### 19.7. Dọn lab

~~~bash
docker compose down
~~~

Lệnh này giữ named volumes theo hành vi thông thường. Nếu **cố ý xóa dữ liệu lab** và chắc chắn đang ở đúng Compose project:

~~~bash
docker compose down -v
~~~

`-v` xóa volumes của project; không chạy trên môi trường dữ liệu quan trọng.

### 19.8. Lưu ý DNS khi chạy từ host

Các hosts `mongo1`, `mongo2`, `mongo3` có thể phân giải bên trong Docker network nhưng không chắc phân giải từ máy host. Nếu mongosh/Java chạy từ host, thiết kế network/hostnames đúng cách; không tự thay tất cả member hosts thành `localhost` vì những member khác cần tự kết nối qua tên được cấu hình.

---

## 20. Các lệnh quản trị đọc trạng thái

### 20.1. `rs.status()`

~~~javascript
rs.status();
~~~

Đọc:

- `set`: tên replica set.
- `members[]`: danh sách thành viên.
- `stateStr`: PRIMARY, SECONDARY, ARBITER...
- `health`: trạng thái liên lạc/health được quan sát.
- `optime` hoặc `optimeDate`: tiến độ sao chép.
- Sync source và các field election/heartbeat phù hợp version.

Ví dụ shape minh họa:

~~~javascript
{
  set: "rsLearn",
  members: [
    { name: "mongo1:27017", health: 1, stateStr: "PRIMARY" },
    { name: "mongo2:27017", health: 1, stateStr: "SECONDARY" },
    { name: "mongo3:27017", health: 1, stateStr: "SECONDARY" }
  ]
}
~~~

Đây chỉ là ví dụ những field cần chú ý, **không phải toàn bộ output thực**.

### 20.2. `rs.conf()`

~~~javascript
rs.conf();
~~~

Kiểm tra hostnames, votes, priority, hidden và các thuộc tính cấu hình. **`rs.conf()` là cấu hình; `rs.status()` là trạng thái thực tế.** Một member trong cấu hình có thể đang DOWN.

### 20.3. `db.hello()`

~~~javascript
db.hello();
~~~

`isWritablePrimary` giúp nhận biết member giữ vai trò writable. Nhưng chỉ số này **không bảo đảm** mọi write concern đều có thể được đáp ứng: trong P-S-A chỉ còn P+A, node có thể là primary nhưng `w:"majority"` không có đủ data-bearing confirmations.

### 20.4. In trạng thái ngắn

~~~javascript
const result = rs.status();

printjson(
  result.members.map((member) => ({
    name: member.name,
    state: member.stateStr,
    health: member.health,
    optimeDate: member.optimeDate
  }))
);
~~~

`health:1` không chứng minh lag bằng 0. Cần đọc optime và monitoring về replication.

### 20.5. Oplog/replication helpers

Trong môi trường mongosh/version hỗ trợ:

~~~javascript
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
~~~

Output và mức hỗ trợ có thể thay đổi theo phiên bản. Trong production, nên sử dụng thêm metrics từ công cụ giám sát và admin commands chính thức.

---

## 21. Java Sync Driver: kết nối đúng replica set

### 21.1. Connection string nhiều hosts

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rsLearn
~~~

Driver có thể khám phá primary và định tuyến thao tác tới node phù hợp. Đây là ví dụ network lab, không có username/TLS. Production cần bảo mật tương ứng.

### 21.2. Java example

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class ReplicaSetExample {

    public static void main(String[] args) {

        String uri =
            "mongodb://mongo1:27017,mongo2:27017,mongo3:27017/"
            + "?replicaSet=rsLearn";

        MongoClientSettings settings =
            MongoClientSettings.builder()
                .applyConnectionString(new ConnectionString(uri))
                .build();

        try (MongoClient client = MongoClients.create(settings)) {

            MongoDatabase database =
                client.getDatabase("replica_lab");

            MongoCollection<Document> orders =
                database.getCollection("orders")
                    .withWriteConcern(
                        WriteConcern.MAJORITY.withWTimeout(
                            5, TimeUnit.SECONDS
                        )
                    )
                    .withReadConcern(ReadConcern.MAJORITY)
                    .withReadPreference(ReadPreference.primary());

            orders.insertOne(
                new Document("_id", "ORDER-JAVA-001")
                    .append("status", "NEW")
            );

            Document saved = orders.find(
                new Document("_id", "ORDER-JAVA-001")
            ).first();

            System.out.println(saved);
        }
    }
}
~~~

Ví dụ minh họa Java Sync Driver thông dụng và giả định lớp kết nối hợp lệ. Nếu chạy lại với cùng `_id`, có thể nhận duplicate key; hãy kiểm soát dữ liệu lab.

### 21.3. Đọc cho báo cáo

~~~java
MongoCollection<Document> reportingOrders =
    database.getCollection("orders")
        .withReadPreference(
            ReadPreference.secondaryPreferred()
        )
        .withReadConcern(ReadConcern.MAJORITY);

Document item = reportingOrders.find(
    new Document("status", "PAID")
).first();
~~~

ReadPreference secondaryPreferred có thể fallback primary và không bảo đảm dữ liệu mới nhất. Chỉ dùng khi report chấp nhận staleness.

### 21.4. Không kết nối cố định host primary

Một URI chỉ vào mongo1 với `directConnection=true` có thể hữu ích cho quản trị member, nhưng không phù hợp làm mặc định ứng dụng cần tự failover vì mongo1 có thể trở thành secondary sau election.

### 21.5. Retry cần hiểu trạng thái chưa rõ

Official drivers hỗ trợ server discovery/monitoring và retryable operations trong những điều kiện nhất định. Nhưng network timeouts, write concern failures và transaction retries vẫn cần chính sách ứng dụng. Không lặp vô hạn các lệnh không idempotent khi không biết chắc ghi trước đã xảy ra chưa.

---

## 22. Replication không phải Backup: đánh giá RPO/RTO

| Khía cạnh | Replica set | Backup hoặc PITR |
|---|---|---|
| Duy trì nhiều bản sao online | Có | Theo lịch/retention |
| Tự bầu primary khi một node lỗi | Có nếu đủ quorum/điều kiện | Không phải nhiệm vụ |
| Khôi phục khi xóa nhầm đã replicate | Không tự khôi phục | Có thể nếu có bản phù hợp |
| Phục hồi một thời điểm lịch sử | Không phải cơ chế chính | Có thể với PITR |
| Bảo vệ trước ransomware trên cùng credentials | Không đủ | Cần cách ly/immutable backups |
| Mục tiêu khôi phục | Failover nhanh hơn | Restore theo RPO/RTO |

**RPO** là mức dữ liệu chấp nhận mất; **RTO** là thời gian khôi phục mong muốn. Replica set có thể cải thiện hai chỉ số trong những lỗi node thông thường, nhưng không cam kết RPO=0 và RTO=0 trong mọi sự cố.

---

## 23. Giám sát và vận hành production

Tối thiểu nên giám sát:

1. **Primary hiện tại** và số lần election.
2. **Member states/health**, heartbeat failures.
3. **Replication lag**, optime/applied/durable tiến độ.
4. **Oplog window** và tỷ lệ tăng dữ liệu oplog.
5. **Write concern errors/timeouts**.
6. Disk usage, disk latency, free space.
7. CPU, RAM, cache pressure, network.
8. Read/write p95/p99 latency và slow queries.
9. Backup age, PITR window và kết quả restore test.
10. TLS certificates, authentication/authorization events, changes to replica set config.

Một cluster có đủ ba member state SECONDARY/PRIMARY vẫn có thể đang rất lag, storage gần đầy hoặc backup không thể restore.

### 23.1. Khi secondary lag cao

Quy trình điều tra:

- Xác định member nào chậm và mức độ chậm.
- Kiểm tra recent writes, disk I/O và network.
- Xem workload báo cáo trên secondary.
- Kiểm tra oplog window.
- Theo dõi hoạt động initial sync/recovering.
- Cân nhắc capacity/index/query optimizations.
- Khôi phục member theo tài liệu chính thức nếu không còn bắt kịp được.

Không giảm write concern hoặc tăng oplog size theo phản xạ mà bỏ qua nguyên nhân cốt lõi.

### 23.2. Khi primary election xảy ra thường xuyên

Kiểm tra:

- Network instability.
- Host reboots/CPU stalls.
- Storage latency.
- Replica set priority/config changes.
- Heartbeat failures.
- Software version compatibility.
- Các thao tác bảo trì gần đây.

Election lặp lại có thể gây gián đoạn ghi và làm ứng dụng tăng retry load.

### 23.3. Bảo mật

Production cần TLS, authentication, member-to-member authentication, least privilege, secret management, network isolation và backup được bảo vệ. Không sao chép Compose lab không auth vào production.

---

## 24. Những hiểu lầm thường gặp

**“Replica set = sharding.”** Sai. Replica set nhân bản cùng dataset; sharding phân chia dataset.

**“Có ba process trên một VM là HA đầy đủ.”** Sai. VM lỗi có thể làm cả ba ngừng.

**“Secondary nhận ngay mọi ghi.”** Sai. Replication bất đồng bộ, secondary có thể lag.

**“Secondary không bao giờ trở thành primary.”** Sai. Secondary đủ điều kiện có thể được bầu.

**“Priority 2 có hai phiếu.”** Sai. Priority khác votes.

**“Priority 0 không sao chép dữ liệu.”** Sai. Vẫn có thể là data-bearing secondary bình thường.

**“Arbiter là một bản sao dữ liệu.”** Sai. Arbiter không có user data.

**“Có primary thì chắc chắn w:majority thành công.”** Sai. P-S-A chỉ còn primary+arbiter là ví dụ.

**“Một data copy còn sống thì có thể ghi.”** Không nhất thiết; cần quorum để có primary hợp lệ.

**“w:1 đã xác nhận ở mọi secondary.”** Sai; w:1 không yêu cầu điều đó.

**“w:majority = toàn bộ members đã ghi.”** Sai; majority không phải all.

**“wtimeout chắc chắn nghĩa là chưa ghi.”** Sai; ghi có thể đã được primary áp dụng.

**“ReadPreference secondary luôn đọc giá trị mới nhất.”** Sai; có thể stale.

**“ReadConcern majority + secondary nghĩa là read latest.”** Không tự đảm bảo secondary đã bắt kịp primary.

**“Oplog là backup.”** Sai; oplog rolling/capped và dùng cho replication.

**“Replica set cứu được xóa nhầm.”** Không tự động; xóa nhầm có thể replicate.

**“Driver phải biết IP primary được hard-code.”** Không; nên dùng replica set discovery và nhiều seed hosts.

**“health:1 chứng minh replication lag = 0.”** Không; health và tiến độ là hai vấn đề.

**“Có thể force reconfig ngay khi mất majority.”** Rủi ro phân kỳ/rollback; cần runbook chính thức.

**“Đọc nhiều trên secondary không ảnh hưởng replication.”** Có thể cạnh tranh tài nguyên, làm lag tăng.

---

## 25. Quy trình thiết kế Replica Set theo nhu cầu hệ thống

### Bước 1 — Đặt yêu cầu rõ ràng

- RPO/RTO mục tiêu?
- Chịu lỗi một node, một zone hay cả region?
- Bao nhiêu writes/second, reads/second?
- API nào cần read-your-writes?
- Có yêu cầu compliance/region?
- Chấp nhận replication lag bao nhiêu?
- Chi phí storage/network cho phép?
- Backup/PITR đã có chưa?

### Bước 2 — Chọn data-bearing members

Khởi điểm phổ biến: ba voting data-bearing members trên các failure domains độc lập. Chỉ chọn arbiter khi hiểu rõ độ an toàn và majority write limitations.

### Bước 3 — Tính election quorum

Với V voting members, majority = floor(V/2)+1. Đánh giá từng tình huống node/zone down. Không chỉ đếm số server còn hoạt động.

### Bước 4 — Đánh giá write acknowledgment

Cho từng tình huống:

~~~text
Còn primary?
Còn bao nhiêu data-bearing members?
Còn quorum?
w:majority còn được ack không?
Có khả năng rollback w:1 không?
~~~

### Bước 5 — Thiết kế đọc

Chọn primary/secondary preference và read concern theo từng API. Không thay read consistency bằng một config toàn ứng dụng thiếu phân biệt.

### Bước 6 — Lập kế hoạch deployment

Bảo đảm DNS/hostnames, disks, zones, TLS, member authentication, write concern, oplog, monitoring, backup và capacity.

### Bước 7 — Kiểm thử lỗi

- Dừng một secondary.
- Dừng primary.
- Khôi phục node.
- Giả lập secondary lag.
- Test read staleness.
- Test majority write timeout.
- Test backup restore.
- Đo failover RTO trên workload thật.

### Bước 8 — Ghi runbook

Tài liệu hóa các lệnh quan sát, các ngưỡng cảnh báo, quy trình thay node, nâng cấp, khôi phục quorum và hướng xử lý rollback/backup.

---

## 26. Các tình huống phân tích

### A. P-S-S mất primary

Hai secondary còn liên lạc: 2/3 votes, có thể bầu primary mới. Ghi có thể tạm ngừng trong election, rồi tiếp tục khi có primary và write concern đáp ứng.

### B. P-S-S mất hai nodes

Một member còn dữ liệu nhưng chỉ 1/3 phiếu, không đạt majority. Không được tự tạo primary bằng force reconfig nếu chưa có kế hoạch cứu hộ chính thức.

### C. P-S-A mất secondary

Primary+arbiter có 2/3 votes nhưng chỉ còn một data-bearing member. Majority writes có thể timeout vì arbiter không xác nhận dữ liệu.

### D. Primary w:1 ack rồi chết

Nếu write chưa majority committed, nó có thể bị rollback khi primary khác được bầu và node cũ hòa nhập lại.

### E. Đọc trên secondary ngay sau thanh toán

Secondary có thể vẫn thấy trạng thái NEW, dù primary đã nhận PAID. Read preference không tự cung cấp read-your-writes.

### F. Secondary offline quá lâu

Oplog window không còn chứa các operations cần catch up. Có thể phải initial sync lại.

### G. Ba nodes cùng shared storage

Khi shared storage lỗi, cả ba có thể ngừng. Voting quorum không khắc phục correlated infrastructure failure.

### H. Xóa nhầm trên primary

Các secondary cũng áp dụng xóa; chỉ backup/PITR độc lập theo chính sách mới giúp phục hồi dữ liệu lịch sử.

### I. Hidden secondary được dùng làm báo cáo

Hidden không được chọn qua normal secondary readPreference; nếu dùng kết nối trực tiếp cho tác vụ chuyên biệt, phải kiểm soát consistency, network/auth và load.

---

## 27. Bài tập thực hành

### Bài 1 — Sơ đồ P-S-S

Vẽ primary, hai secondary, oplog, đường ghi và đường secondary read. Chú thích member nào lưu data, member nào bỏ phiếu.

### Bài 2 — Tính majority

Tính majority cho V = 1, 2, 3, 4, 5, 7. Giải thích vì sao hai voting nodes không chịu được lỗi một node về election quorum.

### Bài 3 — Mất primary trong P-S-S

P chết, S1 và S2 còn. Xác định quorum, data copies, failover steps và mức write concern có thể đạt khi hai nodes theo kịp.

### Bài 4 — Mất secondary trong P-S-A

P + A còn: có đủ votes không? Có đủ data-bearing acknowledgments cho `w:"majority"` không? Vì sao?

### Bài 5 — Member priority

Cấu hình:

~~~javascript
{
  _id: "rs0",
  members: [
    { _id: 0, host: "db1:27017", votes: 1, priority: 2 },
    { _id: 1, host: "db2:27017", votes: 1, priority: 1 },
    { _id: 2, host: "db3:27017", votes: 1, priority: 0 }
  ]
}
~~~

Hỏi db3 có thể làm primary không, có dữ liệu không và db2+db3 có đủ phiếu bầu primary khi db1 lỗi không.

### Bài 6 — So sánh write concerns

Viết lệnh insert `w:1` và `w:"majority"`; giải thích tình huống w:1 ack nhưng chưa sao chép đủ, và hậu quả khi primary lỗi.

### Bài 7 — Read preference

Chọn chính sách cho dashboard lịch sử, xem đơn mới tạo, xác nhận thanh toán và báo cáo analytics. Giải thích staleness/consistency requirements.

### Bài 8 — Quan sát MongoDB

Dùng `rs.status()`, `rs.conf()`, `db.hello()`. Ghi current primary, states, votes, priority, optime. Giải thích vì sao `health:1` chưa chắc lag = 0.

### Bài 9 — Failover trong Docker

Tạo replica set lab, dừng primary, quan sát bầu cử, tạo write mới qua URI replica set, start lại node cũ và quan sát catch up. Không đoán cố định node nào thắng.

### Bài 10 — Oplog window

Secondary offline 20 giờ trong khi oplog chỉ giữ khoảng 8 giờ theo tốc độ ghi hiện tại. Điều gì có thể xảy ra khi nó quay lại?

### Bài 11 — RPO/RTO

Thiết kế sơ bộ cho một ứng dụng cần chịu lỗi một zone. Nêu topology, backup, write concern, lag alerts và cách đo RTO thực.

### Bài 12 — Java Driver

Viết kết nối Java URI có ba hosts, đọc primary, ghi majority, rồi thử báo cáo secondaryPreferred. Nêu cách ứng dụng phải xử lý timeout và retry có tính idempotent.

### Bài 13 — Tính phiếu và bản sao độc lập

Tạo bảng so sánh P-S-S, P-S-A và hai voting data-bearing nodes về majority, data copies, khả năng mất một node và majority writes.

### Bài 14 — Disaster recovery

Nếu admin xóa toàn collection rồi xóa được replicate, mô tả các bước cần có để phục hồi từ backup/PITR. Vì sao delayed secondary cũng không phải bảo đảm phục hồi độc lập?

### Bài 15 — Dashboard giám sát

Thiết kế các panel cho primary, states, election count, lag, oplog window, write concern timeouts, disk, CPU và backup age. Định nghĩa các cảnh báo quan trọng.

---

## 28. Câu hỏi ôn tập

1. Replica set là gì?
2. Khác biệt giữa replication và sharding?
3. Primary có nhiệm vụ nào?
4. Secondary có thể tiếp nhận write trực tiếp từ ứng dụng như primary không?
5. Secondary lấy thay đổi qua cơ chế nào?
6. Oplog nằm ở đâu?
7. Oplog khác journal/backup thế nào?
8. Replication là đồng bộ tức thời hay bất đồng bộ?
9. Replication lag gây tác động nào?
10. Initial sync diễn ra khi nào?
11. Majority election với ba voters là bao nhiêu?
12. Vì sao mất một node trong P-S-S thường vẫn có thể bầu primary?
13. Vì sao chỉ còn một voter không thể bầu trong replica set ba phiếu?
14. Arbiter có dữ liệu không?
15. Arbiter có thể thành primary không?
16. P-S-A khác P-S-S về số data-bearing members thế nào?
17. Vì sao P+A đủ phiếu vẫn có thể không ack `w:"majority"`?
18. Priority 0 có nghĩa gì?
19. Votes 0 có nghĩa gì?
20. Hidden secondary có tác dụng gì?
21. Delayed secondary có thay backup không?
22. Read preference trả lời câu hỏi gì?
23. Read concern khác read preference ra sao?
24. Vì sao majority read từ secondary vẫn có thể stale?
25. `w:1` có nghĩa gì?
26. `w:"majority"` có nghĩa gì?
27. `wtimeout` có chứng minh ghi không xảy ra không?
28. Rollback có thể ảnh hưởng writes loại nào?
29. Vì sao không hard-code primary host?
30. Vì sao ba processes trên một máy không đủ HA theo failure domain?
31. Cần theo dõi những chỉ số nào để phát hiện lag?
32. Secondary offline quá oplog window có thể cần làm gì?
33. Replication có phục hồi xóa nhầm không?
34. RPO và RTO là gì?
35. Vì sao topology production phải kiểm tra cả votes và data copies?

---

## 29. Tổng kết

MongoDB Replica Set duy trì nhiều thành viên để tăng **khả năng sẵn sàng** và **dư thừa dữ liệu**. Trong cấu trúc điển hình, **primary** chấp nhận ghi và lưu oplog; **secondaries** sao chép thay đổi, duy trì bản sao và có thể tham gia election. Replication là bất đồng bộ, nên secondary có thể trễ.

Những nguyên tắc cần nhớ:

- **Primary** là writable member được bầu, không phải host cố định.
- **Secondary** lưu dữ liệu, đồng bộ qua oplog và có thể được bầu thành primary nếu đủ điều kiện.
- **Majority voting** bảo vệ quá trình bầu cử, nhưng không đồng nghĩa có đủ data copies.
- **P-S-S** thường có ba bản sao dữ liệu và phù hợp hơn về redundancy so với **P-S-A**.
- **Arbiter** có phiếu bầu nhưng không có dữ liệu, không thể thay secondary để ack `w:"majority"`.
- **Read preference** quyết định nơi đọc; **read concern** quyết định mức nhìn thấy dữ liệu; **write concern** quyết định mức xác nhận ghi.
- **Replication lag** gây dữ liệu cũ ở secondary; **w:1** có rủi ro rollback cao hơn majority trong các tình huống phù hợp.
- **Backup/PITR** vẫn bắt buộc cho khôi phục dữ liệu bị xóa nhầm hoặc thảm họa.
- **Production readiness** còn cần failure domains, TLS/auth, monitoring, backups, runbook và failover tests.

Câu hỏi đúng khi thiết kế một replica set không chỉ là **“có bao nhiêu máy?”**, mà là: **“còn đủ phiếu để có primary không, còn bao nhiêu bản sao dữ liệu thật sự, và ứng dụng cần mức bảo đảm đọc/ghi nào khi có sự cố?”**

## Tài liệu MongoDB chính thức tham khảo

- [MongoDB Manual — Replication](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Manual — Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-members/)
- [MongoDB Manual — Replica Set Primary](https://www.mongodb.com/docs/manual/core/replica-set-primary/)
- [MongoDB Manual — Replica Set Secondary](https://www.mongodb.com/docs/manual/core/replica-set-secondary/)
- [MongoDB Manual — Replica Set Arbiter](https://www.mongodb.com/docs/manual/core/replica-set-arbiter/)
- [MongoDB Manual — Replication Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [MongoDB Manual — Replica Set Data Synchronization](https://www.mongodb.com/docs/manual/core/replica-set-sync/)
- [MongoDB Manual — Replica Set High Availability](https://www.mongodb.com/docs/manual/core/replica-set-high-availability/)
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Replica Set Write Concern](https://www.mongodb.com/docs/manual/core/replica-set-write-concern/)
- [MongoDB Manual — Replica Set Rollbacks](https://www.mongodb.com/docs/manual/core/replica-set-rollbacks/)
- [MongoDB Manual — rs.status()](https://www.mongodb.com/docs/manual/reference/method/rs.status/)
- [MongoDB Manual — rs.conf()](https://www.mongodb.com/docs/manual/reference/method/rs.conf/)
- [MongoDB Manual — db.hello()](https://www.mongodb.com/docs/manual/reference/method/db.hello/)
- [MongoDB Manual — Deploy a Replica Set](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [MongoDB Java Sync Driver — Connection Guide](https://www.mongodb.com/docs/drivers/java/sync/current/connection/)
- [MongoDB Manual — Backup Methods](https://www.mongodb.com/docs/manual/core/backups/)
