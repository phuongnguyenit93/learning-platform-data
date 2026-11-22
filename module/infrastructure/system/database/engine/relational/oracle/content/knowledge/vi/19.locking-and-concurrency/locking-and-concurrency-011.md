# ORA-01555 và quan hệ giữa thời gian truy vấn với undo trong Oracle Database

`ORA-01555: snapshot too old` là lỗi xảy ra khi Oracle không còn thông tin undo cần thiết để dựng lại phiên bản dữ liệu tại thời điểm snapshot của một truy vấn. Lỗi thường xuất hiện ở truy vấn chạy lâu trong khi các session khác liên tục thay đổi dữ liệu, nhưng thời lượng truy vấn không phải yếu tố duy nhất. Khối lượng undo được tạo ra, kích thước undo tablespace, chính sách retention và cách ứng dụng quản lý transaction đều ảnh hưởng đến khả năng giữ lại phiên bản cũ.

Để hiểu và xử lý lỗi này, cần nắm mối liên hệ giữa ba yếu tố:

- **Thời gian truy vấn:** truy vấn càng lâu thì càng có nhiều thời gian để các phiên bản dữ liệu mà nó cần bị thay đổi và undo cũ bị tái sử dụng.
- **Undo generation:** workload INSERT/UPDATE/DELETE càng lớn thì undo được tạo ra càng nhanh, khiến vùng undo phải luân chuyển nhanh hơn.
- **Undo retention và dung lượng:** Oracle cần giữ undo đủ lâu và có đủ không gian để truy vấn dựng lại dữ liệu tại snapshot ban đầu.

Một truy vấn chạy 30 phút không tự động gặp ORA-01555. Nếu dữ liệu ít thay đổi và undo cần thiết vẫn còn, truy vấn có thể hoàn tất. Ngược lại, truy vấn ngắn vẫn có thể gặp lỗi nếu undo cần thiết bị tái sử dụng quá sớm hoặc có áp lực undo rất lớn.

Bài học giải thích snapshot và consistent read, cách undo được dùng trong quá trình truy vấn, quan hệ giữa query duration và undo retention, các nguyên nhân thường gặp, cách quan sát bằng `V$UNDOSTAT`, hướng sizing undo tablespace, ảnh hưởng của COMMIT trong cursor loop và quy trình điều tra ORA-01555.

## 1. ORA-01555 là gì?

### 1.1. Ý nghĩa của lỗi

Thông báo Oracle:

```text
ORA-01555: snapshot too old: rollback segment number ... with name ...
too small
```

Thông tin chi tiết có thể thay đổi theo phiên bản và ngữ cảnh. Ý nghĩa cốt lõi là Oracle cần một phiên bản cũ của block để đáp ứng snapshot nhất quán, nhưng undo record cần thiết đã không còn khả dụng.

Ví dụ:
1. Truy vấn A bắt đầu tại snapshot SCN 100.
2. Truy vấn A cần đọc một hàng có giá trị tại SCN 100.
3. Transaction B thay đổi hàng đó và commit sau SCN 100.
4. Oracle cần undo của B để dựng lại giá trị cũ cho A.
5. Nếu undo đó bị ghi đè trước khi A đọc block, Oracle không thể dựng lại phiên bản tại SCN 100.
6. A có thể nhận ORA-01555.

### 1.2. Đây là lỗi về khả năng dựng lại snapshot

ORA-01555 không có nghĩa:
- Bảng bị hỏng.
- Truy vấn viết sai cú pháp.
- Transaction đọc đã đọc dữ liệu chưa commit.
- Một session đang giữ row lock khiến truy vấn phải chờ.
- Undo tablespace nhất thiết đã đầy.

Lỗi nói rằng thông tin undo cần thiết cho consistent read không còn sẵn có. Nguyên nhân gốc có thể là thời lượng query, undo generation cao, dung lượng undo nhỏ, retention không đạt mục tiêu hoặc cách sử dụng cursor/transaction chưa phù hợp.

### 1.3. Tại sao Oracle cần undo khi SELECT?

Một SELECT thông thường phải trả về dữ liệu như đã tồn tại tại snapshot của statement. Trong lúc truy vấn chạy, các session khác có thể UPDATE hoặc DELETE những block mà truy vấn chưa đọc tới.

Oracle dùng undo để tái tạo phiên bản phù hợp với snapshot ban đầu. Nhờ đó, một câu SELECT dài có thể đọc dữ liệu nhất quán dù writer vẫn đang commit thay đổi.

Nếu undo cần thiết bị tái sử dụng trước khi truy vấn đọc tới block tương ứng, việc dựng lại snapshot thất bại và có thể phát sinh ORA-01555.

## 2. Snapshot, SCN và consistent read

### 2.1. Snapshot của một câu SELECT

Trong READ COMMITTED mặc định, mỗi câu SQL có một snapshot logic tại thời điểm statement bắt đầu. Có thể hình dung:

```text
Thời gian ----------------------------------------------------->

SCN 100            SCN 110              SCN 120
  |                   |                    |
  |                   |                    +-- Transaction B COMMIT
  |                   +----------------------- Query A bắt đầu
  +-------------------------------------------- Phiên bản cũ

Query A đọc snapshot tại SCN 110:
- Thấy các thay đổi đã commit trước snapshot.
- Không thấy các thay đổi commit sau snapshot.
- Dùng undo để dựng lại phiên bản cũ khi block đã thay đổi.
```

SCN (*System Change Number*) là số thứ tự logic Oracle dùng để xác định thứ tự thay đổi và snapshot. SCN không đơn giản là thời gian đồng hồ theo giây.

### 2.2. Một truy vấn dài vẫn giữ snapshot ban đầu

Giả sử truy vấn A mất 20 phút để quét bảng. Nó bắt đầu tại SCN 110. Trong 20 phút đó, nhiều transaction khác cập nhật và commit dữ liệu.

