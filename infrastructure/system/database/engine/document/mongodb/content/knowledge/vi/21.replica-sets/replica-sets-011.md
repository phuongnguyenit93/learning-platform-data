# Lựa chọn secondary theo tag và mục đích phân tải đọc trong MongoDB Replica Set

Trong một hệ thống bán hàng, primary của MongoDB Replica Set phải xử lý ghi đơn hàng, cập nhật tồn kho và nhiều truy vấn quan trọng. Nếu dashboard nội bộ liên tục quét dữ liệu để lập báo cáo, primary có thể phải chia CPU, RAM, I/O cho công việc đọc nặng. Replica Set có các secondary lưu bản sao dữ liệu, vì vậy ứng dụng có thể **chủ động gửi một số truy vấn đọc đến secondary** để giảm tải cho primary.

Nhưng “đọc từ secondary” chưa phải thiết kế đầy đủ. Khi có nhiều secondary, ta cần trả lời:

- Secondary nào được phép chạy báo cáo, secondary nào dành cho API đọc thông thường?
- Muốn ưu tiên một vùng/zone nhưng có thể rơi về vùng khác thì cấu hình ra sao?
- Nếu mọi secondary dành cho báo cáo đều không sẵn sàng, hệ thống nên **báo lỗi** hay **quay lại primary**?
- Làm sao tránh đọc dữ liệu quá trễ so với primary?
- Có thể dùng tag để chọn một secondary mà không làm thay đổi quyền ghi, bầu chọn hay độ nhất quán không?

MongoDB cung cấp hai công cụ chính: **member tags** gắn vào cấu hình replica set và **read preference với tag sets** ở phía client. Kết hợp chúng, bạn có thể mô tả mục đích của từng secondary và yêu cầu driver lựa chọn **nhóm member đủ điều kiện**, thay vì chọn một host cụ thể bằng tay. Tuy nhiên, tags không phải hệ thống cân bằng tải cứng, không bảo đảm đọc dữ liệu mới nhất và không phải hàng rào bảo mật.

Bài thuộc chương **Replica set** của module *Database Engine Document MongoDB*. Ví dụ dùng **mongosh**, MongoDB Java Driver và Node.js Driver. Một số hành vi fallback, staleness, latency window và routing phụ thuộc phiên bản driver/server, read preference mode và topology; khi triển khai cần kiểm tra trên môi trường mục tiêu. Các lệnh thay cấu hình replica set chỉ là ví dụ cho **lab**, không thực hiện tùy tiện trên production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò primary, secondary và sự trễ đồng bộ trong replica set.
2. Gắn **tags** cho các member và đọc cấu hình bằng `rs.conf()`.
3. Phân biệt năm chế độ `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred` và `nearest`.
4. Sử dụng **read preference tag sets** có thứ tự để ưu tiên nhóm secondary theo mục đích/vùng.
5. Phân biệt **fallback sang secondary khác** với **fallback sang primary**.
6. Biết khi nào cần `maxStalenessSeconds` và vì sao nó không phải cam kết dữ liệu luôn mới trong N giây.
7. Hiểu **latency window** và tại sao `nearest` không bảo đảm đọc từ secondary.
8. Tạo read preference ở cấp connection, database/collection hoặc từng operation trong Java/Node.js Driver.
9. Phân biệt read preference với **read concern**, causal consistency, write concern và authorization.
10. Lập kế hoạch phân tải đọc, giám sát replication lag, lỗi chọn server và tải CPU/I/O.
11. Nhận biết giới hạn với hidden/delayed members, transaction, sharding và failover.
12. Thiết kế bài kiểm thử để xác nhận query thực sự chạy trên nhóm node mong muốn.

## 2. Replica Set: tại sao có thể đọc ở secondary?

Một replica set có nhiều `mongod` duy trì cùng tập dữ liệu bằng cơ chế replication. Trong topology thông thường:

- **Primary** nhận các thao tác ghi của replica set và phục vụ truy vấn đọc mặc định.
- **Secondary** sao chép và áp dụng các thao tác từ oplog để đồng bộ theo thời gian.
- **Election** có thể chọn primary mới khi primary hiện tại không sẵn sàng, tùy cấu hình majority, priority và trạng thái member.

~~~mermaid
flowchart TD
    App["Ứng dụng"] --> W["Ghi"]
    App --> R["Đọc"]
    W --> P["Primary"]
    P --> O["Oplog / replication"]
    O --> S1["Secondary API"]
    O --> S2["Secondary báo cáo"]
    R --> Q{"Read preference + tags"}
    Q -->|"Các ứng viên đủ điều kiện"| S1
    Q -->|"Các ứng viên đủ điều kiện"| S2
~~~

Điểm cốt lõi: **replication bất đồng bộ**. Một lệnh ghi thành công ở primary có thể chưa xuất hiện ngay trên secondary. Vì vậy:

~~~text
Tại thời điểm T:
Primary:   order-1001 đã có
Secondary: order-1001 có thể chưa được áp dụng
~~~

Nếu ngay sau khi tạo order, API đọc bằng read preference `secondary`, nó có thể chưa thấy order mới. Điều này không nhất thiết là lỗi query hay mất dữ liệu; đó có thể là **replication lag**.

### 2.1. Secondary không phải node “đọc miễn phí”

Secondary phải:

- Nhận và áp dụng thay đổi từ primary.
- Duy trì index và dữ liệu riêng.
- Dùng CPU, RAM/cache, disk và network.
- Có thể tham gia bầu chọn tùy cấu hình.

Nếu gửi hàng nghìn báo cáo nặng tới secondary, chính secondary đó có thể bị quá tải, tăng replication lag và ảnh hưởng khả năng phục hồi/failover. **Phân tải đọc là chuyển và phân phối chi phí, không xóa chi phí.**

### 2.2. Đọc phân tải khác mở rộng khả năng ghi

Gửi một truy vấn đọc từ primary sang secondary có thể giảm tải đọc ở primary. Nhưng write operation vẫn đi theo cơ chế ghi của replica set (thông thường tới primary). Thêm secondary **không tự làm write throughput tăng tuyến tính**, vì tất cả member phải duy trì dữ liệu và còn phát sinh chi phí replication.

## 3. Member tags: mô tả thuộc tính từng node

MongoDB cho phép cấu hình một tập các cặp `key: value` dạng string trên từng replica set member. Ví dụ:

~~~javascript
{
  host: "mongo-report-1.example.internal:27017",
  tags: {
    purpose: "reporting",
    region: "hcm",
    zone: "az-b"
  }
}
~~~

Các tag có thể mô tả:

| Tag | Giá trị minh họa | Ý nghĩa được đội vận hành quy ước |
|---|---|---|
| `purpose` | `app`, `reporting` | Dùng cho đọc API hay báo cáo |
| `region` | `hcm`, `hanoi` | Nhóm vị trí địa lý của node |
| `zone` | `az-a`, `az-b` | Availability zone |
| `tier` | `interactive`, `batch` | Phân loại mức tải phù hợp |
| `hardware` | `large-memory` | Mô tả cấu hình máy |

MongoDB không tự hiểu rằng `purpose: "reporting"` có nghĩa “chỉ báo cáo được dùng”. Đây là **quy ước của ứng dụng/vận hành**. Driver chỉ kiểm tra các tag theo read preference mà bạn cung cấp.

### 3.1. Tag không phải hostname và không phải quyền truy cập

Khi một node mang `purpose: "reporting"`:

- Driver có thể chọn node này nếu read preference/tag set phù hợp.
- Node **không tự chặn** client khác đọc nếu client có quyền và lựa chọn read preference khác.
- Tag không giới hạn số kết nối, CPU hay I/O.
- Tag không mã hóa hoặc phân quyền dữ liệu theo tenant.
- Tag không làm node thành secondary; vai trò primary/secondary do replica set/election quyết định.

**Tag là metadata cho lựa chọn server, không phải policy isolation.** Muốn cô lập thật, cần kiến trúc truy cập, credentials, network controls và quản lý workload bổ sung.

### 3.2. Tên key/value phải nhất quán

Những giá trị:

~~~text
purpose=reporting
purpose=Reporting
purpose=reports
~~~

không nên được coi là cùng một quy ước. Driver match theo cặp tag cụ thể. Nhóm vận hành cần chuẩn hóa key/value, tài liệu hóa và kiểm tra drift khi thêm node.

## 4. Topology minh họa để thực hành

Giả sử có ba data-bearing members:

| Member | Vai trò tại thời điểm minh họa | Tags | Mục đích |
|---|---|---|---|
| `mongo-a:27017` | Primary | `{region:"hcm",zone:"az-a",purpose:"app"}` | Ghi và đọc cần dữ liệu mới |
| `mongo-b:27017` | Secondary | `{region:"hcm",zone:"az-b",purpose:"app"}` | API đọc chịu được lag |
| `mongo-c:27017` | Secondary | `{region:"hanoi",zone:"az-c",purpose:"reporting"}` | Báo cáo/batch |

Đây là **ảnh chụp trạng thái**, không phải vai trò bất biến: khi bầu chọn, một secondary có thể trở thành primary nếu đủ điều kiện. Tags là metadata gắn với member, **không tự chuyển theo vai trò**.

~~~mermaid
flowchart LR
    API["API quan trọng"] -->|"primary"| A["mongo-a Primary"]
    Reader["API đọc không gấp"] -->|"secondary + purpose=app"| B["mongo-b Secondary"]
    BI["Reporting job"] -->|"secondary + purpose=reporting"| C["mongo-c Secondary"]
    A -.->|"Replication"| B
    A -.->|"Replication"| C
~~~

### 4.1. Tại sao cần tính tới election?

Giả sử `mongo-c` được tag `purpose: "reporting"` nhưng vẫn có khả năng được bầu primary. Khi election thay đổi:

- Read preference `secondary` **không** chọn primary mới, dù tag vẫn khớp.
- Nếu không còn secondary có `purpose: "reporting"`, query reporting cấu hình strict có thể không tìm được server.
- Query dùng `nearest` và tag phù hợp có thể có quy tắc chọn khác vì mode này cho phép xét cả primary.

Để một node dành riêng cho workload đọc **không trở thành primary**, đội vận hành có thể xem xét `priority: 0` theo thiết kế replica set. Nhưng điều này ảnh hưởng electability, không phải điều kiện bắt buộc cho tag; mọi thay đổi priority/vote phải bảo toàn khả năng election và availability của topology.

