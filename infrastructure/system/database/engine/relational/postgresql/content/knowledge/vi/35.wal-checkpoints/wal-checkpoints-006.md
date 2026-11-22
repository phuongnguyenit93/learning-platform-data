# fsync, synchronous_commit và đánh đổi độ bền trong PostgreSQL

Khi PostgreSQL trả lời ứng dụng rằng một transaction đã **COMMIT thành công**, ứng dụng thường hiểu rằng dữ liệu đã được lưu bền vững. Nhưng câu trả lời này phụ thuộc vào cấu hình ghi WAL, cách hệ điều hành và thiết bị lưu trữ thực hiện flush, và việc hệ thống có chờ bản sao đồng bộ hay không.

Hai thiết lập thường bị nhầm lẫn là **`fsync`** và **`synchronous_commit`**:

- `fsync` quyết định PostgreSQL có yêu cầu hệ điều hành đồng bộ các thay đổi xuống storage theo các điểm cần thiết để bảo đảm khả năng phục hồi sau sự cố hay không.
- `synchronous_commit` quyết định transaction phải chờ tới mức nào trước khi PostgreSQL xác nhận COMMIT: chờ WAL được flush trên primary, chờ standby ghi/flush WAL, hay chờ standby replay WAL; hoặc không chờ local flush trước khi trả lời.

Một khái niệm thứ ba cũng rất quan trọng là **checkpoint**. Checkpoint ghi các dirty data pages xuống data files và xác lập điểm redo cho crash recovery. Tuy nhiên, checkpoint không phải điều kiện để một transaction được xác nhận durable: PostgreSQL có thể xác nhận commit sau khi WAL commit record đã được flush, trong khi data pages tương ứng vẫn chưa được ghi xuống data files. Khi crash, PostgreSQL replay WAL để phục hồi các pages.

```text
Ứng dụng gửi COMMIT
        |
        v
PostgreSQL tạo WAL commit record
        |
        v
WAL được ghi và flush theo durability policy
        |
        +---- synchronous_commit=off
        |       có thể trả lời trước local WAL flush
        |
        +---- synchronous_commit=on
        |       chờ local WAL flush
        |       và standby flush nếu cấu hình sync replication
        |
        +---- remote_apply
                chờ synchronous standby replay WAL
        |
        v
COMMIT được xác nhận cho client
        |
        v
Data pages được checkpoint ghi xuống data files
        (có thể xảy ra sau đó)
```

Bài thuộc chương **WAL và checkpoint** của module *Database Engine Relational PostgreSQL*. Mục tiêu là hiểu ranh giới giữa “đã ghi”, “đã flush”, “đã được standby nhận” và “đã được standby áp dụng”, từ đó chọn cấu hình phù hợp với yêu cầu mất dữ liệu, độ trễ và tính sẵn sàng.

Sau bài học, bạn có thể:

1. Giải thích WAL write, WAL flush, fsync và data-page write khác nhau thế nào.
2. Phân biệt commit acknowledgement với checkpoint và crash recovery.
3. Nêu tác động của `fsync`, `wal_sync_method` và `full_page_writes`.
4. So sánh các mức `synchronous_commit`: `off`, `local`, `remote_write`, `on` và `remote_apply`.
5. Hiểu quan hệ giữa `synchronous_commit` và `synchronous_standby_names`.
6. Phân tích trường hợp transaction đã được ACK nhưng có thể mất khi primary crash.
7. Hiểu group commit và vì sao commit durability không nhất thiết phải flush riêng từng transaction.
8. Chọn transaction-level override cho dữ liệu có thể tái tạo và dữ liệu không được phép mất.
9. Theo dõi WAL, checkpoint, replication lag và wait events.
10. Lập kế hoạch thử nghiệm, backup, failover và hardening storage mà không đánh đổi durability một cách mù quáng.

> **Phạm vi thực hành:** Các lệnh thay đổi `fsync`, `synchronous_commit`, cấu hình synchronous standby hoặc mô phỏng crash chỉ dùng trong môi trường lab. Không tắt `fsync` trên database production đang chứa dữ liệu cần bảo toàn. Một process bị kill, một VM reset và một lần mất điện là các failure modes khác nhau; thử nghiệm cần thiết kế có kiểm soát.

---

## 1. Durability trong ACID nghĩa là gì?

### 1.1. Bốn thuộc tính ACID

| Thuộc tính | Ý nghĩa |
|---|---|
| Atomicity | Transaction hoặc được áp dụng toàn bộ, hoặc được rollback |
| Consistency | Transaction hợp lệ đưa database từ trạng thái hợp lệ sang trạng thái hợp lệ |
| Isolation | Các transaction đồng thời được điều phối theo isolation semantics |
| Durability | Khi commit đã được xác nhận theo durability contract, kết quả được bảo toàn qua sự cố trong phạm vi contract đó |

Durability không có nghĩa mọi data page đã được ghi xuống file bảng ngay khi ứng dụng nhận COMMIT. PostgreSQL dùng **Write-Ahead Logging (WAL)** để có thể xác nhận transaction sau khi log cần thiết đã được lưu bền vững, rồi ghi data pages vào thời điểm phù hợp.

### 1.2. Durability phải nói rõ failure model

Một hệ thống có thể tuyên bố durable với những giả định khác nhau:

- PostgreSQL backend process bị crash nhưng OS và storage vẫn chạy.
- OS/kernel crash hoặc máy chủ reboot đột ngột.
- Mất điện khiến volatile write cache bị mất.
- Storage device/controller hỏng.
- Primary mất hoàn toàn và hệ thống phải promote standby.
- Một vùng lưu trữ hoặc một availability zone bị mất.

`fsync` và `synchronous_commit` chủ yếu điều khiển việc đồng bộ WAL ở primary và standby. Chúng không thay thế backup, replication architecture, storage redundancy hoặc kế hoạch disaster recovery.

### 1.3. Acknowledgement là một cam kết

Khi client nhận COMMIT thành công, client thường không biết WAL đã được flush local, standby đã flush, hay standby đã replay. Ứng dụng phải dựa vào cấu hình PostgreSQL và topology replication để hiểu cam kết đó.

Đừng coi log “COMMIT successful” trong application là bằng chứng độc lập rằng dữ liệu đã được ghi xuống thiết bị bền vững. Nó chỉ cho biết server đã trả lời thành công theo durability settings tại thời điểm transaction kết thúc.

---

## 2. WAL write, WAL flush và data-page write

### 2.1. WAL là gì?

WAL ghi lại những thay đổi cần thiết để PostgreSQL phục hồi database sau crash. Thay vì phải ghi ngay mọi data page thay đổi xuống data files trước khi commit, PostgreSQL ghi WAL records theo thứ tự và bảo đảm WAL tương ứng được lưu trước khi data page liên quan được ghi.

Đó là nguyên tắc **write-ahead**:

> WAL mô tả thay đổi phải được lưu bền vững trước khi data page chứa thay đổi đó được ghi xuống storage.

### 2.2. Ba khái niệm

**WAL write**: dữ liệu WAL được chuyển từ PostgreSQL WAL buffers sang file WAL thông qua các lệnh ghi hệ điều hành. Điều này chưa nhất thiết có nghĩa dữ liệu đã an toàn trước mất điện.

**WAL flush**: PostgreSQL yêu cầu hệ điều hành đồng bộ WAL tới một điểm LSN xuống storage theo cơ chế sync được chọn. Khi `fsync` bật và hệ điều hành/storage thực hiện đúng cam kết, WAL tới điểm đó được coi là bền vững.

**Data-page write**: các page của table/index được ghi xuống data files. Những page này có thể được ghi bởi backend, background writer hoặc checkpoint sau khi transaction đã commit.

### 2.3. Minh họa

```text
Transaction T cập nhật account balance
                 |
                 v
          WAL records được tạo
                 |
                 v
          WAL buffer / WAL file
                 |
                 v
            WAL FLUSH
                 |
          COMMIT ACKNOWLEDGED
                 |
                 v
       Data page có thể vẫn dirty
                 |
                 v
       Checkpoint / background write
                 |
                 v
       Data file được cập nhật
```

Nếu server crash sau commit acknowledgement nhưng trước khi data page được ghi, crash recovery đọc WAL và replay những thay đổi cần thiết. Đây là lý do PostgreSQL không phải flush toàn bộ data files ở mỗi COMMIT.

### 2.4. LSN

LSN (Log Sequence Number) biểu diễn vị trí trong WAL stream. Nó giúp mô tả các điểm WAL đã được ghi, flush, nhận hoặc replay.

Trên primary, có thể xem các vị trí WAL:

```sql
SELECT
    pg_current_wal_lsn()        AS current_wal_lsn,
    pg_current_wal_insert_lsn() AS current_insert_lsn,
    pg_current_wal_flush_lsn()  AS current_flush_lsn;
```

