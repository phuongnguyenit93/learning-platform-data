# Giải phóng không gian bằng shrink, move và tổ chức lại segment

Trong Oracle Database, **xóa hàng không đồng nghĩa giải phóng ngay dung lượng đã cấp cho bảng**. Một bảng có thể giảm từ hàng triệu hàng xuống vài nghìn hàng nhưng vẫn giữ nhiều block và extent để tái sử dụng. Nếu bảng thường xuyên được quét toàn bộ, phần block nằm dưới high-water mark (HWM) có thể tiếp tục ảnh hưởng đến công việc đọc dữ liệu. Nếu tablespace thiếu dung lượng, DBA có thể muốn thu hồi extent không còn phục vụ dữ liệu hiện tại.

Oracle cung cấp **segment shrink**, **table move**, **index coalesce/rebuild**, và thao tác riêng cho partition hoặc LOB. Mỗi cách có điều kiện áp dụng, nhu cầu tài nguyên và tác động khác nhau đến ROWID, index, giao dịch và tính sẵn sàng. Bài học này giải thích cách lựa chọn và thực hành trên một schema Oracle riêng.

> Trước khi tổ chức lại segment, hãy xác định **không gian đang trống ở cấp nào** và muốn thu hồi về **segment, tablespace hay datafile**. Không nên chạy SHRINK hoặc MOVE chỉ vì đã xóa nhiều hàng.

## 1. Hiểu không gian trong Oracle

### 1.1. Block, extent, segment, tablespace và datafile

~~~text
Oracle Database
  |
  +-- Tablespace APP_DATA
       |
       +-- Datafile 01, Datafile 02...
       |
       +-- TABLE segment DON_HANG
       |     +-- Extent A: nhiều data block
       |     +-- Extent B: nhiều data block
       |     +-- Extent C: nhiều data block
       |
       +-- INDEX segment IDX_DON_HANG_NGAY
       |
       +-- LOB segment (nếu có dữ liệu LOB lưu riêng)
~~~

| Đơn vị | Ý nghĩa | Liên hệ với thu hồi dung lượng |
| --- | --- | --- |
| **Data block** | Đơn vị lưu trữ và truy cập dữ liệu của Oracle | Xóa hàng có thể để lại chỗ trống bên trong block |
| **Extent** | Nhóm block được cấp cho một segment | Extent vẫn có thể thuộc segment sau khi nhiều hàng bị xóa |
| **Segment** | Tập extent dành cho table, index, LOB hoặc partition | SHRINK và MOVE tổ chức lại cách segment sử dụng không gian |
| **Tablespace** | Không gian lưu trữ logic chứa các segment | Extent được trả lại có thể được cấp cho đối tượng khác |
| **Datafile** | Tệp vật lý chứa dữ liệu của tablespace | Trả extent về tablespace không tự làm tệp trên đĩa nhỏ đi |

Một bảng có thể liên quan đến **nhiều segment khác nhau**: table segment, các index, LOB và những segment của partition. Giảm kích thước table segment không có nghĩa mọi segment phụ thuộc cũng đã được thu nhỏ.

### 1.2. High-water mark (HWM)

High-water mark đánh dấu vùng block mà Oracle xem là đã từng được sử dụng ở mức segment. Đối với heap table, HWM có vai trò trong những kiểu truy cập như full table scan.

~~~text
Trước khi xóa nhiều hàng:
| hàng | hàng | hàng | hàng | hàng | trống |
                                  ^ HWM

Sau DELETE:
| trống | trống | hàng | trống | hàng | trống |
                                   ^ HWM có thể vẫn giữ nguyên

Sau khi gom hàng và hạ HWM (minh họa):
| hàng | hàng | trống | trống | trống | trống |
              ^ HWM mới
~~~

**DELETE** đánh dấu các hàng bị xóa, tạo không gian trong những block để tái sử dụng khi chèn dữ liệu mới. Nhưng DELETE thông thường **không hạ HWM hoặc trả những extent đã cấp phát về tablespace**. Vì vậy, số hàng có thể giảm mạnh trong khi dung lượng segment gần như không đổi.

Khoảng trống không phải lúc nào cũng lãng phí. Nếu ứng dụng xóa và chèn lại lượng dữ liệu tương đương mỗi ngày, giữ các block để tái sử dụng có thể tốt hơn thu hồi rồi cấp phát lại.

### 1.3. Ba mục tiêu thu hồi khác nhau

