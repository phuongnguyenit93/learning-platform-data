# Heap, trang dữ liệu và cấu trúc tuple trong PostgreSQL

## 1. PostgreSQL lưu một hàng trong bảng như thế nào?

Khi chạy:

```sql
INSERT INTO inventory.products(product_code, product_name, quantity)
VALUES ('BOOK-01', 'PostgreSQL thực hành', 12);
```

ta nhìn thấy một hàng logic gồm ba cột. Nhưng PostgreSQL không lưu bảng thành một danh sách object Java hay một file CSV. Với bảng thông thường, dữ liệu được tổ chức thành **heap relation**: một tập các trang dữ liệu (*pages/blocks*), mỗi trang có các vị trí tham chiếu đến những tuple (phiên bản hàng) đang hoặc từng tồn tại trên trang.

Mô hình khái quát:

```text
Database
  |
  +-- Schema
       |
       +-- Table (heap relation)
            |
            +-- Main fork
            |     +-- Block 0 / Page 0
            |     +-- Block 1 / Page 1
            |     +-- Block 2 / Page 2
            |     +-- ...
            |
            +-- FSM fork
            +-- VM fork
            +-- TOAST relation (nếu cần)
```

Mỗi tuple vật lý chứa thông tin về phiên bản hàng, transaction tạo/xóa/cập nhật, vị trí dữ liệu và các giá trị cột. Index thường lưu **TID** trỏ đến vị trí tuple trên heap, thay vì tự chứa toàn bộ hàng như một bản sao đầy đủ.

Điểm quan trọng: **heap không phải cấu trúc tự sắp xếp theo primary key**. Nếu muốn kết quả theo thứ tự, truy vấn vẫn cần **ORDER BY**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích heap relation và vì sao heap không bảo đảm thứ tự hàng.
2. Phân biệt relation, fork, segment, block/page, line pointer và tuple.
3. Đọc cấu trúc một heap page ở mức khái niệm.
4. Mô tả page header, vùng line pointers, free space và tuple area.
5. Giải thích tuple header, xmin, xmax, ctid, null bitmap và alignment.
6. Hiểu vì sao một hàng logic có thể có nhiều tuple versions do MVCC.
7. Phân biệt ctid với khóa chính và hiểu giới hạn của system columns.
8. Mô tả TOAST và cách PostgreSQL lưu giá trị lớn.
9. Hiểu HOT update, fillfactor và vai trò của free space.
10. Phân biệt Free Space Map (FSM) với Visibility Map (VM).
11. Giải thích VACUUM, pruning, freezing và bloat.
12. Hiểu mối liên hệ giữa heap TID, index scan và index-only scan.
13. Dùng các hàm/catalog và extension phù hợp để quan sát kích thước, page và tuple.
14. Nhận diện các sai lầm phổ biến khi suy luận từ cấu trúc vật lý.

---

## 2. Thuật ngữ và các cấp lưu trữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Database | Cơ sở dữ liệu PostgreSQL |
| Relation | Đối tượng quan hệ như table, index, sequence hoặc view có metadata relation |
| Heap relation | Relation lưu tuple theo dạng heap-organized table |
| Fork | Một nhánh file vật lý của relation, ví dụ main/FSM/VM |
| Segment | Một file thuộc relation; relation lớn có thể chia thành nhiều segment |
| Block/Page | Đơn vị trang dữ liệu mà PostgreSQL đọc/ghi ở mức storage |
| Tuple | Một phiên bản hàng được lưu trong heap |
| Line pointer / ItemId | Phần tử trong page trỏ tới tuple hoặc trạng thái tuple trên page |
| TID / ItemPointer | Định danh vị trí heap theo block number và offset number |
| TOAST | Cơ chế lưu/giảm kích thước giá trị varlena lớn |
| FSM | Free Space Map, ghi nhận xấp xỉ dung lượng trống của các page |
| VM | Visibility Map, ghi nhận page có trạng thái all-visible/all-frozen |

### 2.1. Relation không đồng nghĩa một file duy nhất

Một bảng nhỏ có thể chỉ chiếm một file main fork. Nhưng một relation lớn có thể có nhiều segment; ngoài ra có các fork phụ và có thể có TOAST relation riêng.

### 2.2. Heap không phải một linked list theo thứ tự insert

Một page có thể chứa nhiều tuple, các tuple mới có thể được đặt vào page có free space thích hợp. Sau UPDATE, tuple version mới có thể ở page khác hoặc cùng page nếu HOT update. Không dựa vào thứ tự vật lý để thể hiện business ordering.

### 2.3. Heap và index có vai trò khác nhau

- Heap giữ các tuple và các phiên bản tuple.
- Index cung cấp đường tìm kiếm, thường dẫn tới heap TID để kiểm tra/đọc tuple.
- Một số index-only scans có thể trả kết quả mà không cần heap fetch khi Visibility Map cho phép, nhưng index vẫn có semantics riêng.

## 3. Heap page và kích thước block

PostgreSQL tổ chức dữ liệu theo page/block. Trong phần lớn bản cài đặt phổ biến, kích thước page là **8 KiB (8192 bytes)**.

Kiểm tra:

```sql
SHOW block_size;
```

Kết quả thường gặp:

```text
 block_size
------------
 8192
```

### 3.1. Block size là đặc tính build của PostgreSQL

Kích thước block được xác định khi build PostgreSQL, không phải một thuộc tính tùy chỉnh riêng cho từng bảng bằng ALTER TABLE.

Không nên giả định mọi bản PostgreSQL trên mọi nền tảng đều bắt buộc có 8 KiB. Hãy đọc SHOW block_size trên server thật.

### 3.2. Page là đơn vị quản lý vật lý

Một heap page có thể chứa:

- Header mô tả trạng thái page.
- Mảng line pointers.
- Vùng trống để tuple mới được thêm hoặc cập nhật.
- Các heap tuples được lưu từ phía cuối page.

Số hàng trên một page không cố định. Nó phụ thuộc kích thước tuple, null bitmap, alignment, line pointer, TOAST pointer và free space.

### 3.3. Tính số block gần đúng

Với main fork:

```sql
SELECT
    pg_relation_size('public.some_table'::regclass) AS main_bytes,
    current_setting('block_size')::integer AS block_bytes,
    pg_relation_size('public.some_table'::regclass)
        / current_setting('block_size')::integer AS main_blocks;
```

Đây là phép chia để ước lượng số block trong main fork. Không cộng nhầm kích thước index/TOAST vào đây.

## 4. Sơ đồ bố trí một heap page

Một page thông thường có bố cục khái quát:

```text
Đầu page / offset 0
+---------------------------------------------------+
| PageHeaderData                                    |
+---------------------------------------------------+
| ItemIdData #1                                     |
| ItemIdData #2                                     |
| ItemIdData #3                                     |
| ...                                               |
| (line pointer array grows from header)            |
+---------------------------------------------------+
|                                                   |
|             Free space                            |
|                                                   |
+---------------------------------------------------+
| Tuple C                                            |
|                                                   |
| Tuple B                                            |
|                                                   |
| Tuple A                                            |
+---------------------------------------------------+
Cuối page / BLCKSZ
```

Hai hướng phát triển đối diện nhau:

- Page header và line pointer array phát triển từ đầu page về phía sau.
- Tuple data được đặt từ cuối page ngược về phía đầu.
- Vùng giữa hai phần là free space có thể được sử dụng.

### 4.1. Vì sao cần line pointer?

Index và TID tham chiếu tới **slot line pointer**, không phải trực tiếp byte offset của tuple. Nếu PostgreSQL cần compact dữ liệu trong page, vị trí byte của tuple có thể thay đổi trong khi line pointer vẫn là điểm tham chiếu.

Điều này giúp TID tiếp tục xác định slot trên page trong các thao tác quản lý page phù hợp.

### 4.2. Page của heap thường không dùng special space

Cấu trúc page tổng quát có thể dành vùng special space cho access method. Heap page thông thường không cần vùng special riêng như một số index access methods, nên pd_special thường trỏ tới cuối page.

Không áp dụng sơ đồ chi tiết của B-tree index page cho heap page: chúng là hai loại page có mục đích và cấu trúc khác nhau.

## 5. PageHeaderData: metadata ở đầu page

Page header chứa thông tin phục vụ quản lý page. Các trường quan trọng gồm:

| Trường | Vai trò khái quát |
|---|---|
| pd_lsn | LSN của WAL record liên quan gần nhất đã được áp dụng cho page |
| pd_checksum | Trường checksum của page khi cơ chế checksum được bật/sử dụng |
| pd_flags | Các cờ trạng thái page |
| pd_lower | Ranh giới dưới của vùng line pointer array |
| pd_upper | Ranh giới trên của vùng tuple/free space |
| pd_special | Bắt đầu special space |
| pd_pagesize_version | Thông tin kích thước page và version format |
| pd_prune_xid | Thông tin hỗ trợ xác định page có thể cần pruning |

Trong layout PostgreSQL thông dụng, PageHeaderData chiếm khoảng **24 bytes**. Đây là chi tiết implementation; hãy đối chiếu source/documentation của phiên bản cụ thể nếu cần phân tích forensic hoặc viết công cụ mức byte.

### 5.1. pd_lower và pd_upper

Với heap page bình thường:

- pd_lower đánh dấu điểm kết thúc line pointer array.
- pd_upper đánh dấu vùng bắt đầu của tuple area từ phía cuối page.
- pd_upper - pd_lower là phần trống liên tục giữa hai vùng, không nhất thiết bằng tổng free space có thể thu hồi nếu page có fragmentation hoặc tuple chết cần pruning.

### 5.2. pd_lsn và WAL

WAL (Write-Ahead Logging) cho phép PostgreSQL phục hồi thay đổi sau crash. Page LSN giúp xác định trạng thái WAL mà page đã phản ánh theo cơ chế recovery.

pd_lsn không phải transaction ID và cũng không phải timestamp của lần INSERT gần nhất.

### 5.3. Checksum không phải encryption

Page checksum, nếu được bật, giúp phát hiện một số dạng page corruption. Nó không che dữ liệu khỏi người đọc file, không mã hóa page và không thay backup/restore.

### 5.4. pd_prune_xid không phải số hàng chết chính xác

Đây là metadata hỗ trợ quản lý/pruning, không nên dùng như một thống kê trực tiếp về số tuple dead trong page.

## 6. Line pointers / ItemIdData

