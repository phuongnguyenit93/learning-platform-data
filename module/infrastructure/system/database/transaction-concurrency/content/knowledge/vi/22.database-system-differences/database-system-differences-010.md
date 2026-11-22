# Oracle: nhất quán khi đọc, undo và các lựa chọn cô lập

Oracle Database dùng mô hình đa phiên bản (Multi-Version Concurrency Control — MVCC) để cho phép truy vấn đọc dữ liệu nhất quán trong khi các giao dịch khác vẫn cập nhật. Cơ chế này dựa nhiều vào **undo data**: thông tin về trạng thái cũ của dữ liệu. Oracle dùng undo để hoàn tác giao dịch, dựng lại phiên bản dữ liệu tại thời điểm truy vấn bắt đầu và hỗ trợ một số tính năng Flashback.

Điểm cần hiểu rõ là Oracle có hai phạm vi nhất quán khi đọc phổ biến:

- **Statement-level read consistency:** mỗi câu lệnh truy vấn nhìn thấy dữ liệu đã commit tại thời điểm câu lệnh bắt đầu. Đây là hành vi mặc định của `READ COMMITTED`.
- **Transaction-level read consistency:** mọi câu truy vấn trong một transaction nhìn thấy cùng một snapshot được xác định khi transaction bắt đầu. Oracle cung cấp hành vi này cho `SERIALIZABLE` và `READ ONLY`.

Undo giúp Oracle tạo ra snapshot nhất quán mà không cần khóa mọi hàng mà truy vấn đọc. Vì vậy, đọc và ghi thường không chặn nhau; các thao tác ghi trên cùng hàng vẫn phải phối hợp bằng khóa. Khi chọn isolation level, cần cân bằng giữa snapshot nhất quán, khả năng cập nhật đồng thời và yêu cầu bảo vệ bất biến nghiệp vụ.

## 1. Oracle dùng MVCC để làm gì?

Giả sử `T1` đang chạy một truy vấn đọc bảng `accounts`, trong khi `T2` cập nhật số dư của một tài khoản.

Nếu Oracle buộc `T1` chờ mọi giao dịch ghi kết thúc, các truy vấn đọc có thể bị chặn thường xuyên. Thay vào đó, Oracle có thể trả cho `T1` phiên bản dữ liệu đã commit tại thời điểm snapshot của truy vấn. Nếu block hiện tại đã bị thay đổi sau thời điểm đó, Oracle dùng undo để tái tạo phiên bản cũ cần thiết.

```text
T1: bắt đầu SELECT ─────────────── đọc snapshot tại thời điểm S
                                  │
T2:                UPDATE account│ COMMIT
                                  │
Oracle: dùng undo để dựng lại giá trị trước thay đổi cho T1
                                  │
T1: nhận kết quả nhất quán theo snapshot S
```

`T1` không đọc một nửa giá trị cũ và một nửa giá trị mới chỉ vì `T2` commit trong khi truy vấn đang chạy. Một câu SQL đọc có một mốc nhất quán xác định. Các truy vấn tiếp theo có thể có mốc khác nếu transaction đang ở chế độ `READ COMMITTED`.

## 2. SCN và thời điểm snapshot

Oracle dùng **System Change Number (SCN)** để xác định thứ tự các thay đổi và mốc nhất quán của dữ liệu. Có thể xem SCN như một mốc logic trong lịch sử database.

Khi một câu `SELECT` bắt đầu thực thi ở chế độ `READ COMMITTED`, Oracle xác định SCN cho câu truy vấn. Kết quả phải phản ánh các thay đổi đã commit tại SCN đó, cùng với những thay đổi do chính transaction hiện tại tạo ra theo quy tắc của Oracle.

Ví dụ:

1. `T1` bắt đầu một câu truy vấn khi snapshot tương ứng với SCN `S100`.
2. `T2` cập nhật một hàng và commit ở SCN `S105`.
3. `T1` vẫn đang chạy câu truy vấn ban đầu.
4. `T1` tiếp tục nhận dữ liệu nhất quán theo `S100`, nên không thấy thay đổi commit ở `S105`.
5. Nếu `T1` bắt đầu một câu `SELECT` mới sau khi `T2` commit, truy vấn mới có thể thấy giá trị mới.

