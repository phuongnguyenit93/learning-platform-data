# Quan hệ giữa kích thước bảng, chỉ mục và dữ liệu TOAST trong PostgreSQL

Một bảng PostgreSQL có 2 triệu hàng không nhất thiết lớn gấp đôi bảng 1 triệu hàng. Hai bảng có cùng số hàng cũng có thể chênh nhau hàng chục lần về dung lượng. Bảng chỉ chứa vài cột số nguyên có thể nhỏ hơn nhiều so với bảng lưu văn bản dài, JSONB, mảng hoặc bytea. Khi cộng thêm chỉ mục, dữ liệu TOAST, free space, dead tuples và các cấu trúc phụ trợ, con số “kích thước bảng” có thể khác xa kích thước dữ liệu nghiệp vụ mà ứng dụng tưởng mình đang lưu.

PostgreSQL lưu bảng, chỉ mục và dữ liệu lớn theo các **relation** vật lý riêng. Một số hàm đo dung lượng thường dùng:

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('public.orders')) AS heap_main,
    pg_size_pretty(pg_table_size('public.orders')) AS table_storage,
    pg_size_pretty(pg_indexes_size('public.orders')) AS indexes,
    pg_size_pretty(pg_total_relation_size('public.orders')) AS total;
~~~

Để hiểu đúng kết quả, cần phân biệt:

- **Heap/table relation:** các page lưu tuple của bảng.
- **Index relations:** các cấu trúc B-tree, GIN, GiST, BRIN hoặc loại index khác.
- **TOAST relation:** nơi PostgreSQL lưu các giá trị biến độ dài quá lớn để đặt trực tiếp trong tuple heap.
- **TOAST index:** chỉ mục nội bộ giúp tìm các chunk của giá trị TOAST.
- **Auxiliary forks:** Free Space Map (FSM), Visibility Map (VM) và init fork trong trường hợp phù hợp.

~~~text
                Một bảng PostgreSQL
                       |
        +--------------+---------------+
        |              |               |
        v              v               v
   Heap relation   Index relations   TOAST relation
   - tuple/page    - B-tree           - chunk dữ liệu lớn
   - MVCC version  - GIN/GiST...      - TOAST index
        |              |               |
        +--------------+---------------+
                       |
                 Tổng dung lượng
           heap + forks + indexes + TOAST
~~~

**Điểm cốt lõi:** **pg_relation_size()** mặc định đo main fork của một relation; **pg_table_size()** đo phần lưu trữ của bảng cùng TOAST và các fork phụ trợ; **pg_indexes_size()** đo các chỉ mục gắn với bảng; **pg_total_relation_size()** tổng hợp phần bảng và các chỉ mục. Muốn chẩn đoán tăng dung lượng, phải xem từng thành phần thay vì chỉ nhìn một con số tổng.

Bài này thuộc chương **Lưu trữ** của module *Database Engine Relational PostgreSQL*, tập trung vào quan hệ giữa kích thước heap, index và TOAST, cách PostgreSQL tổ chức page/tuple, cách đo bằng SQL, cách đọc catalog, và tác động của update, vacuum, index maintenance, partitioning cũng như kiểu dữ liệu lớn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt kích thước logic của dữ liệu với kích thước vật lý trên đĩa.
2. Giải thích vì sao số hàng không quyết định trực tiếp dung lượng relation.
3. Mô tả quan hệ giữa heap, indexes, TOAST table, TOAST index và các forks phụ trợ.
4. Dùng các hàm pg_relation_size, pg_table_size, pg_indexes_size và pg_total_relation_size đúng mục đích.
5. Đo dung lượng từng index và từng TOAST relation.
6. Hiểu page, tuple header, line pointer, alignment, MVCC và dead tuples ảnh hưởng kích thước thế nào.
7. Giải thích vì sao giá trị text, bytea, jsonb, array hoặc kiểu varlena khác có thể được nén/đẩy ra TOAST.
8. Phân biệt các chiến lược lưu trữ PLAIN, MAIN, EXTERNAL và EXTENDED.
9. Kiểm tra cột có bật TOAST storage và compression bằng catalog.
10. Đọc kích thước heap/index/TOAST qua một lab có dữ liệu thực tế.
11. Hiểu tại sao index có thể lớn hơn heap và vì sao một bảng nhiều index làm tăng chi phí ghi.
12. Hiểu VACUUM, VACUUM FULL, REINDEX, ANALYZE có tác động khác nhau tới dung lượng.
13. Phân tích table bloat, index bloat, TOAST growth và dead tuples mà không nhầm chúng với dữ liệu sống.
14. Đo tổng dung lượng các partition và tránh đếm sai parent partitioned table.
15. Sử dụng pg_stat_user_tables, pg_statio_user_tables, pg_indexes, pg_class và extension thống kê phù hợp.
16. Đưa ra quyết định lưu trữ dựa trên đo lường thay vì suy luận từ số lượng hàng.

## 2. Logical data và physical storage

Giả sử bảng có:

~~~sql
CREATE TABLE app.documents (
    document_id bigint PRIMARY KEY,
    title text NOT NULL,
    body text,
    metadata jsonb,
    attachment bytea
);
~~~

Một hàng logic có năm trường, nhưng PostgreSQL không nhất thiết lưu tất cả bytes của body, metadata và attachment ngay trong page heap của bảng.

### 2.1. Kích thước logic

Kích thước logic mô tả nội dung ứng dụng quan tâm, chẳng hạn:

- Số ký tự của một chuỗi.
- Số byte của nội dung văn bản UTF-8.
- Số byte payload file.
- Số phần tử trong JSON/array.
- Số lượng hàng và cột.

Các đại lượng như length(text), octet_length(text) hoặc kích thước file nguồn không bao gồm đầy đủ overhead vật lý PostgreSQL.

### 2.2. Kích thước vật lý

Kích thước vật lý là dung lượng các relation/forks mà PostgreSQL dùng để lưu:

- Heap pages và tuple metadata.
- Index pages.
- TOAST chunks và TOAST index.
- Free Space Map và Visibility Map.
- Khoảng trống còn lại trong page.
- Dead tuples chưa được thu hồi/tái sử dụng.

### 2.3. WAL không nằm trong kích thước relation

Write-Ahead Log (WAL) là luồng log riêng trong thư mục pg_wal, không phải phần của pg_total_relation_size('table'). Replication slots, archived WAL, temporary files và backup storage cũng là các hạng mục riêng.

### 2.4. Kích thước database khác tổng kích thước một bảng

pg_database_size() đo dung lượng database theo cách PostgreSQL tính, bao gồm nhiều relation trong database. Một báo cáo bảng riêng không bao gồm mọi schema, catalog, temporary files hay WAL.

### 2.5. Cùng số hàng nhưng kích thước khác nhau

| Bảng | Dữ liệu mỗi hàng | Số index | Kết quả có thể gặp |
| --- | --- | ---: | --- |
| events_small | vài số nguyên và timestamp | 1 | Heap nhỏ, index nhỏ |
| articles | tiêu đề và body dài | 2 | Có TOAST, heap/index lớn hơn |
| files | metadata và bytea | 1 | TOAST có thể chiếm phần lớn |
| search_documents | text/JSONB, nhiều GIN indexes | 4 | Index có thể lớn hơn heap |

## 3. Relation và các thành phần vật lý

Trong PostgreSQL, bảng và index đều là **relation**. Một relation thường được lưu thành một hoặc nhiều file segment trong thư mục dữ liệu.

### 3.1. Heap relation

Heap là nơi lưu các tuple của bảng thông thường. Tên “heap” phản ánh cách tổ chức các tuple không được sắp xếp vật lý theo một thứ tự khóa index cố định.

### 3.2. Index relation

Mỗi index là một relation riêng. Một bảng có thể có nhiều index, và mỗi index cần lưu cấu trúc riêng để tra cứu.

### 3.3. TOAST relation

Khi một row quá lớn để lưu thuận tiện trong page heap, PostgreSQL có thể nén hoặc lưu ngoài các giá trị varlena trong một TOAST relation phụ.

### 3.4. TOAST index

TOAST relation có index nội bộ để tìm các chunk của một giá trị lớn. Đây là index phục vụ cơ chế lưu trữ TOAST, không phải index nghiệp vụ mà ứng dụng tự tạo.

### 3.5. Auxiliary forks

Một relation có thể có các fork ngoài main:

- **fsm:** Free Space Map, ghi nhận ước lượng page còn chỗ trống.
- **vm:** Visibility Map, ghi nhận page có thể được xem là all-visible/all-frozen theo trạng thái tương ứng.
- **init:** init fork dùng với unlogged relation để khôi phục nội dung khởi tạo sau crash.

Không phải mọi relation đều có đủ các fork ở mọi thời điểm.

## 4. Page, block và tuple

PostgreSQL tổ chức heap thành các **page** có kích thước cố định. Kích thước block phổ biến là 8 KiB, nhưng đây là tham số build (BLCKSZ) và không nên hardcode trong mọi công cụ.

~~~text
Một heap page (mô hình giản lược)
+------------------------------------------------+
| PageHeaderData                                 |
+------------------------------------------------+
| ItemId / line pointer array                    |
|   -> vị trí và độ dài tuple                    |
+------------------------------------------------+
|                                                |
| Tuple data                                     |
|   tuple header + null bitmap + column values   |
|                                                |
|                 free space                     |
|                                                |
+------------------------------------------------+
| Special space (tùy loại relation)              |
+------------------------------------------------+
~~~

### 4.1. Page header

Mỗi page có metadata để PostgreSQL quản lý vị trí tuple, trạng thái page và các cấu trúc khác. Phần này không phải payload ứng dụng.

### 4.2. Line pointers

Mỗi tuple được tham chiếu thông qua một item identifier/line pointer trong page. Dù tuple bị xóa logic, line pointer và khoảng trống vật lý có thể vẫn tồn tại cho đến khi cleanup/reuse phù hợp.

### 4.3. Tuple header

Tuple header chứa metadata MVCC như transaction IDs, flags và thông tin null. Bảng có nhiều cột nullable có thể cần null bitmap; mỗi row còn chịu overhead alignment.

### 4.4. Alignment và padding

Các kiểu dữ liệu có yêu cầu alignment khác nhau. PostgreSQL có thể chèn padding giữa các trường; vì vậy tổng độ dài giá trị logic không bằng chính xác độ dài tuple.

### 4.5. Free space trong page

Một page không nhất thiết đầy kín tuple. Khoảng trống hỗ trợ INSERT/UPDATE và được quản lý qua FSM/heap page metadata.

### 4.6. Fillfactor

Fillfactor của bảng điều chỉnh mức độ lấp đầy mục tiêu khi tạo/ghi page. Ví dụ fillfactor thấp hơn có thể để lại chỗ cho HOT updates, nhưng đổi lại heap ban đầu có thể cần nhiều page hơn.

~~~sql
CREATE TABLE app.events (
    event_id bigint,
    payload text
) WITH (fillfactor = 80);
~~~

Fillfactor là một công cụ tối ưu theo workload, không phải cách tự động giảm dung lượng.

## 5. MVCC làm kích thước thay đổi

