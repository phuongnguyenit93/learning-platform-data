# Block header, row piece, row chaining và row migration

Trong Oracle Database, ứng dụng nhìn thấy **một hàng** qua câu lệnh `SELECT`, nhưng Oracle phải lưu hàng đó vào những **data block** có kích thước hữu hạn. Mỗi block cần chừa chỗ cho metadata để quản lý chính block, giao dịch và vị trí các hàng. Một hàng SQL có thể được biểu diễn bằng **một hoặc nhiều row piece**; không phải lúc nào toàn bộ hàng cũng nằm gọn trong một block.

Hai tình huống đặc biệt rất quan trọng khi phân tích lưu trữ và hiệu năng là:

- **Row chaining:** Oracle phải biểu diễn một hàng bằng nhiều row piece được liên kết, điển hình vì hàng quá lớn để nằm trong một data block.
- **Row migration:** một hàng ban đầu nằm gọn trong một block, sau đó **tăng kích thước khi `UPDATE`**, không còn đủ chỗ tại block gốc; Oracle chuyển phần dữ liệu hàng sang vị trí mới và giữ thông tin chuyển tiếp ở vị trí ban đầu.

Để hiểu sự khác nhau, trước tiên cần hiểu **block header**, **row directory**, **row piece** và mối quan hệ giữa **ROWID** với vị trí lưu trữ.

## 1. Data block là đơn vị lưu trữ nào?

Oracle tổ chức lưu trữ theo các tầng:

```text
TABLE / INDEX / LOB ... (đối tượng logic)
              |
          SEGMENT
              |
           EXTENT
              |
       ORACLE DATA BLOCK
              |
         DATAFILE
              |
      Storage của hệ thống
```

- **Data block** là đơn vị lưu trữ logic nhỏ nhất Oracle dùng để quản lý dữ liệu trong database. Block thuộc một datafile và được cấp phát cho các segment qua những extent.
- **Extent** là một tập các data block liên tiếp được cấp phát cho một segment; một segment có thể gồm nhiều extent.
- **Segment** là vùng lưu trữ của đối tượng như bảng heap hoặc index. Segment có nhiều block; một block của bảng heap thường lưu nhiều hàng nhỏ.
- Kích thước Oracle block hay gặp là **8 KB**, nhưng đây **không phải hằng số cho mọi database**. Có môi trường dùng kích thước block khác và một số tablespace có nondefault block size.

Nếu một Oracle block có kích thước 8 KB, điều đó **không có nghĩa** mỗi hàng có thể dùng trọn 8 KB. Một phần block dành cho header, directory, quản lý giao dịch và các thông tin nội bộ. Phần trống phục vụ cập nhật cũng ảnh hưởng đến dung lượng có thể nhét thêm vào block.

> **Phạm vi của bài:** sơ đồ và ví dụ tập trung vào **heap-organized table** thông thường, nơi các hàng được lưu trong table data blocks. Index-organized table (IOT), cluster, row compression, Hybrid Columnar Compression, LOB ngoài dòng và các dạng tổ chức đặc biệt có cách lưu/quan sát khác; không lấy byte layout ở đây làm đặc tả cố định cho mọi dạng segment hoặc mọi release.

## 2. Bên trong một Oracle data block

Sơ đồ khái niệm cho block dữ liệu của một bảng heap:

```text
                  ORACLE DATA BLOCK
   +---------------------------------------------+
   | COMMON + VARIABLE BLOCK HEADER              |
   | - loại block, thông tin nhận diện/trạng thái |
   | - metadata giao dịch, ITL entries ...       |
   +---------------------------------------------+
   | TABLE DIRECTORY                             |
   | - thông tin table có hàng trong block       |
   +---------------------------------------------+
   | ROW DIRECTORY                               |
   | - các entry trỏ đến row piece trong block   |
   +---------------------------------------------+
   |                                             |
   |       FREE SPACE (phụ thuộc thực trạng)     |
   |                                             |
   +---------------------------------------------+
   | ROW DATA / ROW PIECES                       |
   | - row piece A                               |
   | - row piece B                               |
   | - row piece C ...                           |
   +---------------------------------------------+

   Hình minh họa logic; thứ tự byte và kích thước
   thực tế phụ thuộc loại block, release, cấu hình.
```

Oracle có thể dùng không gian trống giữa directory và row data, và các vùng này có thể phát triển theo hướng khác nhau. Sơ đồ không thể hiện mọi chi tiết nội bộ và **không dùng để suy ra offset byte tuyệt đối**.

### 2.1. Block header dùng để làm gì?

**Block header** chứa thông tin giúp Oracle nhận biết và quản lý block. Một số nội dung quan trọng về mặt khái niệm:

| Nhóm thông tin | Vai trò |
| --- | --- |
| Thông tin chung của block | Nhận diện loại block, thông tin địa chỉ/trạng thái và metadata để Oracle kiểm tra, sử dụng block đúng mục đích |
| Thông tin phiên bản/thay đổi | Thông tin liên quan đến thời điểm thay đổi, SCN và cơ chế nhất quán/phục hồi |
| **Transaction header / ITL** | Các mục **Interested Transaction List** hỗ trợ theo dõi giao dịch đang tác động lên các row trong block |
| Thông tin quản lý không gian | Metadata mà Oracle cần để định vị hàng, quản lý vùng còn dùng được và cập nhật block |