## 5. Kiểm tra và cấu hình tags bằng mongosh

Để xem cấu hình replica set:

~~~javascript
rs.conf()
~~~

Bạn có thể tìm:

~~~javascript
{
  _id: "rs0",
  members: [
    {
      _id: 0,
      host: "mongo-a:27017",
      priority: 1,
      tags: { region: "hcm", zone: "az-a", purpose: "app" }
    },
    {
      _id: 1,
      host: "mongo-b:27017",
      priority: 1,
      tags: { region: "hcm", zone: "az-b", purpose: "app" }
    },
    {
      _id: 2,
      host: "mongo-c:27017",
      priority: 0,
      tags: { region: "hanoi", zone: "az-c", purpose: "reporting" }
    }
  ]
}
~~~

Kết quả minh họa lược bỏ các field cấu hình khác như version/votes/settings. Không sao chép đoạn cấu hình này rồi thay hoàn toàn `rs.conf()` bằng một object thiếu field.

### 5.1. Đổi tags trong lab

Trên primary của **replica set lab**, khi đủ quyền:

~~~javascript
const cfg = rs.conf()

// Tìm bằng host chính xác để tránh sửa nhầm member.
const member = cfg.members.find(
  m => m.host === "mongo-c:27017"
)

if (!member) {
  throw new Error("Không tìm thấy member trong cấu hình")
}

member.tags = {
  region: "hanoi",
  zone: "az-c",
  purpose: "reporting"
}

rs.reconfig(cfg)
~~~

Lưu ý trước khi áp dụng:

- `rs.reconfig()` là **thao tác vận hành thay đổi cấu hình**; ví dụ chỉ dành cho lab.
- Dùng đúng hostname/port của member thật, không phải chuỗi mẫu.
- Kiểm tra version/config, trạng thái PRIMARY, quyền và sức khỏe replica set.
- Không đồng thời sửa priority/votes hoặc thêm/bớt member khi mục tiêu chỉ là tags.
- Thay đổi cấu hình có thể ảnh hưởng server selection và trong một số trường hợp kéo theo thay đổi trạng thái/election; cần quy trình rollout/rollback production.

### 5.2. Xác nhận sau thay đổi

~~~javascript
const after = rs.conf()

after.members.forEach(m => {
  printjson({
    host: m.host,
    tags: m.tags,
    priority: m.priority,
    hidden: m.hidden
  })
})

rs.status()
~~~

`rs.conf()` xác nhận **metadata cấu hình**, còn `rs.status()` giúp quan sát trạng thái thành viên/replication. Không có nghĩa một query đã được gửi tới node đúng chỉ vì tags đã xuất hiện; phải xác nhận **server selection tại client**.

## 6. Read preference: ai được phép phục vụ một truy vấn đọc?

MongoDB có năm read preference mode phổ biến:

| Mode | Mục tiêu lựa chọn | Hành vi cần chú ý |
|---|---|---|
| `primary` | Chỉ primary | Mặc định cho phần lớn client; không dùng tag sets để chọn secondary |
| `primaryPreferred` | Ưu tiên primary | Khi primary không khả dụng, có thể đọc secondary theo các điều kiện phù hợp; có nguy cơ dữ liệu trễ khi fallback |
| `secondary` | Chỉ secondary | Phù hợp đọc có thể chịu lag; nếu không có secondary đủ điều kiện sẽ chờ/chọn server thất bại, không âm thầm dùng primary |
| `secondaryPreferred` | Ưu tiên secondary | Có thể fallback sang primary nếu không có secondary dùng được; dễ vô tình dồn tải về primary |
| `nearest` | Member có latency được xem là gần theo driver | Có thể chọn primary **hoặc** secondary; không phải “secondary gần nhất” |

**Không có mode tên “reporting”.** Reporting là tag do bạn định nghĩa; `secondary` là mode đọc secondary; kết hợp chúng để chọn nhóm node phù hợp.

### 6.1. `primary`

~~~javascript
// Ý tưởng cấu hình client:
readPreference = "primary"
~~~

Hữu ích khi:

- Vừa ghi xong và cần đọc trạng thái mới nhất có thể quan sát qua primary theo consistency đã chọn.
- Thao tác phụ thuộc thứ tự ghi, đơn hàng, inventory, xác nhận giao dịch.
- Transaction cần read preference primary theo giới hạn của MongoDB.

Read preference `primary` không cho phép dùng tag set để chọn secondary. Nếu một cấu hình client cố ghép `primary` với read preference tags, có thể bị từ chối bởi driver/configuration.

### 6.2. `secondary`

~~~javascript
readPreference = "secondary"
~~~

Chỉ xem secondary đủ điều kiện theo tags, staleness và latency. Phù hợp khi bạn muốn **bảo vệ primary khỏi workload đọc phụ trợ**, kể cả trường hợp báo cáo phải trả lỗi tạm thời khi secondary không có.

### 6.3. `secondaryPreferred`

~~~javascript
readPreference = "secondaryPreferred"
~~~

Đây là lựa chọn hướng tới availability, nhưng **không phải hard isolation**. Khi không có secondary đủ điều kiện, mode này có thể đọc từ primary theo quy tắc fallback. Nếu dashboard nặng sử dụng mode này, sự cố secondary có thể đẩy hàng loạt báo cáo về primary đúng lúc hệ thống đang thiếu tài nguyên.

### 6.4. `primaryPreferred`

Chọn primary khi có primary phù hợp; tag sets dùng trong việc lựa chọn secondary khi cần fallback. Khi primary đang sẵn sàng, tag “reporting” không biến mode này thành đọc reporting secondary.

### 6.5. `nearest`

Driver chọn các member dựa trên điều kiện eligibility, tag sets và ước lượng latency. **Nearest có thể bao gồm primary**, vì vậy không dùng mode này nếu yêu cầu là “báo cáo tuyệt đối không chạm primary”. Khoảng cách địa lý thật không được driver dùng trực tiếp như một thuật toán GIS; nó sử dụng latency mạng đo được trong quá trình giám sát topology.

## 7. Tag sets: chọn nhóm member bằng những điều kiện ưu tiên

Một **tag set** là tập các cặp key/value phải khớp **đồng thời** trên một member. Ví dụ:

~~~javascript
{ purpose: "reporting", region: "hanoi" }
~~~

nghĩa là member phải có **cả** `purpose = reporting` **và** `region = hanoi`.

Một **danh sách tag sets** là các phương án lựa chọn theo **thứ tự ưu tiên**:

~~~javascript
[
  { purpose: "reporting", region: "hanoi" },
  { purpose: "reporting" }
]
~~~

Hệ thống sẽ xem tag set đầu tiên có các node đủ điều kiện; nếu không có member đáp ứng set đó, thử set tiếp theo. **Không** đọc hai object này như toán tử AND giữa các set. AND nằm **trong một tag set**, còn các set trong list là **các lớp fallback có thứ tự**.

~~~mermaid
flowchart TD
    R["Đọc với mode secondary"] --> First{"Có secondary reporting + hanoi?"}
    First -->|"Có"| A["Chọn trong nhóm reporting/hanoi"]
    First -->|"Không"| Second{"Có secondary reporting?"}
    Second -->|"Có"| B["Chọn trong nhóm reporting bất kỳ vùng"]
    Second -->|"Không"| E["Không có server phù hợp"]
~~~

### 7.1. Ưu tiên nghiêm ngặt cho reporting

~~~javascript
[
  { purpose: "reporting", region: "hanoi" },
  { purpose: "reporting" }
]
~~~

Khi dùng mode `secondary`, cả hai tầng đều giữ điều kiện `purpose: "reporting"`. Nếu không có secondary reporting, truy vấn không âm thầm rơi sang secondary dành cho API hoặc primary. Đây là **fail closed ở mức server selection** cho workload reporting.

### 7.2. Fallback sang mọi secondary

~~~javascript
[
  { purpose: "reporting", region: "hanoi" },
  { purpose: "reporting" },
  {}
]
~~~

Tag set rỗng `{}` biểu thị **không thêm giới hạn tag** ở tầng fallback cuối. Nó cho phép các secondary không mang tag reporting cũng có thể được chọn nếu hai tầng trước không có member đủ điều kiện.

**Đừng thêm `{}` theo thói quen.** Đối với báo cáo nặng, fallback cuối có thể đánh vào secondary API và làm tăng replication lag hoặc latency của những truy vấn quan trọng.

### 7.3. Danh sách chỉ một tag set

~~~javascript
[{ purpose: "app" }]
~~~

giới hạn vào member có tag app. Với `secondary`, nó có thể chọn các secondary app đủ điều kiện, **không** chọn primary chỉ vì primary cũng mang tag app.

### 7.4. Không có tags

Nếu read preference mode được thiết lập nhưng **không có tag constraint**, driver có thể xem tất cả member được phép bởi mode đó, sau khi áp điều kiện health/staleness/latency. Đây là hành vi khác với việc chỉ định một tag set có key không tồn tại.

### 7.5. Cần hiểu fallback của read preference mode riêng với fallback tag set

Hai bước lựa chọn:

1. **Mode** quyết định những loại member có thể được xem xét và khi nào được fallback primary/secondary.
2. **Tag set list** ưu tiên những member khớp metadata trong nhóm đủ điều kiện đó.

Ví dụ mode `secondaryPreferred` có thể fallback tới primary khi không còn secondary phù hợp. Đừng nghĩ `[{purpose:"reporting"}]` tạo cam kết tuyệt đối rằng mọi query ở mode đó **không bao giờ chạy trên primary**. Muốn tách tải báo cáo khỏi primary với hậu quả rõ ràng khi thiếu capacity, ưu tiên mode `secondary` và tag sets strict, cộng timeout/error handling thích hợp.

## 8. Thiết kế tag taxonomy theo mục đích phân tải

Một hệ thống có thể phân loại đọc:

| Workload | Yêu cầu dữ liệu | Cách chọn member ứng viên |
|---|---|---|
| Xác nhận thanh toán, số dư, tồn kho vừa cập nhật | Cần consistency cao | `primary` và read/write concern phù hợp |
| Trang danh mục ít thay đổi | Chấp nhận lag nhỏ | `secondary` hoặc `secondaryPreferred` với tag app |
| Dashboard BI theo giờ | Chấp nhận lag có giới hạn | `secondary` + tag reporting |
| Export dữ liệu lớn theo lịch | Có thể chạy chậm/dừng nếu secondary bận | `secondary` + tag batch/reporting strict |
| Tìm kiếm thông tin hiển thị không quan trọng | Tối ưu latency khi consistency cho phép | `nearest` hoặc mode khác phù hợp, cần xét tải primary |
| Đọc trong multi-document transaction | Theo yêu cầu transaction | `primary` |

### 8.1. Tags theo role hay theo khu vực?

Hai mẫu phổ biến:

**Theo công việc:**

~~~javascript
{ purpose: "reporting" }
{ purpose: "app" }
~~~

**Theo công việc + vị trí:**

~~~javascript
{ purpose: "reporting", region: "hanoi" }
{ purpose: "reporting", region: "hcm" }
~~~

Tag `purpose` giúp tránh để batch query dùng node dành cho ứng dụng. Tag `region` giúp giới hạn lựa chọn theo data-center/vùng và có thể ảnh hưởng latency/network egress. Nhưng không nên để region thành điều kiện cứng nếu số node ở mỗi vùng không đủ chịu lỗi.

### 8.2. Chọn tên tag ổn định

Tránh lặp ý nghĩa:

~~~text
purpose=reports
role=reporting
workload=analytics
type=bi
~~~

Nếu mỗi nhóm ứng dụng dùng một key khác nhau cho cùng loại node, việc đổi cấu hình hoặc vận hành sẽ khó. Nên có một bảng quy ước:

~~~text
purpose: app | reporting | batch
region: hcm | hanoi
zone: az-a | az-b | az-c
~~~

Và nêu rõ:

- Node nào được dùng cho job nào.
- Workload nào được phép fallback.
- Node nào có thể tham gia election.
- Ai được phép sửa tags.
- Sau khi reconfig, kiểm tra gì để tránh cấu hình drift.

## 9. Ví dụ: ưu tiên báo cáo ở một vùng, fallback trong nhóm reporting

Topology:

~~~text
mongo-a: PRIMARY             purpose=app, region=hcm
mongo-b: SECONDARY           purpose=app, region=hcm
mongo-c: SECONDARY           purpose=reporting, region=hanoi
mongo-d: SECONDARY           purpose=reporting, region=hcm
~~~

Nhóm analytics muốn ưu tiên hanoi, nhưng vẫn có thể đọc hcm nếu mongo-c lỗi:

~~~javascript
const reportingTagSets = [
  { purpose: "reporting", region: "hanoi" },
  { purpose: "reporting" }
]
~~~

Nếu `mongo-c` healthy và đủ điều kiện, ưu tiên lớp đầu. Nếu `mongo-c` unavailable/stale theo bộ lọc có áp dụng, có thể chọn `mongo-d`. Không có tầng `{}` nên không tự sử dụng secondary `mongo-b`.

### 9.1. Yêu cầu “không được chạm primary”

Dùng:

~~~text
mode = secondary
tagSets = [
  {purpose:reporting, region:hanoi},
  {purpose:reporting}
]
~~~

Nếu không có reporting secondary phù hợp, driver cuối cùng có thể báo lỗi **server selection timeout**. Đây có thể là lựa chọn tốt: báo cáo phụ trợ dừng tạm thời thay vì đẩy hàng trăm truy vấn nặng lên primary đang xử lý giao dịch.

### 9.2. Yêu cầu “ưu tiên availability”

Dùng `secondaryPreferred` có thể là lựa chọn nếu API cho phép fallback primary khi secondaries không sẵn sàng. Đổi lại, cần **biết trước ảnh hưởng tải lên primary** và giới hạn concurrency/query time. Không chọn `secondaryPreferred` chỉ vì nghe “dự phòng tốt hơn”; phải gắn nó với SLO và chính sách overload.

### 9.3. Yêu cầu “fallback sang secondary app nhưng không primary”

Kết hợp `secondary` với:

~~~javascript
[
  { purpose: "reporting" },
  { purpose: "app" }
]
~~~

Cho phép chuyển tới secondary app khi thiếu reporting secondary. Nó vẫn có thể làm suy giảm API read latency. Nếu cần bảo vệ secondary app, bỏ tầng fallback này và để batch job retry có backoff khi không có node reporting.

## 10. maxStalenessSeconds: loại secondary quá trễ

Read preference có thể đặt `maxStalenessSeconds` nhằm **loại những secondary được ước lượng quá stale** so với trạng thái replication tham chiếu. Ví dụ:

~~~text
mode: secondary
tags: purpose=reporting
maxStalenessSeconds: 120
~~~

Ý định: chỉ chọn secondary đủ điều kiện và có staleness **ước lượng** trong mức chấp nhận. Trong MongoDB hiện đại, ngưỡng tối thiểu được hỗ trợ cho `maxStalenessSeconds` thường là **90 giây** (còn chịu yêu cầu liên quan heartbeat interval); không đặt tùy ý 5 hoặc 10 giây rồi kỳ vọng MongoDB chấp nhận.

### 10.1. Staleness không phải SLA tuyệt đối cho từng lần đọc

Không diễn giải:

> “maxStalenessSeconds = 120 nghĩa là mọi kết quả luôn mới tối đa 120 giây.”

Đây là điều kiện **server selection** dựa trên ước lượng độ trễ replication, không phải cam kết thời điểm cập nhật cuối của từng document hoặc cơ chế chờ đủ mọi write trước đó.

Những yếu tố có thể làm kết quả lệch:

- Latency của heartbeat/giám sát.
- Thời điểm node mới nhận/applied oplog.
- Tần suất write và cách ước lượng staleness.
- Thời điểm query được gửi so với thời điểm đánh giá server.
- Tải I/O/CPU trên secondary.

Nếu business yêu cầu “sau khi ghi phải thấy dữ liệu ngay”, **không dùng `maxStalenessSeconds` như giải pháp duy nhất**. Cân nhắc đọc primary, hoặc causal consistency với session và read/write concern thích hợp.

### 10.2. Secondary staleness và failover

Nếu mọi reporting secondary đều vượt ngưỡng staleness:

- Mode `secondary` có thể không tìm được member hợp lệ và chờ đến server selection timeout.
- Mode `secondaryPreferred` có thể chuyển sang primary theo fallback của mode.

Như vậy, cùng tag set nhưng **mode khác nhau cho cách hệ thống phản ứng với lag rất khác nhau**.

### 10.3. Khi không nên bật ngưỡng quá chặt

Một reporting job cho bảng số liệu cuối ngày có thể chấp nhận lag vài phút nhưng cần hoàn tất trước lịch giao báo cáo. Ngưỡng quá chặt có thể làm query thất bại vào lúc replica đang đồng bộ lại dù dữ liệu vẫn đủ dùng. Chọn staleness theo **yêu cầu nghiệp vụ**, không chọn số nhỏ nhất vì nghĩ “nhỏ là tốt”.

## 11. Latency window: tại sao không thể chỉ định “node gần nhất” bằng trực giác

Các driver MongoDB dùng cơ chế **server selection**:

1. Xác định member theo read preference mode.
2. Áp tags, max staleness và các điều kiện eligibility tương ứng.
3. Dựa vào **round-trip time** đã quan sát để xác định các member trong latency window.
4. Chọn một member trong nhóm ứng viên còn lại theo cơ chế driver.

Tham số `localThresholdMS` (thường mặc định khoảng **15 ms**) mô tả cửa sổ latency: những server có RTT không vượt quá RTT tốt nhất trong nhóm thêm mức threshold có thể cùng được xét.

### 11.1. Ví dụ

~~~text
Reporting secondary A: RTT 12 ms
Reporting secondary B: RTT 20 ms
Reporting secondary C: RTT 35 ms

localThresholdMS = 15 ms
=> Nhóm latency window xấp xỉ 12..27 ms
=> A và B có thể được xét; C thường nằm ngoài
~~~

Các số minh họa, không phải kết quả benchmark. Driver dùng phép đo theo thời gian, và danh sách ứng viên có thể đổi khi tải hoặc mạng thay đổi.

### 11.2. Không suy ra tỷ lệ tải 50/50

Tag set có hai secondary đủ điều kiện **không bảo đảm** mỗi node nhận đúng 50% query. Lựa chọn còn bị ảnh hưởng:

- Server selection của từng driver process.
- Kết nối/pool sẵn có và topology events.
- Latency window và tình trạng server.
- Số lượng client instance.
- Retry khi một node không còn eligible.
- Độ dài/trọng lượng khác nhau của các query.

Để phân tải **có tỷ lệ hoặc quota xác định**, cần kiến trúc workload routing, hàng đợi, client pools riêng hoặc scheduler, không chỉ tags.

### 11.3. nearest không có nghĩa phân tải khỏi primary

`nearest` xét primary lẫn secondary đủ điều kiện trong những trường hợp áp dụng. Nếu primary có RTT tốt, driver có thể chọn primary. Muốn tuyệt đối đọc secondary, dùng mode `secondary`.

## 12. Java Driver: read preference cho báo cáo

Một ứng dụng Java nên giới hạn read preference theo **repository/collection hoặc một truy vấn**, thay vì đặt mọi truy vấn của service sang secondary. Đoạn ví dụ minh họa API của MongoDB Java Sync Driver:

~~~java
import com.mongodb.ReadPreference;
import com.mongodb.Tag;
import com.mongodb.TagSet;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import org.bson.Document;

import java.util.List;

public class ReportingReadExample {
    public static void main(String[] args) {
        String uri =
            "mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/" +
            "?replicaSet=rs0";

        // Mỗi TagSet: các cặp đều phải khớp trên một member.
        TagSet preferredRegion = new TagSet(List.of(
            new Tag("purpose", "reporting"),
            new Tag("region", "hanoi")
        ));
        TagSet anyReporting = new TagSet(List.of(
            new Tag("purpose", "reporting")
        ));

        ReadPreference reportingReadPreference =
            ReadPreference.secondary(
                List.of(preferredRegion, anyReporting)
            );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> collection =
                client.getDatabase("shop").getCollection("orders");

            // Chỉ bản view này của collection dùng secondary reporting.
            MongoCollection<Document> reportingOrders =
                collection.withReadPreference(reportingReadPreference);

            try (MongoCursor<Document> cursor = reportingOrders
                    .find(Filters.eq("status", "PAID"))
                    .limit(100)
                    .iterator()) {
                while (cursor.hasNext()) {
                    System.out.println(cursor.next().toJson());
                }
            }
        }
    }
}
~~~

