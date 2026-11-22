# Sai lệch ghi giữa các giao dịch (write skew)

Trong chương **Tính cô lập** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, *write skew* (sai lệch ghi giữa các giao dịch) là một hiện tượng quan trọng khi thiết kế tầng lưu trữ cho ứng dụng Java: **hai giao dịch đồng thời cùng đọc một điều kiện nghiệp vụ, mỗi giao dịch sửa dữ liệu khác nhau, và sau khi cả hai commit, điều kiện chung bị vi phạm**.

Write skew đặc biệt dễ bị bỏ sót khi ứng dụng dùng đọc theo phiên bản (*Multi-Version Concurrency Control*, MVCC) hoặc *snapshot isolation*. Mỗi giao dịch có thể nhìn thấy một ảnh chụp dữ liệu nhất quán, không đọc thay đổi chưa commit và không ghi đè trực tiếp lên hàng của giao dịch còn lại, nhưng **kết quả cuối cùng vẫn sai về mặt nghiệp vụ**.

Bài học này làm rõ dấu hiệu nhận biết, trình tự xảy ra write skew, giới hạn của các mức cô lập, cách thiết kế SQL và ranh giới transaction trong Java, cũng như cách kiểm chứng việc sửa lỗi.

## 1. Một ví dụ: phải luôn có ít nhất một bác sĩ trực

Giả sử một ca trực có hai bác sĩ **An** và **Bình**, cả hai đều đang trực. Quy tắc bắt buộc là:

> **Với mỗi ca trực, luôn có ít nhất một bác sĩ có trạng thái `on_call = true`.**

Một bác sĩ chỉ được nghỉ nếu vẫn còn người khác trực. Ứng dụng thực hiện thao tác xin nghỉ bằng cách:

1. Đếm số bác sĩ còn trực trong ca.
2. Nếu số lượng lớn hơn 1, cho bác sĩ đang yêu cầu nghỉ chuyển `on_call` thành `false`.
3. Commit giao dịch.

Thử xét **hai yêu cầu được xử lý đồng thời**:

| Thời điểm | Giao dịch T1: An xin nghỉ | Giao dịch T2: Bình xin nghỉ |
| --- | --- | --- |
| T0 | Dữ liệu ban đầu: An trực, Bình trực | Tổng số người trực = **2** |
| T1 | Đọc và thấy **2** người trực | |
| T2 | | Đọc và thấy **2** người trực |
| T3 | Cập nhật **An** thành không trực | |
| T4 | | Cập nhật **Bình** thành không trực |
| T5 | `COMMIT` thành công | |
| T6 | | `COMMIT` thành công |
| Kết quả | An không trực | Bình không trực → còn **0** người trực |

T1 đã kiểm tra “Bình vẫn trực”, còn T2 đã kiểm tra “An vẫn trực”. Hai nhận định đều đúng **trong ảnh chụp riêng của từng giao dịch**, nhưng không còn đúng sau khi cả hai cùng hoàn tất.

```text
Trạng thái đầu:
    An = trực      Bình = trực       ⇒ 2 người trực
       │                │
       └────┐      ┌────┘
            ▼      ▼
        T1 đọc 2   T2 đọc 2
            │      │
        T1 sửa An  T2 sửa Bình
            │      │
            └──┬───┘
               ▼
          Hai giao dịch commit
               ▼
    An = nghỉ      Bình = nghỉ       ⇒ 0 người trực (SAI)
```

Đây là **write skew**. Nó không phải là một giao dịch viết đè giá trị của giao dịch còn lại: T1 chỉ cập nhật hàng của An, T2 chỉ cập nhật hàng của Bình. Xung đột nằm ở **quy tắc phụ thuộc vào nhiều hàng**.

## 2. Định nghĩa chính xác và điều kiện xảy ra

Write skew là một bất thường của tính cô lập, trong đó nhiều giao dịch đọc những dữ kiện có liên hệ, rồi ghi lên những mục dữ liệu khác nhau theo cách khiến kết quả tổng hợp không tương đương với một lịch thực thi tuần tự hợp lệ.

Mẫu thường gặp là:

- **Bất biến chung:** một điều kiện liên quan nhiều hàng, nhiều bản ghi hoặc một phép tổng hợp phải luôn đúng, ví dụ `COUNT(on_call) >= 1`.
- **Đọc trước khi quyết định:** T1 và T2 cùng dựa vào dữ liệu ở thời điểm chưa bao gồm thay đổi của nhau.
- **Tập ghi tách nhau:** T1 và T2 thay đổi các hàng khác nhau, nên không nhất thiết gặp xung đột *write-write* trực tiếp.
- **Kiểm tra không được bảo vệ đủ mạnh:** cơ sở dữ liệu cho phép cả hai commit dù tổ hợp thay đổi phá vỡ bất biến.

