# Vì sao thường phải thực thi lại toàn bộ giao dịch

Khi một transaction gặp deadlock, serialization failure hoặc xung đột cập nhật, việc chạy lại riêng câu SQL cuối cùng thường không đủ để bảo đảm tính đúng đắn. Kết quả ghi thường được tính dựa trên những dữ liệu transaction đã đọc trước đó. Nếu một transaction khác đã thay đổi dữ liệu, các quyết định cũ có thể không còn hợp lệ.

Vì vậy, khi database yêu cầu transaction phải thử lại, ứng dụng thường cần **rollback và thực thi lại toàn bộ đơn vị nghiệp vụ**: đọc lại dữ liệu, kiểm tra điều kiện, tính toán lại và ghi lại thay đổi trong một transaction mới. Transaction mới có snapshot và trạng thái khóa mới, nên các quyết định được đưa ra dựa trên dữ liệu hiện hành mà nó được phép nhìn thấy.

Không phải mọi lỗi SQL đều buộc phải chạy lại toàn bộ transaction. Một số lỗi chỉ làm câu lệnh hiện tại thất bại và transaction vẫn có thể tiếp tục. Phạm vi retry phải dựa trên ngữ nghĩa lỗi của DBMS, trạng thái transaction và việc các câu lệnh sau có phụ thuộc vào dữ liệu đã đọc trước đó hay không.

## 1. Transaction là một đơn vị đọc, quyết định và ghi

Một transaction nghiệp vụ thường gồm nhiều bước có liên quan:

1. Đọc trạng thái hiện tại.
2. Kiểm tra quy tắc nghiệp vụ.
3. Tính toán thay đổi.
4. Ghi một hoặc nhiều bảng.
5. Commit để công bố kết quả.

Ví dụ, khi bán hàng, ứng dụng đọc số lượng tồn kho, kiểm tra đủ hàng, trừ số lượng, tạo đơn hàng và ghi lịch sử giao dịch. Những bước này cùng tạo nên một đơn vị nghiệp vụ.

~~~text
BEGIN TRANSACTION
       |
       v
Đọc dữ liệu hiện tại
       |
       v
Kiểm tra điều kiện nghiệp vụ
       |
       v
Tính toán thay đổi
       |
       v
UPDATE / INSERT nhiều bảng
       |
       v
COMMIT
~~~

Các bước không độc lập. Kết quả của bước ghi phụ thuộc vào dữ liệu và quyết định từ những bước trước. Nếu transaction thất bại vì xung đột đồng thời, một phần dữ liệu đầu vào hoặc giả định mà ứng dụng dùng để tính toán có thể đã lỗi thời.

Chạy lại riêng câu UPDATE cuối cùng bằng tham số cũ có thể ghi một kết quả không còn đúng với trạng thái mới. Chạy lại toàn bộ transaction cho phép ứng dụng xây dựng lại quyết định trên dữ liệu mới.

## 2. Vì sao chạy lại riêng câu lệnh cuối có thể sai?

Giả sử bảng Inventory có 10 sản phẩm. Hai khách hàng cùng đặt mua 7 sản phẩm.

Transaction A và B đều đọc số lượng 10:

~~~text
Trạng thái ban đầu: AvailableQuantity = 10

Transaction A                       Transaction B
--------------                       --------------
Đọc quantity = 10
Tính còn lại = 10 - 7 = 3
                                     Đọc quantity = 10
                                     Tính còn lại = 10 - 7 = 3
Ghi quantity = 3
COMMIT
                                     Cố ghi quantity = 3
                                     Gặp xung đột
~~~

Giả sử database hủy transaction B vì xung đột ghi hoặc serialization failure. Nếu ứng dụng chỉ chạy lại câu UPDATE với giá trị đã tính là 3, nó có thể ghi đè trạng thái hiện tại và làm mất thông tin về đơn hàng A. Trong trường hợp khác, nếu ứng dụng chỉ chạy lại lệnh INSERT đơn hàng mà không kiểm tra lại tồn kho, nó có thể tạo một đơn hàng vượt số lượng thực tế.

Cách đúng là bắt đầu transaction mới và đọc lại:

~~~text
Transaction B chạy lại
----------------------
BEGIN transaction mới
Đọc quantity hiện tại = 3
Kiểm tra yêu cầu mua 7
Không đủ hàng
ROLLBACK hoặc trả kết quả hết hàng
~~~

Lần retry không chỉ lặp lại thao tác ghi. Nó lặp lại **quyết định nghiệp vụ** dựa trên trạng thái mới.

### 2.1. Ví dụ với giá trị tuyệt đối

Một cách triển khai dễ gặp:

~~~sql
BEGIN TRANSACTION;

