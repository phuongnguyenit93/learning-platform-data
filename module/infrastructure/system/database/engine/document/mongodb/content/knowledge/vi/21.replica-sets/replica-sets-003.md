# Khởi tạo replica set, cấu hình thành viên và kiểm tra `rs.status()` trong MongoDB

## 1. Mục tiêu và bối cảnh

Một MongoDB server đơn lẻ có thể lưu và truy vấn document, nhưng nếu tiến trình `mongod` đó dừng hoặc máy chủ bị mất kết nối thì ứng dụng không còn nơi tiếp nhận thao tác đọc/ghi như bình thường. **Replica set** là cơ chế MongoDB tổ chức nhiều tiến trình `mongod` cùng duy trì bản sao của một tập dữ liệu, để có thể **bầu một thành viên primary mới** khi primary cũ không còn phục vụ.

Bài học này tập trung vào ba công việc quản trị:

1. **Khởi tạo replica set**: cấu hình các `mongod` tham gia cùng một tập, chạy `rs.initiate()` và xác nhận bầu primary.
2. **Cấu hình thành viên**: nhận diện `_id`, `host`, `priority`, `votes`, arbiter, secondary không được bầu; bổ sung hoặc thay đổi thành viên bằng công cụ phù hợp.
3. **Kiểm tra `rs.status()`**: đọc trạng thái PRIMARY/SECONDARY, khả năng kết nối, thông tin heartbeat, replication và những dấu hiệu bất thường.

Kết thúc bài, bạn cần phân biệt được:

- **Replica set name** với tên database hay collection.
- **Primary** với **secondary** và **arbiter**.
- **Bầu cử có đa số phiếu** với **sao chép dữ liệu đã hoàn tất**.
- `rs.conf()` là **cấu hình mong muốn**, còn `rs.status()` là **trạng thái quan sát được** tại thời điểm gọi.
- **Một node bị DOWN** với **toàn bộ replica set không có primary**.
- Ví dụ mô phỏng an toàn trên máy cá nhân với cấu hình cần có cho production.

## 2. Replica set vận hành như thế nào?

### 2.1. Primary, secondary và oplog

Trong mô hình cơ bản, replica set có một **primary** và các **secondary**:

```text
                  MongoDB replica set "rsLab"

  Ứng dụng / MongoDB driver
              |
              | Ghi bình thường
              v
     +---------------------+
     | Node A — PRIMARY    |
     | localhost:27117     |
     +---------------------+
              |
       Oplog / replication
         /             \
        v               v
 +----------------+  +----------------+
 | Node B         |  | Node C         |
 | SECONDARY      |  | SECONDARY      |
 | localhost:27118|  | localhost:27119|
 +----------------+  +----------------+

      Các node trao đổi heartbeat và tham gia bầu cử.
```

**Primary** thông thường nhận các thao tác ghi của ứng dụng. **Secondary** sao chép các thay đổi từ luồng **oplog** (operation log) của thành viên phù hợp rồi áp dụng vào dữ liệu của nó. Việc sao chép có tính **bất đồng bộ**, nên một secondary có thể đi sau primary trong khoảng thời gian ngắn hoặc dài tùy tải và tình trạng hệ thống.

Secondary không mặc định là nơi có thể ghi dữ liệu nghiệp vụ. Muốn đọc từ secondary, driver cần read preference thích hợp; việc đọc đó có thể thấy dữ liệu chậm hơn primary.

### 2.2. Bầu primary không có nghĩa luôn có primary

Thành viên có quyền biểu quyết tham gia chọn primary. Một primary cần **đa số phiếu của những voting members theo cấu hình** để được bầu và duy trì vị thế. Với ba thành viên có `votes: 1` mỗi thành viên, đa số là **hai phiếu**.

```text
Ban đầu:
  A PRIMARY    B SECONDARY    C SECONDARY
      1             1              1      => 3 phiếu

A mất kết nối, B và C còn thấy nhau:
  B + C = 2 phiếu / 3 => có thể bầu primary mới

Chỉ còn B, A và C đều mất:
  B = 1 phiếu / 3     => không đủ đa số để bầu primary
```

**Replica set tăng khả năng sẵn sàng, không bảo đảm hệ thống luôn phục vụ ghi trong mọi kiểu sự cố.** Nếu không còn đa số thành viên bỏ phiếu liên lạc với nhau, hệ thống có thể tạm thời không có primary, và thao tác ghi phụ thuộc primary sẽ không thành công.

### 2.3. Số lượng node và lựa chọn thông dụng

| Cấu hình | Đặc điểm | Phù hợp |
|---|---|---|
| 1 data-bearing member | Có thể là replica set một thành viên; không chịu lỗi node | Thực hành, một số môi trường phát triển |
| 3 data-bearing members | Một primary, hai secondary khi ổn định; đa số 2/3 | Mô hình production phổ biến |
| 2 data-bearing + 1 arbiter | Có ba phiếu nhưng chỉ hai bản sao dữ liệu | Tình huống tài nguyên hạn chế; cần cân nhắc kỹ write concern |
| 5 data-bearing members | Đa số 3/5, nhiều khả năng chịu lỗi hơn | Khi yêu cầu về topology và tài nguyên phù hợp |

Không phải thêm càng nhiều node càng tốt. Số voting members bị giới hạn; chi phí replication, băng thông, dung lượng, số phiên, độ trễ liên vùng và vận hành đều tăng theo topology.

**Khuyến nghị cho lab:** dùng ba tiến trình `mongod` trên **một máy**, khác port và khác thư mục dữ liệu. Đây là mô hình giúp học `rs.status()` nhưng **không phải high availability thật**, vì một lỗi máy sẽ làm cả ba node ngừng hoạt động.

## 3. Chuẩn bị trước khi khởi tạo

### 3.1. Những điều kiện tối thiểu

Mỗi `mongod` tham gia một replica set phải:

- Được cấu hình cùng **replica set name**, ví dụ `rsLab`.
- Có **dbPath riêng**; tuyệt đối không cho hai `mongod` truy cập cùng thư mục dữ liệu.
- Có **host:port** riêng, các thành viên khác có thể phân giải và kết nối tới đúng địa chỉ đó.
- Có MongoDB version và cấu hình tương thích với topology; cần kiểm tra quy tắc nâng cấp phiên bản nếu trộn nhiều phiên bản.
- Có mạng, firewall, DNS, hostname và độ đồng bộ đồng hồ phù hợp.
- Có cơ chế xác thực nội bộ và bảo vệ kết nối nếu triển khai ngoài lab.

Replica set name phải thống nhất giữa cấu hình khởi động và cấu hình được `rs.initiate()` sử dụng. Một node chạy với `--replSet rsOther` không thể tự nhiên gia nhập cấu hình `rsLab`.

### 3.2. Phân biệt môi trường học với production

Trong lab bên dưới:

- Ba tiến trình chạy **cùng một máy**.
- Cả ba bind vào `127.0.0.1`/`localhost`, không mở cho bên ngoài.
- Dùng hostname `localhost` và ba port khác nhau.
- Không dùng bộ dữ liệu nhạy cảm.
- Không bật cấu hình network/public có khả năng khiến MongoDB không được xác thực bị lộ ra Internet.

Ở production, cần có thêm **authentication/authorization**, **internal authentication** (ví dụ keyfile hoặc x.509 theo kiến trúc bảo mật), **TLS khi phù hợp**, DNS ổn định, mạng riêng, giám sát, backup và kế hoạch khôi phục. Không copy các lệnh lab thiếu xác thực lên máy chủ công khai.

### 3.3. Hostname thay vì địa chỉ IP cố định

Các thành viên phải sử dụng những tên mà **mọi node và client dự kiến** có thể phân giải và kết nối. Với deployment nhiều máy, nên dùng hostname ổn định:

```text
mongo-a.internal.example:27017
mongo-b.internal.example:27017
mongo-c.internal.example:27017
```

Các tên trên chỉ là **ví dụ**, không phải máy chủ thực. MongoDB các phiên bản hiện đại có kiểm tra liên quan tới split-horizon DNS và cấu hình chỉ dùng IP; cần kiểm tra quy tắc hostname của version triển khai thay vì dùng địa chỉ IP trực tiếp theo thói quen.

**Lưu ý quan trọng:** driver khám phá thành viên từ cấu hình replica set. Nếu một ứng dụng chạy ở máy khác kết nối đến `localhost:27117` và server trả danh sách `localhost:27118`, `localhost:27119`, thì `localhost` ở phía ứng dụng lại trỏ về **chính máy ứng dụng**, gây lỗi khám phá topology. Cấu hình `localhost` chỉ dành cho lab chạy cùng máy.