Không phải cứ hai giao dịch ghi vào hai hàng khác nhau là write skew. Chỉ gọi là write skew khi các thao tác **phụ thuộc vào dữ liệu mà giao dịch kia đã đọc/ghi** và làm phát sinh một kết quả không thể giải thích bằng một thứ tự tuần tự hợp lệ theo quy tắc nghiệp vụ.

Trong ví dụ bác sĩ, nếu T1 chạy hoàn tất **trước khi** T2 bắt đầu, T2 sẽ thấy chỉ còn một bác sĩ trực và **phải từ chối** yêu cầu nghỉ của Bình. Nếu T2 chạy trước, T1 phải từ chối An. Không có cách sắp xếp tuần tự hợp lệ nào để **cả hai** cùng nghỉ. Việc cả hai commit vì thế thể hiện sự thiếu cô lập cần thiết.

### Quan hệ phụ thuộc gây ra write skew

T1 đọc trạng thái của Bình để quyết định cập nhật An. T2 đọc trạng thái của An để quyết định cập nhật Bình. Ta có hai phụ thuộc:

```text
T1 đọc Bình ────► T2 sửa Bình
T2 đọc An   ────► T1 sửa An
```

Đây là một chu trình phụ thuộc đọc–ghi (*read-write dependency cycle*): mỗi giao dịch đều ra quyết định dựa trên dữ liệu mà giao dịch kia thay đổi nhưng chưa xuất hiện trong ảnh chụp nó đã đọc. Đó là lý do việc chỉ tìm xung đột trên **cùng hàng được UPDATE** không đủ để phát hiện write skew.

## 3. Tái hiện bằng PostgreSQL ở mức REPEATABLE READ

Ví dụ sau dùng **PostgreSQL**, trong đó `REPEATABLE READ` sử dụng cơ chế tương đương *snapshot isolation* và vẫn có thể cho phép write skew. Thực hành bằng **hai kết nối SQL độc lập** tới cùng một database. Cần giữ đúng thứ tự xen kẽ giữa hai phiên A và B.

### 3.1. Tạo bảng và dữ liệu mẫu

Chạy một lần ở ngoài hai giao dịch:

```sql
CREATE TABLE shift_duty (
    shift_id   BIGINT NOT NULL,
    doctor_id  BIGINT NOT NULL,
    on_call    BOOLEAN NOT NULL,
    PRIMARY KEY (shift_id, doctor_id)
);

INSERT INTO shift_duty (shift_id, doctor_id, on_call)
VALUES
    (7, 101, TRUE),   -- An
    (7, 202, TRUE);  -- Bình

SELECT doctor_id, on_call
FROM shift_duty
WHERE shift_id = 7
ORDER BY doctor_id;
-- 101 | true
-- 202 | true
```

Bảng có khóa chính để ngăn trùng một bác sĩ trong cùng ca. **Khóa chính này không biểu đạt được** quy tắc “luôn có ít nhất một người trực” vì quy tắc liên quan tới **nhiều hàng**.

### 3.2. Phiên A và B cùng nhìn thấy hai bác sĩ trực

**Phiên A — T1:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS active_doctors
FROM shift_duty
WHERE shift_id = 7 AND on_call = TRUE;
-- Kết quả: 2

-- Tạm dừng; KHÔNG UPDATE/COMMIT vội.
```

**Phiên B — T2:** chạy trước khi A cập nhật:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS active_doctors
FROM shift_duty
WHERE shift_id = 7 AND on_call = TRUE;
-- Kết quả: 2

-- Tạm dừng; cả hai transaction đã có ảnh chụp ban đầu.
```

Ở thời điểm này, cả T1 và T2 đều tin rằng thao tác xin nghỉ của mình là hợp lệ, vì thấy số lượng bác sĩ trực lớn hơn 1.

### 3.3. Hai phiên cập nhật các hàng khác nhau

**Phiên A:**

```sql
UPDATE shift_duty
SET on_call = FALSE
WHERE shift_id = 7 AND doctor_id = 101 AND on_call = TRUE;
-- Cập nhật 1 hàng, chỉ hàng của An.

COMMIT;
```

**Phiên B**, sau khi A đã commit:

```sql
UPDATE shift_duty
SET on_call = FALSE
WHERE shift_id = 7 AND doctor_id = 202 AND on_call = TRUE;
-- Cập nhật 1 hàng, chỉ hàng của Bình.

COMMIT;
```

Với PostgreSQL ở mức `REPEATABLE READ`, lịch thực thi này có thể cho **cả hai giao dịch commit**, vì chúng cập nhật các hàng khác nhau. T2 dùng ảnh chụp đã thiết lập ở bước 3.2, nên không tự động đọc lại điều kiện “còn bao nhiêu bác sĩ trực” theo dữ liệu mới của T1.

Mở một giao dịch mới để kiểm tra:

```sql
SELECT COUNT(*) AS active_doctors
FROM shift_duty
WHERE shift_id = 7 AND on_call = TRUE;
-- 0: bất biến nghiệp vụ đã bị vi phạm.
```