Mỗi line pointer là một entry nhỏ trong page, thường chiếm **4 bytes**. Nó mô tả vị trí và kích thước tuple cùng trạng thái slot.

Một số trạng thái có thể gặp:

- LP_UNUSED: slot không được sử dụng.
- LP_NORMAL: slot trỏ tới tuple bình thường.
- LP_REDIRECT: slot chuyển hướng, thường liên quan HOT chain/pruning.
- LP_DEAD: slot được đánh dấu dead theo trạng thái heap page.

Các tên cờ là chi tiết nội bộ; cách hiển thị chính xác tùy công cụ quan sát.

### 6.1. Offset number là gì?

TID của heap thường có dạng:

```text
(block_number, offset_number)
```

offset_number xác định entry trong line pointer array của block đó. Nó **không phải byte offset tuyệt đối** của tuple trong file.

### 6.2. Vì sao line pointer quan trọng khi page được compact?

Tuple bytes có thể được di chuyển bên trong page để gom free space. PostgreSQL có thể cập nhật lp_off trong line pointer tương ứng mà không bắt buộc đổi TID của slot.

### 6.3. Slot không đồng nghĩa một hàng logic vĩnh viễn

Một row có nhiều tuple versions theo MVCC; HOT chain có thể có các line pointers/redirects khác nhau. Không lưu ctid làm khóa nghiệp vụ lâu dài.

## 7. Tuple là gì?

Tuple là một **phiên bản vật lý của hàng**. Một hàng logic có thể trải qua:

```text
INSERT -> tuple version V1
UPDATE -> tuple version V2
UPDATE -> tuple version V3
DELETE -> V3 trở thành phiên bản đã bị xóa
```

Với MVCC, PostgreSQL giữ các phiên bản cần thiết để transaction khác nhau nhìn thấy dữ liệu theo snapshot của mình. Vì vậy một bảng có 1.000 hàng logic hiện hành vẫn có thể có nhiều tuple vật lý hơn 1.000 do version cũ, tuple chết hoặc dữ liệu chưa được VACUUM/prune.

### 7.1. Tuple header và tuple data

Tuple vật lý gồm hai phần khái quát:

```text
Heap tuple
+----------------------------------+
| Tuple header                     |
|  - xmin / xmax / command info    |
|  - ctid                          |
|  - infomask flags                |
|  - header offset                 |
|  - optional null bitmap          |
+----------------------------------+
| Attribute data                   |
|  - column 1                      |
|  - column 2                      |
|  - padding/alignment             |
|  - column 3                      |
|  - varlena / TOAST pointer       |
+----------------------------------+
```

Kích thước tuple không đơn giản bằng tổng length của các giá trị hiển thị. Cần cộng header, bitmap nếu có, alignment/padding và các cấu trúc dữ liệu vật lý khác.

### 7.2. Header cố định và phần mở rộng

HeapTupleHeaderData có những trường fixed-size; sau đó có thể có null bitmap và phần dữ liệu bắt đầu tại offset được ghi trong t_hoff. Header cần alignment phù hợp.

Con số header tối thiểu thường được mô tả khoảng 23 bytes trước khi tính padding/optional bitmap; không dùng con số này như công thức kích thước tuyệt đối cho mọi tuple.

## 8. Các trường MVCC trong tuple header

Một số trường quan trọng:

| Trường | Vai trò |
|---|---|
| xmin | Transaction ID tạo tuple version |
| xmax | Transaction ID/metadata liên quan xóa, thay thế hoặc khóa tuple |
| cmin / cmax | Command ID liên quan thao tác trong transaction |
| ctid | TID của tuple hiện tại hoặc vị trí tuple version kế tiếp theo ngữ cảnh |
| infomask | Các bit trạng thái của tuple |
| infomask2 | Các bit trạng thái bổ sung, gồm thông tin liên quan số thuộc tính |
| t_hoff | Offset tới phần dữ liệu thuộc tính trong tuple |

### 8.1. xmin

xmin xác định transaction đã tạo tuple version. Một transaction chỉ nhìn thấy tuple khi các quy tắc snapshot/transaction visibility cho phép.

### 8.2. xmax không luôn có nghĩa “đã xóa”

xmax có thể biểu diễn transaction xóa hoặc thay thế tuple, nhưng cũng có các trường hợp thông tin khóa tuple hoặc MultiXact. Không đọc xmax <> 0 rồi kết luận chắc chắn hàng đã bị xóa khỏi mọi transaction.

### 8.3. cmin/cmax

Command IDs phân biệt các command trong cùng transaction. Chúng là một phần của cơ chế MVCC/visibility, không phải cột audit timestamp cho ứng dụng.

### 8.4. Infomask

Các cờ trong infomask cho biết đặc tính tuple, ví dụ có null bitmap, trạng thái transaction đã được xác nhận theo hint bits, có external/varlena attributes hoặc trạng thái khác. Đây là implementation details; dùng công cụ chuẩn thay vì hard-code bit masks trong application.

## 9. System columns: xmin, xmax, ctid, tableoid

PostgreSQL cung cấp một số system columns có thể truy vấn:

```sql
SELECT
    tableoid::regclass AS physical_relation,
    ctid,
    xmin,
    xmax,
    customer_id,
    full_name
FROM public.customers;
```

Các cột này không được khai báo trong DDL như cột business thông thường.

### 9.1. ctid

ctid thể hiện vị trí vật lý của tuple version trong relation, thường có dạng (block, offset).

Nó hữu ích cho:

- Debug page/tuple.
- Quan sát tuple version.
- Lab về UPDATE/HOT/VACUUM.
- Một số thao tác nội bộ có transaction scope và kiểm soát chặt.

Nó không phù hợp làm primary key hoặc external identifier.

### 9.2. UPDATE có thể thay đổi ctid

UPDATE thường tạo tuple version mới. Tuple cũ có thể có ctid trỏ tới tuple version mới. Vì vậy ctid của hàng có thể đổi sau UPDATE.

VACUUM FULL, CLUSTER hoặc thao tác rewrite relation có thể làm vị trí vật lý thay đổi rộng hơn.

### 9.3. xmin không phải created_at

xmin là transaction ID, không phải thời điểm tạo hàng. Transaction IDs có vòng đời, wraparound/freeze và semantics nội bộ; không dùng nó thay created_at.

### 9.4. xmax không phải deleted_at

xmax không phải timestamp xóa. Nếu cần audit thời điểm/actor thay đổi, tạo cột hoặc bảng history/audit phù hợp.

### 9.5. tableoid trong partitioned tables

Khi query qua partitioned table, tableoid giúp xác định relation/partition vật lý chứa tuple. Đây là metadata hữu ích khi điều tra phân vùng, không phải tenant authorization.

## 10. Tuple visibility: vì sao cùng page có thể chứa phiên bản cũ và mới?

MVCC cho phép nhiều transaction đọc snapshot khác nhau mà không phải khóa đọc mọi hàng. Một ví dụ:

```text
Ban đầu: quantity = 5 (tuple V1)

T1: BEGIN
T1: UPDATE quantity = 4
    -> tạo tuple version V2

T2: đang dùng snapshot cũ
    -> có thể vẫn nhìn V1

T1: COMMIT

Transaction mới
    -> nhìn V2

V1 chỉ có thể được thu hồi khi không còn snapshot cần nhìn thấy nó
```

Visibility phụ thuộc transaction status, snapshot và thông tin tuple; không chỉ nhìn một trường xmin hoặc xmax đơn lẻ rồi tự suy ra.

### 10.1. UPDATE thường tạo phiên bản mới

Trong PostgreSQL heap, UPDATE thường không ghi đè trực tiếp mọi bytes của tuple cũ như một mô hình in-place đơn giản. Nó tạo phiên bản mới và đánh dấu phiên bản cũ theo cơ chế MVCC.

### 10.2. DELETE thường không lập tức xóa bytes

DELETE đánh dấu tuple là không còn hợp lệ với các snapshot tương lai sau khi transaction xóa commit, nhưng bytes vật lý có thể còn tồn tại đến khi pruning/VACUUM có thể thu hồi.

### 10.3. Tuple dead phụ thuộc snapshot horizon

Một tuple version chỉ có thể được loại bỏ khi không còn transaction/snapshot cần nó. Long-running transactions hoặc replication slots giữ horizon cũ có thể trì hoãn việc thu hồi.

## 11. UPDATE, DELETE và bloat

Giả sử một hàng bị UPDATE 100 lần. Bảng không nhất thiết chỉ giữ một tuple duy nhất. Nó có thể trải qua nhiều versions:

```text
Page 0:
  tuple version cũ (dead khi không còn cần)
  tuple version mới

Page 1:
  một số versions khác

FSM:
  ghi nhận free space có thể dùng

VACUUM/pruning:
  thu hồi tuple chết khi an toàn
```

### 11.1. Bloat là gì?

Bloat là phần không gian vật lý không còn chứa dữ liệu sống hữu ích hoặc bị sử dụng kém hiệu quả do update/delete churn, page fragmentation, index entries cũ và các yếu tố khác.

Không có một con số bloat duy nhất luôn đúng cho mọi cách đo; cần hiểu tool và methodology.

### 11.2. Bảng có ít hàng vẫn có thể lớn

Nếu bảng từng có hàng triệu records rồi xóa gần hết, file có thể vẫn giữ nhiều pages để tái sử dụng. COUNT(*) nhỏ không chứng minh file nhỏ.

### 11.3. Heap bloat và index bloat khác nhau

- Heap bloat: page/tuple storage có không gian không hiệu quả.
- Index bloat: cấu trúc index chứa dead/underused pages hoặc phân bố không hiệu quả.

VACUUM và REINDEX giải quyết những vấn đề khác nhau; không coi chúng thay thế lẫn nhau.

## 12. TOAST: lưu giá trị lớn

PostgreSQL dùng cơ chế **TOAST** (*The Oversized-Attribute Storage Technique*) cho những giá trị varlena lớn như text, bytea, jsonb và các kiểu có representation phù hợp.

Khi tuple có thuộc tính quá lớn so với mục tiêu lưu inline, PostgreSQL có thể:

1. Nén giá trị.
2. Chuyển giá trị ra TOAST relation.
3. Lưu một pointer/descriptor trong tuple chính.
4. Chia giá trị ngoài dòng thành các chunks trong TOAST table.

Sơ đồ:

