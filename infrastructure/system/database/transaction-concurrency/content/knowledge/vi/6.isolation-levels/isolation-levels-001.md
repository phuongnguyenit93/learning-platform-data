# Mục tiêu và cách diễn đạt bảo đảm của mức cô lập

Khi nhiều giao dịch (transaction) cùng đọc và ghi dữ liệu, hệ quản trị cơ sở dữ liệu (DBMS) phải quyết định mỗi giao dịch được phép quan sát những thay đổi nào và các thao tác đồng thời có thể ảnh hưởng lẫn nhau ra sao. **Mức cô lập (isolation level)** là cách diễn đạt hợp đồng về những lịch thực thi mà DBMS cho phép, hoặc những hiện tượng mà nó cam kết ngăn chặn.

Mục tiêu của isolation không phải lúc nào cũng là buộc mọi giao dịch chạy lần lượt. Một hệ thống tốt thường muốn cho phép nhiều công việc chạy đồng thời để tăng thông lượng, nhưng vẫn giữ những bảo đảm cần thiết cho nghiệp vụ. Vì vậy, khi nói một transaction chạy ở mức cô lập nào, cần hiểu rõ:

- Những gì transaction **được phép nhìn thấy** từ các transaction khác.
- Những kiểu thay đổi đồng thời nào có thể làm kết quả đọc khác đi.
- Những lịch thực thi nào DBMS phải ngăn chặn, phát hiện hoặc hủy.
- Bảo đảm đó áp dụng cho một câu lệnh, một transaction hay toàn bộ quy trình ứng dụng.
- Tên isolation level trong DBMS cụ thể được triển khai như thế nào.

**Mức cô lập là hợp đồng về khả năng quan sát và tương tác giữa các giao dịch.** Nó không tự định nghĩa quy tắc nghiệp vụ, không thay thế constraint và không tự làm một chuỗi gọi nhiều dịch vụ trở thành một transaction nguyên tử.

## 1. Vì sao cần mức cô lập?

Giả sử bảng tồn kho có một sản phẩm với `quantity = 5`. Hai giao dịch cùng muốn bán một sản phẩm cuối cùng trong một tình huống khác, khi tồn kho chỉ còn `1`.

Mỗi yêu cầu thực hiện ba bước:

1. Đọc số lượng hiện tại.
2. Kiểm tra số lượng có lớn hơn 0 không.
3. Trừ đi một và ghi lại.

Nếu cả hai giao dịch cùng đọc `1` trước khi bên nào ghi, cả hai có thể kết luận “còn hàng”. Nếu cách cập nhật cho phép cả hai ghi kết quả tính từ giá trị cũ, hệ thống có thể bán vượt tồn kho hoặc làm mất một lần cập nhật.

Một transaction chạy riêng lẻ có thể luôn đúng. Nhưng khi các thao tác của nhiều transaction xen kẽ, kết quả cuối cùng có thể không đúng với kỳ vọng. Mức cô lập giúp DBMS kiểm soát các tương tác này.

### 1.1. Ví dụ lịch thực thi

Một lịch đơn giản:

```text
Thời gian     T1 (mua hàng)                 T2 (mua hàng)
---------------------------------------------------------------
t1            BEGIN
t2            SELECT quantity -> 1
t3                                           BEGIN
t4                                           SELECT quantity -> 1
t5            UPDATE quantity = 0
t6                                           UPDATE quantity = 0
t7            COMMIT
t8                                           COMMIT
```

Chỉ nhìn trạng thái cuối `quantity = 0` có thể chưa phát hiện sai lệch. Nhưng hai đơn hàng đã được chấp nhận trong khi chỉ có một sản phẩm. Vì thế, đánh giá tính đúng đắn không chỉ là kiểm tra giá trị cuối của một cột; phải xem **các giao dịch đã đọc, quyết định và ghi như thế nào**.

Mức cô lập phù hợp có thể ngăn lịch không hợp lệ, nhưng ứng dụng vẫn phải sử dụng câu lệnh cập nhật đúng và kiểm tra số hàng được tác động. Ví dụ thao tác nguyên tử:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42
  AND quantity > 0;
