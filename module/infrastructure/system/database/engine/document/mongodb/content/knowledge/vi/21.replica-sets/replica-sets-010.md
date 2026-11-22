# Phân bố thành viên theo vùng lỗi và kiểm thử mất thành viên trong MongoDB Replica Set

MongoDB Replica Set lưu nhiều bản sao dữ liệu và sử dụng cơ chế **bầu primary** để duy trì khả năng ghi khi một thành viên không còn phục vụ được. Nhưng có ba thành viên không tự động có nghĩa là hệ thống sẽ chịu được việc mất một máy chủ, Availability Zone (AZ) hoặc Region. Nếu tất cả cùng ở một vùng lỗi, một sự cố chung có thể làm mất toàn bộ replica set.

Thiết kế và kiểm thử đúng cần phân biệt:

1. **Failure domain:** những thành viên nào có thể đồng thời mất vì cùng một nguyên nhân?
2. **Election quorum:** sau sự cố còn đủ voting majority để bầu hoặc duy trì primary hợp lệ không?
3. **Bản sao và ứng dụng:** còn đủ data-bearing members để đáp ứng write concern, và ứng dụng có phục hồi đúng sau failover không?

Bài học giải thích cách phân bố replica set theo host/rack/AZ/Region, tính majority, lựa chọn topology 3 hoặc 5 thành viên, các giới hạn của arbiter và non-voting member, đồng thời xây dựng runbook kiểm thử **mất secondary, mất primary, mất cả AZ và network partition**. Ví dụ sử dụng **mongosh** và **MongoDB Java Sync Driver**.

**Phạm vi an toàn:** Không thực hiện các lệnh dừng node, cô lập mạng hoặc thay đổi primary trên hệ thống thật khi chưa được phép. Các thao tác gây lỗi chỉ dành cho lab/staging hoặc quy trình production game day được phê duyệt, có telemetry, ngưỡng dừng và cách khôi phục.

## 1. Fault tolerance phải được định nghĩa theo vùng lỗi

Một replica set ba thành viên có thể được triển khai theo ba cách:

**Trường hợp A – ba process chung một host:**

~~~text
Host-01
├── mongod-1
├── mongod-2
└── mongod-3
~~~

Mất một process có thể vẫn còn các process khác, nhưng mất Host-01 thì cả ba cùng mất.

**Trường hợp B – ba host trong một AZ:**

~~~text
AZ-A
├── Host-01: mongod-1
├── Host-02: mongod-2
└── Host-03: mongod-3
~~~

Có thể chịu lỗi host độc lập, nhưng sự cố toàn AZ-A vẫn lấy đi cả ba.

**Trường hợp C – ba AZ độc lập:**

~~~text
Region R1
├── AZ-A: mongod-1
├── AZ-B: mongod-2
└── AZ-C: mongod-3
~~~

Với ba thành viên dữ liệu có vote, mất một AZ còn hai phiếu; về toán học vẫn đủ majority. Cần thêm điều kiện hai node còn lại kết nối được và có candidate primary hợp lệ.

### 1.1. Failure domain không chỉ là vị trí địa lý

Các vùng lỗi có thể là:

| Vùng lỗi | Ví dụ |
| --- | --- |
| Process | mongod crash hoặc OOM |
| Host / VM | lỗi kernel, disk, hypervisor |
| Rack | mất nguồn, top-of-rack switch |
| Storage domain | lỗi backing volume hoặc storage service dùng chung |
| Availability Zone | một cụm hạ tầng độc lập tương đối |
| Region | sự cố khu vực hoặc kết nối liên vùng |
| Network | routing, firewall, DNS, certificate |
| Control plane | một rollout hoặc secret rotation lỗi cùng lúc |

Ba VM ở ba AZ vẫn có thể cùng chịu lỗi cấu hình khi một policy được áp dụng đồng loạt. **Đa AZ giảm rủi ro tương quan, không loại bỏ mọi rủi ro tương quan.**

### 1.2. RTO và RPO

- **RTO:** thời gian gián đoạn tối đa mà nghiệp vụ chấp nhận.
- **RPO:** lượng dữ liệu tối đa có thể mất theo mục tiêu nghiệp vụ.

Replica set có thể bầu primary mới nhưng quá trình election và client discovery không tức thời. Vì vậy cần đo thời gian ứng dụng **thật sự ghi trở lại**, thay vì chỉ kiểm tra trên server có PRIMARY.

Replica set cũng không tự bảo đảm mọi write đều bền vững sau failover. Phải đánh giá **write concern** và trạng thái replication.

## 2. Vai trò của các thành viên

| Thành viên | Có dữ liệu? | Góp vote? | Có thể làm primary? |
| --- | --- | --- | --- |
| Primary | Có | Theo cấu hình | Đang là primary |
| Secondary thông thường | Có | Theo cấu hình | Có thể, nếu eligible |
| Arbiter | Không | Có | Không |
| Hidden secondary | Có | Có thể | Thường không do priority = 0 |
| Delayed secondary | Có nhưng áp dụng trễ | Tùy cấu hình | Không xem như candidate thông thường |
| Non-voting secondary | Có | Không | Không |
| Priority-0 secondary | Có | Có thể | Không |

Ba thuộc tính cần phân biệt:

- **votes:** đóng góp cho quorum bầu primary.
- **priority:** mức ưu tiên và khả năng eligible để thành primary.
- **data-bearing:** thực sự lưu collection và oplog.

