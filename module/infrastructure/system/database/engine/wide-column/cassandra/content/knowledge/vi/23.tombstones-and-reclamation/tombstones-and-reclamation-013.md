# Thực nghiệm xóa, replica ngừng hoạt động và khôi phục đúng dữ liệu

## Mục tiêu bài học

Trong Apache Cassandra, `DELETE` không lập tức xóa mọi bản sao của dữ liệu trên các node. Thay vào đó, Cassandra ghi một **tombstone** (dấu xóa) có timestamp. Tombstone được phân phối và hòa giải với dữ liệu còn sống theo cơ chế replica và timestamp; chỉ về sau, trong những điều kiện an toàn nhất định, **compaction** mới có thể thu hồi dữ liệu đã xóa trên đĩa.

Vấn đề khó xuất hiện khi một **replica ngừng hoạt động đúng lúc DELETE**: replica đó có thể vẫn giữ bản ghi cũ. Khi node quay lại, hệ thống cần đồng bộ dấu xóa trước khi nó bị loại bỏ khỏi các bản sao khác. Nếu không, dữ liệu tưởng đã xóa có nguy cơ **xuất hiện lại**, thường gọi là *zombie data*.

Bài học thuộc chương **Tombstone và thu hồi** trong module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nó kết nối đường ghi/đọc, partition key của mô hình wide-column, replication, consistency level, CQL, compaction, repair và thao tác ứng dụng Java.

Sau bài này, bạn có thể:

1. Giải thích vì sao Cassandra dùng tombstone và vai trò của `gc_grace_seconds`.
2. Thiết kế lab **ba node/RF=3** để xóa dữ liệu khi một replica đang down.
3. Phân biệt **DELETE đã được xác nhận**, **đọc không thấy hàng**, và **mọi replica đã biết tombstone**.
4. Khôi phục node, kiểm tra hints/repair và xác minh dữ liệu theo mức nhất quán phù hợp.
5. Nhận diện rủi ro khi replica vắng mặt quá lâu, cũng như những điều không thể sửa chỉ bằng compaction.
6. Ghi nhận ACK, timeout và kết quả kiểm chứng từ Java Driver mà không kết luận quá mức.

> **Giới hạn thực hành:** chỉ dừng node trong cluster lab hoặc môi trường thử nghiệm được phép gây lỗi. Bài này trình bày lệnh để người học tự chạy; không chủ động dừng hệ thống thật. Không rút ngắn `gc_grace_seconds` ở production để cố tạo zombie.

## 1. DELETE, tombstone và thu hồi vật lý là ba thời điểm khác nhau

Giả sử hàng `(run_id='lab-a', item_id=1)` chứa `value='ACTIVE'` trên ba replica. Khi ứng dụng gửi:

~~~sql
DELETE FROM tombstone_lab.entries_by_run
WHERE run_id = 'lab-a' AND item_id = 1;
~~~

Cassandra ghi tombstone với **deletion timestamp** để đánh dấu dữ liệu bị xóa. Trong lúc đọc, các replica cần hòa giải dữ liệu còn sống và tombstone; bản ghi cũ có timestamp thấp hơn dấu xóa không được trở thành kết quả còn sống chỉ vì một replica chưa nhận DELETE.

~~~mermaid
sequenceDiagram
    participant App as Client
    participant C as Coordinator
    participant R1 as Replica 1
    participant R2 as Replica 2
    participant R3 as Replica 3 đang down
    App->>C: DELETE, LOCAL_QUORUM
    C->>R1: Tombstone
    C->>R2: Tombstone
    Note over R3: Giữ giá trị cũ; chưa nhận DELETE
    R1-->>C: ACK
    R2-->>C: ACK
    C-->>App: Success (đạt 2/3 ACK)
~~~

Đây là sơ đồ tình huống thí nghiệm; không bảo đảm mọi lần thực thi đều đúng thứ tự truyền tin này. Việc replica thứ ba còn giá trị cũ phụ thuộc việc nó đã dừng trước DELETE và chưa được đồng bộ sau đó.

