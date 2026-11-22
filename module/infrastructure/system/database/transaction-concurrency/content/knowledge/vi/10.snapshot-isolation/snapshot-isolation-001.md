# Mô hình đọc trên ảnh chụp và xác nhận thay đổi

Trong các hệ quản trị cơ sở dữ liệu dùng MVCC (Multi-Version Concurrency Control), một transaction có thể đọc dữ liệu từ **ảnh chụp nhất quán (snapshot)**: nó nhìn thấy những phiên bản đã commit và thỏa điều kiện hiển thị tại một thời điểm xác định. Trong khi transaction đang xử lý, transaction khác vẫn có thể cập nhật và commit phiên bản mới. Transaction đọc tiếp tục làm việc với ảnh chụp của mình thay vì tự động chuyển sang dữ liệu mới nhất ở mỗi lần đọc.

Cơ chế này giúp giảm xung đột giữa reader và writer, đồng thời cho phép các truy vấn trong cùng transaction có kết quả ổn định. Tuy nhiên, một ảnh chụp chỉ cho biết dữ liệu đã như thế nào tại thời điểm đọc. Trước khi ghi kết quả tính toán trở lại database, hệ thống vẫn cần **xác nhận thay đổi (validate changes)** để biết dữ liệu liên quan có bị transaction khác sửa hay không và các quy tắc nghiệp vụ còn đúng hay không.

Đây là hai phần liên quan nhưng khác nhau:

- **Snapshot read:** transaction đọc một tập phiên bản nhất quán theo mốc thời gian của nó.
- **Validation:** database hoặc ứng dụng kiểm tra xem những thay đổi dự định ghi có còn hợp lệ khi xét đến các transaction cạnh tranh hay không.

## 1. Ảnh chụp dữ liệu được hình thành như thế nào?

### 1.1. MVCC lưu nhiều phiên bản

Nếu mỗi lần UPDATE đều ghi đè trực tiếp lên giá trị cũ, một transaction đọc có thể phải chờ transaction ghi hoàn tất để tránh nhìn thấy dữ liệu chưa commit. MVCC cho phép hệ quản trị duy trì nhiều phiên bản của một dòng trong một khoảng thời gian.

Ví dụ, bảng Account có số dư ban đầu là 1.000:

~~~text
Thời gian
  |
  |  T1 đọc Account.balance
  |  Nhìn thấy phiên bản V1 = 1.000
  |
  |  T2 cập nhật balance = 1.200
  |  T2 COMMIT
  |
  |  T1 đọc Account.balance lần nữa
  |  Vẫn nhìn thấy phiên bản V1 = 1.000
  |
  |  T1 kết thúc
  |
  +---------------------------------->

Các phiên bản:
  V1: balance = 1.000  (được T1 nhìn thấy)
  V2: balance = 1.200  (được commit sau mốc snapshot của T1)
~~~

T1 tiếp tục nhìn thấy V1 vì V2 được commit sau mốc snapshot của T1. Khi T1 kết thúc và không còn transaction nào cần phiên bản cũ, hệ quản trị có thể thu hồi phiên bản đó theo cơ chế quản lý version/undo của sản phẩm.

Snapshot không nhất thiết là một bản sao vật lý của toàn bộ database. Thông thường, hệ quản trị kết hợp dữ liệu hiện tại với chuỗi phiên bản cũ, thông tin transaction và mốc hiển thị để dựng lại giá trị mà transaction được phép nhìn thấy.

### 1.2. Quy tắc hiển thị phiên bản

Một snapshot thường dựa trên mốc thời gian hoặc thứ tự transaction. Khi đọc một dòng, hệ quản trị chọn phiên bản phù hợp với snapshot:

- Phiên bản đã commit trước mốc snapshot có thể được nhìn thấy.
- Phiên bản do transaction khác tạo ra nhưng chưa commit tại mốc snapshot không được xem là dữ liệu đã commit.
- Phiên bản được commit sau mốc snapshot không xuất hiện trong snapshot hiện tại.
- Transaction thường nhìn thấy các thay đổi do chính nó thực hiện, theo quy tắc read-your-own-writes của hệ quản trị.

Nhờ đó, transaction không đọc phải dữ liệu chưa commit của transaction khác. Các lần đọc lặp lại trong cùng snapshot cũng không bị thay đổi chỉ vì transaction khác vừa commit.

Cần phân biệt snapshot với một bản sao bất biến do ứng dụng tự tạo. Snapshot là quy tắc đọc do database thực thi; nó có thể được dựng từ nhiều phiên bản và được kết hợp với các thao tác ghi, khóa và kiểm tra xung đột.

## 2. Snapshot có phạm vi thời gian nào?

