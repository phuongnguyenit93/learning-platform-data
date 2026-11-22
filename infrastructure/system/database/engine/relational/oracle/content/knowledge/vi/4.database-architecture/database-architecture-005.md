# Bộ nhớ SGA: buffer cache, shared pool, redo log buffer và các vùng bổ sung

Khi một ứng dụng gửi SQL đến Oracle Database, hệ quản trị không nhất thiết đọc lại mọi block dữ liệu từ ổ đĩa hoặc phân tích lại toàn bộ câu SQL. Oracle dùng **System Global Area (SGA)**, một vùng bộ nhớ chung của **Oracle instance**, để giữ các block đang được truy cập, chia sẻ cấu trúc SQL và chuẩn bị bản ghi redo cho việc phục hồi sau sự cố.

SGA là chìa khóa để giải thích nhiều hiện tượng tưởng như mâu thuẫn: một truy vấn chạy lần hai nhanh hơn lần đầu; `COMMIT` có thể hoàn tất trước khi datafile được cập nhật; nhiều session sử dụng cùng một SQL cursor; và tăng RAM chưa chắc giúp hệ thống chạy nhanh hơn.

Sau bài học, bạn có thể:

- Phân biệt **SGA**, **PGA**, **instance** và các tệp dữ liệu trên đĩa.
- Giải thích nhiệm vụ và nội dung lưu trữ của **database buffer cache**, **shared pool** và **redo log buffer**.
- Theo dõi đường đi của `SELECT`, `UPDATE` và `COMMIT` qua bộ nhớ và tiến trình nền.
- Nhận biết **large pool**, **Java pool**, **Streams pool**, **fixed SGA** và một số vùng tùy chọn.
- Hiểu các chế độ cấp phát SGA và quan sát bộ nhớ qua các view Oracle mà không cần thay đổi cấu hình.
- Tránh những suy luận sai từ cache hit, hard parse, redo, checkpoint và các wait event.

> Các ví dụ tập trung vào kiến trúc Oracle Database hiện đại, bao gồm môi trường học tập Oracle Database Free. Kích thước, tham số khả dụng, đặc điểm bộ nhớ và quyền dùng một tính năng phụ thuộc phiên bản, edition, nền tảng và cấu hình cụ thể. Truy vấn các dynamic performance views `V$` có thể cần quyền quản trị hoặc quyền `SELECT` phù hợp.

## 1. Đặt SGA vào bức tranh Oracle Database

**Oracle database** là tập dữ liệu được lưu trong datafiles và những tệp điều khiển/redo cần thiết. **Oracle instance** là bộ nhớ và các tiến trình Oracle dùng để mở, quản lý và phục vụ database đó.

Một instance gồm:

1. **SGA:** bộ nhớ dùng chung cho các tiến trình và session phục vụ database.
2. **Background processes:** ví dụ Database Writer (`DBWn`), Log Writer (`LGWR`), Checkpoint (`CKPT`), System Monitor (`SMON`) và các tiến trình khác.

Khi ứng dụng kết nối, server process làm việc với SGA nhưng cũng cần **Program Global Area (PGA)**, vùng nhớ riêng cho hoạt động của tiến trình như work area của sort/hash hoặc trạng thái phục vụ phiên tùy kiến trúc kết nối.

```text
Ứng dụng / SQL client
        │ SQL và dữ liệu bind
        ▼
  Server process ──── PGA (bộ nhớ riêng tiến trình)
        │
        ▼
┌──────────────── ORACLE INSTANCE ─────────────────┐
│                                                  │
│  ┌────────────────── SGA ──────────────────────┐  │
│  │ Database buffer cache                     │  │
│  │ Shared pool                               │  │
│  │ Redo log buffer                           │  │
│  │ Large / Java / Streams pools              │  │
│  │ Fixed SGA và các vùng tùy chọn            │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  Background processes: DBWn, LGWR, CKPT, ...     │
└──────────────┬─────────────────────┬─────────────┘
               │ DBWn                │ LGWR
               ▼                     ▼
           Datafiles           Online redo logs
              └──────────────────────┘
                  Lưu trữ database
```

**SGA thuộc instance, không thuộc riêng một bảng hoặc schema.** Trong kiến trúc CDB/PDB, nhiều PDB có thể được phục vụ bởi cùng một instance và sử dụng tài nguyên bộ nhớ chung ở cấp instance, dù có những cơ chế quản trị tài nguyên theo PDB ở các phiên bản/edition phù hợp. Trong **Oracle RAC**, mỗi instance của cluster có SGA riêng, còn các instance có thể truy cập cùng database; việc trao đổi block giữa các instance là cơ chế bổ sung của RAC.

### 1.1. SGA khác PGA như thế nào?

| Đặc điểm | SGA | PGA |
| --- | --- | --- |
| Phạm vi | Bộ nhớ chia sẻ cấp instance | Bộ nhớ riêng của một tiến trình Oracle |
| Chứa gì? | Data blocks được cache, SQL cursor, metadata, redo records và vùng chung khác | SQL work area, trạng thái hoạt động và bộ nhớ riêng của tiến trình |
| Tham số thường gặp | `SGA_TARGET`, `SGA_MAX_SIZE` | `PGA_AGGREGATE_TARGET`, `PGA_AGGREGATE_LIMIT` |
| Ứng dụng trực tiếp đọc/ghi? | Thông qua các cơ chế của Oracle server process | Thông qua tiến trình Oracle xử lý yêu cầu |
| Tăng dung lượng có tác dụng gì? | Có thể giảm một số đọc block/parse hoặc hỗ trợ thành phần khác | Có thể giảm nhu cầu đổ một số phép sort/hash ra TEMP |

