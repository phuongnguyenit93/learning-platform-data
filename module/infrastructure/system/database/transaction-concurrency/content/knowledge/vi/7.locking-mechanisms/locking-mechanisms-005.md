# Chuyển đổi khóa và nguy cơ bế tắc khi nâng cấp

Khi một giao dịch đọc dữ liệu rồi quyết định sửa chính dữ liệu đó, hệ quản trị cơ sở dữ liệu có thể phải **nâng cấp khóa** đang giữ từ chế độ đọc sang chế độ ghi. Thao tác này gọi là *lock conversion* (chuyển đổi khóa). Nếu nhiều giao dịch cùng giữ khóa đọc trên một tài nguyên rồi đồng thời yêu cầu khóa ghi, mỗi giao dịch có thể chờ giao dịch còn lại nhả khóa. Khi các quan hệ chờ tạo thành một vòng khép kín, hệ thống gặp **deadlock do nâng cấp khóa**.

Hiểu cơ chế này giúp ta nhận ra vì sao một câu lệnh UPDATE đôi khi bị treo dù giao dịch đã đọc được hàng dữ liệu, và biết cách tổ chức thao tác đọc–sửa để giảm tranh chấp.

## 1. Chuyển đổi khóa là gì?

Khóa (*lock*) bảo vệ một tài nguyên mà giao dịch đang truy cập. Tài nguyên có thể là một hàng, một trang dữ liệu, một bảng hoặc một phạm vi khóa trên chỉ mục. Tùy hệ quản trị và kế hoạch thực thi, hệ thống có thể đặt khóa ở một hoặc nhiều mức.

Hai chế độ cơ bản thường gặp là:

- **Shared lock (S):** khóa chia sẻ, thường được dùng để đọc theo cơ chế khóa. Nhiều giao dịch có thể cùng giữ S trên một tài nguyên vì chúng không sửa tài nguyên đó.
- **Exclusive lock (X):** khóa độc quyền, cần thiết khi sửa dữ liệu. Một X thường ngăn giao dịch khác lấy S hoặc X xung đột trên cùng tài nguyên.

Nếu một giao dịch đang giữ S trên hàng Account(10) rồi thực hiện UPDATE hàng đó, hệ thống cần bảo đảm giao dịch có quyền ghi. Nó yêu cầu chuyển S thành X. Đây là chuyển đổi khóa từ S sang X, thường được gọi là *lock upgrade*.

Chuyển đổi khóa khác với việc lấy một khóa mới trên tài nguyên khác:

- **Chuyển đổi khóa:** thay đổi chế độ khóa trên cùng tài nguyên, ví dụ S → X.
- **Lấy thêm khóa:** giao dịch giữ khóa trên tài nguyên A rồi yêu cầu khóa trên tài nguyên B.
- **Lock escalation:** hệ thống thay nhiều khóa ở mức nhỏ, chẳng hạn hàng hoặc trang, bằng một khóa ở mức lớn hơn như bảng. Đây là thay đổi phạm vi khóa, không phải việc nâng S thành X trên cùng một hàng.

Khi yêu cầu chuyển đổi chưa thể được cấp, hệ thống thường giữ khóa hiện tại và đưa yêu cầu mới vào trạng thái chờ. Việc giữ khóa cũ giúp bảo toàn các bảo đảm cô lập của giao dịch. Nếu tự ý nhả S trước khi lấy được X, một giao dịch khác có thể sửa dữ liệu trong khoảng trống đó và làm sai kết quả của thao tác đọc–sửa. Quy tắc xếp hàng và xử lý yêu cầu chuyển đổi cụ thể tùy hệ quản trị.

## 2. Khả năng tương thích giữa khóa đọc và khóa ghi

Với mô hình S/X cơ bản, các yêu cầu trên cùng một tài nguyên có quan hệ như sau:

| Khóa đang được giữ | Yêu cầu S mới | Yêu cầu X mới |
|---|---:|---:|
| S | Được cấp | Phải chờ |
| X | Phải chờ | Phải chờ |

Nhiều giao dịch có thể cùng đọc bằng S. Nhưng nếu một giao dịch đang giữ S yêu cầu X, nó phải chờ mọi khóa đang giữ mà không tương thích được giải phóng.