Mốc SCN cụ thể do Oracle quản lý nội bộ; ứng dụng thông thường không cần tự tính SCN để truy vấn nhất quán. Khái niệm SCN giúp giải thích vì sao hai câu `SELECT` trong cùng một transaction có thể nhìn thấy hai trạng thái khác nhau ở `READ COMMITTED`.

## 3. READ COMMITTED: snapshot cho từng câu lệnh

`READ COMMITTED` là isolation level mặc định của Oracle Database. Một câu lệnh đọc chỉ thấy dữ liệu đã commit trước khi câu lệnh đó bắt đầu. Oracle không cho phép dirty read.

### Ví dụ: hai câu SELECT có thể thấy hai kết quả khác nhau

Giả sử tài khoản A có số dư `100`.

```text
Session 1 (T1)                    Session 2 (T2)
------------------------------    ------------------------------
SELECT balance FROM accounts
→ 100
                                  UPDATE accounts
                                  SET balance = 150
                                  WHERE account_id = 'A';
                                  COMMIT;

SELECT balance FROM accounts
→ 150
```

Hai câu truy vấn của T1 đều nhất quán, nhưng chúng dùng hai snapshot khác nhau. T1 có thể thấy số dư thay đổi giữa hai câu lệnh vì T2 đã commit ở giữa.

### READ COMMITTED bảo đảm và không bảo đảm điều gì?

| Tính chất | Oracle READ COMMITTED |
|---|---|
| Dirty read | Không xảy ra |
| Một câu SELECT đọc dữ liệu nhất quán tại một mốc | Có |
| Đọc lặp lại cùng hàng luôn cho cùng kết quả trong toàn transaction | Không bảo đảm |
| Hai câu SELECT có thể thấy dữ liệu commit khác nhau | Có |
| Truy vấn lặp lại có thể thấy thêm hàng mới phù hợp điều kiện | Có |
| Reader và writer thông thường chặn nhau | Không; Oracle dùng undo cho consistent read |

Do đó, `READ COMMITTED` phù hợp với nhiều ứng dụng giao dịch thông thường. Nhưng nếu logic nghiệp vụ gồm nhiều câu đọc–kiểm tra–ghi và cần một trạng thái nhất quán xuyên suốt, chỉ dựa vào việc mỗi câu `SELECT` đều nhất quán là chưa đủ.

## 4. Transaction-level read consistency

Oracle có thể giữ cùng một snapshot cho toàn bộ transaction. Hai lựa chọn liên quan là `SERIALIZABLE` và `READ ONLY`.

### SERIALIZABLE

Trong transaction `SERIALIZABLE`, các câu truy vấn nhìn thấy những thay đổi đã commit trước khi transaction bắt đầu, cùng với thay đổi do chính transaction tạo ra. Một câu truy vấn sau đó không nhìn thấy các thay đổi được transaction khác commit sau thời điểm bắt đầu.

Ví dụ:

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM orders
WHERE status = 'PENDING';

-- Các câu SELECT tiếp theo trong transaction
-- vẫn dùng snapshot được xác định khi transaction bắt đầu.

COMMIT;
```

`SET TRANSACTION` phải là câu lệnh đầu tiên của transaction. Nếu transaction đã thực hiện một câu SQL bắt đầu giao dịch, không thể tùy tiện đổi isolation level ở giữa transaction.

### READ ONLY

Transaction `READ ONLY` cũng có transaction-level snapshot, nhưng không cho phép các thao tác DML thông thường trong transaction đó. Nó phù hợp với báo cáo cần đọc nhiều bảng và nhiều câu truy vấn trên cùng một trạng thái dữ liệu.

```sql
SET TRANSACTION READ ONLY;

SELECT SUM(amount)
FROM orders
WHERE created_at >= DATE '2026-11-01';

