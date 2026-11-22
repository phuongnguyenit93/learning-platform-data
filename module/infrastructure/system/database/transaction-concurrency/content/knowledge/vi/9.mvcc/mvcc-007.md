# Xung đột giữa các giao dịch cùng ghi một hàng

MVCC cho phép nhiều transaction đọc các phiên bản dữ liệu khác nhau mà không phải chặn nhau trong mọi trường hợp. Tuy nhiên, khi hai transaction cùng muốn cập nhật **một hàng**, cơ sở dữ liệu vẫn phải điều phối xung đột ghi. Một hàng không thể nhận đồng thời hai phiên bản mới dựa trên cùng một trạng thái cũ mà không có quy tắc xác định phiên bản nào được chấp nhận.

Cách xử lý cụ thể phụ thuộc DBMS và isolation level. Một số hệ quản trị khiến transaction ghi sau chờ transaction ghi trước rồi tiếp tục trên phiên bản mới nhất; một số trường hợp có thể hủy transaction ghi sau bằng lỗi serialization. Nếu ứng dụng đọc một giá trị cũ rồi gửi lại một giá trị tuyệt đối để ghi, nó còn có thể gây ra **lost update** (mất cập nhật), ngay cả khi DBMS đã tuần tự hóa hai câu lệnh ghi.

## 1. Vì sao MVCC vẫn cần điều phối người ghi?

MVCC (Multi-Version Concurrency Control) lưu giữ nhiều phiên bản của một hàng để transaction đọc có thể nhìn thấy phiên bản phù hợp với snapshot của mình. Ví dụ, khi transaction A cập nhật số dư từ 100 lên 110, DBMS tạo hoặc ghi nhận phiên bản mới. Một transaction đọc khác có thể tiếp tục nhìn thấy phiên bản cũ theo snapshot của nó.

Điều đó không có nghĩa hai transaction có thể tự do ghi hai phiên bản mới từ cùng một phiên bản cũ rồi cùng commit. Với thao tác ghi, DBMS phải xác định:

- Transaction nào được quyền tạo phiên bản mới trước.
- Transaction còn lại phải chờ, áp dụng thay đổi lên phiên bản mới, hay bị hủy.
- Điều kiện trong câu lệnh UPDATE còn đúng sau khi transaction kia hoàn tất hay không.

Vì vậy, MVCC thường phối hợp với khóa ghi hoặc một cơ chế phát hiện xung đột. Khóa ghi điều phối các writer cùng nhắm vào một hàng; MVCC giúp các reader tiếp tục đọc phiên bản phù hợp mà không nhất thiết phải chờ writer.

Cần phân biệt hai khái niệm:

- **Write-write conflict**: hai transaction cùng muốn ghi một hàng trong khi thao tác của chúng xung đột.
- **Lost update**: một cập nhật hợp lệ trước đó bị ghi đè bởi giá trị được tính từ dữ liệu cũ, khiến kết quả của cập nhật trước biến mất.

Write-write conflict là tình huống DBMS phải điều phối. Lost update là một lỗi kết quả có thể xuất hiện nếu cách đọc, tính toán và ghi của ứng dụng không bảo vệ được ý định cập nhật.

## 2. Hai transaction cùng cập nhật một hàng

Giả sử bảng tài khoản có một hàng:

~~~sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    balance DECIMAL(18, 2) NOT NULL
);

INSERT INTO accounts (account_id, balance)
VALUES (1, 100.00);
~~~

Hai request cùng đọc số dư 100. Request A muốn cộng 10; request B muốn cộng 20. Nếu ứng dụng đọc số dư, tính kết quả ở bộ nhớ rồi gửi một giá trị tuyệt đối vào câu UPDATE, lịch thực thi có thể như sau:

