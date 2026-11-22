# Serializable Snapshot Isolation và phát hiện phụ thuộc nguy hiểm trong PostgreSQL

**Serializable Snapshot Isolation (SSI)** là cơ chế PostgreSQL dùng để thực thi mức cô lập giao dịch `SERIALIZABLE` trong môi trường nhiều transaction đồng thời. Nó kết hợp lợi thế đọc theo **MVCC snapshot** với việc **theo dõi phụ thuộc đọc–ghi** để phát hiện những lịch thực thi có nguy cơ không thể tương đương với một thứ tự chạy tuần tự. Thay vì luôn khóa và buộc các giao dịch chạy lần lượt, PostgreSQL thường để chúng tiếp tục, rồi **hủy một giao dịch khi cần** để bảo đảm tính tuần tự hóa của những giao dịch được commit.

Điểm khó của SSI không nằm ở cú pháp:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

mà là câu hỏi: **Tại sao hai transaction đều đọc dữ liệu đã commit, đều có snapshot nhất quán, cập nhật những hàng khác nhau, nhưng cuối cùng không thể cùng commit?** Câu trả lời nằm ở những **phụ thuộc nguy hiểm** (*dangerous structures*) giữa các transaction.

Bài học thuộc chương **MVCC** của module *Database Engine Relational PostgreSQL*. Nội dung đi từ snapshot isolation, serialization graph và quan hệ `rw-antidependency` đến cách SSI dùng `SIReadLock</BT>, ví dụ write skew hai phiên, cách đọc lỗi `SQLSTATE 40001`, retry toàn bộ transaction, transaction read-only `DEFERRABLE`, quan sát vận hành và các bài tập thực hành.

## 1. Vì sao snapshot nhất quán vẫn có thể cho kết quả sai?

Giả sử bệnh viện có hai bác sĩ, An và Bình, cả hai đang trực. Quy tắc nghiệp vụ:

> Tại mọi thời điểm sau commit, phải có ít nhất một bác sĩ trực.

Mỗi bác sĩ có thể nghỉ nếu đang có ít nhất hai người trực. Hai giao dịch đồng thời thực hiện:

~~~text
Ban đầu:
  An.on_call   = true
  Bình.on_call = true
  count(on_call = true) = 2

T1 (An xin nghỉ)                 T2 (Bình xin nghỉ)
-------------------------------- --------------------------------
Đọc count = 2                    Đọc count = 2
An.on_call = false               Bình.on_call = false
COMMIT                           COMMIT

Kết quả nếu cả hai commit:
  An.on_call   = false
  Bình.on_call = false
  count = 0   <-- Vi phạm bất biến
~~~

Mỗi giao dịch đọc **một snapshot hợp lệ**, không ai đọc dữ liệu chưa commit. T1 và T2 cũng cập nhật **hai hàng khác nhau**, không nhất thiết tranh chấp cùng một row lock.

Đây là **write skew**: hai transaction đọc điều kiện chung nhưng ghi các phần khác nhau của dữ liệu, khiến kết hợp các thay đổi làm sai bất biến.

### 1.1. Snapshot isolation giải quyết gì?

Ở mức `REPEATABLE READ` của PostgreSQL, một transaction dùng snapshot nhất quán. Nó tránh việc hai SELECT thông thường trong cùng transaction nhìn thấy những commit mới khác nhau. Điều này ngăn nonrepeatable read và phantom read truyền thống.

Nhưng snapshot nhất quán chỉ bảo đảm **mỗi transaction nhìn vào một lát cắt ổn định**, không tự bảo đảm **kết quả kết hợp của nhiều transaction** vẫn tương đương chạy tuần tự.

### 1.2. SERIALIZABLE giải quyết gì?

Nếu hai giao dịch trên được thực hiện tuần tự:

~~~text
Thứ tự T1 -> T2:

T1 đọc count = 2, cho An nghỉ, commit.
T2 đọc count = 1, KHÔNG cho Bình nghỉ.
Kết quả còn Bình trực.
~~~

Nếu đảo thứ tự T2 → T1 cũng tương tự: người chạy thứ hai phải quan sát còn một bác sĩ và từ chối nghỉ.

Một lịch trong đó cả hai đều đọc count=2 rồi cùng commit nghỉ **không tương đương** với bất kỳ thứ tự tuần tự hợp lệ nào, với giả định cả hai giao dịch đều thực hiện kiểm tra trước khi cập nhật. SSI ngăn lịch commit đó.

## 2. Ôn lại MVCC và các mức isolation của PostgreSQL

PostgreSQL dùng **Multi-Version Concurrency Control (MVCC)** để quản lý khả năng nhìn thấy các phiên bản hàng. Transaction không phải khóa toàn database mỗi khi đọc.

Một sơ đồ đơn giản:

~~~text
Thời điểm s0: row X = 100  [đã commit]
T1 lấy snapshot S1
T2 cập nhật X = 200 và COMMIT
T1 SELECT X vẫn có thể thấy phiên bản 100 theo S1
T3 lấy snapshot mới và thấy phiên bản 200
~~~

Đây là mô hình logic về visibility, không phải sơ đồ vật lý heap/vacuum hoàn chỉnh.

### 2.1. Bốn tên, ba hành vi chính

| Isolation SQL | PostgreSQL thực hiện | Điểm cần nhớ |
|---|---|---|
| `READ UNCOMMITTED` | Như READ COMMITTED | Không dirty read |
| `READ COMMITTED` | Snapshot theo câu lệnh thông thường | Mỗi SELECT có thể thấy commit mới |
| `REPEATABLE READ` | Snapshot isolation | Snapshot ổn định, vẫn có thể write skew |
| `SERIALIZABLE` | Serializable Snapshot Isolation | Theo dõi xung đột và abort nếu lịch không an toàn |

### 2.2. So sánh nhanh

| Bất thường | READ COMMITTED | REPEATABLE READ PostgreSQL | SERIALIZABLE PostgreSQL |
|---|---|---|---|
| Dirty read | Ngăn | Ngăn | Ngăn |
| Nonrepeatable read | Có thể | Ngăn trong SELECT snapshot | Ngăn trong lịch commit hợp lệ |
| Phantom read truyền thống | Có thể | Ngăn trong SELECT snapshot | Ngăn |
| Read skew giữa nhiều statement | Có thể | Tránh bằng snapshot | Tránh |
| Write skew | Có thể | **Có thể** | Ngăn lịch commit không tuần tự hóa được |
| Serialization failure 40001 | Có thể gặp trong một số tình huống tùy cơ chế | Có thể do concurrent update | **Là một phần của cơ chế SSI** |

`SERIALIZABLE` không có nghĩa mỗi thao tác luôn thành công. Nó có nghĩa những **transaction được commit thành công** phải thỏa bảo đảm serializability. Một transaction có thể bị từ chối để giữ tính chất đó.

### 2.3. Snapshot bắt đầu khi nào?

Trong transaction REPEATABLE READ/SERIALIZABLE, snapshot phù hợp thường được thiết lập khi thực hiện câu lệnh cần snapshot đầu tiên, **không đơn giản ngay khi gõ BEGIN**.

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM some_table;

COMMIT;
~~~

Câu SQL này minh họa cấu trúc; cần bảng `some_table` nếu chạy nguyên văn. Khi thí nghiệm hai phiên, hãy chắc chắn SELECT đầu đã chạy ở mỗi phiên trước khi các transaction kia thay đổi và commit, để thiết lập những snapshot bạn muốn so sánh.

## 3. Serializability: thế nào là tương đương lịch tuần tự?

Một lịch transaction là **serial** nếu toàn bộ thao tác của một transaction hoàn thành trước khi transaction khác bắt đầu phần thao tác logic của nó:

~~~text
Lịch tuần tự 1:
  T1: READ -> CHECK -> WRITE -> COMMIT
  T2: READ -> CHECK -> WRITE -> COMMIT

Lịch tuần tự 2:
  T2: READ -> CHECK -> WRITE -> COMMIT
  T1: READ -> CHECK -> WRITE -> COMMIT
~~~

Trong thực tế PostgreSQL muốn nhiều giao dịch **chạy xen kẽ** để tăng throughput. Serializability yêu cầu lịch xen kẽ có kết quả phù hợp với **một** thứ tự tuần tự nào đó.

### 3.1. Không đồng nghĩa tuần tự hóa vật lý

PostgreSQL không buộc tất cả transaction SERIALIZABLE xếp một hàng chờ. Hai giao dịch không xung đột vẫn có thể chạy đồng thời và commit.

### 3.2. Không đồng nghĩa “thứ tự ID là thứ tự commit”

Sequence/identity không biểu diễn thứ tự serial của toàn transaction. Một giao dịch có thể nhận ID trước nhưng commit sau. Đừng dùng `id</BT> để suy luận tất cả quan hệ happens-before trong ứng dụng.

### 3.3. Không đồng nghĩa mọi quy tắc nghiệp vụ đều được biết

Nếu transaction chỉ chạy:

~~~sql
UPDATE doctors SET on_call = FALSE WHERE doctor_id = 1;
~~~

mà không hề kiểm tra “còn người trực”, SSI không thể tự suy ra quy tắc chưa được biểu diễn. Isolation bảo vệ **thực thi đồng thời của những quyết định được code/constraint mô tả**, không sửa logic nghiệp vụ vốn thiếu.

## 4. Serialization graph: mô hình phụ thuộc giữa transaction

Để hiểu SSI, dùng một đồ thị:

- **Đỉnh**: các transaction.
- **Cạnh có hướng**: một transaction phải đứng trước transaction khác trong thứ tự tuần tự tương ứng do chúng đã truy cập cùng dữ liệu theo một quan hệ có ý nghĩa.

Ví dụ:

~~~text
T1 ------> T2 ------> T3

Cần có một thứ tự phù hợp:
T1 trước T2, T2 trước T3.
~~~

Nếu đồ thị buộc đồng thời:

~~~text
T1 ------> T2
^           |
|           v
+-----------+
~~~

tức có **chu trình**, không thể xếp các đỉnh theo một thứ tự tuần tự thỏa mọi cạnh.

### 4.1. Ba loại quan hệ cần biết

Trong các phân tích về MVCC/serialization graph, thường phân biệt:

| Quan hệ | Đọc như thế nào? | Ý nghĩa khái niệm |
|---|---|---|
| `wr` | Write → Read | T2 đọc dữ liệu do T1 ghi |
| `ww` | Write → Write | T2 ghi vào phiên bản/thực thể sau T1 |
| `rw` | Read → Write | T1 đọc trạng thái mà không nhìn thấy thay đổi do T2 ghi; còn gọi anti-dependency |