Truy vấn A vẫn cần nhìn thấy phiên bản phù hợp với SCN 110. Nó không tự chuyển sang snapshot mới ở giữa statement chỉ vì transaction khác commit.

Đây là điều giúp kết quả SELECT nhất quán, nhưng cũng tạo yêu cầu về việc duy trì undo trong khoảng thời gian truy vấn còn cần đọc phiên bản cũ.

### 2.3. Undo giúp dựng lại phiên bản trước

Ví dụ hàng có giá trị:

```text
Trước UPDATE và đã commit:
    BALANCE = 5.000

Session B UPDATE và chưa COMMIT:
    BALANCE = 4.000

Session B COMMIT:
    BALANCE = 4.000

Query A có snapshot trước UPDATE:
    Oracle cần phiên bản BALANCE = 5.000
    -> dùng undo để dựng lại giá trị cũ
```

Sau COMMIT, undo không bị xóa ngay. Nó có thể vẫn cần cho các query có snapshot cũ và các tính năng Flashback. Nhưng undo space có giới hạn và Oracle có thể tái sử dụng các extent theo chính sách quản lý undo.

### 2.4. Query không cần undo cho mọi block

Nếu một block không bị thay đổi sau snapshot mà query đang dùng, Oracle có thể đọc block hiện tại mà không cần dựng lại phiên bản cũ từ undo. Undo chỉ cần thiết khi block chứa thay đổi không phù hợp với snapshot và Oracle phải quay ngược trạng thái logic để đọc.

Do đó, query dài nhưng đọc dữ liệu gần như không thay đổi có thể không gặp ORA-01555. Query ngắn trên dữ liệu bị thay đổi dày đặc có thể có rủi ro cao hơn dự đoán.

## 3. Quan hệ giữa thời gian truy vấn và undo

### 3.1. Thời lượng query quyết định khoảng thời gian cần giữ phiên bản

Một query bắt đầu ở thời điểm T0. Nếu query vẫn đang chạy ở T1, nó có thể cần đọc những block lần đầu được truy cập ở T1 nhưng phải nhìn thấy phiên bản tại T0.

Những transaction commit trong khoảng T0 đến T1 có thể tạo undo cần thiết để dựng lại phiên bản T0. Undo đó phải còn khả dụng cho đến khi query đọc xong block tương ứng.

Vì vậy, truy vấn càng dài thì khoảng thời gian undo cũ cần được giữ có thể càng dài.

### 3.2. Undo generation quyết định tốc độ tiêu thụ không gian

Undo generation là tốc độ database tạo undo do các transaction thay đổi dữ liệu. Workload UPDATE/DELETE/INSERT lớn thường tạo undo nhanh hơn workload chủ yếu đọc.

Ví dụ:
- Hệ thống báo cáo đọc bảng ít thay đổi: undo cần cho snapshot có thể được giữ lâu.
- Hệ thống OLTP có nhiều UPDATE trên hàng triệu bản ghi: undo có thể được tạo và tái sử dụng rất nhanh.
- Batch cập nhật một bảng lớn trong khi báo cáo quét bảng đó: hai workload có thể cạnh tranh trực tiếp về thời gian giữ undo.

Cùng một query chạy 15 phút có thể ổn vào giờ ít DML nhưng gặp ORA-01555 vào giờ cao điểm.

### 3.3. Mối quan hệ định tính

Có thể mô hình hóa rủi ro bằng cách so sánh:

```text
Thời gian query cần snapshot cũ
                |
                v
      Undo phải còn khả dụng
                |
                v
      Đối chiếu với retention thực tế
                |
                v
   Undo generation và dung lượng tablespace
```

Nếu truy vấn cần một phiên bản cũ lâu hơn khoảng thời gian Oracle có thể giữ undo cần thiết, rủi ro ORA-01555 tăng.

Không có ngưỡng thời gian duy nhất áp dụng cho mọi hệ thống. Cần xem cả query duration, dữ liệu bị thay đổi, undo rate và khả năng giữ undo.

### 3.4. Query duration không phải nguyên nhân duy nhất

| Trường hợp | Rủi ro |
| --- | --- |
| Query lâu, ít DML, undo tablespace đủ lớn | Có thể vẫn chạy thành công |
| Query lâu, DML liên tục, undo tablespace nhỏ | Rủi ro cao hơn |
| Query ngắn, một vùng dữ liệu bị cập nhật cực nhanh | Vẫn có thể gặp lỗi |
| Query ngắn, dữ liệu gần như không thay đổi | Thường ít rủi ro |
| Query cần snapshot cũ hơn retention thực tế | Có thể không dựng lại được phiên bản |

Không kết luận chỉ từ con số thời gian chạy. Cần ghép thông tin truy vấn với thống kê undo tại đúng khoảng thời gian lỗi.

## 4. UNDO_RETENTION và khả năng giữ undo

### 4.1. UNDO_RETENTION là gì?

`UNDO_RETENTION` là tham số tính bằng giây, đặt mục tiêu thời gian Oracle giữ lại undo trong Automatic Undo Management.

Ví dụ:

```sql
ALTER SYSTEM SET undo_retention = 1800;
```

Giá trị 1800 tương ứng 30 phút. Đây là ví dụ cấu hình cần quyền DBA; không chạy tùy tiện trên production.

`UNDO_RETENTION` không đơn giản là bộ hẹn giờ đảm bảo mọi undo luôn được giữ đủ đúng số giây trong mọi tình huống. Khả năng giữ undo còn phụ thuộc dung lượng tablespace, chế độ autoextend, workload và RETENTION GUARANTEE.

### 4.2. Undo retention target và retention thực tế

Cần phân biệt:

- **UNDO_RETENTION:** mục tiêu được cấu hình.
- **TUNED_UNDORETENTION:** giá trị retention Oracle điều chỉnh dựa trên workload và dung lượng theo thông tin trong V$UNDOSTAT.
- **Retention thực tế của undo cần thiết:** phụ thuộc extent có còn được giữ và chưa bị tái sử dụng tại thời điểm query cần dùng hay không.

Một cấu hình UNDO_RETENTION cao không tự tạo thêm dung lượng. Nếu undo tablespace nhỏ và workload tạo undo nhanh, retention thực tế có thể thấp hơn mong đợi.

### 4.3. Khi không có RETENTION GUARANTEE

Với undo tablespace ở chế độ NOGUARANTEE (mặc định phổ biến), Oracle ưu tiên duy trì hoạt động DML. Khi thiếu không gian, hệ thống có thể tái sử dụng undo chưa hết thời gian retention nếu cần.

Điều này giúp DML tiếp tục nhưng có thể làm một query dài mất undo cần thiết và gặp ORA-01555.

### 4.4. Khi bật RETENTION GUARANTEE

RETENTION GUARANTEE yêu cầu Oracle không ghi đè undo chưa hết thời gian retention chỉ vì thiếu chỗ. Điều này giúp bảo vệ undo cho query/Flashback theo retention đã đặt.

Đổi lại, nếu không còn undo space có thể sử dụng và không thể cấp thêm extent, DML mới có thể thất bại, ví dụ với lỗi:

```text
ORA-30036: unable to extend segment by ... in undo tablespace ...
```

Vì vậy, RETENTION GUARANTEE là lựa chọn vận hành có đánh đổi. Cần sizing undo tablespace, theo dõi dung lượng, cấu hình autoextend và dự báo workload trước khi bật.

### 4.5. Undo tablespace autoextend và fixed size

Trong Automatic Undo Management:
- Undo tablespace có AUTOEXTEND có thể tăng dung lượng trong giới hạn MAXSIZE để đáp ứng nhu cầu giữ undo.
- Undo tablespace fixed size phải làm việc trong dung lượng đã cấp phát; Oracle điều chỉnh retention theo không gian thực tế có thể giữ.
- Dù autoextend, giới hạn MAXSIZE hoặc filesystem/storage vẫn có thể ngăn tablespace mở rộng.
- Không có đủ không gian thì retention mục tiêu có thể không đạt được nếu không dùng guarantee.

Kiểm tra cấu hình file:

```sql
SELECT tablespace_name,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM   dba_data_files
WHERE  tablespace_name = (
    SELECT value
    FROM   v$parameter
    WHERE  name = 'undo_tablespace'
);
```

Cần quyền DBA hoặc quyền đọc các dictionary/dynamic performance views tương ứng.

## 5. Ước lượng dung lượng undo cần thiết

### 5.1. Nguyên tắc ước lượng

Một ước lượng ban đầu thường dựa trên:

\[
\text{Undo space} \approx
\text{Undo generation rate}
\times
\text{Desired retention}
\]

Trong đó:
- Undo generation rate là lượng undo tạo ra trong một giây.
- Desired retention là thời gian cần giữ undo, tính bằng giây.
- Kết quả cần cộng thêm phần dự phòng cho transaction đang hoạt động, biến động workload, overhead và các nhu cầu khác.

Nếu dùng số block undo mỗi giây:

\[
\text{Undo bytes} \approx
\text{Undo blocks/second}
\times
\text{DB block size}
\times
\text{Retention seconds}
\]

Đây là mô hình ước lượng phục vụ capacity planning, không phải công thức cấp phát chính xác cho mọi database. Dùng dữ liệu thực tế từ workload và công cụ sizing phù hợp.

### 5.2. Ví dụ tính đơn giản

Giả sử:
- Undo generation trung bình trong giờ cao điểm: 2 MB/giây.
- Query báo cáo dài nhất cần snapshot: 1.800 giây (30 phút).
- Muốn dự phòng thêm 25% cho biến động workload.

Ước lượng cơ bản:

\[
2 \text{ MB/s} \times 1800 \text{ s} = 3600 \text{ MB}
\]

Cộng dự phòng:

\[
3600 \times 1.25 = 4500 \text{ MB}
\]

Mức ước lượng khoảng 4,5 GB. DBA còn phải xét active undo, peak rate, các transaction dài, workload khác, mức tăng trưởng và storage thực tế.

### 5.3. Dùng giờ cao điểm, không chỉ dùng trung bình ngày

Nếu hệ thống có batch lúc 1 giờ sáng và ít DML ban ngày, average cả ngày có thể thấp hơn nhiều so với undo generation ở thời điểm batch chạy. Dùng peak hoặc percentile phù hợp với yêu cầu vận hành để tránh sizing quá thấp.

Cần xem:
- Thời điểm query báo cáo bắt đầu.
- Thời điểm batch DML bắt đầu.
- Undo generation trong từng khoảng.
- Query duration thực tế và biến động theo ngày.
- Dung lượng undo có thể mở rộng tối đa.

### 5.4. Dung lượng lớn không thay thế mọi biện pháp khác

Tăng undo tablespace có thể tăng thời gian giữ undo và giảm nguy cơ tái sử dụng sớm, nhưng:
- Query vẫn có thể chạy quá lâu.
- DML vẫn có thể tạo undo với tốc độ rất cao.
- MAXSIZE hoặc storage có thể đạt giới hạn.
- Transaction dài vẫn giữ active undo.
- Một lỗi do cursor/commit pattern không được sửa chỉ bằng tăng dung lượng.

Hãy kết hợp sizing với tối ưu query, điều chỉnh workload và thiết kế transaction.

## 6. Các nguyên nhân ORA-01555 thường gặp

### 6.1. Query chạy lâu