Một điểm quan trọng là **snapshot có thể được tạo theo từng câu lệnh hoặc theo toàn transaction**, tùy isolation level và DBMS. Vì vậy, hai câu SELECT trong cùng transaction không phải lúc nào cũng nhìn thấy cùng một mốc dữ liệu.

| Hệ quản trị và chế độ | Phạm vi ảnh chụp đọc thường gặp |
|---|---|
| SQL Server với READ_COMMITTED_SNAPSHOT | Mỗi câu lệnh READ COMMITTED đọc theo snapshot tại thời điểm câu lệnh bắt đầu |
| SQL Server với SNAPSHOT | Một snapshot nhất quán ở cấp transaction |
| PostgreSQL READ COMMITTED | Mỗi câu lệnh có snapshot riêng |
| PostgreSQL REPEATABLE READ | Snapshot được giữ ổn định trong transaction, được thiết lập khi transaction bắt đầu thực thi câu lệnh đầu tiên phù hợp |
| MySQL InnoDB READ COMMITTED | Mỗi consistent read tạo snapshot mới |
| MySQL InnoDB REPEATABLE READ | Các consistent read thường dùng snapshot được thiết lập từ lần consistent read đầu tiên của transaction |
| Oracle READ COMMITTED | Mỗi câu lệnh đọc có tính nhất quán tại thời điểm câu lệnh bắt đầu |
| Oracle SERIALIZABLE | Transaction đọc theo một ảnh chụp nhất quán ở cấp transaction, kèm quy tắc phát hiện xung đột ghi của Oracle |

Bảng này mô tả các hành vi phổ biến của những chế độ được nêu. Cần kiểm tra đúng phiên bản, loại câu lệnh và cấu hình cụ thể trước khi dựa vào chúng để thiết kế ứng dụng.

### 2.1. Snapshot ở cấp câu lệnh

Giả sử T1 chạy hai câu SELECT trong READ COMMITTED có row versioning:

~~~text
T1: SELECT balance       -> nhìn thấy 1.000
T2: UPDATE balance = 1.200; COMMIT
T1: SELECT balance       -> nhìn thấy 1.200
~~~

Hai câu SELECT của T1 dùng hai snapshot khác nhau. T1 không đọc dữ liệu chưa commit, nhưng kết quả giữa hai câu lệnh có thể khác nhau vì T2 đã commit ở giữa.

Đây là hành vi thường gặp của READ COMMITTED khi dùng row versioning ở SQL Server, PostgreSQL READ COMMITTED, InnoDB READ COMMITTED và Oracle READ COMMITTED.

### 2.2. Snapshot ở cấp transaction

Với snapshot cấp transaction, T1 tiếp tục đọc cùng một ảnh chụp:

~~~text
T1: BEGIN; tạo snapshot S1
T1: SELECT balance       -> nhìn thấy 1.000
T2: UPDATE balance = 1.200; COMMIT
T1: SELECT balance       -> vẫn nhìn thấy 1.000
T1: COMMIT
~~~

T1 có một góc nhìn ổn định trong toàn transaction. Điều này hữu ích khi cần đọc nhiều bảng, tính toán và đưa ra quyết định dựa trên cùng một trạng thái dữ liệu.

Nhưng snapshot ổn định không có nghĩa là mọi dữ liệu mà T1 đọc vẫn còn mới nhất khi T1 ghi. T2 có thể đã commit phiên bản mới trong lúc T1 đang tính toán. Phần xác nhận thay đổi xử lý khoảng cách giữa thời điểm đọc và thời điểm ghi đó.

## 3. Đọc trên snapshot khác gì với đọc có khóa?

Với MVCC, một consistent read có thể đọc phiên bản cũ phù hợp với snapshot mà không phải chờ writer đang tạo phiên bản mới. Writer cũng có thể tiếp tục cập nhật trong khi reader đang đọc phiên bản cũ.

~~~text
Reader T1                         Writer T2
---------                         ---------
Đọc phiên bản V1
                                  Tạo phiên bản V2
Đọc tiếp V1
                                  COMMIT V2
Đọc tiếp V1
COMMIT
~~~

Lợi ích là giảm blocking giữa reader và writer. Tuy nhiên, không nên suy luận rằng MVCC loại bỏ toàn bộ khóa:

- Các thao tác ghi vẫn cần phối hợp để bảo vệ cập nhật và cấu trúc dữ liệu.
- Hai transaction ghi cùng một dòng có thể xung đột.
- Một số câu lệnh đọc có khóa chủ động yêu cầu phiên bản hiện hành và khóa tài nguyên.
- DDL, khóa bảng, khóa chỉ mục và các cơ chế nội bộ khác vẫn có thể gây chờ.
- Các transaction dài có thể giữ những phiên bản cũ tồn tại lâu hơn.