**Điểm cần nhớ:** mọi dữ liệu mà T1 và T2 đọc đều là dữ liệu **đã commit** tại thời điểm ảnh chụp tương ứng; chúng không thực hiện dirty read. Sự cố xuất phát từ việc **hai quyết định hợp lệ riêng lẻ nhưng không hợp lệ khi kết hợp**.

Để chạy lại ví dụ, khôi phục cả hai hàng sang `TRUE` ngoài các transaction đang thực hành:

```sql
UPDATE shift_duty
SET on_call = TRUE
WHERE shift_id = 7;
```

## 4. Vì sao REPEATABLE READ và snapshot isolation chưa đủ?

Mức `REPEATABLE READ` theo tên gọi gợi ý rằng một giao dịch đọc lại cùng hàng sẽ không thấy giá trị thay đổi bởi giao dịch khác. Trong PostgreSQL, cơ chế snapshot giúp mỗi transaction thấy một ảnh chụp ổn định. Tuy nhiên:

- **Ảnh chụp ổn định không đảm bảo kết quả của hai giao dịch giống như chạy tuần tự.**
- **Ngăn việc hai giao dịch ghi cùng hàng không tự ngăn lỗi khi chúng ghi hai hàng khác nhau.**
- **Kiểm tra `COUNT(*)` trước rồi `UPDATE` sau không biến điều kiện `COUNT(*) >= 1` thành một ràng buộc được CSDL thực thi tự động.**

Write skew là phản ví dụ kinh điển cho nhận định “đã có snapshot isolation thì mọi transaction đều đúng về tính nhất quán nghiệp vụ”.

Các DBMS có hành vi khác nhau. Trong MySQL/InnoDB, mức `REPEATABLE READ` cũng sử dụng MVCC cho nhiều truy vấn đọc thông thường; các truy vấn có khóa và thao tác ghi có thêm quy tắc khóa riêng. SQL Server, Oracle và những hệ quản trị khác có các mức cô lập, chế độ snapshot hoặc cơ chế xung đột khác nhau. Vì vậy, muốn đánh giá một lịch write skew phải chỉ rõ **DBMS, phiên bản, engine, kiểu truy vấn và cơ chế khóa**; không thể suy ra chỉ từ nhãn `REPEATABLE READ`.

### Write skew khác các bất thường quen thuộc thế nào?

| Hiện tượng | Điều làm nó khác biệt | Đối chiếu với ca bác sĩ |
| --- | --- | --- |
| **Dirty read** | Đọc thay đổi **chưa commit** của giao dịch khác. | Không xảy ra: T1 và T2 chỉ đọc dữ liệu đã commit. |
| **Non-repeatable read** | Đọc lại cùng hàng, thấy giá trị khác do giao dịch khác đã commit. | Không cần xảy ra: ảnh chụp của mỗi transaction vẫn ổn định. |
| **Phantom read** | Chạy lại truy vấn theo điều kiện, tập hàng phù hợp thay đổi. | Không cần xảy ra trong một transaction: T1/T2 có thể chỉ đọc `COUNT` một lần. |
| **Lost update** | Một giao dịch ghi đè làm mất cập nhật của giao dịch kia trên dữ liệu cùng mục. | Không xảy ra: T1 sửa An, T2 sửa Bình, cả hai cập nhật đều được giữ. |
| **Write skew** | Hai giao dịch đọc chung một bất biến rồi ghi các mục khác nhau, khiến bất biến sai. | **Đúng:** hai bác sĩ cùng nghỉ dù yêu cầu tối thiểu một người trực. |

**Atomicity không tự chữa được write skew:** mỗi giao dịch vẫn commit đầy đủ các câu lệnh của riêng mình. **Consistency cũng cần thiết kế:** ràng buộc cục bộ như `NOT NULL`, `UNIQUE` hoặc `CHECK (on_call IN (TRUE, FALSE))` không bảo vệ được bất biến “ít nhất một bác sĩ trực” trong nhiều hàng nếu không có cơ chế bổ sung.

## 5. Cách khắc phục thứ nhất: SERIALIZABLE

Một giải pháp mạnh là thực thi **toàn bộ thao tác kiểm tra và cập nhật** ở mức `SERIALIZABLE`, với DBMS hiện thực đúng bảo đảm tuần tự hóa. Mức cô lập này yêu cầu các giao dịch đã commit có kết quả tương đương với một lịch thực thi tuần tự nào đó.

Trong PostgreSQL, cơ chế *Serializable Snapshot Isolation* (SSI) phát hiện các phụ thuộc nguy hiểm giữa các giao dịch. Với lịch hai bác sĩ cùng đọc 2 và cùng muốn nghỉ, không thể cho cả hai cùng commit hợp lệ. CSDL sẽ từ chối ít nhất một giao dịch, thường với lỗi SQLSTATE **`40001`** (*serialization_failure*).

Đặt lại dữ liệu để thực hành, sau đó chạy **trên cả hai phiên**:

**Phiên A:**

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM shift_duty
WHERE shift_id = 7 AND on_call = TRUE;
-- 2