Ví dụ, T1 đang giữ S và yêu cầu X. Nếu T2 chỉ đang giữ S, hai khóa S vẫn tương thích với nhau, nhưng X mà T1 cần lại xung đột với S của T2. Vì vậy T1 phải chờ T2 kết thúc hoặc nhả khóa. Nếu T2 cũng yêu cầu X trong lúc vẫn giữ S, T2 sẽ chờ T1. Từ đó có thể hình thành deadlock.

Bảng trên chỉ mô tả nguyên tắc S/X đơn giản. Hệ quản trị thực tế còn có thể dùng khóa ý định, khóa cập nhật, khóa phạm vi và các quy tắc tương thích khác.

## 3. Deadlock kinh điển khi hai giao dịch cùng nâng S lên X

Giả sử hai giao dịch cùng đọc một tài khoản bằng một thao tác đọc có khóa chia sẻ. Sau khi kiểm tra số dư, cả hai đều muốn cập nhật hàng đó.

Ví dụ giả lập dưới đây dùng cú pháp FOR SHARE để biểu diễn một lần đọc có khóa. Cú pháp và thời điểm khóa được giữ có thể khác giữa các hệ quản trị; điều kiện quan trọng của ví dụ là cả hai giao dịch đều giữ S trên cùng hàng cho đến khi giao dịch kết thúc.

**Giao dịch T1:**

~~~sql
BEGIN;

SELECT balance
FROM account
WHERE account_id = 10
FOR SHARE;

-- T1 kiểm tra dữ liệu rồi quyết định cập nhật.
UPDATE account
SET balance = balance + 100
WHERE account_id = 10;

COMMIT;
~~~

**Giao dịch T2 chạy đồng thời:**

~~~sql
BEGIN;

SELECT balance
FROM account
WHERE account_id = 10
FOR SHARE;

-- T2 cũng kiểm tra dữ liệu rồi quyết định cập nhật.
UPDATE account
SET balance = balance - 50
WHERE account_id = 10;

COMMIT;
~~~

Diễn biến có thể xảy ra theo thứ tự sau:

| Bước | Giao dịch T1 | Giao dịch T2 | Trạng thái khóa trên hàng 10 |
|---|---|---|---|
| 1 | Đọc có khóa, nhận S | | T1 giữ S |
| 2 | | Đọc có khóa, nhận S | T1 và T2 cùng giữ S |
| 3 | Yêu cầu nâng S → X, phải chờ T2 | | T1 chờ T2 nhả S |
| 4 | | Yêu cầu nâng S → X, phải chờ T1 | T2 chờ T1 nhả S |

Lúc này:

- T1 chỉ có thể lấy X khi T2 nhả S.
- T2 chỉ có thể lấy X khi T1 nhả S.
- Cả hai đều đang chờ giao dịch còn lại hoàn tất.

Không giao dịch nào có thể tự tiến tới COMMIT để giải phóng khóa. Đây là một vòng chờ khép kín.

Có thể biểu diễn đồ thị chờ (*wait-for graph*) như sau:

~~~mermaid
flowchart LR
    T1["T1: giữ S, chờ X"] -->|"chờ T2 nhả S"| T2["T2: giữ S, chờ X"]
    T2 -->|"chờ T1 nhả S"| T1
~~~

Khi phát hiện deadlock, hệ quản trị thường chọn một giao dịch làm nạn nhân (*deadlock victim*) và hủy hoặc rollback giao dịch đó để giải phóng khóa. Giao dịch còn lại có thể tiếp tục. Tiêu chí chọn nạn nhân và phạm vi rollback phụ thuộc hệ quản trị.

**Không phải mọi lần nâng S lên X đều gây deadlock.** Nếu chỉ một giao dịch giữ S, hoặc các giao dịch khác đã nhả khóa trước khi yêu cầu X được xử lý, việc chuyển đổi chỉ phải chờ rồi được cấp. Deadlock xuất hiện khi có một chu trình chờ, không chỉ vì một giao dịch phải đợi khóa.

## 4. Vì sao thao tác đọc rồi ghi dễ tạo ra deadlock?