| Thời điểm | Transaction A | Transaction B | Giá trị đã commit |
|---|---|---|---:|
| 1 | Đọc balance = 100 | | 100 |
| 2 | | Đọc balance = 100 | 100 |
| 3 | Ghi balance = 110 | | Chưa commit |
| 4 | Commit | | 110 |
| 5 | | Ghi balance = 120, dựa trên giá trị đã đọc ở thời điểm 2 | 120 |
| 6 | | Commit | 120 |

B đã ghi 120 dựa trên số dư cũ 100. Kết quả cuối là 120, trong khi nếu cả hai lần cộng đều được áp dụng thì kết quả phải là 130. Phần tăng 10 của A đã bị mất.

Ví dụ SQL minh họa cách ứng dụng gửi giá trị tuyệt đối:

~~~sql
-- A đã đọc 100 và tính 100 + 10 ở phía ứng dụng.
UPDATE accounts
SET balance = 110.00
WHERE account_id = 1;

-- B cũng đã đọc 100 và tính 100 + 20 ở phía ứng dụng.
UPDATE accounts
SET balance = 120.00
WHERE account_id = 1;
~~~

Trong PostgreSQL ở mức READ COMMITTED, nếu B chạy UPDATE trong lúc A đang giữ khóa ghi trên hàng, B sẽ chờ A kết thúc. Nếu A commit, PostgreSQL tìm phiên bản hàng mới và đánh giá lại điều kiện WHERE trên phiên bản đó. Tuy nhiên, giá trị gán cố định 120 trong câu lệnh của B vẫn là 120; DBMS không thể tự suy ra rằng ứng dụng muốn cộng thêm 20 vào số dư mới nhất. Do đó, B có thể ghi đè kết quả 110 bằng 120.

Đây là điểm quan trọng: việc DBMS buộc hai thao tác ghi diễn ra lần lượt không tự động bảo đảm phép tính mà ứng dụng thực hiện từ một lần đọc trước đó vẫn đúng.

## 3. UPDATE theo biểu thức giúp tránh lost update trong phép cộng

Nếu nghiệp vụ là cộng hoặc trừ một lượng trên giá trị hiện tại, hãy để phép tính diễn ra trong chính câu UPDATE:

~~~sql
-- A: cộng 10 vào giá trị hiện tại của hàng.
UPDATE accounts
SET balance = balance + 10.00
WHERE account_id = 1;

-- B: cộng 20 vào giá trị hiện tại của hàng.
UPDATE accounts
SET balance = balance + 20.00
WHERE account_id = 1;
~~~

Trong PostgreSQL ở mức READ COMMITTED, nếu B phải chờ A, sau khi A commit, thao tác UPDATE của B được áp dụng lên phiên bản hàng mới nhất. Kết quả là 130 thay vì ghi đè bằng một giá trị đã tính từ snapshot cũ.

Đây là một cập nhật nguyên tử ở phía DBMS: phép đọc giá trị hiện tại, tính toán và ghi phiên bản mới nằm trong một câu lệnh được điều phối như một thao tác cập nhật. Ứng dụng không cần mang giá trị cũ ra ngoài rồi gửi lại kết quả tuyệt đối.

Có thể kết hợp điều kiện nghiệp vụ ngay trong câu lệnh:

~~~sql
UPDATE accounts
SET balance = balance - 20.00
WHERE account_id = 1
  AND balance >= 20.00;
~~~

Ứng dụng cần kiểm tra số hàng bị ảnh hưởng:

- Một hàng được cập nhật: tài khoản có đủ số dư và thao tác đã được thực hiện.
- Không có hàng nào được cập nhật: tài khoản không tồn tại hoặc điều kiện số dư không còn đúng.

Điều kiện phải nằm trong câu UPDATE để DBMS đánh giá nó khi thực hiện cập nhật. Nếu ứng dụng chỉ SELECT kiểm tra số dư rồi mới gửi một UPDATE không có điều kiện tương ứng, một transaction khác vẫn có thể thay đổi số dư ở giữa hai thao tác.

Với bất biến quan trọng, hãy bổ sung constraint ở DBMS. Ví dụ:

~~~sql
ALTER TABLE accounts
ADD CONSTRAINT accounts_balance_nonnegative
CHECK (balance >= 0);
~~~

Câu UPDATE có điều kiện thể hiện quy tắc của thao tác; CHECK constraint bảo vệ dữ liệu trước mọi đường ghi có thể đưa số dư xuống âm.

## 4. DBMS xử lý xung đột ghi như thế nào?

Không có một cách xử lý giống nhau tuyệt đối cho mọi DBMS. Các cơ chế thường gặp gồm:

1. **Chờ khóa ghi**: transaction ghi sau chờ transaction đang giữ khóa trên hàng kết thúc. Sau đó DBMS có thể tiếp tục trên phiên bản mới nhất theo ngữ nghĩa isolation của hệ quản trị.
2. **Phát hiện xung đột và hủy transaction**: DBMS từ chối cập nhật nếu hàng đã thay đổi kể từ snapshot mà transaction đang sử dụng. Ứng dụng nhận lỗi và có thể chạy lại toàn bộ transaction.
3. **Kiểm tra phiên bản do ứng dụng quản lý**: câu UPDATE chỉ thành công nếu version vẫn bằng giá trị mà ứng dụng đã đọc. Nếu không còn khớp, không có hàng nào được cập nhật.

Các cách này có mục tiêu chung là tránh để hai writer âm thầm tạo ra một trạng thái không hợp lệ. Chúng khác nhau ở thời điểm chờ, điều kiện tiếp tục và cách báo lỗi cho ứng dụng.

### Ví dụ với PostgreSQL

PostgreSQL cho thấy rõ sự khác biệt giữa READ COMMITTED và REPEATABLE READ khi hai transaction cùng cập nhật một hàng.

**READ COMMITTED**

Mỗi câu lệnh có snapshot riêng. Khi UPDATE gặp một hàng đang bị transaction khác cập nhật, câu lệnh có thể phải chờ. Nếu transaction kia commit, PostgreSQL tiếp tục với phiên bản hàng mới và đánh giá lại điều kiện WHERE. Điều này cho phép câu lệnh cập nhật trên trạng thái mới nhất, nhưng không sửa được một giá trị tuyệt đối đã được ứng dụng tính từ lần đọc cũ.

**REPEATABLE READ**

Transaction tiếp tục nhìn thấy snapshot ổn định của nó. Nếu transaction khác đã cập nhật hàng mà transaction hiện tại muốn sửa sau thời điểm snapshot được thiết lập, PostgreSQL hủy thao tác hiện tại bằng lỗi serialization, thường có thông báo dạng “could not serialize access due to concurrent update”. Transaction phải rollback và được ứng dụng chạy lại từ đầu để đọc trạng thái mới.

**SERIALIZABLE**

PostgreSQL bổ sung phát hiện các phụ thuộc đọc/ghi có thể tạo ra kết quả không tương đương với một thứ tự tuần tự. DBMS có thể hủy một transaction với lỗi serialization dù từng câu lệnh riêng lẻ có vẻ hợp lệ. Ứng dụng phải sẵn sàng retry toàn bộ transaction.

Các mô tả trên là hành vi cụ thể của PostgreSQL. Những DBMS khác có thể định nghĩa REPEATABLE READ, snapshot isolation, khóa ghi và thời điểm phát hiện xung đột khác nhau. Khi thiết kế hoặc chẩn đoán, cần đối chiếu tài liệu của đúng hệ quản trị và isolation level đang chạy.

## 5. Bốn cách bảo vệ cập nhật

Chọn cách bảo vệ dựa trên việc nghiệp vụ cần tính toán từ giá trị mới nhất, cần đọc nhiều dữ liệu trước khi quyết định, hay muốn phát hiện dữ liệu đã thay đổi.

### Cách 1: Cập nhật nguyên tử bằng một câu SQL

Đây thường là lựa chọn đơn giản nhất cho phép cộng, trừ hoặc tăng bộ đếm:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 101
  AND quantity > 0;