SELECT AvailableQuantity
FROM dbo.Inventory
WHERE ProductId = @productId;

-- Ứng dụng đọc được 10 và tính @newQuantity = 3.

UPDATE dbo.Inventory
SET AvailableQuantity = @newQuantity
WHERE ProductId = @productId;

INSERT INTO dbo.Orders (ProductId, Quantity)
VALUES (@productId, 7);

COMMIT TRANSACTION;
~~~

Nếu transaction phải retry nhưng vẫn giữ @newQuantity = 3 và không đọc lại tồn kho, ứng dụng đang sử dụng một quyết định cũ.

Với nghiệp vụ đơn giản, có thể chuyển điều kiện và phép tính thành một UPDATE nguyên tử:

~~~sql
UPDATE dbo.Inventory
SET AvailableQuantity = AvailableQuantity - @requestedQuantity
WHERE ProductId = @productId
  AND AvailableQuantity >= @requestedQuantity;
~~~

Sau đó kiểm tra số dòng bị ảnh hưởng. Nếu là 1, việc trừ hàng đã được thực hiện; nếu là 0, sản phẩm không tồn tại hoặc không đủ hàng.

Cách cập nhật nguyên tử giúp loại bỏ khoảng cách giữa đọc số lượng và ghi giá trị mới. Tuy nhiên, nếu transaction còn phải kiểm tra nhiều bảng, tính phí vận chuyển, áp dụng hạn mức khách hàng hoặc tạo các bản ghi liên quan, toàn bộ logic nghiệp vụ vẫn có thể cần chạy lại khi transaction bị hủy.

## 3. Các lỗi thường yêu cầu retry toàn bộ transaction

Một số lỗi thể hiện rằng lịch thực thi hiện tại không thể tiếp tục an toàn với những dữ liệu đã đọc.

### 3.1. Deadlock victim

Deadlock xảy ra khi các transaction chờ tài nguyên của nhau theo một chu trình.

Ví dụ:

~~~text
T1                                  T2
--                                  --
Khóa dòng A
                                    Khóa dòng B
Yêu cầu khóa dòng B
                                    Yêu cầu khóa dòng A
Chờ T2                              Chờ T1

Chu trình chờ được phát hiện.
Database chọn một transaction làm victim.
~~~

Transaction bị chọn làm victim phải bị hủy hoặc ít nhất phần thao tác gây deadlock bị rollback theo quy tắc của DBMS. Nếu các bước đọc và tính toán trước đó phụ thuộc vào những khóa hoặc dữ liệu đã thay đổi, ứng dụng nên rollback đơn vị nghiệp vụ và chạy lại từ đầu.

Retry riêng câu lệnh bị deadlock có thể không đủ vì các quyết định trước đó có thể dựa trên trạng thái đã cũ. Thực thi lại toàn bộ transaction cũng giúp lấy khóa theo một lịch mới.

### 3.2. Serialization failure

Ở isolation level SERIALIZABLE, DBMS phải bảo đảm các transaction commit tương đương với một thứ tự chạy tuần tự hợp lệ. Nếu phát hiện một lịch thực thi có thể tạo anomaly, database có thể hủy một transaction.

Ví dụ PostgreSQL có thể báo SQLSTATE 40001:

~~~text
ERROR: could not serialize access due to read/write dependencies among transactions
SQLSTATE: 40001
~~~

Transaction thất bại có thể đã đọc nhiều dòng, kiểm tra một predicate và tính toán thay đổi. Một transaction mới phải lấy snapshot mới và thực hiện lại các bước đó.

Nếu chỉ chạy lại câu UPDATE cuối, ứng dụng có thể tái sử dụng kết quả đọc từ snapshot cũ và tiếp tục tạo ra chính anomaly mà SERIALIZABLE vừa ngăn chặn.

### 3.3. Xung đột optimistic concurrency

Ứng dụng có thể đọc một dòng với Version = 5, sau đó người dùng chỉnh sửa trong vài phút. Một request khác đã cập nhật dòng đó lên Version = 6.

Câu UPDATE có điều kiện:

~~~sql
UPDATE Product
SET Price = @newPrice,
    Version = Version + 1
WHERE ProductId = @productId
  AND Version = @versionRead;
~~~

không cập nhật dòng nào vì version không còn khớp. Đây không nhất thiết là lỗi database cần retry tự động. Ứng dụng phải đọc lại dữ liệu, so sánh thay đổi và quyết định có thể áp dụng lại ý định của người dùng hay cần yêu cầu họ giải quyết xung đột.

