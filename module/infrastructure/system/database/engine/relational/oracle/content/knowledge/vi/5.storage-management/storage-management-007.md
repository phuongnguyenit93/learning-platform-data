# Phân bổ extent, high water mark và ảnh hưởng đến thao tác quét

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Lưu trữ  
> **Mục tiêu:** Hiểu cách Oracle cấp phát không gian từ data block đến extent và segment, vì sao **High Water Mark (HWM)** ảnh hưởng đến số block phải xét khi quét bảng, và phân biệt tác động của `INSERT`, `DELETE`, `TRUNCATE`, `SHRINK` và `MOVE` đối với không gian lưu trữ.

## 1. Đặt vấn đề: bảng còn ít dòng nhưng vẫn quét chậm

Giả sử một bảng Oracle từng chứa 2 triệu bản ghi. Sau một đợt dọn dữ liệu, bảng chỉ còn 2.000 bản ghi. Người học có thể kỳ vọng mọi truy vấn đều nhanh hơn khoảng 1.000 lần.

Thực tế, nếu ứng dụng thực hiện **full table scan**, Oracle có thể vẫn phải đi qua một vùng block rất lớn của segment đã từng được sử dụng. Lý do là thao tác `DELETE` xóa dòng **không đồng nghĩa** segment lập tức co lại hoặc **High Water Mark (HWM)** tự hạ xuống.

Cần phân biệt ba câu hỏi:

1. **Có bao nhiêu dòng còn tồn tại?** Liên quan đến dữ liệu logic.
2. **Có bao nhiêu block/extent đã được cấp phát?** Liên quan đến không gian vật lý của segment.
3. **Vùng block nào thuộc phạm vi scan theo HWM?** Liên quan đến cách Oracle truy cập dữ liệu khi full scan.

Ba con số này không nhất thiết tăng giảm cùng nhau. Bài học tập trung vào mối quan hệ giữa chúng và cách kiểm chứng bằng môi trường Oracle.

## 2. Cấu trúc lưu trữ: tablespace → segment → extent → block

Oracle quản lý không gian theo các cấp độ chính:

| Cấp độ | Khái niệm | Vai trò |
|---|---|---|
| **Tablespace** | Không gian lưu trữ logic, được hỗ trợ bởi một hoặc nhiều datafile | Tổ chức các segment và phân bổ dung lượng cho chúng |
| **Segment** | Tập hợp các extent thuộc một đối tượng lưu trữ | Lưu dữ liệu của bảng, index, undo, một partition... |
| **Extent** | Một tập hợp block Oracle liên tiếp được cấp phát trong **một datafile** | Đơn vị cấp phát/giải phóng không gian cho segment |
| **Oracle data block** | Đơn vị lưu trữ và I/O logic cơ sở của Oracle Database | Chứa hàng dữ liệu, index entries và metadata block |
| **Row** | Một bản ghi logic; có thể trải trên nhiều row piece/block tùy trường hợp | Dữ liệu mà SQL thao tác |

Sơ đồ minh họa:

```text
TABLESPACE USERS
│
├─ DATAFILE users01.dbf
│    ├─ Extent 0 của segment LAB_HWM
│    │    ├─ Block 0
│    │    ├─ Block 1
│    │    └─ ...
│    └─ Extent 2 của segment LAB_HWM
│         └─ ...
│
└─ DATAFILE users02.dbf
     └─ Extent 1 của segment LAB_HWM
          └─ ...

Segment LAB_HWM
  = Extent 0 + Extent 1 + Extent 2 + ...
```

Một segment có thể gồm nhiều extent, và các extent của segment có thể nằm trong các datafile khác nhau của cùng tablespace. **Mỗi extent** là vùng block liên tiếp trong **một** datafile; **cả segment** không cần liên tiếp vật lý trên đĩa.

### 2.1. Data block khác block của hệ điều hành

Ví dụ, một Oracle database có `DB_BLOCK_SIZE = 8192` byte, tương ứng block chuẩn **8 KiB**. Nhưng kích thước này phụ thuộc cấu hình, và một database có thể có các tablespace với kích thước block không mặc định khi được hỗ trợ.

Kiểm tra giá trị của database:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'db_block_size';
```

View `V$PARAMETER` đòi hỏi quyền phù hợp; chỉ xem khi tài khoản được cấp quyền. Không đồng nhất Oracle data block với sector vật lý, page của filesystem hoặc packet mạng.

### 2.2. Extent được cấp phát khi nào?

Khi bảng/index cần thêm không gian mà các block sẵn có không đủ đáp ứng, Oracle có thể cấp phát **extent mới** từ tablespace cho segment. Mỗi extent góp thêm block vào không gian đã cấp phát của segment.

Trong tablespace **locally managed** phổ biến, hai kiểu chiến lược cấp phát extent là:

- **AUTOALLOCATE:** Oracle quyết định kích thước các extent theo cơ chế quản lý không gian.
- **UNIFORM:** mỗi extent có kích thước thống nhất do cấu hình tablespace quy định.

Các extent không bắt buộc có kích thước bằng nhau khi dùng AUTOALLOCATE. Ví dụ minh họa với một tablespace UNIFORM có extent 1 MiB, Oracle block 8 KiB:

```text
1 extent = 1 MiB = 1.048.576 bytes
1 block  = 8 KiB =     8.192 bytes

