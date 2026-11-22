# IF NOT EXISTS, IF EXISTS và điều kiện trên giá trị

## 1. Mục tiêu và vị trí của bài học

Trong Apache Cassandra, `INSERT` và `UPDATE` thường là **upsert**: chúng có thể tạo mới hoặc thay đổi row mà không cần kiểm tra xem row đã tồn tại. Cách đó phù hợp với workload ghi lớn của mô hình **wide-column**, nhưng có thể vi phạm quy tắc nghiệp vụ khi nhiều client cùng tranh một khóa. Ví dụ: hai người cùng đăng ký username, hai request cùng giữ một chỗ, hay hai thread cùng cập nhật phiên bản tài liệu.

Bài này thuộc chương **LWT và đồng thời** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Trọng tâm là ba dạng điều kiện CQL thực tế: **`INSERT ... IF NOT EXISTS`**, **`UPDATE/DELETE ... IF EXISTS`**, và **`UPDATE/DELETE ... IF column = value [AND ...]`**. Các câu lệnh này sử dụng **lightweight transaction (LWT)** dựa trên Paxos để kiểm tra điều kiện và quyết định mutation ở phạm vi phù hợp.

Sau khi học xong, bạn có thể:

1. Chọn đúng giữa **tạo nếu chưa có**, **thay đổi nếu row tồn tại**, và **thay đổi nếu trạng thái/revision còn đúng**.
2. Đọc kết quả `[applied]=True/False` và phân biệt với timeout hay lỗi chưa xác định kết quả.
3. Thiết kế **partition key** theo quy tắc unique/ownership; hiểu vì sao LWT không tạo unique constraint trên cột bất kỳ.
4. Thực hành **hai phiên cqlsh cạnh tranh**, so sánh `IF EXISTS` với `IF revision = ...`.
5. Sử dụng nhiều điều kiện `AND`, phân biệt phần `WHERE` xác định row với phần `IF` kiểm tra dữ liệu.
6. Dùng Apache Cassandra Java Driver với prepared statement, `ResultSet.wasApplied()`, consistency level và serial consistency.
7. Nhận biết những giới hạn quan trọng: một partition, NULL, TTL, tombstone, counter, batch, timestamps, retry và hiệu năng Paxos.
8. Giải thích liên hệ giữa LWT, replication factor, `LOCAL_QUORUM`, `SERIAL/LOCAL_SERIAL`, repair và kết nối từ ứng dụng Java.

> **Điều kiện thực hành:** ví dụ chính dùng **Cassandra 5.0.9 trên một node Docker riêng** để minh họa cú pháp và race giữa client. Một node **không kiểm thử được chịu lỗi replica**; kết luận về quorum RF=3 chỉ đúng khi có ba node thực sự thuộc ring. Không thực hiện các lệnh xóa dữ liệu của bài trên hệ thống production.

## 2. Bảng quyết định: chọn IF nào?

| Yêu cầu | Câu lệnh CQL | Khi điều kiện đúng | Khi điều kiện sai |
|---|---|---|---|
| Chỉ tạo khi **primary key chưa có row** | `INSERT ... IF NOT EXISTS` | Tạo row, `[applied]=true` | Không ghi row mới, `[applied]=false` |
| Chỉ cập nhật khi **row đã tồn tại** | `UPDATE ... IF EXISTS` | Cập nhật dù nội dung row hiện là gì | Không upsert row vắng mặt |
| Chỉ xóa khi **row đã tồn tại** | `DELETE ... IF EXISTS` | Ghi mutation xóa row | Không xóa row vắng mặt |
| Chỉ đổi khi **revision còn như đã đọc** | `UPDATE ... IF revision=7` | Đổi trạng thái và revision trong một conditional mutation | Không ghi, trả `false` |
| Chỉ đổi khi **nhiều giá trị cùng đúng** | `UPDATE ... IF state='FREE' AND revision=1` | Tất cả điều kiện phải đúng | Chỉ một điều kiện sai cũng từ chối |
| Chỉ xóa nếu **đúng chủ sở hữu** | `DELETE ... IF owner_id='alice'` | Chỉ xóa khi owner phù hợp | Không xóa dữ liệu của owner khác |

Điểm dễ nhầm nhất: **`IF EXISTS` không có nghĩa “nếu row vẫn còn ở trạng thái tôi muốn”**. Nó chỉ kiểm tra sự tồn tại. Nếu cả A và B đều cập nhật **cùng một row đang tồn tại** bằng `IF EXISTS`, cả hai mutation vẫn có thể được chấp thuận. Muốn tránh lost update, phải **so giá trị/version**.

### 2.1. Ba mẫu cú pháp chuẩn

```sql
-- INSERT: chỉ có kiểu điều kiện row chưa tồn tại.
INSERT INTO lwt002.claims
  (tenant_id, handle, owner_id, request_id, revision, state)
VALUES
  ('tenant-a', 'skyblue', 'alice',
   20000000-0000-4000-8000-000000000001, 1, 'ACTIVE')
IF NOT EXISTS;

-- UPDATE: chỉ đòi hỏi row tồn tại.
UPDATE lwt002.seats
SET holder_id='alice', state='RESERVED'
WHERE tenant_id='tenant-a' AND seat_id='seat-001'
IF EXISTS;

-- UPDATE: đòi hỏi trạng thái/version của row.
UPDATE lwt002.seats
SET holder_id='alice', state='RESERVED', revision=2
WHERE tenant_id='tenant-a' AND seat_id='seat-001'
IF state='FREE' AND revision=1;
```

Đây là các câu lệnh **minh họa**, chưa cần chạy cho tới khi tạo keyspace/schema và dữ liệu đầu vào ở các mục sau. Tên bảng/khóa được chọn để các phép thử có thể tái lập.

### 2.2. Không nhầm IF của schema với IF của mutation

Ví dụ cú pháp DDL là `CREATE TABLE IF NOT EXISTS ...`, trong đó `...` chỉ là ký hiệu mô tả chứ **không phải một câu lệnh hoàn chỉnh để chạy**. Lệnh tạo bảng thực tế đã được viết đầy đủ ở mục 4.3.

`CREATE TABLE IF NOT EXISTS` là **cú pháp DDL**: tránh báo lỗi nếu bảng đã có, nhưng **không chạy Paxos LWT để kiểm tra row**. Nó không xác minh một bảng tồn tại có đúng primary key/compaction/schema mong muốn. Ngược lại, `INSERT ... IF NOT EXISTS` trên row dữ liệu là **conditional mutation** có kết quả `[applied]`.

## 3. Những khái niệm nền tảng phải giữ đúng

### 3.1. WHERE và IF làm hai công việc khác nhau

```sql
UPDATE lwt002.seats
SET holder_id='alice', state='RESERVED', revision=2
WHERE tenant_id='tenant-a' AND seat_id='seat-002'
IF state='FREE' AND revision=1;
```

Trong câu lệnh này:

- `WHERE tenant_id=... AND seat_id=...` xác định **đúng row** qua primary key.
- `IF state='FREE' AND revision=1` kiểm tra **giá trị của row đó** ở thời điểm CAS quyết định.
- `SET ...` là mutation **chỉ được áp dụng nếu điều kiện được thỏa**.
- Không có bước SELECT riêng nào của Java bảo đảm trạng thái vẫn giữ nguyên giữa lần đọc và lần ghi. Việc kiểm tra phải nằm trong câu CQL conditional.

Với một partition key tổng hợp như `PRIMARY KEY ((tenant_id, seat_id))`, cả hai thành phần phải có trong `WHERE` để định vị partition. Điều kiện IF không thay thế phần khóa còn thiếu. Những cột cần kiểm tra bằng IF là **các cột dữ liệu không thuộc primary key**; primary key dùng để định danh row.