| Giai đoạn | Dữ liệu logic | Dữ liệu vật lý |
| --- | --- | --- |
| Trước `DELETE` | Hàng tồn tại | Giá trị có thể nằm trong memtable/SSTable của replica |
| Sau `DELETE` được ACK | Hàng bị xóa đối với những lần đọc đủ thông tin tombstone | Tombstone và dữ liệu cũ có thể còn trong nhiều SSTable |
| Replica quay lại | Phải học được tombstone để không đưa giá trị cũ trở lại | Có thể cần hints, read repair hoặc anti-entropy repair |
| Khi compaction được phép purge | Hàng bị xóa tiếp tục không xuất hiện | Tombstone và dữ liệu đã bị che có thể được thu hồi nếu đủ điều kiện |

**Compaction không đồng nghĩa DELETE**. Cũng không được cho rằng tombstone sẽ biến mất đúng tại giây thứ `gc_grace_seconds`: purge còn phụ thuộc SSTable chồng lắp, dữ liệu còn sống, compaction strategy và điều kiện an toàn.

### Phân biệt một số kiểu xóa

- `DELETE ... WHERE` với đủ khóa chính có thể xóa một hàng cụ thể; xóa cột, collection hoặc range có những dạng tombstone khác nhau.
- `UPDATE` một cột thành `null` cũng có thể tạo tombstone; nhiều giá trị TTL hết hạn cũng dẫn tới logic tombstone.
- `TRUNCATE` là thao tác xóa dữ liệu ở cấp bảng với ngữ nghĩa khác `DELETE` từng hàng; không dùng `TRUNCATE` để thay thế phép thử lan truyền tombstone.
- Không được tự sửa hoặc xóa tệp SSTable trên ổ để “xóa nhanh”; việc đó có thể gây mất dữ liệu hoặc phá vỡ quá trình phục hồi.

## 2. Vì sao replica ngừng hoạt động gây rủi ro zombie?

Cassandra dùng **last-write-wins reconciliation theo timestamp** cùng thông tin xóa. Khi một replica bỏ lỡ DELETE, nó vẫn giữ bản sao cũ. Trong thời gian tombstone còn tồn tại trên các replica khác, dấu xóa có thể ngăn dữ liệu cũ được coi là hợp lệ khi quá trình hòa giải nhìn thấy nó.

Nhưng nếu replica vắng mặt **quá lâu** và các node còn sống đã có thể purge tombstone, hệ thống có thể không còn đủ dấu vết để phân biệt giá trị cũ với giá trị chưa từng bị xóa. Khi replica cũ quay về hoặc được đồng bộ theo hướng không phù hợp, giá trị sống còn sót lại có thể được sao chép trở lại: **zombie data**.

~~~mermaid
flowchart TD
    A["R1/R2/R3 đều có giá trị cũ"] --> B["R3 ngừng hoạt động"]
    B --> C["DELETE đạt quorum trên R1 + R2"]
    C --> D{"R3 được đồng bộ\ntrước khi tombstone bị purge?"}
    D -->|Có| E["R3 học được dấu xóa\nDữ liệu cũ bị che và loại bỏ an toàn"]
    D -->|Không| F["Tombstone có thể bị purge\nR3 vẫn có giá trị sống cũ"]
    F --> G["Nguy cơ dữ liệu zombie\nkhi R3 trở lại/repair"]
~~~

Ở đây, “nguy cơ” không có nghĩa mọi lần restart sau grace đều chắc chắn tái xuất hiện hàng. Để tái hiện một zombie trong lab phải kiểm soát thời gian, compaction, timestamp và dữ liệu replica; đó là bài thử nâng cao và không cần thực hiện để hiểu cơ chế.

## 3. gc_grace_seconds, hints và repair khác nhau thế nào?

`gc_grace_seconds` là cấu hình **cấp bảng**, tính bằng giây. Nó xác định thời gian ân hạn tối thiểu liên quan tới việc loại bỏ tombstone thông qua compaction, nhằm cho replica đã down có cơ hội nhận thông tin xóa. Giá trị thông dụng trong nhiều bản Cassandra là **864000 giây = 10 ngày**; luôn xác minh cấu hình thực tế.

~~~sql
SELECT keyspace_name, table_name, gc_grace_seconds
FROM system_schema.tables
WHERE keyspace_name = 'tombstone_lab'
  AND table_name = 'entries_by_run';
~~~

Không được hiểu `gc_grace_seconds` là một lệnh “tự chạy repair sau 10 ngày”. Nó không chủ động truyền dấu xóa, không bảo đảm mọi replica đã đồng bộ và không thay thế lịch repair.

