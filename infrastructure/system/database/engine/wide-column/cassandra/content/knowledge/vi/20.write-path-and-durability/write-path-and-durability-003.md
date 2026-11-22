# Các chế độ commitlog_sync và phạm vi dữ liệu có thể mất

Giả sử ứng dụng Java gửi `INSERT` đến Apache Cassandra ở mức nhất quán `QUORUM` và nhận **thành công**. Nếu ngay sau đó máy chủ mất điện, bản ghi có còn không? Nếu một node mất điện thì sao, và nếu cả ba replica cùng mất điện thì sao? Câu trả lời phụ thuộc **chế độ đồng bộ commit log tại từng replica**, những replica đã nhận mutation, các nguồn dữ liệu đã được flush, đặc tính của thiết bị lưu trữ và **phạm vi sự cố**.

Trọng tâm của bài là tham số **`commitlog_sync`**: nó điều khiển cách và thời điểm Cassandra đồng bộ commit log xuống thiết bị lưu trữ, từ đó ảnh hưởng tới **mốc ACK cục bộ**, độ trễ ghi và phần dữ liệu **có nguy cơ không thể replay sau sự cố**. Đây là chủ đề của chương **Đường ghi và độ bền** trong mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, liên hệ trực tiếp với kiến trúc phân tán, partition key, replication, consistency level, CQL, compaction, repair, xử lý lỗi và tích hợp Java.

> **Nguyên tắc cần nhớ:** **ACK theo consistency level không đồng nghĩa mọi mutation đã được `fsync` xuống đĩa trên mọi replica.** Ở `commitlog_sync: periodic`, replica có thể ACK trước lần đồng bộ log tiếp theo. Ở chế độ chờ sync trước ACK như `batch`, ranh giới độ bền cục bộ khác đi. Nhưng ngay cả `fsync` thành công cũng không thay thế replication, backup hoặc kế hoạch xử lý lỗi vật lý.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **append commit log**, **`fsync`**, **apply memtable**, **replica ACK**, **coordinator đạt CL**, **client nhận response** và **flush SSTable**.
2. Giải thích hai chế độ chính **`periodic` và `batch`**, nhận diện những biến thể **`group` khi phiên bản hỗ trợ**, và không áp dụng cấu hình của bản khác một cách máy móc.
3. Xác định những loại sự cố nào có thể khiến một **mutation đã được ACK nhưng chưa sync** không thể replay.
4. So sánh mất dữ liệu **trên một replica**, mất **mọi bản sao của partition** và mất khả năng **quan sát/đọc tạm thời**; không đánh đồng các khái niệm.
5. Liên hệ `commitlog_sync` với `durable_writes`, RF, CL, `LOCAL_QUORUM`, `EACH_QUORUM` và datacenter.
6. Biết vì sao `commitlog_sync_period_in_ms` không phải một “RPO tuyệt đối” và vì sao `fsync` không bảo đảm an toàn trước mọi lỗi storage.
7. Thực hành CQL và Java Driver 4.x với thao tác ghi/đọc, tracing, timestamp ổn định và trạng thái kết quả chưa biết khi timeout.
8. Phân tích benchmark độ trễ và lập checklist thay đổi cấu hình an toàn.

## 2. Nhắc lại write path: dữ liệu đi qua các mốc nào?

Với ghi thông thường, **coordinator** nhận request, xác định replica của partition theo partition key/token/replication strategy, gửi mutation đến chúng và chờ đủ ACK theo consistency level (CL).

Trên mỗi replica, đường ghi khái niệm là:

```text
                  CQL INSERT / UPDATE
                          |
                          v
                   Coordinator
                  /     |      \
                 v      v       v
                R1      R2      R3   (ví dụ RF=3)
                 |       |       |
               Mutation đến mỗi replica
                 |
                 +----> Commit log append
                 |
                 +----> Memtable apply
                 |
                 +----> Replica ACK
                           |
             Coordinator thu đủ ACK theo CL
                           |
                           v
                    Response cho client

  Sau đó: memtable --flush--> SSTable --compaction--> SSTable mới
```

**Sơ đồ là luồng trách nhiệm, không phải lịch thực thi bắt buộc cho mọi thread hoặc mọi phiên bản Cassandra.** Điểm cốt lõi là đường ghi cục bộ dùng commit log và memtable khi `durable_writes` bật; **flush SSTable không phải điều kiện mặc định để ACK mỗi mutation**.

### 2.1. Bảy sự kiện khác nhau

| Sự kiện | Điều gì đã xảy ra? | Có đồng nghĩa mutation an toàn trong mọi kiểu sự cố? |
| --- | --- | --- |
| `A: append` | Mutation được đưa vào đường ghi commit log. | **Không**; append có thể mới nằm trong bộ đệm/OS page cache. |
| `B: apply memtable` | Dữ liệu có mặt trong cấu trúc memory của replica. | **Không**; RAM có thể mất sau restart/mất điện. |
| `C: fsync` | Phần commit log liên quan được yêu cầu đồng bộ theo ngữ nghĩa filesystem/storage. | Bảo vệ tốt hơn trước lỗi mất cache, **không chống mọi lỗi thiết bị**. |
| `D: replica ACK` | Replica hoàn tất phần việc cần thiết theo chế độ sync và phản hồi. | Không chứng minh tất cả replica khác đã làm xong. |
| `E: coordinator đủ CL` | Nhận số ACK/phạm vi replica yêu cầu. | Không chứng minh tất cả replica đã ACK hoặc tất cả đã `fsync`. |
| `F: client nhận success` | Ứng dụng được xác nhận theo CL của request. | Không phải giao dịch ACID đa partition; không loại trừ mọi sự cố mất dữ liệu. |
| `G: flush SSTable` | Memtable được ghi thành SSTable bất biến. | Không có nghĩa đã repair hoặc đồng nhất với replica khác. |

**Chế độ `commitlog_sync` chủ yếu tác động quan hệ giữa `C` và `D`.** CL tác động quan hệ giữa `D` và `E`. Mạng/coordinator tác động việc `F` đến được client hay không. Flush/compaction là vòng đời lưu trữ khác.

### 2.2. Vì sao cần commit log nếu có memtable?

Memtable giúp Cassandra xử lý nhiều mutation nhanh trong RAM. Nếu node crash trước khi memtable được flush, commit log còn khả dụng có thể được **replay** để phục hồi dữ liệu. Nếu mất cả memtable và phần commit log chưa được đồng bộ mà không có SSTable tương ứng, **replica đó** có nguy cơ không phục hồi được mutation.

Đây là nền tảng để hiểu periodic khác batch: hai chế độ **không bỏ memtable**, mà điều chỉnh thời điểm Cassandra yêu cầu storage đồng bộ commit log so với ACK.

## 3. Các kiểu commitlog_sync: periodic, batch và biến thể theo phiên bản

### 3.1. `periodic` — đồng bộ theo chu kỳ

Ở chế độ **`commitlog_sync: periodic`**, Cassandra append mutation vào commit log và đồng bộ log theo **chu kỳ định cấu hình**, thay vì bắt mỗi ghi phải đợi một lần `fsync` riêng trước ACK.

