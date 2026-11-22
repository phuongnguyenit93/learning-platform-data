# Nhìn thấy thay đổi do chính giao dịch tạo ra

Trong cơ chế MVCC (*Multi-Version Concurrency Control*), một giao dịch thường đọc dữ liệu từ một ảnh chụp (*snapshot*) gồm các phiên bản đã commit và phù hợp với quy tắc hiển thị của nó. Tuy nhiên, có một quy tắc đặc biệt: **giao dịch phải nhìn thấy những thay đổi do chính nó tạo ra trước đó**.

Quy tắc này thường được gọi là *read-your-own-writes* (đọc được thay đổi của chính mình). Nó cho phép một giao dịch thực hiện nhiều câu lệnh liên tiếp và dùng kết quả của các câu lệnh ghi trước đó trong những lần đọc tiếp theo, ngay cả khi giao dịch chưa commit.

Ví dụ đơn giản: giao dịch `T1` đọc số dư là `1.000`, trừ đi `100`, rồi đọc lại số dư. Lần đọc thứ hai của `T1` phải nhận được `900`. Nếu nó vẫn nhận `1.000` chỉ vì phiên bản mới chưa commit, giao dịch sẽ không thể làm việc nhất quán với những thay đổi do chính nó thực hiện.

## 1. Vì sao MVCC cần quy tắc này?

MVCC lưu giữ nhiều phiên bản của cùng một hàng dữ liệu. Khi một giao dịch cập nhật hàng, hệ quản trị cơ sở dữ liệu có thể tạo phiên bản mới thay vì ghi đè ngay phiên bản mà các giao dịch khác đang đọc.

Giả sử hàng `account` có số dư ban đầu là `1.000`:

```text
Phiên bản V1: balance = 1.000  (đã commit)
       |
       | T1 cập nhật số dư, tạo phiên bản mới
       v
Phiên bản V2: balance = 900    (do T1 tạo, chưa commit)
```

Trong lúc `T1` chưa commit, phiên bản `V2` chưa phải dữ liệu đã commit để mọi giao dịch khác có thể nhìn thấy. Nhưng `T1` phải nhìn thấy `V2`, bởi đó là kết quả của chính câu lệnh cập nhật mà nó vừa thực hiện.

Vì vậy, khi xác định phiên bản hiển thị, hệ thống thường phải xét cả hai yếu tố:

- Snapshot và trạng thái commit của phiên bản, để quyết định giao dịch có thể nhìn thấy thay đổi từ các giao dịch khác hay không.
- Danh tính giao dịch tạo ra phiên bản, để giao dịch hiện tại có thể nhìn thấy thay đổi của chính nó.

Có thể mô tả quy tắc ở mức khái niệm như sau:

```text
Nếu phiên bản được tạo bởi giao dịch hiện tại
và thay đổi đó chưa bị rollback:
    phiên bản có thể được giao dịch hiện tại nhìn thấy.
Ngược lại:
    áp dụng quy tắc snapshot và trạng thái commit thông thường.
```

Đây là mô hình giải thích. Mỗi hệ quản trị có thể triển khai bằng transaction ID, command ID, write set, version chain hoặc cơ chế nội bộ khác.

## 2. Đọc lại hàng vừa INSERT

Khi một giao dịch thêm một hàng, hàng đó chưa được commit nên các giao dịch khác thường chưa nhìn thấy nó. Dù vậy, giao dịch thêm hàng có thể truy vấn lại hàng vừa tạo.

Ví dụ:

```sql
BEGIN;

INSERT INTO products (id, name, price)
VALUES (501, 'Keyboard', 750000);

SELECT id, name, price
FROM products
WHERE id = 501;

COMMIT;
```

Kết quả của câu `SELECT` trong cùng giao dịch phải chứa hàng vừa được `INSERT`:

| id | name | price |
|---:|---|---:|
| 501 | Keyboard | 750000 |

Nếu một giao dịch khác chạy truy vấn trước khi `T1` commit, nó thường không nhìn thấy hàng này trong chế độ đọc theo snapshot thông thường. Sau khi `T1` commit, các giao dịch có snapshot bao gồm lần commit đó mới có thể nhìn thấy phiên bản đã commit.

Điểm cần nhớ: việc `T1` đọc được hàng vừa thêm không có nghĩa hàng đã được commit. Nó chỉ có nghĩa thay đổi của `T1` hiển thị trong phạm vi chính `T1`.

## 3. Đọc lại hàng vừa UPDATE

Đây là trường hợp thường gặp nhất. Một giao dịch có thể cập nhật một hàng, rồi tiếp tục đọc giá trị mới để tính toán hoặc kiểm tra điều kiện nghiệp vụ.