## 4. Khởi động ba tiến trình `mongod` trên cùng máy

Phần này mô tả một **lab cục bộ**. Các command là ví dụ khi đã cài MongoDB server binaries và `mongosh`. Dùng một tập thư mục mới riêng biệt.

### 4.1. Tạo ba thư mục dữ liệu

Ví dụ PowerShell trên Windows:

```powershell
New-Item -ItemType Directory -Force -Path "C:\mongo-rs-lab\node1"
New-Item -ItemType Directory -Force -Path "C:\mongo-rs-lab\node2"
New-Item -ItemType Directory -Force -Path "C:\mongo-rs-lab\node3"
```

Trên Linux/macOS:

```bash
mkdir -p ~/mongo-rs-lab/node1
mkdir -p ~/mongo-rs-lab/node2
mkdir -p ~/mongo-rs-lab/node3
```

Mỗi thư mục là một **data directory độc lập**. Không được chia sẻ cùng một dbPath giữa các node.

### 4.2. Chạy từng tiến trình ở terminal riêng

Ví dụ Windows, mở **ba PowerShell terminal** và chạy lần lượt:

Terminal 1:

```powershell
mongod --replSet rsLab --port 27117 --dbpath "C:\mongo-rs-lab\node1" --bind_ip localhost
```

Terminal 2:

```powershell
mongod --replSet rsLab --port 27118 --dbpath "C:\mongo-rs-lab\node2" --bind_ip localhost
```

Terminal 3:

```powershell
mongod --replSet rsLab --port 27119 --dbpath "C:\mongo-rs-lab\node3" --bind_ip localhost
```

Trên Linux/macOS, thay `dbpath` thành thư mục tương ứng dưới `~/mongo-rs-lab`:

```bash
# Terminal 1
mongod --replSet rsLab --port 27117 \
  --dbpath "$HOME/mongo-rs-lab/node1" \
  --bind_ip localhost

# Terminal 2
mongod --replSet rsLab --port 27118 \
  --dbpath "$HOME/mongo-rs-lab/node2" \
  --bind_ip localhost

# Terminal 3
mongod --replSet rsLab --port 27119 \
  --dbpath "$HOME/mongo-rs-lab/node3" \
  --bind_ip localhost
```

Các tiến trình chạy ở foreground và ghi log ra terminal, nên cần **giữ ba terminal mở** trong thời gian thực hành. Không chạy cả ba command tuần tự trong cùng một terminal foreground rồi mong cả ba tự hoạt động song song.

### 4.3. Vì sao chọn các option này?

| Option | Vai trò |
|---|---|
| `--replSet rsLab` | Khởi động node trong ngữ cảnh replica set có tên `rsLab` |
| `--port 27117` | Chọn cổng TCP của node; ba node phải khác cổng trên cùng máy |
| `--dbpath ...` | Nơi lưu dữ liệu của chính node đó |
| `--bind_ip localhost` | Chỉ lắng nghe loopback; giảm rủi ro truy cập từ ngoài máy lab |

Khởi động với `--replSet` **chưa đồng nghĩa replica set đã được khởi tạo**. Các tiến trình mới chỉ sẵn sàng nhận cấu hình và tham gia tập.

### 4.4. Cấu hình qua file YAML thay vì command line

Trong môi trường vận hành, cấu hình bằng file thường dễ kiểm soát hơn:

```yaml
# Ví dụ cho node A; path và host chỉ dùng trong lab.
storage:
  dbPath: /home/student/mongo-rs-lab/node1

net:
  port: 27117
  bindIp: localhost

replication:
  replSetName: rsLab
```

Chạy:

```bash
mongod --config /path/to/mongod-a.conf
```

Cần có **một file cấu hình riêng trên mỗi node**, với cổng và dbPath đúng của node đó. Đối với production, sẽ bổ sung bảo mật, logging, process management, storage và các thành phần khác. Đừng suy từ ví dụ ngắn này rằng file trên là cấu hình production hoàn chỉnh.

## 5. Kết nối node đầu tiên và gọi `rs.initiate()`

### 5.1. Kết nối bằng `mongosh`

Mở terminal thứ tư:

```bash
mongosh "mongodb://localhost:27117/?directConnection=true"
```

Tham số `directConnection=true` ở đây có ích trong giai đoạn khởi tạo, khi node chưa có topology replica set hoạt động và ta muốn kết nối đúng node đầu tiên. Không sử dụng URL này như cấu hình ứng dụng production cần tự động phát hiện primary và failover.

### 5.2. Khởi tạo toàn bộ ba thành viên một lần

Trong `mongosh` đang kết nối vào node A:

```javascript
rs.initiate({
  _id: "rsLab",
  members: [
    {
      _id: 0,
      host: "localhost:27117",
      priority: 2
    },
    {
      _id: 1,
      host: "localhost:27118",
      priority: 1
    },
    {
      _id: 2,
      host: "localhost:27119",
      priority: 1
    }
  ]
});
```

Ý nghĩa:

- `_id: "rsLab"` ở cấp trên là **tên replica set**, phải khớp với `--replSet rsLab`.
- `members` là danh sách các thành viên mong muốn.
- `members[n]._id` là **số nguyên định danh thành viên trong cấu hình**, không phải `_id` document.
- `members[n].host` là **hostname:port** để các node tìm nhau.
- `priority: 2` ở A làm A được ưu tiên hơn trong các cuộc bầu cử **khi các điều kiện khác cho phép**; nó không bảo đảm A luôn luôn là primary.
- B và C có `priority: 1` nên cũng có thể trở thành primary nếu đủ điều kiện.

Không gọi `rs.initiate()` trên cả ba node. **Chỉ khởi tạo replica set một lần** với cùng cấu hình. Các node khác gia nhập theo cấu hình mà replica set phân phối.

### 5.3. Vì sao phải chờ bầu cử?

`rs.initiate()` có thể trả về phản hồi xác nhận trước khi toàn bộ các node sẵn sàng. Sau khi khởi tạo:

1. Thành viên nhận cấu hình.
2. Các thành viên liên lạc và trao đổi trạng thái.
3. Replica set thực hiện bầu cử primary nếu đạt điều kiện.
4. Secondary đồng bộ dữ liệu và tiếp tục áp dụng oplog.

`rs.status()` có thể hiển thị các trạng thái chuyển tiếp như `STARTUP2` hoặc `RECOVERING` trong giai đoạn đầu. Không tự coi mọi trạng thái chưa phải SECONDARY ngay sau `rs.initiate()` là lỗi không thể phục hồi.

### 5.4. Kiểm tra đã có primary

```javascript
rs.status();
```

Sau khi quá trình bầu cử ổn định, mục tiêu của lab là thấy:

```text
localhost:27117   PRIMARY
localhost:27118   SECONDARY
localhost:27119   SECONDARY
```

Đây là **một kết quả có thể xảy ra** vì priority của A cao hơn. Nhưng nếu node A chưa sẵn sàng, thiếu heartbeat, không đủ điều kiện hoặc có sự kiện bầu cử khác, primary có thể tạm ở node khác. Nên kiểm tra trạng thái thực tế, không viết ứng dụng phụ thuộc cứng vào A.

## 6. Khởi tạo replica set một node để học nhanh

Nếu chỉ có một `mongod` trên máy học, MongoDB vẫn có thể dùng **single-node replica set** để thử những tính năng cần cấu hình replica set, chẳng hạn transaction trong những điều kiện hỗ trợ.

Ví dụ một lab **độc lập hoàn toàn** với `rsLab` ở phần trước:

```bash
# Chạy mongod có dbPath riêng trên port 27217.
mongod --replSet rsSingle --port 27217 \
  --dbpath "/path/to/single-node-data" \
  --bind_ip localhost
```

Sau khi đã tạo thư mục dữ liệu và tiến trình chạy, kết nối:

```bash
mongosh "mongodb://localhost:27217/?directConnection=true"
```

Rồi:

```javascript
rs.initiate({
  _id: "rsSingle",
  members: [
    { _id: 0, host: "localhost:27217" }
  ]
});

rs.status();
```

Một node có thể tự bầu làm primary vì có đủ đa số phiếu trong tập một thành viên. Tuy nhiên, nếu tiến trình đó ngừng, **không có node còn lại để tiếp tục phục vụ**. Đừng hiểu “single-node replica set” là kiến trúc high availability.

**Không dùng lại dbPath của `rsLab` cho `rsSingle`.** Mỗi ví dụ là một môi trường khác biệt.