Không nên hiểu header như một đối tượng SQL có thể `SELECT` trực tiếp. Đây là cấu trúc bên trong block; các thông tin đã được Oracle trình bày thành metadata và thống kê thích hợp ở các data dictionary/dynamic performance views. Khi cần xem dump block ở mức byte, đó là công việc chẩn đoán nâng cao, phụ thuộc phiên bản và đặc quyền.

#### ITL không phải “mỗi hàng một giao dịch”

**ITL entry** liên hệ block với transaction và hỗ trợ cơ chế khóa hàng/nhất quán. Oracle có thể có nhiều giao dịch thay đổi các hàng khác nhau trong cùng một block. Những row header được đánh dấu theo thông tin giao dịch phù hợp; **ITL thuộc metadata cấp block**, không phải mỗi `UPDATE` nhất thiết tạo thêm một row piece.

Tham số lưu trữ **`INITRANS`** có liên quan đến số ITL entry được chuẩn bị ban đầu trong block. Tình trạng tranh chấp ITL giữa các giao dịch là một vấn đề cạnh tranh truy cập; nó **không đồng nghĩa** row migration hoặc row chaining.

### 2.2. Table directory và row directory

- **Table directory** lưu thông tin nhận diện bảng liên quan đến các hàng trong block. Trong heap table thông thường, các hàng thường thuộc cùng một bảng; cơ chế block khác như cluster có thể phức tạp hơn.
- **Row directory** giữ các entry chỉ tới vị trí **row piece** bên trong block. Về mặt khái niệm, Oracle có thể tìm được row piece bằng *slot* của nó trong block.

Một row directory entry **không đảm bảo** nó đại diện cho toàn bộ một hàng SQL nằm tại một chỗ. Entry có thể dẫn đến row piece đầu tiên của một chuỗi hoặc đến thông tin chuyển tiếp của một hàng đã migration.

### 2.3. Free space và ý nghĩa của `PCTFREE`

Oracle cần vùng trống trong block để chèn thêm hàng và để hàng hiện có **tăng kích thước khi cập nhật**.

Với table heap thông thường, **`PCTFREE`** là cấu hình phần trăm không gian của block dành cho việc cập nhật các hàng đã nằm trong block, thay vì tiếp tục nhét thêm hàng mới cho đến sát giới hạn. Ví dụ:

```sql
CREATE TABLE orders_storage (
    order_id NUMBER PRIMARY KEY,
    note     VARCHAR2(1000)
) PCTFREE 20;
```

`PCTFREE 20` diễn tả chủ ý dành dư địa tăng trưởng tại thời điểm quản lý chèn hàng vào block; **không phải** cam kết 20% block luôn trống vĩnh viễn, và cũng không tự động phân bổ lại những hàng đã tồn tại để sửa ngay tất cả migrated rows.

Trong **Automatic Segment Space Management (ASSM)**, Oracle sử dụng bitmap để quản lý các mức độ đầy của block. Cách block được chọn để chèn hàng còn phụ thuộc quản lý segment; các quy tắc `PCTUSED` cổ điển của **Manual Segment Space Management (MSSM)** không nên áp nguyên xi sang ASSM.

## 3. Row piece: một phần vật lý của một hàng SQL

Hãy phân biệt:

- **Logical row (hàng SQL):** một tập giá trị cột mà ứng dụng đọc bằng `SELECT`, ví dụ đơn hàng `ORDER_ID = 101`.
- **Row piece:** một đơn vị biểu diễn vật lý của toàn bộ hoặc một phần hàng SQL, nằm trong block của segment.
- **Row header:** metadata đứng trước phần giá trị cột của row piece; nó giúp Oracle diễn giải piece và tình trạng của hàng.
- **ROWID:** định danh/vị trí hàng được Oracle sử dụng để truy cập nhanh vào một hàng trong heap table. Với **extended ROWID** của heap table, thông tin mã hóa có data object number, relative file number, block number và row slot.

Một row piece có phần header chứa thông tin như **row flags**, trạng thái khóa, số cột trong piece và thông tin nối với piece khác khi cần; tiếp theo là các thông tin độ dài/giá trị cột. Chi tiết định dạng byte, cờ và cách mã hóa NULL phụ thuộc phiên bản và kiểu dữ liệu; không nên tự xây ứng dụng dựa vào những byte nội bộ này.

Ví dụ một hàng logic:

```text
Hàng SQL:
  (ID=101, CUSTOMER='An', DESCRIPTION='Giao trong ngày')

Khi vừa một block:
  Block 520, slot 7:
    [row-piece header | ID | CUSTOMER | DESCRIPTION]

Khi cần hai piece:
  Block 520, slot 7:
    [row-piece header | ID | CUSTOMER | phần DESCRIPTION]
                     |
                  liên kết
                     v
  Block 876, slot 2:
    [continuation header | phần DESCRIPTION còn lại]
```

Trong trường hợp thứ hai, **ứng dụng vẫn thấy một hàng**, không phải hai record để tự JOIN. Oracle theo các liên kết vật lý và ghép dữ liệu thành hàng logic trước khi trả kết quả.

### ROWID: ổn định không có nghĩa mọi byte nằm ở block cũ