Không phải mọi byte RAM Oracle chiếm đều nằm trong SGA. Khi dự trù RAM cho database cần tính cả PGA, nền tảng OS, tiến trình phụ và bộ nhớ do ứng dụng khác sử dụng.

## 2. Bản đồ các vùng nhớ bên trong SGA

| Thành phần | Nội dung chính | Vì sao cần? |
| --- | --- | --- |
| **Database buffer cache** | Bản sao của database blocks đang được sử dụng; có cả block đã sửa nhưng chưa ghi xuống datafile | Giảm I/O lặp lại và giữ các block đang xử lý |
| **Shared pool** | Shared SQL areas, SQL cursor và plan, PL/SQL dùng chung, data dictionary cache và cấu trúc nội bộ | Tái sử dụng công việc parse, metadata và mã đã xử lý |
| **Redo log buffer** | Redo records mô tả thay đổi phục vụ recovery | Gom redo trong RAM cho LGWR ghi ra online redo logs |
| **Large pool** | Một số cấp phát chuyên biệt, ví dụ RMAN, shared server, parallel execution | Phục vụ các bộ đệm lớn/nhu cầu riêng |
| **Java pool** | Bộ nhớ hỗ trợ Java bên trong Oracle Database | Phục vụ Oracle JVM/tính năng Java khi có sử dụng |
| **Streams pool** | Một số cơ chế luồng dữ liệu, capture/replication, hàng đợi đệm | Hỗ trợ tính năng chuyên biệt theo phiên bản |
| **Fixed SGA** | Cấu trúc điều khiển thiết yếu của instance | Phối hợp hoạt động nội bộ |
| **Vùng tùy chọn** | Ví dụ In-Memory Column Store, Result Cache hoặc buffer pools KEEP/RECYCLE | Hỗ trợ những kiểu workload cụ thể nếu được bật/hỗ trợ |

Ba vùng đầu tiên rất quan trọng và **không thay thế nhau**: buffer cache chứa *block dữ liệu*; shared pool chứa *cấu trúc xử lý SQL/metadata*; redo log buffer chứa *thông tin phục hồi thay đổi*.

## 3. Database buffer cache: vùng nhớ chứa database blocks

### 3.1. Oracle truy cập block ra sao?

Dữ liệu bảng, chỉ mục và nhiều cấu trúc khác được lưu trên đĩa theo **database block**. Khi một câu SQL cần block:

1. Oracle xác định đường truy cập dữ liệu theo execution plan.
2. Nếu block phù hợp đang có trong buffer cache, Oracle có thể dùng bản sao ở bộ nhớ.
3. Nếu block không có sẵn, Oracle có thể đọc từ datafile vào cache.
4. Một số đường đọc như **direct path read** có thể bỏ qua buffer cache theo đường thông thường; không phải mọi lần đọc vật lý đều đưa block vào cache.

```text
      Datafiles trên đĩa
    [A] [B] [C] [D] [E]
         │       │
         │ đọc block cần thiết
         ▼       ▼
  ┌───────────────────────┐
  │  Database buffer cache│
  │       [B] [D]         │
  └───────────┬───────────┘
              │
              ▼
       Xử lý SELECT/JOIN...
              │
              ▼
         Trả kết quả
```

Khi câu SQL tiếp tục sử dụng block đang trong cache, một phần chi phí đọc đĩa có thể tránh được. Tuy nhiên cache không lưu tất cả block mãi mãi: Oracle quản lý và thay thế buffer theo cơ chế nội bộ để phục vụ workload.

**Cần phân biệt:** database buffer cache giữ database blocks. Nó **không mặc định giữ nguyên tập hàng kết quả của mỗi câu `SELECT`**. Query Result Cache (nếu được bật và phù hợp) là một cơ chế khác.

### 3.2. Logical read không đồng nghĩa physical read

Một **logical read** phản ánh hoạt động truy cập block ở cấp logic Oracle, thường bao gồm các hình thức truy cập như consistent gets hoặc current gets. Một **physical read** phản ánh việc phải đọc dữ liệu qua đường I/O theo định nghĩa bộ đếm cụ thể.

| Tình huống | Điều có thể xảy ra |
| --- | --- |
| Lần đầu cần block chưa có trong cache | Cần physical read và có thể cache block |
| Nhiều truy vấn cùng cần block còn ở cache | Có thể tận dụng bộ nhớ và vẫn phát sinh logical reads |
| Cache bị thay đổi do workload khác | Block cũ có thể bị thay thế, sau này phải đọc lại |
| Full scan lớn hoặc direct path | Có thể thực hiện I/O theo đường không dùng buffer cache thông thường |

Không lấy tỉ lệ `cache hit` của cả instance làm lời giải duy nhất cho mọi vấn đề hiệu năng. Một câu SQL đọc quá nhiều block do execution plan không phù hợp có thể chậm ngay cả khi phần lớn block đã nằm trong RAM.

### 3.3. Clean, dirty và pinned buffers

**Clean buffer** là bản block không chứa thay đổi còn phải ghi xuống datafile. **Dirty buffer** chứa thay đổi trong RAM chưa được ghi hết xuống datafile tương ứng. Một buffer cũng có thể đang được tiến trình **pin** hoặc truy cập theo cơ chế đồng bộ.

