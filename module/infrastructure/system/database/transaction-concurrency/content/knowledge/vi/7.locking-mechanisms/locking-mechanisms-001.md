# Khóa chia sẻ và khóa độc quyền

Trong cơ sở dữ liệu quan hệ, nhiều giao dịch có thể đọc và ghi cùng một hàng dữ liệu trong cùng khoảng thời gian. Nếu các thao tác này không được điều phối, một giao dịch có thể đọc dữ liệu đang được giao dịch khác sửa dở, hai giao dịch có thể ghi đè kết quả của nhau, hoặc một giao dịch có thể cập nhật dựa trên giá trị đã thay đổi. Cơ chế khóa (locking) giúp hệ quản trị cơ sở dữ liệu điều phối những truy cập đồng thời đó.

Hai chế độ khóa cơ bản là **khóa chia sẻ** (*Shared Lock*, ký hiệu `S`) và **khóa độc quyền** (*Exclusive Lock*, ký hiệu `X`). Khóa chia sẻ cho phép nhiều giao dịch cùng đọc một tài nguyên trong khi ngăn giao dịch khác sửa tài nguyên đó theo cơ chế khóa tương ứng. Khóa độc quyền dành quyền truy cập ghi cho một giao dịch và xung đột với cả khóa chia sẻ lẫn khóa độc quyền khác trên cùng tài nguyên.

## 1. Tài nguyên được khóa là gì?

Hệ quản trị cơ sở dữ liệu không nhất thiết khóa toàn bộ bảng mỗi khi một câu lệnh đọc hoặc cập nhật dữ liệu. Tùy hệ quản trị, kế hoạch thực thi và mức cô lập, tài nguyên khóa có thể là:

- **Hàng (row/record):** một bản ghi cụ thể. Khóa hàng giúp các giao dịch vẫn có thể làm việc với những hàng khác trong cùng bảng.
- **Trang (page):** một vùng lưu trữ chứa nhiều hàng. Khóa trang có phạm vi rộng hơn khóa hàng.
- **Bảng (table):** toàn bộ bảng. Khóa bảng có thể ảnh hưởng đến nhiều giao dịch đang truy cập các hàng khác nhau trong bảng đó.
- **Khóa hoặc phạm vi khóa (key/range):** một khóa chỉ mục hoặc một khoảng giá trị. Một số hệ quản trị dùng loại khóa này để bảo vệ điều kiện truy vấn, chẳng hạn khi cần ngăn giao dịch khác chèn hàng mới vào khoảng đang được kiểm tra.

`S` và `X` mô tả **chế độ** khóa; row, page, table và range mô tả **phạm vi hoặc loại tài nguyên** bị khóa. Vì vậy, có thể có khóa chia sẻ trên một hàng, khóa độc quyền trên một hàng, hoặc khóa ở cấp bảng với chế độ tương ứng. Không nên đồng nhất khóa độc quyền với việc khóa toàn bộ cơ sở dữ liệu.

## 2. Khóa chia sẻ (Shared Lock - S)

Khóa chia sẻ được dùng để bảo vệ tài nguyên trong lúc một giao dịch đọc dữ liệu theo mô hình khóa. Nhiều giao dịch có thể đồng thời giữ `S` trên cùng một tài nguyên vì các giao dịch đó không làm thay đổi dữ liệu đang đọc.

Giả sử hai giao dịch cùng đọc hàng tài khoản có `id = 10`:

1. Giao dịch T1 yêu cầu khóa `S` trên hàng tài khoản 10.
2. Giao dịch T2 cũng yêu cầu khóa `S` trên chính hàng đó.
3. Hệ quản trị có thể cấp cả hai khóa vì `S` tương thích với `S`.
4. Một giao dịch muốn cập nhật hàng này cần khóa có chế độ `X`; yêu cầu đó phải chờ cho đến khi các khóa `S` đang xung đột được giải phóng.

Do đó, khóa chia sẻ cho phép **nhiều người đọc cùng lúc**, đồng thời bảo vệ dữ liệu khỏi những thao tác ghi cần một khóa xung đột trong thời gian khóa còn hiệu lực.

Khóa `S` không biến giao dịch thành giao dịch chỉ đọc. Một giao dịch đang giữ `S` có thể yêu cầu chuyển sang `X` để cập nhật dữ liệu, nếu hệ quản trị cho phép và không có khóa xung đột cản trở. Việc chuyển chế độ này được gọi là *lock upgrade* hoặc *lock conversion*.