```text
Main heap tuple
+-----------------------------+
| id = 10                     |
| title = 'Document'          |
| body = TOAST pointer ------+-----------------+
+-----------------------------+                 |
                                                v
                                   TOAST relation
                                   +------------------+
                                   | value chunks     |
                                   | chunk sequence   |
                                   | chunk data       |
                                   +------------------+
```

### 12.1. TOAST relation là relation riêng

Bảng có giá trị TOAST có thể có TOAST table và index riêng. pg_total_relation_size tính cả phần liên quan theo semantics hàm; pg_relation_size của main table không kể hết toàn bộ footprint.

### 12.2. Không phải mọi text đều ra TOAST

Giá trị nhỏ thường lưu inline. Cơ chế quyết định phụ thuộc kích thước tuple, strategy của column và điều kiện page.

### 12.3. TOAST không phải Large Objects API

PostgreSQL Large Objects (lo_*) là một cơ chế khác, có API/metadata riêng. Không đồng nhất mọi bytea lớn hoặc text lớn với Large Objects.

## 13. TOAST storage strategies

Các storage strategies quen thuộc:

| Strategy | Compression | Out-of-line | Mục đích |
|---|---|---|---|
| PLAIN | Không | Không | Giữ inline, không nén |
| EXTENDED | Có thể | Có thể | Nén trước, chuyển out-of-line khi cần |
| EXTERNAL | Không | Có thể | Chuyển out-of-line nhưng không nén |
| MAIN | Có thể | Hạn chế/ưu tiên inline | Cố giữ inline, chỉ chuyển ra ngoài khi cần |

Ví dụ thay storage strategy:

```sql
ALTER TABLE documents
ALTER COLUMN body SET STORAGE EXTERNAL;
```

Đây là thay đổi policy cho cách lưu những giá trị được xử lý trong tương lai theo semantics PostgreSQL; không hiểu nó là lệnh tự động viết lại toàn bộ dữ liệu hiện có ngay lập tức.

### 13.1. Compression algorithm phụ thuộc version/build

PGLZ là lựa chọn truyền thống; một số phiên bản/build hỗ trợ LZ4. Hãy xác minh khả năng thực tế của server và cú pháp COMPRESSION trước khi dựa vào một thuật toán cụ thể.

### 13.2. Compression không luôn giảm tổng chi phí

Nén có CPU cost. Nếu workload thường xuyên đọc toàn bộ JSON/text lớn, việc decompress có thể ảnh hưởng latency. Nếu workload chỉ đọc metadata, TOAST giúp tuple chính gọn hơn.

### 13.3. TOAST pointer vẫn là metadata

Dù giá trị nằm ngoài dòng, main tuple vẫn giữ thông tin cần để tìm giá trị đó. Việc đọc cột TOAST có thể gây thêm I/O và detoasting.

## 14. Null bitmap và cách biểu diễn NULL

Tuple có thể chứa null bitmap để chỉ ra thuộc tính nào là NULL.

Ví dụ bảng:

```sql
CREATE TABLE sample_nulls (
    id integer NOT NULL,
    nickname text,
    age integer,
    note text
);
```

Một tuple:

```text
id       = 1
nickname = NULL
age      = 20
note     = NULL
```

Null bitmap ghi nhận trạng thái null của các thuộc tính. Giá trị NULL không được lưu như một chuỗi bytes thông thường có độ dài bằng 0.

### 14.1. NULL khác empty string

- SQL NULL: không có giá trị/unknown theo semantics SQL.
- '': chuỗi có độ dài 0.
- 0: số không.
- false: giá trị boolean false.

Các trạng thái có cách biểu diễn và hành vi truy vấn khác nhau.

### 14.2. Null bitmap chỉ là một phần overhead

Tuple có NULL vẫn cần header và line pointer. Bitmap có kích thước phụ thuộc số thuộc tính và alignment. Không thể tính kích thước tuple chỉ bằng octet_length của các cột text.

## 15. Alignment và padding

PostgreSQL lưu các thuộc tính theo thứ tự cột trong tuple descriptor, có yêu cầu alignment theo kiểu dữ liệu.

Một số nhóm alignment thường gặp:

| Mã alignment | Yêu cầu khái quát |
|---|---|
| c | 1 byte |
| s | 2 bytes |
| i | 4 bytes |
| d | 8 bytes |

Ví dụ kiểu fixed-length int2, int4, int8 có yêu cầu alignment tương ứng. Một số varlena và kiểu khác có quy tắc riêng.

### 15.1. Padding có thể làm tuple lớn hơn tổng payload

Giữa hai thuộc tính có thể có bytes padding để field tiếp theo bắt đầu tại boundary phù hợp.

### 15.2. Column order có thể ảnh hưởng physical size

Một số thứ tự cột có thể tạo padding khác nhau, đặc biệt với nhiều cột fixed-width có alignment lớn/nhỏ xen kẽ. Đây là tối ưu hóa mức vật lý cần đo, không nên thay đổi schema chỉ dựa trên một quy tắc folklore.

### 15.3. Đừng hard-code offset của cột

Tuple data không lưu một offset cố định cho mỗi cột như một struct C do application tự định nghĩa. PostgreSQL dùng tuple descriptor, null bitmap, alignment và type metadata để giải mã thuộc tính.

## 16. TID, heap tuple và index

Một B-tree index thường lưu khóa index cùng TID trỏ tới tuple trên heap:

```text
B-tree index entry
+----------------------------+
| key = customer_id 101      |
| TID = (block 8, offset 3)  |
+----------------------------+
             |
             v
Heap block 8
+----------------------------+
| line pointer #3            |
|       |                    |
|       v                    |
| heap tuple version         |
+----------------------------+
```

### 16.1. Index không nhất thiết lưu toàn bộ hàng

Index lưu key và thông tin cần để xác định tuple. Khi cần các cột không có trong index hoặc phải xác minh visibility, executor có thể truy cập heap.

### 16.2. Index scan có thể cần heap fetch

Index entry chỉ tới TID; PostgreSQL cần đảm bảo tuple version phù hợp snapshot và lấy các thuộc tính cần thiết.

### 16.3. Index-only scan và Visibility Map

Index-only scan có thể tránh heap visit khi index chứa đủ cột cần và Visibility Map cho biết page all-visible. Nếu page chưa all-visible, PostgreSQL có thể vẫn phải kiểm tra heap visibility.

### 16.4. Index-only không có nghĩa “không bao giờ đọc heap”

Nếu VM bit không bật hoặc bị clear do UPDATE, heap fetch có thể xảy ra. Đọc EXPLAIN (ANALYZE, BUFFERS) để quan sát Heap Fetches.

## 17. HOT update (Heap-Only Tuple)

HOT là tối ưu cho UPDATE khi điều kiện phù hợp:

- Các cột được index không thay đổi theo những quy tắc liên quan.
- Có đủ free space trên cùng heap page để tạo tuple version mới.
- Những điều kiện implementation khác được thỏa.

Khi HOT update xảy ra, PostgreSQL có thể tạo tuple version mới trong cùng page mà không cần thêm entry mới cho mọi index, và line pointers/chain hỗ trợ đi từ version cũ tới version mới.

### 17.1. Vì sao HOT có lợi?

UPDATE một cột không được index có thể tránh nhiều index writes, giảm WAL và index bloat trong trường hợp phù hợp.

### 17.2. Khi nào HOT không xảy ra?

- Cột được index thay đổi.
- Expression/partial index phụ thuộc cột thay đổi.
- Không còn đủ chỗ trên cùng page.
- Những điều kiện HOT khác không thỏa.

### 17.3. HOT không phải một kiểu UPDATE mà ứng dụng gọi trực tiếp

Không có cú pháp UPDATE HOT. PostgreSQL quyết định có thể áp dụng tối ưu dựa trên điều kiện page/index.

### 17.4. Quan sát HOT statistics

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY relname;
```

Các thống kê là cumulative/ước lượng theo hệ thống statistics, cần hiểu reset và thời điểm cập nhật. n_tup_hot_upd cho biết số HOT updates được ghi nhận.

## 18. Fillfactor: chừa chỗ cho UPDATE

fillfactor của heap table điều khiển mục tiêu lấp đầy page khi tạo/ghi dữ liệu. Giá trị mặc định thường là 100, nghĩa là cố sử dụng gần hết page theo quy tắc lưu trữ.

Ví dụ:

```sql
CREATE TABLE hot_demo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stable_key text NOT NULL,
    counter integer NOT NULL DEFAULT 0,
    description text
) WITH (fillfactor = 80);
```

### 18.1. Vì sao chừa 20%?

Khoảng trống có thể tạo cơ hội để tuple version mới sau UPDATE nằm trên cùng page, tăng khả năng HOT update.

### 18.2. Fillfactor thấp có trade-off

- Bảng chiếm nhiều page hơn.
- Sequential scans có thể đọc nhiều block hơn.
- Cache footprint tăng.
- INSERT có thể dùng storage kém hiệu quả hơn.
- HOT/update performance có thể cải thiện với workload phù hợp.

### 18.3. Fillfactor không phải giới hạn kích thước tuple

Một tuple lớn vẫn có thể không fit trên page; fillfactor không bảo đảm HOT update.

### 18.4. Thay fillfactor không tự rewrite toàn bộ bảng

ALTER TABLE ... SET (fillfactor = 80) thay storage parameter cho các thao tác phù hợp trong tương lai; nó không tự compact/rewrite mọi page hiện tại thành mức 80%.

## 19. Free Space Map (FSM)

FSM là fork phụ ghi nhận ước lượng free space của các heap pages (và cấu trúc liên quan). Khi PostgreSQL cần đặt tuple mới, FSM hỗ trợ tìm page có thể có đủ chỗ.

### 19.1. FSM không phải bản đồ byte chính xác theo thời gian thực

Một page có thể thay đổi sau khi FSM ghi nhận; đây là metadata hỗ trợ lựa chọn page, không phải cam kết free bytes chính xác tại mọi thời điểm.

### 19.2. FSM hỗ trợ tái sử dụng chỗ trống

Sau DELETE/UPDATE và VACUUM, không gian có thể được đánh dấu để dùng cho các tuple mới, thay vì bắt buộc giảm file ngay.

### 19.3. Xem kích thước FSM

```sql
SELECT
    pg_relation_size('public.some_table'::regclass, 'main') AS main_bytes,
    pg_relation_size('public.some_table'::regclass, 'fsm') AS fsm_bytes;
