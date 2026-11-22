# Tính đúng đắn và hiệu năng khi nhiều giao dịch cùng truy cập dữ liệu

## 1. Vì sao cần điều khiển giao dịch đồng thời?

Trong một hệ thống nhiều người dùng, các giao dịch (transaction) thường chạy xen kẽ trên cùng dữ liệu: hai khách cùng mua sản phẩm cuối cùng, nhiều yêu cầu cùng trừ tiền một tài khoản, hoặc hai nhân viên đồng thời chỉnh sửa một đơn hàng. Chạy đồng thời giúp máy chủ tận dụng CPU, bộ nhớ, I/O và phục vụ nhiều yêu cầu hơn. Tuy nhiên, nếu các thao tác đọc và ghi không được phối hợp, mỗi giao dịch có thể đưa ra quyết định từ một trạng thái dữ liệu đã lỗi thời.

Ví dụ, kho có một sản phẩm với `stock = 1`. Hai giao dịch cùng thực hiện:

1. Đọc thấy `stock = 1`.
2. Kiểm tra số lượng đủ để bán.
3. Tạo một đơn đặt hàng.
4. Ghi `stock = 0`.

Kết quả có **hai đơn được chấp nhận cho một sản phẩm**. Cột tồn kho không nhất thiết âm, nên chỉ kiểm tra `stock >= 0` vẫn chưa phát hiện được lỗi nghiệp vụ.

Mục tiêu của **database transaction concurrency** là đạt được đồng thời hai điều kiện:

- **Tính đúng đắn (correctness):** mọi kết quả đã cam kết (commit) phải tuân thủ các quy tắc dữ liệu và nghiệp vụ, kể cả khi có nhiều yêu cầu cạnh tranh.
- **Hiệu năng (performance):** phục vụ số lượng giao dịch hợp lý với độ trễ chấp nhận được, hạn chế thời gian đợi khóa, số lần thử lại và lượng tài nguyên tiêu thụ.

Hai mục tiêu này liên quan chặt chẽ: giảm khóa có thể tăng khả năng xử lý đồng thời nhưng dễ làm lộ xung đột; khóa quá rộng có thể giữ dữ liệu an toàn nhưng khiến nhiều giao dịch phải xếp hàng. Thiết kế tốt bắt đầu từ **quy tắc bất biến của nghiệp vụ**, rồi mới lựa chọn mức cô lập và cơ chế phối hợp phù hợp.

### 1.1. Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| Transaction | Nhóm thao tác đọc/ghi có ranh giới commit hoặc rollback | Các bước nào phải thành công hoặc thất bại cùng nhau? |
| Concurrency | Nhiều transaction có thời gian thực thi chồng lấn | Chúng có cùng đọc/ghi một dữ liệu không? |
| Consistency invariant | Điều kiện phải đúng trước và sau các transaction hợp lệ | Tồn kho có được âm? Một ca trực có cần ít nhất một người? |
| Isolation | Mức độ giao dịch tránh ảnh hưởng của thay đổi từ giao dịch khác | Transaction được phép quan sát trạng thái nào? |
| Contention | Nhiều transaction cạnh tranh cùng khóa, hàng, phạm vi hoặc tài nguyên | Điểm nóng khiến các giao dịch phải chờ ở đâu? |
| Throughput | Lượng transaction hoàn tất trên đơn vị thời gian | Hệ thống hoàn thành bao nhiêu giao dịch/giây? |
| Latency | Thời gian từ yêu cầu đến kết quả | Yêu cầu mất bao lâu, đặc biệt ở p95/p99? |

**Đồng thời** không nhất thiết là chạy song song trên nhiều lõi CPU. Chỉ cần hai transaction có các thao tác xen kẽ nhau là đủ để xuất hiện rủi ro.

## 2. Định nghĩa tính đúng đắn trước khi tối ưu

### 2.1. Bất biến nghiệp vụ là thước đo cuối cùng

Một cơ sở dữ liệu có thể thực hiện commit thành công nhưng dữ liệu vẫn sai về mặt nghiệp vụ nếu ứng dụng kiểm tra và cập nhật không đúng cách. Những bất biến thường gặp gồm:

- `products.stock >= 0` và tổng số lượng bán không vượt quá số lượng có thể cấp phát.
- `accounts.balance >= 0` khi sản phẩm không hỗ trợ thấu chi.
- Tổng tiền của các tài khoản tham gia chuyển khoản phải được bảo toàn, nếu không có phí hay dòng tiền ngoài.
- Mỗi mã yêu cầu thanh toán chỉ được ghi nhận đúng một lần.
- Một ca trực phải luôn có ít nhất một bác sĩ trực.
- Hai đặt phòng không được chiếm cùng một phòng trong cùng khoảng thời gian.

Bất biến **trên một hàng** thường dễ kiểm soát bằng `CHECK`, `UNIQUE` hoặc câu lệnh cập nhật có điều kiện. Bất biến **trên nhiều hàng hoặc nhiều bảng** đòi hỏi xem xét các transaction đọc gì, ghi gì và có thể tranh chấp với nhau ra sao.

Ví dụ, điều kiện `CHECK (stock >= 0)` bảo vệ số tồn kho không âm, nhưng không ngăn ứng dụng tạo hai đơn hàng rồi cùng gán `stock = 0` nếu việc tạo đơn và cập nhật kho không được điều phối đúng.

### 2.2. ACID giúp gì và chưa đủ ở đâu?

- **Atomicity:** các thay đổi của một transaction được áp dụng trọn vẹn hoặc rollback trọn vẹn.
- **Consistency:** transaction hợp lệ phải giữ các ràng buộc dữ liệu và bất biến nghiệp vụ. Database có thể thực thi một số ràng buộc khai báo, còn nhiều quy tắc vẫn do ứng dụng chịu trách nhiệm.
- **Isolation:** giới hạn cách transaction đang thực thi ảnh hưởng hoặc được nhìn thấy bởi transaction khác. Mức độ bảo vệ phụ thuộc isolation level và cách database triển khai.
- **Durability:** sau khi commit thành công theo cam kết của hệ quản trị, dữ liệu tồn tại bền vững theo cấu hình lưu trữ/khôi phục của hệ thống.

