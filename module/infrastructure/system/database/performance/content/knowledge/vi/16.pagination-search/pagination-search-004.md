# Phân trang khi dữ liệu thay đổi đồng thời và yêu cầu nhất quán

Phân trang thường được xem là việc chia kết quả truy vấn thành từng nhóm nhỏ để API hoặc giao diện chỉ tải một số hàng mỗi lần. Tuy nhiên, khi nhiều người dùng đồng thời thêm, xóa hoặc cập nhật dữ liệu, trang thứ hai có thể không còn là phần tiếp theo của trang thứ nhất. Người dùng có thể thấy một bản ghi lặp lại, bỏ sót bản ghi hoặc nhận các giá trị thuộc những thời điểm khác nhau.

Trong tối ưu hiệu năng cơ sở dữ liệu, phân trang phải cân bằng ba mục tiêu: truy xuất nhanh, duyệt dữ liệu ổn định và mức nhất quán phù hợp với nghiệp vụ. OFFSET/LIMIT đơn giản nhưng có thể tốn kém khi offset lớn và nhạy với thay đổi vị trí hàng. Keyset pagination dùng khóa của hàng cuối cùng làm điểm tiếp tục, thường hiệu quả hơn cho tập dữ liệu lớn, nhưng bản thân cursor không tạo ra snapshot nhất quán. Muốn mọi trang phản ánh cùng một thời điểm, cần kết hợp chiến lược phân trang với cơ chế snapshot, phiên bản dữ liệu hoặc một tập kết quả đã được cố định.

## 1. Vấn đề của phân trang khi dữ liệu thay đổi

Giả sử giao diện hiển thị danh sách đơn hàng mới nhất, mỗi trang 20 hàng. Người dùng mở trang đầu, sau đó một đơn hàng mới được tạo trước khi họ chuyển sang trang thứ hai. Nếu trang thứ hai dùng OFFSET 20 trên trạng thái dữ liệu mới, vị trí của các hàng đã dịch chuyển. Hàng cuối trang đầu có thể xuất hiện lại ở trang hai, hoặc một hàng vốn nằm ở trang hai bị đẩy sang trang ba.

Các thay đổi đồng thời thường gặp:

- **INSERT:** hàng mới được thêm vào trước hoặc giữa vị trí đang duyệt.
- **DELETE:** hàng đã bị xóa làm các vị trí phía sau dịch lên.
- **UPDATE khóa sắp xếp:** hàng chuyển từ vị trí này sang vị trí khác vì created_at, priority, status hoặc cột sort thay đổi.
- **UPDATE điều kiện lọc:** hàng đi vào hoặc ra khỏi tập kết quả vì trạng thái, tenant, quyền truy cập hoặc thuộc tính lọc thay đổi.
- **UPDATE nội dung hiển thị:** vị trí hàng không đổi nhưng giá trị trả về ở trang sau đã khác so với thời điểm tải trang đầu.
- **Thay đổi quan hệ:** dữ liệu liên quan được thêm hoặc xóa khiến join làm số hàng kết quả thay đổi.

Không có một chiến lược phân trang duy nhất đáp ứng mọi yêu cầu. Danh sách hoạt động có thể chấp nhận dữ liệu mới xuất hiện khi tải lại; báo cáo tài chính hoặc kết quả kiểm toán có thể cần một tập dữ liệu cố định tại một thời điểm.

## 2. Vì sao OFFSET/LIMIT có thể lặp hoặc bỏ sót hàng?

OFFSET bỏ qua một số hàng đầu theo thứ tự sắp xếp rồi trả về số hàng tiếp theo. Ví dụ:

~~~sql
SELECT id, created_at, total_amount
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;
~~~

Trang tiếp theo:

~~~sql
SELECT id, created_at, total_amount
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 20;
~~~

Hai câu lệnh thường được chạy ở hai request HTTP riêng, tức hai statement riêng và có thể dùng hai snapshot dữ liệu khác nhau.

### 2.1. INSERT trước vị trí offset

Giả sử thứ tự ban đầu là:

| Vị trí | Bản ghi |
|---:|---|
| 1 | A |
| 2 | B |
| 3 | C |
| 4 | D |
| 5 | E |
| 6 | F |

Trang đầu lấy A, B, C. Trước khi tải trang hai, một hàng X mới được thêm vào đầu danh sách:

| Vị trí mới | Bản ghi |
|---:|---|
| 1 | X |
| 2 | A |
| 3 | B |
| 4 | C |
| 5 | D |
| 6 | E |
| 7 | F |

Nếu trang hai dùng OFFSET 3, kết quả là C, D, E. C đã xuất hiện ở trang đầu nên bị lặp.

### 2.2. DELETE trước vị trí offset

Nếu A bị xóa sau khi trang đầu được tải, danh sách còn B, C, D, E, F. Trang hai dùng OFFSET 3 sẽ bắt đầu ở E, khiến D bị bỏ qua vì vị trí đã dịch lên.

### 2.3. UPDATE khóa sắp xếp

