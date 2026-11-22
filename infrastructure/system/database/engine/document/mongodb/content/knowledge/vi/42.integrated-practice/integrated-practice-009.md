# Thử nghiệm sharding trong môi trường tách biệt và đo phân bố dữ liệu MongoDB

## 1. Tình huống: hai shard không có nghĩa dữ liệu tự chia đều

Một ứng dụng ghi sự kiện đơn hàng với tốc độ tăng dần. Khi dữ liệu vượt khả năng lưu trữ và xử lý của một MongoDB replica set, nhóm phát triển muốn thử **sharding** để phân phối dữ liệu và tải sang nhiều shard.

Họ xây cụm có hai shards, ghi 20.000 documents rồi nhìn thấy:

~~~text
shard A: 19.800 documents
shard B:    200 documents
~~~

Có thể sharding đã bật nhưng shard key không phù hợp, chunks chưa được phân bố, hoặc hệ thống chưa có đủ dữ liệu để balancer thực hiện thay đổi. Việc có hai shards **không** chứng minh rằng dữ liệu, truy vấn hoặc ghi được phân phối đều.

Bài thuộc module **Database Engine Document MongoDB**, chương **Thực hành tổng hợp**, với đề bài **Thử nghiệm sharding trong môi trường tách biệt và đo phân bố dữ liệu**.

### 1.1. Kết quả mong muốn

Sau khi hoàn thành lab, bạn có thể:

1. Giải thích vai trò của `mongos`, config server replica set (CSRS), shard replica sets, chunks/ranges và balancer.
2. Dựng một sharded cluster **tách biệt khỏi production**, không bật cổng database công khai.
3. Khởi tạo config server, hai shard replica sets và thêm shards qua `mongos`.
4. Tạo hai collections tương đương: một **hashed shard key**, một **ranged shard key**.
5. Sinh cùng workload dữ liệu với số lượng và payload xác định.
6. Đo **owned documents, owned data size, chunk count và orphan documents** trên từng shard.
7. Tính độ lệch phân bố, phân biệt cân bằng chunks với cân bằng dung lượng/tải.
8. Sử dụng `sh.status()`, `sh.getShardedDataDistribution()`, `getShardDistribution()` và metadata `config.chunks` chỉ để quan sát.
9. Quan sát balancer, chia và di chuyển ranges ở **lab** trong tình huống được kiểm soát.
10. So query targeting: truy vấn có shard key với scatter-gather.
11. Phân tích hot shard, low-cardinality shard keys, jumbo ranges và hashed/ranged trade-offs.
12. Đo latency/throughput với cùng workload, không kết luận quá mức từ máy laptop.
13. Lập báo cáo thí nghiệm tái lập được, giải thích biến thiên và các giới hạn.
14. Cleanup lab mà không ảnh hưởng bất kỳ deployment khác.

**Nguyên tắc an toàn:** Tất cả ví dụ bên dưới chỉ dành cho **môi trường Docker Compose cục bộ hoặc staging được phê duyệt**. Không chạy `sh.addShard()`, `sh.moveChunk()`, `rs.initiate()`, `dropDatabase()` hoặc thay balancer trên production để “thử”.

## 2. Sharding là gì và không phải gì?

MongoDB sharding phân phối một **sharded collection** theo giá trị **shard key** trên các shards.

~~~text
Application / mongosh
          |
          v
       mongos
    (query router)
          |
          +---------- Config Server Replica Set
          |             - collection metadata
          |             - chunk/range ownership
          |
          +---------- Shard A Replica Set
          |             - owned ranges/documents
          |
          +---------- Shard B Replica Set
                        - owned ranges/documents
~~~

- **mongos**: nhận lệnh từ ứng dụng, định tuyến đến shard cần thiết và tổng hợp kết quả.
- **Config server replica set**: lưu metadata về cluster topology, sharded namespaces và range ownership.
- **Shard**: thông thường là một replica set chứa một phần dữ liệu.
- **Shard key**: một hoặc nhiều fields dùng để quyết định nơi dữ liệu nằm.
- **Chunk/range**: một khoảng giá trị shard key do một shard sở hữu.
- **Balancer**: theo dõi phân phối ranges/chunks và chuyển chúng khi cần.

### 2.1. Sharding khác replication

| Đặc tính | Replica set | Sharded cluster |
|---|---|---|
| Mục tiêu chính | High availability và durability | Horizontal data distribution/scale |
| Dữ liệu trên mỗi node | Các members replicate cùng dataset của shard | Mỗi shard lưu subset, trong shard lại replicated |
| Failover | Primary election trong replica set | Replica set election trong từng shard + CSRS |
| Query routing | Driver topology discovery | `mongos` định tuyến theo metadata |
| Cấu hình | Replica set members | CSRS, mongos và nhiều shards |

### 2.2. Không phải mọi collection đều sharded

Một database nằm trong sharded cluster có thể chứa collections chưa được shard. Chúng vẫn có thể nằm tại một primary shard thay vì phân phối theo shard key.

### 2.3. Không đồng nhất shard với server vật lý

Ở lab, hai shards có thể là hai containers trên **cùng một laptop**. Chúng có logic sharding khác nhau nhưng vẫn chia sẻ CPU, RAM, disk và Docker bridge. Không dùng kết quả này để suy ra tốc độ tăng gấp đôi trên production.

## 3. Định nghĩa phân bố dữ liệu trước khi đo

Nên đo ít nhất bốn đại lượng:

| Đại lượng | Ý nghĩa | Có thể bị hiểu sai khi |
|---|---|---|
| Owned documents | Số documents thuộc shard theo routing ownership | Chunks nhiều nhưng documents ít |
| Owned size bytes | Kích thước documents thuộc shard khi chưa nén | Nhầm với disk usage/WiredTiger |
| Chunk/range count | Số khoảng shard-key do shard sở hữu | Chunks có kích thước không bằng nhau |
| Orphan documents | Bản sao tạm sau range migration chờ xóa | Cộng orphan vào logical dataset |
| Query targeting | Bao nhiêu shards được query chạm tới | Có data balance nhưng query scatter |
| Read/write utilization | CPU, I/O, ops/s, latency từng shard | Một shard phục vụ hot key |

### 3.1. Ví dụ “cân bằng chunks nhưng lệch dữ liệu”

~~~text
Shard A:  4 chunks, 90.000 documents, 300 MB owned
Shard B:  4 chunks, 10.000 documents,  40 MB owned
~~~

Số chunks bằng nhau nhưng documents và bytes chênh lệch lớn.

### 3.2. Ví dụ “cân bằng documents nhưng lệch tải”

~~~text
Shard A: 50.000 docs, 500 read ops/s
Shard B: 50.000 docs, 9.000 read ops/s
~~~

Một hot tenant/key có thể gây tải nặng cho shard B dù data distribution hoàn hảo.

### 3.3. Cần xác định tiêu chí riêng

Một lab hai shards có thể đặt mục tiêu tham khảo như `maxDocumentShare ≤ 60%`, nhưng đó là **ngưỡng chấp nhận tự định nghĩa cho experiment**, không phải bảo đảm của MongoDB. Trên cluster thực, bytes, query distribution, zones và workload mới quyết định tính cân bằng hữu ích.

## 4. Tại sao cần môi trường tách biệt?

Sharding commands có thể:

- Tạo thêm metadata và indexes.
- Chuyển ranges gây I/O, network, replication.
- Làm thay đổi query routing.
- Kích hoạt chunk migrations/range deletion.
- Tạo tải hoặc lock contention.
- Ảnh hưởng tính sẵn sàng nếu cấu hình sai.

### 4.1. Phương án cho bài lab

Ta dùng một Docker Compose project **mongo-sharding-lab** gồm:

~~~text
Host machine
  |
  +-- 127.0.0.1:27027 -> mongos:27017
  |
  +-- Docker private bridge (không publish các cổng này)
         |
         +-- cfg:27019       CSRS, 1 voting member
         +-- shard-a:27018   rsShardA, 1 voting member
         +-- shard-b:27018   rsShardB, 1 voting member
         +-- mongos:27017    router
~~~

### 4.2. Vì sao chỉ một member mỗi replica set?

MongoDB Manual cho phép một member cho config server replica set và mỗi shard replica set **để thử nghiệm**. Production cần nhiều members trên failure domains riêng, thường ít nhất ba members/voting quorum phù hợp.

Lab một member **không kiểm thử failover thật, durability dưới mất node hoặc network partition**. Nó chỉ đủ để nghiên cứu shard-key distribution và routing.

### 4.3. Bảo mật lab

Để đơn giản, ví dụ chưa bật authorization/TLS nội bộ và dùng `--bind_ip_all` **chỉ bên trong mạng containers**. Do đó:

- Không map cổng config/shards ra host.
- Chỉ publish router ở `127.0.0.1`.
- Không đặt lab trên host dùng chung hoặc mạng không tin cậy.
- Không kết nối từ app production tới router lab.
- Không dùng credentials hoặc dữ liệu thật.
- Không áp cấu hình này vào cloud/public IP.

Production bắt buộc áp các biện pháp như RBAC, TLS/internal authentication, firewall/network segregation và observability.

## 5. Yêu cầu trước khi bắt đầu

Cần có:

- Docker Engine và Docker Compose v2.
- Docker daemon đang chạy.
- Máy đủ RAM/CPU cho bốn MongoDB processes; có dung lượng đĩa vài GB.
- `mongosh` thông qua container image; không bắt buộc cài trực tiếp trên host.
- Terminal Bash, PowerShell hoặc tương đương.
- Cổng `127.0.0.1:27027` chưa bị ứng dụng khác chiếm.
- MongoDB image version được cố định theo chính sách; ví dụ sử dụng `mongo:8.0` cho lab. Với CI, nên pin digest đã kiểm duyệt để tái lập chính xác.

**Ghi chú phiên bản:** Một số mongosh commands/định dạng output thay đổi giữa MongoDB 6.x–9.x. Bài cố định tư duy và ví dụ cho **MongoDB 8.0**; xem docs của server và mongosh đang dùng khi so sánh.

### 5.1. Không dựng lab trong thư mục chứa production compose

Đặt file ở một thư mục mới, ví dụ `mongo-sharding-lab/compose.yaml`. Chạy mọi lệnh trong đúng thư mục đó với project name `mongo-sharding-lab`.

### 5.2. Tài nguyên vẫn dùng chung host