PostgreSQL dùng Multi-Version Concurrency Control (MVCC). UPDATE thường tạo phiên bản tuple mới; DELETE đánh dấu phiên bản hiện tại không còn sống đối với các snapshot tương lai.

### 5.1. UPDATE không luôn ghi đè tuple cũ tại chỗ

~~~sql
UPDATE app.documents
SET title = 'New title'
WHERE document_id = 100;
~~~

PostgreSQL tạo phiên bản mới phù hợp với MVCC. Tuple cũ có thể tiếp tục tồn tại để transaction/snapshot khác nhìn thấy cho tới khi không còn cần thiết.

### 5.2. Dead tuples

Tuple cũ không còn visible với bất kỳ snapshot nào có thể trở thành dead tuple và được VACUUM thu hồi/reuse. Trước khi cleanup, nó vẫn chiếm dung lượng heap.

### 5.3. DELETE không lập tức làm file nhỏ lại

~~~sql
DELETE FROM app.documents
WHERE document_id < 1000;
~~~

Số hàng visible giảm, nhưng kích thước file heap thường không giảm ngay. Space có thể được tái sử dụng cho dữ liệu mới.

### 5.4. HOT update

Heap-Only Tuple (HOT) update có thể tránh tạo index entry mới khi các điều kiện phù hợp, chẳng hạn không đổi cột được index tham chiếu và page có đủ chỗ. HOT giúp giảm churn index, nhưng không xóa mọi chi phí MVCC.

### 5.5. Bảng tăng dung lượng dù row count ổn định

Một workload UPDATE liên tục có thể tạo nhiều tuple versions, page splits trong index, dead tuples và free space. Do đó, dung lượng có thể tăng dù count(*) gần như không đổi.

## 6. TOAST là gì?

**TOAST** là viết tắt của *The Oversized-Attribute Storage Technique*. Đây là cơ chế PostgreSQL dùng để xử lý những giá trị thuộc kiểu có thể lưu biến độ dài (varlena) khi chúng quá lớn để đặt hiệu quả trong một tuple heap.

Các kiểu thường gặp có thể dùng TOAST:

- text, varchar, bytea.
- json, jsonb.
- Các kiểu array.
- Một số kiểu dữ liệu do extension định nghĩa dựa trên varlena.

### 6.1. Vì sao cần TOAST?

Một tuple heap cần vừa trong page và nên để đủ chỗ cho nhiều tuple khác. Nếu một hàng chứa một payload JSON 2 MB, giữ toàn bộ giá trị inline sẽ làm page chứa rất ít hàng, tăng I/O và giảm hiệu quả.

### 6.2. Nén trước, externalize khi cần

PostgreSQL có thể:

1. Nén các giá trị varlena lớn nếu phương pháp lưu trữ cho phép.
2. Nếu tuple vẫn quá lớn, chuyển một số giá trị ra TOAST table.
3. Thay giá trị inline bằng một external TOAST pointer nhỏ trong heap tuple.

### 6.3. Không phải mọi giá trị lớn đều được TOAST

TOAST áp dụng cho kiểu dữ liệu và chiến lược storage phù hợp. Một giá trị nhỏ vẫn có thể lưu inline. Các kiểu fixed-length không dùng cơ chế varlena TOAST theo cùng cách.

### 6.4. Ngưỡng không nên hardcode

Với build mặc định có block 8 KiB, ngưỡng xử lý tuple thường ở khoảng một phần tư page (xấp xỉ 2 KiB), nhưng kích thước thực phụ thuộc page size, tuple overhead và cấu hình/build. PostgreSQL cố đưa tuple về kích thước mục tiêu thay vì bảo đảm mọi cột lớn hơn một số byte cố định đều thành external.

### 6.5. TOAST không phải một database riêng

TOAST table là relation nội bộ thuộc bảng chủ. PostgreSQL quản lý tên, quan hệ phụ thuộc và chỉ mục TOAST; người dùng không nên ghi/xóa chunk trực tiếp.

## 7. TOAST relation lưu dữ liệu thế nào?

Mỗi bảng có TOAST table khi cần cơ chế này sẽ có một relation phụ. Giá trị lớn có thể được chia thành các chunk; TOAST index giúp truy xuất các chunk theo định danh giá trị và thứ tự chunk.

~~~text
Heap table: app.documents
  row document_id=10
  body = external pointer
              |
              v
TOAST table: pg_toast.pg_toast_<oid>
  value_id | chunk_seq | chunk_data
  ---------+-----------+-----------
  ...      | 0         | bytes ...
  ...      | 1         | bytes ...
  ...      | 2         | bytes ...
              |
              v
TOAST index
  (value_id, chunk_seq)
~~~

### 7.1. External pointer trong heap

Heap tuple chứa metadata tham chiếu tới TOAST value thay vì toàn bộ payload. Khi truy vấn cần đọc giá trị, PostgreSQL có thể fetch các chunk liên quan.

### 7.2. Chunking

Một giá trị lớn được chia thành nhiều chunk để lưu trong TOAST table. Mỗi chunk có thứ tự và được kết hợp khi giá trị được đọc lại.

### 7.3. TOAST index

TOAST index là phần thiết yếu để định vị các chunk. Nó cũng chiếm dung lượng, có page và có chi phí bảo trì.

### 7.4. UPDATE một giá trị TOAST

Nếu ứng dụng thay đổi một trường JSONB/text lớn, PostgreSQL có thể phải tạo giá trị TOAST mới và thay external pointer. Không giả định một thay đổi nhỏ trong JSONB luôn chỉ ghi vài byte thay đổi vật lý.

### 7.5. Đọc một cột nhỏ không nhất thiết đọc payload TOAST

Một query chỉ chọn document_id và title có thể tránh phải fetch giá trị body/attachment lớn. Điều này giúp giảm I/O và network payload khi thiết kế truy vấn chỉ lấy cột cần dùng.

## 8. Varlena và kiểu dữ liệu có thể TOAST

PostgreSQL dùng representation varlena cho nhiều kiểu có độ dài biến đổi. Varlena cho phép giá trị mang metadata độ dài/representation và hỗ trợ compression/external storage.

### 8.1. Text

~~~sql
CREATE TABLE app.notes (
    note_id bigint PRIMARY KEY,
    content text
);
~~~

Một cột text có thể rất ngắn hoặc rất dài; PostgreSQL không dành sẵn một vùng cố định tối đa cho mọi row.

### 8.2. Bytea

~~~sql
CREATE TABLE app.attachments (
    attachment_id bigint PRIMARY KEY,
    payload bytea
);
~~~

Bytea phù hợp lưu bytes, nhưng với file lớn cần đánh giá TOAST, backup, replication, streaming và chi phí fetch. Lưu file trong object storage rồi giữ metadata/reference trong PostgreSQL cũng là một phương án kiến trúc.

### 8.3. JSONB

~~~sql
CREATE TABLE app.events (
    event_id bigint PRIMARY KEY,
    payload jsonb NOT NULL
);
~~~

JSONB có representation nhị phân riêng và có thể được TOAST khi lớn. Ngoài heap/TOAST, GIN index trên JSONB có thể chiếm dung lượng đáng kể.

### 8.4. Arrays

~~~sql
CREATE TABLE app.measurements (
    measurement_id bigint PRIMARY KEY,
    samples numeric[]
);
~~~

Array lớn cũng có thể cần TOAST. Nếu truy vấn thường xuyên theo từng phần tử, một thiết kế bảng con có thể hiệu quả hơn một array khổng lồ tùy workload.

### 8.5. Composite và extension types

Một kiểu dữ liệu phức tạp có thể dựa trên varlena, nhưng khả năng TOAST cụ thể phụ thuộc định nghĩa type và storage support của nó.

## 9. Bốn chiến lược lưu trữ TOAST

PostgreSQL có thuộc tính storage theo cột:

| Storage | Nén? | Đẩy ra TOAST? | Ý nghĩa |
| --- | --- | --- | --- |
| PLAIN | Không | Không | Giữ inline; không dùng TOAST compression/out-of-line |
| MAIN | Có | Chỉ khi cần để tuple vừa | Ưu tiên giữ inline sau compression |
| EXTERNAL | Không | Có | Có thể lưu ngoài nhưng không nén |
| EXTENDED | Có | Có | Cho phép compression và external storage; mặc định phổ biến cho varlena |

### 9.1. PLAIN

Phù hợp kiểu dữ liệu/representation cần inline hoặc khi storage strategy không cho phép TOAST. Với cột lớn mà bắt buộc inline, row có thể không vừa page và thao tác ghi có thể thất bại.

### 9.2. MAIN

PostgreSQL có thể nén giá trị nhưng ưu tiên giữ inline; chỉ đẩy ra ngoài khi cần thiết để tuple đạt kích thước mục tiêu.

### 9.3. EXTERNAL

PostgreSQL có thể lưu giá trị ngoài mà không nén. Với một số workload truy xuất substring/đọc một phần, tránh giải nén toàn giá trị có thể có lợi, nhưng tốn thêm dung lượng.

### 9.4. EXTENDED

Cho phép cả compression và out-of-line storage. Đây là lựa chọn mặc định phổ biến cho các kiểu varlena như text, bytea và jsonb.

### 9.5. Thay storage strategy

~~~sql
ALTER TABLE app.documents
ALTER COLUMN body SET STORAGE EXTERNAL;
~~~

Thay đổi này điều chỉnh cách PostgreSQL lưu **các giá trị được ghi/cập nhật trong tương lai**. Nó không tự động rewrite toàn bộ các giá trị hiện đang lưu để chuyển chúng sang strategy mới.

### 9.6. Không dùng EXTERNAL chỉ vì thấy TOAST lớn

Không nén có thể làm TOAST tăng mạnh nếu dữ liệu nén tốt. Chỉ chọn strategy sau khi đo compression ratio, pattern đọc và dung lượng.

## 10. Compression của TOAST

PostgreSQL có thể nén giá trị varlena trước khi externalize hoặc giữ inline tùy chiến lược. Compression có thể tiết kiệm disk và I/O nhưng tiêu thụ CPU.

### 10.1. PGLZ

PGLZ là phương pháp nén mặc định truyền thống của PostgreSQL. Nó không cần một thư viện ngoài bổ sung.

### 10.2. LZ4

Các bản PostgreSQL được build với hỗ trợ LZ4 có thể cho phép chọn compression method LZ4. Tính năng/cấu hình cụ thể phụ thuộc phiên bản server và cách build.

### 10.3. Chọn compression cho cột

Ở các phiên bản hỗ trợ, có thể chỉ định:

~~~sql
ALTER TABLE app.documents
ALTER COLUMN body SET COMPRESSION lz4;
~~~

hoặc phương pháp phù hợp khác như pglz. Xác nhận server build và phiên bản trước khi dùng cú pháp này.

### 10.4. Compression không phải lúc nào cũng tiết kiệm

Với dữ liệu đã nén (JPEG, ZIP, PDF, video, encrypted blobs), nén lần nữa có thể ít hiệu quả hoặc làm tăng CPU. Dữ liệu text lặp nhiều thường có tỷ lệ nén tốt hơn.

### 10.5. Compression ratio

Một cách khảo sát logic:

~~~sql
SELECT
    document_id,
    octet_length(body) AS logical_bytes,
    pg_column_size(body) AS datum_bytes
