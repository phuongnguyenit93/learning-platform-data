# Mục tiêu phân vùng: giảm phạm vi truy cập và đơn giản hóa vòng đời dữ liệu

Khi một bảng tăng lên hàng trăm triệu hoặc hàng tỷ dòng, mỗi truy vấn và thao tác bảo trì có thể phải làm việc với một khối lượng dữ liệu rất lớn. Phân vùng dữ liệu (table partitioning) chia một bảng logic thành nhiều phần vật lý theo một quy tắc, chẳng hạn khoảng thời gian, danh sách giá trị hoặc hàm băm. Nếu truy vấn cung cấp điều kiện phù hợp với quy tắc đó, hệ quản trị có thể loại bỏ các phân vùng không liên quan trước khi đọc dữ liệu. Phân vùng cũng giúp quản lý vòng đời dữ liệu: dữ liệu cũ có thể được tách, lưu trữ hoặc loại bỏ theo từng phần.

Trong phạm vi **DATABASE_PERFORMANCE**, việc tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Phân vùng có thể giảm phạm vi truy cập, hỗ trợ bảo trì và kiểm soát tăng trưởng, nhưng chỉ mang lại lợi ích khi khóa phân vùng, cách chia và truy vấn phù hợp với workload. Chia một bảng thành nhiều phần tự nó không bảo đảm truy vấn nhanh hơn.

Bài học này trình bày mục tiêu của phân vùng, cơ chế partition pruning, cách chọn khóa và kích thước phân vùng, các chiến lược RANGE/LIST/HASH, vai trò của chỉ mục bên trong từng phân vùng, cách quản lý vòng đời dữ liệu và phương pháp kiểm chứng hiệu năng trên dữ liệu lớn.

## 1. Phân vùng dữ liệu là gì?

Phân vùng chia một bảng logic thành nhiều bảng hoặc đơn vị lưu trữ con theo một quy tắc xác định. Ứng dụng vẫn truy vấn bảng cha như một đối tượng logic; hệ quản trị định tuyến thao tác đến các phân vùng phù hợp.

Ví dụ, bảng events lưu sự kiện theo thời gian. Thay vì giữ toàn bộ dữ liệu trong một bảng vật lý, có thể chia thành các phân vùng theo tháng:

~~~text
Bảng logic: events
    |
    +-- events_2026_01
    +-- events_2026_02
    +-- events_2026_03
    +-- events_2026_04
    +-- ...
~~~

Ứng dụng vẫn có thể viết:

~~~sql
SELECT event_id, occurred_at, event_type
FROM events
WHERE occurred_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-05-01 00:00:00+00';
~~~

Nếu bảng được partition theo occurred_at và điều kiện truy vấn tương thích, hệ quản trị chỉ cần truy cập phân vùng tháng 4. Các phân vùng tháng 1, 2, 3 và những tháng khác có thể bị loại bỏ trước khi đọc dữ liệu.

### Bảng cha và phân vùng con

Các hệ quản trị có mô hình triển khai khác nhau, nhưng thường có các khái niệm:

- **Partitioned table / bảng cha:** đối tượng logic mà ứng dụng truy vấn.
- **Partition / phân vùng con:** phần dữ liệu thực tế chứa một tập dòng theo quy tắc phân vùng.
- **Partition key / khóa phân vùng:** cột hoặc biểu thức xác định dòng thuộc phân vùng nào.
- **Partition bound / ranh giới phân vùng:** điều kiện xác định miền giá trị mà phân vùng nhận.
- **Partition pruning:** quá trình loại bỏ các phân vùng không thể chứa dòng phù hợp.
- **Partition maintenance:** thao tác tạo, gắn, tách, lưu trữ hoặc loại bỏ phân vùng.

Không phải hệ quản trị nào cũng triển khai bảng cha và phân vùng con giống nhau. Cần đọc tài liệu theo phiên bản và engine đang sử dụng.

## 2. Hai mục tiêu chính: giảm phạm vi truy cập và quản lý vòng đời

Phân vùng thường được triển khai vì hai nhóm mục tiêu. Chúng có liên quan nhưng cần đánh giá riêng.

### Giảm phạm vi truy cập

Nếu truy vấn lọc theo khóa phân vùng, hệ quản trị có thể bỏ qua những phần dữ liệu chắc chắn không liên quan. Ví dụ truy vấn lịch sử sự kiện trong một tuần có thể chỉ đọc một hoặc hai phân vùng ngày/tuần thay vì xét toàn bộ bảng nhiều năm.

Lợi ích có thể gồm:

- Giảm số trang dữ liệu phải đọc.
- Giảm số chỉ mục hoặc phạm vi chỉ mục cần truy cập.
- Giảm lượng dữ liệu phải lọc sau khi đọc.
- Hỗ trợ xử lý song song theo phân vùng trong một số hệ quản trị.
- Giảm phạm vi công việc cho một số thao tác bảo trì.

Partition pruning không thay thế chỉ mục. Sau khi chọn đúng phân vùng, hệ quản trị vẫn cần tìm dòng bên trong phân vùng đó bằng sequential scan, index scan hoặc access path khác.

### Đơn giản hóa vòng đời dữ liệu

Nhiều hệ thống có chính sách lưu trữ theo thời gian: dữ liệu nóng giữ trong vài tháng, dữ liệu cũ chuyển sang vùng lưu trữ rẻ hơn, dữ liệu quá hạn được xóa theo chính sách.

Nếu dữ liệu được chia theo tháng, nhóm vận hành có thể xử lý một tháng như một đơn vị:

- Tạo trước phân vùng cho tháng sắp tới.
- Nạp dữ liệu theo batch vào phân vùng tương ứng.
- Tách phân vùng cũ khỏi bảng đang hoạt động.
- Xuất hoặc lưu trữ phân vùng đã tách.
- Xóa phân vùng hết hạn sau khi hoàn tất các bước lưu trữ và kiểm soát.

Thao tác trên một phân vùng có thể hiệu quả hơn DELETE hàng triệu dòng trong bảng đang hoạt động. Tuy nhiên, việc tách/xóa vẫn có thể chịu ảnh hưởng của khóa DDL, phụ thuộc khóa ngoại, replication, backup và quy trình vận hành.

## 3. Partition pruning hoạt động như thế nào?

Partition pruning là cơ chế quan trọng nhất giúp phân vùng giảm phạm vi truy cập. Optimizer hoặc executor xác định những phân vùng có thể chứa dòng thỏa điều kiện và loại bỏ các phân vùng còn lại.

Giả sử bảng events được chia theo tháng:

| Phân vùng | Miền occurred_at |
|---|---|
| events_2026_01 | Từ 01/01 đến trước 01/02 |
| events_2026_02 | Từ 01/02 đến trước 01/03 |
| events_2026_03 | Từ 01/03 đến trước 01/04 |
| events_2026_04 | Từ 01/04 đến trước 01/05 |
| events_2026_05 | Từ 01/05 đến trước 01/06 |

Truy vấn:

~~~sql
SELECT COUNT(*)
FROM events
WHERE occurred_at >= TIMESTAMPTZ '2026-04-10 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-04-15 00:00:00+00';
~~~

chỉ giao với ranh giới của events_2026_04. Các phân vùng khác có thể được loại bỏ.

### Điều kiện truy vấn phải thể hiện khóa phân vùng

Để pruning có hiệu quả, điều kiện thường cần ràng buộc trực tiếp khóa phân vùng hoặc biểu thức tương thích với cách partition. Ví dụ:

~~~sql
WHERE occurred_at >= :from_time
  AND occurred_at < :to_time
~~~

Cách viết khoảng nửa mở giúp tránh nhầm lẫn ở ranh giới thời gian. Nó cũng thường dễ tận dụng index và partition pruning hơn việc áp dụng hàm lên cột:

~~~sql
WHERE DATE(occurred_at) = DATE '2026-04-12'
~~~

Một biểu thức có hàm không nhất thiết luôn ngăn pruning trong mọi engine, nhưng khả năng nhận diện phụ thuộc hệ quản trị, biểu thức partition key và cách viết điều kiện. Nếu có thể, hãy viết điều kiện theo miền giá trị của cột gốc.

### Pruning lúc lập kế hoạch và lúc thực thi

Tùy hệ quản trị, pruning có thể diễn ra khi tạo kế hoạch hoặc khi thực thi truy vấn. Với câu lệnh dùng tham số, giá trị tham số có thể chỉ được biết lúc chạy. Một số engine hỗ trợ execution-time pruning để loại phân vùng sau khi tham số được truyền vào.

Vì vậy, plan được xem trước khi bind tham số có thể hiển thị nhiều phân vùng hơn số phân vùng thực sự được truy cập khi chạy. Hãy xem actual execution plan hoặc thống kê runtime nếu hệ quản trị cung cấp.

### Không có pruning thì sao?

Nếu truy vấn không lọc theo khóa phân vùng, hệ quản trị có thể phải xét nhiều hoặc tất cả phân vùng. Ví dụ:

~~~sql
SELECT *
FROM events
WHERE event_type = 'LOGIN';
~~~

Nếu events được partition theo occurred_at, điều kiện event_type không giúp loại bỏ phân vùng thời gian. Truy vấn có thể phải truy cập mọi phân vùng đang tồn tại, trừ khi có chiến lược pruning khác dựa trên ràng buộc bổ sung.

Đây là lý do cần chọn khóa phân vùng theo các truy vấn quan trọng, thay vì chỉ chọn cột có vẻ thuận tiện cho việc chia dữ liệu.

## 4. Chọn partition key theo workload và vòng đời

Khóa phân vùng là quyết định có ảnh hưởng lâu dài. Một khóa tốt thường phục vụ được cả điều kiện lọc phổ biến và cách tổ chức vòng đời dữ liệu.

Hãy đánh giá các câu hỏi:

1. Truy vấn quan trọng thường lọc theo cột nào?
2. Dữ liệu được thêm theo thời gian, tenant, khu vực hay một loại khóa khác?
3. Chính sách lưu trữ và xóa dữ liệu dựa trên thuộc tính nào?
4. Phân bố giá trị có đồng đều hay bị lệch?
5. Các truy vấn có thường truy cập một phân vùng hay nhiều phân vùng?
6. Có cần join hoặc aggregate theo khóa phân vùng không?
7. Khóa có ổn định trong suốt vòng đời bản ghi không?
8. Các ràng buộc unique và khóa ngoại có tương thích với mô hình phân vùng không?

### Ví dụ khóa thời gian

Bảng log thường có occurred_at hoặc created_at. Chia theo thời gian có lợi khi:

- Truy vấn chủ yếu tìm theo khoảng ngày/giờ.
- Dữ liệu mới được ghi liên tục.
- Dữ liệu cũ hết hạn theo chính sách lưu trữ.
- Có thể tạo phân vùng mới theo lịch.

### Ví dụ khóa tenant

Bảng có dữ liệu nhiều khách hàng có thể được chia theo tenant_id nếu workload thường truy cập từng tenant và phân bố tenant không quá lệch. Tuy nhiên, nếu có một tenant rất lớn, phân vùng theo LIST từng tenant có thể tạo một phân vùng nóng hoặc số phân vùng quá nhiều.

