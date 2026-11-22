# Thêm, tách, gắn và loại bỏ phân vùng dưới tải

## 1. Vì sao bảo trì phân vùng khi hệ thống vẫn hoạt động cần được thiết kế?

Phân vùng dữ liệu (partitioning) chia một bảng logic thành nhiều phần vật lý hoặc phần lưu trữ có thể quản lý riêng. Các hệ thống thường phân vùng theo thời gian, tenant, vùng địa lý hoặc hash của khóa. Khi dữ liệu tăng liên tục, đội vận hành phải thêm phân vùng mới, tách phân vùng đang quá lớn, gắn một bảng đã nạp dữ liệu vào bảng phân vùng, hoặc loại bỏ phân vùng hết thời hạn lưu trữ.

Những thao tác này thường diễn ra trong khi ứng dụng vẫn đọc và ghi dữ liệu. Một lệnh DDL có thể cần khóa metadata, khóa bảng hoặc khóa partition; có thể quét dữ liệu để xác minh ranh giới; có thể xây dựng lại chỉ mục; và trong một số engine có thể di chuyển hàng loạt dữ liệu. Nếu không kiểm soát, việc bảo trì có thể chặn giao dịch đang chạy, tạo hàng đợi khóa, tăng transaction log/WAL, gây áp lực I/O, làm tăng replication lag hoặc khiến truy vấn bị timeout.

Trong tối ưu hiệu năng cơ sở dữ liệu, mục tiêu của bảo trì partition là giữ đúng ranh giới dữ liệu, giảm thời gian khóa và lượng dữ liệu phải di chuyển, bảo đảm chỉ mục và ràng buộc nhất quán, đồng thời duy trì khả năng đọc/ghi của workload. Cần phân biệt thao tác chỉ thay đổi metadata với thao tác phải scan hoặc di chuyển hàng. Cùng tên thao tác ở hai hệ quản trị có thể có hành vi khóa và chi phí rất khác nhau.

Bài học này giải thích cách thêm (ADD), tách (SPLIT), gắn (ATTACH), tháo (DETACH) và loại bỏ (DROP) phân vùng dưới tải; cách chuẩn bị bảng staging; cách xử lý index, constraint, foreign key và replication; cùng quy trình triển khai, giám sát và khôi phục. Cú pháp và mức độ online phụ thuộc engine, phiên bản, loại partition và cấu trúc bảng. Các ví dụ PostgreSQL và SQL Server được đánh dấu riêng, không đại diện cho mọi hệ quản trị.

## 2. Nắm chắc mô hình phân vùng trước khi thay đổi

### 2.1. Partition key và ranh giới

Partition key là cột hoặc biểu thức dùng để định tuyến một hàng vào partition. Một bảng có thể được phân vùng theo:

- **RANGE:** mỗi partition nhận một khoảng giá trị, thường dùng cho ngày giờ hoặc số tăng dần.
- **LIST:** mỗi partition nhận một tập giá trị cụ thể, thường dùng cho tenant, khu vực hoặc loại nghiệp vụ.
- **HASH:** giá trị khóa được băm để phân phối hàng vào một số partition.
- **Kiểu kết hợp:** nhiều cấp phân vùng, chẳng hạn RANGE theo tháng rồi HASH theo tenant.

Với RANGE, ranh giới thường được biểu diễn theo khoảng nửa mở `[from, to)`: bao gồm giá trị đầu và không bao gồm giá trị cuối. Hai partition liền kề có thể là `[2026-07-01, 2026-08-01)` và `[2026-08-01, 2026-09-01)`. Cách này tránh chồng lấn tại thời điểm chuyển tháng.

Trước khi ADD, SPLIT, ATTACH hoặc DETACH, phải biết rõ:

1. Partition key và kiểu dữ liệu của nó.
2. Ranh giới hiện tại của từng partition, bao gồm quy tắc bao gồm/loại trừ biên.
3. Có default partition hoặc partition nhận giá trị ngoài phạm vi không.
4. Có partition con nhiều cấp không và thao tác tác động ở cấp nào.
5. Ràng buộc CHECK, unique key, primary key, foreign key và quy tắc định tuyến có liên quan.

Một lỗi ranh giới có thể khiến dữ liệu bị từ chối, đi vào default partition, hoặc không được partition pruning như mong đợi. Không dựa vào tên partition để suy ra phạm vi; cần xác minh bound và dữ liệu thực tế.

### 2.2. Partition pruning và khả năng truy vấn

Partition pruning cho phép bộ tối ưu bỏ qua những partition không thể chứa dữ liệu thỏa điều kiện. Ví dụ, truy vấn theo khoảng `event_time` trong tháng 7 có thể chỉ đọc partition tháng 7 nếu điều kiện được viết tương thích với partition key và thống kê/metadata hợp lệ.

Sau thao tác bảo trì, hãy xác nhận:

- Hàng mới được định tuyến vào partition dự kiến.
- Hàng cũ vẫn nằm trong partition có bound hợp lệ.
- Truy vấn theo khoảng vẫn prune các partition không liên quan.
- Truy vấn không vô tình quét default partition hoặc toàn bộ bảng.
- Kế hoạch thực thi và số partition được truy cập phù hợp với workload.

Partition pruning không thay thế chỉ mục. Nếu một partition vẫn rất lớn và truy vấn tìm một số ít hàng, chỉ mục bên trong partition vẫn có thể cần thiết.

### 2.3. Bảng partition và các đối tượng đi kèm

Một partition không chỉ là vùng chứa hàng. Nó có thể có chỉ mục cục bộ, thống kê, constraint, trigger, quyền truy cập, compression, tablespace/filegroup, foreign key hoặc chính sách bảo mật. Một số engine còn có global index hoặc index bao phủ nhiều partition.