### 3.2. Tư duy CAS thay cho SELECT rồi UPDATE

```mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant C as Cassandra/Paxos
    A->>C: UPDATE K SET owner=A IF revision=1
    B->>C: UPDATE K SET owner=B IF revision=1
    C-->>A: [applied]=true
    C-->>B: [applied]=false (revision đã đổi)
    Note over A,B: Kết quả ví dụ; thứ tự thắng có thể đảo
```

Không có giả định rằng Client A luôn thắng. Nếu B được quyết định trước, **B có thể là client nhận true**. Tính chất cần kiểm chứng là hai conditional mutation trái nhau **không cùng thắng** một điều kiện revision chỉ có hiệu lực một lần, khi không có writer ngoài giao thức phá trạng thái.

### 3.3. Khóa phân vùng quyết định phạm vi bảo đảm

Ví dụ quy tắc: trong mỗi tenant, một handle chỉ được một owner sử dụng. Thiết kế:

```sql
PRIMARY KEY ((tenant_id, handle))
```

Mỗi cặp `tenant_id/handle` được kiểm tra trên cùng partition. Nếu lại tạo bảng theo `PRIMARY KEY (owner_id)` và để `handle` là cột thường, hai owner khác nhau có thể chạy `IF NOT EXISTS` ở **hai partition khác nhau** và cả hai được chấp thuận; invariant “handle duy nhất” vẫn bị vi phạm.

**LWT không tự sinh unique index xuyên mọi partition hoặc mọi bảng.** Các dữ liệu liên quan phải được mô hình hóa theo invariant và đường truy vấn cụ thể. Với quota tổng tenant, transaction đa partition, hay side effect trên dịch vụ ngoài Cassandra, cần thiết kế bổ sung.

## 4. Chuẩn bị môi trường thực hành

### 4.1. Khởi động Cassandra một node riêng

Yêu cầu Docker Engine/Desktop ở chế độ Linux containers, host có đủ CPU/SSD và RAM cấp cho Cassandra. Một máy có khoảng **8 GiB RAM tổng trở lên**, cho container 4 GiB và JVM heap 2 GiB, phù hợp bài học nhỏ; không phải đề xuất cấu hình production. Cổng host `9328` phải chưa được sử dụng.

Chạy **trên terminal host có Docker CLI**:

```bash
docker version
docker pull cassandra:5.0.9
docker network create lwt002-net
docker volume create lwt002_node_data

docker run -d --name cassandra-lwt002 --network lwt002-net --memory=4g --memory-swap=4g -e MAX_HEAP_SIZE=2G -e CASSANDRA_CLUSTER_NAME=lwt002-lab -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch -e CASSANDRA_DC=dc1 -e CASSANDRA_RACK=rack1 -p 127.0.0.1:9328:9042 -v lwt002_node_data:/var/lib/cassandra cassandra:5.0.9
```

Các tên container/network/volume được chọn riêng cho bài. Nếu chúng đã tồn tại, **xác minh chủ sở hữu và dữ liệu trước khi tiếp tục**; không xóa hoặc dùng lại dữ liệu của lab khác. Mỗi Cassandra node phải có volume riêng.

Port `9328` chỉ được publish trên **loopback host** vì ví dụ chưa bật authentication/TLS. Không thay bằng `0.0.0.0:9328:9042` trên máy có người khác truy cập. Từ **bên trong container**, CQL vẫn dùng port `9042`.

### 4.2. Chờ Cassandra sẵn sàng

```bash
docker ps -a --filter name=cassandra-lwt002
docker logs --tail 100 cassandra-lwt002
docker exec cassandra-lwt002 nodetool status
docker exec cassandra-lwt002 nodetool statusbinary
docker exec cassandra-lwt002 cqlsh -e "SELECT cluster_name, data_center, release_version FROM system.local WHERE key='local';"
```

Chỉ chuyển bước khi:

1. `nodetool status` có một node `UN` (*Up/Normal*).
2. `nodetool statusbinary` trả `running`.
3. CQL báo `cluster_name=lwt002-lab`, `data_center=dc1` và server `5.0.9`.

Container `Up` không nhất thiết Cassandra đã mở native transport. Nếu câu lệnh lỗi trong lúc bootstrap, đọc log rồi kiểm tra lại; không xóa volume để “chữa” startup chậm.

### 4.3. Keyspace và hai bảng theo đúng invariant

Mở cqlsh:

```bash
docker exec -it cassandra-lwt002 cqlsh
```

Trong `cqlsh>` chạy:

```sql
CREATE KEYSPACE IF NOT EXISTS lwt002
WITH replication = {'class':'NetworkTopologyStrategy', 'dc1':1};

-- Bảng 1: chỉ một owner cho mỗi (tenant, handle).
CREATE TABLE IF NOT EXISTS lwt002.claims (
    tenant_id text,
    handle text,
    owner_id text,
    request_id uuid,
    revision int,
    state text,
    PRIMARY KEY ((tenant_id, handle))
);

-- Bảng 2: trạng thái đặt chỗ và phiên bản theo một seat.
CREATE TABLE IF NOT EXISTS lwt002.seats (
    tenant_id text,
    seat_id text,
    holder_id text,
    state text,
    revision int,
    request_id uuid,
    PRIMARY KEY ((tenant_id, seat_id))
);

DESCRIBE KEYSPACE lwt002;
DESCRIBE TABLE lwt002.claims;
DESCRIBE TABLE lwt002.seats;
```

Nếu keyspace/bảng đã tồn tại, `IF NOT EXISTS` có thể **không thay đổi schema**. Hãy `DESCRIBE` để đối chiếu primary key. Lab dùng `RF=1` vì chỉ có một node; trên cluster thật phải chọn RF theo topology và các CL theo yêu cầu.

### 4.4. Chọn regular và serial consistency trong cqlsh

Ở mỗi phiên cqlsh sẽ dùng để thử LWT, thiết lập:

```text
CONSISTENCY LOCAL_QUORUM;
SERIAL CONSISTENCY SERIAL;
```

Đây là **lệnh riêng của cqlsh**, không phải statement CQL gửi từ Java Driver. `LOCAL_QUORUM` với RF=1 chỉ yêu cầu một replica; `SERIAL` quy định phạm vi serial/Paxos cho conditional mutation. Nếu bài mở rộng sang RF=3 tại cùng DC, `LOCAL_QUORUM` khi đó cần 2/3 phản hồi.

## 5. IF NOT EXISTS: chỉ claim khi row chưa tồn tại

### 5.1. Lần đầu được phép tạo

Trên bảng `lwt002.claims`, chọn cặp khóa chưa tồn tại:

```sql
INSERT INTO lwt002.claims
    (tenant_id, handle, owner_id, request_id, revision, state)
VALUES
    ('tenant-a', 'skyblue-002', 'alice',
     20000000-0000-4000-8000-000000000011, 1, 'ACTIVE')
IF NOT EXISTS;
```

Khi lab sạch, cqlsh thường hiển thị:

```text
 [applied]
-----------
      True
```

Đọc lại row:

```sql
SELECT tenant_id, handle, owner_id, request_id, revision, state
FROM lwt002.claims
WHERE tenant_id='tenant-a' AND handle='skyblue-002';
```

Kỳ vọng owner là `alice`, revision=1. Kết quả `True` nghĩa **điều kiện tồn tại được chấp thuận và mutation đã được áp dụng theo semantics LWT/CL**; nó không phải chứng nhận backup, repair hay dữ liệu đã có ở những node không tồn tại.

### 5.2. Client khác dùng cùng khóa phải bị từ chối

Mở **phiên cqlsh thứ hai**:

```bash
docker exec -it cassandra-lwt002 cqlsh
```

