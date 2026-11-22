# Phát hiện chỉ mục trùng lặp, ít dùng và quyết định loại bỏ có kiểm chứng

Chỉ mục giúp cơ sở dữ liệu tìm và sắp xếp dữ liệu hiệu quả, nhưng mỗi chỉ mục cũng tiêu tốn dung lượng và phải được duy trì khi dữ liệu thay đổi. Một bảng có quá nhiều chỉ mục gần giống nhau có thể làm INSERT, UPDATE và DELETE chậm hơn, tăng I/O, chiếm bộ nhớ đệm và kéo dài thời gian bảo trì. Ngược lại, loại bỏ một chỉ mục tưởng như không dùng có thể làm truy vấn quan trọng chậm đột ngột hoặc phá vỡ một ràng buộc dữ liệu.

Trong chương **Thiết kế chỉ mục** của module **DATABASE_PERFORMANCE**, bài học này hướng dẫn cách phát hiện chỉ mục trùng lặp, chỉ mục ít được sử dụng và quyết định loại bỏ dựa trên bằng chứng. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Vì vậy, việc dọn chỉ mục cần kết hợp metadata, thống kê sử dụng, workload theo chu kỳ nghiệp vụ, kế hoạch truy vấn và chi phí ghi; một bộ đếm bằng không trong một khoảng quan sát ngắn không đủ để kết luận chỉ mục vô ích.

## 1. Vì sao cần rà soát chỉ mục?

Mỗi chỉ mục là một cấu trúc dữ liệu riêng được lưu trữ và cập nhật song song với bảng. Khi một hàng được thêm, sửa hoặc xóa, hệ quản trị có thể phải cập nhật nhiều chỉ mục liên quan. Số lượng và độ rộng chỉ mục càng lớn thì chi phí duy trì càng có thể tăng.

Một tập chỉ mục không được quản lý tốt có thể gây ra:

- **Write amplification:** một thao tác ghi phải cập nhật nhiều cấu trúc chỉ mục.
- **Dung lượng lưu trữ tăng:** chỉ mục có thể chiếm dung lượng đáng kể so với dữ liệu bảng.
- **Áp lực bộ nhớ đệm:** các trang chỉ mục cạnh tranh cache với trang dữ liệu và chỉ mục quan trọng.
- **I/O và thời gian bảo trì tăng:** backup, replication, vacuum, rebuild hoặc tác vụ bảo trì có thể tốn thêm tài nguyên.
- **Khó hiểu kế hoạch:** nhiều chỉ mục tương tự khiến việc phân tích lựa chọn của bộ tối ưu phức tạp hơn.
- **Chi phí triển khai:** tạo, thay đổi và đồng bộ chỉ mục trên các môi trường có thể kéo dài.

Rà soát chỉ mục có hai mục tiêu cùng lúc: tìm cấu trúc dư thừa để giảm chi phí duy trì và bảo vệ những đường truy cập quan trọng. Tối ưu số lượng chỉ mục không có nghĩa là giảm số lượng bằng mọi giá. Một chỉ mục hiếm khi được dùng vẫn có thể rất quan trọng nếu nó phục vụ báo cáo cuối tháng, xử lý sự cố hoặc một ràng buộc toàn vẹn.

## 2. Phân biệt chỉ mục trùng lặp, chồng lấn và ít dùng

Ba khái niệm này cần được tách riêng vì cách đánh giá và quyết định xử lý khác nhau.

### 2.1. Chỉ mục trùng lặp chính xác

Hai chỉ mục có thể được xem là trùng lặp khi chúng có cùng đối tượng bảng, cùng loại cấu trúc, cùng thứ tự cột khóa và cùng thuộc tính ảnh hưởng đến ngữ nghĩa hoặc cách truy cập. Tuy nhiên, chỉ so sánh tên hoặc danh sách cột là chưa đủ.

Khi xác định trùng lặp, cần so sánh:

- Cột khóa và thứ tự cột.
- Hướng sắp xếp ASC/DESC.
- Tính duy nhất (UNIQUE) và vai trò khóa chính.
- Điều kiện lọc của partial/filtered index.
- Cột INCLUDE hoặc cột bao phủ.
- Collation, operator class hoặc kiểu so sánh.
- Biểu thức được lập chỉ mục.
- Kiểu chỉ mục, phân vùng và các thuộc tính riêng của hệ quản trị.