~~~

DBMS điều phối các writer trên hàng. Điều kiện quantity > 0 được đánh giá trong thao tác cập nhật, giúp hai request không cùng bán một sản phẩm cuối cùng dựa trên cùng một lần đọc cũ.

Cách này phù hợp khi toàn bộ quy tắc có thể biểu diễn bằng một câu lệnh. Ứng dụng cần kiểm tra số hàng bị ảnh hưởng và xử lý trường hợp không cập nhật được.

### Cách 2: Khóa hàng trước khi đọc và ra quyết định

Khi nghiệp vụ phải đọc nhiều cột, kiểm tra nhiều điều kiện rồi mới quyết định cách cập nhật, có thể khóa hàng tường minh trong transaction:

~~~sql
BEGIN;

SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

-- Kiểm tra và tính toán dựa trên giá trị vừa đọc.
-- Thực hiện UPDATE trong cùng transaction.

UPDATE accounts
SET balance = balance - 20.00
WHERE account_id = 1;

COMMIT;
~~~

SELECT ... FOR UPDATE yêu cầu khóa các hàng được chọn theo ngữ nghĩa của DBMS. Writer khác cần khóa xung đột trên hàng đó sẽ phải chờ. Ứng dụng đọc dữ liệu sau khi lấy được khóa, nên có thể đưa ra quyết định dựa trên trạng thái được bảo vệ trong transaction.

Giữ transaction ngắn và không gọi dịch vụ bên ngoài trong khi đang giữ khóa. Nếu transaction mở quá lâu, các writer khác có thể phải chờ lâu và làm giảm khả năng xử lý đồng thời.

### Cách 3: Optimistic locking bằng cột version

Nếu xung đột ít xảy ra và ứng dụng muốn phát hiện dữ liệu đã thay đổi kể từ lúc đọc, có thể thêm cột version:

~~~sql
ALTER TABLE inventory
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
~~~

Khi đọc hàng, ứng dụng lấy cả quantity và version. Khi ghi, nó chỉ cập nhật nếu version vẫn đúng:

~~~sql
UPDATE inventory
SET quantity = 9,
    version = version + 1
WHERE product_id = 101
  AND version = 7;
~~~

Nếu một hàng được cập nhật, version đã khớp và thao tác thành công. Nếu không có hàng nào được cập nhật, một transaction khác đã thay đổi version hoặc hàng không tồn tại. Ứng dụng phải đọc lại trạng thái mới và quyết định có thể thử lại hay cần báo xung đột cho người dùng.

Cột version không tự tạo ra cơ chế optimistic locking. Ứng dụng phải luôn tăng version trong mọi đường cập nhật liên quan và phải kiểm tra số hàng bị ảnh hưởng. Nếu một đường ghi thay đổi dữ liệu nhưng quên tăng version, cơ chế phát hiện xung đột có thể bị vô hiệu.

### Cách 4: Dùng SERIALIZABLE và retry transaction

Khi nghiệp vụ có nhiều lần đọc và ghi mà không thể biểu diễn an toàn bằng một câu SQL đơn giản, SERIALIZABLE có thể giúp bảo đảm kết quả tương đương với một thứ tự thực thi tuần tự.

Đổi lại, DBMS có thể hủy transaction để phá vỡ một lịch thực thi không an toàn. Ứng dụng phải nhận diện lỗi serialization, rollback và chạy lại toàn bộ transaction. Việc chạy lại chỉ một câu UPDATE thường không đủ vì các quyết định trước đó có thể đã dựa trên dữ liệu cũ.

Serializable không có nghĩa mọi transaction sẽ chạy lần lượt từ đầu đến cuối. DBMS vẫn có thể cho phép nhiều transaction chạy đồng thời và chỉ hủy những transaction gây ra xung đột không thể chấp nhận.

## 6. So sánh các chiến lược