Giả sử bảng `accounts` có dữ liệu:

| id | owner | balance |
|---:|---|---:|
| 10 | An | 1000 |

Giao dịch:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE id = 10;

SELECT balance
FROM accounts
WHERE id = 10;

COMMIT;
```

Kết quả của câu `SELECT` trong cùng giao dịch là `900`. Nếu giao dịch tiếp tục cập nhật thêm `50`:

```sql
UPDATE accounts
SET balance = balance + 50
WHERE id = 10;

SELECT balance
FROM accounts
WHERE id = 10;
```

Lần đọc tiếp theo nhận được `950`. Các câu lệnh trong cùng giao dịch làm việc trên trạng thái mà chính giao dịch đã xây dựng qua những thay đổi trước đó.

Quy tắc này cũng áp dụng khi thay đổi ảnh hưởng đến điều kiện lọc, phép nối hoặc phép tổng hợp. Ví dụ, sau khi cập nhật `status` từ `PENDING` thành `PAID`, một câu `SELECT` tiếp theo của cùng giao dịch lọc `WHERE status = 'PAID'` có thể tìm thấy hàng đó. Một truy vấn `COUNT(*)` hoặc `SUM(...)` tiếp theo cũng phản ánh thay đổi của giao dịch hiện tại.

## 4. Đọc sau khi DELETE

Khi một giao dịch xóa một hàng, nó phải xem hàng đó như đã bị xóa trong phạm vi các lần đọc tiếp theo của chính nó, dù phiên bản cũ vẫn có thể được giữ lại để những giao dịch khác đọc theo snapshot.

Ví dụ:

```sql
BEGIN;

DELETE FROM products
WHERE id = 501;

SELECT *
FROM products
WHERE id = 501;

COMMIT;
```

Trong cùng giao dịch, câu `SELECT` sau `DELETE` không trả về hàng `501`. Hệ thống có thể chưa xóa vật lý phiên bản cũ ngay lập tức; MVCC cần giữ phiên bản đó cho các snapshot khác còn được phép nhìn thấy.

Nếu `T1` rollback thay vì commit, thao tác xóa bị hủy. Hàng trở lại trạng thái có thể nhìn thấy đối với các giao dịch theo quy tắc snapshot tương ứng.

## 5. Thay đổi của chính mình và thay đổi của giao dịch khác

Quy tắc đọc được thay đổi của chính mình không có nghĩa một giao dịch được nhìn thấy mọi dữ liệu chưa commit. MVCC phân biệt phiên bản do giao dịch hiện tại tạo ra với phiên bản do giao dịch khác tạo ra.

Xét hai giao dịch `T1` và `T2` cùng làm việc với một tài khoản. Ban đầu `balance = 1000`.

**T1:**

```sql
BEGIN;

UPDATE accounts
SET balance = 900
WHERE id = 10;

SELECT balance FROM accounts WHERE id = 10;
-- T1 nhìn thấy 900
```

**T2**, trong khi `T1` chưa commit:

```sql
BEGIN;

SELECT balance FROM accounts WHERE id = 10;
-- T2 thường nhìn thấy phiên bản đã commit phù hợp với snapshot,
-- chẳng hạn 1000.
```

Ở thời điểm này, `T1` nhìn thấy `900` vì nó là giao dịch tạo ra thay đổi đó. `T2` không tự động nhìn thấy `900`, vì phiên bản này vẫn chưa commit và không thuộc snapshot đọc thông thường của `T2`.

| Giao dịch đọc | Phiên bản do `T1` tạo nhưng chưa commit có hiển thị không? | Lý do |
|---|---|---|
| `T1` | Có | Đây là thay đổi của chính giao dịch hiện tại. |
| `T2` | Thông thường không | Snapshot của `T2` không bao gồm thay đổi chưa commit của giao dịch khác. |

Khi `T1` commit, các giao dịch khác có thể nhìn thấy phiên bản mới theo snapshot và mức cô lập đang áp dụng. Nếu `T1` rollback, phiên bản mới không trở thành dữ liệu đã commit; các giao dịch khác tiếp tục nhìn thấy phiên bản cũ nếu phiên bản đó phù hợp với snapshot của chúng.

## 6. Read-your-own-writes khi snapshot đã được tạo

Một điểm dễ gây nhầm lẫn là snapshot của giao dịch có thể đã được thiết lập trước khi giao dịch thực hiện câu lệnh ghi. Điều đó không làm mất quy tắc nhìn thấy thay đổi của chính mình.

Ví dụ:

```sql
BEGIN;

-- Giả sử câu đọc đầu tiên thiết lập snapshot S.
SELECT balance FROM accounts WHERE id = 10;