Ví dụ, hai B-tree cùng khóa (tenant_id, created_at) có thể gần như trùng lặp nếu mọi thuộc tính còn lại giống nhau. Nhưng một chỉ mục UNIQUE và một chỉ mục không UNIQUE có ý nghĩa khác nhau: chỉ mục duy nhất còn thực thi quy tắc dữ liệu. Một chỉ mục có điều kiện WHERE status = 'OPEN' cũng không tương đương với chỉ mục trên toàn bảng.

### 2.2. Chỉ mục chồng lấn hoặc có thể dư thừa

Một chỉ mục có thể là tiền tố của chỉ mục khác. Ví dụ:

~~~sql
CREATE INDEX idx_orders_tenant
ON orders (tenant_id);

CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
~~~

Chỉ mục thứ hai có tiền tố tenant_id nên có thể hỗ trợ nhiều truy vấn mà chỉ mục thứ nhất hỗ trợ. Điều đó tạo ra một ứng viên để xem xét loại bỏ, nhưng không tự động chứng minh chỉ mục đơn là dư thừa.

Chỉ mục đơn có thể nhỏ hơn, ít trang hơn và rẻ hơn khi truy vấn chỉ cần tenant_id. Nó cũng có thể có đặc tính UNIQUE, INCLUDE, filter, collation hoặc hướng sắp xếp khác. Với một số hệ quản trị, bộ tối ưu có thể tận dụng chỉ mục dài cho tiền tố; với hệ quản trị khác hoặc một số workload, chỉ mục ngắn vẫn đem lại lợi ích đáng kể.

Vì vậy, hãy gọi đây là **chồng lấn** hoặc **ứng viên dư thừa** cho đến khi đã kiểm tra workload và kế hoạch.

### 2.3. Chỉ mục ít dùng hoặc chưa thấy được dùng

Chỉ mục ít dùng là chỉ mục có số lần truy cập thấp so với thời gian quan sát, hoặc không có lần truy cập nào được ghi nhận trong thống kê hiện tại. Chỉ số này phụ thuộc cách hệ quản trị đếm, thời điểm reset và việc workload nào đã chạy.

Một chỉ mục không được dùng trong giờ làm việc có thể phục vụ:

- Báo cáo hàng tuần hoặc cuối tháng.
- Tác vụ batch hoặc ETL theo lịch.
- Quy trình đóng sổ, đối soát hoặc lưu trữ.
- Tìm kiếm hiếm khi xảy ra nhưng có yêu cầu độ trễ nghiêm ngặt.
- Một truy vấn chỉ chạy khi có sự cố.
- Ràng buộc UNIQUE, PRIMARY KEY hoặc đường truy cập hỗ trợ thao tác tham chiếu.

Do đó, chỉ số sử dụng thấp là tín hiệu để điều tra, không phải lệnh xóa.

## 3. Đọc metadata để hiểu cấu trúc chỉ mục

Trước khi so sánh mức sử dụng, hãy lập danh mục chỉ mục và thuộc tính của chúng. Một danh mục tốt nên có:

| Thông tin | Câu hỏi cần trả lời |
|---|---|
| Bảng và schema | Chỉ mục thuộc đối tượng nào? |
| Tên và loại chỉ mục | B-tree, hash, bitmap, full-text hay loại khác? |
| Cột khóa | Những cột nào được sắp xếp và theo thứ tự nào? |
| Cột bao phủ | Có cột INCLUDE hoặc dữ liệu bổ sung không? |
| Tính duy nhất | Có thực thi UNIQUE hoặc PRIMARY KEY không? |
| Điều kiện lọc | Đây có phải partial/filtered index không? |
| Biểu thức và collation | Khóa có được tạo từ biểu thức hoặc quy tắc so sánh riêng không? |
| Kích thước | Chỉ mục chiếm bao nhiêu trang hoặc dung lượng? |
| Phụ thuộc | Chỉ mục có được constraint hoặc đối tượng khác sử dụng không? |

Không suy luận cấu trúc chỉ mục từ tên. Tên như idx_orders_status có thể gây hiểu nhầm nếu chỉ mục thực tế chứa nhiều cột, có INCLUDE hoặc filter. Luôn xem catalog hoặc giao diện metadata chính thức của hệ quản trị.

