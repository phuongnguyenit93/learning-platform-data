# Quan hệ giữa đọc bằng MVCC và đọc có khóa

Database có thể cho phép một transaction đọc dữ liệu trong khi transaction khác đang cập nhật cùng dữ liệu. Để làm được điều đó, nhiều hệ quản trị dùng **MVCC (Multi-Version Concurrency Control)**: thay vì bắt mọi reader phải chờ writer, engine giữ nhiều phiên bản của một dòng và chọn phiên bản phù hợp với snapshot của transaction.

Bên cạnh cách đọc theo snapshot, database còn hỗ trợ **đọc có khóa (locking read)**. Khi ứng dụng cần đọc một dòng rồi dựa vào giá trị đó để cập nhật hoặc bảo vệ một điều kiện nghiệp vụ, nó có thể yêu cầu database lấy lock trên tài nguyên liên quan. Transaction khác muốn thực hiện thao tác xung đột sẽ phải chờ hoặc nhận lỗi theo quy tắc của engine.

Hai cách đọc này cùng tồn tại trong nhiều hệ quản trị. Chúng giải quyết hai nhu cầu khác nhau:

- Đọc bằng MVCC ưu tiên quan sát một phiên bản dữ liệu nhất quán mà không cần reader giữ shared row lock trong trường hợp thông thường.
- Đọc có khóa ưu tiên phối hợp quyền truy cập giữa các transaction để bảo vệ thao tác tiếp theo, thường bằng cách giữ lock trong transaction.

Hiểu quan hệ giữa chúng giúp chọn đúng cách đọc cho truy vấn báo cáo, màn hình hiển thị, thao tác cập nhật tồn kho, đặt chỗ hoặc những nghiệp vụ cần kiểm tra rồi thay đổi dữ liệu.

## 1. MVCC tạo ra nhiều phiên bản để reader có thể đọc

MVCC là cơ chế quản lý đồng thời bằng nhiều phiên bản của dữ liệu. Khi một transaction cập nhật một dòng, engine tạo hoặc ghi nhận phiên bản mới theo cách triển khai của nó. Phiên bản cũ có thể tiếp tục được giữ lại để transaction khác đọc nếu phiên bản đó thuộc snapshot mà reader được phép quan sát.

Ví dụ, tài khoản A có số dư 1.000.000 đồng. Transaction T1 cập nhật số dư thành 800.000 đồng nhưng chưa commit. Cùng lúc, T2 chạy truy vấn đọc:

~~~text
T1                                  T2
|                                   |
|--- UPDATE balance = 800.000       |
|                                   |
|                              SELECT balance
|                              |
|                              Đọc phiên bản đã commit:
|                              1.000.000
|                                   |
|--- COMMIT ------------------------|
                                    |
                               Truy vấn tiếp theo
                               tùy snapshot và
                               isolation level
~~~

Trong hệ thống MVCC điển hình, T2 có thể đọc phiên bản đã commit trước đó thay vì chờ T1 nhả lock ghi. T2 không nhìn thấy dữ liệu chưa commit của T1, nhờ vậy tránh dirty read.

Snapshot xác định những thay đổi nào được phép nhìn thấy. Snapshot có thể được tạo ở mỗi câu lệnh hoặc được giữ trong suốt transaction, tùy isolation level và database engine. Vì thế, hai câu SELECT trong cùng transaction có thể nhìn thấy hai tập phiên bản khác nhau ở một số chế độ, trong khi ở chế độ snapshot theo transaction, chúng thường nhìn thấy cùng một trạng thái logic.

Một truy vấn đọc theo MVCC thường không lấy shared row lock chỉ để đọc nội dung dòng. Điều này làm giảm việc reader chặn writer và writer chặn reader. Tuy nhiên, không nên hiểu rằng truy vấn MVCC hoàn toàn không dùng bất kỳ cơ chế đồng bộ nào: engine vẫn có thể cần lock metadata, lock cấu trúc hoặc latch nội bộ để bảo vệ buffer pool, index và các cấu trúc bộ nhớ.