Không chạy stress test lớn khi máy đang phục vụ workloads quan trọng. Docker Compose tạo isolation logic/network, không phải bảo đảm CPU/disk isolation nếu không cấu hình limits.

## 6. File Docker Compose

Tạo file `compose.yaml` trong thư mục lab:

~~~yaml
services:
  cfg:
    image: mongo:8.0
    command:
      - mongod
      - --configsvr
      - --replSet
      - cfgRS
      - --port
      - "27019"
      - --bind_ip_all
    networks: [sharding_lab_net]
    volumes:
      - cfg_data:/data/db

  shard-a:
    image: mongo:8.0
    command:
      - mongod
      - --shardsvr
      - --replSet
      - rsShardA
      - --port
      - "27018"
      - --bind_ip_all
    networks: [sharding_lab_net]
    volumes:
      - shard_a_data:/data/db

  shard-b:
    image: mongo:8.0
    command:
      - mongod
      - --shardsvr
      - --replSet
      - rsShardB
      - --port
      - "27018"
      - --bind_ip_all
    networks: [sharding_lab_net]
    volumes:
      - shard_b_data:/data/db

  mongos:
    image: mongo:8.0
    command:
      - mongos
      - --configdb
      - cfgRS/cfg:27019
      - --port
      - "27017"
      - --bind_ip_all
    depends_on:
      - cfg
      - shard-a
      - shard-b
    ports:
      - "127.0.0.1:27027:27017"
    networks: [sharding_lab_net]

networks:
  sharding_lab_net:
    driver: bridge

volumes:
  cfg_data:
  shard_a_data:
  shard_b_data:
~~~

### 6.1. Vì sao không publish shards?

Ứng dụng sharded cluster bình thường phải kết nối qua `mongos`, không gửi CRUD trực tiếp vào từng shard. MongoDB 8.0 còn có thêm hạn chế đối với một số lệnh trực tiếp trên shards và role maintenance đặc biệt `directShardOperations`; không dùng role đó trong lab thông thường.

### 6.2. Named volumes giữ dữ liệu qua restart

`docker compose down` thông thường không xóa named volumes. `down -v` **xóa dữ liệu lab**, chỉ dùng khi muốn reset hoàn toàn và đã kiểm tra project/directory.

### 6.3. depends_on chưa bảo đảm replica set initialized

Compose sẽ start processes theo phụ thuộc, nhưng `cfgRS` chưa khởi tạo thì `mongos` có thể chưa sẵn sàng. Ta sẽ khởi tạo config/shards trước, sau đó mới start router.

### 6.4. Cảnh báo hostname

MongoDB replica set members quảng bá hostname `cfg`, `shard-a`, `shard-b`. Các hostnames này phải resolve trong Docker network. Không cấu hình members bằng `localhost` hoặc IP container tạm thời khi các members cần nói chuyện liên-container.

## 7. Khởi chạy config server và shard processes

Trong terminal ở thư mục chứa `compose.yaml`:

~~~bash
docker compose -p mongo-sharding-lab up -d cfg shard-a shard-b
~~~

Kiểm tra:

~~~bash
docker compose -p mongo-sharding-lab ps
~~~

Các containers phải ở trạng thái running trước khi dùng `rs.initiate()`.

### 7.1. Nếu containers exit

~~~bash
docker compose -p mongo-sharding-lab logs --tail=80 cfg
docker compose -p mongo-sharding-lab logs --tail=80 shard-a
docker compose -p mongo-sharding-lab logs --tail=80 shard-b
~~~

Không chạy tiếp nếu ports/volumes bị lỗi.

### 7.2. Không dùng hostname localhost trong rs config

Dùng service DNS names như `cfg:27019`. Các addresses cấu hình cho replica set phải phù hợp với cách nội bộ và router truy cập.

## 8. Khởi tạo CSRS

Chạy **một lần**:

~~~bash
docker compose -p mongo-sharding-lab exec -T cfg mongosh \
  --quiet --port 27019 \
  --eval 'rs.initiate({_id:"cfgRS",configsvr:true,members:[{_id:0,host:"cfg:27019"}]})'
~~~

Kết quả hợp lệ thông thường có `ok:1`. Không chạy `rs.initiate()` lặp khi replica set đã được cấu hình.

### 8.1. Kiểm tra elected primary

~~~bash
docker compose -p mongo-sharding-lab exec -T cfg mongosh \
  --quiet --port 27019 \
  --eval 'printjson(db.hello())'
~~~

Chờ đến khi có `isWritablePrimary:true`. Có thể kiểm tra `rs.status()` nếu cần.

### 8.2. Vì sao configsvr:true?

`cfgRS` là config server replica set, không phải một shard chứa dữ liệu nghiệp vụ theo thiết kế **dedicated config server** của bài lab.

### 8.3. Khác với config shard mới hơn

MongoDB hiện có khả năng config shard, nhưng bài này dùng dedicated CSRS để giữ topology dễ quan sát. Không nhầm hai mô hình khi đọc tài liệu 8.x/9.x.

## 9. Khởi tạo hai shard replica sets

Khởi tạo shard A:

~~~bash
docker compose -p mongo-sharding-lab exec -T shard-a mongosh \
  --quiet --port 27018 \
  --eval 'rs.initiate({_id:"rsShardA",members:[{_id:0,host:"shard-a:27018"}]})'
~~~

Khởi tạo shard B:

~~~bash
docker compose -p mongo-sharding-lab exec -T shard-b mongosh \
  --quiet --port 27018 \
  --eval 'rs.initiate({_id:"rsShardB",members:[{_id:0,host:"shard-b:27018"}]})'
~~~

### 9.1. Kiểm tra trạng thái từng shard

~~~bash
docker compose -p mongo-sharding-lab exec -T shard-a mongosh \
  --quiet --port 27018 \
  --eval 'printjson(db.hello())'

docker compose -p mongo-sharding-lab exec -T shard-b mongosh \
  --quiet --port 27018 \
  --eval 'printjson(db.hello())'
~~~

Đợi mỗi replica set đạt primary. Không chạy `sh.addShard` trước khi shards có thể phục vụ.

### 9.2. Cấu hình một node không thể election sang node khác

Khi shard-a container chết, không có secondary của rsShardA để nhận primary. Lab phân bố **không** đại diện bài test HA/failover.

## 10. Start router mongos

~~~bash
docker compose -p mongo-sharding-lab up -d mongos
~~~

Kiểm tra logs:

~~~bash
docker compose -p mongo-sharding-lab logs --tail=80 mongos
~~~

Kết nối vào router từ chính container:

~~~bash
docker compose -p mongo-sharding-lab exec -T mongos mongosh \
  --quiet --port 27017 \
  --eval 'printjson(db.hello())'
~~~

Output của `mongos` thường có `msg:"isdbgrid"`.

### 10.1. Kết nối từ host

Nếu đã cài `mongosh`:

~~~bash
mongosh "mongodb://127.0.0.1:27027"
~~~

Mọi lệnh sharding administration tiếp theo phải được chạy thông qua **mongos**.

### 10.2. Nếu mongos không start sau config initialization

Xem logs/hostnames, đảm bảo `cfgRS` đạt primary và khởi động lại riêng service router nếu cần:

~~~bash
docker compose -p mongo-sharding-lab restart mongos
~~~

Không xóa volumes để chữa lỗi topology nếu chưa hiểu nguyên nhân.

## 11. Thêm shard replica sets vào cluster

Kết nối `mongosh` qua router:

~~~bash
docker compose -p mongo-sharding-lab exec mongos mongosh \
  --port 27017
~~~

Trong shell kết nối với `mongos`:

~~~javascript
sh.addShard("rsShardA/shard-a:27018");
sh.addShard("rsShardB/shard-b:27018");

sh.status();
~~~

### 11.1. Kiểm tra listShards

~~~javascript
db.adminCommand({ listShards: 1 });
~~~

Kỳ vọng thấy hai shard identities tương ứng với `rsShardA` và `rsShardB` (tên shard cụ thể được server trả về là nguồn sự thật).

### 11.2. Lưu ý sh.addShard là thay đổi metadata

Đây là thao tác admin làm thay đổi topology; lab chỉ thêm shard replica sets đã khởi tạo. Không tự thực hiện trên Atlas production.

### 11.3. Ghi baseline

Trước khi shard collections, lưu:

- Server version: `db.version()`.
- Mongosh version: `version()` / `mongosh --version` tùy shell.
- Shard list.
- Balancer state.
- RAM, Docker CPU, host disk.
- Thời điểm UTC và Git revision của tài liệu thử nghiệm.

## 12. Xác định hai shard-key strategies để so sánh

Ta dùng hai collections độc lập cùng số documents:

| Collection | Shard key | Dự đoán |
|---|---|---|
| `shard_lab.events_hash` | `{ eventId:"hashed" }` | Nhiều eventIds khác nhau có hash phân tán |
| `shard_lab.events_range` | `{ sequence:1 }` | Sequence tăng liên tục có nguy cơ dồn một range |

Các field `eventId` và `sequence` của lab đều có cardinality lớn. Khác biệt chính là MongoDB phân vùng theo **giá trị hash** hoặc **giá trị gốc trong range**.

### 12.1. Hash có thể phân phối tốt nhưng không bảo đảm đều tuyệt đối

Hashing tạo phân bố tương đối đều với keys đa dạng; việc mỗi hash range được shard nào giữ, dữ liệu skew, migration, jumbo ranges và workload đều ảnh hưởng kết quả.

### 12.2. Range phù hợp truy vấn có thứ tự nhưng có nguy cơ hotspot

Query `sequence BETWEEN 10000 AND 15000` có thể target một hoặc vài shards. Nhưng khi mọi insert đi vào “đuôi” sequence tăng, hotspot xuất hiện ở range mới nhất.

### 12.3. Không khẳng định đây là shard key tốt cho production

Ví dụ chỉ nhằm minh họa. Với ứng dụng đa tenant và nhiều access patterns, thường cần compound shard key/zone/hashed prefix và benchmark chuyên biệt.

## 13. Tạo database và collections

Trong mongosh router:

~~~javascript
sh.enableSharding("shard_lab");

const labDb = db.getSiblingDB("shard_lab");

labDb.createCollection("events_hash");
labDb.createCollection("events_range");
~~~

Từ MongoDB 6.0, `sh.enableSharding()` không còn là bước bắt buộc để shard collection; dùng ở đây để làm bài học rõ ràng.