Nếu một hàng được cập nhật created_at hoặc priority, nó có thể di chuyển qua ranh giới giữa hai trang. Hàng đã xem có thể xuất hiện lần nữa; hàng chưa xem có thể chuyển lên phía trước offset và bị bỏ qua.

### 2.4. OFFSET không có thứ tự xác định

Không dùng LIMIT/OFFSET nếu không có ORDER BY. Cơ sở dữ liệu không cam kết thứ tự hàng ổn định khi không chỉ định thứ tự. Ngay cả khi có ORDER BY trên một cột không duy nhất, các hàng có cùng giá trị sắp xếp vẫn có thể đổi vị trí tương đối giữa các lần chạy.

Luôn tạo thứ tự xác định bằng cách thêm khóa duy nhất làm tie-breaker:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Thứ tự này làm cho vị trí hàng rõ ràng trong một snapshot. Nó không ngăn các hàng di chuyển khi dữ liệu thay đổi giữa hai snapshot.

## 3. Giữ một snapshot cho nhiều trang

Nếu yêu cầu là mọi trang phải phản ánh cùng một trạng thái dữ liệu, cách trực tiếp nhất về mặt ngữ nghĩa là đọc tất cả trang từ cùng một snapshot nhất quán.

Ví dụ, người dùng mở báo cáo lúc 10:00. Trang 1, trang 2 và trang 3 đều phải thể hiện dữ liệu nhìn thấy tại 10:00, dù các giao dịch khác tiếp tục thêm hoặc cập nhật đơn hàng sau đó.

### 3.1. Snapshot isolation và transaction dài

Nhiều hệ quản trị hỗ trợ cơ chế MVCC hoặc row versioning. Một transaction ở mức cô lập phù hợp có thể nhìn thấy một snapshot nhất quán trong suốt thời gian transaction.

Ưu điểm:

- Hàng mới được commit sau thời điểm snapshot không xuất hiện trong các trang của transaction đó.
- Hàng bị xóa hoặc cập nhật sau snapshot vẫn có thể được đọc theo phiên bản cũ nếu engine còn giữ phiên bản cần thiết.
- Các trang được đọc từ cùng một góc nhìn dữ liệu, giúp báo cáo nhất quán hơn.

Hạn chế:

- Transaction phải được giữ mở qua nhiều lần người dùng yêu cầu trang.
- Connection có thể bị giữ lâu, làm giảm khả năng phục vụ request khác.
- Phiên bản hàng cũ hoặc undo information phải được giữ lâu hơn, làm tăng áp lực vacuum/undo và dung lượng lưu trữ.
- Transaction có thể bị timeout, ngắt kết nối hoặc hết thời gian snapshot.
- API stateless và hệ thống nhiều instance khó gắn các request rời rạc vào cùng một transaction/connection.

Vì vậy, giữ transaction mở trong suốt thời gian người dùng đọc từng trang thường không phù hợp với giao diện web có thời gian chờ tùy ý. Nó có thể phù hợp với tác vụ export hoặc báo cáo chạy nền có thời gian hữu hạn và kiểm soát được vòng đời.

### 3.2. Phân biệt nhất quán theo statement và theo transaction

Mỗi hệ quản trị có mức cô lập và quy tắc snapshot riêng. Một request trang mới có thể nhận snapshot mới ngay cả khi ứng dụng dùng một mức cô lập có tên giống nhau.

| Hệ quản trị | Cơ chế thường dùng | Phạm vi snapshot cần hiểu |
|---|---|---|
| PostgreSQL | REPEATABLE READ dùng snapshot ổn định cho transaction | Các SELECT trong cùng transaction nhìn cùng snapshot; READ COMMITTED thường lấy snapshot mới cho mỗi statement |
| SQL Server | SNAPSHOT isolation; READ COMMITTED SNAPSHOT (RCSI) | SNAPSHOT giữ góc nhìn theo transaction; RCSI cung cấp row versioning ở mức statement |
| MySQL InnoDB | Consistent read với REPEATABLE READ hoặc READ COMMITTED | REPEATABLE READ thường tái sử dụng snapshot của consistent read trong transaction; READ COMMITTED tạo snapshot mới cho mỗi consistent read |
| Oracle Database | Read consistency theo SCN của statement; Flashback Query | Mỗi statement thường có read-consistent view riêng; AS OF SCN/TIMESTAMP có thể cố định mốc đọc nếu undo còn đáp ứng |

Không suy luận hành vi chỉ từ tên mức cô lập. Hãy kiểm tra tài liệu đúng phiên bản, loại câu lệnh (consistent read hay locking read), autocommit và cấu hình của hệ thống.

## 4. PostgreSQL: REPEATABLE READ và snapshot

Trong PostgreSQL, READ COMMITTED thường tạo snapshot ở đầu mỗi statement. Nếu trang 1 và trang 2 là hai SELECT riêng, mỗi câu có thể nhìn dữ liệu mới được commit ở thời điểm bắt đầu câu lệnh.

REPEATABLE READ giữ snapshot của transaction sau khi snapshot được thiết lập. Minh họa:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT id, created_at
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;

