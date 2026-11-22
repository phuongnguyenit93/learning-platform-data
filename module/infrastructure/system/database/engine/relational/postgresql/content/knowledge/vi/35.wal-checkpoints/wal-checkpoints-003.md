# Walwriter, ghi xuống đĩa và thời điểm xác nhận commit trong PostgreSQL

PostgreSQL dùng **Write-Ahead Logging (WAL)** để bảo vệ dữ liệu khi hệ thống gặp sự cố. Khi một transaction thay đổi dữ liệu, PostgreSQL ghi mô tả thay đổi vào WAL trước khi các data pages tương ứng được ghi xuống những file bảng chính.

Điều này tạo ra một câu hỏi quan trọng: **Khi ứng dụng gọi COMMIT và nhận phản hồi thành công, dữ liệu đã thực sự an toàn trên thiết bị lưu trữ chưa?**

Câu trả lời phụ thuộc vào cách PostgreSQL ghi và flush WAL, cấu hình `synchronous_commit`, chế độ đồng bộ replication và độ tin cậy của filesystem/storage.

Các thành phần cần phân biệt:

- **WAL buffers**: vùng shared memory giữ WAL records trước khi ghi ra WAL files.
- **Backend process**: tiến trình phục vụ connection, có thể tự ghi/flush WAL khi cần.
- **Walwriter**: background process ghi WAL buffers ra WAL segment files theo lịch và ngưỡng.
- **Operating system cache**: dữ liệu đã được write xuống kernel/filesystem nhưng chưa chắc bền vững qua mất điện.
- **fsync/fdatasync**: yêu cầu hệ điều hành đồng bộ dữ liệu tới thiết bị lưu trữ theo semantics của platform.
- **COMMIT record**: bản ghi WAL đánh dấu transaction commit.
- **Checkpoint**: quá trình ghi dirty data pages và thiết lập điểm phục hồi; không đồng nghĩa với xác nhận commit.

Bài **“Walwriter, ghi xuống đĩa và thời điểm xác nhận commit”**, thuộc chương **WAL và checkpoint** của module **Database Engine Relational PostgreSQL**, giải thích WAL insert/write/flush, vai trò walwriter, synchronous_commit, group commit, checkpoint, synchronous replication và cách quan sát các metrics liên quan.

> **Điểm cần nhớ:** PostgreSQL có thể xác nhận một transaction commit trước khi data pages được ghi về heap files, vì WAL cho phép crash recovery. Nhưng với cấu hình commit đồng bộ thông thường, WAL chứa commit record phải được flush theo yêu cầu trước khi server trả thành công cho client. “Đã write” và “đã flush bền vững” là hai trạng thái khác nhau.

---

## 1. Vì sao PostgreSQL cần WAL?

Nếu mỗi UPDATE phải ghi ngay mọi thay đổi vào đúng vị trí của heap, index và các structures khác, một transaction sẽ cần nhiều thao tác I/O ngẫu nhiên. Crash giữa chừng cũng có thể để lại dữ liệu ở trạng thái không nhất quán.

WAL thay đổi cách làm:

1. PostgreSQL tạo WAL records mô tả thay đổi.
2. Các records được đưa vào WAL buffers trong shared memory.
3. WAL được ghi ra các WAL segment files.
4. Khi cần durability, WAL được flush tới storage theo cơ chế đồng bộ.
5. Data pages có thể được ghi sau; nếu crash, PostgreSQL redo WAL để phục hồi.

~~~text
Transaction
    |
    v
Thay đổi page trong shared buffers
    |
    v
Tạo WAL records trong WAL buffers
    |
    v
Write WAL ra pg_wal
    |
    v
Flush WAL theo durability policy
    |
    v
COMMIT được xác nhận
    |
    v
Data pages được ghi theo checkpoint/background write
~~~

WAL cho phép database ghi tuần tự vào log và khôi phục các thay đổi đã commit mà chưa được ghi đầy đủ vào data files.

## 2. Write-ahead rule

Nguyên tắc **write-ahead** yêu cầu WAL records mô tả một thay đổi phải được ghi bền vững trước khi data page chứa thay đổi đó được ghi bền vững xuống storage.

~~~text
WAL record: page 42 được sửa
        |
        v
WAL phải durable trước
        |
        v
Data page 42 mới được phép ghi durable
~~~

Nếu data page được ghi trước WAL cần thiết, crash có thể khiến PostgreSQL không có đủ thông tin để phục hồi page đó.

## 3. WAL buffers nằm ở đâu?

PostgreSQL có vùng shared memory gọi là **WAL buffers**, được cấu hình qua `wal_buffers`.

~~~sql
SHOW wal_buffers;
~~~

WAL records được tạo trong quá trình transaction chạy và ghi vào WAL buffers. Chúng chưa nhất thiết đã ra file WAL ngay tại thời điểm SQL statement kết thúc.

Khi buffers cần được giải phóng, backend hoặc walwriter có thể thực hiện việc ghi WAL ra các segment files.

### 3.1. WAL buffers không phải data buffers

| Buffer area | Chứa gì | Được ghi tới |
|---|---|---|
| Shared buffers | Heap/index data pages | Table/index relation files |
| WAL buffers | WAL records | WAL segment files trong pg_wal |

Một page trong shared buffers và một WAL record mô tả thay đổi page đó là hai loại dữ liệu khác nhau.

## 4. WAL segment files

WAL được lưu trong các segment files bên trong thư mục `pg_wal` của data directory.

Tên file thường theo dạng hexadecimal, ví dụ:

~~~text
00000001000000000000000A
00000001000000000000000B
~~~

Kích thước segment mặc định thường là **16 MB**, nhưng có thể được xác định khi initdb bằng lựa chọn phù hợp. Không hard-code kích thước này trong công cụ giám sát.

WAL segment có thể được tạo mới, ghi tiếp, flush, switch sang segment kế tiếp, archive, recycle hoặc xóa khi không còn cần theo các quy tắc retention/replication.

## 5. Ba vị trí WAL: insert, write và flush

PostgreSQL theo dõi nhiều vị trí LSN (Log Sequence Number):

- **Insert LSN**: vị trí WAL mới nhất được tạo/insert vào WAL buffers.
- **Write LSN**: vị trí WAL đã được ghi ra WAL files theo write operation.
- **Flush LSN**: vị trí WAL đã được flush theo durability mechanism.