Thiết lập `CONSISTENCY LOCAL_QUORUM;` và `SERIAL CONSISTENCY SERIAL;` trong phiên mới. Rồi chạy:

```sql
INSERT INTO lwt002.claims
    (tenant_id, handle, owner_id, request_id, revision, state)
VALUES
    ('tenant-a', 'skyblue-002', 'bob',
     20000000-0000-4000-8000-000000000012, 1, 'ACTIVE')
IF NOT EXISTS;
```

Kỳ vọng `[applied]=False`. Tùy câu lệnh và bản Cassandra, kết quả không được áp dụng có thể gồm **một số cột/giá trị hiện tại** của row. Không phụ thuộc vào đúng định dạng hay thứ tự của các cột đó; cần SELECT lại bằng primary key khi chuẩn bị quyết định nghiệp vụ.

```sql
SELECT owner_id, request_id, state
FROM lwt002.claims
WHERE tenant_id='tenant-a' AND handle='skyblue-002';
```

Với dữ liệu lab chưa có writer khác, owner vẫn là `alice`. `False` là **xung đột nghiệp vụ**, khác với `WriteTimeout`/`Unavailable` hoặc lỗi mạng.

### 5.3. Thay tenant tức là thay uniqueness scope

```sql
INSERT INTO lwt002.claims
    (tenant_id, handle, owner_id, request_id, revision, state)
VALUES
    ('tenant-b', 'skyblue-002', 'bob',
     20000000-0000-4000-8000-000000000013, 1, 'ACTIVE')
IF NOT EXISTS;
```

Đây là **partition khác**, nên có thể trả `True`. Nếu nghiệp vụ yêu cầu handle unique trên **toàn hệ thống**, table schema/khóa trên không phù hợp. Thay điều kiện IF không sửa được invariant bị đặt sai ở primary key.

### 5.4. Hai client thực sự gửi đồng thời

Trong bài học hai cửa sổ tuần tự, A cố tình gửi trước B nên kết quả dự kiến đã biết. Khi hai client thực sự cùng gửi `INSERT ... IF NOT EXISTS` tới cùng **một khóa mới**, **một** request có thể nhận `True` và request còn lại `False` nếu cả hai hoàn tất bình thường và không có DELETE/xóa theo TTL xen giữa.

Không đảm bảo Alice hay Bob luôn là người thắng. Số lượng **`True`** quan trọng hơn tên client. Nếu một request timeout, nó có thể đã commit dù client không nhận response; **không** cộng timeout như `False` rồi kết luận chỉ có một phía ghi.

### 5.5. Idempotency của claim và request_id

Trong ứng dụng, nên sinh `request_id` trước lần gửi đầu, giữ nguyên qua retry và lưu nó cùng owner. Nếu lần đầu commit nhưng response bị mất, retry có thể nhận `False` vì **row của chính request đó đã có**. Khi này:

- Đọc theo khóa `tenant_id/handle`.
- So `owner_id` và `request_id` với request gốc.
- Nếu trùng, có thể coi là **yêu cầu của mình đã được áp dụng trước đó**, theo quy tắc nghiệp vụ đã thiết kế.
- Nếu khác, trả **conflict**.
- Nếu chưa xác nhận được do lỗi mạng/consistency, giữ trạng thái **UNKNOWN**, không tự động chấp thuận hay từ chối vĩnh viễn.

Nếu handle có thể được **xóa và tái cấp** trong lúc retry, chỉ request ID có thể chưa đủ. Cần thêm generation/lease/fencing hoặc quy tắc giữ tombstone logic để tránh **ABA**.

## 6. IF EXISTS: chỉ bảo vệ sự tồn tại, không bảo vệ giá trị

### 6.1. UPDATE IF EXISTS với row chưa được tạo

Trên một seat mới `seat-exists-002`:

```sql
UPDATE lwt002.seats
SET holder_id='alice', state='RESERVED', revision=2
WHERE tenant_id='tenant-a' AND seat_id='seat-exists-002'
IF EXISTS;
```

Khi row chưa tồn tại, kết quả là `[applied]=False`. Không có row mới được tạo. Khác với `UPDATE` thường, conditional `IF EXISTS` **không tự upsert row thiếu**.

### 6.2. Tạo dữ liệu fixture và thử lại

```sql
INSERT INTO lwt002.seats
    (tenant_id, seat_id, holder_id, state, revision, request_id)
VALUES
    ('tenant-a', 'seat-exists-002', 'unassigned', 'FREE', 1,
     20000000-0000-4000-8000-000000000021);

UPDATE lwt002.seats
SET holder_id='alice', state='RESERVED', revision=2
WHERE tenant_id='tenant-a' AND seat_id='seat-exists-002'
IF EXISTS;
```

Vì row đã tồn tại, `IF EXISTS` có thể trả `True`. Nhưng câu lệnh **không kiểm tra `state='FREE'` hoặc `revision=1`**.

### 6.3. Vì sao IF EXISTS vẫn có thể gây lost update?

Ngay khi A chuyển seat thành `RESERVED`, Client B gửi:

```sql
UPDATE lwt002.seats
SET holder_id='bob', state='RESERVED', revision=2
WHERE tenant_id='tenant-a' AND seat_id='seat-exists-002'
IF EXISTS;
```

Row vẫn tồn tại, nên B **cũng có thể nhận `True`**, dù Alice vừa đặt chỗ. Khi đọc kết quả:

```sql
SELECT seat_id, holder_id, state, revision
FROM lwt002.seats
WHERE tenant_id='tenant-a' AND seat_id='seat-exists-002';
```

Trong thử nghiệm tuần tự cô lập, giá trị ghi sau thường được thấy theo quy tắc mutation timestamp Cassandra, nhưng **không dựa vào thứ tự A/B tuyệt đối để chứng minh invariant**. Điểm cần chứng minh là **hai lần `IF EXISTS` đều có thể được áp dụng**. Đây là trường hợp dùng IF sai mục tiêu: nó chỉ bảo vệ *có row* chứ không bảo vệ *chưa có ai đặt chỗ*.

| Mong muốn nghiệp vụ | `IF EXISTS` có bảo đảm không? | Điều kiện phù hợp hơn |
|---|---|---|
| Không tạo seat vô tình nếu chưa khởi tạo | **Có** | `IF EXISTS` |
| Chỉ đặt seat đang FREE | **Không** | `IF state='FREE'` |
| Tránh ghi đè revision vừa được người khác tăng | **Không** | `IF revision=<expected>` |
| Chỉ cho đúng holder xác nhận seat | **Không** | `IF holder_id=<expected> AND state='RESERVED'` |

### 6.4. DELETE IF EXISTS

Để thử **xóa có điều kiện tồn tại** mà không ảnh hưởng seat khác, tạo row riêng:

```sql
INSERT INTO lwt002.seats
    (tenant_id, seat_id, holder_id, state, revision)
VALUES
    ('tenant-a', 'seat-delete-002', 'alice', 'RESERVED', 1);

DELETE FROM lwt002.seats
WHERE tenant_id='tenant-a' AND seat_id='seat-delete-002'
IF EXISTS;

DELETE FROM lwt002.seats
WHERE tenant_id='tenant-a' AND seat_id='seat-delete-002'
IF EXISTS;
```

Lần DELETE đầu kỳ vọng `True`, lần thứ hai `False` vì row đã vắng mặt. Nhưng `IF EXISTS` **không hỏi ai là owner**: một client có quyền ghi phù hợp vẫn có thể xóa row của người khác nếu ứng dụng chỉ dùng điều kiện tồn tại.