SELECT COUNT(*)
FROM customers
WHERE status = 'ACTIVE';

COMMIT;
```

Hai truy vấn dùng cùng snapshot dù các transaction khác tiếp tục thêm đơn hàng hoặc thay đổi trạng thái khách hàng. Transaction read-only kết thúc bằng `COMMIT` hoặc `ROLLBACK`.

### So sánh ba lựa chọn chính

| Chế độ | Phạm vi snapshot | Có DML? | Mục đích thường gặp |
|---|---|---:|---|
| `READ COMMITTED` | Mỗi câu lệnh | Có | Giao dịch ứng dụng thông thường |
| `SERIALIZABLE` | Toàn transaction | Có, có thể gặp `ORA-08177` | Giao dịch cần snapshot ổn định xuyên suốt |
| `READ ONLY` | Toàn transaction | Không | Báo cáo nhiều truy vấn cần cùng một mốc dữ liệu |

Oracle không cung cấp `READ UNCOMMITTED` như một lựa chọn isolation level; database không cho phép dirty read. `REPEATABLE READ` cũng không phải tên isolation level mà Oracle cấu hình trực tiếp. Nhu cầu đọc lặp lại theo transaction thường được giải quyết bằng `SERIALIZABLE` hoặc `READ ONLY`, tùy transaction có cần ghi hay không.

## 5. Undo là gì?

Khi một transaction sửa dữ liệu, Oracle tạo undo records chứa thông tin cần thiết để khôi phục giá trị trước thay đổi. Undo được quản lý trong undo segments thuộc undo tablespace khi dùng Automatic Undo Management.

Undo có nhiều vai trò:

1. **Rollback:** khôi phục dữ liệu khi transaction chạy `ROLLBACK` hoặc bị hủy.
2. **Read consistency:** dựng phiên bản dữ liệu cũ để truy vấn đọc theo snapshot.
3. **Database recovery:** hỗ trợ hoàn tác các thay đổi chưa commit trong quá trình phục hồi.
4. **Flashback:** hỗ trợ truy vấn hoặc khôi phục dữ liệu tại một thời điểm trước đó trong phạm vi undo còn được giữ.

Ví dụ một hàng được cập nhật:

```text
Trước UPDATE:
  account_id = A
  balance = 100

T2 chạy UPDATE balance = 150

Undo record lưu thông tin cần thiết để khôi phục balance = 100
Data block hiện tại có thể chứa balance = 150
```

Nếu transaction rollback, Oracle dùng undo để hoàn tác thay đổi. Nếu một truy vấn cần đọc snapshot trước khi T2 commit, Oracle cũng có thể dùng undo để dựng phiên bản `balance = 100` mà truy vấn cần.

### Undo và redo khác nhau

| Loại thông tin | Mục đích chính |
|---|---|
| Undo | Hoàn tác thay đổi, dựng phiên bản cũ cho consistent read và hỗ trợ Flashback |
| Redo | Ghi lại thay đổi để phục hồi database sau sự cố |

Undo và redo có liên quan trong cơ chế phục hồi, nhưng chúng không thể thay thế nhau. Redo giúp phát lại thay đổi cần thiết; undo giúp đảo ngược thay đổi chưa được xác nhận hoặc dựng trạng thái trước đó.

## 6. Oracle dựng phiên bản nhất quán như thế nào?

Một data block có thể đã được transaction khác sửa sau SCN snapshot mà truy vấn cần. Oracle không nhất thiết giữ một bản sao đầy đủ của toàn bộ database cho mỗi truy vấn. Thay vào đó, database có thể dùng undo để tái tạo phiên bản block phù hợp.

Quy trình khái niệm:

1. Truy vấn bắt đầu và có SCN snapshot.
2. Oracle đọc block dữ liệu hiện tại.
3. Nếu block chứa thay đổi không thuộc snapshot, Oracle xác định undo cần thiết.
4. Oracle áp dụng thông tin undo để dựng một consistent-read version của block.
5. Truy vấn đọc phiên bản phù hợp với snapshot.

```text
Data block hiện tại
  balance = 150 (đã sửa sau snapshot)
          │
          ▼