```

Chỉ coi yêu cầu mua thành công khi số hàng cập nhật là `1`. Nếu `0` hàng bị ảnh hưởng, hàng có thể không tồn tại hoặc không còn đủ tồn kho. Câu lệnh điều kiện này bảo vệ một hàng tốt hơn mẫu đọc–tính–ghi tách rời, nhưng các thao tác tạo order và giữ chỗ vẫn cần ranh giới transaction phù hợp.

## 2. Mức cô lập bảo vệ điều gì?

Có thể chia mục tiêu thành ba nhóm.

### 2.1. Kiểm soát dữ liệu được phép nhìn thấy

Transaction không nên dựa trên một thay đổi chưa được xác nhận của transaction khác nếu isolation level cấm dirty read. Ví dụ, T1 sửa số dư thành 0 nhưng chưa commit; T2 đọc giá trị đó rồi quyết định từ chối giao dịch tiếp theo. Nếu T1 rollback, T2 đã ra quyết định dựa trên dữ liệu chưa từng trở thành trạng thái chính thức.

Mức cô lập cũng quy định một transaction có nhìn thấy các lần commit mới xuất hiện giữa những câu truy vấn của nó hay không. Có DBMS tạo snapshot mới ở từng câu lệnh; có mức cô lập giữ một snapshot ổn định cho cả transaction.

### 2.2. Kiểm soát tương tác ghi

Hai transaction có thể cùng sửa một hàng hoặc cùng sửa các hàng khác nhau nhưng phụ thuộc vào một điều kiện chung. DBMS có thể:

- Bắt transaction thứ hai chờ khóa.
- Phát hiện một cập nhật dựa trên phiên bản cũ và trả lỗi.
- Chọn một transaction làm nạn nhân của deadlock.
- Phát hiện lịch có nguy cơ không tuần tự hóa và hủy một transaction.
- Cho phép cả hai commit nếu lịch phù hợp với bảo đảm của isolation level.

Không phải mức cô lập nào cũng được thực thi chỉ bằng khóa. DBMS có thể dùng MVCC (Multi-Version Concurrency Control), phát hiện xung đột, predicate/range locking hoặc kết hợp cơ chế.

### 2.3. Bảo vệ khả năng suy luận về kết quả giao dịch

Một mức cô lập mạnh hơn có thể giúp ứng dụng lập luận rằng kết quả của các transaction tương đương với một thứ tự tuần tự hợp lệ. Tuy nhiên, “tương đương tuần tự” và “giữ đúng thứ tự thời gian thực giữa các request” là hai cam kết khác nhau. SQL `SERIALIZABLE` trong mô hình isolation không nên tự động được diễn giải thành strict serializability hoặc linearizability cho mọi endpoint.

## 3. Những hiện tượng dùng để mô tả isolation

Các hiện tượng sau thường được dùng để giải thích mức cô lập. Chúng mô tả **điều một transaction có thể quan sát**, không phải toàn bộ mọi lỗi logic có thể xảy ra.

### 3.1. Dirty read — đọc dữ liệu chưa commit

T1 ghi giá trị mới nhưng chưa commit; T2 đọc giá trị đó. Sau đó T1 rollback.

```text
T1: BEGIN
T1: UPDATE account SET balance = 0
                         |
T2:                     READ balance -> 0
                         |
T1: ROLLBACK
                         |
T2: sử dụng giá trị 0 đã đọc
```

T2 đã đọc một giá trị không bao giờ trở thành dữ liệu được xác nhận. Điều này có thể khiến báo cáo, quyết định hoặc logic nghiệp vụ sai.

### 3.2. Non-repeatable read — đọc cùng hàng nhưng thấy giá trị khác

T1 đọc một hàng. T2 sửa hàng đó và commit. T1 đọc lại cùng hàng và thấy giá trị mới.

```text
T1: BEGIN
T1: SELECT balance -> 100
T2:                 UPDATE balance = 80
T2:                 COMMIT
T1: SELECT balance -> 80
```

Hai lần đọc cùng một khóa chính có thể trả về hai giá trị khác nhau trong cùng transaction. Với một số nghiệp vụ, đó là điều chấp nhận được; với giao dịch cần tính toán dựa trên một snapshot nhất quán, có thể không.

### 3.3. Phantom read — tập hàng phù hợp điều kiện thay đổi

T1 truy vấn tất cả đơn hàng của khách có trạng thái `PENDING` và nhận ba hàng. T2 thêm một hàng mới thỏa điều kiện rồi commit. Khi T1 chạy lại cùng điều kiện, truy vấn có thể trả về bốn hàng.

```sql
-- T1, lần đọc thứ nhất
SELECT *
FROM orders
WHERE customer_id = 7
  AND status = 'PENDING';

-- T2
INSERT INTO orders(id, customer_id, status)
VALUES (900, 7, 'PENDING');
COMMIT;

-- T1, lần đọc thứ hai
SELECT *
FROM orders
WHERE customer_id = 7
  AND status = 'PENDING';
