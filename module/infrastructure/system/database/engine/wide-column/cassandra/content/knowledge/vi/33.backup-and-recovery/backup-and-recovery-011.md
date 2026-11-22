# sstableloader, restore theo file và đối chiếu topology/phiên bản trong Apache Cassandra

> **Chương:** Sao lưu và phục hồi  
> **Phạm vi:** Phục hồi dữ liệu Apache Cassandra từ SSTable snapshot/incremental backup bằng `sstableloader` hoặc nạp SSTable cục bộ bằng `nodetool import`/`refresh`; kiểm tương thích phiên bản, schema, table ID, partitioner, token ownership, datacenter và replication factor trước khi mở lưu lượng. Ví dụ tham chiếu Cassandra 4.1/5.0 và Java Driver 4.x; lệnh thay đổi dữ liệu chỉ thực hiện trong lab hoặc theo runbook production đã phê duyệt.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **SSTable backup/snapshot**, **incremental backup**, **commit log**, **anti-entropy repair**, **rebuild** và **restore**; hiểu khi nào mỗi công cụ giúp phục hồi dữ liệu.
2. Giải thích cách `sstableloader` **stream các token range** tới cluster đang hoạt động theo **replication strategy hiện tại**; phân biệt với `nodetool import`/`refresh` nạp file trực tiếp trên từng node.
3. Lập một **bảng kiểm trước restore** về phiên bản Cassandra/SSTable format, partitioner, schema và table ID, topology nguồn/đích, RF theo DC, TTL/tombstone, tính đầy đủ và checksum của backup.
4. Chuẩn bị đúng cấu trúc thư mục cho `sstableloader`, xác minh options `--nodes`, TLS/auth, streaming ports, throttling và theo dõi lỗi theo từng replica.
5. Lập runbook phục hồi **theo file trên node** mà không chép bừa SSTable vào live data directory hoặc bỏ qua kiểm token ownership.
6. Giải thích vì sao **đọc được dữ liệu sau restore** chưa đủ chứng minh mọi replica chính xác, và vì sao SSTable cũ có thể bị tombstone/timestamp mới hơn che.
7. Thực hành một restore **không phá dữ liệu gốc** bằng cách stream snapshot từ một bảng lab sang bảng cùng schema ở keyspace đích riêng.
8. Xác minh sau phục hồi bằng CQL, tracing/metrics, kiểm theo nguồn nghiệp vụ và Java Driver với consistency level phù hợp.

Trọng tâm của dịch vụ **`DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`** là kiến trúc **wide-column phân tán**: partition key → token → natural replicas; CQL/schema quyết định ý nghĩa dữ liệu; CL quyết định số phản hồi cần thiết. **Restore phải phù hợp cả ba lớp**, không chỉ có các file `*-Data.db`.

## 2. Bản đồ các phương thức phục hồi: đừng chọn nhầm công cụ

| Tình huống | Công cụ/phương án thường phù hợp | Vì sao? | Điều không giải quyết được |
|---|---|---|---|
| Có SSTable backup, muốn nạp vào cluster **khác số node/RF/DC** | **`sstableloader`** | Lấy ring đích rồi stream phần dữ liệu đến natural replicas theo placement đích | Không tự sửa dữ liệu logic sai hoặc timestamp/tombstone |
| Có SSTable backup cho **một node**, topology/table tương thích, cần bổ sung file cục bộ | **`nodetool import`** (ưu tiên trong các bản mới) | Nạp SSTable ở chính node được gọi, có kiểm tra xác thực/token theo tùy chọn | Không tự phân phối SSTable tới tất cả replica còn lại |
| Đã đặt SSTable hợp lệ trong live table directory, cần Cassandra phát hiện | **`nodetool refresh`** (legacy/deprecated trong hướng dẫn bulk loading) | Nạp các file mới được đặt, không yêu cầu restart chỉ vì refresh | Không làm token-aware streaming; sao chép live directory có rủi ro |
| Một node chết, các replica khác vẫn giữ dữ liệu tốt | **Replace/rebuild node** theo runbook topology | Stream lại range mà node mới phải sở hữu | Không biết dữ liệu bị mất trên **mọi** replica |
| Replica chỉ bỏ lỡ mutation, dữ liệu/tombstone còn trên bản khác | **Anti-entropy repair** | Đối chiếu và đồng bộ replica | Không thay backup/PITR khi dữ liệu mất khắp nơi |
| DELETE nhầm hoặc toàn bộ replica có trạng thái sai | **Restore vào môi trường cách ly, đối chiếu audit rồi khôi phục logic** | Cần nguồn sự thật độc lập, xử lý timestamp/tombstone | Chỉ chạy repair hoặc stream backup cũ không tự đảo DELETE |
| Muốn phục hồi đúng đến một giây trong quá khứ | Backup + **CDC/event log/commit-log workflow** đã thiết kế | Cần chuỗi mutation và mốc thời gian được kiểm soát | Snapshot + incremental SSTable đơn thuần **không bảo đảm PITR tùy ý** |

**Quy tắc chọn nhanh:** Khi topology khác hoặc muốn tránh tự đặt file trên từng node, thường ưu tiên `sstableloader`. Khi cần nhập **file local vào node cụ thể** và biết token ranges/schema tương thích, xem `nodetool import`. Không dùng `refresh` thay streaming chỉ vì thao tác có vẻ ngắn hơn.

### 2.1. Hai mặt phẳng của restore

~~~text
                 BẢN SAO LƯU (SSTables)
                           |
         +-----------------+------------------+
         |                                    |
    sstableloader                        import / refresh
         |                                    |
  Hỏi ring/replication                    Chọn NODE cụ thể
  của cluster đích                        nơi file được nạp
         |                                    |
  Chia token ranges và                    Kiểm file, schema,
  STREAM tới replicas                     ownership tại node
         |                                    |
         +-----------------+------------------+
                           |
                   Kiểm dữ liệu CQL
                   + replica coverage
                   + audit nghiệp vụ
~~~

Hai đường này **không tương đương**: `sstableloader` gửi dữ liệu đến cluster theo placement; `import`/`refresh` không biến một file cục bộ thành bản sao phân tán đầy đủ. Tác động của restore cũ vào bảng đang có dữ liệu còn phụ thuộc **write timestamp, TTL và tombstone**, không chỉ công cụ.

## 3. Những gì thực sự nằm trong một backup Cassandra

### 3.1. SSTable là tập file, không phải một file Data.db

Cassandra lưu dữ liệu đã flush thành **SSTable bất biến**. Một SSTable có nhiều thành phần mang cùng generation/format, chẳng hạn:

~~~text
<prefix>-Data.db               Dữ liệu partition/cell
<prefix>-Index.db              Chỉ mục thành phần (nếu format có)
<prefix>-Statistics.db         Metadata, timestamp và thống kê
<prefix>-Summary.db            Summary/index trợ giúp đọc (nếu có)
<prefix>-Filter.db             Bloom filter (nếu có)
<prefix>-CompressionInfo.db    Metadata nén (nếu được nén)
<prefix>-Digest.crc32          Checksum/digest của format tương ứng
<prefix>-TOC.txt               Danh sách thành phần SSTable
~~~

Các component **thay đổi theo SSTable format và phiên bản** (ví dụ BIG/BTI), nên không ép mọi SSTable phải có chính xác những tên trong ví dụ. Khi sao chép để restore phải bảo toàn **toàn bộ bộ thành phần hợp lệ cùng generation**, không chỉ copy `Data.db` rồi hy vọng engine tái tạo mọi phần còn lại.

### 3.2. Snapshot và incremental backup

| Loại | Tạo bằng cách nào? | Bao gồm | Không bao gồm/mất mát cần lưu ý |
|---|---|---|---|
| **Snapshot** | `nodetool snapshot` tạo hard links tới SSTables đã flush | Các SSTable ở mốc node-local; thường có `schema.cql` và `manifest.json` | Không mặc nhiên là snapshot nguyên tử toàn cluster; không bao gồm mutation chưa flush nếu `--skip-flush` |
| **Incremental backup** | Khi bật, mỗi SSTable được flush/stream có hard link trong `backups/` | Những SSTable mới sau các lần flush; hỗ trợ chuỗi backup | Không tự có đầy đủ schema DDL; muốn restore cần snapshot gốc/schema tương ứng |
| **Commit log** | Nhật ký mutation phục vụ crash recovery của node | Các mutation đã được append theo thiết lập durability | Không tự là bản backup dài hạn/PITR lịch sử có tổ chức |
| **CDC/event audit** | Cấu hình pipeline riêng | Có thể làm nguồn replay mutation nếu retention và completeness đủ | Không mặc nhiên chứa mọi bảng/mutation hoặc thứ tự nghiệp vụ toàn cục |

Snapshot tạo **hard link**, nên snapshot nằm cùng filesystem vẫn có thể bị mất cùng ổ đĩa, bị xóa hoặc gặp sự cố ransomware/máy chủ. **Backup đáng tin** cần được copy độc lập ra vùng lưu trữ khác, có kiểm tra checksum, quyền truy cập, retention và thử restore định kỳ.

### 3.3. Snapshot là node-local, không phải “toàn cluster tại T”

~~~text
Cluster RF=3:
     Node A        Node B        Node C
       |             |             |
  Snapshot 10:00  10:01       10:02
       |             |             |
   SSTables A     SSTables B     SSTables C

Một mutation lúc 10:01 có thể chỉ xuất hiện
ở một phần các snapshot tùy thời điểm flush/replication.
~~~

Để có **restore point cấp nghiệp vụ**, cần thiết kế nhất quán qua các bảng/node và nguồn ghi: có thể tạm quiesce writes, dùng checkpoint của event stream hoặc thực hiện backup orchestration có RPO rõ ràng. Không tự gọi nhiều lần `nodetool snapshot` và tuyên bố đã có atomic global snapshot.

### 3.4. Mục tiêu RPO/RTO cần nêu trước

- **RPO (Recovery Point Objective):** mức dữ liệu mới nhất có thể bị mất. Snapshot lúc 10:00 khôi phục lúc 12:00 có thể bỏ lỡ các mutation hợp lệ giữa hai mốc nếu không replay.
- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận được để dịch vụ phục hồi, gồm lấy backup, xác minh, stream/import, compaction/repair và chuyển traffic.
- **Retention:** backup giữ bao lâu, có bản ở ngoài node không, có kiểm tra khả năng mở file không?
- **Restore scope:** khôi phục một key, một bảng, một DC hay toàn cluster; scope càng rộng càng khó cam kết nguyên tử.

**Đừng hứa “RPO=0” chỉ vì có RF=3**. Replication bảo vệ availability/mất một node theo thiết kế; nếu DELETE nhầm được replicate tới cả ba, RF=3 vẫn có thể đồng loạt giữ cùng một sai lầm.

## 4. Manifest: bộ bằng chứng bắt buộc trước khi nạp SSTable

Mỗi tập backup cần có **manifest do quy trình vận hành tạo** để không quên ngữ cảnh ban đầu. Manifest này khác `manifest.json` mà Cassandra có thể tạo trong snapshot directory.

| Nhóm trường | Ví dụ | Vì sao cần? |
|---|---|---|
| Backup ID/time | `orders-2026-11-21T10Z`, UTC | Chọn đúng recovery point, đánh giá TTL |
| Source Cassandra | Version + distribution + SSTable format | Kiểm target có đọc/stream được |
| Source schema | DDL, schema digest, table ID, UDT, indexes | Tránh nạp sai partition key hoặc col type |
| Source partitioner | `Murmur3Partitioner` | Token calculation phải tương thích |
| Source topology | DC/rack, node IDs, tokens, RF per DC | Biết file là dữ liệu node nào và phạm vi cần tổng hợp |
| Dataset | Keyspace/table, data dirs, generations/components | Không trộn file của hai bảng/đợt |
| Backup completeness | Danh sách node/table/volume, full snapshot + increments | Tránh phục hồi chỉ từ một trong ba replica |
| Integrity | Checksum của file sau khi copy, file count/byte count | Phát hiện file rơi rớt hoặc hỏng trên đường chuyển |
| Security | Key ID/encryption, access control, nơi lưu và owner | Mở được file mà không lộ dữ liệu |
| Logical checks | Expected key set, counts theo partition mẫu, audit event IDs | Xác minh *đúng nghiệp vụ*, không chỉ import thành công |
| Restore method | `sstableloader` hay `import`, target cluster/DC/KS | Ngăn operator nạp vào đích sai |

### 4.1. Kiểm integrity từ bản sao độc lập

Ví dụ thao tác shell **chỉ trên thư mục staging chứa bản copy**, không đọc file đang được engine sử dụng:

~~~bash
# Đường dẫn ví dụ trong lab; đừng dùng trên live data directory.
find /srv/restore-staging -type f -name '*-Data.db' -print
find /srv/restore-staging -type f -name '*-TOC.txt' -print
du -sh /srv/restore-staging