FROM app.documents
ORDER BY document_id;
~~~

octet_length() cho biết số byte nội dung text theo encoding; pg_column_size() cho biết kích thước representation của datum theo cách PostgreSQL đo. Với dữ liệu TOAST/external, đừng diễn giải pg_column_size() như tổng toàn bộ chunk + TOAST index của row; dùng size functions trên relation để đo storage tổng.

### 10.6. Compression method không rewrite dữ liệu cũ

Sau khi đổi compression method, các giá trị đã lưu không nhất thiết được nén lại ngay. Muốn chuyển đổi dữ liệu cũ, cần một quy trình rewrite/update có kiểm soát, đánh giá WAL, locks và dung lượng tạm.

## 11. Heap size, table size, index size và total size

Bốn hàm size chính:

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('public.orders')) AS relation_main,
    pg_size_pretty(pg_table_size('public.orders')) AS table_bytes,
    pg_size_pretty(pg_indexes_size('public.orders')) AS index_bytes,
    pg_size_pretty(pg_total_relation_size('public.orders')) AS total_bytes;
~~~

### 11.1. pg_relation_size

pg_relation_size(relation [, fork]) trả số bytes của một relation/fork. Khi không chỉ định fork, hàm mặc định đo main fork.

Ví dụ:

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('public.orders', 'main')
    ) AS main_fork,
    pg_size_pretty(
        pg_relation_size('public.orders', 'fsm')
    ) AS free_space_map,
    pg_size_pretty(
        pg_relation_size('public.orders', 'vm')
    ) AS visibility_map;
~~~

### 11.2. pg_table_size

Đo phần lưu trữ của bảng, gồm heap relation, các fork phụ trợ và TOAST storage liên quan theo cách PostgreSQL tính; **không phải tổng các index nghiệp vụ gắn trực tiếp với bảng**.

### 11.3. pg_indexes_size

Đo dung lượng các index gắn với bảng. Một bảng có thể có nhiều index, và mỗi index là relation độc lập.

### 11.4. pg_total_relation_size

Đo tổng dung lượng bảng cùng indexes và TOAST storage. Đây thường là con số hữu ích khi cần biết một bảng tiêu thụ bao nhiêu dung lượng tổng thể.

### 11.5. Kích thước tính bằng byte

Các hàm size trả số bytes (bigint). Dùng pg_size_pretty() để hiển thị KB/MB/GB dễ đọc, nhưng giữ giá trị byte khi cần tính tỷ lệ/chênh lệch chính xác.

### 11.6. Ví dụ so sánh

| Hàm | Phạm vi |
| --- | --- |
| pg_relation_size(table) | Main fork của relation được chỉ định |
| pg_table_size(table) | Heap, forks phụ và TOAST storage |
| pg_indexes_size(table) | Các index gắn với bảng |
| pg_total_relation_size(table) | Tổng table + indexes + TOAST |

## 12. Đo từng index của một bảng

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(
        pg_relation_size(
            quote_ident(schemaname) || '.' || quote_ident(indexname)
        )
    ) AS index_size
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'orders'
ORDER BY pg_relation_size(
    quote_ident(schemaname) || '.' || quote_ident(indexname)
) DESC;
~~~

Một cách dùng catalog rõ hơn:

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    pg_size_pretty(pg_relation_size(i.indexrelid)) AS index_size
FROM pg_index AS i
WHERE i.indrelid = 'public.orders'::regclass
ORDER BY pg_relation_size(i.indexrelid) DESC;
~~~

### 12.1. Vì sao index có thể lớn?

- Index nhiều cột hoặc cột có giá trị dài.
- GIN index trên JSONB/array/full-text.
- Nhiều index phục vụ nhiều truy vấn.
- Page split và mức độ phân mảnh.
- Dead index tuples/space chưa được tái sử dụng.

### 12.2. Index không miễn phí

Mỗi INSERT có thể cần thêm index entries. UPDATE cột được index tham chiếu thường tạo thêm chi phí index. Nhiều index làm tăng storage, WAL, CPU và thời gian ghi.

### 12.3. Không xóa index chỉ vì lớn

Index lớn có thể là thành phần thiết yếu cho latency và constraint. Đánh giá usage, query plans, uniqueness và workload trước khi thay đổi.

## 13. Đo TOAST relation

Mỗi bảng có thể tham chiếu TOAST table qua pg_class.reltoastrelid.

~~~sql
SELECT
    c.oid::regclass AS table_name,
    CASE
        WHEN c.reltoastrelid = 0 THEN NULL
        ELSE c.reltoastrelid::regclass::text
    END AS toast_table,
    CASE
        WHEN c.reltoastrelid = 0 THEN NULL
        ELSE pg_size_pretty(
            pg_total_relation_size(c.reltoastrelid)
        )
    END AS toast_total_size
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname = 'documents';
~~~

### 13.1. reltoastrelid bằng 0

Giá trị 0 có nghĩa relation không có TOAST relation gắn theo catalog tại thời điểm kiểm tra. Không phải mọi bảng đều cần TOAST.

### 13.2. TOAST table nằm trong schema hệ thống

Tên vật lý thường thuộc schema pg_toast; người dùng nên truy cập qua bảng chủ và catalog, không thao tác trực tiếp vào TOAST chunks.

### 13.3. Đo TOAST riêng không phải toàn bộ bảng

Kết quả TOAST cho biết relation phụ. Để biết tổng dung lượng bảng, dùng pg_total_relation_size() trên bảng chủ.

### 13.4. TOAST index

TOAST table có index nội bộ. pg_total_relation_size() trên OID của TOAST relation có thể giúp quan sát phần relation cùng index của nó; tránh cộng nhầm thêm lần nữa khi đã dùng total size của bảng chủ.

### 13.5. Không đếm trùng

Nếu báo cáo có cột table_size, toast_size, index_size và total_size, phải ghi rõ table_size đang bao gồm TOAST hay chưa. Nếu pg_table_size() đã tính TOAST, cộng thêm toast_size sẽ đếm trùng.

## 14. Đo size toàn bộ bảng trong schema

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    pg_size_pretty(pg_relation_size(
        quote_ident(schemaname) || '.' || quote_ident(relname)
    )) AS heap_main,
    pg_size_pretty(pg_table_size(
        quote_ident(schemaname) || '.' || quote_ident(relname)
    )) AS table_storage,
    pg_size_pretty(pg_indexes_size(
        quote_ident(schemaname) || '.' || quote_ident(relname)
    )) AS indexes,
    pg_size_pretty(pg_total_relation_size(
        quote_ident(schemaname) || '.' || quote_ident(relname)
    )) AS total
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(
    quote_ident(schemaname) || '.' || quote_ident(relname)
) DESC;
~~~

### 14.1. Chỉ đo bảng người dùng

pg_stat_user_tables thuận tiện để liệt kê bảng người dùng trong các schema được thống kê.

### 14.2. Đổi schema

Thay public bằng schema cần khảo sát. Đừng giả định mọi ứng dụng chỉ dùng schema public.

### 14.3. Identifier an toàn

Trong ví dụ, identifier được quote để tên bảng/schema có ký tự đặc biệt không bị hiểu nhầm. Với công cụ tự động, ưu tiên hàm/catalog join có OID thay vì nối chuỗi tên.

### 14.4. Partitioned parent

Một parent partitioned table không lưu heap tuple như bảng thường. Khi muốn báo cáo chính xác từng partition, liệt kê các leaf partitions và đo từng relation.

## 15. Catalog pg_class và pg_attribute

pg_class lưu metadata cho relation:

- relkind: loại relation.
- reltoastrelid: OID của TOAST relation.
- relpages, reltuples: ước lượng page và tuple.
- relfilenode: file node hiện tại trong tablespace.
- relpersistence: permanent/unlogged/temporary.
- reloptions: storage parameters như fillfactor.

pg_attribute mô tả cột, bao gồm storage strategy và một số thuộc tính compression tùy phiên bản.

### 15.1. Xem bảng và TOAST

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.relkind,
    c.reltoastrelid,
    CASE
        WHEN c.reltoastrelid = 0 THEN NULL
        ELSE c.reltoastrelid::regclass
    END AS toast_relation,
    c.relpages,
    c.reltuples,
    c.reloptions
FROM pg_class AS c
WHERE c.oid = 'public.documents'::regclass;
~~~

### 15.2. Xem storage strategy theo cột

~~~sql
SELECT
    a.attname AS column_name,
    a.atttypid::regtype AS data_type,
    a.attstorage,
    a.attcompression
FROM pg_attribute AS a
WHERE a.attrelid = 'public.documents'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

attcompression có ở các phiên bản PostgreSQL hỗ trợ lựa chọn compression theo cột (ví dụ PostgreSQL 14 trở lên). Trên server cũ hơn, truy vấn cột này có thể lỗi; bỏ cột attcompression khi cần tương thích.

### 15.3. relkind

Một số loại thường gặp:

| relkind | Loại |
| --- | --- |
| r | Ordinary table |
| p | Partitioned table |
| i | Index |
| I | Partitioned index |
| t | TOAST table |
| m | Materialized view |
| v | View |

### 15.4. relpages và reltuples là ước lượng

Các cột này là statistics/catalog estimates, không phải lúc nào cũng chính xác ngay sau một workload mới. ANALYZE cập nhật planner statistics; các hàm size đo bytes vật lý là công cụ khác.

## 16. Lab: tạo bảng có dữ liệu inline và TOAST

Tạo schema:

~~~sql
CREATE SCHEMA storage_lab;
~~~

Tạo bảng:

~~~sql
CREATE TABLE storage_lab.documents (
    document_id bigint PRIMARY KEY,
    title text NOT NULL,
    body text,
    payload bytea,
    metadata jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 16.1. Thêm index nghiệp vụ

~~~sql
CREATE INDEX idx_documents_created_at
ON storage_lab.documents (created_at);

CREATE INDEX idx_documents_metadata_gin
ON storage_lab.documents
USING gin (metadata);
~~~

### 16.2. Thêm dữ liệu có body dài

~~~sql
INSERT INTO storage_lab.documents (
    document_id, title, body, metadata
)
SELECT
    g,
    'Document ' || g,
    (
        SELECT string_agg(
            md5(g::text || ':' || s::text),
            ''
        )
        FROM generate_series(1, 250) AS s
    ),
    jsonb_build_object(
        'category', 'lab',
        'sequence', g,
        'tags', jsonb_build_array('postgres', 'storage', 'toast')
    )
FROM generate_series(1, 30) AS g;
~~~

Body có nhiều chuỗi hash khác nhau, kích thước lớn và khó nén mạnh như một chuỗi lặp đơn giản.

### 16.3. Thêm payload bytea

~~~sql
UPDATE storage_lab.documents
SET payload = decode(
    repeat(md5(document_id::text), 300),
    'hex'
);
~~~

Đây là payload nhị phân giả lập. Mỗi md5() trả 32 ký tự hex; decode(..., 'hex') chuyển về bytes.

### 16.4. Thêm JSONB lớn

~~~sql
UPDATE storage_lab.documents
SET metadata = metadata ||
    jsonb_build_object(
        'attributes',
        (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'key', 'field-' || s,
                    'value', md5(document_id::text || ':' || s::text)
                )
            )
            FROM generate_series(1, 100) AS s
        )
    );