```

Phantom không nhất thiết là cùng một hàng bị sửa; đó có thể là hàng mới được chèn, hàng bị xóa hoặc hàng trở nên thỏa/không còn thỏa điều kiện tìm kiếm.

### 3.4. Lost update — một lần cập nhật bị ghi đè

Hai transaction đọc cùng giá trị `10`, mỗi bên tăng hoặc giảm dựa trên giá trị vừa đọc, rồi ghi lại kết quả. Một thay đổi có thể che mất thay đổi còn lại.

Lost update là hiện tượng thường gặp ở tầng ứng dụng khi đọc giá trị rồi tính toán rồi ghi đè; cách các DBMS xử lý nó ở từng isolation level có thể khác nhau. Không nên coi danh sách ba anomaly dirty/non-repeatable/phantom trong bảng SQL là danh sách đầy đủ mọi nguy cơ cập nhật.

### 3.5. Write skew — sửa các hàng khác nhau nhưng phá điều kiện chung

Giả sử luôn phải có ít nhất một nhân viên trực. Hai transaction cùng đọc thấy nhân viên A và B đều trực; T1 cho A nghỉ, T2 cho B nghỉ. Vì hai transaction cập nhật hai hàng khác nhau, snapshot isolation có thể cho phép cả hai commit trong một số DBMS, khiến không còn ai trực.

Write skew minh họa rằng **snapshot ổn định không tự đồng nghĩa với serializable**. Muốn bảo vệ quy tắc trên nhiều hàng, cần constraint hoặc cơ chế phối hợp phù hợp, chẳng hạn serializable kèm retry hoặc một hàng điều phối chung được khóa.

### 3.6. Bảng tóm tắt

| Hiện tượng | Tình huống chính | Câu hỏi cần đặt ra |
|---|---|---|
| Dirty read | Đọc thay đổi chưa commit | Giá trị có thể bị rollback sau khi mình đọc không? |
| Non-repeatable read | Cùng một hàng thay đổi giữa hai lần đọc | Transaction có cần nhìn cùng một giá trị ở mọi lần đọc không? |
| Phantom read | Tập hàng theo điều kiện thay đổi | Transaction có cần giữ nguyên tập kết quả theo một predicate không? |
| Lost update | Một ghi đè tác dụng của ghi khác | Các lần cập nhật có được cộng dồn hoặc phát hiện xung đột không? |
| Write skew | Ghi các hàng khác nhau phá quy tắc chung | Điều kiện nhiều hàng có được bảo vệ như một đơn vị không? |

## 4. Bốn mức cô lập quen thuộc trong SQL

SQL định nghĩa bốn mức phổ biến: `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE`. Bảng dưới thể hiện mô hình anomaly kinh điển thường được dùng để diễn đạt mức bảo đảm.

| Isolation level | Dirty read | Non-repeatable read | Phantom read | Đặc điểm khái quát |
|---|---|---|---|---|
| `READ UNCOMMITTED` | Có thể | Có thể | Có thể | Cho phép quan sát dữ liệu chưa commit trong mô hình chuẩn. |
| `READ COMMITTED` | Ngăn | Có thể | Có thể | Chỉ đọc dữ liệu đã commit tại snapshot/thời điểm của câu lệnh. |
| `REPEATABLE READ` | Ngăn | Ngăn | Có thể theo mô hình chuẩn | Giữ khả năng đọc lặp lại ổn định đối với các hàng đã đọc. |
| `SERIALIZABLE` | Ngăn | Ngăn | Ngăn | Kết quả transaction phải tương đương một thứ tự tuần tự hợp lệ. |

Cần hiểu bảng này như **hợp đồng ở mức khái niệm của chuẩn**, không phải lời mô tả đầy đủ mọi DBMS. Một hệ quản trị có thể cung cấp bảo đảm mạnh hơn tối thiểu; tên cùng mức cô lập giữa sản phẩm cũng không bảo đảm cách triển khai giống hệt.

### 4.1. READ UNCOMMITTED

Đây là mức bảo đảm thấp nhất trong bốn mức. Trong mô hình chuẩn, transaction có thể đọc thay đổi chưa được transaction khác commit, do đó có nguy cơ dirty read.

Một ứng dụng dùng mức này phải chấp nhận rằng giá trị đọc có thể biến mất sau khi transaction nguồn rollback. Với dữ liệu tài chính, kho hàng, đặt chỗ hay trạng thái đơn hàng, dựa vào dirty read thường không phù hợp.

Một số DBMS không thực sự cung cấp dirty read dù nhận tên `READ UNCOMMITTED`. Ví dụ PostgreSQL xử lý yêu cầu này tương đương `READ COMMITTED`; InnoDB cũng có những khác biệt và điều kiện riêng. Vì vậy không nên suy ra “đặt READ UNCOMMITTED chắc chắn đọc được uncommitted data” mà chưa kiểm tra DBMS.

### 4.2. READ COMMITTED

Transaction chỉ nhìn thấy dữ liệu đã commit theo quy tắc snapshot của mức này. Tuy nhiên, hai câu truy vấn trong cùng transaction có thể quan sát hai trạng thái khác nhau nếu transaction khác commit ở giữa.

Ví dụ trên PostgreSQL, `READ COMMITTED` thường tạo snapshot cho từng câu lệnh. Nếu T1 đọc số dư là 100, T2 cập nhật và commit thành 80, câu đọc tiếp theo của T1 có thể thấy 80.

Mức này thường là mặc định ở nhiều DBMS (nhưng phải xác minh), cân bằng giữa khả năng đồng thời và tính nhất quán cho mỗi câu truy vấn. Nó không giữ một snapshot cố định của toàn bộ transaction.

### 4.3. REPEATABLE READ

Ý tưởng là nếu transaction đã đọc một hàng, lần đọc lại cùng hàng sẽ không thấy nó thay đổi do transaction khác theo cách mà mức này cấm. Nhiều triển khai dùng snapshot ổn định cho transaction.

Nhưng **không được khẳng định mọi DBMS ở REPEATABLE READ đều xử lý phantom giống nhau**. Theo mô hình SQL cổ điển, phantom có thể vẫn xảy ra. PostgreSQL `REPEATABLE READ` dựa trên snapshot isolation và ngăn phantom trong những truy vấn thông thường, nhưng vẫn có thể có write skew và không đồng nghĩa serializable.

InnoDB có thể dùng next-key/gap locks cho một số locking read và truy vấn theo chỉ mục tùy cấu hình; consistent read thông thường lại có semantics snapshot khác. Cần xem đúng kiểu truy vấn, index và DBMS.

### 4.4. SERIALIZABLE

Mục tiêu là kết quả của các transaction đã commit phải tương đương một thứ tự thực hiện tuần tự hợp lệ. DBMS có thể cho transaction chờ khóa, phát hiện phụ thuộc nguy hiểm rồi hủy một transaction, hoặc dùng chiến lược khác.

Ứng dụng phải xử lý lỗi serialization/deadlock thích hợp và có thể cần thử lại **toàn bộ transaction** với dữ liệu mới. `SERIALIZABLE` không có nghĩa mọi request chạy vật lý lần lượt từ đầu đến cuối.

Nó cũng không tự bảo vệ quy tắc chưa được đưa vào logic. Một transaction serializable vẫn có thể ghi số dư âm nếu đó là kết quả của một logic hợp lệ theo những constraint hiện có.

## 5. Mức cô lập là hợp đồng, không chỉ là tên cấu hình

Khi đọc một tuyên bố như “transaction chạy ở mức REPEATABLE READ”, hãy chuyển nó thành những câu hỏi quan sát được:

- Một transaction có thể nhìn thấy dữ liệu chưa commit của transaction khác không?
- Hai câu đọc giống nhau trong cùng transaction có bắt buộc trả cùng giá trị không?
- Tập hàng khớp điều kiện có thể thay đổi do transaction khác insert/delete/update không?
- Hai transaction cùng ghi một hàng thì giao dịch nào chờ, lỗi hay thành công?
- Một transaction đọc nhiều hàng và ghi các hàng khác nhau có thể gây write skew không?
- Khi xung đột, DBMS có block, trả lỗi, rollback transaction hay cho cả hai commit?
- Bảo đảm có áp dụng cho đọc ở replica, cache hoặc endpoint stale-read không?

Đây là cách diễn đạt bằng **hành vi có thể kiểm chứng**. Nó giúp tránh hiểu nhầm mức cô lập dựa trên tên gọi, đặc biệt khi hệ thống hỗ trợ nhiều chế độ snapshot, đọc từ replica hoặc một cấu hình đặc thù.

### 5.1. Phân biệt snapshot theo câu lệnh và snapshot theo transaction

Hai mô hình thường gặp:

```text
READ COMMITTED (ví dụ PostgreSQL):
  T1 bắt đầu
  SELECT lần 1 -> snapshot S1
  T2 cập nhật và COMMIT
  SELECT lần 2 -> snapshot S2, có thể thấy bản mới