# So checksum với manifest độc lập đã ghi khi sao lưu.
sha256sum /srv/restore-staging/restore_target/orders/*-Data.db
~~~

Checksum chỉ chứng minh **byte copy khớp lúc backup**, không chứng minh dữ liệu logic đúng. Nếu bản backup vốn đã sai hay ghi thiếu ở một replica, checksum vẫn có thể hợp lệ. Khi lỗi SSTable corruption, cần dùng công cụ xác minh **đúng phiên bản** trên bản copy/offline và không sửa trực tiếp tập backup gốc.

## 5. Đối chiếu topology nguồn và đích

### 5.1. Vì sao token/RF/DC là phần của kế hoạch restore?

Ví dụ nguồn và đích:

~~~text
Nguồn:                               Đích:
  dc1 (3 nodes, RF=3)                  dc1 (4 nodes, RF=3)
    A -- B -- C                          P -- Q -- R -- S

  Partition key tenant-a                Cùng partition key tenant-a
  -> token t                            -> token t
  -> natural replicas A,B,C             -> natural replicas
                                         được tính lại theo ring P,Q,R,S

File SSTable từ A không thuộc "A" mãi mãi.
Restore sang ring mới phải dùng placement của ĐÍCH.
~~~

**`sstableloader`** hỏi cluster đích về token/ring và streaming các đoạn SSTable đến natural replicas đích theo keyspace replication. Nó hữu ích khi thay đổi số node, token allocation hay RF. **`nodetool import`** nạp cục bộ trên **một node**, nên chính operator phải bảo đảm file chứa token mà node đích có quyền sở hữu hoặc chọn một quy trình bảo đảm placement khác.

### 5.2. Các thông tin topology cần ghi trước restore

| Câu hỏi | Lệnh/nguồn | Hậu quả nếu bỏ qua |
|---|---|---|
| Ring đích có node UP/NORMAL không? | `nodetool status`, `describecluster` | Streaming vào cluster đang thiếu replica |
| Keyspace RF theo DC là bao nhiêu? | `DESCRIBE KEYSPACE`/`system_schema.keyspaces` | Sai số replica hoặc sai DC |
| Partitioner có giống nguồn? | `cassandra.yaml`/JMX/config inventory | Token calculation và placement không tương thích |
| Token ranges/natural endpoints có đổi không? | `nodetool ring`, `getendpoints` cho keys mẫu | Direct copy rơi vào node không sở hữu |
| Có bootstrap/decommission/replace đang chạy? | `nodetool status`, `netstats` | Topology biến động khi restore, streaming tranh tài nguyên |
| DC khác có tham gia không? | `NetworkTopologyStrategy` và target ring | `LOCAL_QUORUM` một DC không xác nhận DC khác |
| Driver/app dùng local DC nào? | Java Driver config | Read verification có thể chỉ kiểm một DC |

Lệnh quan sát:

~~~bash
nodetool version
nodetool status
nodetool ring
nodetool describecluster
nodetool netstats
nodetool getendpoints restore_target orders tenant-a
~~~

`getendpoints` trả natural endpoints dự kiến theo keyspace, table và partition key từ góc nhìn node được gọi; **không chứng minh** các endpoint ấy đang chứa SSTable hoặc đã phục hồi dữ liệu. Với composite partition key, kiểm cú pháp biểu diễn key của bản `nodetool` thay vì giả định truyền một chuỗi tùy ý.

### 5.3. Nhiều datacenter và replication strategy

~~~sql
-- Cấu hình minh họa một cluster hai datacenter.
CREATE KEYSPACE restore_target
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '3',
  'dc2': '2'
};
~~~

Nếu nguồn dùng RF=3 ở một DC mà đích dùng RF=3/2 trên hai DC, `sstableloader` phải nạp theo **replication của đích**. Khối lượng stream/space/network có thể lớn hơn tưởng tượng. Phải kiểm cross-DC bandwidth và TLS/storage ports; `--throttle-mib`/`--inter-dc-throttle-mib` được điều chỉnh theo capacity thực và bản loader.

**Không tự tăng RF rồi tin các replica mới đã nhận dữ liệu lịch sử**. Khi RF của keyspace đích thay đổi sau restore, cần runbook repair/rebuild và đối chiếu đầy đủ các replica mới theo phiên bản Cassandra.

### 5.4. Checklist topology trước khi nhập file cục bộ

Một lần `nodetool import` trên node P chỉ nên thực hiện sau khi đã kiểm:

- P thuộc target cluster và có local table/schema đúng.
- SSTable cần nhập chứa token ranges phù hợp với P theo **ring đích**; dùng kiểm tra token của import, không mặc định bỏ qua.
- Những replica còn lại được phục hồi bằng backup/streaming/repair phù hợp nếu cần.
- Node P có đủ disk headroom; không có import/compaction nặng khác.
- Không nhầm node coordinator với mọi node cần chứa dữ liệu.

Không dùng flag `--no-tokens` chỉ để lờ đi lỗi token ownership khi chưa có thiết kế chuyển đổi range rõ ràng. Một local import thành công nhưng file chứa token lạc chỗ có thể khiến CQL vẫn thiếu dữ liệu hoặc replica placement sai.

## 6. Đối chiếu phiên bản Cassandra, SSTable format, schema và table ID

### 6.1. “Cùng là Cassandra” không bảo đảm SSTable tương thích

SSTable có các **format/version riêng**, độc lập với version CQL. Cassandra 4.x và 5.0 cũng có các khác biệt ở storage engine, format BIG/BTI, metadata và công cụ offline. Trước restore cần kiểm tra:

| Thành phần | Nguồn | Đích | Quyết định |
|---|---|---|---|
| Cassandra release | 4.1.x / 5.0.x… | 4.1.x / 5.0.x… | Đối chiếu upgrade/compatibility matrix chính thức |
| SSTable format/version | Prefix/`sstablemetadata`/manifest | Binary reader/loader | Binary có thể đọc/stream đúng format không? |
| Partitioner | `Murmur3Partitioner`, v.v. | Cấu hình đích | Có cùng cách tính token không? |
| CQL schema | Tên/type các columns, primary key, UDT | DDL đích | Dữ liệu từ file có được diễn giải đúng không? |
| Table ID | UUID trong directory/`schema.cql` | UUID hiện tại | Có copy vào đúng table instance khi restore local? |
| Serialization/compression | Compression, UDTs, SSTable codecs, encryption | Libraries/keys có sẵn | Có đọc/giải mã được component không? |
| Index/views | SAI/2i/materialized view schema | Các cấu trúc đích | Có cần rebuild/đối chiếu riêng? |
| DDL history | Table đã drop/recreate/alter chưa? | Schema hiện tại | Cùng tên nhưng có phải cùng cấu trúc logic? |

**Không nạp trực tiếp SSTable từ một phiên bản mới xuống binary cũ** chỉ vì CQL `CREATE TABLE` thành công. Một SSTable format mới có thể không được reader cũ hỗ trợ. Với thay đổi major version, lập kế hoạch **chuyển đổi SSTable trên bản sao** theo tài liệu phiên bản trước khi restore, sau đó thử trong staging.

### 6.2. `sstableupgrade` không phải lệnh “chạy đại cho xong”

Apache có công cụ **`sstableupgrade`** để rewrite SSTable theo format đang được binary hỗ trợ; tài liệu 5.0 cũng đề cập snapshot upgrade khi muốn dùng snapshot từ major version cũ.

Nhưng cần lưu ý:

- Đây là thao tác **rewrite file**, tốn CPU/disk/temporary space và có thể ảnh hưởng hard links đến snapshot gốc.
- Công cụ offline thường yêu cầu **không chạy đồng thời Cassandra trên data directory nguồn**; cần sao chép sang môi trường cách ly và kiểm version.
- Không tự dùng bản Cassandra 5.0 để “hạ cấp” SSTable rồi nạp vào cluster cũ nếu chưa có ma trận tương thích và thử restore.
- Chọn `sstableupgrade` hay `nodetool upgradesstables` tùy mục tiêu offline/online và tài liệu binary cụ thể, không thay thế hai lệnh cho nhau.

**Đường an toàn:** lưu bản gốc bất biến → copy sang staging → kiểm reader/format → upgrade **trên copy** nếu được hỗ trợ → thử nạp vào cluster lab tương đương → xác minh CQL và SSTable metadata → mới triển khai runbook production.

### 6.3. Cùng tên bảng nhưng khác table ID

Cassandra đặt file table trong thư mục thường có dạng:

~~~text
/var/lib/cassandra/data/
  shop/
    orders-51b4...<table-uuid>/
      mb-1-big-Data.db
      snapshots/backup-tag/
        mb-1-big-Data.db
        schema.cql
        manifest.json
~~~

Đây là **dạng sơ đồ**, prefix SSTable/UUID thực thay đổi theo version. Nếu `DROP TABLE shop.orders` rồi `CREATE TABLE shop.orders` với cùng DDL, **table ID mới** có thể khác. Khi copy file trực tiếp vào directory cũ, Cassandra không tự ánh xạ chúng vào bảng mới.

Phân biệt:

- **`sstableloader`:** xác định đích từ keyspace/table (hoặc option target keyspace nếu bản hỗ trợ) rồi stream dữ liệu qua cluster; tránh giả định table ID nguồn bắt buộc trùng table ID đích.
- **`nodetool import`:** yêu cầu nêu rõ keyspace và table đích, nhận directory chứa SSTable; vẫn phải bảo đảm format/schema/token compatibility.
- **Manual copy + `refresh`:** phải đặt file vào **directory table ID đúng** của node đích và không trùng component filenames; rủi ro cao hơn.

Một số snapshot `schema.cql` có `WITH ID = <uuid>`. Khi khôi phục bảng đã drop, cần hiểu hậu quả của việc giữ hoặc đổi ID — đặc biệt nếu có directory cũ, snapshot/backup hay ứng dụng còn dùng schema. Không paste DDL từ snapshot production vào cluster khác **mà không xem xét** table ID, UDT, indexes và keyspace replication.

### 6.4. Schema agreement không đồng nghĩa dữ liệu đủ

`DESCRIBE TABLE` hoặc metadata driver thấy DDL đúng chỉ xác nhận **cấu trúc logic**. Nó không chứng minh:

- Mọi node đã có SSTables từ backup.
- Tất cả range ở DC đích đã nhận streaming.
- TTL/tombstones không che hàng cũ.
- Derived tables/SAI/index của ứng dụng đã nhất quán.

Cần ba tầng kiểm chứng độc lập: **schema đúng → placement/copy đúng → dữ liệu nghiệp vụ đúng**.

## 7. `sstableloader`: cơ chế, tham số và những giả định nguy hiểm

### 7.1. Khi nào chọn `sstableloader`?

Phù hợp khi:

- Cần restore snapshot/incremental SSTables vào cluster đích **đang chạy**.
- Nguồn và đích có số node, RF, rack/DC hoặc token ranges khác nhau.
- Muốn stream data qua giao thức Cassandra, để target quyết định natural replicas.
- Cần đổi **target keyspace** trong bản loader hỗ trợ hoặc chuẩn bị staging theo tên keyspace/table đích.

Khác với `nodetool import`, người vận hành **không** phải copy nguyên tập SSTable vào từng directory live của mọi replica. Nhưng loader vẫn cần **nguồn file hoàn chỉnh và tương thích**, nhiều endpoint kết nối được, quyền đọc staging và đủ tài nguyên phía đích.

### 7.2. Pipeline của sstableloader

~~~text
File SSTable bản COPY (staging, không phải SSTable active)
                   |
              sstableloader
                   |
       CQL/native port -> hỏi node đầu mối
                   |
          Token map + target RF/DC
                   |
       Chia SSTable thành token sections
                   |
         +---------+----------+
         |         |          |
      Replica P Replica Q  Replica R
         |         |          |
    SSTable streamed/received trên target
         |         |          |
         +---------+----------+
                   |
              CQL đối chiếu
             + repair khi cần
~~~

**Đầu mối `--nodes` không phải một điểm đến lưu toàn bộ dữ liệu.** Nó giúp loader kết nối và lấy ring; target endpoints được xác định theo placement thực. Chạy nhiều loader vào cùng cluster có thể gây streaming burst, phải giới hạn concurrency và network/disk.

### 7.3. Cú pháp chính và cách chuẩn bị thư mục

~~~bash
# Chỉ kiểm help, không thay dữ liệu:
sstableloader --help

# Mẫu lệnh có đường dẫn staging, không dùng live data directory:
sstableloader \
  --nodes 10.10.1.11,10.10.1.12 \
  --throttle-mib 16 \
  /srv/restore-staging/shop/orders
~~~

Theo tài liệu bulk loading, mặc định loader suy **keyspace và table từ parent directories** của đường dẫn SSTable:

~~~text
ĐÚNG cho target shop.orders:
  /srv/restore-staging/shop/orders/
    nb-1-big-Data.db
    nb-1-big-Index.db
    nb-1-big-Statistics.db
    ...

KHÔNG NÊN lấy đường dẫn snapshot gốc làm target mặc định:
  /var/lib/cassandra/data/shop/orders-<uuid>/snapshots/tag-01/

Vì tên thư mục cha có thể bị hiểu sai:
  "snapshots"/"tag-01" không phải shop.orders.
~~~

**`--nodes`/`-d` là bắt buộc.** Không đặt `--nodes` thành danh sách mọi replica cần dữ liệu theo kiểu “thay thế việc biết token ring”; chỉ cần các initial hosts phù hợp và network tới các endpoints mà loader khám phá.

### 7.4. Những option quan trọng

| Option | Tác dụng | Điều cần biết |
|---|---|---|
| `-d, --nodes` | Initial hosts (phân tách dấu phẩy) | Bắt buộc, dùng IP/hostname đích phù hợp |
| `-p, --port` | Native CQL port (thường 9042) | Dùng để kết nối/lấy ring, khác streaming storage port |
| `-sp, --storage-port` | Internode streaming port (thường 7000) | Firewall/TLS phải phù hợp cluster |
| `-ssp, --ssl-storage-port` | Port SSL storage theo cấu hình | Cần đối chiếu version/network policy |
| `-f, --conf-path` | `cassandra.yaml` cho SSL/streaming params | Dùng **bản cấu hình kiểm soát**, không tùy ý trỏ config production có secrets |
| `-u, --username` và credentials | Authentication | Tránh lộ password qua shell history/process list |
| `--throttle-mib` | Giới hạn stream MiB/s | Không dùng `0` nếu muốn hạn chế — 0 là unlimited |
| `--inter-dc-throttle-mib` | Giới hạn inter-DC throughput | Hữu ích khi nạp nhiều DC; tùy phiên bản |
| `-k, --target-keyspace` | Đổi target keyspace trong bản hỗ trợ (từ Cassandra 4.0) | **Không** tự đổi target table name; kiểm help trên binary |
| `-v, --verbose` | Chi tiết tiến độ/log | Có thể tăng log volume, không dùng credential lộ trên output |

Port `9042` cho native CQL và port `7000/7001` cho streaming không được nhầm: một máy có thể kết nối được `9042` rồi vẫn fail streaming vì storage port bị chặn. Cấu hình internode encryption các bản mới có thể khác; **không hard-code 7000/7001** mà xác minh ở cluster đích.

### 7.5. Điều kiện về nguồn file: staging độc lập

Tài liệu `sstableloader` mô tả loader là công cụ xử lý SSTable offline và cảnh báo không chạy trực tiếp trên dữ liệu đang được Cassandra thay đổi. Tài liệu bulk loading đồng thời xác nhận loader **stream đến cluster đích đang chạy**.

Cách hiểu thực hành an toàn:

1. **Target cluster vẫn có thể chạy và phục vụ CQL.**
2. **Nguồn SSTable phải là bản copy ổn định** từ snapshot/incremental backup, ở directory staging độc lập với live data directory; không để compaction của Cassandra thay/xóa file trong lúc loader đang đọc.
3. Nếu dùng các **công cụ SSTable offline khác** để kiểm/upgrade file, tuân thủ yêu cầu dừng Cassandra đối với data directory liên quan hoặc sử dụng **bản copy trên host cô lập**.
4. Tránh chạy `sstableloader` trỏ thẳng vào directory SSTable đang hoạt động trên node production.

Không có mâu thuẫn giữa “target đang chạy” và “nguồn file offline”: **hai phía có vai trò khác nhau**.

### 7.6. Những gì loader không làm

- Không tự chạy `CREATE TABLE`; target schema phải tồn tại và tương thích.
- Không biết “bản ghi đúng nhất về nghiệp vụ” khi backup có version sai.
- Không chấp nhận CSV/JSON trực tiếp; input phải là SSTable hợp lệ.
- Không biến snapshot của **một node** thành backup đầy đủ mọi token range nếu node ấy chỉ giữ một phần dataset.
- Không tự đồng bộ lại **bảng khác** mà ứng dụng denormalize.
- Không xóa SSTable nguồn sau khi stream; phải quản lý staging/retention riêng.
- Không xác nhận backup đủ phục hồi đến một timestamp tùy ý.

## 8. Chuẩn bị bộ file an toàn cho sstableloader

### 8.1. Chọn recovery point, schema và tập SSTable

Giả sử snapshot tên `bk_20261121_1000` cho bảng `shop.orders` trên các node nguồn. Kế hoạch:

1. Tập hợp snapshot và những incremental SSTables **thực sự thuộc mốc phục hồi đã chọn**.
2. Xác nhận bảng/partitioner/schema trong snapshot; không trộn các generation từ table khác.
3. Xác nhận SSTable format target loader có thể đọc.
4. Đối chiếu **source coverage** theo token ranges/replica, kể cả node đã chết.
5. Chuyển từng SSTable component cùng generation sang staging **có bản copy**, không chỉ hard links nằm trên data disk nguồn.
6. Tạo manifest/checksum, đảm bảo đủ disk space cho staging và receiver.

### 8.2. Copy vào staging với tên keyspace/table đích

Ví dụ shell trên host **lab/staging**:

~~~bash
# Ví dụ biến phải thay bằng đường dẫn snapshot thật được chọn.
SNAP_DIR="/backup-external/backup-id/shop/orders/snapshots/bk_20261121_1000"
STAGING="/srv/restore-staging/shop/orders"

mkdir -p "$STAGING"
chmod 700 "$STAGING"

# Copy các file từ bộ snapshot ĐÃ XÁC MINH, không move.
# schema.cql/manifest.json nếu có được giữ làm metadata tham khảo.
cp -a "$SNAP_DIR"/. "$STAGING"/

# Xác minh tập SSTable components cùng generation.
find "$STAGING" -maxdepth 1 -type f -print
du -sh "$STAGING"
~~~

Trong staging, `schema.cql`/`manifest.json` có thể có mặt cùng SSTables khi copy cả snapshot, nhưng **không phải SSTable components để stream**. Lệnh loader duyệt SSTables hợp lệ; giữ các metadata này trong manifest độc lập vẫn hữu ích. Nếu gom nhiều node source vào cùng một directory, **tránh đè tên generation trùng nhau**: các node có thể cùng tên SSTable ID dù nội dung khác. Dùng thư mục staging **riêng cho từng node/source set** hoặc kế hoạch đổi generation bằng công cụ được hỗ trợ; không rename tùy tiện vài component của một SSTable.

### 8.3. Tập hợp nhiều node không đồng nghĩa nạp trùng mọi bản ghi vô hại

Giả sử RF=3, 6 node trong một DC, mỗi node giữ **chỉ một phần** token ranges. Chỉ snapshot node A có thể **thiếu các partition chỉ thuộc replica khác**. Cần tính đủ coverage của toàn ring.

Ngược lại, cùng một partition có thể xuất hiện trên ba node nguồn. Nạp nhiều snapshot replica có thể sinh **stream/write amplification**, tăng disk/compaction và kéo dài restore. Hòa giải theo timestamp thường đưa trạng thái tới hội tụ, nhưng **không có nghĩa** nạp trùng dữ liệu là miễn phí hay an toàn nếu có timestamp/tombstone sai.

Để giảm rủi ro:

- Lập **ma trận token ranges × node nguồn × snapshot available**.
- Không giả định một snapshot node hoặc một `COUNT(*)` là đủ.
- Ưu tiên tập SSTables có coverage đủ và nguồn có lịch sử mutation đáng tin.
- Không trộn snapshot mốc T với incremental files mốc T+1 nếu mục tiêu khôi phục chính xác tại T mà chưa có chính sách replay.

## 9. Restore theo file bằng `nodetool import` (khuyến nghị hơn `refresh`)

Apache Cassandra 5.0 liệt kê `nodetool import` là cách nạp SSTable cục bộ thay cho `nodetool refresh` đã được hướng dẫn bulk loading đánh dấu deprecated.

### 9.1. `nodetool import` làm gì?

`import` nhận **keyspace, table và directory** chứa SSTable rồi thực hiện các bước phù hợp với tùy chọn: kiểm tính hợp lệ, token ownership, cache invalidation và xử lý repaired metadata. Nó thực hiện trên **node được gọi**, không hỏi ring để stream mọi token range tới tất cả natural replicas như `sstableloader`.

~~~text
Backup copy cho node P
        |
        v
Directory staging cục bộ
        |
  nodetool import -- KS TABLE /staging/path
        |
  Node P nạp SSTables vào table store
        |
  Đọc CQL/metrics trên cluster
        |
  Xác minh các replica khác bằng
  restore/rebuild/repair phù hợp
~~~

### 9.2. Cú pháp và tùy chọn nguy hiểm

~~~bash
nodetool help import

# Mẫu chỉ áp dụng khi directory chứa SSTables đúng table/node.
nodetool import -- shop orders /srv/restore-staging/node-p/orders
~~~

| Option | Ý nghĩa | Thực hành |
|---|---|---|
| `-e, --extended-verify` | Kiểm thêm nội dung file | Có ích khi nguồn đáng nghi; tốn thời gian |
| `-l, --keep-level` | Giữ level của SSTable | Chỉ dùng khi compaction strategy/level metadata tương thích |
| `-r, --keep-repaired` | Giữ repaired marker | Nguy hiểm nếu đem trạng thái “đã repair” từ cluster khác |
| `-t, --no-tokens` | Bỏ kiểm token ownership | **Tránh** trừ khi có runbook đặc biệt và bằng chứng placement |
| `-v, --no-verify` | Bỏ bước verify SSTable | **Tránh** với backup chưa kiểm integrity |
| `-q, --quick` | Bỏ nhiều bước verify/cache check/placement check | **Không dùng** để chữa import lỗi không rõ nguyên nhân |
| `-c, --no-invalidate-caches` | Giữ cache | Có thể khiến kết quả đọc từ cache không phản ánh dữ liệu vừa nhập |

**Đọc help trên binary thực tế**: một số bản hỗ trợ thêm tùy chọn hoặc thay tên; bài này không ngụ ý tất cả flags có trên mọi phiên bản.

### 9.3. Vì sao không nên giữ repaired metadata từ nguồn khác?

SSTable có thông tin repaired/unrepaired/pending repair liên quan đến **repair history và cluster**. Nếu giữ `--keep-repaired` một cách mù quáng khi chuyển SSTables từ cluster A sang B, repair/compaction của đích có thể tin sai rằng dữ liệu đã qua một lần đồng bộ mà thực tế **chưa từng diễn ra trên ring B**.

Thông thường phải để công cụ **xử lý repaired state theo chính sách an toàn của phiên bản**, sau đó thực hiện repair theo yêu cầu. Không dùng `--keep-repaired` chỉ để tránh chi phí repair.

### 9.4. File restore không tự sửa schema/index/derived table

Sau `import`, kiểm:

- Table base đã có đủ primary keys và columns.
- Những index/SAI/2i cần thiết có đang phục vụ truy vấn đúng không; khi nghi ngờ, dùng **rebuild index** theo runbook.
- Materialized views và bảng denormalized từ ứng dụng có cần **backfill/replay riêng** không.
- Dữ liệu từ các file import có thuộc đúng token ranges của node và các replica còn lại có đồng bộ không.

Đừng nhầm `nodetool import` đã trả `0` với “khách hàng có thể đọc lại mọi bản ghi ở mọi CL và DC”.

## 10. Legacy `nodetool refresh` và copy trực tiếp vào table directory

`nodetool refresh <keyspace> <table>` yêu cầu Cassandra **phát hiện những SSTable mới được đặt trong live table directory** mà không cần restart chỉ vì thao tác refresh:

~~~bash
nodetool help refresh

# Chỉ minh họa sau khi file đã được đặt đúng vị trí trong
# lab có runbook và xác nhận table ID/token ownership.
nodetool refresh shop orders
~~~

Khác với `import`, `refresh` không nhận directory bất kỳ để tham chiếu nguồn; nó xem dữ liệu local của table đích. Bởi vậy copy thủ công các component vào live directory có nhiều rủi ro:

1. **Sai table ID:** bảng đã drop/recreate có directory UUID mới.
2. **Trùng tên generation:** đè/ghi chồng một SSTable đang được engine sử dụng.
3. **Sai token ownership:** file vốn thuộc node cũ/ring cũ, không phải node đang restore.
4. **Không đủ components:** chỉ copy Data.db, bỏ metadata/digest/TOC.
5. **Read cache và repaired state:** trạng thái cũ không phù hợp.
6. **File copy chưa hoàn thành:** refresh phát hiện bộ component dở dang.
7. **Disk free thấp:** file tạm, snapshot hard link và compaction tạo chi phí lớn.

**Hướng chọn:** Với bản Cassandra hiện đại, ưu tiên **`nodetool import`** từ staging và dùng verification mặc định. Chỉ dùng legacy refresh nếu runbook đã kiểm tra rõ binary, directory UUID, file naming, token ownership và cách staged copy an toàn. **Không** copy thẳng từ một source node sang target live directory khi target đang bận rồi chạy refresh để “thử xem”.

### 10.1. Khi cần copy file thì nên tách hai pha

~~~text
PHA A — Chuẩn bị OFFLINE
  External backup -> staging directory riêng
  Checksum / file set / format / schema / token
  Kiểm nguồn copy hoàn chỉnh

PHA B — NẠP CÓ KIỂM SOÁT
  Ưu tiên import từ staging (không copy vào live dir)
     |
     v
  Kiểm SSTable count + read CQL + replica coverage

Legacy refresh:
  Chỉ trong quy trình được thiết kế và nghiệm thu riêng,
  copy bộ file hợp lệ vào đúng live table directory
  rồi refresh đúng node/table.
~~~

Manual file restore là một kỹ thuật **chọn lọc**. Nếu mục tiêu là đưa một snapshot của cả cluster từ topology cũ sang topology mới, `sstableloader` thường phù hợp hơn và ít rủi ro placement hơn.

## 11. Timestamp, TTL và tombstone: vì sao “restore đã chạy” nhưng row vẫn mất?

### 11.1. Cassandra hòa giải cell theo timestamp, không theo thời điểm restore

Cassandra dùng timestamp mutation (thường độ phân giải **microsecond**) để hòa giải phiên bản. `sstableloader` hoặc `nodetool import` đưa nội dung SSTable cũ vào hệ thống, **không tự coi thời điểm import là write timestamp mới nhất**.

~~~text
T0 — Ghi hàng thành công
  status = PAID, write timestamp = 100

T1 — DELETE nhầm
  tombstone, write timestamp = 200

T2 — Khôi phục SSTable ở snapshot T0
  status = PAID, write timestamp = 100

Trên bảng đích vẫn có tombstone T1:
  200 > 100 => PAID từ snapshot tiếp tục bị che.
  SELECT có thể vẫn trả (0 rows).
~~~

**Không có lỗi loader nào ở đây**: nó có thể đã stream đúng byte và cả replication, nhưng reconciliation của Cassandra vẫn coi DELETE mới hơn là trạng thái hợp lệ. Đây là lý do **khôi phục vào keyspace/bảng cách ly** là lựa chọn an toàn để điều tra: ở môi trường tách biệt, bạn có thể xem nội dung snapshot trước khi quyết định tác động lên bảng live.

### 11.2. Tại sao không “gán timestamp cực lớn” để ép dữ liệu quay lại?

Một cách sửa nhanh nhưng nguy hiểm là replay toàn bộ snapshot với timestamp rất lớn. Nó có thể:

- Ghi đè các UPDATE hợp lệ xảy ra sau snapshot.
- Che DELETE hợp lệ mà nghiệp vụ muốn giữ.
- Tạo timestamp “tương lai” khiến mutation bình thường sau này không thể thắng.
- Phá tính đồng bộ giữa các bảng denormalized, index và audit.

Nếu cần khôi phục **chọn lọc**, phải có **nguồn sự thật** về sự kiện hợp lệ, khóa/phiên bản nghiệp vụ và thời điểm muốn restore. Phân biệt sửa dữ liệu logic với chuyển SSTable; lệnh loader **không** cung cấp quyết định nghiệp vụ.

### 11.3. TTL không được “làm mới” bằng cách stream bản ghi cũ

Giả sử một cell được INSERT với `TTL 3600`, snapshot được tạo khi nó còn sống, nhưng việc restore diễn ra **sau thời điểm hết hạn**. SSTable có metadata TTL/expiration tương ứng, nên giá trị có thể **không còn hiển thị** sau restore.

~~~text
10:00  INSERT token USING TTL 3600
10:10  snapshot, TTL còn khoảng 50 phút
12:00  sstableloader vào cluster khác

Kỳ vọng logic:
  token đã quá thời gian expire, không "sống thêm 1 giờ".
~~~

Khi muốn tạo **phiên làm việc mới**, ứng dụng phải tạo mutation mới theo chính sách nghiệp vụ, không được coi restore là một cách reset TTL. Đối với dữ liệu tuân thủ retention, việc hồi sinh cell đã hết hạn có thể là lỗi nghiêm trọng.

### 11.4. Zombie data khi tombstone đã bị purge

Một nguy cơ ngược lại:

~~~text
T0: A/B/C đều giữ customer-123 (ts=100)
T1: DELETE customer-123 (ts=200), C không nhận DELETE
T2: A/B giữ tombstone; C offline vượt gc_grace_seconds
T3: A/B compaction purge tombstone khi đủ điều kiện
T4: C / backup cũ lại đưa customer-123 ts=100 vào cluster

Không còn tombstone ts=200 để che dữ liệu ts=100
=> customer-123 có thể xuất hiện trở lại (zombie).
~~~

Repair/loader **không thể tái tạo một tombstone đã bị purge** nếu không còn ở nguồn nào. Nên trước restore SSTables cũ, kiểm:

- `gc_grace_seconds` theo table, tuổi backup và lịch repair.
- Thời gian một node/replica ở trạng thái offline.
- Những DELETE/TTL đã xảy ra sau snapshot.
- Có chính sách **legal deletion/retention** buộc không hồi sinh dữ liệu không?
- Cách xác minh **không xuất hiện trở lại** với các khóa đã xóa.

Một snapshot rất cũ không tự “an toàn vì là backup”; nó có thể chứa nhiều giá trị mà chính sách dữ liệu hiện tại yêu cầu **không được quay lại**.

### 11.5. Một bảng có nhiều phiên bản và tombstone theo nhiều scope

| Loại | Điều cần nhớ khi restore |
|---|---|
| Cell UPDATE | Timestamp của từng cell; row có thể hòa giải từ nhiều SSTables |
| Row DELETE | Tombstone che các cell cũ trong row |
| Partition DELETE | Tombstone có thể che cả nhiều clustering rows |
| Range DELETE | Che các clustering ranges, phải xét điều kiện range |
| TTL | Expiration có thể xảy ra trước restore |
| Collection/UDT | Tùy loại collection có cell-level metadata; cần kiểm schema tương thích |
| LWT/CAS | Thứ tự nghiệp vụ không tự được khôi phục chỉ bằng timestamp |

`WRITETIME(col)` trong CQL giúp quan sát write timestamp của một cell **đang sống**; nó **không phải công cụ xem mọi tombstone** hoặc lịch sử đầy đủ trong SSTables. Khi một SELECT không trả hàng, phải phân biệt “chưa nhập”, “nhập nhưng bị tombstone che”, “TTL đã hết”, “sai primary key/CL” và “đọc ở DC chưa đồng bộ”.

## 12. Runbook restore qua sstableloader trên cluster đích

### 12.1. Giai đoạn A — Phân loại sự cố và chốt recovery scope

Chọn **một** mục tiêu cụ thể:

1. Khôi phục table đã mất vào **keyspace phục hồi cách ly** để đối chiếu.
2. Phục hồi một tập khóa bị xóa nhầm sau khi xác định audit.
3. Nạp toàn bộ dữ liệu vào **cluster mới với topology khác**.
4. Phục hồi node/replica thiếu data (cần xem replace/rebuild/repair có phù hợp hơn không).
5. Phục hồi từ snapshot + increments theo một mốc đã công bố, với phạm vi RPO rõ.

Không viết runbook chỉ nói “restore Cassandra” mà không rõ **table/keyspace/cluster/DC, recovery point và nguồn sự thật**.

### 12.2. Giai đoạn B — Preflight bắt buộc

| Cổng | Kiểm gì? | Tiêu chí đạt |
|---|---|---|
| **B1 — Backup** | Có tất cả SSTable components + checksum/manifest? | File đủ, copy độc lập đọc được |
| **B2 — Version** | Binary loader/target và SSTable format có tương thích? | Đã thử đọc trên lab cùng version |
| **B3 — Schema** | Partition key, clustering columns, types, UDT, table ID/indexes? | Schema đích tương thích, DDL được kiểm |
| **B4 — Topology** | Partitioner, tokens, DC/rack, RF và node health? | Ring ổn định, đủ natural replicas |
| **B5 — Capacity** | Disk free, network/streaming, compaction, CPU? | Có headroom cho dữ liệu mới và compaction |
| **B6 — Security** | TLS, auth, secrets, encryption keys, firewall? | Có kết nối các ports cần thiết |
| **B7 — Data safety** | TTL/tombstone/DELETE/newer writes có thể xung đột? | Có isolated restore và audit plan |
| **B8 — Observability** | Metrics, logs, pre/post checks, on-call? | Có thể xác nhận từng bước hoặc dừng |

Nếu B2 hoặc B3 chưa đạt, **không thử stream vào production** để xem liệu có lỗi không. Đầu tiên dùng cluster lab với schema, version và replication gần đích.

### 12.3. Giai đoạn C — Chuẩn bị target cluster và schema

Trong cqlsh, trên cluster đích đã được phép:

~~~sql
DESCRIBE KEYSPACE restore_target;
DESCRIBE TABLE restore_target.orders;
~~~

Nếu table đích chưa tồn tại, phải **tạo theo schema tương thích** được kiểm từ backup và theo topology/RF của target. Không paste toàn bộ `schema.cql` từ nguồn mà không xem các ràng buộc version, table ID, option đã bị loại hoặc RF/DC mới.

**Đường mặc định an toàn:** restore vào keyspace mới `restore_target` với schema tương đương, không vội overwrite bảng production. Sau khi đối chiếu, ứng dụng có thể đọc từ bảng đó hoặc replay chọn lọc sang bảng đích chính theo quy trình nghiệp vụ.

### 12.4. Giai đoạn D — Stream theo batch có giới hạn

~~~bash
# Chỉ trên host có snapshot copy ổn định và network tới target.
sstableloader \
  --nodes 10.10.1.11,10.10.1.12 \
  --throttle-mib 16 \
  /srv/restore-staging/restore_target/orders
~~~

Đây là **lệnh mẫu**, yêu cầu thay hosts/path, kiểm authentication/TLS và limit theo môi trường. Không chạy song song nhiều loader trừ khi đã đo capacity. Theo dõi:

- Loader log: established connections, SSTable sections, bytes streamed, failures/partial transfers.
- `nodetool netstats` tại các node receiver.
- Disk I/O, disk free, compaction pending, GC và write/read p95/p99.
- Node UP/NORMAL, hiện tượng timeout theo CL.
- Số range/source-set đã nạp trong manifest, tránh báo hoàn tất vì một batch thành công.

Không xóa staging sau khi loader báo 100% cho đến khi **đã kiểm đủ dữ liệu và phạm vi**.

### 12.5. Giai đoạn E — Xác minh đủ ba lớp

**Lớp 1: Transport**

- Lệnh loader hoàn tất không lỗi hoặc có danh sách task cần retry.
- Không còn streaming lỗi, source files/bytes và target nhận đủ theo log.
- Không có node/cổng/TLS/auth bị bỏ qua âm thầm.

**Lớp 2: Replica placement**

- Keyspace/table đích đúng, RF theo DC, ring ổn định.
- Những primary keys ở các token ranges đại diện đọc được ở CL mong muốn.
- Coverage của tất cả source partitions/ranges được ghi nhận, không chỉ một node.
- Repair được thực hiện nếu nguồn/đích có dữ liệu lệch/hints không đủ; hiểu repair không thay audit.

**Lớp 3: Business correctness**

- Đối chiếu các primary keys và cột quan trọng với event/audit log.
- Kiểm **hàng phải có và hàng phải vắng**, nhất là DELETE/TTL.
- Kiểm out-of-order update, timestamps, version nghiệp vụ và bảng denormalized.
- Đảm bảo không tái xuất dữ liệu đã bị purge/được yêu cầu xóa.

### 12.6. Điều kiện dừng trong khi streaming

| Điều kiện | Quyết định |
|---|---|
| Format/schema mismatch | Dừng batch, không ép nạp hoặc xóa metadata |
| Một target DC unreachable | Không tuyên bố đủ replica; điều tra network/ring |
| Disk free dưới ngưỡng an toàn | Tạm dừng loader/giảm concurrency theo runbook |
| Client read/write timeout tăng | Kiểm streaming throttle/compaction, giảm tải có kiểm soát |
| Có hàng đã DELETE xuất hiện lại | Dừng đưa vào production, kiểm tombstone/audit |
| Loader success nhưng keys còn thiếu | Kiểm source range coverage, TTL/tombstone, CL, schema |
| Có yêu cầu sửa dữ liệu logic | Chuyển sang quy trình restore chọn lọc, không tiếp tục stream mù quáng |

**Rollback của bulk restore không đơn giản**: loader đã ghi SSTables vào bảng đích và chúng có thể đã được compact. Cách an toàn hơn là **dùng keyspace/table phục hồi cách ly**, giữ traffic ứng dụng ở nơi cũ cho tới khi data checks đạt. Nếu bắt buộc nạp vào live table, phải có **kế hoạch undo theo nguồn nghiệp vụ**, không giả định có một “sstableloader undo”.

## 13. Ví dụ topology khác: restore từ RF=3/3-node vào RF=3/5-node

Giả sử nguồn có RF3 với ba node, đích có RF3 với năm node trong một DC:

~~~text
                  SOURCE                       TARGET
          Cassandra 4.1 / dc1              Cassandra 4.1 / dc1
          nodes A,B,C / RF=3                nodes P,Q,R,S,T / RF=3
                |                                 ^
          node-local snapshots                    |
             A + B + C                            |
                |                                 |
        backup manifest + schema                  |
                |                                 |
          staging copy                            |
                |                                 |
           sstableloader -------------------------+
                |
    target token map -> partitions distributed
         across new natural replicas
~~~

Với nguồn chỉ ba node và RF=3, nhiều partition có ba bản sao (cùng DC), nhưng **không lấy số node là bằng chứng snapshot đã chứa đầy đủ các writes** — replica có thể offline hoặc bỏ lỡ mutation. Mỗi source snapshot có thể khác thời điểm và freshness. Chọn tập backup/repair/source truth theo runbook.

**Sai lầm cần tránh:** Copy snapshot node A vào directory node P, B vào Q và C vào R rồi cho rằng các bản sao đã được phân phối. Ở target 5-node, token placement của các partition đã đổi; `nodetool import` cục bộ như vậy có thể để dữ liệu ở sai node/range. `sstableloader` được thiết kế để dựa vào ring đích thay vì ánh xạ một-một tên node.

### 13.1. Kiểm source ≠ target bằng dữ liệu có khóa thật

Chọn một tập primary key có token nằm rải đều:

~~~text
Primary key                Expected source state      Target checks
tenant-a/order-001         PAID, version=7            PAID, version=7
tenant-b/order-002         CANCELLED, version=3       CANCELLED, version=3
tenant-c/order-003         DELETED at T1              no row
tenant-d/order-004         TTL expired by T2          no row
~~~

Trên đích, dùng `nodetool getendpoints` với partition keys tương ứng (cú pháp theo version) để biết natural endpoints. Nhưng đừng dùng nó như lệnh đọc vật lý trực tiếp SSTable từng node; dữ liệu cần được kiểm qua CL, tracing có kiểm soát và logs/repair coverage.

### 13.2. Multi-DC: LOCAL_QUORUM không kiểm DC còn lại

Giả sử target có:

~~~text
dc1: RF=3, local clients đọc LOCAL_QUORUM
dc2: RF=2, remote clients đọc LOCAL_QUORUM
~~~

Một lần đọc `LOCAL_QUORUM` thành công tại `dc1` **không xác nhận** dữ liệu ở `dc2` đã đủ. Sau restore cần xác minh theo **từng DC**, nhất là khi loader bị chặn internode TLS/firewall giữa các site. Trước khi chuyển traffic ứng dụng Java sang một DC mới, kiểm keyspace replication, streaming logs và driver `local-datacenter`.

## 14. Lab A — Snapshot rồi dùng sstableloader vào keyspace khác, không xóa bảng nguồn

**Mục tiêu:** Tạo hai bảng cùng schema trên **cluster lab một node**, lấy snapshot bảng nguồn, sửa thêm dữ liệu nguồn **sau** snapshot, rồi stream snapshot vào keyspace đích riêng. Nhờ đó có thể chứng minh bản đích đại diện recovery point cũ và **không tự nhận những write sau snapshot**.

**Yêu cầu:** Cassandra 4.1/5.0 lab một node, một data directory để thao tác đơn giản; tài khoản có quyền CQL DDL, `nodetool snapshot` và `sstableloader`; không chạy trên production. Đường dẫn data directory trong ví dụ dành cho Linux package mặc định, **cần xác minh ở máy lab**.

### Bước 1 — Tạo schema nguồn và đích tương thích

~~~sql
CREATE KEYSPACE IF NOT EXISTS restore_source
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE KEYSPACE IF NOT EXISTS restore_target
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS restore_source.orders (
  tenant_id text,
  order_id uuid,
  status text,
  amount int,
  business_version int,
  PRIMARY KEY ((tenant_id), order_id)
);

CREATE TABLE IF NOT EXISTS restore_target.orders (
  tenant_id text,
  order_id uuid,
  status text,
  amount int,
  business_version int,
  PRIMARY KEY ((tenant_id), order_id)
);
~~~

`SimpleStrategy`/RF=1 chỉ để minh họa trên **một node lab**. Không dùng cấu hình này làm khuyến nghị production nhiều DC. Cả hai bảng phải có **cùng partition key, clustering key, types và cấu trúc row**. Bảng target **mới, rỗng** là lựa chọn an toàn; nếu từng chạy lab, tạo keyspace/bảng lab mới hoặc xác minh trạng thái trước khi nạp để tránh lẫn dữ liệu cũ.

### Bước 2 — Ghi dữ liệu nguồn trước snapshot

~~~sql
CONSISTENCY ONE;

INSERT INTO restore_source.orders
  (tenant_id, order_id, status, amount, business_version)
VALUES (
  'tenant-a', 11111111-1111-1111-1111-111111111111,
  'NEW', 500, 1
);

INSERT INTO restore_source.orders
  (tenant_id, order_id, status, amount, business_version)
VALUES (
  'tenant-b', 22222222-2222-2222-2222-222222222222,
  'PAID', 900, 2
);

SELECT order_id, status, amount, business_version
FROM restore_source.orders
WHERE tenant_id = 'tenant-a';

SELECT order_id, status, amount, business_version
FROM restore_source.orders
WHERE tenant_id = 'tenant-b';
~~~

Ghi lại expected state `T0` từ dữ liệu do chính lab tạo: order `1111…` có NEW/version 1, order `2222…` có PAID/version 2.

### Bước 3 — Snapshot đúng một bảng, flush mặc định

~~~bash
# Kiểm help theo version.
nodetool help snapshot

# Snapshot một bảng, không đặt --skip-flush.
nodetool snapshot --tag lab_restore_01 --table orders restore_source

# Quan sát các snapshot trên node.
nodetool listsnapshots
~~~

`--skip-flush` nếu sử dụng sẽ **bỏ qua unflushed memtables**; vì vậy đừng dùng trong lab muốn backup hai INSERT vừa ghi. Snapshot là bản sao node-local; lab một node RF1 khiến tập snapshot dễ hiểu hơn production đa node.

### Bước 4 — Cố ý tạo khác biệt **sau snapshot**

~~~sql
UPDATE restore_source.orders
SET status = 'PAID', business_version = 2
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

INSERT INTO restore_source.orders
  (tenant_id, order_id, status, amount, business_version)
VALUES (
  'tenant-c', 33333333-3333-3333-3333-333333333333,
  'NEW', 1200, 1
);

SELECT order_id, status, business_version
FROM restore_source.orders
WHERE tenant_id = 'tenant-a';

SELECT order_id, status, business_version
FROM restore_source.orders
WHERE tenant_id = 'tenant-c';
~~~

Sau bước này, bảng nguồn `restore_source.orders` có PAID/version 2 cho order `1111…` và có thêm `tenant-c`. Snapshot `lab_restore_01` **không tự thay đổi** khi bạn ghi thêm vào memtable/SSTables nguồn: hard link đến các SSTables tại T0 vẫn giữ nội dung cũ. Đây là giả định cần kiểm bằng chính quá trình restore, không bằng cách nhìn current SELECT nguồn.

### Bước 5 — Tìm snapshot và copy vào staging có đúng parent path

~~~bash
# Đọc danh sách thư mục; không sửa data live.
find /var/lib/cassandra/data/restore_source \
  -type d -path '*/snapshots/lab_restore_01' -print