Một khác biệt quan trọng xuất hiện ở các câu lệnh khóa đọc. Trong MySQL InnoDB, consistent read thông thường đọc theo snapshot, còn SELECT ... FOR UPDATE và SELECT ... FOR SHARE là locking read, có hành vi đọc hiện hành và lấy khóa. PostgreSQL SELECT ... FOR UPDATE cũng khóa các dòng được chọn và có thể phải chờ transaction đang cập nhật chúng. SQL Server có các lock hint như UPDLOCK và HOLDLOCK để thay đổi cách lấy khóa. Không nên trộn lẫn kết quả của snapshot read và locking read mà không hiểu ngữ nghĩa của DBMS.

## 4. Vì sao phải xác nhận thay đổi sau khi đọc snapshot?

Hãy xét một ứng dụng quản lý tồn kho. Một transaction đọc số lượng hàng là 10, rồi tính toán rằng có thể bán 3 sản phẩm. Trong lúc ứng dụng đang xử lý, transaction khác bán 8 sản phẩm và commit.

~~~text
Ban đầu: quantity = 10

T1 đọc snapshot: quantity = 10
T1 tính: 10 - 3 = 7

T2 đọc/cập nhật và COMMIT:
quantity = 2

T1 muốn ghi quantity = 7
~~~

Nếu T1 ghi đè giá trị 7 mà không có kiểm tra phù hợp, phần cập nhật của T2 có thể bị mất. Kết quả còn 7 dù thực tế chỉ còn 2 sản phẩm trước khi T1 ghi.

Đây là lý do không thể chỉ dựa vào kết quả SELECT cũ để ghi một giá trị tuyệt đối. Trước khi ghi, hệ thống phải xác định một trong các điều sau:

1. Dòng chưa bị transaction khác thay đổi kể từ lúc T1 đọc.
2. Phép cập nhật được thực hiện nguyên tử dựa trên giá trị hiện hành và điều kiện nghiệp vụ.
3. Xung đột được phát hiện và transaction phải hủy hoặc thử lại.
4. Quy tắc nghiệp vụ được bảo vệ bằng isolation mạnh hơn, khóa phù hợp hoặc constraint.

Cách xác nhận phụ thuộc loại thay đổi. Một cập nhật trên cùng dòng thường có thể được phát hiện bằng version hoặc write-write conflict. Một quy tắc liên quan đến nhiều dòng lại cần cách bảo vệ rộng hơn.

## 5. Xác nhận xung đột ghi (write-write conflict)

Trong nhiều triển khai snapshot isolation, nếu T1 và T2 cùng sửa một dòng dựa trên snapshot cũ, hệ quản trị áp dụng quy tắc phát hiện xung đột ghi. Một transaction có thể phải thất bại thay vì ghi đè kết quả của transaction đã commit trước đó. Cách và thời điểm phát hiện cụ thể khác nhau giữa DBMS.

Ví dụ:

~~~text
Giá trị ban đầu: balance = 1.000

T1 đọc V1 = 1.000
T2 đọc V1 = 1.000

T1 ghi balance = 1.100
T1 COMMIT

T2 cố ghi balance = 900
Hệ quản trị phát hiện dòng đã được T1 thay đổi
T2 bị báo xung đột và phải ROLLBACK
~~~

Cơ chế này thường được gọi là first-committer-wins hoặc một biến thể phát hiện xung đột ghi. Nó ngăn hai transaction cùng ghi một phiên bản cũ của cùng dòng rồi âm thầm ghi đè lên nhau.

Tuy nhiên, quy tắc đó chỉ bảo vệ những xung đột mà hệ quản trị nhận diện được. Nếu hai transaction sửa hai dòng khác nhau nhưng cùng phụ thuộc vào một điều kiện nghiệp vụ, cả hai có thể vẫn commit. Trường hợp này được gọi là **write skew**.

### 5.1. Ví dụ xác nhận bằng cột version

Một cách phổ biến ở tầng ứng dụng là thêm cột version hoặc row_version. Khi đọc, ứng dụng lưu giá trị version hiện tại. Khi ghi, câu UPDATE chỉ thành công nếu version trong database vẫn bằng giá trị đã đọc.

Giả sử bảng Product có các cột ProductId, Price và Version:

~~~sql
UPDATE dbo.Product
SET Price = @newPrice,
    Version = Version + 1
WHERE ProductId = @productId
  AND Version = @versionRead;
~~~

Ứng dụng kiểm tra số dòng bị ảnh hưởng ngay sau câu UPDATE:

- Nếu cập nhật đúng một dòng, version vẫn khớp tại thời điểm cập nhật; thao tác có thể tiếp tục COMMIT.
- Nếu cập nhật không có dòng nào, bản ghi có thể đã bị xóa hoặc version đã thay đổi. Ứng dụng cần tải lại dữ liệu, thông báo xung đột hoặc thử lại toàn bộ thao tác.

