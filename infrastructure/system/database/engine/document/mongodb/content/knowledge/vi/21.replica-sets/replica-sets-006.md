# Bầu chọn, stepdown và xử lý kết nối khi chuyển primary trong MongoDB Replica Set

## 1. Bối cảnh và mục tiêu

MongoDB replica set là một nhóm tiến trình `mongod` cùng duy trì các bản sao của một tập dữ liệu. Tại một thời điểm vận hành bình thường, replica set có **một primary** nhận các thao tác ghi thông thường; các thành viên **secondary** sao chép các thao tác từ primary để duy trì tính sẵn sàng và hỗ trợ khôi phục.

Nhưng primary không phải một địa chỉ máy chủ bất biến. Nó có thể:

- Gặp sự cố hệ điều hành, phần cứng hoặc mạng.
- Mất khả năng liên lạc với đủ thành viên bỏ phiếu.
- Được quản trị viên chủ động yêu cầu **step down** để bảo trì.
- Bị thay thế sau thay đổi cấu hình hoặc một cuộc bầu chọn.
- Khởi động lại sau một lần bảo trì rồi trở thành secondary.

Ứng dụng thường không cần biết *máy nào* sẽ là primary mãi mãi. Ứng dụng cần biết **cách tìm primary hiện tại**, **đối phó với khoảng thời gian chưa có primary**, và **không làm mất hoặc lặp thao tác nghiệp vụ khi retry**.

Bài học thuộc chương **Replica set** của module **Database Engine Document MongoDB**, tập trung vào ba chủ đề:

1. **Bầu chọn (election):** thành viên nào được bầu, cần bao nhiêu phiếu, vì sao mạng bị chia cắt ảnh hưởng tới khả năng ghi.
2. **Stepdown:** primary chủ động rời vai trò, cách thực hiện bảo trì an toàn và các tác động lên request đang chạy.
3. **Xử lý kết nối khi chuyển primary:** seed list, topology discovery, retryable reads/writes, write concern, giao dịch, idempotency và giám sát.

Sau bài này, bạn có thể phân tích một đợt failover mà không nhầm giữa **kết nối TCP vẫn còn**, **có primary mới**, **một thao tác đã được thực hiện** và **một thao tác đã được xác nhận thành công với client**.

> **Ý chính:** Failover không bảo đảm mọi request đều thành công liên tục. MongoDB và driver giúp tự khám phá primary mới, nhưng ứng dụng vẫn cần chính sách retry, timeout, xác thực kết quả và thao tác nghiệp vụ có thể thực hiện an toàn khi gặp lỗi tạm thời.

## 2. Từ một node đơn lẻ đến replica set

Một triển khai đơn lẻ:

~~~text
Application
     |
     v
  mongod
  (một node)
~~~

Khi node đó ngừng hoạt động, ứng dụng không có node thay thế trong cùng deployment.

Một replica set ba thành viên điển hình:

~~~text
                       Replica set rsDemo
                 +-----------------------------+
                 |                             |
Application ---->|  node-a:27017  PRIMARY      |
                 |      |                      |
                 |      | oplog replication    |
                 |      +-------------------+  |
                 |      |                   |  |
                 |      v                   v  |
                 |  node-b:27017       node-c:27017
                 |  SECONDARY          SECONDARY
                 |                             |
                 +-----------------------------+
~~~

Các secondary nhận dữ liệu bằng cách sao chép và áp dụng những thay đổi từ oplog theo cơ chế replication. Tên host ở sơ đồ là ví dụ; trong triển khai thật, chúng phải là các địa chỉ có thể phân giải và kết nối được giữa thành viên và từ ứng dụng.

### 2.1. Vai trò khác với cấu hình cố định

| Thuật ngữ | Ý nghĩa |
|---|---|
| `PRIMARY` | Thành viên đang giữ quyền primary; nhận ghi thông thường |
| `SECONDARY` | Thành viên đồng bộ dữ liệu từ replica set, có thể ứng cử nếu đủ điều kiện |
| `ARBITER` | Thành viên tham gia bỏ phiếu nhưng không lưu dữ liệu |
| `STARTUP`, `RECOVERING`, `ROLLBACK` và trạng thái khác | Những trạng thái trong vòng đời node; không mặc định sẵn sàng ghi |
| `priority` | Mức ưu tiên tương đối khi thành viên đủ điều kiện ứng cử |
| `votes` | Khả năng tham gia bỏ phiếu bầu chọn |
| `term` | Nhiệm kỳ bầu chọn dùng trong cơ chế election/replication |

Role `PRIMARY` là trạng thái động. Node-a có thể là primary buổi sáng và secondary sau một cuộc bầu chọn. Ứng dụng không nên mã hóa cứng “node-a là máy ghi”.

### 2.2. Dữ liệu replication và đường ghi

Thao tác ghi thông thường cần gửi tới primary:

~~~text
Client
  |
  v
PRIMARY ---- oplog ---> SECONDARY 1
    |
    +-------- oplog ---> SECONDARY 2
~~~

Khi client yêu cầu write concern `w: "majority"`, xác nhận thành công đòi hỏi số lượng thành viên lưu dữ liệu cần thiết đã ghi nhận thao tác theo quy tắc majority của topology. Điều đó khác với việc primary đơn thuần chấp nhận thao tác bằng `w:1`.

**Không nên coi secondary luôn cập nhật tức thời bằng primary.** Replication có thể trễ, và lựa chọn read preference/read concern ảnh hưởng cách ứng dụng quan sát dữ liệu sau failover.

## 3. Cơ chế bầu chọn primary

Một cuộc bầu chọn có thể diễn ra khi:

- Primary hiện tại không còn đáp ứng heartbeat hoặc mất khả năng duy trì vai trò.
- Primary chủ động step down.
- Cấu hình hoặc mức ưu tiên khiến thành viên đủ điều kiện có thể trở thành primary.
- Một quá trình phục hồi/khởi động lại dẫn tới thay đổi topology.

Một secondary **đủ điều kiện** có thể trở thành ứng cử viên và xin phiếu từ các thành viên được cấu hình để bỏ phiếu. MongoDB cần đạt **đa số phiếu của tập thành viên bỏ phiếu** theo cấu hình để bầu primary mới.

### 3.1. Majority/quorum

Trong cấu hình có `V` thành viên bỏ phiếu, số phiếu đa số là:

\[
\text{majorityVotes}=\left\lfloor\frac{V}{2}\right\rfloor+1
\]

| Thành viên bỏ phiếu | Phiếu đa số cần có |
|---:|---:|
| 1 | 1 |
| 2 | 2 |
| 3 | 2 |
| 4 | 3 |
| 5 | 3 |
| 7 | 4 |

Ví dụ ba thành viên có một phiếu mỗi node:

~~~text
node-a: 1 vote
node-b: 1 vote
node-c: 1 vote

Tổng: 3 votes
Majority: 2 votes
~~~

Khi node-a lỗi, node-b và node-c vẫn có thể đạt hai phiếu và bầu primary mới nếu thỏa các điều kiện về khả năng ứng cử, trạng thái và độ cập nhật dữ liệu.

Nếu chỉ node-b còn hoạt động và không liên lạc được với hai node còn lại, **một phiếu không đủ tạo primary** trong cấu hình ba voter. Đây là một giới hạn có chủ đích để bảo vệ tính nhất quán vai trò khi mạng bị chia cắt.

### 3.2. Vì sao thường chọn số voter lẻ?

Trong các cấu hình phổ biến, ba hoặc năm thành viên bỏ phiếu thường mang lại tỷ lệ chịu lỗi hữu ích:

- Với 3 voter, cần 2 phiếu; mất 1 voter vẫn có thể có majority.
- Với 5 voter, cần 3 phiếu; mất 2 voter vẫn có thể có majority.
- Với 4 voter, cần 3 phiếu; cũng chỉ chịu được mất 1 voter như cấu hình 3 voter về mặt phiếu đa số.

Vì vậy, thêm voter thứ tư vào ba voter **không tự tăng** số thành viên có thể mất mà vẫn duy trì majority. Tuy nhiên, khả năng failover thực tế còn phụ thuộc topology mạng, số data-bearing members, độ cập nhật và cấu hình voting.

MongoDB cho phép tối đa **7 thành viên bỏ phiếu** trong một replica set; số lượng thành viên tổng thể và các ràng buộc bổ sung cần đối chiếu đúng phiên bản server. Không nên tăng số voting member chỉ để “primary đổi nhanh hơn”.

### 3.3. Bầu chọn không chỉ dựa vào phiếu

Một ứng cử viên còn phải thỏa các điều kiện như:

- Là thành viên có khả năng trở thành primary, không phải arbiter.
- Có cấu hình `priority` thích hợp (khác 0).
- Có tình trạng replication/độ cập nhật đủ điều kiện theo cơ chế election.
- Không ở trạng thái đang initial sync, recovering hoặc trạng thái không thể ứng cử.
- Đáp ứng các điều kiện theo term và cấu hình replica set.

Vì vậy, **đủ phiếu nhưng không có secondary đủ điều kiện** vẫn có thể dẫn đến khoảng thời gian không có primary.

### 3.4. Term và ngăn primary cũ tiếp tục ghi

MongoDB sử dụng các cơ chế election term và replication để phối hợp thay đổi lãnh đạo. Khi một node phát hiện mình không thể duy trì vai trò primary, nó phải rời vai trò đó theo cơ chế hệ thống.

Một client đang kết nối TCP tới primary cũ **không có nghĩa node ấy còn quyền nhận ghi**. Driver cần cập nhật topology; thao tác mới có thể bị trả lỗi kiểu not-primary rồi được định tuyến lại hoặc retry theo chính sách hỗ trợ.

Không dựa vào việc một host “vẫn ping được” để kết luận host đó là primary hợp lệ.

## 4. Ba kịch bản mạng làm rõ quy tắc majority

### 4.1. Primary mất kết nối, hai secondary còn thấy nhau

~~~text
Trước:
A (PRIMARY) ---- B (SECONDARY)
      \          /
       \        /
        C (SECONDARY)

Sau sự cố:
A  X      B <----> C
(isolated)   có 2/3 votes
~~~

B và C có thể bầu một primary mới nếu đủ điều kiện. A không thể tiếp tục giữ vai trò primary hợp lệ vô thời hạn khi mất khả năng duy trì majority.

### 4.2. Hai node không liên lạc được, chỉ một node sống

~~~text
A  X       B  X       C
                       |
                  1/3 vote
                  không có majority
~~~