Phần quan trọng nhất của SSI là **`rw-antidependency</BT>**.

### 4.2. Cạnh không phải thứ tự chạy câu lệnh đơn thuần

Không tạo cạnh graph chỉ vì “T1 có câu SELECT xảy ra trước T2 có câu SELECT”. Phụ thuộc phản ánh những ràng buộc **đọc/ghi trên dữ liệu hoặc predicate có liên quan**.

Để suy luận đúng, phải xem phiên bản hàng nào được đọc, dữ liệu nào được ghi và những snapshot nào đã nhìn thấy các thay đổi đó.

## 5. Write–read dependency: T2 đọc kết quả của T1

Ví dụ khái niệm:

~~~text
T1: W(X=200), COMMIT
T2: R(X) -> 200
~~~

T2 đọc phiên bản X do T1 tạo ra. Có quan hệ:

~~~text
T1 --wr--> T2
~~~

Trong thứ tự tuần tự tương ứng, T1 phải đứng trước T2 để T2 đọc đúng giá trị do T1 tạo.

### 5.1. Không nhầm wr với dirty read

Đây là T2 đọc **phiên bản đã commit và khả kiến**, không phải phiên bản chưa commit. PostgreSQL vốn không cho dirty read thông thường giữa các transaction.

### 5.2. wr một mình không phải lỗi

T2 đọc giá trị đã commit của T1 là hành vi bình thường. Nó tạo ràng buộc về thứ tự, nhưng chưa đủ để khẳng định có serialization anomaly.

## 6. Write–write dependency: nhiều transaction sửa cùng dữ liệu

Giả sử:

~~~text
T1: W(X=150), COMMIT
T2: W(X=170), COMMIT
~~~

Có thể biểu diễn ràng buộc:

~~~text
T1 --ww--> T2
~~~

T2 ghi sau phiên bản mà T1 tạo.

### 6.1. PostgreSQL điều phối cập nhật cùng hàng

Những transaction UPDATE cùng hàng thường phải qua row locking/concurrency checks. Ở REPEATABLE READ hoặc SERIALIZABLE, cập nhật một hàng đã thay đổi sau snapshot có thể gây lỗi kiểu:

~~~text
could not serialize access due to concurrent update
SQLSTATE 40001
~~~

### 6.2. ww không giải quyết write skew

Trong ví dụ bác sĩ:

~~~text
T1 ghi doctor_id=1
T2 ghi doctor_id=2
~~~

Hai transaction không ghi **cùng hàng**. Cơ chế xung đột ww/row-lock thông thường không đủ để phát hiện bất biến “còn ít nhất một người trực” bị phá. Cần quan tâm các **rw-antidependencies**.

## 7. Read–write antidependency: trung tâm của SSI

Một **rw-antidependency** xảy ra khi T1 đã đọc một phiên bản/trạng thái theo snapshot của mình, trong khi T2 tạo thay đổi mà T1 **không nhìn thấy**. Để giữ kết quả đọc của T1 như vậy trong một lịch tuần tự, T1 phải được sắp **trước** T2 đối với quan hệ đó.

Ký hiệu:

~~~text
T1 --rw--> T2
~~~

Ví dụ:

~~~text
X ban đầu = 100

T1                           T2
---------------------------- ----------------------------
BEGIN; lấy snapshot S1
R(X) -> 100
                             W(X=200)
                             COMMIT
T1 không thấy 200 theo S1
~~~

Cạnh `T1 --rw--> T2` phản ánh rằng snapshot của T1 không chứa phiên bản mới do T2 tạo.

### 7.1. Vì sao gọi là anti-dependency?

Nó ngược hướng với `wr` thông thường:

- `wr`: T2 **đọc thấy** thứ T1 đã ghi.
- `rw`: T1 **không đọc thấy** thứ T2 ghi vì phiên bản đó nằm ngoài snapshot của T1.

### 7.2. Tác động tới câu WHERE

T1 không cần đọc một hàng cụ thể mới có rw-antidependency. Nếu T1 hỏi:

~~~sql
SELECT COUNT(*)
FROM reservations
WHERE room_id = 10
  AND status = 'confirmed';
~~~

rồi T2 INSERT một hàng khớp predicate mà T1 không thấy, hai giao dịch có thể hình thành phụ thuộc rw liên quan **tập hàng truy vấn**.

Đây là lý do PostgreSQL cần theo dõi cả **predicate reads**, không chỉ khóa hàng đã tồn tại.

### 7.3. Một cạnh rw chưa phải lúc nào cũng là lỗi

Nhiều transaction Serializable bình thường có các quan hệ rw mà vẫn hoàn toàn có thể xếp tuần tự.

Ví dụ T1 đọc một cấu hình, T2 cập nhật cấu hình sau đó; nếu không có một chu trình phụ thuộc khác, lịch vẫn có thể tương đương “T1 trước T2”.

SSI quan tâm **tổ hợp các phụ thuộc** tạo rủi ro, không abort mọi lần một dữ liệu đã đọc bị cập nhật.

## 8. Dangerous structure: hai cạnh rw nối tiếp

Trong phân tích Serializable Snapshot Isolation, một cấu trúc đặc biệt quan trọng là:

~~~text
T_in  --rw-->  T_pivot  --rw-->  T_out
                  ^
                  |
               pivot
~~~

Ba transaction đóng ba vai trò:

- **`T_in`**: một transaction có anti-dependency đi **vào** pivot.
- **`T_pivot`**: transaction ở giữa, vừa nhận một cạnh rw vừa có một cạnh rw đi ra.
- **`T_out`**: transaction ở cuối cấu trúc.

Đây gọi là **dangerous structure** — dấu hiệu cần thiết cho những chu trình serialization đặc biệt dẫn tới bất thường dưới snapshot isolation.

### 8.1. Vì sao hai cạnh rw quan trọng?

Một chu trình serialization graph có thể có nhiều cạnh `wr</BT>, `ww</BT> và `rw</BT>. Lý thuyết SSI cho thấy những chu trình không tuần tự hóa được dưới snapshot isolation có một mẫu liên quan **hai cạnh rw liên tiếp**; đó là cơ sở PostgreSQL phát hiện nguy cơ mà không phải xây và kiểm tra toàn bộ đồ thị lịch sử theo cách đơn giản nhất.

### 8.2. Điều kiện commit-order được tối ưu hóa

Không phải mọi hai cạnh rw nối tiếp đều chắc chắn tạo chu trình. Việc **thứ tự commit** giữa các transaction liên quan cũng giúp phân biệt lịch nguy hiểm. Đặc biệt, các cấu trúc thật sự dẫn tới anomaly phải thỏa những ràng buộc về transaction cuối, thường được diễn đạt qua việc **`T_out` commit sớm** trong chuỗi nguy hiểm.

Đây là cơ sở cho những tối ưu trong PostgreSQL SSI nhằm tránh abort không cần thiết. Không nên rút gọn thuật toán thành quy tắc “cứ nhìn thấy hai cạnh rw là phải rollback ngay”, vì implementation còn xét overlap, commit state và các trường hợp chỉ đọc.

### 8.3. Dangerous structure là dấu hiệu bảo thủ

Một dangerous structure **có thể** xuất hiện mà toàn bộ lịch thực tế vẫn serializable do không có đường khép kín thành chu trình. Khi PostgreSQL abort để tránh rủi ro đó, đó có thể là **false positive về anomaly**, không có nghĩa dữ liệu đã sai hay PostgreSQL có bug.

Bảo đảm an toàn được ưu tiên hơn việc luôn cho mọi lịch hợp lệ commit.

## 9. Write skew dưới góc nhìn phụ thuộc rw

Quay lại lịch bác sĩ.

~~~text
Ban đầu: An=true, Bình=true

T1 đọc cả hai người trực.
T2 đọc cả hai người trực.

T1 ghi An=false.
T2 ghi Bình=false.
~~~

Các phụ thuộc:

~~~text
T1 đọc Bình=true, nhưng không thấy T2 ghi Bình=false
    => T1 --rw--> T2

T2 đọc An=true, nhưng không thấy T1 ghi An=false
    => T2 --rw--> T1

Đồ thị:
       rw
   T1 -----> T2
    ^         |
    |         |
    +---------+
        rw
~~~

Chu trình này chứng minh không tồn tại một lịch tuần tự phù hợp với **cả hai kết quả đọc và cả hai phép ghi**.

### 9.1. Hai transaction cũng đủ để tạo chu trình

