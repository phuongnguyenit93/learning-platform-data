# WAL record, segment, LSN và thứ tự thay đổi trong PostgreSQL

## 1. Vì sao cần hiểu WAL và thứ tự ghi?

PostgreSQL dùng **Write-Ahead Logging (WAL)** để bảo vệ tính nhất quán khi máy chủ gặp sự cố và để truyền các thay đổi vật lý tới standby. Thay vì yêu cầu mọi data page được ghi ngay xuống data files trước khi xác nhận một transaction, PostgreSQL ghi mô tả các thay đổi vào WAL theo thứ tự xác định. Khi crash, server có thể đọc WAL và redo những thao tác cần thiết từ checkpoint phù hợp.

WAL không chỉ là một file log văn bản. Nó là một luồng nhị phân có cấu trúc, được chia thành records, pages và segments. Mỗi record chiếm một vùng trong WAL stream và có vị trí được biểu diễn bằng **Log Sequence Number (LSN)**.

Muốn hiểu vì sao một COMMIT đã được xác nhận có thể tồn tại dù data page chưa được flush, cần nối các khái niệm:

- **WAL record:** đơn vị thông tin nhị phân mô tả một thay đổi hoặc sự kiện cần cho recovery/replication.
- **WAL page:** đơn vị page trong WAL stream, có header và chứa một phần hoặc nhiều record.
- **WAL segment:** file vật lý chứa một dải liên tiếp của WAL stream.
- **LSN:** địa chỉ logic xác định vị trí trong WAL stream.
- **Page LSN:** vị trí WAL cuối cùng đã được áp dụng vào một data page.
- **Commit record:** record ghi nhận transaction hoàn tất.
- **Checkpoint:** điểm mà PostgreSQL đã đảm bảo các dirty data pages cần thiết được ghi, giúp giới hạn phạm vi redo sau crash.
- **Timeline:** nhánh lịch sử WAL, đặc biệt quan trọng sau promotion/failover.

### 1.1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích write-ahead rule và mối quan hệ giữa WAL và data pages.
2. Mô tả các thành phần cơ bản của một WAL record.
3. Phân biệt WAL record, WAL page, WAL segment và transaction.
4. Đọc định dạng LSN và tính khoảng cách WAL bằng SQL.
5. Hiểu cách WAL segments được đặt tên, tạo, recycle và archive.
6. Giải thích thứ tự WAL record khi nhiều transactions chạy đồng thời.
7. Phân biệt insert position, write position và flush position.
8. Hiểu commit record, group commit, synchronous_commit và durability.
9. Giải thích page LSN, redo và checkpoint.
10. Quan sát WAL/replication bằng PostgreSQL functions, views và command-line tools.
11. Nhận diện các sai lầm phổ biến khi đọc WAL và xử lý file segment.
12. Thực hành các bài lab và bài tập để diễn giải LSN/record ordering.

### 1.2. Phạm vi phiên bản

Các khái niệm WAL/LSN có tính nền tảng nhưng chi tiết record format, resource managers, system views, functions và command-line options có thể thay đổi giữa major versions. Các ví dụ dùng cú pháp PostgreSQL hiện đại; hãy kiểm tra tài liệu đúng phiên bản server, đặc biệt khi dùng pg_walinspect, pg_waldump hoặc các cột monitoring mới.

> WAL là dữ liệu phục vụ recovery. Không sửa, đổi tên hoặc xóa file trong pg_wal bằng thao tác filesystem thủ công. Nếu cần giải phóng WAL, hãy tìm nguyên nhân retention qua checkpoint, archive, replication slots và standby.

---

## 2. Write-Ahead Logging: quy tắc cốt lõi

### 2.1. Write-ahead rule

Nguyên tắc cơ bản:

**WAL records mô tả thay đổi của một data page phải được ghi bền tới WAL trước khi data page tương ứng được ghi bền xuống data file.**

Giả sử UPDATE một row trong heap page:

~~~text
SQL UPDATE
    |
    v
Thay đổi page trong shared buffers (dirty page)
    |
    +--> Tạo WAL record mô tả thay đổi
    |
    v
WAL record được insert vào WAL buffers
    |
    v
WAL được write/flush theo durability rules
    |
    v
Data page có thể được ghi xuống heap file về sau
~~~

Hình này là mô hình khái niệm; thứ tự chi tiết giữa nhiều buffers, background writer, WAL writer và backend có thể phức tạp hơn. Điều không thay đổi là PostgreSQL phải bảo đảm WAL cần thiết được flush trước khi data page chứa thay đổi tương ứng được ghi bền.

### 2.2. Tại sao không ghi data page trước?

Nếu data page được ghi xuống đĩa nhưng WAL record cần để khôi phục page đó chưa được ghi bền, crash có thể để lại page chứa một phần thay đổi mà không có log để redo/repair đúng cách.

Write-ahead rule giúp recovery biết những thay đổi nào đã được ghi log và có thể phát lại chúng.

### 2.3. Data page chưa flush không có nghĩa transaction chưa bền

Một transaction có thể được COMMIT và xác nhận sau khi commit record đã được flush theo durability policy, dù các heap/index pages được thay đổi vẫn đang ở shared buffers hoặc chưa được ghi xuống data files.

Khi crash, PostgreSQL đọc checkpoint và redo WAL để khôi phục những page changes còn thiếu. Đây là lý do WAL là nền tảng của durability.

### 2.4. WAL không thay thế data files

WAL không phải một bản sao đầy đủ của database có thể được dùng thay thế data directory. Để phục hồi một database tới trạng thái mong muốn, cần base backup/data files thích hợp và WAL cần thiết theo recovery chain.

### 2.5. WAL và crash recovery

Khi PostgreSQL khởi động sau crash:

1. Đọc checkpoint information.
2. Xác định vị trí bắt đầu redo phù hợp.
3. Đọc WAL records theo thứ tự LSN.
4. Áp dụng lại các thay đổi cần thiết vào data pages.
5. Bỏ qua hoặc xử lý những thao tác đã có hiệu lực theo cơ chế recovery.
6. Đưa cluster trở lại trạng thái nhất quán để phục vụ kết nối.

Chi tiết recovery còn bao gồm transaction status, hint bits, full-page images, resource manager redo routines và các cơ chế nội bộ khác.

### 2.6. WAL record không phải SQL statement

Một SQL statement có thể tạo nhiều WAL records:

- UPDATE heap tuple.
- Cập nhật một hoặc nhiều index entries.
- Thay đổi visibility/transaction metadata liên quan.
- Trigger ghi thêm bảng audit/outbox.
- Foreign key action tạo thêm DML.
- Transaction/commit records.

Ngược lại, một WAL record không tương đương một row hoặc một SQL statement. WAL mô tả các thay đổi vật lý/logic nội bộ cần cho recovery, không lưu lại SQL text như query log.

### 2.7. Rollback cũng có thể tạo WAL

Một transaction thay đổi page rồi ROLLBACK không làm các WAL bytes đã phát sinh biến mất. Rollback thường ghi các transaction/status records và các thay đổi phát sinh trong quá trình undo theo cơ chế PostgreSQL; data changes của transaction không trở thành committed business state, nhưng WAL stream vẫn đã tiến lên.

Vì vậy không thể thử một UPDATE lớn rồi ROLLBACK và coi thao tác đó là miễn phí về WAL/I/O.

---

## 3. WAL record: đơn vị ghi log

### 3.1. Một record mô tả điều gì?

Một WAL record có thể mô tả một hành động cần redo, ví dụ:

- Tạo/sửa/xóa tuple trong heap.
- Thay đổi cấu trúc B-tree page.
- Thay đổi transaction status.
- Thay đổi metadata relation/database/tablespace.
- Ghi nhận checkpoint hoặc sự kiện điều khiển WAL.
- Các hoạt động liên quan standby, replication origin hoặc logical decoding.

Mỗi record được xử lý bởi **resource manager** (RMGR) phù hợp. Resource manager biết cách diễn giải record và thực hiện redo tương ứng.

### 3.2. Cấu trúc khái quát

Một WAL record có phần header và payload. Ở mức khái niệm, có thể hình dung:

~~~text
+--------------------------------------------------+
| WAL record header                                |
| - total record length                            |
| - previous record pointer (xl_prev)              |
| - transaction ID (xid, nếu phù hợp)              |
| - resource manager ID                            |
| - info flags                                     |
| - CRC/checksum                                   |
+--------------------------------------------------+
| Block references / relation identifiers         |
| - tablespace/database/relation identity          |
| - fork and block number                          |
| - image metadata nếu có                          |
+--------------------------------------------------+
| Record-specific data                             |
| - heap/btree/transaction/control payload          |
+--------------------------------------------------+
~~~

Đây là sơ đồ khái niệm, không phải cấu trúc C ABI đầy đủ để tự parse mọi PostgreSQL version. Các trường cụ thể, alignment, block reference layout và format thay đổi theo source/version.

### 3.3. Header fields

Các trường thường được nhắc trong source/documentation:

- `xl_tot_len`: tổng chiều dài record.
- `xl_xid`: transaction ID liên quan khi có.
- `xl_prev`: LSN của WAL record trước đó theo chain của WAL insertion order.
- `xl_info`: các info flags phụ thuộc resource manager.
- `xl_rmid`: resource manager ID.
- `xl_crc`: checksum của record theo format/version.

Không phải trường nào cũng có ý nghĩa nghiệp vụ trong mọi record. Một số records không thuộc transaction cụ thể hoặc có xid invalid.

### 3.4. Resource manager (RMGR)

RMGR phân loại records theo subsystem xử lý. Tên/ID có thể khác theo version, nhưng những nhóm thường gặp gồm:

| Nhóm | Vai trò khái quát |
|---|---|
| XLOG | Checkpoint, WAL control và các sự kiện hệ thống |
| XACT | Transaction commit/abort và trạng thái liên quan |
| HEAP | Thay đổi heap tuples/pages |
| HEAP2 | Một số hoạt động heap bổ sung như visibility/pruning/multi-insert |
| BTREE | Thay đổi B-tree indexes |
| SEQ | Sequence operations |
| SMGR | Storage manager/relation file operations |
| Database/Tablespace | Metadata liên quan database/tablespace |
| MULTIXACT | Multi-transaction state |
| STANDBY | Lock/standby-related records |
| Logical message/origin | Thông tin liên quan logical decoding/replication |

Danh sách trên mang tính minh họa. Không hardcode RMGR numeric IDs hoặc kỳ vọng mọi version có cùng danh sách.

### 3.5. Block references

Một record có thể tham chiếu một hoặc nhiều data blocks. Những thông tin liên quan có thể xác định relation, fork và block number, cùng payload delta hoặc full-page image khi phù hợp.

Một SQL UPDATE một tuple có thể cần ghi record liên quan heap và index; một thao tác B-tree split có thể liên quan nhiều blocks. Vì vậy số WAL records không bằng số rows.

### 3.6. Full-page image (FPI)

Khi `full_page_writes` được bật, lần đầu sửa một page sau checkpoint trong các trường hợp phù hợp có thể ghi full-page image vào WAL. FPI giúp bảo vệ khỏi torn-page writes trong crash scenarios.

FPI có thể làm một record lớn hơn nhiều so với delta chỉ mô tả vài bytes thay đổi. WAL compression có thể giảm kích thước FPI trong điều kiện hỗ trợ, nhưng không làm mất mục tiêu bảo vệ crash recovery.

### 3.7. CRC và kiểm tra integrity

Record có checksum/CRC để phát hiện corruption trong WAL record. Cơ chế cụ thể và thuật toán phụ thuộc version/build. Checksum WAL không phải chữ ký mật mã và không thay encryption/authentication của network hoặc archive storage.

### 3.8. Record có thể trải qua nhiều WAL pages

WAL records không nhất thiết nằm trọn trong một WAL page. Record có thể tiếp tục qua page boundary, và các page header/continuation metadata giúp đọc lại record. Vì vậy offset LSN và segment boundaries phải được xử lý theo quy tắc WAL, không tự cộng trừ byte dựa trên giả định record nằm trong một page.

---

## 4. WAL page và WAL segment

### 4.1. WAL page

WAL stream được tổ chức thành các pages. Trong build PostgreSQL phổ biến, WAL page thường có kích thước 8 KiB; kích thước page phụ thuộc build-time configuration. Mỗi page có header chứa thông tin điều khiển như địa chỉ WAL page/timeline và metadata cần thiết để đọc tiếp.

Một WAL record có thể bắt đầu ở page này và tiếp tục sang page kế tiếp.

### 4.2. WAL segment là gì?

**WAL segment** là file vật lý chứa một dải liên tiếp của WAL stream. PostgreSQL tạo/ghi/recycle các segment theo thứ tự, thay vì tạo một file mới cho mỗi SQL statement hay transaction.

Kích thước segment được chọn khi khởi tạo cluster bằng `initdb` (option `--wal-segsize` trên các phiên bản hỗ trợ). Giá trị mặc định thường là 16 MiB, nhưng cluster có thể được khởi tạo với kích thước khác.

### 4.3. Segment không phải transaction

Một segment có thể chứa records của nhiều transactions. Một transaction có thể tạo records trải qua nhiều segments. Một segment cũng có thể chứa phần records chưa commit và records của các transactions đã commit khác.

Không thể nhìn một WAL segment và kết luận nó tương ứng một transaction hoặc một bảng.

### 4.4. Tên file WAL

Tên segment trong `pg_wal` thường là một chuỗi hex 24 ký tự, chia thành ba phần:

~~~text
TTTTTTTT LLLLLLLL SSSSSSSS
|        |        |
|        |        +-- segment number trong log
|        +----------- log ID
+-------------------- timeline ID
~~~

Ví dụ minh họa:

~~~text
00000001000000000000000A
~~~

Trong tên ví dụ:
- `00000001` là timeline ID.
- `00000000` là log ID.
- `0000000A` là segment number.

Tên cụ thể phản ánh timeline và vị trí trong WAL numbering scheme. Không đổi tên file hoặc suy ra LSN bằng cách parse text một cách tùy tiện.

### 4.5. Segment size và tính toán số segments