UPDATE accounts
SET balance = 900
WHERE id = 10;

-- Dù snapshot S đã được thiết lập trước UPDATE,
-- T1 vẫn nhìn thấy thay đổi do chính T1 tạo ra.
SELECT balance FROM accounts WHERE id = 10;

COMMIT;
```

Snapshot quyết định những phiên bản từ các giao dịch khác mà `T1` được phép nhìn thấy. Nó không khiến `T1` phải bỏ qua các thay đổi hợp lệ của chính `T1`.

Điều này giúp duy trì hai yêu cầu đồng thời:

1. Giao dịch đọc một tập phiên bản nhất quán từ các giao dịch khác theo quy tắc snapshot.
2. Giao dịch vẫn đọc được trạng thái mà nó đã tự tạo ra trong quá trình thực hiện.

## 7. Quan hệ với mức cô lập giao dịch

Read-your-own-writes là quy tắc hiển thị trong phạm vi giao dịch. Mức cô lập chủ yếu quyết định giao dịch nhìn thấy thay đổi của **các giao dịch khác** như thế nào. Hai vấn đề này cần được phân biệt.

### READ COMMITTED

Ở mức `READ COMMITTED`, mỗi câu lệnh đọc thường sử dụng một snapshot phản ánh các thay đổi đã commit trước thời điểm câu lệnh bắt đầu. Nếu một giao dịch đã cập nhật một hàng ở câu lệnh trước, câu lệnh đọc tiếp theo của chính giao dịch vẫn nhìn thấy giá trị do nó vừa cập nhật.

Các giao dịch khác có thể nhìn thấy giá trị mới ở câu lệnh đọc bắt đầu sau khi giao dịch ghi đã commit. Một câu lệnh đọc bắt đầu trước thời điểm commit có thể vẫn nhìn thấy phiên bản cũ.

### REPEATABLE READ hoặc snapshot isolation

Ở các hệ thống triển khai `REPEATABLE READ` bằng snapshot cố định, giao dịch thường tiếp tục đọc phiên bản đã commit phù hợp với snapshot ban đầu khi xét thay đổi từ giao dịch khác. Tuy nhiên, các thay đổi do chính giao dịch tạo ra vẫn hiển thị trong những lần đọc tiếp theo của nó.

Vì vậy, snapshot cố định không có nghĩa giao dịch luôn đọc lại đúng trạng thái ban đầu của chính nó. Snapshot cố định áp dụng cho khả năng nhìn thấy thay đổi từ bên ngoài; write set của giao dịch hiện tại vẫn phải được tính đến.

### SERIALIZABLE

`SERIALIZABLE` bổ sung các quy tắc để kết quả giao dịch tương đương một thứ tự tuần tự hợp lệ. Một hệ thống có thể phát hiện xung đột và từ chối commit bằng lỗi serialization. Khi giao dịch còn tiếp tục hợp lệ, nó vẫn phải nhìn thấy những thay đổi mà chính nó đã thực hiện trước đó.

Tên gọi và chi tiết triển khai của các mức cô lập có thể khác giữa các hệ quản trị. Khi cần kết luận chính xác cho một sản phẩm cụ thể, cần đối chiếu tài liệu của sản phẩm đó, nhất là cách nó định nghĩa `REPEATABLE READ`, snapshot và các thao tác đọc có khóa.

## 8. Rollback ảnh hưởng thế nào đến thay đổi mà giao dịch đã nhìn thấy?

Read-your-own-writes chỉ áp dụng với những thay đổi hiện vẫn còn hiệu lực trong giao dịch. Nếu giao dịch rollback, các thay đổi bị hủy không còn là trạng thái mà giao dịch có thể tiếp tục đọc.

Ví dụ:

```sql
BEGIN;

UPDATE accounts
SET balance = 900
WHERE id = 10;

SELECT balance FROM accounts WHERE id = 10;
-- 900

ROLLBACK;
```

Sau `ROLLBACK`, cập nhật `balance = 900` bị hủy. Một giao dịch mới đọc dữ liệu sẽ thấy giá trị đã commit trước đó, giả sử không có giao dịch khác thay đổi hàng này.

Savepoint cũng cho phép hủy một phần công việc:

```sql
BEGIN;

UPDATE accounts
SET balance = 900
WHERE id = 10;

SAVEPOINT after_debit;

UPDATE accounts
SET balance = 850
WHERE id = 10;

SELECT balance FROM accounts WHERE id = 10;
-- 850

ROLLBACK TO SAVEPOINT after_debit;

SELECT balance FROM accounts WHERE id = 10;
-- 900