Dangerous structure thường được mô tả với ba vị trí `T_in</BT>, `T_pivot</BT>, `T_out</BT>, nhưng trong chu trình hai transaction, hai vai trò đầu/cuối có thể do cùng một transaction thực hiện trong cách nhìn về mẫu phụ thuộc.

Không phải mọi anomaly đòi hỏi ba transaction phân biệt.

### 9.2. Vì sao REPEATABLE READ không ngăn?

Mỗi transaction nhìn snapshot chứa cả hai bác sĩ đang trực. Không ai sửa cùng một hàng, nên cơ chế conflict update trực tiếp không buộc một transaction thất bại như trường hợp cùng sửa một row.

REPEATABLE READ bảo vệ **snapshot nhất quán**, không tự loại trừ chu trình phụ thuộc giữa nhiều snapshot.

### 9.3. Vì sao SERIALIZABLE ngăn?

SSI theo dõi các đọc và ghi có liên quan. Nếu hai giao dịch đều cố commit trạng thái write skew, PostgreSQL nhận ra cấu trúc phụ thuộc không an toàn và một transaction không thể commit thành công trong lịch đó.

Thông thường ứng dụng sẽ thấy `SQLSTATE 40001` và cần thực hiện lại toàn giao dịch bị abort.

## 10. Phát hiện phụ thuộc với predicate: hàng chưa tồn tại cũng quan trọng

Một race phổ biến:

1. T1 hỏi “Phòng 101 có booking trùng thời gian không?” → không có.
2. T2 cũng hỏi → không có.
3. T1 INSERT booking A.
4. T2 INSERT booking B trùng giờ với A.
5. Cả hai commit → trùng booking.

Nếu chỉ khóa **những booking hiện có**, một predicate rỗng không có hàng để khóa. Vấn đề nằm ở việc **đọc sự vắng mặt** rồi một transaction khác tạo hàng phù hợp điều kiện đó.

### 10.1. Predicate read là một phần của logic

~~~sql
SELECT NOT EXISTS (
    SELECT 1
    FROM bookings
    WHERE room_id = 101
      AND status = 'confirmed'
      AND starts_at < TIMESTAMPTZ '2026-11-14 12:00+07'
      AND ends_at > TIMESTAMPTZ '2026-11-14 11:00+07'
) AS free_slot;
~~~

Trong một transaction, SELECT trên có thể trả true. Điều đó chưa có nghĩa mãi mãi không ai có thể INSERT booking trùng giờ.

### 10.2. SSI ghi nhận đọc predicate

Khi SERIALIZABLE, PostgreSQL sử dụng thông tin đọc trên phạm vi dữ liệu thích hợp để phát hiện transaction khác ghi vào phạm vi mà giao dịch đầu đã quan sát.

Nếu cả hai thực hiện cùng kiểm tra rồi INSERT theo snapshot riêng, các phụ thuộc rw có thể dẫn đến serialization failure. Nếu thiết kế phù hợp, **exclusion constraint** trên khoảng thời gian cũng là cách mạnh để bảo vệ không trùng booking, đặc biệt khi có nhiều writer.

### 10.3. Row lock không phải predicate lock

~~~sql
SELECT *
FROM bookings
WHERE room_id = 101
FOR UPDATE;
~~~

Lệnh này khóa **các hàng được chọn** theo semantics row locking, không tự khóa mọi hàng có thể được INSERT trong tương lai. Khi query không có hàng, không có nghĩa đã khóa một “khoảng trống” trừ khi có cơ chế/protocol riêng phù hợp.

## 11. SIReadLock: cách PostgreSQL theo dõi những thứ đã đọc

Trong Serializable Snapshot Isolation, PostgreSQL dùng các khóa theo dõi đọc thường được hiển thị với mode **`SIReadLock`**.

Tên gọi “lock” dễ gây hiểu lầm vì mục đích của nó khác row lock cho phép đọc–sửa theo kiểu pessimistic.

### 11.1. SIReadLock không chặn ghi như FOR UPDATE

- `SELECT ... FOR UPDATE` có thể khiến transaction khác phải chờ khi muốn sửa hàng được khóa.
- `SIReadLock` phục vụ **theo dõi xung đột đọc–ghi để quyết định serialization**; nó không đơn giản chặn tất cả UPDATE/INSERT trên dữ liệu đã đọc.

Vì thế hai SERIALIZABLE transaction thường có thể tiếp tục chạy, rồi một transaction bị abort nếu các phụ thuộc hình thành lịch không an toàn.

### 11.2. Predicate tracking có các mức chi tiết

Tùy query plan, vùng đã đọc và tài nguyên sẵn có, PostgreSQL có thể theo dõi ở cấp:

- Tuple/hàng.
- Page/trang dữ liệu.
- Relation/bảng.

Việc theo dõi rộng hơn có thể khiến nhiều thao tác ghi bị coi là có liên quan tới vùng đọc, làm tăng nguy cơ serialization failure không cần thiết về mặt nghiệp vụ.

### 11.3. Seq scan có thể ảnh hưởng phạm vi theo dõi

Một sequential scan đọc toàn bảng có thể dẫn tới thông tin SIREAD rộng hơn so với một index scan giới hạn tập dữ liệu. Index thích hợp đôi khi giúp tránh những xung đột bảo thủ, dù hiệu ứng cụ thể phụ thuộc planner, dữ liệu và query.

**Đừng tạo index chỉ vì thấy SIReadLock.** Cần đối chiếu predicate, EXPLAIN, tần suất 40001 và chi phí ghi/index.

### 11.4. Khóa SIREAD có thể còn cần thiết sau COMMIT

Thông tin theo dõi đọc có thể được giữ đủ lâu để phát hiện phụ thuộc với những transaction Serializable đang chồng lấn, thay vì được nhả hoàn toàn như một row lock ngay khi transaction đọc commit.

Không suy ra “một transaction đã COMMIT nên mọi dấu vết theo dõi xung đột của nó phải biến mất tức thì”.

## 12. SSI khác khóa hai pha nghiêm ngặt như thế nào?

Một cơ chế khác để bảo đảm serializability là dùng locking theo cách các phép đọc/ghi phải chờ nhau để ngăn lịch bất hợp lệ.

SSI có cách tiếp cận khác:

| Khía cạnh | Locking theo hướng chặn truy cập | SSI PostgreSQL |
|---|---|---|
| Đọc dữ liệu | Có thể cần khóa gây chờ ghi | Dựa vào MVCC snapshot |
| Ghi dữ liệu | Chờ khóa/xung đột như thông thường | Vẫn dùng row locking cho ghi |
| Quan hệ đọc–ghi nguy hiểm | Có thể bị chặn từ đầu | Được theo dõi, có thể gây abort |
| Dữ liệu mới khớp predicate | Cần cơ chế bảo vệ predicate/range | Theo dõi predicate reads |
| Cách phản hồi khi không an toàn | Chờ hoặc deadlock/abort tùy thiết kế | Serialization failure `40001` |
| Ứng dụng cần retry | Có thể, tùy loại lỗi | **Cần thiết** để xử lý 40001 |

### 12.1. “Không chặn đọc–ghi” không phải “không bao giờ chờ”

PostgreSQL vẫn dùng locks cho thao tác ghi, DDL, foreign keys và nhiều việc khác. Hai SERIALIZABLE transaction có thể chờ khóa khi cùng UPDATE một hàng. SSI chỉ nói rằng các **predicate reads** phục vụ serializability không đơn giản là khóa chặn mọi writer theo cách pessimistic.

### 12.2. SSI không loại trừ deadlock

Một lịch lấy row locks theo thứ tự đảo ngược vẫn có thể deadlock và PostgreSQL báo `40P01`. Điều đó khác với serialization failure `40001`.

## 13. Lab hai phiên: chuẩn bị dữ liệu

Thực hành trên **PostgreSQL thử nghiệm**, có quyền tạo schema. Không chạy trên production. Mở **hai kết nối độc lập**, ví dụ hai terminal `psql` kết nối cùng database.

Nếu schema `ssi_lab` đã tồn tại, dùng database khác hoặc đổi tên schema; **không tự DROP schema có sẵn**.

### 13.1. Tạo schema

~~~sql
CREATE SCHEMA ssi_lab;
~~~

### 13.2. Bảng bác sĩ

~~~sql
CREATE TABLE ssi_lab.doctors (
    doctor_id INTEGER PRIMARY KEY,
    doctor_name TEXT NOT NULL,
    on_call BOOLEAN NOT NULL
);

INSERT INTO ssi_lab.doctors (
    doctor_id, doctor_name, on_call
)
VALUES
    (1, 'An', TRUE),
    (2, 'Bình', TRUE);
~~~

Đặt invariant nghiệp vụ: `COUNT(*) FILTER (WHERE on_call) >= 1`. Bảng cố ý chưa có một cơ chế constraint nhiều hàng bảo vệ invariant để thấy write skew.

### 13.3. Bảng cấu hình ngân sách

~~~sql
CREATE TABLE ssi_lab.budget (
    budget_id INTEGER PRIMARY KEY,
    department TEXT NOT NULL,
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount >= 0)
);

INSERT INTO ssi_lab.budget (budget_id, department, amount)
VALUES
    (1, 'Engineering', 1000),
    (2, 'Operations', 1000);
~~~

Bảng này sẽ dùng để minh họa snapshot đọc nhất quán và lý do nhiều câu SELECT dưới READ COMMITTED có thể thấy hai trạng thái khác nhau.

### 13.4. Quy tắc chạy lab

- Session A = T1, Session B = T2.
- Chạy theo **thứ tự từng bước** được mô tả, không dán toàn bộ cả hai bên vào một kết nối.
- Bảo đảm cả hai SELECT khởi tạo snapshot hoàn thành **trước các UPDATE/COMMIT** trong thử nghiệm write skew.
- Nếu thấy `ERROR</BT> trong transaction, rollback khi cần trước khi tiếp tục.
- Chỉ reset dữ liệu sau khi hai phiên đã kết thúc transaction.
- Nếu dùng GUI, kiểm tra hai tab thật sự có hai backend sessions độc lập.

## 14. Thí nghiệm A: write skew ở REPEATABLE READ

Đầu tiên, ở một phiên ngoài transaction thí nghiệm:

~~~sql
UPDATE ssi_lab.doctors
SET on_call = TRUE;
~~~

### 14.1. Session A

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS doctors_on_call
FROM ssi_lab.doctors
WHERE on_call;
-- Kỳ vọng: 2.

-- Giữ transaction A mở.
~~~

### 14.2. Session B

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS doctors_on_call
FROM ssi_lab.doctors
WHERE on_call;
-- Kỳ vọng: 2.

-- Giữ transaction B mở.
~~~

Đến đây mỗi phiên có một snapshot đều thấy hai người trực.

### 14.3. Session A cập nhật và commit

~~~sql
UPDATE ssi_lab.doctors
SET on_call = FALSE
WHERE doctor_id = 1;

COMMIT;
~~~

### 14.4. Session B cập nhật và commit

~~~sql
UPDATE ssi_lab.doctors
SET on_call = FALSE
WHERE doctor_id = 2;

COMMIT;
~~~

Hai giao dịch sửa **hai hàng khác nhau**. Dưới REPEATABLE READ, cả hai có thể thành công.

### 14.5. Xem kết quả

~~~sql
SELECT
    doctor_id,
    doctor_name,
    on_call
FROM ssi_lab.doctors
ORDER BY doctor_id;

SELECT COUNT(*) AS remaining_on_call
FROM ssi_lab.doctors
WHERE on_call;
~~~

Nếu cả hai commit, `remaining_on_call = 0`, vi phạm invariant.

**Đây là một lịch không serializable dù không có dirty read, nonrepeatable read hay phantom read trong hai transaction.**

## 15. Thí nghiệm B: cùng lịch với SERIALIZABLE

Reset ngoài transaction:

~~~sql
UPDATE ssi_lab.doctors
SET on_call = TRUE;
~~~

### 15.1. Session A

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS doctors_on_call
FROM ssi_lab.doctors
WHERE on_call;
-- Kỳ vọng: 2.
~~~

### 15.2. Session B

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS doctors_on_call
FROM ssi_lab.doctors
WHERE on_call;
-- Kỳ vọng: 2.
~~~

### 15.3. Session A

~~~sql
UPDATE ssi_lab.doctors
SET on_call = FALSE
WHERE doctor_id = 1;

COMMIT;
~~~

### 15.4. Session B

~~~sql
UPDATE ssi_lab.doctors
SET on_call = FALSE
WHERE doctor_id = 2;

COMMIT;
~~~

Với interleaving trên, PostgreSQL không thể cho cả hai transaction **đều commit thành công** mà không phá tính serializable. Một phiên có thể nhận lỗi kiểu:

~~~text
ERROR: could not serialize access due to read/write dependencies
       among transactions
SQLSTATE 40001
~~~

Thông điệp cụ thể và thời điểm lỗi (`UPDATE</BT> hay `COMMIT</BT>) có thể khác; không hard-code vào chuỗi thông báo tiếng Anh.

### 15.5. Cách kiểm tra SQLSTATE trong psql

Trong `psql`, sau một câu lệnh lỗi, có thể bật chi tiết:

~~~text
\set VERBOSITY verbose
~~~

Lặp lại tình huống trên lab để xem SQLSTATE kèm thông báo, hoặc để ứng dụng/JDBC lấy mã lỗi từ driver.

### 15.6. Sau lỗi cần rollback

Nếu transaction đang ở trạng thái failed, chạy:

~~~sql
ROLLBACK;
~~~

Sau đó mở transaction mới. Không cố tiếp tục những câu SELECT/UPDATE trong một transaction đã bị abort.

### 15.7. Kết quả cuối phải còn người trực

Nếu A commit và B bị abort, An nghỉ còn Bình trực. Nếu B commit và A bị abort, Bình nghỉ còn An trực. Với protocol đọc và kiểm tra invariant đầy đủ, không nên có kết quả cả hai ngừng trực sau khi hai giao dịch Serializable **đều được chấp nhận**.

## 16. Tại sao transaction bị abort? Vẽ graph của lab

Ở thời điểm hai SELECT:

~~~text
T1 snapshot: An=true, Bình=true
T2 snapshot: An=true, Bình=true
~~~

Sau đó:

~~~text
T1 ghi An=false
T2 ghi Bình=false
~~~

Các phụ thuộc:

~~~text
T1 đọc Bình=true và không thấy thay đổi Bình=false của T2
  => T1 --rw--> T2

T2 đọc An=true và không thấy thay đổi An=false của T1
  => T2 --rw--> T1

      +-----------+
      |           v
      T1 --rw--> T2
      ^           |
      +----rw-----+
~~~

Không có thứ tự tuần tự nào giải thích được hai phép đọc đều thấy hai bác sĩ trực **và** cả hai phép cập nhật đều được commit theo đúng logic kiểm tra.

SSI theo dõi phụ thuộc để ngăn chu trình có nguy cơ này.

### 16.1. Vì sao chỉ đếm hàng cũng đủ tạo phụ thuộc?

`SELECT COUNT(*) WHERE on_call</BT> là một truy vấn **theo predicate**. Giá trị đếm phụ thuộc vào những hàng thỏa `on_call = TRUE`. Việc transaction khác đổi TRUE→FALSE làm thay đổi tập kết quả cần được bảo vệ về tính serializability.

### 16.2. Nếu một phiên chỉ SELECT còn phiên kia UPDATE?

Một cạnh rw đơn lẻ không tự tạo anomaly. Serializable không có nghĩa cứ ai cập nhật hàng đã được người khác đọc là một người nhất định phải thất bại. Cấu trúc của toàn lịch mới quyết định rủi ro.

### 16.3. Khi READ COMMITTED có làm khác?

Ở READ COMMITTED, nếu transaction B **đọc lại điều kiện sau khi A commit** thì có thể thấy chỉ còn một bác sĩ và ngừng lại. Nhưng nếu cả hai đã kiểm tra điều kiện từ trước, transaction B có thể vẫn dựa trên quyết định cũ. READ COMMITTED không tự bảo vệ invariant nhiều hàng đó.

## 17. Transaction read-only cũng có thể liên quan serialization

Một transaction chỉ SELECT không ghi hàng nào nhưng vẫn có thể là **một đỉnh trong đồ thị phụ thuộc** của các transaction khác. Vì vậy “tôi chỉ đọc” không tự chứng minh mọi lịch cùng nó serializable.

### 17.1. Báo cáo nhiều câu SELECT ở READ COMMITTED

Giả sử tổng ngân sách hai phòng ban đang là 2000. Transaction T2 chuyển 100 từ Engineering sang Operations bằng hai UPDATE trong cùng transaction.

T1 đọc Engineering trước khi T2 commit, sau đó đọc Operations sau khi T2 commit:

~~~text
Ban đầu Engineering=1000, Operations=1000

T1 đọc Engineering -> 1000

T2 chuyển:
  Engineering -> 900
  Operations  -> 1100
  COMMIT

T1 đọc Operations -> 1100
T1 cộng -> 2100, một tổng không tồn tại ở trạng thái commit.
~~~

Đó là **read skew** giữa hai câu SELECT ở READ COMMITTED.

### 17.2. REPEATABLE READ READ ONLY

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT amount
FROM ssi_lab.budget
WHERE budget_id = 1;

SELECT amount
FROM ssi_lab.budget
WHERE budget_id = 2;

COMMIT;
~~~

Hai SELECT dùng snapshot ổn định, tránh trộn hai lát cắt dữ liệu.

### 17.3. Serializable read-only và các phụ thuộc gián tiếp

Nếu cần kết quả read-only tương đương với một thứ tự tuần tự toàn hệ thống, chỉ “snapshot nhất quán” là chưa phải mô tả hết yêu cầu khi có nhiều giao dịch Serializable đồng thời và phụ thuộc phức tạp. SSI có cơ chế dành cho transaction chỉ đọc và có thể yêu cầu một giao dịch bị abort để bảo đảm serialization.

## 18. SERIALIZABLE READ ONLY DEFERRABLE: chờ snapshot an toàn

PostgreSQL có một chế độ đặc biệt thích hợp cho **báo cáo chỉ đọc** yêu cầu serializable snapshot:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE
    READ ONLY
    DEFERRABLE;

SELECT
    SUM(amount) AS total_budget
FROM ssi_lab.budget;

COMMIT;
~~~

### 18.1. DEFERRABLE làm gì?

Với transaction SERIALIZABLE, READ ONLY và DEFERRABLE, PostgreSQL có thể **chờ đến khi lấy được một snapshot an toàn** trước khi chạy phần đọc. Khi đã có snapshot an toàn, transaction chỉ đọc đó tránh được những serialization failures thông thường gắn với tương tác đọc Serializable của nó.

### 18.2. Không phải bật DEFERRABLE sẽ làm mọi transaction nhanh hơn

Nó có thể phải **chờ trước khi bắt đầu đọc**, nhất là khi có nhiều transaction ghi đồng thời. Đây là đánh đổi giữa thời gian chờ lấy snapshot và việc tránh retry đối với một báo cáo read-only dài.

### 18.3. Điều kiện áp dụng

Chế độ DEFERRABLE có tác dụng đáng kể trong kết hợp **SERIALIZABLE + READ ONLY**. Nó không phải một biến thể có tác dụng tương tự trên mọi transaction READ COMMITTED hoặc giao dịch có ghi.

### 18.4. Khi nào nên dùng?

- Báo cáo đọc nhiều bảng bằng nhiều câu SELECT.
- Một tác vụ xuất dữ liệu chỉ đọc.
- Công việc chấp nhận chờ đầu phiên thay vì phải retry do serialization.
- Cần snapshot có bảo đảm phù hợp với các giao dịch Serializable của hệ thống.

Nếu chỉ chạy một SELECT nhỏ, lựa chọn đơn giản hơn có thể đủ tùy tính đúng nghiệp vụ.

## 19. Serialization failure: lỗi được thiết kế, không phải dữ liệu hỏng

Khi PostgreSQL hủy một transaction Serializable để ngăn lịch nguy hiểm, nó thường trả:

~~~text
SQLSTATE 40001
serialization_failure
~~~

Đây là một lỗi **phải được xử lý trong thiết kế ứng dụng**, không nên xem là sự cố ngẫu nhiên cần che đi.

### 19.1. 40001 có thể xuất hiện ở đâu?

- Khi UPDATE/DELETE gặp phiên bản hàng bị cập nhật sau snapshot.
- Khi PostgreSQL phát hiện phụ thuộc đọc–ghi nguy hiểm trong khi thực hiện DML.
- Khi COMMIT, sau khi các câu SQL trước đó đã chạy xong.

Không chỉ bắt 40001 quanh câu UPDATE; phải bao quanh **toàn bộ transaction bao gồm COMMIT**.

### 19.2. Không nhầm 40001 với deadlock

| SQLSTATE | Tên lỗi phổ biến | Nguyên nhân chính |
|---|---|---|
| `40001` | serialization_failure | Không thể cho transaction tiếp tục/commit đúng bảo đảm isolation |
| `40P01` | deadlock_detected | Các transaction tạo chu trình chờ locks |
| `23505` | unique_violation | Trùng khóa/unique index |
| `23P01` | exclusion_violation | Vi phạm exclusion constraint |
| `55P03` | lock_not_available | Không lấy được lock theo điều kiện của thao tác |

Một số lỗi unique/exclusion có thể là kết quả của race condition mà ứng dụng cần đánh giá như một conflict/retry, nhưng không nên **tự động retry mọi 23505/23P01**; có thể đó là yêu cầu nghiệp vụ không hợp lệ thực sự.

### 19.3. Tỷ lệ abort cao không đồng nghĩa dữ liệu bị sai

SSI abort nhằm **ngăn kết quả sai được commit**. Nếu tần suất 40001 tăng, cần xem workload, transaction duration, query predicates, indexes và retry policy thay vì tắt serializability một cách máy móc.

## 20. Retry đúng: phải chạy lại toàn transaction

Đây là nguyên tắc quan trọng nhất khi lập trình với SSI:

**Gặp 40001 → rollback transaction cũ → bắt đầu transaction mới → đọc lại dữ liệu → quyết định lại → ghi lại → commit.**

### 20.1. Tại sao chỉ retry câu cuối là sai?

Trong lab write skew:

1. T1 và T2 đều đọc count=2.
2. T1 commit cho An nghỉ.
3. T2 bị abort.
4. Nếu T2 chỉ chạy lại `UPDATE doctor_id=2 SET on_call=false` mà không đọc lại, nó bỏ qua bước kiểm tra “còn ai trực”.

Phải đọc count mới, thấy count=1 và **không cho người cuối cùng nghỉ**.

### 20.2. Pseudocode giao dịch đúng

~~~text
max_attempts = 5

for attempt = 1..max_attempts:
    BEGIN SERIALIZABLE

    try:
        current_state = SELECT ...           # Đọc lại
        if not business_precondition(state):
            ROLLBACK
            return DOMAIN_REJECTED

        UPDATE ...                           # Ghi theo quyết định mới
        COMMIT                               # Có thể lỗi 40001 ở đây
        return SUCCESS

    catch sqlstate == 40001:
        ROLLBACK if transaction still open
        backoff_with_jitter(attempt)
        continue with NEW transaction

    catch other_error:
        ROLLBACK if needed
        raise

return RETRY_EXHAUSTED
~~~

### 20.3. Retry có giới hạn

Nên xác định:

- Số lần thử tối đa.
- Backoff và jitter.
- Deadline tổng của request.
- Metrics cho số lần retry.
- Ngưỡng cảnh báo cho 40001.
- Hành vi trả lỗi cho người dùng khi retry cạn.

Retry vô hạn dưới contention cao làm tăng tải và kéo dài latency.

### 20.4. Side effects ngoài database

Một transaction có thể rollback trong PostgreSQL, nhưng **email, HTTP payment call hoặc thông báo đã gửi ra ngoài** không tự rollback.

Nếu retry toàn transaction, thao tác ngoài DB cần idempotency và thiết kế như:

- Transactional outbox.
- Idempotency key.
- Tách side effect sau khi commit nếu hợp đồng cho phép.
- Reconciliation khi trạng thái DB và bên ngoài lệch.
- Consumer xử lý event ít nhất một lần một cách an toàn.

Không đặt việc gọi payment provider mất nhiều giây ngay trong transaction giữ locks nếu có thể thiết kế workflow khác.

## 21. Ví dụ Java/JDBC: bao toàn transaction và SQLSTATE

Một mẫu Java đơn giản minh họa cấu trúc; giả định `DataSource</BT> đã được cấu hình, business precondition và logging được định nghĩa trong ứng dụng.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class DoctorDutyService {
    private final DataSource dataSource;

    public DoctorDutyService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean requestLeave(int doctorId) throws SQLException {
        final int maxAttempts = 5;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try (Connection cn = dataSource.getConnection()) {
                cn.setAutoCommit(false);
                cn.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE);

                try {
                    int count;
                    try (PreparedStatement ps = cn.prepareStatement(
                            "SELECT COUNT(*) FROM ssi_lab.doctors WHERE on_call")) {
                        try (ResultSet rs = ps.executeQuery()) {
                            rs.next();
                            count = rs.getInt(1);
                        }
                    }

                    if (count <= 1) {
                        cn.rollback();
                        return false;
                    }

                    int updated;
                    try (PreparedStatement ps = cn.prepareStatement(
                            "UPDATE ssi_lab.doctors " +
                            "SET on_call = FALSE " +
                            "WHERE doctor_id = ? AND on_call = TRUE")) {
                        ps.setInt(1, doctorId);
                        updated = ps.executeUpdate();
                    }

                    if (updated != 1) {
                        cn.rollback();
                        return false;
                    }

                    cn.commit();
                    return true;

                } catch (SQLException ex) {
                    try {
                        cn.rollback();
                    } catch (SQLException rollbackError) {
                        ex.addSuppressed(rollbackError);
                    }

                    if ("40001".equals(ex.getSQLState())
                            && attempt < maxAttempts) {
                        // Thực tế: backoff/jitter + deadline + logging.
                        continue;
                    }
                    throw ex;
                }
            }
        }

        throw new SQLException("Retry limit exceeded", "40001");
    }
}
~~~

