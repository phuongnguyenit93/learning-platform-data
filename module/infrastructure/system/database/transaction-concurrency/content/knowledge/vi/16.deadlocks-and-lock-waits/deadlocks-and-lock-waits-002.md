# Đồ thị chờ và chu trình phụ thuộc giữa các giao dịch

Khi một giao dịch yêu cầu khóa mà giao dịch khác đang giữ, nó phải chờ. Trong lúc chờ, giao dịch vẫn có thể giữ những khóa đã lấy trước đó. Nếu nhiều giao dịch lần lượt chờ tài nguyên của nhau, chúng có thể tạo thành một chu trình mà không giao dịch nào tự tiếp tục được. Đây là cơ chế cốt lõi của deadlock (bế tắc).

Đồ thị chờ (wait-for graph) biểu diễn quan hệ đó bằng các nút là giao dịch và các cạnh có hướng là quan hệ chờ. Nếu có cạnh từ T1 đến T2, điều đó có nghĩa T1 đang chờ một tài nguyên mà T2 đang giữ hoặc đang được lock manager xem là bên chặn T1. Khi đồ thị có chu trình, các giao dịch trong chu trình đang phụ thuộc vòng tròn vào nhau.

Đồ thị chờ giúp trả lời ba câu hỏi quan trọng: giao dịch nào đang chặn giao dịch nào, chu trình bế tắc gồm những giao dịch nào, và cần hủy giao dịch nào để giải phóng chu trình. Nó cũng giúp phân biệt một chuỗi chờ dài nhưng vẫn có thể tiến triển với một deadlock thực sự.

## 1. Từ chờ khóa đến quan hệ phụ thuộc

### 1.1. Một giao dịch giữ khóa, giao dịch khác phải chờ

Giả sử bảng account có hai hàng với id = 10 và id = 20. Giao dịch A cập nhật hàng 10:

~~~sql
-- Session A
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE id = 10;

-- Chưa COMMIT
~~~

Giao dịch B muốn cập nhật cùng hàng:

~~~sql
-- Session B
BEGIN;

UPDATE account
SET balance = balance + 50
WHERE id = 10;

-- Câu lệnh có thể phải chờ A
~~~

A đang giữ khóa ghi cần thiết trên hàng 10. B yêu cầu khóa xung đột nên chưa thể tiếp tục. Ở thời điểm này, có một quan hệ chờ từ B đến A.

Nếu A COMMIT hoặc ROLLBACK, khóa được giải phóng và B có thể tiếp tục theo quy tắc của hệ quản trị. Đây là lock wait (chờ khóa), nhưng chưa phải deadlock vì A không chờ B.

Có thể biểu diễn quan hệ bằng mũi tên:

~~~text
B  ─────waits for─────>  A
                         |
                         | đang giữ khóa hàng 10
                         v
                       Hàng 10
~~~

Mũi tên đi từ giao dịch đang chờ đến giao dịch đang chặn nó. Quy ước chiều này rất quan trọng khi đọc đồ thị.

### 1.2. Giao dịch vừa giữ khóa vừa chờ khóa khác

Deadlock có thể xảy ra khi một giao dịch đã giữ tài nguyên này nhưng lại yêu cầu tài nguyên khác.

Ví dụ:

- A đã khóa hàng 10.
- B đã khóa hàng 20.
- A muốn khóa hàng 20 nên phải chờ B.
- B muốn khóa hàng 10 nên phải chờ A.

~~~sql
-- Session A
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE id = 10;

-- Sau đó yêu cầu hàng 20
UPDATE account
SET balance = balance + 100
WHERE id = 20;
~~~

~~~sql
-- Session B
BEGIN;

UPDATE account
SET balance = balance - 50
WHERE id = 20;

-- Sau đó yêu cầu hàng 10
UPDATE account
SET balance = balance + 50
WHERE id = 10;
~~~

Nếu A đã lấy khóa hàng 10 và B đã lấy khóa hàng 20 trước khi hai câu UPDATE tiếp theo chạy, ta có:

- A giữ hàng 10 và chờ hàng 20 do B giữ.
- B giữ hàng 20 và chờ hàng 10 do A giữ.

Đồ thị chờ:

~~~text
       A ─────────> B
       ^             |
       |             |
       └─────────────┘
~~~

Hai cạnh tạo thành chu trình A → B → A. Không giao dịch nào có thể tự giải phóng khóa đang giữ vì cả hai đều đang chờ. Nếu không có hành động từ bên ngoài như rollback hoặc hủy một giao dịch, chu trình không thể tự phá vỡ.

## 2. Định nghĩa đồ thị chờ

### 2.1. Thành phần của đồ thị

Đồ thị chờ có thể mô tả bằng một cặp:

\[
G = (V, E)
\]

Trong đó:

- \(V\) là tập các giao dịch đang tham gia vào những quan hệ chờ.
- \(E\) là tập các cạnh có hướng biểu diễn quan hệ chờ.

Một cạnh:

\[
T_i \rightarrow T_j
\]

có nghĩa giao dịch \(T_i\) đang chờ một tài nguyên mà \(T_j\) đang giữ hoặc đang chặn theo quy tắc hàng đợi khóa.

Ví dụ:

~~~text
T1 ──> T2 ──> T3
               |
               v
              T4
~~~

Trong ví dụ này, T1 đang chờ T2; T2 đang chờ T3; T3 đang chờ T4. Nếu T4 không chờ ai và có thể hoàn tất, nó có thể giải phóng khóa để chuỗi chờ tiến triển ngược từ T3 đến T1. Đây là wait chain (chuỗi chờ), chưa phải deadlock.

### 2.2. Khi nào một cạnh được tạo?

Một cạnh được tạo khi yêu cầu khóa của giao dịch đang chờ không tương thích với trạng thái khóa hiện tại hoặc với một yêu cầu trước đó trong hàng đợi.

Ví dụ, với một hàng dữ liệu:

- T1 giữ khóa độc quyền X.
- T2 yêu cầu khóa chia sẻ S trên cùng hàng.
- S và X không tương thích.
- T2 phải chờ T1.

Do đó có cạnh T2 → T1.

Lock manager quyết định tương thích dựa trên loại khóa và tài nguyên. Tên chế độ khóa khác nhau giữa hệ quản trị, nhưng ý nghĩa chung là xác định hai yêu cầu có thể cùng được cấp hay không.

Một số loại tài nguyên có thể tạo cạnh:

- Khóa hàng hoặc khóa bản ghi chỉ mục.
- Khóa khoảng, gap lock hoặc next-key lock.
- Khóa trang hoặc khóa bảng.
- Khóa metadata/lược đồ.
- Khóa do kiểm tra UNIQUE hoặc FOREIGN KEY phát sinh.
- Advisory lock hoặc application lock.
- Khóa trên tài nguyên nội bộ khác mà hệ quản trị quản lý.

Không nên chỉ tìm các câu SELECT ... FOR UPDATE khi điều tra. INSERT, UPDATE, DELETE và kiểm tra ràng buộc cũng có thể tạo yêu cầu khóa.

### 2.3. Một giao dịch có thể có nhiều cạnh đi ra

Một yêu cầu khóa có thể bị chặn bởi nhiều giao dịch. Ví dụ, T1 muốn lấy khóa độc quyền X trên một tài nguyên nhưng T2 và T3 đều đang giữ khóa chia sẻ S tương thích với nhau. Xung đột với cả hai khóa S, nên T1 có thể phải chờ cả T2 và T3.