-- Các trang tiếp theo được đọc trong cùng transaction.
SELECT id, created_at
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 20;

COMMIT;
~~~

Các SELECT trong transaction này đọc cùng snapshot nhất quán. Một giao dịch khác commit đơn hàng mới sau khi snapshot được thiết lập sẽ không làm thay đổi tập dữ liệu mà transaction hiện tại nhìn thấy.

Đối với API web, không nên mặc định giữ transaction và connection mở giữa các lần nhấn nút của người dùng. Với export có thời gian hữu hạn, có thể mở transaction trong worker, đọc tuần tự các batch rồi đóng transaction sau khi hoàn tất.

PostgreSQL có cơ chế exported snapshot, nhưng việc chia sẻ snapshot giữa các transaction cần điều phối chính xác và transaction giữ snapshot phải còn tồn tại trong thời gian import. Đây là kỹ thuật chuyên biệt, không nên dùng như một cursor token đơn giản cho API công khai.

## 5. SQL Server: SNAPSHOT và READ_COMMITTED_SNAPSHOT

SQL Server hỗ trợ row versioning cho các mức đọc nhất quán. Cần phân biệt:

- **READ COMMITTED thông thường:** hành vi khóa phụ thuộc cấu hình; statement có thể chịu ảnh hưởng từ các giao dịch đồng thời.
- **READ_COMMITTED_SNAPSHOT (RCSI):** mỗi statement đọc một snapshot nhất quán tại thời điểm statement bắt đầu.
- **SNAPSHOT isolation:** các statement trong cùng transaction nhìn một snapshot theo transaction.

Nếu mỗi trang là một statement riêng chạy dưới RCSI, trang thứ hai có thể nhìn thấy dữ liệu đã commit sau trang đầu. RCSI giúp statement không đọc dữ liệu dở dang và giảm một số blocking, nhưng không tự giữ cùng snapshot qua nhiều request.

Khi database đã bật ALLOW_SNAPSHOT_ISOLATION, một transaction có thể dùng:

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
BEGIN TRANSACTION;

SELECT id, created_at
FROM dbo.Orders
ORDER BY created_at DESC, id DESC
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;

SELECT id, created_at
FROM dbo.Orders
ORDER BY created_at DESC, id DESC
OFFSET 20 ROWS FETCH NEXT 20 ROWS ONLY;

COMMIT;
~~~

Hai SELECT cùng transaction đọc theo snapshot transaction. Cần xác nhận cấu hình database, version store trong tempdb hoặc persistent version store tùy phiên bản/cấu hình, thời gian transaction và giới hạn vận hành.

## 6. MySQL InnoDB: consistent read trong transaction

InnoDB dùng MVCC cho consistent nonlocking reads. Với REPEATABLE READ, các consistent read trong cùng transaction thường sử dụng cùng read view sau khi được thiết lập. Với READ COMMITTED, mỗi consistent read có thể nhận read view mới.

Ví dụ:

~~~sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT id, created_at
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;

SELECT id, created_at
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 20;

COMMIT;
~~~

WITH CONSISTENT SNAPSHOT thiết lập read view khi bắt đầu transaction trong điều kiện hỗ trợ của InnoDB và REPEATABLE READ. Các locking read như SELECT ... FOR UPDATE có quy tắc khác với consistent nonlocking read; không trộn chúng mà không hiểu rõ snapshot và khóa.

Transaction đọc kéo dài có thể làm undo history cần thiết chưa được purge, tăng áp lực lưu trữ và làm chậm hoạt động bảo trì. Hãy giới hạn thời gian export, số batch và xử lý lỗi để transaction luôn được đóng.

## 7. Oracle Database: SCN và Flashback Query

Oracle cung cấp read consistency theo System Change Number (SCN). Một statement thông thường đọc dữ liệu nhất quán tại SCN của statement đó. Nếu mỗi trang là một statement riêng, các trang có thể nhìn các SCN khác nhau.

Để cố định mốc dữ liệu qua nhiều câu truy vấn, có thể dùng Flashback Query với cùng một SCN:

~~~sql
SELECT id, created_at
FROM orders AS OF SCN :snapshot_scn
ORDER BY created_at DESC, id DESC
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Trang tiếp theo dùng cùng SCN:

~~~sql
SELECT id, created_at
FROM orders AS OF SCN :snapshot_scn
ORDER BY created_at DESC, id DESC
OFFSET 20 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

SCN cần được lấy và lưu an toàn ở đầu phiên phân trang. Flashback phụ thuộc undo data còn được giữ, quyền truy cập và các giới hạn của đối tượng. Nếu snapshot quá cũ so với undo retention, truy vấn có thể thất bại. Không coi SCN là một bản sao dữ liệu vĩnh viễn.

## 8. Keyset pagination: tiếp tục từ khóa cuối thay vì offset

Keyset pagination (còn gọi là seek method hoặc cursor-based pagination) dùng giá trị sắp xếp của hàng cuối trang hiện tại để tìm các hàng tiếp theo. Nó tránh phải bỏ qua một số lượng lớn hàng ở đầu kết quả.

