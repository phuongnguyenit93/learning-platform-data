# Hot block, ITL và tranh chấp khi cập nhật tập trung trong Oracle

Trong hệ thống Oracle có nhiều session cùng ghi dữ liệu, hiệu năng đôi khi giảm mạnh dù các session đang cập nhật những hàng khác nhau. Nguyên nhân có thể là các hàng đó nằm trong cùng một **data block**, hoặc nhiều thao tác INSERT cùng dồn vào một **index leaf block**. Một dạng tranh chấp khác xuất hiện khi block không còn đủ **ITL entry** để ghi nhận các transaction đang cùng thay đổi block. Những hiện tượng này thường được gọi chung là *hot block contention*, nhưng cách xử lý phụ thuộc chính xác tài nguyên đang bị tranh chấp.

Ví dụ, một bảng ghi nhận số lượt truy cập có hàng triệu session cập nhật cùng một bộ đếm; một index dùng khóa tăng tuần tự có nhiều session chèn vào cùng leaf block ở mép phải; hoặc một bảng có nhiều hàng nhỏ nằm chung block và nhiều transaction cập nhật các hàng đó đồng thời. Cả ba tình huống đều có thể tạo wait, nhưng bản chất khác nhau:

- **Hot row:** nhiều transaction muốn sửa cùng một hàng, thường chờ row lock.
- **Hot block:** nhiều session cùng cần truy cập hoặc thay đổi một block, dù có thể đang làm việc trên các hàng khác nhau.
- **ITL contention:** block không có đủ transaction slot để ghi nhận thêm transaction đồng thời đang sửa các hàng trong block.

Bài học thuộc chủ đề **Khóa và đồng thời** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Cấu trúc data block và vai trò của Interested Transaction List (ITL).
- Phân biệt row lock, hot block, ITL wait và index right-edge contention.
- Các wait event thường gặp và cách tìm segment/block gây tranh chấp.
- Vai trò của INITRANS, PCTFREE, ASSM và thiết kế index/partition.
- Kỹ thuật phân tán tải ghi, giảm cập nhật tập trung và kiểm chứng bằng số liệu.

## 1. Data block là đơn vị lưu trữ và điểm hội tụ của nhiều thao tác

Oracle lưu dữ liệu trong các data block. Một table block có thể chứa nhiều row; một index block có thể chứa nhiều entry. Khi session đọc hoặc thay đổi một row, Oracle làm việc với block chứa row đó trong buffer cache. Do đó, hai transaction cập nhật hai row khác nhau vẫn có thể cùng cần một block.

Ví dụ một block có các hàng:

~~~text
Data block #42
+----------------------------------+
| Block header                     |
| ITL slot 1 | ITL slot 2 | ...    |
|                                  |
| Row A: account_id = 101          |
| Row B: account_id = 102          |
| Row C: account_id = 103          |
| Row D: account_id = 104          |
+----------------------------------+
~~~

Session 1 cập nhật Row A và Session 2 cập nhật Row B. Hai session không tranh cùng một row lock, nhưng vẫn phải thay đổi metadata trong cùng block, bao gồm ITL entry và row lock information. Nếu block không có đủ ITL entry khả dụng hoặc không thể mở rộng ITL do thiếu chỗ trống, một transaction có thể phải chờ.

### Hot block không đồng nghĩa hot row

| Tình huống | Đối tượng tranh chấp | Dấu hiệu điển hình |
| --- | --- | --- |
| Nhiều session cập nhật cùng một row | Row lock của cùng row | enq: TX - row lock contention |
| Nhiều transaction sửa các row khác nhau nhưng cùng block, thiếu ITL | ITL slot trong block | enq: TX - allocate ITL entry |
| Nhiều session cần cùng buffer/block trong cache | Buffer/block access hoặc cache structure | Có thể thấy buffer busy waits, cache buffers chains latch/mutex waits tùy phiên bản |
| Nhiều INSERT vào cuối index tăng tuần tự | Index leaf block ở mép phải | Có thể thấy buffer/cache contention; trong RAC có thể có global cache waits |

Tên wait event là manh mối, không phải kết luận độc lập. Cần đối chiếu object, block, SQL_ID, loại thao tác và mức độ đồng thời trước khi chọn cách khắc phục.

## 2. ITL là gì?

**ITL (Interested Transaction List)** là danh sách các entry trong block dùng để ghi nhận những transaction đang quan tâm/thay đổi block đó. Mỗi entry lưu thông tin cần thiết để Oracle theo dõi transaction và các row lock liên quan trong block. Khi một transaction cập nhật row trong block, Oracle cần một ITL entry để ghi nhận transaction đó.

Một cách hình dung:

~~~text
Data block
+--------------------------------------------------+
| Block header                                     |
| ITL 1: transaction X, lock metadata              |
| ITL 2: transaction Y, lock metadata              |
| ITL 3: transaction Z, lock metadata              |
|                                                  |
| Row directory / row data                         |
+--------------------------------------------------+
~~~