Transaction snapshot (ví dụ PostgreSQL REPEATABLE READ):
  T1 bắt đầu
  SELECT lần 1 -> snapshot S
  T2 cập nhật và COMMIT
  SELECT lần 2 -> vẫn đọc theo snapshot S
```

Trong ví dụ, snapshot transaction có thể đã được thiết lập ở lần truy vấn đầu tiên, không nhất thiết ngay tại `BEGIN`. Chi tiết thời điểm tạo snapshot phụ thuộc DBMS.

Snapshot ổn định giúp báo cáo nhiều truy vấn có thể dùng cùng một góc nhìn dữ liệu. Nhưng nó không có nghĩa snapshot là dữ liệu mới nhất tại mọi thời điểm, và cũng không tự bảo vệ tất cả quy tắc giữa nhiều hàng.

### 5.2. “Đọc nhất quán” và “đọc mới nhất” là hai yêu cầu khác nhau

Một snapshot có thể nhất quán nhưng đã cũ. Ví dụ transaction T1 bắt đầu đọc trước khi T2 commit; T1 giữ snapshot cũ đến cuối transaction. Đây có thể là hành vi đúng theo mức cô lập.

Nếu nghiệp vụ cần “sau khi nhận xác nhận thanh toán, yêu cầu đọc mới bắt đầu phải thấy PAID”, cần đảm bảo đường đọc có consistency phù hợp. Chọn transaction snapshot dài không tự đáp ứng yêu cầu này.

Trong hệ thống phân tán, cần phân biệt:

- Đọc trên primary hay replica.
- Replica đồng bộ hay bất đồng bộ.
- Endpoint có cho phép stale read không.
- Cache có invalidation/read-your-writes hay không.
- Cam kết isolation áp dụng trên một transaction hay xuyên nhiều request.

## 6. Mục tiêu của mức cô lập và sự đánh đổi

Không có một mức cô lập duy nhất tối ưu cho mọi truy vấn. Mức bảo đảm cao hơn thường giảm tập lịch được phép, có thể làm giảm khả năng đồng thời hoặc làm tăng số transaction phải chờ/hủy.

| Mục tiêu | Lợi ích | Chi phí hoặc giới hạn có thể gặp |
|---|---|---|
| Cho phép đọc nhanh, ít chặn ghi | Tăng khả năng đồng thời với MVCC | Có thể quan sát snapshot cũ hoặc các câu truy vấn thấy trạng thái khác nhau. |
| Ngăn dirty read | Không dựa trên dữ liệu chưa commit | Không tự ngăn non-repeatable read, phantom hay write skew. |
| Giữ snapshot ổn định | Nhiều câu truy vấn nhìn một trạng thái nhất quán | Phiên bản cũ có thể được giữ lâu; transaction dài gây áp lực dọn dẹp. |
| Bảo đảm serializable | Loại lịch không tương đương thứ tự tuần tự | Có thể block hoặc hủy transaction; cần retry và đo hiệu năng. |
| Giữ thứ tự thời gian thực | Client sau khi nhận xác nhận có thể dựa vào kết quả trước đó trong phạm vi cam kết | Phân tán nhiều node thường cần phối hợp mạnh hơn, có thể tăng latency và giảm availability khi mạng có sự cố. |

Cần đo tải thật thay vì suy đoán “SERIALIZABLE luôn chậm” hoặc “READ COMMITTED luôn nhanh”. Một workload ít tranh chấp có thể chạy serializable hiệu quả; một workload khóa bảng ở read committed vẫn có thể rất chậm.

### 6.1. Isolation không chỉ là chọn cao nhất

Chọn mức cao nhất mà không có thiết kế lỗi và retry phù hợp có thể làm ứng dụng thất bại khi xung đột tăng. Ngược lại, chọn thấp chỉ vì thông lượng có thể khiến quy tắc nhiều hàng bị vi phạm.

Quy trình hợp lý là:

1. Viết rõ bất biến nghiệp vụ.
2. Xác định transaction nào cùng đọc/ghi dữ liệu liên quan.
3. Chọn bảo đảm tối thiểu đủ giữ bất biến.
4. Dùng constraint, SQL nguyên tử, khóa hoặc kiểm soát phiên bản để thu hẹp xung đột.
5. Đo chờ khóa, deadlock, serialization failure và latency.
6. Điều chỉnh khi có bằng chứng workload yêu cầu.

## 7. Phân biệt isolation với consistency, durability và các khái niệm liên quan

### 7.1. Isolation và Consistency trong ACID

**Consistency** nói rằng transaction hợp lệ phải chuyển database từ trạng thái thỏa các ràng buộc sang trạng thái tiếp tục thỏa các ràng buộc. **Isolation** nói về tương tác giữa các transaction đồng thời.

Ví dụ `CHECK (balance >= 0)` bảo vệ một ràng buộc trên hàng. Nhưng hai transaction có thể cùng kiểm tra một điều kiện nhiều hàng rồi cập nhật khác nhau. Khi đó isolation phù hợp có thể cần thiết ngoài constraint đơn hàng.

Không nên hiểu “Consistency trong ACID” là một isolation level hoặc một thuật toán tự động kiểm tra mọi quy tắc nghiệp vụ.

### 7.2. Isolation và Durability

Durability bảo vệ thay đổi đã commit theo cam kết lưu trữ/phục hồi của DBMS. Isolation bảo vệ cách giao dịch tương tác trước và trong lúc commit. Một dữ liệu sai nghiệp vụ nhưng đã commit vẫn có thể được lưu bền vững; durability không biến kết quả sai thành đúng.

### 7.3. Isolation và serializability

Serializability là một mục tiêu lý thuyết mạnh: lịch giao dịch tương đương một thứ tự tuần tự. SQL `SERIALIZABLE` là một mức cô lập hướng đến bảo đảm đó, nhưng triển khai cụ thể có thể có thêm chi tiết về thời gian thực, snapshot, read-only transaction và đường đọc replica.

### 7.4. Isolation và strict serializability

Strict serializability còn yêu cầu thứ tự tuần tự giữ quan hệ thời gian thực giữa các giao dịch không chồng lấn. Một hệ thống chỉ hứa serializability không tự động hứa rằng một request đọc bắt đầu sau response commit sẽ nhìn thấy phiên bản vừa ghi. Đây là điểm cần xác định trong API của hệ phân tán.

### 7.5. Isolation và locking/MVCC

Khóa và MVCC là **cơ chế triển khai**, còn isolation level là **hợp đồng hành vi**. Cùng một hợp đồng có thể được thực thi bằng các cơ chế khác nhau. Một DBMS dùng MVCC vẫn có khóa cho update, locking read và DDL; “MVCC” không có nghĩa “không khóa”.

## 8. Chọn mức cô lập theo loại nghiệp vụ

| Nghiệp vụ | Yêu cầu cần bảo vệ | Hướng thiết kế |
|---|---|---|
| Xem trang danh sách, dữ liệu có thể cập nhật trong lúc xem | Đọc dữ liệu đã commit, chấp nhận kết quả mỗi query có thể mới hơn | `READ COMMITTED` thường là điểm bắt đầu hợp lý, tùy DBMS. |
| Báo cáo tổng hợp cần nhất quán qua nhiều truy vấn | Một snapshot chung để các phép tính không trộn trạng thái khác thời điểm | Transaction snapshot/`REPEATABLE READ` hoặc cơ chế snapshot phù hợp. |
| Trừ tồn kho một sản phẩm | Không bán khi số lượng không đủ | Cập nhật nguyên tử có điều kiện và constraint; kiểm tra số hàng ảnh hưởng. |
| Chuyển tiền giữa hai tài khoản | Hai cập nhật cùng thành công hoặc cùng thất bại, kiểm tra số dư | Một transaction cho cả hai, điều kiện trên tài khoản nguồn, khóa/kiểm soát xung đột và constraint phù hợp. |
| Đặt ghế theo điều kiện không trùng | Không cho hai yêu cầu cùng chiếm một ghế | UNIQUE constraint trên định danh ghế/trạng thái phù hợp, transaction và xử lý conflict. |
| Bảo vệ “ít nhất một người trực” trên nhiều hàng | Ngăn write skew | `SERIALIZABLE` với retry hoặc khóa chung, thêm constraint nếu mô hình hóa được. |
| Quyết định theo lịch sử nhiều thao tác nhạy cảm | Kết quả tương đương một thứ tự tuần tự | `SERIALIZABLE`; xác định rõ phạm vi dữ liệu và cách retry. |
| Client đọc sau khi nhận xác nhận ghi | Đường đọc phải tôn trọng thứ tự trước–sau | Cam kết strong/linearizable hoặc strict-serializable phù hợp; kiểm tra replica/cache. |

Các hướng trên không thay thế việc phân tích schema, transaction boundary và DBMS. Ví dụ, UNIQUE có thể ngăn hai bản ghi trùng một khóa, nhưng không tự bảo vệ một ràng buộc tổng hợp tùy ý.

## 9. Ví dụ SQL diễn đạt các mức cô lập

Cú pháp đặt isolation level khác nhau giữa DBMS. Ví dụ dưới đây sử dụng cú pháp quen thuộc trong PostgreSQL/SQL tương thích gần đó; cần điều chỉnh theo sản phẩm và phiên bản.

### 9.1. Khai báo READ COMMITTED

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM accounts
WHERE id = 10;

COMMIT;
```

