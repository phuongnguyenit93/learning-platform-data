# Xung đột chứng nhận giao dịch và xử lý tại ứng dụng

Trong MySQL Group Replication, một transaction có thể chạy thành công trên node nhận yêu cầu nhưng vẫn bị hủy ở thời điểm COMMIT. Điều này xảy ra khi cơ chế certification phát hiện một transaction khác đã được chứng nhận trước đó có thay đổi xung đột với transaction hiện tại. Ứng dụng phải nhận diện tình huống này và thực hiện lại toàn bộ transaction theo một chính sách có giới hạn.

Bài học thuộc module **DATABASE_MYSQL**, tập trung vào vận hành hệ thống MySQL có tính sẵn sàng cao: hiểu writeset và certification, phân biệt xung đột chứng nhận với deadlock, thiết kế retry an toàn, bảo vệ tính đúng đắn nghiệp vụ và quan sát lỗi trong môi trường single-primary hoặc multi-primary.

## 1. Certification trong Group Replication

Group Replication cho phép nhiều thành viên trong một nhóm cùng duy trì dữ liệu nhất quán. Mỗi thành viên có thể thực thi transaction cục bộ; trước khi transaction được chấp nhận vào lịch sử chung, nhóm phải kiểm tra khả năng xung đột với các transaction đã được chứng nhận.

Quá trình ở mức khái quát:

1. Ứng dụng mở transaction trên một member và thực hiện các câu lệnh đọc/ghi.
2. MySQL thu thập writeset, tức tập hợp các khóa hàng liên quan đến thay đổi của transaction.
3. Khi transaction commit, writeset được đưa vào thứ tự toàn cục của nhóm và kiểm tra với các writeset đã được chứng nhận trong phạm vi cần thiết.
4. Nếu không có xung đột, transaction được chứng nhận và có thể hoàn tất commit.
5. Nếu có xung đột, transaction bị hủy. Ứng dụng nhận lỗi tại commit và cần quyết định có thực hiện lại hay trả lỗi cho người gọi.

Certification là cơ chế phát hiện xung đột ghi giữa các transaction. Nó giúp các member áp dụng cùng một thứ tự transaction và tránh hai transaction xung đột cùng được commit trên các member khác nhau.

### Writeset được hình thành như thế nào?

Writeset mô tả các hàng bị thay đổi thông qua khóa nhận diện hàng. Primary key là lựa chọn tốt nhất vì nó duy nhất và ổn định. MySQL cũng có thể dùng unique key phù hợp. Khi bảng không có khóa duy nhất phù hợp, khả năng nhận diện xung đột và hiệu quả certification có thể kém hơn; thiết kế Group Replication nên có primary key cho mọi bảng.

Ví dụ:

~~~sql
CREATE TABLE inventory (
  sku VARCHAR(40) PRIMARY KEY,
  quantity INT NOT NULL,
  updated_at TIMESTAMP NOT NULL
) ENGINE=InnoDB;
~~~

Nếu transaction cập nhật hàng có sku = 'SKU-100', khóa này là thành phần quan trọng để xác định writeset. Hai transaction cùng thay đổi hàng SKU-100 có khả năng xung đột ở bước certification.

Certification chủ yếu phát hiện xung đột trên các khóa thuộc writeset. Nó không thay thế việc thiết kế ràng buộc dữ liệu, khóa ngoại, unique constraint hoặc logic bảo vệ các quy tắc nghiệp vụ phức tạp. Ví dụ, hai transaction có thể đọc cùng một tổng hợp nhưng ghi vào hai hàng khác nhau; nếu quy tắc nghiệp vụ phụ thuộc vào tổng đó, ứng dụng vẫn phải thiết kế transaction và ràng buộc phù hợp.

## 2. Ví dụ hai transaction xung đột

Giả sử hệ thống chạy Group Replication ở chế độ multi-primary và hai ứng dụng cùng đặt hàng cho một SKU. Cả hai kết nối đến các member khác nhau và đọc thấy số lượng còn lại là 1.