Trước khi thay đổi, hãy lập danh sách những đối tượng phải giữ tương thích. Việc ATTACH một bảng chỉ có dữ liệu đúng nhưng thiếu index hoặc constraint cần thiết vẫn có thể khiến truy vấn chậm, thao tác thất bại hoặc tính toàn vẹn không được bảo đảm.

## 3. Phân biệt ADD, SPLIT, ATTACH, DETACH và DROP

Các thao tác có tên gần nhau nhưng mục đích và chi phí khác nhau:

| Thao tác | Mục tiêu | Dữ liệu có phải di chuyển không? | Rủi ro chính dưới tải |
|---|---|---|---|
| ADD partition | Tạo vùng nhận dữ liệu mới | Thường không nếu partition mới rỗng; tùy engine và default partition | Khóa metadata, xác minh default partition, cập nhật index/metadata |
| SPLIT partition | Chia một partition thành nhiều phần theo ranh giới mới | Có thể phải phân phối lại hàng; tùy engine và trạng thái dữ liệu | Scan/di chuyển hàng, log/WAL, I/O, khóa và rebuild index |
| ATTACH partition | Gắn một bảng có sẵn vào bảng partitioned | Có thể cần scan xác minh bound; thường không phải copy hàng nếu đủ điều kiện | Validation scan, khóa bảng, kiểm tra schema/index/constraint |
| DETACH partition | Tách một partition thành bảng độc lập | Thường giữ nguyên dữ liệu tại chỗ, nhưng phụ thuộc engine | Khóa metadata, xử lý index/FK/dependency và giao dịch đang mở |
| DROP partition | Xóa partition và dữ liệu của nó | Không cần xóa từng hàng theo cách thông thường, nhưng thao tác là hủy dữ liệu | Mất dữ liệu, khóa DDL, index/dependency, log và replication |

Đừng xem các thao tác này là hoán đổi cho nhau. Ví dụ, DETACH thường giữ lại bảng và dữ liệu để lưu trữ hoặc xử lý tiếp; DROP loại bỏ partition và dữ liệu theo semantics của engine. SPLIT có thể tốn kém vì hàng cần được phân phối lại; tạo sẵn partition rỗng rồi chuyển dữ liệu theo từng đợt có thể giảm thời gian khóa.

## 4. ADD: tạo partition mới trước khi cần

### 4.1. Tạo trước partition theo lịch

Với bảng sự kiện phân vùng theo tháng, cách vận hành ổn định là tạo partition cho kỳ sắp tới trước khi dữ liệu đầu tiên đến. Như vậy, giao dịch ghi không phải chờ một thao tác DDL khẩn cấp đúng thời điểm chuyển kỳ.

Ví dụ minh họa cho RANGE theo tháng:

```sql
-- Cú pháp minh họa kiểu PostgreSQL declarative partitioning
CREATE TABLE events_2026_08
PARTITION OF events
FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
```

Khoảng bound bao gồm ngày đầu tháng 8 và loại trừ ngày đầu tháng 9. Cần xác nhận kiểu cột thực tế, timezone và cách lưu timestamp trước khi dùng literal. Cú pháp này không dùng chung cho mọi engine.

### 4.2. ADD khi có default partition

Default partition có thể nhận các hàng không khớp partition cụ thể. Khi thêm một partition mới, những hàng thuộc bound mới có thể đang nằm trong default partition. Một số engine yêu cầu xử lý các hàng đó trước, hoặc cần scan/kiểm tra constraint để bảo đảm không có overlap.

Trước khi ADD:

1. Xác định default partition có chứa giá trị trong phạm vi mới không.
2. Đếm và kiểm tra các hàng thuộc bound mới đang ở default partition.
3. Lập kế hoạch chuyển những hàng đó sang partition mới.
4. Xác nhận ranh giới không trùng với partition hiện có.
5. Kiểm tra index, constraint và quyền của partition mới.

Không giả định ADD luôn là thao tác metadata tức thời. Nếu phải di chuyển dữ liệu khỏi default partition hoặc xác minh điều kiện toàn bảng, thời gian và khóa có thể tăng đáng kể.

### 4.3. ADD dưới tải: giảm thời gian khóa

Hãy thực hiện công việc nặng trước thời điểm cần chuyển partition: chuẩn bị tablespace/filegroup, tạo index phù hợp, cập nhật thống kê khi thích hợp và xác minh dữ liệu. Chọn thời điểm tải thấp để chạy DDL, đặt timeout khóa ngắn nếu engine hỗ trợ và giám sát hàng đợi khóa.

Nếu DDL không lấy được khóa nhanh, nên để lệnh thất bại sớm và thử lại theo lịch thay vì đứng chờ lâu rồi chặn các giao dịch đến sau. Cách đặt lock timeout, statement timeout và khả năng retry tùy hệ quản trị.

## 5. SPLIT: tách partition lớn thành các phần nhỏ hơn

### 5.1. Khi nào cần SPLIT?

SPLIT thường được cân nhắc khi một partition đã quá lớn, cần tách lịch sử theo kỳ, phân bố dữ liệu thay đổi hoặc muốn tạo nhiều vùng lưu trữ có đặc tính khác nhau. Tuy nhiên, nếu partition lớn vẫn đáp ứng truy vấn và bảo trì, split không tự động cải thiện hiệu năng.

Trước khi split, hãy xác định vấn đề cụ thể: truy vấn đọc quá nhiều trang, bảo trì index kéo dài, retention khó thực hiện, backup/restore quá lớn, hoặc một partition nóng gây tranh chấp I/O. Nếu nguyên nhân là predicate không sargable hay thiếu thống kê, split có thể không giải quyết được.

### 5.2. Split có thể chỉ đổi metadata hoặc phải di chuyển hàng

