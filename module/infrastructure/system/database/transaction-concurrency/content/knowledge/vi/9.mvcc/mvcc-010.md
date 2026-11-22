# Vì sao MVCC vẫn cần khóa và vẫn có thể gặp bế tắc

MVCC (Multi-Version Concurrency Control) cho phép nhiều giao dịch cùng truy cập dữ liệu bằng cách duy trì nhiều phiên bản của một hàng. Khi một giao dịch đọc dữ liệu, hệ quản trị xác định phiên bản nào hiển thị với snapshot của giao dịch đó. Nhờ vậy, một thao tác đọc thông thường thường có thể tiếp tục xem phiên bản đã được xác nhận trong khi giao dịch khác đang cập nhật phiên bản mới.

Tuy nhiên, MVCC không loại bỏ mọi xung đột. Khi hai giao dịch cùng sửa một hàng, cùng tranh một giá trị UNIQUE, kiểm tra quan hệ khóa ngoại hoặc cần bảo vệ một phạm vi dữ liệu, hệ quản trị vẫn phải phối hợp quyền ghi và bảo đảm các ràng buộc. Khóa được dùng cho những mục đích đó. Nếu nhiều giao dịch giữ các khóa theo thứ tự khác nhau, chúng vẫn có thể tạo thành một chu trình chờ và gây deadlock.

Để hiểu đúng MVCC, cần tách hai câu hỏi:

- **Giao dịch nào được nhìn thấy phiên bản dữ liệu nào?** Đây là vấn đề về snapshot và khả năng hiển thị phiên bản.
- **Giao dịch nào được phép thay đổi dữ liệu hoặc bảo vệ một điều kiện?** Đây là vấn đề về khóa, kiểm tra xung đột và điều khiển đồng thời.

MVCC chủ yếu cải thiện cách các giao dịch đọc phiên bản dữ liệu. Khóa vẫn cần thiết để điều phối các thao tác ghi và những quy tắc nhất quán mà snapshot đơn thuần không thể bảo vệ.

## 1. MVCC giải quyết vấn đề gì?

### 1.1. Đọc một phiên bản phù hợp với snapshot

Giả sử bảng account có một hàng:

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
);

INSERT INTO account (id, balance)
VALUES (1, 1000.00);
~~~

Giao dịch A bắt đầu và đọc số dư:

~~~sql
BEGIN;

SELECT balance
FROM account
WHERE id = 1;
~~~

Trong khi A vẫn đang mở, giao dịch B cập nhật số dư rồi COMMIT:

~~~sql
BEGIN;

UPDATE account
SET balance = 900.00
WHERE id = 1;

COMMIT;
~~~

Nếu A thực hiện một lần đọc nhất quán theo snapshot cũ, A có thể tiếp tục nhìn thấy phiên bản có balance = 1000.00. Giao dịch B đã tạo phiên bản mới có balance = 900.00, nhưng phiên bản đó không nhất thiết hiển thị với snapshot mà A đang sử dụng.

Đây là lợi ích quan trọng của MVCC: một giao dịch đọc có thể tiếp tục đọc phiên bản phù hợp với snapshot mà không cần chặn mọi giao dịch đang ghi dữ liệu đó.

Chi tiết về thời điểm tạo snapshot phụ thuộc mức cô lập và hệ quản trị:

- Trong PostgreSQL ở READ COMMITTED, mỗi câu lệnh đọc thông thường có snapshot riêng tại thời điểm câu lệnh bắt đầu. Hai câu SELECT trong cùng giao dịch có thể thấy hai trạng thái đã COMMIT khác nhau.
- Trong PostgreSQL ở REPEATABLE READ, giao dịch dùng snapshot ổn định được thiết lập từ câu lệnh đầu tiên phù hợp với quy tắc của mức cô lập.
- Trong InnoDB ở REPEATABLE READ, các consistent read thông thường trong cùng giao dịch thường dùng cùng read view sau khi read view được tạo.
- Locking read và thao tác ghi có quy tắc khác với consistent read thông thường; chúng có thể phải chờ và kiểm tra trạng thái hiện tại của hàng.

Không nên lấy một ví dụ về snapshot ở một hệ quản trị rồi áp dụng nguyên xi cho mọi cơ sở dữ liệu.

### 1.2. Nhiều phiên bản không có nghĩa nhiều giao dịch được ghi đè tùy ý

MVCC cho phép lưu nhiều phiên bản, nhưng hệ quản trị vẫn phải xác định giao dịch nào có thể tạo phiên bản mới.

Nếu A và B cùng đọc balance = 1000 rồi cùng muốn cập nhật hàng đó, hệ quản trị cần phối hợp để tránh hai thao tác ghi xung đột làm mất cập nhật của nhau hoặc vi phạm quy tắc cô lập.

Ví dụ:

~~~sql
-- Giao dịch A
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE id = 1;

-- Chưa COMMIT
~~~

~~~sql
-- Giao dịch B
BEGIN;

UPDATE account
SET balance = balance - 200
WHERE id = 1;

-- Có thể phải chờ giao dịch A
~~~

Dù hệ quản trị giữ phiên bản cũ để phục vụ các snapshot đang đọc, hai giao dịch vẫn không thể tùy ý đồng thời xác nhận hai thay đổi xung đột trên cùng một hàng. Một giao dịch có thể phải chờ giao dịch kia kết thúc; ở một số mức cô lập, giao dịch có thể nhận lỗi xung đột hoặc lỗi serialization và phải chạy lại.

### 1.3. Snapshot chỉ mô tả dữ liệu được nhìn thấy

Snapshot trả lời câu hỏi một giao dịch được nhìn thấy những phiên bản nào. Nó không tự bảo vệ mọi điều kiện nghiệp vụ trong tương lai.

Ví dụ, một ứng dụng muốn bảo đảm chỉ có tối đa một bản ghi hoạt động cho mỗi người dùng. Hai giao dịch có thể cùng đọc snapshot không thấy bản ghi hoạt động nào rồi cùng thêm một bản ghi. Nếu không có UNIQUE constraint, khóa phù hợp hoặc cơ chế tuần tự hóa, cả hai có thể cùng hoàn tất và vi phạm quy tắc.

Tương tự, snapshot của một giao dịch có thể không chứa một hàng vừa được giao dịch khác tạo, nhưng điều đó không có nghĩa giao dịch hiện tại được phép xóa hàng cha mà hàng mới sẽ tham chiếu.

## 2. Vì sao MVCC vẫn cần khóa?

MVCC và khóa giải quyết các phần khác nhau của bài toán đồng thời. Hệ quản trị có thể dùng cả hai trong cùng một câu lệnh.

### 2.1. Điều phối hai giao dịch cùng ghi một hàng