Một `ROWID` có thể được dùng để tìm vị trí gốc của một hàng heap, nhưng **không nên dùng làm khóa nghiệp vụ**:

- Row migration giữ lại điểm dẫn ở block gốc để các tham chiếu qua ROWID hiện có tiếp tục hoạt động.
- Những thao tác khác, chẳng hạn chuyển/reorganize table segment, enable row movement và một số thao tác quản trị, có thể **thay đổi ROWID**.
- Với IOT, định danh kiểu `UROWID` có cách tổ chức khác; ví dụ trong bài không coi nó giống physical ROWID của heap table.

## 4. Row chaining: một hàng phải nằm ở nhiều row piece

### 4.1. Cơ chế

**Row chaining** xảy ra khi Oracle cần lưu một hàng bằng nhiều row piece liên kết với nhau. Trường hợp quen thuộc là ngay lúc **`INSERT`**, kích thước hàng vượt lượng chỗ mà một data block có thể chứa.

Ví dụ trên một tablespace có block 8 KB, hàng có ba cột `VARCHAR2`, mỗi cột chứa hơn 3 KB dữ liệu, có thể lớn hơn sức chứa của một block sau khi tính overhead.

```text
                      ROW CHAINING

Client SELECT một logical row có ID = 200
                       |
                       v
    BLOCK A: [head row piece: cột 1, phần cột 2]
                                        |
                                   next piece
                                        v
    BLOCK B: [continuation: phần cột 2, cột 3]

Oracle ghép các piece trước khi trả về một hàng SQL.
```

Oracle còn có thể tạo nhiều row piece khi một hàng có **rất nhiều cột** (ví dụ vượt giới hạn số cột lưu được trong một piece), kể cả trường hợp các piece nằm trong **cùng một block**. Do đó nói “row chaining *luôn* có nghĩa nhiều block” là quá tuyệt đối: vấn đề hiệu năng rõ nhất phát sinh khi phải theo liên kết và truy cập **thêm các block**.

### 4.2. Nguyên nhân thường gặp

1. **Hàng quá rộng:** tổng dữ liệu cột cộng overhead không thể chứa trong một block.
2. **Số cột vật lý trong một row piece bị giới hạn:** Oracle phải chia piece đối với hàng cực rộng về số cột.
3. **Dữ liệu tăng trong một cấu trúc đã phải chain:** số piece hoặc cách chúng phân bố có thể thay đổi khi hàng được cập nhật.

Một giá trị **CLOB/BLOB lớn** không đồng nghĩa chắc chắn bảng bị chained row: dữ liệu LOB có cơ chế lưu trong/ngoài dòng và LOB segment riêng tùy cấu hình, nên phải phân biệt **row piece của heap table** với **LOB storage**. Tương tự, nén dữ liệu và kiểu bảng ảnh hưởng đến kích thước hàng thực tế.

### 4.3. Hệ quả và hướng xử lý

Nếu phải đọc nhiều block để dựng một logical row, Oracle có thể cần thêm logical I/O, physical I/O và công việc CPU. Tác động thực tế phụ thuộc access path, cache, độ dài dữ liệu, mức độ truy cập và bao nhiêu piece nằm ngoài block đầu.

Với hàng **vốn lớn hơn một block**, tăng `PCTFREE` không làm hàng “vừa vào block”; cần đánh giá mô hình dữ liệu, khả năng chia cột ít truy cập sang bảng phụ, chọn kiểu dữ liệu/LOB phù hợp hoặc chiến lược lưu trữ khác. Tăng database block size cũng **không phải** thay đổi cấu hình đơn giản hoặc bảo đảm phù hợp: đây là quyết định kiến trúc và giới hạn nền tảng, cần đánh giá riêng.

## 5. Row migration: hàng lớn lên sau một cập nhật

### 5.1. Cơ chế

Giả sử khi `INSERT`, hàng vừa gọn trong Block A; sau nhiều hàng khác được chèn vào, block gần đầy. Một câu lệnh `UPDATE` làm giá trị `NOTE` của hàng tăng từ 50 byte lên 3.000 byte. Nếu block gốc **không còn đủ vùng trống**, Oracle có thể chuyển hàng sang một block khác.

```text
                    TRƯỚC UPDATE

   BLOCK A
   +---------------------------------------+
   | row directory                         |
   | slot 5 -> [ID=101 | NOTE='short']      |
   | nhiều hàng khác, ít free space        |
   +---------------------------------------+

                    SAU UPDATE

   BLOCK A (vị trí gốc vẫn nhận diện hàng)
   +---------------------------------------+
   | slot 5 -> [forwarding pointer] --------+---+
   +---------------------------------------+   |
                                               v
   BLOCK B                                +---------------------+
                                          | [ID=101 | NOTE dài]|
                                          +---------------------+

ROWID logic của hàng heap vẫn định vị qua slot gốc.
```

Thông tin ở block cũ giữ lại một **forwarding address/pointer** để Oracle tìm tới hàng được chuyển. Vì thế **ROWID của hàng heap được migration không đổi chỉ vì migration**, dù phần dữ liệu chính đã nằm ở block khác.

### 5.2. Điều kiện thuận lợi dẫn tới migration

