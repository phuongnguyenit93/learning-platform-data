# Điều kiện thu hồi tombstone trong compaction

> **Chương:** Tombstone và thu hồi  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra và cơ sở dữ liệu phân tán wide-column: partition key, thiết kế bảng theo truy vấn, mức nhất quán đọc/ghi, CQL, replication, compaction, repair, xử lý lỗi và kết nối Java.

Khi chạy `DELETE` hoặc để một giá trị hết hạn TTL trong Apache Cassandra, dữ liệu thường **không biến mất ngay khỏi tất cả SSTable**. Cassandra ghi thông tin xóa gọi là **tombstone** để những bản sao và các SSTable chứa giá trị cũ không thể làm giá trị ấy xuất hiện trở lại. Tombstone chỉ có thể được loại bỏ vật lý khi hệ thống có đủ điều kiện về **thời gian**, **quan hệ với dữ liệu nằm trong các SSTable khác** và **an toàn đồng bộ giữa các replica**.

Chủ đề này dễ bị hiểu sai qua câu: “Đợi hết `gc_grace_seconds` là tombstone sẽ được xóa.” Thực tế, hết thời gian grace mới là **một điều kiện cần**. Compaction có thể không chạy ngay; khi chạy, nó vẫn phải tránh để lộ một giá trị cũ chưa bị loại bỏ. Thêm nữa, compaction trên một node không thể tự xác nhận rằng tất cả replica khác đã nhận được thao tác xóa.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `DELETE` tạo tombstone và TTL hết hạn cũng có hệ quả tương tự.
2. Phân biệt **hàng không còn hiển thị khi đọc**, **tombstone đủ tuổi**, và **tombstone đã thực sự được thu hồi khỏi SSTable**.
3. Nêu được các điều kiện để compaction có thể loại bỏ tombstone mà không làm giá trị bị xóa xuất hiện trở lại.
4. Mô tả rủi ro **zombie data** khi replica bỏ lỡ thao tác xóa lâu hơn cửa sổ grace.
5. Thiết kế lab CQL với flush, compaction, repair và quan sát chỉ số mà không nhầm kết quả truy vấn với bằng chứng thu hồi vật lý.
6. Chọn `gc_grace_seconds` và lịch repair có căn cứ, hiểu ảnh hưởng của STCS/LCS/TWCS, TTL, partition key và workload Java.

## 2. Tombstone là gì và được tạo ở đâu?

### 2.1. Xóa logic trước, thu hồi vật lý sau

Cassandra lưu dữ liệu trong memtable và SSTable bất biến. Sau khi dữ liệu đã được ghi vào SSTable, thao tác cập nhật hoặc xóa **không sửa trực tiếp các byte của SSTable cũ**. Thay vào đó, mutation mới (bao gồm tombstone) được ghi vào đường ghi thông thường: commit log và memtable, rồi được flush thành SSTable mới.

Một tombstone chứa thông tin cần thiết để che các phiên bản dữ liệu cũ, như timestamp của thao tác xóa và thời điểm xóa cục bộ phục vụ tính thời gian grace. Khi đọc, Cassandra hợp nhất các phiên bản liên quan theo quy tắc timestamp và xóa; một giá trị cũ hơn tombstone không được phép hiện ra trong kết quả.

| Hành động | Dữ liệu logic | Hệ quả trên lưu trữ |
|---|---|---|
| `INSERT`/`UPDATE` giá trị mới | Có giá trị ở timestamp tương ứng | Mutation được lưu; SSTable cũ có thể vẫn giữ phiên bản trước |
| `DELETE` một cột | Cột đã xóa không còn hiển thị | Có tombstone cho cột/vùng phù hợp |
| `DELETE` một hàng | Hàng đã xóa không còn hiển thị | Có row tombstone hoặc dạng dấu xóa liên quan |
| `DELETE` cả partition | Các hàng thuộc partition bị che theo quy tắc timestamp | Có partition tombstone |
| Hết hạn `TTL` | Giá trị hết hạn không còn hiển thị | Dữ liệu hết hạn được xem là đã xóa và cần thu hồi theo quy tắc tombstone |

Tùy câu lệnh, Cassandra còn có **range tombstone** cho khoảng clustering keys. Kích thước và vị trí của các loại tombstone ảnh hưởng đường đọc và khả năng compaction; không phải mọi lệnh `DELETE` tạo một dòng vật lý giống nhau.

### 2.2. Ví dụ một giá trị cũ và thao tác xóa mới

Giả sử ở một node, cùng khóa `(device_id, day_bucket, event_id)` tồn tại hai SSTable:

~~~text
SSTable-A (đã có từ trước):
  key = K, payload = "ACTIVE", write timestamp = 100

SSTable-B (mới hơn):
  key = K, tombstone, delete timestamp = 200
~~~

Khi đọc, tombstone với timestamp 200 che giá trị timestamp 100, nên ứng dụng không thấy giá trị `ACTIVE`. Nhưng **SSTable-A vẫn chứa byte dữ liệu cũ** cho tới khi compaction đủ điều kiện xử lý nó.

Nếu compaction chỉ xem SSTable-B và xóa tombstone trong khi SSTable-A vẫn còn tồn tại, lần đọc sau có thể lại thấy `ACTIVE`. Vì thế quyết định thu hồi phải xem xét **dữ liệu khác mà tombstone đang che**, chứ không chỉ nhìn tuổi của bản thân tombstone.

