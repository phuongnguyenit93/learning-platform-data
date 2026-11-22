# Thực nghiệm lỗi từng phần và đối chiếu kết quả ghi nhiều bản

**Chương:** BATCH và counter  
**Phạm vi:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`

Bài thuộc nội dung: *Hiểu kiến trúc phân tán và mô hình wide-column của Apache Cassandra, đặc biệt khóa phân vùng, thiết kế bảng theo truy vấn và mức nhất quán đọc ghi. Thực hành CQL, replication, compaction, repair, xử lý lỗi và kết nối từ ứng dụng Java.*

Một thao tác nghiệp vụ thường cần ghi nhiều hàng, chẳng hạn lưu trạng thái đơn hàng, bản sao phục vụ truy vấn và dấu vết xử lý. Trong Cassandra, các hàng có thể nằm ở **nhiều partition**; mỗi partition lại có **nhiều replica**. Khi một node hoặc kết nối lỗi, hai loại “thiếu” này dễ bị nhầm lẫn: thiếu một hàng trong nhóm lệnh ghi và thiếu phiên bản mới trên một replica. Bài thực nghiệm cách tạo tình huống lỗi, quan sát kết quả ở nhiều mức nhất quán và quyết định có được phép gửi lại lệnh hay không.

## 1. Mục tiêu và mô hình quan sát

Sau bài này, bạn có thể:

1. Giải thích vì sao `BATCH` nhiều partition không tương đương transaction ACID của cơ sở dữ liệu quan hệ.
2. Phân biệt `LOGGED BATCH`, `UNLOGGED BATCH`, `COUNTER BATCH` khi gặp lỗi, đặc biệt sau timeout.
3. Dùng khóa truy vấn cụ thể để đối chiếu **từng hàng** của một lần ghi, tránh kết luận từ một truy vấn tổng hợp thiếu chính xác.
4. Nhận biết khác biệt giữa phản hồi của client, dữ liệu đọc tại `ONE`/`LOCAL_QUORUM`/`ALL` và trạng thái trên các replica.
5. Thiết kế retry/reconciliation an toàn cho ghi thông thường, đồng thời tránh cộng counter hai lần.

**Hai trục cần kiểm tra độc lập:**

| Trục | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Nhiều **bản ghi logic** | Các hàng A, B, C thuộc ba partition đã được ghi đủ chưa? | A có, B có, C thiếu sau lỗi giữa chừng. |
| Nhiều **bản sao vật lý** | Với cùng hàng A, replica nào đã nhận phiên bản mới? | Hai replica có A mới, replica thứ ba tạm thời còn A cũ. |

Coordinator là node nhận yêu cầu và điều phối; nó không nhất thiết là replica chứa khóa. `cqlsh` kết nối tới một node **không** đồng nghĩa đọc trực tiếp dữ liệu trên đĩa của node đó.

## 2. Cam kết thực tế của các loại batch

| Cách ghi | Cơ chế khi có lỗi | Điều **không** được suy ra |
| --- | --- | --- |
| `BEGIN BATCH` (logged, mặc định) qua nhiều partition | Cassandra ghi **batchlog** trước khi phát các mutation; nếu batchlog được lưu thành công, các mutation còn thiếu có thể được phát lại để hoàn tất về sau. | Không có isolation xuyên partition; không có rollback tức thời; timeout không chứng minh “chưa ghi”. |
| `BEGIN UNLOGGED BATCH` qua nhiều partition | Không có batchlog bảo đảm phát lại cả nhóm. Một số mutation có thể được áp dụng trong khi mutation khác thất bại. | Một lệnh `APPLY BATCH` không làm nhiều partition trở thành transaction. |
| Nhiều lệnh `INSERT`/`UPDATE` riêng | Mỗi lệnh có phản hồi và lỗi riêng; ứng dụng chịu trách nhiệm trạng thái hoàn thành của toàn nghiệp vụ. | Phản hồi thành công của A không bảo đảm B, C thành công. |
| `BEGIN COUNTER BATCH` | Gộp các phép cập nhật counter theo cú pháp chuyên dụng; phép cộng là **không idempotent**. | Gửi lại sau timeout có thể cộng thêm lần nữa; không được trộn cập nhật counter với batch thông thường. |

**Atomicity cuối cùng không phải isolation tại thời điểm đọc.** Với logged batch nhiều partition, hệ thống hướng tới hoàn tất mọi mutation đã được ghi vào batchlog, nhưng trong thời gian ghi/phát lại, một client khác vẫn có thể quan sát A mới và B cũ. Cassandra không tạo snapshot chung xuyên các partition cho câu lệnh đọc của bạn.

**Phản hồi timeout là trạng thái “chưa biết”.** Có thể yêu cầu chưa tới coordinator, đã tới nhưng chưa ghi, đã ghi một phần, hoặc đã ghi đủ nhưng phản hồi bị mất. Các exception như `WriteTimeoutException`, `UnavailableException` hay lỗi kết nối có ý nghĩa riêng về thời điểm lỗi; không exception nào tự chứng minh mọi mutation đã được rollback. Cần lưu cả *loại lỗi* và *số lần gửi*.

**Consistency level áp dụng cho từng ghi/đọc trên replica.** Ví dụ RF = 3 trong một datacenter: `LOCAL_QUORUM` cần hai replica đáp ứng trong datacenter đó; `ALL` cần cả ba; `ONE` chỉ cần một. Mức nhất quán này không thay thế batchlog và không tạo isolation giữa nhiều partition. Với hai thao tác đọc/ghi cùng khóa không có ghi cạnh tranh, quorum đọc và quorum ghi giúp tránh đọc một bản sao cũ; không nên suy rộng thành transaction tuyến tính hóa cho toàn bộ batch.

## 3. Môi trường và phép đo

Dùng **cluster thử nghiệm riêng** gồm ba node Cassandra trong cùng datacenter, ví dụ `datacenter1`. Các lệnh dừng node bên dưới chỉ dành cho cluster này. Cassandra 4.1/5.x và `cqlsh` phù hợp với bài; kiểm tra tên datacenter và container thực tế trước khi chạy.

```bash
# Ví dụ tên container: cassandra1, cassandra2, cassandra3
docker exec cassandra1 nodetool status
docker exec -it cassandra1 cqlsh
```

Trong `cqlsh`:

```sql
SELECT data_center, release_version FROM system.local;
```

Chỉ tiếp tục khi cả ba node có trạng thái `UN` trong `nodetool status`. Thay `datacenter1` trong các câu `CREATE KEYSPACE` nếu kết quả thực tế khác. Hạn chế test trên cùng cluster có tải thật vì restart node, tạo counter và repair có thể ảnh hưởng tới dữ liệu khác.

Tạo hai keyspace riêng để tách **lỗi ở từng partition** và **độ trễ của các replica**:

```sql
-- RF=1 chỉ dùng để tạo lỗi dễ thấy trong phòng thí nghiệm.
CREATE KEYSPACE IF NOT EXISTS lab_batch_r1
WITH replication = {'class': 'NetworkTopologyStrategy', 'datacenter1': 1}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS lab_batch_r1.copies_by_key (
    copy_key text PRIMARY KEY,
    attempt_id text,
    copy_no int,
    payload text
);

