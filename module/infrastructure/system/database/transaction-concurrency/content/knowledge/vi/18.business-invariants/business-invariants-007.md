# Bộ đếm, số thứ tự và các điểm nóng ghi dữ liệu

Bộ đếm (counter) và số thứ tự (sequence) xuất hiện trong nhiều nghiệp vụ: số lượng tồn kho, số lượt sử dụng, số hóa đơn, mã đơn hàng, số thứ tự sự kiện và ID của bản ghi. Chúng thường trông như những giá trị đơn giản, nhưng khi nhiều transaction cùng cập nhật, chúng có thể trở thành điểm nóng ghi dữ liệu (write hotspot).

Một bộ đếm tập trung trên một hàng khiến mọi transaction muốn tăng giá trị đều phải phối hợp qua cùng tài nguyên. Điều đó bảo vệ thứ tự cập nhật, nhưng cũng buộc các writer xếp hàng. Một sequence chuyên dụng có thể cấp số cho nhiều transaction mà không phải cập nhật một hàng nghiệp vụ dùng chung. Đổi lại, sequence thường cho phép khoảng trống và không bảo đảm số đã cấp phản ánh thứ tự commit.

Thiết kế đúng bắt đầu từ câu hỏi nghiệp vụ: cần một giá trị duy nhất, một bộ đếm chính xác, một thứ tự tăng dần, hay một số liên tục không có khoảng trống? Các yêu cầu này khác nhau và dẫn đến cơ chế đồng thời khác nhau.

## 1. Counter và sequence giải quyết những nhu cầu nào?

**Counter** là giá trị được tăng hoặc giảm theo các thao tác nghiệp vụ. Ví dụ:

- Số sản phẩm còn trong kho.
- Số lượt tải hoặc lượt xem.
- Số chỗ đã được đặt.
- Số request đã sử dụng trong một quota.
- Số lượng item trong một nhóm.

Counter thường là một phần của trạng thái nghiệp vụ. Nếu hai transaction cùng tăng hoặc giảm nó, kết quả phải phản ánh cả hai thay đổi.

**Sequence** là cơ chế cấp các giá trị khác nhau theo một thứ tự tăng hoặc theo quy tắc cấp phát của DBMS. Nó thường được dùng để tạo ID, số tham chiếu hoặc số thứ tự kỹ thuật.

Ví dụ, một bảng đơn hàng có thể dùng sequence để tạo order_id. Việc cấp ID không nhất thiết phải là một phần của nghiệp vụ tạo đơn; sequence có thể đã cấp số ngay cả khi transaction tạo đơn sau đó rollback.

| Nhu cầu | Ý nghĩa | Câu hỏi cần xác định |
|---|---|---|
| Counter nghiệp vụ | Giá trị phản ánh trạng thái hiện tại | Mỗi thay đổi có phải được áp dụng chính xác không? |
| ID duy nhất | Phân biệt một bản ghi | Có cần liên tục hay chỉ cần không trùng? |
| Sequence tăng dần | Cấp số theo một thứ tự | Thứ tự cấp số có cần trùng thứ tự commit không? |
| Số hóa đơn liên tục | Quy tắc đánh số nghiệp vụ | Có thật sự bắt buộc không có khoảng trống không? |
| Bộ đếm lượt xem | Thống kê số lần xảy ra | Cần chính xác tức thời hay có thể tổng hợp trễ? |

Không nên dùng một cơ chế duy nhất cho tất cả các yêu cầu. Ví dụ, sequence rất phù hợp để tạo ID duy nhất, nhưng không tự bảo đảm số hóa đơn liên tục hoặc tổng số hàng tồn kho chính xác.

## 2. Vì sao một hàng counter trở thành write hotspot?

Giả sử ứng dụng lưu số lượt sử dụng trong một hàng:

~~~sql
CREATE TABLE usage_counters (
    counter_name VARCHAR(100) PRIMARY KEY,
    counter_value BIGINT NOT NULL
);

INSERT INTO usage_counters (counter_name, counter_value)
VALUES ('downloads', 0);
~~~

Mỗi request tăng counter:

~~~sql
UPDATE usage_counters
SET counter_value = counter_value + 1
WHERE counter_name = 'downloads';
~~~

Câu UPDATE là nguyên tử. DBMS điều phối các transaction ghi cùng hàng để các lần tăng không ghi đè lên nhau. Nhưng mọi request đều nhắm vào cùng một hàng có khóa chính downloads.