~~~

### 16.5. Không cần hàng triệu records để thấy TOAST

Chỉ vài chục hàng với các trường lớn đã có thể tạo TOAST relation. Dung lượng chính xác phụ thuộc phiên bản, compression và dữ liệu sinh ra.

## 17. Đo bảng lab

~~~sql
SELECT
    pg_size_pretty(pg_relation_size(
        'storage_lab.documents'
    )) AS heap_main,
    pg_size_pretty(pg_table_size(
        'storage_lab.documents'
    )) AS table_including_toast,
    pg_size_pretty(pg_indexes_size(
        'storage_lab.documents'
    )) AS indexes,
    pg_size_pretty(pg_total_relation_size(
        'storage_lab.documents'
    )) AS total;
~~~

### 17.1. Đọc kết quả

- heap_main: main fork của heap relation.
- table_including_toast: table storage cùng các thành phần phụ/TOAST theo hàm.
- indexes: các indexes gắn với bảng.
- total: tổng lưu trữ của bảng và indexes.

### 17.2. Vì sao heap_main nhỏ hơn table_including_toast?

Nếu body, payload hoặc metadata được TOAST, payload được lưu ở relation phụ. Vì thế heap có thể chỉ chứa pointer và phần inline, còn TOAST storage làm tăng table size.

### 17.3. Vì sao total lớn hơn table?

Bảng có primary key index, index created_at và GIN index metadata. Các index là các relation độc lập nên tăng tổng dung lượng.

### 17.4. Tỷ lệ index

~~~sql
SELECT
    pg_total_relation_size('storage_lab.documents') AS total_bytes,
    pg_indexes_size('storage_lab.documents') AS index_bytes,
    round(
        100.0 * pg_indexes_size('storage_lab.documents')
        / NULLIF(
            pg_total_relation_size('storage_lab.documents'), 0
        ),
        2
    ) AS index_percent;
~~~

Tỷ lệ cao không mặc nhiên là xấu; một bảng phục vụ truy vấn tìm kiếm có thể có GIN index lớn hơn heap.

## 18. Đo từng index trong lab

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    pg_size_pretty(pg_relation_size(i.indexrelid)) AS index_size,
    am.amname AS access_method,
    pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_index AS i
JOIN pg_class AS ic
  ON ic.oid = i.indexrelid
JOIN pg_am AS am
  ON am.oid = ic.relam
WHERE i.indrelid = 'storage_lab.documents'::regclass
ORDER BY pg_relation_size(i.indexrelid) DESC;
~~~

### 18.1. B-tree và GIN

Primary key và created_at thường dùng B-tree; index JSONB ở lab dùng GIN. GIN có cấu trúc và fan-out khác B-tree nên dung lượng/chi phí ghi không thể suy từ số entry đơn giản.

### 18.2. Index có thể chứa nhiều metadata

Index lưu key và thông tin định vị tuple, cộng overhead page. Một GIN index có thể mở rộng theo số token/key trong JSONB.

### 18.3. Index không lưu toàn bộ row như heap

Index chỉ lưu dữ liệu cần thiết cho access method và tham chiếu tuple; nhưng với index expression/include columns, phần dữ liệu lưu trong index có thể lớn.

### 18.4. Primary key cũng là index

Khai báo PRIMARY KEY thường tạo unique B-tree index tự động. Không cần tạo thêm index trùng hoàn toàn cùng key nếu không có mục đích riêng.

## 19. Đo TOAST relation của lab

~~~sql
SELECT
    c.oid::regclass AS table_name,
    t.oid::regclass AS toast_table,
    pg_size_pretty(pg_relation_size(t.oid)) AS toast_heap_main,
    pg_size_pretty(pg_total_relation_size(t.oid)) AS toast_total
FROM pg_class AS c
JOIN pg_class AS t
  ON t.oid = c.reltoastrelid
WHERE c.oid = 'storage_lab.documents'::regclass;
~~~

### 19.1. Nếu không có dòng kết quả

Bảng chưa có TOAST relation hoặc catalog relation không match. Trong lab có trường dài nên thường PostgreSQL sẽ tạo TOAST relation, nhưng điều đó vẫn phụ thuộc dữ liệu thực và storage behavior.

### 19.2. Đo chunk count (chỉ khảo sát nội bộ)

Có thể xem metadata TOAST relation trong catalog hoặc đọc relation hệ thống tương ứng bằng công cụ quản trị có quyền phù hợp. Không nên viết ứng dụng nghiệp vụ truy vấn trực tiếp các bảng pg_toast vì tên/OID và cách lưu trữ là implementation detail.

### 19.3. Không cập nhật TOAST chunks trực tiếp

Sửa/xóa chunk nội bộ sẽ phá external pointers và có thể làm hỏng dữ liệu. Chỉ cập nhật cột ở bảng chủ bằng SQL bình thường.

## 20. pg_column_size, octet_length và pg_column_compression

Ba hàm này trả lời những câu hỏi khác nhau.

### 20.1. octet_length

Với text, trả số byte của nội dung sau khi được biểu diễn theo encoding của chuỗi:

~~~sql
SELECT
    title,
    length(body) AS characters,
    octet_length(body) AS logical_bytes
FROM storage_lab.documents
LIMIT 5;
~~~

### 20.2. pg_column_size

Trả số bytes dùng để lưu một giá trị datum theo representation PostgreSQL đo, có thể liên quan compression. Nó không phải tổng dung lượng toàn bộ relation TOAST/index.

~~~sql
SELECT
    document_id,
    octet_length(body) AS body_logical_bytes,
    pg_column_size(body) AS body_datum_bytes,
    octet_length(payload) AS payload_bytes,
    pg_column_size(payload) AS payload_datum_bytes
FROM storage_lab.documents
ORDER BY document_id
LIMIT 10;
~~~

### 20.3. pg_column_compression

Ở các phiên bản hỗ trợ, hàm pg_column_compression(any) trả tên phương pháp nén được dùng cho datum, hoặc NULL nếu không nén.

~~~sql
SELECT
    document_id,
    pg_column_compression(body) AS body_compression,
    pg_column_compression(metadata) AS metadata_compression
FROM storage_lab.documents
ORDER BY document_id
LIMIT 10;
~~~

### 20.4. Vì sao ba con số khác nhau?

- octet_length: nội dung logic tính bằng bytes.
- pg_column_size: kích thước representation của datum theo hàm.
- pg_total_relation_size: dung lượng vật lý relation/table/index gồm nhiều cấu trúc.

Không cộng pg_column_size() của mọi row rồi kỳ vọng bằng pg_total_relation_size(): cách đó bỏ qua page headers, tuple headers, line pointers, free space, index, TOAST chunks, forks và dead tuples.

### 20.5. Giới hạn version

pg_column_compression() và metadata compression phụ thuộc phiên bản PostgreSQL. Nếu hàm không tồn tại, kiểm tra phiên bản server và bỏ cột đó trong truy vấn đo.

## 21. Dung lượng index so với heap

Một bảng có thể có:

~~~sql
CREATE TABLE app.search_docs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text,
    body text,
    attributes jsonb
);

CREATE INDEX search_docs_title_idx
ON app.search_docs (title);

CREATE INDEX search_docs_attributes_gin
ON app.search_docs
USING gin (attributes);
~~~

### 21.1. GIN index trên JSONB

GIN có thể lập index cho nhiều key/token trong JSONB. Một row JSONB nhiều thuộc tính có thể sinh ra nhiều index entries; index có thể rất lớn.

### 21.2. Full-text search

Một tsvector hoặc expression index cho tìm kiếm toàn văn có thể lưu các lexemes và metadata. Số entry index không bằng số row.

### 21.3. INCLUDE columns

~~~sql
CREATE INDEX orders_customer_cover_idx
ON app.orders (customer_id)
INCLUDE (created_at, total_amount);
~~~

Index có thêm payload columns, có thể tăng size nhưng hỗ trợ index-only scans trong điều kiện visibility phù hợp.

### 21.4. Partial indexes

~~~sql
CREATE INDEX orders_open_idx
ON app.orders (created_at)
WHERE status = 'open';
~~~

Partial index có thể nhỏ hơn index toàn bảng nếu chỉ bao phủ một phần rows. Cần cân nhắc query predicates để planner có thể sử dụng.

### 21.5. Nhiều index trùng lặp

Hai index có cùng prefix/columns nhưng khác thứ tự, collation, predicate hoặc include có thể phục vụ các truy vấn khác nhau. Không xóa dựa trên tên; dùng query plans và usage stats để xác định.

## 22. Tại sao bảng có thể lớn hơn tổng giá trị logic?

Dung lượng vật lý có nhiều lớp overhead:

1. Page header và line pointers.
2. Tuple headers, null bitmap, alignment.
3. Free space trong page.
4. Dead tuples và phiên bản MVCC cũ.
5. Index entries và index page overhead.
6. TOAST chunks và TOAST index.
7. FSM/VM/init forks.
8. Fragmentation và page splits.

### 22.1. Không phải mọi byte trong file đều là byte payload

Một bảng lưu 1 GB nội dung ứng dụng có thể chiếm hơn 1 GB relation do overhead và indexes. Tỷ lệ tùy kiểu dữ liệu, số index, fillfactor, cập nhật và compression.

### 22.2. Nén có thể làm dung lượng nhỏ hơn payload logic

Một chuỗi lặp dài có thể nén mạnh. Vì vậy kích thước file PostgreSQL đôi khi nhỏ hơn tổng octet_length() của values.

### 22.3. Nhiều index làm tổng lớn hơn payload nhiều lần

Một bảng có nhiều GIN indexes hoặc indexes chứa các giá trị dài có thể có total size cao hơn nhiều so với heap + TOAST.

### 22.4. Không thể suy dung lượng từ số cột

Một cột jsonb 5 MB khác hẳn một cột integer; số cột không phản ánh dung lượng.

## 23. VACUUM và kích thước heap

VACUUM thường làm sạch dead tuples đủ điều kiện và đánh dấu không gian để tái sử dụng. Nó **không thường xuyên thu nhỏ file relation về hệ điều hành**.

### 23.1. VACUUM thường

~~~sql
VACUUM (ANALYZE) storage_lab.documents;
~~~

Có thể:

- Dọn dead tuples đã không còn cần.
- Làm page space sẵn sàng cho lần ghi sau.
- Cập nhật visibility map.
- Cập nhật statistics khi kèm ANALYZE.

### 23.2. File thường không giảm nhiều

Không gian trống ở giữa relation được giữ để tái sử dụng. Vì thế kích thước pg_total_relation_size() có thể gần như không đổi sau VACUUM dù n_dead_tup giảm.

### 23.3. VACUUM FULL

~~~sql
VACUUM FULL storage_lab.documents;
~~~

VACUUM FULL rewrite bảng sang file mới để thu hồi không gian vật lý, thường yêu cầu ACCESS EXCLUSIVE lock và có thể cần disk tạm đủ lớn. Đây không phải thao tác nhẹ để chạy tùy tiện trong giờ cao điểm.

### 23.4. Autovacuum