Undo record
  giá trị trước đó = 100
          │
          ▼
Consistent-read version
  balance = 100
          │
          ▼
Truy vấn nhận giá trị theo SCN snapshot
```

Oracle có thể tạo các consistent-read clone trong buffer cache để truy vấn sử dụng. Đây là một phần của cơ chế multiversion read consistency. Ứng dụng không cần tự dựng phiên bản dữ liệu bằng SQL.

## 7. Vì sao reader và writer thường không chặn nhau?

Oracle dùng khóa để điều phối các thao tác ghi xung đột, đồng thời dùng undo để phục vụ truy vấn đọc.

- Một câu `SELECT` thông thường không lấy row lock chỉ vì nó đọc một hàng.
- Một transaction sửa hàng sẽ giữ row lock để ngăn transaction khác sửa cùng hàng đồng thời.
- Một reader có thể đọc phiên bản nhất quán cũ bằng undo trong khi writer đang sửa hàng.
- Một writer muốn sửa cùng hàng mà writer khác đang khóa phải chờ transaction giữ khóa commit hoặc rollback.
- `SELECT ... FOR UPDATE` là trường hợp đặc biệt: câu đọc yêu cầu khóa các hàng được chọn để transaction chuẩn bị cập nhật.

| Tương tác | Hành vi thông thường |
|---|---|
| Reader với writer trên cùng hàng | Reader không chặn writer; reader dùng undo để đọc phiên bản nhất quán |
| Writer với reader trên cùng hàng | Writer không chặn câu SELECT thường |
| Writer với writer trên cùng hàng | Writer sau phải chờ khóa được giải phóng |
| `SELECT FOR UPDATE` với writer khác | Có thể tranh chấp khóa vì SELECT này khóa hàng được chọn |

Không nên diễn giải “reader không chặn writer” thành “Oracle không có khóa”. Oracle vẫn dùng khóa hàng và khóa bảng ở các tình huống phù hợp. Điểm khác biệt là truy vấn đọc thường không phải khóa mọi hàng mà nó quan sát.

## 8. SELECT FOR UPDATE khi cần khóa dữ liệu đọc

Nếu ứng dụng cần đọc một hàng rồi cập nhật chính hàng đó, có thể dùng `SELECT ... FOR UPDATE` để lấy khóa trước khi kiểm tra và thay đổi.

```sql
SET TRANSACTION READ WRITE;

SELECT balance
FROM accounts
WHERE account_id = 'A'
FOR UPDATE;

-- Ứng dụng kiểm tra số dư sau khi lấy được khóa.
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 'A';

COMMIT;
```

Khóa được giữ đến khi transaction commit hoặc rollback. Một transaction khác muốn sửa cùng hàng phải chờ. `SELECT FOR UPDATE` phù hợp khi cần bảo vệ một hàng cụ thể qua chuỗi đọc–kiểm tra–cập nhật.

Tuy nhiên, khóa các hàng đã đọc không tự động khóa mọi hàng có thể được thêm vào một tập kết quả trong tương lai. Nếu điều kiện nghiệp vụ phụ thuộc vào nhiều hàng, số lượng hàng hoặc một phạm vi dữ liệu, cần thiết kế cơ chế khóa và ràng buộc bao phủ đúng bất biến đó.

## 9. SERIALIZABLE và ORA-08177

Trong transaction `SERIALIZABLE`, Oracle giữ snapshot ở thời điểm transaction bắt đầu. Nếu transaction cố cập nhật hoặc xóa một hàng đã bị transaction khác thay đổi và commit sau thời điểm transaction hiện tại bắt đầu, Oracle có thể từ chối thao tác với lỗi:

```text
ORA-08177: can't serialize access for this transaction
```

Ví dụ:

```text
T1: SET TRANSACTION ISOLATION LEVEL SERIALIZABLE
T1: đọc hàng A tại snapshot S

T2: UPDATE hàng A
T2: COMMIT