Khi một giao dịch UPDATE hoặc DELETE một hàng, hệ quản trị phải bảo vệ thay đổi đó trước các thao tác ghi xung đột.

~~~sql
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE id = 1;
~~~

Một giao dịch khác muốn cập nhật hoặc xóa cùng hàng thường phải chờ khóa do giao dịch đầu tiên nắm giữ. Sau khi giao dịch đầu tiên COMMIT hoặc ROLLBACK, giao dịch thứ hai mới có thể tiếp tục theo quy tắc của hệ quản trị và mức cô lập.

Đây là xung đột ghi-ghi (write-write conflict). MVCC có thể giữ phiên bản cũ cho người đọc, nhưng không thể để hai giao dịch đồng thời xác nhận những thay đổi không tương thích trên cùng một hàng mà không có cơ chế phối hợp.

### 2.2. Bảo vệ thao tác đọc có ý định cập nhật

Không phải mọi SELECT đều chỉ muốn đọc một snapshot. Có trường hợp ứng dụng muốn đọc một hàng rồi chắc chắn hàng đó không bị giao dịch khác sửa trước khi ứng dụng cập nhật.

Ví dụ:

~~~sql
BEGIN;

SELECT balance
FROM account
WHERE id = 1
FOR UPDATE;

-- Ứng dụng tính toán và cập nhật dựa trên hàng vừa khóa.

UPDATE account
SET balance = balance - 100
WHERE id = 1;

COMMIT;
~~~

FOR UPDATE yêu cầu khóa hàng theo cơ chế của hệ quản trị. Giao dịch khác muốn cập nhật hoặc lấy khóa xung đột trên hàng đó có thể phải chờ.

Một số hệ quản trị hỗ trợ các mức khóa đọc như FOR SHARE hoặc FOR KEY SHARE. Chúng cho phép nhiều thao tác đọc có khóa tương thích cùng tồn tại, nhưng vẫn xung đột với một số loại cập nhật hoặc xóa.

Các locking read rất hữu ích khi nghiệp vụ cần một bước đọc có bảo vệ, nhưng chúng làm giảm mức độ đồng thời. Nếu chỉ cần đọc dữ liệu để hiển thị, SELECT thông thường thường phù hợp hơn.

### 2.3. Bảo vệ UNIQUE và chỉ mục duy nhất

Giả sử bảng account có email duy nhất:

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE
);
~~~

Hai giao dịch cùng thêm email giống nhau:

~~~sql
-- Giao dịch A
BEGIN;

INSERT INTO account (id, email)
VALUES (101, 'linh@example.com');

-- Chưa COMMIT
~~~

~~~sql
-- Giao dịch B
BEGIN;

INSERT INTO account (id, email)
VALUES (102, 'linh@example.com');

-- Có thể phải chờ kết quả của A
~~~

Giao dịch B phải xác định mục chỉ mục duy nhất do A tạo sẽ tồn tại hay bị loại bỏ. Nếu A COMMIT, B không được thêm giá trị trùng. Nếu A ROLLBACK, B có thể tiếp tục chèn giá trị đó.

Một snapshot cũ không đủ để kiểm tra tính duy nhất, bởi giao dịch B phải xét cả những thay đổi đồng thời chưa được xác nhận. Do đó, hệ quản trị cần cơ chế đồng bộ và chờ xung đột tại chỉ mục duy nhất.

Cách xử lý cụ thể phụ thuộc sản phẩm cơ sở dữ liệu. Có thể xuất hiện chờ khóa, chờ giao dịch khác kết thúc hoặc lỗi vi phạm UNIQUE sau khi giao dịch đối thủ hoàn tất.

### 2.4. Bảo vệ khóa ngoại

Xét hai bảng:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(id)
);
~~~

Khi thêm một đơn hàng, hệ quản trị phải xác nhận hàng customer được tham chiếu tồn tại:

~~~sql
INSERT INTO orders (id, customer_id)
VALUES (5001, 42);
~~~

Việc kiểm tra phải phối hợp với các giao dịch đang xóa hoặc thay đổi khóa của customer 42. Nếu chỉ dựa vào snapshot của giao dịch thêm đơn hàng, một giao dịch khác có thể xóa hàng cha trong khi hàng con đang được thêm, làm hỏng quan hệ tham chiếu.

Vì vậy, hệ quản trị thường lấy một loại khóa bảo vệ hàng cha trong quá trình kiểm tra khóa ngoại. Chiều ngược lại, xóa hàng cha phải kiểm tra các hàng con đang tham chiếu. Các thao tác đó có thể chờ nhau hoặc tạo deadlock nếu chúng giữ tài nguyên theo thứ tự khác nhau.

### 2.5. Bảo vệ phạm vi và điều kiện tìm kiếm

Một số quy tắc nghiệp vụ không chỉ liên quan đến một hàng cụ thể mà liên quan đến một tập hàng hoặc một khoảng giá trị.

Ví dụ, ứng dụng muốn ngăn hai cuộc hẹn có thời gian chồng lấn trong cùng một phòng. Hai giao dịch có thể cùng kiểm tra snapshot và không thấy cuộc hẹn xung đột, sau đó cùng thêm dữ liệu. Nếu không có ràng buộc hoặc cơ chế đồng thời phù hợp, cả hai có thể cùng thành công.

Tùy hệ quản trị, việc bảo vệ phạm vi có thể dùng:

- Khóa khoảng hoặc next-key lock, như một số trường hợp trong InnoDB.
- Predicate lock hoặc cơ chế theo dõi phụ thuộc, như Serializable Snapshot Isolation của PostgreSQL.
- Ràng buộc chuyên biệt, chẳng hạn exclusion constraint của PostgreSQL.
- Khóa tường minh trên một hàng đại diện hoặc tài nguyên nghiệp vụ.
- Giao dịch SERIALIZABLE và cơ chế retry khi hệ quản trị phát hiện lịch thực thi không tuần tự hóa được.

Không phải mọi cơ chế bảo vệ phạm vi đều là khóa chặn. Predicate lock trong PostgreSQL SSI chủ yếu ghi nhận phụ thuộc để phát hiện nguy cơ serialization anomaly; nó không hoạt động giống một row lock thông thường.

### 2.6. Khóa bảng, khóa lược đồ và đồng bộ nội bộ

Ngay cả khi dữ liệu hàng được quản lý bằng MVCC, hệ quản trị vẫn có thể dùng các loại khóa khác:

- Khóa bảng để điều phối các thao tác cần tương thích ở cấp bảng.
- Khóa metadata hoặc khóa lược đồ để ngăn thay đổi cấu trúc xung đột với truy vấn đang chạy.
- Khóa trên đối tượng như sequence, advisory lock hoặc tài nguyên do ứng dụng quản lý, tùy hệ quản trị.
- Latch hoặc cơ chế đồng bộ nội bộ để bảo vệ cấu trúc trong bộ nhớ như trang chỉ mục.

Cần phân biệt khóa giao dịch với latch. Khóa giao dịch có thể được giữ qua nhiều câu lệnh đến COMMIT hoặc ROLLBACK. Latch thường bảo vệ cấu trúc nội bộ trong khoảng thời gian ngắn và không nhất thiết xuất hiện như một lần chờ khóa giao dịch trong công cụ quan sát thông thường.

## 3. MVCC làm giảm chặn đọc nhưng không loại bỏ chặn ghi

Một lợi ích lớn của MVCC là giảm việc một giao dịch đọc phải chờ giao dịch khác ghi và ngược lại. Nhưng điều đó không có nghĩa mọi truy vấn đọc đều không chặn hoặc mọi thao tác ghi đều chạy độc lập.

### 3.1. Đọc thông thường và đọc có khóa

Trong PostgreSQL, một SELECT thông thường ở các mức cô lập phổ biến đọc phiên bản phù hợp với snapshot và thường không chờ row lock do UPDATE của giao dịch khác nắm giữ. UPDATE có thể tiếp tục trong khi SELECT đọc phiên bản cũ.

Trong InnoDB, consistent read thông thường cũng đọc phiên bản phù hợp với read view, thường không cần chờ row lock của giao dịch cập nhật hàng đó.

Tuy nhiên, các câu lệnh như SELECT ... FOR UPDATE và SELECT ... FOR SHARE có ý định lấy khóa. Chúng có thể phải chờ giao dịch khác đang giữ khóa xung đột.

Do đó, khi phân tích một lần chờ, cần xác định câu SELECT là consistent read thông thường hay locking read. Hai câu lệnh cùng đọc một bảng nhưng có thể đi qua cơ chế đồng thời khác nhau.

### 3.2. Hai người ghi cùng một hàng

Giả sử hai giao dịch cùng cập nhật tài khoản:

~~~sql
-- Giao dịch A
BEGIN;
UPDATE account
SET balance = balance - 100
WHERE id = 1;
~~~

~~~sql
-- Giao dịch B
BEGIN;
UPDATE account
SET balance = balance - 200
WHERE id = 1;
~~~

B có thể phải chờ A kết thúc. Khi A COMMIT, B tiếp tục theo quy tắc cập nhật của hệ quản trị. Ở một số mức cô lập, nếu phiên bản mà B định sửa không còn phù hợp với snapshot của B, hệ quản trị có thể hủy B với lỗi serialization hoặc lỗi cập nhật đồng thời.

Việc có nhiều phiên bản giúp giao dịch đọc cũ vẫn nhìn thấy dữ liệu hợp lệ. Nó không cho phép hai giao dịch ghi đè cùng một phiên bản theo cách không được kiểm soát.

### 3.3. Giao dịch đọc có thể không chặn nhưng vẫn bị hủy

Ở mức SERIALIZABLE, hệ quản trị phải bảo đảm kết quả tương đương một thứ tự thực thi tuần tự. Với PostgreSQL, Serializable Snapshot Isolation (SSI) theo dõi các phụ thuộc đọc/ghi. Hai giao dịch có thể không chờ row lock của nhau nhưng vẫn tạo ra cấu trúc phụ thuộc nguy hiểm.

Trong tình huống đó, PostgreSQL có thể hủy một giao dịch với serialization failure. Đây là cách hệ quản trị bảo vệ tính tuần tự hóa bằng cách từ chối một lịch thực thi không an toàn.

Điều này khác với deadlock truyền thống. Deadlock là chu trình chờ khóa; serialization failure là giao dịch bị hủy vì lịch thực thi không đáp ứng mức cô lập yêu cầu. Một hệ thống có thể gặp serialization failure dù không có giao dịch nào đang chờ khóa.

## 4. Vì sao MVCC vẫn có thể gặp deadlock?

Deadlock (bế tắc) xảy ra khi các giao dịch tạo thành một chu trình chờ. Mỗi giao dịch đang giữ một tài nguyên mà giao dịch khác cần, khiến tất cả giao dịch trong chu trình không thể tiếp tục.

MVCC không ngăn được chu trình này, bởi các giao dịch vẫn có thể lấy khóa hàng, khóa chỉ mục, khóa khoảng, khóa bảng hoặc khóa ứng dụng. Snapshot chỉ quyết định phiên bản nào được nhìn thấy; nó không tự sắp xếp thứ tự lấy các khóa.

### 4.1. Mô hình chờ khóa

Một giao dịch có thể:

1. Lấy khóa trên tài nguyên A.
2. Thực hiện một số thao tác và tiếp tục giữ khóa A.
3. Yêu cầu khóa trên tài nguyên B.
4. Phải chờ vì giao dịch khác đang giữ B.

Nếu giao dịch thứ hai đang giữ B và lại chờ A, ta có chu trình:

~~~text
Giao dịch A giữ khóa trên hàng 1
        |
        v
Giao dịch A chờ hàng 2
        ^
        |
Giao dịch B giữ khóa trên hàng 2
        |
        v
Giao dịch B chờ hàng 1
~~~

Hệ quản trị phát hiện chu trình trong wait-for graph (đồ thị chờ). Để phá deadlock, nó chọn một giao dịch làm nạn nhân và hủy giao dịch đó. Giao dịch còn lại có thể tiếp tục sau khi tài nguyên được giải phóng.

### 4.2. Deadlock khi cập nhật hai hàng theo thứ tự ngược nhau

Giả sử bảng account có hai hàng id = 1 và id = 2.

Giao dịch A cập nhật hàng 1 trước:

~~~sql
-- Session A
BEGIN;

UPDATE account
SET balance = balance - 10
WHERE id = 1;

-- Chưa COMMIT
~~~

Giao dịch B cập nhật hàng 2 trước:

~~~sql
-- Session B
BEGIN;

UPDATE account
SET balance = balance - 20
WHERE id = 2;

-- Chưa COMMIT
~~~

Sau đó A muốn cập nhật hàng 2:

~~~sql
-- Session A
UPDATE account
SET balance = balance + 10
WHERE id = 2;
~~~

A phải chờ vì B đang giữ khóa hàng 2. B tiếp tục muốn cập nhật hàng 1:

~~~sql
-- Session B
UPDATE account
SET balance = balance + 20
WHERE id = 1;
~~~

B phải chờ vì A đang giữ khóa hàng 1. Khi đó:

- A giữ khóa hàng 1 và chờ hàng 2.
- B giữ khóa hàng 2 và chờ hàng 1.