Hành vi phụ thuộc engine và vị trí ranh giới. Nếu ranh giới mới nằm trong partition có dữ liệu, hệ thống có thể phải phân loại lại hàng, ghi lại trang, cập nhật index và tạo log/WAL. Một số nền tảng có thuật toán online hoặc tối ưu metadata trong trường hợp nhất định; nền tảng khác có thể khóa lâu hoặc cần dung lượng trống đáng kể.

Nếu split tạo ra partition mới rỗng ở một biên ngoài vùng dữ liệu hiện tại, thao tác có thể ít tốn kém hơn nhiều so với split giữa một partition đang chứa hàng. Đây là lý do nên tạo partition tương lai trước khi dữ liệu đến thay vì đợi partition mặc định hoặc partition hiện tại phình lớn.

### 5.3. Chuẩn bị dung lượng và log

Trước split một partition đang có dữ liệu, ước lượng:

- Số hàng và tổng dung lượng dữ liệu trong partition.
- Dung lượng tạm cần để di chuyển hoặc tái tạo trang/index.
- Tốc độ phát sinh transaction log/WAL và dung lượng log khả dụng.
- Băng thông I/O và ảnh hưởng đến truy vấn đọc/ghi cùng storage.
- Replication lag hoặc thời gian áp dụng log ở replica.
- Thời gian rebuild/validate index và cập nhật thống kê.

Nếu engine ghi log đầy đủ cho thao tác di chuyển, log có thể tăng nhanh hơn dự kiến. Theo dõi dung lượng log và replica trong suốt quá trình; không bắt đầu split lớn khi hệ thống đã gần đầy log hoặc storage.

### 5.4. Chia nhỏ bằng quy trình tạo và chuyển dữ liệu

Khi lệnh SPLIT trực tiếp có thời gian khóa hoặc chi phí quá cao, có thể dùng chiến lược nhiều bước nếu hệ quản trị và mô hình dữ liệu cho phép:

1. Tạo partition đích hoặc bảng staging với schema và constraint đúng.
2. Nạp một phần dữ liệu theo batch, có giới hạn kích thước và thời gian.
3. Đồng bộ các thay đổi mới phát sinh trong lúc copy bằng CDC, trigger hoặc cơ chế ghi kép đã được thiết kế.
4. Kiểm tra số hàng, khóa, checksum hoặc aggregate theo từng phạm vi.
5. Chuyển quyền sở hữu/định tuyến dữ liệu trong một bước ngắn có kiểm soát.
6. Dừng ghi vào vùng cũ, xác minh không còn giao dịch ghi đang chạy rồi hoàn tất chuyển đổi.

Quy trình này phức tạp hơn một lệnh DDL và đòi hỏi thiết kế đồng bộ nhất quán. Không tự tạo cơ chế dual-write nếu không có cách xử lý retry, thứ tự sự kiện, idempotency và lỗi giữa hai nơi. Nếu không chứng minh được tính đầy đủ, nhất quán của dữ liệu, hãy dùng cơ chế native của engine hoặc thực hiện trong cửa sổ bảo trì phù hợp.

## 6. ATTACH: gắn bảng staging thành partition

### 6.1. Khi nào dùng ATTACH?

ATTACH hữu ích khi dữ liệu được nạp và kiểm tra trong một bảng độc lập trước, sau đó mới đưa bảng đó vào cấu trúc partitioned. Ví dụ, đội dữ liệu nạp sự kiện của tháng tiếp theo vào staging table, xác minh dữ liệu, xây dựng index và cuối cùng gắn bảng làm partition.

Lợi ích là phần nạp và kiểm tra dữ liệu có thể diễn ra ngoài bảng đang phục vụ ứng dụng. Thời gian chuyển đổi cuối có thể ngắn hơn nếu engine chỉ cần xác minh metadata hoặc dùng constraint đã được chứng minh. Tuy nhiên, ATTACH không mặc nhiên miễn phí: engine có thể scan bảng để xác minh mọi hàng nằm trong bound.

### 6.2. Chuẩn bị schema staging

Bảng staging cần tương thích với bảng cha theo yêu cầu của engine:

- Số cột, thứ tự cột, kiểu dữ liệu, collation và generated column.
- Nullability, default và identity/generated behavior.
- CHECK constraint tương ứng với partition bound.
- Index cần thiết, bao gồm unique key và partitioned index nếu có.
- Compression, tablespace/filegroup, quyền, trigger và policy liên quan.
- Foreign key và dependency có thể cản trở attach hoặc làm thay đổi semantics.

Không chỉ so sánh tên cột. Một khác biệt về kiểu, collation, precision hoặc constraint có thể khiến ATTACH thất bại hoặc dẫn đến chuyển đổi dữ liệu ngoài dự kiến.

### 6.3. Nạp và xác minh staging trước khi gắn

Quy trình đề xuất:

1. Tạo bảng staging với schema tương thích.
2. Nạp dữ liệu bằng batch để kiểm soát transaction log, WAL và I/O.
3. Tạo index và constraint cần thiết trước bước attach.
4. Xác minh mọi hàng nằm trong partition bound, không có giá trị NULL hoặc giá trị ngoài phạm vi trái quy tắc.
5. Kiểm tra khóa duy nhất, duplicate, số hàng và các aggregate kiểm soát.
6. Cập nhật thống kê nếu engine không tự làm hoặc workload cần thống kê mới.
7. Thực hiện ATTACH trong một bước DDL ngắn, theo dõi lock wait và thời gian validation.

Nếu dữ liệu được nạp trong khi nguồn vẫn thay đổi, cần một snapshot hoặc cơ chế CDC để bảo đảm staging phản ánh đầy đủ trạng thái tại thời điểm attach. Chỉ so sánh row count trước và sau chưa đủ nếu hai tập dữ liệu có thể khác nhau nhưng cùng số hàng.

### 6.4. CHECK constraint có thể tránh scan xác minh

Một số hệ quản trị có thể bỏ qua scan xác minh bound nếu staging table đã có CHECK constraint được chứng minh bao phủ đúng phạm vi partition. Ví dụ minh họa PostgreSQL:

```sql
CREATE TABLE events_2026_08
(LIKE events INCLUDING DEFAULTS INCLUDING CONSTRAINTS);

ALTER TABLE events_2026_08
ADD CONSTRAINT events_2026_08_bound
CHECK (
    event_time >= TIMESTAMP '2026-08-01 00:00:00'
    AND event_time < TIMESTAMP '2026-09-01 00:00:00'
);

-- Nạp dữ liệu và xác minh trước khi attach.
ALTER TABLE events
ATTACH PARTITION events_2026_08
FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
```

Đây là ví dụ PostgreSQL cần điều chỉnh theo schema, kiểu `event_time`, timezone và phiên bản. Constraint phải thực sự chứng minh mọi hàng nằm trong bound; không thêm CHECK chỉ để né scan nếu chưa xác minh dữ liệu. Cách tạo index tương ứng và khóa khi attach cũng phụ thuộc phiên bản và cấu trúc bảng cha.

## 7. DETACH: tách partition nhưng giữ lại dữ liệu

### 7.1. DETACH khác DROP

DETACH loại partition khỏi cấu trúc bảng cha, nhưng thường để lại bảng con như một bảng độc lập. Dữ liệu vẫn tồn tại để archive, export, backup, truy vấn riêng hoặc xử lý tiếp. DROP partition loại bỏ cả partition và dữ liệu theo semantics của engine.

Ví dụ vận hành: sau khi dữ liệu đã quá thời hạn lưu trữ trực tuyến, đội vận hành detach partition tháng cũ, xác minh và chuyển nó sang tablespace lưu trữ, sau đó mới quyết định giữ hoặc xóa theo chính sách retention.

### 7.2. Những điều cần kiểm tra trước DETACH

- Có truy vấn, view, stored procedure hoặc ứng dụng tham chiếu trực tiếp tên partition không?
- Có foreign key, trigger, policy, quyền hoặc job bảo trì phụ thuộc bảng cha không?
- Có global index hoặc index trên bảng cha cần cập nhật không?
- Có giao dịch đang đọc/ghi partition hoặc transaction snapshot kéo dài không?
- Có replication/CDC subscriber cần tiếp tục nhận thay đổi không?
- Có backup/restore hoặc retention policy yêu cầu giữ bảng độc lập không?

Sau detach, ứng dụng truy vấn bảng cha sẽ không còn thấy dữ liệu trong partition đó. Nếu vẫn cần truy vấn lịch sử, phải có đường truy cập archive rõ ràng, chẳng hạn view hợp nhất, bảng lịch sử hoặc truy vấn nhiều nguồn.

### 7.3. DETACH CONCURRENTLY và thao tác online

Một số hệ quản trị cung cấp biến thể detach ít chặn hơn hoặc cho phép tách partition theo nhiều pha. PostgreSQL ở các phiên bản hỗ trợ có `DETACH PARTITION ... CONCURRENTLY`; SQL Server, Oracle và các engine khác có cơ chế maintenance riêng. Các biến thể này có điều kiện hạn chế, trạng thái trung gian và yêu cầu hoàn tất thao tác nếu bị gián đoạn.

Không suy ra rằng từ khóa `CONCURRENTLY` đồng nghĩa hoàn toàn không khóa. DDL vẫn cần khóa metadata hoặc các bước đồng bộ; một số dạng không được chạy trong transaction block; default partition, foreign key hoặc partitioned index có thể giới hạn khả năng dùng. Hãy kiểm tra tài liệu đúng phiên bản và thử trên môi trường có tải tương tự.

## 8. DROP: loại bỏ partition hết hạn

### 8.1. Vì sao DROP partition thường nhanh hơn DELETE hàng loạt?

Xóa từng hàng bằng `DELETE` có thể tạo log cho từng thay đổi, cập nhật index, phát sinh vacuum/cleanup và giữ khóa trên nhiều hàng hoặc trang. DROP partition có thể loại bỏ một đơn vị lưu trữ lớn bằng thao tác metadata hoặc thao tác cấp phát, nhờ đó giảm công việc so với xóa từng dòng.

Tuy nhiên, tốc độ và lượng log thực tế phụ thuộc engine, storage, index, foreign key, replication và chính sách ghi log. DROP vẫn có thể cần khóa DDL, cập nhật metadata, xử lý global index hoặc chờ transaction cũ.

### 8.2. Xác nhận retention trước khi DROP

Trước khi xóa:

1. Xác minh partition key và bound của partition cần xóa.
2. Xác nhận mốc retention theo timezone và chính sách pháp lý/nghiệp vụ.
3. Kiểm tra số hàng, khoảng thời gian min/max và nguồn dữ liệu.
4. Xác nhận backup, archive hoặc bản sao cần thiết đã hoàn tất và có thể khôi phục.
5. Kiểm tra không có ứng dụng hoặc báo cáo còn cần dữ liệu đó qua bảng cha.
6. Kiểm tra foreign key, global index, CDC, replication và job phụ thuộc.
7. Lập phương án phục hồi nếu chọn nhầm partition.

DROP thường không thể rollback dữ liệu một cách đơn giản sau khi thao tác đã commit hoặc DDL đã hoàn tất. Nếu còn nghi ngờ, DETACH rồi lưu giữ bảng độc lập trong thời gian xác minh có thể là bước an toàn hơn, nếu kiến trúc và chính sách cho phép.

### 8.3. DETACH rồi DROP sau thời gian chờ

Một chiến lược retention hai pha:

1. DETACH partition hết hạn khỏi bảng đang phục vụ ứng dụng.
2. Đổi tên hoặc chuyển bảng sang schema/tablespace archive.
3. Kiểm tra số hàng, checksum, quyền truy cập và khả năng truy vấn lịch sử.
4. Giữ lại trong thời gian chờ theo chính sách.
5. DROP bảng độc lập sau khi xác nhận không còn nhu cầu và backup đã đủ.