Nếu 5.000 request đồng thời tăng counter này, chúng phải lần lượt lấy quyền cập nhật hàng đó. Những request khác có thể chờ khóa ghi. Hàng counter trở thành điểm tranh chấp nóng, dù mỗi câu UPDATE chỉ thay đổi một số nguyên.

Đây là sự đánh đổi giữa tính chính xác tức thời và khả năng ghi song song:

- Một hàng duy nhất giúp có một giá trị chính xác tại thời điểm đọc sau khi các transaction liên quan hoàn tất.
- Mọi writer cùng cập nhật hàng đó phải phối hợp.
- Khi tốc độ ghi tăng, thời gian chờ khóa và độ trễ có thể tăng theo.
- Thêm CPU hoặc connection không loại bỏ được điểm tuần tự hóa trên cùng một hàng.

### Minh họa các writer cùng tranh chấp

~~~text
Request A ----\
Request B -----\
Request C ------> [counter: downloads] ---> các lần cập nhật lần lượt
Request D -----/
Request E ----/

Nhiều request cùng cần ghi một hàng.
~~~

Write hotspot không nhất thiết là deadlock. Thường chỉ có một transaction giữ khóa và các transaction khác chờ. Deadlock cần một vòng chờ giữa nhiều tài nguyên; một hàng nóng đơn lẻ thường tạo lock queue hoặc lock contention.

## 3. Cập nhật counter nguyên tử để tránh lost update

Một lỗi thường gặp là đọc counter về ứng dụng, tăng trong bộ nhớ rồi ghi giá trị mới:

~~~sql
SELECT counter_value
FROM usage_counters
WHERE counter_name = 'downloads';

-- Ứng dụng cộng thêm 1 rồi gửi giá trị tuyệt đối.
UPDATE usage_counters
SET counter_value = 101
WHERE counter_name = 'downloads';
~~~

Nếu hai request cùng đọc 100, cả hai có thể cùng ghi 101. Một lần tăng bị mất.

Hãy để phép tăng diễn ra ngay trong câu UPDATE:

~~~sql
UPDATE usage_counters
SET counter_value = counter_value + 1
WHERE counter_name = 'downloads';
~~~

Trong PostgreSQL, có thể lấy giá trị mới bằng RETURNING:

~~~sql
UPDATE usage_counters
SET counter_value = counter_value + 1
WHERE counter_name = 'downloads'
RETURNING counter_value;
~~~

DBMS điều phối các writer trên hàng và tính biểu thức từ giá trị hiện tại theo ngữ nghĩa cập nhật của hệ quản trị. Ứng dụng không cần gửi lại một giá trị tuyệt đối đã tính từ lần đọc cũ.

Nếu counter phải nằm trong một giới hạn, đặt điều kiện ngay trong câu UPDATE:

~~~sql
UPDATE usage_counters
SET counter_value = counter_value + 1
WHERE counter_name = 'active_sessions'
  AND counter_value < 1000
RETURNING counter_value;
~~~

Nếu trả về một hàng, request đã chiếm được một đơn vị quota. Nếu không có hàng nào, counter không tồn tại hoặc giới hạn đã đạt. Ứng dụng cần phân biệt các trường hợp theo mô hình dữ liệu và kiểm tra bổ sung khi cần.

Có thể bổ sung CHECK constraint để bảo vệ miền giá trị:

~~~sql
ALTER TABLE usage_counters
ADD CONSTRAINT usage_counter_nonnegative
CHECK (counter_value >= 0);
~~~

Câu UPDATE có điều kiện bảo vệ quyết định tăng trong giới hạn; CHECK constraint ngăn mọi đường ghi commit giá trị âm.

## 4. Counter nghiệp vụ khác ID sequence

Hai ví dụ dưới đây có vẻ giống nhau vì đều tạo ra số tăng dần, nhưng yêu cầu đồng thời khác nhau.

### Counter cần phản ánh mọi thay đổi

Ví dụ số lượng tồn kho:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 101
  AND quantity > 0
RETURNING quantity;
~~~

Nếu hai khách hàng cùng mua sản phẩm cuối cùng, DBMS điều phối các lần cập nhật. Chỉ một transaction có thể giảm quantity từ 1 xuống 0; transaction còn lại sau khi chờ sẽ không còn thỏa điều kiện quantity > 0 và không cập nhật hàng.

Ở đây counter chính là trạng thái nghiệp vụ. Không thể cấp một số rồi bỏ qua việc cập nhật tồn kho thật.