```text
Thời gian ----------------------------------------------->

    append M1  apply memtable  ACK M1
       |             |          |
       v             v          v
       +-------------+----------+--------+
                                         |
                                         v
                                   fsync định kỳ

           [M1 có thể đã ACK trước fsync của nó]
```

**Hệ quả:** Nếu node chịu **mất điện/OS crash** làm mất những bytes mới chỉ tồn tại trong cache chưa được đồng bộ, phần mutation trong đoạn chưa `fsync` có thể **không replay được trên node đó**. Mutation đã flush thành SSTable hoặc đã được sync trước đó không thuộc cùng nhóm rủi ro này.

Periodic thường giảm chi phí phải chờ sync trên từng request và hỗ trợ throughput tốt. Tuy nhiên, “ACK nhanh” là **đánh đổi có chủ đích**: phản hồi replica không xác nhận sync disk cho mutation mới trong mọi thời điểm.

### 3.2. `batch` — ACK sau khi đồng bộ theo nhóm/batch

Với **`commitlog_sync: batch`**, Cassandra xử lý các mutation theo cơ chế đồng bộ commit log mà **ACK của replica phải chờ sync tương ứng**; các write có thể được gom để tận dụng một lần đồng bộ.

```text
Thời gian ------------------------------------------------>

 append M1 ----+
 append M2 ----+---- sync commit log ----> ACK M1, ACK M2
 append M3 ----+

        [ACK không đi trước mốc sync cần thiết của batch]
```

**Hệ quả:** Khi client nhận ACK của replica ở chế độ batch và storage thực hiện đúng cam kết sync, mutation có cơ sở phục hồi mạnh hơn trên **replica đó** nếu máy mất điện trước flush SSTable. Đổi lại, write latency có thể bao gồm thời gian chờ batch window và disk sync; nếu I/O commit log chậm, p95/p99 có thể tăng.

**Không đồng nghĩa:** batch sync tạo transaction nhiều partition, đảm bảo mọi replica đã fsync, hoặc miễn nhiễm với mất/tha hóa ổ đĩa.

### 3.3. `group` — nếu phiên bản/bản phân phối hỗ trợ

Một số phiên bản Cassandra cung cấp **`commitlog_sync: group`**, với ý tưởng **group commit**: đợi một cửa sổ thời gian để gom nhiều mutation, thực hiện sync, rồi mới hoàn tất ACK tương ứng. Mục tiêu là cân bằng chi phí sync và latency.

Không nên suy rằng `group` luôn có mặt với **cùng tên tham số hay cùng giá trị mặc định** ở mọi bản Cassandra. Hãy tra đúng tài liệu và `cassandra.yaml` của **phiên bản đang chạy**. Trong bài này, khi tính cửa sổ mất log, tập trung vào hai mẫu ngữ nghĩa:

- **ACK có thể trước sync:** tiêu biểu là **periodic**.
- **ACK chờ sync:** tiêu biểu là **batch**, và **group** ở những bản có bảo đảm này.

Nếu triển khai không hỗ trợ group hoặc không xác định được chế độ của nó, **không tự thêm tham số vào production** hoặc khẳng định group chắc chắn hoạt động giống batch trong mọi chi tiết.

### 3.4. Bảng đối chiếu theo ngữ nghĩa

| Tiêu chí | `periodic` | `batch` | `group` (nếu hỗ trợ) |
| --- | --- | --- | --- |
| Lịch sync | Theo chu kỳ cấu hình. | Khi xử lý batch cần sync trước ACK. | Gom ghi theo cửa sổ group commit rồi sync. |
| ACK replica có thể đến trước sync của mutation mới? | **Có.** | Theo ngữ nghĩa batch: **không**. | Theo ngữ nghĩa group commit: **không**. |
| Rủi ro log chưa sync sau mất điện | Có đối với những append chưa bền vững. | Giảm cho những ghi đã ACK, nếu storage tôn trọng sync. | Giảm cho những ghi đã ACK, nếu storage tôn trọng sync. |
| Ảnh hưởng latency | Thường thuận lợi vì không chờ sync từng ACK. | Có thể đợi batch/sync. | Có thể đợi group window/sync. |
| Vấn đề riêng | Cửa sổ dữ liệu đã ACK nhưng chưa sync. | Sync latency có thể chi phối p99. | Cần điều chỉnh group window theo bản hỗ trợ. |
| Điều không đổi | RF/CL, memtable, SSTable, repair, backup. | RF/CL, memtable, SSTable, repair, backup. | RF/CL, memtable, SSTable, repair, backup. |

## 4. Cấu hình minh họa: đừng trộn tên tham số giữa các bản

Tham số `commitlog_sync` thuộc **cấu hình node** (thường trong `cassandra.yaml`), **không** phải một lựa chọn `CONSISTENCY` của `cqlsh` hoặc một mệnh đề CQL.

### 4.1. Ví dụ periodic

```yaml
# cassandra.yaml — chỉ minh họa cho bản có tên tham số này.
commitlog_sync: periodic
commitlog_sync_period_in_ms: 10000
```

Giá trị `10000` biểu diễn **chu kỳ sync danh nghĩa 10.000 ms = 10 giây**, không phải khuyến nghị đặt production ở 10 giây. Cần kiểm tra đơn vị, tham số và phạm vi hỗ trợ của đúng bản Cassandra. Chế độ này cho phép ACK trước sync định kỳ, nên cần đánh giá failure model và thiết kế RF.

### 4.2. Ví dụ batch

```yaml
# cassandra.yaml — một ví dụ thay thế periodic, KHÔNG dùng cùng lúc.
commitlog_sync: batch
commitlog_sync_batch_window_in_ms: 2
```

Số `2` ở đây **chỉ là ví dụ minh họa cú pháp** cho phiên bản có tham số tương ứng, không phải giá trị được khuyến nghị hay cam kết về độ trễ. Cấu hình có thể khác ở bản Cassandra mới hoặc bản phân phối thương mại. Nếu phiên bản hỗ trợ `group`, xem đúng tên thuộc tính group window trong cấu hình của bản đó.

### 4.3. Checklist khi thay cấu hình

Trước khi thay `commitlog_sync`:

1. Xác minh **phiên bản Cassandra** và `cassandra.yaml` thực tế của tất cả node.
2. Xác định chế độ, chu kỳ/window, commit log directory và loại thiết bị đang sử dụng.
3. Đo baseline **write latency, throughput, commitlog fsync latency** và tình trạng flush.
4. Nêu rõ **kiểu sự cố** đang muốn chịu: process crash, OS crash, mất điện một host, mất rack hay mất DC.
5. Đánh giá **CL/RF/fault domain**: bao nhiêu replica đã ACK và chúng nằm ở đâu.
6. Thử trên lab với dữ liệu giả; không thay cấu hình tất cả node production đồng thời khi chưa có quy trình.
7. Ghi nhận tác động đến startup/replay, disk space, memtable flush và downstream SLA.
8. Có phương án rollback vận hành và xác nhận cấu hình thực tế sau rollout.