**Atomicity không đồng nghĩa với isolation mạnh.** Hai transaction đều atomic nhưng vẫn có thể cùng ra quyết định dựa trên dữ liệu cũ và gây sai lệch nghiệp vụ.

### 2.3. Lịch thực thi và tính tương đương tuần tự

Một **schedule** là thứ tự thực tế của các thao tác thuộc nhiều transaction. Schedule *tuần tự* chạy hết T1 rồi mới đến T2, hoặc ngược lại. Schedule *xen kẽ* có thể chạy một phần T1, chuyển sang T2, rồi quay lại T1.

**Serializability** là tính chất cho phép kết quả của các transaction đã commit tương đương với một cách chạy tuần tự nào đó của chính các transaction ấy. Đây là mô hình rất hữu ích để lý luận về tính đúng đắn: nếu từng transaction bảo vệ bất biến khi chạy một mình, một lịch thực thi tương đương tuần tự sẽ tránh được nhiều lỗi do xen kẽ.

Tuy nhiên, serializability chỉ áp dụng cho các thao tác tham gia cùng phạm vi kiểm soát giao dịch. Một email đã gửi hoặc cuộc gọi API đã xảy ra trước khi rollback không tự động được hoàn tác. Ngoài ra, serializability thông thường không mặc nhiên bảo đảm ràng buộc thứ tự theo thời gian thực giữa mọi client; yêu cầu đó liên quan đến các mô hình mạnh hơn như *strict serializability*.

## 3. Các dạng sai lệch do giao dịch đồng thời

### 3.1. Dirty read: đọc thay đổi chưa commit

Giả sử T1 cập nhật số dư từ 100 thành 500 nhưng chưa commit. T2 đọc thấy 500; sau đó T1 rollback. T2 đã sử dụng một giá trị chưa từng trở thành trạng thái được commit.

~~~text
T1: BEGIN -> UPDATE balance = 500 ----------> ROLLBACK
T2:                    READ balance = 500 --> quyết định sai
~~~

Dirty read có thể xảy ra tại những hệ thống và mức cô lập cho phép đọc dữ liệu chưa commit. Phần lớn cấu hình giao dịch thường dùng chặn kiểu đọc này.

### 3.2. Non-repeatable read: một hàng đổi giữa hai lần đọc

T1 đọc giá sản phẩm là 100. T2 sửa giá thành 120 rồi commit. T1 đọc lại cùng hàng và thấy 120 trong cùng transaction.

~~~text
T1: READ price = 100 ---------------- READ price = 120
T2:                   UPDATE 120; COMMIT
~~~

Hành vi này có thể hoàn toàn hợp lệ ở `READ COMMITTED`, nhưng gây rắc rối nếu T1 tính toán dựa trên giả định rằng dữ liệu mình đọc sẽ giữ nguyên suốt transaction.

### 3.3. Phantom read: tập hàng thỏa điều kiện thay đổi

T1 chạy `SELECT COUNT(*) FROM bookings WHERE room_id = 5 AND booking_date = ...` và nhận 0. T2 chèn một booking phù hợp rồi commit. T1 chạy lại đúng câu truy vấn và nhận 1.

Phantom liên quan đến **tập kết quả của một điều kiện tìm kiếm**, kể cả các hàng mới xuất hiện hoặc biến mất, thay vì chỉ việc đọc lại giá trị của một hàng đã có. Một snapshot ổn định có thể ngăn thay đổi tập kết quả trong giao dịch đọc; cách bảo vệ cụ thể tùy database.

### 3.4. Lost update: thay đổi của transaction bị ghi đè

Ban đầu `counter = 10`. T1 và T2 đều đọc 10; T1 tính 11, T2 cũng tính 11. Hai transaction lần lượt ghi 11. Kết quả cuối cùng là 11 thay vì 12.

| Thời điểm | Transaction T1 | Transaction T2 |
|---|---|---|
| 1 | Đọc `counter = 10` | |
| 2 | | Đọc `counter = 10` |
| 3 | Ghi `counter = 11` và commit | |
| 4 | | Ghi `counter = 11` và commit |
| 5 | **Giá trị cuối = 11** | **Một lần tăng bị mất** |

Phân biệt hai kiểu cập nhật:

~~~sql
-- Rủi ro: ứng dụng đọc 10, tính 11 rồi ghi đè giá trị cũ.
UPDATE counters SET value = 11 WHERE id = 1;

-- An toàn hơn cho phép tăng đơn lẻ:
UPDATE counters SET value = value + 1 WHERE id = 1;
~~~

Trong database giao dịch thông dụng, câu `UPDATE value = value + 1` thực hiện phép tăng trong database và phối hợp các lần ghi cùng hàng theo cơ chế khóa/xung đột của engine. Điều này khác với chuỗi thao tác **đọc ở ứng dụng → tính toán → gán giá trị cố định**. Còn các quy tắc liên quan nhiều hàng vẫn cần bảo vệ riêng.

### 3.5. Write skew: mỗi transaction sửa một hàng khác nhau

Một ca trực có hai bác sĩ A và B, với quy tắc **phải có ít nhất một người trực**. Ban đầu cả hai đều đang trực.

- T1 đọc danh sách, thấy A và B; quyết định cho A nghỉ và cập nhật `A.on_call = false`.
- T2 cũng đọc cùng trạng thái ban đầu; quyết định cho B nghỉ và cập nhật `B.on_call = false`.
- Hai transaction sửa **hai hàng khác nhau**, nên một số cơ chế chỉ phát hiện xung đột ghi cùng hàng có thể cho cả hai commit.

Kết quả: không còn ai trực. Đây là **write skew**, một ví dụ điển hình cho thấy snapshot isolation có thể ngăn nhiều sai lệch đọc nhưng vẫn chưa bảo vệ một bất biến trên tập hàng.

~~~text
Ban đầu: A = trực, B = trực       Bất biến: số người trực >= 1

T1: đọc A,B = trực ---- cập nhật A = nghỉ ---- COMMIT
T2: đọc A,B = trực ---- cập nhật B = nghỉ ---- COMMIT

