# Dựng replica set, chuyển primary và quan sát tính nhất quán

**MongoDB Replica Set** là nhóm tiến trình `mongod` cùng lưu trữ bản sao của một tập dữ liệu logic. Một thành viên giữ vai trò **primary** để nhận các thao tác ghi thông thường, còn những **secondary** sao chép và áp dụng các thao tác đã ghi từ primary. Khi primary không còn sẵn sàng, các thành viên đủ điều kiện có thể tổ chức bầu cử để chọn primary mới.

Hiểu định nghĩa chỉ là bước đầu. Khi vận hành MongoDB, người phát triển và kỹ sư cần **tự nhìn thấy** vai trò thành viên, độ trễ sao chép, phản ứng của driver khi primary đổi và sự khác nhau giữa:

- Lệnh ghi đã được primary xác nhận;
- Lệnh ghi đã được đa số thành viên xác nhận;
- Một secondary cụ thể đã áp dụng xong thay đổi;
- Client đã có thể đọc dữ liệu từ node mà mình vừa kết nối;
- Một kết quả ghi có thực sự an toàn để retry hay chưa.

Bài thực hành **“Dựng replica set, chuyển primary và quan sát tính nhất quán”** trong chương **Thực hành tổng hợp** hướng dẫn xây dựng replica set ba thành viên bằng Docker Compose, sử dụng `mongosh`, tạo dữ liệu kiểm thử, thực hiện **stepdown có kiểm soát**, quan sát cuộc bầu cử, kiểm chứng `writeConcern`, `readConcern`, `readPreference` và thử ứng dụng Java dùng MongoDB Driver. Bài cũng trình bày giới hạn của phép thử trên một máy và cách diễn giải kết quả mà không rút ra những bảo đảm MongoDB thực tế không đưa ra.

> **Phạm vi an toàn:** Toàn bộ lệnh thay đổi topology, tắt member hoặc thử failover trong bài chỉ dành cho **môi trường lab độc lập** do người học sở hữu. Không thực hiện `rs.stepDown`, `rs.reconfig`, dừng primary hoặc tắt xác thực trên production/Atlas mà không có quy trình, phê duyệt và phương án khôi phục. MongoDB replica set **không thay thế backup**.

---

## 1. Kết quả học tập

Sau khi hoàn thành, bạn có thể:

1. Giải thích vai trò primary, secondary, election, term, oplog và majority quorum.
2. Dựng ba tiến trình `mongod` trên một Docker network không công bố cổng ra bên ngoài.
3. Khởi tạo `rs0` bằng `rs.initiate()` và xác minh đã có primary.
4. Dùng `rs.status()`, `rs.conf()` và lệnh `hello` để đọc trạng thái.
5. Ghi dữ liệu với `w:1` hoặc `w:"majority"` và nhận biết sự khác nhau.
6. Đọc dữ liệu từ primary/secondary theo `readPreference` và `readConcern`.
7. Chuyển vai trò primary bằng `rs.stepDown()` trong lab.
8. Chạy lại lệnh đọc/ghi khi primary đổi; phân biệt lỗi tạm thời với dữ liệu sai.
9. Thử dừng một thành viên rồi đánh giá khả năng quorum.
10. Quan sát replication lag và giải thích vì sao trên cùng một máy có thể **không đo thấy lag**.
11. Viết Java Driver client dùng URI replica set, retryable writes và session.
12. Thiết kế test phù hợp cho tính nhất quán, không dùng một kết quả ngẫu nhiên làm kết luận tổng quát.
13. Xác định các trường hợp cần `majority`, causal consistency, transaction hoặc linearizable read.
14. Thu thập bằng chứng, lập bảng kết quả và hoàn nguyên môi trường.

## 2. Kiến trúc replica set

Một replica set ba thành viên:

```text
                    MongoDB Client
                          │
                          ▼
               Replica set discovery
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
        mongo1:27017  mongo2:27017  mongo3:27017
            │             │             │
         PRIMARY       SECONDARY     SECONDARY
            │             ▲             ▲
            └────── Oplog replication ───┘
```

Vai trò có thể thay đổi:

```text
Trước bầu cử:
  mongo1 = PRIMARY
  mongo2 = SECONDARY
  mongo3 = SECONDARY

Sau khi mongo1 step down:
  mongo1 = SECONDARY
  mongo2 = PRIMARY    (ví dụ, không bảo đảm)
  mongo3 = SECONDARY
```

Không cố định logic ứng dụng vào giả định `mongo1` luôn là primary. MongoDB Driver sẽ khám phá thành viên theo replica set URI và server responses; ứng dụng nên dùng các cơ chế này thay vì hardcode một host duy nhất cho ghi.

### 2.1. Primary

- Nhận writes thông thường của replica set.
- Ghi operations vào oplog.
- Tham gia xác nhận theo write concern.
- Có thể mất vai trò do stepdown, lỗi mạng, election hoặc thay đổi cấu hình.

### 2.2. Secondary

- Sao chép và áp dụng các thay đổi theo replication mechanism.
- Có thể phục vụ reads nếu `readPreference` cho phép.
- Có thể trở thành primary nếu đủ điều kiện và được bầu.
- Không phải mọi secondary luôn bắt kịp primary ngay lập tức.

### 2.3. Oplog

Oplog là log các thao tác phục vụ replication. Secondary theo dõi oplog và áp dụng các thao tác tương ứng. Oplog cũng liên quan tới change streams/resume windows; nếu secondary hoặc consumer tụt lại quá xa, có thể cần đồng bộ lại theo phương pháp phù hợp.

### 2.4. Heartbeat và election

Các thành viên kiểm tra tình trạng các thành viên khác và bầu primary khi cần. Election chịu ảnh hưởng bởi votes, priority, term, trạng thái đồng bộ và majority. Không dựa vào một số giây cố định để dự đoán chính xác node nào sẽ trở thành primary.

## 3. Majority quorum của ba thành viên

Với ba voting members:

\[
\text{majority votes} = \left\lfloor \frac{3}{2} \right\rfloor + 1 = 2
\]

Điều này dẫn tới:

| Tình huống | Voting members liên lạc được | Có thể giữ/chọn primary? |
|---|---:|---|
| Cả ba khỏe | 3 | Có |
| Một voting member ngừng | 2 | Thường có, nếu đủ điều kiện bầu |
| Hai voting members ngừng | 1 | Không đủ majority |
| Hai thành viên ở một partition, một thành viên ở partition khác | 2 và 1 | Phía hai thành viên có thể duy trì bầu cử; phía một thành viên không |
| Ba members vẫn online nhưng không ai đủ điều kiện primary | Có thể đủ votes | Chưa chắc có primary |

**Quorum để bầu cử và xác nhận ghi không hoàn toàn đồng nghĩa với việc mọi thành viên đã nhận dữ liệu.** Cần đọc thêm về voting members, data-bearing voting members và write concern majority semantics theo phiên bản/thiết lập.

### 3.1. Vì sao không dùng hai thành viên để kỳ vọng HA đầy đủ?

Replica set gồm hai voting data-bearing members cần cả hai cho majority. Khi một node mất, node còn lại không đủ phiếu để bầu primary. Ba voting members có thể chịu mất một voting member theo topology phù hợp.

### 3.2. Arbiter không chứa dữ liệu

Một arbiter có thể bỏ phiếu bầu nhưng không lưu bản sao dữ liệu. Nó **không** thay thế một data-bearing secondary cho durability, và những cấu hình có arbiter mang theo trade-off về majority write concern và transactions. Lab dùng **ba data-bearing members** để quan sát đầy đủ replication.

## 4. Chuẩn bị môi trường

Yêu cầu:

- Máy có Docker Engine/Docker Desktop và Docker Compose plugin.
- Terminal hỗ trợ `docker compose` (Windows PowerShell, macOS/Linux shell).
- Đủ CPU/RAM/disk để chạy ba tiến trình MongoDB.
- Không có chính sách cấm chạy các containers này trên máy đang sử dụng.
- Quyền tạo project directory và Docker volumes.
- Có thể chạy `mongosh` **bên trong container**; không bắt buộc cài `mongosh` trên host.
- Internet/container registry access để tải image lần đầu.

Bài dùng image **`mongo:8.0`** nhằm mô tả cú pháp MongoDB 8.0 phổ biến. Đây là **phiên bản được ghim cho ví dụ**, không phải khẳng định rằng nó là phiên bản mới nhất hoặc phù hợp production hiện tại. Nếu đổi image tag, phải kiểm tra compatibility và nâng cấp dữ liệu theo đường hỗ trợ, không thay major version tùy tiện với volumes cũ.

### 4.1. Mục tiêu kết nối

Các containers giao tiếp qua DNS nội bộ:

```text
mongo1:27017
mongo2:27017
mongo3:27017
```

Không công bố `ports:` ra host trong Compose file. Cách này hạn chế khả năng kết nối ngoài Docker network, nhưng **không phải biện pháp bảo mật hoàn chỉnh**.

### 4.2. Giới hạn bảo mật của lab

Để tập trung vào replication, ví dụ không bật authentication/TLS nội bộ. **Chỉ dùng trong Docker lab cô lập**; tuyệt đối không đặt cấu hình này trên mạng truy cập công khai hoặc production. Nếu áp dụng trong môi trường thực, cần internal authentication (keyfile hoặc x.509 theo thiết kế), TLS, RBAC, secret management, network restrictions, monitoring và backup.

## 5. Tạo `compose.yaml` cho ba `mongod`

Trong một thư mục lab mới, tạo:

```yaml
services:
  mongo1:
    image: mongo:8.0
    hostname: mongo1
    command:
      - mongod
      - --replSet
      - rs0
      - --bind_ip_all
      - --port
      - "27017"
    volumes:
      - mongo1_data:/data/db
    networks:
      - rs_lab

  mongo2:
    image: mongo:8.0
    hostname: mongo2
    command:
      - mongod
      - --replSet
      - rs0
      - --bind_ip_all
      - --port
      - "27017"
    volumes:
      - mongo2_data:/data/db
    networks:
      - rs_lab

  mongo3:
    image: mongo:8.0
    hostname: mongo3
    command:
      - mongod
      - --replSet
      - rs0
      - --bind_ip_all
      - --port
      - "27017"
    volumes:
      - mongo3_data:/data/db
    networks:
      - rs_lab

networks:
  rs_lab:
    driver: bridge

volumes:
  mongo1_data:
  mongo2_data:
  mongo3_data:
```

Điểm cần hiểu:

- Mỗi service chạy `mongod` với cùng replica set name `rs0`.
- Mỗi member có **volume riêng** để giữ dữ liệu.
- Hostnames `mongo1`, `mongo2`, `mongo3` phải được các thành viên tự phân giải trong network.
- Không map port `27017` ra máy ngoài.
- Compose **chỉ tạo tiến trình**; chưa khởi tạo replica set.
- `--bind_ip_all` cho phép kết nối trên network interfaces của container; vì không có auth, lab phải cách ly cẩn thận.

### 5.1. Không dùng một volume chung

Sai:

```yaml
volumes:
  - same_data:/data/db
```

cho cả ba members. Mỗi `mongod` cần data directory riêng. Dùng chung storage files giữa các tiến trình không phải replication, có thể phá dữ liệu.

### 5.2. Hostname ổn định

Replica set config lưu `host` cho từng member. Nếu thay hostname hoặc network mà không có quy trình reconfiguration, các thành viên và clients có thể không kết nối đúng.

### 5.3. Vì sao không map ports?

Nếu map cả ba cổng:

```text
localhost:27017
localhost:27018
localhost:27019
```

nhưng replica set vẫn quảng bá `mongo1:27017`, `mongo2:27017`..., một Java client chạy **trên host** có thể không phân giải được các tên `mongo1`, `mongo2`, `mongo3`, dẫn tới lỗi server selection.