```

Nếu fork chưa được tạo hoặc không có dữ liệu, kích thước có thể bằng 0.

### 19.4. pg_freespacemap

Extension pg_freespacemap có thể cho phép xem free-space estimates theo block. Việc cài extension và quyền thực thi phụ thuộc môi trường.

## 20. Visibility Map (VM)

VM ghi nhận trạng thái visibility của heap pages. Hai trạng thái quan trọng:

- **All-visible:** mọi tuple trên page có thể nhìn thấy đối với mọi transaction theo điều kiện visibility phù hợp.
- **All-frozen:** các tuple trên page đã được freeze theo cơ chế transaction ID.

### 20.1. Vì sao VM quan trọng với index-only scans?

Nếu page all-visible, PostgreSQL có thể bỏ qua heap visibility check cho index entries trỏ tới page ấy trong điều kiện phù hợp. Điều này giúp index-only scan giảm heap I/O.

### 20.2. UPDATE có thể làm mất all-visible

Khi page bị thay đổi, visibility bit có thể bị clear vì page không còn được bảo đảm all-visible.

### 20.3. VM không phải cache dữ liệu

VM không chứa các giá trị hàng; nó chứa trạng thái visibility/frozen của pages.

### 20.4. Xem kích thước VM

```sql
SELECT
    pg_relation_size('public.some_table'::regclass, 'vm') AS vm_bytes;
```

## 21. VACUUM và heap page

VACUUM giúp PostgreSQL quản lý tuple versions không còn cần thiết.

Ở mức khái quát, VACUUM có thể:

- Xác định tuple dead không còn cần cho snapshot hợp lệ.
- Thu hồi/đánh dấu slot và vùng tuple để tái sử dụng.
- Cập nhật Free Space Map.
- Cập nhật Visibility Map.
- Thực hiện index cleanup khi phù hợp.
- Hỗ trợ freezing transaction IDs cũ.

### 21.1. VACUUM thường không viết lại toàn bộ bảng

```sql
VACUUM (ANALYZE) public.some_table;
```

VACUUM thông thường chủ yếu làm cho không gian trong relation có thể tái sử dụng và cập nhật metadata/statistics. Nó thường **không làm file heap co lại tương ứng ngay**.

### 21.2. VACUUM FULL khác VACUUM

```sql
VACUUM FULL public.some_table;
```

VACUUM FULL rewrite relation để thu hồi không gian về filesystem, nhưng cần lock mạnh (thường ACCESS EXCLUSIVE), tạo bản viết lại và có chi phí I/O/dung lượng tạm. Không chạy tùy tiện trên bảng production lớn.

### 21.3. Pruning có thể diễn ra trong lúc hoạt động

PostgreSQL có thể prune tuple versions không còn cần trên page trong những thời điểm phù hợp, ví dụ khi page được truy cập. Không phải mọi việc dọn dẹp đều chờ một lần VACUUM thủ công.

### 21.4. Long-running transaction làm chậm thu hồi

Một transaction giữ snapshot cũ có thể khiến phiên bản tuple vẫn cần thiết. Replication slots hoặc các horizon khác cũng có thể trì hoãn cleanup. Theo dõi transaction age và replication state khi dead tuples tăng bất thường.

## 22. Autovacuum

Autovacuum là cơ chế nền giúp duy trì vacuum/analyze dựa trên ngưỡng và thống kê.

Những tham số có thể ảnh hưởng:

- autovacuum.
- autovacuum_vacuum_threshold.
- autovacuum_vacuum_scale_factor.
- autovacuum_analyze_threshold.
- autovacuum_analyze_scale_factor.
- Các tham số per-table storage parameters.
- Cost delay/limit và worker capacity.

### 22.1. Vì sao bảng nhỏ và bảng lớn cần policy khác?

Một scale factor cố định có thể tạo ngưỡng dead tuples lớn ở bảng hàng triệu rows hoặc quá thường xuyên ở bảng nhỏ. Có thể điều chỉnh per-table sau khi đo workload.

### 22.2. Autovacuum không phải một nút bật là hết bloat

Nó có thể bị chậm do:

- Transaction/snapshot kéo dài.
- Replication slot giữ xmin.
- Tải I/O/CPU.
- Worker capacity.
- Table-specific thresholds.
- Bảng có update/delete churn cao.

### 22.3. Theo dõi thống kê

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
```

n_live_tup và n_dead_tup là estimates, không phải kết quả đếm tuple vật lý tuyệt đối.

## 23. Freezing và transaction ID wraparound

PostgreSQL sử dụng transaction IDs có không gian hữu hạn. Nếu các tuple quá cũ không được freeze/maintain đúng, vấn đề wraparound có thể đe dọa tính đúng đắn visibility.

VACUUM có vai trò quan trọng trong việc:

- Đưa các tuple đủ cũ về trạng thái frozen phù hợp.
- Duy trì visibility qua vòng đời transaction IDs.
- Cập nhật all-frozen bits trên VM khi điều kiện đáp ứng.

### 23.1. Frozen không có nghĩa row bất biến

Freeze liên quan cách PostgreSQL diễn giải transaction ID cũ trong visibility. Nó không cấm UPDATE/DELETE hàng và không phải business flag.

### 23.2. Đừng tắt autovacuum tùy tiện

Tắt autovacuum trên bảng/database mà không có quy trình vacuum/freeze thay thế có thể gây tích tụ dead tuples, statistics cũ và rủi ro wraparound.

### 23.3. Kiểm tra cảnh báo vận hành

Theo dõi age của database/table frozen XIDs, autovacuum progress và cảnh báo wraparound theo phiên bản PostgreSQL. Không đợi đến khi server từ chối ghi để xử lý.

## 24. Heap page, index và MVCC visibility

Index scan không thể chỉ tìm đúng key rồi mặc nhiên trả tuple. Nó cần tôn trọng snapshot:

```text
B-tree lookup
    |
    v
Index entry (key, TID)
    |
    v
Heap page / line pointer
    |
    v
Tuple version
    |
    v
MVCC visibility check
    |
    +-- visible -> trả hàng
    |
    +-- not visible -> bỏ qua / xét version phù hợp
```

### 24.1. Vì sao index có thể chứa entry trỏ tới tuple chết?

UPDATE/DELETE và VACUUM có lifecycle riêng. Index entries cũ có thể tồn tại cho tới index cleanup; visibility check vẫn bảo đảm không trả sai version cho query.

### 24.2. HOT và index entries

HOT update có thể tránh tạo index entries mới cho tuple version mới trong điều kiện phù hợp. Index entry cũ dẫn tới chain trong cùng page, giúp tìm phiên bản phù hợp.

### 24.3. Index-only scan

Nếu index chứa đủ cột, executor có thể dùng index để trả giá trị. Tuy nhiên visibility check có thể yêu cầu heap visit trừ khi VM đánh dấu page all-visible.

## 25. TOAST, heap và chỉ số kích thước

Một số hàm hữu ích:

| Hàm | Mục đích |
|---|---|
| pg_relation_size(regclass) | Kích thước fork main mặc định của relation |
| pg_relation_size(regclass, fork) | Kích thước fork chỉ định |
| pg_table_size(regclass) | Kích thước table và thành phần liên quan như TOAST/forks, không cộng index theo cách pg_total_relation_size làm |
| pg_indexes_size(regclass) | Kích thước các indexes của table |
| pg_total_relation_size(regclass) | Tổng kích thước table + indexes và thành phần TOAST liên quan |
| pg_relation_filepath(regclass) | Đường dẫn vật lý relation theo storage mapping hiện tại |
| pg_column_size(value) | Kích thước representation lưu trữ của giá trị theo ngữ cảnh |
| pg_size_pretty(bytes) | Hiển thị kích thước dễ đọc |

Ví dụ:

```sql
SELECT
    pg_size_pretty(pg_relation_size('orm420.heap_demo')) AS main_fork,
    pg_size_pretty(pg_table_size('orm420.heap_demo')) AS table_with_toast,
    pg_size_pretty(pg_indexes_size('orm420.heap_demo')) AS indexes,
    pg_size_pretty(pg_total_relation_size('orm420.heap_demo')) AS total;
```

### 25.1. Không cộng sai các thành phần

pg_total_relation_size đã bao gồm những phần được tính bởi pg_table_size cùng indexes. Không cộng table_size + total_relation_size rồi gọi đó là tổng.

### 25.2. Kích thước logic và vật lý khác nhau

octet_length(text_value) đo byte length của giá trị sau khi lấy ra theo semantics kiểu dữ liệu. pg_column_size đo representation lưu trữ trong ngữ cảnh PostgreSQL và có thể chịu ảnh hưởng nén/TOAST. Chúng không luôn bằng nhau.

### 25.3. pg_relation_filepath

Đường dẫn có thể thay đổi sau thao tác rewrite relation, đổi tablespace hoặc các thao tác quản lý storage. Không lưu file path như ID bền vững của bảng trong ứng dụng.

## 26. Lab: tạo heap table với nhiều kiểu dữ liệu

Tạo schema lab:

```sql
CREATE SCHEMA IF NOT EXISTS orm420;

CREATE TABLE orm420.heap_demo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code integer NOT NULL,
    small_value smallint,
    label text,
    amount numeric(12, 2),
    active boolean NOT NULL DEFAULT true,
    payload text,
    created_at timestamptz NOT NULL DEFAULT now()
) WITH (fillfactor = 85);
```

Chèn một số hàng giả:

```sql
INSERT INTO orm420.heap_demo(
    code, small_value, label, amount, active, payload
)
SELECT
    g,
    CASE WHEN g % 3 = 0 THEN NULL ELSE (g % 100)::smallint END,
    CASE WHEN g % 4 = 0 THEN NULL ELSE 'item-' || g::text END,
    (g * 10.25)::numeric(12,2),
    (g % 2 = 0),
    repeat('training-data-', 20)
FROM generate_series(1, 300) AS g;
```

Kiểm tra:

```sql
SELECT
    id,
    code,
    small_value,
    label,
    amount,
    active,
    octet_length(payload) AS payload_bytes,
    ctid,
    xmin,
    xmax
FROM orm420.heap_demo
ORDER BY id
LIMIT 10;
```

### 26.1. Quan sát kích thước relation