Một secondary **priority: 0, votes: 1** vẫn góp phiếu nhưng không được bầu primary. Một non-voting secondary vẫn lưu dữ liệu nhưng không tăng majority vote. Arbiter có vote nhưng không lưu một bản sao dữ liệu.

## 3. Tính majority

Với **V voting members**, số phiếu cần:

\[
Q = \left\lfloor\frac{V}{2}\right\rfloor + 1
\]

Nếu một failure domain mất **L voter**, điều kiện còn quorum là:

\[
V - L \ge Q
\]

| Số voter V | Majority Q | Mất tối đa bao nhiêu voter còn đủ majority? |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |
| 7 | 4 | 3 |

Replica set thường thiết kế số voter lẻ như **3 hoặc 5**. MongoDB có giới hạn về số voting members; khi mở rộng topology cần theo hướng dẫn đúng phiên bản thay vì chỉ tăng số process.

### 3.1. Đủ majority là điều kiện cần, chưa phải đủ

Để có writable primary sau lỗi, cần:

1. Còn majority của các voter có thể liên lạc.
2. Còn một **data-bearing member eligible** để bầu primary.
3. Các điều kiện election và trạng thái replication phù hợp.
4. Client có thể kết nối tới primary mới.

Nếu phần còn lại chỉ là arbiter và các member priority = 0, không thể mặc nhiên kết luận sẽ có primary dù số phiếu có vẻ đủ.

### 3.2. Election majority khác majority acknowledgement

Một arbiter có thể giúp đạt majority **votes**, nhưng không thể xác nhận rằng nó đã lưu write trên đĩa vì nó không có bản sao dữ liệu. Khi đánh giá khả năng đáp ứng **w: "majority"**, phải kiểm tra các data-bearing members và quy tắc write concern của topology.

## 4. Topology ba data-bearing voters trên ba AZ

~~~text
AZ-A: mongo-a  (data-bearing, voting, electable)
AZ-B: mongo-b  (data-bearing, voting, electable)
AZ-C: mongo-c  (data-bearing, voting, electable)

V = 3, Q = 2
~~~

| Sự cố | Voter còn | Quorum | Hành vi có thể xảy ra |
| --- | ---: | --- | --- |
| Mất AZ-A | 2 | Có | Hai member còn lại có thể bầu primary |
| Mất AZ-B | 2 | Có | Còn majority |
| Mất AZ-C | 2 | Có | Còn majority |
| Mất hai AZ | 1 | Không | Không có đủ phiếu bầu primary |
| Mất một host độc lập | 2 | Có | Còn quorum nếu hai node còn liên lạc |

Nếu mongo-a đang là PRIMARY và AZ-A mất, mongo-b/mongo-c có thể bầu primary mới. Trong thời gian election, write từ ứng dụng có thể timeout hoặc gặp lỗi tạm thời.

Nếu mất AZ chỉ chứa secondary, primary có thể tiếp tục phục vụ, nhưng cụm lúc này còn **đúng majority**; lỗi tiếp theo có thể khiến mất quorum.

## 5. Topology ba voter phân bố 2–1 ở hai AZ

~~~text
AZ-A: mongo-a, mongo-b  (2 voter)
AZ-B: mongo-c           (1 voter)

V = 3, Q = 2
~~~

- Mất AZ-B → còn hai voter, đủ quorum.
- Mất AZ-A → còn một voter, **mất quorum**.

Đây là bố trí có khả năng chịu lỗi bất đối xứng. Nó có thể chịu lỗi một host nhưng **không chịu mất bất kỳ AZ nào**.

Đặt primary với priority cao ở AZ-B cũng không sửa được vấn đề: một voter vẫn là một voter. **Priority không thay số phiếu majority.**

## 6. Topology năm voter phân bố 2–2–1

~~~text
AZ-A: mongo-a1, mongo-a2
AZ-B: mongo-b1, mongo-b2
AZ-C: mongo-c1

V = 5, Q = 3
~~~

| AZ mất | Voter mất | Voter còn | Đủ majority? |
| --- | ---: | ---: | --- |
| AZ-A | 2 | 3 | Có |
| AZ-B | 2 | 3 | Có |
| AZ-C | 1 | 4 | Có |

Bố trí **2–2–1** đáp ứng yêu cầu quorum khi mất từng AZ đơn lẻ, nếu không có các phụ thuộc chung làm mất thêm node.

### 6.1. Bố trí 3–1–1 không tương đương

~~~text
AZ-A: 3 voter
AZ-B: 1 voter
AZ-C: 1 voter

V = 5, Q = 3
~~~

Nếu AZ-A mất, chỉ còn **2/5 voter**. Không đủ majority.

Do đó, **năm node không tốt hơn ba node theo mục tiêu chịu mất AZ nếu việc phân bố phiếu sai**.

### 6.2. Nếu có arbiter hoặc non-voting member

Đừng xem năm process là năm bản sao dữ liệu. Hãy kiểm kê riêng số **voter** và số **data-bearing members**. Một số topology có quorum nhưng không còn candidate hoặc không đáp ứng majority writes như dự kiến.

## 7. Đánh đổi khi phân bố nhiều Region

Một thiết kế trải qua nhiều Region giúp giảm rủi ro mất cả Region nhưng tăng:

- Độ trễ giữa các bản sao.
- Chi phí sao chép dữ liệu xuyên Region.
- Độ trễ của một số majority-acknowledged writes.
- Rủi ro network partition liên vùng.
- Phức tạp định tuyến ứng dụng, secret, DNS và phụ thuộc dịch vụ.

