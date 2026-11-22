# Truy vấn bằng khóa duy nhất và điều kiện trên khoảng

Cách một truy vấn tìm dữ liệu ảnh hưởng trực tiếp đến phạm vi mà hệ quản trị phải bảo vệ khi có giao dịch đồng thời. Truy vấn bằng một khóa duy nhất thường xác định tối đa một hàng. Truy vấn theo khoảng có thể phụ thuộc vào nhiều khóa chỉ mục, kể cả những vị trí hiện chưa có hàng nào.

Sự khác biệt này đặc biệt quan trọng với **khóa khoảng** (*gap lock*), **khóa phạm vi khóa** (*key-range lock*) và **predicate lock**. Một lần tìm chính xác trên unique index thường có phạm vi truy cập nhỏ. Một truy vấn theo khoảng cần bảo vệ cả tập hàng thỏa điều kiện và có thể cần bảo vệ những vị trí mà hàng mới có thể được chèn vào. Phạm vi thực tế còn phụ thuộc hệ quản trị, isolation level, chỉ mục được chọn và execution plan.

## 1. Hai dạng truy vấn có ý nghĩa khác nhau

Giả sử bảng tài khoản có khóa chính là account_id:

~~~sql
CREATE TABLE account (
    account_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    balance DECIMAL(18, 2) NOT NULL
);
~~~

Truy vấn sau tìm theo khóa duy nhất:

~~~sql
SELECT account_id, balance
FROM account
WHERE account_id = 42;
~~~

Vì account_id là khóa chính, điều kiện này xác định tối đa một hàng. Nếu hàng tồn tại, hệ quản trị có thể định vị trực tiếp một khóa trong chỉ mục duy nhất.

Trong khi đó, truy vấn sau tìm theo điều kiện khoảng:

~~~sql
SELECT account_id, balance
FROM account
WHERE balance >= 1000
  AND balance < 5000;
~~~

Truy vấn có thể trả về nhiều hàng. Nó cũng mô tả một phạm vi giá trị: các tài khoản có số dư từ 1.000 đến nhỏ hơn 5.000. Khi cần bảo vệ kết quả truy vấn khỏi thay đổi đồng thời, hệ thống có thể phải theo dõi hoặc khóa cả phạm vi chỉ mục tương ứng, không chỉ các hàng đang trả về.

Một điểm quan trọng: điều kiện SQL và phạm vi khóa không phải lúc nào cũng giống nhau. Optimizer chọn access path; engine có thể khóa các bản ghi chỉ mục đã quét, khoảng giữa chúng, trang chỉ mục hoặc predicate logic. Truy vấn không có chỉ mục phù hợp có thể dẫn đến phạm vi bảo vệ rộng hơn mong muốn.

## 2. Khóa duy nhất bảo đảm tính duy nhất của dữ liệu

Một unique constraint hoặc primary key bảo đảm không có hai hàng cùng mang một giá trị khóa theo quy tắc của constraint.

Ví dụ:

~~~sql
ALTER TABLE account
ADD CONSTRAINT uq_account_customer
UNIQUE (customer_id);
~~~

Điều kiện:

~~~sql
SELECT *
FROM account
WHERE customer_id = 9001;
~~~

có thể trả về tối đa một hàng. Chỉ mục duy nhất giúp engine tìm một điểm khóa thay vì phải tìm cả tập khóa thỏa điều kiện.

Tuy nhiên, cần phân biệt hai loại bảo đảm:

- **Unique constraint** bảo vệ tính duy nhất của dữ liệu. Hai transaction cùng chèn một customer_id sẽ không thể cùng commit hai hàng vi phạm constraint.
- **Locking read hoặc isolation level** bảo vệ quan hệ đọc–ghi của transaction. Nó quyết định transaction khác có thể sửa hoặc chèn dữ liệu ảnh hưởng đến lần đọc hay không.

Một truy vấn SELECT theo unique key không tự tạo ra unique constraint. Nếu cột được tìm kiếm không có ràng buộc duy nhất, điều kiện bằng vẫn có thể trả về nhiều hàng và không thể được coi là point lookup duy nhất.