### 12.1. Điều Java example thể hiện

- Client kết nối tới **replica set URI** gồm seed hosts; driver khám phá topology.
- `ReadPreference.secondary(...)` không cho báo cáo âm thầm đọc primary.
- `preferredRegion` ưu tiên reporting secondary ở hanoi.
- Nếu không có, `anyReporting` cho reporting secondary vùng khác.
- `collection.withReadPreference(...)` trả view/config cho thao tác đọc; không đổi cách các collection khác đọc.

Nếu không có secondary reporting đủ điều kiện, truy vấn có thể chờ tới server selection timeout và lỗi. Cần bắt, phân loại và quyết định retry job có giới hạn ở tầng ứng dụng.

### 12.2. Không đặt read preference cho business transaction theo mẫu này

Ví dụ:

~~~java
// Chỉ minh họa nguyên tắc: repository xử lý tồn kho/đơn mới
// nên dùng primary/read concern phù hợp với nghiệp vụ.
MongoCollection<Document> writeCriticalOrders =
    collection.withReadPreference(ReadPreference.primary());
~~~

Read preference điều khiển **đọc**; thao tác ghi không được “đẩy sang secondary” bằng cách đặt `secondary`. Multi-document transactions phải tuân theo yêu cầu read preference primary của MongoDB.

### 12.3. Các tham số cần thiết kế kèm

Trong service thật còn cần:

- Server selection timeout phù hợp với SLO.
- Socket/connect timeout và connection pool.
- `maxTimeMS` cho query nặng để tránh giữ tài nguyên vô hạn.
- Read concern phù hợp với mức nhất quán cần thiết.
- Tracing/logging cho biết đọc từ member nào.
- Giới hạn đồng thời của reporting jobs.

Không đưa các tham số này thành một cấu hình mặc định cho mọi workload mà chưa đo tác động.

## 13. Node.js Driver: đặt read preference cho một truy vấn

~~~javascript
import { MongoClient, ReadPreference } from "mongodb";

const uri =
  "mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/" +
  "?replicaSet=rs0";

const client = new MongoClient(uri, {
  serverSelectionTimeoutMS: 5000
});

await client.connect();

try {
  const reportingPref = new ReadPreference(
    "secondary",
    [
      { purpose: "reporting", region: "hanoi" },
      { purpose: "reporting" }
    ],
    { maxStalenessSeconds: 120 }
  );

  const docs = await client
    .db("shop")
    .collection("orders")
    .find(
      { status: "PAID" },
      {
        readPreference: reportingPref,
        maxTimeMS: 3000
      }
    )
    .limit(100)
    .toArray();

  console.log("Reporting rows:", docs.length);
} finally {
  await client.close();
}
~~~

Đây là ví dụ minh họa một **đọc không quan trọng về độ mới tuyệt đối**. `maxStalenessSeconds: 120` là ràng buộc lựa chọn member, không giới hạn thời gian thực thi query. `maxTimeMS: 3000` mới liên quan đến ngân sách thời gian thực thi phía server; `serverSelectionTimeoutMS` là thời gian driver thử chọn server phù hợp.

### 13.1. Cần phân biệt ba timeout

| Tham số | Điều gì được giới hạn |
|---|---|
| `serverSelectionTimeoutMS` | Thời gian driver chờ tìm member đủ điều kiện |
| `maxTimeMS` | Ngân sách thực thi query trên server theo semantics được hỗ trợ |
| `socketTimeoutMS` và các timeout mạng | Thời gian chờ giao tiếp socket/operation theo driver |

Không dùng `maxTimeMS` để “sửa” lỗi không có secondary phù hợp; query có thể chưa được gửi tới server. Tương tự, tăng server selection timeout không làm một secondary thiếu tag tự nhiên trở thành eligible.

### 13.2. Quan sát member thực thi

Trong Node.js Driver, có thể bật **command monitoring** khi cấu hình client và lắng nghe sự kiện liên quan đến lệnh, thu thập server address từ metadata được driver cung cấp. Dùng chức năng này trong môi trường test để xác nhận lệnh read thực sự chạy trên node `purpose=reporting`.

Không ghi command body đầy đủ nếu chứa PII/credentials; chỉ log request ID, operation, server address và timing khi đã kiểm tra chính sách bảo mật.

## 14. MongoDB URI: cấu hình read preference và tag sets

Connection string có thể chứa mode và các tag sets:

~~~text
mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/
  ?replicaSet=rs0
  &readPreference=secondary
  &readPreferenceTags=purpose:reporting,region:hanoi
  &readPreferenceTags=purpose:reporting
  &maxStalenessSeconds=120
~~~

Đây là định dạng **xuống dòng để dễ đọc**. Trong cấu hình thật, dùng **một URI liền mạch**, không có khoảng trắng/xuống dòng; encode các ký tự đặc biệt theo quy tắc URI. Lặp tham số `readPreferenceTags` biểu thị **nhiều tag sets có thứ tự**, khác với việc ghép tất cả cặp vào một tag set duy nhất.

### 14.1. Khi nào dùng URI thay vì per-operation?

**URI-level** phù hợp nếu một client/worker được thiết kế chuyên cho reporting. Ví dụ một batch service không chạy write-critical reads có thể dùng kết nối riêng với `readPreference=secondary`.

**Per-operation/per-collection** phù hợp nếu cùng một service vừa có API quan trọng đọc primary vừa có dashboard có thể dùng secondary.

Tránh một connection string toàn cục `secondaryPreferred` cho mọi repository: nó có thể đưa cả những truy vấn cần đọc mới nhất sang secondary khi ứng dụng không chủ động xác định consistency.

### 14.2. Fallback tag rỗng trong URI

Một tầng fallback `{}` có thể được biểu diễn bằng giá trị tag set rỗng theo cú pháp URI được driver hỗ trợ, nhưng **không thêm fallback rỗng chỉ để query “luôn chạy được”**. Nó mở rộng eligibility sang member không mang tag workload, có thể phá mục tiêu tách tải đọc.

## 15. Thực hành mongosh với read preference

Trong một phiên mongosh kết nối tới replica set:

~~~javascript
// Xem trước cấu hình. Đảm bảo có secondary mang purpose=reporting.
rs.conf()

// Thiết lập mode và tag sets cho kết nối shell trong lab.
db.getMongo().setReadPref(
  "secondary",
  [
    { purpose: "reporting", region: "hanoi" },
    { purpose: "reporting" }
  ]
)

use shop

db.orders.find(
  { status: "PAID" },
  { _id: 1, createdAt: 1, amount: 1 }
).limit(10)

// Trả về read preference mặc định ở primary sau khi thử.
db.getMongo().setReadPref("primary")
~~~

Lưu ý:

- Cú pháp và option mongosh có thể thay đổi giữa phiên bản; có thể dùng URI nếu muốn test nhất quán theo driver.
- Nếu chỉ có một secondary reporting ở hanoi, lựa chọn thường rõ ràng hơn, nhưng vẫn cần kiểm tra node thực thi.
- Query có thể thành công mà bạn không nhìn thấy **node nào** trong kết quả `find()`. Cần observability phía driver/server.
- Dùng shell ở chế độ direct connection tới một member có thể làm sai mục tiêu kiểm tra **driver server selection trong replica set topology**; để test read preference, dùng kết nối replica set đúng cách.

### 15.1. Thử tag sets không khớp

~~~javascript
db.getMongo().setReadPref(
  "secondary",
  [{ purpose: "nonexistent-workload" }]
)

db.orders.findOne({})
~~~

Với replica set không có secondary mang tag này, query có thể lỗi server selection sau timeout. Đây là một phép thử có ích để hiểu **không có fallback tự động sang primary** khi dùng mode secondary.

Sau đó khôi phục:

~~~javascript
db.getMongo().setReadPref("primary")
~~~

### 15.2. Một lần đọc không chứng minh khả năng phân tải

Nếu tất cả query tình cờ chạy trên mongo-c, không thể kết luận driver luôn chọn mongo-c hay tải được phân phối hợp lý. Cần quan sát nhiều request từ nhiều client instances, thời gian dài hơn, các sự cố node và thay đổi latency.

## 16. Read preference khác read concern

Hai khái niệm thường bị nhầm:

- **Read preference:** *đọc ở member nào?*
- **Read concern:** *mức cam kết/độ nhất quán của dữ liệu được phép quan sát là gì?*

Ví dụ:

~~~text
readPreference = secondary
readConcern = majority
~~~

nghĩa là cố chọn secondary theo mode/tags và yêu cầu đọc dữ liệu phù hợp với semantics majority read concern. Nó **không** có nghĩa secondary đã áp dụng toàn bộ write mới nhất của primary.

### 16.1. Read concern local

`local` cho phép đọc dữ liệu theo trạng thái local của member, và trong những điều kiện phù hợp dữ liệu chưa majority committed có thể bị rollback. Nó không bảo đảm ứng dụng đọc được write vừa thực hiện ở primary.

### 16.2. Read concern majority

`majority` giới hạn quan sát theo các write được majority acknowledged/committed theo semantics MongoDB, giúp tránh đọc một số dữ liệu có thể rollback. Nhưng secondary có thể **chưa bắt kịp**; kết quả có thể hợp lệ mà vẫn cũ.

### 16.3. Linearizable không phải giải pháp đọc secondary

Read concern `linearizable` được thiết kế cho đọc trên primary với những điều kiện liên quan, không phải cách ép secondary trả dữ liệu mới nhất. Nếu yêu cầu linearizable semantics, không dùng nó để hợp thức hóa read preference secondary.

### 16.4. Bảng tóm tắt