### 2.3. Ba thời điểm không đồng nghĩa

~~~mermaid
flowchart LR
    A["T0: DELETE hoặc TTL hết hạn"] --> B["Đọc không còn thấy giá trị cũ"]
    B --> C["T1: tombstone vượt gc_grace_seconds"]
    C --> D["T2: compaction có thể loại bỏ an toàn"]
    D --> E["Đĩa thực tế được giải phóng dần"]
~~~

- **T0:** dấu xóa có hiệu lực logic theo timestamp và mức nhất quán của lần đọc.
- **T1:** tombstone đủ tuổi để được **xem xét** thu hồi. Không có bộ hẹn giờ tự động xóa đúng ở T1.
- **T2:** compaction xử lý các SSTable phù hợp và xác định điều kiện an toàn để loại bỏ tombstone cùng dữ liệu cũ bị che.
- **Sau T2:** SSTable thay thế được ghi, SSTable cũ không còn cần thiết và được xóa theo cơ chế quản lý file; con số dung lượng có thể cập nhật sau, không phải giảm tức thì ngay sau `DELETE`.

## 3. Ba lớp điều kiện để thu hồi tombstone

### 3.1. Lớp 1 — Đã qua cửa sổ `gc_grace_seconds`

`gc_grace_seconds` là tùy chọn **cấp bảng**, biểu thị khoảng thời gian Cassandra giữ tombstone sau thời điểm xóa cục bộ để các replica bỏ lỡ thao tác xóa còn cơ hội được đồng bộ. Mặc định thường là **864000 giây (10 ngày)** trong Apache Cassandra; phải kiểm tra schema của bảng và phiên bản thực tế.

~~~sql
CREATE TABLE lab_tombstone.events_by_device (
    device_id uuid,
    day_bucket date,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, day_bucket), event_id)
) WITH gc_grace_seconds = 864000;
~~~

Điều kiện khái quát để xem xét một tombstone là:

~~~text
thời điểm hiện tại > thời điểm xóa cục bộ + gc_grace_seconds
~~~

**Lưu ý:** đây là cách diễn đạt khái niệm. Trong triển khai, Cassandra dựa trên metadata của tombstone và logic compaction; `localDeletionTime` và timestamp của thao tác xóa **không phải cùng một đại lượng**. Timestamp dùng giải quyết xung đột phiên bản; thời điểm xóa cục bộ dùng đánh giá thời gian giữ tombstone. Đồng hồ node bị lệch có thể gây sai lệch vận hành, vì vậy cần đồng bộ thời gian.

Việc cấu hình `gc_grace_seconds = 0` khiến tombstone có thể đủ tuổi ngay; nó **không** cam kết xóa vật lý tức khắc và đặc biệt nguy hiểm khi một replica đang giữ dữ liệu cũ. Không chọn 0 chỉ để làm chỉ số tombstone thấp hơn.

### 3.2. Lớp 2 — Không để lộ phiên bản cũ trong các SSTable khác

Compaction phải đảm bảo khi bỏ một tombstone, nó **không làm lộ** dữ liệu cũ vẫn còn trong những SSTable có thể được đọc. Điều này thường đòi phân tích các SSTable **cùng tham gia compaction** và **các SSTable chồng lấn nhưng chưa được compact**, với phạm vi token, khoảng timestamp và dấu xóa phù hợp.

Xét ba tình huống:

| Tình huống | Kết quả hợp lý |
|---|---|
| SSTable-A chứa giá trị cũ; SSTable-B chứa tombstone; chỉ B được compact, A vẫn có thể được đọc | **Giữ** tombstone nếu bỏ nó có thể làm A lộ dữ liệu |
| A và B được compact cùng nhau, không còn nguồn dữ liệu cũ chồng lấn nào khác trên node, tombstone đủ tuổi và các ràng buộc khác thỏa | Có thể loại bỏ **cả** tombstone và giá trị cũ bị che |
| Tombstone đã đủ tuổi nhưng còn SSTable chồng lấn với dữ liệu có thể bị nó che mà compaction chưa xử lý | Có thể phải **giữ lại** tombstone cho tới lượt compaction an toàn hơn |

Vì vậy, **“hết grace rồi chạy compaction một SSTable” không bảo đảm tombstone biến mất**. Những cấu trúc như partition tombstone, row tombstone, range tombstone, TTL và cập nhật timestamp làm bài toán phức tạp hơn hình vẽ hai SSTable. Cassandra tự thực hiện kiểm tra đủ điều kiện trong storage engine; người vận hành không nên xóa thủ công file SSTable chỉ vì thấy tombstone cũ.

### 3.3. Lớp 3 — Đảm bảo replica khác không tái phát dữ liệu đã xóa

Hai điều kiện đầu là điều kiện mà compaction trên **một node** có thể xử lý. Trong cluster phân tán, còn một ràng buộc **vận hành**: các replica cần có cơ hội nhận dấu xóa trước khi nó bị thu hồi ở các replica đang có mặt.