1. **Không gian bên trong segment:** block còn chỗ trống để segment tái sử dụng. DELETE có thể tạo loại không gian này.
2. **Không gian tự do trong tablespace:** extent không còn thuộc segment, có thể phục vụ segment khác. Một số hoạt động SHRINK/MOVE giúp đạt mục tiêu này.
3. **Dung lượng vật lý của datafile:** kích thước tệp ở tầng lưu trữ. Thu hồi extent không tự động giảm datafile; DBA cần xem vị trí extents và khả năng resize riêng.

Ví dụ table segment từ 4 GB giảm xuống 1 GB có thể trả 3 GB về tablespace, trong khi datafile 10 GB vẫn có kích thước 10 GB.

## 2. Đo hiện trạng trước khi reorganize

Cần biết segment nào lớn, có bao nhiêu hàng, dữ liệu đã bị xóa đến mức nào, segment có khả năng tái sử dụng chỗ trống sớm không, và mục tiêu chính là tiết kiệm không gian hay cải thiện truy vấn.

### 2.1. Xem dung lượng segment đã cấp

~~~sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       ROUND(bytes / 1024 / 1024, 2) AS allocated_mb,
       blocks,
       extents
FROM user_segments
WHERE segment_name IN (
    'LAB_REORG',
    'PK_LAB_REORG',
    'IX_LAB_REORG_NHOM'
)
ORDER BY segment_type, segment_name;
~~~

**USER_SEGMENTS.BYTES** là số byte Oracle đã cấp cho segment, **không phải** tổng dung lượng dữ liệu nghiệp vụ còn sống, và cũng không phải số byte chắc chắn có thể thu hồi. Một phần dung lượng có thể dành cho block metadata, chỗ trống trong block, dự phòng ghi và chính sách cấp extent.

### 2.2. Xem thông tin bảng và index

~~~sql
SELECT table_name,
       tablespace_name,
       num_rows,
       blocks,
       avg_row_len,
       last_analyzed
FROM user_tables
WHERE table_name = 'LAB_REORG';

SELECT index_name,
       index_type,
       status,
       tablespace_name
FROM user_indexes
WHERE table_name = 'LAB_REORG';
~~~

Các giá trị **NUM_ROWS**, **BLOCKS** và **AVG_ROW_LEN** là thống kê phục vụ optimizer; chúng có thể cũ sau khi purge dữ liệu. **COUNT(*)** cho biết số hàng hiện tại nhưng trên bảng lớn vẫn có chi phí. Không dùng một phép tính NUM_ROWS × AVG_ROW_LEN để suy ra chính xác lượng extent có thể giải phóng.

Khi cần phân tích sâu phần không gian có thể thu hồi, DBA có thể dùng **Segment Advisor** hoặc khả năng thích hợp của **DBMS_SPACE**, tùy phiên bản, loại segment và quyền truy cập.

### 2.3. ASSM ảnh hưởng khả năng shrink

Segment shrink thông thường yêu cầu đối tượng phù hợp nằm trong tablespace sử dụng **Automatic Segment Space Management (ASSM)**. Có thể xem:

~~~sql
SELECT tablespace_name,
       contents,
       segment_space_management
FROM user_tablespaces
WHERE tablespace_name = 'APP_DATA';
~~~

APP_DATA là tên minh họa. Đối với tablespace dùng quản lý không gian thủ công (MSSM), hoặc kiểu đối tượng không hỗ trợ shrink, cần chọn phương án khác. Không nên chạy thử nhiều lần rồi mặc định lỗi là do thiếu quyền.

## 3. SHRINK SPACE: gom hàng và hạ HWM

**Segment shrink** là cách tổ chức lại không gian bên trong segment phù hợp. Oracle có thể di chuyển các hàng còn sống để gom chúng vào ít block hơn, hạ HWM và trả lại một số extent không còn cần thiết cho tablespace.

Đối với heap table thông thường, vì hàng có thể đổi vị trí vật lý, phải cho phép **row movement**:

~~~sql
ALTER TABLE lab_reorg ENABLE ROW MOVEMENT;
~~~

ROWID có thể thay đổi trong quá trình shrink. Ứng dụng Java không nên lưu ROWID như một khóa nghiệp vụ tồn tại lâu dài; hãy sử dụng primary key.

### 3.1. SHRINK SPACE COMPACT và SHRINK SPACE

~~~sql
-- Bảng phải đủ điều kiện shrink và nằm trong ASSM tablespace.
ALTER TABLE lab_reorg ENABLE ROW MOVEMENT;