**Lưu ý về tombstone:** Cassandra dùng tombstone để biểu diễn xóa, nên “row biến mất khỏi SELECT” không có nghĩa SSTable/đĩa đã lập tức được giải phóng. Không lặp DELETE hàng loạt để kiểm tra dung lượng; theo dõi compaction/repair và `gc_grace_seconds` theo runbook vận hành.

## 7. IF trên giá trị: state và revision

### 7.1. Tạo seat dùng riêng cho compare-and-set

Không sử dụng lại `seat-exists-002` vừa minh họa sai. Tạo row mới:

```sql
INSERT INTO lwt002.seats
    (tenant_id, seat_id, holder_id, state, revision, request_id)
VALUES
    ('tenant-a', 'seat-cas-002', 'unassigned', 'FREE', 1,
     20000000-0000-4000-8000-000000000031);

SELECT holder_id, state, revision
FROM lwt002.seats
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002';
```

Kỳ vọng ban đầu là `unassigned / FREE / 1`. Nếu row đã có và trạng thái khác, không giả định fixture sạch; chọn khóa mới hoặc xác minh volume lab.

### 7.2. A thử giữ chỗ nếu cả hai điều kiện còn đúng

```sql
UPDATE lwt002.seats
SET holder_id='alice',
    state='RESERVED',
    revision=2,
    request_id=20000000-0000-4000-8000-000000000032
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002'
IF state='FREE' AND revision=1;
```

Nếu row còn FREE ở revision 1, Cassandra tiến hành conditional mutation và trả `[applied]=True`. **Cả phần SET được áp dụng theo điều kiện**; không cần SELECT riêng và rồi hy vọng trạng thái không đổi.

### 7.3. B dùng cùng điều kiện cũ

```sql
UPDATE lwt002.seats
SET holder_id='bob',
    state='RESERVED',
    revision=2,
    request_id=20000000-0000-4000-8000-000000000033
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002'
IF state='FREE' AND revision=1;
```

Kỳ vọng `[applied]=False` sau khi A đã thành công, vì row hiện là `RESERVED/2`. Đối chiếu:

```sql
SELECT holder_id, state, revision, request_id
FROM lwt002.seats
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002';
```

Trong một cuộc đua thực sự, ai tới được pha quyết định CAS trước có thể thắng; **không hard-code Alice luôn thắng**. Điều kiện kết hợp `state='FREE' AND revision=1` giúp bảo vệ cả state machine và chống lost update.

### 7.4. Chuyển trạng thái tiếp theo theo owner và revision

Với row đã thuộc Alice ở revision 2, thử:

```sql
UPDATE lwt002.seats
SET state='CONFIRMED', revision=3
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002'
IF state='RESERVED' AND holder_id='alice' AND revision=2;
```

Nếu row đúng ba điều kiện, kỳ vọng `True`. Nếu B đã thắng hoặc row đã qua revision 2, câu lệnh trả `False` và **không được tự động bỏ IF để ép chuyển trạng thái**.

Điểm quan trọng về phiên bản: `revision` là cột dữ liệu **do ứng dụng quản lý**, không phải số version Cassandra tự tăng cho mọi row. Bất kỳ writer không dùng IF hoặc không tăng revision đúng cách đều có thể phá invariant, dù các writer khác đang dùng CAS.

### 7.5. Conditional DELETE kiểm tra giá trị trước khi xóa

Thử một điều kiện cũ, dự kiến **không xóa**:

```sql
DELETE FROM lwt002.seats
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002'
IF holder_id='bob' AND revision=2;
```

Nếu A đã xác nhận row với `holder_id='alice'`, `revision=3`, kết quả là `False`. Chỉ nếu muốn **xóa chính dữ liệu lab này**, kiểm tra row hiện tại và dùng điều kiện phù hợp:

```sql
DELETE FROM lwt002.seats
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002'
IF holder_id='alice' AND state='CONFIRMED' AND revision=3;
```

Không coi conditional DELETE là giải pháp đủ cho một **booking có lịch sử, hoàn tiền hoặc quyền sở hữu chuyển giao**. Xóa rồi tạo lại có thể gây **ABA**; cần thiết kế `generation`, audit, state transition và idempotency theo bài toán thực tế.

## 8. Cú pháp điều kiện và những bẫy quan trọng

### 8.1. IF EXISTS là một nhánh, IF column... là nhánh khác

Với `UPDATE` và `DELETE`, CQL cho phép:

```text
IF EXISTS

hoặc

IF column_a = value_a AND column_b = value_b [AND ...]
```

Trong cùng một statement, **không viết**:

```sql
-- Sai ý tưởng/cú pháp, không chạy:
UPDATE lwt002.seats
SET state='CONFIRMED'
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002'
IF EXISTS AND revision=2;
```

Muốn đảm bảo row đã tồn tại **và** giá trị khớp, điều kiện trên **giá trị không NULL đã được thiết kế rõ** như `revision=2` thường là phù hợp. Tuy nhiên lưu ý một số trường hợp `IF column = null` trên row thiếu có thể có semantics **tạo row** khi điều kiện NULL đúng; **không dùng `IF col = null` như một alias của `IF EXISTS`**. Chọn một state/revision không NULL hoặc bổ sung thiết kế tồn tại phù hợp nếu invariant yêu cầu cả hai.

### 8.2. WHERE phải chỉ định primary key, không phải WHERE tùy ý

```sql
-- Đúng: row xác định bằng toàn bộ composite partition key.
UPDATE lwt002.seats
SET state='RESERVED'
WHERE tenant_id='tenant-a' AND seat_id='seat-009'
IF state='FREE';

-- Sai khi thiếu seat_id: không có một row cụ thể để CAS.
UPDATE lwt002.seats
SET state='RESERVED'
WHERE tenant_id='tenant-a'
IF state='FREE';
```

Các câu có `IF` không biến Cassandra thành công cụ tìm kiếm toàn bảng. Nếu điều kiện nghiệp vụ cần “tìm seat nào còn FREE”, bạn cần **bảng/luồng chọn ứng viên theo truy vấn**, sau đó CAS trên **khóa seat cụ thể**.

### 8.3. IF trên giá trị có thể có nhiều phép so sánh, nhưng không phải SQL WHERE

Với cột thông thường, Cassandra cho phép các so sánh điều kiện theo cú pháp/version CQL phù hợp; ví dụ equality (`=`) và các toán tử so sánh được kiểu dữ liệu hỗ trợ. Tuy nhiên bài học ưu tiên **equality trên state/revision** vì dễ lý giải tính đúng khi cạnh tranh:

```sql
-- Mẫu compare-and-set dễ review:
UPDATE lwt002.seats
SET revision=4
WHERE tenant_id='tenant-a' AND seat_id='seat-cas-002'
IF revision=3;
```

Không đưa biểu thức Java, subquery, join, `OR` phức tạp hoặc function tùy ý vào `IF` rồi giả định được Cassandra hỗ trợ. Một số kiểu collection/UDT có cú pháp điều kiện riêng và giới hạn, cần đối chiếu **tài liệu đúng server version** trước khi dùng. Điều kiện trên **primary key** không thay nhiệm vụ của `WHERE`.

### 8.4. NULL, cột thiếu và row không tồn tại là khác nhau

Các trường hợp phải phân biệt:

| Trạng thái | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| Row **không tồn tại** | Không có `seat_id='seat-100'` | `IF EXISTS` phải trả false |
| Row tồn tại, cột nào đó **không có giá trị** | `holder_id=null` trên seat FREE | `IF holder_id=null` có ngữ nghĩa riêng, không giống `IF EXISTS` |
| Row tồn tại, trạng thái được gán sentinel | `holder_id='unassigned'` | CAS có thể so giá trị cụ thể, dễ kiểm thử |
| Row đã được DELETE hoặc TTL hết hạn | Row không còn live data theo Cassandra | Kết quả existence/condition phụ thuộc row liveness ở thời điểm CAS |