Ngay cả khi có unique index, việc tìm một khóa chưa tồn tại cũng cần được xem xét riêng. Hệ thống có thể không có hàng để đặt row lock. Một số engine có thể bảo vệ vị trí chèn bằng gap/key-range lock; engine khác có thể theo dõi predicate và hủy transaction khi phát hiện lịch không tuần tự hóa được.

## 3. B-tree biến điều kiện truy vấn thành điểm và khoảng

Nhiều chỉ mục quan hệ sử dụng cấu trúc B-tree hoặc biến thể của B-tree. Các khóa chỉ mục được sắp xếp theo thứ tự, cho phép engine tìm một khóa cụ thể hoặc quét từ điểm bắt đầu đến điểm kết thúc.

Ví dụ chỉ mục trên customer_id có các khóa:

~~~text
1001
1008
1015
1022
1030
1044
~~~

Tìm customer_id = 1015 là tìm một điểm cụ thể.

Tìm customer_id >= 1010 AND customer_id < 1035 là quét một khoảng, bao gồm các khóa 1015, 1022 và 1030 cùng những vị trí giữa chúng có thể nhận khóa mới.

Có thể hình dung:

~~~text
Point lookup:
    1001  1008  [1015]  1022  1030  1044
                    ^
                 một khóa

Range scan:
    1001  1008  [1015  1022  1030]  1044
                  <---- phạm vi ---->
~~~

Với point lookup trên unique index, engine có thể định vị một khóa. Với range scan, engine phải duyệt một dải khóa. Nếu transaction cần bảo đảm không có hàng mới xuất hiện trong dải đó, cơ chế khóa hoặc kiểm soát khả tuần tự phải bảo vệ cả phạm vi.

Phạm vi khóa không nhất thiết chỉ gồm các hàng mà SELECT trả về. Một khoảng có thể chứa những vị trí trống giữa hai khóa chỉ mục. Nếu một transaction khác chèn khóa mới vào vị trí đó, kết quả truy vấn theo khoảng có thể thay đổi. Đây là một trường hợp phantom.

## 4. Điều kiện bằng trên unique index và điều kiện bằng trên non-unique index

Hai câu truy vấn cùng dùng dấu bằng nhưng không có cùng ý nghĩa:

~~~sql
-- account_id là PRIMARY KEY
SELECT *
FROM account
WHERE account_id = 42;
~~~

~~~sql
-- customer_id có thể không duy nhất
SELECT *
FROM account
WHERE customer_id = 42;
~~~

Truy vấn thứ nhất tìm tối đa một hàng. Truy vấn thứ hai có thể tìm nhiều hàng nếu customer_id không có constraint duy nhất.

Đối với InnoDB, locking read dùng điều kiện duy nhất trên unique index để tìm thấy một hàng thường chỉ cần khóa bản ghi chỉ mục được tìm thấy, không khóa gap trước bản ghi đó. Nhưng nếu khóa duy nhất được tìm **không tồn tại**, engine không có record để khóa; dưới REPEATABLE READ, việc tìm kiếm khóa có thể bảo vệ gap chứa vị trí chèn. Với non-unique index hoặc điều kiện phạm vi, next-key/gap locking có thể được sử dụng trên các bản ghi và khoảng được quét.

Không nên áp dụng quy tắc InnoDB này cho PostgreSQL hoặc SQL Server. Mỗi engine có cách bảo vệ điểm tìm kiếm và phạm vi khác nhau.

## 5. Điều kiện trên khoảng và phantom

Giả sử hệ thống cần bảo đảm không có hai lượt đặt cho cùng một phòng trong một khoảng ngày.

~~~sql
SELECT booking_id
FROM room_booking
WHERE room_id = 5
  AND booking_date >= DATE '2026-11-20'
  AND booking_date < DATE '2026-11-27';
~~~

Kết quả hiện tại có thể gồm các ngày 20, 22 và 25. Nhưng transaction khác có thể chèn một lượt đặt cho ngày 23 sau khi truy vấn đã chạy.