| Cơ chế | Làm gì? | Không bảo đảm gì? |
| --- | --- | --- |
| **gc_grace_seconds** | Giữ tombstone đủ lâu để tránh purge quá sớm theo điều kiện compaction | Không tự phát hiện replica đã mất dấu xóa; không thay lịch repair |
| **Hinted handoff** | Lưu và phát lại một số mutation cho replica tạm down nếu cấu hình/giới hạn cho phép | Hints có thời hạn, giới hạn lưu trữ; không phải bản sao hoặc thay thế repair |
| **Read repair** | Trong những tình huống đọc có reconciliation và chính sách phù hợp, sửa lệch giữa các replica tham gia | Không quét mọi partition; một lần `SELECT` không chứng minh toàn bộ cluster đồng bộ |
| **Anti-entropy repair** | So sánh phạm vi token giữa replica và đồng bộ dữ liệu/tombstone bị thiếu | Không tái tạo được tombstone đã bị purge ở mọi bản sao |
| **Compaction** | Hợp nhất SSTable và có thể purge tombstone khi đủ điều kiện | Không chủ động đồng bộ replica khác; purge quá sớm có thể góp phần tạo zombie |

Một quy tắc vận hành thường dùng: **hoàn tất repair bao phủ dữ liệu liên quan với chu kỳ ngắn hơn thời gian grace**, có dự phòng cho thời gian node down và thời gian repair. Đây là điều kiện thiết kế, không phải bằng chứng rằng chỉ cần gọi repair một lần là an toàn trong mọi cấu hình. Nếu sử dụng cơ chế tombstone đặc biệt hoặc phiên bản có quy tắc khác, phải theo tài liệu của đúng phiên bản.

Ví dụ: nếu grace là 10 ngày mà replica nghỉ 15 ngày, **không được mặc nhiên mở node cũ rồi chạy repair như bình thường**. Khi một replica vượt quá giới hạn an toàn và tombstone có thể đã bị loại trên các replica khác, cần quy trình phục hồi/replace/rebuild dựa trên bản sao còn đáng tin cậy hoặc backup, cùng kiểm tra tính đầy đủ dữ liệu.

## 4. Thiết kế lab: ba node, RF=3, một DC

### 4.1. Yêu cầu và giả định

Sử dụng cluster ba node cùng datacenter, ví dụ `cass-1`, `cass-2`, `cass-3`. Giả sử datacenter tên `datacenter1`, phiên bản Cassandra đồng nhất và cả ba node phục vụ cùng keyspace. Nếu DC thực tế khác, sửa các lệnh tạo keyspace tương ứng.

Trước tiên xem cluster khi còn khỏe:

~~~bash
# Chạy trên container/VM còn sống, điều chỉnh theo môi trường lab.
nodetool status
~~~

Kỳ vọng ba node ở trạng thái `UN` (*Up/Normal*), không có bootstrap/decommission/repair đang chạy. Từ `cqlsh`:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

Lệnh này mô tả node đang kết nối, không tự xác nhận phiên bản mọi node. Kiểm tra cấu hình từng node nếu cluster đang nâng cấp.

### 4.2. Keyspace và bảng mẫu

~~~sql
CREATE KEYSPACE IF NOT EXISTS tombstone_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS tombstone_lab.entries_by_run (
    run_id text,
    item_id int,
    value text,
    created_at timestamp,
    PRIMARY KEY ((run_id), item_id)
) WITH gc_grace_seconds = 864000;
~~~

`run_id` là **partition key** giúp cô lập dữ liệu của từng lần chạy; `item_id` là clustering column. Thí nghiệm chỉ thao tác đúng một partition và các hàng đã biết, tránh quét rộng. `created_at` là dữ liệu minh họa; timestamp dùng để hòa giải mutation do Cassandra quản lý, không được suy ra chỉ từ nội dung cột này.

**Nếu keyspace/bảng đã tồn tại**, `IF NOT EXISTS` không cập nhật cấu hình cũ. Phải kiểm tra trước khi chạy:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'tombstone_lab';

SELECT table_name, gc_grace_seconds
FROM system_schema.tables
WHERE keyspace_name = 'tombstone_lab'
  AND table_name = 'entries_by_run';