Cuối cùng: A = nghỉ, B = nghỉ     Bất biến bị vi phạm
~~~

Giải pháp có thể là `SERIALIZABLE` kèm retry khi bị abort, hoặc biến việc quyết định thành một thao tác được tuần tự hóa qua cùng một hàng/khóa đại diện cho ca trực, tùy thiết kế dữ liệu.

### 3.6. Tổng hợp hiện tượng

| Hiện tượng | Dấu hiệu | Ví dụ | Hướng xử lý |
|---|---|---|---|
| Dirty read | Đọc dữ liệu chưa commit | Thấy số dư sẽ bị rollback | Ít nhất `READ COMMITTED` trên engine hỗ trợ |
| Non-repeatable read | Đọc cùng hàng hai lần được hai giá trị đã commit | Giá thay đổi giữa phép tính | Snapshot ổn định hoặc khóa khi cần |
| Phantom | Tập hàng thỏa điều kiện thay đổi | Thêm booking mới | Bảo vệ điều kiện/ràng buộc, hoặc serializable |
| Lost update | Một cập nhật ghi đè cập nhật khác | Hai lần tăng chỉ tăng một | Atomic SQL, version check hoặc khóa |
| Write skew | Các ghi khác hàng cùng phá bất biến tập hợp | Hai bác sĩ cùng xin nghỉ | Serializable, khóa điểm phối hợp hoặc thiết kế lại bất biến |

**Không nên đồng nhất “không có dirty read” với “dữ liệu chắc chắn đúng”.** Một ứng dụng vẫn có thể gặp lost update, write skew hoặc xử lý trùng yêu cầu dù chỉ đọc các giá trị đã commit.

## 4. Database phối hợp các transaction như thế nào?

### 4.1. Khóa (locking)

Một số hệ quản trị dùng khóa chia sẻ/độc quyền hoặc biến thể của chúng để điều phối việc đọc và ghi. Khóa có thể gắn với hàng, trang, bảng, phạm vi chỉ mục hay một tài nguyên logic khác.

- **Exclusive lock:** ngăn các cập nhật cạnh tranh không tương thích cùng xảy ra trên tài nguyên bị khóa.
- **Shared lock:** cho phép những thao tác đọc tương thích cùng diễn ra, tùy database, isolation level và loại đọc.
- **Range/key/predicate protection:** bảo vệ thêm tập bản ghi thỏa điều kiện, vì chỉ khóa hàng hiện có sẽ không bảo vệ được sự xuất hiện của hàng mới.
- **Explicit row lock:** `SELECT ... FOR UPDATE` trong các hệ quản trị hỗ trợ có thể khóa những hàng hiện có được chọn để giao dịch kiểm tra và sửa chúng.

Ví dụ:

~~~sql
BEGIN;

SELECT balance
FROM accounts
WHERE id = 42
FOR UPDATE;

-- Kiểm tra đủ tiền, sau đó UPDATE trong cùng transaction.
-- Các transaction muốn lấy khóa ghi không tương thích trên hàng này sẽ chờ hoặc bị hủy.

COMMIT;
~~~

Khóa bảo vệ trạng thái nhưng có chi phí: transaction phải đợi nhau, phát sinh deadlock và có thể kéo dài khi một transaction thực hiện I/O chậm. **Khóa hàng hiện có không tự động bảo vệ một hàng chưa tồn tại**, chẳng hạn kiểm tra “chưa có booking nào” rồi insert; cần ràng buộc, khóa phạm vi hoặc cơ chế phù hợp.

### 4.2. MVCC: nhiều phiên bản của một bản ghi

**Multi-Version Concurrency Control (MVCC)** giữ các phiên bản dữ liệu để nhiều lượt đọc có thể quan sát snapshot phù hợp mà không luôn phải chờ transaction ghi.

Về mặt khái niệm:

~~~text
Phiên bản V1: balance = 100, đã commit
Phiên bản V2: balance = 120, commit sau đó

Transaction đọc với snapshot cũ -> có thể thấy V1
Transaction đọc với snapshot mới -> có thể thấy V2
~~~

Điểm cần nhớ:

1. MVCC cải thiện khả năng đọc đồng thời, nhưng **không có nghĩa là các ghi không cần phối hợp**.
2. Snapshot có thể được tạo cho từng câu lệnh hoặc cho transaction, tùy isolation level và engine.
3. Đọc snapshot nhất quán chưa chắc loại bỏ write skew.
4. Phiên bản cũ cần được dọn dẹp; transaction tồn tại quá lâu có thể gây áp lực lưu trữ và bảo trì phiên bản.

Ví dụ cụ thể: trong **PostgreSQL**, `READ COMMITTED` thường lấy snapshot cho mỗi câu lệnh, còn `REPEATABLE READ` sử dụng một snapshot nhất quán cho transaction. Ở **MySQL InnoDB**, cơ chế đọc nhất quán và đọc có khóa tại `REPEATABLE READ` có những quy tắc khác; không nên suy luận hành vi chính xác của một engine từ tên isolation level của engine khác.

### 4.3. Pessimistic và optimistic concurrency control

**Pessimistic control** chủ động lấy khóa trước khi sửa trạng thái: phù hợp khi khả năng xung đột cao hoặc quyết định cần dựa trên dữ liệu vừa khóa. Chi phí chính là thời gian giữ khóa và chờ khóa.

**Optimistic control** cho phép đọc, tính toán, rồi kiểm tra dữ liệu có còn đúng phiên bản lúc ghi hay không. Nếu phiên bản thay đổi, thao tác thất bại và ứng dụng phải tải lại, quyết định lại hoặc retry.

Ví dụ:

~~~sql
-- Đã đọc version = 7 và stock = 8 trước đó.
UPDATE products
SET stock = stock - 2,
    version = version + 1
WHERE id = 100
  AND version = 7
  AND stock >= 2;
~~~

Nếu số hàng được cập nhật bằng 0, có thể đã có transaction khác đổi phiên bản, hoặc hàng không còn tồn kho đủ, hoặc hàng không tồn tại. Ứng dụng phải kiểm tra nguyên nhân và xử lý theo nghiệp vụ; không được mặc định là thành công.

