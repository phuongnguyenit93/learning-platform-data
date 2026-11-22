# Khóa khoảng, gap lock, next-key lock và predicate lock: phân biệt mục tiêu

Khi một giao dịch truy vấn dữ liệu theo điều kiện, việc khóa các dòng đã tìm thấy đôi khi vẫn chưa đủ để bảo vệ kết quả. Một giao dịch khác có thể chèn một dòng mới thỏa điều kiện vào giữa lúc giao dịch thứ nhất đang chạy. Dòng mới này được gọi là **phantom row** (dòng ảo), còn hiện tượng tập kết quả thay đổi do thao tác đồng thời được gọi là **phantom read**.

Các hệ quản trị cơ sở dữ liệu dùng nhiều cơ chế để bảo vệ khoảng dữ liệu hoặc điều kiện truy vấn: **range lock**, **gap lock**, **next-key lock** và **predicate lock**. Chúng có liên hệ với nhau nhưng không đồng nghĩa. Range lock mô tả việc bảo vệ một khoảng khóa; gap lock bảo vệ khoảng trống giữa các khóa chỉ mục; next-key lock kết hợp một bản ghi chỉ mục với khoảng trống đứng trước nó; predicate lock biểu diễn điều kiện logic mà giao dịch đã đọc.

Điểm cần phân biệt là **mục tiêu bảo vệ** và **cách triển khai**. Một cơ chế có thể chặn thao tác chèn ngay lập tức; cơ chế khác chỉ ghi nhận phụ thuộc để phát hiện lịch giao dịch không tuần tự hóa được rồi hủy một giao dịch. Cùng một mục tiêu ngăn phantom có thể được thực hiện bằng kỹ thuật khác nhau tùy DBMS và mức cô lập.

## 1. Vấn đề phantom: khóa các dòng hiện có chưa đủ

Giả sử bảng `employee` có chỉ mục trên cột `salary`, và T1 cần đọc tất cả nhân viên có lương từ 80 đến dưới 100:

```sql
SELECT employee_id, salary
FROM employee
WHERE salary >= 80
  AND salary < 100;
```

Tại thời điểm T1 đọc, kết quả có hai dòng:

| employee_id | salary |
|---:|---:|
| 10 | 82 |
| 25 | 95 |

Trong lúc T1 vẫn đang chạy, T2 chèn nhân viên mới có `salary = 90` rồi commit. Nếu T1 chạy lại truy vấn và nhìn thấy dòng mới, tập kết quả đã thay đổi dù các dòng ban đầu không bị sửa.

```text
T1: SELECT salary >= 80 AND salary < 100
    Kết quả: 82, 95
          |
          | T2 INSERT salary = 90; COMMIT
          v
T1: chạy lại cùng điều kiện
    Kết quả: 82, 90, 95
```

Khóa `S` trên hai dòng 82 và 95 chỉ bảo vệ hai dòng đang tồn tại. Nó không nhất thiết ngăn T2 tạo một dòng mới có khóa chỉ mục nằm giữa chúng. Muốn giữ ổn định tập dữ liệu theo điều kiện, hệ thống phải bảo vệ cả phạm vi mà dòng mới có thể xuất hiện hoặc theo dõi phụ thuộc vào điều kiện truy vấn.

Phantom đặc biệt quan trọng khi truy vấn dùng để kiểm tra một quy tắc nghiệp vụ, ví dụ:

- Phòng họp không có lịch đặt nào giao với khoảng thời gian cần đặt.
- Không có đơn hàng đang mở cho cùng một mã khách hàng và loại giao dịch.
- Số lượng bản ghi thỏa điều kiện chưa vượt quá giới hạn.
- Không có nhân viên khác đang giữ một vai trò duy nhất.

Nếu chỉ khóa những dòng đã tìm thấy, giao dịch khác có thể chèn dòng mới làm điều kiện kiểm tra ban đầu không còn đúng.

## 2. Khoảng khóa và vai trò của chỉ mục

Các cơ chế range/gap/next-key thường dựa vào thứ tự của khóa chỉ mục. Hãy hình dung chỉ mục B-tree có các giá trị:

```text
10 -------- 20 -------- 30 -------- 40
```