COMMIT;
```

Sau khi rollback về savepoint, thay đổi được thực hiện sau savepoint không còn hiệu lực. Lần đọc tiếp theo của giao dịch nhìn thấy trạng thái còn lại: `900`.

## 9. Phân biệt với dirty read

Hai khái niệm thường bị nhầm vì cả hai đều nói đến dữ liệu chưa commit:

- **Read-your-own-writes**: giao dịch đọc thay đổi chưa commit do chính nó tạo ra. Đây là hành vi cần thiết để giao dịch tiếp tục làm việc trên trạng thái của mình.
- **Dirty read**: giao dịch đọc thay đổi chưa commit do một giao dịch khác tạo ra. Nếu giao dịch tạo thay đổi sau đó rollback, giao dịch đọc đã sử dụng dữ liệu không bao giờ được commit.

Ví dụ:

```text
T1: UPDATE balance = 900
T1: chưa commit
T1: SELECT balance       → T1 thấy 900 (read-your-own-writes)
T2: SELECT balance       → không thấy 900 trong snapshot đọc thông thường
T1: ROLLBACK
```

Việc `T1` nhìn thấy `900` không phải dirty read, vì `T1` chính là giao dịch tạo ra thay đổi. Rủi ro dirty read xuất hiện khi `T2` đọc giá trị chưa commit của `T1`.

## 10. Cách quan sát hành vi trong thực tế

Có thể kiểm tra quy tắc này bằng hai phiên kết nối đến cùng cơ sở dữ liệu. Dùng một bảng thử nghiệm và một hàng đã tồn tại để tránh ảnh hưởng dữ liệu nghiệp vụ.

**Phiên A:**

```sql
BEGIN;

UPDATE mvcc_demo
SET value = 'A-uncommitted'
WHERE id = 1;

SELECT value
FROM mvcc_demo
WHERE id = 1;
```

Phiên A phải đọc được `A-uncommitted` trong chính giao dịch đó.

**Phiên B, trước khi phiên A commit:**

```sql
BEGIN;

SELECT value
FROM mvcc_demo
WHERE id = 1;
```

Trong chế độ đọc snapshot thông thường, phiên B đọc phiên bản đã commit phù hợp với snapshot của nó. Kết quả thường là giá trị cũ. Sau đó:

**Phiên A:**

```sql
COMMIT;
```

Một câu lệnh đọc mới của phiên B ở `READ COMMITTED` có thể nhìn thấy giá trị mới nếu câu lệnh bắt đầu sau commit. Ở mức cô lập dùng snapshot cố định, phiên B có thể tiếp tục thấy phiên bản cũ cho đến khi giao dịch kết thúc và tạo snapshot mới.

Cuối cùng, rollback phiên B và mở giao dịch mới để tránh nhầm lẫn do snapshot cũ:

```sql
ROLLBACK;
```

Kết quả quan sát phụ thuộc mức cô lập và chi tiết của hệ quản trị, nhưng điểm cốt lõi cần xác nhận là phiên A đọc được thay đổi của chính nó trước commit.

## 11. Những điểm cần ghi nhớ

- Giao dịch nhìn thấy các thay đổi hợp lệ do chính nó tạo ra trước đó, kể cả khi những thay đổi này chưa commit.
- Quy tắc này áp dụng cho hàng được `INSERT`, `UPDATE` hoặc `DELETE`; lần đọc sau phản ánh trạng thái do giao dịch tự xây dựng.
- Snapshot điều khiển việc nhìn thấy thay đổi từ giao dịch khác. Nó không buộc giao dịch bỏ qua write set của chính mình.
- Giao dịch khác thường không nhìn thấy phiên bản chưa commit do giao dịch hiện tại tạo ra trong chế độ đọc snapshot thông thường.
- `COMMIT` làm thay đổi trở thành dữ liệu đã commit; `ROLLBACK` hủy thay đổi. Rollback về savepoint chỉ hủy phần công việc nằm sau savepoint.
- Đọc thay đổi của chính mình không phải dirty read. Dirty read là đọc thay đổi chưa commit của giao dịch khác.

Khi phân tích một tình huống MVCC, hãy luôn hỏi hai câu riêng: **phiên bản này do giao dịch nào tạo ra?** và **snapshot của giao dịch đang đọc có cho phép nhìn thấy phiên bản đó không?** Nếu phiên bản do chính giao dịch hiện tại tạo ra và thay đổi chưa bị rollback, giao dịch phải có thể nhìn thấy trạng thái của chính nó. Quy tắc đó cho phép MVCC vừa giữ được snapshot phù hợp đối với các giao dịch khác, vừa bảo đảm các câu lệnh trong một giao dịch tiếp nối trên những thay đổi mà giao dịch đã thực hiện.