Đây là deadlock. Cả hai giao dịch có thể đang dùng MVCC để đọc phiên bản, nhưng các UPDATE vẫn cần khóa để phối hợp ghi. MVCC không phá được chu trình khóa này.

Cách giảm nguy cơ là thống nhất thứ tự cập nhật, chẳng hạn mọi luồng đều cập nhật hàng theo id tăng dần:

~~~sql
-- Quy ước chung: xử lý id nhỏ trước, id lớn sau.
UPDATE account
SET balance = balance - 10
WHERE id = 1;

UPDATE account
SET balance = balance + 10
WHERE id = 2;
~~~

Nếu nhiều hàng được cập nhật trong một câu lệnh, cần xem kế hoạch thực thi và bảo đảm cách xử lý thực tế có thứ tự nhất quán khi nghiệp vụ phụ thuộc vào thứ tự khóa. Chỉ viết ORDER BY ở một truy vấn không phải lúc nào cũng bảo đảm thứ tự khóa của mọi kế hoạch cập nhật.

### 4.3. Deadlock giữa thao tác thêm hàng con và xóa hàng cha

Xét quan hệ customer và orders có khóa ngoại.

Giao dịch A thêm đơn hàng cho customer 42:

~~~sql
-- Session A
BEGIN;

INSERT INTO orders (id, customer_id)
VALUES (7001, 42);

-- Chưa COMMIT
~~~

Giao dịch B đang xử lý customer 42 và một số hàng orders liên quan:

~~~sql
-- Session B
BEGIN;

UPDATE orders
SET status = 'CANCELLED'
WHERE customer_id = 42;

-- Tiếp tục xử lý hàng customer
UPDATE customer
SET name = 'Customer updated'
WHERE id = 42;
~~~

Trong khi A kiểm tra khóa ngoại và cần bảo vệ hàng customer, B có thể đang giữ khóa trên hàng con rồi cần khóa hàng cha. Ở một số lịch thực thi và cách triển khai, các thao tác có thể chờ tài nguyên của nhau và tạo chu trình.

Một biến thể thường gặp là giao dịch xóa hàng cha có hành động CASCADE. Hệ quản trị phải xử lý các hàng con, chỉ mục và những ràng buộc liên quan. Nếu giao dịch khác đang sửa hàng con rồi cần tài nguyên ở bảng cha, hai đường xử lý có thể tạo thứ tự khóa đối nghịch.

Không thể kết luận deadlock chỉ từ việc một giao dịch INSERT bảng con và một giao dịch DELETE bảng cha cùng tồn tại. Cần xem chính xác hàng nào đang bị khóa, khóa nào được yêu cầu và thứ tự thao tác của cả hai giao dịch.

### 4.4. Deadlock qua chỉ mục duy nhất

Một câu lệnh ghi có thể cần khóa hoặc chờ tại chỉ mục duy nhất để kiểm tra xung đột. Giao dịch có thể đồng thời giữ khóa hàng và khóa trên các mục chỉ mục khác.

Ví dụ, bảng employee có hai ràng buộc duy nhất:

~~~sql
CREATE TABLE employee (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    badge_code VARCHAR(50) UNIQUE
);
~~~

Hai giao dịch cập nhật các hàng hoặc các giá trị liên quan theo thứ tự khác nhau có thể tranh chấp trên các hàng và mục chỉ mục duy nhất. Nếu mỗi giao dịch đã giữ một tài nguyên và tiếp tục cần tài nguyên mà giao dịch kia giữ, deadlock có thể xuất hiện.

Không nên suy luận rằng cứ có hai UNIQUE constraint là sẽ deadlock. Điều kiện cần là các thao tác đồng thời tạo thành chu trình chờ thực tế. Log deadlock và thông tin khóa của hệ quản trị mới cho biết chu trình cụ thể.

### 4.5. Deadlock do khóa khoảng trong InnoDB

InnoDB có record lock, gap lock và next-key lock. Trong những trường hợp phù hợp, một truy vấn khóa theo phạm vi có thể bảo vệ cả các bản ghi tìm thấy và khoảng chỉ mục liên quan.

Giả sử chỉ mục trên cột amount có các giá trị 10, 20, 40. Một giao dịch khóa một khoảng:

~~~sql
-- Session A, InnoDB
START TRANSACTION;

SELECT *
FROM payment
WHERE amount >= 20 AND amount < 40
FOR UPDATE;
~~~

Một giao dịch khác có thể cần chèn hoặc cập nhật một giá trị nằm trong khoảng đang được bảo vệ. Nếu các giao dịch đồng thời đã giữ các khóa trên những khoảng hoặc bản ghi khác nhau rồi yêu cầu khóa theo thứ tự đối nghịch, chúng có thể tạo deadlock.

Mức độ sử dụng gap lock phụ thuộc mức cô lập, loại truy vấn, chỉ mục và phiên bản/cấu hình InnoDB. Ở READ COMMITTED, InnoDB thường giảm gap locking cho nhiều thao tác tìm kiếm thông thường, nhưng vẫn có ngoại lệ như kiểm tra khóa ngoại và khóa duy nhất.

### 4.6. Deadlock từ khóa tường minh hoặc khóa ứng dụng

Ứng dụng có thể dùng SELECT ... FOR UPDATE, LOCK TABLE, advisory lock hoặc một cơ chế khóa do ứng dụng tự xây dựng.

Nếu hai luồng lấy các khóa theo thứ tự khác nhau, deadlock vẫn có thể xảy ra dù các câu SELECT thông thường đang dùng MVCC.

Ví dụ, một nghiệp vụ lấy khóa trên tài khoản trước rồi khóa hàng tồn kho; nghiệp vụ khác khóa hàng tồn kho trước rồi mới khóa tài khoản. Hai giao dịch có thể chờ nhau. Khóa ứng dụng cũng phải có quy ước thứ tự và thời hạn giữ khóa rõ ràng.

## 5. MVCC, deadlock và các lỗi đồng thời khác

Các vấn đề đồng thời có biểu hiện giống nhau ở phía ứng dụng, nhưng nguyên nhân và cách xử lý khác nhau.