## 3. Khóa độc quyền (Exclusive Lock - X)

Khóa độc quyền được dùng khi một giao dịch cần sửa hoặc xóa tài nguyên. Trên cùng một tài nguyên, `X` không tương thích với `S` hoặc `X` do giao dịch khác nắm giữ.

Ví dụ, T1 cập nhật số dư của tài khoản 10:

1. T1 yêu cầu khóa `X` trên hàng tài khoản 10.
2. Khi được cấp khóa, T1 có thể thực hiện thao tác cập nhật trên hàng đó.
3. Nếu T2 muốn lấy `S` để thực hiện một truy vấn đọc có khóa trên cùng hàng, hoặc muốn lấy `X` để cập nhật hàng đó, yêu cầu của T2 phải chờ.
4. Khi T1 kết thúc giao dịch bằng `COMMIT` hoặc `ROLLBACK`, khóa được giải phóng theo quy tắc của hệ quản trị; yêu cầu đang chờ có thể được xét cấp.

`X` bảo đảm rằng tại một thời điểm chỉ có một chủ sở hữu khóa độc quyền trên cùng tài nguyên. Điều này giúp tránh hai giao dịch cùng sửa một tài nguyên theo cách không được điều phối.

Lưu ý: khóa `X` không nhất thiết khiến mọi câu lệnh `SELECT` thông thường phải chờ. Trong hệ quản trị dùng MVCC (*Multi-Version Concurrency Control*), một truy vấn đọc không yêu cầu khóa có thể đọc phiên bản đã commit trước đó trong khi giao dịch khác đang giữ khóa ghi. Hành vi cụ thể phụ thuộc hệ quản trị, mức cô lập và loại câu lệnh đọc.

## 4. Ma trận tương thích giữa S và X

Ma trận dưới đây xét hai giao dịch khác nhau đang yêu cầu khóa trên **cùng một tài nguyên**. “Đang giữ” là chế độ khóa hiện có; “yêu cầu” là chế độ khóa mới.

| Khóa đang giữ | Yêu cầu S | Yêu cầu X |
|---|---:|---:|
| **S** | Có thể cấp | Phải chờ |
| **X** | Phải chờ | Phải chờ |

Có thể đọc ma trận theo từng trường hợp:

- **S với S — tương thích:** nhiều giao dịch cùng đọc tài nguyên.
- **S với X — không tương thích:** giao dịch đang đọc có khóa bảo vệ; giao dịch muốn ghi phải chờ.
- **X với S — không tương thích:** giao dịch đang ghi độc quyền; giao dịch muốn đọc bằng một khóa `S` phải chờ.
- **X với X — không tương thích:** hai giao dịch không thể đồng thời nắm quyền ghi độc quyền trên cùng tài nguyên.

```text
             Khóa được yêu cầu
             S             X
Đang giữ S   Tương thích   Xung đột
Đang giữ X   Xung đột      Xung đột
```

Ma trận là quy tắc cơ bản cho hai chế độ `S` và `X`, không phải toàn bộ ma trận khóa của mọi hệ quản trị. Một số hệ quản trị còn có các chế độ khác như update lock, intention lock hoặc khóa phạm vi. Ngoài ra, khóa do chính một giao dịch nắm giữ thường không được xem là xung đột với yêu cầu khác của chính giao dịch đó; quy tắc nâng cấp và quản lý khóa nội bộ phụ thuộc cách triển khai.

## 5. Ví dụ: nhiều giao dịch đọc cùng một hàng

Giả sử bảng `account` có hàng `id = 10`. T1 và T2 đều cần đọc hàng đó và muốn giữ dữ liệu ổn định trong lúc xử lý.

```text
Thời điểm     Giao dịch T1                  Giao dịch T2
----------------------------------------------------------------
1             BEGIN
2             Lấy khóa S trên account(10)
3                                           BEGIN
4                                           Lấy khóa S trên account(10)
5             Đọc số dư                     Đọc số dư
6             COMMIT                        COMMIT
```

T2 không phải chờ T1 ở bước lấy khóa `S`, vì hai khóa tương thích. Đây là lợi ích chính của khóa chia sẻ: các giao dịch đọc có thể tiến hành đồng thời mà không tranh quyền ghi trên tài nguyên.