### Sequence chỉ cần cấp giá trị duy nhất

Ví dụ PostgreSQL:

~~~sql
CREATE SEQUENCE order_id_seq
    START WITH 1000
    INCREMENT BY 1;

INSERT INTO orders (order_id, customer_id, status)
VALUES (nextval('order_id_seq'), 42, 'NEW');
~~~

Sequence cấp giá trị cho từng request mà không cần mọi transaction cập nhật cùng một hàng counter trong bảng orders. DBMS có cơ chế cấp phát riêng để hỗ trợ nhiều session.

ID 1000 có thể được cấp cho transaction A và ID 1001 cho transaction B. Nếu A rollback, ID 1000 vẫn có thể bị bỏ trống. Sequence không phải bộ đếm số hàng đã commit.

### Không dùng MAX(id) + 1 để cấp số

Mẫu sau không an toàn khi có nhiều transaction:

~~~sql
SELECT MAX(order_id) + 1
FROM orders;
~~~

Hai transaction có thể cùng đọc MAX(order_id) = 999 và cùng tính 1000. Nếu cột có PRIMARY KEY/UNIQUE, một transaction sẽ thất bại vì trùng khóa. Nếu thiếu constraint, dữ liệu có thể bị trùng.

Thêm khóa hoặc isolation có thể khiến truy vấn phức tạp hơn, nhưng sequence/identity hoặc một cơ chế cấp số có đồng bộ thường là lựa chọn đúng. Không dùng MAX(id) + 1 như một bộ cấp ID đồng thời.

## 5. Sequence có thể có khoảng trống

Một sequence thông thường bảo đảm cấp các giá trị khác nhau theo quy tắc của nó, nhưng không bảo đảm không có khoảng trống.

Các nguyên nhân phổ biến:

- Transaction lấy số rồi rollback.
- Ứng dụng lấy số nhưng không sử dụng.
- Transaction bị lỗi sau khi đã gọi hàm cấp số.
- DBMS cache một nhóm giá trị và tiến trình dừng bất ngờ.
- Nhiều session lấy số theo thứ tự khác với thứ tự commit.

Ví dụ:

~~~text
Transaction A: lấy nextval -> 1000
Transaction B: lấy nextval -> 1001
Transaction B: INSERT và COMMIT
Transaction A: ROLLBACK

Bảng có order_id = 1001.
Số 1000 đã được cấp nhưng không có hàng đơn hàng tương ứng.
~~~

Đây là hành vi bình thường của sequence. Sequence ưu tiên cấp giá trị hiệu quả và an toàn cho nhiều session, không phải quản lý một dãy số không bao giờ thiếu.

### Sequence không biểu diễn thứ tự commit

Giả sử A lấy số 1000 rồi xử lý lâu. B lấy số 1001 và commit trước A. Sau đó A mới commit.

Khi đọc bảng, order_id 1001 có thể đã tồn tại trước order_id 1000. Vì vậy:

- ID lớn hơn không nhất thiết commit sau.
- ID nhỏ hơn không nhất thiết được nhìn thấy trước.
- Sequence không phải timestamp.
- Sequence không phải bằng chứng về thứ tự hoàn tất nghiệp vụ.

Nếu cần thứ tự sự kiện, cần xác định phạm vi thứ tự và cơ chế ghi nhận phù hợp, chẳng hạn sequence theo partition, log tuần tự hoặc timestamp có hợp đồng rõ ràng. Một sequence toàn cục cũng không tự tạo ra thứ tự commit toàn cục.

## 6. Tại sao sequence thường mở rộng tốt hơn một counter row?

Một counter row trong bảng nghiệp vụ cần transaction cập nhật hàng đó và giữ khóa trong thời gian transaction. Một sequence chuyên dụng có thể cấp giá trị qua cơ chế nội bộ tối ưu cho cấp phát đồng thời, thường có thể cache giá trị để giảm thao tác đồng bộ.

So sánh:

| Tiêu chí | Một counter row | Sequence/identity |
|---|---|---|
| Mục đích | Trạng thái nghiệp vụ hoặc số đếm | Cấp giá trị định danh/số thứ tự |
| Writer cùng lúc | Tranh chấp cùng hàng | DBMS dùng cơ chế cấp phát sequence |
| Rollback | UPDATE counter trong transaction có thể rollback | Giá trị đã lấy thường không được trả lại |
| Khoảng trống | Có thể tránh mất số do rollback nếu counter cập nhật trong cùng transaction, nhưng vẫn có thể phát sinh từ nghiệp vụ khác | Có thể có khoảng trống là đặc tính bình thường |
| Thứ tự commit | Không tự bảo đảm | Không tự bảo đảm |
| Đọc giá trị hiện tại | Giá trị trạng thái counter | Giá trị sequence đã cấp tùy API/session |
| Phù hợp | Quota, tồn kho, số lượng chính xác | ID duy nhất, mã kỹ thuật không yêu cầu liên tục |

Không thể thay một counter tồn kho bằng sequence. Sequence có thể cấp số cho từng yêu cầu mua, nhưng không tự quyết định còn bao nhiêu hàng trong kho.

Ngược lại, không nên dùng một hàng counter duy nhất để cấp ID kỹ thuật cho hàng triệu transaction mỗi giây nếu DBMS có sequence hoặc cơ chế ID chuyên dụng.

## 7. Khi nào cần số liên tục không có khoảng trống?

Một số nghiệp vụ yêu cầu dãy số liên tục trong một phạm vi, chẳng hạn số chứng từ theo kỳ hoặc số hóa đơn theo quy định nội bộ. Trước khi thiết kế, cần xác nhận yêu cầu thực sự là:

- Số duy nhất, không cần liên tục.
- Số tăng dần, có thể có khoảng trống.
- Số liên tục trong phạm vi một tenant/năm/loại chứng từ.
- Số liên tục của các chứng từ đã phát hành, với chứng từ hủy vẫn phải được lưu dấu vết.

Nếu chỉ cần ID duy nhất, sequence là lựa chọn đơn giản. Nếu bắt buộc không có khoảng trống trong các số đã phát hành, cần một giao thức cấp số được tuần tự hóa và gắn với transaction nghiệp vụ.

### Counter row cấp số trong transaction

Ví dụ bảng bộ đếm theo năm:

~~~sql
CREATE TABLE document_number_counters (
    document_year INT PRIMARY KEY,
    last_number BIGINT NOT NULL
);
~~~

Trong cùng transaction tạo chứng từ:

~~~sql
BEGIN;

UPDATE document_number_counters
SET last_number = last_number + 1
WHERE document_year = 2026
RETURNING last_number;

-- Dùng số trả về để INSERT chứng từ.
INSERT INTO documents (document_year, document_number, status)
VALUES (2026, :allocated_number, 'ISSUED');

COMMIT;
~~~

UPDATE khóa hàng counter cho đến khi transaction kết thúc. Transaction khác cấp số trong cùng năm phải chờ. Nếu transaction đầu rollback, thay đổi counter cũng rollback, nên số chưa commit có thể được dùng lại.

Để cách này đúng, cần bảo đảm:

- Counter row tồn tại trước khi cấp số.
- Mọi đường phát hành chứng từ đều dùng cùng giao thức.
- UNIQUE(document_year, document_number) bảo vệ tính duy nhất.
- Số chỉ được xem là phát hành khi transaction tạo chứng từ commit.
- Không xóa chứng từ đã phát hành; nếu hủy, lưu trạng thái hủy để giữ dấu vết số đã cấp.
- Không gửi số ra hệ thống ngoài trước khi biết transaction đã commit, trừ khi có cơ chế idempotency/reconciliation.

Đổi lại, mọi lần cấp số trong cùng phạm vi đều tranh chấp một hàng. Đây là điểm tuần tự hóa có chủ ý. Nếu lưu lượng cao, cần cân nhắc chia phạm vi theo kỳ hoặc chấp nhận số không liên tục.

### Số liên tục có chi phí đồng thời

Muốn không có khoảng trống do rollback, transaction phải giữ quyền cấp số cho đến khi biết bản ghi nghiệp vụ có commit hay không. Điều này khiến transaction sau chờ transaction trước.

Nếu transaction cấp số mở lâu, mọi request cùng phạm vi có thể xếp hàng. Không nên gọi dịch vụ bên ngoài hoặc chờ người dùng trong khi đang giữ khóa counter. Số liên tục và khả năng cấp phát song song cao là hai mục tiêu thường xung đột.

## 8. Giảm hotspot bằng counter theo phạm vi

Nếu nghiệp vụ không cần một counter toàn cục, có thể chia counter theo tenant, loại sự kiện, ngày hoặc partition.

Ví dụ:

~~~sql
CREATE TABLE tenant_counters (
    tenant_id BIGINT PRIMARY KEY,
    value BIGINT NOT NULL
);
~~~

Mỗi tenant có một hàng counter riêng:

~~~sql
UPDATE tenant_counters
SET value = value + 1
WHERE tenant_id = :tenant_id
RETURNING value;
~~~

Request của tenant A và tenant B có thể cập nhật hai hàng khác nhau, nên không phải tranh chấp cùng một khóa hàng. Nhưng mọi request của tenant A vẫn có thể tranh chấp hàng của tenant A.

Cách này phù hợp khi số thứ tự có phạm vi theo tenant hoặc một tài nguyên nghiệp vụ. Nó không tạo một sequence toàn cục. Nếu hai tenant cùng cấp số 1, mã kết hợp phải bao gồm tenant_id để duy nhất:

~~~sql
UNIQUE (tenant_id, value)
~~~

### Partition theo thời gian

Một bộ đếm theo ngày hoặc tháng có thể giảm phạm vi tranh chấp:

~~~sql
CREATE TABLE daily_counters (
    counter_date DATE PRIMARY KEY,
    value BIGINT NOT NULL
);
~~~

Mỗi ngày có một hàng riêng. Các ngày khác nhau không tranh chấp nhau. Tuy nhiên, tại một ngày có tải rất cao, hàng counter ngày đó vẫn là hotspot.

Chọn partition key theo phạm vi nghiệp vụ thật sự. Không chia counter tùy ý nếu caller vẫn cần một số thứ tự duy nhất trên toàn bộ hệ thống.

## 9. Striped counters: tăng thông lượng khi chỉ cần tổng số

Nếu mục tiêu là thống kê lượt xem, số lần tải hoặc số event, đôi khi không cần một hàng tổng duy nhất được cập nhật ngay lập tức. Có thể chia counter thành nhiều stripe (ô đếm), mỗi request chọn một stripe:

~~~sql
CREATE TABLE striped_counters (
    counter_name VARCHAR(100) NOT NULL,
    stripe_id INT NOT NULL,
    value BIGINT NOT NULL,
    PRIMARY KEY (counter_name, stripe_id)
);
~~~

Ví dụ có 32 stripe. Mỗi request chọn một stripe dựa trên hash của request id hoặc một giá trị ngẫu nhiên, rồi tăng stripe đó:

~~~sql
UPDATE striped_counters
SET value = value + 1
WHERE counter_name = 'page_views'
  AND stripe_id = :stripe_id;
~~~

Để lấy tổng:

~~~sql
SELECT SUM(value)
FROM striped_counters
WHERE counter_name = 'page_views';
~~~

Các writer được phân tán trên nhiều hàng thay vì cùng khóa một hàng. Đổi lại, việc đọc tổng cần cộng các stripe và có thể tốn hơn. Nếu tổng được cache hoặc tổng hợp định kỳ, kết quả hiển thị có thể trễ.

### Khi nào không nên dùng striped counter?

Không dùng cách này nếu mỗi lần cập nhật cần kiểm tra một giới hạn toàn cục chính xác, chẳng hạn chỉ cho phép tối đa 100 chỗ đặt trên toàn hệ thống. Nếu mỗi stripe tự kiểm tra một phần hạn mức, tổng hợp có thể vượt giới hạn khi nhiều stripe cùng chấp nhận.

Striped counter phù hợp với thống kê có thể tổng hợp. Với quota hoặc tồn kho chính xác, cần một cơ chế bảo vệ tổng thể như counter/guard row, phân bổ hạn mức trước cho từng partition, hoặc một giao thức reservation.

## 10. Phân bổ theo block bằng hi-lo

Một cách giảm tần suất cập nhật counter tập trung là cấp một dải số cho mỗi node hoặc process. Thay vì xin một số cho từng bản ghi, node lấy trước một block, ví dụ 1.000 số, rồi tự cấp phát trong bộ nhớ.

Bảng allocator:

~~~sql
CREATE TABLE id_allocators (
    allocator_name VARCHAR(100) PRIMARY KEY,
    next_value BIGINT NOT NULL
);
~~~

Cấp block 1.000 số trong một transaction:

~~~sql
UPDATE id_allocators
SET next_value = next_value + 1000
WHERE allocator_name = 'orders'
RETURNING next_value - 1000 AS range_start,
          next_value - 1 AS range_end;
~~~