**Ba Region 1–1–1:** mất một Region còn 2/3 voter, có quorum nếu các Region còn lại kết nối.

**Hai Region 3–2:** mất Region có ba voter còn 2/5, thiếu quorum. Đây không phải topology chịu mất bất kỳ Region.

**Ba Region 2–2–1:** với năm voter, mất một Region bất kỳ còn ít nhất ba voter. Nhưng quorum chỉ là phần toán học; latency và khả năng xác nhận ghi cần được đo.

### 7.1. Ưu tiên primary gần writer

Có thể cấu hình priority để ưu tiên primary gần ứng dụng ghi chính. Nhưng cần tránh thay đổi priority gây leader churn. Khi Region ưu tiên mất, phải còn candidate primary trong vùng sống.

Không dùng priority để thay cho thiết kế quorum.

### 7.2. Đa Region chưa phải disaster recovery hoàn chỉnh

Nếu MongoDB failover thành công nhưng ứng dụng, DNS, payment service hoặc credential chỉ sống ở Region đã mất, người dùng vẫn không thao tác được.

DR cần bao gồm backup, restore, định tuyến dịch vụ, các dependency và quy trình toàn hệ thống.

## 8. Arbiter: phiếu bầu không phải dữ liệu

Mô hình **Primary–Secondary–Arbiter (PSA)**:

~~~text
AZ-A: PRIMARY   (có dữ liệu)
AZ-B: SECONDARY (có dữ liệu)
AZ-C: ARBITER   (không dữ liệu)

3 voter, 2 data-bearing
~~~

Arbiter có thể góp phiếu vào election nhưng:

- Không lưu collection/oplog như data-bearing member.
- Không cung cấp bản sao dữ liệu thứ ba.
- Không phục vụ read từ dữ liệu.
- Không thể được bầu primary.
- Không thay thế backup.

Khi một data-bearing secondary mất, primary còn lại cộng arbiter có thể đủ phiếu election, nhưng khả năng thỏa write concern majority có những giới hạn do không còn đủ bản sao dữ liệu cần thiết.

Với yêu cầu HA và durability mạnh, **ba data-bearing members ở ba failure domains** thường được ưu tiên hơn PSA khi nguồn lực cho phép.

## 9. Hidden, delayed, priority-0 và non-voting secondary

**Hidden secondary** có dữ liệu nhưng thường không được client lựa chọn đọc thông thường. Hidden thường phải có priority = 0 và có thể vẫn mang vote.

**Delayed secondary** áp dụng oplog trễ có chủ đích. Nó không được xem như một bản sao luôn cập nhật để bầu primary ngay. Cần xem các ràng buộc priority/votes theo phiên bản và cấu hình thực tế.

**Non-voting secondary** có dữ liệu nhưng votes = 0, vì vậy không làm tăng election quorum.

**Priority-0 secondary** không thể thành primary dù vẫn có thể góp vote. Nếu phần còn lại sau thảm họa chỉ có priority-0 nodes và arbiter, không có candidate writable primary phù hợp.

Khi thiết kế, cần bảng:

~~~text
Member | Host | Rack | AZ | Region | Votes | Priority
Data-bearing | Hidden | Delayed | Role | Replication lag
~~~

## 10. Write concern majority và khả năng mất dữ liệu

Ví dụ write probe:

~~~javascript
db.haProbe.insertOne(
  {
    _id: "RUN-231-BASE-001",
    ts: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
~~~

**w: "majority"** yêu cầu mức xác nhận majority theo quy tắc write concern và topology đang chạy; **wtimeout** giới hạn thời gian chờ xác nhận.

### 10.1. Write chưa majority-acknowledged có thể rollback

Nếu primary nhận một write và trả acknowledgment theo mức thấp trước khi các secondary cần thiết nhận được, rồi primary mất, primary mới có thể không chứa write đó. Primary cũ khi quay lại có thể phải rollback lịch sử chưa được majority xác nhận.

Trong bài test cần tách:

~~~text
Write được gửi
Write đã áp dụng ở primary
Write acknowledged với w:1
Write acknowledged với w:majority
Write timeout hoặc chưa rõ kết quả
Write còn tồn tại sau failover
~~~

Không báo cáo RPO từ một con số “total successful requests” nếu các mức xác nhận khác nhau.

### 10.2. wtimeout không chứng minh write chưa xảy ra

Khi chưa đạt xác nhận majority trước timeout, client có thể chưa biết write có được áp dụng ở primary hay không. Không tự retry phép cộng/trừ bằng một business command mới nếu nó có thể tạo hiệu ứng lặp.

### 10.3. Election majority và dữ liệu phải được đánh giá riêng

Arbiter có vote nhưng không lưu dữ liệu. Một non-voting secondary có dữ liệu nhưng không góp phiếu. Do đó thiết kế phải đánh giá **quorum, candidate election và mức nhân bản write** như những điều kiện khác nhau.

## 11. Read preference trong failover

Một ứng dụng có thể đọc với:

| Read preference | Hành vi khái quát |
| --- | --- |
| **primary** | Chỉ đọc primary |
| **primaryPreferred** | Ưu tiên primary |
| **secondary** | Chỉ đọc secondary |
| **secondaryPreferred** | Ưu tiên secondary |
| **nearest** | Chọn member phù hợp độ trễ |

Khi không có primary trong thời gian election, read preference **primary** có thể lỗi/tạm chờ. Khi mất mọi secondary phù hợp, read preference **secondary** có thể lỗi dù primary còn hoạt động.

Đọc từ secondary có thể thấy dữ liệu cũ do replication lag. Đối với read-your-writes hoặc consistency cao hơn, cần thiết kế read concern, session và causal consistency cho đúng.

## 12. Preflight trước một bài kiểm thử mất member

Trong mongosh:

~~~javascript
rs.status();
~~~

Xem cấu hình:

~~~javascript
rs.conf();
~~~

Xem trạng thái node:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Có thể tham khảo replication:

~~~javascript
rs.printSecondaryReplicationInfo();
~~~

Các field trong output thay đổi theo phiên bản. Thông tin cần xác định gồm:

- Primary hiện tại.
- Các member và state/health.
- Votes/priority/hidden/delayed.
- Replication lag, oplog window.
- Member nào thuộc AZ/Region nào.
- Client đọc/ghi theo cấu hình nào.

### 12.1. Bảng preflight

| Mục | Điều kiện trước khi test |
| --- | --- |
| Primary | Ổn định, không đang election liên tục |
| Voting members | Không có lỗi ngoài phạm vi thử |
| Secondaries | Replication lag chấp nhận được |
| Oplog | Có đủ cửa sổ cho thời gian offline dự kiến |
| Monitoring | Thu thập được cả database và API |
| Khả năng khôi phục | Có quyền bật lại node/network |
| Backup | Cơ chế khôi phục có sẵn theo yêu cầu môi trường |
| Thay đổi đang chạy | Không có rollout gây thêm sự cố |
| Người điều phối | Có người giám sát và điều kiện dừng |

Không tự làm mất thêm voter nếu cluster đã suy giảm đến mức **chỉ còn đúng majority**.

## 13. Xây dựng workload probe

Một lần ping thành công không chứng minh replica set còn primary và majority write khả dụng. Nên có một collection probe riêng:

~~~javascript
use ha_test_lab

db.probe.insertOne(
  {
    _id: "RUN231-PROBE-001",
    createdAt: new Date(),
    kind: "baseline"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
~~~

Trong bài test dài, ghi các thông tin:

- requestId cố định của mỗi business operation.
- Thời điểm gửi và nhận kết quả.
- Loại read/write.
- Read concern, read preference và write concern.
- Latency và error code.
- Primary/client topology quan sát được.
- Kết quả xác minh dữ liệu sau failover.

### 13.1. Vì sao cần probe liên tục?

Nếu chỉ chạy một write trước sự cố và một write sau sự cố, ta không biết ứng dụng bị gián đoạn bao lâu.

Probe có cadence được kiểm soát, ví dụ mỗi giây một lần, cho phép ước lượng thời gian từ lúc tiêm lỗi đến khi request mới thành công.

### 13.2. Phân biệt kết quả không rõ và thất bại chắc chắn

Nếu network timeout sau khi write được gửi, client có thể không biết chắc server đã áp dụng write chưa. Cần đối soát theo requestId trước khi retry ở tầng nghiệp vụ.

## 14. Kịch bản A: mất secondary

Topology ban đầu:

~~~text
AZ-A: mongo-a PRIMARY
AZ-B: mongo-b SECONDARY
AZ-C: mongo-c SECONDARY
~~~

Thử làm **mongo-b** offline trong lab/staging.

### 14.1. Kỳ vọng

- mongo-a và mongo-c còn 2/3 votes.
- Primary có thể giữ role.
- Majority writes còn có khả năng xác nhận khi đủ data-bearing members.
- Client đọc trực tiếp mongo-b gặp lỗi; ứng dụng có read preference phù hợp có thể chọn nguồn khác.
- Khi mongo-b quay lại, nó cần bắt kịp replication.

### 14.2. Runbook

1. Ghi rs.status, rs.conf, replication lag.
2. Bắt đầu probe majority write và read.
3. Dừng **chỉ mongo-b** bằng công cụ được phép.
4. Quan sát primary và error/latency.
5. Bật lại mongo-b.
6. Chờ nó trở thành secondary khỏe và bắt kịp oplog.
7. Đối soát probes và đóng test.

Node bật process trở lại **chưa chắc đã đồng bộ dữ liệu xong**.

## 15. Kịch bản B: mất primary

~~~text
Trước:
mongo-a PRIMARY
mongo-b SECONDARY
mongo-c SECONDARY

Trong lỗi:
mongo-a unavailable
mongo-b, mongo-c còn majority
~~~

Một secondary đủ điều kiện có thể được bầu làm primary mới.

### 15.1. Timeline quan sát

~~~text
T0  primary mất kết nối
T1  members còn lại nhận biết thay đổi
T2  election hoàn tất, xuất hiện primary mới
T3  driver chọn được primary mới
T4  majority write ở API thành công trở lại
T5  primary cũ quay lại và đồng bộ xong
~~~

**RTO ứng dụng phụ thuộc tới T4, không chỉ T2.** Driver còn cần topology discovery, connection pool và retry.

### 15.2. Controlled step-down trong lab

Để thử chuyển vai trò, khi đang kết nối primary:

~~~javascript
rs.stepDown(60, 10);
~~~

Lệnh này có thể gây ngắt session và chỉ thành công khi điều kiện tương ứng đáp ứng. Nó kiểm thử **leader transition**, không tương đương mất host/AZ thật sự.

Không ép step-down hoặc force reconfig để chạy thử khi không hiểu trạng thái quorum và dữ liệu.

### 15.3. Xác nhận kết quả

Sau election, kiểm tra:

- Chỉ có primary hợp lệ theo topology.
- API majority writes hoạt động trở lại.
- Dữ liệu majority-acknowledged trước lỗi còn tồn tại.
- Request timeout không tạo duplicate nghiệp vụ.
- Member cũ khi quay lại đồng bộ phù hợp.

## 16. Kịch bản C: mất cả AZ

Nếu mục tiêu là chịu lỗi AZ, test phải đánh giá **toàn bộ các voting members trong AZ**, không chỉ một process.

Ví dụ ba voter ở ba AZ:

~~~text
AZ-A: mongo-a PRIMARY
AZ-B: mongo-b SECONDARY
AZ-C: mongo-c SECONDARY
~~~

Mất AZ-A → còn 2/3 votes. Mất AZ-B → primary ở AZ-A còn quorum với AZ-C.

Nhưng nếu AZ-A chứa **hai voter** trong topology 2–1, mất toàn AZ-A khiến phía còn lại không còn majority.

### 16.1. Cần kiểm tra client routing

Cluster có primary mới không đủ nếu:

- Client chỉ được phép kết nối host của AZ đã mất.
- DNS/firewall không cho đi tới AZ còn sống.
- Secret hoặc certificate cần thiết không khả dụng.
- Ứng dụng còn phụ thuộc dịch vụ khác trong AZ lỗi.

Cần test từ **cùng network với ứng dụng**, không chỉ từ máy của DBA.

### 16.2. Điều kiện dừng

Dừng fault injection nếu một AZ thứ hai trở nên bất thường, API error vượt ngưỡng, replication lag tăng quá mức hoặc mất khả năng rollback. Không tiếp tục tạo lỗi để hoàn thành kịch bản cho bằng được.

## 17. Kịch bản D: network partition

Network partition có thể khiến node còn chạy nhưng không kết nối được với majority.

~~~text
Phía A: mongo-a
Phía B: mongo-b <-> mongo-c

V = 3, majority = 2
~~~

Phía B có quorum. Phía A không thể bầu primary mới; primary cũ bị cô lập không thể duy trì khả năng ghi ổn định khi đã mất majority theo cơ chế election.

### 17.1. Đo từ cả hai phía

- Phía majority có primary và majority writes không?
- Phía minority phản ứng thế nào khi không còn quorum?
- Client phía minority gặp server selection/network/write concern errors gì?
- Khi mạng phục hồi, các member hội tụ về cùng một lịch sử hợp lệ ra sao?
- Có write chưa majority-acknowledged phải rollback không?

Kết quả rs.status từ một node là **góc nhìn của node đó**, không phải mô tả toàn bộ partition. Thu thập log và telemetry từ nhiều phía nếu có thể.

### 17.2. Không ngẫu nhiên chia mạng production

Phân vùng mạng có thể gây timeout hàng loạt, election và retry storm. Chỉ thử khi có công cụ hoàn nguyên network, người trực và ngưỡng dừng cụ thể.

## 18. Kịch bản E: cluster đã suy giảm rồi mất thêm voter

~~~text
Ban đầu: 3 voter
mongo-a healthy
mongo-b healthy
mongo-c offline

Còn 2/3 -> đúng majority
~~~

Nếu mongo-b mất tiếp:

~~~text
Chỉ còn mongo-a
1/3 không đủ majority
~~~

Cluster có primary hiện tại chưa chắc có dự phòng để chịu thêm sự cố.

Quy tắc vận hành thường là:

- Tạm dừng bảo trì làm offline voter khác.
- Phục hồi member lỗi trước.
- Kiểm tra oplog window để node offline còn bắt kịp.
- Theo dõi replication lag và lỗi network.
- Chỉ tiếp tục rollout sau khi redundancy trở lại, theo chính sách được phê duyệt.

## 19. Đo thời gian failover từ ứng dụng

Một báo cáo test nên ghi:

~~~text
T0: bắt đầu gây lỗi
T1: primary cũ không sử dụng được
T2: primary mới được bầu
T3: driver nhận topology mới
T4: application majority write thành công
T5: member lỗi quay lại và đồng bộ xong
~~~

Hai chỉ số:

- **Server election duration:** đo hành vi bầu primary.
- **Application recovery duration:** tính từ lúc lỗi tới lúc API phục vụ lại theo tiêu chí.

### 19.1. Mẫu bảng báo cáo

| Metric | Baseline | Khi lỗi | Sau phục hồi |
| --- | --- | --- | --- |
| Reachable voters | 3/3 | 2/3 | 3/3 |
| Primary | mongo-a | Bầu mongo-b | Ổn định |
| Majority write p95 | 20 ms | Có thể timeout | 22 ms |
| Driver errors | Không | Có tạm thời | Hết |
| Replication lag | Thấp | Node lỗi không nhận | Giảm dần |
| Majority acknowledged probes | Đầy đủ | Theo dõi | Đối soát |
| Duplicate business requests | Không | Không nếu idempotent | Không |

**Các con số độ trễ chỉ là ví dụ minh họa**, không phải cam kết hiệu năng của MongoDB.

### 19.2. Không gộp mọi lỗi thành “MongoDB down”

Phân biệt no writable primary, server selection timeout, network timeout, write concern error, transaction transient errors, unknown commit result và HTTP request timeout ở tầng ứng dụng. Cách phục hồi và retry khác nhau.

## 20. Connection string và driver discovery

URI replica set minh họa:

~~~text
mongodb://mongo-a.example.net:27017,mongo-b.example.net:27017,mongo-c.example.net:27017/?replicaSet=rs0&retryWrites=true
~~~

Điều kiện quan trọng:

1. Mọi hostname MongoDB quảng bá phải được client resolve.
2. Client kết nối được tới các node ở vùng còn sống.
3. replicaSet name chính xác.
4. TLS/auth/firewall tương thích.
5. Driver được phép khám phá topology và primary mới.

Nếu ứng dụng ép **directConnection=true** tới primary cũ, hành vi failover không giống kết nối replica set đầy đủ.

### 20.1. Timeouts là một phần của SLO

Server selection timeout quá ngắn làm request lỗi trước khi cluster hoàn tất election. Timeout quá dài có thể khiến request tích tụ.

Hãy đo failover thật để chọn timeout của driver và HTTP API. Không có bộ con số đúng cho mọi ứng dụng.

### 20.2. Retryable writes không thay thế idempotency

Nếu response bị mất sau khi server tạo đơn hàng, retry ở tầng business với orderId mới có thể tạo đơn trùng, dù MongoDB driver hỗ trợ retryable writes cho một số operation.

Một business idempotency key có thể giúp phân biệt cùng yêu cầu được thử lại với yêu cầu mới.

## 21. Java Sync Driver: majority write probe

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Date;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public class ReplicaSetFailoverProbe {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu MONGODB_URI của replica set"
            );
        }

        MongoClientSettings settings = MongoClientSettings.builder()
                .applyConnectionString(new ConnectionString(uri))
                .applyToClusterSettings(builder ->
                        builder.serverSelectionTimeout(
                                15, TimeUnit.SECONDS
                        )
                )
                .writeConcern(
                        WriteConcern.MAJORITY.withWTimeout(
                                10, TimeUnit.SECONDS
                        )
                )
                .readConcern(ReadConcern.MAJORITY)
                .build();

        try (MongoClient client = MongoClients.create(settings)) {
            MongoCollection<Document> probe = client
                    .getDatabase("ha_test_lab")
                    .getCollection("probe");

            String requestId = "HA-" + UUID.randomUUID();

            Document event = new Document("_id", requestId)
                    .append("createdAt", new Date())
                    .append("type", "majority-probe");

            long started = System.nanoTime();

            probe.insertOne(event);

            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started
            );

            System.out.println(
                    "requestId=" + requestId
                    + ", elapsedMs=" + elapsedMs
            );
        }
    }
}
~~~