Nếu toàn bộ thao tác nghiệp vụ phụ thuộc vào version cũ, phải tính toán lại từ đầu. Với biểu mẫu chỉnh sửa, không nên tự động ghi đè thay đổi mới của người khác chỉ bằng cách gửi lại cùng payload.

### 3.4. Constraint violation không mặc nhiên là lỗi retry

Ví dụ hai transaction cùng tạo username giống nhau. Unique constraint cho phép một bên thành công và từ chối bên còn lại.

Đây thường là kết quả nghiệp vụ: tên đã được sử dụng. Retry ngay cùng dữ liệu sẽ tiếp tục thất bại.

Tương tự, CHECK constraint, foreign key violation hoặc exclusion constraint có thể cho biết dữ liệu đầu vào không hợp lệ hoặc tài nguyên đã được đặt. Chỉ retry khi lỗi có thể tạm thời và ứng dụng có thể đọc lại trạng thái rồi đưa ra quyết định mới.

## 4. Vì sao snapshot và dữ liệu đã đọc không thể được tái sử dụng tùy ý?

Một transaction có thể đọc nhiều dữ liệu từ cùng snapshot. Các quyết định sau đó dựa trên mối quan hệ giữa những giá trị này.

Ví dụ, ứng dụng chuyển tiền giữa hai tài khoản:

1. Đọc số dư tài khoản A.
2. Đọc số dư tài khoản B.
3. Kiểm tra A có đủ tiền.
4. Tính phí dựa trên loại tài khoản B.
5. Trừ tiền A.
6. Cộng tiền B.
7. Ghi lịch sử chuyển tiền.

Nếu transaction bị hủy do deadlock hoặc serialization failure, không nên chỉ chạy lại bước trừ/cộng tiền bằng các số đã tính. Số dư, trạng thái tài khoản, phí hoặc giới hạn có thể đã thay đổi.

~~~text
Lần chạy đầu
------------
Snapshot S1
Đọc A = 1.000
Đọc B = 500
Tính phí = 10
Tính số tiền nhận = 490
Ghi thay đổi
Transaction bị hủy

Lần retry
---------
Snapshot S2
Đọc lại A, B và quy tắc hiện hành
Tính lại phí và số tiền nhận
Ghi thay đổi mới
COMMIT
~~~

Snapshot mới có thể trả về các giá trị khác. Retry toàn bộ transaction đảm bảo các phép kiểm tra và phép tính cùng dựa trên một trạng thái hợp lệ theo isolation level đã chọn.

Điều này đặc biệt quan trọng với các quy tắc liên quan nhiều dòng như:

- Tổng hạn mức của một nhóm tài khoản.
- Số chỗ còn trống của một sự kiện.
- Số nhân viên tối thiểu phải trực.
- Điều kiện một khách hàng chỉ có một đơn hàng đang xử lý.
- Trạng thái của nhiều bản ghi cần chuyển cùng nhau.

## 5. Phạm vi retry phụ thuộc loại lỗi và DBMS

Không phải mọi lỗi đều làm toàn bộ transaction bị rollback. Một số DBMS đánh dấu transaction là không thể tiếp tục; một số chỉ rollback câu lệnh gây lỗi. Ứng dụng cần hiểu chính xác trạng thái này.

| DBMS | Lỗi thường gặp | Phạm vi xử lý cần lưu ý |
|---|---|---|
| PostgreSQL | 40001 serialization failure | Phải rollback và chạy lại toàn bộ transaction trên snapshot mới |
| PostgreSQL | 40P01 deadlock detected | Transaction bị hủy; rollback và retry toàn bộ đơn vị nghiệp vụ |
| SQL Server | 1205 deadlock victim | SQL Server rollback transaction được chọn làm victim; retry toàn bộ transaction |
| SQL Server | 1222 lock request timeout | Câu lệnh hết thời gian chờ; trạng thái transaction còn lại phụ thuộc ngữ cảnh và cấu hình, cần kiểm tra XACT_STATE và xử lý rollback phù hợp |
| MySQL InnoDB | 1213 deadlock found | InnoDB rollback toàn bộ transaction bị chọn làm victim; retry transaction |
| MySQL InnoDB | 1205 lock wait timeout | Mặc định thường rollback câu lệnh bị timeout; cấu hình innodb_rollback_on_timeout có thể thay đổi thành rollback toàn transaction |
| Oracle | ORA-08177 cannot serialize access | Transaction SERIALIZABLE không thể tiếp tục theo snapshot; rollback và retry toàn bộ transaction |
| Oracle | ORA-00060 deadlock detected | Oracle thường rollback câu lệnh gây deadlock; transaction có thể vẫn còn hoạt động, nhưng ứng dụng nên đánh giá lại toàn bộ đơn vị nghiệp vụ trước khi tiếp tục |