Mẫu thao tác có rủi ro thường gồm ba điều kiện:

1. Nhiều giao dịch cùng đọc một tài nguyên bằng khóa có thể được giữ lâu.
2. Mỗi giao dịch giữ khóa đọc trong khi yêu cầu khóa ghi trên cùng tài nguyên.
3. Các yêu cầu ghi xung đột và mỗi giao dịch lại cần giao dịch kia nhả khóa trước khi tiếp tục.

Thời gian giữ khóa càng dài thì cơ hội các giao dịch chồng lấn càng cao. Một giao dịch đọc dữ liệu, gọi dịch vụ bên ngoài, chờ người dùng xác nhận rồi mới cập nhật có thể giữ khóa lâu hơn cần thiết nếu toàn bộ công việc nằm trong cùng một transaction.

Deadlock cũng có thể xảy ra khi các giao dịch khóa nhiều tài nguyên theo thứ tự khác nhau. Ví dụ:

- T1 khóa tài khoản 10 rồi yêu cầu khóa tài khoản 20.
- T2 khóa tài khoản 20 rồi yêu cầu khóa tài khoản 10.

Đây là deadlock do thứ tự lấy khóa, dù không nhất thiết có chuyển đổi S → X. Trong hệ thống thật, một chu trình chờ có thể kết hợp cả yêu cầu chuyển đổi khóa và yêu cầu lấy khóa mới.

## 5. Cần phân biệt cách các hệ quản trị tạo khóa

Không nên giả định rằng mọi câu lệnh SELECT đều tạo khóa S và giữ khóa đó đến COMMIT. Nhiều hệ quản trị dùng MVCC (*Multi-Version Concurrency Control*) để cho phép thao tác đọc thông thường lấy một phiên bản dữ liệu mà không cần khóa chia sẻ trên hàng.

| Hệ quản trị | Đọc thông thường | Đọc có khóa và điểm cần chú ý |
|---|---|---|
| PostgreSQL | SELECT thông thường đọc phiên bản phù hợp theo MVCC và không đặt khóa chia sẻ trên hàng theo cách của ví dụ S → X. | SELECT ... FOR SHARE và SELECT ... FOR UPDATE đặt khóa hàng. Các thao tác cập nhật có thể phải chờ khóa hàng xung đột. |
| MySQL InnoDB | Consistent read thông thường thường đọc từ read view của MVCC mà không khóa hàng. | SELECT ... FOR SHARE và SELECT ... FOR UPDATE là locking read. Tùy isolation level và chỉ mục, khóa phạm vi hoặc next-key lock cũng có thể xuất hiện. |
| SQL Server | Với locking READ COMMITTED, khóa S thường được nhả khi câu lệnh đọc kết thúc; REPEATABLE READ và SERIALIZABLE giữ khóa đọc lâu hơn. Khi bật READ_COMMITTED_SNAPSHOT, thao tác đọc dùng row version. | UPDLOCK yêu cầu update lock (U) cho thao tác đọc dự định cập nhật. Khóa U có quy tắc tương thích riêng. |

Do đó, khi phân tích deadlock, hãy xác định hệ quản trị, isolation level, chế độ MVCC hoặc locking, câu lệnh có dùng locking hint hay không, và báo cáo deadlock thực tế. Ví dụ FOR SHARE ở trên minh họa một lịch thực thi có khóa chia sẻ; nó không có nghĩa mọi câu SELECT trên mọi hệ quản trị đều tạo ra lịch khóa đó.

## 6. Update lock: cách giảm deadlock nâng cấp trong SQL Server

SQL Server có chế độ **Update lock (U)**. Đây là khóa dành cho tình huống giao dịch đọc dữ liệu với ý định có thể cập nhật sau đó.

Một số đặc điểm quan trọng:

- U tương thích với S, nên giao dịch đọc thông thường vẫn có thể cùng giữ S.
- U không tương thích với U khác trên cùng tài nguyên; nhờ đó chỉ một giao dịch có thể giữ U tại một thời điểm.
- U không tương thích với X.
- Khi giao dịch thực hiện cập nhật, U có thể được chuyển thành X nếu không còn khóa xung đột.