| Tình huống | Điều gì xảy ra? | Cách xử lý thường dùng |
|---|---|---|
| Lock wait | Giao dịch cần khóa đang do giao dịch khác giữ | Tìm blocker, giảm thời gian giữ khóa, kiểm tra phạm vi truy cập |
| Deadlock | Có chu trình trong đồ thị chờ | Hệ quản trị hủy một giao dịch; retry toàn bộ giao dịch nếu an toàn |
| Unique violation | Giá trị hoặc tổ hợp giá trị đã bị giao dịch khác sử dụng | Xử lý trùng dữ liệu hoặc nhánh xung đột nghiệp vụ |
| Foreign key violation | Hàng cha không tồn tại hoặc còn hàng con tham chiếu theo quy tắc ràng buộc | Sửa dữ liệu hoặc điều chỉnh luồng nghiệp vụ |
| Serialization failure | Lịch thực thi không đáp ứng mức cô lập yêu cầu | Retry toàn bộ giao dịch theo chính sách |
| Lock timeout | Giao dịch chờ lâu hơn thời hạn được cấu hình | Điều tra blocker, quyết định retry hoặc trả lỗi |

### 5.1. Deadlock khác lock timeout

Lock timeout xảy ra khi giao dịch chờ khóa quá thời gian cho phép. Nó không chứng minh có chu trình chờ.

Ví dụ, A giữ khóa một hàng trong 30 giây. B cần khóa hàng đó và chờ. Nếu thời hạn của B là 5 giây, B có thể nhận timeout dù A không chờ B và không có deadlock.

Deadlock đòi hỏi có chu trình. Hệ quản trị thường chủ động phát hiện chu trình và hủy một giao dịch thay vì để tất cả giao dịch chờ đến timeout.

### 5.2. Deadlock khác serialization failure

PostgreSQL SERIALIZABLE sử dụng SSI để phát hiện các phụ thuộc đọc/ghi có thể tạo ra lịch không tuần tự hóa được. Một giao dịch có thể bị hủy với SQLSTATE 40001 (serialization_failure) dù không có lock wait cycle.

Ngược lại, deadlock truyền thống thường được báo bằng SQLSTATE 40P01 trong PostgreSQL.

Trong MySQL/InnoDB, deadlock thường được báo với lỗi 1213 và SQLSTATE 40001. Lock wait timeout thường có mã lỗi 1205. Ứng dụng nên phân biệt các trường hợp theo driver và hệ quản trị đang dùng.

### 5.3. Predicate lock không nhất thiết chặn giao dịch khác

Trong PostgreSQL SSI, predicate lock (thường được hiển thị với tên SIReadLock trong pg_locks) được dùng để theo dõi vùng dữ liệu đã đọc. Nó giúp hệ quản trị nhận biết các phụ thuộc đọc/ghi có thể gây serialization anomaly.

Các khóa theo dõi này không giống row lock hoặc table lock dùng để chặn giao dịch khác. Vì vậy, không nên thấy một SIReadLock rồi kết luận có giao dịch đang bị chặn bởi khóa đó.

Hệ quả là một giao dịch có thể bị hủy vì serialization failure mà không hề có deadlock. Đây là cơ chế bảo vệ tính tuần tự hóa của MVCC ở mức SERIALIZABLE.

## 6. Khác biệt đáng chú ý giữa PostgreSQL và InnoDB

Cả PostgreSQL và InnoDB đều dùng MVCC, nhưng chi tiết khóa và kiểm tra xung đột khác nhau.

### 6.1. PostgreSQL

PostgreSQL lưu nhiều phiên bản tuple và dùng snapshot để xác định phiên bản hiển thị. Một SELECT thông thường thường không chặn UPDATE hoặc DELETE chỉ vì giao dịch ghi đang giữ row lock.

Một số đặc điểm:

- UPDATE và DELETE cần phối hợp khóa trên hàng mục tiêu.
- SELECT ... FOR UPDATE, FOR NO KEY UPDATE, FOR SHARE và FOR KEY SHARE có các mức khóa hàng với khả năng tương thích khác nhau.
- Kiểm tra khóa ngoại có thể lấy khóa hàng tương đương KEY SHARE trên hàng được tham chiếu.
- UNIQUE constraint phải phối hợp với các giao dịch đồng thời, kể cả những thay đổi chưa COMMIT.
- PostgreSQL có các loại table lock để điều phối thao tác ở cấp bảng; ngay cả SELECT thông thường cũng lấy một mức khóa bảng nhẹ, tương thích với nhiều thao tác khác.
- Ở SERIALIZABLE, SSI theo dõi phụ thuộc bằng predicate lock và có thể hủy giao dịch để tránh lịch không tuần tự hóa được.

Một giao dịch PostgreSQL có thể chờ transaction ID của giao dịch khác thay vì hiển thị một khóa hàng theo cách trực quan. Điều này thường xảy ra khi cần xác định trạng thái COMMIT/ROLLBACK của một phiên bản hoặc thao tác đang cạnh tranh.

### 6.2. MySQL InnoDB

InnoDB lưu phiên bản cũ trong undo log để phục vụ consistent read và rollback. Các thao tác ghi dùng khóa bản ghi và trong những tình huống phù hợp có khóa khoảng.

Một số đặc điểm:

- Consistent read thông thường dùng read view để đọc phiên bản phù hợp.
- UPDATE, DELETE và locking read cần khóa trên các bản ghi được tác động.
- Kiểm tra UNIQUE và FOREIGN KEY có thể lấy khóa trên các mục chỉ mục liên quan.
- Trong REPEATABLE READ, truy vấn khóa theo phạm vi có thể dùng next-key lock để bảo vệ cả bản ghi và khoảng.
- Ở READ COMMITTED, gap lock thường được giảm cho nhiều truy vấn tìm kiếm thông thường, nhưng vẫn có ngoại lệ.
- Deadlock detector của InnoDB có thể phát hiện chu trình và rollback một giao dịch làm nạn nhân.

InnoDB phụ thuộc nhiều vào chỉ mục được dùng để tìm hàng. Một điều kiện truy vấn thiếu chỉ mục phù hợp có thể khiến hệ quản trị quét và khóa phạm vi rộng hơn dự kiến.

### 6.3. Cách đọc cùng một tình huống ở hai hệ quản trị

| Chủ đề | PostgreSQL | MySQL InnoDB |
|---|---|---|
| Đọc thông thường | Đọc phiên bản theo snapshot | Consistent read theo read view |
| Ghi cùng hàng | Dùng cơ chế khóa hàng và kiểm tra phiên bản | Dùng record lock và cơ chế phiên bản |
| Khóa phạm vi | Không dùng gap lock như InnoDB | Có gap lock/next-key lock trong các trường hợp phù hợp |
| SERIALIZABLE | SSI theo dõi phụ thuộc, có thể báo serialization failure | Cơ chế khóa và kiểm tra của InnoDB theo mức cô lập |
| Kiểm tra khóa ngoại | Có thể dùng khóa hàng trên hàng được tham chiếu | Có thể khóa bản ghi chỉ mục liên quan |
| Chẩn đoán deadlock | Log deadlock, pg_stat_activity, pg_locks | SHOW ENGINE INNODB STATUS, Performance Schema |

