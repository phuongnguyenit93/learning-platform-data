# Tái hiện ghi lệch trên bất biến nhiều hàng

Ghi lệch (*write skew*) xảy ra khi hai giao dịch cùng đọc một trạng thái hợp lệ, mỗi giao dịch cập nhật một hàng khác nhau, rồi cả hai cùng commit. Từng thay đổi riêng lẻ có vẻ hợp lệ, nhưng kết quả kết hợp lại vi phạm một quy tắc nghiệp vụ trên nhiều hàng.

Bài thực nghiệm này dùng hai phiên kết nối độc lập để tái hiện lỗi. Ta sẽ dùng quy tắc: **mỗi ca trực phải luôn có ít nhất một bác sĩ đang trực**. Sau khi tái hiện dưới snapshot isolation, ta chạy lại với SERIALIZABLE để quan sát cách hệ quản trị từ chối một lịch chạy không thể tuần tự hóa.

## 1. Mục tiêu và điều kiện thực nghiệm

Sau bài này, bạn có thể:

- Tạo hai transaction thực sự chạy đồng thời trên hai connection.
- Điều khiển thứ tự đọc, ghi và commit để tái hiện write skew.
- Giải thích vì sao hai UPDATE trên hai hàng khác nhau không nhất thiết xung đột ghi.
- Phân biệt write skew với lost update.
- So sánh kết quả ở snapshot isolation và SERIALIZABLE.
- Thử một cách bảo vệ bất biến bằng hàng điều phối chung.

Thực hiện trên database thử nghiệm riêng. Không chạy lệnh reset dữ liệu trên môi trường có dữ liệu nghiệp vụ thật. Mở hai cửa sổ terminal hoặc hai SQL editor session, mỗi cửa sổ dùng một connection độc lập tới cùng database.

Bài chính dùng PostgreSQL vì có thể quan sát rõ sự khác nhau giữa REPEATABLE READ (snapshot isolation trong PostgreSQL) và SERIALIZABLE (Serializable Snapshot Isolation). Phần cuối nêu cách điều chỉnh khi thử với các hệ quản trị khác.

## 2. Xây dựng dữ liệu ban đầu

Mỗi hàng biểu diễn trạng thái trực của một bác sĩ trong một ca. Khóa chính gồm shift_id và doctor_id, nên hai bác sĩ của cùng ca là hai hàng riêng biệt.

~~~sql
DROP TABLE IF EXISTS doctor_shift;

CREATE TABLE doctor_shift (
    shift_id  BIGINT  NOT NULL,
    doctor_id BIGINT  NOT NULL,
    on_call   BOOLEAN NOT NULL,
    PRIMARY KEY (shift_id, doctor_id)
);

INSERT INTO doctor_shift (shift_id, doctor_id, on_call)
VALUES
    (42, 1, TRUE),
    (42, 2, TRUE);
~~~

Kiểm tra trạng thái ban đầu:

~~~sql
SELECT shift_id, doctor_id, on_call
FROM doctor_shift
WHERE shift_id = 42
ORDER BY doctor_id;

SELECT COUNT(*) AS doctors_on_call
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;
~~~

Kết quả cần có:

| shift_id | doctor_id | on_call |
|---:|---:|---|
| 42 | 1 | TRUE |
| 42 | 2 | TRUE |

doctors_on_call bằng 2. Bất biến nghiệp vụ là: số bác sĩ đang trực trong ca 42 phải luôn lớn hơn hoặc bằng 1.

Một bác sĩ có thể kết thúc ca nếu sau thay đổi vẫn còn ít nhất một bác sĩ trực. Trong ứng dụng thực tế, kiểm tra số lượng thường được thực hiện bởi service hoặc stored procedure. Để quan sát lỗi, ta sẽ chạy SELECT kiểm tra trong mỗi phiên rồi mới chạy UPDATE riêng biệt.

## 3. Thực nghiệm A: tái hiện write skew bằng hai phiên

Đặt cả hai session ở REPEATABLE READ. Trong PostgreSQL, mỗi transaction sẽ đọc từ một snapshot ổn định. Điều quan trọng là **cả hai phiên phải đọc số lượng bằng 2 trước khi bất kỳ phiên nào commit**.

### 3.1. Phiên 1 — bắt đầu và đọc

Trong cửa sổ Session 1, chạy:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS doctors_on_call
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;
~~~

Kết quả:

~~~text
doctors_on_call
---------------
2
~~~

