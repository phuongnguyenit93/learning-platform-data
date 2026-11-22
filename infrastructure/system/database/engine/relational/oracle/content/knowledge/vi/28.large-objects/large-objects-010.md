# Đo dung lượng, truy vấn metadata và xử lý rò rỉ temporary LOB

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** LOB và dữ liệu lớn  
> **Mục tiêu:** Phân biệt kích thước logic của LOB với dung lượng segment được cấp; truy vấn metadata LOB và segment trong data dictionary; kiểm tra BasicFiles, SecureFiles, lưu trữ IN ROW/OUT OF ROW và partitioned LOB; theo dõi temporary LOB theo session; quản lý vòng đời bằng DBMS_LOB.CREATETEMPORARY, ISTEMPORARY và FREETEMPORARY; phát hiện và xử lý temporary LOB leak trong procedure, package và ứng dụng dùng connection pool.

## 1. LOB có nhiều khái niệm dung lượng khác nhau

LOB (Large Object) lưu nội dung lớn như tài liệu, ảnh, âm thanh, JSON hoặc văn bản dài. Khi điều tra dung lượng, cần phân biệt ba đại lượng:

1. **Logical length:** độ dài nội dung mà ứng dụng nhìn thấy, đo bằng DBMS_LOB.GETLENGTH.
2. **Allocated segment space:** số byte extent Oracle đã cấp cho segment lưu LOB, xem qua USER_SEGMENTS/DBA_SEGMENTS.
3. **Temporary LOB usage:** temporary LOB đang được một session sử dụng và dung lượng temporary tablespace liên quan.

Ba con số này không nhất thiết bằng nhau. Một CLOB dài 1 triệu ký tự không đồng nghĩa nó chiếm đúng 1 MB trên đĩa. Character set, lưu trữ IN ROW, LOB chunk, phiên bản dữ liệu, SecureFiles compression/deduplication, free space trong segment và extent allocation đều có thể làm dung lượng vật lý khác logical length.

Đặc biệt, temporary LOB không phải persistent LOB được lưu trong cột bảng. Temporary LOB có vòng đời gắn với call hoặc session và thường sử dụng temporary tablespace. Không thể tìm chúng bằng cách chỉ truy vấn USER_LOBS.

## 2. Phân biệt BLOB, CLOB, NCLOB và BFILE

| Kiểu | Nội dung | Đơn vị của DBMS_LOB.GETLENGTH |
|---|---|---|
| BLOB | Dữ liệu nhị phân | Byte |
| CLOB | Văn bản theo database character set | Ký tự |
| NCLOB | Văn bản theo national character set | Ký tự |
| BFILE | File nhị phân bên ngoài database | Byte |

Ví dụ:

~~~sql
SELECT document_id,
       DBMS_LOB.GETLENGTH(file_blob) AS blob_bytes,
       DBMS_LOB.GETLENGTH(content_clob) AS clob_characters
FROM documents;
~~~

BLOB length có thể được hiểu là số byte nội dung. CLOB/NCLOB length là số ký tự theo semantics LOB; số byte lưu trữ phụ thuộc character set và cách mã hóa.

Không lấy kết quả GETLENGTH của CLOB rồi chia 1024 để kết luận chính xác số KB trên storage. Đó chỉ là phép quy đổi số ký tự sang một đơn vị số học, không phải dung lượng vật lý.

### 2.1. NULL LOB và empty LOB

Hai trạng thái này khác nhau:

- NULL LOB: cột không có locator/nội dung LOB.
- Empty LOB: có locator LOB hợp lệ nhưng nội dung có độ dài 0.

Ví dụ:

~~~sql
INSERT INTO documents(document_id, content_clob, file_blob)
VALUES (1, NULL, NULL);

INSERT INTO documents(document_id, content_clob, file_blob)
VALUES (2, EMPTY_CLOB(), EMPTY_BLOB());
~~~

Có thể kiểm tra:

~~~sql
SELECT document_id,
       CASE WHEN content_clob IS NULL THEN 'NULL' ELSE 'NOT NULL' END AS clob_state,
       DBMS_LOB.GETLENGTH(content_clob) AS clob_length
FROM documents
ORDER BY document_id;
~~~

Với LOB NULL, GETLENGTH trả NULL. Với empty LOB, length là 0. Khi phân tích thống kê, cần đếm riêng số hàng NULL, số hàng có locator và tổng logical length.

## 3. Đo logical length của LOB trong bảng

Giả sử bảng DOCUMENTS có BLOB FILE_CONTENT và CLOB DESCRIPTION.

### 3.1. Đo độ dài theo từng hàng

~~~sql
SELECT document_id,
       DBMS_LOB.GETLENGTH(file_content) AS file_bytes,
       DBMS_LOB.GETLENGTH(description) AS description_characters
FROM documents
ORDER BY document_id;
~~~

Query giúp tìm hàng có LOB lớn bất thường. Với bảng rất lớn, thêm predicate, partition pruning hoặc giới hạn mẫu để tránh quét toàn bộ dữ liệu chỉ nhằm thống kê.

### 3.2. Tổng logical length

~~~sql
SELECT COUNT(*) AS row_count,
       COUNT(file_content) AS nonnull_blob_count,
       SUM(DBMS_LOB.GETLENGTH(file_content)) AS total_blob_bytes,
       COUNT(description) AS nonnull_clob_count,
       SUM(DBMS_LOB.GETLENGTH(description)) AS total_clob_characters
FROM documents;
~~~

SUM bỏ qua NULL. Vì vậy TOTAL_BLOB_BYTES chỉ cộng độ dài các BLOB không NULL; empty BLOB đóng góp 0.

### 3.3. Tìm LOB lớn nhất

~~~sql
SELECT document_id,
       DBMS_LOB.GETLENGTH(file_content) AS file_bytes
FROM documents
WHERE file_content IS NOT NULL
ORDER BY DBMS_LOB.GETLENGTH(file_content) DESC
FETCH FIRST 20 ROWS ONLY;
~~~

FETCH FIRST yêu cầu phiên bản Oracle hỗ trợ row limiting clause. Với release cũ, có thể bọc truy vấn và dùng ROWNUM.

