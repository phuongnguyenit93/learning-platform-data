# Theo dõi shard, balancer và mức lệch phân bố dữ liệu trong MongoDB

## 1. Bài toán: cluster có ba shard nhưng một shard vẫn quá tải

Giả sử một nền tảng thương mại điện tử chuyển collection **commerce.orders** sang sharded cluster để lưu hàng trăm triệu đơn hàng. Sau khi mở rộng từ hai lên ba shard, dashboard hiển thị:

| Shard | Dung lượng vật lý ước lượng | CPU cao điểm | Write operations/giây |
|---|---:|---:|---:|
| **shard01** | 900 GiB | 92% | 7.500 |
| **shard02** | 320 GiB | 38% | 1.900 |
| **shard03** | 290 GiB | 32% | 1.600 |

Người vận hành cần trả lời:

- MongoDB đã **nhận diện đủ ba shards** chưa?
- Balancer đang bật, tạm dừng hay migration liên tục thất bại?
- Các **ranges/chunks** phân bố ra sao?
- Nếu số chunks gần bằng nhau, vì sao disk và CPU vẫn lệch?
- **Shard key** có đưa writes mới vào một vùng giá trị liên tục không?
- Các **zones** có cố ý giới hạn nơi đặt dữ liệu?
- Có **jumbo/oversized ranges**, orphaned documents hoặc migration backlog?
- Sau khi thêm shard, bao lâu phân bố dữ liệu và workload được cải thiện?
- Cần dashboard và runbook nào để chẩn đoán mà không vô tình gây outage?

Đây là bài toán **quan sát hệ thống**: đo đúng tín hiệu, giải thích nó trong ngữ cảnh cluster metadata và workload, rồi mới ra quyết định vận hành.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Mô tả **mongos, config server replica set, shards và balancer**.
2. Phân biệt **chunk-count skew**, **owned-data skew**, **disk skew** và **workload skew**.
3. Dùng **sh.status()**, **listShards**, **balancerStatus**, **getShardDistribution** và metrics phù hợp.
4. Hiểu **range migration**, placement constraints, zone sharding và tình huống cân bằng mất thời gian.
5. Nhận biết hot shard do shard key/workload thay vì luôn đổ lỗi cho balancer.
6. Theo dõi **migration failures, jumbo ranges, orphan cleanup** và tác động hoạt động dữ liệu.
7. Thiết kế dashboard, ngưỡng cảnh báo và runbook điều tra an toàn.
8. Quan sát cluster qua mongosh, Java và hệ thống metrics.

**Nguyên tắc:** *Chunks đều không đồng nghĩa bytes đều; bytes đều không đồng nghĩa CPU và latency đều; và phân bố theo zone có thể cố ý không đều.*

## 2. Kiến trúc sharded cluster cần quan sát

~~~text
                    Client applications
                            |
                       MongoDB driver
                            |
                 +----------v----------+
                 | mongos routers      |
                 | query targeting     |
                 +----------+----------+
                            |
             +--------------+--------------+
             |              |              |
       +-----v-----+  +-----v-----+  +-----v-----+
       | shard01   |  | shard02   |  | shard03   |
       | replica   |  | replica   |  | replica   |
       | set       |  | set       |  | set       |
       +-----------+  +-----------+  +-----------+
                            ^
                            |
               +------------+-----------+
               | Config server replica  |
               | set (CSRS): metadata   |
               +------------------------+
                     balancer / migrations
~~~

### 2.1. mongos: điểm vào và định tuyến

**mongos** tiếp nhận yêu cầu từ driver, xác định shards/ranges cần truy cập và tổng hợp kết quả nếu một query phân tán. Theo dõi connections, query latency, throughput, errors, tỷ lệ targeted so với scatter-gather và độ trễ từ mongos tới shards/config servers.

Không truy cập primary của một shard như cách thay thế mongos đối với queries ứng dụng thông thường trên sharded collection: có nguy cơ chỉ đọc một phần dữ liệu và bỏ qua routing metadata.

### 2.2. Config servers: metadata phân vùng

Config server replica set (**CSRS**) lưu metadata về shards, sharded collections, chunks/ranges và zones. Metadata cho biết mỗi range thuộc shard nào, hỗ trợ routing và tác vụ placement/migration.

CSRS cũng có primary/secondaries, replication lag và member health cần quan sát. CSRS không khỏe có thể ảnh hưởng các thao tác metadata dù một số truy vấn dữ liệu còn được phục vụ.

**Không tự cập nhật documents trong database config** để ép ownership hoặc thay boundaries. Chỉ dùng các lệnh quản trị được hỗ trợ.

### 2.3. Shards là replica sets

Mỗi shard thường là một replica set và giữ một phần dữ liệu của sharded collection.

Phải quan sát hai cấp:

- **Shard-level:** lượng dữ liệu/ranges được gán, CPU, throughput, cache, disk.
- **Replica-set-level:** primary election, member health, replication lag, oplog và read preference.

Ba members trong một replica set vẫn là **một shard logic**, không phải ba shards phân phối dữ liệu độc lập.

### 2.4. Balancer làm gì?

Balancer giúp cluster điều chỉnh **phân bố các ranges/chunks** và tuân thủ placement constraints:

1. Đọc metadata và thông tin kích thước/phân bố.
2. Xác định ranges có thể/đáng chuyển.
3. Điều phối **range migration** từ donor sang recipient shard.
4. Cập nhật ownership metadata khi migration commit.
5. Tiếp tục hoặc tạm hoãn theo trạng thái cluster và cấu hình/phiên bản.

Balancer **không** bảo đảm CPU/QPS hay độ trễ mọi shard bằng nhau. Nó chủ yếu xử lý vị trí dữ liệu; hiệu năng còn phụ thuộc shard key, indexes, query targeting và hardware.

### 2.5. Vì sao cần quan sát nhiều lớp?

~~~text
User-facing latency
       ^
       |
     mongos                    -> routing/targeting
       ^
       |
  shard primary/secondary      -> CPU, disk, cache, lag
       ^
       |
  ranges/chunks and shard key  -> placement, hot ranges
       ^
       |
  CSRS metadata + balancer     -> migrations, zones
~~~

Chỉ một biểu đồ “disk used per shard” không thể giải thích chuỗi nguyên nhân này.

## 3. Range/chunk và ý nghĩa của số chunks

MongoDB chia keyspace của sharded collection thành **ranges** (thường gọi **chunks** trong nhiều công cụ/tài liệu), có boundaries theo shard key:

~~~text
Shard key space:

-infinity |-----------|-----------|-----------| +infinity
          A           B           C           D

Range R1: [-infinity, A)
Range R2: [A, B)
Range R3: [B, C)
Range R4: [C, D)
Range R5: [D, +infinity)
~~~

Mỗi range có **owner shard**. Mongos dùng shard key và routing metadata để định tuyến.

### 3.1. Chunk count không phải data size

| Shard | Số ranges | Owned data size |
|---|---:|---:|
| shard01 | 100 | 900 GiB |
| shard02 | 100 | 110 GiB |
| shard03 | 100 | 105 GiB |

Số ranges bằng nhau nhưng bytes sở hữu không đều. Có thể có ranges rất lớn hoặc mật độ documents khác nhau.

Ngược lại:

| Shard | Số ranges | Owned data size |
|---|---:|---:|
| shard01 | 300 | 300 GiB |
| shard02 | 150 | 300 GiB |
| shard03 | 75 | 300 GiB |

Số ranges khác nhau nhưng bytes bằng nhau. Cơ chế balancing hiện đại có thể xét kích thước dữ liệu/placement chứ không chỉ chia đều chunk count.

### 3.2. Split, migration và merge khác nhau

- **Split:** chia một range thành nhiều ranges nhỏ hơn.
- **Migration:** chuyển ownership của range giữa donor và recipient shard.
- **Merge:** trong điều kiện hỗ trợ, kết hợp các ranges liền kề cùng owner.

Hành vi split/merge/range management thay đổi theo MongoDB version. **Split không tự giảm bytes trên shard** nếu ownership chưa chuyển.

### 3.3. Migration không làm disk lập tức giảm

~~~text
Logical ownership after move:
  shard01 no longer owns R9
  shard02 owns R9

Physical storage:
  shard01 may still contain orphan copies awaiting cleanup
  shard02 has received R9 data
~~~

Disk usage có thể chưa giảm ngay, hoặc tăng tạm thời trong migration. Cần phân biệt **owned bytes** với **physical storage bytes**.

### 3.4. Disk storage gồm nhiều thành phần

~~~text
Disk usage per shard may reflect:
  collection data
  indexes
  oplog/replication overhead
  storage-engine free space / fragmentation
  temporary migration effects
  other collections on the shard
~~~

Đây là các thành phần khái niệm, không phải công thức cộng metric máy móc: metric storage của MongoDB đôi khi bao gồm các thành phần khác.

### 3.5. Dùng cùng thời điểm so sánh

Nếu một phép đo được lấy lúc 10:00, phép đo còn lại lấy lúc 10:02 giữa migration, các con số có thể phản ánh trạng thái khác nhau. Dashboard cần ghi timestamp, namespace và trạng thái migration khi tính skew.

## 4. Bốn loại mất cân bằng cần phân biệt

### 4.1. Skew theo chunks/ranges

~~~text
shard01: 500 ranges
shard02: 120 ranges
shard03: 110 ranges
~~~

Đây là **chunk-count skew**. Nhưng chưa chứng minh shard01 chứa phần lớn bytes.

### 4.2. Skew theo owned data

~~~text
shard01: 720 GiB owned
shard02: 300 GiB owned
shard03: 280 GiB owned
~~~

Đây là **logical data skew**. Cần biết metric có loại orphaned documents và indexes không, có gom nhiều collections không.

### 4.3. Skew theo disk vật lý

~~~text
shard01: 88% disk full
shard02: 60% disk full
shard03: 58% disk full
~~~

Disk skew có thể do owned data, indexes, orphan cleanup, fragmentation, oplog, unsharded collections hoặc hardware capacities khác nhau. Không kết luận balancer hỏng chỉ vì tỷ lệ đầy ổ khác nhau.

### 4.4. Skew theo workload

~~~text
shard01: write QPS=8000, CPU=90%
shard02: write QPS=1000, CPU=35%
shard03: write QPS=1000, CPU=32%
~~~

Đây là **hot shard**. Ngay cả khi owned bytes đều, nhóm khách hàng/thiết bị đang hoạt động mạnh có thể dồn writes vào một shard key range.

**Balancer di chuyển ranges, không tự chia một shard-key value đang quá nóng** theo thiết kế partition hiện có. Có thể cần shard key tốt hơn, bổ sung yếu tố phân phối hoặc resharding.

### 4.5. Zone-induced skew có thể là chủ đích

~~~text
zone: EU    -> shard01, shard02
zone: APAC  -> shard03
~~~

Nếu dữ liệu APAC lớn hơn EU, shard03 có thể nhiều bytes hơn. Balancer vẫn tuân thủ zone placement, nên so **mức cân bằng trong mỗi zone/eligible shard set** thay vì buộc mọi shard bằng nhau.

## 5. Nguồn dữ liệu quan sát và cấp quyền

Một thao tác điều tra cần biết rõ đang kết nối tới thành phần nào:

| Nguồn | Cách truy cập | Điều quan sát chính |
|---|---|---|
| **mongos** | mongosh kết nối MongoDB URI của router | Tổng quan sharding, list shards, balancer status, phân bố collection. |
| **Config server** | Tool quản trị được hỗ trợ, monitoring | Metadata placement, CSRS member health, migration log. |
| **Shard primary** | Kết nối có kiểm soát tới từng shard replica set | CPU, cache, disk, opcounters, write latency, replication status. |
| **Shard secondary** | Monitoring từng member | Replication lag, disk, cache, read workload nếu có. |
| **Ứng dụng** | Traces, logs, service metrics | Read/write latency, error rate, query patterns và tenant hot spots. |
| **Hạ tầng** | Atlas monitoring, Prometheus/exporter, OS metrics | Disk capacity, IOPS, memory, network, CPU throttling. |

Không gộp các metrics từ các thành phần khác nhau thành một con số mà không hiểu vai trò.

### 5.1. Điều kiện kết nối và quyền truy cập

Các lệnh sharding thường cần kết nối qua **mongos** và một tài khoản có quyền đọc thông tin cluster. Các metrics nhạy cảm, config metadata và operational commands có thể cần quyền cao hơn như **clusterMonitor**, quyền quản trị tương ứng hoặc monitoring role do tổ chức tạo.

Một ví dụ kết nối:

~~~bash
mongosh "mongodb://router1.example:27017,router2.example:27017/admin?authSource=admin" \
  --username monitoring-user
~~~

Ứng dụng/driver có thể yêu cầu TLS và password/secret manager. Không nhúng thông tin bí mật vào shell history hoặc dashboard config.

### 5.2. Nguyên tắc ít quyền