Thứ tự thông thường:

~~~text
Insert LSN >= Write LSN >= Flush LSN
~~~

Các vị trí có thể bằng nhau khi không còn WAL đang chờ ghi/flush.

### 5.1. Insert không đồng nghĩa write

Một WAL record đã được tạo trong shared memory chưa chắc đã được ghi ra pg_wal.

### 5.2. Write không đồng nghĩa flush

Một write operation có thể đưa bytes vào OS page cache. Dữ liệu vẫn có thể nằm trong cache do kernel quản lý và chưa được xác nhận durable trên storage.

### 5.3. Flush là mốc quan trọng cho durability

Flush yêu cầu hệ điều hành đồng bộ WAL data theo cơ chế fsync/fdatasync hoặc phương pháp tương ứng. Với `fsync=on` và storage thực hiện đúng semantics, đây là mốc PostgreSQL dựa vào để xác nhận WAL bền vững.

## 6. Quan sát các LSN hiện tại

Các function hữu ích:

~~~sql
SELECT
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_lsn() AS write_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
~~~

- `pg_current_wal_insert_lsn()` trả vị trí insert hiện tại.
- `pg_current_wal_lsn()` trả vị trí write hiện tại.
- `pg_current_wal_flush_lsn()` trả vị trí flush hiện tại.

Các function này cho thấy tiến độ WAL tại thời điểm query. Chúng không phải lịch sử commit của từng transaction.

### 6.1. Phiên bản cũ

Trong PostgreSQL cũ, tên function dùng tiền tố `pg_current_xlog_*`. Tên WAL thay thế XLOG trong các phiên bản mới. Dùng function tương ứng với server version thực tế.

## 7. Tính khoảng cách LSN

~~~sql
SELECT pg_wal_lsn_diff(
    pg_current_wal_insert_lsn(),
    pg_current_wal_flush_lsn()
) AS unflushed_wal_bytes;
~~~

`pg_wal_lsn_diff` trả khoảng cách bytes giữa hai LSN.

Đây là ảnh chụp tại thời điểm query. Giá trị có thể thay đổi rất nhanh khi workload đang ghi WAL. Không dùng một mẫu đơn lẻ làm kết luận về latency commit.

## 8. Walwriter là gì?

**Walwriter** là background process của PostgreSQL chuyên ghi WAL buffers ra WAL files theo lịch và ngưỡng cấu hình.

Mục tiêu:

- Giảm số lần backend phải tự ghi WAL buffers.
- Ghi WAL định kỳ ngay cả khi không có transaction commit ngay lúc đó.
- Giảm burst I/O và hỗ trợ group commit.
- Giữ WAL tiến triển đều hơn trong workload.

Walwriter không thay thế hoàn toàn backend WAL writes/flushes. Khi một backend cần WAL durable cho COMMIT và WAL chưa được flush tới vị trí yêu cầu, backend có thể tự thực hiện write/flush hoặc chờ cơ chế đồng bộ phù hợp.

### 8.1. Walwriter không ghi heap data pages

Walwriter làm việc với **WAL**. Các data pages của bảng/index được ghi bởi những cơ chế khác như background writer, checkpointer và backend processes.

Đừng nhầm walwriter với background writer.

## 9. Walwriter và backend cùng tham gia ghi WAL

~~~text
                 WAL buffers
                      |
            +---------+---------+
            |                   |
            v                   v
        Walwriter           Backend
      writes WAL          commit needs WAL
            |                   |
            +---------+---------+
                      |
                      v
                 WAL files
                      |
                      v
                 Flush/sync
~~~

Walwriter có thể đã ghi/flush phần WAL cần thiết trước khi backend commit. Khi đó backend không cần lặp lại toàn bộ I/O.

Nếu chưa, backend có thể tự ghi/flush đến vị trí commit cần bảo đảm.

## 10. wal_writer_delay

`wal_writer_delay` xác định khoảng thời gian walwriter chờ giữa các vòng xử lý WAL buffers.

~~~sql
SHOW wal_writer_delay;
~~~

Giá trị mặc định thường là **200 ms** trong PostgreSQL phổ biến.

Giá trị nhỏ hơn có thể làm walwriter thức dậy thường xuyên hơn; giá trị lớn hơn có thể để WAL buffers chờ lâu hơn trước khi được ghi theo vòng walwriter.

Không điều chỉnh tham số chỉ dựa trên mong muốn “commit nhanh hơn”. Commit synchronous có thể buộc backend flush riêng nếu cần.

## 11. wal_writer_flush_after

`wal_writer_flush_after` xác định lượng WAL đã được walwriter ghi mà sau đó nó thực hiện flush theo ngưỡng.

~~~sql
SHOW wal_writer_flush_after;
~~~

Giá trị mặc định thường khoảng **1 MB** trong các phiên bản/cấu hình PostgreSQL phổ biến. Giá trị `0` có thể vô hiệu hóa ngưỡng flush theo byte cho walwriter.

Tham số này giúp kiểm soát việc flush WAL trong background. Nó không thay đổi semantics durability mà `synchronous_commit` yêu cầu đối với transaction.

| Parameter | Điều khiển |
|---|---|
| `wal_writer_delay` | Thời gian giữa các vòng walwriter |
| `wal_writer_flush_after` | Số bytes WAL đã write trước khi walwriter flush theo ngưỡng |

## 12. Write xuống OS cache khác durable storage

~~~text
PostgreSQL
    |
    | write()
    v
Kernel / filesystem cache
    |
    | fsync() hoặc fdatasync()
    v
Storage device / controller
~~~

Sau write, hệ điều hành có thể giữ dữ liệu trong page cache. Điều đó không tự chứng minh dữ liệu đã tồn tại bền vững qua mất điện.

`fsync`/`fdatasync` yêu cầu đồng bộ dữ liệu và metadata cần thiết theo semantics của platform/filesystem.

### 12.1. Thiết bị lưu trữ phải thực hiện đúng flush semantics

PostgreSQL có thể yêu cầu fsync, nhưng nếu storage controller, hypervisor hoặc thiết bị nói dối về flush completion, durability thực tế có thể không đạt kỳ vọng.

Vận hành production cần storage có write cache/power-loss protection và semantics flush đáng tin cậy.

## 13. fsync

~~~sql
SHOW fsync;
~~~