~~~

Ví dụ đường dẫn thật có dạng:

~~~text
/var/lib/cassandra/data/restore_source/
  orders-<source_table_uuid>/
    snapshots/lab_restore_01/
      <sstable_prefix>-Data.db
      <sstable_prefix>-Statistics.db
      ... các component khác ...
      schema.cql
      manifest.json
~~~

**Điền bằng đường dẫn THẬT** từ `find` (không copy literal `<source_table_uuid>`):

~~~bash
# Các path này là template lab, phải thay <source_table_uuid>.
SNAP_DIR="/var/lib/cassandra/data/restore_source/orders-<source_table_uuid>/snapshots/lab_restore_01"
STAGING="/srv/restore-staging/restore_target/orders"

mkdir -p "$STAGING"
chmod 700 "$STAGING"

# Staging cần trống trước lần restore thử; nếu không trống,
# dừng và đánh giá, KHÔNG chạy rm -rf mù quáng.
cp -a "$SNAP_DIR"/. "$STAGING"/

find "$STAGING" -maxdepth 1 -type f -print
du -sh "$STAGING"
~~~

Nếu Cassandra có **nhiều data directories**, snapshot của một table có thể xuất hiện ở nhiều đường dẫn. Lab đơn giản này chỉ hợp lệ khi bạn đã xác minh tất cả SSTables thuộc tập dữ liệu cần test đã được thu thập; không lấy `find` kết quả đầu tiên rồi tuyên bố coverage đủ cho production.