Giả sử thứ tự là created_at giảm dần, sau đó id giảm dần:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE (created_at, id) < (:last_created_at, :last_id)
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Đây là dạng so sánh tuple được PostgreSQL và một số hệ quản trị hỗ trợ. Với SQL Server hoặc để viết theo dạng tương thích rộng hơn, diễn đạt thứ tự từ điển:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE created_at < @last_created_at
   OR (
       created_at = @last_created_at
       AND id < @last_id
   )
ORDER BY created_at DESC, id DESC
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Với lần tải đầu tiên, không có điều kiện cursor; truy vấn lấy 20 hàng đầu theo thứ tự xác định. Các trang sau truyền created_at và id của hàng cuối cùng đã nhận.

### 8.1. Vì sao phải có khóa tie-breaker duy nhất?

Nếu chỉ sắp xếp theo created_at, nhiều hàng có thể có cùng timestamp. Cursor chỉ lưu created_at sẽ không xác định chính xác điểm tiếp tục; các hàng cùng timestamp có thể bị lặp hoặc bỏ sót.

Thêm id duy nhất tạo thứ tự toàn phần:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Cursor cần lưu cả hai giá trị. Predicate tiếp tục phải khớp chính xác thứ tự:

~~~sql
WHERE created_at < :last_created_at
   OR (
       created_at = :last_created_at
       AND id < :last_id
   )
~~~

Nếu thứ tự tăng dần, toán tử so sánh đổi tương ứng. Với nhiều cột sắp xếp, cần mở rộng điều kiện từ điển theo từng tiền tố bằng nhau.

### 8.2. Chỉ mục hỗ trợ keyset

Với truy vấn lọc theo tenant và trạng thái rồi sắp xếp theo created_at, id, một chỉ mục có thể được thử:

~~~sql
CREATE INDEX ix_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

Thứ tự thực tế phụ thuộc điều kiện equality/range, phân bố dữ liệu, cột trả về và hệ quản trị. Nếu có nhiều trạng thái hoặc truy vấn không luôn lọc status, cần đánh giá các phương án index khác.

Keyset pagination thường có độ phức tạp ổn định hơn khi đi sâu vào tập dữ liệu vì engine tìm từ khóa cursor thay vì bỏ qua offset lớn. Tuy vậy, hiệu quả vẫn phụ thuộc chỉ mục, predicate, độ chọn lọc và kích thước trang.

## 9. Keyset ổn định hơn nhưng không tự tạo snapshot

Keyset tránh lỗi dịch vị trí do INSERT/DELETE nằm trước offset, nhưng không đảm bảo toàn bộ trang thuộc cùng một thời điểm.

Giả sử đang duyệt đơn hàng mới nhất theo created_at DESC, id DESC:

- Hàng mới có khóa lớn hơn cursor thường nằm trước vị trí đã duyệt và không xuất hiện trong các trang tiếp theo. Điều này tránh việc hàng mới đẩy offset, nhưng người dùng sẽ không thấy hàng mới nếu không tải lại từ đầu.
- Hàng được chèn với created_at cũ hơn cursor có thể xuất hiện ở một trang sau, dù nó chưa tồn tại khi trang đầu được tải.
- Hàng chưa đọc bị xóa trước khi tới lượt sẽ không xuất hiện.
- Hàng đã đọc bị xóa không gây dịch offset, nhưng lần tải lại hoặc truy vấn chi tiết có thể không còn tìm thấy nó.
- Hàng chưa đọc đổi created_at sang giá trị nằm trước cursor có thể bị bỏ qua.
- Hàng đã đọc đổi created_at sang giá trị nằm sau cursor có thể xuất hiện lại ở trang tiếp theo.
- Các cột không thuộc thứ tự có thể thay đổi và trang sau sẽ trả giá trị mới nếu không dùng snapshot.

Vì vậy, keyset cung cấp cách duyệt theo khóa có ranh giới rõ ràng, nhưng mức nhất quán vẫn phụ thuộc việc khóa sắp xếp có bất biến không và dữ liệu có được đọc từ cùng snapshot không.

### 9.1. Chọn khóa sắp xếp ít thay đổi

Ưu tiên khóa:

- Không NULL hoặc có quy tắc NULL được định nghĩa rõ.
- Có thứ tự so sánh ổn định.
- Có tie-breaker duy nhất.
- Ít hoặc không được cập nhật sau khi bản ghi tạo ra.
- Có chỉ mục hỗ trợ điều kiện tiếp tục.

created_at do server gán một lần và id duy nhất thường phù hợp hơn priority hoặc status nếu các cột này thay đổi thường xuyên. Tuy nhiên, nếu ứng dụng cho phép nhập dữ liệu cũ hoặc sửa created_at, ngay cả timestamp cũng không hoàn toàn bất biến.

### 9.2. Xử lý NULL trong khóa cursor