```sql
SELECT
    pg_relation_size('orm420.heap_demo'::regclass) AS main_bytes,
    pg_table_size('orm420.heap_demo'::regclass) AS table_bytes,
    pg_indexes_size('orm420.heap_demo'::regclass) AS index_bytes,
    pg_total_relation_size('orm420.heap_demo'::regclass) AS total_bytes,
    pg_relation_filepath('orm420.heap_demo'::regclass) AS relation_path;
```

### 26.2. Ước lượng page count

```sql
SELECT
    pg_relation_size('orm420.heap_demo'::regclass)
        / current_setting('block_size')::integer AS main_page_count;
```

Page count của main fork không tính TOAST relation và indexes. Đừng so số này với total bytes rồi suy luận sai.

## 27. Lab: quan sát ctid trước và sau UPDATE

Lấy một tuple:

```sql
SELECT id, ctid, xmin, xmax, code
FROM orm420.heap_demo
WHERE id = 10;
```

Cập nhật:

```sql
UPDATE orm420.heap_demo
SET label = 'updated-label'
WHERE id = 10;
```

Đọc lại:

```sql
SELECT id, ctid, xmin, xmax, code, label
FROM orm420.heap_demo
WHERE id = 10;
```

ctid có thể thay đổi do tuple version mới. xmin thường phản ánh transaction tạo version mới. Giá trị quan sát cụ thể phụ thuộc page free space, HOT eligibility và transaction context.

### 27.1. Xem nhiều versions ở mức raw page

Một SELECT thông thường chỉ trả version nhìn thấy theo snapshot. Để xem tuple vật lý và line pointers, có thể dùng extension pageinspect trên lab page (phần sau).

### 27.2. Không dùng ctid làm API identifier

Nếu ứng dụng lưu ctid rồi dùng nó ở request sau, UPDATE/VACUUM FULL/CLUSTER có thể làm vị trí thay đổi. Hãy dùng primary key ổn định.

## 28. Lab: DELETE và VACUUM

Xóa một tập hàng giả:

```sql
DELETE FROM orm420.heap_demo
WHERE id BETWEEN 20 AND 60;
```

Kiểm tra thống kê:

```sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'orm420'
  AND relname = 'heap_demo';
```

Các thống kê có thể không cập nhật tức thì và là estimates.

Chạy vacuum trên lab:

```sql
VACUUM (VERBOSE, ANALYZE) orm420.heap_demo;
```

### 28.1. Vì sao file có thể không giảm?

VACUUM thông thường làm không gian có thể tái sử dụng trong relation. Nó không hứa compact toàn bộ relation và trả tất cả page cho filesystem.

### 28.2. Quan sát sau vacuum

Đọc lại n_dead_tup, kích thước relation và page inspection. Kết quả phụ thuộc snapshot còn tồn tại, pruning, autovacuum, page layout và workload.

### 28.3. Đừng dùng VACUUM FULL chỉ để số bytes đẹp

VACUUM FULL có chi phí và lock mạnh. Chỉ cân nhắc khi có mục tiêu reclaim storage rõ ràng và kế hoạch vận hành.

## 29. Lab: xem TOAST với payload lớn

Tạo bảng:

```sql
CREATE TABLE orm420.toast_demo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    body text
);
```

Chèn dữ liệu lớn giả:

```sql
INSERT INTO orm420.toast_demo(title, body)
VALUES (
    'Large training document',
    repeat('TOAST-training-', 20000)
);
```

Xem kích thước logic và representation:

```sql
SELECT
    id,
    octet_length(body) AS logical_bytes,
    pg_column_size(body) AS stored_datum_bytes,
    pg_table_size('orm420.toast_demo'::regclass) AS table_bytes,
    pg_total_relation_size('orm420.toast_demo'::regclass) AS total_bytes
FROM orm420.toast_demo;
```

### 29.1. Vì sao body có thể không nằm trọn trong main tuple?

Một giá trị lớn có thể được nén hoặc lưu out-of-line trong TOAST relation. Tuple chính giữ pointer/metadata cần thiết.

### 29.2. Kiểm tra TOAST relation

Có thể tìm relation TOAST bằng catalog:

```sql
SELECT
    c.relname AS table_name,
    c.reltoastrelid::regclass AS toast_relation
FROM pg_class AS c
WHERE c.oid = 'orm420.toast_demo'::regclass;
```

Nếu reltoastrelid là 0 hoặc không có TOAST relation, bảng chưa cần TOAST relation theo trạng thái hiện tại.

### 29.3. TOAST không phải một index search engine cho text

TOAST chia/giữ giá trị lớn; nó không cung cấp full-text search. Nếu cần tìm nội dung, thiết kế tsvector, GIN hoặc search service theo workload.

## 30. pageinspect: đọc page ở mức thấp

pageinspect là extension PostgreSQL cung cấp các hàm quan sát page. Nó hữu ích trong học tập, điều tra và hiểu layout, nhưng không phải API application thông thường.

Cài extension nếu server có hỗ trợ và role có quyền:

```sql
CREATE EXTENSION IF NOT EXISTS pageinspect;
```

Đọc header block 0:

```sql
SELECT *
FROM page_header(
    get_raw_page('orm420.heap_demo', 'main', 0)
);
```

### 30.1. Đọc line pointers và tuple metadata

```sql
SELECT
    lp,
    lp_off,
    lp_flags,
    lp_len,
    t_xmin,
    t_xmax,
    t_ctid,
    t_hoff,
    t_infomask,
    t_infomask2
FROM heap_page_items(
    get_raw_page('orm420.heap_demo', 'main', 0)
)
ORDER BY lp;
```

### 30.2. Đọc tuple attributes

Một số phiên bản pageinspect hỗ trợ:

```sql
SELECT *
FROM heap_page_item_attrs(
    get_raw_page('orm420.heap_demo', 'main', 0),
    'orm420.heap_demo'::regclass,
    true
);
```

Hàm trả representation các attributes dưới dạng bytea array và có tùy chọn detoast. Cấu trúc output/phạm vi hỗ trợ phải kiểm tra tài liệu pageinspect của đúng server version.

### 30.3. Block 0 phải tồn tại

get_raw_page cần một block hợp lệ. Nếu relation rỗng hoặc không có block 0, câu gọi sẽ lỗi. Trong lab đã insert 300 rows nên thường có page để quan sát.

### 30.4. Quyền và an toàn

Raw page inspection có thể đọc bytes vật lý, kể cả các tuple versions không xuất hiện trong SELECT thông thường. Chỉ cấp quyền cho người vận hành/điều tra phù hợp, không cấp rộng cho application roles.

### 30.5. Không sửa raw page

pageinspect dùng để quan sát. Không tự chỉnh byte trong page để “sửa dữ liệu”; sửa raw page ngoài cơ chế PostgreSQL có thể phá cấu trúc, index, WAL consistency và làm hỏng database.

## 31. pg_freespacemap: xem free-space estimates

Nếu extension có sẵn:

```sql
CREATE EXTENSION IF NOT EXISTS pg_freespacemap;
```

Xem một số page:

```sql
SELECT
    blkno,
    avail
FROM pg_freespace('orm420.heap_demo'::regclass)
ORDER BY blkno
LIMIT 20;
```

avail là ước lượng free bytes được FSM ghi nhận. Đây không phải phép đo forensic tuyệt đối cho từng byte tại thời điểm câu SELECT.

### 31.1. FSM không đồng nghĩa free space trong page header

FSM là cấu trúc phụ quản lý ước lượng. Page header pd_lower/pd_upper phản ánh trạng thái bố cục page; fragmentation và pruning có thể làm việc diễn giải free space phức tạp hơn.

## 32. pgstattuple: ước lượng sống/chết/free space

Extension pgstattuple có thể cung cấp thống kê về tuple sống, tuple chết và free space.

```sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;

SELECT *
FROM pgstattuple('orm420.heap_demo');
```

Hàm này có thể phải đọc nhiều pages và có chi phí I/O; không chạy thường xuyên trên bảng production lớn mà không đánh giá.

### 32.1. pgstattuple_approx

Ở những phiên bản hỗ trợ, pgstattuple_approx cung cấp một cách ước lượng nhẹ hơn dựa trên metadata có sẵn và việc kiểm tra một số page.

```sql
SELECT *
FROM pgstattuple_approx('orm420.heap_demo');
```

Tên cột/chi tiết output và availability phải đối chiếu version.

### 32.2. Không có một con số bloat duy nhất

Một thống kê free_percent cao không tự động chứng minh phải chạy VACUUM FULL. Cần biết free space có được tái sử dụng không, workload sẽ INSERT/UPDATE ra sao, index có bloat không và chi phí rewrite là gì.

## 33. HOT update và fillfactor trong lab

Tạo một bảng thử nghiệm:

```sql
CREATE TABLE orm420.hot_lab (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    indexed_code integer NOT NULL,
    counter integer NOT NULL DEFAULT 0,
    description text
) WITH (fillfactor = 70);

CREATE INDEX idx_orm420_hot_code
ON orm420.hot_lab(indexed_code);

INSERT INTO orm420.hot_lab(indexed_code, description)
SELECT g, repeat('x', 100)
FROM generate_series(1, 1000) AS g;
```

Cập nhật cột không nằm trong index:

```sql
UPDATE orm420.hot_lab
SET counter = counter + 1
WHERE id BETWEEN 1 AND 500;
```

Xem thống kê:

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'orm420'
  AND relname = 'hot_lab';