Nếu trả về [10000, 10999], node có thể tự cấp ID trong khoảng đó mà không phải hỏi DBMS cho từng bản ghi. Node khác lấy block tiếp theo, ví dụ [11000, 11999].

Ưu điểm:

- Giảm số lần ghi vào hàng allocator.
- Giảm lock contention trên bộ cấp ID.
- Có thể cấp ID nhanh trong bộ nhớ.
- Mỗi block có phạm vi riêng, không trùng nhau nếu việc cấp block được thực hiện nguyên tử.

Giới hạn:

- Node có thể dừng khi chưa dùng hết block, tạo khoảng trống.
- Restart cần biết block nào đã được cấp cho node hoặc bỏ block cũ an toàn.
- Không được để hai node cùng dùng một block.
- Nếu node mất trạng thái bộ nhớ, các số chưa dùng có thể bị bỏ.
- Số được cấp trong block không nhất thiết theo thứ tự commit của bản ghi.

Hi-lo phù hợp với ID kỹ thuật không yêu cầu liên tục. Nó không phù hợp với số hóa đơn bắt buộc không có khoảng trống.

## 11. ID phân tán và Snowflake-style ID

Trong hệ thống nhiều node hoặc nhiều database, một sequence trung tâm có thể trở thành phụ thuộc mạng hoặc điểm cấp phát chung. Một lựa chọn là tạo ID phân tán gồm nhiều thành phần:

~~~text
| timestamp | worker/node id | per-millisecond sequence |
~~~

Một ID kiểu Snowflake thường kết hợp:

- Phần thời gian để sắp xếp gần đúng theo thời điểm tạo.
- Worker ID để phân biệt node.
- Sequence nhỏ để tạo nhiều ID trên cùng một node trong cùng đơn vị thời gian.

Cách này cho phép mỗi node tạo ID mà không cần round trip tới một sequence trung tâm cho từng bản ghi.

Nhưng cần xử lý:

- Worker ID phải duy nhất trong phạm vi triển khai.
- Đồng hồ lùi có thể làm ID mất thứ tự hoặc trùng nếu thuật toán không có biện pháp bảo vệ.
- Số lượng ID trên một đơn vị thời gian có giới hạn.
- Timestamp trong ID không phải thứ tự commit chính xác.
- Node restart và cấp lại worker ID phải an toàn.
- ID có thể có khoảng trống và không liên tục.

Snowflake-style ID phù hợp với ID duy nhất phân tán và khả năng sắp xếp gần theo thời gian. Nó không tự thay thế sequence nghiệp vụ hoặc cơ chế đảm bảo số chứng từ liên tục.

## 12. Counter chính xác, counter gần đúng và counter tổng hợp

Không phải mọi bộ đếm đều cần cập nhật đồng bộ trong transaction nghiệp vụ.

### Counter chính xác tức thời

Ví dụ số lượng tồn kho, số chỗ còn lại hoặc số tiền đã sử dụng trong hạn mức. Một quyết định nghiệp vụ phụ thuộc trực tiếp vào giá trị đó. Cần cập nhật nguyên tử và bảo vệ invariant trong DBMS.

### Counter gần đúng hoặc có độ trễ

Ví dụ lượt xem trang, lượt tải hoặc số người đang quan tâm một nội dung. Hệ thống có thể ghi event trước rồi tổng hợp sau. Một số request có thể được gom nhóm hoặc cập nhật theo lô.

Đổi lại, số hiển thị có thể trễ và cần có quy tắc xử lý event trùng, event đến muộn hoặc event bị mất.

### Counter tổng hợp từ dữ liệu gốc

Nếu counter chỉ là thông tin dẫn xuất, có thể tính bằng COUNT/SUM từ bảng sự kiện hoặc bảng chi tiết. Nhưng truy vấn tổng hợp trên lượng dữ liệu lớn có thể tốn kém. Materialized view hoặc bảng aggregate được cập nhật theo batch có thể là lựa chọn.

Khi duy trì aggregate riêng, cần xác định nguồn dữ liệu gốc, cách khôi phục nếu bộ đếm lệch và cơ chế chống áp dụng event hai lần.

| Loại counter | Tính chính xác | Mức đồng bộ | Ví dụ |
|---|---|---|---|
| Counter nghiệp vụ | Phải chính xác khi commit | Đồng bộ trong transaction | Tồn kho, quota, chỗ đặt |
| Counter thống kê | Có thể gần đúng hoặc trễ | Bất đồng bộ/batch | Lượt xem, lượt tải |
| Aggregate | Tùy yêu cầu | Trực tiếp hoặc tổng hợp | Tổng doanh thu, số đơn |
| Sequence ID | Duy nhất theo hợp đồng | Cấp phát riêng | order_id, event_id |