**Optimistic không có nghĩa là không có khóa ở thời điểm ghi.** Database vẫn phải điều phối câu `UPDATE`. Lợi ích là ứng dụng tránh giữ khóa xuyên suốt giai đoạn đọc và tính toán, đổi lại có thể phải thử lại khi tranh chấp nhiều.

### 4.4. Deadlock và serialization failure

**Deadlock** xảy ra khi T1 giữ khóa A và chờ B, còn T2 giữ khóa B và chờ A. Database thường phát hiện và hủy một transaction để tháo vòng chờ.

~~~text
T1: khóa account 10  -> chờ account 20
T2: khóa account 20  -> chờ account 10
                        ^ vòng chờ khóa ^
~~~

Một cách giảm nguy cơ là luôn lấy khóa theo cùng thứ tự, ví dụ `account_id` tăng dần. Cần giữ transaction ngắn, chọn chỉ mục phù hợp và tránh giao tiếp mạng chậm trong lúc giữ khóa.

**Serialization failure** là trường hợp database không thể cho phép lịch thực thi hiện tại commit mà vẫn đáp ứng isolation `SERIALIZABLE`; database hủy một transaction để ứng dụng thử lại. Đây có thể là hoạt động bình thường của cơ chế bảo vệ dữ liệu. Deadlock và serialization failure không đồng nghĩa, dù cả hai thường đòi hỏi retry có kiểm soát.

## 5. Chọn isolation level đúng ngữ cảnh

Các tên isolation level trong chuẩn SQL mô tả mức bảo vệ tối thiểu trước một số hiện tượng đọc. Hành vi thực tế của PostgreSQL, MySQL/InnoDB, SQL Server, Oracle… khác nhau ở snapshot, khóa, cách xử lý cập nhật đồng thời và hiện tượng bổ sung như write skew.

| Isolation level | Ý nghĩa chung | Cần thận trọng |
|---|---|---|
| `READ UNCOMMITTED` | Có thể cho phép quan sát dữ liệu chưa commit theo mô hình chuẩn | Không nên dùng nếu quyết định cần dữ liệu đã xác nhận; PostgreSQL xử lý tên mức này như `READ COMMITTED` |
| `READ COMMITTED` | Mỗi lần đọc chỉ thấy dữ liệu đã commit theo quy tắc engine | Có thể đọc kết quả khác nhau ở các câu lệnh; chuỗi read–check–write dễ đua |
| `REPEATABLE READ` | Bảo vệ các lần đọc lại hàng theo yêu cầu chuẩn; nhiều engine dùng snapshot nhất quán | Không được mặc định ngăn mọi phantom/write skew trong mọi engine |
| `SERIALIZABLE` | Các transaction đã commit có hiệu ứng tương đương một lịch tuần tự | Có thể chờ, thất bại và cần retry; chi phí và hiện thực khác nhau theo engine |

Một số lưu ý quan trọng:

- Theo bảng hiện tượng cổ điển của chuẩn SQL, `REPEATABLE READ` không nhất thiết chặn mọi phantom; **PostgreSQL Repeatable Read** thực tế dùng snapshot nên tránh được phantom trong các lần đọc thông thường, nhưng vẫn có thể có write skew.
- **Serializable** không biến các câu lệnh sai nghiệp vụ thành đúng; nó chỉ áp đặt tính tương đương tuần tự. Nếu một transaction đơn lẻ vốn cho phép số dư âm, isolation mạnh không sửa lỗi đó.
- Không phải mọi tác vụ đều cần `SERIALIZABLE`. Một phép trừ tồn kho trên cùng hàng có thể được bảo vệ hiệu quả bằng **một câu `UPDATE` có điều kiện** ở `READ COMMITTED`.
- Việc đọc từ **read replica** có độ trễ hoặc kết hợp nhiều dịch vụ bên ngoài vượt khỏi phạm vi isolation của một transaction trên một database. Phải xem xét tính nhất quán từ đầu đến cuối.

Nguyên tắc lựa chọn: xác định tập hàng mà quyết định phụ thuộc vào, thao tác ghi có thực sự kiểm tra điều kiện tại thời điểm ghi hay không, và mức độ xung đột dự kiến. Từ đó mới chọn isolation level, ràng buộc và chiến lược khóa.

## 6. Các mẫu SQL giữ tính đúng đắn

Các ví dụ dưới đây dùng cú pháp **PostgreSQL** để minh họa. `:product_id`, `:qty` và các tên bắt đầu bằng dấu hai chấm là **tham số do ứng dụng bind**, không phải giá trị SQL có thể chạy nguyên văn trong `psql`.

### 6.1. Bán hàng: gộp kiểm tra và trừ kho thành một thao tác

Giả sử có bảng:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0)
);

CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    product_id BIGINT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

Cách dễ sai là:

~~~text
SELECT stock
-> ứng dụng kiểm tra stock >= qty
-> INSERT order
-> UPDATE products SET stock = giá_trị_đã_tính
~~~

Hai transaction có thể cùng đọc lượng kho còn lại trước khi bất kỳ transaction nào ghi. Cách gọn và an toàn hơn cho trường hợp một sản phẩm là:

~~~sql
BEGIN;

UPDATE products
SET stock = stock - :qty
WHERE id = :product_id
  AND stock >= :qty
RETURNING id, stock;

-- Chỉ tiếp tục khi UPDATE trả đúng một hàng.
-- Nếu không có hàng: ROLLBACK và báo hết hàng/không tìm thấy sản phẩm.

INSERT INTO orders (request_key, product_id, quantity)
VALUES (:request_key, :product_id, :qty);

COMMIT;
~~~

Tại sao cách này hiệu quả?

- Điều kiện `stock >= :qty` được đánh giá gắn với chính câu lệnh cập nhật. Các cập nhật cạnh tranh trên cùng hàng được engine điều phối; transaction sau không thể trừ dựa vào cùng một lượng kho cũ mà bỏ qua điều kiện tại thời điểm ghi.
- Ràng buộc `CHECK (stock >= 0)` là thêm một lớp bảo vệ dữ liệu.
- `INSERT orders` và `UPDATE products` thuộc **cùng transaction**: nếu tạo đơn thất bại, việc trừ kho được rollback.
- `UNIQUE (request_key)` giúp không lưu trùng cùng một yêu cầu nghiệp vụ.