```

### 33.1. Vì sao có thể có HOT?

indexed_code không thay đổi, và fillfactor chừa chỗ. Nếu tuple mới có thể nằm trên cùng page và các điều kiện khác thỏa, HOT update có thể xảy ra.

### 33.2. Thử thay indexed column

```sql
UPDATE orm420.hot_lab
SET indexed_code = indexed_code + 100000
WHERE id BETWEEN 1 AND 500;
```

Vì indexed column thay đổi, update này thường không đủ điều kiện HOT theo điều kiện index liên quan.

### 33.3. Kết quả thống kê không nhất thiết cập nhật ngay

Statistics collector/cumulative stats có cách cập nhật và reset riêng. So sánh theo thời gian, có thể cần đợi/đọc lại, và kiểm soát workload lab.

## 34. Page split của heap khác page split của B-tree

Heap page không có thứ tự khóa như B-tree. Khi page hết chỗ, PostgreSQL có thể chọn page khác theo FSM hoặc mở rộng relation.

B-tree index có cấu trúc phân cấp và có thể split page khi thêm key. Không áp dụng thuật ngữ B-tree page split để mô tả mọi việc heap relation tăng số block.

### 34.1. Heap không sắp xếp theo index

```sql
CREATE INDEX idx_products_code
ON orm420.heap_demo(code);
```

Ngay cả khi tạo index, heap table vẫn không tự sắp xếp vật lý theo code.

### 34.2. CLUSTER là thao tác rewrite có thứ tự

```sql
CLUSTER orm420.heap_demo
USING idx_products_code;
```

CLUSTER rewrite table theo thứ tự index tại thời điểm chạy và cần lock mạnh. Những INSERT/UPDATE về sau có thể làm thứ tự vật lý không còn như lúc cluster. Nó không tạo cam kết ORDER BY cho SQL queries.

## 35. Relation forks: main, FSM, VM và init

Một relation có thể có các forks:

| Fork | Vai trò |
|---|---|
| main | Nội dung chính của table/index |
| fsm | Free Space Map |
| vm | Visibility Map |
| init | Initial fork cho unlogged relations, dùng trong cơ chế khôi phục trạng thái ban đầu sau crash |

Với heap table, main fork chứa pages dữ liệu. FSM/VM chứa metadata phục vụ quản lý storage và visibility.

### 35.1. Unlogged table và init fork

Unlogged tables không được WAL-log theo cách đầy đủ như logged tables và có thể bị truncate/reset sau crash; init fork hỗ trợ khôi phục trạng thái rỗng ban đầu theo cơ chế PostgreSQL.

Không dùng unlogged table cho dữ liệu cần durability như một bảng logged thông thường.

### 35.2. Temporary tables

Temporary tables có phạm vi session/transaction tùy khai báo và được lưu trong temporary schema/backend-specific storage. Không suy luận file vật lý của chúng giống hệt một bảng permanent trong base/database_oid.

### 35.3. Partitioned table

Partitioned parent thường là relation điều phối, không phải một heap chứa toàn bộ rows. Các partitions con là những relations vật lý có pages/forks riêng. Kiểm tra tableoid và từng partition khi đo storage.

## 36. Segment và đường dẫn file vật lý

Một relation lớn có thể được chia thành nhiều segment files. Kích thước segment phổ biến mặc định là khoảng **1 GiB**, nhưng đây là implementation/build detail có thể cấu hình khác.

Có thể xem đường dẫn hiện tại:

```sql
SELECT
    'orm420.heap_demo'::regclass AS relation,
    pg_relation_filenode('orm420.heap_demo'::regclass) AS relfilenode,
    pg_relation_filepath('orm420.heap_demo'::regclass) AS file_path;
```

### 36.1. Vì sao relfilenode có thể đổi?

Các thao tác rewrite relation như VACUUM FULL, CLUSTER hoặc một số ALTER TABLE có thể tạo file relation mới và thay relfilenode.

### 36.2. Không hard-code path trong ứng dụng

Đường dẫn phụ thuộc database OID, tablespace, relfilenode, fork và segment. Dùng SQL/catalog APIs để điều tra; không lưu path như định danh bền vững.

### 36.3. Tablespace

Relation có thể nằm trong tablespace khác với mặc định. Vì vậy không luôn tìm thấy mọi relation dưới một thư mục base duy nhất.

## 37. Tuple width, row count và page density

Một bảng có 100 cột không nhất thiết chiếm cùng dung lượng với bảng 10 cột; số cột và kiểu dữ liệu chưa đủ để suy ra chính xác kích thước.

Các yếu tố:

- Tuple header.
- Null bitmap.
- Attribute alignment/padding.
- Fixed-length và variable-length values.
- TOAST compression/out-of-line.
- Line pointer overhead.
- Fillfactor.
- Dead tuple versions.
- Free space và fragmentation.

### 37.1. Ước lượng đơn giản

Một mô hình khái quát:

```text
page footprint
  ~= page header
   + line pointer array
   + tuple headers
   + null bitmaps
   + aligned attribute data
   + free space
   + special area (nếu access method dùng)
```

Không dùng phép tính này như công thức thay thế pg_relation_size hoặc page inspection.

### 37.2. So sánh hai kiểu dữ liệu

Một bigint có fixed-width 8 bytes ở mức giá trị, nhưng tuple còn header/alignment/line pointer. Một text ngắn có varlena header và có thể dùng short representation. Một text dài có thể TOAST.

### 37.3. Không tách bảng chỉ vì “nhiều cột chắc chậm”

Vertical partitioning có thể giảm heap width cho query phổ biến nhưng thêm joins, transaction consistency và complexity. Quyết định dựa trên access patterns và đo thực tế.

## 38. UPDATE cột nhỏ nhưng tuple lớn

Nếu một bảng chứa JSON/text lớn và thường xuyên cập nhật một cột nhỏ:

- PostgreSQL tạo tuple version mới theo MVCC.
- Các thuộc tính lớn có thể được TOAST/compress hoặc pointer được giữ tùy semantics.
- HOT eligibility phụ thuộc index changes và free space.
- WAL và page churn có thể tăng.
- Indexes có thể nhận entries mới nếu update không HOT.

Vì vậy thiết kế bảng có nhiều trường lớn và trường thường xuyên thay đổi cần được đánh giá theo workload.

### 38.1. Tách metadata và payload?

Một số hệ thống tách payload lớn sang bảng riêng để metadata updates ít gây churn ở bảng chính. Nhưng việc tách tạo join và consistency overhead. Không có quy tắc luôn tách blob.

### 38.2. JSONB có thể có TOAST và index riêng

JSONB lớn có thể TOAST. GIN index trên JSONB lại có cấu trúc/index storage riêng, có thể tăng đáng kể tổng footprint. Đo pg_table_size, pg_indexes_size, pg_total_relation_size.

## 39. VACUUM, REINDEX và CLUSTER: không nhầm mục đích

| Lệnh | Tác dụng chính | Tác động/giới hạn |
|---|---|---|
| VACUUM | Thu hồi tuple dead để tái sử dụng, cập nhật FSM/VM, freeze | Thường không rewrite toàn bộ table |
| VACUUM FULL | Rewrite/compact table, thu hồi file space | Lock mạnh, I/O và dung lượng tạm |
| ANALYZE | Cập nhật statistics cho planner | Không compact table |
| REINDEX | Xây lại index | Không tự compact heap table |
| CLUSTER | Rewrite table theo index order | Lock mạnh; thứ tự vật lý có thể trôi theo DML sau đó |

### 39.1. REINDEX không sửa heap bloat

Nếu heap có nhiều dead tuples/free space, REINDEX chỉ xây lại index. Cần xác định đúng thành phần đang phình.

### 39.2. ANALYZE không dọn tuple

ANALYZE thu thập thống kê phân bố dữ liệu cho planner, không phải vacuum.

### 39.3. Không chạy tất cả lệnh maintenance theo phản xạ

Mỗi lệnh có lock, I/O, WAL và ảnh hưởng availability khác nhau. Kiểm tra mục tiêu và trạng thái hệ thống trước.

## 40. WAL, page LSN và durability

PostgreSQL sử dụng Write-Ahead Logging: thay đổi cần được ghi vào WAL theo thứ tự phù hợp trước khi data pages tương ứng được ghi bền vững.

Sơ đồ đơn giản:

```text
SQL UPDATE
   |
   v
Heap tuple/page change trong buffer
   |
   +--> WAL record được tạo
   |        |
   |        v
   |     WAL flush theo commit/durability settings
   |
   v
Data page có thể được ghi xuống storage sau
```

### 40.1. pd_lsn

Page LSN giúp recovery xác định WAL records đã được phản ánh vào page. Nó không phải một trường business và không nên dùng để xác định thứ tự đơn hàng.

### 40.2. Full-page writes

Trong những điều kiện phù hợp, PostgreSQL có thể ghi full-page images vào WAL để hỗ trợ phục hồi page sau partial page writes. Đây là một phần của WAL/recovery design, không phải backup đầy đủ thay thế.

### 40.3. Page checksums

Checksum giúp phát hiện một số hư hỏng page nếu được bật. Nó không mã hóa dữ liệu và không thay thế backup, replication hoặc restore testing.

### 40.4. fsync và durability

Các cấu hình durability như fsync, synchronous_commit và storage guarantees ảnh hưởng thời điểm xác nhận commit. Không thay đổi chúng chỉ để giảm latency mà chưa hiểu risk mất dữ liệu.

## 41. Heap page và index-only scan: lab EXPLAIN

Tạo index cho cột cần truy vấn:

```sql
CREATE INDEX idx_orm420_heap_demo_code
ON orm420.heap_demo(code);
```

Chạy:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT code
FROM orm420.heap_demo
WHERE code BETWEEN 100 AND 150;
```

### 41.1. Tại sao có thể thấy Index Scan?

Planner có thể dùng index để tìm TIDs rồi fetch heap tuples.

### 41.2. Tại sao có thể thấy Index Only Scan?

Nếu index chứa đủ cột cần và page all-visible theo VM, executor có thể tránh heap fetch cho nhiều rows.

### 41.3. Heap Fetches

Nếu plan có Index Only Scan, xem Heap Fetches. Con số lớn cho thấy executor vẫn cần truy cập heap để kiểm tra visibility ở một số trường hợp.

### 41.4. ANALYZE và VACUUM có thể ảnh hưởng plan

Statistics và visibility map thay đổi theo workload/maintenance. Không ép planner bằng hint không có sẵn trong PostgreSQL core; kiểm tra schema/index/stats trước.

## 42. Quan sát TOAST và relation size tổng thể

Query tổng hợp:

```sql
SELECT
    c.oid::regclass AS relation,
    c.reltoastrelid::regclass AS toast_relation,
    pg_size_pretty(pg_relation_size(c.oid, 'main')) AS main_fork,
    pg_size_pretty(pg_relation_size(c.oid, 'fsm')) AS fsm_fork,
    pg_size_pretty(pg_relation_size(c.oid, 'vm')) AS vm_fork,
    pg_size_pretty(pg_table_size(c.oid)) AS table_size,
    pg_size_pretty(pg_indexes_size(c.oid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
WHERE c.oid = 'orm420.toast_demo'::regclass;
```

Kết quả giúp thấy các thành phần theo những hàm size khác nhau. Các fork phụ có thể chưa tồn tại hoặc có size 0.

### 42.1. TOAST index