## 6. Ví dụ: giao dịch đọc có khóa và giao dịch ghi

Giả sử T1 cần đọc số dư để tính toán và muốn ngăn giao dịch khác sửa hàng đó trong thời gian xử lý. T1 lấy khóa chia sẻ. T2 muốn cập nhật cùng hàng nên cần khóa độc quyền.

```sql
-- Phiên T1
BEGIN;

SELECT balance
FROM account
WHERE id = 10
FOR SHARE;

-- T1 tiếp tục xử lý dựa trên giá trị vừa đọc.
-- Khóa chia sẻ vẫn còn hiệu lực theo quy tắc của hệ quản trị.
COMMIT;
```

```sql
-- Phiên T2
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE id = 10;

COMMIT;
```

Trong các hệ quản trị hỗ trợ cú pháp `FOR SHARE`, truy vấn của T1 yêu cầu khóa đọc chia sẻ trên hàng được chọn. Câu `UPDATE` của T2 cần quyền ghi tương ứng với khóa độc quyền. Vì `S` và `X` không tương thích, T2 phải chờ T1 giải phóng khóa trước khi tiếp tục trên tài nguyên đó.

Trình tự có thể hình dung như sau:

```text
T1: BEGIN ── lấy S ── đọc/xử lý ── COMMIT, nhả S
T2:             yêu cầu X ── chờ ────────────────── lấy X ── UPDATE
```

Các ví dụ SQL trong bài dùng cú pháp khóa hàng kiểu PostgreSQL/MySQL để minh họa ý định. Cú pháp yêu cầu khóa tường minh khác nhau giữa các hệ quản trị; cần xem tài liệu của hệ đang sử dụng trước khi áp dụng.

## 7. Ví dụ: khóa độc quyền chặn yêu cầu khóa khác

T1 muốn cập nhật một hàng và yêu cầu khóa độc quyền. Trong khi T1 đang giữ `X`, T2 không thể lấy `S` hoặc `X` trên cùng tài nguyên bằng một thao tác đọc/ghi có khóa.

```sql
-- Phiên T1
BEGIN;

SELECT balance
FROM account
WHERE id = 10
FOR UPDATE;

UPDATE account
SET balance = balance + 500
WHERE id = 10;

-- Giả sử T1 chưa COMMIT, khóa X vẫn đang được giữ.
```

```sql
-- Phiên T2
BEGIN;

SELECT balance
FROM account
WHERE id = 10
FOR SHARE;

-- Yêu cầu khóa S phải chờ khóa X của T1 được giải phóng.
```

Khi T1 `COMMIT` hoặc `ROLLBACK`, T2 có thể tiếp tục tùy theo trạng thái giao dịch và quy tắc của hệ quản trị. Nếu T2 dùng một truy vấn đọc MVCC không yêu cầu khóa, kết quả có thể khác: truy vấn có thể đọc phiên bản đã commit gần nhất thay vì chờ khóa `X`. Vì vậy, cần phân biệt **đọc có khóa** với **đọc theo snapshot/phiên bản**.

## 8. Vòng đời khóa và chuyển đổi chế độ

### Cấp và giải phóng khóa

Khi một thao tác cần truy cập tài nguyên, giao dịch gửi yêu cầu đến bộ quản lý khóa (*lock manager*). Nếu chế độ khóa tương thích với những khóa đang tồn tại, hệ quản trị cấp khóa. Nếu có xung đột, yêu cầu thường được đưa vào hàng đợi chờ. Khi khóa xung đột được giải phóng, hệ quản trị xét các yêu cầu đang chờ theo chính sách lập lịch của nó.

Thời điểm giải phóng khóa phụ thuộc loại khóa, mức cô lập và hệ quản trị. Trong các giao thức khóa hai pha (*Two-Phase Locking - 2PL*), giao dịch có giai đoạn tăng trưởng để lấy khóa và giai đoạn thu hẹp để giải phóng khóa; sau khi bắt đầu giải phóng khóa, giao dịch không được lấy thêm khóa mới. Với **strict 2PL**, các khóa độc quyền được giữ đến khi giao dịch commit hoặc rollback. **Rigorous 2PL** giữ cả khóa chia sẻ và khóa độc quyền đến cuối giao dịch. Các hệ quản trị có thể áp dụng biến thể hoặc cơ chế khác, vì vậy không nên mặc định mọi khóa `S` đều tồn tại đến cuối giao dịch.

