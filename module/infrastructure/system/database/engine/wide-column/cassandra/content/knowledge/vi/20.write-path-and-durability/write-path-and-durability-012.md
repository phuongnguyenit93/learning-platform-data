# Thực nghiệm dừng nút và kiểm chứng dữ liệu đã được xác nhận

## 1. Mục tiêu: “ghi thành công” thực sự có nghĩa gì?

Trong Apache Cassandra, một câu lệnh `INSERT` hoặc `UPDATE` có thể được gửi đến **coordinator** rồi phân phối tới nhiều **replica** theo *partition key*. Khi client nhận phản hồi thành công, câu hỏi quan trọng không chỉ là “lệnh đã chạy chưa”, mà còn là:

- Bao nhiêu replica đã xác nhận ghi theo **write consistency level**?
- Dữ liệu đang nằm ở **commit log**, **memtable** hay đã flush thành **SSTable**?
- Nếu một node dừng đột ngột ngay sau khi trả lời, **những bản sao còn lại** có đáp ứng truy vấn đọc không?
- Nếu node được khởi động lại, dữ liệu được phục hồi qua commit log và đồng bộ giữa các replica như thế nào?
- Có thể chứng minh điều gì từ một lần `SELECT` thành công và điều gì **không thể** suy ra?

Bài học thuộc chương **Đường ghi và độ bền** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nó kết hợp kiến trúc phân tán, mô hình wide-column, partition key, thiết kế bảng theo truy vấn, replication, consistency level, CQL, compaction, repair, xử lý lỗi và kết nối từ Java.

**Mục tiêu thực hành:** trên cluster Cassandra **ba node cùng datacenter**, tạo dữ liệu có mã nhận diện, chỉ xem là “đã xác nhận” khi client thực sự nhận thành công, dừng một node, truy vấn lại bằng các consistency level khác nhau, khởi động lại node và phân tích điều quan sát được. Đây là thí nghiệm kiểm chứng **giới hạn của bảo đảm**, không phải khẳng định rằng một lần thử thành công chứng minh hệ thống không bao giờ mất dữ liệu.

> **Phạm vi an toàn:** chỉ thao tác dừng/khởi động node trong **lab hoặc môi trường thử nghiệm được phép phá hủy**, không thử trên cluster sản xuất. Các câu lệnh Docker ở đây chỉ là ví dụ; tên container, datacenter và cấu hình phải khớp hạ tầng lab.

## 2. Mô hình đường ghi và điều kiện trả ACK

Giả sử ba replica của một partition nằm trên ba node trong một datacenter. Đường ghi đơn giản hóa:

~~~mermaid
sequenceDiagram
    participant Client as Client / Java
    participant C as Coordinator
    participant R1 as Replica 1
    participant R2 as Replica 2
    participant R3 as Replica 3
    Client->>C: INSERT (CL = LOCAL_QUORUM)
    par Gửi tới replica
        C->>R1: Mutation
        C->>R2: Mutation
        C->>R3: Mutation
    end
    Note over R1,R3: Replica xử lý commit log và memtable
    R1-->>C: ACK
    R2-->>C: ACK
    C-->>Client: Success (đủ 2/3 ACK)
    R3-->>C: ACK (có thể đến sau)
~~~

Coordinator **không nhất thiết đợi mọi replica**; số ACK cần đợi phụ thuộc write consistency level. Sau khi xử lý mutation, replica ghi vào **commit log** (phục vụ phục hồi sau khi tiến trình bị dừng) và cập nhật **memtable** trong bộ nhớ. Về sau, memtable được flush xuống **SSTable** trên đĩa, và compaction tổ chức lại SSTable trong nền.

~~~mermaid
flowchart LR
    W["Mutation tới replica"] --> C["Append commit log"]
    C --> M["Cập nhật memtable"]
    M --> A["ACK theo đường ghi"]
    M --> F["Flush khi cần"]
    F --> S["SSTable trên đĩa"]
    S --> K["Compaction trong nền"]
    R["Node khởi động lại"] --> P["Replay commit log hợp lệ"]
    P --> M
~~~