Các hàm này có ý nghĩa khác nhau:

- `pg_current_wal_insert_lsn()`: vị trí WAL đã được insert.
- `pg_current_wal_lsn()`: vị trí WAL hiện hành theo hàm tương ứng.
- `pg_current_wal_flush_lsn()`: vị trí WAL đã flush trên primary.

Không so sánh LSN như timestamp; muốn tính khoảng cách bytes, dùng `pg_wal_lsn_diff(lsn1, lsn2)`.

### 2.5. Vì sao WAL flush đủ để commit durable?

WAL chứa thông tin phục hồi thay đổi. Khi commit record và các WAL records cần thiết đã được flush, PostgreSQL có thể phục hồi trạng thái transaction sau crash bằng cách replay WAL, ngay cả khi data files chưa phản ánh transaction đó.

Điều này phụ thuộc `fsync` và storage stack thực hiện đúng yêu cầu flush. Nếu thiết bị báo đã flush nhưng thực tế vẫn giữ dữ liệu trong volatile cache không được bảo vệ, bảo đảm durability có thể bị phá vỡ bên dưới PostgreSQL.

---

## 3. Checkpoint không phải commit flush

### 3.1. Checkpoint làm gì?

Checkpoint là một mốc trong WAL/recovery process. PostgreSQL yêu cầu ghi các dirty buffers thích hợp xuống data files và ghi checkpoint record để crash recovery biết bắt đầu redo từ vị trí nào.

Checkpoint giúp:

- Giới hạn lượng WAL cần replay sau crash.
- Cho phép WAL segments cũ được recycle hoặc xử lý theo điều kiện retention/archive.
- Ghi data pages ra storage theo đợt.
- Điều phối write workload để tránh ghi dồn quá nhiều ở cuối checkpoint.

### 3.2. Commit có cần chờ checkpoint?

Thông thường **không**. Với durability thông thường, transaction chỉ cần WAL được flush tới commit record theo policy. Data pages sẽ được ghi xuống storage sau đó.

Nếu phải đợi checkpoint cho từng COMMIT, hệ thống sẽ có write amplification và latency rất lớn. WAL cho phép tách việc xác nhận transaction khỏi việc flush toàn bộ data pages.

### 3.3. Crash recovery

Sau một crash:

1. PostgreSQL tìm checkpoint hợp lệ gần nhất.
2. Đọc WAL từ redo point cần thiết.
3. Replay các WAL records để đưa data pages tới trạng thái nhất quán.
4. Hoàn tất recovery trước khi phục vụ kết nối bình thường.

Transaction có commit record bền vững được phục hồi như committed; transaction không có commit record hợp lệ được xử lý theo quy tắc recovery như chưa commit.

### 3.4. Checkpoint thường xuyên và full-page writes

Checkpoint quá thường xuyên có thể làm tăng số full-page images được ghi vào WAL khi `full_page_writes` bật. Điều này làm tăng WAL volume và I/O. Checkpoint quá thưa có thể làm crash recovery lâu hơn và cần nhiều WAL giữ lại.

Đây là một đánh đổi giữa:

- WAL generation.
- Checkpoint write load.
- Recovery time objective.
- Storage throughput.

### 3.5. Các tham số checkpoint thường gặp

| Tham số | Vai trò |
|---|---|
| `checkpoint_timeout` | Khoảng thời gian tối đa giữa các checkpoint theo lịch |
| `max_wal_size` | Ngưỡng WAL mềm có thể khiến checkpoint được yêu cầu sớm |
| `min_wal_size` | Mức WAL tối thiểu được giữ/recycle theo cơ chế quản lý |
| `checkpoint_completion_target` | Mục tiêu phân tán checkpoint writes trong khoảng giữa các checkpoint |
| `checkpoint_flush_after` | Điều phối flush data files sau lượng ghi nhất định |
| `full_page_writes` | Ghi full-page image khi page được sửa lần đầu sau checkpoint, hỗ trợ phục hồi torn page |

`max_wal_size` không phải giới hạn cứng tuyệt đối cho dung lượng WAL trong mọi tình huống; archive lag, replication slots hoặc workload có thể khiến WAL giữ lại nhiều hơn.

---

## 4. fsync: bảo vệ WAL và data files trước crash

### 4.1. fsync là gì?

`fsync` là cơ chế hệ điều hành yêu cầu đồng bộ dữ liệu file đã ghi tới storage. PostgreSQL dùng các phương thức đồng bộ phù hợp để bảo đảm WAL và những file cần thiết được lưu theo đúng thứ tự durability.

Trong PostgreSQL:

```sql
SHOW fsync;
```

Giá trị mặc định là `on`. Với một database cần bảo toàn dữ liệu, giữ `fsync = on` là nguyên tắc cơ bản.

### 4.2. fsync = on

Khi `fsync` bật, PostgreSQL sử dụng các thao tác đồng bộ file cần thiết. Kết hợp với WAL protocol và storage thực hiện đúng flush semantics, nó bảo vệ database khỏi những rủi ro do hệ điều hành hoặc máy chủ crash.

`fsync` không có nghĩa mỗi row update sẽ gọi một fsync riêng. PostgreSQL có thể gom WAL của nhiều transaction và dùng **group commit** để chia sẻ chi phí flush.

### 4.3. fsync = off

Khi `fsync` tắt, PostgreSQL có thể không yêu cầu storage đồng bộ các file theo cách cần thiết. Sau OS crash hoặc mất điện, database có thể gặp **corruption không thể tự phục hồi bằng WAL thông thường**.

Rủi ro không chỉ là “mất vài transaction mới nhất”. Những data files hoặc WAL files có thể không nhất quán với nhau; database cluster có thể cần được restore từ backup.

### 4.4. synchronous_commit = on không cứu được fsync = off

`synchronous_commit` điều khiển việc transaction chờ flush; `fsync` quyết định PostgreSQL có thực hiện các yêu cầu đồng bộ cần thiết hay không.

Nếu `fsync = off`, việc chờ theo `synchronous_commit = on` không tạo ra bảo đảm durable thực sự. Có thể server trả lời sau khi ghi vào OS cache nhưng dữ liệu vẫn mất khi máy tắt đột ngột.

### 4.5. Khi nào fsync=off có thể xuất hiện?

Tài liệu PostgreSQL đề cập một số workload có thể cân nhắc tắt fsync khi **tạo lại toàn bộ cluster từ dữ liệu nguồn đáng tin** và có thể bỏ đi cluster nếu có sự cố, ví dụ nạp lại một database tạm thời trong quy trình benchmark.

Điều này chỉ hợp lý khi:

- Dữ liệu có thể tái tạo hoàn toàn.
- Cluster không chứa dữ liệu duy nhất.
- Người vận hành chấp nhận cluster có thể hỏng và phải dựng lại.
- Không có workload khác đang dựa vào cluster đó.
- Có kế hoạch bật lại fsync và bảo đảm checkpoint/flush phù hợp trước khi dùng dữ liệu lâu dài.

Không coi `fsync=off` là một tuning option thông thường để tăng tốc production.

### 4.6. fsync không thể sửa phần cứng nói dối

PostgreSQL dựa vào hệ điều hành và thiết bị lưu trữ thực hiện đúng các yêu cầu sync. Nếu storage controller hoặc hypervisor báo flush thành công trong khi dữ liệu vẫn ở cache volatile không có battery/flash protection, durability có thể bị mất.

Hãy xác minh:

- Write cache có battery-backed/flash-backed protection hay không.
- Cloud block storage công bố semantics durability nào.
- Hypervisor/virtual disk có truyền flush/barrier đúng không.
- RAID controller và filesystem có cấu hình an toàn không.
- UPS và power-loss behavior của host.

### 4.7. Quyền thay đổi

`fsync` là cấu hình server-level và chỉ superuser mới có thể thay đổi. Đừng cấp superuser cho application role để cho phép ứng dụng tùy tiện đổi durability.

---

## 5. wal_sync_method: PostgreSQL đồng bộ WAL bằng cách nào?

### 5.1. Vai trò

`wal_sync_method` chọn phương thức PostgreSQL dùng để yêu cầu hệ điều hành đồng bộ WAL files. Các lựa chọn phụ thuộc hệ điều hành và build:

- `fdatasync`.
- `fsync`.
- `fsync_writethrough` trên một số nền tảng.
- `open_datasync`.
- `open_sync` trên một số nền tảng.

Xem giá trị hiện hành:

```sql
SHOW wal_sync_method;
```

### 5.2. fdatasync và fsync

Ở mức khái niệm:

- `fdatasync` yêu cầu đồng bộ dữ liệu file và metadata cần thiết để đọc dữ liệu đó.
- `fsync` yêu cầu đồng bộ dữ liệu cùng metadata file theo semantics hệ điều hành.