Nếu hai giao dịch đều dùng U ngay từ lần đọc có ý định cập nhật, giao dịch thứ hai phải chờ lấy U thay vì cả hai cùng giữ S rồi đồng thời yêu cầu X. Cách này giúp tránh mẫu deadlock nâng cấp S → X phổ biến.

Ví dụ SQL Server:

~~~sql
BEGIN TRANSACTION;

SELECT Balance
FROM dbo.Account WITH (UPDLOCK)
WHERE AccountId = 10;

UPDATE dbo.Account
SET Balance = Balance + 100
WHERE AccountId = 10;

COMMIT TRANSACTION;
~~~

UPDLOCK là cú pháp riêng của SQL Server. Nó báo cho hệ quản trị rằng giao dịch dự định cập nhật dữ liệu đã đọc. Không nên áp dụng tùy tiện cho mọi truy vấn đọc vì khóa U có thể làm giảm khả năng chạy đồng thời.

PostgreSQL và MySQL InnoDB có SELECT ... FOR UPDATE để yêu cầu khóa phục vụ cập nhật ngay ở bước đọc. Mục tiêu tương tự là lấy khóa đủ mạnh từ đầu, nhưng cơ chế khóa bên trong không hoàn toàn giống U lock của SQL Server.

Dùng khóa cập nhật sớm không loại bỏ mọi deadlock. Giao dịch vẫn có thể deadlock khi truy cập nhiều hàng theo thứ tự khác nhau, giữ khóa quá lâu hoặc tranh chấp với một loại khóa khác.

## 7. Cách hạn chế deadlock do nâng cấp khóa

### 7.1. Chọn chế độ khóa ngay từ đầu nếu biết sẽ cập nhật

Nếu giao dịch chắc chắn sẽ sửa hàng vừa đọc, hãy cân nhắc dùng thao tác đọc có khóa cập nhật như SELECT ... FOR UPDATE trên PostgreSQL/MySQL InnoDB, hoặc UPDLOCK trên SQL Server.

Cách này giúp các giao dịch tranh quyền ghi sớm hơn, trước khi chúng cùng giữ khóa đọc rồi mới nâng cấp. Đổi lại, các giao dịch khác có thể phải chờ lâu hơn. Chỉ khóa những hàng thật sự cần cập nhật.

### 7.2. Gộp đọc và kiểm tra vào một câu lệnh ghi có điều kiện

Nếu mục tiêu là kiểm tra điều kiện rồi cập nhật một hàng, một câu UPDATE có điều kiện thường đơn giản hơn quy trình đọc trước, quyết định ở ứng dụng rồi mới ghi.

Ví dụ trừ số lượng tồn kho nhưng không cho phép tồn kho âm:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :product_id
  AND available >= :quantity;
~~~

Sau câu lệnh, ứng dụng kiểm tra số hàng bị ảnh hưởng:

- Một hàng được cập nhật: điều kiện hợp lệ và thao tác thành công.
- Không có hàng nào được cập nhật: sản phẩm không tồn tại hoặc số lượng còn lại không đáp ứng điều kiện; ứng dụng xử lý theo quy tắc nghiệp vụ.

Câu lệnh ghi có điều kiện để hệ quản trị kiểm tra điều kiện và cập nhật trong cùng thao tác. Nó tránh khoảng thời gian giữa một lần đọc riêng và một lần ghi riêng. Với nghiệp vụ phức tạp hơn, vẫn cần transaction và khóa phù hợp.

### 7.3. Luôn lấy khóa theo cùng một thứ tự

Khi một transaction cần cập nhật nhiều tài khoản hoặc nhiều hàng, hãy quy định thứ tự truy cập thống nhất, chẳng hạn theo khóa chính tăng dần.

Ví dụ, mọi giao dịch chuyển tiền đều khóa tài khoản có ID nhỏ hơn trước rồi mới khóa tài khoản có ID lớn hơn. Nếu T1 và T2 cùng xử lý cặp tài khoản 10 và 20, cả hai đều phải lấy khóa theo thứ tự 10 → 20. Điều này tránh tình huống một giao dịch giữ khóa 10 và chờ 20 trong khi giao dịch kia giữ 20 và chờ 10.

