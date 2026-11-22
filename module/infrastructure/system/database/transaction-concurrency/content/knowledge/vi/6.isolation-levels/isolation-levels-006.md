# Cô lập ảnh chụp (snapshot isolation) trong tương quan với các mức SQL

## 1. Snapshot isolation là gì?

**Snapshot isolation (SI)** là một cơ chế điều khiển tương tranh dựa trên nhiều phiên bản dữ liệu (*Multi-Version Concurrency Control – MVCC*). Mỗi giao dịch đọc dữ liệu từ một **ảnh chụp nhất quán** (*snapshot*) tại một thời điểm xác định. Các thay đổi chưa commit của giao dịch khác không xuất hiện trong ảnh chụp đó.

Thay vì bắt mọi thao tác đọc phải chờ giao dịch ghi hoàn tất, DBMS có thể lưu nhiều phiên bản của cùng một hàng. Giao dịch đọc chọn phiên bản phù hợp với snapshot của nó; giao dịch ghi tạo phiên bản mới. Nhờ vậy, nhiều giao dịch có thể đọc và ghi chồng lấn mà không phải khóa tất cả thao tác đọc thông thường.

Hãy xét bảng tài khoản:

| account_id | owner_name | balance |
| ---: | --- | ---: |
| 101 | An | 1000 |
| 202 | Bình | 500 |

Tại thời điểm giao dịch T1 bắt đầu, snapshot của T1 có số dư An là 1.000. Trong lúc T1 còn mở, giao dịch T2 cập nhật số dư An lên 1.200 và commit. Khi T1 đọc lại, dưới SI, T1 vẫn nhìn thấy phiên bản 1.000 theo snapshot ban đầu. Một giao dịch mới T3 bắt đầu sau commit của T2 có thể nhìn thấy 1.200.

```text
Thời gian  T1 (snapshot S1)          T2                         T3
-----------------------------------------------------------------------
t1         BEGIN; snapshot S1
t2                                  BEGIN
t3                                  UPDATE balance = 1200
t4                                  COMMIT
t5         SELECT balance -> 1000
t6                                                             BEGIN; S3
t7                                                             SELECT -> 1200
t8         COMMIT
```

T1 không đọc thay đổi của T2 vì thay đổi đó được commit sau thời điểm snapshot S1 của T1 được xác lập. T3 bắt đầu sau T2 commit nên ảnh chụp của T3 bao gồm phiên bản mới.

Đặc điểm cốt lõi của SI là **tính nhất quán của ảnh chụp đọc**. Điều này giúp tránh dirty read và non-repeatable read theo cách triển khai SI thông thường. Tuy nhiên, SI không đồng nghĩa với mức cô lập SERIALIZABLE: một số lịch vẫn có thể phá vỡ bất biến nghiệp vụ dù mỗi giao dịch nhìn thấy một ảnh chụp nhất quán.

## 2. Cách MVCC tạo và sử dụng nhiều phiên bản

Trong mô hình một phiên bản đơn giản, một hàng chỉ có một giá trị hiện hành. Khi giao dịch ghi thay đổi hàng, thao tác đọc và ghi có thể phải chờ nhau vì cùng truy cập một phiên bản.

MVCC thay đổi cách tổ chức đó. Về khái niệm, một hàng có thể có các phiên bản:

```text
X:
  phiên bản v1 = 1000  (được commit trước)
  phiên bản v2 = 1200  (do T2 tạo và commit)
```

Mỗi snapshot xác định những giao dịch/phiên bản nào được xem là đã hoàn tất và khả kiến. Khi đọc X:

- T1 có snapshot được tạo trước khi T2 commit, nên chọn v1 = 1000.
- T3 có snapshot sau khi T2 commit, nên chọn v2 = 1200.
- Một giao dịch không được nhìn thấy phiên bản do giao dịch khác ghi nhưng chưa commit.

Đây là mô tả khái niệm. Cách lưu phiên bản, mã giao dịch, dọn dẹp phiên bản cũ và quy tắc xác định khả kiến khác nhau giữa PostgreSQL, Oracle, SQL Server, MySQL/InnoDB và các DBMS khác.