Trên Cassandra, `NULL` thường tương ứng xóa/không có giá trị của cell, không phải một giá trị đầy đủ như số 0. Điều kiện `IF col = null` có thể **được thỏa ngay cả khi row chưa tồn tại** và dẫn tới conditional UPDATE tạo row, nên phải thử trên bản server cụ thể nếu dùng. Để bảo vệ workflow “chỉ chỉnh row đã khởi tạo”, dùng `IF EXISTS` hoặc non-null revision/state thiết kế rõ.

### 8.5. Conditional mutation không được cung cấp write timestamp tùy ý

**Không** viết:

```sql
-- Không hợp lệ với conditional INSERT/LWT:
INSERT INTO lwt002.claims (tenant_id, handle, owner_id)
VALUES ('tenant-a', 'bad-timestamp', 'alice')
IF NOT EXISTS
USING TIMESTAMP 1700000000000000;
```

Trong Cassandra, **conditional updates không chấp nhận client-provided `USING TIMESTAMP`** vì giao thức CAS kiểm soát timestamp/điều kiện của mutation. Đừng tự ép timestamp để cố thắng race. Nếu nghiệp vụ cần event time, lưu nó trong **một cột timestamp riêng** và để CAS quyết định điều kiện trên state/revision như thiết kế.

Tương tự, `TTL` có thể làm row/cell hết hiệu lực và tạo điều kiện cho claim được tái cấp sau một khoảng thời gian. Không dùng TTL như **khóa phân tán/lease** nếu chưa xử lý clock, timeout, ABA, trạng thái owner và fencing token.

### 8.6. Không dùng LWT như một primitive cho mọi bảng/loại dữ liệu

- **Counter table** không hỗ trợ conditional mutation thông thường như bảng regular columns; đừng cố kết hợp `IF` với counter update.
- **Batch có điều kiện** bị ràng buộc chặt về **phạm vi một partition** (và các giới hạn câu lệnh/table tùy bản Cassandra), không phải transaction nhiều partition kiểu SQL.
- **CQL batch** không cho đưa một `SELECT` vào giữa để ra quyết định rồi UPDATE. Batch không biến read-check-write ở client thành serializable transaction.
- Không dựa vào LWT để đảm bảo unique trên nhiều bảng hoặc thực hiện side effect ngoài Cassandra theo đúng một giao dịch.

## 9. Diễn giải kết quả [applied] chính xác

### 9.1. Kết quả áp dụng và kết quả không thỏa điều kiện

Với câu `INSERT ... IF NOT EXISTS` hoặc `UPDATE/DELETE ... IF ...`, Cassandra trả về một result row có cột **`[applied]`**.

```text
-- Khi điều kiện đúng:
 [applied]
-----------
      True

-- Khi điều kiện sai:
 [applied] | ... các giá trị hiện hành (nếu server trả về) ...
-----------+-----------------------------------------------
     False | ...
```

Ở trạng thái `False`, **không có mutation được áp dụng bởi conditional statement đó**. Tập cột đính kèm trong kết quả không áp dụng có thể phụ thuộc statement/version; dữ liệu đã có thể đổi ngay sau khi response đến nếu writer khác tiếp tục chạy. Không xem row đính kèm là **một snapshot được khóa** cho quyết định kế tiếp.

### 9.2. Timeout không đồng nghĩa applied=false

```text
Client gửi CAS ----> Coordinator / Paxos replicas
                              |
                          Quyết định có thể được chấp thuận
                              |
           response bị mất / request timeout
                              X
Client nhận exception, không biết chắc trạng thái cuối.
```

| Kết quả nhìn từ client | Có biết điều kiện đã thỏa không? | Hành động ứng dụng |
|---|---|---|
| `[applied]=True` | Có, CAS được áp dụng theo phản hồi server | Trả success, lưu request ID/log |
| `[applied]=False` | Có, điều kiện không được thỏa | Trả conflict hoặc đọc lại state và quyết định mới |
| Timeout/mất kết nối | **Chưa chắc** | Đánh dấu UNKNOWN, kiểm tra row với CL phù hợp, đối chiếu request ID |
| Lỗi câu lệnh/sai schema | Không có kết quả CAS hợp lệ | Sửa CQL/schema, không bỏ IF để “cho qua” |

Nếu một claim timeout, retry cùng `IF NOT EXISTS` có thể nhận False vì **lần đầu chính mình đã commit**. Với `request_id` được ghi cùng row, ứng dụng có bằng chứng để nhận diện yêu cầu của mình trong phạm vi thiết kế. Nếu hàng hóa/booking có thể xóa và tái dùng, cần xử lý thêm vòng đời/generation.

### 9.3. Không nhầm cqlsh response với số row bị tác động

`[applied]=True` **không nói rằng có bao nhiêu bản sao được tạo vật lý**, không phải số row returned của một SELECT, và không phải thời gian một operation tiêu tốn. Với request LWT, điều kiện và mức nhất quán phải được ghi trong biên bản nếu muốn so sánh các lần thử.

## 10. Regular consistency và serial consistency

### 10.1. Hai điều khiển cần được cấu hình riêng

```text
cqlsh> CONSISTENCY LOCAL_QUORUM;
cqlsh> SERIAL CONSISTENCY SERIAL;
```

- **Regular CL** (ví dụ `LOCAL_QUORUM`) quy định mức phản hồi/learn của mutation và yêu cầu thông thường.
- **Serial CL** (`SERIAL` hoặc `LOCAL_SERIAL`) quy định phạm vi pha Paxos của **conditional mutation**.
- Nếu keyspace RF=3 trong một DC, `LOCAL_QUORUM` yêu cầu 2 replica phản hồi. Ở lab RF=1 nó chỉ cần một replica.
- `SERIAL` có ý nghĩa toàn bộ các replica theo phạm vi consensus của Cassandra; `LOCAL_SERIAL` giới hạn pha serial vào **local datacenter**. Khi có nhiều DC và client nhiều vùng cùng tranh một invariant, chọn local serial mà vẫn mong một thứ tự toàn cluster có thể không phù hợp.

**Không chọn `CONSISTENCY SERIAL` để thay cho regular commit consistency của conditional write**; dùng lệnh `SERIAL CONSISTENCY ...` cho serial phase. Trong Java Driver, đặt hai thuộc tính `setConsistencyLevel(...)` và `setSerialConsistencyLevel(...)` riêng.

### 10.2. Sự giao nhau giữa quorum không tự tạo CAS

Giả sử RF=3:

```text
Request 1: SELECT at LOCAL_QUORUM -> state=FREE
Request 2: SELECT at LOCAL_QUORUM -> state=FREE
Request 1: UPDATE thường at LOCAL_QUORUM -> state=RESERVED
Request 2: UPDATE thường at LOCAL_QUORUM -> state=RESERVED
```

Cả hai UPDATE thường vẫn có thể thành công. Quorum read/write **không khóa row xuyên hai statement**. Chính điều kiện `IF state='FREE' AND revision=1` mới là CAS để chọn một mutation được áp dụng theo state ban đầu.

### 10.3. Khi node down

| Tình huống RF=3, một DC | Request thường LOCAL_ONE | Request thường LOCAL_QUORUM | LWT cần quorum serial |
|---|---|---|---|
| Cả 3 node khỏe | Có thể phục vụ | Có thể phục vụ | Có thể phục vụ nếu đủ phản hồi/không contention quá mức |
| 1 node down, 2 node khỏe | Có thể phục vụ | Có thể phục vụ | Có thể phục vụ **nếu đủ Paxos quorum và regular CL** |
| 2 node down, 1 node khỏe | Có thể có request ONE | Không đủ 2 replica | Không đủ quorum consensus trong cấu hình điển hình |