**Cảnh báo:** Một cluster có các node cấu hình sync khác nhau sẽ có mức bảo vệ **cục bộ không đồng nhất**. Cùng một response `QUORUM` có thể bao gồm ACK từ những replica với cơ chế sync khác nhau, nên không suy một chính sách durability chung nếu chưa kiểm tra từng node.

## 5. “Cửa sổ dữ liệu có thể mất” thực sự là gì?

Khi nói **“có thể mất 10 giây dữ liệu”**, cần xác định rõ:

- Dữ liệu nào? **Các mutation đã ACK nhưng phần log chưa sync trên một replica**, hay **mọi write của cluster**?
- Mất do đâu? **Process crash**, **OS crash**, **host mất điện**, **mất disk**, hay **mất cả datacenter**?
- Thời điểm nào? **Lúc ACK**, lúc **client nhận success**, hay lúc **node được khởi động lại**?
- Có bản sao khác không? Những replica khác đã lưu/sync/flush mutation chưa?
- Khi đọc lại, dữ liệu có thể chỉ **chưa quan sát được** hay thực sự đã **mất tất cả bản sao có thể phục hồi**?

### 5.1. Timeline periodic minh họa

Giả sử chu kỳ sync danh nghĩa là 10 giây:

```text
t=00s: commit log sync hoàn tất
t=02s: mutation M1 append -> replica ACK
t=06s: mutation M2 append -> replica ACK
t=08s: mutation M3 append -> replica ACK
t=09s: host mất điện, OS page cache mất
t=10s: lần sync dự kiến tiếp theo chưa bao giờ xảy ra

M1/M2/M3 có thể chưa có log bền vững trên replica đó.
Những mutation đã sync trước t=00s không ở cùng cửa sổ rủi ro.
```

Đây là một **tình huống có thể xảy ra**, không phải khẳng định mọi mutation trong cửa sổ đều sẽ mất: thiết bị có thể đã ghi một phần xuống storage, hoặc memtable đã flush/sync, hoặc các replica khác còn dữ liệu.

### 5.2. Chu kỳ sync không phải giới hạn RPO tuyệt đối

Nếu đặt `commitlog_sync_period_in_ms = 10000`:

- `10 giây` là **khoảng thời gian lập lịch sync mong muốn** trong cấu hình minh họa.
- Nó **không** bảo đảm trong mọi tình huống “chỉ mất tối đa 10 giây” ở cấp cluster.
- Sync có thể bị trì hoãn vì scheduling, tài nguyên, I/O storage hoặc trạng thái node.
- Độ bền còn phụ thuộc flush SSTable, storage cache và các bản sao khác.
- RPO của ứng dụng phải được định nghĩa và đo bằng quy trình DR/backup/replication cụ thể, không được lấy trực tiếp từ một tham số node.

**Phát biểu chính xác hơn:** Với periodic, các ghi mới được ACK kể từ điểm sync bền vững gần nhất **có rủi ro cục bộ** nếu node mất khả năng giữ phần log chưa sync. Độ dài và lượng dữ liệu của vùng rủi ro phụ thuộc lịch sync thực, tải và các cơ chế lưu trữ liên quan.

### 5.3. Dùng ký hiệu để phân tích

Gọi:

- `A_i(t)`: tập mutation mà replica `i` đã **ACK** tới thời điểm `t`.
- `D_i(t)`: tập mutation có trạng thái **bền vững cục bộ có thể phục hồi** từ commit log đã sync hoặc SSTable hợp lệ ở replica `i`.
- `V_i(t) = A_i(t) \setminus D_i(t)`: tập mutation đã ACK nhưng **chưa có bảo đảm phục hồi cục bộ** theo giả định storage/failure đang xét.

Với periodic, `V_i(t)` **có thể không rỗng**. Với chế độ đợi sync trước ACK, `V_i(t)` được kỳ vọng nhỏ hơn trên đường ghi ACK bình thường, nếu storage và các giả định sync đúng.

**Không được suy:** `V_i(t)` chính là “dữ liệu sẽ mất”. Nó chỉ là **dữ liệu có nguy cơ** trong một kịch bản mất log; nó có thể còn ở replica khác.

## 6. Phân biệt kiểu sự cố và phạm vi có thể mất

### 6.1. Process crash, hệ điều hành vẫn sống

Khi **tiến trình Cassandra** crash nhưng kernel/filesystem vẫn sống, OS page cache có thể còn giữ những bytes đã ghi nhưng chưa fsync. Tùy cơ chế ghi, shutdown, filesystem và thời điểm restart, một phần log vẫn có thể được đọc/replay.

**Không tự coi process crash giống mất điện.** Cũng không hứa mọi append chưa fsync chắc chắn được replay chỉ vì OS chưa tắt: còn các lỗi corruption, file descriptor, storage và trạng thái commit log.

### 6.2. OS crash hoặc host mất điện

Khi kernel/host mất nguồn và các bộ đệm volatile biến mất, **bytes chưa được đồng bộ bền vững** có thể không hiện diện sau restart. Đây là failure model nổi bật làm lộ sự khác biệt periodic so với chế độ đợi sync trước ACK.

Với periodic, replica có thể đã ACK mutation nhưng mất phần commit log chưa sync. Với batch/group chờ sync, một mutation đã ACK có đường replay cục bộ tốt hơn **theo giả định thiết bị tôn trọng yêu cầu sync**.

### 6.3. Mất toàn bộ thiết bị lưu trữ của một node

Nếu cả commit log và SSTable của một replica bị mất do disk failure/corruption, **`fsync` trước ACK cũng không bảo vệ node đó khỏi mất toàn bộ disk**. Cần những replica khác, backup hoặc quy trình phục hồi khác.

Nếu commit log và data đặt trên các thiết bị khác nhau, lỗi có thể ảnh hưởng từng thành phần khác nhau. **Không nên kết luận chỉ cần commit log được fsync là node miễn nhiễm với mất disk.**

### 6.4. Mất rack, nguồn điện chung hoặc cả DC

Hai replica nằm trên hai host nhưng chung rack/power domain có thể cùng bị ảnh hưởng bởi một sự cố. CL chỉ đếm phản hồi **theo tập replica và phạm vi logic**, không tự đảm bảo chúng thuộc những miền lỗi độc lập. Placement, rack/DC topology, storage và vận hành mới quyết định mức chống lỗi tương quan.

### 6.5. Mất kết nối mạng không đồng nghĩa mất dữ liệu

Replica vẫn lưu dữ liệu nhưng coordinator không liên lạc được có thể làm request `Unavailable` hoặc timeout. Khi mạng phục hồi, mutation có thể vẫn nằm trên replica đã ACK, hoặc sẽ được phát lại nhờ hints/repair. Đây là **mất khả năng xác nhận/quan sát tạm thời**, không tự chứng minh mất dữ liệu vĩnh viễn.

### 6.6. Bảng failure model