Bảng này mô tả các điểm khác biệt chính, không phải bảng ánh xạ từng loại khóa tương đương hoàn toàn. Khi điều tra hệ thống thật, cần dùng tài liệu đúng phiên bản và dữ liệu quan sát của chính hệ quản trị đó.

## 7. Quan sát deadlock và chờ khóa

Khi ứng dụng báo truy vấn bị treo hoặc deadlock, cần thu thập thông tin của cả giao dịch đang chờ và giao dịch đang giữ khóa. Câu SQL của phiên bị chặn có thể chỉ là bước cuối cùng trong một giao dịch đã mở từ lâu.

### 7.1. PostgreSQL: tìm phiên đang chờ và phiên chặn

Có thể xem các phiên, sự kiện chờ và câu truy vấn hiện tại:

~~~sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Hàm pg_blocking_pids giúp xác định PID đang chặn một phiên:

~~~sql
SELECT
    pid AS blocked_pid,
    pg_blocking_pids(pid) AS blocking_pids,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
~~~

Có thể xem thông tin khóa:

~~~sql
SELECT
    locktype,
    mode,
    granted,
    relation::regclass AS relation,
    page,
    tuple,
    transactionid,
    pid
FROM pg_locks
ORDER BY pid, granted;
~~~

Để hiểu deadlock đã xảy ra, cần bật và xem log phù hợp. PostgreSQL có thể ghi chi tiết giao dịch và tài nguyên liên quan khi phát hiện deadlock; tham số log_lock_waits và deadlock_timeout cũng hữu ích cho chẩn đoán chờ khóa kéo dài.

Không phải mọi phụ thuộc MVCC đều hiển thị thành một row lock đơn giản. Kết hợp pg_stat_activity, pg_locks, pg_blocking_pids và log máy chủ sẽ cho bức tranh đầy đủ hơn.

### 7.2. MySQL InnoDB: xem khóa và deadlock gần nhất

Có thể truy vấn thông tin khóa trong Performance Schema:

~~~sql
SELECT *
FROM performance_schema.data_locks;
~~~

~~~sql
SELECT *
FROM performance_schema.data_lock_waits;
~~~

Để xem báo cáo InnoDB:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Phần TRANSACTIONS và LATEST DETECTED DEADLOCK thường cho biết giao dịch nào giữ khóa, giao dịch nào chờ và câu lệnh liên quan tại thời điểm detector phát hiện deadlock.

Cũng cần kiểm tra:

- Mức cô lập hiện tại.
- Chỉ mục được dùng trong truy vấn.
- Kế hoạch EXPLAIN.
- Kích thước giao dịch và số hàng bị quét.
- Thứ tự các câu lệnh trong mỗi giao dịch.

Một truy vấn chỉ định một hàng theo điều kiện nghiệp vụ nhưng thiếu chỉ mục phù hợp có thể quét nhiều bản ghi. Phạm vi khóa rộng làm tăng khả năng xung đột với giao dịch khác.

### 7.3. Dựng lại đồ thị chờ

Khi có nhiều giao dịch, hãy ghi lại mỗi giao dịch đang giữ tài nguyên nào và đang chờ tài nguyên nào.

Ví dụ:

| Giao dịch | Đang giữ | Đang chờ |
|---|---|---|
| T1 | Hàng A | Hàng B |
| T2 | Hàng B | Hàng C |
| T3 | Hàng C | Hàng A |

Chu trình T1 → T2 → T3 → T1 cho thấy deadlock. Hệ quản trị có thể chọn một giao dịch làm nạn nhân để phá chu trình.

Khi phân tích log, đừng chỉ xem dòng báo lỗi. Cần xác định tài nguyên, chế độ khóa, giao dịch giữ khóa và câu lệnh đã lấy khóa trước đó. Giao dịch giữ khóa có thể đã chạy qua nhiều câu lệnh trước khi bị giao dịch khác chặn.

## 8. Cách thiết kế để giảm deadlock trong hệ thống dùng MVCC

Không thể bảo đảm mọi deadlock biến mất trong một hệ thống có ghi đồng thời, nhưng có thể giảm đáng kể xác suất và giúp ứng dụng phục hồi đúng.

### 8.1. Thống nhất thứ tự lấy khóa

Đây là một trong những biện pháp hiệu quả nhất.

Nếu một nghiệp vụ cần cập nhật nhiều tài khoản, hãy xác định thứ tự chung, chẳng hạn theo account_id tăng dần. Mọi luồng nghiệp vụ đều phải tuân theo quy ước đó.

~~~text
Quy tắc chung:
1. Sắp xếp danh sách account_id tăng dần.
2. Khóa và cập nhật từng tài khoản theo thứ tự đó.
3. Hoàn thành các thao tác liên quan.
4. COMMIT.
~~~

Khi mọi giao dịch lấy cùng nhóm tài nguyên theo cùng thứ tự, nguy cơ tạo chu trình do thứ tự ngược nhau giảm mạnh.

Quy tắc này cần áp dụng xuyên suốt các tầng nghiệp vụ. Nếu một service cập nhật customer rồi orders, service khác lại cập nhật orders rồi customer, deadlock vẫn có thể xuất hiện.

### 8.2. Giữ giao dịch ngắn

Khóa giao dịch thường được giữ đến COMMIT hoặc ROLLBACK. Vì vậy, giảm thời gian giao dịch mở sẽ giảm thời gian các giao dịch khác phải chờ.

Nên tránh:

- Gọi HTTP hoặc RPC trong khi đang giữ khóa hàng.
- Chờ người dùng nhập dữ liệu trong giao dịch.
- Xử lý tệp lớn hoặc tính toán không cần tính nguyên tử trong giao dịch.
- Mở giao dịch trước khi cần truy cập cơ sở dữ liệu quá lâu.
- Quên COMMIT/ROLLBACK khi xử lý ngoại lệ.

Hãy chuẩn bị dữ liệu ngoài giao dịch khi có thể, mở giao dịch gần thời điểm ghi, thực hiện thao tác cần tính nguyên tử và kết thúc sớm.

### 8.3. Tạo chỉ mục phù hợp

Chỉ mục phù hợp giúp hệ quản trị tìm đúng hàng nhanh hơn và giảm phạm vi quét. Đặc biệt chú ý:

- Cột khóa ngoại ở bảng con.
- Các điều kiện WHERE của UPDATE và DELETE thường xuyên.
- Cột dùng trong locking read.
- Các tổ hợp cột được dùng để tìm và cập nhật một tập hàng nhỏ.

Chỉ mục không loại bỏ khóa. Nó giúp giảm thời gian và phạm vi truy cập, nhờ đó giảm cơ hội giao dịch khác chạm vào tài nguyên xung đột.