~~~

Không làm lab RF=3 trên cluster chỉ có hai replica khỏe ngay từ đầu; khi đó các dự đoán số ACK không còn đúng.

### 4.3. Chuẩn bị dữ liệu đã có trên ba replica

Trong `cqlsh` khi cả ba node đang `UN`:

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO tombstone_lab.entries_by_run
    (run_id, item_id, value, created_at)
VALUES ('delete-demo-01', 1, 'SHOULD_BE_DELETED',
        '2026-11-21T09:00:00Z');

INSERT INTO tombstone_lab.entries_by_run
    (run_id, item_id, value, created_at)
VALUES ('delete-demo-01', 2, 'CONTROL_KEEP',
        '2026-11-21T09:00:00Z');
~~~

`CONSISTENCY ALL` trước khi dừng node nhằm yêu cầu **cả ba replica ACK** dữ liệu ban đầu. Ghi lại kết quả thực nhận: nếu có timeout/lỗi, không coi thí nghiệm đã hoàn thành bước chuẩn bị. Hàng `item_id=2` làm **mẫu đối chứng** để đảm bảo ta không vô tình xóa cả partition.

Đọc baseline:

~~~sql
SELECT item_id, value, created_at
FROM tombstone_lab.entries_by_run
WHERE run_id = 'delete-demo-01';
~~~

Kỳ vọng có `item_id=1` và `item_id=2`. Nếu chạy lại, **đổi run_id** để không trộn dữ liệu/tombstone của lần trước. Đừng thay đổi thời gian của hệ thống hoặc dùng timestamp CQL tùy ý trong lab cơ bản, vì sai lệch đồng hồ làm việc phân tích dấu xóa khó hơn.

## 5. Thực nghiệm A: dừng replica trước khi DELETE

Từ host chạy Docker của lab:

~~~bash
# Ví dụ tên container; chỉ thực hiện trong lab.
docker kill --signal=KILL cass-3
~~~

`SIGKILL` dừng tiến trình đột ngột, không phải quy trình `nodetool drain`. Đây là mô phỏng **node tạm không thể nhận mutation**, không phải thí nghiệm mất điện hay mất toàn bộ nội dung thiết bị lưu trữ.

Xem hai node còn lại:

~~~bash
# Chạy trên cass-1 hoặc cass-2.
nodetool status
~~~

Kỳ vọng `cass-3` báo `DN` (*Down/Normal*) và `cass-1`, `cass-2` vẫn `UN`. Kết nối `cqlsh` vào node còn sống; không dùng `cqlsh` trong container đã dừng.

Đặt write consistency level:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

Thực hiện **DELETE đúng một hàng**:

~~~sql
DELETE FROM tombstone_lab.entries_by_run
WHERE run_id = 'delete-demo-01'
  AND item_id = 1;
~~~

Với RF=3 ở một DC, `LOCAL_QUORUM` đòi **2/3 replica** xác nhận. Vì đúng hai replica còn sống, DELETE **có thể thành công** nếu cả hai xử lý yêu cầu. Lưu lại phản hồi chính xác của client:

| Tình huống | Ghi nhận | Có thể kết luận |
| --- | --- | --- |
| `DELETE` trả thành công | `ACK_LOCAL_QUORUM` | Hai replica đã xác nhận mutation xóa theo CL |
| Timeout | `UNKNOWN_TIMEOUT` | Một hoặc nhiều replica có thể đã xử lý, nhưng client chưa nhận đủ xác nhận |
| Unavailable/error | Mã lỗi thực tế | Không tự suy ra có 0 replica xử lý; cần xem loại lỗi và logs |

**Chỉ tiếp tục nhánh kiểm chứng DELETE đã xác nhận khi nhận ACK thành công.** Nếu kết quả không rõ, tạo một `run_id` mới sau khi cluster khỏe lại hoặc điều tra theo biên bản; không lặng lẽ retry rồi tính đây là một thao tác chắc chắn đã ACK.

### Đọc khi replica thứ ba còn down

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT item_id, value
FROM tombstone_lab.entries_by_run
WHERE run_id = 'delete-demo-01';
~~~