| Sự cố | Điều có nguy cơ mất tại một replica | Cơ chế bảo vệ có liên quan |
| --- | --- | --- |
| Cassandra process crash, OS còn chạy | Dữ liệu RAM; log chưa sync có thể vẫn nằm trong OS cache nhưng không nên coi là bảo đảm. | Replay commit log còn tồn tại; SSTable đã flush. |
| OS crash/host mất điện | Memtable và commit log chưa bền vững. | Sync commit log, SSTable, replica khác. |
| Disk chứa commit log hỏng | Phần log trên thiết bị đó, kể cả đã sync. | SSTable trên thiết bị còn lành, replica khác, backup. |
| Disk dữ liệu/SSTable hỏng | SSTable trên node; commit log có thể không còn đủ replay dữ liệu đã flush. | Replica khác, snapshot/backup/repair phù hợp. |
| Mất node/rack cùng nguồn điện | Nhiều replica trong cùng fault domain. | Placement đa rack/DC, RF, backup, kiến trúc cấp nguồn. |
| Mạng tách DC | Khả năng nhận ACK/đọc chéo DC; không nhất thiết mất bytes. | CL local phù hợp, phục hồi mạng, hints/repair. |
| Timeout hoặc mất response | **Không biết chắc** lần ghi đã thực hiện tới đâu. | Operation ID, idempotency, đối soát. |

## 7. Durability trên replica và durability của cluster là hai bài toán

### 7.1. RF và CL chỉ định số bản sao và số ACK

**Replication factor (RF)** xác định số replica đích của partition. **Consistency level (CL)** xác định số ACK cần chờ để báo success. Ví dụ một DC RF=3:

| CL ghi | Số replica ACK cần thiết |
| --- | ---: |
| `ONE` | 1 |
| `TWO` | 2 |
| `QUORUM` | `floor(3/2)+1=2` |
| `ALL` | 3 |

Một request `QUORUM` thành công có **ít nhất hai replica ACK**, nhưng **trạng thái fsync của mỗi replica** còn phụ thuộc `commitlog_sync`. Không thể thay phương trình ACK bằng phương trình “hai bản sao chắc chắn đã xuống đĩa”.

### 7.2. Các tình huống RF=3, CL=QUORUM

| Kịch bản | Kết luận hợp lý |
| --- | --- |
| R1, R2 đã ACK ở periodic; R3 chưa ACK. | Ghi đạt `QUORUM`; **R1/R2 có thể** còn phần log chưa sync. |
| Chỉ R1 mất điện trước sync; R2 còn sống với mutation. | **R2 có thể giữ được dữ liệu**, nên lỗi cục bộ R1 không tự chứng minh mất toàn cluster. |
| R1 và R2 cùng mất điện trước sync, R3 chưa có mutation. | Có **rủi ro** cả hai bản ACK không replay được; độ bền cụm phụ thuộc dữ liệu còn thực tế ở đâu. |
| R1/R2 đã ACK ở batch và sync thành công; R3 down. | Hai bản ACK có cơ sở replay cục bộ tốt hơn trước kiểu mất cache, **không miễn nhiễm mất disk cả hai**. |
| Cả ba replica đều mất thiết bị lưu trữ, không có backup. | Chế độ sync không cứu được khi tất cả bản sao và log đã bị mất vật lý. |

**Từ “có rủi ro” rất quan trọng.** Không thể khẳng định một lần mất điện **chắc chắn** làm mất toàn bộ những mutation chưa `fsync`: OS/thiết bị có thể đã ghi một phần trước đó, hoặc replica khác đã nhận và flush.

### 7.3. `ALL` cũng không là bảo hiểm tuyệt đối

Ghi `ALL` RF=3 nhận đủ ba ACK. Nếu cả ba node dùng periodic và cùng mất điện trước những lần sync liên quan, có thể vẫn tồn tại **cửa sổ rủi ro tương quan**. Nếu chúng ở các rack/DC độc lập và không cùng mất điện, xác suất và đặc điểm rủi ro khác.

Nói “`ALL` nghĩa là dữ liệu không bao giờ mất” là lời hứa vượt quá những gì CL chứng minh. Điều kiện ACK không phải hợp đồng bảo hành ổ đĩa hoặc backup.

### 7.4. `ANY` và hint

`ANY` chỉ dành cho **ghi thường**. Trong tình huống hỗ trợ, request có thể được xác nhận vì coordinator/hint host giữ được **hint**, trong khi **chưa replica đích nào ACK**. Khi đó:

- Không được coi hint là một replica đích đã có dữ liệu để phục vụ đọc.
- Độ bền và khả năng phát lại còn phụ thuộc host lưu hint, storage và giới hạn hinted handoff.
- Ghi `ANY` thành công không cho phép kết luận một `SELECT ONE` ngay sau đó chắc chắn thấy mutation.

Hinted handoff là cơ chế hỗ trợ hội tụ **best effort**, không thay thế anti-entropy repair hoặc backup.

## 8. Nhiều DC: ACK local, global và mất một datacenter

Giả sử `NetworkTopologyStrategy` có RF=3 tại `dc1` và RF=3 tại `dc2`:

```text
                       Partition P

    dc1: R1  R2  R3                 dc2: R4  R5  R6
          RF=3                           RF=3

        Tổng RF = 6, QUORUM toàn cụm = 4.
```

| CL ghi | Ngưỡng ACK bắt buộc | Điều không thể suy từ success |
| --- | --- | --- |
| `LOCAL_ONE` tại dc1 | 1 ACK dc1. | Mọi replica dc2 đã nhận/sync. |
| `LOCAL_QUORUM` tại dc1 | 2 ACK dc1. | DC2 đã có quorum ACK. |
| `QUORUM` toàn cluster | 4 ACK bất kỳ trên 6 replica. | Mỗi DC đều đã có local quorum ACK. |
| `EACH_QUORUM` | 2 ACK dc1 **và** 2 ACK dc2. | Mọi replica của cả hai DC đã ACK. |
| `ALL` | 6 ACK. | Các ổ đĩa/fault domain không thể cùng hỏng. |

### 8.1. LOCAL_QUORUM không nghĩa là không replication từ xa

Mutation vẫn cần được phân phối theo topology đến các replica ở DC khác, nhưng ghi `LOCAL_QUORUM` có thể trả success khi **hai replica trong local DC** ACK. Nếu remote DC bị cô lập, ứng dụng ở DC còn khỏe có thể tiếp tục ghi tại local CL, song các client remote **không được bảo đảm** đọc thấy mutation ngay.

### 8.2. ACK từ hai DC không tự cho biết fsync

Nếu ghi `EACH_QUORUM` RF=3+3 thành công, coordinator đã nhận **ít nhất hai ACK tại từng DC**. Nhưng nếu cả hai DC đều dùng periodic, những ACK ấy **có thể trước sync** trên từng replica. Nếu doanh nghiệp yêu cầu phục hồi sau mất điện toàn bộ từng DC, phải đánh giá commitlog sync, fault domain, storage, khả năng chịu lỗi đồng thời và DR strategy.

### 8.3. RF bất đối xứng

Nếu `dc1 RF=5` và `dc2 RF=1`, `QUORUM` toàn cluster vẫn cần 4 ACK trên tổng 6, và có thể nhận cả bốn **chỉ tại dc1**. Do đó ghi `QUORUM` global không đồng nghĩa có một bản sao đã ACK ở remote DC trong mọi topology.