Query quét bảng lớn, join nhiều bảng, sort hoặc aggregate khối lượng lớn có thể cần snapshot trong thời gian dài. Trong lúc đó, các session khác tiếp tục thay đổi dữ liệu và tạo undo.

Cần xem execution plan, predicate, index, partition pruning, thống kê và khối lượng dữ liệu thực tế. Giảm thời gian query thường giúp giảm khoảng thời gian undo phải được giữ.

### 6.2. Undo tablespace không đủ lớn

Nếu dung lượng undo nhỏ so với lượng undo được tạo trong workload, các extent cũ có thể bị tái sử dụng nhanh. Query dài dễ mất phiên bản cần thiết hơn.

Cần kiểm tra:
- Dung lượng đã cấp phát.
- AUTOEXTEND và MAXSIZE.
- Dung lượng còn trống.
- Undo generation rate.
- UNDO_RETENTION và TUNED_UNDORETENTION.
- RETENTION GUARANTEE hay NOGUARANTEE.

### 6.3. DML đồng thời quá lớn

Một batch UPDATE/DELETE lớn có thể tạo lượng undo đáng kể. Nếu batch chạy đồng thời với báo cáo dài, nó có thể làm undo cũ bị tái sử dụng nhanh hơn.

Các giải pháp có thể gồm:
- Chạy batch vào thời điểm ít báo cáo.
- Chia workload theo lô hợp lý.
- Tối ưu câu DML.
- Dùng partition exchange hoặc chiến lược tải dữ liệu phù hợp nếu nghiệp vụ cho phép.
- Tăng dung lượng undo sau khi sizing.

Không chia batch một cách máy móc nếu điều đó làm thay đổi tính nguyên tử hoặc kết quả nghiệp vụ.

### 6.4. COMMIT quá thường xuyên trong cursor loop

Một pattern rủi ro là mở cursor đọc dữ liệu, rồi trong vòng lặp vừa cập nhật dữ liệu liên quan vừa COMMIT liên tục:

```sql
-- Minh họa pattern không nên dùng tùy tiện
FOR r IN (
    SELECT employee_id, salary
    FROM employees
) LOOP
    UPDATE employees
    SET salary = salary + 100
    WHERE employee_id = r.employee_id;

    COMMIT;
END LOOP;
```

Cursor có thể vẫn cần đọc dữ liệu theo snapshot ban đầu trong khi các commit lặp lại làm undo cũ có thể được tái sử dụng. Trong một số pattern, đặc biệt khi cursor đọc các block bị chính workload thay đổi, điều này làm tăng nguy cơ ORA-01555.

Không có nghĩa mọi COMMIT trong loop đều chắc chắn gây lỗi. Rủi ro phụ thuộc cursor, dữ liệu, cách fetch, lượng DML và retention. Nhưng commit từng hàng thường làm tăng overhead, phá vỡ transaction nghiệp vụ và có thể gây vấn đề nhất quán.

### 6.5. Transaction dài và undo đang hoạt động

Một transaction chưa commit có thể giữ undo đang active. Transaction lớn kéo dài có thể làm tăng nhu cầu undo và áp lực tablespace. Tuy nhiên, active undo không thể bị tái sử dụng như expired undo; cần phân biệt undo của transaction chưa kết thúc với undo đã commit nhưng còn cần cho consistent read.

Theo dõi transaction dài và kiểm tra ứng dụng có giữ transaction mở trong khi chờ người dùng hoặc dịch vụ ngoài hay không.

### 6.6. Undo generation biến động mạnh

Một hệ thống có thể bình thường trong nhiều giờ nhưng đột ngột tạo undo lớn do:
- Batch import.
- Mass update.
- Xóa dữ liệu theo kỳ.
- Đồng bộ dữ liệu từ hệ thống khác.
- Chạy lại job hoặc migration.

Một snapshot bắt đầu trước đợt biến động có thể gặp rủi ro nếu undo cũ bị tái sử dụng trong lúc query vẫn chạy.

## 7. Ví dụ hai session và thời gian truy vấn

### 7.1. Tình huống

- Session A bắt đầu truy vấn quét bảng lớn tại SCN T0.
- Session B cập nhật nhiều hàng và COMMIT liên tục.
- Session A tiếp tục đọc các block mà B đã thay đổi.
- Oracle cần undo để dựng lại phiên bản T0.
- Nếu undo tương ứng vẫn còn, A tiếp tục.
- Nếu undo đã bị tái sử dụng, A có thể gặp ORA-01555.

Sơ đồ:

```text
Thời gian ---------------------------------------------------------->

Session A:  |---------------- Query snapshot T0 --------------------|
            bắt đầu                                         cần block sau

Session B:       UPDATE + COMMIT  UPDATE + COMMIT  UPDATE + COMMIT
                       |               |                |
                       v               v                v
Undo:             tạo undo mới    tạo undo mới     tạo undo mới
                       |               |                |
                       +------ áp lực tái sử dụng undo cũ ------+

Query A cần undo cũ để dựng phiên bản T0.
Nếu undo đó bị tái sử dụng trước khi cần -> ORA-01555.
```

### 7.2. Không phải cứ B commit là A lỗi

Commit của B không tự động làm query A lỗi. Oracle thường giữ undo cần thiết theo retention và không gian sẵn có. Lỗi chỉ xảy ra khi undo cụ thể mà A cần không còn khả dụng tại thời điểm A cần dựng phiên bản cũ.

### 7.3. Cách thử trong môi trường học tập

Có thể tạo một bảng lớn trong schema test, chạy một SELECT đủ lâu ở session A và chạy batch UPDATE/COMMIT ở session B. Kết quả phụ thuộc tốc độ, kích thước undo, số hàng và storage. Một môi trường nhỏ có thể không tái hiện lỗi dù mô hình lý thuyết đúng.

