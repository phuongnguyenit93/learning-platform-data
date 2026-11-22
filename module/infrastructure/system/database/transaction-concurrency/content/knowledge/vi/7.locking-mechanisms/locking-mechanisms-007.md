# Khóa dữ liệu khác gì với latch bảo vệ cấu trúc nội bộ?

Trong một hệ quản trị cơ sở dữ liệu, nhiều transaction có thể chạy đồng thời và cùng truy cập những vùng dữ liệu liên quan. Để tránh xung đột, database engine cần đồng bộ ở nhiều lớp. Hai cơ chế thường được nhắc đến là **khóa dữ liệu (lock)** và **latch**.

Cả hai đều có thể khiến một luồng phải chờ luồng khác, nhưng chúng bảo vệ những thứ khác nhau:

- **Lock** điều phối quyền truy cập vào tài nguyên dữ liệu theo ngữ nghĩa transaction, nhằm duy trì các quy tắc nhất quán và cô lập.
- **Latch** bảo vệ cấu trúc dữ liệu nội bộ đang nằm trong bộ nhớ, để nhiều luồng không đồng thời sửa hoặc đọc một cấu trúc ở trạng thái không an toàn.

Một thao tác SQL có thể cần cả lock lẫn latch. Hiểu sự khác nhau giúp phân biệt một transaction đang chờ quyền truy cập dữ liệu với một luồng đang chờ database engine hoàn tất thao tác trên cấu trúc bộ nhớ.

## 1. Lock bảo vệ quyền truy cập vào tài nguyên dữ liệu

Lock là cơ chế kiểm soát đồng thời ở cấp độ dữ liệu. Database engine cấp lock khi transaction cần đọc, ghi hoặc giữ quyền truy cập đối với một tài nguyên mà transaction khác cũng có thể cần.

Tài nguyên được khóa có thể có nhiều mức hạt khác nhau, tùy engine và kế hoạch thực thi:

- Một dòng dữ liệu (row).
- Một khóa trong index hoặc một khoảng khóa (key range).
- Một page theo nghĩa tài nguyên khóa của database.
- Một bảng, partition hoặc tài nguyên có phạm vi rộng hơn.

Mục tiêu của lock là bảo đảm các transaction tuân thủ quy tắc truy cập mà isolation level và cơ chế concurrency control của database yêu cầu. Ví dụ, nếu hai transaction cùng muốn cập nhật một dòng, engine phải điều phối để chúng không ghi đè kết quả của nhau hoặc quan sát trạng thái trái với mức cô lập đã cam kết.

### Các chế độ lock thường gặp

Hai chế độ cơ bản là:

- **Shared lock (S):** cho phép đọc theo quy tắc tương thích của engine. Nhiều shared lock thường có thể cùng tồn tại trên một tài nguyên.
- **Exclusive lock (X):** dành cho thao tác ghi hoặc thay đổi tài nguyên. Exclusive lock thường xung đột với các lock khác trên cùng tài nguyên.

Các hệ quản trị còn có những chế độ và quy tắc phức tạp hơn, chẳng hạn update lock, intent lock và key-range lock. Bảng tương thích cụ thể phụ thuộc vào database engine.

Ví dụ, transaction T1 cập nhật dòng có **id = 42**:

~~~sql
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE id = 42;

-- Transaction tiếp tục làm các công việc khác.
COMMIT;
~~~

Engine thường phải giữ quyền ghi phù hợp trên dòng hoặc khóa tương ứng để transaction khác không thực hiện một thao tác xung đột trong khoảng thời gian cần thiết. Với thao tác ghi, lock thường được giữ đến **COMMIT** hoặc **ROLLBACK**. Thời điểm giải phóng lock đọc có thể khác nhau tùy isolation level và engine; một số chế độ chỉ giữ shared lock trong thời gian ngắn, còn cơ chế MVCC có thể cho phép reader đọc phiên bản dữ liệu mà không cần shared lock kiểu truyền thống.

Điểm quan trọng là **thời gian sống của lock gắn với quy tắc concurrency control của transaction**, chứ không chỉ với vài lệnh CPU đang sửa một cấu trúc trong RAM.