Giữ transaction mở. Chưa chạy UPDATE và chưa COMMIT.

### 3.2. Phiên 2 — bắt đầu và đọc cùng trạng thái

Trong cửa sổ Session 2, chạy:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS doctors_on_call
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;
~~~

Session 2 cũng phải thấy 2. Lúc này cả hai transaction đã đưa ra quyết định từ trạng thái có hai bác sĩ đang trực.

Nếu Session 2 thấy 1, có transaction khác đã thay đổi dữ liệu hoặc thứ tự thao tác bị sai. Hãy dừng, rollback cả hai session và khôi phục dữ liệu ban đầu trước khi tiếp tục.

### 3.3. Phiên 1 — cập nhật hàng của bác sĩ 1

Quay lại Session 1:

~~~sql
UPDATE doctor_shift
SET on_call = FALSE
WHERE shift_id = 42
  AND doctor_id = 1;
~~~

Câu UPDATE phải tác động đúng một hàng. Chưa commit.

### 3.4. Phiên 2 — cập nhật hàng của bác sĩ 2

Trong Session 2:

~~~sql
UPDATE doctor_shift
SET on_call = FALSE
WHERE shift_id = 42
  AND doctor_id = 2;
~~~

Câu UPDATE cũng phải tác động đúng một hàng. Hai phiên đang sửa hai hàng khác nhau nên không có xung đột ghi trực tiếp trên cùng một hàng.

### 3.5. Commit cả hai phiên

Commit Session 1:

~~~sql
COMMIT;
~~~

Sau đó commit Session 2:

~~~sql
COMMIT;
~~~

Với lịch chạy này ở PostgreSQL REPEATABLE READ, cả hai transaction có thể commit thành công. Mỗi transaction chỉ ghi một hàng khác nhau và không gặp xung đột cập nhật trên cùng hàng.

Kiểm tra kết quả bằng một session mới hoặc sau khi cả hai transaction đã kết thúc:

~~~sql
SELECT shift_id, doctor_id, on_call
FROM doctor_shift
WHERE shift_id = 42
ORDER BY doctor_id;

SELECT COUNT(*) AS doctors_on_call
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;
~~~

Trạng thái cuối:

| shift_id | doctor_id | on_call |
|---:|---:|---|
| 42 | 1 | FALSE |
| 42 | 2 | FALSE |

doctors_on_call bằng 0. Bất biến “mỗi ca phải có ít nhất một bác sĩ trực” đã bị phá vỡ, dù cả hai transaction đều commit thành công.

Đây chính là write skew.

## 4. Đọc lịch chạy và xác định vì sao lỗi xảy ra

Lịch chạy vừa thực hiện có thể viết lại như sau:

| Thứ tự | Session 1 (T1) | Session 2 (T2) |
|---|---|---|
| 1 | BEGIN, tạo snapshot S1 | |
| 2 | Đọc thấy 2 bác sĩ trực | |
| 3 | | BEGIN, tạo snapshot S2 |
| 4 | | Đọc thấy 2 bác sĩ trực |
| 5 | Đặt bác sĩ 1 thành FALSE | |
| 6 | | Đặt bác sĩ 2 thành FALSE |
| 7 | COMMIT | |
| 8 | | COMMIT |

Hai transaction có tập đọc giao nhau: cả hai cùng đọc điều kiện trên ca 42 và cùng thấy hai hàng đang trực. Nhưng tập ghi không giao nhau:

- WS(T1) = {doctor_shift(42, 1)}
- WS(T2) = {doctor_shift(42, 2)}

Cả hai quyết định ghi đều phụ thuộc vào điều kiện chung “còn ít nhất hai người đang trực”. Mỗi transaction không biết rằng transaction kia cũng đang dùng cùng điều kiện để cho một người khác kết thúc ca.

Có thể biểu diễn quan hệ phụ thuộc:

~~~mermaid
flowchart TD
    S["Trạng thái đầu: bác sĩ 1 và 2 đều trực"]
    S --> R1["T1 đọc predicate: có 2 người"]
    S --> R2["T2 đọc predicate: có 2 người"]
    R1 --> W1["T1 ghi hàng bác sĩ 1 = FALSE"]
    R2 --> W2["T2 ghi hàng bác sĩ 2 = FALSE"]
    W1 --> C["Cả hai commit"]
    W2 --> C
    C --> B["Bất biến bị phá: còn 0 người trực"]
~~~