C không tự bầu làm primary chỉ vì là node duy nhất còn chạy. Ứng dụng cần xử lý giai đoạn không có primary, thay vì cố gửi ghi trực tiếp vào C.

### 4.3. Network partition thành hai nhóm

~~~text
Nhóm 1: A + B            Nhóm 2: C
          2 votes                 1 vote

   Có khả năng bầu              Không đạt majority
   một primary hợp lệ           để bầu primary
~~~

Cơ chế majority và term giúp tránh việc hai phía cùng duy trì hai primary hợp lệ trong cùng một cấu hình nhất quán. Nhưng trong những khoảng chuyển tiếp, một client có thể tạm thấy trạng thái cũ hoặc nhận lỗi; cần để driver cập nhật topology thay vì dùng kết quả heartbeat cũ làm quyền ghi.

### 4.4. Quorum không đồng nghĩa mọi request đều thành công

Ngay cả khi nhóm B+C đã bầu primary mới:

- Client còn giữ kết nối tới A có thể gặp lỗi.
- Driver cần phát hiện và chọn server mới.
- Một write đang bay có thể có kết quả không rõ với ứng dụng.
- Transaction có thể bị hủy hoặc commit chưa rõ.
- Secondary reads có thể thấy dữ liệu ở thời điểm khác.

Cơ chế bầu chọn giải quyết **ai có thể là primary**, không trực tiếp giải quyết **ngữ nghĩa retry của mọi API nghiệp vụ**.

## 5. priority, votes và vai trò các thành viên

Một thành viên có hai tham số dễ nhầm:

- `votes`: thành viên có tham gia bỏ phiếu hay không, thường là 0 hoặc 1.
- `priority`: mức ưu tiên làm primary nếu thành viên đủ điều kiện ứng cử.

Ví dụ cấu hình khái niệm:

~~~javascript
{
  _id: "rsDemo",
  members: [
    {
      _id: 0,
      host: "node-a.example.test:27017",
      votes: 1,
      priority: 2
    },
    {
      _id: 1,
      host: "node-b.example.test:27017",
      votes: 1,
      priority: 1
    },
    {
      _id: 2,
      host: "node-c.example.test:27017",
      votes: 1,
      priority: 0
    }
  ]
}
~~~

Đây chỉ là **mẫu minh họa cấu hình**, không phải lệnh cần chạy. Node-c vẫn có thể bỏ phiếu nhưng với `priority:0` thì không được bầu thành primary.

### 5.1. Priority cao có thắng mọi lúc không?

Không. Priority ảnh hưởng ưu tiên trong điều kiện thích hợp; node ưu tiên cao còn cần online, đủ điều kiện, đồng bộ và có khả năng được bầu. Nó không thể buộc một node cô lập hoặc quá lạc hậu trở thành primary ngay.

Dùng priority để diễn đạt mong muốn phân bố vai trò theo hạ tầng; không dùng priority để bỏ qua quy tắc majority.

### 5.2. Priority 0

Một secondary có `priority:0` không được bầu làm primary nhưng có thể tiếp tục đồng bộ và phục vụ những read được phép theo cấu hình. Nó vẫn có thể là voter nếu `votes:1`.

Tình huống sử dụng: node ở khu vực xa hoặc node dành cho một mục đích đọc/báo cáo, nơi bạn không muốn node đó trở thành primary.

### 5.3. Hidden secondary

Hidden secondary là một kiểu secondary không được ứng dụng thông thường chọn như một thành viên đọc qua cơ chế discovery bình thường; nó được cấu hình không đủ điều kiện làm primary, và có thể dùng cho workload chuyên dụng tùy thiết kế.

Không nên nhầm hidden với “không còn trong replica set”. Node vẫn tham gia replication; cấu hình bỏ phiếu và độ sẵn sàng cần xem cụ thể.

### 5.4. Arbiter

Arbiter bỏ phiếu nhưng **không lưu dữ liệu** và không thể trở thành primary. Cấu hình có arbiter thường được gọi là PSA (Primary–Secondary–Arbiter).

Lợi ích giới hạn: có thêm voter khi không thể có thêm data-bearing member.

Đánh đổi:

- Arbiter không cung cấp thêm bản sao dữ liệu.
- Topology PSA có những tình huống phức tạp liên quan majority write concern và tính sẵn sàng ghi.
- Nó không thay thế việc có ba data-bearing members trong một thiết kế cần độ bền/khả năng khôi phục cao.

Khi có thể, ba thành viên lưu dữ liệu thường là lựa chọn dễ lý giải hơn cho thực hành bầu chọn và majority writes. Không tự thêm arbiter để chữa một sự cố quorum khi chưa phân tích topology.

## 6. Heartbeat, election timeout và thời gian chuyển primary

Các thành viên replica set định kỳ gửi heartbeat để nhận biết trạng thái nhau. Một số tham số thường thấy:

- `heartbeatIntervalMillis`: khoảng gửi heartbeat, thường mặc định 2 giây.
- `electionTimeoutMillis`: mốc timeout phục vụ phát hiện cần bầu chọn, thường mặc định 10 giây.

**Các giá trị mặc định này không phải SLA failover cố định.** Thời gian từ khi primary lỗi đến khi ứng dụng ghi thành công trở lại còn phụ thuộc:

1. Việc node khác nhận biết thay đổi.
2. Quá trình bầu chọn và tính sẵn sàng của ứng cử viên.
3. Độ trễ replication và yêu cầu catch-up.
4. Độ trễ mạng và tài nguyên CPU/I/O.
5. Thời gian driver cập nhật topology qua SDAM.
6. Cấu hình `serverSelectionTimeoutMS` và cơ chế retry.
7. Timeout, queue và load của ứng dụng.

Không cam kết “cứ đúng 10 giây sẽ có primary mới” chỉ vì election timeout có mặc định 10 giây.

### 6.1. Tại sao giảm election timeout không luôn tốt?

Giảm timeout quá mức trong mạng có độ trễ, packet loss hoặc hệ thống hay pause có thể khiến replica set bầu chọn quá thường xuyên, làm tăng gián đoạn.

Thay đổi election timeout là quyết định vận hành cần đo chất lượng mạng và đặc điểm cluster; không nên chỉnh tùy tiện để “failover tức thì”.

### 6.2. Khi nào có thể mất nhiều thời gian hơn?

- Secondary chưa bắt kịp oplog.
- Đang initial sync hoặc recovering.
- Hầu hết voter không liên lạc được.
- Node ứng cử viên thiếu tài nguyên.
- Thay đổi topology chưa được driver nhận biết.
- Client sử dụng sai connection string, chỉ gắn vào host cũ.

Điều quan trọng với ứng dụng là chịu được một khoảng **không có primary** và có cơ chế phản hồi phù hợp, không phụ thuộc vào một số giây tưởng tượng.

## 7. Stepdown là gì?

**Stepdown** là hành động primary rời vai trò primary. Quá trình này có thể được chủ động khởi phát để bảo trì hoặc được MongoDB thực hiện khi vai trò primary không còn phù hợp.

Với maintenance có kiểm soát, người quản trị có thể yêu cầu primary hiện tại step down để một secondary đủ điều kiện được bầu làm primary mới.

Sơ đồ:

~~~text
Trước stepdown:
node-a = PRIMARY
node-b = SECONDARY
node-c = SECONDARY

           |
           | rs.stepDown(...)
           v

Chuyển tiếp:
node-a = SECONDARY / đang rời PRIMARY
node-b = SECONDARY / ứng cử
node-c = SECONDARY
Có thể tạm không có PRIMARY

           |
           | election hoàn tất
           v

Sau:
node-a = SECONDARY
node-b = PRIMARY
node-c = SECONDARY
~~~

**Stepdown không bảo đảm node-b là người thắng.** Node nào trở thành primary phụ thuộc cấu hình, số phiếu, priority, độ cập nhật và trạng thái cluster.

### 7.1. Stepdown không phải shutdown

- `stepDown`: node rời vai trò primary nhưng tiến trình `mongod` có thể vẫn chạy và tiếp tục hoạt động như secondary.
- `shutdown`: dừng tiến trình.
- `rs.remove()`: thay đổi thành viên replica set.
- `rs.reconfig()`: thay đổi cấu hình replica set.

Các thao tác này khác nhau về rủi ro. Không dùng `rs.remove()` hoặc ép reconfig chỉ để mô phỏng một cuộc chuyển primary thông thường.

### 7.2. Khi nào chủ động step down?

Ví dụ:

- Bảo trì host đang là primary.
- Thực hiện quy trình nâng cấp rolling upgrade theo hướng dẫn của phiên bản server.
- Chuyển vai trò sang một node đủ điều kiện trước khi thay đổi hạ tầng.
- Thực hành failover trong môi trường test/staging để xác nhận ứng dụng có retry đúng.

Trong production, stepdown là hành động gây gián đoạn ghi ngắn hạn và có thể ngắt operation đang chạy. Cần quy trình phê duyệt, theo dõi và phương án khôi phục.

## 8. Xem trạng thái replica set trước khi thao tác

Giả sử bạn có replica set tên `rsDemo` với ba host đã cấu hình. Ví dụ URI ứng dụng:

~~~text
mongodb://node-a.example.test:27017,node-b.example.test:27017,node-c.example.test:27017/admin?replicaSet=rsDemo
~~~

Các tên miền `example.test` là placeholder, không phải endpoint MongoDB thật. Thay bằng hostname thực sự có trong cấu hình và truy cập được từ máy đang chạy mongosh.

Kết nối mongosh:

~~~bash
mongosh "mongodb://node-a.example.test:27017,node-b.example.test:27017,node-c.example.test:27017/admin?replicaSet=rsDemo"
~~~

Sau khi kết nối:

~~~javascript
rs.status();
~~~

Các trường thường quan sát được gồm tên set, term, state của các member, health và thông tin optime/heartbeat tùy phiên bản.

### 8.1. In trạng thái thành viên gọn hơn

~~~javascript
const status = rs.status();

printjson({
  set: status.set,
  term: status.term,
  members: status.members.map(m => ({
    name: m.name,
    state: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate,
    lastHeartbeatMessage: m.lastHeartbeatMessage
  }))
});
~~~

Ví dụ kết quả **minh họa**, không phải output cố định:

~~~javascript
{
  set: "rsDemo",
  term: NumberLong("12"),
  members: [
    {
      name: "node-a.example.test:27017",
      state: "PRIMARY",
      health: 1
    },
    {
      name: "node-b.example.test:27017",
      state: "SECONDARY",
      health: 1
    },
    {
      name: "node-c.example.test:27017",
      state: "SECONDARY",
      health: 1
    }
  ]
}
~~~