Một phương án khác là HASH theo tenant_id để phân tán tenant vào số lượng phân vùng cố định. Nhưng hash partitioning không thuận tiện cho vòng đời theo thời gian của từng tenant; cần cân nhắc cách kết hợp hoặc thiết kế khác.

### Tránh chọn khóa chỉ vì cardinality cao

Một cột có hàng triệu giá trị khác nhau không tự động là partition key tốt. Chia theo customer_id hoặc order_id có thể tạo quá nhiều phân vùng nhỏ, làm tăng chi phí catalog, lập kế hoạch và bảo trì. Khóa phân vùng cần phù hợp với cách truy cập và quản lý dữ liệu, không chỉ với số lượng giá trị khác nhau.

## 5. Các chiến lược phân vùng phổ biến

Các hệ quản trị thường hỗ trợ một hoặc nhiều chiến lược sau.

### RANGE partitioning

RANGE chia dữ liệu theo các khoảng không chồng lấn, thường dùng cho thời gian, số thứ tự hoặc giá trị có thứ tự.

Ví dụ:

- Một phân vùng mỗi ngày.
- Một phân vùng mỗi tháng.
- Một phân vùng mỗi năm.
- Một phân vùng cho mỗi khoảng ID.

Ưu điểm:

- Truy vấn theo khoảng có thể loại bỏ phần lớn phân vùng.
- Dễ xác định dữ liệu cũ cần lưu trữ hoặc xóa.
- Dễ tạo trước phân vùng tương lai theo lịch.

Rủi ro:

- Nếu dữ liệu mới luôn rơi vào phân vùng mới nhất, phân vùng đó có thể trở thành điểm nóng ghi.
- Nạp dữ liệu trễ hoặc backfill có thể ghi vào phân vùng cũ.
- Thiếu phân vùng cho khoảng giá trị mới có thể làm INSERT thất bại hoặc đi vào default partition nếu có.
- Chọn khoảng quá nhỏ làm số phân vùng tăng nhanh.

### LIST partitioning

LIST chia dữ liệu theo một tập giá trị cụ thể, ví dụ region, category hoặc tenant group.

Ưu điểm:

- Phù hợp khi miền giá trị nhỏ, rõ ràng.
- Có thể cô lập dữ liệu theo nhóm nghiệp vụ.
- Truy vấn lọc đúng giá trị có thể chỉ truy cập phân vùng tương ứng.

Rủi ro:

- Giá trị mới cần có quy tắc tiếp nhận.
- Một số giá trị phổ biến có thể tạo phân vùng rất lớn.
- Số lượng tenant hoặc category tăng không kiểm soát có thể khiến việc quản lý phân vùng phức tạp.

### HASH partitioning

HASH áp dụng hàm băm lên khóa để phân phối dòng vào một số lượng phân vùng định trước.

Ưu điểm:

- Phân phối dữ liệu tương đối đều nếu hash key và phân bố đầu vào phù hợp.
- Tránh một phân vùng RANGE mới nhất nhận toàn bộ ghi.
- Hữu ích khi truy vấn thường lọc theo hash key và hệ quản trị có thể xác định phân vùng tương ứng.

Rủi ro:

- Không tự nhiên hỗ trợ xóa dữ liệu cũ theo thời gian.
- Truy vấn không có điều kiện trên hash key có thể phải truy cập tất cả phân vùng.
- Thay đổi số phân vùng có thể yêu cầu tái phân phối dữ liệu tùy hệ quản trị.

### Phân vùng kết hợp (composite hoặc subpartitioning)

Một số hệ quản trị cho phép chia theo nhiều cấp, ví dụ RANGE theo tháng rồi HASH theo tenant trong mỗi tháng.

~~~text
events
  |
  +-- RANGE: tháng 2026-04
  |      |
  |      +-- HASH bucket 0
  |      +-- HASH bucket 1
  |      +-- HASH bucket 2
  |
  +-- RANGE: tháng 2026-05
         |
         +-- HASH bucket 0
         +-- HASH bucket 1
         +-- HASH bucket 2
~~~

Mô hình này có thể kết hợp pruning theo thời gian và phân tán dữ liệu theo tenant. Đổi lại, số phân vùng con tăng theo tích số của các cấp. Cần tính tổng số đối tượng, index, thao tác DDL và chi phí lập kế hoạch trước khi áp dụng.

## 6. Chọn độ lớn và số lượng phân vùng

Độ hạt (partition granularity) quyết định mỗi phân vùng chứa bao nhiêu dữ liệu và tổng số phân vùng cần quản lý.

Ví dụ với dữ liệu theo thời gian:

- Phân vùng năm: ít phân vùng nhưng truy vấn một ngày có thể phải đọc nhiều dữ liệu trong một phân vùng.
- Phân vùng tháng: cân bằng giữa phạm vi truy cập, số phân vùng và thao tác vòng đời.
- Phân vùng ngày: pruning chi tiết hơn nhưng số phân vùng tăng nhanh.
- Phân vùng giờ: chỉ phù hợp khi workload và quy mô thực sự cần, vì số lượng phân vùng có thể rất lớn.

### Phân vùng quá lớn

Nếu mỗi phân vùng chứa quá nhiều dữ liệu:

- Truy vấn theo khoảng nhỏ vẫn phải làm việc trên một phân vùng lớn.
- Index của phân vùng có thể lớn và tốn cache.
- Vacuum, analyze, backup hoặc rebuild index trên phân vùng có thể mất nhiều thời gian.
- Tách hoặc di chuyển dữ liệu cũ vẫn phải xử lý khối lượng lớn.

### Phân vùng quá nhỏ

Nếu tạo quá nhiều phân vùng nhỏ:

- Optimizer phải quản lý và lập kế hoạch với nhiều đối tượng hơn.
- Catalog metadata và cache metadata tăng.
- Mỗi phân vùng có thể có index nhỏ nhưng tổng số index lớn.
- DDL, backup, monitoring và quyền truy cập phức tạp hơn.
- Nhiều truy vấn có thể phải mở hoặc xét rất nhiều phân vùng.

### Chọn granularity bằng số liệu

Hãy xem:

- Tốc độ tăng dòng mỗi ngày/tuần/tháng.
- Khoảng thời gian truy vấn thường dùng.
- Thời gian lưu trữ và lịch xóa.
- Kích thước heap và index mục tiêu cho mỗi phân vùng.
- Khả năng bảo trì trong cửa sổ vận hành.
- Số lượng phân vùng tối đa có thể quản lý ổn định trên phiên bản hiện tại.

Không có một ngưỡng số phân vùng đúng cho mọi hệ quản trị. Cần benchmark với số lượng phân vùng dự kiến và kiểu truy vấn thực tế.

## 7. Ví dụ RANGE partitioning trong PostgreSQL

Giả sử hệ thống lưu sự kiện theo occurred_at. Có thể tạo bảng cha:

~~~sql
CREATE TABLE events (
    event_id     bigint GENERATED BY DEFAULT AS IDENTITY,
    occurred_at  timestamptz NOT NULL,
    tenant_id    bigint NOT NULL,
    event_type   text NOT NULL,
    payload      jsonb,
    PRIMARY KEY (occurred_at, event_id)
) PARTITION BY RANGE (occurred_at);
~~~

PostgreSQL yêu cầu unique constraint hoặc primary key trên partitioned table phải bao gồm tất cả cột partition key để có thể bảo đảm uniqueness trên toàn bộ các phân vùng theo cơ chế chỉ mục của bảng phân vùng. Vì vậy ví dụ dùng khóa chính ghép (occurred_at, event_id). Nếu nghiệp vụ cần event_id duy nhất toàn cục, phải thiết kế và bảo đảm tính duy nhất bằng cơ chế phù hợp khác; không giả định primary key chỉ trên event_id có thể được tạo trên partitioned table RANGE theo occurred_at.

Tạo phân vùng tháng 4 và tháng 5:

~~~sql
CREATE TABLE events_2026_04
PARTITION OF events
FOR VALUES FROM ('2026-04-01 00:00:00+00')
             TO ('2026-05-01 00:00:00+00');

CREATE TABLE events_2026_05
PARTITION OF events
FOR VALUES FROM ('2026-05-01 00:00:00+00')
             TO ('2026-06-01 00:00:00+00');
~~~

RANGE dùng cận dưới bao gồm và cận trên không bao gồm. Vì vậy một dòng có occurred_at đúng 2026-05-01 sẽ thuộc phân vùng tháng 5, không thuộc tháng 4.

### Tạo index trên bảng phân vùng

Có thể tạo index trên bảng cha:

~~~sql
CREATE INDEX idx_events_tenant_time
ON events (tenant_id, occurred_at DESC);
~~~

Trong PostgreSQL, lệnh trên tạo partitioned index và các index tương ứng trên các phân vùng hiện có. Phân vùng mới tạo trực tiếp bằng PARTITION OF sẽ nhận index tương ứng theo cấu trúc của bảng cha; khi gắn một bảng đã tồn tại bằng ATTACH PARTITION, cần bảo đảm index tương ứng được tạo hoặc gắn theo yêu cầu của phiên bản.

Index vẫn phải phù hợp với workload. Nếu truy vấn chỉ lọc theo thời gian, partition pruning có thể đã giảm phạm vi đáng kể; index trên tenant_id có thể cần thiết cho truy vấn tenant trong từng phân vùng nhưng không phải luôn cần thiết.

### Truy vấn có thể prune phân vùng

~~~sql
SELECT event_id, occurred_at, event_type
FROM events
WHERE occurred_at >= TIMESTAMPTZ '2026-04-10 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-04-15 00:00:00+00'
  AND tenant_id = 9001;
~~~

Điều kiện thời gian chọn phân vùng tháng 4. Trong phân vùng đó, index tenant/time hoặc một access path khác tiếp tục tìm dòng phù hợp.

## 8. Partition pruning không thay thế index trong phân vùng

Phân vùng trả lời câu hỏi “cần xem phần dữ liệu nào?”. Index trả lời câu hỏi “tìm dòng nào trong phần dữ liệu đó?”.

Giả sử bảng có 5 năm dữ liệu và chia theo tháng. Truy vấn một ngày chỉ chọn một phân vùng. Nếu phân vùng đó vẫn có 100 triệu dòng, việc đọc toàn bộ phân vùng có thể vẫn đắt. Index trên tenant_id, occurred_at hoặc event_type có thể giúp thu hẹp phạm vi bên trong phân vùng.

Ngược lại, nếu truy vấn cần 70% dòng trong phân vùng, sequential scan có thể rẻ hơn index scan vì index access phải truy cập nhiều trang heap rải rác.

### Index trên bảng cha và index của phân vùng

Cách quản lý index phụ thuộc hệ quản trị:

- Một số engine tạo index tương ứng trên từng phân vùng khi khai báo index ở bảng cha.
- Một số engine phân biệt local index và global index.
- Global index có thể hỗ trợ tìm kiếm xuyên phân vùng nhưng có thể làm thao tác detach/drop partition phức tạp hơn.
- Local index gắn với từng phân vùng có thể dễ bảo trì theo vòng đời phân vùng, nhưng truy vấn cần nhiều phân vùng phải kết hợp kết quả từ nhiều index.