Không cố tình gây áp lực undo trên production để tạo ORA-01555. Thử nghiệm cần giới hạn tài nguyên và thực hiện ở database riêng.

## 8. Theo dõi undo bằng V$UNDOSTAT

### 8.1. Các cột quan trọng

`V$UNDOSTAT` cung cấp thống kê undo theo các khoảng thời gian. Một số cột thường dùng:

| Cột | Ý nghĩa |
| --- | --- |
| BEGIN_TIME, END_TIME | Khoảng thời gian thống kê |
| UNDOBLKS | Số block undo được sử dụng/phát sinh trong khoảng |
| TXNCOUNT | Số transaction trong khoảng |
| MAXQUERYLEN | Thời lượng query dài nhất quan sát được, tính bằng giây |
| TUNED_UNDORETENTION | Giá trị undo retention được Oracle điều chỉnh |
| SSOLDERRCNT | Số lỗi snapshot too old trong khoảng |
| NOSPACEERRCNT | Số lỗi không gian undo trong khoảng |
| UNXPSTEALCNT | Số lần lấy/steal undo extent chưa hết hạn theo thống kê |

Tên và khả năng truy cập view có thể phụ thuộc phiên bản, kiến trúc CDB/PDB và quyền. DBA cần đối chiếu Data Dictionary Reference của release đang chạy.

### 8.2. Truy vấn thống kê gần đây

```sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt,
       unxpstealcnt
FROM   v$undostat
ORDER  BY begin_time DESC;
```

Đọc các dòng quanh thời điểm query gặp lỗi. Nếu `SSOLDERRCNT` tăng trong khoảng đó, đây là bằng chứng có lỗi snapshot too old trong khoảng thống kê.

### 8.3. So sánh query duration và tuned retention

```sql
SELECT begin_time,
       end_time,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       undoblks
FROM   v$undostat
ORDER  BY begin_time DESC;
```

Nếu `MAXQUERYLEN` lớn hơn `TUNED_UNDORETENTION` trong các khoảng liên quan, đó là dấu hiệu đáng điều tra. Không coi phép so sánh này là chứng minh duy nhất cho nguyên nhân, vì query có thể không cần undo cho toàn bộ dữ liệu hoặc lỗi có nguyên nhân đặc thù khác.

### 8.4. Ước lượng undo generation rate

`UNDOBLKS` cho biết số block undo trong khoảng thống kê. Có thể ước lượng block/giây từ thời gian khoảng:

```sql
SELECT begin_time,
       end_time,
       undoblks,
       ROUND(
           undoblks /
           NULLIF((end_time - begin_time) * 86400, 0),
           2
       ) AS undo_blocks_per_second
FROM   v$undostat
ORDER  BY begin_time DESC;
```

Để chuyển sang byte/giây, nhân với database block size tương ứng. Ví dụ:

```sql
SELECT value AS db_block_size
FROM   v$parameter
WHERE  name = 'db_block_size';
```

Đây là ước lượng theo khoảng thống kê; workload có thể biến động mạnh bên trong khoảng đó. Dùng nhiều khoảng thời gian và tập trung vào peak workload.

### 8.5. Xem dung lượng undo tablespace

```sql
SELECT tablespace_name,
       file_name,
       bytes / 1024 / 1024 AS size_mb,
       autoextensible,
       maxbytes / 1024 / 1024 AS max_size_mb
FROM   dba_data_files
WHERE  tablespace_name = (
    SELECT value
    FROM   v$parameter
    WHERE  name = 'undo_tablespace'
);
```

Để xem extent undo theo trạng thái:

```sql
SELECT tablespace_name,
       status,
       COUNT(*) AS extent_count,
       SUM(bytes) / 1024 / 1024 AS size_mb
FROM   dba_undo_extents
GROUP  BY tablespace_name, status
ORDER  BY tablespace_name, status;
```

Các trạng thái thường gặp:
- ACTIVE: undo đang được transaction sử dụng.
- UNEXPIRED: undo đã commit nhưng còn trong thời gian retention theo quản lý hiện tại.
- EXPIRED: undo có thể được tái sử dụng.

Không diễn giải một ảnh chụp trạng thái extent đơn lẻ như toàn bộ lịch sử. Cần xem xu hướng và đối chiếu với thời điểm lỗi.

### 8.6. Kiểm tra tham số undo

```sql
SELECT name,
       value
FROM   v$parameter
WHERE  name IN (
    'undo_management',
    'undo_tablespace',
    'undo_retention'
);
```

Nếu database dùng Automatic Undo Management, `UNDO_MANAGEMENT` thường là AUTO. Trong cấu hình hiện đại, hãy xác nhận đúng undo tablespace của container/PDB đang chạy truy vấn.

### 8.7. Quyền truy cập

Các view `V$UNDOSTAT`, `V$PARAMETER`, `DBA_DATA_FILES` và `DBA_UNDO_EXTENTS` có thể yêu cầu quyền DBA hoặc quyền đọc dictionary. Không cấp quyền SYSDBA cho tài khoản ứng dụng chỉ để chẩn đoán. Hãy nhờ DBA chạy truy vấn hoặc cấp quyền đọc tối thiểu theo chính sách.

## 9. Xử lý ORA-01555 theo thứ tự

### 9.1. Xác định query và thời điểm lỗi

Thu thập:
- SQL_ID hoặc SQL text.
- Thời gian bắt đầu và thời gian lỗi.
- Thời lượng query.
- Bảng/partition và phạm vi dữ liệu được đọc.
- Job hoặc batch DML chạy cùng thời điểm.
- Session, module và action nếu ứng dụng có ghi nhận.

Không bắt đầu bằng việc tăng UNDO_RETENTION khi chưa biết query nào và workload nào tạo vấn đề.

### 9.2. Đối chiếu thống kê undo