Bài chọn client chạy trong Docker network qua `docker compose exec`. Nếu muốn Java client trên host, phải chủ động thiết kế DNS/host mappings/tunnel phù hợp và bảo đảm mọi advertised member address đều reachable từ client.

## 6. Khởi động các containers

Trong thư mục chứa `compose.yaml`:

```bash
docker compose up -d
```

Xem trạng thái:

```bash
docker compose ps
```

Kiểm tra MongoDB trên từng member:

```bash
docker compose exec mongo1 mongosh --quiet --eval "db.adminCommand({ping: 1})"
docker compose exec mongo2 mongosh --quiet --eval "db.adminCommand({ping: 1})"
docker compose exec mongo3 mongosh --quiet --eval "db.adminCommand({ping: 1})"
```

Expected khi tiến trình đã sẵn sàng:

```javascript
{ ok: 1 }
```

Nếu lệnh chạy quá sớm hoặc container chưa khởi động xong, có thể gặp connection refused; thử lại sau khi xác minh `docker compose ps` và logs. Không đổi cấu hình bảo mật hay xóa volumes để chữa lỗi kết nối chưa điều tra.

### 6.1. Đọc logs

```bash
docker compose logs --tail=80 mongo1
docker compose logs --tail=80 mongo2
docker compose logs --tail=80 mongo3
```

Cảnh báo về authentication disabled có thể xuất hiện trong lab. Điều này **không được xem là cấu hình an toàn để đưa vào production**.

### 6.2. Trước khi `rs.initiate()`

Một tiến trình có `--replSet rs0` chưa được khởi tạo chưa có primary. Khi truy vấn trạng thái replica set có thể thấy thông báo chưa init. Đây là kỳ vọng ban đầu, không phải sự cố mất dữ liệu.

## 7. Khởi tạo replica set bằng `rs.initiate`

Mở `mongosh` trực tiếp trên node đầu:

```bash
docker compose exec mongo1 mongosh
```

Trong mongosh:

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    {
      _id: 0,
      host: "mongo1:27017",
      priority: 2,
      votes: 1
    },
    {
      _id: 1,
      host: "mongo2:27017",
      priority: 1,
      votes: 1
    },
    {
      _id: 2,
      host: "mongo3:27017",
      priority: 1,
      votes: 1
    }
  ]
});
```

Kết quả thành công thường có `ok:1`. Cuộc bầu cử có thể cần thời gian; không kết luận thất bại chỉ vì `hello` ngay lập tức chưa báo primary.

### 7.1. Chỉ init một lần

Không gọi `rs.initiate()` trên mỗi member. Một replica set chỉ cần được khởi tạo bằng cấu hình đã chỉ định; các members khác gia nhập theo config đó.

### 7.2. Vì sao `priority:2` cho mongo1?

Để trình bày rằng một member có election priority cao hơn các members còn lại. Priority có thể ảnh hưởng khả năng được bầu/ưu tiên primary, nhưng **không có nghĩa mọi thời điểm mongo1 chắc chắn là primary** khi vừa có stepdown hoặc khi node không đủ điều kiện.

### 7.3. `_id` và `host`

`_id` ở đây là **member index trong replica set config**, không phải ID dữ liệu trong collection. Mỗi member phải có host hợp lệ và duy nhất theo cấu hình.

### 7.4. DNS trong replica set

Mọi member cần liên lạc được với hostnames trong config. Driver sau khi kết nối seed sẽ khám phá danh sách hostnames đó. Đây là lý do dùng IP tạm hoặc tên chỉ phân giải được trên một máy có thể khiến replica set hoạt động nửa vời.

## 8. Xác minh đã có primary

Trong mongosh:

```javascript
rs.status();
```

Quan sát:

- `set`: `rs0`;
- `members`: ba member được khai báo;
- `stateStr`: `PRIMARY` hoặc `SECONDARY`;
- `health`;
- `term`;
- `optime`/`optimeDate`;
- Thông tin election và replication;
- Trường metadata có thể khác theo server version.

Một cách hiển thị gọn:

```javascript
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr,
  health: m.health,
  optimeDate: m.optimeDate
}));
```

Kết quả ví dụ:

```javascript
[
  {
    name: "mongo1:27017",
    state: "PRIMARY",
    health: 1,
    optimeDate: ISODate("2026-11-14T04:00:00Z")
  },
  {
    name: "mongo2:27017",
    state: "SECONDARY",
    health: 1,
    optimeDate: ISODate("2026-11-14T04:00:00Z")
  },
  {
    name: "mongo3:27017",
    state: "SECONDARY",
    health: 1,
    optimeDate: ISODate("2026-11-14T04:00:00Z")
  }
]
```

Đây chỉ là minh họa: tên primary và timestamps thực tế phụ thuộc trạng thái runtime.

### 8.1. Dùng `hello`

```javascript
db.adminCommand({ hello: 1 });
```

Những field thường hữu ích:

```text
setName
isWritablePrimary
secondary
hosts
primary
me
electionId / topologyVersion (khi xuất hiện)
```

`isWritablePrimary:true` cho biết endpoint đó hiện coi mình là writable primary. **Đó là trạng thái tại thời điểm trả lời**, có thể đổi ngay sau response.

### 8.2. Xác minh từng member

Từ terminal, chạy:

```bash
docker compose exec mongo1 mongosh --quiet --eval "db.adminCommand({hello: 1})"
docker compose exec mongo2 mongosh --quiet --eval "db.adminCommand({hello: 1})"
docker compose exec mongo3 mongosh --quiet --eval "db.adminCommand({hello: 1})"
```

Vì `mongosh` ở đây kết nối local mặc định vào từng node, lệnh `hello` giúp xem từng node tự nhận vai trò gì.

### 8.3. `rs.conf()` khác `rs.status()`

```javascript
rs.conf();
```

- `rs.conf()` mô tả **cấu hình mong muốn**: members, votes, priority, settings.
- `rs.status()` phản ánh **trạng thái runtime**: ai primary, ai secondary, health, lag, election details.

Không dùng `priority` trong `rs.conf()` làm bằng chứng về primary hiện tại.

## 9. Client URI đúng cho replica set

Trong Docker network:

```text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/lab?replicaSet=rs0
```

Mở shell qua một container:

```bash
docker compose exec mongo1 mongosh "mongodb://mongo1:27017,mongo2:27017,mongo3:27017/lab?replicaSet=rs0"
```

URI này cung cấp nhiều **seed hosts** và replica set name. Driver sẽ khám phá topology và định tuyến writes tới primary hiện hành theo semantics tương ứng.

### 9.1. Seed list không phải danh sách primary cố định

Một host trong seed list có thể là secondary. Client vẫn dùng cluster discovery để tìm writable primary. Không giả định host đầu trong URI là primary.

### 9.2. `directConnection=true`

Nếu muốn **chủ động quan sát một node cụ thể**, có thể dùng:

```text
mongodb://mongo2:27017/lab?directConnection=true&readPreference=secondary
```

Đây là một cách kết nối trực tiếp tới member được chỉ định; không nên dùng như URI chính của một ứng dụng cần tự failover theo replica set.

### 9.3. Không dùng `localhost` nhầm không gian mạng

Trong container `mongo1`, `localhost:27017` là chính container đó, không phải host Windows/macOS. Trong container Java riêng, `localhost:27017` là Java container, không phải MongoDB. Dùng service DNS names từ Compose network.

## 10. Tạo collection thử và dữ liệu chuẩn

Ở shell đã kết nối bằng URI replica set:

```javascript
const labDb = db.getSiblingDB("lab");

labDb.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  {
    unique: true,
    name: "uq_tenant_order_no"
  }
);

labDb.orders.insertOne({
  _id: "ORD-001",
  tenantId: "T-01",
  orderNo: "001",
  status: "CREATED",
  amountMinor: NumberLong("250000"),
  createdAt: new Date()
});
```

Kiểm tra:

```javascript
labDb.orders.findOne({ _id: "ORD-001" });
```

### 10.1. Vì sao dùng ID cố định?

Trong bài kiểm thử failover/retry, nếu mỗi retry tạo `_id` mới, bạn có thể vô tình tạo nhiều documents và khó phân biệt duplicate business command với lỗi replication. ID cố định hỗ trợ đối soát.

### 10.2. Unique constraint

Index `(tenantId,orderNo)` ngăn trùng business order number theo tenant. Nó không tự làm toàn bộ workflow idempotent; vẫn cần key/request identity và xử lý lỗi duplicate phù hợp.

## 11. Oplog và đường truyền dữ liệu tới secondary

Luồng ghi logic:

```text
Client writes to PRIMARY
          │
          ▼
Primary applies change
          │
          ▼
Change recorded in oplog
          │
          ├── Secondary A fetches/applies
          └── Secondary B fetches/applies
          │
          ▼
Majority commit / read visibility according to settings
```

Các secondary có thể áp dụng nhanh hoặc chậm theo network/disk/CPU tải. Trong lab một máy, các member thường có latency rất thấp.

### 11.1. Kiểm tra thành viên đã bắt kịp chưa

```javascript
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr,
  optime: m.optime,
  optimeDate: m.optimeDate
}));
```

Khác biệt `optimeDate` là dấu hiệu quan sát, không phải phép đo tổng quát mọi loại lag. Thành viên đang RECOVERING/STARTUP2 có thể không phục vụ reads bình thường.

### 11.2. `rs.printSecondaryReplicationInfo()`

Trong mongosh ở môi trường phù hợp:

```javascript
rs.printSecondaryReplicationInfo();
```

Lệnh tiện ích có thể hiển thị thông tin lag secondary. Cấu trúc/output tùy shell/server version.

### 11.3. Không sửa trực tiếp oplog

Oplog là cấu trúc replication nội bộ. Không cập nhật/đọc ghi tùy tiện `local.oplog.rs` để “đồng bộ” dữ liệu. Với mục tiêu học tập, dùng các lệnh quan sát được hỗ trợ.

## 12. Write concern: ghi tới đâu mới được xác nhận?

MongoDB cho phép chỉ định điều kiện xác nhận ghi.

Các mức thường gặp:

| Write concern | Ý nghĩa khái quát | Trade-off |
|---|---|---|
| `w:0` | Không đợi ACK từ server theo semantics | Client không biết write thực sự thành công hay không |
| `w:1` | Primary xác nhận operation | Độ trễ ACK thấp hơn trong nhiều trường hợp, nhưng write có thể chưa được majority xác nhận |
| `w:2` | Hai data-bearing members xác nhận theo điều kiện hỗ trợ | Phụ thuộc topology, khác ý nghĩa semantic majority khi cấu hình thay đổi |
| `w:"majority"` | Đợi điều kiện majority của replica set theo quy tắc MongoDB | Chống rủi ro rollback tốt hơn, có thể chờ lâu hơn |
| `j:true` | Yêu cầu journal acknowledgment theo semantics phiên bản | Bổ sung điều kiện durability, cần đọc cấu hình |

Sự khác nhau đặc biệt quan trọng khi xảy ra primary failover.

### 12.1. `w:1` không có nghĩa chắc chắn mất dữ liệu

Đa số writes có thể replicate nhanh và không bị rollback. Nhưng **không có bảo đảm** rằng mọi `w:1` acknowledged write đã được majority xác nhận.

### 12.2. `w:"majority"` không có nghĩa tất cả secondary đã áp dụng

Với ba voting data-bearing members, majority thường là hai thành viên; member thứ ba có thể còn tụt. Một secondary bạn đọc ngay sau đó vẫn có thể chưa thấy write.

### 12.3. Journal/durability có các điều kiện phiên bản và cấu hình

Không diễn giải majority ACK như lời hứa vượt mọi lỗi phần cứng/tổ hợp cấu hình. Đọc `writeConcernMajorityJournalDefault`, journaling và tài liệu topology/version đang dùng khi cần bảo đảm durability cụ thể.

## 13. Thực hành ghi với `w:1`

Trong mongosh theo URI replica set:

```javascript
const wcOne = labDb.orders.withWriteConcern({
  w: 1,
  wtimeout: 5000
});