Giao dịch đọc dữ liệu đã commit theo snapshot của từng câu truy vấn trong PostgreSQL. Nếu một transaction khác commit giữa hai câu đọc, câu tiếp theo có thể thấy thay đổi đó.

### 9.2. Khai báo REPEATABLE READ

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT SUM(amount)
FROM account_entries
WHERE account_id = 10;

-- Các transaction khác có thể commit thay đổi sau snapshot.
-- T1 tiếp tục đọc theo snapshot của mình.

SELECT SUM(amount)
FROM account_entries
WHERE account_id = 10;

COMMIT;
```

Trong PostgreSQL, hai phép đọc thông thường sử dụng snapshot ổn định cho transaction. Điều này hữu ích cho báo cáo nhiều truy vấn. Nếu transaction cần ghi và có xung đột với thay đổi đồng thời, nó có thể nhận lỗi serialization tùy lịch.

### 9.3. Khai báo SERIALIZABLE

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM doctors
WHERE on_call = TRUE;

-- Business logic kiểm tra số người trực.
UPDATE doctors
SET on_call = FALSE
WHERE id = 'A';

COMMIT;
```

Nếu transaction khác tạo ra phụ thuộc khiến lịch không serializable, DBMS có thể hủy một transaction. Ứng dụng phải bắt lỗi phù hợp rồi thử lại toàn bộ logic với dữ liệu mới, không chỉ chạy lại câu cuối.