Ví dụ đầy đủ với T-SQL:

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.Product
SET Price = @newPrice,
    Version = Version + 1
WHERE ProductId = @productId
  AND Version = @versionRead;

IF @@ROWCOUNT = 0
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50001, 'Product was changed by another transaction.', 1;
END;

COMMIT TRANSACTION;
~~~

Điều kiện version tạo ra thao tác compare-and-swap ở cấp database: chỉ thay đổi dòng nếu nó vẫn mang phiên bản mà ứng dụng đã đọc. Việc tăng Version phải nằm trong cùng câu UPDATE để hai transaction cạnh tranh không thể cùng thành công với một version cũ.

Trong thực tế, cần phân biệt trường hợp không tìm thấy ProductId với trường hợp version không khớp nếu ứng dụng cần thông báo khác nhau. Nếu dùng SQL Server rowversion, cột đó là giá trị nhị phân do database tự cập nhật; ứng dụng so sánh giá trị đã đọc thay vì tự tăng số nguyên.

Cách kiểm tra version đặc biệt hữu ích khi:

- Nhiều người cùng chỉnh sửa một hồ sơ hoặc tài liệu.
- Một request đọc dữ liệu, xử lý bên ngoài database rồi mới gửi lệnh cập nhật.
- Không muốn giữ khóa trong suốt thời gian người dùng mở màn hình chỉnh sửa.
- Cần trả về thông báo "dữ liệu đã thay đổi, hãy tải lại" thay vì ghi đè âm thầm.

Cột version bảo vệ những dòng được kiểm tra. Nó không tự động bảo vệ quy tắc nghiệp vụ liên quan đến nhiều dòng hoặc nhiều bảng.

### 5.2. Xác nhận bằng điều kiện cập nhật nguyên tử

Nếu nghiệp vụ có thể biểu diễn trực tiếp trong câu UPDATE, hãy đặt điều kiện ngay trong câu lệnh để database kiểm tra cùng lúc với thao tác ghi.

Ví dụ trừ tồn kho nhưng không cho số lượng âm:

~~~sql
UPDATE dbo.Inventory
SET Quantity = Quantity - @requested
WHERE ProductId = @productId
  AND Quantity >= @requested;
~~~

Sau câu lệnh, ứng dụng kiểm tra số dòng bị ảnh hưởng:

- Một dòng được cập nhật: điều kiện đủ hàng đã đúng tại thời điểm database thực hiện thao tác.
- Không có dòng được cập nhật: sản phẩm không tồn tại hoặc số lượng hiện hành không đủ.

Câu lệnh này tốt hơn cách SELECT số lượng, tính giá trị mới ở ứng dụng rồi UPDATE bằng một số tuyệt đối, vì điều kiện và phép trừ được thực hiện như một thao tác database. Tuy nhiên, nếu nghiệp vụ còn phụ thuộc vào nhiều bảng hoặc nhiều dòng, cần xác định thêm các quy tắc đồng thời.

## 6. Write skew: snapshot ổn định vẫn có thể vi phạm quy tắc nghiệp vụ

Snapshot isolation thường ngăn dirty read và cung cấp góc nhìn ổn định. Nó không tự động bảo đảm mọi transaction chạy đồng thời tương đương với một thứ tự tuần tự duy nhất.

Xét quy tắc: một ca trực phải luôn có ít nhất một bác sĩ đang trực. Ban đầu có hai bác sĩ A và B đều đang trực.

~~~text
Trạng thái ban đầu:
Doctor A: on_call = TRUE
Doctor B: on_call = TRUE

T1 (xử lý bác sĩ A)               T2 (xử lý bác sĩ B)
-------------------               -------------------
Đọc snapshot: có 2 người trực     Đọc snapshot: có 2 người trực
Quyết định A có thể nghỉ           Quyết định B có thể nghỉ
UPDATE A = FALSE                  UPDATE B = FALSE
COMMIT                            COMMIT

Kết quả:
Doctor A: on_call = FALSE
Doctor B: on_call = FALSE
Số người trực = 0
~~~

T1 và T2 sửa hai dòng khác nhau. Vì write set của chúng không giao nhau, cơ chế phát hiện xung đột ghi trên cùng dòng có thể không phát hiện vấn đề. Mỗi transaction đều nhìn thấy hai bác sĩ trực trong snapshot của mình và đều kết luận rằng việc cho một người nghỉ là hợp lệ.

Đây là write skew: các transaction đọc những dữ liệu có liên quan đến cùng một invariant nhưng ghi vào các dòng khác nhau. Khi cả hai commit, trạng thái tổng thể vi phạm invariant.