Với truy vấn lấy nhiều hàng, cần kiểm tra hành vi khóa thực tế của hệ quản trị và execution plan; không nên mặc định rằng thứ tự xuất hiện trong câu SQL luôn bảo đảm thứ tự khóa ở mọi hệ thống.

### 7.4. Giữ transaction ngắn

Chỉ đặt những thao tác cần tính nguyên tử vào trong transaction. Hãy hoàn thành việc kiểm tra và ghi dữ liệu rồi COMMIT sớm.

Tránh giữ transaction mở trong lúc:

- Gọi HTTP hoặc dịch vụ bên ngoài.
- Chờ nhập liệu hoặc xác nhận từ người dùng.
- Thực hiện xử lý tốn thời gian không cần khóa cơ sở dữ liệu.
- Chạy truy vấn rộng hơn phạm vi dữ liệu cần thay đổi.

Transaction ngắn làm giảm thời gian khóa bị giữ và giảm xác suất các giao dịch chồng lấn theo cách tạo thành chu trình chờ.

### 7.5. Giới hạn phạm vi dữ liệu bị khóa

Chỉ truy cập những hàng cần thiết và dùng điều kiện lọc có chỉ mục phù hợp. Truy vấn quét phạm vi lớn có thể khiến hệ quản trị phải khóa nhiều hàng hoặc phạm vi hơn dự kiến. Ở các mức cô lập như SERIALIZABLE, khóa phạm vi hoặc khóa khoảng trống còn có thể được dùng để ngăn hiện tượng phantom.

Tối ưu chỉ mục và điều kiện truy vấn có thể giảm số tài nguyên bị khóa, nhưng không thay thế việc thiết kế thứ tự khóa và thời gian transaction hợp lý.

### 7.6. Giữ mức cô lập phù hợp với yêu cầu nghiệp vụ

Không nên hạ isolation level chỉ để làm deadlock biến mất nếu điều đó khiến nghiệp vụ chấp nhận dữ liệu không nhất quán. Trước hết, xác định giao dịch cần bảo đảm gì: đọc lặp lại cùng kết quả, ngăn phantom, hay chỉ cần cập nhật nguyên tử một hàng.

Chọn isolation level phù hợp, sau đó dùng locking read hoặc câu lệnh ghi có điều kiện ở những điểm cần đồng bộ. Cơ chế MVCC có thể giảm tranh chấp đọc–ghi nhưng không loại bỏ deadlock giữa các thao tác ghi hoặc các khóa phạm vi.

### 7.7. Retry toàn bộ transaction khi nhận lỗi deadlock

Deadlock thường là lỗi có thể thử lại: hệ quản trị hủy một giao dịch để giải phóng vòng chờ, sau đó ứng dụng có thể chạy lại giao dịch đó.

Quy trình retry nên:

1. Nhận diện đúng lỗi deadlock từ mã lỗi hoặc loại exception của hệ quản trị.
2. Rollback hoặc đóng transaction hiện tại theo yêu cầu của driver/framework.
3. Bắt đầu một transaction mới và chạy lại toàn bộ đơn vị nghiệp vụ.
4. Giới hạn số lần retry; có thể thêm khoảng chờ tăng dần và ngẫu nhiên (*backoff with jitter*).
5. Bảo đảm các tác động ngoài cơ sở dữ liệu có tính idempotent hoặc được điều phối riêng để retry không gửi email, thu tiền hay phát thông điệp trùng lặp.

Không nên chỉ chạy lại câu UPDATE bị lỗi trong transaction đã bị hệ quản trị đánh dấu rollback hoặc không còn hợp lệ. Hãy khởi động lại toàn bộ transaction theo đúng ranh giới nghiệp vụ.

## 8. Phân biệt blocking và deadlock khi điều tra

**Blocking** là một giao dịch phải chờ khóa do giao dịch khác đang giữ. Nếu giao dịch giữ khóa hoàn tất, giao dịch đang chờ có thể tiếp tục. Một quan hệ chờ đơn lẻ chưa phải deadlock.