Cách này tạo cơ hội khôi phục nếu phát hiện thiếu dữ liệu hoặc ứng dụng còn phụ thuộc. Nó cũng cần quản lý dung lượng lưu trữ và tránh để bảng archive bị bỏ quên.

## 9. Khóa, giao dịch và ảnh hưởng đến workload

### 9.1. DDL có thể tạo lock queue

Một lệnh DDL có thể cần khóa mạnh trong thời gian ngắn để cập nhật metadata. Nếu có giao dịch dài đang giữ khóa tương thích không phù hợp, DDL phải chờ. Trong lúc đó, các giao dịch mới có thể xếp hàng phía sau lệnh DDL đang chờ, làm độ trễ tăng nhanh dù bản thân thao tác chưa thực sự bắt đầu.

Hãy theo dõi:

- Lock wait của DDL và giao dịch đang giữ khóa.
- Tuổi transaction và truy vấn chạy lâu.
- Số session bị block và độ dài hàng đợi.
- Deadlock, timeout và retry rate.
- Thời gian lấy khóa so với thời gian thực thi sau khi có khóa.

Nếu DDL phải chờ quá ngưỡng, hủy hoặc để timeout thay vì chờ vô hạn. Xác định transaction blocker, kết thúc hoặc để nó hoàn tất theo quy trình vận hành, rồi thử lại trong điều kiện phù hợp.

### 9.2. Transaction dài và snapshot

Giao dịch dài có thể giữ lock, snapshot hoặc phiên bản dữ liệu cũ, làm chậm cleanup và detach. Trong hệ thống MVCC, transaction snapshot lâu có thể ngăn vacuum/garbage collection thu hồi phiên bản cũ; thao tác partition có thể tạo thêm dữ liệu cần dọn.

Trước bảo trì, xem tuổi transaction, idle-in-transaction session, replication slot hoặc snapshot consumer. Không kết thúc session của ứng dụng một cách tùy tiện; phối hợp theo chính sách để tránh rollback công việc quan trọng hoặc làm lỗi request đang chạy.

### 9.3. DDL transaction semantics khác nhau

Một số hệ quản trị cho phép DDL nằm trong transaction và rollback được; một số lệnh hoặc engine tự commit; một số thao tác concurrent không được chạy trong transaction block; một số lệnh có trạng thái nhiều pha. Không giả định mọi thao tác ADD/SPLIT/ATTACH/DETACH/DROP có cùng khả năng rollback.

Hãy xác nhận semantics của đúng engine/version, lập kế hoạch xử lý lỗi giữa các pha và ghi rõ điểm không thể quay lại. Không gói một quy trình nhiều bước trong transaction lớn nếu điều đó làm lock kéo dài, log tăng hoặc lệnh không được phép chạy trong transaction.

## 10. Index, constraint và foreign key khi thay đổi partition

### 10.1. Local index và global index

Local index được tổ chức tương ứng theo từng partition; global index có thể bao phủ nhiều partition. Khi ADD hoặc ATTACH, cần bảo đảm partition mới có các index phù hợp. Khi DETACH hoặc DROP, global index có thể cần cập nhật, rebuild hoặc maintenance đặc biệt.

Local index thường giúp thao tác partition độc lập dễ quản lý hơn, nhưng truy vấn nhiều partition phải kết hợp kết quả từ nhiều index. Global index có thể hỗ trợ truy vấn toàn cục, nhưng việc detach/drop partition có thể tốn kém hơn vì index tham chiếu dữ liệu ở nhiều partition.

Không giả định engine tự tạo hoặc duy trì mọi index theo cùng một cách. Trước ATTACH, xác định index cần có, cách engine ghép index con vào partitioned index và thời điểm index trở nên usable. Sau thao tác, kiểm tra trạng thái index, uniqueness và execution plan.

### 10.2. Unique constraint và partition key

Một số hệ quản trị yêu cầu unique constraint hoặc primary key trên bảng partitioned phải bao gồm partition key để có thể bảo đảm tính duy nhất cục bộ giữa các partition. Một số engine có cách hỗ trợ global unique index khác. Điều kiện cụ thể phụ thuộc nền tảng.

Nếu một khóa duy nhất toàn bảng không bao gồm partition key, cần xác định engine bảo đảm uniqueness bằng cơ chế nào. Không được bỏ constraint chỉ để attach partition thành công nếu điều đó làm mất tính toàn vẹn dữ liệu.

### 10.3. Foreign key và quan hệ giữa partition

Foreign key có thể hạn chế detach/drop hoặc yêu cầu cập nhật tham chiếu. Cần kiểm tra cả chiều tham chiếu vào partition và chiều partition tham chiếu đến bảng khác. Nếu dữ liệu archive vẫn cần giữ quan hệ, có thể phải giữ bảng tham chiếu, chuyển quan hệ sang archive schema hoặc thay đổi cách truy cập có kiểm soát.

Tránh tắt constraint trong lúc bảo trì nếu không có kế hoạch kiểm tra lại toàn bộ dữ liệu trước khi bật. Việc bỏ qua xác minh có thể tạo orphan record khó phát hiện.

## 11. Replication, CDC, backup và hệ thống downstream

Thay đổi partition có thể tác động đến replica và hệ thống downstream theo cách khác nhau:

- Một số cơ chế replication truyền DDL hoặc metadata; cơ chế khác cần schema được áp dụng riêng trên replica.
- Di chuyển hàng khi split có thể tạo lượng log lớn và làm replica chậm theo.
- CDC hoặc logical decoding có thể phát sự kiện DDL, sự kiện hàng loạt hoặc yêu cầu cập nhật schema ở consumer.
- Backup vật lý và backup logic có thể xử lý partition/table detached khác nhau.
- ETL, warehouse, search index và báo cáo có thể tham chiếu tên partition hoặc giả định cấu trúc cũ.