**Tại sao parent path là `restore_target/orders`?** `sstableloader` mặc định suy target keyspace/table từ đường dẫn. Snapshot gốc thuộc `restore_source/orders-UUID/snapshots/tag`, nên không thể ném nguyên path snapshot đó vào loader rồi mong nó tự chuyển sang `restore_target.orders`.

### Bước 6 — Chạy sstableloader trên bản copy

~~~bash
# Trên host lab có sstableloader tương thích target.
# Đích 127.0.0.1 chỉ đúng khi loader chạy cùng host Cassandra lab.
sstableloader \
  --nodes 127.0.0.1 \
  --throttle-mib 8 \
  /srv/restore-staging/restore_target/orders
~~~

Kỳ vọng log có những sự kiện:

~~~text
Established connection to initial hosts
Opening sstables and calculating sections to stream
Streaming relevant parts of SSTables ...
Summary statistics: bytes transferred, duration, transfer rate
~~~

Đây là **dạng output minh họa**, không dự báo số bytes/duration thực. Nếu báo lỗi “initial hosts”, kiểm native port/địa chỉ; nếu lỗi streaming, kiểm storage port/TLS; nếu lỗi schema/format, **dừng và sửa nguyên nhân**, không đổi các SSTable bytes bằng tay.

### Bước 7 — Đối chiếu source hiện tại với target snapshot