### 2.1. Snapshot không phải bản sao vật lý riêng của toàn bộ database

Snapshot thường là **một quy tắc khả kiến** áp dụng cho dữ liệu đã commit tại thời điểm logic nhất định, không nhất thiết là bản sao đầy đủ được tạo ra cho từng giao dịch. DBMS sử dụng metadata và phiên bản hàng để trả về góc nhìn nhất quán.

Vì thế, giao dịch dài có thể khiến các phiên bản cũ cần được giữ lâu hơn. Với cơ chế MVCC, DBMS phải cân bằng giữa khả năng đọc snapshot cũ và việc thu hồi phiên bản không còn cần thiết. Giao dịch đọc kéo dài có thể làm tăng áp lực lưu trữ, dọn dẹp và duy trì phiên bản.

### 2.2. Thay đổi chưa commit vẫn không được đọc

Giả sử T1 ghi số dư từ 1.000 thành 700 nhưng chưa commit. T2 mở snapshot trong lúc T1 chưa commit. T2 đọc phiên bản đã commit trước đó, tức 1.000, chứ không đọc 700. Nếu T1 commit, snapshot đã có của T2 thường vẫn giữ góc nhìn cũ; một giao dịch mới mới có thể thấy 700.

Nếu T1 rollback, phiên bản chưa commit không trở thành dữ liệu đã xác nhận. Cơ chế này ngăn dirty read trong snapshot isolation.

## 3. Snapshot isolation so với các mức cô lập SQL

Các mức cô lập được đặt tên trong SQL thường gồm:

- `READ UNCOMMITTED`
- `READ COMMITTED`
- `REPEATABLE READ`
- `SERIALIZABLE`

Snapshot isolation là **một cơ chế/đặc tính triển khai** được nhiều DBMS sử dụng. Nó không phải một mức có tên riêng nằm trong danh sách bốn mức tiêu chuẩn SQL truyền thống. Một DBMS có thể thực hiện REPEATABLE READ bằng snapshot isolation, cung cấp một tùy chọn snapshot riêng, hoặc kết hợp MVCC với khóa theo cách khác.

| Khái niệm | Mục tiêu/đặc điểm | Quan hệ với SI |
| --- | --- | --- |
| READ UNCOMMITTED | Có thể cho phép đọc thay đổi chưa commit trong mô hình cổ điển | SI thông thường không cho dirty read |
| READ COMMITTED | Mỗi câu lệnh đọc dữ liệu đã commit tại thời điểm câu lệnh/snapshot của nó | Snapshot có thể được làm mới sau từng câu lệnh |
| REPEATABLE READ | Duy trì góc nhìn ổn định hơn trong một giao dịch | Một số DBMS triển khai bằng transaction-level snapshot |
| Snapshot isolation | Các lần đọc trong giao dịch dùng snapshot nhất quán; ghi đồng thời lên cùng hàng thường được phát hiện/điều phối | Có thể được dùng để triển khai REPEATABLE READ hoặc mức riêng |
| SERIALIZABLE | Kết quả các giao dịch đã commit tương đương một lịch chạy tuần tự | SI đơn thuần chưa đảm bảo điều này |

Không nên suy luận chỉ từ nhãn mức cô lập. Cần xác định DBMS, engine lưu trữ, cấu hình và hành vi cụ thể.

### 3.1. SI không phải READ COMMITTED

Với READ COMMITTED, nhiều hệ thống tạo snapshot mới cho **mỗi câu lệnh**. Vì vậy, cùng một giao dịch có thể đọc giá trị cũ ở câu đầu và giá trị mới ở câu sau, nếu một giao dịch khác commit ở giữa.

Với transaction-level snapshot isolation, snapshot được giữ ổn định trong phạm vi giao dịch. Một SELECT tiếp theo tiếp tục nhìn ảnh chụp cũ. Điều này ngăn hiện tượng non-repeatable read đối với cùng dữ liệu được đọc qua snapshot.

### 3.2. SI không tự động là SERIALIZABLE

