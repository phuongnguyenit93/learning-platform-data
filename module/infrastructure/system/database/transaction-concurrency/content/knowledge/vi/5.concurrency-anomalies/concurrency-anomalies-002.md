# Ghi bẩn (dirty write): ghi chồng lên thay đổi chưa được xác nhận

Trong môi trường nhiều giao dịch đồng thời, một hàng dữ liệu có thể được nhiều transaction cùng muốn sửa. Vấn đề nghiêm trọng xuất hiện khi một transaction ghi đè lên giá trị mà transaction khác vừa ghi nhưng **chưa commit hoặc rollback**. Hiện tượng đó gọi là **ghi bẩn** (*dirty write*).

Dirty write làm cho kết quả của một giao dịch phụ thuộc vào trạng thái chưa được xác nhận của giao dịch khác. Nếu giao dịch ghi trước rollback, hệ quản trị phải xử lý chuỗi thay đổi sao cho không xóa nhầm dữ liệu hợp lệ của giao dịch còn lại. Vì vậy, các hệ quản trị cơ sở dữ liệu quan hệ phổ biến điều phối writer cạnh tranh bằng khóa hoặc cơ chế tương đương, không cho phép một transaction ghi chồng lên thay đổi chưa commit của transaction khác.

## 1. Định nghĩa và lịch giao dịch

Dirty write xảy ra khi transaction T2 ghi lên cùng một đối tượng dữ liệu X sau khi T1 đã ghi X nhưng trước khi T1 kết thúc bằng commit hoặc rollback. Trọng tâm là **trạng thái xác nhận của lần ghi trước**, không chỉ là việc hai giao dịch cùng cập nhật một hàng.

Giả sử số dư tài khoản ban đầu là 1.000:

~~~text
Thời điểm     T1                              T2
----------------------------------------------------------------
1             BEGIN
2             UPDATE balance = 1100
              (chưa COMMIT)
3                                             BEGIN
4                                             UPDATE balance = 900
                                              (ghi lên thay đổi T1)
5             ROLLBACK
6                                             COMMIT
~~~

Tại thời điểm 4, T2 ghi vào dữ liệu do T1 tạo ra nhưng chưa xác nhận. Đây là dirty write trong lịch giả định này. Các DBMS quan hệ thông dụng ngăn hoặc trì hoãn thao tác ghi ở thời điểm đó.

Trong ký hiệu lịch giao dịch, có thể biểu diễn phần quan trọng như sau:

~~~text
W1(X) ... W2(X) ... C2 ... A1
~~~

- W1(X): T1 ghi đối tượng X.
- W2(X): T2 ghi X sau lần ghi chưa commit của T1.
- C2: T2 commit.
- A1: T1 abort hoặc rollback.

Thứ tự này cho thấy T2 đã ghi trước khi T1 hoàn tất. Nếu T1 rollback, database phải đối mặt với phụ thuộc khó xử lý: khôi phục X về trước T1 có thể xóa mất kết quả T2; giữ nguyên kết quả T2 có thể khiến nó tiếp tục dựa trên thay đổi chưa được xác nhận.

## 2. Vì sao dirty write nguy hiểm?

### Rollback có thể làm hỏng thay đổi khác

Giả sử X ban đầu bằng 10, T1 ghi X bằng 20, rồi T2 ghi X bằng 30 trước khi T1 commit. Nếu T1 rollback và database phục hồi X về 10 một cách ngây thơ, kết quả ghi 30 của T2 cũng bị xóa. Nếu database giữ X bằng 30, T2 lại có thể đã dựa trên trạng thái chưa được xác nhận. Muốn xử lý chính xác cần theo dõi phụ thuộc và quyền sở hữu từng thay đổi.

~~~text
X ban đầu = 10
T1: W(X = 20)       -- chưa commit
T2: W(X = 30)       -- ghi lên thay đổi T1
T1: ROLLBACK
~~~

### Một transaction phụ thuộc vào trạng thái chưa xác nhận

T2 có thể tính toán kết quả từ giá trị T1 vừa ghi. Nếu T1 rollback, căn cứ của T2 biến mất. T2 có thể phải rollback hoặc chạy lại. Quan hệ này tạo ra một lịch phụ thuộc vào dữ liệu chưa được xác nhận và làm suy yếu tính cô lập.