- Bảng có nhiều cột kiểu biến độ dài như `VARCHAR2`, ban đầu ngắn, sau đó thường xuyên tăng.
- Block đã có mật độ chèn cao; `PCTFREE` nhỏ hơn nhu cầu tăng kích thước hàng thực tế.
- Bản ghi bị cập nhật nhiều lần, làm tổng kích thước hàng tăng; không còn chỗ cho row piece hiện tại.

**Không phải mọi `UPDATE` gây migration:** cập nhật giá trị mà không tăng kích thước hoặc tăng nhưng block vẫn còn chỗ có thể giữ hàng tại chỗ. Ngược lại, bảng có các giá trị kiểu cố định cũng có thể chịu overhead/thay đổi khác; phải quan sát môi trường thay vì quyết đoán chỉ dựa vào kiểu cột.

### 5.3. Tại sao migration có thể làm truy vấn chậm?

Nếu Oracle tra hàng qua **index ROWID**, nó thường tìm tới địa chỉ gốc trước. Với migrated row, cần lần theo pointer đến block hiện chứa dữ liệu:

```text
Index lookup
    |
    v
ROWID -> block gốc / row slot
                    |
                    +----> block đích chứa hàng thực tế
```

Khả năng phải truy cập block bổ sung làm tăng thao tác đọc logical block và đôi khi physical I/O. Nếu block đã nằm trong buffer cache, truy cập thêm không nhất thiết đồng nghĩa một lần đọc đĩa, nhưng vẫn là công việc Oracle phải làm.

Một **full table scan** có mô hình chi phí và cách xử lý khác index lookup; không thể nhìn vào một migrated row rồi khẳng định mọi truy vấn trên bảng đều chậm cùng mức độ.

### 5.4. Chuyển vị trí không phải xóa + tạo hàng mới về mặt SQL

Row migration là hoạt động lưu trữ **nội bộ** của Oracle khi thực thi cập nhật; ứng dụng vẫn tương tác với một logical row. Các ràng buộc, transaction, khóa và tính nhất quán SQL vẫn áp dụng. Việc giữ ROWID giúp tránh làm hỏng tham chiếu của index đã giữ ROWID gốc trong quá trình migration thông thường.

Không nên “sửa” migrated row bằng cách cập nhật ROWID thủ công: ROWID không phải cột có thể tự gán vị trí lưu trữ theo ý muốn.

## 6. Bảng so sánh chaining và migration

| Câu hỏi | **Row chaining** | **Row migration** |
| --- | --- | --- |
| Tình huống điển hình | Hàng quá lớn cho một data block khi tạo/lưu, phải chia thành nhiều piece | Hàng từng vừa một block nhưng tăng kích thước do `UPDATE`, block gốc thiếu chỗ |
| Dạng vật lý | Hai hoặc nhiều **row piece** liên kết | Block gốc giữ thông tin **forwarding** tới hàng đã chuyển sang block mới |
| Một logical row có còn là một hàng SQL? | Có | Có |
| Có thể xuất hiện khi `INSERT`? | Có, đặc biệt với hàng rất rộng | Không theo cơ chế điển hình; migration xuất phát từ việc hàng đã lưu tăng kích thước |
| Có thể phát sinh bởi `UPDATE`? | Có thể thay đổi/làm phát sinh nhu cầu chia piece | Có, đây là trường hợp kinh điển |
| `ROWID` của hàng heap | Dẫn vào piece/đầu chuỗi theo cơ chế Oracle | Giữ vị trí gốc, dù dữ liệu đã chuyển |
| `PCTFREE` cao hơn có thể giúp? | Không xử lý được hàng vốn lớn hơn khả năng một block | Có thể giảm nguy cơ khi thiết kế đúng mức tăng trưởng |
| Hướng khắc phục chính | Giảm độ rộng hàng, cân nhắc cách tổ chức dữ liệu và kiểu lưu trữ | Chừa free space hợp lý; giảm cập nhật làm hàng lớn lên; tổ chức lại bảng khi có bằng chứng |
| Khả năng đo bằng `LIST CHAINED ROWS` | Có thể được ghi nhận | Cũng có thể được ghi nhận |

**Điểm mấu chốt:** Oracle và nhiều công cụ thống kê thường gom **chained/migrated rows** vào cùng nhóm báo cáo. Chỉ nhìn một tổng số **không đủ** để biết tất cả hàng là chaining hay migration; cần kết hợp lịch sử workload, độ rộng hàng, cấu trúc bảng và bằng chứng khác.

## 7. Quan sát đúng lớp lưu trữ bằng SQL

### 7.1. Xem tablespace, row count và cấu hình của bảng

Khi đăng nhập bằng chủ sở hữu bảng heap:

```sql
SELECT table_name,
       tablespace_name,
       pct_free,
       ini_trans,
       num_rows,
       avg_row_len,
       chain_cnt,
       last_analyzed
FROM user_tables
WHERE table_name = 'ROW_STORAGE_LAB';
```

Ý nghĩa:

- `PCT_FREE` cho biết cấu hình khoảng trống dành cho cập nhật hàng.
- `NUM_ROWS` và `AVG_ROW_LEN` là **thống kê** có thể đã cũ hoặc chưa được thu thập; không phải phép đếm/đo trực tiếp tại thời điểm `SELECT`.
- `CHAIN_CNT` là thông tin về chained/migrated rows **do cơ chế phân tích phù hợp thu thập**, có thể `NULL` hoặc cũ. **`DBMS_STATS` không nên bị coi là bảo đảm tự cập nhật `CHAIN_CNT`**.
- `LAST_ANALYZED` phản ánh thời điểm thông tin thống kê được cập nhật; không xác nhận rằng `CHAIN_CNT` đại diện cho mọi giao dịch mới nhất.