Số block trong extent = 1.048.576 / 8.192 = 128
```

Đây là phép tính ví dụ. Một số block trong segment cũng phục vụ metadata/space management, không thể kết luận mọi block cấp phát đều chứa đúng 8 KiB dữ liệu người dùng.

### 2.3. Segment creation có thể được hoãn

Ở nhiều phiên bản Oracle hiện đại, một bảng vừa `CREATE TABLE` có thể **chưa có segment vật lý** nếu sử dụng cơ chế **deferred segment creation**. Segment/extent đầu tiên được tạo khi có dữ liệu hoặc hoạt động cần không gian.

Ví dụ:

```sql
CREATE TABLE lab_empty (
    id NUMBER
);
```

Không thấy dòng trong `USER_SEGMENTS` ngay sau `CREATE TABLE` chưa chắc là lỗi. Khi muốn chủ động tạo segment trong bài lab, có thể chọn:

```sql
CREATE TABLE lab_with_segment (
    id NUMBER
)
SEGMENT CREATION IMMEDIATE;
```

Cú pháp và quyền cần phù hợp phiên bản, tablespace và chính sách của môi trường.

## 3. Cấp phát extent và quản lý free space trong segment

### 3.1. Các vùng không gian không giống nhau

Một segment có thể có:

1. **Block đã cấp phát và đang chứa dữ liệu.**
2. **Block đã cấp phát, nằm dưới HWM, nhưng có chỗ trống để ghi thêm dòng.**
3. **Block đã cấp phát, nằm trên HWM và chưa được đưa vào vùng dữ liệu sử dụng.**
4. **Extent chưa cấp cho segment nhưng còn trống trong tablespace.**

Các vùng này dẫn đến hành vi khác nhau. Oracle có thể dùng lại chỗ trống trong block ở vùng thứ hai khi thực hiện **conventional insert**; nếu cần thêm không gian sử dụng, segment có thể mở rộng tới các block trên HWM hoặc xin extent mới.

**Không được hiểu:** “Còn nhiều byte trống trong tablespace” đồng nghĩa “bảng có thể thu gọn ngay” hoặc “full scan sẽ chỉ đọc ít block”. Free space của tablespace, free space trong segment và vị trí HWM là ba khái niệm riêng.

### 3.2. ASSM và MSSM

Có hai cơ chế quản lý không gian tự do trong segment mà người học thường gặp:

- **ASSM (Automatic Segment Space Management):** Oracle dùng bitmap để theo dõi mức đầy tương đối của block và chọn block còn chỗ trống. Đây là lựa chọn phổ biến cho tablespace mới.
- **MSSM (Manual Segment Space Management):** dùng cơ chế quản lý free list và các tham số liên quan; có thể gặp ở hệ thống cũ.

ASSM liên quan **quản lý free space bên trong segment**, còn AUTOALLOCATE/UNIFORM liên quan **kích thước extent cấp phát**. Hai lựa chọn này không đồng nghĩa:

```text
TABLESPACE
  ├─ Extent allocation: AUTOALLOCATE / UNIFORM
  └─ Segment space management: AUTO / MANUAL
                               (ASSM / MSSM)
```

Tùy phiên bản/loại segment, ASSM có thể sử dụng cơ chế low HWM và high HWM để phân biệt các block đã được format hoàn chỉnh với vùng mới cấp phát; vì vậy cách Oracle triển khai scan/format block thực tế tinh vi hơn sơ đồ một vạch HWM. Ở mức nền tảng, HWM vẫn là mốc quan trọng ngăn vùng segment đã đi vào sử dụng với vùng cấp phát chưa sử dụng.

### 3.3. Kiểm tra extent và segment của bảng

Ví dụ bảng `LAB_HWM` đã được tạo và có segment:

```sql
SELECT segment_name, segment_type, tablespace_name,
       extents, blocks, bytes
FROM user_segments
WHERE segment_name = 'LAB_HWM'
  AND segment_type = 'TABLE';
```

Ý nghĩa:

- `EXTENTS`: số extent của segment.
- `BLOCKS`: **tổng số block đã cấp phát** cho segment.
- `BYTES`: tổng dung lượng cấp phát; không phải dung lượng dữ liệu thực của các hàng.
- `TABLESPACE_NAME`: tablespace chứa segment.

Xem từng extent:

```sql
SELECT extent_id, file_id, block_id, blocks, bytes
FROM user_extents
WHERE segment_name = 'LAB_HWM'
  AND segment_type = 'TABLE'
ORDER BY extent_id;
```

Ví dụ minh họa:

| EXTENT_ID | FILE_ID | BLOCK_ID | BLOCKS |
|---:|---:|---:|---:|
| 0 | 7 | 128 | 8 |
| 1 | 7 | 136 | 8 |
| 2 | 7 | 256 | 128 |

Ba extent có thể có kích thước khác nhau theo chính sách cấp phát; bảng chỉ mô phỏng và không đại diện mọi cài đặt.

> **Phạm vi:** Mỗi partition của một partitioned table thường là segment riêng; index cũng có segment riêng. Khi khảo sát một đối tượng có partition/LOB, cần xem đúng `SEGMENT_TYPE` và segment tương ứng, không chỉ tìm tên bảng.

## 4. High Water Mark (HWM) là gì?

**High Water Mark** là mốc logic trong segment biểu thị vùng block đã được đưa vào phạm vi sử dụng của segment tính từ đầu segment. Đối với **full table scan thông thường**, Oracle xem xét các block thuộc vùng bên dưới HWM của segment liên quan; những block đã được cấp phát nhưng chưa đi vào vùng dưới HWM không cần được quét như dữ liệu bảng.

Hãy tưởng tượng 12 block của một bảng:

```text
Segment LAB_HWM, các block đã được cấp phát:

[0][1][2][3][4][5][6][7][8][9][10][11]
 |  |  |  |  |  |  |  |  |   |  |  |
 D  D  F  F  F  F  F  .  .  .   .  .
                     ^
                    HWM

D = có dữ liệu
F = từng dùng, nay không có row (ví dụ sau DELETE)
. = đã cấp phát nhưng chưa dùng, nằm trên HWM

Full table scan: vùng [0..6] cần được xét.
Không mặc nhiên quét vùng [7..11] chỉ vì đã cấp phát.
```

Đây là sơ đồ **logic**; các block metadata, bitmap và cách đọc I/O của Oracle không được thể hiện. Trong ASSM hiện đại còn có chi tiết low/high HWM như đã nói, và bộ máy SQL có thể dùng các tối ưu khác. Sơ đồ tập trung vào bản chất: **HWM là mốc scan quan trọng, không phải bộ đếm số dòng hiện có**.

### 4.1. HWM tăng khi nào?

Khi các thao tác chèn cần sử dụng thêm những block mới ngoài vùng đã sử dụng trước đó, Oracle có thể **nâng HWM**. Một segment có thể được cấp phát extent mới trước hoặc cùng lúc mở rộng vùng sử dụng.

Ví dụ:

```text
Bước A: 5 block đã sử dụng    [D][D][D][D][D][.][.][.]
                                 HWM ^ (sau block 4)

Bước B: chèn thêm nhiều row   [D][D][D][D][D][D][D][.]
                                       HWM ^ (sau block 6)
```

Các block ở phía dưới HWM chưa nhất thiết đầy. Sau nhiều lần chèn/xóa, segment có thể có những khoảng trống phân tán trong vùng đã được sử dụng.

### 4.2. HWM không tự hạ khi DELETE

Giả sử đã từng sử dụng 8 block rồi xóa hầu hết dòng:

```text
Trước DELETE:
[D][D][D][D][D][D][D][D][.][.]
                         ^
                        HWM

Sau DELETE:
[D][F][F][F][F][F][F][F][.][.]
                         ^
                        HWM gần như không đổi