## 2. Đọc có khóa yêu cầu database phối hợp quyền truy cập

Đọc có khóa là truy vấn đọc chủ động yêu cầu một loại lock trên dữ liệu được chọn. Ứng dụng dùng nó khi kết quả đọc sẽ quyết định một thao tác cần được phối hợp với transaction khác.

Các dạng thường gặp gồm:

- **Shared locking read:** lấy shared lock để những thao tác ghi xung đột không thể thay đổi tài nguyên trong thời gian lock còn hiệu lực. Một số engine cho phép nhiều reader cùng giữ shared lock.
- **Exclusive locking read:** lấy exclusive lock trên các dòng được chọn, thường để transaction chuẩn bị cập nhật chúng.
- **Update lock:** một số engine có chế độ trung gian nhằm giảm nguy cơ nhiều transaction cùng đọc rồi cùng chuyển sang exclusive lock.

Tên cú pháp và quy tắc tương thích khác nhau theo sản phẩm. Một số ví dụ phổ biến:

~~~sql
-- PostgreSQL và MySQL/InnoDB
BEGIN;

SELECT balance
FROM accounts
WHERE account_id = 42
FOR UPDATE;

-- Kiểm tra điều kiện và cập nhật trong cùng transaction.
UPDATE accounts
SET balance = balance - 100000
WHERE account_id = 42;

COMMIT;
~~~

Trong PostgreSQL, có thể dùng FOR SHARE khi cần khóa chia sẻ trên các dòng được chọn. MySQL/InnoDB hỗ trợ FOR SHARE trong các phiên bản hiện đại; các phiên bản cũ có cú pháp LOCK IN SHARE MODE.

SQL Server dùng table hints thay vì cú pháp FOR UPDATE:

~~~sql
BEGIN TRANSACTION;

SELECT balance
FROM dbo.accounts WITH (UPDLOCK, HOLDLOCK)
WHERE account_id = 42;

-- Kiểm tra điều kiện và cập nhật trong cùng transaction.
UPDATE dbo.accounts
SET balance = balance - 100000
WHERE account_id = 42;

COMMIT TRANSACTION;
~~~

Ví dụ SQL Server trên minh họa yêu cầu update lock và giữ khóa theo ngữ nghĩa serializable cho phạm vi truy vấn. Cách đặt hint cần được chọn theo mục tiêu và index thực tế; không nên sao chép máy móc vào mọi truy vấn.

Khi một locking read gặp lock không tương thích đang được transaction khác giữ, nó thường phải chờ. Sau khi có thể lấy lock, truy vấn tiếp tục theo quy tắc đọc hiện hành của engine. Lock thường được giữ đến cuối transaction hoặc đến thời điểm engine cho phép giải phóng theo loại lock và isolation level.

## 3. Khác biệt cốt lõi giữa hai cách đọc

| Khía cạnh | Đọc bằng MVCC (consistent/snapshot read) | Đọc có khóa (locking read) |
|---|---|---|
| Mục đích | Đọc phiên bản nhìn thấy được theo snapshot | Đọc đồng thời phối hợp quyền truy cập bằng lock |
| Phiên bản dữ liệu | Có thể đọc phiên bản cũ đã commit phù hợp snapshot | Thường đọc trạng thái hiện hành theo quy tắc của engine; chi tiết khác nhau giữa sản phẩm |
| Shared row lock | Thường không cần trong cách đọc MVCC thông thường | Có thể lấy shared lock hoặc loại lock được yêu cầu |
| Chờ writer | Thường không chờ writer chỉ vì writer đang giữ lock ghi trên dòng | Có thể chờ lock không tương thích |
| Chặn writer | Thường không chặn writer bằng shared row lock | Có thể ngăn writer sửa dòng trong thời gian lock còn hiệu lực |
| Thời gian bảo vệ | Bảo vệ tính nhất quán của snapshot theo isolation level | Bảo vệ tài nguyên được khóa trong phạm vi và thời gian lock |
| Trường hợp dùng | Báo cáo, truy vấn hiển thị, đọc dữ liệu không cần khóa để cập nhật | Đọc rồi cập nhật, giữ chỗ, kiểm tra điều kiện cạnh tranh |
| Chi phí/rủi ro | Có thể giữ phiên bản cũ lâu, tăng chi phí lưu version/undo | Có thể tăng lock wait, deadlock và giảm khả năng chạy đồng thời |