const r1 = wcOne.insertOne({
  _id: "WC-ONE-001",
  tenantId: "T-01",
  orderNo: "WC-ONE-001",
  amountMinor: NumberLong("100"),
  createdAt: new Date()
});

printjson(r1);
```

`wtimeout` có ý nghĩa chờ acknowledgment theo write concern trong phạm vi hỗ trợ. Với `w:1`, một write bình thường trên primary có thể được xác nhận rất nhanh.

### 13.1. Quan sát sau ghi

```javascript
labDb.orders.findOne({ _id: "WC-ONE-001" });
```

Đọc trên primary thường thấy write đã được ghi. Điều này **không tự chứng minh** document đã được majority acknowledge tại thời điểm primary ACK cho `w:1`.

### 13.2. Không cố tạo rollback trên dữ liệu quan trọng

Để kiểm thử rủi ro của `w:1`, chỉ dùng records giả. Một cách cưỡng ép network partition/rollback có thể tạo tình huống phá dữ liệu; bài thực hành chính ưu tiên stepdown có kiểm soát để quan sát election trước.

## 14. Thực hành ghi với `w:"majority"`

```javascript
const wcMajority = labDb.orders.withWriteConcern({
  w: "majority",
  wtimeout: 10000
});

const r2 = wcMajority.insertOne({
  _id: "WC-MAJ-001",
  tenantId: "T-01",
  orderNo: "WC-MAJ-001",
  amountMinor: NumberLong("200"),
  createdAt: new Date()
});

printjson(r2);
```

Nếu được xác nhận thành công, operation đã đáp ứng write concern được yêu cầu.

### 14.1. So sánh thời gian

Bạn có thể đo xấp xỉ elapsed time bằng `Date.now()` trong shell:

```javascript
let started = Date.now();

wcMajority.updateOne(
  { _id: "WC-MAJ-001" },
  { $set: { marker: "majority-check" } }
);

print("Elapsed ms: " + (Date.now() - started));
```

Lặp lại thử nghiệm với các mức write concern và số mẫu đủ lớn. Trên Docker cùng máy, chênh lệch có thể rất nhỏ hoặc bị che bởi scheduler/cache/network, nên **không dùng một lệnh làm benchmark hiệu năng**.

### 14.2. Khi majority không sẵn sàng

Nếu hai members không thể xác nhận theo yêu cầu, `w:"majority"` có thể chờ đến `wtimeout` hoặc gặp lỗi theo điều kiện thực tế. **Write concern error không nhất thiết có nghĩa thay đổi chưa xảy ra trên primary.** Cần kiểm tra trạng thái theo ID/idempotency trước retry.

## 15. Read preference: đọc ở thành viên nào?

`readPreference` ảnh hưởng node được chọn cho read.

| Mode | Ý nghĩa | Hướng sử dụng |
|---|---|---|
| `primary` | Đọc từ primary | Mặc định phổ biến khi cần trạng thái hiện hành |
| `primaryPreferred` | Ưu tiên primary, có fallback khi thiếu primary theo semantics | Cần chấp nhận khác biệt staleness |
| `secondary` | Đọc từ secondary | Offload reads/analytics nếu chấp nhận lag |
| `secondaryPreferred` | Ưu tiên secondary, fallback primary | Trade-off giữa availability và freshness |
| `nearest` | Chọn node phù hợp theo latency window | **Không bảo đảm dữ liệu mới nhất** |

### 15.1. `nearest` không đồng nghĩa "đúng nhất"

Một secondary gần client có thể trả lời nhanh nhưng lag so với primary. Tốc độ mạng không quyết định recency của dữ liệu.

### 15.2. Read preference khác read concern

- `readPreference` hỏi **đọc ở node nào**.
- `readConcern` hỏi **mức bảo đảm về trạng thái dữ liệu được đọc**.

Một `readConcern:"majority"` trên secondary không tự ép secondary đó bắt kịp write mới nhất theo thời gian thực.

## 16. Đọc trực tiếp trên secondary

Từ terminal:

```bash
docker compose exec mongo2 mongosh "mongodb://mongo2:27017/lab?directConnection=true&readPreference=secondary"
```

Trong shell:

```javascript
db.adminCommand({ hello: 1 });
db.getSiblingDB("lab").orders.findOne({
  _id: "WC-MAJ-001"
});
```

Nếu `mongo2` đang SECONDARY, cấu hình `readPreference=secondary` cho phép chạy thử read trên nó.

### 16.1. Nếu mongo2 lại là primary?

Sau stepdown, vai trò có thể thay đổi. Kết nối trực tiếp một node với read preference secondary khi nó đang primary có thể không được driver chọn cho read. Dùng `hello` và chọn đúng member còn SECONDARY thay vì sửa dữ liệu.

### 16.2. Không xem “đã thấy” là một định luật về lag

Nếu đọc vừa ghi trên secondary và kết quả đã có, chỉ chứng minh **node đó đã kịp áp dụng trong lần test này**. Điều đó không chứng minh secondary luôn đồng bộ tức thời.

### 16.3. Đọc theo URI toàn replica set

Trong shell URI nhiều hosts:

```javascript
db.getMongo().setReadPref("secondary");
db.getSiblingDB("lab").orders.findOne({
  _id: "WC-MAJ-001"
});
```

Để quay về:

```javascript
db.getMongo().setReadPref("primary");
```

Khi cần thấy chính xác node phục vụ read, có thể dùng command monitoring/client logging phù hợp, hoặc kết nối trực tiếp member trong lab. Không suy ra node từ kết quả bản ghi.

## 17. Read concern: local, majority, snapshot, linearizable

Các mức thường gặp:

| Read concern | Ý nghĩa chính | Lưu ý |
|---|---|---|
| `local` | Đọc dữ liệu local hiện có trên member theo semantics server | Có thể quan sát dữ liệu chưa majority committed trên một số bối cảnh |
| `majority` | Đọc dữ liệu đã được majority committed theo semantics MongoDB | Không tự tạo read-your-writes khi đổi arbitrary node |
| `snapshot` | Đọc từ snapshot nhất quán theo điều kiện và scope hỗ trợ | Dùng với transaction hoặc snapshot read API thích hợp |
| `linearizable` | Mức bảo đảm mạnh cho single-document reads trên primary theo điều kiện | Có chi phí, yêu cầu phù hợp, không dùng trên secondary |
| `available` | Mức đọc ưu tiên availability trong những ngữ cảnh hỗ trợ | Có trade-off consistency, đặc biệt trong sharded setting |

Không nhầm **write concern**, **read concern** và **read preference**.

### 17.1. Majority read không bằng current latest

Giả sử majority write đã được xác nhận bởi mongo1 và mongo2, trong khi mongo3 chưa catch up. Read majority trên mongo3 vẫn có thể trả một snapshot cũ mà mongo3 đã áp dụng, không bắt buộc ngay lập tức thấy write mới.

### 17.2. Snapshot không tự bao trùm toàn job

Một transaction/snapshot read có scope, thời gian và điều kiện hỗ trợ riêng. Chạy nhiều `find()` rời rạc với read concern majority không mặc nhiên tạo một ảnh dữ liệu chung bất biến cho cả job nhiều giờ.

### 17.3. Linearizable không là default khuyến nghị cho mọi query

Cần hiểu latency, availability và yêu cầu chỉ hỗ trợ các thao tác/điều kiện nhất định. Với đa số web applications, kết hợp majority, causal sessions, CAS và transaction khi cần có thể phù hợp hơn việc áp linearizable cho mọi read.

## 18. Thử majority read trên secondary

Trong shell secondary trực tiếp, nếu command/mongosh hỗ trợ API:

```javascript
const secondaryLab = db.getSiblingDB("lab");
secondaryLab.getCollection("orders")
  .find({ _id: "WC-MAJ-001" })
  .readConcern("majority");
```

Đoạn trên minh họa ý định; `mongosh` cursor fluent API có thể khác theo phiên bản. Một cách đáng tin hơn là **đặt read concern ở URI hoặc driver/collection API**, ví dụ trong Java:

```java
MongoCollection<Document> secondaryOrders =
    db.getCollection("orders")
      .withReadPreference(ReadPreference.secondary())
      .withReadConcern(ReadConcern.MAJORITY);
```

Sau đó đọc qua collection đó với đúng Java Driver version.

### 18.1. Không bắt buộc ép hiện ra lag

Nếu kết quả không cho thấy chênh lệch trên một máy, ghi nhận `NOT OBSERVED` thay vì cho phép student tự kết luận “MongoDB không có replication lag”. Một lab đúng còn phải hiểu **những gì nó không thể chứng minh**.

## 19. Causal consistency: đọc thấy tác động của mình

Một phiên làm việc có tính nhân quả (*causally consistent session*) giúp duy trì những quan hệ thứ tự, như **read-your-writes**, dưới điều kiện được tài liệu MongoDB hỗ trợ, bao gồm dùng write concern `"majority"` và read concern `"majority"` cho các thao tác liên quan.

Ý tưởng:

```text
Client session S
     │
     ├── Write order = PAID (majority)
     │
     └── Read order from secondary
                │
                ▼
         Wait/coordinate causal point
         before returning suitable result
```

### 19.1. Causal session không ép mọi client khác thấy ngay

Một session hỗ trợ causal ordering cho operations của **session đó** theo điều kiện, không phải một global real-time view cho mọi secondary và mọi ứng dụng.

### 19.2. Causal consistency không tự sửa dữ liệu producer sai

Nếu một service khác ghi đè order bằng logic không có CAS, session của bạn không ngăn business race. Cần optimistic concurrency/transaction cho invariants.

### 19.3. Session phải dùng tuần tự

MongoDB Java Driver `ClientSession` không được dùng đồng thời vô điều kiện từ nhiều threads. Một session cho workflow liên quan, giữ đúng lifecycle; đóng sau khi dùng.

## 20. Thử ghi đồng thời để hiểu atomicity

Một document:

```javascript
{
  _id: "COUNTER-1",
  count: NumberLong("0"),
  revision: NumberLong("0")
}
```

Tạo:

```javascript
labDb.counters.insertOne({
  _id: "COUNTER-1",
  count: NumberLong("0"),
  revision: NumberLong("0")
});
```

Cập nhật nguyên tử:

```javascript
labDb.counters.updateOne(
  { _id: "COUNTER-1" },
  {
    $inc: {
      count: NumberLong("1"),
      revision: NumberLong("1")
    }
  }
);
```

Nếu nhiều workers cùng gọi `$inc` hợp lệ, mỗi update thành công trên một document được thực hiện nguyên tử theo semantics của MongoDB.

### 20.1. Đọc rồi `$set` có thể mất cập nhật

Sai:

```text
Worker A read count = 10
Worker B read count = 10
Worker A set count = 11
Worker B set count = 11
```

Dù hai updates đều atomic, kết quả là 11 thay vì 12. Giải pháp có thể là `$inc` hoặc CAS với `revision`, tùy business semantics.

### 20.2. Replica set không chữa race trong application logic

Replicas duy trì bản sao dữ liệu; chúng không tự biến read-modify-write ở hai lệnh khác nhau thành operation nguyên tử.

## 21. Atomic update và consistency giữa các document

Giả sử checkout:

```text
orders.insertOne(order)
inventory.updateOne(decrement)
payment_requests.insertOne(request)
```

Nếu ba commands chạy riêng, chúng có thể thành công một phần.

### 21.1. Khi nào dùng transaction?

Khi business yêu cầu cả ba MongoDB documents cùng commit/abort và topology hỗ trợ:

```text
MongoDB transaction
   ├── Insert order
   ├── Reserve stock
   └── Insert outbox payment request
      COMMIT or ABORT
