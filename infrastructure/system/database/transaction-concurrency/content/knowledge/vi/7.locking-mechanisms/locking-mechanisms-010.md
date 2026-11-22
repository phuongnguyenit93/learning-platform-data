# Phân biệt khóa giao dịch với khóa tư vấn (advisory lock)

Trong xử lý đồng thời, nhiều transaction có thể cùng muốn thay đổi một dữ liệu hoặc thực hiện một công việc liên quan đến cùng một tài nguyên. Cơ sở dữ liệu cần cơ chế điều phối để tránh các thao tác xung đột làm sai dữ liệu hoặc tạo ra kết quả không nhất quán.

Hai cơ chế thường gặp là **khóa giao dịch** và **khóa tư vấn (advisory lock)**. Cả hai đều có thể khiến một transaction phải chờ transaction khác, nhưng chúng bảo vệ những thứ khác nhau:

- **Khóa giao dịch** là khóa mà DBMS sử dụng để bảo vệ dữ liệu và cấu trúc dữ liệu đang được transaction đọc hoặc thay đổi.
- **Advisory lock** là khóa theo một định danh logic do ứng dụng quy ước. DBMS quản lý việc cấp và chờ khóa, còn ý nghĩa của tài nguyên được khóa do ứng dụng xác định.

Một điểm dễ gây nhầm lẫn: advisory lock cũng có thể được giữ trong suốt transaction. Vì vậy, cụm từ “khóa giao dịch” trong bài này nói đến khóa dữ liệu do DBMS sử dụng để bảo vệ thao tác trên dữ liệu; nó không có nghĩa mọi loại khóa được giữ đến lúc transaction kết thúc đều là khóa dữ liệu.

## 1. So sánh nhanh

| Tiêu chí | Khóa giao dịch (transaction/data lock) | Khóa tư vấn (advisory lock) |
|---|---|---|
| Mục đích | Bảo vệ dữ liệu hoặc cấu trúc dữ liệu trước các thao tác xung đột | Điều phối các luồng xử lý cùng quan tâm đến một tài nguyên logic |
| Đối tượng khóa | Hàng, bảng, khóa chỉ mục, phạm vi dữ liệu hoặc đối tượng mà DBMS hỗ trợ | Một khóa định danh do ứng dụng quy ước, chẳng hạn **customer:1001** hoặc **report:202611** |
| Ai yêu cầu khóa? | DBMS thường tự lấy khi thực hiện **INSERT**, **UPDATE**, **DELETE**; ứng dụng cũng có thể yêu cầu tường minh bằng câu lệnh khóa | Ứng dụng chủ động gọi API khóa tư vấn |
| DBMS hiểu điều gì đang được bảo vệ? | DBMS biết khóa gắn với dữ liệu hoặc cấu trúc dữ liệu nào | DBMS chỉ biết khóa có định danh nào; ý nghĩa nghiệp vụ của định danh thuộc về ứng dụng |
| Ai phải tuân thủ? | Các thao tác dữ liệu xung đột được DBMS điều phối theo quy tắc khóa và isolation level | Các luồng xử lý dùng cùng quy ước advisory lock mới phối hợp với nhau |
| Thời điểm giải phóng | Thông thường khi transaction commit hoặc rollback; chi tiết tùy loại khóa và DBMS | Tùy API: có thể theo transaction hoặc theo session |
| Vai trò với tính toàn vẹn | Là một phần trong cơ chế bảo vệ dữ liệu của DBMS, kết hợp với constraint và isolation | Hỗ trợ phối hợp công việc; tự nó không thay thế constraint hoặc kiểm tra tính toàn vẹn |

Khác biệt cốt lõi nằm ở **mối liên hệ giữa khóa và dữ liệu**. Khóa giao dịch bảo vệ dữ liệu mà DBMS đang quản lý. Advisory lock bảo vệ một quy ước xử lý mà ứng dụng muốn các thành phần cùng tuân theo.