Đối với ứng dụng, nên dùng `DBMS_STATS` theo quy trình quản trị để duy trì optimizer statistics; **không dùng `ANALYZE TABLE ... COMPUTE STATISTICS` một cách tùy tiện trong production** chỉ nhằm tìm chained rows.

### 7.2. Xem vị trí logic của hàng

Ví dụ truy vấn một hàng bằng physical `ROWID` trong heap table:

```sql
SELECT id, ROWID AS rid, LENGTHB(payload) AS payload_bytes
FROM row_storage_lab
WHERE id = 1;
```

Oracle có thể giúp bóc tách các thành phần của extended ROWID qua package `DBMS_ROWID`, nếu tài khoản có quyền thực thi:

```sql
SELECT id,
       DBMS_ROWID.ROWID_RELATIVE_FNO(ROWID) AS relative_file_no,
       DBMS_ROWID.ROWID_BLOCK_NUMBER(ROWID) AS rowid_block_no,
       DBMS_ROWID.ROWID_ROW_NUMBER(ROWID)   AS row_slot
FROM row_storage_lab
WHERE id = 1;
```

**Cảnh báo diễn giải:** việc `ROWID` và `ROWID_BLOCK_NUMBER` **không đổi sau một `UPDATE`** là *phù hợp* với cơ chế migration, nhưng **không tự chứng minh rằng migration đã xảy ra**. Hàng không migration cũng giữ ROWID. Để xác nhận cần thêm chẩn đoán về chained/migrated rows.

### 7.3. Dùng `ANALYZE ... LIST CHAINED ROWS` để phát hiện

Oracle có câu lệnh liệt kê các hàng bị chaining/migration vào một bảng hỗ trợ. Ví dụ dưới đây chạy trong **schema thực hành** với table heap tự tạo; tài khoản cần quyền tạo bảng và phân tích đối tượng của mình.

Tạo bảng nhận kết quả, một lần trong schema thực hành:

```sql
CREATE TABLE chained_rows (
    owner_name        VARCHAR2(128),
    table_name        VARCHAR2(128),
    cluster_name      VARCHAR2(128),
    partition_name    VARCHAR2(128),
    subpartition_name VARCHAR2(128),
    head_rowid        ROWID,
    analyze_timestamp DATE
);
```

Đây là cấu trúc tương thích về mục đích với bảng mà script Oracle `utlchain.sql` thường tạo. Nếu môi trường đã có `CHAINED_ROWS` đúng cấu trúc, **không tạo trùng**; nếu dùng IOT hoặc đối tượng đặc thù, dùng script/kiểu dữ liệu phù hợp release theo tài liệu Oracle.

Chạy phân tích liệt kê:

```sql
TRUNCATE TABLE chained_rows;

ANALYZE TABLE row_storage_lab
    LIST CHAINED ROWS INTO chained_rows;

SELECT owner_name, table_name, head_rowid, analyze_timestamp
FROM chained_rows
WHERE owner_name = USER
  AND table_name = 'ROW_STORAGE_LAB'
ORDER BY analyze_timestamp, head_rowid;
```

Để đọc đúng hàng thuộc danh sách, có thể join bằng ROWID khi bảng kết quả chứa head ROWID hợp lệ:

```sql
SELECT t.id, LENGTHB(t.payload) AS payload_bytes, c.head_rowid
FROM row_storage_lab t
JOIN chained_rows c
  ON t.ROWID = c.head_rowid
WHERE c.owner_name = USER
  AND c.table_name = 'ROW_STORAGE_LAB';
```

`LIST CHAINED ROWS` hữu ích khi cần biết **những hàng cụ thể** nào có vấn đề; nó không tự phân loại nguyên nhân thành một cột “MIGRATION” hay “CHAINING”. Trên bảng lớn, việc quét để liệt kê có chi phí I/O và yêu cầu quyền, nên lên lịch phù hợp. Đừng `TRUNCATE` bảng `CHAINED_ROWS` dùng chung của nhóm quản trị.

### 7.4. Chỉ số runtime để bổ sung bằng chứng

Một số thống kê Oracle có tên gần với **`table fetch continued row`**. Với quyền truy cập dynamic performance views, quản trị viên có thể theo dõi thay đổi bộ đếm trong một phiên:

```sql
SELECT n.name, s.value
FROM v$mystat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE n.name = 'table fetch continued row';
```

Bộ đếm có thể phản ánh những lần Oracle phải đi tiếp để lấy dữ liệu từ chained/migrated rows, nhưng **không phải số hàng lỗi duy nhất** của một bảng, không phân biệt đầy đủ hai nguyên nhân và còn phụ thuộc loại truy cập. Đo trước/sau một workload tương đương và kết hợp execution plan/I/O mới có cơ sở kết luận ảnh hưởng hiệu năng. Quyền xem `V$...` khác nhau theo vai trò tài khoản.

## 8. Thực hành có thể tự tái tạo