- Tombstone được truyền như mutation đến các replica theo RF và CL. Một ghi `DELETE` thành công ở `QUORUM` **không đồng nghĩa mọi replica** đã nhận và lưu tombstone.
- Replica Down hoặc bị cô lập có thể còn giữ giá trị cũ. **Hinted handoff** có giới hạn thời gian và tình trạng vận hành, không thay thế repair.
- **Anti-entropy repair** giúp đồng bộ dữ liệu giữa các replica. Tần suất, thời gian hoàn tất và phạm vi repair phải được quản trị sao cho replica lỡ deletion không quay lại sau cửa sổ an toàn mà vẫn giữ dữ liệu cũ.
- Một số cấu hình/phiên bản có tùy chọn `only_purge_repaired_tombstones` để hạn chế thu hồi đối với dữ liệu chưa được đánh dấu repaired. Đây là **hàng rào bổ sung**, không phải thay thế repair đúng lịch, và cần kiểm tra hành vi phiên bản trước khi sử dụng.

**Ranh giới quan trọng:** Cassandra không mặc nhiên “kiểm tra đã repair trên tất cả replica” trước mọi lần compaction thu hồi tombstone. `gc_grace_seconds` là cửa sổ để công tác repair/đồng bộ hoàn thành, **không phải giấy chứng nhận rằng chúng đã hoàn thành**.

### 3.4. Bảng quyết định

| Đã qua grace? | Có dữ liệu cũ có thể bị lộ trên node? | Replica đã được vận hành/repair an toàn? | Kết luận |
|---|---|---|---|
| Không | Bất kỳ | Bất kỳ | Chưa đủ điều kiện thu hồi thông thường |
| Có | Có, chưa được compaction che/xóa an toàn | Có thể có | Chưa nên bỏ tombstone vì nguy cơ lộ dữ liệu cục bộ |
| Có | Không còn dữ liệu cục bộ bị che ngoài phạm vi xử lý | Không rõ | Có thể đủ điều kiện **kỹ thuật cục bộ** nhưng còn rủi ro zombie từ replica khác |
| Có | Có thể loại bỏ an toàn các phiên bản cũ | Có, theo runbook đã kiểm chứng | Có cơ sở để compaction thu hồi khi nó thực sự chạy |

Bảng này là mô hình tư duy. Việc Cassandra purge một tombstone cụ thể còn phụ thuộc thuật toán compaction, metadata SSTable, loại tombstone, phiên bản và cấu hình.

## 4. Vì sao zombie data xuất hiện khi replica lỗi lâu?

### 4.1. Dòng thời gian với RF = 3

Giả sử cluster có ba replica A, B, C, một partition chứa giá trị `status = 'ACTIVE'` timestamp 100 trên cả ba. Hệ thống ghi ở `QUORUM`.

| Thời điểm | Replica A | Replica B | Replica C | Sự kiện |
|---|---|---|---|---|
| Ngày 0 | ACTIVE | ACTIVE | ACTIVE | Dữ liệu đã được đồng bộ |
| Ngày 1 | Tombstone ts=200 | Tombstone ts=200 | **Down, còn ACTIVE** | Delete đạt `QUORUM` nhờ A và B |
| Ngày 1–11 | Dấu xóa được duy trì | Dấu xóa được duy trì | Down | Không repair được C; hints có thể hết hạn |
| Sau grace | Tombstone có thể được purge nếu compaction an toàn cục bộ | Tương tự A | Vẫn còn ACTIVE | Dấu xóa có thể đã mất trên A/B |
| C quay lại | Không còn dấu xóa | Không còn dấu xóa | ACTIVE ts=100 | Repair/read reconciliation có thể phát tán giá trị cũ |

Giá trị đã xóa nhưng xuất hiện lại gọi là **zombie data**. Sự phục hồi có xảy ra hay không còn phụ thuộc lịch sử mutation, timestamp, SSTable thực tế, repair và compaction; bảng mô tả một **kịch bản rủi ro**, không khẳng định mọi node Down quá 10 ngày đều làm dữ liệu sống lại.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant A as Replica A
    participant B as Replica B
    participant C as Replica C
    Note over C: Offline, còn giá trị V cũ
    App->>A: DELETE K (ts=200)
    A->>A: Ghi tombstone
    A->>B: Chuyển mutation xóa
    B->>B: Ghi tombstone
    A-->>App: Đủ QUORUM, trả success
    Note over A,B: Qua grace + compaction an toàn cục bộ
    Note over A,B: Có thể đã thu hồi tombstone
    Note over C: C trở lại cùng V cũ
    C-->>A: Repair/đồng bộ giá trị V
    Note over A,C: Không còn dấu xóa để che V
~~~

Điều nguy hiểm nằm ở chỗ **mỗi node chỉ nhìn thấy SSTable của chính mình khi compaction**. Đảm bảo không lộ giá trị cũ tại A không chứng minh C đã biết thao tác xóa.

### 4.2. Vì sao không giảm grace tùy tiện?

Thời gian grace phải phản ánh **cửa sổ có thể mất liên lạc dài nhất** của replica cộng với khả năng thực hiện repair, trễ vận hành, sự cố kế tiếp và sai số thời gian; không chỉ là thời gian hints còn được lưu.

Ví dụ: nếu tổ chức có thể để node offline 48 giờ nhưng repair dữ liệu lớn mất thêm nhiều ngày, cấu hình grace 24 giờ để “dọn tombstone nhanh” tạo rủi ro rõ ràng. Ngay cả hệ thống theo lịch repair thường xuyên cũng phải kiểm tra **repair hoàn tất**, không chỉ job đã được lên lịch hoặc chạy.