**Phân biệt ACK với flush SSTable:** Cassandra không cần chờ từng mutation trở thành một SSTable trước khi trả lời. Commit log hỗ trợ khôi phục các ghi chưa được flush. Tuy nhiên, **đã append vào commit log** và **đã được fsync xuống thiết bị lưu trữ** là hai mốc khác nhau:

| Cấu hình/khía cạnh | Ý nghĩa với thí nghiệm |
| --- | --- |
| `durable_writes = true` của keyspace | Cho phép dùng commit log để phục hồi ghi chưa flush; đây là lựa chọn nên giữ trong lab độ bền. |
| Commit-log sync **periodic** | Ghi có thể được ACK trước khi commit log được đồng bộ bền vững xuống đĩa; có cửa sổ rủi ro nếu máy hoặc thiết bị lưu trữ mất điện. |
| Commit-log sync **batch** | Đường ACK chờ yêu cầu đồng bộ commit log theo chế độ batch, thường tăng chi phí/độ trễ ghi. |
| Memtable/SSTable | Node có thể khôi phục dữ liệu từ commit log khi memtable chưa flush; SSTable không phải điều kiện cho mỗi ACK. |
| Replica khác | RF và consistency level xác định số bản sao đã phản hồi; điều này khác với độ bền **trên đĩa của từng bản sao**. |

Các tùy chọn sync và mặc định có thể khác giữa phiên bản/cấu hình Cassandra. Trước khi diễn giải kết quả liên quan tới **mất điện/ổ đĩa**, phải kiểm tra cấu hình commit log thực tế của cluster. **Dừng một tiến trình** cũng không mô phỏng đầy đủ việc máy mất điện và cache của hệ điều hành/thiết bị lưu trữ bị mất.

## 3. Dự đoán trước khi chạy: RF và consistency level

Giả sử keyspace có **RF = 3** trong datacenter đang dùng và ba node đều chứa replica cho partition thử nghiệm.

| Write CL | Số xác nhận cần ở RF=3, một DC | Nếu nhận thành công trước khi một node dừng |
| --- | --- | --- |
| `ONE` | Ít nhất **1** replica ACK | Không chứng minh hai replica còn lại đã nhận mutation. |
| `LOCAL_QUORUM` | Ít nhất **2** replica trong local DC ACK | Sau một node dừng, còn ít nhất một bản đã ACK nằm trên các node sống, nếu chỉ một replica hỏng và không có lỗi bổ sung. |
| `ALL` | **3** replica ACK | Cần cả ba node đáp ứng khi ghi; không sẵn sàng ghi `ALL` nếu một replica không thể phản hồi. |

Với `RF = 3`, `W = 2` và `R = 2`, ta có `W + R = 4 > RF = 3`. Hai tập replica đạt quorum **phải giao nhau** ít nhất một replica. Trong điều kiện không có ghi cạnh tranh, xóa, lỗi lưu trữ hoặc cấu hình khác gây bất thường, một lần ghi được ACK ở `LOCAL_QUORUM` có thể được đọc ở `LOCAL_QUORUM` sau khi mất một replica, miễn hai replica còn lại vẫn sẵn sàng.

**Điều cần tránh suy diễn:**

- `ONE` thành công **không đồng nghĩa** dữ liệu chắc chắn mất khi dừng node. Trong mạng ổn định, coordinator thường gửi mutation đến cả ba replica; những replica khác có thể đã nhận. Điều thí nghiệm chứng minh là **mức bảo đảm thấp hơn**, không phải một kịch bản mất dữ liệu bắt buộc.
- `LOCAL_QUORUM` bảo đảm số ACK theo quorum, **không cam kết mọi replica đã cập nhật** và cũng không thay thế sao lưu/khôi phục sau mất nhiều node hoặc thiết bị lưu trữ.
- `ALL` chỉ là yêu cầu số xác nhận lớn hơn; nó giảm khả năng sẵn sàng ghi khi có node lỗi, không làm ứng dụng miễn nhiễm với lỗi đĩa, thao tác xóa hay gửi trùng lệnh.
- Nếu client nhận **timeout**, đừng ghi sổ là “thất bại chắc chắn”: một số replica có thể đã áp dụng mutation dù coordinator không trả thành công. Chỉ gọi là **ACK thành công** nếu client thật sự nhận kết quả thành công.