```

### 21.2. Replica set là điều kiện nền cho transactions

Multi-document transactions có thể hoạt động trên replica sets với những yêu cầu version/topology phù hợp. Một lab replica set ba data-bearing nodes là nền tảng để thử transaction behavior.

### 21.3. Không gọi external payment API trong transaction

MongoDB transaction không làm cuộc gọi HTTP tới payment provider atomic cùng database. Dùng saga/outbox/idempotency/reconciliation.

## 22. Transaction ngắn với `mongosh`

Trong shell URI replica set:

```javascript
const session = db.getMongo().startSession();

try {
  const sdb = session.getDatabase("lab");

  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  sdb.tx_demo.insertOne({
    _id: "TX-001",
    value: "first"
  });

  sdb.tx_demo.insertOne({
    _id: "TX-002",
    value: "second"
  });

  session.commitTransaction();
} catch (e) {
  try {
    session.abortTransaction();
  } catch (ignored) {
    // Không che lỗi gốc; log theo chính sách.
  }
  throw e;
} finally {
  session.endSession();
}
```

Ví dụ cần môi trường sạch hoặc IDs chưa tồn tại. Production phải có retry handling cho transient transaction errors và unknown commit results theo tài liệu driver/shell version.

### 22.1. Quan sát sau commit

```javascript
labDb.tx_demo.find({
  _id: { $in: ["TX-001", "TX-002"] }
});
```

Trên một transaction đã commit thành công, hai inserts cùng được commit theo transaction semantics; không có trạng thái cuối cùng chỉ có TX-001 do lỗi TX-002 nếu transaction đã abort đúng.

### 22.2. Transaction và replication lag

Commit majority không buộc mọi secondary đã bắt kịp ngay. Nếu đọc từ một secondary bất kỳ sau commit mà thiếu kết quả, cần xét read preference/concern/causal session, không kết luận transaction bị “nửa commit”.

## 23. Đo replication lag trong bài thực hành

Trước tiên tạo nhiều write nhỏ:

```javascript
const batch = [];

for (let i = 0; i < 1000; i++) {
  batch.push({
    insertOne: {
      document: {
        _id: "LAG-" + i,
        tenantId: "T-LAB",
        n: i,
        createdAt: new Date()
      }
    }
  });
}

labDb.events.bulkWrite(batch, { ordered: false });
```

Sau đó quan sát:

```javascript
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr,
  optimeDate: m.optimeDate
}));
```

### 23.1. Không phải lúc nào cũng quan sát được lag

Cả ba instances chạy trên cùng máy, network rất gần, documents nhỏ và CPU rảnh có thể khiến mọi secondary áp dụng gần như tức thời. Điều này không vô hiệu hóa thiết kế consistency test.

### 23.2. Tránh làm server quá tải để “chứng minh” lag

Không insert hàng chục triệu documents hoặc tạo CPU stress không kiểm soát trên máy dùng chung. Thử nghiệm có thể dừng ở 1.000 records và ghi nhận kết quả giới hạn.

### 23.3. So sánh timestamps là quan sát gần đúng

`optimeDate`/replication info không phải phép đo duy nhất của read freshness, và timestamps có độ phân giải/semantics riêng. Với các hệ thống có sharding hoặc event processing, phải dùng watermark/cluster time phù hợp.

## 24. Chuẩn bị kiểm thử chuyển primary

Trước failover:

1. Xác nhận ba thành viên đều ở trạng thái `PRIMARY` hoặc `SECONDARY` hợp lệ.
2. Xác nhận có đúng một primary.
3. Kiểm tra secondary không tụt nghiêm trọng.
4. Ghi nhận `rs.status()`, `rs.conf()` và `hello`.
5. Chuẩn bị một client dùng **replica set URI**.
6. Ghi nhận giá trị `w`/`readConcern` của các writes cần quan sát.
7. Không thực hiện failover khi có thao tác dữ liệu quan trọng ngoài lab.
8. Có cách đưa member đã dừng trở lại.

### 24.1. Không giả định mongo1 còn là primary

Trong ví dụ init, priority mongo1 cao hơn, nhưng sau thời gian chạy hoặc thử failover trước đó, hãy **quan sát runtime** để chọn node hiện là primary.

### 24.2. Stepdown khác kill process

`rs.stepDown()` yêu cầu primary nhường vai trò theo lệnh quản trị, với các điều kiện và thời gian chờ thích hợp. `docker compose stop` là dừng tiến trình/container. Cả hai có thể dẫn tới election nhưng biểu hiện, thời điểm và tác động khác.

## 25. Chuyển primary với `rs.stepDown()`

**Chỉ trong lab.** Kết nối bằng shell URI replica set (định tuyến đến primary cho command thích hợp), rồi xác minh:

```javascript
db.adminCommand({ hello: 1 });
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr
}));
```

Nếu shell đang ở primary thực sự, chạy:

```javascript
rs.stepDown(60, 10);
```

Giải thích tham số theo helper mongosh:

- `60`: khoảng thời gian node hiện tại tránh giữ vai trò primary sau stepdown.
- `10`: khoảng thời gian chờ secondary bắt kịp theo logic stepdown được hỗ trợ.

Hãy kiểm tra signature `rs.stepDown()` đúng MongoDB/mongosh version đang dùng. Nếu không có secondary đủ điều kiện, **stepdown không cưỡng ép** có thể từ chối; không thêm `force:true` tùy tiện chỉ để thấy primary đổi.

### 25.1. Lệnh có thể ngắt kết nối

Khi primary nhường vai trò, lệnh shell có thể trả thông báo lỗi kết nối/`NotWritablePrimary` do node vừa mất chức năng primary. Đây là tác động có thể dự kiến trong failover, cần nhìn **trạng thái replica set sau đó** thay vì chỉ đọc một dòng shell.

### 25.2. Có thể cần mở shell mới

Từ terminal:

```bash
docker compose exec mongo2 mongosh "mongodb://mongo1:27017,mongo2:27017,mongo3:27017/lab?replicaSet=rs0"
```

Hoặc dùng `mongo1` container làm nơi chạy client; **container từ đó gọi shell không quyết định primary của cluster**.

### 25.3. Xác minh primary mới

```javascript
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr,
  health: m.health
}));

db.adminCommand({ hello: 1 });
```

Expected là có **một primary mới đủ điều kiện** nếu election thành công. Primary mới có thể là mongo2 hoặc mongo3; không viết assert rằng chắc chắn mongo2 được chọn.

## 26. Timeline chuyển primary

Ghi vào bảng thực hành:

| Thời điểm | Quan sát | Ý nghĩa |
|---|---|---|
| T0 | mongo1 là primary (ví dụ) | Trạng thái trước |
| T1 | Gửi `rs.stepDown(60,10)` | Yêu cầu nhường vai trò |
| T2 | Client nhận lỗi hoặc reconnect | Cửa sổ failover |
| T3 | `rs.status()` có primary mới | Election hoàn tất |
| T4 | Ghi mới với replica set URI thành công | Driver định tuyến được tới primary |
| T5 | Kiểm tra write majority trước đó | Đối soát dữ liệu |
| T6 | Node cũ về secondary | Topology ổn định |

Lưu timestamp UTC, status và error labels. **Khoảng T1→T3 không phải số đo election time tuyệt đối** nếu client polling, shell startup và monitoring interval góp phần vào chênh lệch.

### 26.1. Vì sao primary có thể đổi lại sau đó?

Member có priority cao hơn có thể được ưu tiên bầu lại trong điều kiện phù hợp sau thời gian stepdown/ổn định. Không coi topology ngay sau T3 là bất biến.

### 26.2. `electionId` và term

Replica set có term và metadata bầu cử để sắp xếp leadership theo giao thức. Quan sát chúng giúp thấy election đã diễn ra, nhưng không dùng chúng làm business order ID hoặc tự chỉnh sửa metadata.

## 27. Test đọc/ghi sau election

Sau khi shell kết nối tới replica set URI:

```javascript
const after = db.getSiblingDB("lab");

after.orders.insertOne({
  _id: "AFTER-FAILOVER-001",
  tenantId: "T-01",
  orderNo: "AFTER-FAILOVER-001",
  amountMinor: NumberLong("300"),
  createdAt: new Date()
});

after.orders.findOne({
  _id: "AFTER-FAILOVER-001"
});
```

Nếu không có primary tại thời điểm client cố ghi, driver có thể chờ server selection hoặc báo lỗi. Khi cluster ổn định, thao tác mới thường có thể chạy thành công theo URI chuẩn.

### 27.1. Không sửa URI sang hostname primary mới bằng tay mỗi lần

Ứng dụng phải tự khám phá topology; nếu code hardcode `mongodb://mongo1:27017/?directConnection=true` cho ghi, sau stepdown nó có thể không ghi được.

### 27.2. Kiểm tra các ghi trước failover

```javascript
after.orders.find({
  _id: {
    $in: [
      "WC-MAJ-001",
      "WC-ONE-001",
      "AFTER-FAILOVER-001"
    ]
  }
});
```

Sự hiện diện của các documents trong bài test hữu ích để quan sát, nhưng **không chứng minh chung rằng mọi `w:1` write luôn tồn tại qua failover**.

## 28. Retryable writes qua failover

MongoDB drivers hỗ trợ retryable writes đối với **các thao tác đủ điều kiện** và deployment/version hỗ trợ, thường qua:

```text
retryWrites=true
```

Những điều quan trọng:

- Driver retry không bảo đảm tất cả writes đều retryable.
- Retryable writes có session/transaction statement identity theo protocol.
- `updateMany`/`deleteMany` và bulk chứa operations không đủ điều kiện có semantics khác.
- Timeout ở business/API layer với một request mới không tự giữ cùng write identity.
- Retry vô hạn một command nghiệp vụ có `$inc` có thể làm tăng giá trị hai lần.

### 28.1. Ví dụ lỗi ở cửa sổ failover

```text
T1 Client gửi updateOne tới primary cũ
T2 Primary xử lý write
T3 Primary nhường vai trò
T4 ACK không tới client
T5 Client nhận error / unknown outcome
```

**Unknown outcome** không đồng nghĩa write chắc chắn chưa xảy ra. Nếu ứng dụng tạo order với ID mới hoặc gọi payment lần hai, có thể sinh duplicate business effect.

### 28.2. Business idempotency

Dùng stable operation ID, unique index, conditional state update, provider idempotency key và reconciliation. Đây là lớp bảo vệ ở nghiệp vụ, bổ sung cho retryable writes của driver.

## 29. Test failover bằng dừng container

**Thử nghiệm nâng cao, chỉ trên lab.**

Sau khi xác định member đang primary bằng `rs.status()`, dừng đúng service đó. Ví dụ nếu mongo1 đang primary:

```bash
docker compose stop mongo1
```

Theo dõi các thành viên còn lại:

```bash
docker compose exec mongo2 mongosh --quiet --eval "db.adminCommand({hello: 1})"
docker compose exec mongo3 mongosh --quiet --eval "db.adminCommand({hello: 1})"
```

Nếu hai thành viên còn lại có voting majority và đủ điều kiện, có thể bầu primary mới.

### 29.1. Khác stepdown

- Stepdown: primary tự nhường vai trò theo command.
- Stop container: member biến mất, còn lại phát hiện qua heartbeat/election.
- Tốc độ failover có thể khác.
- Driver errors và retry behavior có thể khác.

### 29.2. Khởi động lại member

```bash
docker compose start mongo1
```

Node được khởi động lại có thể cần catch-up. Không giả định nó ngay lập tức trở lại primary hay đã bắt kịp.

### 29.3. Không dừng theo tên mặc định nếu primary đã đổi

Nếu mongo2 là primary hiện tại, dừng mongo1 (secondary) chỉ là bài test mất secondary, không phải mất primary. Phải chọn member từ **trạng thái runtime**.