### 13.1. Index hỗ trợ shard key

~~~javascript
labDb.events_hash.createIndex({ eventId: "hashed" });
labDb.events_range.createIndex({ sequence: 1 });
~~~

Đối với populated collection, phải có supporting index trước khi shard. Với empty collection, MongoDB có thể tạo index nếu cần.

### 13.2. Hai collections vẫn rỗng

Kiểm tra:

~~~javascript
labDb.events_hash.countDocuments({});
labDb.events_range.countDocuments({});
~~~

Phải là `0` trước khi tiếp tục nếu muốn so sánh một lần nạp deterministic. Nếu đã có dữ liệu từ run cũ, **không tự drop production data**: dùng một lab project mới hoặc khởi tạo lại lab có chủ đích.

## 14. Shard collection khi còn rỗng

~~~javascript
sh.shardCollection(
  "shard_lab.events_hash",
  { eventId: "hashed" }
);

sh.shardCollection(
  "shard_lab.events_range",
  { sequence: 1 }
);
~~~

### 14.1. MongoDB 8.0: initial chunks khác nhau

Trên empty collection với single-field hashed shard key và không có zones, MongoDB 8.0 mặc định tạo **một chunk ban đầu cho mỗi shard** rồi phân phối qua cluster (hành vi có thể khác ở release khác).

Với ranged shard key trên empty collection không có zones, sharding thường khởi tạo **một chunk bao trùm toàn bộ key space**.

### 14.2. Đo ngay sau khi shard

~~~javascript
sh.status(true);

labDb.events_hash.getShardDistribution();
labDb.events_range.getShardDistribution();
~~~

Lúc này số docs bằng 0 nên chưa đánh giá được data distribution, dù chunk ownership đã có.

### 14.3. Không dùng unique:true với hashed

MongoDB không hỗ trợ unique hashed index. Nếu bạn cần database enforce eventId uniqueness, phải thiết kế khác (regular unique index phù hợp shard-key prefix; hoặc xử lý uniqueness trong ứng dụng/hệ thống riêng).

### 14.4. Lưu ý _id trên sharded collection

Nếu `_id` không là shard key, tính duy nhất `_id` trên toàn cluster có thể không được MongoDB enforce trong mọi sharded configurations. Trong lab, producer cấp stable unique IDs; không coi mỗi collection sẽ tự bảo vệ global uniqueness xuyên shards.

## 15. Sinh hai datasets tương đương

Ta nạp **20.000 documents/collection** với payload cố định khoảng 1 KiB, đủ nhìn thấy phân bố cơ bản mà không gây stress lớn lên laptop.

Trong mongosh router:

~~~javascript
const d = db.getSiblingDB("shard_lab");
const N = 20000;
const BATCH = 500;
const pad = "x".repeat(1024);
const baseTime = new Date("2026-11-14T00:00:00.000Z");

if (d.events_hash.countDocuments({}) !== 0 ||
    d.events_range.countDocuments({}) !== 0) {
  throw new Error("Lab collections must be empty before seeding.");
}

let insertedHash = 0;
let insertedRange = 0;

for (let start = 0; start < N; start += BATCH) {
  const hashBatch = [];
  const rangeBatch = [];

  for (let i = start; i < Math.min(start + BATCH, N); i++) {
    const id = String(i).padStart(8, "0");
    const tenant = "tenant-" + String(i % 16).padStart(2, "0");
    const timestamp = new Date(baseTime.getTime() + i * 1000);

    hashBatch.push({
      _id: "h-" + id,
      eventId: "evt-" + id,
      tenantId: tenant,
      sequence: i,
      createdAt: timestamp,
      payload: pad
    });

    rangeBatch.push({
      _id: "r-" + id,
      eventId: "evt-" + id,
      tenantId: tenant,
      sequence: i,
      createdAt: timestamp,
      payload: pad
    });
  }

  d.events_hash.insertMany(hashBatch, { ordered: false });
  d.events_range.insertMany(rangeBatch, { ordered: false });

  insertedHash += hashBatch.length;
  insertedRange += rangeBatch.length;
}

printjson({ insertedHash, insertedRange });
~~~

### 15.1. Tại sao dùng pad payload?

Nếu chỉ lưu vài fields nhỏ trên 20.000 documents, data size quá nhỏ và storage/balancer conditions rất khác production. Payload cố định làm experiment bớt biến động, dù vẫn không đủ để mô phỏng workload thật.

### 15.2. Tại sao dùng 16 tenants?

Cho phép thử truy vấn tenant-specific và giải thích vì sao hashed theo eventId phân tán events của cùng tenant sang nhiều shards.

### 15.3. Vì sao không phải 1 triệu documents ngay?

Lab nhỏ giúp quan sát mechanics và hoàn thành nhanh. Sau khi đúng, có thể tăng `N` hoặc payload với giới hạn tài nguyên, và ghi số liệu. Đừng vừa tăng N vừa đổi index/shard key nếu muốn so sánh có ý nghĩa.

### 15.4. insertMany có retry/error semantics

Nếu lệnh nạp bị ngắt giữa chừng, có thể chỉ một số batches đã commit. Vì vậy dùng `countDocuments` và unique IDs/seed marker để xác định actual input; không giả định N documents đã chắc chắn ghi khi terminal bị disconnect.

## 16. Kiểm tra tổng logical documents

~~~javascript
printjson({
  hashedCount: d.events_hash.countDocuments({}),
  rangedCount: d.events_range.countDocuments({})
});
~~~

Sau một run thành công trên collection rỗng, hai counts phải là `20000`.

### 16.1. Count trả lời gì?

Đây là logical count khi truy vấn qua `mongos`. Nó không thể cho biết mỗi shard sở hữu bao nhiêu documents.

### 16.2. Không đọc trực tiếp shards để cộng lại

Range migration có thể để lại orphan documents chờ dọn. Đọc trực tiếp shard như một standalone database có thể tính lặp và còn có rủi ro tác động routing; hãy dùng các mongos helpers/cluster metrics được hỗ trợ.

### 16.3. Bảo đảm dataset tương đương

Một collection có thể nhiều indexes hơn collection khác (hashed vs ascending index), nên disk/index sizes khác nhau là bình thường. Mục tiêu so sánh chính ở đây là **phân bố logical documents** và query routing, không phải tuyệt đối từng byte disk.

## 17. Công cụ đo 1: getShardDistribution()

Trên router:

~~~javascript
d.events_hash.getShardDistribution();
d.events_range.getShardDistribution();
~~~

Mongosh in thống kê mỗi shard:

~~~text
Shard rsShardA:
  docs: ...
  data: ...
  chunks: ...

Shard rsShardB:
  docs: ...
  data: ...
  chunks: ...

Totals:
  docs: ...
  data: ...
  chunks: ...
  % data / % docs per shard
~~~

Đây chỉ là **mẫu cấu trúc output**, không phải số đo của lab đã chạy.

### 17.1. Đọc đúng “docs”

Trường `docs` giúp ước lượng phân bố, nhưng behavior đối với orphan documents thay đổi theo mongosh version. Từ mongosh 2.3.3, helper không tính orphan vào regular sharded data; bản cũ có thể tính cả orphan đang chờ xóa.

### 17.2. Đọc đúng “data”

Con số data size không phải disk usage chính xác. Chênh lệch BSON sizes, compression, indexes và WiredTiger storage làm disk bytes khác logical document bytes.

### 17.3. Đừng so chunks đơn lẻ

Nếu mỗi shard có 1 chunk nhưng shard A chứa 99% documents, phân bố không cân bằng theo documents. Chunks là ranges, không phải các túi có kích thước cố định.

## 18. Công cụ đo 2: sh.getShardedDataDistribution()

MongoDB 6.0.3+ hỗ trợ:

~~~javascript
const distribution = sh.getShardedDataDistribution();

printjson(
  distribution.filter(item =>
    item.ns === "shard_lab.events_hash" ||
    item.ns === "shard_lab.events_range"
  )
);
~~~

Output cho mỗi namespace gồm các shard records có fields:

~~~javascript
{
  ns: "shard_lab.events_hash",
  shards: [
    {
      shardName: "rsShardA",
      numOrphanedDocs: 0,
      numOwnedDocuments: 10100,
      ownedSizeBytes: 12000000,
      orphanedSizeBytes: 0
    },
    {
      shardName: "rsShardB",
      numOrphanedDocs: 0,
      numOwnedDocuments: 9900,
      ownedSizeBytes: 11800000,
      orphanedSizeBytes: 0
    }
  ]
}
~~~

**Các số trên chỉ minh họa.** Lab thực tế có thể khác, và ban đầu có thể xuất hiện orphan data trong khi migrations đang hoàn tất.

### 18.1. Owned vs orphan

- `numOwnedDocuments`: documents thuộc shard theo ownership.
- `ownedSizeBytes`: kích thước documents sở hữu tính theo **uncompressed bytes**.
- `numOrphanedDocs`: số orphan documents chờ cleanup.
- `orphanedSizeBytes`: kích thước orphan documents.

### 18.2. Đo tại mongos

Helper chỉ được chạy từ `mongosh` kết nối tới `mongos`. Nó không chạy ở standalone/shard direct connection và không được hỗ trợ trên một số Atlas free/flex tiers.

### 18.3. Tại sao 20.000 không nhất thiết 10.000/10.000?

Hash distribution có biến thiên thống kê và initial ranges được gán shard theo metadata. Cân bằng chính xác 50/50 không phải điều được bảo đảm.

## 19. Tự tính tỷ lệ dữ liệu trên từng shard

Trong mongosh, có thể tính từ `sh.getShardedDataDistribution()`:

~~~javascript
(() => {
  const ns = "shard_lab.events_hash";
  const doc = sh.getShardedDataDistribution()
    .find(item => item.ns === ns);

  if (!doc) {
    throw new Error("No sharded distribution for " + ns);
  }

  const rows = doc.shards.map(s => ({
    shard: s.shardName,
    docs: s.numOwnedDocuments,
    bytes: s.ownedSizeBytes,
    orphans: s.numOrphanedDocs
  }));

  const totalDocs = rows.reduce((x, r) => x + r.docs, 0);
  const totalBytes = rows.reduce((x, r) => x + r.bytes, 0);

  const result = rows.map(r => ({
    shard: r.shard,
    docs: r.docs,
    docsPct: totalDocs === 0 ? 0 : 100 * r.docs / totalDocs,
    bytes: r.bytes,
    bytesPct: totalBytes === 0 ? 0 : 100 * r.bytes / totalBytes,
    orphans: r.orphans
  }));

  printjson({ ns, totalDocs, totalBytes, result });
})();
~~~

