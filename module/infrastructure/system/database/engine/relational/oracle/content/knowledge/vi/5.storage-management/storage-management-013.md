# Theo dõi dung lượng, xu hướng tăng trưởng và cảnh báo đầy đĩa trong Oracle Database

Một Oracle Database có thể vận hành bình thường suốt nhiều tháng rồi đột ngột gặp lỗi khi bảng không thể mở rộng, truy vấn cần thêm TEMP, UNDO không còn đủ chỗ hoặc hệ thống không thể ghi archived redo logs. Vấn đề không chỉ nằm ở tổng số gigabyte còn trống: **Oracle quản lý dung lượng ở nhiều lớp**, và một lớp còn chỗ không bảo đảm các lớp bên dưới vẫn đủ khả năng cấp phát.

Ví dụ, datafile có thể đang bật `AUTOEXTEND` với giới hạn 100 GB nhưng filesystem chỉ còn 2 GB trống. Trên giao diện theo dõi tablespace, dung lượng mở rộng theo cấu hình có vẻ lớn; trên hệ điều hành, nguy cơ ghi đầy đĩa lại rất gần. Ngược lại, filesystem có hàng trăm GB trống nhưng datafile đạt `MAXSIZE` hoặc tablespace không còn extent cấp phát được thì câu lệnh `INSERT` vẫn có thể thất bại.

Bài học này trình bày cách **quan sát dung lượng hiện tại, ghi lịch sử để tính tốc độ tăng trưởng, thiết kế cảnh báo và xử lý sớm các dấu hiệu sắp hết chỗ** trong Oracle Database. Trọng tâm là hoạt động đọc và đánh giá, không phải thay đổi kích thước tệp một cách vội vàng.

Sau khi học, bạn có thể:

- Phân biệt dung lượng **tablespace**, **datafile**, **segment**, **TEMP/UNDO**, **filesystem hoặc ASM** và **Fast Recovery Area (FRA)**.
- Đọc các chỉ số `USED_SPACE`, `TABLESPACE_SIZE`, `USED_PERCENT`, `BYTES`, `MAXBYTES` và `AUTOEXTENSIBLE` theo đúng ngữ cảnh.
- Viết truy vấn SQL để tìm tablespace đang đầy, datafile có thể mở rộng và đối tượng chiếm nhiều dung lượng.
- Theo dõi lịch sử thay vì chỉ nhìn một ảnh chụp, ước tính tốc độ tăng trưởng và **days to full** một cách có điều kiện.
- Tạo quy tắc cảnh báo nhiều mức, có ngưỡng theo tỷ lệ sử dụng, dung lượng dự phòng và thời gian dự báo.
- Lập quy trình chẩn đoán an toàn khi phát sinh lỗi thiếu dung lượng hoặc archive/FRA gần đầy.

> Các câu lệnh `SELECT` dùng các dictionary/dynamic performance views của Oracle, có thể yêu cầu quyền `SELECT` trên view liên quan hoặc một tài khoản quản trị phù hợp. Một số view và phép tính có khác biệt theo phiên bản, container CDB/PDB, storage backend và cách tự động mở rộng. Khi không có quyền, hãy nhờ người quản trị cung cấp số liệu; không cần cấp toàn quyền `DBA` cho tài khoản ứng dụng chỉ để xem dung lượng.

## 1. “Đầy đĩa” có thể xảy ra ở nhiều lớp

Đường đi lưu trữ cơ bản của Oracle:

```text
Ứng dụng INSERT / UPDATE / CREATE INDEX / SORT / COMMIT
                         │
                         ▼
             Segment / Extent / Block
                         │
                         ▼
             Tablespace của Oracle
               │            │
          Datafile       Tempfile
               │            │
               └─────┬──────┘
                     ▼
           Filesystem hoặc ASM
                     │
                     ▼
         Đĩa / volume / thiết bị lưu trữ

         Các luồng ghi khác:
         LGWR → online redo logs
         ARCn / RMAN / flashback → FRA hoặc vị trí lưu riêng
```

Một hệ thống có thể thiếu chỗ ở bất kỳ điểm nào:

| Lớp | Câu hỏi cần trả lời | Ví dụ sự cố |
| --- | --- | --- |
| **Segment** | Bảng, index, LOB hoặc partition nào đang chiếm và tăng dung lượng? | Một bảng log tăng nhanh do chính sách giữ dữ liệu chưa phù hợp |
| **Tablespace** | Còn khả năng cấp extent cho segment không? | Tablespace đạt giới hạn; `ORA-01653` khi mở rộng bảng |
| **Datafile** | Kích thước hiện tại, `AUTOEXTEND`, `MAXBYTES` và không gian còn có thể tăng là bao nhiêu? | File đạt `MAXSIZE` dù đĩa dưới vẫn còn trống |
| **TEMP** | Truy vấn sort/hash hoặc thao tác index đang cần bao nhiêu temporary space? | `ORA-01652` khi không cấp thêm temporary segment |
| **UNDO** | Undo extents phục vụ transaction/consistent read còn đủ không? | `ORA-30036` khi không cấp được thêm undo |
| **Filesystem** | Volume chứa datafiles, redo, backup hoặc archive còn bao nhiêu byte/inode? | Datafile muốn mở rộng nhưng thiết bị lưu trữ hết chỗ |
| **ASM disk group** | Dung lượng thực có thể dùng sau khi tính redundancy là bao nhiêu? | `USABLE_FILE_MB` thấp dù `FREE_MB` còn một phần |
| **FRA / archive** | Redo archive, flashback logs và bản backup còn nằm trong giới hạn FRA không? | `ORA-19809` hoặc archiver lỗi; giao dịch có thể bị chặn |
| **VM/container/host** | Đĩa ảo, Docker volume và ổ đĩa thực còn tăng được không? | Container báo lỗi ghi file vì host hoặc đĩa ảo đã hết chỗ |

**Không tồn tại một cột “% disk used” duy nhất mô tả chính xác toàn bộ các lớp trên.** Hệ thống giám sát tốt phải đối chiếu dữ liệu Oracle với thông tin storage bên ngoài database.

### 1.1. Đơn vị và thuật ngữ

- **Block:** đơn vị Oracle dùng để quản lý dữ liệu trên database; kích thước block có thể khác nhau giữa tablespace.
- **Extent:** nhóm các block được cấp phát cho segment. Dung lượng đã cấp cho segment không nhất thiết bằng số byte dữ liệu nghiệp vụ đang dùng.
- **Segment:** vùng lưu trữ thuộc bảng, index, LOB, partition hoặc loại đối tượng khác.
- **Datafile:** tệp vật lý lưu dữ liệu trong một permanent/undo tablespace.
- **Tempfile:** tệp thuộc temporary tablespace; cần theo dõi khác datafile thông thường.
- **Allocated size:** kích thước tệp hoặc extent đã được Oracle cấp phát hiện tại.
- **Potential/configured maximum:** giới hạn có thể mở rộng theo cấu hình; **không đồng nghĩa** đĩa vật lý chắc chắn còn chỗ.
- **Free extents:** phần chưa được cấp cho segment trong datafile; khác với “hàng trống” bên trong một bảng.