**Deadlock** là một chu trình chờ: mỗi giao dịch trong chu trình đều cần một tài nguyên đang bị giao dịch khác trong chu trình giữ. Không giao dịch nào có thể tự tiến lên để giải phóng tài nguyên.

Khi điều tra, hãy thu thập:

- Mã lỗi và báo cáo deadlock do hệ quản trị cung cấp.
- Các transaction tham gia, câu lệnh đang chạy và thứ tự thực thi.
- Tài nguyên bị khóa, chế độ khóa đang giữ và chế độ khóa đang yêu cầu.
- Isolation level, locking hint và chế độ MVCC.
- Execution plan và chỉ mục được sử dụng.
- Thời gian transaction mở và vị trí ứng dụng bắt đầu/commit transaction.

Đừng kết luận rằng một truy vấn chậm là deadlock chỉ vì nó đang chờ khóa. Hãy tìm chu trình trong đồ thị chờ hoặc báo cáo deadlock. Lock wait timeout có thể kết thúc một lần chờ kéo dài, nhưng timeout tự nó không chứng minh rằng có chu trình deadlock.

## 9. Ví dụ chọn cách triển khai

Giả sử một dịch vụ cần đọc số dư tài khoản, kiểm tra điều kiện rồi cộng thêm tiền.

| Cách triển khai | Hành vi khóa có thể xảy ra | Nhận xét |
|---|---|---|
| Đọc có khóa chia sẻ, sau đó cập nhật | Nhiều giao dịch có thể cùng giữ S rồi đồng thời yêu cầu X | Có nguy cơ deadlock nâng cấp S → X |
| Đọc bằng khóa cập nhật hoặc khóa ghi ngay từ đầu | Các giao dịch tranh quyền cập nhật được tuần tự hóa sớm hơn | Giảm mẫu deadlock nâng cấp; có thể tăng thời gian chờ |
| Dùng một câu UPDATE có điều kiện | Hệ quản trị kiểm tra điều kiện và ghi trong cùng câu lệnh | Thường giảm khoảng trống giữa đọc và ghi |
| Cập nhật nhiều hàng theo thứ tự nhất quán | Các giao dịch lấy khóa theo cùng một trật tự | Giảm deadlock do đảo thứ tự tài nguyên |

Không có một lựa chọn duy nhất phù hợp với mọi nghiệp vụ. Nếu cần đọc nhiều dữ liệu để tính toán, hãy xác định rõ dữ liệu nào cần khóa, khóa nào cần lấy từ đầu và transaction có thể ngắn đến đâu. Nếu chỉ cần kiểm tra rồi cập nhật một hàng, ưu tiên câu lệnh ghi nguyên tử có điều kiện.

## 10. Checklist khi thiết kế thao tác đọc–sửa

Trước khi đưa một luồng đọc rồi cập nhật vào production, hãy tự kiểm tra:

- [ ] Thao tác đọc có thực sự tạo khóa trên hàng không, hay đang đọc bằng MVCC?
- [ ] Nếu có khóa đọc, nó được giữ đến cuối câu lệnh hay đến cuối transaction?
- [ ] Có nhiều giao dịch cùng đọc rồi nâng cấp khóa trên một tài nguyên không?
- [ ] Có thể lấy khóa cập nhật ngay từ đầu hoặc dùng một câu ghi có điều kiện không?
- [ ] Nếu cần nhiều tài nguyên, mọi luồng có lấy khóa theo cùng thứ tự không?
- [ ] Transaction có giữ khóa trong lúc gọi dịch vụ ngoài hoặc chờ người dùng không?
- [ ] Ứng dụng có nhận diện deadlock và retry toàn bộ transaction một cách an toàn không?

Chuyển đổi khóa là cơ chế cần thiết để bảo vệ dữ liệu khi một giao dịch chuyển từ đọc sang ghi. Deadlock xuất hiện khi nhiều yêu cầu khóa không tương thích tạo thành chu trình chờ. Bằng cách hiểu chế độ khóa thực tế của hệ quản trị, lấy khóa đúng thời điểm, thống nhất thứ tự truy cập và giữ transaction ngắn, ta có thể giảm đáng kể loại tranh chấp này mà vẫn giữ được tính đúng đắn của dữ liệu.