Đồ thị có thể là:

~~~text
       T2
        ^
        |
        |
T1 ─────┤
        |
        v
       T3
~~~

Nói chính xác hơn, có hai cạnh T1 → T2 và T1 → T3. Khi cả T2 và T3 giải phóng khóa tương ứng, T1 mới có thể được cấp X.

Đừng giả định mỗi giao dịch chỉ có một blocker. Một truy vấn có thể cần nhiều tài nguyên hoặc bị nhiều chủ sở hữu khóa chặn cùng lúc.

### 2.4. Một giao dịch có thể có nhiều cạnh đi vào

Một giao dịch đang giữ tài nguyên nóng có thể chặn nhiều giao dịch:

~~~text
T2 ──┐
     |
T3 ──┼────> T1
     |
T4 ──┘
~~~

T1 có thể là blocker (giao dịch chặn) của T2, T3 và T4. Nếu T1 hoàn tất, nhiều giao dịch có thể được đánh thức. Nhưng nếu T1 lại chờ một giao dịch trong số các giao dịch đó, một chu trình có thể xuất hiện.

Số lượng giao dịch đang chờ một blocker cao thường cho thấy điểm nóng hoặc giao dịch giữ khóa quá lâu. Nó chưa đủ để kết luận có deadlock.

## 3. Chu trình trong đồ thị chờ

### 3.1. Chu trình hai giao dịch

Đây là trường hợp đơn giản nhất:

~~~text
T1 ─────> T2
 ^         |
 |         |
 └─────────┘
~~~

T1 chờ khóa do T2 giữ. T2 chờ khóa do T1 giữ. Mỗi giao dịch đều giữ một tài nguyên mà giao dịch kia cần.

Với lock manager biểu diễn đầy đủ các phụ thuộc chờ, chu trình cho biết các giao dịch trong chu trình không thể tự tiến triển bằng cách chờ thông thường. Hệ quản trị phải phá chu trình, thường bằng cách chọn một giao dịch làm deadlock victim và rollback nó.

### 3.2. Chu trình ba giao dịch

Deadlock không nhất thiết chỉ gồm hai giao dịch:

~~~text
T1 ─────> T2
 ^         |
 |         v
T3 <───────┘
~~~

Tương đương các cạnh:

\[
T1 \rightarrow T2,\quad
T2 \rightarrow T3,\quad
T3 \rightarrow T1
\]

Ví dụ:

- T1 giữ khóa hàng A, chờ hàng B do T2 giữ.
- T2 giữ khóa hàng B, chờ hàng C do T3 giữ.
- T3 giữ khóa hàng C, chờ hàng A do T1 giữ.

Không có một giao dịch nào có thể giải phóng khóa nếu không được phép tiếp tục hoặc bị hủy. Chỉ nhìn danh sách blocker trực tiếp có thể bỏ sót chu trình nếu không lần theo toàn bộ chuỗi phụ thuộc.

### 3.3. Chu trình dài hơn

Với N giao dịch, chu trình có thể có dạng:

\[
T_1 \rightarrow T_2 \rightarrow \cdots
\rightarrow T_N \rightarrow T_1
\]

Chu trình có thể dài hơn hai hoặc ba cạnh. Trong hệ thống có nhiều bảng, trigger, khóa ngoại, cascade và advisory lock, một giao dịch có thể không biết rằng nó đang tham gia vào một chu trình dài qua nhiều thành phần.

Ví dụ một chuỗi nghiệp vụ:

1. T1 cập nhật đơn hàng rồi chờ kho.
2. T2 cập nhật kho rồi chờ thanh toán.
3. T3 cập nhật thanh toán rồi chờ đơn hàng.

Nếu các tài nguyên được giữ theo thứ tự đó, đồ thị tạo chu trình T1 → T2 → T3 → T1.

### 3.4. Chu trình con

Một đồ thị có thể có nhiều giao dịch và nhiều cạnh, nhưng chỉ một nhóm nhỏ tạo thành chu trình. Ví dụ:

~~~text
T1 ──> T2 ──> T3 ──> T1

T4 ──> T2
T5 ──> T4
T6 ──> T4
~~~

T1, T2 và T3 tạo chu trình deadlock. T4, T5 và T6 đang nằm trong chuỗi chờ phụ thuộc vào T2 hoặc T4. Khi hệ quản trị hủy một giao dịch trong chu trình, việc giải phóng khóa có thể làm các giao dịch phía ngoài tiếp tục.

Khi phân tích, cần xác định chính xác chu trình, không chỉ đếm số phiên đang có trạng thái waiting.

## 4. Từ tài nguyên khóa đến đồ thị giao dịch

### 4.1. Resource allocation graph

Một cách mô tả đầy đủ hơn là resource allocation graph (đồ thị cấp phát tài nguyên). Nó có hai loại nút:

- Nút giao dịch.
- Nút tài nguyên hoặc đối tượng khóa.

Các cạnh thể hiện hai quan hệ:

- **Request edge:** giao dịch yêu cầu một tài nguyên.
- **Assignment edge:** tài nguyên đã được cấp cho giao dịch.

Ví dụ:

~~~text
T1 ──request──> R2
                 |
                 | assigned to
                 v
                T2

T2 ──request──> R1
                 |
                 | assigned to
                 v
                T1
~~~

T1 yêu cầu R2 đang được cấp cho T2; T2 yêu cầu R1 đang được cấp cho T1.

Khi mỗi tài nguyên có một instance và các yêu cầu khóa không tương thích, chu trình trong resource allocation graph tương ứng với chu trình chờ. Đồ thị chờ được tạo bằng cách loại bỏ nút tài nguyên và nối giao dịch đang chờ trực tiếp đến giao dịch đang giữ tài nguyên gây chặn.

### 4.2. Chuyển sang wait-for graph

Từ ví dụ trên, ta bỏ R1 và R2:

~~~text
T1 ─────────> T2
 ^             |
 |             |
 └─────────────┘
~~~

Wait-for graph gọn hơn vì nó chỉ tập trung vào quan hệ giữa giao dịch. Đây là biểu diễn thuận tiện cho việc phát hiện chu trình.

Trong cơ sở dữ liệu, lock manager thường có đủ thông tin về resource, owner, mode và wait queue để dựng quan hệ này. Công cụ chẩn đoán có thể hiển thị trực tiếp blocker/waiter hoặc cung cấp deadlock graph có cả tài nguyên lẫn giao dịch.

### 4.3. Vì sao phải xét chế độ khóa?

Một tài nguyên có thể được nhiều giao dịch giữ đồng thời nếu các chế độ khóa tương thích. Chỉ khi một yêu cầu mới không tương thích với một hoặc nhiều khóa hiện có thì mới phát sinh phụ thuộc chờ.

Ví dụ đơn giản:

| Khóa đang giữ | Khóa được yêu cầu | Có thể tương thích? |
|---|---|---|
| S | S | Thường có |
| S | X | Không |
| X | S | Không |
| X | X | Không |

Bảng này chỉ minh họa shared/exclusive lock cơ bản. Hệ quản trị thực tế có nhiều mode hơn, chẳng hạn các mức khóa hàng PostgreSQL, intent lock, update lock hoặc key-range lock. Phải dùng ma trận tương thích của hệ quản trị đang chạy để xác định blocker chính xác.