`fsync=on` là cấu hình được khuyến nghị cho hệ thống cần durability. PostgreSQL yêu cầu hệ điều hành đồng bộ các thay đổi cần thiết tới storage.

Tắt fsync có thể tăng hiệu năng trong một số thử nghiệm nhưng một crash hệ điều hành hoặc mất điện có thể dẫn tới **corruption hoặc mất tính nhất quán**, không chỉ mất vài giao dịch gần nhất.

Không tắt fsync trên production để tối ưu commit latency.

### 13.1. synchronous_commit khác fsync

| Setting | Vai trò |
|---|---|
| `fsync` | Có yêu cầu đồng bộ dữ liệu xuống storage theo durability protocol hay không |
| `synchronous_commit` | Transaction commit có chờ WAL flush/replication acknowledgment tới mức nào |

`synchronous_commit=off` vẫn có thể dùng cùng `fsync=on`; nó thay đổi thời điểm server xác nhận commit, không tắt toàn bộ cơ chế fsync.

## 14. wal_sync_method

~~~sql
SHOW wal_sync_method;
~~~

Tham số này chọn phương pháp PostgreSQL dùng để đồng bộ WAL trên platform hiện tại, ví dụ các biến thể dựa trên `fdatasync`, `fsync`, open_sync hoặc phương pháp tương ứng hệ điều hành.

Giá trị hỗ trợ phụ thuộc platform/build. Không copy giá trị từ Linux sang Windows hoặc ngược lại mà chưa xem khả năng server.

Công cụ `pg_test_fsync` có thể giúp đánh giá hiệu năng các phương pháp đồng bộ trên storage thử nghiệm. Không chạy benchmark I/O tùy tiện trên data directory production.

## 15. COMMIT record trong WAL

Khi transaction commit, PostgreSQL tạo WAL record đánh dấu transaction đã commit.

Một transaction có thể tạo nhiều WAL records cho INSERT/UPDATE/index changes. Commit record là dấu hiệu transaction hoàn tất trong WAL.

~~~text
WAL records cho thay đổi
        |
        v
COMMIT record
        |
        v
Flush theo synchronous_commit policy
        |
        v
Server trả COMMIT thành công
~~~

Nếu crash sau khi commit record durable nhưng trước khi data pages được ghi xuống heap, recovery dùng WAL để redo các thay đổi đã commit.

## 16. Khi nào PostgreSQL xác nhận COMMIT?

Với cấu hình thông dụng `synchronous_commit=on` và `fsync=on`:

1. PostgreSQL đảm bảo WAL chứa commit record đã được ghi/flush tới storage theo durability protocol.
2. Sau khi flush cần thiết hoàn tất, backend có thể trả kết quả COMMIT thành công.
3. Data pages tương ứng không cần đã được ghi xuống table files.
4. Nếu crash, crash recovery dựa trên WAL.

Vì vậy **commit durability dựa trên WAL**, không phải chờ checkpoint ghi mọi data pages.

### 16.1. Client nhận thành công là một mốc rõ ràng, nhưng lỗi mạng có thể tạo kết quả mơ hồ

Nếu server commit xong nhưng connection đứt trước khi response đến client, ứng dụng có thể không biết transaction đã commit hay chưa. Retry không idempotent có thể tạo duplicate side effects.

Thiết kế application cần idempotency key hoặc cơ chế tra cứu kết quả theo business ID.

## 17. synchronous_commit

`synchronous_commit` điều khiển transaction commit chờ đến mức nào.

~~~sql
SHOW synchronous_commit;
~~~

| Value | Chờ ở local | Chờ standby synchronous |
|---|---|---|
| `off` | Không đợi local WAL flush trước khi báo thành công | Không |
| `local` | Đợi local WAL flush | Không đợi remote acknowledgment |
| `remote_write` | Đợi local flush | Đợi standby ghi WAL tới OS, chưa nhất thiết flush durable |
| `on` | Đợi local flush | Nếu synchronous standby được cấu hình, đợi remote flush |
| `remote_apply` | Đợi local flush | Đợi standby apply/replay transaction |

Chi tiết remote modes chỉ có ý nghĩa khi synchronous replication được cấu hình và có standby phù hợp.

## 18. synchronous_commit=on

Đây là lựa chọn phổ biến và mặc định trong PostgreSQL.

~~~sql
SET synchronous_commit = on;
~~~

- Đợi local WAL flush theo durability protocol.
- Nếu synchronous standby được cấu hình, commit còn đợi remote flush theo semantics `on`.
- Không cần đợi checkpoint hoặc tất cả table/index pages.

Mức bảo vệ phụ thuộc `fsync`, filesystem, kernel, storage hardware và replication setup.

## 19. synchronous_commit=off

~~~sql
SET synchronous_commit = off;
~~~

Transaction có thể được báo thành công **trước khi WAL records của nó được flush bền vững**.

Nếu database/OS crash ngay sau phản hồi, một số giao dịch vừa được xác nhận có thể bị mất khi recovery.

Điều quan trọng:

- Database vẫn giữ consistency theo WAL recovery design.
- Đây không đồng nghĩa `fsync=off`.
- Rủi ro chính là mất các giao dịch gần đây đã được xác nhận, không phải cho phép database ghi heap trước WAL.
- Walwriter/background flush sau đó vẫn ghi WAL.

Chỉ cân nhắc cho workload chấp nhận được việc mất một lượng giao dịch rất gần thời điểm crash và có thể tái tạo. Không dùng cho ledger, payment hoặc order confirmation mà ứng dụng cam kết durable ngay khi trả success.

## 20. local, remote_write và remote_apply

Khi có synchronous replication:

- `local`: đợi local WAL flush, bỏ qua việc chờ synchronous standby.
- `remote_write`: đợi standby ghi WAL vào OS, nhưng không đảm bảo standby đã flush bền vững.
- `on`: đợi standby flush WAL theo yêu cầu synchronous replication.
- `remote_apply`: đợi standby replay/apply transaction để queries trên standby có thể nhìn thấy thay đổi.

### 20.1. remote_write không giống remote flush

Standby write xuống OS cache có thể chưa durable qua mất điện ở standby. Nếu yêu cầu một bản sao remote đã flush, dùng semantics phù hợp như `on`.

### 20.2. remote_apply có thể tăng latency