T1: UPDATE hàng A
    → ORA-08177 vì hàng đã được transaction khác sửa
      và commit sau khi T1 bắt đầu
```

Lỗi này là một tín hiệu xung đột serialization. Ứng dụng thường phải rollback transaction hiện tại, bắt đầu transaction mới với snapshot mới, đọc lại dữ liệu và thực hiện lại toàn bộ logic nghiệp vụ. Không nên chỉ chạy lại câu `UPDATE` cuối vì các bước kiểm tra trước đó có thể dựa trên snapshot cũ.

Oracle `SERIALIZABLE` cung cấp transaction-level snapshot và phát hiện các xung đột cập nhật theo quy tắc phiên bản hàng của Oracle. Với một bất biến nghiệp vụ phụ thuộc nhiều hàng khác nhau, không nên mặc định rằng việc đọc snapshot ổn định tự động khóa tất cả hàng đã đọc. Hai transaction có thể đưa ra quyết định dựa trên cùng điều kiện tổng hợp rồi ghi vào các hàng riêng biệt. Với các quy tắc kiểu “ít nhất một nhân viên còn trực” hoặc “tổng số phân bổ không vượt hạn mức”, hãy cân nhắc khóa một hàng điều phối chung, constraint phù hợp hoặc thiết kế ghi có xung đột chung.

## 10. READ ONLY cho báo cáo nhất quán

Một báo cáo có thể cần chạy nhiều truy vấn trên các bảng khác nhau nhưng phải phản ánh cùng một thời điểm. Nếu dùng `READ COMMITTED`, truy vấn đầu và truy vấn sau có thể thấy các transaction commit ở giữa hai truy vấn.

Ví dụ, báo cáo doanh thu và số đơn hàng phải cùng phản ánh một mốc dữ liệu:

```sql
SET TRANSACTION READ ONLY;

SELECT SUM(total_amount)
FROM orders
WHERE order_date >= DATE '2026-11-01';

SELECT COUNT(*)
FROM orders
WHERE order_date >= DATE '2026-11-01';

COMMIT;
```

Với `READ ONLY`, cả hai câu truy vấn nhìn thấy cùng snapshot tại thời điểm transaction bắt đầu. Các transaction khác vẫn có thể cập nhật bảng; báo cáo đọc phiên bản phù hợp bằng undo.

Vì transaction read-only không thực hiện DML, nó tránh được xung đột ghi `ORA-08177`. Tuy nhiên, báo cáo chạy lâu vẫn cần undo đủ lâu để Oracle tái tạo các phiên bản cũ.

## 11. ORA-01555: Snapshot too old

`ORA-01555: snapshot too old` xảy ra khi Oracle cần undo records để dựng phiên bản cũ cho consistent read nhưng các thông tin đó đã bị ghi đè hoặc không còn khả dụng.

Ví dụ:

1. Một truy vấn báo cáo bắt đầu và cần đọc snapshot tại SCN `S100`.
2. Các transaction khác liên tục cập nhật những block mà báo cáo cần đọc.
3. Oracle cần undo để dựng phiên bản trước các cập nhật đó.
4. Undo cần thiết đã bị tái sử dụng trước khi báo cáo đọc đến.
5. Oracle không thể dựng phiên bản đúng snapshot và trả lỗi `ORA-01555`.

Các yếu tố làm tăng nguy cơ:

- Truy vấn hoặc transaction đọc chạy rất lâu.
- Tốc độ phát sinh undo cao do nhiều DML.
- Undo tablespace quá nhỏ so với thời gian truy vấn và mức ghi.
- Cấu hình retention không đáp ứng nhu cầu consistent read hoặc Flashback.
- Có thao tác LOB hoặc workload đặc thù với quy tắc retention riêng.

### Cách xử lý

- Xác định truy vấn nào chạy lâu và block/bảng nào tạo nhiều undo.
- Rút ngắn thời gian chạy truy vấn, tối ưu kế hoạch thực thi và chỉ đọc dữ liệu cần thiết.
- Theo dõi mức phát sinh undo và dung lượng undo tablespace.
- Đánh giá tăng kích thước undo tablespace hoặc khả năng `AUTOEXTEND`.
- Điều chỉnh `UNDO_RETENTION` dựa trên thời gian truy vấn dài nhất và mức phát sinh undo, sau khi kiểm tra dung lượng.
- Chỉ bật `RETENTION GUARANTEE` khi hiểu rõ tác động đến các transaction ghi.

Không nên chỉ tăng `UNDO_RETENTION` mà không xem dung lượng. Nếu không đủ chỗ, Oracle có thể không giữ được toàn bộ undo cần thiết theo mục tiêu retention.

## 12. UNDO_RETENTION và RETENTION GUARANTEE

`UNDO_RETENTION` là tham số thời gian (giây) mà Oracle cố gắng giữ undo cũ để phục vụ consistent read và Flashback. Oracle có cơ chế tự điều chỉnh retention dựa trên cấu hình undo tablespace và hoạt động của hệ thống.

Ví dụ cấu hình:

```sql
ALTER SYSTEM SET UNDO_RETENTION = 3600;
```

Giá trị trên yêu cầu hệ thống hướng tới retention 3.600 giây, tức khoảng một giờ. Khả năng đáp ứng phụ thuộc phiên bản Oracle, cấu hình undo tablespace, autoextend, giới hạn dung lượng và workload. Vì vậy, không nên xem `UNDO_RETENTION` như một bảo đảm tuyệt đối trong mọi cấu hình.

Có thể theo dõi thống kê undo bằng `V$UNDOSTAT`:

```sql
SELECT begin_time,
       end_time,
       tuned_undoretention,
       maxquerylen,
       ssolderrcnt,
       undoblks