Với chỉ mục phân vùng, cần phân biệt chỉ mục logic ở bảng cha với các cấu trúc chỉ mục vật lý trên từng phân vùng. Một chỉ mục có thể có mức sử dụng khác nhau giữa các phân vùng. Rà soát ở sai cấp có thể khiến bạn bỏ sót nơi đang được sử dụng.

## 4. Đo mức sử dụng chỉ mục

Số lần truy cập là một phần của bằng chứng. Cần xem thêm lượng hàng hoặc trang được đọc, thời gian chờ, chi phí ghi và khoảng thời gian thống kê được tích lũy.

Các chỉ số có thể hữu ích:

- Số lần seek hoặc lookup để tìm một vùng khóa.
- Số lần scan hoặc quét chỉ mục.
- Số hàng được đọc và số hàng được trả về.
- Thời gian chờ hoặc thời gian I/O liên quan nếu hệ quản trị cung cấp.
- Số lần cập nhật chỉ mục do INSERT/UPDATE/DELETE.
- Kích thước chỉ mục và số trang.
- Thời điểm bắt đầu thống kê hoặc lần reset gần nhất.

Không so sánh trực tiếp các bộ đếm có định nghĩa khác nhau giữa các hệ quản trị. Một lần scan có thể là một thao tác quét lớn, trong khi hàng nghìn lần seek có thể phục vụ truy vấn rất nhỏ. Số lần truy cập không thể thay thế việc xem tổng thời gian tiêu thụ và ảnh hưởng đến người dùng.

### 4.1. Ví dụ với PostgreSQL

PostgreSQL cung cấp các view thống kê như pg_stat_user_indexes và pg_stat_all_indexes. Ví dụ truy vấn để xem mức sử dụng và kích thước chỉ mục:

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC;
~~~

Các cột thường được quan tâm:

- idx_scan: số lần index được dùng trong các lần index scan theo cách hệ quản trị ghi nhận.
- idx_tup_read: số mục chỉ mục được đọc.
- idx_tup_fetch: số hàng của bảng được lấy thông qua chỉ mục trong các trường hợp được tính.

Đây là số liệu thống kê tích lũy trong phạm vi mà hệ thống đang theo dõi. Hãy xác định thời điểm reset, chu kỳ vận hành và các tác vụ có chạy trong khoảng đó. Một giá trị idx_scan bằng 0 chỉ nói rằng chưa có lần scan được ghi nhận trong phạm vi thống kê hiện tại; nó không chứng minh chỉ mục không cần thiết.

Có thể xem kích thước chỉ mục bằng pg_relation_size hoặc các hàm kích thước liên quan. Kích thước lớn không tự động là lý do xóa: chỉ mục lớn có thể phục vụ truy vấn quan trọng và giảm nhiều I/O hơn chi phí lưu trữ của nó.

### 4.2. Ví dụ với MySQL

MySQL có thể cung cấp thống kê I/O theo chỉ mục qua Performance Schema, ví dụ bảng table_io_waits_summary_by_index_usage. Một truy vấn tham khảo:

~~~sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    COUNT_STAR,
    COUNT_READ,
    COUNT_WRITE,
    SUM_TIMER_WAIT
FROM performance_schema.table_io_waits_summary_by_index_usage
WHERE OBJECT_SCHEMA = DATABASE()
ORDER BY SUM_TIMER_WAIT DESC;
~~~

Cần kiểm tra Performance Schema đã được bật và bảng thống kê có sẵn trong phiên bản đang dùng. INDEX_NAME có thể là NULL cho hoạt động không gắn với một chỉ mục cụ thể, chẳng hạn truy cập toàn bảng theo cách hệ quản trị ghi nhận. Các bộ đếm và thời gian là số liệu tổng hợp, không nhất thiết tương đương số lần một câu SQL được gọi.

Một số bản MySQL cung cấp view sys.schema_unused_indexes để hỗ trợ tìm ứng viên không được sử dụng. Hãy đọc định nghĩa view và phạm vi thống kê của phiên bản đang chạy trước khi dựa vào kết quả.

### 4.3. Ví dụ với SQL Server

SQL Server cung cấp sys.dm_db_index_usage_stats với các bộ đếm user_seeks, user_scans, user_lookups và user_updates. Các bộ đếm này có thể giúp so sánh hoạt động đọc với số lần cập nhật chỉ mục.