-- RF=3 để khảo sát ONE, LOCAL_QUORUM, ALL trong một DC.
CREATE KEYSPACE IF NOT EXISTS lab_batch_r3
WITH replication = {'class': 'NetworkTopologyStrategy', 'datacenter1': 3}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS lab_batch_r3.copies_by_key (
    copy_key text PRIMARY KEY,
    attempt_id text,
    copy_no int,
    payload text
);

CREATE TABLE IF NOT EXISTS lab_batch_r3.counters_by_key (
    counter_key text PRIMARY KEY,
    total counter
);
```

Ở đây `copy_key` là **partition key**. Ba khóa `ok12-a`, `ok12-b`, `ok12-c` là ba partition khác nhau, dù cùng `attempt_id`. Thiết kế khóa cố ý đơn giản để dễ phân phối các partition và đọc lại từng hàng. Không dùng `SELECT *` để quét toàn bộ bảng hoặc giả định lọc theo `attempt_id` là hợp lệ.

### Mẫu ghi nhận kết quả

Trước khi làm lỗi, chuẩn bị một bảng nhật ký thí nghiệm, ghi thời điểm và phản hồi thực tế:

| Thông tin cần lưu | Ví dụ giá trị |
| --- | --- |
| `attempt_id`, khóa A/B/C | `u12`: `u12-a`, `u12-b`, `u12-c` |
| Kiểu batch, RF, write CL | UNLOGGED, RF=1, ONE |
| Sự cố và thời điểm | Node giữ khóa C dừng trước/lúc gửi |
| Phản hồi client | success / timeout / unavailable + thông báo |
| Kết quả mỗi khóa sau khôi phục | A=present, B=present, C=absent |
| Read CL, thời điểm kiểm tra | ONE tại t1, LOCAL_QUORUM tại t2 (khi RF=3) |

Hàng ví dụ chỉ mô tả **cách ghi nhật ký**, không phải kết quả chắc chắn của một lần chạy.

## 4. Đối chứng: ghi đủ ba partition khi không có lỗi

Trong `cqlsh`, chọn `CONSISTENCY ONE` cho keyspace RF=1:

```sql
CONSISTENCY ONE