Nếu cần tìm CLOB lớn nhất theo số ký tự, dùng GETLENGTH trên CLOB; nếu cần byte thực tế đã mã hóa, phải tính đến character set và storage representation.

### 3.4. Phân bố kích thước

Có thể phân nhóm theo logical length:

~~~sql
SELECT CASE
           WHEN file_content IS NULL THEN 'NULL'
           WHEN DBMS_LOB.GETLENGTH(file_content) = 0 THEN 'EMPTY'
           WHEN DBMS_LOB.GETLENGTH(file_content) < 1024 THEN '< 1 KB'
           WHEN DBMS_LOB.GETLENGTH(file_content) < 1048576 THEN '1 KB - 1 MB'
           ELSE '>= 1 MB'
       END AS size_bucket,
       COUNT(*) AS document_count
FROM documents
GROUP BY
    CASE
        WHEN file_content IS NULL THEN 'NULL'
        WHEN DBMS_LOB.GETLENGTH(file_content) = 0 THEN 'EMPTY'
        WHEN DBMS_LOB.GETLENGTH(file_content) < 1024 THEN '< 1 KB'
        WHEN DBMS_LOB.GETLENGTH(file_content) < 1048576 THEN '1 KB - 1 MB'
        ELSE '>= 1 MB'
    END
ORDER BY size_bucket;
~~~

Với BLOB, các ngưỡng trên là byte. Với CLOB, đó là ký tự; hãy đổi nhãn bucket cho đúng đơn vị.

## 4. Truy vấn metadata LOB bằng data dictionary

Oracle cung cấp các view theo phạm vi quyền:

- USER_LOBS: LOB column thuộc schema hiện tại.
- ALL_LOBS: LOB column mà user có quyền xem.
- DBA_LOBS: metadata LOB trên toàn database, cần quyền phù hợp.

Ví dụ:

~~~sql
SELECT table_name,
       column_name,
       segment_name,
       index_name,
       tablespace_name,
       chunk,
       pctversion,
       retention,
       cache,
       in_row,
       securefile
FROM user_lobs
ORDER BY table_name, column_name;
~~~

Các trường giúp xác định LOB column được lưu như thế nào và segment/index tương ứng. Một số thuộc tính có ý nghĩa khác nhau tùy BasicFiles hay SecureFiles và Oracle release.

### 4.1. Những metadata cần chú ý

| Thuộc tính | Ý nghĩa |
|---|---|
| TABLE_NAME | Bảng chứa LOB column |
| COLUMN_NAME | Tên LOB column |
| SEGMENT_NAME | Tên LOB data segment đối với cấu hình không partition |
| INDEX_NAME | LOB index liên quan |
| TABLESPACE_NAME | Tablespace lưu LOB segment |
| CHUNK | Kích thước chunk được cấu hình cho LOB storage |
| PCTVERSION | Tham số quản lý old LOB versions của BasicFiles |
| RETENTION | Chính sách retention của LOB versions, thường liên quan SecureFiles |
| CACHE | Thuộc tính cache của LOB storage |
| IN_ROW | Có cho phép lưu LOB nhỏ inline trong row hay không |
| SECUREFILE | Cho biết LOB dùng SecureFiles hay BasicFiles |

Không diễn giải PCTVERSION và RETENTION như dung lượng LOB hiện tại. Đây là thuộc tính quản lý storage/versioning. LOB segment tăng có thể liên quan old versions, retention hoặc DML update lớn chứ không nhất thiết là temporary LOB leak.

### 4.2. Xem DDL của bảng để biết storage clause

~~~sql
SELECT DBMS_METADATA.GET_DDL(
    'TABLE',
    'DOCUMENTS',
    USER
)
FROM dual;
~~~

DDL giúp kiểm tra LOB storage clause, TABLESPACE, ENABLE/DISABLE STORAGE IN ROW, BasicFiles/SecureFiles và các tùy chọn compression/deduplication/encryption nếu có.

DBMS_METADATA cần quyền truy cập metadata phù hợp. Tên object thường được truyền theo chữ hoa nếu object được tạo bằng identifier không quoted.

## 5. Segment size: dung lượng extent đã cấp

USER_SEGMENTS/ALL_SEGMENTS/DBA_SEGMENTS cho biết segment và dung lượng extent đã cấp.

Ví dụ xem segment trong schema:

~~~sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       bytes,
       ROUND(bytes / 1024 / 1024, 2) AS allocated_mb,
       extents
FROM user_segments
WHERE segment_type IN ('LOBSEGMENT', 'LOBINDEX')
ORDER BY bytes DESC;
~~~

LOB data segment và LOB index là hai cấu trúc riêng. Segment type thường thấy là LOBSEGMENT và LOBINDEX.

### 5.1. Ghép USER_LOBS với USER_SEGMENTS

Với LOB không partition, có thể ghép metadata LOB với segment:

~~~sql
SELECT l.table_name,
       l.column_name,
       l.segment_name AS lob_segment,
       l.index_name AS lob_index,
       l.tablespace_name,
       ROUND(NVL(s.bytes, 0) / 1024 / 1024, 2) AS lob_allocated_mb,
       ROUND(NVL(i.bytes, 0) / 1024 / 1024, 2) AS lob_index_mb
FROM user_lobs l
LEFT JOIN user_segments s
       ON s.segment_name = l.segment_name
      AND s.segment_type = 'LOBSEGMENT'
LEFT JOIN user_segments i
       ON i.segment_name = l.index_name
      AND i.segment_type = 'LOBINDEX'
ORDER BY l.table_name, l.column_name;
~~~

Query minh họa cho LOB segment thông thường. Nếu bảng partitioned hoặc subpartitioned, cần dùng các view LOB partition tương ứng để lấy tên segment của từng partition/subpartition; không giả định một SEGMENT_NAME ở USER_LOBS đại diện toàn bộ các segment phân vùng.

### 5.2. Tổng dung lượng LOB theo tablespace

~~~sql
SELECT tablespace_name,
       segment_type,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS allocated_mb,
       COUNT(*) AS segment_count
FROM user_segments
WHERE segment_type IN ('LOBSEGMENT', 'LOBINDEX')
GROUP BY tablespace_name, segment_type
ORDER BY tablespace_name, segment_type;
~~~