Cần lưu ý thống kê usage có thể mất hoặc bắt đầu lại sau một số sự kiện vòng đời như khởi động lại dịch vụ hoặc thay đổi trạng thái database. Vì vậy, một chỉ mục có số lần seek bằng 0 ngay sau khi khởi động không phải bằng chứng đủ để xóa. Hãy lưu ý thời gian máy chủ hoạt động, thời điểm reset và chu kỳ workload.

Tên view, quyền truy cập và cách tính có thể khác theo phiên bản SQL Server. Dùng tài liệu phiên bản thực tế và xem metadata constraint trước khi kết luận.

## 5. Không nhầm số lần truy cập với giá trị của chỉ mục

Một chỉ mục có nhiều lần seek chưa chắc là chỉ mục hiệu quả. Nó có thể phục vụ một truy vấn đọc rất nhiều hàng, hoặc truy vấn vẫn phải lookup từng hàng ở bảng. Ngược lại, chỉ mục chỉ được dùng vài lần có thể giúp một truy vấn báo cáo quan trọng hoàn tất trong vài giây thay vì hàng chục phút.

Để đánh giá giá trị, hãy đặt các câu hỏi:

- Chỉ mục phục vụ query fingerprint nào?
- Các truy vấn đó chạy bao nhiêu lần và tiêu thụ tổng thời gian bao nhiêu?
- Chỉ mục giảm được bao nhiêu hàng hoặc trang phải đọc?
- Truy vấn có nằm trên đường nghiệp vụ quan trọng không?
- Nếu bỏ chỉ mục, kế hoạch sẽ chuyển sang đường truy cập nào?
- Truy vấn có thể chạy theo lịch hoặc chỉ xuất hiện trong mùa cao điểm không?
- Chỉ mục có bảo vệ một quy tắc dữ liệu hay hỗ trợ thao tác tham chiếu không?

Một chỉ mục nhỏ dùng hàng triệu lần có thể đáng giữ. Một chỉ mục lớn không có truy cập trong một chu kỳ quan sát dài có thể là ứng viên xem xét, nhưng vẫn cần kiểm tra phụ thuộc và workload hiếm.

## 6. Tính chi phí ghi và lợi ích đọc

Để biết chỉ mục có đang tạo gánh nặng hay không, hãy xem cả hoạt động đọc lẫn ghi.

Một chỉ mục có thể giảm số trang đọc cho SELECT nhưng tăng chi phí của INSERT, UPDATE và DELETE. Nếu bảng có tỷ lệ ghi cao, mỗi chỉ mục bổ sung có thể làm tăng công việc cập nhật cấu trúc B-tree, tạo page split, ghi log và phát sinh I/O.

Có thể phân nhóm chỉ mục theo ma trận:

| Lợi ích đọc | Chi phí ghi | Hướng đánh giá |
|---|---|---|
| Cao | Thấp | Thường nên giữ nếu hỗ trợ truy vấn quan trọng |
| Cao | Cao | Đo lợi ích tổng thể và cân nhắc thiết kế hẹp hơn |
| Thấp | Cao | Ứng viên cần điều tra kỹ về dư thừa hoặc loại bỏ |
| Thấp | Thấp | Xem dung lượng, phụ thuộc và workload hiếm trước khi quyết định |
| Chưa rõ | Chưa rõ | Thu thập thêm số liệu trước khi thay đổi |

Một số hệ quản trị cung cấp bộ đếm cập nhật chỉ mục hoặc thống kê thời gian chờ ghi. Các bộ đếm này không phải lúc nào cũng quy đổi trực tiếp thành chi phí của một chỉ mục riêng lẻ. Hãy kết hợp với benchmark có kiểm soát hoặc thử nghiệm workload đại diện khi cần định lượng tác động.

## 7. Những chỉ mục không được xem là dư thừa chỉ vì ít truy vấn

Trước khi loại bỏ, cần kiểm tra các vai trò không thể hiện đầy đủ qua bộ đếm SELECT:

### 7.1. Chỉ mục hỗ trợ ràng buộc

Chỉ mục PRIMARY KEY hoặc UNIQUE thực thi tính duy nhất. Xóa nó có thể làm mất ràng buộc hoặc bị hệ quản trị từ chối. Một số hệ quản trị triển khai constraint thông qua chỉ mục; một số có quan hệ metadata riêng. Phải kiểm tra dependency trước khi thay đổi.