~~~sql
-- Transaction T1 trên member A
START TRANSACTION;
SELECT quantity FROM inventory WHERE sku = 'SKU-100';
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'SKU-100';

-- Transaction T2 trên member B
START TRANSACTION;
SELECT quantity FROM inventory WHERE sku = 'SKU-100';
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'SKU-100';
~~~

Hai transaction đều thay đổi cùng khóa SKU-100. Khi commit, transaction được chứng nhận trước có thể hoàn tất; transaction còn lại bị từ chối vì writeset xung đột. Transaction thua bị rollback và không được coi là một lần đặt hàng thành công.

Ứng dụng phải thực hiện lại toàn bộ transaction từ đầu. Khi đọc lại số lượng sau transaction đầu tiên, ứng dụng có thể thấy hàng đã hết và trả kết quả hết hàng. Nếu chỉ lặp lại câu lệnh COMMIT hoặc tiếp tục từ câu lệnh cuối, logic nghiệp vụ sẽ dùng dữ liệu đọc cũ và có thể tạo ra kết quả sai.

### Cách viết thao tác cập nhật an toàn hơn

Thay vì đọc rồi trừ số lượng ở ứng dụng, có thể đưa điều kiện nghiệp vụ vào câu lệnh cập nhật:

~~~sql
UPDATE inventory
SET quantity = quantity - 1,
    updated_at = CURRENT_TIMESTAMP
WHERE sku = 'SKU-100'
  AND quantity > 0;
~~~

Ứng dụng kiểm tra số hàng bị tác động:

- 1: thao tác giữ được một đơn vị hàng.
- 0: SKU không tồn tại hoặc số lượng không còn đủ; ứng dụng cần phân biệt hai trường hợp nếu nghiệp vụ yêu cầu.

Câu lệnh có điều kiện giúp tránh giảm tồn kho xuống số âm. Tuy nhiên, trong multi-primary, hai transaction cùng sửa một SKU vẫn có thể bị certification conflict. Khi gặp lỗi đó, ứng dụng phải chạy lại transaction và đánh giá lại điều kiện với trạng thái mới.

## 3. Single-primary và multi-primary ảnh hưởng thế nào?

Group Replication có hai cách tổ chức ghi dữ liệu:

| Chế độ | Nơi nhận thao tác ghi | Đặc điểm xung đột |
|---|---|---|
| Single-primary | Một member giữ vai trò primary nhận ghi tại một thời điểm | Giảm xung đột ghi phát sinh do nhiều member cùng ghi, nhưng vẫn có deadlock và các lỗi transaction thông thường |
| Multi-primary | Nhiều member có thể nhận ghi | Các transaction sửa cùng khóa trên nhiều member có thể cạnh tranh ở bước certification |

Trong single-primary, các transaction ghi được tập trung về một node. InnoDB xử lý cạnh tranh cục bộ bằng khóa và deadlock detection; certification vẫn là một phần của cơ chế nhóm. Khi primary chuyển đổi, ứng dụng cần định tuyến lại kết nối và xử lý các transaction bị gián đoạn.

Trong multi-primary, khả năng ghi trên nhiều member tăng tính linh hoạt nhưng cũng tăng nguy cơ hai transaction đồng thời sửa cùng dữ liệu. Các bảng có tần suất ghi cao vào cùng một khóa, chẳng hạn bộ đếm, số dư hoặc tồn kho của một SKU phổ biến, dễ trở thành điểm nóng.

Lựa chọn chế độ cần dựa trên mô hình ghi thực tế. Nếu phần lớn giao dịch cập nhật cùng các hàng hoặc có nhiều quy tắc nghiệp vụ phụ thuộc lẫn nhau, single-primary thường dễ vận hành hơn. Nếu dùng multi-primary, cần thiết kế phân vùng nghiệp vụ hoặc định tuyến để giảm khả năng nhiều member ghi cùng khóa.

## 4. Nhận diện lỗi certification ở ứng dụng