| Chiến lược | Cách phát hiện/điều phối | Phù hợp khi | Điểm cần lưu ý |
|---|---|---|---|
| UPDATE nguyên tử | DBMS điều phối ghi và tính toán trên hàng hiện tại | Phép cộng, trừ, tăng/giảm số lượng | Điều kiện nghiệp vụ phải nằm trong câu SQL |
| SELECT FOR UPDATE | Lấy khóa trước khi đọc và quyết định | Nghiệp vụ cần nhiều bước đọc/ghi trên cùng hàng | Giữ transaction và khóa càng ngắn càng tốt |
| Optimistic locking | So sánh version trong điều kiện UPDATE | Xung đột ít, cần phát hiện dữ liệu đã bị sửa | Phải tăng version trong mọi đường ghi và kiểm tra số hàng |
| SERIALIZABLE | DBMS phát hiện lịch thực thi không tuần tự được | Quy tắc nghiệp vụ phụ thuộc nhiều lần đọc/ghi | Phải retry toàn bộ transaction khi có lỗi serialization |

Có thể kết hợp các chiến lược. Ví dụ, một transaction chạy ở SERIALIZABLE vẫn có thể dùng UPDATE nguyên tử để thể hiện rõ ý định thay đổi dữ liệu. Một ứng dụng dùng version vẫn nên có CHECK hoặc UNIQUE constraint để bảo vệ các bất biến dữ liệu.

## 7. Xung đột ghi khác gì deadlock?

Hai transaction cùng ghi một hàng thường tạo ra tình trạng một transaction phải chờ transaction kia. Việc chờ đơn thuần chưa phải deadlock.

Deadlock xảy ra khi các transaction tạo thành vòng chờ. Ví dụ:

~~~text
Transaction A                         Transaction B
-------------                         -------------
Khóa hàng tài khoản 1                 Khóa hàng tài khoản 2
Cần khóa hàng tài khoản 2             Cần khóa hàng tài khoản 1
Chờ B                                 Chờ A
             \                       /
              \_____ Vòng chờ ______/
~~~

DBMS phát hiện vòng chờ và hủy một transaction để giải phóng hệ thống. Transaction bị hủy cần rollback; ứng dụng có thể retry nếu nghiệp vụ cho phép.

Để giảm deadlock khi cập nhật nhiều hàng, các transaction nên lấy khóa theo cùng một thứ tự, chẳng hạn luôn theo account_id tăng dần. Đồng thời, tránh giữ khóa trong lúc chờ mạng, gọi API hoặc thực hiện tác vụ tốn thời gian.

## 8. Retry sau xung đột cần được thiết kế cẩn thận

Retry là một phần bình thường của ứng dụng chạy với isolation level có thể hủy transaction. Tuy nhiên, retry phải giữ đúng ranh giới nghiệp vụ:

- **Chạy lại toàn bộ transaction** khi DBMS báo serialization failure. Các câu SELECT, phép tính và UPDATE cần được thực hiện lại trên snapshot mới.
- **Phân biệt lỗi có thể retry với lỗi nghiệp vụ**. Version không khớp có thể có nghĩa người dùng đang sửa dữ liệu cũ và cần tải lại màn hình, không nhất thiết tự động ghi đè.
- **Giới hạn số lần retry và thêm độ trễ ngẫu nhiên** để nhiều request không liên tục va chạm lại cùng thời điểm.
- **Bảo đảm thao tác bên ngoài không bị lặp**. Gửi email, trừ tiền qua nhà cung cấp hoặc gọi API không nằm trong transaction DB có thể đã xảy ra dù transaction sau đó rollback. Chỉ thực hiện side effect sau commit hoặc dùng cơ chế outbox/idempotency phù hợp.
- **Ghi log thông tin cần thiết** như loại lỗi, isolation level, khóa hàng hoặc định danh nghiệp vụ và số lần retry để tìm ra điểm nóng tranh chấp.