Bảng này nêu hành vi phổ biến, không thay thế tài liệu của phiên bản và cấu hình cụ thể. Ví dụ, SQL Server có thể dùng SET XACT_ABORT để thay đổi cách xử lý một số lỗi; MySQL có cấu hình riêng cho lock wait timeout. Ứng dụng phải biết transaction còn hoạt động, đã rollback hay đang ở trạng thái không thể commit.

### 5.1. PostgreSQL: transaction bị đánh dấu lỗi

Sau một lỗi trong transaction PostgreSQL, các câu lệnh tiếp theo thường trả lỗi cho đến khi transaction được ROLLBACK hoặc quay về savepoint hợp lệ.

~~~sql
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE account_id = 1;

-- Nếu transaction gặp serialization failure hoặc deadlock,
-- transaction không thể tiếp tục như bình thường.

ROLLBACK;
~~~

Không thể chỉ gửi lại câu UPDATE tiếp theo trên cùng transaction đã bị abort. Cần rollback và mở transaction mới.

### 5.2. SQL Server: kiểm tra trạng thái transaction

Với một số lỗi, transaction có thể vẫn hoạt động; với lỗi khác, nó có thể không còn khả năng commit. Có thể dùng XACT_STATE() để kiểm tra:

~~~sql
SELECT XACT_STATE();
~~~

Các giá trị thường gặp:

- 1: transaction đang hoạt động và có thể commit nếu logic cho phép.
- 0: không có transaction đang hoạt động.
- -1: transaction đang ở trạng thái không thể commit; chỉ có thể đọc hoặc rollback toàn bộ.

Khi xử lý lỗi, ứng dụng nên rollback transaction nếu nó không còn an toàn hoặc không còn khả năng tiếp tục. Đừng giả định mọi exception đều để transaction ở cùng một trạng thái.

### 5.3. MySQL: phân biệt deadlock với lock wait timeout

InnoDB thường rollback toàn bộ transaction khi phát hiện deadlock. Với lock wait timeout, mặc định chỉ câu lệnh bị timeout được rollback; transaction có thể vẫn mở. Cấu hình innodb_rollback_on_timeout thay đổi hành vi này.

Dù database chỉ rollback câu lệnh, ứng dụng vẫn có thể chọn rollback toàn transaction nếu câu lệnh thất bại làm mất hiệu lực các quyết định trước đó. Quyết định này phải dựa trên tính phụ thuộc của nghiệp vụ, không chỉ dựa trên việc transaction còn mở hay không.

## 6. Khi nào chỉ cần chạy lại một câu lệnh?

Retry một statement có thể phù hợp khi tất cả điều kiện sau được thỏa mãn:

- DBMS xác nhận chỉ câu lệnh đó bị rollback và transaction vẫn hợp lệ.
- Câu lệnh không phụ thuộc vào một snapshot hoặc kết quả đọc đã trở nên lỗi thời.
- Các câu lệnh trước đó trong transaction không cần được tính toán lại.
- Việc chạy lại không tạo side effect trùng lặp.
- Quy tắc nghiệp vụ vẫn đúng sau khi câu lệnh được thực thi lại.

Ví dụ, một câu UPDATE độc lập tăng bộ đếm bằng phép toán nguyên tử có thể được chạy lại sau một lỗi tạm thời nếu transaction vẫn hợp lệ và ứng dụng biết lần trước chưa được áp dụng.

Ngược lại, nếu ứng dụng đã đọc số dư, tính số tiền mới rồi cập nhật, chỉ retry UPDATE với giá trị cũ có thể làm sai kết quả.

Một câu lệnh có thể được retry riêng khi nó thực sự là đơn vị độc lập. Nếu nó là bước cuối của một chuỗi đọc, kiểm tra và ghi, hãy xem lại toàn bộ chuỗi.

### 6.1. Savepoint không phải cách giữ snapshot cũ để vượt qua serialization failure

Savepoint cho phép rollback một phần thao tác trong transaction:

~~~sql
BEGIN;

SAVEPOINT before_optional_step;

-- Thực hiện một thao tác có thể thất bại.

ROLLBACK TO SAVEPOINT before_optional_step;

-- Tiếp tục các thao tác còn hợp lệ.
COMMIT;
~~~

Cơ chế này hữu ích khi một phần nghiệp vụ là tùy chọn và lỗi của nó không làm mất hiệu lực các quyết định trước đó.

Tuy nhiên, savepoint không biến một transaction đã gặp serialization failure thành một transaction có thể tiếp tục với cùng dữ liệu cũ. Nó cũng không làm các lượt đọc trước đó tự động được làm mới. Khi DBMS yêu cầu retry transaction, phải bắt đầu transaction mới.