## 2. Khóa giao dịch: DBMS bảo vệ dữ liệu

Khi một transaction cập nhật một hàng, DBMS phải kiểm soát những transaction khác đang muốn thay đổi cùng hàng đó. Nếu không có cơ chế này, hai transaction có thể ghi đè kết quả của nhau hoặc cùng đưa dữ liệu vào một trạng thái không hợp lệ.

Ví dụ, hai khách hàng cùng mua sản phẩm cuối cùng trong kho. Câu lệnh **UPDATE** phải được DBMS điều phối để hai transaction không đồng thời trừ số lượng từ cùng một giá trị cũ.

~~~sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 101
  AND quantity > 0;

-- Ứng dụng kiểm tra số hàng bị ảnh hưởng:
-- 1 hàng: đã giữ được một sản phẩm
-- 0 hàng: sản phẩm không còn đủ số lượng

COMMIT;
~~~

Khi chạy **UPDATE**, DBMS tự lấy các khóa cần thiết để bảo vệ thao tác. Nếu transaction khác đang giữ khóa xung đột trên cùng dữ liệu, thao tác có thể phải chờ. Câu lệnh có điều kiện **quantity > 0** cũng giúp tránh giảm số lượng xuống dưới 0; có thể bổ sung **CHECK (quantity >= 0)** để DBMS bảo vệ bất biến này ở cấp dữ liệu.

Ứng dụng cũng có thể yêu cầu khóa hàng trước khi kiểm tra và cập nhật:

~~~sql
BEGIN;

SELECT quantity
FROM inventory
WHERE product_id = 101
FOR UPDATE;

-- Ứng dụng kiểm tra quantity trong khi vẫn giữ khóa hàng.

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 101
  AND quantity > 0;

COMMIT;
~~~

**SELECT ... FOR UPDATE** yêu cầu DBMS khóa các hàng được chọn theo ngữ nghĩa của hệ quản trị. Transaction khác muốn cập nhật hoặc lấy khóa xung đột trên các hàng đó sẽ phải chờ cho đến khi khóa được giải phóng. Các câu **SELECT** thông thường có thể vẫn đọc phiên bản đã commit trước đó trong hệ quản trị dùng MVCC; không nên hiểu rằng mọi loại khóa hàng đều chặn tất cả lượt đọc.

### DBMS lấy khóa ở đâu?

Tùy câu lệnh, isolation level và hệ quản trị, DBMS có thể quản lý khóa ở nhiều mức:

- **Row lock**: khóa một hoặc nhiều hàng.
- **Table lock**: khóa ở mức bảng, thường có nhiều mode với mức độ tương thích khác nhau.
- **Index/key/range lock**: khóa khóa chỉ mục hoặc phạm vi khóa trong những hệ quản trị và tình huống có hỗ trợ.
- **Predicate lock**: ghi nhận phạm vi đọc để hỗ trợ phát hiện xung đột trong một số cơ chế isolation.

Không phải mọi DBMS đều dùng cùng tên, cùng granularity hoặc cùng thuật toán. Một số hệ quản trị dựa nhiều vào MVCC để cho phép người đọc tiếp tục đọc phiên bản đã commit trong khi transaction khác đang ghi. Vì vậy, khi phân tích một tình huống cụ thể, cần xem loại câu lệnh, isolation level và tài liệu của DBMS đang sử dụng.

Điểm quan trọng là DBMS hiểu thao tác dữ liệu nào đang xung đột và áp dụng quy tắc khóa của nó, kể cả khi ứng dụng không tự gọi một hàm khóa riêng.

## 3. Advisory lock: ứng dụng khóa một tài nguyên logic

Có những tình huống ứng dụng muốn bảo đảm chỉ một luồng xử lý thực hiện một công việc tại một thời điểm, nhưng công việc đó không tương ứng trực tiếp với một hàng đã tồn tại.

Ví dụ:

- Chỉ tạo báo cáo tháng cho một khách hàng một lần tại một thời điểm.
- Chỉ chạy một tác vụ đồng bộ cho cùng một tài khoản.
- Chỉ xử lý một đơn hàng bằng một luồng nghiệp vụ tại một thời điểm.
- Tránh hai worker cùng khởi tạo một tài nguyên có khóa nghiệp vụ giống nhau.

Ứng dụng có thể yêu cầu advisory lock với một khóa định danh. DBMS cấp khóa cho một transaction hoặc session; nếu một luồng khác yêu cầu khóa xung đột với cùng định danh, nó phải chờ hoặc nhận kết quả không lấy được khóa, tùy API được gọi.

Ví dụ dưới đây dùng PostgreSQL. Hai số nguyên được ứng dụng quy ước: **7001** là namespace cho tác vụ tạo báo cáo tháng, còn **202611** là kỳ báo cáo.

~~~sql
BEGIN;

SELECT pg_advisory_xact_lock(7001, 202611);

-- Chỉ một transaction đang dùng cùng cặp khóa
-- (7001, 202611) có thể đi qua vùng xử lý này tại một thời điểm.

INSERT INTO monthly_reports (period_code, generated_at)
VALUES (202611, CURRENT_TIMESTAMP)
ON CONFLICT (period_code) DO NOTHING;

COMMIT;
~~~

**pg_advisory_xact_lock** lấy advisory lock ở phạm vi transaction. Nếu một transaction khác cũng gọi hàm với cặp khóa **(7001, 202611)**, nó sẽ chờ cho đến khi transaction đang giữ khóa kết thúc. Khi transaction commit hoặc rollback, khóa được tự động giải phóng.

DBMS không tự hiểu **202611** là kỳ báo cáo và cũng không tự biết bảng **monthly_reports** liên quan đến khóa đó. Ý nghĩa của hai số khóa đến từ quy ước trong ứng dụng. Một đoạn code khác có thể cập nhật hoặc xóa hàng trong **monthly_reports** mà không gọi advisory lock; DBMS vẫn cho phép thao tác đó nếu không có khóa dữ liệu nào khác ngăn cản.

Vì thế, advisory lock chỉ điều phối được những luồng xử lý cùng tuân thủ quy ước khóa. Trong ví dụ, **UNIQUE** constraint trên **period_code** vẫn cần thiết để bảo vệ quy tắc mỗi kỳ chỉ có tối đa một báo cáo, kể cả khi có một đường ghi dữ liệu quên lấy advisory lock.

### Advisory lock không cần hàng dữ liệu tồn tại

Đây là một trường hợp advisory lock hữu ích. Giả sử hai worker cùng kiểm tra xem báo cáo tháng 11 đã tồn tại chưa. Nếu chưa có hàng nào, không có hàng hiện hữu để dùng **SELECT ... FOR UPDATE** khóa. Hai worker có thể cùng thấy “chưa tồn tại” rồi cùng thử tạo.

Một advisory lock theo khóa nghiệp vụ **report:202611** cho phép ứng dụng điều phối ngay cả khi hàng báo cáo chưa được tạo. Tuy nhiên, unique constraint vẫn là lớp bảo vệ cuối cùng cho tính duy nhất của dữ liệu.

## 4. Phạm vi tồn tại của advisory lock

Advisory lock không nhất thiết luôn tồn tại đến cuối transaction. Phạm vi phụ thuộc API mà DBMS cung cấp.

Trong PostgreSQL, có hai nhóm thường gặp:

| API | Phạm vi khóa | Khi nào được giải phóng |
|---|---|---|
| **pg_advisory_xact_lock(...)** | Transaction | Tự động khi transaction commit hoặc rollback |
| **pg_advisory_lock(...)** | Session/connection | Khi gọi hàm unlock tương ứng hoặc session kết thúc |

Có thể dùng biến thể **pg_try_advisory_xact_lock(...)** nếu muốn thử lấy khóa mà không chờ. Hàm trả về **true** nếu lấy được khóa và **false** nếu khóa xung đột đang được giữ.