### 8.4. Không trộn khái niệm RPO và commitlog sync

**RPO** là mức mất dữ liệu tối đa được doanh nghiệp chấp nhận khi phục hồi sau sự cố xác định. Tham số periodic chỉ giúp mô tả **rủi ro log chưa sync cục bộ**; nó không tự cung cấp RPO của **toàn hệ thống**. Một kiến trúc DR cần cân nhắc:

1. RF và placement tại mỗi fault domain.
2. Độ bền cục bộ của mỗi ACK theo `commitlog_sync`.
3. Những DC/rack có thể hỏng cùng lúc.
4. Hinted handoff/repair và độ trễ hội tụ.
5. Snapshot, backup, restore test và cơ chế ứng dụng đối soát.

Không hứa “`EACH_QUORUM` luôn RPO=0” hoặc “periodic 10 giây nghĩa là cluster mất tối đa 10 giây”.

## 9. `durable_writes`: có dùng commit log hay không?

Keyspace Cassandra có thuộc tính **`durable_writes`**, ảnh hưởng việc mutation thông thường có được ghi vào commit log cho keyspace đó hay không.

Ví dụ cấu hình keyspace trong lab:

```sql
CREATE KEYSPACE IF NOT EXISTS sync_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;
```

**`durable_writes = true`** cho phép write path sử dụng commit log để phục hồi mutation chưa flush. Nhưng nó **không** buộc mọi ACK đợi `fsync` nếu node chạy periodic.

**`durable_writes = false`** có thể bỏ đường ghi commit log đối với những mutation thuộc phạm vi hỗ trợ; nếu node crash trước flush và không có log tương ứng để replay, replica có thể mất mutation ở memtable. Đừng bật chế độ này để benchmark một workload nghiệp vụ quan trọng mà chưa hiểu rủi ro.

### Ba cấu hình tương tác

| Cấu hình | Câu hỏi nó trả lời |
| --- | --- |
| `durable_writes` của keyspace | Mutation thường có được ghi commit log phục hồi hay không? |
| `commitlog_sync` của node | Log được sync vào lúc nào so với replica ACK? |
| RF + CL của request | Có bao nhiêu replica phải ACK ở phạm vi nào trước khi coordinator trả success? |

Không dùng một trong ba cấu hình thay thế ý nghĩa của hai cấu hình còn lại.

## 10. Commit log segment, replay và SSTable flush

Commit log thường được tổ chức thành **segment**. Các segment có thể chứa mutation của nhiều table. Memtable giữ dữ liệu có thể cập nhật trong memory; khi flush, nó tạo SSTable bất biến trên disk.

```text
      mutation ---> commit log segment 101 ----+
                                            /   \
                                      table A   table B
                                       |          |
                                     memtable A  memtable B
                                       |          |
                                     flush A    flush B
                                       |          |
                                     SSTable    SSTable

 Segment chỉ đủ điều kiện thu hồi khi không còn mutation
 chưa flush cần phụ thuộc vào nó theo tracking của Cassandra.
```

### 10.1. Commit log replay

Sau crash, nếu SSTable chưa chứa những mutation trong memtable, Cassandra có thể **replay commit log còn tồn tại hợp lệ** để xây dựng lại trạng thái. Ở periodic, phần log **chưa được sync và thực sự bị mất** sau sự cố không thể replay chỉ bằng ý chí của hệ thống.

### 10.2. Flush bảo vệ một đường khác

Nếu memtable đã flush thành SSTable hợp lệ, mutation có thể được khôi phục từ SSTable mà không cần dựa vào đoạn commit log cũ. Vì vậy **cửa sổ rủi ro do log chưa sync không đồng nghĩa mọi mutation kể từ lần sync trước chắc chắn chưa bền vững**: một số có thể đã vào SSTable hoặc bản sao khác.

### 10.3. Không nhầm flush, compaction và repair

- **Flush:** chuyển memtable cục bộ thành SSTable.
- **Compaction:** hợp nhất/viết lại SSTable cục bộ, xử lý phiên bản cũ/tombstone theo quy tắc.
- **Anti-entropy repair:** so sánh/sửa dữ liệu **giữa các replica**.
- **Hinted handoff:** lưu/phát lại mutation mà replica tạm thời bỏ lỡ.

Không cơ chế nào trong số này là “bản sao thay thế cho `fsync`” về mặt ngữ nghĩa; mỗi cơ chế xử lý một vấn đề và thời điểm khác nhau.

### 10.4. Không xóa commit log thủ công

Một segment còn chứa mutation chưa flush của table nào đó vẫn cần cho replay. Xóa commit log để “giải phóng disk” khi Cassandra đang chạy có thể làm mất khả năng khôi phục dữ liệu. Nếu commit log space tăng, hãy điều tra **flush backlog, disk latency, capacity và trạng thái node**, không sửa bằng xóa file tùy tiện.

## 11. CQL lab: quan sát những gì CQL chứng minh được

Lab cần một cluster Cassandra riêng có DC thật tên `dc1` và đủ ít nhất ba node cho RF=3. Các lệnh quản trị chỉ được dùng ở môi trường test, **không gây crash hoặc mất điện trên production**.

### 11.1. Chuẩn bị dữ liệu

```sql
CREATE KEYSPACE IF NOT EXISTS sync_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS sync_lab.event_by_id (
  event_id uuid PRIMARY KEY,
  state text,
  operation_id uuid,
  event_at timestamp
);
```

`event_id` là partition key; tất cả truy vấn tiếp theo nhắm vào **cùng partition**. Điều này làm ngưỡng replica dễ lý giải hơn so với truy vấn quét nhiều partition.

### 11.2. Ghi/đọc ở QUORUM

Trong `cqlsh`:

```sql
CONSISTENCY QUORUM;

INSERT INTO sync_lab.event_by_id (
  event_id, state, operation_id, event_at
) VALUES (
  11111111-1111-4111-8111-111111111111,
  'RECEIVED',
  22222222-2222-4222-8222-222222222222,
  '2026-11-21 10:00:00+0000'
);

SELECT state, operation_id, WRITETIME(state)
FROM sync_lab.event_by_id
WHERE event_id = 11111111-1111-4111-8111-111111111111;
```

`CONSISTENCY QUORUM` là **lệnh `cqlsh`**, áp dụng cho các statement sau đó trong phiên shell. Nếu INSERT thành công, coordinator đã đủ ACK theo `QUORUM`. Nhưng `WRITETIME(state)` chỉ cho biết **timestamp logic của cell**, không phải thời gian `fsync` hoặc thời điểm ACK.

**Đừng cố suy chế độ commitlog_sync từ một lần INSERT/SELECT thành công**. CQL không cung cấp trực tiếp “fsync hoàn tất lúc nào” cho từng cell.

### 11.3. Bật tracing có kiểm soát

```sql
TRACING ON;

CONSISTENCY QUORUM;

UPDATE sync_lab.event_by_id
SET state = 'PROCESSED'
WHERE event_id = 11111111-1111-4111-8111-111111111111;

TRACING OFF;
```