## 7. `rs.status()`: đọc trạng thái thực tế

### 7.1. Cú pháp

Sau khi kết nối tới một thành viên replica set:

```javascript
rs.status();
```

Lệnh này cung cấp thông tin trạng thái replication mà thành viên được kết nối quan sát tại thời điểm gọi. Kết quả có thể khác nhau tùy node nào được hỏi, thời điểm heartbeat và phiên bản MongoDB.

### 7.2. Cấu trúc kết quả minh họa

```javascript
{
  set: "rsLab",
  date: ISODate("2026-11-14T04:00:00Z"),
  myState: 1,
  term: NumberLong("1"),
  heartbeatIntervalMillis: NumberLong("2000"),
  members: [
    {
      _id: 0,
      name: "localhost:27117",
      health: 1,
      state: 1,
      stateStr: "PRIMARY",
      uptime: 1200,
      optimeDate: ISODate("2026-11-14T03:59:59Z"),
      self: true
    },
    {
      _id: 1,
      name: "localhost:27118",
      health: 1,
      state: 2,
      stateStr: "SECONDARY",
      uptime: 1180,
      optimeDate: ISODate("2026-11-14T03:59:58Z")
    },
    {
      _id: 2,
      name: "localhost:27119",
      health: 1,
      state: 2,
      stateStr: "SECONDARY",
      uptime: 1180,
      optimeDate: ISODate("2026-11-14T03:59:58Z")
    }
  ],
  ok: 1
}
```

Đây là **bản rút gọn minh họa**, không phải JSON đầu ra đầy đủ hay giá trị thực của lab. MongoDB thường trả thêm nhiều trường liên quan đến optime, heartbeat, phiên bản cấu hình, sync source, election và trạng thái lưu trữ.

### 7.3. Nhóm trường cấp trên

| Trường | Ý nghĩa |
|---|---|
| `set` | Tên replica set mà node tin rằng mình thuộc về |
| `date` | Thời điểm server tạo phản hồi trạng thái |
| `myState` | Mã trạng thái **của node đang được kết nối** |
| `term` | Election term; giúp nhận diện giai đoạn bầu cử trong giao thức hiện đại |
| `members` | Danh sách thông tin trạng thái của từng thành viên mà node quan sát được |
| `ok` | Trạng thái thành công của command; `ok: 1` không đồng nghĩa mọi thành viên đều khỏe |

Đặc biệt: **`ok: 1` chỉ cho biết lệnh trạng thái được thực thi thành công**, không bảo đảm replica set có đủ đa số, có primary hoặc không bị replication lag.

### 7.4. Nhóm trường ở từng thành viên

| Trường | Ý nghĩa thực tế |
|---|---|
| `_id` | Member ID trong replica set config |
| `name` | Hostname:port của thành viên |
| `health` | Chỉ báo khả năng liên lạc theo quan sát; thường 1 là thấy khỏe, 0 là không liên lạc được |
| `state` | Mã trạng thái số |
| `stateStr` | Tên trạng thái, ví dụ `PRIMARY`, `SECONDARY` hoặc `ARBITER` |
| `uptime` | Số giây thành viên đã chạy theo thông tin được báo |
| `optime` / `optimeDate` | Vị trí/thời điểm replication tương ứng; cách hiển thị tùy phiên bản |
| `lastHeartbeat` | Thời điểm liên lạc heartbeat gần đây, khi trường được báo |
| `lastHeartbeatRecv` | Thời điểm nhận heartbeat gần đây, khi trường được báo |
| `lastHeartbeatMessage` | Thông điệp liên quan lần heartbeat, hữu ích khi có lỗi |
| `pingMs` | Thông tin RTT heartbeat quan sát được |
| `syncSourceHost` | Nguồn đồng bộ mà secondary đang dùng, nếu có |
| `self` | Chỉ báo phần tử đại diện cho node đang được hỏi |

Không phải mọi thành viên và mọi phiên bản đều cung cấp tất cả các trường này. Một trường vắng mặt **không tự động là lỗi**; đọc cùng `stateStr`, `health` và log của node.

## 8. Các trạng thái `stateStr` thường gặp

### 8.1. PRIMARY và SECONDARY

`PRIMARY` là thành viên được bầu để nhận ghi bình thường. Một replica set khỏe thường chỉ có **một primary** trong một thời điểm của cấu hình, và nhiều secondary sẵn sàng đồng bộ.

`SECONDARY` là thành viên đã vào trạng thái thứ cấp phù hợp, đang theo dõi/áp dụng oplog và có thể tham gia bầu cử nếu cấu hình cho phép.

### 8.2. Bảng trạng thái cần nhận biết

| Mã `state` | `stateStr` | Cách hiểu |
|---:|---|---|
| 0 | `STARTUP` | Thành viên đang khởi động |
| 1 | `PRIMARY` | Thành viên primary hiện tại |
| 2 | `SECONDARY` | Thành viên secondary |
| 3 | `RECOVERING` | Đang phục hồi, chưa phục vụ như secondary bình thường |
| 5 | `STARTUP2` | Giai đoạn khởi tạo/initial sync |
| 6 | `UNKNOWN` | Chưa xác định trạng thái thành viên từ node đang hỏi |
| 7 | `ARBITER` | Thành viên bỏ phiếu nhưng không lưu bộ dữ liệu ứng dụng |
| 8 | `DOWN` | Thành viên không thể liên lạc theo quan sát |
| 9 | `ROLLBACK` | Thành viên đang rollback thao tác chưa được giữ trong lịch sử được chọn |
| 10 | `REMOVED` | Thành viên đã bị loại khỏi cấu hình replica set |

Trên node hoặc bản MongoDB cụ thể có thể có các trạng thái nội bộ khác. Các tên trên là những trạng thái thường gặp để định hướng vận hành, không phải lời khuyên phản ứng giống nhau cho mọi trường hợp.

### 8.3. Khi nào một trạng thái chỉ là chuyển tiếp?

Ví dụ sau khi thêm secondary mới, node phải thực hiện **initial sync**:

```text
Khởi động -> STARTUP/STARTUP2 -> đồng bộ dữ liệu -> SECONDARY
```

Trong lúc đó, nhìn thấy `STARTUP2` không nhất thiết là sự cố. Nhưng nếu trạng thái kéo dài quá kỳ vọng, cần xem log, dung lượng ổ đĩa, mạng, tốc độ đồng bộ, kích thước dữ liệu và khả năng truy cập sync source.

Tương tự, `RECOVERING` có thể xuất hiện trong quá trình phục hồi bình thường hoặc vì một vấn đề kéo dài. **Trạng thái đơn lẻ chưa đủ để chẩn đoán nguyên nhân.**

## 9. Rút gọn `rs.status()` để dễ quan sát

Đầu ra `rs.status()` có thể rất dài. Trong `mongosh`, ta có thể chỉ in những trường trọng yếu:

```javascript
const s = rs.status();

s.members.map(m => ({
  memberId: m._id,
  host: m.name,
  state: m.stateStr,
  health: m.health,
  optimeDate: m.optimeDate,
  syncSourceHost: m.syncSourceHost,
  lastHeartbeatMessage: m.lastHeartbeatMessage
}));
```

Ví dụ cần xác định primary:

```javascript
rs.status().members
  .filter(m => m.stateStr === "PRIMARY")
  .map(m => m.name);
```

Khi hệ thống ổn định và có primary, mảng kết quả nên chứa tên của thành viên PRIMARY theo quan sát của node hiện tại. Nếu mảng rỗng, kiểm tra tiếp xem có đang bầu cử hoặc mất đa số phiếu hay không.

### 9.1. Đừng dựa vào `name` để nhận biết role cố định

Một hôm `localhost:27117` có thể là PRIMARY; hôm khác thành viên khác được bầu. Dù đã cấu hình priority của A cao hơn, **ứng dụng không nên cấu hình ghi cứng vào một host**.

Chọn cách kết nối bằng replica set URI cho phép driver khám phá primary mới. `rs.status()` giúp quan sát vận hành, không thay driver topology discovery.

### 9.2. Trạng thái quan sát từ một node có thể chậm hơn thực tế

Heartbeat được trao đổi theo chu kỳ và mạng có độ trễ. Sau khi một node ngừng, một node khác có thể chưa cập nhật ngay `health: 0` hoặc `stateStr: "DOWN"`. Vì vậy:

- Chụp trạng thái tại nhiều thời điểm nếu đang điều tra sự cố.
- Khi cần, xem từ primary và secondary còn liên lạc được.
- Kết hợp log, metrics và tình trạng kết nối thật.
- Không ra quyết định destructive chỉ vì một ảnh chụp `rs.status()` nhất thời.