Ví dụ:

```text
Ban đầu:
  Datafile:  balance = 500
  Cache:     balance = 500  (clean)

Sau UPDATE:
  Datafile:  balance = 500
  Cache:     balance = 450  (dirty)

Sau DBWn ghi block:
  Datafile:  balance = 450
  Cache:     đã đồng bộ với dữ liệu trên file
```

Đây chỉ là minh họa mức khái niệm; Oracle có nhiều chi tiết đồng thời, undo và consistent read. Chính sách tìm buffer trống/tái sử dụng cũng phức tạp hơn một vòng LRU thuần túy.

### 3.4. Ai ghi dirty buffers xuống datafile?

Tiến trình **Database Writer (`DBWn`)** ghi các dirty blocks từ buffer cache xuống datafiles khi cần, chẳng hạn để có buffer tái sử dụng, đáp ứng áp lực I/O hoặc phục vụ checkpoint. **CKPT** phối hợp thông tin checkpoint và cập nhật metadata thích hợp, không phải tiến trình ghi thay toàn bộ dirty blocks của DBWn.

Điểm then chốt: **`COMMIT` không yêu cầu DBWn ghi ngay toàn bộ dirty blocks của transaction xuống datafiles**. Cơ chế bền vững của commit đồng bộ thường dựa trên redo đã được LGWR ghi ra online redo log trước khi báo thành công.

### 3.5. Consistent read và undo có liên quan gì?

Oracle hỗ trợ **read consistency** để truy vấn thấy dữ liệu phù hợp với snapshot của câu lệnh hoặc transaction, tùy isolation level. Nếu block hiện tại chứa thay đổi không phù hợp với snapshot, Oracle có thể dùng **undo** để tạo phiên bản consistent-read của block.

Undo được lưu trong các undo segments/tablespace của database; các block undo có thể được cache/truy cập qua cơ chế buffer cache. **Không có một vùng SGA riêng tên “undo pool”** tương đương buffer cache. Undo phục vụ rollback và read consistency; redo phục vụ phục hồi những thay đổi cần thiết. Cả hai có liên hệ nhưng nhiệm vụ không giống nhau.

## 4. Shared pool: chia sẻ SQL, PL/SQL và metadata

Shared pool cung cấp các cấu trúc dùng chung cho việc parse, tối ưu, thực thi và quản trị SQL. Hai nhóm thường gặp là:

- **Library cache:** giữ shared SQL areas/cursors, execution plans, mã PL/SQL đã được xử lý và những cấu trúc dùng chung.
- **Data dictionary cache** (row cache): giữ metadata thường cần về objects, users, quyền, định nghĩa và thông tin nội bộ.

```text
                         SHARED POOL
             ┌─────────────────────────────┐
             │ Library cache               │
             │ • SQL cursor / SQL area     │
             │ • Execution plan            │
             │ • PL/SQL dùng chung         │
             ├─────────────────────────────┤
             │ Data dictionary cache       │
             │ • Metadata bảng, cột, quyền │
             │ • Thông tin object khác     │
             ├─────────────────────────────┤
             │ Các cấp phát chung khác     │
             └─────────────────────────────┘
```

### 4.1. Parse, hard parse và soft parse

Khi nhận SQL, Oracle cần kiểm tra cú pháp/ngữ nghĩa, object và quyền, tìm cấu trúc cursor có thể dùng lại, chọn/áp dụng execution plan và thực thi.

**Hard parse** thực hiện những công việc tạo cấu trúc/plan mới khi không có cursor phù hợp để tái sử dụng. Công việc này có thể tốn CPU và gây tranh chấp. **Soft parse** thường có thể dùng lại cấu trúc chia sẻ, giảm bớt một số bước; soft parse không có nghĩa hệ quản trị không phải làm gì.

Khả năng chia sẻ cursor chịu ảnh hưởng của nhiều yếu tố: văn bản SQL, schema, quyền, kiểu dữ liệu bind, settings, metadata, trạng thái object và các cơ chế của optimizer. Hai câu SQL trông giống nhau không nhất thiết chia sẻ cùng một child cursor.

### 4.2. Bind variables giảm nhu cầu tạo SQL khác nhau

Giả sử bảng `orders` có cột `order_id`:

```sql
SELECT order_id, amount FROM orders WHERE order_id = 101;
SELECT order_id, amount FROM orders WHERE order_id = 102;
```

Hai câu trên chứa literal khác nhau. Ứng dụng thực hiện nhiều lần có thể dùng:

```sql
SELECT order_id, amount
FROM orders
WHERE order_id = :order_id;
```

Rồi gán `:order_id` lần lượt bằng 101, 102. Cách này thường tăng cơ hội chia sẻ SQL/cursor, giảm chi phí parse và giúp phòng tránh SQL injection khi bind parameter đúng cách. Nó **không đảm bảo chỉ có một execution plan duy nhất**: Oracle có thể tạo nhiều child cursors/plans khi có lý do hợp lệ, chẳng hạn kiểu bind hoặc đặc tính dữ liệu.

Một câu SQL có thể cần hard parse lại sau DDL hoặc khi metadata/cursor bị invalid. Vì vậy, hiện tượng hard parse cao cần được điều tra cả về SQL design, invalidation và workload, không chỉ kích thước shared pool.

### 4.3. Data dictionary cache giúp gì?

Khi xét câu:

```sql
SELECT customer_id
FROM customers
WHERE customer_id = :id;
```