SI bảo đảm một góc nhìn đọc nhất quán và có quy tắc xử lý xung đột ghi. Nhưng nếu hai giao dịch đọc các hàng giống nhau rồi ghi những hàng khác nhau, chúng có thể không đụng cùng một hàng để phát sinh xung đột ghi. Cả hai có thể commit, trong khi kết quả tổng hợp vi phạm một điều kiện nghiệp vụ.

Hiện tượng tiêu biểu là **write skew**. Đây là lý do phải phân biệt:
- **Repeatable reads qua snapshot**: cùng giao dịch nhìn góc nhìn ổn định.
- **Serializable execution**: toàn bộ lịch có thể được sắp thành một thứ tự tuần tự mà vẫn giữ kết quả quan sát và thay đổi hợp lệ.

Hai mục tiêu có liên quan nhưng không tương đương.

## 4. Phân biệt với các hiện tượng đồng thời kinh điển

| Hiện tượng | Mô tả | SI thông thường xử lý ra sao? |
| --- | --- | --- |
| Dirty read | Đọc thay đổi chưa commit của giao dịch khác | Bị ngăn |
| Non-repeatable read | Đọc cùng hàng hai lần và thấy giá trị đã commit khác nhau | Bị ngăn bởi snapshot cố định |
| Phantom read | Cùng truy vấn điều kiện nhưng tập hàng thay đổi | Snapshot cố định thường ngăn phantom đối với truy vấn đọc snapshot |
| Lost update | Thay đổi của một giao dịch bị ghi đè bởi giao dịch khác | Cơ chế SI thường phát hiện xung đột ghi cùng hàng hoặc khiến một giao dịch thất bại; chi tiết phụ thuộc DBMS và mẫu thao tác |
| Write skew | Hai giao dịch cùng đọc điều kiện, ghi những hàng khác nhau, phá bất biến chung | Có thể xảy ra dưới SI |
| Serialization anomaly | Lịch đã commit không tương đương thứ tự tuần tự | Có thể xảy ra dưới SI |

SI có thể cung cấp hành vi mạnh hơn một số bảo đảm tối thiểu của REPEATABLE READ theo chuẩn SQL, nhưng vẫn không loại bỏ mọi anomaly mà SERIALIZABLE phải ngăn.

## 5. Write skew: giới hạn quan trọng của snapshot isolation

Giả sử phòng trực phải luôn có ít nhất một bác sĩ đang trực. Bảng:

| doctor_id | name | on_call |
| ---: | --- | --- |
| 1 | An | TRUE |
| 2 | Bình | TRUE |

Bất biến nghiệp vụ:

\[
\text{Số bác sĩ trực} \geq 1
\]

Hai giao dịch chạy đồng thời:

- T1 đọc cả hai hàng, thấy có hai bác sĩ trực; quyết định cho An nghỉ, cập nhật hàng An thành FALSE.
- T2 cũng đọc snapshot có hai bác sĩ trực; quyết định cho Bình nghỉ, cập nhật hàng Bình thành FALSE.

Mỗi giao dịch chỉ ghi một hàng riêng. Vì vậy, chúng không có xung đột ghi trực tiếp trên cùng hàng. Dưới snapshot isolation, cả hai có thể được phép commit nếu không có cơ chế bổ sung bảo vệ bất biến. Kết quả cuối:

| doctor_id | name | on_call |
| ---: | --- | --- |
| 1 | An | FALSE |
| 2 | Bình | FALSE |

Không còn ai trực, vi phạm quy tắc.

### 5.1. Đồ thị phụ thuộc

Hai giao dịch đều đọc trạng thái của người còn lại trước khi cập nhật hàng của mình:

```text
T1 đọc hàng Bình, rồi ghi hàng An
T2 đọc hàng An,   rồi ghi hàng Bình

T1 --RW anti-dependency--> T2
T2 --RW anti-dependency--> T1
```

Hai cạnh tạo chu trình phụ thuộc. Snapshot isolation chỉ kiểm soát xung đột ghi theo cách triển khai của nó; khi các giao dịch ghi các hàng khác nhau, chu trình RW có thể không bị phát hiện nếu không có kiểm tra tuần tự hóa.

### 5.2. Vì sao khóa hàng được ghi chưa chắc đủ?