### 21.1. Điểm cần chú ý trong ứng dụng thật

- `Connection.TRANSACTION_SERIALIZABLE` phải được driver/datasource ánh xạ đúng cho PostgreSQL.
- Đặt isolation trước các câu truy vấn của transaction.
- `commit()</BT> nằm trong vùng có xử lý SQLException.
- Mỗi lần retry tạo một transaction mới và đọc lại trạng thái.
- Không trả thành công trước khi commit.
- Với connection pool, trả lại trạng thái autoCommit/isolation đúng theo hợp đồng pool; dùng abstraction transaction của framework có thể an toàn hơn việc tự quản lý thủ công.
- Không gọi external side effect trước commit mà không có idempotency.
- Quyết định “doctorId có tồn tại và được phép nghỉ” cần thêm authorization/domain validation ngoài ví dụ.
- Backoff/jitter và deadline cần được triển khai, không chỉ comment.

### 21.2. Tại sao không retry statement trong cùng transaction?

Khi PostgreSQL báo lỗi trong transaction, nó thường chuyển transaction sang trạng thái failed/aborted cho tới khi rollback. Quan trọng hơn, snapshot và quyết định nghiệp vụ cũ đã không còn an toàn. Cần **transaction mới**, không chỉ câu SQL mới.

## 22. Serializable không thay thế constraints

SSI là một tầng bảo vệ concurrency, nhưng nhiều bất biến nên được thể hiện trực tiếp bằng constraint khi có thể.

### 22.1. UNIQUE cho khóa nghiệp vụ

~~~sql
CREATE TABLE ssi_lab.request_ids (
    request_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Nếu hai writer cùng INSERT một `request_id`, PRIMARY KEY/UNIQUE giúp bảo vệ trùng. Đừng chỉ SELECT “chưa có” rồi INSERT và kỳ vọng pre-check tự đủ.

### 22.2. CHECK cho bất biến cùng hàng

~~~sql
CREATE TABLE ssi_lab.stock (
    sku TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);
~~~

`CHECK</BT> bảo vệ số lượng không âm. Transaction cũng cần kiểm tra đã cấp kho cho đúng đơn hàng và không xử lý trùng request.

### 22.3. Exclusion constraint cho khoảng thời gian

Nếu một phòng không được có hai booking trùng thời gian, exclusion constraint phù hợp trên một range type có thể bảo vệ dữ liệu mạnh hơn logic “SELECT kiểm tra rồi INSERT”. Cần thiết kế toán tử range, index, extension và phạm vi tenant/phòng cụ thể đúng với schema.

### 22.4. Bất biến nhiều hàng khó biểu diễn bằng CHECK

“Ít nhất một bác sĩ trực” là điều kiện **aggregate trên nhiều hàng**, không thể trực tiếp bảo vệ đầy đủ chỉ bằng `CHECK (on_call IS NOT NULL)` hoặc `CHECK (on_call IN (true,false))`.

Đó là một tình huống nơi transaction Serializable hoặc một protocol điều phối phù hợp có giá trị.

### 22.5. Tất cả đường ghi phải giữ nguyên tắc

Một API Serializable kiểm tra rồi cập nhật đúng có thể bị phá invariant bởi một script quản trị chỉ chạy UPDATE không kiểm tra điều kiện. SERIALIZABLE không làm PostgreSQL đoán ra quy tắc mà writer khác chưa biểu diễn.

Hãy kiểm soát cả API, background jobs, batch imports và thao tác sửa dữ liệu thủ công; xem xét quyền tối thiểu và constraint ở DB.

## 23. Alternatives: bảo vệ một hàng không nhất thiết cần SSI

Với một số nghiệp vụ, có cách đơn giản hơn.

### 23.1. UPDATE nguyên tử

Giảm tồn kho một đơn vị nếu còn đủ:

~~~sql
UPDATE ssi_lab.stock
SET quantity = quantity - 1
WHERE sku = 'BOOK-001'
  AND quantity >= 1
RETURNING sku, quantity;
~~~

Đây là một statement cập nhật có điều kiện, phối hợp với row locking của PostgreSQL. Nếu không trả hàng, không được coi cấp phát thành công.

### 23.2. Optimistic locking qua version

~~~sql
UPDATE products
SET price = 110000,
    version = version + 1
WHERE product_id = 123
  AND version = 7
RETURNING product_id, version;
~~~

Ví dụ này yêu cầu bảng `products</BT> có cột `version</BT>. Nếu không có hàng khớp, một writer đã thay đổi bản ghi hoặc dữ liệu không còn tồn tại; ứng dụng phải tải lại và quyết định.

### 23.3. SELECT FOR UPDATE

Khi cần đọc một hàng, tính nghiệp vụ rồi sửa đúng hàng đó:

~~~sql
BEGIN;

SELECT quantity
FROM ssi_lab.stock
WHERE sku = 'BOOK-001'
FOR UPDATE;

-- Kiểm tra và UPDATE trong cùng transaction.
COMMIT;
~~~

Nếu tất cả writer dùng cùng protocol và khóa được lấy đúng trước quyết định, đây có thể là cách đơn giản. Nhưng row lock **không tự bảo vệ một điều kiện về tập hàng chưa tồn tại**.

### 23.4. Guard row hoặc khóa tài nguyên chung

Một transaction có thể khóa hàng đại diện một tài nguyên (ví dụ room, doctor rota) trước khi kiểm tra và sửa nhiều hàng. Tất cả writer phải khóa **cùng hàng điều phối** theo cùng thứ tự.

Ở REPEATABLE READ, việc chờ row lock không tự đổi snapshot đã cố định; guard-row protocol cần được thiết kế và kiểm thử đúng isolation. Không chỉ thêm FOR UPDATE tùy ý rồi khẳng định invariant đã an toàn.

## 24. Vì sao SSI vẫn có false positives?

Một **dangerous structure** là một dấu hiệu đủ để PostgreSQL phải thận trọng, nhưng không phải mọi cấu trúc được phát hiện đều chứng minh tồn tại một **chu trình thực sự đã xảy ra**.

Ví dụ:

~~~text
T1 --rw--> T2 --rw--> T3

Nhưng không có bất kỳ đường nào từ T3 quay về T1.
~~~

Lịch đầy đủ có thể vẫn xếp tuần tự được. Tuy nhiên, chỉ từ thông tin đang theo dõi ở một thời điểm, PostgreSQL có thể cần abort theo quy tắc bảo thủ của SSI để đảm bảo an toàn.

### 24.1. Predicate lock granularity ảnh hưởng false positives

Nếu một query chỉ cần một nhóm nhỏ nhưng planner dùng sequential scan cả bảng, metadata đọc có thể rộng hơn. Ghi vào một hàng khác cùng bảng có thể làm tăng các xung đột được xem xét so với index scan hẹp hơn.

### 24.2. False positive không được giải quyết bằng bỏ retry

Nếu transaction bị abort hợp lệ theo cơ chế SSI, ứng dụng vẫn phải rollback/retry. Một số xung đột thừa có thể được giảm bằng thiết kế query/index/transaction nhưng không bao giờ nên kỳ vọng tỷ lệ 40001 tuyệt đối bằng 0 ở workload cạnh tranh.

### 24.3. Không suy luận lịch nào sai chỉ từ một thông báo 40001

Lỗi có thể chứa chi tiết xung đột, nhưng thông điệp không phải một bằng chứng nghiệp vụ dễ dịch thành “T1 chắc chắn đã làm hỏng dữ liệu”. PostgreSQL đã từ chối commit để **tránh** trường hợp đó.

## 25. Tối ưu hóa transaction để giảm serialization failures

Khi tần suất `40001` cao, hãy đánh giá từng nhóm nguyên nhân.

### 25.1. Giữ transaction ngắn

Nếu transaction đọc xong rồi chờ một API ngoài 10 giây trước khi ghi, nó dễ chồng lấn với nhiều giao dịch khác và mở rộng tập phụ thuộc cần theo dõi.

Không giữ transaction mở khi người dùng đang điền form hoặc khi đang thực hiện tác vụ có thể kéo dài ngoài database.

### 25.2. Chỉ đọc dữ liệu cần cho quyết định