Với nhiều datacenter, `LOCAL_QUORUM` chỉ tính quorum trong datacenter local; khác với `QUORUM` tính theo tổng replication theo topology. Không dùng bảng số ACK ở trên cho một cấu hình multi-DC khi chưa tính lại RF tại mỗi DC.

## 4. Chuẩn bị lab ba node

### 4.1. Yêu cầu và baseline

Chuẩn bị cluster Cassandra ít nhất **ba node trong cùng một datacenter**, có thể dùng container hoặc VM. Cần có `cqlsh` truy cập một node sống và `nodetool` trên các node. Ví dụ bên dưới giả sử các node/container tên `cass-1`, `cass-2`, `cass-3`, còn datacenter có tên `datacenter1`.

Kiểm tra trạng thái trước thử nghiệm:

~~~bash
# Chạy trên các host/container có nodetool tương ứng.
nodetool status
~~~

Kỳ vọng cả ba node đang ở trạng thái `UN` (*Up/Normal*) và cùng datacenter; không tiếp tục nếu cluster đang bootstrap, di chuyển token, repair lớn hoặc có node ngoài ý muốn đang down. Trong `cqlsh`:

~~~sql
SELECT release_version, data_center, host_id FROM system.local;
~~~

Lưu lại `data_center` thực tế. Nếu khác `datacenter1`, thay tên đó trong lệnh tạo keyspace ở dưới. Ở môi trường nâng cấp hỗn hợp, ghi nhận phiên bản từng node để tránh nhầm khác biệt hành vi/cấu hình.

### 4.2. Keyspace có replication rõ ràng

~~~sql
CREATE KEYSPACE IF NOT EXISTS durability_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

USE durability_lab;
~~~

`NetworkTopologyStrategy` phù hợp khi cấu hình replication theo datacenter. Nếu tên DC khác `datacenter1`, phải thay trong CQL. Câu `IF NOT EXISTS` **không sửa cấu hình của keyspace đã tồn tại**; nếu keyspace có sẵn từ bài thử trước, xác minh replication/durable_writes thay vì mặc định nó đúng:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'durability_lab';
~~~

**Không dùng RF=1** cho thí nghiệm phân biệt write quorum. Nếu chỉ có ba node tổng cộng nhưng một phần partition không có ba replica trong DC local, các giả thiết ở mục 3 không còn áp dụng.

### 4.3. Bảng ghi vết bất biến

~~~sql
CREATE TABLE IF NOT EXISTS ack_probe (
    run_id text,
    seq int,
    marker uuid,
    payload text,
    written_at timestamp,
    PRIMARY KEY ((run_id), seq)
);
~~~

`run_id` là **partition key**, `seq` là clustering key. Mỗi lần thử dùng `run_id` mới; trong một run chỉ ghi một lần cho mỗi `seq`, tránh vô tình ghi đè kết quả cũ. `marker` là UUID cố định gắn với sự kiện thử, giúp đối chiếu chính xác dữ liệu sau khi phục hồi. Không bật TTL, không dùng counter và không đưa phép ghi cạnh tranh vào thí nghiệm đầu tiên, vì chúng làm việc suy luận về dữ liệu đã ACK phức tạp hơn.

Trước khi test, xác nhận người thử nghiệm có quyền dừng một node và có cách bật lại node đó. Ghi lại thời điểm, phiên bản, RF, CL, datacenter, tên node sẽ dừng và trạng thái cluster ban đầu.

## 5. Thí nghiệm A: ghi thành công khi cả ba node đang chạy

Trong `cqlsh` kết nối tới một node đang sống:

~~~sql
USE durability_lab;
~~~

Lệnh `CONSISTENCY` dưới đây là **lệnh của cqlsh**, không phải một câu CQL. Dùng nó để đặt CL cho các câu lệnh kế tiếp.

~~~text
CONSISTENCY ONE
~~~