## 2. Latch bảo vệ cấu trúc dữ liệu nội bộ trong bộ nhớ

Latch là cơ chế đồng bộ mức thấp mà database engine dùng để bảo vệ những cấu trúc nội bộ khi nhiều luồng cùng thao tác trên chúng. Những cấu trúc này thường đang được giữ trong bộ nhớ và có thể bị hỏng về mặt cấu trúc nếu nhiều luồng sửa đồng thời mà không được đồng bộ.

Một số ví dụ:

- Nội dung một database page đang được nạp trong buffer pool.
- Các node của B-tree khi engine tìm kiếm, chèn khóa hoặc tách node.
- Bucket và liên kết trong một hash table nội bộ.
- Danh sách quản lý buffer, free list hoặc cấu trúc của lock manager.

Hãy hình dung một B-tree. Khi một luồng chèn khóa mới, node lá có thể đầy và cần được tách thành hai node. Trong lúc engine cập nhật các con trỏ, khóa phân cách và liên kết giữa các node, một luồng khác không được nhìn thấy cấu trúc ở trạng thái mới chỉ một nửa. Latch giúp bảo vệ đoạn thao tác nội bộ đó.

Latch thường được giữ trong **một critical section ngắn**: lấy latch, đọc hoặc thay đổi cấu trúc, rồi nhả latch ngay khi thao tác an toàn đã hoàn tất. Nó không được giữ đến khi transaction commit chỉ vì transaction vẫn còn hoạt động.

Các engine có thể triển khai latch bằng những primitive đồng bộ khác nhau, chẳng hạn mutex, read-write latch hoặc spin latch. Một số latch hỗ trợ nhiều luồng cùng đọc nhưng chỉ cho phép một luồng ghi; một số cơ chế có thể bận chờ trong thời gian ngắn thay vì đưa luồng vào trạng thái ngủ. Tên gọi và chi tiết triển khai thay đổi giữa các hệ quản trị.

Latch không quyết định transaction nào được phép đọc hoặc cập nhật một dòng theo isolation level. Nó bảo đảm engine thao tác an toàn trên biểu diễn nội bộ của dữ liệu trong bộ nhớ.

## 3. So sánh lock và latch

| Khía cạnh | Lock | Latch |
|---|---|---|
| Mục đích | Điều phối quyền truy cập dữ liệu giữa các transaction | Bảo vệ cấu trúc nội bộ khi nhiều luồng cùng thao tác |
| Thứ được bảo vệ | Tài nguyên dữ liệu theo ngữ nghĩa database, như row, key, range, table | Cấu trúc và nội dung đang được dùng trong bộ nhớ, như page trong buffer pool hoặc node index |
| Lý do tồn tại | Duy trì isolation và tính đúng đắn của thao tác dữ liệu đồng thời | Ngăn cấu trúc bộ nhớ rơi vào trạng thái không nhất quán trong lúc đọc hoặc sửa |
| Chủ thể sử dụng | Thường gắn với transaction hoặc phạm vi sở hữu lock do engine quản lý | Thường gắn với luồng thực thi đang đi vào một đoạn mã cần bảo vệ |
| Thời gian giữ | Theo quy tắc concurrency control; lock ghi thường tồn tại đến commit/rollback | Thường rất ngắn, đủ cho một thao tác nội bộ an toàn |
| Chế độ | S, X và các chế độ khác theo lock manager | Có thể có shared/exclusive hoặc các dạng latch chuyên biệt |
| Chờ đợi | Có thể kéo dài nếu transaction khác giữ lock lâu | Thường ngắn; có thể tăng cao khi nhiều luồng tranh chấp cùng cấu trúc |
| Deadlock | Có thể tạo chu trình chờ giữa các transaction; engine thường có cơ chế phát hiện và chọn transaction làm nạn nhân | Có thể có vấn đề thứ tự lấy latch hoặc tranh chấp nội bộ; cách xử lý phụ thuộc engine và không nhất thiết dùng bộ phát hiện deadlock transaction |
| Ý nghĩa với SQL | Ảnh hưởng trực tiếp đến việc transaction nào được phép tiếp tục trên tài nguyên dữ liệu | Là chi tiết đồng bộ nội bộ; không tự tạo ra cam kết isolation cho câu SQL |