Nếu T1 chỉ khóa hàng An và T2 chỉ khóa hàng Bình, hai giao dịch vẫn có thể cùng tiến hành. Việc khóa chính hàng mà mỗi giao dịch định sửa không tự bảo vệ điều kiện tổng thể “ít nhất một bác sĩ trực”.

Có thể khắc phục bằng các cách như:
- Dùng một hàng tổng hợp/đại diện để tuần tự hóa việc thay đổi lịch trực.
- Khóa toàn bộ tập dữ liệu liên quan theo một chiến lược thống nhất.
- Định nghĩa ràng buộc phù hợp ở database nếu mô hình cho phép.
- Dùng isolation SERIALIZABLE để DBMS phát hiện phụ thuộc nguy hiểm và hủy một giao dịch.

Chọn cách nào phụ thuộc cấu trúc dữ liệu và lưu lượng. Nếu dùng SERIALIZABLE, ứng dụng cần xử lý lỗi serialization bằng cách retry toàn bộ transaction.

## 6. Snapshot isolation trong PostgreSQL

PostgreSQL sử dụng MVCC. Mỗi câu lệnh đọc thông thường nhìn snapshot dữ liệu đã commit. Cách xác định snapshot phụ thuộc mức cô lập:

- **READ COMMITTED**: snapshot mới ở đầu mỗi câu lệnh.
- **REPEATABLE READ**: snapshot ổn định trong suốt giao dịch.
- **SERIALIZABLE**: snapshot ổn định kết hợp Serializable Snapshot Isolation (SSI) để theo dõi các phụ thuộc có thể gây bất thường tuần tự hóa.

PostgreSQL triển khai REPEATABLE READ dựa trên snapshot isolation. Mức này ngăn dirty read, non-repeatable read và phantom read thông thường, nhưng **vẫn có thể xảy ra serialization anomaly**, bao gồm write skew.

PostgreSQL SERIALIZABLE bổ sung phát hiện phụ thuộc nguy hiểm. Khi hệ thống không thể bảo đảm lịch tương đương tuần tự, nó có thể hủy một transaction với SQLSTATE `40001` (`serialization_failure`). Ứng dụng cần retry toàn bộ transaction.

Có thể kiểm tra mức cô lập mặc định:

```sql
SHOW default_transaction_isolation;
```

Đặt mức cô lập cho một giao dịch:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
-- Các truy vấn và cập nhật dùng snapshot của giao dịch.
COMMIT;
```

Hoặc:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
-- Đọc, kiểm tra bất biến và cập nhật.
COMMIT;
```

Nếu commit hoặc câu lệnh gặp lỗi serialization, cần rollback nếu giao dịch còn ở trạng thái lỗi và thử lại **từ đầu giao dịch**, không chỉ chạy lại lệnh cuối.

## 7. Thực nghiệm PostgreSQL: một snapshot, hai kết nối

Thí nghiệm này cho thấy giao dịch REPEATABLE READ giữ góc nhìn cũ trong khi giao dịch khác đã commit một cập nhật. Đây là ví dụ cụ thể về snapshot-level consistency.

### 7.1. Chuẩn bị bảng

Dùng một database PostgreSQL dành riêng cho thực hành. Mở hai cửa sổ `psql` độc lập, kết nối cùng database. Có thể xác nhận hai backend bằng:

```sql
SELECT current_database(), pg_backend_pid();
```

Tạo bảng và dữ liệu trong một phiên:

```sql
DROP TABLE IF EXISTS public.si_accounts;

CREATE TABLE public.si_accounts (
    account_id INTEGER PRIMARY KEY,
    balance INTEGER NOT NULL
);

INSERT INTO public.si_accounts (account_id, balance)
VALUES (101, 1000), (202, 500);
```

Không chạy lệnh DROP trên dữ liệu cần giữ.

### 7.2. Quan sát snapshot ổn định

**Phiên A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM public.si_accounts
WHERE account_id = 101;
-- 1000
```

Giữ A mở. **Phiên B:**

```sql
BEGIN;

UPDATE public.si_accounts
SET balance = 1200
WHERE account_id = 101;

COMMIT;
```

Quay lại **phiên A**:

```sql
SELECT balance
FROM public.si_accounts
WHERE account_id = 101;
-- Vẫn 1000 trong snapshot của A.