```

`DELETE` xóa row và tạo undo/redo theo cơ chế transaction, nhưng không mặc nhiên thu hồi toàn bộ các block của segment hoặc đưa HWM xuống thấp. Khoảng trống dưới HWM có thể được tái sử dụng cho **conventional INSERT** sau này.

**Hệ quả:** Bảng còn rất ít row nhưng quét toàn bảng vẫn có thể phải xét nhiều block đã từng chứa dữ liệu.

### 4.3. HWM khác số block cấp phát

Có thể tồn tại:

- **Allocated blocks:** toàn bộ block thuộc các extent segment đã nhận.
- **Blocks below HWM:** vùng block đã nằm trong phạm vi sử dụng/scan của segment.
- **Blocks actually containing rows:** các block hiện có row còn sống.

Ba số liệu không bắt buộc bằng nhau. `USER_SEGMENTS.BLOCKS` phản ánh số block cấp phát, vì vậy không được sử dụng trực tiếp như chỉ số “block dưới HWM” hoặc “block đang chứa dữ liệu”.

## 5. HWM ảnh hưởng đến Full Table Scan như thế nào?

### 5.1. Bản chất của full table scan

Một **full table scan** đọc phạm vi block dữ liệu của bảng, thay vì dùng index để định vị một tập row nhỏ. Oracle thường đọc theo cơ chế multiblock I/O; tùy tình huống có thể dùng buffer cache hoặc direct path reads, serial hoặc parallel scan.

Về mặt nguyên tắc, vùng cần xem xét chịu ảnh hưởng lớn bởi phạm vi **dưới HWM**. Giả sử hai bảng có cùng **1.000 hàng hiện có**, nhưng:

- Bảng **A** mới chèn 1.000 row vào số block nhỏ.
- Bảng **B** từng chứa 1.000.000 row rồi `DELETE` chỉ còn 1.000.

Nếu B chưa thu gọn segment/HWM, full table scan của B có thể phải xử lý nhiều block hơn đáng kể. Việc filter chỉ trả về ít hàng không tự làm co phạm vi block của full scan.

### 5.2. “Quét đến HWM” không đồng nghĩa mọi block đều gây một lần physical I/O

Không nên kết luận số block dưới HWM chính xác bằng số lần đọc đĩa:

- Block đã có trong **buffer cache** có thể không cần đọc vật lý lần nữa.
- Multiblock I/O có thể đọc nhiều block trong một request.
- Direct path reads, parallel query, partition pruning và các tối ưu storage có thể thay đổi cách thực thi.
- Oracle có thể bỏ qua hoặc xử lý đặc biệt các vùng block theo metadata/bitmap nội bộ.
- Truy vấn sử dụng **index** phù hợp có thể không chọn full table scan.

HWM ảnh hưởng phạm vi scan, nhưng thời gian thực thi còn phụ thuộc cache, I/O, CPU, predicate, execution plan và workload.

### 5.3. Câu lệnh nào thực sự full-scan?

Ví dụ:

```sql
SELECT COUNT(*)
FROM lab_hwm;
```

Câu này **không đảm bảo** luôn dùng full table scan. Nếu có index phù hợp và optimizer chọn index fast full scan, đường truy cập sẽ khác. Cần xem execution plan.

Ví dụ kiểm tra plan dự kiến:

```sql
EXPLAIN PLAN FOR
SELECT COUNT(*)
FROM lab_hwm;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Trong bài lab không có index trên `LAB_HWM`, optimizer thường chọn `TABLE ACCESS FULL`. Nếu có nhiều partition, plan có thể sử dụng partition pruning; mỗi partition có segment/HWM riêng.

### 5.4. Giảm số row khác với giảm vùng phải quét

Giả sử trước dọn dữ liệu:

```text
Số row:                    500.000
Block dưới HWM:             10.000  (minh họa)
Extent đã cấp phát:             80
```

Sau `DELETE` 99%:

```text
Số row:                      5.000
Block dưới HWM:             ~10.000 (có thể vẫn gần như cũ)
Extent đã cấp phát:             80  (thường chưa đổi)
```

Full scan không mặc nhiên rẻ hơn 100 lần. Tuy nhiên, **index range scan** chọn lọc cho một điều kiện phù hợp có thể chỉ truy cập ít block; điều đó không phủ nhận tác động HWM lên full table scan.

### 5.5. Vì sao thống kê (statistics) không giải quyết HWM?

`DBMS_STATS.GATHER_TABLE_STATS` làm mới thống kê phục vụ optimizer, ví dụ số row và số block đã dùng theo thống kê. Nó **không** thực hiện tự động compact mọi row, không hạ HWM chỉ vì bảng còn ít dữ liệu.

Nếu số row đã giảm, optimizer có thể chọn execution plan khác dựa trên thống kê mới. Điều này thay đổi **cách truy cập**, nhưng không tương đương **giải phóng không gian vật lý**.

## 6. Các thao tác DML/DDL tác động tới HWM và extent

| Thao tác | Tác động điển hình đến HWM | Tác động đến extent đã cấp phát | Ý nghĩa cho full scan |
|---|---|---|---|
| **Conventional INSERT** | Có thể dùng free space dưới HWM; HWM tăng khi cần vùng block mới | Có thể xin extent mới khi thiếu chỗ | Phạm vi quét có thể tăng khi HWM nâng |
| **Direct-path INSERT** (ví dụ `APPEND`, nếu Oracle thực sự dùng direct path) | Thường ghi vào vùng phía trên HWM rồi cập nhật HWM khi hoàn tất thích hợp | Có thể mở rộng segment/cấp extent | Có thể làm tăng HWM dù bên dưới còn chỗ trống |
| **UPDATE** | Thường sửa row ở các block đã dùng; có thể cần thêm chỗ, row migration/chaining hoặc mở rộng trong một số trường hợp | Không nhất thiết đổi; có thể tăng tùy kích thước row và không gian còn lại | Tùy thay đổi phân bố block và HWM |
| **DELETE** | Thường **không hạ HWM** | Thường giữ extent | Nhiều block dưới HWM có thể rỗng nhưng vẫn nằm trong vùng scan |
| **TRUNCATE TABLE ... DROP STORAGE** | Đặt lại HWM của segment | Có thể giải phóng các extent không cần giữ theo điều kiện của segment | Full scan bảng rỗng thường xử lý rất ít block |
| **TRUNCATE TABLE ... REUSE STORAGE** | Đặt lại HWM | Giữ phần lớn/những extent đã được cấp phát để tái sử dụng | HWM thấp dù `USER_SEGMENTS.BLOCKS` vẫn có thể lớn |
| **ALTER TABLE ... SHRINK SPACE** | Có thể hạ HWM sau compact và bước thu gọn | Có thể trả bớt không gian cho tablespace | Có thể giảm phạm vi full scan |
| **ALTER TABLE ... MOVE** | Tạo lại phần lưu trữ của bảng; HWM theo segment mới | Có thể chuyển/cấp phát lại extent, tùy lựa chọn | Có thể loại bỏ vùng trống lớn; cần lưu ý ROWID/index |
| **DROP TABLE ... PURGE** | Không còn segment bảng để quét | Trả không gian theo cơ chế quản lý đối tượng/tablespace | Không còn đối tượng để full scan |