Xem `V$UNDOSTAT` quanh thời điểm lỗi:
- `SSOLDERRCNT` có tăng không?
- `MAXQUERYLEN` là bao nhiêu?
- `TUNED_UNDORETENTION` có thấp hơn thời gian query không?
- `UNDOBLKS` có tăng đột biến không?
- `UNXPSTEALCNT` có tăng không?
- `NOSPACEERRCNT` có ghi nhận thiếu không gian không?

Các dấu hiệu này giúp định hướng, không phải kết luận tự động. Phải đối chiếu với query và trạng thái tablespace.

### 9.3. Giảm thời gian truy vấn

Đây thường là biện pháp có lợi lâu dài:
- Chỉ đọc các cột cần thiết, tránh quét dữ liệu thừa.
- Dùng predicate có chọn lọc và index phù hợp.
- Kiểm tra partition pruning.
- Giảm join không cần thiết.
- Tối ưu sort, group và subquery.
- Chia báo cáo thành các phạm vi có ý nghĩa nếu yêu cầu nghiệp vụ cho phép.
- Xem execution plan và thống kê thực tế.

Không chia query nếu việc chia làm mất yêu cầu một snapshot thống nhất mà báo cáo cần. Nếu chia thành nhiều statement, phải đánh giá lại semantics snapshot.

### 9.4. Điều chỉnh lịch workload

Nếu batch UPDATE lớn chạy trùng báo cáo dài:
- Chuyển batch sang cửa sổ ít báo cáo.
- Chia batch theo khóa/phạm vi.
- Giảm concurrency của batch khi undo generation quá cao.
- Tránh nhiều job mass update cùng lúc.
- Theo dõi tác động sau khi thay đổi lịch.

Đây là cách giảm cạnh tranh undo mà không nhất thiết tăng tài nguyên.

### 9.5. Tăng dung lượng undo tablespace

Nếu thống kê cho thấy undo space không đủ để giữ phiên bản cần thiết:
- Tăng datafile hoặc thêm datafile.
- Điều chỉnh AUTOEXTEND và MAXSIZE.
- Kiểm tra filesystem/ASM còn đủ dung lượng.
- Tính lại capacity theo undo generation và retention cần thiết.
- Theo dõi sau thay đổi.

Ví dụ DBA có thể mở rộng datafile theo cấu hình phù hợp:

```sql
ALTER DATABASE DATAFILE '/path/to/undo01.dbf'
RESIZE 8G;
```

Đây là cú pháp minh họa; đường dẫn, kích thước và khả năng resize phụ thuộc môi trường. Không chạy nguyên mẫu trên production.

### 9.6. Điều chỉnh UNDO_RETENTION

Có thể tăng mục tiêu retention nếu query cần snapshot dài hơn:

```sql
ALTER SYSTEM SET undo_retention = 3600 SCOPE=BOTH;
```

Giá trị 3600 là ví dụ một giờ. Trước khi thay đổi, cần kiểm tra dung lượng undo và peak undo generation. Nếu tablespace không đủ, tăng tham số đơn thuần không đảm bảo giữ được undo.

### 9.7. Cân nhắc RETENTION GUARANTEE

Nếu yêu cầu nghiệp vụ bắt buộc phải giữ undo đủ thời gian, có thể cân nhắc:

```sql
ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;
```

Lệnh này yêu cầu quyền DBA và tên tablespace phải đúng. Khi guarantee được bật, DML có thể gặp lỗi thiếu undo space nếu không thể cấp phát thêm. Cần có capacity plan và giám sát chặt chẽ.

### 9.8. Không áp dụng mọi biện pháp cùng lúc

Thay đổi nhiều yếu tố đồng thời khiến khó biết nguyên nhân nào thực sự giải quyết vấn đề. Nên:
1. Thu thập baseline.
2. Chọn một thay đổi phù hợp với bằng chứng.
3. Theo dõi cùng workload.
4. So sánh query duration, tuned retention, undo generation và lỗi.
5. Điều chỉnh tiếp nếu cần.

## 10. COMMIT trong cursor loop và lỗi snapshot too old

### 10.1. Pattern rủi ro

Ví dụ minh họa:

```sql
DECLARE
    CURSOR c_emp IS
        SELECT employee_id, salary
        FROM employees
        ORDER BY employee_id;
BEGIN
    FOR r IN c_emp LOOP
        UPDATE employees
        SET salary = salary + 100
        WHERE employee_id = r.employee_id;

        COMMIT;
    END LOOP;
END;
/
```

Cursor đọc một tập dữ liệu trong khi vòng lặp cập nhật và commit từng hàng. Tùy cách cursor được thực thi, bảng/block được đọc và mức undo generation, các commit liên tục có thể làm undo cũ cần cho cursor bị tái sử dụng trước khi fetch hoàn tất.

Đây là một pattern có thể góp phần gây ORA-01555. Nó còn có các nhược điểm khác:
- Transaction nghiệp vụ bị chia nhỏ thành nhiều commit.
- Không thể rollback toàn bộ batch nếu lỗi ở giữa.
- Tăng số lần commit và overhead.
- Dữ liệu được cập nhật một phần nếu chương trình dừng giữa chừng.

### 10.2. Ưu tiên set-based DML khi có thể

Nếu logic chỉ là cộng cùng một lượng cho các hàng thỏa điều kiện, có thể dùng một câu UPDATE:

```sql
UPDATE employees
SET salary = salary + 100
WHERE status = 'ACTIVE';

COMMIT;
```

Một câu DML thường đơn giản hơn cursor loop và tránh fetch cursor dài trong lúc liên tục commit.

### 10.3. Nếu phải xử lý theo batch