Nếu hai giao dịch cùng giữ S trên hàng R, việc cả hai cùng muốn nâng lên X có thể tạo deadlock chuyển đổi khóa, dù ban đầu hai khóa S tương thích.

## 5. Các dạng deadlock thường gặp

### 5.1. Lấy khóa theo thứ tự ngược nhau

Đây là dạng phổ biến nhất khi cập nhật nhiều hàng.

~~~text
T1: khóa A -> yêu cầu B
T2: khóa B -> yêu cầu A
~~~

Mỗi giao dịch lấy tài nguyên theo một thứ tự khác nhau. Khi chạy riêng lẻ, cả hai đều thành công; khi chạy đồng thời, chúng có thể tạo chu trình.

Cách giảm nguy cơ là quy định một thứ tự toàn cục, ví dụ luôn khóa hàng theo khóa chính tăng dần.

### 5.2. Deadlock do nâng cấp khóa

Giả sử T1 và T2 cùng đọc một hàng bằng khóa chia sẻ S:

~~~text
T1 giữ S trên R
T2 giữ S trên R
~~~

Sau đó cả hai muốn cập nhật và nâng khóa lên X:

~~~text
T1 yêu cầu nâng S -> X, phải chờ T2 nhả S
T2 yêu cầu nâng S -> X, phải chờ T1 nhả S
~~~

Đồ thị:

~~~text
T1 ─────> T2
 ^         |
 |         |
 └─────────┘
~~~

Cách phòng tránh có thể là dùng locking read với mode phù hợp ngay từ đầu nếu giao dịch chắc chắn sẽ cập nhật, hoặc tuần tự hóa bước nhận quyền cập nhật. Cú pháp và mức khóa cụ thể phụ thuộc hệ quản trị.

### 5.3. Deadlock qua khóa ngoại và cascade

Một giao dịch thêm hàng con cần xác nhận hàng cha tồn tại. Giao dịch khác xóa hàng cha hoặc cập nhật hàng con liên quan. Nếu hai giao dịch đã giữ các khóa khác nhau rồi yêu cầu tài nguyên theo thứ tự đối nghịch, chúng có thể tạo chu trình.

Các thao tác có thể tham gia:

- INSERT hoặc UPDATE khóa ngoại ở bảng con.
- DELETE hoặc UPDATE khóa được tham chiếu ở bảng cha.
- ON DELETE CASCADE.
- ON UPDATE CASCADE.
- Trigger cập nhật bảng liên quan.
- Kiểm tra UNIQUE hoặc chỉ mục phụ trợ.

Không phải mọi cặp INSERT con và DELETE cha đều tạo deadlock. Có thể chỉ một giao dịch phải chờ rồi thất bại vì vi phạm ràng buộc. Muốn kết luận deadlock, phải dựng được các cạnh chờ và chu trình cụ thể.

### 5.4. Deadlock qua chỉ mục và khoảng khóa

Trong InnoDB, một truy vấn range scan có thể dùng record lock, gap lock hoặc next-key lock. Hai giao dịch có thể khóa các vùng khác nhau rồi chờ chèn/cập nhật vào vùng của nhau.

Ví dụ:

- T1 giữ khóa trên một bản ghi hoặc khoảng index phía trước.
- T2 giữ khóa trên một khoảng khác.
- T1 yêu cầu khoảng do T2 bảo vệ.
- T2 yêu cầu khoảng do T1 bảo vệ.

Đường truy cập và thứ tự lấy khóa trên index có thể quan trọng ngang với thứ tự cập nhật hàng. Thiếu index hoặc điều kiện không sargable có thể làm phạm vi quét rộng hơn và tăng khả năng giao nhau.

### 5.5. Deadlock do trigger hoặc thủ tục lưu trữ

Một câu UPDATE có thể kích hoạt trigger, trigger lại đọc hoặc cập nhật bảng khác. Nếu ứng dụng chỉ nhìn câu SQL bên ngoài, thứ tự lấy khóa thật sự có thể bị che khuất.

Ví dụ:

~~~text
T1: UPDATE order
    -> trigger cập nhật inventory
    -> chờ payment

T2: UPDATE payment
    -> trigger cập nhật order
    -> chờ order
~~~

Đồ thị chờ được tạo từ tất cả thao tác bên trong transaction, bao gồm trigger và stored procedure. Khi đọc deadlock report, cần xem câu lệnh nội bộ và resource list, không chỉ statement được ứng dụng gửi ban đầu.

### 5.6. Deadlock qua khóa ứng dụng

Một ứng dụng có thể dùng advisory lock hoặc application lock để bảo vệ tài nguyên nghiệp vụ. Nếu một luồng lấy khóa ứng dụng trước rồi khóa hàng, luồng khác lấy khóa hàng trước rồi chờ khóa ứng dụng, hệ thống có thể có chu trình phụ thuộc.

Ví dụ:

~~~text
T1 giữ advisory lock A, chờ row lock R
T2 giữ row lock R, chờ advisory lock A
~~~

Nếu một phần tài nguyên được quản lý bởi database lock manager và phần khác bởi một bộ khóa ngoài database, deadlock có thể vượt qua ranh giới của một công cụ chẩn đoán. Cần thiết kế thứ tự lấy khóa thống nhất trên toàn bộ tài nguyên.

## 6. Chuỗi chờ không đồng nghĩa với deadlock

### 6.1. Một chuỗi chờ có thể tự giải quyết

~~~text
T1 ──> T2 ──> T3
~~~

T1 chờ T2; T2 chờ T3. T3 không chờ ai và có thể hoàn tất. Khi T3 COMMIT, nó giải phóng khóa cho T2. T2 tiếp tục và sau đó giải phóng khóa cho T1.

Đây là blocking chain (chuỗi chặn). Nó có thể làm độ trễ tăng đáng kể nhưng không phải deadlock vì không có chu trình.

### 6.2. Một blocker có thể làm nhiều phiên chờ

~~~text
T2 ──┐
T3 ──┼──> T1
T4 ──┘
~~~

Nếu T1 đang chạy một transaction dài và giữ khóa trên hàng nóng, T2, T3, T4 có thể cùng chờ. Đây là blocking fan-out. Khi T1 hoàn tất, các phiên có thể tiếp tục theo thứ tự cấp khóa.

Trường hợp này cần điều tra vì throughput có thể giảm, nhưng không nên gọi là deadlock nếu đồ thị không có chu trình.

### 6.3. Chờ lâu không tự động là deadlock

Một giao dịch có thể chờ hàng phút vì blocker chưa COMMIT. Nếu blocker không chờ giao dịch đang bị chặn, đồ thị không có chu trình.

Lock timeout có thể kết thúc việc chờ lâu, nhưng timeout không phải bằng chứng có deadlock. Deadlock là cấu trúc phụ thuộc vòng tròn, không phải chỉ là thời lượng chờ lớn.

## 7. Phân biệt wait-for graph với serialization graph

Hai loại đồ thị này đều có nút là giao dịch và cạnh có hướng, nên dễ bị nhầm lẫn. Chúng trả lời hai câu hỏi khác nhau.

### 7.1. Wait-for graph

Wait-for graph biểu diễn giao dịch nào đang phải chờ giao dịch nào do xung đột tài nguyên.