Oracle cần biết `customers` thuộc schema nào, định nghĩa cột ra sao, user có quyền gì và metadata nào cần cho việc lập kế hoạch. Những thông tin có thể được lưu/tái sử dụng trong các cấu trúc của shared pool để giảm việc tra cứu lặp lại.

**Shared pool không lưu trực tiếp toàn bộ hàng của bảng để thay database buffer cache.** Shared pool tập trung vào cấu trúc SQL, mã và metadata; buffer cache tập trung vào data blocks.

### 4.4. Điều gì xảy ra nếu shared pool bị áp lực?

Các dấu hiệu có thể bao gồm nhiều hard parses, tranh chấp liên quan library cache hoặc lỗi cấp phát `ORA-04031` trong một số hoàn cảnh. `ORA-04031` có thể liên quan bộ nhớ không đủ, phân mảnh, cấp phát đặc biệt hoặc cấu hình pool; không nhất thiết chỉ cần tăng RAM.

Nên đo tần suất parse, số SQL không tái sử dụng, invalidation, pattern cấp phát và tình trạng pool trước khi điều chỉnh `SHARED_POOL_SIZE`.

## 5. Redo log buffer: bộ đệm phục vụ phục hồi

### 5.1. Redo records là gì?

**Redo records** mang thông tin về những thay đổi cần thiết để Oracle có thể phục hồi database sau sự cố. Redo **không đơn thuần là bản sao nguyên văn câu SQL**. Oracle tạo redo phù hợp cho các thay đổi data/undo và cấu trúc liên quan theo cơ chế ghi log nội bộ.

Những redo records được đưa vào **redo log buffer** trong SGA. Tiến trình **Log Writer (`LGWR`)** ghi redo ra **online redo log files** (trên đĩa hoặc ASM).

```text
       INSERT / UPDATE / DELETE
                 │
       ┌─────────┴─────────┐
       ▼                   ▼
Database buffer cache   Redo log buffer
   (dirty data/undo)      (redo records)
       │                   │
       │ DBWn              │ LGWR
       ▼                   ▼
   Datafiles         Online redo logs
```

Buffer cache và redo log buffer chứa hai loại thông tin khác nhau, được ghi qua hai tiến trình khác nhau đến hai nhóm tệp khác nhau.

### 5.2. `COMMIT` thực sự đợi điều gì?

Với **commit đồng bộ thông thường**:

1. DML thay đổi những block phù hợp trong buffer cache và tạo redo tương ứng.
2. Transaction yêu cầu `COMMIT`; Oracle tạo thông tin commit cần thiết.
3. LGWR ghi redo cần thiết của transaction, bao gồm bản ghi commit, ra online redo log.
4. Khi việc ghi redo theo yêu cầu hoàn tất, Oracle có thể báo `COMMIT` thành công.
5. DBWn có thể ghi các dirty data blocks xuống datafiles sau đó.

Đó là nguyên lý **write-ahead logging**: Oracle cần đảm bảo redo thích hợp được ghi bền vững trước khi các thay đổi dữ liệu liên quan được coi là an toàn trong cơ chế ghi/recovery. Nếu instance gặp sự cố trước khi DBWn ghi hết dirty blocks, Oracle có thể dùng redo để phục hồi những thay đổi đã commit theo quy trình recovery.

> Có các tùy chọn commit có hành vi chờ/ghi khác chế độ đồng bộ mặc định. Trong phạm vi bài này, mô tả trên áp dụng cho commit đồng bộ thông thường; không suy ra mọi cấu hình đều bảo đảm cùng thời điểm durability.

### 5.3. LGWR có chỉ ghi khi commit?

Không. Oracle cũng có thể đẩy redo theo những điều kiện như lượng buffer đang sử dụng, chu kỳ nền, log switch và yêu cầu nội bộ khác. Các ngưỡng/chi tiết triển khai có thể thay đổi theo phiên bản.

**Redo log buffer là vùng RAM ngắn hạn.** Nó không phải lịch sử lưu trữ giao dịch vĩnh viễn. **Online redo log files** mới là nơi redo đã được ghi bền vững, và các nhóm online redo log được luân phiên sử dụng. Khi cơ sở dữ liệu dùng chế độ `ARCHIVELOG`, các redo log thích hợp có thể được sao lưu thành **archived redo logs** theo quy trình archiving.

### 5.4. Phân biệt các thành phần “log”

| Thành phần | Vị trí | Vai trò |
| --- | --- | --- |
| Redo log buffer | Trong SGA/RAM | Giữ redo tạm thời trước khi LGWR ghi |
| Online redo log files | Trên đĩa/ASM | Lưu redo để phục hồi instance |
| Archived redo logs | Lưu trữ archive khi đã cấu hình | Phục vụ recovery/backup theo chính sách |
| Undo segments | Datafiles/undo tablespace; block có thể được cache | Rollback và read consistency |
| Database buffer cache | Trong SGA/RAM | Giữ các database blocks được xử lý |
| Log ứng dụng | Do ứng dụng tự quản lý | Ghi sự kiện nghiệp vụ/kỹ thuật; không thay thế Oracle redo |

Đừng nhầm thao tác `COMMIT` của ứng dụng với việc tất cả datafiles đã được cập nhật; và đừng nhầm redo log buffer với các tệp online redo log.

## 6. Theo dấu một transaction qua ba vùng nhớ chính