Standby cần nhận, flush và replay WAL. Điều này tăng thời gian commit nhưng có thể hữu ích cho yêu cầu read-after-commit trên standby.

## 21. synchronous_standby_names

Để synchronous replication có tác dụng, primary cần cấu hình standby được xem là synchronous.

~~~sql
SHOW synchronous_standby_names;
~~~

Cấu hình xác định standby nào tham gia acknowledgment, có thể dùng chính sách quorum/priority theo syntax PostgreSQL.

Nếu không có synchronous standby được cấu hình, các mức remote của synchronous_commit không tự tạo ra một standby để chờ.

Quan sát:

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

Một standby đang streaming chưa chắc là synchronous standby được chọn cho commit.

## 22. Group commit

Nếu nhiều transactions commit gần nhau, PostgreSQL có thể **group commit**: một lần flush WAL có thể đáp ứng durability requirement cho nhiều transactions.

~~~text
Transaction A -- COMMIT --+
Transaction B -- COMMIT --+--> WAL flush
Transaction C -- COMMIT --+       |
Transaction D -- COMMIT --+       v
                           Nhiều commits được xác nhận
~~~

Group commit giúp tăng throughput mà không cần một fsync riêng cho từng transaction.

Walwriter có thể ghi WAL buffers theo lịch, giúp backend không phải tự làm mọi write. Nhưng synchronous commit vẫn phải bảo đảm flush tới vị trí commit cần thiết trước khi trả success.

## 23. commit_delay và commit_siblings

~~~sql
SHOW commit_delay;
SHOW commit_siblings;
~~~

- `commit_delay`: khoảng microseconds backend có thể chờ trước khi flush WAL để tạo cơ hội gom thêm commits.
- `commit_siblings`: số transactions đồng thời mở tối thiểu để áp dụng commit delay.

Mặc định `commit_delay` thường là 0, tức không chủ động trì hoãn.

Delay có thể tăng latency từng transaction nhưng tăng throughput trong một số workload có nhiều concurrent commits. Cần benchmark với traffic thực.

## 24. Checkpoint khác COMMIT

Đây là điểm rất hay bị nhầm.

**COMMIT** xác nhận một transaction đã hoàn tất theo WAL durability policy.

**CHECKPOINT** ghi dirty data pages và cập nhật checkpoint information để giảm lượng WAL phải replay sau crash.

~~~text
COMMIT:
WAL commit record --> flush --> trả success

CHECKPOINT:
WAL đã đủ bền vững --> ghi dirty data pages
                    --> checkpoint record/state
~~~

Một transaction có thể đã commit durable từ lâu nhưng data page vẫn chưa được ghi bởi checkpoint kế tiếp.

### 24.1. Không chờ checkpoint mới được commit

PostgreSQL không cần flush toàn bộ table/index pages của transaction tại COMMIT. WAL cho phép phục hồi những thay đổi này sau crash.

## 25. Write-ahead rule và checkpoint

Khi checkpointer ghi một dirty page xuống data file, WAL liên quan đến page đó phải đã được flush ít nhất tới LSN cần thiết.

~~~text
WAL durable through page LSN
          |
          v
Data page được phép ghi xuống relation file
~~~

Điều này bảo vệ crash recovery nếu page write bị torn hoặc crash xảy ra giữa các thao tác.

## 26. full_page_writes

~~~sql
SHOW full_page_writes;
~~~

`full_page_writes` thường bật. Sau checkpoint, lần đầu một page được sửa có thể tạo full-page image trong WAL để recovery sửa chữa torn page theo cơ chế PostgreSQL.

Nó có thể làm WAL volume tăng, đặc biệt ngay sau checkpoint hoặc workload cập nhật nhiều pages.

Không tắt full_page_writes chỉ để giảm WAL mà chưa hiểu rủi ro corruption/torn pages và storage guarantees.

## 27. Checkpoint frequency và WAL volume

~~~sql
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW checkpoint_completion_target;
~~~

- `checkpoint_timeout`: khoảng thời gian tối đa giữa các checkpoints theo lịch.
- `max_wal_size`: ngưỡng WAL để kích hoạt checkpoint sớm hơn; không phải hard cap tuyệt đối cho pg_wal.
- `checkpoint_completion_target`: mục tiêu phân bố thời gian ghi checkpoint qua khoảng thời gian liên quan.

Checkpoint quá thường xuyên có thể tăng I/O và full-page images. Checkpoint quá thưa có thể tăng thời gian recovery và WAL retention.

Đừng tăng checkpoint_timeout với kỳ vọng làm COMMIT synchronous không cần flush. Commit durability và checkpoint là hai cơ chế khác nhau.

## 28. Background writer khác walwriter

| Process | Nhiệm vụ chính |
|---|---|
| `walwriter` | Ghi WAL buffers ra WAL files |
| `background writer` | Ghi dirty data buffers theo cơ chế nền |
| `checkpointer` | Thực hiện checkpoint, ghi dirty pages |
| `backend` | Xử lý query/transaction, có thể ghi data/WAL khi cần |

Các process này có thể cùng tạo I/O nhưng làm việc với những vùng dữ liệu và mục tiêu khác nhau.

## 29. wal_buffers và commit latency

~~~sql
SHOW wal_buffers;
~~~

WAL buffers quá nhỏ có thể khiến backends phải tham gia ghi WAL thường xuyên hơn trong một số workload. Tuy nhiên tăng wal_buffers không tự giảm fsync latency của storage.

Tối ưu cần phân biệt WAL generation rate, buffer pressure, write throughput, flush/fsync latency, synchronous replication wait và CPU overhead.

Không tăng shared memory settings chỉ dựa trên một chỉ số commit latency.

## 30. Quan sát WAL statistics

View `pg_stat_wal` cung cấp thống kê WAL tổng hợp trên các phiên bản hỗ trợ:

~~~sql
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
~~~

Các trường thường gặp:

- `wal_records`: số WAL records được tạo.
- `wal_fpi`: số full-page images.
- `wal_bytes`: tổng bytes WAL được tạo.
- `wal_buffers_full`: số lần WAL buffers đầy và phải xử lý.
- `wal_write`: số write operations.
- `wal_sync`: số sync operations.
- `wal_write_time` và `wal_sync_time`: thời gian write/sync nếu tracking tương ứng được bật.
- `stats_reset`: thời điểm reset statistics.