Trong phần SQL, tài liệu dùng `POWER(1024, 2)` để chuyển byte sang MiB và `POWER(1024, 3)` để chuyển byte sang GiB. Nhãn `MB/GB` thường gặp trong công cụ có thể là cách hiển thị làm tròn; khi so sánh số liệu giữa Oracle và storage monitoring hãy thống nhất đơn vị.

## 2. Ba số liệu cần nhìn cùng nhau

Hãy xem một tablespace với số liệu minh họa:

| Chỉ số | Ví dụ | Ý nghĩa |
| --- | ---: | --- |
| Dung lượng các datafiles hiện đã cấp phát | 80 GiB | Dung lượng tệp hiện tại |
| Extents đã cấp cho các segment | 72 GiB | Phần đã cấp phát cho đối tượng |
| Free extents trong datafiles hiện tại | 8 GiB | Khoảng trống trong tệp đang tồn tại |
| Tổng giới hạn cấu hình nếu tự mở rộng | 120 GiB | Giới hạn lý thuyết theo `MAXBYTES` |
| Filesystem bên dưới còn trống | 6 GiB | Phần đĩa hiện có để file tăng thêm, cùng chia sẻ với các tệp khác |

Nếu chỉ xét giới hạn cấu hình, có vẻ tablespace còn 48 GiB giữa extents đã dùng 72 GiB và trần 120 GiB. Nhưng **đĩa vật lý chỉ còn 6 GiB**; không nên dự báo 48 GiB có thể được sử dụng thực tế. Với giả định filesystem chỉ chứa tài nguyên liên quan, dung lượng tăng thêm của tệp có thể bị giới hạn trước ở 6 GiB. Đồng thời, vẫn còn 8 GiB free extents trong những datafiles hiện hữu.

Vì vậy, cần ít nhất ba góc nhìn:

1. **Đã sử dụng/được cấp phát ở cấp Oracle là bao nhiêu?**
2. **Có thể tăng thêm về mặt cấu hình Oracle không?**
3. **Storage thực tế có đủ để đáp ứng việc tăng đó không?**

Khi tập hợp số liệu, phân biệt rõ **dung lượng hiện tại**, **trần cấu hình** và **trần khả dụng thực tế**. Một cảnh báo chỉ dựa vào `AUTOEXTEND=YES` sẽ không đầy đủ.

## 3. Xem mức sử dụng tablespace bằng SQL

### 3.1. Tổng quan qua `DBA_TABLESPACE_USAGE_METRICS`

Oracle cung cấp view `DBA_TABLESPACE_USAGE_METRICS` với các cột quan trọng:

- `TABLESPACE_NAME`: tên tablespace.
- `USED_SPACE`: dung lượng đã dùng theo đơn vị block.
- `TABLESPACE_SIZE`: kích thước tablespace mà phép tính của view đang xét, theo đơn vị block; có thể phản ánh giới hạn mở rộng và yếu tố storage tùy cấu hình/phiên bản.
- `USED_PERCENT`: tỷ lệ giữa `USED_SPACE` và `TABLESPACE_SIZE` theo định nghĩa của view.

Kết hợp với `DBA_TABLESPACES.BLOCK_SIZE` để chuyển block thành byte:

```sql
SELECT
    m.tablespace_name,
    t.contents,
    t.bigfile,
    ROUND(m.used_space * t.block_size / POWER(1024, 3), 2) AS used_gib,
    ROUND(m.tablespace_size * t.block_size / POWER(1024, 3), 2)
        AS capacity_gib,
    ROUND(m.used_percent, 2) AS used_percent,
    ROUND((m.tablespace_size - m.used_space) * t.block_size
          / POWER(1024, 3), 2) AS remaining_gib
FROM dba_tablespace_usage_metrics m
JOIN dba_tablespaces t
  ON t.tablespace_name = m.tablespace_name
ORDER BY m.used_percent DESC;
```

Ví dụ kết quả minh họa:

| TABLESPACE_NAME | CONTENTS | USED_GIB | CAPACITY_GIB | USED_PERCENT |
| --- | --- | ---: | ---: | ---: |
| APP_DATA | PERMANENT | 76.0 | 90.0 | 84.44 |
| APP_INDEX | PERMANENT | 18.0 | 30.0 | 60.00 |
| UNDOTBS1 | UNDO | 10.0 | 16.0 | 62.50 |

**Cách đọc đúng:** tỷ lệ này dựa trên định nghĩa `TABLESPACE_SIZE` của view, có thể khác `used/allocated-current-files`. Vì vậy không đặt nhãn “tỷ lệ lấp đầy filesystem” cho `USED_PERCENT`. Nếu bảng số liệu mâu thuẫn với `df`/ASM, phải kiểm tra datafiles, autoextend và storage thật trước khi kết luận.

Đối với CDB/PDB, các view dạng `DBA_...` thường hiển thị theo phạm vi container đang kết nối; tài khoản ở CDB root không tự có một bảng tổng hợp chính xác mọi PDB nếu chưa xét view/container tương ứng. Hệ thống giám sát đa PDB cần lưu cả **container identity** (`CON_NAME`/`CON_ID`) và chạy với quyền/phạm vi được thiết kế rõ ràng.

### 3.2. Kiểm tra từng datafile và quyền tự mở rộng

`DBA_DATA_FILES` phản ánh kích thước hiện tại và cấu hình mở rộng của datafiles. `DBA_FREE_SPACE` cho biết những free extents trong permanent tablespaces; cần tổng hợp theo `FILE_ID` trước khi nối với datafile:

```sql
WITH free_per_file AS (
    SELECT file_id, SUM(bytes) AS free_bytes
    FROM dba_free_space
    GROUP BY file_id
)
SELECT
    df.tablespace_name,
    df.file_name,
    df.autoextensible,
    ROUND(df.bytes / POWER(1024, 3), 2) AS allocated_gib,
    ROUND(NVL(f.free_bytes, 0) / POWER(1024, 3), 2)
        AS free_extent_gib,
    ROUND((df.bytes - NVL(f.free_bytes, 0))
          / POWER(1024, 3), 2) AS nonfree_extent_gib,
    ROUND(
        CASE WHEN df.autoextensible = 'YES'
             THEN df.maxbytes ELSE df.bytes END
        / POWER(1024, 3), 2
    ) AS configured_file_max_gib
FROM dba_data_files df
LEFT JOIN free_per_file f
  ON f.file_id = df.file_id
ORDER BY df.tablespace_name, df.file_name;
```

Cách diễn giải:

- `ALLOCATED_GIB`: kích thước file Oracle hiện đang có.
- `FREE_EXTENT_GIB`: những extent Oracle chưa cấp cho segment bên trong file.
- `NONFREE_EXTENT_GIB`: phần không còn là free extents trong phép tính đơn giản trên; **không phải số byte dữ liệu nghiệp vụ thực tế**. Datafile có metadata và segment có thể giữ những block chưa chứa hàng đang sử dụng.
- `CONFIGURED_FILE_MAX_GIB`: trần cấu hình được suy từ `MAXBYTES` nếu autoextend bật; không bảo đảm filesystem/ASM còn đủ chỗ.