## 7. Quy trình retry an toàn

Một retry an toàn cần xác định rõ ranh giới nghiệp vụ, phân loại lỗi và luôn tạo transaction mới khi transaction cũ đã bị hủy.

Quy trình khái quát:

~~~text
attempt = 1

Lặp đến MAX_RETRIES:
    BEGIN transaction mới

    Đọc lại dữ liệu cần thiết
    Kiểm tra quy tắc nghiệp vụ
    Tính toán lại thay đổi
    Ghi các thay đổi
    COMMIT

    Nếu thành công:
        Trả kết quả

    Nếu lỗi:
        ROLLBACK nếu transaction còn tồn tại
        Phân loại lỗi

        Nếu lỗi có thể retry:
            Chờ backoff có giới hạn và jitter
            Tăng attempt
            Bắt đầu transaction mới
        Ngược lại:
            Trả lỗi cho tầng gọi
~~~

Điểm quan trọng là phần đọc, kiểm tra và tính toán phải nằm bên trong ranh giới được thực thi lại. Nếu dữ liệu đầu vào được tải trước transaction rồi tái sử dụng qua nhiều lần retry, ứng dụng có thể vẫn dựa trên trạng thái cũ.

### 7.1. Pseudocode ở tầng service

~~~java
public Result executeBusinessOperation(Command command) {
    int maxAttempts = 4;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return transactionRunner.execute(status -> {
                // Đọc lại dữ liệu bên trong transaction mới.
                Account source = accountRepository.findForUpdate(
                    command.sourceAccountId()
                );
                Account target = accountRepository.findForUpdate(
                    command.targetAccountId()
                );

                // Kiểm tra và tính toán lại trên dữ liệu hiện hành.
                validateTransfer(source, target, command);
                TransferPlan plan = calculateTransfer(
                    source, target, command
                );

                // Ghi mọi thay đổi thuộc cùng đơn vị nghiệp vụ.
                applyTransfer(plan);
                transferRepository.insert(plan.toRecord());

                return plan.toResult();
            });
        } catch (RuntimeException error) {
            if (!isRetryableTransactionError(error)
                    || attempt == maxAttempts) {
                throw error;
            }

            sleepWithBackoffAndJitter(attempt);
        }
    }

    throw new IllegalStateException("Unreachable");
}
~~~

Đây là pseudocode theo ý tưởng dùng transaction callback. Tên API và cách nhận diện lỗi phụ thuộc framework. Cần bảo đảm mỗi lần gọi callback thực sự tạo transaction mới, và exception làm transaction cũ rollback trước khi vòng lặp bắt đầu lần tiếp theo.

Không bắt mọi RuntimeException rồi retry. Lỗi dữ liệu không hợp lệ, lỗi phân quyền, lỗi constraint nghiệp vụ hoặc lỗi lập trình không tự biến mất khi chạy lại.

### 7.2. Không đặt dữ liệu đã đọc bên ngoài vòng retry

Ví dụ sai về ranh giới:

~~~java
Account account = accountRepository.findById(accountId);

for (int attempt = 1; attempt <= 3; attempt++) {
    try {
        transactionRunner.execute(status -> {
            // Dùng lại account được đọc trước các lần retry.
            account.debit(amount);
            accountRepository.save(account);
            return null;
        });
    } catch (RetryableException error) {
        // Thử lại nhưng dữ liệu đầu vào vẫn cũ.
    }
}
~~~

Ví dụ này đọc Account một lần rồi tái sử dụng object cũ. Dù callback chạy lại trong transaction mới, dữ liệu trong bộ nhớ không tự được làm mới.

Cách đúng là tải lại dữ liệu trong callback:

~~~java
transactionRunner.execute(status -> {
    Account account = accountRepository.findForUpdate(accountId);
    validateBalance(account, amount);
    account.debit(amount);
    accountRepository.save(account);
    return null;
});
~~~

Nếu callback được thực thi lại, câu truy vấn cũng được thực hiện lại trên transaction mới.

## 8. Backoff, jitter và giới hạn retry

Nếu nhiều transaction cùng gặp deadlock hoặc serialization failure, chúng có thể đồng loạt retry ngay lập tức và lại tranh chấp cùng tài nguyên. Đây là hiện tượng retry storm.

Một chính sách phổ biến là exponential backoff có jitter:

~~~text
delay = min(maxDelay, baseDelay * 2^(attempt - 1))
actualDelay = random(0, delay)
~~~

Ví dụ minh họa:

| Lần thử | Khoảng chờ tối đa trước lần tiếp theo |
|---:|---:|
| 1 | 50 ms |
| 2 | 100 ms |
| 3 | 200 ms |
| 4 | 400 ms |