Cũng không nên tạo chỉ mục tràn lan. Mỗi chỉ mục làm tăng chi phí ghi, dung lượng và công việc duy trì cấu trúc.

### 8.4. Tránh kiểm tra trước rồi ghi sau bằng snapshot cũ

Mẫu sau có thể không an toàn:

~~~sql
BEGIN;

SELECT COUNT(*)
FROM reservation
WHERE room_id = 10
  AND start_time < '2026-12-01 11:00:00'
  AND end_time > '2026-12-01 10:00:00';

-- Nếu không có hàng thì INSERT
INSERT INTO reservation (...);

COMMIT;
~~~

Hai giao dịch có thể cùng đọc snapshot không thấy cuộc hẹn xung đột rồi cùng thêm hàng. Để bảo vệ quy tắc, hãy dùng ràng buộc cơ sở dữ liệu phù hợp, khóa hàng đại diện cho phòng, hoặc SERIALIZABLE với xử lý serialization failure. Cơ chế phù hợp tùy mô hình dữ liệu và hệ quản trị.

### 8.5. Hạn chế locking read khi không cần thiết

FOR UPDATE là công cụ hữu ích khi cần đọc rồi cập nhật một hàng với bảo vệ đồng thời. Nhưng nếu dùng cho mọi SELECT, ứng dụng sẽ tạo nhiều khóa hơn, giảm khả năng chạy đồng thời và tăng nguy cơ deadlock.

Chỉ khóa các hàng thực sự cần được bảo vệ. Chọn mức khóa hẹp nhất đáp ứng nghiệp vụ và tránh khóa một tập hàng lớn chỉ vì muốn phòng ngừa chung chung.

### 8.6. Chú ý thao tác hàng loạt và CASCADE

Một câu lệnh cập nhật hoặc xóa hàng loạt có thể tác động đến nhiều hàng, chỉ mục và quan hệ khóa ngoại. Nếu các giao dịch khác xử lý cùng dữ liệu theo thứ tự khác nhau, nguy cơ deadlock tăng.

Với thao tác hàng loạt:

- Chia lô nếu phù hợp với nghiệp vụ.
- Dùng thứ tự xử lý ổn định.
- Có chỉ mục cho điều kiện lọc.
- Xác định trước tác động của CASCADE.
- Giữ mỗi giao dịch ở phạm vi dữ liệu vừa đủ.

Chia lô làm giảm thời gian và số tài nguyên một giao dịch giữ, nhưng phải bảo đảm nghiệp vụ chấp nhận việc hoàn thành theo từng phần.

### 8.7. Thiết kế khóa ứng dụng có thứ tự và thời hạn

Nếu dùng advisory lock hoặc khóa phân tán, hãy quy định thứ tự lấy khóa, timeout và cách nhả khóa. Tránh lấy một khóa ứng dụng rồi chờ khóa cơ sở dữ liệu trong khi luồng khác lấy khóa cơ sở dữ liệu rồi chờ khóa ứng dụng.

Hệ quản trị không phải lúc nào cũng nhìn thấy toàn bộ đồ thị chờ nếu một phần khóa nằm ở ứng dụng hoặc hệ thống phân tán. Khi đó, deadlock có thể tồn tại ở cấp nghiệp vụ dù cơ sở dữ liệu không báo deadlock.

## 9. Xử lý deadlock đúng cách trong ứng dụng

Deadlock có thể xảy ra ngay cả khi thiết kế đã hợp lý. Ứng dụng cần coi đây là lỗi đồng thời có thể phục hồi, với điều kiện giao dịch được thiết kế để retry an toàn.

### 9.1. Retry toàn bộ giao dịch

Khi hệ quản trị hủy giao dịch do deadlock, các thay đổi trong giao dịch đó thường đã bị rollback. Ứng dụng nên chạy lại toàn bộ đơn vị công việc có tính nguyên tử, thay vì chỉ gửi lại câu lệnh cuối cùng.

Ví dụ về cấu trúc xử lý:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    begin transaction
    try:
        perform all database operations
        commit
        return success
    catch deadlock or retryable serialization error:
        rollback if transaction is still open
        wait with bounded backoff
        continue
    catch other error:
        rollback
        return failure

return retryable failure
~~~

Mã giả này cần được điều chỉnh theo framework và driver. Một số thư viện tự đánh dấu giao dịch là rollback-only sau lỗi; khi đó phải tạo giao dịch mới cho lần retry tiếp theo.

### 9.2. Giới hạn số lần thử và dùng backoff

Không retry vô hạn. Nếu nhiều request cùng retry ngay lập tức, tải có thể tăng và các giao dịch tiếp tục va chạm.

Nên:

- Giới hạn số lần retry.
- Dùng backoff có độ trễ tăng dần.
- Có thể thêm jitter để các request không retry cùng một thời điểm.
- Ghi log số lần retry và loại lỗi.
- Trả lỗi có thể thử lại cho tầng gọi khi vượt giới hạn.

Chỉ retry các lỗi được xác định là có thể phục hồi. Vi phạm UNIQUE do dữ liệu đầu vào trùng thường là lỗi nghiệp vụ, không phải lỗi nên retry liên tục.

### 9.3. Bảo đảm tác dụng phụ bên ngoài an toàn

Retry toàn bộ giao dịch có thể khiến mã ứng dụng chạy lại. Nếu trong giao dịch có gửi email, gọi cổng thanh toán hoặc phát sự kiện không thể đảo ngược, thao tác bên ngoài có thể bị lặp.

Một số cách xử lý:

- Dùng idempotency key cho thao tác có thể được gọi lại.
- Ghi sự kiện vào transactional outbox cùng giao dịch, sau đó phát sự kiện sau COMMIT.
- Tách thao tác bên ngoài khỏi vùng giao dịch đang giữ khóa.
- Thiết kế consumer xử lý sự kiện theo cách idempotent.

Không nên giả định rollback cơ sở dữ liệu sẽ tự hoàn tác một HTTP request hoặc một khoản thanh toán đã được hệ thống bên ngoài xác nhận.

### 9.4. Ghi nhận đủ thông tin để điều tra

Log ứng dụng nên ghi:

- Mã giao dịch nghiệp vụ hoặc correlation ID.
- Tên thao tác và các loại tài nguyên liên quan.
- Mức cô lập nếu có thể quan sát.
- Thời gian giao dịch bắt đầu và kết thúc.
- Loại lỗi, SQLSTATE hoặc mã lỗi driver.
- Số lần retry và kết quả cuối cùng.

Không ghi dữ liệu nhạy cảm hoặc toàn bộ câu SQL chứa thông tin bí mật vào log. Mục tiêu là liên kết được lỗi ở ứng dụng với log deadlock của cơ sở dữ liệu.