### Nâng cấp và hạ cấp khóa

Một giao dịch có thể bắt đầu bằng việc đọc với `S`, sau đó nhận ra cần cập nhật và yêu cầu chuyển sang `X`. Đây là nâng cấp khóa (`S → X`). Hệ quản trị chỉ có thể hoàn tất nâng cấp khi không còn khóa xung đột từ giao dịch khác.

Ví dụ về tình huống có thể gây deadlock:

1. T1 lấy `S` trên hàng A.
2. T2 cũng lấy `S` trên hàng A.
3. T1 yêu cầu nâng cấp lên `X`, nhưng phải chờ T2 nhả `S`.
4. T2 cũng yêu cầu nâng cấp lên `X`, nhưng phải chờ T1 nhả `S`.

Hai giao dịch đều đang chờ nhau nên không thể tự tiếp tục. Hệ quản trị có thể phát hiện deadlock và hủy một giao dịch làm nạn nhân để giải phóng chu trình chờ. Ứng dụng cần sẵn sàng chạy lại toàn bộ giao dịch bị hủy khi lỗi deadlock có thể thử lại.

Hạ cấp (`X → S`) là chuyển từ quyền độc quyền sang quyền đọc chia sẻ khi giao dịch không còn cần sửa tài nguyên. Việc hạ cấp có thể cho phép giao dịch khác đọc sớm hơn, nhưng thời điểm và khả năng thực hiện tùy hệ quản trị.

Một số hệ quản trị cung cấp chế độ trung gian như **update lock (`U`)** để xử lý tình huống đọc trước rồi cập nhật sau. Chế độ này có quy tắc tương thích riêng và không nằm trong ma trận S/X cơ bản. Khi dùng, cần hiểu rõ hành vi của hệ quản trị cụ thể.

## 9. Phạm vi khóa, khóa ý định và leo thang khóa

Khóa `S` hoặc `X` trên một hàng không nhất thiết ngăn giao dịch khác truy cập hàng khác. Đây là lý do khóa hàng thường cho phép mức đồng thời cao hơn khóa bảng. Tuy nhiên, khóa ở phạm vi nhỏ cần nhiều mục khóa hơn và tốn tài nguyên quản lý hơn.

Để phối hợp khóa ở nhiều cấp, một số hệ quản trị dùng **khóa ý định** (*intention lock*). Chẳng hạn, trước khi đặt khóa `X` trên một hàng, giao dịch có thể đặt khóa ý định ở cấp bảng để thông báo rằng bên dưới bảng đang có yêu cầu khóa ghi. Khóa ý định giúp hệ quản trị kiểm tra xung đột giữa khóa cấp bảng và khóa cấp hàng mà không phải quét mọi hàng.

Khi một giao dịch giữ quá nhiều khóa nhỏ, hệ quản trị có thể **leo thang khóa** (*lock escalation*), chuyển nhiều khóa cấp hàng hoặc trang thành một khóa phạm vi lớn hơn, chẳng hạn khóa bảng. Việc này giảm số mục khóa cần quản lý nhưng có thể làm giảm khả năng đồng thời của các giao dịch khác. Ngưỡng và chính sách leo thang khác nhau theo sản phẩm cơ sở dữ liệu.

Với truy vấn theo khoảng, khóa từng hàng hiện có có thể chưa đủ để bảo vệ điều kiện truy vấn khỏi một giao dịch khác chèn thêm hàng phù hợp. Một số hệ quản trị dùng khóa phạm vi khóa (*key-range lock*) hoặc cơ chế kiểm soát tuần tự hóa khác để bảo vệ cả khoảng giá trị. Đây là lý do phạm vi khóa cần được xem xét cùng với mức cô lập và loại truy vấn.

## 10. Quan hệ với MVCC và mức cô lập giao dịch

Khóa chia sẻ và khóa độc quyền là các chế độ khóa phổ biến trong điều phối truy cập đồng thời, nhưng không phải mọi lần đọc đều phải lấy khóa `S`.