Điểm mấu chốt: snapshot isolation thường ngăn hai transaction cùng ghi đè một hàng theo cách gây xung đột cập nhật, nhưng không tự ngăn hai transaction ghi những hàng khác nhau trong khi các quyết định của chúng phụ thuộc vào cùng một predicate nhiều hàng.

## 5. Phân biệt write skew với lost update

Hai hiện tượng có thể cùng bắt nguồn từ việc đọc một giá trị cũ, nhưng cấu trúc lịch chạy khác nhau.

| Tiêu chí | Lost update | Write skew |
|---|---|---|
| Tập ghi | Hai transaction ghi cùng một hàng hoặc giá trị | Hai transaction ghi các hàng khác nhau |
| Dữ liệu được đọc | Thường cùng đọc một giá trị cần cập nhật | Cùng đọc một điều kiện hoặc quan hệ nhiều hàng |
| Xung đột ghi trực tiếp | Có thể được phát hiện trên cùng hàng | Có thể không có vì các hàng ghi khác nhau |
| Kết quả sai | Một thay đổi bị ghi đè hoặc mất | Kết quả kết hợp vi phạm bất biến |
| Ví dụ | Hai lần trừ tiền cùng ghi số dư dựa trên giá trị cũ | Hai bác sĩ cùng rời ca, khiến không còn ai trực |

Trong ví dụ lost update, cả T1 và T2 có thể cùng ghi account.balance. Trong write skew, T1 ghi hàng bác sĩ 1 còn T2 ghi hàng bác sĩ 2. Vì vậy, chỉ kiểm tra xung đột ghi trên cùng hàng là chưa đủ để bảo vệ mọi bất biến nhiều hàng.

## 6. Thực nghiệm B: chạy lại ở SERIALIZABLE

Khôi phục dữ liệu trước khi chạy lại:

~~~sql
UPDATE doctor_shift
SET on_call = TRUE
WHERE shift_id = 42;
~~~

Kiểm tra số lượng phải bằng 2. Sau đó mở lại hai transaction ở mức SERIALIZABLE.

### 6.1. Hai phiên cùng đọc snapshot

Session 1:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS doctors_on_call
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;
~~~

Session 2:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS doctors_on_call
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;
~~~

Cả hai đều đọc được 2. Chưa UPDATE và chưa COMMIT ở cả hai phiên cho đến khi đã hoàn thành hai câu SELECT.

### 6.2. Hai phiên cập nhật các hàng riêng

Session 1:

~~~sql
UPDATE doctor_shift
SET on_call = FALSE
WHERE shift_id = 42
  AND doctor_id = 1;
~~~

Session 2:

~~~sql
UPDATE doctor_shift
SET on_call = FALSE
WHERE shift_id = 42
  AND doctor_id = 2;
~~~

Commit Session 1 trước:

~~~sql
COMMIT;
~~~

Sau đó thử commit Session 2:

~~~sql
COMMIT;
~~~

PostgreSQL SSI theo dõi các phụ thuộc đọc–ghi liên quan đến predicate. Với lịch chạy tạo write skew này, hệ thống phải hủy một transaction để không chấp nhận kết quả không thể tuần tự hóa. Một trong hai phiên sẽ nhận lỗi serialization failure, thường có SQLSTATE 40001. Lỗi có thể được báo ở câu lệnh ghi hoặc khi COMMIT, tùy lịch thực thi và thời điểm phát hiện.

Khi một transaction đã nhận lỗi, hãy kết thúc nó bằng:

~~~sql
ROLLBACK;
~~~

Nếu transaction đã bị đánh dấu aborted, các câu lệnh tiếp theo sẽ không thể tiếp tục nghiệp vụ trong transaction đó.

### 6.3. Retry toàn bộ transaction và kiểm tra lại điều kiện

Giả sử Session 2 là transaction bị hủy. Không chạy lại riêng câu UPDATE bác sĩ 2. Hãy bắt đầu transaction mới và đọc lại trạng thái:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS doctors_on_call
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;
~~~

Lần này kết quả là 1, vì transaction còn lại đã commit việc cho bác sĩ 1 kết thúc ca.

Quy tắc nghiệp vụ chỉ cho phép cập nhật nếu số người đang trực lớn hơn 1. Do đó, ứng dụng phải từ chối yêu cầu của bác sĩ 2 và không chạy UPDATE. Kết thúc transaction mới:

~~~sql
COMMIT;
~~~

Kiểm tra lại:

~~~sql
SELECT doctor_id, on_call
FROM doctor_shift
WHERE shift_id = 42
ORDER BY doctor_id;
~~~

Kết quả hợp lệ là một bác sĩ vẫn đang trực. SERIALIZABLE không tự quyết định nghiệp vụ thay ứng dụng; nó từ chối một lịch chạy nguy hiểm. Ứng dụng phải retry toàn bộ thao tác, đọc lại dữ liệu và áp dụng lại điều kiện nghiệp vụ.

## 7. Cách diễn giải kết quả giữa hai lần chạy

| Thực nghiệm | Kết quả có thể quan sát | Bất biến cuối cùng |
|---|---|---|
| PostgreSQL REPEATABLE READ | Cả hai transaction ghi các hàng khác nhau và có thể commit | Có thể bị vi phạm |
| PostgreSQL SERIALIZABLE | Một transaction có thể bị hủy với serialization failure | Được bảo vệ nếu ứng dụng retry và kiểm tra lại đúng |
| PostgreSQL READ COMMITTED với đúng lịch hai SELECT đều chạy trước UPDATE | Hai câu đọc có thể cùng thấy 2; hai UPDATE riêng biệt có thể cùng commit | Có thể bị vi phạm |
| PostgreSQL SERIALIZABLE nhưng ứng dụng bỏ qua lỗi hoặc không retry đúng | Transaction bị hủy nhưng ứng dụng có thể báo sai hoặc xử lý dở dang | Tùy cách ứng dụng xử lý |

Kết quả phụ thuộc chính xác isolation level và lịch chạy. Nếu Session 2 chỉ SELECT sau khi Session 1 đã commit, nó sẽ thấy một bác sĩ còn trực và có thể từ chối thao tác; lịch đó không tái hiện write skew.

## 8. Thực nghiệm C: bảo vệ bằng hàng điều phối chung

Một cách khác là tạo một hàng đại diện cho ca trực. Mọi transaction thay đổi trạng thái bác sĩ trong cùng ca phải khóa hàng điều phối trước khi đọc số người đang trực.

Tạo bảng điều phối và dữ liệu:

~~~sql
CREATE TABLE shift_guard (
    shift_id BIGINT PRIMARY KEY
);

INSERT INTO shift_guard (shift_id)
VALUES (42)
ON CONFLICT (shift_id) DO NOTHING;

UPDATE doctor_shift
SET on_call = TRUE
WHERE shift_id = 42;
~~~

Chạy mỗi phiên ở READ COMMITTED để minh họa cơ chế khóa. Session 1:

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT shift_id
FROM shift_guard
WHERE shift_id = 42
FOR UPDATE;

SELECT COUNT(*) AS doctors_on_call
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;

-- Nếu số người đang trực > 1 thì mới cho phép cập nhật.
UPDATE doctor_shift
SET on_call = FALSE
WHERE shift_id = 42
  AND doctor_id = 1;
~~~

Giữ Session 1 mở sau câu UPDATE. Chưa commit để khóa trên shift_guard(42) vẫn được giữ.

Trong lúc Session 1 đang giữ khóa guard row, chạy Session 2:

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT shift_id
FROM shift_guard
WHERE shift_id = 42
FOR UPDATE;

-- Câu SELECT FOR UPDATE này phải chờ Session 1 commit.
~~~

Khi Session 2 đang chờ ở SELECT FOR UPDATE, quay lại Session 1 và chạy:

~~~sql
COMMIT;
~~~

Sau khi Session 1 commit, câu SELECT FOR UPDATE của Session 2 mới hoàn tất và Session 2 lấy được khóa. Tiếp tục trong Session 2:

~~~sql
SELECT COUNT(*) AS doctors_on_call
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;

-- Kết quả hiện tại là 1.
-- Không chạy UPDATE vì điều kiện nghiệp vụ không còn đúng.

COMMIT;
~~~

Hàng shift_guard(42) là một điểm đồng bộ đã tồn tại, vì vậy transaction có thể khóa nó ngay cả khi tập hàng chi tiết đang được kiểm tra có thể thay đổi. Cách này chỉ đúng khi **mọi đường ghi liên quan đều lấy cùng guard lock trước khi đọc predicate**. Một batch job hoặc service bỏ qua quy ước sẽ vẫn có thể phá bất biến.