Giữa hai khóa đã tồn tại có các khoảng trống logic:

```text
(-∞, 10) | (10, 20) | (20, 30) | (30, 40) | (40, +∞)
```

Một dòng mới có giá trị khóa 25 sẽ được chèn vào khoảng `(20, 30)`. Nếu giao dịch T1 cần bảo vệ điều kiện chỉ mục bao phủ khoảng này, DBMS phải có cách ngăn hoặc phát hiện thao tác chèn 25.

Trong thực tế, khoảng được xác định theo khóa chỉ mục, không nhất thiết theo thứ tự hiển thị của một cột đơn. Với chỉ mục ghép `(tenant_id, salary)`, thứ tự khóa là thứ tự từ điển trên cả hai thành phần. Điều kiện truy vấn, collation, kiểu dữ liệu, thứ tự cột chỉ mục và kế hoạch thực thi đều ảnh hưởng đến phạm vi có thể được bảo vệ.

Chỉ mục rất quan trọng vì nó cung cấp cấu trúc có thứ tự để DBMS xác định ranh giới. Nếu không có chỉ mục phù hợp, hệ quản trị có thể phải quét phạm vi rộng hơn hoặc khóa ở mức thô hơn. Một truy vấn logic giống nhau nhưng có execution plan khác nhau có thể tạo ra footprint khóa khác nhau.

## 3. Range lock — khóa một khoảng khóa

**Range lock (khóa khoảng)** là cách gọi chung cho việc bảo vệ một khoảng giá trị khóa, nhằm phối hợp các thao tác đọc/cập nhật với thao tác chèn hoặc thay đổi khóa nằm trong khoảng đó.

Trong SQL Server, khái niệm cụ thể thường gặp là **key-range lock**. Khi chạy ở mức cô lập `SERIALIZABLE`, SQL Server có thể khóa các khoảng trong chỉ mục để ngăn giao dịch khác chèn khóa mới thỏa điều kiện của truy vấn cho đến khi transaction kết thúc.

Ví dụ:

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;

SELECT employee_id, salary
FROM dbo.Employee
WHERE salary >= 80
  AND salary < 100;

-- T1 tiếp tục xử lý trước khi kết thúc transaction.
COMMIT;
```

Nếu có chỉ mục phù hợp trên `salary`, SQL Server có thể dùng key-range lock để bảo vệ khoảng liên quan. Một giao dịch khác muốn chèn nhân viên có `salary = 90` có thể phải chờ đến khi T1 kết thúc.

Range lock không phải một chế độ khóa duy nhất có định nghĩa giống hệt trong mọi DBMS. Đây là tên khái quát cho việc khóa một vùng khóa; từng sản phẩm có cách biểu diễn, tên mode, ranh giới và thuật toán kiểm tra riêng. Trong SQL Server, key-range lock có thể kết hợp thành phần khóa khoảng với khóa trên khóa chỉ mục.

### 3.1. Một số key-range lock mode trong SQL Server

SQL Server có các mode key-range phổ biến sau:

| Mode | Ý nghĩa khái quát |
|---|---|
| `RangeS-S` | Khóa chia sẻ trên khoảng và chia sẻ trên khóa chỉ mục liên quan |
| `RangeS-U` | Khóa chia sẻ trên khoảng, dùng thành phần update trên khóa chỉ mục |
| `RangeI-N` | Khóa kiểm tra khoảng khi chèn; thành phần khóa trên khóa chỉ mục là null |
| `RangeX-X` | Khóa độc quyền trên khoảng và độc quyền trên khóa chỉ mục liên quan |

Các mode này phối hợp với những khóa khác trong lock manager. Không nên suy ra rằng một truy vấn luôn nhận đúng một mode cố định: mode thực tế phụ thuộc thao tác, mức cô lập, kế hoạch truy vấn và tình trạng cạnh tranh.

### 3.2. Mục tiêu của range lock

Range lock bảo vệ **một khoảng trong không gian khóa chỉ mục**. Nhờ vậy, hệ thống có thể ngăn một khóa mới xuất hiện trong phạm vi đã được đọc hoặc cập nhật, giúp duy trì ngữ nghĩa của truy vấn trong transaction ở mức cô lập phù hợp.

Range lock thường được nhắc đến trong SQL Server, nhưng ý tưởng bảo vệ khoảng khóa cũng xuất hiện trong các cơ chế khác. Không nên đồng nhất tên gọi range lock với gap lock của InnoDB hay predicate lock trong các hệ thống dùng SSI.

## 4. Gap lock — khóa khoảng trống giữa các khóa chỉ mục

**Gap lock** là khóa bảo vệ khoảng trống giữa các giá trị khóa chỉ mục hiện có. Mục tiêu chính của nó là ngăn một giao dịch khác chèn bản ghi mới vào khoảng trống đó trong thời gian khóa còn hiệu lực.

Giả sử chỉ mục có hai khóa liên tiếp 20 và 30. Gap lock trên `(20, 30)` bảo vệ phần giữa hai khóa:

```text
Index key:       20                         30
                  |--------------------------|