Giá trị thực tế phải được điều chỉnh theo độ trễ hệ thống, loại lỗi và giới hạn thời gian request. Jitter giúp các client không cùng thức dậy và retry tại một thời điểm.

Các nguyên tắc:

- Đặt số lần retry tối đa.
- Đặt tổng thời gian retry không vượt quá deadline của request hoặc job.
- Chỉ retry lỗi tạm thời đã nhận diện.
- Có backoff và jitter khi workload có nhiều client đồng thời.
- Ghi nhận số lần retry, loại lỗi và tỷ lệ thành công.
- Nếu một tài nguyên luôn tranh chấp, cân nhắc tuần tự hóa theo khóa nghiệp vụ hoặc thay đổi thiết kế thay vì tăng số lần retry mãi.

Retry là cơ chế phục hồi, không phải cách thay thế cho việc sửa một transaction luôn giữ khóa quá lâu hoặc một truy vấn luôn gây deadlock.

## 9. Idempotency: điều kiện quan trọng khi chạy lại

Một transaction có thể bị retry sau khi database đã rollback. Nhưng nếu thao tác có side effect bên ngoài database, việc chạy lại có thể lặp hành động.

Ví dụ:

1. Ứng dụng gọi Payment Provider và provider đã thu tiền.
2. Ứng dụng ghi trạng thái PAID trong database.
3. Database deadlock hoặc connection bị mất trước khi ứng dụng nhận kết quả COMMIT.
4. Ứng dụng retry và gọi provider lần nữa.

Nếu provider không nhận diện yêu cầu trùng, khách hàng có thể bị thu tiền hai lần.

**Idempotency** là khả năng thực hiện lại cùng một yêu cầu mà không tạo thêm hiệu ứng nghiệp vụ ngoài ý muốn.

### 9.1. Dùng request key duy nhất

Ứng dụng có thể tạo một RequestId ổn định cho thao tác nghiệp vụ và lưu nó trong cùng transaction với kết quả:

~~~sql
CREATE TABLE PaymentOperation
(
    RequestId       varchar(100) PRIMARY KEY,
    OrderId         bigint NOT NULL,
    Status          varchar(30) NOT NULL,
    ProviderTxnId   varchar(100) NULL
);
~~~

Khi xử lý yêu cầu, ứng dụng kiểm tra RequestId đã tồn tại chưa. Nếu đã có kết quả hoàn tất, trả lại kết quả cũ. Nếu chưa có, tạo operation và xử lý theo trạng thái.

Unique constraint trên RequestId bảo vệ khỏi hai request cùng tạo một thao tác nghiệp vụ. Khi có xung đột, ứng dụng đọc lại operation hiện hành thay vì tạo một giao dịch mới.

RequestId phải đại diện cho cùng một ý định nghiệp vụ qua các lần retry. Nếu mỗi lần retry tạo key mới, cơ chế chống trùng sẽ không còn tác dụng.

### 9.2. Tách side effect khỏi transaction bằng Outbox

Khi cần gửi message hoặc gọi dịch vụ ngoài sau khi database commit, Transactional Outbox cho phép ghi sự kiện cùng transaction nghiệp vụ. Worker gửi sự kiện sau đó và consumer xử lý idempotent.

~~~text
Transaction database
  UPDATE Order
  INSERT Outbox(EventId, PaymentRequested)
  COMMIT

Worker
  Đọc Outbox
  Gửi message với EventId ổn định
  Đánh dấu đã gửi

Consumer
  Kiểm tra EventId đã xử lý chưa
  Nếu chưa: thực hiện nghiệp vụ và ghi nhận EventId
~~~

Nếu worker bị dừng sau khi gửi nhưng trước khi đánh dấu đã gửi, message có thể được phát lại. Consumer phải nhận diện EventId đã xử lý để không tạo side effect lần thứ hai.

Outbox giúp bảo đảm sự kiện được lưu bền vững cùng thay đổi database. Nó thường cung cấp giao ít nhất một lần, nên idempotency vẫn cần thiết ở publisher/consumer.

## 10. Timeout khi COMMIT: kết quả có thể chưa xác định

Một trường hợp khó là kết nối mạng bị ngắt đúng lúc ứng dụng gửi COMMIT.

~~~text
Ứng dụng                         Database
---------                         --------
Gửi COMMIT
                                  COMMIT thành công
Mất kết nối trước khi nhận ACK
Nhận timeout
~~~

Ứng dụng không biết transaction đã commit hay chưa. Đây là **ambiguous commit outcome**. Không thể kết luận rằng transaction đã rollback chỉ vì client không nhận được phản hồi.