Khi nghiệp vụ cần chia batch:
- Chọn batch theo khóa ổn định.
- Chỉ commit sau khi một batch nghiệp vụ hoàn tất.
- Tránh tiếp tục fetch một cursor phụ thuộc vào dữ liệu đang bị chính loop thay đổi sau mỗi commit.
- Cân nhắc keyset pagination hoặc lưu danh sách khóa cần xử lý trước.
- Ghi nhận tiến độ để retry an toàn.
- Đảm bảo xử lý idempotent nếu job có thể chạy lại.

Thiết kế batch cần cân bằng kích thước transaction, lượng undo active, thời gian giữ khóa và khả năng phục hồi. Không có một batch size đúng cho mọi ứng dụng.

### 10.4. COMMIT không giải phóng ngay mọi undo cũ

Sau COMMIT, undo của transaction không còn active để rollback, nhưng có thể vẫn cần cho consistent read và Flashback. Oracle quản lý vòng đời undo theo trạng thái và retention; COMMIT không phải lệnh xóa undo ngay.

Do đó, commit thường xuyên không phải cách tổng quát để giảm dung lượng undo. Trong cursor loop, nó thậm chí có thể làm các phiên bản cũ bị tái sử dụng sớm hơn.

## 11. Phân biệt ORA-01555 với các lỗi liên quan

| Lỗi | Ý nghĩa chính | Hướng điều tra |
| --- | --- | --- |
| ORA-01555 | Undo cần cho snapshot không còn khả dụng | Query duration, undo generation, retention, capacity |
| ORA-30036 | Không thể mở rộng segment trong undo tablespace | Dung lượng, autoextend, maxsize, active/unexpired undo, guarantee |
| ORA-00054 | Resource busy khi NOWAIT hoặc wait timeout | Session giữ khóa, DDL/DML và timeout |
| ORA-00060 | Deadlock detected | Thứ tự khóa, deadlock graph, transaction |
| ORA-08177 | Serialization conflict trong SERIALIZABLE | Xung đột transaction và retry logic |

Không tăng undo tablespace để giải quyết row lock wait. Không kill blocker để giải quyết ORA-01555. Chẩn đoán theo đúng loại lỗi.

## 12. Những hiểu nhầm thường gặp

**“Query chạy lâu chắc chắn gặp ORA-01555.”**  
Sai. Query lâu chỉ làm tăng khoảng thời gian cần giữ snapshot cũ; nếu dữ liệu ít thay đổi và undo còn đủ, query vẫn có thể thành công.

**“Chỉ cần tăng UNDO_RETENTION là hết lỗi.”**  
Sai. UNDO_RETENTION là mục tiêu. Không có đủ dung lượng, Oracle có thể vẫn phải tái sử dụng undo chưa hết hạn nếu không có retention guarantee.

**“ORA-01555 nghĩa là undo tablespace đã đầy.”**  
Không nhất thiết. Undo cần thiết có thể đã bị tái sử dụng dù tablespace vẫn còn dung lượng trống ở thời điểm kiểm tra.

**“COMMIT xóa undo ngay lập tức.”**  
Sai. Undo đã commit có thể còn cần cho consistent read hoặc Flashback.

**“Tăng undo tablespace luôn là giải pháp duy nhất.”**  
Không. Tối ưu query, giảm DML đồng thời, điều chỉnh lịch batch và sửa cursor/commit pattern cũng có thể giải quyết nguyên nhân.

**“Query ngắn không thể gặp ORA-01555.”**  
Sai. Nếu undo cần thiết bị tái sử dụng rất nhanh hoặc có điều kiện đặc thù, query ngắn vẫn có rủi ro.

**“RETENTION GUARANTEE luôn an toàn hơn.”**  
Không. Nó bảo vệ undo chưa hết retention nhưng có thể làm DML thất bại khi tablespace hết chỗ.

**“MAXQUERYLEN lớn hơn TUNED_UNDORETENTION chứng minh nguyên nhân.”**  
Không. Đây là tín hiệu điều tra. Cần kiểm tra query có cần undo trong toàn bộ khoảng thời gian đó và dữ liệu có bị thay đổi hay không.

**“Mọi lỗi snapshot too old đều do cursor loop.”**  
Sai. Cursor loop chỉ là một pattern có thể gây rủi ro; nhiều nguyên nhân khác cũng dẫn tới lỗi.

## 13. Checklist chẩn đoán và capacity planning

Khi gặp ORA-01555, thu thập theo thứ tự:

1. **SQL và thời gian:** query nào lỗi, bắt đầu lúc nào, chạy bao lâu?
2. **Snapshot và phạm vi dữ liệu:** bảng/partition nào được đọc, dữ liệu có bị cập nhật trong lúc query chạy không?
3. **Workload đồng thời:** batch nào chạy, DML có tăng đột biến không?
4. **V$UNDOSTAT:** SSOLDERRCNT, MAXQUERYLEN, TUNED_UNDORETENTION, UNDOBLKS, UNXPSTEALCNT, NOSPACEERRCNT.
5. **Undo configuration:** UNDO_RETENTION, undo tablespace, autoextend, MAXSIZE.
6. **Undo extent:** ACTIVE, UNEXPIRED và EXPIRED biến động thế nào?
7. **Transaction pattern:** có cursor fetch kết hợp DML/COMMIT trong loop không?
8. **Query plan:** có thể giảm scan, join, sort hoặc thời lượng không?
9. **Retention requirement:** cần giữ undo bao lâu cho query và Flashback?
10. **Capacity:** peak undo rate nhân với retention mục tiêu có vừa tablespace và storage không?
11. **Guarantee trade-off:** có cần RETENTION GUARANTEE không, và DML có đủ chỗ không?
12. **Xác nhận sau thay đổi:** chạy lại workload tương đương và so sánh thống kê.