**Điểm dễ bỏ sót:** nếu trùng `request_key`, không được dùng `INSERT ... ON CONFLICT DO NOTHING` rồi vẫn commit sau khi đã trừ kho; cách đó có thể trừ kho hai lần cho một yêu cầu. Phải rollback hoặc thiết kế quy trình idempotent rõ ràng, sau đó đọc lại đơn cũ để trả kết quả tương ứng. Trước khi cập nhật, ứng dụng cũng phải kiểm tra `qty > 0`; schema `orders` ở trên chỉ chặn giá trị sai khi insert.

### 6.2. Khi cần logic quyết định phức tạp: khóa hàng có chủ đích

Nếu việc xử lý phải đọc nhiều cột của cùng hàng, tính toán điều kiện và cập nhật dựa trên chúng, có thể dùng:

~~~sql
BEGIN;

SELECT stock, reserved_stock
FROM inventory
WHERE product_id = :product_id
FOR UPDATE;

-- Tính số lượng còn khả dụng và quyết định dựa trên hàng đã khóa.
UPDATE inventory
SET reserved_stock = reserved_stock + :qty
WHERE product_id = :product_id;

COMMIT;
~~~

Cách này hữu ích khi toàn bộ quyết định phụ thuộc vào hàng được khóa. Nhưng nếu “còn khả dụng” lại phụ thuộc vào **nhiều hàng khác**, chỉ khóa một hàng chưa chắc bảo vệ đầy đủ quy tắc. Cần xác định chính xác tập dữ liệu mà mọi transaction cạnh tranh đều phải phối hợp qua cùng khóa hoặc ràng buộc.

### 6.3. Optimistic locking cho form cập nhật dữ liệu

Một người mở màn hình chỉnh sửa với `version = 5`. Trong lúc đó, người khác đã lưu phiên bản 6. Khi người thứ nhất nhấn Lưu:

~~~sql
UPDATE documents
SET title = :new_title,
    body = :new_body,
    version = version + 1
WHERE id = :document_id
  AND version = :expected_version;
~~~

Nếu `affected_rows = 0`, ứng dụng nên báo dữ liệu đã thay đổi, tải lại để đối chiếu hoặc hợp nhất có chủ đích. Không nên âm thầm ghi đè công sức của người vừa lưu.

Version check phù hợp với xung đột cập nhật một thực thể. Nó **không tự ngăn write skew** khi hai transaction sửa hai thực thể khác nhau để cùng phá vỡ một bất biến liên thực thể.

### 6.4. Chuyển tiền: nguyên tử, thứ tự khóa và kiểm tra điều kiện

Giả sử chuyển `amount` từ tài khoản `from_id` sang `to_id`. Hai cập nhật phải nằm trong **một transaction**; tài khoản nguồn cần đủ tiền, và hệ thống phải tránh việc hai lần chuyển cạnh tranh cùng tiêu số dư.

Một phương án đơn giản là khóa cả hai hàng **theo thứ tự ID tăng dần**, rồi kiểm tra số dư đã khóa:

~~~sql
BEGIN;

-- Ứng dụng sắp xếp hai ID tăng dần, sau đó lần lượt:
SELECT id, balance FROM accounts WHERE id = :smaller_id FOR UPDATE;
SELECT id, balance FROM accounts WHERE id = :larger_id FOR UPDATE;

-- Yêu cầu from_id khác to_id, amount > 0.
-- Bảo đảm đã tìm thấy đủ hai hàng; từ dữ liệu đã khóa kiểm tra nguồn đủ tiền.

UPDATE accounts
SET balance = balance - :amount
WHERE id = :from_id;

UPDATE accounts
SET balance = balance + :amount
WHERE id = :to_id;

COMMIT;
~~~

Nếu không đủ tiền, thiếu tài khoản hoặc phát sinh lỗi, transaction rollback. Có thể thêm `CHECK (balance >= 0)` khi chính sách không cho thấu chi. Phải dùng kiểu số chính xác như `NUMERIC` hoặc đơn vị tiền nguyên nhỏ nhất, tránh sai số làm tròn từ floating point.

Đối với chuyển khoản thực tế còn cần mã yêu cầu idempotent, sổ cái/audit và kiểm soát side effect. Ví dụ trên minh họa phần phối hợp transaction trong một database, chưa phải thiết kế hệ thống thanh toán hoàn chỉnh.

### 6.5. Bất biến trên nhiều hàng: khóa một điểm phối hợp hoặc SERIALIZABLE

Quay lại ví dụ hai bác sĩ cùng xin nghỉ. Khóa riêng hàng bác sĩ A hoặc B không tạo ra xung đột vì hai transaction sửa hàng khác nhau. Có thể thiết kế bảng `shifts`, yêu cầu **mọi yêu cầu thay đổi nhân sự một ca phải khóa cùng hàng `shifts.id`** trước khi đếm số người trực và cập nhật. Khi đó, thao tác quyết định trên cùng ca được tuần tự hóa.

Một phương án khác là dùng `SERIALIZABLE` cho toàn bộ thao tác **đọc số người trực → kiểm tra → cho nghỉ → commit**, rồi retry toàn bộ transaction khi database báo serialization failure. Cần kiểm tra chính xác khả năng phát hiện xung đột và chiến lược retry của engine sử dụng.

**Ràng buộc khai báo vẫn được ưu tiên** nếu biểu diễn được bất biến: `UNIQUE` cho mã duy nhất, `FOREIGN KEY` cho tham chiếu, `CHECK` cho giá trị một hàng và ràng buộc loại trừ phù hợp (ví dụ PostgreSQL exclusion constraint cho các khoảng thời gian chồng lấn). Chúng thường đáng tin cậy hơn một đoạn kiểm tra rời rạc ở ứng dụng.

## 7. Retry, timeout và idempotency

### 7.1. Những trường hợp cần retry