Autovacuum giúp cleanup và analyze tự động theo threshold/scale factor và workload. Nó không đồng nghĩa tự động chạy VACUUM FULL để thu nhỏ mọi file.

### 23.5. Long-running transactions và replication slots

Snapshot lâu hoặc replication slot giữ xmin có thể ngăn VACUUM loại bỏ một số dead tuples. Khi đó heap/index có thể tiếp tục tăng dù autovacuum hoạt động.

## 24. REINDEX và dung lượng index

REINDEX xây dựng lại index:

~~~sql
REINDEX INDEX storage_lab.idx_documents_created_at;
~~~

### 24.1. REINDEX xử lý index, không phải heap

Nó không trực tiếp thu nhỏ heap table hoặc TOAST data. Muốn đo hiệu quả, xem size index trước/sau và đánh giá query plans.

### 24.2. REINDEX TABLE

~~~sql
REINDEX TABLE storage_lab.documents;
~~~

Xây dựng lại các indexes của bảng theo chế độ khóa phù hợp.

### 24.3. REINDEX CONCURRENTLY

~~~sql
REINDEX INDEX CONCURRENTLY storage_lab.idx_documents_created_at;
~~~

Giảm thời gian chặn thao tác ghi so với cách thông thường trong các điều kiện hỗ trợ, nhưng thực hiện nhiều bước hơn, cần tài nguyên tạm và có giới hạn sử dụng. Kiểm tra version/lock behavior trước production.

### 24.4. Không reindex mọi index theo lịch cứng

Index size lớn không tự chứng minh index bloat. Xem workload, stats, index health và các công cụ đo chuyên biệt trước khi quyết định.

## 25. Bloat: heap, index và TOAST

**Bloat** là phần dung lượng bị dùng kém hiệu quả do dead tuples, free space, page splits hoặc những hình thái storage không còn phù hợp workload. Bloat không có một định nghĩa duy nhất áp dụng cho mọi báo cáo.

### 25.1. Heap bloat

Heap có nhiều page chứa ít live tuples hoặc nhiều dead tuples chưa được thu hồi. Kích thước file tăng trong khi row count visible không tăng tương ứng.

### 25.2. Index bloat

Index có nhiều trang ít sử dụng, fragmentation hoặc dead entries/space. Một số loại index tái sử dụng page theo cách khác nhau.

### 25.3. TOAST bloat

Các giá trị TOAST cũ từ update/delete có thể tạo dead chunks; TOAST table cũng cần VACUUM cleanup. Nếu trường lớn bị cập nhật liên tục, TOAST relation có thể tăng.

### 25.4. Đừng nhầm free space với bloat vô dụng

Một page có free space có thể rất hữu ích cho workload INSERT/UPDATE tiếp theo. Thu nhỏ bằng rewrite có thể làm mất chỗ dự phòng và khiến bảng lại tăng sau một thời gian.

### 25.5. Chỉ đo size chưa đủ

Để đánh giá bloat, cần biết live/dead tuple counts, page density, index-specific statistics và lịch sử workload.

## 26. Dùng pg_stat_user_tables để quan sát

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'storage_lab'
ORDER BY n_dead_tup DESC;
~~~

### 26.1. n_live_tup/n_dead_tup là ước lượng

Các counters/stats này không phải một lần đếm chính xác tức thời toàn bộ rows. Chúng hữu ích cho monitoring và xu hướng.

### 26.2. Update churn

n_tup_upd tăng nhanh trong khi n_live_tup ổn định có thể gợi ý workload cập nhật nhiều và cần xem vacuum/HOT/dead tuples.

### 26.3. Vacuum timestamps

last_autovacuum/last_vacuum cho biết thời điểm vacuum gần nhất theo thống kê; không tự chứng minh vacuum đã dọn hết mọi thứ.

### 26.4. Stats có thể reset

Counters có thể reset bởi thao tác quản trị/restart hoặc cơ chế thống kê theo version. Khi tính rate, lưu ý thời điểm reset.

## 27. Dùng pg_statio_user_tables để xem I/O

~~~sql
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit,
    toast_blks_read,
    toast_blks_hit,
    tidx_blks_read,
    tidx_blks_hit
FROM pg_statio_user_tables
WHERE schemaname = 'storage_lab';
~~~

### 27.1. Heap blocks

Cho biết block heap được đọc từ storage hoặc cache theo statistics.

### 27.2. Index blocks

Giúp quan sát hoạt động I/O index ở mức bảng.

### 27.3. TOAST blocks

Có thể cho thấy workload đang đọc dữ liệu TOAST. Nếu query thường xuyên fetch payload lớn, toast block reads/hits có thể tăng.

### 27.4. TOAST index blocks

tidx_blks_* liên quan index của TOAST. Đây là tín hiệu hữu ích khi truy vấn cần tìm các chunk external.

### 27.5. Hit không có nghĩa miễn phí

Cache hit tránh disk read vật lý ở tầng đó, nhưng vẫn tốn CPU, memory bandwidth và tuple reconstruction/decompression.

## 28. Dùng pgstattuple khi cần đo sâu

Extension pgstattuple có thể cung cấp thông tin về live/dead tuples và free space trên relation:

~~~sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;

SELECT *
FROM pgstattuple('storage_lab.documents');
~~~

### 28.1. Kết quả

Extension có thể báo:

- table_len.
- tuple_count, tuple_len.
- dead_tuple_count, dead_tuple_len.
- free_space và tỷ lệ tương ứng.

### 28.2. Quét relation có chi phí

pgstattuple có thể scan toàn bộ relation. Trên bảng lớn, hãy đánh giá I/O và chạy trong thời gian phù hợp.

### 28.3. pgstattuple_approx

Một hàm gần đúng có thể dùng visibility map để giảm công việc trong những điều kiện phù hợp. Kết quả là approximation, không thay một scan đầy đủ khi cần số liệu chính xác.

### 28.4. Quyền và extension

Việc cài extension có thể cần quyền quản trị và package/module được cài trên server. Không giả định mọi managed PostgreSQL cho phép extension.

### 28.5. Không biến báo cáo bloat thành lệnh rewrite tự động

Đo lường chỉ là đầu vào quyết định. Rewrite/reindex cần kế hoạch khóa, disk, replication, backup và rollback.

## 29. FSM và VM ảnh hưởng kích thước ra sao?

### 29.1. Free Space Map

FSM lưu ước lượng page còn chỗ trống để PostgreSQL tìm nơi đặt tuple mới. Nó có thể chiếm một phần relation storage và được cập nhật qua thao tác ghi/vacuum.

### 29.2. Visibility Map

VM lưu trạng thái page all-visible/all-frozen theo semantics PostgreSQL. Nó hỗ trợ VACUUM và index-only scans.

### 29.3. Index-only scan

Nếu query cần các cột có trong index và visibility map cho biết page phù hợp, PostgreSQL có thể tránh heap fetch cho một số rows. VM tốt có thể giúp hiệu năng mà không làm index nhỏ đi.

### 29.4. Init fork

Unlogged relations có init fork để khôi phục nội dung khởi tạo sau crash. Init fork là một phần vật lý riêng; không phải mọi table đều có.

### 29.5. Đo từng fork

~~~sql
SELECT
    pg_size_pretty(pg_relation_size(
        'storage_lab.documents', 'main'
    )) AS main,
    pg_size_pretty(pg_relation_size(
        'storage_lab.documents', 'fsm'
    )) AS fsm,
    pg_size_pretty(pg_relation_size(
        'storage_lab.documents', 'vm'
    )) AS vm,
    pg_size_pretty(pg_relation_size(
        'storage_lab.documents', 'init'
    )) AS init;
~~~

Nếu fork không tồn tại hoặc không áp dụng, kết quả có thể là 0.

## 30. Relation file path và tablespace

Các hàm quản trị cho phép xem vị trí file relation:

~~~sql
SELECT
    pg_relation_filenode('storage_lab.documents'::regclass)
        AS filenode,
    pg_relation_filepath('storage_lab.documents'::regclass)
        AS relative_path;
~~~

### 30.1. relfilenode

Là định danh file vật lý hiện tại của relation trong cơ chế storage. Một số thao tác rewrite/reindex có thể đổi filenode.

### 30.2. File có thể chia segment

Relation lớn hơn giới hạn segment có thể trải thành nhiều file segment. Không chỉ tìm một file có tên filenode rồi xem đó là toàn bộ relation.

### 30.3. Tablespace

Relation có thể nằm trong tablespace riêng. Đường dẫn vật lý có thể khác tablespace mặc định; quyền OS và quản trị disk cần tính đến.

### 30.4. Không sửa/xóa file relation trực tiếp

Không di chuyển, truncate, rename hoặc xóa file trong thư mục base/ hay pg_tblspc/ khi server đang quản lý relation. Dùng SQL/DDL và công cụ PostgreSQL.

## 31. Partitioning và tổng kích thước

Một partitioned table (relkind = 'p') là quan hệ logic cha, không giữ heap rows như ordinary table. Dữ liệu nằm trong partitions con.

### 31.1. Đo từng leaf partition

Ở các phiên bản hỗ trợ pg_partition_tree():

~~~sql
SELECT
    relid::regclass AS partition_name,
    isleaf,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_partition_tree('app.events'::regclass)
WHERE isleaf
ORDER BY pg_total_relation_size(relid) DESC;
~~~

### 31.2. Tổng các partition

~~~sql
SELECT
    sum(pg_total_relation_size(relid)) AS total_bytes,
    pg_size_pretty(sum(pg_total_relation_size(relid))) AS total_pretty
FROM pg_partition_tree('app.events'::regclass)
WHERE isleaf;
~~~

### 31.3. Đừng cộng parent lẫn leaf

Nếu báo cáo đã đo các leaf partitions, không cộng lại parent một lần nữa nếu hàm/công cụ báo cáo đã tính descendants. Ghi rõ cách tổng hợp để tránh double-count.

### 31.4. Partition có thể khác nhau nhiều

Partition theo tháng có thể có dung lượng rất khác nhau do retention, mùa vụ và skew. Báo cáo top partitions giúp tìm dữ liệu nóng hoặc batch bất thường.

### 31.5. Index partitions

Partitioned index trên parent được hiện thực bằng indexes trên các partitions. Khi đo index, cần hiểu parent index metadata và các leaf index relations.

## 32. Materialized views và TOAST

Materialized view lưu kết quả query thành relation vật lý. Nó có thể có heap, indexes và TOAST tương tự bảng.

~~~sql
SELECT
    pg_size_pretty(pg_total_relation_size(
        'app.monthly_report'::regclass
    ));
~~~

### 32.1. View thường không có heap storage

View (relkind = 'v') chỉ là định nghĩa query, không giữ bản sao vật lý dữ liệu như materialized view.

### 32.2. Materialized view có thể có index

Index trên materialized view làm tăng total size và chi phí REFRESH MATERIALIZED VIEW.

### 32.3. Đo đúng loại relation

Khi báo cáo kích thước, lọc relkind để không so sánh view logic với heap table vật lý.

## 33. Unlogged và temporary tables

### 33.1. Unlogged tables

Unlogged table giảm WAL cho dữ liệu bảng theo semantics PostgreSQL, nhưng không có cùng durability sau crash như logged tables và không được replicate như table thông thường theo physical WAL. Nó vẫn chiếm dung lượng relation.