Nếu transaction đầu tiên dựa vào kết quả hiện tại để kết luận còn ngày trống, lần chèn mới có thể làm kết luận đó không còn đúng. Hệ thống cần bảo vệ predicate:

room_id = 5 AND booking_date >= ngày bắt đầu AND booking_date < ngày kết thúc

Chứ không chỉ khóa những hàng đã được SELECT trả về.

Phantom xuất hiện khi một transaction chạy lại cùng điều kiện và thấy thêm hoặc mất hàng do transaction khác chèn/xóa/cập nhật dữ liệu thỏa predicate. Khóa hàng hiện hữu có thể ngăn cập nhật hàng đó, nhưng không nhất thiết ngăn một hàng mới xuất hiện trong khoảng.

## 6. InnoDB: record lock, gap lock và next-key lock

InnoDB sử dụng các loại khóa chỉ mục sau trong locking read và thao tác ghi:

- **Record lock:** khóa một bản ghi chỉ mục hiện hữu.
- **Gap lock:** khóa khoảng giữa các bản ghi chỉ mục, ngăn chèn khóa mới vào khoảng đó.
- **Next-key lock:** kết hợp record lock với gap đứng ngay trước bản ghi chỉ mục.

### 6.1. Tìm một hàng bằng unique key

Ví dụ account_id là primary key:

~~~sql
START TRANSACTION;

SELECT balance
FROM account
WHERE account_id = 42
FOR UPDATE;

-- Cập nhật tài khoản đã tìm thấy.
UPDATE account
SET balance = balance - 100
WHERE account_id = 42;

COMMIT;
~~~

Với điều kiện tìm kiếm duy nhất và hàng tồn tại, InnoDB thường khóa record tương ứng thay vì cả gap. Đây là phạm vi hẹp phù hợp cho một hàng cần cập nhật.

Nếu account_id = 42 chưa tồn tại, không có record để khóa. Ở REPEATABLE READ, locking search có thể đặt gap lock trên khoảng nơi khóa đó sẽ được chèn để ngăn một transaction khác tạo hàng thỏa điều kiện trong khi transaction hiện tại còn giữ bảo vệ.

### 6.2. Quét một khoảng chỉ mục

Ví dụ:

~~~sql
START TRANSACTION;

SELECT account_id, balance
FROM account
WHERE account_id >= 100
  AND account_id < 200
FOR UPDATE;

COMMIT;
~~~

InnoDB có thể sử dụng next-key lock trên các bản ghi chỉ mục được quét và những gap liên quan. Transaction khác có thể bị chặn khi chèn khóa vào phạm vi đang được bảo vệ.

Phạm vi cụ thể phụ thuộc vào chỉ mục và execution plan. Nếu điều kiện dùng unique index và unique search condition, phạm vi có thể nhỏ hơn nhiều so với một range scan trên non-unique index.

### 6.3. Isolation level ảnh hưởng đến gap lock

Ở InnoDB REPEATABLE READ, gap/next-key locking được dùng rộng rãi cho locking read, UPDATE và DELETE theo phạm vi nhằm ngăn phantom trong những tình huống tương ứng.

Ở READ COMMITTED, InnoDB thường tắt gap locking cho tìm kiếm và quét chỉ mục thông thường; một số trường hợp như kiểm tra khóa ngoại và duplicate-key vẫn có thể dùng gap lock. Vì vậy, không thể đổi isolation level mà vẫn giả định phạm vi bảo vệ không đổi.

Khi phân tích, cần xem:

- Câu lệnh có phải locking read hay chỉ là consistent read theo MVCC.
- Isolation level hiện hành.
- Chỉ mục được chọn và các cột tạo nên khóa chỉ mục.
- Các record/gap thực tế bị khóa.
- Transaction khác đang chờ trên tài nguyên nào.

## 7. SQL Server: key-range lock khi cần bảo vệ phạm vi

SQL Server sử dụng key-range lock ở isolation level SERIALIZABLE để ngăn transaction khác chèn khóa mới vào khoảng mà transaction đang đọc.

Ví dụ point lookup trên unique index:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;

SELECT AccountId, Balance
FROM dbo.Account
WHERE AccountId = 42;