COMMIT;
```

Mở một giao dịch mới hoặc chạy SELECT mới sau khi A kết thúc:

```sql
SELECT balance
FROM public.si_accounts
WHERE account_id = 101;
-- 1200
```

Kết quả cho thấy A duy trì góc nhìn tại snapshot của nó; giao dịch mới nhìn phiên bản đã commit sau đó.

### 7.3. So sánh với READ COMMITTED

Đặt lại số dư về 1000, rồi ở A:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM public.si_accounts
WHERE account_id = 101;
-- 1000
```

Giữ A mở, B cập nhật và commit số dư 1200 như trên. A đọc lại:

```sql
SELECT balance
FROM public.si_accounts
WHERE account_id = 101;
-- 1200 ở READ COMMITTED.
COMMIT;
```

Ở PostgreSQL, snapshot READ COMMITTED được làm mới cho từng câu lệnh. Do đó, A có thể nhìn thấy commit của B ở câu SELECT thứ hai. Sự khác nhau giữa hai thử nghiệm nằm ở **thời điểm snapshot được lấy**.

## 8. Thực nghiệm write skew dưới REPEATABLE READ

Ta mô phỏng quy tắc “ít nhất một người trực”. Đây là thí nghiệm cho thấy snapshot ổn định không đồng nghĩa với serializable.

### 8.1. Chuẩn bị bảng lịch trực

```sql
DROP TABLE IF EXISTS public.doctor_roster;

CREATE TABLE public.doctor_roster (
    doctor_id INTEGER PRIMARY KEY,
    doctor_name TEXT NOT NULL,
    on_call BOOLEAN NOT NULL
);

INSERT INTO public.doctor_roster
VALUES
    (1, 'An', TRUE),
    (2, 'Binh', TRUE);
```

Đảm bảo cả hai bác sĩ đều đang trực trước khi chạy thử.

### 8.2. Chạy hai giao dịch

**Phiên A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*)
FROM public.doctor_roster
WHERE on_call = TRUE;
-- 2
```

**Phiên B:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*)
FROM public.doctor_roster
WHERE on_call = TRUE;
-- 2
```

Cả hai đều dựa vào snapshot có hai người đang trực. A cập nhật hàng An:

```sql
-- Phiên A
UPDATE public.doctor_roster
SET on_call = FALSE
WHERE doctor_id = 1;

COMMIT;
```

B cập nhật hàng Bình:

```sql
-- Phiên B
UPDATE public.doctor_roster
SET on_call = FALSE
WHERE doctor_id = 2;

COMMIT;
```

Vì hai giao dịch ghi hai hàng khác nhau, PostgreSQL REPEATABLE READ có thể cho cả hai commit. Kiểm tra:

```sql
SELECT doctor_id, doctor_name, on_call
FROM public.doctor_roster
ORDER BY doctor_id;
```

Kết quả có thể là cả hai `on_call = FALSE`. Bất biến nghiệp vụ bị phá vỡ dù mỗi giao dịch đã đọc snapshot ổn định.

Đây là write skew, thể hiện giới hạn quan trọng của SI.

### 8.3. Bảo vệ bằng SERIALIZABLE