-- Gom hàng, trì hoãn bước hạ HWM.
ALTER TABLE lab_reorg SHRINK SPACE COMPACT;

-- Hoàn tất hạ HWM và thu hồi extent đủ điều kiện.
ALTER TABLE lab_reorg SHRINK SPACE;
~~~

**SHRINK SPACE COMPACT** gom dữ liệu nhưng chưa thực hiện bước điều chỉnh HWM. **SHRINK SPACE** hoàn tất việc giảm HWM và thu hồi extent khi có thể; có thể thực hiện trực tiếp mà không nhất thiết chạy COMPACT trước.

Tách hai giai đoạn giúp bố trí phần di chuyển hàng và phần chỉnh HWM vào những thời điểm khác nhau. Giai đoạn gom dữ liệu có thể cho phép DML theo cơ chế Oracle hỗ trợ; việc hạ HWM có thể yêu cầu khóa ngắn. SHRINK vẫn tiêu thụ CPU, I/O, undo, redo và có thể chờ khóa; không đồng nghĩa vận hành hoàn toàn không gián đoạn.

### 3.2. SHRINK SPACE CASCADE

~~~sql
ALTER TABLE lab_reorg SHRINK SPACE CASCADE;
~~~

Tùy chọn **CASCADE** yêu cầu shrink những đối tượng phụ thuộc được loại đối tượng và phiên bản Oracle hỗ trợ, chẳng hạn một số index. Không mặc định CASCADE sẽ xử lý mọi LOB, domain index, partition hay đối tượng đặc biệt.

Sau khi kết thúc shrink, nếu không còn cần row movement cho chức năng khác:

~~~sql
ALTER TABLE lab_reorg DISABLE ROW MOVEMENT;
~~~

Không tắt row movement khi bảng có yêu cầu khác cần đến nó, ví dụ một số kịch bản cập nhật khóa phân vùng.

### 3.3. Điều kiện cần xem xét

- Bảng có thuộc loại heap table hoặc segment hỗ trợ shrink không?
- Tablespace có ASSM không?
- Có ứng dụng, trigger hoặc xử lý ngoài Oracle dựa vào ROWID cũ không?
- Có LOB, partition, materialized view hoặc kiểu index đặc biệt cần xử lý riêng không?
- Workload hiện tại có chịu được chi phí I/O, undo, redo và khóa khi chỉnh HWM không?
- Dữ liệu có sắp được thêm lại để tái sử dụng khoảng trống không?

**Không phải mọi bảng đều có thể dùng SHRINK SPACE.** Các loại segment chuyên biệt có thể có cú pháp, giới hạn hoặc phương án reorganize khác.

## 4. MOVE: tạo lại table segment

**ALTER TABLE ... MOVE** là thao tác di chuyển hoặc tái tổ chức table segment. Oracle tạo cấu trúc segment đích và chuyển các hàng còn sống sang đó; sau khi hoàn tất thành công, không gian của cấu trúc cũ được xử lý theo cơ chế Oracle.

~~~sql
-- Ví dụ với heap table phù hợp, thường cần cửa sổ bảo trì.
ALTER TABLE lab_reorg MOVE;
~~~

Có thể chỉ định tablespace đích nếu đã được chuẩn bị:

~~~sql
ALTER TABLE lab_reorg MOVE TABLESPACE APP_DATA_NEW;
~~~

APP_DATA_NEW là tên minh họa. Phải kiểm tra quyền, quota, dung lượng và chính sách lưu trữ của tablespace đích.

### 4.1. So sánh SHRINK và MOVE

| Tiêu chí | SHRINK SPACE | MOVE |
| --- | --- | --- |
| Cách làm | Gom hàng trong segment hiện tại và điều chỉnh HWM | Tạo segment mới, chép hàng còn sống |
| Điều kiện ASSM | Thông thường cần ASSM đối với shrink segment | Không đòi đúng điều kiện ASSM của shrink |
| ROWID | Có thể đổi do di chuyển hàng | Thường đổi do sang segment mới |
| Chuyển tablespace | Không phải mục tiêu chính | Có thể chuyển sang tablespace khác |
| Tài nguyên | Di chuyển/gom hàng trong segment, vẫn sinh I/O/undo/redo | Thường cần dung lượng đủ cho segment mới trong lúc move |
| Ảnh hưởng index | Tùy loại shrink và tùy chọn CASCADE | MOVE ngoại tuyến thông thường có thể làm index UNUSABLE nếu không dùng cơ chế duy trì |
| DML đồng thời | Có thể hỗ trợ DML trong một số pha; pha hạ HWM cần lock | MOVE ngoại tuyến có thể chặn DML; online phụ thuộc hỗ trợ |
| Mục tiêu | Thu hồi khoảng trống sau xóa | Reorganize hoặc chuyển vùng lưu trữ |