Đây là dung lượng đã cấp cho segment, không phải logical payload. Nếu cần tổng cả bảng, index thông thường và LOB, mở rộng danh sách segment type và đối chiếu object metadata để không đếm thiếu hoặc đếm trùng.

### 5.3. Allocated bytes không phải bytes đang chứa dữ liệu hữu ích

USER_SEGMENTS.BYTES phản ánh extent đã cấp. Một segment có thể chứa free space nội bộ, block chưa dùng hoặc vùng trống sau khi LOB bị xóa/thu nhỏ nội dung.

Xóa một hàng hoặc gọi DBMS_LOB.TRIM không nhất thiết làm tablespace file giảm ngay. Segment có thể giữ lại extent để tái sử dụng cho lần ghi sau.

Muốn thu hồi dung lượng về tablespace/file, cần đánh giá shrink/move/reorganization phù hợp với loại LOB, storage format, partition và Oracle release. Không chạy SHRINK/MOVE chỉ vì logical length giảm; trước hết đo free space nội bộ và kiểm tra điều kiện vận hành.

## 6. IN ROW, OUT OF ROW và ảnh hưởng đến phép đo

LOB có thể được lưu inline trong row hoặc ngoài row:

- **IN ROW:** nội dung LOB nhỏ có thể được lưu cùng row trong table segment khi storage cho phép.
- **OUT OF ROW:** row lưu locator; nội dung được lưu trong LOB segment.

Vì vậy, khi IN ROW được bật, không phải mọi byte của LOB đều xuất hiện trong LOBSEGMENT. Một phần dữ liệu nằm trong table segment.

Thuộc tính IN_ROW trong USER_LOBS cho biết cấu hình có cho phép inline storage. Nó không có nghĩa mọi LOB trong bảng chắc chắn đang inline; kích thước từng giá trị và điều kiện storage quyết định vị trí thực tế.

Khi tính tổng dung lượng một bảng chứa LOB, cần xem cả:

1. Table segment/partition.
2. LOB data segment/partition.
3. LOB index segment/partition.
4. Index thông thường và các segment phụ khác.

Không cộng logical GETLENGTH vào allocated segment bytes như thể chúng là hai phần độc lập của cùng một phép đo.

## 7. BasicFiles, SecureFiles và compression/deduplication

Oracle hỗ trợ hai mô hình lưu LOB chính:

- BasicFiles là cơ chế LOB storage truyền thống.
- SecureFiles là cơ chế LOB storage hiện đại hơn, cung cấp các khả năng như compression, deduplication và encryption tùy release/edition/licensing.

SecureFiles có thể giảm dung lượng vật lý nhờ compression hoặc deduplication. Khi đó tổng logical length có thể lớn hơn nhiều so với segment allocation. Encryption, metadata, chunk và free space cũng ảnh hưởng số byte thực tế.

Các thuộc tính như COMPRESSION, DEDUPLICATION, ENCRYPT có thể được xem qua metadata view phù hợp với Oracle release:

~~~sql
SELECT table_name,
       column_name,
       securefile,
       compression,
       deduplication,
       encrypt,
       cache,
       in_row
FROM user_lobs
ORDER BY table_name, column_name;
~~~

Nếu view/version không cung cấp một thuộc tính hoặc quyền không đủ, kiểm tra DDL bằng DBMS_METADATA và tài liệu release đang chạy.

Không kết luận SecureFiles luôn nhỏ hơn BasicFiles trong mọi workload. Compression/deduplication có chi phí CPU, tỷ lệ giảm phụ thuộc nội dung và các tùy chọn có thể có yêu cầu license riêng.

## 8. Partitioned LOB và metadata theo partition

Bảng partitioned có thể có LOB segment riêng cho từng partition hoặc subpartition. Lúc đó dung lượng không nằm trong một segment duy nhất.

Các view thường dùng:

- USER_LOB_PARTITIONS / ALL_LOB_PARTITIONS / DBA_LOB_PARTITIONS.
- USER_LOB_SUBPARTITIONS / ALL_LOB_SUBPARTITIONS / DBA_LOB_SUBPARTITIONS.
- USER_SEGMENTS / DBA_SEGMENTS để xem segment allocation.

Ví dụ xem metadata LOB partition:

~~~sql
SELECT table_name,
       column_name,
       partition_name,
       lob_partition_name,
       lob_indpart_name,
       tablespace_name
FROM user_lob_partitions
WHERE table_name = 'DOCUMENTS'
ORDER BY column_name, partition_name;
~~~

Tên cột và khả năng hiển thị có thể khác theo loại partitioning/release. Dùng DESC USER_LOB_PARTITIONS hoặc tra Data Dictionary Reference đúng phiên bản nếu cần mở rộng query.

Sau đó đối chiếu các tên LOB partition/index partition với USER_SEGMENTS:

~~~sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       ROUND(bytes / 1024 / 1024, 2) AS allocated_mb
FROM user_segments
WHERE segment_type IN ('LOBSEGMENT', 'LOBINDEX')
ORDER BY segment_name;
~~~

Query thứ hai liệt kê segment LOB trong schema; kết hợp tên segment từ partition metadata để xác định partition nào đang chiếm dung lượng.

Không dùng query ghép USER_LOBS ở phần trước như phép đo đầy đủ cho bảng partitioned. Hãy cộng tất cả LOB partition và subpartition tương ứng.

## 9. Temporary LOB là gì?

Temporary LOB là LOB tạm được tạo để xử lý dữ liệu trong PL/SQL/SQL mà không phải là một LOB column bền vững của hàng trong bảng.

Temporary LOB có thể được tạo:

- Tường minh bằng DBMS_LOB.CREATETEMPORARY.
- Ngầm bởi một số phép toán, hàm hoặc biểu thức trên LOB.
- Khi xử lý CLOB/BLOB trung gian, nối chuỗi hoặc tạo kết quả LOB mới.
- Khi API trả về một LOB locator tạm.

Temporary LOB thường được lưu trong temporary tablespace; các thuộc tính cache và loại thao tác có thể ảnh hưởng việc dùng tài nguyên. Nó không được liệt kê như một LOB column trong USER_LOBS.