**Observability account** nên đọc metrics, trạng thái và metadata cần thiết, không có quyền thay shard placement, dừng balancer, xóa metadata hoặc đổi collection shard key.

Phân tách:

~~~text
monitoring account:
  observe status, metrics, logs

operations account:
  approved balancer/cluster administration

application account:
  normal CRUD through mongos
~~~

Tránh dùng một tài khoản root cho mọi dashboard service.

### 5.3. Dùng dữ liệu được hỗ trợ trước, config metadata sau

Một thứ tự nguồn thông tin nên ưu tiên:

1. **Atlas/Cluster Monitoring** hoặc metrics được nhà cung cấp hỗ trợ.
2. **sh.status(), balancerStatus, listShards**, các helper/commands quản trị được công bố.
3. **getShardDistribution(), $collStats**, collection-level statistics có kiểm soát.
4. **config database/changelog read-only** khi cần điều tra sâu và có hiểu biết về schema version.

Schema metadata nội bộ có thể thay đổi giữa các phiên bản MongoDB. Không biến một query trực tiếp config.chunks thành một API production phụ thuộc cố định nhiều năm nếu đã có công cụ chính thức phù hợp.

## 6. Kiểm tra shards bằng mongosh

Các ví dụ trong mục này dùng **lệnh đọc trạng thái** trên một cluster được phép quan sát. Chúng không tạo/xóa/migrate dữ liệu.

### 6.1. Kết nối qua mongos

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Thông tin trả về giúp nhận diện thành phần kết nối. Khi kết nối đúng mongos, kết quả thường có dấu hiệu nhận diện router, ví dụ **msg: "isdbgrid"**. Không dùng lệnh dành cho replica-set primary trên một mongos và ngược lại.

### 6.2. Liệt kê shard

~~~javascript
db.adminCommand({ listShards: 1 });
~~~

Đầu ra điển hình mang thông tin shard IDs, hosts/replica set connection strings và các chi tiết khác tùy phiên bản:

~~~javascript
{
  shards: [
    { _id: "shard01", host: "rsShard01/s01a:27017,s01b:27017,s01c:27017" },
    { _id: "shard02", host: "rsShard02/s02a:27017,s02b:27017,s02c:27017" },
    { _id: "shard03", host: "rsShard03/s03a:27017,s03b:27017,s03c:27017" }
  ],
  ok: 1
}
~~~

**Ví dụ này chỉ minh họa cấu trúc**, không phải output được xác minh từ một cluster thực. Trong production, danh sách shard hosts có thể được coi là thông tin hạ tầng nhạy cảm; giới hạn nơi lưu/log.

Quan sát:

- Số shards thực tế khác số dự kiến không?
- Có shard vừa được add hoặc ở trạng thái removal/draining không?
- Replica set names và hostnames có khớp inventory không?
- Có lỗi mạng, TLS hoặc DNS ảnh hưởng một shard không?

### 6.3. Tổng quan phân vùng bằng sh.status()

~~~javascript
sh.status();
~~~

Các phiên bản mongosh hỗ trợ một số mức hiển thị/verbose:

~~~javascript
sh.status(true);
~~~

Kết quả có thể cho biết:

- Shards và host mappings.
- Collections đã sharded.
- Shard key của collection.
- Ranges/chunks được đặt trên những shards nào.
- Thông tin zones/tags và balancer state tùy phiên bản.
- Một số tóm tắt migration hoặc chunk distribution khi có.

**Không coi mọi con số và format của sh.status là ổn định giữa MongoDB versions**. Nếu collection có rất nhiều ranges, output verbose có thể rất dài; đừng gửi toàn bộ kết quả vào log/CI artifacts không giới hạn.

### 6.4. Đúng namespace và shard key

Giả sử cần kiểm tra collection **commerce.orders**:

~~~javascript
use commerce
sh.status();
~~~

Xác định:

1. Collection có thật sự được sharded không?
2. Shard key là **{customerId:"hashed"}** hay **{createdAt:1}**, hay một compound key?
3. Các chunks được phân bố ra sao?
4. Có zone ranges hoặc shard-specific constraints?
5. Tác vụ resharding/repartition có đang diễn ra?

Không thể suy hướng migration chỉ từ tên database; phải tìm đúng **fully qualified namespace**.

### 6.5. getShardDistribution() cho collection cụ thể

Trong những phiên bản mongosh hỗ trợ, helper:

~~~javascript
db.getSiblingDB("commerce")
  .orders
  .getShardDistribution();
~~~

có thể tóm tắt phân bố dữ liệu/ước lượng và chunks theo shard. Nội dung, các phép ước lượng và format output có thể thay đổi theo phiên bản và cách lệnh lấy thống kê.

Các câu hỏi cần trả lời:

- Có shard nào lưu phần lớn dữ liệu collection?
- Số chunks có đi cùng kích thước không?
- Shard mới đã bắt đầu nhận data chưa?
- Có bất thường giữa logical ownership và physical storage?

Không xem sample output như số liệu chính xác tuyệt đối trong khi migrations đang hoạt động.

### 6.6. Collection-level statistics qua $collStats

MongoDB hỗ trợ aggregation **$collStats** trong các phiên bản phù hợp; dùng khi muốn xem count/storage stats của collection.

~~~javascript
db.getSiblingDB("commerce").orders.aggregate([
  {
    $collStats: {
      storageStats: {
        scale: 1048576
      },
      count: {}
    }
  }
]);
~~~

**scale=1048576** thường cho các kích thước hiển thị ở MiB đối với fields áp dụng scaling. Output fields và cách thể hiện per-shard/tổng thể phụ thuộc version và cấu hình; kiểm tra ý nghĩa từng metric trước khi tính tỷ lệ.

**$collStats phải đứng ở vị trí được stage yêu cầu, thông thường là stage đầu tiên**; không đặt $match trước để hạn chế các documents như aggregation bình thường.

Nếu câu lệnh trên cluster cụ thể không hỗ trợ option hoặc trả một dạng khác, dùng các metrics collection được MongoDB version đó khuyến nghị. Không thay bằng tổng kích thước database và gán cho collection đang điều tra.

### 6.7. Xem health của shard replica sets

Nếu có quyền và được phép kết nối trực tiếp từng shard replica set cho mục đích monitoring:

~~~javascript
rs.status();
~~~

Kiểm tra các thành viên:

- Primary có ổn định không?
- Secondaries đang HEALTHY không?
- Replication lag bao nhiêu?
- Oplog retention và network có theo kịp writes/migrations không?

Không chạy rs.status() trên mongos rồi kết luận shard replica set healthy; mongos không phải member replica set của shard.

### 6.8. Phân biệt trạng thái shard với khả năng kết nối

**listShards trả shard trong metadata** không đồng nghĩa tất cả members của shard đó đều khỏe hoặc có đủ disk space.

Phải kết hợp:

~~~text
listShards
    +
replica set/member health
    +
CPU/disk/network metrics
    +
query latency and errors
~~~

Một shard có tên trong danh sách nhưng primary đang election hoặc disk gần hết có thể khiến migrations bị chậm/gián đoạn.

## 7. Kiểm tra balancer: enabled không có nghĩa đang chuyển dữ liệu

Balancer có thể **enabled** nhưng chờ điều kiện, không có range cần chuyển, hoặc migration bị chặn. Cần phân biệt:

~~~text
Balancer configured / enabled?
          |
          v
Currently in a balancer round?
          |
          v
Migration selected / started?
          |
          v
Migration progressing / committed / failed?
          |
          v
Distribution changed toward desired placement?
~~~

### 7.1. balancerStatus

Kết nối mongos với quyền phù hợp:

~~~javascript
db.adminCommand({ balancerStatus: 1 });
~~~

Output minh họa, fields phụ thuộc server version:

~~~javascript
{
  mode: "full",
  inBalancerRound: false,
  numBalancerRounds: 12,
  ok: 1
}
~~~

- **mode** mô tả chế độ hoạt động theo server version.
- **inBalancerRound** cho biết có đang ở vòng balancer lúc quan sát không, khi field này được cung cấp.
- **numBalancerRounds** cho biết tiến trình các vòng, **không phải số migrations thành công**.
- **ok:1** nghĩa lệnh chạy thành công, **không chứng minh collection đã cân bằng**.

### 7.2. Trạng thái enabled

Trong mongosh trên cluster hỗ trợ:

~~~javascript
sh.getBalancerState();
~~~

Hàm phản ánh trạng thái cấu hình balancer, khác với “đang migration ngay lúc này”.

~~~text
Balancer enabled: true
In balancer round: false
~~~

Đây vẫn có thể là trạng thái bình thường khi không cần migration hoặc chưa đến vòng xử lý.

### 7.3. Collection-level balancer status

Một số MongoDB versions hỗ trợ:

~~~javascript
db.adminCommand({
  balancerCollectionStatus: "commerce.orders"
});
~~~

Output có thể nêu **placement compliance** hoặc nguyên nhân chưa compliance, tùy version. Kiểm tra tài liệu của server đang chạy trước khi viết alert dựa trên field cụ thể.

### 7.4. Balancer windows và maintenance

Cluster có thể cấu hình **balancer window**. Nếu ngoài cửa sổ, enabled nhưng chưa migration là dự kiến.

Theo dõi:

1. Balancer global enabled/disabled.
2. Balancing window theo timezone nào?
3. Hiện có nằm trong window không?
4. Có maintenance, resharding hoặc other conflicts?
5. Có collection-specific placement constraints?

Không tự mở balancing ngoài cửa sổ được duyệt chỉ để dashboard “đều” hơn.

### 7.5. Đủ điều kiện nhưng không cần migration

Balancer có thể không làm gì khi:

- Owned data đã đủ cân bằng theo ngưỡng/chính sách.
- Ranges đang ở eligible shards theo zones.
- Không có range có thể chuyển phù hợp kích thước/placement.
- Cluster ngoài balancing window.
- Collection không được cân bằng trong chế độ hiện tại.

**Không có migration không tự đồng nghĩa lỗi.**

### 7.6. Không tự restart balancer khi chưa có bằng chứng

Các APIs bật/dừng balancer thay đổi cluster behavior và có thể ảnh hưởng user-facing latency. Chỉ vận hành khi có change approval, hiểu version và có rollback/monitoring.

Restart balancer không sửa được shard key cardinality thấp hoặc zone chỉ có một eligible shard.

## 8. Range migration: điều gì cần quan sát?

~~~text
                       Balancer
                          |
                 Select eligible range
                          |
                          v
           +------------------------------+
           | Donor shard (source)         |
           | currently owns range R1      |
           +------------------------------+
                          |
                Transfer/clone data
                          |
                          v
           +------------------------------+
           | Recipient shard (target)     |
           | receives range contents      |
           +------------------------------+
                          |
                Catch up concurrent writes
                          |
                Commit placement metadata
                          |
             New owner = recipient shard
                          |
              Orphan cleanup on donor
~~~

Các phase/RPC/điều kiện commit thay đổi theo MongoDB version. Sơ đồ chỉ minh họa vai trò.

### 8.1. Donor và recipient

- **Donor** sở hữu range trước migration.
- **Recipient** nhận data và ownership sau khi commit.
- **Config metadata** cập nhật khi ownership chuyển.
- **Mongos** dùng metadata mới để định tuyến.

Recipient bắt đầu chứa copied data chưa có nghĩa migration đã commit.

### 8.2. Vì sao migration có thể chậm?

- Đọc data và indexes trên donor.
- Ghi data/indexes trên recipient.
- Truyền qua network.
- Theo kịp writes phát sinh trong quá trình clone.
- Chờ các điều kiện replication/durability.
- Commit metadata và cleanup.

Latency phụ thuộc size, write churn, disk IOPS, network, replication lag, topology và tải ứng dụng.

### 8.3. Commit chưa chắc làm disk donor giảm ngay

~~~text
Logical range owner: recipient
Donor may still have orphaned copies
Recipient has copied data
~~~

Theo dõi cả **owned bytes** và **physical storage**, cộng với orphan cleanup.

### 8.4. Migrations lặp lại thất bại

Những nguyên nhân thường cần điều tra:

- Donor/recipient quá tải disk hoặc thiếu free space.
- Primary election, replication lag, network/TLS/DNS errors.
- Range oversized/jumbo hoặc không thể chia như mong đợi.
- Zone placement constraints không tương thích.
- CSRS không khỏe, metadata operations bị chặn.
- Balancing window quá ngắn.
- Active resharding, maintenance hoặc operations xung đột.

Chỉ tăng tốc migration sau khi xác định bottleneck; tăng tải di chuyển có thể làm latency ứng dụng xấu hơn.

### 8.5. Mới thêm một shard

~~~text
Before adding shard03:
  shard01: 500 GiB
  shard02: 500 GiB

Immediately after:
  shard01: 500 GiB
  shard02: 500 GiB
  shard03: ~0 GiB
~~~

Shard mới trống vài phút đầu có thể bình thường. Nếu sau nhiều vòng vẫn không nhận data, kiểm tra listShards, sharding key, zones, balancer/window, eligible ranges, disk/network và migration logs.