Đặt lại cả hai bác sĩ thành `TRUE`, rồi lặp lại quy trình nhưng đổi cả hai giao dịch thành:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
```

Cả A và B đọc số người đang trực, sau đó mỗi giao dịch định tắt một người. PostgreSQL SSI theo dõi các phụ thuộc và có thể hủy một trong hai giao dịch bằng lỗi serialization. Không nên kỳ vọng giao dịch cụ thể nào luôn là giao dịch bị hủy; kết quả phụ thuộc lịch chạy và thời điểm phát hiện.

Ứng dụng cần xử lý lỗi `40001`, rollback và thử lại toàn bộ giao dịch. Khi thử lại, giao dịch mới đọc trạng thái đã commit của giao dịch thắng và có thể thấy chỉ còn một bác sĩ trực; do đó nó không còn đủ điều kiện tắt người còn lại.

Thí nghiệm này là minh họa cho cơ chế. Trong ứng dụng thật, nên thiết kế kiểm tra bất biến trong transaction và có retry với giới hạn, backoff, log và cơ chế idempotency phù hợp.

## 9. Snapshot isolation và lost update

Lost update thường được mô tả là hai giao dịch cùng đọc một giá trị cũ, tính giá trị mới rồi ghi đè lên nhau. Một số biến thể SI phát hiện xung đột ghi đồng thời trên cùng hàng và hủy một giao dịch. Tuy nhiên, không thể dựa vào tên “snapshot isolation” để mặc định mọi kiểu mất cập nhật đều bị ngăn trong mọi DBMS hoặc mọi cách viết SQL.

Cần phân biệt:

1. **Hai lệnh ghi trực tiếp cùng một hàng trong khi giao dịch kia vẫn mở**: cơ chế SI/locking có thể khiến giao dịch sau chờ hoặc bị lỗi write conflict.
2. **Ứng dụng đọc trước, kết thúc giao dịch, tính toán lâu rồi mở giao dịch khác để ghi giá trị tuyệt đối**: xung đột có thể xảy ra giữa hai transaction boundary khác nhau; snapshot mới của lệnh ghi không tự biết phép tính bắt nguồn từ dữ liệu cũ.
3. **Ghi vào các hàng khác nhau nhưng cùng phụ thuộc một bất biến**: có thể là write skew, không phải lost update trên cùng hàng.

Để phòng tránh, dùng cập nhật nguyên tử dựa trên giá trị hiện hành, khóa trước khi đọc, optimistic version hoặc SERIALIZABLE tùy nghiệp vụ.

Ví dụ cập nhật tăng số dư an toàn hơn so với gửi giá trị tuyệt đối:

```sql
UPDATE public.si_accounts
SET balance = balance + 200
WHERE account_id = 101;
```

Nếu điều kiện nghiệp vụ cần bảo vệ nhiều hàng, chỉ một câu UPDATE trên một hàng không đủ; cần kiểm tra và khóa dữ liệu liên quan hoặc dùng SERIALIZABLE.

## 10. Khác biệt giữa các hệ quản trị

Từ “snapshot isolation” có thể được dùng như tên một mức cô lập cụ thể, một đặc tính của transaction hoặc một cách mô tả cách DBMS triển khai REPEATABLE READ. Cần đọc tài liệu của đúng hệ quản trị và phiên bản.

| DBMS | Cách tiếp cận có liên quan | Điều cần chú ý |
| --- | --- | --- |
| PostgreSQL | MVCC; REPEATABLE READ dựa trên snapshot; SERIALIZABLE dùng SSI | REPEATABLE READ vẫn có thể write skew; SERIALIZABLE có thể trả lỗi 40001 |
| SQL Server | Có các tùy chọn READ_COMMITTED_SNAPSHOT và SNAPSHOT isolation | SNAPSHOT thường được bật ở mức database; cần phân biệt với READ COMMITTED dựa trên row versioning |
| Oracle | Consistent read dựa trên undo và SCN; transaction có read consistency | Cách gọi/mapping isolation khác mô hình bốn mức đơn giản; SERIALIZABLE có quy tắc riêng |
| MySQL InnoDB | MVCC cho consistent read; REPEATABLE READ thường dùng read view của transaction | Locking read và consistent read có hành vi khác nhau; cần xét gap/next-key locks và cấu hình |

Bảng chỉ nêu nét khái quát, không thay thế tài liệu chính thức của đúng phiên bản và engine. Đặc biệt, không nên bê nguyên thử nghiệm PostgreSQL sang SQL Server hay MySQL rồi kỳ vọng cùng kết quả.

### 10.1. SQL Server: READ COMMITTED SNAPSHOT và SNAPSHOT

SQL Server có hai khái niệm dễ nhầm:

- **READ_COMMITTED_SNAPSHOT (RCSI)**: READ COMMITTED sử dụng row versioning để mỗi câu lệnh đọc snapshot nhất quán ở cấp câu lệnh.
- **SNAPSHOT isolation**: giao dịch sử dụng snapshot ở cấp transaction, nếu tùy chọn database cần thiết đã được bật.

Cả hai giảm chặn giữa đọc và ghi theo cơ chế phiên bản, nhưng khác nhau ở thời điểm snapshot và cách phát hiện cập nhật xung đột. Không nên coi RCSI và SNAPSHOT là cùng một chế độ.

### 10.2. MySQL InnoDB: consistent read và locking read

InnoDB dùng MVCC cho consistent nonlocking reads. Ở REPEATABLE READ, các consistent read trong một transaction thông thường dùng cùng read view. Tuy nhiên, `SELECT ... FOR UPDATE` hoặc `FOR SHARE` là locking read và tuân theo quy tắc khóa, không đơn giản là đọc cùng snapshot như SELECT thường.

Do đó, khi trộn consistent read với locking read, cần hiểu chính xác mỗi câu lệnh lấy dữ liệu theo cơ chế nào. Chỉ biết mức isolation là REPEATABLE READ chưa đủ để dự đoán mọi tương tác.

## 11. Lợi ích, chi phí và cân nhắc vận hành

### 11.1. Lợi ích

- **Đọc ít chặn ghi**: truy vấn đọc thông thường có thể xem phiên bản đã commit mà không phải chờ hàng đang được cập nhật.
- **Góc nhìn ổn định**: transaction-level snapshot giúp nhiều truy vấn trong cùng giao dịch phân tích trên cùng một trạng thái dữ liệu.
- **Tính nhất quán cho báo cáo**: nhiều câu truy vấn có thể được diễn giải trên cùng ảnh chụp thay vì trộn trạng thái tại nhiều thời điểm.
- **Hỗ trợ tương tranh cao**: đọc và ghi có thể chồng lấn tốt hơn trong workload phù hợp.

### 11.2. Chi phí và rủi ro

- **Giữ phiên bản cũ**: giao dịch snapshot dài có thể trì hoãn việc thu hồi phiên bản.
- **Xung đột ghi**: giao dịch đồng thời sửa cùng một hàng vẫn phải được điều phối; một transaction có thể chờ hoặc thất bại.
- **Write skew**: snapshot ổn định không bảo đảm bất biến liên hàng nếu các giao dịch ghi những hàng khác nhau.
- **Retry**: ở SERIALIZABLE, một số giao dịch bị hủy để bảo đảm lịch tuần tự hóa; ứng dụng phải retry toàn bộ transaction.
- **Bộ nhớ/lưu trữ và dọn dẹp**: MVCC tạo các phiên bản cần theo dõi, có thể làm tăng áp lực vacuum/cleanup hoặc version store tùy DBMS.

### 11.3. Khi nào snapshot isolation hữu ích?

SI phù hợp với nhiều workload đọc nhiều, cần kết quả nhất quán trong một transaction và muốn giảm chờ do đọc/ghi. Ví dụ: báo cáo nhiều truy vấn cần cùng góc nhìn, giao dịch đọc nhiều dữ liệu rồi cập nhật một số hàng, hoặc luồng xử lý cần snapshot ổn định.

Nhưng nếu nghiệp vụ có bất biến liên hàng — như tổng hạn mức, số người trực tối thiểu, số ghế còn trống, giới hạn số đơn được nhận — phải chủ động bảo vệ bất biến đó. Cân nhắc ràng buộc database, khóa một hàng đại diện, khóa tập hàng, hoặc SERIALIZABLE.

## 12. Cách thiết kế ứng dụng khi dùng snapshot

### 12.1. Giữ transaction ngắn

Đừng mở transaction, để người dùng điền biểu mẫu trong vài phút rồi mới commit. Một snapshot lâu có thể giữ phiên bản cũ và tạo gánh nặng cho DBMS. Với tương tác người dùng dài, cân nhắc optimistic locking bằng version thay vì giữ transaction và khóa liên tục.

### 12.2. Retry toàn bộ transaction khi serialization failure

Mẫu logic:

```text
Lặp với số lần tối đa có giới hạn:
    BEGIN ISOLATION LEVEL SERIALIZABLE
    Đọc dữ liệu cần thiết
    Kiểm tra bất biến
    Thực hiện cập nhật
    COMMIT

    Nếu serialization failure:
        ROLLBACK nếu cần
        đợi backoff
        chạy lại từ đầu
    Nếu lỗi khác:
        xử lý theo loại lỗi hoặc trả về