FROM v$undostat
ORDER BY begin_time DESC;
```

Các cột hữu ích:

- `TUNED_UNDORETENTION`: retention được Oracle điều chỉnh trong khoảng thống kê.
- `MAXQUERYLEN`: thời gian truy vấn dài nhất trong khoảng thống kê.
- `SSOLDERRCNT`: số lỗi snapshot too old được ghi nhận trong khoảng đó.
- `UNDOBLKS`: lượng block undo được sử dụng trong khoảng thống kê.

### RETENTION GUARANTEE

Undo tablespace có thể bật retention guarantee:

```sql
ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;
```

Khi bật, Oracle không ghi đè undo chưa hết hạn theo chính sách retention đã bảo đảm, kể cả khi điều đó làm transaction DML thất bại vì undo tablespace hết chỗ. Điều này có thể giúp các truy vấn dài hoặc Flashback hoạt động ổn định hơn, nhưng tạo rủi ro cho khả năng ghi.

Nếu không bật retention guarantee, Oracle có thể tái sử dụng undo chưa hết hạn khi thiếu không gian, làm một số truy vấn dài gặp `ORA-01555`. Vì vậy, hãy xem retention guarantee là quyết định đánh đổi giữa khả năng giữ lịch sử undo và khả năng tiếp tục ghi, không phải một tùy chọn nên bật mặc định.

## 13. So sánh READ COMMITTED, SERIALIZABLE và READ ONLY trong tình huống thực tế

Giả sử một quản lý cần tính số thành viên đang hoạt động của dự án và có thể đồng thời vô hiệu hóa một thành viên.

### READ COMMITTED

Mỗi câu lệnh đọc có snapshot riêng. Nếu transaction chạy `COUNT(*)`, rồi transaction khác thêm/xóa thành viên và commit, câu truy vấn tiếp theo của transaction đầu có thể thấy số lượng mới. Điều này phù hợp với các thao tác ngắn, nhưng logic kiểm tra nhiều câu lệnh cần cơ chế bảo vệ bổ sung nếu có bất biến tổng hợp.

### SERIALIZABLE

Các câu truy vấn trong transaction dùng cùng snapshot. Nếu transaction cố sửa một hàng đã bị transaction khác sửa sau thời điểm transaction bắt đầu, Oracle có thể báo `ORA-08177`. Ứng dụng cần rollback và retry theo quy tắc.

Với bất biến trải trên nhiều hàng, cần đánh giá liệu các giao dịch có thể đọc cùng snapshot nhưng ghi vào các hàng khác nhau hay không. Có thể dùng hàng cha làm guard và yêu cầu mọi thao tác thay đổi tập con khóa hàng đó trước khi kiểm tra.

### READ ONLY

Phù hợp khi chỉ cần đọc nhiều bảng và nhiều truy vấn nhất quán theo cùng snapshot. Không dùng cho transaction phải cập nhật dữ liệu.

## 14. Khi nào nên dùng SELECT FOR UPDATE hoặc khóa tường minh?

Oracle không khóa các hàng chỉ vì một câu SELECT thường đọc chúng. Nếu logic nghiệp vụ cần ngăn transaction khác thay đổi một hàng cụ thể trong lúc ứng dụng kiểm tra và cập nhật, có thể dùng:

```sql
SELECT status
FROM projects
WHERE project_id = 7
FOR UPDATE;
```

Đặt câu lệnh này trong cùng transaction với bước kiểm tra và cập nhật. Khóa được giữ đến `COMMIT` hoặc `ROLLBACK`.

Nếu bất biến liên quan đến nhiều hàng con, có thể khóa một hàng cha đại diện trước khi đọc tập con. Tất cả thao tác thêm, xóa hoặc chuyển con ảnh hưởng đến cùng bất biến phải lấy khóa guard theo cùng giao thức. Nếu một luồng ghi bỏ qua khóa này, quy tắc vẫn có thể bị phá vỡ.

Khóa tường minh làm tăng tranh chấp và có thể tạo deadlock. Hãy khóa phạm vi cần thiết, lấy nhiều khóa theo thứ tự ổn định, giữ transaction ngắn và xử lý deadlock/timeout phù hợp.

## 15. Các lỗi triển khai thường gặp

| Hiểu nhầm hoặc lỗi | Hậu quả | Cách hiểu/khắc phục |
|---|---|---|
| Cho rằng hai SELECT trong cùng transaction luôn thấy cùng dữ liệu | Ở READ COMMITTED, mỗi câu có snapshot riêng | Dùng SERIALIZABLE/READ ONLY hoặc cơ chế khóa phù hợp khi cần snapshot theo transaction |
| Cho rằng SELECT thường khóa hàng | Reader không lấy row lock chỉ vì đọc | Dùng `SELECT FOR UPDATE` khi cần khóa hàng để cập nhật |
| Cho rằng writer sẽ chặn mọi reader | Reader thường dùng undo để đọc phiên bản nhất quán | Phân biệt row lock của writer với consistent read |
| Chỉ tăng UNDO_RETENTION là giải quyết hết ORA-01555 | Không gian undo vẫn có thể không đủ | Kiểm tra kích thước, tốc độ phát sinh undo, thời gian query và retention guarantee |
| Bật RETENTION GUARANTEE mà không xem dung lượng | DML có thể thất bại khi undo tablespace đầy | Đánh giá tác động lên workload ghi trước khi bật |
| Retry riêng câu UPDATE sau ORA-08177 | Quyết định trước đó có thể dựa trên snapshot cũ | Rollback và chạy lại toàn bộ logic transaction |
| Cho rằng snapshot ổn định tự khóa mọi hàng đã đọc | Giao dịch khác vẫn có thể ghi; bất biến nhiều hàng cần cơ chế bảo vệ phù hợp | Dùng guard row, constraint hoặc giao thức khóa tường minh |

## 16. Tự kiểm tra

**Tình huống 1:** Trong `READ COMMITTED`, T1 chạy hai câu `SELECT` trên cùng một hàng. T2 cập nhật và commit giữa hai câu. T1 có thể thấy hai giá trị khác nhau không?

**Đáp án:** Có. Mỗi câu SELECT có snapshot tại thời điểm câu lệnh bắt đầu. Câu thứ hai có thể thấy thay đổi đã commit của T2.

**Tình huống 2:** Một truy vấn đang chạy và T2 cập nhật cùng hàng rồi commit. Vì sao truy vấn không đọc lẫn giá trị cũ và mới?

**Đáp án:** Oracle giữ snapshot của câu truy vấn và dùng undo để dựng phiên bản block phù hợp với SCN snapshot. Vì vậy, truy vấn nhận một kết quả nhất quán theo thời điểm bắt đầu.

**Tình huống 3:** Khi nào nên dùng `SET TRANSACTION READ ONLY`?

**Đáp án:** Khi một báo cáo cần chạy nhiều câu truy vấn trên cùng snapshot và không cần thay đổi dữ liệu. Các transaction khác vẫn có thể ghi trong khi báo cáo đọc dữ liệu nhất quán.

**Tình huống 4:** Một transaction `SERIALIZABLE` gặp `ORA-08177` khi cập nhật hàng vừa bị transaction khác sửa và commit sau khi nó bắt đầu. Ứng dụng nên làm gì?

**Đáp án:** Xử lý lỗi, rollback transaction theo trạng thái DBMS và chạy lại toàn bộ thao tác trong transaction mới để có snapshot mới. Không chỉ chạy lại câu UPDATE cuối.

**Tình huống 5:** Một báo cáo dài gặp `ORA-01555`. Điều đó nói gì về undo?

**Đáp án:** Oracle không còn undo records cần thiết để dựng phiên bản dữ liệu theo snapshot của truy vấn. Cần xem thời gian chạy query, tốc độ phát sinh undo, dung lượng undo tablespace và retention.

**Tình huống 6:** `UNDO_RETENTION` được đặt một giờ. Có thể chắc chắn mọi undo luôn được giữ đủ một giờ không?

**Đáp án:** Không thể kết luận như vậy nếu chưa xem cấu hình và dung lượng. Oracle cố gắng đáp ứng retention, nhưng khả năng thực tế phụ thuộc undo tablespace và workload. Retention guarantee có thể bảo vệ undo chưa hết hạn, nhưng nếu thiếu không gian thì DML có thể thất bại.

**Tình huống 7:** Một quy tắc nghiệp vụ yêu cầu ít nhất một nhân viên trong nhóm còn hoạt động. Hai transaction đọc cùng snapshot rồi cập nhật hai hàng nhân viên khác nhau. Có nên giả định chỉ cần SERIALIZABLE là mọi kiểu bất biến nhiều hàng tự được bảo vệ không?

**Đáp án:** Không nên giả định. Oracle cung cấp transaction-level snapshot và phát hiện xung đột khi transaction cố sửa hàng đã bị transaction khác thay đổi sau thời điểm bắt đầu. Với bất biến phụ thuộc nhiều hàng khác nhau, cần thiết kế điểm ghi/khóa chung hoặc constraint phù hợp để các giao dịch tranh chấp trên cùng tài nguyên.

Khi làm việc với Oracle, hãy xác định câu hỏi đọc cần nhất quán trong phạm vi một câu lệnh hay toàn transaction. Hiểu cách undo tái tạo phiên bản cũ, theo dõi retention để tránh `ORA-01555`, xử lý `ORA-08177` bằng transaction mới và dùng khóa tường minh khi nghiệp vụ cần điều phối các thao tác ghi. MVCC giúp reader và writer hoạt động đồng thời; tính đúng đắn của quy tắc nghiệp vụ vẫn cần được thiết kế rõ ràng.

## Tài liệu Oracle tham khảo

- [Data Concurrency and Consistency — Oracle Database 26ai](https://docs.oracle.com/en/database/oracle/oracle-database/26/cncpt/data-concurrency-and-consistency.html)
- [Managing Undo — Oracle Database 26ai](https://docs.oracle.com/en/database/oracle/oracle-database/26/admin/managing-undo.html)
- [SET TRANSACTION — Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/SET-TRANSACTION.html)
- [ORA-01555 — Snapshot too old](https://docs.oracle.com/en/error-help/db/ora-01555/)