### 9.1. Temporary LOB khác persistent LOB

| Tiêu chí | Persistent LOB | Temporary LOB |
|---|---|---|
| Mục đích | Dữ liệu LOB thuộc bảng/row | Dữ liệu trung gian trong xử lý |
| Metadata | USER_LOBS/DBA_LOBS | Theo dõi qua V$TEMPORARY_LOBS |
| Storage | Tablespace của LOB segment | Temporary tablespace |
| Vòng đời | Theo dữ liệu bảng và transaction | Theo CALL hoặc SESSION duration |
| Giải phóng | DELETE/UPDATE row và quản lý segment | DBMS_LOB.FREETEMPORARY hoặc hết duration |
| Có phải row của bảng? | Có | Không nhất thiết |

Không dùng DELETE FROM bảng để giải phóng temporary LOB; temporary LOB không phải hàng persistent trong bảng.

## 10. Tạo temporary LOB bằng DBMS_LOB.CREATETEMPORARY

Ví dụ tạo CLOB tạm:

~~~sql
DECLARE
    l_temp_clob CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_temp_clob,
        cache   => TRUE,
        dur     => DBMS_LOB.SESSION
    );

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_temp_clob,
        amount  => LENGTH('Temporary text'),
        buffer  => 'Temporary text'
    );

    DBMS_OUTPUT.PUT_LINE(
        'Length = ' || DBMS_LOB.GETLENGTH(l_temp_clob)
    );

    DBMS_LOB.FREETEMPORARY(l_temp_clob);
END;
/
~~~

Các tham số:

- LOB_LOC: locator nhận temporary LOB.
- CACHE: yêu cầu cache dữ liệu LOB theo tùy chọn API.
- DUR: thời lượng CALL hoặc SESSION.

Ví dụ dùng DBMS_LOB.SESSION nghĩa là temporary LOB tồn tại theo session cho đến khi được giải phóng hoặc session kết thúc. Với CALL duration, temporary LOB được quản lý theo vòng đời call tương ứng.

### 10.1. CALL và SESSION duration

| Duration | Vòng đời |
|---|---|
| DBMS_LOB.CALL | Được giải phóng khi call kết thúc theo semantics của temporary LOB |
| DBMS_LOB.SESSION | Tồn tại trong session cho đến khi FREETEMPORARY hoặc session kết thúc |

SESSION duration hữu ích khi LOB tạm cần tồn tại qua nhiều subprogram call trong cùng session. Nhưng nó cũng tạo trách nhiệm cleanup rõ ràng. Trong connection pool, session có thể được tái sử dụng cho nhiều request; không giải phóng temporary LOB session-duration có thể làm số lượng temporary LOB tích lũy qua nhiều request.

### 10.2. CACHE và NOCACHE

CACHE là tùy chọn yêu cầu Oracle cache dữ liệu temporary LOB theo cách API/storage hỗ trợ. NOCACHE tránh yêu cầu cache theo lựa chọn đó. Cache không thay đổi logical length và không thay thế việc giải phóng locator.

Chọn cache dựa trên cách đọc/ghi và đo hiệu năng. Không bật CACHE cho mọi LOB lớn theo thói quen vì có thể ảnh hưởng buffer cache và workload khác.

## 11. ISTEMPORARY và FREETEMPORARY

Hai API quan trọng để quản lý vòng đời:

- DBMS_LOB.ISTEMPORARY(locator): trả 1 nếu locator trỏ đến temporary LOB; trả 0 nếu không.
- DBMS_LOB.FREETEMPORARY(locator): giải phóng temporary LOB.

Ví dụ kiểm tra trước khi free:

~~~sql
IF l_temp_clob IS NOT NULL
   AND DBMS_LOB.ISTEMPORARY(l_temp_clob) = 1
THEN
    DBMS_LOB.FREETEMPORARY(l_temp_clob);
END IF;
~~~

Không gọi FREETEMPORARY cho persistent LOB locator. Kiểm tra ISTEMPORARY trước giúp phân biệt temporary locator với LOB thuộc bảng.

### 11.1. CLOSE không giống FREETEMPORARY

DBMS_LOB.CLOSE đóng thao tác OPEN trên locator khi ứng dụng đã gọi DBMS_LOB.OPEN. Nó không thay thế FREETEMPORARY.

- OPEN/CLOSE quản lý trạng thái mở LOB cho một số thao tác.
- CREATETEMPORARY/FREETEMPORARY quản lý việc tạo và giải phóng temporary LOB.

Đóng LOB không có nghĩa temporary LOB đã được giải phóng.

### 11.2. TRIM không giải phóng locator

DBMS_LOB.TRIM có thể rút nội dung LOB về độ dài nhỏ hơn hoặc bằng độ dài chỉ định:

~~~sql
DBMS_LOB.TRIM(l_temp_clob, 0);
~~~

TRIM làm rỗng nội dung nhưng locator vẫn là temporary LOB. Nếu không dùng nữa, vẫn cần FREETEMPORARY. TRIM có thể hữu ích để tái sử dụng cùng một temporary LOB trong vòng lặp, nhưng không đồng nghĩa trả toàn bộ temporary LOB về pool ngay lập tức.

## 12. Giải phóng temporary LOB an toàn khi có exception

Một nguồn leak phổ biến là tạo temporary LOB rồi code phát sinh exception trước khi FREETEMPORARY.

Mẫu cleanup:

~~~sql
DECLARE
    l_temp_clob CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_temp_clob,
        TRUE,
        DBMS_LOB.SESSION
    );

    DBMS_LOB.WRITEAPPEND(
        l_temp_clob,
        LENGTH('Generated content'),
        'Generated content'
    );

    -- Xử lý l_temp_clob tại đây.

    IF DBMS_LOB.ISTEMPORARY(l_temp_clob) = 1 THEN
        DBMS_LOB.FREETEMPORARY(l_temp_clob);
    END IF;

EXCEPTION
    WHEN OTHERS THEN
        IF l_temp_clob IS NOT NULL
           AND DBMS_LOB.ISTEMPORARY(l_temp_clob) = 1
        THEN
            DBMS_LOB.FREETEMPORARY(l_temp_clob);
        END IF;

        RAISE;