Với isolation level dùng snapshot cấp transaction, cần tránh đọc predicate trước khi lấy guard lock. Nếu snapshot đã được tạo từ trước, lần đọc sau khi chờ khóa có thể vẫn nhìn trạng thái cũ. Hãy lấy guard lock trước lần đọc phụ thuộc vào điều kiện và xác nhận hành vi trên hệ quản trị đang dùng.

## 9. Thử nghiệm trên hệ quản trị khác

Ý tưởng hai phiên vẫn giống nhau: cả hai transaction phải đọc cùng trạng thái ban đầu, sau đó ghi các hàng khác nhau trước khi commit. Cú pháp và hành vi phụ thuộc engine.

### 9.1. MySQL InnoDB

Xác nhận cả hai bảng dùng InnoDB và đặt isolation level cho từng session:

~~~sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT COUNT(*)
FROM doctor_shift
WHERE shift_id = 42
  AND on_call = TRUE;
~~~

Lặp lại trong session còn lại. Sau khi cả hai đã đọc 2, mỗi session UPDATE một doctor_id khác nhau rồi commit. Với InnoDB và lịch ghi hai hàng riêng biệt này, snapshot read không tự tạo xung đột ghi trên cùng hàng; write skew có thể được tái hiện.

Để kiểm tra mức bảo vệ cao hơn, có thể thử SERIALIZABLE, nhưng hãy đọc tài liệu đúng phiên bản InnoDB và ghi lại hành vi thực tế của locking read, gap/next-key lock và lỗi trả về. Không suy ra kết quả chỉ từ tên isolation level.

### 9.2. SQL Server SNAPSHOT

Trước tiên, quản trị viên cần bật snapshot isolation cho database thử nghiệm:

~~~sql
ALTER DATABASE [ConcurrencyLab]
SET ALLOW_SNAPSHOT_ISOLATION ON;
~~~

Trong mỗi session:

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
BEGIN TRANSACTION;

SELECT COUNT(*)
FROM dbo.DoctorShift
WHERE ShiftId = 42
  AND OnCall = 1;
~~~

Sau khi cả hai session đều đọc 2, cập nhật hai hàng khác nhau và commit. Snapshot isolation có thể cho phép cả hai transaction commit vì chúng không ghi cùng một hàng. Thử lại với SERIALIZABLE để quan sát cơ chế khóa phạm vi và sự khác biệt trong blocking.

Đừng nhầm READ_COMMITTED_SNAPSHOT với transaction-level SNAPSHOT. Đây là hai chế độ row versioning khác nhau.

### 9.3. PostgreSQL SERIALIZABLE

PostgreSQL không cần bật một tùy chọn database riêng để dùng SERIALIZABLE. Mức này được chọn ở transaction bằng BEGIN ISOLATION LEVEL SERIALIZABLE. Cơ chế SSI theo dõi phụ thuộc và có thể trả SQLSTATE 40001; ứng dụng cần retry toàn bộ transaction.

Khi so sánh giữa các hệ quản trị, ghi rõ phiên bản, engine, isolation level, autocommit, index, lịch thao tác và mã lỗi. Không coi các kết quả của một engine là quy tắc chung cho engine khác.

## 10. Vì sao CHECK constraint đơn giản không đủ?

Một constraint như:

~~~sql
CHECK (on_call IN (TRUE, FALSE))
~~~

chỉ xác nhận giá trị của một hàng là hợp lệ. Nó không thể bảo đảm rằng tổng số hàng có on_call = TRUE trong mỗi ca phải lớn hơn hoặc bằng 1.

Đây là bất biến nhiều hàng. Cần một cơ chế có thể phối hợp các transaction cùng đánh giá predicate đó, chẳng hạn:

- SERIALIZABLE và retry khi serialization failure.
- Guard row được mọi writer khóa trước khi đọc.
- Một hàng tổng hợp/bộ đếm được cập nhật nguyên tử và duy trì trong cùng transaction.
- Constraint chuyên biệt nếu hệ quản trị có loại constraint phù hợp với quy tắc.

Không nên đặt một truy vấn COUNT(*) trong trigger rồi giả định rằng trigger tự làm phép kiểm tra trở nên nguyên tử. Trigger vẫn chịu isolation level và cơ chế khóa của transaction kích hoạt nó.

## 11. Những sai lệch khiến thực nghiệm không tái hiện được lỗi