### 9.4. Chú ý khi dùng Spring

Spring có thể đặt isolation level ở annotation:

```java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void updateBusinessState() {
    // Đọc điều kiện nghiệp vụ.
    // Cập nhật các dữ liệu liên quan.
}
```

Annotation chỉ là yêu cầu gửi tới transaction manager/connection trong phạm vi được cấu hình. Cần xác minh:

- Transaction có thực sự được mở qua proxy hay không.
- DataSource/transaction manager nào quản lý kết nối.
- DBMS có hỗ trợ isolation được yêu cầu và driver truyền yêu cầu như thế nào.
- Propagation có tham gia một transaction đã tồn tại ở mức khác hay tạo transaction mới.
- Lỗi serialization/deadlock có được chuyển thành exception để ứng dụng xử lý không.

Nếu một method tham gia transaction sẵn có, mức cô lập của transaction đang tồn tại có thể quyết định thực tế; không nên chỉ nhìn annotation của method được gọi.

## 10. Xử lý lỗi là một phần của hợp đồng isolation

Ở mức bảo đảm mạnh, DBMS có thể hủy transaction khi không thể cho phép lịch đồng thời tiếp tục mà vẫn giữ hợp đồng. Đây không nhất thiết là lỗi của DBMS; đó là cách bảo vệ tính đúng đắn.

Các tình huống thường gặp:

| Loại lỗi | Ý nghĩa | Cách xử lý |
|---|---|---|
| Deadlock victim | Một transaction bị chọn hủy để giải phóng vòng chờ khóa | Retry toàn bộ transaction nếu thao tác có thể lặp an toàn. |
| Serialization failure | Lịch vừa thực hiện không thể được chấp nhận ở mức serializable | Rollback và chạy lại toàn bộ transaction với snapshot mới. |
| Lock timeout | Không lấy được khóa trong giới hạn thời gian | Xem xét mức tranh chấp, thứ tự truy cập, timeout và phản hồi retry. |
| Optimistic version conflict | Dữ liệu đã đổi kể từ khi ứng dụng đọc | Đọc lại, báo conflict hoặc áp dụng quyết định mới. |
| Business constraint violation | Thay đổi vi phạm quy tắc được khai báo | Trả lỗi nghiệp vụ, không retry mù quáng. |