So sánh tuple với NULL có thể tạo UNKNOWN. Nếu một cột sắp xếp cho phép NULL, cần xác định NULLS FIRST/LAST và xây dựng predicate tiếp tục tương ứng. Cách đơn giản hơn là chọn cột cursor NOT NULL hoặc thêm một biểu thức phân loại NULL ổn định vào thứ tự, rồi đưa đầy đủ các thành phần đó vào cursor.

Không thay NULL bằng một giá trị sentinel tùy tiện nếu giá trị đó có thể xuất hiện thật hoặc làm thay đổi thứ tự nghiệp vụ. Hãy dùng biểu thức và thứ tự NULL rõ ràng, kiểm tra execution plan và index expression nếu có.

## 10. High-water mark: cố định ranh giới trên của tập dữ liệu

Một yêu cầu thường gặp là người dùng muốn duyệt toàn bộ các bản ghi đã tồn tại khi bắt đầu, nhưng không cần nhìn thấy bản ghi mới được tạo sau đó. Có thể chụp một high-water mark ở lần tải đầu, chẳng hạn giá trị lớn nhất của một khóa tăng đơn điệu, rồi dùng nó làm điều kiện trên cho mọi trang.

Ví dụ:

~~~sql
SELECT MAX(id) AS initial_max_id
FROM orders;
~~~

Lưu initial_max_id trong cursor. Mỗi trang sau giới hạn:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE id <= :initial_max_id
  AND id < :last_id
ORDER BY id DESC
LIMIT 20;
~~~

High-water mark có thể loại các bản ghi có ID lớn hơn mốc ban đầu, nhưng chỉ tạo được một ranh giới đáng tin khi khóa có đặc tính phù hợp. Nó không ngăn cập nhật, xóa hoặc chèn dữ liệu có khóa nhỏ hơn mốc.

### 10.1. Những giới hạn của high-water mark

- Sequence/auto-increment thường cấp số trước khi transaction commit; một transaction cấp ID nhỏ hơn mốc nhưng commit muộn có thể xuất hiện sau khi phân trang bắt đầu.
- Bản ghi cũ có thể được import với ID thấp hơn mốc.
- UPDATE có thể thay đổi nội dung hoặc điều kiện lọc của hàng đã tồn tại.
- DELETE vẫn làm hàng biến mất khỏi trang chưa đọc.
- Nếu thứ tự là created_at nhưng high-water mark chỉ là id, hai khóa có thể không phản ánh cùng một ranh giới thứ tự.

High-water mark phù hợp với workload append-only có quy tắc cấp khóa và commit được hiểu rõ. Nó là kỹ thuật giới hạn tập ứng viên, không thay thế snapshot isolation.

### 10.2. Kết hợp high-water mark với keyset

Nếu bảng append-only và id tăng theo quy tắc nghiệp vụ, có thể dùng cả mốc trên và cursor dưới:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE id <= :initial_max_id
  AND id < :last_id
ORDER BY id DESC
LIMIT 20;
~~~

Điều kiện initial_max_id cố định giới hạn trên; last_id xác định điểm tiếp tục. Nếu dùng một khóa khác để sắp xếp, phải thiết kế cả hai điều kiện theo cùng thứ tự và xem xét commit muộn, cập nhật và xóa.

## 11. Cursor token cho API stateless

Một API cursor-based thường trả về dữ liệu và next_cursor. Cursor nên là một token opaque để client gửi lại nguyên vẹn, không cần tự hiểu cấu trúc bên trong.

Thông tin có thể chứa:

- Giá trị của tất cả cột sắp xếp ở hàng cuối trang.
- Hướng duyệt và phiên bản định nghĩa thứ tự.
- Các bộ lọc ảnh hưởng đến tập kết quả.
- Tenant hoặc phạm vi dữ liệu, nếu phù hợp với mô hình phân quyền.
- High-water mark hoặc snapshot identifier/SCN nếu có cơ chế hỗ trợ.
- Thời điểm tạo và thời hạn hiệu lực của cursor.

Ví dụ payload nội bộ trước khi mã hóa:

~~~json
{
  "version": 1,
  "sort": "created_at_desc_id_desc",
  "last_created_at": "2026-11-19T08:30:00Z",
  "last_id": 918273,
  "filter_hash": "a1b2c3",
  "snapshot_scn": null,
  "expires_at": "2026-11-19T09:00:00Z"
}
~~~

Đây chỉ là ví dụ cấu trúc. API thực tế có thể ký hoặc mã hóa token để ngăn client sửa giá trị cursor, đổi filter hoặc truy cập phạm vi dữ liệu khác. Cursor không thay thế kiểm tra quyền truy cập; server vẫn phải áp dụng tenant và authorization từ danh tính đã xác thực.

### 11.1. Ràng buộc cursor với bộ lọc và thứ tự

Không nên tái sử dụng cursor cũ sau khi client thay đổi filter, sort direction hoặc page size theo cách làm thay đổi ngữ nghĩa truy vấn. Server có thể lưu hash của bộ lọc đã chuẩn hóa và từ chối cursor không khớp.

Nếu thứ tự thay đổi từ created_at DESC sang total_amount DESC, các giá trị cursor cũ không còn xác định cùng vị trí. Dùng trường version trong token để có thể từ chối hoặc hết hạn cursor khi thuật toán phân trang thay đổi.