UPDATE shift_duty
SET on_call = FALSE
WHERE shift_id = 7 AND doctor_id = 101 AND on_call = TRUE;

-- Chưa COMMIT, chuyển sang phiên B.
```

**Phiên B:**

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM shift_duty
WHERE shift_id = 7 AND on_call = TRUE;
-- 2, vì A chưa commit.

UPDATE shift_duty
SET on_call = FALSE
WHERE shift_id = 7 AND doctor_id = 202 AND on_call = TRUE;

-- Chưa COMMIT.
```

Lần lượt `COMMIT` ở A và B. Với lịch xung đột này, PostgreSQL phải ngăn cả hai kết quả cùng được lưu như thể hai giao dịch đều hợp lệ; một giao dịch có thể thất bại với `40001` ngay tại câu lệnh hoặc lúc commit. Giao dịch thất bại cần được **thực hiện lại từ đầu**: đọc lại số người trực và quyết định lại, lúc đó chỉ còn 1 và yêu cầu nghỉ tiếp theo phải bị từ chối.

### Retry đúng cách khi gặp serialization failure

Sai lầm phổ biến là chỉ chạy lại `UPDATE` cuối sau lỗi. Giá trị `COUNT(*)` được đọc trước đó **không còn đáng tin cậy cho một lượt thử mới**. Cần chạy lại toàn bộ phần logic transaction:

```text
for attempt = 1..MAX_ATTEMPTS:
    BEGIN SERIALIZABLE
    SELECT số bác sĩ trực
    nếu <= 1: ROLLBACK và báo không thể nghỉ
    UPDATE đúng bác sĩ đang trực
    COMMIT
    nếu thành công: kết thúc
    nếu serialization_failure (40001):
        ROLLBACK nếu cần
        đợi ngắn có độ lệch ngẫu nhiên; thử lại toàn bộ
    nếu lỗi khác: xử lý theo loại lỗi, không retry vô điều kiện
```

Thực tế cần giới hạn số lần thử, ghi nhận số lần xung đột và tránh gọi API hoặc gửi thông báo không thể hoàn tác bên trong phần transaction có thể được retry. Nếu mất kết nối đúng thời điểm commit, trạng thái giao dịch có thể không rõ với client: dùng mã yêu cầu duy nhất và kiểm tra trạng thái trước khi phát lại một nghiệp vụ có hiệu ứng một lần.

SERIALIZABLE giải quyết sai lệch về lịch thực thi, nhưng **không sửa logic nghiệp vụ sai**. Nếu chương trình không kiểm tra điều kiện còn người trực, một lịch thực thi tuần tự vẫn có thể cho tất cả nghỉ. Tất cả thao tác tham gia bảo vệ bất biến cũng phải dùng chiến lược tương thích.

## 6. Cách khắc phục thứ hai: khóa một hàng đại diện trước khi kiểm tra

Khi nghiệp vụ tập trung vào một nhóm hàng xác định, ta có thể **tuần tự hóa các yêu cầu trên cùng nhóm** bằng cách khóa hàng đại diện. Với ca trực, dùng một hàng `shifts` cho mỗi ca và bắt buộc mọi thao tác xin nghỉ phải khóa hàng này **trước khi đếm**.

Chuẩn bị bảng đại diện:

```sql
CREATE TABLE shifts (
    id BIGINT PRIMARY KEY
);

INSERT INTO shifts (id) VALUES (7);
```

Mỗi giao dịch xin nghỉ chạy theo quy trình **READ COMMITTED**:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT id
FROM shifts
WHERE id = 7
FOR UPDATE;
-- Giữ khóa hàng của ca 7 tới khi COMMIT/ROLLBACK.

SELECT COUNT(*) AS active_doctors
FROM shift_duty
WHERE shift_id = 7 AND on_call = TRUE;
-- Ứng dụng chỉ cho phép tiếp tục nếu COUNT > 1.

-- Chỉ khi COUNT > 1 và bác sĩ thực sự đang trực:
UPDATE shift_duty
SET on_call = FALSE
WHERE shift_id = 7 AND doctor_id = 101 AND on_call = TRUE;
-- Ứng dụng phải kiểm tra đúng 1 hàng được cập nhật.