Các ví dụ tương tự:

- Hệ thống phân ca phải luôn có tối thiểu một nhân viên trực.
- Hạn mức tín dụng tổng của nhiều tài khoản không được vượt quá một giới hạn.
- Số ghế được đặt không được vượt quá sức chứa.
- Một bệnh nhân không được có hai lịch hẹn trùng khung giờ, dù hai request ghi vào hai bảng hoặc hai dòng khác nhau.
- Một nhóm tài nguyên phải luôn có ít nhất một thành viên ở trạng thái hoạt động.

Vì vậy, cần phân biệt hai loại xung đột:

| Loại | Ví dụ | Cách xử lý thường gặp |
|---|---|---|
| Write-write conflict | Hai transaction cùng sửa một ProductId | Snapshot isolation có thể phát hiện và hủy một transaction |
| Write skew | Hai transaction sửa hai DoctorId khác nhau nhưng cùng vi phạm quy tắc tối thiểu một người trực | Cần bảo vệ invariant bằng SERIALIZABLE, khóa/guard row, constraint phù hợp hoặc thiết kế cập nhật nguyên tử |

Không nên dùng việc "không có lỗi xung đột ghi" làm bằng chứng rằng quy tắc nghiệp vụ vẫn được bảo toàn.

## 7. Các cách bảo vệ invariant nhiều dòng

### 7.1. Dùng SERIALIZABLE khi cần thứ tự tuần tự

Isolation level SERIALIZABLE yêu cầu kết quả của các transaction đồng thời tương đương với một thứ tự thực thi tuần tự hợp lệ. Hệ quản trị có thể dùng khóa phạm vi, predicate locking hoặc cơ chế phát hiện xung đột để ngăn các transaction cùng commit nếu chúng tạo ra kết quả không thể tuần tự hóa.

Ví dụ khái niệm:

~~~sql
-- Cú pháp minh họa theo SQL Server
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;

SELECT DoctorId
FROM dbo.Doctor
WHERE OnCall = 1;

-- Kiểm tra quy tắc và cập nhật người trực trong cùng transaction.

COMMIT TRANSACTION;
~~~

Cách triển khai cụ thể phụ thuộc DBMS:

- SQL Server SERIALIZABLE có thể dùng key-range locks để bảo vệ cả phạm vi dữ liệu được truy vấn.
- PostgreSQL SERIALIZABLE dùng Serializable Snapshot Isolation (SSI) để phát hiện các cấu trúc phụ thuộc nguy hiểm; một transaction có thể bị hủy với serialization failure và cần được thử lại.
- MySQL InnoDB SERIALIZABLE thay đổi cách đọc và khóa so với consistent read thông thường; hành vi còn phụ thuộc loại transaction và cấu hình.
- Oracle SERIALIZABLE cung cấp transaction-level read consistency và có thể báo lỗi khi một transaction không thể tiếp tục theo quy tắc serializable.

SERIALIZABLE có thể làm tăng blocking, số lần transaction bị hủy hoặc chi phí xử lý. Chỉ dùng cho phạm vi nghiệp vụ thực sự cần invariant mạnh, rồi đo dưới tải đồng thời đại diện.

### 7.2. Dùng một dòng khóa bảo vệ (guard row)

Nếu nhiều transaction cần thay đổi cùng một quy tắc tổng thể, có thể tạo một dòng đại diện cho tài nguyên hoặc nhóm nghiệp vụ đó. Mỗi transaction phải khóa dòng này trước khi đọc và cập nhật các dòng thành viên.

Ví dụ, một dòng Shift có ShiftId và thông tin trạng thái ca trực. Các thao tác thay đổi người trực trong cùng ca đều khóa dòng Shift tương ứng trước khi kiểm tra số người còn trực.

Với hệ quản trị hỗ trợ SELECT FOR UPDATE:

~~~sql
BEGIN;

SELECT ShiftId
FROM Shift
WHERE ShiftId = :shift_id
FOR UPDATE;

-- Đọc danh sách người trực, kiểm tra invariant,
-- rồi cập nhật người được cho nghỉ.

COMMIT;
~~~

Trong SQL Server, có thể dùng cơ chế khóa phù hợp như UPDLOCK trên dòng guard, kết hợp transaction và điều kiện phạm vi khi cần. Cú pháp và mức bảo vệ phải được kiểm tra theo execution plan, index và isolation level.

Guard row tạo một điểm tuần tự hóa rõ ràng cho những transaction cùng nhóm. Đổi lại, các thao tác trên cùng nhóm phải lần lượt qua dòng đó. Nếu khóa guard quá rộng, throughput có thể giảm; nếu khóa sai phạm vi, write skew vẫn có thể xảy ra.

### 7.3. Dùng constraint khi quy tắc có thể biểu diễn ở database