Đây là **bảng điều kiện replica**, không phải bảo đảm tuyệt đối. Latency, network, disk/GC và failure detector có thể làm request timeout dù đủ node. LWT dùng Paxos có chi phí đáng kể so với mutation thường; vì thế cần đo contention và chọn phạm vi invariant hợp lý.

## 11. Java Driver: prepared statements, điều kiện và xử lý kết quả

### 11.1. Chuẩn bị đúng môi trường Java

Ví dụ bên dưới dùng **Java 17** và **Apache Cassandra Java Driver 4.x** (ví dụ Maven `org.apache.cassandra:java-driver-core:4.19.4`). Trong lab, Java có thể chạy:

| Nơi chạy Java | Contact point | Điều kiện |
|---|---|---|
| Host nơi Docker publish port | `127.0.0.1:9328` | Cổng host còn được map, metadata/route phù hợp |
| Container Java cùng `lwt002-net` | `cassandra-lwt002:9042` | Tên container được Docker DNS resolve |
| Máy khác | IP/DNS có thể route tới Cassandra | Auth/TLS/firewall/broadcast RPC theo chính sách |

**Đừng hard-code địa chỉ production hoặc mật khẩu trong Java source.** Ví dụ bên dưới lấy host, port, DC và cluster name dự kiến từ env; server lab không bật auth/TLS. Trong triển khai thật phải dùng credentials/role tối thiểu và xác minh TLS.

### 11.2. Ví dụ Java hoàn chỉnh: claim nếu chưa có

```java
import java.net.InetSocketAddress;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public class ClaimIfAbsent {
    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + name);
        }
        return value;
    }

    public static void main(String[] args) {
        String host = required("CASSANDRA_HOST");
        int port = Integer.parseInt(required("CASSANDRA_PORT"));
        String dc = required("CASSANDRA_LOCAL_DC");
        String expectedCluster = required("EXPECTED_CLUSTER");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, port))
                .withLocalDatacenter(dc)
                .build()) {
            Row identity = session.execute(
                "SELECT cluster_name, data_center FROM system.local WHERE key='local'")
                .one();
            if (identity == null
                    || !expectedCluster.equals(identity.getString("cluster_name"))
                    || !dc.equals(identity.getString("data_center"))) {
                throw new IllegalStateException("Connected to wrong Cassandra cluster/DC");
            }

            PreparedStatement insert = session.prepare(
                "INSERT INTO lwt002.claims " +
                "(tenant_id, handle, owner_id, request_id, revision, state) " +
                "VALUES (?, ?, ?, ?, 1, 'ACTIVE') IF NOT EXISTS");

            UUID requestId = UUID.randomUUID();
            BoundStatement stmt = insert.bind(
                    "tenant-a", "java-claim-002", "java-alice", requestId)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setSerialConsistencyLevel(DefaultConsistencyLevel.SERIAL);

            ResultSet result = session.execute(stmt);
            if (result.wasApplied()) {
                System.out.println("CLAIM_OK request_id=" + requestId);
            } else {
                System.out.println("CLAIM_NOT_APPLIED: inspect current owner/request_id");
            }
        }
    }
}
```

Chương trình cần các biến môi trường sau khi **chạy trên host**:

```text
CASSANDRA_HOST=127.0.0.1
CASSANDRA_PORT=9328
CASSANDRA_LOCAL_DC=dc1
EXPECTED_CLUSTER=lwt002-lab
```

Chạy lần đầu với handle mới thường thấy `CLAIM_OK`. Chạy lần thứ hai với cùng handle thường thấy `CLAIM_NOT_APPLIED` — **đó là kết quả hợp lệ**, không phải bằng chứng driver không kết nối được.

**Lưu ý:** `ResultSet.wasApplied()` là API đọc kết quả conditional mutation; theo Java Driver 4, nó trả `true` cho cả các **statement không có IF** vì những statement đó không có cột `[applied]`. Vì vậy **không dùng `wasApplied()` của một INSERT thường để suy ra “row được tạo mới”**.

### 11.3. Prepared UPDATE kiểm tra revision

Mẫu Java cho row đã có trong bảng `seats`:

```java
PreparedStatement casUpdate = session.prepare(
    "UPDATE lwt002.seats SET holder_id=?, state=?, revision=? " +
    "WHERE tenant_id=? AND seat_id=? " +
    "IF state=? AND revision=?");

BoundStatement bound = casUpdate.bind(
        "java-alice", "RESERVED", 2,
        "tenant-a", "seat-cas-002",
        "FREE", 1)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.SERIAL);

ResultSet rs = session.execute(bound);
boolean applied = rs.wasApplied();
if (!applied) {
    // Conflict có điều kiện; xem state mới trước khi quyết định.
}
```

Đoạn trên là **trích đoạn sử dụng trong một method đã có `session`**, không phải một Java class độc lập. Khi dùng nhiều request đồng thời, **tái sử dụng `CqlSession`/`PreparedStatement`**, còn mỗi request tạo một bound statement với tham số/CL rõ ràng.

**Đừng coi một prepared statement tự động mang tính transactional** nếu CQL của nó không có `IF`. Đồng thời không tự động gắn `setIdempotent(true)` và retry mọi LWT khi timeout: điều kiện có thể đã được chấp thuận và side effect/nghiệp vụ ngoài DB có thể không idempotent.

### 11.4. Phân loại kết quả trong API

| Điều kiện | Java xử lý | Hành vi ứng dụng |
|---|---|---|
| `wasApplied() == true` | CAS success | Trả success, ghi request ID |
| `wasApplied() == false` | Business conflict | Có thể đọc row và trả HTTP 409 nếu đúng conflict |
| Request timeout/exception | Unknown/technical failure | Log, retry có giới hạn, reconcile business key và request ID |
| Sai cluster/DC hoặc schema | Configuration failure | **Fail closed**, không ghi vào cluster không xác định |

Trên Cassandra, **exception không thể được thay bằng `false`** một cách an toàn. Nếu request đã quyết định thành công mà phản hồi mất, một lần retry có thể nhận `false` do row của chính request đầu đã tồn tại.

## 12. BATCH, counter và tính nguyên tử: những giới hạn

### 12.1. Khi nào không nên gom các điều kiện vào batch?

LWT của Cassandra dựa trên phạm vi **partition**. Các conditional mutations trong một BATCH bị giới hạn về phạm vi, và **không thể dùng conditional batch trên nhiều partition độc lập** để có transaction SQL. Ví dụ muốn cùng lúc chiếm hai handle:

```text
Handle A → partition K1
Handle B → partition K2
```

Không thể chỉ “đưa hai INSERT IF NOT EXISTS vào một BATCH” rồi mong được **atomic check-and-commit xuyên hai partition**. Cần thiết kế một aggregate key chung nếu hợp lý, hoặc dùng một kiến trúc transaction/coordinator khác có đặc tả bảo đảm tương ứng.

Ngoài ra, **conditional batch không cho custom timestamp**, và các counter/collection operations có giới hạn riêng; đọc tài liệu đúng phiên bản nếu thực sự cần kết hợp nhiều conditional mutations trong một partition.

### 12.2. LWT không thay thế phân quyền và durability

Một role có quyền `MODIFY` vẫn có thể chạy một câu `UPDATE` thường nếu ứng dụng/đội vận hành cho phép, phá invariant mà các client khác cố bảo vệ bằng CAS. Phải:

- Bảo đảm **mọi đường ghi** cùng dùng quy tắc CAS phù hợp.
- Cấp quyền SELECT/MODIFY tối thiểu, kiểm tra `CassandraAuthorizer` có thực sự bật.
- Thiết kế TLS/secret management và audit logging; không dùng account superuser cho app.
- Có replication, repair, snapshot/backup và giám sát tương ứng ở production. **LWT không phải backup** và không bảo vệ trước xóa nhầm bởi người có quyền.