Nếu cả hai session không tạo ra kết quả mong đợi, hãy kiểm tra thứ tự thao tác trước khi kết luận về engine.

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Session 2 đọc được 1 thay vì 2 | Session 1 đã commit trước khi Session 2 đọc | Reset dữ liệu và chạy lại; yêu cầu cả hai SELECT hoàn tất trước mọi UPDATE |
| Session 2 bị chờ ở UPDATE | Hai transaction vô tình cập nhật cùng hàng hoặc trigger cập nhật hàng chung | Xác nhận doctor_id khác nhau; xem trigger và lock wait |
| Một transaction bị hủy ngay ở REPEATABLE READ | Có writer khác hoặc một xung đột bổ sung ngoài bài lab | Đóng các session khác, reset dữ liệu, kiểm tra lỗi và deadlock report |
| SERIALIZABLE không báo lỗi trong lần thử | Lịch chạy không chồng lấn đúng cách hoặc predicate đọc không bao phủ hàng được ghi | Đảm bảo cả hai đọc predicate trước khi ghi và kiểm tra lại đúng ca |
| Kết quả cuối không giống bảng dự kiến | UPDATE tác động 0/nhiều hàng hoặc dữ liệu ban đầu không sạch | Kiểm tra khóa chính, số hàng bị tác động và dữ liệu seed |
| Session vẫn ở trạng thái aborted | Một câu lệnh trước đó đã lỗi trong transaction | Chạy ROLLBACK trước khi bắt đầu transaction mới |

Mỗi lần chạy nên bắt đầu từ trạng thái dữ liệu sạch. Không chạy lại một nửa lịch cũ sau khi một session đã commit hoặc bị lỗi.

## 12. Ghi nhận kết quả thực nghiệm

Để kết quả có thể được người khác lặp lại, hãy ghi:

| Trường | Giá trị cần lưu |
|---|---|
| Database và phiên bản | Tên sản phẩm, major/minor/build |
| Storage engine/table type | Ví dụ InnoDB hoặc bảng disk-based |
| Isolation level | REPEATABLE READ, SNAPSHOT, SERIALIZABLE... |
| Số session | Hai connection độc lập |
| Dữ liệu đầu | Hai bác sĩ đều on_call = TRUE |
| Thứ tự đọc | T1 đọc 2, sau đó T2 đọc 2, trước mọi UPDATE |
| Thứ tự ghi | T1 ghi bác sĩ 1; T2 ghi bác sĩ 2 |
| Thứ tự commit | Ghi rõ session nào commit trước |
| Kết quả | Commit/abort, số hàng được cập nhật, SQLSTATE/vendor code |
| Bất biến sau cùng | Số bác sĩ còn trực phải ít nhất là 1 |

Không chỉ ghi “đã thử SERIALIZABLE”. Cần lưu cả lịch thao tác, bởi một bài thử chạy tuần tự không thể chứng minh cơ chế xử lý write skew.

## 13. Checklist thực hành

- [ ] Đã tạo hai connection độc lập tới cùng database thử nghiệm?
- [ ] Đã xác nhận dữ liệu đầu có đúng hai bác sĩ đang trực?
- [ ] Đã bắt đầu transaction ở isolation level cần thử?
- [ ] Cả hai session đã đọc được số lượng 2 trước khi bất kỳ session nào ghi hoặc commit?
- [ ] Mỗi transaction chỉ cập nhật một hàng bác sĩ khác nhau?
- [ ] Đã commit theo thứ tự được chỉ định và ghi lại kết quả?
- [ ] Đã kiểm tra trạng thái cuối và số lượng bác sĩ đang trực?
- [ ] Đã lặp lại cùng lịch với SERIALIZABLE?
- [ ] Đã xử lý serialization failure bằng ROLLBACK và transaction mới?
- [ ] Lần retry đã đọc lại predicate và kiểm tra điều kiện nghiệp vụ?
- [ ] Đã thử guard row và bảo đảm mọi writer dùng cùng giao thức?
- [ ] Đã ghi phiên bản, engine, isolation level và mã lỗi để có thể tái hiện?

Thực nghiệm hai phiên cho thấy write skew xuất hiện khi các transaction cùng dựa vào một predicate nhiều hàng nhưng ghi các hàng khác nhau. Snapshot nhất quán không tự bảo vệ bất biến toàn cục. Để ngăn lỗi, cần một cơ chế phối hợp như SERIALIZABLE, guard row hoặc cập nhật nguyên tử trên một hàng tổng hợp; khi hệ quản trị hủy transaction, ứng dụng phải chạy lại toàn bộ nghiệp vụ và đánh giá lại điều kiện từ dữ liệu mới.