END;
/
~~~

Trong code production, có thể đặt cleanup ở một nested block để đảm bảo mọi đường đi bình thường và lỗi đều gọi cleanup đúng một lần. Sau FREETEMPORARY, không tiếp tục đọc/ghi locator đó.

Không nuốt exception trong cleanup handler. Nếu lỗi gốc cần được chuyển lên caller, dùng RAISE sau khi giải phóng tài nguyên.

### 12.1. Khi trả temporary LOB cho caller

Nếu procedure tạo temporary LOB rồi trả locator qua OUT parameter, cần định nghĩa rõ quyền sở hữu:

- Procedure tạo và trả locator; caller chịu trách nhiệm FREETEMPORARY sau khi dùng.
- Hoặc procedure copy nội dung vào persistent LOB/đích khác rồi tự free temporary LOB trước khi kết thúc.

Không free locator trước khi caller sử dụng kết quả. Đồng thời không để cả caller và callee cùng nghĩ mình là owner duy nhất và free nhiều lần.

Ví dụ hợp đồng ownership:

~~~sql
CREATE OR REPLACE PROCEDURE build_temp_document (
    p_result OUT CLOB
) IS
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        p_result,
        TRUE,
        DBMS_LOB.SESSION
    );

    DBMS_LOB.WRITEAPPEND(
        p_result,
        LENGTH('Document body'),
        'Document body'
    );
END;
/
~~~

Caller nhận và giải phóng:

~~~sql
DECLARE
    l_result CLOB;
BEGIN
    build_temp_document(l_result);

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_result));

    IF DBMS_LOB.ISTEMPORARY(l_result) = 1 THEN
        DBMS_LOB.FREETEMPORARY(l_result);
    END IF;
END;
/
~~~

Đây là mẫu minh họa. API thật nên ghi rõ ai sở hữu locator, duration nào được chọn và caller cần cleanup trong exception path như thế nào.

## 13. Temporary LOB được tạo ngầm

Không phải temporary LOB nào cũng xuất phát từ lời gọi CREATETEMPORARY do lập trình viên viết. Một số phép toán trên LOB có thể tạo temporary LOB trung gian.

Ví dụ xử lý CLOB:

~~~sql
DECLARE
    l_source CLOB;
    l_result CLOB;
BEGIN
    SELECT description
    INTO l_source
    FROM documents
    WHERE document_id = 100;

    l_result := l_source || TO_CLOB(' - reviewed');

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_result));

    IF l_result IS NOT NULL
       AND DBMS_LOB.ISTEMPORARY(l_result) = 1
    THEN
        DBMS_LOB.FREETEMPORARY(l_result);
    END IF;
END;
/
~~~

Tùy biểu thức và kiểu dữ liệu, kết quả LOB trung gian có thể là temporary LOB. Dùng ISTEMPORARY để xác định trước khi free; không giả định mọi locator đều tạm.

Các biểu thức SQL/PLSQL trả CLOB, thao tác nối LOB hoặc hàm biến đổi LOB có thể tạo temporary result. Khi code chạy lặp, cần xem cả các temporary LOB ngầm chứ không chỉ các lời gọi CREATETEMPORARY.

## 14. Temporary LOB leak là gì?

Temporary LOB leak xảy ra khi ứng dụng tạo temporary LOB nhưng giữ locator hoặc không giải phóng LOB khi không còn cần thiết. Một số trường hợp:

- Gọi CREATETEMPORARY trong mỗi vòng lặp nhưng không gọi FREETEMPORARY.
- Procedure tạo LOB SESSION duration rồi trả kết quả, caller quên free.
- Exception thoát khỏi procedure trước cleanup.
- Package global giữ locator temporary LOB qua nhiều lần gọi.
- Ứng dụng dùng connection pool và session được tái sử dụng; temp LOB từ request trước còn tồn tại.
- Biểu thức tạo temporary LOB ngầm nhưng code không kiểm tra/free khi phù hợp.
- Copy locator giữa nhiều biến làm ownership mơ hồ.

### 14.1. Dấu hiệu thường gặp

- Số temporary LOB theo session tăng dần sau mỗi request.
- Temporary tablespace usage tăng theo thời gian dù SQL sort/hash workload không tăng tương ứng.
- Một session giữ nhiều CACHE_LOBS hoặc NOCACHE_LOBS.
- Batch đầu chạy bình thường, các batch sau dùng nhiều temporary space hơn.
- Khi kết thúc session, lượng temporary LOB liên quan biến mất.
- Session pool tái sử dụng connection khiến tài nguyên tồn tại qua nhiều request.

Một lần thấy TEMP tablespace tăng chưa đủ kết luận có leak. Sort, hash join, temporary table và các thao tác SQL khác cũng dùng TEMP. Cần đối chiếu số temporary LOB theo session và loại temp segment.

## 15. Theo dõi temporary LOB bằng V$TEMPORARY_LOBS

V$TEMPORARY_LOBS cung cấp số lượng temporary LOB theo session, phân loại theo loại cache/abstract LOB mà view hỗ trợ.

Ví dụ xem các session:

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.program,
       t.cache_lobs,
       t.nocache_lobs,
       t.abstract_lobs
FROM v$session s
JOIN v$temporary_lobs t
  ON t.sid = s.sid
WHERE s.username IS NOT NULL
ORDER BY
    t.cache_lobs + t.nocache_lobs + t.abstract_lobs DESC;
~~~

Các cột là số lượng LOB theo nhóm, không phải byte. Dùng query này để tìm session có số temporary LOB cao bất thường.

Quyền đọc V$SESSION và V$TEMPORARY_LOBS phụ thuộc tài khoản. DBA có thể cấp quyền xem dynamic performance views theo chính sách; không cấp quyền rộng chỉ để một ứng dụng thông thường giám sát mọi session.

### 15.1. Theo dõi session hiện tại

Nếu biết SID của session, có thể lọc:

~~~sql
SELECT sid,
       cache_lobs,
       nocache_lobs,
       abstract_lobs
FROM v$temporary_lobs
WHERE sid = SYS_CONTEXT('USERENV', 'SID');
~~~