**MOVE có thể cần nhiều free space trước khi giải phóng dung lượng**: trong quá trình di chuyển, cả segment cũ và mới có thể chiếm không gian. Nếu tablespace gần đầy, MOVE có thể không đủ tài nguyên để hoàn tất.

### 4.2. Index sau MOVE

Index thường dùng vị trí hàng (ROWID) để tìm dữ liệu. Khi một heap table được move ngoại tuyến thông thường, các ROWID thay đổi, nên index liên quan có thể bị đánh dấu **UNUSABLE** nếu không có cơ chế duy trì index phù hợp.

Sau khi move, kiểm tra trạng thái:

~~~sql
SELECT index_name, index_type, status
FROM user_indexes
WHERE table_name = 'LAB_REORG'
ORDER BY index_name;
~~~

Với index thường ở trạng thái UNUSABLE, có thể xây lại theo kế hoạch:

~~~sql
ALTER INDEX pk_lab_reorg REBUILD;
ALTER INDEX ix_lab_reorg_nhom REBUILD;
~~~

Ở ví dụ này, tên index được tạo ở phần thực hành. Nếu index dùng tên khác thì lấy tên thực tế từ USER_INDEXES. Với partitioned table, trạng thái ở cấp index partition/subpartition cũng phải được đánh giá.

### 4.3. MOVE ONLINE

Một số phiên bản Oracle hỗ trợ move table theo chế độ online khi đối tượng đủ điều kiện:

~~~sql
-- Chỉ thực hiện khi phiên bản, edition và kiểu bảng hỗ trợ.
ALTER TABLE lab_reorg MOVE ONLINE;
~~~

MOVE ONLINE nhằm giảm gián đoạn DML và có cơ chế bảo trì index phù hợp, nhưng vẫn cần I/O, redo/undo, không gian cho segment mới và có thể có lock ở một số giai đoạn. Kiểu bảng có partition, LOB hoặc index đặc biệt có thể có giới hạn riêng. Không được suy ra online là không cần kế hoạch vận hành.

## 5. INDEX segment: COALESCE, SHRINK và REBUILD

Index là segment riêng. Xóa nhiều hàng trong bảng có thể để lại chỗ trống trong các block của B-tree index, nhưng không phải mọi index sau purge đều cần xây dựng lại.

### 5.1. COALESCE

~~~sql
ALTER INDEX ix_lab_reorg_nhom COALESCE;
~~~

COALESCE tổ chức lại khả năng sử dụng một số leaf block thích hợp của B-tree, giúp không gian nội bộ có thể được tái sử dụng. Nó **không bảo đảm giảm HWM hoặc trả extent về tablespace**.

### 5.2. SHRINK index

Với index thuộc loại hỗ trợ và trong môi trường phù hợp:

~~~sql
ALTER INDEX ix_lab_reorg_nhom SHRINK SPACE;
~~~

Cần xác nhận điều kiện ASSM và kiểu index. Không chạy lệnh này trên mọi bitmap, domain, partitioned hoặc index chuyên biệt mà chưa kiểm tra khả năng hỗ trợ.

### 5.3. REBUILD

~~~sql
ALTER INDEX ix_lab_reorg_nhom REBUILD;
~~~

REBUILD tái tạo cấu trúc index và có thể phù hợp khi index UNUSABLE sau MOVE, khi cần chuyển tablespace index hoặc khi có bằng chứng cần tổ chức lại. Nó tốn CPU, I/O, dung lượng xây dựng và thời gian.

| Hiện trạng | Hướng cân nhắc |
| --- | --- |
| Index UNUSABLE sau MOVE ngoại tuyến | REBUILD hoặc cơ chế khôi phục tương ứng |
| B-tree index còn dùng được nhưng nhiều khoảng trống | COALESCE hoặc SHRINK nếu có lợi và được hỗ trợ |
| Cần chuyển index sang tablespace khác | Biến thể REBUILD với vị trí đích |
| Index đang hoạt động tốt, sắp có nhiều INSERT | Có thể để nguyên và tái sử dụng block trống |

Không nên áp dụng một ngưỡng cố định như “xóa 20% hàng là phải rebuild mọi index”. Quyết định dựa trên workload, khả năng tái sử dụng và lợi ích đo được.