COMMIT TRANSACTION;
~~~

Nếu khóa 42 tồn tại, engine có thể khóa khóa chỉ mục tương ứng. Nếu khóa chưa tồn tại, việc bảo vệ phạm vi có thể ngăn một transaction khác chèn giá trị đó cho đến khi transaction kết thúc.

Ví dụ truy vấn theo khoảng:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;

SELECT AccountId, Balance
FROM dbo.Account
WHERE AccountId >= 100
  AND AccountId < 200;

COMMIT TRANSACTION;
~~~

Hệ quản trị cần bảo vệ phạm vi chỉ mục phù hợp để ngăn phantom. Trong SQL Server, các chế độ key-range lock có tên như RangeS-S, RangeS-U hoặc RangeI-N trong thông tin chẩn đoán. Chế độ cụ thể phụ thuộc loại thao tác và tương tác khóa.

Có thể dùng HOLDLOCK để áp dụng ngữ nghĩa SERIALIZABLE cho một table reference. Khi đọc rồi ghi, UPDLOCK có thể kết hợp với HOLDLOCK để điều phối thao tác cập nhật.

Phạm vi khóa phụ thuộc chỉ mục và access path. Nếu thiếu index phù hợp, SQL Server có thể phải quét nhiều khóa hoặc dùng phạm vi rộng hơn, làm tăng blocking. Hãy xem execution plan và lock information thay vì suy đoán chỉ từ câu SQL.

## 8. PostgreSQL: row lock và predicate tracking không giống nhau

PostgreSQL dùng MVCC cho các truy vấn đọc thông thường. SELECT ... FOR UPDATE khóa các hàng được trả về, nhưng không đặt một row lock lên khoảng trống khi truy vấn không tìm thấy hàng.

Ở mức SERIALIZABLE, PostgreSQL dùng SSI và predicate lock dạng SIREAD để theo dõi các lần đọc. Những khóa này không chặn thao tác ghi như một gap lock thông thường. Chúng giúp hệ thống phát hiện phụ thuộc đọc–ghi có thể dẫn đến lịch không tuần tự hóa được. Nếu có nguy cơ, PostgreSQL có thể hủy một transaction bằng lỗi serialization failure.

Ví dụ:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT booking_id
FROM room_booking
WHERE room_id = 5
  AND booking_date >= DATE '2026-11-20'
  AND booking_date < DATE '2026-11-27';

-- Transaction khác có thể thực hiện INSERT,
-- nhưng lịch commit có thể khiến một transaction bị hủy.

COMMIT;
~~~

Điểm khác biệt:

- InnoDB gap/next-key lock và SQL Server key-range lock có thể chặn insert vào phạm vi.
- PostgreSQL SSI theo dõi phụ thuộc và có thể abort transaction để bảo vệ tính khả tuần tự.
- SELECT ... FOR UPDATE ở PostgreSQL vẫn chỉ khóa hàng được tìm thấy.

Ứng dụng dùng SERIALIZABLE phải nhận diện serialization failure và retry toàn bộ transaction trong một transaction mới. Không được chỉ chạy lại câu INSERT/UPDATE cuối cùng vì quyết định trước đó có thể đã dựa trên snapshot không còn phù hợp.

## 9. Chỉ mục quyết định phạm vi mà engine phải quét

Giả sử truy vấn tìm lượt đặt theo phòng và ngày:

~~~sql
SELECT booking_id
FROM room_booking
WHERE room_id = 5
  AND booking_date >= DATE '2026-11-20'
  AND booking_date < DATE '2026-11-27';
~~~

Một chỉ mục phù hợp có thể là:

~~~sql
CREATE INDEX ix_room_booking_room_date
ON room_booking (room_id, booking_date);
~~~

Với B-tree composite index, các khóa được sắp xếp theo thứ tự cột:

1. room_id
2. booking_date trong từng giá trị room_id

Điều kiện bằng trên room_id xác định một vùng liên tiếp của chỉ mục. Điều kiện khoảng trên booking_date sau đó giới hạn phần quét bên trong vùng đó.