Query giúp so sánh trước/sau một procedure trong cùng session. Lặp thử nhiều lần và quan sát số đếm sau mỗi call.

### 15.2. Oracle RAC

Trong RAC, một session thuộc một instance. Có thể dùng GV$TEMPORARY_LOBS và GV$SESSION, ghép thêm INST_ID:

~~~sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       t.cache_lobs,
       t.nocache_lobs,
       t.abstract_lobs
FROM gv$session s
JOIN gv$temporary_lobs t
  ON t.inst_id = s.inst_id
 AND t.sid = s.sid
WHERE s.username IS NOT NULL
ORDER BY s.inst_id, s.sid;
~~~

Nếu database không chạy RAC, dùng V$ view là đủ. GV$ view cần quyền phù hợp và trả dữ liệu toàn cluster.

## 16. Theo dõi temporary tablespace

V$TEMPSEG_USAGE cho biết temporary segment đang được sử dụng. View này có thể phản ánh sort/hash và các loại temporary segment khác, không chỉ temporary LOB.

~~~sql
SELECT username,
       tablespace,
       segtype,
       sql_id,
       SUM(blocks) AS blocks_used,
       SUM(extents) AS extents_used
FROM v$tempseg_usage
GROUP BY username, tablespace, segtype, sql_id
ORDER BY blocks_used DESC;
~~~

Dùng SEGTYPE để phân biệt nhóm segment. Các giá trị LOB_DATA/LOB_INDEX có thể xuất hiện cho temporary LOB; SORT/HASH phản ánh các hoạt động khác. Kiểm tra giá trị thực tế và tài liệu đúng release trước khi viết dashboard phụ thuộc vào danh sách SEGTYPE.

### 16.1. Tổng quan TEMP tablespace

~~~sql
SELECT tablespace_name,
       ROUND(SUM(bytes_used) / 1024 / 1024, 2) AS used_mb,
       ROUND(SUM(bytes_free) / 1024 / 1024, 2) AS free_mb
FROM v$temp_space_header
GROUP BY tablespace_name
ORDER BY tablespace_name;
~~~

V$TEMP_SPACE_HEADER cung cấp thông tin sử dụng/free theo tempfile và tablespace. Đây là số liệu tổng hợp, không cho biết toàn bộ dung lượng thuộc về temporary LOB.

Có thể xem DBA_TEMP_FREE_SPACE để kiểm tra tổng kích thước, allocated và free của temporary tablespace nếu tài khoản có quyền.

### 16.2. Không kết luận leak chỉ từ TEMP usage

TEMP tăng có thể do:

- Sort lớn.
- Hash join/hash aggregation.
- Global temporary table hoặc thao tác tạm khác.
- Temporary LOB.
- Các truy vấn song song hoặc batch đang chạy.

Kết hợp V$TEMPORARY_LOBS, V$TEMPSEG_USAGE, SQL_ID, session, chương trình và thời điểm workload để xác định nguồn.

## 17. Quy trình điều tra temporary LOB leak

Một quy trình thực tế:

1. Chọn một session test hoặc session ứng dụng có thể theo dõi.
2. Ghi baseline CACHE_LOBS, NOCACHE_LOBS và ABSTRACT_LOBS.
3. Gọi procedure một lần rồi kiểm tra lại.
4. Lặp lại cùng procedure nhiều lần trên cùng session.
5. Quan sát số đếm có tăng đều hay trở về baseline sau mỗi call.
6. Kiểm tra code có CREATETEMPORARY hoặc biểu thức tạo temporary LOB.
7. Kiểm tra tất cả đường thoát bình thường và exception.
8. Kiểm tra package global, biến lưu locator và OUT parameter ownership.
9. Gọi FREETEMPORARY đúng nơi sở hữu locator.
10. Chạy lại thử nghiệm và đối chiếu V$TEMPORARY_LOBS cùng TEMP usage.

### 17.1. Ví dụ baseline và repeated call

Có thể tạo một procedure lab tạo SESSION-duration temporary LOB:

~~~sql
CREATE OR REPLACE PROCEDURE lab_create_temp_lob IS
    l_temp CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_temp,
        TRUE,
        DBMS_LOB.SESSION
    );

    DBMS_LOB.WRITEAPPEND(
        l_temp,
        LENGTH('Temporary payload'),
        'Temporary payload'
    );

    -- Cố ý không free để quan sát trong schema lab.
END;
/
~~~

Gọi nhiều lần trong cùng session:

~~~sql
BEGIN
    lab_create_temp_lob;
    lab_create_temp_lob;
    lab_create_temp_lob;
END;
/
~~~

Kiểm tra V$TEMPORARY_LOBS trước và sau. Sau đó sửa procedure để FREETEMPORARY và lặp lại phép thử.

Đây là bài lab cố ý tạo tình huống rò rỉ. Không chạy procedure này lặp trên production hoặc session dùng chung; kết thúc session lab sẽ giải phóng temporary LOB session-duration còn lại.

### 17.2. So sánh CALL duration và SESSION duration

Lặp cùng một bài test với CALL duration và SESSION duration:

- CALL duration được giải phóng khi call kết thúc theo semantics tương ứng.
- SESSION duration tiếp tục tồn tại cho đến khi free hoặc session kết thúc.

Nếu code dùng session pool, session-duration temporary LOB đặc biệt cần cleanup tường minh vì database session không nhất thiết đóng sau mỗi request ứng dụng.

## 18. Thiết kế cleanup trong vòng lặp

Sai lầm phổ biến:

~~~sql
FOR i IN 1 .. 10000 LOOP
    DBMS_LOB.CREATETEMPORARY(
        l_temp,
        TRUE,
        DBMS_LOB.SESSION
    );

    -- Tạo nội dung và xử lý.
    -- Không gọi FREETEMPORARY.
END LOOP;
~~~

Mỗi iteration tạo thêm một temporary LOB session-duration. Nếu locator cũ bị ghi đè, ứng dụng có thể mất đường tham chiếu để giải phóng từng LOB.

### 18.1. Tạo, dùng và free trong mỗi iteration