- Cạnh T1 → T2: T1 đang chờ T2.
- Chu trình: deadlock trong đồ thị phụ thuộc khóa hiện tại.
- Mục đích: phát hiện và phá bế tắc.

### 7.2. Serialization graph hoặc precedence graph

Serialization graph biểu diễn thứ tự xung đột giữa các giao dịch trong lịch thực thi.

- Cạnh T1 → T2: một thao tác của T1 xảy ra trước và xung đột với thao tác của T2, nên lịch tuần tự tương đương phải đặt T1 trước T2.
- Chu trình: lịch không conflict-serializable.
- Mục đích: phân tích tính tuần tự của lịch thực thi.

Ví dụ, hai giao dịch có thể thực hiện đọc/ghi theo thứ tự tạo chu trình trong serialization graph nhưng không hề chờ khóa nhau nếu hệ thống dùng MVCC và phát hiện xung đột ở bước validation. Ngược lại, một deadlock có thể được phát hiện và hủy trước khi các giao dịch hoàn tất; nó là vấn đề chờ tài nguyên.

| Tiêu chí | Wait-for graph | Serialization graph |
|---|---|---|
| Cạnh biểu diễn | Đang chờ giao dịch khác | Thứ tự xung đột giữa thao tác |
| Chu trình có nghĩa | Deadlock | Lịch không conflict-serializable |
| Dữ liệu cần | Khóa đang giữ, yêu cầu khóa, blocker | Read/write operations và thứ tự thực hiện |
| Mục đích | Phát hiện giao dịch mắc kẹt | Kiểm tra tính tuần tự hóa |

Không dùng đồ thị chờ để kết luận một lịch có serializable hay không. Cũng không dùng serialization graph thay cho thông tin blocker khi cần tìm deadlock đang diễn ra.

## 8. Lock manager phát hiện chu trình như thế nào?

### 8.1. Cập nhật đồ thị khi có yêu cầu chờ

Khi một giao dịch yêu cầu khóa không tương thích, lock manager xác định các chủ sở hữu khóa đang chặn yêu cầu đó và thêm cạnh tương ứng vào wait-for graph.

Ví dụ, trước khi T3 yêu cầu tài nguyên R:

~~~text
T1 ──> T2
~~~

T3 yêu cầu khóa đang do T1 giữ, nên thêm cạnh T3 → T1:

~~~text
T1 ──> T2
^
|
T3
~~~

Nếu sau đó T2 yêu cầu tài nguyên do T3 giữ, cạnh T2 → T3 được thêm vào:

~~~text
T1 ──> T2
^       |
|       v
T3 <────┘
~~~

Một chu trình đã xuất hiện. Lock manager có thể phát hiện ngay khi thêm cạnh mới hoặc trong lần kiểm tra định kỳ tiếp theo.

### 8.2. Tìm chu trình bằng DFS

Một cách phát hiện phổ biến là duyệt đồ thị bằng depth-first search (DFS). Khi duyệt, thuật toán đánh dấu trạng thái nút:

- Chưa thăm.
- Đang nằm trên đường duyệt hiện tại.
- Đã duyệt xong.

Nếu gặp cạnh đến một nút đang nằm trên đường duyệt hiện tại, ta đã tìm thấy chu trình.

Với danh sách kề, một lần duyệt đồ thị có độ phức tạp gần:

\[
O(|V| + |E|)
\]

Trong đó \(|V|\) là số giao dịch trong đồ thị và \(|E|\) là số cạnh chờ. Đây là mô hình thuật toán cơ bản; lock manager thực tế còn phải xử lý đồng bộ dữ liệu khóa, hàng đợi và thay đổi đồ thị trong lúc các giao dịch tiếp tục chạy.

### 8.3. Kiểm tra đường đi khi thêm cạnh

Thay vì duyệt toàn bộ đồ thị định kỳ, hệ thống có thể kiểm tra xem khi thêm cạnh T1 → T2 thì đã tồn tại đường đi từ T2 về T1 hay chưa.

- Nếu chưa có đường đi, cạnh mới chưa tạo chu trình.
- Nếu đã có đường đi, cạnh mới khép kín một chu trình.

Cách này có thể phát hiện deadlock ngay khi cạnh được thêm, nhưng chi phí phụ thuộc kích thước đồ thị và cách hệ thống quản lý trạng thái.

### 8.4. Đồ thị thay đổi liên tục

Wait-for graph là trạng thái động:

- Transaction COMMIT hoặc ROLLBACK sẽ nhả khóa.
- Yêu cầu khóa được cấp sẽ loại bỏ cạnh chờ tương ứng.
- Transaction bị hủy sẽ loại bỏ các cạnh liên quan.
- Một giao dịch có thể chuyển từ chờ một blocker sang chờ blocker khác khi hàng đợi thay đổi.
- Một yêu cầu có thể bị timeout hoặc cancel trước khi detector chạy.

Vì vậy, một deadlock report là ảnh chụp của một thời điểm. Khi điều tra, cần giữ lại thông tin đầy đủ của report thay vì chỉ xem trạng thái lock hiện tại sau khi hệ quản trị đã phá chu trình.

## 9. Hàng đợi khóa và các cạnh phụ thuộc

### 9.1. Vì sao blocker không chỉ là chủ sở hữu khóa đã cấp?

Một số lock manager duy trì hàng đợi để bảo đảm công bằng hoặc ưu tiên yêu cầu khóa độc quyền. Khi một yêu cầu X đang chờ phía trước, một yêu cầu S đến sau có thể phải đứng sau X dù S tương thích với khóa S đang được cấp hiện tại.

Ví dụ:

- T1 đang giữ S trên R.
- T2 yêu cầu X trên R và phải chờ T1.
- T3 yêu cầu S trên R sau T2.

Về tương thích thuần túy, S của T3 có thể tương thích với S của T1. Nhưng nếu lock manager không cho yêu cầu mới vượt qua X đang chờ, T3 phải chờ trong hàng đợi.

Đồ thị đơn giản chỉ nối waiter đến granted lock holder có thể chưa biểu diễn đủ quan hệ hàng đợi này. Một số hệ thống xét cả các yêu cầu trước trong wait queue khi xác định blocker hoặc deadlock.

### 9.2. Chuyển đổi khóa tạo phụ thuộc đặc biệt

Một transaction có thể đang giữ khóa S và yêu cầu nâng lên X. Hệ thống phải xem khóa hiện có của transaction và các khóa tương thích đang được transaction khác giữ.

Ví dụ hai transaction cùng giữ S và cùng yêu cầu X. Nếu cả hai yêu cầu nâng cấp đều chờ khóa S của bên còn lại, deadlock có thể xảy ra.

Một số hệ quản trị có cơ chế update lock hoặc quy tắc chuyển đổi riêng để giảm kiểu deadlock này. Không nên giả định tất cả hệ quản trị đều xử lý conversion giống nhau.

### 9.3. Đọc đồ thị do công cụ DBMS cung cấp

Deadlock graph của sản phẩm cơ sở dữ liệu có thể chứa:

- Process/session/transaction ID.
- Câu lệnh đang chạy.
- Loại và mode của khóa.
- Tài nguyên bị yêu cầu.
- Chủ sở hữu hoặc waiter.
- Wait queue và thứ tự yêu cầu.
- Transaction được chọn làm victim.