ITL là metadata cấp block, trong khi khóa logic của DML vẫn là khóa hàng. Nhiều transaction có thể cập nhật các hàng khác nhau trong cùng block nếu mỗi transaction có ITL entry phù hợp. Nếu không còn entry trống và block không thể cấp thêm entry, transaction mới có thể phải chờ một transaction khác kết thúc để tái sử dụng entry.

### ITL entry không phải một row lock dùng chung cho cả block

Một nhầm lẫn thường gặp là nghĩ block chỉ cho phép một transaction cập nhật tại một thời điểm. Điều đó không đúng. Một block có thể có nhiều ITL entry, cho phép nhiều transaction cùng sửa các row khác nhau trong block. Tranh chấp ITL xuất hiện khi số entry sẵn có không đủ cho mức đồng thời thực tế.

### Điều gì xảy ra khi ITL slot không đủ?

Giả sử block hiện có hai ITL entry:

1. Transaction A chiếm ITL 1 để cập nhật row A.
2. Transaction B chiếm ITL 2 để cập nhật row B.
3. Transaction C muốn cập nhật row C trong cùng block.
4. Không còn ITL entry trống; block cũng không còn free space phù hợp để mở rộng ITL.
5. Transaction C phải chờ một ITL entry được giải phóng hoặc có thể được cấp thêm.

Trong tình huống này, Oracle có thể ghi nhận wait event enq: TX - allocate ITL entry. Đây là dấu hiệu đặc trưng của thiếu ITL entry, khác với chờ một transaction đang khóa đúng row cần cập nhật.

## 3. INITRANS và PCTFREE ảnh hưởng đến ITL ra sao?

Hai tham số lưu trữ thường được xem xét khi có ITL contention là INITRANS và PCTFREE.

### INITRANS: số ITL entry ban đầu

INITRANS chỉ định số transaction entry ban đầu được cấp trong mỗi block mới của segment. Oracle có thể cấp thêm ITL entry động nếu block còn đủ free space.

- Table thường có giá trị mặc định thấp (thông thường 1).
- Index thường có giá trị mặc định khác (thông thường 2).
- Có thể tăng INITRANS khi dự đoán nhiều transaction sẽ đồng thời sửa các row trong cùng block.
- INITRANS cao hơn dành trước nhiều chỗ cho ITL, làm giảm phần không gian ban đầu dành cho row/index entry.

Ví dụ:

~~~sql
CREATE TABLE hot_rows_demo (
    id         NUMBER PRIMARY KEY,
    group_id   NUMBER NOT NULL,
    value_num  NUMBER
)
INITRANS 8
PCTFREE 20;
~~~

Với index:

~~~sql
CREATE INDEX ix_hot_rows_group
ON hot_rows_demo(group_id)
INITRANS 8
PCTFREE 20;
~~~

Các giá trị 8 và 20 chỉ là ví dụ minh họa, không phải cấu hình tối ưu cho mọi bảng. Chọn dựa trên mức đồng thời, kích thước block, kích thước row, loại segment và số liệu wait thực tế.

### PCTFREE: giữ chỗ trong block

PCTFREE chỉ định tỷ lệ phần trăm block được giữ lại làm vùng trống để hỗ trợ các thao tác cập nhật và các nhu cầu mở rộng metadata như ITL. Nếu block không còn free space, Oracle có thể không mở rộng được ITL dù các transaction slot ban đầu đã bị dùng hết.

Tăng PCTFREE có thể giúp block còn chỗ cho ITL entry bổ sung và cho row tăng kích thước sau UPDATE. Đổi lại:

- Mỗi block chứa ít row/index entry hơn.
- Segment có thể cần nhiều block hơn.
- Full scan có thể phải đọc nhiều block hơn.
- Buffer cache và I/O footprint có thể tăng.

PCTFREE không phải công tắc giải quyết mọi hot block. Nếu nguyên nhân là nhiều session cập nhật cùng một row hoặc cùng một index leaf block, chỉ tăng PCTFREE có thể không giúp.

### INITRANS và PCTFREE phối hợp

| Tham số | Vai trò | Đánh đổi |
| --- | --- | --- |
| INITRANS | Dành sẵn số ITL entry ban đầu trong block | Tốn thêm không gian block ngay từ đầu |
| PCTFREE | Giữ vùng trống để row và ITL có thể mở rộng | Giảm mật độ row/entry trên block |

Nếu có nhiều transaction đồng thời sửa các row khác nhau trong cùng block, có thể cần tăng INITRANS và bảo đảm PCTFREE đủ để block mở rộng khi cần. Hai tham số cần được xem xét cùng phân bố row và kích thước block.

### Thay INITRANS có tác động ngay lên block hiện có không?

Không nên giả định ALTER TABLE ... INITRANS hoặc ALTER INDEX ... INITRANS lập tức viết lại toàn bộ block đang tồn tại. Tham số lưu trữ mới chủ yếu định hướng việc tạo/format block mới; các block cũ có thể vẫn giữ cấu trúc ITL đã được cấp trước đó. Khi cần áp dụng rộng cho block hiện hữu, phải đánh giá việc di chuyển/rebuild segment phù hợp, sau đó đo lại. Với index, rebuild tạo lại leaf block theo cấu hình mới; với table có thể cần MOVE hoặc tái tổ chức bằng phương pháp phù hợp phiên bản và partition.