Retry phải có giới hạn, backoff hợp lý và phải đảm bảo tác dụng phụ bên ngoài không lặp vô tình. Nếu transaction gửi email hoặc gọi cổng thanh toán trước khi commit, chạy lại cả method có thể gây hai lần tác dụng; cần outbox/idempotency hoặc tách tác dụng ngoài transaction.

## 11. Mức cô lập chỉ có ý nghĩa trong phạm vi được bảo vệ

Một ứng dụng thường có nhiều lớp:

```text
HTTP client
    |
    v
Application service
    |
    +---- Transaction manager / DB connection
    |            |
    |            v
    |        Primary database
    |
    +---- Cache
    |
    +---- Read replica
    |
    +---- Message broker / external API
```

Một transaction serializable trên primary **không tự biến** cache, replica bất đồng bộ, broker hoặc hệ thống thanh toán thành một phần của transaction ấy.

Ví dụ:

- Ghi commit trên primary, nhưng đọc ngay từ replica chưa đồng bộ có thể thấy dữ liệu cũ.
- Cache vẫn trả giá trị cũ nếu invalidation chưa hoàn tất.
- Message broker xử lý sự kiện trễ hơn transaction database.
- API thanh toán trả response riêng, không tự commit cùng transaction database.

Khi đặc tả hệ thống, hãy nói rõ mức cô lập cho **đối tượng dữ liệu và đường truy cập nào**. Tránh tuyên bố chung “hệ thống có SERIALIZABLE” trong khi một số endpoint vẫn chủ động chấp nhận stale read.

## 12. Cách diễn đạt bảo đảm isolation rõ ràng trong thiết kế

Một đặc tả tốt chuyển tên mức cô lập thành hành vi quan sát được. Ví dụ:

**Mô tả chưa đủ rõ:**

> Các thao tác checkout chạy ở READ COMMITTED.

Câu này thiếu thông tin về bất biến, cách xử lý tồn kho, cập nhật trùng và transaction nào được bao phủ.

**Mô tả có thể kiểm chứng hơn:**

> Mỗi checkout thực hiện trừ tồn kho có điều kiện và tạo đơn trong cùng một transaction. Checkout chỉ thành công khi đúng một hàng tồn kho được cập nhật và đơn được ghi thành công. Một khóa idempotency duy nhất ngăn cùng một request tạo hai đơn. Các truy vấn thông thường chỉ đọc dữ liệu đã commit theo semantics READ COMMITTED của DBMS đã chọn. Tranh chấp tồn kho được trả về như kết quả nghiệp vụ hoặc xử lý theo retry có giới hạn.

Một đặc tả khác cho báo cáo:

> Tất cả truy vấn cấu thành báo cáo phải sử dụng cùng một transaction snapshot. Báo cáo phản ánh một trạng thái dữ liệu nhất quán tại snapshot được thiết lập, nhưng không cam kết đó là trạng thái mới nhất ở thời điểm response trả về.

Với một API cần đọc sau khi xác nhận ghi:

> Nếu transaction cập nhật trả xác nhận commit thành công trước khi một transaction đọc mới được gọi, transaction đọc phải quan sát cập nhật đó trong phạm vi dữ liệu và endpoint có cam kết strong consistency. Đường đọc từ replica/cache phải tuân thủ cùng bảo đảm hoặc được đánh dấu rõ là stale-read.

Những câu này nêu rõ **điều kiện, phạm vi và kết quả mong đợi**, thay vì chỉ nêu tên một isolation level.

### 12.1. Mẫu ghi nhận trong tài liệu kỹ thuật

Có thể mô tả một hợp đồng isolation theo mẫu:

| Trường | Nội dung cần ghi |
|---|---|
| Đơn vị được bảo vệ | Một câu SQL, một transaction, hay nhiều endpoint? |
| Dữ liệu trong phạm vi | Bảng, hàng, tenant, database hay dịch vụ nào? |
| Snapshot/visibility | Mỗi statement hay một snapshot cho cả transaction? |
| Anomaly bị ngăn | Dirty read, non-repeatable, phantom, lost update, write skew... |
| Thứ tự yêu cầu | Có yêu cầu serializable hay strict serializable/real-time không? |
| Cơ chế/triển khai | Khóa, MVCC, SSI, constraint, optimistic version... |
| Khi xung đột | Block, timeout, rollback, retry hay báo lỗi nghiệp vụ? |
| Endpoint ngoài DB | Cache, replica, broker và service khác tham gia bảo đảm nào? |
| Kiểm thử | Lịch hai/ba transaction nào dùng để chứng minh hành vi? |

Không nhất thiết mọi bài toán đều phải ghi đủ mọi ô. Mẫu này giúp phát hiện những chỗ còn mơ hồ trước khi implementation hoặc review.