### 33.2. Init fork

Unlogged relations dùng init fork để phục hồi trạng thái khởi tạo khi server crash/restart theo quy tắc PostgreSQL.

### 33.3. Temporary tables

Temporary tables thuộc session/transaction scope và có thể dùng storage riêng. Chúng không nên bị nhầm với dữ liệu lâu dài của ứng dụng.

### 33.4. Đo temp data

Temp files do sort/hash spill khác với temporary table relation. Chúng có lifecycle và monitoring riêng; không nằm trong pg_total_relation_size() của bảng nghiệp vụ.

## 34. TOAST và truy vấn hiệu năng

### 34.1. SELECT cột cần thiết

~~~sql
SELECT document_id, title
FROM storage_lab.documents
WHERE document_id = 10;
~~~

Không chọn body, payload, metadata nếu request không cần. Giảm dữ liệu TOAST phải fetch/decompress và giảm bytes trả về client.

### 34.2. SELECT *

~~~sql
SELECT *
FROM storage_lab.documents
WHERE document_id = 10;
~~~

Có thể buộc PostgreSQL phải truy xuất các giá trị lớn, làm tăng I/O, CPU giải nén và network payload.

### 34.3. Function có thể detoast

Một số hàm xử lý text/JSONB cần đọc toàn giá trị và có thể detoast. Khi viết biểu thức, đừng giả định một thao tác trên JSONB luôn chỉ chạm một phần bytes.

### 34.4. JSONB path update

jsonb_set() tạo giá trị JSONB kết quả mới theo semantics dữ liệu. Với document rất lớn, một thay đổi nhỏ ở một key có thể vẫn có chi phí xử lý/ghi lớn hơn nhiều so với vài byte.

### 34.5. Tách metadata và blob

Nếu ứng dụng thường chỉ đọc metadata mà ít khi lấy attachment, có thể tách file payload sang bảng riêng hoặc object storage để giảm footprint của các truy vấn metadata. Cần cân nhắc transaction consistency, backup, authorization và lifecycle file.

## 35. Storage strategy và workload đọc

### 35.1. EXTENDED

Thường phù hợp dữ liệu text/jsonb có khả năng nén tốt và không phải lúc nào cũng đọc một phần.

### 35.2. EXTERNAL

Có thể hữu ích với dữ liệu không nén được hoặc pattern cần truy cập substring mà không muốn giải nén cả datum trong một số trường hợp. Đổi lại storage có thể tăng.

### 35.3. MAIN

Có thể giữ giá trị nén inline nếu vừa page, nhưng không phải chiến lược chung để giảm TOAST relation trong mọi tình huống.

### 35.4. PLAIN

Chỉ dùng khi semantics/kiểu dữ liệu yêu cầu; không ép các trường văn bản lớn sang PLAIN để “loại bỏ TOAST”.

### 35.5. Đo trước/sau

Thử trên dữ liệu representative, đo pg_total_relation_size, TOAST size, latency đọc và CPU. Không chọn storage chỉ dựa trên một microbenchmark không đại diện.

## 36. ALTER STORAGE và dữ liệu hiện hữu

Ví dụ:

~~~sql
ALTER TABLE storage_lab.documents
ALTER COLUMN body SET STORAGE EXTERNAL;
~~~

### 36.1. Đây là thuộc tính cột

Storage strategy được lưu trong metadata cột, không phải một lệnh rewrite toàn bộ relation.

### 36.2. Row cũ không tự đổi

Những datum đã lưu có thể giữ representation cũ. Những giá trị được insert/update sau khi thay đổi mới áp dụng strategy mới.

### 36.3. Muốn rewrite cần kế hoạch riêng

Có thể cập nhật lại các rows có chủ đích hoặc dùng thao tác rewrite thích hợp, nhưng sẽ tạo WAL, locks, disk usage tạm và tải hệ thống.

### 36.4. Không chạy UPDATE cột bằng chính nó một cách mù quáng

~~~sql
UPDATE storage_lab.documents
SET body = body;
~~~

Có thể rewrite nhiều rows và kích hoạt triggers/index maintenance dù nội dung không đổi. Nếu cần chuyển storage/compression, đánh giá kỹ phương án rewrite và test trước.

## 37. TOAST, compression và backup

### 37.1. Logical dump

pg_dump đọc giá trị logic của bảng, bao gồm các giá trị đã TOAST, và xuất chúng theo định dạng dump. Nó không cần người dùng tự copy các file pg_toast riêng.

### 37.2. Physical backup

Physical backup bảo toàn cấu trúc storage theo phương án backup/restore phù hợp PostgreSQL. Không tự copy riêng một TOAST relation rồi mong có thể restore độc lập.

### 37.3. Export CSV

COPY TO/\copy TO xuất giá trị logic của các cột được chọn. Khi xuất body, PostgreSQL giải mã representation TOAST để trả nội dung theo format.

### 37.4. Compression layers

Nếu payload đã là ZIP/JPEG rồi còn được nén trong TOAST, lợi ích có thể nhỏ. Backup cũng có thể có compression riêng; tránh suy dung lượng backup trực tiếp từ pg_total_relation_size.

## 38. Đo dung lượng database và top tables

### 38.1. Kích thước database

~~~sql
SELECT
    current_database() AS database_name,
    pg_size_pretty(
        pg_database_size(current_database())
    ) AS database_size;
~~~

### 38.2. Top user tables theo total size

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    pg_size_pretty(
        pg_total_relation_size(
            quote_ident(schemaname) || '.' || quote_ident(relname)
        )
    ) AS total_size,
    pg_total_relation_size(
        quote_ident(schemaname) || '.' || quote_ident(relname)
    ) AS total_bytes
FROM pg_stat_user_tables
ORDER BY total_bytes DESC
LIMIT 20;
~~~

### 38.3. Top index size

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(
        pg_relation_size(
            quote_ident(schemaname) || '.' || quote_ident(indexname)
        )
    ) AS index_size
FROM pg_indexes
ORDER BY pg_relation_size(
    quote_ident(schemaname) || '.' || quote_ident(indexname)
) DESC
LIMIT 20;
~~~

### 38.4. Cần phân biệt database/schema/table

Khi báo cáo, ghi rõ scope:

- Database total.
- Schema total (cần cộng các relation có kiểm soát).
- Table total.
- Heap only.
- Indexes.
- TOAST.

Không cộng các con số đã bao hàm lẫn nhau.

## 39. Tính tăng trưởng theo thời gian

Một lần chụp size chỉ cho biết hiện tại. Muốn hiểu growth, cần lưu snapshot định kỳ.

### 39.1. Bảng snapshot ví dụ

~~~sql
CREATE TABLE storage_lab.size_snapshots (
    sampled_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    relation_name text NOT NULL,
    heap_bytes bigint NOT NULL,
    table_bytes bigint NOT NULL,
    index_bytes bigint NOT NULL,
    total_bytes bigint NOT NULL
);
~~~

### 39.2. Ghi snapshot

~~~sql
INSERT INTO storage_lab.size_snapshots (
    relation_name, heap_bytes, table_bytes,
    index_bytes, total_bytes
)
SELECT
    'storage_lab.documents',
    pg_relation_size('storage_lab.documents'),
    pg_table_size('storage_lab.documents'),
    pg_indexes_size('storage_lab.documents'),
    pg_total_relation_size('storage_lab.documents');
~~~

### 39.3. Chênh lệch giữa hai lần chụp

~~~sql
SELECT
    sampled_at,
    total_bytes,
    total_bytes - lag(total_bytes) OVER (
        ORDER BY sampled_at
    ) AS growth_bytes
FROM storage_lab.size_snapshots
WHERE relation_name = 'storage_lab.documents'
ORDER BY sampled_at;
~~~

### 39.4. Kết hợp workload

Để giải thích growth, lưu thêm:

- Insert/update/delete rates.
- Dead tuple estimates.
- Vacuum/analyze timestamps.
- Index sizes.
- Batch import volumes.
- DDL/partition changes.
- Retention and data lifecycle.

### 39.5. Snapshot có overhead

Bảng snapshot cũng tăng kích thước; đặt retention, partition hoặc aggregate theo ngày/tuần khi monitoring lâu dài.

## 40. Chẩn đoán các mẫu tăng dung lượng

| Quan sát | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| Heap tăng, row count ổn định | Update churn, dead tuples, free space | pg_stat_user_tables, vacuum, pgstattuple |
| Index tăng nhanh | Nhiều index entries, GIN growth, bloat | Đo từng index, usage stats, query workload |
| TOAST tăng nhanh | JSON/text/bytea lớn hoặc thường xuyên thay đổi | reltoastrelid, pg_column_size, data profile |
| Total tăng nhưng table size ổn định | Index tăng | pg_indexes_size |
| Table size tăng nhưng heap main ổn định | TOAST hoặc forks phụ tăng | Đo TOAST relation và forks |
| Database tăng nhưng top table không tăng | Catalog, other schema, temp/other relations | Database/schema inventory |
| File không giảm sau DELETE | Space được giữ để reuse | VACUUM thường vs rewrite |
| Export nhỏ hơn table total | CSV không mang index/page overhead | Phân biệt logical data và physical storage |

### 40.1. Không kết luận TOAST chỉ từ heap nhỏ

Heap nhỏ có thể đơn giản do ít rows. Phải kiểm tra reltoastrelid và TOAST size trước khi kết luận.

### 40.2. Không kết luận bloat chỉ từ total size

Một index lớn có thể hữu ích và đầy dữ liệu sống. Bloat cần bằng chứng về live/dead density hoặc cấu trúc index.

### 40.3. Không kết luận disk leak chỉ từ size không giảm

PostgreSQL giữ free pages để tái sử dụng. File size ổn định sau VACUUM thường là behavior bình thường.

## 41. Các lưu ý về storage parameters

Một số tham số ảnh hưởng cách PostgreSQL sử dụng dung lượng:

- fillfactor: mức lấp đầy mục tiêu của heap/index.
- toast_tuple_target: mục tiêu kích thước tuple sau TOAST processing ở những phiên bản hỗ trợ.
- Storage strategy của cột: PLAIN, MAIN, EXTERNAL, EXTENDED.
- Compression method: pglz, lz4 nếu build/server hỗ trợ.

### 41.1. Xem reloptions

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.reloptions
FROM pg_class AS c
WHERE c.oid = 'storage_lab.documents'::regclass;
~~~

### 41.2. Xem storage của cột

~~~sql
SELECT
    attname,
    attstorage
FROM pg_attribute
WHERE attrelid = 'storage_lab.documents'::regclass
  AND attnum > 0
  AND NOT attisdropped;
~~~

### 41.3. Storage strategy không thay type

ALTER COLUMN ... SET STORAGE không đổi text thành varchar hoặc bytea; nó điều chỉnh cách PostgreSQL lưu giá trị có hỗ trợ TOAST.

### 41.4. Fillfactor thấp hơn không luôn giảm disk

Fillfactor 70 có thể giúp UPDATE nhưng tạo nhiều page hơn khi nạp ban đầu. Đánh giá write/read ratio và page utilization thực tế.

## 42. Index fillfactor và page splits