### Phục hồi trở nên phức tạp

Recovery phải biết thay đổi nào thuộc transaction nào, transaction nào commit, transaction nào abort và thứ tự nào cần undo hoặc redo. Ngăn dirty write làm giảm loại phụ thuộc này: một writer chỉ tiếp tục sau khi writer trước đã kết thúc và trạng thái của nó đã rõ ràng.

## 3. Phân biệt dirty write, dirty read và lost update

Ba khái niệm dễ bị trộn lẫn vì đều liên quan đến cạnh tranh, nhưng mô tả các quan hệ đọc/ghi khác nhau.

| Hiện tượng | Quan hệ xảy ra | Mô tả |
| --- | --- | --- |
| **Dirty read (đọc bẩn)** | T2 đọc dữ liệu T1 ghi nhưng chưa commit | T1 rollback khiến giá trị T2 đã đọc chưa bao giờ được xác nhận. |
| **Dirty write (ghi bẩn)** | T2 ghi đè dữ liệu T1 ghi nhưng chưa commit | T2 thay đổi cùng đối tượng trong lúc lần ghi T1 còn dang dở. |
| **Lost update (mất cập nhật)** | Ghi hợp lệ sau đó làm mất kết quả của lần cập nhật khác | T2 có thể ghi dựa trên bản đọc cũ sau khi T1 đã commit. |

### Dirty read

~~~text
Ban đầu X = 10
T1: UPDATE X = 20       -- chưa commit
T2: SELECT X            -- đọc 20
T1: ROLLBACK            -- X trở lại 10
T2: tiếp tục tính toán từ giá trị 20
~~~

T2 chỉ đọc giá trị chưa commit; không cần ghi X để dirty read xảy ra.

### Lost update

~~~text
Ban đầu X = 10
T1: SELECT X -> 10
T2: SELECT X -> 10
T1: UPDATE X = 11
T1: COMMIT
T2: UPDATE X = 12
T2: COMMIT
~~~

Nếu nghiệp vụ T2 là cộng thêm 2, kết quả mong muốn khi áp dụng cả hai cập nhật có thể là 13. Ghi giá trị tính sẵn 12 làm mất phần tăng của T1. Tuy nhiên, T2 ghi sau khi T1 đã commit, nên đây không phải dirty write.

### Dirty write

~~~text
Ban đầu X = 10
T1: UPDATE X = 20       -- chưa commit
T2: UPDATE X = 30       -- ghi lên thay đổi chưa commit của T1
T1: ROLLBACK
~~~

Điểm phân biệt là T1 còn chưa kết thúc khi T2 ghi. Hãy hỏi: transaction thứ hai đọc giá trị chưa commit, ghi lên giá trị chưa commit, hay ghi sau commit nhưng dựa trên dữ liệu cũ? Ba trường hợp hướng đến dirty read, dirty write và lost update.

## 4. Lịch giao dịch và cách nhận diện

Dirty write liên quan đến hai thao tác ghi trên cùng đối tượng X, trong đó transaction ghi trước chưa commit tại thời điểm transaction ghi sau thực hiện thao tác.

~~~mermaid
sequenceDiagram
    participant DB as Database
    participant T1 as Transaction T1
    participant T2 as Transaction T2
    T1->>DB: BEGIN
    T1->>DB: W1(X): X = 20
    Note over DB: Thay đổi T1 chưa commit
    T2->>DB: BEGIN
    T2->>DB: W2(X): X = 30
    Note over DB: Nếu cho phép, đây là dirty write
    T1->>DB: ROLLBACK
    T2->>DB: COMMIT
~~~

Trong một hệ thống có điều phối ghi an toàn, tại thời điểm T2 yêu cầu ghi X, database nhận thấy X đang được T1 sửa. T2 phải chờ, hoặc bị kết thúc theo chính sách timeout/deadlock/xung đột của engine.

~~~mermaid
sequenceDiagram
    participant DB as Database
    participant T1 as Transaction T1
    participant T2 as Transaction T2
    T1->>DB: UPDATE X = 20
    DB-->>T1: Lấy khóa ghi trên X
    T2->>DB: UPDATE X = 30
    DB-->>T2: Chờ khóa của T1
    T1->>DB: ROLLBACK
    DB-->>T2: Khóa được giải phóng
    T2->>DB: Ghi trên trạng thái hiện hành
    T2->>DB: COMMIT