## 13. Phương pháp kiểm chứng mức cô lập

Một tuyên bố isolation cần được kiểm tra bằng lịch giao dịch có chủ đích.

### 13.1. Dùng hai session độc lập

Tạo hai kết nối A và B. Không chạy toàn bộ ví dụ trong một cửa sổ SQL duy nhất rồi dựa vào thứ tự lệnh tuần tự, vì như vậy không mô phỏng được tương tác đồng thời.

Với dirty read:

1. A bắt đầu transaction và cập nhật một hàng nhưng chưa commit.
2. B bắt đầu transaction và đọc cùng hàng.
3. Quan sát B có đọc giá trị chưa commit hay không.
4. A rollback; kiểm tra B đã quan sát dữ liệu nào.

Với non-repeatable read:

1. A đọc một hàng.
2. B cập nhật cùng hàng và commit.
3. A đọc lại.
4. So sánh hai kết quả trong cùng transaction A.

Với phantom:

1. A chạy truy vấn theo predicate.
2. B insert hoặc update một hàng sao cho nó thỏa predicate rồi commit.
3. A chạy lại predicate.
4. So sánh tập hàng.

Với write skew:

1. A và B cùng đọc điều kiện tổng hợp trên nhiều hàng.
2. Mỗi transaction cập nhật hàng khác nhau.
3. Cho cả hai commit nếu DBMS cho phép hoặc ghi nhận transaction bị hủy.
4. Kiểm tra bất biến ở trạng thái cuối.

### 13.2. Kiểm thử đúng cấu hình

Ghi lại DBMS và version, engine, isolation level thực tế, autocommit, driver, transaction manager, truy vấn và index. Cùng một tên isolation nhưng kết quả có thể khác giữa các sản phẩm.

Nếu ứng dụng dùng pool, cần đảm bảo A và B thật sự là hai connection độc lập. Nếu kiểm thử endpoint, cần ghi nhận route có thể chuyển đọc sang replica/cache hay không.

### 13.3. Phân biệt quan sát và chứng minh

Một lần thử không thấy dirty read không chứng minh mọi lịch đều không thể có dirty read. Kiểm thử concurrency giúp phát hiện phản ví dụ, xác nhận cấu hình và tái hiện lỗi. Bảo đảm chính thức còn cần semantics được tài liệu hóa của DBMS và phạm vi triển khai.

Ngược lại, một lịch quan sát được vi phạm điều kiện đã cam kết là bằng chứng mạnh rằng cấu hình/đường đi đó không đáp ứng hợp đồng dự kiến.

## 14. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| `SERIALIZABLE` nghĩa là database chạy từng transaction lần lượt. | Nó yêu cầu hiệu ứng tương đương thứ tự tuần tự; các transaction vẫn có thể chạy vật lý đồng thời. |
| READ COMMITTED ngăn mọi lỗi đồng thời. | Nó ngăn dirty read theo mô hình, nhưng vẫn có thể có non-repeatable read, phantom và các nguy cơ nghiệp vụ khác. |
| REPEATABLE READ ở mọi DBMS xử lý phantom giống nhau. | Cần xem cách triển khai và loại truy vấn; PostgreSQL và InnoDB có semantics chi tiết khác nhau. |
| MVCC nghĩa là không dùng khóa. | MVCC quản lý phiên bản đọc; ghi, locking read và DDL vẫn có thể dùng khóa. |
| Snapshot ổn định luôn là dữ liệu mới nhất. | Snapshot có thể nhất quán nhưng cũ hơn các commit xảy ra sau thời điểm snapshot. |
| Isolation tự bảo vệ mọi constraint nghiệp vụ. | Logic và constraint vẫn phải biểu diễn quy tắc, đặc biệt khi ràng buộc trải trên nhiều hàng. |
| Chỉ cần retry câu SQL bị lỗi. | Serialization failure thường yêu cầu rollback và chạy lại toàn bộ transaction với dữ liệu mới. |
| Mọi endpoint đều có cùng isolation vì primary dùng SERIALIZABLE. | Replica, cache, broker và service ngoài DB có thể có consistency riêng. |
| Mức cô lập càng cao luôn càng tốt. | Cần cân bằng bảo đảm, độ trễ, tranh chấp, tỷ lệ rollback và yêu cầu nghiệp vụ. |

## 15. Ghi nhớ

**Mục tiêu của isolation là kiểm soát những gì transaction có thể quan sát và những lịch tương tác nào được phép xảy ra.** Các mức cô lập diễn đạt độ mạnh của hợp đồng này; các anomaly như dirty read, non-repeatable read, phantom, lost update và write skew giúp làm rõ giới hạn của từng cơ chế.

Khi chọn mức cô lập, hãy bắt đầu từ bất biến nghiệp vụ và lịch giao dịch cần bảo vệ. Sau đó xác định snapshot, khóa, constraint và hành vi lỗi phù hợp với DBMS thực tế. Cuối cùng, diễn đạt hợp đồng bằng những câu có thể kiểm chứng: transaction nào, đọc dữ liệu nào, có thể thấy thay đổi nào, lỗi gì được phép xảy ra và những endpoint nào nằm trong phạm vi bảo đảm.