Giả sử bảng `accounts(account_id, balance)` đã tồn tại. Ví dụ chuyển 100 đơn vị:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
```

Đây chỉ là mô tả kiến trúc. Ứng dụng thật còn phải kiểm tra tính hợp lệ của số dư, khóa, transaction và rollback nếu gặp lỗi.

| Bước | Thành phần tham gia | Hoạt động |
| --- | --- | --- |
| 1. Nhận SQL | Shared pool | Tìm shared cursor, kiểm tra metadata hoặc thực hiện parse/optimization khi cần |
| 2. Tìm hàng | Buffer cache và I/O | Đọc/định vị block, có thể đọc datafile nếu chưa có trong cache |
| 3. Thay đổi | Buffer cache và undo | Sửa các block liên quan, quản lý thông tin để rollback/read consistency |
| 4. Tạo redo | Redo log buffer | Ghi nhận các redo records cần thiết cho thay đổi |
| 5. Commit | LGWR và online redo logs | Ghi redo cần thiết; sau khi đáp ứng điều kiện commit đồng bộ, xác nhận với client |
| 6. Ghi datafiles | DBWn và datafiles | Ghi dirty blocks khi thích hợp, có thể sau commit |

```text
SQL UPDATE
  │
  ├── Parse/cursor ──► SHARED POOL
  │
  ├── Sửa block ────► BUFFER CACHE ── DBWn ──► DATAFILES
  │
  └── Tạo redo ────► REDO LOG BUFFER ─ LGWR ──► ONLINE REDO
                              ▲
                              │
                           COMMIT