### 8.6. Tác động tới ứng dụng

Trong balancing có thể thấy:

~~~text
network bytes/sec increases
disk read/write IOPS increases
cache pressure increases
replication lag increases
application p95 latency rises temporarily
~~~

Do đó **dashboard migrations phải đứng cạnh dashboard độ trễ ứng dụng**, không theo dõi số bytes chuyển mà bỏ qua SLA.

## 9. Đọc lịch sử migration và metadata placement

### 9.1. config database là nguồn thông tin nội bộ nhạy cảm

MongoDB lưu nhiều metadata và một số log quản trị trong **config** database của sharded cluster.

Khi cần điều tra sâu:

~~~javascript
const configDb = db.getSiblingDB("config");
~~~

Việc xem metadata được thực hiện với quyền thích hợp và **read-only**. Không chạy updateMany/deleteMany/insert để “sửa” config.chunks, config.collections hoặc config.shards. Những writes không được hỗ trợ có thể làm hỏng routing/placement.

### 9.2. Lịch sử sự kiện migration

Ở các versions có **config.changelog**:

~~~javascript
db.getSiblingDB("config").changelog.find(
  {
    what: { $regex: "^moveChunk" }
  },
  {
    _id: 0,
    time: 1,
    what: 1,
    ns: 1,
    details: 1
  }
).sort({ time: -1 }).limit(30);
~~~

Các event names, document fields, log retention và semantics khác nhau tùy version. Dạng **moveChunk.\*** chỉ là một convention được gặp ở một số releases; nếu không trả bản ghi, không thể kết luận chắc chắn “không có migration”.

Đối chiếu với:

- Balancer status/rounds.
- MongoDB server logs có correlation/time.
- Atlas/Ops Manager metrics.
- Placement/size measurements trước và sau.

### 9.3. Event types phải được hiểu theo giai đoạn

Một lịch sử có event:

~~~text
moveChunk.start
moveChunk.commit
moveChunk.error
~~~

không được diễn giải theo việc một event xuất hiện đơn lẻ:

- **start** chưa chắc kết thúc thành công.
- **commit** là tín hiệu quan trọng hơn về ownership change.
- **error/abort** cần tìm reason và xem retry sau đó.

Tên cụ thể có thể khác theo version. Không viết alert hardcoded chỉ phụ thuộc một chuỗi event legacy.

### 9.4. Xem metadata collection và shard key

Trong một số versions, collection metadata có namespace dưới **config.collections._id**:

~~~javascript
db.getSiblingDB("config").collections.findOne(
  { _id: "commerce.orders" }
);
~~~

Có thể thấy fields như **key** (shard key), **uuid** và các metadata khác. Những fields này là internal/administrative representation và không nên bị chỉnh sửa trực tiếp.

Không đồng nhất việc collection nằm trong config.collections với trạng thái hiện tại của mọi range khi cluster đang resharding/migration.

### 9.5. Xem số ranges theo shard của một collection

Chỉ dùng để **khảo sát read-only** trên versions có schema metadata phù hợp; ưu tiên helper chính thức khi có:

~~~javascript
const cdb = db.getSiblingDB("config");
const ns = "commerce.orders";
const collMeta = cdb.collections.findOne({ _id: ns });

if (!collMeta) {
  print("Collection metadata not found");
} else {
  const selector = collMeta.uuid
    ? { uuid: collMeta.uuid }
    : { ns: ns };

  cdb.chunks.aggregate([
    { $match: selector },
    {
      $group: {
        _id: "$shard",
        rangeCount: { $sum: 1 }
      }
    },
    { $sort: { rangeCount: -1 } }
  ]).forEach(printjson);
}
~~~

**Cảnh báo:** việc chunks metadata dùng **uuid** hay **ns**, cũng như field names, indexes và representation, thay đổi theo server version. Đoạn code dùng nhánh minh họa, không bảo đảm đúng với mọi deployment; dùng để hiểu cách đọc metadata chứ không làm parser production bất biến.

Số ranges theo shard **không bằng** tổng bytes hoặc QPS. Nếu cluster có rất nhiều ranges, aggregate metadata cũng cần được giới hạn/tối ưu trong quá trình monitoring.

### 9.6. Xem metadata zones

Zones/tags và phân đoạn shard key có thể được phản ánh trong các metadata collections như **config.tags** hoặc output **sh.status()**, tùy phiên bản.

~~~javascript
db.getSiblingDB("config").tags.find().limit(20);
~~~

Thực tế cần biết:

1. Zone nào gán cho shards nào?
2. Key ranges nào có zone constraint?
3. Có một range nằm trong zone nhưng không có eligible shard không?
4. Có giới hạn vùng địa lý, residency hoặc hardware-specific storage không?

Không tự xóa zone tags để balancer “bớt lệch” khi đó là yêu cầu về data residency.

### 9.7. Theo dõi trạng thái đang diễn ra

Khi có migration lâu bất thường, có thể kết hợp cluster metrics, server logs và công cụ current operations được MongoDB version hỗ trợ. Không dựa vào một thao tác currentOp có output lớn hoặc chứa thông tin nhạy cảm để tạo dashboard thường trực.

Nếu dùng:

~~~javascript
db.adminCommand({ currentOp: 1 });
~~~

hãy lưu ý:

- Quyền gọi có thể cao.
- Output có thể nhiều và chứa query text/namespace/host details.
- Một operation ngắn có thể biến mất trước khi được lấy mẫu.
- Tên operation/field mô tả migration không ổn định xuyên versions.

Với pipeline metrics lâu dài, ưu tiên nguồn metrics chính thức và logs được chuẩn hóa.

## 10. Đo mức lệch phân bố dữ liệu có ý nghĩa

Không chỉ nhìn một chart, hãy định nghĩa **đơn vị, phạm vi, thời điểm và mẫu số** của mỗi metric.

### 10.1. Data share per shard

Giả sử có ba shards với owned data bytes:

~~~text
shard01 = 600 GiB
shard02 = 300 GiB
shard03 = 300 GiB
total   = 1200 GiB
~~~

Tính:

~~~text
dataShare(shard01) = 600 / 1200 * 100% = 50%
dataShare(shard02) = 300 / 1200 * 100% = 25%
dataShare(shard03) = 300 / 1200 * 100% = 25%
~~~

Đây là phép đo phân bố bytes của một **phạm vi cụ thể**. Nếu tổng bytes lấy từ cả database nhưng chart ghi tên một collection, sẽ dẫn tới kết luận sai.

### 10.2. Max-to-average skew ratio

Với N shards:

~~~text
averageOwnedBytes = sum(ownedBytes[i]) / N

maxToAverageSkew = max(ownedBytes[i]) / averageOwnedBytes
~~~

Ở ví dụ:

~~~text
averageOwnedBytes = (600+300+300)/3 = 400 GiB
maxToAverageSkew  = 600/400 = 1.5
~~~

Diễn giải: shard lớn nhất có owned bytes **1,5 lần mức trung bình**.

### 10.3. Max-to-min ratio

~~~text
maxToMinSkew = max(ownedBytes[i]) / min(ownedBytes[i])
~~~

Ví dụ:

~~~text
600 / 300 = 2
~~~

Nhưng khi shard mới có **0 bytes**, mẫu số bằng 0 nên tỷ lệ này không hữu ích/không xác định. Không vẽ giá trị vô cực rồi kết luận cluster “hỏng”; dùng max-to-average, absolute bytes và age since added shard.

### 10.4. Percent deviation from mean

~~~text
relativeDeviation(i) =
  (ownedBytes[i] - averageOwnedBytes) / averageOwnedBytes * 100%
~~~

Ví dụ:

~~~text
shard01: (600-400)/400 = +50%
shard02: (300-400)/400 = -25%
shard03: (300-400)/400 = -25%
~~~

Metric này diễn giải trực quan nhưng vẫn phụ thuộc vào điều kiện all shards equally eligible/capable.

### 10.5. Coefficient of variation (CV)

Đôi khi cần một số tổng hợp mức độ phân tán:

~~~text
mean = sum(x[i]) / N
stdDevPopulation = sqrt(sum((x[i]-mean)^2) / N)
CV = stdDevPopulation / mean
~~~

CV gần 0 biểu thị phân bố gần đều theo metric đang đo. **CV không mô tả nguyên nhân**, và cần tránh dùng khi mean gần 0 hoặc một zone không thể đặt dữ liệu lên mọi shard.

### 10.6. Data distribution khác capacity distribution

Nếu shards có phần cứng không bằng nhau:

| Shard | Owned bytes | Disk capacity | Tỷ lệ owned/capacity |
|---|---:|---:|---:|
| shard01 | 600 GiB | 2.000 GiB | 30% |
| shard02 | 300 GiB | 500 GiB | 60% |
| shard03 | 300 GiB | 500 GiB | 60% |

Nếu bắt owned bytes bằng nhau, các shards nhỏ có thể gần hết disk hơn shard lớn. Một số chiến lược balancing không tự cân bằng theo phần cứng không đồng nhất như business kỳ vọng; cần thiết kế topology và capacity planning rõ.

**So sánh percent disk used, free bytes, absolute bytes và eligible placement**, không chỉ data share.

### 10.7. Skew theo từng collection và theo toàn cluster

Giả sử:

~~~text
commerce.orders:
  shard01 90%, shard02 5%, shard03 5%

analytics.events:
  shard01 5%, shard02 47.5%, shard03 47.5%
~~~

Tổng disk có thể khá đều do hai collections bù nhau, nhưng **commerce.orders** vẫn cực kỳ lệch. Để chẩn đoán write hot spot, cần metrics **theo collection, shard key và workload**, không chỉ tổng GB cluster.

### 10.8. Skew theo xu hướng, không phải một điểm

Thu thập mỗi vài phút:

~~~text
time, namespace, shardId, ownedBytes, chunkCount,
qps, cpuPct, diskUsedBytes, diskFreeBytes,
balancerEnabled, migrationsStarted, migrationsFailed
~~~

Theo dõi sau khi:

- Add shard.
- Thay workload.
- Bật/tắt balancing window theo chính sách.
- Reshard collection.
- Đổi zone tags.
- Di chuyển một tenant lớn.

Mức lệch nhẹ, ổn định có thể chấp nhận được; độ lệch **tăng liên tục** cần ưu tiên điều tra.

### 10.9. Cẩn trọng với metrics được ước lượng

Một số output về số documents, data size hoặc chunks trên sharded collection là **ước lượng hoặc được lấy từ snapshots/metadata**. Trong migrations, orphan cleanup hoặc sau restore, con số này có thể tạm thời lệch với phép đếm chính xác trên dữ liệu sở hữu.

Không dùng sự chênh vài phần trăm của hai metric có định nghĩa khác nhau để phát alarm corruption.

## 11. Shard key và nguyên nhân gây hot shard

Balancer chủ yếu điều chỉnh **placement của các ranges**. Nếu phần lớn thao tác ứng dụng liên tục đổ vào cùng range hoặc shard-key value, di chuyển các ranges khác không giải quyết trực tiếp.

### 11.1. Range-based shard key tăng đơn điệu

Giả sử collection events có shard key:

~~~javascript
{ createdAt: 1 }
~~~

Với nhiều writes có timestamp hiện tại tăng theo thời gian:

~~~text
Shard key range:
  old timestamps          latest timestamps
  |-----------|-----------|-----------|
                                ^
                                |
                          all new writes
~~~

Inserts với createdAt mới liên tục có thể tập trung vào range ở rìa keyspace, tạo **write hot spot**.

Balancer có thể di chuyển ranges cũ nhưng writes mới vẫn dồn vào range chứa timestamp hiện tại. **Data balance không bảo đảm write balance.**

### 11.2. Hashed shard key

Một lựa chọn khác:

~~~javascript
{ customerId: "hashed" }
~~~

Hashed shard key phân tán các values trên hash space để tránh dồn liên tục theo một dãy ID tăng dần.

Tuy nhiên:

- Nếu một **customerId** duy nhất tạo 80% writes, workload của giá trị đó vẫn có thể quá nóng.
- Hashed sharding không duy trì locality tự nhiên cho queries theo khoảng customerId.
- Equality query trên customerId có thể được targeted, nhưng query thiếu shard key có nguy cơ scatter-gather.
- Hashed distribution không thay thế đánh giá cardinality, frequency và query patterns.

### 11.3. Cardinality và frequency

Phân tích shard key theo:

1. **Cardinality:** có bao nhiêu values khác nhau?
2. **Frequency:** có một value nào áp đảo records/operations?
3. **Monotonicity:** values mới liên tục tăng/giảm?
4. **Query targeting:** phần lớn queries có điều kiện shard key cần thiết?
5. **Index/sharding constraints:** field type, uniqueness, collation có hợp lệ?
6. **Growth:** khi tăng tenants/devices, skew thay đổi thế nào?

Không chọn shard key chỉ vì field đó có trong mỗi document.