Gap lock:             (20, 30)
                       không cho chèn 25
```

Nếu T1 giữ gap lock trên `(20, 30)`, T2 không thể chèn dòng có khóa chỉ mục 25 cho đến khi khóa được giải phóng hoặc giao dịch kết thúc theo quy tắc của DBMS.

Gap lock không nhất thiết khóa hai bản ghi biên như một cặp khóa dữ liệu thông thường. Nó nhắm vào khoảng trống nơi một khóa mới có thể được chèn. Đây là điểm khác với một khóa record chỉ bảo vệ bản ghi đã tồn tại.

### 4.1. Gap lock trong InnoDB của MySQL

InnoDB sử dụng gap lock trong một số thao tác tìm kiếm và quét chỉ mục, đặc biệt khi cần bảo vệ phạm vi ở mức cô lập `REPEATABLE READ`. Một câu lệnh khóa như `SELECT ... FOR UPDATE` có thể đặt khóa trên các bản ghi chỉ mục và khoảng liên quan đến range scan.

Ví dụ:

```sql
-- Giả sử đang dùng InnoDB và REPEATABLE READ.
START TRANSACTION;

SELECT *
FROM employee
WHERE salary > 20
  AND salary < 30
FOR UPDATE;

-- T1 tiếp tục xử lý; transaction khác có thể bị chặn
-- khi chèn khóa chỉ mục nằm trong khoảng được bảo vệ.
COMMIT;
```

Hành vi chính xác phụ thuộc chỉ mục được dùng, ranh giới truy vấn và isolation level. Đặc biệt, không nên suy ra mọi câu `SELECT` đều tạo gap lock. Một consistent read thông thường của InnoDB thường dùng MVCC để đọc snapshot và không đặt các khóa gap như một locking read.

Ở `READ COMMITTED`, InnoDB thường tắt gap locking cho các thao tác tìm kiếm/quét thông thường, ngoại trừ một số trường hợp cần bảo vệ kiểm tra khóa ngoại và kiểm tra khóa trùng. Vì vậy, cùng một câu lệnh có thể có hành vi chặn insert khác nhau khi thay đổi isolation level.

### 4.2. Gap lock và insert intention lock

InnoDB còn có **insert intention lock**. Đây là tín hiệu khóa cho biết một transaction đang chuẩn bị chèn vào một vị trí trong gap. Nó hỗ trợ phối hợp nhiều thao tác chèn vào cùng khoảng; các insert ở những vị trí khác nhau trong cùng gap có thể không cần chặn lẫn nhau, miễn là không bị một gap/next-key lock xung đột.

Insert intention lock không phải gap lock theo nghĩa bảo vệ khoảng trống lâu dài. Nó là một loại khóa phục vụ ý định chèn và kiểm tra xung đột với khóa đang bảo vệ khoảng.

## 5. Next-key lock — khóa bản ghi và khoảng trống đứng trước

**Next-key lock** là cơ chế đặc trưng của InnoDB. Nó kết hợp:

1. Record lock trên một bản ghi chỉ mục.
2. Gap lock trên khoảng trống ngay trước bản ghi đó trong thứ tự chỉ mục.

Nếu hai khóa chỉ mục liên tiếp là 20 và 30, next-key lock gắn với khóa 30 có thể được hiểu là bảo vệ khoảng `(20, 30]`: khoảng trống từ sau 20 đến trước 30, đồng thời cả record có khóa 30.

```text
Index:       20                         30                         40
             |--------------------------|--------------------------|