Index có fillfactor riêng cho một số access methods, ví dụ B-tree:

~~~sql
CREATE INDEX documents_title_idx
ON storage_lab.documents (title)
WITH (fillfactor = 80);
~~~

### 42.1. Page split

Khi B-tree leaf page không còn chỗ cho key mới, PostgreSQL có thể split page. Pattern insert/update ngẫu nhiên có thể tạo hình thái page occupancy khác append-only workload.

### 42.2. Fillfactor index

Để trống chỗ trong page khi build index có thể giảm một số page splits trong workload cập nhật, nhưng index ban đầu có thể lớn hơn.

### 42.3. REINDEX có thể làm size thay đổi

Build lại index từ dữ liệu hiện có có thể tạo page layout khác, do đó size sau REINDEX có thể giảm hoặc tăng tùy dữ liệu và fillfactor.

### 42.4. Không dùng một ngưỡng bloat cho mọi access method

B-tree, GIN, GiST và BRIN có cấu trúc/maintenance khác nhau. Công cụ đo phải hiểu loại index.

## 43. Dữ liệu TOAST và index GIN

Một cột JSONB có thể vừa được TOAST vừa được index GIN:

~~~sql
CREATE INDEX documents_metadata_gin
ON storage_lab.documents
USING gin (metadata);
~~~

### 43.1. Hai cấu trúc độc lập

- TOAST lưu representation của giá trị lớn.
- GIN lưu cấu trúc tra cứu các key/token của JSONB.

### 43.2. GIN không thay TOAST

Index giúp tìm hàng theo biểu thức/query, nhưng PostgreSQL vẫn cần truy xuất giá trị JSONB khi query cần trả payload hoặc đánh giá điều kiện còn lại.

### 43.3. Cột lớn có thể tăng cả hai

Một JSONB rất nhiều keys có thể tăng TOAST data và GIN entries cùng lúc. Chỉ nhìn pg_table_size sẽ bỏ sót index contribution; chỉ nhìn pg_indexes_size sẽ bỏ sót TOAST.

### 43.4. Chọn operator class

GIN JSONB có các operator classes như jsonb_ops và jsonb_path_ops với trade-offs về loại query hỗ trợ và index size. Chọn theo workload thực tế, không mặc định một loại luôn nhỏ hơn/tốt hơn.

## 44. Những hiểu lầm thường gặp

### Lỗi 1. pg_relation_size là toàn bộ dung lượng bảng

Mặc định nó đo main fork của relation; chưa bao gồm mọi index/TOAST/fork khác như total.

### Lỗi 2. pg_table_size bao gồm mọi index

Không. Nó đo table storage/TOAST/forks; dùng pg_indexes_size() để xem indexes gắn với bảng.

### Lỗi 3. pg_total_relation_size chỉ là heap + index thường

Nó tính cả TOAST storage liên quan và các thành phần theo định nghĩa hàm.

### Lỗi 4. TOAST là compression

TOAST là cơ chế lưu oversized attributes; compression là một phần có thể được dùng trong quy trình.

### Lỗi 5. Mọi cột text đều nằm trong TOAST

Giá trị nhỏ thường được lưu inline. Chỉ các giá trị/tuple cần xử lý oversized mới được nén/đẩy ngoài.

### Lỗi 6. TOAST lưu toàn bộ hàng

TOAST lưu các giá trị cột lớn, không thay thế toàn bộ heap row.

### Lỗi 7. TOAST index là index nghiệp vụ

Đó là cấu trúc nội bộ để định vị chunks, khác index do ứng dụng tạo.

### Lỗi 8. Nhiều row hơn chắc chắn relation lớn hơn theo tỷ lệ

Kích thước mỗi row, compression, index và dead tuples làm tỷ lệ khác nhau.

### Lỗi 9. DELETE làm file giảm ngay

DELETE tạo dead tuples; VACUUM thường tái sử dụng space, không nhất thiết trả file cho OS.

### Lỗi 10. VACUUM thường tương đương VACUUM FULL

VACUUM thường cleanup/reuse; VACUUM FULL rewrite relation và yêu cầu lock mạnh.

### Lỗi 11. REINDEX thu nhỏ heap

REINDEX chỉ xây lại index, không trực tiếp rewrite heap/TOAST của bảng.

### Lỗi 12. ANALYZE làm file nhỏ lại

ANALYZE cập nhật planner statistics, không phải công cụ thu hồi dung lượng relation.

### Lỗi 13. pg_column_size bằng dung lượng TOAST

Nó đo datum representation, không phải toàn bộ TOAST relation/index.

### Lỗi 14. pg_class.reltuples là count chính xác

Đây là estimate/stats, không tương đương COUNT(*) tại một snapshot cụ thể.

### Lỗi 15. Index lớn là index bloat

Index có thể lớn vì số entry/keys cần lưu. Phải đo density/usage và workload.

### Lỗi 16. Bảng có nhiều index luôn nhanh hơn

Index giúp đọc nhưng tăng write cost, storage và maintenance.

### Lỗi 17. JSONB update nhỏ chỉ ghi vài bytes

Một thao tác tạo JSONB result mới có thể có chi phí lớn, gồm TOAST rewrite và GIN index maintenance.

### Lỗi 18. EXTERNAL luôn tiết kiệm CPU và disk

Nó không nén, có thể giảm decompression nhưng làm dữ liệu lớn hơn.

### Lỗi 19. Đổi SET STORAGE rewrite toàn bộ dữ liệu

Không; thay đổi strategy chủ yếu áp dụng cho values được lưu/cập nhật về sau.

### Lỗi 20. Đổi COMPRESSION nén lại mọi row ngay

Không. Cần một kế hoạch rewrite/update nếu muốn chuyển representation của dữ liệu cũ.

### Lỗi 21. pg_total_relation_size(parent partition) là cách duy nhất đo partitions

Parent partitioned table không có heap như ordinary table. Đo leaf partitions và tổng hợp rõ ràng để tránh bỏ sót/đếm trùng.

### Lỗi 22. WAL nằm trong pg_total_relation_size

WAL là storage riêng, không nằm trong size của relation bảng.

### Lỗi 23. File CSV export bằng size table total

CSV chứa dữ liệu logic được chọn, không mang page/tuple/index/TOAST overhead vật lý như relation.

### Lỗi 24. Xóa file relation bằng OS để thu hồi disk

Sẽ làm hỏng database. Dùng lệnh PostgreSQL có kiểm soát.

## 45. Bài tập thực hành

Các bài dựa trên schema storage_lab hoặc các ví dụ SQL trong bài. Những thao tác VACUUM FULL, REINDEX và thay storage strategy nên thử trên database lab, không chạy trên production chỉ để quan sát.

### Bài 1. Bốn hàm size

Phân biệt pg_relation_size, pg_table_size, pg_indexes_size và pg_total_relation_size.

### Bài 2. Main fork

Nếu gọi pg_relation_size('app.orders') không truyền fork, PostgreSQL đo phần nào?

### Bài 3. Heap và index

Vì sao pg_table_size có thể nhỏ hơn pg_total_relation_size?

### Bài 4. TOAST

TOAST viết tắt của gì và giải quyết vấn đề lưu trữ nào?

### Bài 5. Varlena

Kể tên bốn kiểu dữ liệu PostgreSQL thường có thể dùng TOAST.

### Bài 6. External storage

Một heap tuple có external TOAST pointer nghĩa là gì?

### Bài 7. Chunk

Vì sao một giá trị TOAST lớn có thể được chia thành nhiều chunks?

### Bài 8. TOAST index

TOAST index phục vụ mục đích gì?

### Bài 9. PLAIN

Storage strategy PLAIN cho phép compression hoặc externalization không?

### Bài 10. EXTENDED

EXTENDED hỗ trợ hai hành vi nào?

### Bài 11. MAIN

MAIN khác EXTENDED thế nào trong quyết định externalize?

### Bài 12. EXTERNAL

EXTERNAL có nén giá trị không?

### Bài 13. Compression

Vì sao một chuỗi lặp dài có thể chiếm ít storage hơn octet_length()?

### Bài 14. pg_column_size

Vì sao không cộng pg_column_size() của mọi row rồi coi đó là total relation size?

### Bài 15. TOAST relation

Viết SQL lấy reltoastrelid của storage_lab.documents và đo pg_total_relation_size của nó.

### Bài 16. Index list

Viết SQL liệt kê từng index của storage_lab.documents và dung lượng bytes.

### Bài 17. Forks

Kể tên main, fsm, vm và init fork; mỗi loại phục vụ điều gì?

### Bài 18. MVCC

Vì sao UPDATE có thể làm heap tăng dù số rows visible không đổi?

### Bài 19. DELETE

Vì sao DELETE nhiều rows không nhất thiết làm file relation nhỏ ngay?

### Bài 20. VACUUM

VACUUM thường khác VACUUM FULL thế nào?

### Bài 21. REINDEX

REINDEX có thu nhỏ heap table không?

### Bài 22. ANALYZE

ANALYZE thay đổi dữ liệu relation hay planner statistics?

### Bài 23. Index size

Nêu ba lý do một GIN index JSONB có thể lớn hơn B-tree primary key.

### Bài 24. HOT

Hai điều kiện quan trọng giúp UPDATE trở thành HOT update là gì?

### Bài 25. Fillfactor

Vì sao fillfactor thấp hơn có thể hỗ trợ HOT update nhưng tăng dung lượng ban đầu?

### Bài 26. Catalog

pg_class.reltoastrelid cho biết điều gì?

### Bài 27. attstorage

pg_attribute.attstorage cho biết thuộc tính nào?

### Bài 28. Partitioning

Vì sao nên đo các leaf partitions thay vì so sánh parent relkind='p' như heap table thường?

### Bài 29. WAL

WAL có nằm trong pg_total_relation_size('table') không?

### Bài 30. pg_stat_user_tables

Viết query xem n_live_tup, n_dead_tup, last_autovacuum cho schema storage_lab.

### Bài 31. pg_statio

Hai cột nào cho biết TOAST block reads/hits?

### Bài 32. pgstattuple

Extension pgstattuple có thể cung cấp những thông tin nào hữu ích khi điều tra bloat?

### Bài 33. JSONB

Vì sao một thay đổi nhỏ trong JSONB có thể tạo chi phí TOAST và GIN index đáng kể?

### Bài 34. SET STORAGE

Sau ALTER COLUMN body SET STORAGE EXTERNAL, các giá trị cũ có tự rewrite không?

### Bài 35. Compression

Vì sao thay compression method không tự nén lại mọi row?

### Bài 36. Đo size

Viết query hiển thị heap main, table storage, indexes và total cho storage_lab.documents.

### Bài 37. Index ratio

Viết biểu thức tính phần trăm index size trên total size.

### Bài 38. Growth

Nêu ít nhất bốn loại thông tin nên lưu cùng snapshot size để giải thích tăng trưởng.

### Bài 39. Query projection

Vì sao SELECT document_id, title thường có thể nhẹ hơn SELECT * với bảng có body/payload TOAST lớn?

### Bài 40. Chọn phương án

Một bảng có total size tăng nhanh nhưng heap main ổn định. Nêu thứ tự điều tra các thành phần có khả năng tăng.