Chỉ mục hỗ trợ khóa ngoại cũng cần được xem xét. Nhiều hệ quản trị không tự động tạo chỉ mục ở phía cột tham chiếu của foreign key. Dù chỉ mục đó ít được dùng bởi SELECT thông thường, nó có thể giúp kiểm tra, cập nhật hoặc xóa hàng ở bảng cha và giảm việc quét bảng con. Hành vi chính xác tùy hệ quản trị.

### 7.2. Chỉ mục phục vụ tác vụ định kỳ

Báo cáo cuối tháng, đối soát cuối ngày, tác vụ lưu trữ hoặc batch có thể không xuất hiện trong khoảng theo dõi ngắn. Hãy lập lịch workload theo tuần, tháng, quý và các đợt nghiệp vụ đặc biệt.

### 7.3. Chỉ mục phục vụ sự cố và truy vấn hiếm

Một truy vấn điều tra có thể hiếm khi chạy nhưng rất quan trọng khi hệ thống gặp sự cố. Nếu loại bỏ chỉ mục khiến truy vấn chẩn đoán không thể hoàn thành trong thời gian chấp nhận được, lợi ích ghi nhỏ có thể không bù được rủi ro vận hành.

### 7.4. Chỉ mục hỗ trợ sắp xếp, phân trang và truy cập đặc biệt

Một chỉ mục có thể hỗ trợ ORDER BY, GROUP BY, phân trang, tìm kiếm theo biểu thức, partial predicate hoặc một loại operator cụ thể. Truy vấn dùng tính năng này có thể không được nhận diện nếu chỉ tìm kiếm các câu SELECT đơn giản trong log.

## 8. So sánh chỉ mục chồng lấn một cách chính xác

Khi hai chỉ mục có vẻ giống nhau, hãy so sánh từng thuộc tính thay vì chỉ so sánh số cột.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_tenant_status
ON orders (tenant_id, status);

CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Chỉ mục thứ hai có tiền tố (tenant_id, status), nên có thể hỗ trợ truy vấn tìm theo hai cột đầu. Nhưng chỉ mục thứ nhất hẹp hơn, có thể chiếm ít trang hơn và có chi phí ghi thấp hơn nếu workload chỉ cần hai cột đó. Nếu hai chỉ mục khác tính duy nhất, điều kiện lọc hoặc INCLUDE, chúng có thể không thay thế được nhau.

Một số khác biệt cần kiểm tra:

| Thuộc tính | Vì sao quan trọng |
|---|---|
| Thứ tự cột | Xác định tiền tố và vùng tìm kiếm |
| ASC/DESC | Có thể ảnh hưởng ORDER BY nhiều cột |
| UNIQUE | Thực thi quy tắc dữ liệu |
| INCLUDE | Có thể tránh lookup nhưng làm chỉ mục rộng hơn |
| Filter/predicate | Chỉ mục chỉ bao phủ một tập hàng |
| Expression | Khóa có thể là kết quả của hàm |
| Collation/operator class | Thay đổi quy tắc so sánh hoặc toán tử được hỗ trợ |
| Partitioning | Phạm vi dữ liệu và cấu trúc vật lý khác nhau |
| Loại chỉ mục | B-tree, full-text, spatial và các loại khác có mục đích riêng |

Ví dụ, chỉ mục B-tree trên email không nhất thiết thay thế chỉ mục lower(email) nếu truy vấn tìm theo biểu thức lower(email). Chỉ mục có filter status = 'OPEN' không thay thế chỉ mục toàn bảng cho truy vấn mọi trạng thái. Một chỉ mục có INCLUDE có thể hỗ trợ index-only access mà chỉ mục hẹp hơn không đáp ứng.

## 9. Tìm chỉ mục không dùng trong một chu kỳ quan sát đủ dài

Chọn khoảng thời gian quan sát phải dựa trên chu kỳ nghiệp vụ, không chỉ số ngày cố định. Hãy bao phủ:

- Ngày làm việc và cuối tuần.
- Giờ cao điểm và giờ thấp điểm.
- Tác vụ batch, ETL và báo cáo định kỳ.
- Cuối tháng hoặc thời điểm chốt kỳ nếu có.
- Mùa cao điểm, chiến dịch hoặc đợt tăng tải có tính chu kỳ.
- Các quy trình bảo trì và phục hồi.

Nếu hệ thống mới khởi động lại hoặc bộ đếm vừa được reset, hãy bắt đầu lại khoảng quan sát hoặc dùng lịch sử telemetry được lưu bên ngoài. Không so sánh bộ đếm hiện tại với dữ liệu tích lũy từ một giai đoạn khác mà không chuẩn hóa thời gian.