## 10. Ví dụ: chuyển tiền trong hệ thống MVCC

Giả sử ứng dụng cần chuyển 100 từ tài khoản A sang tài khoản B. Cả hai tài khoản phải được cập nhật trong một giao dịch:

~~~sql
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE id = 10;

UPDATE account
SET balance = balance + 100
WHERE id = 20;

COMMIT;
~~~

Một giao dịch khác chuyển tiền theo chiều ngược lại:

~~~sql
BEGIN;

UPDATE account
SET balance = balance - 50
WHERE id = 20;

UPDATE account
SET balance = balance + 50
WHERE id = 10;

COMMIT;
~~~

Nếu giao dịch thứ nhất khóa tài khoản 10 rồi chờ tài khoản 20, còn giao dịch thứ hai khóa tài khoản 20 rồi chờ tài khoản 10, deadlock có thể xảy ra.

MVCC vẫn có thể giúp các giao dịch đọc thông thường nhìn thấy phiên bản đã xác nhận phù hợp với snapshot. Nhưng hai giao dịch ghi cần khóa để bảo vệ cập nhật. Chu trình chờ phát sinh từ thứ tự lấy khóa.

Có thể thống nhất thứ tự khóa theo id:

~~~sql
BEGIN;

SELECT id, balance
FROM account
WHERE id IN (10, 20)
ORDER BY id
FOR UPDATE;

-- Sau khi khóa các hàng theo quy ước chung,
-- kiểm tra số dư và cập nhật cả hai tài khoản.

UPDATE account
SET balance = balance - 100
WHERE id = 10;

UPDATE account
SET balance = balance + 100
WHERE id = 20;

COMMIT;
~~~

Ví dụ này minh họa ý tưởng. Cách bảo đảm thứ tự khóa thực tế phải được xác nhận theo hệ quản trị và kế hoạch thực thi. Với nghiệp vụ chuyển tiền, ứng dụng cũng cần kiểm tra số dư, giới hạn retry và bảo đảm giao dịch không phát sinh tác dụng phụ lặp.

## 11. Các nhận định sai thường gặp

**“MVCC có nhiều phiên bản nên không cần khóa.”**

Sai. Nhiều phiên bản giúp đọc dữ liệu theo snapshot. Các thao tác ghi xung đột, kiểm tra UNIQUE, khóa ngoại và locking read vẫn cần phối hợp bằng khóa hoặc cơ chế kiểm tra tương đương.

**“SELECT thông thường không chờ thì hệ thống không có deadlock.”**

Sai. Một SELECT thông thường có thể đọc snapshot mà không chờ row lock, trong khi UPDATE, DELETE, locking read hoặc kiểm tra ràng buộc vẫn có thể tạo chu trình chờ.

**“Deadlock chỉ xảy ra khi dùng FOR UPDATE.”**

Sai. UPDATE, DELETE, INSERT vào chỉ mục duy nhất, kiểm tra khóa ngoại, thao tác CASCADE, khóa bảng hoặc khóa ứng dụng đều có thể tham gia vào deadlock.

**“Nếu hai giao dịch sửa hai hàng khác nhau thì không thể deadlock.”**

Sai. Hai giao dịch có thể sửa hai hàng khác nhau nhưng cùng tranh một mục chỉ mục, hàng cha/con, khoảng chỉ mục hoặc tài nguyên ứng dụng.

**“Snapshot cũ bảo đảm dữ liệu không bị thay đổi trong lúc giao dịch chạy.”**

Sai. Snapshot xác định phiên bản được nhìn thấy. Nó không đóng băng toàn bộ cơ sở dữ liệu và không tự ngăn giao dịch khác ghi phiên bản mới.

**“Serialization failure và deadlock là một lỗi.”**

Sai. Deadlock là chu trình chờ khóa. Serialization failure là giao dịch bị hủy vì lịch thực thi không đáp ứng mức cô lập. PostgreSQL SSI có thể báo serialization failure mà không có deadlock.

**“Tăng timeout sẽ sửa deadlock.”**

Sai. Timeout chỉ giới hạn thời gian chờ. Deadlock cần phá chu trình bằng cách hủy một giao dịch; tăng timeout không loại bỏ thứ tự khóa gây ra chu trình.

**“Thêm chỉ mục sẽ loại bỏ mọi deadlock.”**

Sai. Chỉ mục có thể giảm phạm vi quét và thời gian giữ khóa, nhưng các thao tác trên chỉ mục UNIQUE và các quan hệ khóa ngoại vẫn có thể xung đột.

## 12. Cách suy luận khi gặp deadlock trong hệ thống MVCC

Khi nhận được thông báo deadlock, hãy đi từ đồ thị chờ và tài nguyên cụ thể:

1. Xác định các giao dịch tham gia deadlock từ log hoặc công cụ chẩn đoán.
2. Liệt kê khóa mỗi giao dịch đang giữ và khóa nó đang yêu cầu.
3. Xác định câu lệnh nào đã lấy khóa trước đó trong cùng giao dịch.
4. Kiểm tra các ràng buộc UNIQUE, FOREIGN KEY, chỉ mục và hành động CASCADE liên quan.
5. Kiểm tra mức cô lập, loại truy vấn đọc (consistent read hay locking read) và phạm vi chỉ mục được quét.
6. So sánh thứ tự truy cập tài nguyên giữa các luồng nghiệp vụ.
7. Chọn biện pháp giảm chu trình: thống nhất thứ tự khóa, rút ngắn giao dịch, thu hẹp phạm vi quét hoặc điều chỉnh thiết kế ràng buộc.
8. Bổ sung retry toàn bộ giao dịch với giới hạn và backoff nếu lỗi có thể phục hồi.

Khi cần phân biệt deadlock với serialization failure, hãy kiểm tra mã lỗi và thông tin của hệ quản trị. Một giao dịch bị hủy không nhất thiết đã tham gia vào chu trình chờ khóa.

MVCC cho phép nhiều giao dịch đọc các phiên bản phù hợp với snapshot của chúng, nhờ đó giảm nhiều kiểu chặn giữa đọc và ghi. Nhưng dữ liệu vẫn phải được cập nhật nhất quán, các ràng buộc vẫn phải được duy trì và những thao tác có ý định khóa vẫn phải phối hợp với nhau. Vì vậy, MVCC và khóa luôn cùng tồn tại trong điều khiển đồng thời; hiểu ranh giới giữa khả năng hiển thị phiên bản và quyền truy cập tài nguyên là chìa khóa để giải thích vì sao một hệ thống MVCC vẫn có thể chờ khóa và gặp deadlock.