Một báo cáo có thể trình bày resource allocation graph thay vì wait-for graph đã rút gọn. Hãy đọc chú giải cạnh và vai trò resource để tránh đảo chiều mũi tên.

## 10. Hệ quản trị phá deadlock như thế nào?

### 10.1. Chọn deadlock victim

Khi detector phát hiện chu trình, hệ quản trị thường chọn một giao dịch làm victim. Nó hủy hoặc rollback giao dịch đó để giải phóng các khóa đang giữ. Khi các khóa được nhả, những giao dịch còn lại có thể tiếp tục.

Việc chọn victim có thể cân nhắc:

- Lượng công việc giao dịch đã thực hiện.
- Số lượng hoặc chi phí tài nguyên cần rollback.
- Số khóa đang giữ.
- Mức ưu tiên transaction.
- Số lần transaction đã bị chọn làm victim.
- Chi phí phục hồi và khả năng tiến triển của các giao dịch còn lại.

Chính sách cụ thể khác nhau giữa các hệ quản trị. Không nên giả định hệ thống luôn hủy transaction mới nhất, transaction ít thay đổi nhất hoặc transaction đang yêu cầu khóa cuối cùng.

### 10.2. Rollback giải phóng cạnh

Giả sử chu trình:

~~~text
T1 ──> T2 ──> T3 ──> T1
~~~

Hệ quản trị chọn T2 làm victim. Khi T2 rollback:

- Các khóa T2 đang giữ được giải phóng.
- Các yêu cầu khóa T2 đang chờ bị hủy.
- T1 hoặc T3 có thể nhận được khóa đang chờ.
- Các cạnh liên quan đến T2 bị loại bỏ.
- Chu trình không còn tồn tại.

Rollback là hành động phá chu trình, không phải sửa nguyên nhân khiến các giao dịch lấy khóa theo thứ tự đối nghịch. Nếu ứng dụng chạy lại cùng lịch thao tác, deadlock có thể lặp lại.

### 10.3. Rollback toàn transaction hay một phần?

Hành vi sau deadlock phụ thuộc hệ quản trị và driver:

- PostgreSQL báo deadlock detected và transaction hiện tại bị hủy; ứng dụng thường phải ROLLBACK transaction rồi chạy lại trong transaction mới.
- InnoDB thường rollback toàn bộ transaction được chọn làm victim.
- SQL Server chọn victim và rollback transaction đó; ứng dụng nhận lỗi deadlock victim.
- Các hệ quản trị khác có quy tắc riêng về phạm vi rollback và trạng thái session.

Không nên giả định chỉ câu SQL cuối cùng bị rollback. Hãy dựa vào mã lỗi và trạng thái transaction của sản phẩm đang dùng.

### 10.4. Deadlock victim không phải lúc nào cũng là lỗi nghiệp vụ

Một deadlock thường là lỗi đồng thời có thể phục hồi. Dữ liệu transaction bị rollback để bảo vệ tính nhất quán. Ứng dụng có thể chạy lại toàn bộ đơn vị công việc nếu:

- Lỗi được nhận diện đúng là deadlock.
- Logic nghiệp vụ có thể chạy lại.
- Các tác dụng phụ ngoài database được kiểm soát.
- Số lần retry được giới hạn.

Nếu retry không thành công sau một số lần, trả lỗi có thể thử lại hoặc đưa công việc vào cơ chế xử lý khác.

## 11. Phòng tránh, tránh né và phát hiện deadlock

Ba khái niệm này có liên quan nhưng không giống nhau.

### 11.1. Prevention — phòng tránh bằng cách phá điều kiện cần

Deadlock cổ điển liên quan đến bốn điều kiện:

1. **Mutual exclusion:** tài nguyên không thể được nhiều transaction dùng theo chế độ xung đột cùng lúc.
2. **Hold and wait:** transaction giữ tài nguyên đã lấy và tiếp tục chờ tài nguyên khác.
3. **No preemption:** tài nguyên không bị lấy cưỡng bức khỏi transaction theo cách tùy ý.
4. **Circular wait:** tồn tại chu trình chờ.

Phòng tránh có thể thiết kế để phá một điều kiện cần, ví dụ:

- Quy định thứ tự toàn cục để loại bỏ circular wait.
- Yêu cầu lấy trước toàn bộ tài nguyên cần thiết nếu có thể để giảm hold-and-wait.
- Dùng no-wait hoặc abort khi không lấy được khóa.
- Dùng timestamp policy như wait-die hoặc wound-wait để quy định transaction nào được chờ hoặc bị hủy.

Trong hệ quản trị thực tế, việc lấy trước mọi khóa thường khó vì tập tài nguyên có thể phụ thuộc dữ liệu và kế hoạch thực thi. Quy tắc thứ tự khóa thường thực tế hơn.

### 11.2. Avoidance — tránh cấp phát vào trạng thái không an toàn

Deadlock avoidance đánh giá trạng thái cấp phát tài nguyên trước khi cấp thêm tài nguyên, nhằm chỉ đi vào trạng thái được chứng minh là an toàn.

Thuật toán Banker là ví dụ kinh điển trong hệ điều hành: cần biết trước nhu cầu tối đa của từng tiến trình và số tài nguyên sẵn có để xác định có tồn tại thứ tự hoàn tất an toàn hay không.

Trong cơ sở dữ liệu, thường khó biết trước mọi hàng hoặc khoảng khóa mà một transaction sẽ cần, nhất là khi truy vấn phụ thuộc dữ liệu và execution plan. Vì vậy, cơ chế avoidance kiểu Banker không phải cách triển khai phổ biến cho khóa giao dịch thông thường.

### 11.3. Detection and recovery — phát hiện rồi phục hồi

Đây là cách tiếp cận phổ biến trong DBMS:

1. Cho phép giao dịch lấy khóa theo nhu cầu.
2. Khi một giao dịch phải chờ, cập nhật thông tin phụ thuộc.
3. Detector tìm chu trình trong wait-for graph.
4. Nếu có chu trình, chọn victim.
5. Rollback victim và giải phóng khóa.
6. Các giao dịch còn lại tiếp tục.

Cách này chấp nhận rằng deadlock đôi lúc sẽ xảy ra, nhưng tự động phát hiện và phá chu trình.

### 11.4. Wait-die và wound-wait

Một số hệ thống hoặc thuật toán điều khiển đồng thời dùng timestamp của transaction để tránh chu trình.

**Wait-die:**

- Transaction cũ hơn được phép chờ transaction trẻ hơn.
- Transaction trẻ hơn không được chờ transaction cũ hơn; nó bị abort (die) và có thể chạy lại.

**Wound-wait:**

- Transaction cũ hơn có thể buộc transaction trẻ hơn nhả tài nguyên bằng cách hủy transaction trẻ.
- Transaction trẻ hơn nếu cần tài nguyên của transaction cũ thì phải chờ.

Các quy tắc này áp đặt thứ tự theo tuổi transaction, giúp ngăn circular wait. Đây là thuật toán khái niệm; không nên cho rằng mọi DBMS mặc định dùng wait-die hoặc wound-wait.

## 12. Chẩn đoán bằng đồ thị chờ trong PostgreSQL

### 12.1. Tìm phiên đang chờ và blocker

Có thể xem trạng thái session và sự kiện chờ:

~~~sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Dùng pg_blocking_pids để tìm các PID đang chặn một phiên:

~~~sql
SELECT
    pid AS blocked_pid,
    pg_blocking_pids(pid) AS blocking_pids,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
~~~

Hàm pg_blocking_pids trả về các process đang chặn process được truyền vào. Có thể dùng kết quả để dựng các cạnh từ blocked PID đến blocking PID.

### 12.2. Xem thông tin khóa

~~~sql
SELECT
    locktype,
    mode,
    granted,
    relation::regclass AS relation,
    page,
    tuple,
    transactionid,
    pid
FROM pg_locks
ORDER BY pid, granted;
~~~

Cần kết hợp pg_locks với pg_stat_activity vì một phiên có thể đang chờ transaction ID của phiên khác. Không phải mọi lần chờ đều hiển thị như khóa hàng trực tiếp trên relation/page/tuple.

### 12.3. Log deadlock

PostgreSQL ghi thông tin deadlock vào server log khi phát hiện. Có thể cấu hình log_lock_waits và deadlock_timeout để hỗ trợ điều tra chờ khóa kéo dài và deadlock. Giá trị cấu hình cần phù hợp với workload và chính sách log.

SQLSTATE thường gặp cho deadlock là **40P01** (deadlock_detected). Ứng dụng nên phân biệt nó với **40001** (serialization_failure), vì hai lỗi có nguyên nhân và thông tin chẩn đoán khác nhau.

## 13. Chẩn đoán trong MySQL InnoDB

### 13.1. Xem khóa đang giữ và đang chờ

Trong MySQL có thể truy vấn Performance Schema:

~~~sql
SELECT *
FROM performance_schema.data_locks;
~~~

~~~sql
SELECT *
FROM performance_schema.data_lock_waits;
~~~

Các bảng này cung cấp thông tin về lock object, index, lock mode, trạng thái được cấp hoặc đang chờ và quan hệ giữa request với blocker. Cột cụ thể có thể khác theo phiên bản.

### 13.2. Deadlock gần nhất

Dùng:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Phần **LATEST DETECTED DEADLOCK** thường cho biết hai hoặc nhiều transaction tham gia, câu lệnh liên quan, khóa đang giữ và khóa đang chờ, cùng transaction bị rollback.

Đây là báo cáo deadlock gần nhất được lưu trong trạng thái InnoDB, không phải lịch sử đầy đủ mọi deadlock. Với hệ thống cần điều tra dài hạn, hãy cấu hình ghi log deadlock phù hợp và thu thập thông tin Performance Schema.

### 13.3. Mã lỗi

InnoDB thường báo deadlock bằng error 1213 với SQLSTATE **40001**. Lock wait timeout thường là error 1205. Ứng dụng phải phân biệt deadlock với timeout thay vì gom chúng thành một lỗi "database busy".

InnoDB có thể chọn victim dựa trên chi phí rollback và thông tin nội bộ. Không nên dựa vào giả định rằng transaction có ít câu SQL hơn luôn bị hủy.

## 14. Chẩn đoán trong SQL Server

### 14.1. Xác định request đang bị chặn

Có thể xem các request và session:

~~~sql
SELECT
    session_id,
    blocking_session_id,
    wait_type,
    wait_time,
    wait_resource,
    status,
    command
FROM sys.dm_exec_requests
WHERE blocking_session_id <> 0;
~~~

blocking_session_id giúp tìm blocker trực tiếp. Để hiểu transaction nào giữ khóa, có thể kết hợp sys.dm_tran_locks, sys.dm_exec_sessions và sys.dm_exec_requests.

### 14.2. Thu thập deadlock graph

SQL Server có thể ghi deadlock graph qua Extended Events, thường trong session system_health, hoặc qua một Extended Events session được cấu hình riêng.

Deadlock XML thường chứa:

- process-list: các session/transaction tham gia.
- resource-list: tài nguyên và các owner/waiter.
- victim-list: transaction được chọn làm victim.

Đọc cả process-list và resource-list để xác định thứ tự khóa. Một câu lệnh có thể đang chờ key lock nhưng trước đó đã lấy khóa ở bảng hoặc index khác.

SQL Server thường báo lỗi 1205 cho transaction bị chọn làm deadlock victim. Ứng dụng nên rollback/khởi tạo transaction mới và retry toàn bộ nghiệp vụ nếu phù hợp.

## 15. Chẩn đoán trong Oracle

Oracle cung cấp các view động để xem session blocking và lock:

- V$SESSION có các cột như BLOCKING_SESSION, FINAL_BLOCKING_SESSION, EVENT và SECONDS_IN_WAIT tùy phiên bản.
- V$LOCK cho thông tin lock type, mode held và mode requested.
- Trace file có thể chứa thông tin về deadlock graph khi Oracle phát hiện deadlock.

Ví dụ truy vấn session đang bị chặn:

~~~sql
SELECT
    sid,
    serial#,
    blocking_session,
    event,
    seconds_in_wait,
    sql_id
FROM v$session
WHERE blocking_session IS NOT NULL;
~~~

Chi tiết quyền truy cập các view phụ thuộc quyền DBA và cấu hình hệ thống. Hãy dùng trace/deadlock report để xác định resource và transaction trong chu trình, thay vì chỉ dựa vào một dòng blocker hiện tại.

## 16. Cách đọc một deadlock report

Một deadlock report thường có nhiều chi tiết. Có thể đọc theo thứ tự:

1. **Tìm victim.** Xác định session/transaction nào đã bị hủy.
2. **Liệt kê các giao dịch trong chu trình.** Không chỉ ghi nhận hai session được nhắc đầu tiên.
3. **Xác định tài nguyên.** Bảng, hàng, index key, page, range, metadata hoặc application lock.
4. **Xác định khóa đang giữ.** Mỗi giao dịch đã giữ mode nào trên tài nguyên nào?
5. **Xác định khóa đang yêu cầu.** Giao dịch muốn lấy mode nào và vì sao không tương thích?
6. **Lần theo thứ tự thao tác.** Câu lệnh nào đã lấy khóa trước đó trong transaction?
7. **Tìm thứ tự ngược nhau.** Hai luồng có đi qua cùng tập tài nguyên theo thứ tự khác nhau không?
8. **Kiểm tra đường truy cập.** Execution plan có scan rộng, dùng index khác nhau hoặc phát sinh khóa phạm vi không?
9. **Kiểm tra thao tác ẩn.** Có trigger, cascade, constraint check hoặc stored procedure tham gia không?
10. **Chọn thay đổi thiết kế.** Thống nhất thứ tự khóa, thu hẹp truy vấn, thêm index phù hợp hoặc rút ngắn transaction.

Một report có thể hiển thị câu lệnh cuối cùng của transaction, nhưng câu lệnh đó chưa chắc là nơi lấy khóa đầu tiên. Muốn hiểu chu trình, cần xem toàn bộ tài nguyên đang giữ và đang chờ.

## 17. Ví dụ dựng đồ thị từ hai session

Giả sử có bảng inventory:

~~~sql
CREATE TABLE inventory (
    sku VARCHAR(20) PRIMARY KEY,
    quantity INT NOT NULL
);
~~~

T1 cập nhật A trước rồi B:

~~~sql
-- Session 1
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'A';

-- Chưa COMMIT
~~~

T2 cập nhật B trước rồi A:

~~~sql
-- Session 2
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'B';

-- Chưa COMMIT
~~~

Sau đó Session 1 chạy:

~~~sql
UPDATE inventory
SET quantity = quantity + 1
WHERE sku = 'B';
~~~

Session 1 chờ khóa trên B do Session 2 giữ. Tạo cạnh:

\[
T1 \rightarrow T2
\]

Session 2 chạy:

~~~sql
UPDATE inventory
SET quantity = quantity + 1
WHERE sku = 'A';
~~~

Session 2 chờ khóa trên A do Session 1 giữ. Tạo cạnh:

\[
T2 \rightarrow T1
\]

Đồ thị cuối:

~~~text
T1 ─────────> T2
 ^             |
 |             |
 └─────────────┘
~~~

Có chu trình T1 → T2 → T1. Hệ quản trị phát hiện deadlock và hủy một transaction. Transaction còn lại tiếp tục khi khóa được giải phóng.

Cách thiết kế giảm nguy cơ là mọi luồng cập nhật theo cùng thứ tự khóa, chẳng hạn A rồi B. Nếu dữ liệu được xác định động, ứng dụng có thể sắp xếp khóa theo một thứ tự ổn định trước khi cập nhật. Cần bảo đảm thứ tự thực tế của các thao tác khóa, không chỉ thứ tự hiển thị trong code.

## 18. Giảm nguy cơ tạo chu trình

### 18.1. Thống nhất thứ tự lấy khóa

Quy định thứ tự toàn cục cho tài nguyên:

- Theo loại bảng: customer trước order, order trước inventory.
- Theo khóa chính tăng dần khi cập nhật nhiều hàng cùng bảng.
- Theo thứ tự tài nguyên nghiệp vụ đã thống nhất giữa các service.
- Với advisory lock, chuẩn hóa namespace và thứ tự khóa.

Nếu mọi transaction lấy cùng tài nguyên theo một thứ tự, sẽ khó tạo chu trình circular wait do thứ tự ngược nhau.

### 18.2. Giữ transaction ngắn

Khóa giao dịch thường được giữ đến COMMIT hoặc ROLLBACK. Hãy:

- Chỉ mở transaction khi cần tính nguyên tử.
- Không chờ người dùng nhập liệu trong transaction.
- Không gọi HTTP/RPC hoặc dịch vụ thanh toán khi đang giữ khóa nếu có thể tách ra.
- Tránh xử lý tệp lớn và tính toán dài trong transaction.
- Kết thúc transaction ngay sau khi hoàn thành thay đổi cần thiết.

Transaction ngắn làm giảm thời gian tài nguyên nằm trong trạng thái được giữ, từ đó giảm số giao dịch có thể chạm vào cùng chuỗi phụ thuộc.

### 18.3. Thu hẹp tập dữ liệu được truy cập

Index phù hợp và điều kiện sargable giúp tìm đúng hàng nhanh hơn. Tránh scan rộng không cần thiết trong UPDATE, DELETE và locking read.

Đối với InnoDB, phạm vi index scan có thể ảnh hưởng record/gap/next-key locks. Với SQL Server SERIALIZABLE, đường truy cập ảnh hưởng key-range locks. Với PostgreSQL SSI, đường scan có thể ảnh hưởng độ chi tiết predicate tracking.

Không nên thêm index tùy tiện. Index mới cũng cần được duy trì trong thao tác ghi và có thể tạo thêm điểm tranh chấp.

### 18.4. Tránh khóa chuyển đổi không cần thiết

Nếu transaction chắc chắn sẽ cập nhật hàng, hãy cân nhắc dùng locking read với mode phù hợp ngay từ đầu thay vì nhiều transaction cùng giữ S rồi cùng nâng lên X.

Tuy nhiên, lấy khóa mạnh từ đầu làm giảm concurrency. Chỉ dùng khi nghiệp vụ thực sự cần đọc rồi cập nhật hàng đó trong cùng transaction.

### 18.5. Xử lý hàng loạt theo thứ tự ổn định

Một batch UPDATE/DELETE có thể tác động đến nhiều hàng. Nếu hai batch chạy cùng lúc nhưng chạm hàng theo thứ tự khác nhau, chúng có thể deadlock.

Hãy chọn thứ tự xử lý ổn định và chia lô nếu nghiệp vụ cho phép. Kiểm tra execution plan để hiểu thứ tự truy cập thực tế; thứ tự trong source code không luôn bảo đảm thứ tự lock acquisition của một câu lệnh set-based.

### 18.6. Dùng no-wait hoặc skip-locked đúng mục đích

Một số hệ quản trị hỗ trợ NOWAIT để câu lệnh thất bại ngay nếu không lấy được khóa, hoặc SKIP LOCKED để bỏ qua hàng đang bị khóa.

Các tùy chọn này có thể tránh một số quan hệ chờ, nhưng thay đổi semantics:

- NOWAIT chuyển lock wait thành lỗi tức thời.
- SKIP LOCKED có thể trả về tập hàng không đầy đủ.
- SKIP LOCKED phù hợp với phân phối công việc trong queue hơn là truy vấn cần kết quả đầy đủ.
- Cả hai không thay thế ràng buộc và kiểm soát nhất quán.

Chúng có thể giảm blocking trong một luồng xử lý, nhưng không phải cách sửa mọi deadlock.

## 19. Retry sau deadlock

### 19.1. Retry toàn bộ đơn vị nghiệp vụ

Khi transaction bị rollback vì deadlock, các quyết định trước đó có thể dựa trên dữ liệu không còn phù hợp. Thông thường nên bắt đầu transaction mới và chạy lại toàn bộ đơn vị công việc.

Không chỉ gửi lại câu SQL cuối cùng nếu các bước đọc/tính toán trước đó nằm trong cùng transaction và phụ thuộc vào trạng thái cũ.

### 19.2. Giới hạn số lần thử

Một chính sách retry nên có:

- Số lần thử tối đa.
- Backoff tăng dần.
- Jitter để các request không retry cùng lúc.
- Phân loại lỗi chính xác.
- Log số lần thử và thời gian chờ.
- Kết quả rõ ràng khi hết số lần thử.

Retry không giới hạn có thể tạo retry storm và làm contention nặng hơn.

### 19.3. Bảo vệ tác dụng phụ bên ngoài

Nếu transaction gửi email, gọi thanh toán hoặc phát sự kiện trước khi commit, retry có thể thực hiện tác dụng phụ nhiều lần.

Dùng idempotency key, transactional outbox hoặc quy trình bù trừ phù hợp. Rollback database không thể tự thu hồi một HTTP request mà dịch vụ ngoài đã xử lý thành công.

### 19.4. Phân biệt lỗi deadlock với timeout

Không phải mọi lỗi chờ đều nên retry theo cùng cách:

| Lỗi | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Deadlock | Có chu trình chờ; hệ quản trị hủy một transaction | Retry toàn transaction nếu an toàn |
| Lock timeout | Chờ vượt thời hạn; có thể không có chu trình | Tìm blocker, quyết định retry hoặc trả lỗi |
| Statement timeout | Câu lệnh chạy quá thời gian cho phép | Điều tra plan/tải; không mặc định là deadlock |
| Serialization failure | Lịch thực thi không đáp ứng mức cô lập | Retry transaction theo chính sách |
| Constraint violation | Dữ liệu vi phạm ràng buộc | Xử lý nghiệp vụ, không retry mù quáng |