Đừng suy luận rằng chỉ `health:1` là đủ để node thay primary. Kiểm tra khả năng ứng cử, trạng thái replication và majority.

### 8.2. db.hello()

~~~javascript
db.hello();
~~~

Các field hữu ích khi có trong kết quả:

| Field | Ý nghĩa |
|---|---|
| `setName` | Tên replica set |
| `isWritablePrimary` | Node trả lời hiện có được coi là writable primary không |
| `secondary` | Node đang là secondary không |
| `primary` | Host được thông báo là primary hiện tại, nếu biết |
| `hosts` | Danh sách thành viên được discovery công bố |
| `me` | Địa chỉ của node đang trả lời |
| `electionId`, `topologyVersion` | Thông tin thay đổi topology khi được cung cấp |

`db.hello()` là một phép quan sát trạng thái **tại thời điểm lệnh trả về**. Vì election có thể diễn ra ngay sau đó, không nên dùng một lần `hello` để cam kết rằng host sẽ nhận ghi vô thời hạn.

### 8.3. rs.conf()

~~~javascript
rs.conf();
~~~

Xem cấu hình `members` với `host`, `votes`, `priority`, `hidden`, `arbiterOnly` và `settings` nếu có.

Không dùng kết quả `rs.conf()` như danh sách “các node chắc chắn đang healthy”. Cấu hình nói **ai được định nghĩa là thành viên**; `rs.status()` và các nguồn monitoring cho biết **trạng thái vận hành hiện tại**.

### 8.4. Kiểm tra tình trạng replication

Trước khi chủ động stepdown:

- Có đủ voter liên lạc được để hình thành majority không?
- Có secondary data-bearing đủ điều kiện bầu làm primary không?
- Secondary ứng cử đã bắt kịp dữ liệu đến mức nào?
- Có thành viên đang initial sync/rollback/recovering không?
- Workload đang có long-running write hoặc transaction quan trọng không?

Tùy phiên bản và quyền, có thể quan sát các field optime trong `rs.status()` hoặc dùng công cụ monitoring/replication lag của nhà cung cấp.

## 9. Lệnh rs.stepDown() và tham số

Trong `mongosh` kết nối tới **primary**, có thể yêu cầu:

~~~javascript
rs.stepDown();
~~~

Hoặc chỉ rõ tham số:

~~~javascript
rs.stepDown(60, 15);
~~~

Các đối số thường là:

| Tham số | Vai trò |
|---|---|
| `stepDownSecs` | Khoảng thời gian tính bằng giây mà primary cũ không đủ điều kiện ứng cử lại sau stepdown |
| `secondaryCatchUpPeriodSecs` | Khoảng đợi những secondary đủ điều kiện bắt kịp trước khi hoàn tất stepdown theo cơ chế command |

Ví dụ `rs.stepDown(60, 15)` yêu cầu primary cũ rời vai trò trong khoảng 60 giây theo ngữ nghĩa của lệnh và cho phép giai đoạn catch-up đến 15 giây. Nó **không** có nghĩa cluster chắc chắn không có primary trong 60 giây. Primary mới có thể được bầu sớm hơn nhiều.

Các giá trị mặc định thường gặp là 60 giây cho step-down period và 10 giây cho catch-up period, nhưng nên đối chiếu tài liệu phiên bản đang dùng.

### 9.1. Stepdown có thể trả lỗi hoặc ngắt kết nối

Trong quá trình stepdown, node cũ có thể đóng kết nối client và ngắt những thao tác đang chạy. Mongosh có thể thấy lỗi mạng hoặc lỗi not-primary ngay cả khi yêu cầu đã khiến node rời primary.

Do đó:

1. Không chỉ dựa vào một exception của shell để kết luận stepdown thất bại.
2. Kết nối lại bằng URI replica set chứa nhiều seed hosts.
3. Kiểm tra `rs.status()`, `db.hello()` và monitoring.
4. Xác nhận có primary mới và application health trở lại.

### 9.2. Bắt buộc phải có secondary đủ điều kiện

Một stepdown thông thường có thể từ chối thực hiện nếu không có secondary đủ điều kiện để tiếp nhận vai trò trong điều kiện yêu cầu, hoặc quá trình catch-up không thể hoàn tất phù hợp.

Điều này là cơ chế bảo vệ. Không nên ép stepdown khi cluster vốn đang chỉ còn một data-bearing member sẵn sàng, chỉ để “thử failover”.

### 9.3. Không dùng force làm cách xử lý mặc định

MongoDB có administrative command `replSetStepDown` hỗ trợ tham số `force` trong ngữ cảnh quản trị. Ép stepdown có thể làm gián đoạn khả năng ghi trong thời gian dài hơn và tăng rủi ro nếu không có secondary đủ điều kiện, đồng thời làm thay đổi bảo đảm về catch-up.

Đối với bài học và quy trình bảo trì thông thường, **không dùng `force:true`** trừ khi có runbook chuyên biệt và người quản trị hiểu tác động. Không thử force trên cluster sản xuất để xem lỗi có biến mất không.

### 9.4. Không chạy stepdown trên mongos hoặc standalone

`rs.stepDown()` dành cho replica set primary, không phải một lệnh chung để chuyển vai trò trên standalone `mongod` hoặc trực tiếp điều khiển mọi shard qua `mongos`.

Trong môi trường sharded, mỗi shard là một replica set riêng và có primary của shard; có thể còn cấu hình replica set cho config servers. Quy trình maintenance phải nhắm đúng thành phần và theo hướng dẫn triển khai.

## 10. Quy trình stepdown có kiểm soát

Dưới đây là **runbook khái niệm** dành cho một replica set trong test/staging hoặc khi đã có quy trình vận hành được phê duyệt.

### Giai đoạn A — Trước khi chuyển primary

1. Xác định replica set và tên host chính xác.
2. Kiểm tra `rs.status()`, `rs.conf()` và độ trễ replication.
3. Xác nhận số voting member đủ tạo majority.
4. Xác nhận ít nhất một secondary đủ điều kiện và có độ cập nhật phù hợp.
5. Đảm bảo ứng dụng kết nối bằng **replica set URI**, không pin vào primary cũ.
6. Xem các long-running operations/transactions hoặc batch writes nhạy cảm.
7. Đặt kênh giám sát request error, latency, server selection và election events.
8. Xác định người/nhóm chịu trách nhiệm, thời điểm bảo trì và phương án khôi phục.

### Giai đoạn B — Thực hiện

Trên primary và trong môi trường được phép:

~~~javascript
rs.stepDown(60, 15);
~~~

Mongosh có thể báo ngắt kết nối. Đó là một phần của quá trình cần được xác minh, không phải tín hiệu kết luận duy nhất.

### Giai đoạn C — Quan sát bầu chọn

Kết nối lại qua seed list và theo dõi:

~~~javascript
db.hello();
rs.status();
~~~

Đợi replica set công bố một node `PRIMARY` ổn định. Không gửi thủ công thao tác ghi tới một secondary chỉ vì nó đang reachable.

### Giai đoạn D — Xác nhận ứng dụng

- Driver có tìm được primary mới không?
- Ghi thử có ý nghĩa, có write concern phù hợp không?
- Error rate và thời gian chọn server có trở lại mức bình thường không?
- Có request với kết quả không rõ cần đối soát không?
- Có data lag hoặc long-running transaction chưa hoàn tất không?

Đối với kiểm tra nghiệp vụ, dùng lệnh có khóa idempotent và dữ liệu test, không ghi/sửa bản ghi production ngẫu nhiên.

### Giai đoạn E — Ghi nhận

Ghi lại thời điểm stepdown, primary cũ/mới, election term (nếu có), thời gian ngắt ghi quan sát thực tế, lỗi client, retry, kết quả đối soát và các thay đổi bất thường.

**Điểm quan trọng:** Runbook không kết thúc ở câu “mongosh in ra thành công”. Kết quả thật là **replica set ổn định và ứng dụng khôi phục hoạt động đúng**.

## 11. Thay primary tự động khi node gặp sự cố

Khác với planned stepdown, failover tự động có thể xảy ra mà không có thông báo trước.

~~~text
T0   node-a đang PRIMARY
T1   node-a gặp sự cố mạng / tiến trình
T2   secondary nhận biết trạng thái primary không còn hợp lệ
T3   ứng cử và bỏ phiếu
T4   node-b trở thành PRIMARY nếu đủ majority và hợp lệ
T5   driver cập nhật topology và định tuyến các ghi mới tới node-b
~~~

Các mốc chỉ có ý nghĩa thứ tự, **không phải số giây bảo đảm**.

### 11.1. Lỗi có thể quan sát từ ứng dụng

- Ghi vào primary cũ bị từ chối.
- Connection reset/closed.
- Không tìm được writable primary trong server selection deadline.
- Transaction bị ngắt.
- Command đang chạy bị interrupted do role change.
- Kết quả ghi chưa rõ do mất kết nối trước khi nhận ACK.

Khi thấy những lỗi này, không nên lập tức coi mọi write đều chưa thực hiện. Phải phân biệt **chưa thực hiện**, **đã thực hiện nhưng client mất phản hồi**, và **bị rollback** trong bối cảnh write concern và replication.

### 11.2. Primary cũ trở lại

Khi node-a khởi động lại hoặc nối lại mạng, nó thường tham gia như secondary và đồng bộ theo lịch sử được chọn của replica set.

Trong những trường hợp có các write cũ chưa được majority-committed, các write ấy có thể bị rollback khi node đi theo lịch sử của primary mới. Đây là một lý do quan trọng để dùng write concern phù hợp với yêu cầu độ bền.

Không mặc định primary cũ trở lại là lập tức được bầu primary lần nữa, hoặc rằng mọi write trước khi lỗi đều tồn tại trên primary mới.

## 12. Ứng dụng phải kết nối vào replica set, không pin vào primary cũ

### 12.1. Sai lầm: chỉ ghi một host

URI không đầy đủ cho yêu cầu HA:

~~~text
mongodb://node-a.example.test:27017/app
~~~

Tùy cách driver khám phá topology và cấu hình, một seed host vẫn có thể dẫn tới discovery của replica set. Nhưng chỉ có một host đầu vào làm giảm khả năng khởi tạo kết nối nếu host đó chết trước khi driver học được danh sách member.