~~~sql
CONSISTENCY ONE;

SELECT order_id, status, amount, business_version
FROM restore_target.orders
WHERE tenant_id = 'tenant-a';

SELECT order_id, status, amount, business_version
FROM restore_target.orders
WHERE tenant_id = 'tenant-b';

SELECT order_id, status, amount, business_version
FROM restore_target.orders
WHERE tenant_id = 'tenant-c';

SELECT order_id, status, amount, business_version
FROM restore_source.orders
WHERE tenant_id = 'tenant-a';
~~~

| Primary key | Bảng nguồn lúc tạo snapshot T0 | Bảng nguồn hiện tại T1 | Bảng target sau loader (kỳ vọng) |
|---|---|---|---|
| `tenant-a/1111…` | NEW, version=1 | PAID, version=2 | **NEW, version=1** |
| `tenant-b/2222…` | PAID, version=2 | PAID, version=2 | **PAID, version=2** |
| `tenant-c/3333…` | Không có | NEW, version=1 | **Không có** |

Điều này minh họa **snapshot at T0**, không phải replication live. Trong production, snapshot không nguyên tử toàn cluster và dữ liệu sau snapshot cần chính sách replay/restore rõ ràng.

### Bước 8 — Kiểm metrics và thu hồi staging đúng chính sách

~~~bash
nodetool status
nodetool netstats
nodetool tablestats restore_target.orders
nodetool compactionstats
~~~

Sau khi đối chiếu, lưu log/manifest/checksums và trạng thái kết quả. Không xóa staging/snapshot ngay khi câu SELECT đầu tiên đúng; cần thời gian kiểm schema, token ranges, old tombstones và một mẫu dữ liệu đại diện trước khi giải phóng backup.

**Bài học lab:** `sstableloader` có thể nạp dữ liệu từ snapshot sang **bảng cùng schema ở keyspace khác** mà không cần DROP/TRUNCATE bảng nguồn. Điều này giúp điều tra “dữ liệu ở T0” mà không đè lên mutation T1.