Điểm quan trọng là MVCC và lock không loại trừ nhau. Database dùng MVCC để phục vụ nhiều lần đọc nhất quán, đồng thời vẫn dùng lock cho cập nhật và những truy vấn đọc cần phối hợp. Một transaction có thể thực hiện một SELECT thông thường theo snapshot, sau đó thực hiện một locking read hoặc UPDATE để bảo vệ thao tác ghi.

## 4. MVCC read và locking read có thể nhìn thấy phiên bản khác nhau

Trong một số engine, hai cách đọc trong cùng transaction có thể quan sát trạng thái dữ liệu khác nhau.

MySQL/InnoDB là ví dụ dễ thấy: một SELECT thông thường trong transaction thường là consistent read theo snapshot; còn SELECT ... FOR UPDATE và SELECT ... FOR SHARE là locking read, thường được gọi là current read. Current read làm việc với phiên bản hiện hành và lấy lock theo yêu cầu, thay vì đơn thuần đọc phiên bản thuộc snapshot cũ.

Giả sử T1 và T2 cùng chạy ở REPEATABLE READ trong InnoDB:

~~~text
Thời gian       Transaction T1             Transaction T2
----------------------------------------------------------------
t1                                         BEGIN
t2                                         SELECT balance
                                           -> snapshot: 1.000
t3              UPDATE balance = 800
t4              COMMIT
t5                                         SELECT balance
                                           -> consistent read: 1.000
t6                                         SELECT balance
                                           FOR UPDATE
                                           -> current read: 800
t7                                         COMMIT
~~~

Đây là hành vi minh họa cho InnoDB REPEATABLE READ: consistent read tiếp tục dùng snapshot đã tạo, trong khi locking read là current read. Không được suy rộng chính xác hành vi này cho mọi database hoặc mọi isolation level.

Trong PostgreSQL, SELECT thông thường dùng MVCC snapshot; SELECT ... FOR UPDATE khóa các dòng được chọn. Nếu transaction đang ở REPEATABLE READ và dòng đã bị transaction khác thay đổi sau khi snapshot của nó được tạo, locking read có thể kết thúc bằng serialization failure thay vì âm thầm tiếp tục trên phiên bản mới. Ở READ COMMITTED, PostgreSQL có thể chờ transaction cập nhật hoàn tất rồi khóa và trả về phiên bản dòng phù hợp với quy tắc của mức cô lập đó.

Vì vậy, khi trộn snapshot read với locking read trong cùng transaction, cần hiểu rõ engine đang dùng và isolation level. Không thể giả định mọi câu SELECT trong một transaction luôn đọc cùng một phiên bản chỉ vì chúng nằm trong cùng khối BEGIN/COMMIT.

## 5. Khi nào nên dùng MVCC read?

Đọc theo MVCC thường phù hợp khi ứng dụng cần quan sát dữ liệu và không cần ngăn transaction khác cập nhật nó trong lúc đọc.

Ví dụ:

- Trang danh sách đơn hàng cần hiển thị trạng thái đã commit.
- Báo cáo tổng hợp doanh thu theo một snapshot.
- Truy vấn hồ sơ khách hàng để hiển thị.
- Reader cần tiếp tục đọc dù writer đang cập nhật cùng các dòng.
- Một transaction chỉ tính toán hoặc trả dữ liệu, không dùng kết quả đó làm căn cứ cho một cập nhật cần được bảo vệ.

Ví dụ một truy vấn báo cáo:

~~~sql
SELECT status, COUNT(*) AS order_count
FROM orders
GROUP BY status;
~~~