~~~sql
FOR i IN 1 .. 10000 LOOP
    DBMS_LOB.CREATETEMPORARY(
        l_temp,
        TRUE,
        DBMS_LOB.CALL
    );

    BEGIN
        DBMS_LOB.WRITEAPPEND(
            l_temp,
            LENGTH('Batch item'),
            'Batch item'
        );

        -- Xử lý l_temp.
    EXCEPTION
        WHEN OTHERS THEN
            IF DBMS_LOB.ISTEMPORARY(l_temp) = 1 THEN
                DBMS_LOB.FREETEMPORARY(l_temp);
            END IF;
            RAISE;
    END;

    IF DBMS_LOB.ISTEMPORARY(l_temp) = 1 THEN
        DBMS_LOB.FREETEMPORARY(l_temp);
    END IF;
END LOOP;
~~~

Ví dụ cho thấy cleanup cả normal path và exception path. Nếu dùng CALL duration và call kết thúc ngay sau vòng lặp, Oracle cũng quản lý vòng đời call, nhưng free tường minh giúp tài nguyên được giải phóng sớm hơn khi không còn cần.

### 18.2. Tái sử dụng một temporary LOB

Nếu workload tạo nhiều kết quả tuần tự, có thể tạo một temporary LOB ngoài vòng lặp rồi TRIM về 0 để tái sử dụng:

~~~sql
DECLARE
    l_temp CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_temp,
        TRUE,
        DBMS_LOB.SESSION
    );

    FOR i IN 1 .. 1000 LOOP
        DBMS_LOB.TRIM(l_temp, 0);

        DBMS_LOB.WRITEAPPEND(
            l_temp,
            LENGTH('One item'),
            'One item'
        );

        -- Xử lý nội dung hiện tại trước khi lặp tiếp.
    END LOOP;

    DBMS_LOB.FREETEMPORARY(l_temp);
EXCEPTION
    WHEN OTHERS THEN
        IF l_temp IS NOT NULL
           AND DBMS_LOB.ISTEMPORARY(l_temp) = 1
        THEN
            DBMS_LOB.FREETEMPORARY(l_temp);
        END IF;
        RAISE;
END;
/
~~~

TRIM giữ nguyên locator nhưng rút nội dung. Đây là cách có thể giảm số lần tạo temporary LOB, song cần đo vì allocation có thể vẫn được giữ để tái sử dụng.

## 19. Package state và connection pool

Package có thể giữ biến global trong session:

~~~sql
CREATE OR REPLACE PACKAGE temp_lob_state AS
    g_document CLOB;
END temp_lob_state;
/
~~~

Nếu package gán temporary LOB session-duration vào G_DOCUMENT và không giải phóng, locator có thể tồn tại trong package state suốt session.

Trong ứng dụng connection pool:

- Request A mượn database session 42, tạo temporary LOB.
- Request A trả connection về pool nhưng session database vẫn sống.
- Request B mượn lại session 42.
- Temporary LOB cũ có thể vẫn tồn tại nếu chưa free.
- Nhiều request lặp lại có thể làm tài nguyên tích lũy.

Khi trả connection về pool, không mặc định Oracle session bị đóng. Ứng dụng hoặc package cleanup hook cần giải phóng locator đã tạo và reset package state theo chính sách.

Không giữ temporary LOB locator trong package global nếu không có ownership và cleanup lifecycle rõ ràng.

## 20. Temporary LOB và persistent LOB: tránh cleanup nhầm

Không gọi FREETEMPORARY cho locator persistent lấy từ cột bảng:

~~~sql
SELECT content_clob
INTO l_content
FROM documents
WHERE document_id = 100;
~~~

Locator này tham chiếu LOB persistent của row. Không dùng FREETEMPORARY để giải phóng nó.

Có thể kiểm tra:

~~~sql
IF DBMS_LOB.ISTEMPORARY(l_content) = 1 THEN
    DBMS_LOB.FREETEMPORARY(l_content);
END IF;
~~~

Chỉ free khi ISTEMPORARY trả 1. Việc gán locator persistent sang biến PL/SQL không biến persistent LOB thành temporary LOB.

Ngược lại, một biểu thức tạo CLOB tạm có thể được gán vào biến rồi cần cleanup. Vì vậy không dựa vào tên biến hay kiểu CLOB để kết luận locator là persistent hay temporary.

## 21. Khi LOB segment tăng nhưng không phải temporary LOB leak

Một số nguyên nhân làm persistent LOB segment tăng:

- Ứng dụng cập nhật LOB nhiều lần, tạo old versions cần cho read consistency.
- PCTVERSION/RETENTION giữ lại phiên bản LOB cũ theo storage policy.
- DELETE/UPDATE nội dung làm free space nội bộ nhưng extent vẫn được cấp.
- SecureFiles compression/deduplication thay đổi tỷ lệ giữa logical và physical size.
- LOB lưu OUT OF ROW tăng do payload lớn.
- Segment partition tăng theo phân bố dữ liệu.
- DML/retention/backup/recovery workload tạo nhu cầu storage tạm thời.

Vì vậy, cần phân biệt:

- USER_SEGMENTS tăng ở LOBSEGMENT: persistent LOB segment được cấp thêm extent.
- V$TEMPORARY_LOBS tăng theo session: số temporary LOB đang tồn tại tăng.
- V$TEMPSEG_USAGE tăng: temporary segment đang được sử dụng, có thể do LOB, sort hoặc hash.

Ba dấu hiệu này giúp khoanh vùng đúng loại vấn đề.