Sự khác nhau về hiệu năng/behavior phụ thuộc OS, filesystem, storage và cách PostgreSQL ghi WAL. Không có một phương thức tốt nhất cho mọi máy.

### 5.3. open_datasync/open_sync

Một số hệ điều hành cho phép mở file với cờ đồng bộ để các write calls có semantics đồng bộ tương ứng. Chi phí và hiệu quả phụ thuộc implementation.

### 5.4. Đừng đoán theo tên

`wal_sync_method` không phải toggle “nhanh nhất”. Dùng công cụ `pg_test_fsync` được phân phối cùng PostgreSQL để đo các cách sync trên filesystem/storage cụ thể, rồi đánh giá trong workload thật.

### 5.5. Kiểm tra trên máy chủ

Trong shell của máy PostgreSQL:

```bash
pg_test_fsync --help
pg_test_fsync -f /path/to/test-file
```

Đây là ví dụ chạy công cụ hệ thống; đường dẫn test file phải thuộc thư mục lab có đủ dung lượng/quyền. Không chạy test ghi đĩa nặng trên production trong giờ cao điểm nếu chưa có kế hoạch.

### 5.6. pg_test_fsync không chứng minh toàn bộ durability

Công cụ đo hiệu năng các phương thức sync trên một file. Nó không xác minh:

- Thiết bị sẽ không hỏng.
- Controller không báo flush giả.
- Replication/failover đúng.
- Backup restore thành công.
- Workload ứng dụng không có lỗi logic.

Đây là dữ liệu benchmark cho lựa chọn sync method, không phải chứng nhận durability toàn hệ thống.

---

## 6. full_page_writes và torn-page protection

### 6.1. Torn page là gì?

Một data page PostgreSQL thường lớn hơn một số đơn vị ghi nguyên tử mà storage bảo đảm. Khi máy mất điện giữa một lần ghi page, file có thể chứa một phần nội dung cũ và một phần nội dung mới: **torn page**.

### 6.2. full_page_writes

Khi `full_page_writes` bật, PostgreSQL ghi full-page image vào WAL khi một page được sửa lần đầu sau checkpoint. Nếu data page bị torn trong quá trình ghi, recovery có thể dùng full-page image để phục hồi page trước khi replay các thay đổi tiếp theo.

```sql
SHOW full_page_writes;
```

Thông thường giá trị mặc định là `on`.

### 6.3. Không thay thế fsync

`full_page_writes` và `fsync` giải quyết các khía cạnh liên quan nhưng khác nhau:

- `full_page_writes` giúp recovery xử lý torn data pages.
- `fsync` bảo đảm những file/WAL writes cần thiết được yêu cầu đồng bộ xuống storage.

Tắt fsync không trở nên an toàn chỉ vì full_page_writes đang bật.

### 6.4. WAL volume

Full-page images có thể làm tăng WAL đáng kể sau checkpoint, đặc biệt ở workload cập nhật nhiều pages. Đó là một phần chi phí đổi lấy khả năng phục hồi torn page.

### 6.5. Data checksums

Data checksums có thể giúp phát hiện page corruption khi đọc page. Chúng là cơ chế phát hiện, không tự sửa mọi hỏng hóc và không thay WAL, fsync, backup hoặc full-page writes.

---

## 7. synchronous_commit điều khiển điều gì?

### 7.1. Khái niệm

`synchronous_commit` quy định PostgreSQL phải chờ tới đâu trước khi xác nhận một transaction commit thành công.

Giá trị hiện tại:

```sql
SHOW synchronous_commit;
```

Giá trị mặc định thường là `on`.

### 7.2. Năm mức

| Giá trị | Chờ local WAL flush? | Chờ synchronous standby? | Điều kiện remote |
|---|---|---|---|
| `off` | Không chờ cho từng commit | Không | WAL sẽ được flush sau đó bởi WAL writer/transaction khác |
| `local` | Có | Không | Không đợi standby |
| `remote_write` | Có | Có | Chờ standby ghi WAL tới OS, chưa chắc durable trên storage |
| `on` | Có | Có | Chờ standby flush WAL tới durable storage |
| `remote_apply` | Có | Có | Chờ standby replay/apply WAL để thay đổi có thể được đọc ở standby |

Các mức remote chỉ có ý nghĩa khi cấu hình synchronous replication phù hợp. Nếu không có synchronous standby được cấu hình, các mức chờ remote không tự tạo ra một standby; commit vẫn dựa trên local durability behavior.

### 7.3. off

`synchronous_commit = off` cho phép PostgreSQL trả COMMIT success trước khi WAL records của transaction được flush tới storage.

Hệ quả:

- Có thể giảm commit latency.
- Có thể tăng throughput trong workload nhiều transaction nhỏ.
- Nếu OS/server crash ngay sau ACK, một số transaction gần đây có thể bị mất.
- Database vẫn được phục hồi về trạng thái nhất quán nhờ WAL; rủi ro chính là **mất các transaction đã được ACK gần đây**, không phải chấp nhận một database logic bị ghi nửa transaction chỉ vì async commit.

Theo tài liệu PostgreSQL, khoảng thời gian tối đa từ commit tới lúc chắc chắn an toàn thường bị giới hạn bởi cơ chế WAL writer, xấp xỉ tối đa ba lần `wal_writer_delay`; trong điều kiện tải cao có thể ngắn hơn. Đây là giới hạn theo cơ chế hiện hành, không phải SLA cố định cho mọi cấu hình/storage.

### 7.4. local

`synchronous_commit = local` chờ WAL flush ở primary nhưng không chờ synchronous standby.

Phù hợp khi yêu cầu transaction đã bền vững ở primary trước khi ACK, nhưng không muốn latency/availability bị ràng buộc bởi synchronous replica.

Nếu primary mất hoàn toàn trước khi WAL được replicate tới standby, transaction có thể không có trên standby được promote. Local durability không đồng nghĩa HA durability.

### 7.5. remote_write

`remote_write` chờ primary flush WAL local và synchronous standby nhận WAL rồi ghi tới hệ điều hành của standby. Nó không nhất thiết chờ standby flush dữ liệu xuống storage bền vững.

Nếu standby OS crash hoặc mất điện, WAL đã chỉ nằm trong volatile OS cache có thể mất. Vì vậy remote_write mạnh hơn việc chỉ nhận WAL qua network nhưng yếu hơn remote flush.

### 7.6. on

`synchronous_commit = on` là mức mặc định:

- Primary chờ WAL local được flush.
- Nếu synchronous replication được cấu hình, primary chờ acknowledgement flush từ synchronous standby theo policy.
- Nếu không có synchronous standby, nó chờ local flush.

Đây là lựa chọn phổ biến khi muốn commit durability ở primary và synchronous replication theo cấu hình.

### 7.7. remote_apply

`remote_apply` chờ synchronous standby replay WAL records, không chỉ nhận hoặc flush chúng. Khi commit được xác nhận, transaction đã được áp dụng trên standby theo semantics replication.

Điều này hữu ích khi ứng dụng đọc ngay sau ghi từ synchronous standby và cần bảo đảm transaction đã được replay ở đó. Nó thường tăng latency vì standby phải vừa nhận, flush, vừa apply WAL.

### 7.8. Không nhầm remote_write với remote_apply

`remote_write` chỉ chờ WAL được ghi tới OS của standby; `remote_apply` chờ WAL được replay thành thay đổi database trên standby. Nếu mục tiêu là read-after-write từ standby, remote_write chưa đủ.

---

## 8. Bảng chọn synchronous_commit theo yêu cầu

| Yêu cầu | Mức thường cân nhắc | Đánh đổi |
|---|---|---|
| Giao dịch tài chính/đơn hàng đã ACK không được mất khi primary crash | `on`; kết hợp sync replication nếu cần failover zero/low RPO | Latency và khả năng commit phụ thuộc sync standby |
| Chỉ cần local primary durable, chấp nhận replication lag | `local` hoặc `on` khi không cấu hình sync standby | Failover sang async standby có thể mất WAL chưa replicate |
| Cần standby đã nhận và ghi OS, nhưng không cần standby flush durable | `remote_write` | Bảo vệ yếu hơn trước crash/power loss của standby |
| Cần đọc ngay từ synchronous standby sau commit | `remote_apply` | Chờ replay làm tăng latency |
| Telemetry, cache, staging có thể tái tạo | Có thể cân nhắc `off` cho transaction cụ thể | ACK gần đây có thể bị mất khi crash |
| Dữ liệu duy nhất, không thể dựng lại | Không dùng `off`; giữ fsync và policy phù hợp | Trả giá bằng latency/throughput để có durability |

Đây là hướng lựa chọn, không phải thay thế phân tích RPO/RTO, replication topology, storage durability và backup.

---

## 9. synchronous replication và synchronous_standby_names

### 9.1. Synchronous commit cần standby được chỉ định