Một trường hợp nguy hiểm hơn là **ép kết nối trực tiếp**:

~~~text
mongodb://node-a.example.test:27017/app?directConnection=true
~~~

Khi kết nối bị pin vào một host, ứng dụng không được thiết kế để tự chọn primary mới qua cơ chế replica set theo cách thông thường. Đây không phải URI phù hợp cho ứng dụng có yêu cầu tự động failover.

### 12.2. URI với nhiều seed hosts

Một URI rõ ràng cho replica set:

~~~text
mongodb://node-a.example.test:27017,node-b.example.test:27017,node-c.example.test:27017/app?replicaSet=rsDemo&retryWrites=true&retryReads=true&readPreference=primary&w=majority
~~~

Ý nghĩa:

| Thành phần | Vai trò |
|---|---|
| Nhiều host trong seed list | Driver có nhiều điểm khởi đầu để khám phá deployment |
| `replicaSet=rsDemo` | Xác nhận topology là replica set có tên mong muốn |
| `retryWrites=true` | Bật retryable writes cho những thao tác được hỗ trợ |
| `retryReads=true` | Bật retryable reads theo khả năng driver/command |
| `readPreference=primary` | Đọc qua primary theo chính sách đã chọn |
| `w=majority` | Yêu cầu majority write concern |
| `directConnection=false` (ngầm định trong cấu hình phổ biến) | Cho phép topology discovery thay vì pin một host |

**Tên host là ví dụ.** Trong production cần dùng hostname, TLS, authentication và mạng riêng theo chính sách tổ chức.

### 12.3. Server quảng bá danh sách host nào?

Driver không chỉ sử dụng chuỗi seed list. Nó hỏi trạng thái topology thông qua hello/SDAM và có thể khám phá thêm các hostname trong replica set config.

Nếu MongoDB quảng bá các hostname không phân giải được từ mạng ứng dụng, failover vẫn có thể thất bại dù seed host ban đầu kết nối được.

Kiểm tra cả:

- DNS, routing và firewall giữa client với các member.
- Hostname trong `rs.conf()`.
- TLS certificate name validation.
- Trường hợp Kubernetes, Docker, NAT hoặc môi trường nhiều mạng.
- Khả năng client liên lạc với **tất cả host có thể trở thành primary**.

### 12.4. mongodb+srv URI

Với dịch vụ triển khai hỗ trợ SRV, URI `mongodb+srv://...` có thể giúp khám phá endpoint theo DNS SRV/TXT và cơ chế driver tương ứng.

Điều quan trọng vẫn là dùng URI đúng deployment, đúng tên replica set/cluster, bảo mật TLS và không pin ghi vào primary cũ. Không tự chuyển URI thường sang SRV khi hạ tầng DNS chưa cung cấp record cần thiết.

## 13. Driver phát hiện thay primary như thế nào? (SDAM)

**SDAM** viết tắt của **Server Discovery and Monitoring**. Driver MongoDB theo dõi topology để biết:

- Những node nào đang có thể truy cập.
- Node nào là primary.
- Những node nào là secondary.
- Topology hoặc term đã thay đổi hay chưa.
- Địa chỉ nào hợp lệ để gửi lệnh với read preference và khả năng ghi đã chọn.

~~~text
                   MongoDB Driver
                +-------------------+
App operation ->| Server selection  |
                | + monitoring      |
                +---------+---------+
                          |
          +---------------+---------------+
          |               |               |
        node-a          node-b          node-c
        SECONDARY       PRIMARY         SECONDARY
                          |
                          v
                        Write
~~~

Khi primary cũ rời vai trò, driver cập nhật thông tin và tìm primary mới. Quá trình này có thể mất thời gian; request trong giai đoạn không có primary sẽ chờ hoặc thất bại tùy server-selection deadline và trạng thái kết nối.

### 13.1. Không cache biến primaryHost trong ứng dụng

Sai về ý tưởng:

~~~javascript
// Pseudocode ứng dụng: không nên giả định cố định.
const primaryHost = "node-a.example.test";
sendEveryWriteTo(primaryHost);
~~~

Đúng hơn: tạo `MongoClient` bằng URI replica set và tái sử dụng client/connection pool, để driver quản lý discovery và chọn server.

### 13.2. Một MongoClient dài hạn tốt hơn tạo mới cho từng request

MongoDB driver thường quản lý connection pools và background topology monitoring. Tạo một MongoClient mới cho mỗi HTTP request:

- Tăng chi phí kết nối và xác thực.
- Phân tán khả năng theo dõi topology.
- Tăng CPU/socket.
- Khi failover, có thể làm tình trạng quá tải tồi hơn.

Trong ứng dụng server, nên quản lý vòng đời client theo lifetime của ứng dụng, hoặc theo framework dependency injection.

### 13.3. Một socket mở vẫn có thể nối tới secondary

Ngay sau election, node-a cũ có thể vẫn lắng nghe mạng và phản hồi các lệnh phù hợp, nhưng không còn là primary. Kết nối TCP thành công không đồng nghĩa một write được chấp nhận.

Điều này lý giải vì sao ứng dụng cần xử lý cả lỗi **not writable primary** lẫn lỗi network thông thường.

## 14. Timeout khác retry

Một số timeout hay gặp:

| Tham số/khái niệm | Ý nghĩa khái quát |
|---|---|
| `serverSelectionTimeoutMS` | Driver chờ tối đa bao lâu để tìm server phù hợp cho thao tác |
| `connectTimeoutMS` | Thời gian kết nối mạng tới một host |
| `socketTimeoutMS` hoặc read timeout phù hợp driver | Thời gian chờ I/O cho một socket/operation |
| `maxTimeMS` | Thời gian thực thi server áp dụng cho command hỗ trợ |
| Deadline HTTP/gRPC | Hạn phục vụ request của ứng dụng, độc lập với MongoDB |

Ví dụ URI:

~~~text
mongodb://node-a.example.test:27017,node-b.example.test:27017,node-c.example.test:27017/app?replicaSet=rsDemo&serverSelectionTimeoutMS=20000&retryWrites=true
~~~

Nếu chưa có primary mới, driver có thể tiếp tục chờ trong giới hạn server selection. Khi timeout hết, một exception không đồng nghĩa cluster sẽ không bao giờ phục hồi; nó cho biết request đó không tìm được server phù hợp trong deadline.

### 14.1. Timeout ngắn không làm election nhanh hơn

Giảm `serverSelectionTimeoutMS` từ 30 giây xuống 500 ms không làm MongoDB bầu primary nhanh hơn. Nó khiến nhiều request **trả lỗi sớm hơn** trong giai đoạn failover.

Ngược lại, deadline quá dài có thể làm HTTP request treo lâu và gây đầy worker threads hoặc hàng đợi. Nên cân bằng theo SLA, concurrency, retry budget và trải nghiệm người dùng.

### 14.2. Retry phải có ngân sách

Một chính sách retry ở tầng ứng dụng nên quy định:

- Những operation/error nào được retry.
- Số lần và thời gian tối đa.
- Backoff và jitter để tránh mọi client đồng loạt retry.
- Request deadline tổng.
- Trạng thái nào được đối soát thay vì retry mù.
- Cách log request ID/idempotency key.

Không tạo vòng lặp retry vô hạn khi replica set không có majority, vì nó có thể khiến cluster mới hồi phục lại bị quá tải ngay lập tức.

## 15. Retryable reads

Driver hỗ trợ **retryable reads** cho những read operation được thiết kế tương ứng, khi được bật và server/driver hỗ trợ.

Ví dụ URI:

~~~text
...?retryReads=true
~~~

Nếu read bị lỗi tạm thời do network hoặc primary change, driver có thể retry theo quy tắc hỗ trợ.

Điểm cần hiểu:

1. Không phải mọi lệnh/cấu hình đều có cùng retry semantics.
2. Retry một read có thể nhìn dữ liệu ở thời điểm mới hơn.
3. Đối với phân trang, filter/sort và consistency vẫn cần thiết kế riêng.
4. Một aggregation có stage ghi `$out`/`$merge` không nên được coi là read-only thuần túy chỉ vì gọi `aggregate()`.
5. Read preference secondary không làm secondary nhận ghi.

### 15.1. Read preference primary

~~~text
readPreference=primary
~~~

Driver chọn primary cho read. Trong election gap, read theo primary có thể phải chờ hoặc thất bại nếu không có primary.

### 15.2. Read preference secondary hoặc secondaryPreferred

Các chính sách đọc secondary có thể cho phép một số read tiếp tục trong thời gian không có primary, tùy topology và khả năng chọn server. Tuy nhiên:

- Secondary có thể trễ replication.
- Không phải mọi loại read/operation đều phù hợp.
- Đọc từ secondary không giúp ghi được khi không có primary.
- Nghiệp vụ yêu cầu “vừa ghi rồi đọc thấy ngay” cần đánh giá read concern, causal consistency/session và lựa chọn node.

Đừng tự chuyển tất cả read sang secondary trong lúc failover nếu ứng dụng có yêu cầu mạnh về độ mới dữ liệu.

## 16. Retryable writes: driver xử lý được đến đâu?

**Retryable writes** cho phép driver retry **một số write operation** khi gặp lỗi tạm thời như mất kết nối hoặc chuyển primary, theo ngữ nghĩa của server/driver.

Ví dụ:

~~~text
...?retryWrites=true
~~~

Các thao tác thường thuộc phạm vi hỗ trợ gồm single-document operations như `insertOne`, `updateOne`, `replaceOne`, `deleteOne` và một số biến thể `findOneAnd...`, khi thỏa các điều kiện cần thiết. Bulk writes chỉ có thể retry khi mọi operation trong batch thuộc loại retryable tương ứng; các thao tác multi-document như `updateMany`/`deleteMany` không tự có cùng bảo đảm.

Không dùng quy tắc đơn giản “mọi write tự được driver làm lại đúng một lần bất kể lỗi gì”.

### 16.1. Vì sao retryable write cần session/transaction metadata?

Trong retryable write protocol, driver và server sử dụng các định danh logic của operation, session và transaction number để nhận diện việc retry cùng một thao tác trong điều kiện hỗ trợ.

Mục tiêu là tránh server thực hiện lại **cùng một retryable write** hai lần chỉ vì phản hồi đầu tiên bị mất. Nhưng tính năng này không thay thế idempotency của toàn bộ workflow nghiệp vụ và không bảo đảm xử lý mọi tổ hợp lỗi, timeout hoặc thao tác không retryable.

### 16.2. Ví dụ một write và ACK bị mất