### 11.2. Cursor không phải bằng chứng quyền truy cập

Ngay cả khi token đã được ký, server vẫn cần kiểm tra người dùng có quyền đọc bản ghi và tenant hiện tại hay không. Không đặt thông tin bí mật hoặc dữ liệu cá nhân không cần thiết vào token dạng client có thể giải mã. Nếu token có chứa snapshot identifier, cần giới hạn thời hạn và kiểm tra snapshot còn khả dụng.

### 11.3. Trang trước

Để lấy trang trước, cần đảo chiều phép so sánh và thứ tự truy vấn, lấy N hàng gần cursor theo hướng ngược, sau đó đảo thứ tự hiển thị ở tầng ứng dụng. Cần kiểm tra cả trường hợp có các giá trị sort trùng nhau và tie-breaker duy nhất.

Ví dụ nếu thứ tự hiển thị là DESC, để lấy các hàng ngay trước cursor có thể truy vấn theo điều kiện lớn hơn cursor và ORDER BY ASC với cùng bộ khóa, LIMIT N; sau đó đảo mảng kết quả để hiển thị DESC. Cách chính xác phụ thuộc cursor là hàng đầu hay hàng cuối của trang hiện tại.

## 12. Chọn mức nhất quán theo yêu cầu nghiệp vụ

Không phải danh sách nào cũng cần snapshot cố định. Chọn chiến lược theo hậu quả khi dữ liệu thay đổi:

| Nhu cầu | Chiến lược phù hợp để cân nhắc | Đặc điểm |
|---|---|---|
| Feed hoạt động, dữ liệu mới có thể xuất hiện khi tải lại | Keyset với khóa ổn định | Hiệu quả cho duyệt tiếp; thường không phải snapshot cố định |
| Danh sách lớn, ưu tiên tốc độ và tránh offset sâu | Keyset pagination | Tránh chi phí bỏ qua nhiều hàng; cần cursor và tie-breaker |
| Báo cáo cần cùng trạng thái dữ liệu qua nhiều trang | Snapshot/AS OF SCN hoặc snapshot được materialize | Các trang nhìn cùng mốc dữ liệu; cần quản lý vòng đời snapshot |
| Export dài có thời gian hữu hạn | Transaction snapshot trong worker hoặc materialized result | Dễ kiểm soát hơn transaction gắn với tương tác người dùng |
| Duyệt tập dữ liệu append-only theo mốc ban đầu | Keyset + high-water mark | Chặn một số hàng mới; không bảo vệ trước mọi update/delete/commit muộn |
| Hàng đợi worker cần nhận việc không trùng | Claim/lease/locking protocol chuyên biệt | Cần thiết kế transaction và khóa; không đồng nhất với pagination giao diện |

### 12.1. Danh sách thông thường

Với danh sách sản phẩm, ticket hoặc đơn hàng, thường chấp nhận rằng nội dung thay đổi giữa các lần tải. Keyset với thứ tự ổn định giúp tránh lặp/bỏ sót do offset dịch chuyển. Người dùng có thể làm mới danh sách để xem bản ghi mới.

### 12.2. Báo cáo và kiểm toán

Với báo cáo cần đối chiếu số liệu, nên xác định mốc dữ liệu rõ ràng. Có thể dùng snapshot transaction trong một tác vụ export, Flashback/AS OF nếu hệ quản trị hỗ trợ, hoặc tạo bảng kết quả tạm có thời hạn. Cần lưu snapshot identifier cùng thông tin truy vấn để có thể tái hiện báo cáo.

### 12.3. Hàng đợi xử lý

Nếu mục tiêu là nhiều worker lấy các job khác nhau, pagination thông thường chưa đủ. Cần cơ chế claim/lease hoặc locking như SELECT ... FOR UPDATE SKIP LOCKED khi hệ quản trị hỗ trợ, cùng transaction ngắn và cập nhật trạng thái nguyên tử. Mục tiêu của hàng đợi là phân phối công việc an toàn, không phải tạo một góc nhìn danh sách bất biến.

## 13. Đánh đổi hiệu năng của OFFSET, keyset và snapshot

| Phương pháp | Chi phí khi đi sâu | Ổn định trước INSERT/DELETE trước vị trí | Nhất quán qua nhiều request | Độ phức tạp |
|---|---|---|---|---|
| OFFSET/LIMIT | Có thể tăng theo số hàng phải bỏ qua | Thấp nếu mỗi request có snapshot mới | Không tự bảo đảm | Thấp |
| Keyset/cursor | Thường ổn định hơn nếu có index phù hợp | Tốt hơn vì không dựa vào vị trí offset | Không tự bảo đảm cùng snapshot | Trung bình |
| OFFSET trong một snapshot transaction | Offset vẫn tốn chi phí khi sâu | Ổn định trong snapshot | Có, trong cùng transaction | Cao về vận hành nếu kéo dài |
| Keyset trong một snapshot transaction | Tránh offset sâu và giữ cùng snapshot | Ổn định trong snapshot | Có, trong cùng transaction | Cao về vận hành nếu kéo dài |
| Keyset + high-water mark | Thường hiệu quả với khóa tăng và index phù hợp | Chặn một số insert mới | Chỉ giới hạn một phần; không phải snapshot | Trung bình |
| Materialized result/ID set | Đọc trang nhanh sau khi tạo kết quả | Ổn định theo tập đã materialize | Có nếu nội dung cũng được cố định | Cao về storage và vòng đời |