### Bước 9 — Phương án có `--target-keyspace`, chỉ khi binary hỗ trợ

Từ dòng Cassandra 4.0, tài liệu bulk loading nêu option `-k, --target-keyspace`. Với option này, có thể giữ phần source path logic của staging rồi chỉ định đích:

~~~bash
# Ví dụ khác, dùng staging riêng; không chạy thêm vào bảng đã nạp
# nếu không có lý do và kiểm tác động nạp trùng.
sstableloader \
  --nodes 127.0.0.1 \
  --target-keyspace restore_target \
  /srv/restore-staging/restore_source/orders
~~~

Đây là **phương án thay thế** Bước 6, không phải yêu cầu chạy cả hai. Phải kiểm `sstableloader --help` của đúng binary xem option có tồn tại và ý nghĩa path; nó chỉ thay target **keyspace**, không tự đổi tên bảng hoặc chuyển schema.

## 15. Lab B — Lập kế hoạch restore theo file trên một node (không cần phá dữ liệu)

Lab A dùng streaming để nạp vào đúng natural replicas. Lab B tập trung **lập quyết định an toàn** trước khi dùng `nodetool import`. Để tránh nạp trùng hoặc sửa live table trong lúc học, chỉ **thực thi import trên một cluster lab thứ hai** có bảng rỗng, tương thích và được operator xác minh.

### 15.1. Phiếu kiểm trước khi import

~~~text
FILE-IMPORT PRECHECK
Source:
  snapshot tag / backup ID:
  source node ID, token ranges:
  source table ID + CQL DDL:
  Cassandra/SSTable version:
  checksum verified:
  components count:

Destination:
  Cassandra/SSTable reader version:
  keyspace/table ID and exact schema:
  partitioner:
  target node ID, token ranges, local DC:
  enough disk free and no active repair/streaming:
  other replicas' recovery plan:

Method:
  import, not direct copy+refresh
  token verification: ENABLED
  SSTable validation: ENABLED
  keep repaired metadata: NO, unless proven safe
  rollback/escalation: documented
~~~

### 15.2. Cú pháp import để kiểm trong lab thứ hai

~~~bash
# Chỉ kiểm help trước, không nhập bất kỳ file nào.
nodetool help import

# Chỉ chạy trên cluster lab mới, đã xác minh file/token/schema.
nodetool import -- restore_target orders \
  /srv/restore-staging/node-p/orders
~~~

**Không dùng `--no-tokens` hoặc `--no-verify` để ép bài lab thành công.** Nếu import báo token out of range, đó chính là bài học: file lấy từ ring khác không thích hợp để đặt trực tiếp trên node P. Hãy chọn `sstableloader` hoặc tạo source phù hợp, chứ không xóa rào bảo vệ.

### 15.3. Cách so file restore và stream restore

| Câu hỏi | `sstableloader` | `nodetool import` |
|---|---|---|
| Cần biết target node sở hữu token nào? | Loader lấy ring để quyết định | Operator phải chọn node/token phù hợp |
| Có tự stream tới mọi replica? | Có, theo replication đích | Không; import cục bộ |
| Input directory cần có tên KS/table? | Có, trừ phần target-keyspace được hỗ trợ | Không yêu cầu suy KS/table từ path vì đã khai báo trong lệnh |
| Có thể nạp vào cluster có topology khác? | Thường là công cụ thích hợp | Rủi ro placement, cần quy trình đặc biệt |
| Có cần target table/schema trước? | Có | Có |
| Có thể xác minh ngay bằng một SELECT ONE? | Có thể quan sát nhưng chưa chứng minh mọi replica | Có thể quan sát nhưng chưa chứng minh placement toàn cluster |
| Khi nạp trùng nhiều SSTables có miễn phí? | Không | Không |

## 16. Phục hồi một node sau mất đĩa: khi nào dùng backup file?

Giả sử DC có RF=3, một node P mất disk:

~~~text
Trước lỗi:
    P (data disk hỏng), Q, R, S   — RF=3

Những range do P giữ có thể còn bản trên Q/R/S.

Phương án ưu tiên nếu dữ liệu khác còn tốt:
    replace/rebuild node P theo topology và streaming.

Phương án dùng file backup khi thực sự cần:
    restore các SSTables phù hợp vào node P đã chuẩn bị
    bằng import, kiểm token/schema/format và repair.
~~~

**Đừng nhầm:** Một bản SSTable từ node Q **không mặc nhiên** là file restore của node P. Sau thay node/đổi ring, token ownership có thể khác. Chọn giữa rebuild và import theo tốc độ, trạng thái replica, downtime, grace period và chất lượng backup.

### 16.1. Điều kiện để nạp file vào node cục bộ

- Node được quản lý/khởi tạo đúng theo quy trình replace/rebuild; không tự gắn một data directory cũ vào cluster rồi làm “node sống lại”.
- Directory cho table đã có schema/table ID đúng, đúng partitioner và format.
- SSTables được copy từ snapshot có checksum và token ranges hợp lệ.
- Không còn tiến trình Cassandra/source đang sửa các file staging.
- Có lịch repair để xử lý mutation bỏ lỡ kể từ backup, đặc biệt khi **hint retention window** đã qua.
- Đánh giá tombstone GC và nguy cơ zombie nếu node cũ down lâu.
- Chỉ đưa node trở lại phục vụ bình thường sau khi **data coverage + SLO + CL** đạt.

### 16.2. Vì sao không luôn chọn “copy lại file từ backup”?

Nếu replica khác còn đầy đủ và ring đủ khỏe, **rebuild/replace** có thể tái tạo đúng những token ranges mà node mới phải sở hữu trong topology hiện tại. File backup có thể:

- Cũ hơn nhiều giờ/ngày.
- Thiếu mutation trong memtable/commit log.
- Chứa những range node mới không còn sở hữu.
- Mang tombstone đã lỗi thời hoặc repaired metadata không tương thích.
- Mang SSTable format cũ mà binary mới không đọc.

Do đó **backup file là công cụ phục hồi**, không nhất thiết là giải pháp tốt nhất cho mọi node failure.

## 17. Java Driver 4.x: đối chiếu kết quả phục hồi với nguồn kỳ vọng

Ứng dụng Java kết nối Cassandra qua **CQL**, không “đọc trực tiếp ba file Data.db” từ mỗi replica. Một phép đo ứng dụng kiểm **dữ liệu đọc được ở CL đã chọn**, vì vậy phải kết hợp với trạng thái loader/repair và kiểm các datacenter khác.

### 17.1. Probe CQL có thể sử dụng lại

Ví dụ Java 17 với DataStax Java Driver 4.x, dành cho **lab RF=1**:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.util.UUID;

public final class RestoreProbe {
    public record OrderState(
            String status,
            Integer amount,
            Integer businessVersion,
            Long statusWriteTimeMicros) {}

    public static OrderState read(
            CqlSession session, String tenantId, UUID orderId) {

        SimpleStatement stmt = SimpleStatement.builder(
                "SELECT status, amount, business_version, " +
                "WRITETIME(status) AS status_ts " +
                "FROM restore_target.orders " +
                "WHERE tenant_id = ? AND order_id = ?")
            .addPositionalValues(tenantId, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE)
            .build();

        Row row = session.execute(stmt).one();
        if (row == null) {
            return null; // Không có row sống theo CL của phép đọc.
        }

        return new OrderState(
            row.getString("status"),
            row.isNull("amount") ? null : row.getInt("amount"),
            row.isNull("business_version")
                ? null : row.getInt("business_version"),
            row.isNull("status_ts")
                ? null : row.getLong("status_ts"));
    }

    public static void main(String[] args) {
        // Contact point/local DC/credentials lấy từ cấu hình môi trường lab.
        try (CqlSession session = CqlSession.builder()
                .withLocalDatacenter("datacenter1")
                .build()) {

            OrderState t0 = read(
                session, "tenant-a",
                UUID.fromString("11111111-1111-1111-1111-111111111111"));

            boolean matchesSnapshotT0 = t0 != null
                && "NEW".equals(t0.status())
                && Integer.valueOf(500).equals(t0.amount())
                && Integer.valueOf(1).equals(t0.businessVersion());

            System.out.println("snapshotT0Matches=" + matchesSnapshotT0);

            OrderState shouldBeAbsent = read(
                session, "tenant-c",
                UUID.fromString("33333333-3333-3333-3333-333333333333"));

            System.out.println("tenantCAfterT0Absent="
                + (shouldBeAbsent == null));
        }
    }
}
~~~

**Chú ý cách kết nối:** `datacenter1` ở code là **tên DC mặc định của nhiều lab**, nhưng DC thực có thể là `dc1` hoặc tên khác. Driver cần contact points và local datacenter đúng; ứng dụng thật nên cấu hình ngoài code, tái sử dụng `CqlSession`, không tạo session mỗi request. Lệnh demo thiếu cấu hình contact point cụ thể vì môi trường khác nhau; trước khi chạy, bảo đảm driver có thể kết nối qua contact points/defaults theo installation lab.

**Vì sao so với T0 thay vì bảng nguồn hiện tại?** Vì lab cố ý có mutation T1 sau snapshot. Nếu lấy `SELECT restore_source.orders` tại T1 làm “expected”, ta sẽ nhầm đúng snapshot T0 thành restore thiếu dữ liệu.

### 17.2. Đọc ở các mức consistency: thấy đúng chưa chắc mọi replica đúng

| Phép kiểm | Biết được gì? | Không chứng minh được gì? |
|---|---|---|
| `ONE` | Một lần đọc ở CL thấp, phù hợp lab RF1 | Mọi replica RF3 đã giống nhau |
| `LOCAL_QUORUM` | Đã đủ phản hồi trong local DC theo RF | DC khác đã nhận dữ liệu |
| `QUORUM` | Đã đủ quorum theo yêu cầu keyspace/topology | Mọi replica vật lý đều chứa bản đúng |
| `ALL` | Cần phản hồi của tất cả full replicas phù hợp, nếu tất cả khả dụng | Không xác nhận tính đúng nghiệp vụ hay nguồn audit |
| Tracing có kiểm soát | Node tham gia, một số bước đọc/hòa giải | Không bao phủ mọi partition/token range |
| Restore/stream/repair logs | Coverage transport và đồng bộ | Không thay logic kiểm dữ liệu bị DELETE nhầm |

Trong production RF=3 với `NetworkTopologyStrategy`, thay `ONE` của lab bằng CL phù hợp (thường `LOCAL_QUORUM` cho nghiệp vụ cần nhất quán) **theo hợp đồng ứng dụng**. Không hạ CL để làm báo cáo restore trông “đều PASS”.

**Đừng nhầm coordinator với replica:** kết nối Java tới IP của node P và chạy `CONSISTENCY ONE` không bảo đảm dữ liệu trả về được đọc **từ SSTable cục bộ của P**. Coordinator có thể chọn một natural replica khác. Muốn kiểm chính xác node P có file gì, dùng công cụ quan sát/đối soát node phù hợp và quy trình offline, không gọi một SELECT là “đọc riêng P”.

### 17.3. Kiểm timestamp đúng phạm vi

`WRITETIME(status)` cho timestamp của **cell sống**. Khi row bị tombstone che hoặc TTL hết hạn, CQL không hiển thị mọi phiên bản/tombstone lịch sử. Với restoration sau DELETE nhầm:

1. Kiểm nguồn audit xác nhận **DELETE nào là sai**.
2. Kiểm timestamp/version của mutation còn trên bản snapshot.
3. Xác nhận trong live target có tombstone mới hơn hay không qua timeline/log/SSTable inspection được phê duyệt.
4. Xây kế hoạch khôi phục chọn lọc theo business event, không chỉ dựa vào một lần `WRITETIME`.

### 17.4. Xác minh nhiều bảng denormalized

Giả sử ứng dụng có:

~~~text
orders_by_id            PK((tenant_id), order_id)
orders_by_customer_day  PK((customer_id, day), order_id)
orders_by_status_day    PK((status, day), order_id)
~~~

`sstableloader` nạp `orders_by_id` không tự sinh rows trong hai bảng còn lại. Nếu sự cố làm mất cả ba bảng, phải restore/backfill/đối soát **từng bảng** hoặc replay sự kiện nghiệp vụ qua pipeline có idempotency. Một phép kiểm GET /orders/{id} trả đúng không chứng minh trang danh sách theo khách hàng/trạng thái đã phục hồi.

## 18. Quan sát trong và sau restore

### 18.1. Các tín hiệu tối thiểu