### 19.1. Công thức

Với shard `s`:

\[
p_s = \frac{\text{ownedDocs}_s}{\sum_i \text{ownedDocs}_i} \times 100\%.
\]

Với hai shards:

\[
\text{gap}_{pp} = |p_A - p_B|.
\]

`gap_pp` là chênh lệch theo **percentage points**, không phải phần trăm tăng trưởng.

### 19.2. Đánh giá mẫu

Nếu A=10.200 docs và B=9.800 docs:

- A = 51%.
- B = 49%.
- Gap = 2 percentage points.
- Max/min count ratio ≈ 1.04.

Nếu A=19.000 và B=1.000, gap=90 points; dữ liệu cực lệch mặc dù cả hai đều có chunks.

### 19.3. Phân biệt expected với measured

Không ghi 10.000/10.000 vào báo cáo chỉ vì đó là target lý tưởng. Ghi output thật, thời điểm đo, version và trạng thái balancer.

## 20. Đo nhiều lần thay vì lấy một snapshot

Data migration và orphan cleanup chạy bất đồng bộ. Nên đo:

- T0: ngay sau sharding, trước insert.
- T1: ngay sau khi insert xong.
- T2: sau khi quan sát balancer hoạt động.
- T3: sau một khoảng ổn định, không còn migration.
- T4: sau khi áp dụng split/move thử nghiệm ở ranged collection.

### 20.1. Không dùng số liệu T1 làm kết luận cuối

Ngay sau nạp dữ liệu, balancer có thể chưa hoàn tất. Một shard giữ nhiều dữ liệu tạm thời không chứng minh shard key hỏng.

### 20.2. Điều kiện “ổn định”

Thay vì chỉ sleep 30 giây, kiểm tra:

- `sh.balancerCollectionStatus(namespace)`.
- `sh.status()` cho migrations/failed rounds.
- Owned docs/bytes không còn thay đổi đáng kể qua vài lần đo.
- Orphan docs không còn tăng do migration.
- Cluster nodes healthy.

Không đặt kỳ vọng tất cả counters bằng zero tuyệt đối nếu hệ thống còn background processes.

## 21. Đo chunks từ config metadata (read-only)

Khi muốn xem chunk ownership bằng metadata:

~~~javascript
const cfgDb = db.getSiblingDB("config");

const c = cfgDb.collections.findOne({
  _id: "shard_lab.events_hash"
});

if (!c) {
  throw new Error("Sharded collection metadata missing");
}

printjson({
  namespace: c._id,
  uuid: c.uuid,
  shardKey: c.key
});