Khi DELETE đã ACK và hai replica còn sống đáp ứng đọc `LOCAL_QUORUM`, kỳ vọng chỉ thấy hàng đối chứng `item_id=2`. Nếu `item_id=1` không xuất hiện, **đây là bằng chứng về kết quả đọc tại CL đã chọn**, chứ chưa chứng minh `cass-3` biết tombstone.

Thử đọc với `LOCAL_ONE` cũng có thể không thấy hàng, nhưng **LOCAL_ONE có bảo đảm yếu hơn** khi còn một replica cũ. Một lần đọc đúng ở `LOCAL_ONE` không đủ xác nhận mọi replica đồng bộ.

## 6. Thực nghiệm B: khởi động replica và đồng bộ dấu xóa

Khởi động lại node:

~~~bash
docker start cass-3
~~~

Kiểm tra `nodetool status` cho tới khi cả ba node `UN`. Tại thời điểm này, replica `cass-3` từng lưu `item_id=1` trước khi dừng; nó có thể:

- Nhận **hint** đã lưu khi down, nếu cơ chế hints đang bật, còn trong giới hạn và được phát lại thành công.
- Được đồng bộ tombstone qua **read repair** trong các điều kiện đọc phù hợp.
- Được đồng bộ thông qua **anti-entropy repair** trên phạm vi token chứa partition này.

Không có cơ sở để khẳng định cách nào chắc chắn đã xảy ra chỉ bằng `nodetool status`. Trạng thái `UN` nói rằng node đã hoạt động, không nói rằng toàn bộ SSTable đã được sửa.

### 6.1. Đọc sau khi node quay lại

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT item_id, value
FROM tombstone_lab.entries_by_run
WHERE run_id = 'delete-demo-01';
~~~

Nếu kết quả chỉ còn `item_id=2`, hệ thống trả về đúng ở phạm vi đọc hiện tại. Nhưng kết nối `cqlsh` trực tiếp tới `cass-3` **không bảo đảm** Cassandra chỉ đọc bản sao local của chính node đó: coordinator vẫn chọn replica theo routing và consistency level. Vì vậy, không dùng “tôi query từ cass-3 không thấy hàng” làm bằng chứng tất cả replica sạch.

### 6.2. Repair khi tombstone vẫn còn trong grace

Trên cluster lab, chạy repair cho bảng với các node đã khỏe:

~~~bash
# Chạy trên node phù hợp trong lab sau khi cả ba node đã UN.
nodetool repair -full tombstone_lab entries_by_run
~~~

`nodetool repair -full` thực hiện anti-entropy repair không dựa vào phạm vi incremental đã đánh dấu; có thể tốn CPU, disk I/O, network và thời gian. Việc chạy lệnh trên một node áp dụng cho các range mà phiên repair của node đó phụ trách; với topology khác nhau cần lập kế hoạch **bao phủ toàn bộ range/replica** liên quan. Không coi một lệnh trả về thành công trên một node bất kỳ là bằng chứng mọi node/bảng trên cluster lớn đã được repair đầy đủ.

Trong lab ba node RF=3, node gọi repair tham gia mọi phạm vi replica của bảng; vẫn phải xem log/trạng thái hoàn tất, lỗi và phạm vi thực tế. Hãy chạy repair **trước khi vượt grace**, khi các tombstone cần thiết còn tồn tại và mọi replica được phép trao đổi với nhau.

Sau repair, đọc lại hàng đích và mẫu đối chứng:

~~~sql
SELECT item_id, value
FROM tombstone_lab.entries_by_run
WHERE run_id = 'delete-demo-01';
~~~

Mong đợi:

- **Không thấy** `item_id=1`.
- **Vẫn thấy** `item_id=2` với `value='CONTROL_KEEP'`.
- Không có write/update khác lên cùng khóa trong thời gian thử nghiệm.

Để điều tra sâu hơn, thu thập logs và metrics repair/hints trên từng node. Phép thử chỉ tập trung vào hai hàng đã biết; nó không chứng minh trạng thái của các partition khác trong cluster.

## 7. Vì sao không nên cố đợi qua gc_grace_seconds?

Thử nghiệm chuẩn nên hoàn tất trước khi tombstone có thể bị purge. Để hiểu nguy cơ zombie, hãy dùng **tình huống giả định** thay vì dừng node sản xuất hàng chục ngày:

| Mốc | Hai replica khỏe | Replica đã down | Rủi ro |
| --- | --- | --- | --- |
| T0 | Có hàng sống | Có hàng sống | Bình thường |
| T1 | Nhận DELETE và lưu tombstone | Bỏ lỡ DELETE | Replica cũ |
| T1 + vài giờ | Tombstone còn; có thể repair | Chưa quay lại | Có thể phục hồi an toàn nếu đồng bộ trước purge |
| Sau thời gian grace và khi đủ điều kiện compaction | Tombstone **có thể** được purge | Vẫn còn giá trị cũ | Mất thông tin xóa ở những bản sao đã purge |
| Replica cũ quay lại không kiểm soát | Có thể học giá trị cũ như dữ liệu sống | Mang bản sao stale | Nguy cơ **zombie** |

**Điều kiện cần nhấn mạnh:** hết `gc_grace_seconds` không tự động kích hoạt purge đúng lúc đó; nó mở khả năng purge theo điều kiện compaction. Một cụm có thể giữ tombstone lâu hơn grace. Ngược lại, không được dựa vào điều may mắn này làm chiến lược vận hành.

Nếu một replica ở ngoài cluster quá lâu, đặc biệt quá grace hoặc chưa có repair bao phủ, **không mặc định khởi động lại như bình thường**. Trước hết xác minh khả năng đã purge tombstone, tình trạng các replica khỏe, backup và quy trình thay thế/tái dựng node theo phiên bản đang dùng. Mục tiêu là tránh đưa dữ liệu stale trở lại cluster; không xóa thủ công SSTable của node cũ.

Trong một số tình huống, phải **rebuild/replace replica từ nguồn còn tin cậy**, hoặc khôi phục từ bản sao lưu và đối soát với hệ thống nguồn. Nếu tất cả bản sao đã mất tombstone và không có lịch sử xóa đáng tin, repair **không thể tự suy luận** hàng nào từng bị xóa; cần khôi phục từ event log/backup/nguồn nghiệp vụ.

## 8. Thử nghiệm mở rộng: TTL và compaction

TTL cũng dẫn đến dữ liệu hết hạn được coi là không còn tồn tại. Nó tương tác với tombstone và việc thu hồi vật lý:

~~~sql
-- Hàng riêng, không dùng cùng khóa với thí nghiệm DELETE chính.
INSERT INTO tombstone_lab.entries_by_run
    (run_id, item_id, value, created_at)
VALUES ('ttl-demo-01', 1, 'TEMPORARY',
        '2026-11-21T09:00:00Z')
USING TTL 120;
~~~

Đọc trước thời hạn:

~~~sql
SELECT item_id, value, TTL(value)
FROM tombstone_lab.entries_by_run
WHERE run_id = 'ttl-demo-01' AND item_id = 1;
~~~

Sau khi TTL hết, `SELECT` có thể không còn trả hàng; điều đó không chứng minh byte dữ liệu đã được thu hồi khỏi SSTable ngay. Hãy quan sát chỉ số tombstone và compaction qua các công cụ quản trị:

~~~bash
nodetool tablestats tombstone_lab.entries_by_run
nodetool compactionstats
~~~

**Không ép `nodetool compact` chỉ để nhanh chóng “xóa sạch” sau 120 giây.** Major compaction tạo tải I/O/CPU và phụ thuộc điều kiện purge, có thể ảnh hưởng dữ liệu/chiến lược time-series. Cần thời gian quan sát đủ dài và hiểu `gc_grace_seconds` cùng cơ chế compaction của bản Cassandra thực tế.

| Hiện tượng | Cách hiểu đúng |
| --- | --- |
| `SELECT` không còn thấy hàng | Dữ liệu logic không được trả trong truy vấn đó |
| SSTable vẫn chiếm dung lượng | Dữ liệu cũ hoặc tombstone có thể đang chờ compaction |
| Tombstone không giảm ngay | Purge phụ thuộc grace, overlap và việc chọn SSTable |
| Nhiều tombstone gây read latency cao | Read path có thể phải xét nhiều dữ liệu xóa/hết hạn |
| Repair đã chạy | Có thể đồng bộ replica, **không** bắt buộc giải phóng đĩa ngay |

## 9. Ứng dụng Java: tách kết quả DELETE khỏi kết quả đọc