## 30. Test một secondary mất kết nối

Một test khác: nếu mongo3 đang SECONDARY, dừng nó:

```bash
docker compose stop mongo3
```

Trong replica set ba data-bearing voting members, hai members còn lại thường vẫn có majority nếu liên lạc được.

Quan sát:

```javascript
rs.status();
```

Và thử majority write:

```javascript
db.getSiblingDB("lab").orders
  .withWriteConcern({ w: "majority", wtimeout: 5000 })
  .insertOne({
    _id: "TWO-OF-THREE-001",
    tenantId: "T-01",
    orderNo: "TWO-OF-THREE-001"
  });
```

### 30.1. Phục hồi member

```bash
docker compose start mongo3
```

Sau khi member khỏe, kiểm tra status và tiến độ replication. Không reset volume của member chỉ vì nó vừa bị tắt trong lab.

### 30.2. Nếu mong muốn chứng minh chịu được một lỗi

Phải xác nhận **đang còn đúng hai voting data-bearing members có khả năng giao tiếp**, và write majority thành công theo configuration. Nếu một member khác lag, down hoặc không eligible, kết quả sẽ khác.

## 31. Điều gì xảy ra khi mất majority?

Giả sử ban đầu có 3 voting members, sau đó chỉ còn 1.

Khi không đủ majority:

- Không thể duy trì/bầu writable primary bình thường theo giao thức.
- Client ghi sẽ không thể tiếp tục như cluster khỏe.
- `readPreference=secondary` trong một số điều kiện vẫn có thể đọc từ members còn reachable, nhưng phải hiểu khả năng stale và config.
- `w:"majority"` không thể được xác nhận như bình thường.
- Tự thêm `force:true` hoặc `rs.reconfig` để vượt quorum có thể tạo nguy cơ dữ liệu nghiêm trọng.

### 31.1. Không cố tạo primary bằng lệnh nguy hiểm

Trong hệ thật, hành động forced reconfig là phương án khắc phục khẩn cấp có quy trình chặt chẽ, nguy cơ rollback/divergence và cần DBA. Bài lab **không yêu cầu** thực hiện forced reconfiguration.

### 31.2. Thử mất majority có thể làm các phép thử tiếp theo không chạy

Nếu cố dừng hai containers, phải khởi động lại đầy đủ trước khi chuyển phần tiếp theo. Đừng coi lỗi `server selection timeout` là bằng chứng database đã hỏng; có thể đơn giản là cluster không có primary/quorum.

### 31.3. Dữ liệu và availability là hai mục tiêu khác

Replica set ưu tiên quy tắc bầu cử/commit để tránh hai primary hợp lệ cùng ghi theo giao thức. Điều này có thể làm mất khả năng ghi tạm thời thay vì tự cho phép member đơn độc nhận writes.

## 32. `w:1` và rollback: cần diễn giải đúng

Một diễn biến khái niệm:

```text
Primary P nhận write X
     │
     ├── ACK w:1 cho client
     │
     └── Chưa kịp replicate X tới majority

P mất liên lạc / không được bầu lại
     │
     ▼
Secondary khác trở thành primary
     │
     ▼
Write X có thể không nằm trong lịch sử được chọn
     │
     ▼
Rollback trên member chứa X theo cơ chế MongoDB
```

Đây là lý do không nên dùng `w:1` làm bảo đảm tối đa cho dữ liệu có yêu cầu durability mạnh.

### 32.1. Không cần cưỡng ép rollback trong lab cơ sở

Dựng network partitions hoặc force elections để làm rollback có thể phá trạng thái lab và dễ bị áp dụng sai ngoài production. Trong bài này chỉ yêu cầu:

- Giải thích kịch bản;
- Quan sát failover;
- Phân biệt ACK `w:1` và majority;
- Ghi nhận khi nào không thể chứng minh rủi ro bằng test không gây hại.

### 32.2. Một lần `w:1` sống sót qua failover không làm nó thành majority

Nhìn thấy record vẫn còn sau khi stepdown chỉ là một quan sát tại lần thử. Bảo đảm consistency phải dựa trên contract MongoDB của write/read concerns, không dựa trên kết quả may mắn.

## 33. `wtimeout` và kết quả ghi chưa xác định

Trong lúc secondary không đáp ứng, một majority write có thể:

- Được primary áp dụng;
- Không đạt yêu cầu ACK majority trong thời hạn;
- Trả write concern timeout/error tới client.

Đây là trạng thái cần điều tra:

```text
Write sent
   │
   ▼
Primary may apply
   │
   ▼
Majority ACK not achieved before timeout
   │
   ▼
Client sees write concern error
   │
   ▼
Do not blindly retry non-idempotent command
```

### 33.1. Thiết kế idempotent operation

Ví dụ update theo trạng thái cuối:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-001",
    status: "CREATED"
  },
  {
    $set: {
      status: "PAID",
      paymentConfirmed: true
    }
  }
);
```

Nếu cùng command được gọi lại, status đã `PAID` sẽ khiến filter không match và không cộng/chuyển thêm; ứng dụng phải đọc lại để phân loại “đã xử lý” so với “không tồn tại”.

### 33.2. `$inc` không luôn idempotent

```javascript
db.counters.updateOne(
  { _id: "COUNTER-1" },
  { $inc: { count: 1 } }
);
```

Gọi lại như request nghiệp vụ mới có thể cộng lần hai nếu lần trước đã thành công mà client không nhận ACK.

## 34. Majority và secondary read-after-write

Giả sử:

```text
Three members A, B, C

Write X acknowledged w:majority by A+B
C has not yet applied X
```

Nếu client đọc từ C ngay lập tức:

```text
Read C → may see state before X
```

Điều đó không mâu thuẫn với majority write. **Majority** không phải “all replicas caught up”.

### 34.1. Đọc primary nếu cần dữ liệu vừa ghi

Đọc từ primary theo session/concern thích hợp thường giảm rủi ro stale reads. Tuy nhiên, để phát biểu bảo đảm chính xác cho các tình huống concurrent writes và failover, cần đọc đúng semantics của driver/read concern và session, không đơn giản suy từ node label.

### 34.2. Causal session khi cần secondary reads

Nếu workflow phải đọc sau write từ secondary, dùng causally consistent session với majority writes/reads theo điều kiện; driver có thể đảm bảo causal ordering thay vì trả dữ liệu trước mốc cần thiết.

### 34.3. Linearizable read khi có yêu cầu real-time single-document

`readConcern:"linearizable"` với `writeConcern:"majority"` và primary trong điều kiện hỗ trợ phù hợp cho một số invariant yêu cầu phản ánh các writes đã hoàn tất trong thực tế. Có chi phí và hạn chế, không thay multi-document transaction.

## 35. Mô hình thời gian và những guarantee dễ nhầm

| Khái niệm | Câu hỏi cần trả lời |
|---|---|
| Atomicity | Một thao tác có bị thực hiện nửa vời không? |
| Durability | Sau ACK, dữ liệu chịu được loại sự cố nào? |
| Consistency | Client có thể quan sát lịch sử nào? |
| Isolation | Transactions đồng thời có nhìn thấy nhau thế nào? |
| Availability | Khi mất member/partition, dịch vụ tiếp tục gì? |
| Causality | Operation B có quan sát được operation A vốn xảy ra trước nó không? |
| Linearizability | Single-document operations có thể được sắp trong một thứ tự phù hợp real time không? |
| Eventual convergence | Các replicas có bắt kịp khi hệ ổn định không? |

### 35.1. `w:majority` không thay thế business CAS

Nếu hai workers đều có thể chuyển order từ `PENDING` tới hai trạng thái khác nhau bằng `$set` không điều kiện, cả hai writes được majority ACK vẫn có thể làm mất quyết định của worker đầu. Dùng status/revision guards.

### 35.2. `readConcern:majority` không làm các thao tác Java liên tiếp thành transaction

Đọc một tài khoản rồi ghi một đơn ở hai operations riêng có race. Cần atomic conditional update hoặc multi-document transaction nếu invariant yêu cầu.

### 35.3. Replication không có nghĩa backup

Nếu một người xóa nhầm collection trên primary bằng lệnh hợp lệ, thao tác xóa sẽ replicate. Cần backup/PITR để khôi phục trạng thái trước sự cố.

## 36. Java Sync Driver: URI cho ứng dụng

Giả sử Java client chạy **trong Docker network của lab**. URI:

```text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/lab?replicaSet=rs0&retryWrites=true
```

Code:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class ReplicaSetClientDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI missing");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("lab");
            MongoCollection<Document> orders =
                db.getCollection("orders");

            System.out.println(orders.countDocuments());
        }
    }
}
```

Maven dependency minh họa:

```xml
<dependency>
  <groupId>org.mongodb</groupId>
  <artifactId>mongodb-driver-sync</artifactId>
  <version>${mongodb.driver.version}</version>
</dependency>
```

Property `${mongodb.driver.version}` phải được cấu hình bằng phiên bản driver tương thích với server/runtime Java.

### 36.1. Nếu Java chạy trên host

Docker DNS names `mongo1`, `mongo2`, `mongo3` có thể không phân giải ở host. Không chỉ thêm `localhost:27017` và kỳ vọng topology discovery hoạt động: replica set quảng bá addresses từ config. Có thể chạy Java trong Docker network, sử dụng một network setup hợp lệ hoặc DNS được cấu hình để mọi member reachable.

### 36.2. `MongoClient` dùng chung

Trong web service, tạo một `MongoClient` dùng chung theo application lifecycle; nó quản lý discovery/pool. Không tạo một client mới cho mỗi request để “đảm bảo tìm primary mới”.

## 37. Java: write concern majority

```java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.InsertOneResult;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

MongoCollection<Document> durableOrders =
    orders.withWriteConcern(
        WriteConcern.MAJORITY.withWTimeout(10, TimeUnit.SECONDS)
    );

InsertOneResult result = durableOrders.insertOne(
    new Document("_id", "JAVA-MAJ-001")
        .append("tenantId", "T-01")
        .append("orderNo", "JAVA-MAJ-001")
        .append("amountMinor", 500L)
);

System.out.println(result.wasAcknowledged());
```

Mã giả định biến `orders` đã được khởi tạo. Nếu lệnh throw, cần phân loại duplicate key, server selection, retryable labels và write concern errors. Không suy ra mọi exception đều là “record chưa được ghi”.

### 37.1. ACK true có phạm vi

`wasAcknowledged()` báo kết quả theo write concern đã yêu cầu và API trả thành công; không tự kiểm chứng một business transaction qua payment provider.

### 37.2. Không dùng `w:0` cho đơn hàng quan trọng chỉ để tăng throughput

Với dữ liệu nghiệp vụ cần durability mạnh, chọn write concern theo RPO và business risk, không chỉ theo benchmark latency.

## 38. Java: đọc từ secondary với majority read concern

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> secondaryOrders = orders
    .withReadPreference(ReadPreference.secondary())
    .withReadConcern(ReadConcern.MAJORITY);

Document observed = secondaryOrders
    .find(new Document("_id", "JAVA-MAJ-001"))
    .first();

System.out.println(observed);
```

Điều kiện:

- Có secondary reachable/đủ điều kiện;
- Read preference có thể chọn secondary;
- Read concern được server hỗ trợ;
- Document có thể chưa được node đó áp dụng tới commit point mong muốn nếu không có causal coordination.

### 38.1. Không đọc secondary khi nghiệp vụ cần chắc chắn latest

Ví dụ ngay sau khi bấm thanh toán, nếu UI cần phản ánh chính write đã cam kết, cần primary read hoặc causal session phù hợp. Đọc secondary tùy ý có thể hiển thị trạng thái cũ vài giây trong những điều kiện nhất định.

## 39. Java: causally consistent session

Ví dụ luồng tuần tự:

```java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;