COMMIT;
```

Đây là **phác thảo một nhánh thành công**: nếu không tồn tại ca trực, số người trực nhỏ hơn hoặc bằng 1, hay `UPDATE` không tác động đúng một hàng, ứng dụng phải `ROLLBACK` thay vì chạy `COMMIT`.

Nếu T1 đang giữ khóa hàng của ca 7, T2 cũng muốn xin nghỉ trong cùng ca sẽ **phải chờ**. Sau khi T1 commit, T2 mới lấy khóa, rồi thực hiện **một câu `SELECT COUNT(*)` riêng** ở mức `READ COMMITTED`; câu SELECT này thấy số người trực đã cập nhật. Khi chỉ còn một người, T2 từ chối yêu cầu.

**Vì sao phải nhấn mạnh READ COMMITTED?** Với những hệ quản trị sử dụng ảnh chụp cố định ở `REPEATABLE READ`, một transaction bắt đầu ảnh chụp trước khi chờ khóa có thể tiếp tục nhìn thấy dữ liệu cũ sau khi lấy được khóa. Không nên mặc định rằng khóa hàng đại diện cộng với mọi mức snapshot đều tự giải quyết write skew. Ở ví dụ PostgreSQL này, đọc số lượng trong câu lệnh riêng sau khi giữ khóa tại `READ COMMITTED` là phần quan trọng của thiết kế.

Giải pháp khóa hàng đại diện có các điều kiện:

- Mỗi giao dịch có thể ảnh hưởng bất biến của ca đều **phải khóa cùng hàng đại diện trước khi kiểm tra**, kể cả thao tác do job hoặc admin thực hiện.
- Không được gọi API chậm hay chờ người dùng trong lúc giữ khóa; giao dịch cần ngắn.
- Nếu một thao tác tác động nhiều ca, phải khóa các hàng theo **thứ tự nhất quán** để giảm deadlock.
- Khóa giảm khả năng xử lý đồng thời đối với **cùng ca**, nhưng các ca khác nhau vẫn có thể xử lý song song.
- Nếu bảng `shifts` chứa các khóa cha của `shift_duty` trong mô hình thật, nên bổ sung khóa ngoại; ví dụ giản lược ở trên chỉ tập trung vào chiến lược khóa.

Việc chỉ đặt `SELECT ... FOR UPDATE` lên **một hàng của chính bác sĩ xin nghỉ** không đủ: hai bác sĩ sửa hai hàng khác nhau và không phải chờ nhau. Muốn khóa trực tiếp các hàng nhân viên, cần khóa **toàn bộ tập hàng liên quan** theo một giao thức nhất quán và cân nhắc rủi ro tập hàng thay đổi. Một hàng đại diện cố định thường dễ xác định ranh giới bảo vệ hơn.

## 7. Cách khắc phục thứ ba: đưa bất biến về một hàng có kiểm soát

Một lựa chọn khác là **biểu diễn số người đang trực bằng một bộ đếm ở hàng ca trực**, sau đó giảm bộ đếm bằng cập nhật có điều kiện. Mọi lượt xin nghỉ sẽ cùng ghi vào hàng đếm, chuyển sự phụ thuộc nhiều hàng thành xung đột ghi trực tiếp mà CSDL xử lý được.

Ví dụ bảng tổng hợp riêng, sau khi đồng bộ giá trị ban đầu với bảng phân công:

```sql
CREATE TABLE shift_capacity (
    shift_id       BIGINT PRIMARY KEY,
    on_call_count  INTEGER NOT NULL CHECK (on_call_count >= 1)
);

INSERT INTO shift_capacity (shift_id, on_call_count)
VALUES (7, 2);
```

Trong **cùng một transaction**, trước khi cho một bác sĩ nghỉ:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

UPDATE shift_capacity
SET on_call_count = on_call_count - 1
WHERE shift_id = 7 AND on_call_count > 1;
-- BẮT BUỘC kiểm tra số hàng cập nhật = 1; nếu = 0 thì ROLLBACK.

UPDATE shift_duty
SET on_call = FALSE
WHERE shift_id = 7 AND doctor_id = 101 AND on_call = TRUE;
-- BẮT BUỘC kiểm tra số hàng cập nhật = 1; nếu = 0 thì ROLLBACK.

COMMIT;
```

Khi hai giao dịch đồng thời cùng giảm bộ đếm, chúng ghi **cùng hàng**. Ở PostgreSQL `READ COMMITTED`, giao dịch đến sau sẽ đợi khóa cập nhật nếu cần, kiểm tra lại điều kiện `on_call_count > 1` trên giá trị hiện hành và chỉ thành công khi còn đủ người trực. Ràng buộc `CHECK` là lớp bảo vệ bổ sung.

Phương pháp này cần một **quy ước cập nhật dữ liệu chặt chẽ**: nếu có đường ghi sửa `shift_duty` mà không cập nhật `shift_capacity` tương ứng, bộ đếm có thể lệch thực tế. Có thể áp dụng trigger, stored procedure, quyền ghi giới hạn hoặc kiểm soát tất cả đường ghi trong service cùng với quy trình đối soát định kỳ.

Một biến thể khác là **đặt thông tin cần bảo vệ trên cùng hàng** ngay từ thiết kế schema, giúp ràng buộc thông qua một phép `UPDATE ... WHERE ...`. Cách đó phù hợp khi mô hình nghiệp vụ cho phép, nhưng không nên cố gộp những dữ liệu độc lập vào một hàng chỉ để né giải pháp giao dịch.

## 8. Ví dụ Java/JDBC dùng khóa hàng đại diện