~~~sql
BEGIN;

SELECT pg_try_advisory_xact_lock(7001, 202611);

-- Nếu kết quả là true: tiếp tục xử lý.
-- Nếu kết quả là false: bỏ qua, thử lại sau hoặc báo công việc đang được xử lý.

COMMIT;
~~~

Với session-level lock, **COMMIT** hoặc **ROLLBACK** không tự giải phóng khóa. Điều này đặc biệt cần chú ý khi ứng dụng dùng connection pool: connection có thể được trả về pool trong khi advisory lock vẫn còn trên session, khiến request tiếp theo nhận connection đó và gặp trạng thái khóa ngoài dự kiến. Nếu dùng loại khóa này, ứng dụng phải quản lý việc unlock và vòng đời connection một cách rõ ràng.

Một số DBMS có cách đặt phạm vi khác. Ví dụ, SQL Server hỗ trợ application lock qua **sp_getapplock** với owner là transaction hoặc session. MySQL có **GET_LOCK** với phạm vi gắn với connection. Oracle cung cấp cơ chế user lock qua **DBMS_LOCK**. Không nên suy luận rằng tên hàm hoặc cách giải phóng khóa giống nhau giữa các hệ quản trị.

## 5. Khi nào nên dùng từng loại?

Hãy chọn dựa trên thứ cần bảo vệ.

| Tình huống | Cơ chế phù hợp | Lý do |
|---|---|---|
| Cập nhật số dư của một tài khoản | Khóa dữ liệu trong transaction, kết hợp constraint/điều kiện cập nhật | DBMS phải điều phối các thao tác ghi lên dữ liệu thật |
| Đặt chỗ cho một hàng tồn kho hiện có | **UPDATE** có điều kiện hoặc khóa hàng tường minh | Trạng thái cần bảo vệ nằm trong hàng dữ liệu |
| Hai worker cùng tạo báo cáo cho một kỳ chưa có hàng | Advisory lock theo khóa nghiệp vụ, kết hợp unique constraint | Có thể khóa tài nguyên logic trước khi hàng tồn tại |
| Chỉ cho một tác vụ đồng bộ chạy trên một tài khoản | Advisory lock theo account id | Tài nguyên cần điều phối là một công việc logic |
| Bảo đảm email không trùng hoặc mã đơn hàng là duy nhất | Unique constraint | Đây là quy tắc dữ liệu cần được DBMS cưỡng chế ở mọi đường ghi |

Có thể dùng cả hai cơ chế trong cùng một luồng. Advisory lock điều phối công việc ở mức nghiệp vụ; transaction lock bảo vệ các hàng thực tế khi đọc và ghi. Constraint bảo vệ các bất biến dữ liệu mà mọi đường ghi đều phải tuân thủ.

Ví dụ, khi tạo báo cáo cho một kỳ:

1. Lấy advisory lock theo định danh kỳ báo cáo để tránh nhiều worker cùng chạy quy trình.
2. Đọc hoặc ghi các hàng báo cáo trong transaction.
3. Dùng unique constraint để bảo đảm không thể lưu hai báo cáo cho cùng một kỳ.
4. Commit để giải phóng transaction-scoped advisory lock và các khóa dữ liệu của transaction.

## 6. Các lỗi thiết kế thường gặp

### Các luồng xử lý không dùng cùng một khóa

Advisory lock chỉ tạo ra xung đột khi các luồng yêu cầu cùng định danh khóa theo quy tắc tương thích của DBMS. Nếu worker A khóa **(7001, 202611)** nhưng worker B khóa **(7002, 202611)**, DBMS xem đó là hai khóa khác nhau. Hai worker vẫn có thể chạy đồng thời.

Vì vậy, cần quy định rõ namespace, cách tạo khóa và ý nghĩa của từng thành phần. Mọi service hoặc worker cùng điều phối một tài nguyên phải dùng chung quy ước.