## 4. Phân biệt ITL contention với row lock contention

Hai wait event có chữ TX nhưng bản chất khác nhau:

### enq: TX - row lock contention

Một transaction đang chờ transaction khác kết thúc vì hàng mà nó muốn thay đổi đang bị khóa. Ví dụ hai session cùng cập nhật ACCOUNT_ID = 10. Cách giải quyết thường là rút ngắn transaction giữ khóa, giảm cập nhật đồng thời cùng row hoặc thiết kế lại điểm ghi tập trung.

### enq: TX - allocate ITL entry

Transaction cần một ITL entry trong block nhưng không có slot khả dụng và block không thể cấp thêm entry tại thời điểm đó. Các transaction có thể đang sửa những row khác nhau. Hướng xử lý tập trung vào ITL, free space và việc phân tán các row nóng sang nhiều block.

| Đặc điểm | Row lock contention | ITL contention |
| --- | --- | --- |
| Tài nguyên | Một row cụ thể | ITL slot trong block |
| Các transaction có thể sửa row khác nhau? | Thường là không, vì cùng row bị khóa | Có |
| Wait event tiêu biểu | enq: TX - row lock contention | enq: TX - allocate ITL entry |
| Hướng khắc phục | Giảm tranh chấp cùng row, rút ngắn transaction | INITRANS, PCTFREE, tái tổ chức block, phân tán tải |

Không tăng INITRANS để chữa một hot row. INITRANS không cho phép hai transaction cùng sửa một row đã bị khóa; nó chỉ giúp block ghi nhận nhiều transaction khác nhau.

## 5. Hot block ở table và hot block ở index

Hot block có thể nằm ở nhiều loại segment. Phân biệt vị trí giúp chọn đúng giải pháp.

### Hot table block

Hot table block xảy ra khi nhiều thao tác DML cùng truy cập một data block của bảng. Các nguyên nhân thường gặp:

- Một nhóm row rất nhỏ được cập nhật liên tục.
- Nhiều row có cùng block do row nhỏ và block chứa nhiều hàng.
- INSERT dồn vào một vùng block do cách tổ chức dữ liệu hoặc phân bổ free space.
- Nhiều session cập nhật các cột trong các row khác nhau nhưng vẫn phải sửa metadata của cùng block.

Nếu wait là ITL allocation, xem INITRANS/PCTFREE và khả năng phân tán row. Nếu wait là buffer busy hoặc cache buffers chains, cần xác định thao tác nào cùng cần buffer và vì sao block đó nóng; tăng INITRANS không phải cách chữa mặc định.

### Hot index leaf block

Một index B-tree có thể bị nóng ở leaf block cuối khi khóa index tăng gần như đơn điệu, ví dụ sequence tăng dần hoặc timestamp mới nhất:

~~~text
Index leaf blocks (key tăng dần)

[100-199] -> [200-299] -> [300-399] -> [400-499]
                                         ^^^^^^^
                                      nhiều INSERT
                                      cùng vào đây
~~~

Các INSERT mới có khóa lớn hơn thường đi vào leaf block ngoài cùng bên phải. Khi nhiều session cùng chèn, chúng có thể tranh chấp block đó dù mỗi row trong table là row mới và không trùng nhau.

### Vì sao sequence tăng dần có thể tạo điểm nóng?

Sequence cấp khóa duy nhất, nhưng các giá trị tăng liên tục thường làm index entry mới tập trung về một vùng leaf block. CACHE sequence giảm công việc cấp số và giảm truy cập dictionary/sequence state, nhưng **không tự phân tán index leaf block**. Nếu wait đến từ right-edge leaf block, phải xem lại cấu trúc index hoặc phân bố khóa.

### Reverse key index

Reverse key index đảo thứ tự byte của giá trị khóa trước khi lưu trong index. Những khóa tăng dần vì thế được phân tán trên nhiều vùng leaf thay vì dồn hết ở mép phải.

~~~sql
CREATE INDEX ix_orders_id_reverse
ON orders(order_id)
REVERSE;
~~~

Ưu điểm:

- Có thể giảm tranh chấp ở right-edge leaf block khi workload INSERT khóa tăng dần.
- Vẫn hỗ trợ truy vấn equality theo khóa đã đảo.

Giới hạn:

- Không phù hợp với range scan theo thứ tự khóa gốc như BETWEEN hoặc ORDER BY order_id.
- Không giải quyết hot table row/block nếu điểm nóng nằm ở table segment.
- Cần cân nhắc các truy vấn, FK và yêu cầu truy cập của ứng dụng trước khi thay index.

Không tạo reverse key index chỉ vì thấy nhiều INSERT. Trước hết xác nhận wait thực sự tập trung ở leaf block của index tăng tuần tự.

### Hash-partitioned index và partitioning

Hash partitioning có thể phân phối các giá trị khóa trên nhiều partition, giúp tăng số vùng ghi khi khóa phân bố tốt. Ví dụ, global hash-partitioned index có thể chia index thành nhiều partition theo hash của key; mỗi partition có cây B-tree riêng.