| Cấu hình | Được chọn node nào? | Tính mới/nhất quán |
|---|---|---|
| `primary + local` | Primary | Thấy trạng thái primary theo local semantics, không mặc định majority durability |
| `primary + majority` | Primary | Đọc dữ liệu majority committed theo semantics read concern; vẫn cần xét consistency API |
| `secondary + local` | Secondary | Có thể stale, một số dữ liệu có thể rollback tùy trạng thái commit |
| `secondary + majority` | Secondary | Majority-committed nhưng **không chắc mới nhất** |
| `secondary + causal session` | Secondary đủ điều kiện | Có thể đáp ứng một số guarantee nhân quả khi cấu hình session/read/write concern đúng, đôi khi phải chờ |

**Không có một trường cấu hình đơn lẻ** biến mọi secondary read thành đọc mạnh như một giao dịch trên primary.

## 17. Causal consistency và read-your-writes

Tình huống:

1. Client tạo order trên primary.
2. Ngay sau đó muốn hiển thị order trong một màn hình dùng secondary.

Nếu chỉ đặt `readPreference=secondary`, có khả năng query tiếp theo **chưa nhìn thấy** write. Một phương án là **causally consistent session** với write concern và read concern phù hợp (thường cần majority cho các bảo đảm liên quan), giúp driver/server duy trì quan hệ nhân quả giữa các operation cùng session trong điều kiện hỗ trợ.

### 17.1. Không phải giải pháp vô hạn và miễn phí

Nếu secondary chưa đạt tới thời điểm cần đọc theo quan hệ nhân quả, operation có thể phải **đợi**. Khi lag lớn, latency tăng hoặc query timeout. Vì vậy causal consistency không thay thế capacity và replication health.

### 17.2. Khi nào nên đọc primary đơn giản hơn?

Đối với flow:

~~~text
POST /orders
GET /orders/{id} ngay lập tức
~~~

đọc primary cho GET ngay sau write thường là quyết định dễ hiểu hơn nếu mục tiêu là **hiển thị vừa tạo** với độ trễ thấp và chính xác. Các màn hình danh mục, báo cáo hoặc dashboard không cần đọc vừa ghi có thể dùng secondary.

### 17.3. Session không tự truyền giữa hai request HTTP

Đừng giả định request sau tự động kế thừa cùng logical session/causal context. Nếu application muốn bảo đảm liên kết, cần thiết kế cách truyền ngữ cảnh và quản lý session phù hợp. Đối với các API độc lập, read preference secondary thường đem lại eventual consistency trừ khi có cơ chế bổ sung.

## 18. Hidden và delayed members: không coi là reporting secondary thông thường

Một replica set member có thể là:

- Secondary thông thường, có thể được driver chọn theo read preference.
- **Hidden secondary**, không hiển thị cho cơ chế lựa chọn đọc thông thường của ứng dụng.
- **Delayed secondary**, cố tình áp dụng replication trễ và thường được cấu hình hidden.
- Member `priority: 0`, không được bầu primary nhưng **không tự động hidden**.

### 18.1. Không dùng tag để “mở khóa” hidden member

Ngay cả nếu hidden member có tag:

~~~javascript
tags: { purpose: "backup" }
~~~

driver không chọn hidden member cho read preference thông thường chỉ vì tag khớp. Hidden member thường chỉ nhận read khi client **kết nối trực tiếp** đến member trong những tình huống quản trị phù hợp.

Vì vậy, cấu hình:

~~~text
readPreference=secondary
tagSets=[{purpose:"backup"}]
~~~

không biến hidden backup node thành reporting secondary tiêu chuẩn. Nếu muốn một node phục vụ báo cáo tự động theo topology, cần thiết kế nó là **secondary có thể được chọn**, không phải hidden, và cân nhắc `priority:0` nếu muốn tránh vai trò primary.

### 18.2. Delayed secondary không phục vụ báo cáo thời gian thực

Delayed member cố ý giữ dữ liệu lùi so với primary. Việc ép truy vấn tới member này để “giảm tải” có thể trả dữ liệu sai kỳ vọng, nhất là khi kết quả dùng cho quyết định kinh doanh. Nó thường phục vụ một số mục tiêu bảo vệ/phục hồi dữ liệu, không phải read scaling cho API.

### 18.3. Priority:0 khác hidden:true

| Tùy chọn | Ảnh hưởng chính |
|---|---|
| `priority: 0` | Member không được bầu primary |
| `hidden: true` | Member không được driver chọn theo read preference topology thông thường |
| Tags | Giúp mô tả điều kiện chọn server |

Không đánh đồng ba khái niệm. Một secondary `priority:0` nhưng `hidden:false` vẫn có thể được chọn cho read theo mode/tags phù hợp.

## 19. Failover: điều gì xảy ra khi node biến mất?

Giả sử reporting đọc từ `mongo-c` theo:

~~~text
readPreference = secondary
tagSets = [{purpose:reporting}]
~~~

Khi `mongo-c` mất kết nối:

1. Driver cập nhật topology dựa trên heartbeat/monitoring.
2. Nếu có reporting secondary khác đủ điều kiện, có thể chuyển sang node đó.
3. Nếu không có, truy vấn có thể chờ đến server selection timeout rồi lỗi.
4. Nó **không** tự dùng primary vì mode secondary không cho phép.

### 19.1. Trường hợp secondaryPreferred

Với `secondaryPreferred`, khi không có secondary đủ điều kiện, mode có thể fallback tới primary. Điều này làm tăng availability nhưng có thể **tạo overload bất ngờ** nếu thứ vừa mất là một reporting node và toàn bộ batch quay về primary.

### 19.2. Khi primary thay đổi

Nếu reporting secondary được bầu primary, nó không còn là ứng viên cho `secondary`. Tags vẫn là metadata của member nhưng read preference mode loại role primary. Đừng thiết kế dựa vào giả định “tag reporting thì vĩnh viễn là secondary”.

Nếu muốn dành riêng member cho báo cáo, xem xét thiết kế election priority, số member electable, votes, majority và failure domain từ đầu.

### 19.3. Retry có giới hạn

Batch/reporting job khi không có member phù hợp có thể:

- Retry sau backoff + jitter.
- Giới hạn số concurrent jobs.
- Dùng deadline phù hợp lịch báo cáo.
- Cảnh báo khi không có reporting secondary hoặc lag quá ngưỡng.
- Hủy/đợi người vận hành khi tiêu chí tách tải nghiêm ngặt không còn đáp ứng.

Tránh cơ chế tự sửa bằng cách **đổi read preference về primary cho mọi batch** không có kiểm soát: có thể đẩy lỗi từ reporting thành sự cố giao dịch.

## 20. Giám sát replication lag và sức khỏe secondary

Trên replica set, có thể xem:

~~~javascript
rs.status()
~~~

hoặc lệnh admin tương ứng, nếu có quyền:

~~~javascript
db.adminCommand({ replSetGetStatus: 1 })
~~~

Các trường như state, optime/applied times, heartbeat và trạng thái member giúp quan sát replication, nhưng phải hiểu theo phiên bản và không chỉ nhìn một timestamp duy nhất rồi kết luận mọi query có độ mới chính xác bằng chênh lệch đó.

### 20.1. Metric nên theo dõi

| Metric | Tại sao quan trọng? |
|---|---|
| Replication lag theo secondary | Lag lớn ảnh hưởng tính mới và eligibility của maxStaleness |
| CPU, disk I/O, cache pressure | Báo cáo có thể cạnh tranh với replication apply |
| Network bandwidth/RTT | Tác động server selection và latency |
| Query p95/p99 theo node | Phát hiện reporting secondary bị quá tải |
| Connections/active operations | Tìm batch/query giữ tài nguyên lâu |
| Server selection timeout | Không có member đủ điều kiện hoặc topology bất ổn |
| Tag drift/cấu hình member | Client có thể loại nhầm node nếu tags sai |
| Election/primary changes | Có thể đổi eligibility của node reporting |
| Oplog window/replication backlog | Secondary chậm có rủi ro mất khả năng bắt kịp |
| Read request rate theo workload | Xác minh thực sự có offload khỏi primary |

### 20.2. “Đã gửi sang secondary” chưa đủ để kết luận cải thiện

Giả sử primary CPU giảm 20%, nhưng reporting secondary CPU tăng lên 99% và replication lag nhảy từ vài giây lên hàng phút. Hệ thống có thể đã đổi một điểm nghẽn thành điểm nghẽn khác. Cần đo **end-to-end**: throughput, latency, staleness, lag, retry/error, network và khả năng phục hồi.

### 20.3. Đo trong đúng thời điểm workload

Một secondary có thể rất rảnh buổi sáng nhưng bị batch ETL sử dụng buổi tối. Tag/latency chỉ mô tả **eligibility và lựa chọn**, không đảm bảo luôn còn capacity. Cần scheduling, giới hạn song song và query time budget.

## 21. Index và hiệu năng truy vấn trên secondary

Read preference không sửa được query thiếu index. Nếu báo cáo chạy:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(100)
~~~

thì một compound index phù hợp vẫn quan trọng:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  { name: "idx_tenant_status_created" }
)
~~~

Trong replica set, cấu trúc index cần được duy trì trên các member. Thêm index làm tăng footprint và chi phí ghi/replication apply; điều này phải tính cùng hiệu quả reporting query.

### 21.1. Index phục vụ query và tag phục vụ routing

| Công cụ | Câu hỏi nó giải quyết |
|---|---|
| `readPreference=secondary` | Đọc trên loại member nào? |
| Tag sets | Secondary thuộc nhóm mục đích/vùng nào? |
| `maxStalenessSeconds` | Member có staleness ước lượng trong ngưỡng không? |
| `localThresholdMS` | Member có trong latency window không? |
| Index | Query lọc/sort trên dữ liệu của member có hiệu quả không? |
| Read concern | Mức dữ liệu được phép quan sát là gì? |

**Tag không thay index**, và index không đảm bảo query được route khỏi primary.

### 21.2. Explain không luôn xác nhận node đã chọn

`explain("executionStats")` rất hữu ích để phân tích `IXSCAN`, `COLLSCAN`, `SORT`, `totalKeysExamined` và `totalDocsExamined`. Nhưng **explain không phải bằng chứng đầy đủ cho chiến lược server selection của client**. Nên kết hợp command monitoring ở driver hoặc log/metrics phía node để xác nhận query thực sự chạy ở member dự kiến.

### 21.3. Reporting read vẫn có thể tác động thời gian apply oplog