Một quy trình quan sát tốt ghi lại ngày bắt đầu, ngày kết thúc, thời điểm reset, workload đã chạy và các ngoại lệ. Khi chưa bao phủ một chu kỳ quan trọng, hãy giữ ứng viên và tiếp tục thu thập dữ liệu.

## 10. Quy trình đánh giá trước khi loại bỏ

Một quyết định loại bỏ nên có bằng chứng và phương án phục hồi. Có thể thực hiện theo các bước:

1. **Lập danh mục:** ghi nhận bảng, chỉ mục, cột khóa, INCLUDE, filter, uniqueness, loại và kích thước.
2. **Kiểm tra phụ thuộc:** xác định PRIMARY KEY, UNIQUE, FOREIGN KEY, constraint, partition và đối tượng liên quan.
3. **Thu thập usage:** đo seek/scan/lookup, số hàng đọc, thời gian và cập nhật trong một chu kỳ đại diện.
4. **Liên kết với workload:** tìm query fingerprint, lịch batch và truy vấn nghiệp vụ được chỉ mục hỗ trợ.
5. **Phân loại ứng viên:** trùng lặp chính xác, chồng lấn tiền tố, ít dùng, không dùng trong khoảng quan sát hoặc có chi phí ghi cao.
6. **So sánh metadata:** kiểm tra thứ tự khóa, hướng sắp xếp, filter, INCLUDE, biểu thức, collation và loại chỉ mục.
7. **Đánh giá kế hoạch:** xem các truy vấn phụ thuộc sẽ dùng đường truy cập nào nếu chỉ mục không còn khả dụng.
8. **Ước lượng chi phí:** so sánh dung lượng tiết kiệm và chi phí ghi giảm với rủi ro tăng độ trễ đọc.
9. **Thử nghiệm có kiểm soát:** dùng môi trường staging, bản sao dữ liệu hoặc cơ chế invisible/disable/hypothetical mà hệ quản trị hỗ trợ.
10. **Định nghĩa tiêu chí dừng:** xác định ngưỡng p95/p99, thời gian báo cáo, lỗi và thông lượng ghi.
11. **Lập phương án phục hồi:** chuẩn bị lệnh tạo lại, cấu hình, thời gian tạo chỉ mục và ảnh hưởng đến hệ thống.
12. **Thực hiện thay đổi:** chọn thời điểm phù hợp và dùng phương thức online/concurrent nếu hệ quản trị hỗ trợ.
13. **Theo dõi sau thay đổi:** quan sát workload đủ dài, kiểm tra truy vấn quan trọng và so sánh với baseline.
14. **Ghi lại quyết định:** lưu lý do giữ hoặc loại bỏ, số liệu, phạm vi, thời điểm và kết quả.

## 11. Thử nghiệm trước khi xóa trên production

Một số hệ quản trị hỗ trợ làm chỉ mục không hiển thị với bộ tối ưu nhưng vẫn duy trì cấu trúc, giúp quan sát kế hoạch khi chỉ mục không còn được chọn. MySQL và Oracle có cơ chế invisible index với hành vi riêng theo nền tảng. SQL Server có khả năng disable index trong những trường hợp phù hợp, nhưng thao tác này có thể làm chỉ mục không khả dụng và có thể ảnh hưởng constraint. PostgreSQL không có thuộc tính invisible index tương đương trong lõi; có thể dùng môi trường thử nghiệm hoặc extension chỉ mục giả định để xem kế hoạch dự kiến.

Mỗi cơ chế có giới hạn:

- Invisible index thường vẫn được duy trì khi ghi, nên không mô phỏng đầy đủ lợi ích write-cost sau khi xóa.
- Hypothetical index hoặc kế hoạch giả định cho biết optimizer có thể chọn gì, nhưng không đo thời gian thực tế.
- Disable index có thể ảnh hưởng ràng buộc hoặc khiến truy vấn lỗi tùy loại chỉ mục và hệ quản trị.
- Staging chỉ đáng tin nếu dữ liệu, thống kê, tham số và tải gần với production.

Không dùng một cơ chế thử nghiệm của hệ quản trị này như thể nó có cùng ngữ nghĩa ở nền tảng khác. Hãy đọc tài liệu chính thức và xác định rõ thử nghiệm đang kiểm tra kế hoạch, hiệu năng đọc hay chi phí ghi.