Trong ứng dụng Java, lỗi write skew thường xuất hiện ở lớp service theo kiểu “đọc kiểm tra → ghi dữ liệu”, nhất là khi mỗi request sử dụng kết nối và giao dịch riêng. Ví dụ sau cho thao tác xin nghỉ tại ca trực 7 (áp dụng được cho mọi `shiftId`) dùng chiến lược **READ COMMITTED + `FOR UPDATE` trên hàng ca**.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ShiftService {
    private final DataSource dataSource;

    public ShiftService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void leaveDuty(long shiftId, long doctorId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setTransactionIsolation(
                    Connection.TRANSACTION_READ_COMMITTED);
            connection.setAutoCommit(false);

            try {
                // Tất cả yêu cầu của cùng ca phải khóa cùng một hàng này.
                try (PreparedStatement lock = connection.prepareStatement(
                        "SELECT id FROM shifts WHERE id = ? FOR UPDATE")) {
                    lock.setLong(1, shiftId);
                    try (ResultSet rows = lock.executeQuery()) {
                        if (!rows.next()) {
                            throw new IllegalArgumentException(
                                    "Khong tim thay ca truc");
                        }
                    }
                }

                int active;
                try (PreparedStatement count = connection.prepareStatement(
                        "SELECT COUNT(*) FROM shift_duty " +
                        "WHERE shift_id = ? AND on_call = TRUE")) {
                    count.setLong(1, shiftId);
                    try (ResultSet rows = count.executeQuery()) {
                        rows.next();
                        active = rows.getInt(1);
                    }
                }

                if (active <= 1) {
                    throw new IllegalStateException(
                            "Phai con it nhat mot bac si truc");
                }

                try (PreparedStatement update = connection.prepareStatement(
                        "UPDATE shift_duty SET on_call = FALSE " +
                        "WHERE shift_id = ? AND doctor_id = ? AND on_call = TRUE")) {
                    update.setLong(1, shiftId);
                    update.setLong(2, doctorId);
                    if (update.executeUpdate() != 1) {
                        throw new IllegalArgumentException(
                                "Bac si khong o trang thai dang truc");
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
```

Các điểm cần đánh giá khi đưa vào sản phẩm thật:

1. **Ranh giới transaction** bao quanh việc lấy khóa, kiểm tra bất biến và cập nhật; không tách thành những method tự commit độc lập.
2. **Thứ tự thực thi** có ý nghĩa: khóa hàng ca trước, rồi mới đọc số người trực bằng câu `SELECT` riêng trong cùng giao dịch ở `READ COMMITTED`.
3. **Cập nhật có điều kiện** chỉ sửa bác sĩ còn trực, đồng thời kiểm tra chính xác số hàng được cập nhật; không mặc định rằng có bác sĩ hay bản ghi hợp lệ.
4. **Rollback** xảy ra khi thiếu người trực, không tìm thấy bác sĩ hoặc có lỗi SQL; ngoại lệ nghiệp vụ khiến transaction kết thúc trước commit.
5. **Connection pool** cần quản lý việc khôi phục cấu hình isolation và auto-commit theo quy ước của pool. Đừng để việc thay đổi trạng thái kết nối ảnh hưởng request khác.
6. **Deadlock/timeout** có thể xảy ra nếu luồng khác khóa bảng hoặc các hàng theo thứ tự trái ngược; cần phân loại SQLSTATE và thiết kế retry giới hạn nếu thích hợp.
7. **Quyền thao tác** cần được kiểm tra ở service trước khi thực hiện thay đổi dữ liệu; khóa và cô lập không thay thế xác thực hay phân quyền.

Đoạn mã chỉ minh họa thao tác “xin nghỉ” đồng bộ trên một CSDL. Nếu nghiệp vụ gửi thông báo, ghi sự kiện hoặc cập nhật một dịch vụ khác, cần bảo đảm xử lý idempotency và cân nhắc mẫu *transactional outbox* để tránh phát ra hiệu ứng ngoài transaction trước khi dữ liệu đã commit.

Trong Spring, có thể sử dụng `@Transactional(isolation = Isolation.READ_COMMITTED)` ở phương thức service và gọi truy vấn `SELECT ... FOR UPDATE` qua repository, với điều kiện tất cả các thao tác dùng **cùng transaction manager/cùng transaction** và giao thức khóa được mọi luồng cập nhật tuân thủ. Cần kiểm tra cơ chế proxy, rollback rule và hành vi truy vấn thực tế của JPA/ORM.

## 9. Một ví dụ khác: giữ chỗ khi chỉ còn một suất

Giả sử lớp học có tối đa **30 học viên**, hiện có 29 người. Hai học viên mới lần lượt được xử lý qua hai giao dịch:

```text
T1: SELECT COUNT(*) FROM enrollments WHERE class_id = 12;  -- 29
T2: SELECT COUNT(*) FROM enrollments WHERE class_id = 12;  -- 29
T1: INSERT enrollment (class_id=12, student_id=501);       -- một hàng mới
T2: INSERT enrollment (class_id=12, student_id=502);       -- một hàng khác
T1: COMMIT
T2: COMMIT
Cuối cùng: 31 học viên, vượt giới hạn 30.
```

Đây cũng có thể là **write skew** dưới mô hình snapshot cho phép cả hai giao dịch commit: mỗi giao dịch dựa trên một điều kiện đếm chung rồi ghi vào hàng khác nhau. Khóa duy nhất `(class_id, student_id)` ngăn một học viên đăng ký trùng nhưng **không hạn chế tổng số học viên** của lớp.

Cách bảo vệ tương tự bài toán trực bác sĩ: một hàng đại diện cho lớp được khóa trước khi kiểm tra số lượng, một cột `remaining_seats` được giảm bằng `UPDATE ... WHERE remaining_seats > 0`, hoặc kiểm tra và chèn trong giao dịch `SERIALIZABLE` kèm xử lý retry. Cần thống nhất mọi con đường đăng ký, hủy đăng ký, di chuyển lớp và sửa sĩ số để không làm hỏng bất biến.

## 10. Kiểm thử và chẩn đoán write skew

Một bài kiểm thử đúng phải chủ động tạo **hai giao dịch độc lập chồng lấn**, vì một chuỗi thao tác chạy tuần tự thường không bộc lộ lỗi:

1. Khởi tạo dữ liệu với đúng hai bác sĩ trực và xác nhận `COUNT(*) = 2`.
2. Mở hai transaction ở mức cần kiểm tra trên **hai connection** khác nhau.
3. Dùng một điểm đồng bộ trong test để **cả hai đều hoàn tất bước đọc điều kiện** trước khi cho phép bất kỳ giao dịch nào commit.
4. Cho hai giao dịch cập nhật **hai hàng khác nhau** rồi kết thúc; ghi lại kết quả commit, SQLSTATE và số hàng được cập nhật.
5. Từ kết nối mới, kiểm tra bất biến: `SELECT COUNT(*) ... WHERE on_call = TRUE` phải luôn **>= 1**.
6. Chạy lại với chiến lược được chọn: SERIALIZABLE hoặc khóa hàng đại diện hoặc cập nhật bộ đếm; kiểm tra rằng tối đa một yêu cầu xin nghỉ được chấp nhận.

Nếu dùng `SERIALIZABLE`, kiểm thử nên xác nhận **giao dịch bị từ chối được chạy lại từ đầu** và cuối cùng trả về một kết quả nghiệp vụ đúng. Nếu dùng khóa hàng đại diện, kiểm tra giao dịch thứ hai chỉ đọc số người trực **sau khi** giao dịch thứ nhất trả khóa.

Trong vận hành, những dấu hiệu nên theo dõi gồm lỗi `40001`, deadlock, thời gian chờ khóa, xung đột optimistic lock và số lần retry. Chúng là dữ kiện giúp hiểu mức độ tranh chấp, không có nghĩa mọi xung đột đều là write skew. Một bất biến được bảo vệ có thể khiến hệ thống tăng số lần retry hoặc chờ khóa khi tải cao; cần đánh đổi dựa trên yêu cầu đúng đắn và thông lượng.

### Các ngộ nhận dễ gặp

| Nhận định | Vì sao chưa đúng |
| --- | --- |
| “Hai transaction không sửa cùng hàng nên không có xung đột.” | Chúng vẫn có thể phụ thuộc vào các hàng mà nhau đã đọc. |
| “Dùng MVCC và REPEATABLE READ là đủ an toàn.” | Ảnh chụp ổn định vẫn có thể cho write skew. |
| “`SELECT COUNT(*)` đã kiểm tra điều kiện, vậy có thể commit.” | Điều kiện có thể trở thành sai do giao dịch khác commit song song. |
| “Thêm index sẽ giải quyết write skew.” | Index cải thiện kế hoạch truy vấn, không tự áp đặt bất biến nhiều hàng. |
| “Khóa riêng hàng bác sĩ đang xin nghỉ là đủ.” | Hai giao dịch khóa hai hàng khác nhau vẫn có thể cho cả hai nghỉ. |
| “Có `CHECK` trên từng hàng là bảo đảm ít nhất một bác sĩ trực.” | Ràng buộc từng hàng không trực tiếp biểu đạt tổng số người trực của cả ca. |
| “Lỗi serializable chỉ cần chạy lại câu `UPDATE`.” | Phải đọc lại và quyết định lại trong **toàn bộ transaction**. |
| “SERIALIZABLE sẽ tự sửa mọi bug nghiệp vụ.” | Nó bảo đảm thứ tự tương đương tuần tự; logic áp dụng trong thứ tự đó vẫn phải đúng. |

## 11. Chọn phương án cho ứng dụng Java

Không có một lựa chọn duy nhất tốt nhất cho mọi workload. Hãy bắt đầu bằng việc viết rõ **bất biến**, xác định **các hàng mà một quyết định dựa vào**, rồi xét **những thao tác nào có thể xảy ra đồng thời**.

| Hướng tiếp cận | Điểm mạnh | Chi phí và điều kiện |
| --- | --- | --- |
| **SERIALIZABLE** | Bảo vệ lịch sử giao dịch ở mức tổng quát, phù hợp nhiều điều kiện đọc phức tạp. | Phải retry giao dịch bị từ chối; chi phí có thể tăng với workload xung đột. |
| **Khóa hàng đại diện** | Dễ diễn giải quy tắc “mỗi nhóm chỉ một giao dịch quyết định tại một thời điểm”. | Mọi đường ghi phải theo giao thức; cần giữ transaction ngắn, quản lý chờ khóa. |
| **Bộ đếm và cập nhật có điều kiện** | Biến kiểm tra và ghi thành thao tác trên cùng hàng, có thể rất hiệu quả. | Phải duy trì bộ đếm đồng bộ với dữ liệu chi tiết, kể cả trường hợp lỗi và thao tác ngoài luồng. |
| **Tái cấu trúc schema/ràng buộc** | Đưa bất biến vào CSDL để bảo vệ toàn bộ đường ghi. | Có thể cần đổi mô hình dữ liệu và triển khai migration cẩn thận. |

Khi dữ liệu nghiệp vụ thay đổi theo phiên bản schema, phải đánh giá lại các ràng buộc và khóa: thêm một đường ghi mới có thể bỏ qua giao thức cũ. Khi tối ưu truy vấn, cần đo cả **độ trễ do khóa** và **số lần retry** bên cạnh thời gian thực thi SQL. Tầng persistence an toàn là sự kết hợp của mô hình dữ liệu đúng, transaction đủ chặt, xử lý lỗi kết nối và cơ chế vận hành phù hợp.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Hai bác sĩ cùng thấy có hai người trực, mỗi người sửa hàng của mình rồi cùng commit và để lại 0 người trực. Tại sao đây không phải lost update?

Vì **không có cập nhật nào bị ghi đè**: thay đổi của cả hai đều tồn tại sau commit. Sai lệch xảy ra do quy tắc chung “phải còn người trực” bị phá vỡ.

**Câu 2.** Vì sao `READ COMMITTED` thường ngăn dirty read nhưng chưa đủ chống write skew nếu ứng dụng chỉ đọc số người trực rồi sửa hai hàng khác nhau?

Vì dữ liệu đã commit ở lúc kiểm tra có thể **trở nên không còn phù hợp** khi một transaction khác commit song song. Không có khóa/ràng buộc/mức cô lập phù hợp để bảo vệ điều kiện nhiều hàng.

**Câu 3.** Với PostgreSQL, tăng giao dịch từ `REPEATABLE READ` lên `SERIALIZABLE` và nhận lỗi `40001` thì sửa lỗi bằng cách nào?

Rollback hoặc kết thúc giao dịch lỗi, rồi **thực hiện lại toàn bộ transaction**, gồm cả bước đọc và kiểm tra số người trực, với giới hạn số lần thử. Nếu cuối cùng chỉ còn một người trực, từ chối cho nghỉ.

**Câu 4.** Nếu khóa hàng `shifts(id=7)`, sau đó đọc `COUNT(*)` trên PostgreSQL `READ COMMITTED`, điều kiện nào bắt buộc để giải pháp đúng?

Mọi luồng có thể thay đổi bất biến của ca 7 phải khóa **cùng hàng ca trước khi kiểm tra**, việc đếm diễn ra sau khi đã giữ khóa, và kiểm tra/cập nhật/commit thuộc cùng một transaction.

**Câu 5.** Vì sao chỉ thêm `UNIQUE (class_id, student_id)` không ngăn hai lượt đăng ký khiến lớp từ 29 thành 31 người?

Ràng buộc unique kiểm tra **trùng một học viên trong một lớp**, không kiểm tra **số lượng tối đa** của lớp. Giới hạn số lượng cần một cơ chế kiểm soát đồng thời riêng.

## Kết luận

Write skew xuất hiện khi nhiều giao dịch dựa trên **cùng một điều kiện nghiệp vụ**, ghi vào **những hàng khác nhau**, và cùng commit tạo ra trạng thái mà **không thứ tự tuần tự hợp lệ nào được phép tạo ra**. Nó cho thấy việc không đọc dữ liệu bẩn, không mất cập nhật cùng hàng và nhìn thấy snapshot ổn định vẫn chưa đủ cho các bất biến trải qua nhiều bản ghi.

Khi xây tầng persistence cho Java, hãy xác định rõ bất biến, ranh giới transaction và mọi đường ghi liên quan. Tùy mô hình, có thể dùng `SERIALIZABLE` kèm retry toàn giao dịch, khóa một hàng đại diện trước khi kiểm tra hoặc dùng cập nhật có điều kiện trên dữ liệu tổng hợp. Thiết kế đúng sẽ khiến **giao dịch cạnh tranh bị chờ, bị từ chối hoặc phải thử lại** khi cần, thay vì cho phép hai yêu cầu tưởng như hợp lệ cùng làm sai dữ liệu.