Một điểm dễ gây nhầm lẫn là **page lock** và **page latch** có thể cùng nhắc đến một page, nhưng chúng mô tả hai lớp bảo vệ khác nhau.

- Page lock điều phối quyền truy cập logic vào page như một tài nguyên khóa của database.
- Page latch bảo vệ page đang nằm trong bộ nhớ khi engine đọc hoặc thay đổi nội dung và cấu trúc của page.

Cùng một page có thể chịu sự điều phối của lock ở cấp dữ liệu và latch ở cấp bộ nhớ. Tên tài nguyên giống nhau không làm hai cơ chế trở thành một.

## 4. Một thao tác cập nhật có thể cần cả hai

Giả sử hai transaction cập nhật hai dòng khác nhau, **id = 42** và **id = 43**. Hai dòng này có thể nằm trên cùng một database page và cùng được tìm thấy qua một index.

Ở góc độ lock:

- T1 cần quyền cập nhật dòng **id = 42**.
- T2 cần quyền cập nhật dòng **id = 43**.
- Nếu engine khóa ở mức row và không có xung đột khác, hai transaction có thể cùng được cấp lock vì chúng cập nhật hai tài nguyên logic khác nhau.

Ở góc độ latch:

- Cả hai dòng có thể nằm trên cùng một page trong buffer pool.
- Khi T1 đang sửa cấu trúc hoặc nội dung page, engine có thể giữ exclusive latch trên page đó.
- T2 có thể phải chờ latch trong một khoảng ngắn, dù lock trên dòng **id = 43** không xung đột với lock của T1 trên dòng **id = 42**.

Ví dụ này cho thấy **không có lock conflict vẫn có thể có latch contention**. Ngược lại, một transaction có thể phải chờ lock của transaction khác ngay cả khi không có luồng nào đang giữ latch trên page liên quan.

Có thể mô tả luồng xử lý khái quát như sau:

~~~text
Transaction T1
    |
    +-- Xin lock cho dòng id = 42
    |
    +-- Engine lấy latch để đọc/sửa page trong bộ nhớ
    |
    +-- Hoàn tất đoạn thao tác nội bộ và nhả latch
    |
    +-- Tiếp tục transaction
    |
    +-- COMMIT: giải phóng lock theo quy tắc của engine

Transaction T2
    |
    +-- Xin lock cho dòng id = 43
    |
    +-- Có thể được cấp lock vì đây là dòng khác
    |
    +-- Xin latch trên page đang được T1 bảo vệ
    |
    +-- Chờ T1 nhả latch, rồi tiếp tục
~~~

Đây là sơ đồ khái niệm để phân biệt hai lớp đồng bộ. Thứ tự lấy lock và latch thực tế, số lần lấy latch, cũng như loại tài nguyên được khóa phụ thuộc vào database engine và đường đi thực thi cụ thể.

## 5. Lock wait và latch wait nói lên điều gì?

Khi một truy vấn chậm vì phải chờ, cần xác định nó đang chờ loại tài nguyên nào.

**Lock wait** thường cho biết transaction đang chờ quyền truy cập vào một tài nguyên dữ liệu do transaction khác giữ. Thời gian chờ có thể dài nếu transaction giữ lock chưa commit, chạy nhiều công việc trong cùng transaction hoặc bị chặn bởi một chuỗi transaction khác. Cách xử lý thường bắt đầu bằng việc tìm transaction đang giữ lock, câu lệnh liên quan, thời điểm commit và thứ tự truy cập tài nguyên.

**Latch wait** thường cho biết các luồng đang tranh chấp một cấu trúc nội bộ trong bộ nhớ. Nguyên nhân có thể là nhiều luồng cùng truy cập một page nóng, một vùng index thường xuyên thay đổi hoặc một cấu trúc quản lý nội bộ bị tranh chấp. Hướng điều tra là xác định cấu trúc nào đang bị tranh chấp và vì sao nhiều luồng tập trung vào đó.

Tên wait cụ thể phụ thuộc vào sản phẩm. Chẳng hạn, trong SQL Server:

- Nhóm wait **LCK_M_*** thường liên quan đến việc chờ lock.
- **PAGELATCH_*** thường liên quan đến việc chờ latch trên page đang ở trong bộ nhớ.
- **PAGEIOLATCH_*** liên quan đến việc chờ thao tác I/O của page; đây là tín hiệu cần xem xét đường đọc/ghi lưu trữ, không nên đồng nhất với tranh chấp latch thuần túy trên page đã có sẵn trong RAM.

Không nên kết luận nguyên nhân chỉ từ tên wait. Cần xem tài nguyên, session/transaction liên quan, thời lượng chờ và chỉ số của chính database engine đang dùng.

## 6. Deadlock của lock và vấn đề đồng bộ latch

Deadlock transaction thường xảy ra khi các transaction giữ những lock khác nhau rồi chờ tài nguyên của nhau:

~~~text
T1 giữ lock trên A, chờ lock trên B
T2 giữ lock trên B, chờ lock trên A
~~~

Không transaction nào có thể tiếp tục nếu không có một bên nhường tài nguyên. Database engine thường phát hiện chu trình chờ và chọn một transaction làm deadlock victim để rollback, giải phóng lock cho transaction còn lại.

Ở lớp latch, lỗi thứ tự lấy latch cũng có thể tạo ra chu trình chờ giữa các luồng nội bộ. Vì latch thường bảo vệ critical section ngắn, engine cố gắng giới hạn thời gian giữ latch, kiểm soát thứ tự lấy latch và dùng các thuật toán đồng bộ phù hợp. Cơ chế phát hiện hoặc xử lý phụ thuộc vào cách triển khai của từng engine; không nên mặc định rằng latch deadlock được xử lý giống hệt transaction deadlock.

Điểm cần nhớ: lock deadlock thường liên quan đến chuỗi phụ thuộc giữa transaction và tài nguyên dữ liệu; vấn đề latch liên quan đến cách các luồng nội bộ đồng bộ khi truy cập cấu trúc bộ nhớ.

## 7. Những nhầm lẫn thường gặp

**“Latch là một loại lock được giữ đến commit.”**

Không. Latch thường chỉ bảo vệ một đoạn thao tác nội bộ ngắn. Transaction có thể tiếp tục chạy rất lâu sau khi latch đã được nhả.

**“Không có lock wait thì database không bị nghẽn do đồng thời.”**

Không đúng. Nhiều luồng có thể tranh chấp cùng một page hoặc cấu trúc bộ nhớ, tạo latch contention dù chúng không xung đột về quyền truy cập các dòng dữ liệu.

**“Page lock và page latch là một.”**

Không. Page lock điều phối quyền truy cập vào page như tài nguyên dữ liệu; page latch bảo vệ page trong bộ nhớ khi engine thao tác với nó.

**“Dùng MVCC thì không cần latch.”**

Không. MVCC có thể giảm nhu cầu dùng một số shared lock giữa reader và writer, tùy engine. Database vẫn cần đồng bộ buffer pool, index, page và các cấu trúc nội bộ khác. MVCC giải quyết một phần bài toán visibility và concurrency control; latch giải quyết bài toán an toàn khi truy cập cấu trúc bộ nhớ.

**“Thấy một session đang chờ là có thể tăng timeout để giải quyết.”**

Timeout chỉ thay đổi thời gian một thao tác sẵn sàng chờ trước khi thất bại. Nó không loại bỏ lock conflict hoặc latch contention. Cần xác định đúng loại chờ và nguyên nhân trước khi thay đổi cấu hình.

## Kết luận

Lock và latch cùng hỗ trợ database engine xử lý nhiều luồng đồng thời, nhưng nằm ở hai lớp khác nhau. Lock quyết định transaction được phép truy cập tài nguyên dữ liệu như thế nào để bảo đảm concurrency control. Latch giữ cho cấu trúc nội bộ trong bộ nhớ an toàn trong lúc engine đọc hoặc thay đổi chúng.

Khi phân tích một truy vấn bị chặn, hãy xác định nó đang chờ **quyền truy cập dữ liệu** hay đang chờ **một đoạn thao tác nội bộ trên bộ nhớ**. Phân biệt được hai trường hợp này sẽ dẫn đến hướng điều tra phù hợp hơn.