Bảng mô tả hành vi thường gặp đối với **heap table**. Index-organized tables, LOB, partitioned objects và các tùy chọn nén/không gian lưu trữ có quy tắc riêng.

### 6.1. DELETE: được rollback, không tự thu hồi extent

`DELETE` là DML có thể rollback trước khi commit:

```sql
DELETE FROM lab_hwm
WHERE id > 100;

COMMIT;
```

Oracle đánh dấu/xóa row theo cơ chế transaction và tạo undo/redo. Dù đã commit, `USER_SEGMENTS.BYTES` và HWM thường không giảm theo số row bị xóa. Nếu ứng dụng sắp insert dữ liệu mới, khoảng trống này có thể hữu ích để tái sử dụng.

### 6.2. TRUNCATE: dọn toàn bộ row và đặt lại HWM

`TRUNCATE TABLE` là DDL, thường nhanh hơn xóa từng row khi muốn bỏ toàn bộ dữ liệu. Nó tạo implicit commit theo ngữ nghĩa DDL và không thể rollback như một `DELETE` chưa commit.

```sql
TRUNCATE TABLE lab_hwm DROP STORAGE;
```

hoặc:

```sql
TRUNCATE TABLE lab_hwm REUSE STORAGE;
```

Cả hai đều bỏ toàn bộ row và đặt lại HWM; điểm khác biệt lớn là **giải phóng extent** so với **giữ extent để sử dụng lại**. `DROP STORAGE` thường vẫn giữ không gian tối thiểu theo đặc tính segment, thay vì bảo đảm `0 bytes`. `REUSE STORAGE` có thể giúp tránh cấp phát extent lần nữa khi ứng dụng định tải lại nhiều dữ liệu.

Chỉ áp dụng `TRUNCATE` khi **được phép xóa toàn bộ dữ liệu**. Trên hệ thống có khóa ngoại, materialized view log, flashback hoặc các ràng buộc vận hành khác, việc truncate còn phải xét thêm điều kiện/cú pháp/ảnh hưởng của đối tượng.

### 6.3. SHRINK SPACE: compact và hạ HWM

Ở những **heap table** trong tablespace dùng **ASSM**, lệnh `ALTER TABLE ... SHRINK SPACE` có thể di chuyển row để lấp khoảng trống, hạ HWM và trả lại không gian không cần thiết.

Thao tác điển hình:

```sql
ALTER TABLE lab_hwm ENABLE ROW MOVEMENT;

ALTER TABLE lab_hwm SHRINK SPACE COMPACT;

ALTER TABLE lab_hwm SHRINK SPACE;
```

- `ENABLE ROW MOVEMENT` cho phép Oracle chuyển row tới block khác, có thể làm **ROWID thay đổi**. Ứng dụng không được giả định ROWID sẽ bất biến.
- `SHRINK SPACE COMPACT` compact dữ liệu nhưng **chưa thực hiện bước hạ HWM/giải phóng không gian cuối cùng**; hữu ích khi muốn tách giai đoạn xếp lại row khỏi giai đoạn điều chỉnh HWM.
- `SHRINK SPACE` hoàn tất thao tác thu gọn phù hợp, bao gồm khả năng hạ HWM và trả về không gian.

Nếu không cần chia pha, trong trường hợp đủ điều kiện có thể dùng `SHRINK SPACE` trực tiếp. Các lệnh này có thể phát sinh redo/undo, tốn I/O, thay đổi ROWID và tạo các giai đoạn khóa; không phải mọi loại segment hoặc cấu hình đều hỗ trợ shrink.

### 6.4. MOVE: tạo lại segment

`ALTER TABLE ... MOVE` về bản chất tổ chức lại phần lưu trữ của bảng vào segment được tạo lại. Nếu bảng có nhiều block rỗng do `DELETE`, việc tạo lại có thể làm vùng dữ liệu gọn hơn.

Ví dụ hình thức tổng quát:

```sql
ALTER TABLE lab_hwm MOVE;
```

Những điều cần cân nhắc:

- Row có thể đổi **ROWID**.
- Index liên quan có thể cần được duy trì/tạo lại theo phiên bản, loại index và lựa chọn online/offline; tránh giả định index luôn tiếp tục usable sau mọi biến thể MOVE.
- Có thể cần thêm dung lượng tạm thời hoặc không gian cho segment mới; có khả năng ảnh hưởng DML/concurrent sessions.
- Hành vi và hỗ trợ `MOVE ONLINE` phụ thuộc phiên bản, edition và đặc điểm bảng.

Đây là thao tác tổ chức lại vật lý có ảnh hưởng vận hành, không phải cách chữa mặc định cho mọi bảng lớn.

## 7. Vì sao APPEND có thể khiến HWM tăng nhanh?

Cách chèn **conventional** thường ưu tiên sử dụng những block đủ chỗ, kể cả khoảng trống dưới HWM. **Direct-path INSERT** thì thường chèn vào vùng mới phía trên HWM nhằm tối ưu quá trình tải dữ liệu lớn.

Ví dụ cú pháp yêu cầu optimizer cân nhắc direct path:

```sql
INSERT /*+ APPEND */ INTO lab_hwm (id, payload)
SELECT level, RPAD('A', 80, 'A')
FROM dual
CONNECT BY level <= 10000;

COMMIT;
```

Điều kiện thực tế quyết định Oracle có áp dụng direct path hay chuyển sang conventional insert; hint không bảo đảm mọi môi trường đều thực thi đúng như yêu cầu. Direct-path insert cũng có các ràng buộc và tác động riêng lên đồng thời truy cập/transaction.

Tình huống điển hình:

1. Bảng từng có rất nhiều row, sau đó `DELETE` gần hết → nhiều block trống dưới HWM.
2. Nếu chèn theo conventional path, Oracle có thể tái sử dụng các block đó.
3. Nếu chèn theo direct path, Oracle có thể mở rộng dữ liệu phía trên HWM, khiến segment tăng thêm dù còn khoảng trống bên dưới.