Nếu ứng dụng gửi lại toàn bộ thao tác với một RequestId mới, nghiệp vụ có thể bị thực hiện hai lần. Cách xử lý an toàn:

1. Dùng một idempotency key ổn định cho ý định nghiệp vụ.
2. Sau khi kết nối lại, truy vấn trạng thái operation bằng key đó.
3. Nếu operation đã hoàn tất, trả lại kết quả đã lưu.
4. Nếu chưa tồn tại hoặc còn ở trạng thái trung gian, tiếp tục theo quy trình phục hồi được thiết kế.
5. Không tự tạo một operation mới chỉ vì client timeout khi COMMIT.

Với một thao tác chỉ có trong database, unique request key và trạng thái operation có thể giúp xác định kết quả. Với side effect ngoài, cần thêm idempotency key của provider, outbox hoặc quy trình đối soát.

## 11. Retry và thao tác không thể lặp tự do

Không phải mọi logic đều an toàn khi thực thi nhiều lần. Những thao tác sau cần thiết kế riêng:

- Gửi email hoặc SMS.
- Thu tiền hoặc hoàn tiền.
- Gửi thông báo đẩy.
- Gọi API tạo tài nguyên ở dịch vụ khác.
- Ghi tệp hoặc upload tài liệu.
- Phát message đến hệ thống không hỗ trợ deduplication.
- Tăng bộ đếm bên ngoài database.
- Ghi log nghiệp vụ mà mỗi lần ghi đều tạo một sự kiện mới.

Nếu một side effect phải xảy ra đúng một lần theo nghiệp vụ, không đặt nó trong callback transaction có thể bị framework retry tự động trừ khi side effect đó có idempotency.

Một số cách xử lý:

**Idempotency key:** dùng cùng một key qua mọi lần retry để dịch vụ nhận diện cùng một yêu cầu.

**Transactional Outbox:** ghi ý định gửi sự kiện trong transaction database, sau đó worker phát lại an toàn.

**Inbox/deduplication:** consumer lưu EventId đã xử lý trong cùng transaction với thay đổi nghiệp vụ của nó.

**Saga/compensation:** nếu một bước đã thành công nhưng bước sau thất bại, thực hiện hành động bù trừ có định danh và có thể retry.

**Đối soát:** với payment hoặc hệ thống bên ngoài, truy vấn trạng thái giao dịch trước khi quyết định gửi lại hoặc hoàn tiền.

## 12. Khi nào retry tự động, khi nào cần người dùng quyết định?

| Tình huống | Cách xử lý |
|---|---|
| Deadlock victim và thao tác có thể lặp an toàn | Rollback và retry toàn bộ transaction với giới hạn |
| Serialization failure | Rollback, đọc lại snapshot và chạy lại toàn bộ transaction |
| Lock wait timeout | Kiểm tra DBMS đã rollback statement hay transaction; quyết định retry theo trạng thái và logic |
| Optimistic version conflict trong biểu mẫu | Tải lại dữ liệu, merge nếu an toàn hoặc yêu cầu người dùng giải quyết |
| Unique constraint do người khác vừa tạo cùng giá trị | Trả lỗi nghiệp vụ hoặc đọc kết quả hiện hành; không retry mù |
| CHECK/foreign key violation do dữ liệu đầu vào | Trả lỗi validation; sửa đầu vào trước khi thử lại |
| Timeout trong lúc COMMIT | Xác định kết quả bằng idempotency key hoặc trạng thái operation; không giả định rollback |
| HTTP timeout khi gọi dịch vụ ngoài | Tra cứu trạng thái bằng request key; retry cùng key nếu dịch vụ hỗ trợ |

Retry tự động phù hợp với xung đột tạm thời mà ứng dụng có thể giải quyết bằng cách đọc lại và tính toán lại. Nếu việc áp dụng lại thay đổi có thể làm thay đổi ý định của người dùng, ứng dụng cần thông báo xung đột thay vì tự ghi đè.

## 13. Giảm nhu cầu retry bằng cách thiết kế transaction tốt hơn

Retry cần thiết nhưng không nên là cơ chế duy nhất để chịu đựng contention.

**Giữ transaction ngắn.** Không chờ người dùng, HTTP, RPC hoặc message broker khi transaction đang mở.

**Truy cập tài nguyên theo cùng thứ tự.** Nếu các transaction đều cập nhật Account A rồi Account B, nguy cơ deadlock do thứ tự khóa ngược nhau sẽ giảm so với việc mỗi transaction chọn thứ tự khác nhau.

**Dùng câu lệnh nguyên tử.** Đưa điều kiện và phép cập nhật vào cùng một UPDATE khi nghiệp vụ có thể biểu diễn như vậy.