Nếu database dùng MVCC cho consistent read, truy vấn có thể đọc các phiên bản phù hợp snapshot mà không cần lấy shared row lock trên mọi đơn hàng. Writer vẫn có thể cập nhật dữ liệu đồng thời; truy vấn báo cáo nhìn thấy trạng thái theo quy tắc snapshot của transaction.

Điều này không có nghĩa kết quả luôn phản ánh trạng thái mới nhất tại đúng thời điểm trả response. Một snapshot có thể cũ hơn các commit vừa xảy ra. Với báo cáo, điều đó thường chấp nhận được nếu ứng dụng cần một góc nhìn nhất quán. Với nghiệp vụ ra quyết định cần dữ liệu mới nhất, phải xem xét isolation level và cách bảo vệ thao tác.

Một transaction đọc snapshot quá lâu cũng có chi phí. Engine phải giữ các phiên bản cũ đủ lâu để transaction còn có thể nhìn thấy chúng. Tùy sản phẩm, transaction dài có thể làm tăng lượng undo/version cần lưu, cản trở việc dọn dẹp phiên bản cũ hoặc tăng áp lực lưu trữ. Vì vậy, MVCC giảm blocking giữa reader và writer nhưng không làm transaction đọc dài trở nên miễn phí.

## 6. Khi nào nên dùng locking read?

Locking read phù hợp khi ứng dụng cần đọc một tài nguyên rồi dựa trên kết quả đó thực hiện một thay đổi mà transaction khác không được phép chen vào theo cách gây sai nghiệp vụ.

### Ví dụ: chuyển tiền giữa hai tài khoản

Giả sử ứng dụng cần chuyển 100.000 đồng từ tài khoản A sang B. Nó phải xác nhận A đủ tiền và bảo đảm số dư không bị một transaction khác thay đổi theo cách làm cho quyết định chuyển tiền mất hiệu lực.

Một cách làm là khóa hai dòng tài khoản trong cùng transaction:

~~~sql
BEGIN;

SELECT account_id, balance
FROM accounts
WHERE account_id IN (10, 20)
ORDER BY account_id
FOR UPDATE;

-- Ứng dụng kiểm tra số dư tài khoản nguồn.
-- Nếu đủ tiền, cập nhật cả hai tài khoản.

UPDATE accounts
SET balance = balance - 100000
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 100000
WHERE account_id = 20;

COMMIT;
~~~

Ví dụ dùng cú pháp PostgreSQL/MySQL tương thích ở mức khái niệm; cần điều chỉnh theo dialect cụ thể. Khóa các dòng theo một thứ tự ổn định giúp giảm khả năng hai transaction chuyển tiền ngược chiều lấy lock theo thứ tự khác nhau và tạo deadlock.

Nếu không khóa hoặc không dùng một phép cập nhật nguyên tử có điều kiện phù hợp, hai transaction có thể cùng đọc số dư ban đầu rồi cùng quyết định rằng tiền còn đủ. Kết quả cuối cùng có thể vi phạm quy tắc nghiệp vụ.

### Ví dụ: giữ một sản phẩm cuối cùng

Có thể dùng locking read để đọc số lượng rồi cập nhật:

~~~sql
BEGIN;

SELECT available_quantity
FROM inventory
WHERE product_id = 42
FOR UPDATE;

-- Nếu số lượng lớn hơn 0, giảm một đơn vị và tạo reservation.

UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 42;

COMMIT;
~~~

Một cách khác thường gọn hơn là cập nhật có điều kiện:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 42
  AND available_quantity > 0;
~~~

Ứng dụng kiểm tra số dòng được cập nhật. Nếu một dòng được cập nhật, đã giữ được một đơn vị; nếu không có dòng nào, sản phẩm đã hết hoặc không tồn tại. Database điều phối cập nhật cạnh tranh trên dòng đó.

Với thao tác đơn giản như giảm tồn kho, UPDATE có điều kiện thường là lựa chọn tốt vì phép kiểm tra và thay đổi diễn ra trong một câu lệnh nguyên tử. Locking read hữu ích hơn khi cần đọc nhiều giá trị, kiểm tra nhiều điều kiện hoặc thực hiện một chuỗi cập nhật phụ thuộc kết quả đọc.