Với locally managed tablespace, view `DBA_FREE_SPACE` có thể không có dòng cho file không còn free extent; `LEFT JOIN` và `NVL` giúp giữ file đó trong báo cáo. Những tablespace/file ở trạng thái đặc biệt như offline hoặc encrypted có thể cần quyền và điều kiện để đọc metadata; thiếu hàng từ dictionary view không nên tự động coi là “0 byte sử dụng”. **Tempfiles được theo dõi bằng các view khác**, không dùng kết quả này thay cho báo cáo TEMP.

### 3.3. Tìm segment nào đang chiếm nhiều dung lượng

Khi một permanent tablespace tăng nhanh, xem dung lượng các segment:

```sql
SELECT
    owner,
    segment_name,
    segment_type,
    ROUND(SUM(bytes) / POWER(1024, 3), 2) AS allocated_gib
FROM dba_segments
WHERE tablespace_name = :tablespace_name
GROUP BY owner, segment_name, segment_type
ORDER BY SUM(bytes) DESC
FETCH FIRST 20 ROWS ONLY;
```

Gán bind parameter `:tablespace_name` trong SQL client, ví dụ `APP_DATA`. Nếu phân tích partitioned table/index, cần cộng các segment/partition có liên quan. LOB thường nằm ở những segment riêng; bảng gốc có thể nhỏ nhưng LOB segment lớn.

**`DBA_SEGMENTS.BYTES` là dung lượng extent đã được cấp phát**, không phải lượng payload hiệu quả hay số row nhân với độ dài trung bình. Xóa hàng có thể làm table segment không tự trả lại toàn bộ extent cho tablespace; phân tích cần xét high water mark, free space trong segment và chính sách reclaim phù hợp.

Muốn biết segment nào **đang tăng**, phải lưu ảnh chụp `DBA_SEGMENTS` theo thời gian hoặc so sánh với nguồn thống kê dài hạn phù hợp. Một lần chạy `ORDER BY bytes DESC` chỉ cho biết segment lớn, không nhất thiết là thủ phạm tăng trưởng gần đây.

## 4. Theo dõi TEMP và UNDO theo đặc tính riêng

### 4.1. Temporary tablespace: phân biệt đã cấp và đang thực sự sử dụng

Temporary tablespace phục vụ sort, hash join, xử lý trung gian và một số tác vụ khác. Temporary extents có thể được giữ lại để tái sử dụng sau khi truy vấn kết thúc, vì vậy **allocated TEMP không đồng nghĩa toàn bộ đang bị session sử dụng**.

Một góc nhìn tổng quan:

```sql
SELECT
    tablespace_name,
    ROUND(tablespace_size / POWER(1024, 3), 2) AS size_gib,
    ROUND(allocated_space / POWER(1024, 3), 2) AS allocated_gib,
    ROUND(free_space / POWER(1024, 3), 2) AS free_gib
FROM dba_temp_free_space
ORDER BY tablespace_name;
```

Trong `DBA_TEMP_FREE_SPACE`, cách tính `FREE_SPACE` có thể bao gồm không gian đã cấp nhưng hiện không được sử dụng cùng không gian chưa cấp; do đó không nên lấy `TABLESPACE_SIZE - ALLOCATED_SPACE` làm “số TEMP session đang dùng” mà không đọc đúng định nghĩa cột.

Kiểm tra session nào **đang dùng temporary segments**:

```sql
SELECT
    username,
    tablespace,
    segtype,
    SUM(blocks) AS used_blocks
FROM v$tempseg_usage
GROUP BY username, tablespace, segtype
ORDER BY used_blocks DESC;
```

`BLOCKS` ở đây là block, không phải byte; cần kích thước block tương ứng nếu muốn quy đổi. Trong tình huống có nhiều phiên dùng một user, cần thêm định danh session/SQL và dữ liệu thời điểm để xác định câu SQL thực sự tiêu thụ TEMP.

Khi TEMP đầy, không nên kết luận ngay “thiếu dung lượng đĩa”: có thể một truy vấn sort/hash không hiệu quả, một batch bất thường hoặc thao tác tạo index đang tiêu thụ TEMP vượt dự tính.

### 4.2. Undo tablespace: active, unexpired và expired

Undo lưu thông tin phục vụ rollback và read consistency. Một vùng undo có thể là:

- `ACTIVE`: cần cho transaction còn hoạt động.
- `UNEXPIRED`: đã hết vai trò active nhưng vẫn đang trong thời gian giữ lại theo undo retention.
- `EXPIRED`: có thể tái sử dụng theo quy tắc Oracle.

Quan sát theo trạng thái:

```sql
SELECT
    tablespace_name,
    status,
    ROUND(SUM(bytes) / POWER(1024, 3), 2) AS allocated_gib
FROM dba_undo_extents
GROUP BY tablespace_name, status
ORDER BY tablespace_name, status;
```

`UNEXPIRED` không nhất thiết có nghĩa “không bao giờ được tái sử dụng”; việc giữ undo còn phụ thuộc retention, guarantee, áp lực không gian và cấu hình. Truy vấn chạy lâu hoặc transaction kéo dài có thể tăng nhu cầu undo. Các view như `V$UNDOSTAT` giúp quan sát mức sinh undo và vấn đề retention qua từng khoảng thời gian.

Khi phát sinh `ORA-30036`, hãy kiểm tra dung lượng undo, chế độ autoextend, transaction dài, tốc độ DML và giới hạn storage trước khi quyết định mở rộng undo.

## 5. Theo dõi dung lượng storage phía dưới Oracle

### 5.1. Filesystem trên Linux

Khi Oracle lưu datafiles, redo logs hoặc archived redo logs trên filesystem, quản trị viên nên đo ngay trên host hoặc VM:

```bash
df -h
df -i
lsblk -f
```

- `df -h`: không gian đã dùng và còn trống của các filesystem đã mount.
- `df -i`: inode đã dùng/còn trống; với một số filesystem, hết inode có thể khiến tạo file thất bại dù còn byte trống.
- `lsblk -f`: xem block devices, filesystem và mountpoints trên Linux.

Một lệnh kiểm tra đúng mountpoint:

```bash
df -h /u02/oradata
```

`/u02/oradata` chỉ là đường dẫn minh họa. Hãy thay bằng thư mục thực sự chứa datafiles hoặc archive/backup. Nếu Oracle dùng nhiều mountpoints, phải quan sát **từng điểm mount**. Giới hạn filesystem của nơi chứa datafiles không nhất thiết giống nơi chứa archived logs.

Đo tại filesystem cần xét cả hạn mức/quota, thin provisioning hoặc dung lượng khả dụng từ storage array. Với storage thin-provisioned, kết quả từ VM có thể khác dung lượng thực còn trên hạ tầng bên dưới.

### 5.2. ASM: `FREE_MB` khác `USABLE_FILE_MB`

Nếu Oracle dùng **Automatic Storage Management (ASM)**, datafiles/redo có thể nằm trong disk groups (ví dụ `+DATA`, `+RECO`). `df -h` trên Linux guest không thay thế việc xem dung lượng ASM.