`synchronous_commit` không tự tìm một server khác để sao chép dữ liệu. Synchronous replication cần cấu hình primary xác định standby nào có thể xác nhận commit, thường thông qua `synchronous_standby_names` và cấu hình standby.

### 9.2. Ví dụ cấu hình FIRST

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
```

Primary cần acknowledgement từ một standby được chọn theo thứ tự priority trong danh sách. Nếu standby ưu tiên đầu tiên không sẵn sàng, PostgreSQL có thể chọn standby tiếp theo theo quy tắc.

### 9.3. Ví dụ quorum ANY

```conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

Primary cần acknowledgement từ bất kỳ hai synchronous standbys trong nhóm. Quorum mode cho phép nhiều standby tham gia vào điều kiện xác nhận.

### 9.4. Các trạng thái sync_state

`pg_stat_replication` hiển thị `sync_state`. Các giá trị có thể gồm:

- `async`: standby asynchronous.
- `potential`: standby có thể trở thành synchronous theo cấu hình/order.
- `sync`: standby đang được chọn làm synchronous trong FIRST mode.
- `quorum`: standby tham gia nhóm quorum.

Không suy từ việc có một row trong `pg_stat_replication` rằng standby đó đang đáp ứng synchronous commit policy.

### 9.5. Nếu synchronous standby bị mất kết nối?

Nếu policy yêu cầu standby acknowledgement và không có standby đủ điều kiện, transaction có `synchronous_commit` chờ remote có thể **bị chặn tại COMMIT** cho đến khi một standby phù hợp trở lại hoặc cấu hình/thao tác vận hành thay đổi.

Đây là đánh đổi availability:

- Chờ standby giúp tăng durability khi failover.
- Chờ standby có thể làm write traffic dừng khi không có replica đáp ứng.

### 9.6. synchronous_commit=local

Nếu muốn các transaction vẫn commit sau local flush khi sync standby tạm mất, `local` bỏ phần chờ remote. Tuy nhiên, khi failover sang async/standby chưa nhận WAL, transaction đã ACK có thể bị mất.

### 9.7. synchronous_commit=off

`off` bỏ chờ local flush và cũng không chờ synchronous standby cho transaction đó. Nó có thể giảm latency nhưng yếu hơn local về durability.

### 9.8. remote_apply và read routing

`remote_apply` giúp bảo đảm transaction đã được replay ở synchronous standby được dùng để xác nhận commit. Tuy nhiên ứng dụng vẫn cần đọc từ đúng standby/replica thuộc synchronous policy; đọc từ một asynchronous replica khác vẫn có thể thấy dữ liệu cũ.

---

## 10. Group commit: nhiều transaction chia sẻ một lần flush

### 10.1. Không phải mỗi COMMIT luôn fsync riêng

Nếu nhiều transactions commit gần nhau, PostgreSQL có thể gom WAL records của chúng và flush một lần cho cả nhóm. Đây là **group commit**.

```text
Transaction A ---\
Transaction B ----+--> WAL flush tới LSN X
Transaction C ---/          |
                            v
                    A, B, C được ACK
```

Điều này giúp giữ durability mà không cần một syscall flush riêng cho từng transaction.

### 10.2. WAL flush là điểm đồng bộ

Với `synchronous_commit = on`, backend chờ tới khi WAL flush position đủ bao gồm commit record của transaction. Nếu một transaction khác kích hoạt flush tới LSN xa hơn, nhiều commits có thể được xác nhận cùng lúc.

### 10.3. commit_delay và commit_siblings

Các tham số `commit_delay` và `commit_siblings` có thể thêm một khoảng chờ ngắn trước WAL flush để tạo cơ hội gom thêm commits trong một số workload.

Không chỉnh chúng theo cảm tính:

- Delay quá lớn làm tăng commit latency.
- Không đủ concurrency thì không thu được group commit.
- Storage và workload thực tế quyết định lợi ích.

### 10.4. WAL writer

WAL writer background process giúp ghi/flush WAL theo lịch và giảm áp lực cho backend trong một số trường hợp. `wal_writer_delay` và `wal_writer_flush_after` điều chỉnh hành vi liên quan.

Với async commit, WAL writer có vai trò quan trọng trong việc flush các WAL records chưa được đồng bộ theo từng commit.

### 10.5. Tối ưu đúng tầng

Nếu commit latency cao, tìm nguyên nhân:

- Local WAL sync chậm?
- Storage queue/latency?
- Synchronous replication lag?
- Standby apply chậm?
- Network latency?
- WAL generation quá lớn?
- Checkpoint tạo I/O burst?
- Transaction concurrency và lock contention?

Chuyển `synchronous_commit=off` chỉ để giảm latency mà không hiểu bottleneck có thể làm suy yếu durability mà không giải quyết đúng vấn đề.

---

## 11. Override synchronous_commit theo transaction

### 11.1. SET LOCAL

`synchronous_commit` có thể được điều chỉnh trong phạm vi một transaction:

```sql
BEGIN;

SET LOCAL synchronous_commit = off;

INSERT INTO telemetry.events(event_type, payload)
VALUES ('page_view', '{"page":"home"}');

COMMIT;
```

Transaction này không chờ WAL flush theo mức thông thường trước khi trả commit acknowledgement. Sau khi transaction kết thúc, giá trị LOCAL được khôi phục.

### 11.2. Chỉ áp dụng cho dữ liệu có thể tái tạo

Các ứng dụng có thể cân nhắc async commit cho:

- Telemetry hoặc metrics có thể mất một lượng nhỏ dữ liệu gần nhất.
- Cache metadata có thể tái tạo.
- Staging rows có nguồn dữ liệu gốc bên ngoài.
- Dữ liệu phân tích tạm thời không phải nguồn sự thật.

Không áp dụng cho:

- Số dư tài khoản.
- Ledger/financial transactions.
- Thanh toán đã xác nhận.
- Đơn hàng đã cam kết với khách hàng.
- State machine hoặc workflow mà ACK kích hoạt hành động không thể đảo ngược.

Danh sách trên là ví dụ; quyết định dựa vào hậu quả nghiệp vụ nếu transaction đã được ACK nhưng biến mất sau crash.

### 11.3. SET LOCAL phải nằm trong transaction

Không viết:

```sql
SET LOCAL synchronous_commit = off;
INSERT INTO telemetry.events ...;
```

trong autocommit và kỳ vọng setting áp dụng cho INSERT tiếp theo. Hãy dùng `BEGIN` rõ ràng.

### 11.4. Session-level SET

```sql
SET synchronous_commit = off;
```

đặt giá trị cho session cho tới khi đổi/reset hoặc session kết thúc. Nếu dùng connection pool, giá trị có thể tồn tại trên physical connection và ảnh hưởng request tiếp theo nếu không được reset.

### 11.5. ALTER ROLE/ALTER DATABASE

Có thể đặt default:

```sql
ALTER ROLE telemetry_writer
SET synchronous_commit = off;
```

hoặc:

```sql
ALTER DATABASE telemetry_db
SET synchronous_commit = off;
```

Đây là cấu hình mặc định cho sessions mới phù hợp với phạm vi; không phải lệnh sửa mọi session đang mở. Hãy đánh giá role membership, database overrides và connection pools trước khi áp dụng.

### 11.6. Transaction quan trọng trong role async mặc định

Nếu một role/database mặc định dùng `off` cho telemetry nhưng có transaction quan trọng, có thể đặt lại trong transaction:

```sql
BEGIN;

SET LOCAL synchronous_commit = on;

INSERT INTO business.critical_events(event_id, payload)
VALUES (9001, '{"kind":"payment_confirmed"}');

COMMIT;
```

Đừng dựa vào convention của application mà không kiểm tra giá trị thực sự tại transaction.

### 11.7. Không trộn durability policy trong một business unit

Nếu một nghiệp vụ gồm nhiều bảng và nhiều transaction, cần quyết định durability ở cấp đơn vị nghiệp vụ. Nếu một phần dùng async commit nhưng phần khác dùng durable commit, crash có thể để lại trạng thái mà application không mong đợi.

---

## 12. Failure scenarios: transaction nào có thể mất?

### 12.1. fsync=on, synchronous_commit=on, không có sync standby

1. Transaction ghi WAL.
2. PostgreSQL flush WAL local.
3. Server trả COMMIT success.
4. Máy chủ crash.
5. Recovery replay WAL đã flush.

Theo giả định storage tuân thủ flush, transaction đã ACK được bảo toàn trên primary.

### 12.2. fsync=on, synchronous_commit=off

1. Transaction ghi WAL.
2. PostgreSQL trả COMMIT success trước khi WAL của transaction được flush.
3. Máy chủ mất điện trước lần flush tiếp theo.
4. Một số transaction mới được ACK có thể biến mất sau recovery.
5. Database vẫn được phục hồi về trạng thái nhất quán theo WAL còn bền vững.