## 6. Partition, LOB và đối tượng đặc biệt

### 6.1. Partitioned table

Mỗi partition/subpartition có thể có segment riêng. Nếu chỉ purge một partition cũ, xử lý đúng partition thường ít tác động hơn reorganize toàn bảng.

Ví dụ minh họa:

~~~sql
-- Giả định bảng, partition và tablespace đích tồn tại.
ALTER TABLE don_hang_partitioned
    MOVE PARTITION p_2023 TABLESPACE APP_ARCHIVE;
~~~

Khi move partition cần xét **local index**, **global index**, cách duy trì index và các giới hạn cụ thể của phiên bản Oracle. Với một partition đã hết thời hạn lưu giữ, đôi khi TRUNCATE PARTITION hoặc DROP PARTITION thích hợp hơn nhưng chúng là thao tác loại bỏ dữ liệu theo chính sách, không đơn thuần là thu hồi chỗ trống.

### 6.2. CLOB, BLOB và LOB segment

Một bảng có CLOB/BLOB có thể chiếm phần lớn không gian ở LOB segment riêng chứ không ở table segment. Kiểm tra:

~~~sql
SELECT table_name,
       column_name,
       segment_name,
       index_name,
       tablespace_name
FROM user_lobs
WHERE table_name = 'TEN_BANG_CO_LOB';
~~~

Khả năng shrink/move của LOB phụ thuộc **BasicFile/SecureFile**, phiên bản Oracle, loại segment và thuộc tính lưu trữ. Một số phương án sử dụng biến thể MOVE LOB; các loại khác có thao tác thu hồi riêng. Không dùng tùy tiện lệnh dành cho heap table để tác động lên LOB segment.

### 6.3. IOT, cluster và cấu trúc khác

Index-organized table (IOT), cluster, materialized view hoặc domain index có bố cục và điều kiện bảo trì riêng. Trước khi chọn thao tác, phải xác định **kiểu đối tượng thực tế** và khả năng hỗ trợ của bản Oracle đang sử dụng.

### 6.4. TRUNCATE khác SHRINK/MOVE

Nếu toàn bộ dữ liệu của **bảng sandbox** không còn cần giữ, có thể dùng:

~~~sql
-- Chỉ chạy khi được phép loại bỏ toàn bộ dữ liệu thử nghiệm.
TRUNCATE TABLE lab_reorg DROP STORAGE;
~~~

TRUNCATE là DDL, có quy tắc implicit commit và không thể rollback như một DELETE chưa commit. Nó chịu giới hạn của khóa ngoại, partition và thuộc tính lưu trữ. **TRUNCATE toàn bảng không phù hợp khi cần giữ lại một số hàng**.

## 7. Thực hành trên schema Oracle riêng

Ví dụ tạo bảng, thêm dữ liệu, xóa 80% hàng rồi quan sát cấp phát trước và sau SHRINK hoặc MOVE. Chạy **chỉ trong schema thực hành** với quyền tạo/xóa bảng và index. Kết quả kích thước có thể khác nhau theo block size, extent allocation và cách Oracle bố trí dữ liệu.

### 7.1. Tạo bảng và index

~~~sql
CREATE TABLE lab_reorg (
    id       NUMBER(8) CONSTRAINT pk_lab_reorg PRIMARY KEY,
    nhom     NUMBER(3) NOT NULL,
    payload  VARCHAR2(500 CHAR)
);

CREATE INDEX ix_lab_reorg_nhom
    ON lab_reorg (nhom);
~~~

Ràng buộc PK_LAB_REORG thông thường tạo index hỗ trợ có tên tương ứng khi chưa có index phù hợp khác được sử dụng. Trước khi rebuild phải xác định tên thật trong USER_INDEXES.

### 7.2. Nạp dữ liệu có thể lặp lại

~~~sql
INSERT INTO lab_reorg (id, nhom, payload)
SELECT LEVEL,
       MOD(LEVEL, 10),
       RPAD('X', 400, 'X')
FROM dual
CONNECT BY LEVEL <= 20000;

COMMIT;

SELECT COUNT(*) AS so_hang
FROM lab_reorg;
~~~

Số hàng dự kiến là **20.000**. Payload dài 400 ký tự khiến segment dễ quan sát hơn so với chỉ lưu hai số nguyên. Ghi nhận baseline:

~~~sql
SELECT segment_name,
       segment_type,
       ROUND(bytes / 1024 / 1024, 2) AS allocated_mb,
       blocks,
       extents