import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;

import org.bson.Document;

MongoCollection<Document> majorityWrites = orders
    .withWriteConcern(WriteConcern.MAJORITY);

MongoCollection<Document> majoritySecondaryReads = orders
    .withReadPreference(ReadPreference.secondary())
    .withReadConcern(ReadConcern.MAJORITY);

ClientSessionOptions options =
    ClientSessionOptions.builder()
        .causallyConsistent(true)
        .build();

try (ClientSession session = client.startSession(options)) {
    majorityWrites.insertOne(
        session,
        new Document("_id", "CAUSAL-001")
            .append("tenantId", "T-01")
            .append("orderNo", "CAUSAL-001")
    );

    Document result = majoritySecondaryReads
        .find(session, new Document("_id", "CAUSAL-001"))
        .first();

    System.out.println(result);
}
```

Ví dụ minh họa **read-your-writes qua cùng causal session**, với majority write và majority read. Không tự chia sẻ `ClientSession` cho nhiều threads; không dùng test này để kết luận mọi secondary reads ngoài session cũng nhìn thấy write ngay.

### 39.1. Nếu bị lỗi server selection

Kiểm tra:

- `rs.status()`;
- Có primary/secondary eligible không;
- Hostnames reachable từ client không;
- `replicaSet=rs0` đúng không;
- Có đủ thời gian chờ election/replication không;
- Server selection timeout/pool metrics;
- Authentication/TLS nếu triển khai bảo mật.

Không tắt read concern hoặc đặt `directConnection=true` trên ứng dụng production chỉ để che topology discovery lỗi.

## 40. Java: bắt lỗi khi primary đổi

Một khung:

```java
import com.mongodb.MongoException;
import com.mongodb.MongoTimeoutException;

try {
    orders.insertOne(
        new Document("_id", "FAILOVER-CMD-001")
            .append("tenantId", "T-01")
            .append("orderNo", "FAILOVER-CMD-001")
    );
} catch (MongoTimeoutException ex) {
    // Có thể không chọn được server phù hợp trong hạn chờ.
    // Không tạo business request mới khi chưa xác minh kết quả.
    throw ex;
} catch (MongoException ex) {
    // Phân loại error labels/code và áp dụng retry policy phù hợp.
    // Ghi traceId/operationId, không log PII hoặc connection secrets.
    throw ex;
}
```

Nếu driver retryable writes được bật, một số transient errors có thể được driver xử lý nội bộ. Application retry phải có giới hạn, idempotency và reconciliation.

### 40.1. Không map mọi MongoException thành HTTP 500

Một duplicate key cho idempotency key có thể tương ứng “đã tạo đơn” hoặc conflict payload. Một server selection timeout có thể là dịch vụ tạm không sẵn sàng. Một validation error là lỗi dữ liệu. Phân loại theo domain.

### 40.2. Log fields phù hợp

```text
traceId
businessOperationId
collection/namespace (theo chính sách)
writeConcern level
readPreference
errorCode / errorLabel
duration
selectedServer (được phép)
```

Không log raw MongoDB URI kèm credentials hay documents nhạy cảm.

## 41. Quan sát driver topology changes

MongoDB Java Driver có event listeners cho server/topology/command monitoring theo API phiên bản.

Một số tín hiệu:

- Server description changed;
- Topology description changed;
- Primary unavailable;
- New primary discovered;
- Server selection latency;
- Connection pool checkout wait;
- Retryable write errors;
- Request p95/p99;
- Command monitoring `hello`, `find`, `insert`, `getMore`.

### 41.1. Không log raw command bodies

Các commands có thể chứa dữ liệu khách hàng, session metadata hoặc payload nhạy cảm. Thường chỉ ghi command name, duration, error code và trace correlation.

### 41.2. Đo recovery của client, không chỉ election

Có thể có primary mới ở thời điểm T3 nhưng một application instance chưa khám phá xong hoặc đang chờ connection pool. SLO của người dùng phụ thuộc **thời gian trở lại phục vụ reads/writes**, không chỉ `rs.status()` báo PRIMARY.

## 42. Bài test failover nên chia hai lớp

### 42.1. Lớp database

Kiểm tra:

- Replica set có quorum;
- Election thành công;
- Member cũ trở lại SECONDARY;
- Data đã majority acknowledged vẫn ở trạng thái hợp lệ;
- Secondary catch-up;
- Không có replication errors bất thường.

### 42.2. Lớp ứng dụng

Kiểm tra:

- HTTP requests trong cửa sổ failover có timeout/error rate thế nào;
- Driver tự tìm primary mới;
- Idempotency keys ngăn đơn hàng trùng;
- Không double-charge;
- Read-your-writes theo session khi cần;
- Outbox/CDC consumer phục hồi;
- User-facing SLO được đáp ứng trong guardrails.

Một lệnh `rs.status()` thành công không tự là bằng chứng rằng ứng dụng đã phục hồi.

## 43. Đo sai lệch thời gian khi chạy nhiều workers

Giả sử có:

```text
Worker A: ghi trạng thái PAID
Worker B: đọc từ secondary
Worker C: đọc từ primary
```

Nếu không có session/ordering contract, Worker B có thể đọc trạng thái trước đó, còn Worker C thấy PAID. Đây là một kết quả có thể xảy ra theo replication lag.

### 43.1. Không kết luận secondary "sai dữ liệu" ngay

Secondary có thể đang lag và dữ liệu sẽ hội tụ. Cần đánh giá xem ứng dụng có chấp nhận eventual visibility hay bắt buộc read-after-write consistency.

### 43.2. Dùng message/event IDs cho workflow

Nếu Worker B cần xử lý sau sự kiện PAID, event cần mang orderId/version và worker có cơ chế kiểm chứng source of truth hoặc causal ordering. Không dựa vào polling `status` ở secondary tùy ý để quyết định giao hàng.

## 44. `majority` và đọc nhất quán theo phiên

Một workflow:

```text
Session S:
  Write A with majority
       │
       ▼
  Read B with majority, causally ordered