OFFSET vẫn có chỗ dùng: trang đầu, tập dữ liệu nhỏ, giao diện cần nhảy tới số trang bất kỳ hoặc truy vấn có giới hạn. Keyset thường phù hợp với nút “xem tiếp” trên tập lớn. Snapshot/materialization dành cho yêu cầu nhất quán mạnh hơn và có thể chấp nhận chi phí vận hành.

## 14. Count tổng và số trang

COUNT(*) chạy riêng ở request sau có thể nhìn một snapshot khác với danh sách. Khi dữ liệu thay đổi, tổng số kết quả có thể không khớp với số hàng người dùng duyệt.

Các lựa chọn:

- Không hiển thị tổng chính xác; chỉ trả has_next hoặc next_cursor.
- Hiển thị tổng ước lượng hoặc tổng được cache và ghi rõ tính chất cập nhật.
- Tính count cùng snapshot với trang nếu nghiệp vụ cần tính nhất quán.
- Materialize tập ID/kết quả và đếm trên chính tập đó.

COUNT trên tập lớn có thể tốn chi phí đáng kể, đặc biệt khi filter phức tạp hoặc join. Không thêm COUNT(*) chỉ để hiển thị “trang 1 trên 8.245” nếu người dùng không cần và hệ thống phải tính lại ở mỗi request.

## 15. Quy trình thiết kế và kiểm chứng phân trang

1. **Xác định mức nhất quán:** người dùng có chấp nhận dữ liệu mới xuất hiện giữa các trang không? Có cần giữ giá trị cũ hay chỉ cần không lặp/không bỏ sót do offset?
2. **Chọn thứ tự xác định:** dùng ORDER BY trên các cột phù hợp và thêm khóa duy nhất làm tie-breaker.
3. **Đánh giá khả năng bất biến:** xác định cột sắp xếp hoặc filter có thể thay đổi trong khi duyệt không.
4. **Chọn phương pháp:** OFFSET cho tập nhỏ/nhảy trang; keyset cho duyệt tiếp; snapshot hoặc materialization cho báo cáo nhất quán.
5. **Thiết kế index:** tạo chỉ mục phù hợp với filter, thứ tự và điều kiện cursor; đo kích thước và chi phí ghi.
6. **Thiết kế cursor:** lưu đủ khóa sắp xếp, filter identity, hướng, phiên bản và snapshot/high-water mark nếu dùng.
7. **Định nghĩa vòng đời:** thời hạn cursor, thời hạn snapshot, xử lý retry, cursor hết hạn và dữ liệu đã xóa.
8. **Kiểm thử thay đổi đồng thời:** chèn, xóa, cập nhật khóa sắp xếp, thay đổi trạng thái và commit muộn giữa các lần lấy trang.
9. **Đối chiếu kết quả:** kiểm tra bản ghi lặp, bản ghi bỏ sót, giá trị thay đổi và tổng số.
10. **Đo hiệu năng:** so sánh p50/p95, logical/physical reads, CPU, số hàng đọc, temp I/O và throughput ở trang đầu lẫn trang sâu.
11. **Kiểm thử tải đồng thời:** chạy nhiều client cùng duyệt và cập nhật dữ liệu; kiểm tra connection pool, version store/undo và lock waits.
12. **Theo dõi sau triển khai:** quan sát cursor hết hạn, snapshot lỗi, transaction kéo dài, độ trễ trang sâu và mức sử dụng tài nguyên.

## 16. Kịch bản kiểm thử tính nhất quán

Một bộ kiểm thử nên mô phỏng các thay đổi xảy ra đúng giữa hai request:

| Bước | Client đọc | Client ghi đồng thời | Điều cần quan sát |
|---|---|---|---|
| 1 | Lấy trang đầu | Không có thay đổi | Lưu khóa cuối và tập ID trang đầu |
| 2 | Chưa lấy trang hai | INSERT hàng có khóa sắp xếp mới nhất | OFFSET có thể lặp hàng; keyset thường không bị dịch vị trí |
| 3 | Lấy trang hai | DELETE hàng nằm trước ranh giới | OFFSET có thể bỏ sót; keyset tiếp tục theo khóa |
| 4 | Lấy trang ba | UPDATE khóa sort của hàng chưa đọc | Hàng có thể chuyển qua cursor, gây bỏ sót hoặc xuất hiện muộn |
| 5 | Lấy trang tiếp | UPDATE cột hiển thị của hàng đã đọc | Giá trị mới có thể xuất hiện nếu không dùng snapshot |
| 6 | Lấy trang tiếp | INSERT bản ghi cũ/backdated hoặc transaction commit muộn | High-water mark có thể không loại được bản ghi |
| 7 | Đọc lại cùng trang trong snapshot | Thực hiện cùng các thay đổi ở client ghi | Kết quả phải giữ theo snapshot nếu cơ chế được cấu hình đúng |