Nếu segment size là 16 MiB và WAL phát sinh 160 MiB, về mặt dung lượng logic có thể tương đương khoảng 10 segment-worth of WAL. Nhưng số file đang nằm trong `pg_wal` không nhất thiết là 10: PostgreSQL có thể giữ segment đã recycle, giữ thêm vì checkpoint/slots/archive hoặc đang dùng segment hiện tại.

### 4.6. WAL rotation và segment switch

Khi WAL stream tiến tới cuối segment, PostgreSQL chuyển sang segment tiếp theo. Segment switch cũng có thể được yêu cầu bởi một số thao tác/setting hoặc hàm quản trị như `pg_switch_wal()`.

~~~sql
SELECT pg_switch_wal();
~~~

Hàm này yêu cầu chuyển sang WAL segment tiếp theo theo điều kiện server. Nó không phải cách giảm dung lượng `pg_wal`, cũng không nên gọi liên tục chỉ để tạo nhiều archive files nhỏ hơn.

### 4.7. Recycle và reuse

Sau khi segment không còn cần thiết cho recovery/replication/archive, PostgreSQL có thể recycle/reuse segment thay vì xóa và tạo file mới. Vì vậy:
- WAL generation tăng không nhất thiết làm số file tăng mãi.
- `pg_wal` directory size không trực tiếp bằng WAL bytes sinh ra trong một khoảng thời gian.
- Segment cũ có thể được tái sử dụng theo vị trí tương lai.
- Retention do slots/archive có thể ngăn cleanup/recycle.

### 4.8. Archive segment

Nếu archiving được bật, WAL segments hoàn tất có thể được chuyển tới archive destination theo archive command/provider. Archive segment dùng cho backup/PITR và có retention policy riêng. Không được xóa một archived segment khi backup chain còn cần nó.

---

## 5. LSN: địa chỉ trong WAL stream

### 5.1. LSN là gì?

**Log Sequence Number** xác định một vị trí byte trong WAL stream. PostgreSQL thường hiển thị LSN ở dạng:

~~~text
HEX/HEX
~~~

Ví dụ:

~~~text
0/16B6C50
0/16C4200
~~~

LSN là địa chỉ logic, không phải timestamp, transaction ID, row ID hoặc segment file name.

### 5.2. Định dạng high/low 32-bit

Biểu diễn phổ biến `X/Y` tương ứng hai phần hex 32-bit:
- Phần trước slash là high 32 bits.
- Phần sau slash là low 32 bits.

Có thể hình dung giá trị byte offset 64-bit:

\[
LSN = (\text{high}_{32} \ll 32) + \text{low}_{32}
\]

Đây là cách hiểu số học của representation; khi viết SQL nên dùng kiểu `pg_lsn` và hàm PostgreSQL thay vì tự parse text.

### 5.3. LSN tăng theo WAL insertion order

Trên một timeline WAL, record mới được insert ở vị trí sau các records trước đó trong luồng. LSN cho phép xác định thứ tự vị trí WAL trên timeline.

Điều này **không** có nghĩa transaction IDs tăng theo cùng thứ tự commit, cũng không có nghĩa mọi records của một transaction nằm liền nhau.

### 5.4. Tính khoảng cách LSN

~~~sql
SELECT pg_wal_lsn_diff(
    '0/16C4200'::pg_lsn,
    '0/16B6C50'::pg_lsn
) AS wal_bytes;
~~~

Hàm trả khoảng cách byte giữa hai LSN (LSN thứ nhất trừ LSN thứ hai). Hai giá trị trên là ví dụ minh họa; dùng LSN thực tế của server để tính.

Chuyển sang MiB:

~~~sql
SELECT pg_wal_lsn_diff(
    '0/16C4200'::pg_lsn,
    '0/16B6C50'::pg_lsn
) / 1024 / 1024 AS wal_mib;
~~~

### 5.5. Kiểu pg_lsn

`pg_lsn` là kiểu dữ liệu PostgreSQL dành cho LSN. Nó hỗ trợ các phép so sánh và arithmetic phù hợp; dùng kiểu này giúp tránh lỗi xử lý chuỗi hex bằng application code.

Ví dụ:

~~~sql
SELECT
    '0/2000000'::pg_lsn > '0/1000000'::pg_lsn AS later_position;
~~~

### 5.6. LSN không phải timestamp

Một LSN lớn hơn có nghĩa vị trí WAL ở sau trong luồng/timeline tương ứng, không có nghĩa một khoảng thời gian cụ thể đã trôi qua. WAL rate thay đổi theo workload; 100 MiB WAL có thể được tạo trong một giây hoặc nhiều phút.

Muốn biết thời gian, cần kết hợp timestamps, monitoring samples và LSN deltas.

### 5.7. LSN không phải transaction ID

Transaction ID (XID) phục vụ nhận diện transaction/MVCC, có wraparound semantics và các loại XID đặc biệt. LSN đánh địa chỉ WAL byte stream. Một transaction có thể có nhiều WAL records tại nhiều LSNs, và các transactions interleave records.

### 5.8. LSN không phải row version

LSN không trực tiếp nhận diện một row hoặc tuple version. Page LSN và WAL records giúp recovery/redo, còn tuple identity/version cần các thông tin heap/block/offset và MVCC metadata.

---

## 6. Các LSN positions PostgreSQL cung cấp

### 6.1. Current insert LSN

~~~sql
SELECT pg_current_wal_insert_lsn();
~~~

Vị trí WAL insertion hiện tại theo góc nhìn server. Nó có thể đi trước write/flush positions vì WAL đã được insert vào buffers nhưng chưa được ghi/flush tương ứng.

### 6.2. Current write LSN

~~~sql
SELECT pg_current_wal_lsn();
~~~

Hàm thường dùng để lấy vị trí WAL đã được written theo semantics PostgreSQL. Đừng gọi nó là “flush LSN” nếu đang so với hàm flush riêng.

### 6.3. Current flush LSN

~~~sql
SELECT pg_current_wal_flush_lsn();
~~~

Vị trí WAL đã được flush theo trạng thái server. Đây là mốc quan trọng khi xem durability/replication progress, nhưng không nên diễn giải đơn giản là mọi transaction trước LSN đều commit; luồng WAL còn chứa records của các transactions khác và các sự kiện không thuộc commit.

### 6.4. So sánh ba positions

~~~sql
SELECT
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_lsn() AS write_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
~~~

Thông thường:
- Insert position có thể cao hơn write position.
- Write position có thể cao hơn flush position.
- Khi hệ thống idle hoặc WAL writer/backend đã đồng bộ, các positions có thể gần nhau hoặc trùng nhau.

Không coi chênh lệch nhỏ/lớn là lỗi nếu chưa hiểu load, write/flush behavior và sample timing.

### 6.5. Insert, write, flush khác nhau

| Position | Ý nghĩa |
|---|---|
| Insert | Record đã được chèn vào WAL buffers/stream position |
| Write | WAL bytes đã được ghi tới OS/file layer theo semantics server |
| Flush | WAL đã được flush theo durability path của server |

`write` không đồng nghĩa data page đã ghi; `flush` của WAL không đồng nghĩa mọi dirty data pages đã flush.

### 6.6. LSN của session hiện tại?

Các hàm current WAL LSN thường phản ánh WAL stream toàn server, không phải WAL bytes riêng của session hiện tại. Khi nhiều transactions đồng thời, LSN delta giữa hai lần đo bao gồm hoạt động chung của cluster.

### 6.7. Đo WAL delta trong workload

Mẫu đơn giản:

~~~sql
SELECT pg_current_wal_lsn() AS before_lsn;

-- Chạy workload đã xác định và COMMIT.

SELECT pg_current_wal_lsn() AS after_lsn;
~~~

Sau đó tính:

~~~sql
SELECT pg_wal_lsn_diff(
    'AFTER_LSN'::pg_lsn,
    'BEFORE_LSN'::pg_lsn
);
~~~

Thay placeholders bằng LSN thực tế. Để attribution tốt hơn, đo trong môi trường cô lập hoặc workload window ít writes đồng thời. Kết quả là khoảng cách WAL stream, không tự chứng minh bytes do một SQL statement cụ thể tạo ra.

### 6.8. LSN và segment file name

Có thể hỏi PostgreSQL segment name tương ứng với một LSN:

~~~sql
SELECT pg_walfile_name('0/16C4200'::pg_lsn);
~~~

Và xem segment name cùng offset:

~~~sql
SELECT *
FROM pg_walfile_name_offset('0/16C4200'::pg_lsn);
~~~

Kết quả phụ thuộc segment size/timeline và LSN thực tế. Đây là cách an toàn hơn tự tính tên file từ chuỗi hex.

---

## 7. Page LSN và quan hệ với data pages

### 7.1. Page LSN là gì?

Một data page PostgreSQL có header chứa `pd_lsn` (page LSN): vị trí WAL record cuối cùng đã được áp dụng lên page đó theo cơ chế storage/recovery.

Trong một heap/index page:
- Một WAL record có thể thay đổi page.
- Khi thay đổi được áp dụng, page LSN được cập nhật theo record liên quan.
- Khi recovery redo đọc WAL, server có thể so page LSN với record LSN để biết page đã chứa thay đổi đó hay chưa.

### 7.2. Vì sao page LSN hữu ích?

Giả sử crash xảy ra sau khi một page đã được ghi xuống disk, nhưng WAL chứa record tương ứng vẫn nằm trong redo range. Recovery cần tránh áp dụng một số thay đổi đã có hiệu lực lên page lần nữa. Page LSN là một trong các thông tin quan trọng giúp xác định điều kiện redo.

Chi tiết redo decisions phụ thuộc loại record/resource manager; không phải mọi record đều được xử lý bằng một so sánh đơn giản duy nhất.

### 7.3. Page LSN không phải commit LSN

Một page có thể chứa updates từ nhiều transactions. Page LSN biểu thị WAL position cuối cùng áp dụng lên page, không phải transaction commit cuối cùng của mọi rows trên page.

### 7.4. Một transaction thay đổi nhiều pages

UPDATE một row có thể chạm heap page và index pages. Những pages đó có thể có page LSN khác nhau. Commit record có LSN riêng; không có một page LSN chung đại diện cho transaction.

### 7.5. Page LSN và torn-page protection

Full-page images ghi vào WAL sau checkpoint trong những trường hợp phù hợp giúp recovery khôi phục page nếu data page bị torn write. Page LSN và FPI là hai phần trong cơ chế WAL/recovery; đừng tắt `full_page_writes` để giảm log mà không hiểu rủi ro.

---

## 8. Thứ tự thay đổi: record order, transaction order và commit order

### 8.1. Một WAL stream có thứ tự toàn cục

Trên một timeline, WAL records được đặt vào stream theo thứ tự LSN. Nếu record A ở LSN thấp hơn record B, A xuất hiện trước B trong WAL stream.

Nhưng các transactions có thể chạy đồng thời. Records của chúng có thể **xen kẽ** trong luồng.

### 8.2. Ví dụ hai transactions xen kẽ

~~~text
WAL LSN order:

LSN 100  T1: UPDATE orders row A
LSN 200  T2: UPDATE inventory row B
LSN 300  T1: UPDATE audit row
LSN 400  T2: UPDATE inventory row C
LSN 500  T2: COMMIT
LSN 600  T1: COMMIT
~~~

Sơ đồ giả lập này cho thấy T1 không chiếm một vùng liên tục duy nhất. Transaction T2 có thể ghi records giữa những records của T1. Commit order ở ví dụ là T2 trước T1 dù T1 bắt đầu trước.

### 8.3. Start order không bằng commit order

Transaction bắt đầu trước có thể hoàn tất sau. XID assignment order cũng không phải một cơ chế tổng quát để sắp thứ tự commit. Muốn biết một transaction đã commit tại vị trí nào trong WAL cần hiểu commit record/transaction status, không chỉ nhìn XID.

### 8.4. Commit record

Khi transaction commit, PostgreSQL ghi record liên quan commit vào WAL. Commit record là bằng chứng WAL về việc transaction hoàn tất; COMMIT được client xác nhận theo durability policy sau khi các điều kiện flush/replication tương ứng được đáp ứng.

Transaction có thể đã tạo nhiều WAL records trước commit; commit record không gom toàn bộ thay đổi thành một record đơn.

### 8.5. Một transaction có thể không tạo WAL data records?

Read-only transaction thường không tạo heap/index modification records; vẫn có thể có những hoạt động/session/transaction-related records tùy tình huống. Không suy mọi transaction đều tạo một lượng WAL như nhau.

### 8.6. Transaction không có một LSN duy nhất cho mọi thay đổi

Một transaction có:
- Nhiều WAL records cho các thao tác.
- Có thể interleave với records của transactions khác.
- Một commit/abort record liên quan.
- Một commit LSN có thể được quan tâm cho replication/commit ordering.

Vì vậy “LSN của transaction” thường cần nói rõ đang đề cập record nào, commit LSN hay một vị trí snapshot/watermark được application chọn.

### 8.7. Thứ tự WAL không thay thế isolation semantics

WAL là cơ chế persistence/recovery/replication. Thứ tự record không thay thế transaction isolation, row locks, MVCC snapshots hoặc serialization rules. Hai transactions có thể có WAL records theo một thứ tự nhưng SQL visibility giữa concurrent sessions vẫn tuân theo MVCC/isolation.

### 8.8. Một SQL statement có thể tạo record ở nhiều thời điểm

Các thao tác phục vụ transaction/commit/cleanup/control có thể ghi records ở nhiều thời điểm trong statement/transaction lifecycle. Không giả định mọi WAL records của một SQL statement nằm đúng một đoạn trước một mốc cố định, đặc biệt khi có triggers, indexes, concurrent transactions và commit processing.

---

## 9. Thứ tự write, flush và COMMIT

### 9.1. Write khác flush

- **Write:** dữ liệu WAL được gửi tới OS/file layer.
- **Flush:** đảm bảo WAL tới mức bền vững mà PostgreSQL yêu cầu qua sync method/storage stack.
- **COMMIT acknowledgement:** server trả kết quả commit cho client theo synchronous_commit và replication configuration.

Không đồng nhất ba mốc này.

### 9.2. Durability với synchronous_commit mặc định