Một dấu hiệu điển hình là transaction đã thực thi các câu lệnh nhưng lỗi xuất hiện ở lệnh COMMIT. Với Group Replication, lỗi thường gặp là:

- **3101 — ER_TRANSACTION_ROLLBACK_DURING_COMMIT:** transaction bị hủy trong lúc commit do xung đột với transaction đồng thời; thông báo thường yêu cầu thử lại.

Ví dụ minh họa:

~~~sql
START TRANSACTION;
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'SKU-100';

COMMIT;
-- Có thể nhận lỗi 3101 khi certification phát hiện xung đột
~~~

Không phải mọi lỗi xuất hiện tại COMMIT đều là certification conflict. Ứng dụng cần phân loại theo mã lỗi và trạng thái kết nối, không chỉ dựa vào vị trí lỗi.

### Phân biệt các lỗi thường gặp

| Lỗi | Nguyên nhân thường gặp | Hành động |
|---|---|---|
| 3101 | Transaction bị từ chối ở bước certification | Thực hiện lại toàn bộ transaction |
| 1213 | InnoDB phát hiện deadlock và chọn transaction làm nạn nhân | Thực hiện lại toàn bộ transaction nếu thao tác còn hợp lệ |
| 1205 | Hết thời gian chờ khóa | Rollback transaction theo chính sách ứng dụng rồi cân nhắc retry |
| 1062 | Vi phạm unique constraint | Xử lý theo quy tắc nghiệp vụ; thường không retry mù |
| Mất kết nối khi commit | Không chắc server đã commit hay chưa | Kiểm tra kết quả bằng idempotency key hoặc trạng thái nghiệp vụ trước khi gửi lại |

Với lỗi 1205, tùy cấu hình innodb_rollback_on_timeout, MySQL có thể chỉ rollback statement gây timeout thay vì toàn transaction. Vì vậy, lớp quản lý transaction của ứng dụng nên chủ động rollback toàn bộ transaction trước khi retry để bắt đầu từ trạng thái sạch.

Lỗi mất kết nối trong lúc commit đặc biệt quan trọng: server có thể đã commit nhưng phản hồi không đến được client. Đây là kết quả không xác định đối với ứng dụng. Không đưa lỗi này vào danh sách retry tự động như một certification conflict thông thường.

## 5. Retry phải bắt đầu lại toàn bộ transaction

Khi nhận lỗi certification, transaction hiện tại đã bị hủy. Retry đúng nghĩa là:

1. Kết thúc và giải phóng trạng thái transaction hiện tại.
2. Mở một transaction mới.
3. Đọc lại dữ liệu cần thiết.
4. Kiểm tra lại điều kiện nghiệp vụ.
5. Thực hiện lại toàn bộ thao tác ghi.
6. Commit và chỉ trả thành công khi commit được xác nhận.

Không chỉ retry câu lệnh cuối. Không tái sử dụng kết quả đọc từ transaction đã bị hủy, vì dữ liệu có thể đã thay đổi trong nhóm.

### Pseudocode

~~~text
for attempt from 1 to MAX_ATTEMPTS:
    begin a new transaction
    try:
        read current business state
        validate business rules
        execute all writes
        commit
        return success
    catch a known retryable transaction error:
        rollback and release transaction state
        if attempt reached MAX_ATTEMPTS:
            return a retryable failure to caller
        wait with bounded exponential backoff and jitter
        continue with a new transaction
    catch any other error:
        rollback if needed
        return or raise the error
~~~

Ví dụ Java JDBC rút gọn:

~~~java
int maxAttempts = 4;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            reserveInventory(connection, sku, quantity);
            createOrder(connection, requestId, sku, quantity);
            connection.commit();
            return;
        } catch (SQLException error) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                error.addSuppressed(rollbackError);
            }

            int code = error.getErrorCode();
            boolean retryable =
                code == 3101 || // Group Replication certification
                code == 1213 || // InnoDB deadlock
                code == 1205;   // Lock wait timeout

            if (!retryable || attempt == maxAttempts) {
                throw error;
            }
        }
    }

    // Chờ một khoảng tăng dần, có thêm jitter trước lần thử tiếp theo.
    backoffWithJitter(attempt);
}
~~~