Nếu báo cáo chạy collection scan lớn, nó tiêu thụ CPU/cache/disk chung với replication applier. Secondary quá tải có thể áp dụng oplog chậm, tăng lag, và bị loại theo `maxStalenessSeconds`. Đây là vòng phản hồi không tốt: càng dồn báo cáo sang một node, node càng lag và có thể bị rớt khỏi nhóm eligible.

## 22. Chiến lược phân tải đọc theo nhóm API

Một cách triển khai thực tế là tạo **những client/query policy riêng** thay vì thay global read preference vô điều kiện:

~~~mermaid
flowchart LR
    UI["Người dùng"] --> API["Backend"]
    API --> Critical["Order / inventory repository"]
    API --> Catalog["Catalog repository"]
    API --> Reports["Reporting service"]
    Critical -->|"primary"| P["Primary"]
    Catalog -->|"secondary / app tag"| S1["Secondary app"]
    Reports -->|"secondary / reporting tag"| S2["Secondary reporting"]
    P -.->|"Replication"| S1
    P -.->|"Replication"| S2
~~~

### 22.1. Repository giao dịch

Đặt read preference `primary` để giảm bất ngờ trong flow sau ghi. Với nghiệp vụ có transaction, dùng read/write concern phù hợp.

### 22.2. Repository danh mục

Nếu dữ liệu chậm vài giây không làm sai nghiệp vụ, có thể dùng `secondary` hoặc `secondaryPreferred` tùy availability contract. Tag `purpose:app` tránh node reporting.

### 22.3. Reporting service

Đặt `secondary` với tag `purpose:reporting` để **không fallback primary**, giới hạn concurrent jobs và có retry budget. Với báo cáo mà dữ liệu trễ được chấp nhận, chọn max staleness phù hợp; đừng đặt ngưỡng nhỏ hơn khả năng thực của replication.

### 22.4. Export/batch lâu

Có thể dùng một reporting secondary riêng, với `maxTimeMS`, scheduler, giới hạn batch size và cửa sổ chạy. Nếu muốn batch chạy theo snapshot logic nhất quán, cần thêm thiết kế cutoff/snapshot hoặc materialized data; read preference secondary **không tự giữ một snapshot cố định trong cả job kéo dài**.

### 22.5. Tránh gián tiếp xếp hàng trên primary

Một secondary bị quá tải khiến batch dùng mode `secondaryPreferred` fallback primary có thể làm primary tăng độ trễ và gây retry ở các API quan trọng. Thiết kế rõ **ngân sách chịu tải**: job phụ trợ nên thất bại có kiểm soát thay vì tranh tài nguyên với giao dịch chính.

## 23. Tag-based selection không phải load balancing theo phần trăm

Có hai secondary reporting:

~~~text
mongo-c: purpose=reporting, RTT≈10ms, CPU=80%
mongo-d: purpose=reporting, RTT≈25ms, CPU=20%
~~~

Nếu latency window nhỏ và mongo-c luôn có RTT tốt hơn, driver có thể ưu tiên mongo-c trong nhiều lần chọn, dù CPU của nó cao. Tags không mang thông tin “CPU ít hơn nên chọn node này”.

Nếu cần phân phối theo capacity:

- Chia batch queue thành những nhóm được điều phối theo node/workload.
- Sử dụng client pools hoặc deployment riêng cho báo cáo quan trọng.
- Cân nhắc cửa sổ latency, topology, vị trí client và mục tiêu hiệu năng.
- Theo dõi lag/capacity và giảm concurrency khi quá tải.
- Không cố gắn tên host vào logic nghiệp vụ nếu MongoDB driver có thể quản lý topology tốt hơn; chỉ dùng direct connection cho use case vận hành đặc biệt.

### 23.1. Phân biệt tag preference với data locality

Tag `region:hanoi` là metadata do đội vận hành đặt. Driver không xác minh node vật lý có thật ở Hà Nội hay dữ liệu có residency phù hợp pháp lý. Nếu có yêu cầu data residency, compliance hoặc mạng cách ly, cần kiểm soát hạ tầng/triển khai bổ sung.

### 23.2. Tag preference không làm một secondary trở nên nhanh hơn

Nếu secondary đang chậm do thiếu index hoặc network, tag matching vẫn chỉ trả lời “node đủ điều kiện”. Giảm latency cần tối ưu query, index, connection pool, cache, tài nguyên và vị trí client.

## 24. Sharded cluster: mỗi shard cũng có replica set

Trong sharded cluster, mỗi shard thường là một replica set. Read preference/tag sets có thể ảnh hưởng lựa chọn thành viên phục vụ đọc ở **các shard liên quan**. Những điều cần kiểm tra:

- Shard nào thực sự chứa dữ liệu cho query?
- Mỗi shard có secondary mang cùng tag `purpose:reporting` hay không?
- Có shard chỉ có app secondary, khiến reporting query thiếu server phù hợp?
- Staleness/latency của các shard có đồng đều không?
- Query cần scatter-gather tới nhiều shards và hợp nhất kết quả không?
- Phân phối tải có tạo hot shard không?

### 24.1. Không suy ra tag thay shard key

Tag-based read preference chọn **replica set member** để đọc. Shard key quyết định **phân phối/routing dữ liệu giữa shards**. Hai bài toán khác nhau. Có reporting secondary cho mỗi shard không tự khiến một query không có shard key trở thành targeted query.

### 24.2. Cross-shard read có nhiều thời điểm quan sát

Với read preference secondary trên nhiều shards, mỗi shard/member có thể ở thời điểm replication khác nhau. Nếu báo cáo yêu cầu ảnh chụp dữ liệu nhất quán xuyên nhiều nguồn, cần xem read concern/snapshot semantics được hỗ trợ và thiết kế báo cáo, không chỉ đặt cùng `maxStalenessSeconds`.

## 25. Kịch bản lỗi: chính sách nào làm gì?

| Tình huống | `secondary` + tag reporting strict | `secondaryPreferred` + tag reporting | `nearest` không tag |
|---|---|---|---|
| Reporting secondary healthy | Chọn secondary reporting eligible | Ưu tiên secondary reporting | Có thể chọn bất kỳ member đủ điều kiện, gồm primary |
| Reporting secondary mất kết nối | Không có member phù hợp → timeout/lỗi nếu không có reporting khác | Có thể quay về primary theo fallback mode | Có thể chọn primary/secondary khác theo latency |
| Reporting secondary quá stale | Bị loại theo maxStaleness nếu cấu hình | Có thể fallback primary | Phụ thuộc cấu hình staleness và eligibility |
| Primary quá tải | Không tự gửi reporting vào primary | Có nguy cơ dồn reporting về primary khi thiếu secondary | Primary vẫn có thể được chọn |
| Mong muốn dữ liệu vừa ghi | Không bảo đảm read-your-writes | Không bảo đảm nếu đang đọc secondary | Không bảo đảm vì có thể đọc secondary |
| Muốn tránh primary tuyệt đối | Phù hợp | Không phù hợp | Không phù hợp |

Bảng là định hướng **policy**, không thay thế kiểm tra hành vi driver/phiên bản với topology thật.

### 25.1. Tình huống 1: “Báo cáo phải chậm còn hơn làm primary chậm”

Chọn mode `secondary`, tag sets chỉ gồm reporting, không có `{}`. Khi không đủ secondary, job có thể chờ/retry có kiểm soát và cảnh báo. Đây là **failure isolation bằng chính sách lựa chọn server**, không phải hard isolation về CPU/network.

### 25.2. Tình huống 2: “Feed phải hoạt động nếu secondary chết”

Chọn `secondaryPreferred` khi ứng dụng **chấp nhận** tải fallback lên primary và có safeguard. Nếu feed cần thấy write ngay sau khi tạo, có thể phải đọc primary ở endpoint cụ thể.

### 25.3. Tình huống 3: “Đọc gần client nhất”

`nearest` có thể hợp lý nếu đọc từ primary hoặc secondary đều chấp nhận, nhưng phải hiểu latency window; nếu yêu cầu thật là secondary, dùng `secondary` và tags theo vùng thay vì nghĩ nearest mặc nhiên tránh primary.

### 25.4. Tình huống 4: “Chỉ secondary zone B”

Tag set strict:

~~~javascript
[{ zone: "az-b" }]
~~~

Nếu node zone B không healthy hoặc không còn secondary, truy vấn có thể lỗi. Nếu muốn fallback vùng khác thì dùng nhiều tag sets có thứ tự.

## 26. Một lab thử nghiệm không cần giả định đã có production cluster

Điều kiện: có replica set lab ít nhất ba data-bearing members, trong đó có hai secondary, đang khỏe mạnh. Các ví dụ hostname cần thay bằng hostname thật của lab. Không cố dựng topology bằng cách chạy `rs.initiate()` trên một production cluster đã tồn tại.

### 26.1. Chuẩn bị schema và index mẫu

Trên primary lab:

~~~javascript
use read_scaling_lab

db.orders.insertMany([
  {
    _id: "o-001", tenantId: "t-01", status: "PAID",
    amount: NumberDecimal("150000"),
    createdAt: ISODate("2026-08-01T08:00:00Z")
  },
  {
    _id: "o-002", tenantId: "t-01", status: "CREATED",
    amount: NumberDecimal("300000"),
    createdAt: ISODate("2026-08-02T09:00:00Z")
  },
  {
    _id: "o-003", tenantId: "t-02", status: "PAID",
    amount: NumberDecimal("450000"),
    createdAt: ISODate("2026-08-03T10:00:00Z")
  },
  {
    _id: "o-004", tenantId: "t-01", status: "PAID",
    amount: NumberDecimal("90000"),
    createdAt: ISODate("2026-08-04T11:00:00Z")
  },
  {
    _id: "o-005", tenantId: "t-02", status: "PAID",
    amount: NumberDecimal("250000"),
    createdAt: ISODate("2026-08-05T12:00:00Z")
  }
])

db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
)
~~~

Chỉ insert trên database lab rỗng; chạy lại cùng `_id` sẽ gặp duplicate key. Nếu cần lặp bài, dùng một database lab mới.

### 26.2. Gắn tag cho hai secondary

Ví dụ kế hoạch:

~~~text
Primary: mongo-a, purpose=app
Secondary 1: mongo-b, purpose=app, region=hcm
Secondary 2: mongo-c, purpose=reporting, region=hanoi
~~~