## 22. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Coi GETLENGTH(CLOB) là byte vật lý | Ước lượng storage sai | Ghi rõ đơn vị ký tự/byte |
| Coi USER_SEGMENTS.BYTES là payload logic | Nhầm extent allocation với nội dung | Đối chiếu GETLENGTH và segment allocation |
| Chỉ xem USER_LOBS cho bảng partitioned | Bỏ sót LOB partition/subpartition | Dùng USER_LOB_PARTITIONS/SUBPARTITIONS |
| Quên LOB index | Thiếu một phần storage metadata | Đối chiếu INDEX_NAME và LOBINDEX |
| Bỏ qua IN ROW | Đánh giá thiếu dữ liệu nằm trong table segment | Cộng cả table segment khi đo bảng |
| Coi TEMP tăng là chắc chắn leak LOB | Chẩn đoán sai sort/hash usage | Kết hợp V$TEMPORARY_LOBS và V$TEMPSEG_USAGE |
| Tạo SESSION-duration LOB trong loop mà không free | Temporary LOB tích lũy trong session | FREETEMPORARY hoặc tái sử dụng có kiểm soát |
| Chỉ cleanup normal path | Exception làm locator còn tồn tại | Cleanup trong exception handler |
| Nghĩ CLOSE giải phóng temporary LOB | Locator vẫn tồn tại | Gọi FREETEMPORARY |
| Nghĩ TRIM giải phóng locator | Chỉ nội dung bị rút ngắn | FREETEMPORARY khi không dùng nữa |
| Free persistent LOB locator | Dùng sai API/vòng đời | Kiểm tra ISTEMPORARY |
| Caller và callee cùng free locator | Ownership không rõ, có thể lỗi | Quy định một bên chịu trách nhiệm |
| Package global giữ locator | Tài nguyên tồn tại qua nhiều request | Reset state và free trước khi trả session |
| Nghĩ connection pool đóng session sau request | Temporary LOB session-duration còn lại | Cleanup theo request/session lifecycle |
| Kết luận segment không giảm là leak | Extent có thể giữ để tái sử dụng | Kiểm tra free space nội bộ và storage policy |

## 23. Checklist đo dung lượng và điều tra temporary LOB

### Đo persistent LOB

- [ ] Xác định bảng, cột và datatype BLOB/CLOB/NCLOB.
- [ ] Đo logical length bằng DBMS_LOB.GETLENGTH.
- [ ] Ghi rõ BLOB là byte, CLOB/NCLOB là ký tự.
- [ ] Đếm riêng NULL, empty LOB và LOB có nội dung.
- [ ] Xem USER_LOBS/ALL_LOBS/DBA_LOBS.
- [ ] Xem USER_SEGMENTS/DBA_SEGMENTS cho LOBSEGMENT và LOBINDEX.
- [ ] Kiểm tra IN_ROW, SecureFiles/BasicFiles, compression/deduplication.
- [ ] Nếu partitioned, kiểm tra LOB partition/subpartition.
- [ ] Đối chiếu table segment vì LOB inline có thể nằm trong row.
- [ ] Không nhầm allocated bytes với logical payload.

### Điều tra temporary LOB

- [ ] Kiểm tra code có CREATETEMPORARY hoặc biểu thức tạo LOB trung gian.
- [ ] Xác định CALL hay SESSION duration.
- [ ] Quy định owner của locator khi trả qua OUT parameter.
- [ ] Dùng ISTEMPORARY trước khi FREETEMPORARY.
- [ ] Cleanup cả normal path và exception path.
- [ ] Kiểm tra package global và biến lưu locator.
- [ ] Theo dõi V$TEMPORARY_LOBS theo SID/session.
- [ ] Đối chiếu V$TEMPSEG_USAGE và V$TEMP_SPACE_HEADER.
- [ ] Phân biệt LOB temp segment với SORT/HASH.
- [ ] Lặp procedure trên cùng session để kiểm tra số lượng có tích lũy.
- [ ] Kiểm thử trong connection pool có tái sử dụng session.
- [ ] Không dùng FREETEMPORARY cho persistent LOB locator.

## 24. Ghi nhớ cốt lõi

- DBMS_LOB.GETLENGTH đo logical length: BLOB theo byte, CLOB/NCLOB theo ký tự.
- Logical length không phải allocated segment bytes; character set, IN ROW, chunk, free space và SecureFiles options ảnh hưởng storage.
- USER_LOBS mô tả LOB column; USER_SEGMENTS cho biết extent đã cấp của LOBSEGMENT và LOBINDEX.
- Với partitioned LOB, phải kiểm tra USER_LOB_PARTITIONS và USER_LOB_SUBPARTITIONS cùng segment tương ứng.
- IN ROW có thể đặt một phần nội dung LOB trong table segment, vì vậy không chỉ đo LOBSEGMENT.
- BasicFiles PCTVERSION và SecureFiles RETENTION liên quan old LOB versions; segment tăng không tự động có nghĩa temporary LOB leak.
- Temporary LOB là dữ liệu trung gian, thường dùng temporary tablespace và không xuất hiện như LOB column trong USER_LOBS.
- CREATETEMPORARY tạo temporary LOB; ISTEMPORARY nhận diện locator; FREETEMPORARY giải phóng locator.
- CALL và SESSION duration có vòng đời khác nhau; SESSION duration cần cleanup tường minh, nhất là với connection pool.
- CLOSE và TRIM không thay thế FREETEMPORARY.
- Temporary LOB có thể được tạo ngầm bởi phép toán/hàm trên LOB, không chỉ từ CREATETEMPORARY.
- V$TEMPORARY_LOBS đếm temporary LOB theo session, không trực tiếp cho biết số byte.
- V$TEMPSEG_USAGE và V$TEMP_SPACE_HEADER giúp đối chiếu temporary segment và tổng TEMP, nhưng TEMP còn được dùng cho sort/hash.
- Cleanup phải chạy trên cả đường thành công và exception; ownership của OUT locator phải rõ ràng.
- Khi điều tra, phân biệt persistent LOB segment growth, temporary LOB count và temporary tablespace usage trước khi kết luận.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database SecureFiles and Large Objects Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/adlob/) — LOB architecture, BasicFiles/SecureFiles, temporary LOB và DBMS_LOB.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_LOB](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_LOB.html) — GETLENGTH, CREATETEMPORARY, ISTEMPORARY, FREETEMPORARY, TRIM và duration.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — USER_LOBS, USER_SEGMENTS, V$TEMPORARY_LOBS, V$TEMPSEG_USAGE và V$TEMP_SPACE_HEADER.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Tablespace, tempfile, segment allocation và space management.
- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/) — LOB locator, PL/SQL variables, exception handling và package state.

Tên cột dictionary, tùy chọn SecureFiles và cách theo dõi temporary segment có thể khác theo Oracle release. Đối chiếu tài liệu đúng phiên bản, kiểm tra quyền truy cập dynamic performance views và đo trên session lab trước khi thay đổi storage hoặc cleanup logic production.