Đây là **asynchronous commit**: cho phép mất gần đây nhưng không có nghĩa PostgreSQL cố tình ghi nửa transaction.

### 12.3. fsync=off, synchronous_commit=on

1. Backend ghi WAL qua OS.
2. Server có thể trả COMMIT mà không có bảo đảm flush thực sự.
3. OS crash/power loss có thể làm mất hoặc không nhất quán file.
4. Data files/WAL có thể bị corruption; recovery có thể không đủ để khôi phục.

`synchronous_commit=on` không thể bù cho `fsync=off`.

### 12.4. Synchronous replication với on

1. Primary tạo WAL và gửi cho synchronous standby.
2. Primary flush WAL local.
3. Standby nhận và flush WAL theo yêu cầu.
4. Primary nhận acknowledgement.
5. COMMIT được trả cho client.

Nếu primary hỏng sau ACK, standby đã xác nhận có WAL tới transaction đó, giúp failover giảm nguy cơ mất transaction được xác nhận. Thời điểm promote và quy trình failover vẫn phải bảo đảm chọn đúng standby đã đáp ứng policy.

### 12.5. remote_write

Standby đã ghi WAL tới OS nhưng chưa chắc flush durable. Nếu standby cũng mất điện trước khi dữ liệu xuống storage, transaction có thể không còn trên standby dù đã ACK ở primary.

### 12.6. remote_apply

Standby đã replay WAL tới transaction. Điều này cho phép đọc transaction ở standby theo semantics tương ứng, nhưng không thay thế backup hoặc bảo vệ khỏi các lỗi logic được replicate (ví dụ người dùng vô tình DELETE dữ liệu).

### 12.7. Asynchronous replica và failover

Với async replication, primary có thể ACK transaction trước khi standby nhận WAL. Nếu primary mất hoàn toàn và standby được promote, transaction đã ACK nhưng chưa replicate có thể mất.

`synchronous_commit=on` trên primary **không tự biến asynchronous replication thành synchronous replication**.

---

## 13. Durability, availability và RPO/RTO

### 13.1. RPO

Recovery Point Objective (RPO) là mức dữ liệu tối đa tổ chức chấp nhận mất khi xảy ra sự cố.

Ví dụ:

- RPO gần 0 cho transaction đã xác nhận: cần sync replication/standby và storage guarantees thích hợp theo failure model.
- RPO vài giây: asynchronous replication hoặc async commit có thể được cân nhắc, nếu business chấp nhận.
- RPO lớn hơn: backup định kỳ/archiving có thể phù hợp cho một số dữ liệu tái tạo.

### 13.2. RTO

Recovery Time Objective (RTO) là thời gian mục tiêu để dịch vụ phục hồi. Checkpoint, WAL volume, backup/restore speed và failover orchestration ảnh hưởng RTO.

### 13.3. Độ bền local khác độ bền failover

`fsync=on` và `synchronous_commit=on` không có synchronous standby có thể bảo vệ transaction khỏi primary crash trên cùng storage, nhưng không bảo đảm transaction tồn tại nếu toàn bộ primary storage bị mất và failover sang replica asynchronous.

### 13.4. Availability tradeoff

Synchronous replication có thể chặn COMMIT nếu không có synchronous standby đáp ứng. Điều đó làm tăng durability của acknowledged transactions trong topology được thiết kế, nhưng làm write availability phụ thuộc replica/network.

### 13.5. Backup vẫn cần thiết

Replication sao chép cả thao tác sai logic và nhiều dạng corruption ở mức database/application. Backup độc lập, WAL archiving, kiểm thử restore và retention giúp khôi phục khỏi:

- Xóa nhầm dữ liệu.
- Ransomware hoặc mất credentials.
- Hỏng cluster/storage.
- Lỗi migration.
- Corruption đã được replicate.

---

## 14. synchronous_commit và synchronous_standby_names: ví dụ cấu hình

### 14.1. Kiểm tra standby hiện tại

Trên primary:

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
```

Nếu không có rows, hiện không có WAL sender connections tương ứng trong view. Điều này không tự chứng minh replication đã được cấu hình đúng hay sai; kiểm tra thêm server/standby logs và cấu hình.

### 14.2. Kiểm tra cấu hình synchronous standby

```sql
SHOW synchronous_standby_names;
SHOW synchronous_commit;
SHOW fsync;
```

### 14.3. FIRST 1

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
```

Primary chờ một standby phù hợp được chọn theo priority. Cần xác minh `application_name` mà standby gửi lên khớp tên trong cấu hình.

### 14.4. ANY quorum

```conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

Primary chờ hai acknowledgements từ nhóm quorum. Quorum có thể cải thiện tính linh hoạt so với một standby cố định, nhưng vẫn cần đủ số standby đáp ứng.

### 14.5. synchronous_commit per transaction

Ngay cả khi synchronous standbys đã cấu hình, transaction dùng:

```sql
SET LOCAL synchronous_commit = local;
```

chỉ chờ local flush, bỏ chờ remote. Transaction khác giữ `on` sẽ chờ theo synchronous replication policy.

### 14.6. Cẩn thận khi thay đổi cấu hình replication

Thay `synchronous_standby_names` có thể thay đổi standby nào cần acknowledgement và ảnh hưởng availability/commit latency. Thực hiện theo quy trình vận hành, kiểm tra pg_stat_replication, log và failover policy. Không chỉnh trên production chỉ để “hết query treo” mà chưa hiểu lý do chờ SyncRep.

---

## 15. Checkpoint và durability: những tham số thường bị gán nhầm

### 15.1. checkpoint_timeout

Giới hạn khoảng thời gian tối đa giữa các checkpoint theo lịch. Checkpoint cũng có thể được yêu cầu bởi WAL volume hoặc các điều kiện khác.

### 15.2. max_wal_size

Ngưỡng mềm liên quan lượng WAL trước khi checkpoint được yêu cầu. Nó không phải “dung lượng WAL tối đa tuyệt đối”; replication slots và archive backlog có thể giữ WAL nhiều hơn.

### 15.3. checkpoint_completion_target

Điều khiển mục tiêu phân bố checkpoint writes trong khoảng thời gian giữa checkpoints, giúp tránh I/O burst ở cuối checkpoint. Giá trị quá thấp có thể dồn write; quá cao cần đánh giá khoảng cách giữa các checkpoints và storage.

### 15.4. checkpoint_flush_after

Có thể giúp hệ điều hành bắt đầu flush dirty pages theo đợt thay vì giữ quá nhiều dirty data. Tác động phụ thuộc OS/filesystem và workload.

### 15.5. Không dùng checkpoint để thay synchronous_commit

Tăng tần suất checkpoint không làm `synchronous_commit=off` trở thành durable-at-ack. Giảm checkpoint frequency cũng không làm `synchronous_commit=on` mất local WAL flush guarantee khi fsync và storage hoạt động đúng.

Hai cơ chế có mục đích khác nhau:

- `synchronous_commit`: thời điểm ACK transaction.
- Checkpoint: dirty data pages và redo/recovery boundary.

---

## 16. WAL writer, commit_delay và performance

### 16.1. wal_writer_delay

`wal_writer_delay` điều khiển chu kỳ WAL writer thức dậy để ghi/flush WAL theo lịch. Nó có liên quan đến độ trễ an toàn của async commit, nhưng không phải cam kết latency cố định.

### 16.2. wal_writer_flush_after

Điều khiển lượng WAL được ghi trước khi WAL writer yêu cầu flush theo ngưỡng. Giá trị này ảnh hưởng behavior I/O và cần benchmark trong môi trường thật.

### 16.3. commit_delay

`commit_delay` có thể khiến backend chờ ngắn trước khi flush WAL để tăng cơ hội group commit. Đây là microseconds; một giá trị không phù hợp có thể chỉ làm COMMIT chậm hơn.

### 16.4. commit_siblings

`commit_siblings` xác định số transaction đồng thời tối thiểu để commit_delay được áp dụng trong điều kiện phù hợp.

### 16.5. Không tối ưu riêng một chỉ số

Đo:

- Commit p50/p95/p99.
- WAL sync count/time.
- WAL write count/time.
- WAL bytes per transaction.
- Replication flush/replay lag.
- Checkpoint duration và buffers written.
- Storage latency/queue depth.
- Transaction throughput và error rate.

Một cấu hình giảm median latency nhưng tăng tail latency hoặc làm failover mất dữ liệu có thể là cấu hình tệ hơn.

---

## 17. Theo dõi WAL và flush

### 17.1. pg_stat_wal

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    wal_write,
    wal_sync,
    wal_write_time,
    wal_sync_time,
    stats_reset
FROM pg_stat_wal;
```

View này cung cấp thống kê WAL ở mức instance. Nếu `track_wal_io_timing` tắt hoặc môi trường không hỗ trợ timing, các trường thời gian có thể không phản ánh đầy đủ latency.