```

Trong kịch bản crash sau commit nhưng trước lần ghi datafile tương ứng, redo là thành phần thiết yếu cho instance recovery. Nếu transaction chưa commit, việc phục hồi còn phải xử lý phần thay đổi chưa hoàn tất bằng cơ chế undo.

Đường đi này giúp tách bạch **hiệu năng đọc datafile**, **tần suất parse** và **latency ghi redo/commit**: chúng liên quan những vùng SGA khác nhau.

## 7. Các vùng bổ sung trong SGA

### 7.1. Large pool

**Large pool** phục vụ một số cấp phát chuyên biệt, thường liên quan:

- Buffer cho một số tác vụ **RMAN backup/restore**.
- **User Global Area (UGA)** trong một số cấu hình **shared server**.
- Bộ đệm thông điệp của **parallel execution** theo mô hình và phiên bản.

Việc tách một số cấp phát lớn khỏi shared pool có thể giúp shared pool ít chịu áp lực từ những đối tượng có đặc tính cấp phát khác SQL cursor. Tuy vậy, không phải mọi tác vụ RMAN/parallel query đều dùng large pool theo cùng cách; còn tùy phiên bản và cấu hình.

Tham số thường gặp: `LARGE_POOL_SIZE`.

### 7.2. Java pool

**Java pool** được dùng khi database chạy Java bên trong Oracle, chẳng hạn Oracle JVM hoặc Java stored procedures khi khả dụng. Nó khác hoàn toàn **JVM heap của ứng dụng Java/Spring Boot**: JVM của ứng dụng nằm ở tiến trình bên ngoài database, không ở SGA.

Tham số thường gặp: `JAVA_POOL_SIZE`.

### 7.3. Streams pool

**Streams pool** hỗ trợ một số cơ chế luồng dữ liệu, capture, replication hoặc hàng đợi có buffer trong những cấu hình Oracle nhất định. Tên vùng nhớ có nguồn gốc lịch sử từ Oracle Streams. **Không suy ra rằng tính năng Oracle Streams cũ còn được hỗ trợ chỉ vì instance có Streams pool**; các thành phần sử dụng pool thay đổi theo phiên bản.

Tham số thường gặp: `STREAMS_POOL_SIZE`.

### 7.4. Fixed SGA

**Fixed SGA** chứa những cấu trúc điều khiển nội bộ thiết yếu của instance. Một số view tổng quan sẽ hiển thị mục `Fixed Size`. Đây không phải nơi ứng dụng quyết định lưu dữ liệu tùy ý, và không có nghĩa người quản trị nên chỉnh kích thước vùng này như `DB_CACHE_SIZE`.

### 7.5. In-Memory Column Store, Result Cache và các buffer pools

**In-Memory Column Store (IMCS)**, nếu được phiên bản/edition và giấy phép cho phép, có thể giữ biểu diễn dữ liệu theo cột trong SGA cho một số workload phân tích. Nó bổ sung cho cách lưu row-format truyền thống, **không phải toàn bộ database buffer cache được đổi thành column store**.

**Result Cache**, khi được bật và phù hợp, có thể lưu kết quả truy vấn/hàm để sử dụng lại và quản lý invalidation theo thay đổi của dữ liệu phụ thuộc. Result Cache khác **database buffer cache**: một bên lưu kết quả đã tính, bên kia chủ yếu lưu database blocks. Cách cấp phát bộ nhớ result cache trong SGA/shared pool phụ thuộc thiết kế và phiên bản.

**DEFAULT, KEEP, RECYCLE** là các buffer pool có thể xuất hiện trong cơ chế quản lý database buffer cache. Chúng là các chính sách/vùng phân loại của **buffer cache**, không phải pool chứa SQL cursor như shared pool. Tên KEEP không phải lời cam kết mọi block sẽ luôn ở RAM; chỉ cấu hình khi đã hiểu mẫu truy cập block.

## 8. Quản lý kích thước SGA

Oracle có thể phân bổ bộ nhớ theo các **granules** và tái điều chỉnh một số thành phần theo chế độ quản lý. Kích thước một granule phụ thuộc cấu hình/nền tảng; không mặc định các pool thay đổi từng byte.

### 8.1. Các tham số cần biết

| Tham số | Mục đích | Lưu ý |
| --- | --- | --- |
| `SGA_TARGET` | Mục tiêu tổng SGA trong **Automatic Shared Memory Management (ASMM)** | Oracle phân phối lại bộ nhớ giữa một số thành phần |
| `SGA_MAX_SIZE` | Giới hạn trên của SGA trong vòng đời instance | Thay đổi mức trần thường phải khởi động lại |
| `DB_CACHE_SIZE` | Cấu hình kích thước database buffer cache mặc định | Với ASMM, giá trị đặt rõ thường là mức tối thiểu tương ứng |
| `SHARED_POOL_SIZE` | Cấu hình kích thước shared pool | Với ASMM, giá trị đặt rõ thường là mức tối thiểu tương ứng |
| `LOG_BUFFER` | Kích thước redo log buffer được cấu hình | Có quy tắc quản lý riêng, không co giãn tùy ý như mọi thành phần ASMM |
| `LARGE_POOL_SIZE` | Cấu hình large pool | Phù hợp khi workload thật sự dùng vùng này |
| `JAVA_POOL_SIZE` | Cấu hình Java pool | Liên quan Java bên trong database |
| `STREAMS_POOL_SIZE` | Cấu hình Streams pool | Liên quan những tính năng đặc biệt |
| `MEMORY_TARGET` | Mục tiêu **Automatic Memory Management (AMM)** quản lý cả SGA và PGA ở mức tổng thể | Khác `SGA_TARGET`; hỗ trợ phụ thuộc OS/cấu hình |
| `MEMORY_MAX_TARGET` | Giới hạn bộ nhớ cho AMM | Có điều kiện riêng khi thay đổi |
| `PGA_AGGREGATE_TARGET` | Mục tiêu tổng PGA | PGA không nằm trong SGA |

### 8.2. ASMM, AMM và thủ công

**Quản lý thành phần SGA thủ công:** Khi `SGA_TARGET=0` và không sử dụng AMM, quản trị viên phải chủ động xác định những vùng cần thiết bằng các tham số thành phần.

**ASMM:** Khi `SGA_TARGET>0` và `MEMORY_TARGET=0`, Oracle có thể tự điều chỉnh kích thước một số thành phần SGA trong ngân sách chung, còn PGA được quản lý bằng cơ chế riêng. Giá trị thành phần đặt thủ công có thể làm giới hạn mức Oracle được phép thu nhỏ.

**AMM:** Khi `MEMORY_TARGET>0` và nền tảng hỗ trợ, Oracle có thể phân phối mục tiêu bộ nhớ tổng giữa SGA và PGA. Điều này không có nghĩa tổng mức RAM thực tế của database/OS sẽ luôn bằng chính xác `MEMORY_TARGET`.

Trên Linux, AMM có tương tác với HugePages/shared memory; trong container còn cần xét giới hạn memory và các vùng shared memory do runtime cung cấp. Không nên lấy một bộ thông số từ server khác áp thẳng lên máy thực hành có dung lượng nhỏ.

### 8.3. Vì sao không tăng tất cả các pool?

- RAM dành thêm cho SGA sẽ còn ít hơn cho PGA, hệ điều hành và phần mềm khác. Nếu OS phải swap, hệ thống có thể chậm hơn.
- Buffer cache lớn hơn không sửa được SQL scan không cần thiết hoặc thiếu index.
- Shared pool lớn hơn không loại bỏ nguyên nhân ứng dụng tạo nhiều SQL khác nhau bằng literal.
- Redo log buffer lớn hơn không làm ổ đĩa chứa online redo logs ghi nhanh hơn.
- Một số thành phần có kích thước tối thiểu/tối đa hoặc yêu cầu restart riêng; những giới hạn edition phải được tôn trọng.

Quyết định đổi kích thước nên dựa trên **workload, chỉ số và khả năng cấp phát thực tế**, không chỉ một tỉ lệ cache hit.

## 9. Quan sát bộ nhớ SGA qua SQL

Các truy vấn sau **chỉ đọc** và dùng để xem dữ liệu vận hành. Chúng thường yêu cầu tài khoản có quyền thích hợp trên các dynamic performance views `V$`. Không cấp quyền `DBA` cho user ứng dụng chỉ để chạy bài thực hành này.

### 9.1. Kích thước SGA tổng quan

```sql
SELECT name,
       ROUND(value / POWER(1024, 2), 2) AS mb
FROM v$sga;
```

Kết quả thường có các mục như `Fixed Size`, `Variable Size`, `Database Buffers` và `Redo Buffers`. **`Variable Size` không phải RAM “đang rảnh”** mà là một nhóm trong báo cáo tổng của Oracle.

Quan sát chi tiết khác:

```sql
SELECT name,
       ROUND(bytes / POWER(1024, 2), 2) AS mb,
       resizeable
FROM v$sgainfo
ORDER BY name;
```

Cột `RESIZEABLE` mô tả khả năng điều chỉnh vùng bộ nhớ được báo cáo, không tự cho phép sửa cấu hình ngay lập tức.

### 9.2. Những component SGA có khả năng điều chỉnh

```sql
SELECT component,
       ROUND(current_size / POWER(1024, 2), 2) AS current_mb,
       ROUND(user_specified_size / POWER(1024, 2), 2) AS user_specified_mb