## 7. Locking read không tự động khóa mọi dữ liệu liên quan đến điều kiện

Một truy vấn FOR UPDATE thường khóa những dòng được chọn theo quy tắc của engine. Điều đó không đồng nghĩa nó luôn khóa mọi dòng có thể xuất hiện trong tương lai hoặc khóa toàn bộ điều kiện WHERE.

Ví dụ, ứng dụng kiểm tra chưa có lịch đặt phòng nào trùng khoảng thời gian từ 10:00 đến 11:00 rồi mới thêm một lịch mới. Nếu truy vấn không tìm thấy dòng nào, có thể không có row nào để khóa. Một transaction khác vẫn có thể đồng thời kiểm tra cùng khoảng trống và chèn lịch trùng.

Cần phân biệt:

- **Row lock:** khóa những dòng hiện có được truy vấn chọn.
- **Range/gap/next-key lock:** một số engine có thể khóa cả khoảng khóa hoặc khoảng trống index để ngăn insert cạnh tranh.
- **Predicate locking hoặc Serializable isolation:** engine bảo vệ điều kiện logic ở mức cần thiết để ngăn lịch thực thi không tuần tự hóa được; cách triển khai có thể dùng khóa hoặc phát hiện xung đột rồi hủy transaction.

Ví dụ, InnoDB có thể dùng next-key lock trong một số truy vấn locking ở REPEATABLE READ khi index và điều kiện truy vấn phù hợp. PostgreSQL dùng Serializable Snapshot Isolation để theo dõi phụ thuộc đọc/ghi và có thể hủy transaction khi phát hiện nguy cơ serialization anomaly; predicate lock trong cơ chế này không nhất thiết hoạt động như một row lock chặn writer. SQL Server có thể dùng HOLDLOCK/SERIALIZABLE và key-range locks tùy kế hoạch truy vấn.

Vì vậy, nếu nghiệp vụ cần bảo vệ một điều kiện trên tập dòng hoặc một khoảng mà hiện chưa có dòng nào, hãy kiểm tra ngữ nghĩa của engine, index, isolation level và constraint. Một locking read trên các dòng hiện có có thể chưa đủ.

## 8. MVCC snapshot vẫn có thể gặp write skew

MVCC snapshot giúp transaction đọc một trạng thái nhất quán, nhưng snapshot isolation không đồng nghĩa với serializable isolation.

Xét quy tắc trực ca: luôn phải có ít nhất một bác sĩ đang trực. Hiện có hai bác sĩ A và B cùng trực. Hai transaction chạy đồng thời:

~~~text
T1:                                  T2:
Đọc snapshot: A và B đang trực      Đọc snapshot: A và B đang trực
Kiểm tra: còn B trực                 Kiểm tra: còn A trực
Cập nhật A = OFF                    Cập nhật B = OFF
COMMIT                              COMMIT
~~~

Mỗi transaction cập nhật một dòng khác nhau nên có thể không xung đột ghi trực tiếp. Cả hai cùng dựa trên snapshot cho thấy vẫn có người khác trực. Nếu isolation level chỉ cung cấp snapshot isolation và engine không phát hiện phụ thuộc này, cả hai có thể commit, khiến không còn ai trực.

Hiện tượng này gọi là **write skew**. Nó cho thấy một snapshot nhất quán không tự bảo vệ mọi bất biến nghiệp vụ có liên quan đến nhiều dòng.

Có thể xử lý bằng nhiều cách, tùy nghiệp vụ:

- Dùng SERIALIZABLE để engine bảo đảm kết quả tương đương một thứ tự tuần tự; transaction có thể bị hủy và cần retry.
- Khóa một tài nguyên điều phối chung, chẳng hạn một dòng đại diện cho lịch trực, trước khi kiểm tra và cập nhật.
- Thiết kế constraint hoặc mô hình dữ liệu để database có thể thực thi bất biến trực tiếp.
- Dùng một cơ chế reservation hoặc phân quyền cập nhật phù hợp với nghiệp vụ.