### Tự tạo khóa từ chuỗi nhưng bỏ qua va chạm

Ứng dụng thường có khóa nghiệp vụ dạng chuỗi như **customer:1001** hoặc **report:202611**, trong khi API advisory lock có thể nhận số nguyên. Nếu chuyển chuỗi thành hash, hai chuỗi khác nhau có khả năng tạo ra cùng giá trị hash. Khi đó, các công việc không liên quan có thể chặn nhau.

Va chạm như vậy thường làm giảm khả năng chạy song song; nguy hiểm hơn là cách ánh xạ không ổn định giữa các service khiến chúng không khóa cùng một tài nguyên như dự kiến. Nên dùng cách ánh xạ có quy ước rõ ràng, tách namespace và hiểu giới hạn kích thước khóa của DBMS.

### Nghĩ rằng advisory lock tự bảo vệ hàng dữ liệu

Một câu lệnh **UPDATE** không tự động kiểm tra xem ứng dụng có lấy advisory lock hay chưa. Nếu một luồng bỏ qua giao thức advisory lock, nó vẫn có thể cập nhật dữ liệu nếu không bị khóa dữ liệu, constraint hoặc điều kiện khác ngăn lại.

Nếu yêu cầu là “không được có hai hàng cùng mã”, hãy dùng unique constraint. Nếu yêu cầu là “số lượng không được âm”, hãy dùng điều kiện cập nhật và/hoặc check constraint. Advisory lock có thể bổ sung điều phối, nhưng không thay thế các quy tắc dữ liệu này.

### Giữ session lock quá lâu

Session-level advisory lock có thể tồn tại qua nhiều transaction. Nếu connection được tái sử dụng trong pool mà khóa chưa được giải phóng, request khác có thể bị ảnh hưởng. Với công việc có ranh giới transaction rõ ràng, transaction-scoped lock thường dễ quản lý vòng đời hơn.

### Tạo deadlock do thứ tự lấy khóa

Hai transaction có thể deadlock nếu mỗi bên giữ một khóa và chờ khóa bên kia. Ví dụ, transaction A lấy khóa tài khoản 1 rồi chờ tài khoản 2, trong khi transaction B lấy khóa tài khoản 2 rồi chờ tài khoản 1.

Nếu phải lấy nhiều advisory lock, hãy sắp xếp thứ tự khóa nhất quán, chẳng hạn luôn lấy theo account id tăng dần. Đồng thời, thiết kế timeout, xử lý lỗi deadlock và retry phù hợp với nghiệp vụ. Không nên retry vô hạn hoặc giữ transaction mở lâu trong lúc chờ thao tác bên ngoài.

## 7. Cách ghi nhớ

- Cần bảo vệ một hàng hoặc dữ liệu đang được đọc/ghi? Dùng cơ chế khóa dữ liệu của transaction, câu lệnh cập nhật phù hợp và constraint.
- Cần điều phối một tài nguyên logic do ứng dụng đặt tên, kể cả khi tài nguyên chưa có hàng dữ liệu? Advisory lock có thể phù hợp.
- Cần bảo đảm một quy tắc luôn đúng bất kể request đi qua service nào? Đặt quy tắc đó ở DBMS bằng constraint hoặc thao tác dữ liệu có điều kiện.
- Dùng advisory lock thì tất cả luồng liên quan phải thống nhất định danh, phạm vi khóa và cách giải phóng.

Khóa giao dịch và advisory lock giải quyết hai lớp vấn đề khác nhau. Khóa dữ liệu giúp DBMS quản lý xung đột khi transaction thao tác trên dữ liệu. Advisory lock giúp ứng dụng phối hợp các công việc theo một tài nguyên logic. Hiểu rõ đối tượng được khóa, bên chịu trách nhiệm tuân thủ và thời điểm giải phóng sẽ giúp chọn đúng cơ chế cho từng tình huống đồng thời.