Constraint là lớp bảo vệ quan trọng vì mọi đường ghi dữ liệu đều phải tuân theo nó, kể cả ứng dụng hoặc batch job khác.

Ví dụ:

- UNIQUE bảo đảm giá trị khóa không trùng.
- CHECK bảo đảm điều kiện trên một dòng, chẳng hạn Quantity >= 0.
- FOREIGN KEY bảo đảm quan hệ tham chiếu hợp lệ.
- Exclusion constraint của PostgreSQL có thể bảo vệ một số quy tắc không giao nhau trên các khoảng dữ liệu.

Constraint trên một dòng thường không thể tự diễn đạt quy tắc tổng hợp như "ít nhất một bác sĩ trong nhóm phải trực". Khi đó cần thiết kế bảng/aggregate phù hợp, guard row, trigger có cơ chế đồng thời đúng hoặc SERIALIZABLE. Không nên chỉ viết một truy vấn COUNT rồi cho rằng constraint đã được bảo vệ; hai transaction vẫn có thể cùng đọc một kết quả cũ.

### 7.4. Biến quy tắc thành một cập nhật nguyên tử

Một số invariant có thể được mô hình hóa bằng một dòng tổng hợp có bộ đếm hoặc số dư. Thay vì để mọi transaction tự đọc nhiều dòng rồi tính lại, ứng dụng cập nhật một dòng tổng hợp bằng điều kiện nguyên tử.

Ví dụ, nếu cần giới hạn số chỗ đặt tối đa là 100:

~~~sql
UPDATE dbo.EventCapacity
SET Reserved = Reserved + @requested
WHERE EventId = @eventId
  AND Reserved + @requested <= Capacity;
~~~

Ứng dụng chỉ xác nhận đặt chỗ nếu một dòng được cập nhật. Các transaction cùng sự kiện cạnh tranh trên một dòng tổng hợp, nhờ đó database có thể phối hợp cập nhật. Cần bảo đảm dữ liệu tổng hợp được duy trì nhất quán với các bản ghi đặt chỗ và xử lý trường hợp transaction thất bại giữa các bước.

## 8. Snapshot isolation và optimistic concurrency control

Snapshot isolation và optimistic concurrency control (OCC) có liên hệ nhưng không phải cùng một khái niệm.

**Snapshot isolation** mô tả ngữ nghĩa đọc và xử lý xung đột của một isolation level: transaction đọc một snapshot nhất quán và hệ quản trị xử lý các cập nhật xung đột theo quy tắc của DBMS.

**OCC** là một cách tổ chức kiểm soát đồng thời theo hướng lạc quan. Một mô hình OCC cổ điển có ba pha:

1. **Read phase:** transaction đọc dữ liệu và tính toán trên workspace riêng.
2. **Validation phase:** kiểm tra các dữ liệu hoặc điều kiện mà transaction dựa vào có xung đột với transaction đã commit hay không.
3. **Write phase:** nếu xác nhận thành công, các thay đổi được ghi và commit; nếu thất bại, transaction bị hủy hoặc thử lại.

~~~text
             +------------------+
             |   Read phase     |
             | Đọc và tính toán |
             +--------+---------+
                      |
                      v
             +------------------+
             | Validation phase |
             | Kiểm tra xung đột|
             +--------+---------+
                      |
              +-------+-------+
              |               |
           Hợp lệ          Xung đột
              |               |
              v               v
      +---------------+   +----------------+
      | Write/COMMIT  |   | Abort / Retry  |
      +---------------+   +----------------+
~~~

Các DBMS MVCC có thể thực hiện một phần kiểm tra trong lúc UPDATE, trong lúc COMMIT hoặc bằng cơ chế nội bộ khác. Không phải mọi hệ thống đều duy trì một read set đầy đủ và chạy đúng ba pha như mô hình OCC giáo khoa.

Từ góc độ thiết kế ứng dụng, tư duy lạc quan rất hữu ích: cho phép nhiều request đọc cùng dữ liệu, nhưng khi ghi phải kiểm tra version, điều kiện hoặc invariant. Khi có xung đột, ứng dụng xử lý rõ ràng thay vì âm thầm ghi đè.

## 9. Khác biệt khi áp dụng trên các DBMS phổ biến

Không nên coi tên isolation level giống nhau giữa các sản phẩm là bảo đảm chúng có cùng ngữ nghĩa nội bộ.