Một số nguyên tắc vận hành:
- Theo dõi peak workload, không chỉ average.
- Giữ query báo cáo trong thời gian hợp lý.
- Tránh commit từng hàng trong cursor loop khi không cần thiết.
- Đảm bảo undo tablespace có dung lượng và khả năng mở rộng phù hợp.
- Không bật RETENTION GUARANTEE nếu chưa đánh giá rủi ro DML thiếu chỗ.
- Ghi nhận lỗi và thời điểm để đối chiếu với batch workload.

## 14. Bài tập thực hành

### Bài 1 — Đọc lỗi ORA-01555

Một báo cáo bắt đầu lúc 09:00 và lỗi lúc 09:45. Trong khoảng đó, batch UPDATE chạy từ 09:10 đến 09:40.

Hãy giải thích vì sao query có thể cần undo cũ và thông tin nào cần thu thập để xác định nguyên nhân.

### Bài 2 — So sánh query duration

Hai query cùng chạy 20 phút:
- Query A đọc bảng ít thay đổi.
- Query B đọc bảng bị mass UPDATE liên tục.

Giải thích vì sao rủi ro ORA-01555 của B có thể cao hơn A.

### Bài 3 — Tính ước lượng undo

Undo generation peak là 1,5 MB/giây; retention mục tiêu là 2.400 giây. Tính lượng undo cơ bản trước dự phòng.

**Gợi ý:** nhân tốc độ tạo undo với số giây retention; sau đó giải thích vì sao cần cộng overhead và dự phòng.

### Bài 4 — Xem V$UNDOSTAT

```sql
SELECT begin_time,
       end_time,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       undoblks
FROM   v$undostat
ORDER  BY begin_time DESC;
```

Xác định khoảng nào có lỗi snapshot too old và so sánh thời gian query dài nhất với tuned retention.

### Bài 5 — Tính undo generation rate

```sql
SELECT begin_time,
       end_time,
       undoblks,
       ROUND(
           undoblks /
           NULLIF((end_time - begin_time) * 86400, 0),
           2
       ) AS undo_blocks_per_second
FROM   v$undostat
ORDER  BY begin_time DESC;
```

Giải thích tại sao nên quan sát nhiều khoảng thời gian và chú ý peak workload.

### Bài 6 — Kiểm tra AUTOEXTEND

Dùng DBA_DATA_FILES để kiểm tra undo datafile có AUTOEXTEND hay không, MAXBYTES là bao nhiêu. Giải thích tác động nếu file đã đạt MAXSIZE.

### Bài 7 — RETENTION GUARANTEE

Giả sử query cần 45 phút undo. DBA đặt UNDO_RETENTION 45 phút và bật RETENTION GUARANTEE nhưng undo tablespace không thể mở rộng.

Nêu rủi ro với DML và phân biệt ORA-01555 với ORA-30036.

### Bài 8 — Phân tích cursor loop

Đọc ví dụ cursor UPDATE rồi COMMIT mỗi vòng lặp ở mục 10. Nêu ba rủi ro và đề xuất một phương án set-based hoặc batch.

### Bài 9 — Tối ưu query

Một SELECT full scan mất 70 phút. Nêu các bước xem execution plan, predicate, index, partition pruning và dữ liệu không cần thiết trước khi đề nghị tăng undo.

### Bài 10 — Phân biệt lỗi

Phân loại các tình huống sau:
- Query báo ORA-01555.
- DML báo ORA-30036.
- UPDATE chờ session khác.
- Hai transaction báo ORA-00060.

Với mỗi tình huống, nêu view hoặc thông tin cần thu thập.

### Bài 11 — Đánh giá một cấu hình

Giả sử:
- Query dài nhất: 3.000 giây.
- TUNED_UNDORETENTION: 1.800 giây.
- Undo generation peak: 2 MB/giây.
- Undo tablespace hiện tại: 2 GB.

Nêu vì sao cấu hình có rủi ro và ước lượng dung lượng cơ bản cho retention 3.000 giây, chưa tính dự phòng.

### Bài 12 — Lập kế hoạch khắc phục

Một query báo cáo lỗi vào giờ batch. Hãy đề xuất thứ tự xử lý gồm thu thập V$UNDOSTAT, tối ưu query, điều chỉnh lịch batch, sizing undo, retention và kiểm tra lại. Giải thích vì sao không thay đổi mọi thông số cùng lúc.

## 15. Tài liệu Oracle tham khảo

- [Oracle Database Error Messages — ORA-01555](https://docs.oracle.com/en/database/oracle/oracle-database/19/errmg/ORA-01555.html): mô tả lỗi snapshot too old và thông tin liên quan.
- [Oracle Database Concepts — Undo Data](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/undo.html): undo records, undo segments và consistent read.
- [Oracle Database Administrator's Guide — Managing Undo](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-undo.html): Automatic Undo Management, UNDO_RETENTION và retention guarantee.
- [Oracle Database Reference — V$UNDOSTAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-UNDOSTAT.html): thống kê undo, query duration và lỗi snapshot too old.
- [Oracle Database Reference — V$PARAMETER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-PARAMETER.html): cấu hình tham số database.
- [Oracle Database Reference — DBA_UNDO_EXTENTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_UNDO_EXTENTS.html): trạng thái extent trong undo tablespace.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/): phân tích query và hiệu năng database.

Khi gặp ORA-01555, hãy xác định snapshot của query, thời lượng truy vấn và lượng undo được tạo trong cùng khoảng thời gian. Đối chiếu `MAXQUERYLEN`, `TUNED_UNDORETENTION`, `SSOLDERRCNT` và dung lượng undo để tìm nguyên nhân. Sau đó giảm thời gian query hoặc áp lực DML, sửa transaction pattern nếu cần, và chỉ điều chỉnh retention/dung lượng sau khi đã tính đến workload thực tế. **Mục tiêu là giữ đủ undo cho snapshot cần thiết mà vẫn bảo đảm hệ thống có đủ không gian để tiếp tục ghi dữ liệu.**