Các lệnh dưới đây dành cho **một schema lab riêng**, không chạy trên bảng nghiệp vụ. Chúng minh họa cách một hàng phát triển và cách dùng cơ chế `LIST CHAINED ROWS`. Kết quả cụ thể phụ thuộc **block size, độ đầy block, segment space management, phiên bản và cách Oracle cấp phát**.

### 8.1. Thử tạo row migration

Tạo bảng có cột thay đổi chiều dài và cố ý đặt `PCTFREE 0` để việc tăng kích thước hàng sau này dễ gặp thiếu không gian:

```sql
CREATE TABLE row_storage_lab (
    id      NUMBER NOT NULL,
    payload VARCHAR2(4000 BYTE),
    CONSTRAINT pk_row_storage_lab PRIMARY KEY (id)
) PCTFREE 0;
```

Chèn nhiều hàng nhỏ, sau đó tăng kích thước một hàng:

```sql
BEGIN
    FOR i IN 1..500 LOOP
        INSERT INTO row_storage_lab (id, payload)
        VALUES (i, RPAD('a', 120, 'a'));
    END LOOP;
    COMMIT;
END;
/

-- Ghi lại ROWID của ID = 1 trước khi UPDATE.
SELECT id, ROWID AS rid, LENGTHB(payload) AS bytes_before
FROM row_storage_lab
WHERE id = 1;

-- Làm hàng tăng kích thước khi các block đã có nhiều dữ liệu.
UPDATE row_storage_lab
SET payload = RPAD('b', 3900, 'b')
WHERE id = 1;
COMMIT;

-- Đọc lại ROWID và độ dài.
SELECT id, ROWID AS rid, LENGTHB(payload) AS bytes_after
FROM row_storage_lab
WHERE id = 1;
```

**Kỳ vọng chắc chắn:** độ dài `PAYLOAD` của ID 1 tăng lên; ứng dụng vẫn truy xuất bằng `ID = 1`. **Điều không được suy luận chỉ từ ROWID:** dù giá trị ROWID vẫn giữ nguyên, cần `LIST CHAINED ROWS` để biết bản cài cụ thể có thực sự chuyển hàng hay không. Oracle không hứa một lượng insert/update bất kỳ sẽ luôn tạo migration trong mọi cấu hình.

Nếu đã tạo bảng `CHAINED_ROWS` theo mục 7.3, chạy:

```sql
TRUNCATE TABLE chained_rows;

ANALYZE TABLE row_storage_lab
    LIST CHAINED ROWS INTO chained_rows;

SELECT t.id, LENGTHB(t.payload) AS payload_bytes
FROM row_storage_lab t
JOIN chained_rows c
  ON c.head_rowid = t.ROWID
WHERE c.owner_name = USER
  AND c.table_name = 'ROW_STORAGE_LAB';
```

Nếu ID 1 xuất hiện, điều đó cho thấy Oracle ghi nhận hàng này trong danh sách cần đi tiếp qua row piece/forwarding tại thời điểm phân tích. Với **ngữ cảnh hàng ban đầu nhỏ, UPDATE tăng lên nhiều và PCTFREE 0**, migration là lời giải thích phù hợp; để khẳng định layout byte chính xác cần chẩn đoán sâu hơn.

### 8.2. Thử tạo row chaining

Với **tablespace 8 KB** thông dụng, thử một hàng rộng có tổng giá trị lớn hơn một block:

```sql
CREATE TABLE row_chaining_lab (
    id NUMBER PRIMARY KEY,
    part_a VARCHAR2(4000 BYTE),
    part_b VARCHAR2(4000 BYTE),
    part_c VARCHAR2(4000 BYTE)
);

INSERT INTO row_chaining_lab (id, part_a, part_b, part_c)
VALUES (
    1,
    RPAD('A', 3500, 'A'),
    RPAD('B', 3500, 'B'),
    RPAD('C', 3500, 'C')
);
COMMIT;

SELECT id,
       LENGTHB(part_a) + LENGTHB(part_b) + LENGTHB(part_c) AS total_value_bytes
FROM row_chaining_lab;
```

Tổng giá trị cột ở ví dụ là **10.500 byte**, chưa tính metadata của row piece. Trên block 8 KB, một row piece không thể chứa toàn bộ hàng này; Oracle phải sử dụng nhiều piece. Trên tablespace có block lớn hơn, ví dụ này **có thể không chain**, vì vậy cần biết kích thước block thực tế.

Tiếp tục quan sát:

```sql
TRUNCATE TABLE chained_rows;

ANALYZE TABLE row_chaining_lab
    LIST CHAINED ROWS INTO chained_rows;

SELECT table_name, head_rowid
FROM chained_rows
WHERE owner_name = USER
  AND table_name = 'ROW_CHAINING_LAB';
```

Điểm khác thí nghiệm migration: hàng **đã rộng ngay lúc chèn**. Đây là ví dụ về nguyên nhân chaining mà tăng `PCTFREE` không giải quyết được.

### 8.3. Dọn môi trường lab

Chỉ thực hiện trên những đối tượng vừa tạo trong schema thực hành:

```sql
DROP TABLE row_storage_lab PURGE;
DROP TABLE row_chaining_lab PURGE;
-- Chỉ DROP CHAINED_ROWS nếu chính bạn tạo cho lab này
-- và không có công việc phân tích nào khác sử dụng nó.
```