FROM user_segments
WHERE segment_name IN (
    'LAB_REORG', 'PK_LAB_REORG', 'IX_LAB_REORG_NHOM'
)
ORDER BY segment_name;
~~~

### 7.3. Xóa 80% dữ liệu

~~~sql
DELETE FROM lab_reorg
WHERE id <= 16000;

COMMIT;

SELECT COUNT(*) AS so_hang_con_lai
FROM lab_reorg;
~~~

Số hàng còn lại là **4.000**, với ID từ 16001 đến 20000. Truy vấn lại USER_SEGMENTS: mặc dù số hàng đã giảm mạnh, segment thường chưa trả extent về tablespace chỉ nhờ DELETE.

### 7.4. Chạy SHRINK

Nếu heap table nằm trong ASSM tablespace và thỏa điều kiện:

~~~sql
ALTER TABLE lab_reorg ENABLE ROW MOVEMENT;
ALTER TABLE lab_reorg SHRINK SPACE COMPACT;
ALTER TABLE lab_reorg SHRINK SPACE;

SELECT COUNT(*) AS so_hang_sau_shrink
FROM lab_reorg;
~~~

Số hàng vẫn phải bằng **4.000**. Quan sát lại dung lượng LAB_REORG bằng USER_SEGMENTS và trạng thái index bằng USER_INDEXES. Dung lượng thu hồi cụ thể phụ thuộc khả năng gom hàng và cấp phát extent; không kỳ vọng chính xác 80%.

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE table_name = 'LAB_REORG'
ORDER BY index_name;
~~~

Có thể dùng CASCADE trong một thử nghiệm riêng nếu những segment phụ thuộc có hỗ trợ và thực sự cần thu hồi.

### 7.5. MOVE là phương án thực hành thay thế

**MOVE không phải bước bắt buộc sau SHRINK.** Để quan sát công bằng, dùng một bản sao sandbox có trạng thái sau DELETE nhưng trước SHRINK, rồi thực hiện:

~~~sql
ALTER TABLE lab_reorg MOVE;

SELECT index_name, status
FROM user_indexes
WHERE table_name = 'LAB_REORG'
ORDER BY index_name;
~~~

Nếu index bị đánh dấu UNUSABLE, rebuild:

~~~sql
ALTER INDEX pk_lab_reorg REBUILD;
ALTER INDEX ix_lab_reorg_nhom REBUILD;

SELECT COUNT(*) AS so_hang_sau_move
FROM lab_reorg;
~~~

Số hàng vẫn phải là **4.000**. Kiểm tra trạng thái index, các truy vấn quan trọng và dung lượng sau thao tác. Nếu dùng biến thể MOVE ONLINE hoặc cơ chế duy trì index khác, vẫn cần kiểm tra metadata thực tế.

### 7.6. Thu thập thống kê khi phù hợp

Sau purge lớn hoặc tổ chức lại segment, thống kê optimizer có thể không phản ánh dữ liệu mới. Với schema có quyền phù hợp:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_REORG',
        cascade => TRUE
    );
END;
/
~~~

Dấu / ở cuối là lệnh thực thi PL/SQL block của SQL*Plus/SQLcl, không thuộc cú pháp PL/SQL. Trong production cần tuân theo chính sách thu thập statistics vì thay đổi này có thể ảnh hưởng plan.

### 7.7. Dọn bảng thử nghiệm

Khi chắc chắn không cần giữ dữ liệu sandbox:

~~~sql
DROP TABLE lab_reorg PURGE;
~~~

PURGE tránh giữ đối tượng trong recycle bin theo hành vi thông thường, chỉ dùng cho bảng thực hành được phép xóa. Không coi DROP TABLE là cách hoàn tác một thao tác reorganize của bảng nghiệp vụ.

## 8. Tác động tới ROWID, index, lock và giao dịch

### 8.1. ROWID là vị trí, không phải khóa bền vững

ROWID của heap table thường biểu thị vị trí vật lý của hàng. SHRINK/MOVE có thể thay đổi ROWID. Ứng dụng Java lưu ROWID cũ rồi dùng lại sau bảo trì có thể không tìm được hàng hoặc không còn tham chiếu đúng vị trí.

Sử dụng **primary key** hoặc khóa nghiệp vụ ổn định để định danh hàng trong tầng ứng dụng.

### 8.2. DDL và implicit commit

ALTER TABLE, ALTER INDEX, TRUNCATE là DDL; Oracle có quy tắc **implicit commit**. Không xem chúng như UPDATE có thể rollback theo giao dịch thông thường. Tránh chạy DDL bảo trì xen giữa các thao tác nghiệp vụ chưa hoàn tất.