Lợi ích phụ thuộc phân bố key và cách truy vấn. Nếu mọi DML vẫn dồn vào cùng một key hoặc cùng một partition, partitioning không loại bỏ điểm nóng. Với bảng partitioned, local index cũng có thể giúp tách workload theo partition key; thiết kế partition key phải phù hợp cả truy vấn lẫn phân bố ghi.

## 6. Các wait event và cách đọc dấu hiệu

Wait event giúp khoanh vùng loại tranh chấp, nhưng cần xem thêm segment và block:

| Wait/event | Gợi ý nguyên nhân | Điều cần xác minh |
| --- | --- | --- |
| enq: TX - row lock contention | Chờ transaction khác nhả row lock | Hai session có sửa cùng row/key không? |
| enq: TX - allocate ITL entry | Không có ITL entry khả dụng trong block | Segment nào có ITL waits cao? Block có free space không? |
| buffer busy waits | Chờ buffer/block đang được session khác sử dụng theo một chế độ xung đột | File/block/class nào lặp lại? Object là table hay index? |
| latch: cache buffers chains | Tranh chấp trên hash chain quản lý buffer trong cache | Có nhiều session cùng truy cập một nhóm buffer/block không? |
| gc buffer busy acquire/release (RAC) | Tranh chấp buffer/block qua Global Cache Service | Các instance có cùng ghi một block nóng không? |
| gc current block busy (RAC) | Chờ current block được xử lý/truyền giữa instance | Có block bị ping qua lại giữa các instance không? |

Tên và chi tiết wait event có thể thay đổi theo phiên bản Oracle, cấu hình single-instance/RAC và đường thực thi. Không kết luận “hot block” chỉ từ một dòng wait; cần xem tần suất, thời lượng, object và block cụ thể.

### Kiểm tra session đang chờ

Quyền truy cập V$ views phụ thuộc quyền được cấp cho tài khoản:

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       seconds_in_wait,
       p1text, p1,
       p2text, p2,
       p3text, p3
FROM v$session
WHERE status = 'ACTIVE'
  AND state = 'WAITING'
  AND wait_class <> 'Idle'
ORDER BY seconds_in_wait DESC;
~~~

Kết quả cho biết session đang chờ gì và các tham số P1/P2/P3 của event. Ý nghĩa các tham số phụ thuộc từng wait event; không diễn giải P1/P2 thành file/block cho mọi event.

### Xem segment có ITL wait và buffer busy wait cao

~~~sql
SELECT owner,
       object_name,
       subobject_name,
       statistic_name,
       value
FROM v$segment_statistics
WHERE statistic_name IN (
    'ITL waits',
    'buffer busy waits',
    'row lock waits'
)
ORDER BY value DESC;
~~~

Các bộ đếm trong view là số liệu thống kê tích lũy. So sánh hai lần chụp cách nhau một khoảng thời gian trong giờ tải cao để xem segment nào tăng nhanh; không chỉ nhìn tổng số tuyệt đối từ lúc instance khởi động. Tên statistic có thể phụ thuộc phiên bản/loại segment, nên xem các tên thực tế mà database cung cấp.

### Dùng ASH khi được cấp phép

Active Session History có thể giúp tìm SQL và block thường xuyên xuất hiện trong mẫu session đang hoạt động:

~~~sql
SELECT sample_time,
       session_id,
       session_serial#,
       sql_id,
       event,
       current_obj#,
       current_file#,
       current_block#
FROM v$active_session_history
WHERE sample_time > SYSTIMESTAMP - INTERVAL '15' MINUTE
  AND event IS NOT NULL
ORDER BY sample_time DESC;
~~~

V$ACTIVE_SESSION_HISTORY và AWR/ASH historical views thuộc nhóm tính năng Diagnostics Pack trong các phiên bản Oracle áp dụng chính sách license tương ứng. Chỉ sử dụng khi tổ chức có quyền sử dụng. Nếu không có license, có thể bắt đầu bằng V$SESSION, V$SEGMENT_STATISTICS, trace phù hợp và công cụ giám sát đã được cấp phép.

### Từ file/block tìm segment sở hữu

Khi đã xác định được file number và block number (ví dụ từ ASH hoặc tham số của một wait event có định nghĩa rõ), có thể tìm extent chứa block:

~~~sql
SELECT owner,
       segment_name,
       partition_name,
       segment_type,
       block_id,
       blocks
FROM dba_extents
WHERE file_id = :file_no
  AND :block_no BETWEEN block_id AND block_id + blocks - 1;
~~~

Hai bind file_no và block_no phải lấy từ nguồn có ý nghĩa đúng cho wait đang phân tích. Một segment partitioned có thể hiện partition_name; index và table có thể cùng liên quan tới một thao tác DML nhưng là các segment khác nhau.

## 7. Quy trình chẩn đoán có thứ tự

Khi hệ thống chậm do cập nhật tập trung, nên đi từ triệu chứng tới block/object thay vì thay storage parameter ngay:

1. **Xác định thời điểm và workload:** thời điểm nào wait tăng, thao tác là INSERT hay UPDATE, có bao nhiêu session đồng thời?
2. **Nhóm theo wait event:** row lock, ITL allocation, buffer busy, cache buffers chains hay global cache?
3. **Xác định SQL:** lấy SQL_ID, module/action, bind pattern và loại DML gây wait.
4. **Xác định segment:** table, index, partition hay segment khác; xem V$SEGMENT_STATISTICS.
5. **Xác định block nóng:** đối chiếu file/block từ nguồn đáng tin cậy, map sang extent và object.
6. **Xác định hình thái khóa:** cùng một row, nhiều row trong một block, hay index leaf block ở mép phải?
7. **Chọn một thay đổi phù hợp:** giảm hot row, tăng ITL/free space, phân tán key hoặc thay cấu trúc index/partition.
8. **Đo lại trong cùng workload:** so wait time, throughput, latency, số block, redo và tác động tới truy vấn đọc.

Một thay đổi chỉ được coi là hữu ích khi wait giảm mà throughput và độ trễ nghiệp vụ cải thiện, không phải chỉ vì một counter riêng lẻ giảm.

## 8. Cách khắc phục theo đúng loại tranh chấp

Không có một tham số duy nhất giải quyết mọi hot block. Hãy chọn hướng xử lý dựa trên wait và segment đã xác định.

### Trường hợp A: ITL allocation wait

Nếu segment có ITL waits tăng rõ rệt và workload thực sự cập nhật nhiều row khác nhau trong cùng block:

1. Kiểm tra INITRANS của table/index bị ảnh hưởng.
2. Kiểm tra PCTFREE và free space còn lại trong block.
3. Xem có thể tăng INITRANS cho block được tạo mới hay không.
4. Nếu block hiện hữu vẫn thiếu slot, đánh giá MOVE/rebuild/reorganization để viết lại block theo storage parameter mới.
5. Đo lại ITL waits và throughput sau khi chạy đúng workload đồng thời.

Ví dụ cấu hình cho segment được tạo mới:

~~~sql
CREATE TABLE transaction_heavy_rows (
    row_id     NUMBER PRIMARY KEY,
    bucket_id  NUMBER NOT NULL,
    payload    VARCHAR2(100)
)
INITRANS 12
PCTFREE 25;
~~~

Con số chỉ minh họa. INITRANS 12 dành sẵn nhiều slot hơn mặc định; PCTFREE 25 để lại vùng trống lớn hơn. Nếu block thường chỉ có hai transaction đồng thời, cấu hình này có thể lãng phí không gian mà không mang lợi ích đáng kể.

Đối với một index đang bị ITL wait:

~~~sql
ALTER INDEX ix_transaction_heavy_rows
INITRANS 8;

ALTER INDEX ix_transaction_heavy_rows
REBUILD INITRANS 8 PCTFREE 20;
~~~

Lệnh ALTER INDEX thay đổi storage attribute cho việc tạo block về sau; REBUILD tạo lại index segment với cấu hình chỉ định. Rebuild có chi phí I/O, redo/undo, thời gian và có thể cần không gian bổ sung; lên kế hoạch trong cửa sổ phù hợp và kiểm tra trạng thái index sau thao tác.

Với table, việc áp dụng lên block hiện hữu có thể cần tái tổ chức segment/partition, chẳng hạn MOVE trong điều kiện phù hợp:

~~~sql
ALTER TABLE transaction_heavy_rows
MOVE INITRANS 12
PCTFREE 25;
~~~

MOVE có thể làm thay đổi ROWID và có tác động đến index/availability tùy phiên bản, loại bảng và tùy chọn online. Kiểm tra index validity, dependent objects và kế hoạch triển khai trước khi thực hiện. Không chạy lệnh ví dụ trên bảng production chỉ để thử.

### Trường hợp B: nhiều session cập nhật cùng một row

Nếu wait là row lock contention trên một row duy nhất, INITRANS và PCTFREE không giải quyết được nguyên nhân. Các lựa chọn kiến trúc:

- Giảm số lần cập nhật cùng row bằng cách gom/batch sự kiện.
- Dùng nhiều counter shard theo một khóa phân tán, sau đó SUM các shard khi đọc.
- Ghi sự kiện append-only rồi tổng hợp bất đồng bộ nếu độ trễ nghiệp vụ cho phép.
- Dùng hàng queue/worker để tuần tự hóa phần cập nhật bắt buộc phải có thứ tự.
- Thiết kế lại mô hình dữ liệu để mỗi luồng ghi có vùng dữ liệu riêng.

Ví dụ bộ đếm phân mảnh:

~~~sql
CREATE TABLE page_view_counter (
    page_id   NUMBER NOT NULL,
    shard_no  NUMBER NOT NULL,
    view_count NUMBER DEFAULT 0 NOT NULL,
    CONSTRAINT pk_page_view_counter
        PRIMARY KEY (page_id, shard_no)
);
~~~

Thay vì mọi session UPDATE một row duy nhất theo page_id, ứng dụng chọn shard_no trong một tập shard và cập nhật một row thuộc shard đó. Khi đọc tổng:

~~~sql
SELECT page_id,
       SUM(view_count) AS total_views
FROM page_view_counter
WHERE page_id = :page_id
GROUP BY page_id;
~~~