Không nên mặc định rằng thêm FOR UPDATE vào một SELECT bất kỳ là đủ. Cần khóa đúng tập tài nguyên bảo vệ bất biến, hoặc dùng mức cô lập có bảo đảm phù hợp.

## 9. Quan hệ với isolation level

Isolation level quyết định transaction được phép nhìn thấy phiên bản nào và những xung đột nào phải được ngăn chặn hoặc phát hiện. MVCC và locking read là các cơ chế mà engine phối hợp để thực hiện mức cô lập đó.

| Mức cô lập hoặc chế độ | Cách đọc thường gặp | Điều cần lưu ý |
|---|---|---|
| READ COMMITTED | Mỗi statement có thể đọc snapshot của dữ liệu đã commit tại thời điểm statement bắt đầu; một số engine dùng shared lock thay vì versioning nếu không bật chế độ MVCC tương ứng | Hai SELECT trong cùng transaction có thể thấy dữ liệu khác nhau |
| REPEATABLE READ | Một số engine giữ snapshot cho consistent reads trong suốt transaction; engine khác có quy tắc riêng | Không thể suy ra cùng một hành vi giữa mọi sản phẩm; cần xem locking read có dùng current version hay không |
| SNAPSHOT | Các truy vấn đọc thường dựa trên snapshot của transaction | Giảm reader-writer blocking nhưng có thể còn write skew tùy engine và định nghĩa isolation |
| SERIALIZABLE | Engine phải bảo đảm kết quả tương đương một thứ tự thực thi tuần tự | Có thể dùng range/predicate lock hoặc phát hiện xung đột; transaction có thể chờ hoặc bị hủy để retry |

Tên isolation level giống nhau không bảo đảm chi tiết triển khai giống nhau. Ví dụ:

- PostgreSQL dùng MVCC cho SELECT thông thường; READ COMMITTED lấy snapshot theo statement, còn REPEATABLE READ giữ snapshot theo transaction và có thể báo serialization failure khi locking read gặp dòng đã thay đổi.
- MySQL/InnoDB dùng consistent read cho SELECT thông thường; ở REPEATABLE READ, consistent read có thể dùng snapshot ổn định trong transaction trong khi locking read là current read.
- SQL Server có READ COMMITTED dựa trên lock theo cấu hình mặc định truyền thống, nhưng READ_COMMITTED_SNAPSHOT có thể chuyển các truy vấn đọc READ COMMITTED sang row versioning. SNAPSHOT là một chế độ riêng và locking hints có thể thay đổi hành vi truy cập.

Khi đọc tài liệu hoặc phân tích wait, cần xác định đúng sản phẩm, phiên bản, cấu hình database và isolation level của session.

## 10. Những nhầm lẫn thường gặp

**“MVCC có nghĩa là không có lock.”**

Không. MVCC giúp reader đọc phiên bản phù hợp mà thường không cần shared row lock. Writer vẫn cần lock hoặc cơ chế điều phối tương ứng; engine còn có lock metadata, lock cấu trúc và latch nội bộ.

**“SELECT thông thường luôn đọc dữ liệu mới nhất.”**

Không. Truy vấn có thể đọc phiên bản thuộc snapshot đã tạo trước đó. Snapshot mới được lấy theo statement hay transaction phụ thuộc isolation level và engine.

**“SELECT FOR UPDATE chỉ là SELECT nhưng chậm hơn.”**

Không. Đây là yêu cầu đồng bộ có ảnh hưởng đến transaction khác. Nó có thể chờ lock, chặn writer và giữ lock đến khi transaction kết thúc.

**“Đã dùng MVCC thì không cần SERIALIZABLE.”**

Không. Snapshot có thể nhất quán nhưng vẫn cho phép write skew hoặc những bất thường khác tùy engine. Nếu nghiệp vụ có bất biến liên quan đến nhiều dòng, cần chọn isolation level hoặc cơ chế khóa phù hợp.