| Tầng | Chỉ số/log | Dùng để |
|---|---|---|
| Loader | Kết nối, SSTable sections, bytes transferred, failed hosts, summary | Biết batch nào đã stream và còn lỗi |
| Ring/gossip | `nodetool status`, token ownership, node lifecycle | Phát hiện node rời/joining trong restore |
| Streaming | `nodetool netstats`, throughput, connection errors | Theo dõi target nhận dữ liệu |
| Storage | Disk free, Live/TotalSSTableCount, `tablestats`, compaction pending | Nhìn file và chi phí I/O sau load |
| Request | `ClientRequest.Read/Write.Latency`, timeouts/unavailables | Kiểm ảnh hưởng tới traffic hiện tại |
| JVM/OS | CPU, heap/GC, disk await, network bytes/s | Xác định bottleneck/cần throttle |
| Replica data | Repair logs, range coverage, sampled keys | Xem đồng bộ kỹ thuật |
| Business data | Audit event IDs, version, rows phải có/vắng, TTL | Xem tính đúng nghiệp vụ |
| Client Java | p95/p99, pool, retries, CL, local DC | Xác minh ứng dụng thực sự phục vụ được |

Mọi metric Cassandra cần gắn **cluster, DC, node, keyspace, table, UTC timestamp** và nhãn phương thức restore. Một con số `LiveSSTableCount` tăng chỉ xác nhận thêm file hoặc thay đổi compaction, **không chứng minh tất cả hàng đã có**.

### 18.2. Snapshot trước–sau đủ đồng dạng

~~~bash
# Trước và sau trên node nhận dữ liệu, ghi timestamp riêng.
nodetool status
nodetool netstats
nodetool tablestats restore_target.orders
nodetool compactionstats
nodetool tpstats
~~~

Trong ứng dụng đo:

- Query family chính, số QPS và latency p95/p99.
- Timeout/retry theo CL và datacenter.
- Số hàng/column trả về cho tập primary keys kiểm.
- Khác biệt giữa expected snapshot T0 và current source T1 được giải thích.
- Trạng thái của hàng đã DELETE hoặc TTL expired.

Khi bulk load lớn, compaction có thể tiếp tục sau khi loader đã hoàn thành. **Không vội tuyên bố tài nguyên đã ổn** nếu disk/SSTable/compaction backlog vẫn tăng và p99 vượt SLO.

### 18.3. Bảng nghiệm thu ba lớp

| Cổng | Bằng chứng | Kết quả |
|---|---|---|
| A — **File/transport** | Đủ source files và checksums; không lỗi loader/import; các batches hoàn tất | PASS/FAIL |
| B — **Placement/replica** | Đúng ring/partitioner/RF/DC; các token ranges và replicas mục tiêu đã đồng bộ | PASS/FAIL |
| C — **Dữ liệu/nghiệp vụ** | Sample + audit khớp; DELETE/TTL không hồi sinh; nhiều bảng đồng bộ | PASS/FAIL |
| D — **Sẵn sàng dịch vụ** | p95/p99, timeout, resource headroom, app Java hoạt động | PASS/FAIL |

Chỉ đánh dấu **`RESTORE_VALIDATED`** khi tất cả cổng phù hợp mục tiêu đã đạt, **kèm phạm vi và phương pháp sampling**. Nếu chỉ kiểm 30 keys, không gọi đó là “kiểm toán 100% dữ liệu”. Nên ghi explicit `COVERAGE=sampled` hoặc `COVERAGE=full` theo thực tế.

### 18.4. RPO/RTO thực tế phải tính cả validation

~~~text
RTO đo đến lúc ứng dụng phục vụ đúng:

T_restore =
  thời gian lấy backup
  + kiểm integrity/schema/format
  + staging/upgrade nếu cần
  + streaming/import
  + repair/compaction và warmup liên quan
  + kiểm đủ dữ liệu
  + chuyển traffic/feature flag
~~~

Lưu ý đây là **phân rã công việc**, không phải công thức cộng thời lượng chính xác khi một số bước có thể chạy song song. RTO cam kết phải được xác minh bằng **restore drill định kỳ**, không ước lượng từ “tốc độ copy file MB/s” đơn thuần.

## 19. Chẩn đoán lỗi thường gặp

### Ca 1 — Loader báo “initial hosts must be specified”

**Nguyên nhân:** `sstableloader` thiếu `--nodes`/`-d`.  
**Hành động:** Kiểm `sstableloader --help`, truyền hostname/IP của initial target hosts phù hợp; không đổi nguồn path sang live data directory để chữa lỗi này.

### Ca 2 — Kết nối được port 9042 nhưng streaming fail

**Khả năng:** Native CQL path đã thông, nhưng storage port, internode TLS, DNS/broadcast address, firewall hoặc credentials streaming chưa đúng.  
**Hành động:** Kiểm `-p` vs `-sp`/`-ssp`, `--conf-path`, logs và đường mạng tới **mọi receiver**, không chỉ initial host.

### Ca 3 — “No SSTables found” hoặc target table sai

**Khả năng:** Staging chỉ chứa thư mục `snapshots/tag` bên trong, sai cấp thư mục; parent path bị suy thành tên table/keyspace khác; file components thiếu.  
**Hành động:** Xác nhận `<staging>/<keyspace>/<table>/*-Data.db` và tất cả components, kiểm loader đã chọn target keyspace/table nào. Đừng sửa filename bằng tay.

### Ca 4 — “Incompatible SSTable version”

**Khả năng:** SSTable được tạo bởi binary/format mới hơn hoặc quá cũ, target loader không hỗ trợ; cũng có thể do component bị hỏng.  
**Hành động:** Giữ backup gốc, kiểm exact Cassandra/SSTable versions, thử `sstableupgrade` trên **copy offline** theo ma trận chính thức và staging validation; không thử đẩy file vào live table dir bằng `refresh` để vượt lỗi.

### Ca 5 — `nodetool import` báo token không thuộc node

**Khả năng:** File lấy từ ring/node khác, node đích không sở hữu những partition tokens đó.  
**Hành động:** Dừng, đối chiếu partitioner/ring/replica placement. Dùng `sstableloader` nếu cần phân phối lại; không bật `--no-tokens` theo phản xạ.

### Ca 6 — Loader SUCCESS nhưng `SELECT` trả 0 rows

Các khả năng chính:

1. Snapshot thiếu partition này; chỉ backup một node mà không đủ token coverage.
2. Query sai primary key hoặc target keyspace/table.
3. TTL đã hết hạn.
4. Tombstone/timestamp mới hơn trong bảng target che dữ liệu cũ.
5. Schema/UDT/column types không tương thích.
6. Read CL/DC có sự lệch replica hoặc streaming/repair chưa bao phủ.

**Hành động:** Kiểm source manifest/expected keys, timestamps, TTL/tombstone và readback từng DC. Không chạy lại loader vô hạn khi chưa biết nguyên nhân.

### Ca 7 — Row đã DELETE quay trở lại sau restore

**Khả năng:** SSTables cũ đã được nạp sau khi tombstone mới hơn bị purge; hoặc khôi phục sang bảng mới mà không áp lại deletion hợp lệ sau snapshot.  
**Hành động:** **Không đưa bảng phục hồi vào live traffic**, so audit DELETE và retention, replay các deletion/changes hợp lệ, sửa nguồn dữ liệu theo business event. Restore đúng file **không tương đương** restore đúng trạng thái pháp lý/nghiệp vụ.

### Ca 8 — Dữ liệu có ở dc1 nhưng dc2 thiếu

**Khả năng:** Chỉ test `LOCAL_QUORUM` ở dc1, loader không stream hết dc2 hoặc RF/DC config target sai.  
**Hành động:** Kiểm `DESCRIBE KEYSPACE`, ring, TLS/streaming logs và xác minh bằng client đặt local datacenter dc2 theo đúng runbook.

### Ca 9 — File copy thành công nhưng `nodetool refresh` không nạp

**Khả năng:** Sai table-ID directory, trùng filename, file chưa đủ components, token/format lỗi hoặc Cassandra chưa phát hiện bộ file.  
**Hành động:** Dừng copy trực tiếp, bảo toàn backup, kiểm logs và chuyển sang `nodetool import`/`sstableloader` nếu phù hợp. Không xóa live SSTables để ép nhận lại.

### Ca 10 — Data “đã khôi phục” nhưng ứng dụng Java vẫn lỗi

**Khả năng:** Schema agreement chưa xong, driver local DC/metadata chưa đúng, table/index/derived data thiếu, paging/CL mới không phù hợp, hoặc reads bị tombstone che.  
**Hành động:** Kiểm driver pool/CL, schema, RESTORE_VALIDATED gates và business checks theo các query families, không kết luận từ một câu cqlsh `SELECT *`.

### Ca 11 — Nhập SSTables nhiều nguồn bị mất file

**Khả năng:** Hai node nguồn có SSTable generations **trùng tên**, và quá trình copy vào một staging directory đã overwrite file trước đó.  
**Hành động:** Dùng staging **riêng theo node/source set**, checksums và manifest; so đủ file counts/token coverage trước khi loader. Không tự ghép component từ hai generation khác nhau.

### Ca 12 — Disk đầy trong lúc restore hoặc compaction sau restore

**Khả năng:** SSTables mới được stream/import, giữ snapshot hard links, compaction cần output tạm, backlog cao.  
**Hành động:** Dừng thêm batches, đánh giá disk headroom, throttle/repair/compaction theo runbook và mở rộng storage nếu cần. Không xóa file SSTable hoặc tombstone bằng tay.

## 20. Bảo mật và an toàn thao tác phục hồi

### 20.1. SSTable backup là dữ liệu nhạy cảm thực sự

SSTable snapshot chứa các giá trị của bảng, có thể bao gồm PII, thông tin giao dịch, tài khoản, token ứng dụng hoặc dữ liệu cần tuân thủ retention. Không vì nó là file `*.db` thay vì CSV mà coi an toàn để chia sẻ.

Thực hành tối thiểu:

- Dùng **encryption at rest/in transit**, phân quyền least privilege, kiểm quyền đọc key/truststore/keystore.
- Lưu backup **tách failure domain** với data node; kiểm checksum và restore drill.
- Không đưa password vào `sstableloader -pw <secret>` trong script/log tập trung nếu có cách cấu hình credential an toàn hơn; password trong process arguments có thể bị lộ.
- Không đưa đường dẫn có thông tin người dùng, giá trị CQL hoặc các sample PII vào hệ thống monitoring không được phép.
- Hạn chế quyền trên staging; không dùng mẫu `chmod 777` của ví dụ tài liệu như mặc định production.
- Áp dụng chính sách lưu và xóa staging **sau khi nghiệm thu**, có audit trail; không dọn snapshot gốc khi chưa chắc có backup độc lập.
- Nếu SSTable được mã hóa bằng key từ KMS/volume, xác minh **key còn truy cập được ở thời điểm restore**.

### 20.2. Tránh lộ dữ liệu khi restore sang cluster test

Nếu phải dựng cluster staging để xác minh backup production:

1. Dùng môi trường test có **kiểm soát mạng và tài khoản**.
2. Áp dụng masking/anonymization khi có thể mà vẫn bảo đảm tương thích data model.
3. Tách contact points và credentials giữa staging và production; tránh loader trỏ nhầm production.
4. Không cho Java service production tự phát hiện cluster test qua danh sách seeds/contact points.
5. Xác minh target keyspace/table đúng **trước** khi chạy loader, vì streaming vào bảng live không có undo tự động.
6. Định kỳ diễn tập cả khả năng **hủy/thu hồi quyền** truy cập backup sau hoàn tất.

### 20.3. Các thao tác đặc biệt nguy hiểm khi “khôi phục cho nhanh”

| Thao tác | Nguy cơ | Hướng an toàn hơn |
|---|---|---|
| `TRUNCATE` bảng live để bản backup cũ hiển thị | Xóa dữ liệu mới hợp lệ trên toàn bảng; có thể phá mốc RPO | Restore vào bảng cách ly, đối soát rồi replay chọn lọc |
| `DROP TABLE` rồi tạo lại khi chưa lưu schema/table ID | Mất dữ liệu/metadata hiện có và gây xung đột directory | Bảo toàn bản live, chốt DDL/ID, kế hoạch migration |
| `--no-tokens` trong import để ép file vào node | Sai replica placement | Đổi phương thức sang loader hoặc sửa source/target plan |
| `--no-verify`/`--quick` khi gặp file corruption | Bỏ qua bảo vệ, lan truyền dữ liệu lỗi | Xác minh file độc lập và tìm bản backup tốt |
| Copy raw SSTables vào live dir trong lúc engine/compaction chạy | Trùng tên, thiếu components, race, hỏng metadata | Staging + import hoặc loader |
| Bật `--keep-repaired` với file từ cluster khác | Metadata repair không phản ánh ring mới | Giữ mặc định bảo vệ, repair theo runbook |
| Cố đổi timestamp của toàn bộ snapshot thành tương lai | Che mọi mutation hợp lệ mới hơn | Khôi phục logic theo audit/version nghiệp vụ |
| Tắt SSL hoặc mở 7000/9042 cho cả Internet để stream | Rò dữ liệu và tăng attack surface | Network allowlist, TLS và staging network riêng |
| Xóa `gc_grace_seconds`/tombstones để “dọn nhanh” | Zombie data khi replica bỏ lỡ DELETE | Repair/retention runbook, theo dõi grace |