~~~sql
INSERT INTO ack_probe (run_id, seq, marker, payload, written_at)
VALUES (
    'trial-a-20261121', 1,
    11111111-1111-4111-8111-111111111111,
    'ack-one', toTimestamp(now())
);
~~~

Nếu `cqlsh` xác nhận lệnh **không lỗi**, ghi vào sổ là **ACK ở ONE**. Tiếp tục:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO ack_probe (run_id, seq, marker, payload, written_at)
VALUES (
    'trial-a-20261121', 2,
    22222222-2222-4222-8222-222222222222,
    'ack-local-quorum', toTimestamp(now())
);
~~~

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO ack_probe (run_id, seq, marker, payload, written_at)
VALUES (
    'trial-a-20261121', 3,
    33333333-3333-4333-8333-333333333333,
    'ack-all', toTimestamp(now())
);
~~~

Đọc lại khi cluster còn đủ node:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT seq, marker, payload, written_at
FROM ack_probe
WHERE run_id = 'trial-a-20261121';
~~~

Kết quả dự kiến gồm ba hàng có `marker` và `payload` đúng với dữ liệu ghi. **Chỉ đánh dấu hàng nào “ACK thành công” nếu chính lệnh INSERT tương ứng trả về thành công**. Nếu lệnh timeout hay báo lỗi, ghi `UNKNOWN` và không coi lần `SELECT` sau đó là bằng chứng rằng client đã từng nhận ACK.

### Sổ kết quả nên ghi

| run_id/seq | Write CL | Client nhận | Marker kỳ vọng | Ghi chú |
| --- | --- | --- | --- | --- |
| `trial-a-20261121 / 1` | `ONE` | ACK / TIMEOUT / ERROR | `1111…1111` | Ghi cả thời điểm và node kết nối |
| `trial-a-20261121 / 2` | `LOCAL_QUORUM` | ACK / TIMEOUT / ERROR | `2222…2222` | Đánh dấu chỉ khi có thành công |
| `trial-a-20261121 / 3` | `ALL` | ACK / TIMEOUT / ERROR | `3333…3333` | Kiểm tra cả ba replica đang sẵn sàng |

Đây là baseline để so sánh **sau khi dừng node**. Dùng một `run_id` khác nếu chạy lại toàn bộ bài, vì `INSERT` vào cùng khóa với thời điểm mới có thể che dấu dữ liệu của lần trước.

## 6. Thí nghiệm B: dừng đột ngột một node, đọc từ hai node còn lại

Giả sử các thao tác ghi của thí nghiệm A đã kết thúc. Dừng `cass-3` **mà không drain/flush có chủ đích**:

~~~bash
# Ví dụ khi lab chạy bằng Docker. Thay bằng tên container thực tế.
docker kill --signal=KILL cass-3
~~~

Nếu dùng VM, tương đương là dừng đột ngột tiến trình Cassandra trong **lab**, không yêu cầu shutdown êm. Tác động của `SIGKILL` lên **tiến trình** khác với mất nguồn điện vật lý và việc ổ lưu trữ mất dữ liệu cache; không tuyên bố rằng đây là một bài đo fsync trước mất điện.

**Không dùng `nodetool drain` trước khi dừng** nếu mục tiêu là thử khả năng phục hồi ghi chưa flush: drain đưa memtable xuống SSTable và làm thí nghiệm chuyển thành một tình huống dừng có kiểm soát. `docker stop` thường gửi tín hiệu dừng êm rồi mới ép dừng sau timeout, vì vậy cũng không tương đương hoàn toàn với `docker kill`.

Trên `cass-1` hoặc `cass-2`:

~~~bash
nodetool status
~~~

Đợi cluster phản ánh `cass-3` là down; vẫn còn **hai node `UN`** trong DC local. Kết nối `cqlsh` tới **một trong hai node còn sống**, đặt:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT seq, marker, payload
FROM durability_lab.ack_probe
WHERE run_id = 'trial-a-20261121';
~~~