Một hệ thống kiểm soát đồng thời tốt cần dự kiến transaction có thể thất bại dù dữ liệu đầu vào hợp lệ:

- **Serialization failure:** PostgreSQL thường báo SQLSTATE `40001`.
- **Deadlock:** PostgreSQL thường báo SQLSTATE `40P01`.
- **Optimistic version conflict:** `UPDATE` không sửa hàng nào vì version đã thay đổi.
- **Lock timeout:** transaction không thể chờ lâu hơn chính sách cho phép.

Không phải lỗi nào cũng retry được. Ví dụ dữ liệu nhập sai, không đủ số dư thực sự hoặc vi phạm quy tắc nghiệp vụ cần trả lỗi đúng nghĩa. Vi phạm `UNIQUE` có thể là yêu cầu trùng; cần tra cứu theo `request_key`, không retry mù quáng.

### 7.2. Retry toàn bộ quyết định, không chỉ câu SQL cuối

Khi transaction bị hủy do xung đột, kết quả đọc trước đó có thể đã lỗi thời. Vì vậy cần **bắt đầu transaction mới, đọc lại, kiểm tra lại bất biến và thực hiện lại toàn bộ logic**.

~~~text
attempt = 1..MAX_ATTEMPTS
    bắt đầu transaction
    đọc trạng thái cần thiết
    kiểm tra điều kiện nghiệp vụ
    cập nhật, ghi dữ liệu liên quan
    commit

    nếu serialization failure / deadlock có thể retry:
        rollback (nếu cần)
        chờ một khoảng nhỏ có jitter
        chạy lại từ đầu trên transaction mới
    nếu lỗi nghiệp vụ:
        trả kết quả phù hợp
    nếu quá số lần retry:
        trả lỗi có kiểm soát và ghi log/metric
~~~

Giới hạn số lần thử và dùng backoff ngắn có jitter để tránh nhiều client liên tục va chạm cùng một điểm nóng. Không thực hiện retry vô hạn trong request web.

Trong ứng dụng Spring, `@Transactional` xác định ranh giới giao dịch thông qua transaction manager, nhưng **retry cần bao quanh một lần gọi có transaction mới**, thay vì chạy vòng lặp ở bên trong transaction đã bị đánh dấu rollback. Cần xem thêm cấu hình rollback của các loại exception và ngoại lệ database cụ thể.

### 7.3. Side effect và bài toán “đã commit nhưng client không biết”

Một client có thể timeout ngay sau khi database commit thành công. Nếu client gửi lại yêu cầu, transaction mới có thể tạo đơn/chuyển tiền lần nữa nếu thiếu **idempotency key**.

Để chống xử lý trùng:

1. Gán một `request_key` ổn định cho cùng một thao tác nghiệp vụ.
2. Áp dụng ràng buộc duy nhất trong database và lưu trạng thái/kết quả liên quan.
3. Khi nhận lại cùng khóa, trả kết quả đã xử lý hoặc trạng thái đang xử lý, sau khi xác minh các tham số không mâu thuẫn.
4. Đảm bảo mọi cập nhật nghiệp vụ và việc ghi dấu xử lý cùng nằm trong transaction phù hợp.

Nếu cần phát sự kiện sau commit, có thể dùng **transactional outbox**: ghi thay đổi dữ liệu và bản ghi sự kiện vào cùng database transaction, sau đó một tiến trình khác phát sự kiện và xử lý gửi lặp theo cơ chế idempotent. Không gọi thanh toán bên ngoài hoặc gửi email rồi mặc định rằng rollback của database sẽ hoàn tác hành động bên ngoài đó.

## 8. Vì sao bảo vệ đúng đắn có thể làm giảm hiệu năng?

### 8.1. Độ tranh chấp quyết định mức song song hữu ích

Nếu hai giao dịch cập nhật hai hàng độc lập, nhiều engine có thể tiến hành chúng khá đồng thời. Nếu hàng nghìn giao dịch đều muốn cập nhật đúng một hàng tồn kho, tài khoản hoặc bộ đếm, nhiều thao tác sẽ phải chờ hoặc retry.

~~~text
Ít cạnh tranh:
T1: cập nhật hàng A ---- COMMIT
T2: cập nhật hàng B ---- COMMIT
T3: cập nhật hàng C ---- COMMIT

Cùng điểm nóng:
T1: khóa X -> cập nhật -> COMMIT
T2:       chờ X --------> khóa X -> COMMIT
T3:       chờ X ------------------> khóa X -> COMMIT
~~~

Khi mức tranh chấp tăng, thêm worker hoặc tăng connection pool không chắc làm throughput tăng. Nhiều kết nối hơn có thể chỉ tạo hàng chờ dài hơn, đẩy p95/p99 lên cao và tăng tỉ lệ timeout.

### 8.2. Các nguồn chi phí thường gặp

| Nguồn chi phí | Biểu hiện | Điều tra và hướng xử lý |
|---|---|---|
| Chờ khóa | Query chậm dù CPU không cao | Xác định transaction giữ khóa và rút ngắn thời gian giữ |
| Deadlock | Transaction bị hủy theo đợt | Giữ thứ tự khóa nhất quán, giảm phạm vi khóa |
| Retry quá nhiều | CPU/DB load tăng nhưng commit thấp | Đo conflict rate, giảm điểm nóng hoặc thay chiến lược |
| Transaction dài | Phiên bản cũ lưu lâu, khóa tồn tại lâu | Tách tác vụ không cần nằm trong transaction, commit sớm |
| Quét dữ liệu lớn | Cập nhật/khóa nhiều hàng hơn dự kiến | Kiểm tra execution plan và index đúng điều kiện lọc |
| Điểm nóng một hàng | Throughput bão hòa khi thêm client | Thiết kế lại phân bổ công việc khi bất biến cho phép |
| Pool kết nối quá lớn | Nhiều session chờ nhau, đuôi độ trễ tăng | Giới hạn concurrency theo năng lực DB, đo queue wait |
| Tác vụ ngoài DB trong transaction | Khóa bị giữ trong lúc gọi API/file/network | Đưa tác vụ ngoài ra sau commit hoặc dùng outbox |