BEGIN UNLOGGED BATCH
    INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('ok12-a', 'ok12', 1, 'v1');
    INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('ok12-b', 'ok12', 2, 'v1');
    INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('ok12-c', 'ok12', 3, 'v1');
APPLY BATCH;

SELECT copy_key, attempt_id, payload
FROM lab_batch_r1.copies_by_key WHERE copy_key = 'ok12-a';
SELECT copy_key, attempt_id, payload
FROM lab_batch_r1.copies_by_key WHERE copy_key = 'ok12-b';
SELECT copy_key, attempt_id, payload
FROM lab_batch_r1.copies_by_key WHERE copy_key = 'ok12-c';
```

Khi `APPLY BATCH` thành công và các node khỏe, ba truy vấn thông thường đều thấy `v1`. Kết quả này chứng minh **lần chạy cụ thể** hoàn tất; nó không biến unlogged batch thành nguyên tử trước mọi lỗi.

Thử một **đối chứng lỗi ứng dụng có chủ đích**: ghi hai lệnh độc lập dưới `attempt_id = 'control12'` rồi giả lập process dừng, bỏ qua lệnh thứ ba.

```sql
INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
VALUES ('control12-a', 'control12', 1, 'v1');
INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
VALUES ('control12-b', 'control12', 2, 'v1');

-- Cố ý KHÔNG ghi control12-c.
SELECT * FROM lab_batch_r1.copies_by_key WHERE copy_key = 'control12-a';
SELECT * FROM lab_batch_r1.copies_by_key WHERE copy_key = 'control12-b';
SELECT * FROM lab_batch_r1.copies_by_key WHERE copy_key = 'control12-c';
```

Đây là **đối chứng về hình dạng kết quả thiếu một phần**, không phải ví dụ lỗi nội bộ `BATCH`. Sau khi xác nhận A/B tồn tại và C vắng, ta có mốc để so sánh với các thí nghiệm batch thật.

## 5. Thử lỗi phân vùng với UNLOGGED BATCH

### 5.1. Chọn khóa nằm trên những node khác nhau

Với RF=1, mỗi partition chỉ có một replica. Dùng `nodetool getendpoints` để xem node sở hữu khóa; có thể chạy trên bất kỳ node còn sống nào:

```bash
docker exec cassandra1 nodetool getendpoints lab_batch_r1 copies_by_key u12-a
docker exec cassandra1 nodetool getendpoints lab_batch_r1 copies_by_key u12-b
docker exec cassandra1 nodetool getendpoints lab_batch_r1 copies_by_key u12-c
```

Nếu cả ba khóa rơi vào cùng node, đổi hậu tố khóa (ví dụ `u12-d`, `u12-e`) và **thay đồng nhất** trong mọi lệnh bên dưới. Chọn ít nhất một khóa nằm trên node sẽ dừng và ít nhất một khóa trên node vẫn hoạt động. Giữ coordinator `cqlsh` trên một node **khác** node sắp dừng.

### 5.2. Gửi batch khi một node chứa khóa không khả dụng

Ví dụ chỉ dừng `cassandra3` khi nó là replica RF=1 của ít nhất một khóa đã chọn:

```bash
docker stop cassandra3
docker exec cassandra1 nodetool status
```

Trên `cqlsh` nối tới node sống:

```sql
CONSISTENCY ONE