TOAST relation có index riêng để tìm các chunks theo value/chunk sequence. pg_total_relation_size tính phần storage liên quan của TOAST theo semantics của hàm.

### 42.2. Index size không phải tuple payload size

Một index có thể chiếm nhiều dung lượng hơn dự đoán vì key width, tuple overhead, page fill, bloat và số entries. Đo riêng thay vì cộng tay từ column sizes.

## 43. Bảo trì và điều tra storage trên production

Khi một bảng lớn bất thường, điều tra theo trình tự:

1. Đọc pg_relation_size, pg_table_size, pg_indexes_size, pg_total_relation_size.
2. Xác định table có TOAST relation/partition không.
3. Xem row estimates, dead tuples và vacuum timestamps.
4. Xem transaction age, replication slots và xmin horizons nếu vacuum không thu hồi được.
5. Dùng pgstattuple/pgstattuple_approx nếu quyền và chi phí cho phép.
6. Kiểm tra indexes riêng.
7. Xem update/delete churn, HOT ratio và fillfactor.
8. Kiểm tra các query plan thực tế.
9. Lập kế hoạch maintenance với lock/I/O/storage budget.
10. Theo dõi sau khi thực hiện.

### 43.1. Không chạy pageinspect tùy tiện trên mọi bảng

Raw page inspection là công cụ chuyên sâu. Với câu hỏi kích thước, bắt đầu bằng pg_relation_size/catalog. Với câu hỏi tuple/page layout, dùng pageinspect trên môi trường lab hoặc điều tra được cấp quyền.

### 43.2. Không copy raw page ra nơi không kiểm soát

Raw page có thể chứa dữ liệu nhạy cảm, tuple versions cũ hoặc bytes chưa hiển thị trong SELECT. Xử lý output như dữ liệu production nhạy cảm.

### 43.3. Long transaction là dấu hiệu cần điều tra

Một transaction lâu có thể giữ tuple versions cũ cần thiết, làm VACUUM không thu hồi được. Kiểm tra pg_stat_activity, replication slots và các transaction horizons trước khi tăng autovacuum workers vô điều kiện.

## 44. Những hiểu lầm phổ biến

### Hiểu lầm 1 — Heap tự sắp xếp theo primary key

Không. Heap không bảo đảm thứ tự; dùng ORDER BY.

### Hiểu lầm 2 — Một row luôn tương ứng một tuple vật lý

Không. MVCC có nhiều tuple versions cho một row logic qua INSERT/UPDATE/DELETE.

### Hiểu lầm 3 — UPDATE ghi đè tuple tại chỗ

Không nên giả định như vậy. UPDATE thường tạo tuple version mới; HOT là một tối ưu có điều kiện.

### Hiểu lầm 4 — DELETE lập tức giải phóng file bytes

Không. Tuple có thể trở thành dead và chờ pruning/VACUUM.

### Hiểu lầm 5 — VACUUM luôn làm file nhỏ đi

Không. VACUUM thường giúp tái sử dụng free space; VACUUM FULL rewrite để reclaim space với lock/chi phí cao.

### Hiểu lầm 6 — ctid là primary key tốt

Không. ctid có thể thay đổi sau UPDATE/rewrite và chỉ có ý nghĩa vật lý.

### Hiểu lầm 7 — xmin là created_at

Không. xmin là transaction ID, không phải timestamp.

### Hiểu lầm 8 — xmax khác 0 nghĩa tuple chắc chắn đã bị xóa

Không. xmax còn có các trạng thái khóa/MultiXact theo implementation.

### Hiểu lầm 9 — Page có 8KB nên mọi tuple đều có thể chiếm 8KB

Không. Còn page header, line pointers, free space, alignment và các giới hạn lưu tuple/TOAST.

### Hiểu lầm 10 — TOAST chỉ là nén

Không. TOAST có thể nén và/hoặc lưu out-of-line theo storage strategy.

### Hiểu lầm 11 — TOAST và Large Objects là một

Không. Đây là hai cơ chế khác nhau.

### Hiểu lầm 12 — FSM cho biết free bytes tuyệt đối chính xác

Không. FSM là metadata ước lượng để hỗ trợ chọn page.

### Hiểu lầm 13 — VM lưu các giá trị hàng

Không. VM lưu trạng thái visibility/frozen theo page.

### Hiểu lầm 14 — Index-only scan không đọc heap trong mọi trường hợp

Không. Nếu VM không all-visible, heap fetch vẫn có thể cần thiết.

### Hiểu lầm 15 — HOT xảy ra với mọi UPDATE không đổi primary key

Không. Phải xét mọi indexed columns/expressions/predicates và free space cùng các điều kiện khác.

### Hiểu lầm 16 — Fillfactor thấp luôn nhanh hơn

Không. Nó tăng page count/storage/cache footprint; phải đo theo workload.

### Hiểu lầm 17 — Tạo index làm heap được sắp xếp

Không. Index là cấu trúc riêng trỏ tới heap TIDs.

### Hiểu lầm 18 — CLUSTER giữ thứ tự vĩnh viễn

Không. DML về sau có thể làm thứ tự vật lý thay đổi.

### Hiểu lầm 19 — pg_relation_size là tổng mọi thứ

Không. Nó mặc định đo main fork của relation; dùng table/index/total size functions phù hợp.

### Hiểu lầm 20 — pg_column_size bằng octet_length

Không phải lúc nào cũng vậy; TOAST/compression/representation ảnh hưởng.

### Hiểu lầm 21 — Một bảng partitioned parent có toàn bộ heap pages

Không nhất thiết. Các partition con thường là relation vật lý riêng.

### Hiểu lầm 22 — Page checksum mã hóa page

Không. Checksum hỗ trợ phát hiện corruption, không confidentiality.

### Hiểu lầm 23 — Bật autovacuum là không còn dead tuples

Không. Snapshot horizons, replication slots, thresholds và workload có thể trì hoãn cleanup.

### Hiểu lầm 24 — REINDEX dọn heap bloat

Không. REINDEX xây lại index, không compact heap table.

### Hiểu lầm 25 — ANALYZE thu hồi tuple chết

Không. ANALYZE cập nhật planner statistics.

### Hiểu lầm 26 — Có thể lưu ctid để tham chiếu row qua nhiều lần chạy

Không. Dùng primary key/business key ổn định.

### Hiểu lầm 27 — Raw page output không nhạy cảm vì không phải SELECT bình thường

Sai. Nó có thể chứa dữ liệu cũ và bytes nhạy cảm; bảo vệ output như dữ liệu database.

## 45. Bài tập có đáp án

### Bài 1. Heap là gì?

**Đáp án:** Cấu trúc relation lưu tuple trên các pages, không đảm bảo thứ tự hàng theo primary key hay thứ tự INSERT.

### Bài 2. Block size phổ biến của PostgreSQL là bao nhiêu?

**Đáp án:** 8 KiB (8192 bytes) trong bản build phổ biến; kiểm tra bằng SHOW block_size.

### Bài 3. Có thể đổi block size cho một bảng bằng ALTER TABLE không?

**Đáp án:** Không. Đây là đặc tính build/server, không phải setting riêng của table.

### Bài 4. Page có những vùng chính nào?

**Đáp án:** Page header, line pointer array, free space và tuple area; special space có thể có ở access methods dùng nó, heap page thông thường không cần.

### Bài 5. Line pointer thường chiếm bao nhiêu bytes?

**Đáp án:** 4 bytes trong layout thông dụng.

### Bài 6. TID gồm những gì?

**Đáp án:** Block number và offset number của line pointer trong block.

### Bài 7. TID offset có phải byte offset của tuple không?

**Đáp án:** Không. Nó là số slot line pointer.

### Bài 8. Vì sao page cần line pointers?

**Đáp án:** Cho phép tham chiếu tuple qua slot trong khi tuple bytes có thể được di chuyển/compact trong page.

### Bài 9. pd_lower và pd_upper mô tả gì?

**Đáp án:** Ranh giới line pointer array và tuple/free-space region theo page layout.

### Bài 10. pd_lsn liên quan đến gì?

**Đáp án:** WAL LSN liên quan gần nhất được áp dụng cho page.

### Bài 11. Page checksum có mã hóa dữ liệu không?

**Đáp án:** Không. Nó hỗ trợ phát hiện một số corruption.

### Bài 12. Tuple version là gì?

**Đáp án:** Một phiên bản vật lý của hàng trong MVCC, có metadata transaction và attribute data.

### Bài 13. xmin thường biểu diễn gì?

**Đáp án:** Transaction ID tạo tuple version.

### Bài 14. xmax luôn là transaction xóa hàng?

**Đáp án:** Không. Nó còn có thể biểu diễn thông tin lock/MultiXact theo trạng thái tuple.

### Bài 15. ctid có dạng nào?

**Đáp án:** (block_number, offset_number).

### Bài 16. ctid có phù hợp làm khóa chính không?

**Đáp án:** Không. Nó có thể thay đổi sau UPDATE/rewrite.

### Bài 17. UPDATE thường làm gì với tuple cũ?

**Đáp án:** Tạo tuple version mới và đánh dấu phiên bản cũ theo MVCC; cleanup diễn ra sau khi an toàn.

### Bài 18. DELETE có lập tức xóa bytes vật lý không?

**Đáp án:** Không. Tuple có thể dead nhưng chờ pruning/VACUUM.

### Bài 19. Null bitmap dùng để làm gì?

**Đáp án:** Ghi trạng thái NULL của attributes; NULL không phải empty string hoặc giá trị zero bytes thông thường.

### Bài 20. Vì sao tuple size lớn hơn tổng payload cột?

**Đáp án:** Có tuple header, line pointer, null bitmap, alignment/padding và cấu trúc TOAST/varlena.

### Bài 21. TOAST giải quyết vấn đề gì?

**Đáp án:** Nén và/hoặc lưu out-of-line các giá trị varlena lớn để tuple/page chính phù hợp hơn.

### Bài 22. TOAST có giống Large Objects không?

**Đáp án:** Không. Large Objects có API và cơ chế riêng.

### Bài 23. PLAIN storage strategy làm gì?

**Đáp án:** Không nén và không lưu out-of-line.

### Bài 24. EXTENDED có ý nghĩa gì?

**Đáp án:** Có thể nén và lưu out-of-line khi cần.

### Bài 25. FSM và VM khác nhau thế nào?

**Đáp án:** FSM ghi nhận free-space estimates; VM ghi trạng thái all-visible/all-frozen theo page.