FROM v$sga_dynamic_components
WHERE current_size > 0
ORDER BY current_size DESC;
```

`CURRENT_SIZE` mô tả kích thước hiện tại của thành phần mà view ghi nhận; `USER_SPECIFIED_SIZE` là kích thước do người dùng chỉ định nếu có. Không đòi hỏi view này phải hiển thị mọi mục trong sơ đồ SGA: đây là danh sách các dynamic components, không phải toàn bộ taxonomy bộ nhớ.

### 9.3. Mức cấp phát trong các pool

```sql
SELECT NVL(pool, '(khong thuoc pool)') AS memory_pool,
       name,
       ROUND(bytes / POWER(1024, 2), 2) AS mb
FROM v$sgastat
ORDER BY bytes DESC
FETCH FIRST 30 ROWS ONLY;
```

`V$SGASTAT` liệt kê nhiều loại cấp phát trong SGA. Chỉ số `free memory` cần được giải thích trong ngữ cảnh từng pool, allocator và cơ chế co giãn; không nên xem một dòng `free memory` là tổng số RAM có thể sử dụng của toàn Oracle.

### 9.4. Kiểm tra tham số

Trong SQL*Plus hoặc SQLcl:

```sql
SHOW PARAMETER memory_target
SHOW PARAMETER sga_target
SHOW PARAMETER sga_max_size
SHOW PARAMETER db_cache_size
SHOW PARAMETER shared_pool_size
SHOW PARAMETER log_buffer
SHOW PARAMETER pga_aggregate_target
```

Hoặc dùng câu SQL:

```sql
SELECT name, display_value, isdefault, issys_modifiable
FROM v$parameter
WHERE name IN (
    'memory_target',
    'memory_max_target',
    'sga_target',
    'sga_max_size',
    'db_cache_size',
    'shared_pool_size',
    'log_buffer',
    'pga_aggregate_target'
)
ORDER BY name;
```

Giá trị instance đang dùng có thể khác giá trị đặt trong SPFILE chờ restart. `ISDEFAULT` và `ISSYS_MODIFIABLE` giúp người quản trị diễn giải trạng thái tham số nhưng không thay thế việc kiểm tra quy tắc thay đổi của từng tham số.

### 9.5. Một số thống kê có thể so sánh theo thời gian

```sql
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'parse count (total)',
    'parse count (hard)'
)
ORDER BY name;
```

Các bộ đếm trên thường tích lũy theo tuổi thọ instance. Hãy lấy **độ chênh giữa hai thời điểm trong cùng một khoảng workload** nếu muốn đánh giá xu hướng. Các số tổng hợp không tự xác định một SQL cụ thể chậm vì buffer cache hay shared pool, và physical reads không luôn tương đương số thao tác đĩa vật lý cấp thiết bị.

## 10. Nhận diện triệu chứng hiệu năng

| Triệu chứng | Nên xem trước | Kết luận cần tránh |
| --- | --- | --- |
| Truy vấn đọc rất nhiều block, I/O cao | SQL plan, index, cách đọc, buffer cache và workload | “Chắc chắn chỉ cần tăng `DB_CACHE_SIZE`” |
| Hard parse nhiều, CPU parse cao | SQL literal/bind, cursor sharing, metadata invalidation và shared pool | “Tăng `SHARED_POOL_SIZE` sẽ luôn sửa được” |
| `ORA-04031` | Cấp phát/fragmentation trong pool báo lỗi, SQL/cursor và cấu hình | “Mọi lỗi `ORA-04031` chỉ do thiếu RAM tổng” |
| Wait `log file sync` cao | Tần suất commit, LGWR, latency ghi redo | “Chỉ cần tăng `LOG_BUFFER`” |
| Wait `log buffer space` cao | Áp lực tạo redo, LGWR và đường ghi redo | “Không cần kiểm tra thiết bị lưu trữ” |
| Wait `free buffer waits` | Khả năng tái sử dụng buffer, tốc độ DBWn/I/O, workload | “Mọi vấn đề free buffer đều do cache nhỏ” |
| Wait `buffer busy waits` | Nhiều phiên tranh chấp block/buffer đang nóng | “Tranh chấp block đồng nghĩa thiếu SGA” |
| OS swap hoặc database không khởi động | Tổng SGA/PGA/OS, giới hạn VM/container và RAM host | “Cấp tất cả pool lớn hơn” |

Ví dụ hai wait có chữ **buffer** lại khác nhau: `free buffer waits` liên quan tìm buffer có thể tái sử dụng; `buffer busy waits` có thể liên quan tranh chấp đồng thời trên cùng block. Phương án xử lý phải dựa trên số liệu, không dựa vào từ khóa trong tên wait.

Một quy trình điều tra hợp lý:

1. Xác định tác vụ chậm: parse, truy vấn đọc, DML hay `COMMIT`.
2. Đo ở khoảng thời gian thật sự xảy ra workload và lưu baseline.
3. Kết hợp SQL plan, CPU, I/O, waits và thống kê vùng nhớ liên quan.
4. Thử thay đổi một yếu tố có lý do, đo lại kết quả và cân nhắc tài nguyên OS.

Một số công cụ/chức năng phân tích sâu như AWR/ASH có điều kiện về edition/quyền/giấy phép. Có thể bắt đầu từ dynamic performance views mà môi trường thực hành được phép sử dụng.

## 11. Những hiểu nhầm cần loại bỏ

**“SGA là toàn bộ RAM Oracle sử dụng.”** Sai: còn PGA, bộ nhớ tiến trình và OS.

**“Buffer cache lưu mọi kết quả SELECT.”** Sai: buffer cache lưu database blocks; query result cache là cơ chế khác.

**“COMMIT xong là mọi block đã vào datafile.”** Sai đối với commit đồng bộ thông thường: tính bền vững dựa vào redo cần thiết đã được LGWR ghi, DBWn có thể cập nhật datafiles về sau.

**“Redo log buffer và online redo log là một.”** Sai: buffer ở RAM, online redo log ở lưu trữ bền vững.

**“Shared pool chứa nguyên dữ liệu bảng/index.”** Sai: shared pool giữ cursor, plan, metadata và cấu trúc chung; block dữ liệu thường qua buffer cache.

**“PGA là một pool bên trong SGA.”** Sai: PGA là bộ nhớ riêng của tiến trình, có cơ chế cấp phát khác.

**“Có đủ cache thì hoàn toàn không cần I/O.”** Sai: redo vẫn phải ghi, dirty blocks vẫn cần được ghi, những truy cập direct path/TEMP và workload lớn còn sinh I/O.

**“Tăng SGA luôn giúp nhanh hơn.”** Sai: thiếu PGA hoặc khiến OS swap có thể làm chậm toàn hệ thống.

## 12. Bài thực hành quan sát an toàn

**Điều kiện:** Oracle Database đang chạy; nếu cần quan sát `V$SGA`, `V$SGAINFO` hoặc `V$SGA_DYNAMIC_COMPONENTS` thì dùng user có quyền xem view tương ứng. Bài tập không yêu cầu sửa cấu hình instance.

**Bước 1 — Xác định instance và PDB hiện tại.**

```sql
SELECT SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
```

Nếu đang kết nối vào PDB, kết quả container thường cho biết tên PDB. Ghi nhớ rằng các thông số SGA quan sát ở cấp instance không có nghĩa chỉ PDB hiện tại sở hữu toàn bộ SGA.

**Bước 2 — Xem kích thước SGA.**

```sql
SELECT name, ROUND(value / POWER(1024, 2), 1) AS mb
FROM v$sga;
```

Tìm những dòng liên quan database buffers, redo buffers và variable size. Đọc tiếp component động:

```sql
SELECT component, ROUND(current_size / POWER(1024, 2), 1) AS mb
FROM v$sga_dynamic_components
WHERE current_size > 0
ORDER BY current_size DESC;
```

Nếu gặp lỗi thiếu quyền, ghi nhận và nhờ người quản trị truy vấn; không cấp `DBA` cho tài khoản ứng dụng để học một view.

**Bước 3 — Giải thích đường đi của một câu SELECT.**

```sql
SELECT COUNT(*) FROM orders;
```

Giả sử bảng `orders` có tồn tại. Hãy giải thích shared pool có thể tái sử dụng cursor/metadata ra sao, buffer cache có thể phục vụ block thế nào và vì sao Oracle vẫn có thể chọn direct path read. Không cần chạy câu SQL trên một bảng chưa tồn tại.

**Bước 4 — Giải thích một lần UPDATE và COMMIT.**

```sql
UPDATE orders SET status = 'DONE' WHERE order_id = 100;
COMMIT;
```

Giả sử bảng/cột tồn tại và transaction thành công. Hãy tự trả lời:

1. Block nào có thể trở thành dirty trong buffer cache?
2. Redo records nằm ở vùng SGA nào trước khi LGWR ghi?
3. LGWR ghi ra tệp gì và DBWn ghi ra tệp gì?
4. Vì sao transaction có thể được xác nhận bền vững sau commit dù DBWn chưa ghi hết dirty blocks?

**Bước 5 — Đặt giả thuyết hiệu năng.**

Nếu ứng dụng tạo SQL có literal mới ở mỗi lần chạy, shared pool có thể chịu chi phí gì? Nếu `COMMIT` từng dòng chậm, cần điều tra tần suất commit và I/O của LGWR ra sao? Nếu OS swap, vì sao tăng `SGA_TARGET` chưa chắc đúng?

Những câu hỏi này giúp liên hệ vai trò của từng vùng bộ nhớ với dữ liệu đo thực tế.

## 13. Mô hình ghi nhớ

```text
SGA = bộ nhớ chung của Oracle instance

Buffer cache    → giữ database blocks, có thể chứa dirty blocks
Shared pool     → giữ SQL cursor/plan, PL/SQL và metadata dùng chung
Redo log buffer → giữ redo records trước khi LGWR ghi xuống online redo
Large pool      → một số cấp phát lớn/chuyên biệt
Java pool       → hỗ trợ Java trong Oracle Database
Streams pool    → hỗ trợ một số tính năng luồng dữ liệu/capture
Fixed SGA       → thông tin điều khiển cốt lõi của instance
```

Các quan hệ cần thuộc:

- **Truy vấn:** shared pool hỗ trợ SQL cursor/metadata; dữ liệu được đọc qua buffer cache hoặc đường I/O phù hợp.
- **DML:** Oracle thay đổi block trong buffer cache và tạo redo cho những thay đổi cần ghi log.
- **Commit đồng bộ:** LGWR ghi redo cần thiết trước khi Oracle xác nhận thành công; DBWn có thể ghi datafiles sau.

Hiểu ba đường đi này tạo nền tảng để học sâu hơn về background processes, checkpoint, undo/redo recovery, quản lý bộ nhớ và chẩn đoán hiệu năng Oracle Database.