Không có một lệnh ngắn nào có thể thay thế việc xác định **mục tiêu dữ liệu cần phục hồi và bằng chứng nó đúng**.

## 21. Checklist trước, trong và sau restore

### 21.1. Trước restore

- [ ] Đã xác định mục tiêu (bảng/khóa/DC/cluster), RPO/RTO và nguồn nghiệp vụ.
- [ ] Đã phân biệt lỗi node, lỗi replica và lỗi dữ liệu logic.
- [ ] Đã chọn `sstableloader` hay `nodetool import` theo **topology và phạm vi**.
- [ ] Có backup **độc lập**, checksum, manifest, đầy đủ SSTable components/generations.
- [ ] Đã kiểm source token-range coverage theo node/replica; không dựa vào một snapshot node.
- [ ] Có snapshot DDL/UDT/index/schema và kiểm table ID.
- [ ] Cassandra/SSTable format, partitioner và compression/encryption tương thích target.
- [ ] Keyspace đích, RF theo DC và natural replica placement đã xác minh.
- [ ] Ring đích ổn định, không ở giữa bootstrap/decommission/replace chưa xong.
- [ ] Disk/network/CPU/GC/compaction còn headroom cho streaming.
- [ ] Client credentials, TLS/ports, staging path, access permissions đã thử.
- [ ] Có ma trận keys **phải có** và **phải vắng** sau restore (DELETE/TTL).
- [ ] Đã đánh giá snapshot age so với tombstone `gc_grace_seconds` và retention.
- [ ] Đã có phương án staging/restore **không phá live table** trước khi chuyển traffic.
- [ ] Có owner/on-call, cửa sổ bảo trì, ngưỡng dừng, rollback/escalation.

### 21.2. Trong restore

- [ ] Loader/import đang trỏ đúng target cluster, keyspace/table và node.
- [ ] Đã chụp log phiên làm việc, batch IDs, source sets và timestamp UTC.
- [ ] Không nạp lại batch đã hoàn tất khi chưa biết hậu quả nạp trùng.
- [ ] Theo dõi streaming progress/error theo node/DC; không chỉ tổng bytes.
- [ ] Theo dõi disk free/await, network, compaction, read/write p95/p99 và errors.
- [ ] Không đổi đồng thời RF/schema/topology/CL nếu không có kế hoạch phụ thuộc.
- [ ] Nếu nhập local, không dùng `--no-tokens`/`--no-verify` chỉ để bỏ lỗi.
- [ ] Khi có tombstone/TTL/schema mismatch, dừng và điều tra trước khi nạp thêm.
- [ ] Staging/backup gốc vẫn giữ nguyên cho tới khi toàn bộ cổng kiểm chứng đạt.

### 21.3. Sau restore

- [ ] Source-file integrity, số batch, token range coverage, loader/import exit status đã xác nhận.
- [ ] Keyspace/table/partitioner/RF/DC khớp với thiết kế đích.
- [ ] Những node/replica mong muốn đã nhận dữ liệu và cần repair đã được xử lý.
- [ ] Kiểm qua CQL với CL phù hợp ở mọi DC trong phạm vi, không chỉ `ONE`.
- [ ] Có kiểm primary keys, các cột, `WRITETIME` khi phù hợp, version nghiệp vụ.
- [ ] Có kiểm **DELETE/TTL không tái xuất** và dữ liệu mới sau snapshot không bị ghi đè.
- [ ] Các bảng denormalized/index/views liên quan được đối chiếu/rebuild nếu cần.
- [ ] Driver Java đã kết nối đúng local DC, p95/p99 và timeout trong SLO.
- [ ] Compaction, disk/GC và network đã về trạng thái chấp nhận được sau load.
- [ ] Phạm vi kiểm là toàn bộ hay sampling được công bố chính xác.
- [ ] Đã ghi RPO thực, RTO thực, nguồn log/metrics, residual risks và lịch follow-up.
- [ ] Chỉ dọn staging sau khi đủ bằng chứng và retention policy cho phép.

## 22. Câu hỏi tự đánh giá

**Câu 1.** Khi restore từ cluster ba node sang cluster năm node với cùng RF=3, vì sao nên chọn `sstableloader` thay vì chép file A→P, B→Q, C→R?  
**Định hướng:** Token ownership của ring đích đã đổi; loader stream theo natural replicas mới, direct copy một-một có thể đặt sai ranges.

**Câu 2.** Vì sao file `Data.db` riêng lẻ thường không phải một backup SSTable đầy đủ?  
**Định hướng:** SSTable có nhiều components/metadata/digest với cùng generation, phụ thuộc format.

**Câu 3.** Một snapshot được chụp bằng hard links trên cùng ổ đĩa nguồn có phải backup chịu được mất ổ không?  
**Định hướng:** Không. Cần copy độc lập sang vùng lưu trữ khác với kiểm checksum.

**Câu 4.** Vì sao nhiều lần `nodetool snapshot` liên tiếp trên các node không tạo ra atomic snapshot toàn cluster?  
**Định hướng:** Mỗi node có mốc flush/snapshot khác nhau; writes/replication có thể diễn ra giữa các mốc.

**Câu 5.** `sstableloader --nodes 10.0.0.11` có stream **tất cả dữ liệu vào node 10.0.0.11** không?  
**Định hướng:** Không. Đó là initial host để lấy ring; loader stream từng phần đến endpoints theo replication đích.

**Câu 6.** Tại sao cần directory dạng `/staging/shop/orders` cho `sstableloader`?  
**Định hướng:** Loader mặc định suy keyspace/table từ parent directories.

**Câu 7.** Điều gì xảy ra nếu port 9042 thông nhưng port streaming storage bị chặn?  
**Định hướng:** Có thể kết nối ban đầu nhưng streaming tới target replicas thất bại.

**Câu 8.** Vì sao `nodetool import` trên một node không tương đương restore toàn cluster?  
**Định hướng:** Nạp file cục bộ; không tự phân phối tất cả ranges đến các natural replicas.

**Câu 9.** `nodetool import --no-tokens` có phải giải pháp đúng khi báo token không thuộc node?  
**Định hướng:** Không mặc định; phải kiểm partitioner/ring/ownership hoặc dùng loader.

**Câu 10.** Nếu target table bị DROP/CREATE lại với cùng tên, vì sao copy SSTables vào directory UUID cũ có thể vô tác dụng?  
**Định hướng:** Table ID instance mới khác; live directory phải khớp table hiện tại.

**Câu 11.** Source SSTable được tạo ở phiên bản mới hơn reader đích. Có thể dùng `nodetool refresh` để bỏ qua lỗi compatibility không?  
**Định hướng:** Không; phải chọn reader/upgrade path được hỗ trợ, thử trên copy offline.

**Câu 12.** Backup giữ `status=PAID, ts=100`; target có tombstone `ts=200`. Loader thành công thì SELECT trả PAID ngay không?  
**Định hướng:** Không; tombstone mới hơn che giá trị cũ.

**Câu 13.** Tại sao row có TTL 1 giờ snapshot lúc 10:10 không tự sống thêm một giờ khi restore lúc 12:00?  
**Định hướng:** Expiration metadata dựa trên thời điểm ghi, không reset theo restore.

**Câu 14.** Nếu tombstone đã purge và backup cũ đưa dữ liệu đã DELETE trở lại, đó là nguy cơ gì?  
**Định hướng:** Zombie data; cần audit DELETE và chính sách không tái xuất.

**Câu 15.** `WRITETIME(status)` có cho biết mọi DELETE/TTL tombstone lịch sử không?  
**Định hướng:** Không; chỉ timestamp của cell sống trong kết quả được đọc.

**Câu 16.** Một snapshot node nguồn thiếu một số token ranges, nhưng `COUNT(*)` ở target bằng số mong đợi. Có đủ để tuyên bố restore thành công không?  
**Định hướng:** Không; cùng count có thể khác khóa/giá trị, phải kiểm coverage và audit.

**Câu 17.** Tại sao `LOCAL_QUORUM` thành công ở dc1 không chứng minh dc2 đã restore?  
**Định hướng:** Local quorum chỉ xét replica trong local DC.

**Câu 18.** `sstableloader` nạp `orders_by_id` có tự điền `orders_by_customer_day` không?  
**Định hướng:** Không; hai bảng có mutation và replica riêng, cần restore/backfill/replay.

**Câu 19.** Vì sao nên restore vào keyspace mới trước khi phục hồi một DELETE nhầm trên live table?  
**Định hướng:** Tránh trộn backup timestamp cũ với live tombstone/new writes, cho phép kiểm nguồn sự thật.

**Câu 20.** Với một node vừa mất disk nhưng các replica còn dữ liệu tốt, có phải luôn dùng local file import không?  
**Định hướng:** Không; replace/rebuild từ replica còn tốt thường là lựa chọn cần xét trước theo topology.

**Câu 21.** Lệnh loader trả thành công và một SELECT ONE có dữ liệu. Có thể đánh dấu restore hoàn tất chưa?  
**Định hướng:** Chưa; cần token/replica/DC coverage, correctness và SLA.

**Câu 22.** Nếu `sstableloader` đã stream vào live table và sau đó phát hiện dữ liệu sai, có lệnh undo tự động không?  
**Định hướng:** Không. Phải có phương án khôi phục logic/rollback được thiết kế từ đầu, tốt nhất dùng bảng cách ly.

## 23. Tổng kết

~~~text
                BACKUP / SNAPSHOT / INCREMENTS
                             |
             Kiểm manifest + checksum + schema
                             |
          Đối chiếu VERSION + SSTable format + ID
                             |
          Đối chiếu PARTITIONER + RING + RF/DC
                             |
          Chọn phương thức theo phạm vi/topology
                   /                   \
             sstableloader          nodetool import
                   |                   |
             STREAM theo             LOCAL file
             replicas đích           trên đúng node
                   \                   /
                    \                 /
                     TRANSPORT / FILE PASS
                             |
                     REPLICA COVERAGE
                             |
                TTL / tombstone / timestamp
                             |
                  BUSINESS AUDIT / SLO
                             |
                   RESTORE_VALIDATED
                             |
                 Chỉ mới chuyển live traffic
~~~

**Thông điệp quan trọng nhất:** `sstableloader` giúp đưa SSTable đến **natural replicas của topology đích**; `nodetool import`/legacy `refresh` xử lý **file cục bộ trên từng node**. Không công cụ nào tự biết dữ liệu **đúng nghiệp vụ**, tự khôi phục tombstone đã purge hoặc biến snapshot một node thành backup toàn cluster. Restore đáng tin cậy phải được thiết kế như một **quy trình có mốc thời gian, schema/format compatibility, token/RF/DC coverage, kiểm TTL/timestamp/tombstone và nghiệm thu từ ứng dụng Java**.

## Tài liệu tham khảo

- [Apache Cassandra — Backups](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/backups.html) — snapshot, incremental backup, hard links, `schema.cql` và khái niệm restore.
- [Apache Cassandra — Bulk Loading](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/bulk_loading.html) — `sstableloader`, `nodetool import`, target keyspace, source directory và streaming.
- [Apache Cassandra — sstableloader](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstableloader.html) — `--nodes`, `--throttle-mib`, TLS/auth, port và yêu cầu nguồn SSTable ổn định.
- [Apache Cassandra — nodetool import](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/import.html) — import SSTable từ directory bất kỳ, kiểm token/verify và repaired metadata.
- [Apache Cassandra — nodetool refresh](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/refresh.html) — legacy load newly placed SSTables vào table không restart.
- [Apache Cassandra — nodetool snapshot](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/snapshot.html) — tạo snapshot, `--skip-flush` và giới hạn node-local.
- [Apache Cassandra — sstableupgrade](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstableupgrade.html) — chuyển format SSTable/snapshot theo phiên bản Cassandra, lưu ý offline và hard links.
- [Apache Cassandra — nodetool upgradesstables](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/upgradesstables.html) — nâng format SSTables đang được quản lý trên node theo runbook.
- [Apache Cassandra — Storage Engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — commit log, memtable, SSTable, compaction và đường ghi.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — ring/token, replication, consistency, coordinator và hinted handoff.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — anti-entropy, tombstones và đồng bộ replica.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — grace period, tombstone GC và zombie data.
- [DataStax Java Driver 4.17 — CqlSession API](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/CqlSession.html) — truy vấn CQL từ Java và metadata/session.
- [DataStax Java Driver 4.17 — Consistency levels](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/consistency/) — thiết lập CL cho statement và phạm vi kiểm chứng.