## 12. Loại bỏ và phục hồi có kiểm soát

Trước khi xóa, cần xác nhận:

- Không còn ràng buộc hoặc đối tượng phụ thuộc.
- Khoảng quan sát đã bao phủ chu kỳ workload cần thiết.
- Các truy vấn quan trọng đã được kiểm tra với kế hoạch thay thế.
- Có phương án tạo lại chỉ mục và đủ dung lượng để thực hiện.
- Đã biết thao tác xóa có khóa bảng, chặn ghi hoặc tạo tải I/O như thế nào.
- Có người chịu trách nhiệm theo dõi sau thay đổi và tiêu chí rollback.

Các hệ quản trị có cú pháp và khả năng xóa online khác nhau. Ví dụ, PostgreSQL hỗ trợ DROP INDEX CONCURRENTLY cho một số trường hợp, nhưng lệnh có hạn chế riêng và không chạy bên trong transaction block thông thường. Hệ quản trị khác có tùy chọn online hoặc cơ chế riêng. Hãy chọn cú pháp theo phiên bản thực tế và kiểm tra giới hạn trước khi thực hiện.

Sau khi xóa, theo dõi:

- p50, p95, p99 của truy vấn từng dùng chỉ mục.
- Số hàng đọc, số trang đọc và I/O.
- CPU, thời gian chờ khóa và thời gian chờ tài nguyên.
- Thông lượng INSERT/UPDATE/DELETE.
- Các báo cáo và batch job theo lịch.
- Lỗi timeout, deadlock hoặc truy vấn vượt ngưỡng.
- Thay đổi kế hoạch thực thi sau khi optimizer chọn đường truy cập khác.

Nếu xuất hiện hồi quy vượt tiêu chí đã định, hãy khôi phục chỉ mục hoặc áp dụng phương án thay thế đã được kiểm chứng. Tạo lại chỉ mục có thể mất thời gian và gây tải; vì vậy, kế hoạch phục hồi cần được chuẩn bị trước khi xóa.

## 13. Ví dụ: đánh giá hai chỉ mục trên bảng orders

Giả sử bảng orders có hai chỉ mục:

~~~sql
CREATE INDEX idx_orders_tenant
ON orders (tenant_id);

CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Thống kê usage trong 30 ngày cho thấy idx_orders_tenant có rất ít lần truy cập, trong khi chỉ mục nhiều cột được dùng thường xuyên. Đây là tín hiệu để xem xét, nhưng chưa đủ để xóa.

Quy trình đánh giá:

**Bước 1: So sánh metadata.** Xác nhận hai chỉ mục cùng loại B-tree, không có khác biệt về UNIQUE, filter, INCLUDE, collation hoặc partitioning. Nếu có khác biệt, ghi rõ chúng phục vụ chức năng gì.

**Bước 2: Tìm workload chỉ dùng tenant_id.** Tìm các truy vấn lọc theo tenant_id mà không có status. Kiểm tra chúng có chạy trong batch hoặc báo cáo ngoài khoảng 30 ngày không.

**Bước 3: So sánh kế hoạch.** Dùng EXPLAIN để xem truy vấn chỉ lọc tenant_id có thể dùng tiền tố của chỉ mục nhiều cột hay không. Kiểm tra số hàng và trang phải đọc; chỉ mục dài hơn có thể cần nhiều trang hơn chỉ mục đơn.

**Bước 4: Kiểm tra chi phí ghi.** Xem bảng có tỷ lệ INSERT/UPDATE cao không và chỉ mục đơn có làm tăng đáng kể write amplification hay dung lượng không.

**Bước 5: Thử nghiệm.** Nếu hệ quản trị hỗ trợ invisible index, staging hoặc phương án phù hợp khác, kiểm tra kế hoạch và workload khi chỉ mục đơn không khả dụng. Không giả định kế hoạch giả định đã chứng minh thời gian thực tế.

**Bước 6: Quyết định.** Nếu truy vấn quan trọng vẫn đạt mục tiêu bằng chỉ mục nhiều cột, không có dependency và chi phí duy trì chỉ mục đơn đáng kể, có thể đưa nó vào kế hoạch loại bỏ. Nếu truy vấn chỉ tenant_id bị chậm hoặc workload hiếm chưa được quan sát, giữ lại và tiếp tục điều tra.