## 10. `rs.conf()` khác gì `rs.status()`?

### 10.1. `rs.conf()` mô tả cấu hình

```javascript
rs.conf();
```

Kết quả chứa những thông tin như:

```javascript
{
  _id: "rsLab",
  version: 1,
  members: [
    { _id: 0, host: "localhost:27117", priority: 2, votes: 1 },
    { _id: 1, host: "localhost:27118", priority: 1, votes: 1 },
    { _id: 2, host: "localhost:27119", priority: 1, votes: 1 }
  ]
  // Còn có settings và metadata khác...
}
```

Cấu trúc trên là minh họa. `rs.conf()` mô tả **thành viên được cấu hình**, priority, votes và những thiết lập của replica set.

### 10.2. `rs.status()` mô tả trạng thái vận hành

```javascript
rs.status();
```

Một thành viên B có thể **có trong `rs.conf()`** nhưng **hiển thị DOWN trong `rs.status()`**. Cấu hình chỉ nói rằng B là một thành viên mong muốn; nó không bảo đảm tiến trình B đang chạy hoặc kết nối được.

### 10.3. Bảng đối chiếu

| Câu hỏi | Lệnh phù hợp |
|---|---|
| Replica set gồm những host nào theo cấu hình? | `rs.conf()` |
| Priority và votes của từng member hiện đặt bao nhiêu? | `rs.conf()` |
| Thành viên nào đang PRIMARY? | `rs.status()` hoặc `hello` trên node liên quan |
| Node B có liên lạc được không? | `rs.status()`, log và kiểm tra mạng |
| Secondary có đang theo kịp không? | `rs.status()` và chỉ số replication |
| Phiên bản cấu hình là gì? | `rs.conf().version` |

Đừng sửa cấu hình chỉ vì `rs.status()` có một node tạm thời DOWN. Trước tiên xác định **nguyên nhân không kết nối được**.

## 11. Kiểm tra role bằng command `hello`

`rs.status()` cung cấp nhiều thông tin tổng quan. Khi chỉ muốn xác định node đang được kết nối có phải primary không, dùng:

```javascript
db.adminCommand({ hello: 1 });
```

Một số trường hay gặp:

- `isWritablePrimary`: node có đang ở vai trò writable primary theo giao thức này hay không.
- `secondary`: node đang có vai trò secondary hay không.
- `setName`: tên replica set.
- `hosts`: danh sách host thuộc replica set mà node công bố, khi có.
- `primary`: host primary mà node biết, khi có.
- `me`: host của chính node đang được hỏi.

Ví dụ rút gọn:

```javascript
{
  isWritablePrimary: true,
  secondary: false,
  setName: "rsLab",
  hosts: [
    "localhost:27117",
    "localhost:27118",
    "localhost:27119"
  ],
  primary: "localhost:27117",
  me: "localhost:27117",
  ok: 1
}
```

Đây là mẫu minh họa; phản hồi thực có thêm nhiều trường. Các API cũ có thể nhắc tới `isMaster`, nhưng ứng dụng hiện đại nên dùng `hello`/`isWritablePrimary` theo driver và server hiện hành.

### 11.1. Quan sát từng node trong lab

Kết nối trực tiếp tới secondary B:

```bash
mongosh "mongodb://localhost:27118/?directConnection=true"
```

Chạy:

```javascript
db.adminCommand({ hello: 1 });
rs.status();
```

Một secondary bình thường sẽ báo `secondary: true` và `isWritablePrimary: false`. Cách xem trực tiếp giúp phân biệt **node đang kết nối** với **primary của cả set**.

## 12. Theo dõi replication lag và optime

Một replica set có primary và secondary chưa chắc mọi secondary đều có dữ liệu mới nhất ở cùng thời điểm. `rs.status()` có những trường để theo dõi tiến độ replication, chẳng hạn:

- `optime`: mốc logic mà node đã đạt đến trong oplog.
- `optimeDate`: thời điểm liên quan tới optime.
- `lastAppliedWallTime` và `lastDurableWallTime` khi có: thông tin thời gian về thao tác đã áp dụng/đã bền vững.
- `syncSourceHost`: node mà secondary dùng làm nguồn đồng bộ.
- Thông tin optime/majority commit ở cấp replica set, tùy phiên bản.

### 12.1. Ví dụ đọc optime

```javascript
rs.status().members.map(m => ({
  member: m.name,
  state: m.stateStr,
  optimeDate: m.optimeDate,
  syncSourceHost: m.syncSourceHost
}));
```

Nếu primary đã áp dụng thao tác tại 10:00:05, còn secondary mới đến 10:00:02, secondary có thể bị trễ theo quan sát. Tuy nhiên, so sánh timestamps **không phải cách đo replication lag hoàn hảo**:

- Đồng hồ giữa các máy cần được đồng bộ.
- Khi không có thao tác ghi mới, mốc optime có thể không tiến.
- Một secondary đang initial sync hoặc vừa đổi sync source có thể có hành vi khác.
- Các trường timestamp của bản MongoDB cụ thể có ý nghĩa riêng.

Tránh viết cảnh báo “secondary chậm 3 giây” chỉ bằng cách lấy thời gian hiện tại trừ `optimeDate` mà không kiểm tra xem hệ thống thực sự có ghi mới hay không.

### 12.2. Các helper trong mongosh

Có thể sử dụng những helper replication thông dụng:

```javascript
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
```

Helper này hiển thị thông tin liên quan đến oplog và sự chênh lệch của secondary theo phiên bản shell. Nếu command không được hỗ trợ trong môi trường cụ thể, có thể dựa vào `rs.status()`, command giám sát và metrics chính thức của deployment.

### 12.3. Oplog window và initial sync

Oplog là một capped collection lưu lịch sử thao tác đủ để secondary theo kịp primary nếu không bị chậm quá lâu. Nếu secondary mất kết nối dài và những thao tác nó thiếu đã bị cuốn khỏi oplog, việc tiếp tục đồng bộ theo phương thức thông thường có thể không còn khả thi; node có thể phải **initial sync lại** hoặc cần quy trình khôi phục phù hợp.

Vì vậy, theo dõi không chỉ khoảng trễ hiện tại mà còn **oplog window**, tải ghi, dung lượng, thời gian phục hồi và khả năng kết nối. Một secondary bị chậm rất xa không thể được chữa chỉ bằng cách tăng `priority`.

## 13. Cấu hình thành viên: `priority` và `votes`

### 13.1. `priority` điều khiển khả năng ưu tiên khi bầu cử

Trong cấu hình ban đầu:

```javascript
members: [
  { _id: 0, host: "localhost:27117", priority: 2 },
  { _id: 1, host: "localhost:27118", priority: 1 },
  { _id: 2, host: "localhost:27119", priority: 1 }
]
```

Giá trị `priority` ảnh hưởng thành viên nào được ưu tiên làm primary. Một member có `priority: 0` **không được bầu làm primary**.

Đừng hiểu:

```text
priority = 2
```

là thành viên có **hai phiếu**. Priority và votes là **hai thuộc tính khác nhau**.

### 13.2. `votes` quyết định quyền biểu quyết

Thông thường:

```javascript
{ host: "mongo-b.example:27017", priority: 1, votes: 1 }
```

Member có `votes: 1` là một voting member. Nếu `votes: 0`, thành viên đó không tham gia biểu quyết theo cơ chế thông thường, và phải có `priority: 0`.

MongoDB giới hạn **tối đa bảy voting members** trong một replica set; cấu hình có thể có nhiều thành viên hơn nhưng không phải tất cả đều có quyền bỏ phiếu. Không sử dụng `votes: 2` để “tăng phiếu” cho một node: phiếu của thành viên là 0 hoặc 1 theo cấu hình.

### 13.3. Quy tắc kết hợp cần nhớ

| Cấu hình | Có thể được bầu PRIMARY? | Có phiếu bầu? |
|---|---|---|
| `priority: 1, votes: 1` | Có, nếu đủ điều kiện | Có |
| `priority: 2, votes: 1` | Có; có ưu tiên cao hơn | Có |
| `priority: 0, votes: 1` | Không | Có |
| `priority: 0, votes: 0` | Không | Không |
| `priority: 1, votes: 0` | Cấu hình không hợp lệ theo ràng buộc thông thường | Không |

**Chỉ số priority không quyết định phần trăm dữ liệu đã đồng bộ.** Một member có priority cao nhưng không đủ điều kiện hoặc không theo kịp vẫn có thể không được bầu.