### 11.4. Compound shard key

Ví dụ:

~~~javascript
{ tenantId: 1, orderId: "hashed" }
~~~

Mô hình compound key có thể bổ sung entropy cho orders cùng tenant (tùy quy tắc compound hashed shard key/server version), nhưng cần xem query targeting, index requirements, zone sharding và access patterns.

Đặt câu hỏi:

- Có bao nhiêu tenants?
- Một tenant có thể vượt tải một shard không?
- Queries chủ yếu theo tenantId, orderId hay cả hai?
- Có yêu cầu zone/data residency theo tenant?
- Có cần range query theo orderId?

Không mặc định mọi compound hashed key vừa có perfect locality vừa có perfect load balance.

### 11.5. Cardinality cao nhưng vẫn hot

Giả sử 10 triệu customer IDs, nhưng **C-00001** chiếm 45% writes:

~~~text
Total IDs:     10,000,000
Hot ID:        C-00001
Hot write share: 45%
~~~

Cardinality cao không giải quyết hot key. Cần phân tích **top shard-key values theo read/write QPS**, không chỉ distinct count.

### 11.6. Query targeting

Collection sharded theo customerId, nhưng ứng dụng thường chạy:

~~~javascript
db.orders.find({ status: "PENDING" });
~~~

Không có shard-key predicate nên query có thể bị scatter-gather. Balancer không tự sửa được query pattern này.

Truy vấn targeted hơn:

~~~javascript
db.orders.find({
  customerId: "C-00001",
  status: "PENDING"
});
~~~

Targeting chính xác phụ thuộc shard-key pattern, index, collation và planner/version. Cần kiểm tra **explain**, không chỉ suy theo tên field.

### 11.7. Explain qua mongos

~~~javascript
db.getSiblingDB("commerce")
  .orders
  .find({ customerId: "C-00001" })
  .explain("executionStats");
~~~

Quan sát shard stages/targeted shards, keys/docs examined và latency theo output version. Không chạy explain có thể quét toàn collection trên production giờ cao điểm nếu không kiểm soát chi phí.

### 11.8. Biện pháp theo nguyên nhân

| Nguyên nhân | Hướng xem xét |
|---|---|
| Inserts theo timestamp tăng dần | Shard key/hash/compound pattern, partition strategy. |
| Một tenant quá lớn | Bổ sung entropy, resharding hoặc application-level partitioning. |
| Queries thiếu shard key | Query patterns, indexes, API design. |
| Hardware một shard yếu | Capacity planning, không chỉ move range. |
| Hot range có thể move | Move chỉ chuyển nơi bị nóng, chưa chia tải. |
| Zone chỉ có một eligible shard | Mở rộng eligible capacity nếu policy cho phép. |

**Resharding có chi phí và rủi ro**, không phải bước chẩn đoán đầu tiên.

## 12. Zone sharding: balancing trong phạm vi được phép

Zone sharding giúp đặt ranges trên các shards tương ứng với zone, phục vụ data residency, workload isolation hoặc storage tiers.

### 12.1. Ví dụ phân chia zones

~~~text
Zone "EU"   -> shard01, shard02
Zone "APAC" -> shard03

Tenant key ranges:
  EU tenants   -> EU zone
  APAC tenants -> APAC zone
~~~

Nếu APAC có 70% dữ liệu nhưng chỉ shard03 eligible, shard03 chứa nhiều bytes hơn **không nhất thiết là balancer bug**.

### 12.2. Zone compliance khác global evenness

| Zone | Eligible shards | Dữ liệu |
|---|---|---:|
| EU | shard01, shard02 | 600 GiB |
| APAC | shard03 | 900 GiB |

Mục tiêu hợp lệ:

~~~text
EU: shard01 300 GiB, shard02 300 GiB
APAC: shard03 900 GiB
~~~

Balancer không thể chuyển dữ liệu APAC sang shard01 khi shard01 không eligible trong zone đó.

### 12.3. Chẩn đoán zone skew

1. Xác định namespace và shard key.
2. Đọc zone key ranges và shard-zone associations.
3. Kiểm tra số eligible shards/capacity trong mỗi zone.
4. Đo owned bytes và CPU **trong từng zone**.
5. Kiểm tra placement compliance và stuck migrations.
6. Xác nhận data residency requirements trước mọi thay đổi.

### 12.4. Zone constraints gây migration failures

Range có thể không move được khi thiếu recipient eligible, recipient hết disk, oversized range hoặc metadata thay đổi trong lúc vận hành.

Thêm một shard **ngoài zone** không nhất thiết giúp cân bằng dữ liệu của zone đó. Không sửa zone tags để “cho đều” nếu đang thực thi yêu cầu pháp lý/hợp đồng.

## 13. Jumbo và oversized ranges

Một range quá lớn hoặc không có split point phù hợp có thể khó migration, đặc biệt khi nhiều documents có cùng shard-key value.

### 13.1. Không thể chia một shard-key value tùy ý

~~~text
Shard key:
  customerId = C-00001

Millions of documents with identical shard-key value.
~~~

Nếu không có boundary hợp lệ, không thể “cắt đôi” cùng một shard-key value để tách writes sang hai shards mà vẫn giữ semantics của shard key.

### 13.2. Jumbo marker và giới hạn phiên bản

MongoDB versions khác nhau về jumbo marker, range sizing và migration behavior. Không suy rằng:

~~~text
one range > target chunk size
  -> every migration necessarily impossible
~~~

Một oversized range có thể được chuyển hoặc bị từ chối tùy server version, size constraints và flags. Phải đọc lỗi cụ thể và tài liệu đúng version.

### 13.3. Chẩn đoán jumbo

Kiểm tra:

- Namespace, shard key và range boundaries.
- Owned bytes và số records của range.
- Phân bố distinct shard-key values.
- Error logs/reason của migration.
- Zone placement và recipient eligibility.
- Một hot key có đang tăng liên tục?

### 13.4. Không force move tùy tiện

Force migration có thể tăng tải disk/network, làm latency xấu đi, vi phạm placement policy hoặc vẫn không chia được hot key. Đây là tác vụ vận hành cần approval, không phải logic của dashboard quan sát.

Nếu nguyên nhân là thiếu entropy, xem lại shard key, compound key hoặc resharding; **thêm shard không tự chia một key value duy nhất**.

## 14. Theo dõi sức khỏe mỗi shard replica set

Khi phân bố dữ liệu lệch, không chỉ cần hỏi “range nào nằm ở đâu?”, mà phải kiểm tra “shard đó có đủ khả năng xử lý migrations và workload không?”.

### 14.1. Một shard là một replica set có primary/secondaries

Theo dõi:

| Nhóm metrics | Tín hiệu |
|---|---|
| **Replica-set health** | Primary hiện tại, số members available, elections, health status. |
| **Replication** | Replication lag, oplog window, khả năng catch up. |
| **Operations** | Read/write ops/s, queues/concurrency, latency. |
| **WiredTiger cache** | Cache pressure, dirty data, eviction activity. |
| **Storage** | Free space, IOPS, read/write throughput, latency, index sizes. |
| **Network** | Transfer bytes/s, retransmits, latency donor↔recipient. |
| **Resource limits** | CPU saturation, memory pressure, disk throttling. |

Mỗi group có thể chứa nhiều members. Đừng lấy CPU primary của shard01 rồi so với CPU secondary của shard02 và kết luận primary loads lệch.

### 14.2. serverStatus theo từng mongod

Kết nối có quyền tới từng member:

~~~javascript
const status = db.adminCommand({ serverStatus: 1 });

printjson({
  host: status.host,
  uptime: status.uptime,
  opcounters: status.opcounters,
  connections: status.connections,
  network: status.network,
  opLatencies: status.opLatencies
});
~~~

Kết quả có các counters/gauges tùy version; một số field có thể không được cung cấp ở mọi node/edition. **Không log toàn bộ serverStatus ra nơi công khai** vì nó có thể chứa thông tin hạ tầng.

### 14.3. Counters phải được chuyển thành rates

Một field counter như tổng operations kể từ khi process khởi động:

~~~text
readsCounter(t0) = 1,000,000
readsCounter(t1) = 1,060,000
deltaTime        = 60 seconds

readRate = (1,060,000 - 1,000,000) / 60
         = 1,000 ops/sec
~~~

Không vẽ giá trị counter tích lũy trực tiếp như “QPS”.

Cần xử lý:

- Counter reset khi mongod restart/election.
- Missing samples.
- Quy tắc dữ liệu metrics khác nhau theo version.
- Tốc độ đo và tính cùng một role/member.

### 14.4. WiredTiger cache

Khi cache bị ép, balancer migration và ứng dụng có thể cạnh tranh I/O/CPU. Theo dõi cache usage/eviction/dirty bytes qua metrics được hỗ trợ, ví dụ các fields dưới **serverStatus.wiredTiger.cache** khi có.

Không suy rằng “cache used 95%” luôn là lỗi: database cache thường cố tận dụng memory. Quan trọng hơn là **eviction pressure, latency và disk I/O trends**.

### 14.5. Oplog và replication lag

Migration/clone và ghi liên tục tăng tải replication. Nếu secondary không theo kịp, cluster có thể chịu:

- Durability/replication-related waits.
- Oplog window bị thu hẹp.
- Secondary reads stale hơn.
- Những thay đổi primary/election gây gián đoạn.

Theo dõi **replication lag** và **oplog window** ở từng shard replica set; cũng theo dõi CSRS nếu có sự cố metadata operations.

### 14.6. Network và disk trong migration

Một migration chuyển dữ liệu lớn có thể tạo network throughput cao trên donor/recipient và tăng disk reads/writes. Hỏi:

- Network đã gần giới hạn link chưa?
- Disk IOPS hoặc latency có tăng bất thường?
- CPU cao do query workload hay do migration?
- Client p95 latency có tăng cùng lúc?

Nếu chỉ nhìn CPU, dễ nhầm traffic migration với hot-key writes.

### 14.7. Disk free space và capacity runway

Một shard nhận data cần **đủ free space cho migration và overhead**. Theo dõi cả:

~~~text
diskUsedBytes
diskFreeBytes
diskCapacityBytes
writeGrowthBytesPerDay
migrationIncomingBytesPerDay
estimatedDaysToCapacity
~~~

Với tốc độ tăng trưởng gần ổn định:

~~~text
daysToCapacity ≈ usableFreeBytes / netGrowthBytesPerDay
~~~

Đây là ước lượng capacity planning, không là lời hứa. Balancer có thể đồng thời chuyển data vào/ra, compression và cleanup làm growth thay đổi.

## 15. Chọn metrics dashboard để thấy cả phân bố và hiệu năng

Một dashboard sharded cluster nên có **bốn lớp**, không chỉ một con số “Balancer: ON”.

### 15.1. Lớp A — Tổng quan cluster

| Metric | Phạm vi | Câu hỏi |
|---|---|---|
| shardCount | Cluster | Có đủ shards không? |
| routerCount/health | Cluster | Mongos còn hoạt động và phục vụ request? |
| CSRS health | Config replica set | Metadata/coordination có ổn định? |
| balancerEnabled | Cluster | Balancing được phép chạy? |
| inBalancerRound | Cluster | Balancer có đang xử lý vòng không? |
| recentMigrationSuccess/Failure | Cluster/namespace | Migration có tiến triển? |
| global p95 latency | Application/cluster | Người dùng có bị ảnh hưởng? |

### 15.2. Lớp B — Theo collection và shard

| Metric | Nhãn tối thiểu | Đơn vị |
|---|---|---|
| ownedDataBytes | namespace, shard | Bytes |
| chunkCount / rangeCount | namespace, shard | Ranges |
| ownedDocumentCount (nếu có) | namespace, shard | Documents/ước lượng |
| maxToAverageOwnedBytes | namespace | Ratio |
| zonePlacementViolations (nếu có) | namespace, zone | Count |
| jumbo/oversizedRangeCandidates | namespace, shard | Ranges |

**Owned bytes** khác **storageStats.storageSize**, vì latter có thể tính compression/index/orphan/snapshot aspects tùy metric.

### 15.3. Lớp C — Shard/node performance

| Metric | Nhãn | Đơn vị |
|---|---|---|
| read/write QPS | shard, member role | Operations/giây |
| CPU | shard, member | % |
| diskUsed/diskFree | shard, member/volume | Bytes hoặc % |
| network RX/TX | shard, member | Bytes/giây |
| disk latency | shard, volume | Mili giây |
| cache eviction pressure | shard, member | Rate/giá trị |
| replication lag | shard, member | Giây |
| client error/timeout rate | app, endpoint, namespace nếu có | Requests/giây |

### 15.4. Lớp D — Migration/placement diagnostics