Đoạn mã dưới đây dùng **Apache Cassandra Java Driver 4.x**. Giả sử `CqlSession` kết nối đúng keyspace/topology và đã tạo bảng lab; PreparedStatement được tái sử dụng:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class TombstoneProbe {
    private final CqlSession session;
    private final PreparedStatement deleteOne;
    private final PreparedStatement selectOne;

    public enum DeleteResult { ACKNOWLEDGED, UNKNOWN }

    public TombstoneProbe(CqlSession session) {
        this.session = session;
        this.deleteOne = session.prepare(
            "DELETE FROM tombstone_lab.entries_by_run " +
            "WHERE run_id = ? AND item_id = ?");
        this.selectOne = session.prepare(
            "SELECT value FROM tombstone_lab.entries_by_run " +
            "WHERE run_id = ? AND item_id = ?");
    }

    public DeleteResult deleteAtQuorum(String runId, int itemId) {
        BoundStatement statement = deleteOne.bind(runId, itemId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(false);
        try {
            session.execute(statement);
            System.out.printf("DELETE_ACK run=%s item=%d%n", runId, itemId);
            return DeleteResult.ACKNOWLEDGED;
        } catch (RuntimeException error) {
            System.err.printf(
                "DELETE_UNKNOWN run=%s item=%d error=%s%n",
                runId, itemId, error.getClass().getSimpleName());
            return DeleteResult.UNKNOWN;
        }
    }

    public boolean observedAbsentAtQuorum(String runId, int itemId) {
        BoundStatement statement = selectOne.bind(runId, itemId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        Row row = session.execute(statement).one();
        return row == null;
    }
}
~~~

Giải thích những điểm quyết định độ tin cậy:

- `DELETE_ACK` chỉ được ghi khi `session.execute` trả thành công. Timeout hoặc ngoại lệ được đánh dấu `UNKNOWN`; nếu yêu cầu cần phân loại chi tiết, lớp gọi phải giữ exception để phân biệt `Unavailable`, timeout và lỗi cấu hình.
- `observedAbsentAtQuorum` trả `true` khi **lần đọc ở quorum không thấy hàng**; nó không có nghĩa **từng replica** đều đã có tombstone hoặc byte vật lý đã được xóa.
- `setIdempotence(false)` là lựa chọn thận trọng cho lab khi có thể có thao tác ghi lại cùng khóa: retry một `DELETE` sử dụng timestamp mới có thể tương tác khác với update đồng thời. Trong quy trình thật, việc retry phải dựa trên định danh nghiệp vụ, timestamp và mô hình cạnh tranh.
- Giữ `runId` riêng cho từng lượt thử, không đưa thao tác ghi mới lên cùng khóa trong lúc đang phân tích kết quả.
- Đừng tự đổi từ `LOCAL_QUORUM` sang `LOCAL_ONE` khi đọc kiểm chứng rồi diễn giải hai kết quả là tương đương.

Nếu hệ thống cần “xóa vĩnh viễn thông tin khách hàng”, thao tác CQL và tombstone chỉ là **một phần của vòng đời dữ liệu**. Còn phải xét backup, snapshot, downstream ETL, cache, log và chính sách lưu giữ. Lab này không tự xác nhận yêu cầu xóa dữ liệu pháp lý trên toàn hệ thống.

## 10. Checklist xác minh và chẩn đoán lỗi

| Kiểm tra | Dấu hiệu thành công | Nếu bất thường |
| --- | --- | --- |
| Topology | 3 node cùng DC, RF=3, ban đầu `UN` | Sửa cấu hình lab trước khi thử |
| Ghi baseline | `INSERT` ở `ALL` có ACK cho hai hàng | Không tiếp tục trên baseline không rõ |
| Node down | Đúng `cass-3` là `DN`, hai node khác `UN` | Kiểm tra gossip/network và tên node |
| DELETE | `LOCAL_QUORUM` được ACK khi hai replica còn sống | Ghi `UNKNOWN` nếu timeout; không khẳng định xóa chắc chắn |
| Read trước restart | Chỉ còn mẫu đối chứng tại `LOCAL_QUORUM` | Kiểm tra khóa, write CL, timestamp và lỗi đọc |
| Node restart | Ba node về `UN` | Thu logs startup và recovery |
| Hints/repair | Hoàn tất đồng bộ trong grace cho phạm vi liên quan | Không dựa riêng vào `SELECT`; kiểm tra repair coverage |
| Read cuối | Hàng đích không xuất hiện, mẫu đối chứng vẫn tồn tại | Xem logs, phiên repair, stale replica và update cạnh tranh |
| Vận hành lâu dài | Repair schedule phù hợp grace và downtime | Đánh giá rủi ro zombie và quy trình rebuild/restore |

### Nếu hàng đã xóa “xuất hiện lại”, nên kiểm tra gì?

1. **Khóa và nguồn ghi:** `run_id` có bị dùng lại? Có service nào `INSERT` vào cùng primary key sau DELETE?
2. **Timestamp:** thao tác ghi mới có timestamp cao hơn tombstone không? Có client tự cấp timestamp hoặc đồng hồ lệch đáng kể?
3. **CL và topology:** DELETE đã thực sự ACK ở CL nào, RF thực tế là bao nhiêu, datacenter nào được tính?
4. **Sức khỏe replica:** node nào down và bao lâu, hints có còn, repair bao phủ đủ range không?
5. **Tombstone lifecycle:** `gc_grace_seconds` thực tế, compaction và các cơ chế xóa đã hoạt động ra sao?
6. **Nguồn sự thật:** nếu không còn bằng chứng xóa, tra event log/backup/biên bản nghiệp vụ để xác định giá trị hợp lệ trước khi sửa dữ liệu.

Không nên giải quyết ngay bằng `DELETE` lần nữa rồi coi như xong: hành động đó có thể che mất lỗi thiết kế vận hành và tạo lại nguy cơ tương tự trong lần outage sau.

## 11. Bài thực hành và câu hỏi tư duy

**Bài 1 — ACK và phạm vi bảo đảm.** Chuẩn bị hai hàng ở `ALL`, dừng một replica rồi xóa một hàng ở `LOCAL_QUORUM`. Ghi chính xác client phản hồi thành công hay lỗi. Vì sao `W=2` ở RF=3 vẫn có thể trả ACK khi một replica down?

**Bài 2 — Đọc không thấy có nghĩa gì?** Khi `cass-3` chưa chạy lại, đọc ở `LOCAL_QUORUM` chỉ thấy mẫu đối chứng. Phát biểu nào đúng: “hàng bị xóa được che tại quorum” hay “ba replica đều đã xóa vật lý”? Giải thích.

**Bài 3 — Phục hồi.** Bật lại `cass-3` và chạy repair có kiểm soát trước khi grace có thể hết. Theo dõi logs/metrics và kết quả CQL. Vì sao một lần `SELECT` qua coordinator `cass-3` không đủ chứng minh riêng bản sao local đã sửa xong?

**Bài 4 — Zombie giả định.** Replica nghỉ lâu hơn grace và tombstone ở các node khác đã bị compaction loại. Phân tích điều có thể xảy ra khi replica giữ bản ghi cũ quay về. Nêu bước đánh giá nguồn đáng tin trước khi rebuild/replace node.

**Bài 5 — TTL và thu hồi.** Ghi hàng có TTL 120 giây. Sau 120 giây, không còn thấy hàng khi đọc. Có thể khẳng định đã giải phóng đĩa không? Vì sao?

**Bài 6 — Retry trong Java.** `DELETE` ở `LOCAL_QUORUM` timeout nhưng `SELECT` sau đó không thấy hàng. Bạn có đủ bằng chứng rằng lần gọi DELETE đầu tiên đã được ACK không? Thiết kế log tối thiểu chứa `operation_id`, primary key, CL, thời điểm và loại kết quả để điều tra.

## Ghi nhớ

**Tombstone là thông tin cần thiết để dữ liệu đã xóa không bị hồi sinh từ replica cũ.** Thực nghiệm đúng phải ghi nhận ACK của DELETE, đặt CL phù hợp RF, dừng và phục hồi một replica có kiểm soát, đồng bộ trước khi tombstone bị purge và kiểm tra cả dữ liệu đích lẫn mẫu đối chứng. `gc_grace_seconds` tạo cửa sổ an toàn cho việc truyền dấu xóa, còn hints/repair giúp đồng bộ; một lần `SELECT` không thấy hàng không đồng nghĩa mọi replica đã đồng bộ hoặc dữ liệu đã được thu hồi khỏi đĩa.