~~~

Lịch thứ hai minh họa nguyên tắc: không để hai transaction ghi chồng lên nhau khi một lần ghi còn chưa được xác nhận. Nếu T1 rollback, T2 tiếp tục trên trạng thái được phục hồi; nếu T1 commit, T2 tiếp tục sau trạng thái đã commit.

## 5. Cơ chế ngăn dirty write

### Khóa ghi

Khi transaction sửa một hàng, DBMS thường đặt khóa ghi loại trừ phù hợp. Transaction khác muốn sửa cùng hàng phải đợi khóa được giải phóng hoặc kết thúc với lỗi. Khóa do database quản lý, nên điều phối được nhiều thread, process, máy chủ ứng dụng và công cụ cùng kết nối.

~~~text
T1: UPDATE account ... WHERE id = 1
    -> giữ khóa ghi trên hàng id = 1
T2: UPDATE account ... WHERE id = 1
    -> chờ T1 COMMIT hoặc ROLLBACK
T1: ROLLBACK
    -> khóa được giải phóng; trạng thái T1 được hoàn tác
T2: tiếp tục trên trạng thái hiện hành
~~~

Khóa được giải phóng khi transaction kết thúc theo cơ chế của DBMS. Việc T2 phải đợi hay bị hủy còn phụ thuộc timeout, deadlock detection và isolation.

### MVCC không loại bỏ điều phối writer

MVCC (*Multi-Version Concurrency Control*) cho phép nhiều phiên bản dữ liệu cùng tồn tại để reader có thể nhìn thấy phiên bản phù hợp với snapshot. Nhưng MVCC **không có nghĩa mọi writer đều được phép ghi chồng lên phiên bản chưa commit của writer khác**.

Phân biệt bốn trường hợp:

- **Đọc phiên bản cũ đã commit:** có thể được MVCC cho phép để giảm xung đột reader/writer.
- **Đọc phiên bản mới chưa commit:** là dirty read; các mức isolation thông dụng ngăn hành vi này.
- **Ghi lên thay đổi chưa commit của writer khác:** là dirty write; DBMS điều phối để ngăn.
- **Ghi sau khi writer trước commit:** có thể hợp lệ, nhưng vẫn cần xử lý lost update hoặc xung đột logic.

Chỉ biết database có MVCC chưa đủ để suy ra chi tiết khóa. Cần hiểu cách engine xử lý update conflict, row lock và serialization.

## 6. Ví dụ SQL: hai phiên cùng cập nhật tài khoản

Giả sử có bảng tài khoản:

~~~sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL
);

INSERT INTO accounts (id, balance) VALUES (1, 1000);
~~~

Phiên A bắt đầu và chưa commit:

~~~sql
-- Session A
BEGIN;
UPDATE accounts
SET balance = 1100
WHERE id = 1;
-- Giữ transaction mở, chưa COMMIT.
~~~

Trong khi A còn mở, phiên B chạy:

~~~sql
-- Session B
BEGIN;
UPDATE accounts
SET balance = 900
WHERE id = 1;
-- PostgreSQL và các engine dùng row-level write locking
-- sẽ điều phối để B chờ, thay vì ghi chồng thay đổi chưa commit của A.
~~~

Nếu A rollback:

~~~sql
-- Session A
ROLLBACK;
~~~

B có thể tiếp tục trên trạng thái sau rollback. Nếu A commit, B tiếp tục sau trạng thái đã commit; điều kiện cập nhật có thể được đánh giá lại theo semantics của engine và isolation. Cần đọc kết quả thực tế, không giả định tất cả DBMS đều trả cùng một kiểu kết quả.

~~~sql
SELECT balance FROM accounts WHERE id = 1;
~~~

Ví dụ này minh họa cách dirty write được ngăn. Quan sát thấy B bị block là dấu hiệu điều phối ghi hoạt động, không phải bằng chứng dirty write đã xảy ra.

## 7. Liên hệ với các mức cô lập