Trước khi triển khai, xác nhận thứ tự cập nhật schema ở primary và replica, khả năng apply DDL, replication lag cho phép, slot/disk retention và cách consumer xử lý dữ liệu. Sau thao tác, kiểm tra replica đã có cấu trúc và trạng thái tương đương, consumer không bị dừng hoặc bỏ sót dữ liệu.

Không coi việc DDL hoàn tất trên primary là bằng chứng toàn hệ thống đã hoàn tất. Một thao tác partition chỉ được xem là ổn định khi replica, CDC, backup và downstream đã được xác minh theo yêu cầu.

## 12. Ví dụ SQL Server: SWITCH và SPLIT boundary

SQL Server cung cấp `ALTER TABLE ... SWITCH` để chuyển một partition hoặc bảng giữa các đối tượng tương thích bằng thao tác metadata trong những điều kiện cụ thể. Bảng nguồn/đích cần thỏa các yêu cầu về schema, index, constraint, partition alignment và các điều kiện khác. Đây không phải lệnh tổng quát có thể dùng giữa hai bảng bất kỳ.

Ví dụ khái niệm chuyển partition cũ sang bảng archive:

```sql
-- Cú pháp minh họa; cần chuẩn bị bảng đích tương thích hoàn toàn.
ALTER TABLE dbo.Events
SWITCH PARTITION 1 TO dbo.Events_Archive;
```

Trước khi chạy, xác minh bảng archive rỗng hoặc có trạng thái phù hợp, index/constraint tương thích và partition number đúng. SWITCH thường yêu cầu khóa schema/metadata trong thời gian thao tác; các điều kiện không phù hợp khiến lệnh thất bại. Không xem đây là cách chuyển dữ liệu online không có khóa.

Với partition function, `SPLIT RANGE` thêm ranh giới mới. Nếu split một range đang chứa nhiều dữ liệu, engine có thể phải di chuyển dữ liệu giữa các partition và tạo log đáng kể. Một kỹ thuật vận hành phổ biến là duy trì partition trống ở biên, sau đó split range trống để tránh di chuyển dữ liệu đang hoạt động. Cần xác minh trạng thái partition, filegroup và yêu cầu `NEXT USED` theo cấu hình thực tế.

## 13. Ví dụ PostgreSQL: attach bảng staging và detach partition

PostgreSQL declarative partitioning hỗ trợ tạo partition trực tiếp hoặc attach một bảng độc lập. Với bảng staging, CHECK constraint chứng minh bound có thể giúp tránh một lần scan xác minh toàn bộ bảng trong các trường hợp được hỗ trợ.

Quy trình khái niệm:

```sql
-- 1. Tạo bảng staging tương thích với bảng cha.
CREATE TABLE measurements_2026_08
(LIKE measurements INCLUDING DEFAULTS INCLUDING CONSTRAINTS);

-- 2. Ràng buộc dữ liệu nằm trong đúng khoảng partition.
ALTER TABLE measurements_2026_08
ADD CONSTRAINT measurements_2026_08_bound
CHECK (
    measured_at >= TIMESTAMP '2026-08-01 00:00:00'
    AND measured_at < TIMESTAMP '2026-09-01 00:00:00'
);

-- 3. Nạp, xác minh và chuẩn bị index trước bước này.

-- 4. Gắn partition vào bảng cha.
ALTER TABLE measurements
ATTACH PARTITION measurements_2026_08
FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
```

Khi cần loại partition khỏi bảng cha, có thể dùng DETACH theo cú pháp và mức đồng thời được phiên bản hỗ trợ:

```sql
ALTER TABLE measurements
DETACH PARTITION measurements_2026_01;
```

Một số phiên bản hỗ trợ `DETACH PARTITION ... CONCURRENTLY` với điều kiện và hạn chế riêng. Hãy kiểm tra phiên bản PostgreSQL, trạng thái partition, transaction block, default partition và foreign key trước khi dùng. Sau detach, bảng con vẫn tồn tại như bảng độc lập; ứng dụng truy vấn bảng cha sẽ không còn tự động đọc dữ liệu ở đó.

Các ví dụ này chỉ mô tả luồng thao tác. Cần kiểm tra tài liệu phiên bản đang chạy, quyền, index, trigger, constraint và lock level trước khi áp dụng trên production.

## 14. Quy trình triển khai bảo trì partition dưới tải

### Giai đoạn A — Khảo sát và lập kế hoạch

1. Xác định mục tiêu: tạo partition mới, split dữ liệu cũ, attach staging, detach để archive hay drop hết hạn.
2. Kiểm tra bound, partition key, default partition và số hàng của vùng bị tác động.
3. Đọc execution plan và workload để biết partition nào đang nóng, truy vấn nào bị ảnh hưởng.
4. Kiểm tra transaction dài, lock wait, index, constraint, foreign key và dependency.
5. Ước lượng I/O, CPU, log/WAL, temp space, storage headroom và replication capacity.
6. Xác nhận backup/restore, CDC và quy trình rollback.
7. Kiểm tra giới hạn online của đúng engine/version bằng thử nghiệm có tải tương tự.

### Giai đoạn B — Chuẩn bị ngoài thời điểm chuyển đổi

1. Tạo partition tương lai hoặc bảng staging.
2. Chuẩn hóa schema, CHECK constraint và index.
3. Nạp dữ liệu theo batch có giới hạn, tránh transaction khổng lồ.
4. Kiểm tra row count, min/max partition key, duplicate, constraint và checksum/aggregate.
5. Cập nhật thống kê phù hợp và xác nhận plan của các truy vấn chính.
6. Chuẩn bị script DDL, timeout, điều kiện dừng và người chịu trách nhiệm.

### Giai đoạn C — Chuyển đổi có kiểm soát