PostgreSQL sử dụng các index gắn với từng partition; không có một global index B-tree duy nhất trên toàn bộ các partition theo cách tương tự một số hệ quản trị khác. Khi thiết kế, hãy hiểu đúng khả năng của engine đang dùng.

## 9. Phân vùng và khóa duy nhất, khóa ngoại

Phân vùng ảnh hưởng đến cách bảo đảm tính toàn vẹn dữ liệu.

### Unique và primary key

Với PostgreSQL, unique constraint hoặc primary key trên bảng partitioned phải chứa toàn bộ cột partition key. Nếu bảng partition theo occurred_at, unique index chỉ trên event_id không thể bảo đảm event_id không trùng giữa các phân vùng bằng một index toàn cục.

Các lựa chọn thiết kế có thể gồm:

- Khóa chính ghép có chứa partition key.
- Dùng ID được cấp phát từ sequence hoặc generator để giảm xác suất trùng, đồng thời hiểu rằng sequence tự nó không phải unique constraint.
- Duy trì bảng tra cứu khóa toàn cục nếu nghiệp vụ thực sự cần kiểm tra uniqueness không phụ thuộc partition key.
- Chọn partition key phù hợp với mô hình khóa và ràng buộc.

Không bỏ ràng buộc duy nhất chỉ để đơn giản hóa partitioning. Phải bảo đảm tính toàn vẹn theo yêu cầu nghiệp vụ.

### Foreign key

Khả năng tham chiếu và được tham chiếu bởi partitioned table thay đổi theo hệ quản trị và phiên bản. Cần kiểm tra hỗ trợ FK, index ở phía referencing, hành vi khi detach/drop partition và các ràng buộc phụ thuộc.

Một partition không thể được loại bỏ an toàn nếu còn quan hệ tham chiếu hoặc dữ liệu cần giữ theo chính sách. Lập kế hoạch retention phải bao gồm cả dữ liệu liên quan.

## 10. Quản lý vòng đời phân vùng theo thời gian

Với bảng sự kiện, log hoặc giao dịch lịch sử, một quy trình vòng đời thường có các giai đoạn:

1. Tạo phân vùng tương lai trước khi dữ liệu đến.
2. Nạp dữ liệu vào phân vùng đang hoạt động.
3. Theo dõi kích thước, index, thống kê và mức tăng trưởng.
4. Chuyển phân vùng cũ sang trạng thái chỉ đọc hoặc vùng lưu trữ nếu cần.
5. Tách phân vùng hết hạn khỏi bảng chính.
6. Lưu trữ, xác minh backup và xử lý phụ thuộc.
7. Xóa dữ liệu khi hết thời hạn lưu trữ được phê duyệt.

### Tạo trước phân vùng

Không nên chờ đến khi INSERT đầu tiên của tháng mới thất bại mới tạo phân vùng. Hãy lập lịch tạo phân vùng trước một khoảng thời gian đủ để xử lý lỗi DDL và kiểm tra.

Ví dụ tạo phân vùng tháng 6:

~~~sql
CREATE TABLE events_2026_06
PARTITION OF events
FOR VALUES FROM ('2026-06-01 00:00:00+00')
             TO ('2026-07-01 00:00:00+00');
~~~

Quy trình tự động cần kiểm tra phân vùng đã tồn tại trước khi tạo, tránh tạo trùng khi job chạy lại. Cần cảnh báo nếu không có phân vùng tương lai.

### Default partition

Một số hệ quản trị cho phép phân vùng mặc định nhận các giá trị chưa khớp phân vùng cụ thể. Default partition giúp tránh INSERT thất bại khi có giá trị ngoài dự kiến, nhưng có thể che giấu việc thiếu phân vùng hoặc lỗi dữ liệu.

Nếu dùng default partition, cần giám sát số dòng trong đó. Khi tạo phân vùng mới có ranh giới bao phủ các dòng đang nằm trong default partition, có thể phải di chuyển các dòng đó trước; hệ quản trị có thể yêu cầu kiểm tra constraint và khóa phù hợp.

Không dùng default partition như cách thay thế cho quy trình tạo phân vùng đúng lịch.

### Tách và lưu trữ phân vùng cũ trong PostgreSQL

Có thể tách phân vùng cũ khỏi bảng cha:

~~~sql
ALTER TABLE events
DETACH PARTITION events_2025_01;
~~~

Sau khi tách, bảng events_2025_01 trở thành bảng độc lập. Nhóm vận hành có thể xuất dữ liệu, chuyển sang tablespace hoặc hệ lưu trữ khác theo quy trình, xác minh bản lưu trữ rồi mới xóa bảng.

Cú pháp và mức khóa của DETACH PARTITION có thể khác theo phiên bản; PostgreSQL có các biến thể detach đồng thời ở các phiên bản hỗ trợ. Cần xem tài liệu phiên bản và kiểm tra các ràng buộc, index, FK, trigger, replication và backup trước khi chạy trên production.

Tách phân vùng rồi xóa thường giảm lượng công việc so với DELETE từng dòng, nhưng không có nghĩa thao tác hoàn toàn không khóa hoặc không có rủi ro vận hành.

## 11. Nạp dữ liệu và backfill

Partitioning thường đi kèm dữ liệu được nạp liên tục hoặc theo batch. Cần thiết kế ingestion để dòng được định tuyến đúng phân vùng và không tạo áp lực không cần thiết.

### Nạp theo thứ tự partition key

Nếu dữ liệu đến gần theo thứ tự thời gian, việc nạp theo thời gian có thể giúp locality và đơn giản hóa vận hành. Tuy nhiên, không phải workload nào cũng có dữ liệu đến đúng thứ tự.

### Backfill dữ liệu cũ