| Metric | Ý nghĩa |
|---|---|
| Balancer rounds started/completed | Có cơ chế đánh giá placement? |
| Migration started/committed/failed | Hoạt động di chuyển thành công không? |
| Migration duration | Copy/commit có chậm không? |
| Bytes moved per time unit | Tiến độ rebalancing. |
| Orphan cleanup backlog | Disk có thể chưa thu hồi dù ownership đã đổi. |
| Zone compliance | Ranges có nằm đúng eligible shards? |
| Oversized/jumbo candidates | Có range khó/không thể di chuyển? |

Metric names ở bảng là **khái niệm dashboard**, không phải mọi tên field chính thức trong serverStatus. Lựa chọn exporter/Atlas API/server version sẽ quyết định series names.

### 15.5. Ví dụ layout dashboard

~~~text
+----------------------------------------------------+
| SHARDED CLUSTER OVERVIEW                           |
| Shards: 3 | Routers: 2 | Balancer: enabled         |
| CSRS: healthy | Migration failures: 0 (last 1h)  |
+----------------------------------------------------+
| OWNED DATA BY SHARD       | WRITE QPS BY SHARD    |
| shard01: 600 GiB          | shard01: 8,000 ops/s  |
| shard02: 300 GiB          | shard02: 1,000 ops/s  |
| shard03: 300 GiB          | shard03: 1,000 ops/s  |
+----------------------------------------------------+
| MIGRATION TREND           | APPLICATION LATENCY   |
| bytes moved / hour        | p50 / p95 / p99       |
| success / failure         | read / write          |
+----------------------------------------------------+
| DISK / CACHE / NETWORK    | ZONES & RANGES        |
| per primary + secondary   | collection selection  |
+----------------------------------------------------+
~~~

Điểm quan trọng là đặt **owned bytes**, **write QPS**, **migration throughput** và **latency** cạnh nhau, để phân biệt data skew với workload skew.

### 15.6. Tránh labels có cardinality quá cao

Trong Prometheus hoặc metrics backend:

~~~text
cluster
shard
replica_set
member_role
namespace
environment
zone
~~~

thường là nhóm labels có kiểm soát được.

Không tạo metrics label cho **mọi orderId/customerId** nếu có hàng triệu giá trị: cardinality quá cao làm hệ thống monitoring tốn chi phí và không ổn định.

Các hot keys cụ thể nên phân tích qua **sampling/analytics/logs đã làm sạch**, không phải gắn hàng triệu key values vào một time series metrics.

### 15.7. Sampling interval

Các tín hiệu có tốc độ khác nhau:

- CPU/QPS/latency: vài chục giây hoặc phù hợp SLO.
- Balancer rounds/migration logs: theo sự kiện hoặc scrape định kỳ.
- Owned data/skew/chunk counts: vài phút hoặc lâu hơn nếu query tốn tài nguyên.
- Zone metadata: theo thay đổi cấu hình và kiểm tra định kỳ.

Không query nặng toàn bộ config.chunks mỗi 1 giây chỉ để vẽ dashboard.

## 16. Cảnh báo có ngữ cảnh

### 16.1. Alert về owned-data skew

Rule minh họa:

~~~text
IF maxToAverageOwnedBytes > 1.5 for 60 minutes
AND collection is expected to balance across these shards
AND no known zone exception
THEN warn: investigate placement
~~~

**1.5 và 60 phút chỉ là ví dụ**, không phải ngưỡng MongoDB quy định. Cluster mới thêm shard cần thời gian di chuyển; collection nhỏ ít ranges có thể lệch tự nhiên; zone sharding có thể cố ý không đều.

### 16.2. Balancer chưa tiến triển

Không alert chỉ vì:

~~~text
Balancer enabled AND inBalancerRound=false
~~~

Trạng thái này có thể bình thường.

Thay bằng điều kiện kết hợp:

~~~text
Sustained placement violation
AND balancer allowed to run now
AND repeated rounds show no progress
AND a migration/placement blocker is observed
~~~

Kèm namespace, zone, donor/recipient, lỗi và link runbook. Không coi một round thiếu migration là sự cố.

### 16.3. Disk free space

Theo dõi cả **% used**, **absolute free bytes**, days-to-capacity và incoming migration volume. Một volume 10 TiB còn 8% free khác volume 100 GiB còn 8% free; phải căn cứ workload, growth và dự trữ để migration.

### 16.4. Migration failures

~~~text
IF migration errors repeat within 15 minutes
AND matching placement violation persists
THEN alert with namespace, range, donor, recipient and reason
~~~

Một transient failure đã retry thành công có severity khác lỗi lặp đi lặp lại vì oversized range hoặc không có eligible recipient.

### 16.5. Workload hot spot

Kết hợp:

~~~text
max(writeQPS per primary) / avg(writeQPS per primary)
max(CPU per primary)
application p95 latency
~~~

Nếu owned bytes đều nhưng writeQPS ratio cao và latency tăng, nghi vấn shard key/workload. Không tự move chunks dựa trên CPU mà chưa xem hot key.

### 16.6. Replication và zone health

Alert replication lag, primary election và CSRS health theo SLO. Với zone, alert khi **placement violation hoặc thiếu eligible shard**, không phải khi APAC bytes nhiều hơn EU một cách hợp lệ.

### 16.7. Gắn sự kiện thay đổi lên dashboard

Khi add shard, resharding, đổi zones hoặc có maintenance, gắn change annotations vào charts. Không tắt mọi alert; giữ các tín hiệu nghiêm trọng như disk/availability/security hoạt động và chỉ suppress những cảnh báo dự kiến trong khoảng kiểm soát.

### 16.8. Bảng alert gợi ý

| Tín hiệu | Severity minh họa | Việc kiểm tra đầu |
|---|---|---|
| Không thấy shard vừa add | High | listShards, router, metadata. |
| Placement skew kéo dài | Warning | balancerStatus, compliance, zones. |
| Migration failures liên tục | High | logs, recipient health, jumbo ranges. |
| Disk free dưới headroom tối thiểu | Critical | growth, migration volume, capacity. |
| Primary election liên tục | Critical | replica set/network/disk. |
| CPU một shard cao nhưng bytes đều | Warning/High | hot queries, shard key, explain. |
| CSRS không available | Critical | CSRS health, cluster impact. |
| Range nằm sai zone bắt buộc | High | residency/placement diagnosis. |

Ngưỡng và severity phải do SLO/data residency/business requirements của tổ chức quy định.

## 17. Runbook chẩn đoán từ triệu chứng đến nguyên nhân

### 17.1. Case A — Một shard có 80% disk

~~~text
shard01 disk used: 80%
shard02 disk used: 35%
shard03 disk used: 32%
~~~

1. So disk capacity và free bytes của cùng loại member/volume.
2. Xem owned bytes của **từng sharded collection**.
3. So data/index/oplog/storage, orphan cleanup và fragmentation.
4. Xem unsharded collections hoặc workload cục bộ trên shard01.
5. Kiểm tra zones/compliance và migration history.
6. Nếu owned bytes đều nhưng physical disk lệch, đừng gọi đó là balancer failure.

### 17.2. Case B — Balancer enabled, data không đổi

~~~text
Balancer enabled: yes
Owned bytes:
  shard01 700 GiB
  shard02 200 GiB
  shard03 100 GiB
No movement for hours
~~~

1. Balancer mode, rounds và balancing window.
2. Collection-level compliance: có thực sự cần chuyển data?
3. Eligible recipients trong zones.
4. Free disk space của recipients.
5. Oversized/jumbo candidates.
6. Logs migration attempts/errors.
7. CSRS, shard replication, concurrent resharding/maintenance.

Nếu không có recipient eligible do zone, restart balancer không giải quyết.

### 17.3. Case C — Shard vừa thêm không có data

~~~text
shard03 added
shard03 owned bytes = 0 after hours
~~~

Kiểm tra shard có trong listShards, collection thật sự sharded, balancer đang được phép chạy, zones có cho shard03, có đủ ranges để move và có migration errors hay không. Collection nhỏ ít ranges có thể chưa cần di chuyển lớn theo threshold hiện tại.

### 17.4. Case D — Bytes đều nhưng CPU shard01 95%

~~~text
Owned bytes: 400 / 410 / 390 GiB
CPU:         95% / 35% / 34%
~~~

1. So write/read QPS và latency ở primaries.
2. Phân tích top queries, targeted vs scatter-gather.
3. Kiểm tra hot tenants/values theo shard key (bảo vệ PII).
4. Xem range chứa timestamp mới hoặc single-key hotspot.
5. Xem indexes, slow query sampling, cache và migration traffic.
6. Mới cân nhắc shard key redesign hoặc resharding.

Balancer có thể đã cân bằng bytes đúng; vấn đề là **phân bố thao tác**.

### 17.5. Case E — Balancing làm latency tăng

~~~text
Balancer starts migrations
Network and disk I/O increase
Application p95 latency doubles
~~~

Xác định migrations donor/recipient; so network, IOPS, cache và replication lag trước/sau; đối chiếu SLO và maintenance window. Chỉ can thiệp theo incident/change process có phê duyệt, không auto tắt balancer khi thấy CPU tăng.

### 17.6. Case F — Donor disk không giảm sau migration

~~~text
Committed migrations: yes
Owned data on donor: down
Physical disk usage: unchanged
~~~

Có thể do orphan cleanup, storage engine không trả physical blocks ngay, fragmentation, oplog/indexes hoặc writes mới. Kiểm tra metadata ownership và storage metrics trước khi thực hiện defragment/compact đắt đỏ.

### 17.7. Case G — Jumbo range / hot single-key value

~~~text
Migration fails for same range
Many documents share one shard key value
~~~

Xác định bounds, error, version, distinct key values và zone constraints. Đánh giá khả năng split/move được hỗ trợ; cân nhắc resharding/compound key nếu shard-key entropy là nguyên nhân. Không force migrate tùy tiện trong production.

### 17.8. Case H — Zone APAC bị dồn một shard

~~~text
APAC: only shard03 eligible
APAC data: 900 GiB
EU data: 600 GiB on shard01 and shard02
~~~

Xác nhận residency; dự báo capacity shard03; xem có thể mở rộng eligible shards ở APAC hay không. Không chuyển APAC data sang EU chỉ để làm chart cân bằng.

### 17.9. Case I — CSRS primary bất ổn

Kiểm tra CSRS replica set, network/disk/replication, metadata/balancer errors và mongos failures. Không tự chỉnh config database; dùng incident response theo topology.

### 17.10. Thứ tự điều tra chuẩn

~~~text
1. Scope: cluster, namespace, version, time window
2. mongos / listShards / CSRS health
3. balancer mode, rounds, collection compliance
4. owned bytes / chunks / disk and trends
5. zones and oversized ranges
6. migration logs and donor/recipient health
7. QPS / CPU / cache / replication / latency
8. query targeting and shard key design
9. operational decision with approval
10. verify impact and document outcome
~~~

Đừng bỏ qua bước xác định **scope**: một con số 70% có thể chỉ disk toàn node, owned bytes của collection, chunk count hoặc write QPS.

## 18. Theo dõi khi thêm shard hoặc thay shard key

### 18.1. Thêm shard là một thay đổi capacity, không tự động cân bằng ngay

Khi scale-out:

~~~text
Before:
  shard01: 500 GiB
  shard02: 500 GiB

After adding shard03:
  shard01: 500 GiB
  shard02: 500 GiB
  shard03:   0 GiB

After successful eligible migrations:
  shard01: approximately 330 GiB
  shard02: approximately 340 GiB
  shard03: approximately 330 GiB
~~~

Các số **chỉ là ví dụ mong muốn**, không phải SLA hoặc bảo đảm tốc độ balancing. Zones, range size, version, resource limits và workload có thể khiến phân bố khác.

### 18.2. Baseline trước thay đổi

Ghi nhận:

1. Shards, mongos và CSRS members hiện tại.
2. Balancer status và configuration.
3. Owned bytes/chunks theo collection và shard.
4. Disk free/capacity và peak IOPS/network.
5. Read/write QPS, application p50/p95/p99, errors.
6. Replica set health/replication lag.
7. Zone constraints và shard-key design.
8. SLO, RPO/RTO và maintenance/change window.

Không thể chứng minh scale-out cải thiện latency nếu không có baseline so sánh.

### 18.3. Trong khi rebalance

Theo dõi theo time window:

~~~text
timestamp
rangeCount and ownedBytes by shard
migrations attempted/committed/failed
balancer enabled and round status
diskFreeBytes by member
network throughput and disk IOPS
replication lag
application p95 latency / error rate
~~~

Một migration thành công chưa đủ; cần xem dữ liệu chuyển **đúng collection/zone** và có tác động mong muốn.

### 18.4. Sau khi rebalance

Đánh giá:

- Owned bytes có đến gần expected placement?
- Các shards có còn đủ disk headroom cho growth?
- App latency và throughput có cải thiện?
- Query targeting đã tốt hơn, hay vẫn scatter-gather?
- Workload có chuyển từ hot shard01 sang một hot shard khác?
- Orphan cleanup đã ổn định chưa?
- Có jumbo/oversized ranges không được xử lý?