**Bước 7: Theo dõi.** Sau khi loại bỏ, so sánh các chỉ số với baseline trong toàn bộ chu kỳ nghiệp vụ. Nếu truy vấn bị ảnh hưởng vượt ngưỡng, phục hồi chỉ mục hoặc thiết kế lại theo bằng chứng mới.

## 14. Các sai lầm thường gặp

- **Xóa chỉ mục vì idx_scan hoặc seek bằng 0.** Bộ đếm có thể vừa reset hoặc chưa bao phủ batch và báo cáo định kỳ.
- **Coi chỉ mục tiền tố luôn thay thế được chỉ mục ngắn.** Chỉ mục ngắn có thể nhỏ hơn, có thuộc tính khác hoặc phục vụ truy vấn đặc biệt.
- **Chỉ so sánh tên và cột.** Filter, INCLUDE, uniqueness, biểu thức, collation và hướng sắp xếp có thể làm hai chỉ mục khác nhau.
- **Bỏ qua constraint và foreign key.** Chỉ mục có thể bảo vệ tính duy nhất hoặc giúp thao tác tham chiếu.
- **Chỉ đo workload đọc.** Một chỉ mục có thể làm tăng chi phí ghi dù ít được SELECT sử dụng.
- **Không tính đến chu kỳ nghiệp vụ.** Một tháng có thể chưa bao phủ tác vụ quý hoặc mùa cao điểm.
- **Coi kế hoạch giả định là benchmark.** Kế hoạch không đo đầy đủ I/O, cache, contention và thời gian thực.
- **Xóa nhiều chỉ mục cùng lúc.** Khi có hồi quy, khó xác định chỉ mục nào gây ra vấn đề.
- **Không chuẩn bị cách phục hồi.** Tạo lại chỉ mục có thể tốn thời gian và tài nguyên.
- **Dừng theo dõi quá sớm.** Hồi quy có thể chỉ xuất hiện khi batch hoặc báo cáo định kỳ chạy.

## 15. Checklist trước khi loại bỏ chỉ mục

- [ ] Đã lập danh mục đầy đủ metadata và kích thước chỉ mục.
- [ ] Đã phân biệt trùng lặp chính xác với chồng lấn tiền tố.
- [ ] Đã kiểm tra UNIQUE, PRIMARY KEY, FOREIGN KEY và các dependency.
- [ ] Đã xác định thời điểm reset của bộ đếm usage.
- [ ] Đã quan sát đủ chu kỳ nghiệp vụ và workload định kỳ.
- [ ] Đã liên kết chỉ mục với query fingerprint và kế hoạch thực thi.
- [ ] Đã đánh giá cả lợi ích đọc và chi phí ghi.
- [ ] Đã xem xét filter, INCLUDE, expression, collation, sort direction và partitioning.
- [ ] Đã thử kế hoạch thay thế bằng phương thức phù hợp với hệ quản trị.
- [ ] Đã định nghĩa ngưỡng dừng và tiêu chí rollback.
- [ ] Đã chuẩn bị phương án tạo lại chỉ mục và đánh giá tác động vận hành.
- [ ] Đã loại bỏ có kiểm soát và theo dõi sau thay đổi.
- [ ] Đã ghi lại bằng chứng và kết luận.

## 16. Nguyên tắc cần ghi nhớ

Chỉ mục trùng lặp, chồng lấn hoặc ít dùng có thể làm tăng chi phí ghi, lưu trữ và bảo trì, nhưng số lần truy cập thấp không đồng nghĩa với không có giá trị. Một chỉ mục có thể phục vụ workload định kỳ, truy vấn sự cố, ràng buộc dữ liệu hoặc đường truy cập quan trọng chưa xuất hiện trong khoảng đo.

Hãy kết hợp metadata chỉ mục, bộ đếm sử dụng, thời điểm reset, query fingerprint, kế hoạch thực thi và chi phí đọc/ghi. Trước khi loại bỏ, kiểm tra dependency, quan sát đủ chu kỳ nghiệp vụ, thử kế hoạch thay thế và chuẩn bị phục hồi. Sau thay đổi, tiếp tục theo dõi toàn workload để xác nhận lợi ích và phát hiện hồi quy. Quyết định tốt là quyết định có thể giải thích bằng số liệu và có phương án xử lý khi kết quả thực tế khác dự kiến.