Tên/trường cụ thể có thể thay đổi theo PostgreSQL version; xem schema view trên server thực tế.

## 31. track_wal_io_timing

~~~sql
SHOW track_wal_io_timing;
~~~

Khi bật, PostgreSQL có thể thu thập thời gian cho các WAL I/O operations tương ứng, giúp phân biệt thời gian write và sync.

Các timing metrics có overhead nhỏ nhưng vẫn nên cân nhắc trên workload rất nhạy latency.

Không kết luận fsync chậm chỉ từ số lượng wal_sync; xem tổng thời gian, số operations, workload và storage telemetry.

## 32. pg_stat_activity và WAL wait events

Khi commit chậm, xem:

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE wait_event IS NOT NULL
ORDER BY query_start;
~~~

Một số wait events có thể liên quan WAL, chẳng hạn chờ write/sync WAL theo version.

Wait event names và taxonomy có thể thay đổi theo version. Hãy dùng `pg_wait_events` nếu có, hoặc tra danh mục phù hợp với server.

Không phải mọi commit chậm đều do fsync. Các nguyên nhân khác gồm lock waits, synchronous standby lag, storage queue congestion, CPU scheduling, network latency và WAL volume cao.

## 33. Quan sát synchronous replication lag

Trên primary:

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

- `write_lsn`: vị trí standby đã write.
- `flush_lsn`: vị trí standby đã flush.
- `replay_lsn`: vị trí standby đã replay/apply.
- Lag fields là thống kê thời gian gần đây, có thể NULL khi không có sample phù hợp.

Nếu `synchronous_commit=on` và standby được chọn là synchronous nhưng flush chậm, COMMIT có thể chờ remote flush.

## 34. Lab: hai session kiểm tra commit và WAL LSN

Mở hai psql sessions trong **database lab**.

Tạo bảng một lần:

~~~sql
CREATE TABLE wal_lab (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

**Session A:**

~~~sql
SHOW synchronous_commit;

SELECT
    pg_current_wal_insert_lsn(),
    pg_current_wal_lsn(),
    pg_current_wal_flush_lsn();
~~~

**Session B:**

~~~sql
BEGIN;

INSERT INTO wal_lab(value)
VALUES ('transaction one');

COMMIT;
~~~

Sau khi COMMIT trả về, chạy lại các LSN queries ở session A.

Trong workload đồng thời, vị trí insert/write/flush có thể tiến xa hơn transaction đang kiểm tra. LSN là vị trí WAL toàn hệ thống, không phải nhãn riêng cho row vừa INSERT.

## 35. Lab: so sánh synchronous_commit=on và off

Trong session B lab:

~~~sql
BEGIN;

SET LOCAL synchronous_commit = on;

INSERT INTO wal_lab(value)
VALUES ('durability setting on');

COMMIT;
~~~

Thử transaction khác:

~~~sql
BEGIN;

SET LOCAL synchronous_commit = off;

INSERT INTO wal_lab(value)
VALUES ('durability setting off');

COMMIT;
~~~

`SET LOCAL` chỉ áp dụng trong transaction hiện tại.

Nếu không có crash, cả hai rows có thể đều xuất hiện. Sự khác biệt là **thời điểm server xác nhận COMMIT so với thời điểm WAL durable**, không phải một row chắc chắn mất khi dùng off.

Không mô phỏng crash bằng cách kill máy/database production. Durability testing cần môi trường cô lập và quy trình riêng.

## 36. Lab: quan sát background processes

~~~sql
SELECT
    pid,
    backend_type,
    state,
    wait_event_type,
    wait_event,
    backend_start
FROM pg_stat_activity
WHERE backend_type IN (
    'walwriter',
    'background writer',
    'checkpointer'
)
ORDER BY backend_type;
~~~

View và backend_type values tùy version; trên các phiên bản hỗ trợ có thể quan sát process names tương ứng.

Các process này do PostgreSQL quản lý. Không gửi SQL COMMIT/ROLLBACK hay terminate chúng tùy tiện như session ứng dụng.

## 37. Java JDBC và thời điểm commit trả về

Trong JDBC:

~~~java
connection.setAutoCommit(false);

try {
    // INSERT/UPDATE statements
    connection.commit();
} catch (Exception e) {
    connection.rollback();
    throw e;
}
~~~

Khi `commit()` trả về bình thường, server đã xác nhận transaction theo cấu hình durability đang áp dụng, ví dụ `synchronous_commit`.

JDBC không tự biết WAL đã được flush local/remote tới mức nào; semantics đến từ PostgreSQL configuration.

### 37.1. Commit response bị mất trên mạng

Nếu server commit thành công nhưng socket đứt trước khi client nhận response, ứng dụng có thể thấy exception và không biết transaction đã commit hay chưa.

Không retry một giao dịch không idempotent chỉ vì client không thấy response. Dùng business request ID/unique constraint/idempotency key để xác định kết quả.

## 38. SET LOCAL và SET SESSION synchronous_commit

Có thể đặt theo session:

~~~sql
SET synchronous_commit = off;
~~~

Hoặc trong transaction:

~~~sql
BEGIN;
SET LOCAL synchronous_commit = off;
-- statements
COMMIT;
~~~

Có thể cấu hình theo role/database bằng ALTER ROLE/ALTER DATABASE khi có nhu cầu được review.

Đừng đặt global off chỉ để giảm latency cho một job batch.

## 39. COMMIT AND CHAIN

PostgreSQL hỗ trợ:

~~~sql
COMMIT AND CHAIN;
~~~

Lệnh này commit transaction hiện tại và bắt đầu transaction mới với đặc tính transaction tương ứng. Nó không thay đổi durability semantics của commit vừa kết thúc.

Tương tự, `ROLLBACK AND CHAIN` bắt đầu transaction mới sau rollback.

## 40. Asynchronous commit và consistency

`synchronous_commit=off` có thể làm mất những transactions gần nhất đã được server báo thành công nếu crash trước khi WAL flush, nhưng PostgreSQL vẫn giữ tính nhất quán nội bộ thông qua WAL recovery. Có thể có khoảng thời gian dữ liệu mất sau khi application đã nhận success.

Một hệ thống không nên hứa “đã lưu vĩnh viễn” nếu transaction được commit ở chế độ asynchronous.

### 40.1. Sequence và side effects

Ngay cả khi database phục hồi consistency, external side effects (email, payment gateway, message publish) không tự rollback theo WAL. Cần transactional outbox và idempotency cho các tích hợp đó.

## 41. Tuning WAL writer và commit latency

Trước khi thay tham số, phân loại bottleneck:

| Triệu chứng | Hướng kiểm tra |
|---|---|
| wal_buffers_full tăng nhanh | WAL buffer pressure/generation |
| wal_write_time cao | Write path/storage throughput |
| wal_sync_time cao | Flush/fsync latency |
| pg_stat_replication flush_lag cao | Synchronous standby/storage/network |
| Nhiều WAL bytes | Write workload, full-page images, bulk updates |
| Commit chậm nhưng WAL sync thấp | Locks, CPU, app/network, remote wait |
| Checkpoint writes gây I/O burst | Checkpoint cadence/completion target/storage |

Tăng wal_writer_delay không chữa được storage fsync chậm hoặc standby lag.

## 42. Checkpoint statistics theo version

Ở các phiên bản PostgreSQL khác nhau, checkpoint statistics được tổ chức trong các views khác nhau.

PostgreSQL 17+ có `pg_stat_checkpointer` để theo dõi checkpoint counts/timings/buffers; những phiên bản cũ hơn đặt một phần thông tin trong `pg_stat_bgwriter`.

Ví dụ trên server có view phù hợp:

~~~sql
SELECT *
FROM pg_stat_checkpointer;
~~~

Trên version cũ hơn, xem:

~~~sql
SELECT *
FROM pg_stat_bgwriter;
~~~

Không chạy query hard-code cột của version mới trên server cũ. Dùng `\d+ pg_stat_checkpointer` hoặc `\d+ pg_stat_bgwriter` trong psql để xem schema thực tế.

## 43. WAL archive và commit durability

`archive_mode` và `archive_command` phục vụ archive WAL segments cho PITR/backup.

Archive thành công không phải điều kiện để mỗi local transaction COMMIT được xác nhận trong cấu hình thông thường.

Phân biệt:

- Local WAL flush: durability của transaction trên primary theo fsync policy.
- Synchronous replication acknowledgment: remote standby acknowledgment theo sync mode.
- WAL archive: lưu trữ segment để phục hồi point-in-time.

Một transaction đã commit có thể được archive sau đó khi segment hoàn tất/switch theo workflow.

## 44. WAL switch và segment recycling

~~~sql
SELECT pg_switch_wal();
~~~

Function yêu cầu chuyển sang WAL segment mới trong những điều kiện phù hợp. Nó có thể hữu ích trong một số quy trình archive/testing nhưng không phải lệnh flush từng transaction.

Không gọi liên tục để “làm COMMIT nhanh hơn”; switch quá thường xuyên có thể tạo nhiều segment ít dữ liệu và tăng chi phí archive/management.

## 45. synchronous_commit và logical replication

`synchronous_commit` local/remote semantics không tự đồng nghĩa logical subscriber đã áp dụng mọi thay đổi. Logical replication có slot/consumer progress và cơ chế riêng.

Nếu yêu cầu subscriber logical phải apply trước khi primary trả success, cần thiết kế synchronous replication phù hợp với topology/version và xác minh hỗ trợ; không suy từ việc có một logical slot.

## 46. Durability và backup

WAL flush giúp transaction durable trên primary theo storage contract, nhưng không thay backup.

Backup/PITR bảo vệ khỏi xóa nhầm dữ liệu, lỗi ứng dụng ghi dữ liệu sai, hỏng storage vượt khả năng redundancy, mất cả cluster/site và thao tác quản trị sai.

Một transaction commit durable vẫn có thể là transaction nghiệp vụ sai. Cần backup, WAL archive, restore tests và disaster recovery.

## 47. Những hiểu lầm thường gặp

### 47.1. Walwriter ghi data pages

Sai. Walwriter ghi WAL buffers; checkpointer/background writer làm việc với data buffers.

### 47.2. write() đồng nghĩa durable

Sai. Write có thể chỉ đưa dữ liệu vào OS cache; cần flush/fsync theo durability protocol.

### 47.3. COMMIT phải chờ checkpoint

Sai. Commit chờ WAL durability theo policy, không chờ tất cả data pages được checkpoint.

### 47.4. synchronous_commit=off nghĩa fsync=off

Sai. Đây là hai thiết lập khác nhau. Off có thể xác nhận trước local WAL flush; fsync off tắt yêu cầu sync durability và nguy hiểm hơn.

### 47.5. Walwriter luôn flush trước mọi COMMIT

Sai. Backend có thể tự ghi/flush khi commit cần và walwriter có lịch riêng.

### 47.6. Tăng wal_writer_delay luôn tăng throughput

Không chắc. Có thể tăng thời gian WAL chờ; backend synchronous commit có thể phải flush riêng.

### 47.7. remote_write tương đương remote durable

Sai. Standby đã write vào OS nhưng chưa nhất thiết flush bền vững.

### 47.8. remote_apply chỉ chờ write

Sai. Nó chờ standby replay/apply transaction.

### 47.9. Checkpoint và commit là cùng một mốc

Sai. Commit đánh dấu transaction; checkpoint flush data pages và tạo recovery point.

### 47.10. max_wal_size là hard cap của pg_wal

Sai. Đây là ngưỡng checkpoint target, không phải giới hạn tuyệt đối mọi WAL retention.

### 47.11. WAL archive phải xong trước khi COMMIT

Không trong cấu hình thông thường. Archive là workflow riêng.

### 47.12. Nếu JDBC commit exception thì transaction chắc chắn rollback

Sai. Có thể response bị mất sau khi server đã commit; kết quả có thể ambiguous.

## 48. Checklist chẩn đoán COMMIT chậm

1. Xác định synchronous_commit của session/transaction.
2. Kiểm tra fsync và wal_sync_method.
3. Xem pg_stat_wal write/sync counts và timings.
4. Bật/kiểm tra track_wal_io_timing nếu phù hợp.
5. Kiểm tra wait events WALWrite/WALSync theo version.
6. Xem pg_stat_replication nếu synchronous standby được cấu hình.
7. Kiểm tra lock waits và query duration.
8. Đo WAL bytes/transaction và full-page images.
9. Kiểm tra storage latency, queue depth và power-loss protection.
10. So sánh walwriter activity và WAL buffer pressure.
11. Xem checkpoint statistics riêng, không đồng nhất với commit.
12. Benchmark concurrency/group commit bằng workload thực.
13. Không tắt fsync hoặc full_page_writes để che bottleneck.
14. Nếu response bị mất, dùng idempotency để xử lý commit ambiguity.

## 49. Bài tập thực hành

### Bài 1 — WAL

Vì sao PostgreSQL dùng WAL?

**Gợi ý:** write-ahead và crash recovery.

### Bài 2 — WAL buffers

WAL records được tạo ban đầu ở đâu?

**Gợi ý:** WAL buffers trong shared memory.

### Bài 3 — Data buffers

Phân biệt shared buffers và WAL buffers.

**Gợi ý:** data pages vs log records.

### Bài 4 — Insert LSN

`pg_current_wal_insert_lsn` biểu thị gì?

**Gợi ý:** vị trí WAL được insert vào buffers.

### Bài 5 — Write LSN

`pg_current_wal_lsn` biểu thị gì?

**Gợi ý:** vị trí WAL đã được write.

### Bài 6 — Flush LSN

`pg_current_wal_flush_lsn` biểu thị gì?

**Gợi ý:** vị trí WAL đã flush.

### Bài 7 — Write vs flush

Tại sao write xuống OS cache chưa đủ để kết luận durable?

**Gợi ý:** cần fsync/fdatasync semantics.

### Bài 8 — Walwriter

Walwriter làm nhiệm vụ gì?

**Gợi ý:** ghi WAL buffers ra WAL files.

### Bài 9 — Backend flush

Vì sao backend có thể tự flush WAL?

**Gợi ý:** synchronous commit cần WAL durable tới commit record.

### Bài 10 — wal_writer_delay

Tham số này điều khiển gì?

**Gợi ý:** thời gian giữa các vòng walwriter.

### Bài 11 — wal_writer_flush_after

Tham số này điều khiển gì?

**Gợi ý:** byte threshold trước khi walwriter flush.

### Bài 12 — fsync

Tại sao production thường bật fsync?

**Gợi ý:** durability qua OS crash/power loss theo storage contract.

### Bài 13 — synchronous_commit

Nó điều khiển điều gì?

**Gợi ý:** mức độ commit chờ WAL flush/remote acknowledgment.

### Bài 14 — off

synchronous_commit=off có rủi ro nào?

**Gợi ý:** mất một số transactions gần đây đã được báo success khi crash.

### Bài 15 — fsync vs synchronous_commit

Phân biệt hai setting.

**Gợi ý:** storage sync mechanism vs commit wait policy.

### Bài 16 — remote_write

Standby đã write nhưng chưa chắc điều gì?

**Gợi ý:** chưa chắc durable flush.

### Bài 17 — remote_apply

Khác on ở đâu?

**Gợi ý:** chờ standby replay/apply.

### Bài 18 — local

local có chờ synchronous standby không?

**Gợi ý:** không, nhưng đợi local flush.

### Bài 19 — synchronous_standby_names

Vai trò của setting này?

**Gợi ý:** chọn synchronous standbys.

### Bài 20 — Group commit

Group commit giúp gì?

**Gợi ý:** một WAL flush đáp ứng nhiều transactions.

### Bài 21 — commit_delay

Nó có thể tăng throughput khi nào?

**Gợi ý:** concurrent commits đủ nhiều để group.

### Bài 22 — commit_siblings

Điều khiển điều kiện nào?

**Gợi ý:** số transactions đang mở tối thiểu cho commit_delay.

### Bài 23 — Checkpoint

Checkpoint làm gì?

**Gợi ý:** flush dirty data pages và tạo recovery point.

### Bài 24 — Commit vs checkpoint

Tại sao commit không chờ checkpoint?

**Gợi ý:** WAL đủ để redo sau crash.

### Bài 25 — full_page_writes

Nó giúp chống vấn đề gì?

**Gợi ý:** torn pages sau checkpoint.

### Bài 26 — Background writer

Khác walwriter ở đâu?

**Gợi ý:** data buffers vs WAL buffers.

### Bài 27 — wal_buffers

Nó giữ dữ liệu nào?

**Gợi ý:** WAL records trong shared memory.

### Bài 28 — pg_stat_wal

Nêu bốn metrics hữu ích.

**Gợi ý:** wal_bytes, wal_records, wal_write, wal_sync, timing.

### Bài 29 — track_wal_io_timing

Nó giúp quan sát gì?

**Gợi ý:** thời gian WAL write/sync.

### Bài 30 — pg_stat_replication

Các LSN nào giúp theo dõi standby progress?

**Gợi ý:** write_lsn, flush_lsn, replay_lsn.

### Bài 31 — JDBC commit

Khi Connection.commit trả về bình thường, semantics phụ thuộc gì?

**Gợi ý:** server durability settings.

### Bài 32 — Ambiguous commit

Tại sao client nhận SQLException không chứng minh transaction rollback?

**Gợi ý:** response có thể mất sau server commit.

### Bài 33 — Idempotency

Cách nào xử lý retry sau commit ambiguity?

**Gợi ý:** unique business key/idempotency key.

### Bài 34 — WAL archive

Archive WAL có phải điều kiện để COMMIT local thành công không?

**Gợi ý:** không trong cấu hình thông thường.

### Bài 35 — pg_switch_wal

Có phải lệnh flush mỗi transaction không?

**Gợi ý:** không, nó switch segment.

### Bài 36 — max_wal_size

Có phải hard cap của pg_wal không?

**Gợi ý:** không.

### Bài 37 — Storage

Vì sao hardware write cache cần power-loss protection/flush semantics đúng?

**Gợi ý:** fsync không thể bù thiết bị báo durable sai.

### Bài 38 — Commit latency

Nêu ba nguyên nhân khác fsync có thể làm COMMIT chậm.

**Gợi ý:** locks, synchronous standby lag, CPU/network.

### Bài 39 — WAL buffers full

Metric wal_buffers_full tăng gợi ý điều gì?

**Gợi ý:** buffer pressure và WAL generation/write workload.

### Bài 40 — Durability choice

Khi nào có thể cân nhắc synchronous_commit=off?

**Gợi ý:** chỉ workload chấp nhận mất giao dịch gần đây và có khả năng tái tạo.

## 50. Câu hỏi thường gặp

### Walwriter có phải process duy nhất ghi WAL không?

Không. Backend processes cũng có thể ghi/flush WAL khi cần, đặc biệt khi commit cần WAL durable tới vị trí cụ thể.

### WAL đã write là đã an toàn qua mất điện chưa?

Không nhất thiết. Write có thể chỉ đưa dữ liệu vào OS cache. Flush/fsync và storage semantics mới quyết định durability.

### COMMIT có chờ data page ghi xuống bảng không?

Không. Commit thường chờ WAL theo durability policy; data pages có thể được ghi ở checkpoint/background sau đó.

### synchronous_commit=off có thể mất dữ liệu không?

Có thể mất những transactions gần đây đã được server báo thành công nếu crash trước khi WAL flush. Database vẫn dựa trên WAL recovery để giữ consistency.

### Tắt fsync có giống synchronous_commit=off không?

Không. Tắt fsync có thể gây corruption/mất consistency khi crash. synchronous_commit=off thay đổi thời điểm xác nhận commit nhưng giữ cơ chế fsync cho các writes khác.

### remote_write có bảo đảm remote durable không?

Không. Nó đợi standby write WAL vào OS; remote flush chưa nhất thiết hoàn tất.

### remote_apply dùng khi nào?

Khi cần commit chờ standby replay/apply transaction, ví dụ một số yêu cầu read-after-commit trên standby.

### Group commit có làm mọi transaction phải chờ lâu hơn không?

Không nhất thiết. Nó có thể dùng một flush chung cho nhiều commits. commit_delay là cơ chế chờ có điều kiện và cần benchmark.

### Checkpoint quá thường xuyên có ảnh hưởng gì?

Có thể tăng data I/O và full-page images/WAL volume. Cần cân bằng với recovery time và WAL capacity.

### pg_stat_wal có đo commit latency trực tiếp không?

Không. Nó cung cấp thống kê WAL write/sync. Phải kết hợp query timing, wait events, replication metrics và application measurements.

### Nếu JDBC commit timeout thì có nên retry ngay?

Không nếu thao tác không idempotent. Server có thể đã commit nhưng response bị mất. Tra cứu theo business key hoặc idempotency key.

### WAL archive đã có thì có thể tắt fsync không?

Không. Archiving không thay durability của local WAL/data files.

### Tăng wal_writer_delay có giảm commit latency không?

Không đảm bảo. Synchronous backend có thể tự flush nếu cần; thay đổi phải dựa trên measurements.

## 51. Tổng kết

Các câu lệnh quan sát quan trọng:

~~~sql
-- WAL configuration.
SHOW wal_buffers;
SHOW wal_writer_delay;
SHOW wal_writer_flush_after;
SHOW synchronous_commit;
SHOW fsync;
SHOW wal_sync_method;

-- WAL progress.
SELECT
    pg_current_wal_insert_lsn(),
    pg_current_wal_lsn(),
    pg_current_wal_flush_lsn();

-- Bytes chưa flush tại thời điểm query.
SELECT pg_wal_lsn_diff(
    pg_current_wal_insert_lsn(),
    pg_current_wal_flush_lsn()
);

-- WAL statistics.
SELECT *
FROM pg_stat_wal;

-- Synchronous replication progress.
SELECT
    application_name,
    state,
    sync_state,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;

-- WAL wait events and session activity.
SELECT
    pid,
    wait_event_type,
    wait_event,
    state
FROM pg_stat_activity
WHERE wait_event IS NOT NULL;
~~~

Những nguyên tắc cần nhớ:

1. **WAL records được tạo trước khi data pages được ghi bền vững** theo write-ahead rule.
2. WAL buffers nằm trong shared memory; walwriter ghi chúng ra WAL segment files.
3. Backend có thể tự write/flush WAL khi COMMIT cần durability.
4. **Insert, write và flush LSN là ba mốc khác nhau.**
5. Write xuống OS cache chưa đồng nghĩa durable qua mất điện.
6. `fsync=on` là lựa chọn quan trọng cho production durability.
7. `synchronous_commit` quyết định transaction chờ local/remote acknowledgment đến mức nào.
8. `off` có thể báo success trước local WAL flush; những transactions gần đây có thể mất sau crash.
9. `remote_write` không giống remote flush; `remote_apply` chờ standby replay.
10. Group commit cho phép nhiều transactions dùng chung WAL flush.
11. `wal_writer_delay` và `wal_writer_flush_after` điều khiển hoạt động walwriter, không thay durability contract.
12. **COMMIT không cần chờ CHECKPOINT**; WAL đủ bền vững để recovery.
13. Checkpoint ghi dirty data pages và tạo recovery point.
14. Background writer xử lý data buffers; walwriter xử lý WAL buffers.
15. Theo dõi `pg_stat_wal`, LSN gaps, wait events và `pg_stat_replication`.
16. JDBC commit exception có thể là kết quả mơ hồ nếu response mất sau khi server commit; cần idempotency.
17. WAL archive và backup không thay thế fsync hoặc disaster recovery.
18. Storage hardware phải thực hiện đúng flush semantics.

Sơ đồ thời điểm xác nhận:

~~~text
SQL INSERT/UPDATE
       |
       v
WAL records được tạo
       |
       v
WAL buffers (insert LSN)
       |
       v
Write WAL files (write LSN)
       |
       v
Flush WAL (flush LSN)
       |
       v
Commit record durable theo policy?
       |
       +--> synchronous_commit=on:
       |       chờ local flush
       |       và remote flush nếu sync standby
       |
       +--> synchronous_commit=off:
       |       có thể trả success trước local flush
       |
       v
Server trả COMMIT success
       |
       v
Data pages được ghi bởi background/checkpointer
       |
       v
Checkpoint hoàn tất theo lịch/threshold
~~~

**Kết luận:** Walwriter giúp PostgreSQL ghi WAL buffers đều đặn và giảm áp lực cho backend, nhưng **thời điểm COMMIT được xác nhận phụ thuộc durability policy**, đặc biệt là `synchronous_commit`, `fsync` và synchronous replication. Hãy phân biệt write với flush, commit với checkpoint, local durability với remote acknowledgment, và kiểm chứng latency bằng WAL/replication metrics trước khi điều chỉnh cấu hình.