Nếu bytes đều nhưng QPS vẫn lệch, có thể cần tối ưu shard key/query hơn nữa.

### 18.5. Resharding và quan sát

Resharding thay **shard key của collection** bằng cơ chế được MongoDB version hỗ trợ. Vì tác vụ có thể copy/reorganize lượng dữ liệu lớn, cần quan sát:

- Tiến độ/phase của resharding operation theo công cụ chính thức.
- Storage/capacity overhead trên participating shards.
- Write throughput, replication, disk/network.
- User-facing latency và errors.
- Placement compliance sau cutover.
- Bản chất query targeting với key mới.

**Resharding không nên được kích hoạt chỉ vì một alert disk skew**. Cần phân tích điều kiện shard key mới, truy vấn ứng dụng, downtime/online behavior và rollback strategy.

### 18.6. Cân bằng theo capacity khác nhau

Ví dụ:

~~~text
shard01 capacity 4 TiB
shard02 capacity 1 TiB
shard03 capacity 1 TiB
~~~

Nếu workload/capacity rất khác nhau, cần quy hoạch placement cụ thể và quan sát ratio theo free space thay vì kỳ vọng MongoDB tự động tối ưu mọi tỷ lệ theo dung lượng khác biệt.

### 18.7. Shard removal/draining

Khi remove shard theo quy trình được hỗ trợ, hệ thống cần di chuyển dữ liệu khỏi shard đang drain. Theo dõi:

- Trạng thái draining theo lệnh quản trị.
- Số ranges/bytes còn lại trên shard.
- Các unsharded collection hoặc unsplittable placement blockers.
- Zone constraints và eligible destinations.
- Network/disk/latency trong migration.

Không coi shard “không còn phục vụ writes” là đủ điều kiện xóa node vật lý; phải đợi quy trình removal hoàn thành và xác minh.

## 19. Java Sync Driver: thu thập thông tin cluster

Trong Java, **sh.status() là một mongosh helper**, không phải method của MongoCollection. Driver có thể chạy các admin commands được server hỗ trợ.

### 19.1. Mẫu Java đọc listShards và balancerStatus

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class ShardingObserver {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI is required"
            );
        }

        // URI phải kết nối mongos/router của sharded cluster.
        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase admin = client.getDatabase("admin");

            Document shards = admin.runCommand(
                    new Document("listShards", 1)
            );
            System.out.println("Shards:");
            System.out.println(shards.toJson());

            Document balancer = admin.runCommand(
                    new Document("balancerStatus", 1)
            );
            System.out.println("Balancer:");
            System.out.println(balancer.toJson());
        }
    }
}
~~~

Lưu ý:

- Dùng **MongoClient** tái sử dụng lâu dài ở service thật.
- URI/credentials thuộc secrets được bảo vệ, không hardcode password.
- Tài khoản monitoring chỉ cần quyền đọc thông tin cluster tương ứng.
- Balancer/status fields không bất biến giữa MongoDB versions.
- Có thể log summaries được chọn thay vì in raw shard hostnames/metadata.

### 19.2. Thu thập collection-level storage statistics

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;

public final class CollectionStorageObserver {

    private final MongoClient client;

    public CollectionStorageObserver(MongoClient client) {
        this.client = client;
    }

    public void inspectOrders() {
        MongoCollection<Document> orders =
                client.getDatabase("commerce")
                        .getCollection("orders");

        Bson collStats = new Document(
                "$collStats",
                new Document(
                        "storageStats",
                        new Document("scale", 1048576)
                ).append(
                        "count",
                        new Document()
                )
        );

        orders.aggregate(List.of(collStats))
                .forEach(document -> {
                    // Trong production cần parse schema theo version.
                    // Không gửi toàn bộ document nhạy cảm vào logs.
                    System.out.println(document.toJson());
                });
    }
}
~~~

Code minh họa truy vấn **$collStats**. Các fields và per-shard semantics phải kiểm tra trên server/driver đang dùng. Không lấy một field bytes tùy ý rồi đổi tên thành “ownedBytes” nếu metric thực chất là storage size hoặc compressed size.

### 19.3. Java đo skew từ các samples đã xác thực

Nếu đã lấy được một map **ownedBytes theo shard** từ nguồn thống kê đáng tin và nhất quán:

~~~java
import java.util.Map;

public final class SkewCalculator {

    public static double maxToAverage(
            Map<String, Long> ownedBytesByShard) {

        if (ownedBytesByShard.isEmpty()) {
            throw new IllegalArgumentException(
                    "No shard samples"
            );
        }

        double total = 0.0;
        double max = 0.0;

        for (long bytes : ownedBytesByShard.values()) {
            if (bytes < 0) {
                throw new IllegalArgumentException(
                        "Negative bytes"
                );
            }

            total += bytes;
            max = Math.max(max, bytes);
        }

        double mean = total / ownedBytesByShard.size();
        return mean == 0.0 ? 0.0 : max / mean;
    }
}
~~~

Ví dụ:

~~~java
double skew = SkewCalculator.maxToAverage(
        Map.of(
                "shard01", 600L,
                "shard02", 300L,
                "shard03", 300L
        )
);

// skew = 1.5
~~~

Đây chỉ là phần **tính toán từ input metrics đã được chuẩn hóa**, không phải Java tự đọc chính xác ownedBytes của mọi version MongoDB.

### 19.4. Không biến monitoring collector thành một tiến trình nặng

Nếu collector chạy trên 100 mongos instances:

~~~text
100 collectors
    x 1 aggregate over all config.chunks each second
    = 100 expensive metadata queries/sec
~~~

Nên:

- Chỉ định một collector/leader cho các cluster-wide metadata queries.
- Cache/scrape kết quả ở tần suất thích hợp.
- Không ghi config database hoặc kích hoạt migration.
- Bảo vệ timeouts, backoff và rate limiting.
- Áp metrics labels có cardinality thấp.
- Dùng chính Atlas/Ops Manager/exporter metrics khi đủ khả năng.

### 19.5. Không dùng Java application request path để làm cluster admin monitoring

Một API HTTP:

~~~text
GET /orders
  -> listShards
  -> balancerStatus
  -> $collStats
  -> find orders
~~~

không phải thiết kế tốt. Các lệnh điều tra nên chạy **bất đồng bộ trong monitoring/ops service** với quyền và tần suất riêng; API nghiệp vụ chỉ truy vấn dữ liệu theo shard key phù hợp.

## 20. Spring Data MongoDB và quan sát hạ tầng

### 20.1. MongoTemplate.executeCommand

Trong Spring Data MongoDB có thể chạy admin commands qua **MongoTemplate** khi được cấu hình đúng database/connection và có quyền:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class ShardingStatusService {

    private final MongoTemplate mongoTemplate;

    public ShardingStatusService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Document balancerStatus() {
        return mongoTemplate.executeCommand(
                new Document("balancerStatus", 1)
        );
    }
}
~~~

**Cần đảm bảo MongoTemplate đang kết nối qua mongos và tài khoản có quyền**, và kiểm tra command chạy trên database mong muốn. Trong production, nên dùng dedicated monitoring client nếu runtime user không có đặc quyền clusterMonitor.

### 20.2. Điều cần tách trong Spring Boot

~~~text
Business request path:
  repository -> MongoDB through mongos

Monitoring path:
  scheduled collector -> supported read-only stats
                     -> Micrometer/metrics backend
~~~

Không để mỗi request API gọi balancerStatus hoặc config metadata.

### 20.3. Micrometer-style metrics

Nếu có ứng dụng thu được dữ liệu chuẩn hóa, có thể xuất:

~~~text
mongo_shard_owned_bytes{cluster="prod",namespace="commerce.orders",shard="shard01"} 644245094400
mongo_shard_owned_bytes{cluster="prod",namespace="commerce.orders",shard="shard02"} 322122547200
mongo_shard_owned_bytes{cluster="prod",namespace="commerce.orders",shard="shard03"} 322122547200

mongo_shard_data_skew_max_mean{cluster="prod",namespace="commerce.orders"} 1.5
~~~

Tên metrics ở đây **do người thiết kế collector đặt**, không phải mặc định MongoDB/Spring Boot cung cấp. Values minh họa chuyển từ 600/300/300 GiB sang bytes theo hệ nhị phân.

### 20.4. Quy tắc production cho exporter

1. Mô tả **metric semantics** và đơn vị bytes/GiB rõ.
2. Ghi timestamp của observations.
3. Đánh dấu measurement failed/missing thay vì giữ stale value vĩnh viễn.
4. Không cộng các shard samples lấy từ epochs cách nhau quá xa.
5. Không xuất tenantId/orderId của hàng triệu entities thành Prometheus labels.
6. Tránh dump raw config metadata với hostnames/keys vào public endpoint.
7. Bảo vệ metrics endpoint bằng network policy/auth.
8. Tách cluster-wide scrape frequency với node CPU sampling.

## 21. Các yếu tố khiến biểu đồ phân bố “khó hiểu”

### 21.1. Unsharded collection nằm trên primary shard của database

Trong sharded cluster, một database có **primary shard** cho những collections chưa được sharded và các thành phần dữ liệu liên quan theo MongoDB version. Nếu một unsharded collection rất lớn nằm trên shard01:

~~~text
commerce.orders (sharded):
  shard01: 300 GiB
  shard02: 300 GiB
  shard03: 300 GiB

commerce.audit_archive (unsharded):
  shard01: 800 GiB
  shard02:   0 GiB
  shard03:   0 GiB
~~~

Physical disk shard01 có thể lớn hơn rất nhiều dù **orders** được cân bằng.

Balancer của sharded ranges không tự chia một unsharded collection thành nhiều ranges chỉ vì cluster có nhiều shards. Các cơ chế di chuyển unsharded collection hoặc sharding collection khác nhau theo MongoDB version; cần xem hướng dẫn chính thức trước khi vận hành.

### 21.2. Replica set member vs logical shard size

Nếu shard01 có ba replica set members và mỗi member lưu 300 GiB:

~~~text
Logical shard01 data: ~300 GiB
Physical copies across three members: ~900 GiB
~~~

Không cộng dung lượng ba replica members rồi gán **900 GiB owned data trên shard01** khi so với một shard khác chỉ đếm một primary.

Hãy xác định dashboard đang tính:

- Logical owned data.
- Physical bytes trên một member.
- Tổng physical bytes của mọi replicas.

Ba loại metric có mục đích khác nhau.

### 21.3. Compression khác nhau

Hai shards có cùng logical document bytes nhưng compress khác nhau vì dữ liệu khác nhau:

~~~text
shard01 contains highly repetitive documents
shard02 contains random or already-compressed blobs
~~~

Physical storageSize có thể khác dù logical data size tương tự. Index cardinality và key patterns cũng làm index bytes khác.

### 21.4. Một shard có nhiều secondary reads

Nếu ứng dụng dùng read preference tới secondaries, một shard có thể có CPU cao trên secondary dù primary writes tương đối đều. Theo dõi **read distribution theo member role** và query targeting, không chỉ primary write rate.

### 21.5. MongoDB đã cân bằng bytes nhưng một node IOPS kém

Hai shards có 500 GiB mỗi bên, nhưng một bên dùng ổ đĩa chậm hơn hoặc có noisy neighbors. Latency khác nhau không đồng nghĩa placement lệch.

Kiểm tra disk latency, throttling, CPU steal và network, bên cạnh sharding metrics.

### 21.6. Một shard giữ quá nhiều indexes

Thông thường indexes của một sharded collection được xây dựng đồng nhất theo schema/management, nhưng sau thao tác thủ công, sự cố migration hoặc các collection khác nhau, index/storage overhead giữa các shards vẫn có thể khác.

Không chỉ đo dữ liệu documents, hãy so index sizes và query plan. Không tự xóa indexes trên một shard riêng lẻ mà không tuân thủ quy trình quản lý sharded collection.

### 21.7. Orphan cleanup và fragmentation

Sau range migration:

~~~text
ownedDataBytes(shard01) decreases
storageSize(shard01) might not fall immediately
diskAllocatedBytes might remain high
~~~

Điều này không chứng minh migration thất bại. Theo dõi cleanup và storage-engine behavior; đừng dùng diskUsed làm proxy duy nhất cho logical ownership.

### 21.8. Balancer đang hoạt động nhưng placement đúng zone không đều toàn cục

Một số shards không eligible cho dữ liệu trong zone. Khi tính mức lệch, chia theo **eligible shard set** hoặc ghi zone constraints rõ ràng. Tránh đưa một zone-single-shard vào phép tính “mọi shard phải bằng nhau” mà không giải thích.

### 21.9. Collection nhỏ hoặc sparse data

Một collection chỉ có vài ranges hoặc vài MiB data có thể phân bố không đều về số ranges/bytes mà không ảnh hưởng SLO. Một alert max/min cao trên dataset quá nhỏ có thể nhiễu.

Nên đặt thêm **minimum data size/traffic requirement** trước khi đánh giá skew là vấn đề.