### Bài 26. Index-only scan dùng VM để làm gì?

**Đáp án:** Nếu heap page all-visible, có thể bỏ qua heap visibility check và giảm heap fetch.

### Bài 27. HOT update cần những điều kiện quan trọng nào?

**Đáp án:** Các cột được index không thay đổi theo điều kiện liên quan và có đủ free space trên cùng page, cùng các điều kiện implementation khác.

### Bài 28. Fillfactor 70 có nghĩa gì?

**Đáp án:** Mục tiêu lấp đầy page ở mức thấp hơn để chừa không gian cho workload phù hợp; không phải giới hạn tuple size hay bảo đảm HOT.

### Bài 29. VACUUM thường có làm file nhỏ đi không?

**Đáp án:** Thường không rewrite toàn bộ table; nó chủ yếu giúp tái sử dụng space và cập nhật FSM/VM. Một số trailing empty pages có thể được truncate khi điều kiện cho phép.

### Bài 30. VACUUM FULL khác gì?

**Đáp án:** Rewrite/compact relation, có thể trả space cho filesystem nhưng cần lock mạnh và chi phí I/O/dung lượng tạm.

### Bài 31. Long transaction ảnh hưởng VACUUM thế nào?

**Đáp án:** Có thể giữ snapshot cũ, làm tuple versions chưa đủ điều kiện thu hồi.

### Bài 32. Autovacuum có luôn xóa mọi dead tuple ngay lập tức?

**Đáp án:** Không. Nó phụ thuộc thresholds, worker capacity, transaction horizons, replication và workload.

### Bài 33. Freeze có nghĩa row không được UPDATE nữa?

**Đáp án:** Không. Freeze liên quan transaction ID visibility, không phải business immutability.

### Bài 34. pg_relation_size(table) mặc định đo gì?

**Đáp án:** Main fork của relation.

### Bài 35. pg_total_relation_size bao gồm gì?

**Đáp án:** Table storage, indexes và thành phần TOAST liên quan theo semantics hàm.

### Bài 36. pg_column_size luôn bằng octet_length không?

**Đáp án:** Không. Representation, compression và TOAST có thể khiến khác nhau.

### Bài 37. Dùng extension nào để đọc heap page raw?

**Đáp án:** pageinspect, với quyền và hỗ trợ phù hợp.

### Bài 38. heap_page_items cho thông tin gì?

**Đáp án:** Line pointers và tuple metadata như xmin/xmax/ctid/infomask theo output của extension.

### Bài 39. pgstattuple dùng làm gì?

**Đáp án:** Thống kê tuple live/dead và free space; có thể tốn I/O do phải quét relation.

### Bài 40. Heap page split giống B-tree page split không?

**Đáp án:** Không. Heap không có cấu trúc sắp xếp key như B-tree; khi hết chỗ nó tìm page khác hoặc mở rộng relation.

### Bài 41. CLUSTER có bảo đảm thứ tự SELECT về sau?

**Đáp án:** Không. Nó rewrite theo index order tại thời điểm chạy; query vẫn cần ORDER BY.

### Bài 42. REINDEX có compact heap không?

**Đáp án:** Không. Nó xây lại index.

### Bài 43. Một partitioned table lưu rows ở đâu?

**Đáp án:** Thường ở các partition con là relations vật lý riêng; parent chủ yếu là relation điều phối.

### Bài 44. Page LSN có phải timestamp không?

**Đáp án:** Không. Nó là Log Sequence Number trong WAL.

### Bài 45. Có nên chỉnh bytes trực tiếp bằng pageinspect để sửa row?

**Đáp án:** Không. pageinspect là công cụ quan sát; raw page mutation có thể phá database.

## 46. Checklist khi điều tra heap/table storage

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Đây là heap table hay relation khác? | pg_class.relkind, partitioning |
| Block size server là bao nhiêu? | SHOW block_size |
| Main fork chiếm bao nhiêu? | pg_relation_size |
| FSM/VM có kích thước nào? | pg_relation_size(..., 'fsm'/'vm') |
| Có TOAST relation không? | pg_class.reltoastrelid |
| Indexes chiếm bao nhiêu? | pg_indexes_size |
| Tổng footprint bao nhiêu? | pg_total_relation_size |
| File path/relfilenode hiện tại? | pg_relation_filepath, pg_relation_filenode |
| Dead tuple estimates ra sao? | pg_stat_user_tables |
| Autovacuum gần nhất khi nào? | last_autovacuum/last_autoanalyze |
| Có long transactions không? | pg_stat_activity |
| Replication slot giữ horizon không? | replication slot monitoring |
| HOT ratio ra sao? | n_tup_hot_upd / n_tup_upd |
| Fillfactor hiện tại? | pg_class.reloptions/table options |
| Tuple có TOAST values lớn? | pg_column_size, TOAST relation |
| Có page-level evidence cần xem? | pageinspect trên page phù hợp |
| Có bloat thật sự? | pgstattuple/ước lượng và workload |
| Index-only scan có heap fetch? | EXPLAIN (ANALYZE, BUFFERS) |
| Cần VACUUM hay VACUUM FULL? | Reuse space vs reclaim filesystem |
| Có đủ disk headroom cho rewrite? | Storage budget |
| Lock impact của maintenance? | Access pattern, lock plan |
| Có dữ liệu nhạy cảm trong raw page output? | Quyền, lưu trữ output |

## 47. Tài liệu PostgreSQL chính thức

- [Database Physical Storage](https://www.postgresql.org/docs/current/storage.html) — file/fork/segment và layout tổng thể.
- [Database Page Layout](https://www.postgresql.org/docs/current/storage-page-layout.html) — page header, line pointers và tuple area.
- [Heap-Only Tuples (HOT)](https://www.postgresql.org/docs/current/storage-hot.html) — HOT updates và index maintenance.
- [TOAST](https://www.postgresql.org/docs/current/storage-toast.html) — oversized attributes, compression và out-of-line storage.
- [MVCC Introduction](https://www.postgresql.org/docs/current/mvcc-intro.html) — multi-version concurrency control.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — VACUUM, ANALYZE, freezing và autovacuum.
- [Visibility Map](https://www.postgresql.org/docs/current/storage-vm.html) — all-visible/all-frozen và index-only scans.
- [Free Space Map](https://www.postgresql.org/docs/current/storage-fsm.html) — quản lý free space.
- [System Columns](https://www.postgresql.org/docs/current/ddl-system-columns.html) — ctid, xmin, xmax, tableoid.
- [pageinspect](https://www.postgresql.org/docs/current/pageinspect.html) — raw page inspection.
- [pgstattuple](https://www.postgresql.org/docs/current/pgstattuple.html) — tuple/free-space statistics.
- [pg_freespacemap](https://www.postgresql.org/docs/current/pgfreespacemap.html) — FSM inspection.
- [Database File Layout](https://www.postgresql.org/docs/current/storage-file-layout.html) — mapping relation files.
- [WAL Introduction](https://www.postgresql.org/docs/current/wal-intro.html) — Write-Ahead Logging và recovery.

Chi tiết physical layout là implementation detail và có thể thay đổi theo phiên bản/build. Khi viết công cụ đọc page hoặc thực hiện forensic, hãy dùng tài liệu đúng phiên bản và không giả định mọi release có cấu trúc byte giống nhau.

## 48. Tổng kết

Heap relation của PostgreSQL là tập các pages chứa tuple versions. Một page có header, line pointer array, free space và tuple data. Tuple mang metadata MVCC và các giá trị thuộc tính; giá trị lớn có thể được TOAST; index dùng TID để định vị tuple.

```text
Table / Heap relation
   |
   +-- Main fork
   |     |
   |     +-- Page header
   |     +-- Line pointers
   |     +-- Free space
   |     +-- Tuple versions
   |             |
   |             +-- xmin / xmax / ctid
   |             +-- null bitmap / alignment
   |             +-- attribute data / TOAST pointers
   |
   +-- FSM -> free-space estimates
   |
   +-- VM  -> all-visible / all-frozen
   |
   +-- TOAST relation -> large values/chunks
   |
   +-- Indexes -> keys and heap TIDs
```

Những điều quan trọng nhất:

1. **Heap không bảo đảm thứ tự hàng.** Luôn dùng ORDER BY khi thứ tự có ý nghĩa.
2. **Page là đơn vị lưu trữ cơ bản.** 8 KiB là mặc định phổ biến; kiểm tra block_size của server.
3. **Line pointer là slot tham chiếu tuple.** TID dùng block và offset number, không phải byte offset.
4. **Tuple là phiên bản hàng vật lý.** MVCC cho phép nhiều versions cùng tồn tại.
5. **xmin, xmax, ctid là metadata nội bộ.** Không dùng thay khóa chính hoặc audit timestamp.
6. **UPDATE/DELETE không lập tức thu hồi bytes.** Pruning/VACUUM thu hồi khi snapshot không còn cần.
7. **TOAST xử lý giá trị varlena lớn.** TOAST không phải Large Objects.
8. **FSM và VM có mục đích khác nhau.** FSM hỗ trợ tìm free space; VM hỗ trợ visibility/freeze và index-only scans.
9. **HOT update phụ thuộc index changes và free space.** Fillfactor có thể giúp nhưng không bảo đảm HOT.
10. **VACUUM thường tạo space có thể tái sử dụng.** VACUUM FULL rewrite để reclaim file space với lock và chi phí lớn.
11. **Index trỏ tới heap TID.** Index-only scan chỉ giảm heap fetch khi các điều kiện, đặc biệt VM visibility, phù hợp.
12. **Đo đúng thành phần storage.** Phân biệt main fork, table size, indexes, TOAST và total size.
13. **Page inspection là công cụ chuyên sâu.** pageinspect, pgstattuple và FSM functions cần quyền, chi phí và xử lý output phù hợp.
14. **WAL/page LSN/checksum phục vụ durability và integrity.** Checksum không phải encryption.
15. **Storage maintenance phải dựa trên workload.** Đánh giá dead tuples, long transactions, HOT ratio, bloat, locks và disk headroom trước khi rewrite.

**Một câu để nhớ:** *Heap là nơi PostgreSQL giữ các phiên bản hàng trên những page; line pointers định vị tuple, MVCC quyết định phiên bản nào nhìn thấy được, TOAST xử lý giá trị lớn, còn FSM/VM/VACUUM giúp quản lý không gian và visibility theo thời gian.*