Một index phù hợp có thể giúp truy vấn tìm đúng hàng nhanh hơn và giảm thời gian xử lý. Tuy nhiên, index cũng làm tăng chi phí cập nhật và không thay thế được khóa/ràng buộc đúng. Không tối ưu bằng cách thêm index hoặc giảm isolation một cách máy móc.

### 8.3. Tối ưu theo thứ tự

**Bước 1 — Thu hẹp ranh giới transaction.** Chỉ giữ trong transaction những đọc/ghi cần cùng một quyết định nhất quán; tránh truy vấn chậm, tính toán dài hoặc gọi dịch vụ bên ngoài giữa `BEGIN` và `COMMIT`.

**Bước 2 — Thu hẹp phạm vi dữ liệu cạnh tranh.** Dùng điều kiện `WHERE` có index, cập nhật đúng hàng cần thiết, tránh khóa cả tập quá rộng. Nếu nghiệp vụ cho phép, phân tách workload theo tenant, kho, tài khoản hoặc shard.

**Bước 3 — Dùng một câu SQL nguyên tử khi đủ.** `UPDATE ... SET stock = stock - n WHERE stock >= n` thường gọn hơn chuỗi “SELECT rồi UPDATE”, giảm round trip và cửa sổ xung đột.

**Bước 4 — Chọn chiến lược dựa trên mức tranh chấp.** Ít xung đột và người dùng sửa dữ liệu lâu: version check thường hợp lý. Xung đột cao và quyết định ngắn: khóa có chủ đích hoặc atomic update có thể ít lãng phí retry hơn.

**Bước 5 — Đo dưới tải thực tế.** So sánh throughput, latency, retry/abort rate và tỉ lệ vi phạm bất biến. Không đánh đổi tính đúng đắn bằng việc chỉ đo số request thành công HTTP.

### 8.4. Các chỉ số cần quan sát

- **Throughput:** số business transaction thực sự commit thành công trên giây, tách khỏi số request và số retry.
- **Latency:** p50, p95, p99 cho toàn bộ thao tác và thời gian ở database; phân biệt thời gian chạy SQL với thời gian chờ khóa.
- **Lock wait:** số lượt chờ, thời gian chờ, transaction chặn nhiều giao dịch khác.
- **Deadlock / serialization abort:** số lượng và tỉ lệ theo loại nghiệp vụ, xu hướng theo tải.
- **Retry rate:** số lần retry trên một yêu cầu thành công; số yêu cầu hết retry budget.
- **Database resources:** CPU, I/O, buffer/cache, số kết nối hoạt động và hàng chờ connection pool.
- **Data correctness:** các chỉ số nghiệp vụ như số đơn vượt tồn kho, số request trùng, bất biến bị vi phạm.

Với PostgreSQL, có thể bắt đầu bằng những truy vấn chẩn đoán minh họa:

~~~sql
-- Tìm session đang chờ tài nguyên kiểu Lock tại thời điểm quan sát.
SELECT pid, state, wait_event_type, wait_event, query
FROM pg_stat_activity
WHERE wait_event_type = 'Lock';

-- Tổng số deadlock tích lũy theo database từ lần reset thống kê.
SELECT datname, deadlocks
FROM pg_stat_database;
~~~

Các số liệu này là dấu hiệu để điều tra, không tự chứng minh nguyên nhân. Cần kết hợp log, query plan, khoảng thời gian đo, phiên bản engine và cấu hình thực tế.

## 9. Kiểm thử tính đúng đắn dưới tải đồng thời

Kiểm thử một transaction riêng lẻ không thể chứng minh an toàn khi có cạnh tranh. Muốn tái hiện vấn đề, tạo các client chạy **cùng lúc với dữ liệu khởi tạo có chủ đích**.

### 9.1. Kiểm thử hai người mua sản phẩm cuối

**Chuẩn bị:** tạo sản phẩm có `stock = 1`, xóa các đơn thử nghiệm, dùng hai session kết nối độc lập. Cả hai gửi lệnh đặt cùng sản phẩm với `request_key` khác nhau.

**Đồng bộ:** dùng barrier trong test để hai yêu cầu bắt đầu gần nhau, hoặc tạm dừng có kiểm soát ngay sau bước đọc tại phiên bản cố ý chứa read–check–write; không dùng `sleep` ngẫu nhiên làm bằng chứng duy nhất.

**Kỳ vọng:** tổng số đơn **commit thành công** tối đa là một, và tồn kho còn 0. Transaction thất bại do thiếu hàng hoặc xung đột phải có kết quả rõ ràng; không phát sinh đơn “ma”.

**Mở rộng:** tăng lên hàng chục hoặc hàng trăm client, lặp nhiều lượt với dữ liệu độc lập. Kiểm tra bất biến sau khi toàn bộ transaction kết thúc, đồng thời đo retry, latency và lock wait.

### 9.2. Kiểm thử write skew

Khởi tạo hai bác sĩ đang trực. Chạy hai transaction đồng thời, mỗi transaction đọc số người đang trực trước khi một trong hai ghi; mỗi transaction cố tắt trạng thái của một bác sĩ khác nhau. Với chiến lược bảo vệ bất biến đã chọn, kết quả chấp nhận được là còn ít nhất một người trực; nếu có serialization failure, ứng dụng phải retry và kiểm tra lại thay vì commit cả hai.

### 9.3. Kiểm thử retry và mất phản hồi

- Ép một transaction gặp deadlock hoặc serialization failure có kiểm soát; xác nhận retry dùng **transaction mới** và có giới hạn.
- Gửi lại cùng `request_key` sau khi request đầu đã commit; xác nhận không nhân đôi đơn hàng hoặc chuyển tiền.
- Mô phỏng client timeout sau commit; xác nhận truy vấn theo request key có thể trả lại kết quả đã lưu.
- Nếu dùng outbox, mô phỏng phát cùng sự kiện nhiều lần và xác nhận consumer xử lý idempotent.

Kết quả test cần phân biệt ba trạng thái: transaction commit thành công, transaction bị rollback có chủ ý, và kết quả chưa rõ do mất kết nối. Trạng thái “client không nhận được trả lời” **không** suy ra rằng database đã rollback.