| Mức cô lập theo mô hình SQL | Dirty read | Dirty write trong DBMS quan hệ phổ biến | Nhận xét |
| --- | --- | --- | --- |
| **READ UNCOMMITTED** | Có thể được cho phép theo mô hình; engine có thể triển khai mạnh hơn | Vẫn bị ngăn | Không suy ra dirty write được chấp nhận chỉ vì dirty read được nới lỏng. |
| **READ COMMITTED** | Không | Bị ngăn | Câu lệnh thường đọc dữ liệu đã commit theo semantics engine. |
| **REPEATABLE READ** | Không | Bị ngăn | Phantom và write skew khác nhau theo DBMS. |
| **SERIALIZABLE** | Không | Bị ngăn | Hướng tới tương đương một thứ tự tuần tự; có thể hủy transaction cần retry. |

Dirty write không phải mục tiêu mà ứng dụng có thể tùy ý bật/tắt bằng cách giảm isolation. Các engine vẫn cần điều phối writer để bảo vệ trạng thái transaction và khả năng rollback.

PostgreSQL chấp nhận cú pháp READ UNCOMMITTED nhưng thực thi như READ COMMITTED; vì thế dirty read không xảy ra ở mức đó. PostgreSQL cũng điều phối ghi cạnh tranh trên cùng hàng, nên dirty write bị ngăn trong các mức cô lập thông dụng.

Không nên suy diễn hành vi PostgreSQL sang MySQL/InnoDB, SQL Server hoặc Oracle chỉ từ tên mức isolation. Mỗi engine có mô hình khóa, MVCC và báo lỗi riêng.

## 8. Dirty write, rollback và recovery

Một lý do nền tảng để ngăn dirty write là giữ cho rollback của một transaction không phá hủy kết quả của transaction khác.

~~~text
T1 ghi X = 20
T2 muốn ghi X = 30
T1 rollback
T2 tiếp tục trên trạng thái đã phục hồi
~~~

Khi T2 chỉ được ghi sau khi T1 rollback, database có thể khôi phục X về giá trị trước T1 rồi cho T2 thực hiện. Nếu T1 commit, T2 thực hiện sau trạng thái mới đã xác nhận. Transaction sau không phải dựa vào thay đổi chưa được công nhận.

WAL/redo log, undo log và recovery hỗ trợ khôi phục sau crash, nhưng **không thay thế concurrency control**. Nhật ký ghi nhận thông tin phục hồi; khóa và quản lý transaction xác định writer nào được phép tác động lên dữ liệu và vào lúc nào.

Nếu một engine cho phép ghi chồng chưa commit, recovery phải theo dõi giá trị trước T1, thay đổi T1, thay đổi T2, quan hệ phụ thuộc và trạng thái commit/abort. Đây là lịch sử phức tạp hơn. Ngăn dirty write giảm đáng kể loại phụ thuộc này.

Điều quan trọng: recovery không tự sửa một quyết định nghiệp vụ sai đã commit. Nếu một transaction đã hợp lệ hóa số dư sai, log sẽ giúp phục hồi chính trạng thái đã commit ấy. Bất biến và điều phối đồng thời phải được thiết kế ngay trong đường ghi.

## 9. Ứng dụng cần làm gì khi writer cạnh tranh?

Không nên dùng khóa trong bộ nhớ của một process Java như hàng rào duy nhất. Một khóa local chỉ điều phối thread trong process đó, không bảo vệ trước instance khác, batch job hoặc ứng dụng khác cùng kết nối database.

### Cập nhật có điều kiện

Ví dụ trừ tồn kho, kết hợp kiểm tra và cập nhật trong một lệnh:

~~~sql
UPDATE inventory
SET quantity = quantity - :requested
WHERE sku = :sku
  AND quantity >= :requested
RETURNING quantity;
~~~

Ứng dụng kiểm tra số hàng trả về. Một hàng nghĩa là cập nhật thành công; không có hàng nghĩa là không thỏa điều kiện hoặc không tìm thấy SKU. Có thể thêm CHECK (quantity >= 0) như lớp bảo vệ dữ liệu. Cơ chế này không cho phép writer ghi chồng lên thay đổi chưa commit; database vẫn điều phối khóa.

### Optimistic concurrency control

Với cột version:

~~~sql
UPDATE documents
SET content = :new_content,
    version = version + 1