Trong hệ quản trị dùng MVCC, mỗi lần cập nhật có thể tạo phiên bản mới của hàng. Một truy vấn đọc thông thường thường đọc phiên bản phù hợp với snapshot của nó, nên có thể tiếp tục trong khi giao dịch khác đang giữ khóa ghi. Giao dịch ghi vẫn cần cơ chế khóa hoặc kiểm tra xung đột để bảo vệ việc cập nhật. Một câu lệnh đọc có yêu cầu khóa tường minh, ví dụ `SELECT ... FOR SHARE`, có thể chờ khóa ghi đang tồn tại.

Ở mức cô lập `READ COMMITTED`, một số hệ quản trị khóa chia sẻ chỉ trong thời gian thực thi câu lệnh; ở mức cao hơn, hệ quản trị có thể giữ khóa lâu hơn hoặc dùng MVCC, khóa phạm vi hay kiểm tra xung đột tuần tự hóa. Do đó, không thể chỉ nhìn tên `S` hoặc `X` để kết luận chính xác thời gian khóa tồn tại hay câu lệnh nào sẽ bị chặn. Cần kết hợp ba yếu tố: **hệ quản trị**, **mức cô lập**, và **loại thao tác đọc/ghi**.

## 11. Giảm chờ khóa và deadlock trong ứng dụng

Khóa là cơ chế cần thiết nhưng việc giữ khóa lâu hoặc yêu cầu khóa theo thứ tự khác nhau có thể làm giảm thông lượng. Một số thực hành giúp hạn chế vấn đề:

- Giữ giao dịch ngắn: hoàn tất công việc cơ sở dữ liệu và commit sớm; tránh chờ người dùng, gọi dịch vụ bên ngoài hoặc xử lý lâu trong khi đang giữ khóa.
- Truy cập nhiều hàng theo một thứ tự nhất quán trong các giao dịch khác nhau. Điều này làm giảm khả năng tạo chu trình chờ.
- Dùng điều kiện `WHERE` và chỉ mục phù hợp để giới hạn số hàng phải kiểm tra hoặc khóa.
- Chỉ yêu cầu khóa tường minh khi nghiệp vụ thực sự cần bảo vệ dữ liệu trong lúc đọc. Đọc snapshot có thể phù hợp hơn nếu không cần chặn giao dịch ghi.
- Xử lý lỗi deadlock và lỗi xung đột có thể thử lại bằng cách chạy lại toàn bộ giao dịch với giới hạn số lần và khoảng chờ phù hợp.
- Theo dõi thời gian chờ khóa, giao dịch giữ khóa lâu và truy vấn gây tranh chấp để tìm nguyên nhân ở cấp ứng dụng hoặc cơ sở dữ liệu.

Không nên giải quyết mọi tình huống bằng cách tăng phạm vi khóa. Khóa bảng có thể đơn giản hóa việc bảo vệ dữ liệu nhưng cũng khiến nhiều giao dịch không liên quan phải chờ nhau. Hãy chọn phạm vi và chế độ khóa phù hợp với bất biến dữ liệu mà nghiệp vụ cần bảo vệ.

## 12. Những điểm cần nhớ khi đọc hoặc thiết kế giao dịch

- `S` cho phép nhiều giao dịch cùng giữ khóa đọc trên một tài nguyên; `S` xung đột với `X`.
- `X` dành quyền ghi độc quyền trên tài nguyên; nó xung đột với cả `S` và `X` của giao dịch khác.
- Ma trận tương thích chỉ có ý nghĩa khi xét cùng tài nguyên và cùng phạm vi khóa; khóa ở cấp hàng và cấp bảng có thể tương tác qua các chế độ khóa ý định.
- Một câu `SELECT` thông thường không phải lúc nào cũng lấy khóa `S`; MVCC có thể cho phép đọc snapshot trong khi giao dịch khác đang ghi.
- Thời gian giữ khóa phụ thuộc giao thức, mức cô lập, loại câu lệnh và hệ quản trị.
- Nâng cấp `S` lên `X` có thể tạo deadlock nếu nhiều giao dịch cùng giữ `S` rồi đồng thời muốn ghi.

Khi phân tích một tình huống tranh chấp, hãy xác định giao dịch nào đang giữ khóa gì, trên tài nguyên nào, giao dịch còn lại đang yêu cầu chế độ gì, và điều kiện nào sẽ giải phóng khóa. Bốn thông tin đó thường đủ để giải thích vì sao một thao tác được thực hiện ngay, phải chờ, hoặc bị chọn làm nạn nhân của deadlock.