Một lần probe thành công chưa đủ đánh giá failover. Trong bài test thực tế, lặp các thao tác có cadence giới hạn và ghi success/error/latency qua toàn thời gian sự cố.

### 21.1. Giữ nguyên requestId khi retry cùng nghiệp vụ

UUID trong ví dụ được tạo **một lần cho một probe mới**. Nếu cần retry **cùng business request**, phải giữ ID đã tạo; không tạo UUID mới ở mỗi lần retry rồi nghĩ rằng database tự loại trùng.

### 21.2. Xử lý lỗi không rõ kết quả

~~~java
try {
    probe.insertOne(event);
} catch (com.mongodb.MongoException e) {
    System.err.println("Mongo code: " + e.getCode());
    System.err.println("Message: " + e.getMessage());

    // Không mặc định write chưa xảy ra khi timeout.
    // Kiểm tra trạng thái theo requestId.
    throw e;
}
~~~

Với transaction, cần xử lý các labels như **TransientTransactionError** và **UnknownTransactionCommitResult** theo hướng dẫn driver.

## 22. Khôi phục member sau bài test

Một quy trình phục hồi:

1. Hoàn nguyên network/process gây lỗi.
2. Kiểm tra member kết nối lại replica set.
3. Kiểm tra state và health.
4. Theo dõi replication lag và oplog catch-up.
5. Xác định có cần initial sync không.
6. Đối soát dữ liệu majority-acknowledged.
7. Kiểm tra ứng dụng ngừng lỗi.
8. Chỉ đóng bài test khi redundancy trở lại.