Trong **ASM instance** và với quyền phù hợp, có thể dùng:

```sql
SELECT
    name,
    total_mb,
    free_mb,
    required_mirror_free_mb,
    usable_file_mb
FROM v$asm_diskgroup_stat
ORDER BY name;
```

Ý nghĩa:

- `TOTAL_MB`: tổng dung lượng disk group theo cách ASM báo cáo.
- `FREE_MB`: lượng free space ở cấp disk group trước khi xét khả năng lưu bản sao theo redundancy.
- `REQUIRED_MIRROR_FREE_MB`: lượng dung lượng ASM dành cho yêu cầu phục hồi sau sự cố theo redundancy.
- `USABLE_FILE_MB`: chỉ số dung lượng hữu ích còn có thể dùng sau khi xét những yêu cầu lưu trữ đó.

Với redundancy có mirroring, **`FREE_MB` không thể đọc như số MB dữ liệu mới có thể thêm theo nghĩa một bản duy nhất**. `USABLE_FILE_MB` có thể thấp hơn nhiều, thậm chí cho thấy áp lực nghiêm trọng. Cũng cần giám sát dung lượng của từng disk group, mức cân bằng và lỗi thiết bị phù hợp.

### 5.3. Docker, VM và máy chủ vật lý

Với Oracle chạy trong container, dung lượng có thể chịu nhiều giới hạn:

```text
Oracle datafile
   → Docker named volume / bind mount
   → filesystem của Docker host hoặc Linux VM/WSL
   → ổ đĩa vật lý / storage backing
```

Lệnh quan sát mức sử dụng Docker tổng quan:

```powershell
docker system df
docker volume ls
docker volume inspect oracle-lab-data
```

Thay `oracle-lab-data` bằng tên volume thật. `docker system df` chủ yếu phản ánh image/container/volume theo cách Docker thống kê, **không phải một báo cáo thay thế `DBA_DATA_FILES` hoặc dữ liệu Oracle**. Trong Docker Desktop/WSL, còn phải kiểm tra dung lượng đĩa ảo và ổ đĩa host chứa đĩa ảo đó.

**Không xóa volume, file Oracle hoặc chạy lệnh dọn toàn bộ Docker chỉ để giải phóng dung lượng.** Những thao tác đó có thể xóa database thực hành hoặc phá vỡ khả năng phục hồi. Muốn dọn storage, cần xác định chính xác đối tượng và cơ chế sở hữu dữ liệu.

### 5.4. Trên Windows

Nếu datafiles/VM/Docker storage nằm trên ổ Windows, có thể xem các volume bằng PowerShell:

```powershell
Get-Volume | Select-Object DriveLetter, FileSystemLabel, Size, SizeRemaining
```

Cần biết đường dẫn thật của tệp/đĩa ảo để ghép đúng volume. Nếu Oracle chạy trong Linux VM/WSL, số liệu ở Windows host và bên trong guest đều có ý nghĩa: guest có thể hết giới hạn đĩa ảo trước khi host hết dung lượng, hoặc ngược lại.

## 6. FRA, archived redo logs và nguy cơ database bị chặn

**Fast Recovery Area (FRA)** là khu vực lưu trữ phục vụ recovery, có thể chứa archived redo logs, flashback logs, backup pieces và các tệp liên quan tùy cấu hình. FRA có **giới hạn kích thước Oracle quản lý** bên cạnh giới hạn vật lý của filesystem hoặc ASM disk group bên dưới.

Nếu FRA đạt hạn mức, Oracle có thể không tạo được tệp recovery mới; lỗi archiving có thể dẫn đến các vấn đề nghiêm trọng cho hoạt động ghi database. Vì thế **FRA cần một cảnh báo độc lập**, không được gộp đơn giản vào tỷ lệ đầy của tablespace dữ liệu.

### 6.1. Kiểm tra giới hạn và mức dùng FRA

Với quyền phù hợp:

```sql
SELECT
    name,
    ROUND(space_limit / POWER(1024, 3), 2) AS limit_gib,
    ROUND(space_used / POWER(1024, 3), 2) AS used_gib,
    ROUND(space_reclaimable / POWER(1024, 3), 2) AS reclaimable_gib,
    number_of_files
FROM v$recovery_file_dest;
```

Nếu FRA chưa được cấu hình, kết quả có thể không có giá trị sử dụng như mong đợi. Không giả định archived redo logs của mọi database đều được lưu trong FRA; có hệ thống dùng archive destination riêng.

Quan sát nhóm file sử dụng FRA:

```sql
SELECT
    file_type,
    percent_space_used,
    percent_space_reclaimable,
    number_of_files
FROM v$flash_recovery_area_usage
ORDER BY percent_space_used DESC;
```

`SPACE_RECLAIMABLE` cho biết lượng mà Oracle có thể giải phóng theo chính sách/cơ chế quản lý, **không đồng nghĩa các byte đã được trả ngay về đĩa**. Việc reclaim phụ thuộc retention, trạng thái backup, archivelog deletion policy, flashback và các điều kiện khác.

Kiểm tra chế độ archive:

```sql
SELECT log_mode FROM v$database;
```

Hệ thống `ARCHIVELOG` cần theo dõi lưu lượng sinh archived redo và chu kỳ backup/deletion đã được duyệt. Trên database có cấu hình Data Guard hoặc backup liên quan, không được tự xóa archived logs vì chúng có thể còn cần cho standby/recovery.

### 6.2. Vì sao FRA có thể đầy rất nhanh?

- Một batch `INSERT/UPDATE/DELETE` tạo redo lớn hơn thông thường.
- Archive log không được backup hoặc thu dọn đúng chính sách.
- Retention của flashback logs/restore points hoặc các yêu cầu phục hồi đang giữ không gian.
- Giới hạn `DB_RECOVERY_FILE_DEST_SIZE` không tương xứng với tốc độ redo và thời gian cần lưu giữ.
- Storage thực tế phía dưới FRA hết dung lượng trước khi Oracle có thể dùng hết giới hạn cấu hình.

**Không dùng `rm`, `del` hoặc xóa tay online/archived redo logs trong thư mục Oracle như một “cách sửa nhanh”.** Hãy đánh giá trạng thái recovery, backup và deletion policy, sau đó dùng công cụ/quy trình quản trị hợp lệ như RMAN với sự cho phép phù hợp. Xóa sai file có thể làm mất khả năng phục hồi hoặc khiến database ngừng hoạt động.

## 7. “Chụp ảnh” dung lượng định kỳ để thấy xu hướng

Một lần nhìn `USED_PERCENT=78%` không nói đủ mức khẩn cấp:

- Tablespace tăng **0,1 GiB/ngày** và còn 20 GiB có thể đủ lâu.
- Tablespace tăng **5 GiB/ngày** và còn 20 GiB có thể đầy trong vài ngày.
- Dung lượng có thể tăng đột biến trong kỳ batch, khi nạp dữ liệu hoặc sau một lần bảo trì.

Vì vậy phải tạo **time series**. Hãy lấy mẫu cùng cách tính tại các mốc ổn định, lưu ít nhất:

| Trường | Mục đích |
| --- | --- |
| Thời điểm đo, múi giờ | Đối chiếu các mẫu và sự kiện vận hành |
| Database/instance và PDB/container | Không trộn số liệu các database hoặc PDB khác nhau |
| Tên tablespace hoặc ASM disk group/FRA/filesystem | Biết chính xác đối tượng lưu trữ |
| Used bytes và allocated bytes | Thấy lượng sử dụng và dung lượng đã cấp |
| Configured maximum và physical available | Biết giới hạn mở rộng logic và thực tế |
| Used percent | Cảnh báo theo tỷ lệ |
| Tình trạng autoextend và storage health | Giải thích các thay đổi đột ngột |

Tần suất mẫu phụ thuộc môi trường. Ví dụ lab ít thay đổi có thể lấy mỗi ngày; môi trường production có tăng trưởng nhanh nên lấy theo giờ hoặc thậm chí thường xuyên hơn cho FRA, TEMP và filesystem quan trọng. **Chỉ lấy một mẫu mỗi ngày có thể bỏ lỡ đỉnh TEMP vài phút hoặc archive bùng nổ trong một giờ.**

### 7.1. Ví dụ lưu lịch sử tablespace vào một bảng quản lý

Ví dụ sau minh họa cách lưu ảnh chụp theo thời gian trong **một schema giám sát được cấp quyền thích hợp**. Đây là mã tạo bảng để học cơ chế, không phải yêu cầu triển khai thêm schema vào production khi chưa có quy trình sở hữu và retention rõ ràng.

```sql
CREATE TABLE ts_usage_history (
    sampled_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    container_name  VARCHAR2(128) NOT NULL,
    tablespace_name VARCHAR2(128) NOT NULL,
    used_bytes      NUMBER NOT NULL,
    capacity_bytes  NUMBER NOT NULL,
    used_percent    NUMBER NOT NULL
);

CREATE INDEX idx_ts_usage_history
    ON ts_usage_history (
        container_name,
        tablespace_name,
        sampled_at
    );
```

Mỗi lần lấy mẫu:

```sql
INSERT INTO ts_usage_history (
    sampled_at,
    container_name,
    tablespace_name,
    used_bytes,
    capacity_bytes,
    used_percent
)
SELECT
    SYSTIMESTAMP,
    SYS_CONTEXT('USERENV', 'CON_NAME'),
    m.tablespace_name,
    m.used_space * t.block_size,
    m.tablespace_size * t.block_size,
    m.used_percent
FROM dba_tablespace_usage_metrics m
JOIN dba_tablespaces t
  ON t.tablespace_name = m.tablespace_name;

COMMIT;
```

Đây là **snapshot theo container của session đang chạy**. Khi giám sát nhiều database/PDB, hệ thống thật cần thêm định danh database như `DB_UNIQUE_NAME` hoặc một mã nguồn dữ liệu riêng, lưu mỗi PDB đúng phạm vi và tránh trùng dữ liệu. Không tạo job lấy mẫu liên tục không giới hạn hoặc tạo bảng lịch sử mà không có quy trình retention.

Việc lên lịch có thể thực hiện qua một hệ thống monitoring bên ngoài, Oracle Scheduler hoặc cơ chế vận hành sẵn có. Trong production, ưu tiên dùng hệ thống quan sát đã được tổ chức vận hành thay vì bổ sung một job vào database chỉ để thử nghiệm.

### 7.2. Đọc sự thay đổi đầu và cuối một khoảng

Nếu đã thu thập nhiều mẫu `TS_USAGE_HISTORY`:

```sql
WITH endpoints AS (
    SELECT
        container_name,
        tablespace_name,
        MIN(sampled_at) AS first_at,
        MAX(sampled_at) AS last_at,
        MAX(used_bytes) KEEP (
            DENSE_RANK FIRST ORDER BY sampled_at
        ) AS first_used,
        MAX(used_bytes) KEEP (
            DENSE_RANK LAST ORDER BY sampled_at
        ) AS last_used,
        MAX(capacity_bytes) KEEP (
            DENSE_RANK LAST ORDER BY sampled_at
        ) AS last_capacity
    FROM ts_usage_history
    WHERE sampled_at >= SYSTIMESTAMP - INTERVAL '14' DAY
    GROUP BY container_name, tablespace_name
)
SELECT
    container_name,
    tablespace_name,
    ROUND((last_used - first_used) / POWER(1024, 3), 2)
        AS net_growth_gib,
    ROUND(
        (last_used - first_used)
        / POWER(1024, 3)
        / NULLIF(
            CAST(last_at AS DATE) - CAST(first_at AS DATE), 0
          ), 2
    ) AS growth_gib_per_day,
    ROUND((last_capacity - last_used) / POWER(1024, 3), 2)
        AS remaining_gib
FROM endpoints
ORDER BY growth_gib_per_day DESC NULLS LAST;
```

Đây là **tăng trưởng ròng giữa hai mẫu đầu-cuối**. Nó có thể âm khi sau cleanup/reclaim dung lượng giảm; không có nghĩa công việc ghi trong khoảng đó không tốn storage. Truy vấn dùng giá trị capacity cuối kỳ theo view đã chọn, **chưa đưa vào giới hạn vật lý filesystem/ASM hoặc khả năng tăng thêm của FRA**.

Không nên tính tốc độ/ngày từ hai mẫu cách nhau quá ngắn rồi kết luận chính thức. Dùng nhiều điểm đo, đánh giá ngày thường so với cuối tuần, lịch batch và các ngày chạy job dữ liệu lớn để có xu hướng đáng tin cậy.

## 8. Tính tăng trưởng và “số ngày đến lúc đầy”

Một phép dự báo đơn giản:

```text
growth_per_day = (used_at_end - used_at_start) / number_of_days

headroom = effective_capacity - current_used

days_to_full = headroom / growth_per_day
               (chỉ khi growth_per_day > 0)
```

Trong đó:

- `effective_capacity` phải xét **trần Oracle** và **khả năng tăng thực tế của storage**. Nếu chưa có số liệu storage, chỉ được ghi “theo giới hạn logic đã quan sát”, không coi đó là dự báo vật lý chắc chắn.
- `current_used` phải có cùng định nghĩa với dữ liệu lịch sử.
- Khi `growth_per_day <= 0`, **không gán days to full bằng vô cực một cách chắc chắn**; chỉ kết luận không đủ bằng chứng về xu hướng tăng liên tục trong khoảng đo.
- Với workload tăng theo sự kiện, batch/seasonality hoặc dữ liệu nạp theo đợt, xu hướng tuyến tính chỉ là một kịch bản tham khảo.

### 8.1. Ví dụ tính bằng tay

Giả sử tablespace `APP_DATA` có:

| Thông số | Giá trị |
| --- | ---: |
| Used đầu tuần | 62 GiB |
| Used cuối tuần | 76 GiB |
| Thời gian giữa hai mẫu | 7 ngày |
| Capacity có thể sử dụng theo phép đo đang xét | 100 GiB |

Ta có:

```text
Tăng ròng       = 76 - 62 = 14 GiB
Trung bình/ngày = 14 / 7 = 2 GiB/ngày
Còn theo capacity đang xét = 100 - 76 = 24 GiB
Days to full ≈ 24 / 2 = 12 ngày
```

Một bảng điều khiển chỉ báo “76%” có thể trông an toàn nếu ngưỡng cảnh báo là 80%; nhưng với **12 ngày đến lúc đầy**, đội vận hành đã cần biết trước để kịp chuẩn bị lưu trữ hoặc điều chỉnh dữ liệu.

Nếu trần autoextend theo cấu hình là 150 GiB nhưng filesystem chỉ còn 6 GiB ngoài những datafiles hiện tại, không được lấy `150 - 76 = 74 GiB` làm headroom vật lý. Cần cộng phần free extents đang có với **phần mở rộng thực tế khả dụng**, đồng thời tính tới tài nguyên mà những file khác trên cùng filesystem sẽ tiêu thụ.

### 8.2. Dự báo nên có khoảng bất định

Với một tháng dữ liệu, nên quan sát thêm:

- Tốc độ tăng trung bình và tốc độ tăng trong **ngày cao điểm**.
- Xu hướng 7 ngày so với 30 ngày, thời điểm backup/ETL/batch.
- Các thay đổi cấu hình như thêm datafile hoặc tăng `MAXSIZE` làm capacity nhảy vọt.
- Tăng trưởng theo từng nhóm segment, không chỉ tổng tablespace.
- Dữ liệu storage thật: FRA, filesystem/ASM có thể bị hệ thống khác dùng chung.

Ví dụ tốc độ trung bình 1 GiB/ngày nhưng peak đạt 8 GiB/ngày. Nếu còn 12 GiB headroom, công bố “còn 12 ngày chắc chắn” là không an toàn. Có thể hiển thị **khoảng dự báo 1,5–12 ngày** theo hai kịch bản minh họa, ghi rõ giả định và cơ sở dữ liệu quan sát.

## 9. Thiết kế cảnh báo trước khi database thực sự đầy

Một cấu hình cảnh báo chỉ dựa vào “đầy trên 90%” thường báo quá muộn với hệ thống tăng nhanh. Nên kết hợp **mức đầy**, **khả năng mở rộng thực tế** và **tốc độ tăng**.

Ví dụ chính sách mẫu, cần điều chỉnh theo SLA và tốc độ tăng trưởng của từng môi trường:

| Mức | Điều kiện gợi ý | Hành động |
| --- | --- | --- |
| **Info** | Tăng nhanh hơn baseline dù chưa gần đầy | Ghi trend, đối chiếu batch/segment mới |
| **Warning** | Tablespace ≥ 80% hoặc dự báo ≤ 14 ngày | Xác minh growth, autoextend và nguồn storage, mở ticket/capacity planning |
| **Critical** | Tablespace ≥ 90%, hoặc dự báo ≤ 7 ngày, hoặc storage/FRA dưới mức dự phòng an toàn | Báo on-call, đánh giá ngay khả năng cấp phát và ảnh hưởng dịch vụ |
| **Emergency** | Ghi database/archiving đang lỗi hoặc storage thực tế không còn cấp phát được | Kích hoạt runbook sự cố, bảo vệ dữ liệu và năng lực recovery |

Ngưỡng 80/90% và 14/7 ngày là **ví dụ**, không phải chuẩn Oracle bắt buộc. Một tablespace 10 TiB có 5% còn trống khác nhiều tablespace 10 GiB chỉ còn 5%. Để tránh cảnh báo không phù hợp, có thể thêm **số GiB tuyệt đối còn lại** và điều kiện theo workload.

### 9.1. Ví dụ SQL phát hiện tablespace vượt ngưỡng

```sql
SELECT
    tablespace_name,
    ROUND(used_percent, 2) AS used_percent,
    CASE
        WHEN used_percent >= 90 THEN 'CRITICAL'
        WHEN used_percent >= 80 THEN 'WARNING'
        ELSE 'OK'
    END AS severity
FROM dba_tablespace_usage_metrics
WHERE used_percent >= 80
ORDER BY used_percent DESC;
```

Kết quả là **dữ liệu cảnh báo đầu vào**, chưa phải hệ thống gửi cảnh báo. Một triển khai thực tế có thể dùng công cụ monitoring của tổ chức, Oracle Enterprise Manager hoặc cơ chế server-generated alerts phù hợp phiên bản/quyền. Những hệ thống đó cần quản lý người nhận, kênh gửi, ngưỡng và quyền vận hành riêng.

### 9.2. Quy tắc cảnh báo theo lớp

| Đối tượng | Metric nên theo dõi | Vì sao khác nhau? |
| --- | --- | --- |
| Permanent tablespace | `USED_PERCENT`, free extents, datafile max/autoextend | Phát hiện không cấp được extent và giới hạn datafile |
| Temporary tablespace | Free TEMP và TEMP đang được session dùng | Peak theo truy vấn có thể rất ngắn |
| Undo | Trạng thái undo extents, tốc độ sinh undo, mức autoextend | Transaction dài/undo retention có thể gây áp lực |
| Filesystem | Free bytes, free %, inode, tốc độ tăng | Oracle autoextend không vượt qua đĩa thật |
| ASM | `USABLE_FILE_MB`, disk group health, free và redundancy | `FREE_MB` chưa phản ánh đầy đủ usable capacity |
| FRA | Used/limit, reclaimable, archived redo rate, archiver status | FRA có trần riêng, có thể chặn ghi/archiving |
| Datafile | Current size, maxsize, autoextend và tốc độ tăng | Từng file có thể đạt max trước các file khác |
| Segment | Snapshot dung lượng theo owner/object/partition | Giúp tìm đúng nguồn tăng trưởng |

Ví dụ dù tablespace sử dụng mới 65%, nếu **filesystem còn dưới 10 GiB** và tốc độ archive/backup tăng rất nhanh, cảnh báo storage ở cấp host có thể cấp bách hơn tỷ lệ tablespace.

### 9.3. Hạn chế cảnh báo nhiễu

Một hệ thống cảnh báo hữu ích thường cần:

1. **Đặt nhãn nguồn rõ ràng:** database, PDB, tablespace/mountpoint/disk group, môi trường, thời điểm và mức độ.
2. **Dùng nhiều mẫu liên tiếp** cho cảnh báo trend hoặc tỷ lệ đang dao động; sự cố lỗi ghi thật phải báo ngay theo quy định.
3. **Hysteresis:** ví dụ bật warning ở 80%, chỉ tự xác nhận hồi phục sau khi mức sử dụng xuống dưới 75%, nếu chính sách cho phép.
4. **Deduplicate:** không gửi một cảnh báo giống hệt nhau từng phút khi chưa có thay đổi quan trọng.
5. **Gắn runbook và owner:** người nhận phải biết cần kiểm tra Oracle view, filesystem/ASM và FRA nào.
6. **Có dữ liệu phục hồi:** khi dung lượng giảm cần biết do giải phóng thật, mở rộng capacity hay thay đổi cách thu thập.