Đây là khung minh họa; reserveInventory, createOrder và backoffWithJitter là hàm của ứng dụng. Trong triển khai thực tế, cần giữ thời gian giữ connection ngắn, phân loại cả chuỗi exception nếu driver bọc lỗi, và bảo đảm connection bị lỗi được loại khỏi pool khi trạng thái của nó không còn đáng tin cậy.

## 6. Chọn chính sách retry có giới hạn

Retry có thể giúp vượt qua xung đột tạm thời, nhưng retry liên tục cũng làm tăng tải và khiến điểm nóng trở nên nghiêm trọng hơn. Chính sách cần có giới hạn rõ ràng.

### Số lần thử

Đặt số lần thử tối đa nhỏ, chẳng hạn 3–5 lần tùy SLA và độ dài transaction. Khi hết số lần, trả lỗi có thể xử lý được cho tầng gọi phía trên hoặc đưa yêu cầu vào hàng đợi thử lại. Không lặp vô hạn trong một request đồng bộ.

### Exponential backoff và jitter

Khoảng chờ tăng dần làm giảm khả năng các request xung đột thử lại cùng một thời điểm:

**delay = min(maxDelay, baseDelay × 2^(attempt - 1)) + randomJitter**

Ví dụ, với base delay 20 ms và max delay 250 ms, các lần thử sẽ có khoảng chờ tăng dần nhưng không vượt ngưỡng đã chọn. Jitter ngẫu nhiên giúp phân tán các lần retry của nhiều client.

Chọn giá trị theo latency mục tiêu. Transaction ngắn và hệ thống tải cao có thể cần khoảng chờ tính bằng mili giây; quy trình nền có thể chấp nhận khoảng chờ dài hơn.

### Retry chỉ với lỗi có thể phục hồi

Nên giới hạn retry tự động cho các lỗi được xác định là tạm thời như certification conflict 3101, deadlock 1213 và lock wait timeout 1205 sau khi rollback toàn transaction. Các lỗi dữ liệu như sai kiểu, vi phạm ràng buộc, thiếu quyền hoặc schema không tương thích cần được xử lý theo nguyên nhân.

Ghi metric cho số lần retry, mã lỗi, số lần thất bại cuối cùng và thời gian chờ. Nếu tỷ lệ retry tăng nhanh, đó có thể là dấu hiệu điểm nóng, transaction quá dài hoặc định tuyến ghi chưa phù hợp.

## 7. Idempotency và tác dụng phụ ngoài database

Retry có thể khiến cùng một yêu cầu nghiệp vụ được gửi đến ứng dụng nhiều lần. Một thao tác như tạo đơn hàng, thu tiền hoặc gửi yêu cầu sang dịch vụ khác phải được thiết kế idempotent để không tạo tác dụng phụ trùng lặp.

### Dùng idempotency key

Mỗi yêu cầu nghiệp vụ có một mã duy nhất do client hoặc hệ thống điều phối tạo ra. Lưu mã này cùng kết quả trong cùng transaction:

~~~sql
CREATE TABLE processed_requests (
  request_id VARCHAR(64) PRIMARY KEY,
  result_code VARCHAR(32) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
~~~

Khi xử lý yêu cầu, ứng dụng kiểm tra hoặc ghi request_id trong cùng transaction với thay đổi nghiệp vụ. Nếu request đã hoàn tất, trả lại kết quả đã lưu thay vì tạo đơn hàng hoặc trừ tồn kho lần nữa. Unique key trên request_id giúp bảo vệ trường hợp nhiều request trùng nhau đến đồng thời.

Việc kiểm tra và ghi idempotency key phải nằm trong cùng transaction với dữ liệu nghiệp vụ. Nếu ghi key sau khi commit đơn hàng, lỗi giữa hai bước có thể khiến lần retry không biết yêu cầu đã hoàn tất hay chưa.

### Không gọi dịch vụ ngoài trong transaction retry

Tránh gửi email, gọi cổng thanh toán hoặc phát message trực tiếp giữa transaction có thể bị retry. Nếu transaction bị rollback, tác dụng phụ ngoài database không tự được thu hồi.

Một mẫu phù hợp là transactional outbox:

1. Trong cùng transaction, ghi thay đổi nghiệp vụ và một bản ghi sự kiện vào bảng outbox.
2. Commit transaction.
3. Worker riêng đọc outbox và gửi message hoặc gọi dịch vụ bên ngoài.
4. Worker đánh dấu sự kiện đã xử lý bằng một định danh idempotent.

Nhờ đó, transaction có thể được retry mà không gửi trùng email hoặc lệnh thanh toán ngay trong lần thử chưa commit.

## 8. Thiết kế transaction để giảm xung đột

Ứng dụng có thể giảm tần suất certification conflict bằng cách giảm vùng ghi giao nhau và rút ngắn thời gian transaction:

- Giữ transaction ngắn; không thực hiện gọi HTTP, chờ người dùng hoặc xử lý file trong khi transaction đang mở.
- Cập nhật các hàng liên quan theo thứ tự khóa ổn định khi có thể, giảm nguy cơ deadlock.
- Dùng primary key và unique key rõ ràng trên bảng được replicate.
- Tránh cập nhật một hàng bộ đếm toàn cục từ nhiều member.
- Phân vùng dữ liệu theo tenant, tài khoản hoặc vùng nghiệp vụ để cùng một khóa thường được xử lý trên một writer.
- Cân nhắc single-primary nếu workload có nhiều thao tác ghi vào cùng dữ liệu.
- Dùng câu lệnh cập nhật có điều kiện và constraint để bảo vệ quy tắc nghiệp vụ ở database.

### Xử lý điểm nóng

Giả sử một bảng lưu tổng số lượt truy cập:

~~~sql
UPDATE global_counter
SET counter_value = counter_value + 1
WHERE counter_name = 'all_requests';
~~~

Nếu nhiều member multi-primary cùng cập nhật một hàng, writeset sẽ thường xuyên trùng nhau. Có thể giảm cạnh tranh bằng cách chia bộ đếm theo member hoặc theo bucket, sau đó tổng hợp khi đọc:

~~~sql
CREATE TABLE request_counter (
  bucket_id INT PRIMARY KEY,
  counter_value BIGINT NOT NULL
) ENGINE=InnoDB;
~~~

Ứng dụng chọn bucket theo một quy tắc ổn định, ví dụ hash của tenant hoặc một phân vùng nghiệp vụ. Thiết kế này chỉ phù hợp nếu nghiệp vụ chấp nhận tổng hợp nhiều bucket và không yêu cầu một phép cập nhật nguyên tử trên một bộ đếm duy nhất.

## 9. Quan sát và đo lường xung đột

Không nên chỉ quan sát số lần retry ở log ứng dụng. Kết hợp metric từ ứng dụng, trạng thái Group Replication và log máy chủ để xác định nguồn xung đột.

### Ở tầng ứng dụng

Ghi nhận:

- Tổng số transaction commit thành công và thất bại.
- Số lần retry theo mã lỗi 3101, 1213, 1205.
- Tỷ lệ request phải retry và số lần thử trung bình.
- Thời gian từ lần bắt đầu đến commit thành công.
- Bảng, loại thao tác và nhóm nghiệp vụ liên quan, tránh ghi dữ liệu nhạy cảm.
- Số yêu cầu vượt quá số lần retry tối đa.

### Ở tầng MySQL

Kiểm tra trạng thái nhóm:

~~~sql
SELECT
  MEMBER_ID,
  MEMBER_HOST,
  MEMBER_PORT,
  MEMBER_STATE,
  MEMBER_ROLE
FROM performance_schema.replication_group_members;
~~~

Kiểm tra thống kê member:

~~~sql
SELECT *
FROM performance_schema.replication_group_member_stats;
~~~

Các bảng Performance Schema và cột khả dụng có thể thay đổi theo phiên bản. Dùng DESCRIBE performance_schema.replication_group_member_stats để xem cấu trúc trên máy chủ cụ thể. Theo dõi cả hàng đợi applier, transaction bị từ chối và trạng thái member; tên metric chi tiết phụ thuộc phiên bản.

Nếu tỷ lệ conflict cao, phân tích xem các transaction có cùng khóa hoặc cùng bảng hay không. Một nhóm nhỏ khóa xuất hiện lặp lại thường chỉ ra hotspot. Nếu conflict tăng đồng thời với transaction dài, hãy xem lại số câu lệnh, thời gian giữ khóa và thao tác ngoài database nằm trong transaction.

## 10. Kiểm thử retry trước khi triển khai

Tạo bài kiểm thử có kiểm soát để xác nhận ứng dụng thực sự retry toàn transaction:

1. Dựng một Group Replication test group với ít nhất hai member có thể nhận ghi nếu thử multi-primary.
2. Tạo bảng có primary key và một hàng được nhiều transaction cập nhật.
3. Từ hai client, bắt đầu transaction gần như đồng thời và cập nhật cùng một khóa.
4. Commit ở cả hai member; quan sát transaction thắng và lỗi certification ở transaction còn lại.
5. Xác nhận ứng dụng mở transaction mới, đọc lại dữ liệu và kiểm tra quy tắc nghiệp vụ.
6. Gửi lại cùng một request ID để kiểm tra idempotency.
7. Tạo tình huống deadlock hoặc lock wait timeout để xác nhận bộ phân loại lỗi.
8. Mô phỏng mất kết nối tại thời điểm commit và xác nhận ứng dụng không retry mù khi kết quả chưa rõ.

Không chạy thử nghiệm gây xung đột trên hệ thống production. Trong môi trường kiểm thử, lưu mã lỗi, thời gian commit, số lần retry và trạng thái cuối cùng của dữ liệu để đối chiếu.

## 11. Checklist xử lý certification conflict

**Khi nhận lỗi**

- [ ] Đã ghi lại mã lỗi và xác định có phải lỗi 3101 không.
- [ ] Đã xác nhận transaction bị hủy và không dùng lại dữ liệu đọc cũ.
- [ ] Đã rollback hoặc giải phóng trạng thái transaction/connection.
- [ ] Đã phân biệt lỗi certification, deadlock, lock timeout và mất kết nối commit.

**Khi retry**

- [ ] Retry toàn bộ transaction từ đầu.
- [ ] Dùng số lần thử tối đa và exponential backoff có jitter.
- [ ] Kiểm tra lại điều kiện nghiệp vụ trong transaction mới.
- [ ] Bảo vệ request bằng idempotency key.
- [ ] Không phát tác dụng phụ ngoài database trước khi commit.

**Khi tỷ lệ xung đột tăng**

- [ ] Đã xác định bảng và khóa thường xuyên xung đột.
- [ ] Đã kiểm tra transaction dài và hotspot.
- [ ] Đã xem lại định tuyến ghi và lựa chọn single-primary/multi-primary.
- [ ] Đã xác nhận primary key và unique constraint trên các bảng replicate.
- [ ] Đã đo tỷ lệ retry, latency và số lần thất bại cuối cùng.

## Kết luận

Certification conflict là một phần trong cơ chế bảo đảm thứ tự transaction của Group Replication. Lỗi có thể chỉ xuất hiện khi commit, dù các câu lệnh trước đó đã chạy thành công tại member nhận yêu cầu. Ứng dụng cần nhận diện lỗi 3101, rollback trạng thái hiện tại và retry toàn bộ transaction với dữ liệu mới, giới hạn số lần thử và backoff có jitter. Idempotency key cùng transactional outbox bảo vệ tác dụng phụ nghiệp vụ. Nếu conflict xảy ra thường xuyên, hãy xử lý nguyên nhân từ hotspot, thời lượng transaction và mô hình định tuyến ghi thay vì chỉ tăng số lần retry.