Một batch backfill có thể ghi vào nhiều phân vùng cũ. Hãy xem:

- Phân vùng đích đã tồn tại chưa?
- Index trên phân vùng có cần tạo hoặc rebuild không?
- Thống kê có được cập nhật sau nạp không?
- Có lock hoặc cạnh tranh với truy vấn đang đọc phân vùng đó không?
- WAL, replication lag và I/O có vượt ngưỡng không?
- Có cần nạp vào bảng staging rồi attach partition không?

### Attach partition từ bảng staging

Trong một số hệ quản trị, có thể nạp dữ liệu vào bảng độc lập, xác minh constraint/range rồi gắn bảng đó làm partition. Cách này có thể giảm tác động của quá trình bulk load lên bảng đang phục vụ truy vấn, nhưng điều kiện attach và kiểm tra dữ liệu phụ thuộc engine.

Với PostgreSQL, bảng được attach phải thỏa ranh giới partition và các điều kiện về cấu trúc/index. Constraint xác nhận miền dữ liệu có thể giúp tránh quét xác minh toàn bộ bảng trong một số trường hợp. Cần kiểm tra tài liệu phiên bản trước khi áp dụng.

## 12. Phân vùng và truy vấn JOIN

Partitioning có thể hỗ trợ join khi hai bảng được chia theo các khóa tương thích. Một số hệ quản trị có thể thực hiện partition-wise join: nối các phân vùng tương ứng thay vì nối toàn bộ hai bảng như một tập lớn.

Ví dụ, bảng orders và order_items cùng được phân vùng theo tháng đặt hàng hoặc một khóa có quan hệ tương ứng. Nếu truy vấn lọc một khoảng thời gian và điều kiện join phù hợp, hệ quản trị có thể xử lý từng cặp phân vùng.

Điều kiện để có lợi:

- Hai bảng có chiến lược và ranh giới phân vùng tương thích.
- Điều kiện JOIN phù hợp với partition key hoặc có thể xác định cặp phân vùng.
- Truy vấn có filter giúp pruning.
- Số phân vùng và lượng dữ liệu mỗi phân vùng hợp lý.
- Optimizer của engine hỗ trợ chiến lược partition-wise join trong tình huống đó.

Nếu hai bảng phân vùng không tương thích, hệ quản trị có thể phải truy cập nhiều phân vùng và thực hiện join thông thường. Không nên partition cả hai bảng chỉ với kỳ vọng join sẽ tự động nhanh hơn.

### Phân vùng và aggregate

Một số hệ quản trị có thể tổng hợp từng phân vùng rồi kết hợp kết quả nếu phép toán và điều kiện cho phép. Điều này có thể giảm lượng dữ liệu trung gian hoặc hỗ trợ parallelism. Nhưng optimizer cần bảo toàn ngữ nghĩa, đặc biệt với DISTINCT, ORDER BY, LIMIT và aggregate không thể kết hợp đơn giản.

## 13. Phân vùng có thể làm truy vấn chậm hơn khi nào?

Partitioning có chi phí. Các tình huống sau cần đặc biệt chú ý:

### Truy vấn không lọc partition key

Nếu truy vấn phải đọc tất cả phân vùng, nó có thể phải mở nhiều index, tạo nhiều node scan và kết hợp nhiều kết quả. Một bảng không phân vùng có thể có kế hoạch đơn giản hơn.

### Quá nhiều phân vùng

Số lượng phân vùng lớn làm tăng metadata, thời gian lập kế hoạch, số đối tượng index và chi phí vận hành. Một truy vấn có thể phải xét hàng nghìn phân vùng nếu pruning không hiệu quả.

### Phân bố dữ liệu lệch

Một phân vùng có thể lớn hơn nhiều phân vùng khác. Điều này tạo hot partition, mất cân bằng I/O hoặc parallel worker. Hash partitioning cũng không bảo đảm cân bằng hoàn hảo nếu hash key hoặc workload có đặc điểm lệch.

### Phân vùng quá nhỏ

Nhiều phân vùng có ít dòng có thể tạo overhead lớn so với lợi ích. Mỗi phân vùng vẫn cần metadata, index và công việc bảo trì.

### Index không phù hợp bên trong partition

Pruning chọn đúng một phân vùng nhưng truy vấn vẫn quét toàn bộ phân vùng lớn. Cần index hoặc access path phù hợp với điều kiện còn lại.

### DDL và quản lý vòng đời phức tạp

Tạo, attach, detach, rebuild index và backup nhiều phân vùng cần lịch vận hành, quyền và kiểm soát phụ thuộc. Nếu không tự động hóa và giám sát, lỗi thiếu phân vùng hoặc retention sai có thể gây gián đoạn hoặc mất dữ liệu.

## 14. Theo dõi phân vùng và thống kê

Để duy trì hiệu năng, cần quan sát cả cấp bảng cha lẫn từng phân vùng.

Các thông tin hữu ích:

- Số dòng và kích thước heap từng phân vùng.
- Kích thước index của từng phân vùng.
- Số phân vùng được truy cập trong mỗi truy vấn.
- Số phân vùng bị prune.
- Phân bố truy cập đọc/ghi theo partition.
- Tỷ lệ dữ liệu trong default partition nếu có.
- Tuổi dữ liệu và thời hạn retention.
- Thống kê và độ mới của thống kê từng phân vùng.
- Autovacuum, analyze, dead tuples và bloat theo engine.
- Replication lag, backup duration và I/O trong lúc bảo trì.

Một bảng cha có thống kê tổng thể không phải lúc nào cũng mô tả đủ phân bố lệch giữa các phân vùng. Cần cập nhật thống kê theo cơ chế của hệ quản trị và kiểm tra plan cho các phân vùng lớn/nhỏ.