Sharding counter làm giảm khả năng nhiều session khóa cùng một row, nhưng tăng độ phức tạp đọc và vận hành. Chọn shard dựa trên phân bố ghi; nếu mọi session vẫn chọn shard 0 thì điểm nóng vẫn còn.

### Trường hợp C: hot right-edge index leaf block

Nếu các INSERT tập trung ở leaf block cuối của index khóa tăng dần, cân nhắc:

- Reverse key index nếu truy vấn equality chiếm ưu thế và không cần range scan theo key.
- Global hash-partitioned index hoặc cấu trúc partition phù hợp để phân tán insert.
- Thiết kế khóa/index khác nếu có thể tránh monotonic leading key.
- Scalable sequence hoặc cách cấp key phân tán phù hợp phiên bản và ứng dụng.

Sequence CACHE giảm chi phí cấp số, nhưng bản thân nó không loại bỏ leaf block nóng. Cũng không bật ORDER cho sequence trong RAC nếu ứng dụng không cần thứ tự toàn cục; ORDER có thể tạo thêm serialization. Hãy kiểm tra đặc tính sequence và yêu cầu business trước khi thay.

### Trường hợp D: buffer busy hoặc cache buffers chains

Nếu không có ITL waits đáng kể nhưng buffer busy/cache buffers chains cao trên một block:

- Xác định block là table, index, segment header, bitmap hay block loại khác.
- Xác định SQL nào truy cập block đó và thao tác là insert/update/select.
- Xem có hot row, right-edge index, bitmap/free-space management hoặc một cấu trúc metadata tập trung không.
- Phân tán thao tác trên nhiều block/partition hoặc thay đổi mô hình truy cập.
- Chỉ thay INITRANS/PCTFREE nếu bằng chứng chỉ ra ITL/free-space là nút thắt.

## 9. ASSM, freelist và quản lý free space

Oracle có các cơ chế quản lý free space trong segment. Với Automatic Segment Space Management (ASSM), bitmap block quản lý mức sử dụng/free space của các block trong segment. Với Manual Segment Space Management (MSSM), freelist quản lý block còn chỗ để INSERT.

ASSM giúp giảm một số dạng tranh chấp freelist/segment header so với cách quản lý thủ công trong workload phù hợp, nhưng **không loại bỏ hot row, hot index leaf block hay ITL contention**. Một block dữ liệu vẫn có thể nóng nếu nhiều transaction cùng truy cập nó.

Các điểm cần phân biệt:

- ASSM bitmap contention là tranh chấp liên quan tới block bitmap quản lý không gian; không đồng nghĩa ITL wait trong table block.
- MSSM freelist contention có thể liên quan đến việc nhiều session lấy block trống từ cùng freelist; FREELISTS/FREELIST GROUPS là tham số của cơ chế quản lý thủ công trong các môi trường áp dụng.
- ITL contention xảy ra trong block chứa row/index entry khi không đủ transaction slot.
- Hot index leaf block liên quan tới cấu trúc B-tree và phân bố key, không phải freelist của table.

Không chuyển MSSM sang ASSM hoặc đổi storage management chỉ dựa vào một wait event. Xác định đúng block type và cơ chế đang quản lý segment trước.

## 10. RAC: hot block giữa nhiều instance

Trong Oracle RAC, mỗi instance có buffer cache riêng. Một block được nhiều instance đọc/ghi có thể phải chuyển quyền sở hữu qua Global Cache Service (GCS)/Cache Fusion. Nếu nhiều instance liên tục cập nhật cùng block, block có thể bị ping qua lại và tạo global cache waits.

Các dấu hiệu có thể gồm:

- gc buffer busy acquire/release.
- gc current block busy.
- gc current request hoặc các wait global cache liên quan tùy phiên bản.

Hướng giảm tranh chấp:

- Phân vùng workload theo service/instance nếu ứng dụng cho phép.
- Dùng partitioning hoặc hash distribution để các instance làm việc trên các block khác nhau.
- Tránh để các instance cùng cập nhật một nhóm row/index leaf block nóng.
- Kiểm tra affinity của service và phân bố session; không chuyển session qua instance một cách ngẫu nhiên nếu việc đó làm tăng block ping.
- Đo global cache traffic và wait theo object/block trước và sau thay đổi.

Instance affinity chỉ có ích nếu workload được phân chia thực sự. Nếu tất cả instance vẫn cập nhật cùng một block, việc gắn service có thể không giải quyết được điểm nóng.

## 11. Đo lường trước và sau khi tuning

Một thay đổi storage hoặc schema có thể giảm wait nhưng đồng thời làm segment lớn hơn, tăng số block đọc hoặc ảnh hưởng range scan. Cần đo nhiều chiều:

| Chỉ số | Câu hỏi |
| --- | --- |
| ITL waits | Có giảm wait do thiếu ITL entry không? |
| Buffer busy waits | Block contention tổng thể có giảm không? |
| Row lock waits | Có còn hot row hoặc transaction giữ khóa lâu không? |
| Throughput | Số transaction/giây có tăng không? |
| Latency | p95/p99 của thao tác ghi có giảm không? |
| Redo/undo | Lượng redo/undo có tăng do thay đổi kiến trúc không? |
| Segment size | INITRANS/PCTFREE/partitioning có làm tăng footprint không? |
| Read performance | Range scan, equality lookup và báo cáo có bị chậm đi không? |
| RAC global cache | Block transfer/ping có giảm không? |