### 22.1. Node online chưa chắc đã đồng bộ

Nếu node offline lâu hơn oplog window còn phù hợp, nó có thể cần initial sync. Mở port và trả lời ping không đồng nghĩa nó đã là secondary cập nhật đầy đủ.

### 22.2. Primary cũ có thể trở lại thành secondary

Sau failover, primary mới có thể giữ vai trò khi primary cũ trở lại. Không nên ép đổi primary thêm lần nữa chỉ để phục hồi hình thức ban đầu, vì sẽ tạo gián đoạn không cần thiết.

### 22.3. Force reconfig có rủi ro

Khi mất majority, không tự thay votes, force reconfigure hoặc xóa dữ liệu một node để ép cluster hoạt động. Phải biết trạng thái các member, nguyên nhân phân vùng và quy trình DR đúng phiên bản, có backup và phê duyệt phù hợp.

## 23. Replica set không thay thế backup

Một thao tác xóa hợp lệ nhưng sai nghiệp vụ:

~~~javascript
db.orders.deleteMany({
  status: "PAID"
});
~~~

có thể được replication tới mọi secondary. Khi đó cả ba AZ đều khỏe nhưng document đã bị xóa ở tất cả bản sao.

Backup/PITR là cơ chế phục hồi theo điểm thời gian, không phải một tính năng được thay thế hoàn toàn bởi replica set.