Cần chuẩn bị kế hoạch khôi phục, backup thích hợp và cửa sổ triển khai. Không giả định ROLLBACK có thể đảo ngược một lệnh MOVE đã hoàn thành.

### 8.3. Tải và tính đồng thời

- SHRINK SPACE COMPACT hỗ trợ chia giai đoạn gom dữ liệu và điều chỉnh HWM, nhưng vẫn sử dụng CPU/I/O/redo/undo.
- SHRINK khi hoàn tất có thể cần khóa liên quan đến hạ HWM.
- MOVE ngoại tuyến có thể gây gián đoạn DML; MOVE ONLINE nếu được hỗ trợ sẽ giảm hạn chế đó nhưng vẫn có lock ở một số thời điểm.
- Rebuild index và thu thập thống kê cũng có thể ảnh hưởng tài nguyên và execution plan.
- Hệ thống có standby/replication cần xét lượng redo và tác động của thay đổi vật lý.

Cả SHRINK lẫn MOVE đều không bảo đảm truy vấn nhanh hơn. Nếu SQL chậm vì thiếu index, JOIN kém, chọn sai plan hay trả quá nhiều dữ liệu, reorganize không thay thế việc tối ưu SQL. Nên đo lại những SQL quan trọng trước và sau thao tác.

## 9. Vì sao datafile có thể không nhỏ lại?

Giả sử SHRINK trả vài GB extent về tablespace. Các extent đó có thể nằm **giữa datafile**, trong khi các extent đang được dùng khác vẫn nằm gần cuối:

~~~text
Datafile:
| đang dùng | free | đang dùng | free | đang dùng | free |
                                              ^
                              Extent còn tồn tại gần cuối
~~~

Để giảm kích thước vật lý, DBA cần đánh giá **phần cuối datafile có thực sự trống và có thể thu hồi hay không**. Một tablespace có tổng free space lớn không có nghĩa mọi datafile có thể resize nhỏ tương ứng.

Khi dùng ASM, filesystem, cloud storage hay thin provisioning, việc thu hồi dung lượng vật lý và cách tính phí còn phụ thuộc hệ thống lưu trữ. Vì vậy cần đo mục tiêu ở cấp thích hợp, không chỉ trong USER_SEGMENTS.

## 10. Chọn phương án theo tình huống

| Bối cảnh | Hướng cân nhắc | Lý do |
| --- | --- | --- |
| Xóa rồi chèn lại dữ liệu cùng quy mô thường xuyên | **Có thể giữ nguyên** | Tái sử dụng block trống thay vì trả rồi cấp lại |
| Heap table trên ASSM, xóa nhiều hàng, cần trả extent | **SHRINK SPACE** nếu đủ điều kiện | Gom hàng, hạ HWM |
| Muốn tách phần gom dữ liệu khỏi giai đoạn hạ HWM | **COMPACT rồi SHRINK** | Dễ bố trí thời gian vận hành |
| Cần di chuyển bảng sang tablespace khác | **MOVE** | Xây lại segment ở vùng đích |
| Bảng không đủ điều kiện SHRINK nhưng có phương án MOVE | **MOVE** theo loại đối tượng | Khác điều kiện áp dụng của shrink |
| Chỉ một partition chứa dữ liệu cũ | **Partition maintenance** | Tác động đúng phần dữ liệu |
| Index UNUSABLE sau MOVE | **REBUILD hoặc cơ chế tương ứng** | Khôi phục khả năng sử dụng |
| B-tree index còn hợp lệ, nhiều khoảng trống | **COALESCE/SHRINK** khi phù hợp | Tái sử dụng hoặc thu hồi không gian |
| LOB chiếm phần lớn dung lượng | **Bảo trì LOB segment riêng** | Table segment không phản ánh toàn bộ |
| Muốn giảm kích thước datafile | **Quản trị datafile riêng** | Không suy ra từ shrink segment |

Các hướng này cần được xác nhận theo phiên bản/edition và kiểu đối tượng thực tế.

## 11. Quy trình bảo trì có kiểm soát