### 13.4. Tác động của thay đổi priority

Thay đổi priority có thể gây một cuộc bầu cử mới hoặc chuyển primary khi điều kiện cho phép. Vì vậy, ngay cả thao tác trông giống “chỉ sửa metadata” cũng có thể gây **gián đoạn ghi tạm thời**.

Không chỉnh priority hàng loạt trong giờ cao điểm nếu chưa đánh giá majority, replication lag và ảnh hưởng tới kết nối driver.

## 14. `rs.add()` và `rs.addArb()`: thêm thành viên

### 14.1. Thêm một secondary mới

Giả sử set hiện đã khởi tạo với **hai** data-bearing members A và B, và bạn vừa chạy một `mongod` mới C với cùng replica set name trên cổng 27119. Có thể kết nối tới primary rồi chạy:

```javascript
rs.add({
  host: "localhost:27119",
  priority: 0,
  votes: 0
});
```

**Đây là kịch bản riêng** với `rs.initiate()` ba node ở phần 5; nếu đã thêm C ngay trong `rs.initiate()` thì **không chạy `rs.add()` lần nữa cho C**.

Ví dụ mới đặt `priority: 0, votes: 0` để node có thể initial sync trước khi người quản trị đánh giá có nên cho nó tham gia bầu cử. Sau khi node ổn định, có thể cân nhắc cập nhật `votes`/`priority` theo topology mong muốn.

Nếu node mới đang đồng bộ dữ liệu lớn, trạng thái có thể đi từ `STARTUP2` đến `SECONDARY`. Kiểm tra `rs.status()` và tốc độ initial sync, không giả định nó có đầy đủ dữ liệu ngay sau `rs.add()`.

### 14.2. Thêm bằng hostname đơn giản

Với cấu hình mặc định phù hợp, MongoDB cũng cho phép:

```javascript
rs.add("mongo-d.internal.example:27017");
```

Địa chỉ này chỉ là ví dụ. Member mới phải là tiến trình `mongod` được chuẩn bị trước và có thể kết nối từ các thành viên khác; `rs.add()` **không tự cài đặt hoặc khởi động một máy MongoDB mới**.

### 14.3. Arbiter là gì?

Một **arbiter** có quyền tham gia **bầu cử** nhưng **không lưu dữ liệu ứng dụng như primary/secondary**:

```text
  A — PRIMARY          B — SECONDARY
      (data)               (data)
         \                  /
          \                /
            C — ARBITER
             (vote only)
```

Helper:

```javascript
rs.addArb("mongo-arb.internal.example:27017");
```

Arbiter có thể hỗ trợ đạt đa số phiếu trong một số tình huống tài nguyên hạn chế, nhưng **không tạo thêm bản sao dữ liệu** và không thể được bầu primary. Một topology 2 data-bearing + 1 arbiter (PSA) có những đánh đổi quan trọng về write concern majority và độ bền ghi khi một node dữ liệu không sẵn sàng. Với hệ thống cần độ sẵn sàng và độ bền ghi cao, **ba data-bearing members** thường là lựa chọn tốt hơn.

Không sử dụng arbiter như giải pháp mặc định cho mọi bài toán high availability hoặc để che giấu vấn đề mạng.

### 14.4. Hidden secondary

Một hidden secondary:

- Lưu dữ liệu như secondary.
- Không được bầu primary, nên cần `priority: 0`.
- Không được quảng bá như một thành viên đọc thông thường trong topology discovery theo cơ chế của replica set.
- Có thể hữu ích cho các workload đặc thù như backup/reporting tùy kiến trúc và cách kết nối trực tiếp.

Ví dụ cấu hình một member chuyên dụng:

```javascript
{
  _id: 3,
  host: "mongo-hidden.internal.example:27017",
  priority: 0,
  hidden: true,
  votes: 0
}
```

Không sửa ví dụ này trực tiếp vào cấu hình lab đang chạy nếu chưa tạo node thực. Nếu hidden member được chọn làm đích đọc trực tiếp cho tác vụ đặc thù, phải hiểu read preference và khả năng ảnh hưởng đến tính mới của dữ liệu.

### 14.5. Delayed secondary

Một secondary có thể được cấu hình **trì hoãn áp dụng oplog** bằng `secondaryDelaySecs` ở những phiên bản hỗ trợ. Nó có thể hữu ích để có thêm một cửa sổ chống lại một số lỗi thao tác, nhưng **không thay thế backup** và cũng không tự giúp khôi phục mọi lỗi dữ liệu.

Ví dụ ý tưởng cấu hình:

```javascript
{
  _id: 4,
  host: "mongo-delayed.internal.example:27017",
  priority: 0,
  hidden: true,
  secondaryDelaySecs: 3600,
  votes: 0
}
```

Trường `secondaryDelaySecs` và các quy tắc tương ứng phụ thuộc phiên bản MongoDB. Cần kiểm tra oplog window, dung lượng, tính phù hợp của một node có chủ đích chậm và ảnh hưởng tới write concern khi chọn votes.

## 15. `rs.reconfig()`: thay đổi cấu hình replica set

### 15.1. Vì sao cần reconfiguration?

Sau khi replica set chạy, có thể cần:

- Điều chỉnh `priority` của một member.
- Thêm/bớt vai trò bỏ phiếu, ẩn secondary hoặc thay đổi thiết lập thành viên.
- Thay hostname khi di chuyển hạ tầng.
- Điều chỉnh thiết lập replica set theo kế hoạch vận hành.

`rs.reconfig()` là lệnh mạnh vì **cấu hình thành viên liên quan trực tiếp tới bầu cử và khả năng ghi**. Chỉ dùng sau khi xác định cấu hình hiện tại và trạng thái majority.

### 15.2. Ví dụ thay đổi priority cho một thành viên

Kết nối tới primary rồi:

```javascript
const cfg = rs.conf();

const memberB = cfg.members.find(
  m => m.host === "localhost:27118"
);

if (!memberB) {
  throw new Error("Khong tim thay member B trong rs.conf()");
}

memberB.priority = 0;

rs.reconfig(cfg);
```

Sau đó:

```javascript
rs.conf().members.map(m => ({
  host: m.host,
  priority: m.priority,
  votes: m.votes
}));

rs.status().members.map(m => ({
  host: m.name,
  state: m.stateStr,
  health: m.health
}));
```

Khi `priority: 0`, member B không thể được bầu primary, nhưng vẫn có thể là một secondary đồng bộ dữ liệu và bỏ phiếu nếu `votes: 1`.

Ví dụ này minh họa kỹ thuật và **chỉ chạy trên lab**, vì thay đổi khả năng bầu cử của node production phải được lập kế hoạch.

### 15.3. `rs.reconfig()` có thể gây election

Một reconfiguration có thể làm primary hiện tại phải step down hoặc gây bầu cử mới, tùy thay đổi. Driver cần thời gian để nhận topology mới và gửi ghi tới primary mới.

Khi triển khai production:

1. Quan sát `rs.status()` và replication lag.
2. Xác định đủ majority còn hoạt động sau thay đổi.
3. Ghi lại cấu hình trước khi thay.
4. Thay ít thành viên voting mỗi lần theo ràng buộc của MongoDB version.
5. Theo dõi trạng thái sau reconfiguration và bảo đảm application failover hoạt động.

Không dùng `rs.reconfig(cfg, { force: true })` như cách “ép cluster khỏe” khi đang mất đa số. **Force reconfig** có rủi ro phân nhánh lịch sử, rollback hoặc mất ghi chưa được bảo đảm; chỉ xem xét trong quy trình disaster recovery có đánh giá kỹ.

### 15.4. Xóa thành viên bằng `rs.remove()`

Ví dụ cú pháp:

```javascript
rs.remove("localhost:27119");
```

Lệnh trên thay đổi thành viên của replica set. **Không dùng nó như giải pháp cho một secondary tạm thời DOWN.** Nếu cần bảo trì hoặc thay thế node:

- Xác định node có còn trong majority hay không.
- Tính lại số voting members và đa số phiếu sau thay đổi.
- Cân nhắc an toàn dữ liệu và điều kiện election.
- Chỉ xóa khi đó thực sự là thay đổi topology mong muốn.

Một node bị remove không tự mất dữ liệu trên đĩa; việc dọn data directory là hành động riêng, có thể phá hủy dữ liệu và không nằm trong thao tác quản lý cấu hình thông thường.

## 16. Kết nối ứng dụng bằng replica set URI

Một sai lầm vận hành thường gặp là cấu hình ứng dụng chỉ kết nối tới **một địa chỉ node cố định**:

```text
mongodb://mongo-a.internal.example:27017
```

Khi primary chuyển sang node khác, ứng dụng cần driver có khả năng **phát hiện topology và định tuyến thao tác**. Một URI replica set minh họa:

```text
mongodb://mongo-a.internal.example:27017,mongo-b.internal.example:27017,mongo-c.internal.example:27017/?replicaSet=rsProduction
```

Trong lab:

```text
mongodb://localhost:27117,localhost:27118,localhost:27119/?replicaSet=rsLab
```

Trong URI này:

- Danh sách host là **seed list** giúp driver tìm replica set, không phải cố định “host đầu tiên luôn primary”.
- `replicaSet=rsLab` chỉ định tên set mong đợi.
- Driver xác thực topology và khám phá các member từ server.
- Các host do server công bố phải phân giải được từ **máy ứng dụng**.

Đối với production, URI còn cần credential, cơ chế xác thực, TLS và các thiết lập timeout/read preference phù hợp. Tránh chèn mật khẩu trực tiếp vào source code hoặc log.

### 16.1. Ví dụ Java Sync Driver

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public class ReplicaSetReadExample {
    public static void main(String[] args) {
        String uri =
            "mongodb://localhost:27117,localhost:27118,localhost:27119/" +
            "?replicaSet=rsLab";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> sample = client
                .getDatabase("rsLesson")
                .getCollection("events");

            sample.insertOne(new Document("type", "APP_STARTED"));
            System.out.println(sample.countDocuments());
        }
    }
}
```

Ví dụ trên dành cho lab chưa bật authentication. Trong môi trường thật, tạo user và quyền phù hợp, dùng secret manager và bảo vệ kết nối. Driver tự quản lý selection/retry theo những khả năng được hỗ trợ, nhưng ứng dụng vẫn phải xử lý ngoại lệ khi không có primary hoặc write concern không đạt.

### 16.2. Có thể đọc từ secondary không?

MongoDB hỗ trợ read preference như `primary` (thường là mặc định) và các lựa chọn đọc secondary khi phù hợp. Nhưng:

- Secondary có thể lag, nên dữ liệu chưa chắc mới nhất.
- Không nên dùng đọc secondary để đảm bảo “vừa ghi xong lập tức đọc thấy” nếu không thiết kế causal consistency và chính sách đọc phù hợp.
- Một read preference khác không biến secondary thành writable primary.
- Đọc từ secondary có thể giảm một phần tải primary nhưng cũng làm secondary phục vụ replication chậm hơn nếu quá tải.

Chọn read preference theo yêu cầu nhất quán và latency, không phải chỉ để “chia đều số request”.

## 17. Write concern, majority và độ bền

**Bầu cử primary** và **xác nhận một ghi đã được sao chép** là hai vấn đề khác nhau.

### 17.1. Khái niệm `w: "majority"`

Khi ứng dụng yêu cầu write concern majority, lệnh ghi cần được xác nhận theo tiêu chí đa số phù hợp của replica set. Đây là một phần quan trọng để giảm rủi ro dữ liệu được xác nhận rồi bị rollback khi chuyển primary, theo những bảo đảm của MongoDB.

Ví dụ trong `mongosh`:

```javascript
db.getSiblingDB("rsLesson").events.insertOne(
  { type: "PAYMENT_CONFIRMED", createdAt: new Date() },
  { writeConcern: { w: "majority", wtimeout: 10000 } }
);
```

Đoạn mã trên chỉ minh họa cách yêu cầu majority write concern; không có nghĩa mọi thao tác như vậy sẽ thành công khi cluster thiếu phiếu hoặc secondary không theo kịp.

### 17.2. Majority votes không đồng nghĩa majority data-bearing members

Trong topology:

```text
P (data) + S (data) + A (arbiter)
```

Arbiter có thể bỏ phiếu bầu primary nhưng **không lưu thao tác ghi** như một data-bearing secondary. Điều này gây đánh đổi đáng kể khi thực hiện ghi cần majority trên cấu hình PSA, đặc biệt nếu một trong hai node dữ liệu không sẵn sàng.

Đừng kết luận “có hai trên ba node còn sống là mọi ghi majority đều an toàn và tiếp tục được”. Cần biết **node nào giữ dữ liệu**, quy tắc write concern, journaling, topology và sự cố đang xảy ra.

### 17.3. Khi primary dừng trước khi ghi được sao chép

Nếu một ghi chỉ được xác nhận ở primary mà chưa đạt mức độ bền/sao chép mà nghiệp vụ yêu cầu, sự kiện failover có thể dẫn tới tình huống ghi đó không hiện diện trên primary mới, và thành viên cũ có thể phải rollback một phần lịch sử của nó.

Vì thế, replica set **không thay thế** quyết định write concern thích hợp cho giao dịch quan trọng. Ngược lại, yêu cầu majority có thể tăng độ trễ và yêu cầu đủ thành viên để xác nhận; cần cân bằng với mục tiêu ứng dụng.

## 18. Bảo mật replica set: từ lab đến production

### 18.1. Vì sao lab chỉ bind localhost?

Các lệnh lab dùng:

```text
--bind_ip localhost
```

để không công khai cổng MongoDB ra mạng bên ngoài. Nếu dùng `--bind_ip_all` hoặc `0.0.0.0` khi chưa thiết lập authentication/firewall, database có thể bị truy cập trái phép từ những máy có thể kết nối đến cổng.

Không được copy lệnh mở mạng ra production chỉ vì muốn các thành viên liên lạc được.

### 18.2. Authentication nội bộ giữa các node

Các `mongod` trong replica set cần xác thực với nhau trong cấu hình production có bảo mật. Một lựa chọn phổ biến là **keyfile** được phân phối an toàn tới những node tham gia, với quyền file hạn chế theo yêu cầu nền tảng và cùng nội dung bí mật.

Ví dụ cấu hình ý tưởng:

```yaml
security:
  authorization: enabled
  keyFile: /secure/path/rs-keyfile

replication:
  replSetName: rsProduction