Cần xem:

- Backup có ở failure domain độc lập không?
- Có kiểm thử restore định kỳ không?
- Có khóa mã hóa và credential khi Region mất không?
- Có retention và bảo vệ chống xóa nhầm không?
- RTO/RPO của backup có đáp ứng nghiệp vụ không?

## 24. Local lab và kiểm thử vùng lỗi thật

Một replica set ba container trên một máy có thể học election nhưng không thể chứng minh chịu mất host:

~~~text
Một host
├── mongo-a
├── mongo-b
└── mongo-c
~~~

Lab minh họa config:

~~~javascript
rs.initiate({
  _id: "rs0",
  members: [
    {
      _id: 0,
      host: "mongo-a.lab.example:27017",
      votes: 1,
      priority: 1
    },
    {
      _id: 1,
      host: "mongo-b.lab.example:27017",
      votes: 1,
      priority: 1
    },
    {
      _id: 2,
      host: "mongo-c.lab.example:27017",
      votes: 1,
      priority: 1
    }
  ]
});
~~~

Các hostname trên chỉ là placeholder và phải được thay bằng địa chỉ mà mọi member và client đều resolve được, với TLS/auth/network/storage tương ứng.

Muốn kiểm chứng mất AZ, phải có các node đặt trên AZ độc lập hoặc một môi trường mô phỏng đáng tin cậy các dependency tương ứng.

## 25. Runbook tổng hợp cho một game day

### Giai đoạn A – Chuẩn bị

- Xác định kịch bản mất secondary/primary/AZ/partition.
- Chốt topology và bảng votes/priority/data-bearing.
- Tính quorum sau sự cố.
- Xác nhận backup và oplog window.
- Thu thập baseline.
- Định nghĩa workload probe.
- Ghi ngưỡng dừng và người trực.
- Bảo đảm có cách hoàn nguyên từ vùng lỗi khác.

### Giai đoạn B – Gây lỗi có kiểm soát

- Ghi T0 và ID của node/vùng lỗi mục tiêu.
- Chỉ gây đúng lỗi đã được phê duyệt.
- Theo dõi rs.status, election logs và replication.
- Ghi success/error/latency từ client.
- Dừng ngay khi vượt blast radius hoặc ngưỡng an toàn.

### Giai đoạn C – Khôi phục

- Hoàn nguyên network/process.
- Xác nhận member trở lại trạng thái phù hợp.
- Theo dõi replication catch-up/initial sync.
- Kiểm tra majority-acknowledged writes và duplicate.
- Xác nhận API ổn định và redundancy đã phục hồi.

### Giai đoạn D – Báo cáo

~~~text
Scenario:
Replica set:
Members per AZ/Region:
Voting majority:
Fault injected at:
Primary elected at:
API write restored at:
RTO measured:
Write concern errors:
Replication recovery:
Data reconciliation:
Unexpected duplicates/rollbacks:
Pass / Fail:
Actions:
~~~

Không coi một test **PASS** nếu chỉ có primary mới nhưng ứng dụng vẫn timeout hoặc redundancy chưa khôi phục.

## 26. Những sai lầm thường gặp

| Sai lầm | Giải thích |
| --- | --- |
| Có 3 mongod là chịu được mất AZ | Phải xem các mongod có cùng AZ/rack/host không |
| Dùng số process để tính majority | Phải dùng voting members |
| Ưu tiên primary bằng priority thay cho phân bố vote | Priority không tăng quorum |
| Arbiter là bản sao dữ liệu | Arbiter không lưu dữ liệu |
| Priority-0 nghĩa là không góp vote | Priority khác votes |
| Non-voting secondary giúp tăng election majority | votes: 0 không tham gia quorum |
| 5 voter ở 2 Region chắc chắn chịu mất Region bất kỳ | 3–2 không chịu mất Region có 3 voter |
| Đủ election majority là đủ majority write | Cần đánh giá bản sao dữ liệu và write concern |
| wtimeout chứng tỏ write chưa xảy ra | Kết quả có thể chưa rõ |
| Primary mới xuất hiện là API đã hồi phục | Driver còn phải phát hiện và kết nối |
| Ping một mongod chứng minh cluster khỏe | Ping không kiểm tra quorum/majority write |
| StepDown mô phỏng mất AZ hoàn chỉnh | Chỉ kiểm tra chuyển primary |
| Ba container trên một host là ba failure domain | Vẫn chung host |
| Node online là đã bắt kịp oplog | Cần theo dõi replication |
| Retry sau timeout luôn an toàn | Cần idempotency |
| Replica set là backup | Thao tác xóa sai vẫn được replication |
| Force reconfig là cách chữa quorum bình thường | Có nguy cơ dữ liệu khi dùng không đúng |

## 27. Bài thực hành

### Bài 1 – Ba voter trên ba AZ

~~~text
AZ-A: 1 voter
AZ-B: 1 voter
AZ-C: 1 voter
~~~

Tính majority; mất một AZ còn bao nhiêu voter? Nếu member còn lại là data-bearing eligible members và network bình thường, có thể bầu primary không?

### Bài 2 – Ba voter 2–1

~~~text
AZ-A: 2 voter
AZ-B: 1 voter
~~~

So sánh mất AZ-A, mất AZ-B và chỉ mất một host ở AZ-A. Vì sao topology này không đáp ứng yêu cầu mất AZ bất kỳ?