1. **Xác định mục tiêu:** cần free space cho tablespace, giảm HWM để cải thiện quét bảng, di chuyển tablespace hay giảm datafile?
2. **Ghi nhận baseline:** số hàng, mức cấp phát theo segment, index/LOB, kế hoạch SQL, xu hướng tăng trưởng và mức tái sử dụng chỗ trống.
3. **Xác nhận tính phù hợp:** ASSM, row movement, loại bảng/index, partition, LOB và hạn chế của SHRINK/MOVE ONLINE.
4. **Tính tài nguyên:** MOVE có thể cần không gian cho segment mới; SHRINK có chi phí gom hàng, redo/undo, I/O và lock; index maintenance cũng cần ngân sách.
5. **Chuẩn bị vận hành:** quyền, thời điểm ít tải, backup và phương án khôi phục, tác động đến các session, job, standby hoặc replication.
6. **Thực hiện thao tác đã chọn:** không tự động chạy cả SHRINK lẫn MOVE nếu chỉ cần một phương án.
7. **Kiểm chứng:** số hàng và khóa chính, trạng thái index, số extent/bytes, free space tablespace, truy vấn ứng dụng và plan sau bảo trì.
8. **Theo dõi xu hướng:** nếu segment nhanh chóng lớn trở lại, xem retention, batch purge và partitioning thay vì reorganize liên tục.

## 12. Những nhầm lẫn thường gặp

**“Xóa 80% hàng thì Oracle trả 80% dung lượng.”** Không đúng. DELETE tạo khoảng trống nội bộ, không nhất thiết hạ HWM hay trả extent.

**“SHRINK không di chuyển hàng.”** Không đúng. Shrink có thể di chuyển hàng và đổi ROWID.

**“SHRINK sẽ làm nhỏ datafile.”** Không chắc. Nó có thể trả extent về tablespace; datafile là tầng riêng.

**“MOVE không ảnh hưởng index.”** Không đúng với mọi biến thể. MOVE ngoại tuyến thông thường có thể khiến index UNUSABLE.

**“COALESCE index luôn thu hồi extent.”** Không đúng. COALESCE chủ yếu hướng tới khả năng tái sử dụng block nội bộ.

**“Bảng có CLOB/BLOB thì chỉ cần SHRINK bảng.”** Không đủ. LOB có thể nằm ở segment riêng chiếm phần lớn dung lượng.

**“Mọi bảng đều dùng được SHRINK SPACE.”** Không đúng. Cần điều kiện ASSM và kiểu đối tượng được hỗ trợ.

**“ONLINE nghĩa là không cần kế hoạch bảo trì.”** Không đúng. Các biến thể online vẫn có chi phí vận hành và giới hạn riêng.

**“DDL thành công là đủ chứng minh tối ưu.”** Không đúng. Phải đối chiếu dữ liệu, index, không gian và hiệu năng truy vấn.

## 13. Bài tập tự luyện

1. Một bảng 40 GB chỉ còn 5% số hàng nhưng dự kiến ngày mai sẽ chèn lại lượng lớn dữ liệu. Vì sao không shrink ngay có thể hợp lý?
2. Sau DELETE, COUNT(*) giảm mạnh nhưng USER_SEGMENTS.BYTES hầu như không đổi. Hãy giải thích bằng block, extent và HWM.
3. Bảng không nằm trong ASSM tablespace. Vì sao cần xem phương án khác trước khi SHRINK?
4. Sau ALTER TABLE MOVE, những chỉ số và view nào giúp phát hiện index cần rebuild?
5. Một bảng có 500 MB table segment và 30 GB LOB segment. Vì sao SHRINK table segment ít tác động đến tổng dung lượng?
6. Sau shrink, tablespace free space tăng nhưng datafile vẫn giữ nguyên. Điều gì đã xảy ra?
7. Vì sao ứng dụng Java nên dùng primary key thay cho ROWID để lưu định danh hàng?
8. Khi nào COALESCE index phù hợp hơn REBUILD?
9. Vì sao một lệnh MOVE có thể báo thiếu dung lượng dù mục tiêu là giải phóng dung lượng?
10. Hãy so sánh SHRINK và MOVE theo điều kiện ASSM, cơ chế di chuyển hàng, index, locking, chuyển tablespace và không gian bổ sung.

Trong Oracle Database, **không gian trống bên trong segment, free space của tablespace và kích thước datafile là ba cấp khác nhau**. SHRINK giúp gom hàng và hạ HWM với các đối tượng đủ điều kiện; MOVE tái tạo hoặc chuyển vị trí segment; index, LOB và partition có cơ chế riêng. Việc chọn phương án dựa trên dữ liệu trước/sau cùng kế hoạch vận hành sẽ giúp thu hồi không gian mà vẫn bảo toàn dữ liệu và khả năng phục vụ của ứng dụng.