`PURGE` bỏ qua recycle bin của bảng bị xóa; trong môi trường cần giữ dữ liệu hoặc khôi phục, không dùng tùy tiện. Không chạy lệnh `DROP` trên các bảng do người khác quản lý.

## 9. Giảm tác động và chọn giải pháp theo nguyên nhân

### Với row migration

1. **Ước lượng mức tăng thực tế của hàng.** Cột `VARCHAR2` được chèn ngắn rồi thường xuyên kéo dài là tín hiệu cần xem.
2. **Chọn `PCTFREE` phù hợp ngay từ thiết kế/cấp phát block.** Tăng `PCTFREE` giúp còn chỗ cho `UPDATE`, đổi lại **mật độ hàng trên mỗi block thấp hơn**; quá cao cũng có thể tăng I/O vì bảng chiếm nhiều block.
3. **Xem xét cách cập nhật.** Hạn chế pattern chèn placeholder ngắn rồi điền hàng nghìn byte vào cùng hàng nếu nghiệp vụ có thiết kế dữ liệu khác hợp lý.
4. **Đánh giá tổ chức lại segment khi cần.** Các thao tác như table move/redefinition hoặc giải pháp bảo trì thích hợp có thể làm các hàng được lưu lại theo layout mới. Chúng có thể thay đổi ROWID, ảnh hưởng index, lock, storage và khả năng sẵn sàng; phải chọn phương thức/tùy chọn theo release, kiểm thử và lên lịch chứ không áp dụng như câu lệnh “chữa tất cả”.
5. **Đo lại sau thay đổi** bằng cùng workload/điều kiện và công cụ chẩn đoán. Giảm số hàng migration không bảo đảm mọi truy vấn đều tăng tốc.

Đổi thuộc tính bảng bằng `ALTER TABLE ... PCTFREE ...` thường ảnh hưởng cách Oracle quản lý **những lần chèn/cấp phát tiếp theo**; nó **không tự di dời hay “un-migrate” tất cả các hàng đã tồn tại**.

### Với row chaining

1. **Xác nhận hàng có vượt sức chứa của block không.** Nếu một hàng lớn hơn block theo bản chất, tăng `PCTFREE` chỉ giảm chỗ dùng được cho chèn hàng mới.
2. **Xem lại mức độ rộng của một hàng:** cột nào luôn đọc cùng nhau, cột nào ít truy cập, có thể đặt phần dữ liệu lớn ở cấu trúc riêng mà không làm phức tạp nghiệp vụ quá mức?
3. **Chọn cách lưu dữ liệu phù hợp:** với tài liệu lớn, hình ảnh hoặc chuỗi dài, đánh giá LOB và khả năng inline/out-of-line theo đúng yêu cầu; đây là quyết định kiểu dữ liệu và truy cập, không chỉ thay tên cột.
4. **Không tự tăng block size chỉ vì thống kê có chained rows.** Hãy tính tới lợi ích, khả năng hỗ trợ nondefault block size, buffer cache, quản trị và yêu cầu di chuyển dữ liệu.
5. **Phân biệt chaining vì độ rộng với migration vì cập nhật** trước khi chọn giải pháp: một thao tác reorganize có thể làm một số migrated rows được bố trí lại, nhưng không thể nhét hàng lớn hơn block vào một block nhỏ.

### Cân nhắc khi tối ưu

| Lựa chọn | Có thể giúp | Đánh đổi / giới hạn |
| --- | --- | --- |
| Tăng `PCTFREE` hợp lý | Giảm nguy cơ migration do hàng tăng sau insert | Giảm mật độ dữ liệu; không khắc phục row vượt kích thước block |
| Giảm kích thước hàng / thiết kế lại cột lớn | Giảm chained row và lượng dữ liệu mỗi truy vấn phải đọc | Thay đổi schema, code và chi phí join |
| Tổ chức lại table segment có kế hoạch | Bố trí lại hàng, có thể giảm migration hiện tại | Tốn I/O/thời gian/không gian; có thể đổi ROWID và liên quan index |
| Dùng LOB theo nhu cầu | Đưa giá trị lớn sang cách lưu phù hợp, tránh kéo các giá trị khổng lồ vào heap row | LOB vẫn có chi phí truy xuất, metadata và lưu trữ riêng |
| Đổi block size/tablespace | Có thể phù hợp workload có row rộng trong một số giới hạn | Quyết định kiến trúc phức tạp, không phải tuning mặc định |