| DBMS | Snapshot read và xác nhận thay đổi |
|---|---|
| SQL Server | READ_COMMITTED_SNAPSHOT cung cấp snapshot theo câu lệnh ở READ COMMITTED; SNAPSHOT cung cấp snapshot cấp transaction khi database cho phép ALLOW_SNAPSHOT_ISOLATION. Cập nhật một dòng đã bị transaction khác thay đổi sau snapshot có thể gây update conflict, thường được nhận diện bằng lỗi 3960. |
| PostgreSQL | READ COMMITTED dùng snapshot theo câu lệnh; REPEATABLE READ giữ snapshot cấp transaction và có thể gặp serialization failure khi hai transaction cạnh tranh cập nhật cùng dòng. SERIALIZABLE bổ sung SSI để phát hiện các phụ thuộc nguy hiểm, bao gồm những tình huống write skew. |
| MySQL InnoDB | Consistent read dùng MVCC; READ COMMITTED tạo snapshot mới cho mỗi consistent read, còn REPEATABLE READ giữ snapshot cho các consistent read của transaction. Locking read như FOR UPDATE có ngữ nghĩa đọc hiện hành và lấy khóa; cần chú ý khi trộn hai loại đọc. |
| Oracle | READ COMMITTED cung cấp read consistency theo câu lệnh; SERIALIZABLE cung cấp ảnh chụp nhất quán ở cấp transaction. Nếu transaction không thể tiếp tục theo quy tắc serializable, Oracle có thể báo ORA-08177. |

Một số mã lỗi thường gặp giúp ứng dụng nhận diện xung đột:

- SQL Server SNAPSHOT: lỗi 3960 khi cập nhật dòng đã thay đổi kể từ khi snapshot bắt đầu.
- PostgreSQL: SQLSTATE 40001 cho serialization failure; cần xử lý retry theo đúng phạm vi transaction.
- Oracle SERIALIZABLE: ORA-08177 khi không thể serialize access.
- MySQL InnoDB: deadlock hoặc lock wait timeout có thể yêu cầu rollback và thử lại; cần phân biệt lỗi khóa với lỗi nghiệp vụ.

Mã lỗi, điều kiện phát sinh và trạng thái transaction sau lỗi phải được xác nhận theo tài liệu của phiên bản DBMS đang chạy. Không nên viết một bộ retry chung chỉ dựa trên tên isolation level.

## 10. Quy trình xử lý xung đột trong ứng dụng

Khi transaction thất bại ở bước xác nhận, ứng dụng cần quyết định có thể thử lại hay phải yêu cầu người dùng giải quyết.

Một quy trình thường dùng:

1. Bắt đầu transaction với isolation level đã chọn.
2. Đọc dữ liệu từ snapshot và ghi nhận version hoặc điều kiện nghiệp vụ cần thiết.
3. Tính toán thay đổi.
4. Thực hiện UPDATE có điều kiện hoặc để DBMS kiểm tra xung đột.
5. Nếu cập nhật và commit thành công, trả kết quả thành công.
6. Nếu phát hiện xung đột, rollback toàn bộ transaction.
7. Nếu lỗi có thể retry, bắt đầu transaction mới, đọc snapshot mới và tính toán lại.

**Phải đọc lại và tính toán lại trên snapshot mới.** Không nên lấy kết quả đã tính từ snapshot cũ rồi gửi lại lệnh ghi, vì dữ liệu đầu vào có thể đã thay đổi.

Ví dụ, khi hai người cùng sửa thông tin sản phẩm:

- Người A đọc Version 5 và sửa Price.
- Người B cũng đọc Version 5 và sửa Description.
- A cập nhật thành công, Version thành 6.
- B gửi UPDATE với điều kiện Version = 5; không có dòng nào được cập nhật.
- Ứng dụng tải lại Version 6, so sánh các trường thay đổi và quyết định có thể hợp nhất tự động hay cần người dùng chọn.

Nếu hai người sửa hai trường độc lập, ứng dụng có thể xây dựng chính sách merge. Nếu cả hai sửa cùng một trường, thường cần báo xung đột để tránh mất dữ liệu.

### 10.1. Retry phải có giới hạn

Không nên retry vô hạn. Một chính sách thực tế cần:

- Chỉ retry các lỗi xung đột tạm thời đã nhận diện.
- Giới hạn số lần thử.
- Có khoảng chờ tăng dần và jitter khi nhiều request cùng tranh chấp.
- Mỗi lần retry phải tạo transaction mới và đọc lại dữ liệu.
- Bảo đảm thao tác có thể retry an toàn, đặc biệt với thanh toán, gửi email, gọi API hoặc phát sự kiện.
- Chỉ thực hiện side effect bên ngoài sau khi commit, hoặc dùng outbox/idempotency key để phối hợp đáng tin cậy.

Nếu transaction đã gửi email hoặc gọi dịch vụ thanh toán rồi mới gặp lỗi commit, retry toàn bộ transaction có thể tạo side effect trùng lặp. Phần xử lý ngoài database cần có thiết kế idempotency riêng.