~~~text
Client                            Primary cũ
   |                                   |
   | INSERT order-101 ---------------->|
   |                                   | Ghi có thể đã thực hiện
   |             X connection lost     |
   |                                   |
   |      Election diễn ra             |
   |                                   |
   | Driver chọn primary mới           |
   | Retryable write nếu hỗ trợ        |
   |---------------------------------->|
   |                                   |
   | Được xác nhận hoặc trả lỗi         |
~~~

Nếu client không nhận ACK, ứng dụng **không thể chỉ nhìn timeout để biết chắc write chưa được thực hiện**. Driver retryable writes giúp xử lý nhiều trường hợp, nhưng nếu ứng dụng vẫn nhận lỗi cuối cùng, kết quả có thể cần đối soát.

### 16.3. Không tự retry mãi thao tác $inc

Ví dụ nghiệp vụ:

~~~javascript
db.accounts.updateOne(
  { _id: "account-101" },
  { $inc: { balance: 100 } }
);
~~~

Nếu ứng dụng nhận timeout không rõ write đã được áp dụng hay chưa, tự thực hiện lại cùng `$inc` như một **request nghiệp vụ mới** có thể tăng balance hai lần. Đây là rủi ro khác với driver retry đúng protocol của **cùng một retryable write**.

Một thiết kế an toàn hơn cần định danh giao dịch, bản ghi ledger hoặc điều kiện cập nhật nguyên tử để bảo đảm mỗi nghiệp vụ chỉ được xử lý đúng số lần cho phép.

## 17. Idempotency: lớp bảo vệ ở tầng nghiệp vụ

Một operation **idempotent** có thể được thực hiện lại mà không gây tác dụng phụ ngoài ý định so với thực hiện một lần, trong bối cảnh được định nghĩa.

### 17.1. Tạo đơn với _id do ứng dụng quyết định

Một ví dụ:

~~~javascript
db.getSiblingDB("replica_failover_lab").orders.insertOne({
  _id: "order-request-2026-001",
  customerId: "C01",
  status: "NEW",
  amount: NumberDecimal("42.00"),
  createdAt: new Date()
});
~~~

Nếu kết quả ACK bị mất, việc client tự gửi lại một lệnh `insertOne` mới với cùng `_id` có thể gặp duplicate key. Lỗi đó có thể gợi ý document đã tồn tại, nhưng **không nên coi mọi duplicate key là thành công tuyệt đối**. Cần đọc lại record, so request ID/payload và quyền sở hữu để xác định nó có đúng là kết quả của request cũ hay không.

### 17.2. Upsert theo khóa nghiệp vụ duy nhất

Ví dụ khái niệm:

~~~javascript
db.getSiblingDB("replica_failover_lab").requestLog.updateOne(
  { _id: "req-001" },
  {
    $setOnInsert: {
      type: "CREATE_ORDER",
      payloadHash: "expected-hash",
      status: "RECEIVED"
    }
  },
  { upsert: true }
);
~~~

Dùng một key duy nhất cho request giúp ứng dụng nhận biết đã từng xử lý yêu cầu. Nhưng chỉ tạo log chưa đủ để bảo đảm toàn bộ nghiệp vụ exactly-once nếu còn nhiều tác động bên ngoài, ví dụ gửi email, thanh toán hoặc publish message.

Khi có nhiều collection hoặc side effects, cần transaction, outbox/inbox, reconciliation hoặc cơ chế nhất quán nghiệp vụ thích hợp.

### 17.3. Phân biệt 3 lớp retry

| Lớp | Trách nhiệm |
|---|---|
| **Driver retry** | Retry một command theo protocol hỗ trợ và session metadata |
| **Application retry** | Quyết định gọi lại logic sau lỗi, có timeout/backoff và điều kiện |
| **Business idempotency** | Chống nhân đôi tác động nghiệp vụ khi request được gửi lại |

Nếu client HTTP gửi lại request sau timeout, đó thường là một **request ứng dụng mới**, không mặc nhiên là retryable write protocol của command trước. Vì vậy lớp idempotency nghiệp vụ vẫn cần thiết.

## 18. Write concern và dữ liệu sau failover

### 18.1. w:1 và w:majority

Với `w:1`, primary xác nhận sau khi đáp ứng write concern một node theo cấu hình. Nếu primary bị cô lập/sự cố trước khi các thay đổi được nhân bản và commit phù hợp, có thể xảy ra rollback của những write chưa được majority-committed.

Với `w:"majority"`, việc xác nhận đòi hỏi số data-bearing voting members cần thiết theo tính toán của replica set đã đáp ứng majority write concern.

~~~javascript
db.getSiblingDB("replica_failover_lab")
  .orders
  .insertOne(
    {
      _id: "majority-test-001",
      createdAt: new Date(),
      status: "NEW"
    },
    { writeConcern: { w: "majority", wtimeout: 5000 } }
  );
~~~

Ý nghĩa:

- `w:"majority"` tăng bảo đảm độ bền với election/rollback theo semantics của server.
- `wtimeout` giới hạn thời gian chờ đạt write concern.
- Nếu write concern timeout, write **có thể đã được áp dụng** nhưng chưa được xác nhận với write concern yêu cầu. Không coi timeout là bằng chứng “chắc chắn chưa ghi”.

### 18.2. Arbiter không lưu dữ liệu

Trong topology có arbiter, nó có thể bỏ phiếu bầu primary nhưng không thể ghi nhận dữ liệu như một secondary. Bầu chọn majority và majority write concern không nên được giản lược thành “cứ có hai phiếu thì đã lưu đủ hai bản sao”.

Đánh giá `writeMajorityCount`, các data-bearing members và cấu hình write concern của topology thực tế, nhất là PSA.

### 18.3. Read concern majority

Khi nghiệp vụ yêu cầu đọc những dữ liệu đã được majority-committed, có thể xem xét `readConcern: "majority"` cùng read preference và session semantics thích hợp.

Write concern và read concern giải quyết những vấn đề khác nhau:

- **Write concern:** mức xác nhận của thao tác ghi.
- **Read concern:** mức nhất quán/độ cam kết của dữ liệu mà một read được phép quan sát.
- **Read preference:** node nào có thể được chọn để chạy read.

Không nên cho rằng chỉ đặt `readPreference=secondaryPreferred` đã bảo đảm đọc được phiên bản mới nhất hoặc loại bỏ mọi vấn đề sau failover.

## 19. Rollback: chuyện gì xảy ra với write chưa được bảo vệ đủ?

Giả sử ba member A, B, C:

~~~text
T0: A PRIMARY, B/C SECONDARY

T1: Client ghi X vào A, nhận ACK với w:1
T2: X chưa đến đủ node để majority-commit
T3: A bị cô lập

T4: B và C bầu B làm PRIMARY
T5: A trở lại, theo lịch sử của B
    X có thể bị rollback nếu không thuộc lịch sử được chọn
~~~

Ví dụ này minh họa rủi ro khi chỉ xác nhận từ primary cũ. Không đồng nghĩa **mọi write w:1 đều bị rollback**; nó chỉ có thể xảy ra trong tình huống thất bại phù hợp.

### 19.1. Không dùng ACK w:1 như bảo đảm “không bao giờ mất”

Nếu yêu cầu nghiệp vụ là giao dịch tài chính, tạo đơn hoặc lưu sự kiện quan trọng, phải chọn write concern và kiến trúc replication phù hợp với mức độ bền dữ liệu cần thiết.

### 19.2. Majority không giải quyết mọi vấn đề ứng dụng

Ngay cả khi write đã majority-committed, client vẫn có thể không nhận được ACK do lỗi mạng. Khi đó cần nhận diện và đối soát request, không tự thực hiện lại tác động nghiệp vụ như một giao dịch mới.

### 19.3. Thao tác bị rollback và side effects ngoài MongoDB

Nếu ứng dụng gửi email hoặc gọi một dịch vụ thanh toán ngay sau một ghi chưa được bảo đảm đủ, có thể xảy ra trạng thái bên ngoài đã thay đổi nhưng record MongoDB bị rollback.

Khi side effects quan trọng, cần transaction, outbox, event delivery idempotency và cơ chế reconcile phù hợp. Failover không tự thực hiện rollback cho email, HTTP request hoặc các hệ thống khác.

## 20. Transaction khi primary thay đổi

MongoDB hỗ trợ multi-document transactions trong các topology và phiên bản phù hợp. Một transaction đang chạy có thể gặp lỗi khi primary stepdown hoặc election diễn ra.

Những error label thường quan trọng:

| Label | Ý nghĩa xử lý khái quát |
|---|---|
| `TransientTransactionError` | Lỗi tạm thời trong transaction có thể cần chạy lại toàn bộ transaction theo pattern của driver |
| `UnknownTransactionCommitResult` | Không biết chắc commit đã thành công hay chưa; cần retry commit theo cơ chế phù hợp |
| `RetryableWriteError` | Thông tin hỗ trợ xử lý lỗi retryable write theo protocol/driver |
| `NoWritesPerformed` | Label trong những phiên bản hỗ trợ khi không có write nào được thực hiện sau các lần retry write được mô tả |

Không coi các label này là chuỗi thông báo có thể đoán bằng cách match text exception. Driver cung cấp API/thuộc tính để kiểm tra error label.

### 20.1. Lỗi trước commit khác lỗi commit chưa rõ

Trường hợp A: Transaction gặp lỗi tạm thời trước khi commit thành công; driver/hàm tiện ích có thể cần chạy lại toàn bộ transaction.

Trường hợp B: Client gửi commit nhưng kết nối mất trước khi nhận phản hồi. Transaction **có thể đã commit**. Cần retry commit theo protocol hoặc đối soát, không gửi một transaction nghiệp vụ mới ngay.

### 20.2. withTransaction và callback có side effects

Nhiều driver cung cấp helper kiểu `withTransaction` hoặc callback API, có thể tự retry transaction/commit theo semantics hỗ trợ.

Vì callback **có thể được thực thi lại**, không nên đặt side effects ngoài MongoDB như gửi email, charge thẻ hoặc publish message không idempotent trực tiếp trong callback mà không có cơ chế bảo vệ.

Thay vào đó, xem xét ghi outbox record cùng transaction rồi có worker gửi ra ngoài với khả năng xử lý trùng. Đó là thiết kế nghiệp vụ, không phải chức năng tự động của replica set election.

### 20.3. readConcern/writeConcern trong transaction