Next-key:        (20, 30]                  (30, 40]
                 gap + record 30          gap + record 40
```

Vì khóa bao gồm cả record và gap đứng trước, next-key lock có thể vừa ngăn thay đổi/xóa bản ghi đã tồn tại, vừa ngăn chèn khóa mới vào khoảng trước nó. Đây là cách InnoDB bảo vệ các range scan khỏi phantom trong những trường hợp cần locking.

### 5.1. Ví dụ với dãy khóa

Giả sử chỉ mục có các giá trị `10`, `20`, `30`. Một next-key lock gắn với record 20 bảo vệ khoảng `(10, 20]`:

- T2 không thể chèn giá trị 15 vào gap `(10, 20)` khi gap lock còn hiệu lực.
- T2 cũng không thể cập nhật/xóa record 20 theo cách xung đột với record lock.
- Record 10 không nằm trong next-key lock `(10, 20]` này; nó thuộc phạm vi next-key khác nếu được khóa.

InnoDB còn dùng một pseudo-record `supremum` để biểu diễn vị trí sau khóa lớn nhất của một index page/range. Do đó, range scan ở cuối chỉ mục cũng có thể khóa khoảng phía trên giá trị lớn nhất. Footprint chính xác cần xem index scan và thông tin lock thực tế.

### 5.2. Quan hệ giữa gap lock và next-key lock

| Cơ chế | Phần được bảo vệ | Tác động điển hình |
|---|---|---|
| Record lock | Một bản ghi chỉ mục hiện có | Ngăn thao tác xung đột trên bản ghi đó |
| Gap lock | Khoảng trống giữa các khóa chỉ mục | Ngăn chèn khóa mới vào gap |
| Next-key lock | Record hiện tại và gap đứng ngay trước record | Bảo vệ cả bản ghi lẫn vùng chèn ngay trước nó |

Có thể xem next-key lock là tổ hợp record lock + gap lock trong mô hình InnoDB. Một gap lock thuần không tự động có nghĩa bản ghi ở hai đầu khoảng cũng bị khóa theo cùng cách.

## 6. Predicate lock — khóa một điều kiện logic

**Predicate lock (khóa vị từ/điều kiện)** mô tả phạm vi logic mà một truy vấn đã đọc. Thay vì chỉ nói “khóa dòng số 10” hoặc “khóa khoảng chỉ mục `(20, 30)`”, nó thể hiện rằng giao dịch phụ thuộc vào điều kiện như:

```sql
WHERE salary >= 80 AND salary < 100
```

Mục tiêu là phát hiện hoặc ngăn các thao tác làm thay đổi tập kết quả của predicate, bao gồm cả việc chèn một dòng mới thỏa điều kiện. Vì vậy, predicate lock có thể bảo vệ cả những dòng chưa tồn tại tại thời điểm truy vấn.

Predicate lock là cách nhìn ở mức logic. Một DBMS có thể triển khai mục tiêu này bằng khóa khoảng trên chỉ mục; DBMS khác có thể theo dõi xung đột đọc-ghi bằng metadata mà không chặn writer ngay tại thời điểm ghi.

### 6.1. Predicate lock và Serializable Snapshot Isolation trong PostgreSQL

PostgreSQL dùng Serializable Snapshot Isolation (SSI) để cung cấp mức cô lập `SERIALIZABLE` trên nền MVCC. Hệ thống theo dõi các phụ thuộc đọc-ghi có thể làm lịch giao dịch không tuần tự hóa được. Các dấu hiệu theo dõi này thường được gọi là predicate lock hoặc `SIReadLock`.

Điểm quan trọng: predicate lock `SIREAD` của PostgreSQL **không hoạt động như khóa chặn thông thường**. Một giao dịch ghi có thể tiếp tục thay đổi dữ liệu; PostgreSQL ghi nhận quan hệ phụ thuộc và có thể hủy một giao dịch bằng lỗi serialization nếu phát hiện cấu trúc xung đột nguy hiểm.

Ví dụ:

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT employee_id, salary
FROM employee
WHERE salary >= 80
  AND salary < 100;

-- Một transaction khác có thể INSERT một dòng thỏa predicate.
-- PostgreSQL theo dõi xung đột đọc-ghi và có thể hủy một
-- transaction nếu lịch không còn bảo đảm serializable.

COMMIT;
```