Với sự cố kéo dài vượt `gc_grace_seconds`, cần theo **runbook khôi phục/rebuild/replace** phù hợp phiên bản và topology, có thể phải làm lại dữ liệu replica từ nguồn đúng; đừng chỉ bật node cũ lên và tin rằng repair sẽ xử lý mọi tình huống.

## 5. Vì sao đã đủ điều kiện mà tombstone vẫn còn?

Hết grace chỉ làm tombstone **có thể loại bỏ**; nó chưa nhất thiết được chọn trong một compaction. Có nhiều nguyên nhân:

1. **Chưa có compaction phù hợp:** không có compaction nào chạy trên SSTable chứa tombstone hoặc scheduler không chọn các file cần thiết.
2. **SSTable chồng lấn:** compaction đang chạy trên một nhóm file nhưng còn dữ liệu cũ có thể bị lộ ở các SSTable khác.
3. **Tombstone chưa đủ tuổi:** mốc local deletion time/TTL hoặc đồng hồ khiến tính toán thực tế khác dự đoán.
4. **Compaction bị nghẽn:** backlog, tốc độ disk, CPU hoặc giới hạn compaction throughput khiến file không được xử lý sớm.
5. **Chính sách repaired data:** tùy chọn bảo vệ theo tình trạng repaired/unrepaired có thể giữ tombstone lâu hơn trong cấu hình liên quan.
6. **TTL lệch nhau hoặc dữ liệu đến muộn:** SSTable vẫn chứa các phiên bản/tombstone cần che dữ liệu trước đó; việc ghi TTL ngắn không làm toàn bộ partition có thể xóa cùng lúc.
7. **Ảnh hưởng của compaction strategy:** cách chọn SSTable rất khác giữa STCS, LCS và TWCS, dẫn đến cơ hội xóa tombstone khác nhau.

Không nên suy luận “tombstone vẫn còn sau 10 ngày tức Cassandra bị lỗi”. Hãy kiểm tra compaction có chạy không, SSTable nào còn chồng lấn, vị trí tombstone và điều kiện an toàn.

### 5.1. Size-Tiered Compaction Strategy (STCS)

STCS thường chọn các SSTable có kích thước tương tự để compact. Một tombstone ở SSTable nhỏ có thể nằm chờ vì chưa đủ điều kiện tạo nhóm compaction phù hợp hoặc dữ liệu cũ còn trong một SSTable kích thước rất khác. STCS có các lựa chọn liên quan tombstone compaction nhưng nên dùng sau khi hiểu tác động I/O và vùng dữ liệu chồng lấn.

### 5.2. Leveled Compaction Strategy (LCS)

LCS tổ chức SSTable theo level và cố hạn chế overlap trong các level nhất định. Khi compact, phạm vi SSTable phải bảo toàn tính đúng đắn giữa các level. LCS thường cải thiện tính dự báo của đường đọc trong workload thích hợp, nhưng **không** bảo đảm mọi tombstone hết grace sẽ bị xóa ngay; vẫn có tình huống overlap và chi phí compaction lớn.

### 5.3. Time-Window Compaction Strategy (TWCS)

TWCS nhóm SSTable vào các cửa sổ thời gian. Với dữ liệu time-series **chủ yếu được ghi theo thứ tự thời gian, TTL tương đối đồng nhất**, các SSTable của cửa sổ cũ có thể trở nên hoàn toàn hết hạn và được loại bỏ hiệu quả.

Tuy nhiên, dữ liệu đến trễ, cập nhật/xóa vào partition cũ hoặc TTL pha trộn có thể làm các cửa sổ chồng lấn logic. Vì vậy không thể tuyên bố “TWCS + TTL sẽ không có tombstone” hoặc “mỗi cửa sổ hết hạn sẽ được xóa ngay”. Đặc biệt thận trọng với cấu hình cho phép xóa SSTable hết hạn một cách quá chủ động, vì có thể tăng rủi ro lộ dữ liệu trong file chồng lấn.

| Strategy | Cách chọn SSTable khái quát | Hệ quả cho tombstone |
|---|---|---|
| STCS | Nhóm SSTable theo kích thước | Tombstone có thể chờ file phù hợp; tồn tại overlap |
| LCS | Chia SSTable thành level, quản lý phạm vi trùng lấn | Cơ hội xử lý được tổ chức hơn nhưng vẫn phải giữ an toàn |
| TWCS | Nhóm SSTable theo thời gian | Có lợi cho dữ liệu TTL đồng nhất, tuần tự; nhạy với late writes |

**Compaction strategy là lựa chọn theo workload**, không phải một công tắc để tăng tốc thu hồi tombstone bằng mọi giá.

## 6. Lab CQL: quan sát tombstone, grace và compaction

### 6.1. Điều kiện và ranh giới thí nghiệm

Sử dụng **cluster Cassandra thử nghiệm cô lập** với `cqlsh` và `nodetool`; ghi rõ phiên bản, RF, CL, compaction strategy và topology. Các ví dụ dưới đây dựa trên CQL thông dụng của Cassandra 4.x–5.x. Nếu môi trường chỉ có một node, phải chỉnh replication/CL cho đúng; **không dùng keyspace lab có RF=3 trên một node** rồi suy luận kết quả về replica.

Trong lab có ít nhất ba node thuộc DC có tên chính xác `dc1`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_tombstone
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

USE lab_tombstone;