Thiết kế transaction cần dùng read concern, write concern và read preference phù hợp với driver/server. Một số yêu cầu nhất quán cao, đặc biệt khi đọc snapshot, có ràng buộc và chi phí riêng.

Không tự thay mọi transaction sang secondary read trong khi xử lý primary failover.

## 21. Ví dụ Java Driver: kết nối tự khám phá primary

Giả sử hệ thống dùng MongoDB Java Sync Driver tương thích với server. Java Driver cung cấp `MongoClient`, connection pool và cơ chế SDAM.

Ví dụ sau có các hostname minh họa; thay chúng bằng tên trong deployment của bạn.

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

String uri =
    "mongodb://node-a.example.test:27017," +
    "node-b.example.test:27017," +
    "node-c.example.test:27017/app" +
    "?replicaSet=rsDemo" +
    "&retryWrites=true" +
    "&retryReads=true";

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .readPreference(ReadPreference.primary())
    .readConcern(ReadConcern.MAJORITY)
    .writeConcern(WriteConcern.MAJORITY)
    .retryWrites(true)
    .retryReads(true)
    .applyToClusterSettings(builder ->
        builder.serverSelectionTimeout(
            20, TimeUnit.SECONDS
        )
    )
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    MongoDatabase db = client.getDatabase("app");
    MongoCollection<Document> orders =
        db.getCollection("orders");

    Document order = new Document("_id", "req-001")
        .append("status", "NEW")
        .append("amount", 42);

    orders.insertOne(order);

    Document saved = orders.find(
        new Document("_id", "req-001")
    ).first();

    System.out.println(saved);
}
~~~

**Lưu ý:** Đây là chương trình minh họa logic kết nối và write/read, không có credentials, TLS hoặc môi trường server thật. Trong production cần cấu hình xác thực và secret management theo quy định.

### 21.1. Điều gì xảy ra khi stepdown trong Java?

Nếu node-a từng là primary rồi chuyển thành secondary:

- Driver nhận biết node-a không còn writable primary.
- Driver tiếp tục discovery qua những node replica set khác.
- Với write operation mới, driver tìm node đáp ứng yêu cầu primary.
- Với những lỗi tạm thời được hỗ trợ, retryable write/read có thể giúp hoàn tất thao tác.
- Nếu server selection deadline hết hoặc lỗi không retryable, API Java vẫn có thể ném exception.

Điều này không yêu cầu ứng dụng đóng MongoClient rồi khởi tạo MongoClient mới sau mọi election. Tái sử dụng client lâu dài thường là thiết kế đúng.

### 21.2. Đừng tự mở client tới host đọc từ một lần hello

Sai về ý tưởng:

~~~java
// Không nên cache "primary = node-a" rồi tạo
// một MongoClient pinned host cho mọi write tương lai.
~~~

Đúng: URI mô tả topology replica set, còn driver quản lý member discovery và connection pool.

### 21.3. Tạo một client cho vòng đời ứng dụng

Với Spring Boot hoặc server Java, tạo MongoClient thông qua cấu hình/DI; tránh khởi tạo và đóng nó sau mỗi request.

Lợi ích:

- SDAM duy trì được thông tin topology.
- Pool connection được tái sử dụng.
- Giảm overhead kết nối và xác thực.
- Quản lý timeout/retry tập trung.

## 22. Java Driver: xử lý kết quả ghi không rõ

Dưới đây là một mẫu **khái niệm** cho việc tạo đơn với `_id` do ứng dụng xác định:

~~~java
import com.mongodb.MongoException;
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

String requestId = "order-request-001";

Document desired = new Document("_id", requestId)
    .append("status", "NEW")
    .append("amount", 42);

try {
    orders.insertOne(desired);
    System.out.println("Write acknowledged");
} catch (MongoException ex) {
    // Khi ACK không rõ, không kết luận write chưa xảy ra.
    // Cần phân loại lỗi, request deadline và khả năng đối soát.
    Document existing = orders.find(
        new Document("_id", requestId)
    ).first();

    if (existing != null) {
        // So nội dung/owner/payloadHash thật trước khi
        // coi đây là cùng một request nghiệp vụ.
        System.out.println("Need to verify existing order");
    } else {
        // Không có record quan sát được cũng chưa giải quyết
        // được mọi trường hợp eventual failover/timeout.
        System.out.println("Needs controlled recovery");
    }
}
~~~

Ví dụ này không phải một retry engine hoàn chỉnh: phép read để đối soát cũng có thể lỗi khi failover chưa kết thúc. Ứng dụng thật cần bảo vệ cả nhánh kiểm tra bằng timeout và trạng thái có thể tiếp tục xử lý sau.

### 22.1. Vì sao không tự loop insertOne vô hạn?

Một client có thể gửi request mới sau timeout, và không phải mọi timeout đều nói gì về kết quả trên server. Retry không có deadline sẽ:

- Làm tăng số request khi hệ thống đang lỗi.
- Có thể tạo trùng nghiệp vụ nếu không có khóa duy nhất.
- Khiến người dùng phải chờ vô hạn.
- Cạnh tranh tài nguyên với quá trình khôi phục.

Nên kết hợp retry có giới hạn, backoff/jitter, idempotency key và đối soát.

### 22.2. Không phân loại lỗi chỉ theo thông điệp văn bản

Những thông báo như `not primary`, `connection reset` hoặc `timed out` không có nghĩa hoàn toàn giống nhau.

Trong Java Driver, xem loại exception, error code/labels khi có, và kết quả write acknowledgement. Đối với transaction, error labels như `TransientTransactionError`/`UnknownTransactionCommitResult` có vai trò rõ hơn chuỗi message.

## 23. Read-after-write khi primary thay đổi

Một yêu cầu thường gặp:

~~~text
POST /orders
  -> tạo đơn
GET /orders/{id}
  -> kỳ vọng thấy đơn vừa tạo
~~~

Nếu sau khi ghi ở primary, ứng dụng đọc từ một secondary có replication lag, có thể tạm **không thấy** đơn mới.

Ngay cả khi URI có retryReads và driver chọn một secondary healthy, điều đó **không** bảo đảm secondary đã áp dụng write mới nhất.

### 23.1. Chọn cơ chế theo nhu cầu

| Nhu cầu | Điều cần xem |
|---|---|
| Đọc ngay sau ghi trong luồng nghiệp vụ | Đọc primary, cùng session/causal consistency khi thích hợp |
| Chỉ cần báo cáo không yêu cầu mới nhất | Secondary read có thể phù hợp |
| Chỉ đọc dữ liệu đã majority-committed | Read concern majority, kết hợp thiết kế đọc phù hợp |
| Cần snapshot nhất quán nhiều thao tác | Session/transaction/read concern phù hợp, chú ý chi phí |
| Giao diện infinite scroll | Sort ổn định, cursor token, data changes, không chỉ election |

### 23.2. Read preference không thay write routing

`readPreference=secondaryPreferred` cho phép driver chọn secondary cho đọc khi phù hợp, **không cho phép ứng dụng ghi vào secondary** khi primary không có.

Khi mất majority không có primary, các thao tác ghi phải chờ hoặc lỗi; không có tùy chọn read preference nào bỏ qua yêu cầu này.

## 24. Quan sát failover từ mongosh mà không sửa dữ liệu production

Giả sử bạn đã có một replica set thực hành được cấp quyền.

### 24.1. Theo dõi primary hiện tại

~~~javascript
const hello = db.hello();

printjson({
  setName: hello.setName,
  isWritablePrimary: hello.isWritablePrimary,
  primary: hello.primary,
  hosts: hello.hosts
});
~~~

Nếu bạn thực hiện lệnh này từ một mongosh kết nối bằng URI replica set, driver/shell có thể chọn server phù hợp theo cơ chế của nó. Khi muốn kiểm tra **một member cụ thể**, cần dùng công cụ/kết nối đúng mục tiêu vận hành với quyền được phép, không suy luận rằng một `hello()` bất kỳ đại diện cho mọi member tại cùng thời điểm.

### 24.2. Theo dõi trạng thái member

~~~javascript
const s = rs.status();

printjson(
  s.members.map(m => ({
    host: m.name,
    state: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate
  }))
);
~~~

Không cần chạy vòng lặp polling liên tục với tần suất quá cao trong bài học; dùng monitoring hoặc các lần đọc có chủ đích.

### 24.3. Mẫu thao tác ghi có thể kiểm tra

Trong database thực hành riêng:

~~~javascript
use replica_failover_lab