Với PostgreSQL, SQLSTATE 40001 biểu thị serialization failure; SQLSTATE 40P01 biểu thị deadlock detected. Ứng dụng có thể dùng mã lỗi để phân loại và quyết định retry. Cần kiểm tra mã lỗi theo driver và DBMS đang sử dụng thay vì dựa vào nội dung thông báo lỗi dạng văn bản.

## 9. Cách quan sát và tái hiện write-write conflict

Một bài kiểm tra đơn giản có thể dùng hai connection độc lập tới cùng một cơ sở dữ liệu.

**Connection A**

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance + 10
WHERE account_id = 1;

-- Tạm thời chưa COMMIT.
~~~

**Connection B**

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance + 20
WHERE account_id = 1;

-- Trong DBMS dùng khóa ghi, câu lệnh có thể đang chờ A.
~~~

Quay lại Connection A:

~~~sql
COMMIT;
~~~

Sau đó quan sát Connection B tiếp tục hay nhận lỗi theo DBMS và isolation level. Nếu B tiếp tục thành công với hai phép cộng nguyên tử, đọc lại hàng sau khi cả hai commit sẽ thấy tổng thay đổi là 30. Nếu đổi B thành một giá trị tuyệt đối đã tính từ lần đọc cũ, kết quả có thể khác.

Khi thử nghiệm, hãy dùng hai connection thực sự độc lập. Hai câu lệnh chạy tuần tự trên cùng một connection không tái hiện được xung đột ghi giữa các transaction đồng thời.

Các dấu hiệu hữu ích khi quan sát:

- Một câu UPDATE đang chờ có thể đang đợi transaction khác nhả khóa ghi.
- Transaction nhận serialization failure cần được rollback trước khi retry.
- Một câu UPDATE ảnh hưởng 0 hàng có thể do điều kiện WHERE không còn đúng, version đã thay đổi hoặc hàng không tồn tại.
- Thời gian chờ khóa tăng thường cho thấy nhiều transaction đang tranh chấp cùng một tập hàng.

Tên view, câu lệnh và công cụ quan sát lock khác nhau giữa PostgreSQL, MySQL, SQL Server và Oracle. Hãy dùng công cụ giám sát của DBMS đang vận hành để xác định transaction giữ khóa, transaction đang chờ và đối tượng bị tranh chấp.

## 10. Những điều cần nhớ khi thiết kế MVCC

- MVCC giúp reader nhìn thấy phiên bản phù hợp với snapshot; nó không loại bỏ việc điều phối hai writer cùng cập nhật một hàng.
- Khi hai writer xung đột, DBMS có thể buộc chờ, áp dụng thay đổi lên phiên bản mới hoặc hủy một transaction. Hành vi phụ thuộc DBMS và isolation level.
- Tuần tự hóa hai câu UPDATE không đủ ngăn lost update nếu ứng dụng gửi lại một giá trị tuyệt đối được tính từ lần đọc cũ.
- Với phép cộng/trừ, hãy ưu tiên UPDATE nguyên tử và đặt điều kiện nghiệp vụ trong câu lệnh.
- Khi cần đọc rồi quyết định, có thể khóa hàng bằng SELECT FOR UPDATE hoặc dùng version để phát hiện dữ liệu đã thay đổi.
- SERIALIZABLE có thể hủy transaction; ứng dụng cần retry toàn bộ transaction và kiểm soát side effect.
- Constraint vẫn cần thiết để bảo vệ bất biến dữ liệu trước mọi đường ghi.

Khi phân tích một xung đột giữa hai transaction cùng ghi một hàng, hãy lần theo phiên bản mà mỗi transaction đã đọc, thời điểm chúng yêu cầu ghi, isolation level và cách DBMS giải quyết xung đột. Sau đó kiểm tra ứng dụng có gửi một phép cập nhật trên giá trị hiện tại hay đang ghi đè bằng kết quả tính từ dữ liệu cũ. Hai bước này giúp phân biệt việc DBMS đang điều phối writer với lỗi lost update ở tầng nghiệp vụ.