### 21.10. Measurements lấy từ những thời điểm khác nhau

Nếu shard01 vừa nhận migration và shard02 vừa dọn orphan, hai counters ở hai thời điểm khác nhau có thể gây ảo giác data đã tạo thêm hoặc mất đi. Cần đồng bộ timestamps/measurement windows và ghi tình trạng migrations.

### 21.11. Một node restart làm rate counters reset

Nếu serverStatus counter reset:

~~~text
ops counter at t0: 9,000,000
node restarts
ops counter at t1: 10,000
~~~

Phép trừ trực tiếp tạo rate âm không có ý nghĩa. Monitoring backend cần nhận diện reset/restart, tính rate bằng phương pháp phù hợp và thể hiện missing sample.

### 21.12. Query workload thay đổi theo thời gian

Một ứng dụng batch import lúc 01:00 có thể khiến shard01 hot vài giờ, nhưng sau đó workload cân bằng. Cần so biểu đồ **cùng giờ/ngày** và business events trước khi chọn reshard.

## 22. Checklist vận hành theo từng ngày và trước thay đổi

### 22.1. Kiểm tra định kỳ

- [ ] mongos routers reachable; app error rate trong SLO.
- [ ] listShards trả đúng inventory.
- [ ] Config server replica set khỏe.
- [ ] Shard replica set primaries/secondaries khỏe, replication lag chấp nhận được.
- [ ] balancerStatus phản ánh chế độ expected.
- [ ] Collection placement/skew nằm trong ngưỡng theo zone/policy.
- [ ] Migration error trends được kiểm tra.
- [ ] Owned bytes và physical disk được đo riêng.
- [ ] Disk headroom đủ cho growth và migrations.
- [ ] p95/p99 application latency không tăng bất thường.
- [ ] Các queries trọng yếu được targeted tốt theo shard key.
- [ ] Monitoring alerts không chứa credentials, PII hoặc raw config secrets.

### 22.2. Trước khi thêm một shard

- [ ] Chứng minh bottleneck là capacity/placement hay workload.
- [ ] Chọn cấu hình replica set, network và storage capacity phù hợp.
- [ ] Xác định zones và shard eligibility.
- [ ] Đặt baseline owned bytes/QPS/latency/replication.
- [ ] Xác định balancing window/change approval.
- [ ] Ước lượng dữ liệu cần migrate và capacity headroom.
- [ ] Đảm bảo backup/DR và monitoring hiện hành hoạt động.
- [ ] Có tiêu chí thành công và phương án sự cố.

### 22.3. Khi balancer không tiến triển

- [ ] Kiểm tra enabled vs currently running.
- [ ] Kiểm tra collection-level compliance.
- [ ] Xác nhận không ngoài balancing window.
- [ ] Kiểm tra zones/recipient eligibility.
- [ ] Kiểm tra disk free, network, primary elections.
- [ ] Kiểm tra jumbo/oversized ranges.
- [ ] Đọc migration logs cùng mốc thời gian.
- [ ] Không chỉnh config database trực tiếp.
- [ ] Không force migration khi chưa có approval.

### 22.4. Khi CPU/QPS lệch

- [ ] Đo per-shard write QPS và per-member read QPS.
- [ ] Kiểm tra hot shard-key values bằng nguồn dữ liệu được kiểm soát.
- [ ] Kiểm tra shard key cardinality/monotonicity.
- [ ] Kiểm tra targeted/scatter-gather query distribution.
- [ ] Kiểm tra indexes và latency/slow query patterns.
- [ ] Xác nhận không phải migration/backup traffic.
- [ ] Đánh giá resharding chỉ sau khi có evidence.

### 22.5. Sau khi mở rộng/reshard

- [ ] Owned bytes/ranges có thay đổi theo đúng namespace?
- [ ] Zone compliance còn đúng?
- [ ] Migrations hoàn tất hoặc có nguyên nhân rõ?
- [ ] Không có hot shard mới?
- [ ] Application p95/p99 và errors chấp nhận được?
- [ ] Disk free space còn đủ?
- [ ] Orphan cleanup không gây rủi ro capacity?
- [ ] Monitoring baselines/thresholds được cập nhật theo topology mới?
- [ ] Postmortem/change record được lưu khi cần?

## 23. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng sửa |
|---|---|---|
| Balancer enabled được coi là đang migration | Báo cáo sai trạng thái. | Phân biệt enable/mode/round/migration outcome. |
| Số chunks đều nên cho rằng data đều | Che khuất ranges có kích thước khác nhau. | Đo owned bytes theo collection. |
| Disk đều nên cho rằng CPU sẽ đều | Không thấy hot key/query patterns. | Đo QPS/CPU/latency. |
| Disk lệch nên kết luận balancer hỏng | Nhầm indexes/oplog/orphans/unsharded data. | Tách logical và physical metrics. |
| Không có migration thì tự động restart balancer | Có thể gây thay đổi không cần thiết. | Kiểm tra compliance/window/zones trước. |
| Tạo thêm shard sẽ chia được single hot key | Bottleneck vẫn còn. | Xem shard key entropy và resharding. |
| So bytes của shards không cùng zone | Báo động sai ở cluster có residency constraints. | So eligible shards theo zone. |
| Bỏ qua disk free trên recipient | Migration có thể fail/khó chạy. | Capacity planning và headroom. |
| Đọc config.chunks rồi sửa trực tiếp | Nguy cơ hỏng routing metadata. | Chỉ đọc; thao tác qua lệnh hỗ trợ. |
| Dùng parser cố định cho config.chunks | Vỡ khi version đổi schema uuid/ns. | Version-aware, ưu tiên helper chính thức. |
| Dùng numBalancerRounds như số chunks đã move | Sai định nghĩa. | Theo dõi migration commit và owned-byte delta. |
| Xem orphan copies là logical data mới | Sai số lượng bytes sở hữu. | Theo dõi owned vs physical. |
| Query thiếu shard key mà mong balancer cứu latency | Scatter-gather vẫn tồn tại. | Thiết kế query targeting. |
| Query mongos qua shard primary trực tiếp | Có thể chỉ đọc một phần dữ liệu. | Routing qua mongos cho sharded collection. |
| Đếm ba replica members thành ba shards | Phóng đại số shard logic. | Phân biệt RS member vs shard ID. |
| Gọi monitoring commands mỗi request API | Tăng tải không cần thiết. | Dedicated scheduled collector. |
| Gắn tenantId triệu giá trị vào metrics labels | Explode time series cardinality. | Labels có kiểm soát, hot-key analytics riêng. |
| Alert ratio cao trên dataset nhỏ | Báo động giả. | Minimum bytes/QPS/time window. |
| Dùng CPU 95% mà không phân tích I/O và migration | Chẩn đoán sai root cause. | Correlate latency/IO/cache/QPS. |
| Resharding ngay khi thấy skew | Rủi ro lớn, chưa chắc giải quyết. | Baseline, explain, design review và canary plan. |
| Coi config.changelog là audit đầy đủ mãi mãi | Bỏ sót history do retention/version. | Có log pipeline/metrics phù hợp. |
| Không ghi thời điểm metrics | So dữ liệu các epochs khác nhau. | Timestamp và consistency window. |
| Lấy counter chia ngay cho 60 mà không tính delta | Rate sai. | Dùng rate tính trên hai samples và xử lý reset. |

## 24. Bài thực hành

### Bài 1 — Vẽ sơ đồ sharded cluster

Vẽ sơ đồ có **hai mongos routers, một config server replica set và ba shard replica sets**. Ghi rõ thành phần nào nhận query, thành phần nào chứa routing metadata và thành phần nào lưu documents.

### Bài 2 — Đếm shards đúng

Cluster có ba shards, mỗi shard là replica set ba members, config server replica set cũng ba members. Có bao nhiêu **logical shards**? Vì sao số replica members không phải số shards?

### Bài 3 — listShards

Kết nối mongos và chạy:

~~~javascript
db.adminCommand({ listShards: 1 });
~~~

Liệt kê các fields bạn cần để đối chiếu shard inventory và host mappings. Giải thích vì sao command thành công không tự chứng minh mỗi replica set member đều khỏe.

### Bài 4 — sh.status

Chạy sh.status() trên mongosh và xác định:

1. Sharded collections.
2. Shard key mỗi collection.
3. Distribution/placement information có trong output version đó.
4. Có zone constraints không?

Không cần ghi đè hoặc chỉnh sửa config metadata.

### Bài 5 — Bốn loại skew

Một cluster có:

~~~text
Chunks:       100 / 100 / 100
Owned bytes:  900 / 100 / 100 GiB
CPU:          90 / 30 / 25 %
Disk used:    75 / 35 / 34 %
~~~

Phân loại chunk-count, owned-byte, workload và physical-storage skew. Vì sao không được kết luận tất cả metrics đều phản ánh một nguyên nhân?

### Bài 6 — Data share

Với 600/300/300 GiB owned bytes, tính tỷ lệ dữ liệu của mỗi shard trên tổng. Shard lớn nhất chiếm bao nhiêu phần trăm?

### Bài 7 — Max-to-average skew

Với cùng bộ số 600/300/300 GiB, tính averageOwnedBytes và maxToAverageSkew.

### Bài 8 — Shard mới chưa có dữ liệu

Cluster có owned bytes 500/500/0 GiB. Vì sao max-to-min ratio không hữu ích? Hãy tính max-to-average ratio và đề xuất chỉ số bổ sung trong thời gian rebalance.

### Bài 9 — Biểu đồ có zone

Shards 1–2 thuộc zone EU, shard 3 thuộc zone APAC. APAC chiếm 70% dữ liệu. Đề xuất cách đánh giá placement compliance mà không ép 3 shards có owned bytes bằng nhau.

### Bài 10 — Balancer enabled vs running

Giả sử:

~~~javascript
{
  mode: "full",
  inBalancerRound: false,
  ok: 1
}
~~~

Bạn có thể kết luận balancer đang bị lỗi không? Cần kiểm tra điều kiện nào trước?

### Bài 11 — BalancerCollectionStatus

Chạy command nếu server version hỗ trợ:

~~~javascript
db.adminCommand({
  balancerCollectionStatus: "commerce.orders"
});
~~~

Giải thích vì sao một collection-level compliance signal có ích hơn chỉ nhìn toàn cluster.

### Bài 12 — Migration donor và recipient

Vẽ đường đi của một range từ shard01 sang shard02 gồm clone data, catch up, commit ownership và orphan cleanup. Vì sao recipient có bytes trước khi metadata commit mà chưa thể coi là owner?

### Bài 13 — Donor disk không giảm

Sau 30 migrations thành công, owned bytes trên shard01 giảm 100 GiB nhưng physical disk gần như không giảm. Liệt kê bốn giả thuyết cần kiểm tra.

### Bài 14 — Migration quá chậm

Một migration diễn ra trong nhiều giờ. Disk IOPS donor gần bão hòa, replication lag trên recipient tăng, application p95 latency tăng. Hãy đề xuất các bước thu thập bằng chứng và một quyết định theo change/SLO process.

### Bài 15 — Cảnh báo sai

Alert hiện tại:

~~~text
If balancerEnabled=true and inBalancerRound=false
then Critical
~~~

Vì sao alert này sai? Hãy viết lại thành điều kiện có collection compliance và progress/failure signal.

### Bài 16 — Hashed vs ranged shard key

So sánh:

~~~javascript
{ createdAt: 1 }
~~~

với:

~~~javascript
{ customerId: "hashed" }
~~~

Trường hợp nào dễ dồn inserts theo timestamp vào range ở rìa keyspace? Khi nào hashed key làm query range theo customerId kém tự nhiên?

### Bài 17 — Hot tenant

Một tenant chiếm 60% write QPS nhưng collection đã cân bằng owned bytes. Bạn sẽ phân tích cardinality, top shard-key values, primary CPU và query patterns thế nào?

### Bài 18 — Query targeting

Với collection shard theo customerId, so:

~~~javascript
db.orders.find({ status: "PENDING" });

db.orders.find({
  customerId: "C-100",
  status: "PENDING"
});
~~~

Query nào có cơ hội targeted tốt hơn? Kiểm tra bằng explain ra sao?

### Bài 19 — Metadata query đọc chunks

Viết một query read-only trên config.chunks để group rangeCount theo shard cho một collection, lưu ý chọn bằng uuid/ns theo schema version. Vì sao không nên update config.chunks trực tiếp?

### Bài 20 — Unsharded collection làm disk lệch

Collection orders được sharded đều 300 GiB mỗi shard. Collection audit_archive chưa sharded có 800 GiB trên database primary shard. Dashboard tổng disk có thể cho hình dạng gì? Vì sao balancer ranges của orders không tự giải quyết?

### Bài 21 — Counters sang QPS

Counter từ 1.000.000 lên 1.060.000 trong 60 giây. Tính ops/sec. Nếu node restart giữa hai mẫu, collector cần làm gì?

### Bài 22 — Replication lag