CREATE TABLE IF NOT EXISTS events_by_device (
    device_id uuid,
    day_bucket date,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, day_bucket), event_id)
) WITH gc_grace_seconds = 120
  AND compaction = {'class': 'SizeTieredCompactionStrategy'};
~~~

**Cảnh báo phạm vi:** `gc_grace_seconds = 120` (hai phút) **chỉ phục vụ lab có thể xóa bỏ**, để đợi/quan sát được trong một buổi học. Mức này rất thấp đối với replica có thể Down hoặc repair không hoàn tất trong hai phút. **Không áp dụng vào production**. Với bảng đã tồn tại, `IF NOT EXISTS` không sửa lại cấu hình: phải kiểm tra schema thật.

Khóa phân vùng là `(device_id, day_bucket)`, khóa clustering là `event_id`. Vì cùng một partition chứa các event của thiết bị trong một ngày, truy vấn theo partition key có thể được định tuyến hiệu quả; ở thiết bị quá nóng, bucket theo ngày có thể vẫn quá lớn và phải thiết kế lại.

### 6.2. Tạo giá trị rồi xóa logic

Trong `cqlsh`:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

Chạy CQL:

~~~sql
INSERT INTO lab_tombstone.events_by_device
    (device_id, day_bucket, event_id, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    df4d2f1a-c74e-48dc-b889-4e18de3cd51b,
    'VISIBLE_BEFORE_DELETE'
);

SELECT event_id, payload
FROM lab_tombstone.events_by_device
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND day_bucket = '2026-11-21';
~~~

Trước khi xóa, chạy flush trên **các node chứa replica** để tạo SSTable lưu giá trị cũ:

~~~bash
nodetool flush lab_tombstone events_by_device
~~~

Lệnh `nodetool` chạy tại node hiện tại; cần biết endpoint theo partition và lặp trên các node liên quan khi muốn quan sát vật lý ở cả RF=3. Trên mỗi node, flush chỉ chuyển memtable hiện tại của node đó sang SSTable.

Tiếp theo:

~~~sql
DELETE FROM lab_tombstone.events_by_device
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND day_bucket = '2026-11-21'
  AND event_id = df4d2f1a-c74e-48dc-b889-4e18de3cd51b;

SELECT event_id, payload
FROM lab_tombstone.events_by_device
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND day_bucket = '2026-11-21';
~~~

Kết quả `SELECT` sau xóa không còn hàng phù hợp, **nhưng không chứng minh đã xóa byte khỏi disk**. Tombstone có thể còn trong memtable. Chạy flush một lần nữa tại các replica liên quan để có SSTable mới chứa dấu xóa, rồi quan sát chỉ số storage.

### 6.3. Quan sát và so sánh trước/sau compaction

Trên từng replica:

~~~bash
nodetool tablestats lab_tombstone.events_by_device
nodetool compactionstats
nodetool tpstats
~~~

Khi có quyền truy cập trực tiếp thư mục SSTable trên host/container lab, công cụ **`sstablemetadata`** của đúng phiên bản có thể hỗ trợ xem metadata liên quan SSTable/tombstone và tỷ lệ tombstone có khả năng thu hồi (*estimated droppable tombstone ratio*). Cách gọi, đường dẫn và các trường xuất ra phải kiểm tra bằng `sstablemetadata --help` trên môi trường tương ứng. Không sửa trực tiếp các SSTable đang được Cassandra quản lý.

Đối chiếu:

| Thời điểm | Quan sát logic | Quan sát vật lý hợp lý |
|---|---|---|
| Trước DELETE | Có hàng `VISIBLE_BEFORE_DELETE` | SSTable chứa giá trị cũ |
| Ngay sau DELETE | Không thấy hàng ở CL kiểm tra | Giá trị cũ có thể còn; tombstone có thể ở memtable |
| Sau flush, **chưa hết 120 giây** | Không thấy hàng | Có SSTable giá trị cũ và SSTable tombstone; chưa đủ tuổi purge |
| Sau 120 giây, **chưa có compaction thích hợp** | Không thấy hàng | Tombstone có thể vẫn còn dù đã đủ tuổi |
| Sau compaction phù hợp | Không thấy hàng | Có thể thu hồi tombstone và dữ liệu cũ, tùy overlap và điều kiện bảo vệ |

Để học cơ chế, sau khi vượt grace và đã bảo đảm các replica đều nhận thao tác xóa, có thể **trong lab** yêu cầu compaction thủ công trên từng node có liên quan:

~~~bash
nodetool compact lab_tombstone events_by_device
~~~

Đây là lệnh tốn I/O, không phải bước bắt buộc của mỗi xóa trong production. Ngay cả sau khi lệnh hoàn tất, việc dữ liệu có còn trong SSTable nào hay không phải xác minh bằng metadata/storage tools thích hợp; `SELECT` tiếp tục trả rỗng **không thể chứng minh purge**.

**Điều kiện so sánh:** trong một lab rất nhỏ, nội dung không nhiều, metadata có thể thay đổi quá nhanh hoặc compaction nền đã chạy sớm. Muốn đánh giá định lượng, tạo đủ partition, ghi giá trị và tombstone theo nhiều SSTable trước khi đo, đồng thời ghi lại trạng thái compaction.

### 6.4. TTL: thời điểm hết hạn và thời điểm thu hồi

Trong cùng bảng, thêm một event có TTL:

~~~sql
INSERT INTO lab_tombstone.events_by_device
    (device_id, day_bucket, event_id, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    3400f4b1-136a-4130-86a0-8dfc63269fb0,
    'EXPIRES_AFTER_60S'
) USING TTL 60;
~~~

Ở khoảng phút đầu, bản ghi còn hiển thị. Sau TTL, giá trị hết hạn bị coi là đã xóa khi đọc; nó có thể còn ở SSTable và chịu các quy tắc thu hồi như tombstone. **TTL = 60 không có nghĩa dung lượng disk được giải phóng sau đúng 60 giây**. Còn `gc_grace_seconds = 120` trong lab là cửa sổ cần tính thêm từ mốc xóa/hết hạn tương ứng, cùng các điều kiện compaction.

### 6.5. Dữ liệu cần ghi vào báo cáo lab

| Bằng chứng | Nội dung phải ghi | Kết luận hợp lệ |
|---|---|---|
| Schema | RF, CL, `gc_grace_seconds`, compaction | Biết chính xác điều kiện cấu hình |
| CQL trước/sau `DELETE` | Hàng hiển thị trước, ẩn sau | Xóa logic hoạt động |
| Thời điểm flush | SSTable nào hình thành từ giá trị và dấu xóa | Có cơ sở phân tích overlap |
| `tablestats`, `compactionstats` | SSTable count, tombstone per slice nếu có, pending compaction | Có dữ kiện về storage/đường đọc |
| `sstablemetadata` hoặc công cụ SSTable tương ứng | Metadata trước/sau, số liệu tombstone có khả năng purge | Quan sát vật lý có giới hạn theo công cụ |
| Tình trạng replica/repair | Node đủ RF, up/down, đồng bộ dấu xóa | Đánh giá nguy cơ zombie |

**Không dùng chỉ một con số** “SSTable count giảm” để kết luận tombstone cụ thể đã bị xóa: compaction có thể hợp nhất nhiều file mà vẫn giữ dấu xóa. Cũng không lấy “câu lệnh DELETE đã thành công” để kết luận tất cả replica đã đồng bộ ở mọi mức CL.

## 7. Tác động của tombstone lên đường đọc và lưu trữ

### 7.1. Tombstone vẫn có chi phí khi đọc

Khi truy vấn một partition/range, Cassandra có thể phải đọc và hợp nhất nhiều cell, range marker và tombstone qua nhiều SSTable để xác định hàng nào còn sống. Nếu một partition có rất nhiều tombstone, một câu `SELECT ... LIMIT 10` đôi khi vẫn phải bỏ qua lượng lớn dữ liệu đã xóa trước khi tìm đủ mười hàng sống.

Vì vậy, thao tác xóa logic **không ngay lập tức làm truy vấn nhanh hơn**. Nếu dữ liệu thường xuyên bị xóa hàng loạt, workload có thể chịu:

- Tăng số tombstone được quét mỗi truy vấn, kéo theo CPU/IO và p95/p99.
- Cảnh báo hoặc lỗi liên quan ngưỡng tombstone khi quét, tùy phiên bản/cấu hình.
- Dung lượng SSTable cao hơn kích thước dữ liệu sống, tăng write amplification của compaction.
- Nhu cầu kiểm soát TTL, kích thước partition, clustering range và chiến lược xóa phù hợp.

### 7.2. Theo dõi bằng metric đúng ý nghĩa

Các tín hiệu thường hữu ích:

| Công cụ/metric | Trả lời câu hỏi | Không chứng minh |
|---|---|---|
| `nodetool tablestats` | Bảng có nhiều SSTable/chi phí đọc/tombstone per slice đáng chú ý không? | Số tombstone chính xác đã được purge |
| `nodetool tablehistograms` | Kích thước partition, độ trễ và SSTables per read có phân bố bất thường không? | Mọi partition đều giống percentile |
| `nodetool compactionstats` | Compaction đang chạy, pending tasks thế nào? | Chạy compaction sẽ chắc chắn loại mọi tombstone |
| JMX/Table `TombstoneScannedHistogram` và read latency | Truy vấn có quét nhiều tombstone và p99 tăng không? | Tombstone chính là nguyên nhân duy nhất |
| `sstablemetadata`, kiểm tra file phù hợp | Tombstone/drop eligibility ở phạm vi SSTable | Replica khác đã nhận thao tác xóa |
| `nodetool status`, repair history | Topology và tình trạng đồng bộ được quản lý ra sao? | Chỉ riêng status Up là đủ để đảm bảo dữ liệu nhất quán |

Chọn cửa sổ đo trước/sau cùng một workload. Nhiều metric là bộ đếm tích lũy, cần tính delta/rate; các histogram theo bảng hoặc theo node không thay thế latency đầu-cuối của ứng dụng. Không chạy phân tích SSTable nặng hoặc compaction thủ công trên cluster production giờ cao điểm.

## 8. Thiết kế và vận hành để tombstone không thành gánh nặng

### 8.1. Chọn `gc_grace_seconds` theo rủi ro replica và repair

Không có một giá trị grace tối ưu cho mọi bảng. Quyết định cần trả lời:

1. Replica có thể bị cô lập tối đa bao lâu trước khi được khôi phục/rebuild?
2. Repair chạy theo lịch nào, thực tế hoàn thành trong bao lâu trên toàn vùng dữ liệu?
3. Có cửa sổ bảo trì, vùng mạng bất ổn, node thường xuyên Down hay xử lý snapshot/restore không?
4. Dữ liệu đang dùng TTL, xóa cột/hàng/partition, cập nhật phiên bản hay đồng bộ giữa nhiều DC?
5. Có cơ chế theo dõi repair thành công và cảnh báo khi bỏ lỡ lịch không?