Không đồng nhất “tình trạng không có dữ liệu” với “0% sử dụng”. Nếu một agent giám sát dừng hoạt động hoặc tài khoản mất quyền đọc view, cần cảnh báo **monitoring unavailable/stale** để tránh trạng thái an toàn giả.

## 10. Khi có lỗi thiếu dung lượng: chẩn đoán theo thứ tự

### 10.1. Những thông báo thường gặp

| Thông báo | Hướng chẩn đoán đầu tiên |
| --- | --- |
| `ORA-01653: unable to extend table ... in tablespace ...` | Permanent tablespace/datafile không cấp thêm extent cho bảng |
| `ORA-01654: unable to extend index ...` | Index segment hoặc tablespace của index không mở rộng được |
| `ORA-01652: unable to extend temp segment ...` | TEMP hoặc thao tác cần temporary segment gặp giới hạn; kiểm tra workload và storage |
| `ORA-30036: unable to extend segment ... in undo tablespace` | Undo thiếu khả năng cấp extent; xem transaction/retention/autoextend |
| `ORA-19809: limit exceeded for recovery files` | FRA đạt giới hạn cấu hình; xem loại file và chính sách reclaim |
| `ORA-00257: archiver error` | Archiving có vấn đề, có thể do archive destination/FRA đầy hoặc lỗi lưu trữ |
| I/O error hoặc lỗi mở rộng file từ OS | Filesystem/ASM/quota/thiết bị có thể không ghi được |

Đây là **dấu hiệu điều tra**, không phải chẩn đoán chắc chắn. Cần xem đầy đủ error stack, alert log, thời điểm xảy ra và trạng thái của từng lớp lưu trữ.

### 10.2. Runbook quan sát và khoanh vùng

**Bước 1 — Xác định phạm vi ảnh hưởng.** Lỗi xảy ra ở bảng/index, TEMP, UNDO, FRA hay filesystem? Ứng dụng nào bị ảnh hưởng? Có transaction đang chờ hay batch bất thường không? Ghi lại thời gian, database/PDB, bảng/segment và thông báo chính xác.

**Bước 2 — Xác định vị trí vật lý.** Với segment lỗi, tìm tablespace rồi datafiles. Với redo/archive, tìm archive destination/FRA. Với VM/container, tìm mountpoint/volume thực. Không chỉ chạy một lệnh `df -h` ở mountpoint bất kỳ.

**Bước 3 — Đọc current size, free extents và autoextend.** Đối chiếu `DBA_TABLESPACE_USAGE_METRICS`, `DBA_DATA_FILES`, `DBA_FREE_SPACE` hoặc các view TEMP/UNDO tương ứng. Nếu datafile còn có thể tự mở rộng về mặt Oracle, tiếp tục kiểm tra storage bên dưới.

**Bước 4 — Kiểm tra giới hạn storage.** Đọc `df` hoặc ASM disk group, tình trạng FRA, quota/thin provisioning và thông báo lỗi từ storage. Nếu backend hết chỗ, việc tăng `MAXSIZE` trong Oracle đơn thuần không giải quyết được.

**Bước 5 — Tìm nguồn tăng trưởng.** So sánh snapshot `DBA_SEGMENTS`, tốc độ archived redo, batch import, partition mới, transaction dài hoặc truy vấn dùng TEMP nhiều. Xem đây là tăng trưởng bình thường hay bất thường.

**Bước 6 — Chọn hướng xử lý có kiểm soát.** Tùy nguyên nhân và chính sách có thể cần bổ sung storage, điều chỉnh giới hạn datafile, thêm datafile cho loại tablespace hỗ trợ, sửa truy vấn, phân vùng/retention dữ liệu hoặc dọn tệp theo quy trình backup/recovery hợp lệ. Những thao tác này cần bảo đảm có khả năng phục hồi và được thực hiện bởi người có quyền.

**Bước 7 — Theo dõi sau xử lý.** Xác nhận số liệu cả phía Oracle và storage thay đổi đúng; workload phục hồi và cảnh báo được đóng theo bằng chứng mới. Cập nhật dự báo growth để sự cố không lặp lại.

### 10.3. Những việc không nên làm khi đang có nguy cơ đầy

- **Không xóa trực tiếp datafiles, control files, online redo logs hoặc archived redo logs** bằng lệnh hệ điều hành như một giải pháp chung.
- **Không tăng `AUTOEXTEND MAXSIZE` mà không kiểm tra filesystem/ASM thật.** Đó chỉ là thay đổi trần cấu hình, không tạo dung lượng.
- **Không tăng unlimited mọi datafile.** Một file tự mở rộng không kiểm soát có thể chiếm toàn bộ đĩa dùng chung và ảnh hưởng dịch vụ khác.
- **Không coi `DELETE FROM table` luôn trả lại file system space.** Extents và file sizes có vòng đời riêng; reclaim/shrink cần đánh giá cụ thể.
- **Không xóa backup/archive vì “cũ”** nếu chưa đối chiếu retention, standby, recovery window và công cụ quản lý backup.
- **Không cho rằng thêm một datafile luôn hợp lệ.** Bigfile tablespace và một số cấu hình quản lý file có quy tắc khác smallfile tablespace; không chạy lệnh mẫu thiếu ngữ cảnh.
- **Không nhầm hết TEMP do câu truy vấn bất thường với hết permanent tablespace.** Tăng datafile bảng có thể không giúp truy vấn sort đang thiếu TEMP.

## 11. Các tình huống mẫu

### Tình huống A — Autoextend bật nhưng INSERT vẫn lỗi

`APP_DATA` có datafile 40 GiB, `AUTOEXTENSIBLE=YES`, `MAXBYTES=80 GiB`. `DBA_FREE_SPACE` báo gần 0 GiB, filesystem chỉ còn 500 MiB. Một lệnh `INSERT` cần extent lớn không thể cấp được.

**Cách suy luận:** Autoextend chỉ mô tả khả năng yêu cầu file lớn hơn đến mức trần; storage không còn đủ. Cần xác minh lỗi thực tế và giải quyết capacity ở mountpoint/ASM, hoặc áp dụng giải pháp dữ liệu có kiểm soát. Bật autoextend thêm lần nữa không giúp ích.

### Tình huống B — Tablespace 70% nhưng 3 ngày nữa có thể đầy

Tablespace đã dùng 70 GiB trên trần khả dụng 100 GiB, tăng ròng 10 GiB/ngày do đợt import. Phần còn 30 GiB tương đương khoảng 3 ngày nếu tốc độ kéo dài.

**Cách suy luận:** Cảnh báo theo tỷ lệ 80% chưa được kích hoạt, nhưng cảnh báo **days to full ≤ 7** phải phát hiện sớm. Cần xác minh import còn kéo dài hay chỉ là spike một lần trước khi quyết định cấp storage.

### Tình huống C — Data tablespace còn chỗ nhưng ứng dụng không ghi được

`APP_DATA` còn 30 GiB free, trong khi `V$RECOVERY_FILE_DEST` cho thấy FRA gần giới hạn và alert log có lỗi archiver.

**Cách suy luận:** Đây không nhất thiết là lỗi APP_DATA. Oracle cần ghi redo và archive theo cấu hình; nếu không archive được, giao dịch có thể bị ảnh hưởng. Kiểm tra FRA/archived redo/backup policy thay vì mở rộng tablespace ứng dụng.