### 17.2. Timing counters

`wal_write_time` và `wal_sync_time` tích lũy thời gian theo cách được thống kê khi cấu hình tracking phù hợp. Muốn tính trung bình, hãy lấy delta giữa hai lần snapshot trong một khoảng thời gian, không chỉ nhìn giá trị tuyệt đối kể từ stats reset.

### 17.3. pg_stat_replication

```sql
SELECT
    application_name,
    state,
    sync_state,
    pg_wal_lsn_diff(pg_current_wal_lsn(), write_lsn)
        AS bytes_not_written_on_standby,
    pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn)
        AS bytes_not_flushed_on_standby,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)
        AS bytes_not_replayed_on_standby
FROM pg_stat_replication;
```

Các phép trừ trên là ước lượng khoảng cách LSN so với WAL current trên primary. Trong workload đang ghi liên tục, giá trị thay đổi ngay trong lúc query; cần diễn giải cùng thời điểm và state.

### 17.4. Wait events

Có thể quan sát các sessions đang chờ:

```sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query_start,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE wait_event IN ('WALWrite', 'WALSync', 'SyncRep')
ORDER BY query_start;
```

Ý nghĩa tổng quát:

- `WALWrite`: chờ thao tác ghi WAL.
- `WALSync`: chờ WAL sync/flush.
- `SyncRep`: chờ synchronous replication acknowledgement.

Wait event names và chi tiết quan sát có thể thay đổi theo PostgreSQL version. Kiểm tra documentation của version đang chạy.

### 17.5. Checkpoint statistics

Thông tin checkpoint được hiển thị qua các statistics views; tên/cấu trúc view có khác biệt giữa các major versions. Trên những version mới, kiểm tra `pg_stat_checkpointer`; trên các version cũ hơn, một số checkpoint counters nằm trong `pg_stat_bgwriter`.

Không copy một query monitoring từ version khác mà chưa kiểm tra schema của view.

### 17.6. Không kết luận từ một snapshot

Một lần đọc `wal_sync_time` hoặc `flush_lag` không đủ kết luận performance. Hãy:

1. Lấy baseline trước thay đổi.
2. Đo delta trong cùng workload.
3. Tách primary flush latency và standby flush/replay latency.
4. Đối chiếu commit p95/p99 với storage/network metrics.
5. Ghi lại config và stats reset time.

---

## 18. Thử nghiệm durability có kiểm soát

### 18.1. Tạo bảng lab

```sql
CREATE SCHEMA durability_lab;

CREATE TABLE durability_lab.commit_probe (
    probe_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

### 18.2. Xem cấu hình hiện tại

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_settings
WHERE name IN (
    'fsync',
    'synchronous_commit',
    'wal_sync_method',
    'full_page_writes',
    'wal_writer_delay',
    'wal_writer_flush_after',
    'checkpoint_timeout',
    'max_wal_size',
    'checkpoint_completion_target'
)
ORDER BY name;
```

`pg_settings` cho biết setting, context và nguồn cấu hình hiện hành. Không chỉnh các giá trị chỉ vì một môi trường lab có kết quả khác.

### 18.3. Transaction với synchronous_commit on

```sql
BEGIN;

SET LOCAL synchronous_commit = on;

INSERT INTO durability_lab.commit_probe(label)
VALUES ('durable-policy-example');

COMMIT;
```

Với `fsync=on` và storage thực hiện đúng flush, COMMIT chờ local WAL flush. Nếu synchronous replication được cấu hình, nó cũng chờ synchronous standby theo policy.

### 18.4. Transaction với synchronous_commit off

```sql
BEGIN;

SET LOCAL synchronous_commit = off;

INSERT INTO durability_lab.commit_probe(label)
VALUES ('async-commit-example');

COMMIT;
```

Transaction có thể được ACK trước khi WAL của nó được flush. Không cố tình tắt máy để thử trên database chứa dữ liệu quan trọng; chỉ thực hiện failure injection trong disposable VM/lab có bản sao và kế hoạch phục hồi.

### 18.5. Đọc lại dữ liệu

```sql
SELECT probe_id, label, created_at
FROM durability_lab.commit_probe
ORDER BY probe_id;
```

Kết quả đọc ngay sau commit chứng minh transaction đang hiện diện trong database hiện tại; nó không chứng minh transaction sẽ tồn tại sau mọi failure modes.

### 18.6. Không thể chứng minh durability chỉ bằng SELECT

Một query đọc lại ngay sau COMMIT không kiểm tra được:

- WAL đã flush thật tới storage chưa.
- Controller có volatile cache không được bảo vệ không.
- Async replica đã nhận WAL chưa.
- Failover sẽ chọn standby nào.
- Backup restore có hoạt động không.

Durability là thuộc tính của toàn bộ stack và failure model.

---

## 19. Kiểm thử storage và hệ thống

### 19.1. pg_test_fsync

`pg_test_fsync` đo các phương thức sync trên một file test. Dùng nó để so sánh chi phí tương đối trên filesystem cụ thể.

### 19.2. Benchmark workload thật

Một benchmark cần gần với:

- Kích thước WAL record thực tế.
- Số transactions/second.
- Tỷ lệ commit/rollback.
- Số clients đồng thời.
- Sync replication topology.
- Storage latency và cache behavior.

Một microbenchmark chỉ ghi một file không đại diện đầy đủ cho production.

### 19.3. Test crash recovery

Test cần phân biệt:

- Backend process termination.
- PostgreSQL server shutdown không sạch.
- OS crash/VM reset.
- Storage fault/power loss simulation.
- Primary failover sang standby.

Không dùng `kill -9` một backend để tuyên bố đã kiểm thử mất điện; backend crash không tái hiện toàn bộ OS/storage failure.

### 19.4. Test restore

Backup chỉ đáng tin khi đã thử restore:

- Khôi phục base backup.
- Replay WAL archive tới target point.
- Kiểm tra consistency và ứng dụng đọc dữ liệu.
- Đo thời gian phục hồi.

### 19.5. Test failover

Với synchronous replication:

- Xác minh standby được chọn là synchronous.
- Commit marker trên primary.
- Chờ acknowledgement thành công.
- Mô phỏng primary failure trong môi trường lab.
- Promote standby theo quy trình.
- Kiểm tra marker và thứ tự transactions.

Không suy từ cấu hình `synchronous_standby_names` rằng failover tự động chọn đúng node; failover manager và operator policy cũng là một phần của hệ thống.

---

## 20. Vận hành fsync và thay đổi cấu hình

### 20.1. Kiểm tra trước khi thay

Ghi nhận:

- `SHOW fsync`.
- `SHOW synchronous_commit`.
- `SHOW wal_sync_method`.
- `SHOW synchronous_standby_names`.
- `SHOW full_page_writes`.
- PostgreSQL major version.
- Storage class, filesystem và controller semantics.
- Backup/WAL archive status.
- Replication topology và failover policy.

### 20.2. Không dùng SET LOCAL để tắt fsync

`fsync` là cấu hình server-level, không phải transaction-level toggle giống `synchronous_commit`. Không thể an toàn bật/tắt fsync cho từng request như một cách tối ưu.

### 20.3. Thay synchronous_commit theo workload

Nếu cần async commit cho một workload cụ thể, ưu tiên transaction-level `SET LOCAL` sau khi đã xác định dữ liệu có thể mất. Hạn chế setting ở cấp role/database để tránh áp dụng ngoài dự kiến.

### 20.4. Khi thay đổi synchronous_standby_names

Đây là thay đổi topology durability. Cần xác minh:

- Tên application_name trên standby.
- Đủ số standbys theo FIRST/ANY.
- Replication state và lag.
- Behavior khi standby mất kết nối.
- Quy trình failover và promote.

### 20.5. Khi thay wal_sync_method

Chỉ thay sau khi đo `pg_test_fsync` và benchmark workload thực tế. Giữ cấu hình mặc định nếu không có bằng chứng rõ ràng rằng phương thức khác phù hợp hơn.

---

## 21. Các tình huống ứng dụng cần quyết định durability

### 21.1. Payment authorization

Một hệ thống đã trả “thanh toán thành công” cho khách hàng thường cần acknowledged transaction được bảo toàn. `synchronous_commit=off` có thể khiến application trả thành công rồi transaction biến mất sau crash.

Thiết kế phải xác định:

- Khi nào gửi response thành công.
- Khi nào gọi cổng thanh toán/đối tác.
- Có idempotency key không.
- Nếu primary crash sau commit thì recovery/failover xử lý ra sao.
- Replication có synchronous hay không.

### 21.2. Telemetry và metrics

Một vài điểm metrics gần nhất có thể mất mà không gây sai lệch nghiệp vụ. Đây là trường hợp có thể cân nhắc async commit theo transaction, với điều kiện downstream chấp nhận mất dữ liệu và không dùng metrics làm nguồn sự thật.