BEGIN UNLOGGED BATCH
    INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('u12-a', 'u12', 1, 'v1');
    INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('u12-b', 'u12', 2, 'v1');
    INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('u12-c', 'u12', 3, 'v1');
APPLY BATCH;
```

**Ghi nguyên văn phản hồi**, kể cả khi là `Unavailable` hoặc timeout. Thời điểm Cassandra nhận biết replica mất và cách coordinator phát các mutation có thể làm yêu cầu bị từ chối **trước khi** ghi hàng nào, hoặc đã áp dụng được một vài hàng. Vì vậy, một lần chạy không bắt buộc tạo kết quả thiếu một phần. Có thể thử lại với `attempt_id`/khóa mới và gây lỗi đúng lúc có ghi đang bay qua mạng. Không tái sử dụng khóa của lượt trước, vì hàng còn tồn tại sẽ che lấp kết quả.

Khôi phục node rồi đợi `nodetool status` báo cả ba node `UN`:

```bash
docker start cassandra3
docker exec cassandra1 nodetool status
```

Đọc **từng khóa** tại `ONE` trên RF=1:

```sql
CONSISTENCY ONE

SELECT * FROM lab_batch_r1.copies_by_key WHERE copy_key = 'u12-a';
SELECT * FROM lab_batch_r1.copies_by_key WHERE copy_key = 'u12-b';
SELECT * FROM lab_batch_r1.copies_by_key WHERE copy_key = 'u12-c';
```

Điền kết quả thật vào bảng nhật ký. Nếu A/B có và C không có, đã quan sát lỗi từng phần của một thao tác nghiệp vụ gồm nhiều partition. Nếu cả ba có, cũng **không được suy ra** unlogged batch bảo đảm atomicity: các ghi có thể đã thành công, hoặc cơ chế khác như **hinted handoff** đã chuyển dữ liệu tới replica sau khi node hồi phục. Hinted handoff không phải batchlog và không cho cam kết “cả nhóm hoặc không hàng nào”. Nếu cả ba thiếu, yêu cầu có thể đã bị từ chối trước khi phát mutation.

> **Điểm kiểm chứng:** “Client báo lỗi” và “không có hàng” là hai thông tin khác nhau. Tập hợp đủ A/B/C và đo sau khôi phục mới giúp mô tả điều đã xảy ra; riêng mã lỗi chưa đủ.

## 6. So sánh LOGGED BATCH và tình trạng nhìn thấy giữa các replica

### 6.1. Ghi logged batch trên RF=3

Khởi động lại mọi node trước khi thực hiện. Trong `cqlsh`:

```sql
CONSISTENCY LOCAL_QUORUM

BEGIN BATCH
    INSERT INTO lab_batch_r3.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('r312-a', 'r312', 1, 'v1');
    INSERT INTO lab_batch_r3.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('r312-b', 'r312', 2, 'v1');
    INSERT INTO lab_batch_r3.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('r312-c', 'r312', 3, 'v1');
APPLY BATCH;

SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r312-a';
SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r312-b';
SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r312-c';
```

`BEGIN BATCH` không có từ khóa `UNLOGGED` là logged batch. Với ba partition khác nhau, coordinator phải quản lý nhiều mutation; batchlog hỗ trợ **hoàn tất về sau** nếu xảy ra lỗi sau khi batchlog đã được ghi bền vững. Điều đó không làm ba hàng có mặt đồng thời đối với mọi client.

### 6.2. Ghi khi một replica tạm ngừng

Dừng một node trong **cluster RF=3** (ví dụ `cassandra3`), giữ hai node sống:

```bash
docker stop cassandra3
docker exec cassandra1 nodetool status
```

Gửi một logged batch mới, dùng `LOCAL_QUORUM`:

```sql
CONSISTENCY LOCAL_QUORUM

BEGIN BATCH
    INSERT INTO lab_batch_r3.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('r3down12-a', 'r3down12', 1, 'v2');
    INSERT INTO lab_batch_r3.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('r3down12-b', 'r3down12', 2, 'v2');
    INSERT INTO lab_batch_r3.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('r3down12-c', 'r3down12', 3, 'v2');