Ứng dụng phải sẵn sàng xử lý lỗi serialization và retry toàn bộ transaction khi phù hợp. Không nên kỳ vọng T2 luôn bị chặn ngay tại câu `INSERT` chỉ vì T1 đang giữ predicate lock. Hành vi này khác với một gap/next-key lock có mục tiêu chặn insert trong khoảng.

PostgreSQL có thể đặt SIREAD ở mức tuple, page hoặc relation tùy kế hoạch truy vấn và cách quản lý predicate lock. Phạm vi theo dõi có thể được nâng lên mức thô hơn để kiểm soát chi phí bộ nhớ; phạm vi thô hơn có thể làm tăng số xung đột được phát hiện và số lần abort.

### 6.2. Predicate lock không nhất thiết là một khóa vật lý trên mọi giá trị

Predicate là điều kiện logic, có thể mô tả một tập rất lớn hoặc vô hạn các giá trị có thể xuất hiện. Một DBMS không nhất thiết tạo một mục khóa riêng cho từng giá trị trong tập đó. Nó có thể dùng chỉ mục, khoảng, trang, bảng hoặc cấu trúc theo dõi phụ thuộc để đại diện cho điều kiện.

Do đó, khi đọc tài liệu một DBMS, cần xác định “predicate lock” đang nói đến:

- Khóa chặn thật sự trên khoảng hoặc đối tượng tương ứng.
- Metadata ghi nhận giao dịch đã đọc một predicate để phát hiện phụ thuộc.
- Một cơ chế tổng quát trong lý thuyết tuần tự hóa, chưa gắn với cách triển khai cụ thể.

## 7. So sánh bốn khái niệm theo mục tiêu

| Khái niệm | Đối tượng được bảo vệ | Mục tiêu chính | Cách xử lý insert có thể thỏa điều kiện |
|---|---|---|---|
| Range/key-range lock | Một khoảng khóa trong chỉ mục | Bảo vệ phạm vi khóa và ngăn phantom bằng cách điều phối thao tác trong khoảng | Thường bị chặn nếu yêu cầu insert xung đột với khóa khoảng |
| Gap lock | Khoảng trống giữa các khóa chỉ mục | Ngăn tạo khóa mới trong gap | Insert vào gap phải chờ hoặc thất bại theo cơ chế khóa |
| Next-key lock | Một record chỉ mục cộng gap ngay trước record | Kết hợp bảo vệ record hiện có và khoảng có thể chèn trước nó | Insert vào gap bị chặn; thao tác xung đột trên record cũng bị chặn |
| Predicate lock | Điều kiện logic của truy vấn | Bảo vệ tính đúng đắn của predicate/serializability, kể cả dòng chưa tồn tại | Có thể bị chặn hoặc chỉ được ghi nhận là phụ thuộc; tùy cách triển khai |

Một số khác biệt quan trọng:

- Range lock và gap lock đều nói về khoảng, nhưng “range lock” là cách gọi rộng và có thể bao gồm cả khóa trên các key trong phạm vi; “gap lock” nhấn mạnh khoảng trống giữa các key.
- Next-key lock là tổ hợp cụ thể của InnoDB, gồm record và gap đứng trước record.
- Predicate lock nói về điều kiện logic. Một hệ thống có thể dùng range lock để hiện thực predicate protection, nhưng predicate lock trong PostgreSQL SSI là cơ chế theo dõi phụ thuộc không chặn writer theo cách của gap lock.
- Cả bốn khái niệm đều liên quan đến phantom hoặc tuần tự hóa, nhưng không có nghĩa chúng có cùng mode, cùng thời gian giữ hay cùng hành vi chờ.

## 8. Cùng một truy vấn, các DBMS có thể bảo vệ khác nhau