db.orders.updateOne(
  { _id: "health-check-order" },
  {
    $set: {
      status: "READY",
      checkedAt: new Date()
    }
  },
  {
    upsert: true,
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

Nếu primary chuyển vai trò ngay lúc ghi:

- Có thể thành công.
- Có thể nhận lỗi retryable được driver xử lý.
- Có thể hết deadline.
- Có thể không rõ ACK đã nhận đủ write concern hay chưa.

Đừng coi `matchedCount:0` khi upsert là lỗi failover tự thân; với upsert tạo mới, `matchedCount` có thể bằng 0 nhưng vẫn có `upsertedId`.

## 25. Bài thực hành failover trong staging

**Chỉ làm phần này nếu có quyền quản trị một replica set thử nghiệm**. Không thực hiện stepdown trên production trong một bài học thông thường.

### Bài 1 — Kiểm tra điều kiện trước stepdown

Ghi nhận:

~~~javascript
rs.status();
rs.conf();
db.hello();
~~~

Trả lời:

1. Có bao nhiêu voter?
2. Majority cần mấy phiếu?
3. Những member nào là secondary?
4. Secondary nào có `priority:0`?
5. Có secondary eligible và đủ cập nhật không?
6. Host ứng dụng dùng URI replica set hay một host đơn?

### Bài 2 — Bắt đầu thao tác ghi thử

Trong một session client:

~~~javascript
use replica_failover_lab

db.orders.updateOne(
  { _id: "failover-demo" },
  {
    $set: {
      status: "BEFORE_STEPDOWN",
      updatedAt: new Date()
    }
  },
  {
    upsert: true,
    writeConcern: { w: "majority" }
  }
);
~~~

Đọc lại document và ghi nhận đã thành công trước khi thao tác quản trị.

### Bài 3 — Planned stepdown

Từ mongosh có quyền thực thi trên primary và sau khi xác nhận điều kiện an toàn:

~~~javascript
rs.stepDown(60, 15);
~~~

Nếu shell hiện lỗi mạng hoặc not-primary, kết nối lại qua replica set URI và xác minh topology. Không cố gọi `rs.stepDown()` liên tiếp trên primary mới chỉ để thấy command “thành công”.

### Bài 4 — Kiểm tra primary mới

~~~javascript
db.hello();
rs.status();
~~~

Ghi lại:

- Host giữ vai trò primary mới.
- Trạng thái các secondary.
- Term nếu có.
- Thời điểm ứng dụng ghi lại được.
- Những exception client quan sát được.

### Bài 5 — Ghi thử sau election

~~~javascript
db.getSiblingDB("replica_failover_lab")
  .orders
  .updateOne(
    { _id: "failover-demo" },
    {
      $set: {
        status: "AFTER_STEPDOWN",
        updatedAt: new Date()
      }
    },
    {
      writeConcern: {
        w: "majority",
        wtimeout: 5000
      }
    }
  );
~~~

Kiểm tra document sau khi cluster ổn định. Chú ý thao tác chỉ nhằm phục vụ bài thực hành; không dùng record của ứng dụng thật.

### Bài 6 — Thử driver reconnect

Tạo một ứng dụng Java với MongoClient dùng nhiều seed hosts và `replicaSet` name. Giữ MongoClient chạy xuyên suốt cuộc stepdown, rồi quan sát:

- Driver có tự chọn primary mới không?
- Ghi trong election gap có lỗi/đợi bao lâu?
- Retryable write có được bật không?
- Có request nào bị timeout cần đối soát không?
- Sau election, client có phải khởi tạo lại MongoClient không?

**Mục tiêu:** Hiểu behavior, không cố làm hệ thống lỗi quá tải.

### Bài 7 — So sánh w:1 và majority

Không cần cố làm dữ liệu bị rollback. Hãy giải thích trên giấy:

- Với `w:1`, ACK đầu tiên xác nhận điều gì?
- Với `w:"majority"`, ACK chờ điều gì?
- Nếu không có ACK do mạng lỗi, có chắc write chưa thực hiện không?
- Vì sao unique request ID/idempotency vẫn cần?

### Bài 8 — Đối soát thao tác chưa rõ kết quả

Giả sử POST tạo đơn mang `requestId:"req-123"` trả timeout ngay sau primary change.

Thiết kế các bước:

1. Giữ requestId cố định, không tạo một ID mới cho retry.
2. Kết nối lại qua driver replica set.
3. Kiểm tra record theo requestId/unique key.
4. So payloadHash và tenant/owner.
5. Nếu đã có đúng record, phản hồi theo hợp đồng API.
6. Nếu chưa có, quyết định retry có giới hạn hoặc trả trạng thái chờ đối soát.
7. Nếu có record khác cùng key, phân loại conflict, không coi duplicate key luôn là success.

## 26. Kịch bản lỗi thường gặp và cách diễn giải

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Driver báo không tìm thấy primary | Election đang diễn ra, thiếu majority, DNS/network hoặc URI sai | Kiểm tra topology, voter, server selection, connectivity |
| Ghi vào host cũ báo not-primary | Node vừa step down | Dùng replica set URI/driver discovery, xử lý retry hợp lệ |
| Ping node cũ thành công nhưng insert thất bại | Node cũ vẫn online, hiện là secondary | Không nhầm TCP reachable với writable primary |
| rs.stepDown báo mất kết nối | Command có thể đã kích hoạt chuyển role | Kết nối lại và kiểm tra trạng thái, không kết luận chỉ từ exception |
| Stepdown bị từ chối | Không có secondary eligible/caught-up hoặc điều kiện khác | Kiểm tra lag, priority, quorum; không ép force |
| Node có priority 0 không được bầu | Cấu hình không eligible | Đây có thể là hành vi đúng, xem rs.conf |
| Có arbiter nhưng ít bản sao dữ liệu | Arbiter chỉ bỏ phiếu | Đánh giá topology, replication và write concern riêng |
| Secondary read không thấy write mới | Replication lag/consistency | Xem read preference, read concern/session |
| Write báo timeout nhưng document tồn tại | ACK bị mất hoặc write concern timeout | Đối soát bằng request ID, không retry mù |
| $inc bị áp dụng hai lần | Application gửi lại một nghiệp vụ mới sau outcome mơ hồ | Ledger/idempotency/transaction phù hợp |
| Ghi w:1 sau failover bị mất | Write chưa majority-commit có thể rollback | Chọn write concern theo độ bền cần thiết |
| Một giao dịch bị lỗi giữa chừng | Primary change, transient transaction error | Driver transaction retry pattern, kiểm tra side effects |
| Commit result không rõ | Mất kết nối ở bước commit | Retry commit đúng semantics, không tạo nghiệp vụ mới |
| URI chỉ có host cũ đã chết | Discovery chưa thành công/không có seed khác | Cung cấp nhiều seed reachable, replicaSet name |
| URI directConnection=true | Driver pin tới một host | Dùng topology-aware replica set connection |
| Retry quá dồn dập sau failover | Nhiều client retry đồng thời | Backoff+jitter, retry budget, rate limiting |
| Election diễn ra liên tục | Mạng không ổn định, timeout/priority/config hoặc tài nguyên | Kiểm tra log, heartbeats, lag, election term |
| Không có primary dù còn một node sống | Không đủ majority votes | Khôi phục quorum, không cưỡng ép ghi |
| Primary mới ổn nhưng API vẫn lỗi | Connection pool/hostname quảng bá/TLS/timeout | Kiểm tra advertised hosts và driver SDAM |
| Thay primary nhưng app phải restart | Ứng dụng pin host hoặc quản lý MongoClient sai | Dùng MongoClient lâu dài + URI đúng topology |

## 27. Phân biệt election, retry, rollback và consistency

Bốn khái niệm thường được đặt cạnh nhau nhưng giải quyết những vấn đề khác nhau:

| Cơ chế | Câu hỏi được giải quyết |
|---|---|
| **Election/quorum** | Node nào được phép làm primary? |
| **Driver SDAM + retry** | Client tìm primary mới và có thể lặp lại command phù hợp không? |
| **Write concern/rollback** | Ghi đã được xác nhận ở mức độ bền nào, liệu lịch sử chưa commit có bị đảo ngược không? |
| **Read concern/session/transaction** | Một read hoặc một nhóm thao tác được phép nhìn dữ liệu nhất quán ở mức nào? |

Ví dụ:

- Election thành công **không** tự bảo đảm một API thanh toán đã được thực thi đúng một lần.
- Retryable write thành công **không** có nghĩa mọi HTTP retry mới của cùng nghiệp vụ là an toàn.
- `w:"majority"` giúp bảo vệ write được xác nhận, nhưng client vẫn có thể mất ACK.
- Secondary read có thể tồn tại trong một giai đoạn không có primary nhưng chưa chắc có dữ liệu mới nhất.
- Một transaction commit có kết quả mơ hồ cần xử lý khác với transaction bị abort trước commit.

Thiết kế hệ thống ổn định đòi hỏi kết hợp các cơ chế, thay vì kỳ vọng election tự giải quyết mọi tầng nghiệp vụ.

## 28. Theo dõi election và failover trong môi trường thực tế

Những metric/sự kiện hữu ích:

### 28.1. Replica set state

- Primary identity thay đổi.
- Election term thay đổi.
- Member health và state.
- LastHeartbeatMessage.
- Replication lag và optime.
- Số member reachable và khả năng đạt majority.

### 28.2. Driver và ứng dụng

- Số server selection timeouts.
- Thời gian chọn server trước và sau failover.
- Tỷ lệ lỗi insert/update/transaction.
- Số retryable errors và số retry thành công nếu hệ thống ghi nhận.
- p50/p95/p99 latency của API.
- Connection pool checkout time và kết nối mới.
- Số request có outcome chưa rõ cần reconciliation.
- Queue depth và mức retry đồng thời.

### 28.3. Quy trình cảnh báo

Một cảnh báo “primary thay đổi” không đủ để hiểu tác động. Nên liên kết:

~~~text
Election event
     |
     +--> Primary mới là ai?
     |
     +--> Trong bao lâu không có primary?
     |
     +--> Lỗi/latency ứng dụng tăng bao nhiêu?
     |
     +--> Có giao dịch outcome unknown không?
     |
     +--> Mức replication lag sau failover?
     |
     +--> Retry và idempotency hoạt động đúng không?
~~~

Nếu số lần election trong thời gian ngắn tăng bất thường, cần điều tra hạ tầng/mạng, disk stall, CPU và cấu hình, thay vì chỉ tăng vô hạn timeout ở ứng dụng.

## 29. MongoDB Compass và tình huống chuyển primary

MongoDB Compass là công cụ giao diện giúp kiểm tra collection và một số trạng thái kết nối. Giao diện có thể khác nhau theo phiên bản.

Thực hành hợp lý:

1. Kết nối tới một replica set test bằng connection string có seed list/cluster endpoint đúng.
2. Xem danh sách database và collection khi topology đang ổn định.
3. Trong một cửa sổ mongosh được phép, đọc `rs.status()` và `db.hello()`.
4. Nếu có quyền và đang ở test/staging, thực hiện stepdown có kiểm soát.
5. Quan sát Compass có tự tiếp tục query được sau election không.
6. Nếu Compass hiển thị lỗi tạm thời, đợi topology ổn định rồi kiểm tra lại.
7. Đối chiếu với mongosh và driver logs, không dùng việc UI đang hiện document như bằng chứng node hiện là primary.

Không cố tình stepdown cluster production chỉ để trình diễn Compass; UI phục vụ quan sát, không thay thế quyền và runbook vận hành.

## 30. Những ngộ nhận cần tránh

**Ngộ nhận 1: “Replica set ba node nghĩa là luôn có primary.”**

Không đúng. Khi không còn majority hoặc không có secondary đủ điều kiện, có thể không có primary.

**Ngộ nhận 2: “Stepdown dừng mongod.”**

Không đúng. Stepdown thay vai trò; tiến trình thường có thể tiếp tục chạy như secondary.

**Ngộ nhận 3: “Stepdown 60 giây nghĩa là downtime 60 giây.”**

Không đúng. Tham số đó liên quan thời gian primary cũ không ứng cử lại; primary mới có thể xuất hiện trước khi hết 60 giây.

**Ngộ nhận 4: “Bật retryWrites thì mọi HTTP request chạy đúng một lần.”**

Không đúng. Retryable write protocol chỉ áp dụng với những write đủ điều kiện; HTTP retry là tầng khác và cần idempotency nghiệp vụ.

**Ngộ nhận 5: “Mất ACK nghĩa là write chắc chắn chưa chạy.”**

Không đúng. Write có thể đã được thực hiện hoặc đã majority-committed trước khi phản hồi bị mất.

**Ngộ nhận 6: “Đọc từ secondary sẽ giải quyết mọi lỗi failover.”**

Không đúng. Nó không giúp ghi khi không có primary và có thể đọc dữ liệu trễ.

**Ngộ nhận 7: “Có một arbiter là có thêm bản sao dữ liệu.”**

Không đúng. Arbiter bỏ phiếu nhưng không lưu dữ liệu.

**Ngộ nhận 8: “Cứ giảm electionTimeout là HA tốt hơn.”**

Không nhất thiết. Timeout quá thấp có thể làm election không cần thiết trong mạng chập chờn.

**Ngộ nhận 9: “Sau election, primary cũ sẽ tự trở lại primary.”**

Không bảo đảm. Node cũ có thể trở lại làm secondary.

**Ngộ nhận 10: “Một exception sau stepdown chứng minh command thất bại.”**

Không đủ. Kết nối có thể bị đóng như một phần của role change. Cần xác minh trạng thái cluster.

## 31. Bài tập kiểm tra kiến thức

### Câu 1. Majority của replica set ba voter là bao nhiêu?

**Đáp án:** 2 phiếu. Nếu chỉ một voter còn liên lạc được với chính nó, nó không đạt đa số.

### Câu 2. Một secondary có priority 0 nhưng votes 1 có trở thành primary không?

**Đáp án:** Không. Nó có thể tham gia bỏ phiếu theo cấu hình, nhưng priority 0 khiến nó không được bầu primary.

### Câu 3. Stepdown và shutdown khác nhau ở điểm nào?

**Đáp án:** Stepdown thay vai trò primary trong replica set; shutdown dừng tiến trình.

### Câu 4. Vì sao client chỉ kết nối trực tiếp tới node-a có thể gặp vấn đề sau stepdown?

**Đáp án:** Node-a không còn writable primary. Nếu ứng dụng pin kết nối, nó không tự chọn primary mới như driver với replica set topology.

### Câu 5. Khi user POST tạo đơn nhận timeout, có thể tự gửi POST lại ngay với ID mới không?

**Đáp án:** Không an toàn. Write trước có thể đã thực hiện. Cần giữ request ID, retry theo chính sách, và đối soát/idempotency.

### Câu 6. Write concern majority có ý nghĩa gì trong bối cảnh failover?

**Đáp án:** Nó yêu cầu số thành viên lưu dữ liệu cần thiết xác nhận theo majority write concern, giúp giảm rủi ro mất những write được xác nhận khi có election/rollback.

### Câu 7. Read preference secondaryPreferred làm server cho phép ghi vào secondary khi không có primary không?

**Đáp án:** Không. Nó là chính sách chọn node **đọc**.

### Câu 8. Vì sao rs.stepDown có thể ngắt kết nối mongosh?

**Đáp án:** Khi primary rời role, một số connection/operation bị gián đoạn. Cần reconnect, kiểm tra trạng thái, không kết luận từ lỗi riêng lẻ.

### Câu 9. TransientTransactionError khác UnknownTransactionCommitResult ra sao?

**Đáp án:** Một loại gợi ý cần retry toàn bộ transaction theo helper/protocol thích hợp; loại còn lại nói kết quả commit chưa rõ và cần retry commit/đối soát theo semantics tương ứng.

### Câu 10. Tại sao node ping được nhưng không nhận insert?

**Đáp án:** Nó có thể là secondary, đang recovering, hoặc không còn writable primary; network reachability không phải quyền ghi.

## 32. Bài tập thiết kế tình huống

### Tình huống A — Node chính mất nguồn

Replica set có A, B, C đều là data-bearing voter, A primary. A mất nguồn, B và C còn liên lạc.

Trình bày:

1. Majority cần mấy phiếu?
2. B/C có thể làm gì?
3. Trong election gap, ứng dụng ghi có thể thấy lỗi nào?
4. Connection string phải có đặc điểm gì?
5. Vì sao cần xem write concern của các giao dịch trước khi A mất nguồn?

### Tình huống B — Mạng tách 1–2

A ở nhóm một node, B+C ở nhóm hai node. Các node không liên lạc qua hai nhóm.

Giải thích vì sao nhóm có hai voter có cơ hội bầu một primary hợp lệ, còn A đơn lẻ không nên tiếp tục giữ vai trò ghi. Có thể có khoảng thời gian driver vẫn nghĩ A là primary không? Ứng dụng cần phản ứng thế nào?

### Tình huống C — Đang xử lý thanh toán

Ứng dụng nhận request có idempotency key `payment-777`. Sau khi gửi write cập nhật trạng thái, kết nối tới primary bị reset.

Hãy thiết kế:

- Các trạng thái “đã commit”, “không commit” và “chưa rõ”.
- Thao tác đối soát theo key.
- Giới hạn retry.
- Cách tránh gọi payment gateway lần hai.
- Vai trò transaction/outbox nếu có nhiều collection hoặc external side effects.

### Tình huống D — Tự động failover nhưng API lỗi 30 giây

Trong monitoring, election hoàn thành sớm nhưng API vẫn liên tục báo server selection timeout.

Đề xuất kiểm tra:

1. Ứng dụng có dùng `directConnection=true` không?
2. Seed list và `replicaSet` name có đúng không?
3. Advertised hosts trong `rs.conf()` có phân giải được từ app host không?
4. Firewall/TLS của primary mới có cho client truy cập không?
5. MongoClient có bị tạo lại quá thường xuyên không?
6. Connection pool/network load có bất thường không?
7. Deadline ứng dụng có ngắn hơn thời gian cần discovery không?

### Tình huống E — Rolling maintenance

Một DBA muốn cập nhật phần mềm trên replica set ba node. Hãy giải thích vì sao cần kiểm tra replication health, member eligibility, majority, thứ tự bảo trì và khả năng client reconnect **trước** khi stepdown primary.

Không tự đề xuất thao tác shutdown hàng loạt cùng lúc. Thứ tự và compatibility của rolling upgrade phải dựa trên runbook dành cho phiên bản MongoDB cụ thể.

## 33. Checklist trước khi đưa ứng dụng vào production

### Về replica set

- [ ] Có đủ data-bearing members/voters theo mục tiêu chịu lỗi.
- [ ] Majority và network topology được hiểu rõ.
- [ ] Secondary ứng cử có priority/votes phù hợp.
- [ ] Replication lag và health được giám sát.
- [ ] Không phụ thuộc vào arbiter như một bản sao dữ liệu.
- [ ] Có runbook stepdown và cách xác minh primary mới.
- [ ] Có quy trình xử lý khi không đạt majority.

### Về client và kết nối

- [ ] URI mô tả replica set, có nhiều seed hosts hoặc discovery endpoint phù hợp.
- [ ] Không pin ứng dụng ghi vào host primary cũ.
- [ ] Tất cả advertised hosts có thể truy cập từ application network.
- [ ] MongoClient/connection pool có vòng đời dài hạn.
- [ ] Server selection timeout, connect timeout và request deadline được định nghĩa.
- [ ] Read/write retry được bật khi phù hợp với driver/server.
- [ ] Read preference và read concern được chọn theo nghiệp vụ.

### Về an toàn nghiệp vụ

- [ ] Những write quan trọng có write concern phù hợp.
- [ ] Request tạo/sửa có idempotency key hoặc điều kiện chống ghi lặp.
- [ ] Kết quả ghi không rõ được đối soát, không mặc định là thất bại.
- [ ] Transactions xử lý transient error và commit unknown đúng semantics.
- [ ] Side effects ngoài database không bị lặp khi transaction callback retry.
- [ ] Có backoff, jitter và retry budget.
- [ ] HTTP status và trạng thái pending/reconciliation có hợp đồng rõ.

### Về giám sát

- [ ] Theo dõi primary changes/election term.
- [ ] Theo dõi replica lag và member health.
- [ ] Theo dõi server selection timeout, not-primary, network errors.
- [ ] Theo dõi p95/p99 request latency trong failover.
- [ ] Ghi nhận request ID để đối soát các thao tác chưa rõ kết quả.
- [ ] Có diễn tập failover trên staging với workload đại diện.

## 34. Tổng kết

MongoDB replica set có thể tự bầu primary mới khi primary hiện tại không còn phù hợp. Tuy nhiên, một cuộc bầu chọn thành công chỉ là **một phần** của khả năng phục hồi ứng dụng.

- **Election:** đòi hỏi đa số phiếu của các voting members và ứng cử viên đủ điều kiện; thiếu majority có thể dẫn tới không có primary.
- **Priority/votes:** quyết định khả năng tham gia bầu cử và mức ưu tiên, không thay thế kiểm tra trạng thái/độ cập nhật.
- **Stepdown:** chủ động rời role primary để bảo trì; không đồng nghĩa shutdown hay downtime bằng số giây truyền vào.
- **Replica set URI + SDAM:** cho phép driver tìm primary hiện tại và chuyển địa chỉ ghi khi topology đổi.
- **Retryable reads/writes:** giúp phục hồi nhiều lỗi tạm thời nhưng chỉ theo những operation/điều kiện được hỗ trợ.
- **Write concern majority:** tăng bảo đảm độ bền cho write được xác nhận; không thể thay thế thiết kế idempotency khi client mất ACK.
- **Transactions:** phân biệt transient failure với commit outcome unknown; tránh side effects không idempotent trong callback có thể retry.
- **Monitoring/runbook:** quan sát từ trạng thái server tới lỗi client, đo thời gian mất khả năng ghi, và đối soát những request có kết quả chưa rõ.

Một hệ thống MongoDB có tính sẵn sàng cao không chỉ cần **bầu chọn primary nhanh**, mà còn phải có **ứng dụng kết nối đúng topology, phản ứng an toàn khi failover và duy trì ngữ nghĩa nghiệp vụ khi retry**.

## Tài liệu tham khảo chính thức

- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [MongoDB Manual — Replica Set Primary](https://www.mongodb.com/docs/manual/core/replica-set-primary/)
- [MongoDB Manual — Replica Set High Availability](https://www.mongodb.com/docs/manual/core/replica-set-high-availability/)
- [MongoDB Manual — rs.stepDown](https://www.mongodb.com/docs/manual/reference/method/rs.stepDown/)
- [MongoDB Manual — replSetStepDown command](https://www.mongodb.com/docs/manual/reference/command/replSetStepDown/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Production Notes for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Java Sync Driver — Connection Options](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/)