**Tạo index phù hợp.** Index có thể giảm phạm vi quét và số khóa cần lấy, nhưng index bổ sung cũng làm tăng chi phí ghi.

**Chia batch hợp lý.** Với thao tác hàng loạt, COMMIT từng batch có thể giảm thời gian giữ khóa; phải bảo đảm nghiệp vụ chấp nhận xử lý từng phần.

**Bảo vệ invariant bằng constraint hoặc guard row.** Đừng chỉ đọc COUNT rồi giả định kết quả vẫn đúng khi ghi. Dùng cơ chế database có thể thực thi đồng thời.

**Không giữ snapshot quá lâu.** Transaction đọc kéo dài có thể giữ phiên bản cũ và làm tăng chi phí MVCC, ngoài nguy cơ xung đột.

## 14. Theo dõi và kiểm chứng retry

Để biết retry có giúp hệ thống phục hồi hay đang che giấu một vấn đề thiết kế, hãy ghi nhận:

- Tổng số transaction và tỷ lệ transaction phải retry.
- Số deadlock, serialization failure, lock wait timeout và optimistic conflict.
- Loại lỗi theo DBMS và mã lỗi cụ thể.
- Số lần retry trung bình và tối đa cho mỗi request.
- Tỷ lệ retry thành công.
- Tổng thời gian thêm do backoff và thực thi lại.
- Transaction hoặc câu truy vấn thường xuyên xuất hiện trong deadlock.
- Số operation trùng bị deduplicate.
- Các trường hợp COMMIT có kết quả không xác định.

Có thể dùng công cụ theo DBMS:

| DBMS | Nguồn chẩn đoán |
|---|---|
| PostgreSQL | Log SQLSTATE 40001/40P01, pg_stat_activity, pg_locks và deadlock log |
| SQL Server | Extended Events deadlock graph, error 1205, sys.dm_tran_locks và sys.dm_exec_requests |
| MySQL InnoDB | SHOW ENGINE INNODB STATUS, Performance Schema data_locks/data_lock_waits và error log |
| Oracle | Alert log, deadlock trace, thông tin ORA-08177/ORA-00060 và session wait |

Đừng chỉ đếm số lần retry. Nếu tỷ lệ retry tăng đột ngột, cần tìm transaction nào tranh chấp, dữ liệu nào thường bị cập nhật đồng thời và có thể giảm phạm vi khóa hoặc thời gian transaction hay không.

## 15. Những nguyên tắc cần ghi nhớ

- Transaction thường là một đơn vị đọc, kiểm tra, tính toán và ghi có quan hệ phụ thuộc.
- Khi deadlock hoặc serialization failure hủy transaction, kết quả đọc và tính toán trước đó có thể không còn hợp lệ.
- Retry riêng câu SQL cuối có thể dùng dữ liệu cũ, ghi đè thay đổi mới hoặc vi phạm invariant.
- Retry toàn bộ transaction nghĩa là rollback, mở transaction mới, đọc lại dữ liệu, kiểm tra lại quy tắc, tính toán lại và ghi lại.
- Không phải mọi lỗi đều yêu cầu retry toàn transaction; phạm vi rollback phụ thuộc DBMS và loại lỗi.
- PostgreSQL serialization failure 40001 và deadlock 40P01 cần transaction mới; SQL Server deadlock victim 1205 và InnoDB deadlock 1213 thường rollback transaction victim.
- Lock wait timeout và deadlock không nhất thiết có cùng phạm vi rollback trên mọi DBMS.
- Chỉ retry lỗi tạm thời đã nhận diện; không retry mù constraint violation hoặc lỗi validation.
- Dùng giới hạn retry, exponential backoff và jitter để tránh retry storm.
- Dữ liệu cần đọc lại phải nằm bên trong callback hoặc ranh giới retry; không tái sử dụng object cũ từ trước vòng lặp.
- Dùng idempotency key, Outbox, Inbox hoặc Saga để bảo vệ side effect bên ngoài.
- Timeout khi COMMIT có thể để lại kết quả không xác định; hãy tra cứu bằng request key thay vì giả định rollback.

Thực thi lại toàn bộ giao dịch là cách khôi phục tính nhất quán của một quyết định nghiệp vụ sau khi lịch chạy ban đầu bị xung đột. Một transaction mới đọc trạng thái mới, kiểm tra lại điều kiện và tạo ra thay đổi phù hợp với dữ liệu mà database đang bảo vệ. Khi thiết kế đúng ranh giới retry và idempotency, ứng dụng có thể phục hồi từ deadlock hoặc serialization failure mà không làm mất cập nhật hay lặp lại side effect.