**“FOR UPDATE khóa cả những dòng chưa tồn tại.”**

Không phải lúc nào cũng vậy. Khóa khoảng, gap hoặc predicate phụ thuộc engine, isolation level, index và kế hoạch thực thi. Nếu cần bảo vệ điều kiện trên khoảng trống, phải xác minh cơ chế cụ thể.

**“Đọc có khóa luôn tốt hơn đọc MVCC vì dữ liệu mới hơn.”**

Không. Locking read làm tăng phối hợp và có thể giảm khả năng chạy đồng thời. Với báo cáo hoặc truy vấn hiển thị, snapshot read thường đủ và ít gây chặn hơn. Chỉ dùng locking read khi nghiệp vụ cần bảo vệ tài nguyên hoặc điều kiện cụ thể.

## 11. Cách chọn trong ứng dụng

Có thể chọn cách đọc bằng cách xem kết quả truy vấn sẽ được dùng làm gì:

| Nhu cầu | Cách tiếp cận thường phù hợp |
|---|---|
| Hiển thị dữ liệu đã commit | SELECT thông thường theo MVCC nếu engine hỗ trợ |
| Chạy báo cáo cần snapshot nhất quán | Chọn isolation level phù hợp, chú ý thời gian sống của snapshot |
| Đọc dòng rồi cập nhật chính dòng đó | Locking read hoặc UPDATE có điều kiện |
| Giảm tồn kho, tăng bộ đếm có điều kiện | UPDATE nguyên tử với điều kiện trong WHERE và kiểm tra số dòng |
| Bảo vệ nhiều dòng khi chuyển tiền | Khóa các dòng liên quan theo thứ tự ổn định hoặc dùng thao tác cập nhật nguyên tử phù hợp |
| Bảo vệ điều kiện trên một tập dòng/khoảng trống | Xem xét SERIALIZABLE, range/predicate locking, constraint hoặc tài nguyên điều phối |
| Nhiều transaction cùng kiểm tra bất biến nghiệp vụ | Chọn cơ chế phát hiện xung đột hoặc khóa chung để bảo vệ bất biến |

Một quy trình đọc rồi ghi nên được thiết kế như một đơn vị nghiệp vụ rõ ràng:

1. Xác định dữ liệu nào cần đọc và bất biến nào phải giữ.
2. Nếu chỉ cần quan sát, dùng consistent read phù hợp với isolation level.
3. Nếu cần ngăn transaction khác thay đổi tài nguyên trong lúc ra quyết định, dùng locking read hoặc câu lệnh cập nhật nguyên tử.
4. Nếu điều kiện liên quan đến nhiều dòng hoặc khoảng dữ liệu, xác định rõ phạm vi cần bảo vệ; không giả định row lock là đủ.
5. Giữ transaction ngắn, xử lý lỗi lock timeout/deadlock hoặc serialization failure bằng chiến lược retry phù hợp.
6. Kiểm tra lại hành vi trên đúng database engine và phiên bản triển khai.

## Kết luận

Đọc bằng MVCC và đọc có khóa là hai cách đọc bổ sung cho nhau. MVCC cho phép transaction quan sát phiên bản dữ liệu phù hợp snapshot, thường giảm việc reader chặn writer. Locking read yêu cầu database phối hợp quyền truy cập vào tài nguyên được chọn, hữu ích khi kết quả đọc quyết định một thao tác cập nhật hoặc một điều kiện nghiệp vụ cần được bảo vệ.

MVCC không loại bỏ lock, và locking read không tự bảo vệ mọi điều kiện logic. Cần chọn cách đọc theo mục đích, hiểu snapshot và isolation level của engine, đồng thời xác định đúng phạm vi dữ liệu cần khóa. Khi cần bảo vệ bất biến phức tạp trên nhiều dòng, có thể phải dùng SERIALIZABLE, range/predicate protection, constraint hoặc một tài nguyên điều phối chung.