## 10. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “Block 8 KB chứa được đúng 8 KB dữ liệu của một hàng.” | Block còn header, directory, metadata giao dịch và overhead của row piece. |
| “Block header là row header.” | **Block header** quản lý block; **row header** mô tả row piece bên trong block. |
| “Một row directory entry luôn trỏ đến cả hàng.” | Có thể trỏ đến một row piece hoặc forwarding information; hàng có thể nằm trên nhiều piece/block. |
| “Row chaining chỉ do update.” | Chaining điển hình ngay từ insert khi hàng không vừa block; còn migration điển hình khi update làm hàng lớn lên. |
| “Row chaining lúc nào cũng cần hai block khác nhau.” | Một số hàng nhiều cột có thể chia piece trong cùng block; cần xem layout thực tế. |
| “Migrated row đổi ROWID thành địa chỉ block mới.” | Oracle giữ ROWID gốc qua forwarding pointer đối với migration thông thường của heap row. |
| “Nếu ROWID trước/sau update bằng nhau tức không có migration.” | ROWID ổn định trong cả trường hợp không migration và migration, nên không phân biệt được hai tình huống chỉ bằng phép so sánh đó. |
| “`CHAIN_CNT` khác `NULL` là số hàng hiện tại tuyệt đối.” | Đây là thông tin phụ thuộc việc phân tích và thời điểm thu thập; có thể cũ. |
| “Tăng `PCTFREE` sẽ sửa mọi chaining.” | Không thể làm hàng vượt sức chứa block tự vừa trong một block. |
| “Cứ reorganize bảng là tuning tốt.” | Cần bằng chứng I/O và mục tiêu rõ ràng; table move/redefinition có chi phí và rủi ro vận hành. |
| “Bảng có CLOB lớn thì luôn có chained row trong heap table.” | Dữ liệu LOB có cơ chế lưu riêng; xem inline/out-of-line và cấu trúc thực tế. |

## 11. Câu hỏi ôn tập và tình huống thực tế

**Câu 1.** Một hàng được insert với `NOTE = 'OK'` vào block gần đầy, sau đó update `NOTE` thành 3.000 ký tự. Truy vấn qua index đôi khi phải đọc thêm block. Khả năng gì cần kiểm tra?

**Gợi ý:** row migration vì hàng tăng sau update và block gốc thiếu chỗ. Kiểm tra bằng `LIST CHAINED ROWS`, đọc lịch sử cập nhật và thống kê runtime. Đừng coi ROWID không đổi là bằng chứng bác bỏ migration.

**Câu 2.** Một hàng gồm nhiều cột `VARCHAR2` với tổng dữ liệu 11 KB trên tablespace 8 KB ngay lúc insert. Tăng `PCTFREE` từ 10 lên 30 có làm hết vấn đề?

**Gợi ý:** không. Hàng vượt khả năng chứa của một block; Oracle phải dùng nhiều row piece. Tăng `PCTFREE` không tạo thêm byte trong block.

**Câu 3.** Vì sao một query `SELECT ... WHERE ID = :id` qua index có thể nhạy với migration hơn một trường hợp khác, và physical I/O có luôn tăng không?

**Gợi ý:** index trỏ tới ROWID gốc, phải theo forwarding pointer để tìm dữ liệu; truy cập thêm block có thể là logical I/O, physical I/O chỉ khi cần đọc dữ liệu chưa có trong cache.

**Câu 4.** Hệ thống ghi `CHAIN_CNT = 0` nhưng ứng dụng có nhiều `UPDATE` làm hàng lớn lên. Có thể kết luận chắc chắn không có migrated row?

**Gợi ý:** không. `CHAIN_CNT` phụ thuộc phân tích và thời điểm thống kê. Hãy xác minh lại bằng công cụ thích hợp và so với workload.

**Câu 5.** Một bảng có hàng rất rộng vì chứa nhiều trường hiếm khi đọc. Bạn sẽ tối ưu bằng cách nào trước?

**Gợi ý:** xác định mẫu truy cập, độ rộng hàng thực, số row piece và nguyên nhân. Nếu chaining là hệ quả tất yếu của mô hình dữ liệu, cân nhắc thiết kế tách phần ít truy cập hoặc cách lưu phù hợp. Nếu vấn đề là migration, cân nhắc `PCTFREE`, kiểu cập nhật và tổ chức lại có kế hoạch.

## Tổng kết

**Block header** giữ metadata cấp block, trong đó có thông tin giao dịch/ITL; **row directory** chỉ tới các **row piece** vật lý; **row piece** là cách Oracle biểu diễn toàn bộ hoặc một phần của **một hàng logic**. **Row chaining** liên kết nhiều piece vì hàng không thể hoặc không được lưu trong một piece; **row migration** phát sinh điển hình khi cập nhật làm hàng tăng đến mức không còn chỗ ở block gốc, khiến Oracle chuyển dữ liệu và giữ forwarding pointer để duy trì ROWID.

Hiểu sự khác biệt này cho phép chọn đúng phép đo và cách khắc phục: **chaining** thường cần xem lại độ rộng hàng và tổ chức dữ liệu, còn **migration** thường cần xem cách hàng tăng kích thước và chính sách không gian trống. Trong mọi trường hợp, kết luận hiệu năng phải dựa trên workload, trạng thái cache và bằng chứng thực tế.

**Tài liệu Oracle nên đọc tiếp:**

- [Oracle Database Concepts 19c — Physical Storage Structures và Logical Storage Structures](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/index.html): giải thích data block format, row piece, chaining/migration và quan hệ với segment.
- [Oracle Database SQL Language Reference — ANALYZE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ANALYZE.html): cú pháp `LIST CHAINED ROWS` và lưu ý về mục đích sử dụng `ANALYZE`.
- [Oracle Database Reference — USER_TABLES / ALL_TABLES / DBA_TABLES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_TABLES.html): các trường metadata như `PCT_FREE`, `AVG_ROW_LEN`, `CHAIN_CNT` và `LAST_ANALYZED`.

Khi thực hành trên release khác 19c, tra lại tài liệu của chính release đó vì cú pháp tùy chọn, khả năng quan sát và đặc điểm lưu trữ có thể khác.