Đối với keyset, xác minh mỗi hàng chỉ xuất hiện một lần trong tập duyệt khi khóa sắp xếp bất biến và dữ liệu không bị xóa. Nếu khóa có thể thay đổi, ghi nhận đây là giới hạn của mô hình và cân nhắc snapshot hoặc khóa sắp xếp bất biến.

Đối với snapshot, xác minh các trang nhìn cùng tập dữ liệu và giá trị tại mốc snapshot. Đồng thời đo thời gian transaction và lượng version/undo giữ lại để chắc chắn yêu cầu nhất quán không tạo áp lực vận hành ngoài khả năng hệ thống.

## 17. Những lỗi thường gặp

- **Dùng ORDER BY trên cột không duy nhất:** thứ tự giữa các hàng bằng khóa không được xác định đầy đủ.
- **Cho rằng ORDER BY giải quyết thay đổi đồng thời:** ORDER BY chỉ xác định thứ tự trong từng snapshot.
- **Cho rằng keyset tự tạo snapshot:** cursor chỉ đánh dấu vị trí; dữ liệu vẫn có thể thay đổi.
- **Dùng khóa sort có thể cập nhật:** hàng có thể di chuyển qua ranh giới cursor.
- **Dùng high-water mark như snapshot:** ID tăng không ngăn update, delete, import ID cũ hoặc transaction commit muộn.
- **Giữ transaction web mở quá lâu:** làm giữ connection và version/undo, ảnh hưởng vacuum hoặc purge.
- **Nhầm RCSI với snapshot transaction trong SQL Server:** RCSI thường cố định snapshot theo statement, không theo chuỗi request.
- **Không phân biệt READ COMMITTED và REPEATABLE READ:** phạm vi snapshot khác nhau theo engine.
- **Bỏ qua undo retention của Oracle:** AS OF SCN có thể thất bại nếu dữ liệu undo không còn.
- **Tạo cursor chỉ chứa một cột sort:** bỏ qua tie-breaker và có thể gây lặp/bỏ sót khi giá trị trùng.
- **Đặt LIMIT riêng cho từng nhánh mà không hợp nhất đúng:** có thể làm sai top N toàn cục.
- **Tính COUNT ở snapshot khác:** tổng số và danh sách không đồng bộ.
- **Không ràng buộc cursor với filter:** client có thể dùng cursor cũ cho một truy vấn khác.
- **Coi cursor là cơ chế phân quyền:** server vẫn phải xác thực và kiểm tra quyền ở mỗi request.

## 18. Checklist chọn chiến lược phân trang

- [ ] Đã xác định mức nhất quán nghiệp vụ cần có giữa các trang.
- [ ] Đã có ORDER BY xác định và tie-breaker duy nhất.
- [ ] Đã đánh giá các cột sort/filter có thể thay đổi hay không.
- [ ] Đã chọn OFFSET, keyset, snapshot hoặc materialized result theo yêu cầu.
- [ ] Nếu dùng keyset, cursor lưu đủ mọi thành phần của thứ tự.
- [ ] Đã xử lý NULL, timestamp precision, timezone và hướng sort.
- [ ] Đã thiết kế index hỗ trợ filter và cursor predicate.
- [ ] Đã xác định snapshot theo statement hay transaction trên đúng hệ quản trị.
- [ ] Đã giới hạn thời gian transaction và theo dõi version store/undo.
- [ ] Nếu dùng high-water mark, đã kiểm tra commit muộn và khóa được cấp trước commit.
- [ ] Cursor được ràng buộc với filter, sort version, tenant và thời hạn.
- [ ] Đã kiểm thử INSERT, DELETE, UPDATE và thay đổi filter giữa các trang.
- [ ] Đã xác minh không lặp/bỏ sót theo mức đảm bảo đã cam kết.
- [ ] Đã đo độ trễ trang đầu/trang sâu, reads, CPU, throughput và tài nguyên snapshot.
- [ ] Đã xác định cách xử lý total count, cursor hết hạn và snapshot không còn khả dụng.

Phân trang nhất quán bắt đầu từ việc xác định người dùng cần duyệt một danh sách đang thay đổi hay một ảnh chụp dữ liệu tại một thời điểm. OFFSET/LIMIT phù hợp với nhiều trường hợp đơn giản nhưng nhạy với thay đổi vị trí và offset sâu. Keyset dùng khóa sắp xếp ổn định để tiếp tục hiệu quả hơn, song không thay thế snapshot. Khi nghiệp vụ yêu cầu mọi trang phản ánh cùng dữ liệu, hãy dùng cơ chế snapshot hoặc materialization có vòng đời được kiểm soát, rồi xác minh bằng các kịch bản ghi đồng thời và số liệu hiệu năng thực tế.