APPLY BATCH;

SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r3down12-a';
SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r3down12-b';
SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r3down12-c';
```

Nếu hai replica trong datacenter còn đáp ứng, ghi và đọc tại `LOCAL_QUORUM` có thể thành công dù replica thứ ba ngừng. Thử chuyển sang `CONSISTENCY ALL` và đọc cùng khóa khi node vẫn tắt: yêu cầu thường không khả dụng vì không đủ ba replica; **lỗi đọc không đồng nghĩa bản ghi đã biến mất**.

```sql
CONSISTENCY ALL
SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r3down12-a';
```

Khởi động lại node, đợi trạng thái `UN`, rồi đọc tại `ONE` và `LOCAL_QUORUM`:

```bash
docker start cassandra3
docker exec cassandra1 nodetool status
```

```sql
CONSISTENCY ONE
SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r3down12-a';

CONSISTENCY LOCAL_QUORUM
SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r3down12-a';
```

Replica vừa hồi phục có thể tạm thời chậm cập nhật. Đọc tại `ONE` **có khả năng** gặp phiên bản cũ nếu coordinator chọn replica đó; không nhất thiết xảy ra mỗi lần. Đọc tại `LOCAL_QUORUM` trong tình huống không có ghi cạnh tranh đối chiếu nhiều replica và thường thấy giá trị đã được quorum xác nhận. Hinted handoff, read repair (tùy phiên bản) và anti-entropy repair có thể giúp các replica hội tụ; chúng hoạt động ở tầng replica, khác chức năng batchlog ở tầng nhóm mutation.

Để kiểm tra **cụ thể replica nào** giữ dữ liệu, không dùng mẹo “đăng nhập `cqlsh` vào node đó rồi `SELECT`”: truy vấn vẫn qua coordinator và có thể được phục vụ từ replica khác. Việc xác minh tại từng node cần công cụ vận hành/tracing phù hợp, phân tích SSTable trong môi trường lab hoặc dữ liệu telemetry tương ứng; `CONSISTENCY ONE` không ghim vào một node tùy chọn.

### 6.3. Lỗi coordinator ngay sau khi gửi

Để quan sát timeout không rõ kết quả đối với logged batch, phát nhiều lượt ghi **khóa duy nhất** từ ứng dụng thử nghiệm (xem mục Java) rồi dừng coordinator trong lúc đang có yêu cầu. Khởi động lại node và đối chiếu tất cả khóa qua nhiều lần đọc. Một lượt có thể:

- Đã trả success: kiểm tra đủ hàng ở write CL đã chọn.
- Báo timeout/mất kết nối: kiểm tra từng khóa; lúc đầu có thể chưa đủ và sau đó hội tụ nếu batchlog đã được ghi và phát lại thành công.
- Không tạo hàng nào: yêu cầu có thể chưa được nhận hoặc bị từ chối trước khi lưu batchlog.

Không có cách đáng tin cậy để dùng **một** lệnh `docker stop` đúng sát thời điểm nội bộ ghi batchlog trong mọi lần chạy. Không xem một mẫu quan sát đơn lẻ là bằng chứng về thứ tự sự kiện nếu chưa có log/tracing. Cũng không ấn định thời hạn phát lại tuyệt đối: tốc độ phục hồi phụ thuộc cấu hình, tình trạng cluster và thời điểm lỗi.

## 7. COUNTER BATCH: thử lại có thể làm tăng hai lần

Counter có cơ chế cập nhật riêng. Không tạo counter trong bảng hàng thông thường và không trộn `UPDATE ... + 1` vào logged/unlogged batch chứa `INSERT` thường. Với RF=3 và cluster khỏe:

```sql
CONSISTENCY LOCAL_QUORUM

BEGIN COUNTER BATCH
    UPDATE lab_batch_r3.counters_by_key
    SET total = total + 1 WHERE counter_key = 'counter12-a';
    UPDATE lab_batch_r3.counters_by_key
    SET total = total + 1 WHERE counter_key = 'counter12-b';
APPLY BATCH;