Mã lỗi và trạng thái transaction khác nhau theo hệ quản trị và driver. Cần ánh xạ cụ thể trong lớp truy cập dữ liệu.

## 20. Những nhầm lẫn thường gặp

**“Có nhiều giao dịch đang chờ là có deadlock.”**

Sai. Có thể tất cả đều chờ một blocker duy nhất đang chạy và sẽ COMMIT. Cần tìm chu trình trong đồ thị chờ.

**“Chỉ cần hai giao dịch chờ nhau mới là deadlock.”**

Sai. Chu trình có thể gồm ba hoặc nhiều giao dịch.

**“Nếu A chờ B thì B chắc chắn đang chờ A.”**

Sai. Một cạnh đơn lẻ chỉ cho biết A bị B chặn. Cần lần theo các cạnh tiếp theo để xem có đường quay về A hay không.

**“Mũi tên T1 → T2 có nghĩa T1 chặn T2.”**

Sai theo quy ước wait-for graph phổ biến trong bài này. T1 → T2 nghĩa T1 đang chờ T2; T2 là blocker của T1.

**“Deadlock graph và serialization graph là một.”**

Sai. Một đồ thị biểu diễn chờ tài nguyên; đồ thị kia biểu diễn thứ tự xung đột trong lịch thực thi. Chu trình có ý nghĩa khác nhau.

**“Tăng lock timeout sẽ giải quyết deadlock.”**

Sai. Timeout giới hạn thời gian chờ. Nó có thể khiến một transaction bỏ cuộc sau một thời gian, nhưng không sửa thứ tự lấy khóa gây chu trình.

**“Hệ quản trị luôn hủy transaction đang chờ lâu nhất.”**

Sai. Chính sách chọn victim phụ thuộc sản phẩm và chi phí rollback/ưu tiên. Phải đọc deadlock report để biết giao dịch nào thực sự bị chọn.

**“Chỉ câu SQL bị lỗi bị rollback.”**

Không thể mặc định. Nhiều hệ quản trị rollback toàn bộ transaction được chọn làm victim. Ứng dụng phải kiểm tra trạng thái transaction và bắt đầu transaction mới khi retry.

**“Deadlock chỉ do câu SELECT FOR UPDATE.”**

Sai. INSERT, UPDATE, DELETE, UNIQUE/FK checks, cascade, trigger, index range và application locks đều có thể tham gia chu trình.

## 21. Quy trình dựng và phân tích đồ thị chờ

Khi một deadlock xảy ra, hãy làm theo các bước:

1. Thu thập deadlock report hoặc lock-wait snapshot từ hệ quản trị.
2. Xác định các transaction/session tham gia và transaction được chọn làm victim.
3. Với từng transaction, liệt kê tài nguyên đang giữ và tài nguyên đang yêu cầu.
4. Tạo cạnh từ waiter đến blocker theo đúng chiều.
5. Lần theo cạnh cho đến khi quay lại nút bắt đầu hoặc đến nút không còn chờ.
6. Xác định chu trình và tài nguyên làm khép kín chu trình.
7. Đọc các câu lệnh trước đó trong transaction, kể cả trigger, cascade và stored procedure.
8. Kiểm tra index, execution plan, isolation level và lock mode.
9. Chọn thay đổi để phá circular wait hoặc giảm thời gian giữ khóa.
10. Chạy lại workload đồng thời và xác nhận chu trình không còn xuất hiện hoặc tần suất giảm.

Ví dụ bảng ghi chép:

| Transaction | Đang giữ | Đang chờ | Cạnh |
|---|---|---|---|
| T1 | Hàng A | Hàng B do T2 giữ | T1 → T2 |
| T2 | Hàng B | Hàng C do T3 giữ | T2 → T3 |
| T3 | Hàng C | Hàng A do T1 giữ | T3 → T1 |

Chu trình T1 → T2 → T3 → T1 xác nhận deadlock trong đồ thị chờ.

## 22. Bài tập đọc đồ thị

### Bài 1: Chuỗi hay chu trình?

Cho đồ thị:

~~~text
T1 ──> T2 ──> T3
~~~

T3 không chờ giao dịch nào khác.

Đây là chuỗi chờ. Nếu T3 hoàn tất và nhả khóa, T2 rồi T1 có thể tiếp tục. Không có chu trình.

### Bài 2: Hai giao dịch

~~~text
T1 ──> T2
^       |
|       v
└───────┘
~~~

Có chu trình T1 → T2 → T1. Đây là deadlock theo đồ thị chờ.

### Bài 3: Nhiều giao dịch

~~~text
T1 ──> T2 ──> T3 ──> T4
        ^             |
        |             v
        └─────────────┘
~~~

Chu trình là T2 → T3 → T4 → T2. T1 đang chờ T2 và sẽ bị ảnh hưởng bởi việc giải quyết chu trình, nhưng T1 không nằm trong chu trình.

### Bài 4: Một blocker có nhiều waiter

~~~text
T2 ──┐
T3 ──┼──> T1
T4 ──┘
~~~

Nếu T1 không chờ ai, đây là nhiều giao dịch bị một blocker chặn. Chưa có deadlock.

### Bài 5: Phân biệt hai loại đồ thị

Một lịch thực thi có chu trình trong precedence graph nhưng các câu đọc đều dùng MVCC snapshot và không chờ khóa. Điều đó có nghĩa lịch có vấn đề về conflict serializability, nhưng không thể kết luận có deadlock.

Ngược lại, khi wait-for graph có chu trình, các giao dịch đang chờ tài nguyên theo vòng tròn; đó là deadlock dù chưa cần phân tích serialization graph.

## 23. Câu hỏi định hướng khi đọc deadlock graph

Khi nhìn một đồ thị chờ, hãy tự hỏi:

- Nút nào là waiter và nút nào là blocker?
- Mũi tên đang theo quy ước waiter → blocker hay chiều khác của công cụ?
- Mỗi cạnh bắt nguồn từ tài nguyên và lock mode nào?
- Có nhiều blocker cho một yêu cầu không?
- Có wait queue hoặc lock conversion nào tạo thêm phụ thuộc không?
- Chu trình ngắn nhất gồm những transaction nào?
- Giao dịch ngoài chu trình nào đang chờ các transaction trong chu trình?
- Có trigger, cascade, foreign key hoặc unique index tham gia không?
- Execution plan có làm phạm vi khóa rộng hơn dự kiến không?
- Hệ quản trị đã chọn victim nào và rollback ở phạm vi nào?
- Có thể áp dụng thứ tự khóa toàn cục hoặc giảm thời gian giữ khóa không?
- Ứng dụng retry toàn bộ transaction có an toàn không?

Đồ thị chờ biến một tình huống "câu SQL bị treo" thành một mô hình phụ thuộc có thể phân tích. Mỗi cạnh giải thích ai đang chờ ai; chu trình chỉ ra nhóm giao dịch không thể tự tiến triển; deadlock report cho biết tài nguyên và lock mode tạo ra các cạnh đó. Khi kết hợp đồ thị với thứ tự câu lệnh, execution plan và ràng buộc dữ liệu, ta có thể xác định nguyên nhân thực tế và sửa cách các giao dịch lấy, giữ và giải phóng khóa.