Đây là mẫu thiết kế thường hữu ích:

**Các cột equality trước, cột range sau.**

Ví dụ:

| Điều kiện truy vấn | Chỉ mục gợi ý |
|---|---|
| room_id = 5 | (room_id) |
| room_id = 5 AND booking_date = ngày X | (room_id, booking_date) |
| room_id = 5 AND booking_date nằm trong khoảng | (room_id, booking_date) |
| customer_id = 9 AND status = 'OPEN' AND created_at trong khoảng | (customer_id, status, created_at) |

Thứ tự cột cần dựa trên workload thực tế, độ chọn lọc, các truy vấn khác và khả năng tái sử dụng prefix. Không phải cứ đặt cột có độ chọn lọc cao nhất đầu tiên là luôn đúng; điều kiện equality, range và thứ tự sắp xếp đều ảnh hưởng đến access path.

Với chỉ mục (room_id, booking_date), truy vấn chỉ lọc theo booking_date mà không có room_id có thể không tận dụng hiệu quả prefix đầu tiên. Engine có thể chọn một index khác hoặc quét nhiều dữ liệu hơn.

## 10. Viết điều kiện khoảng để tận dụng index

Một truy vấn có thể có cùng ý nghĩa nghiệp vụ nhưng cách viết ảnh hưởng đến khả năng dùng index.

Ví dụ với ngày:

~~~sql
-- Dạng khoảng nửa mở, thường thân thiện với B-tree index.
SELECT *
FROM room_booking
WHERE booking_date >= DATE '2026-11-20'
  AND booking_date < DATE '2026-11-21';
~~~

So với:

~~~sql
-- Hàm áp dụng lên cột có thể làm giảm khả năng dùng index thông thường.
SELECT *
FROM room_booking
WHERE DATE(booking_timestamp) = DATE '2026-11-20';
~~~

Với timestamp, khoảng nửa mở thường an toàn hơn việc dùng BETWEEN cho hai mốc ngày vì nó tránh phải đoán giá trị thời gian cuối ngày:

~~~sql
WHERE booking_timestamp >= TIMESTAMP '2026-11-20 00:00:00'
  AND booking_timestamp <  TIMESTAMP '2026-11-21 00:00:00'
~~~

BETWEEN thường bao gồm cả hai đầu mút. Với các khoảng thời gian liền kề, điều kiện >= start AND < end giúp tránh việc một thời điểm biên bị tính vào hai khoảng.

Không phải mọi biểu thức có hàm đều không thể dùng index. Một số hệ quản trị hỗ trợ expression index hoặc computed-column index. Nhưng nếu muốn truy vấn dùng index thường, tránh bọc cột được lập chỉ mục trong hàm hoặc phép biến đổi không được index hỗ trợ.

## 11. Unique index không thay thế việc bảo vệ predicate phức tạp

Unique index rất tốt cho điều kiện “mỗi khóa chỉ có một hàng”. Ví dụ:

~~~sql
CREATE UNIQUE INDEX uq_room_booking_day
ON room_booking (room_id, booking_date);
~~~

Nó ngăn hai hàng có cùng phòng và ngày. Nhưng nếu quy tắc là “không có hai khoảng thời gian đặt phòng giao nhau”, một unique index trên (room_id, start_time) không đủ. Hai khoảng có thể bắt đầu khác nhau nhưng vẫn chồng lấn.

Tương tự, một unique index không tự bảo vệ điều kiện tổng hợp như:

- Tổng số lượng đặt của một sự kiện không vượt sức chứa.
- Mỗi ca trực phải còn ít nhất một nhân viên đang hoạt động.
- Tổng phân bổ ngân sách trong một nhóm không vượt giới hạn.

Các điều kiện đó cần constraint chuyên biệt nếu hệ quản trị hỗ trợ, hoặc cơ chế transaction như SERIALIZABLE, khóa phạm vi, guard row hay cập nhật bộ đếm nguyên tử.

## 12. Cách quan sát index và lock thực tế

Không nên kết luận phạm vi khóa chỉ từ cú pháp truy vấn. Hãy kiểm tra execution plan và thông tin khóa của hệ quản trị.