Một shard có 2 secondaries, một secondary lag 120 giây. Bạn cần theo dõi thêm những dữ liệu nào: oplog window, disk throughput, network, read preference và migration effects?

### Bài 23 — Jumbo range

Một range lớn có hàng triệu documents cùng customerId. Giải thích vì sao có thể thiếu split point. Đề xuất hai giải pháp kiến trúc và một nguyên tắc an toàn trước khi force migration.

### Bài 24 — Scale-out

Một cluster thêm shard03. Hãy thiết kế dashboard trước/trong/sau migration gồm owned bytes, migrations attempted/committed/failed, disk free, CPU, application p95.

### Bài 25 — Zone placement

EU zone có hai shards, APAC có một shard. Nếu dữ liệu APAC tăng nhanh, giải pháp mở rộng capacity nào không vi phạm residency policy?

### Bài 26 — Prometheus cardinality

Một exporter định xuất metric:

~~~text
mongo_hot_customer_qps{customerId="..."}
~~~

với mười triệu customerIds. Rủi ro là gì? Đề xuất một tập labels có cardinality thấp hơn.

### Bài 27 — $collStats

Viết pipeline sử dụng **$collStats** để lấy storageStats/count của orders. Giải thích vì sao output storage bytes không tự đồng nghĩa owned bytes của sharded collection.

### Bài 28 — Java Sync Driver

Viết một Java monitoring tool chạy:

~~~javascript
db.adminCommand({ listShards: 1 });
db.adminCommand({ balancerStatus: 1 });
~~~

bằng MongoDatabase.runCommand và Document. Giải thích yêu cầu URI qua mongos và account permissions.

### Bài 29 — Tính skew trong Java

Viết hàm nhận Map<String,Long> ownedBytesByShard, tính max/mean ratio. Xử lý empty map, negative values và trường hợp total bytes=0.

### Bài 30 — Spring Data MongoDB

Viết một scheduled collector sử dụng MongoTemplate hoặc một monitoring MongoClient riêng. Vì sao không nên chạy command balancerStatus trong mọi HTTP request?

### Bài 31 — Dự báo hết disk

Một shard còn 300 GiB free và đang tăng ròng 20 GiB/ngày. Tính số ngày runway sơ bộ. Nếu balancer sắp chuyển thêm 150 GiB vào shard, vì sao ước lượng ban đầu phải được cập nhật?

### Bài 32 — So sánh capacities

Shard01 có 600 GiB owned trên ổ 2 TiB; shard02 và shard03 mỗi shard 300 GiB owned trên ổ 500 GiB. Tính percent owned/capacity. Có nên ép owned bytes bằng nhau nếu điều đó làm hai shards nhỏ gần hết disk?

### Bài 33 — Config changelog

Truy vấn migration events read-only từ config.changelog nếu có. Khi không thấy kết quả, bạn có được kết luận cluster chưa từng migration không? Vì sao?

### Bài 34 — Migration success vs availability

Migrations có tốc độ 100 GiB/giờ nhưng p95 latency API tăng gấp đôi. Tính “thành công” theo các SLO nào, không chỉ bytes moved?

### Bài 35 — Viết runbook production

Một dashboard alert:

~~~text
Collection commerce.orders:
  max-to-average owned data skew = 1.8
  3 hours persistent
  balancer enabled
  50 migration errors in 1 hour
  shard03 disk free < 10 GiB
~~~

Đề xuất thứ tự điều tra, dữ liệu cần xem và các hành động **không nên** thực hiện khi chưa được duyệt.

## 25. Câu hỏi ôn tập

1. Mongos có vai trò gì trong sharded cluster?
2. CSRS lưu những metadata nào?
3. Vì sao mỗi shard replica set khác với một replica set member?
4. Balancer điều chỉnh loại tài nguyên nào?
5. Range/chunk là gì?
6. Một range migration khác split thế nào?
7. Vì sao split range không đồng nghĩa dữ liệu đã chuyển shard?
8. Vì sao chunk-count balance không bảo đảm owned bytes balance?
9. Vì sao owned bytes balance không bảo đảm disk balance?
10. Vì sao disk balance không bảo đảm workload balance?
11. Shard key tăng đơn điệu tạo hotspot bằng cơ chế nào?
12. Hashed shard key giải quyết điều gì và không giải quyết điều gì?
13. Cardinality cao có thể vẫn xuất hiện hot key không?
14. Query thiếu shard key có nguy cơ gì?
15. Có thể dùng explain để xác định targeted shards ra sao?
16. Zone sharding giới hạn balancing thế nào?
17. Khi một zone chỉ có một eligible shard, global skew có thể hợp lệ không?
18. Jumbo/oversized range có thể phát sinh vì nguyên nhân gì?
19. Vì sao không nên force migration một range rất lớn khi chưa điều tra?
20. Lệnh listShards trả dữ liệu gì?
21. sh.status có thể cho biết những thông tin nào?
22. balancerStatus có khác sh.getBalancerState không?
23. Vì sao inBalancerRound=false không chứng minh balancer hỏng?
24. Vì sao numBalancerRounds không phải số migrations thành công?
25. Làm sao phân biệt migration commit và orphan cleanup?
26. Data share, max-to-average skew và max-to-min skew khác nhau thế nào?
27. Vì sao max-to-min ratio khó dùng khi shard mới trống?
28. Có những nhóm metrics node-level nào cần xem khi migration chậm?
29. Tại sao cần tính rates từ cumulative counters?
30. Orphaned documents ảnh hưởng vật lý disk thế nào?
31. Unsharded collections làm skew dashboard tổng thể ra sao?
32. Vì sao CSRS health là thành phần observability quan trọng?
33. Vì sao không sửa trực tiếp config.chunks?
34. Config metadata schema có thể thay đổi theo server version như thế nào?
35. Vì sao phải lọc/ẩn hostnames và thông tin cluster trong monitoring logs?
36. Vì sao không đặt customerId có hàng triệu values thành metrics labels?
37. Những cảnh báo nào cần kết hợp zone compliance và balancer status?
38. Khi thêm shard, điều gì cần đo trước và sau?
39. Resharding có thể cần những nguồn tài nguyên phụ nào?
40. Vì sao một dashboard đủ tốt phải có cả application latency?

## 26. Tổng kết: nhìn phân bố dữ liệu cùng với sức khỏe và workload

MongoDB sharded cluster có nhiều thành phần, mỗi thành phần cung cấp một góc nhìn khác nhau về sức khỏe hệ thống:

~~~text
                    User-facing SLO
                  latency, errors, QPS
                          |
                          v
                    mongos routing
                targeted vs scatter-gather
                          |
                          v
              shard primaries/secondaries
           CPU, cache, disk, replication lag
                          |
                          v
             owned ranges/data per shard
              chunk count, bytes, zones
                          |
                          v
           balancer, migrations, CSRS state
              rounds, errors, compliance
~~~

### 26.1. Một quyết định nhanh bằng evidence

~~~text
Observed skew?
     |
     +-- Chunk counts unequal only
     |       |
     |       v
     |   Compare owned bytes and placement compliance.
     |
     +-- Owned bytes unequal
     |       |
     |       v
     |   Check zones, balancer, range sizes and migrations.
     |
     +-- Physical disk unequal
     |       |
     |       v
     |   Check indexes, oplog, orphan cleanup and unsharded data.
     |
     +-- CPU / QPS unequal
             |
             v
         Check hot key, shard key, query targeting,
         indexes, read preference and infrastructure.
~~~

Đừng chọn giải pháp trước khi biết mình đang nhìn loại skew nào.

### 26.2. Năm lệnh và nguồn điều tra quan trọng

| Công cụ | Điều trả lời |
|---|---|
| **sh.status()** | Cluster sharding overview, collections và placements tùy version. |
| **listShards** | Danh sách shards cấu hình trong cluster. |
| **balancerStatus** | Trạng thái hoạt động balancer ở cấp cluster. |
| **getShardDistribution()** | Distribution của một sharded collection theo helper/version. |
| **$collStats, serverStatus, rs.status và metrics dashboard** | Data/storage stats và sức khỏe từng node/replica set. |

Khi cần sâu hơn, tham khảo **balancerCollectionStatus**, logs migration, metadata config read-only và query explain. Không viết vào config database để “sửa nhanh”.

### 26.3. Các dấu hiệu phân loại root cause

**Nếu owned bytes lệch và migration liên tục thất bại**: kiểm tra balancer, zones, recipient disk, oversized ranges và CSRS/replication health.

**Nếu bytes đều nhưng CPU lệch**: tập trung hot shard-key values, query targeting, indexes, read preference hoặc phần cứng. Balancer có thể đang hoạt động đúng.

**Nếu disk không giảm sau migration**: kiểm tra orphan cleanup, indexes, storage engine và counters; ownership đã chuyển không đồng nghĩa space được trả cho hệ điều hành tức thì.

**Nếu zone khiến một shard nhiều dữ liệu hơn**: cân bằng phải tuân thủ eligible placement; data residency có thể quan trọng hơn phân bố đều toàn cluster.

**Nếu vừa thêm shard**: cho phép cơ chế balancing xử lý theo policy/threshold và đo tiến độ, thay vì mong shard mới nhận một phần dữ liệu ngay lập tức.

### 26.4. Những nguyên tắc quan trọng

1. **Shard count và replica set member count là hai đại lượng khác nhau.**
2. **Balancer enabled không đồng nghĩa có migration đang chạy hoặc cần phải chạy.**
3. **Chunk count, owned bytes, physical disk và workload QPS/CPU là bốn nhóm metrics khác nhau.**
4. **Migrations có nhiều giai đoạn; commit ownership và orphan cleanup không đồng thời về mặt disk metrics.**
5. **Zone compliance có thể quan trọng hơn global evenness.**
6. **Shard key cardinality, frequency, monotonicity và query targeting quyết định hot shard.**
7. **Jumbo/oversized ranges cần chẩn đoán theo version, không force move bừa.**
8. **Replication lag, network, cache và disk I/O có thể chặn hoặc làm chậm balancing.**
9. **Mọi phép đo skew phải có đơn vị, namespace, shard, timestamp và capacity context.**
10. **Đánh giá thành công bằng application latency, throughput, availability và SLO, không chỉ bằng số bytes đã chuyển.**
11. **Sử dụng các lệnh đọc và nguồn metrics chính thức; không sửa metadata config thủ công.**
12. **Mọi thay đổi balancer, shard key, zones hoặc migration policy trên production cần evidence và approval.**

### Tài liệu MongoDB chính thức

- [Sharding — tổng quan](https://www.mongodb.com/docs/manual/sharding/) — kiến trúc sharded cluster.
- [Sharded Cluster Components](https://www.mongodb.com/docs/manual/core/sharded-cluster-components/) — shards, mongos và config servers.
- [Sharding Balancer](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/) — balancing, di chuyển ranges và quản trị.
- [Manage the Sharded Cluster Balancer](https://www.mongodb.com/docs/manual/tutorial/manage-sharded-cluster-balancer/) — trạng thái và các lệnh balancer.
- [sh.status()](https://www.mongodb.com/docs/manual/reference/method/sh.status/) — cluster sharding overview.
- [listShards Command](https://www.mongodb.com/docs/manual/reference/command/listShards/) — liệt kê shards.
- [balancerStatus Command](https://www.mongodb.com/docs/manual/reference/command/balancerStatus/) — kiểm tra balancer.
- [balancerCollectionStatus Command](https://www.mongodb.com/docs/manual/reference/command/balancerCollectionStatus/) — collection placement status (khi version hỗ trợ).
- [getShardDistribution()](https://www.mongodb.com/docs/manual/reference/method/db.collection.getShardDistribution/) — thông tin phân bố collection.
- [$collStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/collStats/) — collection storage statistics.
- [serverStatus Command](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — node-level server metrics.
- [Zone Sharding](https://www.mongodb.com/docs/manual/core/zone-sharding/) — placement constraints và zones.
- [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/) — cardinality, frequency và query patterns.
- [Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/) — thay shard key và considerations.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — MongoClient, runCommand và aggregation.
- [Spring Data MongoDB](https://docs.spring.io/spring-data/mongodb/reference/) — MongoTemplate và framework integration.

Các helpers, collection metadata fields, balancer behavior và metrics thay đổi theo MongoDB version/deployment. Khi triển khai, hãy đối chiếu tài liệu đúng **phiên bản server, mongosh, driver và loại cluster**, đặc biệt trước các quyết định thay đổi placement.

**Kết luận:** hệ thống quan sát shard đáng tin cậy phải trả lời đồng thời ba câu hỏi: **Dữ liệu đang nằm ở đâu? Balancer có thể và đang làm gì? Người dùng có đang chịu ảnh hưởng bởi cách phân bố đó không?** Chỉ khi kết nối được ba lớp bằng dữ liệu đo có thời điểm và phạm vi rõ, bạn mới có thể phân biệt một cluster đang cân bằng đúng với một cluster đang thực sự bị lệch cần xử lý.