Vì vậy, lựa chọn phương thức tải dữ liệu cần phù hợp mục tiêu throughput, concurrency và dung lượng của hệ thống.

## 8. Thí nghiệm: INSERT → DELETE → quan sát scan → SHRINK

Thí nghiệm sau chạy **chỉ trong schema lab**, trên bảng tự tạo `LAB_HWM`. Không chạy lên bảng production. Tài khoản cần quyền tạo bảng và quota tablespace phù hợp. Nếu thiếu quyền `DBMS_STATS`, `DBMS_XPLAN` hoặc `DBMS_SPACE`, dùng các truy vấn được cấp quyền hoặc nhờ DBA hỗ trợ.

### 8.1. Tạo bảng không có index

```sql
CREATE TABLE lab_hwm (
    id      NUMBER NOT NULL,
    payload VARCHAR2(200 CHAR) NOT NULL
)
SEGMENT CREATION IMMEDIATE;
```

Chưa tạo index nhằm giữ ví dụ đơn giản: phép `COUNT(*)` thường phải đọc trực tiếp segment bảng.

### 8.2. Chèn nhiều row để mở rộng vùng lưu trữ

```sql
INSERT INTO lab_hwm (id, payload)
SELECT level, RPAD('X', 120, 'X')
FROM dual
CONNECT BY level <= 30000;

COMMIT;

SELECT COUNT(*) AS row_count
FROM lab_hwm;
```

Kết quả mong đợi `ROW_COUNT = 30000`. Tùy block size và không gian có sẵn, số extent và block thực tế khác nhau giữa các máy.

Xem mức cấp phát:

```sql
SELECT segment_name, extents, blocks, bytes
FROM user_segments
WHERE segment_name = 'LAB_HWM'
  AND segment_type = 'TABLE';

SELECT extent_id, file_id, block_id, blocks
FROM user_extents
WHERE segment_name = 'LAB_HWM'
  AND segment_type = 'TABLE'
ORDER BY extent_id;
```

Thu thập optimizer statistics:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname => USER,
    tabname => 'LAB_HWM'
  );
END;
/
```

Sau đó:

```sql
SELECT table_name, num_rows, blocks, empty_blocks, last_analyzed
FROM user_tables
WHERE table_name = 'LAB_HWM';
```

`USER_TABLES.NUM_ROWS`, `BLOCKS`, `EMPTY_BLOCKS` là **thống kê** sau khi gather, không phải bộ đếm chính xác tức thời cho mọi transaction. Trong cách đọc điển hình, `USER_TABLES.BLOCKS` được dùng để phản ánh block đã sử dụng dưới HWM theo thống kê; nó khác với **toàn bộ block đã cấp phát** trong `USER_SEGMENTS.BLOCKS`.

### 8.3. Ghi lại execution plan trước khi xóa

```sql
EXPLAIN PLAN FOR
SELECT COUNT(*)
FROM lab_hwm;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Với bảng không index như trên, thường thấy plan chứa:

```text
TABLE ACCESS FULL  LAB_HWM
```

`EXPLAIN PLAN` là **plan dự kiến**; không cung cấp số block đã thực sự đọc hoặc thời gian chạy thực tế. Khi có quyền xem thống kê cursor, có thể dùng:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS FULL(t) */ COUNT(*)
FROM lab_hwm t;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(
    NULL, NULL, 'ALLSTATS LAST'
));
```

`GATHER_PLAN_STATISTICS` thu thập số liệu thực thi cho câu truy vấn khi Oracle hỗ trợ; `ALLSTATS LAST` có thể hiển thị thống kê lần chạy gần nhất như số hàng, buffer gets và các thông tin I/O. Quyền truy cập các dynamic performance views và khả năng chọn đúng cursor phụ thuộc môi trường; nếu không có quyền, chỉ dùng `EXPLAIN PLAN`.

Để so sánh đáng tin cậy, giữ cùng client/phiên kết nối khi có thể và chú ý các lần chạy sau được hưởng cache ấm hơn.

### 8.4. DELETE gần hết row rồi đo lại

```sql
DELETE FROM lab_hwm
WHERE id > 100;

COMMIT;

SELECT COUNT(*) AS row_count
FROM lab_hwm;
```

Kết quả còn `100` row. Đọc số block/extent cấp phát:

```sql
SELECT extents, blocks, bytes
FROM user_segments
WHERE segment_name = 'LAB_HWM'
  AND segment_type = 'TABLE';
```

Trong trường hợp điển hình, số `EXTENTS`, `BLOCKS` và `BYTES` của segment **không giảm đáng kể chỉ vì DELETE**.

Gom thống kê lại sau delete:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname => USER,
    tabname => 'LAB_HWM'
  );
END;
/

SELECT num_rows, blocks, empty_blocks
FROM user_tables
WHERE table_name = 'LAB_HWM';
```

Điểm quan sát:

- `NUM_ROWS` gần với số row mới (100), nếu gather thành công và phù hợp.
- `BLOCKS` theo thống kê có thể vẫn lớn so với 100 row do vùng dưới HWM chưa được thu gọn.
- `USER_SEGMENTS.BLOCKS` vẫn phản ánh vùng cấp phát, có thể lớn hơn `USER_TABLES.BLOCKS`.

Tiếp tục kiểm tra plan/scan:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS FULL(t) */ COUNT(*)
FROM lab_hwm t;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(
    NULL, NULL, 'ALLSTATS LAST'
));
```

Dù chỉ còn 100 row, full table scan có thể vẫn phải xét vùng block dưới HWM lớn. Không dùng một lần đo thời gian chạy để khẳng định chính xác tác động HWM: cache, background I/O và thống kê truy vấn cũng ảnh hưởng kết quả.

### 8.5. Thu gọn segment rồi quan sát lại

Nếu môi trường dùng **ASSM** và bảng đủ điều kiện để shrink:

```sql
ALTER TABLE lab_hwm ENABLE ROW MOVEMENT;

ALTER TABLE lab_hwm SHRINK SPACE COMPACT;

ALTER TABLE lab_hwm SHRINK SPACE;
```

Kiểm tra:

```sql
SELECT COUNT(*) AS row_count
FROM lab_hwm;

SELECT extents, blocks, bytes
FROM user_segments
WHERE segment_name = 'LAB_HWM'
  AND segment_type = 'TABLE';