### Bài 3 – Năm voter 2–2–1 và 3–1–1

Tính số voter còn lại khi mỗi AZ mất. Giải thích vì sao 2–2–1 có đặc tính quorum tốt hơn 3–1–1 đối với yêu cầu chịu mất một AZ.

### Bài 4 – PSA

Một arbiter, một primary dữ liệu và một secondary dữ liệu ở ba AZ. Có mấy bản sao dữ liệu? Nếu secondary dữ liệu mất, số phiếu còn và khả năng xác nhận w:majority khác nhau thế nào?

### Bài 5 – Mất primary trong lab

1. Thu thập rs.status.
2. Chạy probe majority write.
3. Thử stepDown có kiểm soát hoặc làm primary offline trong môi trường được phép.
4. Đo thời gian có primary mới.
5. Đo thời gian client ghi thành công lại.
6. Khôi phục node và kiểm tra replication.

Giải thích vì sao hai thời gian bước 4 và 5 có thể khác nhau.

### Bài 6 – Network partition 1–2

Ba voter bị chia thành nhóm một và nhóm hai. Phía nào có quorum? Phía một có thể tiếp tục majority write không? Khi mạng hồi phục phải kiểm tra dữ liệu và log gì?

### Bài 7 – Cluster đã suy giảm

Ba voter, một đang offline. Một đợt maintenance định restart voter thứ hai. Hãy tính majority sau restart và đưa quyết định có nên thực hiện không.

### Bài 8 – Duplicate order do retry

Client gửi order rồi timeout ngay sau khi server đã ghi. Client retry với ID mới và tạo order thứ hai. Thiết kế business request ID cố định, unique index hoặc upsert/idempotency để tránh trùng.

### Bài 9 – Đa Region

So sánh 3 voter 1–1–1 với 5 voter 2–2–1 trên ba Region. Phân tích quorum, latency majority write, network partition và chi phí.

### Bài 10 – Backup

Một deleteMany sai được nhân bản trên mọi secondary. Vì sao replica set không thể tự khôi phục phiên bản trước khi xóa? Thiết kế backup/PITR và test restore.

### Bài 11 – Bảng inventory

Lập bảng gồm host, rack, AZ, Region, votes, priority, data-bearing, hidden, delayed, replication lag. Từ bảng tính số vote mất khi mỗi failure domain bị cô lập.

### Bài 12 – Viết runbook

Soạn quy trình test mất AZ chứa primary: preflight, probe, injection, metric, điều kiện dừng, khôi phục, reconciliation và báo cáo RTO/RPO thực đo.

## 28. Checklist thiết kế trước production

1. Xác định tất cả failure domain liên quan.
2. Ghi rõ vị trí mỗi voting và data-bearing member.
3. Tính majority sau khi mất từng vùng lỗi.
4. Xác nhận còn primary candidate hợp lệ.
5. Kiểm tra khả năng majority writes với bản sao còn lại.
6. Đo replication lag và độ trễ xuyên AZ/Region.
7. Kiểm tra driver URI, DNS, firewall, TLS và auth.
8. Định nghĩa SLO/RTO/RPO thực tế.
9. Thiết kế retry/idempotency.
10. Có monitoring server, client và ứng dụng.
11. Thử mất secondary, primary, AZ và partition.
12. Chuẩn bị cách hoàn nguyên network/process.
13. Có backup/PITR độc lập và thử restore.
14. Đo dữ liệu acknowledged và duplicate sau lỗi.
15. Chỉ đóng test khi member trở lại đủ redundancy.

## 29. Kết luận

Một replica set có khả năng chịu lỗi khi các thành viên được **phân bố đúng theo failure domain** và sau sự cố vẫn còn:

- **Election majority** của voting members.
- Một **data-bearing candidate** đủ điều kiện để làm primary.
- Khả năng **nhân bản và xác nhận write** theo yêu cầu.
- Client có thể khám phá primary mới và retry an toàn.

Với ba data-bearing voters ở ba AZ, mất một AZ vẫn có thể còn 2/3 phiếu. Với năm voter phân bố 2–2–1, mất một AZ còn ít nhất 3/5 phiếu. Ngược lại, phân bố 2–1 hoặc 3–1–1 có vùng lỗi chứa quá nhiều vote.

Kiểm thử đúng không chỉ dừng ở **rs.status báo một primary mới**. Cần gây lỗi có kiểm soát, đo thời gian phục hồi ở tầng ứng dụng, bảo vệ majority-acknowledged writes, kiểm tra idempotency, khôi phục member và quan sát replication cho tới khi redundancy trở lại. Và cuối cùng, **replica set không thay thế backup hoặc disaster recovery**.

## Tài liệu tham khảo

- [MongoDB Manual — Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-members/)
- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [MongoDB Manual — Replica Set High Availability](https://www.mongodb.com/docs/manual/core/replica-set-high-availability/)
- [MongoDB Manual — Deploy a Replica Set](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [MongoDB Manual — Replica Set Arbiter](https://www.mongodb.com/docs/manual/core/replica-set-arbiter/)
- [MongoDB Manual — Hidden Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-hidden-member/)
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — rs.status()](https://www.mongodb.com/docs/manual/reference/method/rs.status/)
- [MongoDB Manual — rs.conf()](https://www.mongodb.com/docs/manual/reference/method/rs.conf/)
- [MongoDB Manual — rs.stepDown()](https://www.mongodb.com/docs/manual/reference/method/rs.stepDown/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