### 21.3. Job queue

Nếu một transaction insert job rồi ứng dụng ACK enqueue cho caller, mất job sau crash có thể làm công việc không bao giờ chạy. Cần chọn durability tương ứng hoặc có cơ chế producer retry/reconciliation.

### 21.4. Cache metadata

Nếu cache có thể được dựng lại từ source of truth, async commit có thể phù hợp. Nhưng nếu cache chứa state duy nhất hoặc quyết định quyền truy cập, nó không còn là cache có thể tái tạo đơn giản.

### 21.5. Audit log

Audit log có thể là bằng chứng tuân thủ hoặc điều tra. Không tự xếp nó vào dữ liệu “có thể mất” chỉ vì là log. Xác định retention, regulatory needs và failure contract trước khi chọn off.

---

## 22. Các hiểu lầm thường gặp

**1. “COMMIT success nghĩa mọi data pages đã ghi xuống data files.”** Sai. WAL flush có thể đủ cho commit durability; checkpoint ghi data pages sau.

**2. “Checkpoint là lúc transaction được durable.”** Sai. Checkpoint và commit acknowledgement là hai cơ chế khác nhau.

**3. “fsync=on gọi fsync một lần cho mỗi transaction.”** Không nhất thiết. Group commit có thể gom nhiều transactions vào một flush.

**4. “synchronous_commit=on tự bảo đảm failover không mất dữ liệu.”** Không nếu không có synchronous standby phù hợp; nó vẫn có thể chỉ bảo đảm local flush.

**5. “fsync=off chỉ mất vài transaction mới nhất.”** Sai. Có thể gây corruption và cần restore cluster.

**6. “synchronous_commit=on bù được fsync=off.”** Sai. Không có yêu cầu flush đúng thì chờ commit không tạo durability.

**7. “synchronous_commit=off làm transaction không atomic.”** Không. Nó làm yếu thời điểm durability acknowledgement; transaction vẫn được xử lý theo atomic transaction semantics.

**8. “off có thể làm mất mọi dữ liệu trong database.”** Không phải ý nghĩa thông thường của async commit; rủi ro là các transactions gần đây chưa được flush. Database vẫn phải recovery nhất quán, giả định fsync vẫn bật.

**9. “local giống on.”** Không khi có synchronous replication; local không chờ remote standby.

**10. “remote_write nghĩa standby đã flush durable.”** Không. Nó chờ ghi tới OS, chưa chắc flush tới storage bền vững.

**11. “on nghĩa standby đã replay.”** Không. On chờ standby flush; remote_apply mới chờ replay.

**12. “remote_apply làm mọi replica đều đọc được transaction.”** Không. Nó liên quan synchronous standby được chọn; async replica khác có thể lag.

**13. “Bật synchronous_standby_names là mọi commit tự chờ replica.”** Còn phụ thuộc synchronous_commit value của transaction.

**14. “Không có synchronous standby nhưng đặt remote_apply thì PostgreSQL tự tìm replica.”** Không. Cần cấu hình synchronous replication và standby tương ứng.

**15. “Synchronous replication luôn tăng availability.”** Không. Nếu không có standby đáp ứng, commit có thể bị chặn.

**16. “Async replication cộng synchronous_commit=on cho RPO=0.”** Không. On có thể chỉ chờ local WAL flush nếu không có synchronous standby.

**17. “remote_write an toàn trước mất điện của standby.”** Không nhất thiết; OS cache volatile có thể mất.

**18. “remote_apply thay backup.”** Không. Nó cũng replicate lỗi logic và xóa nhầm.

**19. “full_page_writes thay fsync.”** Không.

**20. “Data checksums tự sửa corruption.”** Không; chủ yếu phát hiện hỏng page.

**21. “wal_sync_method nào có tên fsync là tốt nhất.”** Không. Phụ thuộc OS/filesystem/storage.

**22. “pg_test_fsync chứng minh storage không thể mất dữ liệu.”** Không. Nó đo chi phí sync, không chứng nhận hardware durability.

**23. “Tăng checkpoint frequency làm commit an toàn hơn.”** Không trực tiếp; commit durability dựa vào WAL flush policy.

**24. “Giảm max_wal_size luôn giảm write latency.”** Không; checkpoint frequency và write pressure có thể thay đổi theo hướng bất lợi.

**25. “WAL writer delay là thời gian mất dữ liệu chính xác.”** Không; nó là một phần cơ chế, workload và các lần flush khác có thể làm thời gian ngắn hơn.

**26. “SET LOCAL synchronous_commit ngoài transaction áp dụng cho statement sau.”** Không.

**27. “ALTER ROLE SET thay đổi session đang mở ngay lập tức.”** Không; đó là default cho sessions mới theo precedence cấu hình.

**28. “Một COMMIT ACK đã local durable thì chắc chắn có trên standby async.”** Không.

**29. “Một standby có trong pg_stat_replication chắc chắn đang là synchronous.”** Không; xem sync_state và policy.

**30. “sync_state=sync bảo đảm failover manager luôn promote đúng node.”** Không; failover orchestration cần kiểm chứng riêng.

**31. “Kill backend là test mất điện.”** Không. OS/storage failure khác backend process failure.

**32. “Chỉ cần có backup là fsync có thể tắt.”** Không. Backup không ngăn corruption xảy ra trong cluster đang hoạt động và không bảo đảm phục hồi nhanh.

---

## 23. Bài tập thực hành và đáp án

### Bài 1 — Phân biệt WAL và data pages

**Câu hỏi:** Vì sao PostgreSQL có thể trả COMMIT trước khi data page được ghi xuống data file?

**Đáp án:** Nếu WAL tới commit record đã được flush theo durability policy, crash recovery có thể replay WAL để phục hồi data page sau crash.

### Bài 2 — Checkpoint

**Câu hỏi:** Checkpoint có phải điều kiện cho từng COMMIT được ACK không?

**Đáp án:** Không. Checkpoint ghi dirty data pages và đặt redo point; commit durability thông thường dựa trên WAL flush.

### Bài 3 — fsync

**Câu hỏi:** fsync=on bảo vệ điều gì?

**Đáp án:** Yêu cầu hệ điều hành đồng bộ file changes cần thiết tới storage để hỗ trợ crash recovery theo durability assumptions.

### Bài 4 — fsync=off

**Câu hỏi:** Vì sao fsync=off có thể gây corruption thay vì chỉ mất vài commits?

**Đáp án:** WAL/data files có thể không được đồng bộ theo thứ tự/bảo đảm cần thiết; sau OS crash hoặc power loss, cluster có thể không nhất quán và không phục hồi được bằng WAL.

### Bài 5 — synchronous_commit=off

**Câu hỏi:** Điều gì có thể xảy ra sau khi transaction off được ACK rồi máy mất điện ngay?

**Đáp án:** Một số transactions gần đây chưa flush có thể mất sau recovery, dù database vẫn được phục hồi nhất quán nếu fsync và storage hoạt động đúng.

### Bài 6 — local

**Câu hỏi:** local chờ điều gì?

**Đáp án:** Chờ local WAL flush trên primary, không chờ synchronous standby.

### Bài 7 — remote_write

**Câu hỏi:** remote_write có nghĩa standby đã durable trên storage?

**Đáp án:** Không. Nó chờ standby ghi WAL tới OS; chưa chắc flush tới durable media.

### Bài 8 — on

**Câu hỏi:** Với synchronous standby được cấu hình, on chờ điều gì?

**Đáp án:** Local WAL flush và acknowledgement flush từ synchronous standby theo replication policy.

### Bài 9 — remote_apply

**Câu hỏi:** remote_apply khác on thế nào?

**Đáp án:** Nó chờ standby replay/apply WAL, không chỉ flush.

### Bài 10 — Không có standby

**Câu hỏi:** synchronous_commit=on có tự tạo remote durability khi không có synchronous standby?

**Đáp án:** Không. Nó chờ local flush.

### Bài 11 — sync standby mất kết nối

**Câu hỏi:** Nếu policy cần một synchronous standby nhưng không có standby đáp ứng, commit có thể ra sao?

**Đáp án:** Transaction chờ tại commit cho tới khi standby phù hợp trở lại hoặc policy/config thay đổi.

### Bài 12 — Quorum

**Yêu cầu:** Viết cấu hình chờ hai standby trong ba standby.

```conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

### Bài 13 — FIRST

**Yêu cầu:** Viết cấu hình chọn một standby theo priority.

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
```

### Bài 14 — SET LOCAL

**Yêu cầu:** Cho một transaction telemetry dùng async commit.

```sql
BEGIN;
SET LOCAL synchronous_commit = off;
INSERT INTO telemetry.events(event_type) VALUES ('view');
COMMIT;
```

### Bài 15 — SET LOCAL ngoài transaction