## 13. Đọc counter có thể tạo tải khác với ghi counter

Một counter row nóng không chỉ ảnh hưởng writer. Cách đọc cũng cần cân nhắc:

- Đọc một counter row thường rẻ, nhưng hàng có thể liên tục thay đổi.
- Đọc tổng của nhiều stripe cần SUM và có thể quét nhiều hàng.
- Đọc COUNT(*) từ bảng lớn có thể tốn tài nguyên, tùy index và DBMS.
- Cache giảm tải đọc nhưng có thể trễ.
- Snapshot hoặc replica đọc có thể trả giá trị cũ.
- Một transaction đọc counter rồi ra quyết định phải bảo vệ quyết định đó bằng điều kiện cập nhật/khóa phù hợp.

Ví dụ, không nên đọc số chỗ còn lại rồi kiểm tra ở application trước khi INSERT reservation:

~~~sql
SELECT capacity - reserved_count
FROM events
WHERE event_id = 7;
~~~

Hai transaction có thể cùng đọc còn một chỗ. Hãy cập nhật có điều kiện:

~~~sql
UPDATE events
SET reserved_count = reserved_count + 1
WHERE event_id = 7
  AND reserved_count < capacity
RETURNING reserved_count;
~~~

Nếu có một hàng trả về, chỗ đã được giữ. Nếu không, sự kiện đã hết chỗ hoặc không tồn tại. INSERT reservation cần nằm trong cùng transaction để counter và bản ghi đặt chỗ commit/rollback cùng nhau.

Có thể thêm CHECK constraint:

~~~sql
ALTER TABLE events
ADD CONSTRAINT event_reserved_within_capacity
CHECK (
    reserved_count >= 0
    AND reserved_count <= capacity
);
~~~

Nếu nhiều bảng cùng tham gia, cần bảo đảm mọi đường ghi tuân thủ cùng transaction và constraint cần thiết.

## 14. Các lỗi thiết kế thường gặp

### Dùng SELECT rồi UPDATE giá trị tuyệt đối

Nhiều request cùng đọc một giá trị rồi ghi kết quả tính trong ứng dụng. Các lần tăng có thể ghi đè nhau. Dùng biểu thức counter = counter + delta trong câu UPDATE hoặc version check phù hợp.

### Dùng sequence cho quota

Sequence cấp số khác nhau, nhưng không tự kiểm tra một giới hạn nghiệp vụ. Cần counter hoặc reservation có điều kiện để quyết định còn quota.

### Dùng MAX(id) + 1

Hai transaction có thể tính cùng số. Dùng sequence/identity hoặc bộ cấp số có đồng bộ và constraint UNIQUE.

### Cho rằng sequence không có khoảng trống

Rollback, cache, lỗi ứng dụng và restart có thể làm số đã cấp không được sử dụng. Không dùng sequence nếu yêu cầu thực sự là số phát hành liên tục không có khoảng trống.

### Dùng một hàng toàn cục cho mọi thống kê

Một counter duy nhất trở thành hotspot. Nếu thống kê có thể tổng hợp, cân nhắc striped counters, event log hoặc batch aggregation.

### Chia counter nhưng vẫn yêu cầu giới hạn toàn cục chính xác

Mỗi stripe có thể chấp nhận request trong khi tổng đã vượt quota. Cần phân bổ hạn mức trước hoặc giữ một điểm đồng bộ cho quyết định toàn cục.

### Reset counter trong khi client cũ còn hoạt động

Một token hoặc số thứ tự có thể bị tái sử dụng. Client cũ, cache hoặc message đến muộn có thể nhầm lẫn hai thế hệ giá trị. Nếu cần reset theo kỳ, đưa kỳ vào khóa định danh hoặc tạo phạm vi mới thay vì đặt lại một counter dùng chung một cách tùy tiện.

## 15. Cách quan sát điểm nóng ghi dữ liệu

Khi counter trở thành hotspot, cần đo cả mức tranh chấp lẫn ý nghĩa nghiệp vụ.

Theo dõi:

- Hàng hoặc khóa nào có nhiều transaction chờ nhất.
- Thời gian chờ row/key lock và phân vị p95/p99.
- Số transaction đồng thời cập nhật cùng counter.
- Tỷ lệ deadlock và lock timeout.
- Thời gian transaction giữ khóa.
- Throughput tăng counter theo giây.
- Tỷ lệ retry và số lần retry trung bình.
- Tải ghi lên index và page liên quan.
- Độ trễ đọc tổng counter hoặc aggregate.
- Sai lệch giữa counter lưu sẵn và số liệu tính từ dữ liệu gốc.

Dùng công cụ của DBMS để xác định lock holder, waiter, row/index hoặc sequence liên quan. Nếu counter được cập nhật qua nhiều service, ghi thêm tên nghiệp vụ, tenant/resource id và correlation id để tìm đường ghi.

Đừng nhầm lock contention với latch contention. Lock thường bảo vệ tính nhất quán transaction và có thể tồn tại đến commit. Latch bảo vệ cấu trúc nội bộ trong thời gian ngắn, ví dụ một page index. Cả hai có thể tạo điểm nóng, nhưng cần chẩn đoán bằng công cụ khác nhau.

## 16. Quy trình chọn cơ chế cho counter và sequence

1. **Xác định ý nghĩa**: đây là trạng thái nghiệp vụ, ID duy nhất, số thứ tự hay số liệu thống kê?
2. **Viết invariant**: ví dụ quantity không âm, reserved_count không vượt capacity, hoặc số chứng từ duy nhất trong một năm.
3. **Xác định phạm vi**: toàn cục, theo tenant, theo resource, theo ngày hay theo loại chứng từ?
4. **Chọn tính chất cần bảo đảm**: duy nhất, tăng dần, liên tục, thứ tự commit hay tổng chính xác?
5. **Chọn cơ chế**: atomic UPDATE, sequence/identity, counter row, striped counter, hi-lo hoặc ID phân tán.
6. **Bảo vệ bằng constraint**: PRIMARY KEY, UNIQUE, CHECK và các ràng buộc phù hợp.
7. **Xác định transaction boundary**: counter và bản ghi nghiệp vụ có phải commit/rollback cùng nhau không?
8. **Kiểm thử cạnh tranh**: dùng nhiều connection tăng, giảm, cấp số và rollback đồng thời.
9. **Đo hotspot**: lock wait, throughput, retry, index/page contention và độ trễ đọc.
10. **Thiết kế phục hồi**: cách đối soát, rebuild aggregate, xử lý block ID chưa dùng và request lặp.

## 17. Bảng lựa chọn nhanh

| Yêu cầu | Cơ chế phù hợp | Trade-off chính |
|---|---|---|
| Tăng/giảm tồn kho chính xác | Atomic UPDATE có điều kiện + CHECK | Hàng sản phẩm nóng có thể tranh chấp |
| Giữ quota chính xác | Counter/guard row hoặc reservation nguyên tử | Quyết định toàn cục cần điểm đồng bộ |
| ID duy nhất cho bản ghi | Sequence/identity hoặc ID phân tán | Có thể có khoảng trống |
| Số hóa đơn liên tục trong một kỳ | Counter row theo kỳ trong transaction + UNIQUE | Cấp số bị tuần tự hóa |
| Lượt xem/lượt tải lớn | Striped counter, event log hoặc aggregation | Tổng có thể trễ hoặc cần cộng nhiều stripe |
| Giảm round trip cấp ID | Hi-lo/block allocation | Crash có thể bỏ phần block chưa dùng |
| ID tạo độc lập trên nhiều node | Snowflake-style ID | Cần quản lý worker ID và clock rollback |
| Số thứ tự riêng từng tenant | Counter theo tenant + UNIQUE(tenant_id, number) | Một tenant nóng vẫn có thể tranh chấp |

Counter và sequence đều tạo ra những con số tăng dần, nhưng chúng bảo vệ những điều kiện khác nhau. Counter nghiệp vụ phải giữ đúng trạng thái dưới các cập nhật đồng thời; sequence chủ yếu cấp giá trị định danh duy nhất và thường chấp nhận khoảng trống. Khi một hàng counter trở thành write hotspot, có thể chia phạm vi, dùng striped counter, cấp block hoặc tổng hợp bất đồng bộ nếu nghiệp vụ cho phép. Trước khi tối ưu, hãy xác định rõ cần duy nhất, tăng dần, liên tục hay chính xác tức thời; chính yêu cầu đó quyết định cơ chế phù hợp và mức tranh chấp có thể chấp nhận.