Trace có thể cho thấy coordinator, message và latency; **không phải toàn bộ lịch sử syscall `fsync` trên từng replica**. Không bật tracing diện rộng trên production.

### 11.4. Quan sát memtable/flush

Trên shell quản trị của **một node trong lab**:

```bash
nodetool status
nodetool tablestats sync_lab
nodetool compactionstats

# Chỉ ở lab: yêu cầu flush table để quan sát vòng đời.
nodetool flush sync_lab event_by_id

nodetool tablestats sync_lab
```

Sau flush, memtable chuyển sang SSTable theo cơ chế node; nó **không chứng minh** rằng trước flush mutation hoàn toàn không durable, bởi commit log có thể đã sync. Cũng không chứng minh tất cả replica đều đã flush, vì lệnh quản trị được thực hiện trên node đang kết nối.

### 11.5. Nếu muốn kiểm tra chế độ commit log

Kiểm tra **cấu hình node của cluster lab** bằng cách vận hành hỗ trợ của bản Cassandra đang dùng. Đừng đổi `commitlog_sync` qua CQL: đó **không phải** tham số per-statement. Muốn so sánh periodic/batch, cần hai lần chạy lab được cấu hình và khởi động đúng quy trình, với cùng workload, thiết bị và RF/CL, sau đó so **latency/throughput/fsync metrics**, không chỉ nhìn dữ liệu SELECT.

## 12. Java Driver 4.x: CL không điều khiển fsync

Ứng dụng Java Driver chọn **consistency level của request**, còn `commitlog_sync` được thiết lập **trên node Cassandra**. Driver không có tham số statement kiểu “`setCommitlogSync(BATCH)`” để ép từng mutation thay đổi chế độ sync của replica.

Ví dụ sau giả định có `CqlSession` với contact points, local datacenter, authentication/TLS đúng lab và `PreparedStatement` tái sử dụng:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteFailureException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

import java.time.Instant;
import java.util.UUID;

public final class SyncAwareWriter {
    public enum Outcome {
        ACKNOWLEDGED_AT_CL, UNAVAILABLE, UNKNOWN
    }

    private final CqlSession session;
    private final PreparedStatement insert;