Một câu `SELECT *</BT> quét nhiều hàng rồi lọc ở ứng dụng có thể tạo phạm vi đọc rộng hơn cần thiết. Nếu bất biến chỉ liên quan một phòng và một khoảng thời gian, hãy biểu đạt predicate đó rõ ở SQL.

### 25.3. Index có thể giúp predicate hẹp hơn

Một index thích hợp với điều kiện có thể giúp PostgreSQL truy cập vùng nhỏ hơn và đôi khi giảm xung đột SIREAD bảo thủ. Nhưng index chỉ hữu ích khi planner chọn được kế hoạch phù hợp và workload thật sự hưởng lợi.

### 25.4. Giảm read–modify–write nhiều bước khi có thể

Một câu `UPDATE ... WHERE ... RETURNING` có thể gọn và dễ điều phối hơn chuỗi SELECT→tính ở ứng dụng→UPDATE. Không phải quy tắc nhiều hàng nào cũng biến được thành một câu UPDATE, nhưng nên thử những giải pháp trực tiếp.

### 25.5. Dùng READ ONLY DEFERRABLE cho báo cáo phù hợp

Một báo cáo Serializable chỉ đọc có thể chấp nhận chờ snapshot an toàn để giảm nhu cầu retry.

### 25.6. Tăng retry không phải luôn là tối ưu tốt nhất

Nếu mọi request đều retry nhiều lần, tải có thể tăng theo. Cần xem lại hot predicates, thiết kế write skew, số writers tranh chấp và chiều dài transaction.

## 26. Cấu hình predicate locks: chỉ điều chỉnh khi có bằng chứng

PostgreSQL có các tham số liên quan tới bộ nhớ/độ chi tiết theo dõi predicate locks, chẳng hạn:

- `max_pred_locks_per_transaction`.
- `max_pred_locks_per_relation`.
- `max_pred_locks_per_page`.

Khi tài nguyên theo dõi bị giới hạn, PostgreSQL có thể gộp/thăng cấp tracking lên granularity rộng hơn. Điều đó có thể làm tăng xung đột bảo thủ.

### 26.1. Không chỉnh tham số để “tắt SSI”

Những tham số này không phải công tắc an toàn cho phép bỏ qua phụ thuộc nguy hiểm. Mục tiêu là kiểm soát tài nguyên và chi tiết tracking trong một workload có đo lường.

### 26.2. Tại sao không khuyến nghị một giá trị cố định?

Cấu hình phù hợp phụ thuộc:

- Số transaction concurrent.
- Số quan hệ và trang được đọc.
- Kích thước RAM.
- Query plans.
- Dạng scan và index.
- Tần suất serialization failures.
- Phiên bản PostgreSQL và hạ tầng.

Không tăng giá trị chỉ vì một lần gặp 40001. Trước tiên xác định bất biến, interleaving và phạm vi đọc.

### 26.3. Thay đổi có thể cần restart và ảnh hưởng toàn server

Một số tham số locking/memory liên quan yêu cầu khởi động lại hoặc cấu hình nhất quán. Đừng áp dụng trực tiếp trên production mà chưa đọc tài liệu đúng phiên bản và thử tải.

## 27. Quan sát SIReadLock bằng pg_locks

Trong môi trường thử nghiệm có transaction SERIALIZABLE còn mở, từ **một kết nối giám sát khác**, có thể truy vấn:

~~~sql
SELECT
    l.pid,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    l.page,
    l.tuple
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.mode = 'SIReadLock'
ORDER BY l.pid, l.locktype, relation_name;
~~~

### 27.1. Ý nghĩa cột

| Cột | Ý nghĩa |
|---|---|
| `pid` | Backend liên quan khi có PID |
| `locktype` | Kiểu đối tượng khóa/tracking |
| `mode` | `SIReadLock` với tracking đọc |
| `granted` | Thông tin trạng thái của lock entry |
| `relation_name` | Quan hệ khi có OID relation |
| `page, tuple` | Chi tiết khi lock ở phạm vi page/tuple |

### 27.2. Thấy SIReadLock không đồng nghĩa đang bị chặn

SIReadLock ghi nhận thông tin đọc để SSI phân tích. Một backend không nhất thiết đang chờ vì có SIReadLock.

Để quan sát **đang chờ lock**, cần xem `pg_stat_activity.wait_event_type</BT>, `wait_event</BT>, hoặc `pg_blocking_pids</BT> cho tình huống cụ thể.

### 27.3. Tại sao không thấy một lock ở tuple dự kiến?

Có thể query scan theo cách khác, dữ liệu đã được theo dõi ở page/relation, hoặc transaction/snapshot không còn ở trạng thái bạn tưởng. Không suy luận SSI tắt chỉ vì không có đúng một dòng tuple lock.

### 27.4. Truy cập thống kê có giới hạn quyền

Một role không có quyền giám sát có thể không thấy tất cả chi tiết từ `pg_stat_activity</BT>. Dùng quyền tối thiểu phù hợp thay vì cấp quyền rộng chỉ để debug.

## 28. Theo dõi 40001 và thời gian transaction

Một truy vấn quan sát:

~~~sql
SELECT
    pid,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Hữu ích để phát hiện:

- Transaction mở lâu.
- `idle in transaction`.
- Nhiều backend cùng chờ lock.
- Truy vấn đang giữ một snapshot trong thời gian dài.

### 28.1. pg_stat_database không có bộ đếm trực tiếp mọi 40001

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

`xact_rollback</BT> tính các transaction rollback từ nhiều nguyên nhân, không riêng SSI. `deadlocks</BT> đếm deadlock, không phải serialization failures.

Do đó, để đo chính xác tỷ lệ 40001:

- Thu thập SQLSTATE tại ứng dụng.
- Ghi metrics theo endpoint, transaction type và số lần retry.
- Dùng server logs nếu logging phù hợp.
- Liên hệ với slow queries, contention và transaction durations.

### 28.2. Alert nên dựa trên tác động

Một vài lần serialization retry là bình thường ở hệ thống có tranh chấp. Điều cần quan tâm là tỷ lệ thất bại cuối cùng, p95/p99 latency, retry attempts và khả năng giữ invariant, không chỉ số raw lỗi.

## 29. EXPLAIN và chỉ mục dưới SSI

Query plan ảnh hưởng phạm vi đọc/ghi và chi phí.

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM ssi_lab.doctors
WHERE on_call;
~~~

`EXPLAIN</BT> cho kế hoạch dự kiến; nó không thực hiện truy vấn như `EXPLAIN ANALYZE</BT>.

### 29.1. Khi nào xem index?

Ví dụ một bảng bookings lớn thường tìm:

~~~sql
SELECT 1
FROM bookings
WHERE room_id = 101
  AND status = 'confirmed'
  AND starts_at < TIMESTAMPTZ '2026-11-14 12:00+07'
  AND ends_at > TIMESTAMPTZ '2026-11-14 11:00+07';
~~~

Index cần được chọn theo schema thật, predicate, range query và dữ liệu. Không khẳng định một B-tree trên `room_id</BT> tự giải quyết tối ưu mọi overlap query.

### 29.2. EXPLAIN ANALYZE thực sự chạy

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM ssi_lab.doctors
WHERE on_call;
~~~