SELECT total FROM lab_batch_r3.counters_by_key
WHERE counter_key = 'counter12-a';
SELECT total FROM lab_batch_r3.counters_by_key
WHERE counter_key = 'counter12-b';
```

Ở lần ghi đầu tiên, nếu thành công và chưa có cập nhật khác, mỗi counter thường bằng 1. **Chạy lại nguyên vẹn counter batch trên** để mô phỏng việc ứng dụng retry sau một timeout không rõ kết quả. Nếu cả hai lần đều được áp dụng, mỗi counter thành 2. Cùng khóa và cùng câu CQL không làm phép `+ 1` trở thành idempotent.

Với lỗi mạng thật, có thể một hoặc nhiều phép cộng chưa được áp dụng lúc đọc, cũng có thể một phép cộng đã áp dụng dù client chưa nhận phản hồi. Sau timeout, không thể quyết định “gửi lại” chỉ bằng cách nhìn một counter tại một thời điểm, nhất là khi có client ghi đồng thời.

**Quy tắc ứng dụng:** không bật retry mù cho counter update. Nếu cần đếm chính xác mỗi sự kiện **một lần**, cân nhắc ghi sự kiện bất biến với `event_id` duy nhất và xây dựng giá trị tổng hợp có cơ chế dedup/đối soát; hoặc chọn hệ thống có transaction phù hợp cho yêu cầu exactly-once. Một “đã xử lý event” ở bảng khác và một counter update **không tự động** trở thành transaction xuyên hai partition.

## 8. Đối chiếu sau lỗi từ ứng dụng Java

Với Java Driver 4.x, cố định `attempt_id` và **khóa của từng bản ghi** trước khi gửi. Ví dụ sau dùng các `INSERT` xác định cùng khóa và payload, nên việc gửi lại cùng giá trị có thể đưa dữ liệu về trạng thái mong muốn **khi không có writer cạnh tranh**. Nó không phù hợp với counter hay cập nhật cộng dồn.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DriverException;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;

import java.util.List;

public final class BatchCheck {
    public static void run(CqlSession session, String attemptId) {
        PreparedStatement insert = session.prepare(
            "INSERT INTO lab_batch_r3.copies_by_key " +
            "(copy_key, attempt_id, copy_no, payload) VALUES (?, ?, ?, ?)"
        );

        var builder = BatchStatement.builder(DefaultBatchType.LOGGED)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        List<String> keys = List.of(
            attemptId + "-a", attemptId + "-b", attemptId + "-c"
        );

        for (int i = 0; i < keys.size(); i++) {
            builder.addStatement(insert.bind(keys.get(i), attemptId, i + 1, "v1"));
        }

        try {
            session.execute(builder.build());
            System.out.println("Batch acknowledged: " + attemptId);
        } catch (DriverException ex) {
            System.err.println("Unknown outcome: " + attemptId + " / " + ex);
        }

        // Kiểm tra từng partition, kể cả sau exception.
        PreparedStatement read = session.prepare(
            "SELECT payload FROM lab_batch_r3.copies_by_key WHERE copy_key = ?"
        );
        for (String key : keys) {
            Row row = session.execute(
                read.bind(key)
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            ).one();
            System.out.println(key + " -> " +
                (row == null ? "<absent>" : row.getString("payload")));
        }
    }
}
```

Điều chỉnh contact points, datacenter, phiên bản driver và cấu hình timeout theo cluster của bạn. Một lỗi đọc lúc đối soát vẫn phải được ghi lại như lỗi đọc, **không** ghi `absent` nếu truy vấn chưa hoàn thành. Với dữ liệu thay đổi đồng thời, ghi lại phiên bản/`event_id` để xác định giá trị nào là đúng trước khi bù.

Đối với các phép `INSERT`/`UPDATE` ghi cùng giá trị ổn định vào cùng khóa, quy trình phục hồi thực tế thường là: lưu `attempt_id` → gửi → nếu kết quả không rõ, đọc lại từng khóa tại CL phù hợp → bù riêng khóa thiếu hoặc tái gửi thao tác đã xác minh idempotent → đối chiếu lần cuối. Đừng dùng cùng cơ chế này cho counter vì bù thiếu từ một lần đọc không đủ bảo đảm không cộng trùng.

## 9. Bảng diễn giải kết quả thường gặp