1. Chọn thời điểm tải thấp hoặc khoảng ít giao dịch trên partition mục tiêu.
2. Xác nhận không có transaction blocker bất thường.
3. Thực hiện một thao tác DDL tại một thời điểm; tránh chạy nhiều split/attach/drop cạnh tranh I/O.
4. Dùng lock timeout/statement timeout phù hợp nếu engine hỗ trợ.
5. Theo dõi thời gian lấy khóa, số session bị chặn, log/WAL, I/O, CPU và replication lag.
6. Nếu vượt ngưỡng đã đặt, dừng hoặc hủy theo semantics của engine; không tiếp tục chỉ vì thao tác đã bắt đầu.

### Giai đoạn D — Xác minh và hoàn tất

1. Đọc lại partition metadata và bound.
2. Xác nhận dữ liệu ở đúng partition; kiểm tra row count và aggregate kiểm soát.
3. Kiểm tra index usable, constraint valid, foreign key và quyền.
4. Chạy truy vấn đại diện và đọc execution plan để xác nhận partition pruning.
5. Kiểm tra latency, throughput, lock wait, I/O, log growth và replication lag.
6. Xác nhận CDC, backup và downstream đã đồng bộ.
7. Ghi lại thời điểm, thao tác, số hàng, thời gian khóa, kết quả và mọi sai lệch.

## 15. Giám sát và ngưỡng dừng

Thiết lập ngưỡng trước khi bắt đầu thay đổi. Ngưỡng cụ thể phải dựa trên SLO và năng lực hệ thống, không dùng một con số chung cho mọi môi trường.

| Nhóm theo dõi | Dấu hiệu cần chú ý | Hành động khi vượt ngưỡng |
|---|---|---|
| Locking | DDL chờ lâu, số session blocked tăng, lock queue kéo dài | Hủy/timeout DDL, xác định blocker, thử lại khi giao dịch ngắn đã hoàn tất |
| Latency | p95/p99 của truy vấn tăng bất thường | Dừng bước tiếp theo, xác định partition/index đang bị tác động |
| Throughput | Số giao dịch hoàn tất giảm | Giảm tốc độ batch hoặc hoãn thao tác nặng |
| CPU và I/O | CPU, read/write latency hoặc queue depth tăng cao | Giới hạn song song/batch, chờ tải hạ hoặc chuyển sang cửa sổ khác |
| Log/WAL | Dung lượng log tăng nhanh, nguy cơ đầy đĩa | Tạm dừng thao tác, kiểm tra checkpoint/backup/consumer theo engine |
| Replication/CDC | Lag tăng, slot giữ log, consumer không theo kịp | Dừng thay đổi tiếp theo, khôi phục năng lực apply và xác minh dữ liệu |
| Storage | Dung lượng trống giảm dưới mức dự phòng | Không bắt đầu split/rebuild mới; giải phóng hoặc mở rộng dung lượng theo quy trình |
| Correctness | Row count, bound, checksum hoặc constraint không khớp | Dừng rollout, giữ dữ liệu nguồn và chạy quy trình đối soát/khôi phục |

Không chỉ theo dõi trung bình. Một DDL chờ khóa vài giây có thể tạo đuôi latency dài cho nhiều request; vì vậy cần xem p95/p99, thời gian chặn và số session bị ảnh hưởng.

## 16. Kế hoạch rollback và xử lý lỗi

Rollback phụ thuộc loại thao tác:

- **ADD partition:** nếu chưa có dữ liệu hoặc chưa nhận ghi, có thể detach/drop partition mới theo quy trình phù hợp. Nếu đã có dữ liệu, phải xác định nơi chuyển dữ liệu trước khi loại bỏ.
- **ATTACH partition:** có thể detach lại nếu điều kiện engine cho phép, nhưng cần xử lý giao dịch đã ghi vào partition sau attach và các dependency phát sinh.
- **DETACH partition:** có thể attach lại nếu dữ liệu, bound, schema và index vẫn phù hợp. Trong thời gian detached, ứng dụng có thể đã ghi vào bảng khác; cần đối soát trước khi gắn lại.
- **SPLIT:** nếu đã di chuyển hàng, rollback có thể cần thao tác hợp nhất/chuyển dữ liệu ngược hoặc khôi phục backup; không giả định một lệnh ROLLBACK luôn đủ.
- **DROP partition:** sau khi dữ liệu đã bị xóa và DDL commit, thường phải khôi phục từ backup/archive hoặc bản sao khác. Đây là lý do cần kiểm tra retention và ưu tiên detach nếu còn bất định.

Trước khi chạy, hãy xác định điểm commit, khả năng transactional DDL, dữ liệu phát sinh trong thời gian chuyển đổi và cách xử lý request đang chạy. Một rollback đúng phải khôi phục cả cấu trúc, dữ liệu, index/constraint và đường truy cập của ứng dụng.

## 17. Những lỗi thường gặp

- **Đợi partition hết chỗ mới tạo:** DDL khẩn cấp đúng giờ cao điểm có thể chặn ghi hoặc đưa dữ liệu vào default partition.
- **Cho rằng ADD luôn chỉ thay metadata:** default partition hoặc validation có thể khiến engine scan/chuyển dữ liệu.
- **SPLIT partition đang nóng mà không ước lượng log:** có thể gây I/O bão hòa, log đầy và replica lag.
- **ATTACH staging không có bound constraint:** engine có thể phải scan toàn bảng để xác minh hoặc thao tác thất bại.
- **Chỉ kiểm tra row count:** hai tập dữ liệu khác nhau vẫn có thể cùng số hàng; cần kiểm tra key/range và checksum/aggregate phù hợp.
- **Bỏ qua index và unique constraint:** partition được gắn thành công nhưng index thiếu, không usable hoặc uniqueness không còn được bảo đảm.
- **Nhầm DETACH với DROP:** detach giữ bảng độc lập; drop loại bỏ dữ liệu.
- **Giả định CONCURRENTLY nghĩa là không khóa:** thao tác online vẫn có các pha cần lock và điều kiện hạn chế.
- **Chạy nhiều DDL nặng đồng thời:** cạnh tranh I/O, log và metadata làm tăng rủi ro cho toàn hệ thống.
- **Không tính giao dịch dài:** transaction cũ có thể chặn DDL hoặc ngăn cleanup.
- **Quên replica và CDC:** primary hoàn tất nhưng downstream vẫn thiếu schema hoặc dữ liệu.
- **Không có phương án khôi phục:** DROP hoặc split có di chuyển dữ liệu có thể khó đảo ngược sau commit.
- **Không kiểm tra partition pruning:** cấu trúc mới đúng nhưng truy vấn vẫn quét nhiều partition do predicate hoặc thống kê không phù hợp.