WHERE id = :id
  AND version = :version_read;
~~~

Nếu hai client cùng đọc version 5, chỉ một cập nhật có thể thành công với điều kiện version = 5. Lần còn lại cập nhật 0 hàng và phải báo xung đột, đọc lại hoặc hợp nhất thay đổi. Version check chủ yếu phát hiện cập nhật dựa trên bản đọc cũ; nó không phải cơ chế cho phép dirty write.

### Khóa theo thứ tự nhất quán

Khi cập nhật nhiều hàng, hai transaction có thể lấy khóa theo thứ tự ngược và gây deadlock. Thống nhất thứ tự khóa, ví dụ tăng dần theo ID, giúp giảm rủi ro. Tuy vậy, ứng dụng vẫn phải xử lý deadlock vì còn nhiều đường khóa và tài nguyên khác.

### Retry có giới hạn

Nếu ghi bị chặn quá lâu, timeout hoặc deadlock khiến transaction thất bại, ứng dụng cần rollback và quyết định có retry hay báo lỗi. Retry cần giới hạn số lần, backoff thích hợp và idempotency đối với tác dụng phụ. Không retry vô hạn và không giả định mọi lỗi ghi đều có thể chạy lại an toàn.

## 10. Những hiểu nhầm thường gặp

- **“READ UNCOMMITTED cho phép dirty write.”** Không thể suy ra như vậy. READ UNCOMMITTED nói về khả năng đọc dữ liệu chưa commit theo mô hình isolation; các engine quan hệ phổ biến vẫn ngăn writer ghi đè thay đổi chưa commit của writer khác.
- **“Dirty write và dirty read giống nhau.”** Dirty read là đọc dữ liệu chưa commit; dirty write là ghi lên dữ liệu chưa commit.
- **“Hai câu UPDATE cùng hàng luôn là dirty write.”** Không đúng. Nếu transaction thứ hai ghi sau khi transaction đầu commit hoặc rollback, đó là ghi nối tiếp. Lost update hoặc sai nghiệp vụ vẫn có thể xảy ra nhưng không phải dirty write.
- **“MVCC nghĩa là không cần khóa.”** Không đúng. MVCC giảm một số xung đột đọc/ghi, nhưng writer cùng sửa một hàng vẫn cần được điều phối.
- **“Có WAL là dirty write không thể xảy ra.”** WAL hỗ trợ phục hồi và durability. Việc ngăn ghi đè thay đổi chưa commit thuộc concurrency control.
- **“Rollback một transaction luôn khôi phục toàn bộ database về trước lúc transaction bắt đầu.”** Rollback chỉ hoàn tác thay đổi thuộc transaction đó; nó không được xóa thay đổi hợp lệ của transaction khác đã commit.
- **“Khóa ứng dụng là đủ.”** Khóa local không phối hợp nhiều process. Database là điểm đồng bộ chung cho dữ liệu bền vững.

## 11. Đọc lịch giao dịch để nhận diện dirty write

Khi xem trace hoặc bài tập lịch giao dịch, hãy đi theo trình tự:

1. Xác định transaction nào ghi đối tượng X và thời điểm commit/abort của nó.
2. Tìm thao tác ghi tiếp theo trên cùng X.
3. Kiểm tra transaction ghi trước đã commit hoặc rollback trước lần ghi sau chưa.
4. Nếu lần ghi sau diễn ra khi lần ghi trước vẫn chưa hoàn tất, đó là dấu hiệu dirty write trong lịch.
5. Kiểm tra tiếp transaction ghi sau có commit trước khi transaction trước abort không và rollback sẽ ảnh hưởng đến thay đổi nào.
6. Đối chiếu với cơ chế khóa/isolation của DBMS để biết lịch bị chặn, bị hủy hay được cho phép.

| Lịch | Kết luận |
| --- | --- |
| W1(X), C1, W2(X), C2 | Không có dirty write; T2 ghi sau khi T1 commit. |
| W1(X), W2(X), A1 | T2 ghi khi T1 chưa kết thúc: dirty write trong mô hình lịch. |
| W1(X), R2(X), A1 | T2 đọc giá trị chưa commit: dirty read. |
| R1(X), R2(X), W1(X), C1, W2(X), C2 | Có thể lost update nếu W2 dựa trên giá trị cũ; không phải dirty write. |
| W1(X), W2(X), C2, A1 | Dirty write; thứ tự commit/abort tạo phụ thuộc phục hồi không an toàn. |