### 12.3. Khi không nên dùng LWT

| Workload | Có nên dùng LWT trên mọi write? | Lý do |
|---|---|---|
| Claim username/resource duy nhất | **Thường phù hợp** | Cần CAS trên một key cụ thể |
| Chuyển state với revision | **Phù hợp** | Chống lost update trên aggregate |
| Event telemetry append-only | **Thường không** | Ghi thường theo partition/time bucket hiệu quả hơn |
| Counter lượt xem/metrics | **Không mặc nhiên** | Counter có semantics riêng, tránh LWT trên counter |
| Quota tổng trên nhiều partition | **Không trực tiếp** | Phải đưa invariant về một phạm vi đồng bộ khác |
| Payment + gửi email + CQL | **Không đủ** | Cần outbox/saga/idempotency cho side effects ngoài DB |

## 13. Hiệu năng, contention và quan sát vận hành

### 13.1. Vì sao IF đắt hơn ghi thường?

Ghi thường đưa mutation tới replicas theo regular CL. LWT phải dùng **Paxos** để các replica phối hợp về trạng thái/đề xuất và quyết định mutation. Điều này tạo thêm các round trip và có thể xảy ra tranh chấp khi nhiều writer cùng nhắm tới một partition.

Không tuyên bố cố định “LWT luôn chậm N lần”: latency phụ thuộc RF, số DC, mạng, JVM/GC, I/O, contention, timeout và tối ưu của phiên bản Cassandra.

### 13.2. Những số liệu cần theo dõi

| Chỉ số | Vì sao quan trọng |
|---|---|
| LWT attempts/s | Tổng số thao tác có điều kiện |
| `applied=true` / `applied=false` | Phân biệt thành công và conflict hợp lệ |
| Timeout/unknown | Request chưa rõ kết quả, ảnh hưởng retry |
| p50/p95/p99 latency của CAS | Quan sát chi phí Paxos và tail latency |
| Retry attempts/backoff | Tránh bão retry lên hot key |
| Top contended partition keys (đã ẩn dữ liệu nhạy cảm) | Tìm hot key cần thay thiết kế |
| RF, regular/serial CL, host/DC | Giải thích tính sẵn sàng và độ trễ |
| Node logs, GC/disk/compaction/hints/repair | Phân biệt race nghiệp vụ với lỗi hạ tầng |

Các lệnh chẩn đoán lab:

```bash
docker exec cassandra-lwt002 nodetool status
docker exec cassandra-lwt002 nodetool statusbinary
docker exec cassandra-lwt002 nodetool tpstats
docker exec cassandra-lwt002 nodetool compactionstats
docker logs --tail 100 cassandra-lwt002
```

Chúng **không tự đếm [applied] true/false** của ứng dụng. Muốn đo các kết quả đó, instrument Java/cqlsh test harness, gắn request ID và đo histogram ở phía client; có thể dùng server metrics tương ứng với phiên bản Cassandra để bổ trợ.

## 14. Các lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân khả dĩ | Cách khoanh vùng |
|---|---|---|
| `INSERT IF NOT EXISTS` lần đầu đã `False` | Row đã tồn tại, dùng volume cũ hoặc client khác thắng | SELECT đúng primary key; so `owner_id/request_id` |
| `UPDATE IF EXISTS` cho hai người cùng `True` | Chỉ kiểm tra row tồn tại, không so revision/state | Thay bằng `IF state='FREE' AND revision=<expected>` |
| `UPDATE IF revision=1` `False` | Row đã đổi hoặc chưa khởi tạo revision | SELECT row/revision, xử lý conflict |
| `IF EXISTS AND revision=...` lỗi | Kết hợp sai hai nhánh ngữ pháp | Dùng `IF EXISTS` **hoặc** `IF revision=...` |
| Điều kiện không tìm được row mong đợi | WHERE thiếu/sai primary key, sai tenant/DC/keyspace | `DESCRIBE TABLE`, `system.local` và khóa |
| `IF col=null` tạo row ngoài ý muốn | NULL comparison có ngữ nghĩa khác existence | Dùng non-null state/revision hoặc `IF EXISTS` khi cần row hiện hữu |
| Row bị xóa vẫn thấy disk lớn | Tombstone/SSTable/compaction chưa dọn | `tablestats`, `compactionstats`; không xóa file SSTable |
| Conditional mutation lỗi custom timestamp | LWT không cho `USING TIMESTAMP` | Bỏ timestamp tùy ý; lưu event time ở cột riêng |
| Batch có điều kiện nhiều partition bị từ chối | Paxos scope không hỗ trợ cross-partition transaction | Thiết kế lại aggregate/transaction boundary |
| Counter table + IF lỗi | Counter không hỗ trợ conditional mutation kiểu này | Dùng mô hình bảng/primitive phù hợp khác |
| Client thấy `False` sau khi retry timeout | Lần trước có thể đã commit | Reconcile bằng request ID/owner/state; không mặc định conflict người khác |
| Java `wasApplied()` cho INSERT thường là `true` | API không dùng để xác định row mới cho non-conditional statement | Chỉ diễn giải với CQL có IF |
| SERIAL/LOCAL_SERIAL không hoạt động như dự kiến | Sai regular vs serial CL hoặc thiếu replica | Kiểm tra cqlsh/driver setting, RF/DC, ring |
| Java kết nối contact point nhưng fail peer | Broadcast RPC/IP Docker không route từ nơi app chạy | Kiểm tra network, local DC, driver logs |
| LWT quá chậm | Hot partition, Paxos contention, network/GC/disk | Đo p95/p99, retry, phân bố key; giảm contention |
| Quy tắc unique vẫn bị phá | Có writer ghi thường hoặc normalize khóa không đồng nhất | Review tất cả write paths, key canonicalization và RBAC |

**Thứ tự xử lý hiệu quả:** xác định **invariant** → xem `PRIMARY KEY` → xem câu CQL có `IF` và điều kiện đúng chưa → kiểm tra `[applied]` vs exception → regular/serial CL → ring/network → latency/metrics. Không tự thay một câu CAS đang lỗi bằng ghi thường để “ép chạy”.

## 15. Tình huống chuyên sâu

### 15.1. “Đã có row” chưa chắc “đúng trạng thái”

Một ứng dụng giữ danh sách chỗ. Row có thể ở `FREE`, `RESERVED`, `CONFIRMED`, `CANCELLED`. Nếu mọi transition đều dùng `IF EXISTS`, row chỉ cần tồn tại là trạng thái có thể nhảy trái quy trình. Hãy xây **state machine**:

```text
FREE --IF state='FREE' AND rev=n--> RESERVED
RESERVED --IF holder=owner AND rev=n+1--> CONFIRMED
RESERVED --IF holder=owner AND rev=n+1--> CANCELLED
CONFIRMED --không cho chuyển thẳng về FREE nếu chưa có quy tắc hoàn/hủy
```

Trong thực tế, mỗi transition nên tăng revision và lưu event/audit tương ứng. Đừng tự giả định chỉ cần CAS trên cột `state` là đủ cho mọi đường nghiệp vụ.

### 15.2. IF NOT EXISTS là uniqueness trên **primary key**, không phải trên field bất kỳ

Một bảng `users_by_id(user_id PRIMARY KEY, handle text)` chỉ cho phép CAS tồn tại theo `user_id`. Muốn handle unique theo tenant, cần bảng `claims_by_handle(tenant_id, handle PRIMARY KEY, owner_id...)` với key phù hợp và một quy trình liên kết user/claim. Khi lưu thông tin người dùng trên bảng khác, việc cập nhật cả hai bảng có thể thất bại một phần; phải có saga/compensation/reconciliation hoặc thiết kế dữ liệu đáp ứng yêu cầu, không gắn nhãn “multi-table atomic” cho LWT một row.