```

Thu thập thống kê lại:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname => USER,
    tabname => 'LAB_HWM'
  );
END;
/

SELECT num_rows, blocks, empty_blocks
FROM user_tables
WHERE table_name = 'LAB_HWM';
```

Thử lại full scan để quan sát thông số:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS FULL(t) */ COUNT(*)
FROM lab_hwm t;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(
    NULL, NULL, 'ALLSTATS LAST'
));
```

Nếu shrink thành công, HWM và phạm vi full table scan **có thể giảm rõ rệt**. Tùy số row giữ lại, kích thước row, metadata và cơ chế cấp phát, dung lượng segment sau shrink không nhất thiết giảm về số block tối thiểu lý thuyết.

Khi không còn cần row movement cho bài lab, có thể khôi phục:

```sql
ALTER TABLE lab_hwm DISABLE ROW MOVEMENT;
```

Đây là lựa chọn vận hành tùy nhu cầu; việc tắt lại row movement không đưa các ROWID đã thay đổi về giá trị cũ.

### 8.6. Thí nghiệm thay thế với TRUNCATE

Nếu muốn quan sát HWM đặt lại mà vẫn giữ extent, sau khi đã hoàn tất nhánh thử nghiệm trên bảng lab:

```sql
TRUNCATE TABLE lab_hwm REUSE STORAGE;

SELECT COUNT(*) FROM lab_hwm;

SELECT extents, blocks, bytes
FROM user_segments
WHERE segment_name = 'LAB_HWM'
  AND segment_type = 'TABLE';
```

Lúc này bảng không còn row và HWM đã được đặt lại, trong khi số extent cấp phát có thể vẫn đáng kể vì chọn `REUSE STORAGE`. Đây là minh họa trực tiếp rằng **không gian cấp phát** và **vùng phải quét theo HWM** là hai đại lượng khác nhau.

Nếu muốn xóa bảng thí nghiệm khi đã xong:

```sql
DROP TABLE lab_hwm PURGE;
```

`DROP TABLE ... PURGE` xóa đối tượng khỏi schema mà không đưa bảng vào recycle bin; chỉ chạy trên **bảng lab tự tạo**, sau khi chắc chắn không cần dữ liệu.

## 9. Đo HWM và không gian chưa dùng bằng DBMS_SPACE

`USER_SEGMENTS` cho biết tổng extent/blocks cấp phát; muốn ước lượng vùng chưa dùng phía trên HWM, có thể dùng package **`DBMS_SPACE`** trong môi trường được cấp quyền.

### 9.1. DBMS_SPACE.UNUSED_SPACE

Ví dụ cho heap table không partition:

```sql
SET SERVEROUTPUT ON

DECLARE
  l_total_blocks          NUMBER;
  l_total_bytes           NUMBER;
  l_unused_blocks         NUMBER;
  l_unused_bytes          NUMBER;
  l_last_used_extent_file NUMBER;
  l_last_used_extent_blk  NUMBER;
  l_last_used_block       NUMBER;
BEGIN
  DBMS_SPACE.UNUSED_SPACE(
    segment_owner              => USER,
    segment_name               => 'LAB_HWM',
    segment_type               => 'TABLE',
    total_blocks               => l_total_blocks,
    total_bytes                => l_total_bytes,
    unused_blocks              => l_unused_blocks,
    unused_bytes               => l_unused_bytes,
    last_used_extent_file_id   => l_last_used_extent_file,
    last_used_extent_block_id  => l_last_used_extent_blk,
    last_used_block            => l_last_used_block
  );

  DBMS_OUTPUT.PUT_LINE(
    'Total allocated blocks: ' || l_total_blocks
  );
  DBMS_OUTPUT.PUT_LINE(
    'Unused blocks above HWM: ' || l_unused_blocks
  );
  DBMS_OUTPUT.PUT_LINE(
    'Last used block in extent: ' || l_last_used_block
  );
END;
/
```

Các trường tổng và unused phản ánh không gian cấp phát/chưa dùng theo cách package mô tả, không nên tự xem phần chênh lệch của chúng là chính xác **số block có row**.

**Trường hợp sau DELETE:** Phần lớn block trở nên rỗng nhưng vẫn nằm **dưới HWM**; vì vậy chỉ số `UNUSED_BLOCKS` (không gian chưa dùng phía trên HWM) có thể **không tăng tương ứng** với số row vừa xóa. Đây là điều quan trọng khi diễn giải kết quả.

`LAST_USED_BLOCK` thể hiện vị trí block đã dùng trong extent cuối được báo cáo theo interface package; nó không thay thế cho một “block_id tuyệt đối của HWM” dùng chung trên mọi datafile.

### 9.2. DBMS_SPACE.SPACE_USAGE và ASSM

Với ASSM, `DBMS_SPACE.SPACE_USAGE` cung cấp phân bố các block theo mức sử dụng không gian (như các nhóm phần trăm free space). Các nhóm block có tỷ lệ trống cao có thể tăng sau `DELETE`, dù HWM không thay đổi.

Về mặt khái niệm:

```text
UNUSED_SPACE:
    Quan tâm các block chưa dùng phía trên HWM.

SPACE_USAGE trong ASSM:
    Quan tâm tình trạng đầy/trống của các block được quản lý
    ở những mức free-space khác nhau.

USER_SEGMENTS:
    Tổng các extent/blocks được cấp phát.

USER_TABLES statistics:
    Thông tin phục vụ optimizer, chỉ mới khi gather.