```

Đoạn YAML không phải hướng dẫn tạo credential, phân phối secret hoặc bootstrap user đầy đủ. Trong thực tế cần kế hoạch thiết lập user quản trị, quyền, rotation, tài khoản ứng dụng, TLS, firewall và secret storage. **Không ghi nội dung keyfile vào bài viết, git repository hoặc log**.

### 18.3. TLS và vùng tin cậy của mạng

Khi các node ở các máy/zone khác nhau, cần bảo vệ đường truyền theo chính sách bảo mật. TLS, hostname verification, certificate management và cấu hình định tuyến mạng là các yếu tố thiết yếu trong nhiều production deployment.

Không dùng việc replica set tự bầu cử làm bằng chứng rằng dữ liệu đã được mã hóa trên đường truyền hoặc chỉ người có quyền mới truy cập được database.

### 18.4. Backup vẫn cần thiết

Replica set sao chép **cả những thay đổi không mong muốn** (ví dụ xóa nhầm dữ liệu, cập nhật sai hàng loạt). Nó không phải backup có thể quay về một thời điểm tùy ý.

Kế hoạch production cần backup, khôi phục kiểm chứng được, lưu giữ bản sao ngoài sự cố hạ tầng, và chính sách phục hồi dữ liệu sau lỗi người dùng hoặc ứng dụng.

## 19. Chẩn đoán lỗi thường gặp khi `rs.initiate()` hoặc `rs.status()` không như mong đợi

### 19.1. Lỗi: server chưa chạy với `--replSet`

Nếu khởi động `mongod` bình thường rồi gọi `rs.initiate()` hoặc `rs.status()`, server có thể báo không chạy trong replication mode.

Kiểm tra:

- Startup option có `--replSet rsLab` không?
- File cấu hình có `replication.replSetName: rsLab` không?
- Bạn đang kết nối đúng port của node replica set hay nhầm một standalone `mongod` khác?

Giải pháp là **khởi động tiến trình với cấu hình replication đúng**, không gọi `rs.initiate()` liên tục để “thử lại”.

### 19.2. Lỗi: replica set name không khớp

`--replSet rsLab` nhưng `rs.initiate({ _id: "wrongName", ... })` có thể gây lỗi hoặc cấu hình không được chấp nhận.

Đảm bảo tên set ở startup, `rs.initiate()` và URI của client thống nhất. Nếu đã có dữ liệu/cấu hình cũ trên dbPath, cần xác định lịch sử node trước khi đổi; **không xóa data directory để chữa lỗi trên production**.

### 19.3. Lỗi: thành viên không thể kết nối nhau

Trong `rs.status()`, có thể thấy:

```javascript
{
  name: "mongo-b.internal.example:27017",
  health: 0,
  stateStr: "DOWN",
  lastHeartbeatMessage: "..."
}
```

Những nguyên nhân thường gặp:

- Hostname không phân giải từ một hoặc nhiều node.
- Port không lắng nghe, bị firewall chặn hoặc tiến trình `mongod` chưa chạy.
- `bindIp` không cho phép kết nối từ thành viên khác.
- Cấu hình keyfile/TLS/xác thực nội bộ không khớp.
- Mạng giữa các vùng có vấn đề, latency quá cao.
- Node bị quá tải hoặc đang khởi động lâu.

Không vội `rs.remove()` chỉ để làm dấu DOWN biến mất khỏi màn hình. Trước tiên kiểm tra connectivity và log.

### 19.4. Lỗi: không có PRIMARY

Ví dụ chỉ còn một node có phiếu trong set ba voting members:

```text
A (DOWN)    B (SECONDARY)    C (DOWN)
```

Node B có thể khỏe nhưng **không đủ majority** để tự bầu primary. Trong trạng thái này, các lệnh ghi thông thường sẽ không thành công.

Những việc cần làm:

1. Xác định node nào còn sống và có phiếu.
2. Kiểm tra mạng để xem các node còn kết nối với nhau không.
3. Khôi phục các node hoặc đường kết nối để có đa số khi có thể.
4. Đọc log bầu cử và `rs.status()`.
5. Tránh dùng force reconfig hoặc khởi tạo replica set mới trên dữ liệu cũ khi chưa có quy trình disaster recovery.

**Một secondary khỏe không thể tự ý trở thành primary nếu thiếu điều kiện bầu cử.**

### 19.5. Lỗi: bầu cử lặp đi lặp lại

Nếu primary liên tục chuyển giữa các node, xem:

- Mạng giữa các voting members có ổn định không?
- CPU/đĩa quá tải khiến heartbeat trễ không?
- Đồng hồ hệ thống có được đồng bộ không?
- Priority và votes có tạo kỳ vọng không phù hợp?
- Có automation hoặc quản trị viên chạy reconfiguration/stepDown liên tục không?
- Có các sự kiện failover của hạ tầng, cloud hoặc container scheduler không?

Đừng tăng priority của một node lên giá trị rất cao như biện pháp thay thế cho việc chữa mạng hoặc storage.

### 19.6. Lỗi: secondary ở STARTUP2/RECOVERING lâu

Tìm hiểu:

- Initial sync đang chạy và đã tiến triển tới đâu?
- Oplog window của sync source có đủ?
- Lượng dữ liệu có lớn vượt khả năng đồng bộ trong thời gian dự kiến?
- Ổ đĩa có đủ dung lượng và tốc độ?
- Quyền, bảo mật hoặc mạng có chặn quá trình replication?
- Có lỗi cụ thể trong log không?

**Không tự xóa dữ liệu secondary hoặc re-seed bừa bãi** chỉ vì `rs.status()` chưa hiện SECONDARY.

### 19.7. Lỗi: ứng dụng chỉ kết nối một host và không failover

Nếu URI dùng `directConnection=true` tới một node secondary cũ, driver có thể không khám phá primary như mong muốn. Với ứng dụng cần failover, dùng **replica set URI** chứa seed list và `replicaSet`, bảo đảm hostname được quảng bá phân giải được từ ứng dụng.

Đừng dùng các URI gắn `localhost` trong container/máy từ xa nếu server và client không ở cùng network namespace.

## 20. Quy trình vận hành an toàn khi thêm/bớt/thay member

Một kế hoạch thay đổi replica set production cần chú ý:

### Bước 1 — Ghi lại cấu hình và trạng thái

```javascript
rs.conf();
rs.status();
db.adminCommand({ hello: 1 });
```

Ghi nhận tên set, danh sách member, priority/votes, primary hiện tại, trạng thái replication và đa số phiếu.

### Bước 2 — Xác định mục tiêu thay đổi

Ví dụ:

- Thêm secondary để tăng bản sao dữ liệu.
- Thay một server đã lỗi phần cứng.
- Di chuyển một thành viên sang availability zone khác.
- Tạo một hidden secondary cho workload riêng.
- Điều chỉnh priority sau khi đánh giá khả năng bầu cử.

**Không thay cấu hình chỉ vì một command có thể chạy được.**

### Bước 3 — Chuẩn bị server mới độc lập

Chuẩn bị dbPath, version tương thích, DNS, firewall, xác thực nội bộ, monitoring và dung lượng. Không cho server mới dùng chung dữ liệu với server cũ đang chạy.

### Bước 4 — Thay đổi ít thành viên và theo dõi

Sử dụng `rs.add()`, `rs.remove()` hoặc `rs.reconfig()` đúng trường hợp. Tránh những thay đổi voting members đồng thời không được hỗ trợ bởi version/cấu hình. Sau mỗi thay đổi:

```javascript
rs.conf();
rs.status();
```

Đợi member mới hoàn tất initial sync, replication lag ổn định và majority được giữ.

### Bước 5 — Kiểm chứng ứng dụng

Xác nhận driver:

- Nhìn thấy primary hiện tại.
- Có thể thực hiện thao tác đọc/ghi theo quyền và write concern.
- Có thể vượt qua failover có kiểm soát theo yêu cầu ứng dụng.
- Không phụ thuộc vào hostname/port của primary trước đó.

### Bước 6 — Chuẩn bị rollback và khôi phục

Lưu cấu hình và bằng chứng trạng thái trước/sau. Nếu thay đổi gây lỗi, quay lại theo **quy trình được kiểm soát**, không chạy lệnh force hoặc xóa data directory để rút ngắn sự cố.

## 21. Các anti-pattern trong quản trị replica set

| Anti-pattern | Vì sao nguy hiểm | Cách nghĩ đúng |
|---|---|---|
| Gọi `rs.initiate()` trên từng node | Khởi tạo độc lập làm sai cấu hình tập | Khởi tạo set một lần, các node dùng chung config |
| Dùng chung `dbPath` cho nhiều `mongod` | Tranh chấp/khả năng hỏng dữ liệu | Mỗi tiến trình một dbPath riêng |
| Quảng bá `localhost` ở production nhiều máy | Node/client từ xa hiểu localhost khác nhau | Dùng hostname phân giải được toàn topology |
| Mở `0.0.0.0` không bảo mật | Làm lộ dữ liệu qua mạng | Thiết lập authentication, firewall, TLS phù hợp |
| Coi node có priority cao luôn là primary | Election còn phụ thuộc tình trạng node/đa số | Đọc role thực tế bằng `hello`/`rs.status()` |
| Coi `votes: 1` nghĩa đang chứa dữ liệu | Arbiter cũng có phiếu nhưng không lưu dữ liệu | Phân biệt voting và data-bearing |
| Coi `health: 1` là đã đồng bộ đến primary | Health chủ yếu liên quan khả năng thấy node | Theo dõi optime/lag và trạng thái |
| Thấy `ok: 1` thì kết luận cluster khỏe | Command thành công vẫn có thể báo node DOWN | Kiểm tra từng member và primary/quorum |
| Xóa member ngay khi DOWN | Có thể làm thay đổi majority và failover sai | Điều tra mạng/tiến trình trước |
| Dùng `force: true` để chữa mọi lỗi cấu hình | Có rủi ro mất ghi hoặc phân nhánh lịch sử | Chỉ dùng trong disaster recovery được lập kế hoạch |
| Thêm arbiter và nghĩ có thêm bản sao dữ liệu | Arbiter không lưu tập dữ liệu ứng dụng | Ưu tiên data-bearing khi cần redundancy |
| Đọc secondary và giả định mới như primary | Replication bất đồng bộ, có lag | Chọn read preference/consistency theo nhu cầu |
| Coi replica set là backup | Xóa nhầm cũng được replicate | Có backup/restore độc lập |
| Truy cập ứng dụng bằng một host direct cố định | Không tự khám phá primary mới | Sử dụng replica set URI |
| Chỉ đo lag bằng thời gian hiện tại - optime | Có thể cảnh báo giả khi không có ghi | Kết hợp optime, nguồn ghi và metrics |
| Chỉnh priority giữa sự cố chưa rõ nguyên nhân | Có thể tạo election gián đoạn tiếp | Phân tích majority, log, mạng và storage |

## 22. Bài tập thực hành

### Bài 1 — Khởi tạo ba node cục bộ

Tạo ba thư mục dữ liệu riêng và chạy `mongod` tại các port 27117, 27118, 27119 cùng `--replSet rsLab`. Sau đó:

1. Kết nối node A bằng `mongosh`.
2. Gọi `rs.initiate()` với ba member.
3. Đọc `rs.status()` tới khi có PRIMARY và các secondary sẵn sàng.
4. Ghi lại tên node đang PRIMARY, member ID và giá trị health.
5. Chạy `rs.conf()` để xác nhận số lượng member và priority.

Giải thích vì sao ba node trên một máy giúp học thao tác nhưng không có khả năng chịu lỗi một máy vật lý.

### Bài 2 — Phân biệt `rs.conf()` và `rs.status()`

Giả sử `rs.conf()` ghi:

```javascript
[
  { _id: 0, host: "A:27017", priority: 2, votes: 1 },
  { _id: 1, host: "B:27017", priority: 1, votes: 1 },
  { _id: 2, host: "C:27017", priority: 1, votes: 1 }
]
```

Nhưng `rs.status()` tại A ghi B là `DOWN`. Hãy trả lời:

- B có còn là thành viên trong cấu hình không?
- Vì sao B chưa chắc đã bị remove?
- Những loại lỗi nào có thể làm B không được thấy?
- Có nên gọi `rs.remove("B:27017")` ngay không?

### Bài 3 — Tính majority

Với ba voting members, hãy tính số phiếu cần để elect primary khi:

1. Cả ba hoạt động.
2. Một node bị mất.
3. Hai node bị mất.

Sau đó so sánh với set năm voting members. Tại sao một replica set gồm hai voting members thường có tính sẵn sàng kém hơn ba voting members khi một node lỗi?

### Bài 4 — `priority` khác `votes`

Phân tích bốn cấu hình:

```javascript
{ priority: 2, votes: 1 }
{ priority: 1, votes: 1 }
{ priority: 0, votes: 1 }
{ priority: 0, votes: 0 }
```

Member nào có khả năng được bầu primary? Member nào vẫn được bỏ phiếu dù không thể là primary? Vì sao không thể suy `priority: 2` là hai phiếu?

### Bài 5 — Dừng một secondary trong lab

Trên lab **ba node cùng máy**, chỉ dừng terminal đang chạy node C tại port 27119 (không xóa dữ liệu). Sau đó quan sát:

```javascript
rs.status();
```

Hãy ghi nhận:

- Member C chuyển sang trạng thái gì theo quan sát sau heartbeat?
- Primary có còn phục vụ ghi khi hai voting members khác đang hoạt động?
- Khi khởi động lại C với cùng dbPath và replSetName, trạng thái thay đổi ra sao?
- Vì sao có thể phải chờ replication catch-up?

Chỉ thực hiện trên lab. Không tắt node production khi chưa có kế hoạch chịu lỗi.

### Bài 6 — Giả lập mất đa số

**Không cần thật sự dừng hai node** nếu không muốn gián đoạn lab. Từ mô hình ba voting members, phân tích tình huống A và C DOWN, chỉ còn B.

- B có thể tự bầu primary không?
- Driver thao tác ghi sẽ gặp vấn đề gì?
- Vì sao một secondary vẫn có thể khỏe cục bộ nhưng không đủ điều kiện bầu cử?
- Nên ưu tiên khôi phục đường mạng/node hay dùng `force`?

### Bài 7 — Đọc các trường trong `rs.status()`

Viết đoạn mongosh để in các trường:

```javascript
{
  host: "...",
  health: 1,
  state: "SECONDARY",
  optimeDate: ISODate("..."),
  syncSourceHost: "..."
}
```

từ `rs.status().members`. Giải thích trường nào nói về khả năng liên lạc, trường nào nói về role, trường nào giúp xem tiến độ replication. Có thể khẳng định secondary không lag chỉ vì `health: 1` không?

### Bài 8 — Thiết kế URI cho ứng dụng

Cho set production:

```text
rsShop
mongo-a.internal.example:27017
mongo-b.internal.example:27017
mongo-c.internal.example:27017
```

Viết URI để driver khám phá cả ba member. Giải thích:

- Tác dụng của `replicaSet=rsShop`.
- Vì sao host đầu tiên không nhất thiết là primary.
- Vì sao không nên dùng `localhost` khi client ở máy khác.
- Những thông tin bảo mật nào cần được cấu hình ngoài URI demo.

### Bài 9 — Thêm secondary và kiểm tra initial sync

Giả sử một set đã có A và B, cần thêm C:

1. Chuẩn bị tiến trình C với dbPath riêng và cùng replSetName.
2. Gọi `rs.add()` từ primary.
3. Quan sát các trạng thái C có thể đi qua trước `SECONDARY`.
4. Khi nào mới cân nhắc tăng `votes` hoặc `priority`?
5. Vì sao cần kiểm tra oplog window, dung lượng và tốc độ đồng bộ?

### Bài 10 — So sánh PSS và PSA

Hai topology:

```text
PSS = Primary + Secondary + Secondary
PSA = Primary + Secondary + Arbiter
```

Hãy phân tích:

- Mỗi topology có bao nhiêu data-bearing members?
- Mỗi topology có thể có bao nhiêu voting members?
- Nếu secondary dữ liệu bị mất, khả năng xác nhận ghi majority có thể khác ra sao?
- Vì sao arbiter không được dùng để thay thế một bản sao dữ liệu?

### Bài 11 — Thay đổi cấu hình có thể làm mất tính sẵn sàng

Một người quản trị muốn đưa hai trong ba thành viên xuống `votes: 0` trong cùng một thao tác. Hãy giải thích vì sao nên tính lại voting majority và tuân thủ giới hạn reconfiguration trước khi sửa. Đề xuất quy trình chuẩn bị, sao lưu cấu hình, thay đổi từng bước, theo dõi và kiểm tra ứng dụng.

### Bài 12 — Chẩn đoán kết nối lỗi

Giả sử:

```text
MongoDB Node A: mongo-a.internal.example:27017
MongoDB Node B: mongo-b.internal.example:27017
MongoDB Node C: mongo-c.internal.example:27017
Application chạy trên một container khác.
```

Application kết nối seed A thành công nhưng sau đó bị lỗi khi driver cố kết nối B và C. Hãy liệt kê các khả năng:

- Hostname B/C không phân giải từ container.
- Firewall/network policy không cho kết nối port.
- Server quảng bá tên hostname không phù hợp.
- Cấu hình TLS, auth hoặc replicaSetName không khớp.

Giải thích vì sao đây có thể là lỗi **topology discovery** chứ không phải MongoDB đã mất dữ liệu.

## 23. Tổng kết

**Replica set là nhóm `mongod` cùng quản lý bản sao dữ liệu và tham gia bầu primary.** Một topology phổ biến có ba data-bearing members; để bầu và duy trì primary, các voting members phải có đủ đa số phiếu. Replication là bất đồng bộ, nên không được nhầm khả năng liên lạc với việc đã sao chép mọi ghi.

**Khởi tạo đúng bắt đầu từ từng node:** cùng `replSetName`, mỗi node một dbPath riêng, host/port có thể kết nối lẫn nhau và bảo mật phù hợp. Sau đó gọi `rs.initiate()` **một lần**, đợi bầu cử và theo dõi các trạng thái chuyển tiếp thay vì giả định primary xuất hiện ngay.

**`rs.conf()` là cấu hình, `rs.status()` là thực trạng.** Dùng `rs.conf()` để xem thành viên/priority/votes; dùng `rs.status()` để xem PRIMARY/SECONDARY, health, heartbeat và tiến độ replication; dùng `db.adminCommand({ hello: 1 })` để nhận biết role của node đang kết nối.

**Thay đổi thành viên là thay đổi khả năng sẵn sàng.** `rs.add()`, `rs.addArb()`, `rs.remove()` và `rs.reconfig()` có thể làm thay đổi bầu cử, đa số phiếu và tính an toàn của dữ liệu. Không force reconfig, xóa thành viên hoặc xóa data directory như phản xạ đầu tiên khi một node bị DOWN.

**Một replica set tin cậy cần nhiều hơn các lệnh đúng cú pháp:** hostname/DNS ổn định, xác thực nội bộ, mạng an toàn, write concern phù hợp, monitoring replication lag, backup và quy trình failover/khôi phục rõ ràng. Khi hiểu được ba trụ cột **khởi tạo — cấu hình — kiểm tra trạng thái**, bạn có thể vận hành replica set với các quyết định dựa trên trạng thái thực tế thay vì dựa vào tên máy hoặc kỳ vọng cố định.