## 18. Checklist vận hành

### Trước thao tác

- [ ] Đã xác nhận đúng bảng, partition, bound và partition key.
- [ ] Đã xác định rõ thao tác ADD, SPLIT, ATTACH, DETACH hay DROP.
- [ ] Đã kiểm tra default partition, overlap và dữ liệu ngoài phạm vi.
- [ ] Đã đánh giá schema, index, constraint, foreign key và dependency.
- [ ] Đã kiểm tra transaction dài, lock wait và tải hiện tại.
- [ ] Đã ước lượng dung lượng, log/WAL, I/O, CPU và replication capacity.
- [ ] Đã xác nhận backup, CDC, downstream và kế hoạch rollback.
- [ ] Đã thử quy trình trên đúng phiên bản engine với dữ liệu/tải tương tự.

### Trong thao tác

- [ ] Thực hiện từng DDL theo thứ tự đã duyệt.
- [ ] Theo dõi lock wait, blocked sessions, latency và throughput.
- [ ] Theo dõi CPU, I/O, log/WAL, storage và replication lag.
- [ ] Dừng khi vượt ngưỡng hoặc phát hiện sai lệch dữ liệu.

### Sau thao tác

- [ ] Partition metadata và bound đúng.
- [ ] Row count, key range và kiểm tra dữ liệu đạt yêu cầu.
- [ ] Index usable; constraint và foreign key hợp lệ.
- [ ] Truy vấn đại diện có partition pruning đúng.
- [ ] Latency, throughput, I/O và replication trở lại mức ổn định.
- [ ] CDC, backup và downstream đã đồng bộ.
- [ ] Đã ghi lại kết quả và thời điểm hoàn tất.

## 19. Bài tập tự kiểm tra

**Bài 1.** Một bảng RANGE partition theo tháng sắp bước sang tháng mới. Vì sao nên tạo partition mới trước khi dữ liệu tháng mới đến?

*Gợi ý:* Tránh DDL khẩn cấp dưới tải cao, giảm nguy cơ ghi vào default partition hoặc bị từ chối, và cho phép chuẩn bị index/constraint trước.

**Bài 2.** Một partition lớn cần được chia làm hai. Những yếu tố nào quyết định SPLIT có thể gây ảnh hưởng lớn đến workload?

*Gợi ý:* Số hàng, vị trí boundary, dữ liệu phải di chuyển, index local/global, transaction log/WAL, I/O, khóa, dung lượng tạm và replication lag.

**Bài 3.** Một bảng staging có CHECK constraint đúng bound trước khi ATTACH. Lợi ích là gì và cần xác minh điều gì?

*Gợi ý:* Một số engine có thể dùng constraint để tránh scan xác minh bound. Phải xác nhận constraint thực sự đúng, dữ liệu không vi phạm, schema/index tương thích và hành vi của phiên bản.

**Bài 4.** Vì sao DETACH thường phù hợp hơn DROP khi đội vận hành chưa chắc dữ liệu đã hết nhu cầu?

*Gợi ý:* DETACH thường giữ dữ liệu trong bảng độc lập để archive, kiểm tra hoặc attach lại; DROP xóa dữ liệu và có thể cần restore từ backup nếu thao tác nhầm.

**Bài 5.** DDL đang chờ khóa và số request bị block tăng nhanh. Nên làm gì?

*Gợi ý:* Áp dụng timeout/ngưỡng đã đặt, hủy DDL nếu vượt ngưỡng, xác định transaction blocker và thử lại khi điều kiện phù hợp. Không để DDL chờ vô hạn tạo lock queue.

**Bài 6.** Sau ATTACH, truy vấn theo tháng vẫn quét nhiều partition. Cần kiểm tra gì?

*Gợi ý:* Bound, kiểu và timezone của partition key, predicate có sargable không, plan/pruning, thống kê và cấu trúc partition con.

## 20. Ghi nhớ khi tối ưu

Bảo trì partition dưới tải là bài toán kết hợp giữa metadata, dữ liệu, khóa, index, transaction log và workload. ADD partition tương lai sớm giúp tránh thao tác khẩn cấp; SPLIT cần đánh giá khả năng di chuyển hàng và áp lực log; ATTACH hiệu quả hơn khi staging đã được chuẩn bị và chứng minh đúng bound; DETACH giữ dữ liệu để xử lý tiếp; DROP chỉ nên thực hiện sau khi xác nhận retention và khả năng khôi phục.

Trước mỗi thay đổi, hãy xác định chính xác hành vi của engine/version, thời gian khóa, lượng I/O và tác động đến replica/CDC. Trong lúc thực hiện, theo dõi lock queue, latency, throughput, log/WAL và replication lag với ngưỡng dừng rõ ràng. Sau thao tác, xác minh bound, dữ liệu, index, constraint và partition pruning. Chỉ coi bảo trì hoàn tất khi cả tính toàn vẹn dữ liệu lẫn hiệu năng workload đã được kiểm chứng.