Giả sử T1 đọc các nhân viên có `salary` trong khoảng `[80, 100)` và T2 muốn chèn `salary = 90`.

### 8.1. SQL Server: key-range lock

Ở `SERIALIZABLE`, SQL Server có thể lấy key-range lock trên khoảng của chỉ mục đáp ứng predicate. T2 có thể phải chờ khi chèn một key nằm trong phạm vi được bảo vệ.

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;

SELECT employee_id, salary
FROM dbo.Employee
WHERE salary >= 80 AND salary < 100;

-- Giữ transaction mở để quan sát phạm vi khóa.
COMMIT;
```

Nếu cần dùng hint `HOLDLOCK`, hãy hiểu rằng hint này yêu cầu ngữ nghĩa tương đương `SERIALIZABLE` cho tham chiếu bảng tương ứng. Khóa thực tế phụ thuộc index và execution plan.

### 8.2. MySQL InnoDB: gap/next-key lock

Ở các trường hợp locking range scan trong `REPEATABLE READ`, InnoDB có thể đặt next-key locks trên các entry của index và các gap liên quan. T2 chèn khóa nằm trong gap bị bảo vệ có thể phải chờ.

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT employee_id, salary
FROM employee
WHERE salary >= 80 AND salary < 100
FOR UPDATE;

-- T1 giữ khóa cho đến COMMIT hoặc ROLLBACK.
COMMIT;
```

Hãy nhớ rằng locking read và consistent read thông thường có hành vi khác nhau. `FOR UPDATE` yêu cầu khóa; `SELECT` thông thường trong InnoDB thường đọc snapshot bằng MVCC. `READ COMMITTED` cũng thay đổi việc sử dụng gap lock trong phần lớn tìm kiếm/quét thông thường.

### 8.3. PostgreSQL: predicate tracking trong SSI

Ở `SERIALIZABLE`, PostgreSQL theo dõi predicate read bằng SIREAD lock và kiểm tra phụ thuộc đọc-ghi. T2 có thể thực hiện insert; nếu giao dịch đồng thời tạo ra cấu trúc không tuần tự hóa được, một transaction có thể bị hủy với lỗi serialization.

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT employee_id, salary
FROM employee
WHERE salary >= 80 AND salary < 100;

-- COMMIT có thể thất bại với serialization failure
-- nếu các giao dịch đồng thời tạo ra xung đột nguy hiểm.
COMMIT;
```

Đây là khác biệt thực tế quan trọng: SQL Server key-range lock và InnoDB gap/next-key lock thường điều phối insert bằng cách chặn; PostgreSQL SSI có thể để writer tiếp tục rồi phát hiện xung đột và abort transaction. Cả hai hướng đều nhằm bảo đảm ngữ nghĩa cô lập cần thiết, nhưng trải nghiệm ứng dụng khi có cạnh tranh khác nhau.

## 9. Mức cô lập quyết định khi nào cần bảo vệ khoảng

Phạm vi và thời điểm khóa phụ thuộc isolation level và loại câu lệnh.

| Mức cô lập / cách đọc | Mục tiêu hoặc hành vi thường gặp |
|---|---|
| Read Committed | Mỗi câu lệnh có thể thấy snapshot mới; phantom có thể xuất hiện giữa hai câu lệnh |
| Repeatable Read dựa trên MVCC | Có thể giữ snapshot ổn định nhưng khả năng bảo vệ phantom/anomaly phụ thuộc DBMS |
| Serializable dùng range locking | Bảo vệ khoảng để insert/update không phá vỡ predicate đã đọc |
| Serializable dùng SSI | Theo dõi phụ thuộc và hủy giao dịch nếu lịch có nguy cơ không tuần tự hóa |

Không thể suy ra chỉ từ tên `REPEATABLE READ` rằng mọi DBMS đều dùng next-key lock hoặc mọi phantom đều bị chặn. Ví dụ, InnoDB và PostgreSQL có các cơ chế khác nhau dù cùng hỗ trợ tên mức cô lập này.

## 10. Chỉ mục và kế hoạch truy vấn ảnh hưởng đến footprint khóa

Range/gap/next-key lock thường dựa vào chỉ mục để xác định khoảng. Hãy xem truy vấn:

```sql
SELECT *
FROM orders
WHERE tenant_id = 7
  AND order_no >= 1000
  AND order_no < 2000;