| Hệ quản trị | Kiểm tra kế hoạch | Quan sát khóa |
|---|---|---|
| PostgreSQL | EXPLAIN hoặc EXPLAIN (ANALYZE, BUFFERS) khi có thể chạy an toàn | pg_locks; có thể thấy SIReadLock ở SERIALIZABLE |
| MySQL InnoDB | EXPLAIN và EXPLAIN ANALYZE tùy phiên bản | performance_schema.data_locks và data_lock_waits |
| SQL Server | Actual/estimated execution plan | sys.dm_tran_locks và sys.dm_os_waiting_tasks |

Khi đọc thông tin khóa, cần biết transaction đang chạy ở isolation level nào và câu lệnh có phải locking read hay không. Một SELECT thông thường dưới MVCC có thể không giữ row lock giống như SELECT ... FOR UPDATE.

Hãy kiểm tra cả index được chọn, số hàng được quét, phạm vi khóa và các transaction đang chờ. Nếu một truy vấn theo khoảng quét gần như toàn bảng, phạm vi bảo vệ có thể rộng hơn dự kiến và gây blocking cho nhiều thao tác không liên quan.

## 13. Ví dụ chọn chiến lược theo yêu cầu

| Yêu cầu nghiệp vụ | Cách truy vấn | Cơ chế nên cân nhắc |
|---|---|---|
| Cập nhật một tài khoản đã biết ID | Equality trên primary key | Row lock trên hàng hiện hữu |
| Đảm bảo mã khách hàng không trùng | Equality trên unique key và INSERT | UNIQUE constraint |
| Không cho đặt trùng phòng/ngày | Equality trên tổ hợp phòng/ngày | UNIQUE(room_id, booking_date) |
| Không cho đặt trùng trong một khoảng thời gian | Predicate trên khoảng thời gian | Exclusion constraint, SERIALIZABLE hoặc khóa phạm vi phù hợp |
| Tính tổng các hàng trong một nhóm rồi cập nhật | Range/predicate read và ghi hàng khác | SERIALIZABLE, guard row hoặc aggregate row được cập nhật nguyên tử |
| Chỉ cho phép tạo một bản ghi khi chưa có bản ghi thỏa điều kiện | Check-then-insert theo predicate | Unique constraint nếu biểu diễn được; nếu không, guard/advisory lock hoặc SERIALIZABLE |

## 14. Checklist khi thiết kế truy vấn theo khóa và khoảng

- [ ] Cột tìm kiếm có thực sự là PRIMARY KEY hoặc UNIQUE không?
- [ ] Truy vấn là point lookup hay range scan?
- [ ] Hàng có thể chưa tồn tại tại thời điểm truy vấn không?
- [ ] Cơ chế đang dùng khóa record, gap, key-range hay predicate?
- [ ] Isolation level có thay đổi phạm vi khóa không?
- [ ] Chỉ mục có theo đúng thứ tự cột equality trước, range sau cho workload này không?
- [ ] Điều kiện có dùng biểu thức khiến index khó được sử dụng không?
- [ ] Execution plan có quét phạm vi lớn hơn cần thiết không?
- [ ] Nếu cần ngăn dữ liệu trùng, có thể dùng UNIQUE hoặc constraint phù hợp không?
- [ ] Nếu dùng SERIALIZABLE hoặc SSI, ứng dụng có xử lý retry toàn bộ transaction không?

Truy vấn bằng khóa duy nhất thường định vị một điểm trong chỉ mục và có thể giới hạn phạm vi khóa vào một bản ghi. Truy vấn theo khoảng mô tả cả một dải khóa, vì vậy việc bảo vệ nó có thể cần gap lock, key-range lock hoặc predicate tracking để xử lý phantom. Chỉ mục tốt giúp engine tìm và bảo vệ phạm vi cần thiết hiệu quả hơn, nhưng chỉ mục không tự tạo ra mọi bảo đảm nghiệp vụ. Hãy kết hợp access path phù hợp với constraint hoặc isolation level đúng với quy tắc dữ liệu cần giữ.