Nếu repair thường xuyên thất bại, **đừng chỉ giảm grace để thu hồi nhanh hơn**. Trước hết phải cải thiện repair, availability và quy trình xử lý replica mất liên lạc. Ngược lại, grace rất dài cũng không giải quyết chuyện không repair, đồng thời kéo dài thời gian tombstone có thể tồn tại.

### 8.2. Không lạm dụng `DELETE` theo từng hàng khi cần loại bỏ dữ liệu khối lượng lớn

Một workload tạo hàng triệu event/ngày rồi xóa từng hàng sau một thời hạn có thể tạo lượng lớn tombstone và write amplification. Nếu chính sách nghiệp vụ cho phép:

- Sử dụng **TTL hợp lý** khi tạo event thay vì chạy job quét/xóa từng hàng; dù TTL cũng tạo tombstone, việc chọn TTL đồng nhất hỗ trợ thiết kế dữ liệu time-series.
- Chọn **partition key và time bucket** theo truy vấn, kích thước dữ liệu và vòng đời; tránh một partition chứa hàng triệu hàng cần quét qua tombstone.
- Cân nhắc **TWCS** cho workload time-series phù hợp với ghi theo thời gian và vòng đời dữ liệu nhất quán, đồng thời kiểm chứng late data.
- Đối với tập dữ liệu có thể loại bỏ nguyên bảng/keyspace, thao tác ở cấp schema có quy trình khác với xóa từng hàng; chỉ dùng khi xác định rõ phạm vi và tác động nghiệp vụ.
- Nếu một bảng thường xuyên cập nhật cùng cell hoặc dùng collection lớn, theo dõi tombstone từ cập nhật/xóa phần tử thay vì chỉ thống kê câu lệnh `DELETE`.

**Lưu ý:** không phải cứ có TTL là cần TWCS. Một bảng chứa dữ liệu có thể cập nhật ở nhiều thời điểm và truy vấn không theo cửa sổ thời gian có thể cần chiến lược khác.

### 8.3. Repair, hints và compaction có nhiệm vụ riêng

| Cơ chế | Mục đích chính | Vai trò đối với tombstone |
|---|---|---|
| **Hinted handoff** | Chuyển tiếp một số mutation bị lỡ khi replica tạm Down | Hỗ trợ phát tán tombstone trong cửa sổ hạn chế; không bảo đảm đồng bộ dài hạn |
| **Repair** | So sánh và đồng bộ dữ liệu giữa replica | Giảm nguy cơ replica giữ dữ liệu cũ trong khi tombstone hết grace |
| **Compaction** | Hợp nhất SSTable và xử lý phiên bản trên mỗi node | Có thể loại bỏ tombstone cùng dữ liệu bị che nếu đủ điều kiện |
| **Snapshot/backup** | Cung cấp khả năng khôi phục dữ liệu theo quy trình | Không thay repair; restore snapshot cũ phải xét rủi ro tái nhập dữ liệu đã xóa |

Một số runbook yêu cầu **full repair** sau đổi RF/topology; với bài toán bảo vệ tombstone cần lịch repair phù hợp cụm và phiên bản, không nên đồng nhất “có chạy repair” với “không thể có zombie”. Việc dùng incremental/full repair phải theo phiên bản, phạm vi token và công cụ hiện hành.

## 9. Liên hệ với Java client và consistency level

Trong Java Driver, thao tác xóa là một mutation bình thường và có CL như các write khác. Ví dụ với Java Driver 4.x, trên `CqlSession session` đã được cấu hình local datacenter:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement deleteByKey = session.prepare(
    "DELETE FROM lab_tombstone.events_by_device " +
    "WHERE device_id = ? AND day_bucket = ? AND event_id = ?");

BoundStatement statement = deleteByKey.bind(
        UUID.fromString("0f94e3b9-0b36-4930-91f2-606b44b5231b"),
        LocalDate.of(2026, 11, 21),
        UUID.fromString("df4d2f1a-c74e-48dc-b889-4e18de3cd51b"))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(statement);
~~~

Ở RF=3 trong một DC, `LOCAL_QUORUM` thường chờ hai replica xác nhận. Nó không đảm bảo replica thứ ba đã ghi tombstone; do đó thao tác Java thành công không thay thế nhiệm vụ repair. Một timeout cũng không chứng minh delete thất bại: có thể một số replica đã ghi dấu xóa và client không nhận đủ ACK trước deadline.

**Lưu ý retry:** khi ghi/xóa lại cùng khóa, nếu ứng dụng sử dụng client timestamp, TTL hoặc logic xung đột, cần kiểm soát thứ tự mutation và idempotency. Đặc biệt không tạo một delete timestamp cũ hơn một cập nhật mới rồi kết luận xóa sẽ thắng; Cassandra dùng timestamp để giải quyết phiên bản.

## 10. Những ngộ nhận cần loại bỏ