### Ví dụ xem kích thước trong PostgreSQL

Có thể dùng các hàm kích thước và catalog để kiểm tra bảng cùng index. Ví dụ đơn giản cho một phân vùng đã biết:

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('events_2026_04')) AS heap_size,
    pg_size_pretty(pg_indexes_size('events_2026_04')) AS indexes_size,
    pg_size_pretty(pg_total_relation_size('events_2026_04')) AS total_size;
~~~

Tên quan hệ phải được thay bằng phân vùng tồn tại trong hệ thống. Với nhiều phân vùng, có thể lấy danh sách từ catalog partition và tổng hợp số liệu bằng công cụ giám sát hoặc truy vấn quản trị phù hợp.

## 15. Đọc execution plan để xác nhận pruning

Một thiết kế phân vùng chỉ có giá trị hiệu năng khi truy vấn thực sự loại bỏ được các phân vùng không liên quan.

Trong PostgreSQL, có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, event_type
FROM events
WHERE occurred_at >= TIMESTAMPTZ '2026-04-10 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-04-15 00:00:00+00'
  AND tenant_id = 9001;
~~~

Khi đọc plan, kiểm tra:

- Có bao nhiêu partition scan được đưa vào kế hoạch?
- Có thông tin Subplans Removed cho pruning lúc thực thi không?
- Các phân vùng được truy cập có đúng với khoảng điều kiện không?
- Rows và loops của từng partition scan là bao nhiêu?
- Có index scan hay sequential scan bên trong phân vùng?
- Buffers hit/read và temp I/O là bao nhiêu?
- Planning Time có tăng do quá nhiều phân vùng không?
- Actual rows có lệch nhiều so với estimated rows không?

Tên node và cách hiển thị phụ thuộc phiên bản. Trong một số kế hoạch, các partition scan xuất hiện dưới Append hoặc Merge Append. Cần xem actual execution statistics, không chỉ dựa vào plan ước lượng.

### Truy vấn không có pruning

Đo thêm truy vấn chỉ lọc event_type:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM events
WHERE event_type = 'LOGIN';
~~~

Nếu plan truy cập tất cả phân vùng, đó là kết quả hợp lý khi điều kiện không ràng buộc occurred_at. Nếu truy vấn này quan trọng, có thể cần index phù hợp trên từng phân vùng, một khóa phân vùng khác hoặc một mô hình lưu trữ khác. Không đổi partition key chỉ dựa trên một truy vấn riêng lẻ; hãy đánh giá toàn bộ workload.

## 16. Benchmark thiết kế phân vùng

Benchmark cần so sánh bảng phân vùng với phương án không phân vùng hoặc với các granularity khác trên cùng dữ liệu và workload.

### Chuẩn bị dữ liệu

Dữ liệu thử nghiệm nên phản ánh:

- Tổng số dòng và tốc độ tăng trưởng.
- Phân bố theo thời gian hoặc partition key.
- Tenant/region có dữ liệu lệch.
- Tỷ lệ dữ liệu nóng và dữ liệu lịch sử.
- Truy vấn theo khoảng ngắn và dài.
- Truy vấn không có partition key.
- Tỷ lệ insert, update, delete và backfill.
- Các join, aggregate và báo cáo thực tế.

Dữ liệu đồng đều có thể che giấu hot partition hoặc skew trong production.

### Các phép đo cần có

| Nhóm đo | Chỉ số |
|---|---|
| Pruning | Số phân vùng được xét, số phân vùng bị loại |
| Truy cập dữ liệu | Rows scanned, rows returned, buffers, physical reads |
| Thời gian | Planning time, execution time, p50/p95/p99 |
| Tài nguyên | CPU, memory, temp I/O, storage IOPS |
| Ghi dữ liệu | Insert/update throughput, WAL/log volume, replication lag |
| Bảo trì | Analyze/vacuum duration, index build, backup/restore |
| Vòng đời | Thời gian detach/archive/drop và mức khóa phát sinh |
| Vận hành | Số phân vùng, metadata, lỗi thiếu partition, dung lượng |

### Quy trình benchmark

1. Ghi lại phiên bản DB, schema, partition key, granularity và index.
2. Nạp dữ liệu đại diện với phân bố giống production.
3. Thu thập thống kê sau nạp.
4. Chạy truy vấn đại diện có và không có điều kiện partition key.
5. Đo khoảng truy vấn hẹp, rộng và trang dữ liệu lịch sử.
6. Đo INSERT liên tục, batch load và backfill.
7. Chạy với mức concurrency gần production.
8. Đo thời gian lập kế hoạch, thực thi, buffers, CPU và I/O.
9. Thực hiện thử nghiệm retention trên môi trường kiểm thử.
10. So sánh với baseline không phân vùng hoặc granularity khác.
11. Đánh giá chi phí vận hành và khả năng phục hồi.
12. Lặp lại phép đo sau khi thay đổi partition key, granularity hoặc index.

Không kết luận chỉ từ một truy vấn có pruning tốt. Một thiết kế còn phải phục vụ các truy vấn không có partition key, thao tác ghi và bảo trì.

## 17. Quy trình thiết kế và triển khai phân vùng

Một quy trình thực tế có thể gồm:

1. **Thu thập workload:** liệt kê truy vấn quan trọng, điều kiện lọc, thời gian lưu trữ và tần suất ghi.
2. **Xác định mục tiêu:** giảm phạm vi truy cập, quản lý retention, tăng khả năng nạp dữ liệu hay phân tán tải.
3. **Chọn partition key:** dựa trên filter phổ biến, phân bố dữ liệu và vòng đời.
4. **Chọn strategy:** RANGE, LIST, HASH hoặc kết hợp.
5. **Chọn granularity:** tính kích thước mỗi phân vùng và số lượng trong thời gian vận hành.
6. **Thiết kế index:** xác định access path bên trong từng phân vùng.
7. **Rà soát ràng buộc:** primary key, unique, foreign key, check constraint và quan hệ tham chiếu.
8. **Lập kế hoạch DDL/migration:** cách tạo bảng mới, chuyển dữ liệu, kiểm tra kết quả và rollback.
9. **Tự động hóa lifecycle:** tạo trước partition, giám sát thiếu partition, archive và retention.
10. **Benchmark:** đo truy vấn, ghi, bảo trì và concurrency.
11. **Triển khai có kiểm soát:** theo dõi plan, pruning, I/O và lỗi định tuyến dữ liệu.
12. **Đánh giá định kỳ:** xem lại khi workload, quy mô hoặc chính sách lưu trữ thay đổi.

### Di chuyển bảng lớn sang mô hình phân vùng

Không nên giả định có thể đổi một bảng lớn đang chạy sang partitioned table bằng một lệnh mà không ảnh hưởng dịch vụ. Quy trình có thể cần tạo bảng mới, đồng bộ ghi, backfill theo batch, xác minh số dòng và constraint, chuyển luồng truy cập rồi mới loại bỏ bảng cũ. Chi tiết phụ thuộc hệ quản trị và yêu cầu downtime.

Cần tính đến dung lượng tạm trong quá trình chuyển, replication, backup, quyền truy cập, trigger, view, foreign key và các job phụ thuộc.

## 18. Những sai lầm thường gặp

- **Cho rằng phân vùng tự động làm truy vấn nhanh:** nếu không prune hoặc phải đọc hầu hết dữ liệu, lợi ích có thể rất nhỏ.
- **Chọn partition key chỉ theo cardinality:** số giá trị cao không bảo đảm phù hợp với workload.
- **Không có điều kiện trên partition key:** truy vấn phải truy cập nhiều phân vùng.
- **Phân vùng quá nhỏ:** số lượng phân vùng và overhead lập kế hoạch tăng.
- **Phân vùng quá lớn:** phạm vi truy cập và bảo trì vẫn rộng.
- **Dùng LIST cho hàng triệu tenant:** số phân vùng có thể trở nên khó quản lý.
- **Dùng HASH cho retention theo thời gian:** xóa dữ liệu cũ theo một hash bucket không đơn giản.
- **Bỏ qua skew:** một phân vùng nóng có thể trở thành nút thắt.
- **Không tạo phân vùng tương lai:** INSERT có thể thất bại hoặc rơi vào default partition.
- **Dùng default partition mà không giám sát:** dữ liệu sai miền có thể tích tụ và cản trở việc tạo partition đúng.
- **Không tạo index phù hợp trong partition:** pruning xong vẫn quét phần lớn phân vùng.
- **Bỏ qua unique/FK:** ràng buộc toàn cục có thể bị giới hạn bởi partition key và engine.
- **DROP/DETACH mà chưa kiểm tra retention và backup:** có thể mất dữ liệu hoặc phá vỡ phụ thuộc.
- **Chỉ benchmark truy vấn đọc:** chi phí ghi, DDL, backup và vận hành có thể tăng.
- **Tạo quá nhiều partition mà không đo planning time:** optimizer và metadata có thể trở thành overhead.

## 19. Checklist trước khi đưa partitioning vào production

- Mục tiêu phân vùng được xác định rõ: pruning, retention, ingest hay phân tán dữ liệu.
- Partition key xuất hiện trong các truy vấn quan trọng hoặc có lý do vận hành rõ ràng.
- Strategy RANGE/LIST/HASH phù hợp với phân bố dữ liệu.
- Granularity cân bằng giữa phạm vi truy cập và số lượng partition.
- Đã mô hình hóa skew và hot partition.
- Index trong từng partition hỗ trợ các truy vấn mục tiêu.
- Ràng buộc unique, primary key và foreign key được bảo đảm đúng.
- Có kế hoạch tạo trước partition và xử lý giá trị ngoài miền.
- Default partition, nếu có, được giám sát.
- Có quy trình archive/detach/drop và xác minh backup.
- Đã kiểm tra khóa DDL, replication và thời gian bảo trì.
- Execution plan xác nhận pruning diễn ra như dự kiến.
- Đã benchmark truy vấn có và không có partition key.
- Đã đo workload đọc, ghi, join, aggregate và concurrency.
- Có cảnh báo về số lượng partition, kích thước và tăng trưởng.
- Có baseline và quy trình đánh giá lại khi workload thay đổi.

## Kết luận

Phân vùng dữ liệu có hai mục tiêu thực tiễn: giảm phạm vi dữ liệu cần truy cập khi truy vấn phù hợp với partition key, và đơn giản hóa vòng đời bằng cách quản lý từng phần dữ liệu theo thời gian hoặc nhóm nghiệp vụ. RANGE, LIST, HASH và phân vùng nhiều cấp cung cấp các cách chia khác nhau; mỗi cách có lợi ích và chi phí riêng.

Hiệu quả phụ thuộc vào việc truy vấn có thể prune phân vùng hay không, kích thước từng phần, phân bố dữ liệu, index bên trong partition và khả năng quản lý số lượng phân vùng. Hãy thiết kế theo workload và retention, kiểm tra execution plan, đo cả truy vấn đọc lẫn ghi và thử quy trình bảo trì trước khi triển khai. Phân vùng chỉ nên được giữ khi số liệu xác nhận nó giảm công việc truy cập hoặc làm vòng đời dữ liệu đơn giản hơn mà tổng chi phí vận hành vẫn phù hợp.