### 15.3. Hết TTL hoặc DELETE rồi đăng ký lại: ABA

```text
t0: handle K chưa có
t1: Alice INSERT IF NOT EXISTS → true (generation 1)
t2: Alice release K (DELETE/TTL)
t3: Bob INSERT IF NOT EXISTS → true (generation 2)
t4: Retry cũ của Alice xuất hiện / response cũ đến muộn
```

Ứng dụng cần phân biệt **quyền sở hữu hiện tại** với **request cũ**. Một `request_id` lưu trong row hiện tại có ích, nhưng khi row đã bị xóa nó không giữ toàn bộ lịch sử. Nếu invariant nhạy cảm, thiết kế generation/fencing, hold period, status tombstone logic và idempotency store thích hợp.

### 15.4. Nhiều datacenter và local serial

Nếu client ở DC A và DC B có thể cùng claim một key toàn cục, phải đánh giá replication/topology và phạm vi serial consistency. `LOCAL_SERIAL` chỉ bảo đảm serial phase trong local DC; với invariant cần thống nhất xuyên nhiều DC, nên cân nhắc `SERIAL` và kiểm thử failure/race đa DC theo hướng dẫn chính thức. Trade-off thường là **latency mạng WAN cao hơn** và sensitivity với sự cố DC. Không suy từ kết quả lab một DC RF=1 rằng thiết kế toàn cầu đã đúng.

## 16. Checklist và bài tập

### 16.1. Checklist kiểm chứng lab

| Mục | Bằng chứng PASS |
|---|---|
| Cluster readiness | `lwt002-lab`, `dc1`, một node `UN`, `statusbinary=running` |
| CQL schema | `claims` và `seats` có composite partition keys đúng |
| IF NOT EXISTS lần đầu | Cặp `tenant-a/skyblue-002` trả `True` |
| IF NOT EXISTS cùng khóa | Owner khác thử lại trả `False`; row giữ chủ ban đầu |
| Khác tenant | Cùng handle nhưng `tenant-b` có thể trả `True` |
| IF EXISTS thiếu row | `seat-exists-002` chưa tạo trả `False` |
| IF EXISTS trên row có sẵn | Hai cập nhật khác owner có thể đều `True` |
| IF state AND revision | `seat-cas-002` A thắng, B dùng revision cũ `False` |
| Conditional DELETE | Xóa row lab khi đúng điều kiện; lần sau `IF EXISTS` `False` |
| Java Driver | Dùng prepared IF NOT EXISTS và diễn giải `wasApplied()` đúng |
| Timeout/retry | Phân biệt conflict với UNKNOWN; có kế hoạch reconcile request ID |

### 16.2. Câu hỏi tự kiểm tra

1. Tại sao `INSERT` thường có thể tạo hoặc cập nhật row, còn `INSERT IF NOT EXISTS` có thể trả `False`?
2. `IF NOT EXISTS` đang kiểm tra unique trên **primary key hay cột `owner_id`**?
3. Trong bảng claim, tại sao `tenant-a/skyblue-002` và `tenant-b/skyblue-002` không tranh trên cùng partition?
4. Hai client cùng dùng `UPDATE ... IF EXISTS` trên một seat đang tồn tại. Cả hai có thể nhận `True` không? Vì sao?
5. Câu `UPDATE ... IF state='FREE' AND revision=1` bảo vệ điều gì mà `IF EXISTS` không bảo vệ?
6. Khi B nhận `[applied]=False` sau khi A tăng revision, có nên retry cùng revision liên tục không?
7. Vì sao `WHERE` phải chứa full primary key, còn `IF` chỉ chứa các giá trị được kiểm tra?
8. `IF EXISTS AND revision=2` là cú pháp phù hợp không? Nếu không, hãy viết câu CAS đúng.
9. NULL comparison khác existence test ra sao? Vì sao `IF col=null` có thể là lựa chọn nguy hiểm khi row chưa tồn tại?
10. Tại sao conditional mutation không cho custom `USING TIMESTAMP`?
11. Vì sao `SERIAL CONSISTENCY SERIAL` và `CONSISTENCY LOCAL_QUORUM` phải được hiểu như hai pha khác nhau?
12. Một request timeout rồi retry `IF NOT EXISTS` nhận `False`. Có thể khẳng định người khác đã claim key không?
13. Vì sao một batch có hai conditional mutation trên hai partition **không** tương đương transaction SQL?
14. Java Driver `wasApplied()` trả gì trên một INSERT thường không có IF, và vì sao không dùng nó để xác định row vừa được tạo?
15. Phải kiểm thử thêm điều gì khi từ một node RF=1 chuyển sang cluster RF=3 nhiều datacenter?
16. Tại sao LWT không thay thế backup, repair, authentication/authorization hoặc monitoring?

**Tiêu chí hoàn thành:** người học chạy được các phép thử `IF NOT EXISTS`, `IF EXISTS`, `IF state/revision` và conditional DELETE trên dữ liệu lab; đọc đúng `[applied]`; giải thích vì sao `IF EXISTS` không chống lost update; mô tả riêng regular/serial CL, timeout UNKNOWN, giới hạn Paxos theo partition; và sử dụng Java Driver có phân loại kết quả CAS rõ ràng.

## 17. Dọn lab an toàn

Nếu muốn dừng nhưng **giữ dữ liệu** để học bài LWT tiếp theo:

```bash
docker stop cassandra-lwt002
docker volume inspect lwt002_node_data
```

Nếu muốn xóa **container** nhưng giữ named volume:

```bash
docker rm cassandra-lwt002
docker network rm lwt002-net
docker volume ls
```

Nếu container chưa được dừng, `docker rm` có thể báo lỗi; hãy `docker stop` trước. **Không** chạy `docker volume rm` hoặc `docker volume prune` khi còn cần dữ liệu. Dựng lại một node có dữ liệu cũ cần dùng cùng identity/cấu hình tương thích; khi mở rộng nhiều node còn cần quản lý broadcast/IP và tokens theo runbook.

**Mọi lệnh DELETE/UPDATE trong bài chỉ áp dụng lên keyspace `lwt002` của lab**. Không thử các kịch bản tranh chấp hoặc xóa bản ghi của người dùng thật trên production.

## 18. Tài liệu tham khảo chính thức

- [Apache Cassandra 5.0 — CQL Data Manipulation](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html): cú pháp `INSERT IF NOT EXISTS`, `UPDATE/DELETE IF EXISTS`, `IF condition AND ...`, Paxos và BATCH.
- [Apache Cassandra — CQL Language Reference](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html): kiểu dữ liệu, `PRIMARY KEY` và ràng buộc schema.
- [Apache Cassandra — Guarantees](https://cassandra.apache.org/doc/stable/cassandra/architecture/guarantees.html): phạm vi atomicity/isolation và linearizability của LWT.
- [Apache Cassandra — Dynamo Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): replica, coordinator, quorum/consistency level.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `CONSISTENCY`, `SERIAL CONSISTENCY` và cách chạy CQL.
- [Apache Cassandra Java Driver 4.19 — Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): bind, prepared statement và execution parameters.
- [Apache Cassandra Java Driver 4.19 — ResultSet](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/ResultSet.html): semantics của `wasApplied()` đối với conditional/nonconditional statement.
- [Apache Cassandra Java Driver 4.19 — Statement](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/Statement.html): regular và serial consistency trên statement.
- [Docker Hub — Cassandra Official Image](https://hub.docker.com/_/cassandra): chạy container, biến môi trường cấu hình và lưu trữ bằng volume.