| Quan sát | Giải thích có thể có | Việc cần kiểm chứng |
| --- | --- | --- |
| Client báo timeout, A/B/C đều có | Ghi hoàn tất nhưng phản hồi mất; hoặc hoàn tất sau khi client timeout. | Đọc ở CL phù hợp, xem timestamp và số lần gửi. |
| Client báo lỗi, A/B có, C thiếu | Ghi nhiều partition bị lỗi từng phần; hoặc một replica của C chưa đáp ứng ở thời điểm đọc. | Phân biệt partition và replica; xem RF/CL, truy vấn từng khóa, kiểm tra lại khi node khỏe. |
| `ALL` không đọc được khi một node tắt | Không đủ replica đáp ứng ở CL đã chọn. | Kiểm tra `nodetool status`; đừng kết luận dữ liệu bị xóa. |
| `ONE` đôi khi trả bản cũ, `LOCAL_QUORUM` trả bản mới | Replica chưa hội tụ hoặc còn độ trễ trong lan truyền/phục hồi. | Kiểm tra các ghi cạnh tranh, hint/repair và thời điểm đọc. |
| Counter từ 1 thành 2 sau retry | Hai phép cộng đã được áp dụng. | Xác định số lần gửi và chính sách retry; không giảm counter tùy tiện nếu có ghi đồng thời. |
| Logged batch sau timeout ban đầu thiếu, sau đó đủ | Có thể do batchlog replay hoặc cơ chế phục hồi replica, tùy ca. | Dùng log/tracing để xác định cơ chế; đừng gán nguyên nhân chỉ từ SELECT. |

Đối với một write đã được client xác nhận ở `LOCAL_QUORUM` trên RF=3, sau đó một lần đọc cũng tại `LOCAL_QUORUM` nhưng gặp node lỗi và không có hai replica hoạt động, truy vấn có thể **thất bại**. Tính nhất quán không xóa bỏ yêu cầu về tính sẵn sàng.

## 10. Checklist thực hành và câu hỏi tự kiểm tra

- [ ] Ghi riêng `attempt_id`, ba `copy_key` và thời điểm của **mỗi** lượt.
- [ ] Xác nhận ba node `UN`, datacenter và RF trước khi tạo tình huống lỗi.
- [ ] Có đối chứng không lỗi và đối chứng ứng dụng dừng giữa ba lệnh.
- [ ] Đã quan sát UNLOGGED BATCH ở RF=1 và ghi cả trường hợp không tạo partial.
- [ ] Đã phân biệt lỗi `ALL` do thiếu replica với hàng thực sự vắng mặt.
- [ ] Đã thử hai lần `COUNTER BATCH` và giải thích tại sao không retry mù.
- [ ] Mọi kết luận về đủ/thiếu đều dựa trên ba truy vấn theo partition key, với CL và thời điểm rõ ràng.

**Tự giải thích bằng dữ liệu của chính bạn:**

1. Vì sao `BEGIN BATCH` thành công không đồng nghĩa một client khác luôn đọc được snapshot A/B/C đồng thời?
2. Một lần `WriteTimeoutException` có đủ chứng minh mọi hàng đều chưa được lưu không? Cần bổ sung bằng chứng nào?
3. Khi một node RF=3 ngừng, tại sao `LOCAL_QUORUM` vẫn có thể thành công còn `ALL` không?
4. Khi chạy lại đúng câu `UPDATE total = total + 1`, vì sao kết quả khác với gửi lại một `INSERT` cùng khóa/cùng giá trị?
5. Nếu lần chạy UNLOGGED trả lỗi nhưng sau khi node phục hồi cả ba hàng đều xuất hiện, điều đó **có** chứng minh unlogged batch có batchlog không? Vì sao?

**Điều cần ghi nhớ:** Trước khi sửa dữ liệu sau lỗi, hãy xác định bạn đang đối chiếu **nhiều hàng logic**, **nhiều replica của một hàng**, hay **hai vấn đề cùng lúc**. Dùng batchlog để hiểu cam kết phát lại, consistency level để hiểu phản hồi replica và `attempt_id` để đối soát nghiệp vụ. Riêng phép cộng counter phải được coi là thao tác có thể bị áp dụng lặp nếu retry không kiểm soát.