Với cấu hình durability thông thường, PostgreSQL không xác nhận COMMIT trước khi WAL cần cho transaction được flush tới persistent storage theo policy. Các data pages có thể được ghi về sau; crash recovery sẽ redo chúng.

### 9.3. synchronous_commit=off

Setting này có thể cho phép server acknowledge commit trước khi WAL tương ứng được flush, giảm latency trong một số workloads nhưng chấp nhận rủi ro mất những recent acknowledged transactions nếu server crash. WAL vẫn được tạo; setting không tắt WAL.

### 9.4. Synchronous replication

Nếu cấu hình synchronous standby, synchronous_commit có các modes ảnh hưởng loại xác nhận cần chờ (local flush, remote write/flush/apply theo mode và version). Tùy cấu hình, commit latency có thể phụ thuộc standby.

Không suy COMMIT thành công ở client nghĩa là mọi replica đã replay transaction, trừ khi policy/setting thực sự yêu cầu và xác nhận mức đó.

### 9.5. Group commit

Nhiều transactions có thể cùng chờ flush; PostgreSQL có thể flush WAL một lần cho một nhóm commits. Đây là **group commit**, giúp giảm số lần sync storage so với việc từng transaction tự flush riêng.

Group commit không làm các transactions trở thành một transaction chung và không thay đổi atomicity của chúng.

### 9.6. WAL writer và backend flush

WAL có thể được write/flush bởi backend process hoặc WAL writer theo cơ chế nội bộ và thời điểm phù hợp. Các parameters như wal_writer_delay, wal_writer_flush_after, wal_buffers và wal_sync_method ảnh hưởng behavior; tune chúng cần benchmark và hiểu durability.

### 9.7. Lost response sau COMMIT

Nếu server commit và flush thành công nhưng connection mất trước khi client nhận response, client có thể không biết transaction đã commit hay chưa. Đây là **unknown commit outcome**. Retry business operation cần idempotency key/unique constraint/reconciliation, không thể chỉ dựa vào socket error.

---

## 10. Checkpoint và redo start point

### 10.1. Checkpoint làm gì?

Checkpoint là sự kiện PostgreSQL bảo đảm các dirty pages cần thiết trước mốc checkpoint được ghi xuống data files theo cơ chế checkpoint. Checkpoint record và control information ghi nhận trạng thái cần cho crash recovery.

Sau crash, PostgreSQL không cần replay WAL từ đầu lịch sử database; nó bắt đầu redo từ điểm phù hợp dựa trên checkpoint.

### 10.2. Checkpoint record

WAL có records thuộc resource manager XLOG liên quan checkpoint/control. Checkpoint metadata lưu thông tin như redo pointer và các state cần thiết. Cấu trúc nội bộ phụ thuộc version; không tự parse bằng offsets hardcoded.

### 10.3. Redo LSN

Redo pointer cho biết vị trí WAL từ đó recovery cần bắt đầu xét redo. Nó không nhất thiết là vị trí cuối cùng của WAL trước crash, và không nhất thiết trùng LSN của checkpoint record.

### 10.4. Checkpoint không phải COMMIT

- COMMIT đánh dấu transaction hoàn tất.
- Checkpoint thiết lập mốc recovery và đồng bộ dirty data pages.
- Một transaction có thể commit trước checkpoint kế tiếp.
- Một checkpoint có thể bao gồm data pages từ nhiều transactions đã commit và một số thay đổi đang có trong buffers theo quy tắc recovery.

### 10.5. Checkpoint không có nghĩa WAL segment cũ luôn bị xóa ngay

WAL segments cũ có thể còn cần:
- Archive hoàn tất.
- Standby/replication slot.
- wal_keep_size hoặc các retention requirements.
- Recovery/backup policy.
- Một số điều kiện nội bộ khác.

Checkpoint có thể làm một phần WAL không còn cần cho crash recovery local, nhưng không tự bảo đảm segment bị xóa ngay.

### 10.6. Checkpoint frequency và WAL volume

Checkpoint thường xuyên có thể làm tăng I/O burst và full-page image volume sau checkpoint. checkpoint_timeout, max_wal_size, checkpoint_completion_target và workload cùng ảnh hưởng. Không tăng/giảm tùy tiện chỉ dựa trên một lần thấy nhiều segments.

### 10.7. Checkpoint và full_page_writes

Với full_page_writes=on, lần đầu page được sửa sau checkpoint trong các trường hợp phù hợp có thể cần FPI. Điều này giúp bảo vệ recovery nhưng có thể làm WAL bytes tăng mạnh ngay sau checkpoint. Giảm FPI bằng cách tắt full_page_writes là trade-off nguy hiểm, không phải tối ưu mặc định.

### 10.8. Kiểm tra checkpoint stats

Trên các PostgreSQL versions mới, checkpoint metrics có thể xuất hiện trong pg_stat_checkpointer; ở các phiên bản trước, một số thông tin nằm trong pg_stat_bgwriter. Hãy xem đúng view/schema theo major version.

---

## 11. Timeline: lịch sử WAL sau failover

### 11.1. Vì sao có timeline?

Khi một standby được promote thành primary, lịch sử ghi WAL có thể rẽ nhánh khỏi primary cũ. PostgreSQL dùng **timeline ID** để phân biệt các nhánh lịch sử.

### 11.2. Timeline history file

Sau timeline switch, history file mô tả quan hệ lịch sử và vị trí fork của timeline mới. File này quan trọng khi restore/PITR hoặc thiết lập standby theo timeline.

### 11.3. LSN có thể trùng giữa timelines

Một LSN chỉ có ý nghĩa đầy đủ trong context timeline/history. Hai timelines khác nhau có thể có vị trí LSN giống nhau nhưng không đại diện cùng một history sau điểm fork.

Vì vậy trong HA/recovery, không so LSN đơn lẻ mà bỏ qua timeline.

### 11.4. WAL segment filename chứa timeline ID

Phần đầu của tên WAL segment biểu thị timeline ID. Khi promotion, tên segment của timeline mới phản ánh nhánh lịch sử mới; các segments từ timeline trước vẫn có thể cần cho recovery chain.

### 11.5. Timeline không phải database ID

Timeline phân biệt nhánh lịch sử WAL, không phải database OID, cluster name hoặc transaction ID. Một PostgreSQL cluster có thể có nhiều database nhưng chia sẻ cùng WAL stream/timeline.

---

## 12. Streaming replication và LSN positions

### 12.1. Primary gửi WAL cho standby

Physical streaming replication truyền WAL stream từ primary tới standby. Standby có thể:
1. Nhận WAL bytes.
2. Ghi WAL vào local WAL files.
3. Flush WAL theo state.
4. Replay WAL để áp dụng thay đổi lên data files.

### 12.2. Các LSN trong pg_stat_replication

Trên primary:

~~~sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

Các positions thường được diễn giải:
- sent_lsn: vị trí WAL sender đã gửi.
- write_lsn: vị trí standby đã ghi WAL.
- flush_lsn: vị trí standby đã flush WAL.
- replay_lsn: vị trí standby đã replay WAL.

Chi tiết semantics/counters và lag fields thay đổi theo version; xem tài liệu server.

### 12.3. Chênh lệch bytes

~~~sql
SELECT
    application_name,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)::bigint
    ) AS approximate_bytes_behind
FROM pg_stat_replication
WHERE replay_lsn IS NOT NULL;
~~~

Đây là ước lượng khoảng cách WAL stream giữa primary current position và standby replay position. Nó không phải trực tiếp “số rows chậm” hoặc thời gian chính xác.

### 12.4. Standby nhận nhưng chưa replay

Nếu write_lsn/flush_lsn tiến nhanh nhưng replay_lsn đứng lại, network/receive có thể ổn nhưng apply/replay đang chậm. Kiểm tra standby CPU/I/O, long-running queries/hot standby conflicts, WAL record processing và storage.

### 12.5. Standby nhận chậm

Nếu sent_lsn đi xa trước write_lsn, có thể có network/receiver/storage bottleneck. Kiểm tra network, replication connection, standby WAL write latency và resource contention.

### 12.6. Standby query

Trên standby:

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_commit_time;
~~~

Timestamp commit replay cuối cùng có thể NULL/cũ khi primary không phát sinh transactions mới. Kết hợp LSNs, heartbeat và workload expectations để đo lag.

### 12.7. WAL streaming không phải logical row stream

Physical replication gửi WAL để standby tái tạo trạng thái vật lý phù hợp. Nó không gửi các SQL statements/JSON events ở business level. Logical replication/decoding diễn giải row changes theo cơ chế khác và có semantics riêng.

---

## 13. WAL archive và recovery chain

### 13.1. Archive WAL segment

Khi một WAL segment hoàn tất và đủ điều kiện archive, PostgreSQL gọi archive mechanism để lưu segment tới nơi lưu trữ lâu dài theo cấu hình. Archive thường dùng cùng base backup cho PITR.

### 13.2. Archive không phải copy live segment tùy tiện

Một segment đang được ghi không nên được tự copy/xử lý như archive file hoàn chỉnh. PostgreSQL quản lý segment switch/archiving theo cơ chế để archive nhận một segment hoàn chỉnh và có thể kiểm tra/đảm bảo semantics.

### 13.3. pg_stat_archiver

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Counters cho biết trạng thái archiver, không phải toàn bộ archive inventory. Kết hợp với destination logs, backup metadata và kiểm thử restore.

### 13.4. Archive command fail

Nếu archiving thất bại, WAL có thể tiếp tục được giữ trong pg_wal để thử lại/đảm bảo recovery. Disk có thể tăng. Không xóa segment chưa archive chỉ để giải phóng disk.

### 13.5. PITR cần một chuỗi hợp lệ

Để phục hồi tới một thời điểm, cần base backup và chuỗi WAL liên tục phù hợp từ backup tới target. Thiếu một segment cần thiết có thể khiến recovery dừng trước target. Backup success không nên chỉ đánh giá bằng việc file archive xuất hiện; phải kiểm tra khả năng restore.

---

## 14. Quan sát WAL bằng SQL và công cụ

### 14.1. Current LSN positions

~~~sql
SELECT
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_lsn() AS write_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
~~~

Đây là các vị trí toàn cluster. Role cần quyền phù hợp để gọi các hàm; behavior khi chạy trên standby khác primary.

### 14.2. WAL file name

~~~sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS current_segment;
~~~

Hàm file name ánh xạ LSN sang segment name theo segment size/timeline. Nó không cho biết segment đã archive hay không.

### 14.3. LSN và offset trong segment

~~~sql
SELECT *
FROM pg_walfile_name_offset(pg_current_wal_lsn());
~~~

Kết quả gồm segment file name và byte offset phù hợp. Dùng để định vị segment chứa một LSN, không tự suy file path ngoài thư mục WAL đang cấu hình.

### 14.4. WAL statistics

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    wal_write,
    wal_sync,
    stats_reset
FROM pg_stat_wal;
~~~

View/cột có thể khác version. Các counters là toàn server và có thể bị reset; muốn tính delta cần chụp mốc reset và lấy hai mẫu đúng cách.

### 14.5. pg_waldump

pg_waldump là command-line utility đọc và hiển thị WAL records trong các WAL segment, hữu ích cho phân tích low-level. Tên, options và khả năng lọc phụ thuộc phiên bản.

Ví dụ dạng tổng quát:

~~~bash
pg_waldump --path=/path/to/pg_wal --start=0/16B6C50 --end=0/16C4200
~~~

Đường dẫn/options trên chỉ minh họa. Hãy dùng binary tương thích với PostgreSQL version của cluster và file WAL hợp lệ. Công cụ này không phải query SQL, không tự thay thế recovery hoặc xác minh backup.

### 14.6. pg_walinspect

Extension pg_walinspect ở những phiên bản hỗ trợ cung cấp SQL functions để inspect WAL records/statistics. Các hàm phổ biến ở version hiện đại có thể gồm:
- pg_get_wal_record_info(lsn)
- pg_get_wal_records_info(start_lsn, end_lsn)
- pg_get_wal_stats(start_lsn, end_lsn)
- pg_get_wal_stats_till_end_of_wal(start_lsn)

Tên, output columns, quyền cần thiết và khả năng extension phụ thuộc version. Chỉ cài extension theo policy/DBA, không tự cấp quyền rộng cho application.

### 14.7. Không dump WAL bừa bãi

WAL record inspection có thể lộ thông tin nhạy cảm trong page images/record payload, tạo tải I/O/CPU và tạo lượng output lớn. Giới hạn LSN range, lưu output an toàn, redact và chỉ cấp quyền cho người điều tra cần thiết.

---

## 15. Thứ tự WAL trong ví dụ cụ thể

### 15.1. Tạo bảng lab

~~~sql
CREATE SCHEMA IF NOT EXISTS wal_order_lab;

CREATE TABLE wal_order_lab.accounts (
    account_id bigint PRIMARY KEY,
    balance numeric(12,2) NOT NULL
);

INSERT INTO wal_order_lab.accounts(account_id,balance)
VALUES (1,1000.00),(2,500.00);
~~~

Đây là bảng lab. Những SQL statements trên tạo nhiều hoạt động nội bộ/WAL records; không thể giả định mỗi INSERT row tương ứng đúng một record.

### 15.2. Đo mốc trước

~~~sql
SELECT
    pg_current_wal_insert_lsn() AS before_insert,
    pg_current_wal_lsn() AS before_write,
    pg_current_wal_flush_lsn() AS before_flush;
~~~

Ghi lại output thực tế.

### 15.3. Một transaction cập nhật hai accounts

~~~sql
BEGIN;

UPDATE wal_order_lab.accounts
SET balance=balance-100.00
WHERE account_id=1;

UPDATE wal_order_lab.accounts
SET balance=balance+100.00
WHERE account_id=2;

COMMIT;
~~~

Transaction thực hiện hai row updates. Các WAL records có thể bao gồm heap/index/transaction records và các hoạt động liên quan.

### 15.4. Đo mốc sau

~~~sql
SELECT
    pg_current_wal_insert_lsn() AS after_insert,
    pg_current_wal_lsn() AS after_write,
    pg_current_wal_flush_lsn() AS after_flush;
~~~

Tính khoảng cách bằng LSN thực tế:

~~~sql
SELECT pg_wal_lsn_diff(
    'AFTER_WRITE_LSN'::pg_lsn,
    'BEFORE_WRITE_LSN'::pg_lsn
) AS bytes_between_samples;
~~~

Nếu workload khác đồng thời ghi WAL, delta bao gồm những records đó. Không thể dùng nó để khẳng định transaction accounts riêng tạo chính xác bao nhiêu bytes.

### 15.5. Quan sát transaction consistency

~~~sql
SELECT account_id,balance
FROM wal_order_lab.accounts
ORDER BY account_id;
~~~

Sau COMMIT, tổng balance của hai rows vẫn là 1.500.00. Hai UPDATE được commit atomically trong một transaction; reader không thấy trạng thái chỉ một nửa được commit khi tuân thủ MVCC.

### 15.6. Rollback lab

Nếu muốn thử lại từ đầu:

~~~sql
BEGIN;
UPDATE wal_order_lab.accounts
SET balance=balance-10
WHERE account_id=1;
ROLLBACK;
~~~

Dữ liệu cuối không giữ thay đổi, nhưng WAL vẫn có thể tăng. Không coi rollback là xóa các WAL records.

---

## 16. Segment rotation và quan sát tên file

### 16.1. Xem segment hiện tại

~~~sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS current_wal_file;
~~~

### 16.2. Yêu cầu switch trong lab

~~~sql
SELECT pg_switch_wal();
~~~

Kết quả là LSN liên quan switch theo hàm; behavior phụ thuộc trạng thái hiện tại và server. Chỉ thực hiện khi cần lab/maintenance; gọi liên tục có thể làm tăng số segments/archive workload.

### 16.3. Đọc tên segment

~~~sql
SELECT pg_walfile_name('0/3000000'::pg_lsn);
~~~

LSN giả định này có thể ánh xạ tới segment khác nhau tùy timeline/segment size và vị trí hiện tại; dùng current LSN thực tế trong lab.

### 16.4. Kiểm tra segment size

PostgreSQL có hàm pg_size_bytes để parse kích thước config string, nhưng không có một hàm SQL portable duy nhất cho mọi version/provider để lấy segment size trong mọi bối cảnh. Thông tin segment size là đặc tính cluster/initdb; có thể xem qua control data/tool phù hợp hoặc metadata triển khai. Đừng giả định mọi cluster đều 16 MiB.

### 16.5. Vì sao pg_wal có nhiều file cũ?

Các segments có thể được giữ vì:
- Chưa đủ điều kiện recycle.
- Cần cho archive.
- Replication slot giữ restart LSN cũ.
- Standby không theo kịp.
- wal_keep_size/retention settings.
- Checkpoint/recovery cần.
- PostgreSQL giữ một số segments để reuse.

Hãy quan sát slots, archiver, replication và disk; không xóa files bằng tay.

---

## 17. Thứ tự thay đổi và transaction atomicity

### 17.1. Một transaction nhiều statements

~~~sql
BEGIN;

UPDATE wal_order_lab.accounts
SET balance=balance-100
WHERE account_id=1;

UPDATE wal_order_lab.accounts
SET balance=balance+100
WHERE account_id=2;

COMMIT;
~~~

WAL records được tạo trong quá trình hai UPDATE và transaction completion. Khi COMMIT thành công theo durability policy, cả hai changes thuộc một transaction hoàn tất.

### 17.2. Transaction lỗi

~~~sql
BEGIN;

UPDATE wal_order_lab.accounts
SET balance=balance-100
WHERE account_id=1;

SELECT 1/0;

UPDATE wal_order_lab.accounts
SET balance=balance+100
WHERE account_id=2;

COMMIT;
~~~

Sau division_by_zero, transaction bị abort; UPDATE thứ hai và COMMIT thông thường không thể hoàn tất như dự định. Caller phải ROLLBACK. WAL records đã phát sinh trước lỗi vẫn có thể tồn tại; data changes không commit.

### 17.3. Savepoint

~~~sql
BEGIN;

UPDATE wal_order_lab.accounts
SET balance=balance-10
WHERE account_id=1;

SAVEPOINT optional_step;

-- Nếu một thao tác trong vùng savepoint lỗi:
ROLLBACK TO SAVEPOINT optional_step;

COMMIT;
~~~

Savepoint cho phép rollback một phần trong transaction, nhưng không tạo một transaction độc lập đã commit. Các records liên quan vẫn tồn tại trong WAL; transaction cuối cùng vẫn commit/abort như một unit.

### 17.4. Commit order và visibility

Một transaction chỉ trở nên visible cho những transactions khác theo MVCC sau khi commit. WAL record order hỗ trợ recovery và replication, nhưng visibility còn phụ thuộc snapshot và isolation level.

### 17.5. Không suy commit từ page flush

Data page được flush không tự chứng minh transaction commit. Có thể page chứa tuple từ transaction chưa commit hoặc page chứa nhiều tuples từ các transaction khác nhau. Commit status được xác định qua transaction state/WAL và MVCC, không phải chỉ page LSN.

---

## 18. Những câu hỏi thường gặp

### 18.1. Một WAL segment chứa một transaction?

Không. Một segment chứa một dải WAL stream; nhiều transactions có thể ghi records vào cùng segment, và một transaction có thể trải qua nhiều segments.

### 18.2. Một WAL record tương đương một row?

Không. Record có thể mô tả page-level/index/transaction/control changes. Một row update có thể tạo nhiều records và một record có thể chứa thay đổi liên quan nhiều items/blocks.

### 18.3. LSN tăng nghĩa là transaction mới commit?

Không. LSN tiến khi WAL records được insert; chúng có thể thuộc transactions chưa commit, background operations hoặc control records. Commit record là một sự kiện riêng.

### 18.4. Flush LSN bằng commit LSN?

Không. Flush LSN là vị trí WAL đã flush; commit LSN của transaction là vị trí record commit cụ thể. Flush position có thể tiến qua nhiều record/transaction khác.

### 18.5. Data page chưa ghi nhưng COMMIT trả thành công có an toàn?

Theo durability policy chuẩn, WAL cần thiết đã được flush; crash recovery redo có thể khôi phục page changes. Các setting như synchronous_commit=off thay đổi mức bảo đảm thời điểm acknowledgment.

### 18.6. WAL segment đã archive thì có thể xóa ngay?

Không nhất thiết. PostgreSQL quản lý lifecycle/reuse; archive retention cho PITR cần được giữ theo backup policy. Không tự xóa file trong pg_wal hoặc archive destination.

### 18.7. LSN giống timestamp?

Không. LSN là byte position. Cần timestamps/metrics để ước lượng tốc độ WAL.

### 18.8. XID tăng cùng LSN?

Không có quan hệ đơn giản đảm bảo XID tăng theo mọi LSN hoặc commit order. XID assignment, transaction execution và commit có lifecycle khác nhau.

### 18.9. WAL chỉ chứa data modifications?

Không. Nó còn chứa transaction, checkpoint, storage/catalog và control records cần cho recovery/replication.

### 18.10. Replica nhận WAL là đã query thấy data?

Không. WAL có thể đã received/written/flushed nhưng chưa replay. Query visibility trên standby phụ thuộc replay progress và recovery state.

---

## 19. Checklist đọc WAL và điều tra sự cố

### 19.1. Khi cần hiểu LSN

- [ ] Xác định LSN đang xem là insert, write, flush, receive, replay hay commit LSN.
- [ ] Xác định primary hay standby.
- [ ] Ghi nhận timeline/history khi có failover.
- [ ] Dùng pg_lsn và pg_wal_lsn_diff, không parse chuỗi thủ công.
- [ ] Nhớ LSN delta là cluster-wide nếu có workload đồng thời.

### 19.2. Khi cần hiểu segment

- [ ] Xác định segment size thật của cluster.
- [ ] Đọc filename theo timeline/log/segment numbering.
- [ ] Dùng pg_walfile_name()/pg_walfile_name_offset() nếu phù hợp.
- [ ] Kiểm tra archive/slot/replica retention.
- [ ] Không đổi tên, xóa hoặc copy segment đang active bằng thao tác tùy tiện.

### 19.3. Khi cần hiểu record order

- [ ] Tách record order khỏi transaction start/commit order.
- [ ] Tìm commit/abort records nếu công cụ hỗ trợ.
- [ ] Nhớ records của transactions có thể interleave.
- [ ] Không suy business row identity từ LSN.
- [ ] Dùng tool tương thích version khi decode record.

### 19.4. Khi cần hiểu durability

- [ ] Kiểm tra synchronous_commit.
- [ ] Kiểm tra synchronous replication policy nếu có.
- [ ] Phân biệt WAL write và flush.
- [ ] Phân biệt WAL flush và data-page flush.
- [ ] Kiểm tra fsync, full_page_writes và storage assumptions.
- [ ] Unknown commit outcome phải xử lý bằng idempotency/reconciliation.

### 19.5. Khi cần hiểu checkpoint/recovery

- [ ] Xác định checkpoint/redo LSN.
- [ ] Kiểm tra checkpoint frequency và WAL growth.
- [ ] Xem FPI volume.
- [ ] Kiểm tra archive continuity/PITR.
- [ ] Không xóa segments cần recovery/standby.

---

## 20. Tài liệu tham khảo chính thức

Khi làm việc với một major version cụ thể, ưu tiên tài liệu cùng version:

- [PostgreSQL — Write-Ahead Logging (WAL)](https://www.postgresql.org/docs/current/wal.html): nguyên tắc WAL và crash recovery.
- [PostgreSQL — WAL Internals](https://www.postgresql.org/docs/current/wal-internals.html): WAL records/pages/segments và LSN.
- [PostgreSQL — WAL Configuration](https://www.postgresql.org/docs/current/wal-configuration.html): checkpoint/WAL configuration.
- [PostgreSQL — WAL Reliability](https://www.postgresql.org/docs/current/wal-reliability.html): durability, fsync và write-ahead rules.
- [PostgreSQL — WAL Functions](https://www.postgresql.org/docs/current/functions-admin.html): LSN functions, WAL file naming và administrative functions.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_wal, replication và checkpoint statistics.
- [PostgreSQL — Warm Standby / Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html): send/write/flush/replay và standby behavior.
- [PostgreSQL — Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html): WAL archiving/recovery.
- [PostgreSQL — pg_waldump](https://www.postgresql.org/docs/current/pgwaldump.html): đọc WAL records bằng command-line.
- [PostgreSQL — pg_walinspect](https://www.postgresql.org/docs/current/pgwalinspect.html): inspect WAL bằng SQL extension khi phiên bản hỗ trợ.

Các trang /current/ có thể thay đổi khi PostgreSQL phát hành phiên bản mới. WAL binary format là implementation detail; nếu xây parser hoặc tool phân tích lâu dài, phải version-aware và dựa vào source/docs của đúng release.

---

## 21. Tổng kết

**WAL là một luồng nhị phân có thứ tự, được đánh địa chỉ bằng LSN và lưu vật lý trong các segments.** Hiểu đúng record, segment, LSN và thứ tự thay đổi giúp giải thích crash recovery, COMMIT durability, checkpoint và streaming replication.

Các điểm cần nhớ:

1. **Write-ahead rule:** WAL cần thiết phải được ghi bền trước data page tương ứng được ghi bền.
2. **WAL record không phải SQL statement hay row:** một statement có thể tạo nhiều records, và một record có thể liên quan nhiều blocks.
3. **WAL page và segment là hai cấp tổ chức khác nhau:** segment là file vật lý chứa nhiều pages; records có thể qua page/segment boundaries.
4. **LSN là byte position trong WAL stream:** không phải timestamp, XID hoặc row ID.
5. **LSN tăng theo record insertion order:** records của nhiều transactions có thể xen kẽ; start order không bằng commit order.
6. **Transaction có nhiều WAL records:** commit record là sự kiện riêng, không gom mọi thay đổi thành một record.
7. **Insert, write, flush là các mốc khác nhau:** write không phải flush; flush WAL không đồng nghĩa data pages đã flush.
8. **Commit acknowledgment phụ thuộc durability settings:** synchronous_commit và synchronous replication ảnh hưởng mức chờ xác nhận.
9. **Page LSN giúp recovery quyết định redo:** nó không phải commit LSN hoặc transaction identity.
10. **Checkpoint thiết lập redo starting point:** nó không phải COMMIT và không bảo đảm mọi WAL segment cũ lập tức bị xóa.
11. **Segment naming có timeline/log/segment fields:** segment size phụ thuộc cluster initialization; không hardcode 16 MiB cho mọi cluster.
12. **Timeline phân biệt lịch sử sau failover:** LSN cần được diễn giải trong context timeline.
13. **Replication có receive/write/flush/replay progress:** nhận WAL chưa có nghĩa standby đã replay để query thấy dữ liệu.
14. **Archive/slots có thể giữ WAL:** không xóa files thủ công để giải phóng disk.
15. **Quan sát đúng mốc:** dùng current insert/write/flush LSN, pg_stat_replication, pg_stat_wal, pg_walfile_name và tool tương thích version.
16. **Unknown COMMIT outcome cần idempotency:** mất response không chứng minh transaction rollback.

Quy trình tư duy: **xác định timeline → chọn loại LSN cần quan sát → xác định record/segment tương ứng → phân biệt insert/write/flush → tìm commit/checkpoint/redo context → đối chiếu replica receive/replay và archive → xử lý recovery theo metadata PostgreSQL, không sửa WAL files thủ công**.

---

## 22. Bên trong WAL pages và segment headers

### 22.1. Page header

Mỗi WAL page có header để PostgreSQL nhận biết:
- WAL page bắt đầu ở vị trí nào trong stream.
- Timeline nào đang được dùng.
- Page có flags/metadata gì.
- Có record continuation từ page trước hay không.

Các cấu trúc nội bộ thường được nhắc trong source PostgreSQL gồm page header thường và long page header. Long header có thêm thông tin như system identifier, WAL segment size và WAL block size trong các ngữ cảnh phù hợp.

Đây là chi tiết implementation, không phải API ổn định để ứng dụng tự đọc bằng offset cố định.

### 22.2. WAL block size và segment size

Cần phân biệt:
- **WAL block/page size:** đơn vị page bên trong WAL stream, thường 8 KiB trong các PostgreSQL builds phổ biến.
- **WAL segment size:** kích thước file segment, thường 16 MiB mặc định nhưng được chọn khi initdb.
- **Database block size:** kích thước page của heap/index, thường 8 KiB trong builds phổ biến.

Các kích thước này có quan hệ nhưng không phải một khái niệm. Không dùng database block size để suy segment size.

### 22.3. Continuation record

Nếu record vượt qua phần còn lại của WAL page, phần tiếp theo có thể nằm ở page kế tiếp. Header của page continuation lưu metadata để reader biết còn bao nhiêu bytes thuộc record trước.

Một record cũng có thể băng qua segment boundary. Vì vậy pg_waldump/WAL reader phải đọc nhiều pages/segments đúng thứ tự thay vì parse mỗi file như một log độc lập.

### 22.4. Alignment và padding

WAL record có quy tắc alignment/padding nội bộ. Độ dài payload logic không nhất thiết bằng khoảng cách LSN tới record tiếp theo nếu tính cả alignment/page headers. Hãy dùng PostgreSQL types/tools để phân tích; không cộng record length một cách thủ công để dự đoán LSN tiếp theo.

### 22.5. Fork và block references

Một relation có các forks khác nhau như main, FSM, VM và init trong các bối cảnh phù hợp. WAL block reference có thể xác định relation/fork/block liên quan. Một thao tác không chỉ thay đổi main fork; các thao tác visibility/free-space/storage có thể có record/resource manager riêng.

---

## 23. Các loại WAL records thường gặp

### 23.1. Heap records

Các records của heap resource manager mô tả những thao tác như insert, update, delete, clean/prune hoặc multi-insert tùy loại. Một bulk insert có thể dùng record hỗ trợ nhiều tuples trên cùng page thay vì một record đơn giản cho mỗi row.

### 23.2. B-tree records

Index B-tree có cấu trúc page/sibling/parent. Một insert có thể chỉ thêm index tuple, nhưng page split hoặc các thao tác structural maintenance có thể ghi records liên quan nhiều pages. Đây là lý do một INSERT vào bảng có index có thể tạo nhiều WAL hơn chỉ phần heap row.

### 23.3. Transaction records

Resource manager XACT ghi các sự kiện liên quan transaction, chẳng hạn commit/abort và prepared transaction theo các protocol phù hợp. Commit record chứa metadata cần cho transaction status/recovery; không phải một bản sao SQL statement.

### 23.4. Checkpoint/control records

XLOG resource manager chứa records điều khiển như checkpoint và các sự kiện WAL-level khác. Những records này giúp recovery biết điểm bắt đầu và trạng thái cần thiết.

### 23.5. Sequence records

Sequence changes có semantics riêng; không suy sequence state chỉ từ một row INSERT vào bảng. Việc cấp nextval và transaction rollback có behavior khác DML thông thường.

### 23.6. Logical messages/origin

WAL có thể chứa logical messages và replication origin metadata phục vụ logical decoding/replication. Đây không đồng nghĩa mọi logical change đều được ghi dưới dạng một câu SQL hoặc row JSON nguyên vẹn.

### 23.7. Relation/database metadata

Các thao tác tạo/xóa relation, database, tablespace và storage files có thể sinh WAL records để recovery/replication giữ metadata nhất quán.

### 23.8. Không nên gán mỗi RMGR thành một business operation

Một INSERT orders có thể tạo HEAP và BTREE records cùng transaction records; trigger có thể tạo thêm changes. RMGR là phân loại nội bộ phục vụ redo, không phải event taxonomy của ứng dụng.

---

## 24. WAL, wal_level và loại thông tin được ghi

### 24.1. WAL luôn tồn tại cho crash recovery

PostgreSQL luôn cần WAL để bảo vệ crash recovery. wal_level điều khiển mức thông tin bổ sung được ghi cho các khả năng như replication/logical decoding; nó không phải công tắc tắt WAL.

### 24.2. Các mức thường gặp

Các mức phổ biến:
- **minimal:** mức thông tin đủ cho crash recovery trong các giới hạn sử dụng; không phù hợp với các yêu cầu physical replication/PITR thông thường.
- **replica:** cung cấp thông tin cần cho streaming replication và archive/PITR theo cấu hình.
- **logical:** bổ sung thông tin cần cho logical decoding/replication.

Chi tiết khả năng, mức thấp nhất được phép và yêu cầu restart phụ thuộc PostgreSQL version. Kiểm tra docs/config thực tế trước khi thay đổi.

### 24.3. Không hạ wal_level để chữa disk full

Hạ wal_level có thể làm mất khả năng replication/archiving/logical decoding mà hệ thống đang dựa vào, và có thể cần restart. Nó không xử lý nguyên nhân slot/archive retention đang giữ WAL. Điều tra consumer/archiver/disk trước.

### 24.4. UNLOGGED relations

Dữ liệu của unlogged tables không được WAL-logged như logged tables và không được physical standby tái tạo theo cách thông thường. Sau crash, nội dung unlogged relation có thể bị reset/truncate theo semantics PostgreSQL. Không dùng unlogged cho dữ liệu duy nhất hoặc checkpoint cần durability.

### 24.5. Temporary relations

Temporary tables có lifecycle theo session và logging behavior đặc biệt. Không dùng chúng làm bằng chứng rằng mọi SQL operation đều sinh WAL như một logged permanent table. Khi phân tích WAL volume, phải biết workload đang tác động relation loại nào.

---

## 25. Checkpoint metadata và pg_control

### 25.1. Đọc checkpoint metadata

Các PostgreSQL versions hỗ trợ hàm pg_control_checkpoint() để xem thông tin checkpoint/control từ control file. Ví dụ:

~~~sql
SELECT *
FROM pg_control_checkpoint();
~~~

Output có thể chứa checkpoint LSN, redo LSN, timeline IDs, checkpoint time, next XID và các metadata khác tùy version. Đây là thông tin phục vụ quản trị/recovery, không phải view query nghiệp vụ thông thường.

### 25.2. Quyền truy cập

Các hàm đọc control data thường yêu cầu quyền quản trị/monitor thích hợp. Không cấp superuser cho ứng dụng chỉ để đọc một dashboard. Dùng DBA/monitor role theo least privilege và kiểm tra version.

### 25.3. pg_controldata

pg_controldata là command-line utility đọc control information từ data directory. Nó có thể hiển thị WAL block size, WAL segment size, checkpoint/redo information và các trường control khác tùy version.

Chạy với đúng PostgreSQL binary/data directory và quyền cần thiết. Không chỉnh sửa control file bằng tool này; đây là công cụ đọc thông tin.

### 25.4. Checkpoint LSN và redo LSN

Checkpoint record và redo pointer không nhất thiết là cùng một LSN. Checkpoint metadata lưu điểm recovery phù hợp; redo pointer xác định WAL từ đó recovery cần bắt đầu xét redo.

### 25.5. Checkpoint time không phải transaction commit time

Checkpoint time là thời điểm checkpoint metadata được ghi/hoàn tất theo semantics engine. Nó không cho biết transaction cụ thể commit lúc nào. Muốn truy vấn commit time cần những cơ chế khác, ví dụ commit timestamp tracking nếu được bật và còn dữ liệu phù hợp; không suy từ checkpoint timestamp.

---

## 26. pg_waldump và pg_walinspect: thực hành đọc record

### 26.1. Khi nào cần đọc record?

Các công cụ đọc WAL hữu ích cho:
- Điều tra loại record/resource manager tạo WAL.
- So sánh WAL trước/sau một workload lab.
- Kiểm tra record range khi phân tích replication/recovery.
- Tìm hiểu FPI volume và block references.
- Học cách một thao tác SQL ánh xạ sang WAL records.

Chúng không phải công cụ thay thế backup/restore hoặc một API business auditing.

### 26.2. pg_waldump

Ví dụ dạng tổng quát:

~~~bash
pg_waldump --path=/path/to/pg_wal --start=0/16B6C50 --end=0/16C4200
~~~

Các options thường dùng gồm:
- --path hoặc -p: thư mục chứa WAL segment files.
- --start hoặc -s: LSN bắt đầu.
- --end hoặc -e: LSN kết thúc.
- --rmgr hoặc -r: lọc resource manager trong những phiên bản hỗ trợ.
- --xid hoặc -x: lọc transaction ID theo khả năng tool.
- --stats: hiển thị thống kê theo record/resource manager trong phiên bản hỗ trợ.

Cú pháp/options phải kiểm tra bằng pg_waldump --help của đúng version. Có thể cần file segment liên tiếp và đủ quyền đọc. Không trộn binary version mới với WAL format cũ mà không xác minh compatibility.

### 26.3. Đọc một dòng output

Output có thể chứa:
- LSN bắt đầu record.
- Transaction ID.
- Resource manager.
- Record type.
- Record length.
- Previous record LSN.
- Mô tả record và block references.

Các tên field/output khác nhau theo version. Đây là thông tin low-level; không phải SQL text.

### 26.4. pg_walinspect extension

Trên PostgreSQL versions hỗ trợ extension, có thể cài trong database phù hợp:

~~~sql
CREATE EXTENSION pg_walinspect;
~~~

Extension cung cấp functions để inspect WAL range. Cài đặt và privileges cần tuân thủ chính sách DBA; không bật extension hoặc cấp quyền đọc WAL rộng cho mọi role.

### 26.5. Đọc record cụ thể

Ở các versions hỗ trợ:

~~~sql
SELECT *
FROM pg_get_wal_record_info('0/16B6C50'::pg_lsn);
~~~

LSN phải trỏ tới record hợp lệ trong WAL còn có thể truy cập. LSN giữa record, segment không còn tồn tại hoặc range đã bị recycle có thể gây lỗi/không có dữ liệu.

### 26.6. Đọc nhiều records trong một range

~~~sql
SELECT
    start_lsn,
    end_lsn,
    prev_lsn,
    xid,
    resource_manager,
    record_type,
    record_length,
    main_data_length,
    fpi_length,
    description
FROM pg_get_wal_records_info(
    '0/16B6C50'::pg_lsn,
    '0/16C4200'::pg_lsn
);
~~~

Function signature và output fields cần xác minh theo version extension. Giới hạn range nhỏ để tránh tạo output quá lớn.

### 26.7. Thống kê record range

~~~sql
SELECT *
FROM pg_get_wal_stats(
    '0/16B6C50'::pg_lsn,
    '0/16C4200'::pg_lsn
);
~~~

Thống kê có thể phân loại record counts/bytes theo resource manager hoặc record type. Dùng để hiểu workload lab; không gọi là WAL bytes chính xác của một session nếu database có writes đồng thời.

### 26.8. An toàn khi inspect

WAL có thể chứa page images và dữ liệu nhạy cảm. Khi xuất record descriptions/payload:
- Giới hạn LSN range.
- Không gửi raw WAL dumps lên nơi công khai.
- Redact identifiers/payload khi cần.
- Không giữ lâu hơn policy.
- Không inspect bằng role quá rộng nếu không cần.
- Dùng binary/extension đúng PostgreSQL release.

---

## 27. Các mốc WAL trong một transaction minh họa

### 27.1. Timeline khái niệm

~~~text
T1 bắt đầu
   |
   +-- UPDATE heap page A ---- WAL record R1 @ LSN 100
   |
   +-- UPDATE index page B -- WAL record R2 @ LSN 180
   |
   +-- Trigger audit -------- WAL record R3 @ LSN 240
   |
   +-- COMMIT --------------- commit record @ LSN 310
                              |
                              v
                    WAL flush qua commit record
                              |
                              v
                    Server xác nhận COMMIT
                              |
                              v
                    Data pages được ghi về sau
~~~

Các LSN và thứ tự chỉ là ví dụ. Nếu có T2 chạy song song, record của T2 có thể xuất hiện giữa R1 và R2. Commit record LSN không có nghĩa các records trước nó đều thuộc T1.

### 27.2. Điều kiện xác nhận commit

Trong cấu hình durability thông thường, server chỉ xác nhận transaction commit khi WAL cần cho transaction được flush tới mức cần thiết. Nếu synchronous replication được cấu hình, mức xác nhận có thể còn chờ standby theo mode.

### 27.3. Data page flush sau COMMIT

Một data page chứa R1/R2 có thể được ghi xuống disk sau khi COMMIT đã được xác nhận. Khi đó write-ahead rule đảm bảo WAL tương ứng đã bền trước page write. Nếu crash trước data-page write, recovery redo WAL.

### 27.4. Một page chứa nhiều transactions

Nếu T1 và T2 thay đổi cùng heap page ở các thời điểm khác nhau, page có thể chứa effects từ cả hai transactions. Page LSN thể hiện WAL record cuối cùng được áp dụng lên page, không nói transaction nào là owner của page.

### 27.5. Commit không biến WAL thành một khối liên tục riêng

WAL stream vẫn là một dãy records toàn cluster. Không có file segment riêng cho T1. Recovery dùng record metadata/transaction state để tái dựng kết quả, không cần gom records của T1 thành một file riêng.

---

## 28. Bài lab: đọc các LSN positions

### 28.1. Lấy snapshot

~~~sql
SELECT
    clock_timestamp() AS sampled_at,
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_lsn() AS write_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
~~~

Lưu output. clock_timestamp() là thời gian lấy mẫu; LSNs có thể thay đổi giữa lúc các hàm được đánh giá và workload đồng thời có thể làm các vị trí tiến.

### 28.2. Tạo một transaction có WAL

~~~sql
CREATE SCHEMA IF NOT EXISTS wal_order_lab;

CREATE TABLE IF NOT EXISTS wal_order_lab.demo (
    id bigint PRIMARY KEY,
    payload text NOT NULL
);
~~~

Đo trước, rồi chạy:

~~~sql
BEGIN;

INSERT INTO wal_order_lab.demo(id,payload)
SELECT g, repeat('x',100)
FROM generate_series(1,1000) AS g
ON CONFLICT (id) DO UPDATE
SET payload=EXCLUDED.payload;

COMMIT;
~~~

### 28.3. Đo sau

~~~sql
SELECT
    clock_timestamp() AS sampled_at,
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_lsn() AS write_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
~~~

Ghi các LSN trước/sau và tính diff. Delta là WAL stream toàn cluster giữa các samples, không phải record count của INSERT.

### 28.4. Xem segment chứa current LSN

~~~sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS wal_file,
    (pg_walfile_name_offset(pg_current_wal_lsn())).file_offset AS file_offset;
~~~

Cú pháp truy cập composite result có thể khác cách hiển thị theo client/version; có thể chạy riêng SELECT * FROM pg_walfile_name_offset(...) để xem rõ các cột.

### 28.5. Xem pg_stat_wal trước/sau

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_write,
    wal_sync,
    stats_reset
FROM pg_stat_wal;
~~~

Chụp hai mẫu và so delta. Nếu stats_reset đổi giữa hai lần, không so trực tiếp. Counters global; workloads khác gây nhiễu.

### 28.6. Thử rollback

~~~sql
BEGIN;

INSERT INTO wal_order_lab.demo(id,payload)
VALUES (2001,'rollback-test');

ROLLBACK;
~~~

Kiểm tra:

~~~sql
SELECT *
FROM wal_order_lab.demo
WHERE id=2001;
~~~

Không có row đã commit, nhưng WAL position có thể đã tiến. Đây là minh họa cho khác biệt giữa business visibility và WAL generation.

---

## 29. Bài lab: quan sát checkpoint và replication

### 29.1. Checkpoint metadata

Trên server/role có quyền phù hợp, thử:

~~~sql
SELECT *
FROM pg_control_checkpoint();
~~~

Xem các fields checkpoint/redo/timeline. Nếu function không tồn tại hoặc permission denied, kiểm tra PostgreSQL version và role privileges; không tự cấp superuser cho ứng dụng.

### 29.2. Checkpoint statistics

~~~sql
SELECT *
FROM pg_stat_checkpointer;
~~~

View này có ở các PostgreSQL versions mới; các phiên bản cũ có thể lưu một số counters trong pg_stat_bgwriter. Không dùng một dashboard SQL duy nhất mà không version-gate.

### 29.3. Replication progress trên primary

~~~sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

Nếu không có standby kết nối, view có thể rỗng. Rỗng không đồng nghĩa lag bằng 0.

### 29.4. Receive/replay trên standby

~~~sql
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
~~~

So sánh receive với replay để hiểu standby đã nhận nhưng chưa apply bao nhiêu WAL. Timestamp replay cuối không phản ánh lag chính xác khi primary idle.

### 29.5. Archive progress

~~~sql
SELECT *
FROM pg_stat_archiver;
~~~

Kiểm tra last_archived_wal/time, failed_count, last_failed_wal/time và stats_reset. Kết hợp logs/destination health để điều tra archive backlog.

---

## 30. Quy tắc suy luận khi đọc WAL

### 30.1. Từ LSN thấp tới cao

LSN tăng cho biết vị trí record sau trong WAL stream trên timeline. Nó không tự nói transaction nào commit, business action nào thành công hoặc replica nào đã replay.

### 30.2. Từ commit record

Commit record là một dấu mốc transaction hoàn tất trong WAL. Muốn xác định transaction state cần hiểu XID, commit/abort records và recovery semantics. Không dựa vào việc thấy một heap record để kết luận row đã commit.

### 30.3. Từ page LSN

Page LSN giúp biết page đã áp dụng WAL tới vị trí nào theo cơ chế storage/recovery. Nó không thể thay transaction status hoặc commit record.

### 30.4. Từ flush LSN

Flush LSN cho biết WAL đã flush tới một vị trí. Nó không đồng nghĩa mọi transaction có record trước vị trí đó đều commit; có thể tồn tại aborted/in-progress transactions và non-transactional records.

### 30.5. Từ segment filename

Filename cho biết timeline và vị trí segment trong WAL numbering. Nó không cho biết segment đã archive, đã replay hoặc còn cần cho slot nào.

### 30.6. Từ archive success

Archive success cho biết segment đã được archive theo cơ chế báo cáo, không tự chứng minh một backup chain có thể restore. Cần kiểm thử PITR.

---

## 31. Checklist đọc WAL và điều tra sự cố

### 31.1. Khi cần hiểu LSN

- [ ] Xác định LSN đang xem là insert, write, flush, receive, replay hay commit LSN.
- [ ] Xác định primary hay standby.
- [ ] Ghi nhận timeline/history khi có failover.
- [ ] Dùng pg_lsn và pg_wal_lsn_diff, không parse chuỗi thủ công.
- [ ] Nhớ LSN delta là cluster-wide nếu có workload đồng thời.

### 31.2. Khi cần hiểu segment

- [ ] Xác định segment size thật của cluster.
- [ ] Đọc filename theo timeline/log/segment numbering.
- [ ] Dùng pg_walfile_name()/pg_walfile_name_offset() nếu phù hợp.
- [ ] Kiểm tra archive/slot/replica retention.
- [ ] Không đổi tên, xóa hoặc copy segment đang active bằng thao tác tùy tiện.

### 31.3. Khi cần hiểu record order

- [ ] Tách record order khỏi transaction start/commit order.
- [ ] Tìm commit/abort records nếu công cụ hỗ trợ.
- [ ] Nhớ records của transactions có thể interleave.
- [ ] Không suy business row identity từ LSN.
- [ ] Dùng tool tương thích version khi decode record.

### 31.4. Khi cần hiểu durability

- [ ] Kiểm tra synchronous_commit.
- [ ] Kiểm tra synchronous replication policy nếu có.
- [ ] Phân biệt WAL write và flush.
- [ ] Phân biệt WAL flush và data-page flush.
- [ ] Kiểm tra fsync, full_page_writes và storage assumptions.
- [ ] Unknown commit outcome phải xử lý bằng idempotency/reconciliation.

### 31.5. Khi cần hiểu checkpoint/recovery

- [ ] Xác định checkpoint/redo LSN.
- [ ] Kiểm tra checkpoint frequency và WAL growth.
- [ ] Xem FPI volume.
- [ ] Kiểm tra archive continuity/PITR.
- [ ] Không xóa segments cần recovery/standby.

---

## 32. Tài liệu tham khảo chính thức

Khi làm việc với một major version cụ thể, ưu tiên tài liệu cùng version:

- [PostgreSQL — Write-Ahead Logging (WAL)](https://www.postgresql.org/docs/current/wal.html): nguyên tắc WAL và crash recovery.
- [PostgreSQL — WAL Internals](https://www.postgresql.org/docs/current/wal-internals.html): WAL records/pages/segments và LSN.
- [PostgreSQL — WAL Configuration](https://www.postgresql.org/docs/current/wal-configuration.html): checkpoint/WAL configuration.
- [PostgreSQL — WAL Reliability](https://www.postgresql.org/docs/current/wal-reliability.html): durability, fsync và write-ahead rules.
- [PostgreSQL — WAL Functions](https://www.postgresql.org/docs/current/functions-admin.html): LSN functions, WAL file naming và administrative functions.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_wal, replication và checkpoint statistics.
- [PostgreSQL — Warm Standby / Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html): send/write/flush/replay và standby behavior.
- [PostgreSQL — Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html): WAL archiving/recovery.
- [PostgreSQL — pg_waldump](https://www.postgresql.org/docs/current/pgwaldump.html): đọc WAL records bằng command-line.
- [PostgreSQL — pg_walinspect](https://www.postgresql.org/docs/current/pgwalinspect.html): inspect WAL bằng SQL extension khi phiên bản hỗ trợ.

Các trang /current/ có thể thay đổi khi PostgreSQL phát hành phiên bản mới. WAL binary format là implementation detail; nếu xây parser hoặc tool phân tích lâu dài, phải version-aware và dựa vào source/docs của đúng release.

---

## 33. Tổng kết

**WAL là một luồng nhị phân có thứ tự, được đánh địa chỉ bằng LSN và lưu vật lý trong các segments.** Hiểu đúng record, segment, LSN và thứ tự thay đổi giúp giải thích crash recovery, COMMIT durability, checkpoint và streaming replication.

Các điểm cần nhớ:

1. **Write-ahead rule:** WAL cần thiết phải được ghi bền trước data page tương ứng được ghi bền.
2. **WAL record không phải SQL statement hay row:** một statement có thể tạo nhiều records, và một record có thể liên quan nhiều blocks.
3. **WAL page và segment là hai cấp tổ chức khác nhau:** segment là file vật lý chứa nhiều pages; records có thể qua page/segment boundaries.
4. **LSN là byte position trong WAL stream:** không phải timestamp, XID hoặc row ID.
5. **LSN tăng theo record insertion order:** records của nhiều transactions có thể xen kẽ; start order không bằng commit order.
6. **Transaction có nhiều WAL records:** commit record là sự kiện riêng, không gom mọi thay đổi thành một record.
7. **Insert, write, flush là các mốc khác nhau:** write không phải flush; flush WAL không đồng nghĩa data pages đã flush.
8. **Commit acknowledgment phụ thuộc durability settings:** synchronous_commit và synchronous replication ảnh hưởng mức chờ xác nhận.
9. **Page LSN giúp recovery quyết định redo:** nó không phải commit LSN hoặc transaction identity.
10. **Checkpoint thiết lập redo starting point:** nó không phải COMMIT và không bảo đảm mọi WAL segment cũ lập tức bị xóa.
11. **Segment naming có timeline/log/segment fields:** segment size phụ thuộc cluster initialization; không hardcode 16 MiB cho mọi cluster.
12. **Timeline phân biệt lịch sử sau failover:** LSN cần được diễn giải trong context timeline.
13. **Replication có receive/write/flush/replay progress:** nhận WAL chưa có nghĩa standby đã replay để query thấy dữ liệu.
14. **Archive/slots có thể giữ WAL:** không xóa files thủ công để giải phóng disk.
15. **Quan sát đúng mốc:** dùng current insert/write/flush LSN, pg_stat_replication, pg_stat_wal, pg_walfile_name và tool tương thích version.
16. **Unknown COMMIT outcome cần idempotency:** mất response không chứng minh transaction rollback.

Quy trình tư duy: **xác định timeline → chọn loại LSN cần quan sát → xác định record/segment tương ứng → phân biệt insert/write/flush → tìm commit/checkpoint/redo context → đối chiếu replica receive/replay và archive → xử lý recovery theo metadata PostgreSQL, không sửa WAL files thủ công**.

---

## 34. Lời giải — bài 16 đến 30

### Bài 16 — Flush và durability

Nếu commit record đã được flush theo durability policy, PostgreSQL đã có log cần thiết để phục hồi transaction. Khi crash trước khi heap page được ghi, recovery đọc WAL từ redo point và phát lại thay đổi cần thiết. Write-ahead rule bảo đảm WAL bền trước data-page write.

### Bài 17 — synchronous_commit

Không. WAL vẫn được tạo và ghi theo cơ chế server; setting có thể cho phép acknowledge COMMIT trước khi WAL tương ứng được flush, giảm latency nhưng chấp nhận rủi ro mất những commits vừa được xác nhận nếu crash. Đây là durability trade-off, không phải “tắt WAL”.

### Bài 18 — Checkpoint, redo và commit LSN

- Checkpoint LSN: vị trí liên quan checkpoint record/metadata.
- Redo LSN: điểm WAL recovery cần bắt đầu xét redo.
- Commit LSN: vị trí commit record của transaction cụ thể.

Checkpoint đồng bộ dirty pages và thiết lập recovery point; COMMIT đánh dấu transaction hoàn tất. Hai sự kiện có mục tiêu khác nhau.

### Bài 19 — Timeline

Sau promotion, standby trở thành primary và WAL history có thể rẽ nhánh. Cùng một LSN số học trên hai timelines không nhất thiết cùng history. Timeline ID nằm trong tên WAL segment và được ghi trong timeline history metadata.

### Bài 20 — Replication positions

- sent_lsn: sender đã gửi tới vị trí đó.
- write_lsn: standby đã ghi.
- flush_lsn: standby đã flush.
- replay_lsn: standby đã áp dụng WAL.

Nếu flush tiến nhưng replay đứng lại, kiểm tra standby CPU/I/O, replay process, hot standby conflicts, long-running readers và WAL apply bottleneck. Network có thể không phải nguyên nhân chính nếu receive/flush đã theo kịp.

### Bài 21 — WAL filename

~~~sql
SELECT pg_walfile_name(pg_current_wal_lsn());
~~~

Và:

~~~sql
SELECT *
FROM pg_walfile_name_offset(pg_current_wal_lsn());
~~~

Kết quả cho segment name và offset theo segment size/timeline hiện tại.

### Bài 22 — pg_waldump

Đây là command-line utility đọc/diễn giải WAL segments. Output có thể cho biết record start LSN, previous LSN, XID, resource manager, record type, length, block references và description. Options phụ thuộc version; dùng binary tương thích với cluster.

### Bài 23 — pg_walinspect

Extension cung cấp SQL functions đọc record/range/stats, tránh tự parse binary format. Cần giới hạn LSN range vì output có thể rất lớn và payload có thể nhạy cảm. Quyền đọc WAL phải được cấp theo policy, không cho mọi application role.

### Bài 24 — Segment rotation

pg_switch_wal() yêu cầu switch sang WAL segment tiếp theo theo trạng thái server. Nó không giải phóng WAL; segment vẫn có thể cần cho checkpoint, archive, standby hoặc replication slots. Gọi liên tục còn tạo thêm archive/segment churn.

### Bài 25 — Recycle và archive

- Recycle: PostgreSQL tái sử dụng file segment cho vị trí WAL tương lai khi segment không còn cần ở vị trí cũ.
- Archive: lưu segment hoàn chỉnh ra archive destination để backup/PITR.

File count có thể ổn định dù WAL generation lớn do reuse; hoặc pg_wal có thể lớn vì retention dù generation hiện tại không cao.

### Bài 26 — Rollback

Có. UPDATE có thể tạo WAL records trước ROLLBACK. Sau rollback, business changes không được commit và không còn visible như dữ liệu đã commit, nhưng WAL stream vẫn tiến; aborted tuple versions có thể cần cleanup/reuse.

### Bài 27 — LSN attribution

Current WAL LSN là cluster-wide. Trong production, sessions khác, autovacuum, checkpoints và background activity cũng có thể ghi WAL giữa hai samples. Delta là khoảng cách WAL stream toàn server, không phải chính xác lượng WAL của một transaction.

### Bài 28 — Checkpoint inspection

~~~sql
SELECT *
FROM pg_control_checkpoint();
~~~

Hai trường hữu ích là checkpoint LSN và redo LSN (tên output có thể khác theo version). Có thể xem timeline ID và checkpoint time để hiểu lịch sử/recovery context. Hàm cần version và privileges phù hợp.

### Bài 29 — Archive failure

Các bước an toàn:
1. Đọc pg_stat_archiver và PostgreSQL logs.
2. Kiểm tra archive destination, disk quota, permissions, network và archive command.
3. Đo pg_wal free space và WAL generation rate.
4. Kiểm tra replication slots/standby để biết WAL còn bị giữ vì lý do nào.
5. Khôi phục archive pipeline và theo dõi segment catch-up.
6. Không xóa WAL segment thủ công; xác minh backup/PITR chain.

### Bài 30 — Standby replay chậm

Primary tạo WAL và flush commit record; sender gửi tới standby. Standby nhận/ghi/flush WAL nhanh, nhưng replay process chưa áp dụng kịp, nên replay_lsn tụt sau flush_lsn.

Ba nhóm nguyên nhân:
- CPU/replay processing bottleneck hoặc WAL record workload nặng.
- Storage I/O chậm trên standby.
- Hot standby conflicts/long-running queries hoặc resource contention cản replay.

Quan sát pg_stat_replication trên primary, receive/replay LSN và recovery conflicts trên standby, CPU/I/O, logs và wait events. Nếu ứng dụng đọc replica, tính eventual consistency/lag vào routing.

---

## 35. Bài tập nâng cao: phân tích WAL sequence

### Bài 31 — Transaction xen kẽ

Cho WAL sequence:

~~~text
LSN 100: T1 UPDATE A
LSN 120: T2 UPDATE B
LSN 140: T1 UPDATE C
LSN 160: T2 COMMIT
LSN 180: T1 COMMIT
~~~

Trả lời: transaction nào bắt đầu trước? Transaction nào commit trước? Có thể nói records 100–140 thuộc riêng T1 không?

### Bài 32 — Insert/write/flush positions

Một sample có:
- insert = 0/5000000
- write = 0/4F00000
- flush = 0/4E00000

Giải thích khoảng cách giữa ba positions nói lên điều gì và điều gì không thể kết luận.

### Bài 33 — Segment count

Một cluster dùng 16 MiB segments, sinh khoảng 512 MiB WAL trong một khoảng đo. Có thể kết luận pg_wal hiện phải có đúng 32 files không? Vì sao?

### Bài 34 — Page LSN

Heap page có pd_lsn=0/9000. Một WAL record có LSN=0/8000 tham chiếu page đó trong redo range. Có thể kết luận redo luôn bỏ qua record không? Nêu caveat.

### Bài 35 — WAL record vượt page

Vì sao parser không thể giả định record luôn nằm trọn trong một WAL page? Header continuation có vai trò gì?

### Bài 36 — Checkpoint và segment retention

Sau checkpoint mới, pg_wal vẫn còn nhiều segments cũ. Nêu ít nhất bốn nguyên nhân có thể.

### Bài 37 — Timeline và LSN

Hai nodes báo cùng replay LSN nhưng timeline ID khác nhau sau failover. Có thể kết luận chúng ở cùng history không? Giải thích.

### Bài 38 — Archive success

pg_stat_archiver cho biết archived_count tăng. Điều này có đủ để khẳng định có thể PITR tới mọi thời điểm không? Cần xác minh thêm gì?

### Bài 39 — LSN delta

Bạn lấy pg_current_wal_lsn() trước/sau một workload 5 giây và thấy diff 200 MiB. Tính WAL generation trung bình MiB/s. Nêu ít nhất hai giới hạn của kết quả.

### Bài 40 — Commit acknowledgment

Một transaction COMMIT được xác nhận khi synchronous_commit=off. Server mất điện ngay sau đó. Có thể transaction bị mất không? Vì sao ứng dụng cần idempotency?

### Bài 41 — WAL record vs query log

Vì sao pg_waldump không phải công cụ audit SQL statements hoặc business events? Muốn audit nghiệp vụ nên dùng gì?

### Bài 42 — Unlogged table

Một importer ghi raw data vào UNLOGGED table, sau đó merge vào logged table. Sau crash raw staging có thể ra sao? Những điều kiện nào khiến mô hình này an toàn?

### Bài 43 — wal_level

Một DBA hạ wal_level để giảm disk. Vì sao việc này không giải quyết một replication slot bị stuck và có thể gây hậu quả gì?

### Bài 44 — WAL writer

WAL writer và backend có vai trò gì trong write/flush? Vì sao không nên chỉnh wal_writer_delay chỉ dựa trên một lần đo latency?

### Bài 45 — Runbook tổng hợp

Primary commit bình thường nhưng replica lag tăng, pg_wal retained tăng và archive failures cũng tăng. Viết các bước phân biệt generation pressure với retention pressure và khôi phục an toàn.

---

## 36. Lời giải — bài tập nâng cao

### Bài 31 — Transaction xen kẽ

T1 có record đầu tiên tại LSN 100 nên bắt đầu ghi WAL trước trong sequence này. T2 commit tại LSN 160 trước T1 tại LSN 180. Không thể nói records 100–140 thuộc riêng T1 vì T2 có record ở LSN 120 xen kẽ.

### Bài 32 — Position gaps

Insert đi trước write, write đi trước flush. Có WAL bytes đã insert nhưng chưa write, và bytes đã write nhưng chưa flush tại sample. Không thể suy chính xác số transaction chưa commit hoặc business rows chưa durable chỉ từ các khoảng cách; cần hiểu concurrency, record types và timing.

### Bài 33 — Segment count

Không. 512 MiB / 16 MiB = 32 segment-worth of WAL generation, nhưng directory có thể giữ segments đã recycle, segment hiện tại, segments được giữ bởi archive/slots/standby/checkpoint. File count hiện tại không bằng generation trong window.

### Bài 34 — Page LSN

Nếu page LSN đã ở sau record LSN, recovery thường không cần redo thay đổi page đó lần nữa theo logic redo phù hợp. Nhưng không kết luận mọi record/resource manager đều có điều kiện skip giống nhau; redo routine, block references, FPI và record semantics có thể ảnh hưởng quyết định.

### Bài 35 — Continuation

Record length có thể lớn hơn phần trống còn lại của page. Continuation metadata ở page tiếp theo cho reader biết record trước còn bao nhiêu bytes và nối payload đúng. Parser phải hiểu page headers, alignment và segment boundaries.

### Bài 36 — Segment retention

- Archive command chưa hoàn tất.
- Physical standby hoặc logical replication slot giữ restart LSN cũ.
- Standby nhận/replay chậm hoặc offline.
- wal_keep_size/retention settings.
- Checkpoint/recovery cần giữ segment.
- PostgreSQL recycle/reuse policy và minimum WAL retention.

### Bài 37 — Timeline

Không. Cùng LSN trên hai timelines khác nhau có thể chỉ các history khác nhau sau fork point. Phải kiểm tra timeline IDs/history files và recovery lineage.

### Bài 38 — Archive success

Không đủ. Cần base backup hợp lệ, WAL liên tục từ backup đến target, timeline history cần thiết, archive destination đầy đủ và kiểm thử restore/PITR thực tế. archived_count chỉ là counter, không chứng minh toàn bộ chain restore được.

### Bài 39 — WAL rate

200 MiB / 5 giây = **40 MiB/s** trung bình trong window. Giới hạn:
- WAL của mọi sessions/background tasks có thể được tính chung.
- Rate ngắn hạn có thể che bursts trước/sau.
- LSN delta không phân biệt data/transaction/FPI records.
- Nếu workload có khoảng idle hoặc checkpoint, sample không đại diện steady state.

### Bài 40 — synchronous_commit=off

Có. Server có thể acknowledge trước khi WAL tương ứng được flush; mất điện có thể làm mất một số commits vừa được xác nhận. Client mất response cũng tạo unknown outcome. Idempotency keys/unique constraints và reconciliation giúp retry mà không nhân đôi business effects.

### Bài 41 — WAL không phải audit SQL

WAL ghi binary changes nội bộ để recovery/replication, không đảm bảo lưu câu SQL text hoặc business intent. Một statement có thể sinh nhiều records; một record có thể không thể ánh xạ trực tiếp về một event nghiệp vụ. Audit nên dùng application audit events, outbox/event log hoặc database audit extension phù hợp.

### Bài 42 — UNLOGGED staging

Sau crash/unclean shutdown, raw unlogged table có thể bị truncate/reset theo semantics PostgreSQL và không được physical standby replicate như logged table. Mô hình chỉ an toàn nếu raw source immutable, có checksum/version, có thể reload đầy đủ, checkpoint authoritative được lưu logged và published destination được commit đúng.

### Bài 43 — wal_level

Replication slot giữ WAL vì consumer cần các bytes từ restart_lsn; hạ wal_level không tự làm consumer catch up hoặc xóa retention dependency. Thay đổi có thể phá physical/logical replication, archive/PITR assumptions và cần restart. Phải sửa slot consumer/archive backlog theo runbook.

### Bài 44 — WAL writer

Backend có thể insert/write/flush WAL khi cần; WAL writer hỗ trợ write/flush WAL buffers theo lịch/threshold. wal_writer_delay có thể thay đổi write batching/latency/IO pattern; một sample không đủ vì group commit, storage sync, workload concurrency và WAL buffer pressure cùng ảnh hưởng. Benchmark nhiều windows và giữ durability requirements.

### Bài 45 — Runbook

1. Đo pg_stat_wal bytes/s, current insert/write/flush LSN và disk free.
2. Xem pg_stat_replication sent/write/flush/replay positions.
3. Xem pg_stat_archiver failures và destination health.
4. Xem pg_replication_slots restart_lsn/active/owner.
5. Phân biệt WAL generation tăng hay retention không giải phóng.
6. Nếu generation pressure, throttle write rate/importer; nếu retention pressure, khôi phục archive/consumer/standby.
7. Không xóa WAL files hoặc drop slots chưa xác định owner.
8. Bảo đảm disk headroom, pause an toàn ở transaction boundary nếu cần.
9. Reconcile transactions/unknown commit outcomes trước resume.
10. Resume canary nhỏ và tăng dần khi replica/archive catch up.

---

## 37. Bảng tra cứu nhanh

| Khái niệm | Câu hỏi trả lời | Không nên nhầm với |
|---|---|---|
| WAL record | Một sự kiện/thay đổi nội bộ cần redo | SQL statement, row |
| WAL page | Page chứa một phần WAL stream | Heap page |
| WAL segment | File vật lý chứa dải WAL pages | Transaction file |
| LSN | Byte position trong WAL stream | Timestamp, XID |
| Page LSN | WAL position cuối cùng áp dụng lên data page | Commit LSN |
| Insert LSN | Vị trí WAL đã insert | Flush position |
| Write LSN | Vị trí WAL đã write | Data page write |
| Flush LSN | Vị trí WAL đã flush | Tất cả transactions committed |
| Commit record | Transaction completion record | Checkpoint |
| Checkpoint | Recovery point/dirty-page synchronization | COMMIT |
| Redo LSN | Điểm bắt đầu redo | Current LSN |
| Timeline | Nhánh lịch sử WAL | Database ID |
| Receive LSN | Standby đã nhận WAL tới đâu | Replay LSN |
| Replay LSN | Standby đã apply WAL tới đâu | Primary flush LSN |
| Archive | Lưu segment hoàn chỉnh cho recovery | Recycle |
| pg_waldump | Đọc WAL records offline | SQL audit log |
| pg_walinspect | Inspect WAL qua SQL functions | Business event store |

---

## 38. Tổng kết mở rộng

Khi đọc một con số LSN, trước tiên hỏi nó là **insert, write, flush, receive, replay, redo hay commit position**. Khi đọc một WAL filename, xác định **timeline, log ID, segment number và segment size**. Khi đọc một record, xác định **resource manager, record type, XID, block references và transaction context**.

Ba trục cần luôn tách riêng:

1. **Thứ tự WAL:** thứ tự records được đặt vào WAL stream, đánh địa chỉ bằng LSN.
2. **Trạng thái transaction:** transaction đang chạy, commit hay abort theo XID/commit records/MVCC.
3. **Tiến độ persistence/replication:** WAL đã insert, write, flush, receive, replay hoặc archive tới đâu.

Những trục này liên quan nhưng không thể thay thế lẫn nhau. Một LSN lớn hơn không tự nói transaction đã commit; một flush LSN không tự chứng minh replica đã replay; một checkpoint không phải transaction commit; một segment được archive không tự bảo đảm PITR chain có thể restore.

---

## 39. Bài tập nền tảng: đọc record, segment và LSN

### Bài 46 — Vai trò WAL

Một người mới cho rằng PostgreSQL chỉ cần ghi heap page xuống disk là đủ, WAL chỉ là log phục vụ debug. Giải thích vì sao cách hiểu này sai.

### Bài 47 — Record và page

Một record dài hơn phần trống còn lại của WAL page hiện tại. PostgreSQL xử lý thế nào để record reader có thể đọc tiếp?

### Bài 48 — Segment filename

Cho tên WAL file mẫu 00000002000000010000000F. Hãy tách timeline ID, log ID và segment number.

### Bài 49 — LSN arithmetic

LSN A là 0/1000000 và LSN B là 0/1800000. Viết query tính khoảng cách byte từ A tới B.

### Bài 50 — XID và LSN

Một transaction có XID nhỏ hơn transaction khác nhưng commit sau. Điều này có mâu thuẫn với LSN ordering không? Giải thích.

### Bài 51 — Page LSN và commit

Một heap page có page LSN lớn hơn commit LSN của transaction đã sửa row trên page. Có thể suy page chứa thay đổi của transaction đó không? Nêu giới hạn của suy luận.

### Bài 52 — Write-ahead rule

Một data page có thể được ghi xuống data file trước khi WAL tương ứng được flush không? Vì sao?

### Bài 53 — Group commit

Ba transactions cùng chờ WAL flush. PostgreSQL có thể giảm số lần sync như thế nào? Group commit có làm chúng thành một transaction không?

### Bài 54 — Checkpoint

Sau checkpoint, PostgreSQL có thể bắt đầu crash recovery từ đâu? Vì sao redo LSN không nhất thiết trùng checkpoint record LSN?

### Bài 55 — Segment recycle

WAL generation tăng 1 GiB nhưng pg_wal file count không tăng. Đưa ra lời giải thích hợp lý.

### Bài 56 — WAL archive

Một segment đã được archive thành công. Điều đó có nghĩa PostgreSQL có thể lập tức xóa mọi bản WAL liên quan khỏi local disk không? Vì sao?

### Bài 57 — Timeline fork

Primary cũ và standby promoted đều có record tại LSN 0/5000000 nhưng ở hai timelines khác nhau. Vì sao không thể coi hai records là cùng một history?

### Bài 58 — Replication lag

Primary flush LSN tiến, standby receive LSN tiến tương ứng, nhưng replay LSN chậm. Hãy phân loại bottleneck và nêu ba chỉ số cần xem.

### Bài 59 — WAL delta trong production

Một job chạy từ 10:00 đến 10:05, LSN diff là 2 GiB. Có thể nói job tạo 2 GiB WAL không? Nêu cách tăng độ tin cậy của phép đo.

### Bài 60 — Unknown commit outcome

Client gửi COMMIT nhưng connection bị reset trước khi nhận response. Vì sao không thể mặc định rollback? Đưa ra hai kỹ thuật ứng dụng để xử lý.

---

## 40. Lời giải — bài tập nền tảng 46 đến 60

### Bài 46 — Vai trò WAL

WAL là cơ chế recovery/replication, không phải debug text. Nó ghi các thay đổi cần thiết theo thứ tự và cho phép redo sau crash. Nếu chỉ ghi data page mà thiếu WAL bền tương ứng, crash/torn write có thể khiến database không thể phục hồi nhất quán.

### Bài 47 — Record qua page

Record có thể tiếp tục sang WAL page kế tiếp. Page continuation header cung cấp metadata như phần record còn lại để reader nối bytes đúng thứ tự; parser còn phải xử lý alignment và segment boundary.

### Bài 48 — Filename

Tên 24 hex chars:
- Timeline ID: 00000002.
- Log ID: 00000001.
- Segment number: 0000000F.

Đây là cách tách cấu trúc tên; segment size và timeline history vẫn cần để diễn giải vị trí.

### Bài 49 — LSN diff

~~~sql
SELECT pg_wal_lsn_diff(
    '0/1800000'::pg_lsn,
    '0/1000000'::pg_lsn
) AS bytes;
~~~

Khoảng cách là 0x800000 = 8.388.608 bytes = 8 MiB. Dùng hàm PostgreSQL thay vì tự parse hex trong ứng dụng.

### Bài 50 — XID và LSN

Không mâu thuẫn. XID assignment/start order và commit order khác nhau. LSN đánh vị trí WAL records; records của transactions interleave và transaction có thể commit sau một transaction có XID lớn hơn.

### Bài 51 — Page LSN và commit

Page LSN lớn hơn commit LSN cho biết page đã được áp dụng một record sau đó trong WAL stream, nhưng page có thể chứa changes từ nhiều transactions. Không thể chỉ từ page LSN xác định row cụ thể của transaction nào đang visible/committed; cần tuple/MVCC/transaction status.

### Bài 52 — Write-ahead rule

Không. WAL records cần thiết phải được flush bền trước khi data page tương ứng được ghi bền. Nếu không, page có thể chứa thay đổi mà recovery không có log phù hợp để redo/repair.

### Bài 53 — Group commit

PostgreSQL có thể gom nhiều transactions đang chờ flush để một lần WAL sync phục vụ nhiều commit records. Mỗi transaction vẫn có atomicity và commit state riêng; group commit chỉ tối ưu I/O sync.

### Bài 54 — Checkpoint

Recovery bắt đầu redo từ redo pointer phù hợp được lưu trong checkpoint/control metadata. Checkpoint record là một record sự kiện; redo LSN có thể là vị trí sớm hơn mà recovery cần xét, nên hai LSN không nhất thiết trùng.

### Bài 55 — Recycle

PostgreSQL có thể recycle segments cũ, dùng lại cho vị trí WAL tương lai thay vì tăng file count. Một số segments cũng có thể được giữ cố định bởi retention requirements; file count không bằng WAL generation.

### Bài 56 — Archive

Không. Local segment còn có thể cần cho checkpoint, replication slots, standby, wal_keep_size hoặc recovery. PostgreSQL tự quản lý lifecycle; archived copy cũng phải được giữ theo backup/PITR retention. Không xóa local files bằng tay.

### Bài 57 — Timeline fork

Timeline mới có thể rẽ nhánh tại một LSN sau promotion. Cùng số LSN trên hai timelines có thể chứa bytes/records khác nhau sau fork. Phải xét timeline ID/history, không chỉ LSN.

### Bài 58 — Replay lag

Standby đã nhận/ghi WAL nhưng apply/replay chậm. Kiểm tra:
- replay_lsn và chênh lệch với flush_lsn.
- CPU/I/O latency trên standby.
- Hot standby conflicts, long-running readers, recovery logs và resource contention.

### Bài 59 — LSN delta

Không thể quy toàn bộ 2 GiB cho job nếu database có workload đồng thời. Đo trong môi trường cô lập, tạm ngừng writes khác nếu được phép, lấy nhiều samples, ghi stats_reset và đối chiếu pg_stat_wal/replication. Nếu không cô lập, ghi rõ đó là cluster-wide WAL delta trong window.

### Bài 60 — Unknown commit outcome

Server có thể đã commit và flush nhưng response bị mất, hoặc chưa commit trước khi connection đứt. Kỹ thuật xử lý:
1. Idempotency key/unique business constraint để retry không nhân đôi.
2. Reconnect và reconcile trạng thái theo business key/checkpoint/outbox.
Có thể kết hợp transactional outbox cho external side effects.

---

## 41. Bài tập nền tảng: kiểm tra khái niệm

### Bài 1 — Mục tiêu WAL

Nêu ba vai trò chính của WAL trong PostgreSQL. Vì sao không nên coi WAL là một application log thông thường?

### Bài 2 — Thứ tự ghi

Phát biểu write-ahead rule bằng lời của bạn. WAL cần bền trước loại dữ liệu nào được ghi xuống data files?

### Bài 3 — Các lớp tổ chức

Phân biệt record, page và segment. Cấp nào là đơn vị file vật lý?

### Bài 4 — Một câu SQL

Một INSERT vào bảng có primary key và hai secondary indexes có thể tạo những nhóm WAL records nào?

### Bài 5 — LSN

LSN là viết tắt của gì? Nó đánh địa chỉ vị trí nào và được biểu diễn phổ biến ra sao?

### Bài 6 — LSN và thời gian

Một LSN lớn hơn LSN khác có nghĩa transaction xảy ra muộn hơn bao nhiêu giây? Giải thích.

### Bài 7 — Tính delta

Viết một câu SQL dùng pg_wal_lsn_diff() để tính byte distance giữa hai LSN giả định.

### Bài 8 — Ba positions

Tên ba hàm SQL trả current WAL insert, write và flush LSN là gì?

### Bài 9 — Page LSN

Page LSN được lưu ở đâu và giúp recovery như thế nào?

### Bài 10 — Commit record

Commit record có thay thế các heap/index WAL records trước đó không? Vì sao?

### Bài 11 — Transaction interleaving

Vì sao records của hai transactions có thể xen kẽ trong cùng WAL segment?

### Bài 12 — Checkpoint

Checkpoint giải quyết bài toán gì cho crash recovery? Có phải mọi transaction đều phải đợi checkpoint mới được COMMIT không?

### Bài 13 — Filename

Tên WAL segment gồm ba trường hex nào? Trường nào giúp phân biệt lịch sử sau failover?

### Bài 14 — Segment lifecycle

Phân biệt recycle/reuse với archive. Vì sao số files trong pg_wal không phản ánh trực tiếp WAL rate?

### Bài 15 — Timeline

Sau promotion của standby, vì sao PostgreSQL tạo timeline mới? LSN có đủ để nhận diện history không?

### Bài 16 — Flush và durability

Nếu commit record đã được flush theo durability policy, PostgreSQL có thể phục hồi transaction sau crash dù heap page chưa ghi không?

### Bài 17 — synchronous_commit

Setting này ảnh hưởng điều gì? Nó có tắt WAL generation không?

### Bài 18 — Checkpoint, redo và commit

Phân biệt ba LSN/markers: checkpoint, redo và commit.

### Bài 19 — Timeline ID

Timeline ID được biểu diễn ở đâu trong WAL files? Vì sao cần xem history file?

### Bài 20 — Replication

Phân biệt sent_lsn, write_lsn, flush_lsn và replay_lsn.

### Bài 21 — Segment lookup

Viết query lấy WAL filename hiện tại và query lấy filename/offset từ một LSN.

### Bài 22 — pg_waldump

pg_waldump làm gì? Nó có hiển thị nguyên câu SQL UPDATE mà ứng dụng gửi không?

### Bài 23 — pg_walinspect

pg_walinspect cung cấp khả năng gì? Vì sao không nên inspect range quá rộng?

### Bài 24 — Segment switch

pg_switch_wal() dùng làm gì? Vì sao không phải lệnh dọn disk?

### Bài 25 — Archive retention

Một segment đã archive có thể vẫn còn trong pg_wal vì lý do gì?

### Bài 26 — Rollback

DML đã chạy rồi ROLLBACK có thể tạo WAL không? Vì sao?

### Bài 27 — Attribution

LSN delta trên production có thể bao gồm hoạt động nào ngoài transaction đang đo?

### Bài 28 — Control checkpoint

Hàm nào có thể đọc checkpoint metadata trong các PostgreSQL versions hỗ trợ? Vì sao cần quyền quản trị phù hợp?

### Bài 29 — Archiver failure

Nêu bốn điều cần kiểm tra khi archive failures tăng và pg_wal retained tăng.

### Bài 30 — Replay lag

Nếu standby đã flush WAL nhưng replay_lsn chậm, WAL đang mắc ở giai đoạn nào? Nêu ba nguyên nhân có thể.

---

## 42. Lời giải — bài tập nền tảng 1 đến 15

### Bài 1 — Mục tiêu WAL

WAL hỗ trợ crash recovery, physical streaming replication và continuous archiving/PITR; logical decoding cũng dựa trên WAL. Đây là luồng nhị phân có cấu trúc phục vụ tính đúng đắn của database, không phải log debug để xóa tùy ý.

### Bài 2 — Thứ tự ghi

WAL records mô tả thay đổi của data page phải được ghi bền trước khi data page tương ứng được ghi bền xuống data files. Điều này cho phép recovery redo khi crash xảy ra trước khi page write hoàn tất.

### Bài 3 — Record/page/segment

Record là đơn vị thông tin WAL; page là đơn vị block trong WAL stream có header; segment là file vật lý chứa một dải pages. Segment là cấp file vật lý.

### Bài 4 — Một INSERT

Có thể có heap insert record, B-tree records cho primary/secondary indexes, FPI trong trường hợp phù hợp, transaction/commit records và các records do triggers/foreign-key actions tạo thêm. Không có quan hệ một INSERT row = một WAL record.

### Bài 5 — LSN

Log Sequence Number là vị trí byte trong WAL stream, thường biểu diễn dạng hex X/Y. Nó dùng định vị record/segment và so sánh progress trong cùng timeline context.

### Bài 6 — LSN và thời gian

Không. LSN là byte position, không phải timestamp. WAL generation rate thay đổi theo workload, nên cùng một delta bytes có thể được tạo trong thời gian rất khác nhau.

### Bài 7 — Tính delta

~~~sql
SELECT pg_wal_lsn_diff(
    '0/2000000'::pg_lsn,
    '0/1000000'::pg_lsn
) AS wal_bytes;
~~~

### Bài 8 — Ba positions

- pg_current_wal_insert_lsn()
- pg_current_wal_lsn()
- pg_current_wal_flush_lsn()

Chúng lần lượt phản ánh insert, write và flush positions theo semantics PostgreSQL.

### Bài 9 — Page LSN

Page LSN nằm trong page header, thường được gọi là pd_lsn. Nó ghi vị trí WAL cuối cùng được áp dụng lên page và giúp redo logic xác định page đã có thay đổi tương ứng hay chưa. Nó không phải commit LSN.

### Bài 10 — Commit record

Không. Commit record ghi nhận transaction completion và metadata cần thiết; heap/index changes trước đó vẫn là các records riêng. Các records có thể xen kẽ với transaction khác.

### Bài 11 — Interleaving

Nhiều backend cùng tạo WAL records trong một stream toàn cluster. WAL insertion order xác định LSN order, nhưng transactions không được dành riêng một đoạn liên tục; records của chúng có thể xen kẽ.

### Bài 12 — Checkpoint

Checkpoint thiết lập recovery point và bảo đảm dirty pages cần thiết được ghi theo cơ chế checkpoint. Transaction không cần chờ checkpoint mới commit; commit durability dựa trên WAL flush policy.

### Bài 13 — Filename

Ba trường là timeline ID, log ID và segment number. Timeline ID phân biệt các nhánh lịch sử WAL sau failover/promotion.

### Bài 14 — Segment lifecycle

Recycle/reuse là dùng lại segment file cho vị trí WAL tương lai; archive là lưu segment hoàn chỉnh vào archive destination cho backup/PITR. File count bị ảnh hưởng bởi reuse và retention nên không bằng WAL bytes generated trong một window.

### Bài 15 — Timeline

Promotion có thể làm WAL history rẽ nhánh khỏi primary cũ; timeline mới đánh dấu nhánh đó. LSN một mình không đủ vì cùng giá trị LSN trên timelines khác nhau có thể thuộc histories khác nhau; cần timeline ID/history.