So sánh trên cùng khung thời gian, cùng loại dữ liệu và mức đồng thời tương đương. Nếu workload thay đổi nhiều, chênh lệch counter có thể không phản ánh tác động của cấu hình.

## 12. Bài thực hành: quan sát row, block và ITL

Bài lab dùng schema học tập có quyền CREATE TABLE và quota phù hợp. Mục tiêu là quan sát cách nhiều row nằm trong cùng block và đọc metadata storage. Việc tái tạo wait ITL chính xác phụ thuộc block size, row density, số session và thời gian transaction; một lab nhỏ có thể không tạo wait nếu Oracle còn đủ chỗ để cấp ITL động.

### Bước 1: tạo bảng thử nghiệm

~~~sql
CREATE TABLE hot_rows_demo (
    id         NUMBER PRIMARY KEY,
    group_id   NUMBER NOT NULL,
    value_num  NUMBER DEFAULT 0 NOT NULL,
    payload    VARCHAR2(30)
)
INITRANS 1
PCTFREE 0;

INSERT INTO hot_rows_demo (id, group_id, value_num, payload)
SELECT level,
       MOD(level, 20),
       0,
       RPAD('X', 20, 'X')
FROM dual
CONNECT BY level <= 2000;

COMMIT;
~~~

PCTFREE 0 chỉ phục vụ minh họa để block ít vùng trống hơn; không dùng làm khuyến nghị mặc định cho bảng cập nhật thường xuyên.

### Bước 2: xem các row nằm trong block nào

~~~sql
SELECT DBMS_ROWID.ROWID_RELATIVE_FNO(rowid) AS file_no,
       DBMS_ROWID.ROWID_BLOCK_NUMBER(rowid) AS block_no,
       COUNT(*) AS rows_in_block,
       MIN(id) AS min_id,
       MAX(id) AS max_id
FROM hot_rows_demo
GROUP BY DBMS_ROWID.ROWID_RELATIVE_FNO(rowid),
         DBMS_ROWID.ROWID_BLOCK_NUMBER(rowid)
ORDER BY rows_in_block DESC;
~~~

Chọn một block có nhiều row. Ghi lại hai ID khác nhau nằm trong cùng block để dùng trong hai session. Với bảng partitioned hoặc dạng lưu trữ đặc biệt, cách diễn giải ROWID/file number có thể cần điều chỉnh.

### Bước 3: kiểm tra storage attribute

~~~sql
SELECT owner,
       table_name,
       ini_trans,
       pct_free
FROM all_tables
WHERE table_name = 'HOT_ROWS_DEMO';
~~~

Nếu có quyền DBA, có thể xem thông tin của mọi schema qua DBA_TABLES. Với index:

~~~sql
SELECT owner,
       index_name,
       ini_trans,
       pct_free
FROM all_indexes
WHERE table_name = 'HOT_ROWS_DEMO';
~~~

### Bước 4: thử cập nhật hai row cùng block

Mở hai session riêng. Thay :id_a và :id_b bằng hai ID khác nhau đã xác nhận cùng block.

Session A:

~~~sql
UPDATE hot_rows_demo
SET value_num = value_num + 1
WHERE id = :id_a;

-- Giữ transaction mở, chưa commit.
~~~

Session B:

~~~sql
UPDATE hot_rows_demo
SET value_num = value_num + 1
WHERE id = :id_b;
~~~

Hai session sửa hai row khác nhau. Nếu có đủ ITL slot hoặc Oracle cấp thêm được ITL, cả hai có thể hoàn tất mà không chờ. Nếu block thiếu ITL và không thể mở rộng, session có thể chờ allocate ITL entry. Không thấy wait trong một lần thử không có nghĩa ITL contention không tồn tại ở workload lớn.

Kết thúc session A bằng COMMIT hoặc ROLLBACK. Sau đó kiểm tra session B và kết thúc transaction B. Không để session thử nghiệm giữ khóa lâu.

### Bước 5: xem segment statistics

~~~sql
SELECT owner,
       object_name,
       statistic_name,
       value
FROM v$segment_statistics
WHERE object_name = 'HOT_ROWS_DEMO'
  AND statistic_name IN ('ITL waits', 'buffer busy waits', 'row lock waits');
~~~

Ghi lại số liệu trước/sau khi chạy đồng thời. Đây là counter tích lũy; muốn đánh giá đúng, hãy lấy delta trong cùng một khoảng thời gian.

### Bước 6: thử thay INITRANS trên block mới

Tạo một bảng thử khác với INITRANS lớn hơn:

~~~sql
CREATE TABLE hot_rows_demo_itl8 (
    id         NUMBER PRIMARY KEY,
    group_id   NUMBER NOT NULL,
    value_num  NUMBER DEFAULT 0 NOT NULL,
    payload    VARCHAR2(30)
)
INITRANS 8
PCTFREE 20;