printjson(
  cfgDb.chunks.aggregate([
    { $match: { uuid: c.uuid } },
    {
      $group: {
        _id: "$shard",
        chunks: { $sum: 1 }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray()
);
~~~

### 21.1. Vì sao dùng UUID thay vì ns?

Trong các phiên bản MongoDB hiện đại (MongoDB 5.0+), `config.chunks` dùng `uuid` để tham chiếu collection. Ví dụ cũ truy vấn `{ns:"db.collection"}` có thể không áp dụng.

### 21.2. Config metadata là implementation detail

Schema của `config` database có thể thay đổi giữa MongoDB versions. Dùng helpers chính thức khi có thể và không viết, sửa hoặc xóa trực tiếp metadata `config.chunks`.

### 21.3. Ranh giới chunk

Từng document chunk thường có `min` và `max` thể hiện khoảng `[min,max)`, cùng shard owner. Với hashed key, bounds là **hash ranges**, không phải eventId strings ban đầu.

### 21.4. Không nhầm chunk count với “documents per shard”

Bốn chunks có thể chỉ chứa một lượng nhỏ dữ liệu, trong khi một chunk khác chứa phần lớn records nếu key distribution skewed.

## 22. Balancer có bật hay đang di chuyển dữ liệu?

Trên mongos:

~~~javascript
sh.getBalancerState();
sh.isBalancerRunning();

sh.balancerCollectionStatus(
  "shard_lab.events_hash"
);
~~~

### 22.1. Enabled khác active

`sh.getBalancerState()` cho biết balancer **được phép chạy**. Nó không chứng minh hiện có chunk migration.

`sh.isBalancerRunning()` và `sh.status()` cung cấp tín hiệu hoạt động của balancer theo MongoDB/mongosh version.

### 22.2. Collection balancer status

`sh.balancerCollectionStatus(namespace)` cho biết collection có đang đáp ứng các yêu cầu phân phối/balance hay còn cần di chuyển vì range imbalance, zone violation hoặc draining shard.

Không lấy chỉ một boolean làm bằng chứng business workload cân bằng.

### 22.3. Balancer quyết định dựa trên chính sách/ranges

Balancer không nhất thiết di chuyển vì chênh vài trăm documents, nhất là dataset nhỏ hơn chunk size hoặc không có split cần thiết.

### 22.4. Không bật/tắt balancer trên production để thử

Các lệnh `sh.stopBalancer()`/`sh.startBalancer()` tác động toàn cluster. Nếu bài thử yêu cầu thay state, chỉ làm trong lab có thể reset; lưu trạng thái trước và phục hồi sau.

## 23. Thí nghiệm hashed shard key: đọc kết quả đúng

Trên MongoDB 8.0, sharding một empty collection với single-field hashed key thường tạo initial chunks phân tán, nên khi ingest 20.000 eventIds đa dạng, ta thường thấy dữ liệu trên **cả hai shards**.

### 23.1. Kỳ vọng dạng số, không phải số cố định

~~~text
rsShardA: ~50% owned docs
rsShardB: ~50% owned docs

Exact result depends on hash ranges and data.
~~~

Đây là giả thuyết cần đo. Nếu chỉ một shard có documents, hãy kiểm tra:

- Collection thật sự sharded chưa?
- Hashed initial ranges đã được phân phối chưa?
- Mongos metadata đã cập nhật chưa?
- Balancer/migrations đang chạy?
- Query measurement đang gọi đúng namespace?
- Có sample quá nhỏ hoặc key values trùng lặp nhiều không?

### 23.2. Số lượng shard không phải mức tăng thông lượng

Hashed key có thể phân phối insert tốt hơn range monotonic key, nhưng writes còn phụ thuộc journaling, network, replication, index maintenance và CPU của cùng host.

### 23.3. Point lookup theo eventId

~~~javascript
d.events_hash.find({
  eventId: "evt-00000100"
}).explain("executionStats");
~~~

Do filter có equality trên full hashed shard key, mongos có thể định tuyến tới shard sở hữu hash tương ứng. Hãy xem `winningPlan` và shard execution stats; không giả định chính xác tên stage cố định giữa versions.

### 23.4. Range lookup trên unhashed sequence

~~~javascript
d.events_hash.find({
  sequence: { $gte: 10000, $lt: 11000 }
}).explain("executionStats");
~~~

Vì `sequence` không phải shard key của collection này, mongos có thể scatter-gather đến nhiều shards dù index hỗ trợ filter.

## 24. Thí nghiệm ranged shard key: hiện tượng skew

Với `{sequence:1}`, empty collection thường bắt đầu từ **một range bao trùm toàn key space**. Sau nạp 20.000 records ~1 KiB, dataset có thể quá nhỏ để tự kích hoạt splitting theo kích thước/điều kiện balancer.

Kỳ vọng khả dĩ:

~~~text
rsShardA: 20.000 docs
rsShardB:      0 docs
~~~

Đây là ví dụ **có thể xảy ra**, không phải số mặc định của MongoDB hay một kết quả lab đã được đo.

### 24.1. Ranged sharding không sai vì initial distribution chưa đều

Nếu dữ liệu ít và query thường là time/sequence range, một shard có thể phục vụ workload hợp lý. Đánh giá dựa vào capacity và traffic, không chỉ target 50/50.

### 24.2. Nhưng monotonic insert có nguy cơ hotspot

Nếu mọi insert mới có `sequence` lớn hơn các keys cũ, chúng đi vào uppermost range. Một shard nhận hầu hết writes tại thời điểm đó, cho dù các ranges lịch sử được rải đều.

### 24.3. Đo trước khi can thiệp

~~~javascript
d.events_range.getShardDistribution();

sh.balancerCollectionStatus(
  "shard_lab.events_range"
);
~~~

Lưu snapshot T1. Các bước split/move sau chỉ phục vụ quan sát ở **lab**.

## 25. Thí nghiệm chia range thủ công trong lab

**Cảnh báo:** MongoDB thường khuyến nghị để hệ thống tự quản lý chunk splitting/balancing. `sh.splitAt()` được sử dụng ở đây chỉ để chứng minh mechanics trên cluster thử nghiệm.

Chia collection theo ranh giới `sequence=10000`:

~~~javascript
sh.splitAt(
  "shard_lab.events_range",
  { sequence: 10000 }
);
~~~

Sau split, hai ranges về mặt logic là:

~~~text
[MinKey, 10000)
[10000, MaxKey)
~~~

### 25.1. splitAt chưa di chuyển dữ liệu

Lệnh chỉ tách một chunk thành hai chunks. **Cả hai chunks vẫn có thể ở cùng một shard**. Đây là điểm khác nhau giữa *split* và *migration*.

### 25.2. Chọn split point dựa trên dữ liệu thử

Trong lab ta có keys 0..19999, nên 10000 chia khoảng gần 50% theo số documents. Với production, chia giữa giá trị key **không bảo đảm** chia đôi theo bytes nếu payload sizes khác nhau.

### 25.3. AutoMerger và balancer có thể ảnh hưởng

Các phiên bản MongoDB hiện đại có AutoMerger và balancer. Nếu range vừa split bị merge trở lại trước bước quan sát hoặc metadata thay đổi, kiểm tra trạng thái và thực hiện thí nghiệm dưới chính sách lab phù hợp. Không tắt AutoMerger trên production chỉ để nhìn một split.

## 26. Di chuyển chunk/range đã tách sang shard B

Chỉ ở lab, xác định shard IDs qua:

~~~javascript
db.adminCommand({ listShards: 1 });
~~~

Giả sử shard đích có ID `rsShardB`, có thể:

~~~javascript
sh.moveChunk(
  "shard_lab.events_range",
  { sequence: 15000 },
  "rsShardB"
);
~~~

`sh.moveChunk(namespace,query,destination)` tìm chunk chứa giá trị shard key chỉ định rồi di chuyển chunk đó đến shard đích.

### 26.1. Kỳ vọng

Nếu range [10000,MaxKey) được chuyển sang B:

~~~text
rsShardA: keys 0..9999      -> ~10.000 docs
rsShardB: keys 10000..19999 -> ~10.000 docs
~~~

**Đây là kết quả logic dự kiến**, còn số đo thực tế phải đọc từ cluster. Migrations/range deletion có thể chưa hoàn tất vào đúng thời điểm đo.

### 26.2. Không dùng moveChunk bừa với hashed key

MongoDB docs nêu `sh.moveChunk()` helper không dùng được với hashed shard keys theo cách `find`; muốn move hashed range cần command với bounds thích hợp. Bài này chỉ dùng helper cho **ranged collection**.

### 26.3. Vì sao không chạy trên production?

Manual moves có thể tạo network I/O, tăng độ trễ, ảnh hưởng balancer, zone constraints và replication. Hãy để cluster tự cân bằng trừ khi có approved maintenance plan.

### 26.4. Đo lại

~~~javascript
d.events_range.getShardDistribution();

sh.balancerCollectionStatus(
  "shard_lab.events_range"
);
~~~

So với snapshot T1 trước split/move.

## 27. Truy vấn range: mongos target shards nào?

Sau khi dữ liệu đã được chia theo `sequence=10000`:

~~~javascript
d.events_range.find({
  sequence: { $gte: 5000, $lt: 6000 }
}).explain("executionStats");
~~~

Query có shard key range nằm hoàn toàn trong một chunk/range (nếu metadata không đổi) có thể target **một shard**.

Thử query vượt ranh giới:

~~~javascript
d.events_range.find({
  sequence: { $gte: 9000, $lt: 11000 }
}).explain("executionStats");
~~~

Có thể target **hai shards** nếu ranges được chia như dự kiến.

### 27.1. Hashed vs range targeting

| Query shape | Hashed `eventId` | Ranged `sequence` |
|---|---|---|
| Equality eventId | Thường targeted | Scatter nếu không có shard key |
| Equality sequence | Scatter nếu không shard key | Targeted |
| Range sequence | Scatter | Có thể target subset |
| Range eventId | Không tối ưu hash-range routing | Scatter nếu không shard key |
| All tenant events | Scatter khi tenantId không shard key | Scatter khi tenantId không shard key |

### 27.2. Explain sau khi warmup

Chạy explain khi metadata đã ổn định, sau đó đo query latency riêng bằng cùng workload. Explain có instrumentation overhead nên không xem thời gian trong explain là latency benchmark tương đương của API.

### 27.3. Đừng hardcode plan tree path

MongoDB explain format và stage names có thể khác giữa classic engine, SBE và query routers. Đọc winningPlan, executionStages, shard execution sections theo version; không viết parser chỉ đúng một sample output.

## 28. Đo scatter-gather thay vì chỉ data balance

Một collection phân bố hoàn hảo 50/50 vẫn có thể yêu cầu mọi truy vấn đến cả hai shards:

~~~text
Client query has tenantId only
             |
             v
          mongos
           /   \
          v     v
       shard A shard B
          \     /
           merge
~~~

Nếu workload có 95% queries theo `tenantId`, shard key là `eventId hashed` có thể phân phối inserts tốt nhưng gây fan-out đọc.

### 28.1. Đặt workload queries thực

Thu sample:

~~~text
70% find events by tenantId + time window
20% find by eventId
10% aggregate by eventType/time
~~~

Dùng sample này để đánh giá shard key. Không chọn chỉ bằng một biểu đồ documents per shard.

### 28.2. Phân loại target count

- **Single-shard query**: mongos định tuyến đến một shard.
- **Multi-shard targeted**: vài shards có ranges liên quan.
- **Scatter-gather**: nhiều/tất cả shards phải tham gia.

### 28.3. Query index vẫn quan trọng

Ngay cả targeted single-shard query vẫn chậm nếu index không hỗ trợ filter/sort; sharding không thay thế indexing.

## 29. Dùng analyzeShardKey khi phiên bản hỗ trợ

MongoDB 7.0+ có `analyzeShardKey` để đánh giá đặc điểm shard key và (khi có query sampling) read/write distribution.

Ví dụ trên collection đã có index:

~~~javascript
d.events_range.analyzeShardKey(
  { sequence: 1 },
  {
    keyCharacteristics: true,
    readWriteDistribution: false
  }
);
~~~

Kết quả có thể bao gồm:

- Tổng số documents và số được sample.
- Cardinality/distinct values.
- Most common values/frequency.
- Monotonicity.
- Unique-ness signal theo đặc tính key.

### 29.1. Query sampling để có read/write distribution

Nếu chưa cấu hình `configureQueryAnalyzer` và thu mẫu workload, các metrics read/write distribution có thể trả 0. **Không** diễn giải 0 là “không có scatter-gather”.

### 29.2. Không chạy trực tiếp trên shards

Trong sharded cluster, `analyzeShardKey` phải chạy qua `mongos`, không phải direct connection tới shard replica set.

### 29.3. Đánh giá cardinality

Nếu shard key chỉ có hai giá trị `status={"NEW","DONE"}`, số distinct keys quá ít để phân phối mịn; có nguy cơ jumbo/ranges không chia được.

### 29.4. Đánh giá frequency

Key có một giá trị chiếm 90% records có thể tạo hot key cho dù total distinct values lớn.

### 29.5. Đánh giá monotonicity

Sequence và timestamps tăng đều có nguy cơ append hotspot với ranged shard keys.

## 30. Thử nghiệm shard key cardinality thấp

Tạo dataset **mô tả**:

~~~javascript
{
  tenantId: "tenant-A",
  status: "NEW",
  payload: "..."
}
~~~

Nếu shard key là `{ status:1 }`, chỉ vài key values có nghĩa cluster không thể phân chia dữ liệu vô hạn theo status. MongoDB chunk ranges không thể chia một giá trị shard key đơn lẻ thành hai ranges khác nhau trên cùng collection.

### 30.1. Từ lệch dữ liệu đến jumbo

Nếu rất nhiều documents có cùng shard key value và range quá lớn, hệ thống có thể gặp jumbo/chunk cannot split hoặc mất cân bằng.

### 30.2. Cách cải thiện

- Tăng cardinality bằng compound key có field phân biệt.
- Cân nhắc hashed key phù hợp workload.
- Phân tách hot tenant/entities theo model hoặc zone.
- Đánh giá `refineCollectionShardKey`/`reshardCollection` với migration plan.

### 30.3. Không tự thay shard key trên production

Resharding có chi phí, yêu cầu dung lượng và có rủi ro vận hành. Đây là change cần benchmark, backup, FCV/version compatibility và rollout controls.

## 31. Điều gì xảy ra với dữ liệu orphan sau migration?

Khi move range:

~~~text
Source shard:
  owns range R
     |
     | copy to destination
     v
Destination shard:
  receives range R
     |
  ownership metadata switches
     |
Source:
  old copies become orphaned
  range deleter eventually removes them
~~~

### 31.1. Đo owned, không cộng orphan

`sh.getShardedDataDistribution()` phân biệt `numOwnedDocuments` và `numOrphanedDocs`. Nếu cộng cả hai, sẽ đếm lặp logical data sau migration.

### 31.2. Orphans có thể tạm thời còn

Range deletion chạy bất đồng bộ. Khi thấy bytes trên source vẫn cao, không vội kết luận migration fail nếu metadata ownership đã đổi.

### 31.3. Không tự xóa dữ liệu trực tiếp trên shard

Không kết nối vào shard để `deleteMany` những documents “trông giống duplicate”. Điều đó có thể phá cluster. Dùng cơ chế range cleanup và diagnostics được MongoDB hỗ trợ.

## 32. Cân bằng phân bố không đồng nghĩa cân bằng đĩa

Một shard lưu 10.000 documents rất lớn, shard kia lưu 10.000 documents nhỏ:

~~~text
Shard A: 10.000 docs, 80 MB logical
Shard B: 10.000 docs, 20 MB logical
~~~

Documents 50/50, bytes 80/20. Hãy đo cả hai.

### 32.1. WiredTiger compression

`ownedSizeBytes` báo kích thước **uncompressed**. Disk usage có thể thấp hơn vì compression, hoặc cao hơn do indexes, oplog, metadata và fragmentation.

### 32.2. Cache và working set

Shard có data nhỏ hơn vẫn có CPU/IO cao hơn nếu query traffic tập trung. Monitoring hiệu năng theo shard là bước tiếp theo, không chỉ data size.

### 32.3. Thời điểm đo

Tránh so disk bytes ở lúc source shard chưa dọn orphans với logical owned data của destination, vì đó là hai đại lượng khác nhau.

## 33. Đo latency nhưng không biến lab thành benchmark production

Một kịch bản latency có thể gồm:

1. Warmup vài lần cho collection/index cache.
2. Chạy điểm lookup với eventId trên events_hash.
3. Chạy point/range lookup với sequence trên events_range.
4. Chạy tenantId-only query trên cả hai.
5. Ghi p50/p95/p99 trên cùng client, cùng số requests.
6. So số shards targeted và documents examined.

### 33.1. Đừng dùng chỉ một lần chạy

Lệnh 1 có thể load cold pages; lệnh 2 hưởng cache. Chạy nhiều iterations, randomize order và phân biệt cold/warm cache khi báo cáo.

### 33.2. Đo từ client/driver

Dùng driver command monitoring và latency ứng dụng. `explain("executionStats")` phục vụ plan analysis, không thay benchmark end-to-end.

### 33.3. Cùng laptop có bias

Bốn MongoDB processes chia CPU/RAM/disk. Nếu hashed insert chậm hơn range trong lab, có thể do background migrations, resource contention hoặc index overhead, không tự chứng minh hashed shard key kém trên production.

### 33.4. Tổng throughput và tail latency

Một benchmark chỉ ghi avg latency che tail latency khi balancer migration. Nên báo p95/p99 và error rates.

## 34. Mẫu đo throughput khi ingest

Trong `mongosh`, có thể ghi elapsed time cho một batch nhỏ:

~~~javascript
(() => {
  const dbLab = db.getSiblingDB("shard_lab");
  const coll = dbLab.getCollection("events_hash");
  const marker = "throughput-lab-" + Date.now();
  const docs = [];

  for (let i = 0; i < 1000; i++) {
    docs.push({
      _id: marker + "-" + i,
      eventId: marker + "-" + i,
      tenantId: "benchmark",
      sequence: i,
      createdAt: new Date(),
      payload: "y".repeat(128)
    });
  }

  const startMs = Date.now();
  const result = coll.insertMany(docs);
  const elapsedMs = Date.now() - startMs;

  printjson({
    acknowledgedCount: result.insertedIds
      ? Object.keys(result.insertedIds).length
      : null,
    elapsedMs,
    approximateOpsPerSecond:
      elapsedMs > 0 ? 1000 * docs.length / elapsedMs : null
  });
})();
~~~

### 34.1. Đây là micro-experiment

Không dùng số `opsPerSecond` này làm năng lực production. Nó chỉ giúp quan sát cùng host dưới điều kiện hiện tại.

### 34.2. Seed data và measured data

Batch này **thay đổi tập documents** của events_hash. Nếu cần so distributions trên hai collections một cách công bằng, hãy tách riêng benchmark collection hoặc thực hiện sau khi lưu baseline, rồi ghi chú thay đổi N.

### 34.3. Write concern và durability

`insertMany` mặc định dùng write concern từ URI/client. Nếu so hai workloads có write concern khác nhau, số liệu không tương đương. Trong production, không hạ durability chỉ để tăng điểm benchmark.

## 35. Chạy Java Sync Driver qua mongos

Ứng dụng Java chỉ nên kết nối tới **mongos** (ở host lab `127.0.0.1:27027`):

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class ShardingLabClient {

    public static void main(String[] args) {
        String uri = System.getenv().getOrDefault(
            "MONGO_SHARDING_LAB_URI",
            "mongodb://127.0.0.1:27027"
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("shard_lab");
            MongoCollection<Document> events =
                database.getCollection("events_hash");

            Document event = events.find(
                new Document("eventId", "evt-00000100")
            ).first();

            System.out.println("Found=" + (event != null));
        }
    }
}
~~~

### 35.1. Không kết nối trực tiếp tới shard để đọc app data

Router sử dụng shard key và metadata để phân phối queries. Một direct-shard client bỏ qua mongos routing có thể cho kết quả thiếu/sai hoặc bị server từ chối operations.

### 35.2. MongoClient nên singleton

Java Driver `MongoClient` tái sử dụng connection pools. Không tạo client mới cho mỗi query trong benchmark vì overhead DNS/TCP/TLS có thể làm méo số đo.

### 35.3. Với Spring Boot

MongoDB URI configuration thay đổi theo version:

- Spring Boot 3.5: `spring.data.mongodb.uri`.
- Spring Boot 4.x: `spring.mongodb.uri`.

Trong môi trường lab, URI trỏ mongos; production cần TLS/auth/secret manager và topology đúng.

## 36. Java benchmark: phép đo có giới hạn

Một phép đo đơn giản:

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class QuerySample {

    public static List<Long> sampleMillis(
            MongoCollection<Document> collection,
            List<String> eventIds) {

        List<Long> samples = new ArrayList<>();

        for (String id : eventIds) {
            long started = System.nanoTime();

            collection.find(new Document("eventId", id)).first();

            long elapsed = System.nanoTime() - started;
            samples.add(elapsed);
        }

        Collections.sort(samples);
        return samples;
    }
}
~~~

### 36.1. SampleMillis chỉ là tên minh họa chưa convert

Method trả nanoseconds vì lưu `elapsed` chưa chia 1.000.000; trong code production đặt tên `sampleNanos` hoặc chuyển sang milliseconds rõ ràng. Đây là ví dụ cảnh báo lỗi đơn vị đo rất thường gặp.

### 36.2. Warmup và P95

Trước khi đo, gửi warmup queries. Sau đó dùng danh sách đã sort để lấy median/p95 với index phù hợp. Tách latency do network, server selection và mongos/shard query execution khi có tracing.

### 36.3. Không lấy một sample làm kết luận

Cần nhiều repeats, cùng cardinality, cùng index, cùng concurrency, cùng Docker resources, và log số targeted shards.

## 37. Shard key design: trade-offs phải ghi vào kết quả

| Tiêu chí | Hashed eventId | Range sequence |
|---|---|---|
| Distribution khi key tăng tuần tự | Thường phân tán tốt | Có nguy cơ hot upper range |
| Equality lookup theo key | Targeted | Targeted |
| Range query theo shard key gốc | Kém locality theo hash | Có thể route subset |
| Query theo tenantId khác shard key | Scatter | Scatter |
| Global uniqueness của hashed field | Không unique hashed index | Unique constraints theo rules |
| Chunk initial distribution trên empty MongoDB 8.0 | Có thể phân bố sớm | Có thể bắt đầu một chunk |
| Manual moveChunk helper | Không dùng theo `find` hashed key | Có thể dùng trong lab |
| Chuyển shard key về sau | Resharding cần kế hoạch | Resharding cần kế hoạch |

### 37.1. Không áp một key cho mọi use case

Nếu access pattern chính là `tenantId+aggregateId+time`, một compound key được thiết kế cho workload có thể tốt hơn cả hai single-field keys của bài.

### 37.2. Hash không sửa low-cardinality business grouping tự động

Nếu nhiều events cùng một tenantId và shard key là `{tenantId:"hashed"}`, mọi events của tenant đó vẫn có cùng hash và có thể dồn vào một shard. Hashing **không chia một key value thành nhiều shards**.

## 38. Khi nào cần zones?

Zone sharding giúp gắn một số shard-key ranges với một tập shards, ví dụ:

- Region/data residency.
- Tier of service.
- Tenant group isolation.
- Dữ liệu nóng/lạnh theo policy.

### 38.1. Zone không đồng nghĩa đều về số docs

Nếu một zone chỉ có một shard hoặc một tenant cực lớn, phân bố có thể lệch dù balancer tuân thủ zone constraints hoàn toàn.

### 38.2. Không tự thêm zone vào lab cơ bản

Nếu thêm zones, cần thay expected distribution, bởi balancer lúc ấy phải vừa cân dữ liệu vừa tuân thủ placement constraints. Nên làm thí nghiệm riêng có baseline độc lập.

### 38.3. Legal/regulatory limits

Không dùng việc di chuyển chunk giữa các vùng để “thử” nếu dữ liệu có residency constraints. Lab dùng dữ liệu giả và Docker cùng host.

## 39. Resharding và shardAndDistributeCollection

Từ MongoDB 8.0, `sh.shardAndDistributeCollection()` có thể shard và phân phối lại dữ liệu nhanh hơn trong những điều kiện/resource phù hợp, thay vì chờ balancer từng migration. Nó kết hợp logic sharding và resharding về cùng key.

### 39.1. Đây không phải bước bắt buộc của lab

Bài dùng `sh.shardCollection()` để quan sát rõ initial distribution và balancer. Thay sang shardAndDistributeCollection sẽ làm experiment khác mục tiêu.

### 39.2. Thay shard key đã có

`reshardCollection`/`refineCollectionShardKey` có yêu cầu version, index, namespace, dung lượng, write availability và constraints. Không tự thực hiện chỉ vì graph phân bố đang lệch.

### 39.3. Khi nào cân nhắc

- Workload thật cho thấy hot shard bền vững.
- Chunks không thể chia vì low-cardinality.
- Query targeting kém.
- Data placement không đạt SLO.
- Có đủ free disk/network/CPU để reshard.

## 40. Những bẫy sharding khác nhau theo MongoDB version

### 40.1. MongoDB 5.0+ config.chunks

Dùng `uuid` thay vì giả định `ns` luôn tồn tại trong chunk metadata.

### 40.2. MongoDB 6.0+

`sh.enableSharding()` không còn là bước bắt buộc để shard một collection.

### 40.3. MongoDB 6.0.3+

`sh.getShardedDataDistribution()` có sẵn để lấy owned/orphan counts.

### 40.4. MongoDB 7.0+

`analyzeShardKey` giúp đánh giá key characteristics. Read/write distribution cần sampling setup.

### 40.5. MongoDB 7.2+ / 8.0

Default initial chunk count của empty hashed collection đã thay đổi qua releases; MongoDB 8.0 tạo một chunk ban đầu trên mỗi shard trong trường hợp đơn giản.

### 40.6. MongoDB 8.0+

Có `sh.shardAndDistributeCollection()` và hạn chế với directShardOperations. Không mang lệnh admin từ hướng dẫn MongoDB 4.x vào 8.x mà không kiểm tra docs.

### 40.7. MongoDB 9.x

Một số API/commands và sharded cluster deployment styles tiếp tục phát triển. Nếu đổi version, cần ghi phiên bản thực tế và xác minh helper outputs trước khi so kết quả với bài.

## 41. Phân biệt failed test với kết luận về shard key

Ví dụ:

~~~text
Experiment: events_hash 100% data on rsShardA
~~~

Trước khi kết luận “hashed sharding tệ”, hãy kiểm tra:

- `sh.status()` có đúng namespace sharded?
- `db.events_hash.getIndexes()` có hashed index?
- `sh.getShardedDataDistribution()` được gọi từ mongos?
- Dataset có thật sự chứa nhiều distinct eventId?
- Hai shards đều có trong `listShards` và reachable?
- Có chunks owned by both shards?
- Balancer/migrations có lỗi không?
- Có journal/disk full/network issue?
- Có query kết quả nhầm namespace?
- Có manual zones hoặc placement constraints?
- Có initial distribution pending?

### 41.1. Setup failure

Nếu config server chưa initialized hoặc router không reachable, đó là lỗi infrastructure setup, không chứng minh sharding strategy thất bại.

### 41.2. Measurement error

Nếu count qua direct shard tính cả orphans sau migration, đó là measurement problem. Dùng owned stats.

### 41.3. Statistical variance

Một test 20 documents không cho bằng chứng tốt về sự cân bằng dài hạn. Tăng sample size và chạy repeats có kiểm soát.

## 42. Runbook: tất cả dữ liệu ở một shard

1. Xác nhận collection sharded và key thực tế trong `sh.status()`.
2. Xác nhận cluster có hai shards healthy.
3. Kiểm tra key cardinality và frequency.
4. Kiểm tra chunk count/ownership.
5. Kiểm tra dữ liệu mới hay có từ trước lúc shard.
6. Xem balancer state và collection balance status.
7. Xem chunks quá lớn/jumbo hoặc zone constraints.
8. Chờ background migrations nếu đang diễn ra.
9. Nếu dataset nhỏ, ghi rõ “không đủ dữ liệu để tự split”.
10. Trong lab, thử manual split/move range; trên production dùng change request.
11. Remeasure owned docs/bytes và query targeting.
12. Đánh giá có cần reshard/refine key hay không.

### 42.1. Không giải quyết bằng thay primary

Primary election trong shard replica set không phân bố lại chunks sang shard khác. Nó chỉ đổi node phục vụ writes trong **cùng shard**.

### 42.2. Không giải quyết bằng tăng pool vô điều kiện

Tăng Java MongoClient pool có thể tăng concurrency nhưng không thay shard key placement; hotspot vẫn còn.

## 43. Runbook: balancer không di chuyển chunks

Nguyên nhân có thể:

- Không đủ imbalance theo chính sách.
- Data/ranges chưa cần move.
- Balancer disabled hoặc maintenance window.
- Collection có jumbo/indivisible range.
- Target shard disk/resource constraints.
- Chunks bị zone placement restrictions.
- Migration đang chờ hoặc thất bại.
- Config server/shard health issues.

### 43.1. Kiểm tra

~~~javascript
sh.getBalancerState();
sh.isBalancerRunning();

sh.balancerCollectionStatus(
  "shard_lab.events_range"
);

sh.status();
~~~

### 43.2. Không dùng sh.startBalancer như phản xạ

Trước tiên xác định balancer có disabled thật không. Bật một process không cần chạy sẽ không tự tạo chunks hoặc sửa low-cardinality key.

### 43.3. Lưu error details

Ghi last balancer error, failed rounds, namespace, ranges, server versions và thời điểm. Không sửa thủ công config database.

## 44. Runbook: query vẫn chậm sau khi data cân bằng

1. Đo p95/p99 và throughput theo operation.
2. Dùng `explain("executionStats")` xác định targeted shards.
3. Kiểm tra compound index trên mỗi shard.
4. Kiểm tra scatter-gather và merging costs.
5. Kiểm tra hot tenant/eventType distribution.
6. Đo shard CPU, cache, disk I/O, connections.
7. Kiểm tra balancer migration đang diễn ra.
8. Kiểm tra sort/aggregation spilling.
9. Đánh giá query shape và shard key.
10. Chỉ sau đó cân nhắc thêm capacity hoặc resharding.

### 44.1. Phân bố dữ liệu tốt không chứng minh SLO tốt

Tải đọc có thể lệch hoàn toàn so với số docs. Tối ưu target queries và indexes trước khi mở rộng.

## 45. Bảng ghi kết quả thí nghiệm

Điền số **đo thực tế**, không điền ước đoán.

| Mốc | Collection | Shard | Owned docs | Owned bytes | Chunks | Orphans | Balancer state |
|---|---|---|---:|---:|---:|---:|---|
| T0 | events_hash | rsShardA | ... | ... | ... | ... | ... |
| T0 | events_hash | rsShardB | ... | ... | ... | ... | ... |
| T1 | events_hash | rsShardA | ... | ... | ... | ... | ... |
| T1 | events_hash | rsShardB | ... | ... | ... | ... | ... |
| T1 | events_range | rsShardA | ... | ... | ... | ... | ... |
| T1 | events_range | rsShardB | ... | ... | ... | ... | ... |
| T4 | events_range | rsShardA | ... | ... | ... | ... | ... |
| T4 | events_range | rsShardB | ... | ... | ... | ... | ... |

### 45.1. Ghi metadata cùng bảng

~~~yaml
experimentId: shard-distribution-lab
environment: isolated-docker-compose
mongoVersion: "8.0.x"
mongoshVersion: "record-actual-version"
routerEndpoint: "127.0.0.1:27027"
shards: 2
configServerMembers: 1
membersPerShard: 1
workload:
  documentsPerCollection: 20000
  payloadBytesApprox: 1024
measurement:
  source: sh.getShardedDataDistribution
  includesOrphans: false
notes: "Numbers are observed results, not predetermined"
~~~

Đây là một mẫu báo cáo, không phải file MongoDB config và không thay thế actual measurement.

### 45.2. Báo cáo cả targeted queries

| Query | Collection | Expected routing | Observed shards | p95 | Docs examined |
|---|---|---|---|---|---|
| eventId equality | events_hash | thường 1 shard | ... | ... | ... |
| sequence equality | events_range | thường 1 shard | ... | ... | ... |
| sequence range vượt split | events_range | có thể 2 shards | ... | ... | ... |
| tenantId only | cả hai | scatter | ... | ... | ... |

## 46. Cách đánh giá kết quả cuối

Đánh giá theo nhiều tiêu chí:

- **Correctness:** Tổng logical count đúng, không có data loss/duplication.
- **Ownership:** Owned docs và bytes đã phân phối theo thiết kế.
- **Balance:** Skew ratio và orphan/migration state có thể giải thích.
- **Routing:** Query targeted dự kiến, không scatter ngoài ý muốn.
- **Performance:** p95/p99 và throughput dưới cùng workload.
- **Operations:** Balancer/error counters/CPU/IO ổn định.
- **Repeatability:** Có version, scripts, N, elapsed time và clean slate policy.
- **Security:** Cluster lab không expose ngoài host, không dùng data thật.

### 46.1. PASS không đồng nghĩa phải 50/50

Nếu workload query chủ yếu vào một tenant bị giới hạn zone, data distribution 60/40 có thể hợp lý. Thí nghiệm phải có acceptance criteria trước khi chạy.

### 46.2. Phải giải thích các sai khác

Nếu T1 hash skew nhiều nhưng T3 tốt hơn, có thể do initial chunk migration hoặc balancer. Ghi evidence thay vì chỉ số cuối.

### 46.3. Không lấy lab làm SLA production

Laptop single-host không phản ánh multi-AZ network, replication factor, high concurrency, backups, maintenance hoặc cloud storage behavior.

## 47. An toàn khi làm thí nghiệm trên staging

Nếu thay Docker lab bằng staging cluster thật:

- Chỉ dùng account/staging dataset được duyệt.
- Không dùng live customer PII.
- Giới hạn throughput, query windows và thời gian.
- Có DBA/owner và maintenance boundaries.
- Không chạy direct-shard writes.
- Không sửa config metadata.
- Không chạy manual moveChunk/reshard trừ khi có change approved.
- Có rollback/recovery plan.
- Ghi audit và resource metrics.
- Đảm bảo tài nguyên test không ảnh hưởng môi trường khác.

### 47.1. Tránh “test” quyền bằng root production

Sharding admin commands cần privileges; môi trường lab có thể dùng internal demo admin. Với staging/production, cấp quyền tối thiểu, không lấy root/password thật ra terminal không được bảo vệ.

### 47.2. Query analyzer có overhead

Nếu kích hoạt query sampling trên staging, đặt sampleRate và thời hạn được phê duyệt, ghi overhead. Không giả định công cụ phân tích hoàn toàn miễn phí.

## 48. Cleanup an toàn sau lab

**Trước khi xóa bất cứ thứ gì**, xác nhận terminal đang ở đúng thư mục chứa `compose.yaml` của lab và project name mong muốn.

Xem các containers:

~~~bash
docker compose -p mongo-sharding-lab ps
~~~

Nếu chỉ muốn dừng:

~~~bash
docker compose -p mongo-sharding-lab stop
~~~

Nếu muốn dừng/xóa containers nhưng giữ named volumes:

~~~bash
docker compose -p mongo-sharding-lab down
~~~

Nếu muốn xóa **toàn bộ dữ liệu của lab** sau khi đã xác nhận đúng project:

~~~bash
docker compose -p mongo-sharding-lab down -v --remove-orphans
~~~

### 48.1. down -v là thao tác phá dữ liệu

Lệnh cuối xóa named volumes thuộc Compose project. Không chạy nếu project chứa dữ liệu cần giữ hoặc bạn chưa xác minh tên project.

### 48.2. Không chạy lệnh dọn toàn Docker

Không dùng `docker system prune --all --volumes` như một bước của lab này. Nó có thể xóa dữ liệu/images/volumes của các dự án khác.

### 48.3. Đừng dropDatabase từ kết nối sai

Nếu cleanup bằng `db.dropDatabase()`, trước tiên phải xác minh URI đang trỏ `127.0.0.1:27027` và database `shard_lab`. Compose cleanup cô lập thường an toàn hơn cho bài demo.

## 49. Câu hỏi tự luyện

### Bài 1 — Vai trò thành phần

Giải thích `mongos`, config server replica set và shard replica set.

### Bài 2 — Replication vs sharding

Vì sao thêm secondary vào replica set không tự phân chia dữ liệu?

### Bài 3 — Isolation

Vì sao chỉ map `127.0.0.1:27027`, không publish shard ports?

### Bài 4 — Hostnames

Vì sao `rs.initiate` dùng `cfg:27019` thay cho container IP tạm?

### Bài 5 — Quorum

Một member per replica set có thử được bầu primary mới khi mất node không?

### Bài 6 — mongos connection

Điều gì có thể sai nếu Java app kết nối trực tiếp `shard-a` để đọc mọi dữ liệu?

### Bài 7 — enableSharding

Từ MongoDB 6.0, có cần gọi `sh.enableSharding()` trước `sh.shardCollection()` không?

### Bài 8 — Shard key

Đề xuất hai shard keys cho event stream và giải thích hashed/ranged trade-offs.

### Bài 9 — Initial chunks

Vì sao empty hashed collection và empty ranged collection có initial chunk distribution khác nhau?

### Bài 10 — Dataset

Tạo 20.000 documents với payload 1 KiB và stable IDs; vì sao dùng batch?

### Bài 11 — Logical count

Làm sao kiểm tra total documents qua mongos?

### Bài 12 — Owned vs orphan

Vì sao cần dùng `numOwnedDocuments` thay vì cộng raw records đọc trực tiếp các shards?

### Bài 13 — getShardDistribution

Đọc docs, data, chunks và per-shard percentages từ helper.

### Bài 14 — getShardedDataDistribution

Lấy `ownedSizeBytes`/`numOrphanedDocs` cho một namespace.

### Bài 15 — Data skew

Với 12.000/8.000 docs, tính per-shard percentages và gap_pp.

### Bài 16 — Byte skew

Hai shards có 10.000 docs mỗi bên nhưng bytes 80MB/20MB. Có cân bằng theo data size không?

### Bài 17 — Chunk count

Tại sao số chunks bằng nhau không chứng minh documents cân bằng?

### Bài 18 — Config metadata

Viết query `config.collections` và `config.chunks` theo UUID.

### Bài 19 — Balancer

Phân biệt `sh.getBalancerState()` với balancer actively migrating.

### Bài 20 — Collection balance status

`sh.balancerCollectionStatus` giúp trả lời câu hỏi gì?

### Bài 21 — Ranged split

Với 20.000 events sequence 0..19999, chia tại 10000 tạo ranges nào?

### Bài 22 — Split vs move

Sau `sh.splitAt`, đã chắc dữ liệu xuất hiện trên cả hai shards chưa?

### Bài 23 — Manual migration

Giải thích `sh.moveChunk(namespace,query,destination)`; vì sao chỉ chạy ở lab?

### Bài 24 — Hashed move

Vì sao `sh.moveChunk()` helper không nên dùng theo cách tương tự với hashed shard key?

### Bài 25 — AutoMerger

Một split vừa tạo biến mất khỏi metadata. Nêu lý do hệ thống tự merge có thể là một khả năng.

### Bài 26 — Query targeting

So equality eventId trên hashed collection với equality sequence trên ranged collection.

### Bài 27 — Scatter-gather

Vì sao query theo tenantId có thể chạm cả hai shards trong hai schema của bài?

### Bài 28 — Explain

Nêu các fields cần đọc để biết shards targeted và số documents examined.

### Bài 29 — Cardinality

Nếu shard key chỉ có hai giá trị status, nguy cơ là gì?

### Bài 30 — Frequency

Nếu tenantId=tenant-A chiếm 90% events, hashed tenantId có phân tách tenant-A thành nhiều shards không?

### Bài 31 — Monotonicity

Tại sao sequence tăng dần tạo write hotspot với range sharding?

### Bài 32 — analyzeShardKey

Từ MongoDB 7.0, công cụ nào giúp xem cardinality/monotonicity?

### Bài 33 — Query sampling

Vì sao read/write distribution có thể trả 0 khi chưa có sampled queries?

### Bài 34 — Orphans

Sau migration, tại sao disk bytes source shard vẫn cao dù ownership đã chuyển?

### Bài 35 — Low-volume lab

Vì sao 20MB data chưa chắc tạo automatic split/migration?

### Bài 36 — Performance

Để so hai shard keys, phải giữ những variables nào cố định?

### Bài 37 — p95

Vì sao avg latency có thể che những lần query rất chậm do migration?

### Bài 38 — Unique index

Khi sharding, unique index cần tuân thủ quy tắc shard-key prefix như thế nào?

### Bài 39 — _id uniqueness

Vì sao `_id` không nằm trong shard key có thể không được enforce globally?

### Bài 40 — Zones

Khi zone constraints chỉ cho một shard nhận dữ liệu region A, liệu 50/50 có còn là tiêu chí hợp lý?

### Bài 41 — Resharding

Khác biệt giữa refine shard key và reshardCollection là gì?

### Bài 42 — MongoDB 8.0

`sh.shardAndDistributeCollection` có mục đích gì và vì sao bài này không dùng mặc định?

### Bài 43 — Same-host bias

Vì sao benchmark trên laptop bốn containers không dự đoán chính xác hiệu năng multi-node production?

### Bài 44 — Cleanup

Khác nhau giữa `docker compose down` và `down -v`. Lệnh nào xóa dữ liệu lab?

### Bài 45 — Runbook

Nếu 100% data ở shard A, hãy ghi ít nhất tám bước điều tra trước khi nghĩ đến resharding.

### Bài 46 — Báo cáo kết quả

Viết bảng T0/T1/T3/T4 cho hashed/ranged collections với owned docs, bytes, chunks, orphans, balancer state và query targeting.

### Bài 47 — Thiết kế production

Giả sử ứng dụng đa tenant ghi 50 triệu events/tháng. Chọn shard key dựa trên:
- Query theo tenant+aggregate.
- Query theo eventId.
- Batch report time range.
- Hot tenants và uneven traffic.
- Global uniqueness requirements.
- Region data residency.
- Retention, indexes, backups, reshard migration.
- SLO và observability.

### Bài 48 — Kiểm chứng cuối

Một thí nghiệm có hashed collection 52/48 docs nhưng query p95 tăng do tenantId scatter. Kết luận “hashed tốt hơn ranged” có hợp lý không? Nêu các số liệu còn thiếu.

## 50. Checklist thực hành tổng hợp

### Chuẩn bị

- [ ] Project Docker Compose riêng, không trùng deployment khác.
- [ ] Port router chỉ bind localhost.
- [ ] Không có dữ liệu/credentials thật.
- [ ] MongoDB version/image được pin.
- [ ] Config server và shards healthy.
- [ ] Router trả `msg:"isdbgrid"`.
- [ ] `listShards` có hai shards.
- [ ] Không có direct-shard application traffic.

### Dữ liệu và schema

- [ ] Hai collections rỗng trước khi shard.
- [ ] Index hỗ trợ shard keys.
- [ ] Hashed/ranged key được ghi rõ.
- [ ] Workload có stable IDs, high cardinality.
- [ ] Tổng `countDocuments` khớp expected N.
- [ ] Không nhầm global uniqueness với local-per-shard `_id`.
- [ ] Đã ghi kích thước payload, event fields, indexes.

### Measurement

- [ ] T0/T1/T2/T3 có timestamps UTC.
- [ ] Đo owned documents.
- [ ] Đo owned uncompressed bytes.
- [ ] Đo chunk count/ownership.
- [ ] Đo orphan documents sau migrations.
- [ ] Đo balancer enabled/active/collection status.
- [ ] Tính per-shard percentages và skew.
- [ ] Xem `explain` cho targeted/scatter queries.
- [ ] Đo query p95/p99 theo workload đại diện.
- [ ] Không so sánh data bytes với disk bytes thiếu giải thích.

### Kết luận và cleanup

- [ ] Không suy luận performance từ một lần đo.
- [ ] Có diễn giải nguyên nhân skew.
- [ ] Có phân biệt initial state và settled state.
- [ ] Có nhận xét về cardinality/monotonicity/hot keys.
- [ ] Có mô tả trade-off index, queries, writes.
- [ ] Không can thiệp balancer/migration trên production.
- [ ] Chỉ cleanup đúng Compose project sau khi xác nhận.
- [ ] Lưu kết quả đo/tracing/logs đã redacted.

## 51. Tổng kết

Thử nghiệm sharding có giá trị khi biến một kiến trúc phức tạp thành **kết quả đo có thể giải thích và tái lập**:

1. **Dựng đúng topology:** `mongos`, CSRS và shard replica sets ở một môi trường tách biệt. Một-member replica sets đủ cho data-distribution lab, không đủ cho failover/HA test.
2. **Chọn key để kiểm tra giả thuyết:** hashed high-cardinality key thường giúp trải writes; ranged monotonic key có thể tạo initial concentration và hot upper range.
3. **Đo đúng đại lượng:** owned documents/bytes, chunks, orphan docs và migration state là các số khác nhau. Equal chunks không đồng nghĩa equal data hoặc equal load.
4. **So tại nhiều thời điểm:** Sharding và balancing có thể diễn ra bất đồng bộ. Kết quả ngay sau insert khác settled state.
5. **Kiểm chứng routing:** Point lookup theo full shard key có thể target một shard; query không chứa shard key có thể scatter-gather dù dữ liệu phân bố đẹp.
6. **Giữ tính an toàn:** Không có direct-shard CRUD, không sửa metadata, không manual moves/reshard trên production cho thí nghiệm, không expose insecure lab qua public network.
7. **Báo cáo có kỷ luật:** Ghi version, workload, shard states, owned counts, chunk counts, skew, targeted shards và SLO. Không thay số đo bằng kỳ vọng “50/50”.

**Điều cần nhớ:** *Sharding là phân vùng dữ liệu theo shard key, không phải máy tự chia mọi thứ đều nhau. Đo phân bố chỉ là bước đầu; query routing, hotspot và workload mới quyết định thiết kế có thực sự hiệu quả.*

## Tài liệu MongoDB chính thức

- [Deploy a Self-Managed Sharded Cluster](https://www.mongodb.com/docs/manual/tutorial/deploy-shard-cluster/)
- [Sharding Architecture](https://www.mongodb.com/docs/manual/sharding/)
- [Sharding Overview and Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/)
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/)
- [Range-based Sharding](https://www.mongodb.com/docs/manual/core/ranged-sharding/)
- [Data Partitioning with Chunks](https://www.mongodb.com/docs/manual/core/sharding-data-partitioning/)
- [sh.shardCollection()](https://www.mongodb.com/docs/manual/reference/method/sh.shardcollection/)
- [sh.getShardedDataDistribution()](https://www.mongodb.com/docs/manual/reference/method/sh.getshardeddatadistribution/)
- [db.collection.getShardDistribution()](https://www.mongodb.com/docs/manual/reference/method/db.collection.getsharddistribution/)
- [sh.status()](https://www.mongodb.com/docs/manual/reference/method/sh.status/)
- [sh.balancerCollectionStatus()](https://www.mongodb.com/docs/manual/reference/method/sh.balancercollectionstatus/)
- [Manage Sharded Cluster Balancer](https://www.mongodb.com/docs/manual/tutorial/manage-sharded-cluster-balancer/)
- [sh.splitAt()](https://www.mongodb.com/docs/manual/reference/method/sh.splitat/)
- [sh.moveChunk()](https://www.mongodb.com/docs/manual/reference/method/sh.moveChunk/)
- [Analyze Shard Key](https://www.mongodb.com/docs/manual/reference/command/analyzeshardkey/)
- [Sharded Collection and Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [sh.shardAndDistributeCollection()](https://www.mongodb.com/docs/manual/reference/method/sh.shardanddistributecollection/)
- [MongoDB Java Sync Driver — Connect to MongoDB](https://www.mongodb.com/docs/drivers/java/sync/current/connection/)
- [Security Checklist for Self-Managed Deployments](https://www.mongodb.com/docs/manual/administration/security-checklist/)