```

Nếu có chỉ mục ghép `(tenant_id, order_no)`, DBMS có thể tìm phạm vi liên tục bắt đầu bằng `tenant_id = 7` rồi giới hạn `order_no`. Nếu chỉ có chỉ mục trên `order_no`, phạm vi khóa và số dòng phải quét có thể khác. Nếu không có chỉ mục phù hợp, hệ quản trị có thể quét nhiều dữ liệu và khóa phạm vi lớn hơn dự kiến.

Một số điểm cần xem:

- Thứ tự cột trong chỉ mục ghép có khớp với điều kiện lọc không?
- Điều kiện có tạo thành một khoảng liên tục trong thứ tự index không?
- Có phép chuyển đổi kiểu dữ liệu, hàm hoặc collation làm thay đổi khả năng dùng index không?
- Execution plan có dùng index seek/range scan hay table scan?
- DBMS khóa khóa chỉ mục phụ, khóa bản ghi clustered/heap hay cả hai?
- Phạm vi khóa có bị nâng cấp hoặc mở rộng khi quét quá nhiều entry không?

Predicate lock cũng chịu ảnh hưởng của execution plan trong cách biểu diễn vật lý. Ví dụ, PostgreSQL có thể theo dõi ở cấp tuple, page hoặc relation. Khi phạm vi theo dõi thô hơn, hệ thống có thể phát hiện thêm xung đột bảo thủ, dù các giao dịch thực tế thao tác trên những phần dữ liệu khác nhau.

## 11. Tác động đến hiệu năng và deadlock

Các khóa bảo vệ khoảng giúp ngăn phantom nhưng có thể làm giảm khả năng đồng thời. Một gap lock trên khoảng rộng có thể chặn nhiều thao tác insert dù các dòng đó không tồn tại khi truy vấn bắt đầu. Next-key lock còn bảo vệ record liên quan nên có thể chặn cả update/delete xung đột.

Các tác động thường gặp:

- **Lock wait:** transaction chèn hoặc cập nhật key trong khoảng phải chờ transaction đang giữ khóa.
- **Deadlock:** hai transaction giữ các range khác nhau rồi yêu cầu range/record của nhau theo thứ tự đối nghịch.
- **Abort do serialization:** với SSI không chặn, nhiều giao dịch có thể cùng chạy nhưng một giao dịch bị hủy khi hệ thống phát hiện cấu trúc phụ thuộc nguy hiểm.
- **Giảm throughput:** phạm vi khóa càng rộng, càng nhiều thao tác độc lập có thể bị ảnh hưởng.
- **Tăng chi phí theo dõi:** predicate/range tracking cần metadata, kiểm tra xung đột và dọn dẹp thông tin khi transaction kết thúc.

Một số cách giảm tranh chấp:

1. Tạo chỉ mục phù hợp để DBMS xác định phạm vi hẹp.
2. Giữ transaction ngắn, tránh gọi dịch vụ ngoài hoặc chờ người dùng khi đang giữ range lock.
3. Truy cập nhiều phạm vi theo thứ tự nhất quán để giảm deadlock.
4. Dùng isolation level đáp ứng đúng quy tắc nghiệp vụ; không nâng lên `SERIALIZABLE` một cách tùy tiện cho mọi truy vấn.
5. Xử lý retry cho serialization failure và deadlock với giới hạn cùng backoff.
6. Đo lock wait, deadlock, serialization abort và thời gian transaction trên workload thực tế.

Không nên giảm isolation level chỉ để loại bỏ lock wait nếu việc đó làm mất bảo vệ phantom mà quy tắc nghiệp vụ cần. Hãy xác định trước bất biến dữ liệu nào phải được giữ.

## 12. Những nhầm lẫn thường gặp

**Gap lock và next-key lock là một.** Không chính xác. Gap lock bảo vệ khoảng trống; next-key lock của InnoDB kết hợp gap đứng trước một index record với record đó.

**Range lock chỉ khóa những dòng đã có trong kết quả.** Không đúng. Mục tiêu của range lock là bảo vệ phạm vi khóa, bao gồm vị trí mà dòng mới có thể được chèn vào để thỏa predicate.

**Predicate lock luôn chặn câu lệnh INSERT.** Không đúng. Cách triển khai phụ thuộc DBMS. SIREAD predicate lock của PostgreSQL phục vụ theo dõi phụ thuộc và không chặn writer như gap lock truyền thống.

**Mọi SELECT đều đặt gap lock.** Không đúng. Trong InnoDB, consistent read thông thường dùng MVCC; locking read và các thao tác ghi mới có thể đặt record/gap/next-key lock tùy isolation level và kế hoạch truy vấn.

**REPEATABLE READ có cùng hành vi ở mọi hệ quản trị.** Không đúng. Cơ chế bảo vệ phantom và anomaly khác nhau theo DBMS. Hãy kiểm tra tài liệu cụ thể.

**Có index là chắc chắn khóa chỉ đúng phạm vi predicate.** Không đúng. Phạm vi thực tế còn phụ thuộc cấu trúc index, điều kiện truy vấn, kế hoạch thực thi và cách DBMS đặt khóa.

**Predicate lock chỉ là một cách gọi khác của next-key lock.** Không đúng. Predicate lock biểu diễn điều kiện logic; next-key lock là một cơ chế vật lý cụ thể của InnoDB.

## 13. Cách chẩn đoán một truy vấn bị chặn hoặc bị abort

Khi một giao dịch không thể insert/update hoặc bị serialization failure, hãy xác định loại cơ chế đang bảo vệ phạm vi:

1. Xác định DBMS, phiên bản và isolation level của từng transaction.
2. Xem truy vấn có dùng locking read, `SERIALIZABLE`, `HOLDLOCK` hoặc hint tương tự không.
3. Đọc execution plan để xác định chỉ mục và khoảng khóa được quét.
4. Kiểm tra khóa đang giữ là record, gap, next-key, key-range hay predicate/SIREAD.
5. Xác định giao dịch nào đang giữ khóa, giao dịch nào đang yêu cầu insert/update, và resource/index key liên quan.
6. Với PostgreSQL SSI, kiểm tra serialization failure và các giao dịch có phụ thuộc đọc-ghi; đừng chỉ tìm một lock wait vì writer có thể không bị chặn.
7. Với InnoDB, kiểm tra lock wait/deadlock report để phân biệt record lock, gap lock và next-key lock.
8. Với SQL Server, kiểm tra loại key-range lock và index key mà lock manager đang bảo vệ.
9. Xem xét transaction có giữ khóa lâu, quét phạm vi quá rộng hoặc truy cập index theo thứ tự khác nhau không.
10. Chỉ thay đổi isolation/index/locking hint sau khi xác định rõ bất biến cần bảo vệ và tác động tới các transaction khác.

## 14. Kết luận về mục tiêu của từng cơ chế

Khi phân tích khóa khoảng, hãy bắt đầu bằng câu hỏi “DBMS đang bảo vệ cái gì?”:

- Nếu bảo vệ một khoảng trong thứ tự khóa chỉ mục, hãy nghĩ đến **range/key-range lock**.
- Nếu chỉ bảo vệ khoảng trống nơi một key mới có thể được chèn, đó là **gap lock**.
- Nếu bảo vệ cả một index record và gap đứng ngay trước nó theo cơ chế InnoDB, đó là **next-key lock**.
- Nếu bảo vệ một điều kiện logic mà truy vấn đã đọc, bao gồm cả những dòng có thể xuất hiện sau đó, đó là **predicate protection**; cách triển khai có thể là khóa chặn hoặc theo dõi phụ thuộc.

Các cơ chế này cùng giải quyết bài toán phantom và tính đúng đắn của truy vấn theo phạm vi, nhưng khác nhau ở đối tượng được bảo vệ, thời điểm phát hiện xung đột và cách xử lý giao dịch cạnh tranh. Hiểu sự khác biệt giúp đọc lock report chính xác, thiết kế chỉ mục phù hợp và chọn mức cô lập đúng với yêu cầu nghiệp vụ.