Trong ký hiệu trên, R là đọc, W là ghi, C là commit và A là abort. Theo dõi chính xác thời điểm commit/abort giúp tránh kết luận nhầm chỉ vì hai lệnh cùng cập nhật một hàng.

## 12. Tình huống vận dụng

### Cập nhật số dư tài khoản

Hai yêu cầu điều chỉnh cùng một tài khoản. Yêu cầu A đang cập nhật số dư nhưng chưa commit. Yêu cầu B chạy UPDATE cùng hàng. Database cần điều phối để B không ghi đè trực tiếp kết quả chưa xác nhận của A. Nếu A rollback, B hoạt động trên số dư được phục hồi; nếu A commit, B tiếp tục theo trạng thái sau A và áp dụng quy tắc nghiệp vụ tương ứng.

### Sửa cùng một tài liệu

Một người dùng chỉnh sửa tài liệu và transaction lưu nội dung chưa commit. Người dùng khác gửi bản cập nhật. Dirty write là khi lần ghi thứ hai chồng lên phiên bản chưa xác nhận của lần đầu. Với khóa, lần ghi thứ hai chờ; với optimistic version, một cập nhật có thể thất bại do version đã thay đổi. Hệ thống có thể hiển thị xung đột để người dùng hợp nhất nội dung.

### Đặt chỗ và hoàn tác

Transaction T1 giữ một ghế và chưa commit. Transaction T2 muốn đổi trạng thái cùng ghế sang hủy hoặc đặt cho khách khác. T2 không được tự ghi lên trạng thái chưa xác nhận của T1. Database điều phối việc ghi hàng; logic nghiệp vụ tiếp tục xác định thứ tự hợp lệ sau khi transaction trước kết thúc. Nếu cần giữ chỗ tạm thời nhìn thấy được, hãy mô hình hóa trạng thái giữ chỗ và thời hạn rõ ràng thay vì dựa vào thay đổi uncommitted.

### Tồn kho cập nhật song song

Hai đơn hàng cùng muốn trừ hàng trong kho. Ngay cả khi dirty write bị ngăn, lost update hoặc bán vượt tồn vẫn có thể xuất hiện nếu logic chỉ đọc giá trị cũ rồi ghi giá trị tính sẵn. Cập nhật có điều kiện kết hợp CHECK (quantity >= 0) bảo vệ bất biến tốt hơn. Ngăn dirty write là điều kiện cần, không phải toàn bộ giải pháp concurrency.

## 13. Thiết kế và kết luận

Dirty write là một bất thường ở **quan hệ giữa các thao tác ghi**, chứ không đơn thuần là việc hai transaction cùng chạm vào một hàng. Trọng tâm là transaction thứ hai ghi lên dữ liệu của transaction thứ nhất khi thay đổi đó chưa được xác nhận.

- Database cần điều phối writer cạnh tranh bằng khóa hoặc cơ chế tương đương.
- Các mức READ COMMITTED, REPEATABLE READ và SERIALIZABLE có semantics riêng; không suy diễn hành vi chỉ từ tên isolation.
- MVCC giúp quản lý nhiều phiên bản cho đọc nhất quán, nhưng không cho phép bỏ qua xung đột giữa writer trên cùng dữ liệu.
- WAL và recovery bảo vệ khả năng phục hồi, còn concurrency control quyết định transaction nào được phép ghi và khi nào.
- Ứng dụng vẫn phải xử lý lost update, deadlock, timeout, retry, idempotency và bất biến nghiệp vụ ngay cả khi dirty write đã bị DBMS ngăn chặn.

Một câu hỏi hữu ích khi phân tích hệ thống là: **“Tại thời điểm transaction này ghi X, transaction trước đã commit hoặc rollback chưa?”** Nếu câu trả lời là chưa, cần xác định cơ chế database nào đang ngăn thao tác ghi chồng lên thay đổi chưa được xác nhận. Đó là điểm cốt lõi để nhận diện và hiểu cách ngăn dirty write.