Trong môi trường thử nghiệm nhỏ, câu SELECT an toàn. Nhưng không chạy `EXPLAIN ANALYZE</BT> trên DML hoặc query rất nặng rồi tưởng chỉ “xem kế hoạch”: ANALYZE thực thi truy vấn.

### 29.3. Đừng thay đổi kế hoạch để đánh đổi correctness

Tạo index có thể giảm false positives/overhead, nhưng invariant vẫn cần SERIALIZABLE hoặc protocol phù hợp. Query chạy nhanh hơn không chứng minh nó đã tránh write skew.

## 30. Khi một transaction ở SERIALIZABLE còn giao dịch khác không ở đó

Một hiểu lầm là chỉ cần transaction “quan trọng” chạy SERIALIZABLE, còn mọi writer khác muốn làm gì cũng được.

Nếu nhiều đường ghi vào cùng dữ liệu:

- API A kiểm tra invariant đúng trong transaction Serializable.
- Batch job B UPDATE trực tiếp mà **không kiểm tra invariant**.
- Script C thay dữ liệu bằng quyền cao.

Khi đó kết quả có thể sai về mặt nghiệp vụ ngay cả nếu lịch các transaction có thể xếp tuần tự. Một thứ tự tuần tự cũng có thể **chứa một transaction ghi sai**.

### 30.1. Muốn có bảo đảm thì mọi writer cần protocol chung

Đối với bất biến dựa vào nhiều transactions, hãy thống nhất cách kiểm tra, isolation và quyền cho các đường ghi. Nếu có thể, dùng constraints ở database để bảo vệ nhất quán ngay cả khi một client quên kiểm tra.

### 30.2. Không tự kết luận việc trộn isolation luôn phá mọi bảo đảm

PostgreSQL vẫn thực thi đúng ngữ nghĩa cho mỗi transaction theo isolation đã chọn. Vấn đề là **bảo đảm serializable end-to-end cho toàn workflow** không thể được suy ra đơn giản khi có writer ngoài protocol. Phải phân tích tính đúng thực tế.

## 31. SSI và unique/exclusion constraints

Một số lỗi concurrency xuất hiện khi hai transaction muốn tạo cùng key hoặc cùng tài nguyên:

~~~sql
INSERT INTO ssi_lab.request_ids(request_id)
VALUES ('req-001');
~~~

Nếu transaction khác thêm cùng request ID, một giao dịch có thể gặp `23505` thay vì 40001, tùy tình huống và thứ tự.

### 31.1. UNIQUE vẫn nên được giữ

Đừng bỏ UNIQUE chỉ vì muốn tất cả conflict đều trở thành serialization errors. Constraint là nơi bảo vệ tính duy nhất trực tiếp, ít phụ thuộc vào việc mọi writer có thực hiện pre-check đúng hay không.

### 31.2. Khi nào retry 23505?

Nếu người dùng cố tạo một tên đăng nhập đã tồn tại, retry không thay đổi kết quả; nên báo conflict.

Nếu ứng dụng tự sinh một business key bằng cách đọc rồi chọn “giá trị kế tiếp” và gặp duplicate do concurrency, cần sửa protocol sinh key. Một số trường hợp có thể retry **toàn quyết định** với dữ liệu mới; nhưng không coi mọi unique violation đều là lỗi tạm thời.

### 31.3. Exclusion constraint

Tương tự, trùng khoảng thời gian booking có thể bị báo `23P01`. Xử lý có thể là “khung giờ đã được đặt”, không phải retry ngẫu nhiên tới khi thành công.

## 32. Những tình huống SSI không thể tự giải quyết

### 32.1. Gọi hệ thống ngoài

Gửi email, phát hành hóa đơn qua API hoặc charge payment không nằm trong transaction PostgreSQL. SSI không tự rollback các hành động đó.

### 32.2. Quy tắc chỉ tồn tại trong đầu người thiết kế

Nếu code không đọc/check điều kiện cần bảo vệ, SSI không thể tự tạo invariant.

### 32.3. Dữ liệu sai từ trước

SSI không tự sửa những hàng đã có giá trị không hợp lệ hoặc những quan hệ thiếu constraint.

### 32.4. Quyền truy cập sai

Serializable không có nghĩa request được phép xem/sửa hàng. Cần authorization ở service, GRANT/RLS theo thiết kế.

### 32.5. Request lặp lại

Client timeout rồi gửi lại lệnh tạo đơn có thể tạo hai đơn nếu không có idempotency key, dù mỗi lệnh được commit serializably.

### 32.6. Logic phức tạp ngoài transaction

Nếu application đọc trạng thái trong transaction A, commit, sau đó quyết định và cập nhật ở transaction B mà không kiểm tra lại, các bước không tạo thành một đơn vị serializable duy nhất.

## 33. Một ví dụ khó: ghi khác hàng nhưng cùng bất biến tổng

Giả sử hai phòng ban có mức ngân sách, và quy tắc tổng ngân sách đã cam kết không vượt 3000. Ban đầu mỗi phòng có 1000, còn 1000 khả dụng.

T1 và T2 đều đọc tổng 2000 rồi mỗi transaction tăng ngân sách phòng khác thêm 800:

~~~text
Ban đầu:
Engineering = 1000
Operations  = 1000
Total       = 2000

T1: SELECT SUM(amount) -> 2000
T2: SELECT SUM(amount) -> 2000

T1: UPDATE Engineering = 1800
T2: UPDATE Operations  = 1800

Nếu cả hai COMMIT:
Total = 3600 > 3000
~~~

Đây là write skew vì hai transaction kiểm tra cùng tổng nhưng ghi khác hàng.

### 33.1. READ COMMITTED/REPEATABLE READ có thể không bảo vệ

Nếu các lần đọc diễn ra trước khi bất kỳ transaction nào ghi và hai UPDATE không đụng cùng hàng, một lịch không mong muốn có thể xảy ra.

### 33.2. SERIALIZABLE + kiểm tra trong transaction

Mỗi transaction phải:

1. `BEGIN SERIALIZABLE`.
2. Đọc tổng hiện hành.
3. Kiểm tra `total + requested_increment <= 3000`.
4. UPDATE đúng hàng.
5. COMMIT với xử lý 40001.

Khi retry, giao dịch thứ hai sẽ đọc tổng đã tăng lên 2800 rồi từ chối tăng thêm 800.

### 33.3. Có phương án mô hình dữ liệu khác không?

Có. Nếu ngân sách tổng có thể biểu diễn bằng **một hàng guard/remaining_budget**, cập nhật nguyên tử:

~~~sql
UPDATE budget_limits
SET remaining = remaining - 800
WHERE budget_key = 'company'
  AND remaining >= 800
RETURNING remaining;
~~~

Ví dụ cấu trúc này cần bảng `budget_limits` tồn tại. Một hàng điều phối với constraint và atomic UPDATE có thể đơn giản hơn SSI cho một số quy tắc.

Chọn thiết kế dựa trên số nguồn dữ liệu, độ phức tạp invariant và khả năng tập trung quyết định.

## 34. Thời điểm COMMIT và tác động của phụ thuộc nguy hiểm

Một transaction SERIALIZABLE có thể thực hiện SELECT/UPDATE thành công nhưng thất bại tại COMMIT.

~~~text
T1: BEGIN
T1: SELECT ...                -> thành công
T1: UPDATE ...                -> thành công
T2: commit một lịch liên quan
T1: COMMIT                    -> ERROR 40001
~~~

### 34.1. Đừng báo thành công sớm

Không trả HTTP 200 “đã đặt hàng” chỉ vì UPDATE đã trả một hàng khi transaction chưa commit. Nếu COMMIT thất bại, thay đổi có thể đã được rollback.

### 34.2. RETURNING không chứng minh COMMIT thành công

~~~sql
UPDATE ssi_lab.doctors
SET on_call = FALSE
WHERE doctor_id = 1
RETURNING doctor_id;
~~~

`RETURNING` cho biết lệnh UPDATE đã tác động đến hàng trong transaction hiện tại. Nó không khẳng định transaction sẽ commit thành công.

### 34.3. Savepoint không thay retry toàn transaction

Một ứng dụng có thể dùng savepoint để phục hồi một số lỗi bên trong transaction. Nhưng serialization failure làm cho quyết định dựa trên snapshot cũ không còn hợp lệ; thực hành an toàn là retry **toàn transaction logic**, không chỉ quay lại một savepoint rồi lặp SQL cuối.

### 34.4. Nhiều statement trong cùng transaction phải dùng cùng connection

Nếu ORM chạy SELECT ở connection A nhưng UPDATE ở connection B ngoài transaction, chúng không còn nằm trong cùng đơn vị SSI. Dùng transaction manager để bảo đảm mọi thao tác kiểm tra và ghi tham gia cùng transaction.

## 35. Những hiểu lầm thường gặp về SSI

### 35.1. “SERIALIZABLE tức là tất cả transaction chạy lần lượt”

Sai. PostgreSQL cho chạy đồng thời và dùng SSI/abort để bảo đảm lịch commit có thể tuần tự hóa.

### 35.2. “REPEATABLE READ không phantom nên đã là serializable”

Sai. Write skew có thể xảy ra dù mỗi transaction đọc một snapshot ổn định.

### 35.3. “Hai transaction sửa khác hàng thì không thể xung đột”

Sai. Chúng có thể cùng đọc một bất biến và tạo rw-antidependencies.

### 35.4. “Mọi lần một giá trị đã đọc bị thay đổi đều phải abort”

Sai. Một cạnh rw riêng lẻ có thể hoàn toàn hợp lệ; cần xem cấu trúc phụ thuộc.

### 35.5. “Dangerous structure chắc chắn đồng nghĩa có cycle thực tế”

Không nhất thiết. PostgreSQL phát hiện bảo thủ và có thể abort để tránh rủi ro, kể cả khi lịch cụ thể vẫn serializable.

### 35.6. “SIReadLock ngăn người khác ghi”

Sai. Nó theo dõi predicate reads/xung đột; không phải FOR UPDATE.

### 35.7. “Không thấy tuple-level SIReadLock nghĩa là không có SSI”

Sai. Tracking có thể ở page/relation hoặc trong trạng thái khác; cần hiểu plan và transaction.

### 35.8. “40001 là bug PostgreSQL”

Sai. Đây là cơ chế từ chối một transaction để giữ bảo đảm isolation.

### 35.9. “40001 chỉ xảy ra lúc UPDATE”

Sai. Nó có thể xuất hiện tại COMMIT.

### 35.10. “Retry chỉ câu UPDATE cuối là đủ”

Sai. Phải đọc và quyết định lại với snapshot mới.

### 35.11. “40001 và 40P01 là cùng lỗi”

Sai. Một bên là serialization failure, một bên là deadlock.

### 35.12. “Serializable tự biết ít nhất một bác sĩ phải trực”

Sai. Logic kiểm tra phải được biểu diễn trong transaction hoặc constraint/protocol phù hợp.

### 35.13. “Không cần UNIQUE nếu đã dùng SERIALIZABLE”

Sai. Constraint trực tiếp bảo vệ tập giá trị và áp dụng xuyên các writer thích hợp.

### 35.14. “READ ONLY không thể gây serialization conflict”

Không đúng trong mọi lịch. Read-only transaction có thể tham gia phụ thuộc; `DEFERRABLE` là giải pháp đặc biệt khi cần snapshot an toàn.

### 35.15. “DEFERRABLE làm transaction đọc không bao giờ phải chờ”

Sai. Nó có thể chờ lấy snapshot an toàn ban đầu.

### 35.16. “Index chắc chắn loại bỏ 40001”

Sai. Index có thể giảm phạm vi theo dõi/chi phí, không xóa quan hệ xung đột thật.

### 35.17. “Bật SERIALIZABLE sẽ tự xử lý email và payment”

Sai. External systems cần idempotency, outbox và reconciliation.

### 35.18. “Thông báo UPDATE RETURNING có hàng nghĩa là đã commit”

Sai. COMMIT có thể thất bại.

### 35.19. “Đổi isolation xuống READ COMMITTED để không có retry là sửa lỗi”

Sai nếu bất biến đòi serializability. Nó có thể chỉ cho lịch sai commit.

### 35.20. “Mọi lỗi unique đều nên retry”

Sai. Nhiều lỗi là conflict nghiệp vụ thật sự.

## 36. Bài tập thực hành

### Bài 1 — Snapshot và write skew

Tại sao hai transaction đều đọc snapshot hợp lệ ở REPEATABLE READ nhưng vẫn có thể phá bất biến tổng?

**Gợi ý:** Snapshot không tự bảo vệ quan hệ phụ thuộc giữa nhiều giao dịch; hai transaction có thể ghi các hàng khác nhau.

### Bài 2 — Đồ thị phụ thuộc

Vẽ `T1 --rw--> T2` khi T1 đọc phiên bản X cũ và không nhìn thấy thay đổi X của T2.

**Gợi ý:** T1 phải đứng trước T2 trong thứ tự phù hợp với kết quả đọc đó.

### Bài 3 — wr hay rw?

T1 commit X=50, T2 đọc X=50. Đây là quan hệ gì?

**Đáp án:** T1 --wr--> T2.

### Bài 4 — ww

T1 UPDATE X rồi commit; T2 UPDATE X sau đó. Hãy mô tả ý nghĩa quan hệ ww.

**Gợi ý:** T2 ghi phiên bản sau T1, chịu thứ tự ghi phù hợp.

### Bài 5 — Dangerous structure

Điền tên cạnh:

~~~text
T_in --?--> T_pivot --?--> T_out
~~~

**Đáp án:** Hai cạnh rw-antidependency nối tiếp.

### Bài 6 — Có phải mọi cấu trúc hai cạnh đều lỗi?

Một lịch có `T1 --rw--> T2 --rw--> T3` nhưng không có đường khép chu trình. Có chắc lịch đó không tuần tự hóa được không?

**Gợi ý:** Không. Dangerous structure là dấu hiệu phát hiện bảo thủ, không phải chứng minh hoàn chỉnh của chu trình.

### Bài 7 — Write skew hai bác sĩ

Sau hai commit REPEATABLE READ, on_call count từ 2 xuống 0. Vì sao không phải lost update cùng hàng?

**Gợi ý:** T1 sửa An, T2 sửa Bình; invariant chung mới bị phá.

### Bài 8 — SERIALIZABLE

Điều gì cần xảy ra nếu cùng lịch write skew được chạy đúng với SERIALIZABLE?

**Gợi ý:** Không thể cho cả hai commit thành công; một transaction có thể nhận 40001.

### Bài 9 — Retry

T2 gặp 40001 sau khi đã đọc count=2. Chỉ chạy lại UPDATE Bình=false được không?

**Đáp án:** Không. Phải mở transaction mới, đọc lại count và quyết định lại.

### Bài 10 — COMMIT

Tại sao application chỉ bắt SQLException quanh SELECT/UPDATE nhưng không bắt COMMIT là chưa đủ?

**Gợi ý:** 40001 có thể xuất hiện ở COMMIT.

### Bài 11 — SIReadLock

`SIReadLock` có nhất thiết chặn transaction khác INSERT hàng thỏa predicate không?

**Đáp án:** Không, nó phục vụ theo dõi phụ thuộc cho SSI.

### Bài 12 — Predicate rỗng

Một SELECT kiểm tra “không có booking trùng” trả 0 hàng. Có thể có rw-dependency khi transaction khác chèn booking trùng không?

**Gợi ý:** Có; đọc sự vắng mặt theo predicate cũng quan trọng.

### Bài 13 — Row lock

Vì sao `SELECT ... FOR UPDATE WHERE booking_id = 999` không tự khóa một booking chưa tồn tại?

**Gợi ý:** Row lock nhắm tới hàng được chọn, không tạo khóa trên mọi hàng tương lai.

### Bài 14 — Read-only DEFERRABLE

Chế độ nào phù hợp với báo cáo read-only cần snapshot serializable an toàn và chấp nhận chờ?

**Đáp án:** `SERIALIZABLE READ ONLY DEFERRABLE`.

### Bài 15 — READ COMMITTED và báo cáo

T1 đọc Engineering trước khi T2 chuyển ngân sách, rồi đọc Operations sau khi T2 commit. Hiện tượng gì?

**Đáp án:** Read skew.

### Bài 16 — Cùng một SELECT

Vì sao `SELECT SUM(amount) FROM budget` trong một câu có thể tránh read skew giữa hai câu SELECT tách rời ở READ COMMITTED?

**Gợi ý:** Một SELECT thông thường dùng một statement snapshot nhất quán.

### Bài 17 — SQLSTATE

Ghép các mã với hiện tượng:

| Mã | Hiện tượng |
|---|---|
| `40001` | ? |
| `40P01` | ? |
| `23505` | ? |
| `23P01` | ? |

**Đáp án:** Serialization failure, deadlock, unique violation, exclusion violation.

### Bài 18 — Chọn constraint

Nếu hai booking không được trùng cùng phòng/khoảng giờ, giải pháp constraint nào của PostgreSQL đáng cân nhắc?

**Gợi ý:** Exclusion constraint phù hợp với range types và index.

### Bài 19 — Cột version

Một UI sửa đơn hàng dựa trên version cũ, hãy đề xuất optimistic locking.

**Gợi ý:** `UPDATE ... SET version=version+1 WHERE id=? AND version=? RETURNING ...`.

### Bài 20 — Tồn kho

Viết câu UPDATE chỉ trừ 3 đơn vị nếu tồn kho đủ.

~~~sql
UPDATE ssi_lab.stock
SET quantity = quantity - 3
WHERE sku = 'BOOK-001'
  AND quantity >= 3
RETURNING quantity;
~~~

**Gợi ý:** Nếu không có hàng RETURNING, không coi cấp phát thành công.

### Bài 21 — Index và SSI

Vì sao thêm index đúng predicate có thể giúp giảm một số false positive serialization failures?

**Gợi ý:** Truy vấn có thể quét phạm vi nhỏ hơn, giảm tracking rộng không cần thiết.

### Bài 22 — Không có đảm bảo tuyệt đối

Có nên hứa “sau khi tạo index sẽ không còn 40001” không?

**Đáp án:** Không. Conflicts thực vẫn có thể xảy ra.

### Bài 23 — Transaction dài

Tại sao không nên mở Serializable transaction rồi chờ người dùng duyệt form nhiều phút?

**Gợi ý:** Tăng overlap, giữ snapshot, ảnh hưởng VACUUM và xung đột.

### Bài 24 — Idempotency

Nếu COMMIT thất bại nhưng email đã gửi, retry có thể gây gì?

**Gợi ý:** Gửi email lặp; cần outbox/idempotency.

### Bài 25 — Nhiều writer

Nếu API dùng SSI nhưng background job không kiểm tra invariant, liệu có bảo đảm chính sách nhiều hàng được giữ không?

**Đáp án:** Chưa; mọi đường ghi phải theo protocol hoặc constraint phù hợp.

### Bài 26 — Quan sát SIReadLock

Viết truy vấn `pg_locks` lọc `mode='SIReadLock'` và quan sát granularity `relation/page/tuple`.

**Gợi ý:** Dựa trên ví dụ ở phần 27.

### Bài 27 — Đọc metrics

`pg_stat_database.deadlocks` có phải số lần 40001 không?

**Đáp án:** Không. Cần ghi SQLSTATE ở ứng dụng/log để đo serialization failure.

### Bài 28 — 40001 vs 23505

Một request tạo username đã có sẵn. Có nên luôn retry 23505 như 40001 không?

**Gợi ý:** Không. Unique violation có thể là conflict nghiệp vụ bền vững.

### Bài 29 — Bảo vệ tổng ngân sách

Hai transaction mỗi cái tăng 800 trên hàng khác nhau sau khi đọc total=2000 với giới hạn 3000. Hãy giải thích vì sao cả hai commit là write skew.

**Gợi ý:** Tổng 3600 vi phạm invariant dù hai UPDATE khác hàng.

### Bài 30 — Guard row

Trong trường hợp ngân sách tổng, có thể chuyển thành một hàng `remaining_budget` và dùng atomic UPDATE có điều kiện không?

**Gợi ý:** Có thể, nếu mọi writer dùng cùng protocol và dữ liệu được đồng bộ đúng.

### Bài 31 — Snapshot và BEGIN

Gõ BEGIN Serializable rồi để vài giây mới SELECT có chắc snapshot được lấy chính xác tại thời điểm BEGIN không?

**Đáp án:** Không; snapshot thường được thiết lập khi câu lệnh cần snapshot đầu tiên chạy.

### Bài 32 — Quyết định chọn mức isolation

Một API chỉ giảm stock trong một hàng có CHECK và atomic UPDATE; một workflow khác kiểm tra tổng trên nhiều hàng và sửa các hàng khác nhau. Tại sao không nên mặc định dùng cùng chiến lược cho hai bài toán?

**Gợi ý:** Bất biến và hình thức xung đột khác nhau; chọn cơ chế đơn giản nhất chứng minh được tính đúng.

## 37. Quy trình kiểm tra một lỗi concurrency nghi là SSI

Một quy trình thực tế:

1. **Xác định invariant** cần giữ sau COMMIT, viết thành một điều kiện có thể kiểm tra.
2. **Liệt kê transaction types** có thể đọc hoặc sửa dữ liệu liên quan.
3. **Ghi đúng isolation level** đang dùng ở từng loại giao dịch.
4. **Vẽ lịch xen kẽ T1/T2/T3**, kèm snapshot, đọc, ghi và commit.
5. **Phân biệt cạnh wr, ww và rw**, xem có chu trình hoặc dangerous structure.
6. **Tái hiện trên hai kết nối thật**, không dựa vào test tuần tự.
7. **Xác nhận SQLSTATE** của lỗi, không chỉ khớp text thông báo.
8. **Đảm bảo retry toàn transaction**, kiểm tra lại domain preconditions.
9. **Kiểm tra side effects/idempotency** ngoài DB.
10. **Đo 40001, latency và transaction duration** trong workload.
11. **Kiểm tra query plans và phạm vi predicate reads**, cân nhắc index phù hợp.
12. **Cân nhắc constraint/atomic update/guard row** nếu giản lược được invariant.
13. **Đảm bảo tất cả writer dùng protocol**, gồm API, workers, scripts.
14. **Giữ transaction ngắn**, tránh chờ ngoài DB.
15. **Bổ sung integration test** cho lịch cạnh tranh đã tìm ra.

Một transaction bị từ chối vì SSI không phải thất bại của tính nhất quán. **Nó là cơ chế ngăn thất bại của dữ liệu đã commit**. Điều cần cải thiện là cách ứng dụng xử lý abort và cách mô hình hóa bất biến, không phải che lỗi.

## 38. Bảng ghi nhớ nhanh

| Khái niệm | Điểm cốt lõi |
|---|---|
| MVCC | Các phiên bản hàng được nhìn thấy theo snapshot |
| Snapshot isolation | Mỗi transaction đọc snapshot ổn định; vẫn có thể write skew |
| PostgreSQL REPEATABLE READ | Triển khai snapshot isolation, ngăn phantom truyền thống |
| PostgreSQL SERIALIZABLE | Dùng SSI để bảo đảm lịch commit serializable |
| Serialization graph | Đỉnh là transaction, cạnh là phụ thuộc |
| `wr` | Transaction sau đọc giá trị transaction trước đã ghi |
| `ww` | Quan hệ ghi tiếp sau ghi |
| `rw` | Đọc không nhìn thấy thay đổi từ transaction ghi khác |
| rw-antidependency | Trọng tâm việc phát hiện nguy hiểm ở SSI |
| Dangerous structure | `T_in --rw--> T_pivot --rw--> T_out` |
| Cycle | Không thể xếp một thứ tự tuần tự phù hợp mọi cạnh |
| Write skew | Đọc invariant chung, ghi khác hàng, phá invariant |
| Predicate read | Đọc tập hàng theo WHERE, kể cả lúc tập rỗng |
| SIReadLock | Tracking đọc cho SSI, không phải row lock chặn ghi |
| Granularity | Có thể ở tuple, page hoặc relation |
| False positive | Abort bảo thủ dù lịch cụ thể có thể serializable |
| SQLSTATE 40001 | Serialization failure; retry toàn transaction |
| SQLSTATE 40P01 | Deadlock; nguyên nhân khác 40001 |
| COMMIT có thể lỗi? | Có, phải xử lý cả COMMIT |
| Retry đúng | BEGIN mới → đọc lại → quyết định lại → ghi → COMMIT |
| READ ONLY DEFERRABLE | Chờ snapshot an toàn cho Serializable read-only |
| UNIQUE/CHECK/EXCLUDE | Constraint bảo vệ những invariant diễn đạt được |
| Atomic UPDATE | Giảm race cho điều kiện trên một hàng |
| Row lock FOR UPDATE | Khóa hàng đã chọn, không tự khóa predicate tương lai |
| Truy vấn theo dõi | `pg_locks</BT>, `pg_stat_activity</BT>, SQLSTATE metrics |
| Tuning | Query plan, index, transaction duration, predicate lock memory |
| External side effects | Cần idempotency/outbox/reconciliation |
| Bảo đảm tổng thể | Mọi đường ghi phải tuân thủ invariant và protocol |

---

## Kết luận

**Serializable Snapshot Isolation** là cách PostgreSQL đưa ra bảo đảm **SERIALIZABLE** trong môi trường MVCC mà không đơn giản khóa toàn bộ dữ liệu để chạy từng giao dịch một. SSI cho phép đọc theo snapshot, theo dõi quan hệ đọc–ghi và nhận diện các **rw-antidependencies** có thể ghép thành **dangerous structure**. Khi lịch thực thi có nguy cơ không tuần tự hóa được, PostgreSQL có thể hủy một transaction với **SQLSTATE 40001** thay vì cho tất cả thay đổi cùng commit.

Ví dụ hai bác sĩ cùng xin nghỉ cho thấy lý do cốt lõi: **REPEATABLE READ giữ snapshot ổn định nhưng vẫn có thể xảy ra write skew** khi hai transaction sửa những hàng khác nhau. SSI bảo vệ tính đúng bằng cách phát hiện phụ thuộc chéo, kể cả khi các hàng được đọc nằm trong một predicate như `WHERE on_call=TRUE`. Các dấu theo dõi `SIReadLock</BT> không phải row lock chặn mọi thao tác ghi; chúng hỗ trợ PostgreSQL đánh giá những lịch nguy hiểm và có thể tạo abort bảo thủ trong một số trường hợp.

Ứng dụng dùng SERIALIZABLE phải được viết để **retry toàn transaction**, bao gồm bước đọc lại, kiểm tra lại điều kiện nghiệp vụ và xử lý lỗi tại COMMIT. Với transaction chỉ đọc, `SERIALIZABLE READ ONLY DEFERRABLE` là lựa chọn đáng cân nhắc khi cần snapshot an toàn. Với các bất biến đơn giản, constraint và atomic UPDATE có thể tốt hơn một cơ chế phối hợp phức tạp; với bất biến nhiều hàng, SSI mang lại bảo đảm quan trọng mà snapshot isolation thông thường chưa đủ.

Nguyên tắc cuối cùng: **đừng chỉ hỏi mỗi transaction đã đọc một snapshot nhất quán hay chưa; hãy hỏi tất cả transaction được commit có thể giải thích bằng một thứ tự tuần tự hợp lệ hay không**. Đó chính là vấn đề SSI giải quyết và là nền tảng để xây dựng giao dịch PostgreSQL an toàn dưới tải đồng thời.