INSERT INTO hot_rows_demo_itl8
SELECT *
FROM hot_rows_demo;

COMMIT;
~~~

Chạy lại bài kiểm tra nhiều session và so sánh. Lưu ý bảng mới có thể chứa row theo cách phân bổ block khác; để so sánh có ý nghĩa, cần giữ workload và điều kiện thử gần tương đương.

### Bước 7: dọn dữ liệu

~~~sql
DROP TABLE hot_rows_demo_itl8 PURGE;
DROP TABLE hot_rows_demo PURGE;
~~~

Chỉ chạy khi đã hoàn thành lab và không cần giữ dữ liệu. DROP TABLE là DDL gây implicit commit; PURGE bỏ qua Recycle Bin.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Nhiều session chờ dù update row khác nhau | ITL thiếu hoặc block buffer nóng | Xem wait event, ITL waits, object và block. |
| Tăng INITRANS nhưng wait không giảm | Nguyên nhân là hot row hoặc buffer/index contention khác | Phân biệt row lock, ITL allocation và buffer busy. |
| Tăng PCTFREE làm table lớn hơn | Mật độ row/block giảm | Đo số block, full scan, buffer gets và lợi ích ITL thực tế. |
| INSERT chậm trên index có khóa tăng dần | Right-edge leaf block nóng | Xác định index/block; cân nhắc reverse key hoặc hash partition nếu truy vấn cho phép. |
| Reverse key index làm truy vấn range chậm | Reverse key không giữ thứ tự khóa gốc cho range scan | Chỉ dùng khi workload equality phù hợp; cân nhắc thiết kế index khác. |
| ASSM bật nhưng vẫn có hot block | ASSM không loại bỏ row/block/ITL contention | Xác định đúng loại block và wait event. |
| RAC có nhiều global cache wait | Block nóng được chuyển giữa instance | Xem service affinity, phân vùng workload và global cache statistics. |
| ITL wait counter cao nhưng hiện tại không có wait | Counter là số liệu tích lũy | So sánh delta theo thời gian, không kết luận từ tổng số. |
| ALTER TABLE INITRANS không thay đổi block cũ như mong đợi | Block hiện hữu chưa được viết lại | Xem xét MOVE/reorganization có kế hoạch và kiểm tra index. |

## 14. Câu hỏi tự kiểm tra

1. **Hot block là gì?** Một block bị nhiều session cùng truy cập hoặc thay đổi, tạo điểm tranh chấp.
2. **Hot row khác hot block thế nào?** Hot row là nhiều transaction cùng muốn sửa một row; hot block có thể liên quan tới nhiều row khác nhau cùng nằm trong một block.
3. **ITL là gì?** Danh sách transaction entry trong block dùng để ghi nhận transaction đang sửa các row thuộc block đó.
4. **ITL contention thường tạo wait event nào?** enq: TX - allocate ITL entry.
5. **Row lock contention thường tạo wait event nào?** enq: TX - row lock contention.
6. **INITRANS có tác dụng gì?** Dành sẵn số ITL entry ban đầu trong block mới của segment.
7. **PCTFREE hỗ trợ ITL thế nào?** Giữ free space để row và ITL entry có thể mở rộng khi cần.
8. **Tăng INITRANS có chữa hot row không?** Không; nó không cho phép nhiều transaction sửa cùng một row đã bị khóa.
9. **Vì sao index khóa tăng dần có thể nóng ở mép phải?** Các entry mới liên tục được chèn vào vùng leaf block cuối.
10. **Reverse key index đánh đổi điều gì?** Có thể phân tán insert nhưng không phù hợp range scan theo thứ tự khóa gốc.
11. **CACHE sequence có loại bỏ hot index leaf block không?** Không; CACHE giảm chi phí cấp sequence, không tự phân tán index entry.
12. **ASSM có loại bỏ ITL contention không?** Không; ASSM quản lý free space nhưng ITL vẫn nằm trong block dữ liệu/index.
13. **Vì sao phải xác định segment/block trước khi tuning?** Table, index, bitmap và segment header có nguyên nhân và biện pháp khác nhau.
14. **Khi nào cần xem ASH?** Khi cần tương quan session, SQL, wait event và block theo thời gian; phải tuân thủ license Diagnostics Pack.
15. **Đo tuning bằng chỉ số nào?** ITL/buffer/row lock waits, throughput, latency, redo/undo, segment size và tác động tới truy vấn đọc.

Hot block, ITL và tranh chấp khi cập nhật tập trung là các hiện tượng liên quan nhưng không đồng nhất. Hãy phân biệt transaction đang chờ cùng một row, chờ ITL slot hay tranh chấp buffer/index block. INITRANS và PCTFREE có ích khi bằng chứng chỉ ra thiếu ITL/free space; reverse key, hash partitioning và sharded counter có thể phân tán một số điểm ghi nóng nhưng đi kèm đánh đổi truy vấn và vận hành. Chẩn đoán block, SQL và wait event trước khi thay cấu trúc; sau đó đo lại trên workload tương đương để xác nhận hiệu quả.