```

Dùng đúng phép đo cho đúng câu hỏi. Một số phiên bản/loại segment có thêm tham số hoặc giới hạn trong `DBMS_SPACE`, vì vậy cần đối chiếu API theo phiên bản Oracle đang dùng.

## 10. Ba hiện tượng dễ nhầm trong vận hành

### 10.1. “Tablespace còn trống, tại sao full scan vẫn chậm?”

Free space của tablespace cho biết còn không gian **chưa cấp phát** cho các segment. Nó không làm thay đổi ngay những block nằm dưới HWM của bảng đã được cấp phát trước đó.

Ví dụ:

```text
TABLESPACE USERS: còn trống 50 GiB
SEGMENT HISTORY_LOG:  đã cấp phát 10 GiB
Rows còn lại:         10.000
HWM vẫn cao do từng chứa hàng chục triệu row
```

Việc tablespace còn nhiều GiB không giúp quét `HISTORY_LOG` tự bỏ qua các block rỗng dưới HWM. Muốn đánh giá cần xem plan, thống kê segment và cách table được sử dụng.

### 10.2. “Sau DELETE, bảng nhỏ nhưng USER_SEGMENTS.BYTES không giảm”

Đây là hành vi thường gặp: `DELETE` xóa dòng và để lại chỗ trống tái sử dụng; việc giữ extent có lợi nếu bảng sẽ lại được insert. Nếu bảng sắp tăng trở lại, thu gọn rồi cấp phát lại có thể làm tăng I/O và công việc quản trị không cần thiết.

### 10.3. “Sau TRUNCATE REUSE STORAGE, segment vẫn lớn nhưng full scan rất ít việc”

`TRUNCATE REUSE STORAGE` đặt lại HWM nhưng giữ extent để tái sử dụng. Do đó:

- `USER_SEGMENTS.BYTES` có thể tiếp tục lớn.
- Bảng hiện không có row.
- Phạm vi full table scan của bảng rỗng được giảm theo HWM, không bắt buộc quét toàn bộ extent đã cấp phát.

Đây là ví dụ tốt nhất để phân biệt **allocated space** và **scan range**.

## 11. Partitioning làm phạm vi scan thay đổi ra sao?

Một partitioned table thường gồm **segment riêng cho từng partition**, mỗi segment có extent và HWM riêng. Khi điều kiện truy vấn cho phép **partition pruning**, Oracle chỉ cần scan các partition có liên quan thay vì toàn bộ bảng.

Ví dụ khái niệm:

```text
TABLE SALES
├─ PARTITION P2024: segment + HWM riêng
├─ PARTITION P2025: segment + HWM riêng
└─ PARTITION P2026: segment + HWM riêng
```

Truy vấn:

```sql
SELECT COUNT(*)
FROM sales
WHERE sale_date >= DATE '2026-01-01'
  AND sale_date <  DATE '2027-01-01';
```

Nếu partitioning và kiểu điều kiện phù hợp, optimizer có thể chỉ cần scan `P2026`. Khi đó **HWM của P2024/P2025 không nằm trong phạm vi scan của truy vấn**.

Ngược lại, với điều kiện không cho phép pruning, Oracle có thể phải scan nhiều segment. Khi dọn dữ liệu theo thời gian, một chiến lược partition management phù hợp có thể hiệu quả hơn `DELETE` hàng triệu row, nhưng thao tác `TRUNCATE PARTITION`/`DROP PARTITION` là DDL có tác động dữ liệu, index và ứng dụng, phải được thiết kế cẩn thận.

## 12. HWM có liên quan đến Index Scan không?

Index cũng là một segment có block và extent riêng, nhưng cấu trúc truy cập phổ biến của **B-tree index** khác heap table.

- **Index range scan** lần theo branch/leaf blocks theo khóa, thường không quét vùng bảng đến HWM chỉ để tìm một nhóm row nhỏ.
- **Index fast full scan** đọc toàn bộ index theo phương pháp phù hợp; có thể là lựa chọn thay cho table full scan khi index chứa thông tin đủ để trả kết quả.
- Bảng vẫn có thể bị truy cập theo ROWID từ index, khiến số block bảng thực sự đọc phụ thuộc phân bố row, clustering factor, cache, v.v.
- Xóa row có thể để lại không gian trống trong index; cơ chế tái sử dụng/maintenance của index không giống hoàn toàn việc hạ HWM của heap table.

Bởi vậy, **“HWM cao” không có nghĩa mọi câu SQL trên bảng đều chậm**. Phải xem SQL dùng `TABLE ACCESS FULL`, `INDEX RANGE SCAN`, `INDEX FAST FULL SCAN` hay đường truy cập khác trước khi chọn hướng xử lý.

## 13. Cân nhắc khi muốn giảm thời gian scan

Nếu một bảng có HWM cao và full scan trở thành bottleneck, không nên chạy `SHRINK` hay `MOVE` ngay lập tức. Cần trả lời một số câu hỏi kỹ thuật:

| Câu hỏi | Vì sao cần trả lời? |
|---|---|
| Query thật có dùng `TABLE ACCESS FULL` không? | Nếu plan dùng index/partition pruning, HWM của toàn bảng có thể không phải nút thắt chính |
| Bảng có thường xuyên tăng dữ liệu trở lại không? | Thu gọn có thể gây cấp phát lại không cần thiết |
| Khối lượng dữ liệu rỗng dưới HWM có lớn không? | Ít block trống thì lợi ích shrink có thể hạn chế |
| Query chủ yếu bị chờ I/O, CPU hay contention? | Giải pháp phải bám sát nguyên nhân |
| Tablespace dùng ASSM và table có đủ điều kiện `SHRINK`? | Không phải tất cả loại segment/cấu hình hỗ trợ |
| Ứng dụng có lưu ROWID hoặc phụ thuộc ROWID không đổi? | `SHRINK`/`MOVE` có thể đổi ROWID |
| Có index, FK, LOB, partition, compression hoặc cấu hình đặc biệt không? | Ảnh hưởng bảo trì/phục hồi và hạn chế DDL có thể khác |
| Thao tác có thể chạy trong maintenance window không? | Thu gọn/tổ chức lại segment có thể tạo I/O, redo/undo và khóa |

Các lựa chọn có thể bao gồm: giữ free space để tái sử dụng; cải thiện index/predicate/partitioning; cập nhật statistics; shrink/move trong cửa sổ bảo trì; hoặc thay đổi chính sách lưu giữ dữ liệu bằng partition.

Đừng dựa duy nhất vào `USER_SEGMENTS.BYTES`: một bảng dùng ít dòng hơn nhưng có extent lớn không nhất thiết là vấn đề nếu các truy vấn trọng yếu đã dùng truy cập chọn lọc.

## 14. Lưu ý về thống kê và đo hiệu năng

### 14.1. Chọn đại lượng đo đúng

| Cần đánh giá | Công cụ/số liệu phù hợp | Điều không nên suy ra |
|---|---|---|
| Tổng số block đã cấp phát | `USER_SEGMENTS.BLOCKS/BYTES/EXTENTS` | Không suy ra trực tiếp block có row hoặc block dưới HWM |
| Danh sách extent | `USER_EXTENTS` | Không suy ra có bao nhiêu row trong mỗi extent |
| Số row và số block theo optimizer stats | `USER_TABLES.NUM_ROWS/BLOCKS` sau `DBMS_STATS` | Không mặc định là giá trị live sau mọi DML |
| Vùng unused trên HWM | `DBMS_SPACE.UNUSED_SPACE` | Không đo hết các lỗ trống trong vùng dưới HWM |
| Mức đầy các block ASSM | `DBMS_SPACE.SPACE_USAGE` | Không tự chứng minh một truy vấn sẽ dùng full scan |
| Đường truy cập dự kiến | `EXPLAIN PLAN` và `DBMS_XPLAN.DISPLAY` | Không phải số liệu chạy thật |
| Đường truy cập và số liệu một lần chạy | `DBMS_XPLAN.DISPLAY_CURSOR(..., 'ALLSTATS LAST')` khi có quyền và instrumentation | Không coi duration một lần chạy là benchmark toàn diện |

### 14.2. Tránh so thời gian một lần chạy

Nếu chạy cùng truy vấn hai lần, lần sau có thể nhanh hơn vì **cache đã ấm**, không phải vì HWM đã thay đổi. Khi cần khảo sát hiệu năng nghiêm túc, đo nhiều lần trong điều kiện tương đương, xem physical reads, buffer gets, rows processed và execution plan. Các wait event và thống kê I/O hỗ trợ xác định nguyên nhân.

### 14.3. Không thay đổi môi trường bằng thử nghiệm có tác động lớn

Các lệnh `TRUNCATE`, `SHRINK`, `MOVE`, tải dữ liệu bằng `APPEND` và những thủ thuật “ép scan” đều có thể làm thay đổi dữ liệu hoặc ảnh hưởng hệ thống. Chỉ dùng bảng thuộc schema lab. Với hệ thống có người dùng khác, thu thập bằng chứng trước, đưa ra phương án và thực hiện thay đổi theo quy trình được phê duyệt.

## 15. Câu hỏi ôn tập

### Câu 1. Extent khác segment ở điểm nào?

**Đáp án:** Extent là đơn vị gồm các Oracle blocks liên tiếp được cấp phát trong một datafile. Segment là tập hợp các extent để lưu dữ liệu một đối tượng như bảng hoặc index. Một segment có thể gồm nhiều extent ở nhiều vị trí/datafile thuộc tablespace.

### Câu 2. Vì sao xóa 99% row có thể không làm full table scan giảm công việc tương ứng?

**Đáp án:** Vì `DELETE` thường không hạ HWM và không trả lại extent. Nhiều block trống dưới HWM vẫn nằm trong phạm vi cần xem xét của full table scan.

### Câu 3. USER_SEGMENTS.BLOCKS có phải số block dưới HWM không?

**Đáp án:** Không. `USER_SEGMENTS.BLOCKS` phản ánh các block **được cấp phát**. Số block dưới HWM có thể nhỏ hơn, và số block thực tế chứa row có thể nhỏ hơn nữa.

### Câu 4. Điều gì khác nhau giữa TRUNCATE DROP STORAGE và REUSE STORAGE?

**Đáp án:** Cả hai xóa toàn bộ row và đặt lại HWM. `DROP STORAGE` có thể giải phóng extent không cần giữ, còn `REUSE STORAGE` giữ phần lớn không gian cấp phát để tải lại dữ liệu.

### Câu 5. Vì sao SHRINK SPACE COMPACT chưa tương đương SHRINK SPACE hoàn chỉnh?

**Đáp án:** Pha `COMPACT` chủ yếu sắp xếp row để gom chỗ trống; bước `SHRINK SPACE` hoàn chỉnh mới điều chỉnh HWM và giải phóng không gian thích hợp. Cần kiểm tra điều kiện ASSM, row movement và hỗ trợ của loại segment.

### Câu 6. Có thể dùng thống kê optimizer để “hạ HWM” không?

**Đáp án:** Không. `DBMS_STATS` cập nhật thống kê để optimizer quyết định plan; không tự compact/hạ HWM hay giải phóng extent.

### Câu 7. APPEND có luôn tận dụng block trống dưới HWM không?

**Đáp án:** Không. Direct-path insert thường ghi vào vùng phía trên HWM; conventional insert thường có khả năng tái sử dụng block dưới HWM. Oracle chỉ dùng direct path khi điều kiện thực thi cho phép.

### Câu 8. Một bảng có HWM cao nhưng SQL dùng index range scan. Có nhất thiết phải shrink bảng không?

**Đáp án:** Không. Phải xem bottleneck thực sự, các block được truy cập và workload. HWM chủ yếu là dữ kiện quan trọng với phạm vi full scan; quyết định shrink/move cần dựa trên đo lường và tác động vận hành.

---

## 16. Tóm lược các mối quan hệ quan trọng

```text
TABLESPACE có free space
    |
    v