Với RF=3, một node dừng, hai node còn lại sẵn sàng và những lệnh ghi `LOCAL_QUORUM`/`ALL` ở thí nghiệm A đã **được ACK**, mong đợi thấy ít nhất các hàng `seq=2` và `seq=3`. Hàng `seq=1` (ACK ở `ONE`) **có thể cũng xuất hiện** do các bản sao khác đã nhận mutation; nếu xuất hiện, không được kết luận `ONE` có cùng bảo đảm với quorum.

### Bài đọc phân tích

| Dữ liệu | Bảo đảm từ ACK trước khi dừng | Quan sát cần ghi |
| --- | --- | --- |
| `seq=1` ghi ở `ONE` | Chỉ chắc một replica đã xác nhận | Có/không thấy; không kết luận từ một lần thử |
| `seq=2` ghi ở `LOCAL_QUORUM` | Hai replica đã xác nhận | Dự kiến đọc được ở `LOCAL_QUORUM` khi chỉ một node down |
| `seq=3` ghi ở `ALL` | Cả ba replica đã xác nhận | Dự kiến đọc được ở `LOCAL_QUORUM` trên hai node còn sống |

Nếu một hàng `LOCAL_QUORUM`/**ALL** đã ACK mà không đọc được, **không vội kết luận Cassandra làm mất dữ liệu**. Cần kiểm tra đã thực sự nhận ACK, đã chọn đúng keyspace/run_id, RF/DC, replica còn sống, timeout đọc, lỗi node, ghi/xóa cạnh tranh và cấu hình lab. Trường hợp thực tế bất thường cần thu thập logs/traces trước khi suy luận.

## 7. Thí nghiệm C: ghi khi một node đang down

Giữ `cass-3` tạm thời down. Trên cqlsh kết nối node còn sống, thử ghi một hàng **mới** ở `LOCAL_QUORUM`:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO durability_lab.ack_probe
    (run_id, seq, marker, payload, written_at)
VALUES (
    'trial-b-20261121', 1,
    44444444-4444-4444-8444-444444444444,
    'two-replicas-ack', toTimestamp(now())
);
~~~

Nếu cả hai replica còn sống phản hồi thành công, `LOCAL_QUORUM` đạt **2/3** và có thể trả ACK. Đọc lại cũng ở `LOCAL_QUORUM`:

~~~sql
SELECT marker, payload
FROM durability_lab.ack_probe
WHERE run_id = 'trial-b-20261121' AND seq = 1;
~~~

Sau đó **đổi sang `ALL`** và dùng khóa mới, không ghi đè hàng vừa tạo:

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO durability_lab.ack_probe
    (run_id, seq, marker, payload, written_at)
VALUES (
    'trial-b-20261121', 2,
    55555555-5555-4555-8555-555555555555,
    'all-while-node-down', toTimestamp(now())
);
~~~

Vì một replica không thể xác nhận, **không kỳ vọng lệnh `ALL` được ACK thành công**. Client có thể nhận `Unavailable` hoặc lỗi timeout tùy lúc coordinator nhận biết node đã down và tình huống thực tế.

**Điểm rất quan trọng:** `INSERT` ở `ALL` không nhận ACK **không chứng minh** mutation hoàn toàn không được áp dụng ở các replica còn sống. Nếu sau này bạn đọc thấy `seq=2`, điều đó không mâu thuẫn với việc client từng nhận lỗi: các replica có thể đã xử lý nhưng yêu cầu không đạt consistency level cần thiết. Vì vậy không sử dụng kết quả này để tính số lần xử lý nghiệp vụ theo kiểu “gửi lỗi nghĩa là 0 lần”.

Không chạy `ALL` lặp đi lặp lại bằng cùng khóa chỉ để cố “thấy thành công”. Mỗi thử nghiệm cần marker riêng, nhật ký thời gian và cách đánh giá rõ ràng.

## 8. Khởi động lại node và kiểm chứng

Khởi động lại `cass-3`:

~~~bash
# Chỉ áp dụng khi dùng Docker với tên container như ví dụ.
docker start cass-3
~~~

Kiểm tra:

~~~bash
nodetool status
~~~

Đợi cả ba node về `UN`. Khi khởi động, Cassandra có thể **replay commit log** để khôi phục những mutation đã được ghi log nhưng chưa flush thành SSTable trước khi tiến trình chết. Replica từng tạm dừng cũng có thể nhận dữ liệu thiếu qua **hints** nếu điều kiện và thời hạn lưu hint cho phép; **repair** là cơ chế chủ động để đối chiếu dữ liệu giữa replica. Không giả định hints luôn còn, luôn được bật hoặc đủ để chữa mọi khoảng ngừng.

Đọc từ một coordinator sống:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT seq, marker, payload
FROM durability_lab.ack_probe
WHERE run_id = 'trial-a-20261121';

SELECT seq, marker, payload
FROM durability_lab.ack_probe
WHERE run_id = 'trial-b-20261121';
~~~

**Phân biệt ba kết luận:**

1. `SELECT` thấy `marker` đúng nghĩa là **truy vấn đọc tại CL được chọn đã trả dữ liệu đó**.
2. Điều này **không tự chứng minh** replica `cass-3` đã có bản sao cập nhật đầy đủ, vì coordinator có thể lấy dữ liệu từ replica khác.
3. Việc một lệnh không có ACK sau đó vẫn hiện diện **không biến nó thành lệnh đã ACK** ở thời điểm ban đầu.

Trong một lab nhỏ, có thể thực hiện **repair có kiểm soát** sau khi node trở lại để đồng bộ lại dữ liệu:

~~~bash
# Chạy trên node lab thích hợp; với cluster thực phải có kế hoạch repair.
nodetool repair durability_lab ack_probe
~~~

Repair có thể tốn CPU, I/O và thời gian trên dữ liệu lớn; đừng dùng lệnh này tùy tiện trong production. Trạng thái `UN` và kết quả một lần `SELECT` không tương đương một bằng chứng rằng toàn bộ replica đã đồng bộ, vì vậy cần kết hợp kiểm tra logs/metrics, trạng thái repair và topology khi đánh giá.

### Biên bản kết quả cuối

| Bước | Điều phải lưu |
| --- | --- |
| Trước khi ghi | Phiên bản Cassandra; DC; RF; số node `UN`; cấu hình commit log |
| Sau mỗi write | `run_id`, `seq`, `marker`, CL, thời điểm, **ACK/timeout/error thực nhận** |
| Sau `SIGKILL` | Node bị dừng; thời điểm; `nodetool status`; CL đọc; hàng/marker thấy được |
| Khi còn hai node | ACK `LOCAL_QUORUM`; lỗi của `ALL`; liệu có write không được ACK nhưng đọc thấy |
| Sau khởi động | Trạng thái `UN`, dữ liệu đọc ở từng CL, logs/recovery, repair nếu chạy |
| Kết luận | Phân biệt **bảo đảm lý thuyết**, **điều đã quan sát** và **giới hạn của phép thử** |

## 9. Kết nối Java: lưu ACK và xử lý trạng thái chưa rõ

Trong ứng dụng Java dùng **Apache Cassandra Java Driver 4.x**, tính chính xác của biên bản phụ thuộc vào việc **ghi nhận kết quả từ lời gọi client**, không đoán ACK từ lần đọc về sau. Ví dụ tối giản:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.util.UUID;

public final class DurabilityProbe {
    private final CqlSession session;
    private final PreparedStatement insert;
    private final PreparedStatement select;

    public DurabilityProbe(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO durability_lab.ack_probe " +
            "(run_id, seq, marker, payload, written_at) " +
            "VALUES (?, ?, ?, ?, ?)");
        this.select = session.prepare(
            "SELECT marker, payload FROM durability_lab.ack_probe " +
            "WHERE run_id = ? AND seq = ?");
    }

    public boolean writeAndObserveAck(
            String runId, int seq, UUID marker, String payload) {
        BoundStatement statement = insert.bind(
                runId, seq, marker, payload, Instant.now())
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(false);

        try {
            // Trả về bình thường: client đã nhận phản hồi thành công ở CL yêu cầu.
            session.execute(statement);
            System.out.printf(
                "ACK run=%s seq=%d marker=%s CL=LOCAL_QUORUM%n",
                runId, seq, marker);
            return true;
        } catch (RuntimeException error) {
            // Lỗi/timeout ở client: không suy ra mutation chắc chắn chưa được ghi.
            System.err.printf(
                "UNKNOWN run=%s seq=%d marker=%s error=%s%n",
                runId, seq, marker, error.getClass().getSimpleName());
            return false;
        }
    }

    public void verify(String runId, int seq) {
        Row row = session.execute(select.bind(runId, seq)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM))
            .one();
        if (row == null) {
            System.out.println("NOT OBSERVED at LOCAL_QUORUM");
        } else {
            System.out.printf("OBSERVED marker=%s payload=%s%n",
                row.getUuid("marker"), row.getString("payload"));
        }
    }
}
~~~

**Cách đọc đoạn mã:**

- `writeAndObserveAck` chỉ in `ACK` sau khi `session.execute` trả về bình thường. Nếu bắt lỗi, nhãn là `UNKNOWN`; cần phân loại lỗi chi tiết trong log để phân biệt tình huống khi vận hành.
- `runId + seq + marker` cần ổn định trong toàn bộ một lượt thử. Nếu gửi lại với khóa mới, bạn đang tạo **một sự kiện mới**, không còn thử phục hồi cùng một ghi.
- `setIdempotence(false)` là lựa chọn **thận trọng cho bài thực nghiệm** nhằm tránh client tự phát lại yêu cầu như thể mọi lỗi chắc chắn là chưa ghi. Với câu `INSERT` bình thường có giá trị cố định và không có side effect, ứng dụng sản xuất có thể xây chính sách retry idempotent riêng sau khi hiểu rõ xung đột, timestamp và TTL.
- `verify` chỉ ghi `OBSERVED`, **không suy ra ACK trước đó** và không chứng minh một replica cụ thể đã được đồng bộ.
- Ví dụ trả `false` cho mọi ngoại lệ runtime để báo “chưa có bằng chứng ACK”; trong hệ thống thật cần **phân loại lỗi**, giữ log/traces, tránh che mất lỗi cấu hình và đưa quyết định retry/đối soát vào tầng nghiệp vụ.

Kết quả thực nghiệm nên được lưu ngoài cluster đang gây lỗi, chẳng hạn log ứng dụng hoặc hệ thống giám sát. Nếu chính log ACK chỉ nằm trong node bị dừng thì người thử không có chứng cứ đáng tin cậy về thời điểm client đã nhận thành công.

## 10. Các sai lầm cần tránh khi diễn giải

| Khẳng định thiếu chính xác | Cách hiểu đúng |
| --- | --- |
| “`INSERT` trả thành công nghĩa là mọi replica đã có dữ liệu.” | Chỉ đủ số replica ACK theo write CL; `ALL` mới yêu cầu đủ tất cả replica đã chọn. |
| “ACK nghĩa là dữ liệu đã flush xuống SSTable.” | Commit log và memtable tham gia đường ghi; flush SSTable xảy ra về sau. |
| “`ONE` chắc chắn mất dữ liệu nếu một node chết.” | Không có bảo đảm quorum; nhiều trường hợp replica khác đã nhận nên vẫn đọc được. |
| “`LOCAL_QUORUM` không thể mất dữ liệu trong mọi loại sự cố.” | Vẫn có rủi ro khi mất nhiều bản sao, lỗi lưu trữ, mất điện, cấu hình sync hay ghi/xóa cạnh tranh. |
| “Timeout nghĩa là ghi thất bại và có thể gửi lại an toàn.” | Trạng thái có thể **chưa xác định**; retry phải xét tính idempotent và nghiệp vụ. |
| “Thấy hàng sau khi node lên là node ấy chắc chắn đã có bản sao.” | Coordinator có thể đọc từ node khác; cần quan sát/đối chiếu replica hoặc repair. |
| “`nodetool drain` là cách thử crash chưa flush.” | Drain là dừng có kiểm soát và có thể flush memtable. |
| “`SIGKILL` chứng minh độ bền trước mất điện.” | Nó chỉ giết tiến trình; cache OS/ổ đĩa có thể vẫn tồn tại. |
| “Repair khôi phục mọi dữ liệu bị mất.” | Repair đối chiếu dữ liệu còn có ở replica; không tái tạo dữ liệu đã mất trên **mọi** bản sao. |
| “Nâng read CL lên `ALL` luôn tốt hơn.” | `ALL` giảm tính sẵn sàng khi node lỗi; cần chọn CL theo yêu cầu và RF thực tế. |

## 11. Bài tập mở rộng

### Bài 1 — So sánh ACK với dữ liệu quan sát

Chạy thí nghiệm A đến C, lập bảng ghi đủ `seq`, `marker`, write CL, read CL, trạng thái node và phản hồi. Chỉ tô dấu “đã ACK” nếu **client nhận thành công**. Giải thích vì sao `seq=1` của `ONE` có thể vẫn hiện diện sau khi node down và vì sao không dùng lần quan sát này để nâng bảo đảm của `ONE` lên quorum.

### Bài 2 — Tình huống W+R > RF

Với RF=3 trong một DC, hãy tính `W+R` cho:

- `W=1, R=1`: không bảo đảm hai tập replica giao nhau.
- `W=2, R=2`: tổng bằng 4 lớn hơn 3; có giao nhau.
- `W=3, R=1`: tổng bằng 4 lớn hơn 3; có giao nhau nếu thao tác đọc/ghi có đủ replica đáp ứng.

Thảo luận **tính sẵn sàng** khi một node down: `W=3` không thể thành công, trong khi `W=2` có thể thành công nếu hai replica còn lại khỏe. Giao nhau là một phần của mô hình nhất quán; vẫn cần xét cập nhật đồng thời, tombstone, timeout và topology.

### Bài 3 — Mất điện so với SIGKILL

Viết bảng dự đoán cho cấu hình commit-log sync `periodic` và `batch`. Phân biệt trường hợp:

1. Tiến trình Cassandra chết nhưng host/OS và bộ nhớ đệm lưu trữ vẫn hoạt động.
2. Toàn bộ host mất điện ngay sau ACK.
3. Hai trong ba node mất khả năng truy cập đồng thời.

Không biến dự đoán thành cam kết bảo đảm tuyệt đối nếu chưa xác nhận cấu hình, loại storage và cơ chế fsync thực tế.

### Bài 4 — Sự cố thật cần điều tra gì?

Giả sử `LOCAL_QUORUM` đã trả ACK nhưng `SELECT` sau một node down báo timeout. Bạn cần kiểm tra **read consistency**, số replica sống và mapping DC, logs node/coordinator, trạng thái kết nối, tombstone, timeout và kết quả ghi/xóa cạnh tranh trước khi nghi ngờ mất dữ liệu. Hãy viết checklist phục hồi dựa trên dấu vết và xác định khi nào cần repair.

### Bài 5 — Đưa nguyên tắc vào API Java

Thiết kế một API có kết quả `ACKNOWLEDGED`, `NOT_ACKNOWLEDGED` (chỉ khi có bằng chứng rõ ràng) và `UNKNOWN`; lưu `operation_id` ổn định cho nghiệp vụ. Giải thích vì sao đọc thấy dữ liệu sau timeout không chứng minh được chính **lần gọi client trước đó** đã nhận ACK, và vì sao một phép tăng counter hoặc tác vụ ngoài Cassandra không thể retry tùy ý.

## Ghi nhớ

**Một write ACK trong Cassandra là xác nhận đủ số replica theo consistency level đã chọn; nó không tự đồng nghĩa với việc mọi replica đã cập nhật hay mọi byte đã được fsync.** Để kiểm chứng, phải ghi lại ACK thực nhận, dùng dữ liệu có marker ổn định, dừng đúng một node trong lab, đọc bằng CL được xác định, khởi động lại và quan sát quá trình phục hồi/repair. So sánh RF=3 với `ONE`, `LOCAL_QUORUM` và `ALL` cho thấy sự đánh đổi giữa độ nhất quán được bảo đảm, độ bền theo loại sự cố và tính sẵn sàng khi node không hoạt động.