Sử dụng `rs.conf()` để xác nhận chính xác member host trước khi `rs.reconfig()` trong lab. Không làm thay đổi priority/votes không cần thiết.

### 26.3. Chạy workload reporting

~~~javascript
db.getMongo().setReadPref(
  "secondary",
  [{ purpose: "reporting" }]
)

use read_scaling_lab

db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      totalRevenue: { $sum: "$amount" },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { totalRevenue: -1 } }
])

db.getMongo().setReadPref("primary")
~~~

Vì đây là dataset nhỏ, bài lab tập trung vào **server selection**, không phải benchmark throughput. Cần command monitoring/log để xác minh member nào thực thi query. Dùng nhiều dữ liệu đại diện và lặp đủ lần mới so CPU/latency.

### 26.4. Thử mất reporting secondary

Chỉ trong lab có quyền vận hành và quy trình khôi phục:

1. Xác minh `mongo-c` là reporting secondary duy nhất.
2. Tạm làm node không sẵn sàng **theo kịch bản kiểm thử an toàn**.
3. Query với mode `secondary` + tag reporting strict.
4. Quan sát server selection timeout/thông báo lỗi.
5. Khôi phục node và chờ replication bắt kịp.
6. So với mode `secondaryPreferred` để thấy fallback có thể tác động primary.

Không tắt node replica set production chỉ để trình diễn. Với lab có ít member, mọi thao tác làm mất node phải cân nhắc majority và khả năng election.

### 26.5. Thử mất khả năng match tag

Thay vì tắt node, có thể sửa tag `purpose=reporting` thành một giá trị khác **trong lab**, sau đó chạy query strict. Điều này kiểm tra cách driver phản ứng khi không còn member thỏa tag mà không cần mô phỏng mất mạng. Vẫn cần tránh reconfig trên production.

### 26.6. Quan sát lag

Trong lab, tạo một số ghi trên primary rồi xem trạng thái replication của các secondary. Đừng tuyên bố “secondary luôn nhìn thấy ghi ngay sau insert”; ghi chép thời điểm read cho từng node và so khi có/không `maxStalenessSeconds` ở mức hỗ trợ. **Dữ liệu rất nhỏ và mạng local có thể làm lag gần bằng 0**, không chứng minh tính nhất quán tuyệt đối.

## 27. Bài tập từ cơ bản đến nâng cao

### Bài 1 — Phân biệt role

Cho ba member: primary A, secondary B, secondary C. Giải thích vì sao read preference `secondary` không chọn A, dù A có tag `purpose:reporting`.

### Bài 2 — AND trong tag set

Cho:

~~~javascript
{ purpose: "reporting", region: "hanoi" }
~~~

Member chỉ có `purpose:reporting` nhưng region hcm có khớp không? Vì sao?

### Bài 3 — Fallback theo thứ tự tag sets

~~~javascript
[
  { purpose: "reporting", region: "hanoi" },
  { purpose: "reporting" },
  {}
]
~~~

Giải thích ba lớp fallback và rủi ro của `{}` đối với tải API secondary.

### Bài 4 — Không quay lại primary

Thiết kế read preference cho job export lớn có yêu cầu: **chỉ đọc secondary reporting; nếu không có, job dừng và retry sau**. Chọn mode nào, tag sets nào?

### Bài 5 — Availability

Một API danh mục chấp nhận đọc từ primary khi không có secondary. Nêu một mode có thể phù hợp, và cảnh báo về tải fallback.

### Bài 6 — Nearest

Nếu primary RTT 5ms, secondary A RTT 12ms, secondary B RTT 20ms, tại sao `nearest` có thể chọn primary dù mục tiêu trước đó là đọc secondary?

### Bài 7 — Staleness

Job yêu cầu không chọn secondary có staleness ước lượng quá cao. Cấu hình `maxStalenessSeconds: 120` có thể giúp gì và **không bảo đảm** điều gì?

### Bài 8 — Read concern

So:

~~~text
secondary + local
secondary + majority
primary + majority
~~~

Cấu hình nào có thể đọc dữ liệu majority committed? Cấu hình nào vẫn có nguy cơ không thấy một write vừa thành công ở primary?

### Bài 9 — Hidden member

Một hidden secondary có `tags:{purpose:"backup"}`. Có thể dùng `secondary` + tag backup để driver tự chọn nó không? Cách hiểu đúng về hidden và direct connection?

### Bài 10 — Priority 0

Một secondary `priority:0, hidden:false` có thể phục vụ read theo tags không? `priority:0` khác `hidden:true` ở đâu?

### Bài 11 — Tối ưu index

Báo cáo lọc `tenantId`, `status` và sắp ngày giảm dần. Tại sao chỉ đặt read preference secondary không giải quyết COLLSCAN? Đề xuất compound index.

### Bài 12 — Causal consistency

Người dùng vừa đặt hàng rồi thấy order bị “mất” trên trang đọc secondary. Giải thích nguyên nhân và hai hướng xử lý phù hợp.

### Bài 13 — Failover

Một reporting secondary bị bầu thành primary. Điều gì xảy ra với client `secondary` strict tag reporting nếu không còn reporting secondary khác?

### Bài 14 — Sharded cluster

Một sharded cluster có ba shards, nhưng chỉ hai shards có reporting secondary. Những vấn đề gì có thể xảy ra với báo cáo scatter-gather dùng tag reporting strict?

### Bài 15 — Đo phân tải

Lập bảng metric trước/sau:

| Metric | Trước | Sau | Nhận xét |
|---|---|---|---|
| Primary CPU | … | … | … |
| Reporting secondary CPU | … | … | … |
| Replication lag p95 | … | … | … |
| Query latency p95 | … | … | … |
| Server selection timeout | … | … | … |
| Số read operations theo member | … | … | … |

Không tự điền số “đã đo” nếu chưa thu thập trên môi trường thực. Mục tiêu là nhận diện đánh đổi giữa giảm tải primary và sức khỏe secondary.

### Bài 16 — Thiết kế tag taxonomy

Xây quy ước cho ba loại workload: giao dịch, API danh mục, báo cáo định kỳ; hệ thống có hai region. Đề xuất tag sets và giải thích tầng fallback nào phải loại bỏ để bảo vệ primary.

## 28. Gợi ý đáp án

**Bài 1:** Mode `secondary` chỉ xét secondary đủ điều kiện. Tag trên primary không làm nó trở thành secondary.

**Bài 2:** Không khớp. Những cặp trong **cùng tag set** được yêu cầu đồng thời.

**Bài 3:** Ưu tiên reporting/hanoi; sau đó reporting vùng bất kỳ; cuối cùng bất kỳ secondary đủ điều kiện. `{}` mở rộng phạm vi sang secondary app và có nguy cơ tranh tải.

**Bài 4:** Mode `secondary` với `[{purpose:"reporting"}]`, không dùng `secondaryPreferred` và không thêm fallback `{}`.

**Bài 5:** `secondaryPreferred` có thể phù hợp nếu API chấp nhận fallback primary; cần giới hạn query/concurrency để tránh dồn tải.

**Bài 6:** `nearest` xét cả primary lẫn secondary eligible. Primary RTT 5ms nằm trong nhóm latency tốt, có thể được chọn.

**Bài 7:** Giúp loại member được ước lượng stale vượt ngưỡng; không phải cam kết độ mới tuyệt đối của từng kết quả hay read-your-writes.

**Bài 8:** `majority` liên quan tới mức commit dữ liệu; secondary với majority vẫn có thể chưa áp dụng write mới nhất. Primary + majority phù hợp hơn cho đọc dữ liệu có yêu cầu cao, nhưng vẫn cần hiểu consistency contract.

**Bài 9:** Không. Hidden member không tham gia lựa chọn đọc thông thường của driver; chỉ có thể dùng direct connection trong các tình huống được hỗ trợ và phù hợp vận hành.

**Bài 10:** Có thể, nếu member healthy/eligible. `priority:0` ngăn được bầu primary, còn `hidden:true` ngăn lựa chọn đọc theo topology.

**Bài 11:** Read preference chọn node, index quyết định cách tìm dữ liệu trên node. Ứng viên: `{tenantId:1,status:1,createdAt:-1}`.

**Bài 12:** Secondary chưa áp dụng write từ primary. Có thể đọc primary cho flow ngay sau ghi, hoặc thiết kế causally consistent session với read/write concern phù hợp và chấp nhận chờ.

**Bài 13:** Node reporting trở thành primary nên không còn được mode `secondary` chọn; nếu không có reporting secondary khác, client có thể gặp server selection timeout.

**Bài 14:** Một phần query có thể không tìm được member reporting eligible ở shard thiếu tag; cần đồng bộ topology/tags của các shards và kiểm thử toàn bộ routing.

**Bài 15:** Không chỉ đo primary CPU; nếu replication lag và reporting secondary CPU tăng quá cao, giải pháp có thể chưa đạt SLO toàn hệ thống.

**Bài 16:** Giao dịch đọc primary; danh mục dùng app secondary nếu chấp nhận lag; báo cáo dùng reporting secondary strict. Chỉ thêm fallback khi mô hình tải/availability cho phép.