Oracle cấp EXTENT cho SEGMENT khi cần
    |
    v
SEGMENT có allocated blocks
    |
    +-- Vùng dưới HWM: đã vào phạm vi sử dụng;
    |                 có thể chứa nhiều block rỗng sau DELETE
    |
    +-- Vùng trên HWM: đã được cấp phát nhưng chưa dùng
                       trong phạm vi quét dữ liệu hiện tại

INSERT thông thường  -> có thể tái sử dụng free space dưới HWM
INSERT direct path    -> thường sử dụng vùng mới trên HWM
DELETE               -> xóa row, HWM thường không giảm
TRUNCATE             -> đặt lại HWM; DROP/REUSE khác nhau về extent
SHRINK / MOVE        -> có thể thu gọn hoặc tổ chức lại segment
DBMS_STATS           -> cập nhật số liệu tối ưu hóa, không hạ HWM

FULL TABLE SCAN       -> HWM ảnh hưởng phạm vi block cần xem xét
INDEX / PARTITION     -> có thể làm query truy cập phạm vi nhỏ hơn
```

Khi phân tích một truy vấn Oracle chậm sau đợt xóa dữ liệu lớn, hãy tách riêng **row count**, **extent allocation**, **HWM**, **execution plan** và **I/O thực tế**. Chỉ khi các bằng chứng cho thấy vùng scan lớn dưới HWM là yếu tố đáng kể thì các biện pháp thu gọn/tái tổ chức segment mới là lựa chọn có cơ sở.

### Tài liệu Oracle nên tham khảo

- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — Data Blocks, Extents, Segments, tablespaces và quản lý không gian lưu trữ.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — `TRUNCATE TABLE`, `ALTER TABLE ... SHRINK SPACE`, `ALTER TABLE ... MOVE` và các ràng buộc áp dụng.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — `DBMS_SPACE.UNUSED_SPACE`, `DBMS_SPACE.SPACE_USAGE`, `DBMS_STATS`.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — Full table scans, execution plans, optimizer statistics và cách đọc chỉ số I/O.

Các view, quyền truy cập, khả năng shrink và chi tiết phân bổ block phụ thuộc phiên bản/edition Oracle và loại segment. Đối chiếu đúng tài liệu của database đang sử dụng khi áp dụng trong môi trường thật.