## 10. Quy trình ra quyết định khi thiết kế một thao tác đồng thời

Với mỗi use case, có thể đi qua chuỗi câu hỏi sau:

1. **Bất biến là gì?** Viết được thành điều kiện rõ ràng, ví dụ `stock >= 0` và “không chấp nhận quá số đơn có thể cấp phát”.
2. **Transaction đọc và ghi những gì?** Một hàng, nhiều hàng, một tập theo điều kiện, hay dữ liệu ở nhiều hệ thống?
3. **Nếu hai transaction cùng chạy, điều kiện nào có thể lỗi thời?** Dựng một lịch xen kẽ gồm T1/T2 cụ thể.
4. **Database có ràng buộc nào thực thi được không?** Ưu tiên `UNIQUE`, `CHECK`, khóa ngoại, exclusion constraint khi phù hợp.
5. **Có thể diễn đạt thao tác thành một SQL có điều kiện không?** Nếu có, thường là giải pháp đơn giản và hiệu quả cho cập nhật một hàng.
6. **Nếu phải kiểm tra nhiều hàng, những transaction cạnh tranh phối hợp qua đâu?** Cân nhắc khóa chung, thiết kế lại mô hình hoặc `SERIALIZABLE` với retry.
7. **Phải xử lý lỗi gì?** Thiếu điều kiện nghiệp vụ, optimistic conflict, deadlock, serialization failure, timeout, request trùng.
8. **Đã đo được hiệu quả chưa?** Kiểm thử cạnh tranh trên dữ liệu thật sự có xung đột, đo các chỉ số ở mục 8.

Bảng gợi ý nhanh:

| Tình huống | Hướng tiếp cận thường phù hợp | Cần tránh |
|---|---|---|
| Tăng bộ đếm cùng hàng | Atomic `UPDATE value = value + 1` | Đọc–tăng trong app–ghi giá trị cố định |
| Trừ tồn kho của một sản phẩm | `UPDATE` có điều kiện và kiểm tra số hàng ảnh hưởng | Đọc tồn kho trước rồi cập nhật không điều kiện |
| Người dùng cùng sửa một tài liệu | Optimistic `version` hoặc kiểm soát xung đột | Ghi đè âm thầm |
| Chuyển tiền giữa hai tài khoản trong một DB | Một transaction, khóa/điều kiện nhất quán, idempotency | Hai lần cập nhật độc lập, gửi lại không có mã yêu cầu |
| Bất biến trên tập hàng | Ràng buộc phù hợp; khóa điểm phối hợp; serializable + retry | Chỉ khóa hàng mà từng giao dịch sửa |
| Tác vụ có API ngoài DB | Transactional outbox hoặc orchestration có idempotency | Giả định DB rollback sẽ hủy side effect bên ngoài |
| Điểm nóng có tranh chấp cao | Đo lock wait/retry rồi giảm contention phù hợp bất biến | Tăng vô hạn worker/connection pool |

## 11. Tự kiểm tra mức độ hiểu

**Tình huống A.** Có hai giao dịch chạy `SELECT stock` thấy 5, sau đó mỗi giao dịch trừ 3 bằng `UPDATE products SET stock = 2`. Vì sao dữ liệu cuối là 2 vẫn có thể sai? Sửa như thế nào?

*Gợi ý:* Dữ liệu kho chỉ phản ánh một lần trừ, nhưng nghiệp vụ có thể đã chấp nhận hai đơn tổng cộng 6 sản phẩm. Gộp kiểm tra và trừ bằng một `UPDATE` có điều kiện trong cùng transaction tạo đơn.

**Tình huống B.** Một transaction đọc tổng số người trực là 2 và cho một người nghỉ. Một transaction khác làm điều tương tự với người còn lại. Vì sao optimistic version check **trên từng hàng bác sĩ** không đủ?

*Gợi ý:* Hai giao dịch cập nhật các hàng khác nhau nên không tạo xung đột phiên bản trên cùng hàng. Quy tắc “ít nhất một người trực” phụ thuộc vào cả tập hàng.

**Tình huống C.** Hệ thống không còn lost update nhưng p99 tăng mạnh khi lượng yêu cầu tăng gấp đôi. Nên xem chỉ số nào trước khi nâng cấu hình?

*Gợi ý:* Xem lock wait, số transaction đang chạy/chờ, thời gian transaction, retry/abort rate, điểm nóng theo hàng và mức sử dụng pool kết nối. Thêm tài nguyên chỉ có tác dụng nếu nút thắt thật sự nằm ở tài nguyên đó.

**Tình huống D.** Client gửi yêu cầu chuyển tiền và gặp timeout. Có nên gửi lại với một mã yêu cầu mới không?

*Gợi ý:* Không nên vì lần đầu có thể đã commit. Gửi lại hoặc truy vấn bằng **cùng idempotency key** để xác định kết quả, bảo đảm hệ thống không chuyển hai lần.

## 12. Ghi nhớ khi áp dụng

Tính đúng đắn của giao dịch đồng thời không đến từ một cài đặt isolation level đơn lẻ. Nó đến từ việc **xác định bất biến, gom các bước phụ thuộc vào cùng transaction, dùng ràng buộc và cơ chế điều phối phù hợp, rồi xử lý xung đột và retry chính xác**.

Hiệu năng cũng cần được hiểu từ dữ liệu thực: đọc bằng snapshot có thể giảm chờ, cập nhật nguyên tử giảm số lượt trao đổi, khóa đúng phạm vi bảo vệ quyết định nghiệp vụ, và transaction ngắn giúp giải phóng tài nguyên sớm. Khi nhiều giao dịch cạnh tranh trên một điểm nóng, hệ thống phải trả chi phí dưới dạng chờ, retry hoặc thay đổi thiết kế dữ liệu; chỉ tăng số kết nối không giải quyết được bản chất tranh chấp.

Một thiết kế có thể coi là đạt yêu cầu khi các lịch thực thi cạnh tranh vẫn giữ được bất biến, các lỗi có thể thử lại được xử lý có giới hạn và quan sát được, đồng thời throughput và độ trễ đáp ứng mục tiêu dưới tải thực tế.