## 29. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Nghĩ tag tự chuyển query khỏi primary | Tags không có tác dụng nếu mode là primary | Cấu hình read preference rõ ràng |
| Dùng `secondaryPreferred` để “cấm” primary | Fallback có thể đọc primary | Dùng mode `secondary` cho offload strict |
| Dùng `nearest` và nghĩ chỉ đọc secondary | Nearest có thể chọn primary | Dùng secondary + tags |
| Gộp mọi tag vào một object dù muốn fallback | Các cặp bị yêu cầu cùng lúc | Dùng danh sách nhiều tag sets có thứ tự |
| Thêm `{}` mà không hiểu hậu quả | Có thể dùng secondary không đúng workload | Chỉ thêm fallback khi có chủ đích |
| Nghĩ đọc secondary luôn có dữ liệu mới | Replication bất đồng bộ | Xác định freshness requirement, read concern/session |
| Coi maxStalenessSeconds là hard SLA | Có thể đọc dữ liệu trễ hơn kỳ vọng nghiệp vụ | Monitor lag và chọn consistency đúng |
| Chọn threshold 5 giây không kiểm tra giới hạn | Driver/server có thể từ chối cấu hình | Tôn trọng ngưỡng tối thiểu và phiên bản |
| Gắn tag lên hidden rồi kỳ vọng driver chọn | Hidden không tham gia lựa chọn bình thường | Dùng secondary visible phù hợp |
| Nhầm priority 0 với hidden | Quy hoạch election/read sai | Phân biệt electability và visibility |
| Tạo thêm reporting read nhưng bỏ qua index | COLLSCAN chuyển từ primary sang secondary | Tối ưu query/index trước và sau offload |
| Không tính tải replication apply | Secondary tăng lag và rớt khỏi eligibility | Giám sát CPU/I/O/oplog/lag |
| Coi tags là hard security boundary | Client khác vẫn có thể truy cập theo quyền | Network/AuthZ/workload policies |
| Tin rằng hai secondary có cùng tag là chia tải 50/50 | RTT/pool/topology khiến tỷ lệ khác | Đo bằng server address/metrics |
| Dùng direct connection để test tag routing | Bỏ qua topology selection của driver | Test với URI replica set đúng cách |
| Giả định reporting node không thể lên primary | Tags không điều khiển election | Thiết kế priority/votes phù hợp |
| Thay `rs.reconfig` trên production để thử | Có thể ảnh hưởng availability/election | Lab, change review, rollback |
| Không thử khi secondary bị lỗi | Bất ngờ server timeout hoặc fallback primary | Chaos/failover test có kiểm soát |
| Áp một readPreference cho mọi repository | Flow vừa ghi có thể đọc stale | Phân policy theo use case |
| Đọc majority rồi cho rằng không stale | Majority không có nghĩa mới nhất trên secondary | Xác định causal consistency hoặc primary reads |

## 30. Câu hỏi ôn tập

**1. Tags trong replica set là gì?**

Là các cặp metadata key/value gắn với member, giúp driver chọn nhóm server theo read preference. Tags không thay đổi data placement hoặc quyền truy cập.

**2. Primary có thể mang tag không?**

Có. Nhưng mode `secondary` vẫn không chọn primary, bất kể tag có khớp hay không.

**3. Trong một tag set có hai cặp key/value, logic là AND hay OR?**

AND: member phải khớp cả hai cặp. Một danh sách nhiều tag sets biểu diễn các tầng lựa chọn theo thứ tự ưu tiên.

**4. Tag set `{}` biểu thị điều gì?**

Không thêm ràng buộc tag ở tầng fallback; có thể mở rộng lựa chọn sang những secondary trước đó bị loại bởi tag.

**5. Mode nào bảo đảm không đọc primary theo read preference trong điều kiện thông thường?**

`secondary`, vì chỉ xét secondary đủ điều kiện. Nếu không có member, query có thể thất bại chứ không tự dùng primary.

**6. Vì sao secondaryPreferred nguy hiểm với báo cáo nặng?**

Khi thiếu secondary, nó có thể fallback primary, dồn thêm tải reporting lên node xử lý giao dịch.

**7. Nearest có nghĩa là secondary có RTT thấp nhất?**

Không. Nó có thể xét cả primary và secondary, dựa trên eligibility/latency window; không nhất thiết chỉ một server với RTT thấp nhất.

**8. maxStalenessSeconds có thay thế readConcern majority không?**

Không. Một bên là bộ lọc member theo staleness ước lượng, bên kia mô tả mức commit/độ nhất quán dữ liệu được phép quan sát.

**9. Đặt maxStalenessSeconds=120 có đảm bảo read sau write thấy ngay không?**

Không. Secondary có thể chưa áp dụng write. Với read-your-writes, cần đọc primary hoặc causal consistency phù hợp.

**10. Hidden secondary có được chọn nhờ tag không?**

Không theo cơ chế read preference topology thông thường. Hidden member phục vụ mục đích vận hành riêng và có thể được truy cập qua direct connection theo điều kiện hỗ trợ.

**11. Priority:0 có khiến node không nhận read không?**

Không. Priority 0 liên quan election; nếu không hidden và eligible, secondary vẫn có thể phục vụ read.

**12. Đọc secondary có làm write nhanh gấp đôi không?**

Không. Nó chỉ có thể giảm tải một phần đọc ở primary; replication, index maintenance và ghi vẫn có chi phí.

**13. Khi tag reporting không có node khớp, mode secondary làm gì?**

Không fallback primary; driver có thể chờ trong server selection timeout rồi lỗi, nếu không có secondary đủ điều kiện.

**14. Tags có phân quyền dữ liệu theo tenant không?**

Không. Phân quyền phải thực hiện qua application query/authentication và các policy bảo mật phù hợp.

**15. Vì sao cần quan sát replication lag sau khi offload báo cáo?**

Báo cáo có thể chiếm CPU/I/O của secondary, làm replication apply chậm và dẫn tới dữ liệu stale, mất eligibility hoặc rủi ro vận hành.

**16. Tag sets có phải công cụ chia chính xác 70/30 giữa hai node không?**

Không. Chúng giới hạn/prioritize nhóm eligible; tỷ lệ query phụ thuộc latency, pool và server selection.

**17. Index có vai trò gì nếu query đã chạy trên secondary?**

Giúp secondary lọc/sort hiệu quả, giảm scan và tài nguyên. Read preference không làm query tự động có index.

**18. Khi election làm node reporting trở thành primary, tag reporting có mất không?**

Không tự mất; tag gắn với member. Nhưng mode secondary không còn chọn node đó khi nó đang là primary.

**19. Shard key có cùng chức năng với replica set member tag không?**

Không. Shard key quyết định phân phối/routing dữ liệu giữa shards; member tag hỗ trợ chọn node trong nhóm replica set theo read preference.

**20. Dùng command monitoring có ích gì?**

Giúp xác nhận địa chỉ server thực thi read, thay vì chỉ nhìn query thành công và đoán driver đã chọn đúng secondary.

## 31. Bảng cấu hình ghi nhớ

| Nhu cầu | Read preference/tag gợi ý |
|---|---|
| Đọc primary | `primary` |
| Chỉ secondary | `secondary` |
| Secondary, có thể fallback primary | `secondaryPreferred` |
| Primary trước, có thể fallback secondary | `primaryPreferred` |
| Latency-oriented, chấp nhận primary hoặc secondary | `nearest` |
| Secondary báo cáo, không fallback | `secondary` + `[{purpose:"reporting"}]` |
| Ưu tiên reporting hanoi, rồi reporting vùng khác | `secondary` + `[{purpose:"reporting",region:"hanoi"},{purpose:"reporting"}]` |
| Reporting, rồi bất kỳ secondary | `secondary` + `[{purpose:"reporting"},{}]` — cân nhắc rủi ro |
| Chỉ app secondary | `secondary` + `[{purpose:"app"}]` |
| Loại secondary có lag ước lượng cao | `maxStalenessSeconds` theo ngưỡng được hỗ trợ |
| Điều chỉnh latency window | `localThresholdMS` qua client settings/URI phù hợp |
| Xem tags trên member | `rs.conf()` |
| Xem trạng thái replica set | `rs.status()` |
| Xác minh query thực sự chọn node nào | Driver command monitoring/server logs/metrics |

## 32. Checklist triển khai production

- [ ] Đã phân loại query nào **cần primary** và query nào chịu được lag?
- [ ] Tags đã có taxonomy nhất quán về `purpose`, `region` và `zone`?
- [ ] Driver sử dụng mode `secondary` nếu thực sự cần tránh primary?
- [ ] Có hiểu `secondaryPreferred`/`primaryPreferred` fallback sang role khác trong những trường hợp nào?
- [ ] Danh sách tag sets được sắp theo **thứ tự ưu tiên** có chủ đích?
- [ ] Có tránh tầng `{}` nếu không muốn dùng secondary ngoài nhóm workload?
- [ ] Topology vẫn có đủ node/election majority khi cấu hình `priority:0` hay hidden?
- [ ] Không dùng hidden/delayed member như reporting secondary thông thường?
- [ ] Đã chọn `maxStalenessSeconds` theo nhu cầu nghiệp vụ và giới hạn phiên bản?
- [ ] Có hiểu `maxStalenessSeconds` không bảo đảm read-your-writes?
- [ ] Read concern/session/write concern có đáp ứng yêu cầu tính nhất quán?
- [ ] Driver connection dùng replica set URI và khám phá topology chính xác?
- [ ] Đã kiểm tra read query **thực sự chạy trên member nào**?
- [ ] Đã đo query plan/index, không chỉ đổi nơi thực thi?
- [ ] Có quan sát replication lag, oplog window, CPU/I/O và network?
- [ ] Có giới hạn concurrent reporting jobs, query time và retry budget?
- [ ] Đã thử tình huống không còn secondary đủ điều kiện và kiểm tra fallback?
- [ ] Nếu sharded, các shards cần thiết đều có cấu hình read tags phù hợp?
- [ ] Thay đổi `rs.reconfig` chỉ qua quy trình vận hành có kiểm tra và rollback?
- [ ] Mọi metric đã được đo trong workload đại diện, không chỉ lab ít dữ liệu?

## 33. Kết luận

**Replica set member tags** là cách mô tả những node thích hợp cho các loại truy vấn đọc khác nhau. Khi kết hợp với **read preference tag sets có thứ tự**, ứng dụng có thể ưu tiên secondary theo vùng và mục đích như `purpose:reporting` hoặc `purpose:app`, đồng thời kiểm soát fallback. Tuy nhiên, lựa chọn **mode** quyết định một ranh giới rất quan trọng: `secondary` chỉ đọc secondary và có thể thất bại khi không có node phù hợp, còn `secondaryPreferred` có thể chuyển tải về primary.

Phân tải đọc hiệu quả không chỉ là đổi cấu hình kết nối. Cần tính đến **replication lag**, độ nhất quán và read-your-writes, **latency window**, index, tài nguyên của secondary, election/failover và cách workload được giới hạn. Với báo cáo nặng, một **reporting secondary visible có tag rõ ràng, read preference secondary strict, monitoring và retry có kiểm soát** thường là mẫu dễ dự đoán hơn việc để mọi truy vấn tự do chạy trên nearest node.

Điểm kiểm chứng cuối cùng luôn là **hệ thống thực sự đọc từ member nào, trong trạng thái replication nào, với chi phí và độ trễ bao nhiêu** — không phải chỉ là một dòng `tags` trong `rs.conf()`.