```

Không dùng lại kết quả đọc từ lần thử trước. Một lần retry phải lấy snapshot mới, đọc lại dữ liệu và quyết định lại. Các side effect ngoài transaction như gửi email hoặc gọi API cần thiết kế tách biệt, chẳng hạn transactional outbox và idempotency, để không lặp khi transaction retry.

### 12.3. Bảo vệ bất biến ở đúng phạm vi

Nếu điều kiện liên quan đến một hàng, có thể dùng `CHECK`, `UNIQUE`, hoặc cập nhật có điều kiện. Nếu điều kiện liên quan đến nhiều hàng, hãy xác định tập dữ liệu cần bảo vệ. Khóa từng hàng mà transaction sửa có thể chưa đủ nếu hai giao dịch sửa các hàng khác nhau nhưng cùng phụ thuộc vào một tổng hoặc điều kiện chung.

Ví dụ, giới hạn chỉ có tối đa 10 đặt chỗ đang hoạt động trong một sự kiện không thể luôn được bảo vệ bằng cách khóa riêng từng hàng đặt chỗ mới. Có thể cần một hàng sự kiện làm bộ đếm và cập nhật nguyên tử có điều kiện, hoặc SERIALIZABLE với retry, tùy yêu cầu và thiết kế.

## 13. Bài tập tự luyện

### Bài 1 — Snapshot khác READ COMMITTED thế nào?

T1 bắt đầu và đọc X = 10. T2 đổi X = 20 và commit. T1 đọc X lần nữa.

- Ở READ COMMITTED của PostgreSQL, lần đọc thứ hai trả về gì?
- Ở REPEATABLE READ của PostgreSQL, lần đọc thứ hai trả về gì?
- Vì sao?

### Bài 2 — Nhận diện write skew

Một hệ thống yêu cầu ít nhất một máy chủ luôn ở trạng thái ACTIVE. T1 và T2 cùng đọc hai máy chủ đều ACTIVE. T1 tắt máy chủ 1, T2 tắt máy chủ 2.

- Hai giao dịch có ghi cùng một hàng không?
- Snapshot isolation có thể cho cả hai commit không?
- Cần bảo vệ bất biến ở phạm vi nào?

### Bài 3 — Phân biệt SI và SERIALIZABLE

Nêu điểm giống và khác giữa snapshot isolation và serializable execution. Vì sao một transaction có thể đọc lặp lại cùng giá trị nhưng lịch tổng thể vẫn không tuần tự hóa được?

### Bài 4 — Xử lý serialization failure

Một giao dịch SERIALIZABLE bị PostgreSQL hủy với SQLSTATE 40001. Ứng dụng nên retry câu UPDATE cuối hay toàn bộ transaction? Vì sao cần đọc lại dữ liệu?

## 14. Ghi nhớ

Snapshot isolation dùng MVCC để mỗi giao dịch đọc một ảnh chụp nhất quán của dữ liệu đã commit. Nó giúp ngăn dirty read, cung cấp góc nhìn ổn định và giảm chặn giữa các thao tác đọc với ghi trong nhiều workload. Tuy nhiên, snapshot nhất quán không tự động biến lịch thực thi thành một thứ tự tuần tự hợp lệ. Write skew là ví dụ điển hình: các giao dịch đọc cùng một điều kiện nhưng ghi các hàng khác nhau và cùng commit, khiến bất biến nghiệp vụ bị phá vỡ.

Khi chọn mức cô lập, hãy xác định rõ phạm vi snapshot (mỗi câu lệnh hay cả transaction), loại xung đột ghi mà DBMS phát hiện, các bất biến trải trên nhiều hàng và cách ứng dụng xử lý retry. PostgreSQL REPEATABLE READ là triển khai dựa trên snapshot isolation; SERIALIZABLE bổ sung phát hiện phụ thuộc để bảo vệ tuần tự hóa và có thể yêu cầu chạy lại toàn bộ giao dịch. Tên mức SQL là điểm bắt đầu, còn hành vi thực tế phải được xác định theo DBMS cụ thể.