| Nhận định | Đánh giá | Diễn giải đúng |
|---|---|---|
| “Xóa xong là giải phóng disk” | Sai | Delete thường chỉ tạo dấu xóa; disk được thu hồi qua compaction thích hợp |
| “Qua 10 ngày tombstone tự biến mất” | Sai | Grace là điều kiện tuổi; còn compaction, overlap và yêu cầu an toàn |
| “Chạy `nodetool compact` là xóa hết tombstone” | Sai | Compaction vẫn phải giữ tombstone chưa đủ điều kiện hoặc còn che dữ liệu |
| “`gc_grace_seconds=0` luôn tăng hiệu năng” | Sai/nguy hiểm | Tăng rủi ro dữ liệu cũ tái xuất hiện, không bảo đảm purge ngay |
| “Repair không liên quan đến xóa” | Sai | Repair giúp replica bỏ lỡ mutation nhận được thông tin xóa |
| “Hints thay thế được repair” | Sai | Hints có cửa sổ/giới hạn và không đảm bảo phục hồi mọi bỏ sót |
| “TTL tránh hoàn toàn tombstone” | Sai | Hết TTL tạo trạng thái xóa cần được dọn an toàn |
| “Nhiều tombstone luôn khiến `SELECT` lỗi” | Quá mức | Ảnh hưởng tùy số tombstone phải quét, partition, read path và ngưỡng phiên bản |
| “Chỉ cần đọc rỗng là biết vật lý đã dọn” | Sai | Giá trị cũ có thể vẫn nằm trong SSTable nhưng bị tombstone che |
| “Một replica Up chứng minh mọi xóa đều được nhận” | Sai | Up không nói được lịch sử đồng bộ của từng partition |

## 11. Tình huống vận dụng

### Tình huống A — Đã qua grace nhưng SSTable vẫn giữ tombstone

SSTable A chứa `V(ts=100)`. SSTable B chứa `DELETE(ts=200)` đã qua grace; scheduler chỉ định compact B mà không có A. Có nên xóa tombstone khỏi B?

**Trả lời:** không nên nếu A vẫn có thể được đọc và giá trị cũ của A sẽ lộ ra. Tombstone cần được giữ, hoặc compaction phải xử lý/kiểm tra an toàn đối với dữ liệu chồng lấn. Đủ tuổi **không** đồng nghĩa an toàn cục bộ.

### Tình huống B — Node quay lại sau 15 ngày

RF=3, một node bỏ lỡ `DELETE`, không có repair hiệu quả, cấu hình grace 10 ngày. Hai replica kia đã compact và thu hồi tombstone. Node cũ quay lại. Điều gì có thể xảy ra?

**Trả lời:** nếu node cũ còn giá trị với timestamp trước DELETE nhưng dấu xóa đã mất trên các replica còn lại, dữ liệu cũ có thể được truyền lại và xuất hiện như zombie. Cần runbook khôi phục node đúng đắn, lịch repair và giám sát cửa sổ offline, không chỉ tăng CL của lần đọc.

### Tình huống C — TTL một giờ, tại sao dung lượng vẫn tăng?

Ứng dụng ghi hàng triệu event mỗi giờ với TTL=3600 giây. Sau hai giờ, phần lớn event đã không còn hiển thị nhưng SSTable lớn hơn dự kiến.

**Trả lời:** dữ liệu hết TTL không có nghĩa file đã được xóa. Grace, compaction, overlap, phân phối TTL và điều kiện chọn SSTable đều tác động. Cần kiểm tra strategy, tombstone metrics, thời gian flush/compaction, kích thước partition và dữ liệu đến muộn.

### Tình huống D — Có nên đổi grace từ 10 ngày xuống 1 giờ?

Đội vận hành đang chạy repair **mỗi tuần một lần** nhưng muốn giảm ổ đĩa bằng cách đặt `gc_grace_seconds = 3600`.

**Trả lời:** không đủ an toàn. Cửa sổ một giờ ngắn hơn nhiều so với lịch repair một tuần; một replica bỏ lỡ xóa có thể trở lại với dữ liệu cũ. Cần đánh giá lại repair, topology, SLA sự cố, retention, workload, compaction và rủi ro zombie trước mọi thay đổi.

## 12. Checklist kết thúc bài

- [ ] Phân biệt `DELETE`/TTL hết hạn với thu hồi byte trong SSTable.
- [ ] Nêu được `gc_grace_seconds` là điều kiện thời gian cần thiết nhưng không đủ.
- [ ] Giải thích được tình huống tombstone ở SSTable B che giá trị cũ ở SSTable A.
- [ ] Giải thích nguy cơ zombie khi một replica bỏ lỡ DELETE và mất cửa sổ repair.
- [ ] Dùng `cqlsh`, `nodetool flush`, `tablestats`, `compactionstats` để quan sát quá trình.
- [ ] Không coi `SELECT` trả rỗng hoặc `nodetool compact` thành công là chứng minh purge.
- [ ] Hiểu tác động của STCS, LCS, TWCS và dữ liệu TTL/late-arriving.
- [ ] Đưa ra lựa chọn grace dựa trên repair hoàn tất, thời gian replica offline và topology.
- [ ] Liên hệ được CL và tính mơ hồ của timeout khi Java gửi thao tác xóa.

## 13. Tài liệu tham khảo

1. Apache Cassandra Documentation — [Storage engine: SSTables, compaction, commit log](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html).
2. Apache Cassandra Documentation — [Anti-entropy repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html).
3. Apache Cassandra Documentation — [CQL data definition và table properties](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html).
4. Apache Cassandra Documentation — [Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html).
5. Apache Cassandra Documentation — [Compaction](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html).