    public SyncAwareWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO sync_lab.event_by_id " +
            "(event_id, state, operation_id, event_at) " +
            "VALUES (?, ?, ?, ?) USING TIMESTAMP ?");
    }

    public Outcome write(
            UUID eventId, UUID operationId,
            String state, Instant eventAt, long timestampMicros) {
        // Giữ eventId, operationId, payload và timestamp ổn định
        // nếu thử lại cùng yêu cầu nghiệp vụ.
        BoundStatement request = insert
            .bind(eventId, state, operationId, eventAt, timestampMicros)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);
        // idempotent=true chỉ đúng khi ngữ nghĩa mutation thực sự
        // cho phép lặp và không có side effect ngoài Cassandra.

        try {
            session.execute(request);
            return Outcome.ACKNOWLEDGED_AT_CL;
        } catch (UnavailableException e) {
            return Outcome.UNAVAILABLE;
        } catch (WriteTimeoutException
                 | WriteFailureException
                 | DriverTimeoutException e) {
            return Outcome.UNKNOWN;
        }
    }
}
```

### 12.1. Ý nghĩa response của đoạn Java

`ACKNOWLEDGED_AT_CL` nghĩa là request **đã được xác nhận ở `LOCAL_QUORUM`**. Nó **không** khẳng định hai replica ACK đều chạy batch sync hoặc phần commit log mới đã được fsync trong chế độ periodic.

`UNKNOWN` nghĩa là kết quả thực tế chưa rõ: mutation có thể đã tới một số replica hoặc được xử lý đầy đủ nhưng client mất response. Đừng đổi `eventId`/`operationId` để retry; hãy cân nhắc idempotency, timestamp và đối soát.

### 12.2. Không lẫn dữ liệu chưa đọc được với dữ liệu mất hẳn

Sau một request `LOCAL_QUORUM` thành công tại dc1, một client ở dc2 đọc `LOCAL_QUORUM` có thể chưa thấy mutation. Đây có thể chỉ là **độ trễ replication chéo DC**, không chứng minh mutation không có trên những replica đã ACK.

### 12.3. Khả năng có ghi cạnh tranh

Hai client cùng update một cell bằng ghi thường đều có thể đạt CL; Cassandra hòa giải theo **timestamp**, không tự áp dụng compare-and-set. Với bất biến nghiệp vụ như “chỉ một client được tạo đặt chỗ”, dùng LWT (`IF NOT EXISTS`/`IF`) và serial consistency phù hợp; `commitlog_sync` không thay thế Paxos.

## 13. Hỏng ghi và timeout: đừng lấy response để suy số bytes bền vững

### 13.1. `UnavailableException`

Coordinator đánh giá không đủ replica được coi là sống để đáp ứng CL. Ví dụ RF=3, ghi `QUORUM` cần hai nhưng chỉ một replica được xem là UP. Không có success theo CL; không tự kết luận dữ liệu cũ hoặc một request trước đó đã biến mất.

### 13.2. `WriteTimeoutException`

Coordinator không nhận đủ ACK đúng hạn. Ví dụ:

```text
R1: mutation áp dụng, ACK đến coordinator
R2: mutation có thể đã áp dụng, ACK đến muộn
R3: mất phản hồi
CL=QUORUM, RF=3: coordinator mới nhận 1 ACK trước deadline
-> WriteTimeout
```

**Không được hiểu** “chỉ nhận một ACK” thành “chỉ một replica đã áp dụng”. Trạng thái fsync của những replica đã áp dụng còn là câu hỏi **khác**.

### 13.3. `WriteFailureException`

Replica có thể báo lỗi I/O/storage khi xử lý mutation, khiến request không đạt CL. Một replica khác vẫn có thể ghi thành công. Nếu lỗi storage liên quan commit log, tăng timeout không giải quyết nguyên nhân.

### 13.4. Driver timeout hoặc coordinator mất kết nối

Coordinator có thể đã đủ ACK nhưng phản hồi mất trên mạng, dẫn tới driver timeout. Tầng ứng dụng không được tự coi request đã rollback. Hãy thiết kế **unknown outcome** và retry theo ID ổn định, tránh counter increment/list append hoặc side effect trùng.

### 13.5. Hai lớp câu hỏi sau mỗi lỗi

| Câu hỏi | Nguồn cần xem |
| --- | --- |
| Request **đã được xác nhận theo CL** chưa? | Response server/client, lỗi, trace, coordinator. |
| Mutation **còn có thể phục hồi sau failure model** không? | Replica placement, commit log sync, SSTable, storage, backups và thực tế sau sự cố. |

Một response success giải quyết câu thứ nhất theo CL; muốn đánh giá câu thứ hai phải có thêm giả định và bằng chứng.

## 14. Đo hiệu năng: thay commitlog_sync không chỉ tác động trung bình

Khi so sánh periodic và batch/group trên lab, cần giữ cố định **schema, partition distribution, RF, CL, client concurrency, thiết bị và tải**, nếu không kết quả sẽ bị nhiễu.

| Chỉ số | Vì sao quan trọng? |
| --- | --- |
| Write p50/p95/p99 latency | Chế độ đợi sync có thể làm tăng tail latency, nhất là khi disk bận. |
| Throughput/success rate | Đường ghi có đáp ứng mục tiêu tải không? |
| Commit log sync duration | Cho thấy chi phí `fsync` thực và mức biến động của storage. |
| Commit log segment space/pressure | Có backlog khi memtable flush chậm không? |
| Pending flush/compaction tasks | I/O nền có đang tạo cạnh tranh với commit log không? |
| GC, CPU, disk IO và queue | Tránh quy mọi timeout cho `commitlog_sync`. |
| Unavailable/WriteTimeout/WriteFailure | Phân loại lỗi thực tế, không gộp thành “ghi chậm”. |
| Tỷ lệ retry và request bị duplicate | Phân tích tác động từ phía ứng dụng. |

### Một thí nghiệm đối chứng hợp lý

1. Dùng **hai môi trường lab tương đương**, hoặc đổi cấu hình theo đúng quy trình giữa hai lần chạy.
2. Xác định phiên bản Cassandra và sự hỗ trợ cho periodic/batch/group.
3. Chọn workload ghi **cùng dạng mutation**, partition key phân bố đồng đều và tỷ lệ request cố định.
4. Giữ nguyên RF/CL và giới hạn concurrency; tránh hot partition ngoài chủ đích.
5. Đo latency, fsync duration, throughput và error rate sau khi node đã ổn định.
6. Khi phân tích durability, mô tả **kiểu failure** được mô phỏng; đừng gây mất điện thật trên thiết bị chia sẻ.
7. Ghi rõ giới hạn: benchmark khỏe mạnh **không tự chứng minh** khả năng phục hồi sau một lỗi chưa xảy ra.

**Không dùng một phép đo p99 để suy “batch luôn chậm hơn periodic đúng X ms”**. Chênh lệch phụ thuộc phần cứng, group window, lượng write đồng thời và workload cụ thể.

## 15. Các tình huống nghiệp vụ thực tế

### Tình huống A — Telemetry có thể tái tạo

Hệ thống lưu các phép đo đã có bản gốc ở một stream bền vững bên ngoài Cassandra. Một chút dữ liệu chưa được sync trên một replica có thể **tái nạp** theo event ID. Có thể ưu tiên thông lượng cùng periodic, nhưng vẫn phải tính toán cluster availability, deduplication và rủi ro lỗi đồng thời.

**Không suy:** telemetry luôn ít quan trọng. Một luồng cảnh báo an toàn có thể không chấp nhận trễ/mất dữ liệu.

### Tình huống B — Trạng thái giao dịch quan trọng

API thanh toán yêu cầu biết rõ thời điểm nào trạng thái ghi đã được chấp nhận và không tạo hai giao dịch khi retry. Chỉ đổi sang `batch` chưa đủ: cần **operation ID**, quy tắc idempotency, chính sách CL/fault domain, transaction nghiệp vụ phù hợp và đối soát sau timeout.

### Tình huống C — Ba replica periodic cùng nguồn điện

RF=3, client ghi `ALL` thành công, nhưng ba node nằm cùng nguồn điện và đều có mutation chưa fsync. Một lần mất nguồn chung có thể gây rủi ro **lỗi tương quan ở mọi bản sao đã ACK**.

**Bài học:** Chọn `ALL` không thay thế đặt replica ở các miền lỗi độc lập; sync và placement đều quan trọng.

### Tình huống D — Batch trên commit log disk chậm

Một cluster có write p99 tăng mạnh khi dùng batch. Metrics cho thấy `fsync` commit log chậm và không ổn định. Tăng memtable size không nhất thiết giải quyết, vì mốc ACK đang **chờ đồng bộ commit log**. Cần điều tra disk latency/storage và các tham số sync theo phiên bản.

### Tình huống E — Cụm còn dữ liệu dù một replica mất log

RF=3, ghi `QUORUM` thành công; R1 mất điện và mất phần log periodic chưa sync, R2 vẫn có mutation. Sau khi R1 khôi phục, replica khác và các cơ chế đồng bộ/repair có thể giúp nó nhận lại dữ liệu.

**Bài học:** Mất log cục bộ khác với mất toàn bộ bản sao của partition; cũng cần phân biệt phục hồi dữ liệu với thời điểm có thể phục vụ đọc theo CL.

### Tình huống F — Cửa sổ periodic không bằng SLA

Một nhóm cấu hình periodic 10 giây rồi cam kết “RPO của database là 10 giây trong mọi sự cố”. Cam kết này chưa có cơ sở: chưa nêu failure model, fault domain, sync thực tế, backup, replication và đo kiểm restore.

**Bài học:** RPO là thuộc tính của **quy trình phục hồi toàn hệ thống**, không phải phép đổi đơn vị từ một tham số `commitlog_sync`.

## 16. Bài tập và đáp án

### Bài 1 — ACK trước fsync

Node dùng periodic; mutation đã append commit log, cập nhật memtable và replica ACK. Có chắc log tương ứng đã được `fsync` không?

**Đáp án:** Không. Periodic cho phép ACK trước đợt sync định kỳ. Nếu node mất điện làm mất bytes chưa sync, replica có thể không replay được mutation ấy.

### Bài 2 — Batch khác periodic điểm nào?

Trong ngữ nghĩa `batch`, replica có phải chờ sync commit log cần thiết trước ACK không?

**Đáp án:** Có. Đó là điểm phân biệt quan trọng so với periodic. Đổi lại, write latency có thể chịu chi phí chờ sync.

### Bài 3 — Chu kỳ 10 giây

`commitlog_sync_period_in_ms=10000` có chứng minh “cluster mất tối đa đúng 10 giây dữ liệu” không?

**Đáp án:** Không. Nó là chu kỳ sync danh nghĩa của node; độ mất thực tế phụ thuộc thời điểm sync, scheduling, storage, flush, RF/CL, các replica còn sống và loại sự cố.

### Bài 4 — Process crash hay power loss?

Vì sao process Cassandra crash nhưng OS sống khác máy chủ mất điện?

**Đáp án:** OS page cache có thể tiếp tục giữ các bytes đã append khi process chết; còn mất điện có thể làm mất cache chưa bền vững. Không được coi hai failure model giống nhau hoặc bảo đảm replay mọi byte.

### Bài 5 — RF=3, QUORUM

R1 và R2 ACK ở periodic, R3 chưa ACK. Có chắc cả hai đã fsync commit log không?

**Đáp án:** Không. `QUORUM` chứng minh **hai ACK**, không chứng minh thứ tự fsync trong chế độ periodic.

### Bài 6 — Chỉ một replica mất log

R1 mất phần log chưa sync nhưng R2 còn dữ liệu của mutation. Có chắc mutation đã mất khỏi toàn cluster không?

**Đáp án:** Không. Mất dữ liệu cục bộ R1 không đồng nghĩa mất mọi bản sao; cần đánh giá replica khác, storage và reconciliation/repair.

### Bài 7 — ALL có bảo đảm chống mọi sự cố?

RF=3, ghi `ALL` thành công nhưng cả ba replica dùng periodic và cùng mất điện trước sync. Có thể khẳng định “không có rủi ro mất dữ liệu” không?

**Đáp án:** Không. CL yêu cầu ba ACK nhưng không tự đảm bảo cả ba đã sync, cũng không phòng tránh sự cố tương quan.

### Bài 8 — RF=3+3, EACH_QUORUM

Ghi `EACH_QUORUM` thành công. Điều đó có chứng minh hai DC đều đã fsync mọi ACK không?

**Đáp án:** Không. Nó chứng minh quorum ACK trong mỗi DC; fsync cục bộ còn phụ thuộc chế độ sync trên những replica ấy.

### Bài 9 — durable_writes=false

Một keyspace tắt commit log cho ghi thường, mutation chỉ ở memtable rồi node mất điện trước flush. Rủi ro gì?

**Đáp án:** Mutation có thể mất trên node đó vì memtable biến mất và không có bản ghi commit log tương ứng để replay. Replica khác có thể còn dữ liệu, nhưng không được coi bản ghi cục bộ đã durable.

### Bài 10 — WRITETIME có phải fsync time?

`SELECT WRITETIME(state)` trả một timestamp microsecond. Có thể dùng nó đo `fsync` hoặc ACK của commit log không?

**Đáp án:** Không. `WRITETIME` là timestamp logic gắn với cell đang thắng, không phải thời điểm storage sync hay phản hồi mạng.

### Bài 11 — Trạng thái UNKNOWN

Coordinator đủ hai ACK quorum và gửi success, nhưng phản hồi tới Java client bị mất. Driver timeout. Có được coi mutation chưa ghi rồi tạo event ID mới không?

**Đáp án:** Không. Kết quả client chưa rõ; tạo event ID mới có thể tạo hai sự kiện. Giữ ID/payload/timestamp ổn định và đối soát theo nghiệp vụ.

### Bài 12 — Segment có mutation nhiều table

Một commit log segment có mutation của table A và B. A đã flush, B chưa. Có được xóa segment thủ công không?

**Đáp án:** Không. B còn cần thông tin để replay; Cassandra tự theo dõi và thu hồi segment khi không còn mutation chưa flush phụ thuộc vào nó.

### Bài 13 — Flush và repair

R1 đã flush memtable thành SSTable. Có thể kết luận R2/R3 đã có cùng dữ liệu và không cần repair không?

**Đáp án:** Không. Flush là hoạt động trên một node; repair so sánh replica. SSTable của R1 không chứng minh replica khác đã bắt kịp.

### Bài 14 — Disk mất hoàn toàn

Replica chạy batch và commit log đã `fsync` nhưng cả thiết bị commit log và SSTable của node bị hỏng. Batch có khôi phục dữ liệu chỉ từ node đó được không?

**Đáp án:** Không. `fsync` không cứu được khi thiết bị chứa dữ liệu bị mất vật lý. Cần replica khác hoặc backup.

### Bài 15 — Group commit

Một bản Cassandra hỗ trợ `group`. Nên tự dùng tên tham số group window của bản Cassandra khác mà không kiểm tra không?

**Đáp án:** Không. Chế độ/tên tham số và đơn vị có thể phụ thuộc phiên bản. Phải xác minh tài liệu và cấu hình thực tế; chỉ triển khai sau khi đo latency và kiểm tra failure model.

### Bài 16 — Hạ CL để chữa timeout

API hứa ghi thành công ở `QUORUM`. Khi timeout, ứng dụng retry `ONE` rồi trả “quorum đã xác nhận”. Sai ở đâu?

**Đáp án:** `ONE` không xác nhận `QUORUM`. Retry thấp hơn thay đổi hợp đồng ACK, còn trạng thái của lần đầu có thể chưa rõ. Không hạ ngầm CL hoặc phát biểu sai mức xác nhận.

## 17. Checklist cuối bài và kết luận

Trước khi phát biểu một dữ liệu Cassandra “đã bền vững”, hãy trả lời:

1. **Keyspace có `durable_writes=true` không?** Mutation có được ghi commit log?
2. **Replica chạy `commitlog_sync` nào?** Periodic hay chế độ đợi sync trước ACK?
3. **Append, `fsync`, ACK và flush đã phân biệt chưa?** Những mốc đó không đồng nhất.
4. **RF và CL bao nhiêu?** Có bao nhiêu replica đã ACK, trong DC/rack nào?
5. **Kiểu sự cố đang xét là gì?** Process crash, power loss, disk failure hay mất cả fault domain?
6. **Có bản sao/SSTable/backup còn tốt không?** Mất một commit log cục bộ không mặc nhiên là mất toàn cluster.
7. **Có repair, hints và kế hoạch khôi phục không?** Dữ liệu bị bỏ lỡ hoặc lệch cần cơ chế hội tụ.
8. **Request có timeout không?** Thành công/unknown phải được đối soát đúng với CL và operation ID.
9. **Có ghi cạnh tranh/timestamp bất thường không?** Fsync không giải quyết race condition hay last-write-wins.
10. **RPO/RTO đã được kiểm chứng bằng DR test chưa?** Không suy SLA từ chu kỳ fsync danh nghĩa.

**Kết luận:** `commitlog_sync` xác định một trong những ranh giới quan trọng nhất của write durability **tại từng replica**. `periodic` cho phép ACK trước sync và có cửa sổ rủi ro cục bộ nếu host mất log chưa bền vững; `batch` và các chế độ group commit được hỗ trợ đặt ACK sau sync theo ngữ nghĩa riêng, thường đánh đổi bằng chi phí chờ I/O. Nhưng **độ bền của một mutation trên cluster** còn phụ thuộc RF/CL, vị trí replica, kiểu lỗi, SSTable flush, repair, backup và cách ứng dụng xử lý timeout.

Hãy luôn phân biệt **“đã được xác nhận ở CL”**, **“đã fsync trên một replica”** và **“có thể phục hồi sau loại sự cố doanh nghiệp yêu cầu”**. Ba câu này không tương đương, và không thể trả lời bằng một tham số duy nhất.

### Tài liệu tham khảo

- [Apache Cassandra — Storage Engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html): commit log, memtable, SSTable và write path.
- [Apache Cassandra — Dynamo / Tunable Consistency](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): RF, coordinator, replica và ngưỡng phản hồi.
- [Apache Cassandra — Configuring Cassandra](https://cassandra.apache.org/doc/stable/cassandra/configuration/cass_yaml_file.html): các tham số `commitlog_sync`, sync period/window và cấu hình theo phiên bản.
- [Apache Cassandra — CQL DDL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): `durable_writes` và cấu hình keyspace.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `CONSISTENCY`, `TRACING` khi thực hành.
- [Apache Cassandra — Hints](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hints.html): hinted handoff cho replica bỏ lỡ ghi.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): anti-entropy repair giữa các replica.