## 46. Lời giải tham khảo

### Bài 1–3. Size functions

- pg_relation_size: size của relation/fork được chỉ định, mặc định main.
- pg_table_size: table storage, gồm TOAST và forks phụ theo cách PostgreSQL tính.
- pg_indexes_size: indexes gắn với bảng.
- pg_total_relation_size: table storage cộng indexes.

Total thường lớn hơn table khi bảng có indexes.

### Bài 4–8. TOAST

TOAST là *The Oversized-Attribute Storage Technique*, giúp xử lý các giá trị biến độ dài lớn bằng compression và/hoặc external storage. Các chunks lưu trong TOAST table; TOAST index định vị chúng; heap tuple giữ pointer khi giá trị được externalize.

### Bài 9–12. Storage strategies

| Strategy | Nén | External |
| --- | --- | --- |
| PLAIN | Không | Không |
| MAIN | Có | Chỉ khi cần để tuple vừa |
| EXTENDED | Có | Có |
| EXTERNAL | Không | Có |

### Bài 13–14. Logical và physical size

Chuỗi lặp có thể nén mạnh nên datum representation nhỏ hơn số bytes nội dung. Tổng các datum size không bao gồm page/tuple/line pointer overhead, free space, dead tuples, indexes, TOAST index và forks.

### Bài 15. TOAST

~~~sql
SELECT
    c.reltoastrelid::regclass AS toast_table,
    pg_total_relation_size(c.reltoastrelid) AS toast_bytes
FROM pg_class AS c
WHERE c.oid = 'storage_lab.documents'::regclass
  AND c.reltoastrelid <> 0;
~~~

### Bài 16. Index list

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    pg_relation_size(indexrelid) AS bytes
FROM pg_index
WHERE indrelid = 'storage_lab.documents'::regclass
ORDER BY bytes DESC;
~~~

### Bài 17. Forks

main lưu dữ liệu chính; fsm quản lý ước lượng free space; vm quản lý visibility/all-frozen flags; init phục vụ khôi phục trạng thái ban đầu của unlogged relation.

### Bài 18–19. MVCC

UPDATE thường tạo tuple version mới và giữ version cũ tới khi không còn snapshot cần. DELETE đánh dấu tuple không còn visible; VACUUM mới cleanup/reuse, file không nhất thiết trả lại cho OS.

### Bài 20–22. Maintenance

VACUUM thường dọn/reuse dead tuples; VACUUM FULL rewrite relation và cần lock mạnh. REINDEX xây lại indexes, không rewrite heap. ANALYZE cập nhật planner statistics.

### Bài 23. GIN size

GIN có thể index nhiều JSON keys/tokens mỗi row, lưu cấu trúc posting lists và page metadata; nó không tương đương một entry cho mỗi row như primary key B-tree.

### Bài 24–25. HOT và fillfactor

HOT có thể áp dụng khi không đổi cột được index tham chiếu và page còn đủ chỗ cho tuple mới (cùng các điều kiện kỹ thuật liên quan). Fillfactor thấp để lại chỗ trong page, hỗ trợ update nhưng giảm mật độ tuple ban đầu.

### Bài 26–27. Catalog

reltoastrelid là OID của TOAST relation phụ; attstorage lưu storage strategy của cột như PLAIN/MAIN/EXTERNAL/EXTENDED.

### Bài 28–29. Partition và WAL

Partitioned parent là metadata relation, dữ liệu nằm trong leaf partitions. WAL thuộc pg_wal, không nằm trong total size của bảng.

### Bài 30. Table stats

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'storage_lab';
~~~

### Bài 31. TOAST I/O

toast_blks_read và toast_blks_hit trong pg_statio_user_tables.

### Bài 32. pgstattuple

Có thể cho biết table length, live tuple count/length, dead tuple count/length và free space; các scan có chi phí và cần quyền/extension phù hợp.

### Bài 33. JSONB

JSONB là datum có representation riêng; thay đổi có thể tạo giá trị mới, TOAST value mới và GIN entries mới, dẫn tới heap/TOAST/index write amplification.

### Bài 34–35. Storage/compression change

Không. Thay storage strategy/compression ảnh hưởng các giá trị ghi/cập nhật sau đó; dữ liệu cũ cần một kế hoạch rewrite/update có kiểm soát nếu muốn chuyển representation.

### Bài 36. Size breakdown

~~~sql
SELECT
    pg_relation_size('storage_lab.documents') AS heap_main,
    pg_table_size('storage_lab.documents') AS table_bytes,
    pg_indexes_size('storage_lab.documents') AS index_bytes,
    pg_total_relation_size('storage_lab.documents') AS total_bytes;
~~~

### Bài 37. Index ratio

~~~sql
SELECT round(
    100.0 * pg_indexes_size('storage_lab.documents')
    / NULLIF(
        pg_total_relation_size('storage_lab.documents'), 0
    ),
    2
) AS index_percent;
~~~

### Bài 38. Growth context

Ví dụ: live/dead tuple estimates, insert/update/delete rates, vacuum/analyze timestamps, index sizes, TOAST size, partition sizes, batch imports và workload changes.

### Bài 39. Projection

Khi không chọn các cột lớn, PostgreSQL thường không cần fetch/detoast các giá trị đó cho kết quả; giảm I/O, CPU decompression và bytes truyền về client.

### Bài 40. Điều tra

Đo pg_indexes_size trước, liệt kê từng index; kiểm tra TOAST relation và auxiliary forks; xem update/dead tuple stats, index growth, partition changes và maintenance history. Sau đó mới kết luận thành phần nào tăng và chọn hành động phù hợp.

## 47. Bảng tra cứu nhanh

| Nhu cầu | Công cụ |
| --- | --- |
| Đo main heap fork | pg_relation_size(table) |
| Đo fork cụ thể | pg_relation_size(table, 'fsm') hoặc 'vm' |
| Đo table + TOAST | pg_table_size(table) |
| Đo các index của bảng | pg_indexes_size(table) |
| Đo tổng table + index | pg_total_relation_size(table) |
| Định dạng bytes | pg_size_pretty(bytes) |
| Đo toàn database | pg_database_size(db) |
| Xem TOAST OID | pg_class.reltoastrelid |
| Xem storage strategy | pg_attribute.attstorage |
| Xem compression metadata | pg_attribute.attcompression ở version hỗ trợ |
| Đo datum representation | pg_column_size(value) |
| Đo text logical bytes | octet_length(text) |
| Xem compression method của datum | pg_column_compression(value) ở version hỗ trợ |
| Liệt kê index relation | pg_index.indexrelid |
| Xem index definition | pg_get_indexdef() |
| Xem dead tuple estimate | pg_stat_user_tables.n_dead_tup |
| Xem TOAST I/O | pg_statio_user_tables.toast_blks_* |
| Đo live/dead/free space sâu | Extension pgstattuple |
| Dọn dead tuples/reuse | VACUUM |
| Rewrite heap để thu nhỏ | VACUUM FULL hoặc công cụ rewrite phù hợp |
| Xây lại index | REINDEX |
| Cập nhật planner stats | ANALYZE |
| Xem relation file path | pg_relation_filepath() |
| Xem filenode | pg_relation_filenode() |
| Đo leaf partitions | pg_partition_tree() + size functions |

## 48. Checklist điều tra kích thước bảng tăng bất thường

1. **Xác định đúng scope:** database, schema, table, partition, heap hay total?
2. Ghi nhận byte size bằng các hàm PostgreSQL, không chỉ pg_size_pretty.
3. Tách pg_relation_size, pg_table_size, pg_indexes_size và pg_total_relation_size.
4. Kiểm tra table có reltoastrelid hay không.
5. Đo riêng TOAST relation và tránh đếm trùng TOAST trong table size.
6. Liệt kê từng index, access method và definition.
7. Xem index có GIN/INCLUDE/expressions hoặc keys dài không.
8. Kiểm tra n_live_tup, n_dead_tup, update/delete churn.
9. Xem lần vacuum/analyze gần nhất và autovacuum behavior.
10. Kiểm tra long-running transactions/replication slots giữ dead tuples.
11. Xem FSM/VM forks nếu table size thay đổi nhưng heap main ít đổi.
12. So sánh logical payload (octet_length) với datum representation (pg_column_size).
13. Kiểm tra storage strategy/compression của các cột varlena.
14. Xác định payload JSONB/text/bytea nào lớn hoặc bị cập nhật thường xuyên.
15. Xem TOAST I/O và query có vô tình SELECT * không.
16. Xem partition sizes và không cộng parent/leaf hai lần.
17. Xem fillfactor và pattern HOT update.
18. Kiểm tra index usage/query plans trước khi drop index.
19. Nếu nghi bloat, dùng công cụ đo phù hợp như pgstattuple và đánh giá chi phí scan.
20. Chọn VACUUM, REINDEX hay rewrite theo đúng relation cần xử lý.
21. Đánh giá disk headroom và dung lượng tạm trước VACUUM FULL/rewrite.
22. Đánh giá locks, replication lag, WAL và backup trước maintenance.
23. Không xóa/move relation files bằng thao tác hệ điều hành.
24. Ghi snapshot định kỳ để thấy xu hướng, không chỉ một điểm đo.
25. Sau thay đổi, đo lại cùng scope và cùng phương pháp để so sánh.

## 49. Tổng kết

Kích thước một bảng PostgreSQL là tổng hợp của nhiều cấu trúc vật lý:

- **Heap** lưu các tuple và chịu ảnh hưởng của page layout, MVCC versions, dead tuples, free space và fillfactor.
- **Indexes** là các relation riêng; số lượng, loại access method và nội dung index có thể khiến tổng dung lượng tăng rất lớn.
- **TOAST** xử lý các giá trị varlena quá lớn bằng compression và/hoặc external storage trong relation phụ, cùng TOAST index.
- **FSM/VM/init forks** và các thành phần phụ trợ cũng có thể góp phần vào table storage.

Khi đo, hãy phân biệt pg_relation_size() (main fork mặc định), pg_table_size() (table storage cùng TOAST/forks), pg_indexes_size() (indexes) và pg_total_relation_size() (tổng). Khi điều tra sâu, kết hợp pg_class.reltoastrelid, pg_attribute.attstorage, pg_column_size(), pg_stat_user_tables, pg_statio_user_tables và công cụ như pgstattuple nếu cần.

**Đừng dùng một con số total để đoán nguyên nhân.** Heap tăng, index tăng, TOAST tăng và dead tuples tăng là những hiện tượng khác nhau, cần những biện pháp khác nhau. VACUUM thường giúp tái sử dụng không gian; VACUUM FULL rewrite heap; REINDEX xây lại index; ANALYZE cập nhật statistics. Chọn đúng công cụ sau khi đo và đánh giá locks, WAL, disk headroom, replication cùng workload.

Một cách tiếp cận đáng tin cậy là **đo từng thành phần → xác định kiểu dữ liệu/workload tạo tăng trưởng → xem MVCC/TOAST/index behavior → chọn maintenance đúng relation → đo lại sau thay đổi**. Nhờ đó, quyết định lưu trữ dựa trên cấu trúc PostgreSQL thực sự sử dụng thay vì chỉ dựa vào số lượng hàng hoặc dung lượng file CSV.