## 11. Transaction dài và chi phí giữ phiên bản cũ

Snapshot read giúp reader không phải chờ writer trong nhiều trường hợp, nhưng transaction đọc quá lâu có thể làm tăng chi phí lưu giữ phiên bản.

Hệ quản trị chỉ có thể thu hồi phiên bản cũ khi không còn snapshot nào cần đọc chúng. Do đó:

- SQL Server có thể tăng dung lượng version store trong tempdb hoặc Persistent Version Store khi dùng Accelerated Database Recovery.
- PostgreSQL có thể giữ tuple cũ lâu hơn và làm chậm quá trình VACUUM thu hồi không gian.
- MySQL InnoDB có thể giữ undo history lâu hơn và làm tăng áp lực purge.
- Oracle phụ thuộc undo retention và nhu cầu consistent read; thiếu undo cần thiết có thể gây lỗi đọc nhất quán.

Cách giảm tác động:

- Giữ transaction ngắn và không chờ người dùng hoặc dịch vụ bên ngoài trong transaction.
- Phân trang và đọc theo từng phần nếu nghiệp vụ cho phép.
- Theo dõi tuổi transaction lâu nhất, dung lượng version/undo và các chỉ số cleanup.
- Không mở transaction snapshot chỉ để giữ một màn hình người dùng trong nhiều phút hoặc nhiều giờ; dùng version token ở ứng dụng khi cần phát hiện dữ liệu đã đổi.

Snapshot càng lâu, hệ quản trị càng phải duy trì lịch sử đủ để dựng lại góc nhìn cũ. Đây là chi phí cần tính đến khi chọn transaction-level snapshot.

## 12. Chọn cách xác nhận theo loại yêu cầu

| Yêu cầu | Cách phù hợp để xem xét | Lưu ý |
|---|---|---|
| Người dùng sửa một bản ghi | Cột version hoặc rowversion và UPDATE có điều kiện | Phát hiện bản ghi đã thay đổi kể từ lúc tải biểu mẫu |
| Trừ tồn kho không âm | UPDATE nguyên tử với điều kiện Quantity >= số lượng cần trừ | Tránh đọc rồi ghi lại một giá trị tuyệt đối |
| Cập nhật nhiều dòng độc lập | Snapshot isolation và xử lý write conflict | Cần thiết kế retry toàn transaction |
| Bảo vệ quy tắc liên quan nhiều dòng | SERIALIZABLE, guard row, khóa phạm vi hoặc constraint phù hợp | Tránh write skew |
| Đọc báo cáo cần dữ liệu ổn định | Snapshot cấp transaction hoặc cơ chế read consistency tương ứng | Theo dõi thời gian sống snapshot và chi phí giữ version |
| Nhiều người cùng sửa tài liệu | Optimistic version check và chính sách merge/conflict | Không ghi đè thay đổi mới của người khác |

Không có một isolation level giải quyết tốt nhất mọi yêu cầu. Cần xác định dữ liệu được đọc, dữ liệu được ghi, invariant nào phải giữ và loại xung đột nào ứng dụng có thể chấp nhận.

## 13. Những nguyên tắc cần ghi nhớ

- Snapshot read cho transaction một góc nhìn nhất quán của dữ liệu đã commit tại một mốc xác định.
- Snapshot có thể ở cấp câu lệnh hoặc cấp transaction; READ COMMITTED và SNAPSHOT/REPEATABLE READ không giống nhau giữa các DBMS.
- MVCC giảm nhiều trường hợp reader phải chờ writer, nhưng thao tác ghi vẫn cần phối hợp và có thể xung đột.
- Khi dữ liệu đã thay đổi sau snapshot, transaction cần được xác nhận trước khi ghi kết quả tính toán.
- Version column và UPDATE có điều kiện là cách phổ biến để phát hiện cập nhật lỗi thời ở cấp dòng.
- Snapshot isolation có thể phát hiện write-write conflict trên cùng dòng, nhưng vẫn có thể để lọt write skew giữa các dòng khác nhau.
- SERIALIZABLE, guard row, khóa phạm vi và constraint phù hợp giúp bảo vệ invariant nhiều dòng.
- Khi serialization hoặc optimistic validation thất bại, hãy rollback và tính toán lại trên snapshot mới.
- Transaction snapshot kéo dài làm tăng thời gian giữ version cũ và chi phí dọn dẹp của database.

Mô hình đọc trên ảnh chụp giúp transaction làm việc với dữ liệu nhất quán trong khi hệ thống vẫn phục vụ các thao tác đồng thời. Xác nhận thay đổi là bước nối giữa góc nhìn ổn định đó và trạng thái database tại thời điểm ghi, giúp ứng dụng phát hiện xung đột và bảo vệ các quy tắc nghiệp vụ.