### Tình huống D — TEMP tăng đột biến lúc 02:00

Ban ngày TEMP gần như trống. Job báo cáo lúc 02:00 chạy hash join/sort trên tập dữ liệu lớn, TEMP đầy rồi sau khi job dừng lại trở về trạng thái có thể tái sử dụng.

**Cách suy luận:** Sampling một lần/ngày lúc 09:00 sẽ bỏ lỡ đỉnh. Cần quan sát `V$TEMPSEG_USAGE` trong thời gian job chạy và mẫu theo phút/giờ phù hợp; sau đó xem plan, thống kê, kiểu truy vấn và nhu cầu capacity.

### Tình huống E — ASM còn `FREE_MB` nhưng không đủ usable capacity

Disk group có mirroring; `FREE_MB` dương nhưng `USABLE_FILE_MB` thấp. Một báo cáo chỉ vẽ `FREE_MB/TOTAL_MB` cho rằng disk group an toàn.

**Cách suy luận:** Cần đọc `USABLE_FILE_MB` và yêu cầu redundancy, không áp công thức filesystem đơn giản lên ASM. Khi tăng dung lượng, còn phải kiểm tra trạng thái disk group và khả năng cân bằng dữ liệu.

### Tình huống F — Bảng lớn nhưng không còn tăng

Một bảng lưu lịch sử chiếm 80 GiB, song 30 ngày gần đây gần như không đổi. Một bảng log nhỏ hơn chỉ 8 GiB nhưng tăng 3 GiB/ngày.

**Cách suy luận:** Danh sách “top 10 largest segments” giúp biết nơi chiếm dung lượng hiện tại, còn **snapshot tăng trưởng theo đối tượng** mới chỉ ra nguồn phát sinh nguy cơ sắp đầy.

## 12. Bài thực hành: lập báo cáo capacity và dự báo cảnh báo

Thực hành này có thể làm trên Oracle Database lab hoặc đọc và tính bằng tay nếu chưa có quyền xem dictionary views. Không xóa dữ liệu và không thực hiện thay đổi cấu hình.

### Phần A — Ghi nhận trạng thái hiện tại

1. Chạy `DBA_TABLESPACE_USAGE_METRICS` để lấy top các tablespace có `USED_PERCENT` cao.
2. Chọn một permanent tablespace; kiểm tra `DBA_DATA_FILES` và free extents để phân biệt **file size hiện tại**, **free extents** và **configured max**.
3. Xác định backend là filesystem hay ASM. Tìm mountpoint hoặc disk group phù hợp.
4. Nếu được phép, đọc trạng thái FRA để biết archive/backup có đang tạo rủi ro riêng không.
5. Viết kết luận có điều kiện: tablespace nào gần giới hạn *logic*, storage nào gần giới hạn *vật lý* và nơi nào cần thêm số liệu.

Mẫu báo cáo:

| Thời điểm | Đối tượng | Used | Capacity/limit | Headroom | Tăng/ngày | Days to full | Trạng thái |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 09:00 | APP_DATA | 76 GiB | 100 GiB | 24 GiB | 2 GiB | ≈12 ngày | Warning do dự báo |
| 09:00 | APP_INDEX | 18 GiB | 50 GiB | 32 GiB | 0,2 GiB | ≈160 ngày | Theo dõi |
| 09:00 | FRA | 45 GiB | 50 GiB | 5 GiB | biến động | cần tính riêng | Critical theo tỷ lệ |

Các số liệu trong bảng **chỉ để minh họa**; không đại diện cho một instance thực tế. Đối với FRA phải tính thêm khả năng reclaim/retention và tốc độ archive để có dự báo phù hợp.

### Phần B — Tính tốc độ tăng

Giả sử bạn có 5 mẫu dùng để học:

| Ngày | APP_DATA used |
| --- | ---: |
| Ngày 1 | 50 GiB |
| Ngày 2 | 52 GiB |
| Ngày 3 | 56 GiB |
| Ngày 4 | 57 GiB |
| Ngày 5 | 62 GiB |

Tăng ròng trong 4 ngày là `62 - 50 = 12 GiB`, tốc độ trung bình `12 / 4 = 3 GiB/ngày`. Nếu capacity khả dụng là 80 GiB thì headroom theo phép đo là 18 GiB, dự báo tuyến tính khoảng `18 / 3 = 6 ngày`. Hãy giải thích vì sao bảng này có tốc độ tăng **không đều** và vì sao cần theo dõi các ngày tăng 4–5 GiB/ngày khi thiết kế cảnh báo.

### Phần C — Viết quy tắc cảnh báo

Từ số liệu trên, xây quy tắc theo hai điều kiện:

- Warning nếu tỷ lệ sử dụng từ 80% **hoặc** thời gian dự báo đến giới hạn ≤14 ngày.
- Critical nếu tỷ lệ sử dụng từ 90% **hoặc** thời gian dự báo ≤7 ngày.

Đối với APP_DATA 62/80 GiB, tỷ lệ là 77,5%; cảnh báo dự báo 6 ngày phải nâng mức lên **Critical theo chính sách ví dụ** dù mức sử dụng hiện tại chưa tới 80%. Ghi rõ rằng phép tính dùng giả định capacity vật lý thực sự khả dụng và tốc độ tăng giữ nguyên.

### Phần D — Viết runbook ngắn

Lập một đoạn hướng dẫn dành cho người trực hệ thống: khi APP_DATA báo Critical, họ kiểm tra lần lượt dictionary view nào, đường lưu trữ nào, segment tăng nào, nguồn dữ liệu tăng do batch hay truy vấn và khi nào cần chuyển tới người quản trị storage/backup.

Mục tiêu là khiến cảnh báo **có thể hành động được**, không chỉ hiển thị một con số màu đỏ.

## 13. Ghi nhớ quy trình giám sát dung lượng Oracle

```text
Quan sát đúng nhiều lớp
        │
        ├── Tablespace / Datafile / Segment
        ├── TEMP / UNDO
        ├── Filesystem hoặc ASM
        └── FRA / Archived redo / Backup
        │
        ▼
Lưu lịch sử có timestamp và đúng database/PDB
        │
        ▼
Đo tăng trưởng theo workload và khoảng thời gian
        │
        ▼
Ước tính headroom thực tế và thời gian đến giới hạn
        │
        ▼
Cảnh báo theo % + GiB còn lại + days to full
        │
        ▼
Điều tra nguyên nhân, xử lý có kiểm soát, đo lại
```

Để tránh sự cố đầy đĩa, đừng chờ đến khi Oracle báo không cấp phát được extent. Một mô hình giám sát tốt cần nhìn **dung lượng hiện tại, tốc độ tăng trưởng và giới hạn lưu trữ thực tế**, đồng thời theo dõi riêng các vùng có nguy cơ cao như TEMP và FRA. Khi biết các lớp liên quan và có dữ liệu lịch sử, bạn có thể lên kế hoạch capacity chủ động và khoanh vùng sự cố nhanh hơn mà không gây rủi ro cho dữ liệu.