```

Causal session giúp duy trì các quan hệ thứ tự được hỗ trợ. Nhưng nếu application mở session mới trong mỗi request độc lập mà không mang causal token/context, không mặc nhiên có continuity giữa requests.

### 44.1. Phân biệt user session với driver session

Một `ClientSession` MongoDB là cấu trúc driver/server phục vụ operations/transactions/causality, không đồng nghĩa HTTP session cookie hay user login session.

### 44.2. Không giữ session vô hạn

Session có lifecycle/timeouts và connection resource implications. Tạo theo workflow cần thiết, đóng khi xong, không giữ hàng ngày trong singleton không được quản lý.

## 45. Failover và consistency của multi-document transaction

Một transaction có thể:

- Được commit và majority acknowledged;
- Bị abort do transient error;
- Có commit outcome không rõ cho client khi failover diễn ra.

Ứng dụng cần dùng transaction retry patterns của driver theo error labels, đồng thời bảo vệ business request bằng stable IDs.

### 45.1. Không tự retry toàn transaction có external side effects

Nếu callback transaction gửi payment request HTTP, callback được retry có thể gửi hai payment requests. Tách external API calls ra khỏi transaction, dùng outbox/saga.

### 45.2. Transaction commit không biến secondary bất kỳ thành tức thời up to date

Ngay cả với transaction commit majority, secondary đang tụt vẫn có thể chưa áp dụng transaction. Read concern/session lựa chọn phụ thuộc yêu cầu của workflow.

## 46. Không nhầm độ trễ replication và latency truy vấn

| Chỉ số | Diễn giải |
|---|---|
| Replication lag | Secondary cách primary bao xa về trạng thái áp dụng |
| Write acknowledgment latency | Thời gian client đợi ACK theo write concern |
| Election duration | Khoảng thời gian cluster chuyển leadership |
| Server selection latency | Thời gian client tìm node phù hợp |
| Read query latency | Thời gian trả kết quả query |
| Application recovery time | Thời gian API trở lại SLO sau lỗi |
| Oplog window | Khoảng lịch sử thay đổi có thể sử dụng để sync/resume |
| Change stream lag | Consumer chậm hơn log events bao xa |

Một ứng dụng có low replication lag nhưng query chậm do index thiếu. Ngược lại, một secondary query nhanh có thể trả dữ liệu cũ. Phải đo đúng hiện tượng.

## 47. Một số command quan sát hữu ích

| Command/helper | Mục đích | Tác động |
|---|---|---|
| `rs.status()` | Runtime health/members | Read-only |
| `rs.conf()` | Replica set config | Read-only |
| `db.adminCommand({hello:1})` | Vai trò và topology của node | Read-only |
| `rs.printSecondaryReplicationInfo()` | Quan sát replication lag | Read-only |
| `db.serverStatus()` | Metrics server theo quyền | Read-only |
| `db.currentOp()` | Operations đang chạy theo quyền | Read-only |
| `rs.stepDown()` | Nhường primary | **Topology-changing** |
| `rs.reconfig()` | Sửa replica set config | **Topology-changing, rủi ro** |
| `rs.freeze()` | Hạn chế bầu cử trên secondary trong thời gian chỉ định | **Topology-changing** |
| `docker compose stop` | Dừng member | **Gây gián đoạn** |
| `docker compose down -v` | Xóa containers và volumes | **Xóa dữ liệu lab** |

Không coi lệnh có thể thay đổi topology là read-only vì nó nằm trong `mongosh`.

## 48. Phản ứng khi một member không bắt kịp

Nếu mongo3 vẫn SECONDARY nhưng lag đáng kể:

1. Đọc `rs.status()` và replication metrics.
2. Kiểm tra network connectivity, disk, CPU, cache, throttling.
3. Kiểm tra member có đang initial sync/RECOVERING không.
4. Kiểm tra oplog window và volume thay đổi.
5. Quan sát workload gần đây: batch writes, indexes, long queries.
6. Không xóa data volume hoặc ép reconfig ngay.
7. Nếu cần, làm theo documented initial sync/resync procedure phù hợp.

### 48.1. Phân biệt lag và sync source issues

Secondary có thể đang đợi nguồn sync hoặc không thể áp dụng kịp oplog. Không dựa duy nhất vào `optimeDate`; cần logs và metrics liên quan.

### 48.2. Không ép thành viên lag làm primary

Một member lag hoặc không đủ điều kiện không nên được bầu chỉ để “có primary”. Các election rules nhằm bảo vệ tính nhất quán và vận hành.

## 49. Primary election không phải backup/DR

Giả sử client xóa nhầm:

```javascript
db.orders.deleteMany({});
```

Nếu thao tác hợp lệ được ghi trên primary, các secondary cũng nhận và áp dụng thay đổi. Replica set duy trì bản sao **trạng thái hiện hành**, bao gồm lỗi logic hợp lệ.

Cần:

- Backup snapshots;
- Point-in-time recovery theo phương pháp hỗ trợ;
- Restore drills;
- RPO/RTO;
- Access control;
- Audit;
- Confirmation/soft-delete với lệnh nguy hiểm.

### 49.1. Không dùng lệnh xóa tất cả để thử replication

Bài lab không yêu cầu `deleteMany({})` trên bất cứ collection đang có dữ liệu ngoài test. Nếu cần làm clean-up, làm trong namespace lab đã xác định.

## 50. Bảo mật replica set ngoài lab

Production tối thiểu cần đánh giá:

- Internal authentication giữa mongod members;
- TLS/mTLS theo security architecture;
- SCRAM/x.509/OIDC/LDAP theo môi trường;
- RBAC/least privilege;
- Network segmentation/firewall/private endpoints;
- Secrets/keyfile protection;
- Audit logging;
- Encryption at rest/KMS;
- Backup/PITR;
- Hostname/DNS validity;
- Monitoring/alerts;
- Upgrade compatibility;
- Capacity/disaster recovery.

### 50.1. Tắt auth chỉ vì Docker dễ hơn là sai trong production

Cấu hình minh họa cố tình đơn giản để học replication trên máy cá nhân. Nó không là mẫu production-ready.

### 50.2. Không dùng password trong câu lệnh history

Production dùng secret manager/workload identity/certificate theo thiết kế; không commit credentials vào Compose file hoặc repository.

### 50.3. Quản trị lệnh nhạy cảm

Chỉ người có quyền vận hành mới được dùng `rs.stepDown()`/`rs.reconfig()`, và phải có change window, communication, backup, rollback path.

## 51. Ma trận kỳ vọng khi một node lỗi

Với ba data-bearing voting members, giả định không có lỗi khác:

| Sự kiện | Primary khả dụng? | Majority writes? | Điều cần quan sát |
|---|---|---|---|
| Không lỗi | Có | Có | Normal operation |
| Secondary 3 dừng | Có nếu hai members còn khỏe | Thường có | Lag/rejoin |
| Primary dừng | Tạm gián đoạn đến election | Sau election có thể tiếp tục | Election và driver reconnect |
| Hai members dừng | Không có majority | Không | Server selection/write errors |
| Primary chủ động stepdown | Tạm election | Sau election có thể tiếp tục | State transition |
| Một secondary lag | Có thể có | Tùy members xác nhận được | Read freshness |
| Network phân vùng 2–1 | Phía majority có thể bầu | Phía majority có thể ghi | Không có hai writable primaries hợp lệ |

Đây là **kỳ vọng theo giả định**; thực tế còn phụ thuộc votes, priority, member state, topology, elections và server configuration.

## 52. Bảng kết quả thực nghiệm

Điền sau lab:

| Test ID | Thiết lập | Kết quả kỳ vọng | Quan sát thực tế | Kết luận |
|---|---|---|---|---|
| T01 | Init 3 nodes | 1 primary, 2 secondary | ... | ... |
| T02 | Write `w:1` | Primary ACK theo điều kiện | ... | ... |
| T03 | Write majority | Majority ACK | ... | ... |
| T04 | Read secondary | Có thể lag | ... | ... |
| T05 | Stepdown primary | Election mới | ... | ... |
| T06 | Write sau election | Driver định tuyến được | ... | ... |
| T07 | Stop 1 secondary | Còn majority | ... | ... |
| T08 | Stop primary | New election nếu quorum | ... | ... |
| T09 | Causal session | Read-your-writes theo điều kiện | ... | ... |
| T10 | Transaction | Commit/abort đúng | ... | ... |
| T11 | Resume/cleanup | Cluster ổn định | ... | ... |

### 52.1. PASS không đồng nghĩa quan sát được lag

Với T04, nếu không thấy chênh lệch, kết quả nên là:

```text
Read secondary succeeded; lag NOT OBSERVED
under low-load single-host lab conditions.
```

Không viết “secondary luôn nhất quán tức thì”.

### 52.2. Ghi bằng chứng theo mốc

Có thể lưu:

```text
UTC timestamp
Replica set status (redacted)
Current primary
Current term/election metadata
Member health
Client URI class (without credentials)
Read preference / concern
Write concern
Command outcome / error code
Driver/server versions
```

Không lưu raw secrets hoặc tài liệu khách hàng.

## 53. Sự cố thường gặp: `no primary` sau init

Triệu chứng:

```text
Replica set has no primary
Server selection timed out
```

Nguyên nhân có thể:

- Election chưa hoàn tất;
- Một hoặc nhiều member chưa healthy;
- Hostnames không phân giải được;
- Các member không liên lạc được nhau;
- Cấu hình `rs0` không nhất quán;
- Data volume giữ config cũ từ lần lab trước;
- Votes/priority khiến không có eligible candidate.

Cách kiểm tra:

```bash
docker compose ps
docker compose logs --tail=100 mongo1
docker compose logs --tail=100 mongo2
docker compose logs --tail=100 mongo3
```

Trong mongosh:

```javascript
rs.status();
rs.conf();
db.adminCommand({ hello: 1 });
```

Không xóa volumes trước khi biết chúng có dữ liệu nào cần giữ.

## 54. Sự cố thường gặp: client kết nối được một host nhưng không kết nối được replica set

Mô tả:

```text
mongosh mongodb://localhost:27017 works
Java replicaSet URI times out
```

Nguyên nhân phổ biến trong Docker lab:

- Client chạy trên host nhưng replica set quảng bá Docker DNS hostnames;
- Ports chưa publish hoặc DNS/hosts mappings không đúng;
- Client cố kết nối bằng IP/hostname chỉ có một thành viên hiểu;
- `replicaSet` name trong URI khác `rs.conf()._id`.

### 54.1. Cách xử lý

Đối với lab, chạy `mongosh`/Java trong Docker network. Đối với production, thiết kế DNS và certificate SAN để client có thể kết nối **mọi member được quảng bá**, không chỉ seed đầu.

### 54.2. Không chữa bằng `directConnection=true` cho ứng dụng cần HA

Chế độ direct có thể kết nối vào một node cụ thể nhưng bỏ lợi ích replica set discovery/failover của driver; có thể làm ứng dụng không tìm primary mới khi topology đổi.

## 55. Sự cố thường gặp: `NotWritablePrimary`

Khi write gửi tới một node vừa mất vai trò primary:

```text
NotWritablePrimary / not primary / node is recovering
```

Xác minh:

- Client dùng replica set URI hay direct member;
- Topology discovery;
- `hello` trên node hiện tại;
- Driver version;
- Retryable writes;
- Server selection timeout;
- Election status.

Nếu client kết nối trực tiếp node cũ, retry vô hạn trên chính node đó không biến nó thành primary.

## 56. Sự cố thường gặp: majority write timeout

Khi majority ACK không đạt trước `wtimeout`:

```text
write concern timeout / write concern failed
```

Điều tra:

1. Có primary không?
2. Có đủ voting/data-bearing members để đáp ứng majority không?
3. Secondary nào lag hoặc mất kết nối?
4. Disk/network có bị nghẽn không?
5. Write đã áp dụng ở primary chưa?
6. Operation có idempotent không?
7. Retry policy có nguy cơ tạo trùng không?

Không hạ ngay `w:"majority"` xuống `w:1` trên production để tắt lỗi khi yêu cầu durability chưa được đánh giá lại.

## 57. Sự cố thường gặp: secondary read thấy giá trị cũ

Ví dụ:

```text
Write status=PAID to primary, ACK majority
Read secondary C: status=PENDING
```

Đây có thể là replica lag/read semantics, không nhất thiết là mất dữ liệu.

Hướng giải quyết:

- Xem `readPreference` và `readConcern`;
- Nếu workflow cần read-your-writes, dùng primary read hoặc causal session phù hợp;
- Kiểm tra member lag;
- Không quyết định thực hiện tác động không đảo ngược từ một read có thể stale;
- Thiết kế event ordering/primary verification cho các workflow critical.

## 58. Sự cố thường gặp: `rs.stepDown()` bị từ chối

Một số nguyên nhân:

- Không chạy trên primary;
- Secondary không đủ điều kiện/caught-up theo helper;
- Majority không sẵn sàng;
- Server đang trong trạng thái không phù hợp;
- Quyền admin thiếu.

Cách làm:

1. Đọc `hello` để xác định node đang primary.
2. Đọc `rs.status`.
3. Kiểm tra các secondary khỏe và lag.
4. Chờ ổn định rồi thử lại trong lab nếu thích hợp.
5. Không dùng force option mù quáng.

## 59. Sự cố thường gặp: primary cứ đổi lại

Vì config ban đầu đặt mongo1 priority cao, sau stepdown hoặc node restart, topology có thể bầu lại member ưu tiên hơn khi điều kiện cho phép.

Điều này là lý do:

- Không hardcode node primary;
- Không assert failover luôn chọn mongo2 vĩnh viễn;
- Không coi election test thất bại chỉ vì sau vài phút primary quay lại mongo1;
- Đọc `rs.conf()` và election metrics.

Để test deterministic leadership lâu dài cần thiết kế priority/votes riêng và theo quy trình có kiểm soát, không tự reconfig production chỉ để demo.

## 60. Quy tắc không dùng lệnh nguy hiểm ngoài lab

Những lệnh sau **không phải** bước cần thực hiện trên production trong bài:

```text
rs.stepDown(...)
rs.reconfig(...)
rs.freeze(...)
force reconfiguration
docker compose stop <primary>
docker compose down -v
db.dropDatabase()
```

Ngoài lab, mỗi thao tác topology/destructive cần runbook, backup, quyền phù hợp, change approval và stop criteria.

### 60.1. Đừng dùng `rs.reconfig` để sửa mọi lỗi DNS

Đổi member hostnames có thể ảnh hưởng cluster và các clients. Trước khi reconfig cần kiểm tra network/DNS/driver URI, backup và quy trình hỗ trợ theo version.

### 60.2. Đừng dùng `force:true` vì bài demo chậm

Một forced stepdown/reconfiguration có thể làm tăng rủi ro rollback hoặc availability outage. Phần cơ sở của lab chỉ dùng stepdown bình thường và quan sát trạng thái.

## 61. Hoàn nguyên về trạng thái khỏe

Sau khi thử dừng member:

```bash
docker compose start mongo1
docker compose start mongo2
docker compose start mongo3
```

Nếu container đang chạy, `start` có thể chỉ báo đã chạy; dùng `docker compose ps` để xác nhận.

Kết nối shell replica set:

```bash
docker compose exec mongo1 mongosh "mongodb://mongo1:27017,mongo2:27017,mongo3:27017/lab?replicaSet=rs0"
```

Kiểm tra:

```javascript
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr,
  health: m.health
}));
```

Expected ổn định:

```text
One PRIMARY
Two SECONDARY
All healthy
No member stuck in RECOVERING due to a lab issue
```

### 61.1. Không mong primary luôn quay về mongo1 ngay

Có thể có priority takeover sau thời gian hoặc các điều kiện; điều quan trọng là cluster khỏe, có primary, replicas synced và client hoạt động.

### 61.2. Xác minh dữ liệu

```javascript
labDb.orders.find({
  _id: {
    $in: [
      "ORD-001",
      "WC-ONE-001",
      "WC-MAJ-001",
      "AFTER-FAILOVER-001"
    ]
  }
});
```

Ghi kết quả, không tự kết luận một failed write đã được commit hay không nếu thiếu evidence.

## 62. Dừng lab nhưng giữ dữ liệu

Trong thư mục `compose.yaml`:

```bash
docker compose down
```

Lệnh dừng và xóa containers/network của project, nhưng mặc định **giữ named volumes** như `mongo1_data`, `mongo2_data`, `mongo3_data`.

Khi chạy lại:

```bash
docker compose up -d
```

Volumes còn giữ trạng thái data/replica set. Thường không cần `rs.initiate()` lại nếu mọi thành viên vẫn giữ cấu hình.

### 62.1. Xóa sạch lab khi chắc chắn không cần dữ liệu

**Lệnh xóa volumes của project**, chỉ được chạy trong lab đã xác nhận:

```bash
docker compose down -v
```

Hành động này xóa dữ liệu MongoDB trên named volumes của Compose project. Không chạy trong thư mục của một project production hoặc project chứa dữ liệu khác mà chưa kiểm tra.

### 62.2. Tránh tái sử dụng volumes với image major version khác

Nếu đổi `mongo:8.0` sang image major khác, không mặc định tương thích data files. Thực hiện version upgrades theo đường được MongoDB hỗ trợ.

## 63. Tổng kết các điều đã quan sát được và chưa chứng minh được

| Bằng chứng có thể thu bằng lab | Điều không thể tự suy ra |
|---|---|
| Có đúng 1 primary | Primary luôn là mongo1 |
| Secondary đã thấy write | Secondary không bao giờ lag |
| Majority write ACK | Mọi node đều đã áp dụng |
| `w:1` write còn sau stepdown | Mọi `w:1` write không rollback |
| Driver tìm primary mới | Mọi requests sẽ không lỗi khi failover |
| `rs.stepDown` thành công | Hệ có RTO production đã đạt |
| Transaction commit thành công | External payment cùng được commit |
| Replication khỏe | Không cần backup |
| Secondary read đúng trong một thử nghiệm | Mọi stale reads bị loại trừ |
| Java app connect trong container | URI hoạt động trên host/public network |

### 63.1. Một kết luận khoa học phải nêu giả định

Viết:

> “Trong lab Docker một máy, ba data-bearing members đã bầu lại primary sau stepdown và một majority write trước failover vẫn được đọc lại. Không đo được lag lớn; kết quả không chứng minh RTO production hoặc bảo đảm tức thời cho mọi secondary.”

Không viết:

> “MongoDB replica set luôn failover ngay lập tức và không bao giờ mất dữ liệu.”

## 64. Bài tập 1 — Vẽ topology

Vẽ replica set ba nodes, primary/secondary, oplog replication và client discovery. Giải thích vì sao client URI cần nhiều seed hosts/replicaSet và vì sao không hardcode primary.

## 65. Bài tập 2 — Tính quorum

Với 3, 5 và 7 voting members, tính majority. Với replica set 3 members, phân tích kịch bản mất một hoặc hai voting members. Tại sao thêm arbiter không làm tăng số data-bearing copies?

## 66. Bài tập 3 — Khởi tạo và đọc cấu hình

Dùng Compose, khởi tạo `rs0`, đọc `rs.conf()` và `rs.status()`. Phân biệt `priority`, `votes`, `stateStr`, `health`, `optimeDate`. Ghi primary hiện tại.

## 67. Bài tập 4 — Verify DNS

Giả lập Java client chạy ngoài Docker network không phân giải `mongo2`. Giải thích tại sao nó có thể kết nối seed ban đầu rồi timeout ở discovery. Đề xuất một giải pháp lab an toàn không đổi production replica set config.

## 68. Bài tập 5 — So sánh write concern

Ghi 100 documents `w:1` và 100 documents `w:"majority"` bằng cùng bộ dữ liệu giả. Đo p50/p95 cẩn thận, giải thích vì sao một máy không chứng minh hiệu năng trong hệ đa vùng.

## 69. Bài tập 6 — Read preference

Đọc một order từ primary và một secondary. Thử `primary`, `secondary`, `secondaryPreferred` và giải thích những trade-offs. Không tuyên bố `nearest` đảm bảo newest.

## 70. Bài tập 7 — Read concern

Phân biệt `local`, `majority`, `snapshot`, `linearizable`. Xác định yêu cầu nghiệp vụ của: lịch sử đơn, màn thanh toán vừa xong, báo cáo chấp nhận lag và cập nhật một document quan trọng.

## 71. Bài tập 8 — Causal session

Viết Java client cùng một `ClientSession` để majority write rồi majority read từ secondary. Giải thích tại sao cùng session/causal ordering có ý nghĩa và tại sao session không được chia sẻ tùy ý giữa threads.

## 72. Bài tập 9 — Stepdown

Đọc `rs.status`, gọi `rs.stepDown(60,10)` trên current primary trong lab, ghi timeline, xác định primary mới, thử ghi tiếp bằng replica set URI.

## 73. Bài tập 10 — Stop primary

Dừng current primary container trong lab, xác minh hai members còn lại có quorum, quan sát election và driver reconnect. Khởi động lại member cũ và xác minh catch-up.

## 74. Bài tập 11 — Stop secondary

Dừng một secondary và thử `w:"majority"` trên hai members còn lại. Thử tiếp khi chỉ còn một member trong môi trường lab nếu có kế hoạch hồi phục rõ, mô tả nguyên nhân không có writable primary.

## 75. Bài tập 12 — Unknown write outcome

Một command `$inc` nhận network timeout đúng khi primary stepdown. Viết ba câu hỏi cần xác minh trước retry. Đề xuất stable operation ID hoặc CAS để tránh double increment ở tầng ứng dụng.

## 76. Bài tập 13 — Atomic update

Hai workers đọc `revision=5` rồi cùng muốn đổi order status. Viết `updateOne` với filter revision và giải thích `matchedCount=0`. Replica set có tự tránh lost update nếu cả hai chỉ `$set` không điều kiện không?

## 77. Bài tập 14 — Transaction

Tạo transaction trong lab insert hai documents. Gây lỗi trước commit ở một phiên riêng có cách cleanup, xác minh không có trạng thái nửa vời. Thảo luận commit unknown result và retry transaction.

## 78. Bài tập 15 — Secondary lag

Thực hiện 1.000 writes rồi quan sát `optimeDate`/replication info. Nếu lag không xuất hiện, ghi vì sao môi trường single-host không đủ để chứng minh zero lag. Đề xuất metrics cần đo trên hệ thật.

## 79. Bài tập 16 — Arbiter và trade-off

So sánh 3 data-bearing members với 2 data-bearing + 1 arbiter về availability, durability, write concern và transaction eligibility. Khi nào arbiter có thể được cân nhắc và vì sao không là bản sao dữ liệu?

## 80. Bài tập 17 — Quan sát client

Thêm driver topology/command monitoring theo version. Trong stepdown test, ghi primary discovery, retry count, server selection duration, API p95/p99 và lỗi, nhưng không log command payload hay secrets.

## 81. Bài tập 18 — Tình huống mạng phân vùng

Một cluster 3 members chia thành nhóm 2 và 1. Phân tích bên nào có thể bầu primary, tác động writes, secondary reads và stale results. Không tự dùng force reconfig.

## 82. Bài tập 19 — Khôi phục từ backup

Giả sử operator xóa nhầm một collection rồi thao tác đó replicate. Vì sao bầu primary mới không khôi phục collection? Thiết kế backup/PITR restore drill và RPO/RTO proof.

## 83. Bài tập 20 — Báo cáo thực hành

Viết báo cáo gồm topology, `rs.conf`, member states, write/read concerns, failover timeline, trường hợp không quan sát lag, client recovery, error classification, limitation và kiến nghị áp dụng production.

## 84. Checklist trước khi chạy lab

- [ ] Có Docker Compose và image MongoDB phù hợp.
- [ ] Dùng project directory riêng, không trộn volume production.
- [ ] Không publish cổng unauthenticated ra ngoài.
- [ ] Đủ tài nguyên cho ba `mongod`.
- [ ] Biết địa chỉ Docker DNS và giới hạn host connectivity.
- [ ] Có đủ ba volumes độc lập.
- [ ] Biết cách `docker compose ps/logs/start/stop`.
- [ ] Chỉ thao tác trên môi trường được phép.
- [ ] Có bản ghi mục tiêu/lệnh sẽ chạy.
- [ ] Không có dữ liệu người dùng thật trong lab.

## 85. Checklist sau khi dựng replica set

- [ ] `rs.conf()._id` là `rs0`.
- [ ] Ba hostnames đúng Compose network.
- [ ] Có ba voting data-bearing members.
- [ ] Có đúng một PRIMARY.
- [ ] Các members còn lại là SECONDARY khỏe.
- [ ] `rs.status` không báo lỗi bất thường.
- [ ] MongoDB client URI dùng `replicaSet=rs0`.
- [ ] Insert/query test thành công.
- [ ] Đọc được member state và optime.
- [ ] Đã hiểu rằng priority không là current role.

## 86. Checklist sau khi chuyển primary

- [ ] Ghi trạng thái trước stepdown.
- [ ] Đã chạy stepdown chỉ trên primary của lab.
- [ ] Có primary mới nếu quorum đủ.
- [ ] Client replica set tự phát hiện/định tuyến lại.
- [ ] `w:majority` writes được đối soát.
- [ ] Không kết luận `w:1` rollback-safe từ một test.
- [ ] Secondary cũ/primary cũ quay về trạng thái ổn định.
- [ ] Không có long-running app workers bị kẹt.
- [ ] Có metrics timeout/errors và recovery time.
- [ ] Không dùng force reconfig để “sửa nhanh”.
- [ ] Lab members được start lại đầy đủ.

## 87. Checklist hiểu tính nhất quán

- [ ] Phân biệt write concern và read concern.
- [ ] Phân biệt read concern và read preference.
- [ ] Biết secondary có thể lag.
- [ ] Hiểu majority là subset, không phải tất cả.
- [ ] Hiểu read-your-writes có điều kiện/session.
- [ ] Biết transaction scope khác external side effects.
- [ ] Dùng CAS cho business state races.
- [ ] Có idempotency để xử lý unknown outcomes.
- [ ] Không coi election là backup.
- [ ] Không biến một quan sát single-host thành production SLA.

## 88. Tài liệu tham khảo

Đối chiếu với tài liệu của **đúng MongoDB Server, mongosh và Java Driver version** đang sử dụng:

- [MongoDB Replica Sets](https://www.mongodb.com/docs/manual/replication/)
- [Deploy Replica Set](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [MongoDB `rs.initiate()`](https://www.mongodb.com/docs/manual/reference/method/rs.initiate/)
- [MongoDB `rs.status()`](https://www.mongodb.com/docs/manual/reference/method/rs.status/)
- [MongoDB `rs.conf()`](https://www.mongodb.com/docs/manual/reference/method/rs.conf/)
- [MongoDB `rs.stepDown()`](https://www.mongodb.com/docs/manual/reference/method/rs.stepDown/)
- [MongoDB `hello` Command](https://www.mongodb.com/docs/manual/reference/command/hello/)
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [MongoDB Causal Consistency](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/)
- [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB Driver Connection Strings](https://www.mongodb.com/docs/manual/reference/connection-string/)
- [MongoDB Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/)
- [MongoDB Backup and Restore](https://www.mongodb.com/docs/manual/core/backups/)

## Kết luận

Qua bài thực hành này, bạn đã xây dựng một MongoDB **replica set ba data-bearing members**, đọc cấu hình/vai trò, ghi dữ liệu, quan sát bản sao trên secondary, chuyển primary bằng `rs.stepDown()` và thử phản ứng của client khi bầu cử xảy ra.

Điểm quan trọng không phải chỉ thấy `mongo2` biến thành PRIMARY. Replica set có **cơ chế leader election và replication**, nhưng mỗi mức bảo đảm vẫn cần đặt đúng:

- **`w:1`** xác nhận ở primary theo điều kiện áp dụng, không đồng nghĩa đa số đã lưu.
- **`w:"majority"`** cung cấp bảo đảm mạnh hơn về commit theo majority, không đồng nghĩa mọi secondary đã bắt kịp.
- **`readPreference`** quyết định node được chọn để đọc, không quyết định phiên bản dữ liệu mới nhất.
- **`readConcern`** và **causal session** cung cấp các mức bảo đảm khác nhau về trạng thái được quan sát.
- **Single-document atomicity**, **CAS** và **multi-document transactions** giải quyết những nhóm invariant khác với replication.
- **Retry/idempotency** rất quan trọng vì một timeout quanh failover có thể để lại kết quả không xác định cho client.

Hơn nữa, một lab ba containers trên cùng máy không mô phỏng được mọi lỗi mạng, mất vùng, disk corruption hay latency production. Nếu secondary không biểu hiện lag trong một lần chạy, đó là kết quả hợp lệ của môi trường thử, **không phải bằng chứng rằng replication không bao giờ trễ**.

**Một ứng dụng MongoDB bền vững không cần biết trước node nào sẽ là primary. Nó cần lựa chọn write/read concerns đúng nghiệp vụ, xử lý chuyển topology bằng driver, bảo vệ writes bằng idempotency và xác minh các giả định nhất quán qua test có khả năng lặp lại.**