**Câu hỏi:** Vì sao phải có BEGIN?

**Đáp án:** SET LOCAL có transaction scope; nếu statement chạy autocommit riêng, scope kết thúc ngay sau statement đó.

### Bài 16 — full_page_writes

**Câu hỏi:** full_page_writes bảo vệ điều gì?

**Đáp án:** Hỗ trợ recovery torn data pages bằng full-page image trong WAL ở lần sửa page đầu tiên sau checkpoint.

### Bài 17 — full_page_writes và fsync

**Câu hỏi:** Có thể tắt fsync nếu full_page_writes=on không?

**Đáp án:** Không. Hai cơ chế có vai trò khác nhau.

### Bài 18 — Group commit

**Câu hỏi:** Vì sao nhiều commits có thể dùng chung một WAL flush?

**Đáp án:** PostgreSQL flush WAL tới một LSN bao gồm commit records của nhiều transactions; các backend có thể được đánh thức cùng lúc.

### Bài 19 — wal_sync_method

**Câu hỏi:** Công cụ nào giúp đo các phương thức WAL sync trên storage?

**Đáp án:** pg_test_fsync, sau đó cần benchmark workload thực tế.

### Bài 20 — LSN

**Yêu cầu:** Xem current và flush LSN.

```sql
SELECT pg_current_wal_lsn(), pg_current_wal_flush_lsn();
```

### Bài 21 — pg_stat_wal

**Yêu cầu:** Xem WAL writes/syncs.

```sql
SELECT wal_write, wal_sync, wal_write_time, wal_sync_time
FROM pg_stat_wal;
```

### Bài 22 — Replication lag

**Yêu cầu:** Xem sync state và replay lag.

```sql
SELECT application_name, state, sync_state, replay_lag
FROM pg_stat_replication;
```

### Bài 23 — Wait events

**Câu hỏi:** wait event SyncRep thường gợi ý gì?

**Đáp án:** Backend đang chờ synchronous replication acknowledgement.

### Bài 24 — Checkpoint parameters

**Câu hỏi:** max_wal_size là giới hạn cứng tuyệt đối của WAL directory không?

**Đáp án:** Không. Replication slots/archive backlog và những điều kiện khác có thể giữ WAL nhiều hơn.

### Bài 25 — RPO

**Câu hỏi:** RPO đo gì?

**Đáp án:** Mức dữ liệu tối đa tổ chức chấp nhận mất trong một sự cố.

### Bài 26 — RTO

**Câu hỏi:** RTO đo gì?

**Đáp án:** Thời gian mục tiêu để dịch vụ/database phục hồi.

### Bài 27 — Async replica

**Câu hỏi:** synchronous_commit=on trên primary có bảo đảm async standby có transaction đã ACK không?

**Đáp án:** Không. On chỉ chờ remote nếu synchronous replication được cấu hình cho standby tương ứng.

### Bài 28 — remote_apply và read-after-write

**Câu hỏi:** Vì sao remote_apply hữu ích khi đọc từ synchronous standby?

**Đáp án:** Vì commit chỉ được ACK sau khi standby đã replay transaction theo policy, nên thay đổi đã được áp dụng tại standby đó.

### Bài 29 — Backup

**Câu hỏi:** Synchronous replication có thay backup không?

**Đáp án:** Không. Replication có thể sao chép lỗi logic/xóa nhầm; cần backup và restore test.

### Bài 30 — Failure test

**Câu hỏi:** Kill PostgreSQL backend có chứng minh durability trước power loss không?

**Đáp án:** Không. Backend process failure không mô phỏng OS crash, controller cache hoặc mất điện.

---

## 24. Checklist chọn và vận hành durability policy

### Yêu cầu nghiệp vụ

1. Định nghĩa transaction nào không được mất sau khi ACK.
2. Định nghĩa RPO/RTO cho primary failure và site failure.
3. Phân loại dữ liệu source-of-truth, dữ liệu tái tạo và telemetry.
4. Xác định khi nào application gửi response hoặc gọi hệ thống ngoài.
5. Xác định semantics idempotency/retry nếu commit outcome không rõ.

### PostgreSQL

6. Giữ `fsync=on` cho database cần bảo toàn dữ liệu.
7. Kiểm tra `synchronous_commit` thực tế ở session/transaction.
8. Không nhầm local durability với synchronous replication durability.
9. Hiểu `remote_write`, `on` và `remote_apply` khác nhau.
10. Giữ `full_page_writes` theo khuyến nghị mặc định trừ khi có lý do kỹ thuật rõ.
11. Hiểu `wal_sync_method` và đo trước khi thay.
12. Hiểu checkpoint không phải điều kiện ACK từng commit.

### Replication và storage

13. Xác nhận `synchronous_standby_names` và application_name.
14. Theo dõi `sync_state`, write/flush/replay LSN.
15. Biết behavior khi standby không sẵn sàng.
16. Xác minh storage cache/flush semantics.
17. Kiểm tra filesystem, controller, hypervisor và cloud storage.
18. Có backup/WAL archive độc lập.
19. Thực hiện restore và failover drills.

### Performance và monitoring

20. Theo dõi `pg_stat_wal`.
21. Theo dõi replication lag và SyncRep waits.
22. Theo dõi checkpoint stats theo PostgreSQL version.
23. Đo commit p95/p99, không chỉ average.
24. Benchmark với workload và concurrency thực tế.
25. Chỉ chỉnh group commit/WAL writer sau khi có baseline.

### Async commit

26. Chỉ dùng `synchronous_commit=off` cho dữ liệu chấp nhận mất gần đây.
27. Ưu tiên `SET LOCAL` theo transaction.
28. Không đặt default role/database thành off nếu chưa đánh giá mọi callers.
29. Kiểm tra business transaction không trộn dữ liệu quan trọng và dữ liệu async theo cách gây bất nhất.
30. Ghi lại policy, người phê duyệt và failure contract.

---

## 25. Tổng kết

Durability của PostgreSQL dựa trên WAL và cơ chế đồng bộ file. **WAL flush** cho phép PostgreSQL xác nhận commit trước khi data pages được ghi xuống data files; **checkpoint** ghi dirty pages và thiết lập điểm phục hồi. Hai việc này có quan hệ chặt chẽ nhưng không phải cùng một sự kiện.

Những điểm cần nhớ:

- `fsync=on` là nền tảng để yêu cầu hệ điều hành đồng bộ WAL/data files theo durability protocol. Tắt nó có thể gây corruption sau OS crash hoặc power loss.
- `synchronous_commit` quyết định thời điểm ACK: `off` không chờ local flush; `local` chờ local flush; `remote_write` chờ standby ghi tới OS; `on` chờ standby flush nếu sync replication được cấu hình; `remote_apply` chờ standby replay.
- `synchronous_commit=on` không tự tạo HA durability nếu không có synchronous standby.
- Synchronous replication cải thiện bảo toàn transaction khi failover theo policy, nhưng có thể làm commit bị chặn khi không có standby đáp ứng.
- Group commit giúp nhiều transactions chia sẻ một WAL flush, nên durability không đồng nghĩa một fsync syscall cho mỗi COMMIT.
- `full_page_writes` hỗ trợ phục hồi torn pages; nó không thay thế fsync.
- Async commit phù hợp với dữ liệu có thể tái tạo/mất gần đây theo chấp nhận nghiệp vụ; nên giới hạn bằng `SET LOCAL`.
- Backup, WAL archive, restore tests, storage guarantees và failover drills vẫn cần thiết.

**Câu hỏi tự kiểm tra:** Nếu một API đã trả “thanh toán thành công” sau COMMIT, điều gì phải đúng để transaction không bị mất khi primary crash? Bạn cần kiểm tra local WAL flush, `fsync`, synchronous standby policy, trạng thái flush/replay của standby và failure behavior của storage. Chỉ nhìn thấy COMMIT success hoặc một checkpoint gần đây không đủ chứng minh toàn bộ cam kết đó.

### Tài liệu PostgreSQL chính thức

- [WAL Configuration — fsync, synchronous_commit, wal_sync_method, full_page_writes](https://www.postgresql.org/docs/current/runtime-config-wal.html).
- [WAL Reliability](https://www.postgresql.org/docs/current/wal-reliability.html).
- [WAL Internals](https://www.postgresql.org/docs/current/wal-internals.html).
- [WAL — Write-Ahead Logging](https://www.postgresql.org/docs/current/wal.html).
- [WAL Configuration — Checkpoints](https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-CHECKPOINTS).
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION).
- [Replication Configuration — synchronous_standby_names](https://www.postgresql.org/docs/current/runtime-config-replication.html).
- [Monitoring Statistics — pg_stat_wal and replication views](https://www.postgresql.org/docs/current/monitoring-stats.html).
- [pg_test_fsync](https://www.postgresql.org/docs/current/pgtestfsync.html).
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html).
